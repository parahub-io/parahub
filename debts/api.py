"""
Debts API Endpoints
Django Ninja REST API for debt tracking and clearing
"""

from ninja import Router, Schema
from ninja.errors import HttpError
from typing import List, Optional
from decimal import Decimal
from datetime import datetime
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
from debts.models import Debt, DebtRepayment
from parahub.auth import ProfileAuth
from parahub.crypto.pgp import verify_profile_signature
from parahub.ratelimit import ratelimit, user_or_ip
import logging

logger = logging.getLogger(__name__)

router = Router(tags=["Debts"])


def _build_timestamp_proof_dict(proof_obj) -> dict:
    batch = proof_obj.batch
    return {
        'created_at': proof_obj.created_at.isoformat(),
        'verified_at': batch.verified_at.isoformat() if batch and batch.verified_at else None,
        'bitcoin_block': batch.bitcoin_block if batch else None,
        'batch_id': proof_obj.batch_id,
        'pending': proof_obj.batch_id is None,
    }


# Schemas
class DebtCreateRequest(Schema):
    creditor_id: str
    debtor_id: str
    amount: Decimal
    currency: str = 'EUR'
    description: Optional[str] = None
    pgp_signature: str = ''
    signed_timestamp: str = ''


class DebtResponse(Schema):
    id: str
    object_type: str = 'debt'
    creditor_id: str
    creditor_display_name: str
    debtor_id: str
    debtor_display_name: str
    amount: Decimal
    remaining_amount: Decimal
    currency: str
    description: str
    status: str
    percent_settled: Decimal
    created_by_id: Optional[str]
    confirmed_by_creditor_at: Optional[datetime]
    confirmed_by_debtor_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    pgp_signature: str = ''
    timestamp_proof: Optional[dict] = None


class ConfirmDebtRequest(Schema):
    confirmed: bool
    pgp_signature: str = ''
    signed_timestamp: str = ''


class RepayDebtRequest(Schema):
    amount: Decimal
    notes: Optional[str] = None


class DebtRepaymentResponse(Schema):
    id: str
    object_type: str = 'debt_repayment'
    debt_id: str
    amount: Decimal
    repayment_type: str
    notes: str
    created_by_id: Optional[str]
    created_at: datetime


@router.post('/', response=DebtResponse, auth=ProfileAuth())
@ratelimit(group='debts:create', key=user_or_ip, rate='30/m', method='POST')
@transaction.atomic
def create_debt(request, data: DebtCreateRequest):
    """
    Create a new debt record

    Workflow:
    - Creator can be either debtor or creditor
    - Status starts as PENDING_CONFIRMATION
    - Other party must confirm via /debts/{id}/confirm/
    """
    profile = request.auth_profile

    # Validate parties exist
    from identity.models import Profile
    try:
        creditor = Profile.objects.get(id=data.creditor_id)
        debtor = Profile.objects.get(id=data.debtor_id)
    except Profile.DoesNotExist:
        raise HttpError(404, "Creditor or debtor not found")

    # Validate amount
    if data.amount <= 0:
        raise HttpError(400, "Amount must be positive")

    # PGP signature verification (mandatory if profile has key)
    verify_profile_signature(
        profile,
        {
            "action": "create_debt",
            "amount": str(data.amount),
            "creditor_id": data.creditor_id,
            "currency": data.currency,
            "debtor_id": data.debtor_id,
            "timestamp": data.signed_timestamp,
        },
        data.pgp_signature,
        data.signed_timestamp,
        error_prefix="Debt create PGP",
    )

    # Smart confirmation logic:
    # - If debtor creates debt: ACTIVE immediately (debtor admits debt)
    # - If creditor creates debt: PENDING (debtor must confirm)
    now = timezone.now()
    is_debtor_creator = profile.id == debtor.id

    debt = Debt.objects.create(
        creditor=creditor,
        debtor=debtor,
        amount=data.amount,
        currency=data.currency,
        description=data.description or '',
        created_by=profile,
        status=Debt.Status.ACTIVE if is_debtor_creator else Debt.Status.PENDING_CONFIRMATION,
        # Auto-confirm creator's side
        confirmed_by_creditor_at=now if profile.id == creditor.id else None,
        confirmed_by_debtor_at=now if profile.id == debtor.id else None,
        pgp_signature=data.pgp_signature,
        signed_payload={"timestamp": data.signed_timestamp} if data.signed_timestamp else {},
    )

    logger.info(f"Debt {debt.id} created by {profile.id}: {debtor.id} owes {creditor.id} {data.amount} {data.currency}")

    return DebtResponse(
        id=debt.id,
        creditor_id=debt.creditor_id,
        creditor_display_name=debt.creditor.display_name or debt.creditor.hna or '',
        debtor_id=debt.debtor_id,
        debtor_display_name=debt.debtor.display_name or debt.debtor.hna or '',
        amount=debt.amount,
        remaining_amount=debt.remaining_amount,
        currency=debt.currency,
        description=debt.description,
        status=debt.status,
        percent_settled=debt.percent_settled,
        created_by_id=debt.created_by_id,
        confirmed_by_creditor_at=debt.confirmed_by_creditor_at,
        confirmed_by_debtor_at=debt.confirmed_by_debtor_at,
        created_at=debt.created_at,
        updated_at=debt.updated_at,
        pgp_signature=debt.pgp_signature,
    )


@router.get('/', response=List[DebtResponse], auth=ProfileAuth())
@ratelimit(group='debts:list', key=user_or_ip, rate='30/m')
def list_debts(request, status: Optional[str] = None, mine_only: bool = False):
    """
    List debts

    Query params:
    - status: Filter by status (ACTIVE, PENDING_CONFIRMATION, etc.)
    - mine_only: Show only debts where I'm creditor or debtor
    """
    from django.contrib.contenttypes.models import ContentType
    from audit_log.models import TimestampProof

    profile = request.auth_profile

    queryset = Debt.objects.select_related('creditor', 'debtor', 'created_by')

    if mine_only:
        queryset = queryset.filter(Q(creditor=profile) | Q(debtor=profile))

    if status:
        queryset = queryset.filter(status=status)

    debt_list = list(queryset.order_by('-created_at')[:100])
    debt_ids = [d.id for d in debt_list]

    # Batch-load OTS proofs
    ct = ContentType.objects.get_for_model(Debt)
    proofs = {
        p.object_id: _build_timestamp_proof_dict(p)
        for p in TimestampProof.objects.select_related('batch').filter(
            content_type=ct, object_id__in=debt_ids
        )
    }

    return [
        DebtResponse(
            id=debt.id,
            creditor_id=debt.creditor_id,
            creditor_display_name=debt.creditor.display_name or debt.creditor.hna or '',
            debtor_id=debt.debtor_id,
            debtor_display_name=debt.debtor.display_name or debt.debtor.hna or '',
            amount=debt.amount,
            remaining_amount=debt.remaining_amount,
            currency=debt.currency,
            description=debt.description,
            status=debt.status,
            percent_settled=debt.percent_settled,
            created_by_id=debt.created_by_id,
            confirmed_by_creditor_at=debt.confirmed_by_creditor_at,
            confirmed_by_debtor_at=debt.confirmed_by_debtor_at,
            created_at=debt.created_at,
            updated_at=debt.updated_at,
            pgp_signature=debt.pgp_signature,
            timestamp_proof=proofs.get(debt.id),
        )
        for debt in debt_list
    ]


@router.get('/{debt_id}/', response=DebtResponse, auth=ProfileAuth())
@ratelimit(group='debts:detail', key=user_or_ip, rate='30/m')
def get_debt(request, debt_id: str):
    """Get debt details by ID"""
    from django.contrib.contenttypes.models import ContentType
    from audit_log.models import TimestampProof

    profile = request.auth_profile

    try:
        debt = Debt.objects.select_related('creditor', 'debtor', 'created_by').get(id=debt_id)
    except Debt.DoesNotExist:
        raise HttpError(404, "Debt not found")

    # Check permission (must be creditor or debtor)
    if debt.creditor_id != profile.id and debt.debtor_id != profile.id:
        raise HttpError(403, "You are not authorized to view this debt")

    ct = ContentType.objects.get_for_model(Debt)
    proof_obj = TimestampProof.objects.select_related('batch').filter(
        content_type=ct, object_id=debt.id
    ).first()
    timestamp_proof = _build_timestamp_proof_dict(proof_obj) if proof_obj else None

    return DebtResponse(
        id=debt.id,
        creditor_id=debt.creditor_id,
        creditor_display_name=debt.creditor.display_name or debt.creditor.hna or '',
        debtor_id=debt.debtor_id,
        debtor_display_name=debt.debtor.display_name or debt.debtor.hna or '',
        amount=debt.amount,
        remaining_amount=debt.remaining_amount,
        currency=debt.currency,
        description=debt.description,
        status=debt.status,
        percent_settled=debt.percent_settled,
        created_by_id=debt.created_by_id,
        confirmed_by_creditor_at=debt.confirmed_by_creditor_at,
        confirmed_by_debtor_at=debt.confirmed_by_debtor_at,
        created_at=debt.created_at,
        updated_at=debt.updated_at,
        pgp_signature=debt.pgp_signature,
        timestamp_proof=timestamp_proof,
    )


@router.post('/{debt_id}/confirm/', response=DebtResponse, auth=ProfileAuth())
@ratelimit(group='debts:confirm', key=user_or_ip, rate='30/m', method='POST')
@transaction.atomic
def confirm_debt(request, debt_id: str, data: ConfirmDebtRequest):
    """
    Confirm or reject debt

    - Creditor confirms: confirmed_by_creditor_at set
    - Debtor confirms: confirmed_by_debtor_at set
    - When both confirm: status -> ACTIVE
    - If either rejects: status -> CANCELLED
    """
    profile = request.auth_profile

    try:
        debt = Debt.objects.select_related('creditor', 'debtor').get(id=debt_id)
    except Debt.DoesNotExist:
        raise HttpError(404, "Debt not found")

    # Check permission
    is_creditor = debt.creditor_id == profile.id
    is_debtor = debt.debtor_id == profile.id

    if not (is_creditor or is_debtor):
        raise HttpError(403, "You are not authorized to confirm this debt")

    # PGP signature verification (mandatory if profile has key)
    verify_profile_signature(
        profile,
        {
            "action": "confirm_debt",
            "confirmed": data.confirmed,
            "debt_id": debt_id,
            "timestamp": data.signed_timestamp,
        },
        data.pgp_signature,
        data.signed_timestamp,
        error_prefix="Debt confirm PGP",
    )

    # Reject
    if not data.confirmed:
        debt.status = Debt.Status.CANCELLED
        debt.save()
        logger.info(f"Debt {debt.id} cancelled by {profile.id}")
    else:
        # Confirm
        now = timezone.now()

        if is_creditor and not debt.confirmed_by_creditor_at:
            debt.confirmed_by_creditor_at = now
        if is_debtor and not debt.confirmed_by_debtor_at:
            debt.confirmed_by_debtor_at = now

        # Both confirmed -> ACTIVE
        if debt.confirmed_by_creditor_at and debt.confirmed_by_debtor_at:
            debt.status = Debt.Status.ACTIVE
            logger.info(f"Debt {debt.id} activated (both parties confirmed)")

        debt.save()

    return DebtResponse(
        id=debt.id,
        creditor_id=debt.creditor_id,
        creditor_display_name=debt.creditor.display_name or debt.creditor.hna or '',
        debtor_id=debt.debtor_id,
        debtor_display_name=debt.debtor.display_name or debt.debtor.hna or '',
        amount=debt.amount,
        remaining_amount=debt.remaining_amount,
        currency=debt.currency,
        description=debt.description,
        status=debt.status,
        percent_settled=debt.percent_settled,
        created_by_id=debt.created_by_id,
        confirmed_by_creditor_at=debt.confirmed_by_creditor_at,
        confirmed_by_debtor_at=debt.confirmed_by_debtor_at,
        created_at=debt.created_at,
        updated_at=debt.updated_at,
        pgp_signature=debt.pgp_signature,
    )


@router.post('/{debt_id}/repay/', response=DebtRepaymentResponse, auth=ProfileAuth())
@ratelimit(group='debts:repay', key=user_or_ip, rate='30/m', method='POST')
@transaction.atomic
def create_repayment(request, debt_id: str, data: RepayDebtRequest):
    """
    Create manual repayment record (creditor only)

    Only creditor can record repayment.
    Debt is reduced immediately - no confirmation needed from debtor.
    """
    profile = request.auth_profile

    try:
        debt = Debt.objects.select_related('creditor', 'debtor').get(id=debt_id)
    except Debt.DoesNotExist:
        raise HttpError(404, "Debt not found")

    # Only creditor can record repayment
    if debt.creditor_id != profile.id:
        raise HttpError(403, "Only creditor can record repayment")

    # Validate amount
    if data.amount <= 0:
        raise HttpError(400, "Repayment amount must be positive")
    if data.amount > debt.remaining_amount:
        raise HttpError(400, f"Repayment amount ({data.amount}) exceeds remaining debt ({debt.remaining_amount})")

    # Create repayment
    repayment = DebtRepayment.objects.create(
        debt=debt,
        amount=data.amount,
        repayment_type=DebtRepayment.RepaymentType.MANUAL,
        notes=data.notes or '',
        created_by=profile
    )

    logger.info(f"Repayment {repayment.id} created for debt {debt.id} by {profile.id}: {data.amount} {debt.currency}")

    return DebtRepaymentResponse(
        id=repayment.id,
        debt_id=repayment.debt_id,
        amount=repayment.amount,
        repayment_type=repayment.repayment_type,
        notes=repayment.notes,
        created_by_id=repayment.created_by_id,
        created_at=repayment.created_at
    )


@router.get('/{debt_id}/repayments/', response=List[DebtRepaymentResponse], auth=ProfileAuth())
@ratelimit(group='debts:repayments', key=user_or_ip, rate='30/m')
def list_debt_repayments(request, debt_id: str):
    """List all repayments for a debt"""
    profile = request.auth_profile

    try:
        debt = Debt.objects.select_related('creditor', 'debtor').get(id=debt_id)
    except Debt.DoesNotExist:
        raise HttpError(404, "Debt not found")

    # Check permission
    if debt.creditor_id != profile.id and debt.debtor_id != profile.id:
        raise HttpError(403, "You are not authorized to view this debt's repayments")

    repayments = DebtRepayment.objects.filter(debt=debt).order_by('-created_at')

    return [
        DebtRepaymentResponse(
            id=rep.id,
            debt_id=rep.debt_id,
            amount=rep.amount,
            repayment_type=rep.repayment_type,
            notes=rep.notes,
            created_by_id=rep.created_by_id,
            created_at=rep.created_at
        )
        for rep in repayments
    ]


