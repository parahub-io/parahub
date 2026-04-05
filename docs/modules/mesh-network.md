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

- **Dual WiFi**: Private `Parahub` (802.11r/k/v roaming) + Free `parahub.io/free` (OWE transition mode)
- **Speed Control**: nftables + tc HTB (guest = 512kbps, host = 10Mbps on Bee, paid = 1Gbit via Lightning)
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
- Subscription model via `MeshSubscription` for status monitoring
- Coverage layer on the map shows active mesh nodes

## Use Cases

- Community internet in areas with poor connectivity
- Event networking (festivals, conferences)
- Emergency communication when centralized infrastructure fails
- Privacy-preserving internet access (traffic exits through community VPS)

## Technical Details

- **Build**: `build.sh` in `/opt/parahub-mesh/`
- **Models**: `iot/models.py` -- IoTDevice, MeshSubscription
- **API**: `iot/api.py` -- heartbeat, subscribe endpoints
- **Config**: `99-parahub-mesh` uci-defaults for zero-touch provisioning
- **Frontend**: `/mesh` (firmware download), `/free` (QR payment page), DeviceCard (WiFi/root pwd, settings, location)
