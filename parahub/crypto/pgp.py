"""
PGP Cryptography abstraction layer for Parahub
Provides secure signature verification and key management using python-gnupg library
"""

import gnupg
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
import json
import base64
import logging
import tempfile
import os

logger = logging.getLogger(__name__)


class PGPVerificationError(Exception):
    """Exception raised when PGP verification fails"""
    pass


class NonceError(Exception):
    """Exception raised when nonce validation fails"""
    pass


class TimestampError(Exception):
    """Exception raised when timestamp validation fails"""
    pass


class PGPCrypto:
    """
    PGP cryptography operations for request signing and verification
    Uses python-gnupg (wrapper around GnuPG) for full OpenPGP.js compatibility
    """

    def __init__(self):
        self.max_timestamp_drift = timedelta(minutes=5)  # Allow 5 minutes clock drift
        self.nonce_ttl = timedelta(hours=1)  # Nonce lifetime

        # Initialize GPG with temporary home directory
        # This ensures isolation and no interference with system keyring
        self.gpg_home = tempfile.mkdtemp(prefix='parahub_gpg_')
        self.gpg = gnupg.GPG(gnupghome=self.gpg_home)

        # Configure GPG for headless operation (no pinentry prompts)
        gpg_conf = os.path.join(self.gpg_home, 'gpg.conf')
        gpg_agent_conf = os.path.join(self.gpg_home, 'gpg-agent.conf')

        with open(gpg_conf, 'w') as f:
            f.write('use-agent\n')
            f.write('pinentry-mode loopback\n')

        with open(gpg_agent_conf, 'w') as f:
            f.write('allow-loopback-pinentry\n')

        logger.info(f"Initialized GPG with home directory: {self.gpg_home}")

    def load_public_key(self, public_key_data: str) -> str:
        """
        Load and validate PGP public key from armored text

        Args:
            public_key_data: Armored PGP public key

        Returns:
            Fingerprint of the imported key

        Raises:
            PGPVerificationError: If key is invalid or cannot be loaded
        """
        try:
            # Import key into temporary keyring
            import_result = self.gpg.import_keys(public_key_data)

            if import_result.count == 0:
                raise PGPVerificationError("Failed to import public key")

            # Get fingerprint
            fingerprint = import_result.fingerprints[0]

            # Verify it's a public key (not private)
            keys = self.gpg.list_keys()
            key_info = next((k for k in keys if k['fingerprint'] == fingerprint), None)

            if not key_info:
                raise PGPVerificationError("Key not found after import")

            logger.info(f"Successfully imported PGP key: {fingerprint}")
            return fingerprint

        except PGPVerificationError:
            raise
        except Exception as e:
            logger.error(f"Failed to load public key: {e}")
            raise PGPVerificationError(f"Invalid public key: {e}")

    def extract_fingerprint(self, public_key_data: str) -> str:
        """
        Extract fingerprint from PGP public key without storing it

        Args:
            public_key_data: Armored PGP public key

        Returns:
            Hexadecimal fingerprint string (40 chars, uppercase)
        """
        try:
            # Import temporarily to get fingerprint
            import_result = self.gpg.import_keys(public_key_data)

            if import_result.count == 0 or not import_result.fingerprints:
                raise PGPVerificationError("Failed to extract fingerprint")

            fingerprint = import_result.fingerprints[0].upper()

            # Clean up - delete the key from temporary keyring
            self.gpg.delete_keys(fingerprint)

            return fingerprint

        except Exception as e:
            logger.error(f"Failed to extract fingerprint: {e}")
            raise PGPVerificationError(f"Cannot extract fingerprint: {e}")

    def verify_signature(self, message: str, signature_data: str, public_key_data: str) -> bool:
        """
        Verify PGP detached signature against message and public key

        Args:
            message: The message that was signed
            signature_data: Armored PGP signature (detached, from OpenPGP.js)
            public_key_data: Armored PGP public key

        Returns:
            True if signature is valid, False otherwise

        Raises:
            PGPVerificationError: If verification fails due to invalid data
        """
        import tempfile
        import os

        try:
            # Import public key
            import_result = self.gpg.import_keys(public_key_data)
            if import_result.count == 0:
                raise PGPVerificationError("Failed to import public key for verification")

            fingerprint = import_result.fingerprints[0]

            # For detached signatures, write to temporary files and use verify_file
            # python-gnupg expects file paths as the second argument for detached sigs
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as msg_file:
                msg_file.write(message)
                msg_file_path = msg_file.name

            with tempfile.NamedTemporaryFile(mode='w', suffix='.asc', delete=False) as sig_file:
                sig_file.write(signature_data)
                sig_file_path = sig_file.name

            try:
                # Verify detached signature
                # Open signature file as file object, pass data file as path
                with open(sig_file_path, 'rb') as sig_f:
                    verified = self.gpg.verify_file(sig_f, data_filename=msg_file_path)

                if verified.valid:
                    logger.info(f"Signature verified successfully: {verified.fingerprint}")
                    return True
                else:
                    logger.warning(f"Signature verification failed: {verified.status}")
                    return False
            finally:
                # Clean up temp files
                os.unlink(msg_file_path)
                os.unlink(sig_file_path)
                # Clean up imported key
                self.gpg.delete_keys(fingerprint)

        except PGPVerificationError:
            raise
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    def validate_request_signature(self,
                                 request_data: Dict[str, Any],
                                 signature: str,
                                 public_key_data: str,
                                 nonce: str,
                                 timestamp: str) -> Tuple[bool, str]:
        """
        Validate complete request signature with nonce and timestamp protection

        Args:
            request_data: Dictionary of request data to verify
            signature: Armored PGP signature
            public_key_data: Armored PGP public key
            nonce: Unique request nonce
            timestamp: ISO timestamp of the request

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Step 1: Validate timestamp
            if not self._validate_timestamp(timestamp):
                return False, "Request timestamp is too old or invalid"

            # Step 2: Validate nonce (prevent replay attacks)
            if not self._validate_nonce(nonce, timestamp):
                return False, "Nonce has already been used or is invalid"

            # Step 3: Create canonical message for signing
            canonical_message = self._create_canonical_message(request_data, nonce, timestamp)

            # Step 4: Verify PGP signature
            try:
                is_valid = self.verify_signature(canonical_message, signature, public_key_data)
                if not is_valid:
                    return False, "PGP signature verification failed"
            except PGPVerificationError as e:
                return False, str(e)

            # Step 5: Store nonce to prevent reuse
            self._store_nonce(nonce, timestamp)

            return True, "Signature verified successfully"

        except Exception as e:
            logger.error(f"Request signature validation failed: {e}")
            return False, f"Signature validation error: {e}"

    def _validate_timestamp(self, timestamp_str: str) -> bool:
        """
        Validate request timestamp is within acceptable time window

        Args:
            timestamp_str: ISO timestamp string

        Returns:
            True if timestamp is valid, False otherwise
        """
        try:
            # Parse timestamp
            request_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            current_time = datetime.utcnow().replace(tzinfo=request_time.tzinfo)

            # Check if timestamp is within acceptable drift
            time_diff = abs(current_time - request_time)

            return time_diff <= self.max_timestamp_drift

        except Exception as e:
            logger.warning(f"Invalid timestamp format: {timestamp_str}, error: {e}")
            return False

    def _validate_nonce(self, nonce: str, timestamp: str) -> bool:
        """
        Validate nonce hasn't been used before (replay attack protection)
        Uses Redis cache for distributed nonce storage

        Args:
            nonce: Request nonce
            timestamp: Request timestamp

        Returns:
            True if nonce is valid (unused), False if already used
        """
        try:
            from django.core.cache import cache

            # Basic nonce format validation
            if not nonce or len(nonce) < 16:
                logger.warning(f"Invalid nonce format: {nonce}")
                return False

            # Create cache key for nonce
            cache_key = f"pgp_nonce:{nonce}"

            # Check if nonce already exists in Redis
            if cache.get(cache_key):
                logger.warning(f"Nonce replay detected: {nonce}")
                return False

            return True

        except Exception as e:
            logger.error(f"Nonce validation failed: {e}")
            return False

    def _store_nonce(self, nonce: str, timestamp: str) -> None:
        """
        Store nonce with timestamp to prevent reuse
        Uses Redis cache for distributed storage

        Args:
            nonce: Request nonce
            timestamp: Request timestamp
        """
        try:
            from django.core.cache import cache

            # Create cache key for nonce
            cache_key = f"pgp_nonce:{nonce}"

            # Store nonce data in Redis with TTL
            nonce_data = {
                'timestamp': timestamp,
                'created_at': datetime.utcnow().isoformat()
            }

            # Set with TTL (nonce expires after 1 hour)
            cache.set(cache_key, nonce_data, timeout=int(self.nonce_ttl.total_seconds()))

        except Exception as e:
            logger.error(f"Failed to store nonce: {e}")

    def _create_canonical_message(self, request_data: Dict[str, Any], nonce: str, timestamp: str) -> str:
        """
        Create canonical message for signing

        Args:
            request_data: Request data dictionary
            nonce: Request nonce
            timestamp: Request timestamp

        Returns:
            Canonical message string for signing
        """
        try:
            # Create signing payload
            signing_payload = {
                'nonce': nonce,
                'timestamp': timestamp,
                'data': request_data
            }

            # Convert to deterministic JSON (sorted keys)
            canonical_json = json.dumps(signing_payload, sort_keys=True, separators=(',', ':'))

            return canonical_json

        except Exception as e:
            logger.error(f"Failed to create canonical message: {e}")
            raise PGPVerificationError(f"Cannot create canonical message: {e}")


# Global PGP crypto instance
pgp_crypto = PGPCrypto()


def verify_profile_signature(profile, canonical_payload: dict, signature: str,
                              signed_timestamp: str = '', error_prefix: str = "PGP"):
    """
    Reusable PGP signature verification for any endpoint.

    Strategy: "mandatory if capable"
    - If profile has no pgp_public_key → skip silently (backward compat)
    - If profile has key but signature is empty → HttpError(400)
    - Validates timestamp ±5 min
    - Verifies signature against canonical JSON of payload

    Args:
        profile: Profile model instance (must have .pgp_public_key)
        canonical_payload: dict to be serialized as canonical JSON
        signature: PGP detached signature (armored ASCII)
        signed_timestamp: ISO timestamp string from client
        error_prefix: prefix for error messages (e.g. "Treasury PGP")
    """
    from ninja.errors import HttpError

    # No PGP key → graceful skip
    if not getattr(profile, 'pgp_public_key', None):
        return

    # Has key but no signature → reject
    if not signature or not signature.strip():
        raise HttpError(400, f"{error_prefix}: Signature required (your profile has a PGP key)")

    # Validate timestamp (±5 min)
    if signed_timestamp:
        try:
            from datetime import timezone as tz
            ts_dt = datetime.fromisoformat(signed_timestamp.replace('Z', '+00:00'))
            now = datetime.now(tz.utc)
            age = abs((now - ts_dt).total_seconds())
            if age > 300:
                raise HttpError(400, f"{error_prefix}: Signed timestamp expired (older than 5 minutes)")
        except (ValueError, AttributeError) as e:
            raise HttpError(400, f"{error_prefix}: Invalid timestamp format: {e}")

    # Build canonical message (matches frontend JSON.stringify with sorted keys)
    canonical_message = json.dumps(canonical_payload, sort_keys=True, separators=(',', ':'))

    # Verify
    try:
        is_valid = pgp_crypto.verify_signature(
            message=canonical_message,
            signature_data=signature,
            public_key_data=profile.pgp_public_key
        )
        if not is_valid:
            raise HttpError(400, f"{error_prefix}: Signature verification failed")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"{error_prefix} verification error: {e}", exc_info=True)
        raise HttpError(400, f"{error_prefix}: Signature verification error: {e}")


def generate_test_keypair() -> Tuple[str, str]:
    """
    Generate a test PGP keypair for development and testing.
    Compatible with GPG >= 2.1 (requires passphrase + loopback pinentry).

    Returns:
        Tuple of (private_key_armor, public_key_armor)
    """
    import shutil
    import subprocess

    temp_home = tempfile.mkdtemp(prefix='parahub_test_gpg_')
    try:
        gpg = gnupg.GPG(gnupghome=temp_home)

        # GPG >= 2.1 requires loopback pinentry for headless operation
        with open(os.path.join(temp_home, 'gpg.conf'), 'w') as f:
            f.write('pinentry-mode loopback\n')
        with open(os.path.join(temp_home, 'gpg-agent.conf'), 'w') as f:
            f.write('allow-loopback-pinentry\n')

        passphrase = 'testpass'
        input_data = gpg.gen_key_input(
            name_real='Test User',
            name_email='test@example.com',
            key_type='RSA',
            key_length=2048,
            passphrase=passphrase,
        )
        key = gpg.gen_key(input_data)
        if not key:
            raise PGPVerificationError('GPG key generation failed')

        public_key = gpg.export_keys(str(key))
        private_key = gpg.export_keys(str(key), secret=True, passphrase=passphrase)

        return private_key, public_key

    except PGPVerificationError:
        raise
    except Exception as e:
        logger.error(f"Failed to generate test keypair: {e}")
        raise PGPVerificationError(f"Keypair generation failed: {e}")
    finally:
        # Kill gpg-agent to prevent lingering daemons
        try:
            subprocess.run(
                ['gpgconf', '--homedir', temp_home, '--kill', 'gpg-agent'],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass
        shutil.rmtree(temp_home, ignore_errors=True)
