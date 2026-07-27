"""
Role resolution helpers for the universal ObjectAccess grant model.

Ownership stays on the host model's ``owner`` FK; ObjectAccess rows extend it
with shared roles. Effective role ladder: OWNER (the FK) > MANAGER > VIEWER.
What each role may do is decided by the endpoints of the host's app — these
helpers only answer "which role does this profile hold on this object".
"""

from django.db.models import Q

ROLE_VIEWER = 'VIEWER'
ROLE_MANAGER = 'MANAGER'
ROLE_OWNER = 'OWNER'

_ROLE_RANK = {ROLE_VIEWER: 1, ROLE_MANAGER: 2, ROLE_OWNER: 3}


def get_role(obj, profile):
    """Effective role of ``profile`` on ``obj`` (host with an ``owner`` FK)."""
    if profile is None:
        return None
    if getattr(obj, 'owner_id', None) == profile.id:
        return ROLE_OWNER
    from core.models import ObjectAccess
    grant = ObjectAccess.objects.filter(object_id=obj.id, profile=profile).only('role').first()
    return grant.role if grant else None


def has_role(obj, profile, min_role):
    """True when the effective role meets or exceeds ``min_role``."""
    role = get_role(obj, profile)
    return role is not None and _ROLE_RANK[role] >= _ROLE_RANK[min_role]


def role_satisfies(role, min_role):
    return role is not None and _ROLE_RANK.get(role, 0) >= _ROLE_RANK[min_role]


def granted_object_ids(profile, min_role=ROLE_VIEWER):
    """ULIDs granted to ``profile`` at ``min_role`` or above (owner FK not included)."""
    from core.models import ObjectAccess
    qs = ObjectAccess.objects.filter(profile=profile)
    if min_role == ROLE_MANAGER:
        qs = qs.filter(role=ROLE_MANAGER)
    return list(qs.values_list('object_id', flat=True))


def accessible_q(profile, min_role=ROLE_VIEWER):
    """Q filter for a host queryset (model with ``owner`` FK): own OR granted."""
    return Q(owner=profile) | Q(id__in=granted_object_ids(profile, min_role))
