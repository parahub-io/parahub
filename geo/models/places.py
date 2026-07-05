from django.contrib.gis.db import models
from core.models import ULIDModel


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
