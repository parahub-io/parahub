"""
Shared sync Redis connection pools.

A bare `redis.Redis(host=..., port=...)` inside a view builds a private
ConnectionPool per call — one TCP connect + teardown per request. Import
`get_redis()` instead: clients share a module-level pool, so connections are
reused across requests within a worker.

For async contexts (consumers, daemons) keep using redis.asyncio clients —
those are long-lived per process/connection, not per-request.
"""

import redis
from django.conf import settings

_pools: dict[bool, redis.ConnectionPool] = {}


def get_redis(decode_responses: bool = True) -> redis.Redis:
    """Pooled sync Redis client. Do not call .close() on it."""
    pool = _pools.get(decode_responses)
    if pool is None:
        pool = _pools[decode_responses] = redis.ConnectionPool(
            host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
            port=getattr(settings, 'REDIS_PORT', 6379),
            decode_responses=decode_responses,
        )
    return redis.Redis(connection_pool=pool)
