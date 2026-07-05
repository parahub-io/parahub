from django.contrib.gis.db import models
from core.models import ULIDModel
from identity.models import Profile
from .establishments import Establishment


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
