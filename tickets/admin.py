from django.contrib import admin
from tickets.models import TicketType, Ticket


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price_sats', 'sold_count', 'max_capacity', 'is_active', 'operator')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'operator__local_name')
    raw_id_fields = ('operator', 'event', 'route')


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'ticket_type', 'buyer', 'amount_paid_sats', 'paid_at', 'used_at')
    list_filter = ('status',)
    search_fields = ('qr_token', 'ln_payment_hash', 'buyer__local_name')
    raw_id_fields = ('ticket_type', 'buyer')
