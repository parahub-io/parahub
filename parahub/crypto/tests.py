"""
Tests for cryptographic operations: PGP signing, contract hashes, vote audit Merkle chain,
wallet encryption.

These test invariants that must never break — auth, permissions, crypto, financial operations.
"""

import gnupg
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import SimpleTestCase

from parahub.crypto.pgp import (
    PGPCrypto,
    PGPVerificationError,
    verify_profile_signature,
)


# ---------------------------------------------------------------------------
# Helper: generate a test PGP keypair (GPG >= 2.1 compatible)
# ---------------------------------------------------------------------------
def _cleanup_gpg_home(home):
    """Kill gpg-agent for this home dir, then remove the directory.

    Without this, gpg-agent daemons linger and keep systemd scopes alive,
    preventing yellowgate-*.scope from being re-created on next agent run.
    """
    try:
        subprocess.run(
            ['gpgconf', '--homedir', home, '--kill', 'gpg-agent'],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass
    shutil.rmtree(home, ignore_errors=True)


def _make_test_gpg():
    """Create a temporary GPG instance configured for headless use."""
    home = tempfile.mkdtemp(prefix='parahub_test_gpg_')
    gpg = gnupg.GPG(gnupghome=home)
    with open(os.path.join(home, 'gpg.conf'), 'w') as f:
        f.write('pinentry-mode loopback\n')
    with open(os.path.join(home, 'gpg-agent.conf'), 'w') as f:
        f.write('allow-loopback-pinentry\n')
    return gpg, home


def generate_test_keypair():
    """Generate RSA-2048 test keypair with passphrase (GPG >= 2.1 safe)."""
    gpg, home = _make_test_gpg()
    passphrase = 'testpass'
    inp = gpg.gen_key_input(
        name_real='Test User',
        name_email='test@example.com',
        key_type='RSA',
        key_length=2048,
        passphrase=passphrase,
    )
    key = gpg.gen_key(inp)
    if not key:
        _cleanup_gpg_home(home)
        raise RuntimeError('GPG key generation failed')
    pub = gpg.export_keys(str(key))
    priv = gpg.export_keys(str(key), secret=True, passphrase=passphrase)
    return gpg, home, str(key), pub, priv, passphrase


def sign_message(gpg, keyid, passphrase, message):
    """Create a detached armored signature."""
    sig = gpg.sign(message, keyid=keyid, passphrase=passphrase, detach=True)
    if not sig:
        raise RuntimeError(f'GPG signing failed: {sig.status}')
    return str(sig)


# ============================================================================
# 1. PGP Core Operations
# ============================================================================

class PGPKeyLoadingTest(SimpleTestCase):
    """Test PGP public key import and fingerprint extraction."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gpg, cls.gpg_home, cls.keyid, cls.pub, cls.priv, cls.passphrase = generate_test_keypair()

    @classmethod
    def tearDownClass(cls):
        _cleanup_gpg_home(cls.gpg_home)
        super().tearDownClass()

    def test_load_valid_public_key(self):
        crypto = PGPCrypto()
        fingerprint = crypto.load_public_key(self.pub)
        self.assertEqual(len(fingerprint), 40)
        self.assertTrue(fingerprint.isalnum())

    def test_load_invalid_key_raises(self):
        crypto = PGPCrypto()
        with self.assertRaises(PGPVerificationError):
            crypto.load_public_key('NOT A PGP KEY')

    def test_extract_fingerprint(self):
        crypto = PGPCrypto()
        fp = crypto.extract_fingerprint(self.pub)
        self.assertEqual(len(fp), 40)
        self.assertEqual(fp, fp.upper())

    def test_extract_fingerprint_invalid_key(self):
        crypto = PGPCrypto()
        with self.assertRaises(PGPVerificationError):
            crypto.extract_fingerprint('garbage data')


class PGPSignatureVerificationTest(SimpleTestCase):
    """Test PGP detached signature verification end-to-end."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gpg, cls.gpg_home, cls.keyid, cls.pub, cls.priv, cls.passphrase = generate_test_keypair()

    @classmethod
    def tearDownClass(cls):
        _cleanup_gpg_home(cls.gpg_home)
        super().tearDownClass()

    def test_valid_signature_verifies(self):
        message = 'hello world'
        sig = sign_message(self.gpg, self.keyid, self.passphrase, message)

        crypto = PGPCrypto()
        result = crypto.verify_signature(message, sig, self.pub)
        self.assertTrue(result)

    def test_tampered_message_fails(self):
        message = 'hello world'
        sig = sign_message(self.gpg, self.keyid, self.passphrase, message)

        crypto = PGPCrypto()
        result = crypto.verify_signature('TAMPERED', sig, self.pub)
        self.assertFalse(result)

    def test_wrong_key_fails(self):
        message = 'hello world'
        sig = sign_message(self.gpg, self.keyid, self.passphrase, message)

        gpg2, home2, _, pub2, _, _ = generate_test_keypair()
        try:
            crypto = PGPCrypto()
            result = crypto.verify_signature(message, sig, pub2)
            self.assertFalse(result)
        finally:
            _cleanup_gpg_home(home2)

    def test_invalid_signature_format(self):
        crypto = PGPCrypto()
        result = crypto.verify_signature('msg', 'not-a-sig', self.pub)
        self.assertFalse(result)

    def test_canonical_json_signature(self):
        """Verify signature over canonical JSON (sort_keys, compact separators)."""
        payload = {'z_key': 'last', 'a_key': 'first', 'number': 42}
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        self.assertEqual(canonical, '{"a_key":"first","number":42,"z_key":"last"}')

        sig = sign_message(self.gpg, self.keyid, self.passphrase, canonical)
        crypto = PGPCrypto()
        self.assertTrue(crypto.verify_signature(canonical, sig, self.pub))

        # Non-canonical version must fail
        non_canonical = json.dumps(payload)
        self.assertFalse(crypto.verify_signature(non_canonical, sig, self.pub))


class PGPTimestampValidationTest(SimpleTestCase):
    """Test timestamp freshness checks in PGPCrypto."""

    def test_fresh_timestamp_valid(self):
        crypto = PGPCrypto()
        now = datetime.now(timezone.utc).isoformat()
        self.assertTrue(crypto._validate_timestamp(now))

    def test_old_timestamp_invalid(self):
        crypto = PGPCrypto()
        old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        self.assertFalse(crypto._validate_timestamp(old))

    def test_future_timestamp_within_drift(self):
        crypto = PGPCrypto()
        future = (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat()
        self.assertTrue(crypto._validate_timestamp(future))

    def test_far_future_timestamp_invalid(self):
        crypto = PGPCrypto()
        far = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        self.assertFalse(crypto._validate_timestamp(far))

    def test_garbage_timestamp_invalid(self):
        crypto = PGPCrypto()
        self.assertFalse(crypto._validate_timestamp('not-a-timestamp'))

    def test_z_suffix_accepted(self):
        crypto = PGPCrypto()
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.assertTrue(crypto._validate_timestamp(now))


class PGPCanonicalMessageTest(SimpleTestCase):
    """Test canonical message creation for request signing."""

    def test_deterministic_output(self):
        crypto = PGPCrypto()
        data = {'b': 2, 'a': 1}
        nonce = 'nonce123'
        ts = '2026-01-01T00:00:00Z'

        msg1 = crypto._create_canonical_message(data, nonce, ts)
        msg2 = crypto._create_canonical_message(data, nonce, ts)
        self.assertEqual(msg1, msg2)

    def test_sorted_keys(self):
        crypto = PGPCrypto()
        data = {'z': 1, 'a': 2}
        msg = crypto._create_canonical_message(data, 'n', 't')
        parsed = json.loads(msg)
        keys = list(parsed.keys())
        self.assertEqual(keys, sorted(keys))

    def test_compact_separators(self):
        crypto = PGPCrypto()
        msg = crypto._create_canonical_message({'k': 'v'}, 'n', 't')
        self.assertNotIn(': ', msg)
        self.assertNotIn(', ', msg)


class PGPNonceValidationTest(SimpleTestCase):
    """Test nonce validation (format checks). Uses mock cache to avoid Redis dependency."""

    def test_short_nonce_rejected(self):
        crypto = PGPCrypto()
        ts = datetime.now(timezone.utc).isoformat()
        self.assertFalse(crypto._validate_nonce('short', ts))

    def test_empty_nonce_rejected(self):
        crypto = PGPCrypto()
        self.assertFalse(crypto._validate_nonce('', 'ts'))

    @patch('django.core.cache.cache')
    def test_valid_nonce_accepted(self, mock_cache):
        mock_cache.get.return_value = None  # nonce not yet used
        crypto = PGPCrypto()
        nonce = 'a' * 32
        ts = datetime.now(timezone.utc).isoformat()
        self.assertTrue(crypto._validate_nonce(nonce, ts))

    @patch('django.core.cache.cache')
    def test_replay_detected(self, mock_cache):
        mock_cache.get.return_value = {'timestamp': 'x', 'created_at': 'y'}  # nonce exists
        crypto = PGPCrypto()
        nonce = 'b' * 32
        ts = datetime.now(timezone.utc).isoformat()
        self.assertFalse(crypto._validate_nonce(nonce, ts))


# ============================================================================
# 2. verify_profile_signature() — "mandatory if capable"
# ============================================================================

class VerifyProfileSignatureTest(SimpleTestCase):
    """Test the reusable verify_profile_signature() helper."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gpg, cls.gpg_home, cls.keyid, cls.pub, cls.priv, cls.passphrase = generate_test_keypair()

    @classmethod
    def tearDownClass(cls):
        _cleanup_gpg_home(cls.gpg_home)
        super().tearDownClass()

    def _make_profile(self, has_key=True):
        profile = MagicMock()
        profile.pgp_public_key = self.pub if has_key else ''
        return profile

    def test_no_key_skips_silently(self):
        """Profile without PGP key — skip verification (backward compat)."""
        profile = self._make_profile(has_key=False)
        verify_profile_signature(profile, {'a': 1}, '', '')

    def test_key_present_but_empty_sig_raises(self):
        """Profile has key but signature is empty — must reject."""
        from ninja.errors import HttpError
        profile = self._make_profile(has_key=True)
        with self.assertRaises(HttpError) as ctx:
            verify_profile_signature(profile, {'a': 1}, '', '')
        self.assertIn('Signature required', str(ctx.exception))

    def test_valid_signature_passes(self):
        """Profile has key, valid signature — should pass."""
        profile = self._make_profile(has_key=True)
        payload = {'option_id': 'OPT1', 'poll_id': 'POLL1', 'timestamp': '2026-01-01T00:00:00Z'}
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        sig = sign_message(self.gpg, self.keyid, self.passphrase, canonical)

        ts = datetime.now(timezone.utc).isoformat()
        verify_profile_signature(profile, payload, sig, ts)

    def test_tampered_payload_rejected(self):
        """Signature doesn't match changed payload — must reject."""
        from ninja.errors import HttpError
        profile = self._make_profile(has_key=True)

        original = {'option_id': 'OPT1', 'poll_id': 'POLL1'}
        canonical = json.dumps(original, sort_keys=True, separators=(',', ':'))
        sig = sign_message(self.gpg, self.keyid, self.passphrase, canonical)

        tampered = {'option_id': 'OPT2', 'poll_id': 'POLL1'}
        ts = datetime.now(timezone.utc).isoformat()
        with self.assertRaises(HttpError):
            verify_profile_signature(profile, tampered, sig, ts)

    def test_expired_timestamp_rejected(self):
        """Signed timestamp older than 5 minutes — must reject."""
        from ninja.errors import HttpError
        profile = self._make_profile(has_key=True)
        payload = {'a': 1}
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        sig = sign_message(self.gpg, self.keyid, self.passphrase, canonical)

        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        with self.assertRaises(HttpError) as ctx:
            verify_profile_signature(profile, payload, sig, old_ts)
        self.assertIn('expired', str(ctx.exception))


# ============================================================================
# 3. Contract Canonical Hashes
# ============================================================================

class ContractCanonicalHashTest(SimpleTestCase):
    """Test contract canonical JSON generation and SHA256 hash format."""

    def test_canonical_json_sorted_keys(self):
        data = {
            'title': 'TestContract',
            'creator_id': '01AAAA',
            'partner_id': '01BBBB',
            'file_sha256': 'a' * 64,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        parsed = json.loads(canonical)
        self.assertEqual(list(parsed.keys()), sorted(parsed.keys()))
        # Compact separators: no space after : or ,
        self.assertNotIn(': ', canonical)
        self.assertNotIn(', ', canonical)

    def test_canonical_with_arbiter(self):
        """Arbiter included — must be in sorted position (first alphabetically)."""
        data = {
            'title': 'F1',
            'creator_id': '01CCC',
            'partner_id': '01DDD',
            'file_sha256': 'b' * 64,
            'arbiter_id': '01EEE',
        }
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        self.assertTrue(canonical.startswith('{"arbiter_id":'))

    def test_canonical_without_arbiter(self):
        data = {
            'title': 'F1',
            'creator_id': '01CCC',
            'partner_id': '01DDD',
            'file_sha256': 'b' * 64,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        self.assertNotIn('arbiter_id', canonical)

    def test_sha256_format_validation(self):
        """file_sha256 must be exactly 64 hex characters."""
        valid = 'a' * 64
        self.assertEqual(len(valid), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in valid))

        h = hashlib.sha256(b'test file content').hexdigest()
        self.assertEqual(len(h), 64)

    def test_no_created_at_in_canonical(self):
        """CRITICAL: created_at must NOT be in canonical JSON (causes sync issues)."""
        data = {
            'title': 'F1',
            'creator_id': '01CCC',
            'partner_id': '01DDD',
            'file_sha256': 'c' * 64,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        self.assertNotIn('created_at', canonical)

    def test_contract_signature_roundtrip(self):
        """Sign canonical contract JSON and verify — simulates full contract signing flow."""
        gpg, home, keyid, pub, _, passphrase = generate_test_keypair()
        try:
            data = {
                'title': 'Service Agreement',
                'creator_id': '01AAAAAAAAAAAAAAAAAAAAAAAA',
                'partner_id': '01BBBBBBBBBBBBBBBBBBBBBBBB',
                'file_sha256': hashlib.sha256(b'contract.pdf content').hexdigest(),
            }
            canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
            sig = sign_message(gpg, keyid, passphrase, canonical)

            crypto = PGPCrypto()
            self.assertTrue(crypto.verify_signature(canonical, sig, pub))
        finally:
            _cleanup_gpg_home(home)

    def test_dual_signature_verification(self):
        """Both creator and partner sign same canonical text — both must verify."""
        gpg1, home1, key1, pub1, _, pass1 = generate_test_keypair()
        gpg2, home2, key2, pub2, _, pass2 = generate_test_keypair()
        try:
            data = {
                'title': 'Dual Sig Contract',
                'creator_id': '01CREATOR',
                'partner_id': '01PARTNER',
                'file_sha256': 'd' * 64,
            }
            canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))

            sig1 = sign_message(gpg1, key1, pass1, canonical)
            sig2 = sign_message(gpg2, key2, pass2, canonical)

            crypto = PGPCrypto()
            self.assertTrue(crypto.verify_signature(canonical, sig1, pub1))
            self.assertTrue(crypto.verify_signature(canonical, sig2, pub2))

            # Cross-verification must fail
            self.assertFalse(crypto.verify_signature(canonical, sig1, pub2))
            self.assertFalse(crypto.verify_signature(canonical, sig2, pub1))
        finally:
            _cleanup_gpg_home(home1)
            _cleanup_gpg_home(home2)


# ============================================================================
# 4. Vote Audit Merkle Chain
# ============================================================================

class MerkleChainTest(SimpleTestCase):
    """Test SHA256 Merkle chain used in governance audit logs."""

    @staticmethod
    def _compute_hash(previous_hash, action, actor_id, payload, timestamp_iso):
        """Replicate AuditService hash computation."""
        hash_data = {
            'previous_hash': previous_hash,
            'action': action,
            'actor_id': actor_id,
            'payload': payload,
            'timestamp': timestamp_iso,
        }
        return hashlib.sha256(
            json.dumps(hash_data, sort_keys=True).encode('utf-8')
        ).hexdigest()

    def test_genesis_entry_has_no_previous(self):
        h = self._compute_hash(None, 'poll_created', 'ACTOR1', {}, '2026-01-01T00:00:00+00:00')
        self.assertEqual(len(h), 64)

    def test_chain_links_correctly(self):
        h1 = self._compute_hash(None, 'poll_created', 'A', {'title': 'Test'}, '2026-01-01T00:00:00+00:00')
        h2 = self._compute_hash(h1, 'vote_cast', 'B', {'option_id': 'O1'}, '2026-01-01T00:01:00+00:00')
        h3 = self._compute_hash(h2, 'vote_cast', 'C', {'option_id': 'O2'}, '2026-01-01T00:02:00+00:00')

        self.assertNotEqual(h1, h2)
        self.assertNotEqual(h2, h3)
        self.assertNotEqual(h1, h3)

        for h in (h1, h2, h3):
            self.assertEqual(len(h), 64)
            self.assertTrue(all(c in '0123456789abcdef' for c in h))

    def test_chain_verification(self):
        """Simulate verify_merkle_chain — recompute and compare."""
        entries = []
        prev = None
        for i, (action, actor) in enumerate([
            ('poll_created', 'CREATOR'),
            ('vote_cast', 'VOTER1'),
            ('vote_cast', 'VOTER2'),
            ('delegation_created', 'DEL1'),
            ('poll_ended', 'SYSTEM'),
        ]):
            ts = f'2026-01-01T00:{i:02d}:00+00:00'
            payload = {'step': i}
            h = self._compute_hash(prev, action, actor, payload, ts)
            entries.append({
                'previous_log_hash': prev,
                'current_log_hash': h,
                'action': action,
                'actor_id': actor,
                'payload': payload,
                'timestamp': ts,
            })
            prev = h

        check_prev = None
        for entry in entries:
            self.assertEqual(entry['previous_log_hash'], check_prev)
            recalc = self._compute_hash(
                check_prev, entry['action'], entry['actor_id'],
                entry['payload'], entry['timestamp']
            )
            self.assertEqual(recalc, entry['current_log_hash'])
            check_prev = entry['current_log_hash']

    def test_tampered_entry_detected(self):
        h1 = self._compute_hash(None, 'poll_created', 'A', {}, '2026-01-01T00:00:00+00:00')
        h2 = self._compute_hash(h1, 'vote_cast', 'B', {'option': 'O1'}, '2026-01-01T00:01:00+00:00')

        h2_tampered = self._compute_hash(h1, 'vote_cast', 'B', {'option': 'O2'}, '2026-01-01T00:01:00+00:00')
        self.assertNotEqual(h2, h2_tampered)

        h2_bad_prev = self._compute_hash('wrong_hash', 'vote_cast', 'B', {'option': 'O1'}, '2026-01-01T00:01:00+00:00')
        self.assertNotEqual(h2, h2_bad_prev)

    def test_hash_determinism(self):
        args = (None, 'vote_cast', 'VOTER', {'opt': 1}, '2026-01-01T12:00:00+00:00')
        h1 = self._compute_hash(*args)
        h2 = self._compute_hash(*args)
        self.assertEqual(h1, h2)

    def test_key_order_irrelevant_in_payload(self):
        """json.dumps(sort_keys=True) means payload key order doesn't matter."""
        h1 = self._compute_hash(None, 'vote_cast', 'A', {'z': 1, 'a': 2}, 'ts')
        h2 = self._compute_hash(None, 'vote_cast', 'A', {'a': 2, 'z': 1}, 'ts')
        self.assertEqual(h1, h2)


# ============================================================================
# 5. Vote Canonical Payloads
# ============================================================================

class VoteCanonicalPayloadTest(SimpleTestCase):
    """Test canonical payload formats for governance votes/delegations."""

    def test_vote_payload_format(self):
        payload = {
            'option_id': '01OPTION',
            'poll_id': '01POLL',
            'timestamp': '2026-01-01T00:00:00Z',
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        self.assertEqual(
            canonical,
            '{"option_id":"01OPTION","poll_id":"01POLL","timestamp":"2026-01-01T00:00:00Z"}'
        )

    def test_delegation_payload_format(self):
        payload = {
            'delegate_id': '01DELEGATE',
            'poll_id': '01POLL',
            'timestamp': '2026-01-01T00:00:00Z',
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        self.assertEqual(
            canonical,
            '{"delegate_id":"01DELEGATE","poll_id":"01POLL","timestamp":"2026-01-01T00:00:00Z"}'
        )

    def test_revoke_payload_format(self):
        payload = {
            'action': 'revoke_delegation',
            'poll_id': '01POLL',
            'timestamp': '2026-01-01T00:00:00Z',
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        self.assertEqual(
            canonical,
            '{"action":"revoke_delegation","poll_id":"01POLL","timestamp":"2026-01-01T00:00:00Z"}'
        )

    def test_debt_create_payload_format(self):
        payload = {
            'action': 'create_debt',
            'amount': '100.00',
            'creditor_id': '01CRED',
            'currency': 'EUR',
            'debtor_id': '01DEBT',
            'timestamp': '2026-01-01T00:00:00Z',
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        parsed = json.loads(canonical)
        self.assertEqual(list(parsed.keys()), sorted(parsed.keys()))

    def test_treasury_allocation_payload_format(self):
        payload = {
            'allocations': {'cat1': 30, 'cat2': 70},
            'establishment_slug': 'test-org',
            'timestamp': '2026-01-01T00:00:00Z',
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        parsed = json.loads(canonical)
        self.assertEqual(list(parsed.keys()), sorted(parsed.keys()))

    def test_sign_and_verify_vote_payload(self):
        """Full round-trip: sign vote payload, verify with PGPCrypto."""
        gpg, home, keyid, pub, _, passphrase = generate_test_keypair()
        try:
            payload = {
                'option_id': '01OPT',
                'poll_id': '01POLL',
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
            sig = sign_message(gpg, keyid, passphrase, canonical)

            crypto = PGPCrypto()
            self.assertTrue(crypto.verify_signature(canonical, sig, pub))
        finally:
            _cleanup_gpg_home(home)


# ============================================================================
# 6. Wallet Encryption (Fernet)
# ============================================================================

class WalletEncryptionTest(SimpleTestCase):
    """Test Fernet-based wallet credential encryption from ads/crypto_utils.py."""

    def test_encryption_key_deterministic(self):
        from ads.crypto_utils import get_encryption_key
        k1 = get_encryption_key()
        k2 = get_encryption_key()
        self.assertEqual(k1, k2)

    def test_encryption_key_is_valid_fernet(self):
        from ads.crypto_utils import get_encryption_key
        from cryptography.fernet import Fernet
        key = get_encryption_key()
        f = Fernet(key)
        ct = f.encrypt(b'test')
        self.assertEqual(f.decrypt(ct), b'test')

    def test_lnbits_roundtrip(self):
        from ads.crypto_utils import encrypt_wallet_config, decrypt_wallet_config
        config = {
            'provider': 'lnbits',
            'invoice_key': 'inv_secret_key_123',
            'admin_key': 'adm_secret_key_456',
            'url': 'https://lnbits.example.com',
        }
        encrypted = encrypt_wallet_config(config)
        self.assertNotEqual(encrypted['invoice_key'], config['invoice_key'])
        self.assertNotEqual(encrypted['admin_key'], config['admin_key'])
        self.assertEqual(encrypted['url'], config['url'])
        self.assertEqual(encrypted['provider'], 'lnbits')

        decrypted = decrypt_wallet_config(encrypted)
        self.assertEqual(decrypted['invoice_key'], config['invoice_key'])
        self.assertEqual(decrypted['admin_key'], config['admin_key'])

    def test_alby_roundtrip(self):
        from ads.crypto_utils import encrypt_wallet_config, decrypt_wallet_config
        config = {
            'provider': 'alby',
            'access_token': 'alby_secret_token_789',
        }
        encrypted = encrypt_wallet_config(config)
        self.assertNotEqual(encrypted['access_token'], config['access_token'])

        decrypted = decrypt_wallet_config(encrypted)
        self.assertEqual(decrypted['access_token'], config['access_token'])

    def test_lnd_roundtrip(self):
        from ads.crypto_utils import encrypt_wallet_config, decrypt_wallet_config
        config = {
            'provider': 'lnd',
            'macaroon': 'hex_macaroon_data_abc',
        }
        encrypted = encrypt_wallet_config(config)
        self.assertNotEqual(encrypted['macaroon'], config['macaroon'])

        decrypted = decrypt_wallet_config(encrypted)
        self.assertEqual(decrypted['macaroon'], config['macaroon'])

    def test_empty_config(self):
        from ads.crypto_utils import encrypt_wallet_config, decrypt_wallet_config
        self.assertEqual(encrypt_wallet_config({}), {})
        self.assertEqual(encrypt_wallet_config(None), {})
        self.assertEqual(decrypt_wallet_config({}), {})
        self.assertEqual(decrypt_wallet_config(None), {})


# ============================================================================
# 7. SHA256 Format Invariants
# ============================================================================

class SHA256FormatTest(SimpleTestCase):
    """Test SHA256 hash format invariants used across the codebase."""

    def test_standard_hex_output(self):
        h = hashlib.sha256(b'test').hexdigest()
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in h))

    def test_consistent_encoding(self):
        """UTF-8 encoding of JSON for hashing must be consistent."""
        data = {'key': 'value', 'number': 42}
        j1 = json.dumps(data, sort_keys=True).encode('utf-8')
        j2 = json.dumps(data, sort_keys=True).encode('utf-8')
        self.assertEqual(hashlib.sha256(j1).hexdigest(), hashlib.sha256(j2).hexdigest())

    def test_different_inputs_different_hashes(self):
        h1 = hashlib.sha256(b'input1').hexdigest()
        h2 = hashlib.sha256(b'input2').hexdigest()
        self.assertNotEqual(h1, h2)

    def test_compact_vs_pretty_json_differ(self):
        """Compact and pretty JSON produce different hashes — canonical form matters."""
        data = {'a': 1, 'b': 2}
        compact = json.dumps(data, sort_keys=True, separators=(',', ':'))
        pretty = json.dumps(data, sort_keys=True, indent=2)
        h_compact = hashlib.sha256(compact.encode()).hexdigest()
        h_pretty = hashlib.sha256(pretty.encode()).hexdigest()
        self.assertNotEqual(h_compact, h_pretty)
