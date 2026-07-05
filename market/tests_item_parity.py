"""
Serializer parity tests: the raw-SQL CQRS list path and the ORM list path of
GET /api/v1/items/ MUST produce identical JSON for the same viewer.

Both paths assemble through parahub.endpoints.items.assemble_item_dict; this
suite guards the seams that remain outside the shared core (SQL truncation,
JSONB parsing, photo URL building, demand aggregation, WHERE-clause parity).

The raw path returns HttpResponse (orjson) and the ORM path returns a dict of
pydantic models — the tests assert the response type to prove the intended
path actually ran (the raw path silently falls back to ORM on exceptions).
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from unittest.mock import patch

import orjson
from django.contrib.gis.geos import Point
from django.http import HttpResponse
from django.test import TestCase, RequestFactory

from identity.models import Account, Profile
from core.models import Instance, ObjectPhoto
from market.models import Item
from taxonomy.models import Category
from parahub.endpoints.items import list_items

# All test items carry this marker in the title so `q=` returns the same set
# through the ORM branch as the unfiltered raw branch.
MARKER = 'ParityProbe'
LONG_DESC = 'long description word ' * 20  # >200 chars → truncation on list paths


def _norm(value):
    """Normalize wire-format variants that are NOT divergences:
    ISO datetime strings (Z vs +00:00) and numeric strings vs numbers."""
    if isinstance(value, dict):
        return {k: _norm(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_norm(v) for v in value]
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            pass
        try:
            return Decimal(value)
        except InvalidOperation:
            return value
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    return value


class ItemListParityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test Instance', public_key='test-key')

        def make_profile(username, **profile_kwargs):
            account = Account.objects.create_user(
                username=username, email=f'{username}@test.parahub.io',
                password='x', instance=cls.instance)
            return Profile.objects.create(
                account=account, instance=cls.instance, local_name=username,
                display_name=f'{username.title()} Realname', is_primary=True,
                profile_type=Profile.ProfileType.PERSONAL, **profile_kwargs)

        cls.owner = make_profile('parityowner', name_public=False)
        cls.public_owner = make_profile('paritypublic', name_public=True)
        cls.wot_viewer = make_profile('paritywot', is_verified_wot=True)

        cls.root_cat = Category.objects.create(name='Parity Root', slug='parity-root')
        cls.child_cat = Category.objects.create(
            name='Parity Child', slug='parity-child', parent=cls.root_cat)

        def make_item(owner, title, item_type='CREDIT', **kwargs):
            kwargs.setdefault('category', cls.child_cat)
            kwargs.setdefault('pricing_options', [
                {'type': 'sale', 'amount': '10.00', 'currency': 'EUR',
                 'unit': 'pcs', 'note': 'parity'}])
            return Item.objects.create(
                owner=owner, title=f'{MARKER} {title}', type=item_type, **kwargs)

        cls.item = make_item(
            cls.owner, 'main', description=LONG_DESC,
            location=Point(-8.61024, 41.14961, srid=4326),
            accepted_payment_methods=['CASH'], language='pt',
            self_made=True, attributes={'__demo_seed': True})
        ObjectPhoto.objects.create(
            object_id=cls.item.id, image='items/parity-a.jpg', order=1,
            caption='side', uploaded_by=cls.owner)
        ObjectPhoto.objects.create(
            object_id=cls.item.id, image='items/parity-b.jpg', order=0,
            caption='', uploaded_by=cls.owner)
        cls.item.tags.create(name='parity-beta')
        cls.item.tags.create(name='parity-alpha')

        cls.public_item = make_item(cls.public_owner, 'public-name', description='short')

        # Demand sources for cls.item (CREDIT → demand = visible DEBIT in category):
        make_item(cls.public_owner, 'demand-1', item_type='DEBIT')
        make_item(cls.wot_viewer, 'demand-2', item_type='DEBIT')
        # visible to signed-in viewers only — anon demand must NOT count it
        make_item(cls.wot_viewer, 'demand-registered', item_type='DEBIT',
                  visibility='REGISTERED')
        # the owner's own request must not inflate demand on their own offer
        make_item(cls.owner, 'demand-own', item_type='DEBIT')

        cls.factory = RequestFactory()

    # -- helpers ------------------------------------------------------------

    def _request(self, viewer=None):
        request = self.factory.get('/api/v1/items/')
        if viewer is not None:
            request.user = viewer.account
            request.auth = viewer
            request.auth_profile = viewer
        return request

    def _both_paths(self, viewer=None, **params):
        """Return (raw_items, orm_items) for the same logical query."""
        raw_resp = list_items(self._request(viewer), **params)
        self.assertIsInstance(
            raw_resp, HttpResponse,
            'raw path did not run (fell back to ORM — check logs for the exception)')
        raw = orjson.loads(raw_resp.content)['items']

        orm_resp = list_items(self._request(viewer), q=MARKER, **params)
        self.assertIsInstance(orm_resp, dict, 'ORM path did not run')
        orm = [i.model_dump(mode='json') for i in orm_resp['items']]
        return raw, orm

    def assertParity(self, raw_items, orm_items):
        raw_by_id = {i['id']: i for i in raw_items}
        orm_by_id = {i['id']: i for i in orm_items}
        self.assertEqual(set(raw_by_id), set(orm_by_id), 'result sets differ')
        for iid, raw in raw_by_id.items():
            orm = orm_by_id[iid]
            self.assertEqual(set(raw), set(orm), f'field sets differ for {iid}')
            for field in raw:
                self.assertEqual(
                    _norm(raw[field]), _norm(orm[field]),
                    f'{field} differs for {iid}: raw={raw[field]!r} orm={orm[field]!r}')

    def _main(self, items):
        return next(i for i in items if i['id'] == self.item.id)

    # -- tests --------------------------------------------------------------

    def test_parity_anonymous(self):
        raw, orm = self._both_paths()
        self.assertParity(raw, orm)
        main = self._main(raw)
        # gated name, truncated description, fuzzed location, sorted photos/tags
        self.assertEqual(main['owner_display_name'], '')
        self.assertEqual(len(main['description']), 201)
        self.assertTrue(main['description'].endswith('…'))
        self.assertTrue(main['location']['fuzzed'])
        self.assertEqual([p['order'] for p in main['images']], [0, 1])
        self.assertEqual(main['tags'], ['parity-alpha', 'parity-beta'])
        self.assertTrue(main['is_demo'])
        # public-name owner is visible even to anonymous viewers
        public = next(i for i in raw if i['id'] == self.public_item.id)
        self.assertEqual(public['owner_display_name'], 'Paritypublic Realname')

    def test_parity_owner_viewer(self):
        raw, orm = self._both_paths(viewer=self.owner)
        self.assertParity(raw, orm)
        self.assertEqual(self._main(raw)['owner_display_name'], 'Parityowner Realname')

    def test_parity_wot_viewer(self):
        raw, orm = self._both_paths(viewer=self.wot_viewer)
        self.assertParity(raw, orm)
        self.assertEqual(self._main(raw)['owner_display_name'], 'Parityowner Realname')

    def test_demand_respects_visibility_tiers(self):
        """Demand on the raw path must apply the viewer visibility filter
        (it used to count REGISTERED items for anonymous viewers)."""
        raw, orm = self._both_paths()
        # anon: 2 public DEBIT from others (REGISTERED hidden, own excluded)
        self.assertEqual(self._main(raw)['demand_count'], 2)
        self.assertEqual(self._main(orm)['demand_count'], 2)

        raw_authed, orm_authed = self._both_paths(viewer=self.wot_viewer)
        # signed-in: the REGISTERED request becomes visible → 3
        self.assertEqual(self._main(raw_authed)['demand_count'], 3)
        self.assertEqual(self._main(orm_authed)['demand_count'], 3)

    def test_parity_with_currency_conversion(self):
        with patch('parahub.endpoints.items.ExchangeRate.convert',
                   return_value=Decimal('11.50')):
            raw, orm = self._both_paths(target_currency='USD')
        self.assertParity(raw, orm)
        opt = self._main(raw)['pricing_options'][0]
        self.assertEqual(opt['converted_from'], 'EUR')
        self.assertEqual(opt['currency'], 'USD')
        self.assertEqual(Decimal(str(opt['amount'])), Decimal('11.50'))

    def test_parity_filters(self):
        """WHERE-clause parity for the common filter combinations."""
        for params in (
            {'item_type': 'DEBIT'},
            {'category': self.root_cat.slug},          # descendant expansion
            {'pricing_type': 'sale'},
            {'self_made': True},
            {'owner_id': str(self.owner.id)},
            {'min_price': 5, 'max_price': 20},
        ):
            with self.subTest(params=params):
                raw, orm = self._both_paths(**params)
                self.assertParity(raw, orm)
