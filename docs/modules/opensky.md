# OpenSky

Community aerial imagery protocol. Upload drone photos, process them into map tiles and 3D meshes using OpenDroneMap.

## Workflow

1. **Upload**: ZIP archive (up to 2GB) or individual JPGs (batch 50 files/500MB) with GPS EXIF data
2. **Processing**: OpenDroneMap (ODM) generates orthophoto tiles with auto-alignment to existing missions
3. **3D Mesh** (optional): ODM full pipeline -> obj2gltf -> gltf-transform optimize (Draco + WebP + resize cap 4096px). Typical 12x size reduction (346MB -> 29MB)
4. **Serving**: Processed tiles served via Nginx directly (no Martin intermediary). GLB meshes via X-Accel-Redirect
5. **Viewing**: Tiles displayed as a map layer. 3D meshes in fullscreen three.js viewer with DRACOLoader

## Missions

Each upload creates an OpenSkyMission with status lifecycle: AVAILABLE -> UPLOADING -> QUEUED -> PROCESSING -> PUBLISHED.

- GPS boundary (auto-extracted from image EXIF)
- Processing status tracking
- Generated tile layers (OpenSkyTileLayer)
- 3D mesh output (pilot-only request, on-demand)
- Season comparison via `?mission_id=ULID` filter

## Processing Pipeline

Two systemd timer-triggered jobs:

### Orthophoto (`parahub-opensky-processor.timer`, 5min)
1. Extract GPS coordinates from image EXIF data
2. Run ODM orthophoto generation
3. gdalwarp (EPSG:3857) -> gdal2tiles -> WebP conversion
4. Auto-alignment: Phase Correlation + ECC co-registration to best existing PUBLISHED mission (limits: 30m translation, 5° rotation, 25% scale)
5. Tile compositing with hard links for opaque tiles
6. Register tile layer in database

### 3D Mesh (`parahub-mesh-processor.timer`, 10min)
1. ODM full pipeline (no --skip-3dmodel)
2. obj2gltf conversion
3. gltf-transform optimize: Draco compression + WebP textures + resize cap 4096px
4. Store at `/mnt/opensky/meshes/{mission_id}/`

## Flight Plans

KMZ mission generator for DJI drones:
- Hexagonal cell flight plan (7 cells: 1 center + 6 ring, ~250m area, 75% overlap, ~20min flight)
- Oblique flight plan support (45° angle) for 3D reconstruction
- Waypoint setup to avoid DJI first-photo bug

## Frontend

- `/opensky` dashboard for mission management
- ModelViewer3D.vue: three.js GLTFLoader with DRACOLoader, OrbitControls, fullscreen button
- GLB download button for offline use
- Map layer: `opensky-latest-layer` with season comparison filter

## WoT Requirement

Creating missions requires WoT verification level 2+ to prevent abuse.

## Technical Details

- **Models**: `geo/models.py` -- OpenSkyMission, OpenSkyTileLayer
- **API**: `geo/endpoints/opensky.py` -- upload (ZIP/JPG), missions, request-mesh, mesh download, mesh viewer, flight plans
- **Frontend**: `pages/opensky.vue`, `components/ModelViewer3D.vue`
- **Storage**: `/mnt/opensky/` (uploads + missions + meshes), `/mnt/opensky-tiles/` (final tiles with hard links)
- **Nginx**: Direct `/latest/` serve, X-Accel-Redirect for filtered queries, `/opensky-mesh-accel/` for GLB
