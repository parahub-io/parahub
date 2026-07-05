"""
Tests for market endpoints: item CRUD, listing, search, authorization.

Tests invariants that must never break:
- Auth required for create/delete/deactivate
- Owner-only access for delete/deactivate
- Public access for list/detail
- Search filtering by title/description
- Pagination structure
- Version field increments on save
"""

import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, PropertyMock

from django.http import HttpResponse
from django.test import TestCase, SimpleTestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.gis.geos import Point
from ninja.errors import HttpError

from identity.models import Account, Profile
from core.models import Instance
from market.models import Item
from core.models import ObjectPhoto


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
    if data:
        request = fn(path, data=data, content_type='application/json')
    else:
        request = fn(path)
    request.user = account
    request.auth = profile
    request.auth_profile = profile
    request.session = SessionStore()
    request.session.create()
    return request


def _make_anon_request(factory, method='get', path='/fake/'):
    """Build anonymous request (no auth)."""
    fn = getattr(factory, method)
    request = fn(path)
    request.META['HTTP_AUTHORIZATION'] = ''
    return request


def _create_item(profile, title='Test Item', item_type='CREDIT', **kwargs):
    """Create an Item directly in DB."""
    defaults = dict(
        owner=profile,
        title=title,
        type=item_type,
        description=kwargs.pop('description', 'A test item'),
        pricing_options=kwargs.pop('pricing_options', [{'type': 'sale', 'amount': 10.0, 'currency': 'EUR'}]),
        accepted_payment_methods=kwargs.pop('accepted_payment_methods', ['cash']),
        is_active=kwargs.pop('is_active', True),
        language=kwargs.pop('language', 'en'),
    )
    defaults.update(kwargs)
    return Item.objects.create(**defaults)


def _unwrap_result(result):
    """Unwrap list_items result — handles both dict (ORM) and HttpResponse (raw SQL)."""
    if isinstance(result, HttpResponse):
        data = json.loads(result.content)
        # Convert item dicts to SimpleNamespace so attribute access works (item.title etc.)
        data['items'] = [SimpleNamespace(**it) for it in data['items']]
        return data
    return result


# ===========================================================================
# Model-level tests (SimpleTestCase — no DB)
# ===========================================================================

class ItemModelLogicTest(SimpleTestCase):
    """Test Item model methods without DB."""

    def test_type_choices(self):
        self.assertEqual(Item.ItemType.CREDIT, 'CREDIT')
        self.assertEqual(Item.ItemType.DEBIT, 'DEBIT')

    def test_str_representation(self):
        item = Item()
        item.title = 'Bicycle'
        item.type = 'CREDIT'
        self.assertIn('Bicycle', str(item))

    def test_type_name_property(self):
        item = Item()
        self.assertEqual(item.type_name, 'item')
        self.assertEqual(item.object_type, 'item')

    def test_objectphoto_type_name(self):
        photo = ObjectPhoto()
        self.assertEqual(photo.type_name, 'objectphoto')


# ===========================================================================
# DB-backed tests: Item Creation
# ===========================================================================

class ItemCreateTest(TestCase):
    """Test item creation endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        self.factory = RequestFactory()

    @patch('parahub.endpoints.items.detect_content_language', return_value='en')
    def test_create_item_minimal(self, mock_lang):
        """Create item with minimum required fields."""
        from parahub.endpoints.items import create_item, ItemCreateRequest

        data = ItemCreateRequest(
            title='Test Bicycle',
            item_type='CREDIT',
            pricing_options=[],
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        status, response = create_item(request, data)

        self.assertEqual(status, 201)
        self.assertEqual(response.title, 'Test Bicycle')
        self.assertEqual(response.item_type, 'CREDIT')
        self.assertEqual(response.object_type, 'item')
        self.assertEqual(response.owner_id, self.profile.id)
        self.assertTrue(response.is_active)
        self.assertEqual(Item.objects.filter(owner=self.profile).count(), 1)

    @patch('parahub.endpoints.items.detect_content_language', return_value='en')
    def test_create_item_with_pricing(self, mock_lang):
        """Create item with pricing options."""
        from parahub.endpoints.items import create_item, ItemCreateRequest, PricingOption

        data = ItemCreateRequest(
            title='Laptop for Sale',
            item_type='CREDIT',
            description='Great condition laptop',
            pricing_options=[
                PricingOption(type='sale', amount=Decimal('500'), currency='EUR'),
            ],
            accepted_payment_methods=['cash', 'lightning'],
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        status, response = create_item(request, data)

        self.assertEqual(status, 201)
        self.assertEqual(response.description, 'Great condition laptop')
        self.assertEqual(len(response.pricing_options), 1)
        self.assertEqual(response.pricing_options[0].type, 'sale')
        self.assertEqual(float(response.pricing_options[0].amount), 500.0)

    @patch('parahub.endpoints.items.detect_content_language', return_value='en')
    def test_create_item_debit(self, mock_lang):
        """Create a DEBIT (request) item."""
        from parahub.endpoints.items import create_item, ItemCreateRequest

        data = ItemCreateRequest(
            title='Looking for a Plumber',
            item_type='DEBIT',
            pricing_options=[],
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        status, response = create_item(request, data)

        self.assertEqual(status, 201)
        self.assertEqual(response.item_type, 'DEBIT')

    @patch('parahub.endpoints.items.detect_content_language', return_value='en')
    @patch('parahub.endpoints.items.get_country_code_from_coords', return_value='PT')
    def test_create_item_with_location(self, mock_country, mock_lang):
        """Create item with location sets country_code."""
        from parahub.endpoints.items import create_item, ItemCreateRequest, LocationInput

        data = ItemCreateRequest(
            title='Local Service',
            item_type='CREDIT',
            location=LocationInput(latitude=38.7, longitude=-9.1),
            pricing_options=[],
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        status, response = create_item(request, data)

        self.assertEqual(status, 201)
        item = Item.objects.get(id=response.id)
        self.assertEqual(item.country_code, 'PT')
        self.assertIsNotNone(item.location)

    @patch('parahub.endpoints.items.detect_content_language', return_value='en')
    def test_create_item_with_tags(self, mock_lang):
        """Tags are created and associated with the item."""
        from parahub.endpoints.items import create_item, ItemCreateRequest

        data = ItemCreateRequest(
            title='Tagged Item',
            item_type='CREDIT',
            pricing_options=[],
            tag_names=['electronics', 'used'],
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        status, response = create_item(request, data)

        self.assertEqual(status, 201)
        self.assertIn('electronics', response.tags)
        self.assertIn('used', response.tags)

    @patch('parahub.endpoints.items.detect_content_language', return_value='en')
    def test_create_item_international(self, mock_lang):
        """International flag is stored."""
        from parahub.endpoints.items import create_item, ItemCreateRequest

        data = ItemCreateRequest(
            title='Remote Consulting',
            item_type='CREDIT',
            pricing_options=[],
            is_international=True,
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')
        status, response = create_item(request, data)

        self.assertEqual(status, 201)
        self.assertTrue(response.is_international)

    def test_create_item_title_validation(self):
        """Title shorter than 3 chars rejected by Pydantic."""
        from parahub.endpoints.items import ItemCreateRequest
        from pydantic import ValidationError as PydanticValidationError

        with self.assertRaises(PydanticValidationError):
            ItemCreateRequest(
                title='AB',  # min_length=3
                item_type='CREDIT',
                pricing_options=[],
            )

    def test_create_item_invalid_type(self):
        """Invalid item_type rejected by Pydantic."""
        from parahub.endpoints.items import ItemCreateRequest
        from pydantic import ValidationError as PydanticValidationError

        with self.assertRaises(PydanticValidationError):
            ItemCreateRequest(
                title='Valid Title',
                item_type='INVALID',
                pricing_options=[],
            )

    def test_pricing_option_free_no_amount(self):
        """Free pricing option doesn't require amount."""
        from parahub.endpoints.items import PricingOption

        opt = PricingOption(type='free')
        self.assertEqual(opt.type, 'free')
        self.assertIsNone(opt.amount)

    def test_pricing_option_sale_accepts_amount(self):
        """Sale pricing option with amount works."""
        from parahub.endpoints.items import PricingOption

        opt = PricingOption(type='sale', amount=Decimal('100'), currency='EUR')
        self.assertEqual(float(opt.amount), 100.0)
        self.assertEqual(opt.currency, 'EUR')


# ===========================================================================
# DB-backed tests: Item Listing
# ===========================================================================

class ItemListTest(TestCase):
    """Test item listing endpoint with filters and pagination."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob')
        self.factory = RequestFactory()

        # Create test items
        self.item1 = _create_item(self.alice, 'Bicycle for Sale', 'CREDIT',
                                  description='Mountain bike in great shape')
        self.item2 = _create_item(self.alice, 'Looking for Guitar', 'DEBIT',
                                  description='Want an acoustic guitar')
        self.item3 = _create_item(self.bob, 'Laptop Repair Service', 'CREDIT',
                                  description='Professional laptop repair')

    def test_list_items_public(self):
        """Anonymous users can list items."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = _unwrap_result(list_items(request))

        self.assertEqual(result['count'], 3)
        self.assertEqual(len(result['items']), 3)
        self.assertEqual(result['page'], 1)
        self.assertGreaterEqual(result['pages'], 1)

    def test_list_items_filter_by_type(self):
        """Filter by CREDIT/DEBIT type."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = _unwrap_result(list_items(request, item_type='CREDIT'))

        self.assertEqual(result['count'], 2)
        for item in result['items']:
            self.assertEqual(item.item_type, 'CREDIT')

    def test_list_items_filter_by_owner(self):
        """Filter by owner_id."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = _unwrap_result(list_items(request, owner_id=self.alice.id))

        self.assertEqual(result['count'], 2)
        for item in result['items']:
            self.assertEqual(item.owner_id, self.alice.id)

    def test_list_items_search_title(self):
        """Search by title with q parameter."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = list_items(request, q='Bicycle')

        self.assertEqual(result['count'], 1)
        self.assertEqual(result['items'][0].title, 'Bicycle for Sale')

    def test_list_items_search_description(self):
        """Search by description with q parameter."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = list_items(request, q='acoustic guitar')

        self.assertEqual(result['count'], 1)
        self.assertEqual(result['items'][0].title, 'Looking for Guitar')

    def test_list_items_search_no_results(self):
        """Search with no matching results returns empty."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = list_items(request, q='nonexistent xyz')

        self.assertEqual(result['count'], 0)
        self.assertEqual(len(result['items']), 0)

    def test_list_items_pagination(self):
        """Pagination returns correct subset."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = _unwrap_result(list_items(request, page=1, page_size=2))

        self.assertEqual(result['count'], 3)
        self.assertEqual(len(result['items']), 2)
        self.assertEqual(result['page'], 1)
        self.assertEqual(result['page_size'], 2)
        self.assertEqual(result['pages'], 2)

    def test_list_items_pagination_page2(self):
        """Second page returns remaining items."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = _unwrap_result(list_items(request, page=2, page_size=2))

        self.assertEqual(result['count'], 3)
        self.assertEqual(len(result['items']), 1)
        self.assertEqual(result['page'], 2)

    def test_list_items_inactive_hidden(self):
        """An owner listing their OWN items sees inactive ones in the unfiltered
        'All' view; the is_active filter narrows it. (Anonymous callers are
        forced active-only — hidden listings are private — so this is tested
        from the owner's My-Items perspective, which sends no is_active.)"""
        from parahub.endpoints.items import list_items

        self.item1.is_active = False
        self.item1.save()
        # refresh to avoid F() expression issue
        self.item1.refresh_from_db()

        # Owner (alice) listing her own two items (item1 inactive + item2 active).
        request = _make_auth_request(self.factory, self.alice_account, self.alice)

        # Without filter — owner sees all their items (active + inactive)
        result_all = _unwrap_result(list_items(request, owner_id=self.alice.id))
        self.assertEqual(result_all['count'], 2)

        # Filter active only
        result_active = _unwrap_result(list_items(request, owner_id=self.alice.id, is_active=True))
        self.assertEqual(result_active['count'], 1)

        # Filter inactive only
        result_inactive = _unwrap_result(list_items(request, owner_id=self.alice.id, is_active=False))
        self.assertEqual(result_inactive['count'], 1)

    def test_list_items_explicit_inactive_forced_active(self):
        """A non-owner passing an explicit is_active=false must NOT receive
        other people's hidden (inactive) listings — the server forces the
        filter back to active-only (the None-only guard was bypassable)."""
        from parahub.endpoints.items import list_items

        self.item1.is_active = False
        self.item1.save()

        # Anonymous caller explicitly asking for inactive items
        request = _make_anon_request(self.factory)
        result = _unwrap_result(list_items(request, is_active=False))
        self.assertEqual(result['count'], 2)  # only the two active items
        self.assertNotIn(self.item1.id, [item.id for item in result['items']])

        # Authenticated non-owner (bob) scoped to alice's items — same enforcement
        request = _make_auth_request(self.factory, self.bob_account, self.bob)
        result = _unwrap_result(list_items(request, owner_id=self.alice.id, is_active=False))
        self.assertEqual(result['count'], 1)  # alice's active item only
        self.assertNotIn(self.item1.id, [item.id for item in result['items']])

    def test_list_items_default_ordering(self):
        """Default ordering is newest first (-created_at)."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = _unwrap_result(list_items(request))

        # item3 created last, should be first
        self.assertEqual(result['items'][0].title, 'Laptop Repair Service')

    def test_list_items_location_fuzzed(self):
        """Listed items have fuzzed locations."""
        from parahub.endpoints.items import list_items

        self.item1.location = Point(-9.1, 38.7, srid=4326)
        self.item1.save()
        self.item1.refresh_from_db()

        request = _make_anon_request(self.factory)
        result = _unwrap_result(list_items(request, owner_id=self.alice.id, item_type='CREDIT'))

        # Find the item with location
        located = [i for i in result['items'] if i.location is not None]
        self.assertTrue(len(located) > 0)
        loc = located[0].location
        if isinstance(loc, dict):
            self.assertTrue(loc.get('fuzzed', False))
        else:
            self.assertTrue(getattr(loc, 'fuzzed', False))


# ===========================================================================
# DB-backed tests: Item Detail
# ===========================================================================

class ItemDetailTest(TestCase):
    """Test item detail endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        self.factory = RequestFactory()
        self.item = _create_item(self.profile, 'Detailed Item', 'CREDIT',
                                 location=Point(-9.1, 38.7, srid=4326))

    def test_get_item_public(self):
        """Anyone can view item details (no auth required)."""
        from parahub.endpoints.items import get_item

        request = _make_anon_request(self.factory)
        response = get_item(request, self.item.id)

        self.assertEqual(response.id, self.item.id)
        self.assertEqual(response.object_type, 'item')
        self.assertEqual(response.title, 'Detailed Item')
        self.assertEqual(response.owner_id, self.profile.id)
        self.assertEqual(response.owner_hna, self.profile.hna)
        self.assertIsInstance(response.owner_reputation, Decimal)
        self.assertIsInstance(response.owner_is_verified, bool)

    def test_get_item_fuzzed_location(self):
        """Public view returns fuzzed location."""
        from parahub.endpoints.items import get_item

        request = _make_anon_request(self.factory)
        response = get_item(request, self.item.id)

        self.assertIsNotNone(response.location)
        self.assertTrue(response.location.get('fuzzed', False))
        self.assertIsNone(response.exact_location)

    def test_get_item_not_found(self):
        """Non-existent item raises 404."""
        from parahub.endpoints.items import get_item
        from django.http import Http404

        request = _make_anon_request(self.factory)
        with self.assertRaises(Http404):
            get_item(request, 'NONEXISTENT00000000000000')

    def test_get_item_version_field(self):
        """Item detail includes version field."""
        from parahub.endpoints.items import get_item

        request = _make_anon_request(self.factory)
        response = get_item(request, self.item.id)

        self.assertEqual(response.version, 1)

    def test_get_item_pricing_options(self):
        """Item detail includes pricing options."""
        from parahub.endpoints.items import get_item

        request = _make_anon_request(self.factory)
        response = get_item(request, self.item.id)

        self.assertEqual(len(response.pricing_options), 1)
        self.assertEqual(response.pricing_options[0].type, 'sale')


# ===========================================================================
# DB-backed tests: Item Delete
# ===========================================================================

class ItemDeleteTest(TestCase):
    """Test item delete endpoint — owner-only authorization."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob')
        self.factory = RequestFactory()

    def test_owner_can_delete(self):
        """Owner can delete their own item."""
        from parahub.endpoints.items import delete_item

        item = _create_item(self.alice, 'To Delete')
        item_id = item.id
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'delete')

        # Mock item.deals (Deal model was deleted — reverse FK no longer exists)
        with patch.object(Item, 'deals', create=True, new_callable=PropertyMock) as mock_deals:
            mock_manager = MagicMock()
            mock_manager.exclude.return_value.exists.return_value = False
            mock_deals.return_value = mock_manager

            response = delete_item(request, item_id)

        self.assertEqual(response['message'], 'Item deleted successfully')
        self.assertFalse(Item.objects.filter(id=item_id).exists())

    def test_non_owner_cannot_delete(self):
        """Non-owner gets 403 when trying to delete."""
        from parahub.endpoints.items import delete_item

        item = _create_item(self.alice, 'Alice Item')
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'delete')

        with self.assertRaises(HttpError) as ctx:
            delete_item(request, item.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_delete_nonexistent_item(self):
        """Deleting non-existent item raises HttpError."""
        from parahub.endpoints.items import delete_item

        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'delete')

        # get_object_or_404 raises Http404, caught by except Exception → HttpError(500)
        with self.assertRaises(HttpError) as ctx:
            delete_item(request, 'NONEXISTENT00000000000000')
        self.assertEqual(ctx.exception.status_code, 500)


# ===========================================================================
# DB-backed tests: Item Deactivate
# ===========================================================================

class ItemDeactivateTest(TestCase):
    """Test item deactivation endpoint — owner-only soft-delete."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob')
        self.factory = RequestFactory()

    def test_owner_can_deactivate(self):
        """Owner can deactivate their item."""
        from parahub.endpoints.items import deactivate_item

        item = _create_item(self.alice, 'To Deactivate')
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = deactivate_item(request, item.id)

        self.assertFalse(response.is_active)
        item.refresh_from_db()
        self.assertFalse(item.is_active)

    def test_non_owner_cannot_deactivate(self):
        """Non-owner gets 403."""
        from parahub.endpoints.items import deactivate_item

        item = _create_item(self.alice, 'Alice Item')
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')

        with self.assertRaises(HttpError) as ctx:
            deactivate_item(request, item.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_deactivate_preserves_data(self):
        """Deactivation only sets is_active=False, data preserved."""
        from parahub.endpoints.items import deactivate_item

        item = _create_item(self.alice, 'Preserve Me', description='Important data')
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        deactivate_item(request, item.id)

        item.refresh_from_db()
        self.assertFalse(item.is_active)
        self.assertEqual(item.title, 'Preserve Me')
        self.assertEqual(item.description, 'Important data')

    def test_deactivate_nonexistent_item(self):
        """Deactivating non-existent item raises 404."""
        from parahub.endpoints.items import deactivate_item
        from django.http import Http404

        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(Http404):
            deactivate_item(request, 'NONEXISTENT00000000000000')


# ===========================================================================
# DB-backed tests: Item Activate (re-enable a hidden item)
# ===========================================================================

class ItemActivateTest(TestCase):
    """Test item activation endpoint — owner-only inverse of deactivate."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob')
        self.factory = RequestFactory()

    def test_owner_can_activate_hidden_item(self):
        """Hide then activate round-trip — the flow that 404'd before the route existed."""
        from parahub.endpoints.items import activate_item, deactivate_item

        item = _create_item(self.alice, 'Hide Me')
        deactivate_item(_make_auth_request(self.factory, self.alice_account, self.alice, 'post'), item.id)
        item.refresh_from_db()
        self.assertFalse(item.is_active)

        response = activate_item(_make_auth_request(self.factory, self.alice_account, self.alice, 'post'), item.id)

        self.assertTrue(response.is_active)
        item.refresh_from_db()
        self.assertTrue(item.is_active)

    def test_non_owner_cannot_activate(self):
        """Non-owner gets 403."""
        from parahub.endpoints.items import activate_item

        item = _create_item(self.alice, 'Alice Item')
        item.is_active = False
        item.save()
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')

        with self.assertRaises(HttpError) as ctx:
            activate_item(request, item.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_activate_nonexistent_item(self):
        """Activating non-existent item raises 404."""
        from parahub.endpoints.items import activate_item
        from django.http import Http404

        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(Http404):
            activate_item(request, 'NONEXISTENT00000000000000')


# ===========================================================================
# DB-backed tests: object.updated realtime broadcast (post_save signal)
# ===========================================================================

class ObjectPublishSignalTest(TestCase):
    """The post_save broadcast must materialize F()-expressions (e.g. version)
    so the realtime payload stays JSON-serializable. Before the fix, version was
    still a CombinedExpression at signal time and orjson.dumps threw, silently
    dropping every item-update broadcast."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.account, self.instance)

    def test_update_broadcast_materializes_version(self):
        import orjson
        from unittest.mock import patch

        item = _create_item(self.alice, 'Broadcast Me')  # created → version 1, no broadcast
        captured = {}

        def _capture(channel, data):
            captured['channel'] = channel
            captured['data'] = data

        with patch('parahub.services.ws_publish.ws_publish', side_effect=_capture):
            item.title = 'Updated Title'
            item.save()  # update → Item.save() sets version = F('version') + 1

        self.assertIn('data', captured, 'update should broadcast on object: channel')
        changes = captured['data']['changes']
        # version must be the materialized int, not an unresolved expression
        self.assertIsInstance(changes['version'], int)
        self.assertEqual(changes['version'], 2)
        self.assertEqual(changes['title'], 'Updated Title')
        # the full payload must be JSON-serializable — this is what threw before
        orjson.dumps(captured['data'])


# ===========================================================================
# DB-backed tests: Item Version (optimistic locking)
# ===========================================================================

class ItemVersionTest(TestCase):
    """Test item version increment behavior."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)

    def test_new_item_version_1(self):
        """Newly created item has version 1."""
        item = _create_item(self.profile, 'New Item')
        self.assertEqual(item.version, 1)

    def test_version_increments_on_save(self):
        """Version increments when item is saved (updated)."""
        item = _create_item(self.profile, 'Versioned Item')
        self.assertEqual(item.version, 1)

        item.title = 'Updated Title'
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.version, 2)

    def test_version_increments_multiple_saves(self):
        """Multiple saves increment version each time."""
        item = _create_item(self.profile, 'Multi-save')

        for i in range(3):
            item.title = f'Version {i + 2}'
            item.save()
            item.refresh_from_db()

        self.assertEqual(item.version, 4)


# ===========================================================================
# DB-backed tests: Search with multiple filters
# ===========================================================================

class ItemSearchCombinedTest(TestCase):
    """Test combined search/filter scenarios."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        self.factory = RequestFactory()

        self.offer1 = _create_item(self.profile, 'Electric Bicycle', 'CREDIT',
                                   pricing_options=[{'type': 'sale', 'amount': 300.0, 'currency': 'EUR'}])
        self.offer2 = _create_item(self.profile, 'Mountain Bicycle', 'CREDIT',
                                   pricing_options=[{'type': 'sale', 'amount': 150.0, 'currency': 'EUR'}])
        self.request1 = _create_item(self.profile, 'Need a Bicycle', 'DEBIT')

    def test_search_and_type_filter(self):
        """Combine search + type filter."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = list_items(request, q='Bicycle', item_type='CREDIT')

        self.assertEqual(result['count'], 2)
        for item in result['items']:
            self.assertEqual(item.item_type, 'CREDIT')
            self.assertIn('Bicycle', item.title)

    def test_search_case_insensitive(self):
        """Search is case insensitive."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = list_items(request, q='bicycle')

        self.assertEqual(result['count'], 3)

    def test_search_partial_match(self):
        """Search matches partial words."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = list_items(request, q='Electr')

        self.assertEqual(result['count'], 1)
        self.assertEqual(result['items'][0].title, 'Electric Bicycle')

    def test_ordering_created_at_asc(self):
        """Ordering by created_at ascending returns oldest first."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = _unwrap_result(list_items(request, ordering='created_at'))

        self.assertEqual(result['items'][0].title, 'Electric Bicycle')

    def test_empty_page_returns_empty(self):
        """Page beyond results returns empty items list."""
        from parahub.endpoints.items import list_items

        request = _make_anon_request(self.factory)
        result = _unwrap_result(list_items(request, page=100))

        self.assertEqual(result['count'], 3)
        self.assertEqual(len(result['items']), 0)


# ===========================================================================
# DB-backed tests: Item ↔ Establishment on the edit path (post on behalf of)
# ===========================================================================

class ItemEstablishmentUpdateTest(TestCase):
    """Attach/detach an establishment to an existing item via update_item.

    Guards the edit-path gap: create supported 'post on behalf of' but update
    did not. Owner can attach an establishment they can post for, detach via '',
    a payload without establishment_id leaves it unchanged, and attaching one the
    user can't post for is blocked (403) with no partial write.
    """

    def setUp(self):
        from geo.models import Establishment
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob')
        self.factory = RequestFactory()
        # alice owns this establishment → POSTING_ROLES grants her access
        self.est = Establishment.objects.create(name='Alice Cafe', owner=self.alice)
        # bob owns this one; alice is not a member
        self.bob_est = Establishment.objects.create(name='Bob Bar', owner=self.bob)

    def _update(self, profile, account, item_id, **fields):
        from parahub.endpoints.items import update_item, ItemUpdateRequest
        data = ItemUpdateRequest(**fields)
        request = _make_auth_request(self.factory, account, profile, 'put')
        return update_item(request, item_id, data)

    def test_attach_establishment(self):
        """Owner attaches an establishment they can post for."""
        item = _create_item(self.alice, 'Skoda Octavia')
        self.assertIsNone(item.establishment_id)

        response = self._update(self.alice, self.alice_account, item.id,
                                establishment_id=self.est.id)

        self.assertEqual(response.establishment_id, self.est.id)
        self.assertEqual(response.establishment_name, 'Alice Cafe')
        item.refresh_from_db()
        self.assertEqual(item.establishment_id, self.est.id)

    def test_detach_establishment(self):
        """Empty string detaches (post personally)."""
        item = _create_item(self.alice, 'Skoda Octavia', establishment=self.est)
        self.assertEqual(item.establishment_id, self.est.id)

        response = self._update(self.alice, self.alice_account, item.id,
                                establishment_id='')

        self.assertIsNone(response.establishment_id)
        item.refresh_from_db()
        self.assertIsNone(item.establishment_id)

    def test_omitted_establishment_left_unchanged(self):
        """A payload without establishment_id must not touch the existing link."""
        item = _create_item(self.alice, 'Skoda Octavia', establishment=self.est)

        # unrelated edit (is_active) — avoids triggering language detection
        self._update(self.alice, self.alice_account, item.id, is_active=False)

        item.refresh_from_db()
        self.assertEqual(item.establishment_id, self.est.id)
        self.assertFalse(item.is_active)

    def test_attach_without_permission_blocked(self):
        """Attaching an establishment the user can't post for → 403, no partial write."""
        item = _create_item(self.alice, 'Skoda Octavia')

        status, body = self._update(self.alice, self.alice_account, item.id,
                                    establishment_id=self.bob_est.id)

        self.assertEqual(status, 403)
        item.refresh_from_db()
        self.assertIsNone(item.establishment_id)

    def test_detail_of_item_with_establishment(self):
        """Regression: get_item must not 404 when the item has an establishment.

        The detail builder used item.establishment.logo.url, but Establishment
        exposes logo_url — so every on-behalf-of item 404'd. Guards that fix.
        """
        from parahub.endpoints.items import get_item

        item = _create_item(self.alice, 'Skoda Octavia', establishment=self.est)
        request = _make_anon_request(self.factory)

        response = get_item(request, item.id)

        self.assertEqual(response.id, item.id)
        self.assertEqual(response.establishment_id, self.est.id)
        self.assertEqual(response.establishment_name, 'Alice Cafe')
        self.assertFalse(response.establishment_logo_url)  # no logo set → '' (URLField default)


class ItemVisibilityTest(TestCase):
    """Item.visibility (PUBLIC | REGISTERED): anonymous viewers see PUBLIC only;
    any authenticated user sees every tier. Enforced on list (raw SQL + ORM),
    detail, and create/update."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob')
        self.factory = RequestFactory()
        # Two active items, shared keyword so both list paths can be exercised.
        self.pub = _create_item(self.alice, 'Visible Widget', 'CREDIT', visibility='PUBLIC')
        self.reg = _create_item(self.alice, 'Members Widget', 'CREDIT', visibility='REGISTERED')

    def test_default_visibility_is_public(self):
        """A new item is PUBLIC unless told otherwise (civic-router default)."""
        item = _create_item(self.alice, 'Default Widget', 'CREDIT')
        self.assertEqual(item.visibility, 'PUBLIC')

    def test_list_rawsql_anonymous_excludes_registered(self):
        """Raw-SQL fast path: anonymous list hides REGISTERED items."""
        from parahub.endpoints.items import list_items
        request = _make_anon_request(self.factory)
        titles = {it.title for it in _unwrap_result(list_items(request, owner_id=self.alice.id))['items']}
        self.assertIn('Visible Widget', titles)
        self.assertNotIn('Members Widget', titles)

    def test_list_rawsql_authenticated_includes_registered(self):
        """Any signed-in user (here a non-owner) sees REGISTERED items in the list."""
        from parahub.endpoints.items import list_items
        request = _make_auth_request(self.factory, self.bob_account, self.bob)
        titles = {it.title for it in _unwrap_result(list_items(request, owner_id=self.alice.id))['items']}
        self.assertIn('Visible Widget', titles)
        self.assertIn('Members Widget', titles)

    def test_list_orm_path_anonymous_excludes_registered(self):
        """ORM path (forced by q=search) also hides REGISTERED from anonymous."""
        from parahub.endpoints.items import list_items
        request = _make_anon_request(self.factory)
        titles = {it.title for it in _unwrap_result(list_items(request, owner_id=self.alice.id, q='Widget'))['items']}
        self.assertIn('Visible Widget', titles)
        self.assertNotIn('Members Widget', titles)

    def test_detail_anonymous_404_on_registered(self):
        """A direct URL to a REGISTERED item 404s for anonymous (no leak)."""
        from parahub.endpoints.items import get_item
        from django.http import Http404
        request = _make_anon_request(self.factory)
        with self.assertRaises(Http404):
            get_item(request, self.reg.id)

    def test_detail_anonymous_ok_on_public(self):
        """PUBLIC item detail is reachable anonymously and reports its tier."""
        from parahub.endpoints.items import get_item
        resp = get_item(_make_anon_request(self.factory), self.pub.id)
        self.assertEqual(resp.id, self.pub.id)
        self.assertEqual(resp.visibility, 'PUBLIC')

    def test_detail_authenticated_ok_on_registered(self):
        """A signed-in user can open a REGISTERED item; the tier is reported."""
        from parahub.endpoints.items import get_item
        resp = get_item(_make_auth_request(self.factory, self.bob_account, self.bob), self.reg.id)
        self.assertEqual(resp.id, self.reg.id)
        self.assertEqual(resp.visibility, 'REGISTERED')

    @patch('parahub.endpoints.items.detect_content_language', return_value='en')
    def test_create_registered_persists(self, mock_lang):
        """Create with visibility=REGISTERED is saved and echoed back."""
        from parahub.endpoints.items import create_item, ItemCreateRequest
        data = ItemCreateRequest(title='Secret Tool', item_type='CREDIT',
                                 pricing_options=[], visibility='REGISTERED')
        status, response = create_item(
            _make_auth_request(self.factory, self.alice_account, self.alice, 'post'), data)
        self.assertEqual(status, 201)
        self.assertEqual(response.visibility, 'REGISTERED')
        self.assertEqual(Item.objects.get(id=response.id).visibility, 'REGISTERED')


class MediaReorderTest(TestCase):
    """Combined photo+video reordering: owner-only, one shared order space."""

    def setUp(self):
        import uuid
        from core.models import ObjectVideo
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, is_primary=False)
        self.item = _create_item(self.alice, title='Reorder Item')
        # Legacy-style layout: 3 photos (0,1,2) + 1 video (0).
        self.p0 = ObjectPhoto.objects.create(object_id=self.item.id, order=0, uploaded_by=self.alice)
        self.p1 = ObjectPhoto.objects.create(object_id=self.item.id, order=1, uploaded_by=self.alice)
        self.p2 = ObjectPhoto.objects.create(object_id=self.item.id, order=2, uploaded_by=self.alice)
        self.v = ObjectVideo.objects.create(
            object_id=self.item.id, peertube_uuid=uuid.uuid4(),
            peertube_url='https://video.parahub.io/w/x', title='Vid',
            order=0, uploaded_by=self.alice,
        )

    def _payload(self, seq):
        from parahub.endpoints.items import MediaOrderPayload, MediaOrderEntry
        return MediaOrderPayload(order=[MediaOrderEntry(type=k, id=i) for (k, i) in seq])

    def test_owner_reorders_photos_and_video_into_one_sequence(self):
        from parahub.endpoints.items import reorder_item_media
        # Desired: photo2, video, photo0, photo1 (a photo is now the cover).
        seq = [('photo', self.p2.id), ('video', self.v.id),
               ('photo', self.p0.id), ('photo', self.p1.id)]
        req = _make_auth_request(self.factory, self.alice_account, self.alice, 'patch')
        status, _ = reorder_item_media(req, self.item.id, self._payload(seq))
        self.assertEqual(status, 200)
        for obj in (self.p0, self.p1, self.p2, self.v):
            obj.refresh_from_db()
        self.assertEqual((self.p2.order, self.v.order, self.p0.order, self.p1.order), (0, 1, 2, 3))

    def test_non_owner_forbidden(self):
        from parahub.endpoints.items import reorder_item_media
        req = _make_auth_request(self.factory, self.bob_account, self.bob, 'patch')
        status, _ = reorder_item_media(req, self.item.id, self._payload([('photo', self.p0.id)]))
        self.assertEqual(status, 403)
        self.p0.refresh_from_db()
        self.assertEqual(self.p0.order, 0)  # unchanged

    def test_media_from_another_item_rejected(self):
        from parahub.endpoints.items import reorder_item_media
        other = _create_item(self.alice, title='Other')
        foreign = ObjectPhoto.objects.create(object_id=other.id, order=0, uploaded_by=self.alice)
        req = _make_auth_request(self.factory, self.alice_account, self.alice, 'patch')
        status, _ = reorder_item_media(req, self.item.id, self._payload([('photo', foreign.id)]))
        self.assertEqual(status, 400)

    def test_invalid_type_rejected(self):
        from parahub.endpoints.items import reorder_item_media
        req = _make_auth_request(self.factory, self.alice_account, self.alice, 'patch')
        status, _ = reorder_item_media(req, self.item.id, self._payload([('audio', self.p0.id)]))
        self.assertEqual(status, 400)
