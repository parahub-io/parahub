from django.contrib import admin
from django.utils import timezone
from .models import (Instance, ObjectVideo, ObjectShare, ObjectDistribution,
                     DistributionLine, ContentReport)


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


@admin.register(ContentReport)
class ContentReportAdmin(admin.ModelAdmin):
    """Moderation queue for UGC reports (Play UGC policy: taking action)."""

    list_display = ['created_at', 'reason', 'object_type', 'excerpt_short',
                    'reported_profile', 'reporter', 'status']
    list_filter = ['status', 'reason', 'object_type']
    search_fields = ['object_id', 'excerpt', 'details',
                     'reporter__local_name', 'reported_profile__local_name']
    readonly_fields = ['id', 'object_id', 'object_type', 'reporter', 'reported_profile',
                       'reason', 'details', 'excerpt', 'context_url',
                       'created_at', 'updated_at']
    list_select_related = ['reporter', 'reported_profile']
    date_hierarchy = 'created_at'
    actions = ['mark_actioned', 'mark_dismissed']

    @admin.display(description='Excerpt')
    def excerpt_short(self, obj):
        return (obj.excerpt[:60] + '…') if len(obj.excerpt) > 60 else obj.excerpt

    def _review(self, request, queryset, status):
        updated = queryset.filter(status=ContentReport.Status.PENDING).update(
            status=status, reviewed_by=request.user, reviewed_at=timezone.now(),
        )
        self.message_user(request, f"{updated} report(s) marked {status}")

    @admin.action(description='Mark selected as ACTIONED')
    def mark_actioned(self, request, queryset):
        self._review(request, queryset, ContentReport.Status.ACTIONED)

    @admin.action(description='Mark selected as DISMISSED')
    def mark_dismissed(self, request, queryset):
        self._review(request, queryset, ContentReport.Status.DISMISSED)