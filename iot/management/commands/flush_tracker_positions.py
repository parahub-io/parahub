"""
Daemon: flush GPS tracker positions from Redis to TimescaleDB.

Hot path (webhook) writes positions to Redis only.
This daemon flushes tracker:pending → iot_tracker_history every interval.

Usage:
    python3 manage.py flush_tracker_positions              # Run continuously (60s)
    python3 manage.py flush_tracker_positions --once        # Single flush (testing)
    python3 manage.py flush_tracker_positions --interval 30 # Custom interval
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Daemon: flush GPS tracker positions from Redis to TimescaleDB'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=int, default=60, help='Flush interval in seconds')
        parser.add_argument('--once', action='store_true', help='Single flush (for testing)')

    def handle(self, **options):
        asyncio.run(self._run(options))

    async def _run(self, options):
        interval = options['interval']
        self.stdout.write(f'Starting tracker position flusher (interval={interval}s)')

        host = getattr(settings, 'REDIS_HOST', '127.0.0.1')
        port = getattr(settings, 'REDIS_PORT', 6379)
        redis_conn = aioredis.Redis(host=host, port=port, decode_responses=True)

        while True:
            t0 = time.monotonic()

            try:
                await self._flush(redis_conn)
            except Exception:
                logger.exception('Flush cycle failed')
                # Reset stale DB connection so next cycle can reconnect
                connection.close()

            elapsed = time.monotonic() - t0

            if options['once']:
                break

            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        await redis_conn.close()

    async def _flush(self, redis_conn: aioredis.Redis):
        """Read all pending positions from Redis, batch INSERT to TimescaleDB."""
        # Atomic: get all + delete (use pipeline)
        pending = await redis_conn.hgetall('tracker:pending')
        if not pending:
            return

        batch = []
        keys_to_delete = []

        for key, raw in pending.items():
            try:
                d = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                keys_to_delete.append(key)
                continue

            t = d.get('t')
            if not t:
                keys_to_delete.append(key)
                continue

            batch.append((
                datetime.fromtimestamp(t, tz=timezone.utc),
                d['dev'],          # device_id FK (ULID)
                d['lat'],
                d['lon'],
                d.get('alt'),
                d.get('spd'),
                d.get('hdg'),
                d.get('acc'),
                d.get('bat'),
                d.get('sat'),
            ))
            keys_to_delete.append(key)

        if batch:
            await self._insert_batch(batch)

        # Clean up processed keys
        if keys_to_delete:
            await redis_conn.hdel('tracker:pending', *keys_to_delete)

        # Heartbeat: mark successful flush (monitored externally)
        await redis_conn.set('tracker:flush_ok', str(int(time.time())))

        if batch:
            logger.info(f'Flushed {len(batch)} tracker positions to TimescaleDB')

    async def _insert_batch(self, batch):
        """Batch INSERT into iot_tracker_history (TimescaleDB hypertable)."""
        sql = """
            INSERT INTO iot_tracker_history
                (time, device_id, latitude, longitude, altitude,
                 speed, heading, accuracy, battery_level, satellites)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        def _do_insert():
            with connection.cursor() as cursor:
                cursor.executemany(sql, batch)

        await sync_to_async(_do_insert, thread_sensitive=True)()
