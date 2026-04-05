from typing import List, Optional
from datetime import datetime, timezone as dt_tz
import json as _json_module
import logging
import os
import subprocess
import shlex
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from ninja import Router, Schema
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.contrib.gis.geos import Point
from django.core import signing
from django.http import HttpResponse
from django.utils.crypto import get_random_string
from django.core.cache import cache
from django.utils import timezone
from django.http import HttpRequest
from parahub.auth import ProfileAuth, GlobalAuth
from parahub.ratelimit import ratelimit, user_or_ip
from django.conf import settings
from parahub.middleware.pgp import PGPSignatureAuth
from datetime import timedelta
from .models import IoTDevice, TrackerLocation, TraccarUser, MeshSubscription
from .services import TraccarService
from identity.models import Profile
from ads.ln_wallet_service import LNbitsProvider

from iot.endpoints.dispatch import router as dispatch_router
from iot.endpoints.ha import router as ha_router
from iot.endpoints.history import router as history_router
from iot.endpoints.property import router as property_router

logger = logging.getLogger(__name__)
router = Router(tags=["IoT"])
router.add_router("/dispatch", dispatch_router)
router.add_router("/ha", ha_router)
router.add_router("", history_router)
router.add_router("/properties", property_router)

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

class TraccarCredentialsOut(Schema):
    username: str  # Deprecated: use login_email instead
    login_email: str  # The actual email to use for Traccar login
    password: str
    traccar_url: str = "https://traccar.parahub.io"
    has_account: bool

class TraccarSSOTicketOut(Schema):
    url: str
    expires_in: int = 60  # seconds

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

@router.get("/traccar/credentials", response=TraccarCredentialsOut, auth=ProfileAuth())
@ratelimit(group='iot:traccar_credentials', key=user_or_ip, rate='10/m')
def get_traccar_credentials(request):
    """Получение учетных данных для Traccar - автоматически создает аккаунт если его нет"""
    # Get authenticated user's profile
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")
    
    # Проверяем есть ли аккаунт, если нет - создаем автоматически
    try:
        # Попытка получить существующий аккаунт
        traccar_account = profile.traccar_account
    except TraccarUser.DoesNotExist:
        # Аккаунта нет, пытаемся создать автоматически
        try:
            traccar_service = TraccarService()
            traccar_service.create_or_update_user(profile)
            # Обновляем объект профиля из БД чтобы получить новую связь
            profile.refresh_from_db()
            traccar_account = profile.traccar_account
        except Exception as e:
            logger.error(f"Failed to create Traccar user: {e}")
            raise HttpError(503, f"Не удалось создать аккаунт в Traccar: {str(e)}")
    
    # Расшифровываем пароль для отображения пользователю
    try:
        decrypted_password = TraccarService.decrypt_password(traccar_account.traccar_password_encrypted)
    except Exception as e:
        logger.error(f"Failed to decrypt Traccar password: {e}")
        decrypted_password = "Ошибка получения пароля"
    
    # Compute the login email from username + domain
    login_email = f"{traccar_account.traccar_username}@{settings.TRACCAR_EMAIL_DOMAIN}"
    
    return TraccarCredentialsOut(
        username=traccar_account.traccar_username,  # Deprecated
        login_email=login_email,  # Use this for Traccar login
        password=decrypted_password,
        has_account=True
    )

# Ticket endpoint removed - now using OAuth2/OIDC flow directly

@router.get("/traccar/sso-redirect")
@ratelimit(group='iot:traccar_sso', key='ip', rate='30/m')
def traccar_sso_redirect(request):
    """Инициирует OAuth2 flow для Traccar через OIDC"""
    from django.http import HttpResponseRedirect
    from urllib.parse import urlencode
    import hashlib
    import time
    
    # Генерируем state для защиты от CSRF
    # Используем hash от времени и случайной строки
    state_source = f"{time.time()}:{get_random_string(16)}"
    state = hashlib.sha256(state_source.encode()).hexdigest()[:32]
    
    # Параметры для OAuth2 авторизации
    params = {
        'response_type': 'code',
        'client_id': 'traccar-sso-client',
        'redirect_uri': 'https://traccar.parahub.io/api/session/openid/callback',
        'scope': 'openid profile email groups',
        'state': state,
    }
    
    # Редирект на OAuth2 authorize endpoint
    authorize_url = f"https://parahub.io/o/authorize/?{urlencode(params)}"
    return HttpResponseRedirect(authorize_url)


# ============================================================================
# Traccar Webhook (position forwarding)
# ============================================================================

_TRACCAR_ALLOWED_NETS = ('127.', '::1', '172.', '10.', '192.168.')

@router.post("/webhook/traccar", auth=None)
@ratelimit(group='iot:webhook', key='ip', rate='600/m')
def traccar_webhook(request: HttpRequest):
    """Receive position updates from Traccar event forwarding.

    Configured in traccar.xml via event.forward.url.
    Only accessible from localhost / Docker internal network.
    """
    import json as _json

    # Restrict to localhost / internal networks only
    client_ip = (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
        or request.META.get('REMOTE_ADDR', '')
    )
    if not any(client_ip.startswith(prefix) for prefix in _TRACCAR_ALLOWED_NETS):
        raise HttpError(403, "Forbidden")

    try:
        data = _json.loads(request.body)
    except (ValueError, TypeError):
        raise HttpError(400, "Invalid JSON")

    success = TraccarService.process_position_redis(data)
    return {"processed": success}


# ============================================================================
# Tracker positions for map
# ============================================================================

class TrackerPositionOut(Schema):
    device_id: str
    name: str
    latitude: float
    longitude: float
    speed: Optional[float] = None
    heading: Optional[float] = None
    battery_level: Optional[int] = None
    last_update: Optional[datetime] = None
    traccar_status: Optional[str] = None


@router.get("/tracker-positions", response=List[TrackerPositionOut], auth=ProfileAuth())
@ratelimit(group='iot:tracker_positions', key=user_or_ip, rate='60/m')
def get_tracker_positions(request):
    """Get all tracker positions for the authenticated user (from Redis)."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    devices = list(
        IoTDevice.objects.filter(
            owner=profile,
            device_type='TRACKER',
        ).values_list('id', 'name')
    )

    if not devices:
        return []

    device_ids = [str(d[0]) for d in devices]
    device_names = {str(d[0]): d[1] for d in devices}

    # Read live positions from Redis
    positions = TraccarService.get_positions_from_redis(device_ids)

    import time as _time
    now_epoch = int(_time.time())

    result = []
    for dev_id, pos in positions.items():
        lat = pos.get('lat')
        lon = pos.get('lon')
        if lat and lon:
            t = pos.get('t')
            # Derive status from age: <120s = online, <600s = unknown, else offline
            age = (now_epoch - t) if t else 999999
            status = 'online' if age < 120 else ('unknown' if age < 600 else 'offline')
            result.append(TrackerPositionOut(
                device_id=dev_id,
                name=device_names.get(dev_id, pos.get('name', '')),
                latitude=lat,
                longitude=lon,
                speed=pos.get('spd'),
                heading=pos.get('hdg'),
                battery_level=pos.get('bat'),
                last_update=datetime.fromtimestamp(t, tz=dt_tz.utc) if t else None,
                traccar_status=status,
            ))

    return result


# ============================================================================
# Mesh Router Endpoints
# ============================================================================

class MullvadStatusOut(Schema):
    mode: str  # "mullvad" or "vps"
    account: Optional[str] = None  # masked account number
    country: Optional[str] = None
    server: Optional[str] = None
    server_ip: Optional[str] = None
    local_ip: Optional[str] = None


class MullvadSetupIn(Schema):
    account_key: str
    country: str = ""


class MullvadSetupOut(Schema):
    status: str = "ok"
    mode: str = "mullvad"
    country: Optional[str] = None
    server: Optional[str] = None


class MullvadRemoveOut(Schema):
    status: str = "ok"
    mode: str = "vps"


class SpeedLimitStatusOut(Schema):
    enabled: bool


class SpeedLimitToggleIn(Schema):
    enabled: bool


class SpeedLimitToggleOut(Schema):
    status: str = "ok"
    enabled: bool


class LanVpnStatusOut(Schema):
    enabled: bool


class LanVpnToggleIn(Schema):
    enabled: bool


class LanVpnToggleOut(Schema):
    status: str = "ok"
    enabled: bool


class WiredMeshStatusOut(Schema):
    enabled: bool


class WiredMeshToggleIn(Schema):
    enabled: bool


class WiredMeshToggleOut(Schema):
    status: str = "ok"
    enabled: bool


class MeshHeartbeatIn(Schema):
    mac: str
    hostname: str
    yggdrasil_address: str = "unknown"
    firmware_version: str = "unknown"
    hardware_profile: str = "unknown"
    uptime: int = 0
    private_ssid: str = "unknown"
    firmware_role: str = "unknown"
    mesh_ip: str = "unknown"
    wg_public_key: str = ""
    vpn_mode: str = "unknown"


class VpsGatewayConfig(Schema):
    endpoint: str
    public_key: str
    assigned_ip: str  # with /16 mask
    keepalive: int = 25


class MeshHeartbeatOut(Schema):
    status: str = "ok"
    device_id: str
    paid_clients: List[str] = []
    ygg_allowed: List[str] = []
    vps_gateway: Optional[VpsGatewayConfig] = None


class WifiPasswordOut(Schema):
    wifi_password: str
    ssid: str


class RootPasswordOut(Schema):
    root_password: str
    hostname: str


MAC_RE = re.compile(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$')

# Valid Yggdrasil address pattern (200:xxxx:... or 300:xxxx:...)
_YGG_ADDR_RE = re.compile(r'^[23]0[0-9a-f]:[0-9a-f:]+$')

# Base64-encoded WireGuard public key (44 chars)
_WG_KEY_RE = re.compile(r'^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=?$')


_MESH_MANIFEST_PATH = '/opt/parahub-mesh/output/manifest.json'


def _get_latest_firmware_version() -> Optional[str]:
    """Read latest firmware version from manifest.json, cached for 5 min."""
    cached = cache.get('mesh_latest_firmware_version')
    if cached is not None:
        return cached
    try:
        with open(_MESH_MANIFEST_PATH) as f:
            manifest = _json_module.load(f)
        version = manifest.get('version')
        if version:
            cache.set('mesh_latest_firmware_version', version, 300)
        return version
    except Exception:
        return None


class DeviceRenameIn(Schema):
    name: str


class DeviceRenameOut(Schema):
    status: str = "ok"
    name: str


def _allocate_wg_ip() -> str:
    """Allocate next available IP from 10.99.0.2 - 10.99.255.254 pool."""
    from django.db.models import Max
    max_ip = IoTDevice.objects.filter(wg_ip__isnull=False).aggregate(Max('wg_ip'))['wg_ip__max']
    if max_ip:
        parts = max_ip.split('.')
        current = int(parts[2]) * 256 + int(parts[3])
        next_val = current + 1
        # Skip .0 and .255 in last octet
        o3 = next_val // 256
        o4 = next_val % 256
        if o4 == 0:
            next_val += 1
            o3 = next_val // 256
            o4 = next_val % 256
        if o4 == 255:
            next_val += 1
            o3 = next_val // 256
            o4 = next_val % 256
        if o3 > 255:
            raise HttpError(503, "WireGuard IP pool exhausted")
        return f"10.99.{o3}.{o4}"
    return "10.99.0.2"


def _mesh_ssh(ygg_addr: str, command: str, timeout: int = None) -> subprocess.CompletedProcess:
    """Execute a command on a mesh router via SSH over Yggdrasil."""
    ssh_timeout = timeout or settings.MESH_SSH_TIMEOUT
    return subprocess.run(
        [
            'ssh',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', f'ConnectTimeout={ssh_timeout}',
            '-i', settings.MESH_SSH_KEY_PATH,
            f'root@{ygg_addr}',
            command,
        ],
        capture_output=True,
        text=True,
        timeout=ssh_timeout + 2,
    )


@router.post("/mesh/heartbeat", response=MeshHeartbeatOut, auth=None)
@ratelimit(group='mesh:heartbeat', key='ip', rate='30/m')
def mesh_heartbeat(request: HttpRequest, payload: MeshHeartbeatIn):
    """Phone-home heartbeat from mesh routers (authenticated via shared key)."""
    # Validate Bearer token
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        raise HttpError(401, "Missing Bearer token")

    token = auth_header[7:]
    if not settings.MESH_HEARTBEAT_KEY or token != settings.MESH_HEARTBEAT_KEY:
        raise HttpError(403, "Invalid heartbeat key")

    # Validate MAC format
    mac = payload.mac.lower().strip()
    if not MAC_RE.match(mac):
        raise HttpError(400, "Invalid MAC address format")

    # Build connection_info
    connection_info = {
        'yggdrasil_address': payload.yggdrasil_address,
        'hostname': payload.hostname,
        'firmware_version': payload.firmware_version,
        'hardware_profile': payload.hardware_profile,
        'uptime': payload.uptime,
        'private_ssid': payload.private_ssid,
        'firmware_role': payload.firmware_role,
        'mesh_ip': payload.mesh_ip,
        'vpn_mode': payload.vpn_mode,
    }

    now = timezone.now()

    # Resolve default owner for new devices
    try:
        default_owner = Profile.objects.get(id=settings.MESH_DEFAULT_OWNER_PROFILE_ID)
    except Profile.DoesNotExist:
        logger.error(f"Default mesh owner profile {settings.MESH_DEFAULT_OWNER_PROFILE_ID} not found")
        raise HttpError(500, "Mesh owner profile not configured")

    # Check if device already exists (to avoid overwriting owner on update)
    existing = IoTDevice.objects.filter(device_id=mac, device_type='MESH_ROUTER').first()

    if existing:
        # Update only heartbeat fields, preserve owner, location and user-set name
        existing.last_seen = now
        existing.connection_info = connection_info
        existing.save(update_fields=['last_seen', 'connection_info'])
        device = existing
        created = False
    else:
        device = IoTDevice.objects.create(
            device_id=mac,
            device_type='MESH_ROUTER',
            name=payload.hostname,
            last_seen=now,
            connection_info=connection_info,
            owner=default_owner,
        )
        created = True

    logger.info(f"Mesh heartbeat: {mac} ({'new' if created else 'update'}) host={payload.hostname}")

    # VPS WireGuard gateway: store pubkey + allocate IP for bumblebees
    vps_gateway = None
    if (
        payload.wg_public_key
        and _WG_KEY_RE.match(payload.wg_public_key)
        and payload.firmware_role == 'bumblebee'
        and settings.MESH_VPS_WG_PUBKEY
    ):
        # Store/update WG public key
        if device.wg_public_key != payload.wg_public_key:
            device.wg_public_key = payload.wg_public_key
            device.save(update_fields=['wg_public_key'])

        # Allocate IP if not yet assigned
        if not device.wg_ip:
            try:
                device.wg_ip = _allocate_wg_ip()
                device.save(update_fields=['wg_ip'])
                logger.info(f"Allocated VPS WG IP {device.wg_ip} for {mac}")
            except Exception as e:
                logger.error(f"Failed to allocate WG IP for {mac}: {e}")

        # Include VPS gateway config in response
        if device.wg_ip:
            vps_gateway = VpsGatewayConfig(
                endpoint=settings.MESH_VPS_WG_ENDPOINT,
                public_key=settings.MESH_VPS_WG_PUBKEY,
                assigned_ip=f"{device.wg_ip}/16",
                keepalive=25,
            )

    # Return active paid client IPs for speed control
    active_ips = list(MeshSubscription.objects.filter(
        gateway_device=device,
        status='ACTIVE',
        expires_at__gt=now,
    ).values_list('client_ip', flat=True))

    # Yggdrasil ACL: allowed inbound IPv6 addresses
    ygg_allowed = device.ygg_allowed_ips or []

    return MeshHeartbeatOut(status="ok", device_id=device.id, paid_clients=active_ips, ygg_allowed=ygg_allowed, vps_gateway=vps_gateway)


# ============================================================================
# Yggdrasil Access Control (whitelist IPv6 addresses for inbound access)
# ============================================================================

# Validate Yggdrasil 300::/64 subnet address
_YGG_SUBNET_RE = re.compile(r'^3[0-9a-f]{2}:[0-9a-f:]+$', re.IGNORECASE)

_MAX_YGG_ALLOWED = 20  # Max allowed IPs per router


class YggAccessIn(Schema):
    ip: str


class YggAccessOut(Schema):
    ygg_allowed_ips: List[str]


def _validate_ygg_subnet_ip(ip: str) -> str:
    """Validate and normalize a Yggdrasil 300::/7 subnet IPv6 address."""
    ip = ip.strip().lower()
    if not _YGG_SUBNET_RE.match(ip):
        raise HttpError(400, "Invalid address: must be a Yggdrasil 300::/7 subnet address")
    # Validate it's a proper IPv6
    import ipaddress
    try:
        addr = ipaddress.IPv6Address(ip)
    except ValueError:
        raise HttpError(400, "Invalid IPv6 address")
    return str(addr)


@router.get("/devices/{device_id}/ygg-access", response=YggAccessOut, auth=ProfileAuth())
@ratelimit(group='iot:ygg_access', key=user_or_ip, rate='60/m')
def get_ygg_access(request, device_id: str):
    """Get Yggdrasil inbound access whitelist for a mesh router."""
    profile = request.auth_profile
    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)
    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")
    return YggAccessOut(ygg_allowed_ips=device.ygg_allowed_ips or [])


@router.post("/devices/{device_id}/ygg-access", response=YggAccessOut, auth=ProfileAuth())
@ratelimit(group='iot:ygg_add', key=user_or_ip, rate='30/m', method='POST')
def add_ygg_access(request, device_id: str, payload: YggAccessIn):
    """Add an IPv6 address to the Yggdrasil inbound whitelist."""
    profile = request.auth_profile
    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)
    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")

    ip = _validate_ygg_subnet_ip(payload.ip)
    allowed = list(device.ygg_allowed_ips or [])

    if ip in allowed:
        return YggAccessOut(ygg_allowed_ips=allowed)

    if len(allowed) >= _MAX_YGG_ALLOWED:
        raise HttpError(400, f"Maximum {_MAX_YGG_ALLOWED} addresses allowed")

    allowed.append(ip)
    device.ygg_allowed_ips = allowed
    device.save(update_fields=['ygg_allowed_ips'])
    return YggAccessOut(ygg_allowed_ips=allowed)


@router.delete("/devices/{device_id}/ygg-access", response=YggAccessOut, auth=ProfileAuth())
@ratelimit(group='iot:ygg_remove', key=user_or_ip, rate='30/m', method='DELETE')
def remove_ygg_access(request, device_id: str, payload: YggAccessIn):
    """Remove an IPv6 address from the Yggdrasil inbound whitelist."""
    profile = request.auth_profile
    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)
    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")

    ip = _validate_ygg_subnet_ip(payload.ip)
    allowed = list(device.ygg_allowed_ips or [])

    if ip in allowed:
        allowed.remove(ip)
        device.ygg_allowed_ips = allowed
        device.save(update_fields=['ygg_allowed_ips'])

    return YggAccessOut(ygg_allowed_ips=allowed)


class WgPeerOut(Schema):
    public_key: str
    allowed_ips: str


@router.get("/mesh/wg-peers", response=List[WgPeerOut], auth=None)
@ratelimit(group='iot:wg_peers', key='ip', rate='30/m')
def mesh_wg_peers(request: HttpRequest):
    """Return WireGuard peer list for VPS sync script."""
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        raise HttpError(401, "Missing Bearer token")

    token = auth_header[7:]
    if not settings.MESH_HEARTBEAT_KEY or token != settings.MESH_HEARTBEAT_KEY:
        raise HttpError(403, "Invalid heartbeat key")

    peers = IoTDevice.objects.filter(
        wg_public_key__isnull=False,
        wg_ip__isnull=False,
    ).values_list('wg_public_key', 'wg_ip')

    return [
        WgPeerOut(public_key=pubkey, allowed_ips=f"{ip}/32")
        for pubkey, ip in peers
    ]


@router.get("/devices/{device_id}/wifi-password", response=WifiPasswordOut, auth=ProfileAuth())
@ratelimit(group='iot:wifi_password', key=user_or_ip, rate='10/m')
def get_wifi_password(request, device_id: str):
    """Retrieve WiFi password from mesh router via SSH over Yggdrasil."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)

    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")

    ygg_addr = (device.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr or ygg_addr == 'unknown':
        raise HttpError(503, "Router Yggdrasil address unknown")

    try:
        result = _mesh_ssh(ygg_addr, "grep PRIVATE_WIFI_KEY /etc/parahub/keys | cut -d= -f2")

        if result.returncode != 0:
            logger.warning(f"SSH to {ygg_addr} failed: {result.stderr.strip()}")
            raise HttpError(503, "Router is offline or unreachable")

        password = result.stdout.strip()
        if not password:
            raise HttpError(503, "Could not retrieve WiFi password")

        ssid = (device.connection_info or {}).get('private_ssid', device.name)
        return WifiPasswordOut(wifi_password=password, ssid=ssid)

    except subprocess.TimeoutExpired:
        raise HttpError(504, "Router connection timed out")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"SSH error for mesh device {device_id}: {e}")
        raise HttpError(503, "Failed to connect to router")


@router.get("/devices/{device_id}/root-password", response=RootPasswordOut, auth=ProfileAuth())
@ratelimit(group='iot:root_password', key=user_or_ip, rate='10/m')
def get_root_password(request, device_id: str):
    """Retrieve root password from mesh router via SSH over Yggdrasil."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)

    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")

    ygg_addr = (device.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr or ygg_addr == 'unknown':
        raise HttpError(503, "Router Yggdrasil address unknown")

    try:
        result = _mesh_ssh(ygg_addr, "grep ROOT_PASSWORD /etc/parahub/keys | cut -d= -f2")

        if result.returncode != 0:
            logger.warning(f"SSH to {ygg_addr} failed: {result.stderr.strip()}")
            raise HttpError(503, "Router is offline or unreachable")

        password = result.stdout.strip()
        if not password:
            raise HttpError(503, "Could not retrieve root password (firmware too old?)")

        hostname = (device.connection_info or {}).get('hostname', device.name)
        return RootPasswordOut(root_password=password, hostname=hostname)

    except subprocess.TimeoutExpired:
        raise HttpError(504, "Router connection timed out")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"SSH error for mesh device {device_id}: {e}")
        raise HttpError(503, "Failed to connect to router")


# ============================================================================
# Mesh Router WiFi Config & Location
# ============================================================================

class WifiConfigIn(Schema):
    wifi_password: Optional[str] = None
    wifi_ssid: Optional[str] = None
    apply_to_all: bool = True


class WifiConfigResult(Schema):
    device_id: str
    name: str
    success: bool
    error: Optional[str] = None


class WifiConfigOut(Schema):
    updated: int
    failed: int
    results: List[WifiConfigResult]


class DeviceLocationIn(Schema):
    latitude: float
    longitude: float


class DeviceLocationOut(Schema):
    status: str = "ok"
    latitude: float
    longitude: float


class MeshRouterPositionOut(Schema):
    device_id: str
    name: str
    latitude: float
    longitude: float
    firmware_role: Optional[str] = None
    hardware_profile: Optional[str] = None
    status: str = "offline"


class MeshRouterPublicOut(Schema):
    name: str
    latitude: float
    longitude: float
    hardware_profile: Optional[str] = None
    status: str = "offline"


def _apply_wifi_config_to_router(device: IoTDevice, ssid: Optional[str], password: Optional[str]) -> WifiConfigResult:
    """Apply WiFi SSID/password to a single mesh router via SSH."""
    ygg_addr = (device.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr or ygg_addr == 'unknown':
        return WifiConfigResult(device_id=device.id, name=device.name, success=False, error="No Yggdrasil address")

    # Build UCI commands
    cmds = []
    if ssid:
        safe_ssid = shlex.quote(ssid)
        cmds.append(f"uci set wireless.private_2g.ssid={safe_ssid}")
        cmds.append(f"uci set wireless.private_5g.ssid={safe_ssid}")
    if password:
        safe_pw = shlex.quote(password)
        cmds.append(f"uci set wireless.private_2g.key={safe_pw}")
        cmds.append(f"uci set wireless.private_5g.key={safe_pw}")

    if not cmds:
        return WifiConfigResult(device_id=device.id, name=device.name, success=False, error="Nothing to change")

    cmds.append("uci commit wireless")
    cmds.append("wifi reload")

    # Update /etc/parahub/keys
    if password:
        safe_pw = shlex.quote(password)
        cmds.append(f"sed -i 's/^PRIVATE_WIFI_KEY=.*/PRIVATE_WIFI_KEY={safe_pw}/' /etc/parahub/keys")

    command = " && ".join(cmds)

    try:
        result = _mesh_ssh(ygg_addr, command, timeout=15)
        if result.returncode != 0:
            return WifiConfigResult(device_id=device.id, name=device.name, success=False, error=result.stderr.strip() or "SSH command failed")
        return WifiConfigResult(device_id=device.id, name=device.name, success=True)
    except subprocess.TimeoutExpired:
        return WifiConfigResult(device_id=device.id, name=device.name, success=False, error="Connection timed out")
    except Exception as e:
        return WifiConfigResult(device_id=device.id, name=device.name, success=False, error=str(e))


@router.patch("/devices/{device_id}/wifi-config", response=WifiConfigOut, auth=ProfileAuth())
@ratelimit(group='iot:wifi_config', key=user_or_ip, rate='10/m', method='PATCH')
def update_wifi_config(request, device_id: str, payload: WifiConfigIn):
    """Change WiFi SSID and/or password on mesh router(s)."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)

    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")

    if not payload.wifi_password and not payload.wifi_ssid:
        raise HttpError(400, "Must provide wifi_password or wifi_ssid")

    # Validate password length (WPA requirement)
    if payload.wifi_password and (len(payload.wifi_password) < 8 or len(payload.wifi_password) > 63):
        raise HttpError(400, "WiFi password must be 8-63 characters")

    # Validate SSID length
    if payload.wifi_ssid and (len(payload.wifi_ssid) < 1 or len(payload.wifi_ssid) > 32):
        raise HttpError(400, "WiFi SSID must be 1-32 characters")

    # Collect target devices
    if payload.apply_to_all:
        # All bumblebee routers owned by this user (bee has no private AP)
        all_routers = list(IoTDevice.objects.filter(
            owner=profile,
            device_type='MESH_ROUTER',
        ))
        targets = [r for r in all_routers if (r.connection_info or {}).get('firmware_role') != 'bee']
    else:
        targets = [device]

    # Apply in parallel
    results: List[WifiConfigResult] = []
    with ThreadPoolExecutor(max_workers=min(len(targets), 8)) as executor:
        futures = {
            executor.submit(_apply_wifi_config_to_router, t, payload.wifi_ssid, payload.wifi_password): t
            for t in targets
        }
        for future in as_completed(futures):
            results.append(future.result())

    # Update connection_info in Django for successful devices
    for r in results:
        if r.success:
            try:
                d = IoTDevice.objects.get(id=r.device_id)
                ci = d.connection_info or {}
                if payload.wifi_ssid:
                    ci['private_ssid'] = payload.wifi_ssid
                d.connection_info = ci
                d.save(update_fields=['connection_info'])
            except IoTDevice.DoesNotExist:
                pass

    updated = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    return WifiConfigOut(updated=updated, failed=failed, results=results)


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


@router.get("/devices/{device_id}/mullvad-status", response=MullvadStatusOut, auth=ProfileAuth())
@ratelimit(group='iot:mullvad_status', key=user_or_ip, rate='30/m')
def get_mullvad_status(request, device_id: str):
    """Get Mullvad VPN status from mesh router via SSH."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)
    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")
    if (device.connection_info or {}).get('firmware_role') != 'bumblebee':
        raise HttpError(400, "Mullvad is only available on Bumblebee routers")

    ygg_addr = (device.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr or ygg_addr == 'unknown':
        raise HttpError(503, "Router Yggdrasil address unknown")

    try:
        # Check if mullvad_account file exists and read it
        result = _mesh_ssh(ygg_addr, "cat /etc/parahub/mullvad_account 2>/dev/null || echo '__NONE__'")
        if result.returncode != 0:
            raise HttpError(503, "Router is offline or unreachable")

        output = result.stdout.strip()
        if output == '__NONE__':
            return MullvadStatusOut(mode="vps")

        # Parse key=value pairs from mullvad_account
        info = {}
        for line in output.splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                info[k.strip()] = v.strip()

        account = info.get('MULLVAD_ACCOUNT', '')
        # Mask account: show first 4 and last 4 chars
        if len(account) > 8:
            masked = account[:4] + '****' + account[-4:]
        else:
            masked = '****'

        return MullvadStatusOut(
            mode="mullvad",
            account=masked,
            country=info.get('MULLVAD_COUNTRY'),
            server=info.get('MULLVAD_SERVER'),
            server_ip=info.get('MULLVAD_SERVER_IP'),
            local_ip=info.get('MULLVAD_LOCAL_IP'),
        )

    except subprocess.TimeoutExpired:
        raise HttpError(504, "Router connection timed out")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Mullvad status error for {device_id}: {e}")
        raise HttpError(503, "Failed to connect to router")


@router.post("/devices/{device_id}/mullvad-setup", response=MullvadSetupOut, auth=ProfileAuth())
@ratelimit(group='iot:mullvad_setup', key=user_or_ip, rate='5/m', method='POST')
def mullvad_setup(request, device_id: str, payload: MullvadSetupIn):
    """Setup Mullvad VPN on mesh router via SSH."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)
    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")
    if (device.connection_info or {}).get('firmware_role') != 'bumblebee':
        raise HttpError(400, "Mullvad is only available on Bumblebee routers")

    ygg_addr = (device.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr or ygg_addr == 'unknown':
        raise HttpError(503, "Router Yggdrasil address unknown")

    # Validate account key (Mullvad uses 16-digit numbers)
    account_key = payload.account_key.strip()
    if not account_key.isdigit() or len(account_key) != 16:
        raise HttpError(400, "Mullvad account key must be 16 digits")

    # Validate country code
    country = payload.country.strip().lower()
    if country and (len(country) != 2 or not country.isalpha()):
        raise HttpError(400, "Country code must be 2 letters (e.g. pt, de, us)")

    # Build command
    cmd = f"parahub-mullvad setup {shlex.quote(account_key)}"
    if country:
        cmd += f" {shlex.quote(country)}"

    try:
        # Long timeout — script does API calls + network restart
        result = _mesh_ssh(ygg_addr, cmd, timeout=60)

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            logger.warning(f"Mullvad setup failed on {device_id}: {error_msg}")
            raise HttpError(502, f"Setup failed: {error_msg[:200]}")

        # Parse output for server info
        output = result.stdout
        detected_country = country
        server = None
        for line in output.splitlines():
            if line.startswith('Detected:'):
                detected_country = line.split(':', 1)[1].strip()
            elif line.startswith('Server:'):
                server = line.split(':', 1)[1].strip()

        return MullvadSetupOut(
            status="ok",
            mode="mullvad",
            country=detected_country or None,
            server=server,
        )

    except subprocess.TimeoutExpired:
        raise HttpError(504, "Setup timed out (network restart may still be in progress)")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Mullvad setup error for {device_id}: {e}")
        raise HttpError(503, "Failed to connect to router")


@router.post("/devices/{device_id}/mullvad-remove", response=MullvadRemoveOut, auth=ProfileAuth())
@ratelimit(group='iot:mullvad_remove', key=user_or_ip, rate='5/m', method='POST')
def mullvad_remove(request, device_id: str):
    """Remove Mullvad VPN from mesh router, revert to VPS gateway."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)
    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")

    ygg_addr = (device.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr or ygg_addr == 'unknown':
        raise HttpError(503, "Router Yggdrasil address unknown")

    try:
        result = _mesh_ssh(ygg_addr, "parahub-mullvad remove", timeout=30)

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            logger.warning(f"Mullvad remove failed on {device_id}: {error_msg}")
            raise HttpError(502, f"Remove failed: {error_msg[:200]}")

        return MullvadRemoveOut(status="ok", mode="vps")

    except subprocess.TimeoutExpired:
        raise HttpError(504, "Remove timed out")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Mullvad remove error for {device_id}: {e}")
        raise HttpError(503, "Failed to connect to router")


@router.get("/devices/{device_id}/speed-limit-status", response=SpeedLimitStatusOut, auth=ProfileAuth())
@ratelimit(group='iot:speed_limit_status', key=user_or_ip, rate='30/m')
def get_speed_limit_status(request, device_id: str):
    """Get speed limit status from mesh router via SSH."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)
    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")
    if (device.connection_info or {}).get('firmware_role') != 'bumblebee':
        raise HttpError(400, "Speed limit is only available on Bumblebee routers")

    ygg_addr = (device.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr or ygg_addr == 'unknown':
        raise HttpError(503, "Router Yggdrasil address unknown")

    try:
        result = _mesh_ssh(ygg_addr, "/etc/init.d/parahub-speed enabled 2>/dev/null && echo enabled || echo disabled")
        if result.returncode != 0:
            raise HttpError(503, "Router is offline or unreachable")

        enabled = result.stdout.strip() == 'enabled'
        return SpeedLimitStatusOut(enabled=enabled)

    except subprocess.TimeoutExpired:
        raise HttpError(504, "Router connection timed out")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Speed limit status error for {device_id}: {e}")
        raise HttpError(503, "Failed to connect to router")


@router.post("/devices/{device_id}/speed-limit-toggle", response=SpeedLimitToggleOut, auth=ProfileAuth())
@ratelimit(group='iot:speed_limit_toggle', key=user_or_ip, rate='10/m', method='POST')
def speed_limit_toggle(request, device_id: str, payload: SpeedLimitToggleIn):
    """Enable or disable speed limit on mesh router via SSH."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)
    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")
    if (device.connection_info or {}).get('firmware_role') != 'bumblebee':
        raise HttpError(400, "Speed limit is only available on Bumblebee routers")

    ygg_addr = (device.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr or ygg_addr == 'unknown':
        raise HttpError(503, "Router Yggdrasil address unknown")

    if payload.enabled:
        cmd = "/etc/init.d/parahub-speed enable && /etc/init.d/parahub-speed start"
    else:
        cmd = "/etc/init.d/parahub-speed stop; /etc/init.d/parahub-speed disable"

    try:
        result = _mesh_ssh(ygg_addr, cmd, timeout=15)
        if result.returncode != 0 and payload.enabled:
            error_msg = result.stderr.strip() or result.stdout.strip()
            logger.warning(f"Speed limit toggle failed on {device_id}: {error_msg}")
            raise HttpError(502, f"Toggle failed: {error_msg[:200]}")

        return SpeedLimitToggleOut(status="ok", enabled=payload.enabled)

    except subprocess.TimeoutExpired:
        raise HttpError(504, "Router connection timed out")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Speed limit toggle error for {device_id}: {e}")
        raise HttpError(503, "Failed to connect to router")


@router.get("/devices/{device_id}/lan-vpn-status", response=LanVpnStatusOut, auth=ProfileAuth())
@ratelimit(group='iot:lan_vpn_status', key=user_or_ip, rate='30/m')
def get_lan_vpn_status(request, device_id: str):
    """Get LAN VPN routing status from mesh router via SSH."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)
    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")
    if (device.connection_info or {}).get('firmware_role') != 'bumblebee':
        raise HttpError(400, "LAN VPN is only available on Bumblebee routers")

    ygg_addr = (device.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr or ygg_addr == 'unknown':
        raise HttpError(503, "Router Yggdrasil address unknown")

    try:
        result = _mesh_ssh(ygg_addr, "[ -f /etc/parahub/lan_vpn_enabled ] && echo enabled || echo disabled")
        if result.returncode != 0:
            raise HttpError(503, "Router is offline or unreachable")

        enabled = result.stdout.strip() == 'enabled'
        return LanVpnStatusOut(enabled=enabled)

    except subprocess.TimeoutExpired:
        raise HttpError(504, "Router connection timed out")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"LAN VPN status error for {device_id}: {e}")
        raise HttpError(503, "Failed to connect to router")


@router.post("/devices/{device_id}/lan-vpn-toggle", response=LanVpnToggleOut, auth=ProfileAuth())
@ratelimit(group='iot:lan_vpn_toggle', key=user_or_ip, rate='10/m', method='POST')
def lan_vpn_toggle(request, device_id: str, payload: LanVpnToggleIn):
    """Enable or disable LAN VPN routing on mesh router via SSH."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)
    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")
    if (device.connection_info or {}).get('firmware_role') != 'bumblebee':
        raise HttpError(400, "LAN VPN is only available on Bumblebee routers")

    ygg_addr = (device.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr or ygg_addr == 'unknown':
        raise HttpError(503, "Router Yggdrasil address unknown")

    if payload.enabled:
        cmd = (
            "PRIV_SUBNET=$(ip -4 addr show br-private | grep -oP '\\d+\\.\\d+\\.\\d+\\.0/24') && "
            "PRIV_DEV=br-private && "
            "VPN_ZONE=mullvad_local && "
            "uci add network rule >/dev/null && "
            "uci set network.@rule[-1].src=\"$PRIV_SUBNET\" && "
            "uci set network.@rule[-1].lookup='100' && "
            "uci set network.@rule[-1].priority='99' && "
            "uci commit network && "
            "uci add firewall forwarding >/dev/null && "
            "uci set firewall.@forwarding[-1].src='lan' && "
            "uci set firewall.@forwarding[-1].dest=\"$VPN_ZONE\" && "
            "uci commit firewall && "
            "ip rule add from $PRIV_SUBNET lookup 100 priority 99 2>/dev/null; "
            "ip route add $PRIV_SUBNET dev $PRIV_DEV table 100 2>/dev/null; "
            "fw4 reload && "
            "touch /etc/parahub/lan_vpn_enabled"
        )
    else:
        cmd = (
            "PRIV_SUBNET=$(ip -4 addr show br-private | grep -oP '\\d+\\.\\d+\\.\\d+\\.0/24') && "
            "for i in $(seq $(uci show network | grep -c '@rule') -1 0); do "
            "  if [ \"$(uci -q get network.@rule[$i].priority)\" = '99' ]; then "
            "    uci delete network.@rule[$i]; "
            "  fi; "
            "done; "
            "uci commit network; "
            "for i in $(seq $(uci show firewall | grep -c '@forwarding') -1 0); do "
            "  DST=$(uci -q get firewall.@forwarding[$i].dest); "
            "  SRC=$(uci -q get firewall.@forwarding[$i].src); "
            "  if [ \"$SRC\" = 'lan' ] && [ \"$DST\" = 'mullvad_local' ]; then "
            "    uci delete firewall.@forwarding[$i]; "
            "  fi; "
            "done; "
            "uci commit firewall; "
            "ip rule del from $PRIV_SUBNET lookup 100 priority 99 2>/dev/null; "
            "ip route del $PRIV_SUBNET table 100 2>/dev/null; "
            "fw4 reload; "
            "rm -f /etc/parahub/lan_vpn_enabled"
        )

    try:
        result = _mesh_ssh(ygg_addr, cmd, timeout=20)
        if result.returncode != 0 and payload.enabled:
            error_msg = result.stderr.strip() or result.stdout.strip()
            logger.warning(f"LAN VPN toggle failed on {device_id}: {error_msg}")
            raise HttpError(502, f"Toggle failed: {error_msg[:200]}")

        return LanVpnToggleOut(status="ok", enabled=payload.enabled)

    except subprocess.TimeoutExpired:
        raise HttpError(504, "Router connection timed out")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"LAN VPN toggle error for {device_id}: {e}")
        raise HttpError(503, "Failed to connect to router")


# ============================================================================
# Wired Mesh (batman-adv over Ethernet LAN port — Bumblebee only, Bee has it by default)
# ============================================================================

@router.get("/devices/{device_id}/wired-mesh-status", response=WiredMeshStatusOut, auth=ProfileAuth())
@ratelimit(group='iot:wired_mesh_status', key=user_or_ip, rate='30/m')
def get_wired_mesh_status(request, device_id: str):
    """Get wired mesh (batman-adv on LAN port) status from Bumblebee router via SSH."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)
    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")
    if (device.connection_info or {}).get('firmware_role') not in ('bumblebee', 'bee'):
        raise HttpError(400, "Wired mesh is only available on mesh routers")

    ygg_addr = (device.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr or ygg_addr == 'unknown':
        raise HttpError(503, "Router Yggdrasil address unknown")

    try:
        # Check if any LAN ethernet interface is a batman-adv hardif
        result = _mesh_ssh(ygg_addr, "batctl meshif bat0 if 2>/dev/null | grep -qv mesh && echo enabled || echo disabled")
        if result.returncode != 0:
            raise HttpError(503, "Router is offline or unreachable")

        enabled = result.stdout.strip() == 'enabled'
        return WiredMeshStatusOut(enabled=enabled)

    except subprocess.TimeoutExpired:
        raise HttpError(504, "Router connection timed out")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Wired mesh status error for {device_id}: {e}")
        raise HttpError(503, "Failed to connect to router")


@router.post("/devices/{device_id}/wired-mesh-toggle", response=WiredMeshToggleOut, auth=ProfileAuth())
@ratelimit(group='iot:wired_mesh_toggle', key=user_or_ip, rate='10/m', method='POST')
def wired_mesh_toggle(request, device_id: str, payload: WiredMeshToggleIn):
    """Enable or disable wired mesh (batman-adv on LAN port) on Bumblebee router via SSH."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)
    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")
    if (device.connection_info or {}).get('firmware_role') not in ('bumblebee', 'bee'):
        raise HttpError(400, "Wired mesh is only available on mesh routers")

    ygg_addr = (device.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr or ygg_addr == 'unknown':
        raise HttpError(503, "Router Yggdrasil address unknown")

    if payload.enabled:
        # Detect LAN ports from port_map, remove from br-private, add as batman-adv hardif
        cmd = (
            "PORT_MAP=$(cat /etc/parahub/port_map 2>/dev/null || echo 'eth0:lan eth1:wan') && "
            "if [ \"$PORT_MAP\" = 'dsa' ]; then LAN_PORTS='lan1 lan2 lan3 lan4'; "
            "else LAN_PORTS=''; for m in $PORT_MAP; do "
            "  p=${m%%:*}; r=${m##*:}; [ \"$r\" = 'lan' ] && LAN_PORTS=\"$LAN_PORTS $p\"; "
            "done; fi && "
            "IDX=0; for port in $LAN_PORTS; do "
            "  uci -q del_list network.private_dev.ports=\"$port\" 2>/dev/null; "
            "  uci set network.bat0_hardif_eth${IDX}=interface; "
            "  uci set network.bat0_hardif_eth${IDX}.proto='batadv_hardif'; "
            "  uci set network.bat0_hardif_eth${IDX}.master='bat0'; "
            "  uci set network.bat0_hardif_eth${IDX}.device=\"$port\"; "
            "  IDX=$((IDX + 1)); "
            "done && "
            "uci commit network && "
            "touch /etc/parahub/wired_mesh_enabled && "
            "/etc/init.d/network restart"
        )
    else:
        # Remove batman-adv hardifs for ethX, re-add LAN ports to br-private
        cmd = (
            "PORT_MAP=$(cat /etc/parahub/port_map 2>/dev/null || echo 'eth0:lan eth1:wan') && "
            "if [ \"$PORT_MAP\" = 'dsa' ]; then LAN_PORTS='lan1 lan2 lan3 lan4'; "
            "else LAN_PORTS=''; for m in $PORT_MAP; do "
            "  p=${m%%:*}; r=${m##*:}; [ \"$r\" = 'lan' ] && LAN_PORTS=\"$LAN_PORTS $p\"; "
            "done; fi && "
            "for i in 0 1 2 3; do "
            "  uci -q delete network.bat0_hardif_eth${i} 2>/dev/null; "
            "done && "
            "for port in $LAN_PORTS; do "
            "  uci add_list network.private_dev.ports=\"$port\"; "
            "done && "
            "uci commit network && "
            "rm -f /etc/parahub/wired_mesh_enabled && "
            "/etc/init.d/network restart"
        )

    try:
        result = _mesh_ssh(ygg_addr, cmd, timeout=30)
        if result.returncode != 0 and payload.enabled:
            error_msg = result.stderr.strip() or result.stdout.strip()
            logger.warning(f"Wired mesh toggle failed on {device_id}: {error_msg}")
            raise HttpError(502, f"Toggle failed: {error_msg[:200]}")

        return WiredMeshToggleOut(status="ok", enabled=payload.enabled)

    except subprocess.TimeoutExpired:
        raise HttpError(504, "Router connection timed out")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Wired mesh toggle error for {device_id}: {e}")
        raise HttpError(503, "Failed to connect to router")


# ============================================================================
# Mesh Router Diagnostics
# ============================================================================

class DiagSectionOut(Schema):
    title: str
    output: str


class DiagnosticsOut(Schema):
    tab: str
    sections: List[DiagSectionOut]


_DIAG_COMMANDS = {
    'mesh': [
        ('batctl if', 'batctl if 2>/dev/null || echo "batman-adv not active"'),
        ('batctl originators', 'batctl o 2>/dev/null || echo "batman-adv not active"'),
        ('batctl gateway', 'batctl gw 2>/dev/null || echo "batman-adv not active"'),
    ],
    'wifi': [
        ('iwinfo wlan0', 'iwinfo wlan0 info 2>/dev/null || echo "not found"'),
        ('iwinfo wlan1', 'iwinfo wlan1 info 2>/dev/null || echo "not found"'),
        ('wlan0 clients', 'iwinfo wlan0 assoclist 2>/dev/null || echo "no clients"'),
        ('wlan1 clients', 'iwinfo wlan1 assoclist 2>/dev/null || echo "no clients"'),
    ],
    'network': [
        ('ip rule', 'ip rule show'),
        ('routing table 100', 'ip route show table 100 2>/dev/null || echo "empty"'),
        ('br-private', 'ip addr show br-private 2>/dev/null || echo "not found"'),
        ('br-guest', 'ip addr show br-guest 2>/dev/null || echo "not found"'),
    ],
    'vpn': [
        ('WireGuard', 'wg show 2>/dev/null || echo "not active"'),
        ('Mullvad config', 'cat /etc/parahub/mullvad_account 2>/dev/null || echo "not configured"'),
    ],
    'system': [
        ('Memory', 'free'),
        ('Disk', 'df -h /overlay'),
        ('Speed control', 'tc -s qdisc show dev br-guest 2>/dev/null || echo "not active"'),
        ('System log', 'logread -l 30 2>/dev/null | tail -30'),
    ],
}
_BEE_TABS = {'mesh', 'wifi', 'system'}
_BUMBLEBEE_TABS = {'mesh', 'wifi', 'network', 'vpn', 'system'}


@router.get("/devices/{device_id}/diagnostics/{tab}", response=DiagnosticsOut, auth=ProfileAuth())
@ratelimit(group='iot:diagnostics', key=user_or_ip, rate='30/m')
def get_diagnostics(request, device_id: str, tab: str):
    """Run diagnostic commands on a mesh router via SSH and return output."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    device = get_object_or_404(IoTDevice, id=device_id, owner=profile)
    if device.device_type != 'MESH_ROUTER':
        raise HttpError(400, "Not a mesh router")

    firmware_role = (device.connection_info or {}).get('firmware_role', 'bee')
    allowed_tabs = _BUMBLEBEE_TABS if firmware_role == 'bumblebee' else _BEE_TABS

    if tab not in allowed_tabs:
        raise HttpError(400, f"Tab '{tab}' not available for {firmware_role} routers")

    ygg_addr = (device.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr or ygg_addr == 'unknown':
        raise HttpError(503, "Router Yggdrasil address unknown")

    commands = _DIAG_COMMANDS[tab]
    # Build a single SSH command with section markers
    parts = []
    for i, (_title, cmd) in enumerate(commands):
        if i > 0:
            parts.append(f"echo '___SECTION_{i}___'")
        parts.append(cmd)
    combined = ' ; '.join(parts)

    try:
        result = _mesh_ssh(ygg_addr, combined, timeout=15)
        if result.returncode != 0 and not result.stdout.strip():
            raise HttpError(503, "Router is offline or unreachable")

        # Split output on markers
        raw = result.stdout
        chunks = [raw]
        for i in range(1, len(commands)):
            marker = f'___SECTION_{i}___'
            last = chunks[-1]
            if marker in last:
                before, after = last.split(marker, 1)
                chunks[-1] = before
                chunks.append(after)

        sections = []
        for i, (title, _cmd) in enumerate(commands):
            output = chunks[i].strip() if i < len(chunks) else ''
            sections.append(DiagSectionOut(title=title, output=output))

        return DiagnosticsOut(tab=tab, sections=sections)

    except subprocess.TimeoutExpired:
        raise HttpError(504, "Router connection timed out")
    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Diagnostics error for {device_id}/{tab}: {e}")
        raise HttpError(503, "Failed to connect to router")


@router.get("/mesh-router-positions", response=List[MeshRouterPositionOut], auth=ProfileAuth())
@ratelimit(group='iot:mesh_positions', key=user_or_ip, rate='60/m')
def get_mesh_router_positions(request):
    """Get all mesh router positions for coverage map overlay."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    devices = IoTDevice.objects.filter(owner=profile, device_type='MESH_ROUTER')
    now = timezone.now()
    result = []

    for device in devices:
        if device.latitude is None or device.longitude is None:
            continue

        # Determine status from last_seen
        status = 'offline'
        if device.last_seen:
            diff_minutes = (now - device.last_seen).total_seconds() / 60
            if diff_minutes < 10:
                status = 'online'
            elif diff_minutes < 30:
                status = 'recent'

        ci = device.connection_info or {}
        result.append(MeshRouterPositionOut(
            device_id=device.id,
            name=device.name,
            latitude=device.latitude,
            longitude=device.longitude,
            firmware_role=ci.get('firmware_role'),
            hardware_profile=ci.get('hardware_profile'),
            status=status,
        ))

    return result


@router.get("/mesh/public-positions", response=List[MeshRouterPublicOut], auth=None)
@ratelimit(group='iot:mesh_public_positions', key=user_or_ip, rate='30/m')
def get_mesh_router_public_positions(request):
    """Public mesh router positions for map layer. No auth required."""
    devices = IoTDevice.objects.filter(
        device_type='MESH_ROUTER',
        latitude__isnull=False,
        longitude__isnull=False,
    )
    now = timezone.now()
    result = []

    for device in devices:
        status = 'offline'
        if device.last_seen:
            diff_minutes = (now - device.last_seen).total_seconds() / 60
            if diff_minutes < 10:
                status = 'online'
            elif diff_minutes < 30:
                status = 'recent'

        ci = device.connection_info or {}
        result.append(MeshRouterPublicOut(
            name=device.name,
            latitude=device.latitude,
            longitude=device.longitude,
            hardware_profile=ci.get('hardware_profile'),
            status=status,
        ))

    return result


# ============================================================================
# Mesh WiFi Speed Subscription (Lightning Network)
# ============================================================================

class MeshSubscribeIn(Schema):
    gateway_mac: str = ""


class MeshSubscribeOut(Schema):
    invoice: str
    payment_hash: str
    amount_sats: int
    expires_minutes: int = 15


class MeshSubscribeStatusOut(Schema):
    status: str
    expires_at: Optional[datetime] = None


class MeshMyIPOut(Schema):
    ip: str


def _get_client_ip(request: HttpRequest) -> str:
    """Extract real client IP (behind Nginx proxy)."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _get_mesh_lnbits() -> LNbitsProvider:
    """Create LNbits provider from mesh settings."""
    if not settings.MESH_LNBITS_URL or not settings.MESH_LNBITS_INVOICE_KEY:
        raise HttpError(503, "Lightning payments not configured")
    return LNbitsProvider(
        api_url=settings.MESH_LNBITS_URL,
        invoice_key=settings.MESH_LNBITS_INVOICE_KEY,
    )


@router.get("/mesh/my-ip", response=MeshMyIPOut, auth=None)
@ratelimit(group='iot:mesh_my_ip', key='ip', rate='60/m')
def mesh_my_ip(request: HttpRequest):
    """Return the client's IP address as seen by the server."""
    return MeshMyIPOut(ip=_get_client_ip(request))


@router.post("/mesh/subscribe", response=MeshSubscribeOut, auth=None)
@ratelimit(group='mesh:subscribe', key='ip', rate='5/m')
def mesh_subscribe(request: HttpRequest, payload: MeshSubscribeIn):
    """Create a Lightning invoice for WiFi speed upgrade."""
    client_ip = _get_client_ip(request)
    if not client_ip:
        raise HttpError(400, "Cannot determine client IP")

    mac = payload.gateway_mac.lower().strip()

    if mac:
        if not MAC_RE.match(mac):
            raise HttpError(400, "Invalid gateway MAC format")
        device = IoTDevice.objects.filter(
            device_id=mac, device_type='MESH_ROUTER'
        ).first()
    else:
        # V1: auto-select first bumblebee gateway
        device = IoTDevice.objects.filter(
            device_type='MESH_ROUTER',
        ).order_by('-last_seen').first()

    if not device:
        raise HttpError(404, "No mesh gateway found")

    # Check for existing active subscription
    existing = MeshSubscription.objects.filter(
        client_ip=client_ip,
        gateway_device=device,
        status='ACTIVE',
        expires_at__gt=timezone.now(),
    ).first()
    if existing:
        raise HttpError(409, "Active subscription already exists")

    # Create LN invoice
    lnbits = _get_mesh_lnbits()
    amount = settings.MESH_SUBSCRIPTION_PRICE_SATS
    days = settings.MESH_SUBSCRIPTION_DURATION_DAYS
    memo = f"Parahub WiFi speed upgrade ({days}d) - {client_ip}"

    try:
        invoice = lnbits.create_invoice(amount_sats=amount, memo=memo)
    except Exception as e:
        logger.error(f"Failed to create LN invoice: {e}")
        raise HttpError(503, "Failed to create invoice")

    # Create pending subscription
    MeshSubscription.objects.create(
        client_ip=client_ip,
        gateway_device=device,
        ln_payment_hash=invoice.payment_hash,
        ln_invoice=invoice.payment_request,
        amount_sats=amount,
        status='PENDING',
    )

    return MeshSubscribeOut(
        invoice=invoice.payment_request,
        payment_hash=invoice.payment_hash,
        amount_sats=amount,
        expires_minutes=15,
    )


@router.get("/mesh/subscribe/status/{payment_hash}", response=MeshSubscribeStatusOut, auth=None)
@ratelimit(group='mesh:subscribe_status', key='ip', rate='30/m')
def mesh_subscribe_status(request: HttpRequest, payment_hash: str):
    """Check payment status and activate subscription if paid."""
    sub = MeshSubscription.objects.filter(ln_payment_hash=payment_hash).first()
    if not sub:
        raise HttpError(404, "Subscription not found")

    if sub.status == 'ACTIVE':
        return MeshSubscribeStatusOut(status='active', expires_at=sub.expires_at)
    if sub.status == 'EXPIRED':
        return MeshSubscribeStatusOut(status='expired', expires_at=sub.expires_at)

    # PENDING — check with LNbits
    try:
        lnbits = _get_mesh_lnbits()
        result = lnbits.check_invoice(payment_hash)
    except Exception as e:
        logger.error(f"Failed to check LN invoice {payment_hash}: {e}")
        return MeshSubscribeStatusOut(status='pending')

    if result.get('paid'):
        now = timezone.now()
        duration = timedelta(days=settings.MESH_SUBSCRIPTION_DURATION_DAYS)
        sub.status = 'ACTIVE'
        sub.paid_at = now
        sub.expires_at = now + duration
        sub.save(update_fields=['status', 'paid_at', 'expires_at'])
        return MeshSubscribeStatusOut(status='active', expires_at=sub.expires_at)

    return MeshSubscribeStatusOut(status='pending')


# ==================== SERVER MONITORING ====================

class ServerHealthOut(Schema):
    cpu_percent: float
    ram_percent: float
    disk_percent: float
    containers_running: int
    containers_total: int
    uptime_seconds: int
    netdata_url: str = "https://netdata.parahub.io"
    uptime_kuma_url: str = "https://status.parahub.io"


@router.get("/server/health", response=ServerHealthOut, auth=GlobalAuth())
@ratelimit(group='iot:server_health', key=user_or_ip, rate='30/m')
def server_health(request):
    """Server health metrics for IoT dashboard (staff only)."""
    if not request.auth.is_staff:
        raise HttpError(403, "Staff only")

    cached = cache.get("iot:server:health")
    if cached is not None:
        return cached

    result = {
        'cpu_percent': 0, 'ram_percent': 0, 'disk_percent': 0,
        'containers_running': 0, 'containers_total': 0, 'uptime_seconds': 0,
        'netdata_url': 'https://netdata.parahub.io',
        'uptime_kuma_url': 'https://status.parahub.io',
    }

    # CPU from /proc/loadavg (1-min avg / cores)
    try:
        with open('/proc/loadavg') as f:
            load1 = float(f.read().split()[0])
        result['cpu_percent'] = round(load1 / os.cpu_count() * 100, 1)
    except Exception:
        pass

    # RAM from /proc/meminfo
    try:
        with open('/proc/meminfo') as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                meminfo[parts[0].rstrip(':')] = int(parts[1])
        total = meminfo.get('MemTotal', 1)
        available = meminfo.get('MemAvailable', 0)
        result['ram_percent'] = round((1 - available / total) * 100, 1)
    except Exception:
        pass

    # Disk from os.statvfs
    try:
        st = os.statvfs('/')
        result['disk_percent'] = round((1 - st.f_bavail / st.f_blocks) * 100, 1)
    except Exception:
        pass

    # Uptime from /proc/uptime
    try:
        with open('/proc/uptime') as f:
            result['uptime_seconds'] = int(float(f.read().split()[0]))
    except Exception:
        pass

    # Docker containers
    try:
        out = subprocess.check_output(
            ['docker', 'ps', '-a', '--format', '{{.State}}'],
            timeout=5, text=True
        )
        states = out.strip().split('\n') if out.strip() else []
        result['containers_total'] = len(states)
        result['containers_running'] = sum(1 for s in states if s == 'running')
    except Exception:
        pass

    cache.set("iot:server:health", result, 15)  # 15s TTL
    return result


MONITOR_SERVICES = {
    'netdata': 'https://netdata.parahub.io',
    'status': 'https://status.parahub.io',
}
MONITOR_SALT = 'monitor-auth'


@router.get("/monitor/{service}/", auth=None)
@ratelimit(group='iot:monitor_redirect', key='ip', rate='30/m')
def monitor_redirect(request, service: str):
    """Generate signed token and redirect to monitoring dashboard (staff only).
    Accepts JWT via Authorization header or ?token= query param (for window.open)."""
    if service not in MONITOR_SERVICES:
        raise HttpError(404, "Unknown service")

    # Authenticate: try header first, then query param
    from parahub.auth import GlobalAuth
    auth = GlobalAuth()
    account = None
    try:
        account = auth.authenticate(request, request.META.get('HTTP_AUTHORIZATION', '').replace('Bearer ', ''))
    except Exception:
        pass
    if not account:
        jwt_param = request.GET.get('token', '')
        if jwt_param:
            try:
                account = auth.authenticate(request, jwt_param)
            except Exception:
                pass
    if not account or not account.is_staff:
        raise HttpError(403, "Staff only")

    signed = signing.dumps({'s': service, 'u': account.id}, salt=MONITOR_SALT)
    base = MONITOR_SERVICES[service]
    # Status dashboard lives at /dashboard (root is public status page)
    path = "/dashboard" if service == "status" else ""
    url = f"{base}{path}?_t={signed}"
    return HttpResponse(status=302, headers={'Location': url})


@router.get("/monitor-auth/", auth=None)
@ratelimit(group='iot:monitor_auth', key='ip', rate='120/m')
def monitor_auth(request):
    """Validate monitoring token or cookie (called by nginx auth_request)."""
    # Extract _t from X-Original-URI header (nginx auth_request passes original URI)
    token = request.GET.get('_t', '')
    if not token:
        original_uri = request.META.get('HTTP_X_ORIGINAL_URI', '')
        if '_t=' in original_uri:
            from urllib.parse import urlparse, parse_qs
            parsed = parse_qs(urlparse(original_uri).query)
            token = parsed.get('_t', [''])[0]
    if token:
        try:
            data = signing.loads(token, salt=MONITOR_SALT, max_age=300)
            # Valid token — return 200 with Set-Cookie for subsequent requests
            session_val = signing.dumps({'s': data['s'], 'u': data['u']}, salt=MONITOR_SALT)
            resp = HttpResponse(status=200)
            resp.set_cookie(
                '_monitor', session_val,
                max_age=3600, httponly=True, secure=True, samesite='Strict',
            )
            return resp
        except (signing.BadSignature, KeyError):
            pass

    # Check existing cookie
    cookie = request.COOKIES.get('_monitor', '')
    if cookie:
        try:
            signing.loads(cookie, salt=MONITOR_SALT, max_age=3600)
            return HttpResponse(status=200)
        except signing.BadSignature:
            pass

    return HttpResponse(status=401)