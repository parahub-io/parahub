# Architecture

## Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Django 5 + Django Ninja (REST API) |
| **Frontend** | Nuxt 4.3 (Vue 3, SSR) |
| **Database** | PostgreSQL 16 + PostGIS + TimescaleDB |
| **Cache/Realtime** | Redis |
| **Graph** | Neo4j (barter cycle detection) |
| **Chat** | Synapse (Matrix homeserver) |
| **Maps** | MapLibre GL JS + Martin (vector tiles) + Pelias (geocoding) + Valhalla (routing) |
| **Transit Routing** | MOTIS v2 (RAPTOR multimodal) |
| **GPS Tracking** | Traccar |
| **Git** | Gitea |
| **Video** | Jitsi Meet |
| **Mobile** | Capacitor (WebView shell) |
| **Monitoring** | NetData + Uptime Kuma |
| **Analytics** | Plausible CE (self-hosted) |

## Infrastructure

Single server: Hetzner dedicated (<VPS_IP>) -> LXC container (<LXC_IP>) -> parahub.io

### Services

| Service | Port | Description |
|---------|------|-------------|
| parahub-uvicorn | 8000 | Django API (production) |
| parahub-frontend | 3000 | Nuxt SSR (production) |
| PostgreSQL | 5432 | Main database |
| Redis | 6379 | Cache, sessions, real-time state |
| Neo4j | 7687 | Barter graph |
| Synapse | 8008 | Matrix homeserver |
| Traccar | 8082 | GPS tracking |
| Martin | 3002 | Vector tile server |
| Pelias | 4000 | Geocoding |
| Valhalla | 8002 | Street routing |
| MOTIS | 8090 | Transit routing |
| Gitea | 3003 | Git hosting |
| NetData | 19999 | System metrics |
| Uptime Kuma | 3010 | Service monitoring |

Nginx handles SSL termination and reverse proxying. Systemd manages all services. Docker Compose for containerized services (Neo4j, Synapse, MOTIS, Uptime Kuma, Jitsi, Plausible). Pelias runs from a separate Docker Compose project (`/opt/pelias/`).

## Identity System

### ULIDs
All entities use 26-character ULIDs as primary keys (e.g., `01K7M4MDWPFZ5WQ4A5GRPPVZR2`). Time-sortable, globally unique, no prefixes. Type identification via `object_type` field in API responses.

```json
{"id": "01K7M4MDWPFZ5WQ4A5GRPPVZR2", "object_type": "item", "title": "..."}
```

### Account Model
`Account` extends Django's `AbstractUser` directly -- no separate User model. One account can have multiple profiles (up to 7). Human-readable address: `username@parahub.io` maps to Matrix ID `@username:parahub.io`. Flags: `is_test` (test accounts for E2E), `is_bot` (AI agent accounts) -- both hidden from public listings for non-staff users.

## Authentication

Three-layer authentication:

1. **Session cookie** -- Django session, set on login
2. **JWT token** -- Short-lived, obtained from `/api/v1/auth/session/token/`
3. **PGP signature** -- Required for critical operations (contracts, votes, debts)

API endpoints use three auth classes:
- `ProfileAuth` -- JWT required, returns Profile object (most common)
- `GlobalAuth` -- JWT required, returns Account object (admin operations)
- `OptionalProfileAuth` -- JWT optional, for public endpoints with enhanced authenticated response

OAuth login supported (Google). OIDC provider for Traccar, Matrix, and Gitea SSO.

## API Design

REST API at `/api/v1/` via Django Ninja. Response format:

```json
// List endpoints
{"items": [...], "count": 42}

// Single object
{"id": "...", "object_type": "...", ...}

// Errors (via HttpError exception)
{"detail": "Error message"}
```

Two routing conventions:
- **Cross-cutting endpoints**: `parahub/endpoints/{name}.py` (profiles, items, contracts, auth, matrix, partners, ads, ai_vision, federation, governance, income, jitsi, rides, shipments, wot, zenith)
- **Domain-specific endpoints**: `{app}/api.py` (barter, energy, treasury, governance, debts, parasos, tickets, notifications)

## WebSocket Architecture

Nine WebSocket endpoints:

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `/ws/v1/realtime/` | Required | Unified multiplexed consumer: ULID subscriptions, room-based updates (polls, treasury), personal notifications, global broadcasts |
| `/ws/v1/public/` | None | System broadcasts for anonymous users (deploy notifications) |
| `/ws/v1/map/presence/` | Required | Real-time avatars on map (geo-tile pub/sub) |
| `/ws/v1/transit/` | None | Live transit vehicle positions |
| `/ws/v1/driver/` | Required | Driver mode: bidirectional position/direction/stop announcements |
| `/ws/v1/trackers/` | Required | IoT tracker positions (staff=all, user=own devices) |
| `/ws/v1/federation/` | Required | Inter-node federation protocol |
| `/ws/v1/agents/voice/<name>/` | Staff | AI agent voice chat |
| `/ws/v1/support/voice/` | Staff | Support voice interface |

**Native Redis pub/sub** for all WebSocket messaging (Django Channels' `channels_redis` removed). `FeedPubSubManager` singleton manages subscribe/publish with two Redis connections per worker.

Channel naming convention:
- `user:{account_id}` -- personal notifications
- `object:{ulid}` -- entity field updates
- `poll:{id}` / `treasury:{id}` -- room-based updates
- `transit:tick` / `transit_route:{id}` -- transit data
- `tracker:tick` -- IoT tracker positions
- `map_tile:14:{x}_{y}` -- map presence by tile
- `agent_log:{agent_name}` -- Yellow Gate agent log streaming (staff only)
- `feed:system` -- deploy/version broadcasts

## CQRS Pattern

Commands (writes) -> PostgreSQL (source of truth).
Queries (real-time reads) -> Redis cache.

**Never** write high-frequency data (GPS, analytics, view counts) directly to PostgreSQL.

Example -- transit real-time pipeline:
1. **Ingestion**: asyncio + aiohttp fetches GTFS-RT protobuf feeds
2. **Processing**: RouteCache (in-memory, 10min refresh), StopSnapper (shape projection)
3. **Live state**: Redis HASH with 90s TTL
4. **History**: TimescaleDB hypertable, batch INSERT, 1/min downsample
5. **Push**: WebSocket broadcast by zoom-14 tiles via Redis pub/sub

Example -- tracker pipeline (same CQRS):
1. **Ingestion**: Traccar webhook -> `process_position_redis()`
2. **Live state**: Redis GEOADD + HSET (tracker:geo, tracker:vdata)
3. **History**: Flusher daemon reads `tracker:pending` -> TimescaleDB batch INSERT every 60s
4. **Bridge**: If device has active VehicleAssignment, also writes to `transit:*` keys
5. **Push**: Redis PUBLISH `tracker:tick` -> WebSocket GEOSEARCH by viewport

## Data Model

### Django Apps

| App | Models | Purpose |
|-----|--------|---------|
| `identity` | Account, Profile, Partner, Verification, Contract, ContractReview, ArbiterProfile, ArbitrationVerdict, SocialRecovery, PsychProfile, PGPKeyHistory, ProfileNote, ProfileVerificationPhoto | Identity, trust, contracts, arbitration |
| `market` | Item, ItemImage, Video | Marketplace listings |
| `barter` | Exchange, ExchangeSwap, ExchangeApproval | Multi-party barter |
| `debts` | Debt, DebtRepayment | P2P debt tracking |
| `taxonomy` | Category, Tag | Hierarchical categories (850 items, 17 roots, domain filter) |
| `geo` | Building, Establishment, Event, EventParticipant, Place, Stop, Route, Trip, RouteStop, StopTime, CalendarDate, Agency, TransitDataSource, VehiclePositionHistory, DriverShift, OpenSkyMission, OpenSkyTileLayer, CondominiumFraction, QuotaPayment, EstablishmentPhoto, EstablishmentMembership, EstablishmentReview | Geography, directory, transit, events, aerial imagery, condominium |
| `governance` | Poll, PollContext, PollOption, PollEligibleVoter, PollVote, PollVoteDelegation, PollAuditLog | Liquid democracy |
| `logistics` | Shipment, ShipmentEvent, CarrierOffer, RideRequest, RideBooking, RideReview | P-Hub shipments and carpool |
| `ads` | AdsProfile, AdsInterest, AdsSkill, AdsProfileSkill, AdsChildrenAge, AdCampaign, AdView | P2P advertising |
| `energy` | EnergyCell, EnergyProducer, EnergyConsumer, EnergyRelay, EnergyBillingRecord, GridInfrastructure | P2P solar energy |
| `treasury` | BudgetCategory, BudgetAllocation, BudgetEpoch, Expense, TreasuryAuditLog | Participatory budgets |
| `iot` | IoTDevice, TrackerHistory, TrackerLocation, TraccarUser, MeshSubscription, VehicleAssignment, Property, HAHome, HAEntity | GPS trackers, mesh nodes, dispatch, property, Home Assistant |
| `tickets` | TicketType, Ticket | Unified ticketing (events + transit) |
| `agents` | Agent, AgentSession | AI agent automation |
| `notifications` | PushSubscription, FCMDevice | Web Push, Firebase Cloud Messaging |
| `finance` | Payment, Donation | Payment tracking |
| `parasos` | SafetyGroup, SafetyGroupMember, SOSAlert, SOSResponse, InactivityWatch, GroupInvite | Emergency mutual aid |
| `audit_log` | AuditBatch, TimestampProof, MatrixRoomReference, PGPKeyPublication, ProofExport | Cryptographic proofs |
| `core` | ULIDModel, Instance, ProfileMigration, Like | Base models, federation, likes |
| `currency` | ExchangeRate | Currency exchange rates |
| `psy` | PsychProfile | Psychoinformatics |

### Data Sync
PostgreSQL is the source of truth. Neo4j synced via Django signals (barter graph). Redis stores sessions, rate limiting, PGP nonces (1h TTL), exchange rates (25h TTL), transit live state.

## Frontend Architecture

Nuxt 4 with SSR. KeepAlive for instant page switching (inspired by busti.me). Tailwind CSS with design tokens.

Key patterns:
- **SSR + Auth**: `useAsyncData` for public SEO data, `onMounted` re-fetch with auth for interactive fields
- **Stores**: Pinia -- `auth.ts` (JWT in memory), `realtime.ts` (WebSocket singleton), `iot.ts`, `toast.ts`
- **i18n**: `@nuxtjs/i18n` v10, `prefix_except_default` strategy (EN = no prefix, others = `/pt/`, `/es/`, etc.)
- **Map**: MapLibre Symbol Layers (canvas rendering), polling-based initialization

## Security Architecture

See [Security](security.md) for full details.

Key points:
- JWT tokens are short-lived, stored in memory (not localStorage)
- PGP signatures verified server-side for critical operations
- Rate limiting on all endpoints
- CORS and CSP headers configured
- WebSocket authentication via cookie-based token
- No secrets in code -- environment variables via `rotate-secrets.sh`
