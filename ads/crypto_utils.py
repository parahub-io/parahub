"""
Cryptographic utilities for ads app
Encrypts sensitive wallet credentials before storage
"""

from cryptography.fernet import Fernet
from django.conf import settings
import base64
import hashlib

import logging

logger = logging.getLogger(__name__)


def get_encryption_key() -> bytes:
    """
    Get or generate encryption key for wallet credentials.
    Uses Django SECRET_KEY as base for key derivation.

    Returns:
        32-byte Fernet key
    """
    # Derive consistent key from Django SECRET_KEY
    key_material = settings.SECRET_KEY.encode('utf-8')
    derived_key = hashlib.sha256(key_material).digest()
    return base64.urlsafe_b64encode(derived_key)


def encrypt_wallet_config(config: dict) -> dict:
    """
    Encrypt sensitive fields in wallet configuration.

    Args:
        config: Wallet config dict with provider-specific credentials

    Returns:
        Config dict with encrypted sensitive fields

    Sensitive fields encrypted:
    - invoice_key (LNbits)
    - access_token (Alby)
    - macaroon, cert (LND - future)
    """
    if not config:
        return {}

    encrypted_config = config.copy()
    fernet = Fernet(get_encryption_key())

    # Encrypt sensitive fields based on provider
    if config.get('provider') == 'lnbits':
        if 'invoice_key' in config:
            encrypted = fernet.encrypt(config['invoice_key'].encode('utf-8'))
            encrypted_config['invoice_key'] = encrypted.decode('utf-8')
        if 'admin_key' in config:
            encrypted = fernet.encrypt(config['admin_key'].encode('utf-8'))
            encrypted_config['admin_key'] = encrypted.decode('utf-8')

    elif config.get('provider') == 'alby':
        if 'access_token' in config:
            encrypted = fernet.encrypt(config['access_token'].encode('utf-8'))
            encrypted_config['access_token'] = encrypted.decode('utf-8')

    elif config.get('provider') == 'lnd':
        # Future: Encrypt macaroon and cert
        if 'macaroon' in config:
            encrypted = fernet.encrypt(config['macaroon'].encode('utf-8'))
            encrypted_config['macaroon'] = encrypted.decode('utf-8')

    logger.info(f"Encrypted wallet config for provider: {config.get('provider')}")
    return encrypted_config


def decrypt_wallet_config(encrypted_config: dict) -> dict:
    """
    Decrypt sensitive fields in wallet configuration.

    Args:
        encrypted_config: Config with encrypted fields

    Returns:
        Config dict with decrypted sensitive fields

    Raises:
        Exception: If decryption fails (invalid key or corrupted data)
    """
    if not encrypted_config:
        return {}

    decrypted_config = encrypted_config.copy()
    fernet = Fernet(get_encryption_key())

    try:
        # Decrypt based on provider
        if encrypted_config.get('provider') == 'lnbits':
            if 'invoice_key' in encrypted_config:
                decrypted = fernet.decrypt(encrypted_config['invoice_key'].encode('utf-8'))
                decrypted_config['invoice_key'] = decrypted.decode('utf-8')
            if 'admin_key' in encrypted_config:
                decrypted = fernet.decrypt(encrypted_config['admin_key'].encode('utf-8'))
                decrypted_config['admin_key'] = decrypted.decode('utf-8')

        elif encrypted_config.get('provider') == 'alby':
            if 'access_token' in encrypted_config:
                decrypted = fernet.decrypt(encrypted_config['access_token'].encode('utf-8'))
                decrypted_config['access_token'] = decrypted.decode('utf-8')

        elif encrypted_config.get('provider') == 'lnd':
            if 'macaroon' in encrypted_config:
                decrypted = fernet.decrypt(encrypted_config['macaroon'].encode('utf-8'))
                decrypted_config['macaroon'] = decrypted.decode('utf-8')

        return decrypted_config

    except Exception as e:
        logger.error(f"Failed to decrypt wallet config: {e}")
        raise Exception("Failed to decrypt wallet configuration")
