"""
Real-time presence service — "who is on the site right now".

Backed by Redis sorted sets, fed by the WebSocket connection lifecycle:
  - authenticated clients open ``ws/v1/realtime/`` (RealtimeConsumer)
  - anonymous clients open ``ws/v1/public/`` (PublicConsumer)

Each connection ZADDs itself with score = last-seen unix ts and refreshes that
score on every heartbeat (frontend pings every 30s). "Online" = score within the
freshness WINDOW, so an ungracefully dropped connection (sleep / crash / network
loss) ages out automatically instead of lingering. A clean disconnect ZREMs
immediately.

Keys are namespaced per deployment slot (prod / dev1 / …) because Redis is shared
across prod and all dev slots — without the namespace the prod count would mix in
the AI-agent dev slots and vice versa.

All operations are synchronous (redis-py, like ``map_presence`` / ``ws_publish``);
async consumers call them through ``sync_to_async``.
"""

import logging
import time

import orjson
import redis
from django.conf import settings

from parahub.services.ws_publish import ws_publish

logger = logging.getLogger(__name__)

# Freshness window. A member counts as online while its last-seen score is within
# the last WINDOW seconds (inclusive). Frontend heartbeat is 30s, so 60s tolerates
# exactly one missed/late beat without flicker; a backgrounded (throttled) tab that
# stops beating ages out — which is the truthful answer (not actively present).
WINDOW = 60
TOP_N = 5


class PresenceService:
    """Per-slot online presence over Redis sorted sets."""

    _pool: redis.ConnectionPool | None = None

    @classmethod
    def _r(cls) -> redis.Redis:
        if cls._pool is None:
            cls._pool = redis.ConnectionPool(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                decode_responses=True,
            )
        return redis.Redis(connection_pool=cls._pool)

    # --- key helpers -------------------------------------------------------- #

    @staticmethod
    def _auth_key(slot: str) -> str:
        return f'presence:auth:{slot}'

    @staticmethod
    def _anon_key(slot: str) -> str:
        return f'presence:anon:{slot}'

    @staticmethod
    def _meta_key(slot: str) -> str:
        return f'presence:meta:{slot}'

    @staticmethod
    def _conn_key(slot: str) -> str:
        # profile_id -> number of open connections (multi-tab / multi-device ref count)
        return f'presence:conn:{slot}'

    @staticmethod
    def _lastpub_key(slot: str) -> str:
        return f'presence:lastpub:{slot}'

    @staticmethod
    def _channel(slot: str) -> str:
        return f'presence:{slot}'

    # --- authenticated presence -------------------------------------------- #

    @classmethod
    def mark_online(cls, slot: str, profile_id: str, meta: dict) -> None:
        """Connect: ref-count this connection, refresh score + cache display fields.
        A profile may hold several connections (tabs / devices); it counts once."""
        try:
            r = cls._r()
            pipe = r.pipeline()
            pipe.hincrby(cls._conn_key(slot), profile_id, 1)
            pipe.zadd(cls._auth_key(slot), {profile_id: time.time()})
            pipe.hset(cls._meta_key(slot), profile_id, orjson.dumps(meta).decode())
            pipe.execute()
            cls._publish(slot, force=True)
        except Exception as e:
            logger.warning(f'presence mark_online failed: {e}')

    @classmethod
    def mark_offline(cls, slot: str, profile_id: str) -> None:
        """Clean disconnect of one connection. Only drop the profile when its last
        connection closes — otherwise other tabs/devices keep it online (and its
        avatar/meta intact)."""
        try:
            r = cls._r()
            remaining = r.hincrby(cls._conn_key(slot), profile_id, -1)
            if remaining <= 0:
                pipe = r.pipeline()
                pipe.zrem(cls._auth_key(slot), profile_id)
                pipe.hdel(cls._meta_key(slot), profile_id)
                pipe.hdel(cls._conn_key(slot), profile_id)
                pipe.execute()
                cls._publish(slot, force=True)
            else:
                # still online via another connection — headcount unchanged
                cls._publish(slot, force=False)
        except Exception as e:
            logger.warning(f'presence mark_offline failed: {e}')

    @classmethod
    def touch(cls, slot: str, profile_id: str) -> None:
        """Heartbeat: refresh the freshness score; republish only if the count changed."""
        try:
            cls._r().zadd(cls._auth_key(slot), {profile_id: time.time()})
            cls._publish(slot, force=False)
        except Exception as e:
            logger.warning(f'presence touch failed: {e}')

    # --- anonymous presence (count only, no identity) ---------------------- #

    @classmethod
    def mark_anon_online(cls, slot: str, conn_id: str) -> None:
        try:
            cls._r().zadd(cls._anon_key(slot), {conn_id: time.time()})
            cls._publish(slot, force=True)
        except Exception as e:
            logger.warning(f'presence mark_anon_online failed: {e}')

    @classmethod
    def mark_anon_offline(cls, slot: str, conn_id: str) -> None:
        try:
            cls._r().zrem(cls._anon_key(slot), conn_id)
            cls._publish(slot, force=True)
        except Exception as e:
            logger.warning(f'presence mark_anon_offline failed: {e}')

    @classmethod
    def touch_anon(cls, slot: str, conn_id: str) -> None:
        try:
            cls._r().zadd(cls._anon_key(slot), {conn_id: time.time()})
            cls._publish(slot, force=False)
        except Exception as e:
            logger.warning(f'presence touch_anon failed: {e}')

    # --- snapshot + publish ------------------------------------------------ #

    @classmethod
    def _prune(cls, r: redis.Redis, slot: str, cutoff: float) -> None:
        """Drop members whose last-seen is older than the window (score < cutoff).
        Done before each read so stale connections never inflate the count, and the
        meta hash is cleaned for removed profiles so it stays bounded."""
        auth_key = cls._auth_key(slot)
        stale = r.zrangebyscore(auth_key, '-inf', f'({cutoff}')
        if stale:
            pipe = r.pipeline()
            pipe.zrem(auth_key, *stale)
            pipe.hdel(cls._meta_key(slot), *stale)
            pipe.hdel(cls._conn_key(slot), *stale)
            pipe.execute()
        r.zremrangebyscore(cls._anon_key(slot), '-inf', f'({cutoff}')

    @classmethod
    def get_snapshot(cls, slot: str) -> dict:
        """Return {total, anon, users:[{id,hna,name,avatar}…≤TOP_N]} for the slot.
        ``total`` is authenticated people online; ``anon`` is guests; ``users`` are
        the most-recently-active authenticated profiles."""
        r = cls._r()
        cutoff = time.time() - WINDOW
        cls._prune(r, slot, cutoff)

        total = r.zcount(cls._auth_key(slot), cutoff, '+inf')
        anon = r.zcount(cls._anon_key(slot), cutoff, '+inf')
        top_ids = r.zrevrangebyscore(
            cls._auth_key(slot), '+inf', cutoff, start=0, num=TOP_N,
        )

        users = []
        if top_ids:
            for pid, raw in zip(top_ids, r.hmget(cls._meta_key(slot), top_ids)):
                if not raw:
                    continue
                try:
                    m = orjson.loads(raw)
                except orjson.JSONDecodeError:
                    continue
                m['id'] = pid
                users.append(m)

        return {'total': total, 'anon': anon, 'users': users}

    @classmethod
    def _publish(cls, slot: str, force: bool) -> None:
        """Publish a snapshot to presence:{slot}. When force is False (heartbeat),
        skip if the headcount is unchanged since the last publish — so heartbeats
        don't spam staff clients, but a member ageing out still triggers one."""
        snap = cls.get_snapshot(slot)
        headcount = f"{snap['total']}:{snap['anon']}"
        r = cls._r()
        if not force and r.get(cls._lastpub_key(slot)) == headcount:
            return
        r.set(cls._lastpub_key(slot), headcount, ex=300)
        ws_publish(cls._channel(slot), {'type': 'presence.snapshot', **snap})
