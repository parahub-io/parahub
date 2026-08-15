"""Block enforcement helpers (Play UGC policy: user blocking with real effect).

Direction of enforcement:
- The blocker stops seeing the blocked profile's content (items, comments,
  presence avatars, profile search). The filter spans ALL of the viewer's own
  profiles — the viewer already knows their own account linkage, so no
  pseudonymity is leaked.
- The blocked side is matched per-profile only, never fanned out to the same
  account's other profiles: that would reveal which pseudonymous profiles
  belong together. The single exception is DM creation, where both accounts
  are compared account-to-account — the requester learns at most that some
  profile of theirs is blocked, nothing about third parties.
"""


def blocked_profile_ids(account_id) -> list:
    """Profile ULIDs blocked by any of the account's profiles.

    Returns a plain list (empty for anonymous/None) so callers can skip
    adding query conditions entirely in the common no-blocks case.
    """
    if not account_id:
        return []
    from identity.models import ProfileBlock
    return list(
        ProfileBlock.objects.filter(blocker__account_id=account_id)
        .values_list('blocked_id', flat=True)
    )


def blocked_ids_for_request(request) -> list:
    """Blocked profile ids for the request's authenticated account, else []."""
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False):
        return []
    return blocked_profile_ids(user.id)


def dm_blocked_between_accounts(account_id_1, account_id_2) -> bool:
    """True when a DM between the two accounts must be refused.

    Checked in both directions: any profile of either account blocking any
    profile of the other kills the channel. The error surfaced to the caller
    stays direction-neutral.
    """
    from django.db.models import Q
    from identity.models import ProfileBlock
    return ProfileBlock.objects.filter(
        Q(blocker__account_id=account_id_1, blocked__account_id=account_id_2) |
        Q(blocker__account_id=account_id_2, blocked__account_id=account_id_1)
    ).exists()
