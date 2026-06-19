"""
OpenSky 3D Tiles Generator

Generates OGC 3D Tiles 1.1 from OpenSky mission mesh GLBs:
- LOD levels via gltf-transform simplify (lod0=100%, lod1=50%, lod2=10%, lod3=2%)
- Per-mission tileset.json with ENU→ECEF transform from ODM origin
- Root tileset.json combining all MESH_READY missions

Storage layout (on skystore):
  /skystore/opensky-3dtiles/
  ├── tileset.json                          # Root tileset (all missions)
  └── missions/{id}/
      ├── tileset.json                      # Per-mission tileset
      ├── lod0.glb                          # 100% vertices (original optimized GLB)
      ├── lod1.glb                          # 50%
      ├── lod2.glb                          # 10%
      └── lod3.glb                          # 2%
"""

import json
import logging
import math
import os
import shutil
import subprocess
import tempfile

import numpy as np
from pyproj import Transformer

logger = logging.getLogger(__name__)

from geo.opensky_processor import (
    GLTF_TRANSFORM_PATH,
    MESHES_LOCAL_DIR,
    NODE_BIN_DIR,
    SKYSTORE_3DTILES,
    SKYSTORE_OPENSKY,
    SKYSTORE_SSH,
    _skystore_rsync,
    _skystore_ssh,
)

# LOD levels: (level, simplify_ratio, max_geometric_error, texture_size)
# Texture sizes halved 2026-06 (2048/1024/512 → 1024/512/256): ODM meshes carry
# ~76 texture chunks, decoded RGBA was ~1.7 GB per lod1 mission → multi-mission
# 3D view OOM'd the tab (see PK/opensky-system.md § Memory governor). A/B on a
# building (/design/opensky-lod-ab) showed 1024 visually ≈ 2048 (roof PSNR 29 dB)
# at 4x less memory. 1024-chunk capacity (~80 Mpx/mission) still exceeds the
# ~60 Mpx native-GSD content of one Z17 tile.
LOD_LEVELS = [
    # lod0 = copy of original optimized GLB (no simplification)
    (1, 0.5, 0.01, 1024),
    (2, 0.1, 0.05, 512),
    (3, 0.02, 0.1, 256),
]

# geometricError thresholds for tileset.json (meters)
# Controls at what camera distance each LOD switches
GEOMETRIC_ERRORS = {
    'root': 200,   # mission-level error
    'lod3': 100,   # show lod3 at 2+ km
    'lod2': 30,    # show lod2 at 500m-2km
    'lod1': 10,    # show lod1 at 100-500m
    'lod0': 0,     # show lod0 at <100m (full detail)
}

# Bump on tileset.json schema changes (LOD chain, refine mode, content URIs).
# Used as `?v=N` cache buster on per-mission tileset URIs in the root tileset
# so browsers with old `max-age=604800` cached responses pick up changes
# immediately instead of after a 7-day natural expiry. Frontend's TILESET_URL
# carries the same constant for the root itself.
TILESET_SCHEMA_VERSION = 4


def local_to_ecef_transform(center_lat: float, center_lng: float, center_alt: float = 0) -> list[float]:
    """Compute 4x4 ENU→ECEF transform matrix (column-major for 3D Tiles).

    Args:
        center_lat: Latitude in degrees
        center_lng: Longitude in degrees
        center_alt: Altitude in meters above WGS84 ellipsoid

    Returns:
        16-element list (column-major 4x4 matrix)
    """
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)
    cx, cy, cz = transformer.transform(center_lng, center_lat, center_alt)

    lat_r = math.radians(center_lat)
    lng_r = math.radians(center_lng)

    # ENU → ECEF rotation matrix
    R = np.array([
        [-math.sin(lng_r),                  -math.sin(lat_r) * math.cos(lng_r),  math.cos(lat_r) * math.cos(lng_r)],
        [math.cos(lng_r),                   -math.sin(lat_r) * math.sin(lng_r),  math.cos(lat_r) * math.sin(lng_r)],
        [0,                                  math.cos(lat_r),                     math.sin(lat_r)]
    ])

    transform = np.eye(4)
    transform[:3, :3] = R
    transform[:3, 3] = [cx, cy, cz]
    return transform.flatten(order='F').tolist()  # column-major


def odm_origin_to_latlon(odm_origin: dict) -> tuple[float, float, float]:
    """Convert ODM origin to WGS84 lat/lon.

    Two supported formats:
    1. UTM offset from coords.txt: {'x', 'y', 'z', 'proj'} — projected via pyproj
    2. Direct WGS84 fallback: {'lat', 'lng', 'alt'} — used when coords.txt is
       unavailable (e.g. recovered from photo EXIF centroid). Returned as-is.

    Returns:
        (lat, lng, alt) in WGS84 degrees / meters
    """
    # Direct WGS84 form (fallback when coords.txt is gone)
    if 'lat' in odm_origin and 'lng' in odm_origin:
        return (
            float(odm_origin['lat']),
            float(odm_origin['lng']),
            float(odm_origin.get('alt', odm_origin.get('z', 0))),
        )

    proj_str = odm_origin.get('proj', '')

    # Try to extract EPSG from proj string
    epsg = None
    if 'EPSG' in proj_str:
        import re
        match = re.search(r'EPSG[:\s]+(\d+)', proj_str)
        if match:
            epsg = int(match.group(1))
    elif 'utm' in proj_str.lower():
        import re
        match = re.search(r'zone=(\d+)', proj_str)
        if match:
            zone = int(match.group(1))
            is_south = '+south' in proj_str
            epsg = 32600 + zone if not is_south else 32700 + zone

    if not epsg:
        raise ValueError(
            f"Cannot determine CRS for ODM origin (no proj/EPSG and no lat/lng): {odm_origin}"
        )

    transformer = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    lng, lat, alt = transformer.transform(odm_origin['x'], odm_origin['y'], odm_origin['z'])
    return lat, lng, alt


def generate_lods(glb_path: str, output_dir: str) -> dict[int, str]:
    """Generate LOD levels from a GLB file using gltf-transform simplify.

    Args:
        glb_path: Path to the optimized GLB (becomes lod0)
        output_dir: Directory to write lod0.glb, lod1.glb, etc.

    Returns:
        Dict mapping lod level → file path
    """
    os.makedirs(output_dir, exist_ok=True)
    env = os.environ.copy()
    env['PATH'] = f"{NODE_BIN_DIR}:{env.get('PATH', '')}"

    lod_paths = {}

    # LOD0 = copy of existing optimized GLB
    lod0_path = os.path.join(output_dir, "lod0.glb")
    shutil.copy2(glb_path, lod0_path)
    lod_paths[0] = lod0_path
    logger.info(f"LOD0: {os.path.getsize(lod0_path) / (1024*1024):.1f} MB (copy)")

    # LOD1-3 via gltf-transform simplify → optimize(textures) → draco(geometry).
    #
    # Both downstream steps MUST mirror the main-pipeline GLB optimize
    # (opensky_processor._process_mesh_artifacts), otherwise the rendered lod1
    # leaf gets hairline seams where the basemap bleeds through (verified
    # empirically on 01KQCPGFN546Q1BRD5MQ4F8TX7):
    #
    #   1. --lock-border true on simplify: ODM meshes have ~100 primitives (one
    #      per texture chunk) with split vertices at chunk boundaries. Without
    #      locking, meshopt decimates each primitive's shared edge independently
    #      → the two sides drift apart → cracks. Locking pins the topological
    #      borders (costs a little reduction near seams — correctness over size).
    #   2. draco --quantization-volume scene (NOT optimize --compress draco):
    #      the consolidated optimize form does not expose --quantization-volume
    #      and defaults to per-primitive "mesh" volume → ~7cm drift between
    #      shared vertices at 14-bit → the same hairline seams. Scene volume uses
    #      ONE grid for all primitives → zero drift.
    for level, ratio, error, tex_size in LOD_LEVELS:
        lod_path = os.path.join(output_dir, f"lod{level}.glb")
        simp_path = os.path.join(output_dir, f"lod{level}_simp.glb")
        opt_path = os.path.join(output_dir, f"lod{level}_opt.glb")

        # Simplify (lock borders so primitive seams don't tear)
        result = subprocess.run(
            [GLTF_TRANSFORM_PATH, "simplify", glb_path, simp_path,
             "--ratio", str(ratio), "--error", str(error),
             "--lock-border", "true"],
            capture_output=True, text=True, timeout=600, env=env,
        )
        if result.returncode != 0:
            logger.error(f"gltf-transform simplify LOD{level} failed: {result.stderr[:300]}")
            raise RuntimeError(f"LOD{level} simplify failed: {result.stderr[:300]}")

        # Step 1: textures only (WebP + resize), no geometry compression, no
        # re-simplify (already simplified above).
        result = subprocess.run(
            [GLTF_TRANSFORM_PATH, "optimize", simp_path, opt_path,
             "--compress", "false", "--texture-compress", "webp",
             "--texture-size", str(tex_size), "--simplify", "false"],
            capture_output=True, text=True, timeout=600, env=env,
        )
        if result.returncode != 0:
            logger.error(f"gltf-transform optimize LOD{level} failed: {result.stderr[:300]}")
            raise RuntimeError(f"LOD{level} optimize failed: {result.stderr[:300]}")

        # Step 2: Draco geometry compression with scene-wide quantization volume.
        result = subprocess.run(
            [GLTF_TRANSFORM_PATH, "draco", opt_path, lod_path,
             "--quantization-volume", "scene"],
            capture_output=True, text=True, timeout=600, env=env,
        )
        if result.returncode != 0:
            logger.error(f"gltf-transform draco LOD{level} failed: {result.stderr[:300]}")
            raise RuntimeError(f"LOD{level} draco failed: {result.stderr[:300]}")

        for p in (simp_path, opt_path):
            if os.path.exists(p):
                os.unlink(p)

        lod_paths[level] = lod_path
        size_mb = os.path.getsize(lod_path) / (1024 * 1024)
        logger.info(f"LOD{level}: {size_mb:.1f} MB (ratio={ratio})")

    return lod_paths


def generate_mission_tileset(mission) -> dict:
    """Generate per-mission tileset.json with ENU→ECEF transform.

    Args:
        mission: OpenSkyMission instance with center_lat, center_lng, area, odm_origin

    Returns:
        tileset.json dict
    """
    # Compute bounding region from mission area polygon (radians)
    if mission.area:
        coords = mission.area.coords[0]
        west = min(c[0] for c in coords) * math.pi / 180
        south = min(c[1] for c in coords) * math.pi / 180
        east = max(c[0] for c in coords) * math.pi / 180
        north = max(c[1] for c in coords) * math.pi / 180
    else:
        # Fallback: approximate from center ± 200m
        lat, lng = mission.center_lat, mission.center_lng
        dlat = 200 / 111320  # ~200m in degrees
        dlng = 200 / (111320 * math.cos(math.radians(lat)))
        west = (lng - dlng) * math.pi / 180
        south = (lat - dlat) * math.pi / 180
        east = (lng + dlng) * math.pi / 180
        north = (lat + dlat) * math.pi / 180

    # Altitude bounds in meters above WGS84 ellipsoid. Wide enough to enclose
    # any reasonable terrain — narrow bounds cause loaders.gl to cull tiles.
    # ODM mesh vertices typically span ~250m vertically; we add headroom for
    # mountain terrain (up to ~2000m) and below-ellipsoid bowls (down to -200m).
    region = [west, south, east, north, -200, 2000]

    # Compute ENU→ECEF transform
    # Use ODM origin for precise positioning if available
    if mission.odm_origin:
        try:
            origin_lat, origin_lng, origin_alt = odm_origin_to_latlon(mission.odm_origin)
            transform = local_to_ecef_transform(origin_lat, origin_lng, origin_alt)
        except Exception as e:
            logger.warning(f"ODM origin transform failed, using center: {e}")
            transform = local_to_ecef_transform(mission.center_lat, mission.center_lng)
    else:
        transform = local_to_ecef_transform(mission.center_lat, mission.center_lng)

    # Each child must have its own boundingVolume — strict per OGC 3D Tiles 1.1.
    # `region` is always in WGS84 (lat/lng radians) and ignores any parent transform,
    # so all LODs share the same region as the root.
    bv = {"region": region}
    # NOTE: lod0 is the unsimplified ODM mesh (44–53 MB GLB). It used to be the
    # leaf, but at close zoom on the live map deck.gl would select it for every
    # visible mission and lock the main thread on parse + GPU upload (browser
    # tab freeze). lod1 is now the leaf (50% mesh decimation, 21 MB) — enough
    # detail for in-map browsing. The lod0.glb file is still produced and stays
    # on skystore; for inspection-grade detail use the OpenSky Dashboard's
    # dedicated 3D viewer (`frontend/components/OpenSky/ModelViewer3D.vue`).
    return {
        "asset": {
            "version": "1.1",
            "generator": "parahub-opensky",
            # ODM produces meshes in Z-up local frame (ENU). Default 3D Tiles
            # interpretation is Y-up which would tilt the model 90° around X.
            # loaders.gl reads this from `tileset.asset.gltfUpAxis` (NOT from
            # loadOptions — that's a no-op).
            "gltfUpAxis": "Z",
        },
        "geometricError": GEOMETRIC_ERRORS['root'],
        "root": {
            "boundingVolume": bv,
            "geometricError": GEOMETRIC_ERRORS['root'],
            "refine": "REPLACE",
            "transform": transform,
            "children": [
                {
                    "boundingVolume": bv,
                    "geometricError": GEOMETRIC_ERRORS['lod3'],
                    "content": {"uri": "lod3.glb"},
                    "children": [
                        {
                            "boundingVolume": bv,
                            "geometricError": GEOMETRIC_ERRORS['lod2'],
                            "content": {"uri": "lod2.glb"},
                            "children": [
                                {
                                    "boundingVolume": bv,
                                    "geometricError": GEOMETRIC_ERRORS['lod1'],
                                    "content": {"uri": "lod1.glb"},
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }


def regenerate_root_tileset(exclude_id: str = None):
    """Regenerate /skystore/opensky-3dtiles/tileset.json from all MESH_READY missions.

    `exclude_id` lets callers (e.g. delete_skystore_mission_files) skip a mission
    that's about to be removed from DB but is still present at the moment of the
    call. Without it, the regenerated root would still link the doomed child.
    """
    from geo.models import OpenSkyMission

    missions = OpenSkyMission.objects.filter(
        mesh_status=OpenSkyMission.MeshStatus.MESH_READY,
        area__isnull=False,
    )
    if exclude_id:
        missions = missions.exclude(id=exclude_id)
    if not missions.exists():
        logger.info("No MESH_READY missions with area — removing root tileset")
        try:
            _skystore_ssh(f"rm -f {SKYSTORE_3DTILES}/tileset.json")
        except Exception:
            pass
        return

    children = []
    all_regions = []
    for m in missions:
        coords = m.area.coords[0]
        region = [
            min(c[0] for c in coords) * math.pi / 180,
            min(c[1] for c in coords) * math.pi / 180,
            max(c[0] for c in coords) * math.pi / 180,
            max(c[1] for c in coords) * math.pi / 180,
            -200, 2000,  # Wide altitude bounds — see generate_mission_tileset()
        ]
        all_regions.append(region)
        children.append({
            "boundingVolume": {"region": region},
            "geometricError": GEOMETRIC_ERRORS['root'],
            "content": {"uri": f"missions/{m.id}/tileset.json?v={TILESET_SCHEMA_VERSION}"},
        })

    global_region = [
        min(r[0] for r in all_regions),
        min(r[1] for r in all_regions),
        max(r[2] for r in all_regions),
        max(r[3] for r in all_regions),
        0, 200,
    ]

    tileset = {
        "asset": {
            "version": "1.1",
            "generator": "parahub-opensky",
            # loaders.gl reads `asset.gltfUpAxis` from the ROOT tileset only
            # (via get3dTilesOptions(this.tileset.tileset)). MUST be set here
            # too, not just on per-mission sub-tilesets, otherwise meshes are
            # rotated 90° around X (Y-up default).
            "gltfUpAxis": "Z",
        },
        "geometricError": 500,
        "root": {
            "boundingVolume": {"region": global_region},
            "geometricError": 500,
            "refine": "ADD",
            "children": children,
        },
    }

    # Write to temp file and upload to skystore
    # NamedTemporaryFile defaults to mode 600 — chmod 644 so nginx (www-data) can read.
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(tileset, f, indent=2)
        tmp_path = f.name
    os.chmod(tmp_path, 0o644)

    try:
        _skystore_ssh(f"mkdir -p {SKYSTORE_3DTILES}")
        _skystore_rsync(tmp_path, f"{SKYSTORE_3DTILES}/tileset.json")
        logger.info(f"Root tileset regenerated with {len(children)} mission(s)")
    finally:
        os.unlink(tmp_path)


def regenerate_mission_tileset(mission) -> bool:
    """Regenerate ONLY the per-mission tileset.json (no LOD GLB rebuild).

    Use after a tileset schema change (e.g. dropping lod0 from the LOD chain)
    when the GLB files on skystore are still valid and only the index needs
    updating. Avoids the 30-min ODM/decimation pipeline.
    """
    try:
        tileset = generate_mission_tileset(mission)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(tileset, f, indent=2)
            tmp_path = f.name
        os.chmod(tmp_path, 0o644)
        try:
            remote = f"{SKYSTORE_3DTILES}/missions/{mission.id}/tileset.json"
            _skystore_ssh(f"mkdir -p {SKYSTORE_3DTILES}/missions/{mission.id}")
            _skystore_rsync(tmp_path, remote)
            logger.info(f"Per-mission tileset regenerated for {mission.id}")
            return True
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        logger.error(f"Per-mission tileset regen failed for {mission.id}: {e}", exc_info=True)
        return False


def generate_3d_tiles_for_mission(mission, glb_path: str = None) -> bool:
    """Generate LODs + tileset.json for a single mission, upload to skystore.

    Args:
        mission: OpenSkyMission instance (MESH_READY with area + center)
        glb_path: Optional path to the GLB file. If None, downloads from skystore.

    Returns:
        True on success, False on failure
    """
    local_tiles_dir = os.path.join(MESHES_LOCAL_DIR, f"{mission.id}_3dtiles")
    downloaded_glb = False

    try:
        os.makedirs(local_tiles_dir, exist_ok=True)

        # Get GLB path
        if not glb_path:
            # Download from skystore
            remote_glb = f"{SKYSTORE_OPENSKY}/meshes/{mission.id}/model.glb"
            glb_path = os.path.join(local_tiles_dir, "model.glb")
            subprocess.run(
                ["rsync", "-a", f"{SKYSTORE_SSH}:{remote_glb}", glb_path],
                timeout=300, check=True, capture_output=True, text=True,
            )
            downloaded_glb = True

        # Generate LODs
        lods_dir = os.path.join(local_tiles_dir, "lods")
        generate_lods(glb_path, lods_dir)

        # Generate per-mission tileset.json
        tileset = generate_mission_tileset(mission)
        tileset_path = os.path.join(lods_dir, "tileset.json")
        with open(tileset_path, 'w') as f:
            json.dump(tileset, f, indent=2)

        # Upload to skystore
        remote_tiles = f"{SKYSTORE_3DTILES}/missions/{mission.id}"
        _skystore_ssh(f"mkdir -p {remote_tiles}")
        _skystore_rsync(f"{lods_dir}/", f"{remote_tiles}/", delete=True)

        logger.info(f"3D Tiles generated for mission {mission.id}")

        # Regenerate root tileset
        regenerate_root_tileset()

        return True

    except Exception as e:
        logger.error(f"3D Tiles generation failed for {mission.id}: {e}", exc_info=True)
        return False
    finally:
        if os.path.exists(local_tiles_dir):
            shutil.rmtree(local_tiles_dir, ignore_errors=True)
