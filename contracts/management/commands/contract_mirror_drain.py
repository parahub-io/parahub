"""
Drain pending contract mirror updates from DB to private per-contract git repos.

Single-threaded watermark drain — mirrors the CMS cms_mirror_drain pattern. This
command is the ONLY writer to the contract repos, so .git/index.lock races are
physically impossible. Runs on a systemd timer (parahub-contract-mirror.timer).

Flow:
  1. Read last_sync_ts from cache (Redis); default to epoch on cold start.
  2. Snapshot now() as the new watermark.
  3. Find Contract.objects.filter(updated_at > last_sync) — incremental sync.
  4. mirror.sync(contract) for each.
  5. Advance the watermark to now() only if every sync succeeded; on any error,
     leave it so the next tick retries the failures.

Usage:
  python3 manage.py contract_mirror_drain             # incremental
  python3 manage.py contract_mirror_drain --full      # ignore watermark, re-sync all
  python3 manage.py contract_mirror_drain --dry-run   # list, touch nothing
  python3 manage.py contract_mirror_drain --contract <ulid>   # one contract (no watermark move)
"""
import logging
from datetime import datetime, timezone as dt_timezone

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.utils import timezone

from contracts.contract_git_mirror import ContractGitMirror
from contracts.models import Contract

logger = logging.getLogger(__name__)

LAST_SYNC_KEY = 'contracts:mirror:last_sync_ts'


class Command(BaseCommand):
    help = 'Drain pending contract mirror updates from DB to git (single-threaded)'

    def add_arguments(self, parser):
        parser.add_argument('--full', action='store_true',
                            help='Ignore the watermark and re-sync all contracts')
        parser.add_argument('--contract', help='Limit to one contract ULID (does not move the watermark)')
        parser.add_argument('--dry-run', action='store_true',
                            help='List contracts that would sync, without touching git')

    def handle(self, *args, full=False, contract=None, dry_run=False, **kwargs):
        mirror = ContractGitMirror()
        now = timezone.now()

        last_sync_iso = cache.get(LAST_SYNC_KEY)
        if full or not last_sync_iso:
            last_sync = datetime(2000, 1, 1, tzinfo=dt_timezone.utc)
            mode = 'full' if full else 'cold-start'
        else:
            last_sync = datetime.fromisoformat(last_sync_iso)
            mode = 'incremental'

        qs = Contract.objects.select_related(
            'creator', 'partner', 'arbiter',
        ).prefetch_related('items').filter(updated_at__gt=last_sync).order_by('updated_at')

        if contract:
            qs = qs.filter(id=contract)

        changed = list(qs)

        if dry_run:
            self.stdout.write(f'[{mode}] last_sync={last_sync.isoformat()} now={now.isoformat()}')
            self.stdout.write(f'{len(changed)} contracts would sync:')
            for c in changed[:50]:
                self.stdout.write(
                    f'  {c.status:16s} {c.id} {c.title[:40]} (updated_at={c.updated_at.isoformat()})'
                )
            if len(changed) > 50:
                self.stdout.write(f'  ... and {len(changed) - 50} more')
            return

        synced, errors = 0, 0
        for c in changed:
            try:
                if mirror.sync(c):
                    synced += 1
            except Exception as e:
                logger.error(f'contract_mirror_drain: failed to sync {c.id}: {e}', exc_info=True)
                errors += 1

        # Advance the watermark only on a clean run; errors retry next tick. A
        # scoped --contract run must NOT move the global watermark (it would skip
        # everything else changed since last_sync).
        if errors == 0 and not contract:
            cache.set(LAST_SYNC_KEY, now.isoformat(), timeout=None)
        elif errors:
            logger.warning(f'contract_mirror_drain: {errors} errors — watermark NOT advanced')

        summary = (
            f'contract_mirror_drain [{mode}]: '
            f'{synced} committed, {errors} errors, {len(changed)} scanned'
        )
        logger.info(summary)
        self.stdout.write(summary)
