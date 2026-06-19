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
    OBLIQUE_STEP_BETWEEN_LINES_M,
    OBLIQUE_STEP_BETWEEN_POINTS_M,
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
        """ZIP must contain 5 KMZ (nadir + 4 cardinal obliques) + README."""
        x, y = latlng_to_tile(38.75, -9.15, TILE_ZOOM)
        zip_data = generate_tile_zip(TILE_ZOOM, x, y)
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            names = zf.namelist()

        self.assertIn('1_2D.kmz', names)
        self.assertIn('2_3D-N.kmz', names)
        self.assertIn('3_3D-E.kmz', names)
        self.assertIn('4_3D-S.kmz', names)
        self.assertIn('5_3D-W.kmz', names)
        self.assertIn('README.txt', names)
        self.assertEqual(len(names), 6)

    def test_kmz_internal_structure(self):
        """Each KMZ must contain wpmz/template.kml and wpmz/waylines.wpml."""
        kmz_data = generate_kmz(TILE_ZOOM, 62204, 50209, direction='ns')
        with zipfile.ZipFile(io.BytesIO(kmz_data)) as kmz:
            names = kmz.namelist()
        self.assertIn('wpmz/template.kml', names)
        self.assertIn('wpmz/waylines.wpml', names)

    def test_gimbal_angles(self):
        """Nadir KMZ must have -90° gimbal, all 4 obliques must have -45°."""
        x, y = latlng_to_tile(38.75, -9.15, TILE_ZOOM)
        zip_data = generate_tile_zip(TILE_ZOOM, x, y)

        expectations = [
            ('1_2D.kmz',   '-90'),
            ('2_3D-N.kmz', '-45'),
            ('3_3D-E.kmz', '-45'),
            ('4_3D-S.kmz', '-45'),
            ('5_3D-W.kmz', '-45'),
        ]
        for kmz_name, expected_pitch in expectations:
            with self.subTest(kmz=kmz_name):
                with zipfile.ZipFile(io.BytesIO(zip_data)) as outer:
                    kmz_data = outer.read(kmz_name)
                with zipfile.ZipFile(io.BytesIO(kmz_data)) as kmz:
                    wpml = kmz.read('wpmz/waylines.wpml').decode()

                pitches = set(re.findall(r'gimbalPitchRotateAngle>(-?\d+)<', wpml))
                self.assertEqual(pitches, {expected_pitch},
                    f"{kmz_name}: expected pitch {expected_pitch}, got {pitches}")

    def test_oblique_uses_sparser_spacing(self):
        """
        Oblique missions run at 70% overlap (wider line/point spacing) to
        save flight time. Verify by comparing waypoint counts: each oblique
        KMZ must have strictly fewer waypoints than the nadir KMZ for the
        same tile. Also verify the ratio is roughly the expected ~0.45.
        """
        # Use Lisbon (mid-latitude, typical tile size)
        x, y = latlng_to_tile(38.75, -9.15, TILE_ZOOM)
        zip_data = generate_tile_zip(TILE_ZOOM, x, y)

        def _wp_count(kmz_name):
            with zipfile.ZipFile(io.BytesIO(zip_data)) as outer:
                kmz_data = outer.read(kmz_name)
            with zipfile.ZipFile(io.BytesIO(kmz_data)) as kmz:
                wpml = kmz.read('wpmz/waylines.wpml')
            root = ET.fromstring(wpml)
            return len(root.findall('.//{http://www.opengis.net/kml/2.2}Placemark'))

        nadir = _wp_count('1_2D.kmz')
        for oblique_name in ['2_3D-N.kmz', '3_3D-E.kmz', '4_3D-S.kmz', '5_3D-W.kmz']:
            with self.subTest(kmz=oblique_name):
                obl = _wp_count(oblique_name)
                self.assertLess(obl, nadir,
                    f"{oblique_name} ({obl} wps) must have fewer waypoints than 1_2D ({nadir} wps)")
                # Waypoint ratio should be roughly (1/1.5)^2 ≈ 0.44 — allow 0.35..0.6
                ratio = obl / nadir
                self.assertGreater(ratio, 0.35, f"{oblique_name}: ratio {ratio:.2f} too low — overlap reduction too aggressive")
                self.assertLess(ratio, 0.6, f"{oblique_name}: ratio {ratio:.2f} too high — overlap reduction didn't take effect")

    def test_oblique_constants_relation(self):
        """Oblique spacing must be strictly wider than nadir spacing (70% < 80%)."""
        self.assertGreater(OBLIQUE_STEP_BETWEEN_LINES_M, STEP_BETWEEN_LINES_M)
        self.assertGreater(OBLIQUE_STEP_BETWEEN_POINTS_M, STEP_BETWEEN_POINTS_M)
        # Sanity: 70% overlap is 1.5× wider than 80% overlap
        self.assertAlmostEqual(
            OBLIQUE_STEP_BETWEEN_LINES_M / STEP_BETWEEN_LINES_M, 1.5, places=2
        )
        self.assertAlmostEqual(
            OBLIQUE_STEP_BETWEEN_POINTS_M / STEP_BETWEEN_POINTS_M, 1.5, places=2
        )

    def test_oblique_fixed_headings(self):
        """
        Each oblique KMZ must have ONE fixed camera heading matching its
        cardinal direction: N=0, E=90, S=180, W=270. Nadir can vary.
        """
        x, y = latlng_to_tile(38.75, -9.15, TILE_ZOOM)
        zip_data = generate_tile_zip(TILE_ZOOM, x, y)

        expectations = {
            '2_3D-N.kmz': 0,
            '3_3D-E.kmz': 90,
            '4_3D-S.kmz': 180,
            '5_3D-W.kmz': 270,
        }
        ns = {
            'kml': 'http://www.opengis.net/kml/2.2',
            'wpml': 'http://www.uav.com/wpmz/1.0.2',
        }
        for kmz_name, expected_heading in expectations.items():
            with self.subTest(kmz=kmz_name):
                with zipfile.ZipFile(io.BytesIO(zip_data)) as outer:
                    kmz_data = outer.read(kmz_name)
                with zipfile.ZipFile(io.BytesIO(kmz_data)) as kmz:
                    wpml = kmz.read('wpmz/waylines.wpml')
                root = ET.fromstring(wpml)

                headings = set()
                for pm in root.findall('.//kml:Placemark', ns):
                    h = pm.find('.//wpml:waypointHeadingAngle', ns)
                    if h is not None:
                        headings.add(int(h.text))
                self.assertEqual(headings, {expected_heading},
                    f"{kmz_name}: expected all waypoints heading={expected_heading}, got {headings}")

    def test_setup_waypoint_no_photo(self):
        """Setup waypoint (idx 0) must have gimbalRotate but NOT takePhoto."""
        kmz_data = generate_kmz(TILE_ZOOM, 62204, 50209, direction='ns')
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
        kmz_data = generate_kmz(TILE_ZOOM, 62204, 50209, direction='ns')
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
        """calculate_tile_stats returns expected top-level and budget keys."""
        stats = calculate_tile_stats(TILE_ZOOM, 62204, 50209)
        for key in ['tile', 'center', 'bounds', 'width_m', 'height_m',
                     'missions', 'budgets', 'total_waypoints', 'total_time_min']:
            self.assertIn(key, stats, f"Missing top-level key: {key}")

        # 5 missions with the exact numeric prefix naming
        for mname in ['1_2D', '2_3D-N', '3_3D-E', '4_3D-S', '5_3D-W']:
            self.assertIn(mname, stats['missions'], f"Missing mission: {mname}")

        # 3 budget levels
        for budget in ['1_battery', '3_batteries', '5_batteries']:
            self.assertIn(budget, stats['budgets'], f"Missing budget: {budget}")
            b = stats['budgets'][budget]
            for bkey in ['files', 'time_min', 'waypoints', 'facades_covered', 'description']:
                self.assertIn(bkey, b, f"Missing {budget}.{bkey}")

    def test_budget_monotonicity(self):
        """
        Each next battery must add strictly more info: more files,
        more time, more waypoints, more facades covered.
        """
        stats = calculate_tile_stats(TILE_ZOOM, 62204, 50209)
        b1 = stats['budgets']['1_battery']
        b3 = stats['budgets']['3_batteries']
        b5 = stats['budgets']['5_batteries']

        self.assertEqual(len(b1['files']), 1)
        self.assertEqual(len(b3['files']), 3)
        self.assertEqual(len(b5['files']), 5)

        # b3 must be a superset of b1, b5 must be a superset of b3
        self.assertTrue(set(b1['files']).issubset(set(b3['files'])))
        self.assertTrue(set(b3['files']).issubset(set(b5['files'])))

        self.assertLess(b1['time_min'], b3['time_min'])
        self.assertLess(b3['time_min'], b5['time_min'])

        self.assertEqual(b1['facades_covered'], 0)
        self.assertEqual(b3['facades_covered'], 2)
        self.assertEqual(b5['facades_covered'], 4)

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

                # Time: 5 missions (1 nadir at 80% + 4 oblique at 70%)
                # Reykjavik (smallest tile) ~29 min, equator ~92 min
                self.assertGreater(stats['total_time_min'], 20)
                self.assertLess(stats['total_time_min'], 120)

                # Waypoints: 5 missions with reduced oblique count
                self.assertGreater(stats['total_waypoints'], 80)
                self.assertLess(stats['total_waypoints'], 1500)

    def test_oblique_mission_cheaper_than_nadir(self):
        """
        In the stats dict, oblique missions (with 70% overlap) should have
        strictly fewer waypoints and less time than the nadir (80% overlap).
        This is the stats-level mirror of test_oblique_uses_sparser_spacing.
        """
        stats = calculate_tile_stats(TILE_ZOOM, 62204, 50209)
        nadir = stats['missions']['1_2D']
        for oblique_key in ['2_3D-N', '3_3D-E', '4_3D-S', '5_3D-W']:
            with self.subTest(mission=oblique_key):
                obl = stats['missions'][oblique_key]
                self.assertLess(obl['waypoints_count'], nadir['waypoints_count'],
                    f"{oblique_key} must have fewer waypoints than 1_2D")
                self.assertLess(obl['estimated_time_min'], nadir['estimated_time_min'],
                    f"{oblique_key} must take less time than 1_2D")
                self.assertEqual(obl['overlap_percent'], 70)
        self.assertEqual(nadir['overlap_percent'], 80)


# ── Direction classification tests ──────────────────────────────
#
# Covers classify_photo_direction() in geo/endpoints/opensky.py, which
# maps gimbal (pitch, yaw) EXIF to a direction bucket used by the coverage
# pills UI. Regression: nadir threshold -70°, oblique cardinals are ±45°
# around each of 0/90/180/270.

class DirectionClassificationTest(TestCase):
    def test_nadir_pitch(self):
        from geo.endpoints.opensky import classify_photo_direction
        self.assertEqual(classify_photo_direction(-90, 0), 'nadir')
        self.assertEqual(classify_photo_direction(-85, 180), 'nadir')
        self.assertEqual(classify_photo_direction(-71, None), 'nadir')  # yaw ignored for nadir

    def test_unknown_when_no_pitch(self):
        from geo.endpoints.opensky import classify_photo_direction
        self.assertEqual(classify_photo_direction(None, 0), 'unknown')
        self.assertEqual(classify_photo_direction(None, None), 'unknown')

    def test_unknown_oblique_without_yaw(self):
        from geo.endpoints.opensky import classify_photo_direction
        self.assertEqual(classify_photo_direction(-45, None), 'unknown')
        self.assertEqual(classify_photo_direction(0, None), 'unknown')

    def test_cardinal_buckets(self):
        """Each cardinal ±44° should classify to that cardinal. Boundaries exclusive."""
        from geo.endpoints.opensky import classify_photo_direction
        # North: [315, 360) ∪ [0, 45)
        for yaw in (0, 5, 44, 315, 350, 359):
            self.assertEqual(classify_photo_direction(-45, yaw), 'n', f"yaw={yaw}")
        # East: [45, 135)
        for yaw in (45, 90, 134):
            self.assertEqual(classify_photo_direction(-45, yaw), 'e', f"yaw={yaw}")
        # South: [135, 225)
        for yaw in (135, 180, 224):
            self.assertEqual(classify_photo_direction(-45, yaw), 's', f"yaw={yaw}")
        # West: [225, 315)
        for yaw in (225, 270, 314):
            self.assertEqual(classify_photo_direction(-45, yaw), 'w', f"yaw={yaw}")

    def test_yaw_normalized_modulo(self):
        """DJI yaw can be negative (-180..180) — normalized via mod 360."""
        from geo.endpoints.opensky import classify_photo_direction
        self.assertEqual(classify_photo_direction(-45, -90), 'w')   # -90 → 270
        self.assertEqual(classify_photo_direction(-45, -180), 's')  # -180 → 180
        self.assertEqual(classify_photo_direction(-45, 360), 'n')   # 360 → 0
        self.assertEqual(classify_photo_direction(-45, 450), 'e')   # 450 → 90

    def test_pitch_exactly_minus_70_is_oblique(self):
        """Edge: pitch == -70 classified as oblique (nadir is strict < -70)."""
        from geo.endpoints.opensky import classify_photo_direction
        self.assertEqual(classify_photo_direction(-70, 0), 'n')
        self.assertEqual(classify_photo_direction(-70.0001, 0), 'nadir')

    def test_direction_keys_constant(self):
        """All direction buckets listed in DIRECTION_KEYS, threshold positive."""
        from geo.endpoints.opensky import DIRECTION_KEYS, DIRECTION_COVERAGE_THRESHOLD, empty_direction_counts
        self.assertEqual(set(DIRECTION_KEYS), {'nadir', 'n', 'e', 's', 'w', 'unknown'})
        self.assertGreater(DIRECTION_COVERAGE_THRESHOLD, 0)
        # empty_direction_counts returns dict with all keys at 0
        ec = empty_direction_counts()
        self.assertEqual(sorted(ec.keys()), sorted(DIRECTION_KEYS))
        for v in ec.values():
            self.assertEqual(v, 0)
