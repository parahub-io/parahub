"""
Management command to reset OpenSky data for re-processing with alignment.

Deletes all tiles, orthophotos, and resets missions to QUEUED status.
User can then re-upload missions which will be aligned to the first one.

Usage:
    python manage.py reset_opensky [--dry-run] [--keep-uploads]
"""

from django.core.management.base import BaseCommand
import shutil
import os


class Command(BaseCommand):
    help = 'Reset all OpenSky data (tiles, orthos, mission statuses)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        parser.add_argument(
            '--keep-uploads',
            action='store_true',
            help='Keep source images in missions/ directory'
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Skip confirmation prompt'
        )

    def handle(self, *args, **options):
        from geo.models import OpenSkyMission

        dry_run = options['dry_run']
        keep_uploads = options['keep_uploads']

        # Paths to clean
        paths_to_delete = [
            '/mnt/opensky-tiles/missions',
            '/mnt/opensky-tiles/latest',
            '/mnt/opensky/orthos',
            '/mnt/opensky/processing',
        ]

        if not keep_uploads:
            paths_to_delete.append('/mnt/opensky/missions')

        # Show what will be deleted
        self.stdout.write("\nOpenSky data to be reset:")
        self.stdout.write("=" * 50)

        total_size = 0
        for path in paths_to_delete:
            if os.path.exists(path):
                size = get_dir_size(path)
                total_size += size
                self.stdout.write(f"  {path}: {format_size(size)}")
            else:
                self.stdout.write(f"  {path}: (not found)")

        # Count missions
        missions = OpenSkyMission.objects.all()
        published = missions.filter(status=OpenSkyMission.Status.PUBLISHED).count()
        queued = missions.filter(status=OpenSkyMission.Status.QUEUED).count()
        failed = missions.filter(status=OpenSkyMission.Status.FAILED).count()

        self.stdout.write(f"\nMissions in database: {missions.count()}")
        self.stdout.write(f"  - PUBLISHED: {published} (will be deleted)")
        self.stdout.write(f"  - QUEUED: {queued}")
        self.stdout.write(f"  - FAILED: {failed}")
        self.stdout.write(f"\nTotal size to delete: {format_size(total_size)}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n[DRY RUN] No changes made"))
            return

        if not options['confirm']:
            self.stdout.write(self.style.WARNING(
                "\nThis will DELETE all OpenSky tiles and processed data!"
            ))
            confirm = input("Type 'yes' to confirm: ")
            if confirm.lower() != 'yes':
                self.stdout.write("Cancelled")
                return

        # Delete directories
        self.stdout.write("\nDeleting directories...")
        for path in paths_to_delete:
            if os.path.exists(path):
                self.stdout.write(f"  Deleting {path}...")
                shutil.rmtree(path, ignore_errors=True)
                os.makedirs(path, exist_ok=True)  # Recreate empty
                self.stdout.write(self.style.SUCCESS(f"    Deleted {path}"))

        # Delete missions from database
        self.stdout.write("\nDeleting missions from database...")
        deleted_count = missions.delete()[0]
        self.stdout.write(self.style.SUCCESS(f"  Deleted {deleted_count} mission records"))

        self.stdout.write(self.style.SUCCESS("\nOpenSky reset complete!"))
        self.stdout.write("\nNext steps:")
        self.stdout.write("  1. Re-upload missions via /opensky")
        self.stdout.write("  2. First mission becomes the reference")
        self.stdout.write("  3. Subsequent missions will be aligned to it")


def get_dir_size(path: str) -> int:
    """Get total size of directory in bytes."""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
