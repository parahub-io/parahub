"""Delete voice audio that has outlived its purpose.

Three sweeps, all of them about not keeping recordings of people's voices any
longer than the feature needs them:

1. **Note audio past its expiry** — the mp3 is a rendering of the note; the two
   texts are the record and stay. After 30 days the audio goes and the note
   reads as "audio expired".
2. **Note audio with no note** — a deleted profile takes its notes with it by
   cascade, but the files on disk have no foreign key to follow.
3. **Clone samples that will never become a clone** — a directory whose owner
   withdrew consent (collection should have stopped), or whose files have sat
   untouched past the retention window because the person stopped recording
   halfway to the threshold.

Runs daily from `parahub-voice-purge.timer`. `--dry-run` reports without
deleting; anything it would remove is listed, because a purge that silently
takes more than expected is the one nobody notices.
"""

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from voice.models import VoiceConsent, VoiceNote
from voice.services import cloning, notes as notes_service

SAMPLE_MAX_AGE_DAYS = 30


class Command(BaseCommand):
    help = "Delete expired voice-note audio and abandoned voice-clone samples"

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help="Report what would be deleted, delete nothing")
        parser.add_argument('--verbose-list', action='store_true',
                            help="Print every path considered")

    def handle(self, *args, **opts):
        self.dry_run = opts['dry_run']
        self.verbose_list = opts['verbose_list']
        freed = 0
        freed += self._purge_expired_notes()
        freed += self._purge_orphan_note_files()
        freed += self._purge_abandoned_samples()
        prefix = "Would free" if self.dry_run else "Freed"
        self.stdout.write(self.style.SUCCESS(f"{prefix} {freed / 1024 / 1024:.1f} MB"))

    # ----- 1. expired note audio -------------------------------------------

    def _purge_expired_notes(self) -> int:
        now = timezone.now()
        expired = VoiceNote.objects.filter(
            audio_expires_at__lt=now,
        ).exclude(audio_path='').only('id', 'audio_path')

        freed = 0
        count = 0
        for note in expired.iterator():
            path = Path(settings.MEDIA_ROOT) / note.audio_path
            freed += self._unlink(path)
            count += 1
            if not self.dry_run:
                VoiceNote.objects.filter(pk=note.pk).update(audio_path='')
        self.stdout.write(f"Expired note audio: {count}")
        return freed

    # ----- 2. note audio whose row is gone ---------------------------------

    def _purge_orphan_note_files(self) -> int:
        root = notes_service.AUDIO_ROOT
        on_disk = {p.stem: p for p in root.rglob('*.mp3')} if root.is_dir() else {}
        if not on_disk:
            self.stdout.write("Orphan note files: 0")
            return 0
        known = set(
            VoiceNote.objects.filter(id__in=list(on_disk))
            .values_list('id', flat=True)
        )
        freed = 0
        orphans = [p for note_id, p in on_disk.items() if note_id not in known]
        for path in orphans:
            freed += self._unlink(path)
        self.stdout.write(f"Orphan note files: {len(orphans)}")
        self._prune_empty_dirs(root)
        return freed

    # ----- 3. clone samples that will never be used ------------------------

    def _purge_abandoned_samples(self) -> int:
        root = cloning.SAMPLES_ROOT
        if not root.is_dir():
            self.stdout.write("Sample files: 0")
            return 0

        cutoff = timezone.now() - timedelta(days=SAMPLE_MAX_AGE_DAYS)
        cutoff_ts = cutoff.timestamp()
        consented = set(
            VoiceConsent.objects.filter(revoked_at__isnull=True)
            .values_list('profile_id', flat=True)
        )

        freed = 0
        dropped_dirs = 0
        dropped_files = 0
        for directory in root.iterdir():
            if not directory.is_dir():
                continue
            if directory.name not in consented:
                # Consent gone (or profile gone): nothing here may be kept.
                for path in directory.rglob('*'):
                    if path.is_file():
                        freed += self._unlink(path)
                        dropped_files += 1
                dropped_dirs += 1
                continue
            for path in directory.iterdir():
                if path.is_file() and path.stat().st_mtime < cutoff_ts:
                    freed += self._unlink(path)
                    dropped_files += 1

        self.stdout.write(
            f"Sample files: {dropped_files} (from {dropped_dirs} withdrawn-consent folders)")
        self._prune_empty_dirs(root)
        return freed

    # ----- helpers ---------------------------------------------------------

    def _unlink(self, path: Path) -> int:
        try:
            size = path.stat().st_size
        except OSError:
            return 0
        if self.verbose_list or self.dry_run:
            self.stdout.write(f"  {'would delete' if self.dry_run else 'delete'} {path}")
        if not self.dry_run:
            try:
                path.unlink()
            except OSError as e:
                self.stderr.write(f"  could not delete {path}: {e}")
                return 0
        return size

    def _prune_empty_dirs(self, root: Path) -> None:
        if self.dry_run:
            return
        # Deepest first, so a directory emptied by its children can go too.
        for path in sorted(root.rglob('*'), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                try:
                    path.rmdir()
                except OSError:
                    pass
