"""
Rental API Endpoints
Availability + bookings for market.Item assets listed for rent (Establishment or P2P).

Booking layer only — the heavy legal Contract layer (dual-PGP) is bridged
separately (see `PK/rental-booking-system.md` § Contract bridge). Double-booking is prevented at the DB level
by an exclusion constraint on rental.Booking; this API pre-checks for a
friendly 409 and falls back on the constraint as the race backstop.
"""
import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal
from math import ceil
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ninja import Router, Schema
from ninja.errors import HttpError
from django.db import IntegrityError, transaction
from django.db.models import Q, Case, When, IntegerField
from django.utils import timezone

from core.models import generate_ulid
from market.models import Item
from market.visibility import visible_items_q, can_view_item
from rental.models import Bookable, Availability, AvailabilityException, Booking
from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.services.ws_publish import ws_publish
from geo.permissions import get_establishment_for_action, POSTING_ROLES
from notifications.services import (
    notify_new_booking, notify_booking_confirmed, notify_booking_cancelled,
)

import logging

logger = logging.getLogger(__name__)

router = Router(tags=["Rental"])

WEEKDAY_FIELDS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

# Recurring bookings: cap the series length so one request can't fan out
# unboundedly (occurrences past advance_window are skipped anyway).
RECURRENCE_KINDS = {'NONE', 'WEEKLY', 'MONTHLY'}
MAX_REPEAT = 52


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------
class AvailabilityIn(Schema):
    name: str = ""
    start: str = "09:00"
    stop: str = "18:00"
    slot_minutes: int = 60
    weekdays: List[int] = [0, 1, 2, 3, 4, 5, 6]  # Mon=0..Sun=6


class AvailabilityResponse(Schema):
    id: str
    object_type: str = "availability"
    start: str
    stop: str
    slot_minutes: int
    weekdays: List[int]


class ExceptionIn(Schema):
    """A blackout the owner adds, expressed as an inclusive day range in the
    bookable's timezone (block whole days for maintenance / holiday / personal
    use). The server anchors it to that tz and stores [start 00:00, end+1 00:00)."""
    start_date: str  # YYYY-MM-DD, inclusive
    end_date: str    # YYYY-MM-DD, inclusive
    reason: str = ""


class ExceptionResponse(Schema):
    id: str
    object_type: str = "availability_exception"
    start_date: str  # inclusive, in the bookable's tz
    end_date: str    # inclusive, in the bookable's tz
    reason: str = ""


class ExceptionCreateResponse(Schema):
    exception: ExceptionResponse
    # Live bookings already overlapping the new blackout — a warning for the
    # owner (the blackout does NOT cancel them; it just blocks further bookings).
    conflicts: int = 0


class BookableCreateRequest(Schema):
    item_id: str
    booking_mode: str = "RANGE"          # RANGE | SLOTS
    timezone: str = "Europe/Lisbon"
    confirmation: str = "AUTO"            # AUTO | REQUEST
    requires_contract: str = "THRESHOLD"  # NEVER | THRESHOLD | ALWAYS
    min_duration_minutes: Optional[int] = None
    max_duration_minutes: Optional[int] = None
    buffer_minutes: int = 0
    availability: List[AvailabilityIn] = []


class BookableUpdateRequest(Schema):
    booking_mode: Optional[str] = None
    timezone: Optional[str] = None
    confirmation: Optional[str] = None
    requires_contract: Optional[str] = None
    is_active: Optional[bool] = None


class RentTier(Schema):
    """One rental pricing option (hour / half-day / weekend …). A listing may carry
    several; the renter page shows them all, mirroring the market listing."""
    amount: Optional[Decimal] = None
    currency: str = ""
    unit: str = ""
    note: str = ""


class BookableResponse(Schema):
    id: str
    object_type: str = "bookable"
    item_id: str
    booking_mode: str
    timezone: str
    confirmation: str
    requires_contract: str
    is_active: bool
    rent_amount: Optional[Decimal] = None
    currency: str = ""
    unit: str = ""
    # Every 'rent' pricing tier (the booking total still bills the primary one);
    # lets the renter surface list the same variants shown on the market page.
    rent_options: List[RentTier] = []
    advance_window_days: int = 90  # how far ahead bookings are allowed — drives the SLOTS week-pager horizon


class OccupiedSpan(Schema):
    start: datetime
    end: datetime
    status: str  # booking status or "BLACKOUT"


class SlotSpan(Schema):
    start: datetime
    end: datetime
    busy: bool


class OpenHours(Schema):
    weekday: int
    start: str
    stop: str
    slot_minutes: int = 60


class AvailabilityWindowResponse(Schema):
    bookable: BookableResponse
    occupied: List[OccupiedSpan] = []
    slots: List[SlotSpan] = []
    open_hours: List[OpenHours] = []


class RentalContextResponse(Schema):
    """What the rental page needs before deciding what to render:
    is the item rentable, is it already bookable, and may the viewer set it up?"""
    object_type: str = "rental_context"
    item_id: str
    item_title: str = ""
    slug: str = ""
    has_rent_option: bool
    is_bookable: bool
    can_manage: bool
    rent_amount: Optional[Decimal] = None
    currency: str = ""
    unit: str = ""
    bookable: Optional[BookableResponse] = None


class BookingCreateRequest(Schema):
    item_id: str
    start: datetime
    end: datetime
    msg: str = ""
    recurrence: str = "NONE"   # NONE | WEEKLY | MONTHLY
    repeat: int = 1            # total occurrences incl. the anchor (clamped 1..MAX_REPEAT)
    # Walk-in / manual booking (manager only): book for an offline client who is
    # not a platform user. When `external_renter_name` is set the caller must
    # manage the item; the booking is created with no renter, auto-confirmed.
    external_renter_name: str = ""
    external_renter_phone: str = ""


class BookingResponse(Schema):
    id: str
    object_type: str = "booking"
    bookable_id: str
    item_id: str
    item_title: str = ""
    renter_id: Optional[str] = None   # None for walk-in / manual bookings
    renter_name: str = ""             # platform renter name, or the walk-in client name
    is_walk_in: bool = False
    client_phone: str = ""            # walk-in client phone (empty for platform renters)
    start: datetime
    end: datetime
    status: str
    price_total: Optional[Decimal] = None
    currency: str = ""
    deposit_amount: Optional[Decimal] = None
    mode: str = ""
    unit: str = ""
    contract_id: Optional[str] = None
    msg: str = ""
    cancel_note: str = ""
    cancelled_by_id: Optional[str] = None
    recurrence_group: str = ""
    created_at: datetime


class SkippedOccurrence(Schema):
    start: datetime
    reason: str  # 'occupied' | 'blackout' | 'unavailable' | 'outside_window'


class BookingCreateResponse(Schema):
    """Result of a booking request. A standalone booking → one entry in
    `bookings`, empty `skipped`. A recurring series → the created occurrences
    plus any dates that were skipped (already occupied / outside availability)."""
    object_type: str = "booking_result"
    bookings: List[BookingResponse]
    skipped: List[SkippedOccurrence] = []
    recurrence_group: str = ""


class BookingCancelRequest(Schema):
    note: str = ""
    series: bool = False  # also cancel future occurrences sharing the series


class RentalBoardItem(Schema):
    item_id: str
    object_type: str = "board_item"
    title: str
    slug: str = ""
    booking_mode: str
    confirmation: str = "AUTO"
    rent_amount: Optional[Decimal] = None
    currency: str = ""
    unit: str = ""


class RentalBoardOwner(Schema):
    """Compact owner profile carried on the board so a rental page is a
    self-contained, shareable landing (who the owner is + how to reach them)
    without a second fetch. The owner is polymorphic — an Establishment (org) or
    a Profile (P2P person); `kind` tells the header which fields to render.
    Org-only fields (category, hours, contacts) and person-only fields (hna,
    reputation) default empty for the other kind. A single item is just this
    board focused on n=1, so both granularities share one owner header."""
    kind: str                      # 'establishment' | 'profile'
    id: str
    object_type: str = "owner"
    name: str
    slug: str = ""                 # org slug OR person local_name — used to build URLs
    logo_url: str = ""             # org logo OR person avatar
    description: str = ""          # org description OR person bio
    is_verified: bool = False      # org.is_verified OR person.is_verified_wot
    rating_avg: float = 0.0
    rating_count: int = 0
    # establishment-only
    category_name: str = ""        # English ref-data name; FE localizes by slug
    category_slug: str = ""
    organization_type: str = ""
    full_address: str = ""
    city: str = ""
    location: Optional[Dict[str, float]] = None  # {lat, lon}
    phone: str = ""
    email: str = ""
    website: str = ""
    opening_hours: Dict[str, str] = {}
    is_online: bool = False
    member_count: int = 0
    # profile-only
    hna: str = ""
    reputation_score: float = 0.0


class RentalBoardResponse(Schema):
    """An owner's rentable inventory in one view (one owner → many resources,
    each with its own timetable). The owner is an org or a person — the same
    board, two header projections. Tabs render each item's full availability via
    the existing /items/{id}/availability."""
    object_type: str = "rental_board"
    owner: Optional[RentalBoardOwner] = None
    can_manage: bool = False
    items: List[RentalBoardItem] = []


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _resolve_item(item_id: str) -> Optional[Item]:
    """Resolve an item by ULID or slug (the public market URL uses the slug)."""
    item = Item.objects.filter(id=item_id).first()
    if item is None:
        item = Item.objects.filter(slug=item_id).first()
    return item


def _notify_async(fn, *args):
    """Fire a push notification after the current transaction commits, off the
    request thread — push delivery does network I/O (Web Push + FCM) and must
    not block the booking response."""
    from parahub.background import spawn
    transaction.on_commit(lambda: spawn(fn, *args, label='rental_notification'))


def _manager_accounts(item: Item):
    """Accounts that manage this item's rentals: the P2P owner, or (for an
    establishment item) the establishment owner + its OWNER/ADMIN members."""
    from geo.models import Establishment, EstablishmentMembership
    accounts = []
    if item.establishment_id:
        est = (Establishment.objects.filter(id=item.establishment_id)
               .select_related('owner__account').first())
        if est and est.owner_id and est.owner.account_id:
            accounts.append(est.owner.account)
        for m in (EstablishmentMembership.objects
                  .filter(establishment_id=item.establishment_id, role__in=['OWNER', 'ADMIN'])
                  .select_related('profile__account')):
            if m.profile and m.profile.account_id:
                accounts.append(m.profile.account)
    elif item.owner_id and item.owner.account_id:
        accounts.append(item.owner.account)
    # dedup by account id
    seen, out = set(), []
    for a in accounts:
        if a and a.id not in seen:
            seen.add(a.id)
            out.append(a)
    return out


def _managed_establishment_ids(profile):
    """Establishment IDs the profile may manage (owner or POSTING_ROLES member)."""
    from geo.models import Establishment, EstablishmentMembership
    ids = set(EstablishmentMembership.objects
              .filter(profile=profile, role__in=POSTING_ROLES)
              .values_list('establishment_id', flat=True))
    ids |= set(Establishment.objects
               .filter(owner=profile, is_active=True)
               .values_list('id', flat=True))
    return ids


def _rent_options(item: Item) -> List[dict]:
    """All 'rent' pricing tiers on the item, in listing order (may be empty)."""
    return [opt for opt in (item.pricing_options or []) if opt.get('type') == 'rent']


def _rent_option(item: Item) -> Optional[dict]:
    """The primary rent tier (first listed) — used to bill the booking total."""
    opts = _rent_options(item)
    return opts[0] if opts else None


def _tz(bookable: Bookable) -> ZoneInfo:
    try:
        return ZoneInfo(bookable.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _compute_units(start: datetime, end: datetime, unit: str) -> int:
    """Billable units for a [start,end) window given the rent unit (ceil, min 1)."""
    seconds = (end - start).total_seconds()
    if unit == 'hour':
        units = seconds / 3600
    elif unit == 'month':
        units = seconds / (3600 * 24 * 30)
    elif unit == 'week':
        units = seconds / (3600 * 24 * 7)
    else:  # day (default)
        units = seconds / (3600 * 24)
    return max(1, ceil(units - 1e-9))


def _bookable_response(b: Bookable, item: Item) -> BookableResponse:
    opts = _rent_options(item)
    rent = opts[0] if opts else {}
    amount = rent.get('amount')
    return BookableResponse(
        id=b.id, item_id=item.id, booking_mode=b.booking_mode, timezone=b.timezone,
        confirmation=b.confirmation, requires_contract=b.requires_contract, is_active=b.is_active,
        rent_amount=Decimal(str(amount)) if amount is not None else None,
        currency=rent.get('currency', ''), unit=rent.get('unit', 'day'),
        rent_options=[
            RentTier(
                amount=Decimal(str(o['amount'])) if o.get('amount') is not None else None,
                currency=o.get('currency', ''), unit=o.get('unit', 'day'), note=o.get('note', ''),
            )
            for o in opts
        ],
        advance_window_days=b.advance_window.days,
    )


def _publish_booking(bk: Booking, event: str):
    """Notify calendar viewers (subscribed to the item ULID) of a booking change.

    Reuses the existing `object:{ulid}` realtime channel — `item` is already a
    public-subscribable object type in RealtimeConsumer.
    """
    ws_publish(f'object:{bk.bookable.item_id}', {
        'type': 'rental.booking',
        'event': event,
        'item_id': bk.bookable.item_id,
        'bookable_id': bk.bookable_id,
        'booking_id': bk.id,
        'status': bk.status,
    })


def _booking_response(bk: Booking) -> BookingResponse:
    item = bk.bookable.item
    r = bk.renter
    # Walk-in (no platform renter) → show the external client name / phone.
    renter_name = (bk.external_renter_name if r is None
                   else (r.display_name or r.local_name or getattr(r, 'hna', '') or ''))
    return BookingResponse(
        id=bk.id, bookable_id=bk.bookable_id, item_id=item.id, item_title=item.title,
        renter_id=bk.renter_id,
        renter_name=renter_name,
        is_walk_in=bk.is_walk_in,
        client_phone=(bk.external_renter_phone if r is None else ''),
        start=bk.start, end=bk.end, status=bk.status,
        price_total=bk.price_total, currency=bk.currency, deposit_amount=bk.deposit_amount,
        mode=bk.mode, unit=bk.unit, contract_id=bk.contract_id, msg=bk.msg,
        cancel_note=bk.cancel_note, cancelled_by_id=bk.cancelled_by_id,
        recurrence_group=bk.recurrence_group,
        created_at=bk.created_at,
    )


def _can_manage_item(item: Item, profile) -> bool:
    """Whether `profile` may manage this item's rentals (org manager or P2P owner)."""
    if item.establishment_id:
        try:
            get_establishment_for_action(item.establishment_id, profile, POSTING_ROLES)
            return True
        except HttpError:
            return False
    return item.owner_id == profile.id


def _managed_item_or_403(item_id: str, profile) -> Item:
    """Return the item if `profile` may manage its rental config (manager or P2P owner)."""
    item = _resolve_item(item_id)
    if not item:
        raise HttpError(404, "Item not found")
    if item.establishment_id:
        get_establishment_for_action(item.establishment_id, profile, POSTING_ROLES)
    elif item.owner_id != profile.id:
        raise HttpError(403, "Not allowed to manage this item")
    return item


def _create_availabilities(bookable: Bookable, rows: List[AvailabilityIn]):
    for r in rows:
        kwargs = {f: (i in r.weekdays) for i, f in enumerate(WEEKDAY_FIELDS)}
        Availability.objects.create(
            bookable=bookable, name=r.name, start=r.start, stop=r.stop,
            slot_minutes=r.slot_minutes, **kwargs,
        )


def _generate_slots(bookable: Bookable, frm: datetime, to: datetime):
    tz = _tz(bookable)
    avails = list(bookable.availabilities.all())
    out = []
    day = frm.astimezone(tz).date()
    end_day = to.astimezone(tz).date()
    guard = 0
    while day <= end_day and guard < 400:
        guard += 1
        wd = day.weekday()
        for a in avails:
            if wd not in a.weekdays:
                continue
            cur = datetime.combine(day, a.start, tzinfo=tz)
            stop = datetime.combine(day, a.stop, tzinfo=tz)
            step = timedelta(minutes=a.slot_minutes or 60)
            while cur + step <= stop:
                s_end = cur + step
                if s_end > frm and cur < to:
                    out.append((cur, s_end))
                cur = s_end
        day += timedelta(days=1)
    return out


def _validate_window(bookable: Bookable, start: datetime, end: datetime):
    """Sanity + availability checks. Double-booking itself is enforced by the DB."""
    now = timezone.now()
    if start >= end:
        raise HttpError(400, "End must be after start")
    if start < now - timedelta(minutes=1):
        raise HttpError(400, "Cannot book in the past")
    if start > now + bookable.advance_window:
        raise HttpError(400, "Outside the booking window")
    duration = end - start
    if bookable.min_duration and duration < bookable.min_duration:
        raise HttpError(400, "Shorter than the minimum rental duration")
    if bookable.max_duration and duration > bookable.max_duration:
        raise HttpError(400, "Longer than the maximum rental duration")

    # blackout overlap
    if bookable.exceptions.filter(start__lt=end, end__gt=start).exists():
        raise HttpError(409, "Asset unavailable in that window (blackout)")

    tz = _tz(bookable)
    avails = list(bookable.availabilities.all())
    if not avails:
        return  # no availability rules configured → only sanity + blackout apply

    if bookable.booking_mode == Bookable.Mode.SLOTS:
        # window must exactly match a generated slot
        slots = _generate_slots(bookable, start, end)
        if not any(s == start and e == end for s, e in slots):
            raise HttpError(400, "Selected slot is not offered")
    else:
        # RANGE: pickup (start) and return (end) must fall on open weekday/time
        def _open_at(dt):
            local = dt.astimezone(tz)
            wd = local.weekday()
            t = local.time()
            return any(wd in a.weekdays and a.start <= t <= a.stop for a in avails)
        if not (_open_at(start) and _open_at(end)):
            raise HttpError(400, "Pickup/return time outside opening hours")


def _add_months(d: datetime, n: int) -> datetime:
    """Add n calendar months to a naive datetime, clamping the day (Jan 31 +1mo
    → Feb 28/29). Wall-clock time is preserved."""
    month_index = d.month - 1 + n
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def _occurrence_windows(bookable: Bookable, start: datetime, end: datetime,
                        recurrence: str, repeat: int):
    """Yield (start, end) windows for a (possibly recurring) booking.

    Offsets are applied to the *local wall-clock* time (in the bookable's tz)
    and re-localized, so a 10:00 weekly slot stays 10:00 across DST shifts —
    not 09:00/11:00 as a naïve UTC `+7 days` would produce. The anchor window
    is always first.
    """
    if recurrence == 'NONE' or repeat <= 1:
        yield start, end
        return
    tz = _tz(bookable)
    base_s = start.astimezone(tz).replace(tzinfo=None)
    base_e = end.astimezone(tz).replace(tzinfo=None)
    for i in range(repeat):
        if i == 0:
            ns, ne = base_s, base_e
        elif recurrence == 'WEEKLY':
            ns, ne = base_s + timedelta(weeks=i), base_e + timedelta(weeks=i)
        else:  # MONTHLY
            ns, ne = _add_months(base_s, i), _add_months(base_e, i)
        yield ns.replace(tzinfo=tz), ne.replace(tzinfo=tz)


# ----------------------------------------------------------------------------
# Bookable management (manager / P2P owner)
# ----------------------------------------------------------------------------
@router.post('/bookables', response={200: BookableResponse}, auth=ProfileAuth())
def create_bookable(request, data: BookableCreateRequest):
    profile = request.auth_profile
    item = _managed_item_or_403(data.item_id, profile)
    if not _rent_option(item):
        raise HttpError(400, "Item has no 'rent' pricing option")
    if hasattr(item, 'bookable'):
        raise HttpError(409, "Item is already bookable")

    with transaction.atomic():
        bookable = Bookable.objects.create(
            item=item,
            booking_mode=data.booking_mode,
            timezone=data.timezone,
            confirmation=data.confirmation,
            requires_contract=data.requires_contract,
            min_duration=timedelta(minutes=data.min_duration_minutes) if data.min_duration_minutes else None,
            max_duration=timedelta(minutes=data.max_duration_minutes) if data.max_duration_minutes else None,
            buffer=timedelta(minutes=data.buffer_minutes or 0),
        )
        _create_availabilities(bookable, data.availability)
    return _bookable_response(bookable, item)


@router.patch('/bookables/{bookable_id}', response={200: BookableResponse}, auth=ProfileAuth())
def update_bookable(request, bookable_id: str, data: BookableUpdateRequest):
    profile = request.auth_profile
    bookable = Bookable.objects.select_related('item').filter(id=bookable_id).first()
    if not bookable:
        raise HttpError(404, "Bookable not found")
    _managed_item_or_403(bookable.item_id, profile)
    for field in ('booking_mode', 'timezone', 'confirmation', 'requires_contract', 'is_active'):
        val = getattr(data, field)
        if val is not None:
            setattr(bookable, field, val)
    bookable.save()
    return _bookable_response(bookable, bookable.item)


@router.post('/bookables/{bookable_id}/availability', response={200: List[AvailabilityResponse]}, auth=ProfileAuth())
def set_availability(request, bookable_id: str, rows: List[AvailabilityIn]):
    """Replace the bookable's availability envelope(s) with `rows` (set-semantics).

    The owner's edit panel sends the full schedule, so existing rows are cleared
    first — otherwise edits would accumulate stale envelopes. Bookings reference
    the bookable (not the availability), so replacing rows never touches live
    reservations.
    """
    profile = request.auth_profile
    bookable = Bookable.objects.filter(id=bookable_id).first()
    if not bookable:
        raise HttpError(404, "Bookable not found")
    _managed_item_or_403(bookable.item_id, profile)
    with transaction.atomic():
        bookable.availabilities.all().delete()
        _create_availabilities(bookable, rows)
    return [
        AvailabilityResponse(
            id=a.id, start=str(a.start), stop=str(a.stop),
            slot_minutes=a.slot_minutes, weekdays=a.weekdays,
        )
        for a in bookable.availabilities.all()
    ]


# ----------------------------------------------------------------------------
# Blackout exceptions (manager / P2P owner): block specific day ranges
# ----------------------------------------------------------------------------
def _exc_to_response(ex: AvailabilityException, tz: ZoneInfo) -> ExceptionResponse:
    """Project a stored [start 00:00, end 00:00) datetime window back to the
    inclusive day range the owner sees, in the bookable's timezone."""
    s_local = ex.start.astimezone(tz)
    e_local = ex.end.astimezone(tz)
    return ExceptionResponse(
        id=ex.id,
        start_date=s_local.date().isoformat(),
        end_date=(e_local - timedelta(days=1)).date().isoformat(),  # exclusive → inclusive
        reason=ex.reason,
    )


def _managed_bookable_or_404(bookable_id: str, profile) -> Bookable:
    bookable = Bookable.objects.select_related('item').filter(id=bookable_id).first()
    if not bookable:
        raise HttpError(404, "Bookable not found")
    _managed_item_or_403(bookable.item_id, profile)
    return bookable


@router.get('/bookables/{bookable_id}/exceptions', response={200: List[ExceptionResponse]}, auth=ProfileAuth())
def list_exceptions(request, bookable_id: str):
    """Manager-only: the blackouts on this bookable (with id + reason for editing).
    Renters see blackouts anonymously via the availability read as opaque
    BLACKOUT spans — the reason stays manager-side."""
    bookable = _managed_bookable_or_404(bookable_id, request.auth_profile)
    tz = _tz(bookable)
    return [_exc_to_response(ex, tz) for ex in bookable.exceptions.all()]


@router.post('/bookables/{bookable_id}/exceptions', response={200: ExceptionCreateResponse}, auth=ProfileAuth())
def add_exception(request, bookable_id: str, data: ExceptionIn):
    """Add one blackout (inclusive day range, anchored to the bookable's tz).
    Append-semantics — each blackout is an independent one-off, unlike the
    recurring availability envelope (which is replace-semantics)."""
    bookable = _managed_bookable_or_404(bookable_id, request.auth_profile)
    tz = _tz(bookable)
    try:
        s_date = date.fromisoformat(data.start_date)
        e_date = date.fromisoformat(data.end_date)
    except (ValueError, TypeError):
        raise HttpError(400, "Invalid date (expected YYYY-MM-DD)")
    if e_date < s_date:
        raise HttpError(400, "End date must be on or after the start date")
    start_dt = datetime(s_date.year, s_date.month, s_date.day, tzinfo=tz)
    end_dt = datetime(e_date.year, e_date.month, e_date.day, tzinfo=tz) + timedelta(days=1)
    ex = AvailabilityException.objects.create(
        bookable=bookable, start=start_dt, end=end_dt, reason=(data.reason or '').strip()[:255],
    )
    conflicts = bookable.bookings.filter(
        status__in=Booking.LIVE_STATUSES, start__lt=end_dt, end__gt=start_dt,
    ).count()
    return ExceptionCreateResponse(exception=_exc_to_response(ex, tz), conflicts=conflicts)


@router.delete('/bookables/{bookable_id}/exceptions/{exception_id}', response={200: dict}, auth=ProfileAuth())
def delete_exception(request, bookable_id: str, exception_id: str):
    """Remove one blackout. Scoped to the bookable so an id from another
    bookable can't be deleted through this route."""
    bookable = _managed_bookable_or_404(bookable_id, request.auth_profile)
    deleted, _ = bookable.exceptions.filter(id=exception_id).delete()
    if not deleted:
        raise HttpError(404, "Blackout not found")
    return {"ok": True}


# ----------------------------------------------------------------------------
# Availability read (calendar)
# ----------------------------------------------------------------------------
@router.get('/items/{item_id}/context', response={200: RentalContextResponse}, auth=ProfileAuth())
def rental_context(request, item_id: str):
    """Render context for the rental page: whether the item is rentable/bookable
    and whether the current viewer may configure it (manager or P2P owner)."""
    profile = request.auth_profile
    item = _resolve_item(item_id)
    if not item:
        raise HttpError(404, "Item not found")

    rent = _rent_option(item)
    bookable = getattr(item, 'bookable', None)

    can_manage = _can_manage_item(item, profile)

    return RentalContextResponse(
        item_id=item.id, item_title=item.title, slug=item.slug or '',
        has_rent_option=rent is not None,
        is_bookable=bookable is not None,
        can_manage=can_manage,
        rent_amount=Decimal(str(rent['amount'])) if rent and rent.get('amount') is not None else None,
        currency=(rent or {}).get('currency', ''),
        unit=(rent or {}).get('unit', 'day'),
        bookable=_bookable_response(bookable, item) if bookable else None,
    )


@router.get('/items/{item_id}/availability', response={200: AvailabilityWindowResponse}, auth=OptionalProfileAuth())
def get_availability(request, item_id: str, frm: Optional[datetime] = None, to: Optional[datetime] = None):
    # Public-readable: a shared rental landing must show live availability to
    # anonymous visitors (open hours + busy ranges only — no renter PII).
    item = _resolve_item(item_id)
    if not item:
        raise HttpError(404, "Item not found")
    # REGISTERED items expose no availability to anonymous viewers.
    if not can_view_item(item, request):
        raise HttpError(404, "Item not found")
    bookable = getattr(item, 'bookable', None)
    if not bookable:
        raise HttpError(404, "Item is not bookable")

    now = timezone.now()
    frm = frm or now
    to = to or (now + timedelta(days=7))
    if to > now + bookable.advance_window + timedelta(days=1):
        to = now + bookable.advance_window + timedelta(days=1)

    live = bookable.bookings.filter(status__in=Booking.LIVE_STATUSES, end__gt=frm, start__lt=to)
    occupied = [OccupiedSpan(start=b.start, end=b.end, status=b.status) for b in live]
    for ex in bookable.exceptions.filter(start__lt=to, end__gt=frm):
        occupied.append(OccupiedSpan(start=ex.start, end=ex.end, status="BLACKOUT"))

    slots = []
    if bookable.booking_mode == Bookable.Mode.SLOTS:
        busy_ranges = [(b.start, b.end) for b in live]
        for s, e in _generate_slots(bookable, frm, to):
            busy = any(s < be and e > bs for bs, be in busy_ranges)
            slots.append(SlotSpan(start=s, end=e, busy=busy))

    open_hours = []
    for a in bookable.availabilities.all():
        for wd in a.weekdays:
            open_hours.append(OpenHours(weekday=wd, start=str(a.start), stop=str(a.stop), slot_minutes=a.slot_minutes))

    return AvailabilityWindowResponse(
        bookable=_bookable_response(bookable, item),
        occupied=occupied, slots=slots, open_hours=open_hours,
    )


def _board_owner_from_establishment(est) -> RentalBoardOwner:
    """Project an Establishment onto the board owner header (company profile for
    the self-contained rental landing). Coordinates prefer the establishment's
    own point, falling back to its linked WorldObject (mirrors the FE mapCoords
    precedence in EstablishmentDetail.vue)."""
    wo = est.world_object
    loc = None
    if est.location:
        loc = {"lat": est.location.y, "lon": est.location.x}
    elif wo and wo.location:
        loc = {"lat": wo.location.y, "lon": wo.location.x}
    return RentalBoardOwner(
        kind='establishment',
        id=est.id, name=est.name, slug=est.slug or '',
        logo_url=est.logo_url or '',
        description=est.description or '',
        is_verified=est.is_verified,
        rating_avg=float(est.rating_avg),
        rating_count=est.rating_count,
        category_name=est.category.name if est.category else '',
        category_slug=est.category.slug if est.category else '',
        organization_type=est.organization_type or '',
        full_address=(wo.full_address if wo else '') or '',
        city=(wo.city if wo else '') or '',
        location=loc,
        phone=est.phone or '',
        email=est.email or '',
        website=est.website or '',
        opening_hours=est.opening_hours or {},
        is_online=est.is_online,
        member_count=est.members.count(),
    )


def _board_owner_from_profile(profile) -> RentalBoardOwner:
    """Project a Profile onto the board owner header (the P2P person storefront).
    Avatar→logo, bio→description, WoT status→is_verified, reputation surfaced in
    place of org ratings; org-only fields stay empty. Symmetric with the
    establishment projection so one board renders either owner."""
    return RentalBoardOwner(
        kind='profile',
        id=profile.id,
        name=profile.display_name or profile.local_name or profile.hna,
        slug=profile.local_name or '',
        logo_url=(profile.avatar.url if profile.avatar else ''),
        description=profile.bio or '',
        is_verified=profile.is_verified_wot,
        hna=profile.hna or '',
        reputation_score=float(profile.reputation_score or 0),
    )


def _bookable_items_qs(**owner_filter):
    """Items with an active Bookable for an owner — `establishment_id=…` for an
    org board, or `owner_id=…, establishment_id__isnull=True` for a person's own
    P2P storefront (org-posted items belong to the org board, not the person's)."""
    return (Item.objects.filter(is_active=True, bookable__isnull=False,
                                bookable__is_active=True, **owner_filter)
            .select_related('bookable').order_by('title'))


def _board_items(items) -> List[RentalBoardItem]:
    """Project bookable items onto board entries (price from the rent option)."""
    out = []
    for it in items:
        b = it.bookable
        rent = _rent_option(it) or {}
        out.append(RentalBoardItem(
            item_id=it.id, title=it.title, slug=it.slug or '',
            booking_mode=b.booking_mode, confirmation=b.confirmation,
            rent_amount=Decimal(str(rent['amount'])) if rent.get('amount') is not None else None,
            currency=rent.get('currency', ''), unit=rent.get('unit', 'day'),
        ))
    return out


@router.get('/establishments/{est_id}/board', response={200: RentalBoardResponse}, auth=OptionalProfileAuth())
def establishment_board(request, est_id: str):
    """An establishment's rentable inventory (items with an active Bookable),
    for the owner rental board. Public-readable so the URL is a shareable,
    self-contained booking landing (company profile + inventory + live
    availability); booking itself still requires auth. Lean by design —
    per-item availability is loaded lazily by the active tab via
    /items/{id}/availability."""
    from geo.models import Establishment
    est = (Establishment.objects
           .select_related('world_object', 'category')
           .filter(id=est_id).first()
           or Establishment.objects
           .select_related('world_object', 'category')
           .filter(slug=est_id).first())
    if not est:
        raise HttpError(404, "Establishment not found")

    # can_manage only when authenticated AND holding a posting role.
    can_manage = False
    profile = getattr(request, 'auth_profile', None)
    if profile:
        try:
            get_establishment_for_action(est.id, profile, POSTING_ROLES)
            can_manage = True
        except HttpError:
            can_manage = False

    items = _bookable_items_qs(establishment_id=est.id).filter(visible_items_q(request))
    return RentalBoardResponse(
        owner=_board_owner_from_establishment(est),
        can_manage=can_manage, items=_board_items(items),
    )


@router.get('/profiles/{profile_id}/board', response={200: RentalBoardResponse}, auth=OptionalProfileAuth())
def profile_board(request, profile_id: str):
    """A person's own rentable inventory (the P2P storefront) — the owner board
    generalized from establishments to profiles, so a single item is just this
    board focused on n=1. Resolves by ULID or local_name. Public-readable so
    /rental/u/{name} is a shareable, self-contained landing; booking still
    requires auth. Respects profile visibility: a non-public profile's board is
    hidden from everyone but the owner (mirrors get_public_profile's
    is_publicly_linked gate). Lists only the person's own P2P items —
    org-posted items live on that org's board."""
    from identity.models import Profile
    profile = (Profile.objects.select_related('account').filter(id=profile_id).first()
               or Profile.objects.select_related('account').filter(local_name=profile_id).first())
    if not profile:
        raise HttpError(404, "Profile not found")

    viewer = getattr(request, 'auth_profile', None)
    is_owner = bool(viewer and viewer.id == profile.id)
    if not profile.is_publicly_linked and not is_owner:
        raise HttpError(404, "Profile not found")

    items = _bookable_items_qs(owner_id=profile.id, establishment_id__isnull=True).filter(visible_items_q(request))
    return RentalBoardResponse(
        owner=_board_owner_from_profile(profile),
        can_manage=is_owner, items=_board_items(items),
    )


# ----------------------------------------------------------------------------
# Bookings
# ----------------------------------------------------------------------------
def _skip_reason(err) -> str:
    """Map a failed-occurrence error to a compact skip reason for the series report."""
    if isinstance(err, IntegrityError):
        return 'occupied'
    msg = (getattr(err, 'message', None) or str(err) or '').lower()
    if 'blackout' in msg:
        return 'blackout'
    if 'already booked' in msg or getattr(err, 'status_code', 400) == 409:
        return 'occupied'
    if 'window' in msg:
        return 'outside_window'
    return 'unavailable'


@router.post('/bookings', response={200: BookingCreateResponse}, auth=ProfileAuth())
def create_booking(request, data: BookingCreateRequest):
    profile = request.auth_profile
    item = _resolve_item(data.item_id)
    if not item:
        raise HttpError(404, "Item not found")
    bookable = getattr(item, 'bookable', None)
    if not bookable or not bookable.is_active:
        raise HttpError(404, "Item is not bookable")

    recurrence = (data.recurrence or 'NONE').upper()
    if recurrence not in RECURRENCE_KINDS:
        recurrence = 'NONE'
    repeat = max(1, min(int(data.repeat or 1), MAX_REPEAT))
    is_series = recurrence != 'NONE' and repeat > 1
    group = generate_ulid() if is_series else ''

    rent = _rent_option(item) or {}
    unit = rent.get('unit', 'day')
    amount = rent.get('amount')

    # Walk-in / manual booking: a manager books for an offline client. Only a
    # manager may do this (it has no renter to consent); it is auto-confirmed
    # regardless of the bookable's confirmation mode (the owner is the approver).
    walk_in = bool((data.external_renter_name or '').strip())
    ext_name = (data.external_renter_name or '').strip()[:120]
    ext_phone = (data.external_renter_phone or '').strip()[:40]
    if walk_in:
        if not _can_manage_item(item, profile):
            raise HttpError(403, "Only the owner/manager can add a walk-in booking")
        renter = None
        status = Booking.Status.CONFIRMED
    else:
        renter = profile
        status = (Booking.Status.CONFIRMED if bookable.confirmation == Bookable.Confirmation.AUTO
                  else Booking.Status.REQUESTED)

    created, skipped = [], []
    for idx, (s, e) in enumerate(_occurrence_windows(bookable, data.start, data.end, recurrence, repeat)):
        try:
            _validate_window(bookable, s, e)
            # friendly pre-check (DB exclusion constraint is the race backstop)
            if bookable.bookings.filter(
                status__in=Booking.LIVE_STATUSES, start__lt=e, end__gt=s,
            ).exists():
                raise HttpError(409, "That time is already booked")
            price_total = (Decimal(str(amount)) * _compute_units(s, e, unit)
                           if amount is not None else None)
            with transaction.atomic():
                bk = Booking.objects.create(
                    bookable=bookable, renter=renter, created_by=profile,
                    start=s, end=e, status=status,
                    price_total=price_total, currency=rent.get('currency', ''),
                    mode=bookable.booking_mode, unit=unit, msg=data.msg,
                    external_renter_name=ext_name, external_renter_phone=ext_phone,
                    recurrence_group=group,
                )
            created.append(bk)
        except (HttpError, IntegrityError) as err:
            # The anchor (idx 0) is the date the renter explicitly picked — its
            # failure is a hard error. Later occurrences are best-effort: skip
            # the occupied/unavailable ones and report them back.
            if idx == 0:
                if isinstance(err, IntegrityError):
                    raise HttpError(409, "That time is already booked")
                raise
            skipped.append(SkippedOccurrence(start=s, reason=_skip_reason(err)))

    for bk in created:
        _publish_booking(bk, 'created')
    # One push per request (the anchor) — managers see the rest of a series in
    # the inbox. Skip the renter if they also manage the item.
    if created:
        for acct in _manager_accounts(item):
            if acct.id != profile.account_id:
                _notify_async(notify_new_booking, acct, created[0])
    return BookingCreateResponse(
        bookings=[_booking_response(b) for b in created],
        skipped=skipped, recurrence_group=group,
    )


def _transition(request, booking_id: str, new_status: str, allow_renter: bool, cancel_note=None):
    profile = request.auth_profile
    bk = (Booking.objects
          .select_related('bookable__item', 'renter__account')
          .filter(id=booking_id).first())
    if not bk:
        raise HttpError(404, "Booking not found")
    is_renter = bk.renter_id == profile.id
    is_manager = True
    try:
        _managed_item_or_403(bk.bookable.item_id, profile)
    except HttpError:
        is_manager = False
    if not (is_manager or (allow_renter and is_renter)):
        raise HttpError(403, "Not allowed")
    bk.status = new_status
    fields = ['status', 'updated_at']
    if new_status == Booking.Status.CANCELLED:
        bk.cancelled_by = profile
        bk.cancel_note = (cancel_note or '').strip()[:255]
        fields += ['cancelled_by', 'cancel_note']
    bk.save(update_fields=fields)
    _publish_booking(bk, new_status.lower())

    # Notify the counterpart (off-page push). Walk-ins (renter is None) have no
    # platform renter to notify — the renter-facing pushes simply don't fire.
    if new_status == Booking.Status.CONFIRMED:
        if bk.renter_id and bk.renter.account_id != profile.account_id:
            _notify_async(notify_booking_confirmed, bk.renter.account, bk)
    elif new_status == Booking.Status.CANCELLED:
        if is_renter:
            # renter cancelled → tell the managers
            for acct in _manager_accounts(bk.bookable.item):
                if acct.id != profile.account_id:
                    _notify_async(notify_booking_cancelled, acct, bk)
        else:
            # manager cancelled → tell the renter (no-op for walk-ins)
            if bk.renter_id and bk.renter.account_id != profile.account_id:
                _notify_async(notify_booking_cancelled, bk.renter.account, bk)
    return _booking_response(bk)


@router.post('/bookings/{booking_id}/confirm', response={200: BookingResponse}, auth=ProfileAuth())
def confirm_booking(request, booking_id: str):
    return _transition(request, booking_id, Booking.Status.CONFIRMED, allow_renter=False)


@router.post('/bookings/{booking_id}/cancel', response={200: BookingResponse}, auth=ProfileAuth())
def cancel_booking(request, booking_id: str, data: BookingCancelRequest = None):
    note = data.note if data else ""
    series = bool(data and data.series)
    resp = _transition(request, booking_id, Booking.Status.CANCELLED, allow_renter=True, cancel_note=note)

    # "Cancel the whole series" → also cancel this occurrence's future siblings.
    # Permission rode in via _transition (same renter / same managed item); the
    # primary already pushed the counterpart, so siblings only refresh the live
    # calendar (no N-fold push spam).
    if series and resp.recurrence_group:
        profile = request.auth_profile
        siblings = (Booking.objects.select_related('bookable')
                    .filter(recurrence_group=resp.recurrence_group,
                            status__in=Booking.LIVE_STATUSES,
                            start__gte=resp.start)
                    .exclude(id=resp.id))
        for sib in siblings:
            sib.status = Booking.Status.CANCELLED
            sib.cancelled_by = profile
            sib.cancel_note = (note or '').strip()[:255]
            sib.save(update_fields=['status', 'cancelled_by', 'cancel_note', 'updated_at'])
            _publish_booking(sib, 'cancelled')
    return resp


@router.post('/bookings/{booking_id}/complete', response={200: BookingResponse}, auth=ProfileAuth())
def complete_booking(request, booking_id: str):
    # Completion returns the item to availability — it does NOT deactivate it
    # (contrast contract sale semantics).
    return _transition(request, booking_id, Booking.Status.COMPLETED, allow_renter=False)


@router.get('/bookings/mine', response={200: List[BookingResponse]}, auth=ProfileAuth())
def my_bookings(request):
    profile = request.auth_profile
    qs = (Booking.objects.select_related('bookable__item', 'renter')
          .filter(renter=profile).order_by('-created_at'))
    return [_booking_response(b) for b in qs]


@router.get('/bookings/inbox', response={200: List[BookingResponse]}, auth=ProfileAuth())
def bookings_inbox(request, item_id: str):
    profile = request.auth_profile
    item = _managed_item_or_403(item_id, profile)
    qs = (Booking.objects.select_related('bookable__item', 'renter')
          .filter(bookable__item_id=item.id).order_by('-created_at'))
    return [_booking_response(b) for b in qs]


def _managed_bookings_q(profile):
    """Q matching bookings on items the profile manages (P2P owner or org manager)."""
    return (Q(bookable__item__owner_id=profile.id) |
            Q(bookable__item__establishment_id__in=_managed_establishment_ids(profile)))


@router.get('/bookings/pending-count', response={200: dict}, auth=ProfileAuth())
def pending_count(request):
    """Count of REQUESTED bookings across items the current profile manages —
    drives the nav badge. AUTO-confirmed bookings need no action, so only
    REQUESTED (awaiting approval) counts."""
    profile = request.auth_profile
    count = (Booking.objects
             .filter(status=Booking.Status.REQUESTED)
             .filter(_managed_bookings_q(profile))
             .count())
    return {'count': count}


@router.get('/bookings/incoming', response={200: List[BookingResponse]}, auth=ProfileAuth())
def incoming_bookings(request):
    """Live bookings (REQUESTED + CONFIRMED) across all items the profile
    manages — the owner's aggregate inbox. REQUESTED first, then by start."""
    profile = request.auth_profile
    qs = (Booking.objects
          .select_related('bookable__item', 'renter')
          .filter(status__in=Booking.LIVE_STATUSES)
          .filter(_managed_bookings_q(profile))
          .annotate(_req_first=Case(
              When(status=Booking.Status.REQUESTED, then=0),
              default=1, output_field=IntegerField()))
          .order_by('_req_first', 'start'))
    return [_booking_response(b) for b in qs]


# Parameterized GET — MUST stay after the literal /bookings/* routes above.
@router.get('/bookings/{booking_id}', response={200: BookingResponse}, auth=ProfileAuth())
def get_booking(request, booking_id: str):
    """A single booking, for the renter, its creator, or a manager of its item.
    Backs the 'formalize → rental contract' prefill (period/deposit/price snapshot)."""
    profile = request.auth_profile
    try:
        bk = Booking.objects.select_related('bookable__item', 'renter').get(id=booking_id)
    except Booking.DoesNotExist:
        raise HttpError(404, "Booking not found")
    if not (bk.renter_id == profile.id or bk.created_by_id == profile.id
            or _can_manage_item(bk.bookable.item, profile)):
        raise HttpError(403, "Not authorized to view this booking")
    return _booking_response(bk)
