# Transit

Real-time public transport monitoring. Import transit data via GTFS standard, track live vehicle positions via GTFS-RT, and provide multimodal routing.

## Coverage

Multiple transit feeds across cities worldwide — each with real-time vehicle GPS tracking. The current list of active feeds, routes, and stops is available at `/transit` or via the API (`/api/v1/geo/transit/agencies/`). Auto-updated weekly with SHA256 hash caching. gtfstidy preprocessing for feed normalization.

Static-only feeds (no GTFS-RT) are supported alongside live ones — e.g. CP rail and Transtejo ferry — so interchanges show up on multimodal routes. For feeds without shapes, route geometry is synthesized from the stop sequence with `pfaedle`. A cross-mode 150 m radius tier plus `sta`/`sto` canonicalization groups a rail platform, a bus stop, and a ferry terminal that share a location into one interchange.

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
- **ETA Engine (STT)**: Segment travel time tracking with a rolling FIFO of recent observations. Segment estimates use the FIFO **median** (robust to outliers) rather than the mean. Travel time is attributed to every segment a vehicle traverses; a vehicle moving away from a stop is treated as a stall. Near a stop, in-segment progress is subtracted from the origin ETA so the countdown doesn't overshoot, and an early-arrival nudge sharpens the "arriving now" moment. Direction detection, zombie vehicle filtering (stale positions), and schedule-based fallback. A replayable backtest harness scores STT predictions against observed ground truth to guard against regressions.

### GTFS Relay

Public endpoints for third-party consumers:
- `GET /api/v1/geo/transit/gtfs/feeds/` -- list feeds with relay URLs
- `GET /api/v1/geo/transit/gtfs/static/{slug}/` -- cached GTFS ZIP
- `GET /api/v1/geo/transit/gtfs-rt/vehicle-positions/{slug}/` -- protobuf (GTFS-RT spec)
- `GET /api/v1/geo/transit/gtfs-rt/vehicle-positions/{slug}.json` -- JSON convenience

### Timetable PDF Export

Branded, printable timetable per route, downloaded from a modal on the route page. Seasonal services render as separate columns; where a service period carries no readable name, the column falls back to its date range. The footer links back to the route page.

### Feed Health

A durable feed-health log records each import/refresh outcome so downtime can be reported by cause (upstream unreachable, malformed archive, empty feed, etc.) rather than guessed. This drives the operator-facing reliability view and feeds status monitoring.

### Driver Mode Integration

Verified drivers (WoT 3+) broadcast GPS from the browser. Positions injected into the same Redis pipeline (`transit:geo`, `transit:vdata`, `transit:members`). Passengers see driver vehicles on the map alongside official GTFS-RT feeds. See [Features](../features.md#driver-mode). For feeds that ship no `tts_stop_name`, Portuguese stop names are synthesized at serve time so spoken stop announcements read naturally.

The in-shift HUD includes a route overview ladder — both directions side by side with every live vehicle on the line, per-direction arrival badges in the agency's local time, and the driver's own bus highlighted and kept in view — plus an embedded ticket scanner, so validating passengers never interrupts the shift. As the vehicle approaches a stop, the HUD shows how many passengers marked themselves waiting for the driver's line there.

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

- SEO-friendly slug URLs: `/transit/route/lisbon/carris-metropolitana-1523`. Route and stop pages are listed in the sitemap (canonical-only). The `/transit` page groups the transit network and the rideshare section under tabs.
- Route visualization: line + stops on map with an explicit "Show on map" button and a draggable route mini-map. Stops reveal in a staggered sweep, gated on the map being idle, and both directions of a route are shown (circular/one-direction routes render correctly). The active route persists in the URL for deep-linking, and an active-route chip on the map dismisses it in one tap. A variant-count badge surfaces alternative percursos.
- Live vehicles are rendered on a `deck.gl` overlay (leaving MapLibre idle for smooth panning), with an optional animated comet trail behind each vehicle. On-demand vehicle metadata opens in the live map popup.
- Vehicle icons: busti.me SVG transport type icons (bus, tram, metro, train, ferry).
- Branded timetable PDF download from the route page (see Timetable PDF Export).
- WebSocket subscription by zoom-14 map tiles for efficient updates.
- Feed overview with aggregated statistics (routes/stops/trips per feed).

## Waiting at the Stop

Anyone standing at a stop — signed in or not — can open the stop page and tap the line they are waiting for. A marker is always specific to one line and one direction, so the signal means something: someone waiting for another line is noise to a driver.

- **Who sees it**: other passengers on the stop and route pages see how many people are waiting for the same line; the driver sees the count in the HUD when approaching the stop; the map shows a badge with the number of waiting people at occupied stops (an empty city draws nothing).
- **Lifecycle**: the marker stays alive while the page is open, dims (rather than vanishing) when the screen goes dark, and clears itself when the awaited vehicle arrives at the stop.
- **Shared poles**: a pole served by several operators shows its waiting count on every operator's page for that location.
- **Stranded-to-carpool bridge**: after holding a marker for a while with nothing live on the awaited line, the stop page promotes the rideshare option — including how many others are stuck at the same stop. See [Carpool](carpool.md).
- **Demand history**: minute-by-minute occupancy snapshots are recorded, so the accumulated shape of demand — how many people actually wait where, and when — exists as data a municipality can act on. Live counts alone are ephemeral and cannot be backfilled.

Anonymous markers are identified by a hashed device id and loosely capped per connection as an anti-abuse backstop — loose deliberately, because mobile carriers put many users behind one shared address.

## Multimodal Routing

MOTIS v2 (RAPTOR algorithm) for transit routing. Combines walking + transit for A-to-B journey planning. Docker container at port 8090. GTFS auto-bundle creates combined ZIP from individual feeds for MOTIS ingestion.

## Technical Details

- **Models**: `geo/models.py` -- Agency, Stop, Route, Trip, RouteStop, StopTime, CalendarDate, TransitDataSource, VehiclePositionHistory, DriverShift
- **API**: `geo/endpoints/transit.py` -- cities, discover, search, agencies, routes, stops, schedule, GeoJSON, GTFS relay
- **WebSocket**: `parahub/consumers/transit.py` (public, tile-based), `parahub/consumers/driver.py` (authenticated, bidirectional)
- **Services**: `parahub/services/transit_rt.py` -- RouteCache, StopSnapper, ETA; `parahub/services/transit_waiting.py` -- waiting markers (Redis-backed, WaitingSnapshot history)
- **Daemons**: `fetch_transit_rt.py` (asyncio GTFS-RT), `parahub-tracker-flush.service` (TimescaleDB batch writer)
- **TimescaleDB**: `geo_vehiclepositionhistory` hypertable (1-day chunks, compress after 1d, retain 90d)
