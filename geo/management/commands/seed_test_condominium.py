"""
Seed test condominium with fractions, memberships, and budget categories.
"""

from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from django.db import transaction
from decimal import Decimal


class Command(BaseCommand):
    help = 'Seed test condominium for development'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete existing test condominium first')

    def handle(self, *args, **options):
        from identity.models import Profile
        from geo.models import (
            Building, Establishment, EstablishmentMembership,
            CondominiumFraction
        )
        from geo.services.condominium import CondominiumService

        CONDO_NAME = 'Condomínio Rua Augusta 10'
        CONDO_SLUG = 'condo-rua-augusta-10'

        if options['reset']:
            deleted, _ = Establishment.objects.filter(slug=CONDO_SLUG).delete()
            if deleted:
                self.stdout.write(self.style.WARNING(f'Deleted existing condominium'))

        # Find test users
        try:
            instance_domain = 'parahub.io'
            alice = Profile.objects.get(local_name='alice', instance__domain=instance_domain)
            bob = Profile.objects.get(local_name='bob', instance__domain=instance_domain)
            carol = Profile.objects.filter(
                local_name__in=['carol', 'charlie'],
                instance__domain=instance_domain
            ).first()
            if not carol:
                raise Profile.DoesNotExist('carol or charlie')
        except Profile.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(
                f'Test user not found: {e}. Run seed_test_users first.'))
            return

        if Establishment.objects.filter(slug=CONDO_SLUG).exists():
            self.stdout.write(self.style.WARNING('Condominium already exists, skipping'))
            return

        with transaction.atomic():
            # Create building
            building, _ = Building.objects.get_or_create(
                full_address='Rua Augusta 10, 1100-053 Lisboa, Portugal',
                defaults={
                    'location': Point(-9.1372, 38.7107, srid=4326),
                    'country': 'PT',
                    'city': 'Lisboa',
                    'street': 'Rua Augusta',
                    'house_number': '10',
                    'postal_code': '1100-053',
                    'building_type': 'apartments',
                    'levels': 5,
                }
            )

            # Create establishment
            est = Establishment.objects.create(
                owner=alice,
                building=building,
                name=CONDO_NAME,
                slug=CONDO_SLUG,
                description='Test condominium for development — 6 fractions in Baixa, Lisboa.',
                organization_type='CONDOMINIUM',
                legal_entity_id='501234567',
                member_visibility='MEMBERS_ONLY',
                treasury_enabled=True,
                treasury_eligible_levels=['efetivo', 'fundador'],
                is_verified=True,
            )
            self.stdout.write(f'  Created: {est.name}')

            # Create memberships
            EstablishmentMembership.objects.create(
                profile=alice, establishment=est, role='OWNER', membership_level='fundador')
            EstablishmentMembership.objects.create(
                profile=bob, establishment=est, role='MEMBER', membership_level='efetivo')
            EstablishmentMembership.objects.create(
                profile=carol, establishment=est, role='MEMBER', membership_level='efetivo')

            # Create fractions (total = 1000.000)
            fractions_data = [
                ('1-A', 'T2 1st floor left', '1', 'APARTMENT', Decimal('120.000'), alice),
                ('1-B', 'T3 1st floor right', '1', 'APARTMENT', Decimal('180.000'), bob),
                ('2-A', 'T2 2nd floor left', '2', 'APARTMENT', Decimal('200.000'), carol),
                ('2-B', 'T3 2nd floor right', '2', 'APARTMENT', Decimal('250.000'), None),
                ('R/C Loja', 'Ground floor shop', '0', 'COMMERCIAL', Decimal('150.000'), None),
                ('Gar', 'Underground garage', '-1', 'GARAGE', Decimal('100.000'), None),
            ]

            for ident, desc, floor, ftype, perm, resident in fractions_data:
                CondominiumFraction.objects.create(
                    establishment=est,
                    identifier=ident,
                    description=desc,
                    floor=floor,
                    fraction_type=ftype,
                    permilagem=perm,
                    resident=resident,
                    is_owner=True if resident else True,
                )

            # Create default budget categories
            cat_count = CondominiumService.create_default_budget_categories(est)

            # Set monthly budget in attributes
            est.attributes['monthly_budget'] = '500.00'
            est.save(update_fields=['attributes'])

        self.stdout.write(self.style.SUCCESS(
            f'Created condominium "{CONDO_NAME}" with 6 fractions, '
            f'3 members, {cat_count} budget categories'))
