"""
Re-align OpenSky missions using satellite imagery on skystore.

Runs ECC-based satellite alignment via SSH on skystore.
Corrects consumer GPS offset (typically 1-5m).
"""
import logging

from django.core.management.base import BaseCommand

from geo.models import OpenSkyMission
from geo.opensky_processor import (
    SKYSTORE_OPENSKY, _skystore_ssh,
    check_satellite_alignment_skystore,
    apply_satellite_alignment_skystore,
)

logger = logging.getLogger('opensky')


class Command(BaseCommand):
    help = 'Re-align OpenSky missions using satellite imagery (runs on skystore via SSH)'

    def add_arguments(self, parser):
        parser.add_argument('--mission', type=str, help='Specific mission ID to realign')
        parser.add_argument('--dry-run', action='store_true', help='Show offsets without applying')
        parser.add_argument('--force', action='store_true', help='Apply even if offset < 0.5m')

    def handle(self, *args, **options):
        missions = OpenSkyMission.objects.filter(status=OpenSkyMission.Status.PUBLISHED)
        if options['mission']:
            missions = missions.filter(id=options['mission'])

        if not missions.exists():
            self.stdout.write('No published missions found.')
            return

        for mission in missions.order_by('published_at'):
            r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission.id}.tif"

            # Verify ortho exists on skystore
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

            self.stdout.write(f"\nAnalyzing {mission.id} ({mission.name})...")

            try:
                result = check_satellite_alignment_skystore(mission.id)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Check failed: {e}"))
                continue

            offset = result['offset']
            dx = result['dx']
            dy = result['dy']

            if not result['needs_correction'] and not options['force']:
                self.stdout.write(self.style.SUCCESS(
                    f"  OK — already well-aligned (offset {offset:.2f}m < 0.5m)"
                ))
                continue

            self.stdout.write(
                f"  Detected offset: dx={dx:.2f}m, dy={dy:.2f}m (total={offset:.2f}m)"
            )

            if options['dry_run']:
                continue

            self.stdout.write("  Applying alignment + retile on skystore...")

            try:
                apply_satellite_alignment_skystore(mission.id)
                self.stdout.write(self.style.SUCCESS(
                    f"  DONE: offset corrected by {offset:.2f}m"
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  FAILED: {e}"))
                logger.error(f"Satellite realign failed for {mission.id}: {e}", exc_info=True)
