"""
WebSocket consumer for GPS tracker real-time updates.

URL: ws/v1/trackers/
Auth: Required (JWT via middleware). Staff sees all devices, users see own only.

Redis keys: tracker:geo (GEOADD spatial), tracker:vdata (HSET data),
tracker:tick (PUB/SUB signal per position update).

Client sends:
    { "type": "subscribe_bbox", "bbox": [west, south, east, north] }
    { "type": "update_bbox", "bbox": [west, south, east, north] }
    { "type": "subscribe_device", "device_id": "ULID" }
    { "type": "unsubscribe" }
    { "type": "ping", "timestamp": 1234567890 }

Server sends:
    { "type": "tracker_update", "trackers": [...] }
    { "type": "device_update", "tracker": {...} }
    { "type": "pong", "timestamp": 1234567890 }
"""

import orjson
import logging

import redis.asyncio as aioredis
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from .feed_pubsub import FeedPubSubManager
from .transit import _bbox_to_geosearch_params

logger = logging.getLogger(__name__)


class TrackerConsumer(AsyncWebsocketConsumer):
    """
    Authenticated WebSocket for GPS tracker position updates.
    Staff sees all devices; regular users see only their own.
    """

    async def connect(self):
        self.user = self.scope.get('user')
        self.profile = self.scope.get('profile')

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        self._bbox = None
        self._geo_params = None
        self._subscribed_device = None
        self._tick_subscribed = False
        self._is_staff = bool(self.user.is_staff)
        self._owner_id = str(self.profile.id) if self.profile else None

        self._feed = FeedPubSubManager.get()
        await self._feed.ensure_running()

        host = getattr(settings, 'REDIS_HOST', '127.0.0.1')
        port = getattr(settings, 'REDIS_PORT', 6379)
        self._redis = aioredis.Redis(host=host, port=port, decode_responses=True)

        await self.accept()

    async def disconnect(self, close_code):
        if self._tick_subscribed:
            await self._feed.unsubscribe('tracker:tick', self._on_tick)
            self._tick_subscribed = False
        try:
            await self._redis.close()
        except Exception:
            pass

    async def receive(self, text_data):
        try:
            data = orjson.loads(text_data)
        except orjson.JSONDecodeError:
            return

        msg_type = data.get('type')

        if msg_type == 'subscribe_bbox':
            await self._handle_subscribe_bbox(data)
        elif msg_type == 'update_bbox':
            await self._handle_update_bbox(data)
        elif msg_type == 'subscribe_device':
            await self._handle_subscribe_device(data)
        elif msg_type == 'unsubscribe':
            await self._handle_unsubscribe()
        elif msg_type == 'ping':
            await self.send(text_data=orjson.dumps({
                'type': 'pong',
                'timestamp': data.get('timestamp'),
            }).decode())

    async def _handle_subscribe_bbox(self, data):
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

        self._bbox = bbox
        self._geo_params = params
        self._subscribed_device = None

        if not self._tick_subscribed:
            await self._feed.subscribe('tracker:tick', self._on_tick)
            self._tick_subscribed = True

        await self._send_geosearch_trackers()

    async def _handle_update_bbox(self, data):
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

        old = self._bbox
        self._bbox = bbox
        self._geo_params = params

        if old and self._tick_subscribed:
            old_cx, old_cy = (old[0] + old[2]) / 2, (old[1] + old[3]) / 2
            new_cx, new_cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
            w = old[2] - old[0]
            h = old[3] - old[1]
            if abs(new_cx - old_cx) > w * 0.5 or abs(new_cy - old_cy) > h * 0.5:
                await self._send_geosearch_trackers()

    async def _handle_subscribe_device(self, data):
        device_id = data.get('device_id', '')
        if not device_id:
            return

        self._subscribed_device = device_id
        self._bbox = None
        self._geo_params = None

        if not self._tick_subscribed:
            await self._feed.subscribe('tracker:tick', self._on_tick)
            self._tick_subscribed = True

        # Send initial position
        raw = await self._redis.hget('tracker:vdata', device_id)
        if raw:
            try:
                tracker = orjson.loads(raw)
                if self._can_see(tracker):
                    await self.send(text_data=orjson.dumps({
                        'type': 'device_update',
                        'tracker': tracker,
                    }).decode())
            except (orjson.JSONDecodeError, TypeError):
                pass

    async def _handle_unsubscribe(self):
        if self._tick_subscribed:
            await self._feed.unsubscribe('tracker:tick', self._on_tick)
            self._tick_subscribed = False
        self._bbox = None
        self._geo_params = None
        self._subscribed_device = None
        await self.send(text_data=orjson.dumps({'type': 'unsubscribed'}).decode())

    def _can_see(self, tracker_data: dict) -> bool:
        """Check if current user can see this tracker (staff=all, user=own)."""
        if self._is_staff:
            return True
        return tracker_data.get('owner') == self._owner_id

    async def _send_geosearch_trackers(self):
        """GEOSEARCH within current bbox → filter by ownership → send."""
        if not self._geo_params:
            return

        lon, lat, w_km, h_km = self._geo_params
        try:
            members = await self._redis.geosearch(
                'tracker:geo',
                longitude=lon, latitude=lat,
                width=w_km, height=h_km,
                unit='km',
            )
        except Exception as e:
            logger.debug(f'Tracker GEOSEARCH failed: {e}')
            return

        if not members:
            await self.send(text_data=orjson.dumps({
                'type': 'tracker_update', 'trackers': [],
            }).decode())
            return

        try:
            raw_values = await self._redis.hmget('tracker:vdata', *members)
        except Exception as e:
            logger.debug(f'Tracker HMGET failed: {e}')
            return

        trackers = []
        for raw in raw_values:
            if raw:
                try:
                    t = orjson.loads(raw)
                    if self._can_see(t):
                        trackers.append(t)
                except (orjson.JSONDecodeError, TypeError):
                    pass

        await self.send(text_data=orjson.dumps({
            'type': 'tracker_update', 'trackers': trackers,
        }).decode())

    async def _on_tick(self, channel: str, data):
        """tracker:tick received — device ULID as payload."""
        if self._subscribed_device:
            # Per-device mode: only send if this device updated
            device_ulid = data.get('raw', '') if isinstance(data, dict) else str(data)
            if device_ulid == self._subscribed_device:
                raw = await self._redis.hget('tracker:vdata', device_ulid)
                if raw:
                    try:
                        tracker = orjson.loads(raw)
                        if self._can_see(tracker):
                            await self.send(text_data=orjson.dumps({
                                'type': 'device_update',
                                'tracker': tracker,
                            }).decode())
                    except (orjson.JSONDecodeError, TypeError):
                        pass
        elif self._geo_params:
            # Bbox mode: GEOSEARCH on every tick
            await self._send_geosearch_trackers()
