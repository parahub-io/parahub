from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'sender', 'recipient', 'amount_sats', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['sender__local_name', 'recipient__local_name', 'description', 'ln_payment_hash']
    readonly_fields = ['id', 'created_at', 'updated_at']
