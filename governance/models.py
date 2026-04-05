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
        TSZH = 'tszh', 'ТСЖ/HOA'
        ADHOC = 'adhoc', 'Ad-hoc группа'

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

    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=30, choices=Action.choices)
    actor = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='poll_audit_actions')

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


