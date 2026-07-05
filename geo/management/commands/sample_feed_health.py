"""Sample GTFS-RT feed liveness into FeedHealthSample — durable downtime evidence.

Runs as a persistent service (`parahub-feed-health.service`, `--interval 60`),
one row per active GPS feed per tick. Records the failure CATEGORY at write-time
so `report_feed_health` can split downtime by cause for an operator complaint:

  unreachable — the daemon's fetch failed (ds.last_error set): server down / TLS /
                timeout / HTTP error. The operator's *availability* fault.
  stale       — the feed answers HTTP 200 but is serving frozen data (vehicles in
                the mirror, none fresh, freshest fix > RT_STALE_SECS old). The
                operator's *data-quality* fault (e.g. STCP froze 4h+ on 2026-06-28).
  idle        — feed returns no vehicles (off-service / deep night) — NOT a fault.
  ok          — serving live data.

NOTE: this logs RAW truth (no deep-night guard — that guard only suppresses Kuma
*alerting*; the evidence log records staleness whenever it occurs and lets the
report decide what to count). See PK/transit-system.md § Feed health log.
"""
import json
import time as _time

import redis
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.utils import timezone

from geo.models import TransitDataSource, FeedHealthSample

# Keep in sync with parahub.api.RT_STALE_SECS (the Kuma freeze threshold)
RT_STALE_SECS = 600


class Command(BaseCommand):
    help = "Sample GTFS-RT feed liveness into FeedHealthSample (downtime evidence)."

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Single sample then exit')
        parser.add_argument('--interval', type=int, default=60, help='Seconds between samples')

    def handle(self, *args, **opts):
        r = redis.Redis(host='localhost', port=6379, db=0)
        interval = opts['interval']
        while True:
            try:
                n = self._sample(r)
                if opts['once']:
                    self.stdout.write(self.style.SUCCESS(f'sampled {n} feeds'))
            except Exception as exc:  # never let one bad tick kill the daemon
                self.stderr.write(f'sample tick failed: {exc!r}')
            if opts['once']:
                break
            _time.sleep(interval)

    def _sample(self, r):
        now = int(_time.time())
        ts = timezone.now()
        feeds = (TransitDataSource.objects
                 .filter(is_active=True, rt_kind='gps')
                 .exclude(rt_vehicles_url=''))
        rows = []
        for ds in feeds:
            try:
                fresh = r.scard(f'transit:members:{ds.id}')
            except Exception:
                fresh = 0

            mirror = []
            try:
                raw = cache.get(f'transit:rt:{ds.id}')
                if raw:
                    mirror = json.loads(raw) if isinstance(raw, (bytes, bytearray, str)) else raw
            except Exception:
                mirror = []
            total = len(mirror) if mirror else 0

            freshest_age = None
            detail = ''
            if ds.last_error:
                status = FeedHealthSample.Status.UNREACHABLE
                detail = ds.last_error[:300]
            elif fresh > 0:
                status = FeedHealthSample.Status.OK
                freshest_age = 0
            elif total == 0:
                status = FeedHealthSample.Status.IDLE
            else:
                maxt = max((v.get('t', 0) for v in mirror), default=now)
                freshest_age = max(0, now - maxt)  # clamp clock skew
                status = (FeedHealthSample.Status.STALE
                          if freshest_age > RT_STALE_SECS
                          else FeedHealthSample.Status.OK)

            rows.append(FeedHealthSample(
                time=ts, data_source=ds, status=status,
                fresh_count=fresh, total_served=total,
                freshest_age_s=freshest_age, detail=detail,
            ))

        if rows:
            FeedHealthSample.objects.bulk_create(rows)
        return len(rows)
