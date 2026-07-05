from django.contrib import admin
from .models import Contract, ContractReview, ArbiterProfile, ArbitrationVerdict


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'creator', 'partner', 'status', 'creator_signed_at', 'partner_signed_at']
    list_filter = ['status', 'creator_signed_at']
    search_fields = ['title', 'creator__local_name', 'partner__local_name', 'file_sha256']
    readonly_fields = ['id', 'file_sha256', 'creator_signature', 'partner_signature',
                       'creator_signed_at', 'partner_signed_at', 'creator_completed_at',
                       'partner_completed_at', 'arbitration_initiated_at']


@admin.register(ContractReview)
class ContractReviewAdmin(admin.ModelAdmin):
    list_display = ['contract', 'reviewer', 'reviewed', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['contract__title', 'reviewer__local_name', 'reviewed__local_name']
    raw_id_fields = ['contract', 'reviewer', 'reviewed']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(ArbiterProfile)
class ArbiterProfileAdmin(admin.ModelAdmin):
    list_display = ['profile', 'fee_amount', 'fee_currency', 'is_active', 'created_at']
    list_filter = ['is_active', 'fee_currency']
    search_fields = ['profile__local_name', 'bio']
    raw_id_fields = ['profile']
    filter_horizontal = ['specializations']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(ArbitrationVerdict)
class ArbitrationVerdictAdmin(admin.ModelAdmin):
    list_display = ['contract', 'arbiter', 'verdict_type', 'amount_awarded', 'currency', 'created_at']
    list_filter = ['verdict_type', 'created_at']
    search_fields = ['contract__title', 'arbiter__local_name', 'summary']
    raw_id_fields = ['contract', 'arbiter']
    readonly_fields = ['id', 'created_at', 'updated_at']
