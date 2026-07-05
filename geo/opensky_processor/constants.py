"""
OpenSky processor configuration: paths, ODM parameters, tile pyramid,
alignment/consensus/similarity tunables.

Values are documented in PK/opensky-system.md; incident history lives next to
the constant it produced. Single-consumer constants coupled to one function
stay in that function's module (tile-lock key, Pelias URL, orphan-sweep age,
the consolidation large-shift ECC gate).
"""

import os
import shutil


# Paths
OPENSKY_BASE = "/mnt/opensky"
ORTHOS_DIR = f"{OPENSKY_BASE}/orthos"
TILES_BASE = "/mnt/opensky-tiles"

# Remote processing & storage (skystore Home PT via WireGuard)
SKYSTORE_SSH = "deploy@<SKYSTORE_IP>"
SKYSTORE_OPENSKY = "/skystore/opensky"
SKYSTORE_FAST_PROCESSING = "/fast-processing"  # SSD for ODM temp files
SKYSTORE_TILES = "/skystore/opensky-tiles"
SKYSTORE_ODM_IMAGE = "opendronemap/odm:gpu"

# ODM settings
ODM_RESOLUTION = 1.83  # cm/pixel (DJI Mini 5 Pro 50MP native GSD at 100m)
ODM_MAX_CONCURRENCY = 4

# Split-merge consolidation settings (see PK/opensky-system.md § Consolidation).
ODM_SPLIT = 350           # avg images per ODM submodel (joint reconstruction).
# NOTE (16GB skystore): a cross-season consolidation OOM-kills OpenMVS
# DensifyPointCloud — double coverage (Apr+Jun of the same spot) makes an
# unavoidably dense central submodel that --split does NOT break up (tried 120 →
# still 591 imgs, died at 94% with swap 100% full). Real demand ≈34GB RAM+swap
# (medium) / ~41GB (high); pc-quality barely moves fusion memory (low is NOT a
# validated escape). On 16GB: add a second swapfile or consolidate per
# column-pair. See PK/opensky-system.md § Memory budget.
ODM_SPLIT_OVERLAP = 100   # metres of photo overlap between submodels (cross-stitch)
MAX_CONSOLIDATION_PHOTOS = 3000  # cap per consolidation (disk/RAM on skystore)
MIN_FAST_PROCESSING_FREE_GB = 25  # abort consolidation if /fast-processing has less free

# Tile settings
TILE_MIN_ZOOM = 11
# Highest zoom where one tile spans MULTIPLE Z17 missions, so latest/ must be an
# alpha-composite of all contributors instead of one mission's size-wins tile.
# Z17 (TILE_ZOOM) and deeper are 1 mission = 1 tile and stay hard-linked.
# See rebuild_overview_latest() — fixes zoomed-out "holes" over full coverage.
TILE_ZOOM_OVERVIEW_MAX = 16
TILE_MAX_ZOOM = 22  # DJI Mini 5 Pro 50MP @ 100m AGL → ortho native ~2.94 cm/px ground at lat 42°.
                   # z22 = 2.77 cm/px ground (matches native), z23 = 1.39 cm/px (2x oversample, no
                   # gain), z19 = 22 cm/px (8x worse than native — visibly blurry, MapLibre overzoom
                   # to z20+ just stretches pixels). Map UI maxZoom is 22, so z22 is the exact match.
                   # Tiles per Z17 mission: z11-z19 ~48, z11-z22 ~1500. ~30x storage, worth it.
WEBP_QUALITY = 100

# Alignment settings (used by skystore scripts)
ALIGNMENT_MAX_OFFSET_METERS = 30  # Reject translations larger than this

# Satellite alignment settings (fallback when no overlapping mission exists)
SATELLITE_TILE_ZOOM = 18  # ~0.44 m/px at mid-latitudes, good balance of resolution vs download count
SATELLITE_TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
SATELLITE_CACHE_DIR = f"{SKYSTORE_OPENSKY}/satellite_cache"
SATELLITE_ECC_MIN_CC = 0.15  # Minimum ECC correlation coefficient for satellite alignment

# Mesh processing (local temp on Hetzner, tools installed via npm/pip)
MESHES_LOCAL_DIR = f"{OPENSKY_BASE}/meshes"
SKYSTORE_3DTILES = "/skystore/opensky-3dtiles"
OBJ2GLTF_PATH = shutil.which("obj2gltf") or "/home/deploy/.nvm/versions/node/v24.5.0/bin/obj2gltf"
GLTF_TRANSFORM_PATH = shutil.which("gltf-transform") or "/home/deploy/.nvm/versions/node/v24.5.0/bin/gltf-transform"
NODE_BIN_DIR = os.path.dirname(OBJ2GLTF_PATH)


# Consensus parameters (tuned 2026-04-19 after oscillation incident).
# See PK/opensky-system.md § Pose Graph Architecture for rationale.
MIN_CONSENSUS_SHIFT_M = 0.5   # below this, don't retile (was 0.3 — too tight, caused iteration churn)
MAX_CONSENSUS_SHIFT_M = 10.0  # safety cap (should be < MAX_EDGE_SHIFT_M × 1.5)
OUTLIER_MEDIAN_MULTIPLE = 3.0  # reject edges with |shift| > 3× median of all measured edges
OUTLIER_FLOOR_M = 2.0          # but always accept edges below 2m regardless of median
SATELLITE_DAMPING_WEIGHT = 2e5  # virtual (0,0) edge weight — damps drift toward satellite-aligned position


# Phase-2 similarity bundle adjustment parameters.
SIM_SCALE_OUTLIER_FLOOR = 0.003       # 0.3% — below this, never an outlier
SIM_ROT_OUTLIER_FLOOR_DEG = 0.3       # 0.3° floor
SIM_GAUGE_PRIOR = 1e-3                # weak identity prior on scale/rotation (fixes gauge)
SIM_TRANS_PRIOR = 1e-6                # tiny prior pinning unanchored translation components
# Cross-season ortho↔ortho ORB edges are structurally unreliable (appearance
# changes break feature matching; reciprocal measurements disagree by metres
# while same-season pairs agree to ~0.3m — church quartet, 2026-06-11) and the
# spurious values pass RANSAC/outlier filters. Phase-2 drops ORB edges whose
# captures are further apart than this; cross-season alignment needs joint SfM
# (consolidation / future sfm_bridge edges), not 2D appearance matching.
SIM_MAX_SEASON_GAP_DAYS = 45


# Phase-2 similarity apply thresholds (on the solved delta).
SIM_APPLY_TRANS_M = 0.5       # apply if translation delta > 0.5 m
SIM_APPLY_SCALE = 0.002       # or |ln scale| delta > 0.2%
SIM_APPLY_ROT_DEG = 0.1       # or rotation delta > 0.1°
