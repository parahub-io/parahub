"""
Standing delegations for civic opinion polls (Phase 2.5 — PK/civic-polls-system.md § 4.5).

Materialized-row model: when a delegate has voted, each (transitively) delegating
profile gets a pseudonymous OpinionVote row of their own — their token, the
delegate's payload, `via_delegation=True`, the DELEGATOR's municipality (breakdowns
stay geographically truthful). Aggregates remain a plain sum of rows.

`recompute_poll_materialization(poll)` is a full pass and the single source of
truth for delegated rows: correct under any sequence of votes, acceptances,
revocations and own-vote overrides (stale rows are diffed away by token).
"""
import logging
from typing import Dict, List, Optional, Set

from django.db import transaction
from django.utils import timezone

from identity.models import Profile
from .models import Poll, PollContext, OpinionVote, StandingDelegation
from . import civic

logger = logging.getLogger(__name__)

MAX_CHAIN = 10  # matches per-poll delegation chain cap


def _operational_delegations():
    return StandingDelegation.objects.filter(
        is_active=True, accepted_at__isnull=False, revoked_at__isnull=True,
    )


def delegations_for_poll(poll: Poll):
    """Operational delegations whose scope covers this poll: topic match, or a
    territory that is an ancestor-or-self of the poll's territory."""
    territory = civic.get_poll_territory(poll)
    if territory is None:
        return StandingDelegation.objects.none()
    chain_ids = [t.id for t in territory.ancestor_chain()]
    from django.db.models import Q
    q = Q(scope_type=StandingDelegation.ScopeType.TERRITORY, territory_id__in=chain_ids)
    if poll.topic_id:
        q |= Q(scope_type=StandingDelegation.ScopeType.TOPIC, topic_id=poll.topic_id)
    return _operational_delegations().filter(q).select_related('delegator', 'delegate', 'territory')


def _delegation_priority(d: StandingDelegation, territory_depth: Dict[str, int]) -> tuple:
    """Lower sorts first: topic beats territory; deeper territory beats wider."""
    if d.scope_type == StandingDelegation.ScopeType.TOPIC:
        return (0, 0)
    return (1, -territory_depth.get(d.territory_id, 0))


def build_delegation_graph(poll: Poll) -> Dict[str, str]:
    """{delegator_profile_id: delegate_profile_id} — one outgoing edge per delegator,
    picked by priority (topic > deepest territory)."""
    territory = civic.get_poll_territory(poll)
    if territory is None:
        return {}
    depth = {t.id: i for i, t in enumerate(reversed(territory.ancestor_chain()))}
    best: Dict[str, StandingDelegation] = {}
    for d in delegations_for_poll(poll):
        cur = best.get(d.delegator_id)
        if cur is None or _delegation_priority(d, depth) < _delegation_priority(cur, depth):
            best[d.delegator_id] = d
    return {pid: d.delegate_id for pid, d in best.items()}


def resolve_terminal(profile_id: str, graph: Dict[str, str]) -> Optional[str]:
    """Follow the chain to the final delegate; None on cycle or self-loop."""
    visited: Set[str] = set()
    current = profile_id
    hops = 0
    while current in graph:
        if current in visited or hops >= MAX_CHAIN:
            return None
        visited.add(current)
        current = graph[current]
        hops += 1
    return current if current != profile_id else None


def recompute_poll_materialization(poll: Poll, notify: bool = True) -> int:
    """Full materialization pass for one anonymous opinion poll.
    Returns the number of delegated rows created or updated."""
    if (poll.poll_class != Poll.PollClass.OPINION
            or poll.ballot_mode != Poll.BallotMode.ANONYMOUS
            or poll.status != Poll.Status.ACTIVE):
        return 0

    graph = build_delegation_graph(poll)
    expected_tokens: Dict[str, dict] = {}  # token -> {'profile': Profile, 'payload': dict, 'delegate_id': str}
    changed_delegators: List[Profile] = []

    if graph:
        profiles = {p.id: p for p in Profile.objects.filter(id__in=graph.keys()).select_related('account')}
        # Terminal delegates' own ballots (via_delegation=False)
        terminal_ids = {resolve_terminal(pid, graph) for pid in graph}
        terminal_ids.discard(None)
        terminal_rows: Dict[str, dict] = {}
        for tid in terminal_ids:
            row = OpinionVote.objects.filter(
                poll=poll, voter_token=civic.voter_token(tid, poll.id), via_delegation=False,
            ).first()
            if row:
                terminal_rows[tid] = row.payload

        for delegator_id, _ in graph.items():
            terminal = resolve_terminal(delegator_id, graph)
            if terminal is None or terminal not in terminal_rows:
                continue
            profile = profiles.get(delegator_id)
            if profile is None:
                continue
            # The delegator's own gates still apply (scope/consent/WoT/age) — a vote
            # must never materialize for someone who could not cast it themselves
            try:
                territory, chain = civic.check_can_opinion_vote(poll, profile)
            except civic.CivicVoteError:
                continue
            token = civic.voter_token(delegator_id, poll.id)
            expected_tokens[token] = {
                'profile': profile,
                'payload': terminal_rows[terminal],
                'terr': civic.municipality_code(chain),
                'delegate_id': terminal,
            }

    with transaction.atomic():
        Poll.objects.select_for_update().get(id=poll.id)

        # Own votes always win: drop expectations where an own row exists
        if expected_tokens:
            own = set(OpinionVote.objects.filter(
                poll=poll, voter_token__in=list(expected_tokens.keys()), via_delegation=False,
            ).values_list('voter_token', flat=True))
            for token in own:
                expected_tokens.pop(token, None)

        # Delete stale delegated rows (revoked/decayed chains, delegate withdrew)
        stale = OpinionVote.objects.filter(poll=poll, via_delegation=True).exclude(
            voter_token__in=list(expected_tokens.keys()))
        stale.delete()

        # Upsert expected delegated rows
        existing = {
            row.voter_token: row
            for row in OpinionVote.objects.filter(
                poll=poll, via_delegation=True, voter_token__in=list(expected_tokens.keys()))
        }
        for token, spec in expected_tokens.items():
            row = existing.get(token)
            if row is None:
                OpinionVote.objects.create(
                    poll=poll, voter_token=token, payload=spec['payload'],
                    voter_territory=spec['terr'],
                    voter_wot_verified=bool(spec['profile'].is_verified_wot),
                    via_delegation=True,
                )
                changed_delegators.append(spec['profile'])
            elif row.payload != spec['payload']:
                row.payload = spec['payload']
                row.voter_territory = spec['terr']
                row.voter_wot_verified = bool(spec['profile'].is_verified_wot)
                row.save(update_fields=['payload', 'voter_territory', 'voter_wot_verified', 'updated_at'])
                changed_delegators.append(spec['profile'])

    # Aggregates: one rebuild is simpler than tracking every delta through a full pass
    civic.recount_poll(poll)
    n = OpinionVote.objects.filter(poll=poll).count()
    civic._broadcast_results(poll.id, n)

    if notify and changed_delegators:
        _notify_delegated_cast(poll, changed_delegators)
    return len(changed_delegators)


def _notify_delegated_cast(poll: Poll, delegators: List[Profile]):
    """Default-ON notification: «ваш голос использован» — the liquid-democracy
    safety mechanism (A6). Every delegator can override with one tap."""
    try:
        from notifications.services import emit_notification
    except Exception:
        return
    for profile in delegators:
        account = getattr(profile, 'account', None)
        if not account:
            continue
        try:
            emit_notification(
                account,
                type='civic_delegated_vote',
                title=poll.title[:120],
                body='Your delegated voice was cast in this poll. Open to review or override.',
                url=f'/governance/polls/{poll.id}',
                data={'poll_id': poll.id},
            )
        except Exception as e:
            logger.warning(f"delegated-cast notify failed for {profile.id[:8]}: {e}")


def polls_affected_by(delegation: StandingDelegation):
    """Active anonymous opinion polls whose scope matches a delegation."""
    qs = Poll.objects.filter(
        poll_class=Poll.PollClass.OPINION,
        ballot_mode=Poll.BallotMode.ANONYMOUS,
        status=Poll.Status.ACTIVE,
        context__context_type=PollContext.ContextType.TERRITORY,
    ).select_related('context')
    if delegation.scope_type == StandingDelegation.ScopeType.TOPIC:
        return qs.filter(topic_id=delegation.topic_id)
    # Territory scope: polls whose territory chain contains the delegation territory.
    # Subtree membership is cheap to test per poll; active civic polls are a bounded set.
    matched = []
    for poll in qs:
        territory = civic.get_poll_territory(poll)
        if territory and delegation.territory_id in [t.id for t in territory.ancestor_chain()]:
            matched.append(poll.id)
    return Poll.objects.filter(id__in=matched).select_related('context')


def recompute_for_delegation(delegation: StandingDelegation) -> int:
    total = 0
    for poll in polls_affected_by(delegation):
        total += recompute_poll_materialization(poll)
    return total


def viewer_delegation_info(poll: Poll, viewer: Profile) -> Optional[dict]:
    """For the locked-ballot UI: who terminally holds the viewer's voice on this poll."""
    graph = build_delegation_graph(poll)
    if viewer.id not in graph:
        return None
    terminal_id = resolve_terminal(viewer.id, graph)
    if terminal_id is None:
        return None
    terminal = Profile.objects.filter(id=terminal_id).first()
    if terminal is None:
        return None
    row = OpinionVote.objects.filter(
        poll=poll, voter_token=civic.voter_token(viewer.id, poll.id), via_delegation=True,
    ).first()
    return {
        'delegate_id': terminal.id,
        'delegate_hna': terminal.hna,
        'delegate_display_name': terminal.display_name or '',
        'has_cast': row is not None,
        'cast_at': row.updated_at.isoformat() if row else None,
    }
