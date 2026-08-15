"""
Organization membership: hiring, role changes, and the two-sided proposals
(invitations out, join requests in).

The rule every check here enforces is the delegation rule: an organization's
own OWNER/ADMIN hand out roles, never above their own level, and authority is
never created without the other side agreeing to it. Reading a role is
`geo.permissions.has_capability`; handing one out is this module.
"""

import logging
import secrets
from datetime import timedelta
from typing import List, Optional

from django.db import transaction
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from parahub.auth import OptionalProfileAuth, ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from geo.models import Establishment, EstablishmentInvite, EstablishmentMembership
from geo.permissions import (
    DIRECT_GRANT_ROLES, actor_rank, has_capability, role_rank,
)

logger = logging.getLogger(__name__)
router = Router(tags=["Geo / Membership"])

CAPABILITY = 'members.manage'

#: A link invite is bearer authority — whoever holds the URL becomes the role it
#: carries. Bounded to positions that cannot hand out further authority, so a
#: leaked link never costs the organization control of itself.
LINK_INVITE_MAX_RANK = 1

#: `fundador` in the governing association makes a profile a WoT seed verifier
#: (Profile.is_foundation_member) and unlocks treasury voting — an admin must not
#: be able to mint one.
OWNER_ONLY_LEVELS = {'fundador'}

DEFAULT_INVITE_DAYS = 14


# ===== Schemas =====

class MemberOut(Schema):
    profile_id: str
    profile_hna: str
    profile_display_name: str = ''
    role: str
    position_title: str = ''
    membership_level: Optional[str] = None
    is_treasurer: bool = False
    is_auditor: bool = False
    joined_at: str


class MemberHireIn(Schema):
    #: Validated against DIRECT_GRANT_ROLES in the endpoint rather than typed as a
    #: Literal, so refusing an authority role answers why instead of "not a valid
    #: enumeration member".
    role: str = 'EMPLOYEE'
    position_title: str = ''


class MemberPatchIn(Schema):
    role: Optional[str] = None
    position_title: Optional[str] = None
    membership_level: Optional[str] = None


class InviteCreateIn(Schema):
    profile_id: Optional[str] = None
    hna: Optional[str] = None
    role: str = 'MEMBER'
    position_title: str = ''
    membership_level: Optional[str] = None
    message: str = ''
    expires_in_days: int = DEFAULT_INVITE_DAYS


class InviteOut(Schema):
    id: str
    object_type: str = 'establishment_invite'
    establishment_id: str
    establishment_name: str
    establishment_slug: str = ''
    direction: str
    status: str
    role: str
    position_title: str = ''
    membership_level: Optional[str] = None
    message: str = ''
    target_profile_id: Optional[str] = None
    target_hna: Optional[str] = None
    target_display_name: str = ''
    created_by_hna: Optional[str] = None
    #: Returned only to the organization side — it is the secret itself.
    token: Optional[str] = None
    is_expired: bool = False
    expires_at: Optional[str] = None
    created_at: str
    resolved_at: Optional[str] = None


# ===== Helpers =====

def _resolve_org(establishment_id: str) -> Establishment:
    try:
        return Establishment.objects.get(id=establishment_id, is_active=True)
    except Establishment.DoesNotExist:
        try:
            return Establishment.objects.get(slug=establishment_id, is_active=True)
        except Establishment.DoesNotExist:
            raise HttpError(404, "Establishment not found")


def _manager(request, establishment) -> int:
    """
    Rank of the caller as a member manager, or 403.

    Staff rank as OWNER: onboarding a pilot organization means seating its first
    admin before anyone inside it can.
    """
    profile = request.auth_profile
    if request.user.is_staff:
        return role_rank('OWNER')
    if not has_capability(profile, establishment, CAPABILITY):
        raise HttpError(403, "You cannot manage members of this organization")
    return actor_rank(profile, establishment)


def _check_grant(rank: int, role: str, membership_level: Optional[str] = None):
    """A role may only be handed out at or below the granter's own level."""
    # An unranked role would slip past the comparison below (-1 is under every
    # rank), so a role the ladder doesn't know is refused rather than granted.
    if role not in EstablishmentMembership.Role.values or role_rank(role) < 0:
        raise HttpError(400, f"Unknown role: {role}")
    if role_rank(role) > rank:
        raise HttpError(403, f"You cannot grant '{role}' — it stands above your own level")
    if membership_level in OWNER_ONLY_LEVELS and rank < role_rank('OWNER'):
        raise HttpError(403, f"Membership level '{membership_level}' is granted by the owner only")


def _check_target(rank: int, establishment, membership: EstablishmentMembership):
    """Nobody may act on a member who stands at least as high as themselves."""
    if establishment.owner_id and membership.profile_id == establishment.owner_id:
        raise HttpError(403, "The organization's owner cannot be changed here")
    if role_rank(membership.role) > rank:
        raise HttpError(403, "This member stands above your own level")


def _member_out(m: EstablishmentMembership) -> MemberOut:
    return MemberOut(
        profile_id=m.profile_id,
        profile_hna=m.profile.hna,
        profile_display_name=m.profile.display_name or '',
        role=m.role,
        position_title=m.position_title or '',
        membership_level=m.membership_level,
        is_treasurer=m.is_treasurer,
        is_auditor=m.is_auditor,
        joined_at=m.created_at.isoformat(),
    )


def _invite_out(inv: EstablishmentInvite, *, with_token: bool = False) -> InviteOut:
    return InviteOut(
        id=inv.id,
        establishment_id=inv.establishment_id,
        establishment_name=inv.establishment.name,
        establishment_slug=inv.establishment.slug or '',
        direction=inv.direction,
        status=inv.status,
        role=inv.role,
        position_title=inv.position_title or '',
        membership_level=inv.membership_level,
        message=inv.message or '',
        target_profile_id=inv.target_profile_id,
        target_hna=inv.target_profile.hna if inv.target_profile else None,
        target_display_name=(inv.target_profile.display_name or '') if inv.target_profile else '',
        created_by_hna=inv.created_by.hna if inv.created_by else None,
        token=(inv.token or None) if with_token else None,
        is_expired=inv.is_expired,
        expires_at=inv.expires_at.isoformat() if inv.expires_at else None,
        created_at=inv.created_at.isoformat(),
        resolved_at=inv.resolved_at.isoformat() if inv.resolved_at else None,
    )


def _supersede_pending(establishment, profile, exclude_id=None):
    """
    Close out the other pending proposals once the membership exists.

    A person may hold an invitation and an application at the same time; without
    this the loser stays in the queue forever and an admin approves something
    that already happened.
    """
    qs = EstablishmentInvite.objects.filter(
        establishment=establishment, target_profile=profile,
        status=EstablishmentInvite.Status.PENDING,
    )
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    qs.update(status=EstablishmentInvite.Status.SUPERSEDED, resolved_at=timezone.now())


def _notify(profile, **kwargs):
    """Best-effort — a membership change must not fail on the notifier."""
    try:
        from notifications.services import emit_notification
        if profile and profile.account:
            emit_notification(profile.account, **kwargs)
    except Exception as e:
        logger.warning(f"Membership notification failed: {e}")


def _notify_managers(establishment, exclude_profile_id=None, **kwargs):
    """Reach everyone who could act on it — a queue nobody is told about is a dead queue."""
    from geo.permissions import capability_roles
    profiles = {}
    if establishment.owner_id:
        profiles[establishment.owner_id] = establishment.owner
    for m in EstablishmentMembership.objects.filter(
        establishment=establishment, role__in=capability_roles(CAPABILITY),
    ).select_related('profile'):
        profiles[m.profile_id] = m.profile
    profiles.pop(exclude_profile_id, None)
    for p in profiles.values():
        _notify(p, **kwargs)


def _org_url(establishment) -> str:
    return f"/org/{establishment.slug or establishment.id}"


# ===== Members =====

@router.put("/establishments/{establishment_id}/members/{profile_id}/", auth=ProfileAuth(),
            response={200: MemberOut, 400: dict, 403: dict, 404: dict})
@ratelimit(group='members:hire', key=user_or_ip, rate='30/m', method='PUT')
def add_member(request, establishment_id: str, profile_id: str, data: MemberHireIn):
    """
    Put a person straight into a hired position (EMPLOYEE/CONTRACTOR).

    Employment is a fact the organization already knows and answers for, so it
    needs no acceptance step — unlike anything that carries standing inside the
    organization, which goes through an invitation.
    """
    from identity.models import Profile

    establishment = _resolve_org(establishment_id)
    rank = _manager(request, establishment)

    if data.role not in DIRECT_GRANT_ROLES:
        raise HttpError(400, f"'{data.role}' has to be offered as an invitation, not assigned")
    _check_grant(rank, data.role)

    try:
        target = Profile.objects.get(id=profile_id)
    except Profile.DoesNotExist:
        raise HttpError(404, "Profile not found")

    if EstablishmentMembership.objects.filter(establishment=establishment, profile=target).exists():
        raise HttpError(400, "Already a member — change the role instead")

    with transaction.atomic():
        membership = EstablishmentMembership.objects.create(
            establishment=establishment, profile=target,
            role=data.role, position_title=data.position_title.strip()[:100],
        )
        _supersede_pending(establishment, target)
    membership.profile = target

    _notify(
        target, type='org_membership_changed',
        title=establishment.name,
        body=f"You were added as {data.role.lower()}",
        url=_org_url(establishment),
        data={'establishment_id': establishment.id, 'role': data.role},
    )
    return _member_out(membership)


@router.patch("/establishments/{establishment_id}/members/{profile_id}/", auth=ProfileAuth(),
              response={200: MemberOut, 400: dict, 403: dict, 404: dict})
@ratelimit(group='members:patch', key=user_or_ip, rate='30/m', method='PATCH')
def update_member(request, establishment_id: str, profile_id: str, data: MemberPatchIn):
    """
    Change a member's role, title or membership level.

    Promotion into authority is deliberately not possible here: taking authority
    away never needs the person's consent, receiving it always does, so upward
    moves are offered as invitations instead.
    """
    establishment = _resolve_org(establishment_id)
    rank = _manager(request, establishment)

    if profile_id == request.auth_profile.id:
        raise HttpError(400, "You cannot change your own membership")

    try:
        membership = EstablishmentMembership.objects.select_related('profile').get(
            establishment=establishment, profile_id=profile_id)
    except EstablishmentMembership.DoesNotExist:
        raise HttpError(404, "Not a member of this organization")

    _check_target(rank, establishment, membership)

    fields = []
    role_changed = False
    if data.role is not None and data.role != membership.role:
        _check_grant(rank, data.role)
        promotion = role_rank(data.role) > role_rank(membership.role)
        if promotion and data.role not in DIRECT_GRANT_ROLES:
            raise HttpError(400, f"'{data.role}' has to be offered as an invitation, not assigned")
        membership.role = data.role
        fields.append('role')
        role_changed = True

    if data.position_title is not None:
        membership.position_title = data.position_title.strip()[:100]
        fields.append('position_title')

    if data.membership_level is not None:
        level = data.membership_level or None
        if level and level not in EstablishmentMembership.MembershipLevel.values:
            raise HttpError(400, f"Unknown membership level: {level}")
        _check_grant(rank, membership.role, level)
        membership.membership_level = level
        fields.append('membership_level')

    if fields:
        membership.save(update_fields=fields)

    if role_changed:
        _notify(
            membership.profile, type='org_membership_changed',
            title=establishment.name,
            body=f"Your role is now {membership.role.lower()}",
            url=_org_url(establishment),
            data={'establishment_id': establishment.id, 'role': membership.role},
        )
    return _member_out(membership)


@router.delete("/establishments/{establishment_id}/members/{profile_id}/", auth=ProfileAuth(),
               response={200: dict, 400: dict, 403: dict, 404: dict})
@ratelimit(group='members:remove', key=user_or_ip, rate='30/m', method='DELETE')
def remove_member(request, establishment_id: str, profile_id: str):
    """Remove a member. Leaving on your own is `/leave/`."""
    establishment = _resolve_org(establishment_id)
    rank = _manager(request, establishment)

    if profile_id == request.auth_profile.id:
        raise HttpError(400, "Use leave to end your own membership")

    try:
        membership = EstablishmentMembership.objects.select_related('profile').get(
            establishment=establishment, profile_id=profile_id)
    except EstablishmentMembership.DoesNotExist:
        raise HttpError(404, "Not a member of this organization")

    _check_target(rank, establishment, membership)

    target = membership.profile
    membership.delete()

    _notify(
        target, type='org_membership_changed',
        title=establishment.name,
        body="Your membership was ended",
        url=_org_url(establishment),
        data={'establishment_id': establishment.id, 'role': None},
    )
    return {"ok": True}


# ===== Invitations & join requests =====

@router.post("/establishments/{establishment_id}/invites/", auth=ProfileAuth(),
             response={200: InviteOut, 400: dict, 403: dict, 404: dict})
@ratelimit(group='members:invite', key=user_or_ip, rate='30/m', method='POST')
def create_invite(request, establishment_id: str, data: InviteCreateIn):
    """
    Offer a role. With `profile_id`/`hna` it reaches that person's notifications;
    with neither it returns a one-time link, which is how someone who has no
    account yet is brought in.
    """
    from identity.models import Profile

    establishment = _resolve_org(establishment_id)
    rank = _manager(request, establishment)
    profile = request.auth_profile

    level = data.membership_level or None
    if level and level not in EstablishmentMembership.MembershipLevel.values:
        raise HttpError(400, f"Unknown membership level: {level}")
    _check_grant(rank, data.role, level)

    target = None
    if data.profile_id or data.hna:
        if data.profile_id:
            lookup = {'id': data.profile_id}
        else:
            # `hna` is a property (local_name @ instance domain), not a column.
            handle = data.hna.strip().lstrip('@')
            local_name, _, domain = handle.partition('@')
            lookup = {'local_name': local_name}
            if domain:
                lookup['instance__domain'] = domain
        target = Profile.objects.filter(**lookup).first()
        if not target:
            raise HttpError(404, "Profile not found")
        if EstablishmentMembership.objects.filter(establishment=establishment, profile=target).exists():
            raise HttpError(400, "Already a member — change the role instead")
    elif role_rank(data.role) > LINK_INVITE_MAX_RANK:
        # Bearer authority: whoever holds the link becomes the role it carries.
        raise HttpError(400, f"'{data.role}' has to be invited by name, not by link")

    days = max(1, min(int(data.expires_in_days or DEFAULT_INVITE_DAYS), 90))
    values = {
        'role': data.role,
        'position_title': data.position_title.strip()[:100],
        'membership_level': level,
        'message': data.message.strip()[:2000],
        'created_by': profile,
        'expires_at': timezone.now() + timedelta(days=days),
        'token': '' if target else secrets.token_urlsafe(32),
    }

    if target:
        # Re-inviting someone who already has a pending offer replaces it rather
        # than stacking a second one (the partial unique constraint says so too).
        invite, _created = EstablishmentInvite.objects.update_or_create(
            establishment=establishment, target_profile=target,
            direction=EstablishmentInvite.Direction.INVITE,
            status=EstablishmentInvite.Status.PENDING,
            defaults=values,
        )
        invite.target_profile = target
        _notify(
            target, type='org_invite',
            title=establishment.name,
            body=f"You are invited as {data.role.lower()}",
            url=f"/invite/org/{invite.id}",
            data={'establishment_id': establishment.id, 'invite_id': invite.id, 'role': data.role},
        )
    else:
        invite = EstablishmentInvite.objects.create(
            establishment=establishment,
            direction=EstablishmentInvite.Direction.INVITE, **values,
        )

    invite.establishment = establishment
    return _invite_out(invite, with_token=True)


@router.get("/establishments/{establishment_id}/invites/", auth=ProfileAuth(),
            response={200: List[InviteOut], 403: dict, 404: dict})
@ratelimit(group='members:invite_list', key=user_or_ip, rate='60/m')
def list_invites(request, establishment_id: str, status: str = 'pending'):
    """
    The organization's pending offers and applications; `status=all` adds the
    resolved ones, which are the record of who granted what and when.
    """
    establishment = _resolve_org(establishment_id)
    _manager(request, establishment)

    qs = EstablishmentInvite.objects.filter(establishment=establishment).select_related(
        'establishment', 'target_profile', 'created_by')
    if status != 'all':
        qs = qs.filter(status=EstablishmentInvite.Status.PENDING)

    return [_invite_out(i, with_token=True) for i in qs.order_by('-created_at')[:200]]


@router.get("/my-invites/", auth=ProfileAuth(), response=List[InviteOut])
@ratelimit(group='members:my_invites', key=user_or_ip, rate='60/m')
def my_invites(request):
    """Offers waiting on me, plus applications I am waiting on."""
    profile = request.auth_profile
    qs = EstablishmentInvite.objects.filter(
        target_profile=profile, status=EstablishmentInvite.Status.PENDING,
    ).select_related('establishment', 'target_profile', 'created_by')

    return [_invite_out(i) for i in qs.order_by('-created_at')[:100]]


def _resolve_invite(ident: str) -> EstablishmentInvite:
    """By ULID (a named invite) or by token (a link invite)."""
    invite = EstablishmentInvite.objects.select_related(
        'establishment', 'target_profile', 'created_by').filter(id=ident).first()
    if not invite and ident:
        invite = EstablishmentInvite.objects.select_related(
            'establishment', 'target_profile', 'created_by').filter(token=ident).first()
    if not invite:
        raise HttpError(404, "Invitation not found")
    return invite


def _is_org_side(request, invite) -> bool:
    if getattr(request.user, 'is_staff', False):
        return True
    return has_capability(getattr(request, 'auth_profile', None), invite.establishment_id, CAPABILITY)


@router.get("/invites/{ident}/", auth=OptionalProfileAuth(), response={200: InviteOut, 403: dict, 404: dict})
@ratelimit(group='members:invite_get', key=user_or_ip, rate='60/m')
def get_invite(request, ident: str):
    """
    Read one invitation — by its id if it is addressed to you, by its token otherwise.

    A link invite reads without an account on purpose: its whole point is
    bringing in someone who is not on the platform yet, and they have to see
    what they are being offered before signing up to accept it.
    """
    invite = _resolve_invite(ident)
    profile = getattr(request, 'auth_profile', None)
    org_side = _is_org_side(request, invite)

    if not invite.target_profile and ident == invite.token:
        pass
    elif not (org_side or (profile and profile.id in (invite.target_profile_id, invite.created_by_id))):
        raise HttpError(403, "Not your invitation")

    return _invite_out(invite, with_token=org_side)


@router.post("/invites/{ident}/accept/", auth=ProfileAuth(),
             response={200: dict, 400: dict, 403: dict, 404: dict})
@ratelimit(group='members:invite_accept', key=user_or_ip, rate='30/m', method='POST')
def accept_invite(request, ident: str):
    """
    Agree to the proposal from whichever end it is missing:
    the invited person accepts an INVITE, a manager approves a REQUEST.
    """
    invite = _resolve_invite(ident)
    profile = request.auth_profile

    if invite.status != EstablishmentInvite.Status.PENDING:
        raise HttpError(400, f"This invitation is already {invite.status.lower()}")
    if invite.is_expired:
        raise HttpError(400, "This invitation has expired")
    if not invite.establishment.is_active:
        raise HttpError(400, "This organization is no longer active")

    is_request = invite.direction == EstablishmentInvite.Direction.REQUEST
    if is_request:
        if not _is_org_side(request, invite):
            raise HttpError(403, "You cannot approve applications for this organization")
        member_profile = invite.target_profile
        if not member_profile:
            raise HttpError(400, "This application has no applicant")
    else:
        if invite.target_profile_id and invite.target_profile_id != profile.id:
            raise HttpError(403, "This invitation is addressed to someone else")
        if not invite.target_profile_id and ident != invite.token:
            raise HttpError(403, "This invitation needs its link")
        member_profile = profile

    with transaction.atomic():
        # Claim it first, as one conditional UPDATE: a link invite is a secret
        # that can be forwarded, and two people opening it at once must not both
        # get in on a single offer.
        claimed = EstablishmentInvite.objects.filter(
            id=invite.id, status=EstablishmentInvite.Status.PENDING,
        ).update(
            status=EstablishmentInvite.Status.ACCEPTED,
            resolved_at=timezone.now(), resolved_by=profile,
            target_profile_id=invite.target_profile_id or member_profile.id,
        )
        if not claimed:
            raise HttpError(400, "This invitation is already accepted")

        membership, created = EstablishmentMembership.objects.get_or_create(
            establishment=invite.establishment, profile=member_profile,
            defaults={
                'role': invite.role,
                'position_title': invite.position_title,
                'membership_level': invite.membership_level,
            },
        )
        if not created:
            # Already inside with a lesser role — the accepted offer is the newer fact.
            fields = []
            if role_rank(invite.role) > role_rank(membership.role):
                membership.role = invite.role
                fields.append('role')
            if invite.position_title:
                membership.position_title = invite.position_title
                fields.append('position_title')
            if invite.membership_level:
                membership.membership_level = invite.membership_level
                fields.append('membership_level')
            if fields:
                membership.save(update_fields=fields)

        _supersede_pending(invite.establishment, member_profile, exclude_id=invite.id)

    if is_request:
        _notify(
            member_profile, type='org_membership_changed',
            title=invite.establishment.name,
            body="Your request to join was approved",
            url=_org_url(invite.establishment),
            data={'establishment_id': invite.establishment_id, 'role': invite.role},
        )
    else:
        _notify(
            invite.created_by, type='org_invite_accepted',
            title=invite.establishment.name,
            body=f"{member_profile.display_name or member_profile.hna} accepted the invitation",
            url=f"{_org_url(invite.establishment)}/members",
            data={'establishment_id': invite.establishment_id, 'profile_id': member_profile.id},
        )

    return {"ok": True, "establishment_id": invite.establishment_id,
            "establishment_slug": invite.establishment.slug or '', "role": membership.role}


@router.post("/invites/{ident}/decline/", auth=ProfileAuth(),
             response={200: dict, 400: dict, 403: dict, 404: dict})
@ratelimit(group='members:invite_decline', key=user_or_ip, rate='30/m', method='POST')
def decline_invite(request, ident: str):
    """Refuse the proposal: the invited person says no, or a manager rejects an application."""
    invite = _resolve_invite(ident)
    profile = request.auth_profile

    if invite.status != EstablishmentInvite.Status.PENDING:
        raise HttpError(400, f"This invitation is already {invite.status.lower()}")

    if invite.direction == EstablishmentInvite.Direction.REQUEST:
        if not _is_org_side(request, invite):
            raise HttpError(403, "You cannot decide applications for this organization")
    else:
        if invite.target_profile_id and invite.target_profile_id != profile.id:
            raise HttpError(403, "This invitation is addressed to someone else")
        if not invite.target_profile_id and ident != invite.token:
            raise HttpError(403, "This invitation needs its link")

    invite.status = EstablishmentInvite.Status.DECLINED
    invite.resolved_at = timezone.now()
    invite.resolved_by = profile
    invite.save(update_fields=['status', 'resolved_at', 'resolved_by'])

    if invite.direction == EstablishmentInvite.Direction.REQUEST:
        _notify(
            invite.target_profile, type='org_membership_changed',
            title=invite.establishment.name,
            body="Your request to join was declined",
            url=_org_url(invite.establishment),
            data={'establishment_id': invite.establishment_id},
        )
    return {"ok": True}


@router.delete("/invites/{ident}/", auth=ProfileAuth(),
               response={200: dict, 400: dict, 403: dict, 404: dict})
@ratelimit(group='members:invite_withdraw', key=user_or_ip, rate='30/m', method='DELETE')
def withdraw_invite(request, ident: str):
    """Take back your own proposal: the organization revokes an offer, an applicant cancels."""
    invite = _resolve_invite(ident)
    profile = request.auth_profile

    if invite.status != EstablishmentInvite.Status.PENDING:
        raise HttpError(400, f"This invitation is already {invite.status.lower()}")

    if invite.direction == EstablishmentInvite.Direction.REQUEST:
        if invite.target_profile_id != profile.id:
            raise HttpError(403, "Not your request")
    elif not _is_org_side(request, invite):
        raise HttpError(403, "You cannot manage invitations for this organization")

    invite.status = EstablishmentInvite.Status.WITHDRAWN
    invite.resolved_at = timezone.now()
    invite.resolved_by = profile
    invite.save(update_fields=['status', 'resolved_at', 'resolved_by'])
    return {"ok": True}
