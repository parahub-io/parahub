# Mesh Network

Community-owned internet infrastructure using OpenWrt firmware with batman-adv mesh networking and Yggdrasil overlay.

## Firmware

Two firmware profiles built with OpenWrt 25.x ImageBuilder:
- **Bumblebee** -- L3 gateway, full stack (routing, DHCP, DNS, speed control, paid WiFi). Devices: AXT1800, MT3000, MT6000, AX53U
- **Bee** -- L2 relay, minimal (mesh backhaul + WiFi AP only). Devices: AR300M16, CPE710

Zero-touch provisioning via `99-parahub-mesh` uci-defaults (runs once, deletes self). Separate repository: `/opt/parahub-mesh/`.

## Network Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| L2 Mesh | batman-adv | Layer-2 mesh routing between nodes |
| L3 Overlay | Yggdrasil | IPv6 overlay network for global addressability |
| VPN Exit | WireGuard | Gateway to regular internet via VPS |
| WiFi | hostapd | Access point for end users |

### How It Works

1. Mesh nodes discover each other via batman-adv (WiFi or Ethernet)
2. Yggdrasil provides globally routable IPv6 addresses
3. WireGuard tunnel to VPS provides internet exit for clients
4. End users connect to WiFi AP and get internet access

## Features

- **Dual WiFi**: Private `Parahub` (802.11r/k/v roaming, both bands) + Free `parahub.io/free` (open — OWE reverted until an OpenWrt 25.12.x hostapd bug is fixed upstream)
- **Speed Control**: nftables + tc HTB (per-guest rate, 512 kbps default; host budget on Bee, 10 Mbps default; paid = full speed via Lightning). Both defaults are gateway-owner settings in /iot
- **Paid WiFi**: Lightning invoice per IP, 30-day subscriptions, nftables sync
- **OTA Auto-Updates**: Nightly 3am (Yggdrasil first, public fallback), manifest.json SHA256 verification
- **Coverage Map**: Mesh node locations on Parahub map
- **Heartbeat**: 5-minute cron, sends MAC/Yggdrasil/firmware/WG pubkey, receives paid clients + VPS config + ACL whitelist
- **VPS Gateway**: Shared WireGuard exit via VPS. 3-state health check (server/mesh fallback/isolated)
- **Anycast Gateway**: Bumblebees in `gw_mode=server` add `10.250.250.1/32` on br-private for reliable node discovery
- **Yggdrasil Inbound ACL**: Per-device `ygg_allowed_ips` whitelist, synced via heartbeat. Secure-by-default private IPv6 access
- **DoH**: https-dns-proxy (Cloudflare) for encrypted DNS

## Integration with Parahub

- Mesh nodes register as IoT devices on the platform
- Heartbeat reports sent to `/api/v1/iot/mesh/heartbeat/`
- Account-level speed pass (`MeshPass`) with per-device binding (`MeshDevice`)
- Coverage layer on the map shows active mesh nodes

## Ownership and Sharing

Applies to **every device you register**, not just mesh routers -- GPS trackers and environmental sensors share the same model.

- **Claiming a router**: a factory-fresh router reports in under a fleet account until someone claims it by typing the full hardware address printed on its sticker. Typing that address is the proof that you physically hold the device, which is why there is deliberately no browsable list of unclaimed routers.
- **Sharing**: the owner can grant another profile **viewer** (see the device, its status, telemetry history and, for a tracker, its live position) or **manager** (also configure it -- rename, WiFi, speed limits, network settings, diagnostics). Only the owner can delete a device, manage grants, or hand it over.
- **Transfer**: ownership can be handed to another profile, optionally leaving the previous owner manager access -- the normal path when someone sets a router up for a neighbour and stays on call for support.
- **Traceability**: claims and transfers are written to an ownership log, and grants, claims and transfers all notify the people involved.
- **Honest boundary**: these roles govern what the platform's interface allows. Physical control of a router is a firmware matter -- whoever maintains the fleet firmware retains low-level access, which is why a maintenance grant on a claimed router is shown in the interface and can be revoked there.

## Use Cases

- Community internet in areas with poor connectivity
- Event networking (festivals, conferences)
- Emergency communication when centralized infrastructure fails
- Privacy-preserving internet access (traffic exits through community VPS)

## Technical Details

- **Build**: `build.sh` in `/opt/parahub-mesh/`
- **Models**: `iot/models.py` -- IoTDevice, MeshPass, MeshPassCredit, MeshDevice
- **API**: `iot/api/mesh.py` -- heartbeat, pass, device binding endpoints
- **Config**: `99-parahub-mesh` uci-defaults for zero-touch provisioning
- **Frontend**: `/mesh` (firmware download), `/free` (speed pass: payment QR + device list), DeviceCard (WiFi/root pwd, settings, location)
