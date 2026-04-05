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

    # Mission metadata
    name = models.CharField(max_length=255, blank=True, help_text="Optional mission name")

    # Source photos stats
    source_photos_count = models.IntegerField(default=0)
    source_photos_size_mb = models.FloatField(default=0)

    # Generated tiles stats
    tiles_count = models.IntegerField(default=0)
    tiles_size_mb = models.FloatField(default=0)
    min_zoom = models.IntegerField(default=13)
    max_zoom = models.IntegerField(default=23)

    # Center point for map display
    center_lat = models.FloatField(null=True, blank=True)
    center_lng = models.FloatField(null=True, blank=True)

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

    # Processing options
    satellite_align = models.BooleanField(default=False, help_text="Align to satellite imagery (ESRI) during processing")

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


class TransitDataSource(ULIDModel):
    """Registry of transit data sources (GTFS feeds, CSV imports, etc.)."""
    class Format(models.TextChoices):
        GTFS = 'gtfs', 'GTFS'
        CSV = 'csv', 'CSV'
        XML = 'xml', 'XML'
        GEOJSON = 'geojson', 'GeoJSON'
        MANAGED = 'managed', 'Managed'

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
    last_import_hash = models.CharField(max_length=64, blank=True, help_text="SHA256 of last downloaded ZIP")
    last_import_stats = models.JSONField(null=True, blank=True, help_text="Statistics of last import run")
    rt_interval = models.PositiveSmallIntegerField(default=30, help_text="RT poll interval in seconds")

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

class Stop(ULIDModel):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="stops")
    place = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True, related_name="stops", help_text="Cached: place this stop belongs to")
    source_id = models.CharField(max_length=100, blank=True, db_index=True, help_text="External ID from data source")
    slug = models.SlugField(max_length=150, blank=True, default='', db_index=True)
    name = models.CharField(max_length=255)
    location = models.PointField(srid=4326, geography=True)
    location_type = models.SmallIntegerField(default=0, help_text="0=stop/platform, 1=station")
    parent_station = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='child_stops')

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
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="stop_times")
    stop = models.ForeignKey(Stop, on_delete=models.CASCADE, related_name="stop_times")
    arrival_time = models.TimeField()
    departure_time = models.TimeField()
    stop_sequence = models.PositiveSmallIntegerField()

    class Meta:
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
    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="establishments",
                              help_text="Profile that created this establishment")
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
