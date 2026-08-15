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

# TML's GO Hub publishes ONE combined GTFS-RT feed carrying every operator it
# hosts (~1250 vehicles), each vehicle id bracketed with the operator's internal
# GO agency id: "[7NTB1]14241". A source reading that feed must keep only its
# own operator's vehicles, or every daemon ingests the foreign ones under its
# own ds_id — duplicated map markers and a poisoned STT. Per-feed opt-in keyed
# by TransitDataSource.slug (same shape as SYNTHESIZE_LINE_ID_FEEDS); the prefix
# is stripped from the stored id so vehicle history keys stay stable if TML ever
# renumbers plans. Values are TUPLES because one operator can span several GO
# agency ids (CRTM is published as two: one plan per interurban lot).
# See PK/gtfs-feed-quirks.md "GO Hub (TML)".
RT_VEHICLE_PREFIX = {
    'fertagus': ('[7NTB1]',),
    'tcb-barreiro': ('[A3H3M]',),
    'cascais-proxima': ('[HF16N]',),
    'crtm-madrid': ('[G8N1G]', '[DFS5M]'),
    # Live layer only — TTSL's static stays the operator's own feed, whose
    # route_ids ("3_0") and stop_ids ("3") the GO Hub RT matches verbatim.
    'transtejo-soflusa': ('[LTP61]',),
    # cp-rail's static moved TO the GO Hub plan so these ids resolve; against
    # CP's own export they did not (line-based SINTRA_1 vs O-D 21-94_…).
    'cp-rail': ('[N18KL]',),
}

# GO Hub also publishes per-vehicle STATIC metadata (make/model/plate/
# accessibility) as one combined JSON for all operators it hosts. Feeds that
# opt in get it fetched on the 10-min config-refresh cadence — it is fleet
# registry data, not telemetry, so it has no place in the 15s vehicle loop —
# and joined onto parsed vehicles as '_meta', riding the existing CM pipeline
# (stripped off in _poll_sources into transit:vmeta:* for the popup endpoint).
# Join: records are matched by their GO agency_id (RT_VEHICLE_PREFIX minus
# brackets) and keyed by vehicle_id after its '<gtfs agency id>-' prefix
# ("21-1002" → "1002" = the RT vehicle id after OUR prefix strip). Coverage is
# whatever TML has registered: today that resolves Cascais Próxima (~2/3 of its
# live fleet); Fertagus's registry ids don't match its RT train numbers and
# CP/TTSL/TCB/CRTM have no records yet — the join is simply empty there and
# self-heals as TML registers fleets. See PK/gtfs-feed-quirks.md "GO Hub".
GOHUB_VMETA_URL = 'https://go.tmlmobilidade.pt/hub/api/v1/realtime/vehicles/metadata'
VMETA_REFRESH_S = 600


def _gohub_meta_compact(rec):
    """Map a GO Hub metadata record to the compact vmeta keys the popup
    endpoint serves (same shapes as the CM JSON path: booleans for wc/bk,
    strings for the rest). 'owner' is the operating company's display name
    ("Martín SA") — same semantics as CM's 'ow'."""
    meta = {}
    for src, short in (('wheelchair', 'wc'), ('bicycles', 'bk'),
                       ('propulsion', 'pr'), ('make', 'mk'),
                       ('model', 'md'), ('license_plate', 'lp'),
                       ('owner', 'ow')):
        val = rec.get(src)
        if val not in (None, ''):
            meta[short] = val
    return meta


def build_gohub_vmeta_map(records, agency_ids):
    """{rt_vehicle_id: compact_meta} for one feed from the combined registry.

    Registry vehicle_ids are '<gtfs agency id>-<fleet id>' ("21-1002",
    "16-C001"); the RT feed's ids (after our GO-prefix strip) are the bare
    fleet id, so the join key drops everything up to the first dash.
    """
    vmap = {}
    for rec in records or []:
        if rec.get('agency_id') not in agency_ids:
            continue
        vid = rec.get('vehicle_id') or ''
        if '-' in vid:
            vid = vid.split('-', 1)[1]
        meta = _gohub_meta_compact(rec)
        if vid and meta:
            vmap[vid] = meta
    return vmap


# Every combined-feed source reads the same registry — derived, not duplicated.
RT_VEHICLE_META_URL = {slug: GOHUB_VMETA_URL for slug in RT_VEHICLE_PREFIX}


# GTFS-RT timestamps are POSIX seconds, but GO Hub emits milliseconds. Read as
# seconds, a ms value lands in the year 58k: it passes every freshness cutoff
# forever (ghosts never expire), history rows get absurd times and the RT health
# endpoint's freshest_age goes negative. 10**12 seconds is the year 33658, so
# the magnitude alone separates the two for any real feed.
_MS_TIMESTAMP_MIN = 10 ** 12


def _rt_timestamp(raw):
    """Normalize a feed timestamp to POSIX seconds, falling back to receive time.

    The fallback matters on its own: protobuf's default 0 for a missing
    timestamp would read as infinitely stale and silently blank the feed.
    """
    ts = int(raw or 0)
    if ts > _MS_TIMESTAMP_MIN:
        return ts // 1000
    return ts or int(time.time())


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

        # Per-slug {rt_vehicle_id: compact_meta} from the combined registry
        self._vmeta_maps: dict[str, dict] = {}
        await self._refresh_vehicle_meta(sources, timeout)

        while True:
            now_m = time.monotonic()

            # Refresh route cache + re-read source configs every 10 min
            if route_cache.is_stale(600):
                sources = await self._load_sources(slugs)
                ds_ids = [ds.id for ds in sources] if slugs else None
                await route_cache.refresh(redis_conn=redis_pub, data_source_ids=ds_ids)
                await self._refresh_vehicle_meta(sources, timeout)

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

    async def _refresh_vehicle_meta(self, sources, timeout):
        """Refresh the per-slug static-metadata join maps (10-min cadence).

        A fetch failure keeps the previous map — registry data barely changes,
        so serving a stale join beats blanking every popup for the cycle.
        """
        wanted = {}
        for ds in sources:
            url = RT_VEHICLE_META_URL.get(ds.slug)
            if url:
                wanted.setdefault(url, []).append(ds)
        if not wanted:
            return

        async with aiohttp.ClientSession(timeout=timeout) as session:
            for url, url_sources in wanted.items():
                try:
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        payload = await resp.json()
                except Exception as e:
                    logger.warning(f'Vehicle metadata fetch failed ({url}): {e}')
                    continue
                records = payload.get('data') if isinstance(payload, dict) else payload
                for ds in url_sources:
                    agency_ids = {p.strip('[]') for p in RT_VEHICLE_PREFIX.get(ds.slug, ())}
                    self._vmeta_maps[ds.slug] = build_gohub_vmeta_map(records, agency_ids)
                logger.info(
                    'Vehicle metadata refreshed: '
                    + ', '.join(f'{ds.slug}={len(self._vmeta_maps.get(ds.slug, {}))}'
                                for ds in url_sources)
                )

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
                # Keep the in-memory copy in step with the row: the clear-on-success
                # branch below tests `ds.last_error`, and `sources` is only re-read
                # every 10 min — leaving it stale kept the DB flag set for up to that
                # long after recovery, so anything reading it (feed-health sampler,
                # RT health endpoint) reported an outage that had already ended.
                ds.last_error = str(result)[:500]
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

            # Strip static metadata off every vehicle dict BEFORE it reaches the
            # transit:rt mirror / vdata / WS, keeping the display payload compact.
            # Kept aside per vehicle_id and served on demand by the meta endpoint.
            vmeta = {}
            for v in vehicles:
                m = v.pop('_meta', None)
                if m is not None:
                    vmeta[v['v']] = m

            # Mark as polled
            last_poll[str(ds.id)] = time.monotonic()

            # Clear last_error on success
            if ds.last_error:
                ds.last_error = ''
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
                m = vmeta.get(v['v'])
                if m:
                    # 300s > the 180s display cutoff, so any shown (fresh) vehicle
                    # always has live meta; the key self-expires, no cleanup pass.
                    pipe.set(f'transit:vmeta:{member}', orjson.dumps(m), ex=300)
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

            veh = {
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
                't': _rt_timestamp(v.get('timestamp')),
                'tid': v.get('trip_id', ''),
                'sid': stop_id,
                'd': direction_id,
                'hs': headsign,
                'ps': place_slug,
                'rs': route_slug,
            }
            # Static per-vehicle metadata for the live popup (accessibility,
            # propulsion, make/model, plate, operator). Pulled aside under a
            # private key at ingest; never rides the compact vdata/WS payload,
            # served on demand by the vehicle-meta endpoint.
            meta = {}
            for src, short in (('wheelchair_accessible', 'wc'), ('bikes_allowed', 'bk'),
                               ('propulsion', 'pr'), ('make', 'mk'), ('model', 'md'),
                               ('license_plate', 'lp'), ('owner', 'ow')):
                mv = v.get(src)
                if mv not in (None, ''):
                    meta[short] = mv
            if meta:
                veh['_meta'] = meta
            vehicles.append(veh)
        return vehicles

    def _parse_protobuf(self, data, ds, route_cache, snapper):
        """Standard GTFS-RT FeedMessage protobuf."""
        from google.transit import gtfs_realtime_pb2

        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(data)

        prefixes = RT_VEHICLE_PREFIX.get(ds.slug, ())
        meta_map = getattr(self, '_vmeta_maps', {}).get(ds.slug, {})

        vehicles = []
        for entity in feed.entity:
            vp = entity.vehicle
            vehicle_id = vp.vehicle.id or entity.id
            # Combined multi-operator feed: drop foreign operators before any
            # snapping work, then carry this source's bare vehicle id onward.
            if prefixes:
                match = next((p for p in prefixes if vehicle_id.startswith(p)), None)
                if match is None:
                    continue
                vehicle_id = vehicle_id[len(match):]
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

            veh = {
                'v': vehicle_id,
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
                't': _rt_timestamp(vp.timestamp),
                'tid': vp.trip.trip_id,
                'sid': stop_id,
                'd': direction_id,
                'hs': headsign,
                'ps': place_slug,
                'rs': route_slug,
            }
            # Registry-joined static metadata rides the same '_meta' side
            # channel as the CM JSON path — stripped off in _poll_sources
            # into transit:vmeta:* for the popup endpoint.
            meta = meta_map.get(vehicle_id)
            if meta:
                veh['_meta'] = meta
            vehicles.append(veh)
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
