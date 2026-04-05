"""
Web of Trust API endpoints for frontend integration
Used by /directory page (Web of Trust tab) and user profile verification modal
"""

from ninja import Router
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q, Count
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from decimal import Decimal
import logging

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile, Verification, ProfileVerificationPhoto
from identity.reputation import calculate_reputation

logger = logging.getLogger(__name__)

# Create WoT router
wot_router = Router()

# Pydantic schemas
class ProfileBasicInfo(BaseModel):
    id: str
    hna: Optional[str] = None
    reputation_score: float
    trust_level: str = "NONE"

    model_config = ConfigDict(from_attributes=True)


class VerificationInfo(BaseModel):
    id: str
    verifier_cri: str
    verifier_hna: Optional[str] = None
    verified_user_id: Optional[str] = None
    verified_user_hna: Optional[str] = None
    verification_method: str
    notes: str
    verified_at: datetime
    has_signed: bool = True

    model_config = ConfigDict(from_attributes=True)


class MyWoTStatusResponse(BaseModel):
    reputation_score: float
    trust_level: str
    is_verified: bool
    verification_count: int
    can_verify_others: bool
    received_verifications: List[VerificationInfo]
    given_verifications: List[VerificationInfo]

    model_config = ConfigDict(from_attributes=True)


class UserSearchResult(BaseModel):
    id: str
    hna: Optional[str] = None
    reputation_score: float
    trust_level: str

    model_config = ConfigDict(from_attributes=True)


class CreateVerificationRequest(BaseModel):
    verified_user_id: str = Field(..., description="ULID of user to verify")
    verification_method: str = Field(..., description="Method: IN_PERSON, VIDEO_CALL, DOCUMENTS, VOUCHED")
    timestamp: str = Field(..., description="ISO timestamp when statement was created")
    statement: str = Field(..., description="Machine-readable JSON statement that was signed")
    signature: str = Field(..., description="PGP signature of the statement (armored)")
    notes: Optional[str] = Field("", description="Optional notes about verification (not part of signature)")


@wot_router.get("/my-status/", response=MyWoTStatusResponse, auth=ProfileAuth())
@ratelimit(group='wot:my_status', key=user_or_ip, rate='60/m')
def get_my_wot_status(request):
    """
    Get current user's Web of Trust status
    Includes verification count, received and given verifications
    """
    try:
        profile = request.auth_profile

        # Get verification counts
        received_count = Verification.objects.filter(
            verified_profile=profile,
            is_active=True
        ).count()

        # Determine trust level based on verification count
        if received_count >= 10:
            trust_level = "HIGH"
        elif received_count >= 5:
            trust_level = "MEDIUM"
        elif received_count >= 3:
            trust_level = "BASIC"
        elif received_count >= 1:
            trust_level = "LOW"
        else:
            trust_level = "NONE"

        # Get received verifications
        received_verifications = Verification.objects.filter(
            verified_profile=profile,
            is_active=True
        ).select_related('verifier').order_by('-verified_at')

        received_list = []
        for v in received_verifications:
            received_list.append(VerificationInfo(
                id=v.id,
                verifier_cri=v.verifier.id,
                verifier_hna=v.verifier.hna,
                verification_method=v.verification_method,
                notes=v.notes,
                verified_at=v.verified_at,
                has_signed=True
            ))

        # Get given verifications
        given_verifications = Verification.objects.filter(
            verifier=profile,
            is_active=True
        ).select_related('verified_profile').order_by('-verified_at')

        given_list = []
        for v in given_verifications:
            given_list.append(VerificationInfo(
                id=v.id,
                verified_user_id=v.verified_profile.id,
                verified_user_hna=v.verified_profile.hna,
                verifier_cri=v.verifier.id,
                verifier_hna=v.verifier.hna,
                verification_method=v.verification_method,
                notes=v.notes,
                verified_at=v.verified_at,
                has_signed=True
            ))

        return MyWoTStatusResponse(
            reputation_score=float(profile.reputation_score),
            trust_level=trust_level,
            is_verified=profile.is_verified_wot,
            verification_count=received_count,
            can_verify_others=profile.can_verify_others(),
            received_verifications=received_list,
            given_verifications=given_list
        )

    except Exception as e:
        logger.error(f"Error getting WoT status: {e}", exc_info=True)
        raise


@wot_router.get("/search/", response=dict, auth=ProfileAuth())
@ratelimit(group='wot:search', key=user_or_ip, rate='30/m')
def search_users(request, q: str):
    """
    Search users by HNA, ULID, or email
    Returns basic profile info for verification purposes
    """
    try:
        if not q or len(q) < 2:
            return {"results": []}

        # Search by HNA (local_name), ULID, or associated account email
        profiles = Profile.objects.filter(
            Q(local_name__icontains=q) |
            Q(id__icontains=q) |
            Q(account__email__icontains=q)
        ).exclude(
            id=request.auth_profile.id  # Exclude self
        ).select_related('account', 'instance').annotate(
            _verification_count=Count(
                'received_verifications',
                filter=Q(received_verifications__is_active=True)
            )
        )[:20]

        results = []
        for profile in profiles:
            # Calculate trust level
            verification_count = profile._verification_count

            if verification_count >= 10:
                trust_level = "HIGH"
            elif verification_count >= 5:
                trust_level = "MEDIUM"
            elif verification_count >= 3:
                trust_level = "BASIC"
            elif verification_count >= 1:
                trust_level = "LOW"
            else:
                trust_level = "NONE"

            results.append(UserSearchResult(
                cri=profile.id,
                hna=profile.hna,
                reputation_score=float(profile.reputation_score),
                trust_level=trust_level
            ))

        return {"results": results}

    except Exception as e:
        logger.error(f"Error searching users: {e}", exc_info=True)
        return {"results": [], "error": str(e)}


@wot_router.get("/verification-photo/{profile_id}/", auth=ProfileAuth())
@ratelimit(group='wot:verification_photo', key=user_or_ip, rate='30/m')
def get_verification_photo(request, profile_id: str):
    """
    Serve verification photo to authorized verifiers only.
    Uses X-Accel-Redirect for nginx internal redirect (private media).
    """
    from django.http import HttpResponse

    verifier = request.auth_profile

    # Only authorized verifiers can view verification photos
    if not verifier.can_verify_others():
        raise HttpError(403, "Only authorized verifiers can view verification photos")

    try:
        target = Profile.objects.get(id=profile_id)
    except Profile.DoesNotExist:
        raise HttpError(404, "Profile not found")

    try:
        vp = ProfileVerificationPhoto.objects.get(profile=target, biometric_consent=True)
    except ProfileVerificationPhoto.DoesNotExist:
        raise HttpError(404, "No verification photo found for this profile")

    # X-Accel-Redirect for nginx (serves from internal /media/private/)
    response = HttpResponse(content_type='image/jpeg')
    response['X-Accel-Redirect'] = f'/media/{vp.photo.name}'
    response['Cache-Control'] = 'no-store, no-cache'
    return response


@wot_router.post("/verify/", response={200: dict, 400: dict, 403: dict, 404: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='wot:verify', key=user_or_ip, rate='10/h', method='POST')
def create_verification(request, data: CreateVerificationRequest):
    """
    Create a new verification for another user
    Requires PGP-signed statement for authenticity
    """
    try:
        verifier = request.auth_profile

        # Check if verifier has permission to verify others
        if not verifier.can_verify_others():
            if verifier.profile_type != Profile.ProfileType.PERSONAL:
                raise HttpError(403, "Only personal profiles can verify other users. Pseudonymous profiles cannot participate in WoT verification.")
            if not verifier.pgp_public_key:
                raise HttpError(403, "You must have a PGP key to verify other users. Please create one in your profile settings.")
            raise HttpError(403, "You do not have permission to verify other users. Standard users need 3+ verifications and WoT verified status. Foundation members can verify immediately.")

        # Get target profile
        try:
            target_profile = Profile.objects.get(id=data.verified_user_id)
        except Profile.DoesNotExist:
            raise HttpError(404, "User not found")

        # Prevent self-verification
        if verifier.id == target_profile.id:
            raise HttpError(400, "Cannot verify yourself")

        # Target must have verification photo with valid face embedding
        try:
            ver_photo = ProfileVerificationPhoto.objects.get(
                profile=target_profile,
                biometric_consent=True,
            )
        except ProfileVerificationPhoto.DoesNotExist:
            raise HttpError(400, "Target user must upload a verification photo with biometric consent before WoT verification")

        if not ver_photo.face_embedding:
            raise HttpError(400, "Target user's verification photo has no face embedding. Please re-upload the photo.")

        # Block if re-confirmation in progress and not enough confirmations
        if ver_photo.reconfirmation_needed and ver_photo.reconfirmation_count < 3:
            raise HttpError(400, "Target user's photo was recently changed. Awaiting re-confirmations (need 3).")

        # Face dedup check
        from identity.services.face_dedup import check_duplicate
        duplicate = check_duplicate(bytes(ver_photo.face_embedding), exclude_profile_id=target_profile.id)
        if duplicate:
            logger.warning(f"Face dedup blocked verification: {target_profile.id} matches {duplicate['profile_id']}, distance={duplicate['distance']:.4f}")
            raise HttpError(400, "Verification blocked: this face matches an already-verified profile")

        # Check if verification already exists
        existing = Verification.objects.filter(
            verifier=verifier,
            verified_profile=target_profile,
            is_active=True
        ).exists()

        if existing:
            raise HttpError(400, "You have already verified this user")

        # Validate verification method
        valid_methods = ['IN_PERSON', 'VIDEO_CALL', 'DOCUMENTS', 'VOUCHED']
        if data.verification_method not in valid_methods:
            raise HttpError(400, f"Invalid verification method. Must be one of: {', '.join(valid_methods)}")

        # Validate timestamp (not older than 5 minutes)
        try:
            from datetime import datetime, timezone, timedelta
            timestamp_dt = datetime.fromisoformat(data.timestamp.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            age = (now - timestamp_dt).total_seconds()

            if age > 300:  # 5 minutes
                raise HttpError(400, "Verification statement expired (older than 5 minutes). Please try again.")
            if age < -60:  # Allow 1 minute clock drift into future
                raise HttpError(400, "Verification timestamp is in the future. Check your system clock.")
        except (ValueError, AttributeError) as e:
            raise HttpError(400, f"Invalid timestamp format: {e}")

        # Reconstruct expected statement (machine-readable JSON)
        expected_statement = {
            "action": "wot_verify",
            "verifier_hna": verifier.hna,
            "verifier_id": verifier.id,
            "verified_hna": target_profile.hna,
            "verified_id": target_profile.id,
            "method": data.verification_method,
            "timestamp": data.timestamp
        }

        # Verify that submitted statement matches expected
        import json
        try:
            submitted_statement = json.loads(data.statement)
            if submitted_statement != expected_statement:
                raise HttpError(400, "Statement does not match expected verification data")
        except json.JSONDecodeError:
            raise HttpError(400, "Invalid statement JSON")

        # Verify PGP signature
        # Use the statement as submitted by frontend (data.statement) for verification
        # because the signature was created against that exact string representation
        from parahub.crypto.pgp import pgp_crypto
        try:
            is_valid = pgp_crypto.verify_signature(
                message=data.statement,
                signature_data=data.signature,
                public_key_data=verifier.pgp_public_key
            )

            if not is_valid:
                raise HttpError(400, "Invalid PGP signature. Please ensure you signed with your registered PGP key.")

        except Exception as e:
            logger.error(f"PGP signature verification failed: {e}", exc_info=True)
            raise HttpError(400, f"PGP signature verification error: {str(e)}")

        with transaction.atomic():
            # Create verification (post_save signal auto-updates is_verified_wot)
            verification = Verification.objects.create(
                verifier=verifier,
                verified_profile=target_profile,
                verification_method=data.verification_method,
                notes=data.notes or "",
                signature=data.signature,  # Store PGP signature
                is_active=True
            )

            # Count toward photo re-confirmation if needed
            if ver_photo.reconfirmation_needed and ver_photo.reconfirmation_count < 3:
                ver_photo.reconfirmation_count += 1
                if ver_photo.reconfirmation_count >= 3:
                    ver_photo.reconfirmation_needed = False
                ver_photo.save(update_fields=['reconfirmation_count', 'reconfirmation_needed'])

            # Recalculate reputation based on all dimensions
            result = calculate_reputation(target_profile)
            target_profile.reputation_score = result['total']
            target_profile.save(update_fields=['reputation_score'])

        verification_count = Verification.objects.filter(
            verified_profile=target_profile,
            is_active=True
        ).count()

        logger.info(f"Verification created: {verifier.id} verified {target_profile.id} via {data.verification_method}")

        return {
            "success": True,
            "message": "User verified successfully",
            "verification_id": verification.id,
            "new_verification_count": verification_count
        }

    except HttpError:
        # Re-raise HttpError as-is (400, 403, 404 errors)
        raise
    except Exception as e:
        logger.error(f"Error creating verification: {e}", exc_info=True)
        raise HttpError(500, f"Internal server error: {str(e)}")


class ProfileVerificationsResponse(BaseModel):
    received: List[VerificationInfo]
    given: List[VerificationInfo]


@wot_router.get("/profile/{profile_id}/", response={200: ProfileVerificationsResponse, 404: dict})
@ratelimit(group='wot:profile_verifications', key='ip', rate='60/m')
def get_profile_verifications(request, profile_id: str):
    """
    Get verifications for any profile (public data).
    No auth required — WoT verifications are public by design.
    """
    try:
        profile = Profile.objects.get(id=profile_id)
    except Profile.DoesNotExist:
        raise HttpError(404, "Profile not found")

    received_qs = Verification.objects.filter(
        verified_profile=profile, is_active=True
    ).select_related('verifier').order_by('-verified_at')

    received = [
        VerificationInfo(
            id=v.id,
            verifier_cri=v.verifier.id,
            verifier_hna=v.verifier.hna,
            verification_method=v.verification_method,
            notes=v.notes,
            verified_at=v.verified_at,
            has_signed=bool(v.signature),
        )
        for v in received_qs
    ]

    given_qs = Verification.objects.filter(
        verifier=profile, is_active=True
    ).select_related('verified_profile').order_by('-verified_at')

    given = [
        VerificationInfo(
            id=v.id,
            verifier_cri=v.verifier.id,
            verifier_hna=v.verifier.hna,
            verified_user_id=v.verified_profile.id,
            verified_user_hna=v.verified_profile.hna,
            verification_method=v.verification_method,
            notes=v.notes,
            verified_at=v.verified_at,
            has_signed=bool(v.signature),
        )
        for v in given_qs
    ]

    return ProfileVerificationsResponse(received=received, given=given)


@wot_router.delete("/verify/{verification_cri}/", response={200: dict, 404: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='wot:revoke', key=user_or_ip, rate='10/m', method='DELETE')
def revoke_verification(request, verification_cri: str):
    """
    Revoke a verification given by the authenticated user
    """
    try:
        verifier = request.auth_profile

        # Get verification
        try:
            verification = Verification.objects.get(
                id=verification_cri,
                verifier=verifier,
                is_active=True
            )
        except Verification.DoesNotExist:
            return 404, {"error": "Verification not found or already revoked"}

        target_profile = verification.verified_profile

        with transaction.atomic():
            # Mark as inactive (post_save signal auto-updates is_verified_wot)
            verification.is_active = False
            verification.save()

            # Recalculate reputation based on all dimensions
            result = calculate_reputation(target_profile)
            target_profile.reputation_score = result['total']
            target_profile.save(update_fields=['reputation_score'])

        remaining_count = Verification.objects.filter(
            verified_profile=target_profile,
            is_active=True
        ).count()

        logger.info(f"Verification revoked: {verifier.id} -> {target_profile.id}")

        return {
            "success": True,
            "message": "Verification revoked successfully",
            "remaining_verifications": remaining_count
        }

    except Exception as e:
        logger.error(f"Error revoking verification: {e}", exc_info=True)
        return 500, {"error": str(e)}


class ReputationBreakdownResponse(BaseModel):
    identity: Decimal
    commerce: Decimal
    community: Decimal
    contribution: Decimal
    governance: Decimal
    reliability: Decimal
    total: Decimal
    active_dimensions: int


@wot_router.get("/reputation-breakdown/{profile_id}/", response=ReputationBreakdownResponse)
@ratelimit(group='wot:reputation_breakdown', key='ip', rate='60/m')
def get_reputation_breakdown(request, profile_id: str):
    """Public breakdown of a profile's 6-dimension reputation score."""
    profile = get_object_or_404(Profile, id=profile_id)
    return calculate_reputation(profile)
