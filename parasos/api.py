"""
ParaSOS API — neighborhood emergency mutual aid.

Endpoints:
  Groups: CRUD, join/leave, nearby search
  SOS: send alert, respond, resolve
"""

from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import paginate, PageNumberPagination
from typing import Dict, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from parahub.background import spawn, PRIORITY_URGENT
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db.models import Q, F
from django.utils import timezone

from parahub.auth import ProfileAuth
from identity.visibility import exclude_test_authors
from parahub.ratelimit import ratelimit, user_or_ip

logger = logging.getLogger(__name__)

router = Router(tags=["ParaSOS"])


# ===== Schemas =====

class LocationInput(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class GroupCreateInput(BaseModel):
    name: str = Field(..., max_length=255, min_length=2)
    description: str = Field(default="", max_length=2000)
    visibility: str = Field(default="PUBLIC", pattern="^(PUBLIC|PRIVATE)$")
    center: Optional[LocationInput] = None
    radius_m: Optional[int] = Field(default=1000, ge=100, le=10000)
    world_object_id: Optional[str] = None
    quiet_hours_start: Optional[int] = Field(None, ge=0, le=23)
    quiet_hours_end: Optional[int] = Field(None, ge=0, le=23)


class GroupUpdateInput(BaseModel):
    name: Optional[str] = Field(None, max_length=255, min_length=2)
    description: Optional[str] = Field(None, max_length=2000)
    visibility: Optional[str] = Field(None, pattern="^(PUBLIC|PRIVATE)$")
    radius_m: Optional[int] = Field(None, ge=100, le=10000)
    quiet_hours_start: Optional[int] = Field(None, ge=0, le=23)
    quiet_hours_end: Optional[int] = Field(None, ge=0, le=23)
    is_active: Optional[bool] = None


class MemberInfo(BaseModel):
    id: str
    profile_id: str
    profile_hna: Optional[str]
    profile_display_name: Optional[str]
    profile_avatar_url: Optional[str]
    role: str
    presence: str
    joined_at: datetime


class GroupResponse(BaseModel):
    id: str
    object_type: str = "safety_group"
    name: str
    description: str
    visibility: str
    center: Optional[Dict[str, float]] = None
    radius_m: Optional[int] = None
    world_object_id: Optional[str] = None
    matrix_room_id: Optional[str] = None
    is_active: bool
    quiet_hours_start: Optional[int] = None
    quiet_hours_end: Optional[int] = None
    members_count: int
    is_member: bool = False
    is_admin: bool = False
    my_membership_id: Optional[str] = None
    created_at: datetime


class GroupListItem(BaseModel):
    id: str
    object_type: str = "safety_group"
    name: str
    description: str
    visibility: str
    center: Optional[Dict[str, float]] = None
    radius_m: Optional[int] = None
    is_active: bool
    members_count: int
    created_at: datetime


class InviteResponse(BaseModel):
    id: str
    object_type: str = "group_invite"
    token: str
    label: str
    max_uses: int
    uses_count: int
    expires_at: Optional[datetime] = None
    is_active: bool
    is_valid: bool
    created_at: datetime


class InviteCreateInput(BaseModel):
    label: str = Field(default="", max_length=100)
    max_uses: int = Field(default=0, ge=0)
    expires_hours: Optional[int] = Field(None, ge=1, le=8760, description="Hours until expiry")


class JoinGroupInput(BaseModel):
    presence: str = Field(default="LOCAL", pattern="^(LOCAL|REMOTE)$")
    emergency_context: str = Field(default="", max_length=2000)
    invite_token: Optional[str] = None


class SOSInput(BaseModel):
    level: str = Field(..., pattern="^(INFO|WARNING|EMERGENCY)$")
    category: str = Field(default="OTHER", pattern="^(SUSPICIOUS_ACTIVITY|ALARM_TRIGGERED|MEDICAL|FIRE|INTRUSION|OTHER)$")
    message: str = Field(default="", max_length=1000)
    location: Optional[LocationInput] = None


class SOSResponseInput(BaseModel):
    status: str = Field(..., pattern="^(SEEN|ON_WAY|ON_SITE|UNABLE)$")
    note: str = Field(default="", max_length=1000)


class AlertSenderInfo(BaseModel):
    id: str
    hna: Optional[str]
    display_name: Optional[str]
    avatar_url: Optional[str]


class ResponderInfo(BaseModel):
    id: str
    responder_id: str
    responder_hna: Optional[str]
    responder_display_name: Optional[str]
    responder_avatar_url: Optional[str]
    status: str
    note: str
    created_at: datetime
    updated_at: datetime


class AlertResponse(BaseModel):
    id: str
    object_type: str = "sos_alert"
    group_id: str
    group_name: str
    sender: AlertSenderInfo
    level: str
    category: str
    source: str
    message: str
    location: Optional[Dict[str, float]]
    status: str
    seen_count: int
    responding_count: int
    resolved_at: Optional[datetime]
    created_at: datetime


class AlertListItem(BaseModel):
    id: str
    object_type: str = "sos_alert"
    group_id: str
    group_name: str
    sender_hna: Optional[str]
    sender_display_name: Optional[str]
    level: str
    category: str
    status: str
    message: str
    seen_count: int
    responding_count: int
    created_at: datetime


# ===== Helpers =====

def _get_group_for_member(group_id: str, profile, require_member: bool = True):
    """Fetch a group enforcing membership visibility.

    PRIVATE groups 404 for non-members (existence stays hidden);
    PUBLIC groups 403 when membership is required.
    Returns (group, is_member).
    """
    from parasos.models import SafetyGroup, SafetyGroupMember

    group = get_object_or_404(SafetyGroup, id=group_id)
    is_member = SafetyGroupMember.objects.filter(group=group, profile=profile).exists()
    if not is_member:
        if group.visibility == SafetyGroup.Visibility.PRIVATE:
            raise HttpError(404, "Not found")
        if require_member:
            raise HttpError(403, "Must be a group member")
    return group, is_member


def _format_group_list_item(g) -> GroupListItem:
    return GroupListItem(
        id=g.id,
        name=g.name,
        description=g.description,
        visibility=g.visibility,
        center={"lat": g.center.y, "lon": g.center.x} if g.center else None,
        radius_m=g.radius_m,
        is_active=g.is_active,
        members_count=g.members_count,
        created_at=g.created_at,
    )


def _format_group_response(group, current_profile=None) -> GroupResponse:
    is_member = False
    is_admin = False
    membership_id = None

    if current_profile:
        from parasos.models import SafetyGroupMember
        membership = SafetyGroupMember.objects.filter(
            group=group, profile=current_profile,
        ).first()
        if membership:
            is_member = True
            is_admin = membership.role == SafetyGroupMember.Role.ADMIN
            membership_id = membership.id

    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        visibility=group.visibility,
        center={"lat": group.center.y, "lon": group.center.x} if group.center else None,
        radius_m=group.radius_m,
        world_object_id=group.world_object_id,
        matrix_room_id=group.matrix_room_id if is_member else None,
        is_active=group.is_active,
        quiet_hours_start=group.quiet_hours_start,
        quiet_hours_end=group.quiet_hours_end,
        members_count=group.members_count,
        is_member=is_member,
        is_admin=is_admin,
        my_membership_id=membership_id,
        created_at=group.created_at,
    )


def _format_alert_response(alert) -> AlertResponse:
    sender = alert.sender
    location = None
    if alert.location:
        location = {"lat": alert.location.y, "lon": alert.location.x}

    return AlertResponse(
        id=alert.id,
        group_id=alert.group_id,
        group_name=alert.group.name,
        sender=AlertSenderInfo(
            id=sender.id,
            hna=sender.hna,
            display_name=sender.display_name,
            avatar_url=sender.avatar_url,
        ),
        level=alert.level,
        category=alert.category,
        source=alert.source,
        message=alert.message,
        location=location,
        status=alert.status,
        seen_count=alert.seen_count,
        responding_count=alert.responding_count,
        resolved_at=alert.resolved_at,
        created_at=alert.created_at,
    )


def _create_group_matrix_room(group, creator_account_id) -> Optional[str]:
    """Create Matrix chat room for safety group."""
    import httpx
    from django.conf import settings

    try:
        SYNAPSE_BASE_URL = getattr(settings, 'SYNAPSE_INTERNAL_URL', 'http://localhost:8008')
        SYNAPSE_ADMIN_TOKEN = getattr(settings, 'SYNAPSE_ADMIN_TOKEN', None)
        if not SYNAPSE_ADMIN_TOKEN:
            return None

        from parahub.endpoints.matrix_auth import _get_or_create_matrix_token
        token = _get_or_create_matrix_token(creator_account_id)
        if not token:
            return None

        with httpx.Client(timeout=10) as client:
            # invite-only join rule: SOS notices (locations, medical context)
            # must not be readable by anyone who learns the room id
            resp = client.post(
                f"{SYNAPSE_BASE_URL}/_matrix/client/r0/createRoom",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "preset": "private_chat",
                    "name": f"ParaSOS: {group.name}",
                    "topic": f"Emergency mutual aid group — {group.name}",
                    "visibility": "private",
                    "initial_state": [],
                },
            )
            if resp.status_code in (200, 201):
                room_id = resp.json().get("room_id")
                logger.info(f"Created Matrix room {room_id} for safety group {group.id}")
                return room_id
            else:
                logger.error(f"Failed to create Matrix room for safety group: {resp.text}")
    except Exception as e:
        logger.error(f"Error creating Matrix room for safety group {group.id}: {e}")
    return None


def _ensure_live_group_room(group, actor_profile):
    """Return (room_id, joined_members) for a live group room, recreating it
    when the current one is positively dead.

    A room every local user has left can never be joined again (the join
    falls through to federation and no other homeserver is in the room), so
    the only recovery is a fresh room. Members are re-added in the background.
    joined_members is None when current membership could not be determined.
    """
    from parahub.endpoints.matrix_auth import get_room_joined_members, purge_matrix_room
    from parasos.models import SafetyGroup, SafetyGroupMember

    old_room_id = group.matrix_room_id
    if old_room_id:
        members = get_room_joined_members(old_room_id)
        if members is None or members:
            return old_room_id, members

    # Positively dead (or never created) — recreate, preferring the group
    # creator as room owner so power levels stay with them
    new_room_id = _create_group_matrix_room(group, group.created_by.account_id)
    if not new_room_id and actor_profile is not None:
        new_room_id = _create_group_matrix_room(group, actor_profile.account_id)
    if not new_room_id:
        return None, None

    swapped = SafetyGroup.objects.filter(
        id=group.id, matrix_room_id=old_room_id,
    ).update(matrix_room_id=new_room_id)
    if not swapped:
        # Lost the race to a concurrent heal — abandon ours, adopt the winner's
        purge_matrix_room(new_room_id)
        group.refresh_from_db(fields=['matrix_room_id'])
        return (group.matrix_room_id or None), None

    group.matrix_room_id = new_room_id
    SafetyGroupMember.objects.filter(group=group).update(joined_matrix_room=False)
    logger.info(
        f"Recreated Matrix room for safety group {group.id}: "
        f"{old_room_id or '(none)'} -> {new_room_id}"
    )

    def _cleanup_and_readd():
        if old_room_id:
            purge_matrix_room(old_room_id)
        _readd_group_members(group)

    spawn(_cleanup_and_readd, label=f"parasos-room-heal-{group.id}")
    return new_room_id, None


def _invite_and_join_group_room(group, room_id, joined_members, profile) -> bool:
    """Invite + join user into an invite-only group room.

    The invite must come from someone actually joined: normally the creator,
    otherwise any joined member (the backend can mint any local user's token).
    Individual invite failures are tolerated — the join is the arbiter.
    """
    import httpx
    from django.conf import settings
    from parahub.endpoints.matrix_auth import (
        _get_or_create_matrix_token,
        get_account_id_for_matrix_user,
        get_matrix_user_id,
    )

    try:
        SYNAPSE_BASE_URL = getattr(settings, 'SYNAPSE_INTERNAL_URL', 'http://localhost:8008')
        token = _get_or_create_matrix_token(profile.account_id)
        if not token:
            return False

        user_mxid = get_matrix_user_id(profile.account_id)
        creator_account_id = group.created_by.account_id
        creator_mxid = get_matrix_user_id(creator_account_id)

        inviter_account_ids = []
        if joined_members is None or creator_mxid in joined_members:
            inviter_account_ids.append(creator_account_id)
        for mxid in joined_members or []:
            if mxid in (creator_mxid, user_mxid):
                continue
            account_id = get_account_id_for_matrix_user(mxid)
            if account_id:
                inviter_account_ids.append(account_id)
                break

        with httpx.Client(timeout=10) as client:
            already_joined = user_mxid in (joined_members or [])
            if not already_joined:
                for inviter_account_id in inviter_account_ids:
                    inviter_token = _get_or_create_matrix_token(inviter_account_id)
                    if not inviter_token:
                        continue
                    inv = client.post(
                        f"{SYNAPSE_BASE_URL}/_matrix/client/r0/rooms/{room_id}/invite",
                        headers={"Authorization": f"Bearer {inviter_token}"},
                        json={"user_id": user_mxid},
                    )
                    # 403 usually means "already in the room" — the join decides
                    if inv.status_code in (200, 201, 403):
                        break
                    logger.warning(
                        f"Matrix invite failed for safety group {group.id}: {inv.text}"
                    )

            resp = client.post(
                f"{SYNAPSE_BASE_URL}/_matrix/client/r0/rooms/{room_id}/join",
                headers={"Authorization": f"Bearer {token}"},
                json={},
            )
            return resp.status_code in (200, 201)
    except Exception as e:
        logger.error(f"Error joining Matrix room for safety group {group.id}: {e}")
    return False


def _join_group_matrix_room(group, profile) -> bool:
    """Add user to the group's Matrix room, healing a dead room first."""
    room_id, joined_members = _ensure_live_group_room(group, profile)
    if not room_id:
        return False
    return _invite_and_join_group_room(group, room_id, joined_members, profile)


def _readd_group_members(group):
    """Re-add current group members to a freshly recreated room.

    Runs in a background thread — sequential HTTP per member. Members whose
    Matrix user cannot be resolved keep joined_matrix_room=False.
    """
    from parasos.models import SafetyGroupMember

    for member in SafetyGroupMember.objects.filter(group=group).select_related('profile'):
        try:
            if _invite_and_join_group_room(group, group.matrix_room_id, None, member.profile):
                member.joined_matrix_room = True
                member.save(update_fields=['joined_matrix_room'])
        except Exception as e:
            logger.warning(
                f"Failed to re-add member {member.profile_id} to Matrix room "
                f"of safety group {group.id}: {e}"
            )


def _leave_group_matrix_room(group, profile):
    """Remove a departed group member from the invite-only Matrix room
    (background thread) — ex-members must not keep receiving SOS notices
    (locations, medical context).

    Self-leave with the member's own token; falls back to a kick by the
    creator (room admin) when the member's token cannot be minted.
    """
    import httpx
    from django.conf import settings

    room_id = group.matrix_room_id
    if not room_id:
        return

    def _leave():
        try:
            from parahub.endpoints.matrix_auth import (
                _get_or_create_matrix_token,
                get_matrix_user_id,
                get_room_joined_members,
            )

            user_mxid = get_matrix_user_id(profile.account_id)
            joined_members = get_room_joined_members(room_id)
            if joined_members is not None and user_mxid not in joined_members:
                return  # never entered the chat (or already out)

            SYNAPSE_BASE_URL = getattr(settings, 'SYNAPSE_INTERNAL_URL', 'http://localhost:8008')
            with httpx.Client(timeout=10) as client:
                token = _get_or_create_matrix_token(profile.account_id)
                if token:
                    resp = client.post(
                        f"{SYNAPSE_BASE_URL}/_matrix/client/r0/rooms/{room_id}/leave",
                        headers={"Authorization": f"Bearer {token}"},
                        json={},
                    )
                    if resp.status_code in (200, 201):
                        return

                creator_token = _get_or_create_matrix_token(group.created_by.account_id)
                if not creator_token:
                    logger.warning(
                        f"Could not remove {user_mxid} from Matrix room of "
                        f"safety group {group.id}: no usable token"
                    )
                    return
                resp = client.post(
                    f"{SYNAPSE_BASE_URL}/_matrix/client/r0/rooms/{room_id}/kick",
                    headers={"Authorization": f"Bearer {creator_token}"},
                    json={"user_id": user_mxid, "reason": "Left the safety group"},
                )
                if resp.status_code not in (200, 201):
                    logger.warning(
                        f"Matrix kick failed for safety group {group.id} "
                        f"({resp.status_code}): {resp.text[:200]}"
                    )
        except Exception as e:
            logger.warning(
                f"Failed to remove member from Matrix room of safety group {group.id}: {e}"
            )

    spawn(_leave, label=f"parasos-room-leave-{group.id}")


def _send_matrix_sos_notice(group, alert):
    """Send SOS notice to group's Matrix room (async in thread).

    Sent as the alert sender \u2014 a room member. Synapse rejects sends from
    non-members, and the admin user is in no group room, so an admin-token
    send would silently fail.
    """
    import httpx
    from django.conf import settings

    def _send():
        try:
            from parahub.endpoints.matrix_auth import (
                _get_or_create_matrix_token,
                get_matrix_user_id,
            )

            room_id, joined_members = _ensure_live_group_room(group, alert.sender)
            if not room_id:
                logger.warning(f"No Matrix room for SOS notice, safety group {group.id}")
                return

            sender_mxid = get_matrix_user_id(alert.sender.account_id)
            if joined_members is not None and sender_mxid not in joined_members:
                _invite_and_join_group_room(group, room_id, joined_members, alert.sender)

            token = _get_or_create_matrix_token(alert.sender.account_id)
            if not token:
                logger.warning(f"No Matrix token for SOS sender {alert.sender_id}")
                return

            base_url = getattr(settings, 'SYNAPSE_INTERNAL_URL', 'http://localhost:8008')
            level_emoji = {"INFO": "\u2139\ufe0f", "WARNING": "\u26a0\ufe0f", "EMERGENCY": "\U0001f6a8"}
            emoji = level_emoji.get(alert.level, "")
            sender_name = alert.sender.display_name or alert.sender.hna or "Someone"
            body = f"{emoji} SOS [{alert.level}]: {sender_name}"
            if alert.message:
                body += f" — {alert.message}"
            if alert.category != 'OTHER':
                body += f" ({alert.get_category_display()})"

            import uuid
            with httpx.Client(timeout=10) as client:
                resp = client.put(
                    f"{base_url}/_matrix/client/r0/rooms/{room_id}/send/m.room.message/{uuid.uuid4()}",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"msgtype": "m.notice", "body": body},
                )
                if resp.status_code not in (200, 201):
                    logger.warning(
                        f"Matrix SOS notice send failed ({resp.status_code}): {resp.text[:200]}"
                    )
        except Exception as e:
            logger.warning(f"Failed to send Matrix SOS notice: {e}")

    # SOS is latency-sensitive — jump ahead of bulk background work
    spawn(_send, priority=PRIORITY_URGENT)


def _notify_group_members(group, alert):
    """Send push notifications to group members based on their preferences."""
    from parasos.models import SafetyGroupMember
    from notifications.services import send_push_notification

    members = SafetyGroupMember.objects.filter(
        group=group,
    ).exclude(
        profile=alert.sender,
    ).select_related('profile', 'profile__account')

    now = timezone.now()
    current_hour = now.hour

    # Check quiet hours for INFO level
    in_quiet_hours = False
    if group.quiet_hours_start is not None and group.quiet_hours_end is not None:
        if group.quiet_hours_start <= group.quiet_hours_end:
            in_quiet_hours = group.quiet_hours_start <= current_hour < group.quiet_hours_end
        else:
            in_quiet_hours = current_hour >= group.quiet_hours_start or current_hour < group.quiet_hours_end

    level_emoji = {"INFO": "\u2139\ufe0f", "WARNING": "\u26a0\ufe0f", "EMERGENCY": "\U0001f6a8"}
    emoji = level_emoji.get(alert.level, "")
    sender_name = alert.sender.display_name or alert.sender.hna or "Someone"

    title = f"{emoji} ParaSOS: {group.name}"
    body = f"{sender_name} — {alert.get_level_display()}"
    if alert.message:
        body += f": {alert.message}"

    def _send_all():
        for member in members:
            # Check notification preferences
            if alert.level == 'INFO' and not member.notify_info:
                continue
            if alert.level == 'WARNING' and not member.notify_warning:
                continue
            if alert.level == 'EMERGENCY' and not member.notify_emergency:
                continue

            # Quiet hours (INFO only, WARNING/EMERGENCY always go through)
            if alert.level == 'INFO' and in_quiet_hours and not member.quiet_hours_override:
                continue

            try:
                send_push_notification(
                    member.profile.account,
                    title, body,
                    data={
                        'type': 'sos_alert',
                        'alert_id': alert.id,
                        'group_id': group.id,
                        'level': alert.level,
                        'requireInteraction': alert.level == 'EMERGENCY',
                        'vibrate': [500, 200, 500, 200, 500] if alert.level == 'EMERGENCY' else [200, 100, 200],
                        'tag': f'sos-{alert.id}',
                    },
                    url=f"/sos/{group.id}",
                )
            except Exception as e:
                logger.warning(f"Push failed for member {member.profile_id}: {e}")

    spawn(_send_all, priority=PRIORITY_URGENT)


def _ws_broadcast_alert(group, alert, event_type='sos.new'):
    """Broadcast SOS alert to WebSocket subscribers."""
    from parahub.services.ws_publish import ws_publish

    location = None
    if alert.location:
        location = {"lat": alert.location.y, "lon": alert.location.x}

    ws_publish(f"parasos:{group.id}", {
        "type": event_type,
        "group_id": group.id,
        "group_name": group.name,
        "alert": {
            "id": alert.id,
            "level": alert.level,
            "category": alert.category,
            "message": alert.message,
            "location": location,
            "status": alert.status,
            "sender_id": alert.sender_id,
            "sender_hna": alert.sender.hna,
            "sender_display_name": alert.sender.display_name,
            "seen_count": alert.seen_count,
            "responding_count": alert.responding_count,
            "created_at": alert.created_at.isoformat(),
        },
    })


def _ws_broadcast_response(alert, response, event_type='sos.response'):
    """Broadcast SOS response update to WebSocket subscribers."""
    from parahub.services.ws_publish import ws_publish

    ws_publish(f"parasos:{alert.group_id}", {
        "type": event_type,
        "group_id": alert.group_id,
        "alert_id": alert.id,
        "response": {
            "id": response.id,
            "responder_id": response.responder_id,
            "responder_hna": response.responder.hna,
            "responder_display_name": response.responder.display_name,
            "status": response.status,
            "note": response.note,
        },
        "seen_count": alert.seen_count,
        "responding_count": alert.responding_count,
    })


# ===== Group Endpoints =====

@router.post("/groups/", auth=ProfileAuth(), response={200: GroupResponse, 400: dict, 403: dict})
@ratelimit(group='parasos:create_group', key=user_or_ip, rate='5/m', method='POST')
def create_group(request, payload: GroupCreateInput):
    """
    Create safety group. Requires WoT level 3+.
    Automatically creates Matrix chat room.
    """
    from parasos.models import SafetyGroup, SafetyGroupMember
    from identity.models import Verification

    profile = request.auth

    # WoT check (skip for admins)
    if not profile.account.is_superuser:
        wot_count = Verification.objects.filter(
            verified_profile=profile, is_active=True,
        ).count()
        if wot_count < 3:
            raise HttpError(403, "Requires WoT level 3+ to create safety groups")

    with transaction.atomic():
        center = None
        radius_m = None
        if payload.center:
            center = Point(payload.center.longitude, payload.center.latitude, srid=4326)
            radius_m = payload.radius_m or 1000

        world_object = None
        if payload.world_object_id:
            from geo.models import WorldObject
            world_object = get_object_or_404(WorldObject, id=payload.world_object_id)

        group = SafetyGroup.objects.create(
            name=payload.name,
            description=payload.description,
            visibility=payload.visibility,
            created_by=profile,
            center=center,
            radius_m=radius_m,
            world_object=world_object,
            quiet_hours_start=payload.quiet_hours_start,
            quiet_hours_end=payload.quiet_hours_end,
        )

        # Creator is auto-joined as ADMIN + LOCAL
        SafetyGroupMember.objects.create(
            group=group, profile=profile,
            role=SafetyGroupMember.Role.ADMIN,
            presence=SafetyGroupMember.Presence.LOCAL,
        )
        group.members_count = 1
        group.save(update_fields=['members_count'])

        # Create Matrix room
        room_id = _create_group_matrix_room(group, profile.account_id)
        if room_id:
            group.matrix_room_id = room_id
            group.save(update_fields=['matrix_room_id'])

    return _format_group_response(group, profile)


@router.get("/groups/my/", auth=ProfileAuth(), response=List[GroupListItem])
@ratelimit(group='parasos:my_groups', key=user_or_ip, rate='30/m')
def my_groups(request):
    """Get groups where current user is a member."""
    from parasos.models import SafetyGroup, SafetyGroupMember

    group_ids = SafetyGroupMember.objects.filter(
        profile=request.auth,
    ).values_list('group_id', flat=True)

    groups = SafetyGroup.objects.filter(id__in=group_ids, is_active=True).order_by('-created_at')

    return [_format_group_list_item(g) for g in groups]


@router.get("/groups/{group_id}/", auth=ProfileAuth(), response={200: GroupResponse, 404: dict})
@ratelimit(group='parasos:group_detail', key=user_or_ip, rate='60/m')
def get_group(request, group_id: str):
    """Get safety group details. PRIVATE groups are visible to members only."""
    from parasos.models import SafetyGroup

    group, _ = _get_group_for_member(group_id, request.auth, require_member=False)
    if not group.is_active:
        raise HttpError(404, "Not found")

    return _format_group_response(group, request.auth)


@router.put("/groups/{group_id}/", auth=ProfileAuth(), response={200: GroupResponse, 403: dict, 404: dict})
@ratelimit(group='parasos:update_group', key=user_or_ip, rate='10/m', method='PUT')
def update_group(request, group_id: str, payload: GroupUpdateInput):
    """Update safety group. Only admin can update."""
    from parasos.models import SafetyGroup, SafetyGroupMember

    group = get_object_or_404(SafetyGroup, id=group_id)

    # Check admin
    is_admin = SafetyGroupMember.objects.filter(
        group=group, profile=request.auth, role=SafetyGroupMember.Role.ADMIN,
    ).exists()
    if not is_admin:
        raise HttpError(403, "Only group admin can update settings")

    if payload.name is not None:
        group.name = payload.name
    if payload.description is not None:
        group.description = payload.description
    if payload.visibility is not None:
        group.visibility = payload.visibility
    if payload.radius_m is not None:
        group.radius_m = payload.radius_m
    # Explicit null clears quiet hours (model_fields_set distinguishes
    # "field sent as null" from "field omitted")
    if 'quiet_hours_start' in payload.model_fields_set:
        group.quiet_hours_start = payload.quiet_hours_start
    if 'quiet_hours_end' in payload.model_fields_set:
        group.quiet_hours_end = payload.quiet_hours_end
    if payload.is_active is not None:
        group.is_active = payload.is_active

    group.save()
    return _format_group_response(group, request.auth)


@router.delete("/groups/{group_id}/", auth=ProfileAuth(), response={204: None, 403: dict, 404: dict})
@ratelimit(group='parasos:delete_group', key=user_or_ip, rate='5/m', method='DELETE')
def delete_group(request, group_id: str):
    """Soft-delete safety group. Only admin can delete."""
    from parasos.models import SafetyGroup, SafetyGroupMember, GroupInvite

    group = get_object_or_404(SafetyGroup, id=group_id)

    is_admin = SafetyGroupMember.objects.filter(
        group=group, profile=request.auth, role=SafetyGroupMember.Role.ADMIN,
    ).exists()
    if not is_admin:
        raise HttpError(403, "Only group admin can delete the group")

    from parasos.models import SOSAlert

    with transaction.atomic():
        group.is_active = False
        group.save(update_fields=['is_active'])
        GroupInvite.objects.filter(group=group, is_active=True).update(is_active=False)
        SOSAlert.objects.filter(group=group, status=SOSAlert.Status.ACTIVE).update(
            status=SOSAlert.Status.RESOLVED,
            resolved_at=timezone.now(),
            resolved_by=request.auth,
        )

    # Members with the page open navigate away / refresh on this
    from parahub.services.ws_publish import ws_publish
    ws_publish(f"parasos:{group.id}", {
        "type": "group.deleted",
        "group_id": group.id,
        "group_name": group.name,
    })

    return 204, None


@router.get("/groups/", auth=None, response=List[GroupListItem])
@ratelimit(group='parasos:list_groups', key='ip', rate='60/m')
@paginate(PageNumberPagination, page_size=20)
def list_groups(
    request,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: Optional[float] = None,
    search: Optional[str] = None,
):
    """List safety groups. Optionally filter by proximity."""
    from parasos.models import SafetyGroup

    qs = SafetyGroup.objects.filter(is_active=True)

    # Public listing shows only PUBLIC groups
    qs = qs.filter(visibility='PUBLIC')

    # Hide groups created by test/bot accounts unless the viewer is exempt
    qs = exclude_test_authors(qs, request, field='created_by')

    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))

    if lat is not None and lon is not None:
        point = Point(lon, lat, srid=4326)
        km = radius_km or 10
        # Geo filter only works on groups with center
        qs = qs.filter(center__isnull=False, center__distance_lte=(point, D(km=km)))

    qs = qs.order_by('-members_count', '-created_at')

    return [_format_group_list_item(g) for g in qs]



@router.post("/groups/{group_id}/join/", auth=ProfileAuth(), response={200: dict, 400: dict, 403: dict})
@ratelimit(group='parasos:join_group', key=user_or_ip, rate='10/m', method='POST')
def join_group(request, group_id: str, payload: JoinGroupInput):
    """
    Join safety group. Any authenticated user can join.
    LOCAL members can physically respond. REMOTE members coordinate from afar.
    """
    from parasos.models import SafetyGroup, SafetyGroupMember

    group = get_object_or_404(SafetyGroup, id=group_id, is_active=True)
    profile = request.auth

    # PRIVATE groups require invite token
    invite = None
    if group.visibility == 'PRIVATE':
        from parasos.models import GroupInvite
        if not payload.invite_token:
            raise HttpError(403, "This is a private group. An invite link is required to join")
        invite = GroupInvite.objects.filter(
            group=group, token=payload.invite_token,
        ).first()
        if not invite or not invite.is_valid:
            raise HttpError(403, "Invalid or expired invite link")

    with transaction.atomic():
        # Lock the group row: serializes concurrent joins so the max_members
        # check can't be raced past
        group = SafetyGroup.objects.select_for_update().get(id=group.id)

        if SafetyGroupMember.objects.filter(group=group, profile=profile).exists():
            raise HttpError(400, "Already a member of this group")

        if group.max_members > 0 and group.members_count >= group.max_members:
            raise HttpError(400, f"Group is full (max {group.max_members} members)")

        member = SafetyGroupMember.objects.create(
            group=group, profile=profile,
            role=SafetyGroupMember.Role.MEMBER,
            presence=payload.presence,
            emergency_context=payload.emergency_context,
        )

        group.members_count = group.members.count()
        group.save(update_fields=['members_count'])

        # Increment invite usage
        if invite:
            invite.uses_count = F('uses_count') + 1
            invite.save(update_fields=['uses_count'])

    # Join Matrix room after the transaction — Matrix HTTP must not run while
    # holding the group row lock, and a dead-room heal takes several calls
    if _join_group_matrix_room(group, profile):
        member.joined_matrix_room = True
        member.save(update_fields=['joined_matrix_room'])

    return {"success": True, "members_count": group.members_count}


@router.post("/groups/{group_id}/leave/", auth=ProfileAuth(), response={200: dict, 400: dict})
@ratelimit(group='parasos:leave_group', key=user_or_ip, rate='10/m', method='POST')
def leave_group(request, group_id: str):
    """Leave safety group."""
    from parasos.models import SafetyGroup, SafetyGroupMember

    with transaction.atomic():
        # Lock the group row: serializes concurrent leaves so two admins
        # can't both pass the last-admin check and leave the group adminless
        group = get_object_or_404(SafetyGroup.objects.select_for_update(), id=group_id)

        member = SafetyGroupMember.objects.filter(
            group=group, profile=request.auth,
        ).first()
        if not member:
            raise HttpError(400, "Not a member of this group")

        # Don't allow last admin to leave
        if member.role == SafetyGroupMember.Role.ADMIN:
            admin_count = SafetyGroupMember.objects.filter(
                group=group, role=SafetyGroupMember.Role.ADMIN,
            ).count()
            if admin_count <= 1:
                raise HttpError(400, "Cannot leave: you are the only admin. Transfer admin role first")

        member.delete()
        group.members_count = group.members.count()
        group.save(update_fields=['members_count'])

    # Privacy: ex-members must not keep receiving SOS notices in the room
    _leave_group_matrix_room(group, request.auth)

    return {"success": True, "members_count": group.members_count}


@router.get("/groups/{group_id}/members/", auth=ProfileAuth(), response=List[MemberInfo])
@ratelimit(group='parasos:group_members', key=user_or_ip, rate='60/m')
@paginate(PageNumberPagination, page_size=50)
def get_group_members(request, group_id: str):
    """Get list of group members. Members only."""
    from parasos.models import SafetyGroupMember

    group, _ = _get_group_for_member(group_id, request.auth)

    members = SafetyGroupMember.objects.filter(
        group=group,
    ).select_related('profile').order_by('created_at')

    return [
        MemberInfo(
            id=m.id,
            profile_id=m.profile_id,
            profile_hna=m.profile.hna,
            profile_display_name=m.profile.display_name,
            profile_avatar_url=m.profile.avatar_url,
            role=m.role,
            presence=m.presence,
            joined_at=m.created_at,
        )
        for m in members
    ]


# ===== SOS Alert Endpoints =====

@router.post("/groups/{group_id}/sos/", auth=ProfileAuth(), response={200: AlertResponse, 400: dict, 403: dict})
@ratelimit(group='parasos:sos_send', key=user_or_ip, rate='3/m', method='POST')
def send_sos(request, group_id: str, payload: SOSInput):
    """
    Send SOS alert to safety group.
    Rate limits: 3/min overall. Must be a member.
    Notifies all group members via push + WebSocket + Matrix.
    """
    from parasos.models import SafetyGroup, SafetyGroupMember, SOSAlert

    group = get_object_or_404(SafetyGroup, id=group_id, is_active=True)
    profile = request.auth

    # Must be member
    if not SafetyGroupMember.objects.filter(group=group, profile=profile).exists():
        raise HttpError(403, "Must be a member to send SOS")

    # Check for existing active alert from same sender in this group
    existing = SOSAlert.objects.filter(
        group=group, sender=profile, status=SOSAlert.Status.ACTIVE,
    ).first()
    if existing:
        raise HttpError(400, "You already have an active alert in this group. Resolve it first")

    location = None
    if payload.location:
        location = Point(payload.location.longitude, payload.location.latitude, srid=4326)

    alert = SOSAlert.objects.create(
        group=group,
        sender=profile,
        level=payload.level,
        category=payload.category,
        message=payload.message,
        location=location,
        source=SOSAlert.Source.MANUAL,
    )

    # Notify: push + WS + Matrix
    _notify_group_members(group, alert)
    _ws_broadcast_alert(group, alert, event_type='sos.new')
    _send_matrix_sos_notice(group, alert)

    return _format_alert_response(alert)


@router.post("/alerts/{alert_id}/respond/", auth=ProfileAuth(), response={200: dict, 400: dict, 403: dict})
@ratelimit(group='parasos:sos_respond', key=user_or_ip, rate='30/m', method='POST')
def respond_to_sos(request, alert_id: str, payload: SOSResponseInput):
    """
    Respond to SOS alert. Must be member of the group.
    Statuses: SEEN, ON_WAY, ON_SITE, UNABLE.
    """
    from parasos.models import SOSAlert, SOSResponse, SafetyGroupMember

    alert = get_object_or_404(
        SOSAlert.objects.select_related('group', 'sender'),
        id=alert_id, status=SOSAlert.Status.ACTIVE,
    )
    profile = request.auth

    # Must be member
    if not SafetyGroupMember.objects.filter(group=alert.group, profile=profile).exists():
        raise HttpError(403, "Must be a group member to respond")

    # Can't respond to own alert
    if alert.sender_id == profile.id:
        raise HttpError(400, "Cannot respond to your own alert")

    with transaction.atomic():
        response, created = SOSResponse.objects.update_or_create(
            alert=alert, responder=profile,
            defaults={
                'status': payload.status,
                'note': payload.note,
            },
        )

        # Update denormalized counts
        alert.seen_count = alert.responses.count()
        alert.responding_count = alert.responses.filter(
            status__in=[SOSResponse.Status.ON_WAY, SOSResponse.Status.ON_SITE],
        ).count()
        alert.save(update_fields=['seen_count', 'responding_count'])

    # Broadcast response via WS
    _ws_broadcast_response(alert, response)

    return {
        "success": True,
        "response_id": response.id,
        "status": response.status,
        "seen_count": alert.seen_count,
        "responding_count": alert.responding_count,
    }


@router.post("/alerts/{alert_id}/resolve/", auth=ProfileAuth(), response={200: dict, 400: dict, 403: dict})
@ratelimit(group='parasos:sos_resolve', key=user_or_ip, rate='10/m', method='POST')
def resolve_sos(request, alert_id: str, false_alarm: bool = False):
    """Resolve SOS alert. Only sender or group admin can resolve."""
    from parasos.models import SOSAlert, SafetyGroupMember

    alert = get_object_or_404(
        SOSAlert.objects.select_related('group'),
        id=alert_id, status=SOSAlert.Status.ACTIVE,
    )
    profile = request.auth

    # Only sender or admin can resolve
    is_sender = alert.sender_id == profile.id
    is_admin = SafetyGroupMember.objects.filter(
        group=alert.group, profile=profile, role=SafetyGroupMember.Role.ADMIN,
    ).exists()
    if not is_sender and not is_admin:
        raise HttpError(403, "Only alert sender or group admin can resolve")

    alert.status = SOSAlert.Status.FALSE_ALARM if false_alarm else SOSAlert.Status.RESOLVED
    alert.resolved_at = timezone.now()
    alert.resolved_by = profile
    alert.save(update_fields=['status', 'resolved_at', 'resolved_by'])

    # Broadcast resolution
    _ws_broadcast_alert(alert.group, alert, event_type='sos.resolved')

    return {"success": True, "status": alert.status}


@router.get("/groups/{group_id}/alerts/", auth=ProfileAuth(), response=List[AlertListItem])
@ratelimit(group='parasos:list_alerts', key=user_or_ip, rate='60/m')
@paginate(PageNumberPagination, page_size=20)
def list_alerts(request, group_id: str, status: Optional[str] = None):
    """List SOS alerts for a group. Members only."""
    from parasos.models import SOSAlert

    group, _ = _get_group_for_member(group_id, request.auth)

    qs = SOSAlert.objects.filter(group=group).select_related('sender')

    if status:
        qs = qs.filter(status=status)

    qs = qs.order_by('-created_at')

    return [
        AlertListItem(
            id=a.id,
            group_id=a.group_id,
            group_name=group.name,
            sender_hna=a.sender.hna,
            sender_display_name=a.sender.display_name,
            level=a.level,
            category=a.category,
            status=a.status,
            message=a.message,
            seen_count=a.seen_count,
            responding_count=a.responding_count,
            created_at=a.created_at,
        )
        for a in qs
    ]


@router.get("/alerts/{alert_id}/", auth=ProfileAuth(), response={200: AlertResponse, 404: dict})
@ratelimit(group='parasos:alert_detail', key=user_or_ip, rate='60/m')
def get_alert(request, alert_id: str):
    """Get SOS alert details. Members only (contains sender location)."""
    from parasos.models import SOSAlert

    alert = get_object_or_404(
        SOSAlert.objects.select_related('group', 'sender'),
        id=alert_id,
    )
    _get_group_for_member(alert.group_id, request.auth)
    return _format_alert_response(alert)


@router.get("/alerts/{alert_id}/responses/", auth=ProfileAuth(), response=List[ResponderInfo])
@ratelimit(group='parasos:alert_responses', key=user_or_ip, rate='60/m')
def get_alert_responses(request, alert_id: str):
    """Get all responses to an SOS alert. Members only."""
    from parasos.models import SOSAlert, SOSResponse

    alert = get_object_or_404(SOSAlert, id=alert_id)
    _get_group_for_member(alert.group_id, request.auth)

    responses = SOSResponse.objects.filter(
        alert=alert,
    ).select_related('responder').order_by('created_at')

    return [
        ResponderInfo(
            id=r.id,
            responder_id=r.responder_id,
            responder_hna=r.responder.hna,
            responder_display_name=r.responder.display_name,
            responder_avatar_url=r.responder.avatar_url,
            status=r.status,
            note=r.note,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in responses
    ]


# ===== IoT/HA Auto-Trigger Endpoint =====

class AutoTriggerInput(BaseModel):
    """Auto-trigger SOS from IoT sensor or HA automation."""
    group_id: str
    level: str = Field(default="WARNING", pattern="^(INFO|WARNING|EMERGENCY)$")
    category: str = Field(default="OTHER", pattern="^(SUSPICIOUS_ACTIVITY|ALARM_TRIGGERED|MEDICAL|FIRE|INTRUSION|OTHER)$")
    message: str = Field(default="", max_length=1000)
    source: str = Field(default="IOT_SENSOR", pattern="^(IOT_SENSOR|HA_AUTOMATION)$")
    location: Optional[LocationInput] = None


@router.post("/sos/auto-trigger/", auth=ProfileAuth(), response={200: AlertResponse, 400: dict, 403: dict})
@ratelimit(group='parasos:auto_trigger', key=user_or_ip, rate='10/m', method='POST')
def auto_trigger_sos(request, payload: AutoTriggerInput):
    """
    Auto-trigger SOS from IoT sensor or HA automation.
    The authenticated profile must be a member of the group.
    Typically called by HA webhook or IoT device integration.

    Also updates InactivityWatch.last_activity_at for the sender's watches
    (any IoT trigger counts as activity).
    """
    from parasos.models import SafetyGroup, SafetyGroupMember, SOSAlert, InactivityWatch

    group = get_object_or_404(SafetyGroup, id=payload.group_id, is_active=True)
    profile = request.auth

    # Must be member
    if not SafetyGroupMember.objects.filter(group=group, profile=profile).exists():
        raise HttpError(403, "Must be a group member to trigger SOS")

    # Check for existing active alert from same sender
    existing = SOSAlert.objects.filter(
        group=group, sender=profile, status=SOSAlert.Status.ACTIVE,
    ).first()
    if existing:
        raise HttpError(400, "Active alert already exists from this sender")

    location = None
    if payload.location:
        location = Point(payload.location.longitude, payload.location.latitude, srid=4326)

    alert = SOSAlert.objects.create(
        group=group,
        sender=profile,
        level=payload.level,
        category=payload.category,
        message=payload.message,
        location=location,
        source=payload.source,
    )

    # Notify
    _notify_group_members(group, alert)
    _ws_broadcast_alert(group, alert, event_type='sos.new')
    _send_matrix_sos_notice(group, alert)

    # Update InactivityWatch — any IoT trigger counts as activity
    InactivityWatch.objects.filter(
        watched_profile=profile, is_active=True,
    ).update(last_activity_at=timezone.now())

    return _format_alert_response(alert)


@router.post("/inactivity/activity/", auth=ProfileAuth(), response={200: dict})
@ratelimit(group='parasos:activity_ping', key=user_or_ip, rate='60/m', method='POST')
def report_activity(request):
    """
    Report activity for InactivityWatch (e.g., "I'm OK" daily check-in button).
    Updates last_activity_at for all active watches on this profile.
    """
    from parasos.models import InactivityWatch

    updated = InactivityWatch.objects.filter(
        watched_profile=request.auth, is_active=True,
    ).update(last_activity_at=timezone.now())

    return {"success": True, "watches_updated": updated}


# ===== Invite Endpoints =====

def _format_invite(inv) -> InviteResponse:
    return InviteResponse(
        id=inv.id,
        token=inv.token,
        label=inv.label,
        max_uses=inv.max_uses,
        uses_count=inv.uses_count,
        expires_at=inv.expires_at,
        is_active=inv.is_active,
        is_valid=inv.is_valid,
        created_at=inv.created_at,
    )


@router.post("/groups/{group_id}/invites/", auth=ProfileAuth(), response={200: InviteResponse, 403: dict})
@ratelimit(group='parasos:create_invite', key=user_or_ip, rate='10/m', method='POST')
def create_invite(request, group_id: str, payload: InviteCreateInput):
    """Create invite link for a group. Only admin."""
    from parasos.models import SafetyGroup, SafetyGroupMember, GroupInvite
    from datetime import timedelta

    group = get_object_or_404(SafetyGroup, id=group_id)

    is_admin = SafetyGroupMember.objects.filter(
        group=group, profile=request.auth, role=SafetyGroupMember.Role.ADMIN,
    ).exists()
    if not is_admin:
        raise HttpError(403, "Only group admin can create invites")

    # Check if there's already an active invite with same parameters
    existing = GroupInvite.objects.filter(group=group, is_active=True).first()
    if existing and existing.is_valid and not payload.label and not payload.max_uses:
        return _format_invite(existing)

    expires_at = None
    if payload.expires_hours:
        expires_at = timezone.now() + timedelta(hours=payload.expires_hours)

    invite = GroupInvite.objects.create(
        group=group,
        created_by=request.auth,
        label=payload.label,
        max_uses=payload.max_uses,
        expires_at=expires_at,
    )
    return _format_invite(invite)


@router.get("/groups/{group_id}/invites/", auth=ProfileAuth(), response=List[InviteResponse])
@ratelimit(group='parasos:list_invites', key=user_or_ip, rate='30/m')
def list_invites(request, group_id: str):
    """List invites for a group. Only admin."""
    from parasos.models import SafetyGroup, SafetyGroupMember, GroupInvite

    group = get_object_or_404(SafetyGroup, id=group_id)

    is_admin = SafetyGroupMember.objects.filter(
        group=group, profile=request.auth, role=SafetyGroupMember.Role.ADMIN,
    ).exists()
    if not is_admin:
        raise HttpError(403, "Only group admin can view invites")

    invites = GroupInvite.objects.filter(group=group, is_active=True).order_by('-created_at')
    return [_format_invite(inv) for inv in invites]


@router.delete("/invites/{invite_id}/", auth=ProfileAuth(), response={200: dict, 403: dict})
@ratelimit(group='parasos:delete_invite', key=user_or_ip, rate='10/m', method='DELETE')
def delete_invite(request, invite_id: str):
    """Deactivate an invite. Only group admin."""
    from parasos.models import GroupInvite, SafetyGroupMember

    invite = get_object_or_404(GroupInvite, id=invite_id)

    is_admin = SafetyGroupMember.objects.filter(
        group=invite.group, profile=request.auth, role=SafetyGroupMember.Role.ADMIN,
    ).exists()
    if not is_admin:
        raise HttpError(403, "Only group admin can delete invites")

    invite.is_active = False
    invite.save(update_fields=['is_active'])
    return {"success": True}


@router.get("/invites/{token}/info/", auth=None, response={200: dict, 404: dict})
@ratelimit(group='parasos:invite_info', key='ip', rate='30/m')
def get_invite_info(request, token: str):
    """Get public info about an invite link (group name, validity). No auth required."""
    from parasos.models import GroupInvite

    invite = get_object_or_404(GroupInvite, token=token)

    return {
        "group_id": invite.group_id,
        "group_name": invite.group.name,
        "group_description": invite.group.description,
        "group_members_count": invite.group.members_count,
        "group_visibility": invite.group.visibility,
        "is_valid": invite.is_valid,
        "token": invite.token,
    }
