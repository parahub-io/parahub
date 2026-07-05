"""Backfill blank trip_headsign values with each trip's terminus (last stop).

One-off / re-runnable companion to the same step inside `import_gtfs` (which runs
it automatically after every stop_times import). Use this to fix data already in
the DB without a full re-import — e.g. after deploying the feature on feeds that
ship empty headsigns feed-wide (Carris Lisboa). See
`backfill_empty_headsigns` for the rationale.
"""
from django.core.management.base import BaseCommand

from geo.models import Agency
from geo.management.commands.import_gtfs import backfill_empty_headsigns


class Command(BaseCommand):
    help = "Fill blank Trip.headsign with the trip terminus (last stop)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-source",
            help="Limit to one feed by TransitDataSource slug (default: all feeds).",
        )

    def handle(self, *args, **options):
        agency_ids = None
        slug = options.get("data_source")
        if slug:
            agency_ids = list(
                Agency.objects.filter(data_source__slug=slug).values_list("id", flat=True)
            )
            if not agency_ids:
                self.stderr.write(self.style.ERROR(f"No agencies for data source '{slug}'"))
                return

        n = backfill_empty_headsigns(agency_ids)
        self.stdout.write(self.style.SUCCESS(f"Backfilled {n} blank trip headsigns from terminus"))
