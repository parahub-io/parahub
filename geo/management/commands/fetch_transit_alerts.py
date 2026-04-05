"""
Daemon: fetch GTFS-RT ServiceAlerts, store in Redis for relay endpoints.

Alerts change infrequently — default poll every 5 minutes.

Usage:
    python3 manage.py fetch_transit_alerts              # Run continuously (300s interval)
    python3 manage.py fetch_transit_alerts --once        # Single poll (testing)
    python3 manage.py fetch_transit_alerts --interval 60 # Custom interval
"""

import asyncio
import json
import logging
import time

import aiohttp
import redis.asyncio as aioredis
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from geo.models import TransitDataSource

logger = logging.getLogger(__name__)

# GTFS-RT cause/effect enums → human-readable
CAUSE_MAP = {
    1: 'UNKNOWN_CAUSE', 2: 'OTHER_CAUSE', 3: 'TECHNICAL_PROBLEM',
    4: 'STRIKE', 5: 'DEMONSTRATION', 6: 'ACCIDENT', 7: 'HOLIDAY',
    8: 'WEATHER', 9: 'MAINTENANCE', 10: 'CONSTRUCTION', 11: 'POLICE_ACTIVITY',
    12: 'MEDICAL_EMERGENCY',
}

EFFECT_MAP = {
    1: 'NO_SERVICE', 2: 'REDUCED_SERVICE', 3: 'SIGNIFICANT_DELAYS',
    4: 'DETOUR', 5: 'ADDITIONAL_SERVICE', 6: 'MODIFIED_SERVICE',
    7: 'OTHER_EFFECT', 8: 'UNKNOWN_EFFECT', 9: 'STOP_MOVED',
    10: 'NO_EFFECT', 11: 'ACCESSIBILITY_ISSUE',
}

SEVERITY_MAP = {
    1: 'UNKNOWN', 2: 'INFO', 3: 'WARNING', 4: 'SEVERE',
}

# Redis TTL: 15 minutes (3x poll interval — stale data auto-expires)
REDIS_TTL = 900


def _extract_translated(translated_string, preferred_langs=('en', 'pt', '')):
    """Extract best translation from GTFS-RT TranslatedString."""
    if not translated_string or not translated_string.translation:
        return ''
    by_lang = {t.language: t.text for t in translated_string.translation}
    for lang in preferred_langs:
        if lang in by_lang:
            return by_lang[lang]
    # Fallback: first available
    return translated_string.translation[0].text


class Command(BaseCommand):
    help = 'Daemon: fetch GTFS-RT ServiceAlerts and store in Redis'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=int, default=300, help='Poll interval in seconds (default: 300)')
        parser.add_argument('--once', action='store_true', help='Single poll (for testing)')

    def handle(self, **options):
        asyncio.run(self._run(options))

    async def _run(self, options):
        interval = options['interval']
        self.stdout.write(f'Starting ServiceAlerts fetcher (interval={interval}s)')

        r = aioredis.Redis(
            host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
            port=getattr(settings, 'REDIS_PORT', 6379),
        )

        timeout = aiohttp.ClientTimeout(total=15)

        while True:
            t0 = time.monotonic()

            try:
                sources = await sync_to_async(
                    lambda: list(TransitDataSource.objects.filter(is_active=True)
                                 .exclude(rt_alerts_url=''))
                )()

                if not sources:
                    self.stdout.write('No active alert sources')
                    if options['once']:
                        break
                    await asyncio.sleep(interval)
                    continue

                async with aiohttp.ClientSession(timeout=timeout) as session:
                    tasks = [self._fetch_one(session, ds) for ds in sources]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                total_alerts = 0
                for ds, result in zip(sources, results):
                    ds_id = str(ds.id)
                    slug = ds.slug or ds_id
                    if isinstance(result, Exception):
                        logger.error(f'Alerts fetch failed for {ds.name}: {result}')
                        continue

                    raw_pb, alerts_json = result
                    total_alerts += len(alerts_json)

                    pipe = r.pipeline(transaction=False)

                    # Store raw protobuf for relay endpoint
                    if raw_pb:
                        pipe.setex(f'transit:alerts:pb:{ds_id}', REDIS_TTL, raw_pb)
                    else:
                        pipe.delete(f'transit:alerts:pb:{ds_id}')

                    # Store parsed JSON for our own API
                    if alerts_json:
                        pipe.setex(f'transit:alerts:{ds_id}', REDIS_TTL, json.dumps(alerts_json))
                    else:
                        pipe.delete(f'transit:alerts:{ds_id}')

                    # Per-source heartbeat for monitor.sh staleness check
                    pipe.set(f'transit:alerts_ok:{slug}', str(int(time.time())))

                    await pipe.execute()

                elapsed = (time.monotonic() - t0) * 1000
                logger.info(f'Alerts poll: {total_alerts} alerts from {len(sources)} sources in {elapsed:.0f}ms')

                # Global heartbeat
                await r.set('transit_alerts:flush_ok', str(int(time.time())))

            except Exception:
                logger.exception('Alerts poll cycle failed')
                # Reset stale DB connection so next cycle can reconnect
                connection.close()

            if options['once']:
                break
            await asyncio.sleep(interval)

        await r.aclose()

    async def _fetch_one(self, session, ds):
        """Fetch alerts from a single data source. Returns (raw_protobuf_bytes, parsed_alerts_list)."""
        urls = [u.strip() for u in ds.rt_alerts_url.strip().splitlines() if u.strip()]
        headers = ds.rt_headers or {}

        # Most feeds have a single URL
        all_raw = b''
        all_alerts = []

        for url in urls:
            async with session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get('Content-Type', '')
                data = await resp.read()

                if 'json' in content_type:
                    alerts = self._parse_json(data)
                else:
                    alerts = self._parse_protobuf(data)
                    if not all_raw:
                        all_raw = data  # Keep first protobuf for relay

                all_alerts.extend(alerts)

        return (all_raw, all_alerts)

    def _parse_protobuf(self, data):
        """Parse GTFS-RT FeedMessage, extract ServiceAlert entities."""
        from google.transit import gtfs_realtime_pb2

        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(data)

        alerts = []
        for entity in feed.entity:
            if not entity.HasField('alert'):
                continue
            alert = entity.alert
            alerts.append(self._alert_to_dict(entity.id, alert))
        return alerts

    def _parse_json(self, data):
        """Parse JSON alerts (operator-specific formats)."""
        parsed = json.loads(data)

        # Handle GTFS-RT JSON format (entity wrapper)
        if isinstance(parsed, dict) and 'entity' in parsed:
            alerts = []
            for entity in parsed['entity']:
                if 'alert' in entity:
                    a = entity['alert']
                    alerts.append({
                        'id': entity.get('id', ''),
                        'header': self._json_translated(a.get('headerText', a.get('header_text'))),
                        'description': self._json_translated(a.get('descriptionText', a.get('description_text'))),
                        'url': self._json_translated(a.get('url')),
                        'cause': a.get('cause', ''),
                        'effect': a.get('effect', ''),
                        'severity': a.get('severityLevel', a.get('severity_level', '')),
                        'active_periods': [
                            {'start': p.get('start', 0), 'end': p.get('end', 0)}
                            for p in a.get('activePeriod', a.get('active_period', []))
                        ],
                        'informed_entities': [
                            {k: v for k, v in ie.items() if v}
                            for ie in a.get('informedEntity', a.get('informed_entity', []))
                        ],
                    })
            return alerts

        return []

    def _alert_to_dict(self, entity_id, alert):
        """Convert protobuf Alert to dict."""
        return {
            'id': entity_id,
            'header': _extract_translated(alert.header_text),
            'description': _extract_translated(alert.description_text),
            'url': _extract_translated(alert.url),
            'cause': CAUSE_MAP.get(alert.cause, str(alert.cause)),
            'effect': EFFECT_MAP.get(alert.effect, str(alert.effect)),
            'severity': SEVERITY_MAP.get(alert.severity_level, ''),
            'active_periods': [
                {'start': p.start, 'end': p.end}
                for p in alert.active_period
            ],
            'informed_entities': [
                {
                    **({"agency_id": ie.agency_id} if ie.agency_id else {}),
                    **({"route_id": ie.route_id} if ie.route_id else {}),
                    **({"route_type": ie.route_type} if ie.route_type else {}),
                    **({"stop_id": ie.stop_id} if ie.stop_id else {}),
                    **({"trip_id": ie.trip.trip_id} if ie.HasField('trip') and ie.trip.trip_id else {}),
                    **({"direction_id": ie.trip.direction_id} if ie.HasField('trip') and ie.trip.direction_id else {}),
                }
                for ie in alert.informed_entity
            ],
        }

    def _json_translated(self, field):
        """Extract text from JSON translated string."""
        if not field:
            return ''
        if isinstance(field, str):
            return field
        translations = field.get('translation', [])
        if not translations:
            return ''
        for t in translations:
            if t.get('language', '') in ('en', 'pt', ''):
                return t.get('text', '')
        return translations[0].get('text', '')
