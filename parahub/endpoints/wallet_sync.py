"""Cross-device wallet-context sync — an opaque encrypted blob per account.

Tip batches and payment annotations are client-side by design (the server is
never told who paid whom). This endpoint stores ONE ciphertext per account so a
user who opted in can carry that context between their own devices. The blob is
AES-256-GCM encrypted in the browser with a key derived from the wallet seed;
the server can neither read nor validate its contents and treats it as an
opaque string. Row existence is the account-level "sync enabled" flag: PUT
enables (upserts), DELETE disables (removes the ciphertext entirely).
"""
import logging

from ninja import Router
from ninja.errors import HttpError
from pydantic import BaseModel

from parahub.auth import GlobalAuth
from parahub.ratelimit import ratelimit, user_or_ip
from finance.models import WalletSyncBlob

logger = logging.getLogger(__name__)

wallet_sync_router = Router()

# Generous for its content (batches + annotations are a few KB of JSON), tight
# enough that the endpoint is useless as free blob storage.
MAX_CIPHERTEXT_CHARS = 256 * 1024


class WalletSyncPutRequest(BaseModel):
    ciphertext: str


class WalletSyncOut(BaseModel):
    enabled: bool
    ciphertext: str | None = None
    updated_at: str | None = None


def _serialize(blob: WalletSyncBlob | None) -> dict:
    if blob is None:
        return {'enabled': False, 'ciphertext': None, 'updated_at': None}
    return {
        'enabled': True,
        'ciphertext': blob.ciphertext,
        'updated_at': blob.updated_at.isoformat() if blob.updated_at else None,
    }


@wallet_sync_router.get("/", auth=GlobalAuth(), response=WalletSyncOut)
@ratelimit(group='wallet_sync:get', key=user_or_ip, rate='120/m')
def get_wallet_sync(request):
    """Sync state for the caller's account: enabled flag + current ciphertext."""
    blob = WalletSyncBlob.objects.filter(account=request.auth).first()
    return _serialize(blob)


@wallet_sync_router.put("/", auth=GlobalAuth(), response={200: WalletSyncOut, 400: dict})
@ratelimit(group='wallet_sync:put', key=user_or_ip, rate='60/m', method='PUT')
def put_wallet_sync(request, data: WalletSyncPutRequest):
    """Store the ciphertext, enabling sync if it wasn't. Last write wins."""
    if not data.ciphertext:
        raise HttpError(400, "Ciphertext must not be empty")
    if len(data.ciphertext) > MAX_CIPHERTEXT_CHARS:
        raise HttpError(400, "Ciphertext too large")
    blob, _ = WalletSyncBlob.objects.update_or_create(
        account=request.auth, defaults={'ciphertext': data.ciphertext},
    )
    return _serialize(blob)


@wallet_sync_router.delete("/", auth=GlobalAuth(), response=WalletSyncOut)
@ratelimit(group='wallet_sync:delete', key=user_or_ip, rate='30/m', method='DELETE')
def delete_wallet_sync(request):
    """Disable sync and delete the stored ciphertext."""
    WalletSyncBlob.objects.filter(account=request.auth).delete()
    return _serialize(None)
