"""Lifecycle tick for recurring-support subscriptions.

Run on a daily timer. Two jobs:

  1. Finalize subscriptions whose paid period has ended — flip ACTIVE → LAPSED, or
     → CANCELLED if the subscriber had already opted out (so access is kept for the
     period they paid for, then stops cleanly).
  2. Remind subscribers whose support is about to expire (default 3 days out) so
     they can renew with one tap. Each cycle is reminded at most once.

Non-custodial: this never moves money — renewal is the subscriber re-paying from a
reminder. Idempotent: safe to run repeatedly; reminders are de-duplicated per cycle.
"""
import math
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from finance.models import Subscription


class Command(BaseCommand):
    help = "Lapse expired subscriptions and remind subscribers nearing expiry."

    def add_arguments(self, parser):
        parser.add_argument('--reminder-days', type=int, default=3,
                            help='Remind this many days before expiry (default 3)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would happen without writing or notifying')

    def handle(self, *args, **opts):
        now = timezone.now()
        window_days = opts['reminder_days']
        dry = opts['dry_run']

        # 1) Finalize expired ACTIVE subscriptions.
        lapsed = cancelled = 0
        for sub in Subscription.objects.filter(
            status=Subscription.Status.ACTIVE, expires_at__lte=now,
        ):
            new_status = (
                Subscription.Status.CANCELLED if sub.cancelled_at
                else Subscription.Status.LAPSED
            )
            if not dry:
                sub.status = new_status
                sub.save(update_fields=['status'])
            if new_status == Subscription.Status.CANCELLED:
                cancelled += 1
            else:
                lapsed += 1

        # 2) Remind those expiring within the window (not opted-out, once per cycle).
        window_end = now + timedelta(days=window_days)
        reminded = 0
        for sub in Subscription.objects.filter(
            status=Subscription.Status.ACTIVE,
            cancelled_at__isnull=True,
            expires_at__gt=now,
            expires_at__lte=window_end,
        ).select_related('subscriber__account', 'recipient'):
            # Already reminded for this cycle? (a renewal pushes expires_at forward,
            # which re-qualifies the row next cycle.)
            cycle_window_start = sub.expires_at - timedelta(days=window_days)
            if sub.last_reminder_at and sub.last_reminder_at >= cycle_window_start:
                continue

            days_left = max(1, math.ceil((sub.expires_at - now).total_seconds() / 86400))
            account = getattr(sub.subscriber, 'account', None)
            if not dry and account:
                try:
                    from notifications.services import notify_subscription_expiring
                    notify_subscription_expiring(account, sub, days_left)
                except Exception:
                    self.stderr.write(f"  reminder failed for {sub.id}")
                sub.last_reminder_at = now
                sub.save(update_fields=['last_reminder_at'])
            reminded += 1

        self.stdout.write(
            f"process_subscriptions: lapsed={lapsed} cancelled={cancelled} "
            f"reminded={reminded} (dry_run={dry})"
        )
