"""
Condominium business logic.
"""

import secrets
from decimal import Decimal
from typing import List, Dict, Tuple, Optional
import logging

from django.db import transaction

logger = logging.getLogger(__name__)

PERMILAGEM_TOTAL = Decimal('1000.000')


class CondominiumService:

    @staticmethod
    def validate_permilagem_total(fractions_data: List[Dict]) -> Tuple[bool, str]:
        """Validate that permilagem values sum to 1000."""
        total = sum(Decimal(str(f['permilagem'])) for f in fractions_data)
        if total != PERMILAGEM_TOTAL:
            return False, f"Permilagem total is {total}, must be exactly 1000.000"
        return True, ""

    @staticmethod
    def calculate_monthly_quotas(establishment, total_monthly: Decimal) -> List[Dict]:
        """Calculate quota per fraction based on permilagem."""
        from geo.models import CondominiumFraction

        fractions = CondominiumFraction.objects.filter(establishment=establishment)
        result = []
        for f in fractions:
            quota = (f.permilagem / PERMILAGEM_TOTAL * total_monthly).quantize(Decimal('0.01'))
            result.append({
                'fraction_id': f.id,
                'identifier': f.identifier,
                'permilagem': f.permilagem,
                'quota': quota,
            })
        return result

    @staticmethod
    def setup_poll_voters(poll, establishment) -> int:
        """Populate PollEligibleVoter with fraction owners using permilagem as weight."""
        from geo.models import CondominiumFraction
        from governance.models import PollEligibleVoter

        fractions = CondominiumFraction.objects.filter(
            establishment=establishment,
            resident__isnull=False,
            is_owner=True,
        ).select_related('resident')

        count = 0
        seen_profiles = set()
        for f in fractions:
            if f.resident_id in seen_profiles:
                # Owner has multiple fractions — sum weights
                voter = PollEligibleVoter.objects.get(poll=poll, profile=f.resident)
                voter.weight += f.permilagem
                voter.save(update_fields=['weight'])
            else:
                PollEligibleVoter.objects.create(
                    poll=poll,
                    profile=f.resident,
                    weight=f.permilagem,
                )
                seen_profiles.add(f.resident_id)
                count += 1

        return count

    @staticmethod
    @transaction.atomic
    def create_default_budget_categories(establishment) -> int:
        """Create default condominium budget categories."""
        from treasury.models import BudgetCategory

        defaults = [
            ('quotas-ordinarias', 'Ordinary Quotas', 'receipt', 0),
            ('fundo-reserva', 'Reserve Fund', 'piggy-bank', 1),
            ('seguros', 'Insurance', 'shield', 2),
            ('limpeza', 'Cleaning', 'sparkles', 3),
            ('manutencao', 'Maintenance', 'wrench', 4),
            ('outros', 'Other', 'more-horizontal', 5),
        ]

        count = 0
        for slug, name, icon, order in defaults:
            _, created = BudgetCategory.objects.get_or_create(
                establishment=establishment,
                slug=slug,
                defaults={
                    'name': name,
                    'icon': icon,
                    'order': order,
                    'is_active': True,
                }
            )
            if created:
                count += 1

        return count

    @staticmethod
    def generate_invite_token() -> str:
        """Generate a secure random invite token."""
        return secrets.token_urlsafe(48)
