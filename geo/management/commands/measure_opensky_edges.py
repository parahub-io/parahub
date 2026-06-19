"""
Measure-only ORB pose-edge refresh — see PK/opensky-system.md § Pose Graph
Architecture.

Re-measures ORB_PAIR edges for published missions against the CURRENT on-disk
orthos and upserts them into the pose graph. No consensus math, no warps, no
retiling — unlike `realign_opensky_consensus`, which applies shifts as a side
effect (caused the 2026-06-09 consolidation spill).

This is the standard precursor to a Phase-2 solve: edges measured before an
endpoint's `georef_changed_at` are stale (describe a frame that no longer
exists on disk) and `realign_opensky_similarity` refuses to use them.

Usage:
  python manage.py measure_opensky_edges --all
  python manage.py measure_opensky_edges --missions=ULID1,ULID2,...

Takes the OpenSky tile lock for the duration (serializes vs the processor /
consolidations so orthos aren't read mid-rewrite). ~10-60s per mission.
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger('opensky')


class Command(BaseCommand):
    help = 'Re-measure ORB pose edges against current orthos (measure-only, no warps/retiles)'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true', help='All published, non-superseded missions')
        parser.add_argument('--missions', type=str, help='Comma-separated mission ULIDs')

    def handle(self, *args, **options):
        from geo.models import OpenSkyMission
        from geo.opensky_processor import measure_orb_edges_skystore, opensky_tile_lock

        base = OpenSkyMission.objects.filter(
            status=OpenSkyMission.Status.PUBLISHED,
            is_consolidation=False,
            superseded_by__isnull=True,
        )
        if options['missions']:
            ids = [s.strip() for s in options['missions'].split(',') if s.strip()]
            missions = list(base.filter(id__in=ids).order_by('id'))
        elif options['all']:
            missions = list(base.order_by('id'))
        else:
            self.stderr.write(self.style.ERROR("Provide --all or --missions=..."))
            return

        if not missions:
            self.stderr.write(self.style.ERROR("No matching published missions"))
            return

        self.stdout.write(f"Measuring ORB edges for {len(missions)} mission(s)...")
        total_edges = failed = 0
        with opensky_tile_lock(blocking=True):
            for i, m in enumerate(missions, 1):
                try:
                    edges = measure_orb_edges_skystore(m.id)
                    total_edges += len(edges)
                    self.stdout.write(f"  [{i}/{len(missions)}] {m.id[:12]}: {len(edges)} edge(s)")
                except Exception as e:
                    failed += 1
                    self.stderr.write(self.style.ERROR(f"  [{i}/{len(missions)}] {m.id[:12]} FAILED: {e}"))
                    logger.error(f"Edge measurement failed for {m.id}: {e}", exc_info=True)

        style = self.style.SUCCESS if not failed else self.style.WARNING
        self.stdout.write(style(
            f"Done: {total_edges} edges upserted across {len(missions) - failed} missions"
            + (f", {failed} failed" if failed else "")))
