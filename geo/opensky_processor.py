"""
OpenSky Aerial Imagery Processor

All processing and storage on skystore (Home PT, <SKYSTORE_IP> via WireGuard).
Hetzner orchestrates via SSH, only DB updates are local.

Pipeline: Upload ZIP → rsync to skystore → ODM GPU → gdalwarp → alignment →
gdal2tiles → TMS→XYZ WebP → hard links to latest/ → PUBLISHED.

Storage (on skystore /skystore/):
  /skystore/opensky/missions/{id}/images/   # Source photos
  /skystore/opensky/orthos/{id}.tif         # Preserved orthophotos (EPSG:3857)
  /fast-processing/{id}/                     # ODM temp files (SSD)
  /skystore/opensky/meshes/{id}/            # 3D mesh artifacts
  /skystore/opensky-tiles/missions/{id}/{z}/{x}/{y}.webp  # Mission tiles
  /skystore/opensky-tiles/latest/{z}/{x}/{y}.webp         # Hard links

Local temp (Hetzner /mnt/opensky/):
  missions/{id}/images/  # Upload buffer only, deleted after rsync to skystore
"""

import os
import math
import shlex
import shutil
import subprocess
import logging
import json
import time
from contextlib import contextmanager

import requests

from django.contrib.gis.geos import Polygon
from django.db import models, connection
from django.utils import timezone

logger = logging.getLogger(__name__)

# Session-level Postgres advisory lock serializing all latest/ + OpenSkyTileLayer
# mutations. The per-mission processor (process_opensky_queue) and the manual
# consolidation must not write the same tile coords concurrently. The processor
# try-acquires and skips a tick if held; consolidation blocks (operator action).
OPENSKY_TILE_LOCK_KEY = 478215


@contextmanager
def opensky_tile_lock(blocking: bool = True):
    """Acquire the shared OpenSky tile advisory lock. Yields True if held.

    blocking=True waits for the lock (consolidation); blocking=False try-locks
    and yields False if another holder has it (processor — skip this tick).
    Auto-released on connection close if the process dies mid-run.
    """
    with connection.cursor() as cur:
        if blocking:
            cur.execute("SELECT pg_advisory_lock(%s)", [OPENSKY_TILE_LOCK_KEY])
            acquired = True
        else:
            cur.execute("SELECT pg_try_advisory_lock(%s)", [OPENSKY_TILE_LOCK_KEY])
            acquired = bool(cur.fetchone()[0])
        try:
            yield acquired
        finally:
            if acquired:
                with connection.cursor() as c2:
                    c2.execute("SELECT pg_advisory_unlock(%s)", [OPENSKY_TILE_LOCK_KEY])


def _publish_mission_update(mission_id: str, data: dict):
    """Publish mission update to Redis for real-time WebSocket delivery."""
    import redis as _redis
    try:
        r = _redis.Redis()
        payload = json.dumps({'type': 'opensky.mission_updated', 'mission_id': str(mission_id), **data})
        r.publish('opensky:missions', payload)
    except Exception as e:
        logger.warning(f'Failed to publish opensky update: {e}')


# Local Pelias geocoder (same host as the backend).
PELIAS_URL = "http://localhost:4000"


def reverse_geocode_place(lat, lng):
    """Reverse-geocode a coordinate to ``(place_label, place_region)`` via local Pelias.

    Restricted to area-level layers (parish / municipality / county / region) so an
    open-countryside survey resolves to its parish rather than the nearest street.
    Mirrors the frontend card readout (placeName / placeRegion). Returns ``('', '')``
    on any failure so the caller leaves the existing stored value untouched.
    """
    if lat is None or lng is None:
        return '', ''
    try:
        resp = requests.get(
            f"{PELIAS_URL}/v1/reverse",
            params={
                'point.lat': lat,
                'point.lon': lng,
                'size': 1,
                'layers': 'locality,localadmin,county,region',
            },
            timeout=5,
        )
        resp.raise_for_status()
        features = resp.json().get('features', [])
        if not features:
            return '', ''
        p = features[0].get('properties', {})
        label = (p.get('locality') or p.get('localadmin') or p.get('name')
                 or p.get('county') or p.get('region') or '')
        region = ' · '.join(x for x in (p.get('region'), p.get('country')) if x)
        return label, region
    except Exception as e:
        logger.warning(f"reverse_geocode_place({lat},{lng}) failed: {e}")
        return '', ''


def _skystore_ssh(cmd: str, timeout: int = 60, retries: int = 5) -> subprocess.CompletedProcess:
    """Run a command on skystore via SSH with retry on SSH connection failure (exit 255).

    Retry backoff 5/10/20/40s bridges the short WireGuard/CGNAT flaps observed
    2026-06-12 (sub-minute drops killed two runs at 3x5s). ServerAlive makes a
    LONG-lived ssh (docker wait holds one for hours) detect a dead peer in
    <=10min instead of hanging until its own timeout — a skystore power-loss
    left docker-wait hung on a dead TCP for 5h before this.

    NOTE: TimeoutExpired is NOT retried — local SSH timeout doesn't kill remote process,
    so retry would spawn duplicate concurrent runs. Caller must set adequate timeout.
    """
    for attempt in range(1, retries + 1):
        try:
            return subprocess.run(
                ["ssh", "-o", "ConnectTimeout=10",
                 "-o", "ServerAliveInterval=60", "-o", "ServerAliveCountMax=10",
                 SKYSTORE_SSH, cmd],
                timeout=timeout, check=True,
                capture_output=True, text=True,
            )
        except subprocess.TimeoutExpired:
            logger.error(
                f'Skystore SSH command timed out after {timeout}s. '
                f'Remote process may still be running — DO NOT retry to avoid duplicates.'
            )
            raise
        except subprocess.CalledProcessError as e:
            # Log stderr/stdout for debugging remote command failures
            if e.returncode != 255:
                if e.stderr:
                    logger.error(f'Skystore SSH command stderr (last 2000 chars): {e.stderr[-2000:]}')
                if e.stdout:
                    logger.info(f'Skystore SSH command stdout (last 1000 chars): {e.stdout[-1000:]}')
            # Only retry SSH connection failures (exit 255), not remote command errors
            if e.returncode == 255 and attempt < retries:
                backoff = 5 * (2 ** (attempt - 1))  # 5, 10, 20, 40s
                logger.warning(
                    f'Skystore SSH attempt {attempt}/{retries} connection failed, retrying in {backoff}s...')
                time.sleep(backoff)
            else:
                if e.returncode == 255 and e.stderr:
                    # 255 is also AUTH failure, not just transport — surface it
                    # (a root-without-key unit burned 3 runs looking like "flaps")
                    logger.error(f'Skystore SSH final failure stderr: {e.stderr[-500:]}')
                raise


def _skystore_rsync(src: str, dst: str, timeout: int = 600, delete: bool = False, retries: int = 3):
    """Rsync local path to skystore with retry on connection failure."""
    cmd = ["rsync", "-a"]
    if delete:
        cmd.append("--delete")
    cmd.extend([src, f"{SKYSTORE_SSH}:{dst}"])
    for attempt in range(1, retries + 1):
        try:
            subprocess.run(cmd, timeout=timeout, check=True, capture_output=True, text=True)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            if attempt < retries:
                logger.warning(f'Skystore rsync attempt {attempt}/{retries} failed: {e}, retrying in 5s...')
                time.sleep(5)
            else:
                raise


def upload_to_skystore(mission_id: str):
    """Move uploaded mission photos from Hetzner to skystore, delete local copy."""
    local_images = f"{OPENSKY_BASE}/missions/{mission_id}/images/"
    remote_mission = f"{SKYSTORE_OPENSKY}/missions/{mission_id}/"
    if not os.path.exists(local_images):
        raise FileNotFoundError(f"Local images not found: {local_images}")
    _skystore_ssh(f"mkdir -p {remote_mission}images")
    _skystore_rsync(local_images, f"{remote_mission}images/", timeout=1200)
    # Verify file count matches
    local_count = len([f for f in os.listdir(local_images) if f.lower().endswith(('.jpg', '.jpeg'))])
    result = _skystore_ssh(f"ls {remote_mission}images/*.jpg {remote_mission}images/*.JPG {remote_mission}images/*.jpeg 2>/dev/null | wc -l")
    remote_count = int(result.stdout.strip())
    if remote_count < local_count:
        raise RuntimeError(f"Upload verification failed: local={local_count}, remote={remote_count}")
    # Delete local copy
    shutil.rmtree(f"{OPENSKY_BASE}/missions/{mission_id}", ignore_errors=True)
    logger.info(f"Uploaded {local_count} photos to skystore, deleted local copy")


# Reclaim orphaned ODM scratch. /fast-processing is only 87 GB SSD and leaks when
# a run fails: process_mission keeps the temp dir "for diagnostics" (lightweight
# failure_logs are saved separately on skystore) and clears it only on retry —
# which may never come. Sweep dirs whose mission is no longer PROCESSING and
# untouched for > FAST_PROCESSING_ORPHAN_HOURS. Unknown dirs (manual experiments,
# lost+found) are left alone. The freshest failure stays briefly for live debug.
FAST_PROCESSING_ORPHAN_HOURS = 24


def sweep_orphaned_processing_dirs() -> int:
    """Delete stale /fast-processing/<mission_id> dirs for non-PROCESSING missions.

    Safe by construction: only removes a dir named after a known ULID whose mission
    is not currently PROCESSING (never yanks an active run) and whose mtime is older
    than the threshold. Returns the number of dirs reclaimed.
    """
    from geo.models import OpenSkyMission
    try:
        res = _skystore_ssh(
            f"find {SKYSTORE_FAST_PROCESSING} -maxdepth 1 -mindepth 1 -type d -printf '%f %T@\\n'"
        )
    except Exception as e:
        logger.warning(f"orphan sweep: cannot list {SKYSTORE_FAST_PROCESSING}: {e}")
        return 0

    now = time.time()
    cutoff = FAST_PROCESSING_ORPHAN_HOURS * 3600
    removed = 0
    for line in res.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        name, mtime = parts
        # Only ULID-named mission dirs (26 chars, Crockford base32). Skip everything else.
        if len(name) != 26 or not name.isalnum():
            continue
        try:
            age = now - float(mtime)
        except ValueError:
            continue
        if age < cutoff:
            continue
        m = OpenSkyMission.objects.filter(id=name).first()
        if m and m.status == OpenSkyMission.Status.PROCESSING:
            continue  # never reclaim an active run's scratch
        try:
            _skystore_ssh(f"sudo rm -rf {SKYSTORE_FAST_PROCESSING}/{name}")
            removed += 1
            logger.info(
                f"orphan sweep: reclaimed {SKYSTORE_FAST_PROCESSING}/{name} "
                f"(status={m.status if m else 'DELETED'}, age={age / 3600:.0f}h)"
            )
        except Exception as e:
            logger.warning(f"orphan sweep: failed to remove {name}: {e}")
    return removed


def run_odm_skystore(mission_id: str) -> str:
    """Run ODM on skystore via SSH + Docker GPU. Returns remote orthophoto path."""
    remote_images = f"{SKYSTORE_OPENSKY}/missions/{mission_id}/images"
    remote_processing = f"{SKYSTORE_FAST_PROCESSING}/{mission_id}"
    remote_ortho = f"{remote_processing}/odm_orthophoto/odm_orthophoto.tif"
    container_name = f"odm-{mission_id[:12]}"

    # Skip if previous run already produced orthophoto (e.g. crashed at report stage)
    check = _skystore_ssh(f"test -f {remote_ortho} && echo exists || echo missing")
    if "exists" in check.stdout:
        logger.info(f"ODM orthophoto already exists, skipping ODM run: {remote_ortho}")
        return remote_ortho

    # Clean previous run (Docker creates root-owned files) and prepare project dir on SSD
    _skystore_ssh(f"sudo rm -rf {remote_processing} && mkdir -p {remote_processing}")
    # Remove stale container with same name if exists
    _skystore_ssh(f"docker rm -f {container_name} 2>/dev/null || true")
    # Symlink source images (on HDD) into processing dir (on SSD)
    _skystore_ssh(f"ln -sfn {remote_images} {remote_processing}/images")
    # --end-with odm_orthophoto: skip odm_report stage (broken in current ODM image due to numpy 1.x/2.x conflict)
    docker_cmd = (
        f"docker run --name {container_name} --gpus all"
        f" -v {SKYSTORE_FAST_PROCESSING}:{SKYSTORE_FAST_PROCESSING}"
        f" -v {SKYSTORE_OPENSKY}/missions:{SKYSTORE_OPENSKY}/missions:ro"
        f" {SKYSTORE_ODM_IMAGE}"
        f" --project-path {SKYSTORE_FAST_PROCESSING}"
        f" --orthophoto-resolution {ODM_RESOLUTION}"
        f" --feature-quality high"
        f" --pc-quality high"
        f" --max-concurrency {ODM_MAX_CONCURRENCY}"
        f" --dsm"
        # NO --optimize-disk-space since the 2TB NVMe (2026-06-12): it was for the
        # 87GB-SSD era and deletes resume checkpoints (features/matches/dmaps) —
        # a power-loss restart then re-derives ~1.5h. Peak ~300GB fits easily;
        # scratch is removed on success anyway.
        f" --end-with odm_orthophoto"
        f" {mission_id}"
    )
    logger.info(f"Running ODM on skystore: {docker_cmd}")
    try:
        _skystore_ssh(docker_cmd, timeout=28800)  # 8h timeout (large missions)
    except subprocess.CalledProcessError:
        # Capture docker logs before cleanup
        _save_odm_failure_logs(mission_id, container_name)
        raise
    finally:
        # Remove container (logs already saved on failure)
        _skystore_ssh(f"docker rm -f {container_name} 2>/dev/null || true")
    result = _skystore_ssh(f"test -f {remote_ortho} && echo ok")
    if "ok" not in result.stdout:
        raise RuntimeError("ODM on skystore failed to produce orthophoto")
    return remote_ortho


def _save_odm_failure_logs(mission_id: str, container_name: str):
    """Save docker logs and system state to skystore for post-mortem analysis."""
    log_dir = f"{SKYSTORE_OPENSKY}/missions/{mission_id}/failure_logs"
    try:
        _skystore_ssh(f"mkdir -p {log_dir}")
        # Docker logs (last 500 lines)
        _skystore_ssh(
            f"docker logs --tail 500 {container_name} > {log_dir}/odm_stdout.log 2> {log_dir}/odm_stderr.log || true"
        )
        # System state at time of failure
        _skystore_ssh(
            f"echo '=== dmesg (OOM) ===' > {log_dir}/system.log"
            f" && dmesg -T 2>/dev/null | grep -i -E 'oom|kill|memory' | tail -30 >> {log_dir}/system.log || true"
            f" && echo '\\n=== free ===' >> {log_dir}/system.log"
            f" && free -h >> {log_dir}/system.log"
            f" && echo '\\n=== df ===' >> {log_dir}/system.log"
            f" && df -h /fast-processing /skystore >> {log_dir}/system.log"
        )
        logger.error(f"ODM failure logs saved to skystore: {log_dir}")
    except Exception as ex:
        logger.error(f"Failed to save ODM failure logs: {ex}")


def _build_tms_to_xyz_webp_script(tms_dir: str, xyz_dir: str, quality: int) -> str:
    """Build standalone Python script for TMS→XYZ WebP conversion on skystore."""
    return f'''
import os
from PIL import Image
tms_dir = "{tms_dir}"
xyz_dir = "{xyz_dir}"
quality = {quality}
tiles_count = 0
total_size = 0
for z_str in os.listdir(tms_dir):
    z_path = os.path.join(tms_dir, z_str)
    if not os.path.isdir(z_path) or not z_str.isdigit():
        continue
    z = int(z_str)
    max_y = (2 ** z) - 1
    for x_str in os.listdir(z_path):
        x_path = os.path.join(z_path, x_str)
        if not os.path.isdir(x_path) or not x_str.isdigit():
            continue
        for tile_file in os.listdir(x_path):
            if not tile_file.endswith(".png"):
                continue
            tms_y = int(tile_file.replace(".png", ""))
            xyz_y = max_y - tms_y
            out_dir = os.path.join(xyz_dir, z_str, x_str)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{{xyz_y}}.webp")
            try:
                img = Image.open(os.path.join(x_path, tile_file))
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                img.save(out_path, "WEBP", quality=quality)
                total_size += os.path.getsize(out_path)
                tiles_count += 1
            except Exception:
                pass
print(f"TILES_RESULT:{{tiles_count}}:{{total_size}}")
'''


def _build_coverage_script(tiles_dir: str) -> str:
    """Build standalone Python script for coverage polygon calculation on skystore.

    Uses the MAX zoom level tiles (z19) to compute a tight bounding box around
    actually photographed area. Past bug used MIN zoom (z13) where each tile is
    ~5km, producing a 13km² polygon for a 227m × 227m flight (the parent z13
    tile is huge). At z19 each tile is ~57m, so the bbox hugs the orthophoto
    accurately (~228m for a 1×1 z17 tile mission).
    """
    return f'''
import os, json, math
tiles_dir = "{tiles_dir}"
# Find MAX zoom level — gives the tightest bbox around actual content.
# (gdal2tiles writes the full pyramid; at low zooms, one parent tile covers
# many km even if the photo is only 200m wide.)
max_z = None
for z_str in os.listdir(tiles_dir):
    z_path = os.path.join(tiles_dir, z_str)
    if not os.path.isdir(z_path) or not z_str.isdigit():
        continue
    z = int(z_str)
    if max_z is None or z > max_z:
        max_z = z
if max_z is None:
    print("COVERAGE:{{}}")
else:
    def tile2ll(x, y, z):
        n = 2 ** z
        lon = x / n * 360.0 - 180.0
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        return (lon, lat)
    min_x, min_y, max_x, max_y = float("inf"), float("inf"), float("-inf"), float("-inf")
    z_path = os.path.join(tiles_dir, str(max_z))
    for x_str in os.listdir(z_path):
        x_path = os.path.join(z_path, x_str)
        if not os.path.isdir(x_path) or not x_str.isdigit(): continue
        x = int(x_str)
        for tf in os.listdir(x_path):
            if not tf.endswith(".webp"): continue
            y = int(tf.replace(".webp",""))
            if x < min_x: min_x = x
            if x > max_x: max_x = x
            if y < min_y: min_y = y
            if y > max_y: max_y = y
    sw = tile2ll(min_x, max_y + 1, max_z)
    ne = tile2ll(max_x + 1, min_y, max_z)
    poly = [sw, (ne[0], sw[1]), ne, (sw[0], ne[1]), sw]
    bounds = [sw[0], sw[1], ne[0], ne[1]]
    print("COVERAGE:" + json.dumps({{"polygon": poly, "bounds": bounds}}))
'''


def _build_update_latest_script(mission_dir: str, latest_dir: str, mission_id: str) -> str:
    """Build standalone Python script for updating latest layer on skystore.

    Policy: a mission's tile replaces the latest/ tile only if it has more
    content (larger file). Reason: gdal2tiles produces edge tiles for
    neighboring Z17 coords when the input ortho is clipped close to a tile
    boundary — those edges are effectively empty placeholders (~200 B) and
    would otherwise overwrite a neighbor's real full tile (~tens of KB) at
    the same coord. Past incident: 2026-04-08 C9/R2 missions wiped NVY's
    real tile 17/62485/48643 via this path. Size-wins is a safe "data
    preservation" heuristic — the empty placeholder is ~200 B while any
    meaningful aerial content is >1 KB.
    """
    return f'''
import os
mission_dir = "{mission_dir}"
latest_dir = "{latest_dir}"
os.makedirs(latest_dir, exist_ok=True)
count_written = 0
count_skipped = 0
for z_str in os.listdir(mission_dir):
    z_path = os.path.join(mission_dir, z_str)
    if not os.path.isdir(z_path) or not z_str.isdigit():
        continue
    for x_str in os.listdir(z_path):
        x_path = os.path.join(z_path, x_str)
        if not os.path.isdir(x_path) or not x_str.isdigit():
            continue
        out_dir = os.path.join(latest_dir, z_str, x_str)
        os.makedirs(out_dir, exist_ok=True)
        for tile_file in os.listdir(x_path):
            if not tile_file.endswith(".webp"):
                continue
            src = os.path.join(x_path, tile_file)
            dst = os.path.join(out_dir, tile_file)
            src_size = os.path.getsize(src)
            if os.path.exists(dst):
                dst_size = os.path.getsize(dst)
                if src_size <= dst_size:
                    count_skipped += 1
                    continue
                os.unlink(dst)
            try:
                os.link(src, dst)
            except OSError:
                import shutil
                shutil.copy2(src, dst)
            count_written += 1
print(f"Updated {{count_written}} tiles, skipped {{count_skipped}} smaller-than-existing")
'''


def _build_multi_neighbor_alignment_script(mission_id, r_target, r_orthos, max_shift_m=None):
    """Build multi-neighbor ORB MEASUREMENT script for skystore.

    Discovers all reference orthos with ≥MIN_OVERLAP_RATIO of target area,
    measures ORB shift vs each, emits EDGE lines. Does NOT apply any shift —
    the consensus computation (with median outlier filter + satellite anchor
    damping) runs in Python on Hetzner, and shift application is a separate
    step (`_build_apply_shift_script`).

    Emits stdout lines for Python parsing:
    - EDGE:<neighbor_id>:<dx_m>:<dy_m>:<overlap_m2>:<inlier_ratio>  — per-pair measurement
    - SKIP:<neighbor_id>:<reason>                                   — neighbor rejected

    Constraints (critical — past bug shifted orthos by 1+ km):
    - Per-neighbor overlap ≥ MIN_OVERLAP_RATIO of target area
    - Both windows loaded at COMMON pixel grid of intersection (same geographic resolution)
    - Per-edge shift capped at MAX_EDGE_SHIFT_M (10 m). Legitimate inter-mission
      shifts after satellite alignment are <7 m; anything beyond is a spurious
      ORB match. Tighter than before (was 30 m) — past incident with 13 m and
      18 m outliers poisoning consensus demonstrated 30 m was too permissive.
      Callers measuring a KNOWN-large offset (e.g. realigning a mis-anchored
      consolidation onto its members) pass an explicit `max_shift_m`.
    - Overlap ratio is taken vs the SMALLER of the two ortho areas: a 4-cell
      consolidation vs a single-cell neighbour overlaps <5% of the big side
      but ~20%+ of the small side — the old target-only ratio silently skipped
      ALL ring neighbours of a merged ortho (2026-06-12 mis-anchor incident).
    """
    MAX_EDGE_SHIFT_M = float(max_shift_m) if max_shift_m else 10.0
    MIN_OVERLAP_RATIO = 0.05
    MIN_WINDOW_PX = 64
    MAX_WINDOW_SIDE_PX = 2000
    return f'''
import os, sys, glob, re
import cv2
import numpy as np
import rasterio
from rasterio.windows import from_bounds

target = "{r_target}"
orthos_dir = "{r_orthos}"
mission_id = "{mission_id}"
MAX_EDGE_SHIFT_M = {MAX_EDGE_SHIFT_M}
MIN_OVERLAP_RATIO = {MIN_OVERLAP_RATIO}
MIN_WINDOW_PX = {MIN_WINDOW_PX}
MAX_WINDOW_SIDE_PX = {MAX_WINDOW_SIDE_PX}

ULID_RE = re.compile(r'(0[0-9A-HJKMNP-TV-Z]{{25}})', re.IGNORECASE)

def neighbor_id_from_path(p):
    m = ULID_RE.search(os.path.basename(p))
    return m.group(1).upper() if m else os.path.splitext(os.path.basename(p))[0]

with rasterio.open(target) as src:
    tgt_bounds = src.bounds
    tgt_area = (tgt_bounds.right - tgt_bounds.left) * (tgt_bounds.top - tgt_bounds.bottom)

refs = [r for r in glob.glob(os.path.join(orthos_dir, "*.tif")) if mission_id not in os.path.basename(r)]
if not refs:
    sys.exit(0)

def bbox_overlap(b1, b2):
    L = max(b1.left, b2.left); R = min(b1.right, b2.right)
    B = max(b1.bottom, b2.bottom); T = min(b1.top, b2.top)
    if L >= R or B >= T:
        return 0.0, None
    return (R - L) * (T - B), (L, B, R, T)

def load_isect(path, isect_L, isect_B, isect_R, isect_T, win_w, win_h):
    with rasterio.open(path) as src:
        win = from_bounds(isect_L, isect_B, isect_R, isect_T, src.transform)
        data = src.read(1, window=win, out_shape=(win_h, win_w),
                        resampling=rasterio.enums.Resampling.bilinear)
        if data.dtype != np.uint8:
            if data.max() > 0:
                data = (data / data.max() * 255).astype(np.uint8)
            else:
                data = data.astype(np.uint8)
    return data

for rp in refs:
    nid = neighbor_id_from_path(rp)
    try:
        with rasterio.open(rp) as rs:
            ref_bounds = rs.bounds
            overlap_area, isect = bbox_overlap(tgt_bounds, ref_bounds)
    except Exception as e:
        print(f"SKIP:{{nid}}:cannot_open:{{e}}")
        continue
    if overlap_area <= 0:
        continue
    ref_area = (ref_bounds.right - ref_bounds.left) * (ref_bounds.top - ref_bounds.bottom)
    overlap_ratio = overlap_area / max(min(tgt_area, ref_area), 1.0)
    if overlap_ratio < MIN_OVERLAP_RATIO:
        print(f"SKIP:{{nid}}:overlap_too_small_{{overlap_ratio*100:.2f}}pct")
        continue

    isect_L, isect_B, isect_R, isect_T = isect
    isect_w_m = isect_R - isect_L
    isect_h_m = isect_T - isect_B
    res_m_per_px = max(isect_w_m, isect_h_m) / MAX_WINDOW_SIDE_PX
    win_w = max(1, int(round(isect_w_m / res_m_per_px)))
    win_h = max(1, int(round(isect_h_m / res_m_per_px)))
    if win_w < MIN_WINDOW_PX or win_h < MIN_WINDOW_PX:
        print(f"SKIP:{{nid}}:window_too_small_{{win_w}}x{{win_h}}")
        continue

    try:
        tgt_gray = load_isect(target, isect_L, isect_B, isect_R, isect_T, win_w, win_h)
        ref_gray = load_isect(rp, isect_L, isect_B, isect_R, isect_T, win_w, win_h)
    except Exception as e:
        print(f"SKIP:{{nid}}:load_failed:{{e}}")
        continue

    orb = cv2.ORB_create(5000)
    kp_ref, des_ref = orb.detectAndCompute(ref_gray, None)
    kp_tgt, des_tgt = orb.detectAndCompute(tgt_gray, None)
    if des_ref is None or des_tgt is None or len(kp_ref) < 10 or len(kp_tgt) < 10:
        print(f"SKIP:{{nid}}:insufficient_features")
        continue

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = sorted(bf.match(des_ref, des_tgt), key=lambda m: m.distance)[:50]
    if len(matches) < 6:
        print(f"SKIP:{{nid}}:insufficient_matches_{{len(matches)}}")
        continue

    src_pts = np.float32([kp_ref[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_tgt[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    M, inliers = cv2.estimateAffinePartial2D(dst_pts, src_pts, method=cv2.RANSAC, ransacReprojThreshold=5.0)
    if M is None or inliers is None or int(np.sum(inliers)) < 4:
        print(f"SKIP:{{nid}}:ransac_failed")
        continue

    inlier_count = int(np.sum(inliers))
    inlier_ratio = inlier_count / float(len(matches))
    pixel_dx = float(M[0, 2])
    pixel_dy = float(M[1, 2])
    geo_dx = pixel_dx * res_m_per_px
    geo_dy = -pixel_dy * res_m_per_px
    shift_m = (geo_dx ** 2 + geo_dy ** 2) ** 0.5
    if shift_m > MAX_EDGE_SHIFT_M:
        print(f"SKIP:{{nid}}:shift_too_large_{{shift_m:.2f}}m")
        continue

    # Similarity components of M=[[a,-b,tx],[b,a,ty]] mapping target_a -> ref_b.
    # rel_scale = size(b)/size(a). rel_rot_deg uses +atan2(b,a): M's screen-frame
    # rotation IS the rotation-to-apply-to-a-to-align-onto-b, matching the
    # translation convention (geo_dx/dy are also corrections-to-apply-to-a, not
    # offsets — verified by synthetic test: dE=+2 -> geo_dx=-2, rot=+1 -> rel_rot=-1).
    a = float(M[0, 0]); bb = float(M[1, 0])
    rel_scale = (a * a + bb * bb) ** 0.5
    rel_rot_deg = np.degrees(np.arctan2(bb, a))
    # Hard-gate spurious similarity: legitimate inter-flight scale <2%, rot <few deg.
    if abs(rel_scale - 1.0) > 0.05 or abs(rel_rot_deg) > 5.0:
        print(f"SKIP:{{nid}}:similarity_out_of_range_s{{rel_scale:.4f}}_r{{rel_rot_deg:.2f}}")
        continue

    # isect_L/isect_T = (west, north) corner of the measured window = the world
    # point where the translation (M's pixel-(0,0) component) is referenced.
    # The Phase-2 lever-arm needs this exact point (stored as ref_x/y_3857).
    print(f"EDGE:{{nid}}:{{geo_dx:.4f}}:{{geo_dy:.4f}}:{{overlap_area:.1f}}:{{inlier_ratio:.4f}}:{{rel_scale:.6f}}:{{rel_rot_deg:.4f}}:{{isect_L:.2f}}:{{isect_T:.2f}}")
'''


def _build_apply_shift_script(r_src, r_dst, dx_m, dy_m):
    """Build script to apply a fixed (dx, dy) translation to a target ortho's
    georeference via rasterio Affine transform.
    """
    return f'''
import rasterio
from rasterio.transform import Affine
with rasterio.open("{r_src}") as src:
    new_tf = Affine(
        src.transform.a, src.transform.b, src.transform.c + {dx_m:.6f},
        src.transform.d, src.transform.e, src.transform.f + {dy_m:.6f},
    )
    profile = src.profile.copy()
    profile.update(transform=new_tf)
    with rasterio.open("{r_dst}", "w", **profile) as dst:
        for i in range(1, src.count + 1):
            dst.write(src.read(i), i)
print("APPLY_OK")
'''


def _build_satellite_alignment_script(r_reprojected, r_aligned, cache_dir):
    """Build standalone satellite alignment script for skystore.

    Downloads ESRI World Imagery tiles, runs ECC alignment, outputs transform.
    Writes aligned ortho to r_aligned if correction needed.
    """
    return f'''
import os, sys, math, json, subprocess, urllib.request
import cv2
import numpy as np

target = "{r_reprojected}"
output = "{r_aligned}"
cache_dir = "{cache_dir}"
TILE_ZOOM = {SATELLITE_TILE_ZOOM}
TILE_URL = "{SATELLITE_TILE_URL}"
ECC_MIN_CC = {SATELLITE_ECC_MIN_CC}
MAX_OFFSET_M = {ALIGNMENT_MAX_OFFSET_METERS}

# Get ortho bounds via gdalinfo
result = subprocess.run(["gdalinfo", "-json", target], capture_output=True, text=True, timeout=30)
if result.returncode != 0:
    sys.exit(0)
info = json.loads(result.stdout)
corners = info.get("cornerCoordinates", {{}})
ul = corners.get("upperLeft", [0, 0])
lr = corners.get("lowerRight", [0, 0])
min_x, min_y, max_x, max_y = ul[0], lr[1], lr[0], ul[1]
ortho_w_m = max_x - min_x
ortho_h_m = max_y - min_y

def epsg3857_to_ll(mx, my):
    lng = mx * 180.0 / 20037508.342789244
    lat = math.atan(math.exp(my * math.pi / 20037508.342789244)) * 360.0 / math.pi - 90.0
    return lat, lng

def ll_to_tile(lat, lng, z):
    n = 2 ** z
    x = int((lng + 180.0) / 360.0 * n)
    lr = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2.0 * n)
    return x, y

def tile_bounds_3857(tx, ty, z):
    n = 2 ** z
    ul_lng = tx / n * 360.0 - 180.0
    ul_lr = math.atan(math.sinh(math.pi * (1 - 2 * ty / n)))
    lr_lng = (tx + 1) / n * 360.0 - 180.0
    lr_lr = math.atan(math.sinh(math.pi * (1 - 2 * (ty + 1) / n)))
    def to3857(lng_d, lat_r):
        mx = lng_d * 20037508.342789244 / 180.0
        lat_d = math.degrees(lat_r)
        my = math.log(math.tan((90.0 + lat_d) * math.pi / 360.0)) / (math.pi / 180.0)
        my = my * 20037508.342789244 / 180.0
        return mx, my
    ul_mx, ul_my = to3857(ul_lng, ul_lr)
    lr_mx, lr_my = to3857(lr_lng, lr_lr)
    return (ul_mx, lr_my, lr_mx, ul_my)

# Download satellite tiles
sw_lat, sw_lng = epsg3857_to_ll(min_x, min_y)
ne_lat, ne_lng = epsg3857_to_ll(max_x, max_y)
min_tx, min_ty = ll_to_tile(ne_lat, sw_lng, TILE_ZOOM)
max_tx, max_ty = ll_to_tile(sw_lat, ne_lng, TILE_ZOOM)
cols = max_tx - min_tx + 1
rows = max_ty - min_ty + 1
if cols * rows > 500:
    sys.exit(0)

os.makedirs(cache_dir, exist_ok=True)
composite = np.zeros((rows * 256, cols * 256, 3), dtype=np.uint8)
for ty in range(min_ty, max_ty + 1):
    for tx in range(min_tx, max_tx + 1):
        cd = f"{{cache_dir}}/{{TILE_ZOOM}}/{{tx}}"
        cp = f"{{cd}}/{{ty}}.jpg"
        if not os.path.exists(cp):
            os.makedirs(cd, exist_ok=True)
            url = TILE_URL.format(z=TILE_ZOOM, y=ty, x=tx)
            try:
                req = urllib.request.Request(url, headers={{"User-Agent": "ParahubOpenSky/1.0"}})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    with open(cp, "wb") as f:
                        f.write(resp.read())
            except Exception:
                continue
        try:
            tile_img = cv2.imread(cp)
            if tile_img is not None:
                r, c = ty - min_ty, tx - min_tx
                composite[r*256:(r+1)*256, c*256:(c+1)*256] = tile_img
        except Exception:
            pass

sat_gray = cv2.cvtColor(composite, cv2.COLOR_BGR2GRAY)
nw_b = tile_bounds_3857(min_tx, min_ty, TILE_ZOOM)
se_b = tile_bounds_3857(max_tx, max_ty, TILE_ZOOM)
sat_bounds = (nw_b[0], se_b[1], se_b[2], nw_b[3])
sat_w_m = sat_bounds[2] - sat_bounds[0]
sat_h, sat_w = sat_gray.shape
mpp = sat_w_m / sat_w

out_w = int(ortho_w_m / mpp)
out_h = int(ortho_h_m / mpp)
if out_w < 100 or out_h < 100:
    sys.exit(0)

# Downsample ortho to satellite resolution
import tempfile
tmp = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
tmp_path = tmp.name
tmp.close()
try:
    cmd = ["gdal_translate", "-projwin", str(min_x), str(max_y), str(max_x), str(min_y),
           "-outsize", str(out_w), str(out_h), "-r", "average", "-of", "GTiff", target, tmp_path]
    subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    from PIL import Image
    img = Image.open(tmp_path)
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    ortho_gray = np.array(img.convert("L"))
finally:
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)

# Extract ortho region from satellite composite
ortho_x0 = max(0, int((min_x - sat_bounds[0]) / mpp))
ortho_y0 = max(0, int((sat_bounds[3] - max_y) / mpp))
ortho_x1 = min(sat_w, ortho_x0 + out_w)
ortho_y1 = min(sat_h, ortho_y0 + out_h)
sat_crop = sat_gray[ortho_y0:ortho_y1, ortho_x0:ortho_x1]
crop_h, crop_w = sat_crop.shape[:2]
if crop_h < 100 or crop_w < 100:
    sys.exit(0)

ortho_resized = cv2.resize(ortho_gray, (crop_w, crop_h), interpolation=cv2.INTER_AREA)

# Crop to center 1/3
ortho_mask = (ortho_resized > 10).astype(np.uint8)
ortho_mask = cv2.erode(ortho_mask, np.ones((25, 25), np.uint8))
cy, cx = crop_h // 2, crop_w // 2
cs = min(crop_h, crop_w) // 3
y1c, y2c = cy - cs, cy + cs
x1c, x2c = cx - cs, cx + cs
sat_center = sat_crop[y1c:y2c, x1c:x2c]
ortho_center = ortho_resized[y1c:y2c, x1c:x2c]
mask_center = ortho_mask[y1c:y2c, x1c:x2c]
if mask_center.mean() < 0.5:
    sys.exit(0)

ortho_m = ortho_center * mask_center
sat_m = sat_center * mask_center

# ECC alignment: half-scale then full
warp = np.eye(2, 3, dtype=np.float32)
criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-7)
sc = 0.5
sat_s = cv2.resize(sat_m, None, fx=sc, fy=sc)
ortho_s = cv2.resize(ortho_m, None, fx=sc, fy=sc)
try:
    cc, warp_h = cv2.findTransformECC(sat_s, ortho_s, warp, cv2.MOTION_TRANSLATION, criteria)
except cv2.error:
    sys.exit(0)
if cc < ECC_MIN_CC:
    sys.exit(0)

warp_full = np.eye(2, 3, dtype=np.float32)
warp_full[0, 2] = warp_h[0, 2] / sc
warp_full[1, 2] = warp_h[1, 2] / sc
try:
    cc_full, warp_full = cv2.findTransformECC(sat_m, ortho_m, warp_full, cv2.MOTION_TRANSLATION, criteria)
except cv2.error:
    cc_full = cc

dx_px = warp_full[0, 2]
dy_px = warp_full[1, 2]
dx_m = dx_px * mpp
dy_m = -dy_px * mpp
offset = (dx_m**2 + dy_m**2) ** 0.5

if offset > MAX_OFFSET_M or offset < 0.5:
    print(f"SAT_RESULT:0:0:{{cc_full:.4f}}:{{offset:.2f}}")
    sys.exit(0)

# Apply translation: shift the ortho transform
import rasterio
from rasterio.transform import Affine
with rasterio.open(target) as src:
    new_tf = Affine(src.transform.a, src.transform.b, src.transform.c + dx_m,
                    src.transform.d, src.transform.e, src.transform.f + dy_m)
    profile = src.profile.copy()
    profile.update(transform=new_tf)
    with rasterio.open(output, "w", **profile) as dst:
        for i in range(1, src.count + 1):
            dst.write(src.read(i), i)

print(f"SAT_RESULT:{{dx_m:.2f}}:{{dy_m:.2f}}:{{cc_full:.4f}}:{{offset:.2f}}")
'''


def _clear_self_owned_latest_tiles(mission_id: str, r_tiles_latest: str, r_tiles_mission: str,
                                   override_tiles_dir: str = None, min_override_size: int = 500) -> int:
    """Delete latest/ tiles owned by this mission (per OpenSkyTileLayer DB).

    Must be called BEFORE retile, while `r_tiles_mission` still exists — the
    ownership check below compares latest/ against the mission's own tiles.
    Prevents the size-wins policy in `_build_update_latest_script` from
    keeping stale latest/ links when the new ortho (post-shift) produces
    marginally smaller WebPs at the same coord — without this, latest/ gets
    stuck on pre-shift imagery while the mission dir already has the new
    shifted tiles, yielding a patchwork mosaic across neighboring missions
    at the tile level.

    A latest/ tile is deleted ONLY if it is actually this mission's tile:
    same inode (hard link) or byte-identical (copy2 fallback) with
    `missions/{id}/{z}/{x}/{y}.webp`. OpenSkyTileLayer rows alone are NOT
    proof of ownership — `_record_tile_layers` records every webp in the
    pyramid, including ~200 B edge placeholders at coords where latest/
    holds a NEIGHBOR's real tile. Past incident (2026-06-05): unconditional
    delete by DB rows let each retiled mission wipe its neighbors' real
    latest/ tiles, then `update_latest` planted the mission's empty edge
    placeholders into the freed slots (size-wins passes vs nothing) — 265
    real tiles z17-22 replaced by ~200 B placeholders across the cluster.

    Safe to call on missions without prior tiles: returns 0 if no DB rows.
    Returns number of tile coords targeted for the ownership check.
    """
    from geo.models import OpenSkyTileLayer
    owned = list(
        OpenSkyTileLayer.objects.filter(mission_id=mission_id)
        .values_list('z', 'x', 'y')
    )
    if not owned:
        return 0
    coords_str = '\n'.join(f"{z}/{x}/{y}" for z, x, y in owned)
    # Composite guard (consolidation case): when override_tiles_dir is set, only
    # clear this member's coord if the overriding mission (the consolidation) has
    # REAL content there. If the consolidation tile is an empty ~200B nodata
    # placeholder (or missing), KEEP the member tile so its coverage survives —
    # the consolidation ortho's hole is then filled by the member instead of
    # wiping it (2026-06-18 regression: joint ODM left nodata where a member had
    # full data; clearing the member + planting the empty placeholder lost
    # coverage; the alignment gate does NOT check completeness so it shipped).
    ov_setup = (
        f'override_dir = "{override_tiles_dir}"\nmin_override = {int(min_override_size)}'
        if override_tiles_dir else 'override_dir = None\nmin_override = 0'
    )
    script = f'''
import os, filecmp
latest_dir = "{r_tiles_latest}"
mission_dir = "{r_tiles_mission}"
{ov_setup}
coords = """{coords_str}""".strip().split("\\n")
deleted = 0
kept = 0
composite_filled = 0
for c in coords:
    latest_p = os.path.join(latest_dir, c + ".webp")
    mission_p = os.path.join(mission_dir, c + ".webp")
    try:
        if not os.path.exists(latest_p):
            continue
        if not os.path.exists(mission_p):
            # Cannot prove ownership (mission dir lost this coord, e.g.
            # crashed previous run) — keep; a foreign tile must survive.
            kept += 1
            continue
        if override_dir is not None:
            ov_p = os.path.join(override_dir, c + ".webp")
            if not os.path.exists(ov_p) or os.path.getsize(ov_p) <= min_override:
                # Overriding mission has no real tile here (nodata hole) — keep
                # the member tile so coverage is never lost (composite-fill).
                composite_filled += 1
                continue
        if os.path.samefile(latest_p, mission_p) or filecmp.cmp(latest_p, mission_p, shallow=False):
            os.unlink(latest_p)
            deleted += 1
        else:
            kept += 1
    except Exception:
        pass
print(f"CLEARED:{{deleted}}:KEPT:{{kept}}:COMPOSITE_FILLED:{{composite_filled}}")
'''
    composite_filled = 0
    try:
        result = _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=600)
        for line in (result.stdout or '').strip().splitlines():
            if line.startswith('CLEARED:'):
                logger.info(f"Pre-clear for {mission_id[:8]}: {line} (of {len(owned)} owned coords)")
                parts = line.split(':')
                if len(parts) >= 6 and parts[4] == 'COMPOSITE_FILLED':
                    composite_filled = int(parts[5])
    except Exception as e:
        logger.warning(f"Failed to clear self-owned latest tiles for {mission_id}: {e}")
    return composite_filled


def fill_consolidation_holes_from_members(consolidation_id: str, min_size: int = 500) -> int:
    """Restore member coverage in latest/ at z>=17 coords where a consolidation
    left an empty (nodata-hole) placeholder tile.

    Repairs consolidations published BEFORE the composite guard (2026-06-18): the
    old publish cleared each member's tiles then planted the consolidation's tiles,
    so wherever the joint ODM ortho had a nodata hole, latest/ got a ~200B
    transparent placeholder and the member's real coverage was lost. Re-plants the
    member's real tile into any latest/ slot that is currently empty/missing,
    WITHOUT touching real content (the consolidation weld is preserved). z<=16
    overviews already alpha-composite members under the consolidation, so only
    z>=17 (size-wins hard-link) needs this. Idempotent. Returns tiles restored.
    """
    from geo.models import OpenSkyMission
    con = OpenSkyMission.objects.filter(id=consolidation_id, is_consolidation=True).first()
    if not con:
        logger.error(f"fill_holes: {consolidation_id} is not a consolidation")
        return 0
    members = [link.member for link in con.members.select_related('member').order_by('order')]
    r_latest = f"{SKYSTORE_TILES}/latest"
    total = 0
    for m in members:
        r_mem = f"{SKYSTORE_TILES}/missions/{m.id}"
        script = f'''
import os, shutil
latest_dir = "{r_latest}"
mem_dir = "{r_mem}"
min_size = {int(min_size)}
restored = 0
if os.path.isdir(mem_dir):
    for z_str in os.listdir(mem_dir):
        if not z_str.isdigit() or int(z_str) < 17:
            continue
        zp = os.path.join(mem_dir, z_str)
        if not os.path.isdir(zp):
            continue
        for x_str in os.listdir(zp):
            xp = os.path.join(zp, x_str)
            if not os.path.isdir(xp):
                continue
            for tf in os.listdir(xp):
                if not tf.endswith(".webp"):
                    continue
                src = os.path.join(xp, tf)
                try:
                    if os.path.getsize(src) <= min_size:
                        continue  # member tile is also empty here
                except OSError:
                    continue
                dst_dir = os.path.join(latest_dir, z_str, x_str)
                dst = os.path.join(dst_dir, tf)
                if os.path.exists(dst) and os.path.getsize(dst) > min_size:
                    continue  # latest already has real content — never clobber the weld
                os.makedirs(dst_dir, exist_ok=True)
                if os.path.exists(dst):
                    os.unlink(dst)
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
                restored += 1
print(f"RESTORED:{{restored}}")
'''
        try:
            res = _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=600)
            for line in (res.stdout or '').strip().splitlines():
                if line.startswith("RESTORED:"):
                    n = int(line.split(":")[1])
                    total += n
                    if n:
                        logger.info(f"fill_holes {consolidation_id[:8]}: member {m.id[:8]} restored {n} tiles")
        except Exception as e:
            logger.warning(f"fill_holes: member {m.id[:8]} failed: {e}")
    logger.info(f"fill_holes {consolidation_id[:8]}: total {total} tiles restored from {len(members)} member(s)")
    return total


def _build_partial_composite_script(tiles: list, missions_dir: str, latest_dir: str,
                                    min_opaque: float) -> str:
    """Build a script that pixel-composites ONLY not-fully-opaque latest tiles.

    tiles: [{'z','x','y','contributors':[mid,...]}] ordered low→high layer_order.
    For each coord: if the current latest tile is already >= min_opaque opaque,
    leave it (keep the fast hard-link); else alpha-composite the contributors
    (members under, consolidation on top) into a standalone WebP so the
    consolidation's sub-tile nodata holes are filled per-pixel by the members.
    """
    import json as _json
    tiles_json = _json.dumps(tiles)
    return f'''
import os, json
from PIL import Image
tiles = json.loads({repr(tiles_json)})
missions_dir = "{missions_dir}"
latest_dir = "{latest_dir}"
min_opaque = {float(min_opaque)}
composited = 0
for t in tiles:
    z, x, y = t["z"], t["x"], t["y"]
    dst = os.path.join(latest_dir, str(z), str(x), f"{{y}}.webp")
    if os.path.exists(dst):
        try:
            ah = Image.open(dst).convert("RGBA").getchannel("A").histogram()
            tot = sum(ah)
            if tot and (sum(ah[11:]) / tot) >= min_opaque:
                continue  # already (near-)fully opaque — keep the hard link
        except Exception:
            pass
    result = None
    for mid in t["contributors"]:
        src = os.path.join(missions_dir, mid, str(z), str(x), f"{{y}}.webp")
        if not os.path.exists(src):
            continue
        try:
            im = Image.open(src).convert("RGBA")
        except Exception:
            continue
        result = im if result is None else Image.alpha_composite(result, im)
    if result is not None:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            os.remove(dst)  # break the hard link before a standalone save
        result.save(dst, "WEBP", quality=90)
        composited += 1
print(f"PARTIAL_COMPOSITE:{{composited}}")
'''


def composite_partial_consolidation_tiles(consolidation_id: str, min_opaque: float = 0.99) -> int:
    """Pixel-composite (consolidation over members) the consolidation's z>=17
    latest/ tiles that are NOT fully opaque.

    The tile-level composite (publish guard / fill_consolidation_holes_from_members)
    only restores FULLY-empty placeholder tiles. At middle zooms (z17/z18) a tile
    is LARGER than the hole, so the consolidation tile there has real data PLUS a
    transparent sub-tile hole — size-wins/fill leave it. This composites each such
    tile from its contributors (members under, consolidation on top), filling the
    sub-tile hole per-pixel with member content. Fully-opaque tiles keep their fast
    hard link (only the few partial tiles are rewritten). Idempotent. Returns count.
    """
    from geo.models import OpenSkyMission, OpenSkyTileLayer
    con = OpenSkyMission.objects.filter(id=consolidation_id, is_consolidation=True).first()
    if not con:
        logger.error(f"composite_partial: {consolidation_id} is not a consolidation")
        return 0
    coords = list(OpenSkyTileLayer.objects.filter(
        mission_id=consolidation_id, z__gte=17
    ).values_list('z', 'x', 'y'))
    tiles = []
    for z, x, y in coords:
        contributors = list(
            OpenSkyTileLayer.objects.filter(z=z, x=x, y=y)
            .order_by('layer_order')
            .values_list('mission_id', flat=True)
        )
        if len(contributors) < 2:
            continue  # only the consolidation here — nothing to fill from
        tiles.append({'z': z, 'x': x, 'y': y, 'contributors': contributors})
    if not tiles:
        return 0
    total = 0
    BATCH = 600
    for i in range(0, len(tiles), BATCH):
        batch = tiles[i:i + BATCH]
        script = _build_partial_composite_script(
            batch, f"{SKYSTORE_TILES}/missions", f"{SKYSTORE_TILES}/latest", min_opaque)
        try:
            res = _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=1800)
            for line in (res.stdout or '').strip().splitlines():
                if line.startswith("PARTIAL_COMPOSITE:"):
                    total += int(line.split(":")[1])
        except Exception as e:
            logger.warning(f"composite_partial {consolidation_id[:8]} batch failed: {e}")
    logger.info(
        f"composite_partial {consolidation_id[:8]}: {total} partial tile(s) pixel-composited "
        f"(of {len(tiles)} z>=17 multi-contributor coords)")
    return total


def _record_tile_layers(mission_id: str, r_tiles_mission: str):
    """Scan mission tiles on skystore and create OpenSkyTileLayer records in DB."""
    from geo.models import OpenSkyTileLayer

    result = _skystore_ssh(
        f"find {r_tiles_mission} -name '*.webp' -printf '%P\\n'",
        timeout=120,
    )
    if not result.stdout.strip():
        return

    max_order = OpenSkyTileLayer.objects.aggregate(
        max_order=models.Max('layer_order')
    )['max_order'] or 0
    new_layer_order = max_order + 1

    records = []
    for line in result.stdout.strip().splitlines():
        # Format: z/x/y.webp
        parts = line.strip().split('/')
        if len(parts) != 3 or not parts[2].endswith('.webp'):
            continue
        try:
            z, x = int(parts[0]), int(parts[1])
            y = int(parts[2].replace('.webp', ''))
            records.append(OpenSkyTileLayer(
                z=z, x=x, y=y,
                mission_id=mission_id,
                layer_order=new_layer_order,
            ))
        except (ValueError, IndexError):
            continue

    if records:
        OpenSkyTileLayer.objects.bulk_create(records, ignore_conflicts=True)
        logger.info(f"Recorded {len(records)} tile contributions for mission {mission_id[:8]}")


def _build_rebuild_tiles_script(tiles_to_rebuild: list, missions_dir: str, latest_dir: str) -> str:
    """Build standalone script for rebuilding latest/ tiles on skystore after deletion.

    tiles_to_rebuild: list of dicts {'z': int, 'x': int, 'y': int, 'remaining_missions': [str]}
    """
    import json as _json
    tiles_json = _json.dumps(tiles_to_rebuild)
    return f'''
import os, json
from PIL import Image

tiles = json.loads({repr(tiles_json)})
missions_dir = "{missions_dir}"
latest_dir = "{latest_dir}"
rebuilt = 0
deleted = 0

for t in tiles:
    z, x, y = t["z"], t["x"], t["y"]
    dst = os.path.join(latest_dir, str(z), str(x), f"{{y}}.webp")

    if not t["remaining_missions"]:
        if os.path.exists(dst):
            os.remove(dst)
            deleted += 1
        continue

    result_img = None
    for mid in t["remaining_missions"]:
        src = os.path.join(missions_dir, mid, str(z), str(x), f"{{y}}.webp")
        if not os.path.exists(src):
            continue
        tile_img = Image.open(src).convert("RGBA")
        if result_img is None:
            result_img = tile_img
        else:
            result_img = Image.alpha_composite(result_img, tile_img)

    if result_img:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        # Break any existing hard link first: latest/ tiles are hard-linked to
        # a mission's source tile (same inode), and saving in place would
        # truncate that source. Unlink → write a fresh standalone composite.
        if os.path.exists(dst):
            os.remove(dst)
        result_img.save(dst, "WEBP", quality=90)
        rebuilt += 1
    elif os.path.exists(dst):
        os.remove(dst)
        deleted += 1

print(f"REBUILD_RESULT:{{rebuilt}}:{{deleted}}")
'''


def rebuild_tiles_after_deletion(mission_id: str):
    """
    Rebuild affected tiles in latest/ on skystore after a mission is deleted.

    Queries DB for tile contributions, then runs rebuild script on skystore via SSH.
    """
    from geo.models import OpenSkyTileLayer

    # Find all tiles affected by this mission
    affected_tiles = list(OpenSkyTileLayer.objects.filter(
        mission_id=mission_id
    ).values_list('z', 'x', 'y', flat=False))

    if not affected_tiles:
        logger.info(f"No tiles to rebuild for mission {mission_id[:8]}")
        return

    logger.info(f"Rebuilding {len(affected_tiles)} tiles after deleting mission {mission_id[:8]}")

    # For each affected tile, find remaining missions (ordered by layer)
    tiles_to_rebuild = []
    for z, x, y in affected_tiles:
        remaining = list(
            OpenSkyTileLayer.objects.filter(z=z, x=x, y=y)
            .exclude(mission_id=mission_id)
            .order_by('layer_order')
            .values_list('mission_id', flat=True)
        )
        tiles_to_rebuild.append({
            'z': z, 'x': x, 'y': y,
            'remaining_missions': remaining,
        })

    # Run rebuild on skystore in batches: the script embeds every coord in ONE
    # ssh argument, and Linux caps a single argv string at MAX_ARG_STRLEN
    # (128KB) — ~17k coords blew it up during the 2026-06-09 spill recovery
    # (healed manually back then; batching is now the code path).
    REBUILD_BATCH = 600
    for i in range(0, len(tiles_to_rebuild), REBUILD_BATCH):
        batch = tiles_to_rebuild[i:i + REBUILD_BATCH]
        script = _build_rebuild_tiles_script(
            batch, f"{SKYSTORE_TILES}/missions", f"{SKYSTORE_TILES}/latest"
        )
        _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=1800)
        if len(tiles_to_rebuild) > REBUILD_BATCH:
            logger.info(f"Rebuilt {min(i + REBUILD_BATCH, len(tiles_to_rebuild))}/{len(tiles_to_rebuild)} tiles")

    # Clean up DB records
    OpenSkyTileLayer.objects.filter(mission_id=mission_id).delete()

    logger.info(f"Tile rebuild complete for mission {mission_id[:8]}")


def rebuild_overview_latest(mission_id: str, max_overview_zoom: int = None):
    """Recomposite latest/ overview tiles (z TILE_MIN_ZOOM..TILE_ZOOM_OVERVIEW_MAX).

    gdal2tiles builds a FULL per-mission pyramid clipped to the mission's Z17
    cell, so every overview tile holds that mission's content in only its own
    sub-region (one Z16 tile spans up to 4 Z17 missions; Z15 up to 16; Z14 up
    to 64). `_build_update_latest_script` uses a size-wins hard-link, which
    keeps just ONE mission's partial overview tile and drops the rest — so the
    zoomed-out map (z<=16) shows holes even though every Z17 tile is full.

    Here each overview coord this mission touches is rebuilt as the
    alpha-composite of ALL contributing missions (ordered by layer_order, so
    newest renders on top), i.e. the true union. Transparent placeholder
    regions stay transparent (genuinely unflown sub-cells show the basemap).
    Z17+ tiles are 1 mission = 1 tile and keep their fast size-wins hard link.
    """
    from geo.models import OpenSkyTileLayer

    if max_overview_zoom is None:
        max_overview_zoom = TILE_ZOOM_OVERVIEW_MAX

    overview_coords = list(
        OpenSkyTileLayer.objects.filter(
            mission_id=mission_id, z__lte=max_overview_zoom
        ).values_list('z', 'x', 'y')
    )
    if not overview_coords:
        return

    tiles_to_rebuild = []
    for z, x, y in overview_coords:
        contributors = list(
            OpenSkyTileLayer.objects.filter(z=z, x=x, y=y)
            .order_by('layer_order')
            .values_list('mission_id', flat=True)
        )
        tiles_to_rebuild.append({
            'z': z, 'x': x, 'y': y,
            'remaining_missions': contributors,
        })

    script = _build_rebuild_tiles_script(
        tiles_to_rebuild, f"{SKYSTORE_TILES}/missions", f"{SKYSTORE_TILES}/latest"
    )
    try:
        _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=1800)
        logger.info(
            f"Recomposited {len(tiles_to_rebuild)} overview tiles for mission {mission_id[:8]}"
        )
    except Exception as e:
        # Non-fatal: overview holes are a degradation, not a publish blocker.
        logger.warning(f"Overview recomposite failed for {mission_id[:8]}: {e}")


def delete_skystore_mission_files(mission_id: str):
    """Remove all mission data from skystore: images, ortho, tiles, mesh, 3d tiles."""
    dirs = [
        f"{SKYSTORE_OPENSKY}/missions/{mission_id}",
        f"{SKYSTORE_FAST_PROCESSING}/{mission_id}",
        f"{SKYSTORE_OPENSKY}/meshes/{mission_id}",
        f"{SKYSTORE_TILES}/missions/{mission_id}",
        f"{SKYSTORE_3DTILES}/missions/{mission_id}",
    ]
    ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission_id}.tif"
    rm_cmd = " ".join(f"rm -rf {d}" for d in dirs) + f" && rm -f {ortho}"
    try:
        _skystore_ssh(rm_cmd, timeout=120)
        logger.info(f"Deleted skystore files for mission {mission_id}")
        # Regenerate root 3D Tiles tileset (mission removed).
        # Pass exclude_id because the endpoint deletes the DB row AFTER this
        # cleanup runs — without it the regenerated root would still link
        # the about-to-be-deleted child.
        try:
            from geo.tiles3d_generator import regenerate_root_tileset
            regenerate_root_tileset(exclude_id=mission_id)
        except Exception:
            pass
        # If no missions remain, clean up latest/ tiles
        from geo.models import OpenSkyMission
        remaining = OpenSkyMission.objects.exclude(id=mission_id).filter(
            status=OpenSkyMission.Status.PUBLISHED
        ).count()
        if remaining == 0:
            try:
                _skystore_ssh(f"find {SKYSTORE_TILES}/latest/ -type f -delete && "
                              f"find {SKYSTORE_TILES}/latest/ -mindepth 1 -type d -empty -delete",
                              timeout=300)
                logger.info("Last mission deleted — cleaned up latest/ tiles on skystore")
            except Exception as e:
                logger.error(f"Failed to clean up latest/ tiles: {e}")
    except Exception as e:
        logger.error(f"Failed to delete skystore files for {mission_id}: {e}")


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


def _z17_tile_bounds_3857(z: int, x: int, y: int, buffer_m: float = 0) -> tuple[float, float, float, float]:
    """Web Mercator tile bounds in EPSG:3857 projected meters.

    Returns (xmin, ymin, xmax, ymax). Buffer expands the box outward in
    projected meters (not ground meters — at lat 42° they differ by cos(42°)
    factor, but for buffer=0 it doesn't matter).
    """
    n = 2 ** z
    tile_size = 40075016.686 / n  # Earth circumference / tiles per row
    half_circ = 20037508.342789244
    xmin = x * tile_size - half_circ
    xmax = (x + 1) * tile_size - half_circ
    # Y axis is flipped: y=0 is north pole, y increases south
    ymax = half_circ - y * tile_size
    ymin = half_circ - (y + 1) * tile_size
    return (xmin - buffer_m, ymin - buffer_m, xmax + buffer_m, ymax + buffer_m)


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


def check_satellite_alignment_skystore(mission_id: str) -> dict:
    """Run satellite alignment check on skystore, return offset info."""
    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission_id}.tif"
    r_tmp = f"{SKYSTORE_FAST_PROCESSING}/_sat_check_{mission_id}"
    r_aligned = f"{r_tmp}/aligned.tif"

    try:
        _skystore_ssh(f"mkdir -p {r_tmp}")
        script = _build_satellite_alignment_script(r_ortho, r_aligned, SATELLITE_CACHE_DIR)
        result = _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=300)

        for line in result.stdout.strip().splitlines():
            if line.startswith("SAT_RESULT:"):
                parts = line.split(":")
                dx, dy, cc, offset = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                return {
                    "offset": round(offset, 2),
                    "dx": round(dx, 2),
                    "dy": round(dy, 2),
                    "needs_correction": offset >= 0.5,
                }

        return {"offset": 0, "dx": 0, "dy": 0, "needs_correction": False}
    finally:
        try:
            _skystore_ssh(f"rm -rf {r_tmp}")
        except Exception:
            pass


def _is_superseded(mission_id: str) -> bool:
    """True if this mission must be skipped by the per-mission realign/retile
    paths (consensus, satellite, similarity, retile). Two cases:
    - a MEMBER of a consolidation: re-tiling it re-plants its tiles + grabs a
      fresh max layer_order, inverting above the super-tile (re-introduces seam);
    - a CONSOLIDATION itself: it has NULL tile_z/x/y, so the Z17-clip in
      _reclip_retile_publish is skipped → tiling the UNCLIPPED merged ortho
      spills across many neighbour cells (incident 2026-06-09). Consolidations
      are products, not flights — they are never consensus/similarity-realigned."""
    from geo.models import OpenSkyMission
    m = OpenSkyMission.objects.filter(id=mission_id).first()
    if m and m.is_consolidation:
        logger.info(f"{mission_id[:8]} is a consolidation — skipping per-mission realign/retile")
        return True
    if m and m.superseded_by_id:
        logger.info(
            f"{mission_id[:8]} is superseded by consolidation {m.superseded_by_id[:8]} "
            f"— skipping realign/retile (delete the consolidation to re-enable)")
        return True
    return False


def apply_satellite_alignment_skystore(mission_id: str):
    """Apply satellite alignment + retile on skystore for a published mission."""
    if _is_superseded(mission_id):
        return
    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission_id}.tif"
    r_tmp = f"{SKYSTORE_FAST_PROCESSING}/_sat_realign_{mission_id}"
    r_aligned = f"{r_tmp}/aligned.tif"
    r_tiles_mission = f"{SKYSTORE_TILES}/missions/{mission_id}"
    r_tiles_latest = f"{SKYSTORE_TILES}/latest"

    try:
        _skystore_ssh(f"mkdir -p {r_tmp}")

        # Step 1: Run satellite alignment
        script = _build_satellite_alignment_script(r_ortho, r_aligned, SATELLITE_CACHE_DIR)
        result = _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=300)

        sat_dx = sat_dy = sat_cc = 0.0
        for line in (result.stdout or '').strip().splitlines():
            if line.startswith('SAT_RESULT:'):
                try:
                    parts = line.split(':')
                    sat_dx = float(parts[1])
                    sat_dy = float(parts[2])
                    sat_cc = float(parts[3])
                except (ValueError, IndexError):
                    pass

        # Check if alignment was applied
        check = _skystore_ssh(f"test -f {r_aligned} && echo aligned || echo identity")
        if "aligned" not in check.stdout:
            logger.info(f"Satellite alignment: no correction needed for {mission_id}")
            return

        _write_satellite_anchor(mission_id, sat_dx, sat_dy, sat_cc)

        # Step 2: Replace ortho (unclipped — kept for future ORB alignment)
        _skystore_ssh(f"cp {r_aligned} {r_ortho}")
        _mark_georef_changed(mission_id)

        # Step 3: Clip to Z17 bounds before tiling (mirrors Step 3.7 of
        # process_mission).  Without this, the unclipped ortho's 37m flight
        # buffer spills tiles into neighbor Z17 cells, and size-wins picks
        # them over the neighbor's center tiles → broken mosaic.
        from geo.models import OpenSkyMission
        mission = OpenSkyMission.objects.get(id=mission_id)
        r_tile_src = r_ortho
        if mission.tile_z and mission.tile_x is not None and mission.tile_y is not None:
            r_clipped = f"{r_tmp}/orthophoto_clipped.tif"
            xmin, ymin, xmax, ymax = _z17_tile_bounds_3857(
                mission.tile_z, mission.tile_x, mission.tile_y, buffer_m=0
            )
            _skystore_ssh(
                f"gdalwarp -te {xmin} {ymin} {xmax} {ymax} -te_srs EPSG:3857 "
                f"-r lanczos -co COMPRESS=LZW -co TILED=YES -dstnodata 0 "
                f"-overwrite {r_ortho} {r_clipped}",
                timeout=600,
            )
            r_tile_src = r_clipped

        # Step 4: Retile
        r_tms = f"{r_tmp}/tiles_tms"
        _skystore_ssh(
            f"gdal2tiles.py -z {TILE_MIN_ZOOM}-{TILE_MAX_ZOOM} -w none -r lanczos"
            f" --processes=3 {r_tile_src} {r_tms}",
            timeout=28800,  # 8h
        )

        # Step 4: Convert TMS→XYZ WebP
        # Clear stale latest/ tiles owned by this mission BEFORE generating
        # new tiles — else size-wins policy keeps older tiles when new ones
        # are marginally smaller (common after satellite shift + Z17 reclip).
        _clear_self_owned_latest_tiles(mission_id, r_tiles_latest, r_tiles_mission)
        _skystore_ssh(f"rm -rf {r_tiles_mission}")
        _skystore_ssh(f"mkdir -p {r_tiles_mission}")
        convert_script = _build_tms_to_xyz_webp_script(r_tms, r_tiles_mission, WEBP_QUALITY)
        tile_result = _skystore_ssh(f"python3 -c {shlex.quote(convert_script)}", timeout=3600)

        tiles_count = 0
        tiles_size = 0
        for line in tile_result.stdout.strip().splitlines():
            if line.startswith("TILES_RESULT:"):
                parts = line.split(":")
                tiles_count = int(parts[1])
                tiles_size = int(parts[2])

        # Step 5: Update latest layer
        latest_script = _build_update_latest_script(r_tiles_mission, r_tiles_latest, mission_id)
        _skystore_ssh(f"python3 -c {shlex.quote(latest_script)}", timeout=600)

        # Step 6: Update tile layer records
        from geo.models import OpenSkyTileLayer
        OpenSkyTileLayer.objects.filter(mission_id=mission_id).delete()
        _record_tile_layers(mission_id, r_tiles_mission)
        # Overview tiles (z<=16) span multiple Z17 missions; size-wins above
        # keeps only one mission's partial tile, so recomposite from all
        # contributors here (the union) — otherwise zoomed-out map has holes.
        rebuild_overview_latest(mission_id)

        # Step 7: Coverage + DB update
        coverage_script = _build_coverage_script(r_tiles_mission)
        cov_result = _skystore_ssh(f"python3 -c {shlex.quote(coverage_script)}", timeout=300)
        coverage_polygon = None
        for line in cov_result.stdout.strip().splitlines():
            if line.startswith("COVERAGE:"):
                import json as _json
                data = _json.loads(line[9:])
                if data.get('polygon'):
                    coverage_polygon = Polygon(data['polygon'])

        mission.refresh_from_db()
        mission.tiles_count = tiles_count
        mission.tiles_size_mb = round(tiles_size / 1024 / 1024, 2)
        if coverage_polygon:
            mission.area = coverage_polygon
        mission.save(update_fields=['tiles_count', 'tiles_size_mb', 'area'])

        logger.info(f"Satellite alignment applied for {mission_id}: {tiles_count} tiles")

    finally:
        try:
            _skystore_ssh(f"rm -rf {r_tmp}")
        except Exception:
            pass


# Consensus parameters (tuned 2026-04-19 after oscillation incident).
# See PK/opensky-system.md § Pose Graph Architecture for rationale.
MIN_CONSENSUS_SHIFT_M = 0.5   # below this, don't retile (was 0.3 — too tight, caused iteration churn)
MAX_CONSENSUS_SHIFT_M = 10.0  # safety cap (should be < MAX_EDGE_SHIFT_M × 1.5)
OUTLIER_MEDIAN_MULTIPLE = 3.0  # reject edges with |shift| > 3× median of all measured edges
OUTLIER_FLOOR_M = 2.0          # but always accept edges below 2m regardless of median
SATELLITE_DAMPING_WEIGHT = 2e5  # virtual (0,0) edge weight — damps drift toward satellite-aligned position


def _parse_alignment_output(mission_id: str, stdout: str):
    """Parse multi-neighbor measurement script stdout.

    Returns list of edge dicts: {neighbor_id, dx_m, dy_m, overlap_m2, inlier_ratio}.
    SKIP lines are logged at debug level.
    """
    edges = []
    for line in (stdout or '').strip().splitlines():
        line = line.strip()
        if line.startswith('EDGE:'):
            parts = line.split(':')
            if len(parts) >= 6:
                try:
                    e = {
                        'neighbor_id': parts[1],
                        'dx_m': float(parts[2]),
                        'dy_m': float(parts[3]),
                        'overlap_m2': float(parts[4]),
                        'inlier_ratio': float(parts[5]),
                        # Legacy 6-field lines have no similarity → identity.
                        'rel_scale': float(parts[6]) if len(parts) >= 7 else 1.0,
                        'rel_rotation_deg': float(parts[7]) if len(parts) >= 8 else 0.0,
                        # Translation reference point (window west/north corner);
                        # None on legacy 8-field lines → solver falls back to
                        # the nominal cell-intersection corner.
                        'ref_x_3857': float(parts[8]) if len(parts) >= 10 else None,
                        'ref_y_3857': float(parts[9]) if len(parts) >= 10 else None,
                    }
                    edges.append(e)
                except ValueError:
                    logger.warning(f"Consensus {mission_id}: bad EDGE line: {line}")
        elif line.startswith('SKIP:'):
            logger.debug(f"Consensus {mission_id}: {line}")
    return edges


def compute_consensus_shift(mission_id: str, edges: list):
    """Robust weighted consensus from ORB edges + satellite anchor damping.

    1. Outlier filter: reject edges where |shift| > max(3×median, 2m floor).
    2. Weighted average: weight = overlap_m2 × inlier_ratio.
    3. Satellite anchor: virtual (0,0) edge with SATELLITE_DAMPING_WEIGHT.
       Damps oscillation + prevents unbounded group drift from absolute frame.
       (Satellite alignment already baked into ortho position — (0,0) means
       'stay at satellite-corrected position'.)

    Returns dict {avg_dx, avg_dy, n_used, n_filtered_outliers, shift_m, total_weight}.
    """
    import statistics

    if not edges:
        return {
            'avg_dx': 0.0, 'avg_dy': 0.0,
            'n_used': 0, 'n_filtered_outliers': 0,
            'shift_m': 0.0, 'total_weight': 0.0,
        }

    mags = [(e['dx_m']**2 + e['dy_m']**2) ** 0.5 for e in edges]
    med = statistics.median(mags)
    threshold = max(OUTLIER_MEDIAN_MULTIPLE * med, OUTLIER_FLOOR_M)

    kept = []
    n_outliers = 0
    for e, mag in zip(edges, mags):
        if mag > threshold:
            n_outliers += 1
            logger.info(
                f"Consensus {mission_id}: FILTER outlier {e['neighbor_id'][-5:]} "
                f"|shift|={mag:.2f}m > threshold={threshold:.2f}m (median={med:.2f}m)"
            )
        else:
            kept.append(e)

    if not kept:
        return {
            'avg_dx': 0.0, 'avg_dy': 0.0,
            'n_used': 0, 'n_filtered_outliers': n_outliers,
            'shift_m': 0.0, 'total_weight': 0.0,
        }

    total_w = SATELLITE_DAMPING_WEIGHT
    sum_dx = 0.0
    sum_dy = 0.0
    for e in kept:
        w = e['overlap_m2'] * e['inlier_ratio']
        total_w += w
        sum_dx += w * e['dx_m']
        sum_dy += w * e['dy_m']

    avg_dx = sum_dx / total_w
    avg_dy = sum_dy / total_w
    shift_m = (avg_dx ** 2 + avg_dy ** 2) ** 0.5

    return {
        'avg_dx': avg_dx, 'avg_dy': avg_dy,
        'n_used': len(kept), 'n_filtered_outliers': n_outliers,
        'shift_m': shift_m, 'total_weight': total_w,
    }


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


def solve_similarity_ba(centroids: dict, bounds: dict, orb_edges: list, anchored_ids: set,
                        anchor_weight: float = None) -> dict:
    """Global 2D similarity bundle adjustment over a mission cluster.

    Each mission i gets a correction: scale e^{u_i}, rotation ω_i, centroid
    translation (tx_i,ty_i), applied about its EPSG:3857 centroid c_i.

    Solved in two stages (DELIBERATELY two-stage, not joint — see below):
      Stage 1: two independent weighted-Laplacian scalar solves for u_i (ln s)
               and ω_i (rad) from the DIRECT relative measurements only
               (u_i−u_j=ln s_ij; ω_i−ω_j=θ_ij) + a weak identity prior (gauge).
      Stage 2: translation T_i from (T_i−T_j) = r_ij − lever_i + lever_j, where
               lever_i = u_i·d_i + ω_i·(J·d_i), d_i = x_ref − c_i, x_ref = the
               point where r_ij was measured (M's pixel-(0,0) = window
               west/north corner). Satellite anchors pin T_i→0 ("stay here").

    WHY NOT a joint 4N solve: in a joint system the anchored translations
    observe the cluster's common scale/rotation through the lever terms (the
    anchor baseline). Satellite anchoring is 1-2m-noisy while its solver weight
    (2e5, Phase-1 damping semantics) vastly overstates its precision — so a
    joint solve FABRICATES common-mode scale from anchor noise: ~1.5m of
    inter-anchor residual on a ~300m baseline reads as ~0.5% cluster-wide
    shrink. Observed live 2026-06-11: direct scale measurements said identity
    (median +106ppm) while the joint solution proposed −5000ppm common-mode and
    1-4m moves on a visually settled cluster. Two-stage keeps u/ω sourced from
    the precise direct similarity measurements only; the cost is a small gauge
    tension (~mean(u)·baseline, ≈10cm at production magnitudes) when ≥2 anchors
    exist, since stage 1's identity prior picks the gauge instead of the
    anchors. Guarded by tests_opensky_similarity (anchor-noise robustness).

    Args:
      centroids: {mid: (cx, cy)} EPSG:3857 ortho centroids.
      bounds:    {mid: (left, bottom, right, top)} EPSG:3857.
      orb_edges: [{a, b, ln_s, theta_rad, dx, dy, w, xref?}] — a,b are mids;
                 corrections to apply to a to align onto b (same convention as
                 dx_m/dy_m). Optional xref=(x,y) is the exact point where the
                 translation was measured (window west/north corner, stored as
                 ref_x/y_3857); without it the nominal bbox-intersection corner
                 is used (adds ~0.2-0.5m lever error when extents differ).
      anchored_ids: mids that have a SATELLITE_ANCHOR (translation pinned).
    Returns {mid: {'ln_scale','rotation_deg','tx','ty','translation_only'(bool)}}.

    The solution is a DELTA from the missions' CURRENT on-disk georefs: edges
    must be measured against the current orthos (see edge freshness in
    realign_opensky_similarity), and anchors mean "don't move from here".
    """
    import numpy as np
    import statistics
    from scipy.sparse import csr_matrix
    from scipy.sparse.linalg import lsmr

    if anchor_weight is None:
        anchor_weight = SATELLITE_DAMPING_WEIGHT

    mids = sorted(centroids.keys())
    idx = {m: k for k, m in enumerate(mids)}
    N = len(mids)
    if N == 0:
        return {}

    # Only edges between missions we're solving.
    edges = [e for e in orb_edges if e['a'] in idx and e['b'] in idx]

    # Per-component robust outlier filter (median-multiple with a floor).
    # KNOWN LIMITATION: a mission genuinely sitting several metres off its
    # neighbours produces edges that LOOK like outliers and get rejected here,
    # leaving its (worst-in-cluster) seam unfixed. Reciprocal mirroring
    # (|r_ab+r_ba| ≈ 0 for real misalignment, metres for junk) distinguishes
    # them, but a trust-bypass must exempt ONLY the translation component —
    # prototyped 2026-06-11, it let the low-confidence SCALE noise of trusted
    # edges (±1%) through to stage 1 and overshot sparsely-connected missions
    # (11m move from one low-conf pair). Needs per-component trust before
    # enabling; see PK § Phase 2.
    def thr(vals, floor):
        if not vals:
            return float('inf')
        m = statistics.median([abs(v) for v in vals])
        return max(OUTLIER_MEDIAN_MULTIPLE * m, floor)
    th_s = thr([e['ln_s'] for e in edges], SIM_SCALE_OUTLIER_FLOOR)
    th_r = thr([e['theta_rad'] for e in edges], np.radians(SIM_ROT_OUTLIER_FLOOR_DEG))
    th_t = thr([(e['dx']**2 + e['dy']**2) ** 0.5 for e in edges], OUTLIER_FLOOR_M)
    edges = [e for e in edges
             if abs(e['ln_s']) <= th_s and abs(e['theta_rad']) <= th_r
             and (e['dx']**2 + e['dy']**2) ** 0.5 <= th_t]

    has_anchor = bool(anchored_ids & set(mids))
    lsmr_opts = dict(atol=1e-12, btol=1e-12, conlim=1e10, maxiter=max(1000, 50 * N))

    def solve_scalar(rel_key):
        """Weighted Laplacian: x_i - x_j = rel + weak identity prior → x≈0 gauge."""
        rows, cols, dat, rhs = [], [], [], []
        r = 0
        for e in edges:
            w = e['w'] ** 0.5
            rows += [r, r]; cols += [idx[e['a']], idx[e['b']]]; dat += [w, -w]
            rhs.append(w * e[rel_key]); r += 1
        for k in range(N):
            rows.append(r); cols.append(k); dat.append(SIM_GAUGE_PRIOR); rhs.append(0.0); r += 1
        A = csr_matrix((dat, (rows, cols)), shape=(r, N))
        return lsmr(A, np.array(rhs), **lsmr_opts)[0]

    # Stage 1: scale & rotation from direct relative measurements only (never
    # from translations/anchors — see docstring). If no usable edges, identity.
    if edges:
        u = solve_scalar('ln_s')
        om = solve_scalar('theta_rad')
    else:
        u = np.zeros(N); om = np.zeros(N)

    # Stage 2: translation with stage-1 lever arms folded into the rhs.
    rows, cols, dat, rhs = [], [], [], []
    r = 0
    for e in edges:
        i, j = idx[e['a']], idx[e['b']]
        w = e['w'] ** 0.5
        if e.get('xref'):
            xref = e['xref']   # exact measured window corner (ref_x/y_3857)
        else:
            bi, bj = bounds[e['a']], bounds[e['b']]
            xref = (max(bi[0], bj[0]), min(bi[3], bj[3]))   # nominal fallback = M pixel(0,0)
        ci, cj = centroids[e['a']], centroids[e['b']]
        dix, diy = xref[0] - ci[0], xref[1] - ci[1]
        djx, djy = xref[0] - cj[0], xref[1] - cj[1]
        # lever = u·d + ω·(J·d), J·d = (-dy, dx)
        lev_i = (u[i] * dix + om[i] * (-diy), u[i] * diy + om[i] * (dix))
        lev_j = (u[j] * djx + om[j] * (-djy), u[j] * djy + om[j] * (djx))
        for c, dval in enumerate((e['dx'], e['dy'])):
            rows += [r, r]; cols += [2*i + c, 2*j + c]; dat += [w, -w]
            rhs.append(w * (dval - (lev_i[c] - lev_j[c]))); r += 1
    aw = anchor_weight ** 0.5
    for m in (anchored_ids & set(mids)):
        i = idx[m]
        rows.append(r); cols.append(2*i); dat.append(aw); rhs.append(0.0); r += 1
        rows.append(r); cols.append(2*i + 1); dat.append(aw); rhs.append(0.0); r += 1
    for k in range(2 * N):   # tiny prior pins unanchored components numerically
        rows.append(r); cols.append(k); dat.append(SIM_TRANS_PRIOR); rhs.append(0.0); r += 1
    A = csr_matrix((dat, (rows, cols)), shape=(r, 2 * N))
    t = lsmr(A, np.array(rhs), **lsmr_opts)[0]

    return {
        m: {
            'ln_scale': float(u[idx[m]]),
            'rotation_deg': float(np.degrees(om[idx[m]])),
            'tx': float(t[2*idx[m]]),
            'ty': float(t[2*idx[m] + 1]),
            'translation_only': not has_anchor,
        }
        for m in mids
    }


def _write_orb_edges(mission_id: str, edges: list):
    """Upsert ORB_PAIR pose edges into DB."""
    from geo.models import OpenSkyMission, OpenSkyPoseEdge
    if not edges:
        return
    neighbor_ids = {e['neighbor_id'] for e in edges}
    existing_neighbors = set(
        OpenSkyMission.objects.filter(id__in=neighbor_ids).values_list('id', flat=True)
    )
    for e in edges:
        if e['neighbor_id'] not in existing_neighbors:
            logger.warning(f"Consensus {mission_id}: neighbor {e['neighbor_id']} not in DB, skipping edge")
            continue
        OpenSkyPoseEdge.objects.update_or_create(
            mission_a_id=mission_id,
            mission_b_id=e['neighbor_id'],
            edge_type=OpenSkyPoseEdge.EdgeType.ORB_PAIR,
            defaults={
                'dx_m': e['dx_m'],
                'dy_m': e['dy_m'],
                'weight': e['overlap_m2'] * e['inlier_ratio'],
                'confidence': e['inlier_ratio'],
                'overlap_area_m2': e['overlap_m2'],
                'rel_scale': e.get('rel_scale', 1.0),
                'rel_rotation_deg': e.get('rel_rotation_deg', 0.0),
                'ref_x_3857': e.get('ref_x_3857'),
                'ref_y_3857': e.get('ref_y_3857'),
            },
        )


def _write_satellite_anchor(mission_id: str, dx_m: float, dy_m: float, cc: float):
    """Upsert SATELLITE_ANCHOR pose edge into DB.

    Satellite anchor represents the absolute-frame shift observed by ECC
    against ESRI World Imagery. mission_b is NULL (absolute reference).
    """
    from geo.models import OpenSkyPoseEdge
    OpenSkyPoseEdge.objects.update_or_create(
        mission_a_id=mission_id,
        mission_b=None,
        edge_type=OpenSkyPoseEdge.EdgeType.SATELLITE_ANCHOR,
        defaults={
            'dx_m': dx_m,
            'dy_m': dy_m,
            'weight': 1.0,
            'confidence': cc,
            'overlap_area_m2': 0.0,
            # Anchors observe translation only — similarity is identity.
            'rel_scale': 1.0,
            'rel_rotation_deg': 0.0,
        },
    )


def _reclip_retile_publish(mission_id: str, r_ortho: str, r_tmp: str) -> int:
    """Shared tail after an in-place georef correction of the saved ortho.

    Clip r_ortho to the mission's Z17 cell, retile z11-22, plant into latest/
    (self-clear then size-wins), record tile layers, recomposite overviews,
    update coverage + DB. Used by both the consensus (translation) and the
    similarity (scale+rotation+translation) apply paths. Returns tiles_count.
    """
    from geo.models import OpenSkyMission, OpenSkyTileLayer
    r_tiles_mission = f"{SKYSTORE_TILES}/missions/{mission_id}"
    r_tiles_latest = f"{SKYSTORE_TILES}/latest"
    mission = OpenSkyMission.objects.get(id=mission_id)

    # Clip before tiling (saved ortho is intentionally unclipped; a rotated
    # geotransform from the similarity warp is de-rotated by this same warp).
    # Plain missions clip to their Z17 cell; consolidations (NULL tile coords)
    # clip to the member-cells union rectangle — tiling UNCLIPPED is what
    # caused the 2026-06-09 spill, so a consolidation without resolvable
    # bounds is an error, never a fall-through.
    r_src = r_ortho
    clip_bounds = None
    if mission.tile_z and mission.tile_x is not None and mission.tile_y is not None:
        clip_bounds = _z17_tile_bounds_3857(
            mission.tile_z, mission.tile_x, mission.tile_y, buffer_m=0
        )
    elif mission.is_consolidation:
        members = [link.member for link in mission.members.select_related('member')]
        clip_bounds = _consolidation_union_bounds_3857(members)
        if not clip_bounds:
            raise RuntimeError(
                f"Consolidation {mission_id} has no member tile bounds — refusing unclipped retile")
    if clip_bounds:
        xmin, ymin, xmax, ymax = clip_bounds
        r_clipped = f"{r_tmp}/orthophoto_clipped.tif"
        _skystore_ssh(
            f"gdalwarp -te {xmin} {ymin} {xmax} {ymax} -te_srs EPSG:3857 "
            f"-r lanczos -co COMPRESS=LZW -co TILED=YES -dstnodata 0 "
            f"-overwrite {r_ortho} {r_clipped}",
            timeout=600,
        )
        r_src = r_clipped

    r_tms = f"{r_tmp}/tiles_tms"
    _skystore_ssh(
        f"gdal2tiles.py -z {TILE_MIN_ZOOM}-{TILE_MAX_ZOOM} -w none -r lanczos"
        f" --processes=3 {r_src} {r_tms}",
        timeout=28800,
    )

    _clear_self_owned_latest_tiles(mission_id, r_tiles_latest, r_tiles_mission)
    _skystore_ssh(f"rm -rf {r_tiles_mission}")
    _skystore_ssh(f"mkdir -p {r_tiles_mission}")
    convert_script = _build_tms_to_xyz_webp_script(r_tms, r_tiles_mission, WEBP_QUALITY)
    tile_result = _skystore_ssh(f"python3 -c {shlex.quote(convert_script)}", timeout=3600)
    tiles_count = tiles_size = 0
    for line in tile_result.stdout.strip().splitlines():
        if line.startswith("TILES_RESULT:"):
            parts = line.split(":")
            tiles_count, tiles_size = int(parts[1]), int(parts[2])

    latest_script = _build_update_latest_script(r_tiles_mission, r_tiles_latest, mission_id)
    _skystore_ssh(f"python3 -c {shlex.quote(latest_script)}", timeout=600)

    OpenSkyTileLayer.objects.filter(mission_id=mission_id).delete()
    _record_tile_layers(mission_id, r_tiles_mission)
    rebuild_overview_latest(mission_id)

    coverage_script = _build_coverage_script(r_tiles_mission)
    cov_result = _skystore_ssh(f"python3 -c {shlex.quote(coverage_script)}", timeout=300)
    coverage_polygon = None
    for line in cov_result.stdout.strip().splitlines():
        if line.startswith("COVERAGE:"):
            import json as _json
            data = _json.loads(line[9:])
            if data.get('polygon'):
                coverage_polygon = Polygon(data['polygon'])
    mission.tiles_count = tiles_count
    mission.tiles_size_mb = round(tiles_size / 1024 / 1024, 2)
    if coverage_polygon:
        mission.area = coverage_polygon
    mission.save(update_fields=['tiles_count', 'tiles_size_mb', 'area'])
    return tiles_count


def measure_orb_edges_skystore(mission_id: str) -> list:
    """Measure ORB pose edges vs all overlapping neighbors and persist to DB.

    MEASURE-ONLY: no consensus math, no warp, no retile — safe on any published
    mission incl. right before a Phase-2 solve (this is how edges are refreshed
    after physical georef changes; see `measure_opensky_edges` command).
    Returns the parsed edge list.
    """
    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission_id}.tif"
    r_orthos = f"{SKYSTORE_OPENSKY}/orthos"
    measurement_script = _build_multi_neighbor_alignment_script(
        mission_id, r_ortho, r_orthos,
    )
    result = _skystore_ssh(f"python3 -c {shlex.quote(measurement_script)}", timeout=3600)
    edges = _parse_alignment_output(mission_id, result.stdout or '')
    _write_orb_edges(mission_id, edges)
    return edges


def apply_consensus_alignment_skystore(mission_id: str):
    """Phase 1 pose-graph consensus re-alignment for a published mission.

    See PK/opensky-system.md § Pose Graph Architecture. Flow:
    1. Measurement: runs multi-neighbor ORB script — emits EDGE lines only.
    2. Persist edges to DB (OpenSkyPoseEdge.ORB_PAIR).
    3. Consensus: apply 3×median outlier filter + satellite-anchor damping to
       compute weighted-average shift.
    4. If |shift| ≥ MIN_CONSENSUS_SHIFT_M: apply shift to saved ortho, retile.

    Returns True if the shift was applied, False otherwise.
    """
    if _is_superseded(mission_id):
        return False
    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission_id}.tif"
    r_tmp = f"{SKYSTORE_FAST_PROCESSING}/_consensus_{mission_id}"
    r_aligned = f"{r_tmp}/aligned.tif"

    try:
        _skystore_ssh(f"mkdir -p {r_tmp}")

        # Steps 1-2: Measure ORB shifts vs all overlapping neighbors + persist
        edges = measure_orb_edges_skystore(mission_id)

        # Step 3: Robust consensus (median outlier filter + satellite damping)
        cs = compute_consensus_shift(mission_id, edges)
        logger.info(
            f"Consensus {mission_id}: edges_measured={len(edges)} used={cs['n_used']} "
            f"outliers_filtered={cs['n_filtered_outliers']} "
            f"shift=({cs['avg_dx']:+.2f},{cs['avg_dy']:+.2f})m |s|={cs['shift_m']:.2f}m"
        )

        if cs['shift_m'] < MIN_CONSENSUS_SHIFT_M:
            logger.info(f"Consensus {mission_id}: stable (shift below {MIN_CONSENSUS_SHIFT_M}m threshold)")
            return False

        if cs['shift_m'] > MAX_CONSENSUS_SHIFT_M:
            logger.warning(
                f"Consensus {mission_id}: shift {cs['shift_m']:.2f}m exceeds "
                f"MAX_CONSENSUS_SHIFT_M={MAX_CONSENSUS_SHIFT_M} — NOT applying (safety cap)"
            )
            return False

        # Step 4: Apply shift to saved (unclipped) ortho, then reclip+retile+publish
        apply_script = _build_apply_shift_script(r_ortho, r_aligned, cs['avg_dx'], cs['avg_dy'])
        _skystore_ssh(f"python3 -c {shlex.quote(apply_script)}", timeout=300)
        _skystore_ssh(f"cp {r_aligned} {r_ortho}")
        # Physical georef change — edges measured before this (including the
        # ones written above in Step 2) no longer describe the on-disk frame.
        _mark_georef_changed(mission_id)

        tiles_count = _reclip_retile_publish(mission_id, r_ortho, r_tmp)
        logger.info(f"Consensus {mission_id}: applied + retiled, {tiles_count} tiles")
        return True

    finally:
        try:
            _skystore_ssh(f"rm -rf {r_tmp}")
        except Exception:
            pass


# Phase-2 similarity apply thresholds (on the solved delta).
SIM_APPLY_TRANS_M = 0.5       # apply if translation delta > 0.5 m
SIM_APPLY_SCALE = 0.002       # or |ln scale| delta > 0.2%
SIM_APPLY_ROT_DEG = 0.1       # or rotation delta > 0.1°


def _mark_georef_changed(mission_id: str):
    """Record that the saved ortho's georeference just changed physically.

    Every pose edge measured BEFORE this moment describes a frame that no
    longer exists on disk — the Phase-2 solver filters them out via
    `_edge_is_fresh`. Call after EVERY physical georef mutation of
    /skystore/opensky/orthos/{id}.tif (publish, satellite/consensus shift,
    similarity warp).
    """
    from geo.models import OpenSkyMission
    OpenSkyMission.objects.filter(id=mission_id).update(georef_changed_at=timezone.now())


def _edge_is_fresh(measured_at, *georef_changed_ats) -> bool:
    """True if the edge was measured AFTER the last physical georef change of
    BOTH endpoint orthos (None = ortho never changed since field introduction)."""
    latest = max((g for g in georef_changed_ats if g is not None), default=None)
    return latest is None or measured_at > latest


def _compose_similarity_about_centroid(old: tuple, delta: tuple) -> tuple:
    """Compose two similarity corrections taken about the SAME centroid:
    apply `old` first, then `delta`. Each is (ln_scale, rotation_deg, tx, ty).

    C(p) = s0·R0·(p−c) + c + t0;  D(C(p)) = s0·sd·Rd·R0·(p−c) + c + (sd·Rd·t0 + td)
    → scale/rotation add in log/angle space, old translation is carried through
    delta's scale+rotation. Used only for the cumulative corr_* bookkeeping.
    """
    ln_s = old[0] + delta[0]
    rot = old[1] + delta[1]
    s_d = math.exp(delta[0])
    th = math.radians(delta[1])
    cos_t, sin_t = math.cos(th), math.sin(th)
    tx = s_d * (cos_t * old[2] - sin_t * old[3]) + delta[2]
    ty = s_d * (sin_t * old[2] + cos_t * old[3]) + delta[3]
    return (ln_s, rot, tx, ty)


def _build_similarity_warp_script(r_src, r_dst, cx, cy, ln_scale, rot_deg, tx, ty):
    """Compose a 2D similarity (scale e^lnS, rotation rot_deg, translation t),
    taken about the EPSG:3857 centroid (cx,cy), into the ortho's geotransform.

    p' = sR(p − c) + c + t = sR·p + (c + t − sR·c). Edits only the geotransform
    (lossless — no pixel resampling); the rotated grid is de-rotated later by the
    Z17 reclip gdalwarp. rasterio `W * src.transform` composes pixel→map then map→map.
    """
    return f'''
import math, rasterio
from rasterio.transform import Affine
s = math.exp({ln_scale}); th = math.radians({rot_deg})
cosT = s * math.cos(th); sinT = s * math.sin(th)
cx, cy, tx, ty = {cx}, {cy}, {tx}, {ty}
ox = tx + cx - (cosT * cx - sinT * cy)
oy = ty + cy - (sinT * cx + cosT * cy)
W = Affine(cosT, -sinT, ox, sinT, cosT, oy)
with rasterio.open("{r_src}") as src:
    profile = src.profile.copy()
    profile.update(transform=(W * src.transform), BIGTIFF="IF_SAFER")
    with rasterio.open("{r_dst}", "w", **profile) as dst:
        for i in range(1, src.count + 1):
            dst.write(src.read(i), i)
print("WARP_OK")
'''


def apply_similarity_correction_skystore(mission_id: str, cx: float, cy: float,
                                         d_lns: float, d_rot: float,
                                         d_tx: float, d_ty: float) -> bool:
    """Apply a Phase-2 similarity DELTA (about centroid cx,cy in EPSG:3857) to
    a mission's saved ortho, then reclip+retile+publish.

    The arguments are the solver's output = the correction to the mission's
    CURRENT on-disk georef (the solve consumed only edges measured against it —
    see edge freshness in realign_opensky_similarity). corr_* accumulates the
    composition for bookkeeping; nothing re-derives state from it. Returns True
    if applied (above threshold).
    """
    if _is_superseded(mission_id):
        return False
    from geo.models import OpenSkyMission
    m = OpenSkyMission.objects.get(id=mission_id)

    if ((d_tx**2 + d_ty**2) ** 0.5 < SIM_APPLY_TRANS_M
            and abs(d_lns) < SIM_APPLY_SCALE and abs(d_rot) < SIM_APPLY_ROT_DEG):
        return False  # below apply threshold — leave tiles untouched

    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission_id}.tif"
    r_tmp = f"{SKYSTORE_FAST_PROCESSING}/_sim_{mission_id}"
    r_warped = f"{r_tmp}/sim_warped.tif"
    try:
        _skystore_ssh(f"mkdir -p {r_tmp}")
        warp_script = _build_similarity_warp_script(
            r_ortho, r_warped, cx, cy, d_lns, d_rot, d_tx, d_ty)
        _skystore_ssh(f"python3 -c {shlex.quote(warp_script)}", timeout=600)
        _skystore_ssh(f"cp {r_warped} {r_ortho}")
        # The on-disk frame just changed — every existing edge touching this
        # mission is stale from this point on.
        _mark_georef_changed(mission_id)

        tiles_count = _reclip_retile_publish(mission_id, r_ortho, r_tmp)

        (m.corr_ln_scale, m.corr_rotation_deg, m.corr_dx_m, m.corr_dy_m) = (
            _compose_similarity_about_centroid(
                (m.corr_ln_scale, m.corr_rotation_deg, m.corr_dx_m, m.corr_dy_m),
                (d_lns, d_rot, d_tx, d_ty)))
        m.save(update_fields=['corr_ln_scale', 'corr_rotation_deg', 'corr_dx_m', 'corr_dy_m'])
        logger.info(
            f"Similarity {mission_id[:8]}: applied Δ(lnS={d_lns:+.4f}, rot={d_rot:+.3f}°, "
            f"t={(d_tx**2 + d_ty**2) ** 0.5:.2f}m), {tiles_count} tiles"
        )
        return True
    finally:
        try:
            _skystore_ssh(f"rm -rf {r_tmp}")
        except Exception:
            pass


def retile_mission_skystore(mission_id: str, zoom_range: str = None, clean: bool = False):
    """Retile a published mission on skystore from its saved ortho.

    clean=True wipes the mission tiles dir before retiling (full rebuild).
    The wipe happens AFTER the latest/ pre-clear below — the ownership check
    in `_clear_self_owned_latest_tiles` needs the old mission tiles on disk;
    deleting the dir first (as `retile_opensky --full` used to) makes every
    owned coord unprovable, leaving orphaned latest/ links behind.
    """
    from geo.models import OpenSkyMission

    if _is_superseded(mission_id):
        return (0, 0)

    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission_id}.tif"
    r_tmp = f"{SKYSTORE_FAST_PROCESSING}/_retile_{mission_id}"
    r_tiles_mission = f"{SKYSTORE_TILES}/missions/{mission_id}"
    r_tiles_latest = f"{SKYSTORE_TILES}/latest"

    if not zoom_range:
        zoom_range = f"{TILE_MIN_ZOOM}-{TILE_MAX_ZOOM}"

    try:
        _skystore_ssh(f"mkdir -p {r_tmp}")

        # Mirror Step 3.7 of process_mission: clip the saved (unclipped) ortho
        # to the planned Z17 tile bounds before tiling. The /skystore/opensky/
        # orthos/ copy is intentionally unclipped (kept for cross-mission ORB
        # alignment via the 37m flight overlap), but tiling MUST run on the
        # clipped version to keep tiles confined to one Z17 cell — otherwise
        # retile would generate boundary tiles at neighbor Z17 coords and
        # break newest-wins stitching.
        mission = OpenSkyMission.objects.get(id=mission_id)
        if mission.tile_z and mission.tile_x is not None and mission.tile_y is not None:
            r_clipped = f"{r_tmp}/orthophoto_clipped.tif"
            xmin, ymin, xmax, ymax = _z17_tile_bounds_3857(
                mission.tile_z, mission.tile_x, mission.tile_y, buffer_m=0
            )
            logger.info(
                f"Retile clip: Z{mission.tile_z}/{mission.tile_x}/{mission.tile_y} "
                f"({xmin:.1f},{ymin:.1f},{xmax:.1f},{ymax:.1f} EPSG:3857)"
            )
            _skystore_ssh(
                f"gdalwarp -te {xmin} {ymin} {xmax} {ymax} -te_srs EPSG:3857 "
                f"-r lanczos -co COMPRESS=LZW -co TILED=YES -dstnodata 0 "
                f"-overwrite {r_ortho} {r_clipped}",
                timeout=600,
            )
            r_tile_source = r_clipped
        else:
            logger.warning(f"Mission {mission_id} has no tile_z/x/y — tiling unclipped ortho")
            r_tile_source = r_ortho

        # Generate TMS tiles
        r_tms = f"{r_tmp}/tiles_tms"
        _skystore_ssh(
            f"gdal2tiles.py -z {zoom_range} -w none -r lanczos"
            f" --processes=3 {r_tile_source} {r_tms}",
            timeout=28800,  # 8h
        )

        # Convert TMS→XYZ WebP
        # Clear stale latest/ tiles owned by this mission BEFORE generating
        # new tiles — else size-wins policy keeps older tiles when new ones
        # are marginally smaller (common after retile with different clip).
        _clear_self_owned_latest_tiles(mission_id, r_tiles_latest, r_tiles_mission)
        if clean:
            _skystore_ssh(f"rm -rf {r_tiles_mission}")
        _skystore_ssh(f"mkdir -p {r_tiles_mission}")
        convert_script = _build_tms_to_xyz_webp_script(r_tms, r_tiles_mission, WEBP_QUALITY)
        _skystore_ssh(f"python3 -c {shlex.quote(convert_script)}", timeout=3600)

        # Count the FULL mission pyramid, not just the zooms converted above —
        # partial retile (e.g. adding z11-12 after a TILE_MIN_ZOOM bump) would
        # otherwise persist tiles_count=2 to the DB and break mission cards.
        result = _skystore_ssh(
            f"find {r_tiles_mission} -name '*.webp' -printf '%s\\n' "
            f"| awk '{{c++; s+=$1}} END {{print \"TILES_RESULT:\" c \":\" s}}'",
            timeout=300,
        )
        tiles_count = 0
        tiles_size = 0
        for line in result.stdout.strip().splitlines():
            if line.startswith("TILES_RESULT:"):
                parts = line.split(":")
                tiles_count = int(parts[1])
                tiles_size = int(parts[2])

        # Update latest layer
        latest_script = _build_update_latest_script(r_tiles_mission, r_tiles_latest, mission_id)
        _skystore_ssh(f"python3 -c {shlex.quote(latest_script)}", timeout=600)

        # Update tile records
        from geo.models import OpenSkyTileLayer
        OpenSkyTileLayer.objects.filter(mission_id=mission_id).delete()
        _record_tile_layers(mission_id, r_tiles_mission)
        # Overview tiles (z<=16) span multiple Z17 missions; size-wins above
        # keeps only one mission's partial tile, so recomposite from all
        # contributors here (the union) — otherwise zoomed-out map has holes.
        rebuild_overview_latest(mission_id)

        return tiles_count, tiles_size

    finally:
        try:
            _skystore_ssh(f"rm -rf {r_tmp}")
        except Exception:
            pass


def process_mission(mission_id: str, dry_run: bool = False) -> bool:
    """
    Full pipeline for processing an OpenSky mission.

    Args:
        mission_id: ULID of the mission to process
        dry_run: If True, only log what would be done

    Returns:
        True on success, False on failure
    """
    from geo.models import OpenSkyMission

    logger.info(f"Starting processing for mission {mission_id}")

    try:
        mission = OpenSkyMission.objects.get(id=mission_id)
    except OpenSkyMission.DoesNotExist:
        logger.error(f"Mission {mission_id} not found")
        return False

    if mission.status != OpenSkyMission.Status.QUEUED:
        logger.warning(f"Mission {mission_id} is not in QUEUED status (current: {mission.status})")
        return False

    # Update status to PROCESSING (clear previous error if retrying)
    mission.status = OpenSkyMission.Status.PROCESSING
    mission.processing_started_at = timezone.now()
    mission.processing_step = OpenSkyMission.ProcessingStep.ODM
    mission.error_message = ''

    # Set area + center NOW from the planned Z17 tile bounds (clean rectangle).
    # tile_z/x/y are known at upload time, so we don't need to wait for any
    # processing output. Setting area early is critical because
    # generate_3d_tiles_for_mission() → regenerate_root_tileset() filters by
    # `area__isnull=False`; if we set area only at Step 6, the root tileset
    # gets generated WITHOUT this mission and is then deleted. Legacy missions
    # without tile_z/x/y still fall back to coverage_polygon at Step 6.
    if mission.tile_z and mission.tile_x is not None and mission.tile_y is not None:
        from pyproj import Transformer
        xmin_3857, ymin_3857, xmax_3857, ymax_3857 = _z17_tile_bounds_3857(
            mission.tile_z, mission.tile_x, mission.tile_y, buffer_m=0
        )
        t = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
        sw_lng, sw_lat = t.transform(xmin_3857, ymin_3857)
        ne_lng, ne_lat = t.transform(xmax_3857, ymax_3857)
        mission.area = Polygon((
            (sw_lng, sw_lat),
            (ne_lng, sw_lat),
            (ne_lng, ne_lat),
            (sw_lng, ne_lat),
            (sw_lng, sw_lat),
        ))
        mission.center_lat = (sw_lat + ne_lat) / 2
        mission.center_lng = (sw_lng + ne_lng) / 2

    mission.save(update_fields=[
        'status', 'processing_started_at', 'processing_step', 'error_message',
        'area', 'center_lat', 'center_lng',
    ])
    _publish_mission_update(mission.id, {
        'status': 'PROCESSING',
        'processing_step': 'odm',
        'processing_started_at': mission.processing_started_at.isoformat(),
    })

    # Processing temp on SSD, permanent storage on HDD (ZFS)
    local_images = f"{OPENSKY_BASE}/missions/{mission_id}/images"
    r_images = f"{SKYSTORE_OPENSKY}/missions/{mission_id}/images"
    r_processing = f"{SKYSTORE_FAST_PROCESSING}/{mission_id}"
    r_orthos = f"{SKYSTORE_OPENSKY}/orthos"
    r_tiles_mission = f"{SKYSTORE_TILES}/missions/{mission_id}"
    r_tiles_latest = f"{SKYSTORE_TILES}/latest"

    try:
        if dry_run:
            logger.info(f"[DRY RUN] Would process mission {mission_id}")
            return True

        # Check if images already on skystore (e.g. retry after previous partial failure)
        remote_count_result = _skystore_ssh(f"ls {r_images}/*.JPG {r_images}/*.jpg 2>/dev/null | wc -l")
        remote_image_count = int(remote_count_result.stdout.strip())

        if os.path.exists(local_images):
            image_count = len([f for f in os.listdir(local_images) if f.lower().endswith(('.jpg', '.jpeg'))])
            if image_count == 0 and remote_image_count == 0:
                raise ValueError("No JPG images found in images directory")
            logger.info(f"Found {image_count} images locally")
            # Step 1: Upload photos to skystore, delete local
            logger.info("Step 1: Uploading photos to skystore...")
            upload_to_skystore(mission_id)
        elif remote_image_count > 0:
            logger.info(f"Step 1: Skipped — {remote_image_count} images already on skystore")
        else:
            raise FileNotFoundError(f"Images not found locally ({local_images}) or on skystore ({r_images})")

        # Step 2: Run ODM on skystore (GPU)
        logger.info("Step 2: Running ODM on skystore (GPU)...")
        remote_ortho = run_odm_skystore(mission_id)
        logger.info(f"ODM completed on skystore: {remote_ortho}")

        # Step 3: Reproject to Web Mercator (on skystore via SSH)
        mission.processing_step = OpenSkyMission.ProcessingStep.REPROJECTION
        mission.save(update_fields=['processing_step'])
        _publish_mission_update(mission.id, {'status': 'PROCESSING', 'processing_step': 'reprojection'})
        logger.info("Step 3: Reprojecting on skystore...")
        r_reprojected = f"{r_processing}/orthophoto_3857.tif"
        # Skip if already done (from previous partial run)
        check = _skystore_ssh(f"test -f {r_reprojected} && echo exists || echo missing")
        if "exists" in check.stdout:
            logger.info(f"Reprojected orthophoto already exists, skipping: {r_reprojected}")
        else:
            _skystore_ssh(
                f"gdalwarp -t_srs EPSG:3857 -r lanczos -co COMPRESS=LZW -co TILED=YES"
                f" {remote_ortho} {r_reprojected}",
                timeout=1800,
            )
        r_final_ortho = r_reprojected

        # Step 3.4: Satellite alignment (always — absolute reference).
        # Every mission is aligned to ESRI World Imagery so all tiles share
        # one global reference frame.  Eliminates chain-dependency on the
        # first-ever mission's raw GPS and prevents inter-mission seams.
        mission.processing_step = OpenSkyMission.ProcessingStep.ALIGNMENT
        mission.save(update_fields=['processing_step'])
        _publish_mission_update(mission.id, {'status': 'PROCESSING', 'processing_step': 'alignment'})

        r_sat_aligned = f"{r_processing}/orthophoto_sat_aligned.tif"
        logger.info("Step 3.4: Satellite alignment (absolute reference)...")
        sat_script = _build_satellite_alignment_script(r_reprojected, r_sat_aligned, SATELLITE_CACHE_DIR)
        sat_result = _skystore_ssh(f"python3 -c {shlex.quote(sat_script)}", timeout=1800)
        sat_dx = sat_dy = sat_cc = sat_offset = 0.0
        for line in (sat_result.stdout or '').strip().splitlines():
            if line.startswith('SAT_RESULT:'):
                logger.info(f"Step 3.4: {line}")
                try:
                    parts = line.split(':')
                    sat_dx = float(parts[1])
                    sat_dy = float(parts[2])
                    sat_cc = float(parts[3])
                    sat_offset = float(parts[4])
                except (ValueError, IndexError):
                    pass
        sat_check = _skystore_ssh(f"test -f {r_sat_aligned} && echo aligned || echo identity")
        if "aligned" in sat_check.stdout:
            r_after_sat = r_sat_aligned
            mission.satellite_align = True
            mission.save(update_fields=['satellite_align'])
            _write_satellite_anchor(mission_id, sat_dx, sat_dy, sat_cc)
            logger.info("Satellite-aligned (absolute reference)")
        else:
            r_after_sat = r_reprojected
            logger.info("Satellite alignment skipped (low correlation or negligible offset)")

        # Step 3.5: Multi-neighbor consensus alignment (refinement).
        # See PK/opensky-system.md § Pose Graph Architecture. Measures ORB
        # shift vs EVERY overlapping published neighbor, writes ORB_PAIR pose
        # edges to DB, applies weighted-average shift to this mission only.
        ref_check = _skystore_ssh(f"ls {r_orthos}/*.tif 2>/dev/null | wc -l")
        has_references = int(ref_check.stdout.strip()) > 0

        if has_references:
            logger.info("Step 3.5: Multi-neighbor consensus alignment...")
            r_aligned = f"{r_processing}/orthophoto_aligned.tif"
            measurement_script = _build_multi_neighbor_alignment_script(
                mission_id, r_after_sat, r_orthos,
            )
            result = _skystore_ssh(f"python3 -c {shlex.quote(measurement_script)}", timeout=3600)
            edges = _parse_alignment_output(mission_id, result.stdout or '')
            _write_orb_edges(mission_id, edges)
            cs = compute_consensus_shift(mission_id, edges)
            logger.info(
                f"Step 3.5: edges_measured={len(edges)} used={cs['n_used']} "
                f"outliers_filtered={cs['n_filtered_outliers']} "
                f"shift=({cs['avg_dx']:+.2f},{cs['avg_dy']:+.2f})m |s|={cs['shift_m']:.2f}m"
            )
            if MIN_CONSENSUS_SHIFT_M <= cs['shift_m'] <= MAX_CONSENSUS_SHIFT_M:
                apply_script = _build_apply_shift_script(
                    r_after_sat, r_aligned, cs['avg_dx'], cs['avg_dy'],
                )
                _skystore_ssh(f"python3 -c {shlex.quote(apply_script)}", timeout=300)
                r_final_ortho = r_aligned
                logger.info("Consensus-refined against neighbors")
            else:
                r_final_ortho = r_after_sat
                if cs['shift_m'] > MAX_CONSENSUS_SHIFT_M:
                    logger.warning(
                        f"Step 3.5: shift {cs['shift_m']:.2f}m exceeds MAX_CONSENSUS_SHIFT_M — "
                        f"not applying (safety cap)"
                    )
        else:
            r_final_ortho = r_after_sat

        # Step 3.6: Save FULL (unclipped) orthophoto for future neighbor
        # alignment. Cross-mission alignment uses ORB feature matching across
        # the 37m flight buffer overlap — needs the unclipped ortho to find
        # features in the overlap region. Clipping happens AFTER this save.
        _skystore_ssh(f"mkdir -p {r_orthos} && cp {r_final_ortho} {r_orthos}/{mission_id}.tif")

        # Step 3.7: Clip orthophoto to mission's planned Z17 tile bounds
        # (no buffer). With current newest-wins tile composition (no blending),
        # buffer=0 is mathematically optimal: each mission writes EXACTLY its
        # own tiles, no overlap, no overhead, no quality degradation when a
        # neighbor's oblique-edge pixels would otherwise overwrite this
        # mission's nadir tiles. ODM source overlap (BUFFER_M=37 in
        # mission_generator) is preserved at the flight planning level for
        # ODM stitching, but is NOT carried into the final tile output.
        if mission.tile_z and mission.tile_x is not None and mission.tile_y is not None:
            r_clipped = f"{r_processing}/orthophoto_clipped.tif"
            # Skip if already done (from previous partial run) — same pattern as Step 3.
            check = _skystore_ssh(f"test -f {r_clipped} && echo exists || echo missing")
            if "exists" in check.stdout:
                logger.info(f"Clipped orthophoto already exists, skipping: {r_clipped}")
            else:
                xmin, ymin, xmax, ymax = _z17_tile_bounds_3857(
                    mission.tile_z, mission.tile_x, mission.tile_y, buffer_m=0
                )
                logger.info(
                    f"Step 3.7: Clipping ortho to Z{mission.tile_z}/{mission.tile_x}/{mission.tile_y} "
                    f"({xmin:.1f},{ymin:.1f},{xmax:.1f},{ymax:.1f} EPSG:3857)..."
                )
                _skystore_ssh(
                    f"gdalwarp -te {xmin} {ymin} {xmax} {ymax} -te_srs EPSG:3857 "
                    f"-r lanczos -co COMPRESS=LZW -co TILED=YES -dstnodata 0 "
                    f"-overwrite {r_final_ortho} {r_clipped}",
                    timeout=600,
                )
            r_final_ortho = r_clipped
        else:
            logger.warning(f"Mission {mission_id} has no tile_z/x/y — skipping clip")

        # Step 4: Generate tiles on skystore
        mission.processing_step = OpenSkyMission.ProcessingStep.TILING
        mission.save(update_fields=['processing_step'])
        _publish_mission_update(mission.id, {'status': 'PROCESSING', 'processing_step': 'tiling'})
        logger.info("Step 4: Generating tiles on skystore...")
        r_tms = f"{r_processing}/tiles_tms"
        # Timeout 8h: gdal2tiles z11-z22 on a Z17-clipped ortho takes ~3 min
        # for ~600-photo missions. Headroom kept for edge cases (large missions,
        # disk contention, retry).
        _skystore_ssh(
            f"gdal2tiles.py -z {TILE_MIN_ZOOM}-{TILE_MAX_ZOOM} -w none -r lanczos"
            f" --processes=3 {r_final_ortho} {r_tms}",
            timeout=28800,
        )

        # Step 4.1: Convert TMS→XYZ WebP on skystore
        logger.info("Step 4.1: Converting to XYZ WebP on skystore...")
        # Reprocess of a PUBLISHED mission (append-photos flow): the new
        # pyramid may be shifted by Step 3.4/3.5, leaving latest/ links to
        # the old tiles at coords the new pyramid no longer covers, or
        # marginally-smaller new tiles losing to old ones via size-wins.
        # Clear this mission's own latest/ tiles before overwriting its dir
        # (ownership-guarded — neighbors' tiles survive). No-op for fresh
        # missions (no OpenSkyTileLayer rows yet).
        _clear_self_owned_latest_tiles(mission_id, r_tiles_latest, r_tiles_mission)
        _skystore_ssh(f"mkdir -p {r_tiles_mission}")
        convert_script = _build_tms_to_xyz_webp_script(r_tms, r_tiles_mission, WEBP_QUALITY)
        result = _skystore_ssh(f"python3 -c {shlex.quote(convert_script)}", timeout=3600)
        # Parse tiles_count and tiles_size from script output
        for line in result.stdout.strip().splitlines():
            if line.startswith("TILES_RESULT:"):
                parts = line.split(":")
                tiles_count = int(parts[1])
                tiles_size = int(parts[2])
                break
        else:
            tiles_count = 0
            tiles_size = 0
        logger.info(f"Generated {tiles_count} tiles ({tiles_size / 1024 / 1024:.2f} MB)")

        # Sanity check: reject empty-placeholder pyramids. A legitimate aerial
        # mission produces WebP tiles averaging tens of KB (NVY baseline: ~27KB
        # at Z17). A ~200 B placeholder pyramid (1500 tiles × 202 B = 0.29 MB)
        # means the clipped ortho has zero real pixels — usually because Step
        # 3.5 alignment moved the ortho outside the target tile bounds (past
        # incident: 01KNQ3C9NA5CJ7VKQP6PAEBMFY, 01KNQ3R21JZYNQEJRDYM0KSNRB
        # on 2026-04-08). Fail loud here instead of publishing an empty tile.
        if tiles_count > 0:
            avg_tile_bytes = tiles_size / tiles_count
            if avg_tile_bytes < 1024:
                raise RuntimeError(
                    f"Empty tile pyramid: {tiles_count} tiles averaging "
                    f"{avg_tile_bytes:.0f} B (< 1 KB). Clipped ortho contains "
                    f"no real pixels — check Step 3.5 alignment logs."
                )

        # Step 5: Calculate coverage polygon (on skystore)
        logger.info("Step 5: Calculating coverage polygon on skystore...")
        coverage_script = _build_coverage_script(r_tiles_mission)
        result = _skystore_ssh(f"python3 -c {shlex.quote(coverage_script)}", timeout=300)
        coverage_polygon = None
        bounds = None
        for line in result.stdout.strip().splitlines():
            if line.startswith("COVERAGE:"):
                import json as _json
                data = _json.loads(line[9:])
                if data.get('polygon'):
                    coverage_polygon = Polygon(data['polygon'])
                if data.get('bounds'):
                    bounds = data['bounds']

        # Step 5.1: Update latest layer on skystore
        mission.processing_step = OpenSkyMission.ProcessingStep.FINALIZING
        mission.save(update_fields=['processing_step'])
        _publish_mission_update(mission.id, {'status': 'PROCESSING', 'processing_step': 'finalizing'})
        logger.info("Step 5.1: Updating latest layer on skystore...")
        latest_script = _build_update_latest_script(r_tiles_mission, r_tiles_latest, mission_id)
        result = _skystore_ssh(f"python3 -c {shlex.quote(latest_script)}", timeout=600)
        # Surface update_latest result (written vs skipped) for debugging
        for line in (result.stdout or '').strip().splitlines():
            if line.startswith('Updated '):
                logger.info(f"Step 5.1: {line}")

        # Step 5.2: Record tile contributions in DB for deletion support
        logger.info("Step 5.2: Recording tile contributions...")
        _record_tile_layers(mission_id, r_tiles_mission)
        # Overview tiles (z<=16) span multiple Z17 missions; size-wins above
        # keeps only one mission's partial tile, so recomposite from all
        # contributors here (the union) — otherwise zoomed-out map has holes.
        rebuild_overview_latest(mission_id)

        # Step 5.5: 3D Mesh generation (merged pipeline — ODM already produced mesh)
        mission.processing_step = OpenSkyMission.ProcessingStep.MESH
        mission.save(update_fields=['processing_step'])
        _publish_mission_update(mission.id, {'status': 'PROCESSING', 'processing_step': 'mesh'})
        mesh_ok = False
        try:
            # Verify ODM produced mesh output
            remote_texturing = f"{r_processing}/odm_texturing"
            check = _skystore_ssh(f"test -f {remote_texturing}/odm_textured_model_geo.obj && echo ok || echo no")
            if "ok" in check.stdout:
                logger.info("Step 5.5: Processing 3D mesh artifacts...")

                # Extract ODM origin for georeferencing (before cleanup!)
                odm_origin = _extract_odm_origin(r_processing)
                if odm_origin:
                    mission.odm_origin = odm_origin
                    mission.save(update_fields=['odm_origin'])

                # Download, convert OBJ→GLB, optimize, upload to skystore
                glb_size_mb, local_mesh = _process_mesh_artifacts(mission_id, r_processing)

                # Compute mesh ground level (p5 of vertex z) and shift origin
                # so the mesh's ground sits at WGS84 ellipsoid altitude 0,
                # matching the flat OSM base layer. Otherwise the mesh appears
                # to "float in the sky" because vertex z values encode altitude
                # relative to ODM's local frame anchor (not ellipsoid).
                if odm_origin:
                    ground_z = _compute_mesh_ground_z(mission_id)
                    if ground_z is not None:
                        odm_origin['z'] = -ground_z
                        mission.odm_origin = odm_origin
                        mission.save(update_fields=['odm_origin'])
                        logger.info(f"Shifted origin by ground_z={ground_z:.2f} (mesh p5)")

                # Persist coords.txt + proj.txt + odm_georeferencing_model_geo.txt
                # into meshes/ so future tileset regeneration can recompute the
                # ECEF transform without re-running ODM. MUST run AFTER
                # _process_mesh_artifacts because that function does
                # `rsync --delete` to meshes/ and would otherwise wipe these files.
                remote_meshes = f"{SKYSTORE_OPENSKY}/meshes/{mission_id}"
                try:
                    _skystore_ssh(
                        f"mkdir -p {remote_meshes} && "
                        f"cp -f {r_processing}/odm_georeferencing/coords.txt {remote_meshes}/coords.txt 2>/dev/null; "
                        f"cp -f {r_processing}/odm_georeferencing/proj.txt {remote_meshes}/proj.txt 2>/dev/null; "
                        f"cp -f {r_processing}/odm_georeferencing/odm_georeferencing_model_geo.txt {remote_meshes}/odm_georeferencing_model_geo.txt 2>/dev/null; "
                        f"true"
                    )
                except Exception as e:
                    logger.warning(f"Could not persist coords/proj.txt: {e}")

                mission.mesh_status = OpenSkyMission.MeshStatus.MESH_READY
                mission.mesh_size_mb = glb_size_mb
                mission.mesh_glb_size_mb = glb_size_mb
                mission.mesh_completed_at = timezone.now()
                mission.mesh_error_message = ''
                # IMPORTANT: persist MESH_READY BEFORE generate_3d_tiles_for_mission,
                # because its regenerate_root_tileset() queries the DB for MESH_READY missions.
                # Without this, the root tileset gets deleted right after it's created.
                mission.save(update_fields=[
                    'mesh_status', 'mesh_size_mb', 'mesh_glb_size_mb',
                    'mesh_completed_at', 'mesh_error_message',
                ])
                mesh_ok = True
                logger.info(f"Mesh generation complete: {glb_size_mb} MB GLB")

                # Step 5.6: Generate 3D Tiles (LODs + tileset.json)
                try:
                    from geo.tiles3d_generator import generate_3d_tiles_for_mission
                    glb_on_skystore = f"{SKYSTORE_OPENSKY}/meshes/{mission_id}/model.glb"
                    # GLB was just uploaded to skystore, use local copy if still available
                    local_glb = os.path.join(local_mesh, "model.glb")
                    if os.path.exists(local_glb):
                        generate_3d_tiles_for_mission(mission, glb_path=local_glb)
                    else:
                        generate_3d_tiles_for_mission(mission)
                    logger.info("3D Tiles generated successfully")
                except Exception as e:
                    logger.error(f"3D Tiles generation failed (non-fatal): {e}", exc_info=True)
            else:
                logger.warning("ODM did not produce mesh output — skipping mesh step")
        except Exception as e:
            logger.error(f"Mesh generation failed (non-fatal): {e}", exc_info=True)
            mission.mesh_status = OpenSkyMission.MeshStatus.MESH_FAILED
            mission.mesh_error_message = str(e)[:1000]
        finally:
            # Cleanup local mesh temp dir
            local_mesh_dir = f"{MESHES_LOCAL_DIR}/{mission_id}"
            if os.path.exists(local_mesh_dir):
                shutil.rmtree(local_mesh_dir, ignore_errors=True)

        # Step 6: Update mission record
        mission.status = OpenSkyMission.Status.PUBLISHED
        mission.published_at = timezone.now()
        # A fresh ortho was saved (Step 3.6, possibly consensus-shifted AFTER
        # the Step 3.5 edges were measured) — mark the frame as new so Phase-2
        # only consumes edges measured against it (measure_opensky_edges).
        mission.georef_changed_at = timezone.now()
        mission.tiles_count = tiles_count
        mission.tiles_size_mb = round(tiles_size / 1024 / 1024, 2)
        mission.min_zoom = TILE_MIN_ZOOM
        mission.max_zoom = TILE_MAX_ZOOM

        # area + center for tile-based missions are already set at the top of
        # process_mission. Legacy missions without tile_z/x/y fall back to
        # coverage_polygon computed in Step 5.
        if not (mission.tile_z and mission.tile_x is not None and mission.tile_y is not None):
            if coverage_polygon:
                mission.area = coverage_polygon
                if bounds:
                    mission.center_lat = (bounds[1] + bounds[3]) / 2
                    mission.center_lng = (bounds[0] + bounds[2]) / 2

        # Reverse-geocode the survey location once, at publish — durable + present
        # in SSR. Cards read these stored fields; the client lookup is only a fallback.
        mission.place_label, mission.place_region = reverse_geocode_place(
            mission.center_lat, mission.center_lng)

        mission.processing_step = ''
        mission.save()
        _publish_mission_update(mission.id, {
            'status': 'PUBLISHED',
            'processing_step': '',
            'published_at': mission.published_at.isoformat(),
            'tiles_count': mission.tiles_count,
            'center_lat': mission.center_lat,
            'center_lng': mission.center_lng,
        })

        # Step 7: Cleanup skystore processing dir (images stay for mesh pipeline)
        logger.info("Step 7: Cleaning up skystore processing dir...")
        _skystore_ssh(f"sudo rm -rf {r_processing}")

        logger.info(f"Mission {mission_id} processed successfully!")
        return True

    except Exception as e:
        logger.error(f"Error processing mission {mission_id}: {e}", exc_info=True)

        # Build detailed error message with stderr context
        error_parts = [str(e)]
        if isinstance(e, subprocess.CalledProcessError):
            if e.stderr:
                error_parts.append(f"STDERR(last 500): {e.stderr[-500:]}")
            if e.stdout:
                error_parts.append(f"STDOUT(last 500): {e.stdout[-500:]}")
        error_msg = ' | '.join(error_parts)

        mission.status = OpenSkyMission.Status.FAILED
        mission.processing_step = ''
        mission.error_message = error_msg[:2000]
        mission.save(update_fields=['status', 'processing_step', 'error_message'])
        _publish_mission_update(mission.id, {
            'status': 'FAILED',
            'processing_step': '',
            'error_message': mission.error_message,
        })

        # Keep processing dir on failure for diagnostics (cleanup manually or on retry)
        logger.error(f"Processing dir preserved for diagnostics: {r_processing}")

        return False


# ============================================================================
# Split-merge consolidation (Phase 2 — see PK/opensky-system.md § Consolidation)
#
# A cluster of overlapping missions disagrees at its Z17 seams by an AFFINE
# residual (per-flight GPS scale + independent DSMs) that the per-mission 2D
# consensus can't remove. Joint ODM reconstruction of ALL members' photos
# (--split / --split-overlap) yields ONE seamless ortho. The consolidation is
# itself an OpenSkyMission row (is_consolidation=True) tiled at max layer_order;
# its members keep their own tiles/orthos and point back via superseded_by, so
# the consolidation can be deleted to roll back.
# ============================================================================

def _consolidation_union_bounds_3857(members) -> tuple[float, float, float, float] | None:
    """Bounding rectangle (EPSG:3857) of all member Z17 cells.

    Because every member is a Z17 cell on the same grid, this rectangle is
    Z17-aligned for free — so the union clip emits only whole-cell tiles
    (opaque inside a member cell, empty placeholder outside), never partial
    edge tiles. That is what guarantees no holes when the super-tile overrides
    members in latest/.
    """
    boxes = [
        _z17_tile_bounds_3857(m.tile_z, m.tile_x, m.tile_y, buffer_m=0)
        for m in members
        if m.tile_z and m.tile_x is not None and m.tile_y is not None
    ]
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes), min(b[1] for b in boxes),
        max(b[2] for b in boxes), max(b[3] for b in boxes),
    )


def run_odm_splitmerge_skystore(consolidation_id: str, no_split: bool = False,
                                gps_accuracy: float = None) -> str:
    """Run ODM joint reconstruction on a prepared combined project.

    Assumes process_consolidation() has already populated
    /fast-processing/{cid}/images with all members' photos (prefixed). Returns
    the merged orthophoto path. Default adds --split/--split-overlap (memory-
    bounded submodels); `no_split=True` runs ONE global model — no submodel
    alignment step to fail (run-4 merged quadrants 26-49m apart), at the cost
    of a single big dense fusion (~65MB/img at high — budget RAM+swap; the
    48GB+80G-swap skystore covers the 1446-photo church cluster).

    gps_accuracy overrides ODM's --gps-accuracy (default 3m). For a CROSS-SEASON
    consolidation the 3m default is too tight: each flight-day carries its own
    absolute DJI-GPS bias (~10-24m, measured 2026-06-12), and a 3m GPS sigma
    pins each flight to its biased coords in BA, so cross-season feature matches
    (which exist) cannot weld the blocks — the merged mosaic comes out displaced
    per-flight (run-5b gate refusal, spread 10.8m). Raising it to ~30m lets the
    features dominate relative geometry (biases fall inside 1σ → treated as
    noise); absolute georef is then restored by the members anchor. See
    PK/opensky-system.md § GPS weight.
    """
    r_processing = f"{SKYSTORE_FAST_PROCESSING}/{consolidation_id}"
    r_ortho = f"{r_processing}/odm_orthophoto/odm_orthophoto.tif"
    container_name = f"odmsm-{consolidation_id[:10]}"

    # Skip if a previous run already produced the merged ortho (resume)
    check = _skystore_ssh(f"test -f {r_ortho} && echo exists || echo missing")
    if "exists" in check.stdout:
        logger.info(f"Split-merge ortho already exists, skipping ODM: {r_ortho}")
        return r_ortho

    # Re-adopt a still-running container instead of killing it: the container
    # is local to skystore and survives tunnel flaps / orchestrator restarts —
    # only our visibility dies. rm -f here would murder hours of healthy ODM.
    st = _skystore_ssh(
        f"docker inspect -f '{{{{.State.Status}}}}' {container_name} 2>/dev/null || echo absent")
    status = (st.stdout or 'absent').strip().splitlines()[-1]
    if status == 'running':
        logger.info(
            f"ODM container {container_name} already running — re-adopting "
            f"(orchestrator restart while ODM in flight)")
        return _await_odm_container(consolidation_id, container_name, r_ortho)

    _skystore_ssh(f"docker rm -f {container_name} 2>/dev/null || true")

    # A PARTIAL features/ dir (run killed mid-extraction) makes ODM skip
    # detection entirely (its stage gate is dir-existence, per-image skip lives
    # only INSIDE detect_features) and then crash instantly in match_features.
    # Clear it for a clean re-detect; complete features (== image count) and
    # absent features are both fine as-is.
    n_imgs = (_skystore_ssh(f"ls {r_processing}/images 2>/dev/null | wc -l").stdout or '0').strip()
    n_feat = (_skystore_ssh(f"ls {r_processing}/opensfm/features 2>/dev/null | wc -l").stdout or '0').strip()
    if n_feat.isdigit() and n_imgs.isdigit() and 0 < int(n_feat) < int(n_imgs):
        logger.info(
            f"Consolidation {consolidation_id[:8]}: partial features dir "
            f"({n_feat}/{n_imgs}) — clearing for clean re-detect")
        _skystore_ssh(f"sudo rm -rf {r_processing}/opensfm/features")

    docker_cmd = (
        f"docker run -d --name {container_name} --gpus all"
        f" -v {SKYSTORE_FAST_PROCESSING}:{SKYSTORE_FAST_PROCESSING}"
        f" {SKYSTORE_ODM_IMAGE}"
        f" --project-path {SKYSTORE_FAST_PROCESSING}"
        f" --orthophoto-resolution {ODM_RESOLUTION}"
        f" --feature-quality high"
        # pc-quality high needs ~41GB RAM+swap for a cross-season consolidation
        # (medium ≈34GB): on the 16GB skystore OpenMVS DensifyPointCloud OOM-killed
        # 3x with swap 100% full. Fusion memory is nearly insensitive to pc-quality
        # (high→medium −12%; `low` is NOT a validated escape). Seamlessness comes
        # from the joint SfM, not pc-quality — on 16GB add a second swapfile or
        # consolidate per column-pair. See PK/opensky-system.md § Memory budget.
        f" --pc-quality high"
        f" --max-concurrency {ODM_MAX_CONCURRENCY}"
        f" --dsm"
        # NO --optimize-disk-space (see process_mission): on 1.7T NVMe it only
        # destroys resume checkpoints — cost ~1.5h re-derive per interruption.
        + (f" --gps-accuracy {gps_accuracy}" if gps_accuracy else "")
        + ("" if no_split else f" --split {ODM_SPLIT} --split-overlap {ODM_SPLIT_OVERLAP}")
        + f" --end-with odm_orthophoto"
        f" {consolidation_id}"
    )
    # Run detached so the multi-hour job lives in the docker daemon, independent
    # of this SSH session. Then poll the container until it exits.
    logger.info(f"Running ODM split-merge on skystore: {docker_cmd}")
    _skystore_ssh(docker_cmd, timeout=120)
    return _await_odm_container(consolidation_id, container_name, r_ortho)


def _await_odm_container(consolidation_id: str, container_name: str, r_ortho: str) -> str:
    """Block until the detached ODM container exits; save its full log; verify ortho.

    The container is removed ONLY once it has provably exited — on transport
    errors (tunnel flap, orchestrator death) it is left running so a restarted
    orchestrator re-adopts it instead of redoing hours of reconstruction.
    """
    container_done = False
    try:
        result = _skystore_ssh(f"docker wait {container_name}", timeout=57600)  # 16h ceiling
        exit_code = (result.stdout or '').strip().splitlines()[-1] if result.stdout.strip() else '?'
        container_done = True
        if exit_code != '0':
            _save_odm_failure_logs(consolidation_id, container_name)
            raise RuntimeError(f"ODM split-merge exited {exit_code}")
    finally:
        # Keep the FULL ODM log on success too — the run-4 submodel-merge
        # failure (quadrants 26-49m apart) had no forensics because logs died
        # with the container and scratch was cleaned on "success".
        try:
            _skystore_ssh(
                f"mkdir -p {SKYSTORE_OPENSKY}/missions/{consolidation_id} && "
                f"docker logs {container_name} > {SKYSTORE_OPENSKY}/missions/{consolidation_id}/odm_splitmerge.log 2>&1 || true",
                timeout=300,
            )
            if container_done:
                _skystore_ssh(f"docker rm -f {container_name} 2>/dev/null || true")
        except Exception as log_err:  # never mask the real failure with log plumbing
            logger.warning(f"Could not save ODM log / remove container (tunnel down?): {log_err}")

    ok = _skystore_ssh(f"test -f {r_ortho} && echo ok || echo no")
    if "ok" not in ok.stdout:
        raise RuntimeError("ODM split-merge produced no merged orthophoto")
    return r_ortho


# A large ECC shift needs a strong correlation to be believable: the merged
# church ortho got a bogus +10.2/-10.7m "lock" at cc=0.177 (2026-06-12),
# compounding an ~18m raw-GPS bias into a 33m mis-anchor. Ordinary missions
# keep the script-level floor (0.15) — this gate applies where a big jump is
# claimed on weak evidence.
SAT_LARGE_SHIFT_M = 5.0
SAT_LARGE_SHIFT_MIN_CC = 0.35


def _measure_consolidation_vs_members(consolidation_id: str, member_ids: list,
                                      max_shift_m: float = 60.0) -> list:
    """ORB-measure the consolidation ortho against its members' saved orthos.

    Members render the SAME photos over the same cells, so this is same-content
    matching — the strongest possible reference for placing a merged ortho into
    the frame the rest of the map already agrees with. Returns edge dicts
    (corrections to apply to the CONSOLIDATION). Diagnostic refs dir is
    temporary; nothing is written to the pose graph (members are superseded).
    """
    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{consolidation_id}.tif"
    r_refs = f"{SKYSTORE_FAST_PROCESSING}/_memref_{consolidation_id}"
    _skystore_ssh(f"rm -rf {r_refs} && mkdir -p {r_refs}")
    for mid in member_ids:
        _skystore_ssh(f"ln -sfn {SKYSTORE_OPENSKY}/orthos/{mid}.tif {r_refs}/{mid}.tif")
    try:
        script = _build_multi_neighbor_alignment_script(
            consolidation_id, r_ortho, r_refs, max_shift_m=max_shift_m)
        res = _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=3600)
        return _parse_alignment_output(consolidation_id, res.stdout or '')
    finally:
        _skystore_ssh(f"rm -rf {r_refs}")


def _fit_similarity_to_members(edges):
    """Least-squares 2D similarity (scale, rotation, translation about the EPSG:3857
    centroid of the member overlap windows) that best maps the merged consolidation
    ortho onto its members' frame. Input = same-content member edges from
    `_measure_consolidation_vs_members` (dx/dy at ref_x/y_3857). Returns
    (cx, cy, ln_scale, rot_deg, tx, ty) — the correction to apply to the
    consolidation — or None if there are <3 edges or the fit leaves the sane
    similarity envelope (|s-1|>5% or |θ|>5°, matching the Phase-2 ORB gate) so the
    caller falls back to a pure translation.

    Fit on the TRANSLATION field, NOT the per-edge `rel_scale`: members are precise
    same-content references (<1 m), so the spatial arrangement of their displacement
    vectors is the clean global-scale signal, whereas per-patch ORB rel_scale is
    lean/parallax-contaminated (church June 4-cell: rel_scale mean +1.4% overcorrects
    to 3.1 m spread; the translation-field scale +0.86% lands 1.98 m — under the gate).
    This is the OPPOSITE of the multi-mission Phase-2 BA (noisy satellite anchors →
    scale must come from direct rel_scale, see § Phase 2) because here the reference
    is precise. A pure translation cannot remove a per-flight GPS scale drift, which
    is why translation-only members anchoring left the joint ortho 3 m bent.
    """
    if len(edges) < 3:
        return None
    import numpy as np
    P = np.array([[e['ref_x_3857'], e['ref_y_3857']] for e in edges], float)
    D = np.array([[e['dx_m'], e['dy_m']] for e in edges], float)
    w = np.array([max(e['overlap_m2'] * e['inlier_ratio'], 1e-6) for e in edges], float)
    cx, cy = P.mean(axis=0)
    Pc = P - (cx, cy)
    Tc = Pc + D
    # weighted similarity lstsq: [x';y'] = [[x,-y,1,0],[y,x,0,1]] · [a,b,tx,ty]
    rows, rhs, sw = [], [], []
    for (x, y), (tx_, ty_), wi in zip(Pc, Tc, w):
        s = wi ** 0.5
        rows += [[x, -y, 1.0, 0.0], [y, x, 0.0, 1.0]]
        rhs += [tx_, ty_]
        sw += [s, s]
    sw = np.array(sw)
    a, b, tx, ty = np.linalg.lstsq(np.array(rows) * sw[:, None], np.array(rhs) * sw, rcond=None)[0]
    ln_scale = math.log(math.hypot(a, b))
    rot_deg = math.degrees(math.atan2(b, a))
    if abs(ln_scale) > 0.05 or abs(rot_deg) > 5.0:
        logger.warning(
            f"Members similarity fit out of envelope (scale {(math.exp(ln_scale)-1)*100:+.1f}%, "
            f"rot {rot_deg:+.2f}°) — falling back to translation")
        return None
    return float(cx), float(cy), float(ln_scale), float(rot_deg), float(tx), float(ty)


def realign_consolidation_to_members(consolidation_id: str, dry_run: bool = False) -> bool:
    """Shift a published consolidation onto its members' frame, then retile.

    Recovery/maintenance path for a mis-anchored super-tile (see 2026-06-12:
    weak-cc satellite lock left the church consolidation 33m off; members ARE
    the ground truth the surrounding map was aligned to). Weighted average of
    member ORB edges, no satellite damping (members define the frame), sanity
    bounds instead of the 10m consensus cap. Returns True if applied.
    """
    from geo.models import OpenSkyMission
    con = OpenSkyMission.objects.filter(id=consolidation_id, is_consolidation=True).first()
    if not con:
        logger.error(f"{consolidation_id} is not a consolidation")
        return False
    member_ids = list(con.members.values_list('member_id', flat=True))
    if not member_ids:
        logger.error(f"Consolidation {consolidation_id}: no members")
        return False

    edges = _measure_consolidation_vs_members(consolidation_id, member_ids)
    if len(edges) < 2:
        logger.error(
            f"Consolidation {consolidation_id}: only {len(edges)} member edge(s) measured — "
            f"refusing to realign on a single observation")
        return False
    w_sum = sum(e['overlap_m2'] * e['inlier_ratio'] for e in edges)
    dx = sum(e['dx_m'] * e['overlap_m2'] * e['inlier_ratio'] for e in edges) / w_sum
    dy = sum(e['dy_m'] * e['overlap_m2'] * e['inlier_ratio'] for e in edges) / w_sum
    spread = max(((e['dx_m'] - dx) ** 2 + (e['dy_m'] - dy) ** 2) ** 0.5 for e in edges)
    shift = (dx ** 2 + dy ** 2) ** 0.5
    logger.info(
        f"Consolidation {consolidation_id[:8]} vs {len(edges)} members: "
        f"shift=({dx:+.2f},{dy:+.2f})m |s|={shift:.2f}m spread={spread:.2f}m")
    if spread > 3.0:
        logger.error(f"Member edges disagree by {spread:.2f}m (>3m) — refusing to realign")
        return False
    if shift < MIN_CONSENSUS_SHIFT_M:
        logger.info("Already aligned to members (below threshold)")
        return False
    if dry_run:
        logger.info("[DRY RUN] nothing applied")
        return False

    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{consolidation_id}.tif"
    r_tmp = f"{SKYSTORE_FAST_PROCESSING}/_conrealign_{consolidation_id}"
    r_shifted = f"{r_tmp}/shifted.tif"
    try:
        _skystore_ssh(f"mkdir -p {r_tmp}")
        apply_script = _build_apply_shift_script(r_ortho, r_shifted, dx, dy)
        _skystore_ssh(f"python3 -c {shlex.quote(apply_script)}", timeout=600)
        _skystore_ssh(f"cp {r_shifted} {r_ortho}")
        _mark_georef_changed(consolidation_id)
        tiles_count = _reclip_retile_publish(consolidation_id, r_ortho, r_tmp)
        logger.info(f"Consolidation {consolidation_id[:8]}: realigned to members + retiled, {tiles_count} tiles")
        return True
    finally:
        try:
            _skystore_ssh(f"rm -rf {r_tmp}")
        except Exception:
            pass


def _anchor_merged_ortho(consolidation_id: str, r_ortho: str, r_tmp: str, member_ids: list):
    """Anchor the raw-GPS merged ortho to the established map frame. Order:
    (1) ORB vs the MEMBERS' saved orthos (same content — the strongest and
    only season-proof reference; the members already sit in the frame the
    whole map agrees with); (2) satellite ECC as cross-check, applied only if
    small or strongly correlated; (3) ORB consensus vs NON-member neighbours
    (ring refinement). Mutates r_ortho in place.
    """
    # --- (1) Members anchor (primary): same-content ORB, TWO-STAGE.
    # (1a) COARSE weighted-mean translation positions the merged ortho into the
    #      member frame. The raw merged-GPS ortho is ~5 m off, so its ORB overlap
    #      windows mis-register and a similarity measured on it is unreliable (run-2
    #      raw fit gave +0.32%/-0.35° vs the +0.86%/+0.09° measured post-translation).
    # (1b) FINE 2D similarity, re-measured on the now-aligned ortho, removes the
    #      per-flight GPS scale drift (~0.9%) that a pure translation CANNOT — church
    #      June 4-cell: translation-only leaves 3.0 m member spread, +similarity
    #      1.9 m (under the 2.5 m gate). Fit on the precise member translation field,
    #      not the lean-contaminated per-patch rel_scale (see _fit_similarity_to_members).
    #      The lossless warp leaves a ROTATED geotransform; unlike the Phase-2 path it
    #      is not immediately reclipped, and the satellite/ring cross-checks that
    #      follow (gdal_translate -projwin) + the gate assume north-up — so de-rotate
    #      to north-up now (bakes the similarity into pixels; rotation <0.5° → near
    #      lossless). 2 edges → translation only (2D similarity underdetermined). ---
    # `members_anchored` makes the satellite + ring steps below LOG-ONLY cross-checks
    # once we have a members frame: same-content members ORB is the precise reference,
    # while satellite ECC (~1-2 m, weak cc) and the non-member ring PULL a good anchor
    # off — run-3: sat cc=0.16 + ring +1.5 m dragged a 0.07 m residual to 1.15 m and
    # failed the gate. See PK/opensky-system.md § Consolidation (anchor order).
    members_anchored = False
    edges = _measure_consolidation_vs_members(consolidation_id, member_ids)
    if len(edges) >= 2:
        members_anchored = True
        w_sum = sum(e['overlap_m2'] * e['inlier_ratio'] for e in edges)
        mdx = sum(e['dx_m'] * e['overlap_m2'] * e['inlier_ratio'] for e in edges) / w_sum
        mdy = sum(e['dy_m'] * e['overlap_m2'] * e['inlier_ratio'] for e in edges) / w_sum
        mshift = (mdx ** 2 + mdy ** 2) ** 0.5
        logger.info(
            f"Consolidation {consolidation_id[:8]}: members anchor (translation) "
            f"({mdx:+.2f},{mdy:+.2f})m |s|={mshift:.2f}m from {len(edges)} member edge(s)")
        if mshift >= MIN_CONSENSUS_SHIFT_M:
            r_mem = f"{r_tmp}/member_aligned.tif"
            _skystore_ssh(f"python3 -c {shlex.quote(_build_apply_shift_script(r_ortho, r_mem, mdx, mdy))}",
                          timeout=600)
            _skystore_ssh(f"cp {r_mem} {r_ortho}")
            logger.info(f"Consolidation {consolidation_id[:8]}: applied members anchor (translation)")
            # re-measure on the aligned ortho for a reliable similarity fit
            edges = _measure_consolidation_vs_members(consolidation_id, member_ids)
        sim = _fit_similarity_to_members(edges)
        if sim is not None:
            cx, cy, d_lns, d_rot, d_tx, d_ty = sim
            if (abs(d_lns) >= SIM_APPLY_SCALE or abs(d_rot) >= SIM_APPLY_ROT_DEG
                    or (d_tx ** 2 + d_ty ** 2) ** 0.5 >= MIN_CONSENSUS_SHIFT_M):
                logger.info(
                    f"Consolidation {consolidation_id[:8]}: members similarity refinement "
                    f"scale={(math.exp(d_lns) - 1) * 100:+.2f}% rot={d_rot:+.3f}° "
                    f"t=({d_tx:+.2f},{d_ty:+.2f})m from {len(edges)} member edge(s)")
                r_sim = f"{r_tmp}/member_sim.tif"
                _skystore_ssh(
                    f"python3 -c {shlex.quote(_build_similarity_warp_script(r_ortho, r_sim, cx, cy, d_lns, d_rot, d_tx, d_ty))}",
                    timeout=600)
                # de-rotate the warped grid back to north-up (the cross-checks below
                # and the reclip cannot consume a rotated raster reliably)
                r_sim_nu = f"{r_tmp}/member_sim_nu.tif"
                _skystore_ssh(
                    f"gdalwarp -r lanczos -co COMPRESS=LZW -co TILED=YES -co BIGTIFF=IF_SAFER "
                    f"-dstnodata 0 -overwrite {r_sim} {r_sim_nu}", timeout=1800)
                _skystore_ssh(f"cp {r_sim_nu} {r_ortho}")
                logger.info(f"Consolidation {consolidation_id[:8]}: applied members similarity refinement")
    else:
        logger.warning(
            f"Consolidation {consolidation_id[:8]}: members anchor unavailable "
            f"({len(edges)} edge(s)) — falling back to satellite/ring only")

    # --- (2) Satellite anchor (cross-check; gated against weak-cc big jumps) ---
    r_sat = f"{r_tmp}/sat_aligned.tif"
    sat_script = _build_satellite_alignment_script(r_ortho, r_sat, SATELLITE_CACHE_DIR)
    sat_res = _skystore_ssh(f"python3 -c {shlex.quote(sat_script)}", timeout=600)
    sat_dx = sat_dy = sat_cc = 0.0
    for line in (sat_res.stdout or '').strip().splitlines():
        if line.startswith('SAT_RESULT:'):
            try:
                p = line.split(':'); sat_dx, sat_dy, sat_cc = float(p[1]), float(p[2]), float(p[3])
            except (ValueError, IndexError):
                pass
    sat_shift = (sat_dx ** 2 + sat_dy ** 2) ** 0.5
    if "aligned" in _skystore_ssh(f"test -f {r_sat} && echo aligned || echo identity").stdout:
        if sat_shift > SAT_LARGE_SHIFT_M and sat_cc < SAT_LARGE_SHIFT_MIN_CC:
            logger.warning(
                f"Consolidation {consolidation_id[:8]}: satellite suggests "
                f"({sat_dx:+.2f},{sat_dy:+.2f})m at weak cc={sat_cc:.3f} — NOT applying "
                f"(large shift needs cc>={SAT_LARGE_SHIFT_MIN_CC}; 2026-06-12 bogus-lock incident)")
        elif members_anchored:
            logger.info(
                f"Consolidation {consolidation_id[:8]}: satellite cross-check "
                f"({sat_dx:+.2f},{sat_dy:+.2f}) cc={sat_cc:.3f} — log-only (members anchor authoritative)")
        else:
            _skystore_ssh(f"cp {r_sat} {r_ortho}")
            _write_satellite_anchor(consolidation_id, sat_dx, sat_dy, sat_cc)
            logger.info(f"Consolidation {consolidation_id[:8]}: satellite-anchored ({sat_dx:+.2f},{sat_dy:+.2f}) cc={sat_cc:.3f}")
    else:
        logger.info(f"Consolidation {consolidation_id[:8]}: satellite anchor — no correction")

    # --- ORB consensus vs NON-member neighbors only ---
    # Build a refs dir of orthos for missions that are NOT members and NOT this
    # consolidation, so the merged ortho aligns to the surrounding ring (keeps
    # the super-tile seamless against the rest of the map), never to a member.
    r_refs = f"{r_tmp}/refs"
    listing = _skystore_ssh(f"ls {SKYSTORE_OPENSKY}/orthos/ 2>/dev/null | grep '\\.tif$' || true")
    exclude = set(member_ids) | {consolidation_id}
    ref_ids = [
        fn[:-4] for fn in (listing.stdout or '').split()
        if fn.endswith('.tif') and fn[:-4] not in exclude
    ]
    if ref_ids:
        _skystore_ssh(f"rm -rf {r_refs} && mkdir -p {r_refs}")
        for rid in ref_ids:
            _skystore_ssh(f"ln -sfn {SKYSTORE_OPENSKY}/orthos/{rid}.tif {r_refs}/{rid}.tif")
        meas_script = _build_multi_neighbor_alignment_script(consolidation_id, r_ortho, r_refs)
        meas = _skystore_ssh(f"python3 -c {shlex.quote(meas_script)}", timeout=3600)
        edges = _parse_alignment_output(consolidation_id, meas.stdout or '')
        _write_orb_edges(consolidation_id, edges)
        cs = compute_consensus_shift(consolidation_id, edges)
        logger.info(
            f"Consolidation {consolidation_id[:8]}: ORB vs {len(ref_ids)} non-members "
            f"edges={len(edges)} used={cs['n_used']} shift=({cs['avg_dx']:+.2f},{cs['avg_dy']:+.2f})m |s|={cs['shift_m']:.2f}m"
        )
        if members_anchored:
            logger.info(
                f"Consolidation {consolidation_id[:8]}: ring cross-check "
                f"({cs['avg_dx']:+.2f},{cs['avg_dy']:+.2f})m |s|={cs['shift_m']:.2f}m — "
                f"log-only (members anchor authoritative)")
        elif MIN_CONSENSUS_SHIFT_M <= cs['shift_m'] <= MAX_CONSENSUS_SHIFT_M:
            r_shifted = f"{r_tmp}/orb_shifted.tif"
            apply_script = _build_apply_shift_script(r_ortho, r_shifted, cs['avg_dx'], cs['avg_dy'])
            _skystore_ssh(f"python3 -c {shlex.quote(apply_script)}", timeout=300)
            _skystore_ssh(f"cp {r_shifted} {r_ortho}")
            logger.info(f"Consolidation {consolidation_id[:8]}: applied ORB consensus shift")


def process_consolidation(consolidation_id: str, no_split: bool = False,
                          resume: bool = False, gps_accuracy: float = None) -> bool:
    """Build a seamless super-tile from a consolidation's member missions.

    Mirrors process_mission(): joint ODM split-merge → reproject → satellite +
    ORB anchor → union-clip → tile → override latest/ (clear members, plant
    consolidation) → publish + supersede members. On failure, heals latest/
    from the surviving member tiles and leaves members un-superseded.

    resume=True keeps the existing scratch dir when all photos are already
    pooled (count match) — ODM then skips its completed stages, so a run
    interrupted mid-pipeline (e.g. skystore power loss) loses only the stage
    it died in, not the hours of SfM before it. Falls back to a clean re-pool
    on any count mismatch.
    """
    from geo.models import OpenSkyMission, OpenSkyTileLayer

    con = OpenSkyMission.objects.filter(id=consolidation_id, is_consolidation=True).first()
    if not con:
        logger.error(f"Consolidation {consolidation_id} not found / not a consolidation")
        return False

    members = [link.member for link in con.members.select_related('member').order_by('order')]
    member_ids = [m.id for m in members]
    if len(members) < 2:
        logger.error(f"Consolidation {consolidation_id}: needs >=2 members, has {len(members)}")
        return False
    not_pub = [m.id[:8] for m in members if m.status != OpenSkyMission.Status.PUBLISHED]
    if not_pub:
        logger.error(f"Consolidation {consolidation_id}: members not PUBLISHED: {not_pub}")
        return False

    r_proc = f"{SKYSTORE_FAST_PROCESSING}/{consolidation_id}"
    r_images = f"{r_proc}/images"
    r_ortho_saved = f"{SKYSTORE_OPENSKY}/orthos/{consolidation_id}.tif"
    r_tiles_mission = f"{SKYSTORE_TILES}/missions/{consolidation_id}"
    r_tiles_latest = f"{SKYSTORE_TILES}/latest"

    try:
        # --- Mark PROCESSING + union area/center ---
        union = _consolidation_union_bounds_3857(members)
        if not union:
            logger.error(f"Consolidation {consolidation_id}: no member has tile_z/x/y")
            return False
        from pyproj import Transformer
        t = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
        sw_lng, sw_lat = t.transform(union[0], union[1])
        ne_lng, ne_lat = t.transform(union[2], union[3])
        con.status = OpenSkyMission.Status.PROCESSING
        con.processing_started_at = timezone.now()
        con.processing_step = OpenSkyMission.ProcessingStep.ODM
        con.error_message = ''
        con.area = Polygon((
            (sw_lng, sw_lat), (ne_lng, sw_lat), (ne_lng, ne_lat), (sw_lng, ne_lat), (sw_lng, sw_lat),
        ))
        con.center_lat = (sw_lat + ne_lat) / 2
        con.center_lng = (sw_lng + ne_lng) / 2
        con.tile_z = con.tile_x = con.tile_y = None  # spans many cells — keep NULL
        con.save(update_fields=[
            'status', 'processing_started_at', 'processing_step', 'error_message',
            'area', 'center_lat', 'center_lng', 'tile_z', 'tile_x', 'tile_y',
        ])
        _publish_mission_update(con.id, {'status': 'PROCESSING', 'processing_step': 'odm'})

        # --- Step 1: pre-flight photo cap + disk ---
        total_photos = sum(m.source_photos_count for m in members)
        if total_photos > MAX_CONSOLIDATION_PHOTOS:
            raise RuntimeError(
                f"cluster has {total_photos} photos > cap {MAX_CONSOLIDATION_PHOTOS}; split the cluster")
        dfres = _skystore_ssh(f"df -BG --output=avail {SKYSTORE_FAST_PROCESSING} | tail -1")
        free_gb = int(''.join(c for c in (dfres.stdout or '0').strip() if c.isdigit()) or '0')
        if free_gb < MIN_FAST_PROCESSING_FREE_GB:
            raise RuntimeError(
                f"/fast-processing has {free_gb}G free < {MIN_FAST_PROCESSING_FREE_GB}G required")

        # --- Step 2: combined project — copy each member's photos with its prefix ---
        pooled = False
        if resume:
            n_existing = (_skystore_ssh(f"ls {r_images} 2>/dev/null | wc -l").stdout or '0').strip()
            if n_existing.isdigit() and int(n_existing) == total_photos:
                logger.info(
                    f"Consolidation {consolidation_id[:8]}: resume — {n_existing} photos already "
                    f"pooled, keeping scratch (ODM skips completed stages)")
                pooled = True
            else:
                logger.info(
                    f"Consolidation {consolidation_id[:8]}: resume requested but images dir has "
                    f"{n_existing} != {total_photos} photos — re-pooling from scratch")
        if not pooled:
            _skystore_ssh(f"sudo rm -rf {r_proc} && mkdir -p {r_images}")
            for link in con.members.order_by('order'):
                src = f"{SKYSTORE_OPENSKY}/missions/{link.member_id}/images"
                # find -iname matches .jpg/.JPG and exits 0 on no match (a bare glob
                # would iterate the literal pattern and fail the loop).
                _skystore_ssh(
                    f'find {src} -maxdepth 1 -type f -iname "*.jpg" | '
                    f'while read f; do cp "$f" {r_images}/{link.prefix}$(basename "$f"); done',
                    timeout=3600,
                )
            n_copied = _skystore_ssh(f"ls {r_images} | wc -l").stdout.strip()
            logger.info(f"Consolidation {consolidation_id[:8]}: pooled {n_copied} photos from {len(members)} missions")

        # --- Step 3: ODM split-merge ---
        con.processing_step = OpenSkyMission.ProcessingStep.ODM
        con.save(update_fields=['processing_step'])
        r_merged = run_odm_splitmerge_skystore(consolidation_id, no_split=no_split,
                                               gps_accuracy=gps_accuracy)

        # --- Step 4: reproject to EPSG:3857 ---
        r_3857 = f"{r_proc}/orthophoto_3857.tif"
        _skystore_ssh(
            f"gdalwarp -t_srs EPSG:3857 -r lanczos -co COMPRESS=LZW -co TILED=YES "
            f"-overwrite {r_merged} {r_3857}", timeout=1800)
        # Save unclipped (needed for ORB neighbor reads + future re-alignment)
        _skystore_ssh(f"cp {r_3857} {r_ortho_saved}")

        # --- Step 5 / 5b: members + satellite + ORB anchor to absolute frame ---
        con.processing_step = OpenSkyMission.ProcessingStep.ALIGNMENT
        con.save(update_fields=['processing_step'])
        _anchor_merged_ortho(consolidation_id, r_ortho_saved, r_proc, member_ids)

        # --- Step 5.9: VERIFICATION GATE — refuse to publish a merged ortho
        # that disagrees with its members. Same-content ORB per member; the mean
        # (residual) must be ~0 after the anchor (gross mis-anchor catch), and the
        # SPREAD = max per-member deviation from that mean.
        # The spread threshold is SPLIT-MODE dependent:
        #   --split  → 2.5m: spread catches piecewise submodel-merge failures
        #              (run-4 2026-06-12: quadrants 26-49m apart, melted patchwork).
        #   --no-split → 4.0m: ONE global model, so there is NO submodel-merge mode
        #              to fail. The spread floor is then the legitimate residual of a
        #              similarity-anchored same-season block — the consolidation
        #              renders buildings differently from each leaning single-mission
        #              member, and the weakest-overlap member dominates the max
        #              (01KV2R18 June 4-cell: residual 0.25m, spread 2.70m from one
        #              inl=0.52 member while the other 3 agree ≤1.4m). 4.0m still
        #              catches a cross-season joint warp (10.8m) and any gross break.
        #              (TODO: an inlier-weighted/2nd-largest spread would be less
        #              single-weak-member sensitive than max — defer until needed.) ---
        ver_edges = _measure_consolidation_vs_members(consolidation_id, member_ids)
        if len(ver_edges) >= 2:
            vw = sum(e['overlap_m2'] * e['inlier_ratio'] for e in ver_edges)
            vdx = sum(e['dx_m'] * e['overlap_m2'] * e['inlier_ratio'] for e in ver_edges) / vw
            vdy = sum(e['dy_m'] * e['overlap_m2'] * e['inlier_ratio'] for e in ver_edges) / vw
            vshift = (vdx ** 2 + vdy ** 2) ** 0.5
            vspread = max(((e['dx_m'] - vdx) ** 2 + (e['dy_m'] - vdy) ** 2) ** 0.5 for e in ver_edges)
            spread_gate = 4.0 if no_split else 2.5
            logger.info(
                f"Consolidation {consolidation_id[:8]}: member verification "
                f"residual=({vdx:+.2f},{vdy:+.2f})m |s|={vshift:.2f}m spread={vspread:.2f}m "
                f"(gate 1.0/{spread_gate}m)")
            if vshift > 1.0 or vspread > spread_gate:
                raise RuntimeError(
                    f"merged ortho disagrees with members (residual {vshift:.2f}m, "
                    f"spread {vspread:.2f}m > 1.0/{spread_gate}m gate) — refusing to "
                    f"publish; see odm_splitmerge.log")
        else:
            logger.warning(
                f"Consolidation {consolidation_id[:8]}: verification gate skipped "
                f"({len(ver_edges)} member edge(s) measurable)")

        # --- Step 7: clip to union rectangle (Z17-aligned → no partial tiles) ---
        con.processing_step = OpenSkyMission.ProcessingStep.TILING
        con.save(update_fields=['processing_step'])
        r_clipped = f"{r_proc}/orthophoto_clipped.tif"
        _skystore_ssh(
            f"gdalwarp -te {union[0]} {union[1]} {union[2]} {union[3]} -te_srs EPSG:3857 "
            f"-r lanczos -co COMPRESS=LZW -co TILED=YES -dstnodata 0 -overwrite "
            f"{r_ortho_saved} {r_clipped}", timeout=1800)

        # --- Step 8: gdal2tiles → TMS → XYZ WebP ---
        r_tms = f"{r_proc}/tiles_tms"
        _skystore_ssh(
            f"gdal2tiles.py -z {TILE_MIN_ZOOM}-{TILE_MAX_ZOOM} -w none -r lanczos "
            f"--processes=3 {r_clipped} {r_tms}", timeout=57600)
        _skystore_ssh(f"rm -rf {r_tiles_mission} && mkdir -p {r_tiles_mission}")
        conv = _skystore_ssh(
            f"python3 -c {shlex.quote(_build_tms_to_xyz_webp_script(r_tms, r_tiles_mission, WEBP_QUALITY))}",
            timeout=3600)
        tiles_count = tiles_size = 0
        for line in conv.stdout.strip().splitlines():
            if line.startswith("TILES_RESULT:"):
                _, tc, ts = line.split(":"); tiles_count, tiles_size = int(tc), int(ts)

        # --- Step 9: record tile layers at fresh max layer_order (on top) ---
        OpenSkyTileLayer.objects.filter(mission_id=consolidation_id).delete()
        _record_tile_layers(consolidation_id, r_tiles_mission)

        # --- Step 10: override latest/ — clear each member's own tiles, then plant ---
        # Z17+ latest/ is size-wins (NOT layer_order). Clearing member-owned coords
        # frees them so the consolidation's real tiles win vs nothing; non-member
        # neighbor coords are untouched (their real tile beats our ~200B placeholder).
        # COMPOSITE GUARD: clear a member coord ONLY where the consolidation has a
        # real tile (override_tiles_dir). Where the consolidation ortho has a nodata
        # hole (empty ~200B placeholder), the member tile is KEPT and survives the
        # size-wins plant (202B <= member → skipped) → the hole is filled by the
        # member, never lost. The alignment gate does NOT verify completeness.
        composite_filled = 0
        for mid in member_ids:
            composite_filled += _clear_self_owned_latest_tiles(
                mid, r_tiles_latest, f"{SKYSTORE_TILES}/missions/{mid}",
                override_tiles_dir=r_tiles_mission)
        if composite_filled:
            logger.warning(
                f"Consolidation {consolidation_id[:8]}: COMPLETENESS — {composite_filled} member "
                f"tile coord(s) kept as composite-fill (joint ODM left nodata holes there). "
                f"Coverage preserved by members; reconstruction is incomplete — see odm_splitmerge.log")
        _skystore_ssh(
            f"python3 -c {shlex.quote(_build_update_latest_script(r_tiles_mission, r_tiles_latest, consolidation_id))}",
            timeout=600)
        # z<=16 overview: layer_order DOES apply here → max-order consolidation on top.
        rebuild_overview_latest(consolidation_id)
        # z>=17: pixel-composite any tile that is not fully opaque (consolidation
        # ortho sub-tile nodata holes at middle zooms) from members underneath —
        # closes partial holes that the size-wins plant / composite-guard can't.
        composite_partial_consolidation_tiles(consolidation_id)

        # --- Step 11: publish + supersede members ---
        OpenSkyMission.objects.filter(id__in=member_ids).update(superseded_by=con)
        con.status = OpenSkyMission.Status.PUBLISHED
        con.published_at = timezone.now()
        con.georef_changed_at = timezone.now()  # fresh ortho saved + anchored above
        con.tiles_count = tiles_count
        con.tiles_size_mb = round(tiles_size / 1024 / 1024, 2)
        con.min_zoom = TILE_MIN_ZOOM
        con.max_zoom = TILE_MAX_ZOOM
        con.place_label, con.place_region = reverse_geocode_place(con.center_lat, con.center_lng)
        con.processing_step = ''
        con.save()
        _publish_mission_update(con.id, {
            'status': 'PUBLISHED', 'processing_step': '',
            'published_at': con.published_at.isoformat(), 'tiles_count': con.tiles_count,
        })

        # --- Step 12: cleanup scratch on success ---
        _skystore_ssh(f"sudo rm -rf {r_proc}")
        logger.info(f"Consolidation {consolidation_id} published: {len(members)} missions → {tiles_count} tiles")
        return True

    except Exception as e:
        logger.error(f"Error consolidating {consolidation_id}: {e}", exc_info=True)
        # Heal latest/: recomposite the consolidation's coords from surviving
        # contributors (members keep their tiles + DB rows) so no holes remain
        # from a partial clear/plant. No-op if we failed before any latest/ write.
        try:
            rebuild_tiles_after_deletion(consolidation_id)
        except Exception as he:
            logger.error(f"Consolidation heal failed for {consolidation_id}: {he}")
        con.status = OpenSkyMission.Status.FAILED
        con.processing_step = ''
        con.error_message = str(e)[:2000]
        con.save(update_fields=['status', 'processing_step', 'error_message'])
        _publish_mission_update(con.id, {'status': 'FAILED', 'processing_step': '', 'error_message': con.error_message})
        logger.error(f"Consolidation scratch preserved for diagnostics: {r_proc}")
        return False


