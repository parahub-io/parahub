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

    class ConcessionCategory(models.TextChoices):
        CHILD = 'CHILD', 'Child'
        STUDENT = 'STUDENT', 'Student'
        SENIOR = 'SENIOR', 'Senior'
        REDUCED = 'REDUCED', 'Reduced mobility / social'

    # Mutually exclusive target: event OR route OR agency (network-wide)
    event = models.ForeignKey(
        'geo.Event', on_delete=models.CASCADE,
        null=True, blank=True, related_name='ticket_types',
    )
    route = models.ForeignKey(
        'geo.Route', on_delete=models.CASCADE,
        null=True, blank=True, related_name='ticket_types',
    )
    agency = models.ForeignKey(
        'geo.Agency', on_delete=models.CASCADE,
        null=True, blank=True, related_name='ticket_types',
        help_text="Network-wide ticket: valid on any route of this agency",
    )

    # Creator/manager of record; receives Lightning payment unless
    # operator_establishment is set
    operator = models.ForeignKey(
        'identity.Profile', on_delete=models.CASCADE,
        related_name='operated_ticket_types',
    )
    operator_establishment = models.ForeignKey(
        'geo.Establishment', on_delete=models.CASCADE,
        null=True, blank=True, related_name='operated_ticket_types',
        help_text="Organization operator: receives payment, members manage/validate",
    )

    category = models.CharField(max_length=10, choices=Category.choices, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price_sats = models.PositiveBigIntegerField(
        null=True, blank=True,
        help_text="Fixed price in satoshis (exclusive with price_eur)",
    )
    price_eur = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="EUR price — sats quoted at purchase time (exclusive with price_sats)",
    )
    max_capacity = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Max tickets (null = unlimited)",
    )
    validity_minutes = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Usage window after first validation (null = one-shot: scan marks USED)",
    )
    concession_category = models.CharField(
        max_length=10, choices=ConcessionCategory.choices, blank=True,
        help_text="Concession fare label — inspector checks entitlement document on scan",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    sold_count = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['event', 'is_active']),
            models.Index(fields=['route', 'is_active']),
            models.Index(fields=['agency', 'is_active']),
            models.Index(fields=['category', 'is_active']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(event__isnull=False, route__isnull=True, agency__isnull=True) |
                    models.Q(event__isnull=True, route__isnull=False, agency__isnull=True) |
                    models.Q(event__isnull=True, route__isnull=True, agency__isnull=False)
                ),
                name='ticket_type_single_target',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(price_sats__isnull=False, price_eur__isnull=True) |
                    models.Q(price_sats__isnull=True, price_eur__isnull=False)
                ),
                name='ticket_type_sats_xor_eur_price',
            ),
        ]

    def __str__(self):
        if self.event_id:
            target = self.event.title
        elif self.route_id:
            target = self.route.short_name
        elif self.agency_id:
            target = self.agency.name
        else:
            target = '?'
        price = f"{self.price_eur} EUR" if self.price_eur is not None else f"{self.price_sats} sats"
        return f"{self.name} ({target}) — {price}"

    @property
    def payment_recipient(self):
        """Profile or Establishment whose ln/spark address receives the payment."""
        return self.operator_establishment if self.operator_establishment_id else self.operator

    @property
    def operator_display_name(self):
        if self.operator_establishment_id:
            return self.operator_establishment.name
        return self.operator.display_name

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
        # Windowed ticket activated by first scan; usable until valid_until
        VALIDATED = 'VALIDATED', 'Validated'
        USED = 'USED', 'Used'
        # Buyer asked for a refund; operator refunds manually (NO ESCROW) → CANCELLED
        REFUND_REQUESTED = 'REFUND_REQUESTED', 'Refund Requested'
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

    # Price locked at purchase time (sats quote for EUR-priced types)
    amount_due_sats = models.PositiveBigIntegerField(default=0)
    price_eur = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="EUR price snapshot at purchase (fiat-priced types)",
    )

    # Timestamps
    paid_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)  # first validation
    expires_at = models.DateTimeField(null=True, blank=True)  # PENDING_PAYMENT TTL

    # Usage window (windowed types): set at first validation
    valid_until = models.DateTimeField(null=True, blank=True)
    validation_count = models.PositiveIntegerField(default=0)

    # Refund flow (manual Lightning send-back by operator)
    refund_requested_at = models.DateTimeField(null=True, blank=True)
    refund_reason = models.TextField(blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    refund_payment_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['buyer', 'status']),
            models.Index(fields=['ticket_type', 'status']),
        ]

    def __str__(self):
        return f"Ticket {self.id[:8]} ({self.status})"
