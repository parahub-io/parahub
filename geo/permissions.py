"""
Establishment permission helpers for "act as establishment" feature.

Endpoints ask for a **capability**, never for a role: roles stay human-facing
("dispatcher", "driver") while code checks what the role is allowed to do, so a
new feature adds one string to `ROLE_CAPABILITIES` instead of another
`if role in {...}` spread across apps.

Usage:
    from geo.permissions import require_capability, has_capability

    # In an endpoint:
    est = require_capability(establishment_id, profile, 'content.post')
    # raises HttpError(403/404) if not allowed
"""

from django.db.models import Q
from ninja.errors import HttpError
from geo.models import Establishment, EstablishmentMembership

# What each role may do inside an organization. Single source of truth: the
# legacy `*_ROLES` constants below are derived from it, not maintained beside it.
#
# MEMBER appears nowhere on purpose. It is the entry role a self-service join
# hands out (see Establishment.membership_policy), so it carries no authority to
# act for the organization — authority is always something granted.
ROLE_CAPABILITIES = {
    # Content
    'content.post': {'OWNER', 'ADMIN', 'EMPLOYEE'},      # items, events, ads, posts "as org"
    'content.sign': {'OWNER', 'ADMIN'},                  # PGP on behalf of the org
    # Organization
    'members.manage': {'OWNER', 'ADMIN'},                # invites, role changes
    'finance.treasury': {'OWNER', 'ADMIN'},              # designate the treasurer
    'finance.audit': {'OWNER', 'ADMIN'},                 # designate the auditor (Fiscal Único)
    # Transit
    'transit.manage': {'OWNER', 'ADMIN'},                # routes, stops, agency settings
    'transit.dispatch': {'OWNER', 'ADMIN', 'EMPLOYEE'},  # vehicle assignments
    'transit.drive': {'OWNER', 'ADMIN', 'EMPLOYEE', 'CONTRACTOR'},  # shifts on org routes
    # Tickets
    'tickets.manage': {'OWNER', 'ADMIN'},                # create/edit/deactivate types
    'tickets.validate': {'OWNER', 'ADMIN', 'EMPLOYEE', 'CONTRACTOR'},  # scan at the door
}


# How far a role may reach when handing out authority. "Never above your own
# level" (the approved delegation rule) is this comparison and nothing else:
# an ADMIN appoints dispatchers and other admins, never an OWNER.
#
# EMPLOYEE and CONTRACTOR sit together: both are hired positions, neither may
# grant anything. MEMBER is the floor — the entry role a join hands out.
ROLE_RANK = {
    'OWNER': 3,
    'ADMIN': 2,
    'EMPLOYEE': 1,
    'CONTRACTOR': 1,
    'MEMBER': 0,
}

#: Roles an organization may hand out directly, without the person accepting.
#: Employment is an offline fact the employer already knows and answers for;
#: everything that carries standing inside the organization needs consent.
DIRECT_GRANT_ROLES = {'EMPLOYEE', 'CONTRACTOR'}


def role_rank(role) -> int:
    """Delegation level of a role. Unknown roles rank below MEMBER."""
    return ROLE_RANK.get(role, -1)


def actor_rank(profile, establishment) -> int:
    """
    How high `profile` stands inside `establishment` (-1 = outside it).

    The `owner` field ranks as OWNER without a membership row, the same implicit
    ownership `has_capability` honours.
    """
    if not profile:
        return -1
    if establishment.owner_id and establishment.owner_id == profile.id:
        return ROLE_RANK['OWNER']
    membership = EstablishmentMembership.objects.filter(
        profile=profile, establishment=establishment,
    ).only('role').first()
    return role_rank(membership.role) if membership else -1


def capability_roles(capability):
    """Roles that hold `capability`. Unknown capability is a programming error."""
    try:
        return ROLE_CAPABILITIES[capability]
    except KeyError:
        raise ValueError(f"Unknown capability: {capability}")


# Legacy aliases — same sets, kept because ~20 call sites still read this way.
POSTING_ROLES = ROLE_CAPABILITIES['content.post']
SIGNING_ROLES = ROLE_CAPABILITIES['content.sign']
TREASURER_MGMT_ROLES = ROLE_CAPABILITIES['finance.treasury']
AUDITOR_MGMT_ROLES = ROLE_CAPABILITIES['finance.audit']
DRIVING_ROLES = ROLE_CAPABILITIES['transit.drive']


def has_capability(profile, establishment, capability) -> bool:
    """
    True if profile holds `capability` in an establishment.

    Args:
        establishment: Establishment instance or its ULID
    """
    if not profile:
        return False

    roles = capability_roles(capability)
    est_id = getattr(establishment, 'id', establishment)

    if 'OWNER' in roles:
        # The `owner` field is an implicit OWNER — an establishment with zero
        # membership rows is still fully managed by whoever owns it.
        if isinstance(establishment, Establishment):
            if establishment.is_active and establishment.owner_id == profile.id:
                return True
        elif Establishment.objects.filter(id=est_id, owner=profile, is_active=True).exists():
            return True

    # A deactivated organization grants nothing — same rule as
    # require_capability (404) and establishment_ids_with_capability.
    return EstablishmentMembership.objects.filter(
        profile=profile, establishment_id=est_id, role__in=roles,
        establishment__is_active=True,
    ).exists()


def require_capability(establishment_id, profile, capability):
    """
    Capability-checked variant of get_establishment_for_action.

    Returns:
        Establishment instance

    Raises:
        HttpError(404) if establishment not found or inactive
        HttpError(403) if profile lacks the capability
    """
    try:
        establishment = Establishment.objects.get(id=establishment_id, is_active=True)
    except Establishment.DoesNotExist:
        raise HttpError(404, "Establishment not found")

    if not has_capability(profile, establishment, capability):
        raise HttpError(403, f"'{capability}' is not permitted for you in this organization")

    return establishment


def establishment_ids_with_capability(profile, capability):
    """Establishment ULIDs where profile holds `capability` (active ones only)."""
    if not profile:
        return set()

    roles = capability_roles(capability)
    ids = set(
        EstablishmentMembership.objects.filter(
            profile=profile, role__in=roles, establishment__is_active=True,
        ).values_list('establishment_id', flat=True)
    )
    if 'OWNER' in roles:
        ids.update(
            Establishment.objects.filter(owner=profile, is_active=True).values_list('id', flat=True)
        )
    return ids


def can_operate_agency(profile, agency, capability='transit.drive') -> bool:
    """
    True if profile may act for a transit agency.

    Two paths, in order of durability:
      - `Agency.establishment` — the organization runs the agency, so access
        follows membership and survives staff turnover (a public body's network
        must not hang on one personal account);
      - `Agency.owner` — the solo-operator fallback, a single Profile, which
        holds every capability over its own agency.
    """
    if not profile:
        return False

    if agency.owner_id and agency.owner_id == profile.id:
        return True

    if agency.establishment_id:
        return has_capability(profile, agency.establishment_id, capability)

    return False


def agencies_for_capability(profile, capability):
    """
    Agency queryset the profile may act for with `capability`.

    Usable as a subquery across relations — `route__agency__in=...` — which is
    how dispatch scopes assignments to the operator they belong to.
    """
    from geo.models import Agency

    if not profile:
        return Agency.objects.none()

    return Agency.objects.filter(
        Q(owner=profile)
        | Q(establishment_id__in=establishment_ids_with_capability(profile, capability))
    )


def get_establishment_for_action(establishment_id, profile, allowed_roles):
    """
    Validate that profile can act on behalf of establishment.

    Args:
        establishment_id: Establishment ULID
        profile: Profile performing the action
        allowed_roles: Set of role strings that are permitted

    Returns:
        Establishment instance

    Raises:
        HttpError(404) if establishment not found or inactive
        HttpError(403) if profile doesn't have required role
    """
    try:
        establishment = Establishment.objects.get(id=establishment_id, is_active=True)
    except Establishment.DoesNotExist:
        raise HttpError(404, "Establishment not found")

    # Owner of the establishment always has access
    if establishment.owner_id == profile.id and 'OWNER' in allowed_roles:
        return establishment

    # Check membership role
    try:
        membership = EstablishmentMembership.objects.get(
            profile=profile, establishment=establishment
        )
    except EstablishmentMembership.DoesNotExist:
        raise HttpError(403, "Not a member of this establishment")

    if membership.role not in allowed_roles:
        raise HttpError(403, f"Role '{membership.role}' is not permitted for this action")

    return establishment


def get_treasurer_profile(establishment):
    """
    Get the treasurer's Profile for an establishment.

    Returns:
        Profile instance or None if no treasurer is set
    """
    membership = EstablishmentMembership.objects.filter(
        establishment=establishment, is_treasurer=True
    ).select_related('profile').first()

    return membership.profile if membership else None


def get_auditor_profile(establishment):
    """
    Get the auditor's (Fiscal Único) Profile for an establishment.

    Returns:
        Profile instance or None if no auditor is set
    """
    membership = EstablishmentMembership.objects.filter(
        establishment=establishment, is_auditor=True
    ).select_related('profile').first()

    return membership.profile if membership else None


def get_user_role(establishment, profile):
    """
    Get the user's role in an establishment.

    Returns:
        Role string or None if not a member. Owner gets 'OWNER'.
    """
    if establishment.owner_id == profile.id:
        return 'OWNER'

    try:
        membership = EstablishmentMembership.objects.get(
            profile=profile, establishment=establishment
        )
        return membership.role
    except EstablishmentMembership.DoesNotExist:
        return None
