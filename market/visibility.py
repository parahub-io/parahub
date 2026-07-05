"""Item visibility access-control — the single source of truth for who may
see an Item, used by every surface that serves items to a possibly-anonymous
viewer (market list/detail, rental boards, profile/establishment counts).

v1 tiers (market.Item.Visibility):
  PUBLIC      — visible to everyone, including anonymous visitors and search
                engine crawlers. The default (civic-router discoverability).
  REGISTERED  — visible only to authenticated parahub users (any signed-in
                account, via JWT or session); hidden from anonymous + SEO.

REGISTERED means "any logged-in user", which is why enforcement collapses to a
single bit: is the request authenticated? If yes, no restriction (the viewer
sees every tier); if no, only PUBLIC. A future CIRCLE/WoT tier would NOT be a
single bit (it needs a per-viewer graph query) — deliberately out of v1.

Enforce at EVERY anonymous-reachable item-serving surface. Half-enforcement
leaks: an item hidden from the list but reachable by direct URL (or counted in
a public badge) gives false privacy, which is worse than none.
"""
from django.db.models import Q

from .models import Item


def viewer_is_authenticated(request) -> bool:
    """True when the request carries an authenticated parahub user.

    Reads request.auth_profile, which OptionalProfileAuth sets for both JWT
    (Bearer) and session auth. request.user is NOT reliable here — a JWT-only
    client (mobile) has an anonymous request.user despite being signed in.
    """
    return getattr(request, 'auth_profile', None) is not None


def visible_items_q(request) -> Q:
    """Q() restricting an Item queryset to what this request may see.

    Authenticated -> no restriction (sees PUBLIC + REGISTERED).
    Anonymous     -> PUBLIC only.
    """
    if viewer_is_authenticated(request):
        return Q()
    return Q(visibility=Item.Visibility.PUBLIC)


def can_view_item(item, request) -> bool:
    """Single-item gate for detail endpoints (return 404 when False)."""
    if item.visibility == Item.Visibility.PUBLIC:
        return True
    return viewer_is_authenticated(request)


def visible_items_sql(request, alias: str = 'i'):
    """SQL counterpart of visible_items_q for the raw-SQL list fast path.

    Returns (predicate, params). The predicate references the given table
    alias; params is empty for the authenticated case and carries the PUBLIC
    sentinel (parameterised, never interpolated) for the anonymous case.
    """
    if viewer_is_authenticated(request):
        return "TRUE", []
    return f"{alias}.visibility = %s", [Item.Visibility.PUBLIC]
