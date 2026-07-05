"""
Shared access checks and demo-content exclusion for CMS endpoints.
"""


import logging

from ninja.errors import HttpError


from identity.models import Profile, Verification

logger = logging.getLogger(__name__)

def _check_wot3(profile: Profile):
    """Raise 403 if profile doesn't meet WoT 3+ requirement."""
    if profile.account.is_superuser:
        return
    if profile.is_foundation_member():
        return
    count = Verification.objects.filter(
        verified_profile=profile,
        is_active=True,
    ).count()
    if count < 3:
        raise HttpError(403, "Requires WoT level 3+ to publish blog posts")

def _is_privileged_user(request) -> bool:
    """Return True if the request comes from staff or a test account."""
    user = getattr(request, 'user', None)
    if user and getattr(user, 'is_authenticated', False):
        return getattr(user, 'is_staff', False) or getattr(user, 'is_test', False)
    return False

def _is_demo_obj(obj) -> bool:
    """Check if object has demo markers in attributes/spec_data."""
    attrs = getattr(obj, 'attributes', None) or {}
    if attrs.get('demo') or attrs.get('__demo_seed'):
        return True
    spec = getattr(obj, 'spec_data', None) or {}
    if spec.get('__demo_seed'):
        return True
    author = getattr(obj, 'author', None)
    if author and getattr(author, 'account', None):
        if author.account.is_test or author.account.is_bot:
            return True
    return False

DEMO_ATTR_KEYS = ('demo', '__demo_seed')

def _exclude_demo_posts(qs):
    """Exclude posts with demo markers or from test/bot accounts."""
    # Use __contains for JSONField exclude — plain __demo=True evaluates to NULL
    # when the key is absent, and NOT NULL is NULL (falsy), excluding ALL rows.
    qs = qs.exclude(attributes__contains={'demo': True}).exclude(attributes__has_key='__demo_seed')
    qs = qs.exclude(author__account__is_test=True).exclude(author__account__is_bot=True)
    return qs

def _exclude_demo_sites(qs):
    """Exclude sites with demo markers or owned by test/bot accounts."""
    qs = qs.exclude(attributes__contains={'demo': True}).exclude(attributes__has_key='__demo_seed')
    qs = qs.exclude(establishment__owner__account__is_test=True).exclude(establishment__owner__account__is_bot=True)
    qs = qs.exclude(profile__account__is_test=True).exclude(profile__account__is_bot=True)
    return qs

def _exclude_demo_pages(qs):
    """Exclude site pages with demo markers or from demo sites."""
    qs = qs.exclude(attributes__contains={'demo': True}).exclude(attributes__has_key='__demo_seed')
    qs = qs.exclude(site__attributes__contains={'demo': True}).exclude(site__attributes__has_key='__demo_seed')
    return qs

def _require_profile_owner(request, profile_name: str) -> 'Profile':
    """Verify the authenticated user owns this profile (or is superuser)."""
    profile: Profile = request.auth
    if profile.local_name != profile_name and not profile.account.is_superuser:
        raise HttpError(403, "Not your profile")
    return profile
