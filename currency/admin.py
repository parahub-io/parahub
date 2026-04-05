from django.contrib import admin
from .models import ExchangeRate


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ['currency', 'rate_to_eur', 'updated_at']
    search_fields = ['currency']
    readonly_fields = ['updated_at']
