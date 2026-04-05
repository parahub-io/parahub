"""
Contracts API Endpoints
Django Ninja REST API for P2P contract signing with PGP signatures
"""

from ninja import Router, Schema
from ninja.errors import HttpError
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from django.utils import timezone
from django.db.models import Q, Avg, Count, F, Sum, ExpressionWrapper, DurationField
from django.db import transaction
from identity.models import Contract, Profile, ArbiterProfile, ArbitrationVerdict
from market.models import Item
from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from parahub.crypto.pgp import pgp_crypto, PGPVerificationError
from identity.arbitration_service import (
    create_arbitration_room, post_verdict_to_room, post_escalation_to_room
)
import logging
import asyncio
import threading

logger = logging.getLogger(__name__)

router = Router(tags=["Contracts"])


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
class ContractItemResponse(Schema):
    id: str
    title: str
    type: str


class ContractCreateRequest(Schema):
    partner_id: str
    title: str
    file_sha256: str
    arbiter_id: Optional[str] = None  # Optional arbitrator
    signature: str  # PGP signature of creator signing canonical JSON
    item_ids: Optional[List[str]] = None  # Items linked to this contract
    world_object_id: Optional[str] = None  # WorldObject this contract pertains to


class ContractSignRequest(Schema):
    signature: str  # PGP signature of partner signing canonical JSON


class ContractCompleteRequest(Schema):
    review_text: Optional[str] = None
    rating: Optional[int] = None  # 1-5 stars


class VerdictSubmitRequest(Schema):
    verdict_type: str  # FAVOR_CREATOR / FAVOR_PARTNER / PARTIAL / DISMISSED
    summary: str
    amount_awarded: Optional[Decimal] = None
    currency: Optional[str] = None


class RateArbiterRequest(Schema):
    rating: int  # 1-5


class VerdictResponse(Schema):
    id: str
    object_type: str = 'verdict'
    contract_id: str
    arbiter_id: str
    arbiter_display_name: str
    verdict_type: str
    summary: str
    amount_awarded: Optional[Decimal] = None
    currency: str = ''
    creator_arbiter_rating: Optional[int] = None
    partner_arbiter_rating: Optional[int] = None
    created_at: datetime


class ArbiterProfileResponse(Schema):
    profile_id: str
    display_name: str
    hna: str
    bio: str = ''
    fee_amount: Optional[Decimal] = None
    fee_currency: str = 'EUR'
    is_active: bool = True
    specializations: List[dict] = []
    avg_rating: Optional[float] = None
    total_cases: int = 0


class ContractResponse(Schema):
    id: str
    object_type: str = 'contract'
    creator_id: str
    creator_display_name: str
    partner_id: str
    partner_display_name: str
    arbiter_id: Optional[str] = None
    arbiter_display_name: Optional[str] = None
    title: str
    file_sha256: str
    status: str
    creator_signed_at: datetime
    partner_signed_at: Optional[datetime]
    creator_completed_at: Optional[datetime] = None
    partner_completed_at: Optional[datetime] = None
    arbitration_room_id: Optional[str] = None
    arbitration_initiated_at: Optional[datetime] = None
    arbitration_initiator_id: Optional[str] = None
    arbitration_level: int = 1
    arbitration_escalated_at: Optional[datetime] = None
    verdict: Optional[VerdictResponse] = None
    items: List[ContractItemResponse] = []
    world_object_id: Optional[str] = None
    world_object_label: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    timestamp_proof: Optional[dict] = None


def _build_verdict_response(verdict):
    """Build VerdictResponse from an ArbitrationVerdict instance."""
    return VerdictResponse(
        id=verdict.id,
        contract_id=verdict.contract_id,
        arbiter_id=verdict.arbiter_id,
        arbiter_display_name=verdict.arbiter.display_name or verdict.arbiter.hna or '',
        verdict_type=verdict.verdict_type,
        summary=verdict.summary,
        amount_awarded=verdict.amount_awarded,
        currency=verdict.currency or '',
        creator_arbiter_rating=verdict.creator_arbiter_rating,
        partner_arbiter_rating=verdict.partner_arbiter_rating,
        created_at=verdict.created_at,
    )


def _build_contract_response(contract, timestamp_proof=None):
    """Build ContractResponse from a Contract instance."""
    items = [
        ContractItemResponse(id=item.id, title=item.title, type=item.type)
        for item in contract.items.all()
    ]

    # Build verdict if exists (use prefetched if available)
    verdict_data = None
    try:
        verdict = getattr(contract, '_prefetched_verdict', None) or contract.verdict
        if verdict:
            verdict_data = _build_verdict_response(verdict)
    except ArbitrationVerdict.DoesNotExist:
        pass

    return ContractResponse(
        id=contract.id,
        creator_id=contract.creator_id,
        creator_display_name=contract.creator.display_name or contract.creator.hna or '',
        partner_id=contract.partner_id,
        partner_display_name=contract.partner.display_name or contract.partner.hna or '',
        arbiter_id=contract.arbiter_id,
        arbiter_display_name=contract.arbiter.display_name or contract.arbiter.hna or '' if contract.arbiter else None,
        title=contract.title,
        file_sha256=contract.file_sha256,
        status=contract.status,
        creator_signed_at=contract.creator_signed_at,
        partner_signed_at=contract.partner_signed_at,
        creator_completed_at=contract.creator_completed_at,
        partner_completed_at=contract.partner_completed_at,
        arbitration_room_id=contract.arbitration_room_id,
        arbitration_initiated_at=contract.arbitration_initiated_at,
        arbitration_initiator_id=contract.arbitration_initiator_id,
        arbitration_level=contract.arbitration_level,
        arbitration_escalated_at=contract.arbitration_escalated_at,
        verdict=verdict_data,
        items=items,
        world_object_id=contract.world_object_id,
        world_object_label=(
            contract.world_object.full_address or contract.world_object.xeno_id
            if contract.world_object else None
        ),
        created_at=contract.created_at,
        updated_at=contract.updated_at,
        timestamp_proof=timestamp_proof,
    )


# ============================================================
# LITERAL PATH ENDPOINTS (must come BEFORE parameterized ones)
# ============================================================

@router.get('/arbiter-profiles/', response=List[ArbiterProfileResponse], auth=ProfileAuth())
@ratelimit(group='contracts:arbiter_list', key=user_or_ip, rate='30/m')
def list_arbiter_profiles(request):
    """List active arbiter profiles with avg rating and total cases."""
    arbiters = ArbiterProfile.objects.filter(
        is_active=True
    ).select_related('profile').prefetch_related('specializations')

    results = []
    for ap in arbiters:
        # Compute avg rating and total cases from verdicts
        stats = ArbitrationVerdict.objects.filter(
            arbiter=ap.profile
        ).aggregate(
            avg_creator=Avg('creator_arbiter_rating'),
            avg_partner=Avg('partner_arbiter_rating'),
            total=Count('id'),
        )
        # Average of both ratings (where available)
        ratings = [v for v in [stats['avg_creator'], stats['avg_partner']] if v is not None]
        avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None

        specs = [
            {'id': cat.id, 'name': cat.name, 'slug': cat.slug}
            for cat in ap.specializations.all()
        ]

        results.append(ArbiterProfileResponse(
            profile_id=ap.profile_id,
            display_name=ap.profile.display_name or ap.profile.hna or '',
            hna=ap.profile.hna or '',
            bio=ap.bio,
            fee_amount=ap.fee_amount,
            fee_currency=ap.fee_currency,
            is_active=ap.is_active,
            specializations=specs,
            avg_rating=avg_rating,
            total_cases=stats['total'],
        ))

    return results


@router.get('/arbiter-profiles/{profile_id}/', response={200: ArbiterProfileResponse, 404: dict}, auth=ProfileAuth())
@ratelimit(group='contracts:arbiter_detail', key=user_or_ip, rate='30/m')
def get_arbiter_profile(request, profile_id: str):
    """Get single arbiter profile detail."""
    try:
        ap = ArbiterProfile.objects.select_related('profile').prefetch_related(
            'specializations'
        ).get(profile_id=profile_id)
    except ArbiterProfile.DoesNotExist:
        raise HttpError(404, "Arbiter profile not found")

    stats = ArbitrationVerdict.objects.filter(
        arbiter=ap.profile
    ).aggregate(
        avg_creator=Avg('creator_arbiter_rating'),
        avg_partner=Avg('partner_arbiter_rating'),
        total=Count('id'),
    )
    ratings = [v for v in [stats['avg_creator'], stats['avg_partner']] if v is not None]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None

    specs = [
        {'id': cat.id, 'name': cat.name, 'slug': cat.slug}
        for cat in ap.specializations.all()
    ]

    return ArbiterProfileResponse(
        profile_id=ap.profile_id,
        display_name=ap.profile.display_name or ap.profile.hna or '',
        hna=ap.profile.hna or '',
        bio=ap.bio,
        fee_amount=ap.fee_amount,
        fee_currency=ap.fee_currency,
        is_active=ap.is_active,
        specializations=specs,
        avg_rating=avg_rating,
        total_cases=stats['total'],
    )


class ArbiterStatsResponse(Schema):
    profile_id: str
    display_name: str
    hna: str
    total_cases: int = 0
    avg_rating: Optional[float] = None
    rating_count: int = 0
    rating_distribution: dict = {}
    verdict_breakdown: dict = {}
    escalation_rate: float = 0.0
    avg_resolution_days: Optional[float] = None
    total_awarded: Optional[Decimal] = None
    recent_verdicts: List[dict] = []


@router.get('/arbiter-profiles/{profile_id}/stats/', response={200: ArbiterStatsResponse, 404: dict}, auth=ProfileAuth())
@ratelimit(group='contracts:arbiter_stats', key=user_or_ip, rate='30/m')
def get_arbiter_stats(request, profile_id: str):
    """Detailed transparent statistics for an arbiter."""
    try:
        ap = ArbiterProfile.objects.select_related('profile').get(profile_id=profile_id)
    except ArbiterProfile.DoesNotExist:
        raise HttpError(404, "Arbiter profile not found")

    verdicts = ArbitrationVerdict.objects.filter(arbiter=ap.profile)

    # Verdict breakdown by type
    breakdown_qs = verdicts.values('verdict_type').annotate(count=Count('id'))
    verdict_breakdown = {row['verdict_type']: row['count'] for row in breakdown_qs}
    total_cases = sum(verdict_breakdown.values())

    # Rating distribution (1-5 stars, both parties)
    rating_dist = {str(i): 0 for i in range(1, 6)}
    rating_count = 0
    for field in ['creator_arbiter_rating', 'partner_arbiter_rating']:
        dist_qs = verdicts.filter(**{f'{field}__isnull': False}).values(field).annotate(count=Count('id'))
        for row in dist_qs:
            rating_dist[str(row[field])] += row['count']
            rating_count += row['count']

    # Average rating
    all_ratings_sum = sum(int(k) * v for k, v in rating_dist.items())
    avg_rating = round(all_ratings_sum / rating_count, 2) if rating_count else None

    # Escalation rate: contracts where this arbiter was assigned and level > 1
    arbiter_contracts = Contract.objects.filter(arbiter=ap.profile, arbitration_room_id__isnull=False)
    total_arbitrations = arbiter_contracts.count()
    escalated = arbiter_contracts.filter(arbitration_level__gt=1).count()
    escalation_rate = round(escalated / total_arbitrations, 2) if total_arbitrations else 0.0

    # Average resolution time (verdict.created_at - contract.arbitration_initiated_at)
    resolution_qs = verdicts.filter(
        contract__arbitration_initiated_at__isnull=False
    ).annotate(
        resolution=ExpressionWrapper(
            F('created_at') - F('contract__arbitration_initiated_at'),
            output_field=DurationField()
        )
    )
    avg_resolution_days = None
    if resolution_qs.exists():
        total_seconds = sum(
            v.resolution.total_seconds() for v in resolution_qs if v.resolution
        )
        avg_resolution_days = round(total_seconds / resolution_qs.count() / 86400, 1)

    # Total awarded
    total_awarded = verdicts.aggregate(total=Sum('amount_awarded'))['total']

    # Recent verdicts (last 10)
    recent = verdicts.select_related('contract').order_by('-created_at')[:10]
    recent_verdicts = [
        {
            'contract_id': v.contract_id,
            'contract_title': v.contract.title,
            'verdict_type': v.verdict_type,
            'amount_awarded': str(v.amount_awarded) if v.amount_awarded else None,
            'currency': v.currency or '',
            'created_at': v.created_at.isoformat(),
        }
        for v in recent
    ]

    return ArbiterStatsResponse(
        profile_id=ap.profile_id,
        display_name=ap.profile.display_name or ap.profile.hna or '',
        hna=ap.profile.hna or '',
        total_cases=total_cases,
        avg_rating=avg_rating,
        rating_count=rating_count,
        rating_distribution=rating_dist,
        verdict_breakdown=verdict_breakdown,
        escalation_rate=escalation_rate,
        avg_resolution_days=avg_resolution_days,
        total_awarded=total_awarded,
        recent_verdicts=recent_verdicts,
    )


@router.get('/clause-template/', response={200: dict}, auth=ProfileAuth())
@ratelimit(group='contracts:clause_template', key=user_or_ip, rate='30/m')
def get_clause_template(request, type: str = 'ad_hoc', city: str = 'Lisboa',
                        arbiter_name: str = '', lang: str = 'pt'):
    """Generate arbitration clause text.

    Query params:
    - type: ad_hoc | institutional | escalated
    - city: City for arbitration seat (default: Lisboa)
    - arbiter_name: Arbiter name (for ad_hoc/escalated)
    - lang: Language code (pt, en, es, fr, de, ru)
    """
    from identity.clause_templates import generate_clause

    if type not in ('ad_hoc', 'institutional', 'escalated'):
        raise HttpError(400, "Invalid clause type. Use: ad_hoc, institutional, escalated")

    clause = generate_clause(type, lang=lang, arbiter_name=arbiter_name, city=city)
    return {'clause_type': type, 'language': lang, 'text': clause}


# ============================================================
# CRUD + ACTION ENDPOINTS (parameterized paths)
# ============================================================

@router.post('/', response={200: ContractResponse, 400: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='contracts:create', key=user_or_ip, rate='10/m', method='POST')
def create_contract(request, data: ContractCreateRequest):
    """
    Create a new contract with creator's PGP signature

    Workflow:
    1. Creator uploads file (client-side), computes SHA256
    2. Creator signs canonical JSON with PGP
    3. Contract created with status PENDING_PARTNER
    4. Partner receives notification via WebSocket
    5. Partner signs via /contracts/{id}/sign/
    """
    creator = request.auth_profile

    # Validate partner exists
    try:
        partner = Profile.objects.get(id=data.partner_id)
    except Profile.DoesNotExist:
        raise HttpError(404, "Partner not found")

    # Cannot create contract with yourself
    if creator.id == partner.id:
        raise HttpError(400, "Cannot create contract with yourself")

    # Validate arbiter if specified
    arbiter = None
    if data.arbiter_id:
        try:
            arbiter = Profile.objects.get(id=data.arbiter_id)
        except Profile.DoesNotExist:
            raise HttpError(404, "Arbiter not found")

        # Arbiter cannot be creator or partner
        if arbiter.id in [creator.id, partner.id]:
            raise HttpError(400, "Arbiter cannot be creator or partner")

    # Validate title
    if not data.title or len(data.title.strip()) == 0:
        raise HttpError(400, "Title is required")

    # Validate SHA256 format (64 hex chars)
    if not data.file_sha256 or len(data.file_sha256) != 64:
        raise HttpError(400, "Invalid SHA256 hash format")

    # Verify creator has PGP key first
    if not creator.pgp_public_key:
        raise HttpError(400, "Creator must have PGP key uploaded")

    # Use transaction to rollback on signature verification failure
    with transaction.atomic():
        # Create contract (will generate ULID and created_at)
        contract = Contract(
            creator=creator,
            partner=partner,
            arbiter=arbiter,
            title=data.title.strip(),
            file_sha256=data.file_sha256.lower(),
            creator_signature=data.signature,
            status=Contract.Status.PENDING_PARTNER
        )

        # Need to save first to get created_at timestamp
        contract.save()

        # Now verify creator's PGP signature
        try:
            canonical_text = contract.get_canonical_text()
            is_valid = pgp_crypto.verify_signature(
                canonical_text,
                data.signature,
                creator.pgp_public_key
            )
            if not is_valid:
                raise HttpError(400, "Invalid PGP signature")
        except PGPVerificationError as e:
            logger.error(f"PGP verification failed: {e}")
            raise HttpError(400, f"PGP verification failed: {str(e)}")

    # Link WorldObject if provided
    if data.world_object_id:
        from geo.models import WorldObject
        try:
            wo = WorldObject.objects.get(id=data.world_object_id)
            contract.world_object = wo
            contract.save(update_fields=['world_object_id'])
        except WorldObject.DoesNotExist:
            raise HttpError(404, "WorldObject not found")

    # Link items if provided
    if data.item_ids:
        items = Item.objects.filter(
            id__in=data.item_ids,
            owner__in=[creator, partner],
            is_active=True
        )
        contract.items.set(items)

    logger.info(f"Contract {contract.id} created by {creator.id} for partner {partner.id}")

    return _build_contract_response(contract)


@router.get('/', response=List[ContractResponse], auth=ProfileAuth())
@ratelimit(group='contracts:list', key=user_or_ip, rate='30/m')
def list_contracts(request, status: Optional[str] = None):
    """
    List contracts where current user is creator or partner

    Query params:
    - status: Filter by status (PENDING_PARTNER, SIGNED, etc.)
    """
    from django.contrib.contenttypes.models import ContentType
    from audit_log.models import TimestampProof

    profile = request.auth_profile

    queryset = Contract.objects.select_related(
        'creator', 'partner', 'arbiter', 'world_object', 'world_object'
    ).prefetch_related('items').filter(
        Q(creator=profile) | Q(partner=profile)
    )

    if status:
        queryset = queryset.filter(status=status)

    contract_list = list(queryset.order_by('-created_at')[:100])
    contract_ids = [c.id for c in contract_list]

    # Batch-load OTS proofs (with batch fallback)
    ct = ContentType.objects.get_for_model(Contract)
    proofs = {
        p.object_id: _build_timestamp_proof_dict(p)
        for p in TimestampProof.objects.select_related('batch').filter(
            content_type=ct, object_id__in=contract_ids
        )
    }

    # Batch-load verdicts
    verdicts = {
        v.contract_id: v
        for v in ArbitrationVerdict.objects.select_related('arbiter').filter(
            contract_id__in=contract_ids
        )
    }
    # Attach verdicts to contracts for _build_contract_response
    for c in contract_list:
        if c.id in verdicts:
            # Pre-cache the verdict on the contract to avoid extra queries
            c._prefetched_verdict = verdicts[c.id]

    return [
        _build_contract_response(contract, proofs.get(contract.id))
        for contract in contract_list
    ]


@router.get('/{contract_id}/', response={200: ContractResponse, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='contracts:detail', key=user_or_ip, rate='30/m')
def get_contract(request, contract_id: str):
    """
    Get contract details

    Only creator or partner can view
    """
    from django.contrib.contenttypes.models import ContentType
    from audit_log.models import TimestampProof

    profile = request.auth_profile

    try:
        contract = Contract.objects.select_related(
            'creator', 'partner', 'arbiter', 'world_object'
        ).prefetch_related('items').get(id=contract_id)
    except Contract.DoesNotExist:
        raise HttpError(404, "Contract not found")

    # Only creator or partner can view
    if profile.id not in [contract.creator_id, contract.partner_id]:
        raise HttpError(403, "You are not authorized to view this contract")

    ct = ContentType.objects.get_for_model(Contract)
    proof_obj = TimestampProof.objects.select_related('batch').filter(
        content_type=ct, object_id=contract.id
    ).first()
    timestamp_proof = _build_timestamp_proof_dict(proof_obj) if proof_obj else None

    return _build_contract_response(contract, timestamp_proof)


@router.post('/{contract_id}/sign/', response={200: ContractResponse, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='contracts:sign', key=user_or_ip, rate='10/m', method='POST')
def sign_contract(request, contract_id: str, data: ContractSignRequest):
    """
    Partner signs the contract

    Only partner can sign. After signing, status becomes SIGNED.
    """
    partner = request.auth_profile

    try:
        contract = Contract.objects.select_related(
            'creator', 'partner', 'arbiter', 'world_object'
        ).prefetch_related('items').get(id=contract_id)
    except Contract.DoesNotExist:
        raise HttpError(404, "Contract not found")

    # Only partner can sign
    if partner.id != contract.partner_id:
        raise HttpError(403, "Only partner can sign this contract")

    # Check if already signed
    if contract.status == Contract.Status.SIGNED:
        raise HttpError(400, "Contract is already signed")

    # Verify partner's PGP signature
    canonical_text = contract.get_canonical_text()

    if not partner.pgp_public_key:
        raise HttpError(400, "Partner must have PGP key uploaded")

    try:
        is_valid = pgp_crypto.verify_signature(
            canonical_text,
            data.signature,
            partner.pgp_public_key
        )
        if not is_valid:
            raise HttpError(400, "Invalid PGP signature")
    except PGPVerificationError as e:
        logger.error(f"PGP verification failed: {e}")
        raise HttpError(400, f"PGP verification failed: {str(e)}")

    # Update contract
    contract.partner_signature = data.signature
    contract.partner_signed_at = timezone.now()
    contract.status = Contract.Status.SIGNED
    contract.save()

    logger.info(f"Contract {contract.id} signed by partner {partner.id}")

    return _build_contract_response(contract)


@router.delete('/{contract_id}/', response={200: dict, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='contracts:cancel', key=user_or_ip, rate='10/m', method='DELETE')
def cancel_contract(request, contract_id: str):
    """
    Cancel/reject contract

    - Creator can cancel PENDING_PARTNER contracts
    - Partner can reject PENDING_PARTNER contracts
    - Signed contracts cannot be cancelled (must complete or dispute)
    """
    profile = request.auth_profile

    try:
        contract = Contract.objects.get(id=contract_id)
    except Contract.DoesNotExist:
        raise HttpError(404, "Contract not found")

    # Only creator or partner can cancel
    if profile.id not in [contract.creator_id, contract.partner_id]:
        raise HttpError(403, "Only creator or partner can cancel this contract")

    # Can only cancel pending contracts
    if contract.status != Contract.Status.PENDING_PARTNER:
        raise HttpError(400, "Can only cancel contracts pending signature")

    # Update status to cancelled
    contract.status = Contract.Status.CANCELLED
    contract.save()

    action = "cancelled" if profile.id == contract.creator_id else "rejected"
    logger.info(f"Contract {contract.id} {action} by {profile.id}")

    return {"message": f"Contract {action} successfully", "contract_id": contract.id}


@router.post('/{contract_id}/complete/', response={200: ContractResponse, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='contracts:complete', key=user_or_ip, rate='10/m', method='POST')
def complete_contract(request, contract_id: str, data: ContractCompleteRequest):
    """
    Mark contract as completed and optionally leave a review

    Only creator or partner can complete. After completion, status becomes COMPLETED.
    """
    profile = request.auth_profile

    try:
        contract = Contract.objects.select_related(
            'creator', 'partner', 'arbiter', 'world_object'
        ).prefetch_related('items').get(id=contract_id)
    except Contract.DoesNotExist:
        raise HttpError(404, "Contract not found")

    # Only creator or partner can complete
    if profile.id not in [contract.creator_id, contract.partner_id]:
        raise HttpError(403, "Only creator or partner can complete this contract")

    # Must be signed first
    if contract.status not in [Contract.Status.SIGNED, Contract.Status.COMPLETED]:
        raise HttpError(400, "Contract must be signed before completion")

    # Determine which party is completing
    is_creator = profile.id == contract.creator_id
    is_partner = profile.id == contract.partner_id

    # Check if already completed by this party
    if is_creator and contract.creator_completed_at:
        raise HttpError(400, "You have already marked this contract as completed")
    if is_partner and contract.partner_completed_at:
        raise HttpError(400, "You have already marked this contract as completed")

    # Update completion timestamp
    now = timezone.now()
    if is_creator:
        contract.creator_completed_at = now
    else:
        contract.partner_completed_at = now

    # Check if both parties completed → change status to COMPLETED
    if contract.creator_completed_at and contract.partner_completed_at:
        contract.status = Contract.Status.COMPLETED

    contract.save()

    # Auto-deactivate linked items when contract is fully completed
    if contract.status == Contract.Status.COMPLETED:
        contract.items.filter(is_active=True).update(is_active=False)

    # Create contract review if provided
    if data.review_text or data.rating:
        from identity.models import ContractReview

        # Determine who to review (the other party)
        reviewed_profile = contract.partner if is_creator else contract.creator

        # Check if review already exists
        existing_review = ContractReview.objects.filter(
            contract=contract,
            reviewer=profile
        ).first()

        if not existing_review:
            ContractReview.objects.create(
                contract=contract,
                reviewer=profile,
                reviewed=reviewed_profile,
                rating=data.rating or 5,
                comment=data.review_text or ''
            )
            logger.info(f"Contract review created: {profile.id} → {reviewed_profile.id} for contract {contract.id}")

    logger.info(f"Contract {contract.id} completed by {profile.id} (creator={contract.creator_completed_at is not None}, partner={contract.partner_completed_at is not None})")

    return _build_contract_response(contract)


@router.post('/{contract_id}/initiate_arbitration/', response={200: ContractResponse, 400: dict, 403: dict, 404: dict, 500: dict}, auth=ProfileAuth())
@ratelimit(group='contracts:arbitration', key=user_or_ip, rate='5/m', method='POST')
def initiate_arbitration(request, contract_id: str):
    """
    Initiate arbitration for a signed contract by creating Matrix room.

    Creates E2E encrypted Matrix room with creator, partner, and arbiter.
    Posts contract details and pinned message with dispute info.

    Only creator or partner can initiate. Contract must be SIGNED and have arbiter.
    """
    profile = request.auth_profile

    try:
        contract = Contract.objects.select_related(
            'creator', 'partner', 'arbiter', 'world_object'
        ).prefetch_related('items').get(id=contract_id)
    except Contract.DoesNotExist:
        raise HttpError(404, "Contract not found")

    # Only creator or partner can initiate
    if profile.id not in [contract.creator_id, contract.partner_id]:
        raise HttpError(403, "Only contract parties can initiate arbitration")

    # Must have arbiter specified
    if not contract.arbiter_id:
        raise HttpError(400, "No arbiter specified for this contract")

    # Contract must be SIGNED (not pending, not completed)
    if contract.status != Contract.Status.SIGNED:
        raise HttpError(400, "Only active (signed) contracts can go to arbitration")

    # Check if already initiated
    if contract.arbitration_room_id:
        raise HttpError(400, f"Arbitration already initiated for this contract. Room: {contract.arbitration_room_id}")

    # Create Matrix room asynchronously
    room_id = asyncio.run(create_arbitration_room(contract, profile))

    if not room_id:
        raise HttpError(500, "Failed to create arbitration room")

    # Save arbitration info to contract
    contract.arbitration_room_id = room_id
    contract.arbitration_initiated_at = timezone.now()
    contract.arbitration_initiator = profile
    contract.save()

    logger.info(f"Arbitration initiated for contract {contract.id} by {profile.id}, room: {room_id}")

    # Notify arbiter via Matrix DM (background thread, non-blocking)
    _initiator_id = profile.id
    _arbiter_id = contract.arbiter_id
    _contract_id = contract.id
    _contract_title = contract.title

    def _notify_arbiter():
        try:
            from parahub.endpoints.matrix_auth import create_dm_between_accounts
            initiator = Profile.objects.get(id=_initiator_id)
            arbiter = Profile.objects.get(id=_arbiter_id)
            initiator_name = initiator.display_name or initiator.hna or 'A party'
            msg = (
                f"⚖️ Arbitration requested for contract '{_contract_title}'\n\n"
                f"{initiator_name} has initiated a dispute. You are the assigned arbiter.\n"
                f"Please review the arbitration room in your Matrix chat."
            )
            msg_html = (
                f"⚖️ <b>Arbitration requested</b> for contract <b>{_contract_title}</b><br><br>"
                f"{initiator_name} has initiated a dispute. You are the assigned arbiter.<br>"
                f"Please review the arbitration room in your Matrix chat."
            )
            create_dm_between_accounts(
                str(initiator.account_id),
                str(arbiter.account_id),
                msg,
                msg_html,
            )
            logger.info(f"Sent arbitration DM to arbiter {_arbiter_id} for contract {_contract_id}")
        except Exception as exc:
            logger.warning(f"Failed to send arbitration DM for contract {_contract_id}: {exc}")

    threading.Thread(target=_notify_arbiter, daemon=True).start()

    return _build_contract_response(contract)


@router.post('/{contract_id}/verdict/', response={200: VerdictResponse, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='contracts:verdict', key=user_or_ip, rate='5/m', method='POST')
def submit_verdict(request, contract_id: str, data: VerdictSubmitRequest):
    """Submit arbiter's verdict for a contract.

    Only the assigned arbiter can submit. Contract must have active arbitration.
    """
    profile = request.auth_profile

    try:
        contract = Contract.objects.select_related(
            'creator', 'partner', 'arbiter', 'world_object'
        ).get(id=contract_id)
    except Contract.DoesNotExist:
        raise HttpError(404, "Contract not found")

    # Only arbiter can submit verdict
    if profile.id != contract.arbiter_id:
        raise HttpError(403, "Only the assigned arbiter can submit a verdict")

    # Must have arbitration room (arbitration initiated)
    if not contract.arbitration_room_id:
        raise HttpError(400, "Arbitration has not been initiated for this contract")

    # Validate verdict type
    valid_types = ['FAVOR_CREATOR', 'FAVOR_PARTNER', 'PARTIAL', 'DISMISSED']
    if data.verdict_type not in valid_types:
        raise HttpError(400, f"Invalid verdict type. Use: {', '.join(valid_types)}")

    # Check if verdict already exists
    if ArbitrationVerdict.objects.filter(contract=contract).exists():
        raise HttpError(400, "A verdict has already been submitted for this contract")

    verdict = ArbitrationVerdict.objects.create(
        contract=contract,
        arbiter=profile,
        verdict_type=data.verdict_type,
        summary=data.summary,
        amount_awarded=data.amount_awarded,
        currency=data.currency or '',
    )

    logger.info(f"Verdict submitted for contract {contract.id} by arbiter {profile.id}: {data.verdict_type}")

    # Post verdict to Matrix room (background thread)
    _contract_id = contract.id

    def _post_verdict():
        try:
            c = Contract.objects.select_related('creator', 'partner', 'arbiter', 'world_object').get(id=_contract_id)
            v = ArbitrationVerdict.objects.select_related('arbiter').get(contract=c)
            asyncio.run(post_verdict_to_room(c, v))
        except Exception as exc:
            logger.warning(f"Failed to post verdict to room: {exc}")

    threading.Thread(target=_post_verdict, daemon=True).start()

    return _build_verdict_response(verdict)


@router.get('/{contract_id}/verdict/', response={200: VerdictResponse, 404: dict}, auth=ProfileAuth())
@ratelimit(group='contracts:verdict_detail', key=user_or_ip, rate='30/m')
def get_verdict(request, contract_id: str):
    """Get verdict for a contract."""
    profile = request.auth_profile

    try:
        contract = Contract.objects.get(id=contract_id)
    except Contract.DoesNotExist:
        raise HttpError(404, "Contract not found")

    # Only parties or arbiter can view
    if profile.id not in [contract.creator_id, contract.partner_id, contract.arbiter_id]:
        raise HttpError(403, "Not authorized")

    try:
        verdict = ArbitrationVerdict.objects.select_related('arbiter').get(contract=contract)
    except ArbitrationVerdict.DoesNotExist:
        raise HttpError(404, "No verdict for this contract")

    return _build_verdict_response(verdict)


@router.post('/{contract_id}/rate-arbiter/', response={200: VerdictResponse, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='contracts:rate_arbiter', key=user_or_ip, rate='10/m', method='POST')
def rate_arbiter(request, contract_id: str, data: RateArbiterRequest):
    """Rate the arbiter after verdict. Only creator or partner can rate (once each)."""
    profile = request.auth_profile

    if data.rating < 1 or data.rating > 5:
        raise HttpError(400, "Rating must be between 1 and 5")

    try:
        contract = Contract.objects.get(id=contract_id)
    except Contract.DoesNotExist:
        raise HttpError(404, "Contract not found")

    is_creator = profile.id == contract.creator_id
    is_partner = profile.id == contract.partner_id

    if not is_creator and not is_partner:
        raise HttpError(403, "Only contract parties can rate the arbiter")

    try:
        verdict = ArbitrationVerdict.objects.select_related('arbiter').get(contract=contract)
    except ArbitrationVerdict.DoesNotExist:
        raise HttpError(404, "No verdict exists for this contract")

    if is_creator:
        if verdict.creator_arbiter_rating is not None:
            raise HttpError(400, "You have already rated the arbiter")
        verdict.creator_arbiter_rating = data.rating
        verdict.save(update_fields=['creator_arbiter_rating'])
    else:
        if verdict.partner_arbiter_rating is not None:
            raise HttpError(400, "You have already rated the arbiter")
        verdict.partner_arbiter_rating = data.rating
        verdict.save(update_fields=['partner_arbiter_rating'])

    logger.info(f"Arbiter rated for contract {contract.id} by {profile.id}: {data.rating}")

    return _build_verdict_response(verdict)


@router.post('/{contract_id}/escalate/', response={200: ContractResponse, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='contracts:escalate', key=user_or_ip, rate='5/m', method='POST')
def escalate_arbitration(request, contract_id: str):
    """Escalate arbitration to next level (1=P2P → 2=CAC → 3=Court).

    Only creator or partner can escalate. Arbitration must be initiated.
    """
    profile = request.auth_profile

    try:
        contract = Contract.objects.select_related(
            'creator', 'partner', 'arbiter', 'world_object'
        ).prefetch_related('items').get(id=contract_id)
    except Contract.DoesNotExist:
        raise HttpError(404, "Contract not found")

    if profile.id not in [contract.creator_id, contract.partner_id]:
        raise HttpError(403, "Only contract parties can escalate")

    if not contract.arbitration_room_id:
        raise HttpError(400, "Arbitration has not been initiated")

    if contract.arbitration_level >= 3:
        raise HttpError(400, "Already at maximum escalation level (Court)")

    new_level = contract.arbitration_level + 1
    contract.arbitration_level = new_level
    contract.arbitration_escalated_at = timezone.now()
    contract.arbitration_escalated_by = profile
    contract.save()

    logger.info(f"Contract {contract.id} escalated to level {new_level} by {profile.id}")

    # Post escalation to Matrix room (background thread)
    _contract_id = contract.id
    _profile_id = profile.id
    _new_level = new_level

    def _post_escalation():
        try:
            c = Contract.objects.select_related('creator', 'partner', 'arbiter', 'world_object').get(id=_contract_id)
            p = Profile.objects.get(id=_profile_id)
            asyncio.run(post_escalation_to_room(c, p, _new_level))
        except Exception as exc:
            logger.warning(f"Failed to post escalation to room: {exc}")

    threading.Thread(target=_post_escalation, daemon=True).start()

    return _build_contract_response(contract)
