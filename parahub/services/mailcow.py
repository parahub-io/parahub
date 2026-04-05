"""
Mailcow API service for managing user mailboxes.

Creates/deletes @parahub.io mailboxes via Mailcow HTTP API.
"""
import base64
import hashlib
import secrets
import string
import logging

import httpx
from cryptography.fernet import Fernet
from django.conf import settings

# Mailcow uses a self-signed cert on its internal HTTPS port — skip verification for localhost
_HTTPX_KWARGS = {'verify': False}

logger = logging.getLogger('parahub.mailcow')


def _get_fernet() -> Fernet:
    key_material = settings.SECRET_KEY.encode('utf-8')
    derived_key = base64.urlsafe_b64encode(hashlib.sha256(key_material).digest())
    return Fernet(derived_key)


def encrypt_mail_password(password: str) -> str:
    return _get_fernet().encrypt(password.encode()).decode()


def decrypt_mail_password(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


class MailcowService:
    @staticmethod
    def _headers() -> dict:
        return {
            'X-API-Key': settings.MAILCOW_API_KEY,
            'Content-Type': 'application/json',
        }

    @staticmethod
    def _base_url() -> str:
        return settings.MAILCOW_API_URL

    @classmethod
    def create_mailbox(cls, username: str, display_name: str) -> dict:
        """Create mailbox {username}@parahub.io. Returns {'password': ..., 'created': True}."""
        password = cls._generate_password()
        payload = {
            'local_part': username,
            'domain': settings.MAILCOW_DOMAIN,
            'name': display_name,
            'password': password,
            'password2': password,
            'quota': getattr(settings, 'MAILCOW_DEFAULT_QUOTA_MB', 1024),
            'active': '1',
            'force_pw_update': '0',
        }
        resp = httpx.post(
            f"{cls._base_url()}/api/v1/add/mailbox",
            json=payload,
            headers=cls._headers(),
            timeout=10,
            **_HTTPX_KWARGS,
        )
        resp.raise_for_status()
        return {'password': password, 'created': True}

    @classmethod
    def set_mailbox_password(cls, username: str, password: str) -> bool:
        """Update IMAP/SMTP password for an existing mailbox."""
        resp = httpx.post(
            f"{cls._base_url()}/api/v1/edit/mailbox",
            json={'items': [f'{username}@{settings.MAILCOW_DOMAIN}'], 'attr': {'password': password, 'password2': password}},
            headers=cls._headers(),
            timeout=10,
            **_HTTPX_KWARGS,
        )
        return resp.status_code == 200

    @classmethod
    def delete_mailbox(cls, username: str) -> bool:
        resp = httpx.delete(
            f"{cls._base_url()}/api/v1/delete/mailbox",
            json=[f"{username}@{settings.MAILCOW_DOMAIN}"],
            headers=cls._headers(),
            timeout=10,
            **_HTTPX_KWARGS,
        )
        return resp.status_code == 200

    @classmethod
    def mailbox_exists(cls, username: str) -> bool:
        resp = httpx.get(
            f"{cls._base_url()}/api/v1/get/mailbox/{username}@{settings.MAILCOW_DOMAIN}",
            headers=cls._headers(),
            timeout=10,
            **_HTTPX_KWARGS,
        )
        return resp.status_code == 200 and bool(resp.json())

    @staticmethod
    def _generate_password(length: int = 24) -> str:
        chars = string.ascii_letters + string.digits + '!@#$%^&*'
        return ''.join(secrets.choice(chars) for _ in range(length))
