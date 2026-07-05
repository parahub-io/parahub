"""Report GTFS-RT feed downtime from FeedHealthSample — complaint evidence.

Splits downtime by CAUSE (the distinct operator faults a reclamação must
separate) over a window, with outage windows, per-cause totals, and an
hour-of-day breakdown. Times shown in the feed's agency-local timezone.

    python3 manage.py report_feed_health --feed stcp-porto --since 2026-06-14
    python3 manage.py report_feed_health --feed stcp-porto --since 2026-06-14 --csv > stcp.csv

Default window: last 14 days. No --feed → every active GPS feed. See
PK/complaints-workflow.md and PK/transit-system.md § Feed health log.
"""
from datetime import datetime, timedelta, timezone as dt_tz
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from geo.models import TransitDataSource, Agency, FeedHealthSample

FAULTS = ('unreachable', 'stale')
CAUSE_LABEL = {
    'unreachable': 'SERVER UNREACHABLE (fetch failed)',
    'stale': 'STALE DATA (HTTP 200, frozen feed)',
}
NOMINAL_INTERVAL = 60  # sampler tick; a single fault sample ≈ this much outage


class Command(BaseCommand):
    help = "Report GTFS-RT feed downtime by cause (complaint evidence)."

    def add_arguments(self, parser):
        parser.add_argument('--feed', help='Feed slug (default: all active GPS feeds)')
        parser.add_argument('--since', help='YYYY-MM-DD (default: 14 days ago)')
        parser.add_argument('--until', help='YYYY-MM-DD (default: now)')
        parser.add_argument('--gap', type=int, default=180,
                            help='Seconds tolerated between fault samples before splitting an outage')
        parser.add_argument('--csv', action='store_true', help='CSV of outage windows (for the annex)')

    def handle(self, *args, **opts):
        since = self._parse(opts['since']) if opts['since'] else timezone.now() - timedelta(days=14)
        until = self._parse(opts['until']) if opts['until'] else timezone.now()

        feeds = TransitDataSource.objects.filter(is_active=True, rt_kind='gps').exclude(rt_vehicles_url='')
        if opts['feed']:
            feeds = feeds.filter(slug=opts['feed'])
            if not feeds:
                raise CommandError(f"no active GPS feed with slug '{opts['feed']}'")

        if opts['csv']:
            self.stdout.write('feed,cause,start,end,duration_min,max_stale_min,samples')

        for ds in feeds:
            tzname = self._agency_tz(ds)
            tz = ZoneInfo(tzname)
            samples = list(FeedHealthSample.objects
                           .filter(data_source=ds, time__gte=since, time__lte=until)
                           .order_by('time')
                           .values_list('time', 'status', 'freshest_age_s'))
            runs = self._group(samples, opts['gap'])

            if opts['csv']:
                for run in runs:
                    self.stdout.write(','.join([
                        ds.slug, run['cause'],
                        run['start'].astimezone(tz).strftime('%Y-%m-%d %H:%M'),
                        run['end'].astimezone(tz).strftime('%Y-%m-%d %H:%M'),
                        f"{run['dur_s'] / 60:.1f}",
                        f"{run['max_age'] / 60:.1f}" if run['cause'] == 'stale' else '',
                        str(run['n']),
                    ]))
                continue

            self._print_human(ds, tzname, tz, since, until, samples, runs)

    # ------------------------------------------------------------------ helpers

    def _parse(self, s):
        try:
            return datetime.strptime(s, '%Y-%m-%d').replace(tzinfo=dt_tz.utc)
        except ValueError:
            raise CommandError(f"bad date '{s}', use YYYY-MM-DD")

    def _agency_tz(self, ds):
        ag = Agency.objects.filter(data_source=ds).exclude(timezone='').first()
        return ag.timezone if (ag and ag.timezone) else 'UTC'

    def _group(self, samples, gap):
        """Contiguous fault runs of the same cause; gap-tolerant (bridges missed ticks)."""
        runs, cur = [], None
        for t, status, age in samples:
            if status in FAULTS:
                if cur and cur['cause'] == status and (t - cur['end']).total_seconds() <= gap:
                    cur['end'] = t
                    cur['n'] += 1
                    cur['max_age'] = max(cur['max_age'], age or 0)
                else:
                    if cur:
                        runs.append(cur)
                    cur = {'cause': status, 'start': t, 'end': t, 'n': 1, 'max_age': age or 0}
            elif cur:
                runs.append(cur)
                cur = None
        if cur:
            runs.append(cur)
        for run in runs:
            # outage spans from first fault sample to one tick past the last
            run['dur_s'] = (run['end'] - run['start']).total_seconds() + NOMINAL_INTERVAL
        return runs

    def _print_human(self, ds, tzname, tz, since, until, samples, runs):
        w = self.stdout.write
        w('')
        w(self.style.MIGRATE_HEADING(f'═══ {ds.name}  ({ds.slug})'))
        w(f'  window:   {since.astimezone(tz):%Y-%m-%d %H:%M} → {until.astimezone(tz):%Y-%m-%d %H:%M}  ({tzname})')
        if not samples:
            w(self.style.WARNING('  no samples in window (sampler not running yet, or feed added later)'))
            return

        counts = {}
        for _t, status, _a in samples:
            counts[status] = counts.get(status, 0) + 1
        tot = len(samples)
        w(f'  samples:  {tot}  (' + ', '.join(f'{k}={v} {v*100//tot}%' for k, v in sorted(counts.items())) + ')')

        if not runs:
            w(self.style.SUCCESS('  no faults recorded ✓'))
            return

        # totals by cause
        w('')
        w('  Downtime by cause:')
        for cause in FAULTS:
            c_runs = [r for r in runs if r['cause'] == cause]
            if not c_runs:
                continue
            secs = sum(r['dur_s'] for r in c_runs)
            w(f"    {CAUSE_LABEL[cause]:42}  {secs/3600:5.1f} h   in {len(c_runs)} outage(s)")

        # outage windows
        w('')
        w('  Outage windows:')
        for r in runs:
            extra = f"  (max stale {r['max_age']/60:.0f} min)" if r['cause'] == 'stale' else ''
            w(f"    {r['start'].astimezone(tz):%Y-%m-%d %H:%M}–{r['end'].astimezone(tz):%H:%M}  "
              f"{r['dur_s']/60:6.1f} min  {r['cause']:<11}{extra}")

        # hour-of-day distribution of fault minutes (agency-local)
        by_hour = {}
        for r in runs:
            t = r['start']
            remaining = r['dur_s']
            while remaining > 0:
                h = t.astimezone(tz).hour
                chunk = min(remaining, 3600 - (t.astimezone(tz).minute * 60 + t.astimezone(tz).second))
                by_hour[h] = by_hour.get(h, 0) + chunk
                t = t + timedelta(seconds=chunk)
                remaining -= chunk
        if by_hour:
            w('')
            w('  Fault minutes by hour-of-day (agency-local):')
            peak = max(by_hour.values())
            for h in range(24):
                m = by_hour.get(h, 0) / 60
                if m <= 0:
                    continue
                bar = '█' * max(1, int(20 * (by_hour[h] / peak)))
                w(f'    {h:02d}:00  {m:6.1f} min  {bar}')
