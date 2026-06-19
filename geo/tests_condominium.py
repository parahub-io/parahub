"""
Tests for condominium management endpoints: fractions, quotas, invites, assemblies.

Tests invariants that must never break:
- WoT 3+ requirement for creating condominiums
- Permilagem sum must be exactly 1000
- Only OWNER/ADMIN can manage fractions, payments, invites, assemblies
- Members (non-admin) can list fractions and quotas but not modify
- Non-members get 403 on fraction/quota access
- Invite token: generate → get info (public) → accept (consumes token)
- Cannot delete fraction with assigned resident
- Duplicate fraction identifier rejected
- Quota payment idempotent (get_or_create on fraction+month)
- Assembly creates weighted poll with permilagem-based voters
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory
from django.contrib.gis.geos import Point
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from ninja.errors import HttpError
from django.http import Http404

from identity.models import Account, Profile, Verification
from core.models import Instance
from geo.models import (
    WorldObject, Establishment, EstablishmentMembership,
    CondominiumFraction, QuotaPayment,
)
from geo.services.condominium import CondominiumService


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


def _make_anon_request(factory, method='get', path='/fake/'):
    """Build an unauthenticated request."""
    fn = getattr(factory, method)
    request = fn(path)
    request.auth_profile = None
    return request


def _add_verifications(profile, count=3):
    """Add WoT verifications to a profile so it passes WoT 3+ check."""
    instance = profile.instance
    for i in range(count):
        acc = _create_account(instance, f'v{i}_{profile.local_name}')
        vp = _create_profile(acc, instance, local_name=f'v{i}_{profile.local_name}')
        Verification.objects.create(verifier=vp, verified_profile=profile, is_active=True)


def _create_building(**kwargs):
    defaults = {
        'location': Point(-9.13706, 38.71147, srid=4326),
        'country': 'PT',
        'city': 'Lisboa',
        'street': 'Rua Augusta',
        'house_number': '10',
        'full_address': 'Rua Augusta 10, Lisboa, PT',
        'building_type': 'commercial',
        'levels': 3,
    }
    defaults.update(kwargs)
    return WorldObject.objects.create(**defaults)


def _create_condominium(owner_profile, building=None, name='Test Condo', slug='test-condo',
                        fractions_data=None):
    """Create a condominium establishment with fractions directly in DB."""
    if building is None:
        building = _create_building()
    est = Establishment.objects.create(
        owner=owner_profile,
        world_object=building,
        name=name,
        slug=slug,
        organization_type='CONDOMINIUM',
        member_visibility='MEMBERS_ONLY',
        is_active=True,
        treasury_enabled=True,
        attributes={'monthly_budget': '500'},
    )
    EstablishmentMembership.objects.create(
        profile=owner_profile,
        establishment=est,
        role='OWNER',
        membership_level='fundador',
    )
    # Default fractions: 3 units totaling 1000
    if fractions_data is None:
        fractions_data = [
            {'identifier': '1-A', 'permilagem': Decimal('400.000'), 'fraction_type': 'APARTMENT'},
            {'identifier': '1-B', 'permilagem': Decimal('350.000'), 'fraction_type': 'APARTMENT'},
            {'identifier': 'Gar-1', 'permilagem': Decimal('250.000'), 'fraction_type': 'GARAGE'},
        ]
    fractions = []
    for fd in fractions_data:
        fractions.append(CondominiumFraction.objects.create(
            establishment=est,
            identifier=fd['identifier'],
            permilagem=fd['permilagem'],
            fraction_type=fd.get('fraction_type', 'APARTMENT'),
            description=fd.get('description', ''),
            floor=fd.get('floor', ''),
        ))
    return est, fractions


# ===========================================================================
# Condominium Creation Tests
# ===========================================================================

class CondominiumCreateTest(TestCase):
    """Test POST /condominiums/ endpoint."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        _add_verifications(self.profile, count=3)
        self.building = _create_building()

    @patch('geo.endpoints.events._create_event_matrix_room', return_value=None)
    def test_create_condominium_success(self, mock_matrix):
        """Create condominium with valid fractions succeeds."""
        from geo.endpoints.condominium import create_condominium, CondominiumCreateInput, FractionInput

        data = CondominiumCreateInput(
            world_object_id=self.building.id,
            name='Condomínio Augusta 10',
            fractions=[
                FractionInput(identifier='1-A', permilagem=Decimal('500.000')),
                FractionInput(identifier='1-B', permilagem=Decimal('300.000')),
                FractionInput(identifier='Gar-1', permilagem=Decimal('200.000'), fraction_type='GARAGE'),
            ],
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')

        result = create_condominium(request, data)

        self.assertEqual(result['object_type'], 'establishment')
        self.assertEqual(result['name'], 'Condomínio Augusta 10')
        self.assertEqual(result['fractions_count'], 3)
        self.assertTrue(result['slug'])

        # Verify DB state
        est = Establishment.objects.get(id=result['id'])
        self.assertEqual(est.organization_type, 'CONDOMINIUM')
        self.assertTrue(est.treasury_enabled)
        self.assertEqual(est.fractions.count(), 3)

        # Verify owner membership created
        self.assertTrue(
            EstablishmentMembership.objects.filter(
                profile=self.profile, establishment=est, role='OWNER'
            ).exists()
        )

    def test_create_condominium_permilagem_not_1000(self):
        """Fractions that don't sum to 1000 → 400."""
        from geo.endpoints.condominium import create_condominium, CondominiumCreateInput, FractionInput

        data = CondominiumCreateInput(
            world_object_id=self.building.id,
            name='Bad Permilagem',
            fractions=[
                FractionInput(identifier='1-A', permilagem=Decimal('500.000')),
                FractionInput(identifier='1-B', permilagem=Decimal('300.000')),
                # Missing 200 to reach 1000
            ],
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_condominium(request, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_condominium_wot_insufficient(self):
        """User without WoT 3+ → 403."""
        from geo.endpoints.condominium import create_condominium, CondominiumCreateInput, FractionInput

        no_wot_acc = _create_account(self.instance, 'nowot')
        no_wot_profile = _create_profile(no_wot_acc, self.instance, 'nowot')
        # No verifications added

        data = CondominiumCreateInput(
            world_object_id=self.building.id,
            name='No WoT Condo',
            fractions=[
                FractionInput(identifier='1-A', permilagem=Decimal('1000.000')),
            ],
        )
        request = _make_auth_request(self.factory, no_wot_acc, no_wot_profile, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_condominium(request, data)
        self.assertEqual(ctx.exception.status_code, 403)


# ===========================================================================
# Fraction List Tests
# ===========================================================================

class FractionListTest(TestCase):
    """Test GET /condominiums/{slug}/fractions/ endpoint."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        # Owner
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        # Member
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, 'bob')
        # Outsider
        self.charlie_acc = _create_account(self.instance, 'charlie')
        self.charlie = _create_profile(self.charlie_acc, self.instance, 'charlie')

        self.est, self.fractions = _create_condominium(self.alice)
        # Make bob a fraction resident (member via fraction)
        self.fractions[0].resident = self.bob
        self.fractions[0].save(update_fields=['resident'])

    def test_owner_sees_fractions_with_tokens(self):
        """Owner sees all fractions including invite tokens."""
        from geo.endpoints.condominium import list_fractions

        # Generate a token on one fraction
        self.fractions[1].invite_token = 'test-token-abc'
        self.fractions[1].save(update_fields=['invite_token'])

        request = _make_auth_request(self.factory, self.alice_acc, self.alice)
        result = list_fractions(request, self.est.slug)

        self.assertEqual(len(result), 3)
        identifiers = [f.identifier for f in result]
        self.assertIn('1-A', identifiers)
        self.assertIn('1-B', identifiers)
        self.assertIn('Gar-1', identifiers)

        # Owner sees invite_token
        frac_b = next(f for f in result if f.identifier == '1-B')
        self.assertEqual(frac_b.invite_token, 'test-token-abc')

    def test_member_sees_fractions_without_tokens(self):
        """Member (fraction resident) sees fractions but NOT invite tokens."""
        from geo.endpoints.condominium import list_fractions

        self.fractions[1].invite_token = 'secret-token'
        self.fractions[1].save(update_fields=['invite_token'])

        request = _make_auth_request(self.factory, self.bob_acc, self.bob)
        result = list_fractions(request, self.est.slug)

        self.assertEqual(len(result), 3)
        # Member should not see invite tokens
        frac_b = next(f for f in result if f.identifier == '1-B')
        self.assertIsNone(frac_b.invite_token)

    def test_outsider_cannot_list_fractions(self):
        """Non-member gets 403."""
        from geo.endpoints.condominium import list_fractions

        request = _make_auth_request(self.factory, self.charlie_acc, self.charlie)

        with self.assertRaises(HttpError) as ctx:
            list_fractions(request, self.est.slug)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_nonexistent_condo_404(self):
        """Unknown slug → 404."""
        from geo.endpoints.condominium import list_fractions

        request = _make_auth_request(self.factory, self.alice_acc, self.alice)

        with self.assertRaises(Http404):
            list_fractions(request, 'nonexistent-slug')


# ===========================================================================
# Fraction CRUD Tests
# ===========================================================================

class FractionCRUDTest(TestCase):
    """Test add/update/delete fraction endpoints."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, 'bob')

        self.est, self.fractions = _create_condominium(self.alice)

    def test_add_fraction_success(self):
        """Admin adds a new fraction."""
        from geo.endpoints.condominium import add_fraction, FractionInput

        data = FractionInput(
            identifier='2-A',
            permilagem=Decimal('100.000'),
            fraction_type='APARTMENT',
            floor='2',
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'post')
        result = add_fraction(request, self.est.slug, data)

        self.assertEqual(result.identifier, '2-A')
        self.assertEqual(result.object_type, 'condominium_fraction')
        self.assertEqual(result.permilagem, Decimal('100.000'))
        self.assertEqual(result.floor, '2')
        self.assertEqual(CondominiumFraction.objects.filter(establishment=self.est).count(), 4)

    def test_add_fraction_duplicate_identifier(self):
        """Duplicate identifier → 400."""
        from geo.endpoints.condominium import add_fraction, FractionInput

        data = FractionInput(identifier='1-A', permilagem=Decimal('50.000'))
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            add_fraction(request, self.est.slug, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_non_admin_cannot_add_fraction(self):
        """Regular member cannot add fractions → 403."""
        from geo.endpoints.condominium import add_fraction, FractionInput

        # Make bob a member but not admin
        EstablishmentMembership.objects.create(
            profile=self.bob, establishment=self.est, role='MEMBER',
        )
        data = FractionInput(identifier='2-B', permilagem=Decimal('50.000'))
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, 'post')

        with self.assertRaises(HttpError) as ctx:
            add_fraction(request, self.est.slug, data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_update_fraction_success(self):
        """Owner updates fraction fields."""
        from geo.endpoints.condominium import update_fraction, FractionUpdateInput

        frac = self.fractions[0]
        data = FractionUpdateInput(
            description='Renovated T3',
            floor='1',
            permilagem=Decimal('420.000'),
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'put')
        result = update_fraction(request, self.est.slug, frac.id, data)

        self.assertEqual(result.description, 'Renovated T3')
        self.assertEqual(result.floor, '1')
        self.assertEqual(result.permilagem, Decimal('420.000'))

    def test_update_fraction_duplicate_identifier(self):
        """Renaming to an existing identifier → 400."""
        from geo.endpoints.condominium import update_fraction, FractionUpdateInput

        frac = self.fractions[0]  # 1-A
        data = FractionUpdateInput(identifier='1-B')  # already exists
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'put')

        with self.assertRaises(HttpError) as ctx:
            update_fraction(request, self.est.slug, frac.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_update_fraction_assign_resident(self):
        """Owner assigns a resident to a fraction."""
        from geo.endpoints.condominium import update_fraction, FractionUpdateInput

        frac = self.fractions[1]  # 1-B, no resident
        data = FractionUpdateInput(resident_id=self.bob.id, is_owner=False)
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'put')
        result = update_fraction(request, self.est.slug, frac.id, data)

        self.assertEqual(result.resident_id, self.bob.id)
        self.assertFalse(result.is_owner)

    def test_update_fraction_clear_resident(self):
        """Owner clears resident by passing empty string."""
        from geo.endpoints.condominium import update_fraction, FractionUpdateInput

        frac = self.fractions[0]
        frac.resident = self.bob
        frac.save(update_fields=['resident'])

        data = FractionUpdateInput(resident_id='')
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'put')
        result = update_fraction(request, self.est.slug, frac.id, data)

        self.assertIsNone(result.resident_id)

    def test_delete_vacant_fraction_success(self):
        """Delete a fraction without a resident succeeds."""
        from geo.endpoints.condominium import delete_fraction

        frac = self.fractions[2]  # Gar-1, no resident
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'delete')
        result = delete_fraction(request, self.est.slug, frac.id)

        self.assertTrue(result['ok'])
        self.assertEqual(CondominiumFraction.objects.filter(establishment=self.est).count(), 2)

    def test_delete_occupied_fraction_fails(self):
        """Delete fraction with assigned resident → 409."""
        from geo.endpoints.condominium import delete_fraction

        frac = self.fractions[0]
        frac.resident = self.bob
        frac.save(update_fields=['resident'])

        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'delete')

        with self.assertRaises(HttpError) as ctx:
            delete_fraction(request, self.est.slug, frac.id)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_non_admin_cannot_delete_fraction(self):
        """Member cannot delete fractions → 403."""
        from geo.endpoints.condominium import delete_fraction

        EstablishmentMembership.objects.create(
            profile=self.bob, establishment=self.est, role='MEMBER',
        )
        frac = self.fractions[2]
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, 'delete')

        with self.assertRaises(HttpError) as ctx:
            delete_fraction(request, self.est.slug, frac.id)
        self.assertEqual(ctx.exception.status_code, 403)


# ===========================================================================
# Invite Flow Tests
# ===========================================================================

class InviteFlowTest(TestCase):
    """Test invite generate → get info → accept flow."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, 'bob')

        self.est, self.fractions = _create_condominium(self.alice)

    def test_generate_invite_token(self):
        """Admin generates invite token for a fraction."""
        from geo.endpoints.condominium import generate_invite

        frac = self.fractions[0]
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'post')
        result = generate_invite(request, self.est.slug, frac.id)

        self.assertIn('token', result)
        self.assertTrue(len(result['token']) > 20)
        self.assertEqual(result['fraction_identifier'], '1-A')

        # Verify token saved in DB
        frac.refresh_from_db()
        self.assertEqual(frac.invite_token, result['token'])

    def test_get_invite_info_public(self):
        """Public endpoint returns invite info without auth."""
        from geo.endpoints.condominium import get_invite_info

        frac = self.fractions[0]
        frac.invite_token = 'public-test-token'
        frac.save(update_fields=['invite_token'])

        request = _make_anon_request(self.factory)
        result = get_invite_info(request, 'public-test-token')

        self.assertEqual(result['fraction_identifier'], '1-A')
        self.assertEqual(result['condominium_name'], self.est.name)
        self.assertEqual(result['condominium_slug'], self.est.slug)
        self.assertIn('address', result)

    def test_get_invite_info_invalid_token(self):
        """Invalid token → 404."""
        from geo.endpoints.condominium import get_invite_info

        request = _make_anon_request(self.factory)

        with self.assertRaises(Http404):
            get_invite_info(request, 'nonexistent-token')

    def test_accept_invite_success(self):
        """Accept invite links profile to fraction and creates membership."""
        from geo.endpoints.condominium import accept_invite

        frac = self.fractions[1]  # 1-B, vacant
        frac.invite_token = 'accept-me-token'
        frac.save(update_fields=['invite_token'])

        request = _make_auth_request(self.factory, self.bob_acc, self.bob, 'post')
        result = accept_invite(request, 'accept-me-token')

        self.assertTrue(result['ok'])
        self.assertEqual(result['condominium_slug'], self.est.slug)
        self.assertEqual(result['fraction_identifier'], '1-B')

        # Verify DB state
        frac.refresh_from_db()
        self.assertEqual(frac.resident_id, self.bob.id)
        self.assertIsNone(frac.invite_token)  # Token consumed

        # Membership created
        self.assertTrue(
            EstablishmentMembership.objects.filter(
                profile=self.bob, establishment=self.est
            ).exists()
        )

    def test_accept_invite_already_occupied(self):
        """Accept invite on fraction that already has resident → 400."""
        from geo.endpoints.condominium import accept_invite

        frac = self.fractions[0]
        frac.resident = self.alice
        frac.invite_token = 'occupied-token'
        frac.save(update_fields=['resident', 'invite_token'])

        request = _make_auth_request(self.factory, self.bob_acc, self.bob, 'post')

        with self.assertRaises(HttpError) as ctx:
            accept_invite(request, 'occupied-token')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_non_admin_cannot_generate_invite(self):
        """Regular member cannot generate invite → 403."""
        from geo.endpoints.condominium import generate_invite

        EstablishmentMembership.objects.create(
            profile=self.bob, establishment=self.est, role='MEMBER',
        )
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, 'post')

        with self.assertRaises(HttpError) as ctx:
            generate_invite(request, self.est.slug, self.fractions[0].id)
        self.assertEqual(ctx.exception.status_code, 403)


# ===========================================================================
# Quota Payment Tests
# ===========================================================================

class QuotaListTest(TestCase):
    """Test GET /condominiums/{slug}/quotas/ endpoint."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, 'bob')
        self.charlie_acc = _create_account(self.instance, 'charlie')
        self.charlie = _create_profile(self.charlie_acc, self.instance, 'charlie')

        self.est, self.fractions = _create_condominium(self.alice)
        # Assign bob as resident of 1-A
        self.fractions[0].resident = self.bob
        self.fractions[0].save(update_fields=['resident'])

    def test_member_sees_quota_overview(self):
        """Member sees quotas proportional to permilagem."""
        from geo.endpoints.condominium import list_quotas

        request = _make_auth_request(self.factory, self.alice_acc, self.alice)
        result = list_quotas(request, self.est.slug, month='2026-03')

        self.assertEqual(len(result.items), 3)
        # Budget=500, 1-A permilagem=400 → quota=200.00
        frac_a = next(q for q in result.items if q.identifier == '1-A')
        self.assertEqual(frac_a.expected_quota, Decimal('200.00'))
        self.assertFalse(frac_a.paid)

    def test_quota_with_payment_shows_paid(self):
        """Quota with recorded payment shows paid=True."""
        from geo.endpoints.condominium import list_quotas

        QuotaPayment.objects.create(
            fraction=self.fractions[0],
            month='2026-03',
            amount=Decimal('200.00'),
            paid_at=timezone.now(),
            confirmed_by=self.alice,
        )

        request = _make_auth_request(self.factory, self.alice_acc, self.alice)
        result = list_quotas(request, self.est.slug, month='2026-03')

        frac_a = next(q for q in result.items if q.identifier == '1-A')
        self.assertTrue(frac_a.paid)
        self.assertIsNotNone(frac_a.payment)
        self.assertEqual(frac_a.payment.amount, Decimal('200.00'))

    def test_outsider_cannot_list_quotas(self):
        """Non-member gets 403."""
        from geo.endpoints.condominium import list_quotas

        request = _make_auth_request(self.factory, self.charlie_acc, self.charlie)

        with self.assertRaises(HttpError) as ctx:
            list_quotas(request, self.est.slug)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_default_month_is_current(self):
        """When no month param, uses current month."""
        from geo.endpoints.condominium import list_quotas

        request = _make_auth_request(self.factory, self.alice_acc, self.alice)
        result = list_quotas(request, self.est.slug)

        self.assertEqual(len(result.items), 3)
        # All should be unpaid (no payments exist)
        for q in result.items:
            self.assertFalse(q.paid)


# ===========================================================================
# Financial Summary Tests
# ===========================================================================

class FinancialSummaryTest(TestCase):
    """Test GET /condominiums/{slug}/financial-summary/ endpoint."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, 'bob')
        self.charlie_acc = _create_account(self.instance, 'charlie')
        self.charlie = _create_profile(self.charlie_acc, self.instance, 'charlie')

        self.est, self.fractions = _create_condominium(self.alice)
        CondominiumService.create_default_budget_categories(self.est)

    def test_member_sees_summary(self):
        """Member sees basic financial summary."""
        from geo.endpoints.condominium import financial_summary

        request = _make_auth_request(self.factory, self.alice_acc, self.alice)
        result = financial_summary(request, self.est.slug)

        self.assertEqual(result.year, timezone.now().year)
        self.assertEqual(result.monthly_budget, Decimal('500.00'))
        self.assertEqual(result.annual_budget, Decimal('6000.00'))
        self.assertEqual(result.fractions_total, 3)
        # 6 default categories from create_default_budget_categories
        self.assertEqual(len(result.categories), 6)

    def test_outsider_cannot_access(self):
        """Non-member, non-staff gets 403."""
        from geo.endpoints.condominium import financial_summary

        request = _make_auth_request(self.factory, self.charlie_acc, self.charlie)
        with self.assertRaises(HttpError) as ctx:
            financial_summary(request, self.est.slug)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_staff_non_member_can_access(self):
        """Staff account bypasses membership requirement."""
        from geo.endpoints.condominium import financial_summary

        self.charlie_acc.is_staff = True
        self.charlie_acc.save(update_fields=['is_staff'])
        request = _make_auth_request(self.factory, self.charlie_acc, self.charlie)
        result = financial_summary(request, self.est.slug)

        self.assertEqual(result.fractions_total, 3)

    def test_collection_rate_with_payments(self):
        """Collection rate reflects recorded payments for the current year."""
        from geo.endpoints.condominium import financial_summary

        # Use a past month of the current year so it's captured in YTD
        now = timezone.now()
        last_month = now.month - 1 if now.month > 1 else 1
        month_str = f"{now.year:04d}-{last_month:02d}"

        QuotaPayment.objects.create(
            fraction=self.fractions[0],
            month=month_str,
            amount=Decimal('200.00'),
            paid_at=now,
            confirmed_by=self.alice,
        )

        request = _make_auth_request(self.factory, self.alice_acc, self.alice)
        result = financial_summary(request, self.est.slug)

        self.assertEqual(result.collected_ytd, Decimal('200.00'))
        # expected_ytd = 500 * months_elapsed; must be >= 500 so rate < 1
        self.assertGreater(result.expected_ytd, Decimal('0'))
        self.assertLess(result.collection_rate, Decimal('1'))
        self.assertEqual(
            result.outstanding_balance,
            result.expected_ytd - result.collected_ytd,
        )

    def test_zero_budget_yields_zero_rate(self):
        """monthly_budget=0 → collection_rate=0, no division error."""
        from geo.endpoints.condominium import financial_summary

        self.est.attributes['monthly_budget'] = '0'
        self.est.save(update_fields=['attributes'])

        request = _make_auth_request(self.factory, self.alice_acc, self.alice)
        result = financial_summary(request, self.est.slug)

        self.assertEqual(result.monthly_budget, Decimal('0.00'))
        self.assertEqual(result.annual_budget, Decimal('0.00'))
        self.assertEqual(result.expected_ytd, Decimal('0.00'))
        self.assertEqual(result.collection_rate, Decimal('0'))

    def test_past_year_uses_full_12_months(self):
        """For a past year, months_elapsed=12."""
        from geo.endpoints.condominium import financial_summary

        past_year = timezone.now().year - 1
        request = _make_auth_request(self.factory, self.alice_acc, self.alice)
        result = financial_summary(request, self.est.slug, year=past_year)

        self.assertEqual(result.year, past_year)
        self.assertEqual(result.months_elapsed, 12)
        self.assertEqual(result.expected_ytd, Decimal('6000.00'))
        # Current month snapshot is zero when looking at a past year
        self.assertEqual(result.current_month_expected, Decimal('0.00'))
        self.assertEqual(result.fractions_paid_current, 0)

    def test_categories_sum_matches_annual_budget(self):
        """Equal-split fallback: sum of category annual_amount ≈ annual_budget."""
        from geo.endpoints.condominium import financial_summary

        request = _make_auth_request(self.factory, self.alice_acc, self.alice)
        result = financial_summary(request, self.est.slug)

        total_from_categories = sum((c.annual_amount for c in result.categories), Decimal('0'))
        # With 6 categories and 6000 annual, 6000/6=1000 each → sum exactly 6000
        self.assertEqual(total_from_categories, result.annual_budget)


class QuotaPaymentRecordTest(TestCase):
    """Test POST /condominiums/{slug}/quotas/ endpoint."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, 'bob')

        self.est, self.fractions = _create_condominium(self.alice)

    def test_record_payment_success(self):
        """Admin records a quota payment."""
        from geo.endpoints.condominium import record_payment, QuotaPaymentInput

        data = QuotaPaymentInput(
            fraction_id=self.fractions[0].id,
            month='2026-03',
            amount=Decimal('200.00'),
            notes='Bank transfer ref 12345',
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'post')
        result = record_payment(request, self.est.slug, data)

        self.assertEqual(result.object_type, 'quota_payment')
        self.assertEqual(result.amount, Decimal('200.00'))
        self.assertEqual(result.month, '2026-03')
        self.assertIsNotNone(result.paid_at)
        self.assertEqual(result.notes, 'Bank transfer ref 12345')

    def test_record_payment_idempotent(self):
        """Recording same fraction+month updates existing payment."""
        from geo.endpoints.condominium import record_payment, QuotaPaymentInput

        # First payment
        data1 = QuotaPaymentInput(
            fraction_id=self.fractions[0].id,
            month='2026-03',
            amount=Decimal('200.00'),
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'post')
        result1 = record_payment(request, self.est.slug, data1)

        # Second payment same month — should update
        data2 = QuotaPaymentInput(
            fraction_id=self.fractions[0].id,
            month='2026-03',
            amount=Decimal('250.00'),
            notes='Corrected amount',
        )
        request2 = _make_auth_request(self.factory, self.alice_acc, self.alice, 'post')
        result2 = record_payment(request, self.est.slug, data2)

        self.assertEqual(result2.amount, Decimal('250.00'))
        self.assertEqual(result2.notes, 'Corrected amount')
        # Only 1 payment record in DB
        self.assertEqual(
            QuotaPayment.objects.filter(fraction=self.fractions[0], month='2026-03').count(),
            1,
        )

    def test_non_admin_cannot_record_payment(self):
        """Member cannot record payments → 403."""
        from geo.endpoints.condominium import record_payment, QuotaPaymentInput

        EstablishmentMembership.objects.create(
            profile=self.bob, establishment=self.est, role='MEMBER',
        )
        data = QuotaPaymentInput(
            fraction_id=self.fractions[0].id,
            month='2026-03',
            amount=Decimal('200.00'),
        )
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, 'post')

        with self.assertRaises(HttpError) as ctx:
            record_payment(request, self.est.slug, data)
        self.assertEqual(ctx.exception.status_code, 403)


# ===========================================================================
# Assembly (Weighted Poll) Tests
# ===========================================================================

class AssemblyCreateTest(TestCase):
    """Test POST /condominiums/{slug}/assembly/ endpoint."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, 'bob')

        self.est, self.fractions = _create_condominium(self.alice)
        # Assign residents as owners for voting eligibility
        self.fractions[0].resident = self.alice
        self.fractions[0].is_owner = True
        self.fractions[0].save(update_fields=['resident', 'is_owner'])
        self.fractions[1].resident = self.bob
        self.fractions[1].is_owner = True
        self.fractions[1].save(update_fields=['resident', 'is_owner'])

    def test_create_assembly_success(self):
        """Admin creates weighted assembly poll."""
        from geo.endpoints.condominium import create_assembly, AssemblyInput
        from governance.models import Poll, PollOption, PollEligibleVoter

        data = AssemblyInput(
            title='Approve budget 2026',
            description='Annual budget proposal',
            options=['Approve', 'Reject', 'Abstain'],
            quorum_type='simple_majority',
            ends_at=timezone.now() + timedelta(days=7),
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'post')
        result = create_assembly(request, self.est.slug, data)

        self.assertEqual(result['object_type'], 'poll')
        self.assertEqual(result['title'], 'Approve budget 2026')
        self.assertEqual(result['voter_count'], 2)  # alice + bob

        # Verify poll in DB
        poll = Poll.objects.get(id=result['poll_id'])
        self.assertTrue(poll.use_weights)
        self.assertEqual(poll.weight_source, 'ownership_shares')
        self.assertEqual(poll.status, 'active')
        self.assertEqual(PollOption.objects.filter(poll=poll).count(), 3)

        # Verify voter weights match permilagem
        alice_voter = PollEligibleVoter.objects.get(poll=poll, profile=self.alice)
        self.assertEqual(alice_voter.weight, Decimal('400.000'))
        bob_voter = PollEligibleVoter.objects.get(poll=poll, profile=self.bob)
        self.assertEqual(bob_voter.weight, Decimal('350.000'))

    def test_create_assembly_two_thirds_quorum(self):
        """Assembly with two_thirds quorum type sets 67%."""
        from geo.endpoints.condominium import create_assembly, AssemblyInput
        from governance.models import Poll

        data = AssemblyInput(
            title='Major renovation',
            options=['Yes', 'No'],
            quorum_type='two_thirds',
            ends_at=timezone.now() + timedelta(days=3),
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'post')
        result = create_assembly(request, self.est.slug, data)

        poll = Poll.objects.get(id=result['poll_id'])
        self.assertEqual(poll.quorum_percent, 67)

    def test_multi_fraction_owner_weight_summed(self):
        """Owner with 2 fractions gets summed weight."""
        from geo.endpoints.condominium import create_assembly, AssemblyInput
        from governance.models import PollEligibleVoter

        # Assign alice also as owner of Gar-1
        self.fractions[2].resident = self.alice
        self.fractions[2].is_owner = True
        self.fractions[2].save(update_fields=['resident', 'is_owner'])

        data = AssemblyInput(
            title='Multi-fraction test',
            options=['A', 'B'],
            ends_at=timezone.now() + timedelta(days=1),
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'post')
        result = create_assembly(request, self.est.slug, data)

        # Alice: 400 (1-A) + 250 (Gar-1) = 650
        from governance.models import Poll
        poll = Poll.objects.get(id=result['poll_id'])
        alice_voter = PollEligibleVoter.objects.get(poll=poll, profile=self.alice)
        self.assertEqual(alice_voter.weight, Decimal('650.000'))

    def test_non_admin_cannot_create_assembly(self):
        """Member cannot create assembly → 403."""
        from geo.endpoints.condominium import create_assembly, AssemblyInput

        EstablishmentMembership.objects.create(
            profile=self.bob, establishment=self.est, role='MEMBER',
        )
        data = AssemblyInput(
            title='Unauthorized',
            options=['A', 'B'],
            ends_at=timezone.now() + timedelta(days=1),
        )
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_assembly(request, self.est.slug, data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_tenant_not_eligible_voter(self):
        """Tenant (is_owner=False) is NOT added as poll voter."""
        from geo.endpoints.condominium import create_assembly, AssemblyInput
        from governance.models import Poll, PollEligibleVoter

        # Make bob a tenant, not owner
        self.fractions[1].is_owner = False
        self.fractions[1].save(update_fields=['is_owner'])

        data = AssemblyInput(
            title='Owners only',
            options=['Yes', 'No'],
            ends_at=timezone.now() + timedelta(days=1),
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'post')
        result = create_assembly(request, self.est.slug, data)

        self.assertEqual(result['voter_count'], 1)  # Only alice
        poll = Poll.objects.get(id=result['poll_id'])
        self.assertFalse(PollEligibleVoter.objects.filter(poll=poll, profile=self.bob).exists())


# ===========================================================================
# Service Layer Tests
# ===========================================================================

class CondominiumServiceTest(TestCase):
    """Test CondominiumService methods."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)

    def test_validate_permilagem_exact_1000(self):
        """Exact 1000 sum passes."""
        fractions = [
            {'permilagem': Decimal('500.000')},
            {'permilagem': Decimal('300.000')},
            {'permilagem': Decimal('200.000')},
        ]
        valid, err = CondominiumService.validate_permilagem_total(fractions)
        self.assertTrue(valid)
        self.assertEqual(err, '')

    def test_validate_permilagem_under_1000(self):
        """Under 1000 fails."""
        fractions = [
            {'permilagem': Decimal('500.000')},
            {'permilagem': Decimal('200.000')},
        ]
        valid, err = CondominiumService.validate_permilagem_total(fractions)
        self.assertFalse(valid)
        self.assertIn('700', err)

    def test_validate_permilagem_over_1000(self):
        """Over 1000 fails."""
        fractions = [
            {'permilagem': Decimal('600.000')},
            {'permilagem': Decimal('500.000')},
        ]
        valid, err = CondominiumService.validate_permilagem_total(fractions)
        self.assertFalse(valid)
        self.assertIn('1100', err)

    def test_calculate_monthly_quotas(self):
        """Monthly quotas proportional to permilagem."""
        est, fractions = _create_condominium(self.alice)
        quotas = CondominiumService.calculate_monthly_quotas(est, Decimal('500.00'))

        self.assertEqual(len(quotas), 3)
        # 1-A: 400/1000 * 500 = 200.00
        qa = next(q for q in quotas if q['identifier'] == '1-A')
        self.assertEqual(qa['quota'], Decimal('200.00'))
        # 1-B: 350/1000 * 500 = 175.00
        qb = next(q for q in quotas if q['identifier'] == '1-B')
        self.assertEqual(qb['quota'], Decimal('175.00'))
        # Gar-1: 250/1000 * 500 = 125.00
        qg = next(q for q in quotas if q['identifier'] == 'Gar-1')
        self.assertEqual(qg['quota'], Decimal('125.00'))

    def test_calculate_monthly_quotas_zero_budget(self):
        """Zero budget → all quotas zero."""
        est, _ = _create_condominium(self.alice)
        quotas = CondominiumService.calculate_monthly_quotas(est, Decimal('0'))

        for q in quotas:
            self.assertEqual(q['quota'], Decimal('0.00'))

    def test_create_default_budget_categories(self):
        """Creates 6 default budget categories."""
        from treasury.models import BudgetCategory

        est, _ = _create_condominium(self.alice)
        count = CondominiumService.create_default_budget_categories(est)

        self.assertEqual(count, 6)
        self.assertEqual(BudgetCategory.objects.filter(establishment=est).count(), 6)
        slugs = set(BudgetCategory.objects.filter(establishment=est).values_list('slug', flat=True))
        self.assertIn('quotas-ordinarias', slugs)
        self.assertIn('fundo-reserva', slugs)

    def test_create_default_budget_categories_idempotent(self):
        """Second call doesn't duplicate categories."""
        from treasury.models import BudgetCategory

        est, _ = _create_condominium(self.alice)
        CondominiumService.create_default_budget_categories(est)
        count2 = CondominiumService.create_default_budget_categories(est)

        self.assertEqual(count2, 0)
        self.assertEqual(BudgetCategory.objects.filter(establishment=est).count(), 6)

    def test_generate_invite_token_uniqueness(self):
        """Generated tokens are unique."""
        tokens = {CondominiumService.generate_invite_token() for _ in range(100)}
        self.assertEqual(len(tokens), 100)

    def test_setup_poll_voters(self):
        """Setup poll voters from fraction owners."""
        from governance.models import Poll, PollContext, PollEligibleVoter

        est, fractions = _create_condominium(self.alice)
        bob_acc = _create_account(self.instance, 'bob')
        bob = _create_profile(bob_acc, self.instance, 'bob')

        fractions[0].resident = self.alice
        fractions[0].is_owner = True
        fractions[0].save(update_fields=['resident', 'is_owner'])
        fractions[1].resident = bob
        fractions[1].is_owner = True
        fractions[1].save(update_fields=['resident', 'is_owner'])
        # fractions[2] has no resident

        context = PollContext.objects.create(
            context_type='tszh', context_id=est.id, created_by=self.alice,
        )
        poll = Poll.objects.create(
            context=context,
            title='Test',
            created_by=self.alice,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(days=1),
            use_weights=True,
            status='active',
        )

        count = CondominiumService.setup_poll_voters(poll, est)

        self.assertEqual(count, 2)
        self.assertEqual(PollEligibleVoter.objects.filter(poll=poll).count(), 2)


# ===========================================================================
# Admin Role via Membership Tests
# ===========================================================================

class AdminMembershipTest(TestCase):
    """Test that ADMIN role (not just OWNER) can perform admin actions."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.admin_acc = _create_account(self.instance, 'admin_user')
        self.admin_profile = _create_profile(self.admin_acc, self.instance, 'admin_user')

        self.est, self.fractions = _create_condominium(self.alice)
        # Make admin_user an ADMIN member
        EstablishmentMembership.objects.create(
            profile=self.admin_profile, establishment=self.est, role='ADMIN',
        )

    def test_admin_can_add_fraction(self):
        """ADMIN role member can add fractions."""
        from geo.endpoints.condominium import add_fraction, FractionInput

        data = FractionInput(identifier='3-A', permilagem=Decimal('50.000'))
        request = _make_auth_request(self.factory, self.admin_acc, self.admin_profile, 'post')
        result = add_fraction(request, self.est.slug, data)

        self.assertEqual(result.identifier, '3-A')

    def test_admin_can_record_payment(self):
        """ADMIN role member can record payments."""
        from geo.endpoints.condominium import record_payment, QuotaPaymentInput

        data = QuotaPaymentInput(
            fraction_id=self.fractions[0].id,
            month='2026-03',
            amount=Decimal('200.00'),
        )
        request = _make_auth_request(self.factory, self.admin_acc, self.admin_profile, 'post')
        result = record_payment(request, self.est.slug, data)

        self.assertEqual(result.amount, Decimal('200.00'))

    def test_admin_can_generate_invite(self):
        """ADMIN role member can generate invites."""
        from geo.endpoints.condominium import generate_invite

        request = _make_auth_request(self.factory, self.admin_acc, self.admin_profile, 'post')
        result = generate_invite(request, self.est.slug, self.fractions[0].id)

        self.assertIn('token', result)
