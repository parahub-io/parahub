from django.contrib import admin
from .models import (
    IoTDevice, TraccarUser, TrackerLocation, TrackerHistory,
    MeshPass, MeshPassCredit, MeshDevice, VehicleAssignment,
)


@admin.register(IoTDevice)
class IoTDeviceAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'device_type', 'item_twin', 'last_seen', 'created_at']
    list_filter = ['device_type', 'last_seen', 'created_at']
    search_fields = ['name', 'owner__local_name']
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(TraccarUser)
class TraccarUserAdmin(admin.ModelAdmin):
    list_display = ['profile', 'traccar_user_id', 'traccar_username', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['profile__local_name', 'traccar_username']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(TrackerLocation)
class TrackerLocationAdmin(admin.ModelAdmin):
    list_display = ['device', 'location', 'speed', 'battery_level', 'device_timestamp']
    list_filter = ['device_timestamp']
    search_fields = ['device__name']
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(TrackerHistory)
class TrackerHistoryAdmin(admin.ModelAdmin):
    list_display = ['device', 'latitude', 'longitude', 'speed', 'time']
    list_filter = ['time']
    search_fields = ['device__name']
    date_hierarchy = 'time'


class MeshDeviceInline(admin.TabularInline):
    model = MeshDevice
    extra = 0
    readonly_fields = ['id', 'mac', 'last_ipv4', 'last_gateway', 'last_seen_at', 'created_at']


class MeshPassCreditInline(admin.TabularInline):
    model = MeshPassCredit
    extra = 0
    readonly_fields = ['id', 'source', 'days', 'amount_sats', 'ln_payment_hash', 'status', 'applied_at', 'created_at']


@admin.register(MeshPass)
class MeshPassAdmin(admin.ModelAdmin):
    list_display = ['id', 'profile', 'expires_at', 'max_devices', 'created_at']
    search_fields = ['profile__local_name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    inlines = [MeshDeviceInline, MeshPassCreditInline]


@admin.register(MeshDevice)
class MeshDeviceAdmin(admin.ModelAdmin):
    list_display = ['mac', 'label', 'mesh_pass', 'last_ipv4', 'last_gateway', 'last_seen_at', 'created_at']
    search_fields = ['mac', 'label', 'mesh_pass__profile__local_name']
    readonly_fields = ['id', 'created_at']


@admin.register(VehicleAssignment)
class VehicleAssignmentAdmin(admin.ModelAdmin):
    list_display = ['device', 'route', 'direction_id', 'date', 'status', 'display_vehicle_id', 'created_at']
    list_filter = ['status', 'date']
    search_fields = ['device__name', 'route__short_name', 'display_vehicle_id']
    readonly_fields = ['id', 'created_at', 'updated_at']
    date_hierarchy = 'date'
