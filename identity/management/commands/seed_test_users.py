from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from django.contrib.auth.models import Group
from identity.models import Account, Profile, Verification
from core.models import Instance
import secrets
import string
import os
from pathlib import Path


class Command(BaseCommand):
    help = 'Create a standard set of test users for development and testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing test users before creating new ones',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=3,
            help='Number of test users to create (1-8, default: 3)',
        )
        parser.add_argument(
            '--password',
            type=str,
            default=None,
            help='Custom password for all test accounts (default: auto-generated 10 characters)',
        )

    def handle(self, *args, **options):
        count = options['count']
        reset = options['reset']
        shared_password = options['password']  # If provided, use same password for all

        # Validate count
        if count < 1 or count > 8:
            self.stdout.write(self.style.ERROR('Count must be between 1 and 8'))
            return

        # Get or create default instance
        instance, _ = Instance.objects.get_or_create(
            domain='parahub.io',
            defaults={
                'name': 'ParaHub.io',
                'is_primary': True,
            }
        )

        # Get or create test users group
        test_users_group, created = Group.objects.get_or_create(name='test_users')
        if created:
            self.stdout.write(self.style.SUCCESS('Created "test_users" group'))

        test_users = [
            {
                'username': 'alice',
                'email': 'alice@test.parahub.io',
                'local_name': 'alice',
                'display_name': 'Alice Anderson',
                'location': Point(13.4050, 52.5200, srid=4326),  # Berlin
                'reputation_score': 95.5,
                'is_verified_wot': True,
            },
            {
                'username': 'bob',
                'email': 'bob@test.parahub.io',
                'local_name': 'bob',
                'display_name': 'Bob Builder',
                'location': Point(-0.1276, 51.5074, srid=4326),  # London
                'reputation_score': 87.3,
                'is_verified_wot': True,
            },
            {
                'username': 'charlie',
                'email': 'charlie@test.parahub.io',
                'local_name': 'charlie',
                'display_name': 'Charlie Chen',
                'location': Point(121.4737, 31.2304, srid=4326),  # Shanghai
                'reputation_score': 76.8,
                'is_verified_wot': False,
            },
            {
                'username': 'diana',
                'email': 'diana@test.parahub.io',
                'local_name': 'diana',
                'display_name': 'Diana Davis',
                'location': Point(-74.0060, 40.7128, srid=4326),  # New York
                'reputation_score': 92.1,
                'is_verified_wot': True,
            },
            {
                'username': 'eve',
                'email': 'eve@test.parahub.io',
                'local_name': 'eve',
                'display_name': 'Eve Evans',
                'location': Point(2.3522, 48.8566, srid=4326),  # Paris
                'reputation_score': 15.0,
                'is_verified_wot': False,
            },
            {
                'username': 'frank',
                'email': 'frank@test.parahub.io',
                'local_name': 'frank',
                'display_name': 'Frank Foster',
                'location': Point(-118.2437, 34.0522, srid=4326),  # Los Angeles
                'reputation_score': 68.4,
                'is_verified_wot': False,
            },
            {
                'username': 'grace',
                'email': 'grace@test.parahub.io',
                'local_name': 'grace',
                'display_name': 'Grace Garcia',
                'location': Point(139.6917, 35.6895, srid=4326),  # Tokyo
                'reputation_score': 84.7,
                'is_verified_wot': True,
            },
            {
                'username': 'henry',
                'email': 'henry@test.parahub.io',
                'local_name': 'henry',
                'display_name': 'Henry Harris',
                'location': Point(-122.4194, 37.7749, srid=4326),  # San Francisco
                'reputation_score': 91.2,
                'is_verified_wot': True,
            },
        ]

        # Limit to requested count
        test_users = test_users[:count]

        if reset:
            self.stdout.write('Deleting existing test users...')
            test_usernames = [u['username'] for u in test_users]
            # Only delete accounts that are in test_users group
            deleted_accounts = Account.objects.filter(
                username__in=test_usernames,
                groups__name='test_users'
            ).delete()
            self.stdout.write(self.style.WARNING(
                f'Deleted {deleted_accounts[0]} objects (test accounts only)'
            ))

        created_count = 0
        skipped_count = 0
        user_credentials = {}  # {username: password}

        for user_data in test_users:
            username = user_data['username']

            # Check if account exists
            if Account.objects.filter(username=username).exists():
                self.stdout.write(self.style.WARNING(
                    f'Skipping {username} - already exists'
                ))
                skipped_count += 1
                continue

            # Generate individual password or use shared one
            if shared_password:
                password = shared_password
            else:
                # Generate unique 10-character password for this user
                alphabet = string.ascii_letters + string.digits
                password = ''.join(secrets.choice(alphabet) for _ in range(10))

            # Create account and add to test_users group
            account = Account.objects.create_user(
                username=username,
                email=user_data['email'],
                password=password,
                instance=instance,
            )
            account.is_test = True
            account.save(update_fields=['is_test'])
            account.groups.add(test_users_group)

            # Create profile
            profile = Profile.objects.create(
                account=account,
                instance=instance,
                local_name=user_data['local_name'],
                display_name=user_data['display_name'],
                location=user_data.get('location'),
                reputation_score=user_data.get('reputation_score', 0.0),
                is_verified_wot=user_data.get('is_verified_wot', False),
                preferred_language='en',
                is_primary=True,
            )

            created_count += 1
            user_credentials[username] = password
            verified_status = '✓ verified' if profile.is_verified_wot else '✗ not verified'
            self.stdout.write(self.style.SUCCESS(
                f'Created {username} ({profile.hna}) - {verified_status}, '
                f'reputation: {profile.reputation_score}'
            ))

        self.stdout.write(self.style.SUCCESS(
            f'\nTotal: {created_count} created, {skipped_count} skipped'
        ))

        # Create mutual verifications for WoT level 2+
        # alice and bob verify each other + charlie verifies both
        if created_count >= 2:
            wot_profiles = list(Profile.objects.filter(
                account__username__in=['alice', 'bob', 'charlie'],
                account__groups__name='test_users',
            ).select_related('account'))
            if len(wot_profiles) >= 2:
                pairs = []
                for i, p1 in enumerate(wot_profiles):
                    for p2 in wot_profiles[i+1:]:
                        pairs.append((p1, p2))
                        pairs.append((p2, p1))
                for verifier, verified in pairs:
                    Verification.objects.get_or_create(
                        verifier=verifier,
                        verified_profile=verified,
                        defaults={'verification_method': 'IN_PERSON'},
                    )
                self.stdout.write(self.style.SUCCESS(
                    f'Created {len(pairs)} mutual verifications (WoT 3+)'
                ))

        self.stdout.write('')

        # Save credentials to file if users were created
        if created_count > 0:
            password_file = Path('/opt/parahub/.test_users_password')
            try:
                with open(password_file, 'w') as f:
                    f.write(f"# Test Users Credentials\n")
                    f.write(f"# Generated by: python3 manage.py seed_test_users\n")
                    f.write(f"# DO NOT commit this file to git!\n\n")

                    if shared_password:
                        f.write(f"Password (same for all): {shared_password}\n\n")
                        f.write(f"Users ({len(user_credentials)}):\n")
                        for username in user_credentials:
                            f.write(f"  - {username}\n")
                    else:
                        f.write(f"Users with individual passwords ({len(user_credentials)}):\n\n")
                        for username, pwd in user_credentials.items():
                            f.write(f"{username}:{pwd}\n")

                # Set restrictive permissions (owner read/write only)
                os.chmod(password_file, 0o600)

                self.stdout.write(self.style.SUCCESS(
                    f'Credentials saved to: {password_file}'
                ))
                self.stdout.write(self.style.WARNING(
                    f'Make sure this file is in .gitignore!'
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'Failed to save password file: {e}'
                ))

        self.stdout.write('')
        if created_count > 0:
            if shared_password:
                self.stdout.write(self.style.SUCCESS(f'Password for all test accounts: {shared_password}'))
                self.stdout.write(self.style.SUCCESS(
                    f'You can now login with: {", ".join(user_credentials.keys())}'
                ))
            else:
                self.stdout.write(self.style.SUCCESS('Individual passwords for test accounts:'))
                for username, pwd in user_credentials.items():
                    self.stdout.write(self.style.SUCCESS(f'  {username}: {pwd}'))
