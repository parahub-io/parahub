# Home Assistant Integration

Connect user-owned Home Assistant instances to Parahub. Discover, import, and control smart home entities.

## Architecture

User-owned HA instances communicate directly with Parahub API. No proxying -- Parahub stores connection details and fetches state from HA REST API.

### Connection Methods
- **Yggdrasil IPv6** (preferred): zero NAT traversal, direct mesh connection
- **Public URL**: HA instance exposed to internet
- **Any reachable URL**: local network, VPN, etc.

## Models

- **HAHome** -- connection to a HA instance (owner, name, URL, Fernet-encrypted token, metadata, optional Property FK)
- **HAEntity** -- imported entity from HA (home FK, device, entity_id, state, attributes)

## Entity Control

Controllable domains: light, switch, fan, cover, lock, climate, media_player, vacuum, humidifier, water_heater, valve, siren, button, scene, script.

## Periodic Sync

`sync_ha_states` management command runs via systemd timer (60s interval). Respects per-home minimum sync interval (30s). Updates entity states and attributes in bulk.

## API

Endpoints at `/api/v1/iot/ha/`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/homes/` | POST | Add HA home |
| `/homes/` | GET | List user's HA homes |
| `/homes/{id}/` | GET | Home detail |
| `/homes/{id}/` | PATCH | Update home settings |
| `/homes/{id}/` | DELETE | Remove home |
| `/homes/{id}/test/` | POST | Test connection |
| `/homes/{id}/discover/` | GET | Discover available entities |
| `/homes/{id}/import/` | POST | Import selected entities |
| `/homes/{id}/sync/` | POST | Manual state sync |
| `/homes/{id}/entities/` | GET | List imported entities |
| `/entities/{id}/control/` | POST | Control entity (turn on/off, set values) |
| `/entities/{id}/state/` | GET | Fresh state from HA |

## Security

- **SSRF protection**: URL validation prevents internal network scanning
- **Fernet encryption**: HA access tokens encrypted at rest
- **Async HTTP**: 5s connect timeout, 15s read timeout

## Frontend

- **HAHomeCard**: home overview with entity count
- **HAHomeForm**: URL, token, property link
- **HADiscoverDialog**: search and filter available entities for import
- **HAEntityCard**: entity state display with control buttons
- **HAControlPanel**: domain-specific controls (brightness, temperature, etc.)
- Location: `/iot` page between DeviceList and Mesh sections
- i18n: `locales/{en,pt,es,fr,de,ru}/ha.json`

## Technical Details

- **Models**: `iot/models.py` -- HAHome, HAEntity (migration iot/0016)
- **Service**: `iot/services/ha_service.py`
- **API**: `iot/endpoints/ha.py`
- **Timer**: `parahub-ha-sync.timer` (60s)
