"""
Seed demo condominiums with realistic Portuguese building data.

Creates 2 condominiums in Lisbon:
  1. Residential building on Rua da Prata (5 floors, 10 fractions)
  2. Mixed-use building on Av. da Liberdade (7 floors, 12 fractions)

Each has realistic permilagem distribution, Portuguese family names,
and 6 months of quota payment history (paid/pending/overdue mix).
"""

import hashlib
from datetime import datetime, timedelta, timezone as dt_tz
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone


DEMO_MARKER = 'demo'

# Past assemblies — (months_ago, title_pt, description_pt, options, target_yes_ratio)
ASSEMBLY_HISTORY = [
    (
        6,
        'Aprovação do orçamento anual 2025-2026',
        'Proposta de orçamento anual para manutenção, limpeza, seguros e fundo de reserva conforme art. 40.º do DL 268/94. Discussão em assembleia ordinária.',
        ['Aprovar', 'Rejeitar', 'Abstenção'],
        0.85,
    ),
    (
        3,
        'Obras de manutenção da fachada e caleiras',
        'Orçamento de reparação da fachada sul e substituição de caleiras (3 orçamentos anexos). Custo estimado: 4.200€ — distribuição por permilagem.',
        ['Aprovar orçamento A', 'Aprovar orçamento B', 'Adiar decisão'],
        0.60,
    ),
]

# Active assembly (ongoing, ends in N days)
ACTIVE_ASSEMBLY = (
    14,
    'Contrato de manutenção de elevadores 2026',
    'Renovação anual do contrato de manutenção dos elevadores. Proposta da empresa Schindler vs. ThyssenKrupp (ver anexos). Decisão requer maioria simples (Lei 8/2022).',
    ['Schindler (atual)', 'ThyssenKrupp', 'Abstenção'],
    0.55,
)

# Recurring expense templates — (category_slug, month_offset_pattern, description_pt, amount_base, variance)
# month_offset_pattern: 'monthly' | 'quarterly' | 'annual'
EXPENSE_TEMPLATES = [
    ('limpeza', 'monthly', 'Serviço de limpeza de áreas comuns (CleanPro, Lda.)', Decimal('180.00'), Decimal('20')),
    ('manutencao', 'monthly', 'Manutenção geral — pequenas reparações', Decimal('90.00'), Decimal('60')),
    ('outros', 'monthly', 'Electricidade áreas comuns (EDP)', Decimal('75.00'), Decimal('15')),
    ('seguros', 'quarterly', 'Seguro multirrisco do edifício (Fidelidade)', Decimal('220.00'), Decimal('0')),
    ('manutencao', 'quarterly', 'Manutenção de elevadores (Schindler)', Decimal('145.00'), Decimal('0')),
    ('fundo-reserva', 'annual', 'Transferência anual para fundo comum de reserva (art. 4.º DL 268/94)', Decimal('350.00'), Decimal('0')),
]

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
            WorldObject, Establishment, EstablishmentMembership,
            CondominiumFraction, QuotaPayment,
        )
        from geo.services.condominium import CondominiumService

        instance_domain = 'parahub.io'

        if options['reset']:
            from governance.models import PollContext
            qs = Establishment.objects.filter(
                organization_type='CONDOMINIUM',
                attributes__demo=True,
            )
            est_ids = list(qs.values_list('id', flat=True))
            count = qs.count()
            # PollContext.context_id is CharField (no FK cascade) — delete explicitly
            poll_ctx_count = PollContext.objects.filter(
                context_type='tszh', context_id__in=est_ids,
            ).count()
            PollContext.objects.filter(
                context_type='tszh', context_id__in=est_ids,
            ).delete()
            qs.delete()
            if count:
                self.stdout.write(self.style.WARNING(
                    f'Deleted {count} demo condominium(s) '
                    f'+ {poll_ctx_count} assembly poll context(s)'))

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
        total_assemblies = 0
        total_votes = 0
        total_expenses = 0

        for condo_data in CONDOS:
            slug = condo_data['establishment']['slug']
            if Establishment.objects.filter(slug=slug).exists():
                self.stdout.write(self.style.WARNING(
                    f'  Skipping (exists): {slug}'))
                continue

            with transaction.atomic():
                # WorldObject (formerly Building)
                bld = condo_data['building']
                wo, _ = WorldObject.objects.get_or_create(
                    full_address=bld['full_address'],
                    defaults={k: v for k, v in bld.items()
                              if k != 'full_address'},
                )

                # Establishment
                est_info = condo_data['establishment']
                est = Establishment.objects.create(
                    owner=admin_profile,
                    world_object=wo,
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

                # Assemblies (past ended + 1 active)
                assemblies_made, votes_made = self._create_assemblies(
                    est, fraction_objects, test_users, admin_profile, now)
                total_assemblies += assemblies_made
                total_votes += votes_made

                # Expenses (6 months of realistic spending across categories)
                expenses_made = self._create_expenses(est, months, now)
                total_expenses += expenses_made

                wo.establishments_count = (
                    wo.establishments.filter(is_active=True).count())
                wo.save(update_fields=['establishments_count'])

                self.stdout.write(self.style.SUCCESS(
                    f'  Created: {est.name} '
                    f'({len(condo_data["fractions"])} fractions, '
                    f'{cat_count} budget cats, '
                    f'{assemblies_made} assemblies/{votes_made} votes, '
                    f'{expenses_made} expenses)'))

        self.stdout.write(self.style.SUCCESS(
            f'\nTotal across {len(CONDOS)} condominiums: '
            f'{total_fractions} fractions, '
            f'{total_payments} quota payments, '
            f'{total_assemblies} assemblies ({total_votes} votes), '
            f'{total_expenses} expenses'))

    # ------------------------------------------------------------------
    # Assembly seeding
    # ------------------------------------------------------------------
    def _create_assemblies(self, est, fraction_objects, test_users,
                           admin_profile, now):
        """Create 2 past (ended) + 1 active assembly poll with realistic votes."""
        from governance.models import (
            Poll, PollOption, PollContext, PollEligibleVoter, PollVote,
        )
        from geo.services.condominium import CondominiumService

        context, _ = PollContext.objects.get_or_create(
            context_type='tszh', context_id=est.id,
            defaults={'created_by': admin_profile},
        )

        assemblies_made = 0
        votes_made = 0

        # Past assemblies — ended
        for months_ago, title, desc, option_texts, yes_ratio in ASSEMBLY_HISTORY:
            start = now - timedelta(days=months_ago * 30)
            end = start + timedelta(days=15)
            poll = Poll.objects.create(
                context=context, title=title, description=desc,
                created_by=admin_profile,
                start_time=start, end_time=end,
                use_weights=True, weight_source='ownership_shares',
                quorum_type='custom', quorum_percent=Decimal('50'),
                status='ended',
            )
            options = [
                PollOption.objects.create(poll=poll, text=t, order=i)
                for i, t in enumerate(option_texts)
            ]
            CondominiumService.setup_poll_voters(poll, est)
            votes_made += self._cast_votes(
                poll, fraction_objects, options, yes_ratio,
                vote_day=start + timedelta(days=5),
                seed=f'{est.slug}:{months_ago}',
            )
            assemblies_made += 1

        # Active assembly
        days_left, title, desc, option_texts, yes_ratio = ACTIVE_ASSEMBLY
        start = now - timedelta(days=3)
        end = now + timedelta(days=days_left)
        poll = Poll.objects.create(
            context=context, title=title, description=desc,
            created_by=admin_profile,
            start_time=start, end_time=end,
            use_weights=True, weight_source='ownership_shares',
            quorum_type='custom', quorum_percent=Decimal('50'),
            status='active',
        )
        options = [
            PollOption.objects.create(poll=poll, text=t, order=i)
            for i, t in enumerate(option_texts)
        ]
        CondominiumService.setup_poll_voters(poll, est)
        # Partial turnout on active poll
        votes_made += self._cast_votes(
            poll, fraction_objects, options, yes_ratio,
            vote_day=start + timedelta(days=1),
            seed=f'{est.slug}:active', participation=0.45,
        )
        assemblies_made += 1

        return assemblies_made, votes_made

    def _cast_votes(self, poll, fraction_objects, options, yes_ratio,
                    vote_day, seed, participation=0.80):
        """Cast deterministic demo votes. yes_ratio skews option 0; participation limits turnout."""
        from governance.models import PollVote

        voted = 0
        seen_profiles = set()
        for frac in fraction_objects:
            if not frac.resident_id or not frac.is_owner:
                continue
            if frac.resident_id in seen_profiles:
                continue
            seen_profiles.add(frac.resident_id)

            h = hashlib.md5(f'{seed}:{frac.resident_id}'.encode()).hexdigest()
            turnout_roll = int(h[:4], 16) % 100
            if turnout_roll >= int(participation * 100):
                continue

            choice_roll = int(h[4:8], 16) % 100
            if choice_roll < int(yes_ratio * 100):
                option = options[0]
            elif choice_roll < int(yes_ratio * 100) + 20 and len(options) > 1:
                option = options[1]
            else:
                option = options[-1]

            PollVote.objects.create(
                poll=poll, voter=frac.resident, option=option,
                pgp_signature='',
                signed_payload={
                    'poll_id': poll.id, 'option_id': option.id,
                    'timestamp': vote_day.isoformat(),
                    'demo': True,
                },
                effective_weight=frac.permilagem,
            )
            voted += 1

        return voted

    # ------------------------------------------------------------------
    # Expense seeding
    # ------------------------------------------------------------------
    def _create_expenses(self, est, months, now):
        """Create 6 months of realistic demo expenses tied to budget categories."""
        from treasury.models import BudgetCategory, Expense

        categories = {c.slug: c for c in BudgetCategory.objects.filter(establishment=est)}
        admin = est.owner
        count = 0

        for month_idx, month_str in enumerate(months):
            y, m = [int(x) for x in month_str.split('-')]
            for template_idx, (cat_slug, cadence, desc, base, variance) in enumerate(EXPENSE_TEMPLATES):
                cat = categories.get(cat_slug)
                if not cat:
                    continue
                # Apply cadence filter
                if cadence == 'quarterly' and month_idx % 3 != 0:
                    continue
                if cadence == 'annual' and month_idx != 0:
                    continue

                h = hashlib.md5(f'{est.slug}:{month_str}:{template_idx}'.encode()).hexdigest()
                delta = (int(h[:4], 16) % 2001 - 1000) / Decimal('1000')  # -1.0..+1.0
                amount = (base + variance * delta).quantize(Decimal('0.01'))
                if amount <= 0:
                    amount = base

                # Most expenses APPROVED; newest month mix DRAFT
                is_latest = month_idx == len(months) - 1
                status = Expense.Status.DRAFT if (is_latest and int(h[4:6], 16) % 3 == 0) \
                    else Expense.Status.APPROVED

                day = 5 + (int(h[6:8], 16) % 20)
                # Clamp day to valid range for month
                try:
                    exp_date = datetime(y, m, day).date()
                except ValueError:
                    exp_date = datetime(y, m, 28).date()

                Expense.objects.create(
                    establishment=est, category=cat, created_by=admin,
                    amount=amount, description=desc, date=exp_date,
                    status=status, epoch_label=month_str,
                )
                count += 1

        return count
