"""
Civic opinion polls service layer.

Pseudonymous (GDPR Art. 9) territory-scoped opinion voting:
- voter_token = HMAC-SHA256(CIVIC_VOTE_SECRET, profile_ulid + poll_ulid), no profile FK stored
- CQRS: PostgreSQL OpinionVote is the source of truth, Redis holds hot counters
- Timing-deanonymization guard: below CIVIC_LIVE_THRESHOLD only `n` is broadcast/displayed exactly quantized
- Receipts: the audit entry hash is returned to the voter for counted-as-cast verification

See PK/civic-polls-system.md (design: .todo/civic-polls-design.md until graduation).
"""
import hmac
import hashlib
import logging
from collections import defaultdict
from typing import Optional, Tuple

import redis
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from identity.models import Profile
from geo.models import Territory
from .models import Poll, PollContext, PollOption, OpinionVote
from .services import AuditService

logger = logging.getLogger(__name__)

# Redis key layout (all rebuildable from PostgreSQL via recount_poll):
#   civic:{poll}:counts    hash {option_ulid: int}   all voters
#   civic:{poll}:counts_v  hash {option_ulid: int}   WoT-verified voters only
#   civic:{poll}:terr:{code} hash {option_ulid: int} per municipality (DICO)
#   civic:{poll}:terrs     set of municipality codes seen
#   civic:cd:{poll}:{profile} cooldown marker EX 60
#   civic:ws:{poll}        broadcast throttle marker EX 1
REVOTE_COOLDOWN_SECONDS = 60
BREAKDOWN_MIN_N = 5  # k-anonymity threshold for territorial breakdowns


def _redis() -> redis.Redis:
    from parahub.services.ws_publish import _get_pool
    return redis.Redis(connection_pool=_get_pool())


def voter_token(profile_id: str, poll_id: str) -> str:
    """Stable pseudonymous voter key. Server-side only; never expose to clients."""
    secret = settings.CIVIC_VOTE_SECRET
    if not secret:
        raise ImproperlyConfigured("CIVIC_VOTE_SECRET is not set")
    return hmac.new(secret.encode(), f"{profile_id}{poll_id}".encode(), hashlib.sha256).hexdigest()


def residency_chain(profile: Profile):
    """[Territory, ...] from declared residency up to country; falls back to
    profile.country_code when no residency is set. Empty list if neither."""
    if profile.residency_territory_id:
        territory = Territory.objects.select_related(
            'parent', 'parent__parent', 'parent__parent__parent'
        ).filter(id=profile.residency_territory_id).first()
        if territory:
            return territory.ancestor_chain()
    if profile.country_code:
        country = Territory.objects.filter(
            level=Territory.Level.COUNTRY, code=profile.country_code.upper()
        ).first()
        if country:
            return [country]
    return []


def municipality_code(chain) -> str:
    """Voter territory stored on rows, coarsened to municipality (DICO)."""
    for t in chain:
        if t.level == Territory.Level.MUNICIPALITY:
            return t.code
    return ''


def get_poll_territory(poll: Poll) -> Optional[Territory]:
    if poll.context.context_type != PollContext.ContextType.TERRITORY:
        return None
    return Territory.objects.filter(id=poll.context.context_id).first()


class CivicVoteError(Exception):
    def __init__(self, message: str, status: int = 400):
        self.message = message
        self.status = status
        super().__init__(message)


def check_can_opinion_vote(poll: Poll, profile: Profile, territory: Optional[Territory] = None):
    """Raises CivicVoteError on any gate failure. Returns (territory, chain)."""
    if poll.poll_class != Poll.PollClass.OPINION or poll.ballot_mode != Poll.BallotMode.ANONYMOUS:
        raise CivicVoteError("Not an anonymous opinion poll", 400)
    if poll.status != Poll.Status.ACTIVE:
        raise CivicVoteError("Poll is not active", 400)
    if poll.end_time and timezone.now() > poll.end_time:
        raise CivicVoteError("Poll has ended", 400)

    territory = territory or get_poll_territory(poll)
    if territory is None:
        raise CivicVoteError("Poll has no territory scope", 400)

    if not profile.civic_opinion_consent:
        # 422 is the frontend's signal to open the consent screen
        raise CivicVoteError("Civic consent required", 422)

    chain = residency_chain(profile)
    if territory.id not in [t.id for t in chain]:
        raise CivicVoteError("Poll territory is outside your residency scope", 403)

    if poll.require_wot_verified and not (profile.is_verified_wot or profile.is_foundation_member()):
        raise CivicVoteError("WoT verification required for this poll", 403)

    if territory.level == Territory.Level.COUNTRY:
        min_age_days = settings.CIVIC_COUNTRY_MIN_ACCOUNT_AGE_DAYS
        account_created = getattr(profile.account, 'date_joined', None) or profile.created_at
        if (timezone.now() - account_created).days < min_age_days:
            raise CivicVoteError(f"Account must be at least {min_age_days} days old for country-level polls", 403)

    return territory, chain


def cast_opinion_vote(poll: Poll, profile: Profile, option: PollOption) -> dict:
    """Validate, upsert the pseudonymous vote, chain an audit entry, update Redis, broadcast.

    Returns {receipt, my_vote, changed, n}.
    """
    territory, chain = check_can_opinion_vote(poll, profile)

    r = _redis()
    cooldown_key = f"civic:cd:{poll.id}:{profile.id}"
    if not r.set(cooldown_key, 1, ex=REVOTE_COOLDOWN_SECONDS, nx=True):
        raise CivicVoteError("Please wait a minute before changing your vote", 429)

    token = voter_token(profile.id, poll.id)
    terr_code = municipality_code(chain)
    is_verified = bool(profile.is_verified_wot)

    with transaction.atomic():
        # Serialize per-poll so the audit chain's previous_hash stays linear
        Poll.objects.select_for_update().get(id=poll.id)

        existing = OpinionVote.objects.filter(poll=poll, voter_token=token).first()
        old_option = existing.payload.get('option') if existing else None
        old_terr = existing.voter_territory if existing else None
        old_verified = existing.voter_wot_verified if existing else False

        if existing and old_option == option.id:
            # Same choice — nothing to change, still refresh territory snapshot? No: keep row stable.
            return {
                'receipt': None, 'my_vote': option.id, 'changed': False,
                'n': OpinionVote.objects.filter(poll=poll).count(),
            }

        if existing:
            existing.payload = {'option': option.id}
            existing.voter_territory = terr_code
            existing.voter_wot_verified = is_verified
            existing.via_delegation = False  # own vote overrides a materialized delegated row
            existing.save(update_fields=['payload', 'voter_territory', 'voter_wot_verified',
                                         'via_delegation', 'updated_at'])
        else:
            OpinionVote.objects.create(
                poll=poll, voter_token=token, payload={'option': option.id},
                voter_territory=terr_code, voter_wot_verified=is_verified,
            )

        entry = AuditService.create_log_entry(
            poll=poll,
            action='opinion_vote',
            actor=None,
            payload={
                'token_prefix': token[:8],
                'option_id': option.id,
                'revote': bool(existing),
            },
            pgp_signature='',
        )

        n = OpinionVote.objects.filter(poll=poll).count()

        def _after_commit():
            _apply_redis_delta(
                poll_id=poll.id, new_option=option.id, new_terr=terr_code, new_verified=is_verified,
                old_option=old_option, old_terr=old_terr, old_verified=old_verified,
            )
            _broadcast_results(poll.id, n)
            # The voter may be a terminal delegate — fan their ballot out to delegators
            from .civic_delegation import recompute_poll_materialization
            try:
                recompute_poll_materialization(poll)
            except Exception as e:
                logger.warning(f"delegation materialization failed for {poll.id[:8]}: {e}")

        transaction.on_commit(_after_commit)

    return {'receipt': entry.current_log_hash, 'my_vote': option.id, 'changed': bool(old_option), 'n': n}


def _apply_redis_delta(poll_id, new_option, new_terr, new_verified,
                       old_option=None, old_terr=None, old_verified=False):
    try:
        r = _redis()
        pipe = r.pipeline()
        if old_option:
            pipe.hincrby(f"civic:{poll_id}:counts", old_option, -1)
            if old_verified:
                pipe.hincrby(f"civic:{poll_id}:counts_v", old_option, -1)
            if old_terr:
                pipe.hincrby(f"civic:{poll_id}:terr:{old_terr}", old_option, -1)
        pipe.hincrby(f"civic:{poll_id}:counts", new_option, 1)
        if new_verified:
            pipe.hincrby(f"civic:{poll_id}:counts_v", new_option, 1)
        if new_terr:
            pipe.hincrby(f"civic:{poll_id}:terr:{new_terr}", new_option, 1)
            pipe.sadd(f"civic:{poll_id}:terrs", new_terr)
        pipe.execute()
    except Exception as e:  # Redis down: PG is still authoritative; recount heals
        logger.warning(f"civic redis delta failed for poll {poll_id[:8]}: {e}")


def _broadcast_results(poll_id: str, n: int):
    """Throttled (<=1/s per poll). Below the live threshold only `n` is pushed —
    per-option live ticks at small n allow timing deanonymization. Clients of
    hidden-until-vote polls also suppress rendering (soft bias guard, REST enforces)."""
    try:
        r = _redis()
        if not r.set(f"civic:ws:{poll_id}", 1, ex=1, nx=True):
            return  # at high rates the next vote broadcasts within a second
        from parahub.services.ws_publish import ws_publish
        payload = {'type': 'civic.results_updated', 'poll_id': poll_id, 'n': n}
        if n >= settings.CIVIC_LIVE_THRESHOLD:
            counts = r.hgetall(f"civic:{poll_id}:counts")
            counts_v = r.hgetall(f"civic:{poll_id}:counts_v")
            payload['counts'] = {k: int(v) for k, v in counts.items()}
            payload['counts_verified'] = {k: int(v) for k, v in counts_v.items()}
        ws_publish(f"poll:{poll_id}", payload)
    except Exception as e:
        logger.warning(f"civic broadcast failed for poll {poll_id[:8]}: {e}")


def _counts_from_redis_or_recount(poll: Poll) -> Tuple[dict, dict]:
    r = _redis()
    counts = r.hgetall(f"civic:{poll.id}:counts")
    if not counts and OpinionVote.objects.filter(poll=poll).exists():
        recount_poll(poll)
        counts = r.hgetall(f"civic:{poll.id}:counts")
    counts_v = r.hgetall(f"civic:{poll.id}:counts_v")
    return (
        {k: int(v) for k, v in counts.items()},
        {k: int(v) for k, v in counts_v.items()},
    )


def _n_display(n: int) -> str:
    """Quantized participation label for small-n polls."""
    if n >= settings.CIVIC_LIVE_THRESHOLD:
        return str(n)
    if n == 0:
        return "0"
    if n < BREAKDOWN_MIN_N:
        return f"<{BREAKDOWN_MIN_N}"
    return f"{BREAKDOWN_MIN_N}–{settings.CIVIC_LIVE_THRESHOLD - 1}"


def get_opinion_results(poll: Poll, viewer: Optional[Profile]) -> dict:
    """Results with hide-until-vote (U2) and small-n quantization (A1) applied."""
    if poll.poll_type == Poll.PollType.SLIDERS:
        return get_slider_results(poll, viewer)
    ended = poll.status == Poll.Status.ENDED

    if poll.frozen_results:
        frozen = dict(poll.frozen_results)
        frozen.update({'poll_id': poll.id, 'frozen': True, 'ended': True, 'hidden': False, 'my_vote': None})
        return frozen

    my_vote = None
    my_vote_via = False
    delegation_info = None
    in_scope = False
    if viewer:
        token = voter_token(viewer.id, poll.id)
        row = OpinionVote.objects.filter(poll=poll, voter_token=token).first()
        if row:
            my_vote = row.payload.get('option')
            my_vote_via = row.via_delegation
        territory = get_poll_territory(poll)
        if territory:
            in_scope = territory.id in [t.id for t in residency_chain(viewer)]
        if in_scope and poll.status == Poll.Status.ACTIVE:
            from .civic_delegation import viewer_delegation_info
            delegation_info = viewer_delegation_info(poll, viewer)

    counts, counts_v = _counts_from_redis_or_recount(poll)
    n = sum(counts.values())
    n_verified = sum(counts_v.values())

    # U2: eligible-but-not-voted viewers see participation only, not the distribution
    hidden = bool(viewer and in_scope and not my_vote and not ended)

    base = {
        'poll_id': poll.id,
        'n': None if n < settings.CIVIC_LIVE_THRESHOLD else n,
        'n_display': _n_display(n),
        'n_verified': None if n < settings.CIVIC_LIVE_THRESHOLD else n_verified,
        'quantized': n < settings.CIVIC_LIVE_THRESHOLD,
        'hidden': hidden,
        'ended': ended,
        'frozen': False,
        'my_vote': my_vote,
        'my_vote_via': my_vote_via,
        'delegation': delegation_info,
        'options': None,
        'by_territory': None,
    }
    if hidden:
        return base

    options_meta = list(poll.options.all())
    quantized = base['quantized']

    def pct(count, total, step):
        if total <= 0:
            return 0
        raw = count / total * 100
        return int(round(raw / step) * step)

    step = 10 if quantized else 1
    base['options'] = [
        {
            'option_id': o.id,
            'text': o.text,
            'count': None if quantized else counts.get(o.id, 0),
            'percent': pct(counts.get(o.id, 0), n, step),
            'count_verified': None if quantized else counts_v.get(o.id, 0),
            'percent_verified': pct(counts_v.get(o.id, 0), n_verified, step),
        }
        for o in options_meta
    ]

    if not quantized:
        base['by_territory'] = _territory_breakdown(poll)

    return base


def _territory_breakdown(poll: Poll):
    """Per-municipality splits, k>=5 only. Names resolved via Territory (DICO codes)."""
    r = _redis()
    codes = r.smembers(f"civic:{poll.id}:terrs")
    if not codes:
        return []
    territory = get_poll_territory(poll)
    country = territory.country if territory else 'PT'
    names = {
        t.code: t.name
        for t in Territory.objects.filter(
            country=country, level=Territory.Level.MUNICIPALITY, code__in=codes
        )
    }
    out = []
    for code in codes:
        tc = r.hgetall(f"civic:{poll.id}:terr:{code}")
        tc = {k: int(v) for k, v in tc.items()}
        tn = sum(tc.values())
        if tn < BREAKDOWN_MIN_N:
            continue
        out.append({'code': code, 'name': names.get(code, code), 'n': tn, 'counts': tc})
    out.sort(key=lambda x: -x['n'])
    return out


def recount_poll(poll: Poll, verify_only: bool = False) -> dict:
    """Rebuild Redis aggregates from PostgreSQL (source of truth). Returns the PG truth."""
    counts = defaultdict(int)
    counts_v = defaultdict(int)
    terr = defaultdict(lambda: defaultdict(int))
    hist = defaultdict(lambda: defaultdict(int))
    hist_v = defaultdict(lambda: defaultdict(int))
    for payload, territory_code, verified in OpinionVote.objects.filter(poll=poll).values_list(
        'payload', 'voter_territory', 'voter_wot_verified'
    ):
        option = (payload or {}).get('option')
        values = (payload or {}).get('values')
        if option:
            counts[option] += 1
            if verified:
                counts_v[option] += 1
            if territory_code:
                terr[territory_code][option] += 1
        elif values:
            for axis, v in values.items():
                hist[axis][int(v)] += 1
                if verified:
                    hist_v[axis][int(v)] += 1

    truth = {
        'counts': dict(counts),
        'counts_verified': dict(counts_v),
        'by_territory': {code: dict(opts) for code, opts in terr.items()},
        'hist': {a: dict(h) for a, h in hist.items()},
        'hist_verified': {a: dict(h) for a, h in hist_v.items()},
    }
    if verify_only:
        return truth

    r = _redis()
    pipe = r.pipeline()
    old_terrs = r.smembers(f"civic:{poll.id}:terrs")
    for code in old_terrs:
        pipe.delete(f"civic:{poll.id}:terr:{code}")
    pipe.delete(f"civic:{poll.id}:counts", f"civic:{poll.id}:counts_v", f"civic:{poll.id}:terrs")
    for axis_id in poll.options.values_list('id', flat=True):
        pipe.delete(f"civic:{poll.id}:hist:{axis_id}", f"civic:{poll.id}:hist_v:{axis_id}")
    if counts:
        pipe.hset(f"civic:{poll.id}:counts", mapping={k: v for k, v in counts.items()})
    if counts_v:
        pipe.hset(f"civic:{poll.id}:counts_v", mapping={k: v for k, v in counts_v.items()})
    for code, opts in terr.items():
        pipe.hset(f"civic:{poll.id}:terr:{code}", mapping={k: v for k, v in opts.items()})
        pipe.sadd(f"civic:{poll.id}:terrs", code)
    for axis, h in hist.items():
        pipe.hset(f"civic:{poll.id}:hist:{axis}", mapping={str(k): v for k, v in h.items()})
    for axis, h in hist_v.items():
        pipe.hset(f"civic:{poll.id}:hist_v:{axis}", mapping={str(k): v for k, v in h.items()})
    pipe.execute()
    return truth


def erase_civic_data(profile: Profile) -> int:
    """GDPR erasure: delete the profile's pseudonymous votes across all opinion polls,
    chain erasure audit entries, heal aggregates. Returns number of affected polls.

    Standing delegations are revoked in both directions: given ones stop future
    materialization for this profile; received ones stop further disclosure of the
    (now erased) delegate's ballots."""
    from .models import StandingDelegation
    from django.db.models import Q
    delegations = list(StandingDelegation.objects.filter(
        Q(delegator=profile) | Q(delegate=profile), is_active=True))
    if delegations:
        StandingDelegation.objects.filter(id__in=[d.id for d in delegations]).update(
            is_active=False, revoked_at=timezone.now())
        from .civic_delegation import recompute_for_delegation
        for d in delegations:
            try:
                recompute_for_delegation(d)
            except Exception as e:
                logger.warning(f"erasure delegation recompute failed: {e}")

    affected = []
    for poll in Poll.objects.filter(poll_class=Poll.PollClass.OPINION).iterator():
        token = voter_token(profile.id, poll.id)
        with transaction.atomic():
            Poll.objects.select_for_update().get(id=poll.id)
            deleted, _ = OpinionVote.objects.filter(poll=poll, voter_token=token).delete()
            if deleted:
                AuditService.create_log_entry(
                    poll=poll, action='opinion_erased', actor=None,
                    payload={'token_prefix': token[:8]}, pgp_signature='',
                )
                affected.append(poll)
    for poll in affected:
        recount_poll(poll)
        _broadcast_results(poll.id, OpinionVote.objects.filter(poll=poll).count())
    return len(affected)


def freeze_and_purge(poll: Poll) -> bool:
    """30 days after end: persist aggregates into Poll.frozen_results, drop raw rows
    (data minimization). Sub-k municipality rows fold into an 'other' bucket."""
    if poll.status != Poll.Status.ENDED or poll.frozen_results:
        return False
    rows = OpinionVote.objects.filter(poll=poll)
    if not rows.exists():
        return False
    if poll.poll_type == Poll.PollType.SLIDERS:
        return _freeze_and_purge_sliders(poll, rows)

    truth = recount_poll(poll, verify_only=True)
    n = sum(truth['counts'].values())
    n_verified = sum(truth['counts_verified'].values())
    options_meta = {o.id: o.text for o in poll.options.all()}

    by_territory = []
    other = defaultdict(int)
    territory = get_poll_territory(poll)
    country = territory.country if territory else 'PT'
    names = {
        t.code: t.name for t in Territory.objects.filter(
            country=country, level=Territory.Level.MUNICIPALITY,
            code__in=list(truth['by_territory'].keys()),
        )
    }
    for code, opts in truth['by_territory'].items():
        tn = sum(opts.values())
        if tn >= BREAKDOWN_MIN_N:
            by_territory.append({'code': code, 'name': names.get(code, code), 'n': tn, 'counts': opts})
        else:
            for opt, c in opts.items():
                other[opt] += c
    if other:
        by_territory.append({'code': 'other', 'name': 'other', 'n': sum(other.values()), 'counts': dict(other)})

    quantized = n < settings.CIVIC_LIVE_THRESHOLD

    def pct(count, total, step):
        if total <= 0:
            return 0
        return int(round(count / total * 100 / step) * step)

    step = 10 if quantized else 1
    frozen = {
        'n': None if quantized else n,
        'n_display': _n_display(n),
        'n_verified': None if quantized else n_verified,
        'quantized': quantized,
        'options': [
            {
                'option_id': oid,
                'text': text,
                'count': None if quantized else truth['counts'].get(oid, 0),
                'percent': pct(truth['counts'].get(oid, 0), n, step),
                'count_verified': None if quantized else truth['counts_verified'].get(oid, 0),
                'percent_verified': pct(truth['counts_verified'].get(oid, 0), n_verified, step),
            }
            for oid, text in options_meta.items()
        ],
        'by_territory': [] if quantized else by_territory,
        'frozen_at': timezone.now().isoformat(),
    }

    with transaction.atomic():
        Poll.objects.select_for_update().get(id=poll.id)
        poll.frozen_results = frozen
        poll.save(update_fields=['frozen_results'])
        rows.delete()

    r = _redis()
    for code in r.smembers(f"civic:{poll.id}:terrs"):
        r.delete(f"civic:{poll.id}:terr:{code}")
    r.delete(f"civic:{poll.id}:counts", f"civic:{poll.id}:counts_v", f"civic:{poll.id}:terrs")
    logger.info(f"Opinion poll {poll.id[:8]} frozen and purged (n={n})")
    return True


# ---------------------------------------------------------------------------
# Community scopes (household / condominium) — open-ballot opinion polls
# ---------------------------------------------------------------------------

def resolve_context_audience(context_type: str, context_id: str) -> set:
    """Profile IDs allowed to vote in a household/condominium poll."""
    if context_type == PollContext.ContextType.HOUSEHOLD:
        from iot.models import Property, PropertyMember
        prop = Property.objects.filter(id=context_id).first()
        if not prop:
            return set()
        audience = {prop.owner_id}
        audience.update(PropertyMember.objects.filter(property=prop).values_list('profile_id', flat=True))
        return audience
    if context_type in (PollContext.ContextType.CONDOMINIUM, PollContext.ContextType.TSZH):
        from geo.models import CondominiumFraction
        return set(
            CondominiumFraction.objects.filter(establishment_id=context_id, resident__isnull=False)
            .values_list('resident_id', flat=True)
        )
    return set()


def sync_poll_audience(poll: Poll) -> None:
    """Keep PollEligibleVoter in sync with live membership for community polls.

    Adds new members; removes departed members who have not voted (cast votes stay —
    they were legitimate when cast)."""
    from .models import PollEligibleVoter, PollVote
    audience = resolve_context_audience(poll.context.context_type, poll.context.context_id)
    if not audience:
        return
    current = set(PollEligibleVoter.objects.filter(poll=poll).values_list('profile_id', flat=True))
    to_add = audience - current
    to_remove = current - audience
    if to_add:
        PollEligibleVoter.objects.bulk_create(
            [PollEligibleVoter(poll=poll, profile_id=pid) for pid in to_add],
            ignore_conflicts=True,
        )
    if to_remove:
        voted = set(PollVote.objects.filter(poll=poll, voter_id__in=to_remove).values_list('voter_id', flat=True))
        PollEligibleVoter.objects.filter(poll=poll, profile_id__in=(to_remove - voted)).delete()


def sync_context_audience_polls(context_type: str, context_id: str) -> None:
    """Sync all active community polls of a context after membership changes."""
    polls = Poll.objects.filter(
        context__context_type=context_type,
        context__context_id=context_id,
        status=Poll.Status.ACTIVE,
    ).select_related('context')
    for poll in polls:
        sync_poll_audience(poll)


# ---------------------------------------------------------------------------
# Slider polls (Phase 2): status-quo-relative axes, -2..+2 (U3)
# ---------------------------------------------------------------------------
# Redis: civic:{poll}:hist:{option}   hash {"-2".."2": count}  all voters
#        civic:{poll}:hist_v:{option} hash {...}               WoT-verified only
# Values are discrete (5 anchors), so the histogram IS the full distribution —
# medians are exact from Redis, no PG read on the hot path.

SLIDER_MIN, SLIDER_MAX = -2, 2


def validate_slider_values(poll: Poll, values: dict) -> dict:
    """All axes required, each an int in [-2, 2]. Returns {option_id: int}."""
    axis_ids = set(poll.options.values_list('id', flat=True))
    if not axis_ids:
        raise CivicVoteError("Poll has no axes", 400)
    clean = {}
    for key, raw in (values or {}).items():
        if key not in axis_ids:
            raise CivicVoteError(f"Unknown axis {key}", 400)
        if not isinstance(raw, int) or isinstance(raw, bool) or not (SLIDER_MIN <= raw <= SLIDER_MAX):
            raise CivicVoteError("Slider values must be integers in [-2, 2]", 400)
        clean[key] = raw
    if set(clean.keys()) != axis_ids:
        raise CivicVoteError("All axes must be answered", 400)
    return clean


def cast_slider_vote(poll: Poll, profile: Profile, values: dict) -> dict:
    """Slider-poll counterpart of cast_opinion_vote: same gates, pseudonymous upsert,
    audit receipt, Redis histogram deltas, throttled broadcast."""
    if poll.poll_type != Poll.PollType.SLIDERS:
        raise CivicVoteError("Not a slider poll", 400)
    territory, chain = check_can_opinion_vote(poll, profile)
    clean = validate_slider_values(poll, values)

    r = _redis()
    cooldown_key = f"civic:cd:{poll.id}:{profile.id}"
    if not r.set(cooldown_key, 1, ex=REVOTE_COOLDOWN_SECONDS, nx=True):
        raise CivicVoteError("Please wait a minute before changing your vote", 429)

    token = voter_token(profile.id, poll.id)
    terr_code = municipality_code(chain)
    is_verified = bool(profile.is_verified_wot)

    with transaction.atomic():
        Poll.objects.select_for_update().get(id=poll.id)

        existing = OpinionVote.objects.filter(poll=poll, voter_token=token).first()
        old_values = (existing.payload.get('values') or {}) if existing else None
        old_verified = existing.voter_wot_verified if existing else False

        if existing and old_values == clean:
            return {
                'receipt': None, 'my_values': clean, 'changed': False,
                'n': OpinionVote.objects.filter(poll=poll).count(),
            }

        if existing:
            existing.payload = {'values': clean}
            existing.voter_territory = terr_code
            existing.voter_wot_verified = is_verified
            existing.via_delegation = False  # own vote overrides a materialized delegated row
            existing.save(update_fields=['payload', 'voter_territory', 'voter_wot_verified',
                                         'via_delegation', 'updated_at'])
        else:
            OpinionVote.objects.create(
                poll=poll, voter_token=token, payload={'values': clean},
                voter_territory=terr_code, voter_wot_verified=is_verified,
            )

        entry = AuditService.create_log_entry(
            poll=poll, action='opinion_vote', actor=None,
            payload={'token_prefix': token[:8], 'values': clean, 'revote': bool(existing)},
            pgp_signature='',
        )

        n = OpinionVote.objects.filter(poll=poll).count()

        def _after_commit():
            _apply_slider_delta(poll.id, clean, is_verified, old_values, old_verified)
            _broadcast_results(poll.id, n)
            from .civic_delegation import recompute_poll_materialization
            try:
                recompute_poll_materialization(poll)
            except Exception as e:
                logger.warning(f"delegation materialization failed for {poll.id[:8]}: {e}")

        transaction.on_commit(_after_commit)

    return {'receipt': entry.current_log_hash, 'my_values': clean, 'changed': old_values is not None, 'n': n}


def _apply_slider_delta(poll_id, new_values, new_verified, old_values=None, old_verified=False):
    try:
        r = _redis()
        pipe = r.pipeline()
        for axis, v in (old_values or {}).items():
            pipe.hincrby(f"civic:{poll_id}:hist:{axis}", str(v), -1)
            if old_verified:
                pipe.hincrby(f"civic:{poll_id}:hist_v:{axis}", str(v), -1)
        for axis, v in new_values.items():
            pipe.hincrby(f"civic:{poll_id}:hist:{axis}", str(v), 1)
            if new_verified:
                pipe.hincrby(f"civic:{poll_id}:hist_v:{axis}", str(v), 1)
        pipe.execute()
    except Exception as e:
        logger.warning(f"civic slider delta failed for poll {poll_id[:8]}: {e}")


def _median_from_hist(hist: dict) -> Optional[float]:
    """Exact median over the discrete -2..2 distribution {value:int count}."""
    total = sum(hist.values())
    if total == 0:
        return None
    lo_pos = (total + 1) // 2
    hi_pos = total // 2 + 1
    cumulative = 0
    lo_val = hi_val = None
    for v in range(SLIDER_MIN, SLIDER_MAX + 1):
        cumulative += hist.get(v, 0)
        if lo_val is None and cumulative >= lo_pos:
            lo_val = v
        if hi_val is None and cumulative >= hi_pos:
            hi_val = v
            break
    return (lo_val + hi_val) / 2


def _slider_hists(poll: Poll) -> Tuple[dict, dict]:
    """{axis_id: {int value: count}} for all + verified, from Redis with lazy heal."""
    r = _redis()
    axis_ids = list(poll.options.values_list('id', flat=True))
    hists = {a: {int(k): int(v) for k, v in r.hgetall(f"civic:{poll.id}:hist:{a}").items()} for a in axis_ids}
    if not any(sum(h.values()) for h in hists.values()) and OpinionVote.objects.filter(poll=poll).exists():
        recount_poll(poll)
        hists = {a: {int(k): int(v) for k, v in r.hgetall(f"civic:{poll.id}:hist:{a}").items()} for a in axis_ids}
    hists_v = {a: {int(k): int(v) for k, v in r.hgetall(f"civic:{poll.id}:hist_v:{a}").items()} for a in axis_ids}
    return hists, hists_v


def get_slider_results(poll: Poll, viewer: Optional[Profile]) -> dict:
    """Slider counterpart of get_opinion_results: hide-until-vote + quantization apply."""
    ended = poll.status == Poll.Status.ENDED
    if poll.frozen_results:
        frozen = dict(poll.frozen_results)
        frozen.update({'poll_id': poll.id, 'frozen': True, 'ended': True, 'hidden': False, 'my_values': None})
        return frozen

    my_values = None
    my_vote_via = False
    delegation_info = None
    in_scope = False
    if viewer:
        token = voter_token(viewer.id, poll.id)
        row = OpinionVote.objects.filter(poll=poll, voter_token=token).first()
        if row:
            my_values = row.payload.get('values')
            my_vote_via = row.via_delegation
        territory = get_poll_territory(poll)
        if territory:
            in_scope = territory.id in [t.id for t in residency_chain(viewer)]
        if in_scope and poll.status == Poll.Status.ACTIVE:
            from .civic_delegation import viewer_delegation_info
            delegation_info = viewer_delegation_info(poll, viewer)

    hists, hists_v = _slider_hists(poll)
    axis_meta = list(poll.options.all())
    n = sum(hists.get(axis_meta[0].id, {}).values()) if axis_meta else 0
    n_verified = sum(hists_v.get(axis_meta[0].id, {}).values()) if axis_meta else 0

    hidden = bool(viewer and in_scope and not my_values and not ended)
    quantized = n < settings.CIVIC_LIVE_THRESHOLD

    base = {
        'poll_id': poll.id,
        'poll_type': 'sliders',
        'n': None if quantized else n,
        'n_display': _n_display(n),
        'n_verified': None if quantized else n_verified,
        'quantized': quantized,
        'hidden': hidden,
        'ended': ended,
        'frozen': False,
        'my_values': my_values,
        'my_vote_via': my_vote_via,
        'delegation': delegation_info,
        'axes': None,
        'by_territory': None,
        'options': None,
    }
    if hidden:
        return base

    def dist(hist, total, step):
        if total <= 0:
            return {str(v): 0 for v in range(SLIDER_MIN, SLIDER_MAX + 1)}
        return {
            str(v): int(round(hist.get(v, 0) / total * 100 / step) * step)
            for v in range(SLIDER_MIN, SLIDER_MAX + 1)
        }

    step = 10 if quantized else 1
    base['axes'] = [
        {
            'option_id': a.id,
            'text': a.text,
            'median': _median_from_hist(hists.get(a.id, {})),
            'median_verified': _median_from_hist(hists_v.get(a.id, {})),
            # Distribution as percents (counts hidden when quantized — A1)
            'distribution_pct': dist(hists.get(a.id, {}), n, step),
            'distribution': None if quantized else {str(v): hists.get(a.id, {}).get(v, 0)
                                                    for v in range(SLIDER_MIN, SLIDER_MAX + 1)},
        }
        for a in axis_meta
    ]
    return base


def _freeze_and_purge_sliders(poll: Poll, rows) -> bool:
    """Slider counterpart of freeze_and_purge: medians + distributions into frozen_results."""
    truth = recount_poll(poll, verify_only=True)
    axis_meta = list(poll.options.all())
    hist = {a: {int(k): v for k, v in truth['hist'].get(a, {}).items()} for a in truth['hist']}
    hist_v = {a: {int(k): v for k, v in truth['hist_verified'].get(a, {}).items()} for a in truth['hist_verified']}
    n = sum(hist.get(axis_meta[0].id, {}).values()) if axis_meta else 0
    n_verified = sum(hist_v.get(axis_meta[0].id, {}).values()) if axis_meta else 0
    quantized = n < settings.CIVIC_LIVE_THRESHOLD

    def dist_pct(h, total, step):
        if total <= 0:
            return {str(v): 0 for v in range(SLIDER_MIN, SLIDER_MAX + 1)}
        return {str(v): int(round(h.get(v, 0) / total * 100 / step) * step)
                for v in range(SLIDER_MIN, SLIDER_MAX + 1)}

    step = 10 if quantized else 1
    frozen = {
        'poll_type': 'sliders',
        'n': None if quantized else n,
        'n_display': _n_display(n),
        'n_verified': None if quantized else n_verified,
        'quantized': quantized,
        'axes': [
            {
                'option_id': a.id,
                'text': a.text,
                'median': _median_from_hist(hist.get(a.id, {})),
                'median_verified': _median_from_hist(hist_v.get(a.id, {})),
                'distribution_pct': dist_pct(hist.get(a.id, {}), n, step),
                'distribution': None if quantized else {str(v): hist.get(a.id, {}).get(v, 0)
                                                        for v in range(SLIDER_MIN, SLIDER_MAX + 1)},
            }
            for a in axis_meta
        ],
        'options': None,
        'by_territory': None,
        'frozen_at': timezone.now().isoformat(),
    }

    with transaction.atomic():
        Poll.objects.select_for_update().get(id=poll.id)
        poll.frozen_results = frozen
        poll.save(update_fields=['frozen_results'])
        rows.delete()

    r = _redis()
    for a in axis_meta:
        r.delete(f"civic:{poll.id}:hist:{a.id}", f"civic:{poll.id}:hist_v:{a.id}")
    logger.info(f"Slider poll {poll.id[:8]} frozen and purged (n={n})")
    return True
