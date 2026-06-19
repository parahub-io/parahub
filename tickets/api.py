"""
Tickets API — unified ticketing for events and transit.
Purchase flow: initiate → pay via Lightning (client-side) → confirm with proof → use QR.
"""
import csv
import hashlib
import io
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from django.db import models as db_models
from django.db.models import F
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from ninja import Field, Router, Schema
from ninja.errors import HttpError

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from tickets.models import Ticket, TicketType
from tickets.pricing import RateUnavailable, eur_to_sats, sats_per_eur
from tickets.qr_signing import build_qr_payload, public_key_b64

import logging

logger = logging.getLogger(__name__)

router = Router(tags=["Tickets"])


# ── Operator permissions ─────────────────────────────────────────────
# Personal types: the operator profile. Establishment types: membership roles.

MANAGE_ROLES = ('OWNER', 'ADMIN')
VALIDATE_ROLES = ('OWNER', 'ADMIN', 'EMPLOYEE', 'CONTRACTOR')


def _is_establishment_member(profile, establishment_id: str, roles) -> bool:
    from geo.models import EstablishmentMembership
    return EstablishmentMembership.objects.filter(
        profile_id=profile.id, establishment_id=establishment_id, role__in=roles,
    ).exists()


def _can_manage(tt: TicketType, profile) -> bool:
    """Edit/deactivate rights."""
    if profile.account.is_staff:
        return True
    if tt.operator_establishment_id:
        return _is_establishment_member(profile, tt.operator_establishment_id, MANAGE_ROLES)
    return tt.operator_id == profile.id


def _can_validate(tt: TicketType, profile) -> bool:
    """Scan/validate rights (also grants operator-side ticket detail view)."""
    if profile.account.is_staff:
        return True
    if tt.operator_establishment_id:
        return _is_establishment_member(profile, tt.operator_establishment_id, VALIDATE_ROLES)
    return tt.operator_id == profile.id


# ── Schemas ──────────────────────────────────────────────────────────

class TicketTypeOut(Schema):
    id: str
    object_type: str = 'ticket_type'
    category: str
    name: str
    description: str
    # Fixed sats price, or current quote for EUR-priced types (None if no rate)
    price_sats: Optional[int]
    price_eur: Optional[float]
    max_capacity: Optional[int]
    sold_count: int
    is_sold_out: bool
    is_active: bool
    validity_minutes: Optional[int]
    concession_category: str
    # Context
    event_id: Optional[str]
    route_id: Optional[str]
    agency_id: Optional[str]
    agency_name: Optional[str]
    operator_id: str
    operator_name: str
    operator_establishment_id: Optional[str]
    operator_ln_address: str
    operator_spark_address: str
    created_at: str

    @classmethod
    def from_obj(cls, tt: TicketType, eur_rate: Optional[Decimal] = None) -> 'TicketTypeOut':
        """eur_rate: pre-fetched sats_per_eur() — pass when serializing lists."""
        recipient = tt.payment_recipient
        if tt.price_eur is not None:
            rate = eur_rate if eur_rate is not None else sats_per_eur()
            price_sats = eur_to_sats(tt.price_eur, rate=rate)
        else:
            price_sats = tt.price_sats
        return cls(
            id=tt.id,
            category=tt.category,
            name=tt.name,
            description=tt.description,
            price_sats=price_sats,
            price_eur=float(tt.price_eur) if tt.price_eur is not None else None,
            max_capacity=tt.max_capacity,
            sold_count=tt.sold_count,
            is_sold_out=tt.is_sold_out,
            is_active=tt.is_active,
            validity_minutes=tt.validity_minutes,
            concession_category=tt.concession_category,
            event_id=tt.event_id,
            route_id=tt.route_id,
            agency_id=tt.agency_id,
            agency_name=tt.agency.name if tt.agency_id else None,
            operator_id=tt.operator_id,
            operator_name=tt.operator_display_name,
            operator_establishment_id=tt.operator_establishment_id,
            operator_ln_address=getattr(recipient, 'ln_address', '') or '',
            operator_spark_address=getattr(recipient, 'spark_address', '') or '',
            created_at=tt.created_at.isoformat(),
        )


class TicketOut(Schema):
    id: str
    object_type: str = 'ticket'
    status: str
    qr_token: str
    pgp_signature: str
    ticket_type_id: str
    ticket_type_name: str
    category: str
    # Sats locked at purchase (what the buyer pays/paid)
    price_sats: int
    amount_due_sats: int
    price_eur: Optional[float]
    amount_paid_sats: int
    ln_payment_hash: str
    # Usage window
    validity_minutes: Optional[int]
    valid_until: Optional[str]
    validation_count: int
    concession_category: str
    # Signed QR string for offline verification (active tickets only)
    qr_payload: Optional[str]
    # Refund flow
    refund_requested_at: Optional[str]
    refund_reason: str
    refunded_at: Optional[str]
    # Context
    event_id: Optional[str]
    event_title: Optional[str]
    route_id: Optional[str]
    route_name: Optional[str]
    agency_id: Optional[str]
    agency_name: Optional[str]
    operator_name: str
    buyer_id: str
    paid_at: Optional[str]
    used_at: Optional[str]
    expires_at: Optional[str]
    created_at: str

    @classmethod
    def from_obj(cls, t: Ticket) -> 'TicketOut':
        tt = t.ticket_type
        # Legacy tickets (pre amount_due_sats) fall back to the type's sats price
        due = t.amount_due_sats or tt.price_sats or 0
        price_eur = t.price_eur if t.price_eur is not None else tt.price_eur
        return cls(
            id=t.id,
            status=t.status,
            qr_token=t.qr_token,
            pgp_signature=t.pgp_signature,
            ticket_type_id=tt.id,
            ticket_type_name=tt.name,
            category=tt.category,
            price_sats=due,
            amount_due_sats=due,
            price_eur=float(price_eur) if price_eur is not None else None,
            amount_paid_sats=t.amount_paid_sats,
            ln_payment_hash=t.ln_payment_hash,
            validity_minutes=tt.validity_minutes,
            valid_until=t.valid_until.isoformat() if t.valid_until else None,
            validation_count=t.validation_count,
            concession_category=tt.concession_category,
            qr_payload=build_qr_payload(t) if t.status in (
                Ticket.Status.ACTIVE, Ticket.Status.VALIDATED,
            ) else None,
            refund_requested_at=t.refund_requested_at.isoformat() if t.refund_requested_at else None,
            refund_reason=t.refund_reason,
            refunded_at=t.refunded_at.isoformat() if t.refunded_at else None,
            event_id=tt.event_id,
            event_title=tt.event.title if tt.event_id else None,
            route_id=tt.route_id,
            route_name=tt.route.short_name if tt.route_id else None,
            agency_id=tt.agency_id,
            agency_name=tt.agency.name if tt.agency_id else None,
            operator_name=tt.operator_display_name,
            buyer_id=t.buyer_id,
            paid_at=t.paid_at.isoformat() if t.paid_at else None,
            used_at=t.used_at.isoformat() if t.used_at else None,
            expires_at=t.expires_at.isoformat() if t.expires_at else None,
            created_at=t.created_at.isoformat(),
        )


class ValidateResult(Schema):
    valid: bool
    ticket_id: Optional[str] = None
    buyer_name: Optional[str] = None
    ticket_type_name: Optional[str] = None
    valid_until: Optional[str] = None
    validation_count: Optional[int] = None
    concession_category: Optional[str] = None
    message: str


# ── Request schemas ──────────────────────────────────────────────────

class TicketTypeCreateReq(Schema):
    category: str  # EVENT or TRANSIT
    name: str
    description: str = ''
    # Exactly one of price_sats / price_eur
    price_sats: Optional[int] = None
    price_eur: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    max_capacity: Optional[int] = None
    validity_minutes: Optional[int] = None  # null = one-shot
    concession_category: str = ''
    event_id: Optional[str] = None
    # TRANSIT target: exactly one of route_id / agency_id (agency = network-wide)
    route_id: Optional[str] = None
    agency_id: Optional[str] = None
    operator_establishment_id: Optional[str] = None


class TicketTypeUpdateReq(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    # Setting one price mode clears the other
    price_sats: Optional[int] = None
    price_eur: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    max_capacity: Optional[int] = None
    validity_minutes: Optional[int] = None  # 0 clears (back to one-shot)
    concession_category: Optional[str] = None  # '' clears
    is_active: Optional[bool] = None


class PurchaseReq(Schema):
    ticket_type_id: str


class ConfirmReq(Schema):
    ticket_id: str
    ln_payment_hash: str
    ln_preimage: str


class SignReq(Schema):
    pgp_signature: str


class ValidateReq(Schema):
    qr_token: str


class SyncItem(Schema):
    qr_token: str
    scanned_at: datetime


class SyncReq(Schema):
    items: List[SyncItem] = Field(..., max_length=200)


class SyncResultItem(Schema):
    qr_token: str
    valid: bool
    message: str


class RefundRequestReq(Schema):
    reason: str = ''


class RefundResolveReq(Schema):
    action: str  # 'refund' | 'reject'
    payment_hash: str = ''  # optional LN proof of the send-back


# ── TicketType CRUD ──────────────────────────────────────────────────

@router.get('/types/', response=List[TicketTypeOut], auth=None)
@ratelimit(group='tickets:types_list', key='ip', rate='60/m')
def list_ticket_types(
    request,
    event_id: Optional[str] = None,
    route_id: Optional[str] = None,
    agency_id: Optional[str] = None,
    category: Optional[str] = None,
):
    """List active ticket types, optionally filtered.

    route_id filter also returns network-wide (agency) types of that
    route's agency, so route pages offer passes alongside single rides.
    """
    qs = TicketType.objects.filter(is_active=True).select_related(
        'operator', 'operator_establishment', 'agency',
    )
    if event_id:
        qs = qs.filter(event_id=event_id)
    if route_id:
        from geo.models import Route
        route_agency_ids = Route.objects.filter(id=route_id).values_list('agency_id', flat=True)
        qs = qs.filter(
            db_models.Q(route_id=route_id) | db_models.Q(agency_id__in=route_agency_ids)
        )
    if agency_id:
        qs = qs.filter(agency_id=agency_id)
    if category:
        qs = qs.filter(category=category)
    eur_rate = sats_per_eur()
    return [TicketTypeOut.from_obj(tt, eur_rate=eur_rate) for tt in qs]


@router.get('/types/{tt_id}/', response={200: TicketTypeOut, 404: dict}, auth=None)
@ratelimit(group='tickets:type_detail', key='ip', rate='60/m')
def get_ticket_type(request, tt_id: str):
    """Get ticket type detail."""
    try:
        tt = TicketType.objects.select_related(
            'operator', 'operator_establishment', 'agency',
        ).get(id=tt_id)
    except TicketType.DoesNotExist:
        raise HttpError(404, "Ticket type not found")
    return TicketTypeOut.from_obj(tt)


@router.post('/types/', response={200: TicketTypeOut, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:type_create', key=user_or_ip, rate='10/m', method='POST')
def create_ticket_type(request, data: TicketTypeCreateReq):
    """Create a ticket type. Requires WoT 3+."""
    profile = request.auth_profile

    # WoT check (is_verified_wot = 3+ active verifications, same pattern as driver mode)
    if not profile.is_verified_wot and not profile.account.is_staff:
        raise HttpError(403, "WoT 3+ required to create ticket types")

    # Operator: establishment (org-operated) or personal profile
    establishment = None
    if data.operator_establishment_id:
        from geo.models import Establishment
        try:
            establishment = Establishment.objects.get(id=data.operator_establishment_id)
        except Establishment.DoesNotExist:
            raise HttpError(404, "Establishment not found")
        if not profile.account.is_staff and not _is_establishment_member(
            profile, establishment.id, MANAGE_ROLES,
        ):
            raise HttpError(403, "Must be OWNER or ADMIN of the establishment")
        if not establishment.ln_address and not establishment.spark_address:
            raise HttpError(400, "Establishment needs a Lightning/Spark payment address first")
    elif not profile.ln_address and not profile.spark_address:
        raise HttpError(400, "Set up a Lightning address in your profile first")

    # Validate category + target
    if data.category == 'EVENT':
        if not data.event_id:
            raise HttpError(400, "event_id required for EVENT tickets")
        from geo.models import Event
        try:
            Event.objects.get(id=data.event_id)
        except Event.DoesNotExist:
            raise HttpError(404, "Event not found")
    elif data.category == 'TRANSIT':
        if bool(data.route_id) == bool(data.agency_id):
            raise HttpError(400, "Provide exactly one of route_id or agency_id for TRANSIT tickets")
        if data.route_id:
            from geo.models import Route
            try:
                Route.objects.get(id=data.route_id)
            except Route.DoesNotExist:
                raise HttpError(404, "Route not found")
        else:
            from geo.models import Agency
            try:
                Agency.objects.get(id=data.agency_id)
            except Agency.DoesNotExist:
                raise HttpError(404, "Agency not found")
    else:
        raise HttpError(400, "category must be EVENT or TRANSIT")

    if data.validity_minutes is not None and data.validity_minutes <= 0:
        raise HttpError(400, "validity_minutes must be positive")

    if data.concession_category and data.concession_category not in TicketType.ConcessionCategory.values:
        raise HttpError(400, "Invalid concession_category")

    # Exactly one pricing mode
    if (data.price_sats is None) == (data.price_eur is None):
        raise HttpError(400, "Provide exactly one of price_sats or price_eur")
    if data.price_sats is not None and data.price_sats <= 0:
        raise HttpError(400, "price_sats must be positive")
    if data.price_eur is not None and data.price_eur <= 0:
        raise HttpError(400, "price_eur must be positive")

    tt = TicketType.objects.create(
        category=data.category,
        name=data.name,
        description=data.description,
        price_sats=data.price_sats,
        price_eur=data.price_eur,
        max_capacity=data.max_capacity,
        validity_minutes=data.validity_minutes,
        concession_category=data.concession_category,
        event_id=data.event_id if data.category == 'EVENT' else None,
        route_id=data.route_id if data.category == 'TRANSIT' else None,
        agency_id=data.agency_id if data.category == 'TRANSIT' else None,
        operator=profile,
        operator_establishment=establishment,
    )
    tt.refresh_from_db()
    return TicketTypeOut.from_obj(tt)


@router.put('/types/{tt_id}/', response={200: TicketTypeOut, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:type_update', key=user_or_ip, rate='10/m', method='PUT')
def update_ticket_type(request, tt_id: str, data: TicketTypeUpdateReq):
    """Update ticket type. Operator (or establishment OWNER/ADMIN) only."""
    profile = request.auth_profile
    try:
        tt = TicketType.objects.select_related(
            'operator', 'operator_establishment',
        ).get(id=tt_id)
    except TicketType.DoesNotExist:
        raise HttpError(404, "Ticket type not found")

    if not _can_manage(tt, profile):
        raise HttpError(403, "Only operator can update")

    if data.name is not None:
        tt.name = data.name
    if data.description is not None:
        tt.description = data.description
    if data.price_sats is not None and data.price_eur is not None:
        raise HttpError(400, "Provide only one of price_sats or price_eur")
    if data.price_sats is not None:
        if data.price_sats <= 0:
            raise HttpError(400, "price_sats must be positive")
        tt.price_sats = data.price_sats
        tt.price_eur = None
    if data.price_eur is not None:
        if data.price_eur <= 0:
            raise HttpError(400, "price_eur must be positive")
        tt.price_eur = data.price_eur
        tt.price_sats = None
    if data.validity_minutes is not None:
        # 0 clears the window (back to one-shot)
        tt.validity_minutes = data.validity_minutes or None
    if data.concession_category is not None:
        if data.concession_category and data.concession_category not in TicketType.ConcessionCategory.values:
            raise HttpError(400, "Invalid concession_category")
        tt.concession_category = data.concession_category
    if data.max_capacity is not None:
        tt.max_capacity = data.max_capacity
    if data.is_active is not None:
        tt.is_active = data.is_active

    tt.save()
    return TicketTypeOut.from_obj(tt)


@router.delete('/types/{tt_id}/', auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='tickets:type_delete', key=user_or_ip, rate='10/m', method='DELETE')
def delete_ticket_type(request, tt_id: str):
    """Deactivate ticket type (soft delete). Operator (or establishment OWNER/ADMIN) only."""
    profile = request.auth_profile
    try:
        tt = TicketType.objects.get(id=tt_id)
    except TicketType.DoesNotExist:
        raise HttpError(404, "Ticket type not found")

    if not _can_manage(tt, profile):
        raise HttpError(403, "Only operator can deactivate")

    tt.is_active = False
    tt.save(update_fields=['is_active', 'updated_at'])
    return {"ok": True}


# ── Purchase flow ────────────────────────────────────────────────────

PENDING_TTL_MINUTES = 15


@router.post('/purchase/', response={200: TicketOut, 403: dict, 404: dict, 409: dict, 429: dict, 503: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:purchase', key=user_or_ip, rate='10/m', method='POST')
def purchase_ticket(request, data: PurchaseReq):
    """
    Initiate ticket purchase.
    Creates PENDING_PAYMENT ticket. Client pays operator via Lightning,
    then calls /confirm/ with payment proof.
    """
    profile = request.auth_profile

    # WoT 1+ to purchase (at least 1 active verification)
    has_verification = profile.received_verifications.filter(is_active=True).exists()
    if not has_verification and not profile.account.is_staff:
        raise HttpError(403, "WoT 1+ required to purchase tickets")

    try:
        tt = TicketType.objects.select_related(
            'operator', 'operator_establishment',
        ).get(id=data.ticket_type_id, is_active=True)
    except TicketType.DoesNotExist:
        raise HttpError(404, "Ticket type not found or inactive")

    if tt.is_sold_out:
        raise HttpError(409, "Sold out")

    # Lock the sats amount now (EUR types: quote at current rate, valid for the TTL)
    if tt.price_eur is not None:
        try:
            amount_due = eur_to_sats(tt.price_eur, strict=True)
        except RateUnavailable:
            raise HttpError(503, "EUR exchange rate unavailable — try again later")
    else:
        amount_due = tt.price_sats or 0

    # Cleanup expired pending tickets for this buyer + type
    Ticket.objects.filter(
        buyer=profile,
        ticket_type=tt,
        status=Ticket.Status.PENDING_PAYMENT,
        expires_at__lt=timezone.now(),
    ).update(status=Ticket.Status.EXPIRED)

    # Rate limit: max 5 pending per hour
    recent_pending = Ticket.objects.filter(
        buyer=profile,
        status=Ticket.Status.PENDING_PAYMENT,
        created_at__gte=timezone.now() - timedelta(hours=1),
    ).count()
    if recent_pending >= 5:
        raise HttpError(429, "Too many pending purchases. Complete or wait.")

    ticket = Ticket.objects.create(
        ticket_type=tt,
        buyer=profile,
        amount_due_sats=amount_due,
        price_eur=tt.price_eur,
        expires_at=timezone.now() + timedelta(minutes=PENDING_TTL_MINUTES),
    )
    ticket.refresh_from_db()
    return TicketOut.from_obj(ticket)


@router.post('/confirm/', response={200: TicketOut, 400: dict, 404: dict, 409: dict, 410: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:confirm', key=user_or_ip, rate='10/m', method='POST')
def confirm_payment(request, data: ConfirmReq):
    """
    Confirm Lightning payment with proof.
    Verifies SHA256(preimage) == payment_hash, transitions to ACTIVE.
    """
    profile = request.auth_profile

    try:
        ticket = Ticket.objects.select_related(
            'ticket_type', 'ticket_type__operator', 'ticket_type__operator_establishment',
            'ticket_type__event', 'ticket_type__route', 'ticket_type__agency',
        ).get(id=data.ticket_id, buyer=profile)
    except Ticket.DoesNotExist:
        raise HttpError(404, "Ticket not found")

    if ticket.status != Ticket.Status.PENDING_PAYMENT:
        raise HttpError(400, f"Ticket is {ticket.status}, expected PENDING_PAYMENT")

    if ticket.expires_at and ticket.expires_at < timezone.now():
        ticket.status = Ticket.Status.EXPIRED
        ticket.save(update_fields=['status', 'updated_at'])
        raise HttpError(410, "Ticket expired")

    # Verify preimage: SHA256(preimage_bytes) == payment_hash
    try:
        preimage_bytes = bytes.fromhex(data.ln_preimage)
        expected_hash = hashlib.sha256(preimage_bytes).hexdigest()
    except (ValueError, TypeError):
        raise HttpError(400, "Invalid preimage format")

    if expected_hash != data.ln_payment_hash:
        raise HttpError(400, "Preimage does not match payment hash")

    # Check duplicate payment hash
    if Ticket.objects.filter(
        ln_payment_hash=data.ln_payment_hash,
        status=Ticket.Status.ACTIVE,
    ).exists():
        raise HttpError(409, "Payment hash already used")

    now = timezone.now()
    ticket.status = Ticket.Status.ACTIVE
    ticket.ln_payment_hash = data.ln_payment_hash
    ticket.ln_preimage = data.ln_preimage
    ticket.amount_paid_sats = ticket.amount_due_sats or ticket.ticket_type.price_sats or 0
    ticket.paid_at = now
    ticket.save(update_fields=[
        'status', 'ln_payment_hash', 'ln_preimage',
        'amount_paid_sats', 'paid_at', 'updated_at',
    ])

    # Increment sold_count
    TicketType.objects.filter(id=ticket.ticket_type_id).update(
        sold_count=F('sold_count') + 1,
    )

    logger.info(f"Ticket {ticket.id} confirmed for {profile.display_name}")
    return TicketOut.from_obj(ticket)


@router.patch('/{ticket_id}/sign/', response={200: TicketOut, 400: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:sign', key=user_or_ip, rate='30/m', method='PATCH')
def sign_ticket(request, ticket_id: str, data: SignReq):
    """Attach PGP signature to ticket (buyer only)."""
    profile = request.auth_profile

    try:
        ticket = Ticket.objects.select_related(
            'ticket_type', 'ticket_type__operator', 'ticket_type__operator_establishment',
            'ticket_type__event', 'ticket_type__route', 'ticket_type__agency',
        ).get(id=ticket_id, buyer=profile)
    except Ticket.DoesNotExist:
        raise HttpError(404, "Ticket not found")

    if ticket.status not in (Ticket.Status.ACTIVE, Ticket.Status.PENDING_PAYMENT):
        raise HttpError(400, "Cannot sign a used/cancelled ticket")

    ticket.pgp_signature = data.pgp_signature
    ticket.save(update_fields=['pgp_signature', 'updated_at'])
    return TicketOut.from_obj(ticket)


# ── My tickets ───────────────────────────────────────────────────────

@router.get('/my/', response=List[TicketOut], auth=ProfileAuth())
@ratelimit(group='tickets:my', key=user_or_ip, rate='30/m')
def my_tickets(request, status: Optional[str] = None):
    """List buyer's tickets."""
    profile = request.auth_profile
    qs = Ticket.objects.filter(buyer=profile).select_related(
        'ticket_type', 'ticket_type__operator', 'ticket_type__operator_establishment',
        'ticket_type__event', 'ticket_type__route', 'ticket_type__agency',
    ).order_by('-created_at')

    if status:
        qs = qs.filter(status=status)

    return [TicketOut.from_obj(t) for t in qs[:100]]


# ── Validation (scan QR) — MUST be before /{ticket_id}/ to avoid route collision ──

def _apply_validation(ticket: Ticket, profile, now) -> ValidateResult:
    """Validation state machine, shared by /validate/ and /validate/sync/.

    `now` is the scan moment — timezone.now() for live scans, the (clamped)
    device timestamp for offline scans synced later.
    """
    if not _can_validate(ticket.ticket_type, profile):
        return ValidateResult(valid=False, message="Not authorized to validate")

    tt = ticket.ticket_type

    def _result(valid, message, **extra):
        return ValidateResult(
            valid=valid,
            ticket_id=ticket.id,
            buyer_name=ticket.buyer.display_name,
            ticket_type_name=tt.name,
            valid_until=ticket.valid_until.isoformat() if ticket.valid_until else None,
            validation_count=ticket.validation_count,
            concession_category=tt.concession_category or None,
            message=message,
            **extra,
        )

    if ticket.status == Ticket.Status.USED:
        return _result(False, f"Already used at {ticket.used_at.strftime('%H:%M') if ticket.used_at else '?'}")

    # Windowed ticket already activated: valid until the window closes
    if ticket.status == Ticket.Status.VALIDATED:
        if ticket.valid_until and now <= ticket.valid_until:
            ticket.validation_count = F('validation_count') + 1
            ticket.save(update_fields=['validation_count', 'updated_at'])
            ticket.refresh_from_db(fields=['validation_count'])
            return _result(True, f"Valid until {timezone.localtime(ticket.valid_until).strftime('%H:%M')}")
        expired_str = timezone.localtime(ticket.valid_until).strftime('%H:%M') if ticket.valid_until else '?'
        return _result(False, f"Validity window ended at {expired_str}")

    if ticket.status != Ticket.Status.ACTIVE:
        return ValidateResult(
            valid=False,
            ticket_id=ticket.id,
            message=f"Ticket is {ticket.status}",
        )

    # First validation
    ticket.used_at = now
    ticket.validation_count = 1
    if tt.validity_minutes:
        ticket.status = Ticket.Status.VALIDATED
        ticket.valid_until = now + timedelta(minutes=tt.validity_minutes)
        ticket.save(update_fields=['status', 'used_at', 'valid_until', 'validation_count', 'updated_at'])
        message = f"Valid until {timezone.localtime(ticket.valid_until).strftime('%H:%M')}"
    else:
        ticket.status = Ticket.Status.USED
        ticket.save(update_fields=['status', 'used_at', 'validation_count', 'updated_at'])
        message = "Valid ticket"

    logger.info(f"Ticket {ticket.id} validated by {profile.display_name}")
    return _result(True, message)


_VALIDATE_SELECT_RELATED = (
    'ticket_type', 'ticket_type__operator', 'ticket_type__operator_establishment', 'buyer',
)


@router.post('/validate/', response=ValidateResult, auth=ProfileAuth())
@ratelimit(group='tickets:validate', key=user_or_ip, rate='30/m', method='POST')
def validate_ticket(request, data: ValidateReq):
    """
    Validate a ticket QR code. For drivers/event organizers.
    One-shot tickets become USED; windowed tickets VALIDATED until window end.
    """
    profile = request.auth_profile
    try:
        ticket = Ticket.objects.select_related(*_VALIDATE_SELECT_RELATED).get(qr_token=data.qr_token)
    except Ticket.DoesNotExist:
        return ValidateResult(valid=False, message="Unknown ticket")
    return _apply_validation(ticket, profile, timezone.now())


SYNC_MAX_AGE_DAYS = 7


@router.post('/validate/sync/', response=List[SyncResultItem], auth=ProfileAuth())
@ratelimit(group='tickets:validate_sync', key=user_or_ip, rate='10/m', method='POST')
def validate_sync(request, data: SyncReq):
    """
    Replay offline scans queued by the scanner. Each item runs through the
    normal state machine at its (clamped) scan timestamp; oldest first, so a
    windowed ticket activated offline gets the correct retroactive window.
    """
    profile = request.auth_profile
    now = timezone.now()
    oldest_allowed = now - timedelta(days=SYNC_MAX_AGE_DAYS)

    results = []
    for item in sorted(data.items, key=lambda i: i.scanned_at):
        scanned_at = item.scanned_at
        if timezone.is_naive(scanned_at):
            scanned_at = timezone.make_aware(scanned_at)
        scanned_at = min(max(scanned_at, oldest_allowed), now)
        try:
            ticket = Ticket.objects.select_related(*_VALIDATE_SELECT_RELATED).get(qr_token=item.qr_token)
        except Ticket.DoesNotExist:
            results.append(SyncResultItem(qr_token=item.qr_token, valid=False, message="Unknown ticket"))
            continue
        verdict = _apply_validation(ticket, profile, scanned_at)
        results.append(SyncResultItem(
            qr_token=item.qr_token, valid=verdict.valid, message=verdict.message,
        ))
    return results


@router.get('/qr-pubkey/', auth=None)
@ratelimit(group='tickets:qr_pubkey', key='ip', rate='30/m')
def qr_pubkey(request):
    """Ed25519 public key for offline QR signature verification."""
    return {'alg': 'ed25519', 'version': 1, 'key': public_key_b64()}


# ── Operator dashboard (sales reporting) ────────────────────────────

PAID_STATUSES = (Ticket.Status.ACTIVE, Ticket.Status.VALIDATED, Ticket.Status.USED)
MAX_STATS_DAYS = 366
CSV_ROW_CAP = 10000


class OperatorContextOut(Schema):
    establishment_id: Optional[str]  # null = personal operator
    name: str
    types_count: int


class DailyStat(Schema):
    date: str
    count: int
    sats: int


class TypeStat(Schema):
    id: str
    name: str
    target: str
    count: int
    sats: int
    eur: float


class OperatorStatsOut(Schema):
    total_sold: int
    revenue_sats: int
    # Sum of EUR price snapshots (EUR-priced tickets only)
    revenue_eur: float
    daily: List[DailyStat]
    by_type: List[TypeStat]


def _operator_types(profile, establishment_id: Optional[str]):
    """TicketType queryset for an operator context. 403 if not allowed."""
    if establishment_id:
        if not profile.account.is_staff and not _is_establishment_member(
            profile, establishment_id, MANAGE_ROLES,
        ):
            raise HttpError(403, "Not a manager of this establishment")
        return TicketType.objects.filter(operator_establishment_id=establishment_id)
    return TicketType.objects.filter(operator=profile, operator_establishment__isnull=True)


def _paid_tickets(profile, establishment_id: Optional[str], days: int):
    days = max(1, min(days, MAX_STATS_DAYS))
    since = timezone.now() - timedelta(days=days)
    return Ticket.objects.filter(
        ticket_type__in=_operator_types(profile, establishment_id),
        status__in=PAID_STATUSES,
        paid_at__gte=since,
    )


def _target_name(route_name, agency_name, event_title):
    return route_name or agency_name or event_title or ''


@router.get('/operator/contexts/', response=List[OperatorContextOut], auth=ProfileAuth())
@ratelimit(group='tickets:op_contexts', key=user_or_ip, rate='30/m')
def operator_contexts(request):
    """Operator contexts for the dashboard: personal + managed establishments."""
    profile = request.auth_profile
    from geo.models import EstablishmentMembership
    out = [OperatorContextOut(
        establishment_id=None,
        name=profile.display_name,
        types_count=TicketType.objects.filter(
            operator=profile, operator_establishment__isnull=True,
        ).count(),
    )]
    memberships = EstablishmentMembership.objects.filter(
        profile=profile, role__in=MANAGE_ROLES,
    ).select_related('establishment')
    for m in memberships:
        out.append(OperatorContextOut(
            establishment_id=m.establishment_id,
            name=m.establishment.name,
            types_count=TicketType.objects.filter(
                operator_establishment_id=m.establishment_id,
            ).count(),
        ))
    return out


@router.get('/operator/stats/', response={200: OperatorStatsOut, 403: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:op_stats', key=user_or_ip, rate='30/m')
def operator_stats(request, days: int = 30, establishment_id: Optional[str] = None):
    """Sales stats for an operator context (paid tickets only)."""
    profile = request.auth_profile
    qs = _paid_tickets(profile, establishment_id, days)

    totals = qs.aggregate(
        count=db_models.Count('id'),
        sats=db_models.Sum('amount_paid_sats'),
        eur=db_models.Sum('price_eur'),
    )

    daily = qs.annotate(day=TruncDate('paid_at')).values('day').annotate(
        count=db_models.Count('id'),
        sats=db_models.Sum('amount_paid_sats'),
    ).order_by('day')

    by_type = qs.values(
        'ticket_type_id', 'ticket_type__name',
        'ticket_type__route__short_name',
        'ticket_type__agency__name',
        'ticket_type__event__title',
    ).annotate(
        count=db_models.Count('id'),
        sats=db_models.Sum('amount_paid_sats'),
        eur=db_models.Sum('price_eur'),
    ).order_by('-count')

    return OperatorStatsOut(
        total_sold=totals['count'] or 0,
        revenue_sats=totals['sats'] or 0,
        revenue_eur=float(totals['eur'] or 0),
        daily=[DailyStat(
            date=row['day'].isoformat(), count=row['count'], sats=row['sats'] or 0,
        ) for row in daily],
        by_type=[TypeStat(
            id=row['ticket_type_id'],
            name=row['ticket_type__name'],
            target=_target_name(
                row['ticket_type__route__short_name'],
                row['ticket_type__agency__name'],
                row['ticket_type__event__title'],
            ),
            count=row['count'],
            sats=row['sats'] or 0,
            eur=float(row['eur'] or 0),
        ) for row in by_type],
    )


class ValidableTypeOut(Schema):
    id: str
    name: str


@router.get('/operator/validable-types/', response=List[ValidableTypeOut], auth=ProfileAuth())
@ratelimit(group='tickets:op_validable', key=user_or_ip, rate='30/m')
def validable_types(request):
    """Active types the user may validate — cached by the scanner for offline mode."""
    profile = request.auth_profile
    from geo.models import EstablishmentMembership
    est_ids = list(EstablishmentMembership.objects.filter(
        profile=profile, role__in=VALIDATE_ROLES,
    ).values_list('establishment_id', flat=True))
    qs = TicketType.objects.filter(
        db_models.Q(operator=profile, operator_establishment__isnull=True) |
        db_models.Q(operator_establishment_id__in=est_ids),
        is_active=True,
    ).values('id', 'name')
    return [ValidableTypeOut(id=r['id'], name=r['name']) for r in qs]


class RefundRequestOut(Schema):
    ticket_id: str
    ticket_type_name: str
    buyer_name: str
    buyer_ln_address: str
    buyer_spark_address: str
    amount_paid_sats: int
    price_eur: Optional[float]
    reason: str
    requested_at: Optional[str]


@router.get('/operator/refunds/', response={200: List[RefundRequestOut], 403: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:op_refunds', key=user_or_ip, rate='30/m')
def operator_refunds(request, establishment_id: Optional[str] = None):
    """Pending refund requests for an operator context."""
    profile = request.auth_profile
    tickets = Ticket.objects.filter(
        ticket_type__in=_operator_types(profile, establishment_id),
        status=Ticket.Status.REFUND_REQUESTED,
    ).select_related('buyer', 'ticket_type').order_by('refund_requested_at')
    return [RefundRequestOut(
        ticket_id=t.id,
        ticket_type_name=t.ticket_type.name,
        buyer_name=t.buyer.display_name,
        buyer_ln_address=t.buyer.ln_address or '',
        buyer_spark_address=getattr(t.buyer, 'spark_address', '') or '',
        amount_paid_sats=t.amount_paid_sats,
        price_eur=float(t.price_eur) if t.price_eur is not None else None,
        reason=t.refund_reason,
        requested_at=t.refund_requested_at.isoformat() if t.refund_requested_at else None,
    ) for t in tickets[:200]]


@router.get('/operator/sales.csv', response={403: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:op_csv', key=user_or_ip, rate='10/m')
def operator_sales_csv(request, days: int = 30, establishment_id: Optional[str] = None):
    """Sales export for accounting (paid tickets, newest first, capped)."""
    profile = request.auth_profile
    qs = _paid_tickets(profile, establishment_id, days).select_related(
        'ticket_type', 'ticket_type__route', 'ticket_type__agency', 'ticket_type__event',
    ).order_by('-paid_at')[:CSV_ROW_CAP]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['paid_at', 'ticket_id', 'type', 'target', 'status', 'amount_sats', 'price_eur'])
    for t in qs:
        tt = t.ticket_type
        writer.writerow([
            t.paid_at.isoformat() if t.paid_at else '',
            t.id,
            tt.name,
            _target_name(
                tt.route.short_name if tt.route_id else None,
                tt.agency.name if tt.agency_id else None,
                tt.event.title if tt.event_id else None,
            ),
            t.status,
            t.amount_paid_sats,
            t.price_eur if t.price_eur is not None else '',
        ])
    return HttpResponse(
        buf.getvalue(),
        content_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="ticket-sales.csv"'},
    )


# ── Ticket detail (parameterized — MUST be after literal paths) ───

@router.get('/{ticket_id}/', response={200: TicketOut, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:detail', key=user_or_ip, rate='30/m')
def get_ticket(request, ticket_id: str):
    """Get ticket detail. Buyer or operator can view."""
    profile = request.auth_profile
    try:
        ticket = Ticket.objects.select_related(
            'ticket_type', 'ticket_type__operator', 'ticket_type__operator_establishment',
            'ticket_type__event', 'ticket_type__route', 'ticket_type__agency',
        ).get(id=ticket_id)
    except Ticket.DoesNotExist:
        raise HttpError(404, "Ticket not found")

    is_buyer = ticket.buyer_id == profile.id
    if not is_buyer and not _can_validate(ticket.ticket_type, profile):
        raise HttpError(403, "Access denied")

    return TicketOut.from_obj(ticket)


# ── Refunds (manual Lightning send-back by operator; NO ESCROW) ─────

def _get_buyer_ticket(ticket_id: str, profile) -> Ticket:
    try:
        return Ticket.objects.select_related(
            'ticket_type', 'ticket_type__operator', 'ticket_type__operator_establishment',
            'ticket_type__event', 'ticket_type__route', 'ticket_type__agency',
        ).get(id=ticket_id, buyer=profile)
    except Ticket.DoesNotExist:
        raise HttpError(404, "Ticket not found")


@router.post('/{ticket_id}/refund-request/', response={200: TicketOut, 400: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:refund_request', key=user_or_ip, rate='10/m', method='POST')
def request_refund(request, ticket_id: str, data: RefundRequestReq):
    """Buyer requests a refund. Unused (ACTIVE) tickets only."""
    profile = request.auth_profile
    ticket = _get_buyer_ticket(ticket_id, profile)
    if ticket.status != Ticket.Status.ACTIVE:
        raise HttpError(400, "Only unused (active) tickets can be refunded")
    ticket.status = Ticket.Status.REFUND_REQUESTED
    ticket.refund_requested_at = timezone.now()
    ticket.refund_reason = data.reason[:1000]
    ticket.save(update_fields=['status', 'refund_requested_at', 'refund_reason', 'updated_at'])
    return TicketOut.from_obj(ticket)


@router.post('/{ticket_id}/refund-cancel/', response={200: TicketOut, 400: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:refund_cancel', key=user_or_ip, rate='10/m', method='POST')
def cancel_refund_request(request, ticket_id: str):
    """Buyer withdraws a pending refund request — ticket becomes usable again."""
    profile = request.auth_profile
    ticket = _get_buyer_ticket(ticket_id, profile)
    if ticket.status != Ticket.Status.REFUND_REQUESTED:
        raise HttpError(400, "No pending refund request")
    ticket.status = Ticket.Status.ACTIVE
    ticket.refund_requested_at = None
    ticket.refund_reason = ''
    ticket.save(update_fields=['status', 'refund_requested_at', 'refund_reason', 'updated_at'])
    return TicketOut.from_obj(ticket)


@router.post('/{ticket_id}/refund-resolve/', response={200: TicketOut, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:refund_resolve', key=user_or_ip, rate='30/m', method='POST')
def resolve_refund(request, ticket_id: str, data: RefundResolveReq):
    """Operator resolves a refund request.

    'refund' = sats were sent back manually → CANCELLED (frees capacity);
    'reject' = back to ACTIVE.
    """
    profile = request.auth_profile
    try:
        ticket = Ticket.objects.select_related(
            'ticket_type', 'ticket_type__operator', 'ticket_type__operator_establishment',
            'ticket_type__event', 'ticket_type__route', 'ticket_type__agency',
        ).get(id=ticket_id)
    except Ticket.DoesNotExist:
        raise HttpError(404, "Ticket not found")

    if not _can_manage(ticket.ticket_type, profile):
        raise HttpError(403, "Only operator managers can resolve refunds")
    if ticket.status != Ticket.Status.REFUND_REQUESTED:
        raise HttpError(400, "No pending refund request")

    if data.action == 'refund':
        ticket.status = Ticket.Status.CANCELLED
        ticket.refunded_at = timezone.now()
        ticket.refund_payment_hash = data.payment_hash[:64]
        ticket.save(update_fields=['status', 'refunded_at', 'refund_payment_hash', 'updated_at'])
        # Free the seat
        TicketType.objects.filter(id=ticket.ticket_type_id, sold_count__gt=0).update(
            sold_count=F('sold_count') - 1,
        )
        logger.info(f"Ticket {ticket.id} refunded by {profile.display_name}")
    elif data.action == 'reject':
        ticket.status = Ticket.Status.ACTIVE
        ticket.save(update_fields=['status', 'updated_at'])
    else:
        raise HttpError(400, "action must be 'refund' or 'reject'")

    return TicketOut.from_obj(ticket)
