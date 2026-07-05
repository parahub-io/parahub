"""
IoT device CRUD: create/list/get/delete, rename, manual location.
"""


from typing import List, Optional
from datetime import datetime, timezone as dt_tz
import logging
from ninja import Schema
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from ..models import IoTDevice
from ..services import TraccarService

from .base import router
from .mesh import _get_latest_firmware_version

logger = logging.getLogger(__name__)

class IoTDeviceIn(Schema):
    name: str
    device_type: str = "TRACKER"
    imei: Optional[str] = None
    device_id: Optional[str] = None  # ID устройства для Traccar
    property_id: Optional[str] = None

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
            "connection_info": device.connection_info or {}
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
    
    # Если это трекер, пробуем зарегистрировать в Traccar
    if device.device_type == "TRACKER":
        try:
            traccar_service = TraccarService()
            
            # Создаем пользователя в Traccar если нет
            if not hasattr(profile, 'traccar_account'):
                traccar_service.create_or_update_user(profile)
            
            # Регистрируем устройство
            traccar_service.register_device(device, profile.traccar_account)
            traccar_device_id = device.traccar_device_id
            
            device.traccar_device_id = traccar_device_id
            device.save()
            
        except Exception as e:
            logger.error(f"Failed to register device in Traccar: {e}")
    
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

    qs = IoTDevice.objects.filter(owner=profile)
    if property_id:
        qs = qs.filter(property_id=property_id)
    elif unassigned:
        qs = qs.filter(property__isnull=True)
    devices = list(qs.order_by('-created_at'))

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

        result.append(IoTDeviceOut(**data))

    return result

@router.get("/devices/{device_id}", response=IoTDeviceOut, auth=ProfileAuth())
@ratelimit(group='iot:get_device', key=user_or_ip, rate='60/m')
def get_device(request, device_id: str):
    """Получение информации об IoT устройстве"""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(
        IoTDevice,
        id=device_id,
        owner=profile,
    )

    # Read live position from Redis
    data = {
        "id": device.id,
        "object_type": "iot_device",
        "name": device.name,
        "device_type": device.device_type,
        "imei": device.imei,
        "device_id": device.device_id,
        "traccar_device_id": device.traccar_device_id,
        "last_seen": device.last_seen,
        "connection_info": device.connection_info or {},
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

    return IoTDeviceOut(**data)

@router.delete("/devices/{device_id}", auth=ProfileAuth())
@ratelimit(group='iot:delete_device', key=user_or_ip, rate='10/m', method='DELETE')
def delete_device(request, device_id: str):
    """Удаление IoT устройства"""
    # Get authenticated user's profile
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)

    # Clean up Redis tracker data
    if device.device_type == 'TRACKER':
        TraccarService.cleanup_device_redis(str(device.id))

    # Удаляем из Traccar если зарегистрировано
    if device.traccar_device_id:
        try:
            TraccarService.delete_device(device.traccar_device_id)
        except Exception as e:
            logger.error(f"Failed to delete device from Traccar: {e}")

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
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)

    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")

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
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)

    name = payload.name.strip()
    if len(name) < 2 or len(name) > 100:
        raise HttpError(400, "Name must be 2-100 characters")

    device.name = name
    device.save(update_fields=['name'])

    return DeviceRenameOut(name=device.name)
