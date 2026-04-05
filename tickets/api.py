"""
Tickets API — unified ticketing for events and transit.
Purchase flow: initiate → pay via Lightning (client-side) → confirm with proof → use QR.
"""
import hashlib
import secrets
from datetime import timedelta
from typing import List, Optional

from django.db import models as db_models
from django.db.models import F
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from tickets.models import Ticket, TicketType

import logging

logger = logging.getLogger(__name__)

router = Router(tags=["Tickets"])


# ── Schemas ──────────────────────────────────────────────────────────

class TicketTypeOut(Schema):
    id: str
    object_type: str = 'ticket_type'
    category: str
    name: str
    description: str
    price_sats: int
    max_capacity: Optional[int]
    sold_count: int
    is_sold_out: bool
    is_active: bool
    # Context
    event_id: Optional[str]
    route_id: Optional[str]
    operator_id: str
    operator_name: str
    operator_ln_address: str
    operator_spark_address: str
    created_at: str

    @classmethod
    def from_obj(cls, tt: TicketType) -> 'TicketTypeOut':
        op = tt.operator
        return cls(
            id=tt.id,
            category=tt.category,
            name=tt.name,
            description=tt.description,
            price_sats=tt.price_sats,
            max_capacity=tt.max_capacity,
            sold_count=tt.sold_count,
            is_sold_out=tt.is_sold_out,
            is_active=tt.is_active,
            event_id=tt.event_id,
            route_id=tt.route_id,
            operator_id=op.id,
            operator_name=op.display_name,
            operator_ln_address=getattr(op, 'ln_address', '') or '',
            operator_spark_address=getattr(op, 'spark_address', '') or '',
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
    price_sats: int
    amount_paid_sats: int
    ln_payment_hash: str
    # Context
    event_id: Optional[str]
    event_title: Optional[str]
    route_id: Optional[str]
    route_name: Optional[str]
    operator_name: str
    buyer_id: str
    paid_at: Optional[str]
    used_at: Optional[str]
    expires_at: Optional[str]
    created_at: str

    @classmethod
    def from_obj(cls, t: Ticket) -> 'TicketOut':
        tt = t.ticket_type
        return cls(
            id=t.id,
            status=t.status,
            qr_token=t.qr_token,
            pgp_signature=t.pgp_signature,
            ticket_type_id=tt.id,
            ticket_type_name=tt.name,
            category=tt.category,
            price_sats=tt.price_sats,
            amount_paid_sats=t.amount_paid_sats,
            ln_payment_hash=t.ln_payment_hash,
            event_id=tt.event_id,
            event_title=tt.event.title if tt.event_id else None,
            route_id=tt.route_id,
            route_name=tt.route.short_name if tt.route_id else None,
            operator_name=tt.operator.display_name,
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
    message: str


# ── Request schemas ──────────────────────────────────────────────────

class TicketTypeCreateReq(Schema):
    category: str  # EVENT or TRANSIT
    name: str
    description: str = ''
    price_sats: int
    max_capacity: Optional[int] = None
    event_id: Optional[str] = None
    route_id: Optional[str] = None


class TicketTypeUpdateReq(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    price_sats: Optional[int] = None
    max_capacity: Optional[int] = None
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


# ── TicketType CRUD ──────────────────────────────────────────────────

@router.get('/types/', response=List[TicketTypeOut], auth=None)
@ratelimit(group='tickets:types_list', key='ip', rate='60/m')
def list_ticket_types(
    request,
    event_id: Optional[str] = None,
    route_id: Optional[str] = None,
    category: Optional[str] = None,
):
    """List active ticket types, optionally filtered."""
    qs = TicketType.objects.filter(is_active=True).select_related('operator')
    if event_id:
        qs = qs.filter(event_id=event_id)
    if route_id:
        qs = qs.filter(route_id=route_id)
    if category:
        qs = qs.filter(category=category)
    return [TicketTypeOut.from_obj(tt) for tt in qs]


@router.get('/types/{tt_id}/', response={200: TicketTypeOut, 404: dict}, auth=None)
@ratelimit(group='tickets:type_detail', key='ip', rate='60/m')
def get_ticket_type(request, tt_id: str):
    """Get ticket type detail."""
    try:
        tt = TicketType.objects.select_related('operator').get(id=tt_id)
    except TicketType.DoesNotExist:
        raise HttpError(404, "Ticket type not found")
    return TicketTypeOut.from_obj(tt)


@router.post('/types/', response={200: TicketTypeOut, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:type_create', key=user_or_ip, rate='10/m', method='POST')
def create_ticket_type(request, data: TicketTypeCreateReq):
    """Create a ticket type. Requires WoT 2+."""
    profile = request.auth_profile

    # WoT check (is_verified_wot = 3+ active verifications, same pattern as driver mode)
    if not profile.is_verified_wot and not profile.account.is_staff:
        raise HttpError(403, "WoT 2+ required to create ticket types")

    # Operator must have Lightning address
    if not profile.ln_address and not profile.spark_address:
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
        if not data.route_id:
            raise HttpError(400, "route_id required for TRANSIT tickets")
        from geo.models import Route
        try:
            Route.objects.get(id=data.route_id)
        except Route.DoesNotExist:
            raise HttpError(404, "Route not found")
    else:
        raise HttpError(400, "category must be EVENT or TRANSIT")

    if data.price_sats <= 0:
        raise HttpError(400, "price_sats must be positive")

    tt = TicketType.objects.create(
        category=data.category,
        name=data.name,
        description=data.description,
        price_sats=data.price_sats,
        max_capacity=data.max_capacity,
        event_id=data.event_id if data.category == 'EVENT' else None,
        route_id=data.route_id if data.category == 'TRANSIT' else None,
        operator=profile,
    )
    tt.refresh_from_db()
    return TicketTypeOut.from_obj(tt)


@router.put('/types/{tt_id}/', response={200: TicketTypeOut, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:type_update', key=user_or_ip, rate='10/m', method='PUT')
def update_ticket_type(request, tt_id: str, data: TicketTypeUpdateReq):
    """Update ticket type. Operator only."""
    profile = request.auth_profile
    try:
        tt = TicketType.objects.select_related('operator').get(id=tt_id)
    except TicketType.DoesNotExist:
        raise HttpError(404, "Ticket type not found")

    if tt.operator_id != profile.id and not profile.account.is_staff:
        raise HttpError(403, "Only operator can update")

    if data.name is not None:
        tt.name = data.name
    if data.description is not None:
        tt.description = data.description
    if data.price_sats is not None:
        if data.price_sats <= 0:
            raise HttpError(400, "price_sats must be positive")
        tt.price_sats = data.price_sats
    if data.max_capacity is not None:
        tt.max_capacity = data.max_capacity
    if data.is_active is not None:
        tt.is_active = data.is_active

    tt.save()
    return TicketTypeOut.from_obj(tt)


@router.delete('/types/{tt_id}/', auth=ProfileAuth(), response={200: dict, 403: dict, 404: dict})
@ratelimit(group='tickets:type_delete', key=user_or_ip, rate='10/m', method='DELETE')
def delete_ticket_type(request, tt_id: str):
    """Deactivate ticket type (soft delete). Operator only."""
    profile = request.auth_profile
    try:
        tt = TicketType.objects.get(id=tt_id)
    except TicketType.DoesNotExist:
        raise HttpError(404, "Ticket type not found")

    if tt.operator_id != profile.id and not profile.account.is_staff:
        raise HttpError(403, "Only operator can deactivate")

    tt.is_active = False
    tt.save(update_fields=['is_active', 'updated_at'])
    return {"ok": True}


# ── Purchase flow ────────────────────────────────────────────────────

PENDING_TTL_MINUTES = 15


@router.post('/purchase/', response={200: TicketOut, 403: dict, 404: dict, 409: dict, 429: dict}, auth=ProfileAuth())
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
        tt = TicketType.objects.select_related('operator').get(
            id=data.ticket_type_id, is_active=True,
        )
    except TicketType.DoesNotExist:
        raise HttpError(404, "Ticket type not found or inactive")

    if tt.is_sold_out:
        raise HttpError(409, "Sold out")

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
            'ticket_type', 'ticket_type__operator',
            'ticket_type__event', 'ticket_type__route',
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
    ticket.amount_paid_sats = ticket.ticket_type.price_sats
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
            'ticket_type', 'ticket_type__operator',
            'ticket_type__event', 'ticket_type__route',
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
        'ticket_type', 'ticket_type__operator',
        'ticket_type__event', 'ticket_type__route',
    ).order_by('-created_at')

    if status:
        qs = qs.filter(status=status)

    return [TicketOut.from_obj(t) for t in qs[:100]]


# ── Validation (scan QR) — MUST be before /{ticket_id}/ to avoid route collision ──

@router.post('/validate/', response=ValidateResult, auth=ProfileAuth())
@ratelimit(group='tickets:validate', key=user_or_ip, rate='30/m', method='POST')
def validate_ticket(request, data: ValidateReq):
    """
    Validate a ticket QR code. For drivers/event organizers.
    Marks ticket as USED if valid.
    """
    profile = request.auth_profile

    try:
        ticket = Ticket.objects.select_related(
            'ticket_type', 'ticket_type__operator', 'buyer',
        ).get(qr_token=data.qr_token)
    except Ticket.DoesNotExist:
        return ValidateResult(valid=False, message="Unknown ticket")

    # Only operator or staff can validate
    is_operator = ticket.ticket_type.operator_id == profile.id
    is_staff = profile.account.is_staff
    if not (is_operator or is_staff):
        return ValidateResult(valid=False, message="Not authorized to validate")

    if ticket.status == Ticket.Status.USED:
        return ValidateResult(
            valid=False,
            ticket_id=ticket.id,
            buyer_name=ticket.buyer.display_name,
            ticket_type_name=ticket.ticket_type.name,
            message=f"Already used at {ticket.used_at.strftime('%H:%M') if ticket.used_at else '?'}",
        )

    if ticket.status != Ticket.Status.ACTIVE:
        return ValidateResult(
            valid=False,
            ticket_id=ticket.id,
            message=f"Ticket is {ticket.status}",
        )

    # Mark as used
    now = timezone.now()
    ticket.status = Ticket.Status.USED
    ticket.used_at = now
    ticket.save(update_fields=['status', 'used_at', 'updated_at'])

    logger.info(f"Ticket {ticket.id} validated by {profile.display_name}")

    return ValidateResult(
        valid=True,
        ticket_id=ticket.id,
        buyer_name=ticket.buyer.display_name,
        ticket_type_name=ticket.ticket_type.name,
        message="Valid ticket",
    )


# ── Ticket detail (parameterized — MUST be after literal paths) ───

@router.get('/{ticket_id}/', response={200: TicketOut, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='tickets:detail', key=user_or_ip, rate='30/m')
def get_ticket(request, ticket_id: str):
    """Get ticket detail. Buyer or operator can view."""
    profile = request.auth_profile
    try:
        ticket = Ticket.objects.select_related(
            'ticket_type', 'ticket_type__operator',
            'ticket_type__event', 'ticket_type__route',
        ).get(id=ticket_id)
    except Ticket.DoesNotExist:
        raise HttpError(404, "Ticket not found")

    is_buyer = ticket.buyer_id == profile.id
    is_operator = ticket.ticket_type.operator_id == profile.id
    is_staff = profile.account.is_staff

    if not (is_buyer or is_operator or is_staff):
        raise HttpError(403, "Access denied")

    return TicketOut.from_obj(ticket)
