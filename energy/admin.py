from django.contrib import admin
from .models import EnergyCell, EnergyProducer, EnergyConsumer


class EnergyProducerInline(admin.TabularInline):
    model = EnergyProducer
    extra = 0
    fields = ('profile', 'cpe_code', 'capacity_kw', 'battery_kwh', 'inverter_type', 'is_active')


class EnergyConsumerInline(admin.TabularInline):
    model = EnergyConsumer
    extra = 0
    fields = ('profile', 'cpe_code', 'distribution_coefficient', 'is_active')


@admin.register(EnergyCell)
class EnergyCellAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'current_price_eur', 'radius_km', 'transformer_id', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'transformer_id')
    inlines = [EnergyProducerInline, EnergyConsumerInline]
    readonly_fields = ('created_at', 'updated_at')
