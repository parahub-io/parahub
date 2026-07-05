"""
Condominium management endpoints.
"""

from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import paginate, PageNumberPagination
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import datetime
import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

router = Router(tags=["Geo / Condominiums"])


# ===== Schemas =====

class FractionInput(BaseModel):
    identifier: str = Field(..., max_length=20)
    description: str = ""
    floor: str = ""
    fraction_type: str = "APARTMENT"
    permilagem: Decimal = Field(..., gt=0, le=1000)


class FractionResponse(BaseModel):
    id: str
    object_type: str = "condominium_fraction"
    identifier: str
    description: str
    floor: str
    fraction_type: str
    permilagem: Decimal
    resident_id: Optional[str] = None
    resident_hna: Optional[str] = None
    resident_display_name: Optional[str] = None
    is_owner: bool = True
    invite_token: Optional[str] = None
    created_at: datetime


class FractionUpdateInput(BaseModel):
    identifier: Optional[str] = Field(None, max_length=20)
    description: Optional[str] = None
    floor: Optional[str] = None
    fraction_type: Optional[str] = None
    permilagem: Optional[Decimal] = Field(None, gt=0, le=1000)
    resident_id: Optional[str] = None
    is_owner: Optional[bool] = None


class CondominiumCreateInput(BaseModel):
    """Create condominium with fractions in one call."""
    world_object_id: str
    name: str = Field(..., max_length=255)
    slug: Optional[str] = Field(None, max_length=100)
    description: str = ""
    legal_entity_id: str = ""
    terms_content: str = ""
    fractions: List[FractionInput]


class QuotaPaymentInput(BaseModel):
    fraction_id: str
    month: str = Field(..., pattern=r'^\d{4}-\d{2}$')
    amount: Decimal = Field(..., gt=0)
    notes: str = ""


class QuotaPaymentResponse(BaseModel):
    id: str
    object_type: str = "quota_payment"
    fraction_id: str
    fraction_identifier: str
    month: str
    amount: Decimal
    paid_at: Optional[datetime] = None
    confirmed_by_id: Optional[str] = None
    confirmed_by_hna: Optional[str] = None
    confirmed_by_display_name: Optional[str] = None
    notes: str
    created_at: datetime


class QuotaOverviewItem(BaseModel):
    fraction_id: str
    identifier: str
    permilagem: Decimal
    expected_quota: Decimal
    paid: bool
    payment: Optional[QuotaPaymentResponse] = None
    resident_display_name: Optional[str] = None
    resident_id: Optional[str] = None
    is_owner: bool = True
    months_unpaid: int = 0


class QuotaPageResponse(BaseModel):
    monthly_budget: Decimal
    is_admin: bool
    items: List[QuotaOverviewItem]
    fractions_paid: int
    fractions_total: int
    delinquent_count: int


class FinancialSummaryCategory(BaseModel):
    category_id: Optional[str] = None
    slug: str
    name: str
    percent: Decimal  # 0..100, share of annual budget
    annual_amount: Decimal


class FinancialSummaryResponse(BaseModel):
    year: int
    monthly_budget: Decimal
    annual_budget: Decimal
    categories: List[FinancialSummaryCategory]
    current_month: str  # "YYYY-MM"
    months_elapsed: int
    expected_ytd: Decimal
    collected_ytd: Decimal
    outstanding_balance: Decimal
    collection_rate: Decimal  # 0..1, 0 if expected=0
    current_month_expected: Decimal
    current_month_collected: Decimal
    fractions_total: int
    fractions_paid_current: int


class BudgetUpdateInput(BaseModel):
    monthly_budget: Decimal = Field(..., ge=0)


class AssemblyInput(BaseModel):
    title: str = Field(..., max_length=255)
    description: str = ""
    options: List[str] = Field(..., min_length=2, max_length=10)
    quorum_type: str = "simple_majority"  # simple_majority, two_thirds, unanimity
    ends_at: datetime


# ===== Helpers =====

def _resolve_condo(slug: str):
    """Resolve condominium establishment by slug."""
    from geo.models import Establishment
    est = get_object_or_404(Establishment, slug=slug, organization_type='CONDOMINIUM', is_active=True)
    return est


def _check_condo_admin(request, establishment) -> bool:
    """Check if user is OWNER or ADMIN of the condominium."""
    from geo.models import EstablishmentMembership
    profile = request.auth
    if establishment.owner_id == profile.id:
        return True
    return EstablishmentMembership.objects.filter(
        profile=profile,
        establishment=establishment,
        role__in=['OWNER', 'ADMIN'],
    ).exists()


def _check_condo_member(request, establishment) -> bool:
    """Check if user is any member of the condominium."""
    from geo.models import EstablishmentMembership, CondominiumFraction
    profile = request.auth
    if establishment.owner_id == profile.id:
        return True
    if EstablishmentMembership.objects.filter(profile=profile, establishment=establishment).exists():
        return True
    if CondominiumFraction.objects.filter(establishment=establishment, resident=profile).exists():
        return True
    return False


def _format_fraction(f, show_token=False, viewer=None) -> FractionResponse:
    return FractionResponse(
        id=f.id,
        identifier=f.identifier,
        description=f.description,
        floor=f.floor,
        fraction_type=f.fraction_type,
        permilagem=f.permilagem,
        resident_id=f.resident_id,
        resident_hna=f.resident.hna if f.resident else None,
        resident_display_name=(f.resident.display_name if f.resident.name_visible_to(viewer) else f.resident.hna) if f.resident else None,
        is_owner=f.is_owner,
        invite_token=f.invite_token if show_token else None,
        created_at=f.created_at,
    )


def _format_payment(p, viewer=None) -> QuotaPaymentResponse:
    return QuotaPaymentResponse(
        id=p.id,
        fraction_id=p.fraction_id,
        fraction_identifier=p.fraction.identifier,
        month=p.month,
        amount=p.amount,
        paid_at=p.paid_at,
        confirmed_by_id=p.confirmed_by_id,
        confirmed_by_hna=p.confirmed_by.hna if p.confirmed_by else None,
        confirmed_by_display_name=(p.confirmed_by.display_name if p.confirmed_by.name_visible_to(viewer) else p.confirmed_by.hna) if p.confirmed_by else None,
        notes=p.notes,
        created_at=p.created_at,
    )


def _wot_check(request):
    """Require WoT level 3+ (or admin/foundation member)."""
    from identity.models import Verification
    profile = request.auth
    if profile.account.is_superuser:
        return
    if profile.is_foundation_member():
        return
    count = Verification.objects.filter(verified_profile=profile, is_active=True).count()
    if count < 3:
        raise HttpError(403, "Requires WoT level 3+ to manage condominiums")


# ===== Map Schema =====

class CondominiumMapItem(BaseModel):
    id: str
    name: str
    slug: Optional[str] = None
    full_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    fraction_count: int = 0
    member_count: int = 0


# ===== Endpoints =====

class MyCondominiumItem(BaseModel):
    id: str
    object_type: str = "establishment"
    name: str
    slug: Optional[str] = None
    full_address: Optional[str] = None
    fraction_count: int = 0
    member_count: int = 0
    role: str = "member"  # owner, admin, member, resident
    is_demo: bool = False


@router.get("/condominiums/my/", auth=ProfileAuth(), response=List[MyCondominiumItem])
@ratelimit(group='condo:my', key=user_or_ip, rate='30/m')
def my_condominiums(request):
    """List condominiums where the user is owner, member, or fraction resident."""
    from geo.models import Establishment, EstablishmentMembership, CondominiumFraction
    from django.db.models import Count, Q

    profile = request.auth

    # Condos where user is owner or member
    member_est_ids = set(
        EstablishmentMembership.objects.filter(profile=profile)
        .values_list('establishment_id', flat=True)
    )
    # Condos where user is fraction resident
    resident_est_ids = set(
        CondominiumFraction.objects.filter(resident=profile)
        .values_list('establishment_id', flat=True)
    )
    # Owner
    owner_est_ids = set(
        Establishment.objects.filter(owner=profile, organization_type='CONDOMINIUM', is_active=True)
        .values_list('id', flat=True)
    )

    all_ids = member_est_ids | resident_est_ids | owner_est_ids
    if not all_ids:
        return []

    qs = (
        Establishment.objects
        .filter(id__in=all_ids, organization_type='CONDOMINIUM', is_active=True)
        .select_related('world_object')
        .annotate(
            fraction_count_ann=Count('fractions', distinct=True),
            member_count_ann=Count('memberships', distinct=True),
        )
        .order_by('-created_at')
    )

    # Roles map
    membership_roles = dict(
        EstablishmentMembership.objects.filter(profile=profile, establishment_id__in=all_ids)
        .values_list('establishment_id', 'role')
    )

    results = []
    for est in qs:
        if est.owner_id == profile.id:
            role = 'owner'
        elif membership_roles.get(est.id) in ('OWNER', 'ADMIN'):
            role = 'admin'
        elif est.id in resident_est_ids:
            role = 'resident'
        else:
            role = 'member'

        results.append(MyCondominiumItem(
            id=est.id,
            name=est.name,
            slug=est.slug or None,
            full_address=est.world_object.full_address if est.world_object else None,
            fraction_count=est.fraction_count_ann,
            member_count=est.member_count_ann,
            role=role,
            is_demo=bool(est.attributes.get('__demo_seed') or est.attributes.get('demo')),
        ))

    return results


@router.get("/condominiums/map/", auth=None, response=List[CondominiumMapItem])
@ratelimit(group='condo:map', key='ip', rate='60/m')
def condominiums_map(request):
    """
    Public lightweight list of condominiums for the map layer.
    Returns only active condominiums with coordinates.
    """
    from geo.models import Establishment
    from django.db.models import Count

    qs = (
        Establishment.objects
        .filter(organization_type='CONDOMINIUM', is_active=True)
        .exclude(owner__account__is_test=True)
        .exclude(owner__account__is_bot=True)
        .select_related('world_object')
        .annotate(
            fraction_count_ann=Count('fractions', distinct=True),
            member_count_ann=Count('memberships', distinct=True),
        )
    )

    results = []
    for est in qs:
        lat = lon = None
        if est.world_object and est.world_object.location:
            lat = est.world_object.location.y
            lon = est.world_object.location.x
        elif est.location:
            lat = est.location.y
            lon = est.location.x

        if lat is None:
            continue  # skip condos without coordinates

        results.append(CondominiumMapItem(
            id=est.id,
            name=est.name,
            slug=est.slug or None,
            full_address=est.world_object.full_address if est.world_object else None,
            latitude=lat,
            longitude=lon,
            fraction_count=est.fraction_count_ann,
            member_count=est.member_count_ann,
        ))

    return results


@router.post("/condominiums/", auth=ProfileAuth(), response={200: dict, 400: dict, 403: dict})
@ratelimit(group='condo:create', key=user_or_ip, rate='10/m', method='POST')
def create_condominium(request, payload: CondominiumCreateInput):
    """Create a new condominium with fractions."""
    from geo.models import WorldObject, Establishment, EstablishmentMembership, CondominiumFraction
    from geo.services.condominium import CondominiumService

    _wot_check(request)
    profile = request.auth

    # Validate permilagem
    fractions_data = [f.model_dump() for f in payload.fractions]
    valid, err = CondominiumService.validate_permilagem_total(fractions_data)
    if not valid:
        raise HttpError(400, err)

    world_object = get_object_or_404(WorldObject, id=payload.world_object_id)

    with transaction.atomic():
        # Create establishment
        est = Establishment.objects.create(
            owner=profile,
            world_object=world_object,
            name=payload.name,
            slug=payload.slug or '',
            description=payload.description,
            organization_type='CONDOMINIUM',
            legal_entity_id=payload.legal_entity_id,
            terms_content=payload.terms_content,
            member_visibility='MEMBERS_ONLY',
            treasury_enabled=True,
            treasury_eligible_levels=['efetivo', 'fundador'],
        )

        # Auto-generate slug if not provided
        if not est.slug:
            from django.utils.text import slugify
            from core.models import generate_ulid
            base = slugify(payload.name)[:80]
            est.slug = f"{base}-{generate_ulid()[:8].lower()}"
            est.save(update_fields=['slug'])

        # Create owner membership
        EstablishmentMembership.objects.create(
            profile=profile,
            establishment=est,
            role='OWNER',
            membership_level='fundador',
        )

        # Create fractions
        for f_data in fractions_data:
            CondominiumFraction.objects.create(
                establishment=est,
                identifier=f_data['identifier'],
                description=f_data.get('description', ''),
                floor=f_data.get('floor', ''),
                fraction_type=f_data.get('fraction_type', 'APARTMENT'),
                permilagem=f_data['permilagem'],
            )

        # Create default budget categories
        CondominiumService.create_default_budget_categories(est)

        # Create Matrix room (best effort)
        try:
            from geo.endpoints.events import _create_event_matrix_room

            class _CondoRoom:
                def __init__(self, est):
                    self.id = est.id
                    self.title = est.name
            room_id = _create_event_matrix_room(_CondoRoom(est), profile)
            if room_id:
                est.matrix_room_id = room_id
                est.save(update_fields=['matrix_room_id'])
        except Exception as e:
            logger.warning(f"Failed to create Matrix room for condominium {est.id}: {e}")

    return {
        'id': est.id,
        'object_type': 'establishment',
        'slug': est.slug,
        'name': est.name,
        'fractions_count': len(fractions_data),
    }


class CondoInfoResponse(BaseModel):
    id: str
    name: str
    slug: Optional[str] = None
    full_address: Optional[str] = None


@router.get("/condominiums/{slug}/info/", auth=None, response=CondoInfoResponse)
@ratelimit(group='condo:info', key='ip', rate='60/m')
def condo_info(request, slug: str):
    """Get basic condominium info for page headers. Public — name is not sensitive."""
    est = _resolve_condo(slug)
    return CondoInfoResponse(
        id=est.id,
        name=est.name,
        slug=est.slug or None,
        full_address=est.world_object.full_address if est.world_object else None,
    )


@router.get("/condominiums/{slug}/fractions/", auth=ProfileAuth(), response=List[FractionResponse])
@ratelimit(group='condo:fractions', key=user_or_ip, rate='30/m')
def list_fractions(request, slug: str):
    """List fractions for a condominium."""
    from geo.models import CondominiumFraction
    est = _resolve_condo(slug)
    if not _check_condo_member(request, est):
        raise HttpError(403, "Not a member of this condominium")

    is_admin = _check_condo_admin(request, est)
    fractions = CondominiumFraction.objects.filter(establishment=est).select_related('resident')
    return [_format_fraction(f, show_token=is_admin, viewer=request.auth) for f in fractions]


@router.post("/condominiums/{slug}/fractions/", auth=ProfileAuth(), response={200: FractionResponse, 400: dict, 403: dict})
@ratelimit(group='condo:fraction_add', key=user_or_ip, rate='30/m', method='POST')
def add_fraction(request, slug: str, payload: FractionInput):
    """Add a fraction to a condominium."""
    from geo.models import CondominiumFraction
    est = _resolve_condo(slug)
    if not _check_condo_admin(request, est):
        raise HttpError(403, "Only OWNER/ADMIN can add fractions")

    # Check unique identifier
    if CondominiumFraction.objects.filter(establishment=est, identifier=payload.identifier).exists():
        raise HttpError(400, f"Fraction '{payload.identifier}' already exists")

    f = CondominiumFraction.objects.create(
        establishment=est,
        identifier=payload.identifier,
        description=payload.description,
        floor=payload.floor,
        fraction_type=payload.fraction_type,
        permilagem=payload.permilagem,
    )
    return _format_fraction(f, show_token=True, viewer=request.auth)


@router.put("/condominiums/{slug}/fractions/{fraction_id}/", auth=ProfileAuth(),
            response={200: FractionResponse, 400: dict, 403: dict})
@ratelimit(group='condo:fraction_update', key=user_or_ip, rate='30/m', method='PUT')
def update_fraction(request, slug: str, fraction_id: str, payload: FractionUpdateInput):
    """Update a fraction."""
    from geo.models import CondominiumFraction
    from identity.models import Profile
    est = _resolve_condo(slug)
    if not _check_condo_admin(request, est):
        raise HttpError(403, "Only OWNER/ADMIN can update fractions")

    f = get_object_or_404(CondominiumFraction, id=fraction_id, establishment=est)

    update_fields = []
    if payload.identifier is not None:
        # Check uniqueness
        if CondominiumFraction.objects.filter(establishment=est, identifier=payload.identifier).exclude(id=f.id).exists():
            raise HttpError(400, f"Fraction '{payload.identifier}' already exists")
        f.identifier = payload.identifier
        update_fields.append('identifier')
    if payload.description is not None:
        f.description = payload.description
        update_fields.append('description')
    if payload.floor is not None:
        f.floor = payload.floor
        update_fields.append('floor')
    if payload.fraction_type is not None:
        f.fraction_type = payload.fraction_type
        update_fields.append('fraction_type')
    if payload.permilagem is not None:
        f.permilagem = payload.permilagem
        update_fields.append('permilagem')
    if payload.is_owner is not None:
        f.is_owner = payload.is_owner
        update_fields.append('is_owner')
    if payload.resident_id is not None:
        if payload.resident_id == '':
            f.resident = None
        else:
            f.resident = get_object_or_404(Profile, id=payload.resident_id)
        update_fields.append('resident')

    if update_fields:
        f.save(update_fields=update_fields)

    return _format_fraction(f, show_token=True, viewer=request.auth)


@router.delete("/condominiums/{slug}/fractions/{fraction_id}/", auth=ProfileAuth(),
               response={200: dict, 403: dict, 409: dict})
@ratelimit(group='condo:fraction_delete', key=user_or_ip, rate='30/m', method='DELETE')
def delete_fraction(request, slug: str, fraction_id: str):
    """Delete a vacant fraction."""
    from geo.models import CondominiumFraction
    est = _resolve_condo(slug)
    if not _check_condo_admin(request, est):
        raise HttpError(403, "Only OWNER/ADMIN can delete fractions")

    f = get_object_or_404(CondominiumFraction, id=fraction_id, establishment=est)
    if f.resident_id:
        raise HttpError(409, "Cannot delete fraction with assigned resident")

    f.delete()
    return {'ok': True}


@router.post("/condominiums/{slug}/fractions/{fraction_id}/invite/", auth=ProfileAuth(),
             response={200: dict, 403: dict})
@ratelimit(group='condo:invite', key=user_or_ip, rate='10/m', method='POST')
def generate_invite(request, slug: str, fraction_id: str):
    """Generate an invite token for a fraction."""
    from geo.models import CondominiumFraction
    from geo.services.condominium import CondominiumService
    est = _resolve_condo(slug)
    if not _check_condo_admin(request, est):
        raise HttpError(403, "Only OWNER/ADMIN can generate invites")

    f = get_object_or_404(CondominiumFraction, id=fraction_id, establishment=est)
    f.invite_token = CondominiumService.generate_invite_token()
    f.save(update_fields=['invite_token'])

    return {
        'token': f.invite_token,
        'fraction_identifier': f.identifier,
    }


@router.get("/condominiums/invite/{token}/", auth=None, response={200: dict, 404: dict})
@ratelimit(group='condo:invite_info', key='ip', rate='30/m')
def get_invite_info(request, token: str):
    """Get invite info (public, for invite acceptance page)."""
    from geo.models import CondominiumFraction
    f = get_object_or_404(CondominiumFraction, invite_token=token)
    est = f.establishment
    return {
        'fraction_identifier': f.identifier,
        'fraction_type': f.fraction_type,
        'permilagem': f.permilagem,
        'floor': f.floor,
        'condominium_name': est.name,
        'condominium_slug': est.slug,
        'address': est.world_object.full_address if est.world_object else '',
    }


@router.post("/condominiums/invite/{token}/accept/", auth=ProfileAuth(),
             response={200: dict, 400: dict, 404: dict})
@ratelimit(group='condo:invite_accept', key=user_or_ip, rate='10/m', method='POST')
def accept_invite(request, token: str):
    """Accept an invite — link profile to fraction + create membership."""
    from geo.models import CondominiumFraction, EstablishmentMembership
    profile = request.auth

    f = get_object_or_404(CondominiumFraction, invite_token=token)
    est = f.establishment

    if f.resident_id:
        raise HttpError(400, "Fraction already has a resident assigned")

    with transaction.atomic():
        f.resident = profile
        f.invite_token = None  # Consume token
        f.save(update_fields=['resident', 'invite_token'])

        # Create membership if not exists
        EstablishmentMembership.objects.get_or_create(
            profile=profile,
            establishment=est,
            defaults={
                'role': 'MEMBER',
                'membership_level': 'efetivo',
            }
        )

    return {
        'ok': True,
        'condominium_slug': est.slug,
        'fraction_identifier': f.identifier,
    }


@router.get("/condominiums/{slug}/quotas/", auth=ProfileAuth(), response=QuotaPageResponse)
@ratelimit(group='condo:quotas', key=user_or_ip, rate='30/m')
def list_quotas(request, slug: str, month: str = None):
    """Quota overview for all fractions in a given month, with budget metadata and delinquency."""
    from geo.models import CondominiumFraction, QuotaPayment
    est = _resolve_condo(slug)
    if not _check_condo_member(request, est):
        raise HttpError(403, "Not a member of this condominium")

    if not month:
        month = timezone.now().strftime('%Y-%m')

    total_monthly = Decimal(str(est.attributes.get('monthly_budget', '0')))
    is_admin = _check_condo_admin(request, est)

    fractions = (
        CondominiumFraction.objects.filter(establishment=est)
        .select_related('resident')
        .order_by('floor', 'identifier')
    )

    # Payments for selected month
    payments_map = {}
    for p in QuotaPayment.objects.filter(
        fraction__establishment=est, month=month
    ).select_related('fraction', 'confirmed_by'):
        payments_map[p.fraction_id] = p

    # Delinquency: count unpaid months in last 6 months per fraction
    months_to_check = []
    year, mo = int(month[:4]), int(month[5:7])
    for i in range(6):
        months_to_check.append(f"{year:04d}-{mo:02d}")
        mo -= 1
        if mo == 0:
            mo = 12
            year -= 1

    paid_months_map = {}
    if total_monthly > 0:
        for fid, m in QuotaPayment.objects.filter(
            fraction__establishment=est,
            month__in=months_to_check,
            paid_at__isnull=False,
        ).values_list('fraction_id', 'month'):
            paid_months_map.setdefault(fid, set()).add(m)

    items = []
    fractions_paid = 0
    delinquent_count = 0

    for f in fractions:
        quota = (f.permilagem / Decimal('1000.000') * total_monthly).quantize(Decimal('0.01'))
        payment = payments_map.get(f.id)
        is_paid = payment is not None and payment.paid_at is not None
        if is_paid:
            fractions_paid += 1

        paid_months = paid_months_map.get(f.id, set())
        months_unpaid = len(months_to_check) - len(paid_months) if total_monthly > 0 else 0
        if months_unpaid >= 2:
            delinquent_count += 1

        items.append(QuotaOverviewItem(
            fraction_id=f.id,
            identifier=f.identifier,
            permilagem=f.permilagem,
            expected_quota=quota,
            paid=is_paid,
            payment=_format_payment(payment, viewer=request.auth) if payment else None,
            resident_display_name=(f.resident.display_name if f.resident.name_visible_to(request.auth) else f.resident.hna) if f.resident else None,
            resident_id=f.resident_id,
            is_owner=f.is_owner,
            months_unpaid=months_unpaid,
        ))

    return QuotaPageResponse(
        monthly_budget=total_monthly,
        is_admin=is_admin,
        items=items,
        fractions_paid=fractions_paid,
        fractions_total=len(items),
        delinquent_count=delinquent_count,
    )


@router.get("/condominiums/{slug}/financial-summary/", auth=ProfileAuth(),
            response=FinancialSummaryResponse)
@ratelimit(group='condo:financial', key=user_or_ip, rate='30/m')
def financial_summary(request, slug: str, year: int = None):
    """
    Aggregated financial health: annual budget, category breakdown,
    collection rate, outstanding balance, and current-period status.

    Access: condominium members + staff only.
    """
    from django.db.models import Sum
    from geo.models import CondominiumFraction, QuotaPayment
    from treasury.models import BudgetCategory, BudgetEpoch

    est = _resolve_condo(slug)
    if not _check_condo_member(request, est) and not request.auth.account.is_staff:
        raise HttpError(403, "Not a member of this condominium")

    now = timezone.now()
    target_year = year or now.year
    current_year = now.year
    current_month_str = now.strftime('%Y-%m')

    monthly_budget = Decimal(str(est.attributes.get('monthly_budget', '0')))
    annual_budget = (monthly_budget * 12).quantize(Decimal('0.01'))

    # Months elapsed in target year: full year if past, current month if this year, 0 if future
    if target_year < current_year:
        months_elapsed = 12
    elif target_year == current_year:
        months_elapsed = now.month
    else:
        months_elapsed = 0

    # ---- Category breakdown ----
    # Prefer latest finalized BudgetEpoch of target year (median-voted allocation).
    # Fall back to equal-weight split across active categories.
    epoch = (
        BudgetEpoch.objects
        .filter(establishment=est,
                status=BudgetEpoch.Status.FINALIZED,
                label__startswith=f"{target_year:04d}-")
        .order_by('-start_date')
        .first()
    )
    categories: List[FinancialSummaryCategory] = []
    use_epoch = False
    if epoch and epoch.frozen_allocations:
        total_percent = sum(Decimal(str(a.get('median_percent', 0))) for a in epoch.frozen_allocations)
        if total_percent > 0:
            use_epoch = True
            for alloc in epoch.frozen_allocations:
                percent = Decimal(str(alloc.get('median_percent', 0)))
                amount = (annual_budget * percent / Decimal('100')).quantize(Decimal('0.01'))
                categories.append(FinancialSummaryCategory(
                    category_id=alloc.get('category_id'),
                    slug=alloc.get('slug', ''),
                    name=alloc.get('name', ''),
                    percent=percent,
                    annual_amount=amount,
                ))
    if not use_epoch:
        active_cats = list(BudgetCategory.objects.filter(establishment=est, is_active=True).order_by('order', 'name'))
        if active_cats:
            share = Decimal('100') / Decimal(len(active_cats))
            per_amount = (annual_budget / Decimal(len(active_cats))).quantize(Decimal('0.01'))
            for cat in active_cats:
                categories.append(FinancialSummaryCategory(
                    category_id=cat.id,
                    slug=cat.slug,
                    name=cat.name,
                    percent=share.quantize(Decimal('0.01')),
                    annual_amount=per_amount,
                ))

    # ---- Totals ----
    fractions_total = CondominiumFraction.objects.filter(establishment=est).count()

    expected_ytd = (monthly_budget * months_elapsed).quantize(Decimal('0.01'))

    collected_ytd = QuotaPayment.objects.filter(
        fraction__establishment=est,
        month__startswith=f"{target_year:04d}-",
        paid_at__isnull=False,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    collected_ytd = Decimal(collected_ytd).quantize(Decimal('0.01'))

    outstanding_balance = (expected_ytd - collected_ytd).quantize(Decimal('0.01'))
    collection_rate = (
        (collected_ytd / expected_ytd).quantize(Decimal('0.0001'))
        if expected_ytd > 0 else Decimal('0')
    )

    # ---- Current month snapshot (only meaningful for current year) ----
    if target_year == current_year:
        current_month_expected = monthly_budget.quantize(Decimal('0.01'))
        current_month_collected = QuotaPayment.objects.filter(
            fraction__establishment=est,
            month=current_month_str,
            paid_at__isnull=False,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        current_month_collected = Decimal(current_month_collected).quantize(Decimal('0.01'))
        fractions_paid_current = QuotaPayment.objects.filter(
            fraction__establishment=est,
            month=current_month_str,
            paid_at__isnull=False,
        ).values('fraction_id').distinct().count()
    else:
        current_month_expected = Decimal('0.00')
        current_month_collected = Decimal('0.00')
        fractions_paid_current = 0

    return FinancialSummaryResponse(
        year=target_year,
        monthly_budget=monthly_budget.quantize(Decimal('0.01')),
        annual_budget=annual_budget,
        categories=categories,
        current_month=current_month_str,
        months_elapsed=months_elapsed,
        expected_ytd=expected_ytd,
        collected_ytd=collected_ytd,
        outstanding_balance=outstanding_balance,
        collection_rate=collection_rate,
        current_month_expected=current_month_expected,
        current_month_collected=current_month_collected,
        fractions_total=fractions_total,
        fractions_paid_current=fractions_paid_current,
    )


@router.post("/condominiums/{slug}/quotas/", auth=ProfileAuth(),
             response={200: QuotaPaymentResponse, 400: dict, 403: dict})
@ratelimit(group='condo:payment', key=user_or_ip, rate='30/m', method='POST')
def record_payment(request, slug: str, payload: QuotaPaymentInput):
    """Record a quota payment for a fraction."""
    from geo.models import CondominiumFraction, QuotaPayment
    est = _resolve_condo(slug)
    if not _check_condo_admin(request, est):
        raise HttpError(403, "Only OWNER/ADMIN can record payments")

    f = get_object_or_404(CondominiumFraction, id=payload.fraction_id, establishment=est)

    payment, created = QuotaPayment.objects.get_or_create(
        fraction=f,
        month=payload.month,
        defaults={
            'amount': payload.amount,
            'paid_at': timezone.now(),
            'confirmed_by': request.auth,
            'notes': payload.notes,
        }
    )
    if not created:
        # Update existing
        payment.amount = payload.amount
        payment.paid_at = timezone.now()
        payment.confirmed_by = request.auth
        payment.notes = payload.notes
        payment.save(update_fields=['amount', 'paid_at', 'confirmed_by', 'notes'])

    return _format_payment(payment, viewer=request.auth)


@router.put("/condominiums/{slug}/budget/", auth=ProfileAuth(),
            response={200: dict, 403: dict})
@ratelimit(group='condo:budget', key=user_or_ip, rate='10/m', method='PUT')
def update_budget(request, slug: str, payload: BudgetUpdateInput):
    """Update monthly budget for a condominium."""
    est = _resolve_condo(slug)
    if not _check_condo_admin(request, est):
        raise HttpError(403, "Only OWNER/ADMIN can update budget")

    est.attributes['monthly_budget'] = str(payload.monthly_budget)
    est.save(update_fields=['attributes'])

    return {'ok': True, 'monthly_budget': str(payload.monthly_budget)}


class AssemblyListItem(BaseModel):
    id: str
    object_type: str = "poll"
    title: str
    status: str
    created_at: datetime
    end_time: Optional[datetime] = None
    total_eligible: int = 0
    total_voted: int = 0
    quorum_percent: Decimal
    quorum_met: bool = False


@router.get("/condominiums/{slug}/assemblies/", auth=ProfileAuth(), response=List[AssemblyListItem])
@ratelimit(group='condo:assemblies', key=user_or_ip, rate='30/m')
def list_assemblies(request, slug: str):
    """List assembly polls for a condominium, most recent first."""
    from governance.models import Poll, PollContext
    from django.db.models import Count

    est = _resolve_condo(slug)
    if not _check_condo_member(request, est):
        raise HttpError(403, "Not a member of this condominium")

    context = PollContext.objects.filter(context_type='tszh', context_id=est.id).first()
    if not context:
        return []

    # Auto-end expired active polls
    now = timezone.now()
    Poll.objects.filter(
        context=context, status='active', end_time__isnull=False, end_time__lt=now
    ).update(status='ended')

    polls = (
        Poll.objects.filter(context=context)
        .annotate(
            _total_eligible=Count('eligible_voters', distinct=True),
            _total_voted=Count('direct_votes', distinct=True),
        )
        .order_by('-created_at')
    )

    results = []
    for poll in polls:
        total_eligible = poll._total_eligible
        total_voted = poll._total_voted
        if total_eligible > 0:
            turnout = Decimal(total_voted) / Decimal(total_eligible) * Decimal('100')
        else:
            turnout = Decimal('0')
        quorum_met = turnout >= poll.quorum_percent

        results.append(AssemblyListItem(
            id=poll.id,
            title=poll.title,
            status=poll.status,
            created_at=poll.created_at,
            end_time=poll.end_time,
            total_eligible=total_eligible,
            total_voted=total_voted,
            quorum_percent=poll.quorum_percent,
            quorum_met=quorum_met,
        ))

    return results


@router.post("/condominiums/{slug}/assembly/", auth=ProfileAuth(),
             response={200: dict, 400: dict, 403: dict})
@ratelimit(group='condo:assembly', key=user_or_ip, rate='10/m', method='POST')
def create_assembly(request, slug: str, payload: AssemblyInput):
    """Create a condominium assembly poll with weighted voting."""
    from governance.models import Poll, PollOption, PollContext
    from geo.services.condominium import CondominiumService

    est = _resolve_condo(slug)
    if not _check_condo_admin(request, est):
        raise HttpError(403, "Only OWNER/ADMIN can create assembly polls")

    # Map quorum type to percentage
    quorum_map = {
        'simple_majority': 50,
        'two_thirds': 67,
        'unanimity': 100,
    }
    quorum_percent = quorum_map.get(payload.quorum_type, 50)

    with transaction.atomic():
        # Get or create poll context for this condominium
        context, _ = PollContext.objects.get_or_create(
            context_type='tszh',
            context_id=est.id,
            defaults={'created_by': request.auth},
        )

        poll = Poll.objects.create(
            context=context,
            title=payload.title,
            description=payload.description or '',
            created_by=request.auth,
            start_time=timezone.now(),
            end_time=payload.ends_at,
            use_weights=True,
            weight_source='ownership_shares',
            quorum_type='custom',
            quorum_percent=quorum_percent,
            status='active',
        )

        for i, option_text in enumerate(payload.options):
            PollOption.objects.create(
                poll=poll,
                text=option_text,
                order=i,
            )

        # Setup voters from fractions
        voter_count = CondominiumService.setup_poll_voters(poll, est)

    return {
        'poll_id': poll.id,
        'object_type': 'poll',
        'title': poll.title,
        'voter_count': voter_count,
    }
