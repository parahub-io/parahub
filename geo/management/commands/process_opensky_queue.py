"""
Management command to process queued OpenSky missions.

Runs as a systemd timer every 5 minutes to process drone photos
into XYZ WebP tiles for the OpenSky aerial imagery layer.

Usage:
    python manage.py process_opensky_queue [--dry-run] [--mission-id=ULID]
"""

from django.core.management.base import BaseCommand
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process queued OpenSky missions (ODM -> tiles)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without actually processing'
        )
        parser.add_argument(
            '--mission-id',
            type=str,
            help='Process specific mission by ULID'
        )
        parser.add_argument(
            '--max-missions',
            type=int,
            default=1,
            help='Maximum number of missions to process in one run (default: 1)'
        )

    def handle(self, *args, **options):
        from geo.models import OpenSkyMission
        from geo.opensky_processor import process_mission

        dry_run = options['dry_run']
        specific_mission = options.get('mission_id')
        max_missions = options['max_missions']

        if specific_mission:
            # Process specific mission
            self.stdout.write(f"Processing specific mission: {specific_mission}")

            try:
                mission = OpenSkyMission.objects.get(id=specific_mission)
            except OpenSkyMission.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Mission {specific_mission} not found"))
                return

            if mission.status != OpenSkyMission.Status.QUEUED:
                self.stdout.write(
                    self.style.WARNING(
                        f"Mission {specific_mission} is not in QUEUED status (current: {mission.status})"
                    )
                )
                # Allow processing anyway for debugging
                if not dry_run:
                    mission.status = OpenSkyMission.Status.QUEUED
                    mission.save(update_fields=['status'])

            success = process_mission(specific_mission, dry_run=dry_run)

            if success:
                self.stdout.write(self.style.SUCCESS(f"Mission {specific_mission} processed successfully"))
            else:
                self.stderr.write(self.style.ERROR(f"Mission {specific_mission} processing failed"))

            return

        # Process queue
        processed_count = 0

        for _ in range(max_missions):
            # Use SELECT FOR UPDATE SKIP LOCKED to prevent parallel processing
            # This allows multiple workers to process different missions safely
            with transaction.atomic():
                mission = (
                    OpenSkyMission.objects
                    .select_for_update(skip_locked=True)
                    .filter(status=OpenSkyMission.Status.QUEUED)
                    .order_by('uploaded_at')  # FIFO
                    .first()
                )

                if not mission:
                    if processed_count == 0:
                        self.stdout.write("No queued missions to process")
                    break

                self.stdout.write(f"Processing mission {mission.id} (uploaded {mission.uploaded_at})")

                if dry_run:
                    self.stdout.write(f"  [DRY RUN] Would process mission {mission.id}")
                    self.stdout.write(f"    - Pilot: {mission.pilot_id}")
                    self.stdout.write(f"    - Photos: {mission.source_photos_count}")
                    self.stdout.write(f"    - Size: {mission.source_photos_size_mb} MB")
                    processed_count += 1
                    continue

            # Process outside the transaction (long-running)
            success = process_mission(mission.id, dry_run=dry_run)

            if success:
                self.stdout.write(
                    self.style.SUCCESS(f"Mission {mission.id} processed successfully")
                )
            else:
                self.stderr.write(
                    self.style.ERROR(f"Mission {mission.id} processing failed")
                )

            processed_count += 1

        if processed_count > 0:
            self.stdout.write(f"Processed {processed_count} mission(s)")
