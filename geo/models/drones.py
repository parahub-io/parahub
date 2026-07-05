from django.contrib.gis.db import models
from core.models import ULIDModel


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
