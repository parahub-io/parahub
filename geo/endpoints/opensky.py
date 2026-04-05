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
from datetime import datetime

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
import math

logger = logging.getLogger(__name__)

# 1 mission = 1 tile: max allowed distance from tile center to any photo GPS
# ~215m (Z17 half-diagonal) + 37m (buffer) + 68m (GPS error margin) = 320m
MAX_PHOTO_DISTANCE_FROM_TILE_M = 320

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
    area: Optional[Dict[str, Any]]  # GeoJSON polygon
    center_lat: Optional[float]
    center_lng: Optional[float]
    source_photos_count: int
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


class OpenSkyMissionListItem(BaseModel):
    """Simplified mission for list views"""
    id: str
    object_type: str = "opensky_mission"
    name: str
    status: str
    pilot_id: Optional[str]
    pilot_name: Optional[str]
    center_lat: Optional[float]
    center_lng: Optional[float]
    source_photos_count: int
    tiles_count: int
    uploaded_at: datetime
    published_at: Optional[datetime]
    processing_started_at: Optional[datetime] = None
    processing_step: str = ""
    mesh_status: str = "NONE"
    tile_z: Optional[int] = None
    tile_x: Optional[int] = None
    tile_y: Optional[int] = None


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

def _format_opensky_mission(mission, detailed: bool = False) -> dict:
    """Format OpenSkyMission model to response dict"""
    data = {
        'id': mission.id,
        'object_type': 'opensky_mission',
        'name': mission.name or f"Mission {mission.id[:8]}",
        'status': mission.status,
        'pilot_id': mission.pilot_id,
        'pilot_name': mission.pilot.display_name if mission.pilot else None,
        'center_lat': mission.center_lat,
        'center_lng': mission.center_lng,
        'source_photos_count': mission.source_photos_count,
        'tiles_count': mission.tiles_count,
        'uploaded_at': mission.uploaded_at,
        'published_at': mission.published_at,
        'processing_started_at': mission.processing_started_at,
        'processing_step': mission.processing_step or '',
        'mesh_status': mission.mesh_status,
        'satellite_align': mission.satellite_align,
    }

    if detailed:
        data['area'] = None
        if mission.area:
            data['area'] = json.loads(mission.area.geojson)
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


@router.post("/opensky/upload/", auth=ProfileAuth(), response={201: OpenSkyMissionResponse, 400: dict})
@ratelimit(group='opensky:upload', key=user_or_ip, rate='10/m', method='POST')
def upload_opensky_mission(request, name: Form[str] = "", mission_id: Form[str] = "", multi_file: Form[bool] = False, satellite_align: Form[bool] = False):
    """
    Upload drone photos for processing.

    Accepts:
    - Single ZIP archive (field: 'file')
    - Multiple JPG files (field: 'files' - up to 100 per request)

    Max total size per request: 2GB

    Multi-file upload (for better ODM stitching):
    - First batch: omit mission_id, set multi_file=true → creates mission with UPLOADING status
    - Subsequent batches: pass mission_id from first upload → appends to same mission
    - After last batch: call POST /opensky/missions/{id}/finalize/ → sets QUEUED
    """
    from geo.models import OpenSkyMission
    import zipfile
    import os
    import tempfile
    import shutil
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS

    # Get uploaded files - support both 'file' (single/ZIP) and 'files' (multiple JPG)
    uploaded_files = request.FILES.getlist('files')
    if not uploaded_files and 'file' in request.FILES:
        uploaded_files = [request.FILES['file']]

    if not uploaded_files:
        raise HttpError(400, "No files uploaded. Use 'file' (ZIP) or 'files' (JPG) field.")

    # Validate total size (2GB max per request)
    max_size_bytes = 2 * 1024 * 1024 * 1024
    total_size = sum(f.size for f in uploaded_files)
    if total_size > max_size_bytes:
        raise HttpError(400, f"Total size {total_size / 1024 / 1024:.0f}MB exceeds 2GB limit.")

    # Determine upload type: ZIP or direct JPG
    is_zip_upload = len(uploaded_files) == 1 and uploaded_files[0].name.lower().endswith('.zip')
    is_jpg_upload = all(f.name.lower().endswith(('.jpg', '.jpeg')) for f in uploaded_files)

    if not is_zip_upload and not is_jpg_upload:
        raise HttpError(400, "Upload either a single ZIP or multiple JPG/JPEG files.")

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
        # Create new mission
        # Use UPLOADING status for multi-file, QUEUED for single file
        initial_status = OpenSkyMission.Status.UPLOADING if multi_file else OpenSkyMission.Status.QUEUED
        mission = OpenSkyMission.objects.create(
            pilot=request.auth,
            name=name,
            status=initial_status,
            satellite_align=satellite_align,
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

    try:
        photos_count = 0
        total_size = 0
        gps_coords = []  # All extracted GPS points for spread validation

        if is_zip_upload:
            # ZIP upload - extract contents
            uploaded_file = uploaded_files[0]
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_zip = os.path.join(temp_dir, 'upload.zip')
                with open(temp_zip, 'wb') as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)

                if not zipfile.is_zipfile(temp_zip):
                    raise HttpError(400, "Invalid ZIP file.")

                with zipfile.ZipFile(temp_zip, 'r') as zf:
                    for file_info in zf.infolist():
                        if file_info.is_dir() or file_info.filename.startswith('__MACOSX'):
                            continue
                        filename = os.path.basename(file_info.filename)
                        if not filename.lower().endswith(('.jpg', '.jpeg')):
                            continue

                        target_path = os.path.join(images_dir, filename)
                        with zf.open(file_info) as src, open(target_path, 'wb') as dst:
                            shutil.copyfileobj(src, dst)

                        photos_count += 1
                        total_size += file_info.file_size

                        lat, lng = extract_gps(target_path)
                        if lat is not None:
                            gps_coords.append((lat, lng))
        else:
            # Direct JPG upload - save files directly (no ZIP overhead)
            for uploaded_file in uploaded_files:
                filename = uploaded_file.name
                # Ensure unique filename to avoid overwriting
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

        mission.save()

        action = "appended to" if mission_id else "created by"
        upload_type = "ZIP" if is_zip_upload else f"{len(uploaded_files)} JPG"
        logger.info(f"OpenSky mission {mission.id} {action} {request.auth.id}: {photos_count} photos via {upload_type} (+{round(total_size / (1024 * 1024), 2)}MB), total: {mission.source_photos_count} photos")

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

    qs = OpenSkyMission.objects.select_related('pilot')

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
    filtered to the given viewport bounding box.
    """
    from geo.models import OpenSkyMission
    from geo.mission_generator import TILE_ZOOM

    n = 1 << TILE_ZOOM
    x_min = int((west + 180) / 360 * n)
    x_max = int((east + 180) / 360 * n)
    lat_rad_n = math.radians(north)
    lat_rad_s = math.radians(south)
    y_min = int((1 - math.log(math.tan(lat_rad_n) + 1 / math.cos(lat_rad_n)) / math.pi) / 2 * n)
    y_max = int((1 - math.log(math.tan(lat_rad_s) + 1 / math.cos(lat_rad_s)) / math.pi) / 2 * n)

    tiles = list(
        OpenSkyMission.objects.filter(
            status=OpenSkyMission.Status.PUBLISHED,
            tile_z=TILE_ZOOM,
            tile_x__gte=x_min, tile_x__lte=x_max,
            tile_y__gte=y_min, tile_y__lte=y_max,
        )
        .values_list('tile_x', 'tile_y')
        .distinct()
    )

    return {'tiles': [{'x': t[0], 'y': t[1]} for t in tiles]}


@router.get("/opensky/stats/", auth=None, response=OpenSkyStatsResponse)
@ratelimit(group='opensky:stats', key='ip', rate='120/m')
def opensky_stats(request):
    """
    Get OpenSky system statistics.
    """
    from geo.models import OpenSkyMission

    # Count missions by status
    status_counts = dict(
        OpenSkyMission.objects.values('status').annotate(count=Count('id')).values_list('status', 'count')
    )

    # Aggregate stats for published missions
    published_stats = OpenSkyMission.objects.filter(
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

    # For missions with area polygon, calculate bounds
    result = []
    for m in OpenSkyMission.objects.filter(
        status=OpenSkyMission.Status.PUBLISHED
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
