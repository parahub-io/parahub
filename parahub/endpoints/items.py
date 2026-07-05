"""
Item Management API endpoints for Parahub
Implements Phase 3.1: Core Marketplace Item APIs
"""

from ninja import Router, UploadedFile, Form
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.db import transaction, connection
from django.db.models import Q, F
from django.contrib.gis.geos import Point
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from decimal import Decimal
from datetime import datetime
import logging
import orjson

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.errors import LocalizedHttpError
from parahub.ratelimit import ratelimit, user_or_ip
from parahub.endpoints.ai_vision import _is_valid_image_magic
from market.models import Item
from market.visibility import visible_items_q, can_view_item, visible_items_sql
from identity.models import Profile
from core.models import ObjectPhoto
from taxonomy.models import Category, Tag
from currency.models import ExchangeRate
from geo.utils import detect_content_language, get_country_code_from_coords, get_country_code_from_request

logger = logging.getLogger(__name__)


def _truncate(text, max_len=200):
    """Truncate text for list responses, preserving full text on detail endpoints."""
    if not text or len(text) <= max_len:
        return text or ''
    return text[:max_len] + '…'


# Create item router
item_router = Router()


def _resolve_item(item_id: str, **kwargs):
    """Resolve item by ULID or slug."""
    try:
        return Item.objects.get(id=item_id, **kwargs)
    except Item.DoesNotExist:
        return get_object_or_404(Item, slug=item_id, **kwargs)

# Pydantic schemas for API request/response

class PricingOption(BaseModel):
    """Single pricing option for an item"""
    type: str = Field(..., pattern="^(sale|rent|free)$")
    amount: Optional[Decimal] = Field(None, ge=0, description="Required if type != 'free'")
    currency: Optional[str] = Field(None, pattern="^[A-Z]{3}$", description="ISO 4217 code (EUR, USD, etc)")
    unit: Optional[str] = Field(None, max_length=50, description="Pricing unit, e.g. 'kg', 'hour', 'day', 'pcs'")
    note: Optional[str] = Field(None, max_length=100, description="Optional note/description")
    converted_from: Optional[str] = Field(None, description="Original currency if converted")

    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v, info):
        if info.data.get('type') != 'free' and v is None:
            raise ValueError("amount is required when type is not 'free'")
        return v

class LocationInput(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)

    @field_validator('latitude', 'longitude')
    @classmethod
    def validate_coordinates(cls, v):
        if v is None:
            raise ValueError("Coordinates cannot be null")
        return v

class ItemSpecData(BaseModel):
    """Flexible spec data for additional item information"""
    # Common fields
    condition: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None

    # Service-specific
    duration_hours: Optional[float] = None

    # Rental-specific
    rental_period_days: Optional[int] = None
    deposit_sats: Optional[int] = None
    
    # Vehicle-specific
    year: Optional[int] = None
    mileage: Optional[int] = None
    
    # IoT Device-specific
    device_id: Optional[str] = None
    firmware_version: Optional[str] = None
    
    # Info Resource-specific
    url: Optional[str] = None
    access_type: Optional[str] = None
    
    # Video Content-specific
    duration_seconds: Optional[int] = None
    resolution: Optional[str] = None
    
    model_config = ConfigDict(extra='allow')

class ItemImageResponse(BaseModel):
    id: str  # ULID
    object_type: str = "itemimage"
    url: str
    order: int
    caption: str

    model_config = ConfigDict(from_attributes=True)


class ItemResponse(BaseModel):
    id: str  # ULID
    object_type: str = "item"
    slug: str = ''
    owner_id: str  # Profile ULID
    owner_account_id: str  # Account ULID for Matrix chat
    owner_hna: str
    owner_display_name: str = ''
    title: str
    description: str
    item_type: str  # Renamed from 'type' to avoid confusion with object_type
    spec_data: Dict[str, Any]
    location: Optional[Dict[str, float]] = None  # Fuzzed for privacy
    pricing_options: List[PricingOption] = []
    accepted_payment_methods: List[str] = []
    is_active: bool
    category_id: Optional[str] = None  # Category ULID
    category_name: Optional[str] = None
    category_path: Optional[List[Dict[str, str]]] = None  # Full path from root to category
    tags: List[str] = []
    images: List[ItemImageResponse] = []
    language: str = ''
    is_international: bool = False
    self_made: bool = False  # Producer (made/grew/prepared it), not a reseller — drives "made by hand" badge
    visibility: str = 'PUBLIC'  # PUBLIC | REGISTERED — drives the "registered-only" badge
    version: int
    created_at: datetime
    updated_at: datetime
    distance_meters: Optional[float] = None  # Distance from user location (when ordering by distance)
    # Act as establishment
    establishment_id: Optional[str] = None
    establishment_name: Optional[str] = None
    establishment_slug: Optional[str] = None
    establishment_logo_url: Optional[str] = None
    # Staff-only demo marker
    is_demo: bool = False
    # Demand indicator: count of opposite-type items in same category
    demand_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class ItemDetailResponse(ItemResponse):
    """Detailed view with additional information"""
    owner_reputation: Decimal
    owner_is_verified: bool
    owner_avatar_url: Optional[str] = None
    owner_created_at: Optional[datetime] = None  # Profile created_at for "member since"
    owner_verifications_count: int = 0  # WoT verifications received
    exact_location: Optional[Dict[str, float]] = None  # Only for deal participants

class ItemCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = Field("", max_length=5000)
    item_type: str = Field(..., pattern="^(CREDIT|DEBIT)$", description="CREDIT for offer, DEBIT for request")
    spec_data: Optional[ItemSpecData] = Field(default_factory=dict)
    location: Optional[LocationInput] = None
    pricing_options: List[PricingOption] = Field(default_factory=list, description="Array of pricing options")
    accepted_payment_methods: Optional[List[str]] = Field(default_factory=list)
    category_id: Optional[str] = Field(None, description="Category ULID (26 chars)")
    tag_names: Optional[List[str]] = []
    is_international: bool = Field(False, description="Visible to all users regardless of language filter")
    self_made: bool = Field(False, description="Producer made/grew/prepared it (not a reseller). Applies to offers (CREDIT) only.")
    visibility: str = Field('PUBLIC', pattern="^(PUBLIC|REGISTERED)$", description="Audience scope: PUBLIC (anyone, default) or REGISTERED (signed-in users only).")
    ai_analysis_log_id: Optional[int] = Field(None, description="AI analysis log ID for accuracy tracking")
    establishment_id: Optional[str] = Field(None, description="Post on behalf of this establishment (ULID)")

class ItemUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    spec_data: Optional[ItemSpecData] = None
    location: Optional[LocationInput] = None
    pricing_options: Optional[List[PricingOption]] = None
    category_id: Optional[str] = Field(None, description="Category ULID (26 chars)")
    tag_names: Optional[List[str]] = None
    is_active: Optional[bool] = None
    self_made: Optional[bool] = Field(None, description="Producer made/grew/prepared it (not a reseller). Applies to offers (CREDIT) only.")
    visibility: Optional[str] = Field(None, pattern="^(PUBLIC|REGISTERED)$", description="Audience scope: PUBLIC (anyone) or REGISTERED (signed-in users only).")
    establishment_id: Optional[str] = Field(None, description="Post on behalf of this establishment (ULID). Empty string '' to detach (post personally).")
    expected_version: Optional[int] = Field(None, description="Version for optimistic locking")


def serialize_pricing_options(pricing_options: List[Dict], target_currency: Optional[str] = None) -> List[Dict]:
    """Serialize raw pricing_options JSONB into response dicts, converting to
    target_currency when requested. The ONLY pricing serialization — both the
    ORM and the raw-SQL item paths go through here."""
    result = []
    for opt in pricing_options or []:
        po = {
            'type': opt.get('type'),
            'amount': opt.get('amount'),
            'currency': opt.get('currency'),
            'unit': opt.get('unit') or opt.get('period'),
            'note': opt.get('note'),
            'converted_from': None,
        }
        if target_currency and po['currency'] and po['amount'] and po['currency'] != target_currency:
            try:
                converted = ExchangeRate.convert(
                    Decimal(str(po['amount'])), po['currency'], target_currency
                )
                # str keeps orjson serializable; pydantic coerces it back to Decimal
                po['amount'] = str(converted)
                po['converted_from'] = po['currency']
                po['currency'] = target_currency
            except Exception as e:
                logger.warning(f"Currency conversion failed ({po['converted_from'] or po['currency']} -> {target_currency}): {e}")
                po['converted_from'] = None  # keep original values if conversion fails
        result.append(po)
    return result


def batch_demand_maps(category_ids, request):
    """Demand aggregates for a set of categories, viewer-visibility-aware.

    Returns (demand_total, demand_by_owner):
      demand_total[(category_id, type)]            -> active visible count across all owners
      demand_by_owner[(category_id, type, owner)]  -> active visible count for that owner

    Per-item demand = total for the OPPOSITE type − count owned by the item's
    own owner (a user's own request must not inflate demand on their own offer).
    Single implementation for both list paths so the raw path cannot drift from
    the ORM path (it used to skip the visibility filter).
    """
    demand_total = {}
    demand_by_owner = {}
    category_ids = [c for c in category_ids if c]
    if not category_ids:
        return demand_total, demand_by_owner
    from django.db.models import Count
    counts = (
        Item.objects.filter(category_id__in=category_ids, is_active=True)
        .filter(visible_items_q(request))
        .values('category_id', 'type', 'owner_id')
        .annotate(count=Count('id'))
    )
    for row in counts:
        key = (row['category_id'], row['type'])
        demand_total[key] = demand_total.get(key, 0) + row['count']
        demand_by_owner[(row['category_id'], row['type'], row['owner_id'])] = row['count']
    return demand_total, demand_by_owner


def demand_count_for(item_type, category_id, owner_id, demand_total, demand_by_owner):
    """Demand for one item from batch_demand_maps aggregates: opposite-type
    active items in the same category, excluding the item's own owner."""
    if not category_id:
        return None
    opposite = 'DEBIT' if item_type == 'CREDIT' else 'CREDIT'
    return (demand_total.get((category_id, opposite), 0)
            - demand_by_owner.get((category_id, opposite, owner_id), 0)) or None


def assemble_item_dict(
    *,
    item_id, slug, title, description, item_type,
    spec_data, pricing_options, accepted_payment_methods,
    is_active, language, is_international, self_made, visibility,
    lat, lon,
    category_id, category_name, category_path,
    tags, images,
    version, created_at, updated_at, attributes,
    owner_id, owner_account_id, owner_hna, owner_display_name, owner_name_public,
    establishment_id, establishment_name, establishment_slug, establishment_logo_url,
    viewer=None, target_currency=None, demand_count=None, distance_meters=None,
) -> dict:
    """Single source of truth for the public Item JSON shape.

    Every serialization path — build_item_response (ORM), get_item (detail)
    and _list_items_raw (CQRS fast path) — assembles through this function so
    the field set, defaults, privacy gating, location fuzzing and pricing
    conversion cannot drift between them. Guarded by market.tests_item_parity.

    `description` arrives already truncated where the endpoint truncates
    (list paths); `images` is a list of ItemImageResponse-shaped dicts.
    """
    location = None
    if lat is not None and lon is not None:
        grid = 100 / 111000  # ~100m privacy grid, keep in sync with accuracy_meters
        location = {
            'latitude': round(lat / grid) * grid,
            'longitude': round(lon / grid) * grid,
            'fuzzed': True,
            'accuracy_meters': 100,
        }
    attributes = attributes or {}
    return {
        'id': item_id,
        'object_type': 'item',
        'slug': slug or '',
        'owner_id': owner_id,
        'owner_account_id': owner_account_id,
        'owner_hna': owner_hna,
        'owner_display_name': (owner_display_name or '') if Profile.name_visible(owner_name_public, owner_id, viewer) else '',
        'title': title,
        'description': description or '',
        'item_type': item_type,
        'spec_data': spec_data or {},
        'location': location,
        'pricing_options': serialize_pricing_options(pricing_options, target_currency),
        'accepted_payment_methods': accepted_payment_methods or [],
        'is_active': is_active,
        'language': language or '',
        'is_international': is_international,
        'self_made': self_made,
        'visibility': visibility or 'PUBLIC',
        'category_id': category_id,
        'category_name': category_name,
        'category_path': category_path,
        'tags': tags,
        'images': images,
        'version': version,
        'created_at': created_at,
        'updated_at': updated_at,
        'distance_meters': distance_meters,
        'establishment_id': establishment_id or None,
        'establishment_name': establishment_name,
        'establishment_slug': establishment_slug,
        'establishment_logo_url': establishment_logo_url,
        'is_demo': bool(attributes.get('__demo_seed') or attributes.get('demo')),
        'demand_count': demand_count,
    }


def _model_assemble_kwargs(item: Item, request, target_currency=None, demand_count=None, photos_map=None):
    """Extract assemble_item_dict kwargs from an ORM Item instance."""
    if photos_map is not None:
        photo_list = photos_map.get(item.id, [])
    else:
        photo_list = ObjectPhoto.objects.filter(object_id=item.id).order_by('order', 'created_at')
    images = [
        {'id': p.id, 'object_type': p.type_name, 'url': p.image.url,
         'order': p.order, 'caption': p.caption or ''}
        for p in photo_list
    ]
    return dict(
        item_id=item.id,
        slug=item.slug,
        title=item.title,
        description=item.description,
        item_type=item.type,
        spec_data=item.spec_data,
        pricing_options=item.pricing_options,
        accepted_payment_methods=item.accepted_payment_methods,
        is_active=item.is_active,
        language=item.language,
        is_international=item.is_international,
        self_made=item.self_made,
        visibility=item.visibility,
        lat=item.location.y if item.location else None,
        lon=item.location.x if item.location else None,
        category_id=item.category.id if item.category else None,
        category_name=item.category.name if item.category else None,
        category_path=item.category.get_path() if item.category else None,
        tags=[tag.name for tag in item.tags.all()],
        images=images,
        version=item.version,
        created_at=item.created_at,
        updated_at=item.updated_at,
        attributes=item.attributes,
        owner_id=item.owner.id,
        owner_account_id=item.owner.account.id,
        owner_hna=item.owner.hna,
        owner_display_name=item.owner.display_name,
        owner_name_public=item.owner.name_public,
        establishment_id=item.establishment_id,
        establishment_name=item.establishment.name if item.establishment else None,
        establishment_slug=item.establishment.slug if item.establishment else None,
        establishment_logo_url=item.establishment.logo_url if item.establishment else None,
        viewer=getattr(request, 'auth_profile', None),
        target_currency=target_currency,
        demand_count=demand_count,
    )


def build_item_response(item: Item, request=None, target_currency: str = None, include_distance: bool = False, demand_count: int = None, photos_map: dict = None) -> ItemResponse:
    """Build ItemResponse from an Item instance via the shared assembly core.

    Args:
        item: Item model instance
        request: HTTP request object (viewer for privacy gating)
        target_currency: Optional target currency for price conversion
        include_distance: Whether to include distance_meters from annotation
        photos_map: Pre-fetched {object_id: [ObjectPhoto, ...]} to avoid N+1
    """
    kwargs = _model_assemble_kwargs(item, request, target_currency, demand_count, photos_map)
    kwargs['description'] = _truncate(kwargs['description'], 200)
    if include_distance and hasattr(item, 'distance_meters'):
        kwargs['distance_meters'] = float(item.distance_meters.m) if item.distance_meters else None
    return ItemResponse(**assemble_item_dict(**kwargs))


def _list_items_raw(request, item_type, pricing_type, category_id_resolved,
                    is_active, min_price, max_price, include_barter,
                    owner_id, target_currency, language, ordering,
                    page, page_size, is_staff_or_test, self_made=None):
    """Raw SQL fast path for items list — bypasses ORM/Pydantic overhead."""
    conditions = ["TRUE"]
    params = []

    if self_made:
        conditions.append("i.self_made = TRUE")

    # Hide test/bot items for non-staff
    if not is_staff_or_test:
        conditions.append("a.is_test = FALSE AND a.is_bot = FALSE")

    # Visibility: anonymous viewers see PUBLIC only; authed users see all tiers.
    vis_pred, vis_params = visible_items_sql(request)
    conditions.append(vis_pred)
    params.extend(vis_params)

    if item_type:
        conditions.append("i.type = %s")
        params.append(item_type)
    if pricing_type:
        conditions.append("i.pricing_options @> %s::jsonb")
        params.append(orjson.dumps([{'type': pricing_type}]).decode())
    if category_id_resolved:
        # category_id_resolved is already a list of IDs (parent + descendants)
        placeholders = ','.join(['%s'] * len(category_id_resolved))
        conditions.append(f"i.category_id IN ({placeholders})")
        params.extend(category_id_resolved)
    if is_active is not None:
        conditions.append("i.is_active = %s")
        params.append(is_active)
    if owner_id:
        conditions.append("i.owner_id = %s")
        params.append(owner_id)
    if language:
        viewer_country = (
            getattr(getattr(request, 'auth_profile', None), 'country_code', '') or
            get_country_code_from_request(request)
        )
        if viewer_country:
            conditions.append(
                "(i.is_international = TRUE OR i.language = '' "
                "OR (i.language = %s AND i.country_code = '') "
                "OR i.country_code = %s)"
            )
            params.extend([language, viewer_country])
        else:
            conditions.append(
                "(i.language = %s OR i.language = '' OR i.is_international = TRUE)"
            )
            params.append(language)
    if min_price is not None or max_price is not None:
        if min_price is not None:
            conditions.append("(i.pricing_options->0->>'amount')::numeric >= %s")
            params.append(min_price)
        if max_price is not None:
            conditions.append("(i.pricing_options->0->>'amount')::numeric <= %s")
            params.append(max_price)
        if include_barter:
            # Rewrite last conditions to also include empty pricing_options
            # Remove the conditions we just added and combine with OR
            price_conds = []
            if min_price is not None:
                price_conds.append("(i.pricing_options->0->>'amount')::numeric >= %s")
            if max_price is not None:
                price_conds.append("(i.pricing_options->0->>'amount')::numeric <= %s")
            # Pop the price conditions we already added
            for _ in price_conds:
                conditions.pop()
                params.pop()
            combined = " AND ".join(price_conds)
            conditions.append(f"(({combined}) OR i.pricing_options = '[]'::jsonb)")
            if min_price is not None:
                params.append(min_price)
            if max_price is not None:
                params.append(max_price)

    where = " AND ".join(conditions)

    # Ordering
    if ordering == 'min_price':
        order_clause = "(i.pricing_options->0->>'amount')::numeric ASC NULLS LAST"
    elif ordering == '-min_price':
        order_clause = "(i.pricing_options->0->>'amount')::numeric DESC NULLS LAST"
    elif ordering == 'created_at':
        order_clause = "i.created_at ASC"
    else:
        order_clause = "i.created_at DESC"

    offset = (page - 1) * page_size

    base_from = (
        "FROM market_item i "
        "JOIN identity_profile p ON i.owner_id = p.id "
        "JOIN identity_account a ON p.account_id = a.id "
        "JOIN core_instance inst ON p.instance_id = inst.id "
        "LEFT JOIN taxonomy_category c ON i.category_id = c.id "
        "LEFT JOIN taxonomy_category c2 ON c.parent_id = c2.id "
        "LEFT JOIN taxonomy_category c3 ON c2.parent_id = c3.id "
        "LEFT JOIN taxonomy_category c4 ON c3.parent_id = c4.id "
        "LEFT JOIN taxonomy_category c5 ON c4.parent_id = c5.id "
        "LEFT JOIN geo_establishment est ON i.establishment_id = est.id"
    )

    with connection.cursor() as cur:
        # Count
        cur.execute(f"SELECT COUNT(*) {base_from} WHERE {where}", params)
        total = cur.fetchone()[0]

        # Main query
        cur.execute(f"""
            SELECT
                i.id, i.slug, i.title,
                CASE WHEN LENGTH(i.description) > 200
                     THEN LEFT(i.description, 200) || '…'
                     ELSE i.description END AS description,
                i.type,
                i.spec_data, i.pricing_options, i.accepted_payment_methods,
                i.is_active, i.language, i.is_international,
                ST_Y(i.location::geometry), ST_X(i.location::geometry),
                i.version, i.created_at, i.updated_at, i.attributes,
                i.category_id, i.establishment_id,
                -- owner
                p.id, p.local_name, p.display_name, p.name_public, inst.domain, a.id,
                -- category
                c.name, c.slug,
                c2.id, c2.name, c2.slug,
                c3.id, c3.name, c3.slug,
                c4.id, c4.name, c4.slug,
                c5.id, c5.name, c5.slug,
                -- establishment
                est.name, est.slug, est.logo_url,
                i.self_made, i.visibility
            {base_from}
            WHERE {where}
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        rows = cur.fetchall()

    if not rows:
        body = orjson.dumps({
            'items': [], 'count': total,
            'pages': (total + page_size - 1) // page_size,
            'page': page, 'page_size': page_size
        })
        return HttpResponse(body, content_type='application/json')

    item_ids = [r[0] for r in rows]

    # Batch-fetch tags
    tags_map = {}
    with connection.cursor() as cur:
        placeholders = ','.join(['%s'] * len(item_ids))
        cur.execute(f"""
            SELECT mt.item_id, t.name
            FROM market_item_tags mt
            JOIN taxonomy_tag t ON mt.tag_id = t.id
            WHERE mt.item_id IN ({placeholders})
            ORDER BY t.name
        """, item_ids)
        for item_id, tag_name in cur.fetchall():
            tags_map.setdefault(item_id, []).append(tag_name)

    # Batch-fetch photos
    photos_map = {}
    with connection.cursor() as cur:
        cur.execute(f"""
            SELECT object_id, id, image, "order", caption
            FROM core_objectphoto
            WHERE object_id IN ({placeholders})
            ORDER BY "order", created_at
        """, item_ids)
        for obj_id, photo_id, image_path, order, caption in cur.fetchall():
            photos_map.setdefault(obj_id, []).append({
                'id': photo_id, 'object_type': 'objectphoto',
                'url': f'/media/{image_path}',
                'order': order, 'caption': caption or '',
            })

    # Batch demand counts — one shared, visibility-aware implementation for
    # both list paths (this raw path used to skip the visibility filter).
    demand_total, demand_by_owner = batch_demand_maps({r[17] for r in rows}, request)

    # Build response through the shared assembly core — same shape, privacy
    # gating and pricing conversion as the ORM path (orjson serializes the
    # datetime objects the cursor returns).
    viewer = getattr(request, 'auth_profile', None)
    items = []
    for r in rows:
        (item_id, slug, title, desc, itype,
         spec_data, pricing_opts_raw, payment_methods,
         active, lang, international,
         lat, lon,
         version, created_at, updated_at, attrs,
         cat_id, est_id,
         owner_id, local_name, display_name, name_public, inst_domain, account_id,
         cat_name, cat_slug,
         c2_id, c2_name, c2_slug,
         c3_id, c3_name, c3_slug,
         c4_id, c4_name, c4_slug,
         c5_id, c5_name, c5_slug,
         est_name, est_slug, est_logo, self_made, visibility) = r

        # Parse JSONB fields (cursor returns str for jsonb)
        spec = orjson.loads(spec_data) if isinstance(spec_data, str) else (spec_data or {})
        pricing_opts = orjson.loads(pricing_opts_raw) if isinstance(pricing_opts_raw, str) else (pricing_opts_raw or [])
        pay_methods = orjson.loads(payment_methods) if isinstance(payment_methods, str) else (payment_methods or [])
        attrs_parsed = orjson.loads(attrs) if isinstance(attrs, str) else (attrs or {})

        # Category path (walk up to 5 levels, root first — same shape as Category.get_path)
        cat_path = None
        if cat_id:
            cat_path = [
                {'id': cid, 'name': cname, 'slug': cslug}
                for cid, cname, cslug in [
                    (c5_id, c5_name, c5_slug), (c4_id, c4_name, c4_slug),
                    (c3_id, c3_name, c3_slug), (c2_id, c2_name, c2_slug),
                    (cat_id, cat_name, cat_slug),
                ] if cid
            ]

        items.append(assemble_item_dict(
            item_id=item_id, slug=slug, title=title, description=desc,
            item_type=itype, spec_data=spec, pricing_options=pricing_opts,
            accepted_payment_methods=pay_methods, is_active=active,
            language=lang, is_international=international,
            self_made=self_made, visibility=visibility,
            lat=lat, lon=lon,
            category_id=cat_id, category_name=cat_name, category_path=cat_path,
            tags=tags_map.get(item_id, []),
            images=photos_map.get(item_id, []),
            version=version, created_at=created_at, updated_at=updated_at,
            attributes=attrs_parsed,
            owner_id=owner_id, owner_account_id=account_id,
            owner_hna=f'{local_name}@{inst_domain}',
            owner_display_name=display_name, owner_name_public=name_public,
            establishment_id=est_id, establishment_name=est_name,
            establishment_slug=est_slug, establishment_logo_url=est_logo,
            viewer=viewer, target_currency=target_currency,
            demand_count=demand_count_for(itype, cat_id, owner_id, demand_total, demand_by_owner),
        ))

    body = orjson.dumps({
        'items': items, 'count': total,
        'pages': (total + page_size - 1) // page_size,
        'page': page, 'page_size': page_size,
    })
    return HttpResponse(body, content_type='application/json')


@item_router.get("/", auth=OptionalProfileAuth())
@ratelimit(group='items:list', key=user_or_ip, rate='30/m')
def list_items(request,
               item_type: Optional[str] = None,
               pricing_type: Optional[str] = None,
               category: Optional[str] = None,
               category_id: Optional[str] = None,
               is_active: Optional[bool] = None,
               min_price: Optional[int] = None,
               max_price: Optional[int] = None,
               include_barter: Optional[bool] = None,
               owner_id: Optional[str] = None,
               target_currency: Optional[str] = None,
               q: Optional[str] = None,
               ordering: Optional[str] = None,
               lat: Optional[float] = None,
               lng: Optional[float] = None,
               match_type: Optional[str] = None,
               language: Optional[str] = None,
               self_made: Optional[bool] = None,
               page: int = 1,
               page_size: int = 20):
    """
    List items with filtering options

    Returns items with fuzzed locations for privacy.
    Prices can be converted to target_currency if provided.
    pricing_type filters by pricing option type: 'sale', 'rent', or 'free'
    ordering: Sort order (e.g., '-created_at', 'created_at', 'min_price', '-min_price', 'distance')
    lat/lng: User coordinates for distance sorting (required when ordering='distance')
    match_type: Filter items matching user's items ('offer_matches' | 'want_matches')
        - 'offer_matches': show DEBIT items matching categories of my CREDIT items
        - 'want_matches': show CREDIT items matching categories of my DEBIT items
    """
    # Hidden items are private. Force active-only unless the caller is listing
    # their OWN items (My Items sends no is_active for "All", False for hidden).
    # Don't trust the client's is_active value — an explicit is_active=false
    # from a non-owner must not expose other people's hidden listings.
    if is_active is not True:
        viewer = getattr(request, 'auth_profile', None)
        is_owner_self = bool(owner_id) and viewer is not None and owner_id == viewer.id
        if not is_owner_self:
            is_active = True

    # --- Fast path: raw SQL for simple filters ---
    use_orm = bool(match_type) or bool(q) or (ordering == 'distance')
    if not use_orm:
        try:
            # Resolve category slug/id to list of descendant IDs
            category_id_resolved = None
            if category or category_id:
                try:
                    if category:
                        cat = Category.objects.get(slug=category)
                    else:
                        cat = Category.objects.get(id=category_id)
                    # Collect all descendant IDs via raw SQL (avoids ORM traversal)
                    with connection.cursor() as cur:
                        cur.execute("""
                            WITH RECURSIVE tree AS (
                                SELECT id FROM taxonomy_category WHERE id = %s
                                UNION ALL
                                SELECT c.id FROM taxonomy_category c
                                JOIN tree t ON c.parent_id = t.id
                            )
                            SELECT id FROM tree
                        """, [cat.id])
                        category_id_resolved = [r[0] for r in cur.fetchall()]
                except Category.DoesNotExist:
                    # Return empty
                    body = orjson.dumps({
                        'items': [], 'count': 0, 'pages': 0,
                        'page': page, 'page_size': page_size
                    })
                    return HttpResponse(body, content_type='application/json')

            user = getattr(request, 'user', None)
            is_staff_or_test = False
            if user and getattr(user, 'is_authenticated', False):
                is_staff_or_test = getattr(user, 'is_staff', False) or getattr(user, 'is_test', False)

            return _list_items_raw(
                request, item_type, pricing_type, category_id_resolved,
                is_active, min_price, max_price, include_barter,
                owner_id, target_currency, language, ordering,
                page, page_size, is_staff_or_test, self_made=self_made,
            )
        except Exception:
            logger.exception("Raw SQL items list failed, falling back to ORM")

    # --- ORM path: complex filters (match_type, search, distance) ---
    try:
        queryset = Item.objects.all()

        # Hide items from test/bot accounts for non-staff/non-test users
        user = getattr(request, 'user', None)
        if user and getattr(user, 'is_authenticated', False):
            if not getattr(user, 'is_staff', False) and not getattr(user, 'is_test', False):
                queryset = queryset.exclude(owner__account__is_test=True).exclude(owner__account__is_bot=True)
        else:
            queryset = queryset.exclude(owner__account__is_test=True).exclude(owner__account__is_bot=True)

        # Visibility: anonymous viewers see PUBLIC only; authed users see all tiers.
        queryset = queryset.filter(visible_items_q(request))

        # Match type filter - show items matching user's opposite type items
        # "offer_matches": show DEBIT items (requests) matching my CREDIT items (offers)
        # "want_matches": show CREDIT items (offers) matching my DEBIT items (requests)
        if match_type in ['offer_matches', 'want_matches']:
            # Get current user's profile
            if not hasattr(request, 'auth_profile') or not request.auth_profile:
                # No auth - return empty queryset
                queryset = queryset.none()
            else:
                current_profile = request.auth_profile

                # Get user's active items of the opposite type
                if match_type == 'offer_matches':
                    # Get categories from my CREDIT items (offers)
                    my_item_type = 'CREDIT'
                    target_item_type = 'DEBIT'
                elif match_type == 'want_matches':
                    # Get categories from my DEBIT items (requests)
                    my_item_type = 'DEBIT'
                    target_item_type = 'CREDIT'

                # Get category IDs from user's active items
                my_categories = Item.objects.filter(
                    owner=current_profile,
                    type=my_item_type,
                    is_active=True,
                    category__isnull=False
                ).values_list('category_id', flat=True).distinct()

                my_category_ids = list(my_categories)

                if my_category_ids:
                    # Filter: opposite type items with matching categories, exclude my own items
                    queryset = queryset.filter(
                        type=target_item_type,
                        category_id__in=my_category_ids
                    ).exclude(owner=current_profile)
                else:
                    # User has no items of the required type - return empty
                    queryset = queryset.none()

        # Basic filters
        if item_type:
            queryset = queryset.filter(type=item_type)

        # Pricing type filter - filters items that have at least one pricing option of specified type
        if pricing_type:
            # Filter items where pricing_options JSON array contains at least one option with matching type
            queryset = queryset.filter(pricing_options__contains=[{'type': pricing_type}])

        # Category filter
        # - 'category' param: slug only (for frontend/URL filtering)
        # - 'category_id' param: ULID (for API/backend integrations)
        # Both include items from selected category AND all its subcategories
        selected_category = None

        if category:
            # Frontend filter: expects slug
            try:
                selected_category = Category.objects.get(slug=category)
            except Category.DoesNotExist:
                logger.warning(f"Category slug not found: {category}")
                queryset = queryset.none()
        elif category_id:
            # Backend filter: expects ULID (26 chars)
            try:
                selected_category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                logger.warning(f"Category ID not found: {category_id}")
                queryset = queryset.none()

        if selected_category:
            # Get all descendant categories (children, grandchildren, etc.)
            # Use iterative breadth-first traversal to collect all subcategory IDs
            category_ids = [selected_category.id]
            categories_to_process = [selected_category]

            while categories_to_process:
                current_cat = categories_to_process.pop(0)
                children = list(current_cat.children.all())
                for child in children:
                    category_ids.append(child.id)
                    categories_to_process.append(child)

            queryset = queryset.filter(category__id__in=category_ids)

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        if owner_id:
            queryset = queryset.filter(owner__id=owner_id)
        if self_made:
            queryset = queryset.filter(self_made=True)

        # Language filter: show items in requested language + untagged (legacy) + international
        # Physical items in viewer's country are shown regardless of language.
        if language:
            # Prefer saved profile country (authenticated users); fallback to GeoIP
            viewer_country = (
                getattr(getattr(request, 'auth_profile', None), 'country_code', '') or
                get_country_code_from_request(request)
            )
            if viewer_country:
                queryset = queryset.filter(
                    Q(is_international=True) |
                    Q(language='') |
                    Q(language=language, country_code='') |
                    Q(country_code=viewer_country)
                )
            else:
                queryset = queryset.filter(
                    Q(language=language) | Q(language='') | Q(is_international=True)
                )

        # Search filter - search in title, description, and tags
        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q) |
                Q(tags__name__icontains=q)
            ).distinct()

        # Price range filters / min_price ordering need the SAME numeric cast
        # as the raw path: pricing_options[0].amount is stored as a JSON
        # string, so a plain jsonb key comparison (string vs number) never
        # matches and jsonb ordering is lexicographic ('9' > '10').
        if (min_price is not None or max_price is not None
                or ordering in ('min_price', '-min_price')):
            from django.db.models.expressions import RawSQL
            queryset = queryset.annotate(
                _first_amount=RawSQL("(pricing_options->0->>'amount')::numeric", []))
        if min_price is not None or max_price is not None:
            price_q = Q()
            if min_price is not None:
                price_q &= Q(_first_amount__gte=min_price)
            if max_price is not None:
                price_q &= Q(_first_amount__lte=max_price)
            if include_barter:
                # Also include items with no pricing (barter-only)
                price_q = price_q | Q(pricing_options=[])
            queryset = queryset.filter(price_q)

        # Optimize query with related data
        queryset = queryset.select_related(
            'owner', 'owner__account', 'owner__instance',
            'category', 'category__parent', 'category__parent__parent',
            'category__parent__parent__parent', 'category__parent__parent__parent__parent',
            'establishment',
        ).prefetch_related(
            'tags',
        )

        # Apply ordering
        if ordering == 'distance' and lat is not None and lng is not None:
            # Distance sorting requires GIS distance annotation
            from django.contrib.gis.db.models.functions import Distance
            from django.contrib.gis.geos import Point

            user_location = Point(lng, lat, srid=4326)
            # Filter items that have location (exclude NULL locations)
            queryset = queryset.filter(location__isnull=False).annotate(
                distance_meters=Distance('location', user_location)
            ).order_by('distance_meters')
        elif ordering == 'min_price':
            # Numeric sort on first pricing option (same NULLS LAST as raw path)
            queryset = queryset.order_by(F('_first_amount').asc(nulls_last=True))
        elif ordering == '-min_price':
            queryset = queryset.order_by(F('_first_amount').desc(nulls_last=True))
        elif ordering == 'created_at':
            # Oldest first
            queryset = queryset.order_by('created_at')
        else:
            # Default: newest first
            queryset = queryset.order_by('-created_at')

        # Manual pagination
        total_count = queryset.count()

        # Calculate pagination
        start = (page - 1) * page_size
        end = start + page_size

        # Get paginated items
        paginated_items = list(queryset[start:end])

        # Batch demand counts — shared, visibility-aware implementation (same as raw path)
        demand_total, demand_by_owner = batch_demand_maps(
            {item.category_id for item in paginated_items}, request)

        # Batch-fetch photos for all items (eliminates N+1)
        item_ids = [item.id for item in paginated_items]
        photos_map = {iid: [] for iid in item_ids}
        if item_ids:
            for photo in ObjectPhoto.objects.filter(object_id__in=item_ids).order_by('order', 'created_at'):
                photos_map[photo.object_id].append(photo)

        # Build response for each item
        # Include distance when ordering by distance
        include_distance = (ordering == 'distance' and lat is not None and lng is not None)
        items = []
        for item in paginated_items:
            dc = demand_count_for(item.type, item.category_id, item.owner_id, demand_total, demand_by_owner)
            items.append(build_item_response(item, request, target_currency, include_distance, demand_count=dc, photos_map=photos_map))

        # Return paginated response
        return {
            "items": items,
            "count": total_count,
            "pages": (total_count + page_size - 1) // page_size,  # Ceiling division
            "page": page,
            "page_size": page_size
        }

    except Exception as e:
        logger.error(f"Error listing items: {e}", exc_info=True)
        return {
            "items": [],
            "count": 0,
            "pages": 0,
            "page": page,
            "page_size": page_size
        }


@item_router.post("/", response={201: ItemResponse, 400: dict, 404: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='items:create', key=user_or_ip, rate='10/m', method='POST')
def create_item(request, data: ItemCreateRequest):
    """
    Create a new marketplace item

    Requires authentication. The authenticated user becomes the owner.
    """
    try:
        owner_profile = request.auth_profile

        # Validate establishment if posting on behalf
        establishment = None
        if data.establishment_id:
            from geo.permissions import get_establishment_for_action, POSTING_ROLES
            establishment = get_establishment_for_action(data.establishment_id, owner_profile, POSTING_ROLES)

        with transaction.atomic():
            # Convert pricing_options to dict for JSONField
            # Convert Decimal to float for JSON serialization
            pricing_opts_data = []
            for opt in data.pricing_options:
                opt_dict = opt.dict(exclude_none=True)
                if 'amount' in opt_dict and opt_dict['amount'] is not None:
                    opt_dict['amount'] = float(opt_dict['amount'])
                pricing_opts_data.append(opt_dict)

            # Handle category
            category = None
            if data.category_id:
                try:
                    category = Category.objects.get(id=data.category_id)
                    # Validate that category is a leaf node (no children)
                    if not category.is_leaf:
                        logger.warning(f"Non-leaf category rejected: {data.category_id}")
                        return 400, {"error": "Please select a specific category. Parent categories cannot be used for items."}
                except Category.DoesNotExist:
                    logger.warning(f"Category not found: {data.category_id}")
                    return 404, {"error": f"Category {data.category_id} not found"}

            # Auto-detect content language and country
            detected_lang = detect_content_language(
                data.title, data.description or '',
                fallback=owner_profile.preferred_language or '',
            )
            detected_country = get_country_code_from_coords(
                data.location.latitude, data.location.longitude
            ) if data.location else ''

            # Create item
            item = Item(
                owner=owner_profile,
                title=data.title,
                description=data.description,
                type=data.item_type,
                spec_data=data.spec_data.dict() if data.spec_data else {},
                pricing_options=pricing_opts_data,
                accepted_payment_methods=data.accepted_payment_methods if data.accepted_payment_methods else [],
                category=category,
                language=detected_lang,
                country_code=detected_country,
                is_international=data.is_international,
                # self_made is meaningful only for offers (you can't "make" a request)
                self_made=bool(data.self_made and data.item_type == 'CREDIT'),
                visibility=data.visibility,
                establishment=establishment,
            )

            # Handle location
            if data.location:
                item.location = Point(data.location.longitude, data.location.latitude)

            item.save()

            # Handle tags
            if data.tag_names:
                for tag_name in data.tag_names:
                    tag, _ = Tag.objects.get_or_create(name=tag_name.lower())
                    item.tags.add(tag)

            # Update AI analysis log if provided (for accuracy tracking)
            if data.ai_analysis_log_id:
                try:
                    from parahub.models import AIAnalysisLog

                    log = AIAnalysisLog.objects.get(id=data.ai_analysis_log_id, profile=owner_profile)

                    # Track accuracy: did user accept AI suggestions?
                    log.final_item = item
                    log.user_accepted_category = (log.suggested_category_id == item.category_id) if log.suggested_category_id and item.category_id else None
                    log.user_accepted_title = (log.suggested_title.strip() == item.title.strip()) if log.suggested_title else None

                    # Check price acceptance (compare first pricing option)
                    if log.suggested_price and pricing_opts_data:
                        suggested_amount = log.suggested_price.get('amount')
                        actual_amount = pricing_opts_data[0].get('amount')
                        log.user_accepted_price = (suggested_amount == actual_amount) if suggested_amount and actual_amount else None

                    log.save()
                    logger.info(f"Updated AI log {log.id} with final item {item.id}")
                except AIAnalysisLog.DoesNotExist:
                    logger.warning(f"AI analysis log {data.ai_analysis_log_id} not found")
                except Exception as e:
                    logger.error(f"Error updating AI log: {e}")

        logger.info(f"Item created: {item.id} (type={item.type_name}) by {owner_profile.id}")
        return 201, build_item_response(item, request)

    except ValidationError as e:
        logger.warning(f"Item creation validation error: {e}")
        return 400, {"error": "Invalid item data", "details": str(e)}
    except Exception as e:
        logger.error(f"Error creating item: {e}", exc_info=True)
        return 500, {"error": "Failed to create item", "details": str(e)}


@item_router.get("/{id}/", response={200: ItemDetailResponse, 404: dict}, auth=OptionalProfileAuth())
@ratelimit(group='items:detail', key='ip', rate='60/m')
def get_item(request, id: str, target_currency: Optional[str] = None):
    """
    Get detailed item information by ULID or slug.

    Returns fuzzed location for public access.
    Exact location only available to deal participants.
    Prices can be converted to target_currency if provided.

    Hidden (is_active=False) items are not publicly reachable: only the owner
    gets the detail; everyone else gets 404 (treat hidden as offline).
    """
    try:
        item = _resolve_item(id)
        viewer = getattr(request, 'auth_profile', None)

        # Hidden items are private — owner only, 404 for anyone else.
        if not item.is_active:
            is_owner = viewer is not None and viewer.id == item.owner_id
            if not is_owner:
                raise Http404("Item not found")

        # Visibility: a REGISTERED item is 404 for anonymous viewers (any
        # signed-in user may see it; enforced here so the direct URL can't leak it).
        if not can_view_item(item, request):
            raise Http404("Item not found")

        # Demand count — shared, visibility-aware implementation (same as list paths)
        demand_total, demand_by_owner = batch_demand_maps([item.category_id], request)
        demand_count = demand_count_for(item.type, item.category_id, item.owner_id, demand_total, demand_by_owner)

        # Exact location: currently not exposed (Deal model removed)
        show_exact_location = False

        # Same assembly core as the list paths; detail keeps the FULL description
        # and adds the owner_* detail fields on top.
        data = assemble_item_dict(**_model_assemble_kwargs(item, request, target_currency, demand_count))
        return ItemDetailResponse(
            **data,
            owner_reputation=item.owner.reputation_score,
            owner_is_verified=item.owner.is_verified_wot,
            owner_avatar_url=item.owner.avatar.url if item.owner.avatar else None,
            owner_created_at=item.owner.created_at,
            owner_verifications_count=item.owner.received_verifications.filter(is_active=True).count(),
            exact_location={
                'latitude': item.location.y,
                'longitude': item.location.x
            } if show_exact_location and item.location else None,
        )

    except Item.DoesNotExist:
        raise Http404("Item not found")
    except Http404:
        raise
    except Exception as e:
        logger.error(f"Error retrieving item {id}: {e}")
        raise Http404("Item not found")


@item_router.put("/{id}/", response={200: ItemResponse, 400: dict, 403: dict, 404: dict, 409: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='items:update', key=user_or_ip, rate='10/m', method='PUT')
def update_item(request, id: str, data: ItemUpdateRequest):
    """
    Update an existing item (by ULID or slug).

    Requires authentication and owner permission.
    Uses optimistic locking with version field.
    """
    try:
        item = _resolve_item(id)
        
        # Check ownership
        if item.owner != request.auth_profile:
            return 403, {"error": "You don't have permission to update this item"}

        # Check version for optimistic locking (skip if client didn't send version)
        if data.expected_version is not None and item.version != data.expected_version:
            return 409, {"error": "Item has been modified by another user. Please refresh and try again."}
        
        with transaction.atomic():
            # Update fields if provided
            if data.title is not None:
                item.title = data.title
            if data.description is not None:
                item.description = data.description
            if data.spec_data is not None:
                item.spec_data = data.spec_data.dict()
            if data.location is not None:
                item.location = Point(data.location.longitude, data.location.latitude)

            # Re-detect language/country if content or location changed
            if data.title is not None or data.description is not None:
                item.language = detect_content_language(
                    item.title, item.description or '',
                    fallback=item.owner.preferred_language or '',
                )
            if data.location is not None:
                item.country_code = get_country_code_from_coords(
                    data.location.latitude, data.location.longitude
                )
            if data.pricing_options is not None:
                # Convert Decimal to float for JSON serialization
                pricing_opts_data = []
                for opt in data.pricing_options:
                    opt_dict = opt.dict(exclude_none=True)
                    if 'amount' in opt_dict and opt_dict['amount'] is not None:
                        opt_dict['amount'] = float(opt_dict['amount'])
                    pricing_opts_data.append(opt_dict)
                item.pricing_options = pricing_opts_data
            if data.is_active is not None:
                item.is_active = data.is_active
            if data.self_made is not None:
                # self_made is meaningful only for offers (you can't "make" a request)
                item.self_made = bool(data.self_made and item.type == 'CREDIT')
            if data.visibility is not None:
                item.visibility = data.visibility

            # Handle category update
            if data.category_id is not None:
                if data.category_id == "":
                    item.category = None
                else:
                    try:
                        # category_id is ULID (26 chars)
                        category_id = data.category_id
                        category = Category.objects.get(id=category_id)
                        # Validate that category is a leaf node (no children)
                        if not category.is_leaf:
                            logger.warning(f"Non-leaf category rejected on update: {category_id}")
                            return 400, {"error": "Please select a specific category. Parent categories cannot be used for items."}
                        item.category = category
                    except Category.DoesNotExist:
                        return 404, {"error": f"Category {data.category_id} not found"}

            # Handle establishment update (post on behalf of)
            # None = leave unchanged; "" = detach (post personally); ULID = attach if permitted.
            # Placed before any DB-mutating op below so an early permission return leaves no partial writes.
            if data.establishment_id is not None:
                if data.establishment_id == "":
                    item.establishment = None
                else:
                    from geo.permissions import get_establishment_for_action, POSTING_ROLES
                    from ninja.errors import HttpError
                    try:
                        item.establishment = get_establishment_for_action(
                            data.establishment_id, request.auth_profile, POSTING_ROLES
                        )
                    except HttpError as e:
                        return e.status_code, {"error": e.message}

            # Handle tags update
            if data.tag_names is not None:
                item.tags.clear()
                for tag_name in data.tag_names:
                    tag, _ = Tag.objects.get_or_create(name=tag_name.lower())
                    item.tags.add(tag)
            
            item.save()
            # Refresh to resolve F('version') + 1 expression to actual int
            item.refresh_from_db()

        logger.info(f"Item updated: {item.id} by {request.auth_profile.id}")
        return build_item_response(item, request)
        
    except Item.DoesNotExist:
        raise Http404("Item not found")
    except ValidationError as e:
        logger.warning(f"Item update validation error: {e}")
        return 400, {"error": "Invalid item data", "details": str(e)}
    except Exception as e:
        logger.error(f"Error updating item: {e}")
        return 500, {"error": "Failed to update item"}


@item_router.delete("/{id}/", auth=ProfileAuth())
@ratelimit(group='items:delete', key=user_or_ip, rate='10/m', method='DELETE')
def delete_item(request, id: str):
    """
    Delete an item permanently (by ULID or slug).

    Requires authentication and owner permission.
    """
    try:
        item = _resolve_item(id)

        # Check ownership
        if item.owner != request.auth_profile:
            raise LocalizedHttpError(403, "item_delete_forbidden", "You don't have permission to delete this item")

        item_ulid = item.id
        item.delete()

        logger.info(f"Item deleted: {item_ulid} by {request.auth_profile.id}")

        return {"message": "Item deleted successfully"}

    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Error deleting item: {e}")
        raise LocalizedHttpError(500, "item_delete_failed", "Failed to delete item")


@item_router.post("/{id}/deactivate/", response={200: ItemResponse, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='items:deactivate', key=user_or_ip, rate='10/m', method='POST')
def deactivate_item(request, id: str):
    """
    Mark an item as inactive (soft delete, by ULID or slug).

    Requires authentication and owner permission.
    """
    item = _resolve_item(id)

    # Check ownership
    if item.owner != request.auth_profile:
        raise LocalizedHttpError(403, "item_deactivate_forbidden", "You don't have permission to deactivate this item")

    item.is_active = False
    item.save()
    item.refresh_from_db()

    logger.info(f"Item deactivated: {item.id} by {request.auth_profile.id}")
    return build_item_response(item, request)


@item_router.post("/{id}/activate/", response={200: ItemResponse, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='items:activate', key=user_or_ip, rate='10/m', method='POST')
def activate_item(request, id: str):
    """
    Re-activate a previously hidden item (by ULID or slug).

    Requires authentication and owner permission. Inverse of deactivate_item.
    """
    item = _resolve_item(id)

    # Check ownership
    if item.owner != request.auth_profile:
        raise LocalizedHttpError(403, "item_activate_forbidden", "You don't have permission to activate this item")

    item.is_active = True
    item.save()
    item.refresh_from_db()

    logger.info(f"Item activated: {item.id} by {request.auth_profile.id}")
    return build_item_response(item, request)


@item_router.post("/{id}/images/", response={201: ItemImageResponse, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='items:upload_image', key=user_or_ip, rate='20/m', method='POST')
def upload_item_image(request, id: str, image: UploadedFile, order: int = Form(0), caption: str = Form("")):
    """
    Upload an image for an item (max 5 images per item)

    Requires authentication and owner permission.
    Images are ordered from 0 (primary) to 4.
    """
    from PIL import Image
    from io import BytesIO
    from django.core.files.uploadedfile import InMemoryUploadedFile
    import sys

    try:
        item = _resolve_item(id)

        # Check ownership
        if item.owner != request.auth_profile:
            return 403, {"error": "You don't have permission to upload images for this item"}

        # Check image count limit
        current_count = ObjectPhoto.objects.filter(object_id=item.id).count()
        if current_count >= 5:
            return 400, {"error": "Maximum 5 images per item allowed"}

        # Validate order. Upper bound is the max combined media position
        # (5 photos + 10 videos − 1); photos share one global order space with
        # videos so a photo can sit past index 4 in the unified media strip.
        if order < 0 or order > 14:
            return 400, {"error": "Order must be between 0 and 14"}

        # Validate image file — content_type + magic bytes (content_type can be spoofed)
        if not image.content_type.startswith('image/') or not _is_valid_image_magic(image.file):
            return 400, {"error": "File must be an image"}

        # Validate file size (max 15MB)
        if image.size > 15 * 1024 * 1024:
            return 400, {"error": "Image size must be less than 15MB"}

        # Process image with PIL (resize if too large)
        img = Image.open(image.file)

        # Convert to RGB if necessary
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')

        # Resize if larger than 1920x1920
        max_size = (1920, 1920)
        if img.width > max_size[0] or img.height > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Save to BytesIO
        output = BytesIO()
        img_format = 'JPEG' if img.mode == 'RGB' else 'PNG'
        img.save(output, format=img_format, quality=85, optimize=True)
        output.seek(0)

        # Create Django file object
        file_name = f"{item.id}_{order}.{img_format.lower()}"
        django_file = InMemoryUploadedFile(
            output, 'ImageField', file_name,
            f'image/{img_format.lower()}', sys.getsizeof(output), None
        )

        # Create ObjectPhoto
        with transaction.atomic():
            # Check if image with this order already exists
            existing = ObjectPhoto.objects.filter(object_id=item.id, order=order).first()
            if existing:
                # Delete old image
                existing.image.delete()
                existing.delete()

            photo = ObjectPhoto(
                object_id=item.id,
                uploaded_by=request.auth_profile,
                order=order,
                caption=caption
            )
            photo.image.save(file_name, django_file, save=True)

        logger.info(f"Image uploaded for item {item.id} by {request.auth_profile.id}")

        # Use relative URL to avoid SSR issues with localhost
        image_url = photo.image.url  # Already relative (/media/...)

        return 201, ItemImageResponse(
            id=photo.id,
            object_type=photo.type_name,
            url=image_url,
            order=photo.order,
            caption=photo.caption
        )

    except Item.DoesNotExist:
        return 404, {"error": "Item not found"}
    except Exception as e:
        logger.error(f"Error uploading image: {e}", exc_info=True)
        return 400, {"error": f"Failed to upload image: {str(e)}"}


@item_router.delete("/{id}/images/{image_id}/", response={200: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='items:delete_image', key=user_or_ip, rate='20/m', method='DELETE')
def delete_item_image(request, id: str, image_id: str):
    """
    Delete a single image from an item.

    Requires authentication and owner permission.
    """
    try:
        item = _resolve_item(id)
    except Item.DoesNotExist:
        return 404, {"error": "Item not found"}

    # Check ownership
    if item.owner != request.auth_profile:
        return 403, {"error": "You don't have permission to delete images for this item"}

    photo = ObjectPhoto.objects.filter(object_id=item.id, id=image_id).first()
    if not photo:
        return 404, {"error": "Image not found"}

    if photo.image:
        photo.image.delete(save=False)
    photo.delete()

    logger.info(f"Image {image_id} deleted from item {item.id} by {request.auth_profile.id}")
    return 200, {"success": True}


class MediaOrderEntry(BaseModel):
    type: str  # 'photo' | 'video'
    id: str


class MediaOrderPayload(BaseModel):
    # Full media sequence in the desired display order. Photos and videos share
    # one global order space — element index becomes each item's `order`, so the
    # detail-page gallery (which merges photos+videos and sorts by `order`)
    # renders them exactly as listed here. The first entry is the listing cover.
    order: List[MediaOrderEntry]


@item_router.patch("/{id}/media-order/", response={200: dict, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='items:reorder_media', key=user_or_ip, rate='30/m', method='PATCH')
def reorder_item_media(request, id: str, payload: MediaOrderPayload):
    """
    Set the combined display order of an item's photos and videos.

    Body: {"order": [{"type": "photo"|"video", "id": "<ulid>"}, ...]} — the
    full media list in the desired sequence. Each entry's position becomes its
    `order` (0-based), giving photos and videos one shared ordering so the owner
    can put a photo first and a video third.

    Requires authentication and owner permission.
    """
    from core.models import ObjectVideo

    try:
        item = _resolve_item(id)
    except Item.DoesNotExist:
        return 404, {"error": "Item not found"}

    if item.owner != request.auth_profile:
        return 403, {"error": "You don't have permission to reorder this item's media"}

    photo_ids = [e.id for e in payload.order if e.type == 'photo']
    video_ids = [e.id for e in payload.order if e.type == 'video']

    if any(e.type not in ('photo', 'video') for e in payload.order):
        return 400, {"error": "Each entry type must be 'photo' or 'video'"}

    photos = {p.id: p for p in ObjectPhoto.objects.filter(object_id=item.id, id__in=photo_ids)}
    videos = {v.id: v for v in ObjectVideo.objects.filter(object_id=item.id, id__in=video_ids)}

    # Every referenced id must resolve to a photo/video on THIS item (ignore dupes).
    if len(photos) != len(set(photo_ids)) or len(videos) != len(set(video_ids)):
        return 400, {"error": "Some media do not belong to this item"}

    photos_to_update = []
    videos_to_update = []
    for idx, e in enumerate(payload.order):
        obj = (photos if e.type == 'photo' else videos)[e.id]
        if obj.order != idx:
            obj.order = idx
            (photos_to_update if e.type == 'photo' else videos_to_update).append(obj)

    with transaction.atomic():
        if photos_to_update:
            ObjectPhoto.objects.bulk_update(photos_to_update, ['order'])
        if videos_to_update:
            ObjectVideo.objects.bulk_update(videos_to_update, ['order'])

    logger.info(f"Media reordered for item {item.id} by {request.auth_profile.id} "
                f"({len(photos)} photos, {len(videos)} videos)")
    return 200, {"success": True}


class AIAnalysisResponse(BaseModel):
    """AI analysis result for item image"""
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    category_confidence: float
    title: str
    description: str
    suggested_price: Optional[PricingOption] = None
    confidence: float
    provider: str  # 'claude', 'openai', 'google'

    model_config = ConfigDict(from_attributes=True)


@item_router.post("/analyze-image/", response={200: AIAnalysisResponse, 400: dict, 503: dict}, auth=ProfileAuth())
@ratelimit(group='items:analyze_image', key=user_or_ip, rate='10/h', method='POST')
def analyze_item_image(request, image: UploadedFile):
    """
    Analyze item image using AI vision API and return structured data

    Requires authentication. Returns category, title, description, and price estimate.

    Supported AI providers (configured in Django admin):
    - Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)
    - OpenAI GPT-5 (gpt-5)
    - Google Cloud Vision
    """
    from parahub.services.vision_ai import AIVisionService
    from parahub.models import AISettings

    try:
        # Validate image file
        if not image.content_type.startswith('image/'):
            return 400, {"error": "File must be an image"}


        # Validate file size (max 10MB for AI analysis)
        if image.size > 10 * 1024 * 1024:
            return 400, {"error": "Image size must be less than 10MB"}

        # Read image data
        image_data = image.read()

        # Get user's preferred language
        user_language = request.auth_profile.preferred_language or 'en'

        # Analyze image
        try:
            result = AIVisionService.analyze_item_image(image_data, language=user_language)
        except ValueError as e:
            # No AI provider configured
            return 503, {"error": str(e)}

        # Get category name
        category_name = None
        if result.get('category_id'):
            try:
                category = Category.objects.get(id=result['category_id'])
                category_name = category.name
            except Category.DoesNotExist:
                logger.warning(f"AI suggested non-existent category: {result['category_id']}")

        # Get configured providers
        ai_settings = AISettings.get_instance()
        vision_provider = ai_settings.provider if ai_settings.enabled else 'unknown'
        categorization_provider = ai_settings.categorization_provider if ai_settings.enabled else 'unknown'

        # Update usage stats
        ai_settings.total_requests += 1
        ai_settings.save(update_fields=['total_requests'])

        logger.info(f"AI image analysis completed for user {request.auth_profile.id} using vision={vision_provider}, cat={categorization_provider}")

        return 200, AIAnalysisResponse(
            category_id=result.get('category_id'),
            category_name=category_name,
            category_confidence=result.get('category_confidence', 0.8),
            title=result.get('title', ''),
            description=result.get('description', ''),
            suggested_price=result.get('suggested_price'),
            confidence=result.get('confidence', 0.8),
            provider=vision_provider
        )

    except Exception as e:
        logger.error(f"Error analyzing image: {e}", exc_info=True)
        return 400, {"error": f"Failed to analyze image: {str(e)}"}