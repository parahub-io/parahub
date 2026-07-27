"""
WebSocket consumer for map presence (MMORPG-style avatars)

Real-time viewport position tracking and avatar interactions.
Users see others viewing nearby map locations.

URL: ws/v1/map/presence/
"""

import orjson
import logging
import math
import time

import redis.asyncio as aioredis
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async
from django.conf import settings

from parahub.services.map_presence import MapPresenceService
from identity.models import Profile
from .feed_pubsub import FeedPubSubManager

logger = logging.getLogger(__name__)


def _get_aioredis() -> aioredis.Redis:
    """Lazy module-level async Redis connection (rate limiting)."""
    global _aioredis_conn
    if _aioredis_conn is None:
        url = settings.CACHES['default']['LOCATION']
        _aioredis_conn = aioredis.from_url(url, decode_responses=True)
    return _aioredis_conn


_aioredis_conn: aioredis.Redis | None = None

# Security limits. Broadcast payloads must stay small: every message fans out
# to all subscribers of the sender's tile.
MAX_MESSAGE_SIZE = 4096  # bytes; largest legit message is a 200-char speech bubble
RATE_LIMIT_PER_SECOND = 30  # per profile, all connections; keyboard panning peaks ~10/s
SPEECH_BUBBLE_MAX_CHARS = 200
LAT_LIMIT = 85.05112878  # Web Mercator / Redis GEO latitude bound


def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple:
    """Convert lat/lon to tile coordinates (x, y) for given zoom level."""
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (x, y)


class MapPresenceConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for map presence updates.

    Client sends:
    - position_update: Update viewport position
    - set_state: Change avatar state (idle, walking, jumping, sitting, emoting)
    - set_speech_bubble: Set speech bubble text
    - ping: Heartbeat (refreshes presence TTL for idle-but-connected users)

    Server broadcasts:
    - nearby_avatars: List of avatars in view
    - avatar_update: Single avatar position/state/speech change, or 'leave' on disconnect
    """

    async def connect(self):
        """Handle WebSocket connection"""
        self.user = self.scope.get('user')
        self.profile = self.scope.get('profile')

        if not self.user or not self.user.is_authenticated:
            logger.warning("Unauthenticated map presence connection attempt")
            await self.close(code=4001)
            return

        if not self.profile:
            logger.warning(f"No profile found for user {self.user.id}")
            await self.close(code=4004)
            return

        self.profile_id = self.profile.id

        @database_sync_to_async
        def get_profile_info(profile_id):
            try:
                profile = Profile.objects.select_related('instance').get(id=profile_id)
                return profile.hna, profile.display_name or profile.local_name
            except Exception:
                return '', ''

        self.profile_hna, self.profile_name = await get_profile_info(self.profile_id)

        # Current subscribed tiles (will be updated on position_update)
        self.subscribed_tiles: set[str] = set()
        self.center_tile: str | None = None

        # Init FeedPubSubManager
        self._feed = FeedPubSubManager.get()
        await self._feed.ensure_running()

        await self.accept()

        await self.send(text_data=orjson.dumps({
            'type': 'connected',
            'profile_id': self.profile_id,
            'message': 'Map presence connected'
        }).decode())

        logger.info(f"Map presence connected: {self.profile_id}")

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Tell tile subscribers the avatar left — otherwise it lingers on their
        # maps until their own next position_update refreshes the nearby list
        if getattr(self, 'center_tile', None) and hasattr(self, '_feed'):
            try:
                await self._feed.publish(self.center_tile, {
                    'update_type': 'leave',
                    'sender': self.profile_id,
                    'profile_id': self.profile_id,
                })
            except Exception:
                logger.exception('Failed to publish leave event')

        if hasattr(self, '_feed') and hasattr(self, 'subscribed_tiles'):
            for tile_channel in self.subscribed_tiles:
                await self._feed.unsubscribe(tile_channel, self._on_tile_event)

        if hasattr(self, 'profile_id'):
            await sync_to_async(MapPresenceService.remove_user)(self.profile_id)
            logger.info(f"Map presence disconnected: {self.profile_id} (code: {close_code})")
        else:
            logger.info(f"Map presence disconnected (code: {close_code})")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            if text_data and len(text_data) > MAX_MESSAGE_SIZE:
                logger.warning(
                    f"Oversized map presence message from {self.profile_id}: {len(text_data)} bytes"
                )
                return

            if not await self._check_rate_limit():
                return

            data = orjson.loads(text_data)
            message_type = data.get('type')

            if message_type == 'position_update':
                await self.handle_position_update(data)
            elif message_type == 'set_state':
                await self.handle_set_state(data)
            elif message_type == 'set_speech_bubble':
                await self.handle_set_speech_bubble(data)
            elif message_type == 'ping':
                # Heartbeat: refresh presence TTL so idle-but-connected users stay visible
                await sync_to_async(MapPresenceService.touch)(self.profile_id)
                await self.send(text_data=orjson.dumps({
                    'type': 'pong',
                    'timestamp': data.get('timestamp')
                }).decode())
            else:
                logger.warning(f"Unknown message type: {message_type}")

        except orjson.JSONDecodeError:
            logger.warning(f"Invalid JSON received: {text_data}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def _check_rate_limit(self) -> bool:
        """Per-profile message rate limit across all connections. Fails open on Redis errors."""
        try:
            r = _get_aioredis()
            window_key = f'map_presence:rl:{self.profile_id}:{int(time.time())}'
            count = await r.incr(window_key)
            if count == 1:
                await r.expire(window_key, 5)
            if count > RATE_LIMIT_PER_SECOND:
                if count == RATE_LIMIT_PER_SECOND + 1:  # log/notify once per window
                    logger.warning(f"Map presence rate limit exceeded: profile={self.profile_id}")
                    await self.send(text_data=orjson.dumps({
                        'type': 'error',
                        'message': 'Rate limit exceeded'
                    }).decode())
                return False
            return True
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            return True

    async def handle_position_update(self, data):
        try:
            lat = float(data.get('lat'))
            lon = float(data.get('lon'))
            zoom = int(float(data.get('zoom')))
            if not (math.isfinite(lat) and math.isfinite(lon)):
                raise ValueError('non-finite coordinates')
            if abs(lat) > LAT_LIMIT or abs(lon) > 180.0:
                raise ValueError('coordinates out of range')
        except (TypeError, ValueError, OverflowError) as e:
            logger.warning(f"Invalid position update from {self.profile_id}: {e}")
            await self.send(text_data=orjson.dumps({
                'type': 'error',
                'message': 'Invalid position data'
            }).decode())
            return

        zoom = max(0, min(zoom, 22))

        # Sanitize before broadcast — subscribers receive these fields verbatim
        avatar_type = data.get('avatar_type', 'p1')
        if avatar_type not in MapPresenceService.AVATAR_TYPES:
            avatar_type = 'p1'
        avatar_state = data.get('avatar_state', 'idle')
        if avatar_state not in MapPresenceService.AVATAR_STATES:
            avatar_state = 'idle'

        # Update position in Redis
        await sync_to_async(MapPresenceService.set_position)(
            profile_id=self.profile_id,
            lat=lat, lon=lon, zoom=zoom,
            avatar_type=avatar_type,
            avatar_state=avatar_state,
            profile_hna=self.profile_hna,
            profile_name=self.profile_name,
        )

        # Tile subscription (fixed zoom 14)
        TILE_ZOOM = 14
        x, y = lat_lon_to_tile(lat, lon, TILE_ZOOM)

        self.center_tile = f'map_tile:14:{x}_{y}'

        # 3x3 grid around viewport center
        new_tiles = set()
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                new_tiles.add(f'map_tile:14:{x + dx}_{y + dy}')

        # Unsub old tiles, sub new ones
        for tile_channel in self.subscribed_tiles - new_tiles:
            await self._feed.unsubscribe(tile_channel, self._on_tile_event)
        for tile_channel in new_tiles - self.subscribed_tiles:
            await self._feed.subscribe(tile_channel, self._on_tile_event)

        self.subscribed_tiles = new_tiles

        # Broadcast position to center tile via Redis pub/sub
        await self._feed.publish(self.center_tile, {
            'update_type': 'position',
            'sender': self.profile_id,
            'profile_id': self.profile_id,
            'lat': lat,
            'lon': lon,
            'avatar_type': avatar_type,
            'avatar_state': avatar_state,
            'profile_hna': self.profile_hna,
            'profile_name': self.profile_name,
        })

        # Get nearby users and send to client (including self)
        nearby_users = await sync_to_async(MapPresenceService.get_nearby_users)(
            lat=lat, lon=lon, radius_km=5.0, limit=100
        )

        await self.send(text_data=orjson.dumps({
            'type': 'nearby_avatars',
            'avatars': nearby_users,
            'count': len(nearby_users)
        }).decode())

    async def handle_set_state(self, data):
        try:
            state = data.get('state', 'idle')
            if state not in MapPresenceService.AVATAR_STATES:
                logger.warning(f"Invalid avatar state from {self.profile_id}: {state!r}")
                return

            await sync_to_async(MapPresenceService.set_avatar_state)(
                profile_id=self.profile_id,
                avatar_state=state
            )

            user_data = await sync_to_async(MapPresenceService.get_user_data)(self.profile_id)

            if self.center_tile:
                await self._feed.publish(self.center_tile, {
                    'update_type': 'state',
                    'sender': self.profile_id,
                    'profile_id': self.profile_id,
                    'avatar_state': state,
                    'lat': float(user_data.get('lat', 0)) if user_data else 0,
                    'lon': float(user_data.get('lon', 0)) if user_data else 0,
                    'avatar_type': user_data.get('avatar_type', 'p1') if user_data else 'p1',
                    'profile_hna': user_data.get('profile_hna', '') if user_data else '',
                    'profile_name': user_data.get('profile_name', '') if user_data else '',
                })
        except Exception as e:
            logger.error(f"Failed to set avatar state: {e}")

    async def handle_set_speech_bubble(self, data):
        try:
            text = data.get('text', '')
            if not isinstance(text, str):
                return
            # Truncate before broadcast, not only before storage
            text = text[:SPEECH_BUBBLE_MAX_CHARS]

            await sync_to_async(MapPresenceService.set_speech_bubble)(
                profile_id=self.profile_id,
                speech_bubble=text
            )

            user_data = await sync_to_async(MapPresenceService.get_user_data)(self.profile_id)

            if self.center_tile:
                await self._feed.publish(self.center_tile, {
                    'update_type': 'speech_bubble',
                    'sender': self.profile_id,
                    'profile_id': self.profile_id,
                    'speech_bubble': text,
                    'lat': float(user_data.get('lat', 0)) if user_data else 0,
                    'lon': float(user_data.get('lon', 0)) if user_data else 0,
                    'avatar_type': user_data.get('avatar_type', 'p1') if user_data else 'p1',
                    'avatar_state': user_data.get('avatar_state', 'idle') if user_data else 'idle',
                    'profile_hna': user_data.get('profile_hna', '') if user_data else '',
                    'profile_name': user_data.get('profile_name', '') if user_data else '',
                })
        except Exception as e:
            logger.error(f"Failed to set speech bubble: {e}")

    # ------------------------------------------------------------------ #
    #  Redis pub/sub callback
    # ------------------------------------------------------------------ #

    async def _on_tile_event(self, channel: str, data: dict):
        """Handle tile event from Redis pub/sub. Forward to WS client (skip self for position)."""
        update_type = data.get('update_type', 'position')

        # Self-exclusion for position updates (avoid duplicates from 3x3 grid)
        if update_type in ('position', 'leave') and data.get('sender') == self.profile_id:
            return

        if update_type == 'leave':
            await self.send(text_data=orjson.dumps({
                'type': 'avatar_update',
                'update_type': 'leave',
                'profile_id': data.get('profile_id', ''),
            }).decode())
            return

        await self.send(text_data=orjson.dumps({
            'type': 'avatar_update',
            'update_type': update_type,
            'profile_id': data.get('profile_id', ''),
            'lat': data.get('lat', 0),
            'lon': data.get('lon', 0),
            'avatar_type': data.get('avatar_type', 'p1'),
            'avatar_state': data.get('avatar_state', 'idle'),
            'profile_hna': data.get('profile_hna', ''),
            'profile_name': data.get('profile_name', ''),
            'speech_bubble': data.get('speech_bubble', ''),
        }).decode())
