"""
Batch OpenTimestamps stamp management command.

Collects pending TimestampProofs, writes JSON event files, makes a git commit,
stamps the commit hash with OTS, and links proofs to an AuditBatch.
"""
import logging
from datetime import datetime, timezone

from django.core.management.base import BaseCommand
from django.db import transaction

from audit_log.models import AuditBatch, TimestampProof
from audit_log.services import GitAuditService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Batch stamp pending TimestampProofs via git commit + OTS'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show pending proofs without stamping')
        parser.add_argument('--limit', type=int, default=500, help='Max proofs per batch (default: 500)')

    def handle(self, *args, **options):
        pending = list(
            TimestampProof.objects
            .filter(batch__isnull=True, ots_proof__isnull=True)
            .select_related('content_type')
            .order_by('created_at')[:options['limit']]
        )

        if options['dry_run']:
            if not pending:
                self.stdout.write("No pending proofs.")
                return
            self.stdout.write(f"Pending proofs ({len(pending)}):")
            for p in pending:
                self.stdout.write(f"  {p.content_type.model} {p.object_id[:8]} ({p.created_at.date()})")
            return

        git_service = GitAuditService()
        self._publish_stragglers(git_service)

        if not pending:
            self.stdout.write("No pending proofs.")
            # Still push: keyring/registry commits (and straggler proofs) have
            # no publisher of their own — this run is what delivers them.
            git_service.push_public()
            return

        batch_label = datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')

        # 1. Write event files to events/{YYYY-MM-DD}/{model}_{id}.json
        written = git_service.write_event_files(pending)
        if not written:
            self.stdout.write("All pending proofs already have event files; nothing to commit.")
            return

        # 2. git add + commit
        try:
            commit_hash = git_service.commit_events(written, batch_label)
        except Exception as e:
            self.stderr.write(f"Git commit failed: {e}")
            return

        # 3. Capture the PUBLIC repo HEAD (PGP keyring + federation registry) and
        #    record BOTH roots in the stamped file, so the single Bitcoin anchor
        #    also covers the keyring — and it stays independently checkout-able.
        try:
            registry_commit = git_service.repo.head.commit.hexsha
        except Exception:
            registry_commit = None  # public repo has no commits yet → events-only anchor
        hash_file = git_service.write_commit_hash_file(commit_hash, registry_commit, batch_label)

        # 4. OTS stamp the commit hash file
        ots_bytes = git_service.stamp_commit_hash_file(hash_file)
        if not ots_bytes:
            self.stderr.write(
                f"OTS stamp failed for batch {batch_label}. "
                f"Git commit {commit_hash[:8]} preserved; retry on next run."
            )
            return

        # 5. Commit .ots proof to repo (safe to push to Gitea)
        try:
            git_service.commit_ots_proof(hash_file, batch_label)
        except Exception as e:
            logger.warning(f"Failed to commit .ots proof to git: {e}")

        # 6. DB: create AuditBatch + link all pending proofs
        with transaction.atomic():
            batch = AuditBatch.objects.create(
                git_commit_hash=commit_hash,
                git_commit_file=f"batch_commits/{batch_label}.txt",
                ots_proof=ots_bytes,
                event_count=len(pending),
            )
            TimestampProof.objects.filter(
                id__in=[p.id for p in pending]
            ).update(batch=batch)

        # 7. Optional push to Gitea
        git_service.push_public()

        reg = f", registry {registry_commit[:8]}" if registry_commit else ""
        self.stdout.write(self.style.SUCCESS(
            f"Batch {batch.id}: {len(pending)} proofs stamped, events {commit_hash[:8]}{reg}, batch_label={batch_label}"
        ))

    def _publish_stragglers(self, git_service) -> int:
        """
        Commit batch_commits/ files left behind by an earlier failed run:
        untracked ones from a step-5 commit that failed AFTER the batch was
        recorded in the DB, and modified ones from a verify_ots_batches proof
        upgrade whose commit failed. Neither is retried anywhere else, so
        without this sweep the files never reach the public repo.
        """
        untracked = [
            p for p in git_service.repo.untracked_files
            if p.startswith('batch_commits/')
        ]
        dirty = [
            d.a_path for d in git_service.repo.index.diff(None)
            if d.a_path.startswith('batch_commits/')
        ]
        stragglers = sorted(set(untracked + dirty))
        if not stragglers:
            return 0
        try:
            git_service.repo.index.add(stragglers)
            git_service.repo.index.commit(
                f"audit: publish {len(stragglers)} batch proof files left by failed runs"
            )
        except Exception as e:
            logger.warning(f"Failed to commit straggler batch proofs: {e}")
            return 0
        self.stdout.write(f"Published {len(stragglers)} straggler batch proof files.")
        return len(stragglers)
