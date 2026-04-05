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
    { "type": "unsubscribe" }
    { "type": "ping", "timestamp": 1234567890 }

Server sends:
    { "type": "transit_update", "vehicles": [...] }
    { "type": "route_vehicles", "vehicles": [...], "stop_ids": [...], "etas": {0: {...}, 1: {...}} }
    { "type": "pong", "timestamp": 1234567890 }
"""

import asyncio
import orjson
import logging
import math

import redis.asyncio as aioredis
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from .feed_pubsub import FeedPubSubManager

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
        members_key = f'transit:members:{ds_id}'
        member_ids = await self._redis.smembers(members_key)
        if member_ids:
            raw_values = await self._redis.hmget('transit:vdata', *member_ids)
            for raw in raw_values:
                if not raw:
                    continue
                try:
                    v = orjson.loads(raw)
                    if v.get('r') == route_source_id:
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

        Returns: {0: {stop_source_id: eta_seconds, ...}, 1: {...}}

        Algorithm:
        1. Load stop sequences for both directions (2 Redis GETs)
        2. Batch-read segment travel times (1 pipeline per direction)
        3. Single SCAN for all confirmed vehicles on this route
        4. Cumulative sum per vehicle → min ETA per stop
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

            dir_data = {}  # direction → source_ids list
            dir_coords = {}  # direction → [(lat, lon), ...] for nearest-stop fallback
            all_seg_keys = []  # flat list of all segment keys
            dir_seg_ranges = {}  # direction → (start_idx, count) in all_seg_keys

            for direction, raw in ((0, raw0), (1, raw1)):
                if not raw:
                    continue
                try:
                    stops_list = orjson.loads(raw)
                except (orjson.JSONDecodeError, TypeError):
                    continue
                if len(stops_list) < 2:
                    continue

                source_ids = [s[0] for s in stops_list]
                num_stops = len(source_ids)
                dir_data[direction] = source_ids
                dir_coords[direction] = [(s[1], s[2]) for s in stops_list]

                start = len(all_seg_keys)
                for i in range(num_stops - 1):
                    all_seg_keys.append(
                        f'transit:stt:{ds_id}:{source_ids[i]}:{source_ids[i + 1]}'
                    )
                dir_seg_ranges[direction] = (start, num_stops - 1)

            if not dir_data:
                return {}

            # 2. Batch-read ALL segment travel times in one pipeline
            pipe = self._redis.pipeline(transaction=False)
            for sk in all_seg_keys:
                pipe.lrange(sk, 0, -1)
            all_seg_results = await pipe.execute()

            # Parse segment averages per direction
            dir_seg_avg = {}
            for direction, (start, count) in dir_seg_ranges.items():
                seg_avg = []
                for vals in all_seg_results[start:start + count]:
                    if vals:
                        avg = sum(float(v) for v in vals) / len(vals)
                        seg_avg.append(avg)
                    else:
                        seg_avg.append(90.0)
                dir_seg_avg[direction] = seg_avg

            # 3. SCAN for confirmed/tentative vehicles on this route (both directions)
            vehicle_by_dir = {d: [] for d in dir_data}
            useful_tracked_vids = set()  # vehicle IDs contributing non-terminal ETAs
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
                        if not state:
                            continue
                        if state.get('r') != route_src:
                            continue
                        vid = key[len(vprev_prefix):] if isinstance(key, str) else key.decode()[len(vprev_prefix):]
                        # Only use confirmed/tentative for ETA computation
                        if state.get('st') not in ('c', 't'):
                            continue
                        d = int(state.get('d', -1))
                        if d in vehicle_by_dir:
                            idx = int(state.get('idx', 0))
                            vehicle_by_dir[d].append(idx)
                            # Track vehicles at non-terminal positions (actually useful)
                            num = len(dir_data[d])
                            if idx < num - 1:
                                useful_tracked_vids.add(vid)

                if cursor == 0:
                    break

            # 3b. Fallback: for directions without useful tracked vehicles,
            #     use GTFS-RT vdata + nearest stop by coordinates.
            #     Only skip vehicles that are already contributing useful (non-terminal)
            #     ETAs. Terminal-positioned or untracked vehicles get re-snapped.
            directions_missing = []
            for d in dir_data:
                indices = vehicle_by_dir.get(d, [])
                num = len(dir_data[d])
                if not any(idx < num - 1 for idx in indices):
                    directions_missing.append(d)
            if directions_missing:
                import time as _time
                now_ts = _time.time()
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
                        vlat, vlon = v.get('lat'), v.get('lon')
                        if vlat is None or vlon is None:
                            continue
                        # Find nearest stop by coordinates
                        coords = dir_coords[v_dir]
                        best_idx = 0
                        best_dist = float('inf')
                        for i, (slat, slon) in enumerate(coords):
                            d2 = (vlat - slat) ** 2 + (vlon - slon) ** 2
                            if d2 < best_dist:
                                best_dist = d2
                                best_idx = i
                        vehicle_by_dir[v_dir].append(best_idx)

            # 4. Compute cumulative ETAs per direction
            result = {}
            for direction, source_ids in dir_data.items():
                indices = vehicle_by_dir.get(direction, [])
                if not indices:
                    continue

                num_stops = len(source_ids)
                seg_avg = dir_seg_avg[direction]
                etas = {}

                for v_idx in indices:
                    if v_idx >= num_stops - 1:
                        continue
                    cumulative = 0.0
                    for j in range(v_idx, num_stops - 1):
                        cumulative += seg_avg[j]
                        stop_src = source_ids[j + 1]
                        if stop_src not in etas or cumulative < etas[stop_src]:
                            etas[stop_src] = int(cumulative)

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

        vehicles = []
        for raw in raw_values:
            if raw:
                try:
                    vehicles.append(orjson.loads(raw))
                except (orjson.JSONDecodeError, TypeError):
                    pass

        await self.send(text_data=orjson.dumps({
            'type': 'transit_update', 'vehicles': vehicles,
        }).decode())

    # Native Redis pub/sub callbacks
    async def _on_tick(self, channel: str, data):
        """Daemon tick — do GEOSEARCH and push vehicles."""
        if self._geo_params:
            await self._send_geosearch_vehicles()

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
