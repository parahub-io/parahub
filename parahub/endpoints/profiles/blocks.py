"""User blocking endpoints (Play UGC policy: block users with real effect).

NOTE: this module MUST be imported before ``core`` in ``__init__.py`` — the
literal ``GET /blocked/`` route would otherwise be swallowed by core's
``/{id}/`` param route (registration order = import order, see
PK/architecture.md § Ninja path shadowing).
"""

from datetime import datetime
from typing import List, Optional

from django.shortcuts import get_object_or_404
from pydantic import BaseModel
import logging

from parahub.auth import ProfileAuth
from parahub.errors import LocalizedHttpError
from parahub.ratelimit import ratelimit, user_or_ip
from identity.models import Profile

from .base import profile_router

logger = logging.getLogger(__name__)


class BlockedProfileResponse(BaseModel):
    id: str
    object_type: str = 'profile'
    local_name: str
    hna: str
    display_name: str = ''
    avatar_url: Optional[str] = None
    blocked_at: datetime


class BlockedListResponse(BaseModel):
    items: List[BlockedProfileResponse]
    count: int


def _resolve_profile(id: str) -> Profile:
    if len(id) == 26 and id.isalnum():
        return get_object_or_404(Profile, id=id)
    return get_object_or_404(Profile, local_name=id)


@profile_router.get('/blocked/', response=BlockedListResponse, auth=ProfileAuth())
@ratelimit(group='profiles:list_blocked', key=user_or_ip, rate='60/m')
def list_blocked_profiles(request):
    """Profiles blocked by any of the viewer's own profiles."""
    from identity.models import ProfileBlock

    blocks = (
        ProfileBlock.objects
        .filter(blocker__account_id=request.auth.account_id)
        .select_related('blocked', 'blocked__instance')
        .order_by('-created_at')
    )
    items = [
        BlockedProfileResponse(
            id=b.blocked.id,
            local_name=b.blocked.local_name,
            hna=b.blocked.hna,
            display_name=b.blocked.display_name if b.blocked.name_public else '',
            avatar_url=b.blocked.avatar_url,
            blocked_at=b.created_at,
        )
        for b in blocks
    ]
    return BlockedListResponse(items=items, count=len(items))


@profile_router.post('/{id}/block/', response={201: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:block', key=user_or_ip, rate='30/m', method='POST')
def block_profile(request, id: str):
    """Block a profile: hides their content from the viewer and refuses new DMs."""
    from identity.models import ProfileBlock

    target = _resolve_profile(id)
    blocker = request.auth

    if target.account_id == blocker.account_id:
        raise LocalizedHttpError(400, "block_own_profile", "You cannot block your own profile")

    _, created = ProfileBlock.objects.get_or_create(blocker=blocker, blocked=target)
    if created:
        logger.info(f"Profile {blocker.id} blocked {target.id}")
    return 201, {"success": True, "blocked_id": target.id}


@profile_router.delete('/{id}/block/', response={200: dict}, auth=ProfileAuth())
@ratelimit(group='profiles:unblock', key=user_or_ip, rate='30/m', method='DELETE')
def unblock_profile(request, id: str):
    """Remove a block created by any of the viewer's own profiles."""
    from identity.models import ProfileBlock

    target = _resolve_profile(id)
    deleted, _ = ProfileBlock.objects.filter(
        blocker__account_id=request.auth.account_id, blocked=target,
    ).delete()
    if deleted:
        logger.info(f"Account {request.auth.account_id} unblocked {target.id}")
    return 200, {"success": True, "unblocked": bool(deleted)}
