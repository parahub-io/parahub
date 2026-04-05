import secrets
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from core.models import ULIDModel
from identity.models import Profile
from geo.models import Establishment
from market.models import Item


def generate_tracking_code():
    return secrets.token_urlsafe(6)[:8].upper()


def generate_pickup_code():
    return str(secrets.randbelow(900000) + 100000)


class Shipment(ULIDModel):
    """P-Hub shipment: parcel moving between hub Establishments."""

    class Status(models.TextChoices):
        CREATED = 'CREATED', 'Created'
        AT_ORIGIN = 'AT_ORIGIN', 'At Origin Hub'
        IN_TRANSIT = 'IN_TRANSIT', 'In Transit'
        AT_HUB = 'AT_HUB', 'At Intermediate Hub'
        READY = 'READY', 'Ready for Pickup'
        DELIVERED = 'DELIVERED', 'Delivered'
        EXPIRED = 'EXPIRED', 'Expired'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class SizeCategory(models.TextChoices):
        S = 'S', 'Small (envelope/book)'
        M = 'M', 'Medium (shoebox)'
        L = 'L', 'Large (backpack)'
        XL = 'XL', 'Extra Large (suitcase)'

    # Parties
    sender = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='shipments_sent')
    receiver = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='shipments_received')

    # Route
    origin_hub = models.ForeignKey(Establishment, on_delete=models.PROTECT, related_name='shipments_outbound')
    destination_hub = models.ForeignKey(Establishment, on_delete=models.PROTECT, related_name='shipments_inbound')
    current_hub = models.ForeignKey(Establishment, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='shipments_current')

    # Cargo
    title = models.CharField(max_length=200)
    size_category = models.CharField(max_length=2, choices=SizeCategory.choices)
    item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name='shipments')

    # Tracking
    tracking_code = models.CharField(max_length=8, unique=True, default=generate_tracking_code,
                                     db_index=True, help_text="Public code for QR/sharing (e.g. A3K9M2XP)")
    pickup_code = models.CharField(max_length=6, default=generate_pickup_code,
                                   help_text="One-time code shown only to receiver")
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.CREATED)

    # Fees (informational — payments are direct P2P via Lightning)
    storage_fee_total = models.PositiveIntegerField(default=0, help_text="Accumulated storage fee in sats")
    delivery_fee = models.PositiveIntegerField(default=0, help_text="Agreed carrier fee in sats")

    # Timing
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Auto-set from hub_max_days on deposit")
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sender', 'status']),
            models.Index(fields=['receiver', 'status']),
            models.Index(fields=['current_hub', 'status']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"PH-{self.tracking_code} ({self.status})"


class ShipmentEvent(ULIDModel):
    """Immutable audit log of shipment state changes."""

    class EventType(models.TextChoices):
        CREATED = 'CREATED', 'Created'
        DEPOSITED = 'DEPOSITED', 'Deposited at hub'
        CARRIER_PICKUP = 'CARRIER_PICKUP', 'Carrier picked up'
        ARRIVED = 'ARRIVED', 'Arrived at hub'
        READY = 'READY', 'Ready for pickup'
        DELIVERED = 'DELIVERED', 'Delivered to receiver'
        EXPIRED = 'EXPIRED', 'Expired'
        CANCELLED = 'CANCELLED', 'Cancelled'
        NOTE = 'NOTE', 'Note'

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    hub = models.ForeignKey(Establishment, null=True, blank=True, on_delete=models.SET_NULL)
    actor = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.CASCADE)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['shipment', 'created_at']),
        ]

    def __str__(self):
        return f"{self.event_type} on PH-{self.shipment.tracking_code}"


class CarrierOffer(ULIDModel):
    """Carrier volunteers to move a shipment between hubs."""

    class Status(models.TextChoices):
        OFFERED = 'OFFERED', 'Offered'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='carrier_offers')
    carrier = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='carrier_offers')
    from_hub = models.ForeignKey(Establishment, on_delete=models.PROTECT, related_name='+')
    to_hub = models.ForeignKey(Establishment, on_delete=models.PROTECT, related_name='+')
    fee_sats = models.PositiveIntegerField(default=0, help_text="Carrier's price in sats")
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.OFFERED)
    matrix_room_id = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['shipment', 'status']),
            models.Index(fields=['carrier', 'status']),
        ]

    def __str__(self):
        return f"Offer by {self.carrier} for PH-{self.shipment.tracking_code}"


class RideRequest(ULIDModel):
    """Passenger's ride request — the primary entity in the carpool system."""
    passenger = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='ride_requests')
    origin_stop = models.ForeignKey('geo.Stop', on_delete=models.SET_NULL, null=True, related_name='+')
    destination_stop = models.ForeignKey('geo.Stop', on_delete=models.SET_NULL, null=True, related_name='+')
    price_sats = models.BigIntegerField()
    passengers_count = models.PositiveSmallIntegerField(default=1)
    note = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', '-created_at']),
            models.Index(fields=['passenger', 'is_active']),
        ]


class RideBooking(ULIDModel):
    """Driver's response to a request + booking lifecycle."""
    class Status(models.TextChoices):
        OFFERED = 'OFFERED', 'Offered'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    request = models.ForeignKey(RideRequest, on_delete=models.CASCADE, related_name='bookings')
    driver = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='ride_drives')
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.OFFERED)
    driver_note = models.CharField(max_length=500, blank=True)
    available_seats = models.PositiveSmallIntegerField(default=3)
    matrix_room_id = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['request', 'status']),
            models.Index(fields=['driver', 'status']),
        ]


class RideReview(ULIDModel):
    """Mutual review after a completed ride."""
    booking = models.ForeignKey(RideBooking, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='ride_reviews_given')
    reviewee = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='ride_reviews_received')
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['booking', 'reviewer'], name='unique_ride_review'),
        ]
