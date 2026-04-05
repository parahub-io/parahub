from django.db import models
from core.models import ULIDModel
from identity.models import Profile


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
