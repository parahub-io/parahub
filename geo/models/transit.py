from django.contrib.gis.db import models
from core.models import ULIDModel
from identity.models import Profile
from market.models import Item
from .places import Place


class TransitDataSource(ULIDModel):
    """Registry of transit data sources (GTFS feeds, CSV imports, etc.)."""
    class Format(models.TextChoices):
        GTFS = 'gtfs', 'GTFS'
        CSV = 'csv', 'CSV'
        XML = 'xml', 'XML'
        GEOJSON = 'geojson', 'GeoJSON'
        MANAGED = 'managed', 'Managed'

    class RtKind(models.TextChoices):
        # How this feed delivers realtime — distinct from the static GTFS format.
        # The "static + RT vehicle GPS" feed policy assumes GPS; metro/rail feeds
        # publish arrival predictions instead (no GPS in a tunnel), and are valid too.
        GPS = 'gps', 'GPS vehicle positions'        # GTFS-RT VehiclePositions (rt_vehicles_url)
        ARRIVALS = 'arrivals', 'Arrival predictions'  # bespoke arrival-time API, no GPS (e.g. Metro de Lisboa)
        NONE = 'none', 'No realtime'                  # static only

    name = models.CharField(max_length=255, help_text="Human-readable source name")
    url = models.TextField(blank=True, help_text="Static data download URL(s), one per line for multi-feed sources")
    format = models.CharField(max_length=20, choices=Format.choices, default='gtfs')
    rt_vehicles_url = models.TextField(blank=True, help_text="RT vehicle positions URL(s), one per line")
    rt_alerts_url = models.TextField(blank=True, help_text="RT service alerts URL(s), one per line")
    rt_headers = models.JSONField(null=True, blank=True, help_text="Custom HTTP headers for RT requests (e.g. API keys)")
    is_active = models.BooleanField(default=True)
    last_imported_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    slug = models.SlugField(max_length=100, blank=True, default='', help_text="URL slug for GTFS relay")
    motis_input_name = models.CharField(max_length=64, blank=True, default='', help_text="Filename inside /opt/motis/input/ to sync the fresh GTFS ZIP to. Empty = not synced to MOTIS.")
    last_import_hash = models.CharField(max_length=64, blank=True, help_text="SHA256 of last downloaded ZIP")
    last_import_stats = models.JSONField(null=True, blank=True, help_text="Statistics of last import run")
    rt_interval = models.PositiveSmallIntegerField(default=30, help_text="RT poll interval in seconds")
    rt_kind = models.CharField(
        max_length=16, choices=RtKind.choices, default=RtKind.GPS,
        help_text="Realtime delivery model: gps=GTFS-RT VehiclePositions (default), "
                  "arrivals=bespoke arrival-time API with no GPS (metro/rail), none=static only",
    )
    generate_shapes = models.BooleanField(
        default=False,
        help_text="Synthesize shapes.txt with pfaedle (map-match trips onto OSM track "
                  "geometry) during update when the upstream feed ships none. For rail "
                  "feeds whose trips reference shape_id but omit shapes.txt (e.g. CP).",
    )

    def __str__(self):
        return self.name

class Agency(ULIDModel):
    establishment = models.OneToOneField('Establishment', on_delete=models.CASCADE, null=True, blank=True, related_name="transit_profile")
    data_source = models.ForeignKey(TransitDataSource, on_delete=models.CASCADE, null=True, blank=True, related_name="agencies")
    owner = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name="owned_agencies", help_text="Profile that manages this agency via UI")
    is_managed = models.BooleanField(default=False, help_text="True = created via UI, not GTFS import")
    source_id = models.CharField(max_length=100, blank=True, db_index=True, help_text="External ID from data source (e.g. GTFS agency_id)")
    name = models.CharField(max_length=255, blank=True)
    url = models.URLField(blank=True)
    timezone = models.CharField(max_length=50)
    lang = models.CharField(max_length=10)

    class Meta:
        indexes = [
            models.Index(fields=['source_id']),
        ]

    def __str__(self):
        return self.name or self.source_id or str(self.id)[:8]

class StopGroup(ULIDModel):
    """
    Virtual stop: display-level grouping of physically coincident Stop records
    (same-feed direction poles, cross-feed duplicates). Physical stops are never
    mutated — this is a derived layer recomputed idempotently after GTFS imports
    (recompute_stop_groups). No member is "primary": location is the centroid.
    """
    name = models.CharField(max_length=255)
    location = models.PointField(srid=4326, geography=True, help_text="Centroid of member unit roots")
    place = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True, related_name='stop_groups')
    member_count = models.PositiveSmallIntegerField(default=0, help_text="Physical platforms/poles (location_type=0) in the group")

    def __str__(self):
        return f"{self.name} ×{self.member_count}"

class Stop(ULIDModel):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="stops")
    place = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True, related_name="stops", help_text="Cached: place this stop belongs to")
    source_id = models.CharField(max_length=100, blank=True, db_index=True, help_text="External ID from data source")
    slug = models.SlugField(max_length=150, blank=True, default='', db_index=True)
    name = models.CharField(max_length=255)
    tts_name = models.CharField(max_length=255, blank=True, default='', help_text="GTFS tts_stop_name: unabbreviated form for text-to-speech (driver-mode announcements, screen readers). Empty when the feed omits it.")
    location = models.PointField(srid=4326, geography=True)
    location_type = models.SmallIntegerField(default=0, help_text="0=stop/platform, 1=station")
    parent_station = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='child_stops')
    group = models.ForeignKey(StopGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='stops', db_index=True, help_text="Virtual stop this physical stop belongs to (recomputed, never authored)")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['agency', 'source_id'], name='unique_agency_stop'),
            models.UniqueConstraint(fields=['place', 'slug'], name='unique_place_stop_slug',
                                    condition=models.Q(place__isnull=False) & ~models.Q(slug='')),
        ]

class Route(ULIDModel):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="routes")
    place = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True, related_name="routes")
    places = models.ManyToManyField(Place, blank=True, related_name="m2m_routes")
    source_id = models.CharField(max_length=100, blank=True, db_index=True, help_text="External ID from data source")
    slug = models.SlugField(max_length=100, blank=True, default='', db_index=True)
    short_name = models.CharField(max_length=50)
    long_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    route_type = models.SmallIntegerField(default=3, help_text="0=tram, 1=metro, 2=rail, 3=bus, 4=ferry, 7=funicular")
    route_color = models.CharField(max_length=6, blank=True, help_text="Hex color without #")
    route_text_color = models.CharField(max_length=6, blank=True)
    # Line grouping (non-standard GTFS extension, e.g. Carris Metropolitana routes.txt).
    # Multiple Route variants (path patterns) of the same public line share line_id.
    # Blank when the feed has no line concept → route stands alone.
    line_id = models.CharField(max_length=100, blank=True, db_index=True, help_text="External line ID grouping route variants (GTFS line_id ext)")
    line_long_name = models.CharField(max_length=255, blank=True, help_text="Public line name (GTFS line_long_name ext)")
    path_type = models.SmallIntegerField(default=0, help_text="Variant order within line (GTFS path_type ext); lowest = canonical")
    geometry = models.LineStringField(srid=4326, geography=True, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['agency', 'source_id'], name='unique_agency_route'),
            models.UniqueConstraint(fields=['place', 'slug'], name='unique_place_route_slug',
                                    condition=models.Q(place__isnull=False) & ~models.Q(slug='')),
        ]

class Shape(ULIDModel):
    """Deduplicated trip shape geometry. One Shape can be shared by many trips."""
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="shapes")
    source_id = models.CharField(max_length=100, blank=True, db_index=True, help_text="GTFS shape_id")
    geometry = models.LineStringField(srid=4326, geography=True)
    length_m = models.FloatField(default=0, help_text="Precomputed ST_Length(geography)")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['agency', 'source_id'], name='unique_agency_shape',
                condition=~models.Q(source_id=''),
            ),
        ]

class Trip(ULIDModel):
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="trips")
    source_id = models.CharField(max_length=100, blank=True, db_index=True, help_text="External ID from data source")
    headsign = models.CharField(max_length=255)
    service_id = models.CharField(max_length=100, db_index=True, blank=True)
    direction_id = models.SmallIntegerField(null=True, blank=True, help_text="0 or 1")
    shape_ref = models.ForeignKey(Shape, on_delete=models.SET_NULL, null=True, blank=True, related_name="trips")
    vehicle_item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'spec_type': 'VEHICLE'})

    class Meta:
        indexes = [
            models.Index(fields=['route', 'direction_id']),
            models.Index(fields=['service_id', 'route']),
        ]

class RouteStop(ULIDModel):
    """Stop sequence on a route."""
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="route_stops")
    stop = models.ForeignKey(Stop, on_delete=models.CASCADE, related_name="route_stops")
    sequence = models.PositiveSmallIntegerField()
    direction_id = models.SmallIntegerField(null=True, blank=True, help_text="0=outbound, 1=inbound, NULL=legacy/undirected")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['route', 'stop', 'direction_id'], name='unique_routestop_dir'),
        ]
        ordering = ['sequence']
        indexes = [
            models.Index(fields=['stop', 'direction_id', 'sequence']),
            models.Index(fields=['route', 'direction_id', 'sequence']),
        ]

class Vehicle(ULIDModel):
    """Transportation vehicle."""
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="vehicles")
    vehicle_id = models.CharField(max_length=100)
    license_plate = models.CharField(max_length=20, blank=True)
    model = models.CharField(max_length=100, blank=True)
    capacity = models.PositiveSmallIntegerField(null=True, blank=True)
    current_location = models.PointField(srid=4326, geography=True, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('agency', 'vehicle_id')

class StopTime(models.Model):
    # Natural composite PK — NO synthetic `id` column. StopTime is never looked
    # up by a surrogate key (every read filters by trip/stop/departure_time +
    # stop_sequence), so the default BigAutoField PK was pure overhead: ~1.4 GB
    # of index on 41M rows. (trip, stop_sequence) is unique by GTFS spec (a trip
    # visits each sequence once) and was already the unique_together — promoting
    # it to PK reuses that existing index instead of carrying a second one.
    pk = models.CompositePrimaryKey("trip", "stop_sequence")
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="stop_times")
    # db_index=False: a plain (stop_id) btree is fully covered by the
    # (stop, departure_time) composite in Meta.indexes — the auto FK index was
    # ~900 MB of duplicate on 45M rows.
    stop = models.ForeignKey(Stop, on_delete=models.CASCADE, related_name="stop_times", db_index=False)
    arrival_time = models.TimeField()
    departure_time = models.TimeField()
    # GTFS seconds from service-day start, NOT wrapped — can exceed 86400 for
    # night service (e.g. 25:20:00 → 91200). departure_time is the same value
    # %24 (TimeField can't hold ≥24:00), which destroys the day-offset; this
    # field preserves it so night routes order/display correctly across
    # midnight. NULL on imports before 2026-06-13 — readers degrade to
    # departure_time (old wrapped behaviour) until the feed is re-imported.
    departure_secs = models.PositiveIntegerField(null=True, blank=True)
    stop_sequence = models.PositiveSmallIntegerField()

    class Meta:
        # The (trip, stop_sequence) UNIQUE constraint is retained as the table's
        # natural key/index (the composite PK is an ORM-level construct; we keep
        # the existing DB unique index rather than rebuild it as a PRIMARY KEY —
        # functionally identical, and avoids a 4.2 GB index rebuild + long lock
        # on the live 41M-row table). Dropping only the `id` column reclaims its
        # ~1.4 GB index.
        unique_together = ('trip', 'stop_sequence')
        ordering = ['stop_sequence']
        indexes = [
            models.Index(fields=['stop', 'departure_time']),
        ]

class CalendarDate(models.Model):
    """GTFS calendar_dates.txt — service exceptions by date."""
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="calendar_dates")
    service_id = models.CharField(max_length=100, db_index=True)
    date = models.DateField(db_index=True)
    exception_type = models.SmallIntegerField(help_text="1=added, 2=removed")

    class Meta:
        unique_together = ('agency', 'service_id', 'date')
        indexes = [
            models.Index(fields=['agency', 'date', 'exception_type']),
        ]

# ===== Transit Real-Time History (TimescaleDB) =====

class VehiclePositionHistory(models.Model):
    """
    Time-series vehicle position history (TimescaleDB hypertable).
    Uses BigAutoField PK (not ULID) — optimized for time-series inserts.
    Float fields (not PointField) for better TimescaleDB compression.
    """
    # Hypertable conversion + the DESC time_idx exist only in the prod DB
    # (managed outside migrations; they predate the migration reset). Fresh DBs
    # get a plain table — fine for tests.
    time = models.DateTimeField(db_index=True)
    # No FK index at all, deliberately: the plain btree and later the
    # (ds, vehicle, time) composite were both dropped as unused (~1.2 GB) —
    # hot reads go through Redis, the table is write-mostly.
    data_source = models.ForeignKey(TransitDataSource, on_delete=models.CASCADE, related_name='position_history', db_index=False)
    vehicle_id = models.CharField(max_length=100, help_text="External vehicle ID from feed")
    latitude = models.FloatField()
    longitude = models.FloatField()
    bearing = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True, help_text="Speed in km/h")
    route_source_id = models.CharField(max_length=100, blank=True)
    stop_source_id = models.CharField(max_length=100, blank=True)
    direction_id = models.SmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=30, blank=True)

    class Meta:
        db_table = 'geo_vehiclepositionhistory'

    def __str__(self):
        return f"{self.vehicle_id} @ {self.time}"

class FeedHealthSample(models.Model):
    """Periodic GTFS-RT feed liveness sample — durable downtime evidence.

    Written by `sample_feed_health` every ~60s for every active GPS feed. Unlike
    Kuma (records only *when* a monitor was down, with a truncated msg that drops
    the cause) this stores the failure CATEGORY separately at write-time, so a
    complaint report (`report_feed_health`) can split downtime into "server
    unreachable" (fetch failed) vs "stale data" (frozen upstream serving HTTP 200)
    — the two distinct operator faults a reclamação must distinguish. Plain
    indexed table (not a hypertable): ~13K rows/day across all feeds, kept
    long-term for legal evidence. See PK/transit-system.md § Feed health log and
    PK/complaints-workflow.md. BigAutoField PK (time-series, not an API object).
    """
    class Status(models.TextChoices):
        OK = 'ok', 'OK (serving live data)'
        IDLE = 'idle', 'Idle (no vehicles — off-service)'
        STALE = 'stale', 'Stale (frozen data despite HTTP 200)'
        UNREACHABLE = 'unreachable', 'Unreachable (fetch failed)'

    time = models.DateTimeField(db_index=True)
    data_source = models.ForeignKey(TransitDataSource, on_delete=models.CASCADE, related_name='health_samples', db_index=False)
    status = models.CharField(max_length=12, choices=Status.choices)
    fresh_count = models.PositiveIntegerField(default=0, help_text="Vehicles fresher than 180s (transit:members)")
    total_served = models.PositiveIntegerField(default=0, help_text="Vehicles in the unfiltered feed mirror")
    freshest_age_s = models.PositiveIntegerField(null=True, blank=True, help_text="Age of the freshest fix, seconds")
    detail = models.CharField(max_length=300, blank=True, help_text="last_error text (unreachable) or note")

    class Meta:
        db_table = 'geo_feedhealthsample'
        indexes = [models.Index(fields=['data_source', 'time'], name='feedhealth_ds_time_idx')]

    def __str__(self):
        return f"{self.data_source_id} {self.status} @ {self.time}"

class DriverShift(ULIDModel):
    """Driver-sourced GPS broadcasting shift.

    A driver opens /driver, selects a route, and starts broadcasting GPS
    from their browser/tablet.  Hot path (positions) goes through Redis only;
    this model records shift metadata for audit.
    """

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        ENDED = 'ENDED', 'Ended'

    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='driver_shifts',
    )
    route = models.ForeignKey(
        Route, on_delete=models.CASCADE, related_name='driver_shifts',
    )
    data_source = models.ForeignKey(
        TransitDataSource, on_delete=models.CASCADE, related_name='driver_shifts',
    )
    direction_id = models.SmallIntegerField(default=0)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE,
    )
    vehicle_id = models.CharField(
        max_length=50, help_text="Unique vehicle ID for transit pipeline",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    position_count = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['profile', 'status']),
            models.Index(fields=['route', 'status']),
        ]

    def __str__(self):
        return f"{self.profile.local_name} → {self.route.short_name} ({self.status})"
