"""
Step 3.4 — satellite alignment (absolute reference): ECC against ESRI World
Imagery z18 tiles. Check-only and apply+retile paths for published missions;
the script builder is also used inline by the pipeline and consolidation.
"""

import logging
import shlex

from django.contrib.gis.geos import Polygon

from .common import _is_superseded
from .constants import (
    ALIGNMENT_MAX_OFFSET_METERS, SATELLITE_CACHE_DIR, SATELLITE_ECC_MIN_CC,
    SATELLITE_TILE_URL, SATELLITE_TILE_ZOOM, SKYSTORE_FAST_PROCESSING,
    SKYSTORE_OPENSKY, SKYSTORE_TILES, TILE_MAX_ZOOM, TILE_MIN_ZOOM,
    WEBP_QUALITY,
)
from .pose_graph import _mark_georef_changed, _write_satellite_anchor
from .remote import _skystore_ssh
from .tiles import (
    _build_coverage_script, _build_tms_to_xyz_webp_script,
    _build_update_latest_script, _clear_self_owned_latest_tiles,
    _record_tile_layers, _z17_tile_bounds_3857, rebuild_overview_latest,
)

logger = logging.getLogger(__name__)


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
