"""Recurring-support (Subscription) domain logic.

Shared by the HTTP API and the expiry/reminder management command. Non-custodial
by construction: callers *report* a completed client-side Lightning payment —
nothing in here moves money. Each paid cycle is recorded as a ``Payment`` linked
to the ``Subscription`` and pushes ``expires_at`` one cycle forward.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from finance.models import Subscription, Payment

# One monthly cycle. Kept as a flat 30 days (no calendar-month drift) so renewals
# are predictable and the reminder window math stays simple.
CYCLE = timedelta(days=30)


def is_live_subscriber(subscriber, recipient) -> bool:
    """True iff ``subscriber`` holds an ACTIVE, unexpired subscription to ``recipient``.

    This is the single gate that unlocks a recipient's restricted content. Safe to
    call with either side None (anonymous viewer) — returns False."""
    if subscriber is None or recipient is None or subscriber.id == recipient.id:
        return False
    return Subscription.objects.filter(
        subscriber=subscriber,
        recipient=recipient,
        status=Subscription.Status.ACTIVE,
        expires_at__gt=timezone.now(),
    ).exists()


@transaction.atomic
def start_or_renew(subscriber, recipient, amount_sats, ln_payment_hash=''):
    """Record one paid cycle: create the subscription or extend an existing one.

    Returns ``(subscription, is_new)``. ``is_new`` is True the first time this
    subscriber backs this recipient (or revives it after a full lapse/cancel) — the
    caller uses it to fire the "new subscriber" notification only for genuinely new
    relationships, not on every monthly renewal.

    Idempotent on ``ln_payment_hash``: a replayed report of an already-recorded
    cycle returns the existing subscription without extending it again.
    """
    now = timezone.now()

    # Replay guard — a client retry must not double-extend the period.
    if ln_payment_hash:
        prior = Payment.objects.filter(ln_payment_hash=ln_payment_hash).first()
        if prior is not None and prior.subscription_id:
            return prior.subscription, False

    sub, created = Subscription.objects.select_for_update().get_or_create(
        subscriber=subscriber,
        recipient=recipient,
        defaults={'amount_sats': amount_sats, 'expires_at': now + CYCLE},
    )

    was_dormant = sub.status != Subscription.Status.ACTIVE
    # Extend from the later of now / current expiry so a still-live renewal keeps
    # its unused days; a lapsed one restarts from now.
    base = max(now, sub.expires_at) if (not created and sub.expires_at) else now
    sub.expires_at = base + CYCLE
    sub.amount_sats = amount_sats
    sub.status = Subscription.Status.ACTIVE
    sub.cancelled_at = None
    sub.last_paid_at = now
    sub.save()

    Payment.objects.create(
        sender=subscriber,
        recipient=recipient,
        amount_sats=amount_sats,
        subscription=sub,
        ln_payment_hash=ln_payment_hash or None,
        status=Payment.Status.COMPLETED,
        description=f"recurring support → {recipient.local_name}"[:255],
    )

    return sub, (created or was_dormant)


def cancel(sub) -> Subscription:
    """Stop renewal reminders. Access is retained until the paid period ends — the
    status flips to CANCELLED only when the timer reaches ``expires_at`` (the cycle
    was already paid for, so revoking immediately would be a regression for the
    subscriber)."""
    if sub.cancelled_at is None:
        sub.cancelled_at = timezone.now()
        sub.save(update_fields=['cancelled_at'])
    return sub
