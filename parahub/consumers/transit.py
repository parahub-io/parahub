"""
WebSocket consumer for transit vehicle real-time updates.

URL: ws/v1/transit/
Public — no authentication required.

Bbox-based spatial subscription using Redis GEO (GEOSEARCH).
Daemon writes GEOADD + HSET per vehicle, publishes `transit:tick` every poll cycle.
Consumer does GEOSEARCH on tick → sends vehicles in client's bbox.

Route subscription also computes per-stop ETA predictions (both directions)
from STT segment data in Redis and pushes them with each update.

Client sends:
    { "type": "subscribe_vehicles", "bbox": [west, south, east, north] }
    { "type": "update_bbox", "bbox": [west, south, east, north] }
    { "type": "subscribe_route", "ds_id": "...", "route_source_id": "..." }
    { "type": "subscribe_stop", "ds_id": "...", "stop_source_id": "..." }
    { "type": "unsubscribe" }
    { "type": "ping", "timestamp": 1234567890 }

Server sends:
    { "type": "transit_update", "vehicles": [...] }
    { "type": "route_vehicles", "vehicles": [...], "stop_ids": [...], "etas": {0: {...}, 1: {...}} }
    { "type": "stop_live", "at_stop": [...], "approaching": [...] }
    { "type": "pong", "timestamp": 1234567890 }
"""

import asyncio
import orjson
import logging
import math
import time

import redis.asyncio as aioredis
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings

from .feed_pubsub import FeedPubSubManager
from parahub.services.transit_eta import (
    parse_rstops, segment_averages, segment_infos, build_index_map,
    resolve_origin, cumulative_min_etas, zombie_keeps_eta,
)

logger = logging.getLogger(__name__)

# Max bbox area in square degrees (~40 x 40 degrees)
MAX_BBOX_AREA = 1600


def _bbox_to_geosearch_params(bbox: list) -> tuple[float, float, float, float] | None:
    """Convert [west, south, east, north] to (center_lon, center_lat, width_km, height_km).
    Returns None if bbox is invalid."""
    west, south, east, north = bbox

    if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south <= 90 and -90 <= north <= 90):
        return None
    if west >= east or south >= north:
        return None
    if (east - west) * (north - south) > MAX_BBOX_AREA:
        return None

    center_lon = (west + east) / 2
    center_lat = (south + north) / 2

    # Approximate km per degree at this latitude
    lat_rad = math.radians(center_lat)
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * math.cos(lat_rad)

    width_km = (east - west) * km_per_deg_lon
    height_km = (north - south) * km_per_deg_lat

    # Small padding to avoid edge clipping
    width_km *= 1.05
    height_km *= 1.05

    return center_lon, center_lat, width_km, height_km


class TransitConsumer(AsyncWebsocketConsumer):
    """
    Public WebSocket for transit vehicle position updates.
    Clients subscribe with a bounding box; server pushes vehicles via
    Redis GEOSEARCH on each daemon tick.
    """

    async def connect(self):
        self._bbox: list | None = None     # [west, south, east, north]
        self._geo_params: tuple | None = None  # (lon, lat, w_km, h_km)
        self._route_group: str | None = None
        self._route_ds_id: str | None = None
        self._route_source_id: str | None = None
        self._stop_ds_id: str | None = None
        self._stop_source_id: str | None = None
        self._stop_route_dirs: set | None = None
        self._tick_subscribed = False
        self._feed = FeedPubSubManager.get()
        await self._feed.ensure_running()

        # Dedicated Redis connection for GEOSEARCH reads (not pub/sub mode)
        host = getattr(settings, 'REDIS_HOST', '127.0.0.1')
        port = getattr(settings, 'REDIS_PORT', 6379)
        self._redis = aioredis.Redis(host=host, port=port, decode_responses=True)

        await self.accept()
        logger.debug("Transit WS connected")

    async def disconnect(self, close_code):
        if self._tick_subscribed:
            await self._feed.unsubscribe('transit:tick', self._on_tick)
            self._tick_subscribed = False
        if self._route_group:
            await self._feed.unsubscribe(self._route_group, self._on_route_update)
        try:
            await self._redis.close()
        except Exception:
            pass
        logger.debug(f"Transit WS disconnected (code: {close_code})")

    async def receive(self, text_data):
        try:
            data = orjson.loads(text_data)
        except orjson.JSONDecodeError:
            return

        msg_type = data.get('type')

        if msg_type == 'subscribe_vehicles':
            await self._handle_subscribe_vehicles(data)
        elif msg_type == 'update_bbox':
            await self._handle_update_bbox(data)
        elif msg_type == 'subscribe_route':
            await self._handle_subscribe_route(data)
        elif msg_type == 'subscribe_stop':
            await self._handle_subscribe_stop(data)
        elif msg_type == 'unsubscribe':
            await self._handle_unsubscribe()
        elif msg_type == 'ping':
            await self.send(text_data=orjson.dumps({
                'type': 'pong',
                'timestamp': data.get('timestamp'),
            }).decode())

    async def _handle_subscribe_vehicles(self, data):
        """Subscribe to vehicles within a bounding box."""
        bbox = data.get('bbox')
        if not isinstance(bbox, list) or len(bbox) != 4:
            await self.send(text_data=orjson.dumps({
                'type': 'error', 'message': 'bbox must be [west, south, east, north]',
            }).decode())
            return

        try:
            bbox = [float(x) for x in bbox]
        except (ValueError, TypeError):
            await self.send(text_data=orjson.dumps({
                'type': 'error', 'message': 'bbox values must be numbers',
            }).decode())
            return

        params = _bbox_to_geosearch_params(bbox)
        if not params:
            await self.send(text_data=orjson.dumps({
                'type': 'error', 'message': 'invalid bbox',
            }).decode())
            return

        self._bbox = bbox
        self._geo_params = params

        # Subscribe to tick if not already
        if not self._tick_subscribed:
            await self._feed.subscribe('transit:tick', self._on_tick)
            self._tick_subscribed = True

        # Send initial data
        await self._send_geosearch_vehicles()

    async def _handle_update_bbox(self, data):
        """Update bbox. Immediate push if center moved significantly."""
        bbox = data.get('bbox')
        if not isinstance(bbox, list) or len(bbox) != 4:
            return

        try:
            bbox = [float(x) for x in bbox]
        except (ValueError, TypeError):
            return

        params = _bbox_to_geosearch_params(bbox)
        if not params:
            return

        # Check if center moved >50% of bbox dims → immediate push
        old = self._bbox
        self._bbox = bbox
        self._geo_params = params

        if old and self._tick_subscribed:
            old_cx, old_cy = (old[0] + old[2]) / 2, (old[1] + old[3]) / 2
            new_cx, new_cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
            dx = abs(new_cx - old_cx)
            dy = abs(new_cy - old_cy)
            w = old[2] - old[0]
            h = old[3] - old[1]
            if dx > w * 0.5 or dy > h * 0.5:
                await self._send_geosearch_vehicles()

    async def _handle_unsubscribe(self):
        """Unsubscribe from vehicles and route."""
        if self._tick_subscribed:
            await self._feed.unsubscribe('transit:tick', self._on_tick)
            self._tick_subscribed = False
        self._bbox = None
        self._geo_params = None
        if self._route_group:
            await self._feed.unsubscribe(self._route_group, self._on_route_update)
            self._route_group = None
        self._route_ds_id = None
        self._route_source_id = None
        self._stop_ds_id = None
        self._stop_source_id = None
        self._stop_route_dirs = None
        await self.send(text_data=orjson.dumps({'type': 'unsubscribed'}).decode())

    async def _handle_subscribe_route(self, data):
        """Subscribe to live vehicles + stop_ids + ETAs for a specific route."""
        ds_id = data.get('ds_id', '')
        route_source_id = data.get('route_source_id', '')
        if not ds_id or not route_source_id:
            await self.send(text_data=orjson.dumps({
                'type': 'error', 'message': 'ds_id and route_source_id required',
            }).decode())
            return

        new_group = f'transit_route:{ds_id}_{route_source_id}'

        # Leave previous route group if any
        if self._route_group and self._route_group != new_group:
            await self._feed.unsubscribe(self._route_group, self._on_route_update)

        self._route_group = new_group
        self._route_ds_id = ds_id
        self._route_source_id = route_source_id
        await self._feed.subscribe(new_group, self._on_route_update)

        # Send initial data: vehicles + stop_ids from Redis
        vehicles = []
        stop_ids = set()
        # Freshness cutoff: CM's /v2/vehicles retains a parked bus's last fix for
        # hours, and the daemon keeps it in transit:vdata indefinitely. Without this
        # the route page renders 12-29h-old ghosts as vehicle icons at the termini.
        # Mirrors the HTTP get_route_live_vehicles / stop-schedule 180s cutoff.
        cutoff = time.time() - 180
        members_key = f'transit:members:{ds_id}'
        member_ids = await self._redis.smembers(members_key)
        if member_ids:
            raw_values = await self._redis.hmget('transit:vdata', *member_ids)
            for raw in raw_values:
                if not raw:
                    continue
                try:
                    v = orjson.loads(raw)
                    if v.get('r') == route_source_id and v.get('t', 0) >= cutoff:
                        vehicles.append(v)
                        if v.get('sid'):
                            stop_ids.add(v['sid'])
                except (orjson.JSONDecodeError, TypeError):
                    pass

        # Compute ETAs for both directions
        etas = await self._compute_route_etas()

        await self.send(text_data=orjson.dumps({
            'type': 'route_vehicles',
            'vehicles': vehicles,
            'stop_ids': list(stop_ids),
            'etas': etas,
        }).decode())

    async def _compute_route_etas(self) -> dict:
        """
        Compute per-stop ETA predictions for both directions of the subscribed route.

        Returns: {"0": {stop_source_id: eta_seconds, ...}, "1": {...}}

        Algorithm:
        1. Load stop sequences for both directions (2 Redis GETs)
        2. Batch-read segment travel times → seg_avg via shared estimator
           (observed avg, else scheduled prior, else default)
        3. SCAN confirmed/tentative vehicles; anchor each one's ETA origin to its
           feed/displayed snapped stop (sid), not the STT idx (keeps the live
           block contiguous with the on-map icon)
        4. Cumulative sum per vehicle → min ETA per stop

        Segment estimation, origin resolution and the cumulative chain are shared
        with the REST endpoints (parahub.services.transit_eta).
        """
        ds_id = self._route_ds_id
        route_src = self._route_source_id
        if not ds_id or not route_src:
            return {}

        try:
            # 1. Load stop sequences for both directions
            pipe = self._redis.pipeline(transaction=False)
            pipe.get(f'transit:rstops:{route_src}:0')
            pipe.get(f'transit:rstops:{route_src}:1')
            raw0, raw1 = await pipe.execute()

            dir_data = {}     # direction → source_ids list
            dir_coords = {}   # direction → [(lat, lon), ...] for nearest-stop fallback
            dir_sched = {}    # direction → cumulative scheduled offsets
            dir_idxmap = {}   # direction → {source_id: index}
            all_seg_keys = []  # flat list of all segment keys
            dir_seg_ranges = {}  # direction → (start_idx, count) in all_seg_keys

            for direction, raw in ((0, raw0), (1, raw1)):
                parsed = parse_rstops(raw)
                if not parsed:
                    continue
                source_ids, coords, sched = parsed
                num_stops = len(source_ids)
                dir_data[direction] = source_ids
                dir_coords[direction] = coords
                dir_sched[direction] = sched
                dir_idxmap[direction] = build_index_map(source_ids)

                start = len(all_seg_keys)
                for i in range(num_stops - 1):
                    all_seg_keys.append(
                        f'transit:stt:{ds_id}:{source_ids[i]}:{source_ids[i + 1]}'
                    )
                dir_seg_ranges[direction] = (start, num_stops - 1)

            if not dir_data:
                return {}

            # 2. Batch-read ALL segment travel times in one pipeline → seg_avg
            pipe = self._redis.pipeline(transaction=False)
            for sk in all_seg_keys:
                pipe.lrange(sk, 0, -1)
            all_seg_results = await pipe.execute()

            dir_seg_avg = {}
            for direction, (start, count) in dir_seg_ranges.items():
                seg_obs = all_seg_results[start:start + count]
                dir_seg_avg[direction] = segment_averages(seg_obs, dir_sched[direction])

            # 3. SCAN confirmed/tentative vehicles on this route (both directions),
            #    collect (vid, direction, stt_idx, move_ts).
            tracked = []  # (vid, direction, stt_idx, move_ts)
            vprev_prefix = f'transit:vprev:{ds_id}:'
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor, match=f'{vprev_prefix}*', count=500
                )
                if keys:
                    pipe = self._redis.pipeline(transaction=False)
                    for key in keys:
                        pipe.hgetall(key)
                    states = await pipe.execute()

                    for key, state in zip(keys, states):
                        if not state or state.get('r') != route_src:
                            continue
                        # Only use confirmed/tentative for ETA computation
                        if state.get('st') not in ('c', 't'):
                            continue
                        d = int(state.get('d', -1))
                        if d not in dir_data:
                            continue
                        vid = key[len(vprev_prefix):] if isinstance(key, str) else key.decode()[len(vprev_prefix):]
                        tracked.append((vid, d, int(state.get('idx', 0)), float(state.get('mt') or 0)))

                if cursor == 0:
                    break

            # 3a. Fetch vdata for this route's tracked vehicles (bounded — not all
            #     feed members): the displayed snapped stop (sid) anchors the ETA
            #     origin, and the zombie flag (z) excludes parked vehicles. A
            #     stopped bus's feed sid can go stale (operators report the next
            #     trip's origin during layover), which would otherwise paint a
            #     long bogus ETA chain. Exception — short dwell with a sid that
            #     agrees with the STT idx (timing point): still a live arrival,
            #     and a consistent sid can't paint a bogus chain (zombie_keeps_eta).
            sid_by_vid = {}
            zombie_vids = set()
            if tracked:
                fields = [f'{ds_id}:{vid}' for vid, _, _, _ in tracked]
                vals = await self._redis.hmget('transit:vdata', *fields)
                for (vid, _, _, _), raw in zip(tracked, vals):
                    if not raw:
                        continue
                    try:
                        vv = orjson.loads(raw)
                    except (orjson.JSONDecodeError, TypeError):
                        continue
                    if vv.get('z'):
                        zombie_vids.add(vid)
                    if vv.get('sid'):
                        sid_by_vid[vid] = vv['sid']

            vehicle_by_dir = {d: [] for d in dir_data}
            useful_tracked_vids = set()  # vehicle IDs contributing non-terminal ETAs
            now_ts = time.time()
            for vid, d, stt_idx, move_ts in tracked:
                sid = sid_by_vid.get(vid)
                # Hard feed evidence overrides an unconfirmed STT direction: a vehicle
                # whose snapped stop is a platform of the OPPOSITE direction (a shared
                # terminus mid-turnaround) must not paint a forward ETA chain on this
                # direction. Otherwise resolve_origin falls back to the geometric
                # stt_idx and fabricates phantom ETAs at the far end — yellow times
                # with no vehicle icon (the bus is at the other direction's platform).
                if sid and d in (0, 1):
                    other = 1 - d
                    if sid not in dir_idxmap.get(d, {}) and sid in dir_idxmap.get(other, {}):
                        continue
                if vid in zombie_vids and not zombie_keeps_eta(
                    now_ts, move_ts, sid, stt_idx, dir_idxmap[d],
                ):
                    continue
                origin = resolve_origin(sid, stt_idx, dir_idxmap[d])
                vehicle_by_dir[d].append(origin)
                if origin < len(dir_data[d]) - 1:
                    useful_tracked_vids.add(vid)

            # 3b. Fallback: for directions without useful tracked vehicles,
            #     use GTFS-RT vdata (sid index if present, else nearest stop by
            #     coords). Only for vehicles not already contributing useful ETAs.
            directions_missing = [
                d for d in dir_data
                if not any(idx < len(dir_data[d]) - 1 for idx in vehicle_by_dir.get(d, []))
            ]
            if directions_missing:
                now_ts = time.time()
                members_key = f'transit:members:{ds_id}'
                member_ids = await self._redis.smembers(members_key)
                if member_ids:
                    raw_values = await self._redis.hmget(
                        'transit:vdata', *member_ids
                    )
                    for member_id, raw in zip(member_ids, raw_values):
                        if not raw:
                            continue
                        try:
                            v = orjson.loads(raw)
                        except (orjson.JSONDecodeError, TypeError):
                            continue
                        if v.get('r') != route_src:
                            continue
                        # Skip zombie vehicles and stale data (>5 min)
                        if v.get('z'):
                            continue
                        v_ts = v.get('t')
                        if v_ts and (now_ts - v_ts) > 300:
                            continue
                        # Skip vehicles already contributing useful ETAs
                        vid = v.get('v', '')
                        if vid in useful_tracked_vids:
                            continue
                        v_dir = v.get('d')
                        if v_dir is None:
                            continue
                        v_dir = int(v_dir)
                        if v_dir not in directions_missing:
                            continue
                        sid = v.get('sid')
                        origin = dir_idxmap[v_dir].get(sid) if sid else None
                        if origin is None:
                            vlat, vlon = v.get('lat'), v.get('lon')
                            if vlat is None or vlon is None:
                                continue
                            # Find nearest stop by coordinates
                            best_idx = 0
                            best_dist = float('inf')
                            for i, (slat, slon) in enumerate(dir_coords[v_dir]):
                                d2 = (vlat - slat) ** 2 + (vlon - slon) ** 2
                                if d2 < best_dist:
                                    best_dist = d2
                                    best_idx = i
                            origin = best_idx
                        vehicle_by_dir[v_dir].append(origin)

            # 4. Compute cumulative ETAs per direction
            result = {}
            for direction, source_ids in dir_data.items():
                origins = vehicle_by_dir.get(direction, [])
                if not origins:
                    continue
                etas = cumulative_min_etas(source_ids, dir_seg_avg[direction], origins)
                if etas:
                    result[str(direction)] = etas

            return result

        except Exception as e:
            logger.debug(f'Route ETA computation failed: {e}')
            return {}

    async def _send_geosearch_vehicles(self):
        """GEOSEARCH within current bbox → send transit_update."""
        if not self._geo_params:
            return

        lon, lat, w_km, h_km = self._geo_params
        try:
            members = await self._redis.geosearch(
                'transit:geo',
                longitude=lon, latitude=lat,
                width=w_km, height=h_km,
                unit='km',
            )
        except Exception as e:
            logger.debug(f'GEOSEARCH failed: {e}')
            return

        if not members:
            await self.send(text_data=orjson.dumps({
                'type': 'transit_update', 'vehicles': [],
            }).decode())
            return

        # Fetch vehicle data from HASH
        try:
            raw_values = await self._redis.hmget('transit:vdata', *members)
        except Exception as e:
            logger.debug(f'HMGET failed: {e}')
            return

        # Freshness cutoff: same 180s convention as the route-page WS legs and
        # HTTP reads. Stale fixes (CM retains parked buses for hours) stay in
        # Redis (transit:geo/vdata) for diagnostics — a future transport debug
        # mode may expose them — but are never displayed on the map.
        cutoff = time.time() - 180
        vehicles = []
        for raw in raw_values:
            if raw:
                try:
                    v = orjson.loads(raw)
                except (orjson.JSONDecodeError, TypeError):
                    continue
                if v.get('t', 0) >= cutoff:
                    vehicles.append(v)

        await self.send(text_data=orjson.dumps({
            'type': 'transit_update', 'vehicles': vehicles,
        }).decode())

    # Native Redis pub/sub callbacks
    async def _on_tick(self, channel: str, data):
        """Daemon tick — push bbox vehicles and/or live stop arrivals."""
        if self._geo_params:
            await self._send_geosearch_vehicles()
        if self._stop_source_id:
            await self._send_stop_live()

    async def _on_route_update(self, channel: str, data):
        """Route vehicles + stop IDs + ETAs — forward to WS client."""
        if isinstance(data, dict):
            vehicles = data.get('vehicles', [])
            stop_ids = data.get('stop_ids', [])
        elif isinstance(data, list):
            # Backward compat: old format was just stop_ids list
            vehicles = []
            stop_ids = data
        else:
            return

        # Compute fresh ETAs from Redis on each daemon tick
        etas = await self._compute_route_etas()

        await self.send(text_data=orjson.dumps({
            'type': 'route_vehicles',
            'vehicles': vehicles,
            'stop_ids': stop_ids,
            'etas': etas,
        }).decode())

    # ===== Stop subscription =====

    async def _handle_subscribe_stop(self, data):
        """Subscribe to live vehicles AT + APPROACHING a specific stop.

        Mirrors subscribe_route: one DB query on subscribe to resolve the routes
        serving this stop, then pure-Redis pushes on each daemon tick. The stop
        page overlays the approaching ETAs onto its static schedule board (live
        yellow vs scheduled grey) and pulses real arrivals (at_stop)."""
        ds_id = data.get('ds_id', '')
        stop_source_id = data.get('stop_source_id', '')
        if not ds_id or not stop_source_id:
            await self.send(text_data=orjson.dumps({
                'type': 'error', 'message': 'ds_id and stop_source_id required',
            }).decode())
            return

        self._stop_ds_id = ds_id
        self._stop_source_id = stop_source_id
        self._stop_route_dirs = await self._load_stop_route_dirs(ds_id, stop_source_id)

        if not self._tick_subscribed:
            await self._feed.subscribe('transit:tick', self._on_tick)
            self._tick_subscribed = True

        await self._send_stop_live()

    @database_sync_to_async
    def _load_stop_route_dirs(self, ds_id, stop_source_id):
        """{(route_source_id, direction_id)} serving this stop — resolved once on
        subscribe so per-tick pushes stay pure-Redis (no DB)."""
        from geo.models import Stop, RouteStop
        stop = Stop.objects.filter(
            source_id=stop_source_id, agency__data_source_id=ds_id
        ).first()
        if not stop:
            return set()
        rd = RouteStop.objects.filter(stop=stop).values_list(
            'route__source_id', 'direction_id'
        )
        return {(r, d if d is not None else 0) for r, d in rd}

    async def _send_stop_live(self):
        """Push vehicles at the stop + approaching ETAs (recomputed each tick)."""
        ds_id = self._stop_ds_id
        stop_src = self._stop_source_id
        if not ds_id or not stop_src:
            return

        # Vehicles currently AT this stop — displayable set (members + vdata, 180s
        # cutoff), same source the route page uses for its on-list icon.
        at_stop = []
        cutoff = time.time() - 180
        member_ids = await self._redis.smembers(f'transit:members:{ds_id}')
        if member_ids:
            raw_values = await self._redis.hmget('transit:vdata', *member_ids)
            for raw in raw_values:
                if not raw:
                    continue
                try:
                    v = orjson.loads(raw)
                except (orjson.JSONDecodeError, TypeError):
                    continue
                if v.get('sid') == stop_src and v.get('t', 0) >= cutoff:
                    at_stop.append({
                        'vehicle_id': v.get('v', ''),
                        'route_short_name': v.get('rn', ''),
                        'route_color': v.get('rc', ''),
                        'headsign': v.get('hs', ''),
                        'direction': v.get('d'),
                        'trip_id': v.get('tid', ''),
                    })

        approaching = await self._compute_stop_approaching()

        await self.send(text_data=orjson.dumps({
            'type': 'stop_live',
            'at_stop': at_stop,
            'approaching': approaching,
        }).decode())

    async def _compute_stop_approaching(self) -> list:
        """Confirmed vehicles approaching this stop with chained-segment ETAs.

        Async-Redis mirror of the REST get_stop_eta (same transit_eta helpers);
        the serving (route, dir) set is resolved once on subscribe."""
        ds_id = self._stop_ds_id
        stop_src = self._stop_source_id
        route_dirs = self._stop_route_dirs
        if not ds_id or not stop_src or not route_dirs:
            return []

        try:
            # 1. Load stop sequences for serving (route, dir) pairs incl. this stop
            rd_list = list(route_dirs)
            pipe = self._redis.pipeline(transaction=False)
            for route_src, dir_id in rd_list:
                pipe.get(f'transit:rstops:{route_src}:{dir_id}')
            seq_results = await pipe.execute()

            route_seqs = {}      # (route_src, dir) → source_ids
            route_idxmap = {}
            route_sched = {}
            target_idx = {}
            for (route_src, dir_id), raw in zip(rd_list, seq_results):
                parsed = parse_rstops(raw)
                if not parsed:
                    continue
                source_ids, _coords, sched = parsed
                if stop_src not in source_ids:
                    continue
                key = (route_src, dir_id)
                route_seqs[key] = source_ids
                route_idxmap[key] = build_index_map(source_ids)
                route_sched[key] = sched
                target_idx[key] = source_ids.index(stop_src)

            if not route_seqs:
                return []

            # 2. Per-route segment model (observed avg / scheduled prior / default),
            #    memoized so each route's segments are read once.
            seg_cache = {}

            async def seg_infos_for(route_key):
                if route_key not in seg_cache:
                    ordered = route_seqs[route_key]
                    keys = [
                        f'transit:stt:{ds_id}:{ordered[i]}:{ordered[i + 1]}'
                        for i in range(len(ordered) - 1)
                    ]
                    p = self._redis.pipeline(transaction=False)
                    for sk in keys:
                        p.lrange(sk, 0, -1)
                    seg_cache[route_key] = segment_infos(await p.execute(), route_sched[route_key])
                return seg_cache[route_key]

            # 3. SCAN confirmed vehicles on serving routes → chain origin→stop
            results = []
            vprev_prefix = f'transit:vprev:{ds_id}:'
            now_ts = time.time()
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor, match=f'{vprev_prefix}*', count=500
                )
                if keys:
                    pipe = self._redis.pipeline(transaction=False)
                    for k in keys:
                        pipe.hgetall(k)
                    states = await pipe.execute()

                    cands = []  # (vid, route_key, v_idx, move_ts)
                    for k, state in zip(keys, states):
                        if not state or state.get('st') != 'c':
                            continue
                        route_key = (state.get('r', ''), int(state.get('d', -1)))
                        if route_key not in target_idx:
                            continue
                        vid = k[len(vprev_prefix):] if isinstance(k, str) else k.decode()[len(vprev_prefix):]
                        cands.append((vid, route_key, int(state.get('idx', 0)), float(state.get('mt') or 0)))

                    if cands:
                        fields = [f'{ds_id}:{vid}' for vid, _, _, _ in cands]
                        vals = await self._redis.hmget('transit:vdata', *fields)
                        for (vid, route_key, v_idx, move_ts), raw in zip(cands, vals):
                            vdata = {}
                            if raw:
                                try:
                                    vdata = orjson.loads(raw)
                                except (orjson.JSONDecodeError, TypeError):
                                    vdata = {}
                            idxmap = route_idxmap[route_key]
                            if vdata.get('z') and not zombie_keeps_eta(
                                now_ts, move_ts, vdata.get('sid'), v_idx, idxmap,
                            ):
                                continue
                            origin = resolve_origin(vdata.get('sid'), v_idx, idxmap)
                            tgt = target_idx[route_key]
                            if origin >= tgt:
                                continue
                            stops_away = tgt - origin
                            if stops_away > 15:
                                continue
                            chain = (await seg_infos_for(route_key))[origin:tgt]
                            if not chain:
                                continue
                            eta_seconds = sum(s['avg'] for s in chain)
                            if eta_seconds <= 0:
                                continue
                            results.append({
                                'vehicle_id': vid,
                                'route': route_key[0],
                                'route_name': vdata.get('rn', ''),
                                'route_color': vdata.get('rc') or '3b82f6',
                                'headsign': vdata.get('hs', ''),
                                'direction': route_key[1],
                                'trip_id': vdata.get('tid', ''),
                                'eta_seconds': int(eta_seconds),
                                'eta_minutes': round(eta_seconds / 60, 1),
                                'stops_away': stops_away,
                            })

                if cursor == 0:
                    break

            results.sort(key=lambda x: x['eta_seconds'])
            return results[:20]

        except Exception as e:
            logger.debug(f'Stop approaching computation failed: {e}')
            return []
