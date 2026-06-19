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
from django.db.models import Q
from django.contrib.gis.geos import Point
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from decimal import Decimal
from datetime import datetime
import logging
import orjson

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from parahub.endpoints.ai_vision import _is_valid_image_magic
from market.models import Item
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
    expected_version: Optional[int] = Field(None, description="Version for optimistic locking")


def fuzz_location(point: Point, fuzz_meters: int = 100) -> Dict[str, float]:
    """
    Fuzz location for privacy by rounding to nearest grid point

    Args:
        point: Original location point
        fuzz_meters: Grid size in meters (default 100m)

    Returns:
        Dictionary with fuzzed latitude and longitude
    """
    if not point:
        return None

    # Simple grid-based fuzzing
    # In production, use more sophisticated fuzzing
    grid_size = fuzz_meters / 111000  # Rough conversion to degrees

    fuzzed_lat = round(point.y / grid_size) * grid_size
    fuzzed_lon = round(point.x / grid_size) * grid_size

    return {
        'latitude': fuzzed_lat,
        'longitude': fuzzed_lon,
        'fuzzed': True,
        'accuracy_meters': fuzz_meters
    }


def convert_pricing_options(pricing_options: List[Dict], target_currency: str) -> List[PricingOption]:
    """
    Convert pricing options to target currency

    Args:
        pricing_options: List of pricing option dicts from Item model
        target_currency: Target currency code (EUR, USD, etc)

    Returns:
        List of PricingOption objects with converted amounts
    """
    result = []
    for opt in pricing_options:
        original_currency = opt.get('currency')
        original_amount = opt.get('amount')

        # Build PricingOption
        pricing_opt = PricingOption(
            type=opt.get('type'),
            amount=original_amount,
            currency=original_currency,
            unit=opt.get('unit') or opt.get('period'),
            note=opt.get('note')
        )

        # Convert if needed
        if original_currency and original_amount and target_currency and original_currency != target_currency:
            try:
                converted_amount = ExchangeRate.convert(
                    Decimal(str(original_amount)),
                    original_currency,
                    target_currency
                )
                pricing_opt.amount = converted_amount
                pricing_opt.currency = target_currency
                pricing_opt.converted_from = original_currency
            except Exception as e:
                logger.warning(f"Currency conversion failed ({original_currency} -> {target_currency}): {e}")
                # Keep original values if conversion fails

        result.append(pricing_opt)

    return result


def build_item_response(item: Item, request=None, target_currency: str = None, include_distance: bool = False, demand_count: int = None, photos_map: dict = None) -> ItemResponse:
    """
    Build ItemResponse from Item model instance

    Avoids Pydantic model_validate which can't access related fields.

    Args:
        item: Item model instance
        request: HTTP request object (for building absolute URLs)
        target_currency: Optional target currency for price conversion
        include_distance: Whether to include distance_meters from annotation
        photos_map: Pre-fetched {object_id: [ObjectPhoto, ...]} to avoid N+1
    """
    # Build image responses (sorted by order, then created_at)
    # Use relative URLs to avoid SSR issues with localhost
    images = []
    if photos_map is not None:
        photo_list = photos_map.get(item.id, [])
    else:
        photo_list = ObjectPhoto.objects.filter(object_id=item.id).order_by('order', 'created_at')
    for img in photo_list:
        image_url = img.image.url  # Already relative (/media/...)
        images.append(ItemImageResponse(
            id=img.id,
            object_type=img.type_name,
            url=image_url,
            order=img.order,
            caption=img.caption
        ))

    # Convert pricing_options with optional currency conversion
    if target_currency:
        pricing_opts = convert_pricing_options(item.pricing_options, target_currency)
    else:
        pricing_opts = []
        for opt in item.pricing_options:
            pricing_opts.append(PricingOption(
                type=opt.get('type'),
                amount=opt.get('amount'),
                currency=opt.get('currency'),
                unit=opt.get('unit') or opt.get('period'),
                note=opt.get('note')
            ))

    # Extract distance from annotation if available
    distance = None
    if include_distance and hasattr(item, 'distance_meters'):
        distance = float(item.distance_meters.m) if item.distance_meters else None

    return ItemResponse(
        id=item.id,
        object_type=item.type_name,
        slug=item.slug,
        owner_id=item.owner.id,
        owner_account_id=item.owner.account.id,
        owner_hna=item.owner.hna,
        owner_display_name=item.owner.display_name or '',
        title=item.title,
        description=_truncate(item.description, 200),
        item_type=item.type,
        spec_data=item.spec_data,
        location=fuzz_location(item.location),
        pricing_options=pricing_opts,
        accepted_payment_methods=item.accepted_payment_methods,
        is_active=item.is_active,
        language=item.language,
        is_international=item.is_international,
        category_id=item.category.id if item.category else None,
        category_name=item.category.name if item.category else None,
        category_path=item.category.get_path() if item.category else None,
        tags=[tag.name for tag in item.tags.all()],
        images=images,
        version=item.version,
        created_at=item.created_at,
        updated_at=item.updated_at,
        distance_meters=distance,
        establishment_id=item.establishment_id if item.establishment_id else None,
        establishment_name=item.establishment.name if item.establishment else None,
        establishment_slug=item.establishment.slug if item.establishment else None,
        establishment_logo_url=item.establishment.logo_url if item.establishment else None,
        is_demo=bool(item.attributes.get('__demo_seed') or item.attributes.get('demo')),
        demand_count=demand_count,
    )


def _fuzz_coord(val, grid_size=100/111000):
    """Grid-snap a single coordinate for privacy."""
    if val is None:
        return None
    return round(val / grid_size) * grid_size


def _list_items_raw(request, item_type, pricing_type, category_id_resolved,
                    is_active, min_price, max_price, include_barter,
                    owner_id, target_currency, language, ordering,
                    page, page_size, is_staff_or_test):
    """Raw SQL fast path for items list — bypasses ORM/Pydantic overhead."""
    conditions = ["TRUE"]
    params = []

    # Hide test/bot items for non-staff
    if not is_staff_or_test:
        conditions.append("a.is_test = FALSE AND a.is_bot = FALSE")

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
                p.id, p.local_name, p.display_name, inst.domain, a.id,
                -- category
                c.name, c.slug,
                c2.id, c2.name, c2.slug,
                c3.id, c3.name, c3.slug,
                c4.id, c4.name, c4.slug,
                c5.id, c5.name, c5.slug,
                -- establishment
                est.name, est.slug, est.logo_url
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

    # Batch demand counts
    demand_counts = {}
    cat_ids = list({r[17] for r in rows if r[17]})
    if cat_ids:
        with connection.cursor() as cur:
            placeholders_c = ','.join(['%s'] * len(cat_ids))
            cur.execute(f"""
                SELECT category_id, type, COUNT(*)
                FROM market_item
                WHERE category_id IN ({placeholders_c}) AND is_active = TRUE
                GROUP BY category_id, type
            """, cat_ids)
            for cat_id, itype, cnt in cur.fetchall():
                demand_counts[(cat_id, itype)] = cnt

    # Build response
    grid = 100 / 111000
    items = []
    for r in rows:
        (item_id, slug, title, desc, itype,
         spec_data, pricing_opts_raw, payment_methods,
         active, lang, international,
         lat, lon,
         version, created_at, updated_at, attrs,
         cat_id, est_id,
         owner_id, local_name, display_name, inst_domain, account_id,
         cat_name, cat_slug,
         c2_id, c2_name, c2_slug,
         c3_id, c3_name, c3_slug,
         c4_id, c4_name, c4_slug,
         c5_id, c5_name, c5_slug,
         est_name, est_slug, est_logo) = r

        # Parse JSONB fields (cursor returns str for jsonb)
        spec = orjson.loads(spec_data) if isinstance(spec_data, str) else (spec_data or {})
        pricing_opts = orjson.loads(pricing_opts_raw) if isinstance(pricing_opts_raw, str) else (pricing_opts_raw or [])
        pay_methods = orjson.loads(payment_methods) if isinstance(payment_methods, str) else (payment_methods or [])
        attrs_parsed = orjson.loads(attrs) if isinstance(attrs, str) else (attrs or {})

        # Build pricing_options response
        pricing_response = []
        for opt in pricing_opts:
            po = {
                'type': opt.get('type'),
                'amount': opt.get('amount'),
                'currency': opt.get('currency'),
                'unit': opt.get('unit') or opt.get('period'),
                'note': opt.get('note'),
                'converted_from': None,
            }
            # Currency conversion if requested
            if target_currency and po['currency'] and po['amount'] and po['currency'] != target_currency:
                try:
                    converted = ExchangeRate.convert(
                        Decimal(str(po['amount'])), po['currency'], target_currency
                    )
                    po['converted_from'] = po['currency']
                    po['amount'] = str(converted)
                    po['currency'] = target_currency
                except Exception:
                    pass
            pricing_response.append(po)

        # Fuzz location
        location = None
        if lat is not None and lon is not None:
            location = {
                'latitude': _fuzz_coord(lat, grid),
                'longitude': _fuzz_coord(lon, grid),
                'fuzzed': True, 'accuracy_meters': 100,
            }

        # Category path (walk up to 5 levels)
        cat_path = None
        if cat_id:
            cat_path = []
            for cid, cname, cslug in [
                (c5_id, c5_name, c5_slug), (c4_id, c4_name, c4_slug),
                (c3_id, c3_name, c3_slug), (c2_id, c2_name, c2_slug),
                (cat_id, cat_name, cat_slug),
            ]:
                if cid:
                    cat_path.append({'id': cid, 'name': cname, 'slug': cslug})

        # Demand count
        dc = None
        if cat_id:
            opposite = 'DEBIT' if itype == 'CREDIT' else 'CREDIT'
            dc = demand_counts.get((cat_id, opposite), 0) or None

        items.append({
            'id': item_id, 'object_type': 'item',
            'slug': slug or '', 'owner_id': owner_id,
            'owner_account_id': account_id,
            'owner_hna': f'{local_name}@{inst_domain}',
            'owner_display_name': display_name or '',
            'title': title, 'description': desc or '',
            'item_type': itype, 'spec_data': spec,
            'location': location,
            'pricing_options': pricing_response,
            'accepted_payment_methods': pay_methods,
            'is_active': active, 'language': lang or '',
            'is_international': international,
            'category_id': cat_id, 'category_name': cat_name,
            'category_path': cat_path,
            'tags': tags_map.get(item_id, []),
            'images': photos_map.get(item_id, []),
            'version': version,
            'created_at': created_at.isoformat() if created_at else None,
            'updated_at': updated_at.isoformat() if updated_at else None,
            'distance_meters': None,
            'establishment_id': est_id,
            'establishment_name': est_name,
            'establishment_slug': est_slug,
            'establishment_logo_url': est_logo,
            'is_demo': bool(attrs_parsed.get('__demo_seed') or attrs_parsed.get('demo')),
            'demand_count': dc,
        })

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
                page, page_size, is_staff_or_test,
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

        # Price range filters on pricing_options JSONField
        if min_price is not None or max_price is not None:
            price_q = Q()
            if min_price is not None:
                price_q &= Q(pricing_options__0__amount__gte=min_price)
            if max_price is not None:
                price_q &= Q(pricing_options__0__amount__lte=max_price)
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
            # Sort by minimum price (ascending)
            # Extract first pricing option amount for sorting
            queryset = queryset.order_by('pricing_options__0__amount')
        elif ordering == '-min_price':
            # Sort by minimum price (descending)
            queryset = queryset.order_by('-pricing_options__0__amount')
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

        # Batch compute demand counts: for each item, count opposite-type items in same category
        demand_counts = {}
        category_ids = {item.category_id for item in paginated_items if item.category_id}
        if category_ids:
            from django.db.models import Count
            counts = (
                Item.objects.filter(category_id__in=category_ids, is_active=True)
                .values('category_id', 'type')
                .annotate(count=Count('id'))
            )
            for row in counts:
                demand_counts[(row['category_id'], row['type'])] = row['count']

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
            # demand_count = opposite type items in same category
            dc = None
            if item.category_id:
                opposite = 'DEBIT' if item.type == 'CREDIT' else 'CREDIT'
                dc = demand_counts.get((item.category_id, opposite), 0) or None
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


@item_router.get("/{id}/", response={200: ItemDetailResponse, 404: dict})
@ratelimit(group='items:detail', key='ip', rate='60/m')
def get_item(request, id: str, target_currency: Optional[str] = None):
    """
    Get detailed item information by ULID or slug.

    Returns fuzzed location for public access.
    Exact location only available to deal participants.
    Prices can be converted to target_currency if provided.
    """
    try:
        item = _resolve_item(id)

        # Demand count: opposite-type items in same category
        demand_count = None
        if item.category_id:
            opposite_type = 'DEBIT' if item.type == 'CREDIT' else 'CREDIT'
            dc = Item.objects.filter(
                category_id=item.category_id,
                type=opposite_type,
                is_active=True,
            ).count()
            if dc > 0:
                demand_count = dc

        # Exact location: currently not exposed (Deal model removed)
        show_exact_location = False

        # Convert pricing_options with optional currency conversion
        if target_currency:
            pricing_opts = convert_pricing_options(item.pricing_options, target_currency)
        else:
            pricing_opts = []
            for opt in item.pricing_options:
                pricing_opts.append(PricingOption(
                    type=opt.get('type'),
                    amount=opt.get('amount'),
                    currency=opt.get('currency'),
                    unit=opt.get('unit') or opt.get('period'),
                    note=opt.get('note')
                ))

        # Build image responses (sorted by order, then created_at)
        # Use relative URLs to avoid SSR issues with localhost
        images = []
        for img in ObjectPhoto.objects.filter(object_id=item.id).order_by('order', 'created_at'):
            image_url = img.image.url  # Already relative (/media/...)
            images.append(ItemImageResponse(
                id=img.id,
                object_type=img.type_name,
                url=image_url,
                order=img.order,
                caption=img.caption
            ))

        # Build response manually
        response_data = ItemDetailResponse(
            id=item.id,
            object_type=item.type_name,
            slug=item.slug,
            owner_id=item.owner.id,
            owner_account_id=item.owner.account.id,
            owner_hna=item.owner.hna,
            owner_display_name=item.owner.display_name or '',
            owner_reputation=item.owner.reputation_score,
            owner_is_verified=item.owner.is_verified_wot,
            owner_avatar_url=item.owner.avatar.url if item.owner.avatar else None,
            owner_created_at=item.owner.created_at,
            owner_verifications_count=item.owner.received_verifications.filter(is_active=True).count(),
            title=item.title,
            description=item.description,
            item_type=item.type,
            spec_data=item.spec_data,
            location=fuzz_location(item.location),
            exact_location={
                'latitude': item.location.y,
                'longitude': item.location.x
            } if show_exact_location and item.location else None,
            pricing_options=pricing_opts,
            accepted_payment_methods=item.accepted_payment_methods,
            is_active=item.is_active,
            category_id=item.category.id if item.category else None,
            category_name=item.category.name if item.category else None,
            category_path=item.category.get_path() if item.category else None,
            tags=[tag.name for tag in item.tags.all()],
            images=images,
            language=item.language,
            is_international=item.is_international,
            version=item.version,
            created_at=item.created_at,
            updated_at=item.updated_at,
            establishment_id=item.establishment_id if item.establishment_id else None,
            establishment_name=item.establishment.name if item.establishment else None,
            establishment_slug=item.establishment.slug if item.establishment else None,
            establishment_logo_url=item.establishment.logo.url if item.establishment and item.establishment.logo else None,
            is_demo=bool(item.attributes.get('__demo_seed') or item.attributes.get('demo')),
            demand_count=demand_count,
        )

        return response_data

    except Item.DoesNotExist:
        raise Http404("Item not found")
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
            raise HttpError(403, "You don't have permission to delete this item")

        item_ulid = item.id
        item.delete()

        logger.info(f"Item deleted: {item_ulid} by {request.auth_profile.id}")

        return {"message": "Item deleted successfully"}

    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Error deleting item: {e}")
        raise HttpError(500, "Failed to delete item")


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
        raise HttpError(403, "You don't have permission to deactivate this item")

    item.is_active = False
    item.save()
    item.refresh_from_db()

    logger.info(f"Item deactivated: {item.id} by {request.auth_profile.id}")
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

        # Validate order
        if order < 0 or order > 4:
            return 400, {"error": "Order must be between 0 and 4"}

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