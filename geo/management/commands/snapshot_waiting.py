"""Sample waiting-passenger markers into WaitingSnapshot — municipal history.

Runs as a persistent service (`parahub-waiting-snapshot.service`, `--interval 60`),
one row per occupied (data source, route, direction, stop) per tick and nothing at
all for an empty minute.

Live marker counts are ephemeral by design; the thing a city or a small operator
can act on is the accumulated shape — which poles hold people, on which line, at
which hour. That is not backfillable, so it is recorded from the day the feature
exists. See PK/transit-system.md § Waiting-passenger markers.
"""
import time as _time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from geo.models import TransitDataSource, WaitingSnapshot
from parahub.services.transit_waiting import WaitingService


class Command(BaseCommand):
    help = "Sample waiting-passenger markers into WaitingSnapshot (municipal history)."

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Single sample then exit')
        parser.add_argument('--interval', type=int, default=60, help='Seconds between samples')

    def handle(self, *args, **opts):
        interval = opts['interval']
        while True:
            try:
                # No request cycle ever runs in this process, so nothing else
                # retires a connection Postgres has dropped — without this one
                # restart of Postgres would leave every later tick failing on a
                # dead handle (same pattern as parahub/background.py).
                close_old_connections()
                n = self._sample()
                if opts['once']:
                    self.stdout.write(self.style.SUCCESS(f'sampled {n} occupied stop(s)'))
            except Exception as exc:  # never let one bad tick kill the daemon
                self.stderr.write(f'snapshot tick failed: {exc!r}')
            if opts['once']:
                break
            _time.sleep(interval)

    def _sample(self):
        rows = WaitingService.iter_occupied()
        if not rows:
            return 0

        # Redis holds the data-source id as an opaque string; a feed deleted
        # while somebody stood at its stop would otherwise break the FK.
        known = set(TransitDataSource.objects.values_list('id', flat=True))
        now = timezone.now()
        snapshots = [
            WaitingSnapshot(
                time=now,
                data_source_id=ds_id,
                route_source_id=route_source_id,
                direction_id=direction,
                stop_source_id=stop_source_id,
                waiting=total,
                active=active,
            )
            for ds_id, route_source_id, direction, stop_source_id, total, active in rows
            if ds_id in known
        ]
        if snapshots:
            WaitingSnapshot.objects.bulk_create(snapshots)
        return len(snapshots)
