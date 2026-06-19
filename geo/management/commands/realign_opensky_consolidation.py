"""
Realign a published consolidation onto its members' frame — recovery path for
a mis-anchored super-tile (see PK/opensky-system.md § Split-Merge Consolidation).

Members render the SAME photos over the same cells, so member↔consolidation
ORB is same-content matching — the strongest possible reference, immune to the
weak-satellite-lock failure that left the church super-tile 33m off
(2026-06-12). Applies a translation shift to the saved merged ortho, then
reclips to the member-union rectangle and retiles.

Usage:
  python manage.py realign_opensky_consolidation <consolidation_ulid> [--dry-run]

Run apply as a transient systemd unit (retile is ~20-40 min).
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Shift a consolidation onto its members' frame (recovery for mis-anchored super-tiles)"

    def add_arguments(self, parser):
        parser.add_argument('consolidation_id', type=str)
        parser.add_argument('--dry-run', action='store_true', help='Measure + report; apply nothing')

    def handle(self, *args, **options):
        from geo.opensky_processor import realign_consolidation_to_members, opensky_tile_lock

        cid = options['consolidation_id'].strip()
        if options['dry_run']:
            applied = realign_consolidation_to_members(cid, dry_run=True)
        else:
            with opensky_tile_lock(blocking=True):
                applied = realign_consolidation_to_members(cid)
        if applied:
            self.stdout.write(self.style.SUCCESS(f"Realigned + retiled {cid}"))
        else:
            self.stdout.write("Nothing applied (see opensky log for the measurement)")
