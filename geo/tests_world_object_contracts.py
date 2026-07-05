"""
Access-control tests for GET /geo/world-objects/{id}/contracts/.

Invariant: contracts linked to a WorldObject are a private P2P relationship —
visible only to each contract's own parties (creator/partner) or staff.
Anonymous and non-party callers must get an empty list, never other people's
contract titles / counterparties / statuses. (Regression guard for the
2026-07-02 fix that gated this previously-public `auth=None` endpoint.)
"""

from django.test import TestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore

from identity.models import Account, Profile
from contracts.models import Contract
from core.models import Instance
from geo.models import WorldObject
from geo.endpoints.world_objects import list_world_object_contracts


FAKE_SHA256 = 'a' * 64
FAKE_SIGNATURE = '-----BEGIN PGP SIGNATURE-----\nfake\n-----END PGP SIGNATURE-----'


def _make_request(factory, account=None, profile=None):
    """Anonymous request when profile is None; otherwise auth_profile attached."""
    request = factory.get('/fake/')
    if profile is not None:
        request.user = account
        request.auth = profile
        request.auth_profile = profile
        request.session = SessionStore()
        request.session.create()
    return request


class WorldObjectContractsAccessTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')

        def mk(username, is_staff=False):
            acc = Account.objects.create_user(
                username=username, email=f'{username}@test.parahub.io',
                password='x', instance=self.instance, is_staff=is_staff)
            prof = Profile.objects.create(
                account=acc, instance=self.instance, local_name=username,
                display_name=username.title(), is_primary=True)
            return acc, prof

        self.alice_acc, self.alice = mk('alice')          # contract creator
        self.bob_acc, self.bob = mk('bob')                # contract partner
        self.carol_acc, self.carol = mk('carol')          # unrelated third party
        self.dave_acc, self.dave = mk('dave', is_staff=True)  # staff, non-party

        self.wo = WorldObject.objects.create(xeno_source='osm', xeno_id='way/test1')
        self.contract = Contract.objects.create(
            creator=self.alice, partner=self.bob, title='Sur-Ron rental',
            file_sha256=FAKE_SHA256, creator_signature=FAKE_SIGNATURE,
            status=Contract.Status.SIGNED, world_object_id=self.wo.id)

    def _call(self, account=None, profile=None):
        return list_world_object_contracts(
            _make_request(self.factory, account, profile), self.wo.id)

    def test_anonymous_gets_empty(self):
        status, data = self._call()
        self.assertEqual(status, 200)
        self.assertEqual(data, [])

    def test_non_party_gets_empty(self):
        status, data = self._call(self.carol_acc, self.carol)
        self.assertEqual(status, 200)
        self.assertEqual(data, [])

    def test_creator_sees_own_contract(self):
        status, data = self._call(self.alice_acc, self.alice)
        self.assertEqual(status, 200)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['id'], self.contract.id)
        self.assertEqual(data[0]['title'], 'Sur-Ron rental')

    def test_partner_sees_own_contract(self):
        status, data = self._call(self.bob_acc, self.bob)
        self.assertEqual(status, 200)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['id'], self.contract.id)

    def test_staff_sees_all(self):
        status, data = self._call(self.dave_acc, self.dave)
        self.assertEqual(status, 200)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['id'], self.contract.id)

    def test_missing_object_404(self):
        status, data = list_world_object_contracts(
            _make_request(self.factory), 'NONEXISTENT000000000000000')
        self.assertEqual(status, 404)
