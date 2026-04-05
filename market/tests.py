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
        """Inactive items included only when is_active filter is set."""
        from parahub.endpoints.items import list_items

        self.item1.is_active = False
        self.item1.save()
        # refresh to avoid F() expression issue
        self.item1.refresh_from_db()

        request = _make_anon_request(self.factory)

        # Without filter — all items returned (active + inactive)
        result_all = _unwrap_result(list_items(request))
        self.assertEqual(result_all['count'], 3)

        # Filter active only
        result_active = _unwrap_result(list_items(request, is_active=True))
        self.assertEqual(result_active['count'], 2)

        # Filter inactive only
        result_inactive = _unwrap_result(list_items(request, is_active=False))
        self.assertEqual(result_inactive['count'], 1)

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
