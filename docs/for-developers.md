# For Developers

## API

REST API at `https://parahub.io/api/v1/`. Built with Django Ninja (OpenAPI schema auto-generated).

### Authentication

Most endpoints require JWT authentication:

```
GET /api/v1/auth/session/token/
Cookie: sessionid=...
-> {"token": "eyJ..."}

GET /api/v1/profiles/me/
Cookie: sessionid=...
Authorization: Bearer eyJ...
-> {"id": "01K...", "object_type": "profile", "local_name": "alice", ...}
```

Both session cookie AND JWT header are required for authenticated endpoints.

### Key Endpoints

| Prefix | Description |
|--------|-------------|
| `/api/v1/auth/` | Login, logout, session token, OAuth |
| `/api/v1/profiles/` | User profiles, avatar upload, badges |
| `/api/v1/items/` | Marketplace items CRUD |
| `/api/v1/partners/` | Partner management, invites |
| `/api/v1/contracts/` | P2P contract signing |
| `/api/v1/debts/` | Debt tracking |
| `/api/v1/wot/` | Web of Trust verifications |
| `/api/v1/barter/` | Barter exchange management |
| `/api/v1/governance/polls/` | Polls, voting, delegation |
| `/api/v1/geo/` | Buildings, events, transit, geocoding, OpenSky |
| `/api/v1/energy/` | Energy cells and memberships |
| `/api/v1/treasury/{slug}/` | Participatory budgets |
| `/api/v1/ads/` | Ad campaigns |
| `/api/v1/matrix/` | Chat integration, DM creation |
| `/api/v1/shipments/` | P-Hub shipment tracking, carrier offers |
| `/api/v1/iot/` | IoT devices, mesh network, tracker, dispatch, properties |
| `/api/v1/iot/ha/` | Home Assistant homes and entities |
| `/api/v1/geo/condominiums/` | Condominium management (fractions, quotas, assemblies) |
| `/api/v1/geo/transit/manage/` | Transit management (agency/route/stop CRUD, GTFS export) |
| `/api/v1/geo/driver/` | Driver mode GPS broadcasting |
| `/api/v1/tickets/` | Ticket types, purchase, validate |
| `/api/v1/income/` | Donation config, transparency |
| `/api/v1/agents/` | AI agent management |

### Response Format

```json
// List with pagination
{"items": [...], "count": 42}

// Single entity (always includes object_type)
{"id": "01K...", "object_type": "item", "title": "..."}

// Error
{"detail": "Error message"}
```

### WebSocket

Nine WebSocket endpoints:

```
ws://parahub.io/ws/v1/realtime/              # Authenticated: subscriptions, notifications, rooms
ws://parahub.io/ws/v1/public/                # Anonymous: system broadcasts
ws://parahub.io/ws/v1/map/presence/          # Authenticated: map avatars
ws://parahub.io/ws/v1/transit/               # Anonymous: live vehicle positions
ws://parahub.io/ws/v1/driver/                # Authenticated: driver GPS broadcasting
ws://parahub.io/ws/v1/trackers/              # Authenticated: IoT tracker positions
ws://parahub.io/ws/v1/federation/            # Authenticated: inter-node federation protocol
ws://parahub.io/ws/v1/agents/voice/<name>/   # Staff: AI agent voice chat
ws://parahub.io/ws/v1/support/voice/         # Staff: support voice interface
```

Realtime consumer messages:
```json
{"type": "subscribe", "ids": ["01K7M4...", "01K7M5..."]}
{"type": "unsubscribe", "ids": ["01K7M4..."]}
{"type": "join", "room": "poll", "id": "01K9..."}
{"type": "leave", "room": "poll", "id": "01K9..."}
```

## Tech Stack

| Component | Version |
|-----------|---------|
| Python | 3.12+ |
| Django | 5+ |
| django-ninja | 1.5+ |
| Nuxt | 4.3 |
| Vue | 3 |
| PostgreSQL | 16+ (PostGIS, TimescaleDB) |
| Redis | 7+ |
| Neo4j | 5+ |
| Node.js | 22+ |

## Project Structure

```
/opt/parahub/
  manage.py               # Django management
  parahub/                # Main Django project
    api.py                # API root, router registration
    auth.py               # JWT/PGP authentication
    settings.py           # Configuration
    endpoints/            # Cross-cutting API endpoints
    consumers/            # WebSocket consumers
    services/             # Business logic services
    crypto/               # PGP utilities
  identity/               # Accounts, profiles, partners, contracts
  market/                 # Items, images
  barter/                 # Neo4j barter graph
  debts/                  # P2P debts
  geo/                    # Maps, directory, transit, events, OpenSky
  governance/             # Polls, liquid democracy
  logistics/              # P-Hub shipments, carpool
  ads/                    # P2P advertising
  energy/                 # Solar energy ACC
  treasury/               # Participatory budgets
  taxonomy/               # Categories
  iot/                    # IoT devices, trackers, dispatch
  tickets/                # Unified ticketing
  agents/                 # AI agents
  notifications/          # Web Push
  frontend/               # Nuxt application
    pages/                # Vue router pages
    components/           # Vue components
    composables/          # Vue composables
    stores/               # Pinia stores
    locales/              # i18n translations (6 languages)
```

## Self-Hosting

Parahub is open source (MIT License). To run your own instance:

### Requirements
- Linux server (Ubuntu 22.04+ recommended)
- PostgreSQL 16+ with PostGIS and TimescaleDB extensions
- Redis 7+
- Neo4j 5+
- Node.js 22+
- Python 3.12+

### Quick Start

```bash
git clone <repo-url> /opt/parahub
cd /opt/parahub

# Bootstrap script
./install.sh

# Create database
createdb parahub
python3 manage.py migrate

# Seed test data (optional)
python3 manage.py seed_test_users
python3 manage.py seed_test_items

# Build frontend
cd frontend && npm install && npx nuxi build
cd ..

# Run
python3 manage.py runserver  # Backend
cd frontend && node .output/server/index.mjs  # Frontend
```

For production deployment, see the systemd units in `systemd/` and run `nginx/setup-nginx.sh` to generate nginx configs from templates (or customize `nginx/templates/` directly).

### External Services

Some features require additional services:

| Service | Required For | Setup |
|---------|-------------|-------|
| Synapse | Matrix chat | Docker or native |
| Pelias | Geocoding | Docker (`/opt/pelias/`) |
| Martin | Vector tiles | Binary or Docker |
| Valhalla | Street routing | Docker |
| MOTIS | Transit routing | Docker |
| Traccar | GPS tracking | Docker |
| Gitea | Git hosting | Docker or native |

## Contributing

Parahub is developed by the PARAHUB Association (Portuguese NPO). Contributions welcome.

### Guidelines
- **Icons**: lucide-vue-next only
- **Components**: Use UiButton, UiTabs, UiBadge, UiAlert from the design system
- **Colors**: CSS design tokens (`var(--color-primary)`, etc.) -- never hardcode hex values
- **i18n**: All user-facing strings in locale files, support all 6 languages
- **Testing**: Backend tests with `python3 manage.py test`, E2E with Playwright
- **Commits**: Descriptive messages, point commits (only changed files)

### Communication
- Matrix: `#general:parahub.io`
- Git: Self-hosted Gitea at `gitea.parahub.io`

## License

MIT License. The core platform is and will always be open source. See [LICENSE](../LICENSE) and [CLA](../CLA.md).
