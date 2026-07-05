"""
Step 5.5 — 3D mesh artifacts: ODM origin extraction (UTM offset + proj), mesh
ground level (p5 vertex z), and the OBJ→GLB convert/optimize/upload chain
(two-step Draco with scene-wide quantization — see the comment inside).
"""

import logging
import os
import shlex
import subprocess

from .constants import (
    GLTF_TRANSFORM_PATH, MESHES_LOCAL_DIR, NODE_BIN_DIR, OBJ2GLTF_PATH,
    SKYSTORE_OPENSKY, SKYSTORE_SSH,
)
from .remote import _skystore_rsync, _skystore_ssh

logger = logging.getLogger(__name__)


def _compute_mesh_ground_z(mission_id: str) -> float | None:
    """Compute the 5th-percentile vertex z value of an OBJ mesh on skystore.

    Used as the "ground level" of the mesh (robust against deep-hole outliers
    that pull min z way down). The tileset transform's origin altitude is set
    to -ground_z so the mesh's ground sits at WGS84 ellipsoid altitude 0,
    matching the OSM 2D base layer.

    Returns p5 in meters, or None on failure.
    """
    obj_path = f"{SKYSTORE_OPENSKY}/meshes/{mission_id}/model.obj"
    script = (
        "import sys\n"
        f"zs=[]\n"
        f"with open('{obj_path}') as f:\n"
        f"    for line in f:\n"
        f"        if line.startswith('v '):\n"
        f"            zs.append(float(line.split()[3]))\n"
        f"zs.sort()\n"
        f"print(zs[len(zs)*5//100] if zs else '')"
    )
    try:
        result = _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=120)
        out = result.stdout.strip()
        if not out:
            return None
        return float(out)
    except Exception as e:
        logger.warning(f"Failed to compute mesh ground z: {e}")
        return None


def _extract_odm_origin(remote_processing_or_mission_id: str) -> dict | None:
    """Extract ODM reconstruction origin (UTM offset) from skystore.

    Reads `odm_georeferencing_model_geo.txt` (clean 2-line format, preferred)
    with fallback to `coords.txt` (which has the same UTM offset on line 2 but
    is also full of per-image entries we must skip).

    Looks in two places:
    1. The temp processing dir (during pipeline run, before cleanup).
    2. `meshes/{mission_id}/` (persisted post-pipeline — used when regenerating
       tilesets without re-running ODM).

    Argument can be either a full processing path (with `/odm_georeferencing/`)
    or just a mission ID (then we look in `meshes/{id}/`).

    Returns dict with {x, y, z=0, proj} or None if not found.
    Note: ODM stores only x,y in the offset files. z=0 means the tileset
    origin sits at WGS84 ellipsoid altitude; the mesh vertices encode their
    own absolute altitudes relative to ODM's local frame anchor.
    """
    try:
        # Prefer odm_georeferencing_model_geo.txt — clean 2-line format:
        #   Line 1: "WGS84 UTM 29N" (header)
        #   Line 2: "551452 4652829" (UTM offset, 2 floats)
        # Falls back to coords.txt which has the same line 2 but also
        # per-image entries (3-float lines we must NOT pick).
        result = _skystore_ssh(
            f"cat {remote_processing_or_mission_id}/odm_georeferencing/odm_georeferencing_model_geo.txt 2>/dev/null || "
            f"cat {SKYSTORE_OPENSKY}/meshes/{remote_processing_or_mission_id}/odm_georeferencing_model_geo.txt 2>/dev/null || "
            f"cat {remote_processing_or_mission_id}/odm_georeferencing/coords.txt 2>/dev/null || "
            f"cat {SKYSTORE_OPENSKY}/meshes/{remote_processing_or_mission_id}/coords.txt 2>/dev/null || "
            f"echo NOTFOUND"
        )
        if "NOTFOUND" in result.stdout:
            logger.warning(f"ODM origin file not found in {remote_processing_or_mission_id}")
            return None

        # We want line 2 specifically: "<utm_x> <utm_y>" (2 floats, no z).
        # In coords.txt, line 3+ has 3 floats (per-image local coords) — must SKIP.
        # Strategy: take the FIRST non-header line; require exactly 2 floats
        # (3+ floats means we're in coords.txt per-image section — ignore).
        x = y = None
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            try:
                # Need at least 2 parseable floats. ODM offset is exactly 2.
                px, py = float(parts[0]), float(parts[1])
            except (ValueError, IndexError):
                # Header line like "WGS84 UTM 29N" — skip
                continue
            # Reject lines with 3+ floats (per-image entries in coords.txt).
            if len(parts) >= 3:
                try:
                    float(parts[2])
                    continue  # 3rd is float — per-image entry, skip
                except ValueError:
                    pass  # 3rd is not float — OK, this is a 2-value line
            x, y = px, py
            break

        if x is None:
            logger.warning(f"Could not parse UTM offset from ODM files in {remote_processing_or_mission_id}")
            return None

        # z=0: ODM offset files don't include altitude. The mesh vertices
        # carry absolute altitudes (relative to ODM's local frame anchor).
        origin = {'x': x, 'y': y, 'z': 0}
        logger.info(f"ODM origin: x={x:.3f} y={y:.3f} z=0 (mesh vertices encode altitude)")

        # Read EPSG from proj.txt (needed for UTM→WGS84 conversion).
        try:
            proj_result = _skystore_ssh(
                f"cat {remote_processing_or_mission_id}/odm_georeferencing/proj.txt 2>/dev/null || "
                f"cat {SKYSTORE_OPENSKY}/meshes/{remote_processing_or_mission_id}/proj.txt 2>/dev/null || "
                f"echo ''"
            )
            proj_str = proj_result.stdout.strip()
            if proj_str:
                origin['proj'] = proj_str
                logger.info(f"ODM proj: {proj_str[:80]}")
        except Exception:
            pass

        return origin
    except Exception as e:
        logger.warning(f"Failed to extract ODM origin: {e}")
        return None


def _process_mesh_artifacts(mission_id: str, remote_processing: str) -> tuple[float, str]:
    """Download mesh from skystore, convert OBJ→GLB, optimize.

    Returns (glb_size_mb, local_mesh_dir).
    """
    import re
    from pathlib import Path

    remote_texturing = f"{remote_processing}/odm_texturing"
    local_mesh = f"{MESHES_LOCAL_DIR}/{mission_id}"
    remote_meshes = f"{SKYSTORE_OPENSKY}/meshes/{mission_id}"

    os.makedirs(local_mesh, exist_ok=True)

    # Download OBJ + MTL + textures from skystore
    subprocess.run(
        ["rsync", "-a",
         "--include=*.obj", "--include=*.mtl", "--include=*.png",
         "--exclude=*",
         f"{SKYSTORE_SSH}:{remote_texturing}/", f"{local_mesh}/"],
        timeout=600, check=True, capture_output=True, text=True,
    )

    # Rename geo OBJ/MTL to standard names
    for f in os.listdir(local_mesh):
        full = os.path.join(local_mesh, f)
        if f.endswith('.obj') and 'geo' in f:
            os.rename(full, os.path.join(local_mesh, "model.obj"))
        elif f.endswith('.mtl') and 'geo' in f:
            os.rename(full, os.path.join(local_mesh, "model.mtl"))

    # Fix OBJ mtllib reference
    obj_path = os.path.join(local_mesh, "model.obj")
    if os.path.exists(obj_path):
        content = Path(obj_path).read_text()
        content = re.sub(r'mtllib\s+\S+', 'mtllib model.mtl', content)
        Path(obj_path).write_text(content)

    # Convert OBJ → GLB
    glb_path = os.path.join(local_mesh, "model.glb")
    env = os.environ.copy()
    env['PATH'] = f"{NODE_BIN_DIR}:{env.get('PATH', '')}"

    result = subprocess.run(
        [OBJ2GLTF_PATH, "-i", obj_path, "-o", glb_path, "--binary"],
        capture_output=True, text=True, timeout=600, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"obj2gltf failed: {result.stderr[:500]}")

    # Optimize GLB in two steps so Draco can use scene-wide quantization volume.
    #
    # Why two steps: `gltf-transform optimize` doesn't expose `--quantization-volume`
    # for its built-in Draco pass. Default is "mesh" volume — each primitive
    # is quantized with its OWN bbox. For our ODM meshes (~100 primitives, one
    # per material/texture chunk, sharing ~37% of vertices at material boundaries),
    # independent per-primitive quantization drifts shared vertices apart by up
    # to ~7cm at 14-bit precision over 850m bbox, creating hairline gaps in the
    # rendered mesh where the OSM basemap shows through (verified empirically).
    #
    # Scene volume uses ONE quantization grid for all primitives, so vertices
    # shared across primitives fall in the same grid cell and decode to the
    # exact same position → zero drift, no seams. Also slightly smaller GLB
    # (shared grid compresses better than per-primitive grids).
    #
    # Step 1: optimize without geometry compression (texture compression, weld,
    # prune, etc.). Does NOT merge the 98 primitives because each has a distinct
    # material/texture.
    opt_path = glb_path.replace('.glb', '_opt.glb')
    result = subprocess.run(
        [GLTF_TRANSFORM_PATH, "optimize", glb_path, opt_path,
         "--compress", "false", "--texture-compress", "webp",
         "--texture-size", "4096", "--simplify", "false"],
        capture_output=True, text=True, timeout=1800, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gltf-transform optimize failed: {result.stderr[:500]}")

    # Step 2: Draco geometry compression with scene-wide quantization volume.
    drc_path = glb_path.replace('.glb', '_drc.glb')
    result = subprocess.run(
        [GLTF_TRANSFORM_PATH, "draco", opt_path, drc_path,
         "--quantization-volume", "scene"],
        capture_output=True, text=True, timeout=1800, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gltf-transform draco failed: {result.stderr[:500]}")

    os.replace(drc_path, glb_path)
    if os.path.exists(opt_path):
        os.remove(opt_path)

    glb_size_mb = round(os.path.getsize(glb_path) / (1024 * 1024), 2)
    logger.info(f"Mesh GLB ready: {glb_size_mb} MB")

    # Upload to skystore meshes dir
    _skystore_ssh(f"mkdir -p {remote_meshes}")
    _skystore_rsync(f"{local_mesh}/", f"{remote_meshes}/", delete=True)

    return glb_size_mb, local_mesh
