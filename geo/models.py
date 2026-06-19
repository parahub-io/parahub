from django.contrib.gis.db import models
from django.core.validators import RegexValidator
from core.models import ULIDModel
from identity.models import Profile
from market.models import Item
from taxonomy.models import Category


class Place(ULIDModel):
    """Geographic place (city, region, etc)."""
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=200, unique=True, blank=True, default='')
    country_code = models.CharField(max_length=2, help_text="ISO 3166-1 alpha-2 country code")
    wof_id = models.BigIntegerField(null=True, unique=True, help_text="Who's On First ID")
    geometry = models.MultiPolygonField(srid=4326, geography=True, null=True, blank=True)
    center_point = models.PointField(srid=4326, geography=True, null=True, blank=True, spatial_index=False)
    population = models.IntegerField(null=True, blank=True)
    place_type = models.CharField(max_length=20, default="city", help_text="Type of place: city, region, country")
    parent_place = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='child_places')
    sort_order = models.PositiveSmallIntegerField(default=0)
    transit_stops_count = models.PositiveIntegerField(default=0, help_text="Cached: stops within geometry")
    transit_routes_count = models.PositiveIntegerField(default=0, help_text="Cached: routes within geometry")

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return f"{self.name} ({self.country_code})"

class OpenSkyMission(ULIDModel):
    """
    Aerial imagery mission for OpenSky layer.

    Workflow (single file):
    1. User uploads ZIP with drone photos → status=QUEUED
    2. systemd timer runs process_opensky_queue → status=PROCESSING
    3. ODM + gdal2tiles → status=PUBLISHED or FAILED

    Workflow (multi-file for better stitching):
    1. User uploads first ZIP → status=UPLOADING
    2. User uploads more ZIPs (appended to same mission)
    3. User clicks "Finalize" → status=QUEUED
    4. Processing continues as above

    Legacy statuses (AVAILABLE, ASSIGNED) are for future bounty system.
    """
    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available (Bounty)'
        ASSIGNED = 'ASSIGNED', 'Assigned to Pilot'
        UPLOADING = 'UPLOADING', 'Uploading (multi-file)'
        QUEUED = 'QUEUED', 'Queued for Processing'
        PROCESSING = 'PROCESSING', 'Data Processing'
        PUBLISHED = 'PUBLISHED', 'Published'
        FAILED = 'FAILED', 'Failed'

    class MeshStatus(models.TextChoices):
        NONE = 'NONE', 'No mesh'
        MESH_QUEUED = 'MESH_QUEUED', 'Mesh queued'
        MESH_PROCESSING = 'MESH_PROCESSING', 'Mesh processing'
        MESH_READY = 'MESH_READY', 'Mesh ready'
        MESH_FAILED = 'MESH_FAILED', 'Mesh failed'

    # Area covered by this mission (calculated from tiles after processing)
    area = models.PolygonField(srid=4326, geography=True, null=True, blank=True)

    status = models.CharField(max_length=15, choices=Status.choices, default=Status.QUEUED, db_index=True)
    pilot = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="opensky_missions")

    # Split-merge consolidation (see PK/opensky-system.md § Consolidation).
    # A consolidation is itself an OpenSkyMission row (is_consolidation=True) whose
    # tiles are the joint ODM split-merge of its member missions' photos — one
    # seamless ortho that overrides the members in latest/. Members keep their own
    # tiles/orthos (for rollback) and point back via superseded_by.
    is_consolidation = models.BooleanField(default=False, db_index=True,
        help_text="True if this row is a split-merge super-tile, not a single flight")
    # SET_NULL (NOT CASCADE): deleting the consolidation must free its members,
    # never delete them. rebuild_tiles_after_deletion heals latest/ from members.
    superseded_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='superseded_members',
        help_text="If set, this mission is a member of a consolidation and its tiles are overridden by it")

    # Mission metadata
    name = models.CharField(max_length=255, blank=True, help_text="Optional mission name")

    # Source photos stats
    source_photos_count = models.IntegerField(default=0)
    source_photos_size_mb = models.FloatField(default=0)

    # Per-direction photo counts (classified from gimbal pitch + yaw EXIF/XMP).
    # Keys: nadir, n, e, s, w, unknown. Values: photo counts.
    # Used for coverage pills UI. Threshold for "covered" = 50 photos per direction.
    direction_counts = models.JSONField(default=dict, blank=True)

    # Generated tiles stats
    tiles_count = models.IntegerField(default=0)
    tiles_size_mb = models.FloatField(default=0)
    min_zoom = models.IntegerField(default=13)
    max_zoom = models.IntegerField(default=23)

    # Center point for map display
    center_lat = models.FloatField(null=True, blank=True)
    center_lng = models.FloatField(null=True, blank=True)

    # Reverse-geocoded place (computed once at publish via local Pelias).
    # The card "Location" readout reads these stored fields; the client-side
    # lookup is only a fallback for missions not yet backfilled.
    place_label = models.CharField(max_length=120, blank=True, default='', help_text="Area name (parish/municipality) for the mission card readout")
    place_region = models.CharField(max_length=120, blank=True, default='', help_text="Region · country subtitle for the mission card readout")

    # Web Mercator tile coordinates (Z/X/Y, default Z17 ~305×240m)
    tile_z = models.SmallIntegerField(null=True, blank=True, default=17)
    tile_x = models.IntegerField(null=True, blank=True)
    tile_y = models.IntegerField(null=True, blank=True)

    # Processing sub-step (for real-time progress display)
    class ProcessingStep(models.TextChoices):
        ODM = 'odm', 'Running ODM'
        REPROJECTION = 'reprojection', 'Reprojecting'
        ALIGNMENT = 'alignment', 'Aligning'
        TILING = 'tiling', 'Generating tiles'
        MESH = 'mesh', 'Generating 3D mesh'
        FINALIZING = 'finalizing', 'Finalizing'

    processing_step = models.CharField(max_length=20, choices=ProcessingStep.choices, default='', blank=True)

    # Timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)
    captured_at = models.DateTimeField(null=True, blank=True, help_text="Earliest photo EXIF DateTimeOriginal")
    processing_started_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    # Error tracking
    error_message = models.TextField(blank=True, help_text="Error details if status=FAILED")

    # 3D Mesh generation
    mesh_status = models.CharField(max_length=15, choices=MeshStatus.choices, default=MeshStatus.NONE, db_index=True)
    mesh_size_mb = models.FloatField(default=0, help_text="ZIP archive size (OBJ+MTL+textures)")
    mesh_glb_size_mb = models.FloatField(default=0, help_text="GLB file size for browser viewer")
    mesh_error_message = models.TextField(blank=True, help_text="Error details if mesh_status=MESH_FAILED")
    mesh_requested_at = models.DateTimeField(null=True, blank=True)
    mesh_completed_at = models.DateTimeField(null=True, blank=True)

    # ODM reconstruction origin (UTM coords from odm_georeferencing/coords.txt)
    # Stored for 3D Tiles georeferencing: this is the (0,0,0) of the local OBJ coordinate system
    odm_origin = models.JSONField(null=True, blank=True, help_text="ODM origin {x, y, z} in UTM meters + EPSG code")

    # Cumulative similarity correction applied by the Phase-2 similarity BA
    # (composition of all applied deltas, about the ortho centroid, EPSG:3857).
    # Bookkeeping/debug only — the solver works in DELTA space against fresh
    # edges; nothing re-derives state from these. See realign_opensky_similarity.
    corr_ln_scale = models.FloatField(default=0.0, help_text="ln(scale) correction last applied (0 = none)")
    corr_rotation_deg = models.FloatField(default=0.0, help_text="Rotation correction last applied (deg, 0 = none)")
    corr_dx_m = models.FloatField(default=0.0, help_text="X translation correction last applied (m, EPSG:3857)")
    corr_dy_m = models.FloatField(default=0.0, help_text="Y translation correction last applied (m, EPSG:3857)")

    # When the saved ortho's georeference last changed physically (publish,
    # satellite/consensus shift, similarity warp). Pose edges measured BEFORE
    # this moment describe a frame that no longer exists on disk — the Phase-2
    # solver must ignore them (see § frame freshness in realign_opensky_similarity).
    georef_changed_at = models.DateTimeField(null=True, blank=True,
                                             help_text="Last physical georef change of the saved ortho")

    # Processing options
    satellite_align = models.BooleanField(default=False, help_text="Align to satellite imagery (ESRI) during processing")

    # Licensing (CC BY-SA 4.0): uploaded imagery + all derived ortho/mesh/tiles.
    # consent recorded at upload; pilot FK records who consented.
    license = models.CharField(max_length=32, default='CC-BY-SA-4.0', help_text="License of uploaded imagery + derived ortho/mesh/tiles")
    license_consent_at = models.DateTimeField(null=True, blank=True, help_text="When the pilot accepted the imagery license terms at upload")

    # Legacy fields (for future bounty system)
    reputation_reward = models.FloatField(default=1.0)
    published_data_cid = models.CharField(max_length=255, blank=True, help_text="IPFS CID for decentralized storage")

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['status', 'uploaded_at']),
            models.Index(fields=['pilot', 'status']),
            models.Index(fields=['tile_z', 'tile_x', 'tile_y']),
        ]

    def __str__(self):
        return f"OpenSky {self.id[:8]} ({self.status})"


class OpenSkyTileLayer(models.Model):
    """
    Tracks which missions contribute to each tile in latest/.
    Used for rebuilding tiles when a mission is deleted.
    """
    z = models.IntegerField()
    x = models.IntegerField()
    y = models.IntegerField()
    mission = models.ForeignKey(OpenSkyMission, on_delete=models.CASCADE, related_name='tile_layers')
    layer_order = models.IntegerField(help_text="Order in compositing stack (higher = on top)")

    class Meta:
        unique_together = ('z', 'x', 'y', 'mission')
        indexes = [
            models.Index(fields=['z', 'x', 'y']),
            models.Index(fields=['mission']),
        ]

    def __str__(self):
        return f"Tile {self.z}/{self.x}/{self.y} <- Mission {self.mission_id[:8]}"


class OpenSkyConsolidationMember(models.Model):
    """
    Membership of a single-flight mission in a split-merge consolidation.

    The consolidation and each member are both OpenSkyMission rows; this through
    table records which flights were jointly reconstructed, plus the collision-safe
    image filename ``prefix`` (e.g. ``m00_``) used when pooling photos into one ODM
    project. ``order`` makes prefix assignment deterministic across re-runs.
    """
    consolidation = models.ForeignKey(OpenSkyMission, on_delete=models.CASCADE, related_name='members')
    member = models.ForeignKey(OpenSkyMission, on_delete=models.CASCADE, related_name='consolidation_links')
    prefix = models.CharField(max_length=16, help_text="Image filename prefix for this member in the joint ODM project")
    order = models.IntegerField(default=0)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('consolidation', 'member')
        ordering = ['order']
        indexes = [
            models.Index(fields=['consolidation']),
            models.Index(fields=['member']),
        ]

    def __str__(self):
        return f"{self.consolidation_id[:8]} <- {self.member_id[:8]} ({self.prefix})"


class OpenSkyPoseEdge(models.Model):
    """
    Pose graph edge — one observation relating two missions or one mission to
    the absolute reference frame.

    Edges are immutable raw data. Mission positions are derived from edges via
    consensus (Phase 1) or regional bundle adjustment (Phase 2). See
    PK/opensky-system.md § Pose Graph Architecture.
    """
    class EdgeType(models.TextChoices):
        ORB_PAIR = 'orb_pair', 'ORB feature match vs another mission'
        SATELLITE_ANCHOR = 'satellite_anchor', 'ECC alignment vs satellite imagery (absolute anchor)'

    mission_a = models.ForeignKey(
        OpenSkyMission, on_delete=models.CASCADE, related_name='pose_edges_outgoing',
        help_text="Mission whose position is being measured (perspective).",
    )
    mission_b = models.ForeignKey(
        OpenSkyMission, on_delete=models.CASCADE, null=True, blank=True,
        related_name='pose_edges_incoming',
        help_text="Reference neighbor. NULL for SATELLITE_ANCHOR (absolute frame).",
    )
    edge_type = models.CharField(max_length=20, choices=EdgeType.choices, db_index=True)
    dx_m = models.FloatField(help_text="X shift (m, EPSG:3857) to apply to mission_a to align with mission_b (or absolute frame)")
    dy_m = models.FloatField(help_text="Y shift (m, EPSG:3857) to apply to mission_a to align with mission_b (or absolute frame)")
    # Similarity components of the ORB measurement (Phase 2 similarity BA).
    # rel_scale = size(mission_b)/size(mission_a); rel_rotation_deg = map-frame
    # rotation of mission_a onto mission_b. Defaults make legacy translation-only
    # edges valid similarities (s=1, θ=0). SATELLITE_ANCHOR observes neither.
    rel_scale = models.FloatField(default=1.0, help_text="Relative scale s_ij of mission_a vs mission_b (ORB only)")
    rel_rotation_deg = models.FloatField(default=0.0, help_text="Relative rotation (deg, map frame) of mission_a vs mission_b (ORB only)")
    # Where dx/dy is referenced: the (west, north) corner of the measured
    # intersection window (= pixel (0,0) of the ORB affine), EPSG:3857. The
    # Phase-2 lever-arm needs this exact point; NULL (legacy edges / anchors)
    # falls back to the nominal Z17-cell intersection corner (~0.2-0.5m error).
    ref_x_3857 = models.FloatField(null=True, blank=True, help_text="X of the translation reference point (m, EPSG:3857)")
    ref_y_3857 = models.FloatField(null=True, blank=True, help_text="Y of the translation reference point (m, EPSG:3857)")
    weight = models.FloatField(default=1.0, help_text="Solver weight (e.g. overlap area for ORB)")
    confidence = models.FloatField(default=1.0, help_text="Observation quality (RANSAC inlier ratio for ORB, ECC correlation for satellite)")
    overlap_area_m2 = models.FloatField(default=0, help_text="Geographic intersection area (ORB only)")
    measured_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['mission_a', 'edge_type']),
            models.Index(fields=['mission_b', 'edge_type']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['mission_a', 'mission_b', 'edge_type'],
                name='unique_pose_edge',
            ),
        ]

    def __str__(self):
        b = self.mission_b_id[:8] if self.mission_b_id else 'SAT'
        return f"PoseEdge {self.mission_a_id[:8]} → {b} [{self.edge_type}] ({self.dx_m:+.2f}, {self.dy_m:+.2f})"


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
    stop = models.ForeignKey(Stop, on_delete=models.CASCADE, related_name="stop_times")
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


# ===== Directory System (2GIS-like) =====

class WorldObject(ULIDModel):
    """Any real-world entity that needs a ULID for interactions.

    Absorbs the former Building model. Represents buildings, parks, POIs, or any
    OSM/external entity. Lifecycle: get_or_create(xeno_source, xeno_id) on first interaction.
    """

    # External identity (how we found it)
    xeno_source = models.CharField(max_length=20, blank=True, db_index=True,
                                    help_text="Source system: osm, traccar, ha, external")
    xeno_id = models.CharField(max_length=100, blank=True, db_index=True,
                                help_text="External ID: way/1168594818, node/123456")

    # Geo
    location = models.PointField(srid=4326, geography=True, null=True, blank=True)

    # Geometry (absorbed from Building)
    geometry = models.PolygonField(srid=4326, geography=True, null=True, blank=True,
                                   help_text="Footprint polygon (buildings, parks, etc.)")

    # Address (absorbed from Building)
    country = models.CharField(max_length=2, blank=True, help_text="ISO 3166-1 alpha-2")
    city = models.CharField(max_length=255, blank=True)
    street = models.CharField(max_length=255, blank=True)
    house_number = models.CharField(max_length=20, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    full_address = models.CharField(max_length=500, blank=True, db_index=True)

    # Building metadata (absorbed from Building)
    building_type = models.CharField(max_length=50, blank=True,
                                      help_text="OSM building type: residential, commercial, etc.")
    levels = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Number of floors")

    # Stats (denormalized)
    establishments_count = models.PositiveIntegerField(default=0)

    # Ownership
    owner = models.ForeignKey('identity.Profile', null=True, blank=True,
                              on_delete=models.SET_NULL, related_name='owned_objects')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['xeno_source', 'xeno_id'],
                condition=~models.Q(xeno_id=''),
                name='unique_xeno_identity'
            )
        ]
        indexes = [
            models.Index(fields=['xeno_source', 'xeno_id']),
            models.Index(fields=['city', 'street']),
            models.Index(fields=['country', 'city']),
        ]

    def __str__(self):
        if self.xeno_source and self.xeno_id:
            return f"WorldObject({self.xeno_source}:{self.xeno_id})"
        return f"WorldObject({self.id})"


class Establishment(ULIDModel):
    """Unified business entity: physical places, online businesses, associations, networks."""

    class OrganizationType(models.TextChoices):
        ASSOCIATION = 'ASSOCIATION', 'Association'
        COOPERATIVE = 'COOPERATIVE', 'Cooperative'
        COMPANY = 'COMPANY', 'Company'
        NGO = 'NGO', 'NGO'
        COMMUNITY = 'COMMUNITY', 'Community'
        CONDOMINIUM = 'CONDOMINIUM', 'Condominium'
        GOVERNMENT = 'GOVERNMENT', 'Government'

    class MemberVisibility(models.TextChoices):
        PUBLIC = 'PUBLIC', 'Public'
        MEMBERS_ONLY = 'MEMBERS_ONLY', 'Members only'
        PRIVATE = 'PRIVATE', 'Private'

    # Ownership & linking
    owner = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="establishments",
                              help_text="Profile that manages this establishment")
    world_object = models.ForeignKey(WorldObject, on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='establishments')

    # Network/franchise structure
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='branches', help_text="Parent establishment for franchises/networks")

    # Basic info
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=100, blank=True, db_index=True,
                            help_text="URL-friendly name (e.g., parahub-associacao)")
    description = models.TextField(blank=True)
    is_online = models.BooleanField(default=False, help_text="Online-only business (no physical location)")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="establishments", help_text="Primary business category")

    # Organization/association fields
    organization_type = models.CharField(max_length=20, choices=OrganizationType.choices, blank=True,
                                         help_text="Type if this is an organization/association")
    legal_entity_id = models.CharField(max_length=50, blank=True, help_text="NIF/NIPC/Tax ID")
    member_visibility = models.CharField(max_length=20, choices=MemberVisibility.choices,
                                         default=MemberVisibility.PUBLIC,
                                         help_text="Who can see members list")
    requires_terms_acceptance = models.BooleanField(default=False,
                                                     help_text="Members must accept terms before joining")
    terms_url = models.CharField(max_length=255, blank=True, help_text="URL to terms/estatutos page")
    terms_content = models.TextField(blank=True, help_text="Full text of terms/estatutos (markdown)")

    # Treasury (participatory budget)
    treasury_enabled = models.BooleanField(default=False, help_text="Enable Treasury for this establishment")
    treasury_eligible_levels = models.JSONField(default=list, blank=True,
                                                 help_text="Membership levels eligible to vote, e.g. ['efetivo','fundador']")

    # Communication
    matrix_room_id = models.CharField(max_length=255, blank=True, help_text="Matrix room ID for org chat")

    # Payments
    ln_address = models.CharField(max_length=255, blank=True, help_text="Lightning address for payments")
    spark_address = models.CharField(max_length=512, blank=True, help_text="Spark address for P2P payments")

    # Membership (M2M through EstablishmentMembership)
    members = models.ManyToManyField(Profile, through='EstablishmentMembership', related_name="member_of_establishments",
                                     blank=True)

    # Location (if not in building, e.g. outdoor kiosk)
    location = models.PointField(srid=4326, geography=True, null=True, blank=True,
                                 help_text="Precise location if different from building center")
    floor = models.CharField(max_length=10, blank=True, help_text="Floor number or range (e.g., '2', '2-3')")
    office_number = models.CharField(max_length=50, blank=True, help_text="Office/suite number")

    # Contact information
    phone = models.CharField(max_length=50, blank=True, validators=[
        RegexValidator(r'^\+?[\d\s\-\(\)]+$', 'Enter valid phone number')
    ])
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)

    # Social media (JSON for extensibility)
    social_links = models.JSONField(default=dict, blank=True, help_text="Social media handles")

    # Opening hours (OSM format)
    opening_hours = models.JSONField(default=dict, blank=True, help_text="Opening hours by day")

    # Media
    logo_url = models.URLField(blank=True, help_text="Organization logo")
    photos = models.JSONField(default=list, blank=True, help_text="Array of photo URLs")

    # Items showcase (products/services)
    items = models.ManyToManyField(Item, blank=True, related_name="establishments",
                                   help_text="Items sold/offered at this establishment")

    # Stats & moderation
    views_count = models.PositiveIntegerField(default=0)
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    rating_count = models.PositiveIntegerField(default=0)
    is_verified = models.BooleanField(default=False, help_text="Verified by moderators")
    is_active = models.BooleanField(default=True, db_index=True)

    # P-Hub (logistics point)
    is_hub = models.BooleanField(default=False, db_index=True, help_text="Enables P-Hub mode (drop-off/pick-up point)")
    hub_capacity = models.PositiveIntegerField(null=True, blank=True, help_text="Max parcels (null = unlimited)")
    hub_max_days = models.PositiveSmallIntegerField(default=14, help_text="Max storage days before expiry")
    hub_storage_fee_daily = models.PositiveIntegerField(default=0, help_text="Storage fee in sats/day (0 = free)")
    hub_accepted_sizes = models.JSONField(default=list, blank=True, help_text='Accepted sizes: ["S","M","L","XL"]')
    hub_instructions = models.TextField(blank=True, help_text="Pickup/dropoff instructions (e.g. 'enter from backyard')")

    # Extensible attributes (EAV pattern for future)
    attributes = models.JSONField(default=dict, blank=True,
                                  help_text="Custom attributes (parking, wifi, accessibility, etc)")

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['slug']),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['world_object', 'is_active']),
            models.Index(fields=['organization_type', 'is_active']),
            models.Index(fields=['owner', 'is_active']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['slug'], name='unique_establishment_slug',
                condition=~models.Q(slug=''),
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.world_object.full_address if self.world_object else self.slug or 'no address'})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_slug()
        super().save(*args, **kwargs)

    def _generate_slug(self):
        from django.utils.text import slugify
        base = slugify(self.name)[:80] or self.id[:8].lower()
        candidate = base
        counter = 2
        while Establishment.objects.filter(slug=candidate).exclude(id=self.id).exists():
            suffix = str(counter)
            candidate = f"{base[:80 - len(suffix) - 1]}-{suffix}"
            counter += 1
        return candidate


class EstablishmentMembership(models.Model):
    """Membership in an establishment/organization."""

    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        ADMIN = 'ADMIN', 'Admin'
        MEMBER = 'MEMBER', 'Member'
        EMPLOYEE = 'EMPLOYEE', 'Employee'
        CONTRACTOR = 'CONTRACTOR', 'Contractor'

    class MembershipLevel(models.TextChoices):
        APOIANTE = 'apoiante', 'Associado Apoiante'
        EFETIVO = 'efetivo', 'Associado Efetivo'
        FUNDADOR = 'fundador', 'Associado Fundador'

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='establishment_memberships')
    establishment = models.ForeignKey(Establishment, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    membership_level = models.CharField(
        max_length=20, choices=MembershipLevel.choices, blank=True, null=True,
        help_text="Membership level for associations (apoiante, efetivo, fundador)"
    )
    terms_accepted_at = models.DateTimeField(null=True, blank=True,
                                              help_text="When member accepted terms")
    employment_start_date = models.DateField(null=True, blank=True)
    employment_end_date = models.DateField(null=True, blank=True)

    position_title = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Custom position title (e.g. Vice-Presidente, Secretário) — shown instead of generic role label"
    )
    is_treasurer = models.BooleanField(
        default=False,
        help_text="Designated treasurer — wallet receives establishment payments"
    )
    is_auditor = models.BooleanField(
        default=False,
        help_text="Designated auditor (Fiscal Único) — read-only access to all financial data"
    )

    class Meta:
        unique_together = ('profile', 'establishment')
        indexes = [
            models.Index(fields=['establishment', 'role']),
            models.Index(fields=['profile', 'created_at']),
        ]

    def __str__(self):
        return f"{self.profile.hna} → {self.establishment.name} ({self.role})"


class EstablishmentReview(ULIDModel):
    """User review and star rating for an establishment."""
    establishment = models.ForeignKey(Establishment, on_delete=models.CASCADE, related_name='reviews')
    author = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='establishment_reviews')
    rating = models.SmallIntegerField()  # 1-5
    text = models.TextField(blank=True)
    wot_count_snapshot = models.PositiveSmallIntegerField(default=0)  # verifications at review time
    owner_reply = models.TextField(blank=True)

    class Meta:
        unique_together = ('establishment', 'author')
        indexes = [
            models.Index(fields=['establishment', '-created_at']),
        ]

    def __str__(self):
        return f"{self.author.hna} → {self.establishment.name} ({self.rating}★)"


# ===== Condominium System =====

class CondominiumFraction(ULIDModel):
    """Individual fraction (apartment, garage, etc.) within a condominium."""

    class FractionType(models.TextChoices):
        APARTMENT = 'APARTMENT', 'Apartment'
        GARAGE = 'GARAGE', 'Garage'
        STORAGE = 'STORAGE', 'Storage'
        COMMERCIAL = 'COMMERCIAL', 'Commercial'
        OTHER = 'OTHER', 'Other'

    establishment = models.ForeignKey(Establishment, on_delete=models.CASCADE, related_name='fractions')
    identifier = models.CharField(max_length=20, help_text="Fraction identifier, e.g. '1-A', 'R/C Esq', 'Gar 5'")
    description = models.CharField(max_length=255, blank=True, help_text="e.g. 'T2 3rd floor'")
    floor = models.CharField(max_length=10, blank=True)
    fraction_type = models.CharField(max_length=20, choices=FractionType.choices, default=FractionType.APARTMENT)
    permilagem = models.DecimalField(max_digits=7, decimal_places=3, help_text="Ownership share in permilagem (e.g. 87.500)")
    resident = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='condo_fractions', help_text="Current resident (owner or tenant)")
    is_owner = models.BooleanField(default=True, help_text="True if resident is owner, False if tenant")
    invite_token = models.CharField(max_length=64, blank=True, null=True, unique=True,
                                     help_text="Token for inviting a resident to this fraction")

    class Meta:
        unique_together = ('establishment', 'identifier')
        indexes = [
            models.Index(fields=['establishment', 'resident']),
            models.Index(fields=['establishment', 'floor']),
        ]
        ordering = ['floor', 'identifier']

    def __str__(self):
        return f"{self.identifier} ({self.establishment.name})"


class QuotaPayment(ULIDModel):
    """Monthly quota payment record for a condominium fraction."""

    fraction = models.ForeignKey(CondominiumFraction, on_delete=models.CASCADE, related_name='payments')
    month = models.CharField(max_length=7, help_text="Payment month, e.g. '2026-03'")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='confirmed_payments')
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ('fraction', 'month')

    def __str__(self):
        return f"{self.fraction.identifier} — {self.month} ({self.amount})"


# ===== Events System (Community Meetups) =====

class Event(ULIDModel):
    """Community event/meetup."""

    class EventType(models.TextChoices):
        OFFLINE = 'OFFLINE', 'Offline (in-person)'
        ONLINE = 'ONLINE', 'Online (virtual)'
        HYBRID = 'HYBRID', 'Hybrid (both)'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PUBLISHED = 'PUBLISHED', 'Published'
        CANCELLED = 'CANCELLED', 'Cancelled'
        COMPLETED = 'COMPLETED', 'Completed'

    # Organizer
    organizer = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="organized_events",
                                  help_text="Profile that created this event")
    establishment = models.ForeignKey(
        'Establishment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='organized_events',
        help_text="If set, event is posted on behalf of this establishment"
    )

    # Basic info
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="events", help_text="Event category from taxonomy")
    event_type = models.CharField(max_length=10, choices=EventType.choices, default=EventType.OFFLINE)

    # Timing
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(max_length=50, default='UTC', help_text="IANA timezone (e.g., Europe/Moscow)")

    # Location (offline/hybrid) - either building OR arbitrary point
    world_object = models.ForeignKey(WorldObject, on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='events')
    location = models.PointField(srid=4326, geography=True, null=True, blank=True,
                                 help_text="Location if not in a building (park, outdoor venue)")
    location_name = models.CharField(max_length=255, blank=True,
                                     help_text="Human-readable location description")

    # Online info (online/hybrid)
    online_url = models.URLField(blank=True, help_text="Jitsi/Zoom/Google Meet link")

    # Capacity
    max_participants = models.PositiveIntegerField(null=True, blank=True,
                                                   help_text="Maximum participants (null = unlimited)")

    # Matrix chat room
    matrix_room_id = models.CharField(max_length=255, blank=True, db_index=True,
                                      help_text="Matrix room ID for event chat")

    # Media
    cover_image = models.ImageField(upload_to='events/%Y/%m/', blank=True,
                                     help_text="Uploaded cover image")
    cover_image_url = models.URLField(blank=True, help_text="External cover image URL (fallback)")

    # Status
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT, db_index=True)

    # Stats (denormalized for performance)
    participants_count = models.PositiveIntegerField(default=0, help_text="Number of confirmed participants")
    views_count = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'starts_at']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['organizer', 'status']),
        ]
        ordering = ['starts_at']

    def __str__(self):
        return f"{self.title} ({self.starts_at.strftime('%Y-%m-%d %H:%M')})"

    def get_location_display(self):
        """Return human-readable location string."""
        if self.world_object:
            return self.world_object.full_address
        elif self.location_name:
            return self.location_name
        elif self.location:
            return f"{self.location.y:.6f}, {self.location.x:.6f}"
        return ""

    def is_full(self):
        """Check if event has reached max participants."""
        if self.max_participants is None:
            return False
        return self.participants_count >= self.max_participants


class EventParticipant(ULIDModel):
    """Event registration/participation."""

    class ParticipantStatus(models.TextChoices):
        GOING = 'GOING', 'Going'
        MAYBE = 'MAYBE', 'Maybe'
        CANCELLED = 'CANCELLED', 'Cancelled'

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="event_participants")
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="event_participations")
    status = models.CharField(max_length=15, choices=ParticipantStatus.choices, default=ParticipantStatus.GOING)

    # Track when they joined Matrix room (for cleanup if needed)
    joined_matrix_room = models.BooleanField(default=False)

    class Meta:
        unique_together = ('event', 'profile')
        indexes = [
            models.Index(fields=['event', 'status']),
            models.Index(fields=['profile', 'status']),
        ]

    def __str__(self):
        return f"{self.profile} -> {self.event.title} ({self.status})"


# ===== Transit Real-Time History (TimescaleDB) =====

class VehiclePositionHistory(models.Model):
    """
    Time-series vehicle position history (TimescaleDB hypertable).
    Uses BigAutoField PK (not ULID) — optimized for time-series inserts.
    Float fields (not PointField) for better TimescaleDB compression.
    """
    time = models.DateTimeField(db_index=True)  # Also has RunSQL time_idx (DESC) in migration 0024
    data_source = models.ForeignKey(TransitDataSource, on_delete=models.CASCADE, related_name='position_history', db_index=False)  # RunSQL ds_vid_time composite covers this
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
        # Indexes created via RunSQL in migration (TimescaleDB hypertable)

    def __str__(self):
        return f"{self.vehicle_id} @ {self.time}"


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


class DroneZone(ULIDModel):
    """UAS geographical zone (drone no-fly / restricted airspace), ED-269 model.

    One row per geometry *segment*: an ED-269 feature may carry several segments,
    each with its own vertical band, so segments are stored individually to keep
    altitude limits precise. Reloaded wholesale per source on import
    (small dataset, version-stamped), so no per-row upsert is needed.
    """

    class Restriction(models.TextChoices):
        PROHIBITED = 'PROHIBITED', 'Prohibited'
        REQ_AUTHORISATION = 'REQ_AUTHORISATION', 'Authorisation required'
        CONDITIONAL = 'CONDITIONAL', 'Conditional'
        NO_RESTRICTION = 'NO_RESTRICTION', 'No restriction'

    source = models.CharField(
        max_length=32, default='anac_pt', db_index=True,
        help_text="Data provider key, e.g. 'anac_pt'",
    )
    source_version = models.CharField(
        max_length=64, blank=True, help_text="Provider dataset version stamp",
    )
    zone_identifier = models.CharField(
        max_length=64, db_index=True,
        help_text="ED-269 feature identifier (e.g. '1001UA')",
    )
    name = models.CharField(max_length=255, blank=True)
    country_code = models.CharField(max_length=3, default='PRT')
    restriction = models.CharField(
        max_length=20, choices=Restriction.choices,
        default=Restriction.REQ_AUTHORISATION, db_index=True,
    )
    reason = models.JSONField(
        default=list, blank=True,
        help_text="ED-269 reason codes, e.g. ['AIR_TRAFFIC']",
    )
    message = models.TextField(blank=True)
    lower_limit_m = models.FloatField(default=0, help_text="Lower vertical limit, metres")
    upper_limit_m = models.FloatField(default=120, help_text="Upper vertical limit, metres")
    lower_ref = models.CharField(max_length=8, default='AGL', help_text="AGL or AMSL")
    upper_ref = models.CharField(max_length=8, default='AGL', help_text="AGL or AMSL")
    geometry = models.MultiPolygonField(
        srid=4326, geography=True,
        help_text="Zone footprint (ED-269 circles buffered to polygons)",
    )

    class Meta:
        indexes = [
            models.Index(fields=['source', 'restriction']),
        ]

    def __str__(self):
        return f"{self.zone_identifier} {self.name} [{self.restriction}]"
