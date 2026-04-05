from django.contrib import admin
from .models import (
    PollContext, Poll, PollOption, PollEligibleVoter,
    PollVoteDelegation, PollVote, PollAuditLog,
)


@admin.register(PollContext)
class PollContextAdmin(admin.ModelAdmin):
    list_display = ['id', 'context_type', 'context_id', 'created_by', 'created_at']
    list_filter = ['context_type', 'created_at']
    search_fields = ['context_id', 'created_by__local_name']
    readonly_fields = ['id', 'created_at']


class PollOptionInline(admin.TabularInline):
    model = PollOption
    extra = 0
    fields = ['order', 'text', 'description']
    readonly_fields = ['id']


class PollEligibleVoterInline(admin.TabularInline):
    model = PollEligibleVoter
    extra = 0
    fields = ['profile', 'weight']
    readonly_fields = ['id']
    autocomplete_fields = ['profile']


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ['title', 'context', 'poll_type', 'status', 'start_time', 'end_time',
                    'quorum_type', 'allow_delegation', 'created_by', 'created_at']
    list_filter = ['status', 'poll_type', 'quorum_type', 'allow_delegation', 'require_wot_verified', 'created_at']
    search_fields = ['title', 'description', 'created_by__local_name']
    readonly_fields = ['id', 'created_at', 'merkle_root', 'result_pgp_signature']
    inlines = [PollOptionInline, PollEligibleVoterInline]


@admin.register(PollVote)
class PollVoteAdmin(admin.ModelAdmin):
    list_display = ['poll', 'voter', 'option', 'effective_weight', 'created_at']
    list_filter = ['poll', 'created_at']
    search_fields = ['voter__local_name', 'poll__title']
    readonly_fields = ['id', 'pgp_signature', 'signed_payload', 'voted_on_behalf_of', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PollVoteDelegation)
class PollVoteDelegationAdmin(admin.ModelAdmin):
    list_display = ['poll', 'delegator', 'delegate', 'is_active', 'created_at', 'revoked_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['delegator__local_name', 'delegate__local_name', 'poll__title']
    readonly_fields = ['id', 'pgp_signature', 'signed_payload', 'revoke_signature', 'created_at', 'revoked_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PollAuditLog)
class PollAuditLogAdmin(admin.ModelAdmin):
    list_display = ['poll', 'action', 'actor', 'current_log_hash_short', 'timestamp']
    list_filter = ['action', 'timestamp']
    search_fields = ['poll__title', 'actor__local_name', 'current_log_hash']
    readonly_fields = ['id', 'poll', 'action', 'actor', 'previous_log_hash', 'current_log_hash',
                       'payload', 'pgp_signature', 'timestamp']

    @admin.display(description='Hash (8)')
    def current_log_hash_short(self, obj):
        return obj.current_log_hash[:8] if obj.current_log_hash else '—'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
