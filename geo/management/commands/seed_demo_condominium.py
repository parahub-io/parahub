"""
Seed demo condominiums with realistic Portuguese building data.

Creates 2 condominiums in Lisbon:
  1. Residential building on Rua da Prata (5 floors, 10 fractions)
  2. Mixed-use building on Av. da Liberdade (7 floors, 12 fractions)

Each has realistic permilagem distribution, Portuguese family names,
and 6 months of quota payment history (paid/pending/overdue mix).
"""

import hashlib
from datetime import datetime, timezone as dt_tz
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone


DEMO_MARKER = 'demo'

CONDOS = [
    # ---- Building 1: Residential, Baixa Pombalina ----
    {
        'building': {
            'full_address': '[Demo] Rua da Prata 78, 1100-420 Lisboa, Portugal',
            'location': Point(-9.1365, 38.7118, srid=4326),
            'country': 'PT',
            'city': 'Lisboa',
            'street': 'Rua da Prata',
            'house_number': '78',
            'postal_code': '1100-420',
            'building_type': 'apartments',
            'levels': 5,
        },
        'establishment': {
            'name': '[Demo] Condominio Rua da Prata 78',
            'slug': 'demo-condo-rua-da-prata-78',
            'description': 'Edificio residencial na Baixa Pombalina. 10 fracoes, 5 pisos.',
            'legal_entity_id': '501111222',
            'monthly_budget': '850.00',
        },
        # Total permilagem = 1000.000
        'fractions': [
            # (floor, identifier, description, type, permilagem, test_user or None)
            ('0', 'R/C Esq', 'T1 R/C esquerdo (Fam. Silva)', 'APARTMENT', '85.000', None),
            ('0', 'R/C Dir', 'T2 R/C direito (Fam. Costa)', 'APARTMENT', '100.000', None),
            ('1', '1-Esq', 'T2 1.o esquerdo (Fam. Ferreira)', 'APARTMENT', '110.000', 'alice'),
            ('1', '1-Dir', 'T3 1.o direito (Fam. Pereira)', 'APARTMENT', '130.000', None),
            ('2', '2-Esq', 'T2 2.o esquerdo (Fam. Oliveira)', 'APARTMENT', '110.000', 'bob'),
            ('2', '2-Dir', 'T3 2.o direito (Fam. Rodrigues)', 'APARTMENT', '130.000', None),
            ('3', '3-Esq', 'T2 3.o esquerdo (Fam. Martins)', 'APARTMENT', '110.000', None),
            ('3', '3-Dir', 'T3 3.o direito (Fam. Santos)', 'APARTMENT', '130.000', 'charlie'),
            ('-1', 'Gar 1', 'Lugar garagem 1', 'GARAGE', '47.500', 'alice'),
            ('-1', 'Gar 2', 'Lugar garagem 2', 'GARAGE', '47.500', None),
        ],
    },
    # ---- Building 2: Mixed-use, Av. da Liberdade ----
    {
        'building': {
            'full_address': '[Demo] Av. da Liberdade 142, 1250-146 Lisboa, Portugal',
            'location': Point(-9.1453, 38.7202, srid=4326),
            'country': 'PT',
            'city': 'Lisboa',
            'street': 'Av. da Liberdade',
            'house_number': '142',
            'postal_code': '1250-146',
            'building_type': 'mixed',
            'levels': 7,
        },
        'establishment': {
            'name': '[Demo] Condominio Av. Liberdade 142',
            'slug': 'demo-condo-av-liberdade-142',
            'description': 'Edificio misto na Av. da Liberdade. Comercio no R/C, habitacao nos pisos superiores.',
            'legal_entity_id': '501333444',
            'monthly_budget': '1450.00',
        },
        # Total permilagem = 1000.000
        # Commercial ground floor has higher permilagem (realistic for prime Lisbon avenue)
        'fractions': [
            ('0', 'Loja A', 'Loja comercial A (Fam. Gomes)', 'COMMERCIAL', '145.000', None),
            ('0', 'Loja B', 'Loja comercial B (Fam. Lopes)', 'COMMERCIAL', '135.000', None),
            ('1', '1-Esq', 'T2 1.o esquerdo (Fam. Almeida)', 'APARTMENT', '82.000', 'alice'),
            ('1', '1-Dir', 'T3 1.o direito (Fam. Alves)', 'APARTMENT', '93.000', None),
            ('2', '2-Esq', 'T2 2.o esquerdo (Fam. Ribeiro)', 'APARTMENT', '82.000', 'bob'),
            ('2', '2-Dir', 'T3 2.o direito (Fam. Pinto)', 'APARTMENT', '93.000', None),
            ('3', '3-Esq', 'T3 3.o esquerdo (Fam. Carvalho)', 'APARTMENT', '82.000', None),
            ('3', '3-Dir', 'T3 3.o direito (Fam. Teixeira)', 'APARTMENT', '93.000', None),
            ('4', '4-Esq', 'T2 4.o esquerdo (Fam. Moreira)', 'APARTMENT', '82.000', 'charlie'),
            ('4', '4-Dir', 'T3 4.o direito (Fam. Correia)', 'APARTMENT', '93.000', None),
            ('-1', 'Gar 1', 'Lugar garagem 1', 'GARAGE', '10.000', None),
            ('-1', 'Gar 2', 'Lugar garagem 2', 'GARAGE', '10.000', None),
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed demo condominiums with realistic Portuguese building data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Delete demo condominiums (attributes.demo=True) before recreating',
        )

    def handle(self, *args, **options):
        from identity.models import Profile
        from geo.models import (
            Building, Establishment, EstablishmentMembership,
            CondominiumFraction, QuotaPayment,
        )
        from geo.services.condominium import CondominiumService

        instance_domain = 'parahub.io'

        if options['reset']:
            qs = Establishment.objects.filter(
                organization_type='CONDOMINIUM',
                attributes__demo=True,
            )
            count = qs.count()
            qs.delete()
            if count:
                self.stdout.write(self.style.WARNING(
                    f'Deleted {count} demo condominium(s)'))

        # Find test users
        test_users = {}
        for name in ('alice', 'bob', 'charlie'):
            try:
                test_users[name] = Profile.objects.get(
                    local_name=name, instance__domain=instance_domain)
            except Profile.DoesNotExist:
                pass

        if not test_users:
            self.stdout.write(self.style.ERROR(
                'No test users found. Run: python3 manage.py seed_test_users'))
            return

        admin_profile = test_users.get('alice') or next(iter(test_users.values()))
        now = timezone.now()
        total_fractions = 0
        total_payments = 0

        for condo_data in CONDOS:
            slug = condo_data['establishment']['slug']
            if Establishment.objects.filter(slug=slug).exists():
                self.stdout.write(self.style.WARNING(
                    f'  Skipping (exists): {slug}'))
                continue

            with transaction.atomic():
                # Building
                bld = condo_data['building']
                building, _ = Building.objects.get_or_create(
                    full_address=bld['full_address'],
                    defaults={k: v for k, v in bld.items()
                              if k != 'full_address'},
                )

                # Establishment
                est_info = condo_data['establishment']
                est = Establishment.objects.create(
                    owner=admin_profile,
                    building=building,
                    name=est_info['name'],
                    slug=est_info['slug'],
                    description=est_info['description'],
                    organization_type='CONDOMINIUM',
                    legal_entity_id=est_info['legal_entity_id'],
                    member_visibility='MEMBERS_ONLY',
                    treasury_enabled=True,
                    treasury_eligible_levels=['efetivo', 'fundador'],
                    is_verified=True,
                    attributes={DEMO_MARKER: True,
                                'monthly_budget': est_info['monthly_budget']},
                )

                # Memberships — collect test users assigned to fractions
                assigned_users = set()
                for frac_data in condo_data['fractions']:
                    user_key = frac_data[5]
                    if user_key and user_key in test_users:
                        assigned_users.add(user_key)

                EstablishmentMembership.objects.create(
                    profile=admin_profile, establishment=est,
                    role='OWNER', membership_level='fundador')
                for ukey in assigned_users:
                    if test_users[ukey] == admin_profile:
                        continue
                    EstablishmentMembership.objects.create(
                        profile=test_users[ukey], establishment=est,
                        role='MEMBER', membership_level='efetivo')

                # Fractions
                monthly_budget = Decimal(est_info['monthly_budget'])
                fraction_objects = []
                for floor, ident, desc, ftype, perm_str, user_key in condo_data['fractions']:
                    resident = test_users.get(user_key) if user_key else None
                    frac = CondominiumFraction.objects.create(
                        establishment=est,
                        identifier=ident,
                        description=desc,
                        floor=floor,
                        fraction_type=ftype,
                        permilagem=Decimal(perm_str),
                        resident=resident,
                        is_owner=True,
                    )
                    fraction_objects.append(frac)
                    total_fractions += 1

                # Budget categories
                cat_count = CondominiumService.create_default_budget_categories(est)

                # Quota payments — 6 months history
                months = []
                for i in range(6, 0, -1):
                    m = now.month - i
                    y = now.year
                    while m <= 0:
                        m += 12
                        y -= 1
                    months.append(f'{y}-{m:02d}')

                for frac in fraction_objects:
                    quota = (frac.permilagem / Decimal('1000') * monthly_budget
                             ).quantize(Decimal('0.01'))

                    for month_idx, month_str in enumerate(months):
                        # Deterministic pseudo-random per fraction+month
                        h = hashlib.md5(
                            f'{frac.identifier}:{month_str}'.encode()
                        ).hexdigest()
                        roll = int(h[:8], 16) % 100

                        # Older months mostly paid, recent months mixed
                        if month_idx < 4:
                            paid_day = 5 if roll < 90 else 18
                            y, m = month_str.split('-')
                            paid_at = datetime(int(y), int(m), paid_day,
                                               10, 0, tzinfo=dt_tz.utc)
                            confirmed = admin_profile
                        elif month_idx == 4:
                            if roll < 70:
                                y, m = month_str.split('-')
                                paid_at = datetime(int(y), int(m), 8,
                                                   10, 0, tzinfo=dt_tz.utc)
                                confirmed = admin_profile
                            else:
                                paid_at = None
                                confirmed = None
                        else:
                            # Newest month: mostly unpaid
                            if roll < 40:
                                y, m = month_str.split('-')
                                paid_at = datetime(int(y), int(m), 3,
                                                   10, 0, tzinfo=dt_tz.utc)
                                confirmed = admin_profile
                            else:
                                paid_at = None
                                confirmed = None

                        QuotaPayment.objects.create(
                            fraction=frac,
                            month=month_str,
                            amount=quota,
                            paid_at=paid_at,
                            confirmed_by=confirmed,
                        )
                        total_payments += 1

                building.establishments_count = (
                    building.establishments.filter(is_active=True).count())
                building.save(update_fields=['establishments_count'])

                self.stdout.write(self.style.SUCCESS(
                    f'  Created: {est.name} '
                    f'({len(condo_data["fractions"])} fractions, '
                    f'{cat_count} budget categories)'))

        self.stdout.write(self.style.SUCCESS(
            f'\nTotal: {total_fractions} fractions, '
            f'{total_payments} quota payments across '
            f'{len(CONDOS)} condominiums'))
