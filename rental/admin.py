# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import Bookable, Availability, AvailabilityException, Booking


class AvailabilityInline(admin.TabularInline):
    model = Availability
    extra = 0


class AvailabilityExceptionInline(admin.TabularInline):
    model = AvailabilityException
    extra = 0


@admin.register(Bookable)
class BookableAdmin(admin.ModelAdmin):
    list_display = ('id', 'item', 'booking_mode', 'confirmation', 'requires_contract', 'is_active')
    list_filter = ('booking_mode', 'confirmation', 'requires_contract', 'is_active')
    search_fields = ('id', 'item__id', 'item__title')
    inlines = [AvailabilityInline, AvailabilityExceptionInline]


@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ('id', 'bookable', 'start', 'stop', 'slot_minutes')
    search_fields = ('id', 'bookable__id')


@admin.register(AvailabilityException)
class AvailabilityExceptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'bookable', 'start', 'end', 'reason')
    search_fields = ('id', 'bookable__id')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'bookable', 'renter', 'start', 'end', 'status', 'price_total', 'currency',
                    'cancelled_by', 'cancel_note')
    list_filter = ('status', 'mode')
    search_fields = ('id', 'bookable__id', 'renter__id')
    raw_id_fields = ('bookable', 'renter', 'created_by', 'contract', 'cancelled_by')
