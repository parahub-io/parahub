"""
Shared access checks and demo-content exclusion for CMS endpoints.
"""


import logging

from ninja.errors import HttpError


from identity.models import Profile, Verification
from identity.visibility import account_is_synthetic, exclude_test_authors, viewer_sees_test_content

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
    return viewer_sees_test_content(request)

def _is_demo_obj(obj) -> bool:
    """Check if object has demo markers in attributes/spec_data."""
    attrs = getattr(obj, 'attributes', None) or {}
    if attrs.get('demo') or attrs.get('__demo_seed'):
        return True
    spec = getattr(obj, 'spec_data', None) or {}
    if spec.get('__demo_seed'):
        return True
    author = getattr(obj, 'author', None)
    if author and account_is_synthetic(getattr(author, 'account', None)):
        return True
    return False

DEMO_ATTR_KEYS = ('demo', '__demo_seed')

def _exclude_demo_posts(qs):
    """Exclude posts with demo markers or from test/bot accounts."""
    # Use __contains for JSONField exclude — plain __demo=True evaluates to NULL
    # when the key is absent, and NOT NULL is NULL (falsy), excluding ALL rows.
    qs = qs.exclude(attributes__contains={'demo': True}).exclude(attributes__has_key='__demo_seed')
    qs = exclude_test_authors(qs, field='author')
    return qs

def _exclude_demo_sites(qs):
    """Exclude sites with demo markers or owned by test/bot accounts."""
    qs = qs.exclude(attributes__contains={'demo': True}).exclude(attributes__has_key='__demo_seed')
    qs = exclude_test_authors(qs, field='establishment__owner')
    qs = exclude_test_authors(qs, field='profile')
    return qs

def _exclude_demo_pages(qs):
    """Exclude site pages with demo markers, from demo sites, or belonging to a
    demo/synthetic owner.

    The owner-side checks are what actually catch seeded mini-sites: `seed_demo_*`
    marks the Establishment, not the Site it later gets, so a page whose own
    attributes are empty still belongs to demo data. Sitemap-only helper, hence
    the unconditional exclude_test_authors (no viewer to exempt).
    """
    qs = qs.exclude(attributes__contains={'demo': True}).exclude(attributes__has_key='__demo_seed')
    qs = qs.exclude(site__attributes__contains={'demo': True}).exclude(site__attributes__has_key='__demo_seed')
    qs = (qs.exclude(site__establishment__attributes__contains={'demo': True})
            .exclude(site__establishment__attributes__has_key='__demo_seed'))
    qs = exclude_test_authors(qs, field='site__establishment__owner')
    qs = exclude_test_authors(qs, field='site__profile')
    return qs

def _require_profile_owner(request, profile_name: str) -> 'Profile':
    """Verify the authenticated user owns this profile (or is superuser)."""
    profile: Profile = request.auth
    if profile.local_name != profile_name and not profile.account.is_superuser:
        raise HttpError(403, "Not your profile")
    return profile
