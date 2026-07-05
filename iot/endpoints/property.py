"""Property (My Home) endpoints."""
import logging
from typing import List, Optional
from datetime import datetime

from ninja import Router, Schema
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.contrib.gis.geos import Point, Polygon
from django.db.models import Count, Q

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from iot.models import Property

logger = logging.getLogger(__name__)
router = Router(tags=["Property"])


# ---------- Schemas ----------

class PropertyCreateIn(Schema):
    name: str
    property_type: str = 'house'
    world_object_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    territory: Optional[dict] = None  # GeoJSON Polygon
    address: Optional[str] = None

class PropertyUpdateIn(Schema):
    name: Optional[str] = None
    property_type: Optional[str] = None
    world_object_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    territory: Optional[dict] = None
    address: Optional[str] = None

class PropertyOut(Schema):
    id: str
    object_type: str = 'property'
    name: str
    property_type: str
    address: str
    latitude: float
    longitude: float
    has_territory: bool
    world_object_id: Optional[str]
    world_object_address: Optional[str]
    device_count: int
    ha_home_count: int
    ha_entity_count: int
    mesh_count: int
    tracker_count: int
    energy_producer_count: int
    energy_consumer_count: int
    created_at: datetime

class PropertyMapOut(Schema):
    id: str
    name: str
    property_type: str
    latitude: float
    longitude: float
    territory: Optional[dict] = None


# ---------- Helpers ----------

def _property_annotations():
    """Annotations for batch-loading property counts in list queries."""
    return dict(
        _device_count=Count('devices', distinct=True),
        _ha_home_count=Count('ha_homes', distinct=True),
        _ha_entity_count=Count(
            'ha_homes__entities',
            filter=Q(ha_homes__entities__is_imported=True),
            distinct=True,
        ),
        _mesh_count=Count(
            'devices',
            filter=Q(devices__device_type='MESH_ROUTER'),
            distinct=True,
        ),
        _tracker_count=Count(
            'devices',
            filter=Q(devices__device_type='TRACKER'),
            distinct=True,
        ),
        _energy_producer_count=Count('energy_producers', distinct=True),
        _energy_consumer_count=Count('energy_consumers', distinct=True),
    )


def _serialize_property(prop: Property) -> dict:
    # Use pre-annotated counts if available (list endpoint), else query (single object)
    device_count = getattr(prop, '_device_count', None)
    if device_count is None:
        # Fallback for single-object calls (create, update, detail)
        ha_homes = prop.ha_homes.all()
        from iot.models import HAEntity
        return {
            'id': prop.id,
            'object_type': 'property',
            'name': prop.name,
            'property_type': prop.property_type,
            'address': prop.address,
            'latitude': prop.location.y,
            'longitude': prop.location.x,
            'has_territory': prop.territory is not None,
            'world_object_id': prop.world_object_id,
            'world_object_address': prop.world_object.full_address if prop.world_object else None,
            'device_count': prop.devices.count(),
            'ha_home_count': ha_homes.count(),
            'ha_entity_count': HAEntity.objects.filter(home__in=ha_homes, is_imported=True).count(),
            'mesh_count': prop.devices.filter(device_type='MESH_ROUTER').count(),
            'tracker_count': prop.devices.filter(device_type='TRACKER').count(),
            'energy_producer_count': prop.energy_producers.count(),
            'energy_consumer_count': prop.energy_consumers.count(),
            'created_at': prop.created_at,
        }

    return {
        'id': prop.id,
        'object_type': 'property',
        'name': prop.name,
        'property_type': prop.property_type,
        'address': prop.address,
        'latitude': prop.location.y,
        'longitude': prop.location.x,
        'has_territory': prop.territory is not None,
        'world_object_id': prop.world_object_id,
        'world_object_address': prop.world_object.full_address if prop.world_object else None,
        'device_count': prop._device_count,
        'ha_home_count': prop._ha_home_count,
        'ha_entity_count': prop._ha_entity_count,
        'mesh_count': prop._mesh_count,
        'tracker_count': prop._tracker_count,
        'energy_producer_count': prop._energy_producer_count,
        'energy_consumer_count': prop._energy_consumer_count,
        'created_at': prop.created_at,
    }


def _parse_territory(geojson: dict) -> Polygon:
    """Parse GeoJSON Polygon to Django Polygon."""
    if geojson.get('type') != 'Polygon' or not geojson.get('coordinates'):
        raise HttpError(400, "territory must be a GeoJSON Polygon")
    try:
        return Polygon(geojson['coordinates'][0], srid=4326)
    except Exception:
        raise HttpError(400, "Invalid polygon coordinates")


# ---------- Endpoints ----------

@router.post("/", response=PropertyOut, auth=ProfileAuth())
@ratelimit(group='property:create', key=user_or_ip, rate='10/m', method='POST')
def create_property(request, data: PropertyCreateIn):
    profile = request.auth_profile
    building = None

    if data.world_object_id:
        from geo.models import WorldObject
        world_object = get_object_or_404(WorldObject, id=data.world_object_id)
        location = world_object.location
        address = data.address or world_object.full_address
    elif data.latitude is not None and data.longitude is not None:
        world_object = None
        location = Point(data.longitude, data.latitude, srid=4326)
        address = data.address or ''
    else:
        raise HttpError(400, "Provide world_object_id or latitude+longitude")

    territory = _parse_territory(data.territory) if data.territory else None

    valid_types = [c[0] for c in Property.PropertyType.choices]
    if data.property_type not in valid_types:
        raise HttpError(400, f"Invalid property_type. Choose from: {', '.join(valid_types)}")

    prop = Property.objects.create(
        owner=profile,
        name=data.name,
        world_object=world_object,
        location=location,
        territory=territory,
        address=address,
        property_type=data.property_type,
    )
    return _serialize_property(prop)


@router.get("/", response=List[PropertyOut], auth=ProfileAuth())
@ratelimit(group='property:list', key=user_or_ip, rate='60/m')
def list_properties(request):
    profile = request.auth_profile
    props = Property.objects.filter(owner=profile).select_related('world_object').annotate(
        **_property_annotations()
    )
    return [_serialize_property(p) for p in props]


@router.get("/map/", response=List[PropertyMapOut], auth=ProfileAuth())
@ratelimit(group='property:map', key=user_or_ip, rate='60/m')
def properties_map(request):
    """GeoJSON-ready data for map layer (own properties only)."""
    profile = request.auth_profile
    props = Property.objects.filter(owner=profile)
    result = []
    for p in props:
        territory = None
        if p.territory:
            territory = {
                'type': 'Polygon',
                'coordinates': [list(p.territory.coords[0])],
            }
        result.append({
            'id': p.id,
            'name': p.name,
            'property_type': p.property_type,
            'latitude': p.location.y,
            'longitude': p.location.x,
            'territory': territory,
        })
    return result


@router.get("/{property_id}/", response=PropertyOut, auth=ProfileAuth())
@ratelimit(group='property:detail', key=user_or_ip, rate='60/m')
def get_property(request, property_id: str):
    prop = get_object_or_404(Property, id=property_id)
    if prop.owner_id != request.auth_profile.id:
        raise HttpError(403, "Not your property")
    return _serialize_property(prop)


@router.patch("/{property_id}/", response=PropertyOut, auth=ProfileAuth())
@ratelimit(group='property:update', key=user_or_ip, rate='30/m', method='PATCH')
def update_property(request, property_id: str, data: PropertyUpdateIn):
    prop = get_object_or_404(Property, id=property_id)
    if prop.owner_id != request.auth_profile.id:
        raise HttpError(403, "Not your property")

    if data.name is not None:
        prop.name = data.name
    if data.property_type is not None:
        valid_types = [c[0] for c in Property.PropertyType.choices]
        if data.property_type not in valid_types:
            raise HttpError(400, f"Invalid property_type")
        prop.property_type = data.property_type
    if data.address is not None:
        prop.address = data.address
    if data.world_object_id is not None:
        from geo.models import WorldObject
        if data.world_object_id == '':
            prop.world_object = None
        else:
            prop.world_object = get_object_or_404(WorldObject, id=data.world_object_id)
            prop.location = prop.world_object.location
            if not data.address:
                prop.address = prop.world_object.full_address
    if data.latitude is not None and data.longitude is not None:
        prop.location = Point(data.longitude, data.latitude, srid=4326)
    if data.territory is not None:
        prop.territory = _parse_territory(data.territory)

    prop.save()
    return _serialize_property(prop)


@router.delete("/{property_id}/", auth=ProfileAuth())
@ratelimit(group='property:delete', key=user_or_ip, rate='10/m', method='DELETE')
def delete_property(request, property_id: str):
    prop = get_object_or_404(Property, id=property_id)
    if prop.owner_id != request.auth_profile.id:
        raise HttpError(403, "Not your property")
    prop.delete()
    return {"ok": True}


# ---------- Household members (civic polls audience — PK/civic-polls-system.md) ----------

class HouseholdMemberOut(Schema):
    profile_id: str
    hna: str
    display_name: str = ''
    role: str
    is_owner: bool = False
    created_at: Optional[datetime] = None


def _require_household_access(prop: Property, profile) -> bool:
    """Owner or member."""
    if prop.owner_id == profile.id:
        return True
    from iot.models import PropertyMember
    return PropertyMember.objects.filter(property=prop, profile=profile).exists()


@router.get("/{property_id}/household/", response=List[HouseholdMemberOut], auth=ProfileAuth())
@ratelimit(group='property:household', key=user_or_ip, rate='30/m')
def list_household(request, property_id: str):
    from iot.models import PropertyMember
    prop = get_object_or_404(Property, id=property_id)
    if not _require_household_access(prop, request.auth_profile):
        raise HttpError(403, "Not a member of this household")
    out = [HouseholdMemberOut(
        profile_id=prop.owner.id, hna=prop.owner.hna,
        display_name=prop.owner.display_name or '', role='owner', is_owner=True,
        created_at=prop.created_at,
    )]
    for m in PropertyMember.objects.filter(property=prop).select_related('profile'):
        out.append(HouseholdMemberOut(
            profile_id=m.profile.id, hna=m.profile.hna,
            display_name=m.profile.display_name or '', role=m.role,
            created_at=m.created_at,
        ))
    return out


@router.post("/{property_id}/household/invite/", auth=ProfileAuth())
@ratelimit(group='property:household_invite', key=user_or_ip, rate='10/m', method='POST')
def create_household_invite(request, property_id: str):
    """Generate (or rotate) the household invite token. Owner only.
    Rotating invalidates previously shared links."""
    import secrets
    prop = get_object_or_404(Property, id=property_id)
    if prop.owner_id != request.auth_profile.id:
        raise HttpError(403, "Only the owner can invite household members")
    prop.household_invite_token = secrets.token_urlsafe(32)
    prop.save(update_fields=['household_invite_token'])
    return {"token": prop.household_invite_token}


@router.post("/household/join/", auth=ProfileAuth())
@ratelimit(group='property:household_join', key=user_or_ip, rate='10/m', method='POST')
def join_household(request, token: str):
    """Join a household via invite token."""
    from iot.models import PropertyMember
    profile = request.auth_profile
    prop = Property.objects.filter(household_invite_token=token).select_related('owner').first()
    if not prop or not token:
        raise HttpError(404, "Invite not found or revoked")
    if prop.owner_id == profile.id:
        return {"property_id": prop.id, "property_name": prop.name, "joined": False, "already": True}
    _, created = PropertyMember.objects.get_or_create(
        property=prop, profile=profile,
        defaults={'invited_by': prop.owner},
    )
    # Keep active household polls' audience in sync immediately
    try:
        from governance.civic import sync_context_audience_polls
        sync_context_audience_polls('household', prop.id)
    except Exception:
        pass
    return {"property_id": prop.id, "property_name": prop.name, "joined": True, "already": not created}


@router.delete("/{property_id}/household/{profile_id}/", auth=ProfileAuth())
@ratelimit(group='property:household_remove', key=user_or_ip, rate='20/m', method='DELETE')
def remove_household_member(request, property_id: str, profile_id: str):
    """Owner removes a member, or a member leaves (profile_id == own id)."""
    from iot.models import PropertyMember
    prop = get_object_or_404(Property, id=property_id)
    requester = request.auth_profile
    if requester.id != profile_id and prop.owner_id != requester.id:
        raise HttpError(403, "Only the owner can remove other members")
    deleted, _ = PropertyMember.objects.filter(property=prop, profile_id=profile_id).delete()
    if deleted:
        try:
            from governance.civic import sync_context_audience_polls
            sync_context_audience_polls('household', prop.id)
        except Exception:
            pass
    return {"removed": bool(deleted)}
