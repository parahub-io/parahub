from django.contrib import admin
from .models import Debt, DebtRepayment


class DebtRepaymentInline(admin.TabularInline):
    model = DebtRepayment
    extra = 0
    readonly_fields = ('created_at', 'created_by')
    fields = ('amount', 'repayment_type', 'confirmed_by_creditor', 'confirmed_by_debtor', 'notes', 'created_at')


@admin.register(Debt)
class DebtAdmin(admin.ModelAdmin):
    list_display = ('id', 'debtor', 'creditor', 'amount', 'remaining_amount', 'currency', 'status', 'created_at')
    list_filter = ('status', 'currency', 'created_at')
    search_fields = ('id', 'debtor__display_name', 'creditor__display_name', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at', 'version', 'percent_settled')
    inlines = [DebtRepaymentInline]

    fieldsets = (
        ('Parties', {
            'fields': ('debtor', 'creditor', 'created_by')
        }),
        ('Amount', {
            'fields': ('amount', 'remaining_amount', 'currency', 'percent_settled')
        }),
        ('Status', {
            'fields': ('status', 'confirmed_by_creditor_at', 'confirmed_by_debtor_at')
        }),
        ('Details', {
            'fields': ('description',)
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at', 'version'),
            'classes': ('collapse',)
        }),
    )


@admin.register(DebtRepayment)
class DebtRepaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'debt', 'amount', 'repayment_type', 'created_at')
    list_filter = ('repayment_type', 'created_at')
    search_fields = ('id', 'debt__id', 'notes')
    readonly_fields = ('id', 'created_at', 'updated_at', 'confirmed_at')

    fieldsets = (
        (None, {
            'fields': ('debt', 'amount', 'repayment_type')
        }),
        ('Clearing', {
            'fields': ('clearing_exchange_id',)
        }),
        ('Details', {
            'fields': ('notes', 'created_by', 'confirmed_at')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
