"""
Seed demo contracts for Show HN readiness.
Creates 3 contracts in different lifecycle states between test users.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from identity.models import Profile
from contracts.models import Contract

# Demo contracts use a known SHA256 prefix for identification and cleanup
DEMO_SHA256_PREFIX = '0000000000000000'


class Command(BaseCommand):
    help = 'Create demo contracts between test users for Show HN readiness'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete demo contracts before recreating (only demo data)',
        )

    def _get_test_profiles(self):
        profiles = {}
        for name in ('alice', 'bob', 'charlie'):
            try:
                profiles[name] = Profile.objects.get(
                    local_name=name, instance__domain='parahub.io'
                )
            except Profile.DoesNotExist:
                pass
        return profiles

    def handle(self, *args, **options):
        if options['reset']:
            deleted = Contract.objects.filter(
                file_sha256__startswith=DEMO_SHA256_PREFIX
            ).delete()
            self.stdout.write(self.style.WARNING(f'Deleted {deleted[0]} demo contracts'))

        profiles = self._get_test_profiles()
        if len(profiles) < 3:
            self.stdout.write(self.style.ERROR(
                'Need alice, bob, charlie. Run: python3 manage.py seed_test_users --count 3'
            ))
            return

        alice, bob, charlie = profiles['alice'], profiles['bob'], profiles['charlie']
        now = timezone.now()
        created = 0

        # --- Contract 1: PENDING_PARTNER (awaiting signature) ---
        c1, c1_new = Contract.objects.get_or_create(
            file_sha256=DEMO_SHA256_PREFIX + 'a' * 48,
            defaults={
                'creator': alice,
                'partner': bob,
                'title': 'Web design services for community garden website',
                'creator_signature': 'DEMO_PGP_SIG_ALICE_C1',
                'status': Contract.Status.PENDING_PARTNER,
            }
        )
        if c1_new:
            created += 1
            self.stdout.write(self.style.SUCCESS(
                f'  ✓ Contract 1 (PENDING_PARTNER): {c1.title}'
            ))

        # --- Contract 2: SIGNED (both parties signed, work in progress) ---
        c2, c2_new = Contract.objects.get_or_create(
            file_sha256=DEMO_SHA256_PREFIX + 'b' * 48,
            defaults={
                'creator': bob,
                'partner': charlie,
                'title': 'Bicycle repair in exchange for Portuguese language tutoring',
                'creator_signature': 'DEMO_PGP_SIG_BOB_C2',
                'partner_signature': 'DEMO_PGP_SIG_CHARLIE_C2',
                'status': Contract.Status.SIGNED,
                'partner_signed_at': now - timedelta(days=3),
            }
        )
        if c2_new:
            created += 1
            self.stdout.write(self.style.SUCCESS(
                f'  ✓ Contract 2 (SIGNED): {c2.title}'
            ))

        # --- Contract 3: COMPLETED (both parties confirmed completion, with reviews) ---
        c3, c3_new = Contract.objects.get_or_create(
            file_sha256=DEMO_SHA256_PREFIX + 'c' * 48,
            defaults={
                'creator': charlie,
                'partner': alice,
                'title': 'Photography session for profile and portfolio shots',
                'creator_signature': 'DEMO_PGP_SIG_CHARLIE_C3',
                'partner_signature': 'DEMO_PGP_SIG_ALICE_C3',
                'status': Contract.Status.COMPLETED,
                'partner_signed_at': now - timedelta(days=14),
                'creator_completed_at': now - timedelta(days=2),
                'partner_completed_at': now - timedelta(days=1),
            }
        )
        if c3_new:
            created += 1
            from contracts.models import ContractReview
            # Both parties review each other
            ContractReview.objects.get_or_create(
                contract=c3, reviewer=charlie,
                defaults={
                    'reviewed': alice,
                    'rating': 5,
                    'comment': 'Excellent work! The photos came out beautifully. Very professional and easy to work with.',
                }
            )
            ContractReview.objects.get_or_create(
                contract=c3, reviewer=alice,
                defaults={
                    'reviewed': charlie,
                    'rating': 4,
                    'comment': 'Great client, clear brief and punctual. Would work together again.',
                }
            )
            self.stdout.write(self.style.SUCCESS(
                f'  ✓ Contract 3 (COMPLETED + reviews): {c3.title}'
            ))

        self.stdout.write(self.style.SUCCESS(f'\nTotal: {created} demo contracts created'))
