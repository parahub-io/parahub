"""
Building, Establishment, Membership, and Review endpoints.
"""

from ninja import Router, UploadedFile
from ninja.errors import HttpError
from ninja.pagination import paginate, PageNumberPagination
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import logging
from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.core.cache import cache
from django.db.models import Q, Count, F
from django.http import HttpResponse
import orjson
from datetime import datetime

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.endpoints.ai_vision import _is_valid_image_magic
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

router = Router(tags=["Geo / Directory"])


def _resolve_establishment(establishment_id: str, **kwargs):
    """Resolve establishment by ULID or slug."""
    from geo.models import Establishment
    try:
        return Establishment.objects.get(id=establishment_id, **kwargs)
    except Establishment.DoesNotExist:
        return get_object_or_404(Establishment, slug=establishment_id, **kwargs)


# ===== Schemas =====

class LocationInput(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class BuildingInput(BaseModel):
    """Create/update world object (building)"""
    osm_way_id: Optional[int] = None
    location: LocationInput
    country: str = Field(..., max_length=2, pattern="^[A-Z]{2}$")
    city: str = Field(..., max_length=255)
    street: Optional[str] = Field(None, max_length=255)
    house_number: Optional[str] = Field(None, max_length=20)
    postal_code: Optional[str] = Field(None, max_length=20)
    full_address: str = Field(..., max_length=500)
    building_type: Optional[str] = Field(None, max_length=50)
    levels: Optional[int] = Field(None, ge=1, le=200)


class BuildingResponse(BaseModel):
    id: str
    object_type: str = "world_object"
    osm_way_id: Optional[int] = None
    xeno_source: str = ""
    xeno_id: str = ""
    location: Dict[str, float]  # {lat, lon}
    country: str
    city: str
    street: Optional[str]
    house_number: Optional[str]
    postal_code: Optional[str]
    full_address: str
    building_type: Optional[str]
    levels: Optional[int]
    establishments_count: int
    created_at: datetime
    updated_at: datetime


class EstablishmentInput(BaseModel):
    """Create/update establishment"""
    world_object_id: Optional[str] = None
    name: str = Field(..., max_length=255)
    slug: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    category_id: Optional[str] = None
    is_online: bool = False
    organization_type: Optional[str] = None
    parent_id: Optional[str] = None
    location: Optional[LocationInput] = None
    floor: Optional[str] = Field(None, max_length=10)
    office_number: Optional[str] = Field(None, max_length=50)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = None
    website: Optional[str] = None
    social_links: Optional[Dict[str, str]] = None
    opening_hours: Optional[Dict[str, str]] = None
    logo_url: Optional[str] = None
    photos: Optional[List[str]] = None
    attributes: Optional[Dict[str, Any]] = None
    ln_address: Optional[str] = None
    spark_address: Optional[str] = None
    matrix_room_id: Optional[str] = None
    legal_entity_id: Optional[str] = None
    requires_terms_acceptance: bool = False
    terms_url: Optional[str] = None
    member_visibility: str = "PUBLIC"


class EstablishmentPhotoResponse(BaseModel):
    id: str
    object_type: str = "establishment_photo"
    url: str
    order: int
    caption: str


class EstablishmentResponse(BaseModel):
    id: str
    object_type: str = "establishment"
    owner_id: Optional[str] = None  # null for imported/ownerless establishments (OSM churches, gov buildings)
    world_object: Optional[BuildingResponse] = None
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    is_online: bool = False
    organization_type: Optional[str] = None
    legal_entity_id: Optional[str] = None
    member_visibility: str = "PUBLIC"
    requires_terms_acceptance: bool = False
    terms_url: Optional[str] = None
    matrix_room_id: Optional[str] = None
    ln_address: Optional[str] = None
    spark_address: Optional[str] = None
    parent_id: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    category_slug: Optional[str] = None
    category_icon: Optional[str] = None
    location: Optional[Dict[str, float]] = None
    floor: Optional[str] = None
    office_number: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    social_links: Dict[str, str] = {}
    opening_hours: Dict[str, str] = {}
    logo_url: Optional[str] = None
    photos: List[str] = []
    uploaded_photos: List[EstablishmentPhotoResponse] = []
    attributes: Dict[str, Any] = {}
    views_count: int = 0
    rating_avg: float = 0.0
    rating_count: int = 0
    is_verified: bool = False
    is_active: bool = True
    member_count: int = 0
    rentable_count: int = 0  # active bookable items → drives the "Rental" entry button
    is_member: bool = False
    user_membership_level: Optional[str] = None
    treasury_enabled: bool = False
    is_hub: bool = False
    hub_capacity: Optional[int] = None
    hub_max_days: int = 14
    hub_storage_fee_daily: int = 0
    hub_accepted_sizes: List[str] = []
    hub_instructions: str = ""
    is_demo: bool = False
    created_at: datetime
    updated_at: datetime


class EstablishmentListItem(BaseModel):
    """Simplified for list views"""
    id: str
    object_type: str = "establishment"
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    organization_type: Optional[str] = None
    is_online: bool = False
    category_name: Optional[str] = None
    category_icon: Optional[str] = None
    full_address: Optional[str] = None
    location: Optional[Dict[str, float]] = None
    building_osm_way_id: Optional[int] = None
    phone: Optional[str] = None
    logo_url: Optional[str] = None
    opening_hours: Dict[str, str] = {}
    is_verified: bool = False
    is_active: bool = True
    views_count: int = 0
    rating_avg: float = 0.0
    rating_count: int = 0
    member_count: int = 0
    is_demo: bool = False


class MembershipResponse(BaseModel):
    profile_id: str
    profile_hna: str
    profile_display_name: Optional[str] = None
    role: str
    position_title: str = ''
    joined_at: datetime
    membership_level: Optional[str] = None
    is_treasurer: bool = False
    is_auditor: bool = False


class JoinEstablishmentRequest(BaseModel):
    terms_accepted: bool = False
    membership_level: Optional[str] = None


class PostableEstablishment(BaseModel):
    """Simplified establishment for 'post as' dropdown"""
    id: str
    name: str
    slug: Optional[str] = None
    logo_url: Optional[str] = None
    role: str


class MyEstablishment(BaseModel):
    """The current user's establishment + their role/standing in it.
    Powers the standalone "My organizations" page (/org)."""
    id: str
    name: str
    slug: Optional[str] = None
    logo_url: Optional[str] = None
    organization_type: Optional[str] = None
    role: str
    position_title: Optional[str] = None
    is_treasurer: bool = False
    is_auditor: bool = False
    is_verified: bool = False
    member_count: int = 0


class TreasurerResponse(BaseModel):
    profile_id: str
    profile_hna: str
    ln_address: Optional[str] = None
    spark_address: Optional[str] = None


class SetTreasurerRequest(BaseModel):
    profile_id: str = Field(..., description="Profile ULID of the member to set as treasurer")


class AuditorResponse(BaseModel):
    profile_id: str
    profile_hna: str
    profile_display_name: Optional[str] = None
    appointed_at: datetime


class SetAuditorRequest(BaseModel):
    profile_id: str = Field(..., description="Profile ULID of the user to set as auditor (Fiscal Único)")


class ReviewInput(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    text: str = ""


class ReviewReplyInput(BaseModel):
    owner_reply: str


class ReviewResponse(BaseModel):
    id: str
    object_type: str = "establishment_review"
    establishment_id: str
    author_id: str
    author_hna: str
    author_display_name: str = ''
    rating: int
    text: str
    wot_count_snapshot: int
    owner_reply: str
    created_at: datetime
    updated_at: datetime


# ===== Helpers =====

def _format_establishment_response(establishment, request=None) -> EstablishmentResponse:
    """Helper to format Establishment model to response"""
    from geo.models import EstablishmentMembership
    from core.models import ObjectPhoto
    from market.visibility import visible_items_q  # rentable_count must respect item visibility

    world_object_data = _format_world_object_response(establishment.world_object) if establishment.world_object else None

    location_data = None
    if establishment.location:
        location_data = {"lat": establishment.location.y, "lon": establishment.location.x}

    # Membership info for current user
    is_member = False
    user_membership_level = None
    if request and hasattr(request, 'auth_profile') and request.auth_profile:
        try:
            membership = EstablishmentMembership.objects.get(
                profile=request.auth_profile, establishment=establishment)
            is_member = True
            user_membership_level = membership.membership_level
        except EstablishmentMembership.DoesNotExist:
            pass

    # Uploaded photos
    uploaded_photos_data = [
        EstablishmentPhotoResponse(
            id=p.id,
            url=p.image.url,
            order=p.order,
            caption=p.caption,
        )
        for p in ObjectPhoto.objects.filter(object_id=establishment.id)
    ]

    return EstablishmentResponse(
        id=establishment.id,
        owner_id=establishment.owner_id,
        world_object=world_object_data,
        name=establishment.name,
        slug=establishment.slug or None,
        description=establishment.description,
        is_online=establishment.is_online,
        organization_type=establishment.organization_type or None,
        legal_entity_id=establishment.legal_entity_id or None,
        member_visibility=establishment.member_visibility,
        requires_terms_acceptance=establishment.requires_terms_acceptance,
        terms_url=establishment.terms_url or None,
        matrix_room_id=establishment.matrix_room_id or None,
        ln_address=establishment.ln_address or None,
        spark_address=establishment.spark_address or None,
        parent_id=establishment.parent_id,
        category_id=establishment.category_id,
        category_name=establishment.category.name if establishment.category else None,
        category_slug=establishment.category.slug if establishment.category else None,
        category_icon=establishment.category.icon if establishment.category else None,
        location=location_data,
        floor=establishment.floor,
        office_number=establishment.office_number,
        phone=establishment.phone,
        email=establishment.email,
        website=establishment.website,
        social_links=establishment.social_links,
        opening_hours=establishment.opening_hours,
        logo_url=establishment.logo_url,
        photos=establishment.photos,
        uploaded_photos=uploaded_photos_data,
        attributes=establishment.attributes,
        views_count=establishment.views_count,
        rating_avg=float(establishment.rating_avg),
        rating_count=establishment.rating_count,
        is_verified=establishment.is_verified,
        is_active=establishment.is_active,
        member_count=establishment.memberships.count(),
        rentable_count=establishment.posted_items.filter(
            is_active=True, bookable__isnull=False, bookable__is_active=True
        ).filter(visible_items_q(request)).count(),
        is_member=is_member,
        user_membership_level=user_membership_level,
        treasury_enabled=establishment.treasury_enabled,
        is_hub=establishment.is_hub,
        hub_capacity=establishment.hub_capacity,
        hub_max_days=establishment.hub_max_days,
        hub_storage_fee_daily=establishment.hub_storage_fee_daily,
        hub_accepted_sizes=establishment.hub_accepted_sizes or [],
        hub_instructions=establishment.hub_instructions or "",
        is_demo=bool(establishment.attributes.get('__demo_seed') or establishment.attributes.get('demo')),
        created_at=establishment.created_at,
        updated_at=establishment.updated_at
    )


def _format_review(review, viewer=None) -> ReviewResponse:
    return ReviewResponse(
        id=review.id,
        establishment_id=review.establishment_id,
        author_id=review.author_id,
        author_hna=review.author.hna,
        author_display_name=(review.author.display_name or '') if review.author.name_visible_to(viewer) else '',
        rating=review.rating,
        text=review.text,
        wot_count_snapshot=review.wot_count_snapshot,
        owner_reply=review.owner_reply,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


def _format_world_object_response(wo) -> BuildingResponse:
    """Helper to format WorldObject to BuildingResponse."""
    osm_way_id = None
    if wo.xeno_source == 'osm' and wo.xeno_id.startswith('way/'):
        try:
            osm_way_id = int(wo.xeno_id.split('/')[1])
        except (ValueError, IndexError):
            pass
    return BuildingResponse(
        id=wo.id,
        osm_way_id=osm_way_id,
        xeno_source=wo.xeno_source,
        xeno_id=wo.xeno_id,
        location={"lat": wo.location.y, "lon": wo.location.x} if wo.location else {"lat": 0, "lon": 0},
        country=wo.country,
        city=wo.city,
        street=wo.street,
        house_number=wo.house_number,
        postal_code=wo.postal_code,
        full_address=wo.full_address,
        building_type=wo.building_type,
        levels=wo.levels,
        establishments_count=wo.establishments_count,
        created_at=wo.created_at,
        updated_at=wo.updated_at,
    )


# ===== Building Endpoints =====

@router.post("/buildings/", auth=ProfileAuth(), response=BuildingResponse)
@ratelimit(group='directory:create_building', key=user_or_ip, rate='60/m', method='POST')
def create_building(request, payload: BuildingInput):
    """Create new building. Requires WoT level 3+ (or admin/parahub member)"""
    from geo.models import WorldObject
    from identity.models import Verification

    # Skip WoT check for admins
    if not request.auth.account.is_superuser:
        # Skip WoT check for Parahub organization members
        is_parahub_member = request.auth.is_foundation_member()

        if not is_parahub_member:
            # Check WoT (requires 3+ verifications)
            verification_count = Verification.objects.filter(
                verified_profile=request.auth,
                is_active=True
            ).count()
            if verification_count < 3:
                raise HttpError(403, "Requires WoT level 3+ to create buildings (or be admin/parahub member)")

    with transaction.atomic():
        if payload.osm_way_id:
            # OSM-linked building: deduplicate by xeno_source/xeno_id
            wo, created = WorldObject.objects.get_or_create(
                xeno_source='osm',
                xeno_id=f'way/{payload.osm_way_id}',
                defaults={
                    'location': Point(payload.location.longitude, payload.location.latitude, srid=4326),
                    'country': payload.country,
                    'city': payload.city,
                    'street': payload.street or "",
                    'house_number': payload.house_number or "",
                    'postal_code': payload.postal_code or "",
                    'full_address': payload.full_address,
                    'building_type': payload.building_type or "",
                    'levels': payload.levels
                }
            )
        else:
            # No OSM ID: find nearby existing or create new
            from django.contrib.gis.db.models.functions import Distance
            point = Point(payload.location.longitude, payload.location.latitude, srid=4326)
            nearby = WorldObject.objects.filter(
                location__distance_lte=(point, D(m=30)),
                xeno_source='',
            ).annotate(dist=Distance('location', point)).order_by('dist').first()
            if nearby:
                wo = nearby
            else:
                wo = WorldObject.objects.create(
                    location=point,
                    country=payload.country,
                    city=payload.city,
                    street=payload.street or "",
                    house_number=payload.house_number or "",
                    postal_code=payload.postal_code or "",
                    full_address=payload.full_address,
                    building_type=payload.building_type or "",
                    levels=payload.levels,
                )

    return _format_world_object_response(wo)


@router.get("/buildings/{building_id}/", auth=None, response=BuildingResponse)
@ratelimit(group='directory:get_building', key='ip', rate='120/m')
def get_building(request, building_id: str):
    """Get building (world object) details"""
    from geo.models import WorldObject

    wo = get_object_or_404(WorldObject, id=building_id)
    return _format_world_object_response(wo)


# ===== Establishment Endpoints =====

@router.post("/establishments/", auth=ProfileAuth(), response={200: EstablishmentResponse, 403: dict, 404: dict})
@ratelimit(group='directory:create_establishment', key=user_or_ip, rate='60/m', method='POST')
def create_establishment(request, payload: EstablishmentInput):
    """Create new establishment. Requires WoT level 3+ (or admin/parahub member)"""
    from geo.models import Establishment, WorldObject
    from taxonomy.models import Category
    from identity.models import Verification

    # Skip WoT check for admins
    if not request.auth.account.is_superuser:
        # Skip WoT check for Parahub organization members
        is_parahub_member = request.auth.is_foundation_member()

        if not is_parahub_member:
            # Check WoT (requires 3+ verifications)
            verification_count = Verification.objects.filter(
                verified_profile=request.auth,
                is_active=True
            ).count()
            if verification_count < 3:
                raise HttpError(403, "Requires WoT level 3+ to create establishments (or be admin/parahub member)")

    with transaction.atomic():
        # Get world object if provided
        world_object = None
        if payload.world_object_id:
            world_object = get_object_or_404(WorldObject, id=payload.world_object_id)

        # Get category if provided
        category = None
        if payload.category_id:
            category = get_object_or_404(Category, id=payload.category_id)

        # Create establishment
        location_point = None
        if payload.location:
            location_point = Point(payload.location.longitude, payload.location.latitude, srid=4326)

        establishment = Establishment.objects.create(
            owner=request.auth,
            world_object=world_object,
            name=payload.name,
            slug=payload.slug or "",  # auto-generated in save() if empty
            description=payload.description or "",
            category=category,
            is_online=payload.is_online,
            organization_type=payload.organization_type or "",
            parent_id=payload.parent_id,
            location=location_point,
            floor=payload.floor or "",
            office_number=payload.office_number or "",
            phone=payload.phone or "",
            email=payload.email or "",
            website=payload.website or "",
            social_links=payload.social_links or {},
            opening_hours=payload.opening_hours or {},
            logo_url=payload.logo_url or "",
            photos=payload.photos or [],
            attributes=payload.attributes or {},
            ln_address=payload.ln_address or "",
            spark_address=payload.spark_address or "",
            matrix_room_id=payload.matrix_room_id or "",
            legal_entity_id=payload.legal_entity_id or "",
            requires_terms_acceptance=payload.requires_terms_acceptance,
            terms_url=payload.terms_url or "",
            member_visibility=payload.member_visibility,
        )

        # Update world object counter
        if world_object:
            world_object.establishments_count = world_object.establishments.filter(is_active=True).count()
            world_object.save(update_fields=['establishments_count'])

    return _format_establishment_response(establishment)


@router.get("/establishments/my-postable/", auth=ProfileAuth(), response=List[PostableEstablishment])
@ratelimit(group='directory:my_postable', key=user_or_ip, rate='60/m')
def my_postable_establishments(request):
    """
    List establishments where the current user can post content.
    Returns establishments where user has OWNER/ADMIN/MEMBER role.
    Used for the 'Post as' dropdown in create forms.
    """
    from geo.models import Establishment, EstablishmentMembership
    from geo.permissions import POSTING_ROLES

    profile = request.auth

    # Get memberships with posting roles
    memberships = EstablishmentMembership.objects.filter(
        profile=profile,
        role__in=POSTING_ROLES,
        establishment__is_active=True
    ).select_related('establishment')

    result = [
        PostableEstablishment(
            id=m.establishment.id,
            name=m.establishment.name,
            slug=m.establishment.slug or None,
            logo_url=m.establishment.logo_url or None,
            role=m.role,
        )
        for m in memberships
    ]

    # Also include establishments where user is owner (might not have membership row)
    owned = Establishment.objects.filter(owner=profile, is_active=True).exclude(
        id__in=[m.establishment_id for m in memberships]
    )
    for est in owned:
        result.append(PostableEstablishment(
            id=est.id,
            name=est.name,
            slug=est.slug or None,
            logo_url=est.logo_url or None,
            role='OWNER',
        ))

    return result


# Role display priority for the "My organizations" page: management first.
_MY_ORG_ROLE_ORDER = {'OWNER': 0, 'ADMIN': 1, 'MEMBER': 2, 'EMPLOYEE': 3, 'CONTRACTOR': 4}


@router.get("/establishments/mine/", auth=ProfileAuth(), response=List[MyEstablishment])
@ratelimit(group='directory:my_establishments', key=user_or_ip, rate='60/m')
def my_establishments(request):
    """
    Every establishment the current user belongs to (any membership role) or owns,
    each tagged with their role + standing. Powers the standalone "My organizations"
    page (/org).

    Unlike /my-postable/ (OWNER/ADMIN/MEMBER only, for the 'post as' picker), this
    also includes EMPLOYEE/CONTRACTOR so the page is a complete view of the user's
    affiliations — the frontend groups them by role (manage / member / work).

    Must be defined BEFORE the {establishment_id} route to avoid collision.
    """
    from geo.models import Establishment, EstablishmentMembership

    profile = request.auth

    # Membership rows carry role + custom position title + treasurer/auditor flags.
    by_est = {
        m['establishment_id']: m
        for m in EstablishmentMembership.objects.filter(
            profile=profile, establishment__is_active=True
        ).values('establishment_id', 'role', 'position_title', 'is_treasurer', 'is_auditor')
    }

    # Owners may lack a membership row — synthesize an OWNER entry for those.
    owned_ids = Establishment.objects.filter(
        owner=profile, is_active=True
    ).values_list('id', flat=True)
    for est_id in owned_ids:
        if est_id not in by_est:
            by_est[est_id] = {
                'establishment_id': est_id, 'role': 'OWNER',
                'position_title': '', 'is_treasurer': False, 'is_auditor': False,
            }

    if not by_est:
        return []

    # One annotated query for display fields + member counts.
    ests = Establishment.objects.filter(
        id__in=by_est.keys(), is_active=True
    ).annotate(mc=Count('memberships')).values(
        'id', 'name', 'slug', 'logo_url', 'organization_type', 'is_verified', 'mc'
    )

    result = []
    for e in ests:
        m = by_est[e['id']]
        result.append(MyEstablishment(
            id=e['id'],
            name=e['name'],
            slug=e['slug'] or None,
            logo_url=e['logo_url'] or None,
            organization_type=e['organization_type'] or None,
            role=m['role'],
            position_title=m['position_title'] or None,
            is_treasurer=m['is_treasurer'],
            is_auditor=m['is_auditor'],
            is_verified=e['is_verified'],
            member_count=e['mc'],
        ))

    result.sort(key=lambda r: (_MY_ORG_ROLE_ORDER.get(r.role, 9), r.name.lower()))
    return result


class GovernmentMapItem(BaseModel):
    id: str
    name: str
    slug: Optional[str] = None
    latitude: float
    longitude: float
    category_slug: Optional[str] = None


@router.get("/establishments/government-map/", auth=None)
@ratelimit(group='directory:gov_map', key='ip', rate='60/m')
def government_map(request):
    """Public lightweight list of government establishments for the map layer."""
    cache_key = 'geo:gov_map'
    cached = cache.get(cache_key)
    if cached:
        return HttpResponse(cached, content_type='application/json')

    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("""SELECT e.id, e.name, e.slug,
                              ST_Y(e.location::geometry), ST_X(e.location::geometry),
                              c.slug
                       FROM geo_establishment e
                       LEFT JOIN taxonomy_category c ON e.category_id = c.id
                       WHERE e.organization_type = 'GOVERNMENT'
                         AND e.is_active = true
                         AND e.location IS NOT NULL""")
        rows = cur.fetchall()

    result = [
        {
            'id': r[0],
            'name': r[1],
            'slug': r[2],
            'latitude': r[3],
            'longitude': r[4],
            'category_slug': r[5],
        }
        for r in rows
    ]
    body = orjson.dumps(result)
    cache.set(cache_key, body, 3600)
    return HttpResponse(body, content_type='application/json')


class ChurchMapItem(BaseModel):
    id: str
    name: str
    slug: Optional[str] = None
    latitude: float
    longitude: float
    denomination: Optional[str] = None


@router.get("/establishments/church-map/", auth=None)
@ratelimit(group='directory:church_map', key='ip', rate='60/m')
def church_map(request):
    """Public lightweight list of churches for the map layer."""
    cache_key = 'geo:church_map'
    cached = cache.get(cache_key)
    if cached:
        return HttpResponse(cached, content_type='application/json')

    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("""SELECT e.id, e.name, e.slug,
                              ST_Y(e.location::geometry), ST_X(e.location::geometry),
                              e.attributes->>'denomination'
                       FROM geo_establishment e
                       JOIN taxonomy_category c ON e.category_id = c.id
                       WHERE c.slug = 'church'
                         AND e.is_active = true
                         AND e.location IS NOT NULL""")
        rows = cur.fetchall()

    result = [
        {
            'id': r[0],
            'name': r[1],
            'slug': r[2],
            'latitude': r[3],
            'longitude': r[4],
            'denomination': r[5],
        }
        for r in rows
    ]
    body = orjson.dumps(result)
    cache.set(cache_key, body, 3600)
    return HttpResponse(body, content_type='application/json')


@router.get("/establishments/{establishment_id}/", auth=OptionalProfileAuth(), response=EstablishmentResponse)
@ratelimit(group='directory:get_establishment', key='ip', rate='120/m')
def get_establishment(request, establishment_id: str):
    """Get establishment details by ULID or slug. Increments view counter."""
    from geo.models import Establishment

    qs = Establishment.objects.select_related('world_object', 'category', 'owner')
    try:
        establishment = qs.get(id=establishment_id, is_active=True)
    except Establishment.DoesNotExist:
        establishment = get_object_or_404(qs, slug=establishment_id, is_active=True)

    # Increment views
    Establishment.objects.filter(id=establishment.id).update(views_count=F('views_count') + 1)
    establishment.refresh_from_db()

    return _format_establishment_response(establishment, request=request)


@router.get("/establishments/", auth=OptionalProfileAuth())
@ratelimit(group='directory:list', key='ip', rate='120/m')
def list_establishments(
    request,
    world_object_id: Optional[str] = None,
    category_id: Optional[str] = None,
    search: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: Optional[float] = None,
    city: Optional[str] = None,
    street: Optional[str] = None,
    house_number: Optional[str] = None,
    country: Optional[str] = None,
    organization_type: Optional[str] = None,
    is_online: Optional[bool] = None,
    my_memberships: Optional[bool] = None,
    owned_only: Optional[bool] = None,
    page: int = 1,
):
    """
    List establishments with filters. Raw SQL with server-side pagination.
    ORM was loading all 11K rows then slicing — now uses LIMIT/OFFSET.
    """
    page_size = 20
    offset = (max(page, 1) - 1) * page_size

    conditions = ["e.is_active = true"]
    params = []

    # Hide test/bot accounts for non-staff users
    user = getattr(request, 'user', None)
    is_privileged = (user and getattr(user, 'is_authenticated', False)
                     and (getattr(user, 'is_staff', False) or getattr(user, 'is_test', False)))
    if not is_privileged:
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM identity_profile ip "
            "JOIN identity_account ia ON ip.account_id = ia.id "
            "WHERE ip.id = e.owner_id AND (ia.is_test = true OR ia.is_bot = true))"
        )

    if world_object_id:
        conditions.append("e.world_object_id = %s")
        params.append(world_object_id)
    if category_id:
        conditions.append("e.category_id = %s")
        params.append(category_id)
    if organization_type:
        conditions.append("e.organization_type = %s")
        params.append(organization_type)
    if is_online is not None:
        conditions.append("e.is_online = %s")
        params.append(is_online)
    if owned_only:
        # Directory "organizations" tab: real member-orgs only, exclude ownerless
        # OSM imports (churches/parish councils) that belong on the map overlays.
        conditions.append("e.owner_id IS NOT NULL")
    if my_memberships and hasattr(request, 'auth_profile') and request.auth_profile:
        conditions.append(
            "EXISTS (SELECT 1 FROM geo_establishmentmembership em "
            "WHERE em.establishment_id = e.id AND em.profile_id = %s)"
        )
        params.append(request.auth_profile.id)
    if search:
        conditions.append("(e.name ILIKE %s OR e.description ILIKE %s)")
        params.extend([f'%{search}%', f'%{search}%'])
    if lat is not None and lon is not None and radius_km:
        radius_m = radius_km * 1000
        conditions.append(
            "(ST_DWithin(b.location::geography, "
            "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s) "
            "OR ST_DWithin(e.location::geography, "
            "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s))"
        )
        params.extend([lon, lat, radius_m, lon, lat, radius_m])
    if city:
        conditions.append("b.city ILIKE %s")
        params.append(f'%{city}%')
    if street:
        conditions.append("b.street ILIKE %s")
        params.append(f'%{street}%')
    if house_number:
        conditions.append("LOWER(b.house_number) = LOWER(%s)")
        params.append(house_number)
    if country:
        conditions.append("LOWER(b.country) = LOWER(%s)")
        params.append(country)

    where = " AND ".join(conditions)
    base_from = (
        "FROM geo_establishment e "
        "LEFT JOIN geo_worldobject b ON e.world_object_id = b.id "
        "LEFT JOIN taxonomy_category c ON e.category_id = c.id"
    )

    with connection.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) {base_from} WHERE {where}", params)
        total = cur.fetchone()[0]

        cur.execute(f"""
            SELECT e.id, e.name, e.slug, LEFT(e.description, 200),
                   e.organization_type, e.is_online,
                   c.name, c.icon,
                   b.full_address,
                   CASE WHEN b.xeno_source = 'osm' AND b.xeno_id LIKE 'way/%%'
                        THEN CAST(SUBSTRING(b.xeno_id FROM 5) AS BIGINT) ELSE NULL END,
                   ST_Y(b.location::geometry), ST_X(b.location::geometry),
                   ST_Y(e.location::geometry), ST_X(e.location::geometry),
                   e.phone, e.logo_url, e.opening_hours,
                   e.is_verified, e.is_active, e.views_count,
                   e.rating_avg, e.rating_count, e.attributes,
                   (SELECT COUNT(*) FROM geo_establishmentmembership m
                    WHERE m.establishment_id = e.id) AS member_count,
                   c.slug
            {base_from}
            WHERE {where}
            ORDER BY e.is_verified DESC, e.views_count DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        rows = cur.fetchall()

    items = []
    for r in rows:
        loc = None
        if r[10] is not None and r[11] is not None:
            loc = {'lat': r[10], 'lon': r[11]}
        elif r[12] is not None and r[13] is not None:
            loc = {'lat': r[12], 'lon': r[13]}
        # Raw cursor returns JSONB as string — parse manually
        attrs = orjson.loads(r[22]) if isinstance(r[22], str) else (r[22] or {})
        hours = orjson.loads(r[16]) if isinstance(r[16], str) else (r[16] or {})
        items.append({
            'id': r[0], 'object_type': 'establishment',
            'name': r[1], 'slug': r[2] or None,
            'description': r[3], 'organization_type': r[4] or None,
            'is_online': r[5], 'category_name': r[6], 'category_icon': r[7] or None,
            'category_slug': r[24],
            'full_address': r[8], 'location': loc,
            'building_osm_way_id': r[9], 'phone': r[14],
            'logo_url': r[15] or None, 'opening_hours': hours,
            'is_verified': r[17], 'is_active': r[18], 'views_count': r[19],
            'rating_avg': float(r[20]) if r[20] else 0.0,
            'rating_count': r[21],
            'member_count': r[23] if r[4] else 0,
            'is_demo': bool(attrs.get('__demo_seed') or attrs.get('demo')),
        })

    body = orjson.dumps({'items': items, 'count': total})
    return HttpResponse(body, content_type='application/json')


@router.get("/buildings/{building_id}/establishments/", auth=None, response=List[EstablishmentListItem])
@ratelimit(group='directory:building_establishments', key='ip', rate='120/m')
def get_building_establishments(request, building_id: str):
    """Get all establishments in a building"""
    from geo.models import Establishment, WorldObject

    wo = get_object_or_404(WorldObject, id=building_id)
    establishments = Establishment.objects.filter(world_object=wo, is_active=True).select_related('category').order_by('-is_verified', 'name')

    # Derive osm_way_id from xeno_id for backward compat
    osm_way_id = None
    if wo.xeno_source == 'osm' and wo.xeno_id.startswith('way/'):
        try:
            osm_way_id = int(wo.xeno_id.split('/')[1])
        except (ValueError, IndexError):
            pass

    return [
        EstablishmentListItem(
            id=est.id,
            name=est.name,
            category_name=est.category.name if est.category else None,
            category_icon=est.category.icon if est.category else None,
            full_address=wo.full_address,
            location={"lat": wo.location.y, "lon": wo.location.x} if wo.location else None,
            building_osm_way_id=osm_way_id,
            phone=est.phone,
            opening_hours=est.opening_hours or {},
            is_verified=est.is_verified,
            is_active=est.is_active,
            views_count=est.views_count,
            is_demo=bool(est.attributes.get('__demo_seed') or est.attributes.get('demo')),
        )
        for est in establishments
    ]


@router.put("/establishments/{establishment_id}/", auth=ProfileAuth(), response={200: EstablishmentResponse, 403: dict, 404: dict})
@ratelimit(group='directory:update_establishment', key=user_or_ip, rate='60/m', method='PUT')
def update_establishment(request, establishment_id: str, payload: EstablishmentInput):
    """Update establishment. Only owner can update."""
    from geo.models import Establishment, WorldObject
    from taxonomy.models import Category

    establishment = _resolve_establishment(establishment_id, is_active=True)

    # Check ownership
    if establishment.owner_id != request.auth.id:
        raise HttpError(403, "Only owner can update establishment")

    with transaction.atomic():
        # Update world object if changed
        if payload.world_object_id and payload.world_object_id != (establishment.world_object_id or ""):
            old_wo = establishment.world_object
            establishment.world_object = get_object_or_404(WorldObject, id=payload.world_object_id)

            # Update counters
            if old_wo:
                old_wo.establishments_count = old_wo.establishments.filter(is_active=True).count()
                old_wo.save(update_fields=['establishments_count'])

            establishment.world_object.establishments_count = establishment.world_object.establishments.filter(is_active=True).count()
            establishment.world_object.save(update_fields=['establishments_count'])

        # Update category if provided
        if payload.category_id:
            establishment.category = get_object_or_404(Category, id=payload.category_id)

        # Update location if provided
        if payload.location:
            establishment.location = Point(payload.location.longitude, payload.location.latitude, srid=4326)

        # Update fields
        establishment.name = payload.name
        establishment.description = payload.description or ""
        establishment.floor = payload.floor or ""
        establishment.office_number = payload.office_number or ""
        establishment.phone = payload.phone or ""
        establishment.email = payload.email or ""
        establishment.website = payload.website or ""
        establishment.social_links = payload.social_links or {}
        establishment.opening_hours = payload.opening_hours or {}
        establishment.logo_url = payload.logo_url or ""
        establishment.photos = payload.photos or []
        establishment.attributes = payload.attributes or {}

        establishment.slug = payload.slug or establishment.slug
        establishment.is_online = payload.is_online
        establishment.organization_type = payload.organization_type or establishment.organization_type
        establishment.ln_address = payload.ln_address or establishment.ln_address
        establishment.spark_address = payload.spark_address or establishment.spark_address
        establishment.matrix_room_id = payload.matrix_room_id or establishment.matrix_room_id
        establishment.legal_entity_id = payload.legal_entity_id or establishment.legal_entity_id
        establishment.requires_terms_acceptance = payload.requires_terms_acceptance
        establishment.terms_url = payload.terms_url or establishment.terms_url
        establishment.member_visibility = payload.member_visibility

        if payload.parent_id:
            establishment.parent_id = payload.parent_id

        establishment.save()

    return _format_establishment_response(establishment)


@router.delete("/establishments/{establishment_id}/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='directory:delete_establishment', key=user_or_ip, rate='10/m', method='DELETE')
def delete_establishment(request, establishment_id: str):
    """Deactivate establishment (soft delete). Only owner can delete."""
    from geo.models import Establishment

    establishment = _resolve_establishment(establishment_id, is_active=True)

    # Check ownership
    if establishment.owner_id != request.auth.id:
        raise HttpError(403, "Only owner can delete establishment")

    with transaction.atomic():
        establishment.is_active = False
        establishment.save(update_fields=['is_active'])

        # Update world object counter
        if establishment.world_object:
            establishment.world_object.establishments_count = establishment.world_object.establishments.filter(is_active=True).count()
            establishment.world_object.save(update_fields=['establishments_count'])

    return {"success": True, "message": "Establishment deactivated"}


# ===== Establishment Membership Endpoints =====

@router.post("/establishments/{establishment_id}/join/", auth=ProfileAuth(), response={200: MembershipResponse, 400: dict, 404: dict})
@ratelimit(group='directory:join', key=user_or_ip, rate='30/m', method='POST')
def join_establishment(request, establishment_id: str, data: JoinEstablishmentRequest):
    """Join an establishment/organization as a member."""
    from geo.models import Establishment, EstablishmentMembership

    profile = request.auth_profile
    establishment = _resolve_establishment(establishment_id, is_active=True)

    if EstablishmentMembership.objects.filter(profile=profile, establishment=establishment).exists():
        raise HttpError(400, "Already a member")

    if establishment.requires_terms_acceptance and not data.terms_accepted:
        raise HttpError(400, "Must accept terms to join")

    membership = EstablishmentMembership.objects.create(
        profile=profile,
        establishment=establishment,
        role=EstablishmentMembership.Role.MEMBER,
        terms_accepted_at=datetime.now() if establishment.requires_terms_acceptance else None,
        membership_level=data.membership_level or 'apoiante',
    )

    return MembershipResponse(
        profile_id=profile.id,
        profile_hna=profile.hna,
        profile_display_name=profile.display_name,
        role=membership.role,
        position_title=membership.position_title,
        joined_at=membership.created_at,
        membership_level=membership.membership_level,
        is_treasurer=membership.is_treasurer,
        is_auditor=membership.is_auditor,
    )


@router.post("/establishments/{establishment_id}/leave/", auth=ProfileAuth(), response={200: dict, 400: dict, 404: dict})
@ratelimit(group='directory:leave', key=user_or_ip, rate='30/m', method='POST')
def leave_establishment(request, establishment_id: str):
    """Leave an establishment/organization."""
    from geo.models import Establishment, EstablishmentMembership

    profile = request.auth_profile
    establishment = _resolve_establishment(establishment_id)

    try:
        membership = EstablishmentMembership.objects.get(profile=profile, establishment=establishment)
    except EstablishmentMembership.DoesNotExist:
        raise HttpError(404, "Not a member")

    if membership.role == EstablishmentMembership.Role.OWNER:
        owner_count = EstablishmentMembership.objects.filter(
            establishment=establishment, role=EstablishmentMembership.Role.OWNER).count()
        if owner_count <= 1:
            raise HttpError(400, "Cannot leave: you are the last owner")

    membership.delete()
    return {"message": f"Left {establishment.name}"}


@router.get("/establishments/{establishment_id}/members/", auth=None, response=List[MembershipResponse])
@ratelimit(group='directory:members', key='ip', rate='120/m')
def list_establishment_members(request, establishment_id: str):
    """List members of an establishment/organization."""
    from geo.models import Establishment, EstablishmentMembership

    establishment = _resolve_establishment(establishment_id)

    memberships = EstablishmentMembership.objects.filter(
        establishment=establishment
    ).select_related('profile', 'profile__instance').order_by('-created_at')

    # Real name gated to name_public / owner / WoT viewers; others get the @handle
    # (frontend falls back to profile_hna). Mirrors _format_review in this module.
    viewer = getattr(request, 'auth_profile', None)

    return [
        MembershipResponse(
            profile_id=m.profile.id,
            profile_hna=m.profile.hna,
            profile_display_name=(m.profile.display_name or '') if m.profile.name_visible_to(viewer) else '',
            role=m.role,
            position_title=m.position_title,
            joined_at=m.created_at,
            membership_level=m.membership_level,
            is_treasurer=m.is_treasurer,
            is_auditor=m.is_auditor,
        )
        for m in memberships
    ]


@router.get("/establishments/{establishment_id}/terms/", auth=None, response={200: dict, 404: dict})
@ratelimit(group='directory:terms', key='ip', rate='120/m')
def get_establishment_terms(request, establishment_id: str):
    """Get establishment terms/estatutos."""
    from geo.models import Establishment

    qs = Establishment.objects.all()
    try:
        establishment = qs.get(id=establishment_id)
    except Establishment.DoesNotExist:
        establishment = get_object_or_404(qs, slug=establishment_id)

    if not establishment.terms_url and not establishment.terms_content:
        raise HttpError(404, "No terms available")

    # terms_content is owner-authored markdown rendered via v-html on the public
    # estatutos page. Sanitize server-side (markdown -> HTML -> nh3 allowlist) so
    # a hostile owner can't land stored XSS on every visitor. Strip the leading
    # "# Title" preamble first (the page header already shows the name).
    terms_content_html = ''
    if establishment.terms_content:
        from cms.models import render_markdown
        import re
        md = establishment.terms_content
        m = re.search(r'^## ', md, re.MULTILINE)
        if m and m.start() > 0:
            md = md[m.start():]
        terms_content_html = render_markdown(md)

    return {
        "establishment_id": establishment.id,
        "establishment_name": establishment.name,
        "establishment_slug": establishment.slug,
        "terms_url": establishment.terms_url,
        # Raw markdown kept for backward-compat / non-HTML consumers; the UI
        # renders the sanitized terms_content_html, never this.
        "terms_content": establishment.terms_content,
        "terms_content_html": terms_content_html,
        "requires_acceptance": establishment.requires_terms_acceptance,
    }


# ===== Establishment Treasurer =====

@router.get("/establishments/{establishment_id}/treasurer/", auth=None, response={200: dict, 404: dict})
@ratelimit(group='directory:get_treasurer', key='ip', rate='60/m')
def get_treasurer(request, establishment_id: str):
    """Get current treasurer for an establishment."""
    from geo.models import Establishment
    from geo.permissions import get_treasurer_profile

    qs = Establishment.objects.all()
    try:
        establishment = qs.get(id=establishment_id, is_active=True)
    except Establishment.DoesNotExist:
        establishment = get_object_or_404(qs, slug=establishment_id, is_active=True)

    treasurer = get_treasurer_profile(establishment)
    if not treasurer:
        raise HttpError(404, "No treasurer set")

    return TreasurerResponse(
        profile_id=treasurer.id,
        profile_hna=treasurer.hna,
        ln_address=establishment.ln_address or None,
        spark_address=establishment.spark_address or None,
    )


@router.put("/establishments/{establishment_id}/treasurer/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='directory:set_treasurer', key=user_or_ip, rate='10/m', method='PUT')
def set_treasurer(request, establishment_id: str, data: SetTreasurerRequest):
    """
    Set a member as treasurer for an establishment.
    Only OWNER/ADMIN can manage the treasurer.
    Syncs the member's ln_address/spark_address to the establishment.
    """
    from geo.models import Establishment, EstablishmentMembership
    from geo.permissions import get_establishment_for_action, TREASURER_MGMT_ROLES

    establishment = get_establishment_for_action(establishment_id, request.auth, TREASURER_MGMT_ROLES)

    # Verify target profile is a member
    try:
        target_membership = EstablishmentMembership.objects.select_related('profile').get(
            establishment=establishment, profile_id=data.profile_id
        )
    except EstablishmentMembership.DoesNotExist:
        raise HttpError(404, "Profile is not a member of this establishment")

    with transaction.atomic():
        # Clear existing treasurer
        EstablishmentMembership.objects.filter(
            establishment=establishment, is_treasurer=True
        ).update(is_treasurer=False)

        # Set new treasurer
        target_membership.is_treasurer = True
        target_membership.save(update_fields=['is_treasurer'])

        # Sync payment addresses only if establishment has none set
        # (treasurer can set a separate org wallet via Establishment settings)
        treasurer_profile = target_membership.profile
        changed = False
        if not establishment.ln_address and treasurer_profile.ln_address:
            establishment.ln_address = treasurer_profile.ln_address
            changed = True
        if not establishment.spark_address and treasurer_profile.spark_address:
            establishment.spark_address = treasurer_profile.spark_address
            changed = True
        if changed:
            establishment.save(update_fields=['ln_address', 'spark_address'])

    return TreasurerResponse(
        profile_id=treasurer_profile.id,
        profile_hna=treasurer_profile.hna,
        ln_address=establishment.ln_address or None,
        spark_address=establishment.spark_address or None,
    )


@router.delete("/establishments/{establishment_id}/treasurer/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='directory:remove_treasurer', key=user_or_ip, rate='10/m', method='DELETE')
def remove_treasurer(request, establishment_id: str):
    """Remove the treasurer from an establishment. Only OWNER/ADMIN can manage."""
    from geo.models import EstablishmentMembership
    from geo.permissions import get_establishment_for_action, TREASURER_MGMT_ROLES

    establishment = get_establishment_for_action(establishment_id, request.auth, TREASURER_MGMT_ROLES)

    updated = EstablishmentMembership.objects.filter(
        establishment=establishment, is_treasurer=True
    ).update(is_treasurer=False)

    if not updated:
        raise HttpError(404, "No treasurer to remove")

    # Don't clear payment addresses — org may have its own wallet

    return {"ok": True}


# ===== Payment Address =====

class PaymentAddressRequest(BaseModel):
    spark_address: str = ''


@router.patch("/establishments/{establishment_id}/payment-address/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='directory:payment_address', key=user_or_ip, rate='30/m', method='PATCH')
def update_payment_address(request, establishment_id: str, data: PaymentAddressRequest):
    """Update establishment payment address. OWNER/ADMIN or treasurer can update."""
    from geo.models import Establishment, EstablishmentMembership

    establishment = _resolve_establishment(establishment_id, is_active=True)

    # Check: owner, admin, or treasurer
    profile = request.auth
    allowed = False
    if establishment.owner_id == profile.id:
        allowed = True
    else:
        try:
            membership = EstablishmentMembership.objects.get(
                profile=profile, establishment=establishment
            )
            if membership.role in ('ADMIN',) or membership.is_treasurer:
                allowed = True
        except EstablishmentMembership.DoesNotExist:
            pass

    if not allowed:
        raise HttpError(403, "Not authorized to update payment address")

    establishment.spark_address = data.spark_address.strip()
    establishment.save(update_fields=['spark_address'])

    return {'ok': True, 'spark_address': establishment.spark_address}


# ===== Establishment Auditor (Fiscal Único) =====

@router.get("/establishments/{establishment_id}/auditor/", auth=None, response={200: dict, 404: dict})
@ratelimit(group='directory:get_auditor', key='ip', rate='60/m')
def get_auditor(request, establishment_id: str):
    """Get current auditor (Fiscal Único) for an establishment."""
    from geo.models import Establishment, EstablishmentMembership

    qs = Establishment.objects.all()
    try:
        establishment = qs.get(id=establishment_id, is_active=True)
    except Establishment.DoesNotExist:
        establishment = get_object_or_404(qs, slug=establishment_id, is_active=True)

    membership = EstablishmentMembership.objects.filter(
        establishment=establishment, is_auditor=True
    ).select_related('profile').first()

    if not membership:
        raise HttpError(404, "No auditor set")

    # Real name gated to name_public / owner / WoT viewers; others get the @handle.
    viewer = getattr(request, 'auth_profile', None)

    return AuditorResponse(
        profile_id=membership.profile.id,
        profile_hna=membership.profile.hna,
        profile_display_name=(membership.profile.display_name or '') if membership.profile.name_visible_to(viewer) else '',
        appointed_at=membership.created_at,
    )


@router.put("/establishments/{establishment_id}/auditor/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='directory:set_auditor', key=user_or_ip, rate='10/m', method='PUT')
def set_auditor(request, establishment_id: str, data: SetAuditorRequest):
    """
    Set a user as auditor (Fiscal Único) for an establishment.
    Only OWNER/ADMIN can manage the auditor.
    Auditor does not need to be a prior member — membership is auto-created if needed.
    """
    from geo.models import Establishment, EstablishmentMembership
    from geo.permissions import get_establishment_for_action, AUDITOR_MGMT_ROLES
    from identity.models import Profile

    establishment = get_establishment_for_action(establishment_id, request.auth, AUDITOR_MGMT_ROLES)

    # Verify target profile exists
    try:
        target_profile = Profile.objects.get(id=data.profile_id)
    except Profile.DoesNotExist:
        raise HttpError(404, "Profile not found")

    with transaction.atomic():
        # Clear existing auditor
        EstablishmentMembership.objects.filter(
            establishment=establishment, is_auditor=True
        ).update(is_auditor=False)

        # Get or create membership for auditor
        membership, _created = EstablishmentMembership.objects.get_or_create(
            establishment=establishment, profile=target_profile,
            defaults={'role': EstablishmentMembership.Role.MEMBER}
        )

        membership.is_auditor = True
        membership.save(update_fields=['is_auditor'])

    return AuditorResponse(
        profile_id=target_profile.id,
        profile_hna=target_profile.hna,
        profile_display_name=target_profile.display_name,
        appointed_at=membership.created_at,
    )


@router.delete("/establishments/{establishment_id}/auditor/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='directory:remove_auditor', key=user_or_ip, rate='10/m', method='DELETE')
def remove_auditor(request, establishment_id: str):
    """Remove the auditor from an establishment. Only OWNER/ADMIN can manage."""
    from geo.models import EstablishmentMembership
    from geo.permissions import get_establishment_for_action, AUDITOR_MGMT_ROLES

    establishment = get_establishment_for_action(establishment_id, request.auth, AUDITOR_MGMT_ROLES)

    updated = EstablishmentMembership.objects.filter(
        establishment=establishment, is_auditor=True
    ).update(is_auditor=False)

    if not updated:
        raise HttpError(404, "No auditor to remove")

    return {"ok": True}


# ===== Establishment Photos =====

@router.post("/establishments/{establishment_id}/photos/", auth=ProfileAuth(), response={201: EstablishmentPhotoResponse, 400: dict, 403: dict})
@ratelimit(group='directory:upload_photo', key=user_or_ip, rate='10/m', method='POST')
def upload_establishment_photo(request, establishment_id: str, image: UploadedFile, order: int = 0, caption: str = ""):
    """Upload a photo for an establishment (max 10). Owner only."""
    from PIL import Image
    from io import BytesIO
    from django.core.files.uploadedfile import InMemoryUploadedFile
    import sys
    from geo.models import Establishment
    from core.models import ObjectPhoto

    establishment = _resolve_establishment(establishment_id, is_active=True)

    if establishment.owner_id != request.auth.id:
        return 403, {"error": "Only owner can upload photos"}

    if ObjectPhoto.objects.filter(object_id=establishment.id).count() >= 10:
        return 400, {"error": "Maximum 10 photos per establishment"}

    if not image.content_type.startswith('image/') or not _is_valid_image_magic(image.file):
        return 400, {"error": "File must be an image"}

    if image.size > 15 * 1024 * 1024:
        return 400, {"error": "Image size must be less than 15MB"}

    try:
        img = Image.open(image.file)

        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        max_size = (1600, 1600)
        if img.width > max_size[0] or img.height > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        output = BytesIO()
        img_format = 'JPEG' if img.mode == 'RGB' else 'PNG'
        img.save(output, format=img_format, quality=85, optimize=True)
        output.seek(0)

        file_name = f"{establishment.id}_{order}.{img_format.lower()}"
        django_file = InMemoryUploadedFile(
            output, 'ImageField', file_name,
            f'image/{img_format.lower()}', sys.getsizeof(output), None
        )

        photo = ObjectPhoto(
            object_id=establishment.id,
            uploaded_by=request.auth,
            order=order,
            caption=caption
        )
        photo.image.save(file_name, django_file, save=True)

        logger.info(f"Photo uploaded for establishment {establishment.id}")

        return 201, EstablishmentPhotoResponse(
            id=photo.id,
            url=photo.image.url,
            order=photo.order,
            caption=photo.caption,
        )

    except Exception as e:
        logger.error(f"Error uploading establishment photo: {e}", exc_info=True)
        return 400, {"error": f"Failed to upload photo: {str(e)}"}


@router.delete("/establishments/{establishment_id}/photos/{photo_id}/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='directory:delete_photo', key=user_or_ip, rate='30/m', method='DELETE')
def delete_establishment_photo(request, establishment_id: str, photo_id: str):
    """Delete an establishment photo. Owner only."""
    from core.models import ObjectPhoto

    establishment = _resolve_establishment(establishment_id, is_active=True)

    if establishment.owner_id != request.auth.id:
        raise HttpError(403, "Only owner can delete photos")

    photo = get_object_or_404(ObjectPhoto, id=photo_id, object_id=establishment.id)
    photo.image.delete()
    photo.delete()

    return {"ok": True}


# ===== Establishment Logo =====

class LogoResponse(BaseModel):
    logo_url: str


def _delete_logo_files(establishment_id: str):
    """Remove any previously stored logo files for this establishment
    (both jpg/png variants) so a replace never leaves an orphan."""
    from django.core.files.storage import default_storage
    for ext in ('jpg', 'png'):
        path = f"establishment_logos/{establishment_id}.{ext}"
        if default_storage.exists(path):
            default_storage.delete(path)


@router.post("/establishments/{establishment_id}/logo/", auth=ProfileAuth(), response={200: LogoResponse, 400: dict, 403: dict})
@ratelimit(group='directory:upload_logo', key=user_or_ip, rate='10/m', method='POST')
def upload_establishment_logo(request, establishment_id: str, image: UploadedFile):
    """Upload / replace an establishment logo. Owner only. Stores a single
    optimized image (max 512px) and sets `logo_url`. Persists immediately so a
    logo survives even if the edit form isn't saved."""
    from PIL import Image
    from io import BytesIO
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    establishment = _resolve_establishment(establishment_id, is_active=True)

    if establishment.owner_id != request.auth.id:
        return 403, {"error": "Only owner can change the logo"}

    if not image.content_type.startswith('image/') or not _is_valid_image_magic(image.file):
        return 400, {"error": "File must be an image"}

    if image.size > 10 * 1024 * 1024:
        return 400, {"error": "Image size must be less than 10MB"}

    try:
        img = Image.open(image.file)
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        img.thumbnail((512, 512), Image.Resampling.LANCZOS)

        output = BytesIO()
        fmt = 'PNG' if img.mode == 'RGBA' else 'JPEG'
        if fmt == 'JPEG':
            img.save(output, format='JPEG', quality=88, optimize=True)
        else:
            img.save(output, format='PNG', optimize=True)
        output.seek(0)

        _delete_logo_files(establishment.id)
        ext = 'png' if fmt == 'PNG' else 'jpg'
        saved = default_storage.save(
            f"establishment_logos/{establishment.id}.{ext}",
            ContentFile(output.read()),
        )
        establishment.logo_url = default_storage.url(saved)
        establishment.save(update_fields=['logo_url'])

        logger.info(f"Logo uploaded for establishment {establishment.id}")
        return 200, LogoResponse(logo_url=establishment.logo_url)

    except Exception as e:
        logger.error(f"Error uploading establishment logo: {e}", exc_info=True)
        return 400, {"error": f"Failed to upload logo: {str(e)}"}


@router.delete("/establishments/{establishment_id}/logo/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='directory:delete_logo', key=user_or_ip, rate='30/m', method='DELETE')
def delete_establishment_logo(request, establishment_id: str):
    """Remove an establishment logo. Owner only."""
    establishment = _resolve_establishment(establishment_id, is_active=True)

    if establishment.owner_id != request.auth.id:
        raise HttpError(403, "Only owner can remove the logo")

    _delete_logo_files(establishment.id)
    establishment.logo_url = ""
    establishment.save(update_fields=['logo_url'])
    return {"ok": True}


# ===== Establishment Reviews =====

@router.get("/establishments/{establishment_id}/reviews/", auth=None, response=List[ReviewResponse])
@ratelimit(group='directory:reviews', key='ip', rate='120/m')
@paginate(PageNumberPagination)
def list_establishment_reviews(request, establishment_id: str):
    """List reviews for an establishment."""
    from geo.models import Establishment, EstablishmentReview
    _resolve_establishment(establishment_id)
    qs = EstablishmentReview.objects.filter(
        establishment_id=establishment_id
    ).select_related('author', 'author__instance').order_by('-created_at')
    return [_format_review(r) for r in qs]


@router.post("/establishments/{establishment_id}/reviews/", auth=ProfileAuth(), response={201: ReviewResponse})
@ratelimit(group='directory:create_review', key=user_or_ip, rate='10/m', method='POST')
def create_establishment_review(request, establishment_id: str, payload: ReviewInput):
    """Create a review. Requires WoT 3+ (or admin/parahub member)."""
    from geo.models import Establishment, EstablishmentReview
    from identity.models import Verification

    establishment = _resolve_establishment(establishment_id, is_active=True)
    profile = request.auth

    # WoT check
    wot_count = 0
    if not profile.account.is_superuser and not profile.is_foundation_member():
        wot_count = Verification.objects.filter(verified_profile=profile, is_active=True).count()
        if wot_count < 3:
            raise HttpError(403, "Requires WoT level 3+ to write reviews (or be admin/parahub member)")
    else:
        wot_count = Verification.objects.filter(verified_profile=profile, is_active=True).count()

    if EstablishmentReview.objects.filter(establishment=establishment, author=profile).exists():
        raise HttpError(409, "You have already reviewed this establishment")

    review = EstablishmentReview.objects.create(
        establishment=establishment,
        author=profile,
        rating=payload.rating,
        text=payload.text,
        wot_count_snapshot=wot_count,
    )
    return 201, _format_review(review, viewer=request.auth)


@router.put("/establishments/{establishment_id}/reviews/{review_id}/", auth=ProfileAuth(), response=ReviewResponse)
@ratelimit(group='directory:update_review', key=user_or_ip, rate='30/m', method='PUT')
def update_establishment_review(request, establishment_id: str, review_id: str, payload: ReviewInput):
    """Update own review."""
    from geo.models import EstablishmentReview

    review = get_object_or_404(EstablishmentReview, id=review_id, establishment_id=establishment_id)
    if review.author_id != request.auth.id:
        raise HttpError(403, "Not your review")

    review.rating = payload.rating
    review.text = payload.text
    review.save(update_fields=['rating', 'text', 'updated_at'])
    return _format_review(review, viewer=request.auth)


@router.delete("/establishments/{establishment_id}/reviews/{review_id}/", auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='directory:delete_review', key=user_or_ip, rate='10/m', method='DELETE')
def delete_establishment_review(request, establishment_id: str, review_id: str):
    """Delete own review (or establishment owner can delete any review)."""
    from geo.models import Establishment, EstablishmentReview

    review = get_object_or_404(EstablishmentReview, id=review_id, establishment_id=establishment_id)
    profile = request.auth

    establishment = _resolve_establishment(establishment_id)
    is_owner = establishment.owner_id == profile.id
    is_author = review.author_id == profile.id
    is_admin = profile.account.is_superuser

    if not (is_author or is_owner or is_admin):
        raise HttpError(403, "Not allowed")

    review.delete()
    return {"ok": True}


@router.put("/establishments/{establishment_id}/reviews/{review_id}/reply/", auth=ProfileAuth(), response=ReviewResponse)
@ratelimit(group='directory:reply_review', key=user_or_ip, rate='30/m', method='PUT')
def reply_to_establishment_review(request, establishment_id: str, review_id: str, payload: ReviewReplyInput):
    """Add/update establishment owner reply to a review."""
    from geo.models import Establishment, EstablishmentReview

    establishment = _resolve_establishment(establishment_id)
    review = get_object_or_404(EstablishmentReview, id=review_id, establishment_id=establishment_id)
    profile = request.auth

    is_owner = establishment.owner_id == profile.id
    is_admin = profile.account.is_superuser
    if not (is_owner or is_admin):
        raise HttpError(403, "Only the establishment owner can reply")

    review.owner_reply = payload.owner_reply
    review.save(update_fields=['owner_reply', 'updated_at'])
    return _format_review(review, viewer=request.auth)
