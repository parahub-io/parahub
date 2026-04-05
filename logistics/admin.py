from django.contrib import admin
from .models import Shipment, ShipmentEvent, CarrierOffer, RideRequest, RideBooking, RideReview


class ShipmentEventInline(admin.TabularInline):
    model = ShipmentEvent
    extra = 0
    fields = ['event_type', 'hub', 'actor', 'note', 'created_at']
    readonly_fields = ['id', 'created_at']


class CarrierOfferInline(admin.TabularInline):
    model = CarrierOffer
    extra = 0
    fields = ['carrier', 'from_hub', 'to_hub', 'fee_sats', 'status']
    readonly_fields = ['id', 'created_at']


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ['tracking_code', 'title', 'sender', 'receiver', 'status', 'origin_hub', 'destination_hub', 'created_at']
    list_filter = ['status', 'size_category', 'created_at']
    search_fields = ['tracking_code', 'title', 'sender__local_name', 'receiver__local_name']
    readonly_fields = ['id', 'tracking_code', 'pickup_code', 'created_at', 'updated_at']
    inlines = [ShipmentEventInline, CarrierOfferInline]


@admin.register(ShipmentEvent)
class ShipmentEventAdmin(admin.ModelAdmin):
    list_display = ['shipment', 'event_type', 'hub', 'actor', 'created_at']
    list_filter = ['event_type', 'created_at']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(CarrierOffer)
class CarrierOfferAdmin(admin.ModelAdmin):
    list_display = ['shipment', 'carrier', 'from_hub', 'to_hub', 'fee_sats', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    readonly_fields = ['id', 'created_at', 'updated_at']


class RideBookingInline(admin.TabularInline):
    model = RideBooking
    extra = 0
    fields = ['driver', 'status', 'available_seats', 'driver_note']
    readonly_fields = ['id', 'created_at']


@admin.register(RideRequest)
class RideRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'passenger', 'origin_stop', 'destination_stop', 'price_sats',
                    'passengers_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['passenger__local_name', 'origin_stop__name', 'destination_stop__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    inlines = [RideBookingInline]


@admin.register(RideBooking)
class RideBookingAdmin(admin.ModelAdmin):
    list_display = ['id', 'request', 'driver', 'status', 'available_seats', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['driver__local_name', 'request__passenger__local_name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(RideReview)
class RideReviewAdmin(admin.ModelAdmin):
    list_display = ['reviewer', 'reviewee', 'booking', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['reviewer__local_name', 'reviewee__local_name']
    readonly_fields = ['id', 'created_at', 'updated_at']
