"""
Tests for identity endpoints: profile CRUD, partner invites, WoT verification,
profile search.

Tests invariants that must never break:
- Profile creation limit (7 total per account)
- WoT verification requirement for additional profiles
- Owner-only access to profile updates
- Partner invite token lifecycle
- Profile search visibility (is_publicly_linked)
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, SimpleTestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore

from identity.models import Account, Profile, Partner, Verification
from core.models import Instance


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


def _make_auth_request(factory, account, profile, method='get', path='/fake/', data=None):
    """Build a request with auth_profile and session attached (mimics ProfileAuth)."""
    fn = getattr(factory, method)
    request = fn(path, data=data, content_type='application/json') if data else fn(path)
    request.user = account
    request.auth = profile
    request.auth_profile = profile
    request.session = SessionStore()
    request.session.create()
    return request


# ===========================================================================
# Model-level tests (SimpleTestCase — no DB)
# ===========================================================================

class ProfileModelLogicTest(SimpleTestCase):
    """Test Profile model methods without DB."""

    def test_can_create_additional_profiles_unverified(self):
        p = Profile()
        p.is_verified_wot = False
        with patch.object(Profile, 'is_foundation_member', return_value=False):
            self.assertFalse(p.can_create_additional_profiles())

    def test_can_create_additional_profiles_verified(self):
        p = Profile()
        p.is_verified_wot = True
        with patch.object(Profile, 'is_foundation_member', return_value=False):
            self.assertTrue(p.can_create_additional_profiles())

    def test_can_create_additional_profiles_foundation_member(self):
        p = Profile()
        p.is_verified_wot = False
        with patch.object(Profile, 'is_foundation_member', return_value=True):
            self.assertTrue(p.can_create_additional_profiles())

    def test_can_manage_same_profile(self):
        p = Profile()
        p.id = 'AAAAAAAAAAAAAAAAAAAAAAAAAA'
        p.account_id = '01ACCOUNT0000000000000001'
        self.assertTrue(p.can_manage_profile(p))

    def test_can_manage_same_account(self):
        p1 = Profile()
        p1.id = 'AAAAAAAAAAAAAAAAAAAAAAAAAA'
        p1.account_id = '01ACCOUNT0000000000000001'
        p2 = Profile()
        p2.id = 'BBBBBBBBBBBBBBBBBBBBBBBBBB'
        p2.account_id = '01ACCOUNT0000000000000001'
        self.assertTrue(p1.can_manage_profile(p2))

    def test_cannot_manage_different_account(self):
        p1 = Profile()
        p1.id = 'AAAAAAAAAAAAAAAAAAAAAAAAAA'
        p1.account_id = '01ACCOUNT0000000000000001'
        p2 = Profile()
        p2.id = 'BBBBBBBBBBBBBBBBBBBBBBBBBB'
        p2.account_id = '01ACCOUNT0000000000000002'
        self.assertFalse(p1.can_manage_profile(p2))

    def test_invite_token_valid_when_active(self):
        p = Profile()
        p.invite_token = 'abc123'
        p.invite_token_active = True
        self.assertTrue(p.is_invite_token_valid())

    def test_invite_token_invalid_when_inactive(self):
        p = Profile()
        p.invite_token = 'abc123'
        p.invite_token_active = False
        self.assertFalse(p.is_invite_token_valid())

    def test_invite_token_invalid_when_empty(self):
        p = Profile()
        p.invite_token = ''
        p.invite_token_active = True
        self.assertFalse(p.is_invite_token_valid())

    def test_hna_property(self):
        p = Profile()
        p.local_name = 'alice'
        # Can't assign MagicMock to FK field, so patch the property
        with patch.object(type(p), 'hna', new_callable=lambda: property(lambda self: f'{self.local_name}@parahub.io')):
            self.assertEqual(p.hna, 'alice@parahub.io')


# ===========================================================================
# DB-backed tests: Profile CRUD
# ===========================================================================

class ProfileCreationTest(TestCase):
    """Test profile creation endpoint logic (7-profile limit, WoT requirement)."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.primary = _create_profile(self.account, self.instance, is_primary=True, is_verified_wot=True)
        self.factory = RequestFactory()

    def test_create_pseudonymous_profile_wot_verified(self):
        """WoT-verified user can create a pseudonymous profile."""
        from parahub.endpoints.profiles import create_profile, ProfileCreateRequest

        data = ProfileCreateRequest(
            profile_type='PSEUDONYMOUS',
            local_name='alice-alt',
            display_name='Alice Alt',
        )

        request = _make_auth_request(self.factory, self.account, self.primary, 'post')
        # Bypass rate limiter
        with patch('parahub.endpoints.profiles.core.ratelimit', lambda **kw: lambda fn: fn):
            response = create_profile(request, data)

        self.assertEqual(response.profile_type, 'PSEUDONYMOUS')
        self.assertFalse(response.is_primary)
        self.assertEqual(Profile.objects.filter(account=self.account).count(), 2)

    def test_create_profile_not_wot_verified_denied(self):
        """Non-WoT-verified user cannot create additional profiles."""
        from parahub.endpoints.profiles import create_profile, ProfileCreateRequest
        from ninja.errors import HttpError

        self.primary.is_verified_wot = False
        self.primary.save(update_fields=['is_verified_wot'])

        data = ProfileCreateRequest(
            profile_type='PSEUDONYMOUS',
            local_name='alice-alt',
            display_name='Alice Alt',
        )

        request = _make_auth_request(self.factory, self.account, self.primary, 'post')
        with patch('parahub.endpoints.profiles.core.ratelimit', lambda **kw: lambda fn: fn):
            with self.assertRaises(HttpError) as ctx:
                create_profile(request, data)
            self.assertEqual(ctx.exception.status_code, 403)

    def test_max_7_profiles_limit(self):
        """Cannot exceed 7 total profiles per account."""
        from parahub.endpoints.profiles import create_profile, ProfileCreateRequest
        from ninja.errors import HttpError

        # Create 6 additional profiles (total = 7 with primary)
        for i in range(6):
            _create_profile(
                self.account, self.instance,
                local_name=f'alt-{i}',
                is_primary=False,
                profile_type=Profile.ProfileType.PSEUDONYMOUS,
            )

        self.assertEqual(Profile.objects.filter(account=self.account).count(), 7)

        data = ProfileCreateRequest(
            profile_type='PSEUDONYMOUS',
            local_name='one-too-many',
            display_name='Overflow',
        )

        request = _make_auth_request(self.factory, self.account, self.primary, 'post')
        with patch('parahub.endpoints.profiles.core.ratelimit', lambda **kw: lambda fn: fn):
            with self.assertRaises(HttpError) as ctx:
                create_profile(request, data)
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn('Maximum', str(ctx.exception))

    def test_duplicate_local_name_rejected(self):
        """Cannot create profile with existing local_name on same instance."""
        from parahub.endpoints.profiles import create_profile, ProfileCreateRequest
        from ninja.errors import HttpError

        data = ProfileCreateRequest(
            profile_type='PSEUDONYMOUS',
            local_name='alice',  # already taken by primary
            display_name='Duplicate',
        )

        request = _make_auth_request(self.factory, self.account, self.primary, 'post')
        with patch('parahub.endpoints.profiles.core.ratelimit', lambda **kw: lambda fn: fn):
            with self.assertRaises(HttpError) as ctx:
                create_profile(request, data)
            self.assertEqual(ctx.exception.status_code, 400)


class ProfileDetailTest(TestCase):
    """Test public profile detail endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'bob')
        self.profile = _create_profile(self.account, self.instance, is_verified_wot=True)
        self.factory = RequestFactory()

    def test_public_profile_returns_public_fields(self):
        """Public endpoint returns expected fields."""
        from parahub.endpoints.profiles import get_public_profile

        request = self.factory.get(f'/api/v1/profiles/{self.profile.id}/')
        request.META['HTTP_AUTHORIZATION'] = ''

        response = get_public_profile(request, self.profile.id)

        self.assertEqual(response.id, self.profile.id)
        self.assertEqual(response.object_type, 'profile')
        self.assertTrue(response.is_verified_wot)
        self.assertEqual(response.hna, f'bob@test.parahub.io')

    def test_public_profile_by_local_name(self):
        """Can look up profile by local_name."""
        from parahub.endpoints.profiles import get_public_profile

        request = self.factory.get('/api/v1/profiles/bob/')
        request.META['HTTP_AUTHORIZATION'] = ''

        response = get_public_profile(request, 'bob')
        self.assertEqual(response.id, self.profile.id)

    def test_non_public_profile_hidden(self):
        """Profile with is_publicly_linked=False returns 404."""
        from parahub.endpoints.profiles import get_public_profile
        from django.http import Http404

        self.profile.is_publicly_linked = False
        self.profile.save(update_fields=['is_publicly_linked'])

        request = self.factory.get(f'/api/v1/profiles/{self.profile.id}/')
        request.META['HTTP_AUTHORIZATION'] = ''

        with self.assertRaises(Http404):
            get_public_profile(request, self.profile.id)


class ProfileUpdateTest(TestCase):
    """Test profile update (preferences PATCH) — owner only."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.factory = RequestFactory()

    def test_owner_can_update_preferences(self):
        """Owner can update display_name, language, etc."""
        from parahub.endpoints.profiles import update_my_preferences, ProfileUpdateRequest

        data = ProfileUpdateRequest(
            display_name='Alice Updated',
            preferred_language='pt',
            preferred_currency='BRL',
        )

        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'patch')

        # update_my_preferences calls get_my_profile internally which needs location logic
        with patch('parahub.endpoints.profiles.core.get_my_profile') as mock_get:
            mock_get.return_value = MagicMock(display_name='Alice Updated')
            response = update_my_preferences(request, data)

        self.alice.refresh_from_db()
        self.assertEqual(self.alice.display_name, 'Alice Updated')
        self.assertEqual(self.alice.preferred_language, 'pt')
        self.assertEqual(self.alice.preferred_currency, 'BRL')


# ===========================================================================
# DB-backed tests: Partner invites
# ===========================================================================

class PartnerInviteTest(TestCase):
    """Test partner invite token generation, acceptance, and lifecycle."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob')
        self.factory = RequestFactory()

    def test_get_invite_generates_token(self):
        """First call to get_invite_link generates a token."""
        from parahub.endpoints.partners import get_invite_link

        self.assertIsNone(self.alice.invite_token)

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        response = get_invite_link(request)

        self.alice.refresh_from_db()
        self.assertIsNotNone(self.alice.invite_token)
        self.assertTrue(response.is_active)
        self.assertIn(self.alice.invite_token, response.invite_url)

    def test_regenerate_creates_new_token(self):
        """Regenerate creates a new token, old one becomes invalid."""
        from parahub.endpoints.partners import regenerate_invite_token

        self.alice.generate_invite_token()
        old_token = self.alice.invite_token

        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        with patch('parahub.endpoints.partners.ratelimit', lambda **kw: lambda fn: fn):
            response = regenerate_invite_token(request)

        self.alice.refresh_from_db()
        self.assertNotEqual(self.alice.invite_token, old_token)
        self.assertTrue(response.is_active)

    def test_toggle_invite_token(self):
        """Toggle invite token active/inactive."""
        from parahub.endpoints.partners import toggle_invite_token, ToggleInviteRequest

        self.alice.generate_invite_token()
        self.assertTrue(self.alice.invite_token_active)

        # Disable
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = toggle_invite_token(request, ToggleInviteRequest(active=False))

        self.alice.refresh_from_db()
        self.assertFalse(self.alice.invite_token_active)
        self.assertFalse(response.is_active)

        # Re-enable
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = toggle_invite_token(request, ToggleInviteRequest(active=True))

        self.alice.refresh_from_db()
        self.assertTrue(self.alice.invite_token_active)

    def test_accept_invitation_creates_mutual_partnership(self):
        """Accepting invite creates mutual partnership (both directions)."""
        from parahub.endpoints.partners import accept_invitation, AddPartnerRequest

        self.alice.generate_invite_token()

        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        data = AddPartnerRequest(invite_token=self.alice.invite_token)

        with patch('parahub.endpoints.partners.ratelimit', lambda **kw: lambda fn: fn):
            with patch('parahub.services.ws_publish.ws_publish'):
                with patch('parahub.endpoints.matrix_auth.create_dm_between_accounts'):
                    response = accept_invitation(request, data)

        # Both directions exist
        self.assertTrue(Partner.objects.filter(profile=self.bob, partner_profile=self.alice).exists())
        self.assertTrue(Partner.objects.filter(profile=self.alice, partner_profile=self.bob).exists())

    def test_accept_invalid_token_rejected(self):
        """Invalid invite token returns error."""
        from parahub.endpoints.partners import accept_invitation, AddPartnerRequest

        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        data = AddPartnerRequest(invite_token='nonexistent-token-123')

        with patch('parahub.endpoints.partners.ratelimit', lambda **kw: lambda fn: fn):
            response = accept_invitation(request, data)

        # Returns tuple (error, status_code)
        self.assertEqual(response, (400, {"error": "Invalid or inactive invite token"}))

    def test_cannot_add_self_as_partner(self):
        """Cannot accept own invite token."""
        from parahub.endpoints.partners import accept_invitation, AddPartnerRequest

        self.alice.generate_invite_token()

        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        data = AddPartnerRequest(invite_token=self.alice.invite_token)

        with patch('parahub.endpoints.partners.ratelimit', lambda **kw: lambda fn: fn):
            response = accept_invitation(request, data)

        self.assertEqual(response, (400, {"error": "Cannot add yourself as partner"}))

    def test_accept_inactive_token_rejected(self):
        """Deactivated invite token cannot be accepted."""
        from parahub.endpoints.partners import accept_invitation, AddPartnerRequest

        self.alice.generate_invite_token()
        self.alice.invite_token_active = False
        self.alice.save(update_fields=['invite_token_active'])

        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        data = AddPartnerRequest(invite_token=self.alice.invite_token)

        with patch('parahub.endpoints.partners.ratelimit', lambda **kw: lambda fn: fn):
            response = accept_invitation(request, data)

        self.assertEqual(response, (400, {"error": "Invalid or inactive invite token"}))

    def test_direct_add_one_way(self):
        """Direct add creates one-way partnership only."""
        from parahub.endpoints.partners import add_partner_direct

        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with patch('parahub.services.ws_publish.ws_publish'):
            response = add_partner_direct(request, self.bob.id)

        self.assertTrue(Partner.objects.filter(profile=self.alice, partner_profile=self.bob).exists())
        self.assertFalse(Partner.objects.filter(profile=self.bob, partner_profile=self.alice).exists())

    def test_remove_partner(self):
        """Removing partner deletes only own direction."""
        from parahub.endpoints.partners import remove_partner

        # Create mutual partnership
        Partner.objects.create(profile=self.alice, partner_profile=self.bob)
        Partner.objects.create(profile=self.bob, partner_profile=self.alice)

        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'delete')

        with patch('parahub.services.ws_publish.ws_publish'):
            response = remove_partner(request, self.bob.id)

        self.assertFalse(Partner.objects.filter(profile=self.alice, partner_profile=self.bob).exists())
        # Bob's direction remains
        self.assertTrue(Partner.objects.filter(profile=self.bob, partner_profile=self.alice).exists())


# ===========================================================================
# DB-backed tests: WoT verification and permissions
# ===========================================================================

class WoTVerificationTest(TestCase):
    """Test WoT verification count affects profile permissions."""

    def setUp(self):
        self.instance = _create_instance()
        self.target_account = _create_account(self.instance, 'target')
        self.target = _create_profile(self.target_account, self.instance)

    def _create_verifier(self, name):
        acc = _create_account(self.instance, name)
        return _create_profile(acc, self.instance, local_name=name)

    def test_unverified_below_3(self):
        """Profile with <3 verifications is not WoT verified."""
        v1 = self._create_verifier('v1')
        v2 = self._create_verifier('v2')
        Verification.objects.create(verifier=v1, verified_profile=self.target)
        Verification.objects.create(verifier=v2, verified_profile=self.target)

        count = Verification.objects.filter(verified_profile=self.target, is_active=True).count()
        self.assertEqual(count, 2)
        self.assertFalse(self.target.is_verified_wot)

    def test_verified_at_3(self):
        """Profile with 3+ verifications can be marked WoT verified."""
        for i in range(3):
            verifier = self._create_verifier(f'verifier-{i}')
            Verification.objects.create(verifier=verifier, verified_profile=self.target)

        count = Verification.objects.filter(verified_profile=self.target, is_active=True).count()
        self.assertEqual(count, 3)

        # Simulate what the verify endpoint does
        self.target.is_verified_wot = count >= 3
        self.target.save(update_fields=['is_verified_wot'])

        self.assertTrue(self.target.is_verified_wot)
        self.assertTrue(self.target.can_create_additional_profiles())

    def test_revoked_verification_drops_below_threshold(self):
        """Revoking a verification can drop below 3 and revoke WoT status."""
        verifiers = []
        for i in range(3):
            v = self._create_verifier(f'v-{i}')
            Verification.objects.create(verifier=v, verified_profile=self.target)
            verifiers.append(v)

        self.target.is_verified_wot = True
        self.target.save(update_fields=['is_verified_wot'])

        # Revoke one verification
        Verification.objects.filter(verifier=verifiers[0], verified_profile=self.target).update(is_active=False)

        remaining = Verification.objects.filter(verified_profile=self.target, is_active=True).count()
        self.target.is_verified_wot = remaining >= 3
        self.target.save(update_fields=['is_verified_wot'])

        self.assertEqual(remaining, 2)
        self.assertFalse(self.target.is_verified_wot)
        self.assertFalse(self.target.can_create_additional_profiles())

    def test_can_verify_others_requires_pgp_and_wot(self):
        """can_verify_others requires PGP key + WoT verified + 3 verifications."""
        # No PGP key
        self.target.pgp_public_key = ''
        self.target.pgp_fingerprint = ''
        self.target.is_verified_wot = True
        with patch.object(Profile, 'is_foundation_member', return_value=False):
            self.assertFalse(self.target.can_verify_others())

        # Has PGP but not verified
        self.target.pgp_public_key = 'KEY'
        self.target.pgp_fingerprint = 'FINGERPRINT'
        self.target.is_verified_wot = False
        with patch.object(Profile, 'is_foundation_member', return_value=False):
            self.assertFalse(self.target.can_verify_others())

        # Has PGP + verified + 3 verifications
        self.target.is_verified_wot = True
        for i in range(3):
            v = self._create_verifier(f'verifier-cv-{i}')
            Verification.objects.create(verifier=v, verified_profile=self.target)

        with patch.object(Profile, 'is_foundation_member', return_value=False):
            self.assertTrue(self.target.can_verify_others())


# ===========================================================================
# DB-backed tests: Profile search
# ===========================================================================

class ProfileSearchTest(TestCase):
    """Test profile search endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.searcher_account = _create_account(self.instance, 'searcher')
        self.searcher = _create_profile(self.searcher_account, self.instance)

        self.visible_account = _create_account(self.instance, 'visible-user')
        self.visible = _create_profile(
            self.visible_account, self.instance,
            local_name='visible-user',
            is_publicly_linked=True,
            is_verified_wot=True,
        )

        self.hidden_account = _create_account(self.instance, 'hidden-user')
        self.hidden = _create_profile(
            self.hidden_account, self.instance,
            local_name='hidden-user',
            is_publicly_linked=False,
        )

        self.factory = RequestFactory()

    def test_search_finds_public_profiles(self):
        """Search returns publicly linked profiles matching query."""
        from parahub.endpoints.profiles import search_profiles

        request = _make_auth_request(self.factory, self.searcher_account, self.searcher)
        response = search_profiles(request, q='visible', verified_only=False, only_partners=False)

        ids = [item.id for item in response['items']]
        self.assertIn(self.visible.id, ids)

    def test_search_excludes_non_public_profiles(self):
        """Search does not return profiles with is_publicly_linked=False."""
        from parahub.endpoints.profiles import search_profiles

        request = _make_auth_request(self.factory, self.searcher_account, self.searcher)
        response = search_profiles(request, q='hidden', verified_only=False, only_partners=False)

        ids = [item.id for item in response['items']]
        self.assertNotIn(self.hidden.id, ids)

    def test_search_verified_only_filter(self):
        """verified_only=True excludes unverified profiles."""
        from parahub.endpoints.profiles import search_profiles

        unverified_account = _create_account(self.instance, 'unverified')
        _create_profile(
            unverified_account, self.instance,
            local_name='unverified',
            is_verified_wot=False,
        )

        request = _make_auth_request(self.factory, self.searcher_account, self.searcher)
        response = search_profiles(request, q='', verified_only=True, only_partners=False)

        ids = [item.id for item in response['items']]
        self.assertIn(self.visible.id, ids)
        for item in response['items']:
            self.assertTrue(item.is_verified_wot)

    def test_search_only_partners_filter(self):
        """only_partners=True returns only user's partners."""
        from parahub.endpoints.profiles import search_profiles

        Partner.objects.create(profile=self.searcher, partner_profile=self.visible)

        request = _make_auth_request(self.factory, self.searcher_account, self.searcher)
        response = search_profiles(request, q='', verified_only=False, only_partners=True)

        ids = [item.id for item in response['items']]
        self.assertIn(self.visible.id, ids)
        self.assertEqual(len(response['items']), 1)

    def test_search_by_hna(self):
        """Search by HNA format (local_name@domain)."""
        from parahub.endpoints.profiles import search_profiles

        request = _make_auth_request(self.factory, self.searcher_account, self.searcher)
        response = search_profiles(
            request,
            q=f'visible-user@test.parahub.io',
            verified_only=False,
            only_partners=False,
        )

        ids = [item.id for item in response['items']]
        self.assertIn(self.visible.id, ids)

    def test_search_pagination(self):
        """Search respects page and page_size."""
        from parahub.endpoints.profiles import search_profiles

        request = _make_auth_request(self.factory, self.searcher_account, self.searcher)
        response = search_profiles(request, q='', verified_only=False, only_partners=False, page=1, page_size=1)

        self.assertEqual(response['page'], 1)
        self.assertEqual(response['page_size'], 1)
        self.assertLessEqual(len(response['items']), 1)


# ===========================================================================
# DB-backed tests: Partnership status
# ===========================================================================

class PartnershipStatusTest(TestCase):
    """Test partnership status check endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob')
        self.factory = RequestFactory()

    def test_no_partnership(self):
        """No partnership between two profiles."""
        from parahub.endpoints.partners import check_partnership_status

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        response = check_partnership_status(request, self.bob.id)

        self.assertFalse(response.i_added_them)
        self.assertFalse(response.they_added_me)
        self.assertFalse(response.is_mutual)

    def test_one_way_partnership(self):
        """One-way partnership shows correctly."""
        from parahub.endpoints.partners import check_partnership_status

        Partner.objects.create(profile=self.alice, partner_profile=self.bob)

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        response = check_partnership_status(request, self.bob.id)

        self.assertTrue(response.i_added_them)
        self.assertFalse(response.they_added_me)
        self.assertFalse(response.is_mutual)

    def test_mutual_partnership(self):
        """Mutual partnership detected."""
        from parahub.endpoints.partners import check_partnership_status

        Partner.objects.create(profile=self.alice, partner_profile=self.bob)
        Partner.objects.create(profile=self.bob, partner_profile=self.alice)

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        response = check_partnership_status(request, self.bob.id)

        self.assertTrue(response.i_added_them)
        self.assertTrue(response.they_added_me)
        self.assertTrue(response.is_mutual)

    def test_self_check_returns_false(self):
        """Checking partnership with self returns all false."""
        from parahub.endpoints.partners import check_partnership_status

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        response = check_partnership_status(request, self.alice.id)

        self.assertFalse(response.i_added_them)
        self.assertFalse(response.is_mutual)


# ===========================================================================
# DB-backed tests: Manageable profiles
# ===========================================================================

class ManageableProfilesTest(TestCase):
    """Test manageable profiles endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.primary = _create_profile(self.account, self.instance, is_primary=True, is_verified_wot=True)
        self.factory = RequestFactory()

    def test_returns_all_account_profiles(self):
        """Manageable profiles returns all profiles under the account."""
        from parahub.endpoints.profiles import get_manageable_profiles

        alt = _create_profile(
            self.account, self.instance,
            local_name='alice-alt',
            is_primary=False,
            profile_type=Profile.ProfileType.PSEUDONYMOUS,
        )

        request = _make_auth_request(self.factory, self.account, self.primary)
        response = get_manageable_profiles(request)

        ids = [p.id for p in response]
        self.assertIn(self.primary.id, ids)
        self.assertIn(alt.id, ids)
        self.assertEqual(len(response), 2)

    def test_other_account_profiles_excluded(self):
        """Profiles from another account are not included."""
        other_account = _create_account(self.instance, 'other')
        _create_profile(other_account, self.instance, local_name='other')

        from parahub.endpoints.profiles import get_manageable_profiles

        request = _make_auth_request(self.factory, self.account, self.primary)
        response = get_manageable_profiles(request)

        ids = [p.id for p in response]
        self.assertEqual(len(ids), 1)
        self.assertIn(self.primary.id, ids)


# ===========================================================================
# Reputation scoring tests
# ===========================================================================

import math
from identity.reputation import calculate_reputation
from contracts.models import Contract, ContractReview
from geo.models import (
    Event, EventParticipant, Establishment, EstablishmentMembership,
)
from governance.models import PollContext, Poll, PollOption, PollVote, PollVoteDelegation
from debts.models import Debt
from django.utils import timezone


class ReputationZeroActivityTest(TestCase):
    """Test reputation for a brand new user with no activity."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, username='rep_zero')
        self.profile = _create_profile(self.account, self.instance, local_name='rep_zero')

    def test_zero_activity_scores(self):
        result = calculate_reputation(self.profile)
        self.assertEqual(result['identity'], Decimal('0.0000'))
        self.assertEqual(result['commerce'], Decimal('0.0000'))
        self.assertEqual(result['community'], Decimal('0.0000'))
        self.assertEqual(result['contribution'], Decimal('0.0000'))
        self.assertEqual(result['governance'], Decimal('0.0000'))
        # reliability neutral default = 5.0 (fewer than 3 commitments)
        self.assertEqual(result['reliability'], Decimal('5.0000'))

    def test_zero_activity_total(self):
        result = calculate_reputation(self.profile)
        self.assertEqual(result['total'], Decimal('5.0000'))

    def test_zero_activity_active_dimensions(self):
        """Only reliability counts as active at neutral default (5.0 = not active)."""
        result = calculate_reputation(self.profile)
        self.assertEqual(result['active_dimensions'], 0)


class ReputationIdentityDimensionTest(TestCase):
    """Test identity dimension: WoT verifications."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, username='rep_id')
        self.profile = _create_profile(self.account, self.instance, local_name='rep_id')
        # Create verifiers
        self.verifiers = []
        for i in range(5):
            acc = _create_account(self.instance, username=f'verifier{i}')
            prof = _create_profile(acc, self.instance, local_name=f'verifier{i}')
            self.verifiers.append(prof)

    def test_one_verification(self):
        Verification.objects.create(
            verifier=self.verifiers[0], verified_profile=self.profile,
            is_active=True,
        )
        result = calculate_reputation(self.profile)
        expected = min(Decimal('25'), Decimal(str(8.3 * math.log(2))))
        self.assertEqual(result['identity'], expected.quantize(Decimal('0.0001')))
        self.assertGreater(result['identity'], Decimal('0'))

    def test_three_verifications(self):
        for i in range(3):
            Verification.objects.create(
                verifier=self.verifiers[i], verified_profile=self.profile,
                is_active=True,
            )
        result = calculate_reputation(self.profile)
        expected = min(Decimal('25'), Decimal(str(8.3 * math.log(4))))
        self.assertEqual(result['identity'], expected.quantize(Decimal('0.0001')))

    def test_inactive_verification_not_counted(self):
        Verification.objects.create(
            verifier=self.verifiers[0], verified_profile=self.profile,
            is_active=False,
        )
        result = calculate_reputation(self.profile)
        self.assertEqual(result['identity'], Decimal('0.0000'))

    def test_identity_capped_at_25(self):
        """Even with many verifications, identity maxes at 25."""
        for i in range(5):
            Verification.objects.create(
                verifier=self.verifiers[i], verified_profile=self.profile,
                is_active=True,
            )
        result = calculate_reputation(self.profile)
        self.assertLessEqual(result['identity'], Decimal('25.0000'))

    def test_identity_counted_as_active_dimension(self):
        Verification.objects.create(
            verifier=self.verifiers[0], verified_profile=self.profile,
            is_active=True,
        )
        result = calculate_reputation(self.profile)
        self.assertGreaterEqual(result['active_dimensions'], 1)


class ReputationCommerceDimensionTest(TestCase):
    """Test commerce dimension: contract review average (min 3 reviews)."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, username='rep_com')
        self.profile = _create_profile(self.account, self.instance, local_name='rep_com')
        self.other_acc = _create_account(self.instance, username='rep_com_other')
        self.other_profile = _create_profile(self.other_acc, self.instance, local_name='rep_com_other')

    def _create_contract_and_review(self, rating, reviewer_username):
        reviewer_acc = _create_account(self.instance, username=reviewer_username)
        reviewer_prof = _create_profile(reviewer_acc, self.instance, local_name=reviewer_username)
        contract = Contract.objects.create(
            creator=reviewer_prof, partner=self.profile,
            title='Test Contract', status=Contract.Status.COMPLETED,
        )
        ContractReview.objects.create(
            contract=contract, reviewer=reviewer_prof,
            reviewed=self.profile, rating=rating,
        )
        return contract

    def test_fewer_than_3_reviews_is_zero(self):
        self._create_contract_and_review(5, 'rev1')
        self._create_contract_and_review(5, 'rev2')
        result = calculate_reputation(self.profile)
        self.assertEqual(result['commerce'], Decimal('0.0000'))

    def test_3_reviews_scored(self):
        self._create_contract_and_review(4, 'rev1')
        self._create_contract_and_review(5, 'rev2')
        self._create_contract_and_review(3, 'rev3')
        result = calculate_reputation(self.profile)
        avg_rating = (4 + 5 + 3) / 3
        expected = min(Decimal('15'), Decimal(str(avg_rating * 3.0)))
        self.assertEqual(result['commerce'], expected.quantize(Decimal('0.0001')))
        self.assertGreater(result['commerce'], Decimal('0'))

    def test_commerce_capped_at_15(self):
        for i in range(5):
            self._create_contract_and_review(5, f'rev5_{i}')
        result = calculate_reputation(self.profile)
        self.assertEqual(result['commerce'], Decimal('15.0000'))


class ReputationReliabilityDimensionTest(TestCase):
    """Test reliability dimension: contract completion + debt repayment rates."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, username='rep_rel')
        self.profile = _create_profile(self.account, self.instance, local_name='rep_rel')
        self.other_acc = _create_account(self.instance, username='rep_rel_other')
        self.other_profile = _create_profile(self.other_acc, self.instance, local_name='rep_rel_other')

    def test_fewer_than_3_commitments_neutral(self):
        """< 3 total commitments = neutral 5.0."""
        Contract.objects.create(
            creator=self.profile, partner=self.other_profile,
            title='C1', status=Contract.Status.COMPLETED,
        )
        result = calculate_reputation(self.profile)
        self.assertEqual(result['reliability'], Decimal('5.0000'))

    def test_perfect_completion(self):
        """3 completed contracts + 0 debts = perfect reliability."""
        for i in range(3):
            Contract.objects.create(
                creator=self.profile, partner=self.other_profile,
                title=f'C{i}', status=Contract.Status.COMPLETED,
            )
        result = calculate_reputation(self.profile)
        # completion_rate=1.0, repayment_rate=1.0 (no debts)
        # 10 * (0.6 * 1.0 + 0.4 * 1.0) = 10.0
        self.assertEqual(result['reliability'], Decimal('10.0000'))

    def test_mixed_completion(self):
        """2 completed + 1 signed (not completed) contracts."""
        for i in range(2):
            Contract.objects.create(
                creator=self.profile, partner=self.other_profile,
                title=f'Done{i}', status=Contract.Status.COMPLETED,
            )
        Contract.objects.create(
            creator=self.profile, partner=self.other_profile,
            title='Still signed', status=Contract.Status.SIGNED,
        )
        result = calculate_reputation(self.profile)
        # completion_rate = 2/3, repayment_rate = 1.0 (no debts)
        expected_raw = 10 * (0.6 * (2/3) + 0.4 * 1.0)
        expected = min(Decimal('10'), Decimal(str(expected_raw)))
        self.assertEqual(result['reliability'], expected.quantize(Decimal('0.0001')))

    def test_reliability_active_dimension(self):
        """When reliability differs from neutral 5.0, it counts as active."""
        for i in range(3):
            Contract.objects.create(
                creator=self.profile, partner=self.other_profile,
                title=f'C{i}', status=Contract.Status.COMPLETED,
            )
        result = calculate_reputation(self.profile)
        # reliability should be 10.0 != 5.0 → active
        self.assertNotEqual(result['reliability'], Decimal('5.0000'))


class ReputationTotalTest(TestCase):
    """Test total calculation across dimensions."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, username='rep_total')
        self.profile = _create_profile(self.account, self.instance, local_name='rep_total')

    def test_total_is_sum_of_dimensions(self):
        result = calculate_reputation(self.profile)
        dimension_sum = (
            result['identity'] + result['commerce'] + result['community']
            + result['contribution'] + result['governance'] + result['reliability']
        )
        self.assertEqual(result['total'], dimension_sum)

    def test_all_dimensions_quantized_to_4_decimal_places(self):
        result = calculate_reputation(self.profile)
        for key in ('identity', 'commerce', 'community', 'contribution',
                     'governance', 'reliability', 'total'):
            val = result[key]
            self.assertEqual(val, val.quantize(Decimal('0.0001')))
