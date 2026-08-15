"""Demo/test poll isolation — keep seed data out of the public feed.

Mirrors the CMS convention (cms/api/helpers.py): polls created by test/bot
accounts, or explicitly flagged demo in ``attributes``, are visible only to
staff and test accounts. Everyone else — anonymous visitors and ordinary
members alike — sees a clean feed. See PK/governance-polls-system.md.
"""


from identity.visibility import exclude_test_authors, viewer_sees_test_content


def viewer_is_privileged(request) -> bool:
    """True if the resolved viewer is a staff or test account.

    Thin alias over the platform-wide check in identity.visibility.
    """
    return viewer_sees_test_content(request)


def exclude_demo_polls(qs):
    """Drop polls created by test/bot accounts or flagged demo in attributes.

    Uses ``__contains`` for the JSONField exclude: a plain ``demo=True`` lookup
    evaluates to NULL when the key is absent, and ``NOT NULL`` is NULL (falsy),
    which would drop every row.
    """
    return (
        exclude_test_authors(qs, field='created_by')
          .exclude(attributes__contains={'demo': True})
          .exclude(attributes__has_key='__demo_seed')
    )
