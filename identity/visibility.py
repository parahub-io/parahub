"""Synthetic-content visibility — the single source of truth for hiding
test/bot-authored content from real users.

Platform-wide policy: content authored by accounts flagged ``is_test`` or
``is_bot`` (identity.Account) is invisible to real users; only staff and
test-account viewers see it. Bot viewers are NOT exempt — AI agents must
browse the same feed a real member would. This isolation is what makes the
prod-DB testing strategy safe (Yellow Gate agents, seed users, demo data all
live in production), so EVERY anonymous- or member-reachable listing surface
must apply it. Half-enforcement leaks test junk into real feeds.

App-specific composites (cms demo markers, governance demo attributes) keep
their extra excludes but delegate the viewer exemption and the author-flag
excludes here.
"""


def viewer_account(request):
    """Resolve the viewing Account from a request.

    Reads ``request.auth_profile`` first — set by both ProfileAuth (JWT) and
    OptionalProfileAuth (JWT or session). ``request.user`` alone is NOT
    reliable: a JWT-only client (mobile) has an anonymous ``request.user``
    despite being signed in. Falls back to ``request.user`` for plain
    session-auth endpoints. Returns None for anonymous viewers.
    """
    profile = getattr(request, 'auth_profile', None)
    if profile is not None:
        return getattr(profile, 'account', None)
    user = getattr(request, 'user', None)
    if user is not None and getattr(user, 'is_authenticated', False):
        return user
    return None


def account_sees_test_content(account) -> bool:
    """Viewer-side predicate on an already-resolved Account. Use this when the
    endpoint resolved the viewer itself (optional-auth surfaces that must not
    mutate ``request``); ``viewer_sees_test_content`` is the request-based twin
    and both share this one rule."""
    return bool(account and (getattr(account, 'is_staff', False)
                             or getattr(account, 'is_test', False)))


def viewer_sees_test_content(request) -> bool:
    """Canonical exemption check: staff and test-account viewers see
    synthetic content; everyone else (anonymous, real members, bot viewers)
    does not."""
    return account_sees_test_content(viewer_account(request))


def account_is_synthetic(account) -> bool:
    """Content-side predicate: the authoring account is a test or bot
    account. Pass an Account; None returns False (caller decides how to
    treat authorless content)."""
    return bool(account and (account.is_test or account.is_bot))


def exclude_test_authors(qs, request=None, field='owner'):
    """Hide synthetic-authored rows from a queryset unless the viewer is
    exempt.

    ``field`` is the FK path from the queryset's model to the authoring
    Profile ('owner', 'organizer', 'created_by', 'author',
    'establishment__owner'); pass field='' when the queryset is of Profile
    itself. ``request=None`` means "no viewer" — always exclude (sitemaps,
    SEO surfaces, aggregate counters that should reflect the real community).
    """
    if request is not None and viewer_sees_test_content(request):
        return qs
    prefix = f'{field}__account' if field else 'account'
    return qs.exclude(**{f'{prefix}__is_test': True}).exclude(**{f'{prefix}__is_bot': True})


def test_authors_sql(request, alias='a'):
    """SQL twin of exclude_test_authors for raw-SQL fast paths.

    Returns ``(predicate, params)`` where the predicate references the
    already-joined identity_account table by ``alias``. Params is always
    empty — the shape mirrors market.visibility.visible_items_sql so call
    sites compose both the same way.
    """
    if viewer_sees_test_content(request):
        return "TRUE", []
    return f"({alias}.is_test = FALSE AND {alias}.is_bot = FALSE)", []
