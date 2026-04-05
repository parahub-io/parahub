"""
Transit real-time services: RouteCache, StopSnapper, and STT (Segment Travel Time) engine.

RouteCache: in-memory lookup tables refreshed every 10 min
  - route_info: route_source_id → (color, short_name, place_slug)
  - headsign_info: (route_source_id, direction_id) → headsign
  - shapes: (route_source_id, direction_id) → ShapeData
  - stop_seqs: (route_source_id, direction_id) → list[StopPoint]

StopSnapper: snap vehicle position to nearest stop using linear referencing
STT: segment travel time tracking + ETA prediction from observed vehicle movements
"""

import bisect
import orjson
import logging
import math
import time
from dataclasses import dataclass, field

from asgiref.sync import sync_to_async
from django.contrib.gis.geos import GEOSGeometry, LineString, Point

logger = logging.getLogger(__name__)

SNAP_MAX_DISTANCE_M = 500  # Skip if vehicle is >500m from shape


# ---------------------------------------------------------------------------
# Fast flat-earth distance (no trig per call, ~10x faster than haversine)
# Error <0.1% for distances <5km at latitudes 30-65°
# ---------------------------------------------------------------------------

def make_flat_dist(ref_lat: float):
    """
    Create a flat-earth distance function pre-computed for a reference latitude.
    Returns: flat_dist(lat1, lon1, lat2, lon2) → meters
    """
    cos_lat = math.cos(math.radians(ref_lat))
    mx = 111_320.0 * cos_lat  # meters per degree longitude
    my = 110_540.0             # meters per degree latitude

    def flat_dist(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        dx = (lon2 - lon1) * mx
        dy = (lat2 - lat1) * my
        return math.sqrt(dx * dx + dy * dy)

    return flat_dist


@dataclass
class StopPoint:
    """A stop in a route's ordered sequence (for STT engine)."""
    source_id: str
    lat: float
    lon: float


@dataclass
class StopOnShape:
    """A stop projected onto a shape line, sorted by fraction."""
    source_id: str
    name: str
    fraction: float  # 0.0–1.0 along shape


@dataclass
class ShapeData:
    """Pre-computed shape data for a (route, direction) pair."""
    line: LineString  # GEOS LineString in SRID 4326
    stops: list  # list[StopOnShape] sorted by fraction
    length_m: float = 0.0  # Approximate length in meters


class RouteCache:
    """
    In-memory cache of route info, headsigns, shapes, and stop sequences.
    Thread-safe for read access; refresh is called periodically from daemon.
    """

    def __init__(self):
        self.route_info: dict[str, tuple[str, str, str, int, str]] = {}  # source_id → (color, short_name, place_slug, route_type, route_slug)
        self.headsign_info: dict[tuple[str, int | None], str] = {}
        self.shapes: dict[tuple[str, int | None], ShapeData] = {}
        self.stop_seqs: dict[tuple[str, int | None], list[StopPoint]] = {}  # (route_src, dir) → ordered stops
        self._last_refresh = 0.0
        self._version = 0  # incremented on each refresh (for change detection)

    def is_stale(self, max_age_s: int = 600) -> bool:
        return (time.monotonic() - self._last_refresh) > max_age_s

    async def refresh(self, redis_conn=None, data_source_ids=None):
        """Reload all caches from DB (sync_to_async). Optionally write stop_seqs to Redis.

        Args:
            data_source_ids: If set, only load routes belonging to these TransitDataSource IDs.
                             None = load all routes (backward compatible).
        """
        t0 = time.monotonic()
        load_fn = lambda: self._load_all(data_source_ids)
        route_info, headsign_info, shapes, stop_seqs = await sync_to_async(
            load_fn, thread_sensitive=True
        )()
        self.route_info = route_info
        self.headsign_info = headsign_info
        self.shapes = shapes
        self.stop_seqs = stop_seqs
        self._version += 1
        self._last_refresh = time.monotonic()

        # Write stop_seqs to Redis for API access
        if redis_conn and stop_seqs:
            await self._write_stop_seqs_to_redis(redis_conn, stop_seqs)

        elapsed = (time.monotonic() - t0) * 1000
        ds_label = f" (ds={len(data_source_ids)})" if data_source_ids else ""
        logger.info(
            f"RouteCache refreshed{ds_label}: {len(route_info)} routes, "
            f"{len(headsign_info)} headsigns, {len(shapes)} shapes, "
            f"{len(stop_seqs)} stop sequences in {elapsed:.0f}ms"
        )

    @staticmethod
    async def _write_stop_seqs_to_redis(redis_conn, stop_seqs):
        """Write stop sequences to Redis for API endpoints to read."""
        pipe = redis_conn.pipeline(transaction=False)
        for (route_src, dir_id), stops in stop_seqs.items():
            key = f'transit:rstops:{route_src}:{dir_id}'
            # Store as JSON array of [source_id, lat, lon] for compactness
            value = orjson.dumps([[s.source_id, s.lat, s.lon] for s in stops])
            pipe.set(key, value, ex=3600)
        await pipe.execute()
        logger.debug(f"Wrote {len(stop_seqs)} stop sequences to Redis")

    def _load_all(self, data_source_ids=None):
        from geo.models import Route
        from django.db import connection

        # Resolve route IDs for filtering (Route→Agency→TransitDataSource)
        route_ids = None
        if data_source_ids:
            route_ids = list(
                Route.objects.filter(agency__data_source_id__in=data_source_ids)
                .values_list('id', flat=True)
            )
            if not route_ids:
                return {}, {}, {}, {}

        # 1. Route info (with place_slug for city-based WS broadcasting)
        route_info = {}
        route_qs = Route.objects.select_related('place').only(
            'source_id', 'route_color', 'short_name', 'place__slug', 'route_type', 'slug'
        )
        if route_ids is not None:
            route_qs = route_qs.filter(id__in=route_ids)
        for r in route_qs:
            place_slug = r.place.slug if r.place else ''
            route_info[r.source_id] = (r.route_color or '3b82f6', r.short_name, place_slug, r.route_type, r.slug or '')

        # 2. Headsign info — LATERAL join: one headsign per (route, direction), ~128ms vs 757ms
        headsign_info = {}
        headsign_sql = """
            SELECT r.source_id, d.direction_id, d.headsign
            FROM geo_route r
            CROSS JOIN LATERAL (
                SELECT DISTINCT ON (t.direction_id) t.direction_id, t.headsign
                FROM geo_trip t
                WHERE t.route_id = r.id AND t.headsign IS NOT NULL AND t.headsign != ''
                ORDER BY t.direction_id
            ) d
        """
        params = []
        if route_ids is not None:
            headsign_sql += " WHERE r.id = ANY(%s)"
            params = [route_ids]
        with connection.cursor() as cursor:
            cursor.execute(headsign_sql, params)
            for route_src, direction_id, headsign in cursor.fetchall():
                headsign_info[(route_src, direction_id)] = headsign

        # 3. Stop sequences for STT engine: (route_source_id, direction_id) → [StopPoint]
        # Raw SQL: 204K rows in ~600ms vs ~7s with ORM
        stop_seqs_raw = {}     # (route_source_id, direction_id) → [(sequence, StopPoint)]
        stop_sql = """
            SELECT r.source_id, rs.direction_id, rs.sequence,
                   s.source_id,
                   ST_Y(s.location::geometry), ST_X(s.location::geometry)
            FROM geo_routestop rs
            JOIN geo_route r ON r.id = rs.route_id
            JOIN geo_stop s ON s.id = rs.stop_id
        """
        params = []
        if route_ids is not None:
            stop_sql += " WHERE r.id = ANY(%s)"
            params = [route_ids]
        stop_sql += " ORDER BY rs.route_id, rs.direction_id, rs.sequence"

        with connection.cursor() as cursor:
            cursor.execute(stop_sql, params)
            for route_src, direction_id, sequence, stop_src, lat, lon in cursor.fetchall():
                # direction_id=NULL → treat as direction 0 (circular/legacy routes)
                dir_id = direction_id if direction_id is not None else 0
                key = (route_src, dir_id)
                stop_seqs_raw.setdefault(key, []).append(
                    (sequence, StopPoint(source_id=stop_src, lat=lat, lon=lon))
                )

        # Sort by sequence and extract StopPoints
        stop_seqs = {}
        for key, items in stop_seqs_raw.items():
            items.sort(key=lambda x: x[0])
            stop_seqs[key] = [sp for _, sp in items]

        # 4a. Stop projections onto shapes (ST_LineLocatePoint in DB: ~4s vs ~27s in Python)
        # Uses geo_shape table (deduplicated, ~17K rows) instead of scanning 1.28M trips.
        # CTE picks one trip per (route, direction), then JOINs to shape (~7K rows).
        route_filter = ""
        proj_params = []
        if route_ids is not None:
            route_filter = " WHERE t.route_id = ANY(%s)"
            proj_params = [route_ids]

        projections = {}  # (route_source_id, direction_id) → [(stop_source_id, stop_name, fraction)]
        with connection.cursor() as cursor:
            cursor.execute(f"""
                WITH route_shapes AS (
                    SELECT DISTINCT ON (t.route_id, t.direction_id)
                        t.route_id, t.direction_id, t.shape_ref_id
                    FROM geo_trip t
                    {route_filter}
                      {"AND" if route_filter else "WHERE"} t.shape_ref_id IS NOT NULL
                    ORDER BY t.route_id, t.direction_id
                )
                SELECT r.source_id, rs2.direction_id,
                       s.source_id, s.name,
                       ST_LineLocatePoint(sh.geometry::geometry, s.location::geometry)
                FROM route_shapes rs2
                JOIN geo_route r ON r.id = rs2.route_id
                JOIN geo_shape sh ON sh.id = rs2.shape_ref_id
                JOIN geo_routestop rs ON rs.route_id = rs2.route_id
                JOIN geo_stop s ON s.id = rs.stop_id
            """, proj_params)
            for route_src, dir_id, stop_src, stop_name, fraction in cursor.fetchall():
                key = (route_src, dir_id)
                projections.setdefault(key, []).append((stop_src, stop_name, fraction))

        # 4b. Shapes: geometry + precomputed length, combined with stop projections
        shapes = {}
        with connection.cursor() as cursor:
            cursor.execute(f"""
                WITH route_trips AS (
                    SELECT DISTINCT ON (t.route_id, t.direction_id)
                        t.route_id, t.direction_id, t.shape_ref_id
                    FROM geo_trip t
                    {route_filter}
                      {"AND" if route_filter else "WHERE"} t.shape_ref_id IS NOT NULL
                    ORDER BY t.route_id, t.direction_id
                )
                SELECT r.source_id, rt.direction_id, s.geometry, s.length_m
                FROM route_trips rt
                JOIN geo_route r ON r.id = rt.route_id
                JOIN geo_shape s ON s.id = rt.shape_ref_id
            """, proj_params)
            for route_src, direction_id, shape_wkb, length_m in cursor.fetchall():
                line = GEOSGeometry(shape_wkb)
                if not line or len(line.coords) < 2:
                    continue

                key = (route_src, direction_id)
                stops_proj = projections.get(key, [])
                stops_on_shape = sorted(
                    [StopOnShape(source_id=s, name=n, fraction=f) for s, n, f in stops_proj],
                    key=lambda x: x.fraction
                )
                shapes[key] = ShapeData(
                    line=line,
                    stops=stops_on_shape,
                    length_m=length_m,
                )

        return route_info, headsign_info, shapes, stop_seqs


class StopSnapper:
    """
    Snap a vehicle position to the nearest stop on its route shape.

    Algorithm:
    1. Find ShapeData for (route_source_id, direction_id)
    2. Project vehicle point onto shape → fraction
    3. If distance > 500m → skip (vehicle off-route)
    4. Binary search sorted stops → nearest stop by fraction
    """

    def __init__(self, route_cache: RouteCache):
        self.cache = route_cache

    def snap(self, lat: float, lon: float, route_source_id: str,
             direction_id: int | None) -> tuple[str, int | None] | None:
        """
        Try to snap vehicle to nearest stop.

        Returns:
            (stop_source_id, direction_id) or None if can't snap
        """
        # Try exact key first
        shape_data = self.cache.shapes.get((route_source_id, direction_id))

        # If direction unknown, try both
        if shape_data is None and direction_id is None:
            shape_data_0 = self.cache.shapes.get((route_source_id, 0))
            shape_data_1 = self.cache.shapes.get((route_source_id, 1))
            if shape_data_0 and shape_data_1:
                # Pick the one closer to the vehicle
                pt = Point(lon, lat, srid=4326)
                d0 = shape_data_0.line.distance(pt)
                d1 = shape_data_1.line.distance(pt)
                shape_data = shape_data_0 if d0 <= d1 else shape_data_1
                direction_id = 0 if d0 <= d1 else 1
            elif shape_data_0:
                shape_data = shape_data_0
                direction_id = 0
            elif shape_data_1:
                shape_data = shape_data_1
                direction_id = 1

        if shape_data is None or not shape_data.stops:
            return None

        pt = Point(lon, lat, srid=4326)

        # Check distance from shape (rough degrees → meters)
        dist_deg = shape_data.line.distance(pt)
        # At ~38° latitude (Portugal), 1 deg lon ≈ 87km, 1 deg lat ≈ 111km
        dist_m = dist_deg * 100000  # Rough approximation
        if dist_m > SNAP_MAX_DISTANCE_M:
            return None

        # Project vehicle onto shape
        vehicle_fraction = shape_data.line.project_normalized(pt)

        # Binary search for nearest stop
        fractions = [s.fraction for s in shape_data.stops]
        idx = bisect.bisect_left(fractions, vehicle_fraction)

        # Check neighbors
        best_stop = None
        best_diff = float('inf')
        for candidate_idx in [idx - 1, idx, idx + 1]:
            if 0 <= candidate_idx < len(shape_data.stops):
                diff = abs(shape_data.stops[candidate_idx].fraction - vehicle_fraction)
                if diff < best_diff:
                    best_diff = diff
                    best_stop = shape_data.stops[candidate_idx]

        if best_stop is None:
            return None

        return (best_stop.source_id, direction_id)


def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """
    Convert lat/lon to tile coordinates (x, y) for given zoom level.
    Shared utility used by both MapPresenceConsumer and TransitConsumer.
    """
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (x, y)


# ---------------------------------------------------------------------------
# STT: Segment Travel Time engine
# ---------------------------------------------------------------------------

# Direction states
ST_TENTATIVE = 't'   # feed hint accepted, awaiting verification
ST_DUAL = 'd'        # no hint or hint failed, testing both directions
ST_CONFIRMED = 'c'   # direction verified by observed movement

# STT config
STT_FIFO_SIZE = 10           # max observations per segment
STT_MIN_TRAVEL_S = 10        # reject segment times below this
STT_ZOMBIE_THRESHOLD_S = 120 # no movement for this long → zombie
STT_ZOMBIE_MOVE_M = 10       # minimum movement to count as "moved"
STT_GPS_JUMP_M = 2000        # re-initialize if vehicle is this far from expected stop
STT_STALL_POLLS = 3          # re-initialize direction after this many polls with no progress
STT_VPREV_TTL = 300          # Redis TTL for vehicle state
STT_SEGMENT_TTL = 1800       # Redis TTL for segment FIFO


class SttProcessor:
    """
    Segment Travel Time processor.

    Tracks vehicle stop transitions, records segment travel times in Redis FIFO lists,
    detects zombie vehicles. Runs per-poll in the daemon, batched per data source.

    All Redis operations are pipelined for performance (2 round-trips per data source).
    """

    def __init__(self, route_cache: RouteCache):
        self.cache = route_cache
        self._flat_dist = make_flat_dist(45.0)  # good enough for 30-65° latitude range
        self._last_cache_ver = route_cache._version

    async def process_vehicles(self, redis_conn, ds_id: str, vehicles: list[dict], now: float):
        """
        Process a batch of vehicles from one data source.
        Updates vprev state, records segment times, marks zombies.

        Mutates vehicle dicts in-place: adds 'z' (zombie), 'eta_next' (seconds to next stop).
        """
        if not vehicles:
            return

        # Detect cache refresh — stop sequences may have changed
        cache_changed = self.cache._version != self._last_cache_ver
        if cache_changed:
            self._last_cache_ver = self.cache._version

        dist = self._flat_dist

        # --- Phase 1: Read all vprev states in one pipeline ---
        vid_to_vehicle = {}
        vprev_keys = []
        for v in vehicles:
            vid = v.get('v', '')
            route_src = v.get('r', '')
            if not vid or not route_src:
                continue
            vid_to_vehicle[vid] = v
            vprev_keys.append(f'transit:vprev:{ds_id}:{vid}')

        if not vprev_keys:
            return

        pipe = redis_conn.pipeline(transaction=False)
        for key in vprev_keys:
            pipe.hgetall(key)
        raw_states = await pipe.execute()

        # --- Phase 2: Process each vehicle (pure Python, no I/O) ---
        writes = []       # (key, hash_dict) for vprev updates
        segments = []      # (stt_key, travel_time) for LPUSH
        deletes = []       # vprev keys to delete (end of route)

        vids = list(vid_to_vehicle.keys())

        for i, vid in enumerate(vids):
            v = vid_to_vehicle[vid]
            raw = raw_states[i]
            vprev_key = vprev_keys[i]

            vlat, vlon = v['lat'], v['lon']
            route_src = v.get('r', '')
            feed_dir = v.get('d')  # hint from feed (may be None/unreliable)

            # Decode vprev from Redis (bytes → str/float)
            state = {}
            if raw:
                for k_bytes, v_bytes in raw.items():
                    k = k_bytes.decode() if isinstance(k_bytes, bytes) else k_bytes
                    val = v_bytes.decode() if isinstance(v_bytes, bytes) else v_bytes
                    state[k] = val

            if not state or state.get('r') != route_src or cache_changed:
                # --- INIT: vehicle first seen, route changed, or cache refreshed ---
                new_state = self._init_vehicle(
                    route_src, feed_dir, vlat, vlon, now, ds_id
                )
                if new_state:
                    writes.append((vprev_key, new_state))
                continue

            # --- Zombie detection ---
            prev_lat = float(state.get('lat', 0))
            prev_lon = float(state.get('lon', 0))
            mt = float(state.get('mt', now))

            moved = dist(vlat, vlon, prev_lat, prev_lon) > STT_ZOMBIE_MOVE_M
            if moved:
                mt = now

            is_zombie = (now - mt) > STT_ZOMBIE_THRESHOLD_S
            if is_zombie:
                v['z'] = 1
                # Update position + mt only, don't process transitions
                state.update({'lat': str(vlat), 'lon': str(vlon), 'mt': str(mt)})
                writes.append((vprev_key, state))
                continue

            # --- Direction resolution + forward tracking ---
            st = state.get('st', ST_DUAL)
            stall = int(state.get('stall', 0))

            if st == ST_TENTATIVE:
                result = self._verify_tentative(state, vlat, vlon, route_src, ds_id, stall)
            elif st == ST_DUAL:
                result = self._verify_dual(state, vlat, vlon, route_src, ds_id)
            else:
                # ST_CONFIRMED — normal forward tracking
                result = self._track_forward(state, vlat, vlon, route_src, ds_id, now, stall)

            if result is None:
                # Couldn't process (no stop sequence etc) — just update position
                state.update({'lat': str(vlat), 'lon': str(vlon), 'mt': str(mt)})
                writes.append((vprev_key, state))
                continue

            action, new_state = result
            new_state['lat'] = str(vlat)
            new_state['lon'] = str(vlon)
            new_state['mt'] = str(mt)

            if action == 'delete':
                deletes.append(vprev_key)
            elif action == 'segment':
                # Segment traversal recorded
                seg_key = new_state.pop('_seg_key', None)
                seg_time = new_state.pop('_seg_time', None)
                if seg_key and seg_time:
                    segments.append((seg_key, seg_time))
                writes.append((vprev_key, new_state))
            else:
                writes.append((vprev_key, new_state))

            # Add ETA to next stop for broadcast
            if new_state.get('st') in (ST_CONFIRMED,) and new_state.get('d') != '-1':
                eta_next = self._calc_eta_next(new_state, ds_id, vlat, vlon)
                if eta_next is not None:
                    v['eta'] = eta_next

        # --- Phase 3: Write all updates in one pipeline ---
        if writes or segments or deletes:
            pipe = redis_conn.pipeline(transaction=False)
            for key, data in writes:
                pipe.hset(key, mapping=data)
                pipe.expire(key, STT_VPREV_TTL)
            for stt_key, travel_time in segments:
                pipe.lpush(stt_key, str(int(travel_time)))
                pipe.ltrim(stt_key, 0, STT_FIFO_SIZE - 1)
                pipe.expire(stt_key, STT_SEGMENT_TTL)
            for key in deletes:
                pipe.delete(key)
            await pipe.execute()

        if segments:
            logger.debug(f'STT [{ds_id[:8]}]: {len(segments)} segment times recorded')

    def _init_vehicle(self, route_src, feed_dir, lat, lon, now, ds_id):
        """Initialize tracking for a newly seen vehicle."""
        dist = self._flat_dist
        seq0 = self.cache.stop_seqs.get((route_src, 0))
        seq1 = self.cache.stop_seqs.get((route_src, 1))

        if not seq0 and not seq1:
            return None  # no stop data for this route

        # Case 3: single direction
        if seq0 and not seq1:
            idx = self._nearest_stop_idx(seq0, lat, lon, dist)
            return {
                'r': route_src, 'd': '0', 'st': ST_CONFIRMED,
                'idx': str(idx), 't': str(now), 'stall': '0',
                'lat': str(lat), 'lon': str(lon), 'mt': str(now),
            }
        if seq1 and not seq0:
            idx = self._nearest_stop_idx(seq1, lat, lon, dist)
            return {
                'r': route_src, 'd': '1', 'st': ST_CONFIRMED,
                'idx': str(idx), 't': str(now), 'stall': '0',
                'lat': str(lat), 'lon': str(lon), 'mt': str(now),
            }

        # Both directions exist
        idx0 = self._nearest_stop_idx(seq0, lat, lon, dist)
        idx1 = self._nearest_stop_idx(seq1, lat, lon, dist)

        # Case 1: feed provides direction hint
        if feed_dir is not None and feed_dir in (0, 1):
            primary_d = str(feed_dir)
            alt_d = str(1 - feed_dir)
            primary_idx = idx0 if feed_dir == 0 else idx1
            alt_idx = idx1 if feed_dir == 0 else idx0
            return {
                'r': route_src, 'd': primary_d, 'st': ST_TENTATIVE,
                'idx': str(primary_idx), 'idx_alt': str(alt_idx), 'd_alt': alt_d,
                't': str(now), 'stall': '0',
                'lat': str(lat), 'lon': str(lon), 'mt': str(now),
            }

        # Case 2: no direction hint
        return {
            'r': route_src, 'd': '-1', 'st': ST_DUAL,
            'idx0': str(idx0), 'idx1': str(idx1),
            't': str(now), 'stall': '0',
            'lat': str(lat), 'lon': str(lon), 'mt': str(now),
        }

    def _verify_tentative(self, state, lat, lon, route_src, ds_id, stall):
        """Verify direction hint from feed."""
        dist = self._flat_dist
        d = int(state['d'])
        idx = int(state['idx'])
        seq = self.cache.stop_seqs.get((route_src, d))

        if not seq or idx + 1 >= len(seq):
            return None

        # Check forward progress in hinted direction
        d_cur = dist(lat, lon, seq[idx].lat, seq[idx].lon)
        d_nxt = dist(lat, lon, seq[idx + 1].lat, seq[idx + 1].lon)

        if d_nxt < d_cur:
            # Hint confirmed
            new_state = dict(state)
            new_state['st'] = ST_CONFIRMED
            new_state['stall'] = '0'
            return ('update', new_state)

        # Try alternative
        alt_d = int(state.get('d_alt', 1 - d))
        alt_idx = int(state.get('idx_alt', 0))
        alt_seq = self.cache.stop_seqs.get((route_src, alt_d))

        if alt_seq and alt_idx + 1 < len(alt_seq):
            d_cur_alt = dist(lat, lon, alt_seq[alt_idx].lat, alt_seq[alt_idx].lon)
            d_nxt_alt = dist(lat, lon, alt_seq[alt_idx + 1].lat, alt_seq[alt_idx + 1].lon)

            if d_nxt_alt < d_cur_alt:
                # Hint was wrong, flip
                logger.info(
                    f'STT direction flip: feed={d} actual={alt_d} '
                    f'route={route_src} ds={ds_id[:8]}'
                )
                new_state = dict(state)
                new_state['d'] = str(alt_d)
                new_state['idx'] = str(alt_idx)
                new_state['st'] = ST_CONFIRMED
                new_state['stall'] = '0'
                # Clean up alt fields
                new_state.pop('idx_alt', None)
                new_state.pop('d_alt', None)
                return ('update', new_state)

        # Neither progressed — increment stall
        stall += 1
        new_state = dict(state)
        new_state['stall'] = str(stall)
        if stall >= 5:
            # Degrade to dual
            new_state['st'] = ST_DUAL
            new_state['d'] = '-1'
            idx0 = int(state['idx']) if d == 0 else int(state.get('idx_alt', 0))
            idx1 = int(state.get('idx_alt', 0)) if d == 0 else int(state['idx'])
            new_state['idx0'] = str(idx0)
            new_state['idx1'] = str(idx1)
            new_state['stall'] = '0'
        return ('update', new_state)

    def _verify_dual(self, state, lat, lon, route_src, ds_id):
        """Test both directions when no hint available."""
        dist = self._flat_dist
        idx0 = int(state.get('idx0', 0))
        idx1 = int(state.get('idx1', 0))
        seq0 = self.cache.stop_seqs.get((route_src, 0))
        seq1 = self.cache.stop_seqs.get((route_src, 1))

        progress0 = False
        progress1 = False

        if seq0 and idx0 + 1 < len(seq0):
            progress0 = dist(lat, lon, seq0[idx0 + 1].lat, seq0[idx0 + 1].lon) < \
                         dist(lat, lon, seq0[idx0].lat, seq0[idx0].lon)

        if seq1 and idx1 + 1 < len(seq1):
            progress1 = dist(lat, lon, seq1[idx1 + 1].lat, seq1[idx1 + 1].lon) < \
                         dist(lat, lon, seq1[idx1].lat, seq1[idx1].lon)

        new_state = dict(state)

        if progress0 and not progress1:
            new_state['d'] = '0'
            new_state['idx'] = str(idx0)
            new_state['st'] = ST_CONFIRMED
            new_state['stall'] = '0'
            new_state.pop('idx0', None)
            new_state.pop('idx1', None)
            return ('update', new_state)

        if progress1 and not progress0:
            new_state['d'] = '1'
            new_state['idx'] = str(idx1)
            new_state['st'] = ST_CONFIRMED
            new_state['stall'] = '0'
            new_state.pop('idx0', None)
            new_state.pop('idx1', None)
            return ('update', new_state)

        # Both or neither — wait
        return ('update', new_state)

    def _is_circular(self, seq) -> bool:
        """Check if route is circular (first stop ≈ last stop, within 200m)."""
        if len(seq) < 3:
            return False
        return self._flat_dist(seq[0].lat, seq[0].lon, seq[-1].lat, seq[-1].lon) < 200

    def _track_forward(self, state, lat, lon, route_src, ds_id, now, stall):
        """Track confirmed vehicle along its stop sequence."""
        dist = self._flat_dist
        d = int(state['d'])
        idx = int(state['idx'])
        t_last = float(state.get('t', now))
        seq = self.cache.stop_seqs.get((route_src, d))

        if not seq or idx + 1 >= len(seq):
            return ('delete', dict(state))  # end of route

        d_cur = dist(lat, lon, seq[idx].lat, seq[idx].lon)
        d_nxt = dist(lat, lon, seq[idx + 1].lat, seq[idx + 1].lon)

        new_state = dict(state)

        if d_nxt < d_cur:
            # Forward progress — record segment
            travel_time = now - t_last
            stop_from = seq[idx].source_id
            stop_to = seq[idx + 1].source_id

            idx += 1
            new_state['idx'] = str(idx)
            new_state['t'] = str(now)
            new_state['stall'] = '0'

            # Check for skip (bus passed multiple stops in one poll)
            while idx + 1 < len(seq):
                if dist(lat, lon, seq[idx + 1].lat, seq[idx + 1].lon) < \
                   dist(lat, lon, seq[idx].lat, seq[idx].lon):
                    idx += 1
                    new_state['idx'] = str(idx)
                else:
                    break

            # End of route check
            if idx >= len(seq) - 1:
                if self._is_circular(seq):
                    # Circular route: wrap around to start, keep tracking
                    new_state['idx'] = '0'
                    new_state['t'] = str(now)
                else:
                    return ('delete', new_state)

            # Validate and record segment time
            seg_dist = dist(seq[idx - 1].lat, seq[idx - 1].lon,
                           seq[idx].lat, seq[idx].lon) if idx > 0 else 500
            # Dynamic max: distance / 3 m/s (≈10 km/h, crawling in traffic)
            max_travel = max(seg_dist / 3.0, 60)
            if STT_MIN_TRAVEL_S < travel_time < max_travel:
                stt_key = f'transit:stt:{ds_id}:{stop_from}:{stop_to}'
                new_state['_seg_key'] = stt_key
                new_state['_seg_time'] = travel_time

            return ('segment', new_state)

        # No progress
        stall += 1
        new_state['stall'] = str(stall)

        # GPS jump check
        if d_cur > STT_GPS_JUMP_M:
            reinit = self._init_vehicle(route_src, None, lat, lon, now, ds_id)
            if reinit:
                return ('update', reinit)

        # Stall → re-init as dual
        if stall >= STT_STALL_POLLS:
            reinit = self._init_vehicle(route_src, None, lat, lon, now, ds_id)
            if reinit:
                return ('update', reinit)

        return ('update', new_state)

    def _calc_eta_next(self, state, ds_id, vlat, vlon):
        """Quick ETA to next stop (for broadcast). Returns seconds or None."""
        # This is a lightweight estimate — full ETA chain is in the API endpoint
        d = int(state.get('d', -1))
        idx = int(state.get('idx', 0))
        route_src = state.get('r', '')
        seq = self.cache.stop_seqs.get((route_src, d))

        if not seq or idx + 1 >= len(seq):
            return None

        dist = self._flat_dist
        d_next = dist(vlat, vlon, seq[idx + 1].lat, seq[idx + 1].lon)

        # Very rough: assume 20 km/h average urban speed
        eta = d_next / 5.56  # 5.56 m/s ≈ 20 km/h
        return max(0, int(eta))

    @staticmethod
    def _nearest_stop_idx(seq: list[StopPoint], lat: float, lon: float, dist_fn) -> int:
        """Find index of nearest stop in sequence by flat distance."""
        best_idx = 0
        best_dist = float('inf')
        for i, sp in enumerate(seq):
            d = dist_fn(lat, lon, sp.lat, sp.lon)
            if d < best_dist:
                best_dist = d
                best_idx = i
        return best_idx
