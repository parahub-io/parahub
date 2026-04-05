from django.contrib import admin
from .models import BudgetCategory, BudgetAllocation, BudgetEpoch, TreasuryAuditLog


@admin.register(BudgetCategory)
class BudgetCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon', 'order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    ordering = ('order',)


@admin.register(BudgetAllocation)
class BudgetAllocationAdmin(admin.ModelAdmin):
    list_display = ('profile', 'updated_at')
    search_fields = ('profile__local_name',)
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(BudgetEpoch)
class BudgetEpochAdmin(admin.ModelAdmin):
    list_display = ('label', 'status', 'total_eligible', 'total_participants', 'finalized_at')
    list_filter = ('status',)
    readonly_fields = ('id', 'created_at', 'merkle_root', 'finalized_at')


@admin.register(TreasuryAuditLog)
class TreasuryAuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'actor', 'timestamp', 'current_log_hash')
    list_filter = ('action',)
    readonly_fields = ('id', 'created_at', 'previous_log_hash', 'current_log_hash', 'timestamp')
    ordering = ('-timestamp',)
