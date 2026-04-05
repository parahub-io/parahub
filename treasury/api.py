from typing import List, Optional, Dict
from datetime import date
from decimal import Decimal
import logging

from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.pagination import paginate

from parahub.auth import ProfileAuth
from parahub.crypto.pgp import verify_profile_signature
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile
from geo.models import Establishment, EstablishmentMembership
from geo.permissions import get_auditor_profile
from .models import BudgetCategory, BudgetAllocation, BudgetEpoch, Expense, TreasuryAuditLog
from .services import TreasuryService, TreasuryAuditService

logger = logging.getLogger(__name__)
router = Router(tags=["Treasury"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_treasury_establishment(slug: str) -> Establishment:
    """Resolve establishment by slug and verify treasury is enabled."""
    try:
        est = Establishment.objects.get(slug=slug, is_active=True)
    except Establishment.DoesNotExist:
        raise HttpError(404, "Establishment not found")
    if not est.treasury_enabled:
        raise HttpError(404, "Treasury is not enabled for this establishment")
    return est


# ── Schemas ──────────────────────────────────────────────────────────────────

class CategoryOut(Schema):
    id: str
    object_type: str = 'budget_category'
    name: str
    slug: str
    description: str
    icon: str
    order: int


class MedianOut(Schema):
    category_id: str
    slug: str
    name: str
    icon: str
    median_percent: float
    voter_count: int


class CurrentBudgetOut(Schema):
    medians: List[MedianOut]
    total_eligible: int
    total_participants: int
    participation_percent: float


class AllocationIn(Schema):
    allocations: Dict[str, float]
    pgp_signature: str = ''
    signed_payload: dict = {}


class AllocationOut(Schema):
    id: str
    object_type: str = 'budget_allocation'
    allocations: Dict[str, float]
    pgp_signature: str
    updated_at: str


class MyAllocationOut(Schema):
    is_eligible: bool
    needs_update: bool = False
    allocation: Optional[AllocationOut] = None


class EpochListOut(Schema):
    id: str
    object_type: str = 'budget_epoch'
    label: str
    status: str
    total_eligible: int
    total_participants: int
    finalized_at: Optional[str] = None


class EpochDetailOut(Schema):
    id: str
    object_type: str = 'budget_epoch'
    label: str
    start_date: str
    end_date: str
    status: str
    frozen_allocations: list
    total_eligible: int
    total_participants: int
    merkle_root: str
    individual_allocations_snapshot: list
    finalized_at: Optional[str] = None


class StatsOut(Schema):
    total_eligible: int
    total_participants: int
    participation_percent: float


class AuditLogOut(Schema):
    id: str
    object_type: str = 'treasury_audit_log'
    action: str
    actor_hna: Optional[str] = None
    previous_log_hash: Optional[str] = None
    current_log_hash: str
    payload: dict
    pgp_signature: str
    timestamp: str


class ExpenseIn(Schema):
    category_id: Optional[str] = None
    amount: float
    description: str
    receipt_url: str = ''
    date: str  # YYYY-MM-DD
    epoch_label: str = ''  # YYYY-MM


class ExpenseUpdateIn(Schema):
    category_id: Optional[str] = None
    amount: Optional[float] = None
    description: Optional[str] = None
    receipt_url: Optional[str] = None
    date: Optional[str] = None
    epoch_label: Optional[str] = None


class ExpenseOut(Schema):
    id: str
    object_type: str = 'treasury_expense'
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    created_by_id: Optional[str] = None
    created_by_hna: Optional[str] = None
    created_by_display_name: Optional[str] = None
    amount: float
    description: str
    receipt_url: str
    date: str
    status: str
    epoch_label: str
    created_at: str


class ExpenseStatusIn(Schema):
    status: str  # APPROVED or REJECTED


# ── Helpers ──────────────────────────────────────────────────────────────────

def _can_manage_expenses(profile, establishment):
    """Check if profile can create/edit expenses (treasurer, OWNER, ADMIN)."""
    if establishment.owner_id == profile.id:
        return True
    m = EstablishmentMembership.objects.filter(
        profile=profile, establishment=establishment
    ).first()
    if not m:
        return False
    return m.is_treasurer or m.role in ('ADMIN',)


def _can_approve_expenses(profile, establishment):
    """Check if profile can approve/reject expenses (auditor, OWNER, ADMIN)."""
    if establishment.owner_id == profile.id:
        return True
    m = EstablishmentMembership.objects.filter(
        profile=profile, establishment=establishment
    ).first()
    if not m:
        return False
    return m.is_auditor or m.role in ('ADMIN',)


def _expense_to_out(e) -> ExpenseOut:
    return ExpenseOut(
        id=e.id,
        category_id=e.category_id,
        category_name=e.category.name if e.category else None,
        created_by_id=e.created_by_id,
        created_by_hna=e.created_by.hna if e.created_by else None,
        created_by_display_name=e.created_by.display_name if e.created_by else None,
        amount=float(e.amount),
        description=e.description,
        receipt_url=e.receipt_url,
        date=e.date.isoformat(),
        status=e.status,
        epoch_label=e.epoch_label,
        created_at=e.created_at.isoformat(),
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get('/{slug}/categories/', response=List[CategoryOut], auth=None)
@ratelimit(group='treasury:categories', key='ip', rate='60/m')
def list_categories(request, slug: str):
    """Active budget categories for an establishment (public)."""
    est = _get_treasury_establishment(slug)
    cats = TreasuryService.get_active_categories(est)
    return [CategoryOut(
        id=c.id,
        name=c.name,
        slug=c.slug,
        description=c.description,
        icon=c.icon,
        order=c.order,
    ) for c in cats]


@router.get('/{slug}/current/', response=CurrentBudgetOut, auth=None)
@ratelimit(group='treasury:current', key='ip', rate='60/m')
def current_budget(request, slug: str):
    """Current median-based budget for an establishment (public)."""
    est = _get_treasury_establishment(slug)
    medians = TreasuryService.calculate_current_medians(est)
    stats = TreasuryService.get_participation_stats(est)
    return CurrentBudgetOut(
        medians=[MedianOut(**m) for m in medians],
        total_eligible=stats['total_eligible'],
        total_participants=stats['total_participants'],
        participation_percent=stats['participation_percent'],
    )


@router.get('/{slug}/my/', response=MyAllocationOut, auth=ProfileAuth())
@ratelimit(group='treasury:my', key=user_or_ip, rate='30/m')
def my_allocation(request, slug: str):
    """Current user's allocation + eligibility status for an establishment."""
    est = _get_treasury_establishment(slug)
    profile: Profile = request.auth
    eligible = TreasuryService.is_eligible(profile, est)

    if not eligible:
        return MyAllocationOut(is_eligible=False)

    try:
        alloc = BudgetAllocation.objects.get(profile=profile, establishment=est)
        # Check if needs update (missing active categories)
        active_ids = set(
            BudgetCategory.objects.filter(
                establishment=est, is_active=True
            ).values_list('id', flat=True)
        )
        alloc_ids = set(alloc.allocations.keys())
        needs_update = active_ids != alloc_ids

        return MyAllocationOut(
            is_eligible=True,
            needs_update=needs_update,
            allocation=AllocationOut(
                id=alloc.id,
                allocations=alloc.allocations,
                pgp_signature=alloc.pgp_signature,
                updated_at=alloc.updated_at.isoformat(),
            ),
        )
    except BudgetAllocation.DoesNotExist:
        return MyAllocationOut(is_eligible=True, needs_update=True)


@router.put('/{slug}/my/', response=AllocationOut, auth=ProfileAuth())
@ratelimit(group='treasury:allocate', key=user_or_ip, rate='30/m', method='PUT')
def update_allocation(request, slug: str, data: AllocationIn):
    """Update current user's budget allocation for an establishment."""
    est = _get_treasury_establishment(slug)
    profile: Profile = request.auth

    if not TreasuryService.is_eligible(profile, est):
        raise HttpError(403, "Not eligible to vote. Check membership level requirements.")

    is_valid, error = TreasuryService.validate_allocations(data.allocations, est)
    if not is_valid:
        raise HttpError(400, error)

    # PGP signature verification (mandatory if profile has key)
    verify_profile_signature(
        profile=profile,
        canonical_payload={
            "allocations": dict(sorted(data.allocations.items())),
            "establishment_slug": slug,
            "timestamp": data.signed_payload.get("timestamp", ""),
        },
        signature=data.pgp_signature,
        signed_timestamp=data.signed_payload.get("timestamp", ""),
        error_prefix="Treasury PGP",
    )

    alloc = TreasuryService.update_allocation(
        profile=profile,
        establishment=est,
        allocations=data.allocations,
        pgp_signature=data.pgp_signature,
        signed_payload=data.signed_payload,
    )

    TreasuryAuditService.create_log_entry(
        establishment=est,
        action=TreasuryAuditLog.Action.ALLOCATION_UPDATED,
        payload={
            'profile_id': profile.id,
            'profile_hna': profile.hna,
            'allocations': data.allocations,
        },
        actor=profile,
        pgp_signature=data.pgp_signature,
    )

    # Broadcast via WebSocket
    _broadcast_treasury_update(est, profile)

    return AllocationOut(
        id=alloc.id,
        allocations=alloc.allocations,
        pgp_signature=alloc.pgp_signature,
        updated_at=alloc.updated_at.isoformat(),
    )


@router.get('/{slug}/epochs/', response=List[EpochListOut], auth=None)
@ratelimit(group='treasury:epochs', key='ip', rate='60/m')
@paginate
def list_epochs(request, slug: str):
    """List budget epochs for an establishment (paginated)."""
    est = _get_treasury_establishment(slug)
    epochs = BudgetEpoch.objects.filter(establishment=est).order_by('-start_date')
    return [EpochListOut(
        id=e.id,
        label=e.label,
        status=e.status,
        total_eligible=e.total_eligible,
        total_participants=e.total_participants,
        finalized_at=e.finalized_at.isoformat() if e.finalized_at else None,
    ) for e in epochs]


@router.get('/{slug}/epochs/{epoch_id}/', response=EpochDetailOut, auth=None)
@ratelimit(group='treasury:epoch_detail', key='ip', rate='60/m')
def epoch_detail(request, slug: str, epoch_id: str):
    """Epoch detail with individual allocations."""
    est = _get_treasury_establishment(slug)
    try:
        e = BudgetEpoch.objects.get(id=epoch_id, establishment=est)
    except BudgetEpoch.DoesNotExist:
        raise HttpError(404, "Epoch not found")

    return EpochDetailOut(
        id=e.id,
        label=e.label,
        start_date=e.start_date.isoformat(),
        end_date=e.end_date.isoformat(),
        status=e.status,
        frozen_allocations=e.frozen_allocations,
        total_eligible=e.total_eligible,
        total_participants=e.total_participants,
        merkle_root=e.merkle_root,
        individual_allocations_snapshot=e.individual_allocations_snapshot,
        finalized_at=e.finalized_at.isoformat() if e.finalized_at else None,
    )


@router.get('/{slug}/stats/', response=StatsOut, auth=None)
@ratelimit(group='treasury:stats', key='ip', rate='60/m')
def participation_stats(request, slug: str):
    """Participation statistics for an establishment (public)."""
    est = _get_treasury_establishment(slug)
    stats = TreasuryService.get_participation_stats(est)
    return StatsOut(**stats)


@router.get('/{slug}/audit-log/', response=List[AuditLogOut], auth=None)
@ratelimit(group='treasury:audit_log', key='ip', rate='60/m')
@paginate
def audit_log(request, slug: str):
    """Treasury audit log for an establishment (paginated, public)."""
    est = _get_treasury_establishment(slug)
    logs = TreasuryAuditLog.objects.filter(
        establishment=est
    ).select_related('actor').order_by('-timestamp')
    return [AuditLogOut(
        id=log.id,
        action=log.action,
        actor_hna=log.actor.hna if log.actor else None,
        previous_log_hash=log.previous_log_hash,
        current_log_hash=log.current_log_hash,
        payload=log.payload,
        pgp_signature=log.pgp_signature,
        timestamp=log.timestamp.isoformat(),
    ) for log in logs]


@router.get('/{slug}/audit-log/verify/', auth=None)
@ratelimit(group='treasury:audit_verify', key='ip', rate='10/m')
def verify_audit_chain(request, slug: str):
    """Verify Merkle chain integrity for an establishment's treasury audit log."""
    est = _get_treasury_establishment(slug)
    count = TreasuryAuditLog.objects.filter(establishment=est).count()
    if count == 0:
        return {'valid': True, 'entries': 0, 'error': None}
    is_valid, error = TreasuryAuditService.verify_merkle_chain(est)
    return {'valid': is_valid, 'entries': count, 'error': error}


# ── Expense Endpoints ────────────────────────────────────────────────────────

@router.get('/{slug}/expenses/', response=List[ExpenseOut], auth=None)
@ratelimit(group='treasury:expenses_list', key='ip', rate='60/m')
def list_expenses(request, slug: str, status: Optional[str] = None, epoch: Optional[str] = None):
    """List expenses for an establishment (public — transparency)."""
    est = _get_treasury_establishment(slug)
    qs = Expense.objects.filter(
        establishment=est
    ).select_related('category', 'created_by').order_by('-date', '-created_at')

    if status:
        qs = qs.filter(status=status.upper())
    if epoch:
        qs = qs.filter(epoch_label=epoch)

    return [_expense_to_out(e) for e in qs[:100]]


@router.post('/{slug}/expenses/', response=ExpenseOut, auth=ProfileAuth())
@ratelimit(group='treasury:expense_create', key=user_or_ip, rate='30/m', method='POST')
def create_expense(request, slug: str, data: ExpenseIn):
    """Create expense (treasurer, OWNER, ADMIN only)."""
    est = _get_treasury_establishment(slug)
    profile: Profile = request.auth

    if not _can_manage_expenses(profile, est):
        raise HttpError(403, "Only treasurer, owner, or admin can create expenses")

    # Validate category if provided
    category = None
    if data.category_id:
        try:
            category = BudgetCategory.objects.get(id=data.category_id, establishment=est, is_active=True)
        except BudgetCategory.DoesNotExist:
            raise HttpError(400, "Invalid category")

    try:
        expense_date = date.fromisoformat(data.date)
    except ValueError:
        raise HttpError(400, "Invalid date format, use YYYY-MM-DD")

    expense = Expense.objects.create(
        establishment=est,
        category=category,
        created_by=profile,
        amount=Decimal(str(data.amount)),
        description=data.description,
        receipt_url=data.receipt_url,
        date=expense_date,
        epoch_label=data.epoch_label or expense_date.strftime('%Y-%m'),
    )

    TreasuryAuditService.create_log_entry(
        establishment=est,
        action=TreasuryAuditLog.Action.EXPENSE_CREATED,
        payload={
            'expense_id': expense.id,
            'amount': str(expense.amount),
            'description': expense.description[:100],
            'category': category.slug if category else None,
        },
        actor=profile,
    )

    return _expense_to_out(Expense.objects.select_related('category', 'created_by').get(id=expense.id))


@router.put('/{slug}/expenses/{expense_id}/', response=ExpenseOut, auth=ProfileAuth())
@ratelimit(group='treasury:expense_update', key=user_or_ip, rate='30/m', method='PUT')
def update_expense(request, slug: str, expense_id: str, data: ExpenseUpdateIn):
    """Update a DRAFT expense (creator, treasurer, OWNER, ADMIN)."""
    est = _get_treasury_establishment(slug)
    profile: Profile = request.auth

    try:
        expense = Expense.objects.select_related('category', 'created_by').get(
            id=expense_id, establishment=est
        )
    except Expense.DoesNotExist:
        raise HttpError(404, "Expense not found")

    if expense.status != 'DRAFT':
        raise HttpError(400, "Only DRAFT expenses can be edited")

    is_creator = expense.created_by_id == profile.id
    if not is_creator and not _can_manage_expenses(profile, est):
        raise HttpError(403, "Not allowed to edit this expense")

    if data.category_id is not None:
        if data.category_id:
            try:
                expense.category = BudgetCategory.objects.get(
                    id=data.category_id, establishment=est, is_active=True
                )
            except BudgetCategory.DoesNotExist:
                raise HttpError(400, "Invalid category")
        else:
            expense.category = None

    if data.amount is not None:
        expense.amount = Decimal(str(data.amount))
    if data.description is not None:
        expense.description = data.description
    if data.receipt_url is not None:
        expense.receipt_url = data.receipt_url
    if data.date is not None:
        try:
            expense.date = date.fromisoformat(data.date)
        except ValueError:
            raise HttpError(400, "Invalid date format, use YYYY-MM-DD")
    if data.epoch_label is not None:
        expense.epoch_label = data.epoch_label

    expense.save()
    return _expense_to_out(expense)


@router.put('/{slug}/expenses/{expense_id}/status/', response=ExpenseOut, auth=ProfileAuth())
@ratelimit(group='treasury:expense_status', key=user_or_ip, rate='30/m', method='PUT')
def update_expense_status(request, slug: str, expense_id: str, data: ExpenseStatusIn):
    """Approve or reject an expense (auditor, OWNER, ADMIN)."""
    est = _get_treasury_establishment(slug)
    profile: Profile = request.auth

    if data.status not in ('APPROVED', 'REJECTED'):
        raise HttpError(400, "Status must be APPROVED or REJECTED")

    if not _can_approve_expenses(profile, est):
        raise HttpError(403, "Only auditor, owner, or admin can approve/reject expenses")

    try:
        expense = Expense.objects.select_related('category', 'created_by').get(
            id=expense_id, establishment=est
        )
    except Expense.DoesNotExist:
        raise HttpError(404, "Expense not found")

    if expense.status != 'DRAFT':
        raise HttpError(400, "Only DRAFT expenses can be approved/rejected")

    expense.status = data.status
    expense.save(update_fields=['status', 'updated_at'])

    TreasuryAuditService.create_log_entry(
        establishment=est,
        action=TreasuryAuditLog.Action.EXPENSE_APPROVED,
        payload={
            'expense_id': expense.id,
            'new_status': data.status,
            'amount': str(expense.amount),
        },
        actor=profile,
    )

    return _expense_to_out(expense)


# ── WebSocket broadcast helper ───────────────────────────────────────────────

def _broadcast_treasury_update(establishment: Establishment, profile: Profile):
    """Broadcast updated medians to all treasury room subscribers for this establishment."""
    from parahub.services.ws_publish import ws_publish
    medians = TreasuryService.calculate_current_medians(establishment)
    stats = TreasuryService.get_participation_stats(establishment)

    ws_publish(f'treasury:{establishment.id}', {
        'type': 'treasury.medians_updated',
        'id': establishment.id,
        'medians': medians,
        'total_eligible': stats['total_eligible'],
        'total_participants': stats['total_participants'],
        'participation_percent': stats['participation_percent'],
        'updated_by': profile.hna,
    })
