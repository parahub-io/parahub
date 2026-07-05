"""
Response/request schemas shared by the profile endpoint modules.
"""


from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal
import logging


logger = logging.getLogger(__name__)

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
    has_verification_photo: bool = False  # Target uploaded a WoT verification photo (consent + face embedding) — required before anyone can verify them
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
    rentable_count: int = 0  # Active P2P bookable items (owner's own, not org-posted) → drives the "Rental" storefront button

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def model_validate(cls, obj, items_credit_count=0, items_debit_count=0, verifications_received_count=0, verifications_given_count=0, i_verified_them=False, has_verification_photo=False, contracts_active_count=0, contracts_completed_count=0, debts_active_count=0, debts_settled_count=0, invited_count=0, invited_verified_count=0, rentable_count=0, current_user=None, current_profile=None):
        # id_photo is private (media/private/) — never expose the raw file URL.
        # Reveal it only to the owner or WoT-verified viewers, and only as the
        # gated /id-photo/ endpoint (which re-checks auth + serves via X-Accel).
        viewer_can_see_id_photo = bool(
            obj.id_photo and current_profile and (
                current_profile.id == obj.id or getattr(current_profile, 'is_verified_wot', False)
            )
        )
        id_photo_url = f"/api/v1/profiles/{obj.id}/id-photo/" if viewer_can_see_id_photo else None

        # Return clean ULID + object type
        data = {
            'id': obj.id,
            'account_id': obj.account.id,
            'hna': obj.hna,
            # Real name gated to the owner + WoT-verified viewers (name_visible_to);
            # anonymous / non-WoT viewers get '' and the frontend falls back to @handle.
            'display_name': obj.display_name if obj.name_visible_to(current_profile) else '',
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
            'has_verification_photo': has_verification_photo,
            'pgp_fingerprint': obj.pgp_fingerprint or None,
            'ln_address': obj.ln_address or None,
            'spark_address': obj.spark_address or None,
            'contracts_active_count': contracts_active_count,
            'contracts_completed_count': contracts_completed_count,
            'debts_active_count': debts_active_count,
            'debts_settled_count': debts_settled_count,
            'avatar_url': obj.avatar.url if obj.avatar else None,
            'id_photo_url': id_photo_url,
            'id_photo_verified': (obj.id_photo_verified if viewer_can_see_id_photo and hasattr(obj, 'id_photo_verified') else False),
            'is_supporter': obj.is_supporter if hasattr(obj, 'is_supporter') else False,
            'invited_count': invited_count,
            'invited_verified_count': invited_verified_count,
            'country_code': obj.country_code or '',
            'rentable_count': rentable_count,
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
    name_public: bool = False  # Whether the real name is shown to everyone (privacy opt-out)

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
            # Owner viewing their own profile — always allowed; served via the gated endpoint
            'id_photo_url': (f"/api/v1/profiles/{obj.id}/id-photo/" if obj.id_photo else None),
            'id_photo_verified': obj.id_photo_verified if hasattr(obj, 'id_photo_verified') else False,
            'is_primary': obj.is_primary if hasattr(obj, 'is_primary') else True,
            'profile_type': obj.profile_type if hasattr(obj, 'profile_type') else 'PERSONAL',
            'is_foundation_member': obj.is_foundation_member(),
            'country_code': obj.country_code or '',
            'support_level': obj.support_level if hasattr(obj, 'support_level') else Decimal('0.1'),
            'notification_prefs': obj.notification_prefs if hasattr(obj, 'notification_prefs') else {},
            'name_public': obj.name_public,
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
    name_public: Optional[bool] = None

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
