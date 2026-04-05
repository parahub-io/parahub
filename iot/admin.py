from django.contrib import admin
from .models import IoTDevice, TraccarUser, TrackerLocation, TrackerHistory, MeshSubscription, VehicleAssignment


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


@admin.register(MeshSubscription)
class MeshSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['id', 'client_ip', 'client_mac', 'gateway_device', 'status',
                    'amount_sats', 'paid_at', 'expires_at', 'created_at']
    list_filter = ['status', 'created_at', 'gateway_device']
    search_fields = ['client_ip', 'client_mac', 'ln_payment_hash']
    readonly_fields = ['id', 'ln_payment_hash', 'ln_invoice', 'created_at']


@admin.register(VehicleAssignment)
class VehicleAssignmentAdmin(admin.ModelAdmin):
    list_display = ['device', 'route', 'direction_id', 'date', 'status', 'display_vehicle_id', 'created_at']
    list_filter = ['status', 'date']
    search_fields = ['device__name', 'route__short_name', 'display_vehicle_id']
    readonly_fields = ['id', 'created_at', 'updated_at']
    date_hierarchy = 'date'
