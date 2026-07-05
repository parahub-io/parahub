from django.contrib import admin
from .models import PushSubscription, Notification, FCMDevice, Activity


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


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'recipient', 'type', 'category', 'title', 'read_at', 'created_at']
    list_filter = ['category', 'type', 'created_at']
    search_fields = ['recipient__email', 'title', 'body', 'type']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['recipient']


@admin.register(FCMDevice)
class FCMDeviceAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'platform', 'is_active', 'failed_count', 'last_sent_at', 'created_at']
    list_filter = ['platform', 'is_active', 'created_at']
    search_fields = ['user__email', 'token']
    readonly_fields = ['id', 'created_at', 'updated_at', 'last_sent_at', 'failed_count']
    raw_id_fields = ['user']


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ['id', 'actor', 'verb', 'category', 'title', 'created_at']
    list_filter = ['category', 'verb', 'created_at']
    search_fields = ['actor__email', 'verb', 'title', 'body']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['actor']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        # Append-only log written by notifications.signals — never created by hand.
        return False
