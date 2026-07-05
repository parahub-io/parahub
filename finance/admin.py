from django.contrib import admin
from .models import Payment, Donation, Subscription


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'sender', 'recipient', 'amount_sats', 'status', 'subscription', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['sender__local_name', 'recipient__local_name', 'description', 'ln_payment_hash']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['sender', 'recipient', 'subscription']


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ['id', 'profile', 'source', 'donation_amount_sats', 'source_amount_sats',
                    'support_level_at_time', 'status', 'created_at']
    list_filter = ['source', 'status', 'created_at']
    search_fields = ['profile__local_name', 'ln_payment_hash']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['profile']
    date_hierarchy = 'created_at'


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['id', 'subscriber', 'recipient', 'amount_sats', 'status', 'is_live_display',
                    'expires_at', 'last_paid_at', 'created_at']
    list_filter = ['status', 'expires_at', 'created_at']
    search_fields = ['subscriber__local_name', 'recipient__local_name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'started_at']
    raw_id_fields = ['subscriber', 'recipient']

    @admin.display(boolean=True, description='Live')
    def is_live_display(self, obj):
        return obj.is_live
