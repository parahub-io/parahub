"""WorldObject get-or-create and resolve for external entities (OSM, etc.)."""
from ninja import Router, Schema
from pydantic import BaseModel
from typing import Optional
import logging

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

router = Router(tags=["Geo / World Objects"])


class WorldObjectRequest(Schema):
    xeno_source: str
    xeno_id: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    country: str = ""
    city: str = ""
    street: str = ""
    house_number: str = ""
    full_address: str = ""


class WorldObjectResponse(BaseModel):
    id: str
    object_type: str = 'world_object'
    xeno_source: str
    xeno_id: str
    created: bool
    owner_id: Optional[str] = None
    owner_name: str = ""


@router.post("/", auth=ProfileAuth(), response={200: WorldObjectResponse, 201: WorldObjectResponse, 400: dict})
@ratelimit(group='geo:world_object', key=user_or_ip, rate='20/m', method='POST')
def get_or_create_world_object(request, data: WorldObjectRequest):
    """Get or create a WorldObject for an external entity."""
    from geo.models import WorldObject
    from django.contrib.gis.geos import Point

    if not data.xeno_source or not data.xeno_id:
        return 400, {"error": "xeno_source and xeno_id are required"}

    location = None
    if data.latitude is not None and data.longitude is not None:
        location = Point(data.longitude, data.latitude, srid=4326)

    obj, created = WorldObject.objects.get_or_create(
        xeno_source=data.xeno_source,
        xeno_id=data.xeno_id,
        defaults={
            'location': location,
            'country': data.country,
            'city': data.city,
            'street': data.street,
            'house_number': data.house_number,
            'full_address': data.full_address,
        }
    )

    status = 201 if created else 200
    return status, WorldObjectResponse(
        id=obj.id,
        xeno_source=obj.xeno_source,
        xeno_id=obj.xeno_id,
        created=created,
    )


@router.get("/resolve/", auth=None, response={200: WorldObjectResponse, 404: dict})
@ratelimit(group='geo:world_object_resolve', key='ip', rate='60/m')
def resolve_world_object(request, xeno_source: str, xeno_id: str):
    """Look up a WorldObject by external identity."""
    from geo.models import WorldObject

    try:
        obj = WorldObject.objects.select_related('owner').get(xeno_source=xeno_source, xeno_id=xeno_id)
        return WorldObjectResponse(
            id=obj.id,
            xeno_source=obj.xeno_source,
            xeno_id=obj.xeno_id,
            created=False,
            owner_id=str(obj.owner_id) if obj.owner_id else None,
            owner_name=obj.owner.local_name if obj.owner else "",
        )
    except WorldObject.DoesNotExist:
        return 404, {"error": "Not found"}


class WorldObjectDetailResponse(BaseModel):
    id: str
    object_type: str = 'world_object'
    xeno_source: str
    xeno_id: str
    owner_id: Optional[str] = None
    owner_name: str = ""
    full_address: str = ""


@router.post("/{world_object_id}/claim/", auth=ProfileAuth(), response={200: WorldObjectDetailResponse, 400: dict, 404: dict, 409: dict})
@ratelimit(group='geo:world_object_claim', key=user_or_ip, rate='10/m', method='POST')
def claim_world_object(request, world_object_id: str):
    """Claim ownership of an unowned WorldObject."""
    from geo.models import WorldObject

    try:
        obj = WorldObject.objects.select_related('owner').get(id=world_object_id)
    except WorldObject.DoesNotExist:
        return 404, {"error": "Not found"}

    if obj.owner_id is not None:
        return 409, {"error": "Already owned"}

    obj.owner = request.auth
    obj.save(update_fields=['owner_id'])

    # Log ownership claim
    from core.models import OwnershipLog
    OwnershipLog.objects.create(
        object_id=world_object_id,
        action='claim',
        actor=request.auth,
        previous_owner=None,
        new_owner=request.auth,
    )

    return 200, WorldObjectDetailResponse(
        id=obj.id, xeno_source=obj.xeno_source, xeno_id=obj.xeno_id,
        owner_id=str(request.auth.id), owner_name=request.auth.local_name,
        full_address=obj.full_address,
    )


class TransferInput(Schema):
    new_owner_id: str


@router.post("/{world_object_id}/transfer/", auth=ProfileAuth(), response={200: WorldObjectDetailResponse, 400: dict, 403: dict, 404: dict})
@ratelimit(group='geo:world_object_transfer', key=user_or_ip, rate='10/m', method='POST')
def transfer_world_object(request, world_object_id: str, data: TransferInput):
    """Transfer ownership to another profile. Current owner only."""
    from geo.models import WorldObject
    from identity.models import Profile

    try:
        obj = WorldObject.objects.get(id=world_object_id)
    except WorldObject.DoesNotExist:
        return 404, {"error": "Not found"}

    if obj.owner_id != request.auth.id:
        return 403, {"error": "Only current owner can transfer"}

    try:
        new_owner = Profile.objects.get(id=data.new_owner_id)
    except Profile.DoesNotExist:
        return 400, {"error": "Target profile not found"}

    previous_owner = request.auth
    obj.owner = new_owner
    obj.save(update_fields=['owner_id'])

    # Log ownership transfer
    from core.models import OwnershipLog
    OwnershipLog.objects.create(
        object_id=world_object_id,
        action='transfer',
        actor=request.auth,
        previous_owner=previous_owner,
        new_owner=new_owner,
    )

    return 200, WorldObjectDetailResponse(
        id=obj.id, xeno_source=obj.xeno_source, xeno_id=obj.xeno_id,
        owner_id=str(new_owner.id), owner_name=new_owner.local_name,
        full_address=obj.full_address,
    )


@router.get("/{world_object_id}/contracts/", auth=OptionalProfileAuth(), response={200: list, 404: dict})
@ratelimit(group='geo:world_object_contracts', key=user_or_ip, rate='30/m')
def list_world_object_contracts(request, world_object_id: str):
    """List contracts linked to a WorldObject — private to each contract's own
    parties (creator/partner), plus staff. A P2P contract is a private commercial
    relationship, so anonymous/non-party callers get an empty list. The object's
    public ownership/transfer provenance is served separately by /activity/."""
    from django.db.models import Q
    from geo.models import WorldObject
    from contracts.models import Contract

    try:
        WorldObject.objects.get(id=world_object_id)
    except WorldObject.DoesNotExist:
        return 404, {"error": "Not found"}

    viewer = getattr(request, 'auth_profile', None)
    if viewer is None:
        return 200, []

    contracts = Contract.objects.select_related('creator', 'partner').filter(
        world_object_id=world_object_id
    )
    if not viewer.account.is_staff:
        contracts = contracts.filter(Q(creator=viewer) | Q(partner=viewer))
    contracts = contracts.order_by('-created_at')[:50]

    return 200, [
        {
            'id': c.id,
            'object_type': 'contract',
            'title': c.title,
            'status': c.status,
            'creator_name': c.creator.local_name if c.creator else '',
            'partner_name': c.partner.local_name if c.partner else '',
            'created_at': c.created_at.isoformat(),
        }
        for c in contracts
    ]


@router.get("/{world_object_id}/activity/", auth=None, response={200: list, 404: dict})
@ratelimit(group='geo:world_object_activity', key='ip', rate='30/m')
def get_world_object_activity(request, world_object_id: str, limit: int = 50):
    """Aggregate activity feed for a WorldObject (query-time)."""
    from geo.models import WorldObject
    from core.models import ObjectPhoto, ObjectComment, OwnershipLog

    try:
        WorldObject.objects.get(id=world_object_id)
    except WorldObject.DoesNotExist:
        return 404, {"error": "Not found"}

    activities = []

    for p in ObjectPhoto.objects.filter(object_id=world_object_id).select_related('uploaded_by'):
        activities.append({
            'type': 'photo',
            'id': p.id,
            'url': p.image.url if p.image else '',
            'caption': p.caption,
            'actor_name': p.uploaded_by.local_name if p.uploaded_by else '',
            'created_at': p.created_at.isoformat(),
        })

    for c in ObjectComment.objects.filter(object_id=world_object_id).select_related('author'):
        activities.append({
            'type': 'comment',
            'id': c.id,
            'text': c.text,
            'actor_name': c.author.local_name if c.author else '',
            'created_at': c.created_at.isoformat(),
        })

    for o in OwnershipLog.objects.filter(object_id=world_object_id).select_related('actor', 'new_owner', 'previous_owner'):
        activities.append({
            'type': 'ownership',
            'id': o.id,
            'action': o.action,
            'actor_name': o.actor.local_name if o.actor else '',
            'new_owner_name': o.new_owner.local_name if o.new_owner else '',
            'previous_owner_name': o.previous_owner.local_name if o.previous_owner else '',
            'created_at': o.created_at.isoformat(),
        })

    activities.sort(key=lambda x: x['created_at'], reverse=True)
    return 200, activities[:limit]
