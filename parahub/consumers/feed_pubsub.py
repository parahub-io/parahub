"""
Native Redis pub/sub feed manager.

channels_redis uses sorted sets (ZADD/ZRANGE per member) for group messaging — O(N)
per broadcast. For high fan-out feeds (transit, system-wide notifications) native Redis
pub/sub is O(1) publish. This module provides a singleton per-worker that shares a
single redis.asyncio connection for all consumers in the process.

Usage from a consumer:
    manager = FeedPubSubManager.get()
    await manager.ensure_running()
    await manager.subscribe('feed:system', self._on_feed)
    ...
    await manager.unsubscribe('feed:system', self._on_feed)

Publishing (from CLI / deploy script):
    redis-cli PUBLISH feed:system '{"event":"new_version","slot":"prod"}'
"""

import asyncio
import orjson
import logging

import redis.asyncio as aioredis
from django.conf import settings

logger = logging.getLogger(__name__)


class FeedPubSubManager:
    """Singleton per worker process. One aioredis pub/sub connection shared by all consumers."""

    _instance: 'FeedPubSubManager | None' = None

    def __init__(self):
        self._redis: aioredis.Redis | None = None
        self._redis_pub: aioredis.Redis | None = None  # separate conn for PUBLISH (sub mode can't publish)
        self._pubsub: aioredis.client.PubSub | None = None
        self._listeners: dict[str, set] = {}  # channel -> {async_callback, ...}
        self._task: asyncio.Task | None = None
        self._has_subscriptions = asyncio.Event()

    @classmethod
    def get(cls) -> 'FeedPubSubManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def ensure_running(self):
        """Lazy-init: create aioredis connection + background listener task."""
        if self._task and not self._task.done():
            return

        host = getattr(settings, 'REDIS_HOST', '127.0.0.1')
        port = getattr(settings, 'REDIS_PORT', 6379)

        self._redis = aioredis.Redis(host=host, port=port, decode_responses=True)
        self._redis_pub = aioredis.Redis(host=host, port=port, decode_responses=True)
        self._pubsub = self._redis.pubsub()
        self._task = asyncio.ensure_future(self._listen())

    async def subscribe(self, channel: str, callback):
        """Register async callback for a Redis pub/sub channel."""
        if channel not in self._listeners:
            self._listeners[channel] = set()
            # First listener for this channel — subscribe in Redis
            if self._pubsub:
                await self._pubsub.subscribe(channel)
                self._has_subscriptions.set()

        self._listeners[channel].add(callback)

    async def publish(self, channel: str, data: dict):
        """Publish JSON message to a Redis pub/sub channel (async)."""
        if self._redis_pub:
            await self._redis_pub.publish(channel, orjson.dumps(data))

    async def unsubscribe(self, channel: str, callback):
        """Remove callback. Unsubscribe from Redis if last listener."""
        listeners = self._listeners.get(channel)
        if not listeners:
            return

        listeners.discard(callback)
        if not listeners:
            del self._listeners[channel]
            if self._pubsub:
                await self._pubsub.unsubscribe(channel)

    async def _listen(self):
        """Infinite loop: read from pub/sub, dispatch to callbacks."""
        try:
            # Wait until at least one channel is subscribed (avoids RuntimeError)
            await self._has_subscriptions.wait()

            while True:
                if not self._pubsub:
                    await asyncio.sleep(1)
                    continue

                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    continue

                channel = message.get('channel', '')
                raw_data = message.get('data', '')

                # Parse JSON payload
                try:
                    data = orjson.loads(raw_data) if isinstance(raw_data, str) else {}
                except (orjson.JSONDecodeError, TypeError):
                    data = {'raw': raw_data}

                # Dispatch to registered callbacks
                callbacks = self._listeners.get(channel, set()).copy()
                for cb in callbacks:
                    try:
                        await cb(channel, data)
                    except Exception:
                        logger.exception(f'Feed callback error on {channel}')

        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception('FeedPubSubManager listener crashed')
        finally:
            if self._pubsub:
                try:
                    await self._pubsub.close()
                except Exception:
                    pass
            for conn in (self._redis, self._redis_pub):
                if conn:
                    try:
                        await conn.close()
                    except Exception:
                        pass
