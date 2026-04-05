"""Cooperative share helpers — governance integration, distribution generation."""
from decimal import Decimal

from core.models import ObjectShare, ObjectDistribution, DistributionLine


def setup_share_weighted_voters(poll, object_id) -> int:
    """
    Populate PollEligibleVoter from ObjectShare for weighted voting.
    Pattern follows geo/services/condominium.py:setup_poll_voters().
    """
    from governance.models import PollEligibleVoter

    shares = ObjectShare.objects.filter(
        object_id=object_id,
        is_active=True,
    ).select_related('profile')

    count = 0
    seen_profiles = set()
    for s in shares:
        if s.profile_id in seen_profiles:
            voter = PollEligibleVoter.objects.get(poll=poll, profile=s.profile)
            voter.weight += s.share_percent
            voter.save(update_fields=['weight'])
        else:
            PollEligibleVoter.objects.create(
                poll=poll,
                profile=s.profile,
                weight=s.share_percent,
            )
            seen_profiles.add(s.profile_id)
            count += 1

    return count


def generate_distribution_lines(distribution: ObjectDistribution) -> int:
    """
    Generate DistributionLine entries from active shares for a distribution.
    Called when distribution status moves to APPROVED.
    Returns number of lines created.
    """
    shares = ObjectShare.objects.filter(
        object_id=distribution.object_id,
        is_active=True,
    ).select_related('profile')

    lines = []
    for s in shares:
        amount = (distribution.total_amount * s.share_percent / Decimal('100')).quantize(Decimal('0.01'))
        if amount > 0:
            lines.append(DistributionLine(
                distribution=distribution,
                profile=s.profile,
                share_percent=s.share_percent,
                amount=amount,
            ))

    DistributionLine.objects.bulk_create(lines)
    return len(lines)
