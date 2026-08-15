from django.db import models
from django.utils import timezone
from core.models import ULIDModel
from identity.models import Account, Profile


class Payment(ULIDModel):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        EXPIRED = 'EXPIRED', 'Expired'

    sender = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, related_name="sent_payments")
    recipient = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, related_name="received_payments")
    amount_sats = models.BigIntegerField()
    description = models.CharField(max_length=255, blank=True)

    # Set when this payment is one cycle of a recurring Subscription (else null = ad-hoc P2P).
    subscription = models.ForeignKey(
        'Subscription', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payments',
    )

    ln_invoice = models.TextField(blank=True)
    ln_payment_hash = models.CharField(max_length=64, unique=True, db_index=True, null=True, blank=True)
    ln_preimage = models.CharField(max_length=64, blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)


class Donation(ULIDModel):
    """Association donation — separate transaction after P2P payment."""

    class Source(models.TextChoices):
        WALLET_SEND = 'WALLET_SEND', 'After wallet P2P send'
        ADS_CAMPAIGN = 'ADS_CAMPAIGN', 'Ads campaign listing fee'
        MANUAL = 'MANUAL', 'Manual donation'
        PROFILE_TIP = 'PROFILE_TIP', 'After profile tip'
        SUBSCRIPTION = 'SUBSCRIPTION', 'After P2P subscription payment'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        SKIPPED = 'SKIPPED', 'Skipped (0%)'

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='donations')
    source = models.CharField(max_length=20, choices=Source.choices)
    source_amount_sats = models.BigIntegerField(help_text="Original transaction amount")
    donation_amount_sats = models.BigIntegerField(help_text="Actual donation amount")
    support_level_at_time = models.DecimalField(max_digits=4, decimal_places=1)
    ln_payment_hash = models.CharField(max_length=64, blank=True, db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    class Meta:
        db_table = 'finance_donation'
        indexes = [
            models.Index(fields=['profile', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"Donation {self.donation_amount_sats} sats from {self.profile_id} ({self.source})"


class WalletSyncBlob(ULIDModel):
    """Opt-in encrypted cross-device sync of client-side wallet context.

    Tip batches and payment annotations live in localStorage by design — the
    server is never told who paid whom. This row lets a user who explicitly
    opted in carry that context between their own devices: the client encrypts
    the whole store with AES-256-GCM under a key derived from the wallet seed
    (HKDF, client-side) and stores only the ciphertext here. The server cannot
    read it; it learns only that an encrypted store exists, its size and update
    times. Row existence IS the account-level "sync enabled" flag — disabling
    sync deletes the row.
    """

    account = models.OneToOneField(
        Account, on_delete=models.CASCADE, related_name='wallet_sync_blob',
    )
    # base64(iv || AES-256-GCM ciphertext), key never leaves the client.
    ciphertext = models.TextField()

    class Meta:
        db_table = 'finance_wallet_sync_blob'

    def __str__(self):
        return f"WalletSyncBlob for account {self.account_id} ({len(self.ciphertext)} chars)"


class Subscription(ULIDModel):
    """Recurring direct support between two profiles.

    One profile (``subscriber``) commits to send another (``recipient``) a fixed
    amount on a monthly cadence. Non-custodial: the platform never holds funds —
    every cycle is a separate client-side Lightning payment recorded as a
    ``Payment`` linked back here. There is no auto-pull (Lightning is push): the
    subscriber renews each cycle from a reminder, which extends ``expires_at``.

    While ``status == ACTIVE`` and ``expires_at`` is in the future the subscription
    is *live* and unlocks the recipient's restricted content (see
    ``cms.Post.subscribers_only``). Past ``expires_at`` without renewal it lapses
    and access falls away.
    """

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        LAPSED = 'LAPSED', 'Lapsed'          # expired without renewal
        CANCELLED = 'CANCELLED', 'Cancelled'  # subscriber stopped it

    subscriber = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='outbound_subscriptions',
    )
    recipient = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='inbound_subscriptions',
    )
    amount_sats = models.BigIntegerField(help_text="Amount committed per monthly cycle")
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True,
    )

    started_at = models.DateTimeField(auto_now_add=True)
    # Access valid until this moment; a renewal payment pushes it one cycle forward.
    expires_at = models.DateTimeField(db_index=True)
    last_paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    # Last time an "expiring soon" reminder was emitted — guards against re-pinging the same cycle.
    last_reminder_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'finance_subscription'
        constraints = [
            # At most one subscription row per (subscriber, recipient); re-subscribing
            # after cancelling reactivates the same row rather than duplicating it.
            models.UniqueConstraint(
                fields=['subscriber', 'recipient'],
                name='unique_subscriber_recipient',
            ),
        ]
        indexes = [
            models.Index(fields=['recipient', 'status']),
            models.Index(fields=['subscriber', 'status']),
            models.Index(fields=['status', 'expires_at']),
        ]

    def __str__(self):
        return f"Subscription {self.subscriber_id}→{self.recipient_id} ({self.amount_sats} sats/mo, {self.status})"

    @property
    def is_live(self) -> bool:
        """ACTIVE and not yet expired — the gate that unlocks restricted content."""
        return self.status == self.Status.ACTIVE and self.expires_at > timezone.now()
