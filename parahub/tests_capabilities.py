"""
Tests for the platform capability layer (`parahub/capabilities.py`) and the
surfaces that ask it.

Invariants:
- a capability is one Django group, so granting it is a group membership
- `is_staff` still passes every check (the superuser override the design keeps)
- an anonymous or deactivated login holds nothing
- a capability opens exactly its own surface and no other
"""

from django.contrib.auth.models import Group
from django.test import TestCase, SimpleTestCase, RequestFactory
from ninja.errors import HttpError

from parahub.capabilities import (
    PLATFORM_CAPABILITIES, has_platform_capability, platform_capabilities,
    require_platform_capability,
)
from geo.tests import _create_account, _create_instance, _create_profile, _make_auth_request


class CapabilityMapTest(SimpleTestCase):
    def test_every_capability_names_a_group(self):
        for capability, group in PLATFORM_CAPABILITIES.items():
            with self.subTest(capability=capability):
                self.assertTrue(group and isinstance(group, str))
        self.assertEqual(len(set(PLATFORM_CAPABILITIES.values())), len(PLATFORM_CAPABILITIES))

    def test_unknown_capability_raises(self):
        """A typo is a programming error, not a silent denial."""
        with self.assertRaises(ValueError):
            has_platform_capability(None, 'infra.teleport')


class PlatformCapabilityTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)

    def _grant(self, group_name):
        group, _ = Group.objects.get_or_create(name=group_name)
        self.account.groups.add(group)
        self.account.refresh_from_db()

    def test_a_plain_login_holds_nothing(self):
        self.assertEqual(platform_capabilities(self.account), set())

    def test_a_group_grants_exactly_its_own_surface(self):
        self._grant('urban_validators')
        self.assertTrue(has_platform_capability(self.account, 'urban.validate'))
        self.assertFalse(has_platform_capability(self.account, 'federation.admin'))
        self.assertFalse(has_platform_capability(self.account, 'moderation.review'))
        self.assertFalse(has_platform_capability(self.account, 'infra.operate'))

    def test_staff_still_holds_everything(self):
        """The override the design keeps — nothing narrows for staff."""
        self.account.is_staff = True
        self.account.save(update_fields=['is_staff'])
        self.assertEqual(platform_capabilities(self.account), set(PLATFORM_CAPABILITIES))

    def test_a_deactivated_login_holds_nothing(self):
        self._grant('federation_admins')
        self.account.is_active = False
        self.account.save(update_fields=['is_active'])
        self.assertEqual(platform_capabilities(self.account), set())

    def test_anonymous_holds_nothing(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(platform_capabilities(None), set())
        self.assertEqual(platform_capabilities(AnonymousUser()), set())

    def test_require_returns_the_account_it_attributes_to(self):
        self._grant('federation_admins')
        request = _make_auth_request(self.factory, self.account, self.profile)
        self.assertEqual(
            require_platform_capability(request, 'federation.admin'), self.account)

    def test_require_denies_with_403(self):
        request = _make_auth_request(self.factory, self.account, self.profile)
        with self.assertRaises(HttpError) as ctx:
            require_platform_capability(request, 'federation.admin')
        self.assertEqual(ctx.exception.status_code, 403)


class SurfaceGateTest(TestCase):
    """One capability opens one surface — the endpoints, not just the helper."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)

    def _grant(self, group_name):
        group, _ = Group.objects.get_or_create(name=group_name)
        self.account.groups.add(group)
        self.account.refresh_from_db()

    def _request(self):
        return _make_auth_request(self.factory, self.account, self.profile)

    def test_wot_graph_needs_moderation(self):
        from parahub.endpoints.wot import get_wot_graph

        with self.assertRaises(HttpError) as ctx:
            get_wot_graph(self._request())
        self.assertEqual(ctx.exception.status_code, 403)

        self._grant('moderators')
        self.assertEqual(get_wot_graph(self._request()).total_profiles, 1)

    def test_moderation_does_not_open_the_federation_registry(self):
        from parahub.endpoints.federation import sync_status

        self._grant('moderators')
        with self.assertRaises(HttpError) as ctx:
            sync_status(self._request())
        self.assertEqual(ctx.exception.status_code, 403)

    def test_urban_dossie_reads_the_same_map(self):
        from geo.endpoints.urban import _validator_account

        request = self._request()
        request.auth = self.profile
        self.assertIsNone(_validator_account(request))

        self._grant('urban_validators')
        request = self._request()
        request.auth = self.profile
        self.assertEqual(_validator_account(request), self.account)


class GrantScreenTest(TestCase):
    """
    `parahub/endpoints/platform.py` — handing a capability out.

    The invariant worth a test: holding capabilities never includes handing them
    out, and `is_staff` (which holds all four) does not either. Only the node's
    superuser appoints.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.owner = _create_account(self.instance, 'owner', is_staff=True, is_superuser=True)
        self.owner_profile = _create_profile(self.owner, self.instance)
        self.target = _create_account(self.instance, 'liliana')
        self.target_profile = _create_profile(self.target, self.instance)
        self.target_profile.display_name = 'Liliana Costa'
        self.target_profile.save(update_fields=['display_name'])

    def _as(self, account, profile, method='get', data=None):
        return _make_auth_request(self.factory, account, profile, method=method, data=data)

    def _grant(self, capability='moderation.review', username=None):
        from parahub.endpoints.platform import GrantIn, grant_capability
        return grant_capability(
            self._as(self.owner, self.owner_profile, method='post'), capability,
            GrantIn(username=username or self.target.username))

    def test_a_plain_login_cannot_see_the_screen(self):
        from parahub.endpoints.platform import list_capabilities

        with self.assertRaises(HttpError) as ctx:
            list_capabilities(self._as(self.target, self.target_profile))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_staff_cannot_grant_what_staff_already_holds(self):
        """Otherwise the whole set is self-propagating."""
        from parahub.endpoints.platform import list_capabilities

        staff = _create_account(self.instance, 'kemys', is_staff=True)
        staff_profile = _create_profile(staff, self.instance)
        self.assertEqual(platform_capabilities(staff), set(PLATFORM_CAPABILITIES))

        with self.assertRaises(HttpError) as ctx:
            list_capabilities(self._as(staff, staff_profile))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_grant_puts_the_login_in_the_group(self):
        status, holder = self._grant()
        self.assertEqual(status, 200)
        self.assertEqual(holder.username, 'liliana')
        self.assertFalse(holder.implicit)

        self.target.refresh_from_db()
        self.assertEqual(platform_capabilities(self.target), {'moderation.review'})

    def test_grant_is_idempotent(self):
        self._grant()
        self._grant()
        self.assertEqual(self.target.groups.filter(name='moderators').count(), 1)

    def test_revoke_takes_it_back(self):
        from parahub.endpoints.platform import revoke_capability

        self._grant()
        status, body = revoke_capability(
            self._as(self.owner, self.owner_profile, method='delete'),
            'moderation.review', 'liliana')
        self.assertEqual(status, 200)
        self.assertFalse(body['still_holds'])

        self.target.refresh_from_db()
        self.assertEqual(platform_capabilities(self.target), set())

    def test_revoking_from_staff_says_they_still_hold_it(self):
        """A revoke that changed nothing must not read as a revoke that worked."""
        from parahub.endpoints.platform import revoke_capability

        self.target.is_staff = True
        self.target.save(update_fields=['is_staff'])
        self._grant()
        _, body = revoke_capability(
            self._as(self.owner, self.owner_profile, method='delete'),
            'moderation.review', 'liliana')
        self.assertTrue(body['still_holds'])

    def test_unknown_capability_is_404(self):
        with self.assertRaises(HttpError) as ctx:
            self._grant(capability='infra.teleport')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_unknown_login_is_404(self):
        with self.assertRaises(HttpError) as ctx:
            self._grant(username='nobody')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_listing_answers_who_can_do_this_today(self):
        """Staff hold everything by override, so the screen shows them too."""
        from parahub.endpoints.platform import list_capabilities

        self._grant()
        rows = {c.key: c for c in list_capabilities(self._as(self.owner, self.owner_profile))}
        self.assertEqual(set(rows), set(PLATFORM_CAPABILITIES))

        moderation = {h.username: h for h in rows['moderation.review'].holders}
        self.assertFalse(moderation['liliana'].implicit)
        self.assertTrue(moderation['owner'].implicit)
        # The owner is staff, so they appear under every capability; liliana only
        # under the one she was given.
        self.assertNotIn('liliana', {h.username for h in rows['infra.operate'].holders})

    def test_account_search_finds_a_login_by_the_name_on_its_profile(self):
        from parahub.endpoints.platform import search_accounts

        request = self._as(self.owner, self.owner_profile)
        self.assertEqual([a.username for a in search_accounts(request, q='Liliana')], ['liliana'])
        self.assertEqual(search_accounts(request, q='L'), [])


class SessionPayloadTest(TestCase):
    """The frontend gates on what the session says."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)

    def _session(self):
        from parahub.endpoints.auth import check_session
        request = self.factory.get('/fake/')
        request.user = self.account
        request.session = {}
        return check_session(request)

    def test_capabilities_travel_with_the_session(self):
        self.assertEqual(self._session()['user']['capabilities'], [])

        group, _ = Group.objects.get_or_create(name='infra_operators')
        self.account.groups.add(group)
        self.account.refresh_from_db()
        self.assertEqual(self._session()['user']['capabilities'], ['infra.operate'])

    def test_staff_session_lists_all_of_them(self):
        self.account.is_staff = True
        self.account.save(update_fields=['is_staff'])
        self.assertEqual(
            set(self._session()['user']['capabilities']), set(PLATFORM_CAPABILITIES))
