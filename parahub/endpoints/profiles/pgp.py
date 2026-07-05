"""
PGP key management: upload/remove + key history (own and public).
"""


from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.http import Http404
from typing import List
import logging

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile

from .base import profile_router
from .schemas import PGPKeyHistoryResponse, PGPKeyRequest, PGPKeyResponse

logger = logging.getLogger(__name__)

@profile_router.post("/me/keys/", response={200: PGPKeyResponse, 400: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:upload_pgp_key', key=user_or_ip, rate='10/m', method='POST')
def upload_pgp_key(request, data: PGPKeyRequest):
    """
    Upload/update PGP public key for the authenticated user

    Uses ProfileAuth (JWT only) instead of PGPSignatureAuth to avoid chicken-egg problem:
    - First upload: user has no key on server yet, can't sign
    - Update: user uploads new key (old key becomes invalid)

    Public key upload is not a critical operation (only public data).
    Critical operations (deals, etc.) require PGP signature.

    Creates audit trail in PGPKeyHistory:
    - Marks old key as EXPIRED (if exists)
    - Creates new key record with CREATED action
    """
    try:
        from parahub.crypto.pgp import pgp_crypto
        from identity.models import PGPKeyHistory
        from django.utils import timezone

        profile = request.auth_profile

        # Validate PGP key and extract real fingerprint using python-gnupg
        try:
            # Extract real PGP fingerprint (now works with OpenPGP.js keys!)
            fingerprint = pgp_crypto.extract_fingerprint(data.public_key)
            logger.info(f"Extracted real PGP fingerprint: {fingerprint}")

        except Exception as e:
            logger.warning(f"Invalid PGP key upload attempt: {e}")
            raise HttpError(400, f"Invalid PGP public key: {str(e)}")

        # Get client IP and user agent for audit
        def get_client_ip(request):
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                return x_forwarded_for.split(',')[0].strip()
            return request.META.get('REMOTE_ADDR')

        client_ip = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

        now = timezone.now()

        # If profile already has a key, mark old key as EXPIRED
        if profile.pgp_fingerprint:
            old_key = PGPKeyHistory.objects.filter(
                profile=profile,
                valid_until__isnull=True  # Find active key
            ).first()

            if old_key:
                old_key.valid_until = now
                old_key.action = PGPKeyHistory.Action.EXPIRED
                old_key.save()
                logger.info(f"Marked old PGP key as expired: {old_key.fingerprint}")

        # Create history record for new key
        PGPKeyHistory.objects.create(
            profile=profile,
            fingerprint=fingerprint,
            public_key=data.public_key,
            action=PGPKeyHistory.Action.CREATED,
            valid_from=now,
            valid_until=None,  # Active key
            created_from_ip=client_ip,
            user_agent=user_agent
        )

        # Update profile with new key
        profile.pgp_public_key = data.public_key
        profile.pgp_fingerprint = fingerprint
        profile.save()

        logger.info(f"PGP key updated for profile {profile.id}: {fingerprint}")

        return PGPKeyResponse(
            fingerprint=fingerprint,
            created_at=now.isoformat(),
            is_active=True
        )

    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Error uploading PGP key: {e}")
        raise HttpError(500, "Failed to upload PGP key")

@profile_router.delete("/me/keys/", auth=ProfileAuth())
@ratelimit(group='profiles:remove_pgp_key', key=user_or_ip, rate='10/m', method='DELETE')
def remove_pgp_key(request):
    """
    Remove/revoke current PGP public key

    Uses ProfileAuth (not PGPSignatureAuth) because:
    - User deletes keys from browser localStorage
    - Can't sign with deleted key
    - JWT auth is sufficient for this operation

    Creates audit trail in PGPKeyHistory:
    - Marks current key as REVOKED
    - Clears pgp_public_key and pgp_fingerprint from profile
    """
    try:
        from identity.models import PGPKeyHistory
        from django.utils import timezone

        profile = request.auth_profile

        # Check if profile has a key
        if not profile.pgp_fingerprint:
            raise HttpError(404, "No PGP key found")

        # Mark current key as REVOKED in history
        current_key = PGPKeyHistory.objects.filter(
            profile=profile,
            valid_until__isnull=True  # Active key
        ).first()

        if current_key:
            current_key.valid_until = timezone.now()
            current_key.action = PGPKeyHistory.Action.REVOKED
            current_key.save()
            logger.info(f"Marked PGP key as revoked: {current_key.fingerprint}")

        # Clear key from profile
        old_fingerprint = profile.pgp_fingerprint
        profile.pgp_public_key = ""
        profile.pgp_fingerprint = ""
        profile.save()

        logger.info(f"PGP key removed from profile {profile.id}: {old_fingerprint}")

        return {"message": "PGP key revoked successfully"}

    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Error removing PGP key: {e}")
        raise HttpError(500, "Failed to remove PGP key")

@profile_router.get("/me/keys/history/", response={200: List[PGPKeyHistoryResponse], 500: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:my_key_history', key=user_or_ip, rate='60/m')
def get_my_pgp_key_history(request):
    """
    Get complete PGP key history for authenticated user

    Returns all historical keys with private audit data (IP, user agent).
    Ordered by most recent first.
    """
    try:
        from identity.models import PGPKeyHistory

        profile = request.auth_profile

        keys = PGPKeyHistory.objects.filter(profile=profile).order_by('-action_timestamp')

        result = []
        for key in keys:
            result.append(PGPKeyHistoryResponse(
                id=key.id,
                fingerprint=key.fingerprint,
                public_key=key.public_key,
                action=key.action,
                action_timestamp=key.action_timestamp.isoformat(),
                valid_from=key.valid_from.isoformat(),
                valid_until=key.valid_until.isoformat() if key.valid_until else None,
                is_active=key.is_active,
                validity_days=key.validity_days,
                created_from_ip=key.created_from_ip,
                user_agent=key.user_agent
            ))

        return result

    except Exception as e:
        logger.error(f"Error retrieving PGP key history: {e}")
        raise HttpError(500, "Failed to retrieve key history")

@profile_router.get("/{id}/keys/history/", response={200: List[PGPKeyHistoryResponse], 500: dict}, auth=None)
@ratelimit(group='profiles:public_key_history', key='ip', rate='60/m')
def get_public_pgp_key_history(request, id: str):
    """
    Get public PGP key history for any profile

    Returns historical keys WITHOUT private audit data.
    Useful for verifying old signatures and key rotation transparency.
    """
    try:
        from identity.models import PGPKeyHistory

        if len(id) == 26 and id.isalnum():
            profile = get_object_or_404(Profile, id=id)
        else:
            profile = get_object_or_404(Profile, local_name=id)

        # Check if profile is publicly linked
        if not profile.is_publicly_linked:
            raise Http404("Profile not found")

        keys = PGPKeyHistory.objects.filter(profile=profile).order_by('-action_timestamp')

        result = []
        for key in keys:
            result.append(PGPKeyHistoryResponse(
                id=key.id,
                fingerprint=key.fingerprint,
                public_key=key.public_key,  # Include for export
                action=key.action,
                action_timestamp=key.action_timestamp.isoformat(),
                valid_from=key.valid_from.isoformat(),
                valid_until=key.valid_until.isoformat() if key.valid_until else None,
                is_active=key.is_active,
                validity_days=key.validity_days,
                created_from_ip=None,  # Don't expose private data
                user_agent=None
            ))

        return result

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error retrieving public PGP key history for {id}: {e}")
        raise HttpError(500, "Failed to retrieve key history")
