# Maps and Geography

Interactive map system with self-hosted tiles, geocoding, routing, and multiple data layers.

## Map Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Renderer | MapLibre GL JS | Vector tile rendering in the browser |
| Tiles | Martin | Self-hosted vector tile server |
| Geocoding | Pelias (213M docs) | Address search and reverse geocoding |
| Street Routing | Valhalla | Car, walk, bike directions with maneuvers |
| Transit Routing | MOTIS v2 | Multimodal journey planning (RAPTOR) |
| Font Glyphs | Self-hosted (nginx) | No external CDN dependency |

## Layers

The map displays multiple data layers controlled via a unified **Layers** button (merged Aerial/Transit/Condo toggles):

- **Items** -- marketplace listings with location
- **Establishments** -- business directory entries
- **Events** -- upcoming community events
- **Transit** -- real-time vehicle positions
- **P-Hub** -- logistics point markers (capacity, accepted sizes, opening hours)
- **Energy Cells** -- solar energy community areas
- **Condominiums** -- building management overlays
- **Mesh Nodes** -- community network coverage
- **OpenSky** -- aerial imagery tiles
- **IoT Devices** -- GPS trackers and smart devices
- **Properties** -- user properties with GeoJSON boundaries
- **Map Presence** -- real-time user avatars (MMORPG-style)

## Business Directory

2GIS-style organization directory integrated with the map:

- **Buildings** -- physical addresses with OSM data
- **Establishments** -- businesses, organizations, cooperatives within buildings
- Membership management (Owner/Admin/Member roles)
- Public Board (Direção) section: governance structure with president, board members, treasurer, auditor — role badges, linked profiles, joined dates
- Organization detail: open/closed status badge (based on opening hours), directions button (external map link), share button
- Photo galleries
- Reviews and reputation
- Treasury (participatory budget per establishment)
- Hub mode: any establishment can activate P-Hub for parcel drop-off/pick-up

Click a building on the map to see establishments inside, with a clean in-panel navigation (list -> details -> back).

## Map Presence

Real-time user avatars on the map, inspired by MMORPG games:
- Redis GEOHASH for spatial indexing
- WebSocket subscription by zoom-14 tiles
- LPC sprite-style avatars
- Separate WebSocket endpoint (`/ws/v1/map/presence/`)

## Routing Panel

Directions panel with three modes (Car, Walk, Bike):
- Geocode autocomplete for start/end points
- Click-on-map to set waypoints
- Valhalla maneuver list with turn-by-turn instructions
- Polyline visualization on map
- Lock-on bracket preview markers on hover for search results

## Search and Navigation

- **Unified search**: geocoding + local content (items, establishments, events)
- **Edge distance indicator**: off-screen search results shown with distance arc on viewport edge
- **Lock-on bracket animation**: preview markers for search/routing results on hover
- **Map state persistence**: `useMapState()` composable reads last position/zoom from localStorage

## Performance

- **KeepAlive**: map persists across page navigation, no tile reload
- **Canvas snapshot**: instant map redraw when returning to map page
- **trackResize: false**: prevents unnecessary tile reloading
- **Smart ResizeObserver**: skips resize if dimensions unchanged

## Technical Details

- **Frontend**: `pages/map.vue`, `components/MapLibre*.vue`, `components/MapRoutingPanel.vue`, `components/MapFeaturePanel.vue`
- **Composables**: `useRouting` (Valhalla directions)
- **Backend**: `geo/endpoints/geocoding.py` (Pelias proxy), `geo/endpoints/buildings.py` (directory)
- **WebSocket**: `parahub/consumers/map_presence.py`
- **Services**: `parahub/services/map_presence.py`
