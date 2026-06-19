"""
OpenSky Mission Generator — WPML flight plans for drone aerial survey.

Uses standard Web Mercator tiles (Z/X/Y) at zoom 17 (~305×240m per tile).
Each tile generates 5 KMZ — pilot flies as many as budget allows:

    1_2D.kmz    — nadir (gimbal -90°)   — orthophoto (always fly)
    2_3D-N.kmz  — oblique, camera North — captures south-facing walls
    3_3D-E.kmz  — oblique, camera East  — captures west-facing walls
    4_3D-S.kmz  — oblique, camera South — captures north-facing walls
    5_3D-W.kmz  — oblique, camera West  — captures east-facing walls

Flight budget ramp (monotonic quality, each battery adds one wall direction):
    1 battery  → 1        — ortho only, no 3D
    3 batteries → 1+2+3   — 2 of 4 facades (diagonal, south + west) — baseline 3D
    5 batteries → 1..5    — all 4 facades — ultra 3D

The ordering N→E→S→W is chosen so that the 3-battery subset (N+E) gives
orthogonal facades (south + west) rather than opposite (e.g. south+north)
— orthogonal coverage is photogrammetrically more informative per battery.

Lawnmower pattern clipped to tile bounds + buffer for ODM stitching.

Parameters (50MP sensor at 100m AGL):
- Altitude: 100m AGL
- Overlap: 80% on nadir, 70% on oblique (frontal and side)
- Flight speed: ~5 m/s

Nadir stays at 80% — orthophoto quality depends on dense overlap for
clean SIFT matching over featureless surfaces (roofs, pavement).

Obliques reduced to 70% because:
- 4 orthogonal directions provide cross-direction constraints that
  compensate for lower per-mission density — ODM matches features of
  the same wall across N+E+S+W flights
- ~33% fewer flight lines per oblique → ~33% less flight time per
  oblique → ~3× fewer photos per oblique → much less upload, storage,
  and ODM processing load
- Still above the 60% practical floor for SIFT matching on textured
  surfaces (walls, vegetation)
"""

import io
import math
import zipfile
from typing import List, Tuple
from dataclasses import dataclass
import time


# === Constants ===

ALTITUDE_M = 100
FLIGHT_SPEED_MS = 5.0
GROUND_WIDTH_M = 133   # Cross-track coverage at 100m AGL
GROUND_HEIGHT_M = 100   # Along-track coverage at 100m AGL

# Nadir: dense 80% overlap — orthophoto needs this for clean SIFT on roofs/pavement.
OVERLAP_PERCENT = 80   # Legacy name retained for `STEP_BETWEEN_*` (nadir)
# Lawnmower geometry: parallel lines are spaced ACROSS the flight direction, photos
# are taken ALONG it. So line spacing is bounded by the cross-track footprint
# (GROUND_WIDTH, the wide/long sensor edge ⟂ heading) and point spacing by the
# along-track footprint (GROUND_HEIGHT). Confirmed against flown Mini 4 Pro EXIF
# (landscape 4032×3024, gimbal yaw ≈ flight heading → long edge is cross-track).
STEP_BETWEEN_LINES_M = GROUND_WIDTH_M * (1 - OVERLAP_PERCENT / 100)   # ~26.6m → 80% side overlap
STEP_BETWEEN_POINTS_M = GROUND_HEIGHT_M * (1 - OVERLAP_PERCENT / 100)  # 20m → 80% frontal overlap

# Oblique: relaxed 70% overlap — 4 cardinal directions cross-constrain each wall,
# so each individual oblique mission can be sparser without losing SIFT matching.
# ~1.5× wider spacing → ~33% fewer flight lines → ~33% less flight time per oblique
# → ~2–3× fewer photos per oblique, dramatically cutting upload/ODM load.
OBLIQUE_OVERLAP_PERCENT = 70
OBLIQUE_STEP_BETWEEN_LINES_M = GROUND_WIDTH_M * (1 - OBLIQUE_OVERLAP_PERCENT / 100)   # ~39.9m → 70% side
OBLIQUE_STEP_BETWEEN_POINTS_M = GROUND_HEIGHT_M * (1 - OBLIQUE_OVERLAP_PERCENT / 100)  # 30m → 70% frontal

TILE_ZOOM = 17           # ~305×240m at mid-latitudes
BUFFER_M = 37            # Buffer beyond tile edge for ODM stitching overlap

OBLIQUE_GIMBAL_PITCH = -45

DRONE_ENUM = {
    'mavic_mini': 68,
    'mini_2': 68,
    'mini_3': 77,
    'mini_3_pro': 77,
}


@dataclass
class Waypoint:
    """Single waypoint in flight plan"""
    lat: float
    lon: float
    alt: float
    heading: float = 0
    index: int = 0


# === Web Mercator tile math (standard OSM/Google slippy map) ===

def tile_bounds(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
    """
    Standard slippy map tile → (west, south, east, north) in WGS84 degrees.
    Same formula as OSM, Google Maps, MapLibre. Pure math, no cos tricks.
    """
    n = 2 ** z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return west, south, east, north


def latlng_to_tile(lat: float, lng: float, z: int) -> Tuple[int, int]:
    """Convert (lat, lng) to tile (x, y) at zoom z."""
    n = 2 ** z
    x = int((lng + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tile_center(z: int, x: int, y: int) -> Tuple[float, float]:
    """Return (lat, lng) of tile center."""
    w, s, e, n = tile_bounds(z, x, y)
    return (s + n) / 2, (w + e) / 2


# === Lawnmower pattern generation ===

def generate_tile_snake_pattern(
    z: int, x: int, y: int,
    buffer_m: float = BUFFER_M,
    altitude_m: float = ALTITUDE_M,
    line_spacing_m: float = STEP_BETWEEN_LINES_M,
    point_spacing_m: float = STEP_BETWEEN_POINTS_M,
    direction: str = 'ns'
) -> List[Waypoint]:
    """
    Generate snake/lawnmower waypoints for a Web Mercator tile + buffer.

    Simple rectangle clipping — no polygon intersection needed.

    Args:
        z, x, y: Tile coordinates (zoom/column/row)
        direction: 'ns' = North-South lines (nadir), 'ew' = East-West lines (oblique)

    Includes setup waypoint (index 0) for gimbal pre-rotation.
    """
    west, south, east, north = tile_bounds(z, x, y)
    center_lat, center_lng = tile_center(z, x, y)

    meters_per_deg_lat = 111320
    meters_per_deg_lon = 111320 * math.cos(math.radians(center_lat))

    # Tile bounds in meters relative to center
    half_w = (east - west) / 2 * meters_per_deg_lon
    half_h = (north - south) / 2 * meters_per_deg_lat

    # Expand by buffer
    eff_half_w = half_w + buffer_m
    eff_half_h = half_h + buffer_m

    waypoints = []
    setup_offset_m = 5

    if direction == 'ew':
        # East-West flight lines, spaced along Y axis
        y_start = -eff_half_h
        lines = []
        y_m = y_start
        while y_m <= eff_half_h:
            lines.append((y_m, -eff_half_w, eff_half_w))
            y_m += line_spacing_m

        if not lines:
            return waypoints

        # Setup waypoint
        first_y, first_xmin, _ = lines[0]
        setup_lat = center_lat + first_y / meters_per_deg_lat
        setup_lon = center_lng + (first_xmin - setup_offset_m) / meters_per_deg_lon
        waypoints.append(Waypoint(lat=setup_lat, lon=setup_lon, alt=altitude_m, heading=90, index=0))

        index = 1
        for i, (y_m, x_min, x_max) in enumerate(lines):
            line_lat = center_lat + y_m / meters_per_deg_lat
            n_points = int((x_max - x_min) / point_spacing_m) + 1

            if i % 2 == 0:
                for j in range(n_points):
                    x_m = x_min + j * point_spacing_m
                    lon = center_lng + x_m / meters_per_deg_lon
                    waypoints.append(Waypoint(lat=line_lat, lon=lon, alt=altitude_m, heading=90, index=index))
                    index += 1
            else:
                for j in range(n_points - 1, -1, -1):
                    x_m = x_min + j * point_spacing_m
                    lon = center_lng + x_m / meters_per_deg_lon
                    waypoints.append(Waypoint(lat=line_lat, lon=lon, alt=altitude_m, heading=270, index=index))
                    index += 1
    else:
        # North-South flight lines (default), spaced along X axis
        x_start = -eff_half_w
        lines = []
        x_m = x_start
        while x_m <= eff_half_w:
            lines.append((x_m, -eff_half_h, eff_half_h))
            x_m += line_spacing_m

        if not lines:
            return waypoints

        # Setup waypoint
        first_x, first_ymin, _ = lines[0]
        setup_lat = center_lat + (first_ymin - setup_offset_m) / meters_per_deg_lat
        setup_lon = center_lng + first_x / meters_per_deg_lon
        waypoints.append(Waypoint(lat=setup_lat, lon=setup_lon, alt=altitude_m, heading=0, index=0))

        index = 1
        for i, (x_m, y_min, y_max) in enumerate(lines):
            line_lon = center_lng + x_m / meters_per_deg_lon
            n_points = int((y_max - y_min) / point_spacing_m) + 1

            if i % 2 == 0:
                for j in range(n_points):
                    y_m = y_min + j * point_spacing_m
                    lat = center_lat + y_m / meters_per_deg_lat
                    waypoints.append(Waypoint(lat=lat, lon=line_lon, alt=altitude_m, heading=0, index=index))
                    index += 1
            else:
                for j in range(n_points - 1, -1, -1):
                    y_m = y_min + j * point_spacing_m
                    lat = center_lat + y_m / meters_per_deg_lat
                    waypoints.append(Waypoint(lat=lat, lon=line_lon, alt=altitude_m, heading=180, index=index))
                    index += 1

    return waypoints


# === Helpers ===

def _total_path_distance(waypoints: List[Waypoint]) -> float:
    """Haversine total distance along waypoint path, in meters."""
    total = 0.0
    for i in range(1, len(waypoints)):
        wp1, wp2 = waypoints[i - 1], waypoints[i]
        lat1, lon1 = math.radians(wp1.lat), math.radians(wp1.lon)
        lat2, lon2 = math.radians(wp2.lat), math.radians(wp2.lon)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        total += 6371000 * 2 * math.asin(math.sqrt(a))
    return total


# === WPML generation ===

def generate_template_kml(drone_enum: int = 68) -> str:
    """Generate template.kml with mission config."""
    timestamp = int(time.time() * 1000)

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="http://www.uav.com/wpmz/1.0.2">
  <Document>
    <wpml:author>parahub</wpml:author>
    <wpml:createTime>{timestamp}</wpml:createTime>
    <wpml:updateTime>{timestamp}</wpml:updateTime>
    <wpml:missionConfig>
      <wpml:flyToWaylineMode>safely</wpml:flyToWaylineMode>
      <wpml:finishAction>goHome</wpml:finishAction>
      <wpml:exitOnRCLost>executeLostAction</wpml:exitOnRCLost>
      <wpml:executeRCLostAction>goBack</wpml:executeRCLostAction>
      <wpml:globalTransitionalSpeed>{FLIGHT_SPEED_MS}</wpml:globalTransitionalSpeed>
      <wpml:droneInfo>
        <wpml:droneEnumValue>{drone_enum}</wpml:droneEnumValue>
        <wpml:droneSubEnumValue>0</wpml:droneSubEnumValue>
      </wpml:droneInfo>
    </wpml:missionConfig>
  </Document>
</kml>'''


def generate_waylines_wpml(waypoints: List[Waypoint], drone_enum: int = 68, gimbal_pitch: int = -90) -> str:
    """Generate waylines.wpml with all waypoints."""
    total_distance = _total_path_distance(waypoints)
    duration = int(total_distance / FLIGHT_SPEED_MS)

    placemarks = []
    action_group_id = 0
    action_id = 0

    for i, wp in enumerate(waypoints):
        is_first = (i == 0)
        is_last = (i == len(waypoints) - 1)

        if is_first or is_last:
            turn_mode = "toPointAndStopWithContinuityCurvature"
        else:
            turn_mode = "toPointAndPassWithContinuityCurvature"

        heading_enable = 1 if is_first else 0

        action_groups = []

        if is_first:
            # Setup waypoint: gimbalRotate to set initial pitch
            action_group_id += 1
            action_id += 1
            action_groups.append(f'''
        <wpml:actionGroup>
          <wpml:actionGroupId>{action_group_id}</wpml:actionGroupId>
          <wpml:actionGroupStartIndex>0</wpml:actionGroupStartIndex>
          <wpml:actionGroupEndIndex>0</wpml:actionGroupEndIndex>
          <wpml:actionGroupMode>parallel</wpml:actionGroupMode>
          <wpml:actionTrigger>
            <wpml:actionTriggerType>reachPoint</wpml:actionTriggerType>
          </wpml:actionTrigger>
          <wpml:action>
            <wpml:actionId>{action_id}</wpml:actionId>
            <wpml:actionActuatorFunc>gimbalRotate</wpml:actionActuatorFunc>
            <wpml:actionActuatorFuncParam>
              <wpml:gimbalHeadingYawBase>aircraft</wpml:gimbalHeadingYawBase>
              <wpml:gimbalRotateMode>absoluteAngle</wpml:gimbalRotateMode>
              <wpml:gimbalPitchRotateEnable>1</wpml:gimbalPitchRotateEnable>
              <wpml:gimbalPitchRotateAngle>{gimbal_pitch}</wpml:gimbalPitchRotateAngle>
              <wpml:gimbalRollRotateEnable>1</wpml:gimbalRollRotateEnable>
              <wpml:gimbalRollRotateAngle>0</wpml:gimbalRollRotateAngle>
              <wpml:gimbalYawRotateEnable>0</wpml:gimbalYawRotateEnable>
              <wpml:gimbalYawRotateAngle>0</wpml:gimbalYawRotateAngle>
              <wpml:gimbalRotateTimeEnable>0</wpml:gimbalRotateTimeEnable>
              <wpml:gimbalRotateTime>0</wpml:gimbalRotateTime>
              <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>
            </wpml:actionActuatorFuncParam>
          </wpml:action>
        </wpml:actionGroup>''')
        else:
            # Survey waypoints: takePhoto
            action_group_id += 1
            action_id += 1
            action_groups.append(f'''
        <wpml:actionGroup>
          <wpml:actionGroupId>{action_group_id}</wpml:actionGroupId>
          <wpml:actionGroupStartIndex>{wp.index}</wpml:actionGroupStartIndex>
          <wpml:actionGroupEndIndex>{wp.index}</wpml:actionGroupEndIndex>
          <wpml:actionGroupMode>parallel</wpml:actionGroupMode>
          <wpml:actionTrigger>
            <wpml:actionTriggerType>reachPoint</wpml:actionTriggerType>
          </wpml:actionTrigger>
          <wpml:action>
            <wpml:actionId>{action_id}</wpml:actionId>
            <wpml:actionActuatorFunc>takePhoto</wpml:actionActuatorFunc>
            <wpml:actionActuatorFuncParam>
              <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>
            </wpml:actionActuatorFuncParam>
          </wpml:action>
        </wpml:actionGroup>''')

        actions_xml = "".join(action_groups)

        placemark = f'''
      <Placemark>
        <Point>
          <coordinates>{wp.lon},{wp.lat}</coordinates>
        </Point>
        <wpml:index>{wp.index}</wpml:index>
        <wpml:executeHeight>{wp.alt}</wpml:executeHeight>
        <wpml:waypointSpeed>{FLIGHT_SPEED_MS}</wpml:waypointSpeed>
        <wpml:waypointHeadingParam>
          <wpml:waypointHeadingMode>smoothTransition</wpml:waypointHeadingMode>
          <wpml:waypointHeadingAngle>{wp.heading}</wpml:waypointHeadingAngle>
          <wpml:waypointPoiPoint>0.000000,0.000000,0.000000</wpml:waypointPoiPoint>
          <wpml:waypointHeadingAngleEnable>{heading_enable}</wpml:waypointHeadingAngleEnable>
          <wpml:waypointHeadingPathMode>followBadArc</wpml:waypointHeadingPathMode>
          <wpml:waypointHeadingPoiIndex>0</wpml:waypointHeadingPoiIndex>
        </wpml:waypointHeadingParam>
        <wpml:waypointTurnParam>
          <wpml:waypointTurnMode>{turn_mode}</wpml:waypointTurnMode>
          <wpml:waypointTurnDampingDist>0</wpml:waypointTurnDampingDist>
        </wpml:waypointTurnParam>
        <wpml:useStraightLine>0</wpml:useStraightLine>{actions_xml}
        <wpml:waypointGimbalHeadingParam>
          <wpml:waypointGimbalPitchAngle>0</wpml:waypointGimbalPitchAngle>
          <wpml:waypointGimbalYawAngle>0</wpml:waypointGimbalYawAngle>
        </wpml:waypointGimbalHeadingParam>
      </Placemark>'''

        placemarks.append(placemark)

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="http://www.uav.com/wpmz/1.0.2">
  <Document>
    <wpml:missionConfig>
      <wpml:flyToWaylineMode>safely</wpml:flyToWaylineMode>
      <wpml:finishAction>goHome</wpml:finishAction>
      <wpml:exitOnRCLost>executeLostAction</wpml:exitOnRCLost>
      <wpml:executeRCLostAction>goBack</wpml:executeRCLostAction>
      <wpml:globalTransitionalSpeed>{FLIGHT_SPEED_MS}</wpml:globalTransitionalSpeed>
      <wpml:droneInfo>
        <wpml:droneEnumValue>{drone_enum}</wpml:droneEnumValue>
        <wpml:droneSubEnumValue>0</wpml:droneSubEnumValue>
      </wpml:droneInfo>
    </wpml:missionConfig>
    <Folder>
      <wpml:templateId>0</wpml:templateId>
      <wpml:executeHeightMode>relativeToStartPoint</wpml:executeHeightMode>
      <wpml:waylineId>0</wpml:waylineId>
      <wpml:distance>{int(total_distance)}</wpml:distance>
      <wpml:duration>{duration}</wpml:duration>
      <wpml:autoFlightSpeed>{FLIGHT_SPEED_MS}</wpml:autoFlightSpeed>{"".join(placemarks)}
    </Folder>
  </Document>
</kml>'''


# === KMZ / ZIP generation ===

def generate_kmz(
    z: int, x: int, y: int,
    direction: str = 'ns',
    gimbal_pitch: int = -90,
    forced_heading: int | None = None,
) -> bytes:
    """
    Generate WPML KMZ file for a single tile mission.

    Args:
        direction: 'ns' (North-South lines) or 'ew' (East-West lines)
        gimbal_pitch: -90 for nadir, -45 for oblique
        forced_heading: If set, all waypoints use this heading (0/90/180/270).
            Oblique missions require a fixed heading so the camera always
            points in one cardinal direction (see PK/opensky-system.md).
            If None and gimbal is oblique, falls back to the natural heading
            of the first waypoint for backward compatibility.
    """
    # Oblique missions use sparser spacing (70% overlap) to cut flight time
    # and photo count. Nadir keeps dense 80% for orthophoto quality.
    if gimbal_pitch != -90:
        line_spacing = OBLIQUE_STEP_BETWEEN_LINES_M
        point_spacing = OBLIQUE_STEP_BETWEEN_POINTS_M
    else:
        line_spacing = STEP_BETWEEN_LINES_M
        point_spacing = STEP_BETWEEN_POINTS_M

    waypoints = generate_tile_snake_pattern(
        z, x, y,
        direction=direction,
        line_spacing_m=line_spacing,
        point_spacing_m=point_spacing,
    )

    # Oblique missions require fixed heading (see PK/opensky-system.md)
    if gimbal_pitch != -90 and waypoints:
        fixed_heading = forced_heading if forced_heading is not None else waypoints[0].heading
        for wp in waypoints:
            wp.heading = fixed_heading

    template_kml = generate_template_kml()
    waylines_wpml = generate_waylines_wpml(waypoints, gimbal_pitch=gimbal_pitch)

    kmz_buffer = io.BytesIO()
    with zipfile.ZipFile(kmz_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('wpmz/template.kml', template_kml.encode('utf-8'))
        zf.writestr('wpmz/waylines.wpml', waylines_wpml.encode('utf-8'))

    return kmz_buffer.getvalue()


def calculate_mission_stats(waypoints: List[Waypoint]) -> dict:
    """Calculate mission statistics."""
    if len(waypoints) < 2:
        return {}

    total_distance = _total_path_distance(waypoints)

    return {
        "waypoints_count": len(waypoints),
        "total_distance_m": round(total_distance, 1),
        "estimated_time_min": round(total_distance / FLIGHT_SPEED_MS / 60, 1),
        "altitude_m": ALTITUDE_M,
        "overlap_percent": OVERLAP_PERCENT,
    }


def calculate_tile_stats(z: int, x: int, y: int) -> dict:
    """
    Calculate statistics for a single tile mission (5 sub-missions).

    Nadir uses dense 80% overlap; obliques use relaxed 70% — per-mission
    stats differ. Returns three budget levels the pilot can choose from:
        budget_1_battery  — ortho only (1_2D)
        budget_3_batteries — baseline 3D (1_2D + 2_3D-N + 3_3D-E)
        budget_5_batteries — ultra 3D, all 4 facades (1..5)
    """
    # Nadir (80% overlap, NS lines)
    nadir_wps_list = generate_tile_snake_pattern(z, x, y, direction='ns')
    nadir_stats = calculate_mission_stats(nadir_wps_list)

    # Oblique NS (70% overlap — used by 2_3D-N and 4_3D-S)
    oblique_ns_list = generate_tile_snake_pattern(
        z, x, y,
        direction='ns',
        line_spacing_m=OBLIQUE_STEP_BETWEEN_LINES_M,
        point_spacing_m=OBLIQUE_STEP_BETWEEN_POINTS_M,
    )
    oblique_ns_stats = calculate_mission_stats(oblique_ns_list)

    # Oblique EW (70% overlap — used by 3_3D-E and 5_3D-W)
    oblique_ew_list = generate_tile_snake_pattern(
        z, x, y,
        direction='ew',
        line_spacing_m=OBLIQUE_STEP_BETWEEN_LINES_M,
        point_spacing_m=OBLIQUE_STEP_BETWEEN_POINTS_M,
    )
    oblique_ew_stats = calculate_mission_stats(oblique_ew_list)

    west, south, east, north = tile_bounds(z, x, y)
    center_lat, center_lng = tile_center(z, x, y)
    mpd = 111320 * math.cos(math.radians(center_lat))
    width_m = (east - west) * mpd
    height_m = (north - south) * 111320

    nadir_time = nadir_stats.get("estimated_time_min", 0)
    oblique_ns_time = oblique_ns_stats.get("estimated_time_min", 0)
    oblique_ew_time = oblique_ew_stats.get("estimated_time_min", 0)

    nadir_wps = nadir_stats.get("waypoints_count", 0)
    oblique_ns_wps = oblique_ns_stats.get("waypoints_count", 0)
    oblique_ew_wps = oblique_ew_stats.get("waypoints_count", 0)

    # Flight layout per mission:
    #   1_2D    — nadir    (80%), NS lines
    #   2_3D-N  — oblique  (70%), NS lines (camera N)
    #   3_3D-E  — oblique  (70%), EW lines (camera E)
    #   4_3D-S  — oblique  (70%), NS lines (camera S)
    #   5_3D-W  — oblique  (70%), EW lines (camera W)
    total_waypoints_5 = nadir_wps + 2 * oblique_ns_wps + 2 * oblique_ew_wps
    total_time_5 = nadir_time + 2 * oblique_ns_time + 2 * oblique_ew_time

    # 3-battery bundle = nadir + 2_3D-N + 3_3D-E = nadir + 1×oblique-NS + 1×oblique-EW
    total_waypoints_3 = nadir_wps + oblique_ns_wps + oblique_ew_wps
    total_time_3 = nadir_time + oblique_ns_time + oblique_ew_time

    oblique_ns_meta = {**oblique_ns_stats, "gimbal_pitch": OBLIQUE_GIMBAL_PITCH, "direction": "ns", "overlap_percent": OBLIQUE_OVERLAP_PERCENT}
    oblique_ew_meta = {**oblique_ew_stats, "gimbal_pitch": OBLIQUE_GIMBAL_PITCH, "direction": "ew", "overlap_percent": OBLIQUE_OVERLAP_PERCENT}

    return {
        "tile": {"z": z, "x": x, "y": y},
        "center": {"lat": center_lat, "lng": center_lng},
        "bounds": {"north": north, "south": south, "east": east, "west": west},
        "width_m": round(width_m),
        "height_m": round(height_m),
        "area_m2": round(width_m * height_m),
        "buffer_m": BUFFER_M,
        "missions": {
            "1_2D":   {**nadir_stats, "gimbal_pitch": -90, "direction": "ns", "overlap_percent": OVERLAP_PERCENT},
            "2_3D-N": {**oblique_ns_meta, "camera_heading": 0},
            "3_3D-E": {**oblique_ew_meta, "camera_heading": 90},
            "4_3D-S": {**oblique_ns_meta, "camera_heading": 180},
            "5_3D-W": {**oblique_ew_meta, "camera_heading": 270},
        },
        "budgets": {
            "1_battery": {
                "files": ["1_2D"],
                "time_min": round(nadir_time, 1),
                "waypoints": nadir_wps,
                "facades_covered": 0,
                "description": "Ortho only (2D map)",
            },
            "3_batteries": {
                "files": ["1_2D", "2_3D-N", "3_3D-E"],
                "time_min": round(total_time_3, 1),
                "waypoints": total_waypoints_3,
                "facades_covered": 2,
                "description": "Baseline 3D (south + west walls)",
            },
            "5_batteries": {
                "files": ["1_2D", "2_3D-N", "3_3D-E", "4_3D-S", "5_3D-W"],
                "time_min": round(total_time_5, 1),
                "waypoints": total_waypoints_5,
                "facades_covered": 4,
                "description": "Ultra 3D (all 4 walls)",
            },
        },
        # Aggregates for the full 5-file download (useful for logging / sanity checks)
        "total_waypoints": total_waypoints_5,
        "total_time_min": round(total_time_5, 1),
    }


def generate_readme(z: int, x: int, y: int) -> str:
    """Generate README.txt with flight instructions for 5-file mission bundle."""
    center_lat, center_lng = tile_center(z, x, y)

    # Nadir (80% overlap, NS lines)
    nadir_wps = generate_tile_snake_pattern(z, x, y, direction='ns')
    t_nadir = calculate_mission_stats(nadir_wps).get('estimated_time_min', 17)

    # Oblique (70% overlap) — separate NS and EW patterns
    obl_ns_wps = generate_tile_snake_pattern(
        z, x, y, direction='ns',
        line_spacing_m=OBLIQUE_STEP_BETWEEN_LINES_M,
        point_spacing_m=OBLIQUE_STEP_BETWEEN_POINTS_M,
    )
    obl_ew_wps = generate_tile_snake_pattern(
        z, x, y, direction='ew',
        line_spacing_m=OBLIQUE_STEP_BETWEEN_LINES_M,
        point_spacing_m=OBLIQUE_STEP_BETWEEN_POINTS_M,
    )
    t_obl_ns = calculate_mission_stats(obl_ns_wps).get('estimated_time_min', 12)
    t_obl_ew = calculate_mission_stats(obl_ew_wps).get('estimated_time_min', 12)

    t_1 = round(t_nadir, 0)
    t_3 = round(t_nadir + t_obl_ns + t_obl_ew, 0)
    t_5 = round(t_nadir + 2 * t_obl_ns + 2 * t_obl_ew, 0)
    west, south, east, north = tile_bounds(z, x, y)

    return f"""OPENSKY FLIGHT PLAN — Z{z}/{x}/{y}
{'=' * 50}

Tile:   Z{z}/{x}/{y}
Center: {center_lat:.6f}, {center_lng:.6f}
Bounds: N{north:.6f} S{south:.6f} E{east:.6f} W{west:.6f}

CONTENTS (5 flight plans)
-------------------------
1_2D.kmz     Nadir (gimbal -90 deg)     — orthophoto for 2D map
2_3D-N.kmz   Oblique, camera North      — captures SOUTH-facing walls
3_3D-E.kmz   Oblique, camera East       — captures WEST-facing walls
4_3D-S.kmz   Oblique, camera South      — captures NORTH-facing walls
5_3D-W.kmz   Oblique, camera West       — captures EAST-facing walls

Each oblique mission captures ONE facade direction (the wall facing
toward the camera). To cover all 4 sides of buildings, fly all 4
oblique missions. Flying fewer is fine — you'll get partial facade
coverage proportional to how many you fly.

FLIGHT BUDGET — fly as many as you need
---------------------------------------
1 battery   1_2D                                    ~{t_1:.0f} min
            Orthophoto only (2D map). No 3D model.

3 batteries 1_2D + 2_3D-N + 3_3D-E                  ~{t_3:.0f} min
            Baseline 3D: south + west walls (2 of 4 facades).
            Equivalent to the previous 3-battery OpenSky workflow.

5 batteries 1_2D + 2_3D-N + 3_3D-E + 4_3D-S + 5_3D-W  ~{t_5:.0f} min
            Ultra 3D: all 4 walls covered. Recommended for buildings,
            monuments, dense areas. Spread across multiple sessions
            is fine — upload all photos together at the end.

Numbers are ordered so each next battery adds maximum new information.
Fly them in numeric order (1 → 2 → 3 → 4 → 5).

PARAMETERS
----------
Altitude:       100m AGL
Overlap:        80% on nadir, 70% on obliques (sparser oblique spacing
                means ~33% faster per oblique flight and fewer photos
                to upload — 4 cardinal directions cross-constrain the
                mesh, so you don't need dense overlap per mission)
Speed:          ~5 m/s

CAMERA SETTINGS
---------------
Format:         JPEG (not RAW)
Aspect ratio:   4:3
Resolution:     12 MP
White balance:  Sunny / fixed
ISO:            100-400

HOW TO FLY (DJI Fly)
--------------------
1. Set camera to JPEG, 4:3, 12 MP before first flight
2. Import .kmz file via DJI Fly > Waypoint Mission > Import
3. Review waypoints on map, then start mission
4. After each mission: swap battery, import next .kmz, fly again
5. Upload ALL photos (from all flights for this tile) to the same
   OpenSky mission. The mission must contain nadir photos before
   processing — oblique-only missions are rejected at finalize.

You don't have to fly everything in one session. You can fly
1_2D today, come back next weekend to add 2_3D-N and 3_3D-E,
then append the rest later. Each subsequent upload reprocesses
the mission with ALL accumulated photos.

Generated by OpenSky (parahub.io)
"""


def generate_tile_zip(z: int, x: int, y: int, base_name: str = "OpenSky") -> bytes:
    """
    Generate ZIP with 5 KMZ files (nadir + 4 oblique) for a single tile.

    Structure:
        1_2D.kmz    — NS lines, gimbal -90°              (nadir orthophoto)
        2_3D-N.kmz  — NS lines, gimbal -45°, heading 0°  (camera North → south walls)
        3_3D-E.kmz  — EW lines, gimbal -45°, heading 90° (camera East  → west walls)
        4_3D-S.kmz  — NS lines, gimbal -45°, heading 180°(camera South → north walls)
        5_3D-W.kmz  — EW lines, gimbal -45°, heading 270°(camera West  → east walls)
        README.txt  — Flight instructions + budget matrix (1/3/5 batteries)

    Pilot flies as many as budget allows (see README):
        1 battery  → ortho only (1)
        3 batteries → baseline 3D, 2 of 4 facades (1+2+3)
        5 batteries → ultra 3D, all 4 facades (1..5)

    Filenames are prefixed with flight-order numbers so DJI Fly sorts
    them correctly alphabetically. `base_name` is retained for backward
    compatibility of the ZIP download filename but not used inside.

    Fixed heading per mission for oblique compatibility (see PK/opensky-system.md).
    """
    # Generator dispatch: (filename, direction, gimbal_pitch)
    # The actual camera heading is set by the first waypoint in each direction
    # (NS → heading 0, EW → heading 90). For opposite-direction obliques (S and W)
    # we rotate the heading of every waypoint post-hoc to 180/270.
    files = [
        ("1_2D.kmz",    "ns", -90,                    None),  # nadir
        ("2_3D-N.kmz",  "ns", OBLIQUE_GIMBAL_PITCH,   0),     # camera North
        ("3_3D-E.kmz",  "ew", OBLIQUE_GIMBAL_PITCH,   90),    # camera East
        ("4_3D-S.kmz",  "ns", OBLIQUE_GIMBAL_PITCH,   180),   # camera South
        ("5_3D-W.kmz",  "ew", OBLIQUE_GIMBAL_PITCH,   270),   # camera West
    ]

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname, direction, pitch, forced_heading in files:
            kmz_bytes = generate_kmz(
                z, x, y,
                direction=direction,
                gimbal_pitch=pitch,
                forced_heading=forced_heading,
            )
            zf.writestr(fname, kmz_bytes)

        zf.writestr("README.txt", generate_readme(z, x, y))

    return zip_buffer.getvalue()
