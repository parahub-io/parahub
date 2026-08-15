"""Tests for the wallet-sync blob endpoint.

Invariants:
- the flag IS the row: no row = disabled, PUT enables, DELETE disables
- the server treats the ciphertext as opaque and returns it byte-identical
- accounts are isolated — one account can never read another's blob
- size cap and empty-body rejection
"""

from django.test import RequestFactory, TestCase
from ninja.errors import HttpError

from core.models import Instance
from finance.models import WalletSyncBlob
from identity.models import Account
from parahub.endpoints.wallet_sync import (
    MAX_CIPHERTEXT_CHARS, WalletSyncPutRequest,
    delete_wallet_sync, get_wallet_sync, put_wallet_sync,
)


class WalletSyncEndpointTests(TestCase):
    def setUp(self):
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.alice = Account.objects.create_user(
            username='alice', email='alice@test.parahub.io',
            password='x', instance=self.instance)
        self.bob = Account.objects.create_user(
            username='bob', email='bob@test.parahub.io',
            password='x', instance=self.instance)
        self.factory = RequestFactory()

    def _request(self, account):
        request = self.factory.get('/fake/')
        request.auth = account
        return request

    def test_disabled_by_default(self):
        out = get_wallet_sync(self._request(self.alice))
        self.assertEqual(out, {'enabled': False, 'ciphertext': None, 'updated_at': None})

    def test_put_enables_and_roundtrips_opaque_ciphertext(self):
        blob = 'AAAA////base64+not+validated=='
        out = put_wallet_sync(self._request(self.alice), WalletSyncPutRequest(ciphertext=blob))
        self.assertTrue(out['enabled'])
        self.assertIsNotNone(out['updated_at'])

        out = get_wallet_sync(self._request(self.alice))
        self.assertTrue(out['enabled'])
        self.assertEqual(out['ciphertext'], blob)

    def test_put_overwrites_last_write_wins(self):
        put_wallet_sync(self._request(self.alice), WalletSyncPutRequest(ciphertext='v1'))
        put_wallet_sync(self._request(self.alice), WalletSyncPutRequest(ciphertext='v2'))
        self.assertEqual(WalletSyncBlob.objects.filter(account=self.alice).count(), 1)
        out = get_wallet_sync(self._request(self.alice))
        self.assertEqual(out['ciphertext'], 'v2')

    def test_delete_disables_and_removes_row(self):
        put_wallet_sync(self._request(self.alice), WalletSyncPutRequest(ciphertext='v1'))
        out = delete_wallet_sync(self._request(self.alice))
        self.assertEqual(out, {'enabled': False, 'ciphertext': None, 'updated_at': None})
        self.assertFalse(WalletSyncBlob.objects.filter(account=self.alice).exists())
        # Deleting when already disabled is a no-op, not an error.
        out = delete_wallet_sync(self._request(self.alice))
        self.assertFalse(out['enabled'])

    def test_accounts_are_isolated(self):
        put_wallet_sync(self._request(self.alice), WalletSyncPutRequest(ciphertext='alice-secret'))
        out = get_wallet_sync(self._request(self.bob))
        self.assertFalse(out['enabled'])
        self.assertIsNone(out['ciphertext'])

    def test_rejects_empty_and_oversized(self):
        with self.assertRaises(HttpError):
            put_wallet_sync(self._request(self.alice), WalletSyncPutRequest(ciphertext=''))
        with self.assertRaises(HttpError):
            put_wallet_sync(self._request(self.alice), WalletSyncPutRequest(
                ciphertext='x' * (MAX_CIPHERTEXT_CHARS + 1)))
        self.assertFalse(WalletSyncBlob.objects.filter(account=self.alice).exists())
