"""Demo/test poll isolation — keep seed data out of the public feed.

Mirrors the CMS convention (cms/api/helpers.py): polls created by test/bot
accounts, or explicitly flagged demo in ``attributes``, are visible only to
staff and test accounts. Everyone else — anonymous visitors and ordinary
members alike — sees a clean feed. See PK/governance-polls-system.md.
"""


def viewer_is_privileged(request) -> bool:
    """True if the resolved viewer is a staff or test account.

    Works with OptionalProfileAuth endpoints (``request.auth_profile``) and
    falls back to Django session auth (``request.user``).
    """
    profile = getattr(request, 'auth_profile', None)
    if profile is not None:
        acc = getattr(profile, 'account', None)
        return bool(acc and (acc.is_staff or acc.is_test))
    user = getattr(request, 'user', None)
    if user is not None and getattr(user, 'is_authenticated', False):
        return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_test', False))
    return False


def exclude_demo_polls(qs):
    """Drop polls created by test/bot accounts or flagged demo in attributes.

    Uses ``__contains`` for the JSONField exclude: a plain ``demo=True`` lookup
    evaluates to NULL when the key is absent, and ``NOT NULL`` is NULL (falsy),
    which would drop every row.
    """
    return (
        qs.exclude(created_by__account__is_test=True)
          .exclude(created_by__account__is_bot=True)
          .exclude(attributes__contains={'demo': True})
          .exclude(attributes__has_key='__demo_seed')
    )
