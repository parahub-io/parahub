from django.contrib.gis.db import models as gis_models
from django.db import models
from core.models import ULIDModel
from identity.models import Profile


class EnergyCell(ULIDModel):
    """
    ACC (Autoconsumo Coletivo) group — локальная энерго-ячейка.
    Все участники должны быть в радиусе 2 км от одной подстанции (PT).
    """

    class Status(models.TextChoices):
        GREEN = 'GREEN', 'Green — surplus available'
        YELLOW = 'YELLOW', 'Yellow — balanced'
        RED = 'RED', 'Red — no surplus'
        OFFLINE = 'OFFLINE', 'Offline'

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    # Местоположение подстанции (PT — Posto de Transformação)
    location = gis_models.PointField(geography=True, srid=4326)

    # PT ID из документов E-Redes (заполняется вручную при регистрации)
    transformer_id = models.CharField(max_length=50, blank=True, help_text='E-Redes PT ID')

    # Радиус ячейки в км (LV=2, MV=4)
    radius_km = models.DecimalField(max_digits=4, decimal_places=1, default=2.0)

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OFFLINE,
    )

    # Текущая цена для соседей (EUR/kWh), None = не активна
    current_price_eur = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)

    created_by = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_energy_cells',
    )

    # Optional link to cooperative Establishment that owns/manages this cell
    establishment = models.ForeignKey(
        'geo.Establishment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='energy_cells',
        help_text='Cooperative or organization managing this ACC',
    )

    class Meta:
        db_table = 'energy_cell'
        verbose_name = 'Energy Cell (ACC)'

    def __str__(self):
        return f'{self.name} [{self.status}]'


class EnergyProducer(ULIDModel):
    """
    UPAC — Unidade de Produção para Autoconsumo.
    Производитель: солнечные панели, инвертор, опционально АКБ.
    """

    class InverterType(models.TextChoices):
        SOLARMAN = 'SOLARMAN', 'Solarman (Deye/Sofar)'
        FRONIUS = 'FRONIUS', 'Fronius'
        GROWATT = 'GROWATT', 'Growatt'
        SMA = 'SMA', 'SMA'
        SHELLY = 'SHELLY', 'Shelly EM'
        OTHER = 'OTHER', 'Other'

    cell = models.ForeignKey(EnergyCell, on_delete=models.CASCADE, related_name='producers')
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='energy_producer_memberships')
    property = models.ForeignKey('iot.Property', on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name='energy_producers')

    cpe_code = models.CharField(max_length=30, help_text='CPE code from electricity bill (e.g. PT0002XXXXXXXXXX)')
    capacity_kw = models.DecimalField(max_digits=6, decimal_places=2, help_text='Installed PV capacity in kW')
    battery_kwh = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Battery capacity in kWh (optional)',
    )

    inverter_type = models.CharField(max_length=12, choices=InverterType.choices, default=InverterType.OTHER)
    # URL/token для polling API инвертора (опционально, для Smart-Trigger)
    inverter_api_url = models.CharField(max_length=255, blank=True)
    inverter_api_token = models.CharField(max_length=255, blank=True)

    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'energy_producer'
        unique_together = [('cell', 'profile')]
        verbose_name = 'Energy Producer (UPAC)'

    def __str__(self):
        return f'Producer {self.profile_id} in {self.cell_id}'


class EnergyConsumer(ULIDModel):
    """
    Utilizador — потребитель внутри ACC-ячейки (сосед).
    Требует только Smart Meter (уже у 90% в PT).
    """

    cell = models.ForeignKey(EnergyCell, on_delete=models.CASCADE, related_name='consumers')
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='energy_consumer_memberships')
    property = models.ForeignKey('iot.Property', on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name='energy_consumers')

    cpe_code = models.CharField(max_length=30, help_text='CPE code from electricity bill')
    # Коэффициент раздачи (доля от общего пула), задаётся при DGEG регистрации
    distribution_coefficient = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'energy_consumer'
        unique_together = [('cell', 'profile')]
        verbose_name = 'Energy Consumer (Neighbor)'

    def __str__(self):
        return f'Consumer {self.profile_id} in {self.cell_id}'


class EnergyRelay(ULIDModel):
    """Direct smart relay controlled by energy cell status (no HA required).

    When cell goes GREEN → relay ON, YELLOW/RED → relay OFF.
    Supports Shelly Gen1/Gen2 and Tasmota HTTP APIs.
    """

    class RelayType(models.TextChoices):
        SHELLY_GEN2 = 'SHELLY_GEN2', 'Shelly Gen2+'
        SHELLY_GEN1 = 'SHELLY_GEN1', 'Shelly Gen1'
        TASMOTA = 'TASMOTA', 'Tasmota'

    consumer = models.ForeignKey(EnergyConsumer, on_delete=models.CASCADE, related_name='relays')
    name = models.CharField(max_length=100)  # "Water Heater", "Pool Pump"
    relay_type = models.CharField(max_length=12, choices=RelayType.choices)
    url = models.CharField(max_length=255)  # http://192.168.1.50 or http://[200:...]:80
    channel = models.SmallIntegerField(default=0, help_text='Relay channel (0 for single-channel devices)')
    is_active = models.BooleanField(default=True)
    last_triggered = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = 'energy_relay'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.relay_type})'


class EnergyBillingRecord(ULIDModel):
    """EGAC management fee billing record — monthly per ACC participant."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        INVOICED = 'INVOICED', 'Invoiced'
        PAID = 'PAID', 'Paid'

    cell = models.ForeignKey(EnergyCell, on_delete=models.CASCADE, related_name='billing_records')
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='energy_billing')
    period_start = models.DateField()
    period_end = models.DateField()
    kwh_consumed = models.DecimalField(max_digits=10, decimal_places=2)
    fee_eur = models.DecimalField(max_digits=8, decimal_places=4, help_text="1% EGAC management fee")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    invoice_reference = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'energy_billing_record'
        indexes = [
            models.Index(fields=['profile', '-period_start']),
            models.Index(fields=['cell', '-period_start']),
        ]

    def __str__(self):
        return f'Billing {self.profile_id} {self.period_start} - {self.fee_eur}€'


class GridInfrastructure(ULIDModel):
    """Portuguese electricity grid infrastructure element (E-Redes)."""

    class InfraType(models.TextChoices):
        TRANSFORMER = 'transformer', 'Transformer Station (PT)'
        POLE = 'pole', 'Power Pole'
        CABINET = 'cabinet', 'Distribution Cabinet'

    infrastructure_type = models.CharField(max_length=15, choices=InfraType.choices)
    eredes_id = models.CharField(max_length=50, unique=True)
    location = gis_models.PointField(srid=4326, geography=True)
    capacity_kva = models.FloatField(null=True, blank=True)
    voltage_level = models.CharField(max_length=10, blank=True)  # "BT", "MT"
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'energy_grid_infrastructure'

    def __str__(self):
        return f'{self.infrastructure_type} {self.eredes_id}'
