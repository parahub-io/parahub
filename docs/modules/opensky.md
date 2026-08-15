# OpenSky

Community aerial imagery. Pilots fly their own drone over a cell of the map, upload the photos, and the platform turns them into an open orthophoto layer and a 3D model that everyone can use.

## How a Survey Works

1. **Pick a cell on the map** — switch on the aerial grid in the map tools. The map is divided into fixed square cells (roughly 305 m at the equator, ~240 m across in Portugal). Cells that already have imagery are shaded yellow and carry the dates of their most recent surveys, so it is visible at a glance what still needs flying.
2. **Check the cell is reachable** — the flight planner (below) says whether your drone and controller can actually work that cell from the launch point you have in mind.
3. **Download the flight plans** — one click on a cell gives a ZIP with five ready-made DJI mission files.
4. **Fly** — as many of the five as the terrain and your battery budget justify. Flights can be spread across several sessions.
5. **Upload the photos** — JPGs straight off the card.
6. **Wait** — processing is automatic, with live progress on the mission card. The imagery joins the public aerial layer when it finishes.

## Flight Planning (Drone Reach)

From a launch point, the map classifies the surrounding cells using four independent checks:

- **Range** — a straight-line disk around the launch point (a drone flies straight, not along roads). Presets are 500 m, 2 km and 5 km.
- **Terrain ceiling** — missions fly at a constant altitude measured from the *launch* point, with no terrain following. Where the ground inside a cell rises close to that altitude, the cell is blocked. The altitude slider stops at 120 m, the EASA open-category legal ceiling.
- **Controller line of sight** — a ridge between you and a cell can break the radio link even where the drone would clear the terrain. Such cells are flagged separately: the drone could fly there, the controller could not talk to it.
- **Airspace** — a cell whose centre falls inside a hard no-fly zone that overlaps your flight altitude is marked restricted.

**What the planner cannot tell you.** The elevation data is a coarse terrain surface: it knows hills, not masts, power lines, trees or building edges. The line-of-sight check is optical geometry, not a radio model — no diffraction, foliage or interference. Range ignores wind and temperature, so keep a generous battery reserve. And keeping the drone in your own visual line of sight is a legal duty that usually caps the practical radius well below the radio link. The result saves wasted drives; it is not clearance to fly.

## Airspace and No-Fly Zones

Official UAS geo-zones can be drawn on the map as a separate overlay. For Portugal they come from ANAC's published national geo-zone dataset in the standard European exchange format, each zone carrying its own altitude band and restriction type.

Most zones are not outright bans — they require authorisation or attach conditions — so only hard prohibitions are folded into the reachability colours. Everything else is drawn as an advisory polygon for the pilot to read and judge.

**Temporary restrictions are not included.** NOTAMs, events and short-notice closures live in separate, time-varying sources. Like the planner, the overlay is a planning aid and never a legal clearance: checking current restrictions and holding the right authorisations remains the pilot's responsibility.

## Uploading

- **JPG only**, straight from the drone — the GPS data written by the camera is what places the mission on the map.
- Batches of up to 50 files / 500 MB; one mission can be assembled from several batches.
- **One cell, one mission.** Every photo must sit within about 320 m of the cell centre, otherwise the upload is rejected. A cell may hold several missions flown on different dates — that is what makes season comparison work.
- **At least one straight-down (nadir) pass is required.** An upload consisting only of angled photos is rejected: obliques alone cannot produce a usable orthophoto.
- **You can come back later.** Adding oblique photos to an already-published mission reprocesses it from the full photo set, nadir plus everything new.
- Missions name themselves from the cell coordinates and take their survey date from the photos, so there is nothing to fill in.

## License and Responsibility

Imagery uploaded to OpenSky, and everything derived from it — orthophotos, 3D meshes, map tiles — is published under **Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0)**. The layer is a collective asset that cannot be reflown on demand, so share-alike is what keeps it from being enclosed later. (The platform *code* is MIT; data and code licenses are independent.)

Starting a mission requires ticking the license consent box, which confirms two things: that you are the author or otherwise hold the rights to the photos, and that you agree to publish them on those terms. Photos added to an existing mission inherit that consent.

A copyright license settles none of the following, which stay with the pilot: privacy law, including the GDPR where faces, plates or private property are recognisable, and aviation rules such as ANAC's in Portugal.

## Missions

Each upload creates a mission that moves through: uploading → queued → processing → published (or failed, with the reason shown on the card).

- Ground boundary and survey date, both read from the photos
- Live processing progress, step by step
- Generated tile layers
- 3D mesh and 3D Tiles output
- Season comparison — several surveys of the same cell over time
- **Direction coverage** — photos classified by camera direction (straight down plus four cardinals) and shown as five pills on the mission card, so it is clear what has been flown and what is still missing

## 3D Quality vs Terrain

Oblique (angled) photos mostly improve vertical surfaces — walls and facades. Flat terrain with sparse buildings gets very little benefit, dense urban terrain gets a lot.

| Terrain | Recommendation |
|---|---|
| Forest, rural, agricultural | **Nadir-only is usually enough.** The 80%-overlap lawnmower already gives a very good 3D (~95% of the full-oblique quality, visually indistinguishable on inspection). Fly `1_2D.kmz` only, save flight time. |
| Suburban, low buildings (≤3 floors) | Nadir + 1-2 oblique directions gives a noticeable improvement in facade definition. Pick whichever cardinal faces the most-visible side. |
| Dense urban, high-rise, heritage buildings | Fly all 5 missions (nadir + 4 cardinals). Wall geometry and textures benefit strongly from every direction. Budget ~1h total flight time per cell. |

The KMZ generator emits all 5 missions up front; the pilot decides which subset to actually fly based on terrain. Coverage pills in the UI show what was flown so far — you can always add more photos later.

## Flight Plans

KMZ mission generator for DJI drones (fixed grid cells, nadir 80% overlap / oblique 70% overlap, 100 m above the launch point). One click on a cell downloads a ZIP with **5 KMZ flight plans**, numbered for DJI Fly's alphabetical sort:

1. `1_2D.kmz` — nadir (-90°), orthophoto source
2. `2_3D-N.kmz` — oblique -45°, camera North, captures south-facing walls
3. `3_3D-E.kmz` — oblique -45°, camera East, captures west-facing walls
4. `4_3D-S.kmz` — oblique -45°, camera South, captures north-facing walls
5. `5_3D-W.kmz` — oblique -45°, camera West, captures east-facing walls

Pilot picks a flight budget:

- **1 battery** — fly `1_2D` only (orthophoto, no 3D)
- **3 batteries** — fly `1_2D + 2_3D-N + 3_3D-E` (baseline 3D, 2 orthogonal facades)
- **5 batteries** — fly all five (ultra 3D, full facade coverage)

Each oblique captures one direction of walls — the wall facing toward the camera. Flights can be spread across sessions and uploaded together at the end. A setup waypoint pre-rotates the gimbal to avoid DJI's first-photo bug.

## Processing Pipeline

The heavy processing runs on a self-hosted GPU node in Portugal (see [Architecture](../architecture.md#infrastructure)), connected to the main server over an encrypted WireGuard tunnel — photogrammetry is GPU-bound and kept off the application server. Missions are picked up from a queue automatically:

1. Read GPS coordinates from the photos
2. Run OpenDroneMap (full reconstruction, orthophoto and 3D model)
3. Reproject to Web Mercator, convert to WebP
4. **Satellite alignment** (always) — matched against a global satellite reference, which fixes the mission's absolute position
5. **Neighbour alignment** (when adjacent missions exist) — feature matching against published neighbours, which removes visible seams between flights
6. Cut into map tiles and composite into the shared layer
7. Build the 3D mesh and its level-of-detail pyramid
8. Publish

Alignment measurements are stored as observations rather than baked into the imagery, so positions improve as more missions land nearby, and better methods can be added later without discarding what came before. Where flights of the same spot disagree because tall buildings lean differently in each, their photos can be reconstructed jointly into one seamless super-mission that supersedes the originals.

Processed tiles are served directly by the web server; 3D meshes are streamed on demand.

## Viewing

- **Map** — the aerial layer sits in the layer picker; a mission can be opened straight from its card, which frames it on the map
- **3D** — meshes open in a fullscreen viewer with orbit controls and an optional slow auto-rotation for showing the model off; the model file can be downloaded by the pilot for offline use
- **Dashboard** — `/opensky` lists your own missions and everyone else's, with stats and upload

## Who Can Create Missions

Uploading requires a registered account with a profile, and the license consent that comes with it. Viewing the imagery — the aerial layer, mission cards and 3D models — is open to everyone, including anonymous visitors. Downloading a mission's raw 3D file is limited to the pilot who flew it.

## Technical Details

- **Models**: `geo/models/opensky.py` — mission, tile layer, consolidation membership, pose-graph edges; `geo/models/drones.py` — UAS geo-zones
- **API**: `geo/endpoints/opensky.py` — upload and finalize, missions, tiles, covered cells, flight plans, reachability, geo-zones
- **Flight plans**: `geo/mission_generator.py` — grid maths and DJI WPML/KMZ generation
- **Planner**: `geo/drone_reach.py` — range, terrain ceiling, controller viewshed, regulatory classification (elevation from the routing engine's height service)
- **Geo-zone import**: `geo/management/commands/import_drone_zones.py` — fetches and reloads the published national dataset
- **Processing**: `geo/opensky_processor/` — one module per pipeline step (ingest, ODM runners, satellite and neighbour alignment, tiling, mesh, consolidation)
- **Frontend**: `frontend/pages/opensky/index.vue`, `frontend/components/OpenSky/`, `frontend/components/MapPanelOpenSky.vue`, `frontend/composables/useMapOpenSky.ts`, `frontend/composables/useMapDroneReach.ts`
