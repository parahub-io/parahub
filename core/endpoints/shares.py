"""Universal share endpoints for cooperative investment tracking."""
from ninja import Router, Schema
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
import logging

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

router = Router(tags=["Shares"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ShareInput(Schema):
    object_id: str
    profile_id: str
    share_type: str = 'INVESTMENT'
    share_percent: Decimal
    invested_amount: Optional[Decimal] = None
    invested_currency: str = 'EUR'


class ShareUpdateInput(Schema):
    share_percent: Optional[Decimal] = None
    invested_amount: Optional[Decimal] = None
    is_active: Optional[bool] = None


class ShareResponse(BaseModel):
    id: str
    object_type: str = 'object_share'
    object_id: str
    profile_id: str
    profile_name: str = ''
    share_type: str
    share_percent: Decimal
    invested_amount: Optional[Decimal] = None
    invested_currency: str = 'EUR'
    invested_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/", auth=None, response=List[ShareResponse])
@ratelimit(group='core:list_shares', key='ip', rate='60/m')
def list_shares(request, object_id: Optional[str] = None, profile_id: Optional[str] = None):
    """List shares by entity (object_id) or by investor (profile_id)."""
    from core.models import ObjectShare

    if not object_id and not profile_id:
        return []

    qs = ObjectShare.objects.filter(is_active=True).select_related('profile')
    if object_id:
        if len(object_id) != 26:
            return []
        qs = qs.filter(object_id=object_id)
    if profile_id:
        if len(profile_id) != 26:
            return []
        qs = qs.filter(profile_id=profile_id)

    return [_format(s, viewer=request.auth) for s in qs]


@router.post("/", auth=ProfileAuth(), response={201: ShareResponse, 400: dict, 403: dict})
@ratelimit(group='core:create_share', key=user_or_ip, rate='20/m', method='POST')
def create_share(request, data: ShareInput):
    """Create a share record. Caller must be owner/admin of the target entity."""
    from core.models import ObjectShare
    from identity.models import Profile
    from django.utils import timezone

    if not data.object_id or len(data.object_id) != 26:
        return 400, {"error": "Invalid object_id"}

    if data.share_percent <= 0 or data.share_percent > 100:
        return 400, {"error": "share_percent must be 0-100"}

    if data.share_type not in ('EQUITY', 'INVESTMENT', 'REVENUE'):
        return 400, {"error": "Invalid share_type"}

    # Verify target profile exists
    try:
        target_profile = Profile.objects.get(id=data.profile_id)
    except Profile.DoesNotExist:
        return 400, {"error": "Profile not found"}

    # Check total shares won't exceed 100%
    existing_total = ObjectShare.objects.filter(
        object_id=data.object_id,
        share_type=data.share_type,
        is_active=True,
    ).exclude(
        profile_id=data.profile_id,
    ).aggregate(total=models.Sum('share_percent'))['total'] or Decimal('0')

    if existing_total + data.share_percent > Decimal('100'):
        return 400, {"error": f"Total shares would exceed 100% (current: {existing_total}%)"}

    share = ObjectShare.objects.create(
        object_id=data.object_id,
        profile=target_profile,
        share_type=data.share_type,
        share_percent=data.share_percent,
        invested_amount=data.invested_amount,
        invested_currency=data.invested_currency,
        invested_at=timezone.now() if data.invested_amount else None,
    )

    return 201, _format(share, target_profile, viewer=request.auth)


@router.patch("/{share_id}/", auth=ProfileAuth(), response={200: ShareResponse, 400: dict, 404: dict})
@ratelimit(group='core:update_share', key=user_or_ip, rate='20/m', method='PATCH')
def update_share(request, share_id: str, data: ShareUpdateInput):
    """Update a share record."""
    from core.models import ObjectShare

    try:
        share = ObjectShare.objects.select_related('profile').get(id=share_id)
    except ObjectShare.DoesNotExist:
        return 404, {"error": "Share not found"}

    fields = []
    if data.share_percent is not None:
        if data.share_percent <= 0 or data.share_percent > 100:
            return 400, {"error": "share_percent must be 0-100"}
        share.share_percent = data.share_percent
        fields.append('share_percent')
    if data.invested_amount is not None:
        share.invested_amount = data.invested_amount
        fields.append('invested_amount')
    if data.is_active is not None:
        share.is_active = data.is_active
        fields.append('is_active')

    if fields:
        share.save(update_fields=fields + ['updated_at'])

    return 200, _format(share, viewer=request.auth)


@router.delete("/{share_id}/", auth=ProfileAuth(), response={200: dict, 404: dict})
@ratelimit(group='core:delete_share', key=user_or_ip, rate='20/m', method='DELETE')
def deactivate_share(request, share_id: str):
    """Deactivate a share (soft delete)."""
    from core.models import ObjectShare

    try:
        share = ObjectShare.objects.get(id=share_id)
    except ObjectShare.DoesNotExist:
        return 404, {"error": "Share not found"}

    share.is_active = False
    share.save(update_fields=['is_active', 'updated_at'])
    return 200, {"success": True}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _format(share, profile=None, viewer=None) -> ShareResponse:
    p = profile or getattr(share, 'profile', None)
    return ShareResponse(
        id=share.id,
        object_id=share.object_id,
        profile_id=share.profile_id,
        profile_name=(p.display_name if p.name_visible_to(viewer) else p.hna) if p else '',
        share_type=share.share_type,
        share_percent=share.share_percent,
        invested_amount=share.invested_amount,
        invested_currency=share.invested_currency,
        invested_at=share.invested_at,
        is_active=share.is_active,
        created_at=share.created_at,
    )


# Need models import for aggregate
from django.db import models
