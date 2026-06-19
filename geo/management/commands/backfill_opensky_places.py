"""
Backfill place_label / place_region on OpenSky missions via the local Pelias geocoder.

Resolves each published mission's area name (parish / municipality) + region·country
once and stores it, so mission cards read it from the DB instead of reverse-geocoding
on every page load. New missions get this at publish time; this command covers missions
published before the feature existed.

    python manage.py backfill_opensky_places [--mission=ULID] [--only-empty] [--dry-run]
"""
from django.core.management.base import BaseCommand

from geo.models import OpenSkyMission
from geo.opensky_processor import reverse_geocode_place


class Command(BaseCommand):
    help = "Backfill place_label/place_region on OpenSky missions (reverse-geocode via Pelias)"

    def add_arguments(self, parser):
        parser.add_argument('--mission', type=str, default=None, help='Single mission ULID')
        parser.add_argument('--only-empty', action='store_true', help='Only missions with empty place_label')
        parser.add_argument('--dry-run', action='store_true', help='Show changes without saving')

    def handle(self, *args, **opts):
        qs = OpenSkyMission.objects.filter(status=OpenSkyMission.Status.PUBLISHED)
        if opts['mission']:
            qs = qs.filter(id=opts['mission'])
        if opts['only_empty']:
            qs = qs.filter(place_label='')
        qs = qs.exclude(center_lat__isnull=True).exclude(center_lng__isnull=True)

        total = qs.count()
        self.stdout.write(f"{total} mission(s) to process" + (" [dry-run]" if opts['dry_run'] else ""))

        updated = 0
        for m in qs:
            label, region = reverse_geocode_place(m.center_lat, m.center_lng)
            if not label:
                self.stdout.write(self.style.WARNING(
                    f"  {m.id[:8]}  ({m.center_lat:.4f},{m.center_lng:.4f}) -> no result, skipped"))
                continue
            self.stdout.write(
                f"  {m.id[:8]}  {(m.place_label or '∅')!r} -> {label!r}  |  {region!r}")
            if not opts['dry_run']:
                m.place_label = label
                m.place_region = region
                m.save(update_fields=['place_label', 'place_region'])
                updated += 1

        if opts['dry_run']:
            self.stdout.write(self.style.SUCCESS("Dry-run complete, nothing saved."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Done. {updated} mission(s) updated."))
