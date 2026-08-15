"""
Platform authority — the node owner's grant screen.

`parahub/capabilities.py` defines the four node-level capabilities and reads
them off the Account's Django groups; this router is the surface that hands
them out, so appointing a moderator or a federation admin no longer means
opening Django admin (and no longer means `is_staff` as a shortcut).

Granting is superuser-only, deliberately: `is_staff` already resolves to every
capability, so letting staff grant them would make the set self-propagating.
See `require_superuser`.
"""
import logging
from typing import List, Optional

from django.contrib.auth.models import Group
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import BaseModel

from parahub.auth import ProfileAuth
from parahub.capabilities import (
    PLATFORM_CAPABILITIES, PLATFORM_CAPABILITY_INFO, require_superuser,
)
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

router = Router(tags=["Platform"])


# ── Schemas ────────────────────────────────────────────────────────────

class HolderOut(BaseModel):
    account_id: str
    username: str
    display_name: str = ''
    local_name: str = ''
    avatar_url: str = ''
    is_staff: bool = False
    #: True when the account holds the capability through `is_staff` rather than
    #: through the group — the screen must not offer to revoke what it cannot.
    implicit: bool = False


class CapabilityOut(BaseModel):
    key: str
    group: str
    label: str
    description: str
    holders: List[HolderOut] = []


class GrantIn(Schema):
    username: str


# ── Helpers ────────────────────────────────────────────────────────────

def _capability_group(capability: str) -> Group:
    """The Django group behind a capability, created on first use."""
    group_name = PLATFORM_CAPABILITIES.get(capability)
    if not group_name:
        raise HttpError(404, f"Unknown platform capability: {capability}")
    group, _ = Group.objects.get_or_create(name=group_name)
    return group


def _primary_profiles(account_ids):
    """account_id → primary Profile, for putting a face on a username."""
    from identity.models import Profile

    profiles = {}
    for p in Profile.objects.filter(account_id__in=account_ids, is_primary=True):
        profiles[p.account_id] = p
    return profiles


def _holder(account, profile) -> HolderOut:
    return HolderOut(
        account_id=account.id,
        username=account.username,
        display_name=(profile.display_name if profile else '') or '',
        local_name=(profile.local_name if profile else '') or '',
        avatar_url=(profile.avatar_url or '') if profile else '',
        is_staff=account.is_staff,
        implicit=account.is_staff,
    )


def _notify(account, *, granted: bool, capability: str):
    """Delegation nobody is told about is not delegation."""
    try:
        from notifications.services import emit_notification

        label = PLATFORM_CAPABILITY_INFO.get(capability, (capability, ''))[0]
        emit_notification(
            account,
            # Deliberately outside TYPE_TO_CATEGORY: a change to what you may do
            # on this node is not a preference-muteable social ping.
            type='platform_capability_granted' if granted else 'platform_capability_revoked',
            title=label,
            body=(f"You now hold '{capability}' on this node."
                  if granted else f"'{capability}' was withdrawn from your login."),
            url='/iot?tab=infra',
            data={'capability': capability},
        )
    except Exception as e:
        logger.warning(f"Capability notification failed: {e}")


# ── Endpoints ──────────────────────────────────────────────────────────

@router.get("/capabilities/", auth=ProfileAuth(), response=List[CapabilityOut])
@ratelimit(group='platform:list_capabilities', key=user_or_ip, rate='60/m')
def list_capabilities(request):
    """Every platform capability and who holds it. Node owner only."""
    require_superuser(request)
    from identity.models import Account

    groups = {g.name: g for g in Group.objects.filter(name__in=PLATFORM_CAPABILITIES.values())}
    staff = list(Account.objects.filter(is_staff=True, is_active=True).order_by('username'))
    profiles = _primary_profiles(
        [a.id for a in staff]
        + list(Account.objects.filter(groups__name__in=PLATFORM_CAPABILITIES.values())
               .values_list('id', flat=True))
    )

    out = []
    for key, group_name in PLATFORM_CAPABILITIES.items():
        label, description = PLATFORM_CAPABILITY_INFO.get(key, (key, ''))
        group = groups.get(group_name)
        members = list(group.user_set.filter(is_active=True).order_by('username')) if group else []
        member_ids = {a.id for a in members}
        holders = [_holder(a, profiles.get(a.id)) for a in members]
        # Staff hold everything by override; show them so the list answers
        # "who can do this today", not "whose row exists".
        holders += [_holder(a, profiles.get(a.id)) for a in staff if a.id not in member_ids]
        out.append(CapabilityOut(
            key=key, group=group_name, label=label, description=description, holders=holders,
        ))
    return out


@router.get("/accounts/", auth=ProfileAuth(), response=List[HolderOut])
@ratelimit(group='platform:search_accounts', key=user_or_ip, rate='60/m')
def search_accounts(request, q: str = '', limit: int = 10):
    """Find a login to appoint, by username or by the name on its primary profile."""
    require_superuser(request)
    from django.db.models import Q
    from identity.models import Account

    q = (q or '').strip()
    if len(q) < 2:
        return []

    accounts = list(Account.objects.filter(
        Q(username__icontains=q)
        | Q(profiles__display_name__icontains=q)
        | Q(profiles__local_name__icontains=q),
        is_active=True,
    ).distinct().order_by('username')[:max(1, min(limit, 25))])

    profiles = _primary_profiles([a.id for a in accounts])
    return [_holder(a, profiles.get(a.id)) for a in accounts]


@router.post("/capabilities/{capability}/holders/", auth=ProfileAuth(),
             response={200: HolderOut, 400: dict, 403: dict, 404: dict})
@ratelimit(group='platform:grant', key=user_or_ip, rate='30/m', method='POST')
def grant_capability(request, capability: str, data: GrantIn):
    """Put a login in the capability's group. Node owner only."""
    actor = require_superuser(request)
    from identity.models import Account

    group = _capability_group(capability)
    account = Account.objects.filter(username=data.username, is_active=True).first()
    if account is None:
        raise HttpError(404, "No such login")

    already = account.groups.filter(pk=group.pk).exists()
    if not already:
        account.groups.add(group)
        logger.info(f"Platform capability {capability} granted to {account.username} "
                    f"by {actor.username}")
        _notify(account, granted=True, capability=capability)

    profile = _primary_profiles([account.id]).get(account.id)
    return 200, _holder(account, profile)


@router.delete("/capabilities/{capability}/holders/{username}/", auth=ProfileAuth(),
               response={200: dict, 400: dict, 403: dict, 404: dict})
@ratelimit(group='platform:revoke', key=user_or_ip, rate='30/m', method='DELETE')
def revoke_capability(request, capability: str, username: str):
    """Take a login out of the capability's group. Node owner only."""
    actor = require_superuser(request)
    from identity.models import Account

    group = _capability_group(capability)
    account = Account.objects.filter(username=username).first()
    if account is None:
        raise HttpError(404, "No such login")

    if account.groups.filter(pk=group.pk).exists():
        account.groups.remove(group)
        logger.info(f"Platform capability {capability} revoked from {account.username} "
                    f"by {actor.username}")
        _notify(account, granted=False, capability=capability)

    # Staff keep the capability by override; say so rather than let the screen
    # claim a revoke that changed nothing.
    return 200, {'success': True, 'still_holds': bool(account.is_staff)}
