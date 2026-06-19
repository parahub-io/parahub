"""
Management command to generate 3D Tiles for existing MESH_READY missions.

Usage:
    python manage.py generate_3d_tiles                    # All MESH_READY missions
    python manage.py generate_3d_tiles --mission=ULID     # Specific mission
    python manage.py generate_3d_tiles --dry-run           # Preview only
    python manage.py generate_3d_tiles --root-only         # Just regenerate root tileset
    python manage.py generate_3d_tiles --tileset-only      # Per-mission tileset.json (no LOD rebuild)
"""

from django.core.management.base import BaseCommand
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Generate 3D Tiles (LODs + tileset.json) for MESH_READY OpenSky missions'

    def add_arguments(self, parser):
        parser.add_argument('--mission', type=str, help='Process specific mission by ULID')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be processed')
        parser.add_argument('--root-only', action='store_true', help='Only regenerate root tileset.json')
        parser.add_argument('--tileset-only', action='store_true', help='Only rewrite per-mission tileset.json (skip LOD GLB rebuild)')

    def handle(self, *args, **options):
        from geo.models import OpenSkyMission
        from geo.tiles3d_generator import (
            generate_3d_tiles_for_mission,
            regenerate_mission_tileset,
            regenerate_root_tileset,
        )

        if options['root_only']:
            self.stdout.write("Regenerating root tileset...")
            regenerate_root_tileset()
            self.stdout.write(self.style.SUCCESS("Root tileset regenerated"))
            return

        if options['mission']:
            missions = OpenSkyMission.objects.filter(id=options['mission'])
            if not missions.exists():
                self.stderr.write(self.style.ERROR(f"Mission {options['mission']} not found"))
                return
        else:
            missions = OpenSkyMission.objects.filter(
                mesh_status=OpenSkyMission.MeshStatus.MESH_READY,
                area__isnull=False,
            )

        count = missions.count()
        if count == 0:
            self.stdout.write("No MESH_READY missions to process")
            return

        self.stdout.write(f"Found {count} mission(s) to process")

        success = 0
        for mission in missions:
            self.stdout.write(f"  Processing {mission.id} ({mission.name or 'unnamed'})...")

            if options['dry_run']:
                self.stdout.write(f"    [DRY RUN] center=({mission.center_lat:.6f}, {mission.center_lng:.6f})")
                self.stdout.write(f"    [DRY RUN] mesh_glb={mission.mesh_glb_size_mb} MB, odm_origin={'yes' if mission.odm_origin else 'no'}")
                continue

            if options['tileset_only']:
                ok = regenerate_mission_tileset(mission)
                label = "tileset.json rewritten" if ok else "tileset rewrite failed"
            else:
                ok = generate_3d_tiles_for_mission(mission)
                label = "3D Tiles generated" if ok else "Failed"

            if ok:
                self.stdout.write(self.style.SUCCESS(f"    {label}"))
                success += 1
            else:
                self.stderr.write(self.style.ERROR(f"    {label}"))

        # In tileset-only mode the root index doesn't change (still references
        # `missions/{id}/tileset.json` per child), so no root regen needed.

        if not options['dry_run']:
            self.stdout.write(f"Completed: {success}/{count} missions")
