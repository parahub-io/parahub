from django.contrib import admin
from parasos.models import SafetyGroup, SafetyGroupMember, SOSAlert, SOSResponse, InactivityWatch


@admin.register(SafetyGroup)
class SafetyGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'members_count', 'radius_m', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    raw_id_fields = ('created_by', 'world_object')


@admin.register(SafetyGroupMember)
class SafetyGroupMemberAdmin(admin.ModelAdmin):
    list_display = ('group', 'profile', 'role', 'presence', 'created_at')
    list_filter = ('role', 'presence')
    raw_id_fields = ('group', 'profile')


@admin.register(SOSAlert)
class SOSAlertAdmin(admin.ModelAdmin):
    list_display = ('group', 'sender', 'level', 'category', 'source', 'status', 'created_at')
    list_filter = ('level', 'category', 'status', 'source')
    raw_id_fields = ('group', 'sender')


@admin.register(SOSResponse)
class SOSResponseAdmin(admin.ModelAdmin):
    list_display = ('alert', 'responder', 'status', 'created_at')
    list_filter = ('status',)
    raw_id_fields = ('alert', 'responder')


@admin.register(InactivityWatch)
class InactivityWatchAdmin(admin.ModelAdmin):
    list_display = ('watched_profile', 'group', 'max_inactivity_hours', 'last_activity_at', 'is_active')
    list_filter = ('is_active',)
    raw_id_fields = ('group', 'watched_profile', 'ha_home')
