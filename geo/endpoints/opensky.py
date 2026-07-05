"""
OpenSky aerial imagery endpoints (mission upload, tiles, 3D mesh).
"""

from ninja import Router, Form
from ninja.errors import HttpError
from ninja.pagination import paginate, PageNumberPagination
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
import json
import logging
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import datetime

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
import math
import re

logger = logging.getLogger(__name__)

# 1 mission = 1 tile: max allowed distance from tile center to any photo GPS
# ~215m (Z17 half-diagonal) + 37m (buffer) + 68m (GPS error margin) = 320m
MAX_PHOTO_DISTANCE_FROM_TILE_M = 320

# Direction coverage: threshold for a direction to be considered "covered" in UI
# (green pill). Below threshold but > 0 = amber ("partial"). 0 = gray outline.
DIRECTION_COVERAGE_THRESHOLD = 50

# Direction keys used in OpenSkyMission.direction_counts JSON field.
DIRECTION_KEYS = ('nadir', 'n', 'e', 's', 'w', 'unknown')


def extract_gimbal_pitch(image_path):
    """Extract gimbal pitch from DJI XMP metadata. Returns degrees or None."""
    try:
        with open(image_path, 'rb') as f:
            header = f.read(65536)
        match = re.search(rb'(?:drone-dji|drone):GimbalPitchDegree="([^"]+)"', header)
        if match:
            return float(match.group(1))
    except Exception:
        pass
    return None


def extract_gimbal_yaw(image_path):
    """Extract gimbal yaw from DJI XMP metadata. Returns degrees or None.

    DJI reports yaw as 0-360 (north=0, east=90) or -180..180 depending on firmware;
    classify_photo_direction() normalizes via modulo.
    """
    try:
        with open(image_path, 'rb') as f:
            header = f.read(65536)
        match = re.search(rb'(?:drone-dji|drone):GimbalYawDegree="([^"]+)"', header)
        if match:
            return float(match.group(1))
    except Exception:
        pass
    return None


def classify_photo_direction(pitch, yaw):
    """
    Classify a photo by camera direction based on gimbal pitch + yaw.

    Returns one of: 'nadir', 'n', 'e', 's', 'w', 'unknown'

    - nadir: pitch < -70 (straight down, orthophoto source)
    - n/e/s/w: pitch >= -70 (oblique) + yaw bucket (cardinal ±45)
    - unknown: pitch missing, or oblique with yaw missing (legacy EXIF)
    """
    if pitch is None:
        return 'unknown'
    if pitch < -70:
        return 'nadir'
    if yaw is None:
        return 'unknown'
    # Normalize yaw to [0, 360)
    y = yaw % 360
    if y >= 315 or y < 45:
        return 'n'
    if y < 135:
        return 'e'
    if y < 225:
        return 's'
    return 'w'


def empty_direction_counts() -> dict:
    """Zero-initialized direction counts dict."""
    return {k: 0 for k in DIRECTION_KEYS}


router = Router(tags=["Geo / OpenSky"])


# ===== Schemas =====

class OpenSkyMissionResponse(BaseModel):
    """OpenSky mission details"""
    id: str
    object_type: str = "opensky_mission"
    name: str
    status: str
    pilot_id: Optional[str]
    pilot_name: Optional[str]
    pilot_hna: Optional[str] = None
    area: Optional[Dict[str, Any]]  # GeoJSON polygon
    area_m2: Optional[float] = None
    center_lat: Optional[float]
    center_lng: Optional[float]
    place_label: str = ""
    place_region: str = ""
    source_photos_count: int
    direction_counts: Dict[str, int] = {}
    tiles_count: int
    tiles_size_mb: float
    min_zoom: int
    max_zoom: int
    uploaded_at: datetime
    published_at: Optional[datetime]
    error_message: Optional[str]
    processing_started_at: Optional[datetime] = None
    processing_step: str = ""
    mesh_status: str = "NONE"
    mesh_size_mb: float = 0
    mesh_glb_size_mb: float = 0
    mesh_error_message: Optional[str] = None
    mesh_requested_at: Optional[datetime] = None
    mesh_completed_at: Optional[datetime] = None
    satellite_align: bool = False
    tile_z: Optional[int] = None
    tile_x: Optional[int] = None
    tile_y: Optional[int] = None
    license: str = "CC-BY-SA-4.0"


class OpenSkyMissionListItem(BaseModel):
    """Simplified mission for list views"""
    id: str
    object_type: str = "opensky_mission"
    name: str
    status: str
    pilot_id: Optional[str]
    pilot_name: Optional[str]
    pilot_hna: Optional[str] = None
    center_lat: Optional[float]
    center_lng: Optional[float]
    place_label: str = ""
    place_region: str = ""
    area_m2: Optional[float] = None
    source_photos_count: int
    direction_counts: Dict[str, int] = {}
    tiles_count: int
    uploaded_at: datetime
    captured_at: Optional[datetime] = None
    published_at: Optional[datetime]
    processing_started_at: Optional[datetime] = None
    processing_step: str = ""
    mesh_status: str = "NONE"
    tile_z: Optional[int] = None
    tile_x: Optional[int] = None
    tile_y: Optional[int] = None
    license: str = "CC-BY-SA-4.0"


class OpenSkyStatsResponse(BaseModel):
    """OpenSky system statistics"""
    total_missions: int
    published_missions: int
    processing_missions: int
    queued_missions: int
    failed_missions: int
    total_pilots: int
    total_coverage_km2: float
    total_tiles: int
    total_size_gb: float


# ===== Helpers =====

def _mission_area_m2(mission) -> Optional[float]:
    """Geodesic area of the mission footprint polygon, in square metres."""
    if not mission.area:
        return None
    try:
        ring = mission.area.coords[0]  # exterior ring: ((lon, lat), ...)
    except (IndexError, TypeError):
        return None
    if not ring or len(ring) < 4:
        return None
    R = 6378137.0  # WGS84 mean radius
    total = 0.0
    for i in range(len(ring) - 1):
        lon1, lat1 = ring[i][0], ring[i][1]
        lon2, lat2 = ring[i + 1][0], ring[i + 1][1]
        total += math.radians(lon2 - lon1) * (2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2)))
    return abs(total * R * R / 2.0)


def _format_opensky_mission(mission, detailed: bool = False) -> dict:
    """Format OpenSkyMission model to response dict"""
    # Ensure direction_counts always has all keys (frontend iterates them).
    dc = empty_direction_counts()
    for k, v in (mission.direction_counts or {}).items():
        if k in dc:
            dc[k] = int(v)

    data = {
        'id': mission.id,
        'object_type': 'opensky_mission',
        'name': mission.name or f"Mission {mission.id[:8]}",
        'status': mission.status,
        'pilot_id': mission.pilot_id,
        'pilot_name': mission.pilot.display_name if mission.pilot else None,
        'pilot_hna': mission.pilot.hna if mission.pilot else None,
        'center_lat': mission.center_lat,
        'center_lng': mission.center_lng,
        # Place name resolved once at publish (reverse-geo); card reads these directly
        'place_label': mission.place_label,
        'place_region': mission.place_region,
        # Surveyed ground area in m² (cards show ha/km²); polygon itself only in detail
        'area_m2': _mission_area_m2(mission),
        'source_photos_count': mission.source_photos_count,
        'direction_counts': dc,
        'tiles_count': mission.tiles_count,
        'uploaded_at': mission.uploaded_at,
        'captured_at': mission.captured_at,
        'published_at': mission.published_at,
        'processing_started_at': mission.processing_started_at,
        'processing_step': mission.processing_step or '',
        'mesh_status': mission.mesh_status,
        'satellite_align': mission.satellite_align,
        'license': mission.license,
    }

    if detailed:
        data['area'] = json.loads(mission.area.geojson) if mission.area else None
        data['tiles_size_mb'] = mission.tiles_size_mb
        data['min_zoom'] = mission.min_zoom
        data['max_zoom'] = mission.max_zoom
        data['error_message'] = mission.error_message if mission.status == 'FAILED' else None
        data['mesh_size_mb'] = mission.mesh_size_mb
        data['mesh_glb_size_mb'] = mission.mesh_glb_size_mb
        data['mesh_error_message'] = mission.mesh_error_message if mission.mesh_status == 'MESH_FAILED' else None
        data['mesh_requested_at'] = mission.mesh_requested_at
        data['mesh_completed_at'] = mission.mesh_completed_at

    return data


def _validate_tile_spread(gps_coords: list, tile_center_lat: float, tile_center_lng: float) -> Optional[str]:
    """
    Check that all photo GPS coordinates fall within one tile.
    Returns error message if spread is too wide, None if OK.
    """
    if not gps_coords:
        return None

    meters_per_deg_lat = 111320
    meters_per_deg_lng = 111320 * math.cos(math.radians(tile_center_lat))

    max_dist = 0
    for lat, lng in gps_coords:
        dy = (lat - tile_center_lat) * meters_per_deg_lat
        dx = (lng - tile_center_lng) * meters_per_deg_lng
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > max_dist:
            max_dist = dist

    if max_dist > MAX_PHOTO_DISTANCE_FROM_TILE_M:
        return (
            f"Photos span {max_dist:.0f}m from tile center (max {MAX_PHOTO_DISTANCE_FROM_TILE_M}m). "
            f"Upload one tile per mission. Use the tile grid on the map to generate per-tile flight plans."
        )
    return None


# ===== Endpoints =====

@router.get("/opensky/mission/", auth=ProfileAuth())
@ratelimit(group='opensky:generate', key=user_or_ip, rate='10/m')
def generate_opensky_mission(
    request,
    tile_z: Optional[int] = None,
    tile_x: Optional[int] = None,
    tile_y: Optional[int] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    name: Optional[str] = None
):
    """
    Generate ZIP with 2 KMZ flight plans (nadir + oblique) for a single Z17 tile.

    Accepts (tile_z, tile_x, tile_y) or (lat, lng) which is converted to tile.
    Returns: ZIP file with 2 KMZ files + README
    """
    from django.http import HttpResponse
    from geo.mission_generator import generate_tile_zip, calculate_tile_stats, latlng_to_tile, TILE_ZOOM

    if tile_z is not None and tile_x is not None and tile_y is not None:
        n = 2 ** tile_z
        if not (10 <= tile_z <= 20):
            raise HttpError(400, "tile_z must be between 10 and 20")
        if not (0 <= tile_x < n):
            raise HttpError(400, f"tile_x must be between 0 and {n - 1}")
        if not (0 <= tile_y < n):
            raise HttpError(400, f"tile_y must be between 0 and {n - 1}")
    elif lat is not None and lng is not None:
        if not (-90 <= lat <= 90):
            raise HttpError(400, "Latitude must be between -90 and 90")
        if not (-180 <= lng <= 180):
            raise HttpError(400, "Longitude must be between -180 and 180")
        tile_z = TILE_ZOOM
        tile_x, tile_y = latlng_to_tile(lat, lng, tile_z)
    else:
        raise HttpError(400, "Provide (tile_z, tile_x, tile_y) or (lat, lng)")

    base_name = name or f"OpenSky_Z{tile_z}_{tile_x}_{tile_y}"
    zip_data = generate_tile_zip(tile_z, tile_x, tile_y, base_name)

    stats = calculate_tile_stats(tile_z, tile_x, tile_y)
    logger.info(f"Generated OpenSky tile mission for {request.auth.id}: Z{tile_z}/{tile_x}/{tile_y}, {stats['total_time_min']} min")

    response = HttpResponse(zip_data, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{base_name}.zip"'
    return response


@router.get("/opensky/mission/preview/", auth=ProfileAuth())
@ratelimit(group='opensky:preview', key=user_or_ip, rate='60/m')
def preview_opensky_mission(
    request,
    tile_z: Optional[int] = None,
    tile_x: Optional[int] = None,
    tile_y: Optional[int] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
):
    """Preview single tile mission statistics without generating files."""
    from geo.mission_generator import calculate_tile_stats, latlng_to_tile, TILE_ZOOM

    if tile_z is not None and tile_x is not None and tile_y is not None:
        n = 2 ** tile_z
        if not (10 <= tile_z <= 20):
            raise HttpError(400, "tile_z must be between 10 and 20")
        if not (0 <= tile_x < n):
            raise HttpError(400, f"tile_x must be between 0 and {n - 1}")
        if not (0 <= tile_y < n):
            raise HttpError(400, f"tile_y must be between 0 and {n - 1}")
    elif lat is not None and lng is not None:
        if not (-90 <= lat <= 90):
            raise HttpError(400, "Latitude must be between -90 and 90")
        if not (-180 <= lng <= 180):
            raise HttpError(400, "Longitude must be between -180 and 180")
        tile_z = TILE_ZOOM
        tile_x, tile_y = latlng_to_tile(lat, lng, tile_z)
    else:
        raise HttpError(400, "Provide (tile_z, tile_x, tile_y) or (lat, lng)")

    return calculate_tile_stats(tile_z, tile_x, tile_y)


@router.get("/opensky/reachability/", auth=ProfileAuth())
@ratelimit(group='opensky:reach', key=user_or_ip, rate='30/m')
def opensky_reachability(
    request,
    lat: float,
    lng: float,
    agl: float = 100,
    margin: float = 30,
    radius_m: float = 2000,
    rc_height: float = 2,
):
    """Drone reachability from a launch point: classify Z17 tiles by
    range + terrain ceiling + RC line-of-sight. SRTM via Valhalla /height.
    Planning aid only — NOT collision-avoidance (see geo/drone_reach.py)."""
    from geo.drone_reach import compute_reachability

    if not (-90 <= lat <= 90):
        raise HttpError(400, "Latitude must be between -90 and 90")
    if not (-180 <= lng <= 180):
        raise HttpError(400, "Longitude must be between -180 and 180")

    try:
        return compute_reachability(lat, lng, agl=agl, margin=margin,
                                    radius_m=radius_m, rc_height=rc_height)
    except ValueError as e:
        raise HttpError(400, str(e))
    except RuntimeError as e:
        raise HttpError(503, str(e))


# Whole national dataset is small (~hundreds of zones); cap defensively anyway.
DRONE_ZONES_MAX = 1000


@router.get("/opensky/drone-zones/", auth=ProfileAuth())
@ratelimit(group='opensky:zones', key=user_or_ip, rate='60/m')
def opensky_drone_zones(
    request,
    min_lng: float,
    min_lat: float,
    max_lng: float,
    max_lat: float,
):
    """UAS geographical zones (ED-269) intersecting a bbox, as GeoJSON for the
    map overlay. Source: national authority import (e.g. ANAC PT). Returns both
    prohibited and advisory (authorisation/conditional) zones; informational
    NO_RESTRICTION zones are omitted. Planning aid — NOTAM / temporary
    restrictions are NOT included."""
    from django.contrib.gis.geos import Polygon as GEOSPolygon
    from geo.models import DroneZone

    if not (-180 <= min_lng <= max_lng <= 180) or not (-90 <= min_lat <= max_lat <= 90):
        raise HttpError(400, "Invalid bbox (need min_lng<=max_lng, min_lat<=max_lat, in range)")

    bbox = GEOSPolygon.from_bbox((min_lng, min_lat, max_lng, max_lat))
    bbox.srid = 4326

    qs = (
        DroneZone.objects
        .filter(geometry__intersects=bbox)
        .exclude(restriction=DroneZone.Restriction.NO_RESTRICTION)
        .order_by('restriction')[:DRONE_ZONES_MAX]
    )

    features = []
    for z in qs:
        features.append({
            "type": "Feature",
            "geometry": json.loads(z.geometry.geojson),
            "properties": {
                "id": z.zone_identifier,
                "name": z.name,
                "restriction": z.restriction,
                "reason": z.reason,
                "lower_m": z.lower_limit_m,
                "upper_m": z.upper_limit_m,
                "lower_ref": z.lower_ref,
                "upper_ref": z.upper_ref,
                "message": z.message,
                "color": (z.attributes or {}).get("color"),
            },
        })

    return {"type": "FeatureCollection", "features": features, "count": len(features)}


@router.post("/opensky/upload/", auth=ProfileAuth(), response={201: OpenSkyMissionResponse, 400: dict})
@ratelimit(group='opensky:upload', key=user_or_ip, rate='10/m', method='POST')
def upload_opensky_mission(request, name: Form[str] = "", mission_id: Form[str] = "", multi_file: Form[bool] = False, license_consent: Form[bool] = False):
    """
    Upload drone photos (JPG only) for processing.

    Multi-file upload:
    - First batch: omit mission_id, set multi_file=true → creates mission with UPLOADING status
    - Subsequent batches: pass mission_id from first upload → appends to same mission
    - After last batch: call POST /opensky/missions/{id}/finalize/ → sets QUEUED

    Licensing: uploaded imagery (and derived ortho/mesh/tiles) is published under
    CC BY-SA 4.0. Creating a new mission requires license_consent=true; appends to an
    existing mission inherit the consent given at creation.
    """
    from geo.models import OpenSkyMission
    import os
    import shutil
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS

    # Get uploaded JPG files
    uploaded_files = request.FILES.getlist('files')
    if not uploaded_files:
        raise HttpError(400, "No files uploaded. Use 'files' field with JPG photos.")

    # Validate all are JPG
    for f in uploaded_files:
        if not f.name.lower().endswith(('.jpg', '.jpeg')):
            raise HttpError(400, f"{f.name}: Only JPG/JPEG files are accepted.")

    # Validate total size (frontend batches at 50 files / 500MB, allow margin)
    total_size_bytes = sum(f.size for f in uploaded_files)
    if total_size_bytes > 700 * 1024 * 1024:
        raise HttpError(400, f"Batch too large ({total_size_bytes // (1024*1024)}MB). Max 50 files / 500MB per batch.")

    # Multi-file upload: append to existing mission
    if mission_id:
        try:
            mission = OpenSkyMission.objects.get(id=mission_id)
        except OpenSkyMission.DoesNotExist:
            raise HttpError(404, "Mission not found.")

        # Verify ownership
        if mission.pilot_id != request.auth.id:
            raise HttpError(403, "Not your mission.")

        # Allow appending to UPLOADING or PUBLISHED missions (e.g. adding oblique photos)
        if mission.status not in (OpenSkyMission.Status.UPLOADING, OpenSkyMission.Status.PUBLISHED):
            raise HttpError(400, "Can only add photos to missions in UPLOADING or PUBLISHED status.")

        # PUBLISHED → UPLOADING (will be reprocessed after finalize)
        if mission.status == OpenSkyMission.Status.PUBLISHED:
            mission.status = OpenSkyMission.Status.UPLOADING
            mission.save(update_fields=['status'])
    else:
        # New mission: pilot must accept the imagery license (CC BY-SA 4.0).
        if not license_consent:
            raise HttpError(400, "Imagery license consent required: imagery is published under CC BY-SA 4.0.")

        # Create new mission
        # Use UPLOADING status for multi-file, QUEUED for single file
        initial_status = OpenSkyMission.Status.UPLOADING if multi_file else OpenSkyMission.Status.QUEUED
        mission = OpenSkyMission.objects.create(
            pilot=request.auth,
            name=name,
            status=initial_status,
            license_consent_at=timezone.now(),
        )

    # Create directory structure
    images_dir = f"/mnt/opensky/missions/{mission.id}/images"
    os.makedirs(images_dir, exist_ok=True)

    def extract_gps(image_path):
        """Extract GPS coordinates from image EXIF."""
        try:
            img = Image.open(image_path)
            exif_data = img._getexif()
            if exif_data:
                gps_info = {}
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == 'GPSInfo':
                        for gps_tag_id, gps_value in value.items():
                            gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                            gps_info[gps_tag] = gps_value

                if 'GPSLatitude' in gps_info and 'GPSLongitude' in gps_info:
                    lat = gps_info['GPSLatitude']
                    lng = gps_info['GPSLongitude']
                    lat_deg = float(lat[0]) + float(lat[1])/60 + float(lat[2])/3600
                    lng_deg = float(lng[0]) + float(lng[1])/60 + float(lng[2])/3600
                    if gps_info.get('GPSLatitudeRef') == 'S':
                        lat_deg = -lat_deg
                    if gps_info.get('GPSLongitudeRef') == 'W':
                        lng_deg = -lng_deg
                    return lat_deg, lng_deg
            img.close()
        except Exception as e:
            logger.debug(f"Could not extract EXIF from {image_path}: {e}")
        return None, None

    def extract_capture_date(image_path):
        """Extract DateTimeOriginal from EXIF. Returns datetime or None."""
        try:
            img = Image.open(image_path)
            exif_data = img._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == 'DateTimeOriginal':
                        from datetime import datetime as _dt
                        return _dt.strptime(value, '%Y:%m:%d %H:%M:%S')
            img.close()
        except Exception:
            pass
        return None

    try:
        photos_count = 0
        total_size = 0
        gps_coords = []
        capture_dates = []
        # Per-batch direction counts (merged into mission.direction_counts after loop)
        batch_direction_counts = empty_direction_counts()

        for uploaded_file in uploaded_files:
            filename = uploaded_file.name
            target_path = os.path.join(images_dir, filename)
            counter = 1
            while os.path.exists(target_path):
                name, ext = os.path.splitext(filename)
                target_path = os.path.join(images_dir, f"{name}_{counter}{ext}")
                counter += 1

            with open(target_path, 'wb') as f:
                for chunk in uploaded_file.chunks():
                    f.write(chunk)

            photos_count += 1
            total_size += uploaded_file.size

            lat, lng = extract_gps(target_path)
            if lat is not None:
                gps_coords.append((lat, lng))

            # Sample capture date from first few photos only (EXIF read is slow)
            if len(capture_dates) < 3:
                cdate = extract_capture_date(target_path)
                if cdate:
                    capture_dates.append(cdate)

            # Classify photo direction from gimbal pitch + yaw
            pitch = extract_gimbal_pitch(target_path)
            yaw = extract_gimbal_yaw(target_path)
            direction = classify_photo_direction(pitch, yaw)
            batch_direction_counts[direction] += 1

        if photos_count == 0:
            if not mission_id and mission.source_photos_count == 0:
                shutil.rmtree(f"/mnt/opensky/missions/{mission.id}", ignore_errors=True)
                mission.delete()
            raise HttpError(400, "No JPG/JPEG images found.")

        # Validate geographic spread: 1 mission = 1 tile
        if gps_coords:
            from geo.mission_generator import latlng_to_tile, tile_center, TILE_ZOOM
            avg_lat = sum(c[0] for c in gps_coords) / len(gps_coords)
            avg_lng = sum(c[1] for c in gps_coords) / len(gps_coords)

            if mission_id and mission.center_lat is not None:
                tx, ty = latlng_to_tile(mission.center_lat, mission.center_lng, TILE_ZOOM)
            else:
                tx, ty = latlng_to_tile(avg_lat, avg_lng, TILE_ZOOM)

            tc_lat, tc_lng = tile_center(TILE_ZOOM, tx, ty)
            spread_error = _validate_tile_spread(gps_coords, tc_lat, tc_lng)
            if spread_error:
                # Clean up uploaded files on rejection
                if not mission_id and mission.source_photos_count == 0:
                    shutil.rmtree(f"/mnt/opensky/missions/{mission.id}", ignore_errors=True)
                    mission.delete()
                raise HttpError(400, spread_error)

        # Update mission with stats (append for multi-file)
        mission.source_photos_count += photos_count
        mission.source_photos_size_mb = round(mission.source_photos_size_mb + total_size / (1024 * 1024), 2)

        if gps_coords:
            avg_lat = sum(c[0] for c in gps_coords) / len(gps_coords)
            avg_lng = sum(c[1] for c in gps_coords) / len(gps_coords)
            if mission_id and mission.center_lat is not None:
                # Multi-file: recalculate from all coords (existing center weighted by count)
                existing_weight = mission.source_photos_count - photos_count
                if existing_weight > 0:
                    avg_lat = (mission.center_lat * existing_weight + avg_lat * len(gps_coords)) / (existing_weight + len(gps_coords))
                    avg_lng = (mission.center_lng * existing_weight + avg_lng * len(gps_coords)) / (existing_weight + len(gps_coords))
            mission.center_lat = avg_lat
            mission.center_lng = avg_lng
            # Assign tile for fog-of-war tracking
            from geo.mission_generator import latlng_to_tile, TILE_ZOOM
            mission.tile_z = TILE_ZOOM
            mission.tile_x, mission.tile_y = latlng_to_tile(mission.center_lat, mission.center_lng, TILE_ZOOM)
            # Auto-generate name from tile coords (e.g. "62484x48643").
            # Regenerate if the current name looks like an auto-pattern — the
            # weighted-center recalculation across multi-file batches can shift
            # tile_x/tile_y by ±1, and we want the name to track the tile.
            # User-provided names (anything not matching the pattern) are kept.
            if not mission.name or re.fullmatch(r'\d+x\d+', mission.name):
                mission.name = f"{mission.tile_x}x{mission.tile_y}"

        # Set captured_at from earliest EXIF date (first upload batch only)
        if capture_dates and not mission.captured_at:
            from django.utils.timezone import make_aware
            earliest = min(capture_dates)
            mission.captured_at = make_aware(earliest) if earliest.tzinfo is None else earliest

        # Nadir-presence check happens at finalize (see finalize_opensky_mission),
        # not per-batch — multi-batch uploads may have nadir photos in any batch
        # depending on file order (often last, if shot in a separate flight).

        # Merge per-batch counts into mission.direction_counts (additive across batches)
        existing = mission.direction_counts or {}
        merged = empty_direction_counts()
        for k in DIRECTION_KEYS:
            merged[k] = int(existing.get(k, 0)) + batch_direction_counts[k]
        mission.direction_counts = merged

        mission.save()

        action = "appended to" if mission_id else "created by"
        logger.info(f"OpenSky mission {mission.id} {action} {request.auth.id}: {photos_count} photos ({len(uploaded_files)} files, +{round(total_size / (1024 * 1024), 2)}MB), total: {mission.source_photos_count} photos")

        return 201, _format_opensky_mission(mission, detailed=True)

    except HttpError:
        raise
    except Exception as e:
        logger.error(f"Error processing OpenSky upload: {e}", exc_info=True)
        if not mission_id:
            shutil.rmtree(f"/mnt/opensky/missions/{mission.id}", ignore_errors=True)
            mission.delete()
        raise HttpError(500, "Error processing upload. Please try again.")


@router.post("/opensky/missions/{mission_id}/finalize/", auth=ProfileAuth(), response={200: OpenSkyMissionResponse, 400: dict})
@ratelimit(group='opensky:finalize', key=user_or_ip, rate='10/m', method='POST')
def finalize_opensky_mission(request, mission_id: str):
    """
    Finalize multi-file upload mission: UPLOADING → QUEUED.

    Call this after uploading all ZIP files to start processing.
    """
    from geo.models import OpenSkyMission

    try:
        mission = OpenSkyMission.objects.get(id=mission_id)
    except OpenSkyMission.DoesNotExist:
        raise HttpError(404, "Mission not found.")

    # Verify ownership
    if mission.pilot_id != request.auth.id:
        raise HttpError(403, "Not your mission.")

    # Only allow finalizing UPLOADING missions
    if mission.status != OpenSkyMission.Status.UPLOADING:
        raise HttpError(400, f"Mission is {mission.status}, not UPLOADING.")

    # Verify we have photos
    if mission.source_photos_count == 0:
        raise HttpError(400, "Mission has no photos. Upload at least one ZIP first.")

    # Fool-proofing: reject oblique-only missions (no nadir base).
    # ODM needs nadir photos as the geometric anchor; oblique-only inputs typically
    # fail reconstruction or produce garbage. Mission is preserved so the user can
    # append nadir photos and re-finalize.
    counts = mission.direction_counts or {}
    classified = sum(int(counts.get(k, 0)) for k in ('nadir', 'n', 'e', 's', 'w'))
    if classified > 0 and int(counts.get('nadir', 0)) == 0:
        raise HttpError(400,
            "This mission has only oblique (angled) photos. "
            "Upload nadir (straight-down) photos and try again — "
            "ODM needs them as the geometric anchor."
        )

    # Set to QUEUED for processing
    mission.status = OpenSkyMission.Status.QUEUED
    mission.save(update_fields=['status'])

    logger.info(f"OpenSky mission {mission.id} finalized by {request.auth.id}: {mission.source_photos_count} photos ready for processing")

    return 200, _format_opensky_mission(mission, detailed=True)


@router.get("/opensky/missions/", auth=None, response=List[OpenSkyMissionListItem])
@ratelimit(group='opensky:list', key='ip', rate='120/m')
@paginate(PageNumberPagination, page_size=20)
def list_opensky_missions(
    request,
    status: Optional[str] = None,
    pilot_id: Optional[str] = None,
    year: Optional[int] = None
):
    """
    List OpenSky missions with filters.

    Filters:
    - status: QUEUED, PROCESSING, PUBLISHED, FAILED
    - pilot_id: Filter by pilot profile ID
    - year: Filter by upload year
    """
    from geo.models import OpenSkyMission

    # Consolidations are synthetic super-tile rows, not flights — never list them.
    qs = OpenSkyMission.objects.select_related('pilot').filter(is_consolidation=False)

    # Default to PUBLISHED only for public view
    if status:
        qs = qs.filter(status=status)
    else:
        qs = qs.filter(status=OpenSkyMission.Status.PUBLISHED)

    if pilot_id:
        qs = qs.filter(pilot_id=pilot_id)

    if year:
        qs = qs.filter(uploaded_at__year=year)

    qs = qs.order_by('-published_at', '-uploaded_at')

    return [_format_opensky_mission(m) for m in qs]


@router.get("/opensky/missions/me/", auth=ProfileAuth(), response=List[OpenSkyMissionListItem])
@ratelimit(group='opensky:my_missions', key=user_or_ip, rate='60/m')
def my_opensky_missions(request):
    """Get current user's OpenSky missions (all statuses)."""
    from geo.models import OpenSkyMission

    qs = OpenSkyMission.objects.filter(
        pilot=request.auth
    ).order_by('-uploaded_at')

    return [_format_opensky_mission(m) for m in qs]


@router.get("/opensky/missions/{mission_id}/", auth=None, response=OpenSkyMissionResponse)
@ratelimit(group='opensky:detail', key='ip', rate='120/m')
def get_opensky_mission(request, mission_id: str):
    """Get OpenSky mission details."""
    from geo.models import OpenSkyMission

    mission = get_object_or_404(
        OpenSkyMission.objects.select_related('pilot'),
        id=mission_id
    )

    return _format_opensky_mission(mission, detailed=True)


@router.delete("/opensky/missions/{mission_id}/", auth=ProfileAuth())
@ratelimit(group='opensky:delete', key=user_or_ip, rate='10/m', method='DELETE')
def delete_opensky_mission(request, mission_id: str):
    """
    Delete OpenSky mission.
    Only owner or admin can delete.
    Rebuilds affected tiles in latest/ from remaining missions.
    """
    from geo.models import OpenSkyMission
    from geo.opensky_processor import rebuild_tiles_after_deletion, delete_skystore_mission_files

    mission = get_object_or_404(OpenSkyMission, id=mission_id)

    # Check permissions
    is_owner = mission.pilot_id == request.auth.id
    is_admin = request.auth.account.is_superuser

    if not is_owner and not is_admin:
        raise HttpError(403, "Only owner or admin can delete mission")

    # Don't allow deleting missions currently being processed
    if mission.status == OpenSkyMission.Status.PROCESSING:
        raise HttpError(400, "Cannot delete mission while processing")

    # Block deleting a mission that is a member of a consolidation — its photos
    # are still needed to re-consolidate, and its tiles back the super-tile's
    # union edges. Delete the consolidation first (which frees its members).
    if mission.superseded_by_id:
        raise HttpError(400, "Mission is part of a consolidation; delete the consolidation first")

    # Rebuild affected tiles in latest/ on skystore BEFORE deleting files
    try:
        rebuild_tiles_after_deletion(mission_id)
    except Exception as e:
        logger.error(f"Error rebuilding tiles after deletion: {e}")

    # Cleanup files on skystore (images, ortho, tiles, mesh)
    try:
        delete_skystore_mission_files(mission_id)
    except Exception as e:
        logger.error(f"Error cleaning up skystore files: {e}")

    mission.delete()
    logger.info(f"OpenSky mission {mission_id} deleted by {request.auth.id}")

    return {"success": True, "message": "Mission deleted"}


@router.get("/opensky/missions/{mission_id}/mesh/download/", auth=ProfileAuth())
@ratelimit(group='opensky:download_mesh', key=user_or_ip, rate='30/m')
def download_opensky_mesh(request, mission_id: str):
    """
    Download optimized 3D mesh GLB file.
    Only the mission pilot can download.
    Uses X-Accel-Redirect for Nginx to serve the file.
    """
    from django.http import HttpResponse as DjangoHttpResponse
    from geo.models import OpenSkyMission

    mission = get_object_or_404(OpenSkyMission, id=mission_id)

    if mission.pilot_id != request.auth.id:
        raise HttpError(403, "Only mission pilot can download mesh")

    if mission.mesh_status != OpenSkyMission.MeshStatus.MESH_READY:
        raise HttpError(404, "Mesh not available")

    response = DjangoHttpResponse()
    response['X-Accel-Redirect'] = f"/opensky-mesh-accel/{mission_id}/model.glb"
    response['Content-Type'] = 'model/gltf-binary'
    response['Content-Disposition'] = f'attachment; filename="mesh_{mission_id[:8]}.glb"'
    return response


@router.get("/opensky/missions/{mission_id}/mesh/model.glb", auth=ProfileAuth())
@ratelimit(group='opensky:mesh_glb', key=user_or_ip, rate='60/m')
def get_opensky_mesh_glb(request, mission_id: str):
    """
    Serve 3D mesh GLB file for browser viewer.
    Only the mission pilot can access.
    Uses X-Accel-Redirect for Nginx to serve the file.
    """
    from django.http import HttpResponse as DjangoHttpResponse
    from geo.models import OpenSkyMission

    mission = get_object_or_404(OpenSkyMission, id=mission_id)

    if mission.pilot_id != request.auth.id:
        raise HttpError(403, "Only mission pilot can view mesh")

    if mission.mesh_status != OpenSkyMission.MeshStatus.MESH_READY:
        raise HttpError(404, "Mesh not available")

    response = DjangoHttpResponse()
    response['X-Accel-Redirect'] = f"/opensky-mesh-accel/{mission_id}/model.glb"
    response['Content-Type'] = 'model/gltf-binary'
    return response


@router.post("/opensky/missions/{mission_id}/satellite-align/", auth=ProfileAuth())
@ratelimit(group='opensky:satellite_align', key=user_or_ip, rate='10/m', method='POST')
def satellite_align_opensky_mission(request, mission_id: str, action: str = "check"):
    """
    Satellite alignment for a published mission.

    Actions:
    - check: compute offset (~10s), return {offset, dx, dy, cc}
    - apply: apply correction + retile in background
    """
    from geo.models import OpenSkyMission
    from geo.opensky_processor import (
        check_satellite_alignment_skystore, apply_satellite_alignment_skystore,
        SKYSTORE_OPENSKY, _skystore_ssh,
    )
    import subprocess

    mission = get_object_or_404(OpenSkyMission, id=mission_id)

    if mission.pilot_id != request.auth.id:
        raise HttpError(403, "Only mission pilot can align")

    if mission.status != OpenSkyMission.Status.PUBLISHED:
        raise HttpError(400, "Mission must be published")

    # Verify ortho exists on skystore
    ortho_path = f"{SKYSTORE_OPENSKY}/orthos/{mission.id}.tif"
    try:
        result = _skystore_ssh(f"test -f {ortho_path} && echo ok")
        if "ok" not in result.stdout:
            raise HttpError(400, "Orthophoto not found on skystore")
    except subprocess.CalledProcessError:
        raise HttpError(400, "Orthophoto not found on skystore")

    if action == "check":
        return check_satellite_alignment_skystore(mission_id)

    elif action == "apply":
        # Run in background via management command
        subprocess.Popen(
            ["python3", "manage.py", "realign_opensky_satellite", f"--mission={mission_id}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        mission.satellite_align = True
        mission.save(update_fields=['satellite_align'])
        logger.info(f"Satellite alignment apply triggered for mission {mission_id}")
        return {"success": True, "message": "Satellite alignment started"}

    raise HttpError(400, f"Unknown action: {action}")


@router.get("/opensky/covered-tiles/", auth=None)
@ratelimit(group='opensky:covered', key='ip', rate='120/m')
def get_opensky_covered_tiles(request, west: float, south: float, east: float, north: float):
    """
    Return Z17 tile coordinates that have at least one PUBLISHED mission,
    filtered to the given viewport bounding box. Each tile carries its survey
    date(s) (up to the 3 most recent distinct dates, ascending) and the total
    mission count, for the mission-planning grid label.

    Consolidations have NULL tile coords (tile_z != TILE_ZOOM) so they are
    excluded automatically — count reflects real flights, not super-tiles.
    """
    from collections import defaultdict
    from django.utils import timezone
    from geo.models import OpenSkyMission
    from geo.mission_generator import TILE_ZOOM

    n = 1 << TILE_ZOOM
    x_min = int((west + 180) / 360 * n)
    x_max = int((east + 180) / 360 * n)
    lat_rad_n = math.radians(north)
    lat_rad_s = math.radians(south)
    y_min = int((1 - math.log(math.tan(lat_rad_n) + 1 / math.cos(lat_rad_n)) / math.pi) / 2 * n)
    y_max = int((1 - math.log(math.tan(lat_rad_s) + 1 / math.cos(lat_rad_s)) / math.pi) / 2 * n)

    rows = (
        OpenSkyMission.objects.filter(
            status=OpenSkyMission.Status.PUBLISHED,
            tile_z=TILE_ZOOM,
            tile_x__gte=x_min, tile_x__lte=x_max,
            tile_y__gte=y_min, tile_y__lte=y_max,
        )
        .values_list('tile_x', 'tile_y', 'captured_at', 'uploaded_at')
    )

    # Aggregate per tile: total mission count + distinct survey dates.
    # Survey date = earliest-photo EXIF (captured_at); fall back to the upload
    # date for legacy missions whose EXIF date was never extracted (uploaded_at
    # is auto_now_add, so always present).
    agg = defaultdict(lambda: {'count': 0, 'dates': set()})
    for tx, ty, captured_at, uploaded_at in rows:
        bucket = agg[(tx, ty)]
        bucket['count'] += 1
        when = captured_at or uploaded_at
        if when:
            bucket['dates'].add(timezone.localtime(when).date().isoformat())

    tiles = [
        {
            'x': tx,
            'y': ty,
            'count': bucket['count'],
            # Most recent 3 distinct dates, ascending (oldest of the three first).
            'dates': sorted(bucket['dates'])[-3:],
        }
        for (tx, ty), bucket in agg.items()
    ]

    return {'tiles': tiles}


@router.get("/opensky/stats/", auth=None, response=OpenSkyStatsResponse)
@ratelimit(group='opensky:stats', key='ip', rate='120/m')
def opensky_stats(request):
    """
    Get OpenSky system statistics.
    """
    from geo.models import OpenSkyMission

    # Exclude consolidations everywhere — they are synthetic super-tiles that
    # overlap their member flights; counting them would double-count missions,
    # tiles, and coverage. Real flown coverage = the member/normal missions.
    flights = OpenSkyMission.objects.filter(is_consolidation=False)

    # Count missions by status
    status_counts = dict(
        flights.values('status').annotate(count=Count('id')).values_list('status', 'count')
    )

    # Aggregate stats for published missions
    published_stats = flights.filter(
        status=OpenSkyMission.Status.PUBLISHED
    ).aggregate(
        total_tiles=Sum('tiles_count'),
        total_size_mb=Sum('tiles_size_mb')
    )

    # Count unique pilots
    total_pilots = OpenSkyMission.objects.exclude(
        pilot__isnull=True
    ).values('pilot').distinct().count()

    # Calculate total coverage (rough estimate from mission count * avg area)
    # Each mission covers ~0.0625 km² (250m x 250m)
    published_count = status_counts.get('PUBLISHED', 0)
    total_coverage_km2 = published_count * 0.0625

    return OpenSkyStatsResponse(
        total_missions=sum(status_counts.values()),
        published_missions=status_counts.get('PUBLISHED', 0),
        processing_missions=status_counts.get('PROCESSING', 0),
        queued_missions=status_counts.get('QUEUED', 0),
        failed_missions=status_counts.get('FAILED', 0),
        total_pilots=total_pilots,
        total_coverage_km2=round(total_coverage_km2, 2),
        total_tiles=published_stats['total_tiles'] or 0,
        total_size_gb=round((published_stats['total_size_mb'] or 0) / 1024, 2)
    )


@router.get("/opensky/tiles/{z}/{x}/{y}.webp", auth=None)
@ratelimit(group='opensky:tile', key='ip', rate='600/m')
def get_opensky_tile(request, z: int, x: int, y: int, year: int = None, pilot_id: str = None, mission_id: str = None):
    """
    Proxy for OpenSky tiles with filtering support.

    Without filters (year, pilot_id, mission_id):
    - Nginx proxies to skystore latest/ via WireGuard (fast!)
    - This endpoint is not reached

    With filters:
    - Django finds matching mission and returns X-Accel-Redirect
    - mission_id: show tiles from specific mission only
    - year: filter by upload year
    - pilot_id: filter by pilot
    """
    from django.http import HttpResponse
    from geo.models import OpenSkyMission

    # Build filter query
    qs = OpenSkyMission.objects.filter(status=OpenSkyMission.Status.PUBLISHED)

    if mission_id:
        qs = qs.filter(id=mission_id)

    if year:
        qs = qs.filter(uploaded_at__year=year)

    if pilot_id:
        qs = qs.filter(pilot_id=pilot_id)

    # Get most recent matching mission
    mission = qs.order_by('-published_at').first()

    if not mission:
        return HttpResponse(status=404)

    # Use X-Accel-Redirect for Nginx to serve the file
    response = HttpResponse()
    response['X-Accel-Redirect'] = f"/opensky-accel/{mission.id}/{z}/{x}/{y}.webp"
    response['Content-Type'] = 'image/webp'
    return response


@router.get("/opensky/published-bounds/", auth=None)
@ratelimit(group='opensky:bounds', key='ip', rate='120/m')
def get_opensky_published_bounds(request):
    """
    Get list of published mission bounds for map layer.
    Returns minimal data for efficient tile source configuration.
    """
    from geo.models import OpenSkyMission

    # For missions with area polygon, calculate bounds.
    # Exclude missions superseded by a consolidation — their seamless super-tile
    # (itself a PUBLISHED is_consolidation row, superseded_by=NULL) carries the
    # bounds instead, so the map renders the joint ortho over the members.
    result = []
    for m in OpenSkyMission.objects.filter(
        status=OpenSkyMission.Status.PUBLISHED,
        superseded_by__isnull=True,
    ).only('id', 'min_zoom', 'max_zoom', 'area', 'center_lat', 'center_lng'):
        bounds = None
        if m.area:
            extent = m.area.extent  # (xmin, ymin, xmax, ymax)
            bounds = [extent[0], extent[1], extent[2], extent[3]]
        elif m.center_lat and m.center_lng:
            # Approximate bounds from center (250m square)
            half_deg = 0.00125  # ~125m in degrees at equator
            bounds = [
                m.center_lng - half_deg,
                m.center_lat - half_deg,
                m.center_lng + half_deg,
                m.center_lat + half_deg
            ]

        if bounds:
            result.append({
                'id': m.id,
                'bounds': bounds,
                'minzoom': m.min_zoom,
                'maxzoom': m.max_zoom
            })

    return {'missions': result}
