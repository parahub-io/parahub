"""
Tests for contracts endpoints: create, sign, complete, cancel, items M2M,
arbitration, reviews.

Tests invariants that must never break:
- Dual PGP signature flow (creator signs → partner signs)
- Status lifecycle: PENDING_PARTNER → SIGNED → COMPLETED | CANCELLED
- Both parties must independently confirm completion
- Arbiter cannot be creator or partner
- Auto-deactivation of linked items on COMPLETED
- Authorization: only parties can view/modify their contracts
- File SHA256 format validation (64 hex chars)
- Canonical JSON determinism (sorted keys, no created_at)
"""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from django.test import TestCase, SimpleTestCase, RequestFactory, override_settings
from django.contrib.sessions.backends.db import SessionStore
from ninja.errors import HttpError

from identity.models import Account, Profile
from contracts.models import Contract, ContractReview
from core.models import Instance
from market.models import Item


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


def _create_item(profile, title='Test Item', item_type='CREDIT', **kwargs):
    """Create an Item directly in DB."""
    defaults = dict(
        owner=profile,
        title=title,
        type=item_type,
        description=kwargs.pop('description', 'A test item'),
        pricing_options=kwargs.pop('pricing_options', []),
        accepted_payment_methods=kwargs.pop('accepted_payment_methods', ['cash']),
        is_active=kwargs.pop('is_active', True),
        language=kwargs.pop('language', 'en'),
    )
    defaults.update(kwargs)
    return Item.objects.create(**defaults)


FAKE_SHA256 = 'a' * 64
FAKE_SIGNATURE = '-----BEGIN PGP SIGNATURE-----\nfake\n-----END PGP SIGNATURE-----'
FAKE_PGP_KEY = '-----BEGIN PGP PUBLIC KEY BLOCK-----\nfake\n-----END PGP PUBLIC KEY BLOCK-----'


def _create_contract(creator, partner, title='F1', status=Contract.Status.PENDING_PARTNER,
                     arbiter=None, **kwargs):
    """Create a Contract directly in DB."""
    return Contract.objects.create(
        creator=creator,
        partner=partner,
        arbiter=arbiter,
        title=title,
        file_sha256=kwargs.pop('file_sha256', FAKE_SHA256),
        creator_signature=kwargs.pop('creator_signature', FAKE_SIGNATURE),
        status=status,
        **kwargs,
    )


# ===========================================================================
# Model-level tests (SimpleTestCase — no DB)
# ===========================================================================

class ContractModelLogicTest(SimpleTestCase):
    """Test Contract model methods without DB."""

    def test_status_choices(self):
        self.assertEqual(Contract.Status.PENDING_PARTNER, 'PENDING_PARTNER')
        self.assertEqual(Contract.Status.SIGNED, 'SIGNED')
        self.assertEqual(Contract.Status.COMPLETED, 'COMPLETED')
        self.assertEqual(Contract.Status.CANCELLED, 'CANCELLED')

    def test_is_signed_true(self):
        c = Contract()
        c.status = Contract.Status.SIGNED
        c.partner_signature = FAKE_SIGNATURE
        self.assertTrue(c.is_signed)

    def test_is_signed_false_wrong_status(self):
        c = Contract()
        c.status = Contract.Status.PENDING_PARTNER
        c.partner_signature = FAKE_SIGNATURE
        self.assertFalse(c.is_signed)

    def test_is_signed_false_no_signature(self):
        c = Contract()
        c.status = Contract.Status.SIGNED
        c.partner_signature = None
        self.assertFalse(c.is_signed)

    def test_is_fully_completed_true(self):
        from django.utils import timezone
        c = Contract()
        c.creator_completed_at = timezone.now()
        c.partner_completed_at = timezone.now()
        self.assertTrue(c.is_fully_completed)

    def test_is_fully_completed_false_creator_only(self):
        from django.utils import timezone
        c = Contract()
        c.creator_completed_at = timezone.now()
        c.partner_completed_at = None
        self.assertFalse(c.is_fully_completed)

    def test_is_fully_completed_false_partner_only(self):
        from django.utils import timezone
        c = Contract()
        c.creator_completed_at = None
        c.partner_completed_at = timezone.now()
        self.assertFalse(c.is_fully_completed)

    def test_is_fully_completed_false_neither(self):
        c = Contract()
        c.creator_completed_at = None
        c.partner_completed_at = None
        self.assertFalse(c.is_fully_completed)


# ===========================================================================
# DB-backed tests: Canonical JSON (needs FK access)
# ===========================================================================

@patch('audit_log.signals._create_pending_proof', return_value=None)
class ContractCanonicalTextTest(TestCase):
    """Test canonical JSON generation for PGP signing."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance, pgp_public_key=FAKE_PGP_KEY)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob', pgp_public_key=FAKE_PGP_KEY)

    def test_canonical_sorted_keys(self, _mock_proof):
        """Keys must be alphabetically sorted for deterministic hashing."""
        contract = _create_contract(self.alice, self.bob)
        text = contract.get_canonical_text()
        import json
        parsed = json.loads(text)
        keys = list(parsed.keys())
        self.assertEqual(keys, sorted(keys))

    def test_canonical_no_created_at(self, _mock_proof):
        """CRITICAL: created_at must NOT be in canonical JSON."""
        contract = _create_contract(self.alice, self.bob)
        text = contract.get_canonical_text()
        self.assertNotIn('created_at', text)

    def test_canonical_with_arbiter(self, _mock_proof):
        """Arbiter ID included when present."""
        charlie_account = _create_account(self.instance, 'charlie')
        charlie = _create_profile(charlie_account, self.instance, local_name='charlie')
        contract = _create_contract(self.alice, self.bob, arbiter=charlie)
        text = contract.get_canonical_text()
        import json
        parsed = json.loads(text)
        self.assertIn('arbiter_id', parsed)
        self.assertEqual(parsed['arbiter_id'], charlie.id)

    def test_canonical_without_arbiter(self, _mock_proof):
        """No arbiter_id key when arbiter is None."""
        contract = _create_contract(self.alice, self.bob)
        text = contract.get_canonical_text()
        self.assertNotIn('arbiter_id', text)

    def test_canonical_compact_json(self, _mock_proof):
        """JSON must be compact (no spaces) — matches Python separators=(',',':')."""
        contract = _create_contract(self.alice, self.bob)
        text = contract.get_canonical_text()
        self.assertNotIn(': ', text)
        self.assertNotIn(', ', text)

    def test_canonical_deterministic(self, _mock_proof):
        """Same contract produces same canonical text on repeated calls."""
        contract = _create_contract(self.alice, self.bob)
        text1 = contract.get_canonical_text()
        text2 = contract.get_canonical_text()
        self.assertEqual(text1, text2)


# ===========================================================================
# DB-backed tests: Contract Creation
# ===========================================================================

@patch('audit_log.signals._create_pending_proof', return_value=None)
class ContractCreateTest(TestCase):
    """Test contract creation endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance,
                                     pgp_public_key=FAKE_PGP_KEY)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob',
                                   pgp_public_key=FAKE_PGP_KEY)
        self.factory = RequestFactory()

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_create_contract_basic(self, mock_pgp, _mock_proof):
        """Create contract with minimum required fields."""
        mock_pgp.verify_signature.return_value = True

        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='F1',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = create_contract(request, data)

        self.assertEqual(response.title, 'F1')
        self.assertEqual(response.creator_id, self.alice.id)
        self.assertEqual(response.partner_id, self.bob.id)
        self.assertEqual(response.status, 'PENDING_PARTNER')
        self.assertEqual(response.object_type, 'contract')
        self.assertIsNone(response.arbiter_id)
        self.assertEqual(response.file_sha256, FAKE_SHA256)
        self.assertEqual(Contract.objects.count(), 1)

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_create_contract_with_arbiter(self, mock_pgp, _mock_proof):
        """Create contract with optional arbiter."""
        mock_pgp.verify_signature.return_value = True

        charlie_account = _create_account(self.instance, 'charlie')
        charlie = _create_profile(charlie_account, self.instance, local_name='charlie')

        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='F1',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
            arbiter_id=charlie.id,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = create_contract(request, data)

        self.assertEqual(response.arbiter_id, charlie.id)

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_create_contract_with_items(self, mock_pgp, _mock_proof):
        """Create contract with linked items (M2M)."""
        mock_pgp.verify_signature.return_value = True

        item1 = _create_item(self.alice, title='Bicycle')
        item2 = _create_item(self.bob, title='Laptop')

        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='F1',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
            item_ids=[item1.id, item2.id],
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = create_contract(request, data)

        self.assertEqual(len(response.items), 2)
        item_ids = {i.id for i in response.items}
        self.assertIn(item1.id, item_ids)
        self.assertIn(item2.id, item_ids)

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_create_contract_items_must_be_active(self, mock_pgp, _mock_proof):
        """Inactive items are filtered out when linking."""
        mock_pgp.verify_signature.return_value = True

        active_item = _create_item(self.alice, title='Active')
        inactive_item = _create_item(self.alice, title='Inactive', is_active=False)

        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='F1',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
            item_ids=[active_item.id, inactive_item.id],
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = create_contract(request, data)

        self.assertEqual(len(response.items), 1)
        self.assertEqual(response.items[0].id, active_item.id)

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_create_contract_items_must_belong_to_parties(self, mock_pgp, _mock_proof):
        """Items not owned by creator or partner are filtered out."""
        mock_pgp.verify_signature.return_value = True

        charlie_account = _create_account(self.instance, 'charlie')
        charlie = _create_profile(charlie_account, self.instance, local_name='charlie')
        charlie_item = _create_item(charlie, title='Not yours')

        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='F1',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
            item_ids=[charlie_item.id],
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = create_contract(request, data)

        self.assertEqual(len(response.items), 0)

    def test_create_contract_self_contract_rejected(self, _mock_proof):
        """Cannot create contract with yourself."""
        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        data = ContractCreateRequest(
            partner_id=self.alice.id,
            title='F1',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_contract(request, data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('yourself', str(ctx.exception))

    def test_create_contract_partner_not_found(self, _mock_proof):
        """Non-existent partner raises 404."""
        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        data = ContractCreateRequest(
            partner_id='NONEXISTENT000000000000000',
            title='F1',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_contract(request, data)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_create_contract_arbiter_is_creator_rejected(self, _mock_proof):
        """Arbiter cannot be the creator."""
        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='F1',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
            arbiter_id=self.alice.id,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_contract(request, data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('Arbiter', str(ctx.exception))

    def test_create_contract_arbiter_is_partner_rejected(self, _mock_proof):
        """Arbiter cannot be the partner."""
        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='F1',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
            arbiter_id=self.bob.id,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_contract(request, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_contract_empty_title_rejected(self, _mock_proof):
        """Empty title raises 400."""
        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='   ',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_contract(request, data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('Title', str(ctx.exception))

    def test_create_contract_invalid_sha256_rejected(self, _mock_proof):
        """SHA256 hash must be exactly 64 hex chars."""
        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='F1',
            file_sha256='tooshort',
            signature=FAKE_SIGNATURE,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_contract(request, data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('SHA256', str(ctx.exception))

    def test_create_contract_no_pgp_key_rejected(self, _mock_proof):
        """Creator without PGP key cannot create contract."""
        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        no_key_account = _create_account(self.instance, 'nokey')
        no_key_profile = _create_profile(no_key_account, self.instance, local_name='nokey')

        data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='F1',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
        )
        request = _make_auth_request(self.factory, no_key_account, no_key_profile, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_contract(request, data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('PGP', str(ctx.exception))

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_create_contract_invalid_signature_rejected(self, mock_pgp, _mock_proof):
        """Invalid PGP signature rolls back contract creation."""
        mock_pgp.verify_signature.return_value = False

        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='F1',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_contract(request, data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('signature', str(ctx.exception).lower())
        # Contract should NOT be in DB (transaction rolled back)
        self.assertEqual(Contract.objects.count(), 0)

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_create_contract_pgp_verification_error(self, mock_pgp, _mock_proof):
        """PGPVerificationError from crypto layer raises 400."""
        from parahub.crypto.pgp import PGPVerificationError
        mock_pgp.verify_signature.side_effect = PGPVerificationError("bad key")

        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='F1',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_contract(request, data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(Contract.objects.count(), 0)

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_create_contract_sha256_lowercased(self, mock_pgp, _mock_proof):
        """SHA256 hash is stored lowercase."""
        mock_pgp.verify_signature.return_value = True

        from parahub.endpoints.contracts import create_contract, ContractCreateRequest

        upper_sha = 'A' * 64
        data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='F1',
            file_sha256=upper_sha,
            signature=FAKE_SIGNATURE,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = create_contract(request, data)

        self.assertEqual(response.file_sha256, 'a' * 64)


# ===========================================================================
# DB-backed tests: Contract Listing
# ===========================================================================

@patch('audit_log.signals._create_pending_proof', return_value=None)
class ContractListTest(TestCase):
    """Test contract list endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance,
                                     pgp_public_key=FAKE_PGP_KEY)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob',
                                   pgp_public_key=FAKE_PGP_KEY)
        self.charlie_account = _create_account(self.instance, 'charlie')
        self.charlie = _create_profile(self.charlie_account, self.instance, local_name='charlie')
        self.factory = RequestFactory()

    def test_list_contracts_as_creator(self, _mock_proof):
        """Creator sees contracts they created."""
        _create_contract(self.alice, self.bob, title='F1')
        _create_contract(self.alice, self.bob, title='F2')

        from parahub.endpoints.contracts import list_contracts
        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        response = list_contracts(request)

        self.assertEqual(len(response), 2)

    def test_list_contracts_as_partner(self, _mock_proof):
        """Partner sees contracts where they are partner."""
        _create_contract(self.alice, self.bob, title='F1')

        from parahub.endpoints.contracts import list_contracts
        request = _make_auth_request(self.factory, self.bob_account, self.bob)
        response = list_contracts(request)

        self.assertEqual(len(response), 1)
        self.assertEqual(response[0].title, 'F1')

    def test_list_contracts_excludes_unrelated(self, _mock_proof):
        """User does not see contracts they are not part of."""
        _create_contract(self.alice, self.bob, title='F1')

        from parahub.endpoints.contracts import list_contracts
        request = _make_auth_request(self.factory, self.charlie_account, self.charlie)
        response = list_contracts(request)

        self.assertEqual(len(response), 0)

    def test_list_contracts_filter_by_status(self, _mock_proof):
        """Status filter returns only matching contracts."""
        _create_contract(self.alice, self.bob, title='Pending',
                         status=Contract.Status.PENDING_PARTNER)
        _create_contract(self.alice, self.bob, title='Signed',
                         status=Contract.Status.SIGNED,
                         partner_signature=FAKE_SIGNATURE)

        from parahub.endpoints.contracts import list_contracts
        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        response = list_contracts(request, status='SIGNED')

        self.assertEqual(len(response), 1)
        self.assertEqual(response[0].title, 'Signed')

    def test_list_contracts_empty(self, _mock_proof):
        """Empty list when no contracts exist."""
        from parahub.endpoints.contracts import list_contracts
        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        response = list_contracts(request)

        self.assertEqual(len(response), 0)


# ===========================================================================
# DB-backed tests: Contract Detail
# ===========================================================================

@patch('audit_log.signals._create_pending_proof', return_value=None)
class ContractDetailTest(TestCase):
    """Test contract detail endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance,
                                     pgp_public_key=FAKE_PGP_KEY)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob',
                                   pgp_public_key=FAKE_PGP_KEY)
        self.charlie_account = _create_account(self.instance, 'charlie')
        self.charlie = _create_profile(self.charlie_account, self.instance, local_name='charlie')
        self.factory = RequestFactory()

    def test_detail_as_creator(self, _mock_proof):
        """Creator can view contract details."""
        contract = _create_contract(self.alice, self.bob)

        from parahub.endpoints.contracts import get_contract
        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        response = get_contract(request, contract.id)

        self.assertEqual(response.id, contract.id)
        self.assertEqual(response.title, 'F1')
        self.assertEqual(response.object_type, 'contract')

    def test_detail_as_partner(self, _mock_proof):
        """Partner can view contract details."""
        contract = _create_contract(self.alice, self.bob)

        from parahub.endpoints.contracts import get_contract
        request = _make_auth_request(self.factory, self.bob_account, self.bob)
        response = get_contract(request, contract.id)

        self.assertEqual(response.id, contract.id)

    def test_detail_unauthorized(self, _mock_proof):
        """Non-party user cannot view contract."""
        contract = _create_contract(self.alice, self.bob)

        from parahub.endpoints.contracts import get_contract
        request = _make_auth_request(self.factory, self.charlie_account, self.charlie)

        with self.assertRaises(HttpError) as ctx:
            get_contract(request, contract.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_detail_not_found(self, _mock_proof):
        """Non-existent contract raises 404."""
        from parahub.endpoints.contracts import get_contract
        request = _make_auth_request(self.factory, self.alice_account, self.alice)

        with self.assertRaises(HttpError) as ctx:
            get_contract(request, 'NONEXISTENT000000000000000')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_detail_includes_items(self, _mock_proof):
        """Contract detail includes linked items."""
        contract = _create_contract(self.alice, self.bob)
        item = _create_item(self.alice, title='Bike')
        contract.items.add(item)

        from parahub.endpoints.contracts import get_contract
        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        response = get_contract(request, contract.id)

        self.assertEqual(len(response.items), 1)
        self.assertEqual(response.items[0].title, 'Bike')


# ===========================================================================
# DB-backed tests: Contract Signing
# ===========================================================================

@patch('audit_log.signals._create_pending_proof', return_value=None)
class ContractSignTest(TestCase):
    """Test contract signing endpoint (partner signs)."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance,
                                     pgp_public_key=FAKE_PGP_KEY)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob',
                                   pgp_public_key=FAKE_PGP_KEY)
        self.factory = RequestFactory()
        self.contract = _create_contract(self.alice, self.bob)

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_sign_contract_success(self, mock_pgp, _mock_proof):
        """Partner signs contract, status becomes SIGNED."""
        mock_pgp.verify_signature.return_value = True

        from parahub.endpoints.contracts import sign_contract, ContractSignRequest

        data = ContractSignRequest(signature=FAKE_SIGNATURE)
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        response = sign_contract(request, self.contract.id, data)

        self.assertEqual(response.status, 'SIGNED')
        self.assertIsNotNone(response.partner_signed_at)

        # Verify DB state
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.status, Contract.Status.SIGNED)
        self.assertEqual(self.contract.partner_signature, FAKE_SIGNATURE)

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_sign_contract_creator_cannot_sign(self, mock_pgp, _mock_proof):
        """Creator cannot sign their own contract (only partner can)."""
        mock_pgp.verify_signature.return_value = True

        from parahub.endpoints.contracts import sign_contract, ContractSignRequest

        data = ContractSignRequest(signature=FAKE_SIGNATURE)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            sign_contract(request, self.contract.id, data)
        self.assertEqual(ctx.exception.status_code, 403)

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_sign_already_signed_rejected(self, mock_pgp, _mock_proof):
        """Cannot sign an already signed contract."""
        mock_pgp.verify_signature.return_value = True
        self.contract.status = Contract.Status.SIGNED
        self.contract.partner_signature = FAKE_SIGNATURE
        self.contract.save()

        from parahub.endpoints.contracts import sign_contract, ContractSignRequest

        data = ContractSignRequest(signature=FAKE_SIGNATURE)
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')

        with self.assertRaises(HttpError) as ctx:
            sign_contract(request, self.contract.id, data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('already signed', str(ctx.exception).lower())

    def test_sign_partner_no_pgp_key_rejected(self, _mock_proof):
        """Partner without PGP key cannot sign."""
        no_key_account = _create_account(self.instance, 'nokey')
        no_key_profile = _create_profile(no_key_account, self.instance, local_name='nokey')

        contract = _create_contract(self.alice, no_key_profile)

        from parahub.endpoints.contracts import sign_contract, ContractSignRequest

        data = ContractSignRequest(signature=FAKE_SIGNATURE)
        request = _make_auth_request(self.factory, no_key_account, no_key_profile, 'post')

        with self.assertRaises(HttpError) as ctx:
            sign_contract(request, contract.id, data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('PGP', str(ctx.exception))

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_sign_invalid_signature_rejected(self, mock_pgp, _mock_proof):
        """Invalid PGP signature raises 400."""
        mock_pgp.verify_signature.return_value = False

        from parahub.endpoints.contracts import sign_contract, ContractSignRequest

        data = ContractSignRequest(signature=FAKE_SIGNATURE)
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')

        with self.assertRaises(HttpError) as ctx:
            sign_contract(request, self.contract.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_sign_not_found(self, _mock_proof):
        """Signing non-existent contract raises 404."""
        from parahub.endpoints.contracts import sign_contract, ContractSignRequest

        data = ContractSignRequest(signature=FAKE_SIGNATURE)
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')

        with self.assertRaises(HttpError) as ctx:
            sign_contract(request, 'NONEXISTENT000000000000000', data)
        self.assertEqual(ctx.exception.status_code, 404)


# ===========================================================================
# DB-backed tests: Contract Cancel
# ===========================================================================

@patch('audit_log.signals._create_pending_proof', return_value=None)
class ContractCancelTest(TestCase):
    """Test contract cancel/reject endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance,
                                     pgp_public_key=FAKE_PGP_KEY)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob',
                                   pgp_public_key=FAKE_PGP_KEY)
        self.charlie_account = _create_account(self.instance, 'charlie')
        self.charlie = _create_profile(self.charlie_account, self.instance, local_name='charlie')
        self.factory = RequestFactory()

    def test_cancel_by_creator(self, _mock_proof):
        """Creator can cancel pending contract."""
        contract = _create_contract(self.alice, self.bob)

        from parahub.endpoints.contracts import cancel_contract
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'delete')
        response = cancel_contract(request, contract.id)

        self.assertIn('cancelled', response['message'])
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.CANCELLED)

    def test_reject_by_partner(self, _mock_proof):
        """Partner can reject pending contract."""
        contract = _create_contract(self.alice, self.bob)

        from parahub.endpoints.contracts import cancel_contract
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'delete')
        response = cancel_contract(request, contract.id)

        self.assertIn('rejected', response['message'])
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.CANCELLED)

    def test_cancel_signed_contract_rejected(self, _mock_proof):
        """Cannot cancel already signed contract."""
        contract = _create_contract(self.alice, self.bob, status=Contract.Status.SIGNED)

        from parahub.endpoints.contracts import cancel_contract
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'delete')

        with self.assertRaises(HttpError) as ctx:
            cancel_contract(request, contract.id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('pending', str(ctx.exception).lower())

    def test_cancel_unauthorized(self, _mock_proof):
        """Non-party user cannot cancel."""
        contract = _create_contract(self.alice, self.bob)

        from parahub.endpoints.contracts import cancel_contract
        request = _make_auth_request(self.factory, self.charlie_account, self.charlie, 'delete')

        with self.assertRaises(HttpError) as ctx:
            cancel_contract(request, contract.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_cancel_not_found(self, _mock_proof):
        """Cancel non-existent contract raises 404."""
        from parahub.endpoints.contracts import cancel_contract
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'delete')

        with self.assertRaises(HttpError) as ctx:
            cancel_contract(request, 'NONEXISTENT000000000000000')
        self.assertEqual(ctx.exception.status_code, 404)


# ===========================================================================
# DB-backed tests: Contract Completion (Dual)
# ===========================================================================

@patch('audit_log.signals._create_pending_proof', return_value=None)
class ContractCompleteTest(TestCase):
    """Test contract completion endpoint (dual completion)."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance,
                                     pgp_public_key=FAKE_PGP_KEY)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob',
                                   pgp_public_key=FAKE_PGP_KEY)
        self.charlie_account = _create_account(self.instance, 'charlie')
        self.charlie = _create_profile(self.charlie_account, self.instance, local_name='charlie')
        self.factory = RequestFactory()
        # Create a SIGNED contract for completion tests
        self.contract = _create_contract(
            self.alice, self.bob, status=Contract.Status.SIGNED,
            partner_signature=FAKE_SIGNATURE,
        )

    def test_creator_completes_first(self, _mock_proof):
        """Creator marks complete — status stays SIGNED (waiting for partner)."""
        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest

        data = ContractCompleteRequest()
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = complete_contract(request, self.contract.id, data)

        self.assertEqual(response.status, 'SIGNED')
        self.assertIsNotNone(response.creator_completed_at)
        self.assertIsNone(response.partner_completed_at)

    def test_partner_completes_first(self, _mock_proof):
        """Partner marks complete — status stays SIGNED (waiting for creator)."""
        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest

        data = ContractCompleteRequest()
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        response = complete_contract(request, self.contract.id, data)

        self.assertEqual(response.status, 'SIGNED')
        self.assertIsNone(response.creator_completed_at)
        self.assertIsNotNone(response.partner_completed_at)

    def test_dual_completion_becomes_completed(self, _mock_proof):
        """Both parties complete → status becomes COMPLETED."""
        from django.utils import timezone
        self.contract.creator_completed_at = timezone.now()
        self.contract.save()

        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest

        data = ContractCompleteRequest()
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        response = complete_contract(request, self.contract.id, data)

        self.assertEqual(response.status, 'COMPLETED')
        self.assertIsNotNone(response.creator_completed_at)
        self.assertIsNotNone(response.partner_completed_at)

    def test_complete_pending_contract_rejected(self, _mock_proof):
        """Cannot complete a pending (unsigned) contract."""
        pending_contract = _create_contract(self.alice, self.bob,
                                             status=Contract.Status.PENDING_PARTNER)

        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest

        data = ContractCompleteRequest()
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            complete_contract(request, pending_contract.id, data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('signed', str(ctx.exception).lower())

    def test_double_complete_rejected(self, _mock_proof):
        """Same party cannot complete twice."""
        from django.utils import timezone
        self.contract.creator_completed_at = timezone.now()
        self.contract.save()

        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest

        data = ContractCompleteRequest()
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            complete_contract(request, self.contract.id, data)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('already', str(ctx.exception).lower())

    def test_complete_unauthorized(self, _mock_proof):
        """Non-party user cannot complete."""
        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest

        data = ContractCompleteRequest()
        request = _make_auth_request(self.factory, self.charlie_account, self.charlie, 'post')

        with self.assertRaises(HttpError) as ctx:
            complete_contract(request, self.contract.id, data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_complete_with_review(self, _mock_proof):
        """Completion with review creates ContractReview."""
        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest

        data = ContractCompleteRequest(review_text='Great work!', rating=5)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        complete_contract(request, self.contract.id, data)

        reviews = ContractReview.objects.filter(contract=self.contract)
        self.assertEqual(reviews.count(), 1)
        review = reviews.first()
        self.assertEqual(review.reviewer_id, self.alice.id)
        self.assertEqual(review.reviewed_id, self.bob.id)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, 'Great work!')

    def test_complete_without_review(self, _mock_proof):
        """Completion without review data creates no review."""
        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest

        data = ContractCompleteRequest()
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        complete_contract(request, self.contract.id, data)

        self.assertEqual(ContractReview.objects.count(), 0)

    def test_complete_review_unique_per_party(self, _mock_proof):
        """Same party cannot leave two reviews (duplicate check in endpoint)."""
        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest

        data = ContractCompleteRequest(review_text='Good', rating=4)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        complete_contract(request, self.contract.id, data)

        self.assertEqual(ContractReview.objects.filter(
            contract=self.contract, reviewer=self.alice
        ).count(), 1)

    def test_both_parties_review(self, _mock_proof):
        """Both parties can leave independent reviews."""
        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest

        # Creator reviews
        data = ContractCompleteRequest(review_text='Great partner', rating=5)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        complete_contract(request, self.contract.id, data)

        # Partner reviews
        data = ContractCompleteRequest(review_text='Nice creator', rating=4)
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        complete_contract(request, self.contract.id, data)

        self.assertEqual(ContractReview.objects.filter(contract=self.contract).count(), 2)

        creator_review = ContractReview.objects.get(reviewer=self.alice)
        self.assertEqual(creator_review.reviewed_id, self.bob.id)
        self.assertEqual(creator_review.rating, 5)

        partner_review = ContractReview.objects.get(reviewer=self.bob)
        self.assertEqual(partner_review.reviewed_id, self.alice.id)
        self.assertEqual(partner_review.rating, 4)

    def test_complete_review_default_rating(self, _mock_proof):
        """Rating defaults to 5 when review_text is given but no rating."""
        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest

        data = ContractCompleteRequest(review_text='All good')
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        complete_contract(request, self.contract.id, data)

        review = ContractReview.objects.get(contract=self.contract)
        self.assertEqual(review.rating, 5)


# ===========================================================================
# DB-backed tests: Items Auto-Deactivation on COMPLETED
# ===========================================================================

@patch('audit_log.signals._create_pending_proof', return_value=None)
class ContractItemsDeactivationTest(TestCase):
    """Test auto-deactivation of linked items when contract becomes COMPLETED."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance,
                                     pgp_public_key=FAKE_PGP_KEY)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob',
                                   pgp_public_key=FAKE_PGP_KEY)
        self.factory = RequestFactory()

    def test_items_deactivated_on_full_completion(self, _mock_proof):
        """Linked items set is_active=False when both parties complete."""
        from django.utils import timezone

        item1 = _create_item(self.alice, title='Bike')
        item2 = _create_item(self.bob, title='Laptop')

        contract = _create_contract(
            self.alice, self.bob, status=Contract.Status.SIGNED,
            partner_signature=FAKE_SIGNATURE,
        )
        contract.items.set([item1, item2])

        # Creator already completed
        contract.creator_completed_at = timezone.now()
        contract.save()

        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest

        data = ContractCompleteRequest()
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        response = complete_contract(request, contract.id, data)

        self.assertEqual(response.status, 'COMPLETED')

        item1.refresh_from_db()
        item2.refresh_from_db()
        self.assertFalse(item1.is_active)
        self.assertFalse(item2.is_active)

    def test_items_not_deactivated_on_single_completion(self, _mock_proof):
        """Items stay active when only one party completes."""
        item = _create_item(self.alice, title='Bike')

        contract = _create_contract(
            self.alice, self.bob, status=Contract.Status.SIGNED,
            partner_signature=FAKE_SIGNATURE,
        )
        contract.items.add(item)

        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest

        data = ContractCompleteRequest()
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        complete_contract(request, contract.id, data)

        item.refresh_from_db()
        self.assertTrue(item.is_active)


# ===========================================================================
# DB-backed tests: Arbitration
# ===========================================================================

@patch('audit_log.signals._create_pending_proof', return_value=None)
class ContractArbitrationTest(TestCase):
    """Test arbitration initiation endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance,
                                     pgp_public_key=FAKE_PGP_KEY)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob',
                                   pgp_public_key=FAKE_PGP_KEY)
        self.arbiter_account = _create_account(self.instance, 'arbiter')
        self.arbiter = _create_profile(self.arbiter_account, self.instance, local_name='arbiter')
        self.factory = RequestFactory()

    @patch('parahub.endpoints.contracts.create_arbitration_room', return_value='!room123:parahub.io')
    @patch('parahub.endpoints.contracts.spawn')
    def test_initiate_arbitration_success(self, mock_spawn, mock_room, _mock_proof):
        """Creator initiates arbitration, Matrix room created."""
        contract = _create_contract(
            self.alice, self.bob, status=Contract.Status.SIGNED,
            arbiter=self.arbiter, partner_signature=FAKE_SIGNATURE,
        )

        from parahub.endpoints.contracts import initiate_arbitration
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = initiate_arbitration(request, contract.id)

        self.assertEqual(response.arbitration_room_id, '!room123:parahub.io')
        self.assertIsNotNone(response.arbitration_initiated_at)
        self.assertEqual(response.arbitration_initiator_id, self.alice.id)

    def test_arbitration_no_arbiter_rejected(self, _mock_proof):
        """Cannot initiate arbitration without arbiter."""
        contract = _create_contract(
            self.alice, self.bob, status=Contract.Status.SIGNED,
            partner_signature=FAKE_SIGNATURE,
        )

        from parahub.endpoints.contracts import initiate_arbitration
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            initiate_arbitration(request, contract.id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('arbiter', str(ctx.exception).lower())

    def test_arbitration_pending_contract_rejected(self, _mock_proof):
        """Cannot initiate arbitration on pending contract."""
        contract = _create_contract(
            self.alice, self.bob, status=Contract.Status.PENDING_PARTNER,
            arbiter=self.arbiter,
        )

        from parahub.endpoints.contracts import initiate_arbitration
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            initiate_arbitration(request, contract.id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('signed', str(ctx.exception).lower())

    @patch('parahub.endpoints.contracts.create_arbitration_room', return_value='!room:parahub.io')
    @patch('parahub.endpoints.contracts.spawn')
    def test_arbitration_already_initiated_rejected(self, mock_spawn, mock_room, _mock_proof):
        """Cannot initiate arbitration twice."""
        contract = _create_contract(
            self.alice, self.bob, status=Contract.Status.SIGNED,
            arbiter=self.arbiter, partner_signature=FAKE_SIGNATURE,
        )
        contract.arbitration_room_id = '!existing:parahub.io'
        contract.save()

        from parahub.endpoints.contracts import initiate_arbitration
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            initiate_arbitration(request, contract.id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('already', str(ctx.exception).lower())

    def test_arbitration_unauthorized(self, _mock_proof):
        """Non-party user cannot initiate arbitration."""
        contract = _create_contract(
            self.alice, self.bob, status=Contract.Status.SIGNED,
            arbiter=self.arbiter, partner_signature=FAKE_SIGNATURE,
        )

        charlie_account = _create_account(self.instance, 'charlie')
        charlie = _create_profile(charlie_account, self.instance, local_name='charlie')

        from parahub.endpoints.contracts import initiate_arbitration
        request = _make_auth_request(self.factory, charlie_account, charlie, 'post')

        with self.assertRaises(HttpError) as ctx:
            initiate_arbitration(request, contract.id)
        self.assertEqual(ctx.exception.status_code, 403)

    @patch('parahub.endpoints.contracts.create_arbitration_room', return_value=None)
    def test_arbitration_room_creation_fails(self, mock_room, _mock_proof):
        """Matrix room creation failure raises 500."""
        contract = _create_contract(
            self.alice, self.bob, status=Contract.Status.SIGNED,
            arbiter=self.arbiter, partner_signature=FAKE_SIGNATURE,
        )

        from parahub.endpoints.contracts import initiate_arbitration
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            initiate_arbitration(request, contract.id)
        self.assertEqual(ctx.exception.status_code, 500)


# ===========================================================================
# DB-backed tests: Full Lifecycle
# ===========================================================================

@patch('audit_log.signals._create_pending_proof', return_value=None)
class ContractLifecycleTest(TestCase):
    """Test complete contract lifecycle: create → sign → complete."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance,
                                     pgp_public_key=FAKE_PGP_KEY)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob',
                                   pgp_public_key=FAKE_PGP_KEY)
        self.factory = RequestFactory()

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_full_lifecycle(self, mock_pgp, _mock_proof):
        """Create → Sign → Dual Complete with items and reviews."""
        mock_pgp.verify_signature.return_value = True

        from parahub.endpoints.contracts import (
            create_contract, sign_contract, complete_contract,
            ContractCreateRequest, ContractSignRequest, ContractCompleteRequest,
        )

        item = _create_item(self.alice, title='Bicycle')

        # 1. Creator creates
        create_data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='Bike Sale',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
            item_ids=[item.id],
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        created = create_contract(request, create_data)
        self.assertEqual(created.status, 'PENDING_PARTNER')
        self.assertEqual(len(created.items), 1)
        contract_id = created.id

        # 2. Partner signs
        sign_data = ContractSignRequest(signature=FAKE_SIGNATURE)
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        signed = sign_contract(request, contract_id, sign_data)
        self.assertEqual(signed.status, 'SIGNED')

        # 3. Creator completes with review
        complete_data = ContractCompleteRequest(review_text='Smooth trade', rating=5)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        half_done = complete_contract(request, contract_id, complete_data)
        self.assertEqual(half_done.status, 'SIGNED')  # Still waiting for partner

        # 4. Partner completes with review
        complete_data = ContractCompleteRequest(review_text='Great bike', rating=4)
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        done = complete_contract(request, contract_id, complete_data)
        self.assertEqual(done.status, 'COMPLETED')

        # Verify: item auto-deactivated
        item.refresh_from_db()
        self.assertFalse(item.is_active)

        # Verify: both reviews exist
        self.assertEqual(ContractReview.objects.filter(
            contract_id=contract_id
        ).count(), 2)

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_create_then_cancel(self, mock_pgp, _mock_proof):
        """Create → Cancel lifecycle."""
        mock_pgp.verify_signature.return_value = True

        from parahub.endpoints.contracts import (
            create_contract, cancel_contract,
            ContractCreateRequest,
        )

        create_data = ContractCreateRequest(
            partner_id=self.bob.id,
            title='F1',
            file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        created = create_contract(request, create_data)

        # Partner rejects
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'delete')
        result = cancel_contract(request, created.id)
        self.assertIn('rejected', result['message'])

        contract = Contract.objects.get(id=created.id)
        self.assertEqual(contract.status, Contract.Status.CANCELLED)


# ===========================================================================
# DB-backed tests: Native Rental Contract (document_text + Booking link + kind)
# ===========================================================================

@patch('audit_log.signals._create_pending_proof', return_value=None)
class ContractRentalDocumentTest(TestCase):
    """Native rental contract: server-stored PRIVATE body + Booking link + kind=RENTAL.

    Invariants:
    - document_text is stored and returned to the parties (not in canonical text).
    - A CONFIRMED booking links to the contract only for a party to the booking.
    - kind=RENTAL keeps the linked item active on completion (only SALE consumes it).
    - Legacy/upload contracts (no document_text) stay backward-compatible (blank body).
    """

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance, pgp_public_key=FAKE_PGP_KEY)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob', pgp_public_key=FAKE_PGP_KEY)
        self.factory = RequestFactory()

    def _make_booking(self, owner, renter, status='CONFIRMED'):
        """A CONFIRMED booking on an item owned by `owner`, rented by `renter`."""
        from datetime import timedelta
        from decimal import Decimal
        from django.utils import timezone
        from rental.models import Bookable, Booking
        item = _create_item(owner, title='Sur-Ron Ultra Bee')
        bookable = Bookable.objects.create(item=item)
        start = timezone.now() + timedelta(days=1)
        booking = Booking.objects.create(
            bookable=bookable, renter=renter, created_by=owner,
            start=start, end=start + timedelta(days=1), status=status,
            price_total=Decimal('50'), currency='EUR', deposit_amount=Decimal('100'),
            mode='RANGE', unit='month',
        )
        return item, booking

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_rental_contract_stores_body_and_links_booking(self, mock_pgp, _mock_proof):
        """RENTAL contract stores the private body and links its CONFIRMED booking."""
        mock_pgp.verify_signature.return_value = True
        item, booking = self._make_booking(self.alice, self.bob)
        body = '<h3>Contrato</h3><p>Caução: 100 EUR</p>'

        from parahub.endpoints.contracts import create_contract, ContractCreateRequest
        data = ContractCreateRequest(
            partner_id=self.bob.id, title='Aluguer — Sur-Ron',
            file_sha256=FAKE_SHA256, signature=FAKE_SIGNATURE,
            kind='RENTAL', document_text=body, document_format='html',
            item_ids=[item.id], booking_id=booking.id,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = create_contract(request, data)

        self.assertEqual(response.document_text, body)
        self.assertEqual(response.document_format, 'html')
        # kind is not part of the response schema → assert on the persisted row
        contract = Contract.objects.get(id=response.id)
        self.assertEqual(contract.kind, Contract.Kind.RENTAL)
        # document body is NOT in the signed canonical text (signatures stay valid)
        self.assertNotIn('document_text', contract.get_canonical_text())
        # the booking is now linked to the contract
        booking.refresh_from_db()
        self.assertEqual(booking.contract_id, response.id)

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_document_text_visible_to_partner(self, mock_pgp, _mock_proof):
        """The counterparty can read the stored body via the contract detail."""
        mock_pgp.verify_signature.return_value = True
        contract = _create_contract(self.alice, self.bob,
                                    document_text='<p>private terms</p>',
                                    kind=Contract.Kind.RENTAL)

        from parahub.endpoints.contracts import get_contract
        request = _make_auth_request(self.factory, self.bob_account, self.bob)
        response = get_contract(request, contract.id)
        self.assertEqual(response.document_text, '<p>private terms</p>')

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_legacy_contract_has_blank_body(self, mock_pgp, _mock_proof):
        """Upload / hash-only contracts stay backward-compatible (blank body)."""
        mock_pgp.verify_signature.return_value = True
        from parahub.endpoints.contracts import create_contract, ContractCreateRequest
        data = ContractCreateRequest(
            partner_id=self.bob.id, title='Upload contract',
            file_sha256=FAKE_SHA256, signature=FAKE_SIGNATURE,
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = create_contract(request, data)
        self.assertEqual(response.document_text, '')

    def test_rental_completion_keeps_item_active(self, _mock_proof):
        """kind=RENTAL: the asset returns to availability (only SALE deactivates)."""
        from django.utils import timezone
        item = _create_item(self.alice, title='Sur-Ron')
        contract = _create_contract(self.alice, self.bob, status=Contract.Status.SIGNED,
                                    partner_signature=FAKE_SIGNATURE, kind=Contract.Kind.RENTAL)
        contract.items.set([item])
        contract.creator_completed_at = timezone.now()
        contract.save()

        from parahub.endpoints.contracts import complete_contract, ContractCompleteRequest
        data = ContractCompleteRequest()
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        response = complete_contract(request, contract.id, data)

        self.assertEqual(response.status, 'COMPLETED')
        item.refresh_from_db()
        self.assertTrue(item.is_active)

    @patch('parahub.endpoints.contracts.pgp_crypto')
    def test_booking_link_rejects_non_party(self, mock_pgp, _mock_proof):
        """A non-party to the booking cannot link it — and no orphan contract is left."""
        mock_pgp.verify_signature.return_value = True
        _item, booking = self._make_booking(self.alice, self.bob)
        charlie_account = _create_account(self.instance, 'charlie')
        charlie = _create_profile(charlie_account, self.instance, local_name='charlie',
                                  pgp_public_key=FAKE_PGP_KEY)
        before = Contract.objects.count()

        from parahub.endpoints.contracts import create_contract, ContractCreateRequest
        data = ContractCreateRequest(
            partner_id=self.alice.id, title='Sneaky', file_sha256=FAKE_SHA256,
            signature=FAKE_SIGNATURE, kind='RENTAL', booking_id=booking.id,
        )
        request = _make_auth_request(self.factory, charlie_account, charlie, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_contract(request, data)
        self.assertEqual(ctx.exception.status_code, 403)
        # Booking is validated BEFORE the contract is created → nothing orphaned.
        self.assertEqual(Contract.objects.count(), before)


# ===========================================================================
# DB-backed tests: Contract Git Mirror (v1.5 — private per-contract proof repo)
# ===========================================================================

@patch('audit_log.signals._create_pending_proof', return_value=None)
class ContractGitMirrorTest(TestCase):
    """Private per-contract DB → git mirror.

    Invariants:
    - sync() writes a proof bundle: body, canonical.json (== signed bytes),
      meta.json (structured front-matter), and detached signatures.
    - canonical.json mirrors get_canonical_text() exactly (court-verifiable offline).
    - Edits create new commits (redline history); unchanged rows commit nothing.
    - Legacy hash-only/upload contracts (no body) still mirror meta + canonical + sig.
    - The drain command mirrors every changed contract from the watermark.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='contract-mirror-test-'))
        # Isolate the git root AND the cache: the drain watermark lives in the
        # default cache (real Redis on the server), so without a local cache the
        # test would advance the production mirror watermark.
        self._ov = override_settings(
            CONTRACTS_GIT_ROOT=self.tmp,
            CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
        )
        self._ov.enable()
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance, pgp_public_key=FAKE_PGP_KEY)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, local_name='bob', pgp_public_key=FAKE_PGP_KEY)

    def tearDown(self):
        self._ov.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _repo_dir(self, contract):
        return self.tmp / contract.id

    def test_sync_writes_proof_bundle(self, _mp):
        c = _create_contract(self.alice, self.bob, title='Aluguer — Sur-Ron',
                             document_text='<h3>Termos</h3>', kind=Contract.Kind.RENTAL)
        from contracts.contract_git_mirror import ContractGitMirror
        commit = ContractGitMirror().sync(c)
        self.assertIsNotNone(commit)
        d = self._repo_dir(c)
        self.assertTrue((d / 'contract.html').exists())
        self.assertTrue((d / 'canonical.json').exists())
        self.assertTrue((d / 'meta.json').exists())
        self.assertTrue((d / 'signatures' / 'creator.asc').exists())
        self.assertEqual((d / 'contract.html').read_text(), '<h3>Termos</h3>')
        # canonical.json is byte-identical to the signed bytes
        self.assertEqual((d / 'canonical.json').read_text().strip(), c.get_canonical_text())
        meta = json.loads((d / 'meta.json').read_text())
        self.assertEqual(meta['id'], c.id)
        self.assertEqual(meta['kind'], 'RENTAL')
        self.assertEqual(meta['file_sha256'], c.file_sha256)
        self.assertTrue(meta['has_body'])

    def test_sync_idempotent(self, _mp):
        c = _create_contract(self.alice, self.bob, document_text='<p>x</p>')
        from contracts.contract_git_mirror import ContractGitMirror
        m = ContractGitMirror()
        self.assertIsNotNone(m.sync(c))
        self.assertIsNone(m.sync(c))  # nothing changed → no second commit

    def test_edit_creates_new_commit(self, _mp):
        import git
        c = _create_contract(self.alice, self.bob, document_text='<p>v1</p>')
        from contracts.contract_git_mirror import ContractGitMirror
        m = ContractGitMirror()
        m.sync(c)
        c.document_text = '<p>v2</p>'
        c.save()
        self.assertIsNotNone(m.sync(c))
        repo = git.Repo(self._repo_dir(c))
        # init + v1 + v2
        self.assertEqual(len(list(repo.iter_commits())), 3)
        self.assertEqual((self._repo_dir(c) / 'contract.html').read_text(), '<p>v2</p>')

    def test_signed_writes_partner_signature(self, _mp):
        c = _create_contract(self.alice, self.bob, status=Contract.Status.SIGNED,
                             partner_signature=FAKE_SIGNATURE, document_text='<p>x</p>')
        from contracts.contract_git_mirror import ContractGitMirror
        ContractGitMirror().sync(c)
        self.assertTrue((self._repo_dir(c) / 'signatures' / 'partner.asc').exists())

    def test_legacy_contract_no_body_file(self, _mp):
        c = _create_contract(self.alice, self.bob)  # no document_text
        from contracts.contract_git_mirror import ContractGitMirror
        ContractGitMirror().sync(c)
        d = self._repo_dir(c)
        self.assertFalse((d / 'contract.html').exists())
        self.assertFalse((d / 'contract.md').exists())
        self.assertTrue((d / 'meta.json').exists())
        self.assertTrue((d / 'canonical.json').exists())
        self.assertTrue((d / 'signatures' / 'creator.asc').exists())
        self.assertFalse(json.loads((d / 'meta.json').read_text())['has_body'])

    def test_drain_command_mirrors_all(self, _mp):
        from django.core.cache import cache
        from django.core.management import call_command
        cache.delete('contracts:mirror:last_sync_ts')
        c1 = _create_contract(self.alice, self.bob, title='C1', document_text='<p>1</p>')
        c2 = _create_contract(self.alice, self.bob, title='C2')
        call_command('contract_mirror_drain')
        self.assertTrue((self._repo_dir(c1) / 'meta.json').exists())
        self.assertTrue((self._repo_dir(c2) / 'meta.json').exists())
