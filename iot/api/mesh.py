"""
Mesh router fleet: heartbeat + WireGuard/Yggdrasil provisioning, wifi
config, credentials, positions, paid subscriptions.
"""


from typing import List, Optional
from datetime import datetime
from itertools import combinations
import hmac as _hmac
import ipaddress
import json as _json_module
import logging
import subprocess
import shlex
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from constance import config
from ninja import Schema
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.http import HttpRequest
from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from django.conf import settings
from datetime import timedelta
from core.access import ROLE_MANAGER, accessible_q
from ..models import IoTDevice, MeshPass, MeshPassCredit, MeshDevice
from ..mesh_pass import grant_mesh_pass, ensure_mesh_pass_floor
from identity.models import Profile
from ads.ln_wallet_service import LNbitsProvider

from .access import get_device_for
from .base import public_owner_fields, router

logger = logging.getLogger(__name__)

class GuestLease(Schema):
    mac: str
    ip: str
    host: str = ""

class MeshStatsIn(Schema):
    uplink_dev: str = ''
    wan_rx: int = 0
    wan_tx: int = 0
    guest_rx: int = 0
    guest_tx: int = 0
    wifi_clients: int = 0
    guest_clients: int = 0
    load_1m: float = 0
    mem_total: int = 0
    mem_avail: int = 0


class MeshLinkIn(Schema):
    o: str  # originator MAC
    n: str  # nexthop MAC
    t: float = 0  # BATMAN_V throughput estimate, Mbit/s


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
    # ph54+: whether this node actually broadcasts the private AP (firmware
    # gates it on dual-band hardware, not on role — a dual-band bee has one).
    # None = older firmware; callers fall back to the role heuristic.
    private_ap: Optional[bool] = None
    # Mesh topology (ph37+): own mesh iface MACs + originator MACs seen via
    # batctl o. None = old firmware that doesn't report topology.
    mesh_macs: Optional[List[str]] = None
    mesh_originators: Optional[List[str]] = None
    # Originator-table routes (ph50+): raw {originator, nexthop, throughput}
    # rows from batctl o. A row whose nexthop belongs to the same node as the
    # originator is a direct radio link — resolved backend-side against the
    # fleet's mesh_macs (the topology graph). None = old firmware.
    mesh_links: Optional[List[MeshLinkIn]] = None
    # Every burned-in address of the box (ph45+), so claim-by-sticker can match
    # whichever one is on the label. None = old firmware.
    hw_macs: Optional[List[str]] = None
    # Guest DHCP leases (ph40+, guest-VLAN terminator only): the node's view of
    # MAC↔IP on its guest subnet. None = old firmware.
    guest_leases: Optional[List[GuestLease]] = None
    # Telemetry counters (ph41+). None = old firmware; a reporting node writes
    # one MeshRouterStats row per heartbeat.
    stats: Optional[MeshStatsIn] = None

class VpsGatewayConfig(Schema):
    endpoint: str
    public_key: str
    assigned_ip: str  # with /16 mask
    keepalive: int = 25

class MeshRatesOut(Schema):
    # ph44: owner-set sharing budgets. guest_kbps = per-guest free-tier rate
    # (this node's own knob, applied while it terminates the guest VLAN);
    # host_mbps = bat0 budget for a bee / fallback bumblebee riding a donor's
    # uplink (min over the island's donor bumblebees).
    guest_kbps: int = 512
    host_mbps: int = 10

class BondPeerOut(Schema):
    pubkey: str        # peer's WireGuard public key (same keypair as vps_gateway)
    endpoint_ip: str   # peer's transit-VLAN address — the WG endpoint
    bond_ip: str       # peer's WG-tunnel address — the GRETAP endpoint

class BondConfigOut(Schema):
    """Same-owner private-L2 bonding (ph55+): GRETAP over WireGuard over the
    transit VLAN, hub-spoke within one mesh island. Restores the cross-building
    L2 (DLNA/SSDP, seamless roaming) that leaving the mesh out of br-private
    removed — scoped to one owner's nodes, keyed per pair."""
    role: str          # 'hub' | 'spoke'
    local_ip: str      # this node's WG-tunnel address
    peers: List[BondPeerOut]  # spoke: exactly the hub; hub: every spoke

class MeshHeartbeatOut(Schema):
    status: str = "ok"
    device_id: str
    paid_clients: List[str] = []
    ygg_allowed: List[str] = []
    vps_gateway: Optional[VpsGatewayConfig] = None
    guest_gateway: bool = False  # ph35: this bumblebee terminates the mesh guest VLAN
    bond: Optional[BondConfigOut] = None  # ph55: same-owner L2 bonding
    # ph42: backend probes this node's ygg:22 and confirmed it dead — the node
    # should climb its self-heal ladder (yggdrasil restart -> reboot)
    ygg_inbound_dead: bool = False
    rates: Optional[MeshRatesOut] = None
    # ph51: owner-set coordinates (already public via mesh/public-positions) so
    # the node's guest status page can link the map centered on itself
    latitude: Optional[float] = None
    longitude: Optional[float] = None

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

# --- Yggdrasil inbound reachability (self-heal) --------------------------------
# The mesh_probe_inbound command (parahub-mesh-probe.timer, every 2 min)
# TCP-probes each fresh node's ygg SSH port and keeps a consecutive-failure
# streak here. Catches the ygg-inbound-dead wedge: heartbeats flow out while
# inbound connections time out, so the node looks green yet is unmanageable.
# The heartbeat reply carries the verdict as ygg_inbound_dead and the node
# runs its escalation ladder (yggdrasil restart -> reboot). Short TTL by
# design: if the probe timer stops, the state evaporates and no node ever
# acts on a stale verdict.
YGG_PROBE_TTL = 900
YGG_PROBE_DEAD_AFTER = 3  # consecutive failed probes ~= 6 min at a 2-min timer


def ygg_probe_key(mac: str) -> str:
    return f'iot:mesh:ygg_probe:{mac}'


def ygg_inbound_status(mac: str) -> Optional[bool]:
    """True = reachable, False = confirmed dead streak, None = not probed."""
    state = cache.get(ygg_probe_key(mac))
    if not state:
        return None
    return not state.get('dead')

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

# --- Guest-VLAN gateway election ----------------------------------------------
# Exactly one bumblebee per mesh island terminates that island's guest VLAN
# (bat0.10): it runs the guest DHCP server + VPN exit, while every other node
# relays the VLAN L2-only. batman-adv's gw_mode arbitrates DHCP on the untagged
# bat0 but NOT on a tagged sub-interface, so without a single designated
# terminator per island bumblebees would race DHCP on the shared guest L2.
#
# Islands come from heartbeat-reported topology (ph37+): each node sends its own
# mesh interface MACs (`mesh_macs`) and the originator MACs it sees
# (`mesh_originators`; batctl o is the full multi-hop island view, so two
# bumblebees joined only through bees still see each other). Two nodes share an
# island when either's mesh MAC appears in the other's originator set; an empty
# originator set is a solo island. Until EVERY fresh bumblebee reports topology,
# the election stays fleet-global — grouping with partial data could split one
# physical island in two and reintroduce the DHCP race, so a mixed ph36/ph37
# fleet never uses per-island mode.
#
# Eligibility is two-tier. VPN-backed bumblebees win: guests must exit through
# a VPN whenever one exists anywhere on the island. When NO candidate has a
# working VPN (total-internet blackout), a local-only terminator is elected
# instead so guest DHCP/RA stay up and free clients keep the NAT66→Yggdrasil
# path to the platform. Local mode is safe by construction: the guest zone only
# forwards to VPN interfaces, so with every VPN down there is no IPv4 egress at
# all — never a raw-WAN exit. The choice is sticky (cache) per island with
# failover when the incumbent goes stale or loses its uplink; a VPN-backed
# candidate immediately displaces a local-only incumbent, while a VPN-loss
# blackout keeps the incumbent seated (no lease churn). `guest_gateway_force`
# keeps a node out of the election entirely — it self-terminates (VPN-gated)
# via its own heartbeat; emergency knob for topologies the election can't see
# (e.g. a solo island on pre-ph37 firmware).
_PH_BUILD_RE = re.compile(r'-ph(\d+)')
_GUEST_GW_MIN_BUILD = 35
_GUEST_GW_FRESH = timedelta(minutes=15)
_GUEST_GW_TTL = 1800  # seconds the cached designation stays sticky

def _ph_build(version: str) -> int:
    """Extract the PARAHUB_BUILD N from a '...-phN' firmware version (0 if absent)."""
    m = _PH_BUILD_RE.search(version or '')
    return int(m.group(1)) if m else 0

def _fresh_bumblebees(now) -> List[IoTDevice]:
    """Fresh mesh-router bumblebees — the election population."""
    fresh = now - _GUEST_GW_FRESH
    return [
        d for d in IoTDevice.objects.filter(device_type='MESH_ROUTER', last_seen__gte=fresh)
        if (d.connection_info or {}).get('firmware_role') == 'bumblebee'
    ]

def _gw_eligible(d: IoTDevice) -> bool:
    """Can this bumblebee be elected to terminate a guest VLAN?"""
    ci = d.connection_info or {}
    if d.guest_gateway_force:
        return False  # forced terminators sit outside the election
    if ci.get('vpn_mode') not in ('vps', 'mullvad'):
        return False
    return _ph_build(ci.get('firmware_version', '')) >= _GUEST_GW_MIN_BUILD

def _gw_local_eligible(d: IoTDevice) -> bool:
    """Fallback tier: can terminate the guest VLAN without a VPN (local-only)."""
    ci = d.connection_info or {}
    if d.guest_gateway_force:
        return False
    return _ph_build(ci.get('firmware_version', '')) >= _GUEST_GW_MIN_BUILD

def _gw_candidates(nodes: List[IoTDevice]) -> List[str]:
    """Sorted terminator candidate MACs, best tier first: VPN-backed if any
    exist, else local-only (blackout mode — see the module comment above)."""
    vpn = sorted(d.device_id for d in nodes if _gw_eligible(d))
    if vpn:
        return vpn
    return sorted(d.device_id for d in nodes if _gw_local_eligible(d))

def _compute_islands(devices: List[IoTDevice]) -> List[List[IoTDevice]]:
    """Union-find over reported topology: A and B share an island when either's
    own mesh MAC appears in the other's originator set."""
    parent = {d.device_id: d.device_id for d in devices}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    topo = {
        d.device_id: (
            set((d.connection_info or {}).get('mesh_macs') or []),
            set((d.connection_info or {}).get('mesh_originators') or []),
        )
        for d in devices
    }
    for a, b in combinations(devices, 2):
        own_a, orig_a = topo[a.device_id]
        own_b, orig_b = topo[b.device_id]
        if own_a & orig_b or own_b & orig_a:
            parent[find(a.device_id)] = find(b.device_id)

    groups = {}
    for d in devices:
        groups.setdefault(find(d.device_id), []).append(d)
    return list(groups.values())

# --- Same-owner L2 bonding (ph55+) -------------------------------------------
# GRETAP over WireGuard over the transit VLAN, hub-spoke, one owner's
# bumblebees within one mesh island. Deterministic hub (own-WAN preferred,
# then lowest MAC) so configs stay stable without cache stickiness; the peer
# LIST uses a generous freshness window so a briefly-offline node does not
# tear the whole bond down, while the HUB must be recently alive (it carries
# the L2 — a stale hub fails over to the next candidate).
_BOND_MIN_BUILD = 55
_BOND_PEER_MAX_AGE = timedelta(days=7)
_BOND_HUB_FRESH = timedelta(minutes=15)

def _mac_octets_45(mac: str) -> tuple:
    """MAC octets 4,5 with the same 0/255 remap of octet 4 the firmware's
    subnet generation applies (uci-defaults §2)."""
    parts = mac.split(':')
    o4, o5 = int(parts[3], 16), int(parts[4], 16)
    if o4 == 0:
        o4 = 1
    if o4 == 255:
        o4 = 254
    return o4, o5

def _transit_ip(mac: str) -> str:
    o4, o5 = _mac_octets_45(mac)
    return f'172.30.{o4}.{o5}'

def _bond_ip(mac: str) -> str:
    o4, o5 = _mac_octets_45(mac)
    return f'172.31.{o4}.{o5}'

def _has_own_wan(d: IoTDevice) -> bool:
    """True when the node's latest telemetry shows a real WAN uplink (not the
    mesh transit or the pre-ph54 flat-L2 fallback)."""
    from ..models import MeshRouterStats
    s = MeshRouterStats.objects.filter(device=d).order_by('-time').first()
    return bool(s and s.uplink_dev and s.uplink_dev not in ('bat0', 'bat0.30', 'br-private'))

def _bond_config(device: IoTDevice, payload, now) -> Optional[BondConfigOut]:
    """Bond role/peers for this node, or None when there is nothing to bond."""
    if payload.firmware_role != 'bumblebee':
        return None
    if _ph_build(payload.firmware_version) < _BOND_MIN_BUILD:
        return None
    cutoff = now - _BOND_PEER_MAX_AGE
    fleet = [
        d for d in IoTDevice.objects.filter(
            device_type='MESH_ROUTER', owner_id=device.owner_id, last_seen__gte=cutoff)
        if (d.connection_info or {}).get('firmware_role') == 'bumblebee'
        and _ph_build((d.connection_info or {}).get('firmware_version', '')) >= _BOND_MIN_BUILD
        and d.wg_public_key
    ]
    if len(fleet) < 2 or not any(d.device_id == device.device_id for d in fleet):
        return None
    # Same mesh island only — the transit VLAN is one radio L2. While any
    # fleet member still runs topology-less firmware, treat the fleet as one
    # island (mirrors the guest-gateway election's fallback).
    if all('mesh_macs' in (d.connection_info or {}) for d in fleet):
        islands = _compute_islands(fleet)
        island = next(
            (i for i in islands if any(d.device_id == device.device_id for d in i)), None)
    else:
        island = fleet
    if not island or len(island) < 2:
        return None
    fresh_cut = now - _BOND_HUB_FRESH
    hub_pool = [d for d in island if d.last_seen and d.last_seen >= fresh_cut] or island
    hub = sorted(hub_pool, key=lambda d: (not _has_own_wan(d), d.device_id))[0]
    if device.device_id == hub.device_id:
        role, peer_devs = 'hub', [d for d in island if d.device_id != hub.device_id]
    else:
        role, peer_devs = 'spoke', [hub]
    return BondConfigOut(
        role=role,
        local_ip=_bond_ip(device.device_id),
        peers=[
            BondPeerOut(
                pubkey=d.wg_public_key,
                endpoint_ip=_transit_ip(d.device_id),
                bond_ip=_bond_ip(d.device_id),
            )
            for d in peer_devs
        ],
    )

def _elect_guest_gateway(mac: str, now) -> Optional[str]:
    """Designated guest-VLAN terminator MAC for the island containing `mac`,
    sticky across heartbeats with failover. Falls back to a single fleet-global
    election while any fresh bumblebee still runs topology-less firmware."""
    bumblebees = _fresh_bumblebees(now)

    if bumblebees and all('mesh_macs' in (d.connection_info or {}) for d in bumblebees):
        island = next(
            (i for i in _compute_islands(bumblebees) if any(d.device_id == mac for d in i)),
            None,
        )
        if island is None:
            return None
        eligible = _gw_candidates(island)
        key = f"mesh_guest_gateway:island:{min(d.device_id for d in island)}"
        if not eligible:
            cache.delete(key)
            return None
        chosen = cache.get(key)
        if chosen not in eligible:
            # Adopt the fleet-global incumbent when it sits on this island, so
            # switching to per-island mode doesn't churn a working gateway.
            legacy = cache.get('mesh_guest_gateway')
            chosen = legacy if legacy in eligible else eligible[0]
        cache.set(key, chosen, _GUEST_GW_TTL)
        return chosen

    # Fleet-global election (mixed / pre-topology fleet)
    eligible = _gw_candidates(bumblebees)
    if not eligible:
        cache.delete('mesh_guest_gateway')
        return None
    current = cache.get('mesh_guest_gateway')
    chosen = current if current in eligible else eligible[0]
    cache.set('mesh_guest_gateway', chosen, _GUEST_GW_TTL)
    return chosen

_DEFAULT_HOST_MBPS = 10

def _island_host_rate(device: IoTDevice, now) -> int:
    """Host-tier budget for this node: min over its island's donor bumblebees'
    `mesh_host_rate_mbps` (excluding the node itself — its budget bounds
    OTHERS on its uplink, and in fallback it can egress via any donor, so the
    tightest one wins). Falls back to the fleet-wide min while topology is
    partial, and to the default when there is no donor at all (then there is
    also no gateway to ride, so the value is moot)."""
    bumblebees = _fresh_bumblebees(now)
    donors = [d for d in bumblebees if d.device_id != device.device_id]
    if bumblebees and all('mesh_macs' in (d.connection_info or {}) for d in bumblebees):
        pool = list(bumblebees)
        if not any(d.device_id == device.device_id for d in pool):
            pool.append(device)
        island = next(
            (i for i in _compute_islands(pool) if any(d.device_id == device.device_id for d in i)),
            None,
        )
        if island is not None:
            donors = [d for d in island
                      if d.device_id != device.device_id
                      and (d.connection_info or {}).get('firmware_role') == 'bumblebee']
    if not donors:
        return _DEFAULT_HOST_MBPS
    return min(d.mesh_host_rate_mbps or _DEFAULT_HOST_MBPS for d in donors)

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

def _stats_rate(cur: int, prev: Optional[int], dt: float) -> Optional[int]:
    """bps between two counter samples; None on a reset (counter went down)."""
    if prev is None or cur < prev:
        return None
    return int((cur - prev) * 8 / dt)


def _record_router_stats(device: IoTDevice, stats, uptime: int, connection_info: dict, now) -> None:
    """One MeshRouterStats row per stats-reporting heartbeat (ph41+).

    Rates derive from the previous sample kept in Redis. An uptime drop marks
    a reboot (all rates null); a lone counter drop (e.g. wifi restart
    recreating guest VAPs) nulls just that pair via _stats_rate.
    """
    from ..models import MeshRouterStats

    prev_key = f'iot:mesh:stats:last:{device.id}'
    prev = cache.get(prev_key)
    rates = {}
    if prev:
        dt = now.timestamp() - prev['ts']
        rebooted = uptime < prev.get('uptime', 0)
        if 60 <= dt <= 3600 and not rebooted:
            rates = {
                'wan_rx_bps': _stats_rate(stats.wan_rx, prev.get('wan_rx'), dt),
                'wan_tx_bps': _stats_rate(stats.wan_tx, prev.get('wan_tx'), dt),
                'guest_rx_bps': _stats_rate(stats.guest_rx, prev.get('guest_rx'), dt),
                'guest_tx_bps': _stats_rate(stats.guest_tx, prev.get('guest_tx'), dt),
            }
    cache.set(prev_key, {
        'ts': now.timestamp(), 'uptime': uptime,
        'wan_rx': stats.wan_rx, 'wan_tx': stats.wan_tx,
        'guest_rx': stats.guest_rx, 'guest_tx': stats.guest_tx,
    }, 7200)

    mesh_macs = connection_info.get('mesh_macs')
    try:
        MeshRouterStats.objects.create(
            time=now,
            device=device,
            uplink_dev=stats.uplink_dev[:16],
            wan_rx_bytes=stats.wan_rx,
            wan_tx_bytes=stats.wan_tx,
            guest_rx_bytes=stats.guest_rx,
            guest_tx_bytes=stats.guest_tx,
            wifi_clients=stats.wifi_clients,
            guest_clients=stats.guest_clients,
            load_1m=stats.load_1m,
            mem_used_pct=(
                round((stats.mem_total - stats.mem_avail) * 100 / stats.mem_total)
                if stats.mem_total > 0 else None
            ),
            mesh_neighbors=len(mesh_macs) if mesh_macs is not None else None,
            uptime=uptime,
            **rates,
        )
    except Exception as e:
        # Telemetry must never fail the heartbeat itself
        logger.warning(f"Mesh stats write failed for {device.id}: {e}")


def _extend_host_pass(device):
    """Hosting reciprocity: a live node keeps its owner's mesh pass covered.

    What you get out of the mesh follows what you put into it — while the node
    heartbeats, its owner's own devices ride at full speed on every node of
    every island, without paying. Coverage lapses on its own once the node
    stops reporting, so this needs no expiry job.

    Devices still sitting in the unclaimed fleet pool are skipped: nobody has
    proven possession of them yet.
    """
    if not settings.MESH_HOST_PASS_DAYS or not device.owner_id:
        return
    if device.owner_id == settings.MESH_DEFAULT_OWNER_PROFILE_ID:
        return
    try:
        credit = ensure_mesh_pass_floor(
            device.owner,
            days=settings.MESH_HOST_PASS_DAYS,
            renew_below_days=settings.MESH_HOST_PASS_RENEW_BELOW_DAYS,
        )
    except Exception as e:
        # Entitlement bookkeeping must never fail node provisioning
        logger.warning(f"Host pass renewal failed for {device.id}: {e}")
        return
    if credit is None:
        return
    logger.info(
        f"Host pass renewed for profile {device.owner_id} "
        f"(+{credit.days}d) from node {device.device_id}"
    )
    # Announce the entitlement once, when it first appears — nobody asked for
    # this pass, so without a nudge a host would only find it by accident.
    # Later renewals stay silent; an owner who already bought one knows.
    try:
        if credit.mesh_pass.credits.count() == 1:
            from notifications.services import notify_mesh_host_pass
            notify_mesh_host_pass(device.owner.account, device)
    except Exception as e:
        logger.warning(f"Host pass notification failed for {device.id}: {e}")


@router.post("/mesh/heartbeat", response=MeshHeartbeatOut, auth=None)
@ratelimit(group='mesh:heartbeat', key='ip', rate='30/m')
def mesh_heartbeat(request: HttpRequest, payload: MeshHeartbeatIn):
    """Phone-home heartbeat from mesh routers (authenticated via shared key)."""
    # Validate Bearer token
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        raise HttpError(401, "Missing Bearer token")

    token = auth_header[7:]
    if not settings.MESH_HEARTBEAT_KEY or not _hmac.compare_digest(token, settings.MESH_HEARTBEAT_KEY):
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
    if payload.private_ap is not None:
        connection_info['private_ap'] = payload.private_ap

    # Mesh topology (ph37+) for per-island guest-gateway election. Key presence
    # marks a topology-reporting node — old firmware omits the fields entirely,
    # and connection_info is rebuilt wholesale so no stale keys survive.
    if payload.mesh_macs is not None:
        connection_info['mesh_macs'] = sorted(
            {m.lower().strip() for m in payload.mesh_macs if MAC_RE.match(m.lower().strip())}
        )[:16]
    if payload.mesh_originators is not None:
        connection_info['mesh_originators'] = sorted(
            {m.lower().strip() for m in payload.mesh_originators if MAC_RE.match(m.lower().strip())}
        )[:512]
    # Originator-table routes (ph50+) for the topology graph. Key presence
    # marks a links-reporting node, same contract as mesh_macs above.
    if payload.mesh_links is not None:
        mesh_links = []
        for link in payload.mesh_links[:256]:
            lo, ln = link.o.lower().strip(), link.n.lower().strip()
            if not (MAC_RE.match(lo) and MAC_RE.match(ln)):
                continue
            mesh_links.append({'o': lo, 'n': ln,
                               't': round(max(0.0, min(float(link.t), 100000.0)), 1)})
        connection_info['mesh_links'] = mesh_links
    # Hardware MACs (ph45+): the claim-by-sticker match set. device_id alone is
    # br-private's address, which need not be the one printed on the label.
    if payload.hw_macs is not None:
        connection_info['hw_macs'] = sorted(
            {m.lower().strip() for m in payload.hw_macs if MAC_RE.match(m.lower().strip())}
        )[:32]

    # Guest leases (ph40+): validated MAC↔IPv4 pairs from the terminator's
    # guest subnet — the ground truth for translating bound device MACs into
    # the per-node paid_clients IP list.
    guest_leases = []
    if payload.guest_leases is not None:
        for lease in payload.guest_leases[:256]:
            lmac = lease.mac.lower().strip()
            if not MAC_RE.match(lmac):
                continue
            try:
                lip = str(ipaddress.IPv4Address(lease.ip.strip()))
            except ValueError:
                continue
            guest_leases.append({'mac': lmac, 'ip': lip, 'host': lease.host.strip()[:64]})
        connection_info['guest_leases'] = guest_leases

    now = timezone.now()

    # Resolve default owner for new devices
    try:
        default_owner = Profile.objects.get(id=settings.MESH_DEFAULT_OWNER_PROFILE_ID)
    except Profile.DoesNotExist:
        logger.error(f"Default mesh owner profile {settings.MESH_DEFAULT_OWNER_PROFILE_ID} not found")
        raise HttpError(500, "Mesh owner profile not configured")

    # Check if device already exists (to avoid overwriting owner on update)
    # owner joined in: _extend_host_pass needs it, and a join beats a second
    # round trip on a path every node walks every 5 minutes.
    existing = IoTDevice.objects.filter(
        device_id=mac, device_type='MESH_ROUTER').select_related('owner').first()

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

    if payload.stats is not None:
        _record_router_stats(device, payload.stats, payload.uptime, connection_info, now)

    _extend_host_pass(device)

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

    # Paid clients for speed control: bound devices with an active pass whose
    # MAC appears in THIS node's guest leases → their current IPs. Nodes that
    # report no leases (relays, bees, old firmware) get an empty list.
    active_ips = []
    if guest_leases:
        active_macs = set(MeshDevice.objects.filter(
            mesh_pass__expires_at__gt=now,
        ).values_list('mac', flat=True))
        matched = [l for l in guest_leases if l['mac'] in active_macs]
        active_ips = [l['ip'] for l in matched]
        for lease in matched:
            MeshDevice.objects.filter(mac=lease['mac']).update(
                last_ipv4=lease['ip'], last_gateway=device, last_seen_at=now,
            )

    # Yggdrasil ACL: allowed inbound IPv6 addresses
    ygg_allowed = device.ygg_allowed_ips or []

    # Guest-VLAN gateway election: tell exactly one bumblebee per mesh island to
    # terminate its guest VLAN (DHCP + VPN exit); every other node relays L2-only.
    # Two-tier: VPN-backed candidates win, an all-VPN-down island elects a
    # local-only terminator (blackout mode — guest keeps the NAT66→ygg platform
    # path; the guest firewall zone has no raw-WAN forward, so IPv4 egress stays
    # impossible). guest_gateway_force bypasses the election for topologies it
    # can't see, still gated on an active VPN.
    guest_gateway = False
    if payload.firmware_role == 'bumblebee':
        if device.guest_gateway_force:
            guest_gateway = payload.vpn_mode in ('vps', 'mullvad')
        else:
            guest_gateway = _elect_guest_gateway(mac, now) == mac

    return MeshHeartbeatOut(
        status="ok", device_id=device.id, paid_clients=active_ips,
        ygg_allowed=ygg_allowed, vps_gateway=vps_gateway,
        guest_gateway=guest_gateway,
        bond=_bond_config(device, payload, now),
        ygg_inbound_dead=ygg_inbound_status(mac) is False,
        rates=MeshRatesOut(
            guest_kbps=device.mesh_guest_rate_kbps or 512,
            host_mbps=_island_host_rate(device, now),
        ),
        latitude=device.latitude,
        longitude=device.longitude,
    )

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
    device = get_device_for(request.auth_profile, device_id, ROLE_MANAGER, require_mesh=True)
    return YggAccessOut(ygg_allowed_ips=device.ygg_allowed_ips or [])

@router.post("/devices/{device_id}/ygg-access", response=YggAccessOut, auth=ProfileAuth())
@ratelimit(group='iot:ygg_add', key=user_or_ip, rate='30/m', method='POST')
def add_ygg_access(request, device_id: str, payload: YggAccessIn):
    """Add an IPv6 address to the Yggdrasil inbound whitelist."""
    device = get_device_for(request.auth_profile, device_id, ROLE_MANAGER, require_mesh=True)

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
    device = get_device_for(request.auth_profile, device_id, ROLE_MANAGER, require_mesh=True)

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
    if not settings.MESH_HEARTBEAT_KEY or not _hmac.compare_digest(token, settings.MESH_HEARTBEAT_KEY):
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
    device = get_device_for(request.auth_profile, device_id, ROLE_MANAGER, require_mesh=True)

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
    device = get_device_for(request.auth_profile, device_id, ROLE_MANAGER, require_mesh=True)

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

# Fleet-wide shared-wifi ESSID baked into the firmware (open guest VLAN)
GUEST_WIFI_SSID = 'parahub.io/free'

# How old the newest MeshRouterStats row may be to still count as the router's
# current public readout (heartbeats come every 5 min)
_PUBLIC_STATS_FRESH = timedelta(minutes=30)

class MeshRouterPublicOut(Schema):
    # ULID of the IoTDevice — inert for strangers, lets the owner's map panel
    # fetch the owner-gated /devices/{id} detail on marker click
    device_id: str
    name: str
    latitude: float
    longitude: float
    hardware_profile: Optional[str] = None
    status: str = "offline"
    # Public heartbeat subset for the map HUD. guest_ssid on any non-offline
    # router; the counters only from a fresh stats row (ph41+ firmware).
    # Deliberately NEVER exposed here: private SSID, firmware version,
    # Yggdrasil/mesh addresses, MACs, leases, load/mem.
    guest_ssid: Optional[str] = None
    wifi_clients: Optional[int] = None
    mesh_links: Optional[int] = None
    # Owner attribution — only when the owner opted in via show_owner
    owner_name: Optional[str] = None
    owner_cri: Optional[str] = None
    uptime: Optional[int] = None

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
    device = get_device_for(request.auth_profile, device_id, ROLE_MANAGER, require_mesh=True)

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
        # All routers this user manages (own + MANAGER grants) that actually
        # broadcast the private AP. The firmware gates the AP on dual-band
        # hardware, not on role — a dual-band bee has one and must not fall
        # out of a fleet-wide rotation. private_ap is reported by ph54+
        # heartbeats; older nodes fall back to the role heuristic (their only
        # bees are single-band, where skipping is correct).
        def _has_private_ap(r: IoTDevice) -> bool:
            ci = r.connection_info or {}
            pap = ci.get('private_ap')
            if pap is not None:
                return bool(pap)
            return ci.get('firmware_role') != 'bee'

        all_routers = list(IoTDevice.objects.filter(
            accessible_q(request.auth_profile, ROLE_MANAGER),
            device_type='MESH_ROUTER',
        ))
        targets = [r for r in all_routers if _has_private_ap(r)]
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

    devices = IoTDevice.objects.filter(accessible_q(profile), device_type='MESH_ROUTER')
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
    from ..models import MeshRouterStats

    devices = list(IoTDevice.objects.filter(
        device_type='MESH_ROUTER',
        latitude__isnull=False,
        longitude__isnull=False,
    ).select_related('owner'))
    now = timezone.now()

    # Latest fresh stats row per device in one query (ph41+ heartbeats only)
    stats_by_device = {
        s.device_id: s
        for s in MeshRouterStats.objects.filter(
            device__in=devices,
            time__gte=now - _PUBLIC_STATS_FRESH,
        ).order_by('device_id', '-time').distinct('device_id')
    }

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
        row = MeshRouterPublicOut(
            device_id=device.id,
            name=device.name,
            latitude=device.latitude,
            longitude=device.longitude,
            hardware_profile=ci.get('hardware_profile'),
            status=status,
        )
        # Attribution is static (owner opt-in), not heartbeat data — offline
        # routers keep it too
        if device.show_owner:
            row.owner_name, row.owner_cri = public_owner_fields(device.owner)
        if status != 'offline':
            row.guest_ssid = GUEST_WIFI_SSID
            stats = stats_by_device.get(device.id)
            if stats is not None:
                row.wifi_clients = (stats.wifi_clients or 0) + (stats.guest_clients or 0)
                row.mesh_links = stats.mesh_neighbors
                row.uptime = stats.uptime
        result.append(row)

    return result

# --- Mesh pass: account-level speed upgrade -----------------------------------
# Entitlement lives on the profile (MeshPass, extended by Lightning payments or
# achievement grants); enforcement is per device MAC (MeshDevice). Binding a
# device only works from inside the mesh: an on-mesh guest's API request
# reaches nginx's Yggdrasil listener NAT66-masqueraded to its node's address,
# and that node's conntrack + neighbor tables resolve the request's source
# port back to the client's MAC deterministically. The ygg nginx server blocks
# stamp X-Ygg-Gate (shared secret) + X-Ygg-Client-IP/Port; the gate token
# proves the headers came from the trusted listener, not from a spoofing
# client on a public vhost.

_ULA_NET = ipaddress.ip_network('fc00::/7')       # guest clients (NAT66'd)
_YGG_PRIVATE_NET = ipaddress.ip_network('300::/8')  # private clients (SLAAC)

class MeshNetworkOut(Schema):
    on_mesh: bool
    network: Optional[str] = None  # 'guest' | 'private'
    node_hostname: Optional[str] = None
    # Map deep-link target (/map?device=mesh:{id}); only set when the node has
    # coordinates — a link to a node the map layer can't resolve goes nowhere.
    node_id: Optional[str] = None

class MeshDeviceOut(Schema):
    id: str
    mac: str
    label: str
    last_ipv4: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    created_at: datetime

class MeshPassOut(Schema):
    active: bool
    expires_at: Optional[datetime] = None
    max_devices: int
    devices: List[MeshDeviceOut] = []
    price_sats: int
    duration_days: int
    payments_available: bool
    from_hosting: bool = False  # pass is being kept alive by a node the caller hosts

class MeshInvoiceOut(Schema):
    invoice: str
    payment_hash: str
    amount_sats: int
    expires_minutes: int = 15

class MeshInvoiceStatusOut(Schema):
    status: str  # 'pending' | 'paid' | 'expired'
    pass_expires_at: Optional[datetime] = None

class MeshBindOut(Schema):
    status: str = 'bound'
    device: MeshDeviceOut
    activated: bool  # speed applied instantly (else within one heartbeat)

def _get_mesh_lnbits() -> LNbitsProvider:
    """Create LNbits provider from mesh settings."""
    if not settings.MESH_LNBITS_URL or not settings.MESH_LNBITS_INVOICE_KEY:
        raise HttpError(503, "Lightning payments not configured")
    return LNbitsProvider(
        api_url=settings.MESH_LNBITS_URL,
        invoice_key=settings.MESH_LNBITS_INVOICE_KEY,
    )

def _device_out(d: MeshDevice) -> MeshDeviceOut:
    return MeshDeviceOut(
        id=d.id, mac=d.mac, label=d.label, last_ipv4=d.last_ipv4,
        last_seen_at=d.last_seen_at, created_at=d.created_at,
    )

def _ygg_client(request: HttpRequest):
    """(source_ip, source_port) of a request that arrived via the trusted
    Yggdrasil nginx listener; (None, None) for any other path. Trust comes
    from the X-Ygg-Gate shared secret that only the ygg server blocks stamp —
    a spoofed copy arriving via public vhosts doesn't know the token."""
    gate = request.META.get('HTTP_X_YGG_GATE', '')
    token = settings.MESH_YGG_GATE_TOKEN
    if not token or not _hmac.compare_digest(gate, token):
        return None, None
    try:
        ip = str(ipaddress.IPv6Address(request.META.get('HTTP_X_YGG_CLIENT_IP', '')))
        port = int(request.META.get('HTTP_X_YGG_CLIENT_PORT', ''))
        if not 0 < port < 65536:
            raise ValueError
    except ValueError:
        return None, None
    return ip, port

def _fresh_node_by_ygg(ip: str) -> Optional[IoTDevice]:
    """Fresh mesh router whose Yggdrasil address equals `ip` (normalized)."""
    try:
        target = ipaddress.IPv6Address(ip)
    except ValueError:
        return None
    fresh = timezone.now() - _GUEST_GW_FRESH
    for d in IoTDevice.objects.filter(device_type='MESH_ROUTER', last_seen__gte=fresh):
        addr = (d.connection_info or {}).get('yggdrasil_address', '')
        try:
            if addr and ipaddress.IPv6Address(addr) == target:
                return d
        except ValueError:
            continue
    return None

def _parse_conntrack_client(ct_text: str, port: int) -> Optional[str]:
    """Find the NAT66 conntrack entry whose reply tuple is our request
    (sport 443/80, dport == masqueraded source port) and return the original
    source — the client's ULA address. /proc/net/nf_conntrack prints two
    tuples per line: original (client → backend), then reply (backend → node)."""
    for line in ct_text.splitlines():
        if not line.startswith('ipv6'):
            continue
        pairs = re.findall(r'(\w+)=(\S+)', line)
        srcs = [v for k, v in pairs if k == 'src']
        sports = [v for k, v in pairs if k == 'sport']
        dports = [v for k, v in pairs if k == 'dport']
        if len(srcs) < 2 or len(sports) < 2 or len(dports) < 2:
            continue
        if sports[1] in ('443', '80') and dports[1] == str(port):
            try:
                client = ipaddress.IPv6Address(srcs[0])
            except ValueError:
                continue
            if client in _ULA_NET:
                return str(client)
    return None

def _parse_neigh_mac(neigh_text: str, client_ip6: str) -> Optional[str]:
    """Resolve an IPv6 neighbor entry to its MAC ('<ip> dev X lladdr <mac> STATE')."""
    target = ipaddress.IPv6Address(client_ip6)
    for line in neigh_text.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3] == 'lladdr':
            try:
                if ipaddress.IPv6Address(parts[0]) == target:
                    mac = parts[4].lower()
                    if MAC_RE.match(mac):
                        return mac
            except ValueError:
                continue
    return None

def _guest_lease_for_mac(terminator: Optional[IoTDevice], mac: str):
    """(ipv4, hostname) of `mac` on the terminator's guest subnet — from its
    last heartbeat leases, falling back to a live SSH read for clients that
    joined after the last heartbeat."""
    if terminator is None:
        return None, ''
    for lease in (terminator.connection_info or {}).get('guest_leases', []):
        if lease.get('mac') == mac:
            return lease.get('ip'), lease.get('host', '')

    ygg_addr = (terminator.connection_info or {}).get('yggdrasil_address')
    if not ygg_addr:
        return None, ''
    try:
        res = _mesh_ssh(ygg_addr, "uci -q get network.guest.ipaddr; cat /tmp/dhcp.leases 2>/dev/null")
    except subprocess.TimeoutExpired:
        return None, ''
    if res.returncode != 0:
        return None, ''
    lines = res.stdout.splitlines()
    if not lines:
        return None, ''
    prefix = '.'.join(lines[0].strip().split('.')[:3]) + '.'
    if not re.match(r'^\d+\.\d+\.\d+\.$', prefix):
        return None, ''
    for line in lines[1:]:
        fields = line.split()
        if len(fields) >= 4 and fields[1].lower() == mac and fields[2].startswith(prefix):
            host = fields[3] if fields[3] != '*' else ''
            return fields[2], host
    return None, ''

@router.get("/mesh/network", response=MeshNetworkOut, auth=None)
@ratelimit(group='mesh:network', key='ip', rate='60/m')
def mesh_network(request: HttpRequest):
    """Which Parahub network (if any) the client is browsing from."""
    ip, _port = _ygg_client(request)
    if not ip:
        return MeshNetworkOut(on_mesh=False)
    node = _fresh_node_by_ygg(ip)
    if node:
        has_position = node.latitude is not None and node.longitude is not None
        return MeshNetworkOut(
            on_mesh=True, network='guest',
            node_hostname=(node.connection_info or {}).get('hostname'),
            node_id=node.id if has_position else None,
        )
    if ipaddress.IPv6Address(ip) in _YGG_PRIVATE_NET:
        return MeshNetworkOut(on_mesh=True, network='private')
    return MeshNetworkOut(on_mesh=False)

@router.get("/mesh/pass", response=MeshPassOut, auth=ProfileAuth())
def mesh_pass_status(request):
    """The caller's mesh pass: activity, expiry, bound devices, pricing."""
    profile = request.auth_profile
    now = timezone.now()
    mp = MeshPass.objects.filter(profile=profile).first()
    devices = list(mp.devices.order_by('created_at')) if mp else []
    # A node quiet for a day no longer explains the pass — it keeps running on
    # whatever coverage the last heartbeat bought, so stop crediting hosting.
    from_hosting = bool(settings.MESH_HOST_PASS_DAYS) and IoTDevice.objects.filter(
        owner=profile, device_type='MESH_ROUTER', last_seen__gt=now - timedelta(days=1),
    ).exists()
    return MeshPassOut(
        active=bool(mp and mp.expires_at > now),
        expires_at=mp.expires_at if mp else None,
        max_devices=mp.max_devices if mp else settings.MESH_PASS_MAX_DEVICES,
        devices=[_device_out(d) for d in devices],
        price_sats=config.MESH_SUBSCRIPTION_PRICE_SATS,
        duration_days=config.MESH_SUBSCRIPTION_DURATION_DAYS,
        payments_available=bool(settings.MESH_LNBITS_URL and settings.MESH_LNBITS_INVOICE_KEY),
        from_hosting=from_hosting,
    )

@router.post("/mesh/pass/invoice", response=MeshInvoiceOut, auth=ProfileAuth())
@ratelimit(group='mesh:invoice', key=user_or_ip, rate='5/m')
def mesh_pass_invoice(request):
    """Create a Lightning invoice extending the caller's mesh pass."""
    profile = request.auth_profile
    lnbits = _get_mesh_lnbits()
    amount = config.MESH_SUBSCRIPTION_PRICE_SATS
    days = config.MESH_SUBSCRIPTION_DURATION_DAYS
    try:
        invoice = lnbits.create_invoice(amount_sats=amount, memo=f"Parahub mesh pass ({days}d)")
    except Exception as e:
        logger.error(f"Failed to create LN invoice: {e}")
        raise HttpError(503, "Failed to create invoice")

    mp, _ = MeshPass.objects.get_or_create(
        profile=profile,
        defaults={'expires_at': timezone.now(), 'max_devices': settings.MESH_PASS_MAX_DEVICES},
    )
    MeshPassCredit.objects.create(
        mesh_pass=mp, source='LIGHTNING', days=days, amount_sats=amount,
        ln_payment_hash=invoice.payment_hash, ln_invoice=invoice.payment_request,
        status='PENDING',
    )
    return MeshInvoiceOut(
        invoice=invoice.payment_request,
        payment_hash=invoice.payment_hash,
        amount_sats=amount,
        expires_minutes=15,
    )

@router.get("/mesh/pass/invoice/{payment_hash}", response=MeshInvoiceStatusOut, auth=ProfileAuth())
@ratelimit(group='mesh:invoice_status', key=user_or_ip, rate='30/m')
def mesh_pass_invoice_status(request, payment_hash: str):
    """Poll a pass invoice; applies the credit when LNbits reports it paid."""
    profile = request.auth_profile
    credit = MeshPassCredit.objects.filter(
        ln_payment_hash=payment_hash, mesh_pass__profile=profile,
    ).select_related('mesh_pass').first()
    if not credit:
        raise HttpError(404, "Invoice not found")

    if credit.status == 'APPLIED':
        return MeshInvoiceStatusOut(status='paid', pass_expires_at=credit.mesh_pass.expires_at)
    if credit.status == 'EXPIRED':
        return MeshInvoiceStatusOut(status='expired')

    try:
        result = _get_mesh_lnbits().check_invoice(payment_hash)
    except Exception as e:
        logger.error(f"Failed to check LN invoice {payment_hash}: {e}")
        return MeshInvoiceStatusOut(status='pending')

    if result.get('paid'):
        with transaction.atomic():
            locked = MeshPassCredit.objects.select_for_update().get(id=credit.id)
            if locked.status == 'PENDING':
                grant_mesh_pass(profile, locked.days, credit=locked)
        mp = MeshPass.objects.get(profile=profile)
        return MeshInvoiceStatusOut(status='paid', pass_expires_at=mp.expires_at)

    return MeshInvoiceStatusOut(status='pending')

@router.post("/mesh/bind", response=MeshBindOut, auth=ProfileAuth())
@ratelimit(group='mesh:bind', key=user_or_ip, rate='5/m')
def mesh_bind(request: HttpRequest):
    """Bind the requesting device (by its WiFi MAC) to the caller's pass.

    Guest-network requests only: the ygg listener headers identify the NAT66
    node, its conntrack maps our source port to the client's ULA, its neighbor
    table maps the ULA to the MAC, and the island terminator's guest leases
    map the MAC to the current IPv4 for instant activation.
    """
    profile = request.auth_profile
    now = timezone.now()
    mp = MeshPass.objects.filter(profile=profile).first()
    if not mp or mp.expires_at <= now:
        raise HttpError(409, "no_active_pass")

    ip, port = _ygg_client(request)
    if not ip:
        raise HttpError(409, "not_on_mesh")
    node = _fresh_node_by_ygg(ip)
    if not node:
        if ipaddress.IPv6Address(ip) in _YGG_PRIVATE_NET:
            raise HttpError(409, "on_private_network")
        raise HttpError(409, "not_on_mesh")

    node_ygg = (node.connection_info or {}).get('yggdrasil_address')
    try:
        res = _mesh_ssh(
            node_ygg,
            "grep -E 'sport=(443|80) ' /proc/net/nf_conntrack 2>/dev/null; echo ==NEIGH==; ip -6 neigh show",
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise HttpError(504, "node_unreachable")
    if res.returncode != 0:
        logger.warning(f"mesh_bind: SSH to {node_ygg} failed: {res.stderr.strip()}")
        raise HttpError(504, "node_unreachable")

    ct_text, _, neigh_text = res.stdout.partition('==NEIGH==')
    client6 = _parse_conntrack_client(ct_text, port)
    if not client6:
        raise HttpError(409, "client_not_found")
    mac = _parse_neigh_mac(neigh_text, client6)
    if not mac:
        raise HttpError(409, "client_not_found")

    term_mac = _elect_guest_gateway(node.device_id, now)
    term = None
    if term_mac:
        term = IoTDevice.objects.filter(device_id=term_mac, device_type='MESH_ROUTER').first()
    ipv4, host = _guest_lease_for_mac(term, mac)

    # Serialize the limit check + write against concurrent binds on the same
    # pass — two different new MACs could otherwise both pass count < max and
    # push the pass to max+1. Lock the pass row; the slow SSH work above and
    # the speed-control call below stay outside the transaction.
    with transaction.atomic():
        mp = MeshPass.objects.select_for_update().get(id=mp.id)
        existing = MeshDevice.objects.filter(mac=mac).select_related('mesh_pass').first()
        if existing and existing.mesh_pass_id != mp.id:
            raise HttpError(409, "device_bound_elsewhere")
        if not existing and mp.devices.count() >= mp.max_devices:
            raise HttpError(409, "device_limit_reached")

        if existing:
            existing.last_seen_at = now
            if ipv4:
                existing.last_ipv4 = ipv4
                existing.last_gateway = term or node
            if not existing.label and host:
                existing.label = host
            existing.save()
            device_row = existing
        else:
            device_row = MeshDevice.objects.create(
                mesh_pass=mp, mac=mac, label=host or '',
                last_ipv4=ipv4,
                last_gateway=(term or node) if ipv4 else None,
                last_seen_at=now if ipv4 else None,
            )

    # Instant activation on the terminator; the 5-min heartbeat self-heals
    # anything missed here (no lease yet, SSH hiccup).
    activated = False
    if ipv4 and term:
        term_ygg = (term.connection_info or {}).get('yggdrasil_address')
        if term_ygg:
            try:
                r = _mesh_ssh(term_ygg, f"parahub-speed-control add {shlex.quote(ipv4)}")
                activated = r.returncode == 0
            except subprocess.TimeoutExpired:
                pass

    logger.info(f"mesh_bind: {mac} → pass {mp.id} (ipv4={ipv4}, activated={activated})")
    return MeshBindOut(device=_device_out(device_row), activated=activated)

@router.delete("/mesh/devices/{mesh_device_id}", auth=ProfileAuth())
@ratelimit(group='mesh:unbind', key=user_or_ip, rate='10/m')
def mesh_unbind(request, mesh_device_id: str):
    """Remove a device from the caller's pass (frees a slot, drops its speed)."""
    profile = request.auth_profile
    device_row = MeshDevice.objects.filter(
        id=mesh_device_id, mesh_pass__profile=profile,
    ).select_related('last_gateway').first()
    if not device_row:
        raise HttpError(404, "Device not found")

    if device_row.last_ipv4 and device_row.last_gateway:
        ygg_addr = (device_row.last_gateway.connection_info or {}).get('yggdrasil_address')
        if ygg_addr:
            try:
                _mesh_ssh(ygg_addr, f"parahub-speed-control remove {shlex.quote(device_row.last_ipv4)}")
            except subprocess.TimeoutExpired:
                pass

    device_row.delete()
    return {"status": "removed"}


# --- Fleet topology graph (staff) ---------------------------------------------

class MeshGraphNodeOut(Schema):
    id: str                      # IoTDevice ULID (links to /iot)
    mac: str                     # device_id (br-private MAC)
    hostname: str
    name: str = ""
    role: str = "unknown"
    firmware_version: str = "unknown"
    vpn_mode: str = "unknown"
    fresh: bool = False          # heartbeat within the election window
    last_seen: Optional[datetime] = None
    uptime: int = 0
    island: int = 0              # index into the response's island grouping
    is_terminator: bool = False  # elected guest-VLAN terminator
    reports_links: bool = False  # ph50+ firmware, direct edges available
    wifi_clients: Optional[int] = None
    guest_clients: Optional[int] = None


class MeshGraphEdgeOut(Schema):
    source: str                    # node ULID
    target: str                    # node ULID
    tp_ab: Optional[float] = None  # Mbit/s, link as measured by source
    tp_ba: Optional[float] = None  # Mbit/s, link as measured by target
    inferred: bool = False         # same-island sight only (pre-ph50 endpoints)


class MeshGraphOut(Schema):
    nodes: List[MeshGraphNodeOut]
    edges: List[MeshGraphEdgeOut]
    islands: int
    fresh_nodes: int


_GRAPH_NODE_HORIZON = timedelta(days=7)
_GRAPH_LINK_HORIZON = timedelta(hours=1)


@router.get("/mesh/graph", response=MeshGraphOut, auth=ProfileAuth())
@ratelimit(group='mesh:graph', key=user_or_ip, rate='30/m')
def mesh_graph(request):
    """Fleet mesh topology graph.

    Staff only — the fleet-wide picture (heartbeat state, VPN modes, elected
    terminators) is operator data; owners see their own devices on /iot.

    Nodes: mesh routers seen within 7 days, plus any older device a live node
    still routes to (mesh alive, heartbeat dead — the interesting diagnostic).
    Direct edges come from ph50+ originator tables: a row whose nexthop
    interface belongs to the same node as the originator is a direct radio
    link, with BATMAN_V throughput per reporting side. Pairs where neither
    endpoint reports links fall back to a dashed "sees in island" edge.
    """
    profile = request.auth_profile
    if not profile.account.is_staff:
        raise HttpError(403, "Staff only")

    from ..models import MeshRouterStats

    now = timezone.now()
    all_routers = list(IoTDevice.objects.filter(device_type='MESH_ROUTER'))
    iface_owner = {}
    for d in all_routers:
        for m in (d.connection_info or {}).get('mesh_macs') or []:
            iface_owner[m] = d

    horizon = now - _GRAPH_NODE_HORIZON
    nodes = {d.device_id: d for d in all_routers
             if d.last_seen and d.last_seen >= horizon}

    # Direct links from recent reporters. Max throughput per direction — a
    # node pair usually shares several radio paths (two bands x two ifaces).
    link_cut = now - _GRAPH_LINK_HORIZON
    reporters = [d for d in all_routers
                 if d.last_seen and d.last_seen >= link_cut
                 and 'mesh_links' in (d.connection_info or {})]
    direct = {}  # (reporter_mac, neighbor_mac) -> max Mbit/s
    for d in reporters:
        for row in (d.connection_info or {}).get('mesh_links') or []:
            neigh = iface_owner.get(row.get('o'))
            if neigh is None or neigh.device_id == d.device_id:
                continue
            if iface_owner.get(row.get('n')) is not neigh:
                continue  # route via a third node — not adjacency
            key = (d.device_id, neigh.device_id)
            tp = float(row.get('t') or 0)
            if tp > direct.get(key, -1.0):
                direct[key] = tp
            # a live node routes to it: keep it on the graph even when its
            # own heartbeat is long dead
            nodes.setdefault(neigh.device_id, neigh)

    edges = []
    seen_pairs = set()
    for (a_mac, b_mac) in list(direct.keys()):
        pair = tuple(sorted((a_mac, b_mac)))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        edges.append(MeshGraphEdgeOut(
            source=nodes[pair[0]].id,
            target=nodes[pair[1]].id,
            tp_ab=direct.get((pair[0], pair[1])),
            tp_ba=direct.get((pair[1], pair[0])),
        ))

    # Fallback sight edges — only when NEITHER endpoint reports links: a
    # reporting endpoint's table decides adjacency for the whole pair, so its
    # absence there means multi-hop, not a missing edge.
    macs_of = {m: set((d.connection_info or {}).get('mesh_macs') or [])
               for m, d in nodes.items()}
    origs_of = {m: set((d.connection_info or {}).get('mesh_originators') or [])
                for m, d in nodes.items()}
    for a, b in combinations(nodes.values(), 2):
        if ('mesh_links' in (a.connection_info or {})
                or 'mesh_links' in (b.connection_info or {})):
            continue
        pair = tuple(sorted((a.device_id, b.device_id)))
        if pair in seen_pairs:
            continue
        if (macs_of[a.device_id] & origs_of[b.device_id]
                or macs_of[b.device_id] & origs_of[a.device_id]):
            seen_pairs.add(pair)
            edges.append(MeshGraphEdgeOut(
                source=nodes[pair[0]].id, target=nodes[pair[1]].id,
                inferred=True))

    # Island indices over the graph population (bees included) — purely a
    # display grouping, unrelated to the election's fresh-bumblebee islands.
    island_idx = {}
    groups = sorted(_compute_islands(list(nodes.values())),
                    key=lambda g: min(d.device_id for d in g))
    for idx, group in enumerate(groups):
        for d in group:
            island_idx[d.device_id] = idx

    # Elected terminators: read the election's sticky cache without voting.
    terminators = set()
    bumblebees = _fresh_bumblebees(now)
    if bumblebees and all('mesh_macs' in (d.connection_info or {}) for d in bumblebees):
        for isl in _compute_islands(bumblebees):
            mac = cache.get(f"mesh_guest_gateway:island:{min(d.device_id for d in isl)}")
            if mac:
                terminators.add(mac)
    else:
        mac = cache.get('mesh_guest_gateway')
        if mac:
            terminators.add(mac)
    for d in nodes.values():
        if d.guest_gateway_force and \
                (d.connection_info or {}).get('vpn_mode') in ('vps', 'mullvad'):
            terminators.add(d.device_id)

    latest_stats = {
        s.device_id: s for s in MeshRouterStats.objects.filter(
            device_id__in=[d.id for d in nodes.values()],
            time__gte=link_cut,
        ).order_by('device_id', '-time').distinct('device_id')
    }

    fresh_cut = now - _GUEST_GW_FRESH
    out_nodes = []
    for d in sorted(nodes.values(), key=lambda x: (x.connection_info or {}).get('hostname') or x.device_id):
        ci = d.connection_info or {}
        st = latest_stats.get(d.id)
        out_nodes.append(MeshGraphNodeOut(
            id=d.id,
            mac=d.device_id,
            hostname=ci.get('hostname') or d.name or d.device_id,
            name=d.name or "",
            role=ci.get('firmware_role') or 'unknown',
            firmware_version=ci.get('firmware_version') or 'unknown',
            vpn_mode=ci.get('vpn_mode') or 'unknown',
            fresh=bool(d.last_seen and d.last_seen >= fresh_cut),
            last_seen=d.last_seen,
            uptime=int(ci.get('uptime') or 0),
            island=island_idx.get(d.device_id, 0),
            is_terminator=d.device_id in terminators,
            reports_links='mesh_links' in ci,
            wifi_clients=st.wifi_clients if st else None,
            guest_clients=st.guest_clients if st else None,
        ))

    return MeshGraphOut(
        nodes=out_nodes,
        edges=edges,
        islands=len(groups),
        fresh_nodes=sum(1 for n in out_nodes if n.fresh),
    )
