"""
Unified real-time WebSocket consumer.

Single multiplexed connection per user handles:
- Object subscriptions (ULID-based, e.g. IoT devices)
- Personal notifications (partner added, debt created, etc.)
- Room-based updates (polls, treasury)
- Global broadcasts (ads feed)

Map presence stays separate (geo-tile paradigm).
"""

import json
import logging
from channels.db import database_sync_to_async
from .base import AuthenticatedJsonWebsocketConsumer
from .deploy_slot import get_deploy_slot
from .feed_pubsub import FeedPubSubManager

logger = logging.getLogger(__name__)

# Max ULIDs per subscribe/unsubscribe request
BATCH_LIMIT = 1000
# Max total subscriptions per connection
MAX_SUBSCRIPTIONS = 1000

# Registry: object_type -> config
# visibility: 'public' = any authenticated user can subscribe, 'owner' = owner match required
_TYPE_REGISTRY = {
    'iot_device':    {'model': 'iot.IoTDevice',       'owner': 'owner__account', 'visibility': 'owner'},
    'item':          {'model': 'market.Item',          'visibility': 'public'},
    'profile':       {'model': 'identity.Profile',     'visibility': 'public'},
    'establishment': {'model': 'geo.Establishment',    'visibility': 'public'},
    'event':         {'model': 'geo.Event',            'visibility': 'public'},
    'poll':          {'model': 'governance.Poll',       'visibility': 'public'},
}

# Room registry: room_type -> config
_ROOM_REGISTRY = {
    'poll': {
        'channel_prefix': 'poll:',
    },
    'treasury': {
        'channel_prefix': 'treasury:',
    },
    'agent_log': {
        'channel_prefix': 'agent_log:',
    },
    'agent_stats': {
        'channel_prefix': 'agent_stats:',
    },
    'opensky': {
        'channel_prefix': 'opensky:',
    },
    'parasos': {
        'channel_prefix': 'parasos:',
    },
}


class RealtimeConsumer(AuthenticatedJsonWebsocketConsumer):
    """
    Unified consumer for all real-time updates (except map presence).

    Client messages:
        {"type": "subscribe", "ids": ["ULID1", ...]}
        {"type": "unsubscribe", "ids": ["ULID1", ...]}
        {"type": "join", "room": "poll|treasury", "id": "ULID"}
        {"type": "leave", "room": "poll|treasury", "id": "ULID"}

    Server messages:
        {"type": "subscribed", "ids": [...], "denied": [...]}
        {"type": "unsubscribed", "ids": [...]}
        {"type": "object.updated", ...}
        {"type": "room.joined", "room": "...", "id": "..."}
        {"type": "room.left", "room": "...", "id": "..."}
        {"type": "poll.*", ...}  (poll events)
        {"type": "notification", ...}  (personal notifications)
    """

    async def connect(self):
        self.subscribed_ids: set[str] = set()
        self.joined_rooms: dict[str, set[str]] = {}  # {"poll": {"ID1"}, "treasury": {"ID2"}}
        self._deploy_slot = get_deploy_slot(self.scope)

        await super().connect()

        # Init FeedPubSubManager
        self._feed = FeedPubSubManager.get()
        await self._feed.ensure_running()

        # Auto-subscribe to personal notification channel
        await self._feed.subscribe(f'user:{self.user.id}', self._on_notification)

        # Auto-subscribe to global broadcast channels
        await self._feed.subscribe('ads_feed', self._on_ads_feed)
        await self._feed.subscribe('feed:system', self._on_feed_system)

    async def disconnect(self, close_code):
        # Unsubscribe from personal + global channels
        if hasattr(self, '_feed'):
            await self._feed.unsubscribe(f'user:{self.user.id}', self._on_notification)
            await self._feed.unsubscribe('ads_feed', self._on_ads_feed)
            await self._feed.unsubscribe('feed:system', self._on_feed_system)

            # Leave all ULID subscription channels
            for ulid in list(self.subscribed_ids):
                await self._feed.unsubscribe(f'object:{ulid}', self._on_object_update)
            self.subscribed_ids.clear()

            # Leave all room channels
            for room_type, ids in self.joined_rooms.items():
                config = _ROOM_REGISTRY.get(room_type)
                if config:
                    for room_id in ids:
                        await self._feed.unsubscribe(
                            f"{config['channel_prefix']}{room_id}",
                            self._on_room_event,
                        )
            self.joined_rooms.clear()

        await super().disconnect(close_code)

    # ------------------------------------------------------------------ #
    #  Client message handlers (routed by base class receive_json)
    # ------------------------------------------------------------------ #

    async def handle_subscribe(self, content):
        ids = content.get('ids', [])
        if not isinstance(ids, list) or len(ids) > BATCH_LIMIT:
            await self.send_error(f'ids must be a list of max {BATCH_LIMIT} items')
            return

        if not ids:
            await self.send_error('ids list is empty')
            return

        # Enforce per-connection limit
        new_ids = [uid for uid in ids if uid not in self.subscribed_ids]
        available_slots = MAX_SUBSCRIPTIONS - len(self.subscribed_ids)
        if available_slots <= 0:
            await self.send_error(f'Subscription limit reached ({MAX_SUBSCRIPTIONS})')
            return
        if len(new_ids) > available_slots:
            new_ids = new_ids[:available_slots]

        # Owner-restricted ids need DB permission check
        denied = set()
        if new_ids:
            denied = await self._check_owner_permissions(new_ids)

        allowed = [uid for uid in new_ids if uid not in denied]

        for ulid in allowed:
            await self._feed.subscribe(f'object:{ulid}', self._on_object_update)
            self.subscribed_ids.add(ulid)

        await self.send_json({
            'type': 'subscribed',
            'ids': allowed,
            'denied': list(denied) if denied else [],
        })

    async def handle_unsubscribe(self, content):
        ids = content.get('ids', [])
        if not isinstance(ids, list) or len(ids) > BATCH_LIMIT:
            await self.send_error(f'ids must be a list of max {BATCH_LIMIT} items')
            return

        removed = []
        for ulid in ids:
            if ulid in self.subscribed_ids:
                await self._feed.unsubscribe(f'object:{ulid}', self._on_object_update)
                self.subscribed_ids.discard(ulid)
                removed.append(ulid)

        await self.send_json({
            'type': 'unsubscribed',
            'ids': removed,
        })

    async def handle_join(self, content):
        """Join a room (poll, treasury)."""
        room = content.get('room')
        room_id = content.get('id')

        if not room or not room_id:
            await self.send_error('room and id are required')
            return

        config = _ROOM_REGISTRY.get(room)
        if not config:
            await self.send_error(f'Unknown room type: {room}')
            return

        # Permission check
        allowed = await self._check_room_permission(room, room_id)
        if not allowed:
            await self.send_error(f'Access denied to {room}/{room_id}')
            return

        # Subscribe to Redis pub/sub channel
        channel = f"{config['channel_prefix']}{room_id}"
        await self._feed.subscribe(channel, self._on_room_event)

        # Track joined rooms
        if room not in self.joined_rooms:
            self.joined_rooms[room] = set()
        self.joined_rooms[room].add(room_id)

        await self.send_json({
            'type': 'room.joined',
            'room': room,
            'id': room_id,
        })

        # Send initial state
        initial_state = await self._get_room_initial_state(room, room_id)
        if initial_state is not None:
            await self.send_json({
                'type': f'{room}.initial_state',
                **initial_state,
            })

    async def handle_leave(self, content):
        """Leave a room."""
        room = content.get('room')
        room_id = content.get('id')

        if not room or not room_id:
            await self.send_error('room and id are required')
            return

        config = _ROOM_REGISTRY.get(room)
        if not config:
            return

        channel = f"{config['channel_prefix']}{room_id}"
        await self._feed.unsubscribe(channel, self._on_room_event)

        if room in self.joined_rooms:
            self.joined_rooms[room].discard(room_id)
            if not self.joined_rooms[room]:
                del self.joined_rooms[room]

        await self.send_json({
            'type': 'room.left',
            'room': room,
            'id': room_id,
        })

    # ------------------------------------------------------------------ #
    #  Redis pub/sub callbacks — forward to WS client
    # ------------------------------------------------------------------ #

    async def _on_object_update(self, channel: str, data: dict):
        """object:{ulid} → forward object update."""
        await self.send_json(data)

    async def _on_notification(self, channel: str, data: dict):
        """user:{account_id} → forward personal notification."""
        await self.send_json(data)

    async def _on_ads_feed(self, channel: str, data: dict):
        """ads_feed → forward ads event."""
        await self.send_json(data)

    async def _on_feed_system(self, channel: str, data: dict):
        """feed:system → forward system event (filtered by deployment slot)."""
        msg_slot = data.get('slot')
        if msg_slot and msg_slot != self._deploy_slot:
            return
        await self.send_json({
            'type': 'feed.system',
            **data,
        })

    async def _on_room_event(self, channel: str, data: dict):
        """poll:{id} / treasury:{id} → forward room event."""
        await self.send_json(data)

    # ------------------------------------------------------------------ #
    #  Permission helpers
    # ------------------------------------------------------------------ #

    @database_sync_to_async
    def _check_owner_permissions(self, ulids: list[str]) -> set[str]:
        """Return set of denied ULIDs (only checks owner-restricted types).
        Public objects are allowed without DB queries."""
        from django.apps import apps

        denied: set[str] = set()
        remaining = set(ulids)

        for object_type, config in _TYPE_REGISTRY.items():
            if config['visibility'] != 'owner' or not remaining:
                continue

            Model = apps.get_model(*config['model'].split('.'))
            # Find objects of this type that exist but don't belong to user
            all_ids = set(Model.objects.filter(id__in=list(remaining)).values_list('id', flat=True))
            owned_ids = set(Model.objects.filter(
                id__in=list(all_ids),
                **{config['owner']: self.user},
            ).values_list('id', flat=True))
            denied |= (all_ids - owned_ids)
            remaining -= all_ids

        return denied

    @database_sync_to_async
    def _check_room_permission(self, room: str, room_id: str) -> bool:
        """Check if user can join a room."""
        if room == 'poll':
            from governance.models import Poll
            return Poll.objects.filter(id=room_id).exists()

        elif room == 'treasury':
            # Treasury room is public (anyone authenticated can join)
            return True

        elif room == 'agent_log':
            # Agent log requires is_staff
            return self.user.is_staff and room_id in ('pixel', 'forge', 'scout', 'kevin')

        elif room == 'agent_stats':
            return self.user.is_staff and room_id == 'global'

        elif room == 'opensky':
            return True  # Any authenticated user

        elif room == 'parasos':
            from parasos.models import SafetyGroupMember
            return SafetyGroupMember.objects.filter(
                group_id=room_id, profile=self.profile,
            ).exists()

        return False

    @database_sync_to_async
    def _get_room_initial_state(self, room: str, room_id: str):
        """Get initial state to send when joining a room."""
        if room == 'poll':
            from governance.models import Poll
            from governance.services import VotingService
            try:
                poll = Poll.objects.get(id=room_id)
                service = VotingService(poll)
                results = service.calculate_results()
                return {
                    'poll_id': poll.id,
                    'status': poll.status,
                    'total_voted': results['total_voted'],
                    'total_eligible': results['total_eligible'],
                    'quorum_met': results['quorum_met'],
                    'results': results['results'],
                }
            except Poll.DoesNotExist:
                return None

        elif room == 'agent_log':
            from agents.services import get_log_tail
            lines = get_log_tail(room_id, 50)
            return {'agent': room_id, 'backfill': lines}

        elif room == 'agent_stats':
            from agents.services import get_stats_summary
            return get_stats_summary()

        return None

