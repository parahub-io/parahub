"""
Daemon: fetch GTFS-RT vehicle positions, store in Redis, broadcast via WS, save history.

Supports per-source mode for independent scaling:
    python3 manage.py fetch_transit_rt --source carris-metropolitana
    python3 manage.py fetch_transit_rt --source stcp-porto,carris-lisboa
    python3 manage.py fetch_transit_rt              # All active sources (legacy)
    python3 manage.py fetch_transit_rt --once        # Single poll (testing)
"""

import asyncio
import orjson
import logging
import time
from datetime import datetime, timezone

import aiohttp
import redis.asyncio as aioredis
from asgiref.sync import sync_to_async
from psycopg2.extras import execute_values
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import connection

from geo.models import TransitDataSource
from parahub.services.transit_rt import RouteCache, StopSnapper, SttProcessor

logger = logging.getLogger(__name__)

# Status enum mapping for GTFS-RT protobuf
STATUS_MAP = {0: 'INCOMING_AT', 1: 'STOPPED_AT', 2: 'IN_TRANSIT_TO'}

# Downsample: save at most 1 position per vehicle per minute
HISTORY_MIN_INTERVAL_S = 60


class Command(BaseCommand):
    help = 'Daemon: fetch GTFS-RT vehicle positions (async, per-source scaling)'

    def add_arguments(self, parser):
        parser.add_argument('--source', type=str, default='',
                            help='Comma-separated TransitDataSource slugs (empty = all active)')
        parser.add_argument('--interval', type=int, default=0,
                            help='Override poll interval for all sources (0 = use per-source rt_interval)')
        parser.add_argument('--once', action='store_true', help='Single poll (for testing)')

    def handle(self, **options):
        asyncio.run(self._run(options))

    async def _load_sources(self, slugs: list[str] | None):
        """Load TransitDataSource objects from DB."""
        def _query():
            qs = TransitDataSource.objects.filter(is_active=True).exclude(rt_vehicles_url='')
            if slugs:
                qs = qs.filter(slug__in=slugs)
            return list(qs)
        return await sync_to_async(_query)()

    async def _run(self, options):
        source_arg = options['source'].strip()
        slugs = [s.strip() for s in source_arg.split(',') if s.strip()] if source_arg else None
        override_interval = options['interval'] or None

        label = ','.join(slugs) if slugs else 'all'
        self.stdout.write(f'Starting GTFS-RT fetcher [{label}]')

        # Load sources
        sources = await self._load_sources(slugs)
        if not sources:
            self.stderr.write(f'No active RT sources found for: {slugs}')
            return

        # Data source IDs for filtered RouteCache (None = load all)
        ds_ids = [ds.id for ds in sources] if slugs else None

        # Init route cache + snapper + STT
        route_cache = RouteCache()
        redis_pub = aioredis.Redis(
            host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
            port=getattr(settings, 'REDIS_PORT', 6379),
        )
        await route_cache.refresh(redis_conn=redis_pub, data_source_ids=ds_ids)
        snapper = StopSnapper(route_cache)
        stt = SttProcessor(route_cache)

        # Per-source last-poll tracking (monotonic)
        last_poll: dict[str, float] = {}
        # Downsample tracker: "ds_id:vehicle_id" → last_saved_timestamp
        last_saved: dict[str, float] = {}

        timeout = aiohttp.ClientTimeout(total=15)

        while True:
            now_m = time.monotonic()

            # Refresh route cache + re-read source configs every 10 min
            if route_cache.is_stale(600):
                sources = await self._load_sources(slugs)
                ds_ids = [ds.id for ds in sources] if slugs else None
                await route_cache.refresh(redis_conn=redis_pub, data_source_ids=ds_ids)

            # Determine which sources are due for polling
            due = []
            for ds in sources:
                interval = override_interval or ds.rt_interval or 30
                if now_m - last_poll.get(str(ds.id), 0) >= interval:
                    due.append(ds)

            if due:
                await self._poll_sources(
                    due, route_cache, snapper, stt, redis_pub, timeout, last_poll, last_saved
                )

            if options['once']:
                break

            # Smart sleep: wait until next source is due
            sleep_time = self._calc_sleep(sources, last_poll, override_interval)
            await asyncio.sleep(sleep_time)

    async def _poll_sources(self, sources, route_cache, snapper, stt, redis_pub,
                            timeout, last_poll, last_saved):
        """Fetch and process a batch of due sources."""
        t0 = time.monotonic()

        # Concurrent fetch
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [self._fetch_one(session, ds, route_cache, snapper) for ds in sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        now = time.time()
        now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
        total_vehicles = 0
        total_fresh = 0
        routes_batch: dict[str, dict] = {}   # route_group → {vehicles: [], stop_ids: set}
        history_batch = []

        for ds, result in zip(sources, results):
            if isinstance(result, Exception):
                logger.error(f'RT fetch failed for {ds.name}: {result}')
                await sync_to_async(
                    lambda ds_id=ds.id, err=str(result)[:500]:
                        TransitDataSource.objects.filter(id=ds_id).update(last_error=err)
                )()
                # Mark as polled even on error (retry next interval, not immediately)
                last_poll[str(ds.id)] = time.monotonic()
                continue

            vehicles = result
            total_vehicles += len(vehicles)
            ds_id_str = str(ds.id)

            # Mark as polled
            last_poll[str(ds.id)] = time.monotonic()

            # Clear last_error on success
            if ds.last_error:
                await sync_to_async(
                    lambda ds_id=ds.id:
                        TransitDataSource.objects.filter(id=ds_id).update(last_error='')
                )()

            # Write-side freshness split (180s, same convention as all read
            # paths): the full feed incl. stale parked-bus ghosts (CM keeps a
            # bus's last fix for hours) goes ONLY to the transit:rt mirror
            # (relay + diagnostics / transport debug mode); everything else —
            # STT, geo/vdata spatial index, route pushes, history — takes
            # `fresh`, so Redis display keys and downstream readers never
            # carry stale fixes and ghosts stop refreshing vprev/history.
            fresh = [v for v in vehicles if v.get('t', 0) >= now - 180]
            total_fresh += len(fresh)

            # STT: track stop transitions, record segment times, detect zombies
            # Mutates vehicle dicts in-place (adds 'z', 'eta' fields)
            try:
                await stt.process_vehicles(redis_pub, ds_id_str, fresh, now)
            except Exception as e:
                logger.error(f'STT processing failed for {ds.name}: {e}')

            # a) Redis HASH — unfiltered feed mirror (GTFS-RT relay endpoints,
            # schedule endpoint with its own cutoff, debug/diagnostics)
            await sync_to_async(
                lambda ds_id=ds.id, v=vehicles: cache.set(f'transit:rt:{ds_id}', orjson.dumps(v), timeout=180)
            )()

            # b) Redis GEO spatial index + vehicle data HASH (fresh only; the
            # members SET diff below auto-evicts vehicles that went stale)
            current_members = set()
            pipe = redis_pub.pipeline(transaction=False)
            for v in fresh:
                member = f'{ds_id_str}:{v["v"]}'
                current_members.add(member)
                pipe.geoadd('transit:geo', (v['lon'], v['lat'], member))
                pipe.hset('transit:vdata', member, orjson.dumps(v))
            await pipe.execute()

            # Cleanup stale members for this data source
            prev_key = f'transit:members:{ds_id_str}'
            prev_members_raw = await redis_pub.smembers(prev_key)
            prev_members = {m if isinstance(m, str) else m.decode() for m in prev_members_raw} if prev_members_raw else set()
            stale = prev_members - current_members
            if stale:
                pipe = redis_pub.pipeline(transaction=False)
                pipe.zrem('transit:geo', *stale)
                pipe.hdel('transit:vdata', *stale)
                await pipe.execute()

            # Update members SET with TTL
            if current_members:
                await redis_pub.delete(prev_key)
                await redis_pub.sadd(prev_key, *current_members)
                await redis_pub.expire(prev_key, 300)

            # c) Batch by route for route subscriptions (with vehicle data) —
            # `fresh` already carries the 180s cutoff
            for v in fresh:
                route_src = v.get('r')
                if route_src:
                    route_group = f'transit_route:{ds_id_str}_{route_src}'
                    batch = routes_batch.setdefault(route_group, {'vehicles': [], 'stop_ids': set()})
                    batch['vehicles'].append(v)
                    if v.get('sid'):
                        batch['stop_ids'].add(v['sid'])

            # d) Downsample history (fresh only — a parked ghost would write
            # identical rows every minute for hours)
            for v in fresh:
                key = f'{ds.id}:{v["v"]}'
                if now - last_saved.get(key, 0) >= HISTORY_MIN_INTERVAL_S:
                    last_saved[key] = now
                    history_batch.append((
                        now_dt,        # time
                        ds.id,         # data_source_id
                        v['v'],        # vehicle_id
                        v['lat'],      # latitude
                        v['lon'],      # longitude
                        v.get('b'),    # bearing
                        v.get('s'),    # speed
                        v.get('r', ''),   # route_source_id
                        v.get('sid', ''), # stop_source_id
                        v.get('d'),    # direction_id
                        v.get('st', ''),  # status
                    ))

        # WS broadcast: tick + per-route vehicle data (single pipeline)
        try:
            pipe = redis_pub.pipeline(transaction=False)
            pipe.publish('transit:tick', str(int(now)))
            for route_group, batch in routes_batch.items():
                payload = orjson.dumps({
                    'vehicles': batch['vehicles'],
                    'stop_ids': list(batch['stop_ids']),
                })
                pipe.publish(route_group, payload)
            await pipe.execute()
        except Exception as e:
            logger.debug(f'WS publish failed: {e}')

        # TimescaleDB batch INSERT
        if history_batch:
            await self._insert_history(history_batch)

        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            f'Poll: {total_vehicles} vehicles ({total_fresh} fresh) from {len(sources)} sources, '
            f'{len(history_batch)} history rows, {len(routes_batch)} routes in {elapsed:.0f}ms'
        )

    @staticmethod
    def _calc_sleep(sources, last_poll, override_interval):
        """Calculate sleep time until next source is due."""
        now_m = time.monotonic()
        min_wait = 30.0
        for ds in sources:
            interval = override_interval or ds.rt_interval or 30
            elapsed = now_m - last_poll.get(str(ds.id), 0)
            remaining = interval - elapsed
            min_wait = min(min_wait, remaining)
        return max(min_wait, 0.5)  # At least 0.5s to avoid busy loop

    async def _fetch_one(self, session, ds, route_cache, snapper):
        """Fetch vehicles from a single data source (supports multi-URL + custom headers)."""
        urls = [u.strip() for u in ds.rt_vehicles_url.strip().splitlines() if u.strip()]
        headers = ds.rt_headers or {}

        if len(urls) == 1:
            url = urls[0]
            async with session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get('Content-Type', '')
                if 'json' in content_type or url.endswith('/vehicles'):
                    data = await resp.json()
                    return self._parse_json(data, ds, route_cache, snapper)
                else:
                    data = await resp.read()
                    return self._parse_protobuf(data, ds, route_cache, snapper)
        else:
            # Multi-URL: fetch all concurrently, merge protobuf results
            async def fetch_url(url):
                async with session.get(url, headers=headers) as resp:
                    resp.raise_for_status()
                    return await resp.read()

            raw_results = await asyncio.gather(*[fetch_url(u) for u in urls], return_exceptions=True)
            all_vehicles = []
            for url, result in zip(urls, raw_results):
                if isinstance(result, Exception):
                    logger.warning(f'Multi-URL fetch failed for {url}: {result}')
                    continue
                all_vehicles.extend(self._parse_protobuf(result, ds, route_cache, snapper))
            return all_vehicles

    def _parse_json(self, data, ds, route_cache, snapper):
        """Carris Metropolitana custom JSON format."""
        vehicles = []
        for v in data:
            if not v.get('lat') or not v.get('lon'):
                continue
            route_src = v.get('route_id', '')
            color, name, place_slug, rtype, route_slug = route_cache.route_info.get(route_src, ('', '', '', 3, ''))

            # Direction from pattern_id
            pattern_id = v.get('pattern_id', '')
            cm_dir = None
            if pattern_id:
                parts = pattern_id.rsplit('_', 1)
                if len(parts) == 2 and parts[1].isdigit():
                    cm_dir = int(parts[1])
            direction_id = {1: 0, 2: 1}.get(cm_dir)  # CM 1=outbound→0, 2=return→1, 3=variant→None

            headsign = route_cache.headsign_info.get((route_src, direction_id), '')

            stop_id = v.get('stop_id', '')

            # Stop snapping fallback
            if not stop_id and route_src:
                snap_result = snapper.snap(v['lat'], v['lon'], route_src, direction_id)
                if snap_result:
                    stop_id = snap_result[0]
                    if direction_id is None:
                        direction_id = snap_result[1]
                        headsign = route_cache.headsign_info.get((route_src, direction_id), headsign)

            vehicles.append({
                'v': v.get('id', ''),
                'lat': v['lat'],
                'lon': v['lon'],
                # CM uses bearing:0 as a sentinel for "unknown" (~22% of vehicles
                # report exactly 0, vs ~0.5% expected for genuine due-north) — treat
                # 0/missing as no heading so the map skips the direction chevron
                # instead of pointing a fifth of the fleet north. See PK/gtfs-feed-quirks.md.
                'b': v.get('bearing') or None,
                's': round(v.get('speed', 0) * 3.6, 1),
                'r': route_src,
                'rc': color,
                'rn': name,
                'rt': rtype,
                'st': v.get('current_status', ''),
                't': v.get('timestamp') or int(time.time()),
                'tid': v.get('trip_id', ''),
                'sid': stop_id,
                'd': direction_id,
                'hs': headsign,
                'ps': place_slug,
                'rs': route_slug,
            })
        return vehicles

    def _parse_protobuf(self, data, ds, route_cache, snapper):
        """Standard GTFS-RT FeedMessage protobuf."""
        from google.transit import gtfs_realtime_pb2

        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(data)

        vehicles = []
        for entity in feed.entity:
            vp = entity.vehicle
            if not vp.position.latitude or not vp.position.longitude:
                continue
            route_src = vp.trip.route_id
            color, name, place_slug, rtype, route_slug = route_cache.route_info.get(route_src, ('', '', '', 3, ''))
            direction_id = vp.trip.direction_id
            headsign = route_cache.headsign_info.get((route_src, direction_id), '')

            stop_id = vp.stop_id

            # Stop snapping fallback
            if not stop_id and route_src:
                snap_result = snapper.snap(
                    vp.position.latitude, vp.position.longitude,
                    route_src, direction_id
                )
                if snap_result:
                    stop_id = snap_result[0]

            vehicles.append({
                'v': vp.vehicle.id or entity.id,
                'lat': vp.position.latitude,
                'lon': vp.position.longitude,
                # proto2 returns 0.0 for an unset bearing, indistinguishable from
                # genuine due north — use HasField so a missing bearing stays None
                # and the map skips the direction chevron instead of pointing up.
                'b': vp.position.bearing if vp.position.HasField('bearing') else None,
                's': round(vp.position.speed * 3.6, 1),
                'r': route_src,
                'rc': color,
                'rn': name,
                'rt': rtype,
                'st': STATUS_MAP.get(vp.current_status, str(vp.current_status)),
                # Fallback to receive time (mirrors the CM JSON path): protobuf
                # default 0 for a missing timestamp would otherwise read as
                # infinitely stale and silently blank the whole feed
                't': vp.timestamp or int(time.time()),
                'tid': vp.trip.trip_id,
                'sid': stop_id,
                'd': direction_id,
                'hs': headsign,
                'ps': place_slug,
                'rs': route_slug,
            })
        return vehicles

    async def _insert_history(self, batch):
        """Batch INSERT into TimescaleDB via raw SQL (sync_to_async)."""
        # execute_values folds the whole batch into one multi-row INSERT;
        # executemany here meant one server round-trip per vehicle position.
        sql = """
            INSERT INTO geo_vehiclepositionhistory
                (time, data_source_id, vehicle_id, latitude, longitude,
                 bearing, speed, route_source_id, stop_source_id, direction_id, status)
            VALUES %s
        """

        def _do_insert():
            with connection.cursor() as cursor:
                execute_values(cursor.cursor, sql, batch, page_size=1000)

        try:
            await sync_to_async(_do_insert, thread_sensitive=True)()
        except Exception as e:
            logger.error(f'History INSERT failed ({len(batch)} rows): {e}')
