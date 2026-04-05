"""
Public WebSocket consumer for anonymous broadcast events.

No authentication required. Subscribes only to feed:system (new_version, maintenance, etc.).
Authenticated users get these events via RealtimeConsumer instead.
"""

import json
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .deploy_slot import get_deploy_slot
from .feed_pubsub import FeedPubSubManager

logger = logging.getLogger(__name__)


class PublicConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        self._deploy_slot = get_deploy_slot(self.scope)
        await self.accept()
        self._feed = FeedPubSubManager.get()
        await self._feed.ensure_running()
        await self._feed.subscribe('feed:system', self._on_feed)

    async def disconnect(self, close_code):
        if hasattr(self, '_feed'):
            await self._feed.unsubscribe('feed:system', self._on_feed)

    async def receive_json(self, content):
        # Heartbeat only — no other client messages supported
        if content.get('type') == 'heartbeat':
            await self.send_json({'type': 'heartbeat.response', 'timestamp': content.get('timestamp')})

    async def _on_feed(self, channel: str, data: dict):
        msg_slot = data.get('slot')
        if msg_slot and msg_slot != self._deploy_slot:
            return
        await self.send_json({'type': 'feed.system', **data})
