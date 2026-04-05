"""
Centralized Pydantic schemas for Parahub API
Provides type-safe request/response models following SPECIFICATION.md
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, EmailStr, field_validator
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class ItemType(str, Enum):
    """Item type: offering or request"""
    CREDIT = "CREDIT"  # Offering (Предложение)
    DEBIT = "DEBIT"   # Request (Запрос)


class ItemSpecType(str, Enum):
    """Item specialization type"""
    GOODS = "GOODS"
    SERVICE = "SERVICE"
    RENTAL = "RENTAL"
    GIFT = "GIFT"
    VEHICLE = "VEHICLE"
    IOT_DEVICE = "IOT_DEVICE"
    INFO_RESOURCE = "INFO_RESOURCE"
    VIDEO_CONTENT = "VIDEO_CONTENT"
    RIDESHARE_REQUEST = "RIDESHARE_REQUEST"


class PaymentMethod(str, Enum):
    """Supported payment methods"""
    PARAHUB_LN = "parahub_ln"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"
    BARTER = "barter"
    GIFT = "gift"


class VerificationStatus(str, Enum):
    """Web of Trust verification status"""
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    REVOKED = "revoked"


# ============================================================================
# BASE SCHEMAS
# ============================================================================

class RelationSchema(BaseModel):
    """Schema for object relations"""
    type: str = Field(..., description="Type of relation (e.g., 'is_component_of')")
    target_id: str = Field(..., description="ULID of the target object")
    target_type: Optional[str] = Field(None, description="Optional type of target object")


class ULIDBase(BaseModel):
    """Base schema for all ULID-identified entities"""
    id: str = Field(..., description="ULID identifier (26 characters)")
    object_type: Optional[str] = Field(None, description="Type of the object (e.g., 'item', 'profile')")


class ULIDModelBase(ULIDBase):
    """Base schema for ULID models with attributes and relations"""
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Key-value store for intrinsic properties")
    relations: List[RelationSchema] = Field(default_factory=list, description="List of relationships to other objects")


class TimestampedBase(BaseModel):
    """Base schema with timestamps"""
    created_at: datetime
    updated_at: datetime


class LocationSchema(BaseModel):
    """Geographic location"""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy_meters: Optional[int] = Field(None, ge=0)


# ============================================================================
# IDENTITY SCHEMAS
# ============================================================================

class ProfileBase(BaseModel):
    """Base profile information"""
    local_name: str = Field(..., min_length=3, max_length=30)
    display_name: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = None
    location: Optional[LocationSchema] = None
    preferred_currency: str = Field("EUR", description="User's preferred currency for marketplace")
    animation_enabled: bool = Field(True, description="Enable UI animations (transitions, map flyTo, etc)")


class ProfileCreate(ProfileBase):
    """Profile creation request"""
    pgp_public_key: Optional[str] = None


class ProfileUpdate(BaseModel):
    """Profile update request (all fields optional)"""
    display_name: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = None
    location: Optional[LocationSchema] = None
    pgp_public_key: Optional[str] = None
    preferred_currency: Optional[str] = None
    animation_enabled: Optional[bool] = None


class ProfileResponse(ProfileBase, ULIDModelBase, TimestampedBase):
    """Profile response with full data"""
    hna: str = Field(..., description="Human-readable Network Alias")
    is_verified: bool = False
    reputation_score: Decimal = Field(default=Decimal("0.0"))
    verification_count: int = 0
    has_pgp_key: bool = False


class OrganizationBase(BaseModel):
    """Base organization information"""
    local_name: str = Field(..., min_length=3, max_length=30)
    display_name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    website: Optional[str] = None
    location: Optional[LocationSchema] = None


class OrganizationCreate(OrganizationBase):
    """Organization creation request"""
    pass


class OrganizationResponse(OrganizationBase, ULIDModelBase, TimestampedBase):
    """Organization response with full data"""
    hna: str = Field(..., description="Human-readable Network Alias")
    is_verified: bool = False
    member_count: int = 0
    owner_id: str


# ============================================================================
# MARKET SCHEMAS
# ============================================================================

class ItemBase(BaseModel):
    """Base item information"""
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = Field("", max_length=5000)
    type: ItemType
    spec_type: ItemSpecType
    spec_data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    location: Optional[LocationSchema] = None
    price_amount: Decimal = Field(Decimal("0"), ge=0)
    price_currency: str = Field("EUR", max_length=3)
    accepted_payment_methods: List[PaymentMethod] = Field(default_factory=lambda: [PaymentMethod.CASH])
    category_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ItemCreate(ItemBase):
    """Item creation request"""
    pass


class ItemUpdate(BaseModel):
    """Item update request (all fields optional)"""
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    spec_data: Optional[Dict[str, Any]] = None
    location: Optional[LocationSchema] = None
    price_amount: Optional[Decimal] = Field(None, ge=0)
    price_currency: Optional[str] = Field(None, max_length=3)
    accepted_payment_methods: Optional[List[PaymentMethod]] = None
    category_id: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None
    expected_version: int = Field(..., description="Version for optimistic locking")


class ItemResponse(ItemBase, ULIDModelBase, TimestampedBase):
    """Item response with full data"""
    owner_id: str
    owner_account_id: str
    owner_hna: str
    is_active: bool = True
    version: int = 1
    category_name: Optional[str] = None
    location_fuzzed: Optional[LocationSchema] = None  # Privacy-protected location


class ItemDetailResponse(ItemResponse):
    """Detailed item view with additional information"""
    owner_reputation: Decimal
    owner_is_verified: bool
    exact_location: Optional[LocationSchema] = None  # Only for deal participants


# ============================================================================
# VERIFICATION SCHEMAS
# ============================================================================

class VerificationCreate(BaseModel):
    """Create verification request"""
    verified_profile_id: str
    verification_type: str = Field("identity", description="Type of verification")
    notes: Optional[str] = Field(None, max_length=500)
    pgp_signature: str = Field(..., description="PGP signature of the verification")


class VerificationResponse(ULIDModelBase, TimestampedBase):
    """Verification response"""
    verifier_id: str
    verifier_hna: str
    verified_id: str
    verified_hna: str
    verification_type: str
    status: VerificationStatus
    notes: Optional[str] = None
    pgp_signature: str


# ============================================================================
# GOVERNANCE SCHEMAS
# ============================================================================

class ProposalCreate(BaseModel):
    """Create governance proposal"""
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=20, max_length=5000)
    proposal_type: str = Field("general", description="Type of proposal")
    voting_deadline: datetime
    required_quorum: Optional[Decimal] = Field(None, ge=0, le=100)


class ProposalResponse(ULIDModelBase, TimestampedBase):
    """Proposal response"""
    creator_id: str
    creator_hna: str
    title: str
    description: str
    proposal_type: str
    status: str
    voting_deadline: datetime
    required_quorum: Optional[Decimal] = None
    votes_for: int = 0
    votes_against: int = 0
    votes_abstain: int = 0


class VoteCreate(BaseModel):
    """Cast vote on proposal"""
    proposal_id: str
    vote_choice: str = Field(..., pattern="^(for|against|abstain)$")
    comment: Optional[str] = Field(None, max_length=500)
    pgp_signature: str = Field(..., description="PGP signature of the vote")


# ============================================================================
# LOGISTICS SCHEMAS
# ============================================================================

class HubBase(BaseModel):
    """Base P-Hub information"""
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    location: LocationSchema
    address: str = Field(..., max_length=200)
    operating_hours: Optional[Dict[str, str]] = None
    storage_capacity_m3: Optional[float] = Field(None, ge=0)


class HubCreate(HubBase):
    """Create P-Hub request"""
    pass


class HubResponse(HubBase, ULIDModelBase, TimestampedBase):
    """P-Hub response"""
    operator_id: str
    operator_hna: str
    is_active: bool = True
    current_occupancy_percent: Optional[float] = None


class ShipmentCreate(BaseModel):
    """Create shipment request"""
    item_id: str
    origin_hub_id: str
    destination_hub_id: str
    pickup_deadline: Optional[datetime] = None
    delivery_deadline: Optional[datetime] = None
    special_instructions: Optional[str] = Field(None, max_length=500)


class ShipmentResponse(ULIDModelBase, TimestampedBase):
    """Shipment response"""
    item_id: str
    sender_id: str
    receiver_id: str
    origin_hub_id: str
    destination_hub_id: str
    status: str
    tracking_number: str
    pickup_deadline: Optional[datetime] = None
    delivery_deadline: Optional[datetime] = None


# ============================================================================
# PAGINATION & FILTERS
# ============================================================================

class PaginationParams(BaseModel):
    """Standard pagination parameters"""
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class SearchFilters(BaseModel):
    """Standard search filters"""
    query: Optional[str] = Field(None, min_length=2, max_length=100)
    category_id: Optional[str] = None
    tags: Optional[List[str]] = None
    location: Optional[LocationSchema] = None
    radius_km: Optional[float] = Field(None, ge=0.1, le=1000)
    price_min: Optional[Decimal] = Field(None, ge=0)
    price_max: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    is_active: Optional[bool] = True


class PaginatedResponse(BaseModel):
    """Standard paginated response wrapper"""
    count: int
    next: Optional[str] = None
    previous: Optional[str] = None
    results: List[Any]  # Override with specific type in subclasses


# ============================================================================
# ADVERTISING SYSTEM
# ============================================================================

# Reference Data Schemas
class AdsInterestSchema(ULIDBase):
    """Interest category for ad targeting"""
    object_type: str = "ads_interest"
    name: str
    slug: str


class AdsSkillSchema(ULIDBase):
    """Skill category for ad targeting"""
    object_type: str = "ads_skill"
    name: str
    slug: str


class AdsChildrenAgeSchema(ULIDBase):
    """Children age range for family ad targeting"""
    object_type: str = "ads_children_age"
    name: str


class AdsProfileSkillSchema(BaseModel):
    """User's skill with rating level"""
    skill_id: str
    skill_name: str
    level: int = Field(..., ge=1, le=5, description="Skill level 1-5 (Beginner/Intermediate/Advanced/Expert/Master)")


class AdsProfileLocationSchema(BaseModel):
    """User location for geo-targeted ads"""
    id: Optional[str] = None
    label: str = Field(..., max_length=50)
    latitude: float
    longitude: float


class AdsProfileResponse(ULIDBase, TimestampedBase):
    """User's advertising profile"""
    object_type: str = "ads_profile"
    profile_id: str
    gender: str = "any"
    age: Optional[int] = None
    birth_date: Optional[str] = None  # ISO date format
    min_reward_sats: int = 0
    interests: List[str] = Field(default_factory=list, description="List of interest IDs")
    children_ages: List[str] = Field(default_factory=list, description="List of children age IDs")
    skills: List[AdsProfileSkillSchema] = Field(default_factory=list, description="Skills with ratings")
    locations: List[AdsProfileLocationSchema] = Field(default_factory=list, description="User locations for geo-targeting")
    ln_address: str = ""
    has_wallet_config: bool = False
    wallet_provider: str = ""
    total_views: int = 0
    total_earned_sats: int = 0


class AdsProfileUpdate(BaseModel):
    """Update ads profile settings"""
    gender: Optional[str] = Field(None, pattern="^(any|male|female)$")
    age: Optional[int] = Field(None, ge=13, le=120)
    birth_date: Optional[str] = Field(None, description="Birth date in ISO format (YYYY-MM-DD)")
    min_reward_sats: Optional[int] = Field(None, ge=0, description="Minimum satoshis per ad view")
    interest_ids: Optional[List[str]] = Field(None, description="List of interest IDs")
    children_age_ids: Optional[List[str]] = Field(None, description="List of children age IDs")
    skill_ratings: Optional[Dict[str, int]] = Field(None, description="Dict of skill_id -> level (1-5)")
    locations: Optional[List[AdsProfileLocationSchema]] = Field(None, description="User locations (max 3, replace-all)")
    ln_wallet_config: Optional[Dict[str, Any]] = Field(None, description="Wallet provider configuration")


class WalletTestRequest(BaseModel):
    """Test wallet provider connection"""
    provider: str = Field(..., description="Wallet provider: lnbits or alby")
    api_url: Optional[str] = Field(None, description="LNbits API URL")
    invoice_key: Optional[str] = Field(None, description="LNbits invoice key")
    admin_key: Optional[str] = Field(None, description="LNbits admin key")
    access_token: Optional[str] = Field(None, description="Alby access token")


class AdCampaignCreate(BaseModel):
    """Create new advertising campaign"""
    name: str = Field(..., min_length=1, max_length=200)
    post_title: str = Field(..., min_length=1, max_length=200)
    post_content: str = Field(..., min_length=1)
    link: Optional[str] = Field(None, max_length=500)

    @field_validator('link')
    @classmethod
    def validate_link_url(cls, v):
        if v is not None and v != '' and not v.startswith(('http://', 'https://')):
            raise ValueError('Link must be a valid HTTP or HTTPS URL')
        return v
    reward_sats: int = Field(..., ge=1, description="Satoshis per view")
    budget_sats: int = Field(..., ge=1, description="Total campaign budget")
    target_gender: str = Field("any", pattern="^(any|male|female)$")
    target_age_from: int = Field(18, ge=13, le=120)
    target_age_to: int = Field(65, ge=13, le=120)
    target_interest_ids: List[str] = Field(default_factory=list, description="Interest IDs for targeting")
    target_children_age_ids: List[str] = Field(default_factory=list)
    target_skill_ids: List[str] = Field(default_factory=list)
    target_min_skill_level: int = Field(1, ge=1, le=5)
    target_latitude: Optional[float] = Field(None, ge=-90, le=90)
    target_longitude: Optional[float] = Field(None, ge=-180, le=180)
    target_radius_km: float = Field(0, ge=0, le=50)
    include_self: bool = Field(False, description="Always show to advertiser (monitoring)")
    exclude_self: bool = Field(False, description="Never show to advertiser")
    establishment_id: Optional[str] = Field(None, description="Post on behalf of this establishment (ULID)")
    linked_item_id: Optional[str] = Field(None, description="Link a marketplace item to promote")
    linked_establishment_id: Optional[str] = Field(None, description="Link an establishment to promote")


class AdCampaignUpdate(BaseModel):
    """Update existing campaign"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    post_title: Optional[str] = Field(None, min_length=1, max_length=200)
    post_content: Optional[str] = Field(None, min_length=1)
    link: Optional[str] = Field(None, max_length=500)

    @field_validator('link')
    @classmethod
    def validate_link_url(cls, v):
        if v is not None and v != '' and not v.startswith(('http://', 'https://')):
            raise ValueError('Link must be a valid HTTP or HTTPS URL')
        return v
    status: Optional[str] = Field(None, pattern="^(draft|active|paused|completed)$")
    target_interest_ids: Optional[List[str]] = None
    target_children_age_ids: Optional[List[str]] = None
    target_skill_ids: Optional[List[str]] = None
    target_min_skill_level: Optional[int] = Field(None, ge=1, le=5)
    target_latitude: Optional[float] = Field(None, ge=-90, le=90)
    target_longitude: Optional[float] = Field(None, ge=-180, le=180)
    target_radius_km: Optional[float] = Field(None, ge=0, le=50)
    include_self: Optional[bool] = None
    exclude_self: Optional[bool] = None
    linked_item_id: Optional[str] = Field(None, description="Link a marketplace item (null to clear)")
    linked_establishment_id: Optional[str] = Field(None, description="Link an establishment (null to clear)")


class AdLinkedItemSchema(BaseModel):
    """Mini schema for linked marketplace item"""
    id: str
    title: str
    image_url: Optional[str] = None
    pricing_options: Optional[List[Dict[str, Any]]] = None


class AdLinkedEstablishmentSchema(BaseModel):
    """Mini schema for linked establishment"""
    id: str
    name: str
    slug: str
    logo_url: Optional[str] = None
    category_name: Optional[str] = None


class AdCampaignResponse(ULIDBase, TimestampedBase):
    """Ad campaign response"""
    object_type: str = "ad_campaign"
    advertiser_id: str
    name: str
    post_title: str
    post_content: str
    link: str
    image_url: Optional[str] = None
    reward_sats: int
    budget_sats: int
    spent_sats: int
    remaining_budget_sats: int
    target_gender: str
    target_age_from: int
    target_age_to: int
    target_interest_ids: List[str] = Field(default_factory=list)
    target_children_age_ids: List[str] = Field(default_factory=list)
    target_skill_ids: List[str] = Field(default_factory=list)
    target_min_skill_level: int = 1
    target_latitude: Optional[float] = None
    target_longitude: Optional[float] = None
    target_radius_km: float = 0
    status: str
    include_self: bool = False
    exclude_self: bool = False
    total_views: int
    total_clicks: int
    ctr: float
    # Act as establishment
    establishment_id: Optional[str] = None
    establishment_name: Optional[str] = None
    establishment_slug: Optional[str] = None
    establishment_logo_url: Optional[str] = None
    # Linked content
    linked_item: Optional[AdLinkedItemSchema] = None
    linked_establishment: Optional[AdLinkedEstablishmentSchema] = None


class AdFeedItem(BaseModel):
    """Ad in user's feed"""
    id: str
    object_type: str = "ad_feed_item"
    campaign_id: str
    post_title: str
    post_content: str
    link: str
    image_url: Optional[str] = None
    reward_sats: int
    advertiser_id: Optional[str] = None
    advertiser_name: Optional[str] = None
    advertiser_hna: Optional[str] = None
    # Linked content
    linked_item: Optional[AdLinkedItemSchema] = None
    linked_establishment: Optional[AdLinkedEstablishmentSchema] = None
    # Establishment branding
    establishment_name: Optional[str] = None
    establishment_logo_url: Optional[str] = None


class AdFeedHistoryItem(BaseModel):
    """Ad from user's view history"""
    id: str
    object_type: str = "ad_feed_history_item"
    campaign_id: str
    post_title: str
    post_content: str
    link: str
    image_url: Optional[str] = None
    reward_sats: int
    earned_sats: int
    payment_sent: bool = False
    viewed_at: datetime


class AdViewCreate(BaseModel):
    """Record ad view"""
    campaign_id: str


class EarningsStatsResponse(BaseModel):
    """User's earnings statistics"""
    total_views: int
    total_earned_sats: int
    avg_per_view_sats: float


# ============================================================================
# ERROR RESPONSES
# ============================================================================

class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None


class ValidationErrorResponse(ErrorResponse):
    """Validation error response"""
    error: str = "VALIDATION_ERROR"
    field_errors: Optional[Dict[str, List[str]]] = None