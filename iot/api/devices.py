"""
IoT device CRUD: create/list/get/delete, rename, manual location.
"""


from typing import List, Optional
from datetime import datetime, timezone as dt_tz
import logging
from ninja import Schema
from ninja.errors import HttpError
from django.conf import settings
from django.shortcuts import get_object_or_404
from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from core.access import ROLE_MANAGER, ROLE_OWNER, accessible_q
from ..models import IoTDevice
from ..services import TraccarService

from .access import get_device_for
from .base import router
from .mesh import _get_latest_firmware_version, ygg_inbound_status

logger = logging.getLogger(__name__)

class IoTDeviceIn(Schema):
    name: str
    device_type: str = "TRACKER"
    imei: Optional[str] = None
    device_id: Optional[str] = None  # ID устройства для Traccar
    property_id: Optional[str] = None

def _keeps_host_pass(device: IoTDevice, is_own: bool) -> bool:
    """Whether this node is what keeps its viewer-owner's mesh pass covered.

    Hosting reciprocity runs off the heartbeat (`iot/api/mesh.py`), for owned
    routers only — a router still sitting in the unclaimed fleet pool earns
    nobody anything.
    """
    return bool(
        is_own
        and device.device_type == 'MESH_ROUTER'
        and settings.MESH_HOST_PASS_DAYS
        and device.owner_id != settings.MESH_DEFAULT_OWNER_PROFILE_ID
    )


class IoTDeviceOut(Schema):
    id: str
    object_type: str = "iot_device"
    name: str
    device_type: str
    imei: Optional[str]
    device_id: Optional[str]  # ID устройства от пользователя
    traccar_device_id: Optional[int]
    property_id: Optional[str] = None
    last_seen: Optional[datetime]
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed: Optional[float] = None
    battery_level: Optional[int] = None
    last_update: Optional[datetime] = None
    connection_info: dict = {}
    latest_firmware_version: Optional[str] = None
    # Mesh routers: backend ygg:22 probe verdict. False = node heartbeats but
    # inbound is wedged (self-heal running); None = unknown / not probed.
    ygg_inbound_ok: Optional[bool] = None
    # Viewer's effective role (OWNER/MANAGER/VIEWER); shared devices carry the
    # owner reference so the UI can show who shared them.
    access_role: Optional[str] = None
    owner_hna: Optional[str] = None
    owner_name: Optional[str] = None
    # Owner attribution opt-in for the public map panel
    show_owner: bool = False
    # This node's heartbeats are what keep the viewer's own mesh pass alive
    keeps_host_pass: bool = False

    @staticmethod
    def from_orm(device: IoTDevice):
        data = {
            "id": device.id,
            "object_type": "iot_device",
            "name": device.name,
            "device_type": device.device_type,
            "imei": device.imei,
            "device_id": device.device_id,
            "traccar_device_id": device.traccar_device_id,
            "property_id": device.property_id,
            "last_seen": device.last_seen,
            "connection_info": device.connection_info or {},
            "access_role": getattr(device, 'access_role', None),
            "show_owner": device.show_owner,
        }

        # Добавляем данные о местоположении если есть
        if hasattr(device, 'current_location'):
            location = device.current_location
            data.update({
                "latitude": location.location.y if location.location else None,
                "longitude": location.location.x if location.location else None,
                "speed": location.speed,
                "battery_level": location.battery_level,
                "last_update": location.device_timestamp
            })

        # Mesh routers: use model fields for location
        if device.device_type == 'MESH_ROUTER' and data.get('latitude') is None:
            if device.latitude is not None and device.longitude is not None:
                data['latitude'] = device.latitude
                data['longitude'] = device.longitude

        # Add latest firmware version for mesh routers
        if device.device_type == 'MESH_ROUTER':
            data['latest_firmware_version'] = _get_latest_firmware_version()
            data['ygg_inbound_ok'] = ygg_inbound_status(device.device_id)

        return IoTDeviceOut(**data)

@router.post("/devices", response=IoTDeviceOut, auth=ProfileAuth())
@ratelimit(group='iot:create_device', key=user_or_ip, rate='10/m', method='POST')
def create_device(request, device_in: IoTDeviceIn):
    """Создание нового IoT устройства"""
    # Get authenticated user's profile
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")
    
    # Validate property ownership if provided
    prop = None
    if device_in.property_id:
        from iot.models import Property
        prop = Property.objects.filter(id=device_in.property_id, owner=profile).first()
        if not prop:
            raise HttpError(404, "Property not found")

    # Создаем устройство
    device = IoTDevice.objects.create(
        owner=profile,
        name=device_in.name,
        device_type=device_in.device_type,
        imei=device_in.imei,
        device_id=device_in.device_id,
        property=prop,
    )
    device.access_role = 'OWNER'

    # Trackers are registered in Traccar asynchronously by the post_save
    # signal (iot/signals.py) — traccar_device_id appears on a later fetch
    return IoTDeviceOut.from_orm(device)

@router.get("/devices", response=List[IoTDeviceOut], auth=ProfileAuth())
@ratelimit(group='iot:list_devices', key=user_or_ip, rate='60/m')
def list_devices(request, property_id: Optional[str] = None, unassigned: Optional[bool] = None):
    """Получение списка IoT устройств пользователя.

    Auto-syncs devices from Traccar DB on each request (fast — single SQL query).
    Batch-fetches latest positions for all trackers in one query.
    Filters: property_id — filter by property; unassigned=true — devices without property.
    """
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    # Auto-import devices from Traccar that don't exist in Parahub yet
    try:
        imported = TraccarService.sync_devices_from_traccar(profile)
        if imported:
            logger.info(f"Synced {imported} devices from Traccar for {profile}")
    except Exception as e:
        logger.error(f"Traccar sync failed: {e}")

    # Own devices + devices shared via ObjectAccess grants
    qs = IoTDevice.objects.filter(accessible_q(profile)).select_related('owner__instance')
    if property_id:
        qs = qs.filter(property_id=property_id)
    elif unassigned:
        qs = qs.filter(property__isnull=True)
    devices = list(qs.order_by('-created_at'))

    # Grant role per shared device (single query; owner beats any grant row)
    from core.models import ObjectAccess
    grant_roles = dict(ObjectAccess.objects.filter(
        profile=profile,
        object_id__in=[d.id for d in devices if d.owner_id != profile.id],
    ).values_list('object_id', 'role'))

    # Batch-read live positions from Redis for trackers
    tracker_ulids = [str(d.id) for d in devices if d.device_type == 'TRACKER']
    redis_positions = {}
    if tracker_ulids:
        try:
            redis_positions = TraccarService.get_positions_from_redis(tracker_ulids)
        except Exception as e:
            logger.error(f"Failed to read tracker positions from Redis: {e}")

    result = []
    for device in devices:
        is_own = device.owner_id == profile.id
        data = {
            "id": device.id,
            "object_type": "iot_device",
            "name": device.name,
            "device_type": device.device_type,
            "imei": device.imei,
            "device_id": device.device_id,
            "traccar_device_id": device.traccar_device_id,
            "property_id": device.property_id,
            "last_seen": device.last_seen,
            "connection_info": device.connection_info or {},
            "access_role": 'OWNER' if is_own else grant_roles.get(device.id, 'VIEWER'),
            "owner_hna": None if is_own else (device.owner.hna or None),
            "owner_name": None if is_own else (device.owner.display_name or device.owner.local_name),
            "keeps_host_pass": _keeps_host_pass(device, is_own),
        }

        # Inject Redis position for trackers
        dev_id = str(device.id)
        if dev_id in redis_positions:
            pos = redis_positions[dev_id]
            t = pos.get('t')
            ts = datetime.fromtimestamp(t, tz=dt_tz.utc) if t else None
            data.update({
                "latitude": pos.get('lat'),
                "longitude": pos.get('lon'),
                "speed": pos.get('spd'),
                "battery_level": pos.get('bat'),
                "last_update": ts,
            })
            # Derive last_seen from Redis (fresher than PG for active trackers)
            if ts:
                data["last_seen"] = ts
        elif device.device_type == 'MESH_ROUTER':
            if device.latitude is not None and device.longitude is not None:
                data['latitude'] = device.latitude
                data['longitude'] = device.longitude

        if device.device_type == 'MESH_ROUTER':
            data['latest_firmware_version'] = _get_latest_firmware_version()
            data['ygg_inbound_ok'] = ygg_inbound_status(device.device_id)

        result.append(IoTDeviceOut(**data))

    return result

@router.get("/devices/{device_id}", response=IoTDeviceOut, auth=ProfileAuth())
@ratelimit(group='iot:get_device', key=user_or_ip, rate='60/m')
def get_device(request, device_id: str):
    """Получение информации об IoT устройстве"""
    profile = request.auth_profile
    device = get_device_for(profile, device_id)
    is_own = device.owner_id == profile.id

    # Read live position from Redis
    data = {
        "id": device.id,
        "object_type": "iot_device",
        "name": device.name,
        "device_type": device.device_type,
        "imei": device.imei,
        "device_id": device.device_id,
        "traccar_device_id": device.traccar_device_id,
        "property_id": device.property_id,
        "last_seen": device.last_seen,
        "connection_info": device.connection_info or {},
        "access_role": device.access_role,
        "owner_hna": None if is_own else (device.owner.hna or None),
        "owner_name": None if is_own else (device.owner.display_name or device.owner.local_name),
        "keeps_host_pass": _keeps_host_pass(device, is_own),
    }

    if device.device_type == "TRACKER":
        positions = TraccarService.get_positions_from_redis([str(device.id)])
        pos = positions.get(str(device.id))
        if pos:
            t = pos.get('t')
            ts = datetime.fromtimestamp(t, tz=dt_tz.utc) if t else None
            data.update({
                "latitude": pos.get('lat'),
                "longitude": pos.get('lon'),
                "speed": pos.get('spd'),
                "battery_level": pos.get('bat'),
                "last_update": ts,
            })
            if ts:
                data["last_seen"] = ts
    elif device.device_type == 'MESH_ROUTER':
        if device.latitude is not None and device.longitude is not None:
            data['latitude'] = device.latitude
            data['longitude'] = device.longitude
        data['latest_firmware_version'] = _get_latest_firmware_version()
        data['ygg_inbound_ok'] = ygg_inbound_status(device.device_id)

    return IoTDeviceOut(**data)

@router.delete("/devices/{device_id}", auth=ProfileAuth())
@ratelimit(group='iot:delete_device', key=user_or_ip, rate='10/m', method='DELETE')
def delete_device(request, device_id: str):
    """Удаление IoT устройства"""
    device = get_device_for(request.auth_profile, device_id, ROLE_OWNER)

    # Clean up Redis tracker data
    if device.device_type == 'TRACKER':
        TraccarService.cleanup_device_redis(str(device.id))

    # Remove from Traccar first: if its row survives, the auto-sync in
    # list_devices resurrects the device on the next fetch, so a failed
    # cleanup must abort the delete instead of faking success
    if device.traccar_device_id:
        if not TraccarService.delete_device(device.traccar_device_id):
            raise HttpError(502, "Failed to remove device from Traccar, try again later")

    device.delete()
    return {"success": True}

class DeviceRenameIn(Schema):
    name: str

class DeviceRenameOut(Schema):
    status: str = "ok"
    name: str

class DeviceLocationIn(Schema):
    latitude: float
    longitude: float

class DeviceLocationOut(Schema):
    status: str = "ok"
    latitude: float
    longitude: float

@router.put("/devices/{device_id}/location", response=DeviceLocationOut, auth=ProfileAuth())
@ratelimit(group='iot:set_location', key=user_or_ip, rate='30/m', method='PUT')
def set_device_location(request, device_id: str, payload: DeviceLocationIn):
    """Set AP coordinates for coverage map."""
    device = get_device_for(request.auth_profile, device_id, ROLE_MANAGER, require_mesh=True)

    # Validate coordinate ranges
    if not (-90 <= payload.latitude <= 90) or not (-180 <= payload.longitude <= 180):
        raise HttpError(400, "Invalid coordinates")

    device.latitude = payload.latitude
    device.longitude = payload.longitude
    device.save(update_fields=['latitude', 'longitude'])

    return DeviceLocationOut(latitude=payload.latitude, longitude=payload.longitude)

@router.patch("/devices/{device_id}/rename", response=DeviceRenameOut, auth=ProfileAuth())
@ratelimit(group='iot:rename_device', key=user_or_ip, rate='10/m', method='PATCH')
def rename_device(request, device_id: str, payload: DeviceRenameIn):
    """Rename an IoT device."""
    device = get_device_for(request.auth_profile, device_id, ROLE_MANAGER)

    name = payload.name.strip()
    if len(name) < 2 or len(name) > 100:
        raise HttpError(400, "Name must be 2-100 characters")

    device.name = name
    device.save(update_fields=['name'])

    return DeviceRenameOut(name=device.name)


class MeshSettingsIn(Schema):
    # None = leave unchanged; uplink_type='' / down/up=0 = clear
    guest_rate_kbps: Optional[int] = None
    host_rate_mbps: Optional[int] = None
    uplink_type: Optional[str] = None
    uplink_down_mbps: Optional[int] = None
    uplink_up_mbps: Optional[int] = None


class MeshSettingsOut(Schema):
    status: str = "ok"
    guest_rate_kbps: int
    host_rate_mbps: int
    uplink_type: Optional[str] = None
    uplink_down_mbps: Optional[int] = None
    uplink_up_mbps: Optional[int] = None


def _mesh_settings_out(device: IoTDevice) -> MeshSettingsOut:
    return MeshSettingsOut(
        guest_rate_kbps=device.mesh_guest_rate_kbps,
        host_rate_mbps=device.mesh_host_rate_mbps,
        uplink_type=device.uplink_type,
        uplink_down_mbps=device.uplink_down_mbps,
        uplink_up_mbps=device.uplink_up_mbps,
    )


@router.get("/devices/{device_id}/mesh-settings", response=MeshSettingsOut, auth=ProfileAuth())
@ratelimit(group='iot:mesh_settings', key=user_or_ip, rate='30/m')
def get_mesh_settings(request, device_id: str):
    """Sharing budgets + declared uplink of a mesh router (DB-backed, no SSH)."""
    device = get_device_for(request.auth_profile, device_id, ROLE_MANAGER, require_mesh=True)
    if (device.connection_info or {}).get('firmware_role') != 'bumblebee':
        raise HttpError(400, "Mesh settings are only available on Bumblebee routers")
    return _mesh_settings_out(device)


@router.put("/devices/{device_id}/mesh-settings", response=MeshSettingsOut, auth=ProfileAuth())
@ratelimit(group='iot:mesh_settings_set', key=user_or_ip, rate='10/m', method='PUT')
def set_mesh_settings(request, device_id: str, payload: MeshSettingsIn):
    """Update sharing budgets / uplink passport. Budgets reach the fleet via
    the next heartbeats (≤5 min): guest_rate applies where this node
    terminates the guest VLAN, host_rate feeds the island-min host budget."""
    device = get_device_for(request.auth_profile, device_id, ROLE_MANAGER, require_mesh=True)
    if (device.connection_info or {}).get('firmware_role') != 'bumblebee':
        raise HttpError(400, "Mesh settings are only available on Bumblebee routers")

    fields = []
    if payload.guest_rate_kbps is not None:
        if not (64 <= payload.guest_rate_kbps <= 102400):
            raise HttpError(400, "guest_rate_kbps must be between 64 and 102400")
        device.mesh_guest_rate_kbps = payload.guest_rate_kbps
        fields.append('mesh_guest_rate_kbps')
    if payload.host_rate_mbps is not None:
        if not (1 <= payload.host_rate_mbps <= 10000):
            raise HttpError(400, "host_rate_mbps must be between 1 and 10000")
        device.mesh_host_rate_mbps = payload.host_rate_mbps
        fields.append('mesh_host_rate_mbps')
    if payload.uplink_type is not None:
        if payload.uplink_type == '':
            device.uplink_type = None
        elif payload.uplink_type in IoTDevice.UplinkType.values:
            device.uplink_type = payload.uplink_type
        else:
            raise HttpError(400, "Invalid uplink_type")
        fields.append('uplink_type')
    if payload.uplink_down_mbps is not None:
        if payload.uplink_down_mbps < 0 or payload.uplink_down_mbps > 100000:
            raise HttpError(400, "uplink_down_mbps out of range")
        device.uplink_down_mbps = payload.uplink_down_mbps or None
        fields.append('uplink_down_mbps')
    if payload.uplink_up_mbps is not None:
        if payload.uplink_up_mbps < 0 or payload.uplink_up_mbps > 100000:
            raise HttpError(400, "uplink_up_mbps out of range")
        device.uplink_up_mbps = payload.uplink_up_mbps or None
        fields.append('uplink_up_mbps')

    if fields:
        device.save(update_fields=fields)
    return _mesh_settings_out(device)


class DeviceShowOwnerIn(Schema):
    show_owner: bool


class DeviceShowOwnerOut(Schema):
    status: str = "ok"
    show_owner: bool


@router.patch("/devices/{device_id}/show-owner", response=DeviceShowOwnerOut, auth=ProfileAuth())
@ratelimit(group='iot:show_owner', key=user_or_ip, rate='10/m', method='PATCH')
def set_device_show_owner(request, device_id: str, payload: DeviceShowOwnerIn):
    """Toggle owner attribution on the public map panel.

    ROLE_OWNER, not MANAGER: the toggle discloses the owner's identity, so
    only the owner may consent.
    """
    device = get_device_for(request.auth_profile, device_id, ROLE_OWNER)

    device.show_owner = payload.show_owner
    device.save(update_fields=['show_owner'])

    return DeviceShowOwnerOut(show_owner=device.show_owner)
