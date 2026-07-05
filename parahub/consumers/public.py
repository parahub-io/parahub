"""
Public WebSocket consumer for anonymous broadcast events.

No authentication required. Subscribes only to feed:system (new_version, maintenance, etc.).
Authenticated users get these events via RealtimeConsumer instead.
"""

import json
import logging
import uuid

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .deploy_slot import get_deploy_slot
from .feed_pubsub import FeedPubSubManager
from parahub.services.presence import PresenceService

logger = logging.getLogger(__name__)


class PublicConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        self._deploy_slot = get_deploy_slot(self.scope)
        # Unique id per anonymous connection — guests are counted, not identified
        self._anon_id = uuid.uuid4().hex
        await self.accept()
        self._feed = FeedPubSubManager.get()
        await self._feed.ensure_running()
        await self._feed.subscribe('feed:system', self._on_feed)
        await sync_to_async(PresenceService.mark_anon_online)(self._deploy_slot, self._anon_id)

    async def disconnect(self, close_code):
        if hasattr(self, '_feed'):
            await self._feed.unsubscribe('feed:system', self._on_feed)
        if hasattr(self, '_anon_id'):
            await sync_to_async(PresenceService.mark_anon_offline)(self._deploy_slot, self._anon_id)

    async def receive_json(self, content):
        # Heartbeat only — no other client messages supported
        if content.get('type') == 'heartbeat':
            await self.send_json({'type': 'heartbeat.response', 'timestamp': content.get('timestamp')})
            if hasattr(self, '_anon_id'):
                await sync_to_async(PresenceService.touch_anon)(self._deploy_slot, self._anon_id)

    async def _on_feed(self, channel: str, data: dict):
        msg_slot = data.get('slot')
        if msg_slot and msg_slot != self._deploy_slot:
            return
        await self.send_json({'type': 'feed.system', **data})
