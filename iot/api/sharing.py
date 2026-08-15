"""
Device sharing & ownership: ObjectAccess grants on IoT devices, mesh router
claim-by-MAC flow (unclaimed pool -> claimant), ownership transfer.

Claim model: factory-fresh routers heartbeat into the fleet pool profile
(``MESH_DEFAULT_OWNER_PROFILE_ID``). Anyone holding the physical router proves
possession by typing the full MAC from its sticker; on claim they become its
sole holder of access. No standing support grant is created: the platform never
keeps a key to a router it handed out — an owner who wants remote help grants it
explicitly, and can revoke it. ``MESH_SUPPORT_PROFILE_ID`` is only notified that
a claim happened.
"""

import logging
import re
from datetime import datetime
from typing import List, Optional

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from ninja import Schema
from ninja.errors import HttpError

from core.access import ROLE_MANAGER, ROLE_OWNER
from core.models import ObjectAccess, ObjectActionLog, OwnershipLog
from identity.models import Profile
from parahub.auth import ProfileAuth
from parahub.errors import LocalizedHttpError
from parahub.ratelimit import ratelimit, user_or_ip

from ..models import IoTDevice
from .access import get_device_for
from .base import router

logger = logging.getLogger(__name__)

_MAC_CLEAN_RE = re.compile(r'[^0-9a-f]')
_VALID_ROLES = (ObjectAccess.Role.VIEWER, ObjectAccess.Role.MANAGER)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AccessGrantOut(Schema):
    id: str
    object_type: str = "object_access"
    profile_id: str
    profile_hna: Optional[str] = None
    profile_name: Optional[str] = None
    role: str
    created_at: Optional[datetime] = None


class DeviceAccessOut(Schema):
    device_id: str
    owner_hna: Optional[str] = None
    owner_name: Optional[str] = None
    is_owner: bool
    grants: List[AccessGrantOut]


class ActionLogOut(Schema):
    id: str
    object_type: str = "object_action_log"
    action: str
    role: str
    method: str
    status: int
    fields: List[str] = []
    actor_hna: Optional[str] = None
    actor_name: Optional[str] = None
    created_at: datetime


class GrantIn(Schema):
    handle: str
    role: str = "VIEWER"


class TransferIn(Schema):
    handle: str
    keep_access: bool = True


class ClaimIn(Schema):
    mac: str


class ClaimPreviewOut(Schema):
    name: str
    hardware_profile: Optional[str] = None
    firmware_role: Optional[str] = None
    online: bool
    last_seen: Optional[datetime] = None
    first_seen: Optional[datetime] = None


class ClaimOut(Schema):
    status: str = "claimed"
    device_id: str
    name: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_mac(raw: str) -> str:
    """Accept aa:bb:cc:dd:ee:ff / AA-BB-… / aabbcc… -> canonical lowercase colons."""
    digits = _MAC_CLEAN_RE.sub('', (raw or '').lower())
    if len(digits) != 12:
        raise HttpError(400, "Invalid MAC address")
    return ':'.join(digits[i:i + 2] for i in range(0, 12, 2))


def _resolve_profile(handle: str) -> Profile:
    """Resolve a local_name or full HNA (name@domain) to a Profile."""
    handle = (handle or '').strip().lstrip('@')
    if not handle:
        raise HttpError(400, "Handle required")
    if '@' in handle:
        local_name, domain = handle.split('@', 1)
        profile = Profile.objects.filter(
            local_name=local_name, instance__domain=domain,
        ).select_related('instance').first()
    else:
        profile = Profile.objects.filter(
            local_name=handle, instance__trust_level='local',
        ).select_related('instance').first()
    if not profile:
        raise HttpError(404, "Profile not found")
    return profile


def _find_claimable(mac: str, profile: Profile) -> IoTDevice:
    """Unclaimed pool lookup — only devices still owned by the fleet pool
    profile are claimable, so nobody can claim a router that already has a
    real owner.

    Matches any of the node's burned-in addresses (`hw_macs`, ph45+), not just
    its device_id: device_id is br-private's address at first boot, which on
    some boards is a locally-administered one the bridge invented and that
    appears on no label. Every hw_mac belongs to the same physical box, so any
    of them is equally good proof of possession.

    A router that IS known but already owned answers with its own status
    instead of "unknown MAC": otherwise someone retyping the sticker of a
    router they already claimed gets sent back to check the label, and burns
    the claim budget doing it. This only reveals that a MAC belongs to the
    fleet — never who owns it — and the MAC has to be known in full first.
    """
    pool_id = settings.MESH_DEFAULT_OWNER_PROFILE_ID
    if not pool_id:
        raise HttpError(503, "Claim flow not configured")
    device = IoTDevice.objects.filter(
        Q(device_id=mac) | Q(connection_info__contains={'hw_macs': [mac]}),
        device_type='MESH_ROUTER',
    ).first()
    if not device:
        raise LocalizedHttpError(404, "claim_not_found", "No router with this MAC")
    if device.owner_id == profile.id:
        raise LocalizedHttpError(409, "claim_already_yours",
                                 "This router is already attached to your account")
    if device.owner_id != pool_id:
        raise LocalizedHttpError(409, "claim_already_owned",
                                 "This router is already attached to another account")
    return device


def _grant_payload(grant: ObjectAccess) -> AccessGrantOut:
    p = grant.profile
    return AccessGrantOut(
        id=grant.id,
        profile_id=p.id,
        profile_hna=p.hna or None,
        profile_name=p.display_name or p.local_name,
        role=grant.role,
        created_at=grant.created_at,
    )


def _notify(account, **kwargs):
    """Best-effort notification — sharing must not fail on notifier errors."""
    try:
        from notifications.services import emit_notification
        if account:
            emit_notification(account, **kwargs)
    except Exception as e:
        logger.warning(f"Device sharing notification failed: {e}")


def _online(device: IoTDevice) -> bool:
    return bool(device.last_seen and (timezone.now() - device.last_seen).total_seconds() < 600)


# ---------------------------------------------------------------------------
# Claim flow (mesh routers from the unclaimed pool)
# ---------------------------------------------------------------------------

@router.post("/devices/claim/preview", response=ClaimPreviewOut, auth=ProfileAuth())
@ratelimit(group='iot:claim_preview', key=user_or_ip, rate='30/h', method='POST')
def claim_preview(request, payload: ClaimIn):
    """Look up an unclaimed router by its sticker MAC (no mutation).

    Budgeted apart from the claim itself: a lookup mutates nothing and the
    sticker MAC is easy to mistype (the label may carry the LAN, WAN or radio
    address), so failed searches must not eat the budget of the one call that
    actually transfers ownership.
    """
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")
    device = _find_claimable(_normalize_mac(payload.mac), profile)
    ci = device.connection_info or {}
    return ClaimPreviewOut(
        name=device.name,
        hardware_profile=ci.get('hardware_profile'),
        firmware_role=ci.get('firmware_role'),
        online=_online(device),
        last_seen=device.last_seen,
        first_seen=device.created_at,
    )


@router.post("/devices/claim", response=ClaimOut, auth=ProfileAuth())
@ratelimit(group='iot:claim', key=user_or_ip, rate='10/h', method='POST')
def claim_device(request, payload: ClaimIn):
    """Claim an unclaimed router: the claimant becomes owner and the only party
    with access. Support is notified, but receives no grant."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    mac = _normalize_mac(payload.mac)
    support_id = getattr(settings, 'MESH_SUPPORT_PROFILE_ID', '')

    with transaction.atomic():
        device = _find_claimable(mac, profile)
        pool_profile = device.owner
        device.owner = profile
        device.save(update_fields=['owner'])

        # Claimant's own stale grant (if any) is superseded by ownership
        ObjectAccess.objects.filter(object_id=device.id, profile=profile).delete()

        OwnershipLog.objects.create(
            object_id=device.id,
            action='claim',
            actor=profile,
            previous_owner=pool_profile,
            new_owner=profile,
        )

    # log the device's own id too: the claim may have matched an hw_mac
    logger.info(f"Mesh router {device.device_id} claimed by profile "
                f"{profile.id} (typed {mac})")
    support_profile = (Profile.objects.filter(id=support_id).first()
                       if support_id and support_id != profile.id else None)
    if support_profile:
        _notify(
            support_profile.account,
            type='device_claimed',
            title='Router claimed',
            body=f'{profile.display_name or profile.hna} claimed router {device.name} ({mac}).',
            url='/iot',
            data={'device_id': device.id},
        )
    return ClaimOut(device_id=device.id, name=device.name)


# ---------------------------------------------------------------------------
# Access grants
# ---------------------------------------------------------------------------

@router.get("/devices/{device_id}/access", response=DeviceAccessOut, auth=ProfileAuth())
@ratelimit(group='iot:access_list', key=user_or_ip, rate='60/m')
def list_device_access(request, device_id: str):
    """Grant list for a device. Any access role may view (a grantee sees who
    else has access and can leave); only the owner mutates."""
    profile = request.auth_profile
    device = get_device_for(profile, device_id)
    grants = ObjectAccess.objects.filter(object_id=device.id).select_related(
        'profile__instance').order_by('created_at')
    return DeviceAccessOut(
        device_id=device.id,
        owner_hna=device.owner.hna or None,
        owner_name=device.owner.display_name or device.owner.local_name,
        is_owner=device.owner_id == profile.id,
        grants=[_grant_payload(g) for g in grants],
    )


@router.get("/devices/{device_id}/activity", response=List[ActionLogOut], auth=ProfileAuth())
@ratelimit(group='iot:activity', key=user_or_ip, rate='30/m')
def device_activity(request, device_id: str, limit: int = 50):
    """What was done to this device, by whom, as what role.

    Readable by anyone with access, deliberately: the owner sees what a helper
    changed, and a helper sees that the record of their work is not private to
    the owner. Same audience as the grants list, hence the same name handling.
    """
    profile = request.auth_profile
    device = get_device_for(profile, device_id)
    rows = ObjectActionLog.objects.filter(object_id=device.id).select_related(
        'actor__instance')[:max(1, min(limit, 200))]
    out = []
    for row in rows:
        detail = row.detail or {}
        actor = row.actor
        out.append(ActionLogOut(
            id=row.id,
            action=row.action,
            role=row.role,
            method=detail.get('method', ''),
            status=detail.get('status', 0),
            fields=detail.get('fields', []),
            actor_hna=(actor.hna or None) if actor else None,
            actor_name=(actor.display_name or actor.local_name) if actor else None,
            created_at=row.created_at,
        ))
    return out


@router.post("/devices/{device_id}/access", response=AccessGrantOut, auth=ProfileAuth())
@ratelimit(group='iot:access_grant', key=user_or_ip, rate='20/m', method='POST')
def grant_device_access(request, device_id: str, payload: GrantIn):
    """Share the device with another profile (owner only)."""
    profile = request.auth_profile
    device = get_device_for(profile, device_id, ROLE_OWNER)

    role = (payload.role or '').strip().upper()
    if role not in _VALID_ROLES:
        raise HttpError(400, "Role must be VIEWER or MANAGER")

    target = _resolve_profile(payload.handle)
    if target.id == device.owner_id:
        raise HttpError(400, "Profile already owns this device")

    grant, _created = ObjectAccess.objects.update_or_create(
        object_id=device.id, profile=target,
        defaults={'role': role, 'granted_by': profile},
    )

    _notify(
        target.account,
        type='device_shared',
        title='Device shared with you',
        body=f'{profile.display_name or profile.hna} shared {device.name} with you ({role.lower()}).',
        url='/iot',
        data={'device_id': device.id, 'role': role},
    )
    return _grant_payload(grant)


@router.delete("/devices/{device_id}/access/{grant_id}", auth=ProfileAuth())
@ratelimit(group='iot:access_revoke', key=user_or_ip, rate='30/m', method='DELETE')
def revoke_device_access(request, device_id: str, grant_id: str):
    """Revoke a grant. The owner revokes anyone; a grantee may remove their own."""
    profile = request.auth_profile
    device = get_device_for(profile, device_id)  # any access level to resolve device
    grant = ObjectAccess.objects.filter(id=grant_id, object_id=device.id).first()
    if not grant:
        raise HttpError(404, "Grant not found")
    if device.owner_id != profile.id and grant.profile_id != profile.id:
        raise HttpError(403, "Only the owner or the grantee can revoke this grant")
    grant.delete()
    return {"success": True}


# ---------------------------------------------------------------------------
# Ownership transfer
# ---------------------------------------------------------------------------

@router.post("/devices/{device_id}/transfer", response=DeviceAccessOut, auth=ProfileAuth())
@ratelimit(group='iot:transfer', key=user_or_ip, rate='10/h', method='POST')
def transfer_device(request, device_id: str, payload: TransferIn):
    """Transfer ownership to another profile (owner only). ``keep_access``
    leaves the previous owner a revocable MANAGER grant."""
    profile = request.auth_profile
    device = get_device_for(profile, device_id, ROLE_OWNER)

    target = _resolve_profile(payload.handle)
    if target.id == profile.id:
        raise HttpError(400, "Device is already yours")

    with transaction.atomic():
        device.owner = target
        device.save(update_fields=['owner'])

        # New owner's grant (if any) is superseded by ownership
        ObjectAccess.objects.filter(object_id=device.id, profile=target).delete()

        if payload.keep_access:
            ObjectAccess.objects.update_or_create(
                object_id=device.id, profile=profile,
                defaults={'role': ObjectAccess.Role.MANAGER, 'granted_by': profile},
            )

        OwnershipLog.objects.create(
            object_id=device.id,
            action='transfer',
            actor=profile,
            previous_owner=profile,
            new_owner=target,
        )

    _notify(
        target.account,
        type='device_transferred',
        title='Device transferred to you',
        body=f'{profile.display_name or profile.hna} transferred {device.name} to you.',
        url='/iot',
        data={'device_id': device.id},
    )

    grants = ObjectAccess.objects.filter(object_id=device.id).select_related(
        'profile__instance').order_by('created_at')
    return DeviceAccessOut(
        device_id=device.id,
        owner_hna=target.hna or None,
        owner_name=target.display_name or target.local_name,
        is_owner=False,
        grants=[_grant_payload(g) for g in grants],
    )
