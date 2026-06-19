"""
Regenerate OpenSky tiles from saved orthophotos on skystore.

Runs gdal2tiles + TMS→XYZ WebP conversion on skystore via SSH.
Updates mission records and latest/ layer.
"""
import logging

from django.core.management.base import BaseCommand

from geo.models import OpenSkyMission
from geo.opensky_processor import (
    SKYSTORE_OPENSKY, SKYSTORE_TILES,
    TILE_MIN_ZOOM, TILE_MAX_ZOOM,
    _skystore_ssh, retile_mission_skystore,
)

logger = logging.getLogger('opensky')


class Command(BaseCommand):
    help = 'Regenerate OpenSky tiles for new zoom levels from saved orthophotos (on skystore)'

    def add_arguments(self, parser):
        parser.add_argument('--mission', type=str, help='Specific mission ID to retile')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
        parser.add_argument('--full', action='store_true', help='Full retile (delete existing tiles)')

    def handle(self, *args, **options):
        missions = OpenSkyMission.objects.filter(status=OpenSkyMission.Status.PUBLISHED)
        if options['mission']:
            missions = missions.filter(id=options['mission'])

        if not missions.exists():
            self.stdout.write('No published missions found.')
            return

        for mission in missions:
            r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission.id}.tif"
            r_tiles_mission = f"{SKYSTORE_TILES}/missions/{mission.id}"

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

            # Check existing zoom levels on skystore
            existing_zooms = set()
            try:
                result = _skystore_ssh(f"ls -d {r_tiles_mission}/[0-9]* 2>/dev/null || true")
                for line in result.stdout.strip().splitlines():
                    z = line.strip().split('/')[-1]
                    if z.isdigit():
                        existing_zooms.add(int(z))
            except Exception:
                pass

            needed_zooms = set(range(TILE_MIN_ZOOM, TILE_MAX_ZOOM + 1)) - existing_zooms

            if not needed_zooms and not options['full']:
                self.stdout.write(self.style.SUCCESS(
                    f"SKIP {mission.id} ({mission.name}) — all zoom levels {TILE_MIN_ZOOM}-{TILE_MAX_ZOOM} present"
                ))
                continue

            if options['full']:
                zoom_range = f"{TILE_MIN_ZOOM}-{TILE_MAX_ZOOM}"
                self.stdout.write(f"FULL retile {mission.id} ({mission.name}): zoom {zoom_range}")
            else:
                zoom_range = f"{min(needed_zooms)}-{max(needed_zooms)}"
                self.stdout.write(
                    f"RETILE {mission.id} ({mission.name}): adding zoom {zoom_range} "
                    f"(existing: {sorted(existing_zooms)})"
                )

            if options['dry_run']:
                continue

            try:
                # clean=True (full): mission tiles dir is wiped INSIDE
                # retile_mission_skystore, after the latest/ pre-clear — the
                # pre-clear ownership check needs the old tiles on disk.
                tiles_count, tiles_size = retile_mission_skystore(
                    mission.id, zoom_range, clean=options['full']
                )

                # Update mission record
                mission.min_zoom = TILE_MIN_ZOOM
                mission.max_zoom = TILE_MAX_ZOOM
                mission.tiles_count = tiles_count
                mission.tiles_size_mb = round(tiles_size / 1024 / 1024, 2)
                mission.save(update_fields=['min_zoom', 'max_zoom', 'tiles_count', 'tiles_size_mb'])

                self.stdout.write(self.style.SUCCESS(
                    f"  DONE: {tiles_count} tiles, {mission.tiles_size_mb} MB"
                ))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  FAILED: {e}"))
                logger.error(f"Retile failed for {mission.id}: {e}", exc_info=True)
