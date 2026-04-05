"""Universal distribution/payout endpoints for cooperative revenue sharing."""
from ninja import Router, Schema
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
import logging

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

router = Router(tags=["Distributions"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class DistributionInput(Schema):
    object_id: str
    period_label: str
    total_amount: Decimal
    currency: str = 'EUR'
    notes: str = ''


class DistributionResponse(BaseModel):
    id: str
    object_type: str = 'object_distribution'
    object_id: str
    period_label: str
    total_amount: Decimal
    currency: str
    status: str
    merkle_root: str = ''
    notes: str = ''
    lines_count: int = 0
    lines_paid: int = 0
    created_at: datetime


class LineResponse(BaseModel):
    id: str
    object_type: str = 'distribution_line'
    profile_id: str
    profile_name: str = ''
    share_percent: Decimal
    amount: Decimal
    status: str
    created_at: datetime


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/", auth=None, response=List[DistributionResponse])
@ratelimit(group='core:list_distributions', key='ip', rate='60/m')
def list_distributions(request, object_id: str):
    """List distributions for an entity."""
    from core.models import ObjectDistribution

    if not object_id or len(object_id) != 26:
        return []

    return [
        _format_dist(d)
        for d in ObjectDistribution.objects.filter(object_id=object_id)
        .prefetch_related('lines')
    ]


@router.post("/", auth=ProfileAuth(), response={201: DistributionResponse, 400: dict})
@ratelimit(group='core:create_distribution', key=user_or_ip, rate='10/m', method='POST')
def create_distribution(request, data: DistributionInput):
    """Create a draft distribution."""
    from core.models import ObjectDistribution

    if not data.object_id or len(data.object_id) != 26:
        return 400, {"error": "Invalid object_id"}

    if data.total_amount <= 0:
        return 400, {"error": "total_amount must be positive"}

    if not data.period_label:
        return 400, {"error": "period_label required"}

    dist = ObjectDistribution.objects.create(
        object_id=data.object_id,
        period_label=data.period_label,
        total_amount=data.total_amount,
        currency=data.currency,
        notes=data.notes,
        created_by=request.auth,
    )

    return 201, _format_dist(dist)


@router.post("/{dist_id}/approve/", auth=ProfileAuth(), response={200: DistributionResponse, 400: dict, 404: dict})
@ratelimit(group='core:approve_distribution', key=user_or_ip, rate='10/m', method='POST')
def approve_distribution(request, dist_id: str):
    """Approve a draft distribution — generates lines from active shares."""
    from core.models import ObjectDistribution
    from core.services.shares import generate_distribution_lines

    try:
        dist = ObjectDistribution.objects.get(id=dist_id)
    except ObjectDistribution.DoesNotExist:
        return 404, {"error": "Distribution not found"}

    if dist.status != ObjectDistribution.Status.DRAFT:
        return 400, {"error": f"Cannot approve — status is {dist.status}"}

    count = generate_distribution_lines(dist)
    if count == 0:
        return 400, {"error": "No active shares found for this entity"}

    dist.status = ObjectDistribution.Status.APPROVED
    dist.save(update_fields=['status', 'updated_at'])

    dist.refresh_from_db()
    return 200, _format_dist(dist)


@router.get("/{dist_id}/lines/", auth=None, response=List[LineResponse])
@ratelimit(group='core:list_lines', key='ip', rate='60/m')
def list_lines(request, dist_id: str):
    """List payout lines for a distribution."""
    from core.models import DistributionLine

    return [
        _format_line(line)
        for line in DistributionLine.objects.filter(distribution_id=dist_id)
        .select_related('profile')
    ]


@router.post("/{dist_id}/lines/{line_id}/pay/", auth=ProfileAuth(), response={200: LineResponse, 400: dict, 404: dict})
@ratelimit(group='core:pay_line', key=user_or_ip, rate='30/m', method='POST')
def mark_line_paid(request, dist_id: str, line_id: str):
    """Mark a distribution line as paid."""
    from core.models import DistributionLine, ObjectDistribution

    try:
        line = DistributionLine.objects.select_related('profile').get(
            id=line_id, distribution_id=dist_id,
        )
    except DistributionLine.DoesNotExist:
        return 404, {"error": "Line not found"}

    if line.status == DistributionLine.Status.PAID:
        return 400, {"error": "Already paid"}

    line.status = DistributionLine.Status.PAID
    line.save(update_fields=['status', 'updated_at'])

    # Check if all lines are paid → mark distribution as DISTRIBUTED
    dist = line.distribution
    if not dist.lines.filter(status=DistributionLine.Status.PENDING).exists():
        dist.status = ObjectDistribution.Status.DISTRIBUTED
        dist.save(update_fields=['status', 'updated_at'])

    return 200, _format_line(line)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _format_dist(dist) -> DistributionResponse:
    lines = getattr(dist, '_prefetched_objects_cache', {}).get('lines')
    if lines is not None:
        lines_count = len(lines)
        lines_paid = sum(1 for l in lines if l.status == 'PAID')
    else:
        lines_count = dist.lines.count()
        lines_paid = dist.lines.filter(status='PAID').count()

    return DistributionResponse(
        id=dist.id,
        object_id=dist.object_id,
        period_label=dist.period_label,
        total_amount=dist.total_amount,
        currency=dist.currency,
        status=dist.status,
        merkle_root=dist.merkle_root,
        notes=dist.notes,
        lines_count=lines_count,
        lines_paid=lines_paid,
        created_at=dist.created_at,
    )


def _format_line(line) -> LineResponse:
    p = getattr(line, 'profile', None)
    return LineResponse(
        id=line.id,
        profile_id=line.profile_id,
        profile_name=p.display_name if p else '',
        share_percent=line.share_percent,
        amount=line.amount,
        status=line.status,
        created_at=line.created_at,
    )
