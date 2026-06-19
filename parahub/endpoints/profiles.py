"""
Profile Management API endpoints for Parahub
Implements Phase 2B: Profile Management APIs
"""

from ninja import Form, Router
from ninja.pagination import paginate, PageNumberPagination
from ninja.errors import HttpError
from ninja.files import UploadedFile
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.http import Http404
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal
import logging

from parahub.auth import GlobalAuth, ProfileAuth
from parahub.middleware.pgp import PGPSignatureAuth
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile, Account
from core.models import Instance

logger = logging.getLogger(__name__)

# Create profile router
profile_router = Router()

# Pydantic schemas for API request/response
class ProfilePublicResponse(BaseModel):
    id: str
    object_type: str = 'profile'
    account_id: str
    hna: str
    display_name: str
    bio: str = ''
    reputation_score: Decimal
    is_verified_wot: bool
    antispam_fee_sats: int
    is_publicly_linked: bool
    preferred_language: Optional[str] = None
    preferred_currency: str = 'EUR'
    items_credit_count: int = 0  # CREDIT = user offers (has to give)
    items_debit_count: int = 0   # DEBIT = user wants (needs to receive)
    verifications_received_count: int = 0  # How many people verified this profile
    verifications_given_count: int = 0     # How many people this profile verified
    i_verified_them: bool = False  # Whether current user already verified this profile
    pgp_fingerprint: Optional[str] = None  # PGP key fingerprint (public)
    ln_address: Optional[str] = None  # Lightning address (e.g., user@breez.tips)
    spark_address: Optional[str] = None  # Spark address for direct P2P payments
    contracts_active_count: int = 0  # SIGNED contracts (in progress)
    contracts_completed_count: int = 0  # COMPLETED contracts
    debts_active_count: int = 0  # ACTIVE + PARTIALLY_SETTLED debts
    debts_settled_count: int = 0  # FULLY_SETTLED debts
    avatar_url: Optional[str] = None  # Profile avatar URL
    id_photo_url: Optional[str] = None  # ID photo URL (for Para-ID badge)
    id_photo_verified: bool = False  # Whether ID photo passed AI validation
    is_supporter: bool = False  # Has donated to the association at least once
    invited_count: int = 0  # How many people this user invited
    invited_verified_count: int = 0  # How many invited people are verified (3+ WoT)
    is_test: bool = False  # Staff-only: test account flag
    is_bot: bool = False  # Staff-only: AI bot account flag
    is_arbiter: bool = False  # Has active arbiter profile
    country_code: str = ''  # ISO 3166-1 alpha-2

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def model_validate(cls, obj, items_credit_count=0, items_debit_count=0, verifications_received_count=0, verifications_given_count=0, i_verified_them=False, contracts_active_count=0, contracts_completed_count=0, debts_active_count=0, debts_settled_count=0, invited_count=0, invited_verified_count=0, current_user=None):
        # Return clean ULID + object type
        data = {
            'id': obj.id,
            'account_id': obj.account.id,
            'hna': obj.hna,
            'display_name': obj.display_name,
            'bio': obj.bio or '',
            'reputation_score': obj.reputation_score,
            'is_verified_wot': obj.is_verified_wot,
            'antispam_fee_sats': obj.antispam_fee_sats,
            'is_publicly_linked': obj.is_publicly_linked,
            'preferred_language': obj.preferred_language or '',
            'preferred_currency': obj.preferred_currency or 'EUR',
            'items_credit_count': items_credit_count,
            'items_debit_count': items_debit_count,
            'verifications_received_count': verifications_received_count,
            'verifications_given_count': verifications_given_count,
            'i_verified_them': i_verified_them,
            'pgp_fingerprint': obj.pgp_fingerprint or None,
            'ln_address': obj.ln_address or None,
            'spark_address': obj.spark_address or None,
            'contracts_active_count': contracts_active_count,
            'contracts_completed_count': contracts_completed_count,
            'debts_active_count': debts_active_count,
            'debts_settled_count': debts_settled_count,
            'avatar_url': obj.avatar.url if obj.avatar else None,
            'id_photo_url': obj.id_photo.url if obj.id_photo else None,
            'id_photo_verified': obj.id_photo_verified if hasattr(obj, 'id_photo_verified') else False,
            'is_supporter': obj.is_supporter if hasattr(obj, 'is_supporter') else False,
            'invited_count': invited_count,
            'invited_verified_count': invited_verified_count,
            'country_code': obj.country_code or '',
        }

        # Arbiter status
        try:
            data['is_arbiter'] = obj.arbiterprofile.is_active
        except Exception:
            pass

        # Staff-only fields
        if current_user and getattr(current_user, 'is_staff', False):
            data['is_test'] = getattr(obj.account, 'is_test', False)
            data['is_bot'] = getattr(obj.account, 'is_bot', False)

        return super().model_validate(data)

class ProfileSearchResponse(ProfilePublicResponse):
    """Extended profile response for search results with partner info"""
    is_partner: bool = False
    partner_added_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class ProfilePrivateResponse(ProfilePublicResponse):
    local_name: str
    pgp_fingerprint: str
    location: Optional[dict] = None
    map_style: str = 'osm-liberty'
    animation_enabled: bool = True
    is_staff: bool = False  # Admin flag for UI (dev mode toggle, etc.)
    is_primary: bool = True  # Whether this is the primary profile
    profile_type: str = 'PERSONAL'  # Profile type for UI logic
    is_foundation_member: bool = False  # Foundation member of Parahub Associação
    support_level: Decimal = Decimal('0.1')  # Association support percentage
    notification_prefs: dict = {}

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def model_validate(cls, obj):
        # Return clean ULID + object type
        data = {
            'id': obj.id,
            'account_id': obj.account.id,
            'hna': obj.hna,
            'display_name': obj.display_name,
            'bio': obj.bio or '',
            'reputation_score': obj.reputation_score,
            'is_verified_wot': obj.is_verified_wot,
            'antispam_fee_sats': obj.antispam_fee_sats,
            'is_publicly_linked': obj.is_publicly_linked,
            'preferred_language': obj.preferred_language or '',
            'preferred_currency': obj.preferred_currency or 'EUR',
            'local_name': obj.local_name,
            'pgp_fingerprint': obj.pgp_fingerprint,
            'location': None,  # Will be set separately
            'map_style': obj.map_style or 'osm-liberty',
            'animation_enabled': obj.animation_enabled if hasattr(obj, 'animation_enabled') else True,
            'is_staff': obj.account.is_staff if hasattr(obj, 'account') else False,
            'avatar_url': obj.avatar.url if obj.avatar else None,
            'id_photo_url': obj.id_photo.url if obj.id_photo else None,
            'id_photo_verified': obj.id_photo_verified if hasattr(obj, 'id_photo_verified') else False,
            'is_primary': obj.is_primary if hasattr(obj, 'is_primary') else True,
            'profile_type': obj.profile_type if hasattr(obj, 'profile_type') else 'PERSONAL',
            'is_foundation_member': obj.is_foundation_member(),
            'country_code': obj.country_code or '',
            'support_level': obj.support_level if hasattr(obj, 'support_level') else Decimal('0.1'),
            'notification_prefs': obj.notification_prefs if hasattr(obj, 'notification_prefs') else {},
        }
        return super(ProfilePublicResponse, cls).model_validate(data)

class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(None, max_length=255)
    bio: Optional[str] = Field(None, max_length=300)
    antispam_fee_sats: Optional[int] = Field(None, ge=0)
    location: Optional[dict] = None
    is_publicly_linked: Optional[bool] = None
    preferred_language: Optional[str] = Field(None, max_length=5)
    preferred_currency: Optional[str] = None
    map_style: Optional[str] = Field(None, max_length=20)
    animation_enabled: Optional[bool] = None
    ln_address: Optional[str] = Field(None, max_length=255)
    spark_address: Optional[str] = Field(None, max_length=512)
    country_code: Optional[str] = Field(None, max_length=2)
    support_level: Optional[Decimal] = Field(None, ge=0, le=10)
    notification_prefs: Optional[dict] = None

class PGPKeyRequest(BaseModel):
    public_key: str = Field(..., description="Armored PGP public key")

class PGPKeyResponse(BaseModel):
    fingerprint: str
    created_at: str
    is_active: bool

class PGPKeyHistoryResponse(BaseModel):
    id: str
    fingerprint: str
    public_key: str  # Include public key for export functionality
    action: str
    action_timestamp: str
    valid_from: str
    valid_until: Optional[str] = None
    is_active: bool
    validity_days: int
    # Private fields (only for owner)
    created_from_ip: Optional[str] = None
    user_agent: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class ProfileCreateRequest(BaseModel):
    profile_type: str = Field(default='PSEUDONYMOUS', description="PSEUDONYMOUS")
    local_name: str = Field(..., min_length=3, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=255)

class ProfileDetailResponse(ProfilePublicResponse):
    profile_type: str
    is_primary: bool
    can_manage: bool = False  # Whether current user can manage this profile
    animation_enabled: bool = True  # Animation preference (default: true)

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def model_validate(cls, obj, can_manage=False):
        data = {
            'id': obj.id,
            'account_id': obj.account.id,
            'hna': obj.hna,
            'display_name': obj.display_name,
            'reputation_score': obj.reputation_score,
            'is_verified_wot': obj.is_verified_wot,
            'antispam_fee_sats': obj.antispam_fee_sats,
            'is_publicly_linked': obj.is_publicly_linked,
            'preferred_language': obj.preferred_language or '',
            'preferred_currency': obj.preferred_currency or 'EUR',
            'profile_type': obj.profile_type,
            'is_primary': obj.is_primary,
            'can_manage': can_manage,
            'animation_enabled': getattr(obj, 'animation_enabled', True),
        }
        return super(ProfilePublicResponse, cls).model_validate(data)


@profile_router.get("/me/", response=ProfilePrivateResponse, auth=ProfileAuth())
@ratelimit(group='profiles:me', key=user_or_ip, rate='60/m')
def get_my_profile(request):
    """
    Get authenticated user's complete profile information

    Returns all profile data including private information
    only accessible to the profile owner.
    """
    try:
        profile = request.auth_profile

        # Auto-detect country on first request (one-time, user can override later)
        if not profile.country_code:
            from geo.utils import get_country_code_from_request
            detected = get_country_code_from_request(request)
            if detected:
                profile.country_code = detected
                profile.save(update_fields=['country_code'])

        # Convert location point to dict if exists
        location_data = None
        if profile.location:
            location_data = {
                'latitude': profile.location.y,
                'longitude': profile.location.x
            }

        response_data = ProfilePrivateResponse.model_validate(profile)
        response_data.location = location_data

        return response_data

    except Exception as e:
        logger.error(f"Error retrieving private profile: {e}")
        return {"error": "Failed to retrieve profile"}, 500


@profile_router.get("/me/mail-credentials/", auth=ProfileAuth())
@ratelimit(group='profiles:mail_credentials', key=user_or_ip, rate='30/m')
def get_mail_credentials(request):
    """Return decrypted mail password for the authenticated user (used for webmail auto-login)."""
    account = request.auth_profile.account
    if not account.mail_password:
        return {"error": "No mail account found"}, 404
    try:
        from parahub.services.mailcow import decrypt_mail_password
        from django.conf import settings as djsettings
        return {
            'username': account.username,
            'password': decrypt_mail_password(account.mail_password),
            'email': f'{account.username}@{djsettings.MAILCOW_DOMAIN}',
        }
    except Exception as e:
        logger.error(f'Failed to decrypt mail password for {account.username}: {e}')
        return {"error": "Failed to retrieve mail credentials"}, 500


@profile_router.patch("/me/preferences/", response={200: ProfilePrivateResponse, 500: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:preferences', key=user_or_ip, rate='30/m', method='PATCH')
def update_my_preferences(request, data: ProfileUpdateRequest):
    """
    Update authenticated user's preferences (language, currency, map style, animations)

    Does NOT require PGP signature for non-critical preferences.
    Only updates preference settings (not profile identity).
    """
    try:
        profile = request.auth_profile

        # Track which fields to update
        update_fields = []

        # Only update non-critical preference fields
        if data.preferred_language is not None:
            profile.preferred_language = data.preferred_language
            update_fields.append('preferred_language')

        if data.preferred_currency is not None:
            profile.preferred_currency = data.preferred_currency
            update_fields.append('preferred_currency')

        if data.map_style is not None:
            profile.map_style = data.map_style
            update_fields.append('map_style')

        if data.animation_enabled is not None:
            profile.animation_enabled = data.animation_enabled
            update_fields.append('animation_enabled')

        if data.display_name is not None:
            profile.display_name = data.display_name
            update_fields.append('display_name')

        if data.ln_address is not None:
            profile.ln_address = data.ln_address
            update_fields.append('ln_address')

        if data.spark_address is not None:
            profile.spark_address = data.spark_address
            update_fields.append('spark_address')

        if data.country_code is not None:
            profile.country_code = data.country_code.upper()
            update_fields.append('country_code')

        if data.support_level is not None:
            profile.support_level = data.support_level
            update_fields.append('support_level')

        if data.notification_prefs is not None:
            allowed_keys = {'social', 'contracts', 'governance', 'calls'}
            prefs = {k: bool(v) for k, v in data.notification_prefs.items() if k in allowed_keys}
            profile.notification_prefs = prefs
            update_fields.append('notification_prefs')

        # Save only the updated fields
        if update_fields:
            profile.save(update_fields=update_fields)

        logger.info(f"Profile preferences updated successfully: {profile.id} - fields: {update_fields}")

        # Return updated profile
        return get_my_profile(request)

    except Exception as e:
        logger.error(f"Error updating profile preferences: {e}")
        raise HttpError(500, "Failed to update preferences")


@profile_router.put("/me/", response=ProfilePrivateResponse, auth=PGPSignatureAuth())
@ratelimit(group='profiles:update', key=user_or_ip, rate='30/m', method='PUT')
def update_my_profile(request, data: ProfileUpdateRequest):
    """
    Update authenticated user's profile information

    Requires PGP signature for security.
    Only profile owner can update their profile.
    """
    try:
        profile = request.auth_profile
        
        # Update only provided fields
        if data.display_name is not None:
            profile.display_name = data.display_name

        if data.bio is not None:
            profile.bio = data.bio

        if data.antispam_fee_sats is not None:
            profile.antispam_fee_sats = data.antispam_fee_sats
        
        if data.is_publicly_linked is not None:
            profile.is_publicly_linked = data.is_publicly_linked

        if data.preferred_language is not None:
            profile.preferred_language = data.preferred_language

        if data.preferred_currency is not None:
            profile.preferred_currency = data.preferred_currency

        # Handle location update
        if data.location is not None:
            from django.contrib.gis.geos import Point
            if 'latitude' in data.location and 'longitude' in data.location:
                profile.location = Point(
                    data.location['longitude'], 
                    data.location['latitude']
                )
            elif data.location == {}:  # Empty dict means remove location
                profile.location = None
        
        profile.full_clean()
        profile.save()
        
        logger.info(f"Profile updated successfully: {profile.id}")
        
        # Return updated profile
        return get_my_profile(request)
        
    except ValidationError as e:
        logger.warning(f"Profile update validation error: {e}")
        return {"error": "Invalid profile data", "details": str(e)}, 400
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        return {"error": "Failed to update profile"}, 500


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


@profile_router.get("/manageable/", response=List[ProfileDetailResponse], auth=ProfileAuth())
@ratelimit(group='profiles:manageable', key=user_or_ip, rate='60/m')
def get_manageable_profiles(request):
    """
    Get all profiles that the authenticated user can manage

    Returns:
    - Primary personal profile
    - Organization profiles where user is owner/admin
    - Pseudonymous profiles created by this user (if primary profile)
    """
    try:
        current_profile = request.auth_profile

        # Get all manageable profiles with account preloaded
        profiles = current_profile.get_manageable_profiles().select_related('account')

        # Build response with management flag
        result = []
        for profile in profiles:
            profile_data = ProfileDetailResponse.model_validate(profile, can_manage=True)
            result.append(profile_data)

        logger.info(f"Retrieved {len(result)} manageable profiles for {current_profile.id}")
        return result

    except Exception as e:
        logger.error(f"Error retrieving manageable profiles: {e}")
        return {"error": "Failed to retrieve profiles"}, 500


@profile_router.get("/search/", response=dict, auth=ProfileAuth())
@ratelimit(group='profiles:search', key=user_or_ip, rate='60/m')
def search_profiles(request, q: Optional[str] = None, verified_only: bool = False, only_partners: bool = False, page: int = 1, page_size: int = 50):
    """
    Search for public profiles (requires authentication)

    Args:
        q: Search query for display name or local name
        verified_only: Only return WoT verified profiles
        only_partners: Only return user's partners
        page: Page number (default: 1)
        page_size: Items per page (default: 50, max: 100)
    """
    try:
        current_profile = request.auth

        queryset = Profile.objects.filter(is_publicly_linked=True).select_related('account', 'instance')

        # Hide test/bot/admin accounts and localhost instance profiles from directory listings
        queryset = queryset.exclude(account__is_test=True).exclude(account__is_bot=True).exclude(account__is_superuser=True)
        queryset = queryset.exclude(instance__domain='localhost')

        # Filter by partners if requested
        if only_partners and current_profile:
            from identity.models import Partner
            partner_ids = Partner.objects.filter(
                profile=current_profile
            ).values_list('partner_profile_id', flat=True)
            queryset = queryset.filter(id__in=partner_ids)

        # Filter by verification status
        if verified_only:
            queryset = queryset.filter(is_verified_wot=True)

        # Search by name if query provided
        if q:
            from django.db.models import Q

            # Check if query looks like HNA (contains @)
            if '@' in q:
                parts = q.split('@', 1)
                local_name_part = parts[0]
                domain_part = parts[1] if len(parts) > 1 else ''

                if domain_part:
                    # Full HNA search: local_name@domain
                    queryset = queryset.filter(
                        local_name__iexact=local_name_part,
                        instance__domain__iexact=domain_part
                    )
                else:
                    # Partial HNA: just local_name@
                    queryset = queryset.filter(local_name__istartswith=local_name_part)
            else:
                # Regular search by display_name or local_name
                queryset = queryset.filter(
                    Q(display_name__icontains=q) | Q(local_name__icontains=q)
                )

        # Order by reputation score descending
        queryset = queryset.order_by('-reputation_score', '-created_at')

        # Count total before pagination
        total_count = queryset.count()

        # Apply pagination
        page_size = min(page_size, 100)  # Max 100 items per page
        offset = (page - 1) * page_size
        paginated_queryset = queryset[offset:offset + page_size]

        # Get partner info if authenticated
        partner_map = {}
        if current_profile:
            from identity.models import Partner
            partners = Partner.objects.filter(
                profile=current_profile,
                partner_profile_id__in=[p.id for p in paginated_queryset]
            ).select_related('partner_profile')
            partner_map = {
                p.partner_profile_id: {
                    'added_at': p.added_at.isoformat() if p.added_at else None,
                }
                for p in partners
            }

        # Get item counts for ALL profiles (not just partners)
        from market.models import Item
        from django.db.models import Count, Q
        profile_ids = [p.id for p in paginated_queryset]
        item_counts = {}
        if profile_ids:
            # Use aggregation to efficiently count items per profile
            # CREDIT = user offers (has to give), DEBIT = user wants (needs to receive)
            items_query = Item.objects.filter(
                owner_id__in=profile_ids
            ).values('owner_id', 'type').annotate(count=Count('id'))

            for item in items_query:
                if item['owner_id'] not in item_counts:
                    item_counts[item['owner_id']] = {'CREDIT': 0, 'DEBIT': 0}
                item_counts[item['owner_id']][item['type']] = item['count']

        # Get verification counts for ALL profiles
        from identity.models import Verification
        verification_counts = {}
        if profile_ids:
            # Count verifications received (where profile is verified_profile)
            verifications_received_query = Verification.objects.filter(
                verified_profile_id__in=profile_ids,
                is_active=True
            ).values('verified_profile_id').annotate(count=Count('id'))

            for v in verifications_received_query:
                if v['verified_profile_id'] not in verification_counts:
                    verification_counts[v['verified_profile_id']] = {'received': 0, 'given': 0}
                verification_counts[v['verified_profile_id']]['received'] = v['count']

            # Count verifications given (where profile is verifier)
            verifications_given_query = Verification.objects.filter(
                verifier_id__in=profile_ids,
                is_active=True
            ).values('verifier_id').annotate(count=Count('id'))

            for v in verifications_given_query:
                if v['verifier_id'] not in verification_counts:
                    verification_counts[v['verifier_id']] = {'received': 0, 'given': 0}
                verification_counts[v['verifier_id']]['given'] = v['count']

        # Build response with partner info, item counts, and verification counts
        results = []
        for profile in paginated_queryset:
            partner_info = partner_map.get(profile.id, {})
            counts = item_counts.get(profile.id, {'CREDIT': 0, 'DEBIT': 0})
            verif_counts = verification_counts.get(profile.id, {'received': 0, 'given': 0})
            result = ProfileSearchResponse(
                id=profile.id,
                account_id=profile.account.id,
                hna=profile.hna,
                display_name=profile.display_name,
                reputation_score=profile.reputation_score,
                is_verified_wot=profile.is_verified_wot,
                antispam_fee_sats=profile.antispam_fee_sats,
                is_publicly_linked=profile.is_publicly_linked,
                preferred_language=profile.preferred_language or '',
                preferred_currency=profile.preferred_currency or 'EUR',
                bio=profile.bio or '',
                avatar_url=profile.avatar.url if profile.avatar else None,
                country_code=profile.country_code or '',
                is_partner=profile.id in partner_map,
                items_credit_count=counts.get('CREDIT', 0),
                items_debit_count=counts.get('DEBIT', 0),
                verifications_received_count=verif_counts.get('received', 0),
                verifications_given_count=verif_counts.get('given', 0),
                partner_added_at=partner_info.get('added_at'),
            )
            results.append(result)

        return {
            "items": results,
            "count": total_count,
            "page": page,
            "page_size": page_size
        }

    except Exception as e:
        logger.error(f"Error searching profiles: {e}")
        return {"items": [], "count": 0, "page": page, "page_size": page_size}


@profile_router.post("/create/", response={200: ProfileDetailResponse, 400: dict, 403: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:create', key=user_or_ip, rate='3/h', method='POST')
def create_profile(request, data: ProfileCreateRequest):
    """
    Create a new pseudonymous profile

    Requirements:
    - User must be WoT verified (3+ verifications)
    - local_name must be unique on this instance
    """
    try:
        current_profile = request.auth_profile

        # Check WoT verification requirement (must check primary profile, not current active profile)
        primary_profile = Profile.objects.filter(
            account=current_profile.account,
            is_primary=True
        ).first()

        if not primary_profile or not primary_profile.can_create_additional_profiles():
            raise HttpError(403, "Only WoT verified members can create additional profiles (3+ verifications required)")

        # Check max profiles limit (1 primary + 6 additional = 7 total)
        total_profiles = Profile.objects.filter(account=current_profile.account).count()
        if total_profiles >= 7:
            raise HttpError(403, "Maximum number of profiles reached (6 additional profiles allowed)")

        # Check if local_name is already taken
        instance = current_profile.instance
        if Profile.objects.filter(instance=instance, local_name=data.local_name).exists():
            raise HttpError(400, f"Profile name '{data.local_name}' is already taken")

        # Create new pseudonymous profile
        new_profile = Profile(
            account=current_profile.account,
            instance=instance,
            local_name=data.local_name,
            display_name=data.display_name,
            profile_type=Profile.ProfileType.PSEUDONYMOUS,
            is_primary=False,
        )

        new_profile.full_clean()
        new_profile.save()

        logger.info(f"New pseudonymous profile created: {new_profile.hna} by {current_profile.hna}")

        # Automatically switch to the newly created profile
        request.session['active_profile_id'] = new_profile.id
        request.session.modified = True

        return ProfileDetailResponse.model_validate(new_profile, can_manage=True)

    except ValidationError as e:
        logger.warning(f"Profile creation validation error: {e}")
        raise HttpError(400, f"Invalid profile data: {str(e)}")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Error creating profile: {e}")
        raise HttpError(500, "Failed to create profile")


@profile_router.get("/{id}/", response=ProfilePublicResponse, auth=None)
@ratelimit(group='profiles:public', key='ip', rate='60/m')
def get_public_profile(request, id: str):
    """
    Get public profile information by ULID or local_name (nickname)

    This endpoint returns publicly available profile data including
    reputation score, verification status, and display name.

    Supports both formats:
    - /profiles/01K2SH48YZ42G55225PMWBCHD3/ (ULID)
    - /profiles/daring-water/ (local_name/nickname)

    If user is authenticated, also returns whether they already verified this profile.
    """
    try:
        # Try to find by ULID first (26 alphanumeric chars), otherwise by local_name
        if len(id) == 26 and id.isalnum():
            profile = get_object_or_404(Profile.objects.select_related('account'), id=id)
        else:
            profile = get_object_or_404(Profile.objects.select_related('account'), local_name=id)

        # Check if profile is publicly linked
        if not profile.is_publicly_linked:
            raise Http404("Profile not found")

        # Try to get authenticated profile (optional)
        current_profile = None
        authenticated_user = None
        try:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                # Use GlobalAuth to validate JWT and get user
                global_auth = GlobalAuth()
                user = global_auth.authenticate(request, token)
                if user:
                    authenticated_user = user
                    # Get profile for this user
                    current_profile = global_auth.get_user_profile(request)
        except Exception as e:
            # Optional auth failed - this is OK for public endpoint
            logger.debug(f"Optional auth failed for profile {id}: {e}")

        # Count items for this profile
        from market.models import Item
        from django.db.models import Count, Q

        item_counts = Item.objects.filter(
            owner_id=profile.id
        ).values('type').annotate(count=Count('id'))

        counts = {'CREDIT': 0, 'DEBIT': 0}
        for item in item_counts:
            counts[item['type']] = item['count']

        # Count verifications for this profile
        from identity.models import Verification
        verifications_received = Verification.objects.filter(
            verified_profile_id=profile.id,
            is_active=True
        ).count()

        verifications_given = Verification.objects.filter(
            verifier_id=profile.id,
            is_active=True
        ).count()

        # Check if current user already verified this profile
        i_verified_them = False
        if current_profile and current_profile.id != profile.id:
            i_verified_them = Verification.objects.filter(
                verifier_id=current_profile.id,
                verified_profile_id=profile.id,
                is_active=True
            ).exists()

        # Count contracts for this profile
        from identity.models import Contract
        contracts_active = Contract.objects.filter(
            Q(creator_id=profile.id) | Q(partner_id=profile.id),
            status='SIGNED'
        ).count()

        contracts_completed = Contract.objects.filter(
            Q(creator_id=profile.id) | Q(partner_id=profile.id),
            status='COMPLETED'
        ).count()

        # Count debts for this profile
        from debts.models import Debt
        debts_active = Debt.objects.filter(
            Q(creditor_id=profile.id) | Q(debtor_id=profile.id),
            status__in=['ACTIVE', 'PARTIALLY_SETTLED']
        ).count()

        debts_settled = Debt.objects.filter(
            Q(creditor_id=profile.id) | Q(debtor_id=profile.id),
            status='FULLY_SETTLED'
        ).count()

        # Count invited users and how many are verified (3+ WoT)
        invited_profiles = Profile.objects.filter(invited_by=profile)
        invited_count = invited_profiles.count()
        invited_verified_count = 0
        if invited_count > 0:
            invited_verified_count = invited_profiles.filter(
                is_verified_wot=True
            ).filter(
                id__in=Verification.objects.filter(
                    is_active=True
                ).values('verified_profile_id').annotate(
                    cnt=Count('id')
                ).filter(cnt__gte=3).values('verified_profile_id')
            ).count()

        return ProfilePublicResponse.model_validate(
            profile,
            items_credit_count=counts.get('CREDIT', 0),
            items_debit_count=counts.get('DEBIT', 0),
            verifications_received_count=verifications_received,
            verifications_given_count=verifications_given,
            i_verified_them=i_verified_them,
            contracts_active_count=contracts_active,
            contracts_completed_count=contracts_completed,
            debts_active_count=debts_active,
            debts_settled_count=debts_settled,
            invited_count=invited_count,
            invited_verified_count=invited_verified_count,
            current_user=authenticated_user,
        )

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error retrieving public profile {id}: {e}")
        raise Http404("Profile not found")


@profile_router.get("/by-account/{account_id}/", response=ProfilePublicResponse, auth=None)
@ratelimit(group='profiles:by_account', key='ip', rate='60/m')
def get_profile_by_account(request, account_id: str):
    """
    Get primary profile by account ULID

    Returns the primary profile for a given account ID.
    Used by Matrix integration to resolve display names.
    ULIDs are case-insensitive, so we uppercase the input.
    """
    try:
        # ULID is case-insensitive - normalize to uppercase
        account_id_upper = account_id.upper()

        # Get primary profile for the account
        profile = get_object_or_404(
            Profile.objects.select_related('account'),
            account_id=account_id_upper,
            is_primary=True
        )

        # Check if profile is publicly linked
        if not profile.is_publicly_linked:
            raise Http404("Profile not found")

        # Count items for this profile
        from market.models import Item
        from django.db.models import Count

        item_counts = Item.objects.filter(
            owner_id=profile.id
        ).values('type').annotate(count=Count('id'))

        counts = {'CREDIT': 0, 'DEBIT': 0}
        for item in item_counts:
            counts[item['type']] = item['count']

        # Count verifications for this profile
        from identity.models import Verification
        verifications_received = Verification.objects.filter(
            verified_profile_id=profile.id,
            is_active=True
        ).count()

        verifications_given = Verification.objects.filter(
            verifier_id=profile.id,
            is_active=True
        ).count()

        # Count contracts for this profile
        from identity.models import Contract
        contracts_active = Contract.objects.filter(
            Q(creator_id=profile.id) | Q(partner_id=profile.id),
            status='SIGNED'
        ).count()

        contracts_completed = Contract.objects.filter(
            Q(creator_id=profile.id) | Q(partner_id=profile.id),
            status='COMPLETED'
        ).count()

        # Count debts for this profile
        from debts.models import Debt
        debts_active = Debt.objects.filter(
            Q(creditor_id=profile.id) | Q(debtor_id=profile.id),
            status__in=['ACTIVE', 'PARTIALLY_SETTLED']
        ).count()

        debts_settled = Debt.objects.filter(
            Q(creditor_id=profile.id) | Q(debtor_id=profile.id),
            status='FULLY_SETTLED'
        ).count()

        # Count invited users and how many are verified (3+ WoT)
        invited_profiles = Profile.objects.filter(invited_by=profile)
        invited_count = invited_profiles.count()
        invited_verified_count = 0
        if invited_count > 0:
            invited_verified_count = invited_profiles.filter(
                is_verified_wot=True
            ).filter(
                id__in=Verification.objects.filter(
                    is_active=True
                ).values('verified_profile_id').annotate(
                    cnt=Count('id')
                ).filter(cnt__gte=3).values('verified_profile_id')
            ).count()

        return ProfilePublicResponse.model_validate(
            profile,
            items_credit_count=counts.get('CREDIT', 0),
            items_debit_count=counts.get('DEBIT', 0),
            verifications_received_count=verifications_received,
            verifications_given_count=verifications_given,
            contracts_active_count=contracts_active,
            contracts_completed_count=contracts_completed,
            debts_active_count=debts_active,
            debts_settled_count=debts_settled,
            invited_count=invited_count,
            invited_verified_count=invited_verified_count
        )

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error retrieving profile for account {account_id}: {e}")
        raise Http404("Profile not found")


@profile_router.get("/{id}/reviews/", response=List[dict])
@ratelimit(group='profiles:reviews', key='ip', rate='60/m')
@paginate(PageNumberPagination, page_size=10)
def get_profile_reviews(request, id: str):
    """
    Get reviews for a specific profile

    Returns paginated list of reviews received by this profile.
    Note: This is a placeholder - full review system will be implemented in Phase 3.
    """
    try:
        profile = get_object_or_404(Profile, id=id)

        # Placeholder return - will be implemented with Review model in Phase 3
        return []

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error retrieving reviews for profile {id}: {e}")
        return []


@profile_router.post("/switch/{id}/", response={200: ProfileDetailResponse, 403: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:switch', key=user_or_ip, rate='30/m', method='POST')
def switch_active_profile(request, id: str):
    """
    Switch active profile context

    Allows user to switch between their manageable profiles (personal, organization, pseudonymous).
    The active profile is stored in session and used for creating items, sending messages, etc.

    Returns the newly active profile details.
    """
    try:
        current_profile = request.auth_profile
        target_profile = get_object_or_404(Profile, id=id)

        # Check if user can manage this profile (use primary profile for permission check)
        primary_profile = Profile.objects.filter(
            account=current_profile.account,
            is_primary=True
        ).first()

        # Check if target profile belongs to same account
        if target_profile.account_id != current_profile.account_id:
            raise HttpError(403, "You don't have permission to switch to this profile")

        # Store active profile in session
        request.session['active_profile_id'] = target_profile.id
        request.session.modified = True

        logger.info(f"Profile switched: {current_profile.hna} → {target_profile.hna}")

        return ProfileDetailResponse.model_validate(target_profile, can_manage=True)

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Error switching profile: {e}")
        raise HttpError(500, "Failed to switch profile")


@profile_router.delete("/{id}/", auth=ProfileAuth())
@ratelimit(group='profiles:delete', key=user_or_ip, rate='10/m', method='DELETE')
def delete_profile(request, id: str):
    """
    Delete a profile (only non-primary profiles)

    Requirements:
    - Profile must not be primary (cannot delete main profile)
    - User must have permission to manage this profile

    Deletes:
    - The profile itself
    - Profile's data (cascades automatically)

    Note: Items and other content created by this profile are NOT deleted
    """
    try:
        current_profile = request.auth_profile
        target_profile = get_object_or_404(Profile, id=id)

        # Cannot delete primary profile
        if target_profile.is_primary:
            return {
                "error": "CANNOT_DELETE_PRIMARY",
                "message": "Cannot delete primary profile"
            }, 400

        # Check if user can manage this profile
        if not current_profile.can_manage_profile(target_profile):
            return {
                "error": "PERMISSION_DENIED",
                "message": "You don't have permission to delete this profile"
            }, 403

        # Store HNA for logging
        profile_hna = target_profile.hna

        # Delete the profile (cascades to ProfileData, etc.)
        target_profile.delete()

        # If deleted profile was active in session, switch back to current profile
        if request.session.get('active_profile_id') == id:
            request.session['active_profile_id'] = current_profile.id
            request.session.modified = True

        logger.info(f"Profile deleted: {profile_hna} by {current_profile.hna}")

        return {"message": "Profile deleted successfully", "deleted_profile": profile_hna}

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error deleting profile: {e}")
        return {"error": "INTERNAL_ERROR", "message": "Failed to delete profile"}, 500


# ========== Psycho-informatics (Yellow Protocol) Endpoints ==========

class PsychProfileResponse(BaseModel):
    """Response with psycho-informatics profile data"""
    id: str
    profile_id: str
    psych_hash_4: List[str] = []
    form3_completed_at: Optional[str] = None
    psych_hash_4_updated_at: Optional[str] = None
    form3_data: Optional[dict] = None  # Only returned to owner (via /me/psych/)

    model_config = ConfigDict(from_attributes=True)


class PsychProfileUpdateRequest(BaseModel):
    """Request to update psycho-informatics profile"""
    form3_data: Optional[dict] = Field(None, description="Answers to 30 questions (1-5 scale). Format: {q1: 3, q2: 5, ...}")
    psych_hash_4: Optional[List[str]] = Field(None, description="4 words describing personality", max_length=4)


@profile_router.get("/me/psych/", response=PsychProfileResponse, auth=ProfileAuth())
@ratelimit(group='profiles:my_psych', key=user_or_ip, rate='60/m')
def get_my_psych_profile(request):
    """
    Get my psycho-informatics profile

    Returns (to owner only):
    - psych_hash_4: 4 words (PUBLIC)
    - form3_completed_at: timestamp
    - form3_data: answers to 30 questions (PRIVATE, only returned to owner)
    """
    from identity.models import PsychProfile
    from django.utils import timezone

    try:
        profile = request.auth_profile

        # Get or create PsychProfile
        psych_profile, created = PsychProfile.objects.get_or_create(profile=profile)

        return PsychProfileResponse(
            id=psych_profile.id,
            profile_id=profile.id,
            psych_hash_4=psych_profile.psych_hash_4 or [],
            form3_completed_at=psych_profile.form3_completed_at.isoformat() if psych_profile.form3_completed_at else None,
            psych_hash_4_updated_at=psych_profile.psych_hash_4_updated_at.isoformat() if psych_profile.psych_hash_4_updated_at else None,
            form3_data=psych_profile.form3_data or {},  # Return to owner
        )

    except Exception as e:
        logger.error(f"Error retrieving psych profile: {e}")
        return {"error": "INTERNAL_ERROR", "message": "Failed to retrieve psych profile"}, 500


@profile_router.post("/me/psych/", response=PsychProfileResponse, auth=ProfileAuth())
@ratelimit(group='profiles:update_psych', key=user_or_ip, rate='30/m', method='POST')
def update_my_psych_profile(request, data: PsychProfileUpdateRequest):
    """
    Update my psycho-informatics profile

    Can update:
    - form3_data: Answers to 30 questions (1-5 scale) - PRIVATE
    - psych_hash_4: 4 words - PUBLIC

    form3_data is stored but NEVER returned to users (system only).
    """
    from identity.models import PsychProfile
    from django.utils import timezone

    try:
        profile = request.auth_profile

        # Get or create PsychProfile
        psych_profile, created = PsychProfile.objects.get_or_create(profile=profile)

        # Update form3_data if provided
        if data.form3_data is not None:
            # Validate form3_data structure (30 questions, values 1-5)
            if not isinstance(data.form3_data, dict):
                return {"error": "VALIDATION_ERROR", "message": "form3_data must be a dict"}, 400

            # Validate each answer is 1-5
            for key, value in data.form3_data.items():
                if not isinstance(value, int) or value < 1 or value > 5:
                    return {
                        "error": "VALIDATION_ERROR",
                        "message": f"Invalid answer for {key}: must be integer 1-5"
                    }, 400

            psych_profile.form3_data = data.form3_data

            # Only set form3_completed_at if all 30 questions answered
            if len(data.form3_data) >= 30:
                psych_profile.form3_completed_at = timezone.now()
            else:
                psych_profile.form3_completed_at = None

        # Update psych_hash_4 if provided
        if data.psych_hash_4 is not None:
            if not isinstance(data.psych_hash_4, list) or len(data.psych_hash_4) != 4:
                return {"error": "VALIDATION_ERROR", "message": "psych_hash_4 must be array of 4 strings"}, 400

            psych_profile.psych_hash_4 = data.psych_hash_4
            psych_profile.psych_hash_4_updated_at = timezone.now()

        psych_profile.save()

        logger.info(f"Psych profile updated for {profile.hna}")

        return PsychProfileResponse(
            id=psych_profile.id,
            profile_id=profile.id,
            psych_hash_4=psych_profile.psych_hash_4 or [],
            form3_completed_at=psych_profile.form3_completed_at.isoformat() if psych_profile.form3_completed_at else None,
            psych_hash_4_updated_at=psych_profile.psych_hash_4_updated_at.isoformat() if psych_profile.psych_hash_4_updated_at else None,
            form3_data=psych_profile.form3_data or {},  # Return to owner
        )

    except Exception as e:
        logger.error(f"Error updating psych profile: {e}")
        return {"error": "INTERNAL_ERROR", "message": "Failed to update psych profile"}, 500


@profile_router.get("/{id}/psych/", response={200: PsychProfileResponse, 404: dict}, auth=GlobalAuth())
@ratelimit(group='profiles:public_psych', key=user_or_ip, rate='60/m')
def get_profile_psych_hash(request, id: str):
    """
    Get psycho-informatics data for a profile (PUBLIC DATA ONLY)

    Returns only:
    - psych_hash_4: 4 words (for WoT matching)

    Does NOT return:
    - form3_data (private, system only)
    """
    from identity.models import PsychProfile

    try:
        profile = get_object_or_404(Profile, id=id)

        # Try to get PsychProfile
        try:
            psych_profile = PsychProfile.objects.get(profile=profile)
        except PsychProfile.DoesNotExist:
            # Return empty response if no psych profile
            return PsychProfileResponse(
                id="",
                profile_id=profile.id,
                psych_hash_4=[],
                form3_completed_at=None,
                psych_hash_4_updated_at=None,
                form3_data=None,  # NEVER expose to others
            )

        # Return only PUBLIC data (psych_hash_4)
        return PsychProfileResponse(
            id=psych_profile.id,
            profile_id=profile.id,
            psych_hash_4=psych_profile.psych_hash_4 or [],
            form3_completed_at=None,  # Don't expose timestamp to others
            psych_hash_4_updated_at=None,  # Don't expose timestamp to others
            form3_data=None,  # NEVER expose to others
        )

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error retrieving psych profile for {id}: {e}")
        return {"error": "INTERNAL_ERROR", "message": "Failed to retrieve psych profile"}, 500


# ==================== Profile Notes ====================

class ProfileNoteResponse(BaseModel):
    id: str
    note: str

    model_config = ConfigDict(from_attributes=True)


class ProfileNoteInput(BaseModel):
    note: str = Field(..., max_length=10000, description="Private note content")


@profile_router.get('/{id}/note/', response={200: ProfileNoteResponse, 500: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:get_note', key=user_or_ip, rate='60/m')
def get_profile_note(request, id: str):
    """
    Get private note about a profile (only for authenticated user)
    """
    from identity.models import ProfileNote

    try:
        if len(id) == 26 and id.isalnum():
            target_profile = get_object_or_404(Profile, id=id)
        else:
            target_profile = get_object_or_404(Profile, local_name=id)
        owner_profile = request.auth_profile

        # Try to get note - raise 404 if doesn't exist
        try:
            note = ProfileNote.objects.get(owner=owner_profile, about=target_profile)
        except ProfileNote.DoesNotExist:
            raise Http404("Note not found")

        return ProfileNoteResponse(
            id=note.id,
            note=note.note
        )

    except Http404:
        raise
    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error retrieving note: {e}")
        raise HttpError(500, "Failed to retrieve note")


@profile_router.post('/{id}/note/', response={200: ProfileNoteResponse, 400: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:save_note', key=user_or_ip, rate='30/m', method='POST')
def create_or_update_profile_note(request, id: str, data: ProfileNoteInput):
    """
    Create or update private note about a profile (only for authenticated user)
    """
    from identity.models import ProfileNote

    try:
        if len(id) == 26 and id.isalnum():
            target_profile = get_object_or_404(Profile, id=id)
        else:
            target_profile = get_object_or_404(Profile, local_name=id)
        owner_profile = request.auth_profile

        # Prevent creating note about yourself
        if owner_profile.id == target_profile.id:
            raise HttpError(400, "Cannot create note about yourself")

        # Create or update note
        note, created = ProfileNote.objects.update_or_create(
            owner=owner_profile,
            about=target_profile,
            defaults={'note': data.note}
        )

        return ProfileNoteResponse(
            id=note.id,
            note=note.note
        )

    except Profile.DoesNotExist:
        raise Http404("Profile not found")
    except Exception as e:
        logger.error(f"Error creating/updating note: {e}")
        raise HttpError(500, "Failed to save note")


# =============================================================================
# Profile Photo Upload (Avatar + ID Photo)
# =============================================================================

class PhotoUploadResponse(BaseModel):
    """Response for photo upload"""
    url: str
    verified: Optional[bool] = None  # Only for ID photo
    verification_issues: Optional[List[str]] = None  # AI validation issues


@profile_router.post("/me/avatar/", response={200: PhotoUploadResponse, 400: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:upload_avatar', key=user_or_ip, rate='10/m', method='POST')
def upload_avatar(request, image: UploadedFile):
    """
    Upload avatar photo for the authenticated user.

    Avatar is automatically:
    - Cropped to square (center crop)
    - Resized to 400x400 max
    - Compressed to JPEG quality 85

    Max file size: 10MB
    """
    from PIL import Image
    from io import BytesIO
    from django.core.files.uploadedfile import InMemoryUploadedFile
    import sys

    try:
        profile = request.auth_profile

        # Validate file type
        if not image.content_type.startswith('image/'):
            return 400, {"error": "File must be an image"}

        # Validate file size (max 10MB)
        if image.size > 10 * 1024 * 1024:
            return 400, {"error": "Image size must be less than 10MB"}

        # Process image with PIL
        img = Image.open(image.file)

        # Convert to RGB if necessary
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        elif img.mode == 'RGBA':
            # Convert RGBA to RGB with white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background

        # Center crop to square
        width, height = img.size
        min_dim = min(width, height)
        left = (width - min_dim) // 2
        top = (height - min_dim) // 2
        img = img.crop((left, top, left + min_dim, top + min_dim))

        # Resize to 400x400
        img = img.resize((400, 400), Image.Resampling.LANCZOS)

        # Save to BytesIO
        output = BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)

        # Delete old avatar if exists
        if profile.avatar:
            profile.avatar.delete(save=False)

        # Create Django file object
        file_name = f"{profile.id}.jpg"
        django_file = InMemoryUploadedFile(
            output, 'ImageField', file_name,
            'image/jpeg', sys.getsizeof(output), None
        )

        # Save avatar
        profile.avatar.save(file_name, django_file, save=True)

        logger.info(f"Avatar uploaded for profile {profile.id}")

        return PhotoUploadResponse(url=profile.avatar.url)

    except Exception as e:
        logger.error(f"Error uploading avatar: {e}", exc_info=True)
        return 400, {"error": f"Failed to upload avatar: {str(e)}"}


@profile_router.delete("/me/avatar/", response={200: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:delete_avatar', key=user_or_ip, rate='10/m', method='DELETE')
def delete_avatar(request):
    """Delete avatar photo for the authenticated user."""
    try:
        profile = request.auth_profile

        if profile.avatar:
            profile.avatar.delete(save=True)
            logger.info(f"Avatar deleted for profile {profile.id}")
            return {"success": True}
        else:
            return {"success": True, "message": "No avatar to delete"}

    except Exception as e:
        logger.error(f"Error deleting avatar: {e}", exc_info=True)
        raise HttpError(500, "Failed to delete avatar")


@profile_router.post("/me/id-photo/", response={200: PhotoUploadResponse, 400: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:upload_id_photo', key=user_or_ip, rate='10/m', method='POST')
def upload_id_photo(request, image: UploadedFile):
    """
    Upload ID photo for Para-ID badge.

    ID photo is:
    - Resized to 600x800 max (3:4 ratio)
    - Compressed to JPEG quality 90
    - AI-validated for face detection (advisory, not blocking)

    Returns verification status and any issues found.
    Max file size: 10MB
    """
    from PIL import Image
    from io import BytesIO
    from django.core.files.uploadedfile import InMemoryUploadedFile
    import sys

    try:
        profile = request.auth_profile

        # Validate file type
        if not image.content_type.startswith('image/'):
            return 400, {"error": "File must be an image"}

        # Validate file size (max 10MB)
        if image.size > 10 * 1024 * 1024:
            return 400, {"error": "Image size must be less than 10MB"}

        # Process image with PIL
        img = Image.open(image.file)

        # Convert to RGB if necessary
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        elif img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background

        # Resize maintaining aspect ratio (max 600x800)
        max_width, max_height = 600, 800
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

        # Save to BytesIO for AI validation
        output = BytesIO()
        img.save(output, format='JPEG', quality=90, optimize=True)
        output.seek(0)

        # AI validation (advisory, doesn't block upload)
        verified = False
        verification_issues = []

        try:
            validation_result = _validate_id_photo_with_ai(output.getvalue(), profile)
            verified = validation_result.get('valid', False)
            verification_issues = validation_result.get('issues', [])
        except Exception as ai_error:
            logger.warning(f"AI validation failed (non-blocking): {ai_error}")
            verification_issues = ["AI validation unavailable"]

        # Reset buffer position
        output.seek(0)

        # Delete old id_photo if exists
        if profile.id_photo:
            profile.id_photo.delete(save=False)

        # Create Django file object
        file_name = f"{profile.id}.jpg"
        django_file = InMemoryUploadedFile(
            output, 'ImageField', file_name,
            'image/jpeg', sys.getsizeof(output), None
        )

        # Save id_photo and verification status
        profile.id_photo.save(file_name, django_file, save=False)
        profile.id_photo_verified = verified
        profile.save(update_fields=['id_photo', 'id_photo_verified'])

        logger.info(f"ID photo uploaded for profile {profile.id}, verified={verified}")

        return PhotoUploadResponse(
            url=profile.id_photo.url,
            verified=verified,
            verification_issues=verification_issues if verification_issues else None
        )

    except Exception as e:
        logger.error(f"Error uploading ID photo: {e}", exc_info=True)
        return 400, {"error": f"Failed to upload ID photo: {str(e)}"}


@profile_router.delete("/me/id-photo/", response={200: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:delete_id_photo', key=user_or_ip, rate='10/m', method='DELETE')
def delete_id_photo(request):
    """Delete ID photo for the authenticated user."""
    try:
        profile = request.auth_profile

        if profile.id_photo:
            profile.id_photo.delete(save=False)
            profile.id_photo_verified = False
            profile.save(update_fields=['id_photo', 'id_photo_verified'])
            logger.info(f"ID photo deleted for profile {profile.id}")
            return {"success": True}
        else:
            return {"success": True, "message": "No ID photo to delete"}

    except Exception as e:
        logger.error(f"Error deleting ID photo: {e}", exc_info=True)
        raise HttpError(500, "Failed to delete ID photo")


@profile_router.post("/me/verification-photo/", response={200: dict, 400: dict}, auth=ProfileAuth())
@ratelimit(group='profile:verification_photo', key=user_or_ip, rate='5/h', method='POST')
def upload_verification_photo(request, image: UploadedFile, biometric_consent: bool = Form(False)):
    """
    Upload verification photo for WoT face deduplication.

    Requires explicit GDPR biometric consent.
    Extracts face embedding and checks for duplicates against verified profiles.
    If updating existing photo with significantly different face, requires 3 re-confirmations.
    """
    from PIL import Image
    from io import BytesIO
    from django.core.files.uploadedfile import InMemoryUploadedFile
    from django.utils import timezone
    from identity.models import ProfileVerificationPhoto
    from identity.services.face_dedup import (
        extract_embedding, serialize_embedding, check_duplicate,
        is_significant_change, compute_photo_hash, compute_face_fingerprint,
    )
    import sys

    try:
        profile = request.auth_profile

        # Only personal profiles can have verification photos
        if profile.profile_type != Profile.ProfileType.PERSONAL:
            logger.warning(f"Verification photo 400 for profile {profile.id}: non-personal profile_type={profile.profile_type}")
            return 400, {"error": "Only personal profiles can upload verification photos"}

        # GDPR: explicit biometric consent required
        if not biometric_consent:
            logger.warning(f"Verification photo 400 for profile {profile.id}: biometric_consent=false")
            return 400, {"error": "Biometric consent is required. Please check the consent checkbox to proceed."}

        # Validate file type
        if not image.content_type.startswith('image/'):
            logger.warning(f"Verification photo 400 for profile {profile.id}: bad content_type={image.content_type}")
            return 400, {"error": "File must be an image"}

        # Validate file size (max 10MB)
        if image.size > 10 * 1024 * 1024:
            logger.warning(f"Verification photo 400 for profile {profile.id}: oversize {image.size} bytes")
            return 400, {"error": "Image size must be less than 10MB"}

        # Process image with PIL
        img = Image.open(image.file)
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        elif img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background

        # Resize (max 600x800)
        img.thumbnail((600, 800), Image.Resampling.LANCZOS)

        output = BytesIO()
        img.save(output, format='JPEG', quality=90, optimize=True)
        image_bytes = output.getvalue()
        output.seek(0)

        # Extract face embedding + non-blocking quality warnings
        try:
            embedding, quality_warnings = extract_embedding(image_bytes)
        except ValueError as e:
            logger.warning(f"Verification photo 400 for profile {profile.id}: extract_embedding ValueError: {e}")
            return 400, {"error": str(e)}

        if embedding is None:
            logger.warning(f"Verification photo 400 for profile {profile.id}: embedding is None")
            return 400, {"error": "Could not extract face features from photo"}

        embedding_bytes = serialize_embedding(embedding)
        photo_hash = compute_photo_hash(image_bytes)

        # Check for duplicates against all verified profiles
        duplicate = check_duplicate(embedding_bytes, exclude_profile_id=profile.id)
        if duplicate:
            logger.warning(f"Face dedup blocked upload for profile {profile.id}: distance={duplicate['distance']:.4f}")
            return 400, {"error": "Verification blocked: this face matches an already-verified profile"}

        # Check if updating existing photo
        reconfirmation_needed = False
        try:
            existing = ProfileVerificationPhoto.objects.get(profile=profile)
            old_embedding = bytes(existing.face_embedding)

            if old_embedding and profile.is_verified_wot:
                if is_significant_change(old_embedding, embedding_bytes):
                    reconfirmation_needed = True

            # Delete old photo file
            if existing.photo:
                existing.photo.delete(save=False)

            # Update existing record
            existing.face_embedding = embedding_bytes
            existing.photo_hash = photo_hash
            existing.biometric_consent = True
            existing.biometric_consent_at = timezone.now()
            existing.embedding_version = 1
            if reconfirmation_needed:
                existing.reconfirmation_needed = True
                existing.reconfirmation_count = 0

            file_name = f"{profile.id}_vp.jpg"
            django_file = InMemoryUploadedFile(
                output, 'ImageField', file_name, 'image/jpeg', sys.getsizeof(output), None
            )
            existing.photo.save(file_name, django_file, save=False)
            existing.save()

        except ProfileVerificationPhoto.DoesNotExist:
            # Create new record
            file_name = f"{profile.id}_vp.jpg"
            output.seek(0)
            django_file = InMemoryUploadedFile(
                output, 'ImageField', file_name, 'image/jpeg', sys.getsizeof(output), None
            )
            existing = ProfileVerificationPhoto(
                profile=profile,
                face_embedding=embedding_bytes,
                photo_hash=photo_hash,
                biometric_consent=True,
                biometric_consent_at=timezone.now(),
                embedding_version=1,
            )
            existing.photo.save(file_name, django_file, save=False)
            existing.save()

        logger.info(f"Verification photo uploaded for profile {profile.id}, reconfirmation_needed={reconfirmation_needed}")

        return {
            "success": True,
            "face_detected": True,
            "reconfirmation_needed": reconfirmation_needed,
            "quality_warnings": quality_warnings,
            "face_fingerprint": compute_face_fingerprint(embedding),
        }

    except Exception as e:
        logger.error(f"Error uploading verification photo: {e}", exc_info=True)
        return 400, {"error": f"Failed to upload verification photo: {str(e)}"}


@profile_router.delete("/me/verification-photo/", response={200: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:delete_verification_photo', key=user_or_ip, rate='10/m', method='DELETE')
def delete_verification_photo(request):
    """
    Delete verification photo and face embedding (GDPR right to erasure).
    This will also reset WoT verified status since photo is required for WoT.
    """
    from identity.models import ProfileVerificationPhoto

    try:
        profile = request.auth_profile
        try:
            vp = ProfileVerificationPhoto.objects.get(profile=profile)
            if vp.photo:
                vp.photo.delete(save=False)
            vp.delete()
            logger.info(f"Verification photo deleted for profile {profile.id}")
            return {"success": True}
        except ProfileVerificationPhoto.DoesNotExist:
            return {"success": True, "message": "No verification photo to delete"}
    except Exception as e:
        logger.error(f"Error deleting verification photo: {e}", exc_info=True)
        raise HttpError(500, "Failed to delete verification photo")


@profile_router.get("/me/verification-photo/status/", response={200: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:verification_photo_status', key=user_or_ip, rate='60/m')
def verification_photo_status(request):
    """Get current verification photo status."""
    from identity.models import ProfileVerificationPhoto
    from identity.services.face_dedup import face_fingerprint_from_bytes

    try:
        profile = request.auth_profile
        try:
            vp = ProfileVerificationPhoto.objects.get(profile=profile)
            return {
                "has_photo": True,
                "biometric_consent": vp.biometric_consent,
                "reconfirmation_needed": vp.reconfirmation_needed,
                "reconfirmation_count": vp.reconfirmation_count,
                "uploaded_at": vp.uploaded_at.isoformat() if vp.uploaded_at else None,
                "face_fingerprint": face_fingerprint_from_bytes(bytes(vp.face_embedding)) if vp.face_embedding else None,
            }
        except ProfileVerificationPhoto.DoesNotExist:
            return {"has_photo": False}
    except Exception as e:
        logger.error(f"Error getting verification photo status: {e}", exc_info=True)
        raise HttpError(500, "Failed to get verification photo status")


def _validate_id_photo_with_ai(image_bytes: bytes, profile) -> dict:
    """
    Validate ID photo using AI vision.

    Uses existing AI vision infrastructure with quota system.
    Returns: {"valid": bool, "confidence": float, "issues": list, "face_detected": bool}
    """
    from parahub.services.quota import QuotaService
    from parahub.models import AISettings
    import base64
    import json

    # Check quota (uses same quota as AI analysis)
    quota_info = QuotaService.check_quota(profile.account_id, 'ai_analysis')
    if quota_info['remaining'] <= 0:
        return {
            "valid": False,
            "confidence": 0.0,
            "issues": ["AI quota exceeded for today"],
            "face_detected": False
        }

    # Get AI settings
    try:
        ai_settings = AISettings.objects.first()
        if not ai_settings:
            raise ValueError("AI settings not configured")
    except Exception:
        return {
            "valid": False,
            "confidence": 0.0,
            "issues": ["AI service not configured"],
            "face_detected": False
        }

    # Prepare prompt for ID photo validation.
    # This photo goes on the Para-ID badge (a "this is me" portrait shown to humans),
    # not into face embeddings — so we don't enforce passport-style composition.
    # The WoT verification photo has its own pipeline with embedding-quality checks.
    prompt = """Analyze this photo for use as a personal ID badge portrait. Check:
1. Exactly one person visible (not zero, not multiple)
2. A face is visible and recognizable as the same person (not a back of the head, not heavily obscured)
3. Eyes are visible (no opaque sunglasses, eyes open)
4. Photo is in focus (not heavily blurred)

Composition, framing, background, lighting style, accessories (hats, glasses, makeup), and mood are NOT issues — the user picks their own portrait style.

Return ONLY valid JSON with no markdown formatting:
{"valid": true/false, "confidence": 0.0-1.0, "issues": ["list of problems found"], "face_detected": true/false, "face_count": number}

If the photo meets the four checks above, set valid=true and issues=[].
"""

    # Call AI provider
    try:
        if ai_settings.provider == 'gemini-2.5-flash-lite':
            result = _call_gemini_vision(ai_settings, image_bytes, prompt)
        elif ai_settings.provider.startswith('claude'):
            result = _call_claude_vision(ai_settings, image_bytes, prompt)
        elif ai_settings.provider.startswith('gpt'):
            result = _call_openai_vision(ai_settings, image_bytes, prompt)
        else:
            # Default to Gemini
            result = _call_gemini_vision(ai_settings, image_bytes, prompt)

        # Consume quota after successful validation
        QuotaService.consume_quota(profile.account_id, 'ai_analysis', metadata={'type': 'id_photo_validation'})

        return result

    except Exception as e:
        logger.error(f"AI vision call failed: {e}")
        return {
            "valid": False,
            "confidence": 0.0,
            "issues": [f"AI validation error: {str(e)}"],
            "face_detected": False
        }


def _call_gemini_vision(ai_settings, image_bytes: bytes, prompt: str) -> dict:
    """Call Gemini Vision API for ID photo validation."""
    from google import genai
    from google.genai import types as genai_types
    import json

    client = genai.Client(api_key=ai_settings.google_api_key)
    image_part = genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    response = client.models.generate_content(
        model='gemini-2.0-flash-lite',
        contents=[prompt, image_part]
    )

    # Parse JSON response
    text = response.text.strip()
    # Remove markdown code blocks if present
    if text.startswith('```'):
        text = text.split('\n', 1)[1]
        if text.endswith('```'):
            text = text.rsplit('```', 1)[0]
        text = text.strip()

    return json.loads(text)


def _call_claude_vision(ai_settings, image_bytes: bytes, prompt: str) -> dict:
    """Call Claude Vision API for ID photo validation."""
    import anthropic
    import base64
    import json

    client = anthropic.Anthropic(api_key=ai_settings.claude_api_key)

    response = client.messages.create(
        model="claude-haiku-4-5-20250514",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.b64encode(image_bytes).decode()
                    }
                },
                {"type": "text", "text": prompt}
            ]
        }]
    )

    return json.loads(response.content[0].text)


def _call_openai_vision(ai_settings, image_bytes: bytes, prompt: str) -> dict:
    """Call OpenAI Vision API for ID photo validation."""
    import openai
    import base64
    import json

    client = openai.OpenAI(api_key=ai_settings.openai_api_key)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"
                    }
                }
            ]
        }]
    )

    return json.loads(response.choices[0].message.content)


# =============================================================================
# Para-ID Badge Generation
# =============================================================================

class BadgeOptionsRequest(BaseModel):
    """Options for badge generation"""
    include_birth_date: bool = True
    include_pgp: bool = True


@profile_router.get("/me/badge/", auth=ProfileAuth())
@ratelimit(group='profiles:badge', key=user_or_ip, rate='30/m')
def download_my_badge(
    request,
    format: str = "single",
    include_birth_date: bool = True,
    include_pgp: bool = True
):
    """
    Generate and download Para-ID badge PDF for the authenticated user.

    Query params:
        format: "single" (54x86mm) or "batch" (9 cards on A4) - default: single
        include_birth_date: Include birth date if available (default: true)
        include_pgp: Include PGP fingerprint if available (default: true)

    Single mode: Returns a printable PDF badge (54x86mm) suitable for lanyard display.
    Batch mode: Returns A4 PDF with 9 identical badges and cut lines for economical printing.
    """
    from django.http import HttpResponse
    from parahub.services.badge_generator import BadgeGenerator

    try:
        profile = request.auth_profile

        # Generate PDF based on format
        if format == "batch":
            pdf_bytes = BadgeGenerator.generate_batch(
                profile,
                include_pgp=include_pgp,
            )
            filename = f"parahub-{profile.local_name}-batch.pdf"
        else:
            pdf_bytes = BadgeGenerator.generate(
                profile,
                include_birth_date=include_birth_date,
                include_pgp=include_pgp,
            )
            filename = f"parahub-{profile.local_name}.pdf"

        # Return as downloadable PDF
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        logger.error(f"Error generating badge: {e}")
        raise HttpError(500, "Failed to generate badge")
