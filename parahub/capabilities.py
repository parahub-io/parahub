"""
Platform capabilities — authority over surfaces no organization owns.

The other half of the delegation model. Authority that belongs to a team lives
on `EstablishmentMembership` and is asked for with `geo.permissions`; this
module covers the handful of node-level surfaces that have no organization
behind them: the federation registry, the trust graph, the infrastructure
consoles, the urbanística dossiê.

Held on the **Account**, not the Profile: the login is who a sign-off is
attributed to, which is why `urban_validators` was put there in the first place.
A capability is one Django group, so granting it is a group membership and
nothing else — no new model, no second source of truth.

    from parahub.capabilities import require_platform_capability

    account = require_platform_capability(request, 'federation.admin')

`is_staff` still passes every check. It is the superuser override the design
keeps, and until the groups are populated it is also what keeps today's access
working — but the *question* the code asks is now the capability, so handing
one out no longer means handing out Django admin with it.
"""

#: capability → the Django group that grants it.
PLATFORM_CAPABILITIES = {
    # Gate-L2 urbanística sign-off (`geo/endpoints/urban.py`) — a licensed
    # urbanista gets this surface and nothing else.
    'urban.validate': 'urban_validators',
    # Trust-graph audit and post-hoc takedowns (WoT edge list, civic ideas).
    'moderation.review': 'moderators',
    # Node infrastructure: server health, mesh and monitoring consoles.
    'infra.operate': 'infra_operators',
    # Federation registry: peers, organizations, migrations.
    'federation.admin': 'federation_admins',
}


#: What each capability opens, for the owner's grant screen. Staff-facing English,
#: like the rest of the node consoles.
PLATFORM_CAPABILITY_INFO = {
    'urban.validate': (
        'Urbanística validator',
        'Signs off Gate-L2 dossiês on plot analyses.',
    ),
    'moderation.review': (
        'Moderator',
        'Works the abuse-report queue and the trust-graph audit.',
    ),
    'infra.operate': (
        'Infrastructure operator',
        'Reads server health and the node monitoring consoles.',
    ),
    'federation.admin': (
        'Federation admin',
        'Registry writes, peers, organizations, profile migrations.',
    ),
}


def platform_capabilities(account) -> set:
    """Every platform capability this account holds (empty set for anonymous)."""
    if account is None or not getattr(account, 'is_authenticated', False):
        return set()
    if not account.is_active:
        return set()
    if account.is_staff:
        return set(PLATFORM_CAPABILITIES)
    groups = set(account.groups.values_list('name', flat=True))
    return {cap for cap, group in PLATFORM_CAPABILITIES.items() if group in groups}


def has_platform_capability(account, capability) -> bool:
    """True if the account holds `capability`. Unknown capability is a bug, not a denial."""
    if capability not in PLATFORM_CAPABILITIES:
        raise ValueError(f"Unknown platform capability: {capability}")
    return capability in platform_capabilities(account)


def account_from_request(request):
    """
    The Account behind a request, whichever auth class served it.

    `request.user` is set for session and JWT alike; the profile-based auth
    classes also hang the Profile on the request, and its `account` is the same
    login.
    """
    account = getattr(request, 'user', None)
    if account is not None and getattr(account, 'is_authenticated', False):
        return account
    profile = getattr(request, 'auth_profile', None) or getattr(request, 'auth', None)
    return getattr(profile, 'account', None)


def require_platform_capability(request, capability):
    """
    The caller's Account, or 403.

    Returns the Account rather than a bool because these surfaces attribute what
    they do — a dossiê sign-off, a registry write — to the login that did it.
    """
    from ninja.errors import HttpError

    account = account_from_request(request)
    if not has_platform_capability(account, capability):
        raise HttpError(403, f"'{capability}' is not permitted for you")
    return account


def require_superuser(request):
    """
    The caller's Account, or 403 — for handing a capability *out*.

    Holding a capability never includes widening the circle that holds it, and
    `is_staff` does not either: staff resolves to every capability above, so
    letting staff grant them would make the whole set self-propagating. Only the
    node's superuser appoints, which is where the design puts platform authority.
    """
    from ninja.errors import HttpError

    account = account_from_request(request)
    if account is None or not getattr(account, 'is_superuser', False) or not account.is_active:
        raise HttpError(403, "Only the node owner can grant platform capabilities")
    return account
