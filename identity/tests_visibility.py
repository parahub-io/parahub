"""Guard tests for the platform-wide synthetic-content visibility policy.

identity.visibility is the single source of truth: test/bot-authored content
is invisible to real users; only staff and test-account viewers are exempt
(bot viewers are NOT). These tests pin both the helper semantics and — via
the surface sweep — the actual list endpoints, so a surface that forgets the
filter (the civic-ideas incident) or a helper regression fails loudly here.
"""

import orjson
from django.contrib.auth.models import AnonymousUser
from django.http import Http404, HttpResponse
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone
from datetime import timedelta

from core.models import Instance
from geo.models import Event
from identity.models import Account, Profile
from identity.visibility import (
    account_is_synthetic, account_sees_test_content, exclude_test_authors,
    test_authors_sql, viewer_account, viewer_sees_test_content)
from market.models import Item
from parahub.endpoints.dashboard import get_platform_stats
from parahub.endpoints.items import list_items
from parahub.endpoints.profiles.core import get_public_profile, search_profiles
from taxonomy.models import Category


class VisibilityFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test Instance', public_key='test-key')

        def make_pair(username, **flags):
            account = Account.objects.create_user(
                username=username, email=f'{username}@test.parahub.io',
                password='x', instance=cls.instance, **flags)
            profile = Profile.objects.create(
                account=account, instance=cls.instance, local_name=username,
                display_name=username.title(), is_primary=True,
                is_publicly_linked=True,
                profile_type=Profile.ProfileType.PERSONAL)
            return account, profile

        cls.real_account, cls.real_profile = make_pair('visreal')
        cls.staff_account, cls.staff_profile = make_pair('visstaff', is_staff=True)
        cls.test_account, cls.test_profile = make_pair('vistest', is_test=True)
        cls.bot_account, cls.bot_profile = make_pair('visbot', is_bot=True)

        cls.category = Category.objects.create(name='Vis Cat', slug='vis-cat')

        def make_item(owner, title):
            return Item.objects.create(
                owner=owner, title=title, type='CREDIT', category=cls.category,
                pricing_options=[{'type': 'sale', 'amount': '5.00',
                                  'currency': 'EUR', 'unit': 'pcs', 'note': ''}])

        cls.real_item = make_item(cls.real_profile, 'VisProbe real thing')
        cls.test_item = make_item(cls.test_profile, 'VisProbe test junk')
        cls.bot_item = make_item(cls.bot_profile, 'VisProbe bot junk')

        cls.factory = RequestFactory()

    def _request(self, viewer_profile=None, path='/api/v1/items/'):
        request = self.factory.get(path)
        request.user = AnonymousUser()
        if viewer_profile is not None:
            request.user = viewer_profile.account
            request.auth = viewer_profile
            request.auth_profile = viewer_profile
        return request


class ViewerResolutionTest(VisibilityFixtureMixin, TestCase):
    def test_anonymous(self):
        request = self.factory.get('/')
        self.assertIsNone(viewer_account(request))
        self.assertFalse(viewer_sees_test_content(request))
        request.user = AnonymousUser()
        self.assertIsNone(viewer_account(request))
        self.assertFalse(viewer_sees_test_content(request))

    def test_session_user_fallback(self):
        request = self.factory.get('/')
        request.user = self.staff_account
        self.assertEqual(viewer_account(request), self.staff_account)
        self.assertTrue(viewer_sees_test_content(request))

    def test_jwt_only_client_resolves_via_auth_profile(self):
        # A JWT-only (mobile) client has an anonymous request.user but a
        # populated auth_profile — the viewer must still resolve.
        request = self.factory.get('/')
        request.user = AnonymousUser()
        request.auth_profile = self.test_profile
        self.assertEqual(viewer_account(request), self.test_account)
        self.assertTrue(viewer_sees_test_content(request))

    def test_exemption_matrix(self):
        for profile, exempt in [(self.real_profile, False),
                                (self.staff_profile, True),
                                (self.test_profile, True),
                                (self.bot_profile, False)]:
            request = self._request(profile)
            self.assertEqual(
                viewer_sees_test_content(request), exempt,
                f'{profile.local_name}: expected exempt={exempt}')

    def test_account_is_synthetic(self):
        self.assertFalse(account_is_synthetic(None))
        self.assertFalse(account_is_synthetic(self.real_account))
        self.assertFalse(account_is_synthetic(self.staff_account))
        self.assertTrue(account_is_synthetic(self.test_account))
        self.assertTrue(account_is_synthetic(self.bot_account))


class ExcludeTestAuthorsTest(VisibilityFixtureMixin, TestCase):
    def _visible_items(self, viewer_profile=None, request=Ellipsis):
        if request is Ellipsis:
            request = self._request(viewer_profile) if viewer_profile else None
        qs = exclude_test_authors(Item.objects.all(), request, field='owner')
        return set(qs.values_list('id', flat=True))

    def test_real_viewer_hides_synthetic(self):
        self.assertEqual(self._visible_items(self.real_profile), {self.real_item.id})

    def test_bot_viewer_not_exempt(self):
        self.assertEqual(self._visible_items(self.bot_profile), {self.real_item.id})

    def test_staff_and_test_viewers_see_everything(self):
        everything = {self.real_item.id, self.test_item.id, self.bot_item.id}
        self.assertEqual(self._visible_items(self.staff_profile), everything)
        self.assertEqual(self._visible_items(self.test_profile), everything)

    def test_no_request_always_excludes(self):
        self.assertEqual(self._visible_items(request=None), {self.real_item.id})

    def test_profile_queryset_field_empty(self):
        qs = exclude_test_authors(
            Profile.objects.all(), self._request(self.real_profile), field='')
        names = set(qs.values_list('local_name', flat=True))
        self.assertIn('visreal', names)
        self.assertIn('visstaff', names)
        self.assertNotIn('vistest', names)
        self.assertNotIn('visbot', names)

    def test_sql_twin(self):
        pred, params = test_authors_sql(self._request(self.staff_profile), alias='a')
        self.assertEqual((pred, params), ('TRUE', []))
        pred, params = test_authors_sql(self._request(self.real_profile), alias='x')
        self.assertEqual(params, [])
        self.assertIn('x.is_test = FALSE', pred)
        self.assertIn('x.is_bot = FALSE', pred)


class SurfaceSweepTest(VisibilityFixtureMixin, TestCase):
    """End-to-end: real list surfaces must not leak synthetic content."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        soon = timezone.now() + timedelta(days=7)
        cls.real_event = Event.objects.create(
            organizer=cls.real_profile, title='VisProbe real meetup',
            description='x', starts_at=soon, status=Event.Status.PUBLISHED)
        cls.test_event = Event.objects.create(
            organizer=cls.test_profile, title='VisProbe test meetup',
            description='x', starts_at=soon, status=Event.Status.PUBLISHED)

    def _items_ids(self, response):
        payload = (orjson.loads(response.content)
                   if isinstance(response, HttpResponse) else response)
        return {i['id'] for i in payload['items']}

    def test_items_list_raw_path_anonymous(self):
        response = list_items(self._request())
        self.assertIsInstance(response, HttpResponse, 'raw path did not run')
        ids = self._items_ids(response)
        self.assertIn(self.real_item.id, ids)
        self.assertNotIn(self.test_item.id, ids)
        self.assertNotIn(self.bot_item.id, ids)

    def test_items_list_orm_path_real_viewer(self):
        response = list_items(self._request(self.real_profile), q='VisProbe')
        self.assertIsInstance(response, dict, 'ORM path did not run')
        ids = {i.id for i in response['items']}
        self.assertIn(self.real_item.id, ids)
        self.assertNotIn(self.test_item.id, ids)
        self.assertNotIn(self.bot_item.id, ids)

    def test_items_list_staff_sees_synthetic(self):
        response = list_items(self._request(self.staff_profile))
        ids = self._items_ids(response)
        self.assertEqual(
            {self.real_item.id, self.test_item.id, self.bot_item.id} - ids, set())

    def test_events_list_http_anonymous_and_staff(self):
        client = Client()
        payload = client.get('/api/v1/geo/events/').json()
        titles = {e['title'] for e in payload['items']}
        self.assertIn('VisProbe real meetup', titles)
        self.assertNotIn('VisProbe test meetup', titles)

        client.force_login(self.staff_account)
        payload = client.get('/api/v1/geo/events/').json()
        titles = {e['title'] for e in payload['items']}
        self.assertIn('VisProbe test meetup', titles)

    def test_profiles_search_real_vs_test_viewer(self):
        def names_for(profile, **kwargs):
            response = search_profiles(
                self._request(profile, path='/api/v1/profiles/search/'), **kwargs)
            return {p.hna.split('@')[0] for p in response['items']}

        names = names_for(self.real_profile)
        self.assertIn('visreal', names)
        self.assertNotIn('vistest', names)
        self.assertNotIn('visbot', names)

        names = names_for(self.test_profile)
        self.assertIn('vistest', names)

        # exclude_test=True lets an exempt viewer opt out of synthetic profiles
        # (the directory browse surface does; the by-name pickers do not)
        for viewer in (self.test_profile, self.staff_profile, self.real_profile):
            names = names_for(viewer, exclude_test=True)
            self.assertIn('visreal', names)
            self.assertNotIn('vistest', names)
            self.assertNotIn('visbot', names)

        # ...and the staff viewer keeps seeing them without it (picker path)
        self.assertIn('vistest', names_for(self.staff_profile))

    def _profile_page(self, handle, viewer_profile=None):
        """Returns 'kind:<x>' for the stripped stub, 404, or the full response."""
        request = self._request(viewer_profile, path=f'/api/v1/profiles/{handle}/')
        request.limited = False
        try:
            result = get_public_profile(request, handle)
        except Http404:
            return '404'
        return f'kind:{result.account_kind}' if result.account_kind else result

    def test_public_profile_page_strips_synthetic_for_strangers(self):
        """A seeded profile must not read as a member to anyone the exemption
        does not cover: they get the held-handle stub, never reputation or WoT.
        404 would be a lie — the signup form calls the same handle taken."""
        for handle, kind in (('vistest', 'test'), ('visbot', 'bot')):
            self.assertEqual(self._profile_page(handle), f'kind:{kind}', f'{handle}: anonymous')
            self.assertEqual(self._profile_page(handle, self.real_profile), f'kind:{kind}',
                             f'{handle}: member')
            for viewer in (self.staff_profile, self.test_profile):
                self.assertIsNone(self._profile_page(handle, viewer).account_kind,
                                  f'{handle}: exempt viewer gets the real profile')

        # A bot viewer is not exempt, but still reaches its OWN profile
        self.assertIsNone(self._profile_page('visbot', self.bot_profile).account_kind)
        self.assertEqual(self._profile_page('vistest', self.bot_profile), 'kind:test')

        # A real profile stays fully public, anonymous included
        self.assertIsNone(self._profile_page('visreal').account_kind)

    def test_held_handle_stub_carries_no_member_signal(self):
        """The stub must not leak the seeded identity it stands for."""
        self.test_profile.is_verified_wot = True
        self.test_profile.reputation_score = 92
        self.test_profile.bio = 'seeded bio'
        self.test_profile.save()

        stub = get_public_profile(
            self._request(path='/api/v1/profiles/vistest/'), 'vistest')

        self.assertEqual(stub.account_kind, 'test')
        self.assertEqual(stub.hna, f'vistest@{self.instance.domain}')
        self.assertFalse(stub.is_verified_wot)
        self.assertEqual(stub.reputation_score, 0)
        self.assertEqual(stub.display_name, '')
        self.assertEqual(stub.bio, '')
        self.assertEqual(stub.verifications_received_count, 0)
        # account_id would hand back the by-account resolver, which is not gated
        self.assertEqual(stub.account_id, '')

    def test_reserved_handle_says_so_but_private_profiles_stay_hidden(self):
        # Reserved with nothing behind it — still held, so not "not found"
        self.assertEqual(self._profile_page('support'), 'kind:reserved')

        # A member's own hidden profile is not the platform's to announce
        hidden = Profile.objects.create(
            account=self.real_account, instance=self.instance,
            local_name='visreal-alt', display_name='Alt', is_primary=False,
            is_publicly_linked=False,
            profile_type=Profile.ProfileType.PSEUDONYMOUS)
        self.assertEqual(self._profile_page('visreal-alt'), '404')
        hidden.delete()

        # An unknown handle is still an honest 404
        self.assertEqual(self._profile_page('nobody-here-at-all'), '404')

        # Handles resolve case-insensitively, so /@Visreal is not a false 404
        self.assertIsNone(self._profile_page('VISREAL').account_kind)

    def test_platform_stats_count_only_the_real_community(self):
        """The public counters on /about must not be inflated by seeds."""
        stats = get_platform_stats(self._request(path='/api/v1/dashboard/stats'))

        real_ids = {self.real_profile.id, self.staff_profile.id}
        self.assertEqual(stats['total_profiles'], len(real_ids))

        self.test_profile.is_verified_wot = True
        self.test_profile.save(update_fields=['is_verified_wot'])
        self.real_profile.is_verified_wot = True
        self.real_profile.save(update_fields=['is_verified_wot'])

        stats = get_platform_stats(self._request(path='/api/v1/dashboard/stats'))
        self.assertEqual(stats['verified_users'], 1)
