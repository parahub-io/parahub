"""
Establishment permission helpers for "act as establishment" feature.

Usage:
    from geo.permissions import get_establishment_for_action, get_treasurer_profile

    # In an endpoint:
    est = get_establishment_for_action(establishment_id, profile, POSTING_ROLES)
    # raises HttpError(403/404) if not allowed
"""

from ninja.errors import HttpError
from geo.models import Establishment, EstablishmentMembership

# Roles that can post content (items, events, ads) on behalf of establishment
POSTING_ROLES = {'OWNER', 'ADMIN', 'MEMBER'}

# Roles that can sign documents on behalf of establishment
SIGNING_ROLES = {'OWNER', 'ADMIN'}

# Roles that can manage the treasurer
TREASURER_MGMT_ROLES = {'OWNER', 'ADMIN'}

# Roles that can manage the auditor (Fiscal Único)
AUDITOR_MGMT_ROLES = {'OWNER', 'ADMIN'}


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
