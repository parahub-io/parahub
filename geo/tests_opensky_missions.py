"""
OpenSky mission generator tests — Z17 Web Mercator tiles.

Tests the full pipeline: tile geometry, coordinate conversions,
KMZ structure, and frontend↔backend consistency.

Run: python3 manage.py test geo.tests_opensky_missions
"""

import math
import zipfile
import io
import re
import xml.etree.ElementTree as ET
from django.test import TestCase

from geo.mission_generator import (
    tile_bounds,
    latlng_to_tile,
    tile_center,
    generate_tile_snake_pattern,
    generate_tile_zip,
    generate_kmz,
    calculate_tile_stats,
    calculate_mission_stats,
    TILE_ZOOM,
    BUFFER_M,
    STEP_BETWEEN_LINES_M,
    STEP_BETWEEN_POINTS_M,
)


# ── Test locations spanning the globe ────────────────────────────

LOCATIONS = [
    ('Lisbon', 38.75, -9.15),
    ('Tokyo', 35.68, 139.70),
    ('New York', 40.71, -74.01),
    ('Sydney', -33.87, 151.21),
    ('Reykjavik', 64.14, -21.94),
    ('Nairobi', -1.29, 36.82),
]


# ── Helpers ──────────────────────────────────────────────────────

def _frontend_lng2tile(lng, z):
    """Simulate frontend lng2tile (must match Python latlng_to_tile)."""
    return int((lng + 180) / 360 * (2 ** z))


def _frontend_lat2tile(lat, z):
    """Simulate frontend lat2tile (must match Python latlng_to_tile)."""
    lat_rad = lat * math.pi / 180
    return int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * (2 ** z))


def _extract_kmz_waypoints(kmz_data):
    """Extract survey waypoints (skip setup idx=0) from KMZ bytes."""
    with zipfile.ZipFile(io.BytesIO(kmz_data)) as kmz:
        wpml = kmz.read('wpmz/waylines.wpml')
    root = ET.fromstring(wpml)
    ns = {
        'kml': 'http://www.opengis.net/kml/2.2',
        'wpml': 'http://www.uav.com/wpmz/1.0.2',
    }
    wps = []
    for pm in root.findall('.//kml:Placemark', ns):
        coords = pm.find('.//kml:coordinates', ns).text.strip()
        lon_s, lat_s = coords.split(',')[:2]
        idx = int(pm.find('wpml:index', ns).text)
        if idx > 0:
            wps.append((float(lat_s), float(lon_s)))
    return wps


# ── Tile geometry tests ──────────────────────────────────────────

class TileBoundsTest(TestCase):
    """Test tile_bounds produces correct WGS84 rectangles."""

    def test_tile_bounds_known_values(self):
        """Tile (0,0,0) covers the entire world."""
        w, s, e, n = tile_bounds(0, 0, 0)
        self.assertAlmostEqual(w, -180.0, places=5)
        self.assertAlmostEqual(e, 180.0, places=5)
        self.assertAlmostEqual(n, 85.05113, delta=0.001)
        self.assertAlmostEqual(s, -85.05113, delta=0.001)

    def test_tile_bounds_z1_quadrants(self):
        """Z1 splits the world into 4 tiles."""
        # Top-left: western hemisphere, northern
        w, s, e, n = tile_bounds(1, 0, 0)
        self.assertAlmostEqual(w, -180.0)
        self.assertAlmostEqual(e, 0.0)
        self.assertGreater(n, 0)

    def test_tile_bounds_non_overlapping(self):
        """Adjacent Z17 tiles share edges, don't overlap."""
        for name, lat, lng in LOCATIONS:
            with self.subTest(location=name):
                x, y = latlng_to_tile(lat, lng, TILE_ZOOM)
                w1, s1, e1, n1 = tile_bounds(TILE_ZOOM, x, y)
                w2, s2, e2, n2 = tile_bounds(TILE_ZOOM, x + 1, y)
                self.assertAlmostEqual(e1, w2, places=10,
                    msg=f"{name}: east edge of tile doesn't match west edge of neighbor")

                w3, s3, e3, n3 = tile_bounds(TILE_ZOOM, x, y + 1)
                self.assertAlmostEqual(s1, n3, places=10,
                    msg=f"{name}: south edge doesn't match north edge of tile below")


class TileRoundTripTest(TestCase):
    """Test latlng→tile→center round-trip consistency."""

    def test_round_trip_global(self):
        """Original point must land inside the tile it maps to."""
        for name, lat, lng in LOCATIONS:
            with self.subTest(location=name):
                x, y = latlng_to_tile(lat, lng, TILE_ZOOM)
                w, s, e, n = tile_bounds(TILE_ZOOM, x, y)
                self.assertGreaterEqual(lat, s, f"{name}: lat below south bound")
                self.assertLessEqual(lat, n, f"{name}: lat above north bound")
                self.assertGreaterEqual(lng, w, f"{name}: lng below west bound")
                self.assertLessEqual(lng, e, f"{name}: lng above east bound")

    def test_center_inside_tile(self):
        """tile_center must be inside tile bounds."""
        for name, lat, lng in LOCATIONS:
            with self.subTest(location=name):
                x, y = latlng_to_tile(lat, lng, TILE_ZOOM)
                c_lat, c_lng = tile_center(TILE_ZOOM, x, y)
                w, s, e, n = tile_bounds(TILE_ZOOM, x, y)
                self.assertGreater(c_lat, s)
                self.assertLess(c_lat, n)
                self.assertGreater(c_lng, w)
                self.assertLess(c_lng, e)


class FrontendBackendAlignmentTest(TestCase):
    """
    THE CRITICAL TEST: frontend tile computation must match backend.

    Frontend sends tile_x/tile_y to API. If they disagree on which tile
    a coordinate falls into, the user sees one tile but gets a mission
    for a different one.
    """

    def test_tile_coords_match(self):
        """Frontend and backend must compute identical tile (x, y) for all locations."""
        for name, lat, lng in LOCATIONS:
            with self.subTest(location=name):
                bx, by = latlng_to_tile(lat, lng, TILE_ZOOM)
                fx = _frontend_lng2tile(lng, TILE_ZOOM)
                fy = _frontend_lat2tile(lat, TILE_ZOOM)
                self.assertEqual(bx, fx, f"{name}: x mismatch backend={bx} frontend={fx}")
                self.assertEqual(by, fy, f"{name}: y mismatch backend={by} frontend={fy}")

    def test_waypoint_centroid_near_tile_center(self):
        """Waypoint centroid must be within 15m of tile center (global)."""
        for name, lat, lng in LOCATIONS:
            with self.subTest(location=name):
                x, y = latlng_to_tile(lat, lng, TILE_ZOOM)
                c_lat, c_lng = tile_center(TILE_ZOOM, x, y)
                mpd_lon = 111320 * math.cos(math.radians(c_lat))

                wps = generate_tile_snake_pattern(TILE_ZOOM, x, y, direction='ns')
                survey_wps = wps[1:]  # skip setup
                centroid_lat = sum(w.lat for w in survey_wps) / len(survey_wps)
                centroid_lng = sum(w.lon for w in survey_wps) / len(survey_wps)

                dx = (centroid_lng - c_lng) * mpd_lon
                dy = (centroid_lat - c_lat) * 111320
                dist = math.sqrt(dx ** 2 + dy ** 2)
                self.assertLess(dist, 15.0,
                    f"{name}: centroid {dist:.1f}m from tile center (max 15m)")


# ── Waypoint bounds tests ────────────────────────────────────────

class WaypointsInsideTileTest(TestCase):
    """All waypoints must be within tile bounds + buffer."""

    def test_all_waypoints_within_bounds(self):
        """Survey waypoints (skip setup) within tile + BUFFER_M at all locations."""
        for name, lat, lng in LOCATIONS:
            for direction in ['ns', 'ew']:
                with self.subTest(location=name, direction=direction):
                    x, y = latlng_to_tile(lat, lng, TILE_ZOOM)
                    w, s, e, n = tile_bounds(TILE_ZOOM, x, y)
                    c_lat, c_lng = tile_center(TILE_ZOOM, x, y)
                    mpd_lon = 111320 * math.cos(math.radians(c_lat))

                    half_w_m = (e - w) / 2 * mpd_lon + BUFFER_M
                    half_h_m = (n - s) / 2 * 111320 + BUFFER_M

                    wps = generate_tile_snake_pattern(TILE_ZOOM, x, y, direction=direction)
                    self.assertGreater(len(wps), 10, f"{name} {direction}: too few waypoints")

                    for wp in wps[1:]:  # skip setup
                        dx = abs(wp.lon - c_lng) * mpd_lon
                        dy = abs(wp.lat - c_lat) * 111320
                        self.assertLessEqual(dx, half_w_m + 1,
                            f"{name} {direction}: wp lon {wp.lon} is {dx:.1f}m from center (max {half_w_m:.1f}m)")
                        self.assertLessEqual(dy, half_h_m + 1,
                            f"{name} {direction}: wp lat {wp.lat} is {dy:.1f}m from center (max {half_h_m:.1f}m)")

    def test_snake_pattern_covers_full_tile(self):
        """Waypoints must span most of the tile area (>80% of each dimension)."""
        for name, lat, lng in LOCATIONS:
            with self.subTest(location=name):
                x, y = latlng_to_tile(lat, lng, TILE_ZOOM)
                w, s, e, n = tile_bounds(TILE_ZOOM, x, y)
                c_lat, _ = tile_center(TILE_ZOOM, x, y)
                mpd_lon = 111320 * math.cos(math.radians(c_lat))
                tile_w_m = (e - w) * mpd_lon
                tile_h_m = (n - s) * 111320

                wps = generate_tile_snake_pattern(TILE_ZOOM, x, y, direction='ns')
                lats = [wp.lat for wp in wps[1:]]
                lons = [wp.lon for wp in wps[1:]]
                lat_span_m = (max(lats) - min(lats)) * 111320
                lon_span_m = (max(lons) - min(lons)) * mpd_lon

                self.assertGreater(lat_span_m, tile_h_m * 0.8,
                    f"{name}: lat span {lat_span_m:.0f}m < 80% of tile height {tile_h_m:.0f}m")
                self.assertGreater(lon_span_m, tile_w_m * 0.8,
                    f"{name}: lon span {lon_span_m:.0f}m < 80% of tile width {tile_w_m:.0f}m")


# ── KMZ content tests ────────────────────────────────────────────

class KMZContentTest(TestCase):
    """Verify KMZ file structure and content."""

    def test_zip_structure(self):
        """ZIP must contain nadir KMZ + 2 oblique KMZ + README."""
        x, y = latlng_to_tile(38.75, -9.15, TILE_ZOOM)
        zip_data = generate_tile_zip(TILE_ZOOM, x, y, 'Test')
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            names = zf.namelist()

        self.assertIn('Test_2D.kmz', names)
        self.assertIn('Test_3D-E.kmz', names)
        self.assertIn('Test_3D-N.kmz', names)
        self.assertIn('README.txt', names)
        self.assertEqual(len(names), 4)

    def test_kmz_internal_structure(self):
        """Each KMZ must contain wpmz/template.kml and wpmz/waylines.wpml."""
        kmz_data = generate_kmz(TILE_ZOOM, 62204, 50209, 'Test', direction='ns')
        with zipfile.ZipFile(io.BytesIO(kmz_data)) as kmz:
            names = kmz.namelist()
        self.assertIn('wpmz/template.kml', names)
        self.assertIn('wpmz/waylines.wpml', names)

    def test_gimbal_angles(self):
        """Nadir must have -90° gimbal, oblique must have -45°."""
        x, y = latlng_to_tile(38.75, -9.15, TILE_ZOOM)
        zip_data = generate_tile_zip(TILE_ZOOM, x, y, 'G')

        for kmz_name, expected_pitch in [('G_2D.kmz', '-90'), ('G_3D-E.kmz', '-45'), ('G_3D-N.kmz', '-45')]:
            with self.subTest(kmz=kmz_name):
                with zipfile.ZipFile(io.BytesIO(zip_data)) as outer:
                    kmz_data = outer.read(kmz_name)
                with zipfile.ZipFile(io.BytesIO(kmz_data)) as kmz:
                    wpml = kmz.read('wpmz/waylines.wpml').decode()

                pitches = set(re.findall(r'gimbalPitchRotateAngle>(-?\d+)<', wpml))
                self.assertEqual(pitches, {expected_pitch},
                    f"{kmz_name}: expected pitch {expected_pitch}, got {pitches}")

    def test_setup_waypoint_no_photo(self):
        """Setup waypoint (idx 0) must have gimbalRotate but NOT takePhoto."""
        kmz_data = generate_kmz(TILE_ZOOM, 62204, 50209, 'W', direction='ns')
        with zipfile.ZipFile(io.BytesIO(kmz_data)) as kmz:
            wpml = kmz.read('wpmz/waylines.wpml')

        root = ET.fromstring(wpml)
        ns = {
            'kml': 'http://www.opengis.net/kml/2.2',
            'wpml': 'http://www.uav.com/wpmz/1.0.2',
        }
        first_pm = root.findall('.//kml:Placemark', ns)[0]
        actions = [a.text for a in first_pm.findall('.//wpml:actionActuatorFunc', ns)]

        self.assertIn('gimbalRotate', actions, "Setup waypoint missing gimbalRotate")
        self.assertNotIn('takePhoto', actions, "Setup waypoint should NOT take photo")

    def test_survey_waypoints_have_photo(self):
        """All non-setup waypoints must have takePhoto action."""
        kmz_data = generate_kmz(TILE_ZOOM, 62204, 50209, 'P', direction='ns')
        with zipfile.ZipFile(io.BytesIO(kmz_data)) as kmz:
            wpml = kmz.read('wpmz/waylines.wpml')

        root = ET.fromstring(wpml)
        ns = {
            'kml': 'http://www.opengis.net/kml/2.2',
            'wpml': 'http://www.uav.com/wpmz/1.0.2',
        }
        placemarks = root.findall('.//kml:Placemark', ns)
        for pm in placemarks[1:]:  # skip setup
            idx = int(pm.find('wpml:index', ns).text)
            actions = [a.text for a in pm.findall('.//wpml:actionActuatorFunc', ns)]
            self.assertIn('takePhoto', actions, f"Waypoint {idx} missing takePhoto")


class TileStatsTest(TestCase):
    """Test mission statistics calculation."""

    def test_stats_structure(self):
        """calculate_tile_stats returns expected keys."""
        stats = calculate_tile_stats(TILE_ZOOM, 62204, 50209)
        for key in ['tile', 'center', 'bounds', 'width_m', 'height_m',
                     'nadir_mission', 'oblique_ew_mission', 'oblique_ns_mission',
                     'total_waypoints', 'total_time_min', 'batteries']:
            self.assertIn(key, stats, f"Missing key: {key}")

    def test_stats_reasonable_values(self):
        """Stats must be within reasonable ranges for Z17."""
        for name, lat, lng in LOCATIONS:
            with self.subTest(location=name):
                x, y = latlng_to_tile(lat, lng, TILE_ZOOM)
                stats = calculate_tile_stats(TILE_ZOOM, x, y)

                # Tile size: 100-320m (varies by latitude)
                self.assertGreater(stats['width_m'], 100)
                self.assertLess(stats['width_m'], 320)
                self.assertGreater(stats['height_m'], 100)
                self.assertLess(stats['height_m'], 320)

                # Time: 3 missions, 5-30 min each
                self.assertGreater(stats['total_time_min'], 15)
                self.assertLess(stats['total_time_min'], 90)

                # Waypoints: reasonable count
                self.assertGreater(stats['total_waypoints'], 50)
                self.assertLess(stats['total_waypoints'], 1000)
