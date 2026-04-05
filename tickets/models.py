import secrets
from django.db import models
from core.models import ULIDModel


def generate_qr_token():
    return secrets.token_hex(32)


class TicketType(ULIDModel):
    """Template for purchasable tickets — linked to Event OR Route."""

    class Category(models.TextChoices):
        EVENT = 'EVENT', 'Event ticket'
        TRANSIT = 'TRANSIT', 'Transit ticket'

    # Mutually exclusive: event OR route
    event = models.ForeignKey(
        'geo.Event', on_delete=models.CASCADE,
        null=True, blank=True, related_name='ticket_types',
    )
    route = models.ForeignKey(
        'geo.Route', on_delete=models.CASCADE,
        null=True, blank=True, related_name='ticket_types',
    )

    # Who receives Lightning payment
    operator = models.ForeignKey(
        'identity.Profile', on_delete=models.CASCADE,
        related_name='operated_ticket_types',
    )

    category = models.CharField(max_length=10, choices=Category.choices, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price_sats = models.PositiveBigIntegerField(help_text="Price in satoshis")
    max_capacity = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Max tickets (null = unlimited)",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    sold_count = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['event', 'is_active']),
            models.Index(fields=['route', 'is_active']),
            models.Index(fields=['category', 'is_active']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(event__isnull=True, route__isnull=False) |
                    models.Q(event__isnull=False, route__isnull=True)
                ),
                name='ticket_type_event_xor_route',
            ),
        ]

    def __str__(self):
        target = self.event.title if self.event_id else (
            self.route.short_name if self.route_id else '?'
        )
        return f"{self.name} ({target}) — {self.price_sats} sats"

    @property
    def is_sold_out(self):
        if self.max_capacity is None:
            return False
        return self.sold_count >= self.max_capacity


class Ticket(ULIDModel):
    """Individual purchased ticket."""

    class Status(models.TextChoices):
        PENDING_PAYMENT = 'PENDING_PAYMENT', 'Pending Payment'
        ACTIVE = 'ACTIVE', 'Active'
        USED = 'USED', 'Used'
        CANCELLED = 'CANCELLED', 'Cancelled'
        EXPIRED = 'EXPIRED', 'Expired'

    ticket_type = models.ForeignKey(
        TicketType, on_delete=models.CASCADE, related_name='tickets',
    )
    buyer = models.ForeignKey(
        'identity.Profile', on_delete=models.CASCADE,
        related_name='purchased_tickets',
    )

    status = models.CharField(
        max_length=20, choices=Status.choices,
        default=Status.PENDING_PAYMENT, db_index=True,
    )

    # QR & validation
    qr_token = models.CharField(
        max_length=64, unique=True, db_index=True,
        default=generate_qr_token,
    )
    pgp_signature = models.TextField(blank=True)

    # Lightning payment proof
    ln_payment_hash = models.CharField(max_length=64, blank=True, db_index=True)
    ln_preimage = models.CharField(max_length=64, blank=True)
    amount_paid_sats = models.PositiveBigIntegerField(default=0)

    # Timestamps
    paid_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['buyer', 'status']),
            models.Index(fields=['ticket_type', 'status']),
        ]

    def __str__(self):
        return f"Ticket {self.id[:8]} ({self.status})"
