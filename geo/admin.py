from django.contrib import admin
from .models import (TransitDataSource, OpenSkyMission, Agency, Stop, Route, Shape, Trip, StopTime, RouteStop,
                     Vehicle, Place, WorldObject, Establishment, EstablishmentMembership, EstablishmentReview,
                     CalendarDate, Event, EventParticipant)


@admin.register(TransitDataSource)
class TransitDataSourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'format', 'url', 'is_active', 'last_imported_at', 'import_hash_short', 'created_at']
    list_filter = ['format', 'is_active', 'created_at']
    search_fields = ['name', 'url']
    readonly_fields = ['id', 'created_at', 'updated_at', 'last_import_hash', 'last_import_stats']

    @admin.display(description='Hash (8)')
    def import_hash_short(self, obj):
        return obj.last_import_hash[:8] if obj.last_import_hash else '—'


@admin.register(OpenSkyMission)
class OpenSkyMissionAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'pilot', 'reputation_reward', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['pilot__local_name', 'published_data_cid']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = ['name', 'source_id', 'data_source', 'timezone', 'lang', 'created_at']
    list_filter = ['timezone', 'lang', 'created_at']
    search_fields = ['name', 'source_id']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Stop)
class StopAdmin(admin.ModelAdmin):
    list_display = ['name', 'agency', 'source_id', 'parent_station', 'created_at']
    list_filter = ['agency', 'created_at']
    search_fields = ['name', 'source_id']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ['short_name', 'long_name', 'agency', 'route_type', 'route_color', 'source_id', 'created_at']
    list_filter = ['agency', 'route_type', 'created_at']
    search_fields = ['short_name', 'long_name', 'source_id']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Shape)
class ShapeAdmin(admin.ModelAdmin):
    list_display = ['source_id', 'agency', 'length_m', 'created_at']
    list_filter = ['agency']
    search_fields = ['source_id']
    readonly_fields = ['id', 'created_at', 'updated_at']

@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ['headsign', 'route', 'source_id', 'shape_ref', 'vehicle_item', 'created_at']
    list_filter = ['route', 'created_at']
    search_fields = ['headsign', 'source_id']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(RouteStop)
class RouteStopAdmin(admin.ModelAdmin):
    list_display = ['route', 'stop', 'sequence', 'created_at']
    list_filter = ['route', 'created_at']
    search_fields = ['route__short_name', 'stop__name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ['vehicle_id', 'agency', 'license_plate', 'model', 'is_active', 'created_at']
    list_filter = ['agency', 'is_active', 'created_at']
    search_fields = ['vehicle_id', 'license_plate', 'model']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'country_code', 'place_type', 'sort_order', 'population', 'parent_place', 'created_at']
    list_filter = ['country_code', 'place_type', 'created_at']
    search_fields = ['name', 'slug', 'country_code']
    readonly_fields = ['id', 'created_at', 'updated_at']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(StopTime)
class StopTimeAdmin(admin.ModelAdmin):
    list_display = ['trip', 'stop', 'arrival_time', 'departure_time', 'stop_sequence']
    list_filter = ['trip__route', 'arrival_time']
    search_fields = ['trip__headsign', 'stop__name']


@admin.register(WorldObject)
class WorldObjectAdmin(admin.ModelAdmin):
    list_display = ['full_address', 'city', 'country', 'xeno_source', 'xeno_id', 'establishments_count', 'created_at']
    list_filter = ['country', 'city', 'building_type', 'xeno_source', 'created_at']
    search_fields = ['full_address', 'street', 'city', 'xeno_id']
    readonly_fields = ['id', 'created_at', 'updated_at', 'establishments_count']


class EstablishmentMembershipInline(admin.TabularInline):
    model = EstablishmentMembership
    extra = 0
    readonly_fields = ['created_at']
    autocomplete_fields = ['profile']


@admin.register(Establishment)
class EstablishmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'organization_type', 'category', 'world_object', 'owner', 'is_online', 'is_verified', 'is_active', 'views_count', 'created_at']
    list_filter = ['organization_type', 'is_online', 'category', 'is_verified', 'is_active', 'created_at']
    search_fields = ['name', 'slug', 'description', 'world_object__full_address', 'owner__local_name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'views_count']
    autocomplete_fields = ['owner', 'world_object', 'category', 'parent']
    filter_horizontal = ['items']
    inlines = [EstablishmentMembershipInline]


@admin.register(EstablishmentReview)
class EstablishmentReviewAdmin(admin.ModelAdmin):
    list_display = ['author', 'establishment', 'rating', 'wot_count_snapshot', 'created_at']
    list_filter = ['rating']
    search_fields = ['author__local_name', 'establishment__name', 'text']
    raw_id_fields = ['author', 'establishment']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(CalendarDate)
class CalendarDateAdmin(admin.ModelAdmin):
    list_display = ['agency', 'service_id', 'date', 'exception_type']
    list_filter = ['agency', 'exception_type', 'date']
    search_fields = ['service_id']


class EventParticipantInline(admin.TabularInline):
    model = EventParticipant
    extra = 0
    fields = ['profile', 'status']
    readonly_fields = ['id', 'created_at']
    autocomplete_fields = ['profile']


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'organizer', 'event_type', 'status', 'starts_at', 'ends_at',
                    'location_name', 'max_participants', 'participants_count', 'created_at']
    list_filter = ['event_type', 'status', 'starts_at', 'created_at']
    search_fields = ['title', 'description', 'organizer__local_name', 'location_name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'participants_count', 'views_count']
    autocomplete_fields = ['organizer', 'world_object', 'category']
    inlines = [EventParticipantInline]


@admin.register(EventParticipant)
class EventParticipantAdmin(admin.ModelAdmin):
    list_display = ['profile', 'event', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['profile__local_name', 'event__title']
    readonly_fields = ['id', 'created_at', 'updated_at']
