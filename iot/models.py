from django.db import models
from django.contrib.gis.db import models as gis_models
from core.models import ULIDModel
from identity.models import Profile
from market.models import Item

# NOTE: IoTDevice is kept for backward compatibility but uses ITM prefix
# It should be considered as a specialized view of Item with spec_type='IOT_DEVICE'
# Future refactoring should migrate to using Item directly
class IoTDevice(ULIDModel):
    class DeviceType(models.TextChoices):
        SENSOR = 'SENSOR', 'Sensor'
        ACTUATOR = 'ACTUATOR', 'Actuator (e.g., Smart Lock)'
        MESH_ROUTER = 'MESH_ROUTER', 'Mesh Network Router'
        GATEWAY = 'GATEWAY', 'Gateway'
        TRACKER = 'TRACKER', 'GPS Tracker'
        HA_DEVICE = 'HA_DEVICE', 'Home Assistant Device'

    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="iot_devices")
    name = models.CharField(max_length=100)
    device_type = models.CharField(max_length=15, choices=DeviceType.choices)
    
    # Для трекеров - IMEI или другой идентификатор
    imei = models.CharField(max_length=20, null=True, blank=True, help_text="IMEI для GPS трекеров")
    
    # Пользовательский ID устройства (для регистрации в Traccar)
    device_id = models.CharField(max_length=50, null=True, blank=True, help_text="ID устройства указанный пользователем")
    
    # ID устройства в Traccar (сохраняется после регистрации)
    traccar_device_id = models.IntegerField(null=True, blank=True, help_text="ID устройства в Traccar")

    item_twin = models.OneToOneField(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="iot_device_link", limit_choices_to={'spec_type': 'IOT_DEVICE'})

    connection_info = models.JSONField(default=dict, blank=True)

    # GRE tunnel IP assigned by Django for multi-bumblebee VPN (172.16.0.{2-254})
    tunnel_ip = models.GenericIPAddressField(null=True, blank=True, unique=True)

    # VPS WireGuard gateway fields
    wg_public_key = models.CharField(max_length=44, null=True, blank=True)
    wg_ip = models.GenericIPAddressField(null=True, blank=True, unique=True)

    # Yggdrasil ACL: IPv6 addresses allowed inbound from Yggdrasil overlay
    ygg_allowed_ips = models.JSONField(default=list, blank=True, help_text="IPv6 addresses allowed inbound from Yggdrasil")

    # Solo-island override for the guest-VLAN gateway election: this bumblebee
    # terminates its own guest VLAN (DHCP + VPN exit) regardless of the fleet-wide
    # election. Only safe on a node with no batman-adv mesh neighbors — on a shared
    # island two DHCP servers would race on the one guest VLAN. Interim knob until
    # per-island election (heartbeat-reported originator sets) lands.
    guest_gateway_force = models.BooleanField(default=False)

    # Sharing budgets (mesh routers): how much of this node's uplink its owner
    # donates. Delivered to the fleet via heartbeat; defaults match the printed
    # getting-started sheet.
    mesh_guest_rate_kbps = models.PositiveIntegerField(
        default=512,
        help_text="Per-guest free-tier rate in kbps, applied while this node terminates the guest VLAN",
    )
    mesh_host_rate_mbps = models.PositiveIntegerField(
        default=10,
        help_text="Total budget in Mbps for a mesh host node riding this node's uplink",
    )

    # Declared uplink passport (owner-entered; observed throughput lives in
    # MeshRouterStats)
    class UplinkType(models.TextChoices):
        FIBER = 'FIBER', 'Fiber'
        CABLE = 'CABLE', 'Cable'
        DSL = 'DSL', 'DSL'
        STARLINK = 'STARLINK', 'Starlink'
        CELLULAR = 'CELLULAR', 'Cellular (4G/5G)'
        OTHER = 'OTHER', 'Other'

    uplink_type = models.CharField(max_length=10, choices=UplinkType.choices, null=True, blank=True)
    uplink_down_mbps = models.PositiveIntegerField(null=True, blank=True)
    uplink_up_mbps = models.PositiveIntegerField(null=True, blank=True)

    # User-set AP location for coverage map (independent of connection_info)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    # Owner-consented attribution on the public map panel. Off by default:
    # device coordinates are usually a home, so linking a profile to them is
    # the owner's explicit choice, never implied by map visibility.
    show_owner = models.BooleanField(
        default=False,
        help_text="Show the owner (with a profile link) on the public map panel",
    )

    # Physical location grouping
    property = models.ForeignKey('iot.Property', on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name='devices')

    last_seen = models.DateTimeField(null=True, blank=True)
    status_data = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['device_id'],
                condition=models.Q(device_type='MESH_ROUTER'),
                name='unique_mesh_router_device_id',
            ),
        ]


class TraccarUser(models.Model):
    """Учетные данные пользователя в Traccar"""
    profile = models.OneToOneField(
        Profile,
        on_delete=models.CASCADE,
        related_name='traccar_account'
    )
    traccar_user_id = models.IntegerField(unique=True)
    traccar_username = models.CharField(max_length=128, unique=True)
    traccar_password_encrypted = models.CharField(max_length=256)  # Зашифрованный пароль
    traccar_api_token = models.CharField(max_length=256, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Traccar account for {self.profile.id}"

    class Meta:
        db_table = 'iot_traccar_user'


class TrackerLocation(ULIDModel):
    """Текущее местоположение GPS трекера с PostGIS полями"""
    
    device = models.OneToOneField(
        IoTDevice, 
        on_delete=models.CASCADE,
        related_name="current_location",
        limit_choices_to={'device_type': 'TRACKER'}
    )
    
    # PostGIS поля для эффективных гео-запросов
    location = gis_models.PointField(srid=4326, spatial_index=True)
    altitude = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True, help_text="Speed in km/h")
    heading = models.FloatField(null=True, blank=True, help_text="Direction 0-360")
    accuracy = models.FloatField(null=True, blank=True, help_text="Accuracy in meters")
    
    # Дополнительные данные
    battery_level = models.IntegerField(null=True, blank=True, help_text="Battery 0-100%")
    signal_type = models.CharField(max_length=10, null=True, blank=True)  # 2G/3G/4G/5G
    satellites = models.IntegerField(null=True, blank=True)
    
    # Временная метка от устройства
    device_timestamp = models.DateTimeField()
    
    def __str__(self):
        return f"Location of {self.device.name} at {self.device_timestamp}"
    
    class Meta:
        db_table = 'iot_tracker_location'
        indexes = [
            models.Index(fields=['device', '-device_timestamp']),
        ]


class MeshPass(ULIDModel):
    """Account-level full-speed entitlement on the mesh guest network.

    One pass per profile; money (Lightning) and achievements both extend the
    same expiry through MeshPassCredit. Enforcement is per bound device
    (MeshDevice MAC), pushed to routers via the heartbeat response.
    """

    profile = models.OneToOneField(
        'identity.Profile', on_delete=models.CASCADE, related_name='mesh_pass',
    )
    expires_at = models.DateTimeField()
    max_devices = models.PositiveSmallIntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_active(self) -> bool:
        from django.utils import timezone
        return self.expires_at > timezone.now()

    def __str__(self):
        return f"MeshPass {self.profile_id} until {self.expires_at:%Y-%m-%d}"


class MeshPassCredit(ULIDModel):
    """One extension of a MeshPass: a Lightning payment, an achievement
    reward, or a manual grant. PENDING = unpaid Lightning invoice."""

    class Source(models.TextChoices):
        LIGHTNING = 'LIGHTNING'
        ACHIEVEMENT = 'ACHIEVEMENT'
        GRANT = 'GRANT'

    class Status(models.TextChoices):
        PENDING = 'PENDING'
        APPLIED = 'APPLIED'
        EXPIRED = 'EXPIRED'

    mesh_pass = models.ForeignKey(MeshPass, on_delete=models.CASCADE, related_name='credits')
    source = models.CharField(max_length=12, choices=Source.choices)
    days = models.PositiveSmallIntegerField()
    amount_sats = models.BigIntegerField(null=True, blank=True)
    ln_payment_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    ln_invoice = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"MeshPassCredit {self.source} +{self.days}d [{self.status}]"


class MeshDevice(ULIDModel):
    """A client device (WiFi MAC) bound to a MeshPass.

    MAC is the durable key: modern phones keep a persistent randomized MAC
    per SSID, so one binding covers every island of the shared guest ESSID.
    The heartbeat translates bound MACs to current guest-lease IPs per node.
    """

    mesh_pass = models.ForeignKey(MeshPass, on_delete=models.CASCADE, related_name='devices')
    mac = models.CharField(max_length=17, unique=True)
    label = models.CharField(max_length=64, blank=True)
    last_ipv4 = models.GenericIPAddressField(protocol='IPv4', null=True, blank=True)
    last_gateway = models.ForeignKey(
        IoTDevice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bound_mesh_devices',
        limit_choices_to={'device_type': 'MESH_ROUTER'},
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"MeshDevice {self.mac} ({self.label or 'unnamed'})"


class MeshRouterStats(models.Model):
    """Mesh router telemetry time series (TimescaleDB hypertable).

    One row per heartbeat (5-min cron) from stats-reporting firmware (ph41+);
    older firmware sends no stats block and simply writes no rows. Raw byte
    counters plus write-time derived rates: the heartbeat handler keeps the
    previous sample in Redis and computes bps, treating an uptime drop or a
    counter decrease as a reboot/reset (rates null for that sample).
    365-day retention via TimescaleDB.
    """
    id = models.BigAutoField(auto_created=True, primary_key=True, serialize=False)
    time = models.DateTimeField(db_index=True)
    device = models.ForeignKey(
        IoTDevice,
        on_delete=models.CASCADE,
        related_name="mesh_stats",
    )
    uplink_dev = models.CharField(max_length=16, blank=True, default='')
    wan_rx_bytes = models.BigIntegerField(null=True, blank=True)
    wan_tx_bytes = models.BigIntegerField(null=True, blank=True)
    wan_rx_bps = models.BigIntegerField(null=True, blank=True)
    wan_tx_bps = models.BigIntegerField(null=True, blank=True)
    guest_rx_bytes = models.BigIntegerField(null=True, blank=True)
    guest_tx_bytes = models.BigIntegerField(null=True, blank=True)
    guest_rx_bps = models.BigIntegerField(null=True, blank=True)
    guest_tx_bps = models.BigIntegerField(null=True, blank=True)
    wifi_clients = models.SmallIntegerField(null=True, blank=True)
    guest_clients = models.SmallIntegerField(null=True, blank=True)
    load_1m = models.FloatField(null=True, blank=True)
    mem_used_pct = models.SmallIntegerField(null=True, blank=True)
    mesh_neighbors = models.SmallIntegerField(null=True, blank=True)
    uptime = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'iot_mesh_router_stats'
        indexes = [
            models.Index(fields=['device', '-time'], name='iot_mrs_device_time'),
        ]


class TrackerHistory(models.Model):
    """GPS tracker position history (TimescaleDB hypertable).

    Float fields (not PointField) for better TimescaleDB compression.
    Written in batches by flush_tracker_positions daemon (1/min).
    90-day retention policy via TimescaleDB.
    """
    id = models.BigAutoField(auto_created=True, primary_key=True, serialize=False)
    time = models.DateTimeField(db_index=True)
    device = models.ForeignKey(
        IoTDevice,
        on_delete=models.CASCADE,
        related_name="position_history",
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    altitude = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True, help_text="Speed in km/h")
    heading = models.FloatField(null=True, blank=True)
    accuracy = models.FloatField(null=True, blank=True)
    battery_level = models.SmallIntegerField(null=True, blank=True)
    satellites = models.SmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'iot_tracker_history'


class VehicleAssignment(ULIDModel):
    """Dispatch: assign a GPS tracker device to a transit route."""

    class Status(models.TextChoices):
        ASSIGNED = 'ASSIGNED', 'Assigned'
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    device = models.ForeignKey(
        IoTDevice, on_delete=models.CASCADE,
        related_name='vehicle_assignments',
        limit_choices_to={'device_type': 'TRACKER'},
    )
    route = models.ForeignKey(
        'geo.Route', on_delete=models.CASCADE,
        related_name='vehicle_assignments',
    )
    data_source = models.ForeignKey(
        'geo.TransitDataSource', on_delete=models.CASCADE,
        related_name='vehicle_assignments',
    )
    direction_id = models.SmallIntegerField(default=0)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ASSIGNED)
    display_vehicle_id = models.CharField(max_length=50, blank=True, help_text="Vehicle ID shown to passengers")
    created_by = models.ForeignKey(
        'identity.Profile', on_delete=models.CASCADE,
        related_name='dispatch_assignments',
    )
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['device', 'date', 'status']),
            models.Index(fields=['data_source', 'date', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['device', 'date'],
                condition=models.Q(status__in=['ASSIGNED', 'ACTIVE']),
                name='unique_active_device_date',
            ),
        ]

    def __str__(self):
        return f"{self.device.name} → {self.route.short_name} ({self.date})"


class Property(ULIDModel):
    """User's physical property (home, dacha, office)."""

    class PropertyType(models.TextChoices):
        HOUSE = 'house', 'House'
        APARTMENT = 'apartment', 'Apartment'
        LAND = 'land', 'Land Plot'
        OFFICE = 'office', 'Office'
        DACHA = 'dacha', 'Dacha/Country House'
        GARAGE = 'garage', 'Garage'
        OTHER = 'other', 'Other'

    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='properties')
    name = models.CharField(max_length=100)

    # Geo: Building link OR manual point+polygon
    world_object = models.ForeignKey('geo.WorldObject', on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='properties')
    location = gis_models.PointField(srid=4326, geography=True)
    territory = gis_models.PolygonField(srid=4326, geography=True, null=True, blank=True)

    address = models.CharField(max_length=500, blank=True)
    property_type = models.CharField(max_length=20, choices=PropertyType.choices, default=PropertyType.HOUSE)
    photo = models.ImageField(upload_to='properties/', null=True, blank=True)
    household_invite_token = models.CharField(
        max_length=64, null=True, blank=True, unique=True,
        help_text="Invite link token for household members (civic polls audience); rotate to revoke"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['owner', 'name'], name='unique_property_name_per_owner')
        ]

    def save(self, *args, **kwargs):
        if self.world_object and not self.location:
            self.location = self.world_object.location
        if self.world_object and not self.address:
            self.address = self.world_object.full_address
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.property_type})"


class PropertyMember(ULIDModel):
    """Household member of a Property — the audience of household civic polls
    (PK/civic-polls-system.md). The owner is implicit; rows are invited residents."""

    class Role(models.TextChoices):
        MEMBER = 'member', 'Member'

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='household_members')
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='property_memberships')
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    invited_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='household_invites_sent')

    class Meta:
        unique_together = [['property', 'profile']]
        indexes = [
            models.Index(fields=['profile']),
        ]

    def __str__(self):
        return f"{self.profile_id[:8]} @ {self.property.name}"


class EnvStation(ULIDModel):
    """A physical environmental station (weather and/or air quality) at a fixed
    location.

    Data arrives by push — Ecowitt "Customized upload", AirGradient custom
    server (``httpDomain``) — is stored as an ``EnvReading`` timeseries, and,
    when ``is_public``, shared on the public map for everyone. One station may
    report weather, air quality, or both: every reading metric is optional.
    """

    class Source(models.TextChoices):
        ECOWITT = 'ECOWITT', 'Ecowitt / Fine Offset'
        AIRGRADIENT = 'AIRGRADIENT', 'AirGradient'
        GENERIC = 'GENERIC', 'Generic'

    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='env_stations')
    property = models.ForeignKey('iot.Property', on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name='env_stations')
    name = models.CharField(max_length=100)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.GENERIC)

    # Ingest identity. Ecowitt matches on the token embedded in its upload Path
    # (the console has no way to send a bearer header); AirGradient matches on
    # its device serial carried in the pushed body. Both are unique-indexed for
    # an O(1) lookup on every inbound reading.
    ingest_token = models.CharField(max_length=32, unique=True, db_index=True)
    external_id = models.CharField(
        max_length=64, blank=True, db_index=True,
        help_text="Device serial (AirGradient) / PASSKEY (Ecowitt) for push matching",
    )

    location = gis_models.PointField(srid=4326, geography=True)
    is_public = models.BooleanField(default=False, help_text="Show on the public map for everyone")
    # Owner-consented attribution on the public map panel. Separate from
    # is_public: publishing readings at a point is not consent to naming the
    # profile at that point (station coordinates are usually a home).
    show_owner = models.BooleanField(
        default=False,
        help_text="Show the owner (with a profile link) on the public map panel",
    )
    # Owner-pasted deep link to the station's page on its vendor cloud (the
    # AirGradient/Ecowitt map ids are not derivable from serial/coords, so the
    # link cannot be auto-built). Shown to everyone on the public map panel for
    # independent cross-checking of our ingested readings.
    public_url = models.URLField(
        max_length=300, blank=True, default='',
        help_text="Link to the station's public page (e.g. vendor cloud map), shown on the map panel",
    )

    # Fast map render: latest reading snapshot, so the public map layer never
    # touches the (large) hypertable.
    last_reading_at = models.DateTimeField(null=True, blank=True)
    latest = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['owner', 'name'], name='unique_env_station_per_owner'),
        ]
        indexes = [
            models.Index(fields=['is_public', 'last_reading_at']),
        ]

    def __str__(self):
        return f"{self.name} ({self.source})"


class EnvReading(models.Model):
    """A single environmental station reading (TimescaleDB hypertable).

    Every metric is optional — a station writes the subset its sensors provide
    (a weather console fills the top block, an air-quality monitor the bottom).
    Float fields (not typed sensor rows) for TimescaleDB compression, mirroring
    ``TrackerHistory``. Converted to a hypertable + retention policy out of band
    (raw SQL, like ``iot_tracker_history``).
    """

    id = models.BigAutoField(auto_created=True, primary_key=True, serialize=False)
    time = models.DateTimeField(db_index=True)
    station = models.ForeignKey(EnvStation, on_delete=models.CASCADE, related_name='readings')

    # Weather
    temperature = models.FloatField(null=True, blank=True, help_text="°C")
    humidity = models.FloatField(null=True, blank=True, help_text="%")
    pressure = models.FloatField(null=True, blank=True, help_text="hPa (relative)")
    wind_speed = models.FloatField(null=True, blank=True, help_text="km/h")
    wind_gust = models.FloatField(null=True, blank=True, help_text="km/h")
    wind_dir = models.FloatField(null=True, blank=True, help_text="degrees the wind blows FROM")
    rain_rate = models.FloatField(null=True, blank=True, help_text="mm/h")
    rain_daily = models.FloatField(null=True, blank=True, help_text="mm")
    solar_radiation = models.FloatField(null=True, blank=True, help_text="W/m²")
    uv = models.FloatField(null=True, blank=True, help_text="UV index")

    # Air quality
    pm01 = models.FloatField(null=True, blank=True, help_text="PM1.0 µg/m³")
    pm25 = models.FloatField(null=True, blank=True, help_text="PM2.5 µg/m³")
    pm10 = models.FloatField(null=True, blank=True, help_text="PM10 µg/m³")
    co2 = models.FloatField(null=True, blank=True, help_text="ppm")
    tvoc_index = models.FloatField(null=True, blank=True, help_text="VOC index (0-500)")
    nox_index = models.FloatField(null=True, blank=True, help_text="NOx index (0-500)")

    raw = models.JSONField(default=dict, blank=True, help_text="Original decoded payload")

    class Meta:
        db_table = 'iot_env_reading'
        indexes = [
            models.Index(fields=['station', '-time']),
        ]

    def __str__(self):
        return f"Reading of {self.station_id} at {self.time}"


class HAHome(ULIDModel):
    """A user's Home Assistant server instance."""
    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='ha_homes')
    property = models.ForeignKey(Property, on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name='ha_homes')
    name = models.CharField(max_length=100)  # "Home", "Dacha", "Office"

    # Connection
    url = models.URLField(max_length=500)  # http://[200:abc::1]:8123 or https://my-ha.duckdns.org
    access_token_encrypted = models.TextField()  # Long-lived token, Fernet encryption

    # Metadata (populated from GET /api/config on first connection)
    ha_version = models.CharField(max_length=20, blank=True)
    location_name = models.CharField(max_length=100, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    # Status
    status = models.CharField(max_length=20, choices=[
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('error', 'Auth Error'),
    ], default='offline')
    last_seen = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)

    # Sync settings
    sync_interval_seconds = models.IntegerField(default=60)
    auto_import = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['owner', 'name'], name='unique_ha_home_per_owner')
        ]

    def __str__(self):
        return f"{self.name} ({self.status})"


class HAEntity(ULIDModel):
    """Mapping between a Home Assistant entity and an IoTDevice."""

    class EnergySignalRole(models.TextChoices):
        SURPLUS_BOOL = 'SURPLUS_BOOL', 'Solar surplus on/off'
        SURPLUS_POWER = 'SURPLUS_POWER', 'Solar production (watts)'
        SURPLUS_PRICE = 'SURPLUS_PRICE', 'Solar price (€/kWh)'

    home = models.ForeignKey(HAHome, on_delete=models.CASCADE, related_name='entities')
    device = models.OneToOneField(IoTDevice, on_delete=models.CASCADE, related_name='ha_entity',
                                  null=True, blank=True)

    # HA data
    entity_id = models.CharField(max_length=255)  # "light.kitchen", "sensor.temperature_outdoor"
    domain = models.CharField(max_length=50)  # "light", "sensor", "switch", "climate", ...
    friendly_name = models.CharField(max_length=255, blank=True)

    # Cached state (updated during sync)
    state = models.CharField(max_length=255, blank=True)  # "on", "off", "22.5", "locked"
    attributes_json = models.JSONField(default=dict)
    last_changed = models.DateTimeField(null=True, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    # Visibility control
    is_imported = models.BooleanField(default=False)
    is_controllable = models.BooleanField(default=False)

    # Energy signal: Parahub toggles this entity based on EnergyCell status
    energy_signal_role = models.CharField(
        max_length=15, choices=EnergySignalRole.choices,
        null=True, blank=True, db_index=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['home', 'entity_id'], name='unique_entity_per_home')
        ]
        ordering = ['domain', 'friendly_name']

    def __str__(self):
        return f"{self.entity_id} ({self.state})"
