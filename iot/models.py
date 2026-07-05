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

    # User-set AP location for coverage map (independent of connection_info)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

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


class MeshSubscription(ULIDModel):
    """Paid WiFi speed upgrade subscription for mesh guest clients."""

    class Status(models.TextChoices):
        PENDING = 'PENDING'
        ACTIVE = 'ACTIVE'
        EXPIRED = 'EXPIRED'

    client_ip = models.GenericIPAddressField()
    client_mac = models.CharField(max_length=17, blank=True)
    gateway_device = models.ForeignKey(
        IoTDevice, on_delete=models.CASCADE,
        related_name='subscriptions',
        limit_choices_to={'device_type': 'MESH_ROUTER'},
    )
    ln_payment_hash = models.CharField(max_length=64, unique=True, db_index=True)
    ln_invoice = models.TextField()
    amount_sats = models.BigIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['gateway_device', 'status', 'expires_at']),
        ]

    def __str__(self):
        return f"MeshSub {self.client_ip} [{self.status}]"


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
