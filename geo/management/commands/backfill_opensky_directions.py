"""
Backfill direction_counts for existing OpenSky missions.

Reads DJI XMP metadata (GimbalPitchDegree + GimbalYawDegree) from photos
stored on skystore, classifies each photo by direction (nadir / N / E / S / W
/ unknown), and writes counts to OpenSkyMission.direction_counts.

Usage:
    python manage.py backfill_opensky_directions
    python manage.py backfill_opensky_directions --mission 01KNYC27...
    python manage.py backfill_opensky_directions --only-empty
    python manage.py backfill_opensky_directions --dry-run
"""
import json
import logging
import subprocess

from django.core.management.base import BaseCommand

from geo.models import OpenSkyMission
from geo.opensky_processor import SKYSTORE_SSH, SKYSTORE_OPENSKY

logger = logging.getLogger('opensky')


# Remote script — runs on skystore via `ssh ... python3 -`.
# Classifies images in /skystore/opensky/missions/{MID}/images/ by gimbal pitch+yaw.
# Must match classify_photo_direction() in geo/endpoints/opensky.py.
REMOTE_SCRIPT = r'''
import os, re, sys, json, glob

mission_id = sys.argv[1]
base = os.environ.get("SKYSTORE_OPENSKY", "/skystore/opensky")
images_dir = f"{base}/missions/{mission_id}/images"

if not os.path.isdir(images_dir):
    print(json.dumps({"error": f"no images dir: {images_dir}"}))
    sys.exit(0)

files = sorted(glob.glob(f"{images_dir}/*.JPG") + glob.glob(f"{images_dir}/*.jpg") + glob.glob(f"{images_dir}/*.jpeg"))
pitch_re = re.compile(rb'(?:drone-dji|drone):GimbalPitchDegree="([^"]+)"')
yaw_re = re.compile(rb'(?:drone-dji|drone):GimbalYawDegree="([^"]+)"')

counts = {"nadir": 0, "n": 0, "e": 0, "s": 0, "w": 0, "unknown": 0}

for f in files:
    try:
        with open(f, "rb") as fh:
            h = fh.read(65536)
    except Exception:
        counts["unknown"] += 1
        continue
    pm = pitch_re.search(h)
    ym = yaw_re.search(h)
    pitch = float(pm.group(1)) if pm else None
    yaw = float(ym.group(1)) if ym else None

    if pitch is None:
        counts["unknown"] += 1
        continue
    if pitch < -70:
        counts["nadir"] += 1
        continue
    if yaw is None:
        counts["unknown"] += 1
        continue
    yn = yaw % 360
    if yn >= 315 or yn < 45:
        counts["n"] += 1
    elif yn < 135:
        counts["e"] += 1
    elif yn < 225:
        counts["s"] += 1
    else:
        counts["w"] += 1

print(json.dumps({"total": len(files), "counts": counts}))
'''


class Command(BaseCommand):
    help = 'Backfill direction_counts for existing OpenSky missions by reading EXIF on skystore'

    def add_arguments(self, parser):
        parser.add_argument('--mission', type=str, help='Specific mission ID')
        parser.add_argument('--only-empty', action='store_true', help='Only process missions with empty direction_counts')
        parser.add_argument('--dry-run', action='store_true', help='Show results without saving')

    def handle(self, *args, **options):
        missions = OpenSkyMission.objects.filter(status=OpenSkyMission.Status.PUBLISHED)
        if options['mission']:
            missions = missions.filter(id=options['mission'])
        if options['only_empty']:
            missions = [m for m in missions if not m.direction_counts or sum((m.direction_counts or {}).values()) == 0]

        missions = list(missions)
        if not missions:
            self.stdout.write('No matching missions.')
            return

        self.stdout.write(f'Processing {len(missions)} missions...')
        for mission in missions:
            self.stdout.write(f'  {mission.id[:12]} ({mission.name}, {mission.source_photos_count} photos)')
            try:
                result = subprocess.run(
                    [
                        'ssh', '-o', 'ConnectTimeout=10',
                        SKYSTORE_SSH,
                        f'SKYSTORE_OPENSKY={SKYSTORE_OPENSKY} python3 - {mission.id}',
                    ],
                    input=REMOTE_SCRIPT,
                    capture_output=True,
                    text=True,
                    timeout=1800,  # 30 min for very large missions
                )
            except subprocess.TimeoutExpired:
                self.stdout.write(self.style.ERROR(f'    TIMEOUT'))
                continue
            if result.returncode != 0:
                self.stdout.write(self.style.ERROR(f'    ssh exit {result.returncode}: {result.stderr.strip()[:200]}'))
                continue
            stdout = result.stdout.strip()
            if not stdout:
                self.stdout.write(self.style.ERROR(f'    empty output'))
                continue
            try:
                data = json.loads(stdout.splitlines()[-1])
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.ERROR(f'    bad JSON: {e}: {stdout[:200]}'))
                continue
            if 'error' in data:
                self.stdout.write(self.style.WARNING(f'    {data["error"]}'))
                continue

            counts = data['counts']
            total = data['total']
            summary = ' '.join(f'{k}={v}' for k, v in counts.items() if v > 0)
            self.stdout.write(f'    {total} files → {summary or "all zero"}')

            if not options['dry_run']:
                mission.direction_counts = counts
                mission.save(update_fields=['direction_counts'])
                self.stdout.write(self.style.SUCCESS(f'    saved'))

        self.stdout.write(self.style.SUCCESS('Done.'))
