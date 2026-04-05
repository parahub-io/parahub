# Transit

Real-time public transport monitoring. Import transit data via GTFS standard, track live vehicle positions via GTFS-RT, and provide multimodal routing.

## Coverage

Multiple transit feeds across cities worldwide — each with real-time vehicle GPS tracking. The current list of active feeds, routes, and stops is available at `/transit` or via the API (`/api/v1/geo/transit/agencies/`). Auto-updated weekly with SHA256 hash caching. gtfstidy preprocessing for feed normalization.

## Architecture

### Data Pipeline (CQRS)

```
GTFS-RT feeds (protobuf/JSON)
    |
    v
asyncio daemon (fetch_transit_rt.py)    -- 30s cycle
    |
    v
Processing (RouteCache + StopSnapper)   -- in-memory, 10min refresh
    |
    +---> Redis HASH (transit:rt:{ds_id}, TTL 90s)     -- live state
    +---> TimescaleDB hypertable (batch INSERT, 1/min)  -- history
    +---> WebSocket broadcast (zoom-14 tiles)            -- push to clients
```

- **Commands** (writes): TimescaleDB for position history
- **Queries** (reads): Redis for live state
- **Static data**: PostgreSQL for schedules, stops, routes

### GTFS Import

Management command: `python3 manage.py import_gtfs --url <feed_url>` or `--file <path>`. Supports `--reset` for clean reimport, `--skip-stop-times` for faster import. ULID-stable upsert (preserves IDs across reimports). Nested ZIP normalization for multi-archive feeds. gtfstidy preprocessing auto-reverts if routes drop >5% or stops >10%.

### Real-Time Processing

- **RouteCache**: In-memory cache of route info (color, name, place, type). 10-minute refresh from PostgreSQL.
- **StopSnapper**: Projects vehicle GPS position onto route shape to find nearest stop. Binary search on shape points.
- **ETA Engine (STT)**: Segment travel time tracking with rolling FIFO of last 10 observations. Direction detection. Zombie vehicle filtering (stale positions). Schedule-based fallback.

### GTFS Relay

Public endpoints for third-party consumers:
- `GET /api/v1/geo/transit/gtfs/feeds/` -- list feeds with relay URLs
- `GET /api/v1/geo/transit/gtfs/static/{slug}/` -- cached GTFS ZIP
- `GET /api/v1/geo/transit/gtfs-rt/vehicle-positions/{slug}/` -- protobuf (GTFS-RT spec)
- `GET /api/v1/geo/transit/gtfs-rt/vehicle-positions/{slug}.json` -- JSON convenience

### Driver Mode Integration

Verified drivers (WoT 2+) broadcast GPS from the browser. Positions injected into the same Redis pipeline (`transit:geo`, `transit:vdata`, `transit:members`). Passengers see driver vehicles on the map alongside official GTFS-RT feeds. See [Features](../features.md#driver-mode).

### Ticket Integration

Unified tickets for transit routes. Lightning payment (no escrow), QR validation. See [Tickets](tickets.md).

## Transit Management

Platform for transit companies to manage operations via Parahub web UI instead of external GTFS tools.

- **Managed agencies**: `Agency.is_managed=True`, `Agency.owner` FK to Profile. Excluded from `update_gtfs_feeds` (no external URL).
- **Route/stop CRUD**: Create stops, create routes with ordered stops. Valhalla `bus` costing generates route shape from stop sequence.
- **GTFS export**: `GET /api/v1/geo/transit/manage/gtfs/export/{agency_id}/` — public, no auth. Generates GTFS ZIP on the fly from managed data.
- **GTFS-RT**: Existing GTFS-RT relay endpoint (`/api/v1/geo/transit/gtfs-rt/vehicle-positions/{slug}/`) works for managed agencies via tracker → transit bridge.
- **Frontend pages**: `/dispatch/routes` (route list + create/edit), `/dispatch/stops` (stop management).
- **Slug uniqueness**: Managed stops/routes use ULID suffix in slug to avoid collisions with GTFS-imported data.

## Frontend

- SEO-friendly slug URLs: `/transit/route/lisbon/carris-metropolitana-1523`
- Route visualization: line + stops on map with "Show on map" button
- Vehicle icons: busti.me SVG transport type icons (bus, tram, metro, train, ferry)
- WebSocket subscription by zoom-14 map tiles for efficient updates
- Feed overview with aggregated statistics (routes/stops/trips per feed)

## Multimodal Routing

MOTIS v2 (RAPTOR algorithm) for transit routing. Combines walking + transit for A-to-B journey planning. Docker container at port 8090. GTFS auto-bundle creates combined ZIP from individual feeds for MOTIS ingestion.

## Technical Details

- **Models**: `geo/models.py` -- Agency, Stop, Route, Trip, RouteStop, StopTime, CalendarDate, TransitDataSource, VehiclePositionHistory, DriverShift
- **API**: `geo/endpoints/transit.py` -- cities, discover, search, agencies, routes, stops, schedule, GeoJSON, GTFS relay
- **WebSocket**: `parahub/consumers/transit.py` (public, tile-based), `parahub/consumers/driver.py` (authenticated, bidirectional)
- **Services**: `parahub/services/transit_rt.py` -- RouteCache, StopSnapper, ETA
- **Daemons**: `fetch_transit_rt.py` (asyncio GTFS-RT), `parahub-tracker-flush.service` (TimescaleDB batch writer)
- **TimescaleDB**: `geo_vehiclepositionhistory` hypertable (1-day chunks, compress after 1d, retain 90d)
