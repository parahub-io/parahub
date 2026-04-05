"""
Monthly budget epoch snapshot.
Run via systemd timer on 1st of each month at 02:00.
Usage: python manage.py freeze_budget_epoch [--label 2026-02] [--establishment slug]
"""
import calendar
from datetime import date

from django.core.management.base import BaseCommand

from geo.models import Establishment
from treasury.models import BudgetEpoch, TreasuryAuditLog
from treasury.services import TreasuryService, TreasuryAuditService


class Command(BaseCommand):
    help = 'Freeze current budget allocations into a monthly epoch snapshot'

    def add_arguments(self, parser):
        parser.add_argument(
            '--label', type=str, default=None,
            help='Epoch label (e.g. 2026-02). Defaults to previous month.'
        )
        parser.add_argument(
            '--establishment', type=str, default=None,
            help='Establishment slug. Defaults to all treasury-enabled establishments.'
        )

    def handle(self, *args, **options):
        label = options['label']

        if not label:
            # Default: previous month
            today = date.today()
            if today.month == 1:
                prev_year, prev_month = today.year - 1, 12
            else:
                prev_year, prev_month = today.year, today.month - 1
            label = f"{prev_year}-{prev_month:02d}"

        # Parse dates from label
        year, month = map(int, label.split('-'))
        start_date = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end_date = date(year, month, last_day)

        # Resolve establishments
        slug = options['establishment']
        if slug:
            try:
                establishments = [Establishment.objects.get(slug=slug, treasury_enabled=True)]
            except Establishment.DoesNotExist:
                self.stderr.write(self.style.ERROR(
                    f"Establishment '{slug}' not found or treasury not enabled."
                ))
                return
        else:
            establishments = list(Establishment.objects.filter(treasury_enabled=True))
            if not establishments:
                self.stderr.write(self.style.WARNING("No treasury-enabled establishments found."))
                return

        for est in establishments:
            # Check if epoch already exists for this establishment
            if BudgetEpoch.objects.filter(establishment=est, label=label).exists():
                self.stderr.write(self.style.WARNING(
                    f"Epoch {label} already exists for {est.slug}, skipping."
                ))
                continue

            epoch = TreasuryService.freeze_epoch(est, label, start_date, end_date)

            TreasuryAuditService.create_log_entry(
                establishment=est,
                action=TreasuryAuditLog.Action.EPOCH_FINALIZED,
                payload={
                    'epoch_id': epoch.id,
                    'label': label,
                    'total_eligible': epoch.total_eligible,
                    'total_participants': epoch.total_participants,
                    'merkle_root': epoch.merkle_root,
                },
            )

            self.stdout.write(self.style.SUCCESS(
                f"[{est.slug}] Epoch {label}: {epoch.total_participants}/{epoch.total_eligible} "
                f"participants, merkle_root={epoch.merkle_root[:16]}..."
            ))
