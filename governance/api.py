"""
Polls API - Multiple Choice Voting with Liquid Democracy
"""

from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import paginate, PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import models, transaction, IntegrityError
from django.db.models import Count
from django.utils import timezone
from typing import List, Optional, Dict
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from decimal import Decimal
import hashlib
import logging
from django.conf import settings
from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit
from parahub.crypto.pgp import verify_profile_signature
from identity.models import Profile
from geo.models import EstablishmentMembership
from .models import (
    Poll, PollContext, PollOption, PollEligibleVoter,
    PollVote, PollVoteDelegation, PollAuditLog
)
from .services import VotingService, AuditService

logger = logging.getLogger(__name__)

# Create polls router
polls_router = Router()


def _maybe_update_poll_statuses():
    """Auto-activate/end polls, throttled to once per 30s via Redis."""
    from django.core.cache import cache
    if cache.get('polls:status_check'):
        return  # Already checked recently
    cache.set('polls:status_check', 1, 30)

    now = timezone.now()
    Poll.objects.filter(
        status=Poll.Status.DRAFT,
        start_time__lte=now
    ).update(status=Poll.Status.ACTIVE)

    to_end_ids = list(Poll.objects.filter(
        status=Poll.Status.ACTIVE,
        end_time__isnull=False,
        end_time__lt=now
    ).values_list('id', flat=True))
    if to_end_ids:
        Poll.objects.filter(id__in=to_end_ids).update(status=Poll.Status.ENDED)
        for ended_poll in Poll.objects.filter(id__in=to_end_ids):
            AuditService.finalize_poll(ended_poll)
        if getattr(settings, 'OPENTIMESTAMPS_ENABLED', False):
            _create_poll_proofs(to_end_ids)


def _create_poll_proofs(poll_ids):
    """Create pending OTS proofs for polls that just transitioned to ENDED."""
    from audit_log.signals import _create_pending_proof
    from audit_log.models import TimestampProof
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(Poll)
    already_done = set(TimestampProof.objects.filter(
        content_type=ct, object_id__in=poll_ids
    ).values_list('object_id', flat=True))

    for poll in Poll.objects.filter(id__in=poll_ids).prefetch_related('options'):
        if poll.id in already_done:
            continue
        data = {
            'id': poll.id,
            'object_type': 'poll',
            'title': poll.title,
            'created_by_id': poll.created_by_id,
            'end_time': poll.end_time.isoformat() if poll.end_time else None,
            'merkle_root': getattr(poll, 'merkle_root', None),
            'result_pgp_signature': getattr(poll, 'result_pgp_signature', None),
        }
        try:
            _create_pending_proof(poll, data)
        except Exception as e:
            logger.error(f"Creating pending OTS proof failed for poll {poll.id[:8]}: {e}")


# ============================================================================
# WebSocket Helper
# ============================================================================

def _resolve_civic_topic(topic_slug):
    """Curated civic topic lookup (children of 'civic-topics'); None-safe."""
    if not topic_slug:
        return None
    from taxonomy.models import Category
    topic = Category.objects.filter(slug=topic_slug, is_active=True,
                                    parent__slug='civic-topics').first()
    if topic is None:
        raise HttpError(404, "Unknown civic topic")
    return topic


def broadcast_poll_update(poll_id: str, event_type: str, data: dict):
    """Broadcast update to all WebSocket clients connected to poll."""
    from parahub.services.ws_publish import ws_publish
    # Normalize event_type: poll_vote_cast → poll.vote_cast
    ws_type = event_type.replace('_', '.', 1)
    ws_publish(f'poll:{poll_id}', {'type': ws_type, **data})


# ============================================================================
# Pydantic Schemas
# ============================================================================

class PollContextSchema(BaseModel):
    context_type: str
    context_id: str

    model_config = ConfigDict(from_attributes=True)


class PollOptionSchema(BaseModel):
    id: str
    text: str
    description: str = ""
    order: int

    model_config = ConfigDict(from_attributes=True)


class PollListItemSchema(BaseModel):
    id: str
    object_type: str = "poll"
    title: str
    description: str
    status: str
    poll_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    allow_delegation: bool
    created_by_id: str
    created_by_hna: str
    created_by_display_name: str = ''
    created_at: datetime

    # Stats
    total_eligible: int = 0
    total_voted: int = 0
    quorum_percent: Decimal
    quorum_met: bool = False
    is_demo: bool = False

    # Civic (PK/civic-polls-system.md)
    poll_class: str = 'decision'
    ballot_mode: str = 'open'
    civic_destination: str = ''
    civic_outcome: str = ''
    scope_level: Optional[str] = None  # territory level when context is TERRITORY
    scope_name: str = ''

    model_config = ConfigDict(from_attributes=True)


class PollDetailSchema(PollListItemSchema):
    context: PollContextSchema
    options: List[PollOptionSchema] = []
    quorum_type: str
    use_weights: bool
    weight_source: Optional[str] = None
    require_wot_verified: bool
    public_results: bool
    warning_hours: int

    # Results (если public_results=True)
    results: Optional[List[Dict]] = None
    winning_option_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PollCreateRequest(BaseModel):
    context_type: str = Field(..., pattern="^(organization|community|tszh|adhoc|territory|household|condominium)$")
    context_id: str = Field(..., min_length=26, max_length=26)
    # Civic (PK/civic-polls-system.md): territory contexts are staff-only in MVP
    poll_class: str = Field(default="decision", pattern="^(decision|opinion)$")
    civic_destination: str = Field(default='', max_length=300)
    topic_slug: Optional[str] = None  # civic topic (standing delegations match on it)
    from_idea_id: Optional[str] = Field(None, min_length=26, max_length=26)  # promote a citizen idea
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=10)
    options: List[str] = Field(..., min_length=2, max_length=10)
    poll_type: str = Field(default="multiple_choice", pattern="^(simple|multiple_choice|ranked|quadratic|sliders)$")

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    warning_hours: int = Field(default=24, ge=1, le=168)

    quorum_type: str = Field(default="simple_majority", pattern="^(simple_majority|qualified_majority|unanimous|custom)$")
    quorum_percent: Decimal = Field(default=Decimal("50.00"), ge=0, le=100)

    allow_delegation: bool = True
    require_wot_verified: bool = False
    public_results: bool = True
    use_weights: bool = False
    weight_source: Optional[str] = None

    eligible_voter_ids: Optional[List[str]] = None

    @field_validator('options')
    @classmethod
    def validate_options(cls, v):
        if len(v) < 2:
            raise ValueError('Минимум 2 варианта ответа')
        if len(v) > 10:
            raise ValueError('Максимум 10 вариантов ответа')
        return v


class VoteCastRequest(BaseModel):
    option_id: str = Field(..., min_length=26, max_length=26)
    pgp_signature: str = ''
    signed_timestamp: str = ''


class DelegationCreateRequest(BaseModel):
    delegate_id: str = Field(..., min_length=26, max_length=26)
    pgp_signature: str = ''
    signed_timestamp: str = ''


class DelegationRevokeRequest(BaseModel):
    pgp_signature: str = ''
    signed_timestamp: str = ''


class VoteResponseSchema(BaseModel):
    id: str
    object_type: str = "poll_vote"
    poll_id: str
    voter_id: str
    voter_hna: str
    voter_display_name: str = ''
    option_id: str
    option_text: str
    effective_weight: Decimal
    voted_on_behalf_of: List[str] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DelegationResponseSchema(BaseModel):
    id: str
    object_type: str = "poll_delegation"
    poll_id: str
    delegator_id: str
    delegator_hna: str
    delegator_display_name: str = ''
    delegate_id: str
    delegate_hna: str
    delegate_display_name: str = ''
    is_active: bool
    created_at: datetime
    revoked_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ChainProfileSchema(BaseModel):
    hna: str = ''
    display_name: str = ''


class DelegationChainSchema(BaseModel):
    chain: List[str]  # [delegator_id, intermediate_id, ..., final_delegate_id]
    length: int
    final_delegate_id: str
    final_delegate_hna: str
    final_delegate_display_name: str = ''
    has_voted: bool
    vote_option_id: Optional[str] = None
    chain_profiles: Dict[str, ChainProfileSchema] = {}


class PollResultsSchema(BaseModel):
    poll_id: str
    status: str
    total_eligible: int
    total_voted: int
    total_weight_voted: float
    eligible_weight: float
    quorum_percent: float
    quorum_met: bool
    results: List[Dict]
    winning_option_id: Optional[str] = None


class AuditLogEntrySchema(BaseModel):
    id: str
    action: str
    actor_id: Optional[str] = None  # None for pseudonymous opinion-vote events
    actor_hna: str = ''
    actor_display_name: str = ''
    timestamp: datetime
    payload: Dict
    current_log_hash: str
    previous_log_hash: Optional[str] = None
    pgp_signature: str

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Endpoints
# ============================================================================

@polls_router.get("/", response=List[PollListItemSchema], auth=None)
@ratelimit(group='governance:polls_list', key='ip', rate='30/m')
@paginate(PageNumberPagination, page_size=20)
def list_polls(
    request,
    status: Optional[str] = None,
    context_type: Optional[str] = None,
    context_id: Optional[str] = None,
    created_by_id: Optional[str] = None,
):
    """
    Список всех голосований с фильтрацией.
    Публичный endpoint.
    """
    _maybe_update_poll_statuses()

    # Opinion (civic) polls live in /governance/civic/feed/ — excluded here so the
    # group listing doesn't duplicate them
    queryset = Poll.objects.exclude(poll_class=Poll.PollClass.OPINION)

    if status:
        queryset = queryset.filter(status=status)
    if context_type:
        queryset = queryset.filter(context__context_type=context_type)
    if context_id:
        queryset = queryset.filter(context__context_id=context_id)
    if created_by_id:
        queryset = queryset.filter(created_by_id=created_by_id)

    # Use Subquery for counts to avoid cross-join from double LEFT JOIN
    from django.db.models import Subquery, OuterRef
    queryset = queryset.select_related('created_by', 'context').annotate(
        _total_eligible=Subquery(
            PollEligibleVoter.objects.filter(poll=OuterRef('pk'))
            .values('poll').annotate(c=Count('id')).values('c'),
            default=0,
        ),
        _total_voted=Subquery(
            PollVote.objects.filter(poll=OuterRef('pk'))
            .values('poll').annotate(c=Count('id')).values('c'),
            default=0,
        ),
    ).order_by('-created_at')

    results = []
    for poll in queryset:
        total_eligible = poll._total_eligible or 0
        total_voted = poll._total_voted or 0

        # Lightweight quorum calculation (avoids full delegation resolution)
        if total_eligible > 0:
            turnout = Decimal(total_voted) / Decimal(total_eligible) * Decimal('100')
        else:
            turnout = Decimal('0')

        if poll.quorum_type == Poll.QuorumType.SIMPLE_MAJORITY:
            quorum_met = turnout > poll.quorum_percent
        else:
            quorum_met = turnout >= poll.quorum_percent

        item = PollListItemSchema(
            id=poll.id,
            title=poll.title,
            description=poll.description,
            status=poll.status,
            poll_type=poll.poll_type,
            start_time=poll.start_time,
            end_time=poll.end_time,
            allow_delegation=poll.allow_delegation,
            created_by_id=poll.created_by.id,
            created_by_hna=poll.created_by.hna,
            created_by_display_name=poll.created_by.display_name or '',
            created_at=poll.created_at,
            total_eligible=total_eligible,
            total_voted=total_voted,
            quorum_percent=poll.quorum_percent,
            quorum_met=quorum_met,
            is_demo=bool(poll.attributes.get('__demo_seed') or poll.attributes.get('demo')),
        )
        results.append(item)

    return results


@polls_router.get("/{poll_id}/", response=PollDetailSchema, auth=None)
def get_poll(request, poll_id: str):
    """
    Детальная информация о голосовании.
    Публичный endpoint.
    """
    # Auto-activate if start_time arrived
    now = timezone.now()
    Poll.objects.filter(
        id=poll_id,
        status=Poll.Status.DRAFT,
        start_time__lte=now
    ).update(status=Poll.Status.ACTIVE)

    # Auto-update status if poll has ended
    ended_qs = Poll.objects.filter(
        id=poll_id,
        status=Poll.Status.ACTIVE,
        end_time__isnull=False,
        end_time__lt=now
    )
    to_end_ids = list(ended_qs.values_list('id', flat=True))
    if to_end_ids:
        ended_qs.update(status=Poll.Status.ENDED)
        # Финализируем Merkle chain
        for ended_poll in Poll.objects.filter(id__in=to_end_ids):
            AuditService.finalize_poll(ended_poll)
        if getattr(settings, 'OPENTIMESTAMPS_ENABLED', False):
            _create_poll_proofs(to_end_ids)

    poll = get_object_or_404(
        Poll.objects.select_related('created_by', 'context').prefetch_related('options', 'eligible_voters'),
        id=poll_id
    )

    # Territory / community scope info for civic polls
    scope_level = None
    scope_name = ''
    if poll.context.context_type == PollContext.ContextType.TERRITORY:
        from geo.models import Territory
        territory = Territory.objects.filter(id=poll.context.context_id).first()
        if territory:
            scope_level = territory.level
            scope_name = territory.name
    elif poll.context.context_type in (PollContext.ContextType.HOUSEHOLD, PollContext.ContextType.CONDOMINIUM):
        scope_level = poll.context.context_type
        if poll.context.context_type == PollContext.ContextType.HOUSEHOLD:
            from iot.models import Property
            prop = Property.objects.filter(id=poll.context.context_id).first()
            scope_name = prop.name if prop else ''
        else:
            from geo.models import Establishment
            est = Establishment.objects.filter(id=poll.context.context_id).first()
            scope_name = est.name if est else ''
        # Keep the audience in sync with live membership (lazy, active polls only)
        if poll.status == Poll.Status.ACTIVE:
            from governance.civic import sync_poll_audience
            sync_poll_audience(poll)

    # Подсчёт результатов
    service = VotingService(poll)
    poll_results = service.calculate_results()

    # Собираем опции
    options = [
        PollOptionSchema(
            id=opt.id,
            text=opt.text,
            description=opt.description,
            order=opt.order
        )
        for opt in poll.options.all()
    ]

    # Собираем результаты (если публичные или голосование завершено)
    results_data = None
    winning_option_id = None
    if poll.public_results or poll.status == Poll.Status.ENDED:
        results_data = poll_results['results']
        winning_option_id = poll_results['winning_option_id']

    detail = PollDetailSchema(
        id=poll.id,
        title=poll.title,
        description=poll.description,
        status=poll.status,
        poll_type=poll.poll_type,
        start_time=poll.start_time,
        end_time=poll.end_time,
        allow_delegation=poll.allow_delegation,
        created_by_id=poll.created_by.id,
        created_by_hna=poll.created_by.hna,
        created_by_display_name=poll.created_by.display_name or '',
        created_at=poll.created_at,
        context=PollContextSchema(
            context_type=poll.context.context_type,
            context_id=poll.context.context_id
        ),
        options=options,
        quorum_type=poll.quorum_type,
        quorum_percent=poll.quorum_percent,
        use_weights=poll.use_weights,
        weight_source=poll.weight_source,
        require_wot_verified=poll.require_wot_verified,
        public_results=poll.public_results,
        warning_hours=poll.warning_hours,
        total_eligible=poll_results['total_eligible'],
        total_voted=poll_results['total_voted'],
        quorum_met=poll_results['quorum_met'],
        results=results_data,
        winning_option_id=winning_option_id,
        is_demo=bool(poll.attributes.get('__demo_seed') or poll.attributes.get('demo')),
        poll_class=poll.poll_class,
        ballot_mode=poll.ballot_mode,
        civic_destination=poll.civic_destination,
        civic_outcome=poll.civic_outcome,
        scope_level=scope_level,
        scope_name=scope_name,
    )

    return detail


@polls_router.post("/", response=PollDetailSchema, auth=ProfileAuth())
def create_poll(request, data: PollCreateRequest):
    """
    Создание нового голосования.
    Требует аутентификации.
    """
    profile = request.auth_profile

    is_territory = data.context_type == 'territory'
    is_community = data.context_type in ('household', 'condominium')
    if is_territory:
        # MVP: territory (civic) polls are staff-seeded until the Phase 3 idea pipeline
        if not profile.account.is_staff:
            raise HttpError(403, "Territory polls are staff-only for now")
        from geo.models import Territory
        if not Territory.objects.filter(id=data.context_id, is_active=True).exists():
            raise HttpError(404, "Territory not found")
        if data.poll_class != 'opinion':
            raise HttpError(400, "Territory polls are opinion-class only (binding civic votes are a later phase)")
    elif is_community:
        # Household/condominium: any audience member creates (it's their living room)
        from governance.civic import resolve_context_audience
        community_audience = resolve_context_audience(data.context_type, data.context_id)
        if profile.id not in community_audience:
            raise HttpError(403, "You are not a member of this household/condominium")
    elif data.context_id:
        # Authorization: verify creator is a member of the establishment
        if not EstablishmentMembership.objects.filter(
            establishment_id=data.context_id, profile=profile
        ).exists():
            raise HttpError(403, "You must be a member of this organization to create polls")

    if data.poll_type == 'sliders' and not is_territory:
        raise HttpError(400, "Slider polls are territory opinion polls only for now")

    with transaction.atomic():
        # Создаём контекст
        context = PollContext.objects.create(
            context_type=data.context_type,
            context_id=data.context_id,
            created_by=profile
        )

        # Вычисляем start_time и end_time
        start_time = data.start_time or timezone.now()
        end_time = data.end_time

        # Opinion-class invariants. Territory → anonymous ballots, no delegation
        # (Phase 2.5 adds standing delegations). Community (household/condo) →
        # open ballots on the identified PollVote engine, per-poll delegation allowed
        # (the liquid-democracy sandbox).
        is_opinion = (is_territory and data.poll_class == 'opinion') or is_community

        # Создаём голосование
        poll = Poll.objects.create(
            context=context,
            title=data.title,
            description=data.description,
            poll_type=data.poll_type,
            start_time=start_time,
            end_time=end_time,
            warning_hours=data.warning_hours,
            quorum_type=data.quorum_type,
            quorum_percent=data.quorum_percent,
            allow_delegation=data.allow_delegation if is_community else (False if is_opinion else data.allow_delegation),
            require_wot_verified=data.require_wot_verified,
            public_results=data.public_results,
            use_weights=False if is_opinion else data.use_weights,
            weight_source=None if is_opinion else data.weight_source,
            poll_class=Poll.PollClass.OPINION if is_opinion else Poll.PollClass.DECISION,
            ballot_mode=Poll.BallotMode.ANONYMOUS if is_territory and is_opinion else Poll.BallotMode.OPEN,
            civic_destination=data.civic_destination if is_opinion else '',
            topic=_resolve_civic_topic(data.topic_slug) if is_territory else None,
            status=Poll.Status.ACTIVE,
            created_by=profile
        )

        # Создаём опции
        for i, option_text in enumerate(data.options):
            PollOption.objects.create(
                poll=poll,
                text=option_text,
                order=i
            )

        # Добавляем eligible voters
        if is_territory and is_opinion:
            pass  # Anonymous opinion polls have no eligible list — the audience is the residency scope at vote time
        elif is_community:
            # Audience snapshot from live membership; kept in sync lazily on poll reads
            PollEligibleVoter.objects.bulk_create(
                [PollEligibleVoter(poll=poll, profile_id=pid, weight=Decimal('1.0000'))
                 for pid in community_audience],
                ignore_conflicts=True,
            )
        elif data.use_weights and data.weight_source == 'ownership_shares' and data.context_id:
            # Auto-populate from ObjectShare (cooperatives, energy cells, etc.)
            from core.services.shares import setup_share_weighted_voters
            count = setup_share_weighted_voters(poll, data.context_id)
            # Ensure creator is included even if they have no shares
            if not PollEligibleVoter.objects.filter(poll=poll, profile=profile).exists():
                PollEligibleVoter.objects.create(
                    poll=poll,
                    profile=profile,
                    weight=Decimal('0.0000')
                )
        else:
            # Manual voter list (existing behavior)
            PollEligibleVoter.objects.create(
                poll=poll,
                profile=profile,
                weight=Decimal('1.0000')
            )

            if data.eligible_voter_ids:
                for voter_id in data.eligible_voter_ids:
                    if voter_id == profile.id:
                        continue
                    try:
                        voter_profile = Profile.objects.get(id=voter_id)
                        PollEligibleVoter.objects.create(
                            poll=poll,
                            profile=voter_profile,
                            weight=Decimal('1.0000')
                        )
                    except Profile.DoesNotExist:
                        logger.warning(f"Profile {voter_id} not found, skipping")

        # Создаём audit log entry
        AuditService.create_log_entry(
            poll=poll,
            action='poll_created',
            actor=profile,
            payload={
                'poll_id': poll.id,
                'title': poll.title,
                'options': data.options,
                'eligible_voters_count': poll.eligible_voters.count()
            },
            pgp_signature='SYSTEM_GENERATED'  # Poll creation - system action
        )

        # Send notifications to eligible voters
        eligible_voters = poll.eligible_voters.all()
        if eligible_voters.exists():
            from parahub.services.ws_publish import ws_publish

            poll_data = {
                'id': poll.id,
                'title': poll.title,
                'description': poll.description,
                'created_by_id': profile.id,
                'created_by_hna': profile.hna,
                'end_time': poll.end_time.isoformat() if poll.end_time else None,
            }
            payload = {'type': 'poll.created', 'poll': poll_data}

            for eligible_voter in eligible_voters:
                voter_account = eligible_voter.profile.account
                if voter_account:
                    ws_publish(f"user:{voter_account.id}", payload)

            logger.info(f"Sent notifications to {eligible_voters.count()} eligible voters for poll {poll.id}")

        logger.info(f"Poll created: {poll.id} by {profile.id}")

        # Ideas pipeline (Phase 3): promoting an idea links it and notifies supporters
        if is_territory and data.from_idea_id:
            from governance.civic_api import link_promoted_idea
            link_promoted_idea(data.from_idea_id, poll, profile)

    # Возвращаем созданное голосование
    return get_poll(request, poll.id)


@polls_router.post("/{poll_id}/vote/", response=VoteResponseSchema, auth=ProfileAuth())
def cast_vote(request, poll_id: str, data: VoteCastRequest):
    """
    Проголосовать в голосовании.
    Требует аутентификации.
    """
    profile = request.auth_profile
    poll = get_object_or_404(Poll, id=poll_id)

    # Проверка существования option (safe to check outside transaction)
    try:
        option = PollOption.objects.get(id=data.option_id, poll=poll)
    except PollOption.DoesNotExist:
        raise HttpError(400, "Недопустимый вариант ответа")

    # PGP signature verification (mandatory if profile has key)
    verify_profile_signature(
        profile,
        {"option_id": data.option_id, "poll_id": poll_id, "timestamp": data.signed_timestamp},
        data.pgp_signature,
        data.signed_timestamp,
        error_prefix="Governance vote PGP",
    )

    try:
        with transaction.atomic():
            # Lock poll row to serialize concurrent vote attempts
            Poll.objects.select_for_update().get(id=poll_id)

            # Check voting rights inside transaction to prevent TOCTOU
            service = VotingService(poll)
            can_vote, error_msg = service.check_can_vote(profile)
            if not can_vote:
                raise HttpError(400, error_msg)

            # Получаем вес голоса
            try:
                eligible = PollEligibleVoter.objects.get(poll=poll, profile=profile)
                weight = eligible.weight
            except PollEligibleVoter.DoesNotExist:
                weight = Decimal('1.0000')

            # Создаём голос
            vote = PollVote.objects.create(
                poll=poll,
                voter=profile,
                option=option,
                pgp_signature=data.pgp_signature,
                signed_payload={
                    "poll_id": poll.id,
                    "option_id": option.id,
                    "timestamp": data.signed_timestamp or timezone.now().isoformat()
                },
                voted_on_behalf_of=[],
                effective_weight=weight
            )

            # Создаём audit log entry
            AuditService.create_log_entry(
                poll=poll,
                action='vote_cast',
                actor=profile,
                payload={
                    'vote_id': vote.id,
                    'option_id': option.id,
                    'effective_weight': str(weight)
                },
                pgp_signature=data.pgp_signature
            )

            logger.info(f"Vote cast: {vote.id} by {profile.id} on poll {poll.id}")
    except IntegrityError:
        raise HttpError(400, "Вы уже проголосовали")

    # Broadcast WebSocket update
    service = VotingService(poll)
    results = service.calculate_results()

    broadcast_poll_update(
        poll_id=poll.id,
        event_type='poll_vote_cast',
        data={
            'voter_hna': profile.hna,
            'option_id': option.id,
            'option_text': option.text,
            'total_voted': results['total_voted'],
            'timestamp': timezone.now().isoformat()
        }
    )

    return VoteResponseSchema(
        id=vote.id,
        poll_id=poll.id,
        voter_id=profile.id,
        voter_hna=profile.hna,
        voter_display_name=profile.display_name or '',
        option_id=option.id,
        option_text=option.text,
        effective_weight=vote.effective_weight,
        voted_on_behalf_of=vote.voted_on_behalf_of,
        created_at=vote.created_at
    )


@polls_router.post("/{poll_id}/delegate/", response=DelegationResponseSchema, auth=ProfileAuth())
def create_delegation(request, poll_id: str, data: DelegationCreateRequest):
    """
    Делегировать голос другому пользователю.
    Требует аутентификации.
    """
    delegator = request.auth_profile
    poll = get_object_or_404(Poll, id=poll_id)

    # Получаем делегата
    try:
        delegate = Profile.objects.get(id=data.delegate_id)
    except Profile.DoesNotExist:
        raise HttpError(404, "Делегат не найден")

    # PGP signature verification (mandatory if profile has key)
    verify_profile_signature(
        delegator,
        {"delegate_id": data.delegate_id, "poll_id": poll_id, "timestamp": data.signed_timestamp},
        data.pgp_signature,
        data.signed_timestamp,
        error_prefix="Governance delegation PGP",
    )

    with transaction.atomic():
        # Lock poll row to serialize concurrent delegation attempts
        Poll.objects.select_for_update().get(id=poll_id)

        # Check delegation rights inside transaction to prevent TOCTOU
        service = VotingService(poll)
        can_delegate, error_msg = service.check_can_delegate(delegator, delegate)
        if not can_delegate:
            raise HttpError(400, error_msg)

        # Use update_or_create to handle re-delegation after revocation
        # unique_together=[poll, delegator] means only one record per pair
        delegation, created = PollVoteDelegation.objects.update_or_create(
            poll=poll,
            delegator=delegator,
            defaults={
                'delegate': delegate,
                'pgp_signature': data.pgp_signature,
                'signed_payload': {
                    "poll_id": poll.id,
                    "delegate_id": delegate.id,
                    "timestamp": data.signed_timestamp or timezone.now().isoformat()
                },
                'is_active': True,
                'revoked_at': None,
                'revoke_signature': None,
            }
        )

        # Создаём audit log entry
        AuditService.create_log_entry(
            poll=poll,
            action='delegation_created',
            actor=delegator,
            payload={
                'delegation_id': delegation.id,
                'delegate_id': delegate.id
            },
            pgp_signature=data.pgp_signature
        )

        logger.info(f"Delegation {'created' if created else 're-activated'}: {delegation.id} from {delegator.id} to {delegate.id}")

    # Broadcast WebSocket update
    broadcast_poll_update(
        poll_id=poll.id,
        event_type='poll_delegation_created',
        data={
            'delegator_hna': delegator.hna,
            'delegate_hna': delegate.hna,
            'timestamp': timezone.now().isoformat()
        }
    )

    return DelegationResponseSchema(
        id=delegation.id,
        poll_id=poll.id,
        delegator_id=delegator.id,
        delegator_hna=delegator.hna,
        delegator_display_name=delegator.display_name or '',
        delegate_id=delegate.id,
        delegate_hna=delegate.hna,
        delegate_display_name=delegate.display_name or '',
        is_active=delegation.is_active,
        created_at=delegation.created_at,
        revoked_at=delegation.revoked_at
    )


@polls_router.post("/{poll_id}/delegate/revoke/", response=Dict, auth=ProfileAuth())
def revoke_delegation(request, poll_id: str, data: DelegationRevokeRequest):
    """
    Отозвать делегирование голоса.
    Требует аутентификации.
    """
    delegator = request.auth_profile
    poll = get_object_or_404(Poll, id=poll_id)

    # Cannot modify voting state on ended/cancelled polls
    if poll.status not in (Poll.Status.ACTIVE, Poll.Status.DRAFT):
        raise HttpError(400, f"Голосование не активно (статус: {poll.get_status_display()})")

    try:
        delegation = PollVoteDelegation.objects.get(
            poll=poll,
            delegator=delegator,
            is_active=True
        )
    except PollVoteDelegation.DoesNotExist:
        raise HttpError(404, "Активное делегирование не найдено")

    # PGP signature verification (mandatory if profile has key)
    verify_profile_signature(
        delegator,
        {"action": "revoke_delegation", "poll_id": poll_id, "timestamp": data.signed_timestamp},
        data.pgp_signature,
        data.signed_timestamp,
        error_prefix="Governance revoke PGP",
    )

    with transaction.atomic():
        delegation.is_active = False
        delegation.revoked_at = timezone.now()
        delegation.revoke_signature = data.pgp_signature
        delegation.save()

        # Создаём audit log entry
        AuditService.create_log_entry(
            poll=poll,
            action='delegation_revoked',
            actor=delegator,
            payload={
                'delegation_id': delegation.id
            },
            pgp_signature=data.pgp_signature
        )

        logger.info(f"Delegation revoked: {delegation.id}")

    # Broadcast WebSocket update
    broadcast_poll_update(
        poll_id=poll.id,
        event_type='poll_delegation_revoked',
        data={
            'delegator_hna': delegator.hna,
            'timestamp': timezone.now().isoformat()
        }
    )

    return {"message": "Делегирование успешно отозвано", "delegation_id": delegation.id}


@polls_router.get("/{poll_id}/results/", response=PollResultsSchema, auth=None)
@ratelimit(group='governance:poll_results', key='ip', rate='30/m')
def get_results(request, poll_id: str):
    """
    Получить результаты голосования.
    Публичный endpoint если public_results=True или poll.status=ENDED.
    """
    poll = get_object_or_404(Poll, id=poll_id)

    # Проверка доступа к результатам
    if not poll.public_results and poll.status != Poll.Status.ENDED:
        raise HttpError(403, "Результаты недоступны")

    service = VotingService(poll)
    results = service.calculate_results()

    return PollResultsSchema(**results)


@polls_router.get("/{poll_id}/delegations/", response=List[DelegationChainSchema], auth=None)
def get_delegation_chains(request, poll_id: str):
    """
    Получить визуализацию цепочек делегирования.
    Публичный endpoint.
    """
    poll = get_object_or_404(Poll, id=poll_id)

    service = VotingService(poll)
    chains_data = service.get_delegation_chains_visual()

    # Получаем информацию о голосах
    votes_map = {
        v.voter.id: v.option.id
        for v in PollVote.objects.filter(poll=poll).select_related('voter', 'option')
    }

    # Получаем профили
    profile_ids = set()
    for chain_data in chains_data:
        profile_ids.update(chain_data['chain'])

    _profiles = Profile.objects.filter(id__in=profile_ids)
    profiles_map = {p.id: p.hna for p in _profiles}
    display_names_map = {p.id: p.display_name or '' for p in _profiles}

    results = []
    for chain_data in chains_data:
        final_delegate_id = chain_data['final_delegate_id']
        has_voted = final_delegate_id in votes_map
        vote_option_id = votes_map.get(final_delegate_id)

        # Redact vote_option_id for private polls
        if not poll.public_results and vote_option_id:
            vote_option_id = None

        chain_profiles = {
            pid: ChainProfileSchema(
                hna=profiles_map.get(pid, ''),
                display_name=display_names_map.get(pid, ''),
            )
            for pid in chain_data['chain']
        }

        results.append(DelegationChainSchema(
            chain=chain_data['chain'],
            length=chain_data['length'],
            final_delegate_id=final_delegate_id,
            final_delegate_hna=profiles_map.get(final_delegate_id, ''),
            final_delegate_display_name=display_names_map.get(final_delegate_id, ''),
            has_voted=has_voted,
            vote_option_id=vote_option_id,
            chain_profiles=chain_profiles,
        ))

    return results


@polls_router.get("/{poll_id}/my-status/", response=Dict, auth=ProfileAuth())
def get_my_status(request, poll_id: str):
    """
    Получить статус текущего пользователя в голосовании:
    - Имеет ли право голоса
    - Проголосовал ли
    - Есть ли активное делегирование
    """
    profile = request.auth_profile
    poll = get_object_or_404(Poll, id=poll_id)

    # Проверка права голоса
    is_eligible = PollEligibleVoter.objects.filter(poll=poll, profile=profile).exists()

    # Проверка голоса
    try:
        vote = PollVote.objects.get(poll=poll, voter=profile)
        has_voted = True
        vote_option_id = vote.option.id
        vote_option_text = vote.option.text
    except PollVote.DoesNotExist:
        has_voted = False
        vote_option_id = None
        vote_option_text = None

    # Проверка делегирования
    try:
        delegation = PollVoteDelegation.objects.get(
            poll=poll,
            delegator=profile,
            is_active=True
        )
        has_delegation = True
        delegate_id = delegation.delegate.id
        delegate_hna = delegation.delegate.hna

        # Проверка проголосовал ли делегат
        delegate_voted = PollVote.objects.filter(poll=poll, voter_id=delegate_id).exists()
    except PollVoteDelegation.DoesNotExist:
        has_delegation = False
        delegate_id = None
        delegate_hna = None
        delegate_voted = False

    service = VotingService(poll)
    can_vote, vote_error = service.check_can_vote(profile)

    return {
        "poll_id": poll.id,
        "profile_id": profile.id,
        "is_eligible": is_eligible,
        "can_vote": can_vote,
        "vote_error": vote_error,
        "has_voted": has_voted,
        "vote_option_id": vote_option_id,
        "vote_option_text": vote_option_text,
        "has_delegation": has_delegation,
        "delegate_id": delegate_id,
        "delegate_hna": delegate_hna,
        "delegate_voted": delegate_voted,
    }


@polls_router.get("/{poll_id}/audit-log/", response=List[AuditLogEntrySchema], auth=None)
@ratelimit(group='governance:audit_log', key='ip', rate='30/m')
def get_audit_log(request, poll_id: str):
    """
    Получить криптографический audit log голосования.
    Публичный endpoint.
    """
    poll = get_object_or_404(Poll, id=poll_id)

    logs = PollAuditLog.objects.filter(poll=poll).select_related('actor').order_by('timestamp')

    results = []
    for log in logs:
        payload = log.payload

        # Redact option_id in vote_cast entries for private polls
        # Replace with sha256(actor_id + option_id + poll_id) for verifiability
        if not poll.public_results and log.action == 'vote_cast' and 'option_id' in payload and log.actor_id:
            payload = dict(payload)
            raw_option_id = payload['option_id']
            payload['option_id'] = hashlib.sha256(
                f"{log.actor_id}{raw_option_id}{poll.id}".encode()
            ).hexdigest()
            payload['option_id_hashed'] = True

        results.append(AuditLogEntrySchema(
            id=log.id,
            action=log.action,
            actor_id=log.actor.id if log.actor else None,
            actor_hna=log.actor.hna if log.actor else '',
            actor_display_name=(log.actor.display_name or '') if log.actor else '',
            timestamp=log.timestamp,
            payload=payload,
            current_log_hash=log.current_log_hash,
            previous_log_hash=log.previous_log_hash,
            pgp_signature=log.pgp_signature
        ))

    return results
