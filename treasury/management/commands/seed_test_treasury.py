"""
Seed test treasury allocations for development/testing.
Usage: python manage.py seed_test_treasury [--reset] [--establishment slug]
"""
import random

from django.core.management.base import BaseCommand

from treasury.models import BudgetCategory, BudgetAllocation, TreasuryAuditLog, BudgetEpoch
from treasury.services import TreasuryService, TreasuryAuditService
from identity.models import Profile
from geo.models import Establishment, EstablishmentMembership


class Command(BaseCommand):
    help = 'Seed test budget allocations for treasury'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete existing allocations first')
        parser.add_argument(
            '--establishment', type=str, default='parahub-associacao',
            help='Establishment slug (default: parahub-associacao)'
        )

    def handle(self, *args, **options):
        slug = options['establishment']

        # Ensure establishment exists
        estab = Establishment.objects.filter(slug=slug).first()
        if not estab:
            self.stderr.write(self.style.WARNING(
                f"No '{slug}' establishment found. Creating one..."
            ))
            owner = Profile.objects.first()
            if not owner:
                self.stderr.write(self.style.ERROR("No profiles exist. Run seed_test_users first."))
                return
            estab = Establishment.objects.create(
                name=slug.replace('-', ' ').title(),
                slug=slug,
                owner=owner,
                organization_type=Establishment.OrganizationType.ASSOCIATION,
            )
            self.stdout.write(f"Created establishment: {estab.name}")

        # Enable treasury if not already
        if not estab.treasury_enabled:
            estab.treasury_enabled = True
            estab.treasury_eligible_levels = ['efetivo', 'fundador']
            estab.save(update_fields=['treasury_enabled', 'treasury_eligible_levels'])
            self.stdout.write(f"Enabled treasury on {estab.slug}")

        if options['reset']:
            count = BudgetAllocation.objects.filter(establishment=estab).delete()[0]
            self.stdout.write(f"Deleted {count} existing allocations")
            BudgetEpoch.objects.filter(establishment=estab).delete()
            TreasuryAuditLog.objects.filter(establishment=estab).delete()

        # Ensure default categories exist for this establishment
        categories = list(BudgetCategory.objects.filter(establishment=estab, is_active=True))
        if not categories:
            self.stdout.write("No categories for this establishment, creating defaults...")
            default_cats = [
                {'slug': 'operations', 'name': 'Operations', 'icon': 'settings', 'order': 0, 'description': 'Rent, utilities, accounting, legal, supplies'},
                {'slug': 'team', 'name': 'Team', 'icon': 'users', 'order': 1, 'description': 'Salaries, fees, compensation, HR'},
                {'slug': 'development', 'name': 'Development', 'icon': 'rocket', 'order': 2, 'description': 'Product/service improvement, R&D, innovation'},
                {'slug': 'marketing', 'name': 'Marketing', 'icon': 'megaphone', 'order': 3, 'description': 'Promotion, advertising, member acquisition, PR'},
                {'slug': 'community', 'name': 'Community', 'icon': 'heart-handshake', 'order': 4, 'description': 'Events, workshops, education, social activities'},
                {'slug': 'reserve', 'name': 'Reserve Fund', 'icon': 'shield', 'order': 5, 'description': 'Emergency fund, savings, contingency'},
            ]
            for cat_data in default_cats:
                BudgetCategory.objects.get_or_create(
                    establishment=estab, slug=cat_data['slug'],
                    defaults={**cat_data, 'establishment': estab},
                )
            categories = list(BudgetCategory.objects.filter(establishment=estab, is_active=True))

        # Get test profiles and ensure they have membership
        profiles = list(Profile.objects.filter(is_primary=True)[:6])
        if not profiles:
            self.stderr.write(self.style.ERROR("No profiles found. Run seed_test_users first."))
            return

        eligible_profiles = []
        levels = ['efetivo', 'fundador']
        for i, profile in enumerate(profiles):
            membership, created = EstablishmentMembership.objects.get_or_create(
                profile=profile,
                establishment=estab,
                defaults={
                    'role': EstablishmentMembership.Role.MEMBER,
                    'membership_level': levels[i % 2],
                }
            )
            if created:
                self.stdout.write(f"  Added {profile.hna} as {membership.membership_level}")
            elif not membership.membership_level:
                membership.membership_level = levels[i % 2]
                membership.save(update_fields=['membership_level'])
                self.stdout.write(f"  Updated {profile.hna} to {membership.membership_level}")
            eligible_profiles.append(profile)

        cat_ids = [c.id for c in categories]

        # Seed allocations with varied distributions
        # Presets: operations, team, development, marketing, community, reserve
        presets = [
            # Manager: heavy on ops and team
            {cat_ids[0]: 30, cat_ids[1]: 30, cat_ids[2]: 15, cat_ids[3]: 10, cat_ids[4]: 10, cat_ids[5]: 5},
            # Balanced voter
            {cat_ids[0]: 17, cat_ids[1]: 17, cat_ids[2]: 17, cat_ids[3]: 17, cat_ids[4]: 17, cat_ids[5]: 15},
            # Growth-focused
            {cat_ids[0]: 10, cat_ids[1]: 15, cat_ids[2]: 25, cat_ids[3]: 30, cat_ids[4]: 10, cat_ids[5]: 10},
            # Community builder
            {cat_ids[0]: 10, cat_ids[1]: 10, cat_ids[2]: 10, cat_ids[3]: 10, cat_ids[4]: 45, cat_ids[5]: 15},
            # Cautious saver
            {cat_ids[0]: 15, cat_ids[1]: 20, cat_ids[2]: 10, cat_ids[3]: 10, cat_ids[4]: 15, cat_ids[5]: 30},
            # Random
            None,
        ]

        created_count = 0
        for i, profile in enumerate(eligible_profiles):
            if BudgetAllocation.objects.filter(profile=profile, establishment=estab).exists():
                self.stdout.write(f"  {profile.hna} already has allocation, skipping")
                continue

            if i < len(presets) and presets[i] is not None:
                allocations = presets[i]
            else:
                # Generate random allocation that sums to 100
                raw = [random.randint(5, 40) for _ in cat_ids]
                total = sum(raw)
                allocations = {}
                for j, cid in enumerate(cat_ids):
                    if j == len(cat_ids) - 1:
                        allocations[cid] = round(100 - sum(allocations.values()), 1)
                    else:
                        allocations[cid] = round(raw[j] / total * 100, 1)

            TreasuryService.update_allocation(
                profile=profile,
                establishment=estab,
                allocations={k: float(v) for k, v in allocations.items()},
            )
            created_count += 1
            self.stdout.write(f"  Created allocation for {profile.hna}")

        # Show current medians
        medians = TreasuryService.calculate_current_medians(estab)
        self.stdout.write(self.style.SUCCESS(f"\nCreated {created_count} allocations"))
        self.stdout.write("Current medians:")
        for m in medians:
            self.stdout.write(f"  {m['name']}: {m['median_percent']}%")
