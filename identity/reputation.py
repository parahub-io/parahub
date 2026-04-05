"""
6-dimension reputation calculator.

Dimensions (owner-approved weights):
  Identity     0–25  (WoT verifications)
  Commerce     0–15  (contract review avg, min 3 reviews)
  Community    0–20  (events attended + org memberships)
  Contribution 0–15  (verifications given + items + barter exchanges)
  Governance   0–15  (poll votes + delegations received)
  Reliability  0–10  (contract completion + debt repayment rates)
  Total        0–100
"""

import math
from decimal import Decimal

from django.db.models import Avg, Q


def calculate_reputation(profile) -> dict:
    """Calculate 6-dimension reputation score for a profile.

    Returns dict with each dimension score, total, and active_dimensions count.
    """
    from identity.models import Verification, ContractReview, Contract
    from geo.models import EventParticipant, EstablishmentMembership
    from market.models import Item
    from governance.models import PollVote, PollVoteDelegation
    from barter.models import Exchange
    from debts.models import Debt

    # --- Identity (0–25) ---
    verifications = Verification.objects.filter(
        verified_profile=profile, is_active=True
    ).count()
    identity = min(Decimal('25'), Decimal(str(
        8.3 * math.log(1 + verifications)
    )))

    # --- Commerce (0–15) ---
    reviews = ContractReview.objects.filter(reviewed=profile)
    review_count = reviews.count()
    if review_count >= 3:
        avg = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
        commerce = min(Decimal('15'), Decimal(str(avg * 3.0)))
    else:
        commerce = Decimal('0')

    # --- Community (0–20) ---
    events = EventParticipant.objects.filter(
        profile=profile, status='GOING'
    ).count()
    memberships = EstablishmentMembership.objects.filter(
        profile=profile
    ).count()
    community = min(Decimal('20'), Decimal(str(
        7 * math.log(1 + events) + 4 * math.log(1 + memberships)
    )))

    # --- Contribution (0–15) ---
    verifs_given = Verification.objects.filter(
        verifier=profile, is_active=True
    ).count()
    items_created = Item.objects.filter(owner=profile).count()
    barter_completed = Exchange.objects.filter(
        status=Exchange.Status.COMPLETED,
        user_chain__contains=str(profile.id),
    ).count()
    contribution = min(Decimal('15'), Decimal(str(
        5 * math.log(1 + verifs_given)
        + 2 * math.log(1 + items_created)
        + 4 * math.log(1 + barter_completed)
    )))

    # --- Governance (0–15) ---
    votes = PollVote.objects.filter(voter=profile).count()
    delegations = PollVoteDelegation.objects.filter(
        delegate=profile, is_active=True
    ).count()
    governance = min(Decimal('15'), Decimal(str(
        5 * math.log(1 + votes) + 6 * math.log(1 + delegations)
    )))

    # --- Reliability (0–10) ---
    party_q = Q(creator=profile) | Q(partner=profile)
    completed = Contract.objects.filter(
        party_q, status='COMPLETED'
    ).count()
    total_contracts = Contract.objects.filter(
        party_q, status__in=['SIGNED', 'COMPLETED']
    ).count()

    repaid = Debt.objects.filter(
        debtor=profile, status='FULLY_SETTLED'
    ).count()
    total_debts = Debt.objects.filter(
        debtor=profile, status__in=['ACTIVE', 'PARTIALLY_SETTLED', 'FULLY_SETTLED']
    ).count()

    total_commitments = total_contracts + total_debts
    if total_commitments >= 3:
        completion_rate = completed / total_contracts if total_contracts > 0 else 1.0
        repayment_rate = repaid / total_debts if total_debts > 0 else 1.0
        reliability = min(Decimal('10'), Decimal(str(
            10 * (0.6 * completion_rate + 0.4 * repayment_rate)
        )))
    else:
        reliability = Decimal('5')  # neutral default

    # --- Total ---
    total = identity + commerce + community + contribution + governance + reliability

    # --- Active dimensions ---
    active = 0
    if identity > 0:
        active += 1
    if commerce > 0:
        active += 1
    if community > 0:
        active += 1
    if contribution > 0:
        active += 1
    if governance > 0:
        active += 1
    if reliability != Decimal('5'):  # 5.0 is neutral = no data
        active += 1

    return {
        'identity': identity.quantize(Decimal('0.0001')),
        'commerce': commerce.quantize(Decimal('0.0001')),
        'community': community.quantize(Decimal('0.0001')),
        'contribution': contribution.quantize(Decimal('0.0001')),
        'governance': governance.quantize(Decimal('0.0001')),
        'reliability': reliability.quantize(Decimal('0.0001')),
        'total': total.quantize(Decimal('0.0001')),
        'active_dimensions': active,
    }
