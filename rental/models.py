# -*- coding: utf-8 -*-
"""Rental booking layer.

Availability + reservations for any `market.Item` listed for rent — by an
Establishment or a person (P2P). The lightweight primitive that sits *under*
the heavy `contracts.Contract` layer (see `PK/rental-booking-system.md` § Contract
bridge); most rentals stop at a `Booking` and never need a signed contract.

Two booking modes, one `Booking` primitive:
  - RANGE  → arbitrary check-in/check-out (motorcycle, drill, apartment)
  - SLOTS  → recurring weekly grid (room, court, studio)

Double-booking is prevented at the DB level by a Postgres GiST exclusion
constraint on `Booking` (see Meta below); the API also pre-checks for a
friendly error.
"""
from datetime import timedelta

from django.db import models
from django.db.models import Q, Func
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators

from core.models import ULIDModel
from identity.models import Profile


class TsTzRange(Func):
    """tstzrange(start, end, '[)') for the exclusion constraint."""
    function = 'TSTZRANGE'
    output_field = DateTimeRangeField()


class Bookable(ULIDModel):
    """Rental configuration attached to a market.Item.

    Not every Item is bookable; this OneToOne keeps `market` a clean catalog
    while holding the rental-specific knobs here.
    """

    class Mode(models.TextChoices):
        RANGE = 'RANGE', 'Date range (check-in/check-out)'
        SLOTS = 'SLOTS', 'Recurring time slots'

    class Confirmation(models.TextChoices):
        AUTO = 'AUTO', 'Auto-confirm'
        REQUEST = 'REQUEST', 'Owner approves'

    class ContractPolicy(models.TextChoices):
        NEVER = 'NEVER', 'Never'
        THRESHOLD = 'THRESHOLD', 'When asset warrants it'
        ALWAYS = 'ALWAYS', 'Always'

    item = models.OneToOneField(
        'market.Item', on_delete=models.CASCADE, related_name='bookable',
        help_text="The rentable subject (must have a 'rent' pricing option)",
    )
    booking_mode = models.CharField(max_length=8, choices=Mode.choices, default=Mode.RANGE)
    timezone = models.CharField(
        max_length=64, default='Europe/Lisbon',
        help_text="IANA tz; availability/slots are interpreted in this local time",
    )
    min_duration = models.DurationField(null=True, blank=True, help_text="Minimum rental length")
    max_duration = models.DurationField(null=True, blank=True, help_text="Maximum rental length")
    buffer = models.DurationField(default=timedelta(0), help_text="Turnaround gap between bookings")
    advance_window = models.DurationField(
        default=timedelta(days=90), help_text="How far ahead bookings are allowed",
    )
    confirmation = models.CharField(max_length=8, choices=Confirmation.choices, default=Confirmation.AUTO)
    requires_contract = models.CharField(
        max_length=10, choices=ContractPolicy.choices, default=ContractPolicy.THRESHOLD,
        help_text="When a CONFIRMED booking should spawn a rental Contract (see PK/rental-booking-system.md § Contract bridge)",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "Bookable"
        verbose_name_plural = "Bookables"

    def __str__(self):
        return f"Bookable<{self.item_id}:{self.booking_mode}>"

    @property
    def owner_profile_id(self):
        """Who manages this — establishment owner path or the item owner (P2P)."""
        return self.item.owner_id


class Availability(ULIDModel):
    """The 'open' envelope: which weekdays/hours the bookable is offered.

    SLOTS uses weekday flags + start/stop + slot_minutes to generate discrete
    slots (a weekday×time grid). RANGE uses the same weekday/hours
    as opening hours; reservations cut occupancy out of the envelope.
    """
    bookable = models.ForeignKey(Bookable, on_delete=models.CASCADE, related_name='availabilities')
    name = models.CharField(max_length=64, blank=True)

    start = models.TimeField(default='09:00')
    stop = models.TimeField(default='18:00')
    slot_minutes = models.PositiveSmallIntegerField(
        default=60, help_text="Slot length for SLOTS mode (ignored for RANGE)",
    )

    mon = models.BooleanField(default=True)
    tue = models.BooleanField(default=True)
    wed = models.BooleanField(default=True)
    thu = models.BooleanField(default=True)
    fri = models.BooleanField(default=True)
    sat = models.BooleanField(default=True)
    sun = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Availability"
        verbose_name_plural = "Availabilities"
        ordering = ['bookable_id', 'start']

    def __str__(self):
        return f"Availability<{self.bookable_id}: {self.start}-{self.stop}>"

    @property
    def weekdays(self):
        """List of Python weekday ints (Mon=0..Sun=6) this row applies to."""
        flags = [self.mon, self.tue, self.wed, self.thu, self.fri, self.sat, self.sun]
        return [i for i, on in enumerate(flags) if on]


class AvailabilityException(ULIDModel):
    """Blackout window (maintenance, asset out, holiday). Applies to both modes."""
    bookable = models.ForeignKey(Bookable, on_delete=models.CASCADE, related_name='exceptions')
    start = models.DateTimeField()
    end = models.DateTimeField()
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Availability exception"
        verbose_name_plural = "Availability exceptions"
        ordering = ['start']

    def __str__(self):
        return f"Blackout<{self.bookable_id}: {self.start}–{self.end}>"


class Booking(ULIDModel):
    """A reservation of a Bookable for a time window.

    Conflict-free by a DB exclusion constraint over (bookable, [start,end)) for
    live statuses. Completion does NOT consume the item — it returns to
    availability (contrast contract *sale* semantics).
    """

    class Status(models.TextChoices):
        REQUESTED = 'REQUESTED', 'Requested'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        COMPLETED = 'COMPLETED', 'Completed'
        NO_SHOW = 'NO_SHOW', 'No-show'

    # statuses that occupy the calendar (must not overlap)
    LIVE_STATUSES = ['REQUESTED', 'CONFIRMED']

    bookable = models.ForeignKey(Bookable, on_delete=models.CASCADE, related_name='bookings')
    # Nullable for walk-in / phone-in bookings: a manager books on behalf of a
    # client who isn't a platform user (renter=None, external_renter_* below).
    # CASCADE still applies to real renters; a walk-in has no FK target to cascade.
    renter = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True, blank=True,
                               related_name='rentals_as_renter')
    created_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='rentals_created')

    # Walk-in / manual booking: the client is offline (not a platform profile).
    # The manager enters their name (and optionally a phone to reach them); the
    # slot is blocked like any booking, but there is no renter to notify and it
    # never clutters the owner's own "my bookings" (renter is None, not them).
    external_renter_name = models.CharField(
        max_length=120, blank=True,
        help_text="Walk-in / phone-in client name (set when renter is not a platform user)")
    external_renter_phone = models.CharField(
        max_length=40, blank=True, help_text="Walk-in client contact phone (optional)")

    start = models.DateTimeField()
    end = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED, db_index=True)

    # immutable snapshots taken at booking time
    price_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=8, blank=True)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    mode = models.CharField(max_length=8, blank=True, help_text="Snapshot of bookable.booking_mode")
    unit = models.CharField(max_length=16, blank=True, help_text="Snapshot of the rent pricing unit")

    contract = models.ForeignKey('contracts.Contract', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='rental_bookings')
    msg = models.CharField(max_length=255, blank=True)

    # Cancellation audit — who cancelled and an optional reason. Visible to the
    # other party (renter ↔ owner) in their booking log.
    cancelled_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='rentals_cancelled',
                                     help_text="Who cancelled the booking")
    cancel_note = models.CharField(max_length=255, blank=True,
                                   help_text="Optional reason left at cancellation")

    # Recurring series — all occurrences of one "repeat weekly/monthly" request
    # share this ULID. Blank = standalone booking. Each occurrence is still a
    # full, independent Booking row, so the exclusion constraint guards every
    # occurrence on its own (recurring `weekly` bookings, done conflict-safe).
    recurrence_group = models.CharField(
        max_length=26, blank=True, default='', db_index=True,
        help_text="ULID shared by occurrences of a recurring booking series (blank = standalone)",
    )

    class Meta:
        verbose_name = "Booking"
        verbose_name_plural = "Bookings"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['bookable', 'status', 'start']),
            models.Index(fields=['renter', '-created_at']),
        ]
        constraints = [
            # DB-enforced no-double-book: live bookings of the same bookable may
            # not overlap. Requires the btree_gist extension (added in migration
            # 0001 via BTreeGistExtension) for the scalar `bookable` equality.
            ExclusionConstraint(
                name='rental_no_double_booking',
                expressions=[
                    ('bookable', RangeOperators.EQUAL),
                    (TsTzRange('start', 'end', RangeBoundary()), RangeOperators.OVERLAPS),
                ],
                condition=Q(status__in=['REQUESTED', 'CONFIRMED']),
            ),
        ]

    def __str__(self):
        return f"Booking<{self.id}:{self.bookable_id}:{self.status}>"

    @property
    def is_walk_in(self) -> bool:
        """A manager-entered booking for an offline client (no platform renter)."""
        return self.renter_id is None
