"""
Events (community meetups) endpoints.
"""

from ninja import Router
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.pagination import paginate, PageNumberPagination
from typing import Dict, Optional, List
from pydantic import BaseModel, Field
import logging
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db.models import Q, F
from django.utils import timezone
from datetime import datetime

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from geo.endpoints.buildings import BuildingResponse, LocationInput

logger = logging.getLogger(__name__)

router = Router(tags=["Geo / Events"])


# ===== Schemas =====

class EventInput(BaseModel):
    """Create/update event"""
    title: str = Field(..., max_length=255, min_length=3)
    description: str = Field(..., min_length=10)
    category_id: Optional[str] = None
    event_type: str = Field(default="OFFLINE", pattern="^(OFFLINE|ONLINE|HYBRID)$")
    starts_at: datetime
    ends_at: Optional[datetime] = None
    timezone: str = Field(default="UTC", max_length=50)
    world_object_id: Optional[str] = None
    location: Optional[LocationInput] = None
    location_name: Optional[str] = Field(None, max_length=255)
    online_url: Optional[str] = None
    max_participants: Optional[int] = Field(None, ge=1, le=10000)
    cover_image_url: Optional[str] = None
    establishment_id: Optional[str] = Field(None, description="Post on behalf of this establishment (ULID)")


class OrganizerInfo(BaseModel):
    """Organizer profile info"""
    id: str
    hna: Optional[str]
    display_name: Optional[str]
    avatar_url: Optional[str]


class EventResponse(BaseModel):
    """Full event details"""
    id: str
    object_type: str = "event"
    organizer: OrganizerInfo
    title: str
    description: str
    category_id: Optional[str]
    category_name: Optional[str]
    category_icon: Optional[str]
    event_type: str
    starts_at: datetime
    ends_at: Optional[datetime]
    timezone: str
    world_object: Optional[BuildingResponse]
    location: Optional[Dict[str, float]]
    location_name: Optional[str]
    online_url: Optional[str]
    max_participants: Optional[int]
    matrix_room_id: Optional[str]
    cover_image_url: Optional[str]
    status: str
    participants_count: int
    views_count: int
    is_full: bool
    is_organizer: bool = False
    my_participation_status: Optional[str] = None
    # Act as establishment
    establishment_id: Optional[str] = None
    establishment_name: Optional[str] = None
    establishment_slug: Optional[str] = None
    establishment_logo_url: Optional[str] = None
    is_demo: bool = False
    created_at: datetime
    updated_at: datetime


class EventListItem(BaseModel):
    """Simplified for list views"""
    id: str
    object_type: str = "event"
    title: str
    organizer_hna: Optional[str]
    organizer_display_name: Optional[str] = None
    organizer_avatar_url: Optional[str]
    category_name: Optional[str]
    category_icon: Optional[str]
    event_type: str
    starts_at: datetime
    ends_at: Optional[datetime]
    location_display: Optional[str]
    location: Optional[Dict[str, float]]
    status: str
    participants_count: int
    max_participants: Optional[int]
    is_full: bool
    cover_image_url: Optional[str]
    # Act as establishment
    establishment_id: Optional[str] = None
    establishment_name: Optional[str] = None
    establishment_slug: Optional[str] = None
    establishment_logo_url: Optional[str] = None
    is_demo: bool = False


class ParticipantInfo(BaseModel):
    """Event participant info"""
    id: str
    profile_id: str
    profile_hna: Optional[str]
    profile_display_name: Optional[str]
    profile_avatar_url: Optional[str]
    status: str
    joined_at: datetime


class JoinEventInput(BaseModel):
    """Join event request"""
    status: str = Field(default="GOING", pattern="^(GOING|MAYBE)$")


# ===== Helpers =====

def _format_event_response(event, current_profile=None) -> EventResponse:
    """Helper to format Event model to response"""
    world_object_data = None
    if event.world_object:
        w = event.world_object
        osm_way_id = None
        if w.xeno_source == 'osm' and w.xeno_id.startswith('way/'):
            try:
                osm_way_id = int(w.xeno_id.split('/')[1])
            except Exception:
                pass
        world_object_data = BuildingResponse(
            id=w.id,
            osm_way_id=osm_way_id,
            xeno_source=w.xeno_source,
            xeno_id=w.xeno_id,
            location={"lat": w.location.y, "lon": w.location.x} if w.location else {"lat": 0, "lon": 0},
            country=w.country,
            city=w.city,
            street=w.street,
            house_number=w.house_number,
            postal_code=w.postal_code,
            full_address=w.full_address,
            building_type=w.building_type,
            levels=w.levels,
            establishments_count=w.establishments_count,
            created_at=w.created_at,
            updated_at=w.updated_at
        )

    location_data = None
    if event.location:
        location_data = {"lat": event.location.y, "lon": event.location.x}

    organizer = event.organizer
    organizer_info = OrganizerInfo(
        id=organizer.id,
        hna=organizer.hna,
        display_name=organizer.display_name,
        avatar_url=organizer.avatar.url if organizer.avatar else None
    )

    # Check if current user is organizer or participant
    is_organizer = bool(current_profile and event.organizer_id == current_profile.id)
    my_participation_status = None

    if current_profile and not is_organizer:
        from geo.models import EventParticipant
        participation = EventParticipant.objects.filter(
            event=event,
            profile=current_profile
        ).first()
        if participation:
            my_participation_status = participation.status

    return EventResponse(
        id=event.id,
        organizer=organizer_info,
        title=event.title,
        description=event.description,
        category_id=event.category_id,
        category_name=event.category.name if event.category else None,
        category_icon=event.category.icon if event.category else None,
        event_type=event.event_type,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        timezone=event.timezone,
        world_object=world_object_data,
        location=location_data,
        location_name=event.location_name,
        online_url=event.online_url,
        max_participants=event.max_participants,
        matrix_room_id=event.matrix_room_id,
        cover_image_url=event.cover_image.url if event.cover_image else event.cover_image_url or None,
        status=event.status,
        participants_count=event.participants_count,
        views_count=event.views_count,
        is_full=event.is_full(),
        is_organizer=is_organizer,
        my_participation_status=my_participation_status,
        establishment_id=event.establishment_id if event.establishment_id else None,
        establishment_name=event.establishment.name if event.establishment else None,
        establishment_slug=event.establishment.slug if event.establishment else None,
        establishment_logo_url=event.establishment.logo_url if event.establishment else None,
        is_demo=bool(event.attributes.get('__demo_seed') or event.attributes.get('demo')),
        created_at=event.created_at,
        updated_at=event.updated_at
    )


def _format_event_list_item(event) -> EventListItem:
    """Helper to format Event for list views"""
    location_data = None
    location_display = None

    if event.world_object:
        location_display = event.world_object.full_address
        location_data = {"lat": event.world_object.location.y, "lon": event.world_object.location.x}
    elif event.location_name:
        location_display = event.location_name
        if event.location:
            location_data = {"lat": event.location.y, "lon": event.location.x}
    elif event.location:
        location_data = {"lat": event.location.y, "lon": event.location.x}
        location_display = f"{event.location.y:.4f}, {event.location.x:.4f}"

    return EventListItem(
        id=event.id,
        title=event.title,
        organizer_hna=event.organizer.hna if event.organizer else None,
        organizer_display_name=event.organizer.display_name if event.organizer else None,
        organizer_avatar_url=event.organizer.avatar.url if event.organizer and event.organizer.avatar else None,
        category_name=event.category.name if event.category else None,
        category_icon=event.category.icon if event.category else None,
        event_type=event.event_type,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        location_display=location_display,
        location=location_data,
        status=event.status,
        participants_count=event.participants_count,
        max_participants=event.max_participants,
        is_full=event.is_full(),
        cover_image_url=event.cover_image.url if event.cover_image else event.cover_image_url or None,
        establishment_id=event.establishment_id if event.establishment_id else None,
        establishment_name=event.establishment.name if event.establishment else None,
        establishment_slug=event.establishment.slug if event.establishment else None,
        establishment_logo_url=event.establishment.logo_url if event.establishment else None,
        is_demo=bool(event.attributes.get('__demo_seed') or event.attributes.get('demo')),
    )


def _create_event_matrix_room(event, organizer_profile) -> Optional[str]:
    """Create Matrix chat room for event. Returns room_id or None on failure."""
    import httpx
    from django.conf import settings

    try:
        SYNAPSE_BASE_URL = getattr(settings, 'SYNAPSE_INTERNAL_URL', 'http://localhost:8008')
        SYNAPSE_ADMIN_TOKEN = getattr(settings, 'SYNAPSE_ADMIN_TOKEN', None)

        if not SYNAPSE_ADMIN_TOKEN:
            logger.warning("SYNAPSE_ADMIN_TOKEN not configured, skipping Matrix room creation")
            return None

        # Get organizer's Matrix token
        from parahub.endpoints.matrix_auth import _get_or_create_matrix_token

        organizer_token = _get_or_create_matrix_token(organizer_profile.account_id)
        if not organizer_token:
            logger.error(f"Failed to get Matrix token for organizer {organizer_profile.id}")
            return None

        with httpx.Client(timeout=10) as client:
            create_room_response = client.post(
                f"{SYNAPSE_BASE_URL}/_matrix/client/r0/createRoom",
                headers={"Authorization": f"Bearer {organizer_token}"},
                json={
                    "preset": "public_chat",
                    "name": event.title,
                    "topic": f"Event chat: {event.title}",
                    "visibility": "private",
                    "initial_state": []
                }
            )

            if create_room_response.status_code in (200, 201):
                room_data = create_room_response.json()
                room_id = room_data.get("room_id")
                logger.info(f"Created Matrix room {room_id} for event {event.id}")
                return room_id
            else:
                logger.error(f"Failed to create Matrix room: {create_room_response.text}")
                return None

    except Exception as e:
        logger.error(f"Error creating Matrix room for event {event.id}: {e}")
        return None


def _join_event_matrix_room(event, profile) -> bool:
    """Join user to event's Matrix room. Returns True on success."""
    import httpx
    from django.conf import settings

    if not event.matrix_room_id:
        return False

    try:
        SYNAPSE_BASE_URL = getattr(settings, 'SYNAPSE_INTERNAL_URL', 'http://localhost:8008')

        from parahub.endpoints.matrix_auth import _get_or_create_matrix_token

        user_token = _get_or_create_matrix_token(profile.account_id)
        if not user_token:
            logger.error(f"Failed to get Matrix token for user {profile.id}")
            return False

        with httpx.Client(timeout=10) as client:
            join_response = client.post(
                f"{SYNAPSE_BASE_URL}/_matrix/client/r0/rooms/{event.matrix_room_id}/join",
                headers={"Authorization": f"Bearer {user_token}"},
                json={}
            )

            if join_response.status_code in (200, 201):
                logger.info(f"User {profile.id} joined Matrix room {event.matrix_room_id}")
                return True
            else:
                logger.error(f"Failed to join Matrix room: {join_response.text}")
                return False

    except Exception as e:
        logger.error(f"Error joining Matrix room for event {event.id}: {e}")
        return False


# ===== Endpoints =====

@router.post("/events/", auth=ProfileAuth(), response={200: EventResponse, 400: dict, 403: dict, 404: dict})
@ratelimit(group='events:create', key=user_or_ip, rate='10/m', method='POST')
def create_event(request, payload: EventInput):
    """
    Create new event. Requires WoT level 3+ (or admin/parahub member).
    Automatically creates Matrix chat room for the event.
    """
    from geo.models import Event, WorldObject
    from taxonomy.models import Category
    from identity.models import Verification

    # Validate establishment if posting on behalf
    establishment = None
    if payload.establishment_id:
        from geo.permissions import get_establishment_for_action, POSTING_ROLES
        establishment = get_establishment_for_action(payload.establishment_id, request.auth, POSTING_ROLES)

    # Skip WoT check for admins
    if not request.auth.account.is_superuser:
        is_parahub_member = request.auth.is_foundation_member()

        if not is_parahub_member:
            verification_count = Verification.objects.filter(
                verified_profile=request.auth,
                is_active=True
            ).count()
            if verification_count < 3:
                raise HttpError(403, "Requires WoT level 3+ to create events (or be admin/parahub member)")

    # Validate event type and location
    if payload.event_type in ('OFFLINE', 'HYBRID'):
        if not payload.world_object_id and not payload.location and not payload.location_name:
            raise HttpError(400, "Offline/hybrid events require location (world_object_id, location coordinates, or location_name)")

    if payload.event_type in ('ONLINE', 'HYBRID'):
        if not payload.online_url:
            raise HttpError(400, "Online/hybrid events require online_url")

    # Validate dates
    if payload.ends_at and payload.ends_at <= payload.starts_at:
        raise HttpError(400, "End time must be after start time")

    with transaction.atomic():
        world_object = None
        if payload.world_object_id:
            world_object = get_object_or_404(WorldObject, id=payload.world_object_id)

        category = None
        if payload.category_id:
            category = get_object_or_404(Category, id=payload.category_id)

        location_point = None
        if payload.location:
            location_point = Point(payload.location.longitude, payload.location.latitude, srid=4326)

        event = Event.objects.create(
            organizer=request.auth,
            establishment=establishment,
            title=payload.title,
            description=payload.description,
            category=category,
            event_type=payload.event_type,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            timezone=payload.timezone,
            world_object=world_object,
            location=location_point,
            location_name=payload.location_name or "",
            online_url=payload.online_url or "",
            max_participants=payload.max_participants,
            cover_image_url=payload.cover_image_url or "",
            status=Event.Status.PUBLISHED  # Auto-publish, no moderation for now
        )

        # Create Matrix room for the event
        matrix_room_id = _create_event_matrix_room(event, request.auth)
        if matrix_room_id:
            event.matrix_room_id = matrix_room_id
            event.save(update_fields=['matrix_room_id'])

    return _format_event_response(event, request.auth)


@router.get("/events/{event_id}/", auth=None, response=EventResponse)
@ratelimit(group='events:detail', key='ip', rate='60/m')
def get_event(request, event_id: str):
    """Get event details. Increments view counter."""
    from geo.models import Event

    event = get_object_or_404(
        Event.objects.select_related('organizer', 'world_object', 'category'),
        id=event_id
    )

    # Increment views
    Event.objects.filter(id=event_id).update(views_count=F('views_count') + 1)
    event.refresh_from_db()

    # Get current user's profile if authenticated
    current_profile = None
    if request.user.is_authenticated:
        from identity.models import Profile
        current_profile = Profile.objects.filter(account=request.user, is_primary=True).first()

    return _format_event_response(event, current_profile)


@router.post("/events/{event_id}/cover-image/", auth=ProfileAuth(), response={200: dict, 400: dict, 403: dict, 404: dict})
@ratelimit(group='events:upload_cover', key=user_or_ip, rate='10/m', method='POST')
def upload_event_cover_image(request, event_id: str, image: UploadedFile):
    """Upload cover image for event. Only organizer can upload. Max 10MB, JPEG/PNG."""
    from PIL import Image as PILImage
    from io import BytesIO
    from django.core.files.uploadedfile import InMemoryUploadedFile
    from parahub.endpoints.ai_vision import _is_valid_image_magic
    import sys

    from geo.models import Event

    event = get_object_or_404(Event, id=event_id)

    if event.organizer_id != request.auth.id:
        return 403, {"error": "Only organizer can upload cover image"}

    # Validate image
    if not image.content_type.startswith('image/') or not _is_valid_image_magic(image.file):
        return 400, {"error": "File must be an image (JPEG/PNG/WebP)"}

    if image.size > 10 * 1024 * 1024:
        return 400, {"error": "Image must be less than 10MB"}

    # Process with PIL
    img = PILImage.open(image.file)
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')

    # Resize if too large (max 1920px wide for cover)
    if img.width > 1920:
        ratio = 1920 / img.width
        img = img.resize((1920, int(img.height * ratio)), PILImage.Resampling.LANCZOS)

    output = BytesIO()
    img_format = 'JPEG' if img.mode == 'RGB' else 'PNG'
    img.save(output, format=img_format, quality=85, optimize=True)
    output.seek(0)

    file_name = f"event_{event_id}.{img_format.lower()}"
    django_file = InMemoryUploadedFile(
        output, 'ImageField', file_name,
        f'image/{img_format.lower()}', sys.getsizeof(output), None
    )

    # Delete old cover image if exists
    if event.cover_image:
        event.cover_image.delete(save=False)

    event.cover_image.save(file_name, django_file, save=True)

    return 200, {"url": event.cover_image.url}


@router.get("/events/", auth=None, response=List[EventListItem])
@ratelimit(group='events:list', key='ip', rate='60/m')
@paginate(PageNumberPagination, page_size=20)
def list_events(
    request,
    status: Optional[str] = "PUBLISHED",
    event_type: Optional[str] = None,
    category_id: Optional[str] = None,
    city: Optional[str] = None,
    country: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    time_filter: Optional[str] = "upcoming",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: Optional[float] = None,
    organizer_id: Optional[str] = None,
    search: Optional[str] = None
):
    """
    List events with filters.

    Filters:
    - status: DRAFT, PUBLISHED, CANCELLED, COMPLETED (default: PUBLISHED)
    - event_type: OFFLINE, ONLINE, HYBRID
    - category_id: Filter by category
    - city/country: Filter by location
    - date_from/date_to: Filter by date range (ISO format: YYYY-MM-DD)
    - time_filter: upcoming (default), past, all
    - lat/lon/radius_km: Geographic search
    - organizer_id: Filter by organizer
    - search: Search in title/description
    """
    from geo.models import Event

    qs = Event.objects.select_related('organizer', 'organizer__instance', 'world_object', 'category', 'establishment')

    # Hide events from test/bot accounts for non-staff/non-test users
    user = getattr(request, 'user', None)
    if user and getattr(user, 'is_authenticated', False):
        if not getattr(user, 'is_staff', False) and not getattr(user, 'is_test', False):
            qs = qs.exclude(organizer__account__is_test=True).exclude(organizer__account__is_bot=True)
    else:
        qs = qs.exclude(organizer__account__is_test=True).exclude(organizer__account__is_bot=True)

    # Status filter
    if status == 'DRAFT':
        # DRAFT events are only visible to the organizer
        current_profile = getattr(request, 'auth_profile', None)
        if not current_profile:
            # Try to resolve from session (endpoint is auth=None)
            if request.user and request.user.is_authenticated:
                from identity.models import Profile
                current_profile = Profile.objects.filter(account=request.user, is_primary=True).first()
        if not current_profile:
            raise HttpError(401, "Authentication required to view draft events")
        qs = qs.filter(status='DRAFT', organizer=current_profile)
    elif status:
        qs = qs.filter(status=status)

    # Event type filter
    if event_type:
        qs = qs.filter(event_type=event_type)

    # Category filter
    if category_id:
        qs = qs.filter(category_id=category_id)

    # Organizer filter
    if organizer_id:
        qs = qs.filter(organizer_id=organizer_id)

    # Search
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))

    # Time filter (upcoming/past/all)
    now = timezone.now()
    if time_filter == 'past':
        qs = qs.filter(starts_at__lt=now)
    elif time_filter != 'all':
        # Default: upcoming
        qs = qs.filter(starts_at__gte=now)

    # Date filters (override time_filter if both provided)
    if date_from:
        try:
            from_date = datetime.fromisoformat(date_from)
            qs = qs.filter(starts_at__gte=from_date)
        except ValueError:
            pass

    if date_to:
        try:
            to_date = datetime.fromisoformat(date_to)
            qs = qs.filter(starts_at__lte=to_date)
        except ValueError:
            pass

    # Location filters (world_object-based)
    if city:
        qs = qs.filter(world_object__city__icontains=city)

    if country:
        qs = qs.filter(world_object__country__iexact=country)

    # Geographic search
    if lat is not None and lon is not None and radius_km:
        point = Point(lon, lat, srid=4326)
        qs = qs.filter(
            Q(world_object__location__distance_lte=(point, D(km=radius_km))) |
            Q(location__distance_lte=(point, D(km=radius_km)))
        )

    # Ordering: past events newest-first, upcoming/all by start date
    if time_filter == 'past':
        qs = qs.order_by('-starts_at')
    else:
        qs = qs.order_by('starts_at')

    return [_format_event_list_item(event) for event in qs]


@router.get("/events/my/", auth=ProfileAuth(), response=Dict[str, List[EventListItem]])
@ratelimit(group='events:my', key=user_or_ip, rate='30/m')
def get_my_events(request):
    """
    Get current user's events:
    - organizing: Events created by user
    - participating: Events user is registered for
    """
    from geo.models import Event, EventParticipant

    profile = request.auth

    # Events I'm organizing
    organizing = Event.objects.filter(
        organizer=profile
    ).exclude(
        status=Event.Status.CANCELLED
    ).select_related('organizer', 'organizer__instance', 'world_object', 'category', 'establishment').order_by('starts_at')

    # Events I'm participating in
    participating_ids = EventParticipant.objects.filter(
        profile=profile,
        status__in=[EventParticipant.ParticipantStatus.GOING, EventParticipant.ParticipantStatus.MAYBE]
    ).values_list('event_id', flat=True)

    participating = Event.objects.filter(
        id__in=participating_ids,
        status=Event.Status.PUBLISHED
    ).exclude(
        organizer=profile  # Don't include events I'm organizing
    ).select_related('organizer', 'organizer__instance', 'world_object', 'category', 'establishment').order_by('starts_at')

    return {
        "organizing": [_format_event_list_item(e) for e in organizing],
        "participating": [_format_event_list_item(e) for e in participating]
    }


@router.put("/events/{event_id}/", auth=ProfileAuth(), response={200: EventResponse, 400: dict, 403: dict, 404: dict})
@ratelimit(group='events:update', key=user_or_ip, rate='30/m', method='PUT')
def update_event(request, event_id: str, payload: EventInput):
    """Update event. Only organizer can update."""
    from geo.models import Event, WorldObject
    from taxonomy.models import Category

    event = get_object_or_404(Event, id=event_id)

    if event.organizer_id != request.auth.id:
        raise HttpError(403, "Only organizer can update event")

    if event.status == Event.Status.CANCELLED:
        raise HttpError(400, "Cannot update cancelled event")

    # Validate dates
    if payload.ends_at and payload.ends_at <= payload.starts_at:
        raise HttpError(400, "End time must be after start time")

    with transaction.atomic():
        world_object = None
        if payload.world_object_id:
            world_object = get_object_or_404(WorldObject, id=payload.world_object_id)

        category = None
        if payload.category_id:
            category = get_object_or_404(Category, id=payload.category_id)

        location_point = None
        if payload.location:
            location_point = Point(payload.location.longitude, payload.location.latitude, srid=4326)

        event.title = payload.title
        event.description = payload.description
        event.category = category
        event.event_type = payload.event_type
        event.starts_at = payload.starts_at
        event.ends_at = payload.ends_at
        event.timezone = payload.timezone
        event.world_object = world_object
        event.location = location_point
        event.location_name = payload.location_name or ""
        event.online_url = payload.online_url or ""
        event.max_participants = payload.max_participants
        event.cover_image_url = payload.cover_image_url or ""
        event.save()

    return _format_event_response(event, request.auth)


@router.post("/events/{event_id}/cancel/", auth=ProfileAuth(), response={200: dict, 400: dict, 403: dict, 404: dict})
@ratelimit(group='events:cancel', key=user_or_ip, rate='10/m', method='POST')
def cancel_event(request, event_id: str):
    """Cancel event. Only organizer can cancel."""
    from geo.models import Event

    event = get_object_or_404(Event, id=event_id)

    if event.organizer_id != request.auth.id:
        raise HttpError(403, "Only organizer can cancel event")

    if event.status == Event.Status.CANCELLED:
        raise HttpError(400, "Event is already cancelled")

    event.status = Event.Status.CANCELLED
    event.save(update_fields=['status'])

    # Notify participants via Matrix room
    if event.matrix_room_id:
        import threading
        def _send_cancel_notice(room_id, event_title):
            try:
                from django.conf import settings
                import httpx
                base_url = getattr(settings, 'SYNAPSE_INTERNAL_URL', 'http://localhost:8008')
                admin_token = getattr(settings, 'SYNAPSE_ADMIN_TOKEN', None)
                if not admin_token:
                    return
                with httpx.Client(timeout=10) as client:
                    client.put(
                        f"{base_url}/_matrix/client/r0/rooms/{room_id}/send/m.room.message/{__import__('uuid').uuid4()}",
                        headers={"Authorization": f"Bearer {admin_token}"},
                        json={
                            "msgtype": "m.notice",
                            "body": f"⚠️ Event \"{event_title}\" has been cancelled by the organizer."
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to send Matrix cancellation notice: {e}")
        threading.Thread(target=_send_cancel_notice, args=(event.matrix_room_id, event.title), daemon=True).start()

    return {"success": True, "message": "Event cancelled"}


@router.post("/events/{event_id}/join/", auth=ProfileAuth(), response={200: dict, 400: dict, 404: dict})
@ratelimit(group='events:join', key=user_or_ip, rate='30/m', method='POST')
def join_event(request, event_id: str, payload: JoinEventInput):
    """
    Register for event.
    Automatically joins user to event's Matrix chat room.
    """
    from geo.models import Event, EventParticipant

    event = get_object_or_404(Event, id=event_id, status=Event.Status.PUBLISHED)

    if event.organizer_id == request.auth.id:
        raise HttpError(400, "Organizer cannot join their own event as participant")

    if event.is_full() and payload.status == "GOING":
        raise HttpError(400, "Event is full")

    with transaction.atomic():
        participant, created = EventParticipant.objects.update_or_create(
            event=event,
            profile=request.auth,
            defaults={'status': payload.status}
        )

        # Update participant count
        event.participants_count = event.event_participants.filter(
            status=EventParticipant.ParticipantStatus.GOING
        ).count()
        event.save(update_fields=['participants_count'])

        # Join Matrix room if not already joined
        if event.matrix_room_id and not participant.joined_matrix_room:
            if _join_event_matrix_room(event, request.auth):
                participant.joined_matrix_room = True
                participant.save(update_fields=['joined_matrix_room'])

    return {
        "success": True,
        "status": participant.status,
        "participants_count": event.participants_count
    }


@router.post("/events/{event_id}/leave/", auth=ProfileAuth(), response={200: dict, 400: dict, 404: dict})
@ratelimit(group='events:leave', key=user_or_ip, rate='30/m', method='POST')
def leave_event(request, event_id: str):
    """Unregister from event."""
    from geo.models import Event, EventParticipant

    event = get_object_or_404(Event, id=event_id)

    participant = EventParticipant.objects.filter(
        event=event,
        profile=request.auth
    ).first()

    if not participant:
        raise HttpError(400, "Not registered for this event")

    with transaction.atomic():
        participant.status = EventParticipant.ParticipantStatus.CANCELLED
        participant.save(update_fields=['status'])

        # Update participant count
        event.participants_count = event.event_participants.filter(
            status=EventParticipant.ParticipantStatus.GOING
        ).count()
        event.save(update_fields=['participants_count'])

    return {
        "success": True,
        "participants_count": event.participants_count
    }


@router.get("/events/{event_id}/participants/", auth=None, response=List[ParticipantInfo])
@ratelimit(group='events:participants', key='ip', rate='60/m')
@paginate(PageNumberPagination, page_size=50)
def get_event_participants(request, event_id: str, status: Optional[str] = None):
    """Get list of event participants."""
    from geo.models import Event, EventParticipant

    event = get_object_or_404(Event, id=event_id)

    qs = EventParticipant.objects.filter(event=event).select_related('profile')

    if status:
        qs = qs.filter(status=status)
    else:
        # By default exclude cancelled
        qs = qs.exclude(status=EventParticipant.ParticipantStatus.CANCELLED)

    qs = qs.order_by('created_at')

    return [
        ParticipantInfo(
            id=p.id,
            profile_id=p.profile_id,
            profile_hna=p.profile.hna,
            profile_display_name=p.profile.display_name,
            profile_avatar_url=p.profile.avatar.url if p.profile.avatar else None,
            status=p.status,
            joined_at=p.created_at
        )
        for p in qs
    ]
