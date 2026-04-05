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
LOD_LEVELS = [
    # lod0 = copy of original optimized GLB (no simplification)
    (1, 0.5, 0.01, 2048),
    (2, 0.1, 0.05, 1024),
    (3, 0.02, 0.1, 512),
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
    """Convert ODM UTM origin to WGS84 lat/lon.

    ODM stores the reconstruction origin in UTM coordinates in coords.txt.
    We need to detect the UTM zone from the proj.txt or from the coordinate values.

    Args:
        odm_origin: dict with 'x', 'y', 'z' (UTM meters), optionally 'proj' (proj string)

    Returns:
        (lat, lng, alt) in WGS84 degrees
    """
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
            # Check hemisphere from +north/+south
            is_south = '+south' in proj_str
            epsg = 32600 + zone if not is_south else 32700 + zone

    if not epsg:
        # Guess UTM zone from X coordinate (100000-999999 range) and Y
        # Y > 10000000 → southern hemisphere
        x, y = odm_origin['x'], odm_origin['y']
        is_south = y > 10000000
        # X in UTM is 6-digit with false easting 500000, so zone can't be determined from X alone
        # Fall back: use mission center_lat/center_lng (caller should provide)
        logger.warning("Could not determine EPSG from ODM origin, falling back to EPSG:4326 assumption")
        return odm_origin.get('lat', 0), odm_origin.get('lng', 0), odm_origin.get('z', 0)

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

    # LOD1-3 via gltf-transform simplify + optimize
    for level, ratio, error, tex_size in LOD_LEVELS:
        lod_path = os.path.join(output_dir, f"lod{level}.glb")
        tmp_path = os.path.join(output_dir, f"lod{level}_tmp.glb")

        # Simplify
        result = subprocess.run(
            [GLTF_TRANSFORM_PATH, "simplify", glb_path, tmp_path,
             "--ratio", str(ratio), "--error", str(error)],
            capture_output=True, text=True, timeout=600, env=env,
        )
        if result.returncode != 0:
            logger.error(f"gltf-transform simplify LOD{level} failed: {result.stderr[:300]}")
            raise RuntimeError(f"LOD{level} simplify failed: {result.stderr[:300]}")

        # Optimize (Draco + WebP + texture resize)
        result = subprocess.run(
            [GLTF_TRANSFORM_PATH, "optimize", tmp_path, lod_path,
             "--compress", "draco", "--texture-compress", "webp",
             "--texture-size", str(tex_size)],
            capture_output=True, text=True, timeout=600, env=env,
        )
        if result.returncode != 0:
            logger.error(f"gltf-transform optimize LOD{level} failed: {result.stderr[:300]}")
            raise RuntimeError(f"LOD{level} optimize failed: {result.stderr[:300]}")

        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

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

    region = [west, south, east, north, 0, 200]

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

    return {
        "asset": {"version": "1.1", "generator": "parahub-opensky"},
        "geometricError": GEOMETRIC_ERRORS['root'],
        "root": {
            "boundingVolume": {"region": region},
            "geometricError": GEOMETRIC_ERRORS['root'],
            "refine": "REPLACE",
            "transform": transform,
            "children": [
                {
                    "geometricError": GEOMETRIC_ERRORS['lod3'],
                    "content": {"uri": "lod3.glb"},
                    "children": [
                        {
                            "geometricError": GEOMETRIC_ERRORS['lod2'],
                            "content": {"uri": "lod2.glb"},
                            "children": [
                                {
                                    "geometricError": GEOMETRIC_ERRORS['lod1'],
                                    "content": {"uri": "lod1.glb"},
                                    "children": [
                                        {
                                            "geometricError": GEOMETRIC_ERRORS['lod0'],
                                            "content": {"uri": "lod0.glb"},
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }


def regenerate_root_tileset():
    """Regenerate /skystore/opensky-3dtiles/tileset.json from all MESH_READY missions."""
    from geo.models import OpenSkyMission

    missions = OpenSkyMission.objects.filter(
        mesh_status=OpenSkyMission.MeshStatus.MESH_READY,
        area__isnull=False,
    )
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
            0, 200,
        ]
        all_regions.append(region)
        children.append({
            "boundingVolume": {"region": region},
            "geometricError": GEOMETRIC_ERRORS['root'],
            "content": {"uri": f"missions/{m.id}/tileset.json"},
        })

    global_region = [
        min(r[0] for r in all_regions),
        min(r[1] for r in all_regions),
        max(r[2] for r in all_regions),
        max(r[3] for r in all_regions),
        0, 200,
    ]

    tileset = {
        "asset": {"version": "1.1", "generator": "parahub-opensky"},
        "geometricError": 500,
        "root": {
            "boundingVolume": {"region": global_region},
            "geometricError": 500,
            "refine": "ADD",
            "children": children,
        },
    }

    # Write to temp file and upload to skystore
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(tileset, f, indent=2)
        tmp_path = f.name

    try:
        _skystore_ssh(f"mkdir -p {SKYSTORE_3DTILES}")
        _skystore_rsync(tmp_path, f"{SKYSTORE_3DTILES}/tileset.json")
        logger.info(f"Root tileset regenerated with {len(children)} mission(s)")
    finally:
        os.unlink(tmp_path)


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
