"""
Sitemap feed tests for member-created content (core/endpoints/sitemap.py).

The feeds decide what search engines are told exists, so the interesting cases
are all exclusions: a wrong include publishes a private or synthetic page, and a
wrong exclude silently costs a real page its discovery path.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.endpoints.sitemap import (
    establishment_sitemap_urls, event_sitemap_urls, item_sitemap_urls,
)
from core.models import Instance, ObjectPhoto
from geo.models import Establishment, EstablishmentMembership, Event
from identity.models import Account, Profile
from market.models import Item


def _locs(feed):
    return {row['loc'] for row in feed}


class SitemapFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test Instance', public_key='k')

        def profile(username, **account_kwargs):
            account = Account.objects.create_user(
                username=username, email=f'{username}@test.parahub.io',
                password='x', instance=cls.instance, **account_kwargs)
            return Profile.objects.create(
                account=account, instance=cls.instance, local_name=username,
                display_name=username.title(), is_primary=True,
                profile_type=Profile.ProfileType.PERSONAL)

        cls.real = profile('smreal')
        cls.robot = profile('smbot', is_bot=True)
        cls.tester = profile('smtest', is_test=True)

    # ---- items -------------------------------------------------------------

    def _item(self, owner, **kwargs):
        defaults = dict(owner=owner, title='Probe', type='CREDIT',
                        pricing_options=[{'type': 'sale', 'amount': '5.00', 'currency': 'EUR'}])
        return Item.objects.create(**{**defaults, **kwargs})

    def test_item_feed_lists_public_active_listings_only(self):
        wanted = self._item(self.real)
        self._item(self.real, is_active=False)
        self._item(self.real, visibility=Item.Visibility.REGISTERED)
        self._item(self.real, attributes={'__demo_seed': True})
        self._item(self.real, attributes={'demo': True})
        self._item(self.robot)
        self._item(self.tester)

        self.assertEqual(_locs(item_sitemap_urls(None)), {f'/market/{wanted.id}'})

    def test_item_feed_carries_lastmod(self):
        item = self._item(self.real)
        row = next(r for r in item_sitemap_urls(None) if r['loc'].endswith(item.id))
        self.assertEqual(row['lastmod'], item.updated_at.isoformat())

    # ---- events ------------------------------------------------------------

    def _event(self, organizer, starts_in_days, **kwargs):
        starts = timezone.now() + timedelta(days=starts_in_days)
        defaults = dict(organizer=organizer, title='Probe', description='d',
                        starts_at=starts, ends_at=starts + timedelta(hours=2),
                        status=Event.Status.PUBLISHED)
        return Event.objects.create(**{**defaults, **kwargs})

    def test_event_feed_lists_published_events_still_ahead(self):
        wanted = self._event(self.real, 7)
        open_ended = self._event(self.real, 3, ends_at=None)
        self._event(self.real, -7)                                    # already over
        self._event(self.real, -1, ends_at=None)                      # started yesterday
        self._event(self.real, 7, status=Event.Status.DRAFT)
        self._event(self.real, 7, status=Event.Status.CANCELLED)
        self._event(self.real, 7, attributes={'__demo_seed': True})
        self._event(self.robot, 7)
        self._event(self.tester, 7)

        self.assertEqual(
            _locs(event_sitemap_urls(None)),
            {f'/events/{wanted.id}', f'/events/{open_ended.id}'},
        )

    def test_event_that_started_but_has_not_ended_stays_listed(self):
        running = self._event(self.real, 0)
        running.starts_at = timezone.now() - timedelta(hours=1)
        running.save(update_fields=['starts_at'])
        self.assertIn(f'/events/{running.id}', _locs(event_sitemap_urls(None)))

    # ---- establishments ----------------------------------------------------

    def _org(self, name, owner=None, **kwargs):
        return Establishment.objects.create(name=name, owner=owner, **kwargs)

    def test_bare_directory_entry_is_not_advertised(self):
        self._org('Bare Stub')
        self.assertEqual(_locs(establishment_sitemap_urls(None)), set())

    def test_each_content_signal_earns_an_entry(self):
        described = self._org('Described', description='We bake bread.')
        verified = self._org('Verified', is_verified=True)
        pictured = self._org('Pictured')
        ObjectPhoto.objects.create(object_id=pictured.id, uploaded_by=self.real,
                                   image='photos/x.jpg')
        legacy_photo = self._org('Legacy Photo', photos=['https://example.org/a.jpg'])
        staffed = self._org('Staffed')
        EstablishmentMembership.objects.create(profile=self.real, establishment=staffed)
        selling = self._org('Selling')
        self._item(self.real, establishment=selling)

        self.assertEqual(
            _locs(establishment_sitemap_urls(None)),
            {f'/org/{o.slug}' for o in
             (described, verified, pictured, legacy_photo, staffed, selling)},
        )

    def test_inactive_demo_and_synthetic_owners_are_left_out(self):
        self._org('Closed', description='d', is_active=False)
        self._org('Demo', description='d', attributes={'__demo_seed': True})
        self._org('Demo Flag', description='d', attributes={'demo': True})
        self._org('Bot Owned', description='d', owner=self.robot)
        self._org('Test Owned', description='d', owner=self.tester)
        self.assertEqual(_locs(establishment_sitemap_urls(None)), set())

    def test_ownerless_establishment_still_qualifies(self):
        """The whole seeded directory has no owner — a NULL FK must not read as
        'synthetic author' or the feed would only ever hold claimed places."""
        org = self._org('Unclaimed', description='A real place nobody claimed yet.')
        self.assertEqual(_locs(establishment_sitemap_urls(None)), {f'/org/{org.slug}'})

    def test_multiple_signals_yield_one_entry(self):
        org = self._org('Popular', description='d', is_verified=True)
        for p in (self.real, self.robot):
            EstablishmentMembership.objects.create(profile=p, establishment=org)
        self._item(self.real, establishment=org)
        self._item(self.real, establishment=org)

        feed = establishment_sitemap_urls(None)
        self.assertEqual([r['loc'] for r in feed], [f'/org/{org.slug}'])
