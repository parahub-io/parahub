"""
Confirm OTS proofs for AuditBatches against the Bitcoin blockchain.

Runs daily (via systemd timer). Two confirmation tiers per batch:

1. `ots verify` against the local Bitcoin node (pruned bitcoind in the prod
   docker compose stack, RPC on 127.0.0.1:8332) — full independent
   verification (merkle path checked against a locally validated header).
2. `ots upgrade` + attestation parse — completes the proof via calendar
   servers and reads the Bitcoin block height the proof itself attests
   (BitcoinBlockHeaderAttestation). Sets bitcoin_block but NOT verified_at:
   verified_at is reserved for tier-1 node verification, which is why the
   batch filter is verified_at — tier-2-attested batches keep coming back
   until the node independently verifies them (fails soft while the node
   is still syncing).

Upgraded published .ots files are committed back to the public registry so the
proofs are self-contained (a pending proof dies with the calendar servers, a
completed one verifies forever).
"""
from django.core.management.base import BaseCommand

from audit_log.models import AuditBatch
from audit_log.services import GitAuditService


class Command(BaseCommand):
    help = 'Confirm OTS proofs for AuditBatches (node verify when available, else calendar-completed attestation)'

    def add_arguments(self, parser):
        parser.add_argument('--batch-id', type=int, help='Confirm a specific batch by ID')
        parser.add_argument('--limit', type=int, default=20, help='Max batches to confirm (default: 20)')

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
            self.stdout.write("No unconfirmed batches with OTS proofs.")
            return

        confirmed = 0
        changed_files = []
        for batch in batches:
            self.stdout.write(
                f"Checking batch {batch.id} (commit {batch.git_commit_hash[:8]}, {batch.event_count} events)..."
            )
            height, changed = git_service.upgrade_batch_proof(batch)
            if changed:
                changed_files.append(changed)

            if git_service.verify_batch(batch):
                self.stdout.write(self.style.SUCCESS(
                    f"  Verified against local node — Bitcoin block #{batch.bitcoin_block}"
                ))
                confirmed += 1
            elif height:
                batch.bitcoin_block = height
                batch.save(update_fields=['bitcoin_block'])
                self.stdout.write(self.style.SUCCESS(
                    f"  Attested at Bitcoin block #{height} (completed proof; local node verify pending)"
                ))
                confirmed += 1
            else:
                self.stdout.write("  Pending — no Bitcoin attestation yet")

        if changed_files:
            try:
                git_service.repo.index.add(changed_files)
                git_service.repo.index.commit(
                    f"audit: upgrade {len(changed_files)} OTS proofs to self-contained form"
                )
                self.stdout.write(f"Committed {len(changed_files)} upgraded proof files.")
            except Exception as e:
                # Left dirty in the worktree — batch_ots_stamp's straggler
                # sweep publishes them on its next run.
                self.stderr.write(f"Failed to commit upgraded proofs (sweep will retry): {e}")
        git_service.push_public()

        self.stdout.write(f"\nConfirmed {confirmed}/{len(batches)} batches.")
