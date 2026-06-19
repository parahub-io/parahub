"""
Drone reachability for OpenSky mission planning.

From a launch point, classify Z17 Web Mercator tiles by whether a DJI-class
drone can actually capture them, accounting for FOUR constraints:

  A. Range      — radial disk (drone flies straight, NOT a road isochrone):
                  min(radio link range, battery round-trip with RTH). Bounded
                  by `radius_m` here; per-tile battery cost is a separate UI readout.
  B. Terrain ceiling — generated missions fly relativeToStartPoint (constant
                  ABSOLUTE altitude = elev(launch) + AGL everywhere, NO terrain
                  following). Over rising ground the clearance shrinks, so a hill
                  whose surface reaches within `margin` of that plane is unsafe.
  C. RC line-of-sight (viewshed) — terrain between the RC and the drone over the
                  tile occludes the radio link. Optical LOS + Earth-curvature term.
  D. Regulatory — a tile inside a PROHIBITED UAS geo-zone (ED-269, e.g. ANAC PT)
                  whose vertical band overlaps the flight altitude is hard no-fly.
                  Advisory zones (authorisation/conditional) are NOT folded into
                  tile status; they are returned as a separate map overlay.

Elevation source: Valhalla /height (SRTM), already running on :8002. No new infra.

Honest limits (this is a PLANNER, not collision-avoidance):
  - SRTM ~30-90 m, coarse surface model — does NOT see a single tower / power
    line / tree / building edge. Hill-awareness only.
  - LOS is optical, not an RF model (no Fresnel / diffraction / foliage / multipath).
  - Battery range ignores wind/temperature — keep a generous reserve upstream.
"""

import math
import logging

import requests
from django.core.cache import cache

from geo.mission_generator import (
    TILE_ZOOM, tile_bounds, tile_center, latlng_to_tile,
)

logger = logging.getLogger(__name__)

VALHALLA_URL = "http://127.0.0.1:8002"

# --- Tunables (mirrored as UI sliders; defaults chosen conservatively) ---
DEFAULT_AGL_M = 100        # flight height above launch (= mission_generator ALTITUDE_M)
DEFAULT_MARGIN_M = 30      # safety clearance terrain<->flight plane (SRTM is coarse)
DEFAULT_RADIUS_M = 2000    # practical extended-VLOS disk
DEFAULT_RC_HEIGHT_M = 2    # RC antenna height above launch ground
MAX_RADIUS_M = 10000       # hard cap (cost bound)
MAX_AGL_M = 120            # EASA open-category legal ceiling (AGL)
MAX_TILES = 2500           # refuse absurd disks

CEIL_GRID = 3              # NxN terrain samples per tile for the ceiling max
LOS_STEP_M = 30            # viewshed sample spacing (~SRTM resolution)
LOS_MAX_SAMPLES = 64       # cap samples per ray (long rays use a coarser step)
HEIGHT_CHUNK = 500         # points per Valhalla /height request

EARTH_R = 6371000.0
EARTH_R_EFF = EARTH_R * 4.0 / 3.0   # standard 4/3 effective radius (radio refraction)

CACHE_TTL = 7 * 24 * 3600  # elevation is static -> cache hard


def _haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return EARTH_R * 2 * math.asin(math.sqrt(a))


def _fetch_heights(points):
    """points: list[(lat, lon)] -> list[float] elevations (None coerced to 0.0).

    Chunked POST to Valhalla /height (plain, no `range` — we own the geometry,
    so cumulative distances aren't needed and would block batching)."""
    out = []
    for i in range(0, len(points), HEIGHT_CHUNK):
        chunk = points[i:i + HEIGHT_CHUNK]
        body = {"shape": [{"lat": la, "lon": lo} for la, lo in chunk]}
        try:
            r = requests.post(f"{VALHALLA_URL}/height", json=body, timeout=25)
            r.raise_for_status()
            heights = r.json().get("height", [])
        except Exception as e:
            logger.warning("Valhalla /height failed: %s", e)
            raise RuntimeError("elevation service unavailable") from e
        if len(heights) != len(chunk):
            raise RuntimeError("elevation service returned wrong count")
        out.extend(0.0 if h is None else float(h) for h in heights)
    return out


def _tiles_in_disk(lat, lng, radius_m):
    """All Z17 tiles whose center is within radius_m of (lat, lng)."""
    dlat = radius_m / 111320.0
    dlng = radius_m / (111320.0 * max(0.01, math.cos(math.radians(lat))))
    x_lo, y_hi = latlng_to_tile(lat + dlat, lng - dlng, TILE_ZOOM)  # NW (smaller y)
    x_hi, y_lo = latlng_to_tile(lat - dlat, lng + dlng, TILE_ZOOM)  # SE
    tiles = []
    for x in range(min(x_lo, x_hi), max(x_lo, x_hi) + 1):
        for y in range(min(y_lo, y_hi), max(y_lo, y_hi) + 1):
            clat, clng = tile_center(TILE_ZOOM, x, y)
            if _haversine_m(lat, lng, clat, clng) <= radius_m:
                tiles.append((x, y, clat, clng))
    return tiles


def _ceiling_samples(x, y):
    """NxN (lat, lon) grid inside tile bounds for the terrain-max."""
    w, s, e, n = tile_bounds(TILE_ZOOM, x, y)
    pts = []
    for iy in range(CEIL_GRID):
        fy = (iy + 0.5) / CEIL_GRID
        la = s + (n - s) * fy
        for ix in range(CEIL_GRID):
            fx = (ix + 0.5) / CEIL_GRID
            lo = w + (e - w) * fx
            pts.append((la, lo))
    return pts


def _los_samples(lat, lng, clat, clng):
    """Intermediate (lat, lon) points along the launch->tile-center ray, with
    their distances from launch. Endpoints excluded (they never self-occlude)."""
    D = _haversine_m(lat, lng, clat, clng)
    if D < LOS_STEP_M:
        return [], D
    n = min(LOS_MAX_SAMPLES, int(D / LOS_STEP_M))
    step = D / (n + 1)
    pts, dists = [], []
    for k in range(1, n + 1):
        f = (k * step) / D
        pts.append((lat + (clat - lat) * f, lng + (clng - lng) * f))
        dists.append(k * step)
    return list(zip(pts, dists)), D


def _restricted_indices(results, lat, lng, radius_m, agl, flight_plane):
    """Indices of currently-`capturable` tiles whose center lies inside a
    PROHIBITED UAS geo-zone overlapping the flight altitude band. Hard no-fly
    only — advisory zones (authorisation/conditional) are exposed as a separate
    overlay (see drone_zones_geojson), not folded into per-tile status."""
    from django.contrib.gis.geos import Point
    from django.contrib.gis.measure import D
    from geo.models import DroneZone

    center = Point(lng, lat, srid=4326)
    qs = DroneZone.objects.filter(
        restriction=DroneZone.Restriction.PROHIBITED,
        geometry__dwithin=(center, D(m=radius_m)),
    )
    geoms = []
    for z in qs:
        # AGL zone: relevant if it starts at/below our max AGL band; AMSL zone:
        # compare its floor against our absolute flight plane.
        ceiling = agl if z.lower_ref == "AGL" else flight_plane
        if z.lower_limit_m <= ceiling:
            geoms.append(z.geometry)
    if not geoms:
        return set()

    union = geoms[0]
    for g in geoms[1:]:
        union = union.union(g)
    prep = union.prepared

    blocked = set()
    for i, row in enumerate(results):
        if row[6] != "capturable":
            continue
        if prep.intersects(Point(row[3], row[2], srid=4326)):  # (lng, lat)
            blocked.add(i)
    return blocked


def compute_reachability(lat, lng, agl=DEFAULT_AGL_M, margin=DEFAULT_MARGIN_M,
                         radius_m=DEFAULT_RADIUS_M, rc_height=DEFAULT_RC_HEIGHT_M):
    """Return reachability classification for all Z17 tiles in the disk.

    {launch:{lat,lng,elev}, params:{...}, tiles:[{x,y,status,max_terrain,clearance}],
     stats:{capturable,terrain,los,restricted,total}}
     status in capturable|terrain|los|restricted.
    """
    agl = max(1.0, min(float(agl), MAX_AGL_M))
    margin = max(0.0, min(float(margin), 200.0))
    radius_m = max(50.0, min(float(radius_m), MAX_RADIUS_M))
    rc_height = max(0.0, min(float(rc_height), 50.0))

    ckey = "dronereach:%.5f:%.5f:%d:%d:%d:%d" % (
        lat, lng, int(agl), int(margin), int(radius_m), int(rc_height))
    cached = cache.get(ckey)
    if cached is not None:
        return cached

    launch_elev = _fetch_heights([(lat, lng)])[0]
    flight_plane = launch_elev + agl   # constant absolute altitude (relativeToStartPoint)
    rc_h = launch_elev + rc_height

    tiles = _tiles_in_disk(lat, lng, radius_m)
    if len(tiles) > MAX_TILES:
        raise ValueError(f"radius too large ({len(tiles)} tiles > {MAX_TILES}); reduce radius")

    # --- Filter B: terrain ceiling (batched ceiling grid for every tile) ---
    ceil_pts, ceil_slices = [], []
    for (x, y, clat, clng) in tiles:
        pts = _ceiling_samples(x, y)
        ceil_slices.append((len(ceil_pts), len(ceil_pts) + len(pts)))
        ceil_pts.extend(pts)
    ceil_h = _fetch_heights(ceil_pts) if ceil_pts else []

    results = []      # (x, y, clat, clng, max_terrain, clearance, status)
    los_candidates = []
    for idx, (x, y, clat, clng) in enumerate(tiles):
        a, b = ceil_slices[idx]
        max_terrain = max(ceil_h[a:b]) if b > a else launch_elev
        clearance = flight_plane - max_terrain
        if clearance < margin:
            results.append([x, y, clat, clng, max_terrain, clearance, "terrain"])
        else:
            results.append([x, y, clat, clng, max_terrain, clearance, None])
            los_candidates.append(idx)

    # --- Filter C: viewshed / RC line-of-sight (batched across all rays) ---
    los_pts = []
    los_meta = []     # (result_idx, start, end, dists, D)
    for idx in los_candidates:
        x, y, clat, clng = results[idx][0], results[idx][1], results[idx][2], results[idx][3]
        pd, D = _los_samples(lat, lng, clat, clng)
        start = len(los_pts)
        for (pt, _d) in pd:
            los_pts.append(pt)
        los_meta.append((idx, start, len(los_pts), [d for (_p, d) in pd], D))
    los_h = _fetch_heights(los_pts) if los_pts else []

    for (idx, start, end, dists, D) in los_meta:
        blocked = False
        if D > 0:
            for j, d in enumerate(dists):
                terrain = los_h[start + j]
                # line of sight from RC (rc_h) to drone over tile (flight_plane)
                line = rc_h + (flight_plane - rc_h) * (d / D)
                curv = d * (D - d) / (2 * EARTH_R_EFF)   # Earth bulge raises terrain
                if terrain + curv > line:
                    blocked = True
                    break
        results[idx][6] = "los" if blocked else "capturable"

    # --- Filter D: regulatory no-fly (hard PROHIBITED geo-zones only) ---
    for i in _restricted_indices(results, lat, lng, radius_m, agl, flight_plane):
        results[i][6] = "restricted"

    out_tiles, n_cap, n_terr, n_los, n_restr = [], 0, 0, 0, 0
    for (x, y, clat, clng, max_terrain, clearance, status) in results:
        if status == "capturable":
            n_cap += 1
        elif status == "terrain":
            n_terr += 1
        elif status == "los":
            n_los += 1
        elif status == "restricted":
            n_restr += 1
        out_tiles.append({
            "x": x, "y": y,
            "status": status,
            "max_terrain": round(max_terrain, 1),
            "clearance": round(clearance, 1),
        })

    result = {
        "launch": {"lat": lat, "lng": lng, "elev": round(launch_elev, 1)},
        "params": {
            "agl": agl, "margin": margin, "radius_m": radius_m,
            "rc_height": rc_height, "flight_plane": round(flight_plane, 1),
            "tile_zoom": TILE_ZOOM,
        },
        "tiles": out_tiles,
        "stats": {"capturable": n_cap, "terrain": n_terr, "los": n_los,
                  "restricted": n_restr, "total": len(out_tiles)},
    }
    cache.set(ckey, result, CACHE_TTL)
    return result
