"""
Re-align OpenSky missions using multi-neighbor consensus (Phase 1 of pose graph
architecture — see PK/opensky-system.md).

For each mission: measures ORB shift vs EVERY overlapping neighbor, writes
ORB_PAIR pose edges, applies weighted-average shift. Iterates until all
missions are stable (max per-iteration shift below threshold).
"""
import logging

from django.core.management.base import BaseCommand

from geo.models import OpenSkyMission
from geo.opensky_processor import (
    SKYSTORE_OPENSKY, _skystore_ssh,
    apply_consensus_alignment_skystore,
)

logger = logging.getLogger('opensky')


class Command(BaseCommand):
    help = 'Multi-neighbor consensus re-alignment (iterates until stable or --iterations reached)'

    def add_arguments(self, parser):
        parser.add_argument('--mission', type=str, help='Specific mission ID to realign (single pass, no iteration)')
        parser.add_argument('--iterations', type=int, default=5, help='Max iterations over all missions (default 5)')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done (no apply)')

    def handle(self, *args, **options):
        missions = OpenSkyMission.objects.filter(status=OpenSkyMission.Status.PUBLISHED)
        if options['mission']:
            missions = missions.filter(id=options['mission'])

        if not missions.exists():
            self.stdout.write('No published missions found.')
            return

        max_iterations = options['iterations'] if not options['mission'] else 1

        for iteration in range(1, max_iterations + 1):
            self.stdout.write(f"\n=== Iteration {iteration}/{max_iterations} ===")
            applied_count = 0
            skipped_count = 0

            for mission in missions.order_by('created_at'):
                r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission.id}.tif"

                try:
                    result = _skystore_ssh(f"test -f {r_ortho} && echo ok")
                    if "ok" not in result.stdout:
                        self.stdout.write(self.style.WARNING(
                            f"SKIP {mission.id} ({mission.name}) — no orthophoto on skystore"
                        ))
                        continue
                except Exception:
                    self.stdout.write(self.style.WARNING(
                        f"SKIP {mission.id} ({mission.name}) — skystore unreachable"
                    ))
                    continue

                self.stdout.write(f"Consensus aligning {mission.id} ({mission.name})...")

                if options['dry_run']:
                    continue

                try:
                    applied = apply_consensus_alignment_skystore(mission.id)
                    if applied:
                        self.stdout.write(self.style.SUCCESS(f"  APPLIED + retiled"))
                        applied_count += 1
                    else:
                        self.stdout.write(f"  stable (no shift applied)")
                        skipped_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  FAILED: {e}"))
                    logger.error(f"Consensus realign failed for {mission.id}: {e}", exc_info=True)

            self.stdout.write(
                f"Iteration {iteration} done: applied={applied_count}, stable={skipped_count}"
            )

            if applied_count == 0:
                self.stdout.write(self.style.SUCCESS(
                    f"\nConverged at iteration {iteration} — all missions stable."
                ))
                return

        self.stdout.write(self.style.WARNING(
            f"\nReached max iterations ({max_iterations}) without full convergence."
        ))
