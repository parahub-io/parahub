"""
6-dimension reputation calculator.

Dimension ceilings (owner-approved weights) sum to 100:
  Identity     0–25  WoT verifications received
  Commerce     0–15  contract review quality, weighted by review volume
  Community    0–20  events attended + establishment memberships
  Contribution 0–15  verifications given + live listings + barter cycles closed
  Governance   0–15  poll votes + delegations held + civic ideas + budget votes
  Reliability  0–10  contract completion + debt repayment, weighted by volume
  Total        0–100

Every curve is anchored: `_curve(n, ceiling, target)` returns exactly `ceiling`
at `target` units, so a ceiling is a number someone can actually reach instead
of an asymptote. Targets are set at "active member of a working community"
levels, not at theoretical extremes.

Where a dimension has several inputs, the sub-ceilings deliberately sum above
the dimension ceiling: a strong showing in two of three inputs still maxes the
dimension, while no single cheap input can max it alone.

Reliability is the one dimension that can score below its neutral point: it
measures kept promises, so a broken record has to cost something. Profiles with
no commitments at all sit at the neutral 5.0 and report
`reliability_has_data=False` so callers can render "no data" instead of a
half-filled bar.
"""

import math
from decimal import Decimal

from django.db.models import Avg, Q
from django.utils import timezone

# Dimension ceilings — the denominators the UI shows and the sum that makes 100.
MAXIMA = {
    'identity': 25,
    'commerce': 15,
    'community': 20,
    'contribution': 15,
    'governance': 15,
    'reliability': 10,
}

# Units at which each input reaches its own ceiling.
TARGET_VERIFICATIONS_RECEIVED = 10   # WoT gate is 3; 10 is a well-known member
TARGET_REVIEWS = 10                  # full weight for review quality
TARGET_EVENTS = 10
TARGET_MEMBERSHIPS = 3
TARGET_VERIFICATIONS_GIVEN = 10
TARGET_LISTINGS = 10
TARGET_BARTER_CYCLES = 5
TARGET_POLL_VOTES = 10
TARGET_DELEGATIONS = 3
TARGET_CIVIC_IDEAS = 2               # ideas that passed the peer support threshold
TARGET_CIVIC_SUPPORTS = 10
TARGET_BUDGET_VOTES = 2

# Commitments needed before a completion rate is trusted at face value; below
# this the rate is blended toward the neutral 0.5.
RELIABILITY_CONFIDENT_N = 3

NEUTRAL_RELIABILITY = 5.0


def _curve(n: int, ceiling: float, target: int) -> float:
    """Concave score for `n` units, reaching `ceiling` exactly at `target` units."""
    if n <= 0:
        return 0.0
    return min(ceiling, ceiling * math.log1p(n) / math.log1p(target))


def _saturation(n: int, target: int) -> float:
    """0..1 confidence factor, reaching 1.0 at `target` units."""
    if n <= 0:
        return 0.0
    return min(1.0, math.log1p(n) / math.log1p(target))


def _q(value: float) -> Decimal:
    """Quantize a dimension score to the stored precision."""
    return Decimal(str(round(float(value), 4))).quantize(Decimal('0.0001'))


def calculate_reputation(profile) -> dict:
    """Calculate 6-dimension reputation score for a profile.

    Returns dict with each dimension score, total, active_dimensions count,
    whether reliability had any data, and the dimension ceilings.
    """
    from identity.models import Verification
    from contracts.models import Contract, ContractReview
    from geo.models import EventParticipant, EstablishmentMembership
    from market.models import Item
    from governance.models import (
        PollVote, PollVoteDelegation, StandingDelegation,
        CivicIdea, CivicIdeaSupport,
    )
    from barter.models import Exchange
    from debts.models import Debt
    from treasury.models import BudgetAllocation

    # --- Identity (0–25) ---
    verifications = Verification.objects.filter(
        verified_profile=profile, is_active=True
    ).count()
    identity = _curve(verifications, MAXIMA['identity'], TARGET_VERIFICATIONS_RECEIVED)

    # --- Commerce (0–15) ---
    # Quality maps 1★→0.0 and 5★→1.0, so a bad record earns nothing rather than
    # a floor; volume decides how much of that quality is credited.
    reviews = ContractReview.objects.filter(reviewed=profile)
    review_count = reviews.count()
    if review_count:
        avg = float(reviews.aggregate(avg=Avg('rating'))['avg'] or 0)
        quality = min(1.0, max(0.0, (avg - 1.0) / 4.0))
        commerce = MAXIMA['commerce'] * quality * _saturation(review_count, TARGET_REVIEWS)
    else:
        commerce = 0.0

    # --- Community (0–20) ---
    # Only events that have started count: an RSVP to a future event is a plan,
    # not participation. Cancelled events never count.
    events = EventParticipant.objects.filter(
        profile=profile, status='GOING', event__starts_at__lt=timezone.now(),
    ).exclude(event__status='CANCELLED').count()
    memberships = EstablishmentMembership.objects.filter(profile=profile).count()
    community = min(float(MAXIMA['community']), (
        _curve(events, 13.0, TARGET_EVENTS)
        + _curve(memberships, 9.0, TARGET_MEMBERSHIPS)
    ))

    # --- Contribution (0–15) ---
    # Closing a barter cycle outweighs posting: listings are the cheapest signal
    # here, so they carry the smallest sub-ceiling.
    verifs_given = Verification.objects.filter(
        verifier=profile, is_active=True
    ).count()
    items_live = Item.objects.filter(owner=profile, is_active=True).count()
    barter_completed = Exchange.objects.filter(
        status=Exchange.Status.COMPLETED,
        user_chain__contains=str(profile.id),
    ).count()
    contribution = min(float(MAXIMA['contribution']), (
        _curve(verifs_given, 7.0, TARGET_VERIFICATIONS_GIVEN)
        + _curve(items_live, 4.0, TARGET_LISTINGS)
        + _curve(barter_completed, 8.0, TARGET_BARTER_CYCLES)
    ))

    # --- Governance (0–15) ---
    # governance.OpinionVote (civic barometer) is deliberately absent: those
    # ballots carry no profile FK by design (GDPR Art. 9, see
    # PK/civic-polls-system.md), so crediting them would break pseudonymity.
    # Civic participation is credited through the profile-linked surfaces only.
    votes = PollVote.objects.filter(voter=profile).count()
    delegations = (
        PollVoteDelegation.objects.filter(delegate=profile, is_active=True).count()
        + StandingDelegation.objects.filter(
            delegate=profile, is_active=True,
            accepted_at__isnull=False, revoked_at__isnull=True,
        ).count()
    )
    civic_ideas = CivicIdea.objects.filter(
        author=profile,
        status__in=[CivicIdea.Status.REVIEW, CivicIdea.Status.PROMOTED],
    ).count()
    civic_supports = CivicIdeaSupport.objects.filter(profile=profile).count()
    budget_votes = BudgetAllocation.objects.filter(profile=profile).count()
    governance = min(float(MAXIMA['governance']), (
        _curve(votes, 7.0, TARGET_POLL_VOTES)
        + _curve(delegations, 5.0, TARGET_DELEGATIONS)
        + _curve(civic_ideas, 3.0, TARGET_CIVIC_IDEAS)
        + _curve(civic_supports, 2.0, TARGET_CIVIC_SUPPORTS)
        + _curve(budget_votes, 3.0, TARGET_BUDGET_VOTES)
    ))

    # --- Reliability (0–10) ---
    # A contract cancelled after both parties signed stays in the denominator:
    # walking away from a signed commitment must not erase the record.
    party_q = Q(creator=profile) | Q(partner=profile)
    committed_q = (
        Q(status__in=['SIGNED', 'COMPLETED'])
        | Q(status='CANCELLED', partner_signed_at__isnull=False)
    )
    contracts_done = Contract.objects.filter(party_q, status='COMPLETED').count()
    contracts_total = Contract.objects.filter(party_q).filter(committed_q).count()

    debts_repaid = Debt.objects.filter(
        debtor=profile, status='FULLY_SETTLED'
    ).count()
    debts_total = Debt.objects.filter(
        debtor=profile, status__in=['ACTIVE', 'PARTIALLY_SETTLED', 'FULLY_SETTLED']
    ).count()

    # Each component is scored only if it has data, blended toward neutral while
    # the sample is small, and re-normalized so a missing component neither adds
    # free credit nor drags the score down.
    components = []
    if contracts_total:
        rate = contracts_done / contracts_total
        confidence = min(1.0, contracts_total / RELIABILITY_CONFIDENT_N)
        components.append((0.6, confidence * rate + (1 - confidence) * 0.5))
    if debts_total:
        rate = debts_repaid / debts_total
        confidence = min(1.0, debts_total / RELIABILITY_CONFIDENT_N)
        components.append((0.4, confidence * rate + (1 - confidence) * 0.5))

    reliability_has_data = bool(components)
    if reliability_has_data:
        weight_sum = sum(weight for weight, _ in components)
        reliability = MAXIMA['reliability'] * (
            sum(weight * score for weight, score in components) / weight_sum
        )
    else:
        reliability = NEUTRAL_RELIABILITY

    # --- Total (sum of the values actually reported) ---
    scores = {
        'identity': _q(identity),
        'commerce': _q(commerce),
        'community': _q(community),
        'contribution': _q(contribution),
        'governance': _q(governance),
        'reliability': _q(reliability),
    }

    active = sum(
        1 for key, value in scores.items()
        if key != 'reliability' and value > 0
    ) + (1 if reliability_has_data else 0)

    return {
        **scores,
        'total': sum(scores.values()).quantize(Decimal('0.0001')),
        'active_dimensions': active,
        'reliability_has_data': reliability_has_data,
        'maxima': dict(MAXIMA),
    }
