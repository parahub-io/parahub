from django.db import models
from django.utils import timezone
from core.models import ULIDModel
from identity.models import Profile
from geo.models import Establishment

# ============================================================================
# VOTING SYSTEM (NEW - Polls with Multiple Choice & Liquid Democracy)
# ============================================================================

class PollContext(ULIDModel):
    """Контекст голосования - к чему привязано"""
    class ContextType(models.TextChoices):
        ORGANIZATION = 'organization', 'Organization'
        COMMUNITY = 'community', 'Community'
        TSZH = 'tszh', 'ТСЖ/HOA'  # deprecated alias, use CONDOMINIUM
        ADHOC = 'adhoc', 'Ad-hoc группа'
        TERRITORY = 'territory', 'Territory'  # context_id = geo.Territory ULID
        HOUSEHOLD = 'household', 'Household'  # context_id = iot.Property ULID
        CONDOMINIUM = 'condominium', 'Condominium'  # context_id = geo.Establishment ULID

    context_type = models.CharField(max_length=20, choices=ContextType.choices)
    context_id = models.CharField(max_length=26)  # ULID организации/группы
    created_by = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='poll_contexts_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'governance_poll_context'
        indexes = [
            models.Index(fields=['context_type', 'context_id']),
        ]


class Poll(ULIDModel):
    """Голосование с поддержкой Multiple Choice и Liquid Democracy"""
    class PollType(models.TextChoices):
        SIMPLE = 'simple', 'Yes/No'
        MULTIPLE_CHOICE = 'multiple_choice', 'Multiple Choice'
        RANKED = 'ranked', 'Ranked Choice'  # будущее
        QUADRATIC = 'quadratic', 'Quadratic'  # будущее
        SLIDERS = 'sliders', 'Sliders'  # opinion axes, status-quo-relative -2..+2 (civic)

    class QuorumType(models.TextChoices):
        SIMPLE_MAJORITY = 'simple_majority', '50%+1'
        QUALIFIED_MAJORITY = 'qualified_majority', '2/3'
        UNANIMOUS = 'unanimous', '100%'
        CUSTOM = 'custom', 'Custom %'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ACTIVE = 'active', 'Active'
        ENDED = 'ended', 'Ended'
        CANCELLED = 'cancelled', 'Cancelled'

    context = models.ForeignKey(PollContext, on_delete=models.CASCADE, related_name='polls')
    title = models.CharField(max_length=200)
    description = models.TextField()

    # Timing
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)  # если null = бессрочно
    warning_hours = models.IntegerField(default=24)  # за сколько предупредить неголосовавших

    # Voting rules
    poll_type = models.CharField(max_length=20, choices=PollType.choices, default=PollType.MULTIPLE_CHOICE)

    # Quorum & thresholds
    quorum_type = models.CharField(max_length=20, choices=QuorumType.choices, default=QuorumType.SIMPLE_MAJORITY)
    quorum_percent = models.DecimalField(max_digits=5, decimal_places=2, default=50.00)

    # Weights (для будущего)
    use_weights = models.BooleanField(default=False)  # учитывать ли веса голосов
    weight_source = models.CharField(max_length=20, null=True, blank=True, choices=[
        ('wot_reputation', 'WoT Reputation'),
        ('ownership_shares', 'Доля собственности'),
        ('custom', 'Custom weights')
    ])

    # Settings
    allow_delegation = models.BooleanField(default=True)
    require_wot_verified = models.BooleanField(default=False)  # пока False
    public_results = models.BooleanField(default=True)  # для будущего ZK

    # Civic polls (see PK/civic-polls-system.md)
    class PollClass(models.TextChoices):
        DECISION = 'decision', 'Decision'  # binding, identified, quorum
        OPINION = 'opinion', 'Opinion'  # non-binding barometer, no quorum

    class BallotMode(models.TextChoices):
        OPEN = 'open', 'Open'  # identified votes (PollVote), visible to audience
        ANONYMOUS = 'anonymous', 'Anonymous'  # pseudonymous votes (OpinionVote), forced for TERRITORY opinion

    poll_class = models.CharField(max_length=10, choices=PollClass.choices,
                                  default=PollClass.DECISION, db_index=True)
    ballot_mode = models.CharField(max_length=10, choices=BallotMode.choices, default=BallotMode.OPEN)
    civic_destination = models.CharField(
        max_length=300, blank=True, default='',
        help_text="Where the result goes (e.g. 'Junta de Freguesia de Moncao, 2026-09-01') — efficacy commitment"
    )
    topic = models.ForeignKey(
        'taxonomy.Category', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='civic_polls',
        help_text="Civic topic (curated subset) — standing topic delegations match on this"
    )
    civic_outcome = models.TextField(
        blank=True, default='',
        help_text="What actually happened after the poll — closes the loop"
    )
    frozen_results = models.JSONField(
        null=True, blank=True,
        help_text="Aggregates frozen at purge time (30d after end) when raw opinion votes are deleted"
    )

    # Crypto audit
    merkle_root = models.CharField(max_length=64, null=True, blank=True)  # финальный Merkle root
    result_pgp_signature = models.TextField(null=True, blank=True)  # подпись создателя на результаты

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='polls_created')

    class Meta:
        db_table = 'governance_poll'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['context', 'status']),
        ]


class PollOption(ULIDModel):
    """Вариант голосования"""
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    order = models.IntegerField()

    class Meta:
        db_table = 'governance_poll_option'
        ordering = ['order']
        unique_together = [['poll', 'order']]


class PollEligibleVoter(ULIDModel):
    """Кто имеет право голосовать"""
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='eligible_voters')
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='eligible_polls')
    weight = models.DecimalField(max_digits=10, decimal_places=4, default=1.0000)  # вес голоса

    class Meta:
        db_table = 'governance_poll_eligible_voter'
        unique_together = [['poll', 'profile']]
        indexes = [
            models.Index(fields=['poll', 'profile']),
        ]


class PollVoteDelegation(ULIDModel):
    """Делегирование голоса (per-poll, транзитивное)"""
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='vote_delegations')
    delegator = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='poll_delegations_given')
    delegate = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='poll_delegations_received')

    pgp_signature = models.TextField()  # подпись делегатора
    signed_payload = models.JSONField()  # {"poll_id": "...", "delegate_id": "...", "timestamp": "..."}

    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)  # если отозвали
    revoke_signature = models.TextField(null=True, blank=True)

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = 'governance_poll_vote_delegation'
        unique_together = [['poll', 'delegator']]
        indexes = [
            models.Index(fields=['poll', 'is_active']),
            models.Index(fields=['poll', 'delegate', 'is_active']),
        ]


class PollVote(ULIDModel):
    """Прямой голос"""
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='direct_votes')
    voter = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='poll_votes_cast')
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name='votes')

    # Crypto proof
    pgp_signature = models.TextField()
    signed_payload = models.JSONField()  # {"poll_id": "...", "option_id": "...", "timestamp": "..."}

    # Для транзитивного делегирования
    voted_on_behalf_of = models.JSONField(default=list)  # [profile_id1, profile_id2, ...] цепочка делегирования
    effective_weight = models.DecimalField(max_digits=10, decimal_places=4, default=1.0000)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'governance_poll_vote'
        unique_together = [['poll', 'voter']]
        indexes = [
            models.Index(fields=['poll', 'created_at']),
            models.Index(fields=['poll', 'option']),
        ]


class PollAuditLog(ULIDModel):
    """Публичный неизменяемый лог для криптографической проверки"""
    class Action(models.TextChoices):
        POLL_CREATED = 'poll_created', 'Poll Created'
        POLL_STARTED = 'poll_started', 'Poll Started'
        VOTE_CAST = 'vote_cast', 'Vote Cast'
        DELEGATION_CREATED = 'delegation_created', 'Delegation Created'
        DELEGATION_REVOKED = 'delegation_revoked', 'Delegation Revoked'
        POLL_ENDED = 'poll_ended', 'Poll Ended'
        OPINION_VOTE = 'opinion_vote', 'Opinion Vote (pseudonymous)'
        OPINION_ERASED = 'opinion_erased', 'Opinion Votes Erased (GDPR)'

    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=30, choices=Action.choices)
    # NULL actor = pseudonymous opinion-vote event (or profile erased); SET_NULL keeps the chain intact.
    actor = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='poll_audit_actions')
    # ULID snapshot used in hash recomputation so chain verification survives actor deletion.
    # Empty string for anonymous events (hashed as None).
    actor_ulid = models.CharField(max_length=26, blank=True, default='')

    # Merkle tree для батчей
    previous_log_hash = models.CharField(max_length=64, null=True, blank=True)
    current_log_hash = models.CharField(max_length=64)  # SHA256 от (previous + payload)

    payload = models.JSONField()  # детали действия
    pgp_signature = models.TextField()

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'governance_poll_audit_log'
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['poll', 'timestamp']),
        ]


class StandingDelegation(ULIDModel):
    """Standing (cross-poll) delegation for civic opinion polls (Phase 2.5).

    Scope is a topic (all polls tagged with it) or a territory subtree («всё в моей
    фрегезии/стране»). Acceptance is mandatory: it doubles as the delegate's
    GDPR Art. 9(2)(a) consent to disclose their votes in this scope to delegators.
    Resolution priority: own vote > topic > territory (deepest territory first).
    """

    class ScopeType(models.TextChoices):
        TOPIC = 'topic', 'Topic'
        TERRITORY = 'territory', 'Territory'

    delegator = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='standing_delegations_given')
    delegate = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='standing_delegations_received')
    scope_type = models.CharField(max_length=10, choices=ScopeType.choices)
    topic = models.ForeignKey('taxonomy.Category', null=True, blank=True, on_delete=models.CASCADE,
                              related_name='standing_delegations')
    territory = models.ForeignKey('geo.Territory', null=True, blank=True, on_delete=models.CASCADE,
                                  related_name='standing_delegations')

    pgp_signature = models.TextField(blank=True, default='')
    signed_payload = models.JSONField(default=dict, blank=True)

    accepted_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = 'governance_standing_delegation'
        constraints = [
            models.UniqueConstraint(
                fields=['delegator', 'scope_type', 'topic', 'territory'],
                condition=models.Q(is_active=True),
                name='unique_active_standing_delegation_per_scope',
            ),
        ]
        indexes = [
            models.Index(fields=['delegate', 'is_active']),
            models.Index(fields=['delegator', 'is_active']),
        ]

    @property
    def is_operational(self) -> bool:
        return self.is_active and self.accepted_at is not None and self.revoked_at is None

    def __str__(self):
        scope = self.topic.slug if self.topic_id else (self.territory.code if self.territory_id else '?')
        return f"{self.delegator_id[:8]} → {self.delegate_id[:8]} ({self.scope_type}:{scope})"


class OpinionVote(ULIDModel):
    """Pseudonymous vote for opinion-class polls (ballot_mode=anonymous).

    GDPR Art. 9 design (PK/civic-polls-system.md): NO profile FK, NO IP, NO PGP.
    voter_token = HMAC-SHA256(CIVIC_VOTE_SECRET, profile_ulid + poll_ulid) — re-vote
    upserts by (poll, voter_token); erasure recomputes tokens per poll and deletes.
    voter_territory is coarsened to municipality level to prevent small-parish
    re-identification on a DB leak.
    """
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='opinion_votes')
    voter_token = models.CharField(max_length=64)
    payload = models.JSONField()  # {"option": <PollOption ulid>} | {"values": {axis_ulid: -2..2}}
    voter_territory = models.CharField(
        max_length=16, blank=True, default='',
        help_text="Municipality-level code (DICO) for k>=5 breakdowns; parish polls carry the poll's own code"
    )
    voter_wot_verified = models.BooleanField(default=False)
    via_delegation = models.BooleanField(default=False)  # materialized standing-delegation row (Phase 2.5)

    class Meta:
        db_table = 'governance_opinion_vote'
        unique_together = [['poll', 'voter_token']]
        indexes = [
            models.Index(fields=['poll', 'created_at']),
            models.Index(fields=['poll', 'voter_territory']),
        ]




class CivicIdea(ULIDModel):
    """Citizen-submitted poll idea (Phase 3 — PK/civic-polls-system.md § 9).

    Pipeline: open → (support threshold) review → promoted (staff writes the final
    neutral formulation as an opinion poll) | rejected. Supporting an idea is itself
    Art. 9-adjacent — supporter lists are NEVER public, counts only.
    """

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        REVIEW = 'review', 'Review (threshold reached)'
        PROMOTED = 'promoted', 'Promoted to poll'
        REJECTED = 'rejected', 'Rejected'
        ARCHIVED = 'archived', 'Archived'

    territory = models.ForeignKey('geo.Territory', on_delete=models.CASCADE, related_name='civic_ideas')
    topic = models.ForeignKey('taxonomy.Category', null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='civic_ideas')
    title = models.CharField(max_length=200)
    body = models.TextField(max_length=4000)
    author = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='civic_ideas')

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    support_count = models.IntegerField(default=0)  # denormalized; truth = CivicIdeaSupport rows
    reports_count = models.IntegerField(default=0)
    promoted_poll = models.ForeignKey(Poll, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name='source_ideas')
    reviewed_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='civic_ideas_reviewed')
    review_note = models.CharField(max_length=500, blank=True, default='')

    class Meta:
        db_table = 'governance_civic_idea'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['territory', 'status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.title[:40]} [{self.status}]"


class CivicIdeaSupport(ULIDModel):
    """Support signature for an idea. Never exposed individually — counts only."""
    idea = models.ForeignKey(CivicIdea, on_delete=models.CASCADE, related_name='supports')
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='civic_idea_supports')

    class Meta:
        db_table = 'governance_civic_idea_support'
        unique_together = [['idea', 'profile']]
