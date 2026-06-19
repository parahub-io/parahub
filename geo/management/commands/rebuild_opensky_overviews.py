"""
Recomposite OpenSky latest/ overview tiles (z13..16) from all contributing missions.

Why: gdal2tiles builds a full per-mission pyramid clipped to the mission's Z17
cell, so every overview tile holds that mission's content in only its own
sub-region (one Z16 tile spans up to 4 Z17 missions; Z15 up to 16; Z14 up to 64).
The publish path's size-wins hard-link keeps just ONE mission's partial overview
tile and drops the rest, so the zoomed-out map (z<=16) shows holes even though
every Z17 tile is full. This command rebuilds each overview coord as the
alpha-composite of ALL contributors (ordered by layer_order) — the true union.

Z17+ tiles are 1 mission = 1 tile and are left untouched (their size-wins hard
link is correct).

Usage:
    python3 manage.py rebuild_opensky_overviews [--dry-run] [--only-multi] [--max-zoom 16]
"""
import logging
import shlex

from django.core.management.base import BaseCommand
from django.db.models import Count

from geo.models import OpenSkyTileLayer
from geo.opensky_processor import (
    SKYSTORE_TILES,
    TILE_ZOOM_OVERVIEW_MAX,
    _build_rebuild_tiles_script,
    _skystore_ssh,
)

logger = logging.getLogger('opensky')


class Command(BaseCommand):
    help = 'Recomposite latest/ overview tiles (z<=16) from all contributing missions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-zoom', type=int, default=TILE_ZOOM_OVERVIEW_MAX,
            help=f'Rebuild overview tiles up to this zoom (default {TILE_ZOOM_OVERVIEW_MAX})',
        )
        parser.add_argument(
            '--only-multi', action='store_true',
            help='Only rebuild coords with 2+ contributing missions (the broken ones)',
        )
        parser.add_argument('--dry-run', action='store_true', help='Show plan, change nothing')

    def handle(self, *args, **options):
        max_z = options['max_zoom']

        coords = list(
            OpenSkyTileLayer.objects.filter(z__lte=max_z)
            .values('z', 'x', 'y')
            .annotate(c=Count('mission_id'))
            .order_by('z', 'x', 'y')
        )
        if options['only_multi']:
            coords = [c for c in coords if c['c'] > 1]

        if not coords:
            self.stdout.write('No overview tiles to rebuild.')
            return

        tiles_to_rebuild = []
        for c in coords:
            contributors = list(
                OpenSkyTileLayer.objects.filter(z=c['z'], x=c['x'], y=c['y'])
                .order_by('layer_order')
                .values_list('mission_id', flat=True)
            )
            tiles_to_rebuild.append({
                'z': c['z'], 'x': c['x'], 'y': c['y'],
                'remaining_missions': contributors,
            })

        multi = sum(1 for t in tiles_to_rebuild if len(t['remaining_missions']) > 1)
        self.stdout.write(
            f'Overview coords to rebuild: {len(tiles_to_rebuild)} '
            f'(z<={max_z}, {multi} with 2+ contributors)'
        )
        for t in tiles_to_rebuild:
            self.stdout.write(
                f"  z{t['z']}/{t['x']}/{t['y']} <- "
                f"{len(t['remaining_missions'])} mission(s): "
                f"{', '.join(m[:8] for m in t['remaining_missions'])}"
            )

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing changed'))
            return

        # Batch to keep the SSH-sent script size bounded as coverage scales.
        BATCH = 200
        total_rebuilt = total_deleted = 0
        for i in range(0, len(tiles_to_rebuild), BATCH):
            batch = tiles_to_rebuild[i:i + BATCH]
            script = _build_rebuild_tiles_script(
                batch, f"{SKYSTORE_TILES}/missions", f"{SKYSTORE_TILES}/latest"
            )
            result = _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=1800)
            for line in result.stdout.strip().splitlines():
                if line.startswith('REBUILD_RESULT:'):
                    parts = line.split(':')
                    total_rebuilt += int(parts[1])
                    total_deleted += int(parts[2])

        self.stdout.write(self.style.SUCCESS(
            f'Overview rebuild complete: {total_rebuilt} tiles recomposited, '
            f'{total_deleted} removed.'
        ))
