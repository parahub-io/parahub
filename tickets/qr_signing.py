"""
Self-verifiable QR payloads for offline ticket validation.

QR string: `PHT1.<base64url(payload)>.<base64url(signature)>`
Payload — compact JSON the scanner can show and verify without network:
ticket id, qr_token, type id/name, validity window, concession category.

Signing key: Ed25519 derived deterministically from SECRET_KEY via
HKDF-SHA256 — no key storage or rotation machinery. Rotating SECRET_KEY
invalidates previously issued QR payloads for OFFLINE verification only;
online validation (by qr_token) is unaffected. Offline verdicts are
advisory — the server state machine applies the truth at sync time.
"""
import base64
import json
from functools import lru_cache

from django.conf import settings
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization

QR_PREFIX = 'PHT1'
_HKDF_INFO = b'parahub-tickets-qr-ed25519-v1'


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


@lru_cache(maxsize=1)
def _private_key() -> Ed25519PrivateKey:
    seed = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO,
    ).derive(settings.SECRET_KEY.encode())
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_key_b64() -> str:
    """Raw 32-byte Ed25519 public key, base64url — served to scanners."""
    raw = _private_key().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b64url(raw)


def build_qr_payload(ticket) -> str:
    """Signed QR string for an active/validated ticket."""
    tt = ticket.ticket_type
    payload = {
        'v': 1,
        'tid': ticket.id,
        'qr': ticket.qr_token,
        'ty': tt.id,
        'nm': tt.name,
        'vm': tt.validity_minutes,
        'cc': tt.concession_category or None,
    }
    raw = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode()
    sig = _private_key().sign(raw)
    return f"{QR_PREFIX}.{_b64url(raw)}.{_b64url(sig)}"
