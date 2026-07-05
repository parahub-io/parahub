"""
Civic polls API: consent, residency, pseudonymous opinion voting, feed.

Mounted at /api/v1/governance/civic/ (+ opinion endpoints under /polls/{id}/).
See PK/civic-polls-system.md.
"""
import logging
from datetime import timedelta
from typing import List, Optional, Dict

from ninja import Router
from ninja.errors import HttpError
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from pydantic import BaseModel, Field

from parahub.auth import ProfileAuth, OptionalProfileAuth
from parahub.ratelimit import ratelimit
from geo.models import Territory
from .models import Poll, PollContext, PollOption, OpinionVote
from . import civic

logger = logging.getLogger(__name__)

civic_router = Router()


# ============================================================================
# Schemas
# ============================================================================

class TerritoryBriefSchema(BaseModel):
    id: str
    level: str
    country: str
    code: str
    name: str


class ConsentRequest(BaseModel):
    granted: bool


class ResidencyRequest(BaseModel):
    territory_id: Optional[str] = Field(None, min_length=26, max_length=26)


class OpinionVoteRequest(BaseModel):
    option_id: Optional[str] = Field(None, min_length=26, max_length=26)  # choice polls
    values: Optional[Dict[str, int]] = None  # slider polls: {axis_ulid: -2..2}


class CivicFeedItemSchema(BaseModel):
    id: str
    object_type: str = "poll"
    title: str
    description: str
    status: str
    poll_class: str
    ballot_mode: str
    scope_level: str  # country|region|municipality|parish|group
    scope_name: str = ''
    territory_id: Optional[str] = None
    civic_destination: str = ''
    civic_outcome: str = ''
    end_time: Optional[str] = None
    created_at: str
    n_display: str = '0'
    has_voted: bool = False
    comments_enabled: bool = False


# ============================================================================
# Consent & residency
# ============================================================================

@civic_router.post("/consent/", auth=ProfileAuth())
@ratelimit(group='civic:consent', key='user', rate='10/m')
def set_civic_consent(request, data: ConsentRequest):
    """Grant or revoke GDPR Art. 9 consent. Revoking erases all opinion votes."""
    profile = request.auth_profile
    if data.granted:
        profile.civic_opinion_consent = True
        profile.civic_opinion_consent_at = timezone.now()
        profile.save(update_fields=['civic_opinion_consent', 'civic_opinion_consent_at'])
        return {'consent': True, 'consent_at': profile.civic_opinion_consent_at.isoformat()}

    erased = civic.erase_civic_data(profile)
    profile.civic_opinion_consent = False
    profile.civic_opinion_consent_at = None
    profile.save(update_fields=['civic_opinion_consent', 'civic_opinion_consent_at'])
    logger.info(f"Civic consent revoked by {profile.id[:8]}, erased votes in {erased} polls")
    return {'consent': False, 'erased_polls': erased}


@civic_router.get("/residency/", auth=ProfileAuth())
def get_residency(request):
    profile = request.auth_profile
    chain = civic.residency_chain(profile)
    cooldown_until = None
    if profile.residency_changed_at:
        until = profile.residency_changed_at + timedelta(days=settings.CIVIC_RESIDENCY_COOLDOWN_DAYS)
        if until > timezone.now():
            cooldown_until = until.isoformat()
    return {
        'territory_id': profile.residency_territory_id,
        'chain': [TerritoryBriefSchema(
            id=t.id, level=t.level, country=t.country, code=t.code, name=t.name
        ).dict() for t in chain],
        'consent': profile.civic_opinion_consent,
        'consent_at': profile.civic_opinion_consent_at.isoformat() if profile.civic_opinion_consent_at else None,
        'cooldown_until': cooldown_until,
    }


@civic_router.put("/residency/", auth=ProfileAuth())
@ratelimit(group='civic:residency', key='user', rate='10/m')
def set_residency(request, data: ResidencyRequest):
    """Set declared residency. First set is free; changes respect a 30-day cooldown
    (poll-shopping guard). Existing votes never migrate territories."""
    profile = request.auth_profile

    if data.territory_id is None:
        profile.residency_territory = None
        profile.save(update_fields=['residency_territory'])
        return get_residency(request)

    territory = get_object_or_404(Territory, id=data.territory_id, is_active=True)

    changing = (profile.residency_territory_id
                and profile.residency_territory_id != territory.id)
    if changing and profile.residency_changed_at:
        until = profile.residency_changed_at + timedelta(days=settings.CIVIC_RESIDENCY_COOLDOWN_DAYS)
        if until > timezone.now():
            raise HttpError(429, f"Residency can be changed again after {until.date().isoformat()}")

    profile.residency_territory = territory
    if changing or not profile.residency_changed_at:
        profile.residency_changed_at = timezone.now()
    # Keep the legacy country field in sync with the chain root
    root = territory.ancestor_chain()[-1]
    if root.level == Territory.Level.COUNTRY:
        profile.country_code = root.code
    profile.save(update_fields=['residency_territory', 'residency_changed_at', 'country_code'])
    return get_residency(request)


# ============================================================================
# Opinion voting
# ============================================================================

@civic_router.post("/polls/{poll_id}/opinion-vote/", auth=ProfileAuth())
@ratelimit(group='civic:vote', key='user', rate='20/m')
def cast_opinion_vote(request, poll_id: str, data: OpinionVoteRequest):
    profile = request.auth_profile
    poll = get_object_or_404(Poll.objects.select_related('context'), id=poll_id)

    try:
        if poll.poll_type == Poll.PollType.SLIDERS:
            if not data.values:
                raise HttpError(400, "Slider polls expect `values`")
            result = civic.cast_slider_vote(poll, profile, data.values)
        else:
            if not data.option_id:
                raise HttpError(400, "Choice polls expect `option_id`")
            try:
                option = PollOption.objects.get(id=data.option_id, poll=poll)
            except PollOption.DoesNotExist:
                raise HttpError(400, "Invalid option")
            result = civic.cast_opinion_vote(poll, profile, option)
    except civic.CivicVoteError as e:
        raise HttpError(e.status, e.message)

    results = civic.get_opinion_results(poll, profile)
    return {**result, 'results': results}


@civic_router.get("/polls/{poll_id}/opinion-results/", auth=OptionalProfileAuth())
@ratelimit(group='civic:results', key='ip', rate='60/m')
def get_opinion_results(request, poll_id: str):
    poll = get_object_or_404(Poll.objects.select_related('context').prefetch_related('options'), id=poll_id)
    if poll.poll_class != Poll.PollClass.OPINION:
        raise HttpError(400, "Not an opinion poll")
    viewer = getattr(request, 'auth_profile', None)
    return civic.get_opinion_results(poll, viewer)


@civic_router.get("/polls/{poll_id}/verify-receipt/", auth=None)
@ratelimit(group='civic:receipt', key='ip', rate='30/m')
def verify_receipt(request, poll_id: str, hash: str):
    """Counted-as-cast check: is this receipt hash present in the poll's audit chain,
    and does the chain verify end to end."""
    from .models import PollAuditLog
    from .services import AuditService
    poll = get_object_or_404(Poll, id=poll_id)
    entry = PollAuditLog.objects.filter(poll=poll, current_log_hash=hash).first()
    chain_valid, chain_error = AuditService.verify_merkle_chain(poll)
    return {
        'included': entry is not None,
        'action': entry.action if entry else None,
        'timestamp': entry.timestamp.isoformat() if entry else None,
        'chain_valid': chain_valid,
        'chain_error': chain_error,
        'merkle_root': poll.merkle_root or None,
    }


# ============================================================================
# Feed
# ============================================================================

# Scope levels where comments are enabled (U4: local only in MVP)
COMMENTABLE_LEVELS = {'municipality', 'parish'}


@civic_router.get("/feed/", response=List[CivicFeedItemSchema], auth=OptionalProfileAuth())
@ratelimit(group='civic:feed', key='ip', rate='60/m')
def civic_feed(request, scope: Optional[str] = None, country: Optional[str] = None,
               page: int = 1, page_size: int = 20):
    """Merged civic feed: territory opinion polls in the viewer's residency chain.

    Anonymous viewers get country-level polls (?country=XX or none). Group polls
    stay on the existing /governance/polls/ listing and merge client-side.
    """
    profile = getattr(request, 'auth_profile', None)
    page_size = min(max(page_size, 1), 50)

    chain = []
    if profile:
        chain = civic.residency_chain(profile)
    elif country:
        c = Territory.objects.filter(level=Territory.Level.COUNTRY, code=country.upper()).first()
        if c:
            chain = [c]

    territory_levels = {'parish', 'municipality', 'region', 'country'}
    community_levels = {'household', 'condominium'}
    if scope and scope != 'all':
        if scope in territory_levels:
            chain = [t for t in chain if t.level == scope]
        else:
            chain = []

    from django.db.models import Case, When, Value, IntegerField, Q, Count

    chain_by_id = {t.id: t for t in chain}
    q_scope = Q(pk__in=[])  # empty
    if chain_by_id:
        q_scope |= Q(context__context_type=PollContext.ContextType.TERRITORY,
                     context__context_id__in=list(chain_by_id.keys()))
    if profile and (not scope or scope == 'all' or scope in community_levels):
        # Household/condominium polls where the viewer is in the audience
        community_types = [PollContext.ContextType.HOUSEHOLD, PollContext.ContextType.CONDOMINIUM]
        if scope in community_levels:
            community_types = [scope]
        q_scope |= Q(context__context_type__in=community_types, eligible_voters__profile=profile)

    qs = (
        Poll.objects.filter(
            q_scope,
            poll_class=Poll.PollClass.OPINION,
            status__in=[Poll.Status.ACTIVE, Poll.Status.ENDED],
        )
        .select_related('context')
        .distinct()
        .annotate(active_rank=Case(
            When(status=Poll.Status.ACTIVE, then=Value(0)),
            default=Value(1), output_field=IntegerField(),
        ))
        .order_by('active_rank', '-created_at')
    )
    polls = list(qs[(page - 1) * page_size: page * page_size])
    if not polls:
        return []

    territory_polls = [p for p in polls if p.context.context_type == PollContext.ContextType.TERRITORY]
    community_polls = [p for p in polls if p.context.context_type != PollContext.ContextType.TERRITORY]

    # Voted flags — anonymous polls via token, open polls via PollVote
    voted_ids = set()
    if profile and territory_polls:
        q = Q(pk__in=[])
        for p in territory_polls:
            q |= Q(poll_id=p.id, voter_token=civic.voter_token(profile.id, p.id))
        voted_ids = set(OpinionVote.objects.filter(q).values_list('poll_id', flat=True))
    if profile and community_polls:
        from .models import PollVote
        voted_ids |= set(PollVote.objects.filter(
            poll__in=community_polls, voter=profile).values_list('poll_id', flat=True))

    # Participation counts
    n_by_poll = dict(
        OpinionVote.objects.filter(poll__in=territory_polls)
        .values_list('poll_id').annotate(c=Count('id')).values_list('poll_id', 'c')
    ) if territory_polls else {}
    if community_polls:
        from .models import PollVote
        n_by_poll.update(dict(
            PollVote.objects.filter(poll__in=community_polls)
            .values_list('poll_id').annotate(c=Count('id')).values_list('poll_id', 'c')
        ))

    # Community scope names
    household_ids = [p.context.context_id for p in community_polls
                     if p.context.context_type == PollContext.ContextType.HOUSEHOLD]
    condo_ids = [p.context.context_id for p in community_polls
                 if p.context.context_type == PollContext.ContextType.CONDOMINIUM]
    names: Dict[str, str] = {}
    if household_ids:
        from iot.models import Property
        names.update({pid: name for pid, name in
                      Property.objects.filter(id__in=household_ids).values_list('id', 'name')})
    if condo_ids:
        from geo.models import Establishment
        names.update({eid: name for eid, name in
                      Establishment.objects.filter(id__in=condo_ids).values_list('id', 'name')})

    items = []
    for p in polls:
        n = n_by_poll.get(p.id, 0)
        if p.context.context_type == PollContext.ContextType.TERRITORY:
            territory = chain_by_id.get(p.context.context_id)
            items.append(CivicFeedItemSchema(
                id=p.id, title=p.title, description=p.description, status=p.status,
                poll_class=p.poll_class, ballot_mode=p.ballot_mode,
                scope_level=territory.level if territory else 'country',
                scope_name=territory.name if territory else '',
                territory_id=territory.id if territory else None,
                civic_destination=p.civic_destination, civic_outcome=p.civic_outcome,
                end_time=p.end_time.isoformat() if p.end_time else None,
                created_at=p.created_at.isoformat(),
                n_display=civic._n_display(n),
                has_voted=p.id in voted_ids,
                comments_enabled=(territory.level in COMMENTABLE_LEVELS) if territory else False,
            ))
        else:
            items.append(CivicFeedItemSchema(
                id=p.id, title=p.title, description=p.description, status=p.status,
                poll_class=p.poll_class, ballot_mode=p.ballot_mode,
                scope_level=p.context.context_type,
                scope_name=names.get(p.context.context_id, ''),
                territory_id=None,
                civic_destination=p.civic_destination, civic_outcome=p.civic_outcome,
                end_time=p.end_time.isoformat() if p.end_time else None,
                created_at=p.created_at.isoformat(),
                n_display=str(n),  # open ballots: exact counts, identified anyway
                has_voted=p.id in voted_ids,
                comments_enabled=True,  # local by definition
            ))
    return items


@civic_router.get("/polls/{poll_id}/open-ballots/", auth=ProfileAuth())
@ratelimit(group='civic:open_ballots', key='user', rate='60/m')
def open_ballots(request, poll_id: str):
    """Per-voter list for open-ballot opinion polls (household/condominium):
    «кто за что и когда». Audience-only — never the public web."""
    from .models import PollVote, PollEligibleVoter
    profile = request.auth_profile
    poll = get_object_or_404(Poll.objects.select_related('context'), id=poll_id)
    if poll.poll_class != Poll.PollClass.OPINION or poll.ballot_mode != Poll.BallotMode.OPEN:
        raise HttpError(400, "Not an open-ballot opinion poll")
    is_audience = (
        poll.created_by_id == profile.id
        or PollEligibleVoter.objects.filter(poll=poll, profile=profile).exists()
    )
    if not is_audience:
        raise HttpError(403, "Audience only")
    votes = PollVote.objects.filter(poll=poll).select_related('voter', 'option').order_by('created_at')
    return [
        {
            'voter_id': v.voter.id,
            'hna': v.voter.hna,
            'display_name': v.voter.display_name or '',
            'option_id': v.option.id,
            'option_text': v.option.text,
            'created_at': v.created_at.isoformat(),
            'on_behalf_count': len(v.voted_on_behalf_of or []),
        }
        for v in votes
    ]


# ============================================================================
# Standing delegations (Phase 2.5)
# ============================================================================

class StandingDelegationCreateRequest(BaseModel):
    delegate_id: str = Field(..., min_length=26, max_length=26)
    scope_type: str = Field(..., pattern="^(topic|territory)$")
    topic_slug: Optional[str] = None
    territory_id: Optional[str] = Field(None, min_length=26, max_length=26)
    pgp_signature: str = ''
    signed_timestamp: str = ''


def _delegation_out(d, viewer_id: str) -> dict:
    return {
        'id': d.id,
        'direction': 'given' if d.delegator_id == viewer_id else 'received',
        'delegator_id': d.delegator_id,
        'delegator_hna': d.delegator.hna,
        'delegator_display_name': d.delegator.display_name or '',
        'delegate_id': d.delegate_id,
        'delegate_hna': d.delegate.hna,
        'delegate_display_name': d.delegate.display_name or '',
        'scope_type': d.scope_type,
        'topic_slug': d.topic.slug if d.topic_id else None,
        'topic_name': d.topic.name if d.topic_id else None,
        'territory_id': d.territory_id,
        'territory_name': d.territory.name if d.territory_id else None,
        'territory_level': d.territory.level if d.territory_id else None,
        'accepted_at': d.accepted_at.isoformat() if d.accepted_at else None,
        'created_at': d.created_at.isoformat(),
        'operational': d.is_operational,
    }


@civic_router.get("/topics/", auth=None)
@ratelimit(group='civic:topics', key='ip', rate='60/m')
def list_civic_topics(request):
    """Curated civic topic list for polls and standing delegations."""
    from taxonomy.models import Category
    root = Category.objects.filter(slug='civic-topics').first()
    if not root:
        return []
    return [
        {'slug': c.slug, 'name': c.name, 'name_i18n': c.name_i18n, 'icon': c.icon}
        for c in root.children.filter(is_active=True).order_by('order', 'slug')
    ]


@civic_router.get("/delegations/", auth=ProfileAuth())
@ratelimit(group='civic:delegations', key='user', rate='30/m')
def list_standing_delegations(request):
    from django.db.models import Q
    from .models import StandingDelegation
    profile = request.auth_profile
    qs = (StandingDelegation.objects
          .filter(Q(delegator=profile) | Q(delegate=profile), is_active=True)
          .select_related('delegator', 'delegate', 'topic', 'territory')
          .order_by('-created_at'))
    given, received_pending, received_active = [], [], []
    for d in qs:
        out = _delegation_out(d, profile.id)
        if d.delegator_id == profile.id:
            given.append(out)
        elif d.accepted_at is None:
            received_pending.append(out)
        else:
            received_active.append(out)

    # Dashboard (A6): where is my voice currently cast via delegation
    from .models import Poll, OpinionVote
    active_polls = list(Poll.objects.filter(
        poll_class=Poll.PollClass.OPINION, ballot_mode=Poll.BallotMode.ANONYMOUS,
        status=Poll.Status.ACTIVE,
    ).values_list('id', flat=True))
    voice_used = 0
    if active_polls:
        q = Q(pk__in=[])
        for pid in active_polls:
            q |= Q(poll_id=pid, voter_token=civic.voter_token(profile.id, pid), via_delegation=True)
        voice_used = OpinionVote.objects.filter(q).count()

    return {
        'given': given,
        'received_pending': received_pending,
        'received_active': received_active,
        'voice_used_in_polls': voice_used,
    }


@civic_router.post("/delegations/", auth=ProfileAuth())
@ratelimit(group='civic:delegation_create', key='user', rate='10/m')
def create_standing_delegation(request, data: StandingDelegationCreateRequest):
    from parahub.crypto.pgp import verify_profile_signature
    from taxonomy.models import Category
    from identity.models import Profile as ProfileModel
    from .models import StandingDelegation

    profile = request.auth_profile
    if not profile.civic_opinion_consent:
        raise HttpError(422, "Civic consent required")
    if data.delegate_id == profile.id:
        raise HttpError(400, "Cannot delegate to yourself")
    delegate = ProfileModel.objects.filter(id=data.delegate_id).first()
    if delegate is None:
        raise HttpError(404, "Delegate not found")

    topic = None
    territory = None
    if data.scope_type == 'topic':
        if not data.topic_slug:
            raise HttpError(400, "topic_slug required")
        topic = Category.objects.filter(slug=data.topic_slug, is_active=True,
                                        parent__slug='civic-topics').first()
        if topic is None:
            raise HttpError(404, "Unknown civic topic")
    else:
        if not data.territory_id:
            raise HttpError(400, "territory_id required")
        territory = Territory.objects.filter(id=data.territory_id, is_active=True).first()
        if territory is None:
            raise HttpError(404, "Territory not found")

    verify_profile_signature(
        profile,
        {
            'action': 'standing_delegation',
            'delegate_id': data.delegate_id,
            'scope_type': data.scope_type,
            'scope': data.topic_slug or data.territory_id,
            'timestamp': data.signed_timestamp,
        },
        data.pgp_signature,
        data.signed_timestamp,
        error_prefix="Standing delegation PGP",
    )

    existing = StandingDelegation.objects.filter(
        delegator=profile, scope_type=data.scope_type,
        topic=topic, territory=territory, is_active=True,
    ).first()
    if existing:
        raise HttpError(400, "An active delegation for this scope already exists — revoke it first")

    d = StandingDelegation.objects.create(
        delegator=profile, delegate=delegate,
        scope_type=data.scope_type, topic=topic, territory=territory,
        pgp_signature=data.pgp_signature,
        signed_payload={
            'delegate_id': data.delegate_id, 'scope_type': data.scope_type,
            'scope': data.topic_slug or data.territory_id,
            'timestamp': data.signed_timestamp,
        },
    )

    try:
        from notifications.services import emit_notification
        if delegate.account:
            emit_notification(
                delegate.account,
                type='civic_delegation_request',
                title='Delegation request',
                body=f'{profile.display_name or profile.hna} wants to delegate their civic voice to you.',
                url='/governance/delegations',
                data={'delegation_id': d.id},
            )
    except Exception as e:
        logger.warning(f"delegation request notify failed: {e}")

    return _delegation_out(
        StandingDelegation.objects.select_related('delegator', 'delegate', 'topic', 'territory').get(id=d.id),
        profile.id,
    )


def _get_own_delegation(profile, delegation_id, as_delegate=False):
    from .models import StandingDelegation
    d = (StandingDelegation.objects
         .select_related('delegator', 'delegate', 'topic', 'territory')
         .filter(id=delegation_id, is_active=True).first())
    if d is None:
        raise HttpError(404, "Delegation not found")
    if as_delegate and d.delegate_id != profile.id:
        raise HttpError(403, "Not the delegate")
    if not as_delegate and profile.id not in (d.delegator_id, d.delegate_id):
        raise HttpError(403, "Not a party of this delegation")
    return d


@civic_router.post("/delegations/{delegation_id}/accept/", auth=ProfileAuth())
@ratelimit(group='civic:delegation_accept', key='user', rate='20/m')
def accept_standing_delegation(request, delegation_id: str):
    """Accepting doubles as the delegate's Art. 9(2)(a) consent: their ballots in
    this scope become visible to the delegator (locked-ballot UI)."""
    profile = request.auth_profile
    if not profile.civic_opinion_consent:
        raise HttpError(422, "Civic consent required")
    d = _get_own_delegation(profile, delegation_id, as_delegate=True)
    if d.accepted_at is None:
        d.accepted_at = timezone.now()
        d.save(update_fields=['accepted_at'])
        from .civic_delegation import recompute_for_delegation
        recompute_for_delegation(d)
        try:
            from notifications.services import emit_notification
            if d.delegator.account:
                emit_notification(
                    d.delegator.account,
                    type='civic_delegation_accepted',
                    title='Delegation accepted',
                    body=f'{profile.display_name or profile.hna} accepted your civic delegation.',
                    url='/governance/delegations',
                    data={'delegation_id': d.id},
                )
        except Exception:
            pass
    return _delegation_out(d, profile.id)


@civic_router.post("/delegations/{delegation_id}/decline/", auth=ProfileAuth())
@ratelimit(group='civic:delegation_decline', key='user', rate='20/m')
def decline_standing_delegation(request, delegation_id: str):
    profile = request.auth_profile
    d = _get_own_delegation(profile, delegation_id, as_delegate=True)
    d.declined_at = timezone.now()
    d.is_active = False
    d.save(update_fields=['declined_at', 'is_active'])
    return {'declined': True}


@civic_router.post("/delegations/{delegation_id}/revoke/", auth=ProfileAuth())
@ratelimit(group='civic:delegation_revoke', key='user', rate='20/m')
def revoke_standing_delegation(request, delegation_id: str):
    """Either party can revoke. Materialized rows melt away on recompute."""
    profile = request.auth_profile
    d = _get_own_delegation(profile, delegation_id)
    was_operational = d.is_operational
    d.revoked_at = timezone.now()
    d.is_active = False
    d.save(update_fields=['revoked_at', 'is_active'])
    if was_operational:
        from .civic_delegation import recompute_for_delegation
        recompute_for_delegation(d)
    return {'revoked': True}


# ============================================================================
# Ideas pipeline (Phase 3): citizen idea → support threshold → review → poll
# ============================================================================

class IdeaCreateRequest(BaseModel):
    territory_id: str = Field(..., min_length=26, max_length=26)
    title: str = Field(..., min_length=5, max_length=200)
    body: str = Field(..., min_length=10, max_length=4000)
    topic_slug: Optional[str] = None


class IdeaRejectRequest(BaseModel):
    note: str = Field(default='', max_length=500)


def _idea_out(idea, viewer=None, supported_ids=None) -> dict:
    return {
        'id': idea.id,
        'object_type': 'civic_idea',
        'title': idea.title,
        'body': idea.body,
        'status': idea.status,
        'territory_id': idea.territory_id,
        'territory_name': idea.territory.name,
        'territory_level': idea.territory.level,
        'topic_slug': idea.topic.slug if idea.topic_id else None,
        'author_hna': idea.author.hna,
        'author_display_name': idea.author.display_name or '',
        'support_count': idea.support_count,
        'threshold': settings.CIVIC_IDEA_SUPPORT_THRESHOLD,
        'supported_by_me': bool(supported_ids and idea.id in supported_ids),
        'promoted_poll_id': idea.promoted_poll_id,
        'review_note': idea.review_note,
        'created_at': idea.created_at.isoformat(),
    }


@civic_router.get("/ideas/", auth=OptionalProfileAuth())
@ratelimit(group='civic:ideas_list', key='ip', rate='60/m')
def list_ideas(request, scope: Optional[str] = None, country: Optional[str] = None,
               status: Optional[str] = None, page: int = 1, page_size: int = 20):
    """Ideas in the viewer's residency chain (same scoping as the poll feed)."""
    from .models import CivicIdea, CivicIdeaSupport
    profile = getattr(request, 'auth_profile', None)
    page_size = min(max(page_size, 1), 50)

    chain = []
    if profile:
        chain = civic.residency_chain(profile)
    elif country:
        c = Territory.objects.filter(level=Territory.Level.COUNTRY, code=country.upper()).first()
        if c:
            chain = [c]
    if scope and scope != 'all':
        chain = [t for t in chain if t.level == scope]
    if not chain:
        return []

    qs = (CivicIdea.objects
          .filter(territory_id__in=[t.id for t in chain])
          .select_related('territory', 'author', 'topic'))
    if status:
        qs = qs.filter(status=status)
    else:
        qs = qs.exclude(status__in=[CivicIdea.Status.REJECTED, CivicIdea.Status.ARCHIVED])
    ideas = list(qs.order_by('-support_count', '-created_at')[(page - 1) * page_size: page * page_size])

    supported_ids = set()
    if profile and ideas:
        supported_ids = set(CivicIdeaSupport.objects.filter(
            profile=profile, idea__in=ideas).values_list('idea_id', flat=True))
    return [_idea_out(i, profile, supported_ids) for i in ideas]


@civic_router.post("/ideas/", auth=ProfileAuth())
@ratelimit(group='civic:idea_create', key='user', rate='5/h')
def create_idea(request, data: IdeaCreateRequest):
    from .models import CivicIdea, CivicIdeaSupport
    profile = request.auth_profile
    if not profile.civic_opinion_consent:
        raise HttpError(422, "Civic consent required")

    territory = get_object_or_404(Territory, id=data.territory_id, is_active=True)
    chain = civic.residency_chain(profile)
    if territory.id not in [t.id for t in chain]:
        raise HttpError(403, "Territory is outside your residency scope")

    topic = None
    if data.topic_slug:
        from taxonomy.models import Category
        topic = Category.objects.filter(slug=data.topic_slug, is_active=True,
                                        parent__slug='civic-topics').first()
        if topic is None:
            raise HttpError(404, "Unknown civic topic")

    idea = CivicIdea.objects.create(
        territory=territory, topic=topic,
        title=data.title.strip(), body=data.body.strip(),
        author=profile, support_count=1,
    )
    CivicIdeaSupport.objects.create(idea=idea, profile=profile)  # author supports implicitly
    return _idea_out(idea, profile, {idea.id})


def _refresh_idea_support(idea) -> None:
    from .models import CivicIdea, CivicIdeaSupport
    idea.support_count = CivicIdeaSupport.objects.filter(idea=idea).count()
    update_fields = ['support_count']
    if (idea.status == CivicIdea.Status.OPEN
            and idea.support_count >= settings.CIVIC_IDEA_SUPPORT_THRESHOLD):
        idea.status = CivicIdea.Status.REVIEW
        update_fields.append('status')
        try:
            from notifications.services import emit_notification
            if idea.author.account:
                emit_notification(
                    idea.author.account,
                    type='civic_idea_threshold',
                    title=idea.title[:120],
                    body='Your idea reached the support threshold and entered formulation review.',
                    url='/governance/ideas',
                    data={'idea_id': idea.id},
                )
        except Exception:
            pass
    idea.save(update_fields=update_fields)


@civic_router.post("/ideas/{idea_id}/support/", auth=ProfileAuth())
@ratelimit(group='civic:idea_support', key='user', rate='30/m')
def support_idea(request, idea_id: str):
    """Supporter lists are never public (Art. 9-adjacent) — counts only."""
    from .models import CivicIdea, CivicIdeaSupport
    profile = request.auth_profile
    if not profile.civic_opinion_consent:
        raise HttpError(422, "Civic consent required")
    idea = get_object_or_404(CivicIdea.objects.select_related('territory', 'author', 'topic'), id=idea_id)
    if idea.status not in (CivicIdea.Status.OPEN, CivicIdea.Status.REVIEW):
        raise HttpError(400, "Idea is not open for support")
    chain = civic.residency_chain(profile)
    if idea.territory_id not in [t.id for t in chain]:
        raise HttpError(403, "Idea territory is outside your residency scope")
    CivicIdeaSupport.objects.get_or_create(idea=idea, profile=profile)
    _refresh_idea_support(idea)
    return _idea_out(idea, profile, {idea.id})


@civic_router.post("/ideas/{idea_id}/unsupport/", auth=ProfileAuth())
@ratelimit(group='civic:idea_support', key='user', rate='30/m')
def unsupport_idea(request, idea_id: str):
    from .models import CivicIdea, CivicIdeaSupport
    profile = request.auth_profile
    idea = get_object_or_404(CivicIdea.objects.select_related('territory', 'author', 'topic'), id=idea_id)
    CivicIdeaSupport.objects.filter(idea=idea, profile=profile).delete()
    _refresh_idea_support(idea)
    return _idea_out(idea, profile, set())


@civic_router.post("/ideas/{idea_id}/report/", auth=ProfileAuth())
@ratelimit(group='civic:idea_report', key='user', rate='10/h')
def report_idea(request, idea_id: str):
    from .models import CivicIdea
    from django.db.models import F
    CivicIdea.objects.filter(id=idea_id).update(reports_count=F('reports_count') + 1)
    return {'reported': True}


@civic_router.post("/ideas/{idea_id}/reject/", auth=ProfileAuth())
@ratelimit(group='civic:idea_reject', key='user', rate='30/m')
def reject_idea(request, idea_id: str, data: IdeaRejectRequest):
    """Staff formulation review: reject with a note (visible to the author)."""
    from .models import CivicIdea
    profile = request.auth_profile
    if not profile.account.is_staff:
        raise HttpError(403, "Staff only")
    idea = get_object_or_404(CivicIdea.objects.select_related('territory', 'author', 'topic'), id=idea_id)
    idea.status = CivicIdea.Status.REJECTED
    idea.review_note = data.note
    idea.reviewed_by = profile
    idea.save(update_fields=['status', 'review_note', 'reviewed_by'])
    try:
        from notifications.services import emit_notification
        if idea.author.account:
            emit_notification(
                idea.author.account, type='civic_idea_rejected',
                title=idea.title[:120],
                body=data.note or 'Your idea was not promoted to a poll.',
                url='/governance/ideas', data={'idea_id': idea.id},
            )
    except Exception:
        pass
    return _idea_out(idea, profile)


def link_promoted_idea(idea_id: str, poll, reviewer) -> None:
    """Called from poll creation (from_idea_id): closes the pipeline loop and
    notifies every supporter that their idea became a live poll."""
    from .models import CivicIdea, CivicIdeaSupport
    idea = CivicIdea.objects.filter(id=idea_id).select_related('author').first()
    if idea is None:
        return
    idea.status = CivicIdea.Status.PROMOTED
    idea.promoted_poll = poll
    idea.reviewed_by = reviewer
    idea.save(update_fields=['status', 'promoted_poll', 'reviewed_by'])
    try:
        from notifications.services import emit_notification
        supporter_profiles = (CivicIdeaSupport.objects.filter(idea=idea)
                              .select_related('profile__account'))
        for s in supporter_profiles:
            account = s.profile.account
            if account:
                emit_notification(
                    account, type='civic_idea_promoted',
                    title=idea.title[:120],
                    body='An idea you supported is now a live poll — cast your voice.',
                    url=f'/governance/polls/{poll.id}',
                    data={'idea_id': idea.id, 'poll_id': poll.id},
                )
    except Exception as e:
        logger.warning(f"idea promote notify failed: {e}")
