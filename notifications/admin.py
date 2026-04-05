from django.contrib import admin
from .models import PushSubscription


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'endpoint_short', 'is_active', 'failed_count', 'last_sent_at', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__email', 'endpoint', 'user_agent']
    readonly_fields = ['id', 'created_at', 'updated_at', 'last_sent_at', 'failed_count']
    raw_id_fields = ['user']

    def endpoint_short(self, obj):
        return obj.endpoint[:80] + '...' if len(obj.endpoint) > 80 else obj.endpoint
    endpoint_short.short_description = 'Endpoint'

    fieldsets = (
        ('Subscription Info', {
            'fields': ('id', 'user', 'endpoint', 'p256dh', 'auth')
        }),
        ('Status', {
            'fields': ('is_active', 'failed_count', 'last_sent_at')
        }),
        ('Metadata', {
            'fields': ('user_agent', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
