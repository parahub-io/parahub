from django.contrib import admin
from .models import Instance, ObjectVideo, ObjectShare, ObjectDistribution, DistributionLine


@admin.register(Instance)
class InstanceAdmin(admin.ModelAdmin):
    list_display = ['domain', 'name', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['domain', 'name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(ObjectVideo)
class ObjectVideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'object_id', 'peertube_uuid', 'duration_seconds', 'is_published', 'uploaded_by']
    list_filter = ['is_published']
    search_fields = ['title', 'object_id', 'peertube_uuid']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(ObjectShare)
class ObjectShareAdmin(admin.ModelAdmin):
    list_display = ['profile', 'object_id', 'share_type', 'share_percent', 'invested_amount', 'is_active', 'created_at']
    list_filter = ['share_type', 'is_active', 'invested_currency']
    search_fields = ['object_id', 'profile__display_name']
    readonly_fields = ['id', 'created_at', 'updated_at']


class DistributionLineInline(admin.TabularInline):
    model = DistributionLine
    extra = 0
    readonly_fields = ['id', 'profile', 'share_percent', 'amount', 'status', 'payment']


@admin.register(ObjectDistribution)
class ObjectDistributionAdmin(admin.ModelAdmin):
    list_display = ['object_id', 'period_label', 'total_amount', 'currency', 'status', 'created_at']
    list_filter = ['status', 'currency']
    search_fields = ['object_id', 'period_label']
    readonly_fields = ['id', 'created_at', 'updated_at']
    inlines = [DistributionLineInline]