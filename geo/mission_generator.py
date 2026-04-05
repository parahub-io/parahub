"""
OpenSky Mission Generator — WPML flight plans for drone aerial survey.

Uses standard Web Mercator tiles (Z/X/Y) at zoom 17 (~305×240m per tile).
Each tile generates 3 KMZ: nadir (NS) + oblique East (EW) + oblique North (NS).
Lawnmower pattern clipped to tile bounds + buffer for ODM stitching.

Parameters (50MP sensor at 100m AGL):
- Altitude: 100m AGL
- Overlap: 80% (frontal and side)
- Flight speed: ~5 m/s
"""

import io
import math
import zipfile
from typing import List, Tuple
from dataclasses import dataclass
import time


# === Constants ===

ALTITUDE_M = 100
OVERLAP_PERCENT = 80
FLIGHT_SPEED_MS = 5.0
GROUND_WIDTH_M = 133   # Cross-track coverage at 100m AGL
GROUND_HEIGHT_M = 100   # Along-track coverage at 100m AGL

STEP_BETWEEN_LINES_M = GROUND_HEIGHT_M * (1 - OVERLAP_PERCENT / 100)  # 20m
STEP_BETWEEN_POINTS_M = GROUND_WIDTH_M * (1 - OVERLAP_PERCENT / 100)  # ~26.6m

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
    mission_name: str = "OpenSky Mission",
    direction: str = 'ns',
    gimbal_pitch: int = -90
) -> bytes:
    """Generate WPML KMZ file for a single tile mission."""
    waypoints = generate_tile_snake_pattern(z, x, y, direction=direction)

    # Oblique missions require fixed heading (see PK/opensky-system.md)
    if gimbal_pitch != -90 and waypoints:
        fixed_heading = waypoints[0].heading
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
    """Calculate statistics for a single tile mission (nadir + 2 oblique)."""
    ns_wps = generate_tile_snake_pattern(z, x, y, direction='ns')
    ew_wps = generate_tile_snake_pattern(z, x, y, direction='ew')
    ns_stats = calculate_mission_stats(ns_wps)
    ew_stats = calculate_mission_stats(ew_wps)

    west, south, east, north = tile_bounds(z, x, y)
    center_lat, center_lng = tile_center(z, x, y)
    mpd = 111320 * math.cos(math.radians(center_lat))
    width_m = (east - west) * mpd
    height_m = (north - south) * 111320

    return {
        "tile": {"z": z, "x": x, "y": y},
        "center": {"lat": center_lat, "lng": center_lng},
        "bounds": {"north": north, "south": south, "east": east, "west": west},
        "width_m": round(width_m),
        "height_m": round(height_m),
        "area_m2": round(width_m * height_m),
        "buffer_m": BUFFER_M,
        "nadir_mission": ns_stats,
        "oblique_ew_mission": ew_stats,
        "oblique_ns_mission": ns_stats,
        "total_waypoints": ns_stats.get("waypoints_count", 0) * 2 + ew_stats.get("waypoints_count", 0),
        "total_time_min": round(
            ns_stats.get("estimated_time_min", 0) * 2 + ew_stats.get("estimated_time_min", 0), 1
        ),
        "batteries": 3,
    }


def generate_readme(base_name: str, z: int, x: int, y: int) -> str:
    """Generate README.txt with flight instructions."""
    center_lat, center_lng = tile_center(z, x, y)
    ns_wps = generate_tile_snake_pattern(z, x, y, direction='ns')
    ns_stats = calculate_mission_stats(ns_wps)
    time_per = ns_stats.get('estimated_time_min', 25)
    west, south, east, north = tile_bounds(z, x, y)

    return f"""OPENSKY FLIGHT PLAN — {base_name}
{'=' * 50}

Tile: Z{z}/{x}/{y}
Center: {center_lat:.6f}, {center_lng:.6f}
Bounds: N{north:.6f} S{south:.6f} E{east:.6f} W{west:.6f}

CONTENTS
--------
{base_name}_2D.kmz       Camera straight down (nadir, gimbal -90 deg)
                          North-South flight lines
                          For orthophoto (2D map tiles)

{base_name}_3D-E.kmz     Camera at 45 deg facing East (oblique, gimbal -45 deg)
                          East-West flight lines

{base_name}_3D-N.kmz     Camera at 45 deg facing North (oblique, gimbal -45 deg)
                          North-South flight lines

Both 3D missions together give full facade coverage for 3D reconstruction.

FLIGHT ORDER
------------
1. Fly 2D mission  ({base_name}_2D.kmz)   — ~{time_per:.0f} min, 1 battery
2. Swap battery
3. Fly 3D-E mission ({base_name}_3D-E.kmz) — ~{time_per:.0f} min, 1 battery
4. Swap battery
5. Fly 3D-N mission ({base_name}_3D-N.kmz) — ~{time_per:.0f} min, 1 battery
6. Upload ALL photos (2D + 3D-E + 3D-N) together to OpenSky

PARAMETERS
----------
Altitude:       100m AGL
Overlap:        80%
Speed:          ~5 m/s
Batteries:      3 (one per mission)

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
5. Upload all photos from all flights to the same OpenSky mission

Generated by OpenSky (parahub.io)
"""


def generate_tile_zip(z: int, x: int, y: int, base_name: str = "OpenSky") -> bytes:
    """
    Generate ZIP with 3 KMZ files (nadir + 2 oblique) for a single tile.

    Structure:
        {base_name}_2D.kmz     — NS lines, gimbal -90° (nadir orthophoto)
        {base_name}_3D-E.kmz   — EW lines, gimbal -45°, heading East (oblique)
        {base_name}_3D-N.kmz   — NS lines, gimbal -45°, heading North (oblique)
        README.txt              — Flight instructions

    Two oblique directions (E + N) give full facade coverage for 3D reconstruction.
    Fixed heading per mission for oblique compatibility (see PK/opensky-system.md).
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        nadir_kmz = generate_kmz(z, x, y, f"{base_name}_2D", direction='ns', gimbal_pitch=-90)
        zf.writestr(f"{base_name}_2D.kmz", nadir_kmz)

        oblique_ew = generate_kmz(z, x, y, f"{base_name}_3D-E", direction='ew', gimbal_pitch=OBLIQUE_GIMBAL_PITCH)
        zf.writestr(f"{base_name}_3D-E.kmz", oblique_ew)

        oblique_ns = generate_kmz(z, x, y, f"{base_name}_3D-N", direction='ns', gimbal_pitch=OBLIQUE_GIMBAL_PITCH)
        zf.writestr(f"{base_name}_3D-N.kmz", oblique_ns)

        zf.writestr("README.txt", generate_readme(base_name, z, x, y))

    return zip_buffer.getvalue()
