"""
Mesh router fleet: heartbeat + WireGuard/Yggdrasil provisioning, wifi
config, credentials, positions, paid subscriptions.
"""


from typing import List, Optional
from datetime import datetime
import json as _json_module
import logging
import subprocess
import shlex
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from ninja import Schema
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from django.utils import timezone
from django.http import HttpRequest
from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from django.conf import settings
from datetime import timedelta
from ..models import IoTDevice, MeshSubscription
from identity.models import Profile
from ads.ln_wallet_service import LNbitsProvider

from .base import router

logger = logging.getLogger(__name__)

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
    guest_gateway: bool = False  # ph35: this bumblebee terminates the mesh guest VLAN

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

# --- Guest-VLAN gateway election (ph35) --------------------------------------
# Exactly one bumblebee terminates the mesh-wide guest VLAN (bat0.10): it runs
# the guest DHCP server + VPN exit, while every other node relays the VLAN
# L2-only. batman-adv's gw_mode arbitrates DHCP on the untagged bat0 but NOT on
# a tagged sub-interface, so without a single designated terminator every ph35
# bumblebee would serve guest DHCP on the one shared L2 (a race that did not
# exist pre-ph34, when guest was node-local). Only ph35+ bumblebees with an
# active VPN uplink are eligible; the choice is sticky (cache) with failover to
# the next node when the incumbent goes stale or loses its uplink.
_PH_BUILD_RE = re.compile(r'-ph(\d+)')
_GUEST_GW_MIN_BUILD = 35
_GUEST_GW_FRESH = timedelta(minutes=15)
_GUEST_GW_TTL = 1800  # seconds the cached designation stays sticky

def _ph_build(version: str) -> int:
    """Extract the PARAHUB_BUILD N from a '...-phN' firmware version (0 if absent)."""
    m = _PH_BUILD_RE.search(version or '')
    return int(m.group(1)) if m else 0

def _eligible_guest_gateways(now) -> List[str]:
    """device_ids of bumblebees that can terminate the guest VLAN, sorted for determinism."""
    fresh = now - _GUEST_GW_FRESH
    out = []
    for d in IoTDevice.objects.filter(device_type='MESH_ROUTER', last_seen__gte=fresh):
        ci = d.connection_info or {}
        if ci.get('firmware_role') != 'bumblebee':
            continue
        if ci.get('vpn_mode') not in ('vps', 'mullvad'):
            continue
        if _ph_build(ci.get('firmware_version', '')) < _GUEST_GW_MIN_BUILD:
            continue
        out.append(d.device_id)
    return sorted(out)

def _elect_guest_gateway(now) -> Optional[str]:
    """Designate one guest-VLAN terminator, sticky across heartbeats with failover."""
    eligible = _eligible_guest_gateways(now)
    if not eligible:
        cache.delete('mesh_guest_gateway')
        return None
    current = cache.get('mesh_guest_gateway')
    chosen = current if current in eligible else eligible[0]
    cache.set('mesh_guest_gateway', chosen, _GUEST_GW_TTL)
    return chosen

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

    # Guest-VLAN gateway election (ph35): tell exactly one bumblebee to terminate
    # the mesh guest VLAN (DHCP + VPN exit); every other node relays it L2-only.
    guest_gateway = False
    if payload.firmware_role == 'bumblebee':
        guest_gateway = _elect_guest_gateway(now) == mac

    return MeshHeartbeatOut(status="ok", device_id=device.id, paid_clients=active_ips, ygg_allowed=ygg_allowed, vps_gateway=vps_gateway, guest_gateway=guest_gateway)

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
