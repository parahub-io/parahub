"""
Sync Redis PUBLISH helper for broadcasting WebSocket events.

Use from Django signals, views, management commands — anywhere synchronous.
For async contexts (consumers), use FeedPubSubManager.publish() instead.

Usage:
    from parahub.services.ws_publish import ws_publish
    ws_publish('user:123', {'type': 'partner.added', 'partner': {...}})
"""

import orjson
import logging

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

_pool: redis.ConnectionPool | None = None


def _get_pool() -> redis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True,
        )
    return _pool


def ws_publish(channel: str, data: dict) -> None:
    """Publish a JSON message to a Redis pub/sub channel (sync, fire-and-forget)."""
    try:
        r = redis.Redis(connection_pool=_get_pool())
        r.publish(channel, orjson.dumps(data))
    except Exception as e:
        logger.warning(f'ws_publish to {channel} failed: {e}')
