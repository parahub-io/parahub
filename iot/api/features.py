"""
Per-router feature toggles over mesh SSH: Mullvad exit, speed limit,
LAN VPN, wired mesh, diagnostics.
"""


from typing import List, Optional
import logging
import subprocess
import shlex
from ninja import Schema
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from ..models import IoTDevice

from .base import router
from .mesh import _mesh_ssh

logger = logging.getLogger(__name__)

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
