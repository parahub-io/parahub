"""
Tests for geo endpoints: establishments, membership, reviews, search,
buildings, treasurer/auditor management, events.

Tests invariants that must never break:
- WoT 3+ requirement for creating establishments, buildings, reviews, events
- Owner-only update/delete of establishments
- Membership join/leave lifecycle
- Review uniqueness (one per author per establishment)
- Owner reply on reviews (establishment owner only)
- ULID and slug resolution for establishment lookups
- Treasurer/auditor management (OWNER/ADMIN only)
- Address and geo-based search filters
- Event lifecycle: create → join/leave → cancel, capacity enforcement
- Organizer-only event update/cancel permissions
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime

from django.test import TestCase, SimpleTestCase, RequestFactory
from django.contrib.gis.geos import Point
from django.contrib.sessions.backends.db import SessionStore
from ninja.errors import HttpError

from identity.models import Account, Profile, Verification
from core.models import Instance
from geo.models import (
    WorldObject, Establishment, EstablishmentMembership,
    EstablishmentReview,
)


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
    """Build an unauthenticated request (mimics OptionalProfileAuth with no user)."""
    fn = getattr(factory, method)
    request = fn(path)
    request.auth_profile = None
    return request


def _add_verifications(profile, count=3):
    """Add WoT verifications to a profile."""
    instance = profile.instance
    verifiers = []
    for i in range(count):
        acc = _create_account(instance, f'verifier{i}_{profile.local_name}')
        vp = _create_profile(acc, instance, local_name=f'verifier{i}_{profile.local_name}')
        verifiers.append(vp)
        Verification.objects.create(
            verifier=vp,
            verified_profile=profile,
            is_active=True,
        )
    return verifiers


def _create_building(location=None, **kwargs):
    """Create a world object (building) for testing."""
    defaults = {
        'location': location or Point(-9.13706, 38.71147, srid=4326),
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


def _create_establishment(owner, building=None, **kwargs):
    """Create an establishment for testing."""
    defaults = {
        'name': 'Test Café',
        'slug': 'test-cafe',
        'description': 'A test café',
        'is_active': True,
    }
    defaults.update(kwargs)
    return Establishment.objects.create(owner=owner, world_object=building, **defaults)


# ===========================================================================
# Building Endpoints
# ===========================================================================

class BuildingCreateTest(TestCase):
    """Test building creation: WoT requirements, get_or_create on osm_way_id."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance, is_verified_wot=True)
        self.factory = RequestFactory()

    def test_create_building_wot_verified(self):
        """User with WoT 3+ can create a building."""
        from geo.endpoints.buildings import create_building, BuildingInput, LocationInput

        _add_verifications(self.profile, 3)
        payload = BuildingInput(
            osm_way_id=12345,
            location=LocationInput(latitude=38.71, longitude=-9.13),
            country='PT',
            city='Lisboa',
            street='Rua Augusta',
            full_address='Rua Augusta, Lisboa',
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        response = create_building(request, payload)

        self.assertEqual(response.object_type, 'world_object')
        self.assertEqual(response.city, 'Lisboa')
        self.assertEqual(WorldObject.objects.count(), 1)

    def test_create_building_wot_insufficient_denied(self):
        """User with <3 verifications is denied."""
        from geo.endpoints.buildings import create_building, BuildingInput, LocationInput

        _add_verifications(self.profile, 2)
        payload = BuildingInput(
            osm_way_id=99999,
            location=LocationInput(latitude=38.71, longitude=-9.13),
            country='PT',
            city='Lisboa',
            full_address='Lisboa',
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_building(request, payload)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_create_building_admin_bypass_wot(self):
        """Superuser bypasses WoT check."""
        from geo.endpoints.buildings import create_building, BuildingInput, LocationInput

        self.account.is_superuser = True
        self.account.save()

        payload = BuildingInput(
            osm_way_id=54321,
            location=LocationInput(latitude=38.71, longitude=-9.13),
            country='PT',
            city='Porto',
            full_address='Porto, PT',
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        response = create_building(request, payload)
        self.assertEqual(response.city, 'Porto')

    def test_create_building_deduplicates_osm_way_id(self):
        """Building with same osm_way_id returns existing building."""
        from geo.endpoints.buildings import create_building, BuildingInput, LocationInput

        _add_verifications(self.profile, 3)
        payload = BuildingInput(
            osm_way_id=77777,
            location=LocationInput(latitude=38.71, longitude=-9.13),
            country='PT',
            city='Lisboa',
            full_address='Lisboa',
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        create_building(request, payload)
        # Create again with same osm_way_id
        response = create_building(request, payload)
        self.assertEqual(WorldObject.objects.filter(xeno_source='osm', xeno_id='way/77777').count(), 1)

    def test_get_building(self):
        """Public endpoint returns building details."""
        from geo.endpoints.buildings import get_building

        building = _create_building(xeno_source='osm', xeno_id='way/111')
        request = self.factory.get(f'/api/v1/geo/buildings/{building.id}/')
        response = get_building(request, building.id)

        self.assertEqual(response.id, building.id)
        self.assertEqual(response.object_type, 'world_object')
        self.assertEqual(response.full_address, 'Rua Augusta 10, Lisboa, PT')

    def test_get_building_establishments(self):
        """List establishments in a building."""
        from geo.endpoints.buildings import get_building_establishments

        building = _create_building()
        _create_establishment(self.profile, building, name='Café A', slug='cafe-a')
        _create_establishment(self.profile, building, name='Café B', slug='cafe-b')
        _create_establishment(self.profile, building, name='Inactive', slug='inactive', is_active=False)

        request = self.factory.get(f'/api/v1/geo/buildings/{building.id}/establishments/')
        response = get_building_establishments(request, building.id)

        self.assertEqual(len(response), 2)
        names = [e.name for e in response]
        self.assertIn('Café A', names)
        self.assertIn('Café B', names)
        self.assertNotIn('Inactive', names)


# ===========================================================================
# Establishment CRUD
# ===========================================================================

class EstablishmentCreateTest(TestCase):
    """Test establishment creation: WoT gate, building linkage."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance, is_verified_wot=True)
        self.factory = RequestFactory()

    def test_create_establishment_wot_verified(self):
        """User with WoT 3+ can create an establishment."""
        from geo.endpoints.buildings import create_establishment, EstablishmentInput

        _add_verifications(self.profile, 3)
        payload = EstablishmentInput(name='My Café', slug='my-cafe')
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        response = create_establishment(request, payload)

        self.assertEqual(response.object_type, 'establishment')
        self.assertEqual(response.name, 'My Café')
        self.assertEqual(response.owner_id, self.profile.id)
        self.assertEqual(Establishment.objects.count(), 1)

    def test_create_establishment_wot_insufficient_denied(self):
        """User with <3 verifications is denied."""
        from geo.endpoints.buildings import create_establishment, EstablishmentInput

        _add_verifications(self.profile, 2)
        payload = EstablishmentInput(name='Blocked Café')
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_establishment(request, payload)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_create_establishment_admin_bypass_wot(self):
        """Superuser bypasses WoT check."""
        from geo.endpoints.buildings import create_establishment, EstablishmentInput

        self.account.is_superuser = True
        self.account.save()

        payload = EstablishmentInput(name='Admin Café')
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        response = create_establishment(request, payload)
        self.assertEqual(response.name, 'Admin Café')

    def test_create_establishment_with_building_updates_counter(self):
        """Creating in a building increments establishments_count."""
        from geo.endpoints.buildings import create_establishment, EstablishmentInput

        _add_verifications(self.profile, 3)
        building = _create_building()
        self.assertEqual(building.establishments_count, 0)

        payload = EstablishmentInput(name='In Building', world_object_id=building.id)
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        create_establishment(request, payload)

        building.refresh_from_db()
        self.assertEqual(building.establishments_count, 1)

    def test_create_establishment_with_location(self):
        """Establishment can have a direct location (no building)."""
        from geo.endpoints.buildings import create_establishment, EstablishmentInput, LocationInput

        _add_verifications(self.profile, 3)
        payload = EstablishmentInput(
            name='Outdoor Kiosk',
            location=LocationInput(latitude=38.72, longitude=-9.14),
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        response = create_establishment(request, payload)

        self.assertIsNotNone(response.location)
        self.assertAlmostEqual(response.location['lat'], 38.72, places=1)

    def test_create_establishment_foundation_member_bypass(self):
        """Foundation member bypasses WoT check."""
        from geo.endpoints.buildings import create_establishment, EstablishmentInput

        # No verifications needed
        payload = EstablishmentInput(name='Foundation Café')
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')

        with patch.object(Profile, 'is_foundation_member', return_value=True):
            response = create_establishment(request, payload)
        self.assertEqual(response.name, 'Foundation Café')


class EstablishmentDetailTest(TestCase):
    """Test establishment detail: ULID/slug resolution, view counter."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        self.building = _create_building()
        self.establishment = _create_establishment(
            self.profile, self.building,
            name='Detail Café', slug='detail-cafe',
        )
        self.factory = RequestFactory()

    def test_get_by_ulid(self):
        """Get establishment by ULID."""
        from geo.endpoints.buildings import get_establishment

        request = _make_anon_request(self.factory)
        response = get_establishment(request, self.establishment.id)

        self.assertEqual(response.id, self.establishment.id)
        self.assertEqual(response.name, 'Detail Café')
        self.assertEqual(response.object_type, 'establishment')

    def test_get_by_slug(self):
        """Get establishment by slug."""
        from geo.endpoints.buildings import get_establishment

        request = _make_anon_request(self.factory)
        response = get_establishment(request, 'detail-cafe')
        self.assertEqual(response.id, self.establishment.id)

    def test_get_increments_views(self):
        """Detail endpoint increments view counter."""
        from geo.endpoints.buildings import get_establishment

        self.assertEqual(self.establishment.views_count, 0)

        request = _make_anon_request(self.factory)
        get_establishment(request, self.establishment.id)

        self.establishment.refresh_from_db()
        self.assertEqual(self.establishment.views_count, 1)

    def test_get_inactive_returns_404(self):
        """Inactive establishment returns 404."""
        from geo.endpoints.buildings import get_establishment
        from django.http import Http404

        self.establishment.is_active = False
        self.establishment.save(update_fields=['is_active'])

        request = _make_anon_request(self.factory)
        with self.assertRaises(Http404):
            get_establishment(request, self.establishment.id)

    def test_get_returns_is_member_for_authenticated(self):
        """Authenticated member sees is_member=True."""
        from geo.endpoints.buildings import get_establishment

        EstablishmentMembership.objects.create(
            profile=self.profile,
            establishment=self.establishment,
            role='MEMBER',
        )

        request = _make_auth_request(self.factory, self.account, self.profile)
        response = get_establishment(request, self.establishment.id)
        self.assertTrue(response.is_member)

    def test_get_returns_is_member_false_for_nonmember(self):
        """Authenticated non-member sees is_member=False."""
        from geo.endpoints.buildings import get_establishment

        request = _make_auth_request(self.factory, self.account, self.profile)
        response = get_establishment(request, self.establishment.id)
        self.assertFalse(response.is_member)

    def test_get_includes_building_data(self):
        """Response includes world_object details when linked."""
        from geo.endpoints.buildings import get_establishment

        request = _make_anon_request(self.factory)
        response = get_establishment(request, self.establishment.id)

        self.assertIsNotNone(response.world_object)
        self.assertEqual(response.world_object.city, 'Lisboa')


class EstablishmentUpdateTest(TestCase):
    """Test establishment update: owner-only access."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, local_name='bob')
        self.establishment = _create_establishment(self.alice, name='Original', slug='original')
        self.factory = RequestFactory()

    def test_owner_can_update(self):
        """Owner can update establishment."""
        from geo.endpoints.buildings import update_establishment, EstablishmentInput

        payload = EstablishmentInput(name='Updated Name')
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'put')
        response = update_establishment(request, self.establishment.id, payload)

        self.assertEqual(response.name, 'Updated Name')
        self.establishment.refresh_from_db()
        self.assertEqual(self.establishment.name, 'Updated Name')

    def test_non_owner_cannot_update(self):
        """Non-owner is denied update."""
        from geo.endpoints.buildings import update_establishment, EstablishmentInput

        payload = EstablishmentInput(name='Hacked')
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, 'put')
        with self.assertRaises(HttpError) as ctx:
            update_establishment(request, self.establishment.id, payload)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_update_by_slug(self):
        """Owner can update by slug."""
        from geo.endpoints.buildings import update_establishment, EstablishmentInput

        payload = EstablishmentInput(name='Slug Update')
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'put')
        response = update_establishment(request, 'original', payload)
        self.assertEqual(response.name, 'Slug Update')


class EstablishmentDeleteTest(TestCase):
    """Test establishment soft-delete: owner-only, building counter update."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, local_name='bob')
        self.building = _create_building()
        self.establishment = _create_establishment(self.alice, self.building)
        # Fix building counter
        self.building.establishments_count = 1
        self.building.save(update_fields=['establishments_count'])
        self.factory = RequestFactory()

    def test_owner_can_delete(self):
        """Owner can soft-delete establishment."""
        from geo.endpoints.buildings import delete_establishment

        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'delete')
        delete_establishment(request, self.establishment.id)

        self.establishment.refresh_from_db()
        self.assertFalse(self.establishment.is_active)

    def test_non_owner_cannot_delete(self):
        """Non-owner is denied delete."""
        from geo.endpoints.buildings import delete_establishment

        request = _make_auth_request(self.factory, self.bob_acc, self.bob, 'delete')
        with self.assertRaises(HttpError) as ctx:
            delete_establishment(request, self.establishment.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_delete_updates_building_counter(self):
        """Soft-deleting decrements building's establishments_count."""
        from geo.endpoints.buildings import delete_establishment

        request = _make_auth_request(self.factory, self.alice_acc, self.alice, 'delete')
        delete_establishment(request, self.establishment.id)

        self.building.refresh_from_db()
        self.assertEqual(self.building.establishments_count, 0)


# ===========================================================================
# Establishment List & Search
# ===========================================================================

class EstablishmentListTest(TestCase):
    """Test listing/search: text search, address filters, geo search."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        self.factory = RequestFactory()

        # Buildings in different cities
        self.building_lisbon = _create_building(
            location=Point(-9.13706, 38.71147, srid=4326),
            city='Lisboa', street='Rua Augusta', house_number='10',
            full_address='Rua Augusta 10, Lisboa, PT',
            country='PT',
        )
        self.building_porto = _create_building(
            location=Point(-8.6, 41.15, srid=4326),
            city='Porto', street='Rua Santa Catarina', house_number='5',
            full_address='Rua Santa Catarina 5, Porto, PT',
            country='PT',
        )

        self.est_lisbon = _create_establishment(
            self.profile, self.building_lisbon,
            name='Lisbon Café', slug='lisbon-cafe',
            description='Best coffee in Lisbon',
        )
        self.est_porto = _create_establishment(
            self.profile, self.building_porto,
            name='Porto Wine Bar', slug='porto-wine',
            description='Port wine tasting',
        )
        self.est_online = _create_establishment(
            self.profile, building=None,
            name='Online Shop', slug='online-shop',
            is_online=True,
            organization_type='COMPANY',
        )

    def _get_items(self, result):
        """Extract items from paginated response (HttpResponse or dict)."""
        import json
        from types import SimpleNamespace
        if hasattr(result, 'content'):
            data = json.loads(result.content)
            return [SimpleNamespace(**item) for item in data.get('items', [])]
        if isinstance(result, dict) and 'items' in result:
            return [SimpleNamespace(**item) for item in result['items']]
        return result

    def test_list_returns_active_only(self):
        """Listing returns only active establishments."""
        from geo.endpoints.buildings import list_establishments

        inactive = _create_establishment(
            self.profile, name='Dead', slug='dead', is_active=False,
        )
        request = _make_anon_request(self.factory)
        items = self._get_items(list_establishments(request))
        ids = [e.id for e in items]
        self.assertNotIn(inactive.id, ids)

    def test_search_by_name(self):
        """Text search in name."""
        from geo.endpoints.buildings import list_establishments

        request = _make_anon_request(self.factory)
        items = self._get_items(list_establishments(request, search='Lisbon'))
        names = [e.name for e in items]
        self.assertIn('Lisbon Café', names)
        self.assertNotIn('Porto Wine Bar', names)

    def test_search_by_description(self):
        """Text search in description."""
        from geo.endpoints.buildings import list_establishments

        request = _make_anon_request(self.factory)
        items = self._get_items(list_establishments(request, search='Port wine'))
        names = [e.name for e in items]
        self.assertIn('Porto Wine Bar', names)
        self.assertNotIn('Lisbon Café', names)

    def test_filter_by_city(self):
        """Filter by building city (case-insensitive)."""
        from geo.endpoints.buildings import list_establishments

        request = _make_anon_request(self.factory)
        items = self._get_items(list_establishments(request, city='lisboa'))
        names = [e.name for e in items]
        self.assertIn('Lisbon Café', names)
        self.assertNotIn('Porto Wine Bar', names)

    def test_filter_by_country(self):
        """Filter by building country code."""
        from geo.endpoints.buildings import list_establishments

        request = _make_anon_request(self.factory)
        items = self._get_items(list_establishments(request, country='PT'))
        names = [e.name for e in items]
        # Both Lisbon and Porto are PT, online shop has no building
        self.assertIn('Lisbon Café', names)
        self.assertIn('Porto Wine Bar', names)

    def test_filter_by_street(self):
        """Filter by street name."""
        from geo.endpoints.buildings import list_establishments

        request = _make_anon_request(self.factory)
        items = self._get_items(list_establishments(request, street='Santa Catarina'))
        names = [e.name for e in items]
        self.assertIn('Porto Wine Bar', names)
        self.assertNotIn('Lisbon Café', names)

    def test_filter_by_house_number(self):
        """Filter by house number (exact match)."""
        from geo.endpoints.buildings import list_establishments

        request = _make_anon_request(self.factory)
        items = self._get_items(list_establishments(request, city='Lisboa', house_number='10'))
        names = [e.name for e in items]
        self.assertIn('Lisbon Café', names)

    def test_filter_by_organization_type(self):
        """Filter by organization type."""
        from geo.endpoints.buildings import list_establishments

        request = _make_anon_request(self.factory)
        items = self._get_items(list_establishments(request, organization_type='COMPANY'))
        names = [e.name for e in items]
        self.assertIn('Online Shop', names)
        self.assertNotIn('Lisbon Café', names)

    def test_filter_is_online(self):
        """Filter online-only establishments."""
        from geo.endpoints.buildings import list_establishments

        request = _make_anon_request(self.factory)
        items = self._get_items(list_establishments(request, is_online=True))
        names = [e.name for e in items]
        self.assertIn('Online Shop', names)
        self.assertNotIn('Lisbon Café', names)

    def test_geo_search(self):
        """Geographic search by lat/lon/radius."""
        from geo.endpoints.buildings import list_establishments

        request = _make_anon_request(self.factory)
        # Search near Lisbon (radius 1km should only find Lisbon establishment)
        items = self._get_items(list_establishments(request, lat=38.71, lon=-9.13, radius_km=1.0))
        names = [e.name for e in items]
        self.assertIn('Lisbon Café', names)
        self.assertNotIn('Porto Wine Bar', names)

    def test_my_memberships_filter(self):
        """my_memberships filter returns only establishments user is a member of."""
        from geo.endpoints.buildings import list_establishments

        EstablishmentMembership.objects.create(
            profile=self.profile,
            establishment=self.est_lisbon,
            role='MEMBER',
        )

        request = _make_auth_request(self.factory, self.account, self.profile)
        items = self._get_items(list_establishments(request, my_memberships=True))
        names = [e.name for e in items]
        self.assertIn('Lisbon Café', names)
        self.assertNotIn('Porto Wine Bar', names)


# ===========================================================================
# Membership
# ===========================================================================

class MembershipJoinTest(TestCase):
    """Test join/leave establishment lifecycle."""

    def setUp(self):
        self.instance = _create_instance()
        self.owner_acc = _create_account(self.instance, 'alice')
        self.owner = _create_profile(self.owner_acc, self.instance)
        self.user_acc = _create_account(self.instance, 'bob')
        self.user = _create_profile(self.user_acc, self.instance, local_name='bob')
        self.establishment = _create_establishment(
            self.owner, name='Test Org', slug='test-org',
            organization_type='ASSOCIATION',
        )
        self.factory = RequestFactory()

    def test_join_creates_membership(self):
        """User can join an establishment."""
        from geo.endpoints.buildings import join_establishment, JoinEstablishmentRequest

        data = JoinEstablishmentRequest()
        request = _make_auth_request(self.factory, self.user_acc, self.user, 'post')
        response = join_establishment(request, self.establishment.id, data)

        self.assertEqual(response.role, 'MEMBER')
        self.assertEqual(response.profile_id, self.user.id)
        self.assertTrue(
            EstablishmentMembership.objects.filter(
                profile=self.user, establishment=self.establishment
            ).exists()
        )

    def test_join_duplicate_rejected(self):
        """Cannot join same establishment twice."""
        from geo.endpoints.buildings import join_establishment, JoinEstablishmentRequest

        EstablishmentMembership.objects.create(
            profile=self.user, establishment=self.establishment, role='MEMBER',
        )

        data = JoinEstablishmentRequest()
        request = _make_auth_request(self.factory, self.user_acc, self.user, 'post')
        with self.assertRaises(HttpError) as ctx:
            join_establishment(request, self.establishment.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_join_requires_terms_acceptance(self):
        """Establishment with requires_terms_acceptance blocks join without acceptance."""
        from geo.endpoints.buildings import join_establishment, JoinEstablishmentRequest

        self.establishment.requires_terms_acceptance = True
        self.establishment.save(update_fields=['requires_terms_acceptance'])

        data = JoinEstablishmentRequest(terms_accepted=False)
        request = _make_auth_request(self.factory, self.user_acc, self.user, 'post')
        with self.assertRaises(HttpError) as ctx:
            join_establishment(request, self.establishment.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_join_with_terms_accepted(self):
        """Join succeeds when terms_accepted=True."""
        from geo.endpoints.buildings import join_establishment, JoinEstablishmentRequest

        self.establishment.requires_terms_acceptance = True
        self.establishment.save(update_fields=['requires_terms_acceptance'])

        data = JoinEstablishmentRequest(terms_accepted=True)
        request = _make_auth_request(self.factory, self.user_acc, self.user, 'post')
        response = join_establishment(request, self.establishment.id, data)
        self.assertEqual(response.role, 'MEMBER')

    def test_join_with_membership_level(self):
        """Join with specified membership level."""
        from geo.endpoints.buildings import join_establishment, JoinEstablishmentRequest

        data = JoinEstablishmentRequest(membership_level='efetivo')
        request = _make_auth_request(self.factory, self.user_acc, self.user, 'post')
        response = join_establishment(request, self.establishment.id, data)
        self.assertEqual(response.membership_level, 'efetivo')


class MembershipLeaveTest(TestCase):
    """Test leaving an establishment."""

    def setUp(self):
        self.instance = _create_instance()
        self.owner_acc = _create_account(self.instance, 'alice')
        self.owner = _create_profile(self.owner_acc, self.instance)
        self.user_acc = _create_account(self.instance, 'bob')
        self.user = _create_profile(self.user_acc, self.instance, local_name='bob')
        self.establishment = _create_establishment(self.owner, slug='leave-org')
        self.factory = RequestFactory()

    def test_member_can_leave(self):
        """Member can leave an establishment."""
        from geo.endpoints.buildings import leave_establishment

        EstablishmentMembership.objects.create(
            profile=self.user, establishment=self.establishment, role='MEMBER',
        )

        request = _make_auth_request(self.factory, self.user_acc, self.user, 'post')
        leave_establishment(request, self.establishment.id)

        self.assertFalse(
            EstablishmentMembership.objects.filter(
                profile=self.user, establishment=self.establishment
            ).exists()
        )

    def test_non_member_leave_returns_404(self):
        """Non-member cannot leave."""
        from geo.endpoints.buildings import leave_establishment

        request = _make_auth_request(self.factory, self.user_acc, self.user, 'post')
        with self.assertRaises(HttpError) as ctx:
            leave_establishment(request, self.establishment.id)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_last_owner_cannot_leave(self):
        """Last owner cannot leave."""
        from geo.endpoints.buildings import leave_establishment

        EstablishmentMembership.objects.create(
            profile=self.owner, establishment=self.establishment, role='OWNER',
        )

        request = _make_auth_request(self.factory, self.owner_acc, self.owner, 'post')
        with self.assertRaises(HttpError) as ctx:
            leave_establishment(request, self.establishment.id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('last owner', str(ctx.exception))


class MembershipListTest(TestCase):
    """Test listing members of an establishment."""

    def setUp(self):
        self.instance = _create_instance()
        self.owner_acc = _create_account(self.instance, 'alice')
        self.owner = _create_profile(self.owner_acc, self.instance)
        self.user_acc = _create_account(self.instance, 'bob')
        self.user = _create_profile(self.user_acc, self.instance, local_name='bob')
        self.establishment = _create_establishment(self.owner, slug='members-org')
        self.factory = RequestFactory()

    def test_list_members(self):
        """List returns all members with roles."""
        from geo.endpoints.buildings import list_establishment_members

        EstablishmentMembership.objects.create(
            profile=self.owner, establishment=self.establishment, role='OWNER',
        )
        EstablishmentMembership.objects.create(
            profile=self.user, establishment=self.establishment, role='MEMBER',
        )

        request = self.factory.get('/fake/')
        response = list_establishment_members(request, self.establishment.id)
        self.assertEqual(len(response), 2)
        roles = {m.role for m in response}
        self.assertEqual(roles, {'OWNER', 'MEMBER'})

    def test_list_members_empty(self):
        """No members returns empty list."""
        from geo.endpoints.buildings import list_establishment_members

        request = self.factory.get('/fake/')
        response = list_establishment_members(request, self.establishment.id)
        self.assertEqual(len(response), 0)


# ===========================================================================
# Reviews
# ===========================================================================

class ReviewCreateTest(TestCase):
    """Test review creation: WoT gate, uniqueness constraint."""

    def setUp(self):
        self.instance = _create_instance()
        self.owner_acc = _create_account(self.instance, 'alice')
        self.owner = _create_profile(self.owner_acc, self.instance)
        self.reviewer_acc = _create_account(self.instance, 'bob')
        self.reviewer = _create_profile(self.reviewer_acc, self.instance, local_name='bob')
        self.establishment = _create_establishment(self.owner, slug='reviewed-cafe')
        self.factory = RequestFactory()

    def test_create_review_wot_verified(self):
        """User with WoT 3+ can create a review."""
        from geo.endpoints.buildings import create_establishment_review, ReviewInput

        _add_verifications(self.reviewer, 3)
        payload = ReviewInput(rating=4, text='Great coffee!')
        request = _make_auth_request(self.factory, self.reviewer_acc, self.reviewer, 'post')
        status, response = create_establishment_review(request, self.establishment.id, payload)

        self.assertEqual(status, 201)
        self.assertEqual(response.rating, 4)
        self.assertEqual(response.text, 'Great coffee!')
        self.assertEqual(response.wot_count_snapshot, 3)

    def test_create_review_wot_insufficient_denied(self):
        """User with <3 verifications is denied."""
        from geo.endpoints.buildings import create_establishment_review, ReviewInput

        _add_verifications(self.reviewer, 2)
        payload = ReviewInput(rating=5)
        request = _make_auth_request(self.factory, self.reviewer_acc, self.reviewer, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_establishment_review(request, self.establishment.id, payload)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_create_review_admin_bypass(self):
        """Superuser bypasses WoT check."""
        from geo.endpoints.buildings import create_establishment_review, ReviewInput

        self.reviewer_acc.is_superuser = True
        self.reviewer_acc.save()

        payload = ReviewInput(rating=5, text='Admin review')
        request = _make_auth_request(self.factory, self.reviewer_acc, self.reviewer, 'post')
        status, response = create_establishment_review(request, self.establishment.id, payload)
        self.assertEqual(status, 201)

    def test_duplicate_review_rejected(self):
        """One review per author per establishment."""
        from geo.endpoints.buildings import create_establishment_review, ReviewInput

        _add_verifications(self.reviewer, 3)
        EstablishmentReview.objects.create(
            establishment=self.establishment,
            author=self.reviewer,
            rating=3,
        )

        payload = ReviewInput(rating=5)
        request = _make_auth_request(self.factory, self.reviewer_acc, self.reviewer, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_establishment_review(request, self.establishment.id, payload)
        self.assertEqual(ctx.exception.status_code, 409)


class ReviewUpdateDeleteTest(TestCase):
    """Test review update and delete permissions."""

    def setUp(self):
        self.instance = _create_instance()
        self.owner_acc = _create_account(self.instance, 'alice')
        self.owner = _create_profile(self.owner_acc, self.instance)
        self.reviewer_acc = _create_account(self.instance, 'bob')
        self.reviewer = _create_profile(self.reviewer_acc, self.instance, local_name='bob')
        self.other_acc = _create_account(self.instance, 'charlie')
        self.other = _create_profile(self.other_acc, self.instance, local_name='charlie')
        self.establishment = _create_establishment(self.owner, slug='review-edit')
        self.review = EstablishmentReview.objects.create(
            establishment=self.establishment,
            author=self.reviewer,
            rating=3,
            text='OK',
        )
        self.factory = RequestFactory()

    def test_author_can_update(self):
        """Author can update own review."""
        from geo.endpoints.buildings import update_establishment_review, ReviewInput

        payload = ReviewInput(rating=5, text='Updated')
        request = _make_auth_request(self.factory, self.reviewer_acc, self.reviewer, 'put')
        response = update_establishment_review(
            request, self.establishment.id, self.review.id, payload,
        )

        self.assertEqual(response.rating, 5)
        self.assertEqual(response.text, 'Updated')

    def test_non_author_cannot_update(self):
        """Non-author is denied update."""
        from geo.endpoints.buildings import update_establishment_review, ReviewInput

        payload = ReviewInput(rating=1, text='Hacked')
        request = _make_auth_request(self.factory, self.other_acc, self.other, 'put')
        with self.assertRaises(HttpError) as ctx:
            update_establishment_review(
                request, self.establishment.id, self.review.id, payload,
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_author_can_delete(self):
        """Author can delete own review."""
        from geo.endpoints.buildings import delete_establishment_review

        request = _make_auth_request(self.factory, self.reviewer_acc, self.reviewer, 'delete')
        delete_establishment_review(request, self.establishment.id, self.review.id)
        self.assertFalse(EstablishmentReview.objects.filter(id=self.review.id).exists())

    def test_establishment_owner_can_delete_any_review(self):
        """Establishment owner can delete any review."""
        from geo.endpoints.buildings import delete_establishment_review

        request = _make_auth_request(self.factory, self.owner_acc, self.owner, 'delete')
        delete_establishment_review(request, self.establishment.id, self.review.id)
        self.assertFalse(EstablishmentReview.objects.filter(id=self.review.id).exists())

    def test_random_user_cannot_delete(self):
        """Random user cannot delete someone else's review."""
        from geo.endpoints.buildings import delete_establishment_review

        request = _make_auth_request(self.factory, self.other_acc, self.other, 'delete')
        with self.assertRaises(HttpError) as ctx:
            delete_establishment_review(request, self.establishment.id, self.review.id)
        self.assertEqual(ctx.exception.status_code, 403)


class ReviewReplyTest(TestCase):
    """Test owner reply to reviews."""

    def setUp(self):
        self.instance = _create_instance()
        self.owner_acc = _create_account(self.instance, 'alice')
        self.owner = _create_profile(self.owner_acc, self.instance)
        self.reviewer_acc = _create_account(self.instance, 'bob')
        self.reviewer = _create_profile(self.reviewer_acc, self.instance, local_name='bob')
        self.establishment = _create_establishment(self.owner, slug='reply-cafe')
        self.review = EstablishmentReview.objects.create(
            establishment=self.establishment,
            author=self.reviewer,
            rating=2,
            text='Could be better',
        )
        self.factory = RequestFactory()

    def test_owner_can_reply(self):
        """Establishment owner can reply to reviews."""
        from geo.endpoints.buildings import reply_to_establishment_review, ReviewReplyInput

        payload = ReviewReplyInput(owner_reply='Thank you for your feedback!')
        request = _make_auth_request(self.factory, self.owner_acc, self.owner, 'put')
        response = reply_to_establishment_review(
            request, self.establishment.id, self.review.id, payload,
        )
        self.assertEqual(response.owner_reply, 'Thank you for your feedback!')

    def test_non_owner_cannot_reply(self):
        """Non-owner is denied replying."""
        from geo.endpoints.buildings import reply_to_establishment_review, ReviewReplyInput

        payload = ReviewReplyInput(owner_reply='Fake reply')
        request = _make_auth_request(self.factory, self.reviewer_acc, self.reviewer, 'put')
        with self.assertRaises(HttpError) as ctx:
            reply_to_establishment_review(
                request, self.establishment.id, self.review.id, payload,
            )
        self.assertEqual(ctx.exception.status_code, 403)


# ===========================================================================
# Treasurer Management
# ===========================================================================

class TreasurerTest(TestCase):
    """Test treasurer get/set/remove."""

    def setUp(self):
        self.instance = _create_instance()
        self.owner_acc = _create_account(self.instance, 'alice')
        self.owner = _create_profile(self.owner_acc, self.instance)
        self.member_acc = _create_account(self.instance, 'bob')
        self.member = _create_profile(self.member_acc, self.instance, local_name='bob')
        self.other_acc = _create_account(self.instance, 'charlie')
        self.other = _create_profile(self.other_acc, self.instance, local_name='charlie')
        self.establishment = _create_establishment(self.owner, slug='treasurer-org')
        # Owner membership
        EstablishmentMembership.objects.create(
            profile=self.owner, establishment=self.establishment, role='OWNER',
        )
        # Member membership
        EstablishmentMembership.objects.create(
            profile=self.member, establishment=self.establishment, role='MEMBER',
        )
        self.factory = RequestFactory()

    def test_get_treasurer_when_none(self):
        """Get treasurer returns 404 when not set."""
        from geo.endpoints.buildings import get_treasurer

        request = self.factory.get('/fake/')
        with self.assertRaises(HttpError) as ctx:
            get_treasurer(request, self.establishment.id)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_set_treasurer_by_owner(self):
        """Owner can set a member as treasurer."""
        from geo.endpoints.buildings import set_treasurer, SetTreasurerRequest

        data = SetTreasurerRequest(profile_id=self.member.id)
        request = _make_auth_request(self.factory, self.owner_acc, self.owner, 'put')
        response = set_treasurer(request, self.establishment.id, data)

        self.assertEqual(response.profile_id, self.member.id)
        membership = EstablishmentMembership.objects.get(
            profile=self.member, establishment=self.establishment,
        )
        self.assertTrue(membership.is_treasurer)

    def test_set_treasurer_non_member_rejected(self):
        """Cannot set non-member as treasurer."""
        from geo.endpoints.buildings import set_treasurer, SetTreasurerRequest

        data = SetTreasurerRequest(profile_id=self.other.id)
        request = _make_auth_request(self.factory, self.owner_acc, self.owner, 'put')
        with self.assertRaises(HttpError) as ctx:
            set_treasurer(request, self.establishment.id, data)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_remove_treasurer(self):
        """Owner can remove treasurer."""
        from geo.endpoints.buildings import remove_treasurer

        membership = EstablishmentMembership.objects.get(
            profile=self.member, establishment=self.establishment,
        )
        membership.is_treasurer = True
        membership.save(update_fields=['is_treasurer'])

        request = _make_auth_request(self.factory, self.owner_acc, self.owner, 'delete')
        remove_treasurer(request, self.establishment.id)

        membership.refresh_from_db()
        self.assertFalse(membership.is_treasurer)

    def test_non_owner_cannot_set_treasurer(self):
        """Regular member cannot set treasurer."""
        from geo.endpoints.buildings import set_treasurer, SetTreasurerRequest

        data = SetTreasurerRequest(profile_id=self.member.id)
        request = _make_auth_request(self.factory, self.member_acc, self.member, 'put')
        with self.assertRaises(HttpError) as ctx:
            set_treasurer(request, self.establishment.id, data)
        self.assertEqual(ctx.exception.status_code, 403)


# ===========================================================================
# Auditor Management
# ===========================================================================

class AuditorTest(TestCase):
    """Test auditor (Fiscal Único) get/set/remove."""

    def setUp(self):
        self.instance = _create_instance()
        self.owner_acc = _create_account(self.instance, 'alice')
        self.owner = _create_profile(self.owner_acc, self.instance)
        self.auditor_acc = _create_account(self.instance, 'bob')
        self.auditor = _create_profile(self.auditor_acc, self.instance, local_name='bob')
        self.member_acc = _create_account(self.instance, 'charlie')
        self.member = _create_profile(self.member_acc, self.instance, local_name='charlie')
        self.establishment = _create_establishment(self.owner, slug='auditor-org')
        EstablishmentMembership.objects.create(
            profile=self.owner, establishment=self.establishment, role='OWNER',
        )
        self.factory = RequestFactory()

    def test_get_auditor_when_none(self):
        """Get auditor returns 404 when not set."""
        from geo.endpoints.buildings import get_auditor

        request = self.factory.get('/fake/')
        with self.assertRaises(HttpError) as ctx:
            get_auditor(request, self.establishment.id)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_set_auditor_auto_creates_membership(self):
        """Setting auditor auto-creates membership if not a member."""
        from geo.endpoints.buildings import set_auditor, SetAuditorRequest

        data = SetAuditorRequest(profile_id=self.auditor.id)
        request = _make_auth_request(self.factory, self.owner_acc, self.owner, 'put')
        response = set_auditor(request, self.establishment.id, data)

        self.assertEqual(response.profile_id, self.auditor.id)
        # Membership auto-created
        membership = EstablishmentMembership.objects.get(
            profile=self.auditor, establishment=self.establishment,
        )
        self.assertTrue(membership.is_auditor)

    def test_set_auditor_clears_previous(self):
        """Setting a new auditor clears the previous one."""
        from geo.endpoints.buildings import set_auditor, SetAuditorRequest

        # Set first auditor
        EstablishmentMembership.objects.create(
            profile=self.auditor, establishment=self.establishment,
            role='MEMBER', is_auditor=True,
        )

        # Set second auditor
        data = SetAuditorRequest(profile_id=self.member.id)
        request = _make_auth_request(self.factory, self.owner_acc, self.owner, 'put')
        set_auditor(request, self.establishment.id, data)

        # Old auditor cleared
        old = EstablishmentMembership.objects.get(
            profile=self.auditor, establishment=self.establishment,
        )
        self.assertFalse(old.is_auditor)

        # New auditor set
        new = EstablishmentMembership.objects.get(
            profile=self.member, establishment=self.establishment,
        )
        self.assertTrue(new.is_auditor)

    def test_remove_auditor(self):
        """Owner can remove auditor."""
        from geo.endpoints.buildings import remove_auditor

        EstablishmentMembership.objects.create(
            profile=self.auditor, establishment=self.establishment,
            role='MEMBER', is_auditor=True,
        )

        request = _make_auth_request(self.factory, self.owner_acc, self.owner, 'delete')
        remove_auditor(request, self.establishment.id)

        membership = EstablishmentMembership.objects.get(
            profile=self.auditor, establishment=self.establishment,
        )
        self.assertFalse(membership.is_auditor)

    def test_non_owner_cannot_set_auditor(self):
        """Regular member cannot set auditor."""
        from geo.endpoints.buildings import set_auditor, SetAuditorRequest

        EstablishmentMembership.objects.create(
            profile=self.member, establishment=self.establishment, role='MEMBER',
        )

        data = SetAuditorRequest(profile_id=self.auditor.id)
        request = _make_auth_request(self.factory, self.member_acc, self.member, 'put')
        with self.assertRaises(HttpError) as ctx:
            set_auditor(request, self.establishment.id, data)
        self.assertEqual(ctx.exception.status_code, 403)


# ===========================================================================
# Payment Address
# ===========================================================================

class PaymentAddressTest(TestCase):
    """Test payment address update permissions."""

    def setUp(self):
        self.instance = _create_instance()
        self.owner_acc = _create_account(self.instance, 'alice')
        self.owner = _create_profile(self.owner_acc, self.instance)
        self.member_acc = _create_account(self.instance, 'bob')
        self.member = _create_profile(self.member_acc, self.instance, local_name='bob')
        self.other_acc = _create_account(self.instance, 'charlie')
        self.other = _create_profile(self.other_acc, self.instance, local_name='charlie')
        self.establishment = _create_establishment(self.owner, slug='payment-org')
        self.factory = RequestFactory()

    def test_owner_can_update_payment_address(self):
        """Owner can set spark address."""
        from geo.endpoints.buildings import update_payment_address, PaymentAddressRequest

        data = PaymentAddressRequest(spark_address='sp1qtest123')
        request = _make_auth_request(self.factory, self.owner_acc, self.owner, 'patch')
        response = update_payment_address(request, self.establishment.id, data)
        self.assertTrue(response['ok'])
        self.establishment.refresh_from_db()
        self.assertEqual(self.establishment.spark_address, 'sp1qtest123')

    def test_treasurer_can_update_payment_address(self):
        """Treasurer can update payment address."""
        from geo.endpoints.buildings import update_payment_address, PaymentAddressRequest

        EstablishmentMembership.objects.create(
            profile=self.member, establishment=self.establishment,
            role='MEMBER', is_treasurer=True,
        )

        data = PaymentAddressRequest(spark_address='sp1qtreasurer')
        request = _make_auth_request(self.factory, self.member_acc, self.member, 'patch')
        response = update_payment_address(request, self.establishment.id, data)
        self.assertTrue(response['ok'])

    def test_random_user_cannot_update_payment_address(self):
        """Non-member cannot update payment address."""
        from geo.endpoints.buildings import update_payment_address, PaymentAddressRequest

        data = PaymentAddressRequest(spark_address='sp1qhacked')
        request = _make_auth_request(self.factory, self.other_acc, self.other, 'patch')
        with self.assertRaises(HttpError) as ctx:
            update_payment_address(request, self.establishment.id, data)
        self.assertEqual(ctx.exception.status_code, 403)


# ===========================================================================
# Terms
# ===========================================================================

class EstablishmentTermsTest(TestCase):
    """Test terms/estatutos endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        self.factory = RequestFactory()

    def test_get_terms_with_content(self):
        """Returns terms content when set."""
        from geo.endpoints.buildings import get_establishment_terms

        est = _create_establishment(
            self.profile, slug='terms-org',
            terms_content='# Our Rules\n1. Be nice',
            terms_url='https://example.com/terms',
        )

        request = self.factory.get('/fake/')
        response = get_establishment_terms(request, est.id)
        self.assertEqual(response['terms_content'], '# Our Rules\n1. Be nice')
        self.assertEqual(response['terms_url'], 'https://example.com/terms')

    def test_get_terms_returns_404_when_empty(self):
        """Returns 404 when no terms set."""
        from geo.endpoints.buildings import get_establishment_terms

        est = _create_establishment(self.profile, slug='no-terms')

        request = self.factory.get('/fake/')
        with self.assertRaises(HttpError) as ctx:
            get_establishment_terms(request, est.id)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_get_terms_by_slug(self):
        """Terms can be fetched by slug."""
        from geo.endpoints.buildings import get_establishment_terms

        est = _create_establishment(
            self.profile, slug='slug-terms',
            terms_content='Some terms',
        )

        request = self.factory.get('/fake/')
        response = get_establishment_terms(request, 'slug-terms')
        self.assertEqual(response['establishment_id'], est.id)


# ===========================================================================
# My Postable Establishments
# ===========================================================================

class MyPostableTest(TestCase):
    """Test my-postable endpoint for 'Post as' dropdown."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        self.factory = RequestFactory()

    def test_includes_owned_establishments(self):
        """Owned establishments appear in postable list."""
        from geo.endpoints.buildings import my_postable_establishments

        est = _create_establishment(self.profile, slug='owned')

        request = _make_auth_request(self.factory, self.account, self.profile)
        response = my_postable_establishments(request)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0].name, est.name)
        self.assertEqual(response[0].role, 'OWNER')

    def test_includes_member_establishments(self):
        """Member establishments appear in postable list."""
        from geo.endpoints.buildings import my_postable_establishments

        other_acc = _create_account(self.instance, 'bob')
        other = _create_profile(other_acc, self.instance, local_name='bob')
        est = _create_establishment(other, slug='other-org')
        EstablishmentMembership.objects.create(
            profile=self.profile, establishment=est, role='MEMBER',
        )

        request = _make_auth_request(self.factory, self.account, self.profile)
        response = my_postable_establishments(request)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0].role, 'MEMBER')

    def test_excludes_inactive_establishments(self):
        """Inactive establishments not in postable list."""
        from geo.endpoints.buildings import my_postable_establishments

        _create_establishment(self.profile, slug='inactive-owned', is_active=False)

        request = _make_auth_request(self.factory, self.account, self.profile)
        response = my_postable_establishments(request)
        self.assertEqual(len(response), 0)


# ===========================================================================
# Permissions helpers
# ===========================================================================

class PermissionsHelperTest(TestCase):
    """Test geo.permissions helper functions."""

    def setUp(self):
        self.instance = _create_instance()
        self.owner_acc = _create_account(self.instance, 'alice')
        self.owner = _create_profile(self.owner_acc, self.instance)
        self.member_acc = _create_account(self.instance, 'bob')
        self.member = _create_profile(self.member_acc, self.instance, local_name='bob')
        self.establishment = _create_establishment(self.owner, slug='perm-org')

    def test_get_establishment_for_action_owner(self):
        """Owner with OWNER in allowed_roles succeeds."""
        from geo.permissions import get_establishment_for_action

        result = get_establishment_for_action(
            self.establishment.id, self.owner, {'OWNER', 'ADMIN'},
        )
        self.assertEqual(result.id, self.establishment.id)

    def test_get_establishment_for_action_member(self):
        """Member with MEMBER in allowed_roles succeeds."""
        from geo.permissions import get_establishment_for_action

        EstablishmentMembership.objects.create(
            profile=self.member, establishment=self.establishment, role='MEMBER',
        )

        result = get_establishment_for_action(
            self.establishment.id, self.member, {'OWNER', 'ADMIN', 'MEMBER'},
        )
        self.assertEqual(result.id, self.establishment.id)

    def test_get_establishment_for_action_insufficient_role(self):
        """Member with wrong role is denied."""
        from geo.permissions import get_establishment_for_action

        EstablishmentMembership.objects.create(
            profile=self.member, establishment=self.establishment, role='MEMBER',
        )

        with self.assertRaises(HttpError) as ctx:
            get_establishment_for_action(
                self.establishment.id, self.member, {'OWNER', 'ADMIN'},
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_get_establishment_for_action_nonmember_denied(self):
        """Non-member is denied."""
        from geo.permissions import get_establishment_for_action

        with self.assertRaises(HttpError) as ctx:
            get_establishment_for_action(
                self.establishment.id, self.member, {'OWNER'},
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_get_treasurer_profile(self):
        """Returns treasurer profile when set."""
        from geo.permissions import get_treasurer_profile

        EstablishmentMembership.objects.create(
            profile=self.member, establishment=self.establishment,
            role='MEMBER', is_treasurer=True,
        )

        result = get_treasurer_profile(self.establishment)
        self.assertEqual(result.id, self.member.id)

    def test_get_treasurer_profile_none(self):
        """Returns None when no treasurer."""
        from geo.permissions import get_treasurer_profile

        result = get_treasurer_profile(self.establishment)
        self.assertIsNone(result)

    def test_get_auditor_profile(self):
        """Returns auditor profile when set."""
        from geo.permissions import get_auditor_profile

        EstablishmentMembership.objects.create(
            profile=self.member, establishment=self.establishment,
            role='MEMBER', is_auditor=True,
        )

        result = get_auditor_profile(self.establishment)
        self.assertEqual(result.id, self.member.id)

    def test_get_user_role_owner(self):
        """Returns OWNER for establishment owner."""
        from geo.permissions import get_user_role

        result = get_user_role(self.establishment, self.owner)
        self.assertEqual(result, 'OWNER')

    def test_get_user_role_member(self):
        """Returns role for member."""
        from geo.permissions import get_user_role

        EstablishmentMembership.objects.create(
            profile=self.member, establishment=self.establishment, role='ADMIN',
        )

        result = get_user_role(self.establishment, self.member)
        self.assertEqual(result, 'ADMIN')

    def test_get_user_role_none(self):
        """Returns None for non-member."""
        from geo.permissions import get_user_role

        result = get_user_role(self.establishment, self.member)
        self.assertIsNone(result)


# ===========================================================================
# Rating Signal
# ===========================================================================

class RatingSignalTest(TestCase):
    """Test that review signals update establishment rating_avg/rating_count."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        self.reviewer1_acc = _create_account(self.instance, 'bob')
        self.reviewer1 = _create_profile(self.reviewer1_acc, self.instance, local_name='bob')
        self.reviewer2_acc = _create_account(self.instance, 'charlie')
        self.reviewer2 = _create_profile(self.reviewer2_acc, self.instance, local_name='charlie')
        self.establishment = _create_establishment(self.profile, slug='signal-cafe')

    def test_rating_avg_updated_on_review_create(self):
        """Rating average and count updated after review creation."""
        from geo.signals import update_establishment_rating_on_save

        review = EstablishmentReview(
            establishment=self.establishment,
            author=self.reviewer1,
            rating=4,
        )
        review.save()
        # Manually trigger signal (signals may not auto-connect in tests)
        update_establishment_rating_on_save(
            sender=EstablishmentReview, instance=review,
        )

        self.establishment.refresh_from_db()
        self.assertEqual(self.establishment.rating_count, 1)
        self.assertEqual(float(self.establishment.rating_avg), 4.0)

    def test_rating_avg_after_multiple_reviews(self):
        """Rating average calculated from multiple reviews."""
        from geo.signals import update_establishment_rating_on_save

        r1 = EstablishmentReview.objects.create(
            establishment=self.establishment, author=self.reviewer1, rating=5,
        )
        r2 = EstablishmentReview.objects.create(
            establishment=self.establishment, author=self.reviewer2, rating=3,
        )
        update_establishment_rating_on_save(sender=EstablishmentReview, instance=r2)

        self.establishment.refresh_from_db()
        self.assertEqual(self.establishment.rating_count, 2)
        self.assertEqual(float(self.establishment.rating_avg), 4.0)

    def test_rating_avg_after_review_delete(self):
        """Rating recalculated after review deletion."""
        from geo.signals import update_establishment_rating_on_save, update_establishment_rating_on_delete

        r1 = EstablishmentReview.objects.create(
            establishment=self.establishment, author=self.reviewer1, rating=5,
        )
        r2 = EstablishmentReview.objects.create(
            establishment=self.establishment, author=self.reviewer2, rating=1,
        )
        update_establishment_rating_on_save(sender=EstablishmentReview, instance=r2)

        # Delete second review
        r2.delete()
        update_establishment_rating_on_delete(sender=EstablishmentReview, instance=r2)

        self.establishment.refresh_from_db()
        self.assertEqual(self.establishment.rating_count, 1)
        self.assertEqual(float(self.establishment.rating_avg), 5.0)


# ===========================================================================
# Event Model Tests (SimpleTestCase — no DB)
# ===========================================================================

class EventModelLogicTest(SimpleTestCase):
    """Test Event model methods without DB."""

    def test_status_choices(self):
        from geo.models import Event
        self.assertEqual(Event.Status.DRAFT, 'DRAFT')
        self.assertEqual(Event.Status.PUBLISHED, 'PUBLISHED')
        self.assertEqual(Event.Status.CANCELLED, 'CANCELLED')
        self.assertEqual(Event.Status.COMPLETED, 'COMPLETED')

    def test_event_type_choices(self):
        from geo.models import Event
        self.assertEqual(Event.EventType.OFFLINE, 'OFFLINE')
        self.assertEqual(Event.EventType.ONLINE, 'ONLINE')
        self.assertEqual(Event.EventType.HYBRID, 'HYBRID')

    def test_participant_status_choices(self):
        from geo.models import EventParticipant
        self.assertEqual(EventParticipant.ParticipantStatus.GOING, 'GOING')
        self.assertEqual(EventParticipant.ParticipantStatus.MAYBE, 'MAYBE')
        self.assertEqual(EventParticipant.ParticipantStatus.CANCELLED, 'CANCELLED')

    def test_is_full_unlimited(self):
        from geo.models import Event
        event = Event()
        event.max_participants = None
        event.participants_count = 999
        self.assertFalse(event.is_full())

    def test_is_full_not_reached(self):
        from geo.models import Event
        event = Event()
        event.max_participants = 10
        event.participants_count = 5
        self.assertFalse(event.is_full())

    def test_is_full_reached(self):
        from geo.models import Event
        event = Event()
        event.max_participants = 10
        event.participants_count = 10
        self.assertTrue(event.is_full())

    def test_is_full_exceeded(self):
        from geo.models import Event
        event = Event()
        event.max_participants = 10
        event.participants_count = 11
        self.assertTrue(event.is_full())

    def test_get_location_display_with_name(self):
        from geo.models import Event
        event = Event()
        event.world_object = None
        event.location_name = 'Parque das Nações'
        event.location = None
        self.assertEqual(event.get_location_display(), 'Parque das Nações')

    def test_get_location_display_empty(self):
        from geo.models import Event
        event = Event()
        event.world_object = None
        event.location_name = ''
        event.location = None
        self.assertEqual(event.get_location_display(), '')


# ===========================================================================
# Event Create Tests
# ===========================================================================

def _create_event(organizer, **kwargs):
    """Create an Event directly in DB."""
    from geo.models import Event
    from django.utils import timezone as tz
    defaults = {
        'title': 'Test Meetup',
        'description': 'A community meetup for testing purposes.',
        'event_type': Event.EventType.OFFLINE,
        'starts_at': tz.now() + tz.timedelta(days=7),
        'timezone': 'Europe/Lisbon',
        'location_name': 'Praça do Comércio',
        'status': Event.Status.PUBLISHED,
    }
    defaults.update(kwargs)
    return Event.objects.create(organizer=organizer, **defaults)


class EventCreateTest(TestCase):
    """Test event creation: WoT requirements, validation, field checks."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        _add_verifications(self.profile, count=3)

    @patch('geo.endpoints.events._create_event_matrix_room', return_value=None)
    def test_create_offline_event(self, mock_matrix):
        """Create offline event with location name."""
        from geo.endpoints.events import create_event, EventInput
        from django.utils import timezone as tz

        payload = EventInput(
            title='Community Meetup',
            description='An awesome meetup for testing.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=7),
            location_name='Parque das Nações',
        )
        request = _make_auth_request(self.factory, self.account, self.profile, method='post')
        result = create_event(request, payload)
        self.assertEqual(result.title, 'Community Meetup')
        self.assertEqual(result.event_type, 'OFFLINE')
        self.assertEqual(result.status, 'PUBLISHED')
        self.assertTrue(result.is_organizer)

    @patch('geo.endpoints.events._create_event_matrix_room', return_value=None)
    def test_create_online_event(self, mock_matrix):
        """Create online event with URL."""
        from geo.endpoints.events import create_event, EventInput
        from django.utils import timezone as tz

        payload = EventInput(
            title='Online Workshop',
            description='Learn Django testing online.',
            event_type='ONLINE',
            starts_at=tz.now() + tz.timedelta(days=3),
            online_url='https://meet.parahub.io/test',
        )
        request = _make_auth_request(self.factory, self.account, self.profile, method='post')
        result = create_event(request, payload)
        self.assertEqual(result.event_type, 'ONLINE')

    @patch('geo.endpoints.events._create_event_matrix_room', return_value=None)
    def test_create_hybrid_event(self, mock_matrix):
        """Hybrid event needs both location and URL."""
        from geo.endpoints.events import create_event, EventInput
        from django.utils import timezone as tz

        payload = EventInput(
            title='Hybrid Talk',
            description='Join us in person or online!',
            event_type='HYBRID',
            starts_at=tz.now() + tz.timedelta(days=5),
            location_name='Lisbon Tech Hub',
            online_url='https://meet.parahub.io/hybrid',
        )
        request = _make_auth_request(self.factory, self.account, self.profile, method='post')
        result = create_event(request, payload)
        self.assertEqual(result.event_type, 'HYBRID')

    def test_create_offline_no_location_fails(self):
        """Offline event without location must fail."""
        from geo.endpoints.events import create_event, EventInput
        from django.utils import timezone as tz

        payload = EventInput(
            title='No Location Event',
            description='This should fail validation.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=7),
        )
        request = _make_auth_request(self.factory, self.account, self.profile, method='post')
        with self.assertRaises(HttpError) as ctx:
            create_event(request, payload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('location', str(ctx.exception))

    def test_create_online_no_url_fails(self):
        """Online event without URL must fail."""
        from geo.endpoints.events import create_event, EventInput
        from django.utils import timezone as tz

        payload = EventInput(
            title='No URL Event',
            description='This should fail validation.',
            event_type='ONLINE',
            starts_at=tz.now() + tz.timedelta(days=7),
        )
        request = _make_auth_request(self.factory, self.account, self.profile, method='post')
        with self.assertRaises(HttpError) as ctx:
            create_event(request, payload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('online_url', str(ctx.exception))

    def test_create_end_before_start_fails(self):
        """End time must be after start time."""
        from geo.endpoints.events import create_event, EventInput
        from django.utils import timezone as tz

        now = tz.now()
        payload = EventInput(
            title='Bad Time Event',
            description='Ends before it starts.',
            event_type='OFFLINE',
            starts_at=now + tz.timedelta(days=7),
            ends_at=now + tz.timedelta(days=6),
            location_name='Somewhere',
        )
        request = _make_auth_request(self.factory, self.account, self.profile, method='post')
        with self.assertRaises(HttpError) as ctx:
            create_event(request, payload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('End time', str(ctx.exception))

    def test_create_requires_wot3(self):
        """Users with <3 WoT verifications cannot create events."""
        from geo.endpoints.events import create_event, EventInput
        from django.utils import timezone as tz

        # New user with no verifications
        acc = _create_account(self.instance, 'newbie')
        prof = _create_profile(acc, self.instance, 'newbie')

        payload = EventInput(
            title='Newbie Event',
            description='Should be blocked by WoT.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=7),
            location_name='Somewhere',
        )
        request = _make_auth_request(self.factory, acc, prof, method='post')
        with self.assertRaises(HttpError) as ctx:
            create_event(request, payload)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn('WoT', str(ctx.exception))

    @patch('geo.endpoints.events._create_event_matrix_room', return_value=None)
    def test_create_admin_bypasses_wot(self, mock_matrix):
        """Superusers skip WoT check."""
        from geo.endpoints.events import create_event, EventInput
        from django.utils import timezone as tz

        admin_acc = _create_account(self.instance, 'admin', is_superuser=True)
        admin_prof = _create_profile(admin_acc, self.instance, 'admin')

        payload = EventInput(
            title='Admin Event',
            description='Admin can create without WoT.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=7),
            location_name='HQ',
        )
        request = _make_auth_request(self.factory, admin_acc, admin_prof, method='post')
        result = create_event(request, payload)
        self.assertEqual(result.title, 'Admin Event')

    @patch('geo.endpoints.events._create_event_matrix_room', return_value='!test_room:parahub.io')
    def test_create_sets_matrix_room(self, mock_matrix):
        """Matrix room ID is saved when room creation succeeds."""
        from geo.endpoints.events import create_event, EventInput
        from geo.models import Event
        from django.utils import timezone as tz

        payload = EventInput(
            title='Matrix Room Event',
            description='Should have a Matrix room attached.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=7),
            location_name='Matrix HQ',
        )
        request = _make_auth_request(self.factory, self.account, self.profile, method='post')
        result = create_event(request, payload)
        # Reload from DB to verify
        event = Event.objects.get(id=result.id)
        self.assertEqual(event.matrix_room_id, '!test_room:parahub.io')

    @patch('geo.endpoints.events._create_event_matrix_room', return_value=None)
    def test_create_with_building(self, mock_matrix):
        """Event with world_object reference."""
        from geo.endpoints.events import create_event, EventInput
        from django.utils import timezone as tz

        building = _create_building()
        payload = EventInput(
            title='Building Event',
            description='Happens in a specific building.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=7),
            world_object_id=building.id,
        )
        request = _make_auth_request(self.factory, self.account, self.profile, method='post')
        result = create_event(request, payload)
        self.assertIsNotNone(result.world_object)

    @patch('geo.endpoints.events._create_event_matrix_room', return_value=None)
    def test_create_with_coordinates(self, mock_matrix):
        """Event with lat/lon coordinates."""
        from geo.endpoints.events import create_event, EventInput
        from geo.endpoints.buildings import LocationInput
        from django.utils import timezone as tz

        payload = EventInput(
            title='Geo Event',
            description='Located by coordinates.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=7),
            location=LocationInput(latitude=38.7167, longitude=-9.1395),
        )
        request = _make_auth_request(self.factory, self.account, self.profile, method='post')
        result = create_event(request, payload)
        self.assertIsNotNone(result.location)
        self.assertAlmostEqual(result.location['lat'], 38.7167, places=3)

    @patch('geo.endpoints.events._create_event_matrix_room', return_value=None)
    def test_create_with_max_participants(self, mock_matrix):
        """Event with max participants."""
        from geo.endpoints.events import create_event, EventInput
        from django.utils import timezone as tz

        payload = EventInput(
            title='Limited Event',
            description='Only 10 people can attend.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=7),
            location_name='Small Room',
            max_participants=10,
        )
        request = _make_auth_request(self.factory, self.account, self.profile, method='post')
        result = create_event(request, payload)
        self.assertEqual(result.max_participants, 10)
        self.assertFalse(result.is_full)


# ===========================================================================
# Event Detail Tests
# ===========================================================================

class EventDetailTest(TestCase):
    """Test event detail retrieval and view counter."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        self.event = _create_event(self.profile)

    def test_get_event_detail(self):
        """Get event detail returns correct data."""
        from geo.endpoints.events import get_event

        request = _make_anon_request(self.factory)
        # Simulate unauthenticated user
        request.user = MagicMock()
        request.user.is_authenticated = False
        result = get_event(request, self.event.id)
        self.assertEqual(result.id, self.event.id)
        self.assertEqual(result.title, 'Test Meetup')
        self.assertEqual(result.object_type, 'event')

    def test_get_event_increments_views(self):
        """View counter incremented on each GET."""
        from geo.endpoints.events import get_event
        from geo.models import Event

        initial_views = self.event.views_count
        request = _make_anon_request(self.factory)
        request.user = MagicMock()
        request.user.is_authenticated = False
        get_event(request, self.event.id)

        self.event.refresh_from_db()
        self.assertEqual(self.event.views_count, initial_views + 1)

    def test_get_event_shows_organizer(self):
        """Authenticated organizer sees is_organizer=True."""
        from geo.endpoints.events import get_event

        request = _make_auth_request(self.factory, self.account, self.profile)
        # get_event uses request.user.is_authenticated, not request.auth
        result = get_event(request, self.event.id)
        self.assertTrue(result.is_organizer)

    def test_get_event_nonexistent_404(self):
        """Non-existent event raises 404."""
        from geo.endpoints.events import get_event
        from django.http import Http404

        request = _make_anon_request(self.factory)
        request.user = MagicMock()
        request.user.is_authenticated = False
        with self.assertRaises(Http404):
            get_event(request, '01NONEXISTENT00000000000000')


# ===========================================================================
# Event List Tests
# ===========================================================================

class EventListTest(TestCase):
    """Test event listing with filters."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        from django.utils import timezone as tz
        self.event1 = _create_event(self.profile, title='Python Meetup',
                                     description='Learn Python.')
        self.event2 = _create_event(self.profile, title='Rust Workshop',
                                     description='Rust is great.',
                                     event_type='ONLINE',
                                     online_url='https://meet.test.io/rust',
                                     starts_at=tz.now() + tz.timedelta(days=14))
        self.event_draft = _create_event(self.profile, title='Draft Event',
                                          description='Not published yet.',
                                          status='DRAFT')

    def _get_items(self, result):
        """Extract items from paginated response."""
        if isinstance(result, dict) and 'items' in result:
            return result['items']
        return result

    def test_list_published_default(self):
        """Default list shows only PUBLISHED events."""
        from geo.endpoints.events import list_events

        request = _make_anon_request(self.factory)
        items = self._get_items(list_events(request, status='PUBLISHED'))
        titles = [e.title for e in items]
        self.assertIn('Python Meetup', titles)
        self.assertIn('Rust Workshop', titles)
        self.assertNotIn('Draft Event', titles)

    def test_list_filter_event_type(self):
        """Filter by event type."""
        from geo.endpoints.events import list_events

        request = _make_anon_request(self.factory)
        items = self._get_items(list_events(request, event_type='ONLINE'))
        titles = [e.title for e in items]
        self.assertIn('Rust Workshop', titles)
        self.assertNotIn('Python Meetup', titles)

    def test_list_search(self):
        """Search by title/description."""
        from geo.endpoints.events import list_events

        request = _make_anon_request(self.factory)
        items = self._get_items(list_events(request, search='Python Meetup'))
        found = [e for e in items if e.title == 'Python Meetup']
        self.assertEqual(len(found), 1)

    def test_list_search_description(self):
        """Search matches description too."""
        from geo.endpoints.events import list_events

        request = _make_anon_request(self.factory)
        items = self._get_items(list_events(request, search='Rust is great'))
        found = [e for e in items if e.title == 'Rust Workshop']
        self.assertEqual(len(found), 1)

    def test_list_filter_organizer(self):
        """Filter by organizer_id."""
        from geo.endpoints.events import list_events

        bob_acc = _create_account(self.instance, 'bob')
        bob_prof = _create_profile(bob_acc, self.instance, 'bob')
        _create_event(bob_prof, title='Bob Event', description='Bob organizes this.')

        request = _make_anon_request(self.factory)
        items = self._get_items(list_events(request, organizer_id=bob_prof.id))
        found = [e for e in items if e.title == 'Bob Event']
        self.assertEqual(len(found), 1)

    def test_list_draft_requires_auth(self):
        """DRAFT filter requires authentication."""
        from geo.endpoints.events import list_events

        request = _make_anon_request(self.factory)
        request.user = None
        with self.assertRaises(HttpError) as ctx:
            list_events(request, status='DRAFT')
        self.assertEqual(ctx.exception.status_code, 401)

    def test_list_draft_shows_own(self):
        """Authenticated user sees only their own drafts."""
        from geo.endpoints.events import list_events

        request = _make_auth_request(self.factory, self.account, self.profile)
        items = self._get_items(list_events(request, status='DRAFT'))
        titles = [e.title for e in items]
        self.assertIn('Draft Event', titles)

    def test_list_date_from_filter(self):
        """Filter events starting after a date."""
        from geo.endpoints.events import list_events
        from django.utils import timezone as tz

        future_date = (tz.now() + tz.timedelta(days=10)).isoformat()
        request = _make_anon_request(self.factory)
        items = self._get_items(list_events(request, date_from=future_date))
        titles = [e.title for e in items]
        self.assertIn('Rust Workshop', titles)
        self.assertNotIn('Python Meetup', titles)

    def test_list_returns_object_type(self):
        """List items include object_type field."""
        from geo.endpoints.events import list_events

        request = _make_anon_request(self.factory)
        items = self._get_items(list_events(request))
        published = [e for e in items if e.title in ('Python Meetup', 'Rust Workshop')]
        for item in published:
            self.assertEqual(item.object_type, 'event')


# ===========================================================================
# My Events Tests
# ===========================================================================

class EventMyEventsTest(TestCase):
    """Test /events/my/ — organizing and participating."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, 'bob')

        self.alice_event = _create_event(self.alice, title='Alice Meetup',
                                          description='Organized by Alice.')
        self.bob_event = _create_event(self.bob, title='Bob Meetup',
                                        description='Organized by Bob.')

    def test_my_events_organizing(self):
        """Shows events I'm organizing."""
        from geo.endpoints.events import get_my_events

        request = _make_auth_request(self.factory, self.alice_acc, self.alice)
        result = get_my_events(request)
        org_titles = [e.title for e in result['organizing']]
        self.assertIn('Alice Meetup', org_titles)
        self.assertNotIn('Bob Meetup', org_titles)

    def test_my_events_participating(self):
        """Shows events I've joined as participant."""
        from geo.endpoints.events import get_my_events
        from geo.models import EventParticipant

        # Alice joins Bob's event
        EventParticipant.objects.create(
            event=self.bob_event, profile=self.alice, status='GOING',
        )

        request = _make_auth_request(self.factory, self.alice_acc, self.alice)
        result = get_my_events(request)
        part_titles = [e.title for e in result['participating']]
        self.assertIn('Bob Meetup', part_titles)

    def test_my_events_excludes_cancelled(self):
        """Cancelled events excluded from organizing."""
        from geo.endpoints.events import get_my_events

        self.alice_event.status = 'CANCELLED'
        self.alice_event.save(update_fields=['status'])

        request = _make_auth_request(self.factory, self.alice_acc, self.alice)
        result = get_my_events(request)
        org_titles = [e.title for e in result['organizing']]
        self.assertNotIn('Alice Meetup', org_titles)

    def test_my_events_organizing_not_in_participating(self):
        """Own events don't show in participating list."""
        from geo.endpoints.events import get_my_events
        from geo.models import EventParticipant

        # Alice joins her own event via EventParticipant (edge case)
        EventParticipant.objects.create(
            event=self.alice_event, profile=self.alice, status='GOING',
        )

        request = _make_auth_request(self.factory, self.alice_acc, self.alice)
        result = get_my_events(request)
        part_titles = [e.title for e in result['participating']]
        self.assertNotIn('Alice Meetup', part_titles)


# ===========================================================================
# Event Update Tests
# ===========================================================================

class EventUpdateTest(TestCase):
    """Test event update: organizer-only, cancelled check."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        _add_verifications(self.alice, count=3)
        self.event = _create_event(self.alice)

    def test_update_by_organizer(self):
        """Organizer can update event."""
        from geo.endpoints.events import update_event, EventInput
        from django.utils import timezone as tz

        payload = EventInput(
            title='Updated Meetup',
            description='Updated description for our meetup.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=14),
            location_name='New Location',
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, method='put')
        result = update_event(request, self.event.id, payload)
        self.assertEqual(result.title, 'Updated Meetup')

    def test_update_by_non_organizer_fails(self):
        """Non-organizer cannot update event."""
        from geo.endpoints.events import update_event, EventInput
        from django.utils import timezone as tz

        bob_acc = _create_account(self.instance, 'bob')
        bob = _create_profile(bob_acc, self.instance, 'bob')

        payload = EventInput(
            title='Hacked Event',
            description='Should not be allowed to update.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=14),
            location_name='Somewhere',
        )
        request = _make_auth_request(self.factory, bob_acc, bob, method='put')
        with self.assertRaises(HttpError) as ctx:
            update_event(request, self.event.id, payload)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_update_cancelled_event_fails(self):
        """Cannot update a cancelled event."""
        from geo.endpoints.events import update_event, EventInput
        from django.utils import timezone as tz

        self.event.status = 'CANCELLED'
        self.event.save(update_fields=['status'])

        payload = EventInput(
            title='Should Fail',
            description='Cannot update cancelled event.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=14),
            location_name='Somewhere',
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, method='put')
        with self.assertRaises(HttpError) as ctx:
            update_event(request, self.event.id, payload)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_update_end_before_start_fails(self):
        """Update with end before start fails."""
        from geo.endpoints.events import update_event, EventInput
        from django.utils import timezone as tz

        now = tz.now()
        payload = EventInput(
            title='Bad Update',
            description='End time before start time.',
            event_type='OFFLINE',
            starts_at=now + tz.timedelta(days=14),
            ends_at=now + tz.timedelta(days=13),
            location_name='Somewhere',
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, method='put')
        with self.assertRaises(HttpError) as ctx:
            update_event(request, self.event.id, payload)
        self.assertEqual(ctx.exception.status_code, 400)


# ===========================================================================
# Event Cancel Tests
# ===========================================================================

class EventCancelTest(TestCase):
    """Test event cancellation: organizer-only, status checks."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.event = _create_event(self.alice)

    @patch('threading.Thread')
    def test_cancel_by_organizer(self, mock_thread):
        """Organizer can cancel event."""
        from geo.endpoints.events import cancel_event

        request = _make_auth_request(self.factory, self.alice_acc, self.alice, method='post')
        result = cancel_event(request, self.event.id)
        self.assertTrue(result['success'])

        self.event.refresh_from_db()
        self.assertEqual(self.event.status, 'CANCELLED')

    def test_cancel_by_non_organizer_fails(self):
        """Non-organizer cannot cancel event."""
        from geo.endpoints.events import cancel_event

        bob_acc = _create_account(self.instance, 'bob')
        bob = _create_profile(bob_acc, self.instance, 'bob')

        request = _make_auth_request(self.factory, bob_acc, bob, method='post')
        with self.assertRaises(HttpError) as ctx:
            cancel_event(request, self.event.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_cancel_already_cancelled_fails(self):
        """Cannot cancel an already cancelled event."""
        from geo.endpoints.events import cancel_event

        self.event.status = 'CANCELLED'
        self.event.save(update_fields=['status'])

        request = _make_auth_request(self.factory, self.alice_acc, self.alice, method='post')
        with self.assertRaises(HttpError) as ctx:
            cancel_event(request, self.event.id)
        self.assertEqual(ctx.exception.status_code, 400)


# ===========================================================================
# Event Join Tests
# ===========================================================================

class EventJoinTest(TestCase):
    """Test event joining: status, capacity, organizer guard, Matrix join."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, 'bob')
        self.event = _create_event(self.alice)

    @patch('geo.endpoints.events._join_event_matrix_room', return_value=False)
    def test_join_going(self, mock_matrix):
        """User can join event with GOING status."""
        from geo.endpoints.events import join_event, JoinEventInput

        payload = JoinEventInput(status='GOING')
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        result = join_event(request, self.event.id, payload)
        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'GOING')
        self.assertEqual(result['participants_count'], 1)

    @patch('geo.endpoints.events._join_event_matrix_room', return_value=False)
    def test_join_maybe(self, mock_matrix):
        """User can join with MAYBE status (doesn't count in participants_count)."""
        from geo.endpoints.events import join_event, JoinEventInput

        payload = JoinEventInput(status='MAYBE')
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        result = join_event(request, self.event.id, payload)
        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'MAYBE')
        # MAYBE doesn't count as GOING
        self.assertEqual(result['participants_count'], 0)

    def test_join_organizer_fails(self):
        """Organizer cannot join their own event as participant."""
        from geo.endpoints.events import join_event, JoinEventInput

        payload = JoinEventInput(status='GOING')
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, method='post')
        with self.assertRaises(HttpError) as ctx:
            join_event(request, self.event.id, payload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('Organizer', str(ctx.exception))

    @patch('geo.endpoints.events._join_event_matrix_room', return_value=False)
    def test_join_full_event_fails(self, mock_matrix):
        """Cannot join full event with GOING status."""
        from geo.endpoints.events import join_event, JoinEventInput

        self.event.max_participants = 1
        self.event.participants_count = 1
        self.event.save(update_fields=['max_participants', 'participants_count'])

        payload = JoinEventInput(status='GOING')
        charlie_acc = _create_account(self.instance, 'charlie')
        charlie = _create_profile(charlie_acc, self.instance, 'charlie')
        request = _make_auth_request(self.factory, charlie_acc, charlie, method='post')
        with self.assertRaises(HttpError) as ctx:
            join_event(request, self.event.id, payload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('full', str(ctx.exception))

    @patch('geo.endpoints.events._join_event_matrix_room', return_value=False)
    def test_join_update_status(self, mock_matrix):
        """Re-joining updates status (MAYBE → GOING)."""
        from geo.endpoints.events import join_event, JoinEventInput
        from geo.models import EventParticipant

        # First join as MAYBE
        payload = JoinEventInput(status='MAYBE')
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        join_event(request, self.event.id, payload)

        # Update to GOING
        payload = JoinEventInput(status='GOING')
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        result = join_event(request, self.event.id, payload)
        self.assertEqual(result['status'], 'GOING')
        self.assertEqual(result['participants_count'], 1)

        # Verify only one participant record exists
        self.assertEqual(
            EventParticipant.objects.filter(event=self.event, profile=self.bob).count(), 1
        )

    def test_join_unpublished_fails(self):
        """Cannot join a non-published event."""
        from geo.endpoints.events import join_event, JoinEventInput
        from django.http import Http404

        self.event.status = 'DRAFT'
        self.event.save(update_fields=['status'])

        payload = JoinEventInput(status='GOING')
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        with self.assertRaises(Http404):
            join_event(request, self.event.id, payload)

    @patch('geo.endpoints.events._join_event_matrix_room', return_value=True)
    def test_join_marks_matrix_room_joined(self, mock_matrix):
        """Successful Matrix join sets joined_matrix_room=True."""
        from geo.endpoints.events import join_event, JoinEventInput
        from geo.models import EventParticipant

        self.event.matrix_room_id = '!test:parahub.io'
        self.event.save(update_fields=['matrix_room_id'])

        payload = JoinEventInput(status='GOING')
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        join_event(request, self.event.id, payload)

        participant = EventParticipant.objects.get(event=self.event, profile=self.bob)
        self.assertTrue(participant.joined_matrix_room)


# ===========================================================================
# Event Leave Tests
# ===========================================================================

class EventLeaveTest(TestCase):
    """Test leaving events: status update, participant count."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, 'bob')
        self.event = _create_event(self.alice)

        from geo.models import EventParticipant
        EventParticipant.objects.create(
            event=self.event, profile=self.bob, status='GOING',
        )
        self.event.participants_count = 1
        self.event.save(update_fields=['participants_count'])

    def test_leave_event(self):
        """Participant can leave event."""
        from geo.endpoints.events import leave_event

        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        result = leave_event(request, self.event.id)
        self.assertTrue(result['success'])
        self.assertEqual(result['participants_count'], 0)

    def test_leave_updates_status_to_cancelled(self):
        """Leaving sets participant status to CANCELLED."""
        from geo.endpoints.events import leave_event
        from geo.models import EventParticipant

        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        leave_event(request, self.event.id)

        participant = EventParticipant.objects.get(event=self.event, profile=self.bob)
        self.assertEqual(participant.status, 'CANCELLED')

    def test_leave_not_registered_fails(self):
        """Cannot leave event if not registered."""
        from geo.endpoints.events import leave_event

        charlie_acc = _create_account(self.instance, 'charlie')
        charlie = _create_profile(charlie_acc, self.instance, 'charlie')

        request = _make_auth_request(self.factory, charlie_acc, charlie, method='post')
        with self.assertRaises(HttpError) as ctx:
            leave_event(request, self.event.id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('Not registered', str(ctx.exception))


# ===========================================================================
# Event Participants Tests
# ===========================================================================

class EventParticipantsTest(TestCase):
    """Test participants list: filtering, ordering, cancelled exclusion."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.event = _create_event(self.alice)

        from geo.models import EventParticipant
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, 'bob')
        EventParticipant.objects.create(
            event=self.event, profile=self.bob, status='GOING',
        )
        self.charlie_acc = _create_account(self.instance, 'charlie')
        self.charlie = _create_profile(self.charlie_acc, self.instance, 'charlie')
        EventParticipant.objects.create(
            event=self.event, profile=self.charlie, status='MAYBE',
        )
        self.dave_acc = _create_account(self.instance, 'dave')
        self.dave = _create_profile(self.dave_acc, self.instance, 'dave')
        EventParticipant.objects.create(
            event=self.event, profile=self.dave, status='CANCELLED',
        )

    def _get_items(self, result):
        """Extract items from paginated response."""
        if isinstance(result, dict) and 'items' in result:
            return result['items']
        return result

    def test_list_excludes_cancelled_by_default(self):
        """Default participant list excludes CANCELLED."""
        from geo.endpoints.events import get_event_participants

        request = _make_anon_request(self.factory)
        items = self._get_items(get_event_participants(request, event_id=self.event.id))
        statuses = [p.status for p in items]
        self.assertNotIn('CANCELLED', statuses)
        self.assertEqual(len(items), 2)

    def test_list_filter_going(self):
        """Filter participants by GOING status."""
        from geo.endpoints.events import get_event_participants

        request = _make_anon_request(self.factory)
        items = self._get_items(get_event_participants(request, event_id=self.event.id, status='GOING'))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, 'GOING')

    def test_list_filter_maybe(self):
        """Filter participants by MAYBE status."""
        from geo.endpoints.events import get_event_participants

        request = _make_anon_request(self.factory)
        items = self._get_items(get_event_participants(request, event_id=self.event.id, status='MAYBE'))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, 'MAYBE')

    def test_list_filter_cancelled(self):
        """Can explicitly filter for CANCELLED."""
        from geo.endpoints.events import get_event_participants

        request = _make_anon_request(self.factory)
        items = self._get_items(get_event_participants(request, event_id=self.event.id, status='CANCELLED'))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, 'CANCELLED')

    def test_list_returns_profile_info(self):
        """Participant info includes profile details."""
        from geo.endpoints.events import get_event_participants

        request = _make_anon_request(self.factory)
        items = self._get_items(get_event_participants(request, event_id=self.event.id, status='GOING'))
        self.assertEqual(items[0].profile_id, self.bob.id)
        self.assertIsNotNone(items[0].profile_hna)


# ===========================================================================
# Event Lifecycle Integration Tests
# ===========================================================================

class EventLifecycleTest(TestCase):
    """Full event lifecycle: create → join → leave → cancel."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        _add_verifications(self.alice, count=3)
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance, 'bob')

    @patch('threading.Thread')
    @patch('geo.endpoints.events._join_event_matrix_room', return_value=False)
    @patch('geo.endpoints.events._create_event_matrix_room', return_value=None)
    def test_full_lifecycle(self, mock_create_matrix, mock_join_matrix, mock_thread):
        """Create → Join → Leave → Cancel full lifecycle."""
        from geo.endpoints.events import (
            create_event, join_event, leave_event, cancel_event,
            EventInput, JoinEventInput
        )
        from django.utils import timezone as tz

        # 1. Create event
        create_payload = EventInput(
            title='Lifecycle Event',
            description='Testing full lifecycle flow.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=7),
            location_name='Test Plaza',
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, method='post')
        event_resp = create_event(request, create_payload)
        event_id = event_resp.id
        self.assertEqual(event_resp.status, 'PUBLISHED')
        self.assertEqual(event_resp.participants_count, 0)

        # 2. Bob joins
        join_payload = JoinEventInput(status='GOING')
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        join_result = join_event(request, event_id, join_payload)
        self.assertEqual(join_result['participants_count'], 1)

        # 3. Bob leaves
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        leave_result = leave_event(request, event_id)
        self.assertEqual(leave_result['participants_count'], 0)

        # 4. Alice cancels
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, method='post')
        cancel_result = cancel_event(request, event_id)
        self.assertTrue(cancel_result['success'])

    @patch('geo.endpoints.events._join_event_matrix_room', return_value=False)
    @patch('geo.endpoints.events._create_event_matrix_room', return_value=None)
    def test_capacity_enforcement(self, mock_create_matrix, mock_join_matrix):
        """Event with max_participants=1 blocks second GOING join."""
        from geo.endpoints.events import create_event, join_event, EventInput, JoinEventInput
        from django.utils import timezone as tz

        create_payload = EventInput(
            title='Small Event',
            description='Only one person can attend.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=7),
            location_name='Tiny Room',
            max_participants=1,
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, method='post')
        event_resp = create_event(request, create_payload)
        event_id = event_resp.id

        # Bob joins (fills capacity)
        join_payload = JoinEventInput(status='GOING')
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        join_event(request, event_id, join_payload)

        # Charlie tries to join → should fail
        charlie_acc = _create_account(self.instance, 'charlie')
        charlie = _create_profile(charlie_acc, self.instance, 'charlie')
        request = _make_auth_request(self.factory, charlie_acc, charlie, method='post')
        with self.assertRaises(HttpError) as ctx:
            join_event(request, event_id, join_payload)
        self.assertEqual(ctx.exception.status_code, 400)

    @patch('geo.endpoints.events._join_event_matrix_room', return_value=False)
    @patch('geo.endpoints.events._create_event_matrix_room', return_value=None)
    def test_rejoin_after_leave(self, mock_create_matrix, mock_join_matrix):
        """User can rejoin after leaving."""
        from geo.endpoints.events import (
            create_event, join_event, leave_event,
            EventInput, JoinEventInput
        )
        from geo.models import EventParticipant
        from django.utils import timezone as tz

        create_payload = EventInput(
            title='Rejoin Event',
            description='Test rejoining after leave.',
            event_type='OFFLINE',
            starts_at=tz.now() + tz.timedelta(days=7),
            location_name='Park',
        )
        request = _make_auth_request(self.factory, self.alice_acc, self.alice, method='post')
        event_resp = create_event(request, create_payload)
        event_id = event_resp.id

        # Bob joins → leaves → rejoins
        join_payload = JoinEventInput(status='GOING')
        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        join_event(request, event_id, join_payload)

        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        leave_event(request, event_id)

        request = _make_auth_request(self.factory, self.bob_acc, self.bob, method='post')
        result = join_event(request, event_id, join_payload)
        self.assertEqual(result['status'], 'GOING')
        self.assertEqual(result['participants_count'], 1)

        # Only one participant record
        self.assertEqual(
            EventParticipant.objects.filter(event_id=event_id, profile=self.bob).count(), 1
        )
