"""Home Assistant integration endpoints."""
import logging
from typing import List, Optional
from datetime import datetime

from ninja import Router, Schema
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.utils import timezone

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from iot.models import HAHome, HAEntity, IoTDevice
from iot import ha_service

logger = logging.getLogger(__name__)
router = Router(tags=["Home Assistant"])


# ---------- Schemas ----------

class HAHomeCreateIn(Schema):
    name: str
    url: str
    access_token: str
    property_id: Optional[str] = None

class HAHomeUpdateIn(Schema):
    name: Optional[str] = None
    url: Optional[str] = None
    access_token: Optional[str] = None
    sync_interval_seconds: Optional[int] = None
    auto_import: Optional[bool] = None

class HAHomeOut(Schema):
    id: str
    object_type: str = 'ha_home'
    name: str
    url: str
    ha_version: str
    location_name: str
    latitude: Optional[float]
    longitude: Optional[float]
    status: str
    last_seen: Optional[datetime]
    last_error: str
    entity_count: int
    sync_interval_seconds: int
    auto_import: bool
    property_id: Optional[str] = None

class HATestOut(Schema):
    ok: bool
    ha_version: Optional[str] = None
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    error: Optional[str] = None

class HAEntityDiscoverOut(Schema):
    entity_id: str
    domain: str
    friendly_name: str
    state: str
    is_controllable: bool
    already_imported: bool

class HAEntityImportIn(Schema):
    entity_ids: List[str]

class HAEntityOut(Schema):
    id: str
    object_type: str = 'ha_entity'
    entity_id: str
    domain: str
    friendly_name: str
    state: str
    attributes: dict
    is_controllable: bool
    last_changed: Optional[datetime]
    last_synced: Optional[datetime]
    home_id: str
    home_name: str
    device_id: Optional[str]
    energy_signal_role: Optional[str] = None

class HAEntityUpdateIn(Schema):
    energy_signal_role: Optional[str] = None  # SURPLUS_BOOL, SURPLUS_POWER, SURPLUS_PRICE, or null to clear

class HAControlIn(Schema):
    service: str  # "turn_on", "turn_off", "set_temperature", "lock", "unlock"
    data: Optional[dict] = None  # {"brightness": 128, "color_temp": 300}

class HASyncOut(Schema):
    updated: int
    errors: int
    offline: List[str]


# ---------- Helpers ----------

def _get_home_or_404(profile, home_id: str) -> HAHome:
    home = get_object_or_404(HAHome, id=home_id)
    if home.owner_id != profile.id:
        raise HttpError(403, "Not your HA home")
    return home


def _home_to_out(home: HAHome) -> dict:
    return {
        'id': home.id,
        'object_type': 'ha_home',
        'name': home.name,
        'url': home.url,
        'ha_version': home.ha_version,
        'location_name': home.location_name,
        'latitude': home.latitude,
        'longitude': home.longitude,
        'status': home.status,
        'last_seen': home.last_seen,
        'last_error': home.last_error,
        'entity_count': home.entities.filter(is_imported=True).count(),
        'sync_interval_seconds': home.sync_interval_seconds,
        'auto_import': home.auto_import,
        'property_id': home.property_id,
    }


def _entity_to_out(entity: HAEntity) -> dict:
    return {
        'id': entity.id,
        'object_type': 'ha_entity',
        'entity_id': entity.entity_id,
        'domain': entity.domain,
        'friendly_name': entity.friendly_name,
        'state': entity.state,
        'attributes': entity.attributes_json,
        'is_controllable': entity.is_controllable,
        'last_changed': entity.last_changed,
        'last_synced': entity.last_synced,
        'home_id': entity.home_id,
        'home_name': entity.home.name,
        'device_id': entity.device_id,
        'energy_signal_role': entity.energy_signal_role,
    }


# ---------- Home CRUD ----------

@router.post("/homes", response=HAHomeOut, auth=ProfileAuth())
@ratelimit(group='ha:home_create', key=user_or_ip, rate='10/m', method='POST')
async def create_home(request, data: HAHomeCreateIn):
    """Add a Home Assistant server."""
    profile = request.auth_profile
    name = data.name.strip()[:100]
    if not name:
        raise HttpError(400, "Name is required")

    # Validate URL
    try:
        url = ha_service._validate_url(data.url)
    except ValueError as e:
        raise HttpError(400, str(e))

    # Check uniqueness
    if await HAHome.objects.filter(owner=profile, name=name).aexists():
        raise HttpError(409, f"You already have a home named '{name}'")

    # Test connection first
    result = await ha_service.test_connection(url, data.access_token)
    if not result['ok']:
        raise HttpError(400, f"Connection failed: {result['error']}")

    # Validate property ownership if provided
    prop = None
    if data.property_id:
        from iot.models import Property
        try:
            prop = await Property.objects.aget(id=data.property_id, owner=profile)
        except Property.DoesNotExist:
            raise HttpError(404, "Property not found")

    home = await HAHome.objects.acreate(
        owner=profile,
        name=name,
        url=url,
        property=prop,
        access_token_encrypted=ha_service.encrypt_token(data.access_token),
        ha_version=result.get('ha_version', ''),
        location_name=result.get('location_name', ''),
        latitude=result.get('latitude'),
        longitude=result.get('longitude'),
        status='online',
        last_seen=timezone.now(),
    )
    return _home_to_out(home)


@router.get("/homes", response=List[HAHomeOut], auth=ProfileAuth())
@ratelimit(group='ha:homes_list', key=user_or_ip, rate='60/m')
async def list_homes(request, property_id: Optional[str] = None):
    """List user's HA homes. Filter by property_id if provided."""
    profile = request.auth_profile
    qs = HAHome.objects.filter(owner=profile)
    if property_id:
        qs = qs.filter(property_id=property_id)
    homes = []
    async for home in qs:
        homes.append(_home_to_out(home))
    return homes


@router.get("/homes/{home_id}", response=HAHomeOut, auth=ProfileAuth())
@ratelimit(group='ha:home_detail', key=user_or_ip, rate='60/m')
async def get_home(request, home_id: str):
    """Get HA home details."""
    home = _get_home_or_404(request.auth_profile, home_id)
    return _home_to_out(home)


@router.patch("/homes/{home_id}", response=HAHomeOut, auth=ProfileAuth())
@ratelimit(group='ha:home_update', key=user_or_ip, rate='30/m', method='PATCH')
async def update_home(request, home_id: str, data: HAHomeUpdateIn):
    """Update HA home settings."""
    home = _get_home_or_404(request.auth_profile, home_id)
    update_fields = []

    if data.name is not None:
        name = data.name.strip()[:100]
        if name and name != home.name:
            if await HAHome.objects.filter(owner=home.owner, name=name).exclude(id=home.id).aexists():
                raise HttpError(409, f"You already have a home named '{name}'")
            home.name = name
            update_fields.append('name')

    if data.url is not None:
        try:
            home.url = ha_service._validate_url(data.url)
            update_fields.append('url')
        except ValueError as e:
            raise HttpError(400, str(e))

    if data.access_token is not None:
        home.access_token_encrypted = ha_service.encrypt_token(data.access_token)
        update_fields.append('access_token_encrypted')

    if data.sync_interval_seconds is not None:
        home.sync_interval_seconds = max(30, data.sync_interval_seconds)
        update_fields.append('sync_interval_seconds')

    if data.auto_import is not None:
        home.auto_import = data.auto_import
        update_fields.append('auto_import')

    if update_fields:
        await home.asave(update_fields=update_fields)

    return _home_to_out(home)


@router.delete("/homes/{home_id}", auth=ProfileAuth())
@ratelimit(group='ha:home_delete', key=user_or_ip, rate='10/m', method='DELETE')
async def delete_home(request, home_id: str):
    """Delete HA home and all associated entities/devices."""
    home = _get_home_or_404(request.auth_profile, home_id)

    # Delete associated IoTDevices
    entity_device_ids = []
    async for entity in HAEntity.objects.filter(home=home, device__isnull=False).select_related('device'):
        entity_device_ids.append(entity.device_id)
    if entity_device_ids:
        await IoTDevice.objects.filter(id__in=entity_device_ids).adelete()

    await home.adelete()
    return {'status': 'deleted'}


@router.post("/homes/{home_id}/test", response=HATestOut, auth=ProfileAuth())
@ratelimit(group='ha:test', key=user_or_ip, rate='10/m', method='POST')
async def test_home_connection(request, home_id: str):
    """Test connection to an existing HA home."""
    home = _get_home_or_404(request.auth_profile, home_id)
    token = ha_service.decrypt_token(home.access_token_encrypted)
    result = await ha_service.test_connection(home.url, token)

    if result['ok']:
        home.status = 'online'
        home.last_seen = timezone.now()
        home.last_error = ''
        home.ha_version = result.get('ha_version', home.ha_version)
        home.location_name = result.get('location_name', home.location_name)
        home.latitude = result.get('latitude', home.latitude)
        home.longitude = result.get('longitude', home.longitude)
        await home.asave(update_fields=[
            'status', 'last_seen', 'last_error', 'ha_version',
            'location_name', 'latitude', 'longitude',
        ])
    else:
        home.status = 'error' if 'token' in result.get('error', '').lower() else 'offline'
        home.last_error = result.get('error', '')[:500]
        await home.asave(update_fields=['status', 'last_error'])

    return result


# ---------- Entity Listing, Discovery & Import ----------

@router.get("/homes/{home_id}/entities", response=List[HAEntityOut], auth=ProfileAuth())
@ratelimit(group='ha:entities_list', key=user_or_ip, rate='60/m')
async def list_entities(request, home_id: str):
    """List imported entities for a home."""
    home = _get_home_or_404(request.auth_profile, home_id)
    entities = []
    async for e in HAEntity.objects.filter(home=home, is_imported=True).select_related('home'):
        entities.append(_entity_to_out(e))
    return entities


@router.get("/homes/{home_id}/discover", response=List[HAEntityDiscoverOut], auth=ProfileAuth())
@ratelimit(group='ha:discover', key=user_or_ip, rate='10/m')
async def discover_entities(request, home_id: str):
    """Discover all entities from HA (GET /api/states)."""
    home = _get_home_or_404(request.auth_profile, home_id)
    token = ha_service.decrypt_token(home.access_token_encrypted)

    try:
        states = await ha_service.fetch_states(home.url, token)
    except Exception as e:
        raise HttpError(502, f"Failed to fetch HA states: {e}")

    # Get already-imported entity_ids
    imported_ids = set()
    async for eid in HAEntity.objects.filter(home=home).values_list('entity_id', flat=True):
        imported_ids.add(eid)

    result = []
    for s in states:
        eid = s.get('entity_id', '')
        domain = eid.split('.')[0] if '.' in eid else ''
        friendly = s.get('attributes', {}).get('friendly_name', eid)
        result.append({
            'entity_id': eid,
            'domain': domain,
            'friendly_name': friendly,
            'state': str(s.get('state', '')),
            'is_controllable': ha_service.determine_controllability(domain),
            'already_imported': eid in imported_ids,
        })

    # Sort by domain then name
    result.sort(key=lambda x: (x['domain'], x['friendly_name']))
    return result


@router.post("/homes/{home_id}/import", auth=ProfileAuth())
@ratelimit(group='ha:import', key=user_or_ip, rate='10/m', method='POST')
async def import_entities(request, home_id: str, data: HAEntityImportIn):
    """Import selected entities from HA into Parahub."""
    home = _get_home_or_404(request.auth_profile, home_id)
    profile = request.auth_profile

    if not data.entity_ids:
        raise HttpError(400, "No entity IDs provided")

    # Fetch current states to populate initial data
    token = ha_service.decrypt_token(home.access_token_encrypted)
    try:
        states = await ha_service.fetch_states(home.url, token)
    except Exception as e:
        raise HttpError(502, f"Failed to fetch HA states: {e}")

    state_map = {s['entity_id']: s for s in states}
    now = timezone.now()
    imported = 0

    for eid in data.entity_ids:
        # Skip already imported
        if await HAEntity.objects.filter(home=home, entity_id=eid).aexists():
            continue

        ha_state = state_map.get(eid)
        if ha_state is None:
            continue

        domain = eid.split('.')[0] if '.' in eid else ''
        friendly = ha_state.get('attributes', {}).get('friendly_name', eid)
        is_ctrl = ha_service.determine_controllability(domain)
        device_type = ha_service.map_domain_to_device_type(domain)

        # Create IoTDevice
        iot_device = await IoTDevice.objects.acreate(
            owner=profile,
            name=friendly[:100],
            device_type=device_type,
        )

        # Parse last_changed
        lc = ha_state.get('last_changed')
        last_changed = None
        if lc:
            try:
                last_changed = datetime.fromisoformat(lc.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                pass

        # Create HAEntity
        await HAEntity.objects.acreate(
            home=home,
            device=iot_device,
            entity_id=eid,
            domain=domain,
            friendly_name=friendly[:255],
            state=str(ha_state.get('state', ''))[:255],
            attributes_json=ha_state.get('attributes', {}),
            last_changed=last_changed,
            last_synced=now,
            is_imported=True,
            is_controllable=is_ctrl,
        )
        imported += 1

    return {'imported': imported}


@router.patch("/entities/{entity_id}", response=HAEntityOut, auth=ProfileAuth())
@ratelimit(group='ha:entity_update', key=user_or_ip, rate='30/m', method='PATCH')
async def update_entity(request, entity_id: str, data: HAEntityUpdateIn):
    """Update entity settings (e.g. energy signal role)."""
    entity = get_object_or_404(HAEntity.objects.select_related('home'), id=entity_id)
    if entity.home.owner_id != request.auth_profile.id:
        raise HttpError(403, "Not your entity")

    valid_roles = {c.value for c in HAEntity.EnergySignalRole}
    role = data.energy_signal_role
    if role is not None and role not in valid_roles:
        raise HttpError(400, f"Invalid energy_signal_role. Must be one of: {', '.join(valid_roles)}")

    entity.energy_signal_role = role
    await entity.asave(update_fields=['energy_signal_role'])
    return _entity_to_out(entity)


@router.delete("/entities/{entity_id}", auth=ProfileAuth())
@ratelimit(group='ha:entity_delete', key=user_or_ip, rate='30/m', method='DELETE')
async def delete_entity(request, entity_id: str):
    """Remove an imported entity from Parahub (not from HA)."""
    entity = get_object_or_404(HAEntity, id=entity_id)
    if entity.home.owner_id != request.auth_profile.id:
        raise HttpError(403, "Not your entity")

    # Delete associated IoTDevice
    if entity.device_id:
        await IoTDevice.objects.filter(id=entity.device_id).adelete()

    await entity.adelete()
    return {'status': 'deleted'}


# ---------- Entity State & Control ----------

@router.get("/entities/{entity_id}/state", response=HAEntityOut, auth=ProfileAuth())
@ratelimit(group='ha:entity_state', key=user_or_ip, rate='60/m')
async def get_entity_state(request, entity_id: str):
    """Get fresh state of an entity (direct HA query)."""
    entity = get_object_or_404(HAEntity.objects.select_related('home'), id=entity_id)
    if entity.home.owner_id != request.auth_profile.id:
        raise HttpError(403, "Not your entity")

    token = ha_service.decrypt_token(entity.home.access_token_encrypted)
    try:
        state_data = await ha_service.get_entity_state(entity.home.url, token, entity.entity_id)
    except Exception as e:
        raise HttpError(502, f"Failed to query HA: {e}")

    # Update cached state
    now = timezone.now()
    entity.state = str(state_data.get('state', ''))[:255]
    entity.attributes_json = state_data.get('attributes', {})
    entity.friendly_name = state_data.get('attributes', {}).get('friendly_name', entity.friendly_name)[:255]
    lc = state_data.get('last_changed')
    if lc:
        try:
            entity.last_changed = datetime.fromisoformat(lc.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            pass
    entity.last_synced = now
    await entity.asave(update_fields=[
        'state', 'attributes_json', 'friendly_name', 'last_changed', 'last_synced',
    ])

    return _entity_to_out(entity)


@router.post("/entities/{entity_id}/control", auth=ProfileAuth())
@ratelimit(group='ha:control', key=user_or_ip, rate='30/m', method='POST')
async def control_entity(request, entity_id: str, data: HAControlIn):
    """Control an entity (turn on/off, set temperature, etc.)."""
    entity = get_object_or_404(HAEntity.objects.select_related('home'), id=entity_id)
    if entity.home.owner_id != request.auth_profile.id:
        raise HttpError(403, "Not your entity")
    if not entity.is_controllable:
        raise HttpError(400, "This entity is not controllable")

    token = ha_service.decrypt_token(entity.home.access_token_encrypted)
    try:
        await ha_service.call_service(
            entity.home.url, token, entity.domain, data.service,
            entity.entity_id, data.data,
        )
    except Exception as e:
        raise HttpError(502, f"HA service call failed: {e}")

    # Refresh state after control
    try:
        state_data = await ha_service.get_entity_state(entity.home.url, token, entity.entity_id)
        entity.state = str(state_data.get('state', ''))[:255]
        entity.attributes_json = state_data.get('attributes', {})
        entity.last_synced = timezone.now()
        await entity.asave(update_fields=['state', 'attributes_json', 'last_synced'])
    except Exception:
        pass  # Non-critical: state refresh can fail

    return {'status': 'ok', 'new_state': entity.state}


@router.post("/homes/{home_id}/sync", response=HASyncOut, auth=ProfileAuth())
@ratelimit(group='ha:sync', key=user_or_ip, rate='10/m', method='POST')
async def sync_home(request, home_id: str):
    """Manual sync of all imported entities for a home."""
    home = _get_home_or_404(request.auth_profile, home_id)
    result = await ha_service.sync_home_entities(home)
    return result
