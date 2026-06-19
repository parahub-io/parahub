"""
WebSocket consumer for Driver Mode GPS broadcasting.

URL: ws/v1/driver/
Authenticated — JWT via ws_token cookie.

Bidirectional:
  UP:   {"type": "position", "lat": ..., "lon": ..., "speed": ..., "bearing": ..., "accuracy": ...}
  DOWN: {"type": "stop_announcement", "stop_name": ..., "next_stop_name": ...}
        {"type": "position_ack", "seq": N, "stop_id": ...}
        {"type": "shift_confirmed", ...}
        {"type": "error", "message": ...}
"""

import asyncio
import orjson
import logging
import time

import redis.asyncio as aioredis
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from .feed_pubsub import FeedPubSubManager

logger = logging.getLogger(__name__)

# Module-level singleton RouteCache + StopSnapper (shared by all driver consumers)
_route_cache = None
_stop_snapper = None
_cache_lock = asyncio.Lock()

POSITION_INTERVAL_MIN_S = 5  # Reject positions faster than 5s apart
HEARTBEAT_TTL = 45  # Redis heartbeat key TTL


async def _ensure_route_cache():
    """Lazy-load and periodically refresh the shared RouteCache."""
    global _route_cache, _stop_snapper
    async with _cache_lock:
        if _route_cache is None:
            from parahub.services.transit_rt import RouteCache, StopSnapper
            _route_cache = RouteCache()
            await _route_cache.refresh()
            _stop_snapper = StopSnapper(_route_cache)
        elif _route_cache.is_stale():
            await _route_cache.refresh()
    return _route_cache, _stop_snapper


class DriverConsumer(AsyncWebsocketConsumer):
    """
    Authenticated WebSocket for driver GPS broadcasting.
    Writes to the same Redis transit pipeline as the GTFS-RT daemon.
    """

    async def connect(self):
        self.user = self.scope.get('user')
        self.profile = self.scope.get('profile')

        if not self.user or not self.user.is_authenticated or not self.profile:
            await self.close(code=4001)
            return

        self._shift = None
        self._ds_id = None
        self._vehicle_id = None
        self._route_source_id = None
        self._route_color = ''
        self._route_name = ''
        self._route_type = 3
        self._direction_id = 0
        self._headsign = ''
        self._last_stop_id = ''
        self._pos_count = 0
        self._last_pos_time = 0.0
        self._feed = FeedPubSubManager.get()
        await self._feed.ensure_running()

        host = getattr(settings, 'REDIS_HOST', '127.0.0.1')
        port = getattr(settings, 'REDIS_PORT', 6379)
        self._redis = aioredis.Redis(host=host, port=port, decode_responses=True)

        await self.accept()
        logger.info(f"Driver WS connected: {self.user.username}")

    async def disconnect(self, close_code):
        if self._shift:
            await self._cleanup_redis()
            await self._end_shift_db()
        try:
            await self._redis.close()
        except Exception:
            pass
        logger.info(f"Driver WS disconnected: {getattr(self, 'user', '?')} (code: {close_code})")

    async def receive(self, text_data):
        try:
            data = orjson.loads(text_data)
        except orjson.JSONDecodeError:
            return

        msg_type = data.get('type')

        if msg_type == 'start':
            await self._handle_start(data)
        elif msg_type == 'position':
            await self._handle_position(data)
        elif msg_type == 'direction_change':
            await self._handle_direction_change(data)
        elif msg_type == 'ping':
            await self.send(text_data=orjson.dumps({
                'type': 'pong',
                'timestamp': data.get('timestamp'),
            }).decode())

    async def _handle_start(self, data):
        """Attach to an active DriverShift by ID."""
        shift_id = data.get('shift_id', '')
        if not shift_id:
            await self._send_error('shift_id required')
            return

        shift = await self._load_shift(shift_id)
        if not shift:
            await self._send_error('Shift not found or not yours')
            return
        if shift['status'] != 'ACTIVE':
            await self._send_error('Shift is not active')
            return

        self._shift = shift
        self._ds_id = shift['ds_id']
        self._vehicle_id = shift['vehicle_id']
        self._route_source_id = shift['route_source_id']
        self._route_color = shift['route_color']
        self._route_name = shift['route_name']
        self._route_type = shift['route_type']
        self._direction_id = shift['direction_id']

        # Load headsign from RouteCache
        cache, _ = await _ensure_route_cache()
        hs = cache.headsign_info.get((self._route_source_id, self._direction_id), '')
        self._headsign = hs

        # Load stop sequence for announcements
        self._stop_seq = cache.stop_seqs.get(
            (self._route_source_id, self._direction_id), []
        )

        await self.send(text_data=orjson.dumps({
            'type': 'shift_confirmed',
            'shift_id': shift['id'],
            'vehicle_id': self._vehicle_id,
            'route_source_id': self._route_source_id,
            'route_name': self._route_name,
            'headsign': self._headsign,
            'stops': [
                {'id': s.source_id, 'name': self._get_stop_name(s.source_id)}
                for s in self._stop_seq
            ] if len(self._stop_seq) <= 200 else [],
        }).decode())
        logger.info(f"Driver shift started: {self._vehicle_id} on route {self._route_name}")

    async def _handle_position(self, data):
        """Process GPS position from driver's browser."""
        if not self._shift:
            await self._send_error('Send "start" first')
            return

        now = time.time()
        if (now - self._last_pos_time) < POSITION_INTERVAL_MIN_S:
            return  # Throttle
        self._last_pos_time = now

        lat = data.get('lat')
        lon = data.get('lon')
        speed = data.get('speed', 0) or 0
        bearing = data.get('bearing')
        accuracy = data.get('accuracy')

        if lat is None or lon is None:
            return
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return

        # Snap to nearest stop
        _, snapper = await _ensure_route_cache()
        snap_result = snapper.snap(lat, lon, self._route_source_id, self._direction_id)
        stop_id = snap_result[0] if snap_result else ''

        now_int = int(now)
        ds_id = self._ds_id
        vid = self._vehicle_id
        member = f'{ds_id}:{vid}'

        vdata = orjson.dumps({
            'v': vid,
            'lat': lat, 'lon': lon,
            'b': bearing,
            's': round(speed, 1) if speed else 0,
            'r': self._route_source_id,
            'rc': self._route_color,
            'rn': self._route_name,
            'rt': self._route_type,
            'st': 'IN_TRANSIT_TO',
            't': now_int,
            'tid': '',
            'sid': stop_id,
            'd': self._direction_id,
            'hs': self._headsign,
            'src': 'driver',
        })

        # Write to Redis (same keys as GTFS-RT daemon)
        pipe = self._redis.pipeline(transaction=False)
        pipe.geoadd('transit:geo', (lon, lat, member))
        pipe.hset('transit:vdata', member, vdata)
        pipe.sadd(f'transit:members:{ds_id}', member)
        pipe.expire(f'transit:members:{ds_id}', 300)
        pipe.set(f'driver:heartbeat:{self._shift["id"]}', '1', ex=HEARTBEAT_TTL)
        pipe.publish('transit:tick', str(now_int))
        await pipe.execute()

        # Publish to route channel (route page subscribers)
        route_channel = f'transit_route:{ds_id}_{self._route_source_id}'
        await self._feed.publish(route_channel, {
            'vehicles': [orjson.loads(vdata)],
            'stop_ids': [stop_id] if stop_id else [],
        })

        self._pos_count += 1

        # Stop announcement
        announcement = None
        if stop_id and stop_id != self._last_stop_id:
            self._last_stop_id = stop_id
            stop_name = self._get_stop_name(stop_id)
            next_stop = self._get_next_stop(stop_id)
            next_stop_id = next_stop[0] if next_stop else ''
            # Unabbreviated tts_stop_name for the SPOKEN announcement — one indexed
            # lookup, fired only on a stop transition (rare). Client falls back to
            # the abbreviated name when a feed omits tts. See Stop.tts_name.
            tts = await self._get_tts_names([stop_id, next_stop_id])
            announcement = {
                'type': 'stop_announcement',
                'stop_id': stop_id,
                'stop_name': stop_name,
                'stop_tts': tts.get(stop_id, ''),
                'next_stop_id': next_stop_id,
                'next_stop_name': next_stop[1] if next_stop else '',
                'next_stop_tts': tts.get(next_stop_id, ''),
            }

        # Send ack (and announcement if any)
        ack = {
            'type': 'position_ack',
            'seq': self._pos_count,
            'stop_id': stop_id,
        }
        if announcement:
            await self.send(text_data=orjson.dumps([announcement, ack]).decode())
        else:
            await self.send(text_data=orjson.dumps(ack).decode())

        # Update DB position count periodically (every 20 positions = ~5 min)
        if self._pos_count % 20 == 0:
            await self._update_shift_count()

    async def _handle_direction_change(self, data):
        """Driver switches direction mid-route."""
        if not self._shift:
            return

        new_dir = data.get('direction_id')
        if new_dir not in (0, 1):
            await self._send_error('direction_id must be 0 or 1')
            return

        self._direction_id = new_dir
        self._last_stop_id = ''  # Reset stop tracking

        # Update headsign + stop sequence
        cache, _ = await _ensure_route_cache()
        self._headsign = cache.headsign_info.get(
            (self._route_source_id, new_dir), ''
        )
        self._stop_seq = cache.stop_seqs.get(
            (self._route_source_id, new_dir), []
        )

        # Update DB
        await self._update_shift_direction(new_dir)

        await self.send(text_data=orjson.dumps({
            'type': 'direction_changed',
            'direction_id': new_dir,
            'headsign': self._headsign,
            'stops': [
                {'id': s.source_id, 'name': self._get_stop_name(s.source_id)}
                for s in self._stop_seq
            ] if len(self._stop_seq) <= 200 else [],
        }).decode())

    @database_sync_to_async
    def _get_tts_names(self, source_ids):
        """{source_id: tts_name} for these stops of this data source (only stops
        that actually have a tts_name). One indexed query; empty when the feed
        omits tts_stop_name. See Stop.tts_name (GTFS tts_stop_name)."""
        ids = [s for s in source_ids if s]
        if not ids or not self._ds_id:
            return {}
        from geo.models import Stop
        return {
            sid: tts
            for sid, tts in Stop.objects.filter(
                agency__data_source_id=self._ds_id, source_id__in=ids
            ).values_list('source_id', 'tts_name')
            if tts
        }

    def _get_stop_name(self, stop_source_id: str) -> str:
        """Get stop name from cached shape data."""
        if not _route_cache:
            return stop_source_id
        shape = _route_cache.shapes.get((self._route_source_id, self._direction_id))
        if shape:
            for s in shape.stops:
                if s.source_id == stop_source_id:
                    return s.name
        return stop_source_id

    def _get_next_stop(self, current_stop_id: str):
        """Get the next stop after the current one in the sequence."""
        for i, sp in enumerate(self._stop_seq):
            if sp.source_id == current_stop_id and i + 1 < len(self._stop_seq):
                nxt = self._stop_seq[i + 1]
                return (nxt.source_id, self._get_stop_name(nxt.source_id))
        return None

    async def _cleanup_redis(self):
        """Remove vehicle from transit pipeline on disconnect."""
        if not self._ds_id or not self._vehicle_id:
            return
        member = f'{self._ds_id}:{self._vehicle_id}'
        try:
            pipe = self._redis.pipeline(transaction=False)
            pipe.zrem('transit:geo', member)
            pipe.hdel('transit:vdata', member)
            pipe.srem(f'transit:members:{self._ds_id}', member)
            pipe.delete(f'driver:heartbeat:{self._shift["id"]}')
            pipe.publish('transit:tick', str(int(time.time())))
            await pipe.execute()
        except Exception as e:
            logger.warning(f"Driver Redis cleanup failed: {e}")

    async def _send_error(self, msg: str):
        await self.send(text_data=orjson.dumps({'type': 'error', 'message': msg}).decode())

    # --- DB operations ---

    @database_sync_to_async
    def _load_shift(self, shift_id: str):
        from geo.models import DriverShift
        try:
            s = (
                DriverShift.objects
                .select_related('route__agency__data_source', 'route__place')
                .get(id=shift_id, profile=self.profile)
            )
            return {
                'id': str(s.id),
                'ds_id': str(s.data_source_id),
                'vehicle_id': s.vehicle_id,
                'route_source_id': s.route.source_id,
                'route_color': s.route.route_color or '',
                'route_name': s.route.short_name,
                'route_type': s.route.route_type,
                'direction_id': s.direction_id,
                'status': s.status,
            }
        except DriverShift.DoesNotExist:
            return None

    @database_sync_to_async
    def _end_shift_db(self):
        from django.utils import timezone as tz
        from geo.models import DriverShift
        if not self._shift:
            return
        DriverShift.objects.filter(
            id=self._shift['id'], status='ACTIVE',
        ).update(
            status='ENDED',
            ended_at=tz.now(),
            position_count=self._pos_count,
        )

    @database_sync_to_async
    def _update_shift_count(self):
        from geo.models import DriverShift
        if not self._shift:
            return
        DriverShift.objects.filter(id=self._shift['id']).update(
            position_count=self._pos_count,
        )

    @database_sync_to_async
    def _update_shift_direction(self, direction_id: int):
        from geo.models import DriverShift
        if not self._shift:
            return
        DriverShift.objects.filter(id=self._shift['id']).update(
            direction_id=direction_id,
        )
