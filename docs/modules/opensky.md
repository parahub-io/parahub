# OpenSky

Community aerial imagery protocol. Upload drone photos, process them into map tiles and 3D meshes using OpenDroneMap.

## Workflow

1. **Upload**: individual JPG files (batch up to 50 files / 500MB) with GPS EXIF data. ZIP upload was removed — only JPGs accepted now.
2. **Processing**: OpenDroneMap (ODM) generates orthophoto tiles with auto-alignment to existing missions
3. **3D Mesh** (optional): ODM full pipeline -> obj2gltf -> gltf-transform optimize (Draco + WebP + resize cap 4096px). Typical 12x size reduction (346MB -> 29MB)
4. **Serving**: Processed tiles served via Nginx directly (no Martin intermediary). GLB meshes via X-Accel-Redirect
5. **Viewing**: Tiles displayed as a map layer. 3D meshes in fullscreen three.js viewer with DRACOLoader

## Missions

Each upload creates an OpenSkyMission with status lifecycle: AVAILABLE -> UPLOADING -> QUEUED -> PROCESSING -> PUBLISHED.

- GPS boundary (auto-extracted from image EXIF)
- Processing status tracking
- Generated tile layers (OpenSkyTileLayer)
- 3D Tiles output (auto-generated in merged pipeline)
- Season comparison via `?mission_id=ULID` filter
- **Direction coverage** — per-photo classification by camera direction (nadir + 4 cardinals), shown as 5 pills on the mission card. Informational only.
- **Incremental upload** — add more photos to an existing PUBLISHED mission at any time. The pipeline reprocesses from the full photo set (nadir + any new obliques).

## 3D Quality vs Terrain

Oblique (angled) photos mostly improve vertical surfaces — walls and facades. Flat terrain with sparse buildings gets very little benefit, dense urban terrain gets a lot.

| Terrain | Recommendation |
|---|---|
| Forest, rural, agricultural | **Nadir-only is usually enough.** The 80%-overlap lawnmower already gives a very good 3D (~95% of the full-oblique quality, visually indistinguishable on inspection). Fly `1_2D.kmz` only, save flight time. |
| Suburban, low buildings (≤3 floors) | Nadir + 1-2 oblique directions gives a noticeable improvement in facade definition. Pick whichever cardinal faces the most-visible side. |
| Dense urban, high-rise, heritage buildings | Fly all 5 missions (nadir + 4 cardinals). Wall geometry and textures benefit strongly from every direction. Budget ~1h total flight time per Z17 tile. |

The KMZ generator emits all 5 missions up front; the pilot decides which subset to actually fly based on terrain. Coverage pills in the UI show what was flown so far — you can always add more photos later.

## Processing Pipeline

Single systemd timer-triggered job:

### Merged Pipeline (`parahub-opensky-processor.timer`, 5min)
1. Extract GPS coordinates from image EXIF data
2. Run ODM (full pipeline including 3D model)
3. gdalwarp (EPSG:3857) -> WebP conversion
4. Satellite alignment (always): ECC against ESRI World Imagery z18 — absolute global reference
5. ORB alignment (if neighbors exist): feature matching refinement against adjacent published missions
6. gdal2tiles -> tile compositing with hard links for opaque tiles
6.5. 3D Tiles generation: LOD pyramid via tiles3d_generator.py, ECEF georeferencing
7. Register tile layer in database

## Flight Plans

KMZ mission generator for DJI drones (Z17 Web Mercator, ~305×240m tiles, nadir 80% overlap / oblique 70% overlap):

One click on a tile downloads a ZIP with **5 KMZ flight plans**, numbered for DJI Fly alphabetical sort:

1. `1_2D.kmz` — nadir (-90°), orthophoto source
2. `2_3D-N.kmz` — oblique -45°, camera North, captures south-facing walls
3. `3_3D-E.kmz` — oblique -45°, camera East, captures west-facing walls
4. `4_3D-S.kmz` — oblique -45°, camera South, captures north-facing walls
5. `5_3D-W.kmz` — oblique -45°, camera West, captures east-facing walls

Pilot picks flight budget:
- **1 battery** — fly `1_2D` only (orthophoto, no 3D)
- **3 batteries** — fly `1_2D + 2_3D-N + 3_3D-E` (baseline 3D, 2 orthogonal facades)
- **5 batteries** — fly all five (ultra 3D, full facade coverage)

Each oblique captures one direction of walls — the wall facing toward the camera. Pilot can spread flights across multiple sessions and upload all photos at the end. Setup waypoint pre-rotates the gimbal to avoid DJI's first-photo bug.

## Frontend

- `/opensky` dashboard for mission management
- ModelViewer3D.vue: three.js GLTFLoader with DRACOLoader, OrbitControls, fullscreen button
- GLB download button for offline use
- Map layer: `opensky-latest-layer` with season comparison filter

## WoT Requirement

Creating missions requires WoT verification level 2+ to prevent abuse.

## Technical Details

- **Models**: `geo/models.py` -- OpenSkyMission, OpenSkyTileLayer
- **API**: `geo/endpoints/opensky.py` -- upload (JPG only), missions, 3D tiles, flight plans
- **Frontend**: `pages/opensky.vue`, `components/ModelViewer3D.vue`
- **Storage**: `/mnt/opensky/` (uploads + missions + meshes), `/mnt/opensky-tiles/` (final tiles with hard links)
- **Nginx**: Direct `/latest/` serve, X-Accel-Redirect for filtered queries, `/opensky-mesh-accel/` for GLB
