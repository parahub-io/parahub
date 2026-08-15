"""
Tests for market item view counters (parahub/services/item_views.py) and the
beacon / owner-stats endpoints.

Invariants:
- One view per viewer per item per 24h (dedup)
- Owner views are never counted
- Hidden / non-visible items are never counted
- Totals survive a Redis wipe (lazy re-seed from Item.views_total)
- flush_totals persists to PG without bumping the optimistic-lock version
- view-stats endpoint is owner-scoped

Redis isolation: settings routes REDIS_APP_DB to 15 under `manage.py test`
(same guard as the cache), and setUp clears only the market:views:* prefix.
"""

import json

from django.test import TestCase, RequestFactory

from market.models import Item
from market.tests import (
    _create_instance, _create_account, _create_profile, _create_item,
    _make_auth_request, _make_anon_request,
)
from parahub.services import item_views
from parahub.endpoints.items import record_item_view, my_item_view_stats


def _clear_view_keys():
    r = item_views._r()
    keys = list(r.scan_iter('market:views:*'))
    if keys:
        r.delete(*keys)


class ViewCounterServiceTest(TestCase):
    def setUp(self):
        _clear_view_keys()
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        self.item = _create_item(self.profile)

    def tearDown(self):
        _clear_view_keys()

    def test_view_counted_once_per_viewer(self):
        self.assertTrue(item_views.record_view(self.item.id, 'p:viewer1'))
        self.assertFalse(item_views.record_view(self.item.id, 'p:viewer1'))
        stats = item_views.get_stats([self.item.id])
        self.assertEqual(stats[self.item.id], {'total': 1, 'last24h': 1})

    def test_distinct_viewers_counted(self):
        item_views.record_view(self.item.id, 'p:viewer1')
        item_views.record_view(self.item.id, 'a:someipuahash')
        stats = item_views.get_stats([self.item.id])
        self.assertEqual(stats[self.item.id], {'total': 2, 'last24h': 2})

    def test_reseed_from_pg_after_redis_wipe(self):
        Item.objects.filter(id=self.item.id).update(views_total=5)
        # Redis is empty (fresh test db) — first view must fold in the PG total.
        item_views.record_view(self.item.id, 'p:viewer1')
        stats = item_views.get_stats([self.item.id])
        self.assertEqual(stats[self.item.id]['total'], 6)
        self.assertEqual(stats[self.item.id]['last24h'], 1)

    def test_get_stats_falls_back_to_db_totals(self):
        # No Redis data at all: db_totals covers the pre-reseed window.
        stats = item_views.get_stats([self.item.id], db_totals={self.item.id: 7})
        self.assertEqual(stats[self.item.id], {'total': 7, 'last24h': 0})

    def test_flush_persists_and_keeps_version(self):
        version_before = self.item.version
        item_views.record_view(self.item.id, 'p:viewer1')
        item_views.record_view(self.item.id, 'p:viewer2')
        updated = item_views.flush_totals()
        self.assertEqual(updated, 1)
        self.item.refresh_from_db()
        self.assertEqual(self.item.views_total, 2)
        self.assertEqual(self.item.version, version_before)
        # Dirty set drained — nothing left to flush.
        self.assertEqual(item_views.flush_totals(), 0)

    def test_flush_drops_deleted_items(self):
        item_views.record_view(self.item.id, 'p:viewer1')
        Item.objects.filter(id=self.item.id).delete()
        self.assertEqual(item_views.flush_totals(), 0)
        r = item_views._r()
        self.assertIsNone(r.hget(item_views.KEY_TOTAL, self.item.id))


class ViewBeaconEndpointTest(TestCase):
    def setUp(self):
        _clear_view_keys()
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.owner_account = _create_account(self.instance, 'alice')
        self.owner = _create_profile(self.owner_account, self.instance)
        self.viewer_account = _create_account(self.instance, 'bob')
        self.viewer = _create_profile(self.viewer_account, self.instance)
        self.item = _create_item(self.owner)

    def tearDown(self):
        _clear_view_keys()

    def test_anonymous_view_counted(self):
        request = _make_anon_request(self.factory, 'post')
        request.META['HTTP_USER_AGENT'] = 'test-browser'
        status, body = record_item_view(request, self.item.id)
        self.assertEqual(status, 200)
        self.assertTrue(body['counted'])
        stats = item_views.get_stats([self.item.id])
        self.assertEqual(stats[self.item.id]['total'], 1)

    def test_owner_view_not_counted(self):
        request = _make_auth_request(self.factory, self.owner_account, self.owner, 'post')
        status, body = record_item_view(request, self.item.id)
        self.assertFalse(body['counted'])
        self.assertEqual(item_views.get_stats([self.item.id])[self.item.id]['total'], 0)

    def test_hidden_item_not_counted(self):
        self.item.is_active = False
        self.item.save()
        request = _make_auth_request(self.factory, self.viewer_account, self.viewer, 'post')
        status, body = record_item_view(request, self.item.id)
        self.assertFalse(body['counted'])

    def test_authed_viewer_counted_and_deduped(self):
        request = _make_auth_request(self.factory, self.viewer_account, self.viewer, 'post')
        self.assertTrue(record_item_view(request, self.item.id)[1]['counted'])
        request2 = _make_auth_request(self.factory, self.viewer_account, self.viewer, 'post')
        self.assertFalse(record_item_view(request2, self.item.id)[1]['counted'])

    def test_view_stats_owner_scoped(self):
        item_views.record_view(self.item.id, 'p:someviewer')
        # Owner sees their item's stats.
        request = _make_auth_request(self.factory, self.owner_account, self.owner)
        status, body = my_item_view_stats(request)
        self.assertEqual(status, 200)
        self.assertEqual(body['stats'][self.item.id], {'total': 1, 'last24h': 1})
        # Another profile gets no stats for items it doesn't own.
        request2 = _make_auth_request(self.factory, self.viewer_account, self.viewer)
        status2, body2 = my_item_view_stats(request2)
        self.assertNotIn(self.item.id, body2['stats'])
