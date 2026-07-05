"""
Tests for notification preference system.

Tests invariants that must never break:
- Profile.notification_prefs defaults to empty dict (all enabled)
- _should_notify respects per-category prefs
- Unknown notification types always send
- Missing profile = always send
- Allowed-keys filtering for pref updates
"""

from unittest.mock import patch

from django.test import TestCase, RequestFactory
from django.utils import timezone

from identity.models import Account, Profile
from core.models import Instance
from notifications.models import Notification, Activity
from notifications.services import (
    _should_notify, emit_notification, _serialize,
    record_activity, _serialize_activity,
)
from notifications import api as napi


def _req(profile, post=False):
    """A real request (RequestFactory sets REMOTE_ADDR=127.0.0.1 → @ratelimit
    skips) carrying the resolved auth_profile, for calling endpoints directly."""
    rf = RequestFactory()
    r = rf.post('/') if post else rf.get('/')
    r.auth_profile = profile
    return r


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_instance():
    return Instance.objects.create(
        domain='test.parahub.io',
        name='Test Instance',
        public_key='test-key',
    )


def _create_account(instance, username='alice', **kwargs):
    return Account.objects.create_user(
        username=username,
        email=f'{username}@test.parahub.io',
        password='testpass123',
        instance=instance,
        **kwargs,
    )


def _create_profile(account, instance, local_name=None, is_primary=True, **kwargs):
    local_name = local_name or account.username
    return Profile.objects.create(
        account=account,
        instance=instance,
        local_name=local_name,
        display_name=local_name.title(),
        is_primary=is_primary,
        profile_type=kwargs.pop('profile_type', Profile.ProfileType.PERSONAL),
        **kwargs,
    )


# ===========================================================================
# notification_prefs field defaults
# ===========================================================================

class NotificationPrefsDefaultTest(TestCase):
    """Test that Profile.notification_prefs defaults correctly."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance)
        self.profile = _create_profile(self.account, self.instance)

    def test_default_is_empty_dict(self):
        """Empty dict = all notifications enabled."""
        self.assertEqual(self.profile.notification_prefs, {})

    def test_default_persists_after_save(self):
        self.profile.save()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.notification_prefs, {})

    def test_can_set_and_retrieve_prefs(self):
        self.profile.notification_prefs = {'social': False, 'contracts': True}
        self.profile.save(update_fields=['notification_prefs'])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.notification_prefs, {'social': False, 'contracts': True})


# ===========================================================================
# _should_notify logic
# ===========================================================================

class ShouldNotifyTest(TestCase):
    """Test _should_notify respects per-category prefs."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance)
        self.profile = _create_profile(self.account, self.instance)

    def _set_prefs(self, prefs):
        self.profile.notification_prefs = prefs
        self.profile.save(update_fields=['notification_prefs'])

    def test_empty_prefs_all_enabled(self):
        """Empty prefs dict = all categories enabled."""
        self.assertTrue(_should_notify(self.account, 'partner_added'))
        self.assertTrue(_should_notify(self.account, 'new_contract'))
        self.assertTrue(_should_notify(self.account, 'new_poll'))
        self.assertTrue(_should_notify(self.account, 'incoming_call'))

    def test_disabled_social_blocks_partner_added(self):
        self._set_prefs({'social': False})
        self.assertFalse(_should_notify(self.account, 'partner_added'))

    def test_disabled_social_blocks_verification_received(self):
        self._set_prefs({'social': False})
        self.assertFalse(_should_notify(self.account, 'verification_received'))

    def test_disabled_contracts_blocks_new_contract(self):
        self._set_prefs({'contracts': False})
        self.assertFalse(_should_notify(self.account, 'new_contract'))

    def test_disabled_contracts_blocks_contract_signed(self):
        self._set_prefs({'contracts': False})
        self.assertFalse(_should_notify(self.account, 'contract_signed'))

    def test_disabled_contracts_blocks_new_debt(self):
        self._set_prefs({'contracts': False})
        self.assertFalse(_should_notify(self.account, 'new_debt'))

    def test_disabled_governance_blocks_new_poll(self):
        self._set_prefs({'governance': False})
        self.assertFalse(_should_notify(self.account, 'new_poll'))

    def test_disabled_calls_blocks_incoming_call(self):
        self._set_prefs({'calls': False})
        self.assertFalse(_should_notify(self.account, 'incoming_call'))

    def test_unknown_type_always_sends(self):
        """Unknown notification types bypass prefs check."""
        self._set_prefs({
            'social': False, 'contracts': False,
            'governance': False, 'calls': False,
        })
        self.assertTrue(_should_notify(self.account, 'unknown_type'))

    def test_no_profile_always_sends(self):
        """Account without a primary profile = always send."""
        orphan = Account.objects.create_user(
            username='orphan', email='orphan@test.parahub.io',
            password='testpass123', instance=self.instance,
        )
        self.assertTrue(_should_notify(orphan, 'partner_added'))

    def test_selective_disable(self):
        """Disabling one category doesn't affect others."""
        self._set_prefs({'social': False})
        self.assertFalse(_should_notify(self.account, 'partner_added'))
        self.assertTrue(_should_notify(self.account, 'new_contract'))
        self.assertTrue(_should_notify(self.account, 'new_poll'))

    def test_explicit_true_still_sends(self):
        self._set_prefs({'social': True})
        self.assertTrue(_should_notify(self.account, 'partner_added'))


# ===========================================================================
# Allowed-keys filtering (endpoint logic)
# ===========================================================================

class NotificationPrefsFilteringTest(TestCase):
    """Test that the endpoint filtering logic keeps only allowed keys."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance)
        self.profile = _create_profile(self.account, self.instance)

    def _apply_endpoint_filter(self, raw_prefs):
        """Simulate the endpoint's allowed-keys filtering."""
        allowed_keys = {'social', 'contracts', 'governance', 'calls'}
        return {k: bool(v) for k, v in raw_prefs.items() if k in allowed_keys}

    def test_allowed_keys_pass_through(self):
        result = self._apply_endpoint_filter({
            'social': False, 'contracts': True,
            'governance': False, 'calls': True,
        })
        self.assertEqual(result, {
            'social': False, 'contracts': True,
            'governance': False, 'calls': True,
        })

    def test_disallowed_keys_filtered_out(self):
        result = self._apply_endpoint_filter({
            'social': False, 'evil_key': True, 'admin': True,
        })
        self.assertNotIn('evil_key', result)
        self.assertNotIn('admin', result)
        self.assertIn('social', result)

    def test_values_coerced_to_bool(self):
        result = self._apply_endpoint_filter({'social': 0, 'calls': 1})
        self.assertIs(result['social'], False)
        self.assertIs(result['calls'], True)

    def test_empty_input(self):
        result = self._apply_endpoint_filter({})
        self.assertEqual(result, {})


# ===========================================================================
# emit_notification dispatcher (persist + WS + push fan-out)
# ===========================================================================

class EmitNotificationTest(TestCase):
    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance)
        self.profile = _create_profile(self.account, self.instance)

    @patch('parahub.services.ws_publish.ws_publish')
    @patch('notifications.services.send_push_notification', return_value=(1, 0))
    def test_creates_row_and_fans_out(self, mock_push, mock_ws):
        emit_notification(self.account, type='new_contract', title='T', body='B',
                          url='/contracts/x', data={'contract_id': 'x'})
        n = Notification.objects.get(recipient=self.account)
        self.assertEqual(n.type, 'new_contract')
        self.assertEqual(n.category, 'contracts')  # derived from TYPE_TO_CATEGORY
        self.assertEqual(n.title, 'T')
        self.assertEqual(n.url, '/contracts/x')
        self.assertIsNone(n.read_at)
        # off-device push fired
        mock_push.assert_called_once()
        # live WS event on the recipient's personal channel
        mock_ws.assert_called_once()
        channel, payload = mock_ws.call_args.args
        self.assertEqual(channel, f'user:{self.account.id}')
        self.assertEqual(payload['type'], 'notification.new')
        self.assertEqual(payload['notification']['id'], n.id)

    @patch('parahub.services.ws_publish.ws_publish')
    @patch('notifications.services.send_push_notification', return_value=(1, 0))
    def test_muted_category_persists_nothing(self, mock_push, mock_ws):
        self.profile.notification_prefs = {'contracts': False}
        self.profile.save(update_fields=['notification_prefs'])
        result = emit_notification(self.account, type='new_contract', title='T', body='B')
        self.assertEqual(result, (0, 0))
        self.assertEqual(Notification.objects.filter(recipient=self.account).count(), 0)
        mock_push.assert_not_called()
        mock_ws.assert_not_called()

    def test_serialize_shape(self):
        n = Notification.objects.create(
            recipient=self.account, type='new_booking', category='rental',
            title='T', body='B', url='/x', data={'k': 1})
        s = _serialize(n)
        self.assertEqual(s['object_type'], 'notification')
        self.assertEqual(s['id'], n.id)
        self.assertEqual(s['type'], 'new_booking')
        self.assertEqual(s['data'], {'k': 1})
        self.assertIs(s['read'], False)
        self.assertIsNotNone(s['created_at'])


# ===========================================================================
# Feed API (list / unread-count / mark-read / mark-all-read)
# ===========================================================================

class NotificationFeedAPITest(TestCase):
    def setUp(self):
        self.instance = _create_instance()
        self.alice = _create_account(self.instance, 'alice')
        self.alice_p = _create_profile(self.alice, self.instance)
        self.bob = _create_account(self.instance, 'bob')
        self.bob_p = _create_profile(self.bob, self.instance)
        self.n1 = Notification.objects.create(recipient=self.alice, type='new_contract', category='contracts', title='c1')
        self.n2 = Notification.objects.create(recipient=self.alice, type='new_poll', category='governance', title='p1')
        self.n3 = Notification.objects.create(recipient=self.alice, type='new_booking', category='rental', title='b1')
        Notification.objects.create(recipient=self.bob, type='new_contract', category='contracts', title='bobs')

    def test_feed_newest_first_and_scoped(self):
        res = napi.notification_feed(_req(self.alice_p))
        ids = [r['id'] for r in res]
        # ordered by -id (ULID is time-sortable); robust to same-ms creation
        self.assertEqual(ids, sorted([self.n1.id, self.n2.id, self.n3.id], reverse=True))
        self.assertNotIn('bobs', [r['title'] for r in res])

    def test_feed_category_filter(self):
        res = napi.notification_feed(_req(self.alice_p), category='rental')
        self.assertEqual([r['id'] for r in res], [self.n3.id])

    def test_feed_cursor_pagination(self):
        full = [r['id'] for r in napi.notification_feed(_req(self.alice_p))]
        page1 = napi.notification_feed(_req(self.alice_p), limit=1)
        self.assertEqual(page1[0]['id'], full[0])
        page2 = napi.notification_feed(_req(self.alice_p), limit=1, before=page1[0]['id'])
        self.assertEqual(page2[0]['id'], full[1])

    def test_unread_count_scoped(self):
        self.assertEqual(napi.unread_count(_req(self.alice_p))['count'], 3)
        self.assertEqual(napi.unread_count(_req(self.bob_p))['count'], 1)

    def test_mark_read_subset(self):
        napi.mark_read(_req(self.alice_p, post=True), napi.MarkReadRequest(ids=[self.n1.id]))
        self.assertEqual(napi.unread_count(_req(self.alice_p))['count'], 2)
        self.n1.refresh_from_db()
        self.assertIsNotNone(self.n1.read_at)

    def test_mark_read_cannot_touch_other_users(self):
        bobs = Notification.objects.get(recipient=self.bob)
        result = napi.mark_read(_req(self.alice_p, post=True), napi.MarkReadRequest(ids=[bobs.id]))
        self.assertEqual(result['updated'], 0)
        bobs.refresh_from_db()
        self.assertIsNone(bobs.read_at)

    def test_mark_all_read_scoped(self):
        napi.mark_all_read(_req(self.alice_p, post=True))
        self.assertEqual(napi.unread_count(_req(self.alice_p))['count'], 0)
        self.assertEqual(napi.unread_count(_req(self.bob_p))['count'], 1)  # bob untouched


# ===========================================================================
# Activity log (the actor's own actions) + merged feed
# ===========================================================================

class RecordActivityTest(TestCase):
    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance)
        self.profile = _create_profile(self.account, self.instance)

    @patch('parahub.services.ws_publish.ws_publish')
    def test_creates_row_and_pushes(self, mock_ws):
        # GenericFK points at a real object — reuse the profile as a stand-in.
        # WS fires via transaction.on_commit → capture it (TestCase rolls back).
        with self.captureOnCommitCallbacks(execute=True):
            act = record_activity(
                self.account, verb='voted', obj=self.profile, category='governance',
                title='You voted', body='Poll X', url='/governance/polls/x',
                data={'poll_id': 'x'},
            )
        self.assertEqual(act.actor_id, self.account.id)
        self.assertEqual(act.verb, 'voted')
        self.assertEqual(act.object_id, self.profile.id)
        self.assertIsNotNone(act.content_type)
        # on_commit fires the WS push to the actor's personal channel
        mock_ws.assert_called_once()
        channel, payload = mock_ws.call_args.args
        self.assertEqual(channel, f'user:{self.account.id}')
        self.assertEqual(payload['type'], 'activity.new')
        self.assertEqual(payload['activity']['id'], act.id)

    @patch('parahub.services.ws_publish.ws_publish')
    def test_publish_false_skips_ws(self, mock_ws):
        record_activity(
            self.account, verb='voted', obj=self.profile,
            title='t', body='b', publish=False,
        )
        mock_ws.assert_not_called()

    def test_serialize_activity_shape(self):
        act = Activity.objects.create(
            actor=self.account, verb='listed_item', category='market',
            title='T', body='B', url='/market/x', data={'k': 1})
        s = _serialize_activity(act)
        self.assertEqual(s['object_type'], 'activity')
        self.assertEqual(s['id'], act.id)
        self.assertEqual(s['type'], 'listed_item')
        self.assertIs(s['read'], True)  # own actions are never unread
        self.assertEqual(s['data'], {'k': 1})


class MergedFeedTest(TestCase):
    """The /feed endpoint merges Notification (incoming) + Activity (own)."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice = _create_account(self.instance, 'alice')
        self.alice_p = _create_profile(self.alice, self.instance)
        self.bob = _create_account(self.instance, 'bob')
        self.bob_p = _create_profile(self.bob, self.instance)
        # Interleave so ULID ordering mixes the two streams.
        self.n1 = Notification.objects.create(recipient=self.alice, type='new_contract', category='contracts', title='n1')
        self.a1 = Activity.objects.create(actor=self.alice, verb='voted', category='governance', title='a1')
        self.n2 = Notification.objects.create(recipient=self.alice, type='new_poll', category='governance', title='n2')
        self.a2 = Activity.objects.create(actor=self.alice, verb='verified', category='social', title='a2')
        # Other user's rows must never leak in.
        Notification.objects.create(recipient=self.bob, type='new_contract', category='contracts', title='bob_n')
        Activity.objects.create(actor=self.bob, verb='voted', category='governance', title='bob_a')

    def test_all_merges_both_streams_newest_first(self):
        res = napi.notification_feed(_req(self.alice_p), source='all')
        ids = [r['id'] for r in res]
        expected = sorted([self.n1.id, self.a1.id, self.n2.id, self.a2.id], reverse=True)
        self.assertEqual(ids, expected)
        types = {r['object_type'] for r in res}
        self.assertEqual(types, {'notification', 'activity'})
        titles = [r['title'] for r in res]
        self.assertNotIn('bob_n', titles)
        self.assertNotIn('bob_a', titles)

    def test_mine_returns_only_activity(self):
        res = napi.notification_feed(_req(self.alice_p), source='mine')
        self.assertEqual({r['object_type'] for r in res}, {'activity'})
        self.assertEqual([r['id'] for r in res], sorted([self.a1.id, self.a2.id], reverse=True))

    def test_incoming_returns_notifications_read_and_unread(self):
        # 'incoming' = things others did to you, regardless of read state, never activity.
        self.n1.read_at = timezone.now()
        self.n1.save(update_fields=['read_at'])
        res = napi.notification_feed(_req(self.alice_p), source='incoming')
        ids = [r['id'] for r in res]
        self.assertEqual(ids, sorted([self.n1.id, self.n2.id], reverse=True))  # both, incl. read
        self.assertEqual({r['object_type'] for r in res}, {'notification'})

    def test_unread_keeps_only_unread_incoming(self):
        # unread=True drops read notifications AND all activity (never unread).
        self.n1.read_at = timezone.now()
        self.n1.save(update_fields=['read_at'])
        res = napi.notification_feed(_req(self.alice_p), source='all', unread=True)
        ids = [r['id'] for r in res]
        self.assertEqual(ids, [self.n2.id])  # only the still-unread notification
        self.assertEqual({r['object_type'] for r in res}, {'notification'})

    def test_mine_with_unread_is_empty(self):
        # Your own actions are never unread → mine + unread = nothing.
        res = napi.notification_feed(_req(self.alice_p), source='mine', unread=True)
        self.assertEqual(res, [])

    def test_merged_cursor_pagination_spans_both(self):
        full = [r['id'] for r in napi.notification_feed(_req(self.alice_p), source='all')]
        page1 = napi.notification_feed(_req(self.alice_p), source='all', limit=2)
        self.assertEqual([r['id'] for r in page1], full[:2])
        page2 = napi.notification_feed(_req(self.alice_p), source='all', limit=2, before=page1[-1]['id'])
        self.assertEqual([r['id'] for r in page2], full[2:4])


class ActivitySignalTest(TestCase):
    """post_save on a first-class action writes an Activity row (no scattered emits)."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance)
        self.profile = _create_profile(self.account, self.instance, preferred_language='en')

    def test_listing_an_item_logs_activity(self):
        from market.models import Item
        item = Item.objects.create(owner=self.profile, title='Bike', type=Item.ItemType.CREDIT)
        act = Activity.objects.filter(actor=self.account, verb='listed_item').first()
        self.assertIsNotNone(act)
        self.assertEqual(act.body, 'Bike')
        self.assertEqual(act.object_id, item.id)
        self.assertEqual(act.url, f'/market/{item.id}')
        self.assertEqual(act.title, 'You posted a listing')  # actor lang = en
