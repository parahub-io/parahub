from django.contrib import admin
from tickets.models import TicketType, Ticket


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'validity_minutes', 'concession_category', 'sold_count', 'max_capacity', 'is_active', 'operator', 'operator_establishment')
    list_filter = ('category', 'is_active', 'concession_category')
    search_fields = ('name', 'operator__local_name', 'operator_establishment__name')
    raw_id_fields = ('operator', 'operator_establishment', 'event', 'route', 'agency')

    @admin.display(description='Price')
    def price(self, obj):
        if obj.price_eur is not None:
            return f"{obj.price_eur} €"
        return f"{obj.price_sats} sats"


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'ticket_type', 'buyer', 'amount_due_sats', 'amount_paid_sats', 'price_eur', 'paid_at', 'used_at', 'valid_until', 'validation_count')
    list_filter = ('status',)
    search_fields = ('qr_token', 'ln_payment_hash', 'buyer__local_name')
    raw_id_fields = ('ticket_type', 'buyer')
