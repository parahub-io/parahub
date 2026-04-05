"""
Verify OTS proofs for AuditBatches against the Bitcoin blockchain.

Runs daily (via systemd timer) to check which batches have been confirmed.
"""
from django.core.management.base import BaseCommand

from audit_log.models import AuditBatch
from audit_log.services import GitAuditService


class Command(BaseCommand):
    help = 'Verify OTS proofs for unverified AuditBatches against Bitcoin blockchain'

    def add_arguments(self, parser):
        parser.add_argument('--batch-id', type=int, help='Verify a specific batch by ID')
        parser.add_argument('--limit', type=int, default=20, help='Max batches to verify (default: 20)')

    def handle(self, *args, **options):
        git_service = GitAuditService()

        if options.get('batch_id'):
            try:
                batches = [AuditBatch.objects.get(id=options['batch_id'])]
            except AuditBatch.DoesNotExist:
                self.stderr.write(f"Batch {options['batch_id']} not found.")
                return
        else:
            batches = list(
                AuditBatch.objects
                .filter(verified_at__isnull=True, ots_proof__isnull=False)
                .order_by('stamped_at')[:options['limit']]
            )

        if not batches:
            self.stdout.write("No unverified batches with OTS proofs.")
            return

        verified_count = 0
        for batch in batches:
            self.stdout.write(f"Checking batch {batch.id} (commit {batch.git_commit_hash[:8]}, {batch.event_count} events)...")
            ok = git_service.verify_batch(batch)
            if ok:
                self.stdout.write(self.style.SUCCESS(
                    f"  Verified! Bitcoin block #{batch.bitcoin_block}"
                ))
                verified_count += 1
            else:
                self.stdout.write(f"  Not yet confirmed in blockchain (pending)")

        self.stdout.write(f"\nVerified {verified_count}/{len(batches)} batches.")
