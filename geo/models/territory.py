from django.contrib.gis.db import models
from core.models import ULIDModel


class Territory(ULIDModel):
    """Administrative territory for civic poll scoping (country/region/municipality/parish).

    Distinct from Place (WOF gazetteer for search): Territory carries official
    administrative codes (ISO 3166-1, NUTS II, DICO, DICOFRE for PT) and a strict
    4-level hierarchy used to resolve a voter's residency chain.
    """

    class Level(models.TextChoices):
        COUNTRY = 'country', 'Country'
        REGION = 'region', 'Region'
        MUNICIPALITY = 'municipality', 'Municipality'
        PARISH = 'parish', 'Parish'

    level = models.CharField(max_length=20, choices=Level.choices, db_index=True)
    country = models.CharField(max_length=2, help_text="ISO 3166-1 alpha-2; equals code for country rows")
    code = models.CharField(
        max_length=16,
        help_text="Official code: ISO alpha-2 (country), NUTS II (region), DICO (PT municipality), DICOFRE (PT parish)"
    )
    name = models.CharField(max_length=200)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')
    geometry = models.MultiPolygonField(srid=4326, geography=True, null=True, blank=True,
                                        help_text="Simplified boundary, optional (future residency auto-suggest)")
    is_active = models.BooleanField(default=True, help_text="False for territories dissolved by administrative reforms")

    class Meta:
        db_table = 'geo_territory'
        unique_together = [['country', 'level', 'code']]
        indexes = [
            models.Index(fields=['country', 'level']),
            models.Index(fields=['parent']),
        ]
        verbose_name_plural = 'territories'

    def __str__(self):
        return f"{self.name} ({self.level}:{self.code})"

    def ancestor_chain(self):
        """Return [self, parent, ..., root] following parent links (max 4 hops by construction)."""
        chain = [self]
        node = self
        hops = 0
        while node.parent_id and hops < 6:
            node = node.parent
            chain.append(node)
            hops += 1
        return chain
