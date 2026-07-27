"""Public WebSocket consumer for live environmental-station readings.

URL: ws/v1/env/
Auth: none — mirrors the public ``/env-stations/map`` feed. A client subscribes
to public stations by id and receives a ``station_update`` on every new
reading (poll bridge or push ingest → ``env_service.record_reading`` publishes
``env:tick``). Two subscription shapes: one station (feature panel) or a list
(map HUD markers — all visible stations at once).

Client sends:
    { "type": "subscribe_station", "station_id": "ULID" }
    { "type": "subscribe_stations", "station_ids": ["ULID", ...] }   # replaces the set
    { "type": "unsubscribe" }
    { "type": "ping", "timestamp": 1234567890 }

Server sends:
    { "type": "station_update", "station": {id, name, source, latest, last_reading_at, ...} }
    { "type": "unsubscribed" }
    { "type": "pong", "timestamp": 1234567890 }
"""

import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .feed_pubsub import FeedPubSubManager

logger = logging.getLogger(__name__)


MAX_SUBSCRIBED_STATIONS = 200


class EnvStationConsumer(AsyncJsonWebsocketConsumer):
    """Public live readings for a set of stations (single id or id list)."""

    async def connect(self):
        self._station_ids: set[str] = set()
        self._subscribed = False
        self._feed = FeedPubSubManager.get()
        await self._feed.ensure_running()
        await self.accept()

    async def disconnect(self, close_code):
        if self._subscribed:
            await self._feed.unsubscribe('env:tick', self._on_tick)
            self._subscribed = False

    async def receive_json(self, content):
        msg_type = content.get('type')
        if msg_type == 'subscribe_station':
            station_id = content.get('station_id') or ''
            if not station_id:
                return
            await self._set_subscription({str(station_id)})
        elif msg_type == 'subscribe_stations':
            ids = content.get('station_ids') or []
            if not isinstance(ids, list):
                return
            wanted = {str(i) for i in ids if i}
            await self._set_subscription(set(list(wanted)[:MAX_SUBSCRIBED_STATIONS]))
        elif msg_type == 'unsubscribe':
            await self._set_subscription(set())
            await self.send_json({'type': 'unsubscribed'})
        elif msg_type == 'ping':
            await self.send_json({'type': 'pong', 'timestamp': content.get('timestamp')})

    async def _set_subscription(self, ids: set):
        """Replace the subscribed set; attach/detach the pubsub handler to match."""
        self._station_ids = ids
        if ids and not self._subscribed:
            await self._feed.subscribe('env:tick', self._on_tick)
            self._subscribed = True
        elif not ids and self._subscribed:
            await self._feed.unsubscribe('env:tick', self._on_tick)
            self._subscribed = False

    async def _on_tick(self, channel: str, data: dict):
        """env:tick received — forward only subscribed, public stations."""
        if str(data.get('id')) not in self._station_ids:
            return
        # Defensive: never leak a private station even if its id is known.
        if not data.get('is_public'):
            return
        await self.send_json({'type': 'station_update', 'station': data})
