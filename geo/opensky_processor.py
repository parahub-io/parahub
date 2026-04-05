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
import shlex
import shutil
import subprocess
import logging
import json
import time

from django.contrib.gis.geos import Polygon
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


def _publish_mission_update(mission_id: str, data: dict):
    """Publish mission update to Redis for real-time WebSocket delivery."""
    import redis as _redis
    try:
        r = _redis.Redis()
        payload = json.dumps({'type': 'opensky.mission_updated', 'mission_id': str(mission_id), **data})
        r.publish('opensky:missions', payload)
    except Exception as e:
        logger.warning(f'Failed to publish opensky update: {e}')


def _skystore_ssh(cmd: str, timeout: int = 60, retries: int = 3) -> subprocess.CompletedProcess:
    """Run a command on skystore via SSH with retry on SSH connection failure (exit 255)."""
    for attempt in range(1, retries + 1):
        try:
            return subprocess.run(
                ["ssh", "-o", "ConnectTimeout=10", SKYSTORE_SSH, cmd],
                timeout=timeout, check=True,
                capture_output=True, text=True,
            )
        except subprocess.TimeoutExpired as e:
            if attempt < retries:
                logger.warning(f'Skystore SSH attempt {attempt}/{retries} timed out, retrying in 5s...')
                time.sleep(5)
            else:
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
                logger.warning(f'Skystore SSH attempt {attempt}/{retries} connection failed, retrying in 5s...')
                time.sleep(5)
            else:
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


def run_odm_skystore(mission_id: str) -> str:
    """Run ODM on skystore via SSH + Docker GPU. Returns remote orthophoto path."""
    remote_images = f"{SKYSTORE_OPENSKY}/missions/{mission_id}/images"
    remote_processing = f"{SKYSTORE_FAST_PROCESSING}/{mission_id}"
    # Clean previous run (Docker creates root-owned files) and prepare project dir on SSD
    _skystore_ssh(f"sudo rm -rf {remote_processing} && mkdir -p {remote_processing}")
    # Symlink source images (on HDD) into processing dir (on SSD)
    _skystore_ssh(f"ln -sfn {remote_images} {remote_processing}/images")
    docker_cmd = (
        f"docker run --rm --gpus all"
        f" -v {SKYSTORE_FAST_PROCESSING}:{SKYSTORE_FAST_PROCESSING}"
        f" -v {SKYSTORE_OPENSKY}/missions:{SKYSTORE_OPENSKY}/missions:ro"
        f" {SKYSTORE_ODM_IMAGE}"
        f" --project-path {SKYSTORE_FAST_PROCESSING}"
        f" --orthophoto-resolution {ODM_RESOLUTION}"
        f" --feature-quality high"
        f" --max-concurrency {ODM_MAX_CONCURRENCY}"
        f" --dsm"
        f" {mission_id}"
    )
    logger.info(f"Running ODM on skystore: {docker_cmd}")
    _skystore_ssh(docker_cmd, timeout=14400)  # 4h timeout
    remote_ortho = f"{remote_processing}/odm_orthophoto/odm_orthophoto.tif"
    result = _skystore_ssh(f"test -f {remote_ortho} && echo ok")
    if "ok" not in result.stdout:
        raise RuntimeError("ODM on skystore failed to produce orthophoto")
    return remote_ortho


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
    """Build standalone Python script for coverage polygon calculation on skystore."""
    return f'''
import os, json, math
tiles_dir = "{tiles_dir}"
min_x, min_y, max_x, max_y = float("inf"), float("inf"), float("-inf"), float("-inf")
min_z = None
for z_str in sorted(os.listdir(tiles_dir)):
    z_path = os.path.join(tiles_dir, z_str)
    if not os.path.isdir(z_path) or not z_str.isdigit():
        continue
    z = int(z_str)
    if min_z is None or z < min_z:
        min_z = z
    for x_str in os.listdir(z_path):
        x_path = os.path.join(z_path, x_str)
        if not os.path.isdir(x_path) or not x_str.isdigit():
            continue
        x = int(x_str)
        for tile_file in os.listdir(x_path):
            if not tile_file.endswith(".webp"):
                continue
            y = int(tile_file.replace(".webp", ""))
            if x < min_x: min_x = x
            if x > max_x: max_x = x
            if y < min_y: min_y = y
            if y > max_y: max_y = y
if min_z is None:
    print("COVERAGE:{{}}")
else:
    z = min_z
    n = 2 ** z
    def tile2ll(x, y, z):
        n = 2 ** z
        lon = x / n * 360.0 - 180.0
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        return (lon, lat)
    # Recalculate bounds at min_z
    min_x2, min_y2, max_x2, max_y2 = float("inf"), float("inf"), float("-inf"), float("-inf")
    z_path = os.path.join(tiles_dir, str(min_z))
    if os.path.isdir(z_path):
        for x_str in os.listdir(z_path):
            x_path = os.path.join(z_path, x_str)
            if not os.path.isdir(x_path) or not x_str.isdigit(): continue
            x = int(x_str)
            for tf in os.listdir(x_path):
                if not tf.endswith(".webp"): continue
                y = int(tf.replace(".webp",""))
                if x < min_x2: min_x2 = x
                if x > max_x2: max_x2 = x
                if y < min_y2: min_y2 = y
                if y > max_y2: max_y2 = y
    sw = tile2ll(min_x2, max_y2 + 1, min_z)
    ne = tile2ll(max_x2 + 1, min_y2, min_z)
    poly = [sw, (ne[0], sw[1]), ne, (sw[0], ne[1]), sw]
    bounds = [sw[0], sw[1], ne[0], ne[1]]
    print("COVERAGE:" + json.dumps({{"polygon": poly, "bounds": bounds}}))
'''


def _build_update_latest_script(mission_dir: str, latest_dir: str, mission_id: str) -> str:
    """Build standalone Python script for updating latest layer on skystore."""
    return f'''
import os
mission_dir = "{mission_dir}"
latest_dir = "{latest_dir}"
os.makedirs(latest_dir, exist_ok=True)
count = 0
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
            if os.path.exists(dst):
                os.unlink(dst)
            try:
                os.link(src, dst)
            except OSError:
                import shutil
                shutil.copy2(src, dst)
            count += 1
print(f"Updated {{count}} tiles in latest layer")
'''


def _build_alignment_script(mission_id, r_reprojected, r_aligned, r_orthos):
    """Build standalone alignment script for skystore. Simplified — uses gdalwarp GCP approach."""
    # Alignment on skystore uses OpenCV feature matching between reference and target ortho.
    # This is a simplified version — full alignment logic is complex.
    # For now, use the best-overlap reference ortho.
    return f'''
import os, sys, glob
import cv2
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import Affine

target = "{r_reprojected}"
output = "{r_aligned}"
orthos_dir = "{r_orthos}"

# Find reference ortho with best overlap (largest file as proxy — same area = similar size)
refs = sorted(glob.glob(os.path.join(orthos_dir, "*.tif")), key=os.path.getsize, reverse=True)
# Exclude self
refs = [r for r in refs if "{mission_id}" not in r]
if not refs:
    sys.exit(0)  # No reference, no alignment

ref_path = refs[0]

# Load both at reduced resolution for feature matching
def load_gray(path, scale=0.25):
    with rasterio.open(path) as src:
        h, w = int(src.height * scale), int(src.width * scale)
        data = src.read(1, out_shape=(h, w))
        return data, src.transform, src.crs, src.width, src.height

tgt_gray, tgt_tf, tgt_crs, tw, th = load_gray(target)
ref_gray, ref_tf, ref_crs, rw, rh = load_gray(ref_path)

# Feature matching
orb = cv2.ORB_create(5000)
kp1, des1 = orb.detectAndCompute(ref_gray, None)
kp2, des2 = orb.detectAndCompute(tgt_gray, None)

if des1 is None or des2 is None or len(kp1) < 10 or len(kp2) < 10:
    sys.exit(0)

bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
matches = sorted(bf.match(des1, des2), key=lambda m: m.distance)[:50]

if len(matches) < 6:
    sys.exit(0)

# Estimate affine transform
src_pts = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
dst_pts = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
M, inliers = cv2.estimateAffinePartial2D(dst_pts, src_pts, method=cv2.RANSAC, ransacReprojThreshold=5.0)

if M is None or np.sum(inliers) < 4:
    sys.exit(0)

# Check if transform is near-identity (no significant shift)
dx = abs(M[0, 2])
dy = abs(M[1, 2])
if dx < 1 and dy < 1:
    sys.exit(0)  # No significant shift

# Apply transform using rasterio
with rasterio.open(target) as src:
    # Modify the transform by the computed offset (scaled back to full resolution)
    scale = 0.25
    pixel_dx = M[0, 2] / scale
    pixel_dy = M[1, 2] / scale
    geo_dx = pixel_dx * src.transform.a
    geo_dy = pixel_dy * src.transform.e
    new_transform = Affine(
        src.transform.a, src.transform.b, src.transform.c + geo_dx,
        src.transform.d, src.transform.e, src.transform.f + geo_dy,
    )
    profile = src.profile.copy()
    profile.update(transform=new_transform)
    with rasterio.open(output, "w", **profile) as dst:
        for i in range(1, src.count + 1):
            dst.write(src.read(i), i)

print(f"Aligned: dx={{geo_dx:.2f}}m, dy={{geo_dy:.2f}}m")
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

    # Run rebuild on skystore
    script = _build_rebuild_tiles_script(
        tiles_to_rebuild, f"{SKYSTORE_TILES}/missions", f"{SKYSTORE_TILES}/latest"
    )
    _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=1800)

    # Clean up DB records
    OpenSkyTileLayer.objects.filter(mission_id=mission_id).delete()

    logger.info(f"Tile rebuild complete for mission {mission_id[:8]}")


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
        # Regenerate root 3D Tiles tileset (mission removed)
        try:
            from geo.tiles3d_generator import regenerate_root_tileset
            regenerate_root_tileset()
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
ODM_MAX_CONCURRENCY = 8

# Tile settings
TILE_MIN_ZOOM = 13
TILE_MAX_ZOOM = 23
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


def _extract_odm_origin(remote_processing: str) -> dict | None:
    """Extract ODM reconstruction origin from coords.txt on skystore.

    Returns dict with {x, y, z, epsg} or None if not found.
    ODM writes the reconstruction origin (local coordinate system origin) to
    odm_georeferencing/coords.txt in the format: x_offset y_offset z_offset
    These are UTM coordinates.
    """
    try:
        result = _skystore_ssh(
            f"cat {remote_processing}/odm_georeferencing/coords.txt 2>/dev/null || echo NOTFOUND"
        )
        if "NOTFOUND" in result.stdout:
            logger.warning("ODM coords.txt not found — cannot extract origin")
            return None

        # coords.txt format: one line with "x y z" (UTM meters)
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) >= 3:
                origin = {
                    'x': float(parts[0]),
                    'y': float(parts[1]),
                    'z': float(parts[2]),
                }
                logger.info(f"ODM origin: x={origin['x']:.3f} y={origin['y']:.3f} z={origin['z']:.3f}")

                # Read EPSG from proj.txt (needed for UTM→WGS84 conversion)
                try:
                    proj_result = _skystore_ssh(
                        f"cat {remote_processing}/odm_georeferencing/proj.txt 2>/dev/null || echo ''"
                    )
                    proj_str = proj_result.stdout.strip()
                    if proj_str:
                        origin['proj'] = proj_str
                        logger.info(f"ODM proj: {proj_str[:80]}")
                except Exception:
                    pass

                return origin

        return None
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

    # Optimize GLB (Draco + WebP + texture resize)
    opt_path = glb_path.replace('.glb', '_opt.glb')
    result = subprocess.run(
        [GLTF_TRANSFORM_PATH, "optimize", glb_path, opt_path,
         "--compress", "draco", "--texture-compress", "webp",
         "--texture-size", "4096", "--simplify", "false"],
        capture_output=True, text=True, timeout=1800, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gltf-transform optimize failed: {result.stderr[:500]}")

    os.replace(opt_path, glb_path)

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


def apply_satellite_alignment_skystore(mission_id: str):
    """Apply satellite alignment + retile on skystore for a published mission."""
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

        # Check if alignment was applied
        check = _skystore_ssh(f"test -f {r_aligned} && echo aligned || echo identity")
        if "aligned" not in check.stdout:
            logger.info(f"Satellite alignment: no correction needed for {mission_id}")
            return

        # Step 2: Replace ortho
        _skystore_ssh(f"cp {r_aligned} {r_ortho}")

        # Step 3: Retile
        r_tms = f"{r_tmp}/tiles_tms"
        _skystore_ssh(
            f"gdal2tiles.py -z {TILE_MIN_ZOOM}-{TILE_MAX_ZOOM} -w none -r lanczos"
            f" --processes=3 {r_ortho} {r_tms}",
            timeout=3600,
        )

        # Step 4: Convert TMS→XYZ WebP
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

        from geo.models import OpenSkyMission
        mission = OpenSkyMission.objects.get(id=mission_id)
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


def retile_mission_skystore(mission_id: str, zoom_range: str = None):
    """Retile a published mission on skystore from its saved ortho."""
    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission_id}.tif"
    r_tmp = f"{SKYSTORE_FAST_PROCESSING}/_retile_{mission_id}"
    r_tiles_mission = f"{SKYSTORE_TILES}/missions/{mission_id}"
    r_tiles_latest = f"{SKYSTORE_TILES}/latest"

    if not zoom_range:
        zoom_range = f"{TILE_MIN_ZOOM}-{TILE_MAX_ZOOM}"

    try:
        _skystore_ssh(f"mkdir -p {r_tmp}")

        # Generate TMS tiles
        r_tms = f"{r_tmp}/tiles_tms"
        _skystore_ssh(
            f"gdal2tiles.py -z {zoom_range} -w none -r lanczos"
            f" --processes=3 {r_ortho} {r_tms}",
            timeout=7200,
        )

        # Convert TMS→XYZ WebP
        _skystore_ssh(f"mkdir -p {r_tiles_mission}")
        convert_script = _build_tms_to_xyz_webp_script(r_tms, r_tiles_mission, WEBP_QUALITY)
        result = _skystore_ssh(f"python3 -c {shlex.quote(convert_script)}", timeout=3600)

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

    # Update status to PROCESSING
    mission.status = OpenSkyMission.Status.PROCESSING
    mission.processing_started_at = timezone.now()
    mission.processing_step = OpenSkyMission.ProcessingStep.ODM
    mission.save(update_fields=['status', 'processing_started_at', 'processing_step'])
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
        _skystore_ssh(
            f"gdalwarp -t_srs EPSG:3857 -r lanczos -co COMPRESS=LZW -co TILED=YES"
            f" {remote_ortho} {r_reprojected}",
            timeout=1800,
        )
        r_final_ortho = r_reprojected

        # Step 3.5: Align to reference (on skystore via SSH)
        mission.processing_step = OpenSkyMission.ProcessingStep.ALIGNMENT
        mission.save(update_fields=['processing_step'])
        _publish_mission_update(mission.id, {'status': 'PROCESSING', 'processing_step': 'alignment'})
        # Check if reference orthos exist on skystore
        ref_check = _skystore_ssh(f"ls {r_orthos}/*.tif 2>/dev/null | wc -l")
        has_references = int(ref_check.stdout.strip()) > 0

        if has_references:
            logger.info("Step 3.5: Aligning on skystore (reference orthos available)...")
            r_aligned = f"{r_processing}/orthophoto_aligned.tif"
            # Run alignment script on skystore
            align_script = _build_alignment_script(
                mission_id, r_reprojected, r_aligned, r_orthos,
            )
            result = _skystore_ssh(f"python3 -c {shlex.quote(align_script)}", timeout=1800)
            # Check if alignment produced output
            check = _skystore_ssh(f"test -f {r_aligned} && echo aligned || echo identity")
            if "aligned" in check.stdout:
                r_final_ortho = r_aligned
                logger.info("Aligned to reference")
        elif mission.satellite_align:
            logger.info("Step 3.5: Satellite alignment on skystore...")
            r_aligned = f"{r_processing}/orthophoto_aligned.tif"
            sat_script = _build_satellite_alignment_script(r_reprojected, r_aligned, SATELLITE_CACHE_DIR)
            _skystore_ssh(f"python3 -c {shlex.quote(sat_script)}", timeout=1800)
            check = _skystore_ssh(f"test -f {r_aligned} && echo aligned || echo identity")
            if "aligned" in check.stdout:
                r_final_ortho = r_aligned
                logger.info("Satellite-aligned")
        else:
            logger.info("No reference orthos, no satellite alignment requested")

        # Step 3.6: Save orthophoto for future alignment reference
        _skystore_ssh(f"mkdir -p {r_orthos} && cp {r_final_ortho} {r_orthos}/{mission_id}.tif")

        # Step 4: Generate tiles on skystore
        mission.processing_step = OpenSkyMission.ProcessingStep.TILING
        mission.save(update_fields=['processing_step'])
        _publish_mission_update(mission.id, {'status': 'PROCESSING', 'processing_step': 'tiling'})
        logger.info("Step 4: Generating tiles on skystore...")
        r_tms = f"{r_processing}/tiles_tms"
        _skystore_ssh(
            f"gdal2tiles.py -z {TILE_MIN_ZOOM}-{TILE_MAX_ZOOM} -w none -r lanczos"
            f" --processes=3 {r_final_ortho} {r_tms}",
            timeout=3600,
        )

        # Step 4.1: Convert TMS→XYZ WebP on skystore
        logger.info("Step 4.1: Converting to XYZ WebP on skystore...")
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
        _skystore_ssh(f"python3 -c {shlex.quote(latest_script)}", timeout=600)

        # Step 5.2: Record tile contributions in DB for deletion support
        logger.info("Step 5.2: Recording tile contributions...")
        _record_tile_layers(mission_id, r_tiles_mission)

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

                mission.mesh_status = OpenSkyMission.MeshStatus.MESH_READY
                mission.mesh_size_mb = glb_size_mb
                mission.mesh_glb_size_mb = glb_size_mb
                mission.mesh_completed_at = timezone.now()
                mission.mesh_error_message = ''
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
        mission.tiles_count = tiles_count
        mission.tiles_size_mb = round(tiles_size / 1024 / 1024, 2)
        mission.min_zoom = TILE_MIN_ZOOM
        mission.max_zoom = TILE_MAX_ZOOM

        if coverage_polygon:
            mission.area = coverage_polygon

        if bounds:
            mission.center_lat = (bounds[1] + bounds[3]) / 2
            mission.center_lng = (bounds[0] + bounds[2]) / 2

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

        mission.status = OpenSkyMission.Status.FAILED
        mission.processing_step = ''
        mission.error_message = str(e)[:1000]
        mission.save(update_fields=['status', 'processing_step', 'error_message'])
        _publish_mission_update(mission.id, {
            'status': 'FAILED',
            'processing_step': '',
            'error_message': mission.error_message,
        })

        try:
            _skystore_ssh(f"sudo rm -rf {r_processing}")
        except Exception:
            pass

        return False


