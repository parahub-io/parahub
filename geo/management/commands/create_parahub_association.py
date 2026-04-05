"""
Management command to create the official PARAHUB - ASSOCIAÇÃO establishment.

This creates the legal entity representing the Portuguese association
with proper configuration for statute acceptance.

Usage:
    python manage.py create_parahub_association [--owner-hna=user@parahub.io]
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from identity.models import Profile
from geo.models import Establishment, EstablishmentMembership

ESTATUTOS_PATH = Path(__file__).resolve().parents[3] / 'docs' / 'estatutos.md'


class Command(BaseCommand):
    help = 'Create PARAHUB - ASSOCIAÇÃO establishment with proper configuration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--owner-hna',
            type=str,
            help='HNA of the profile to set as owner (e.g., admin@parahub.io). If not provided, uses first superuser profile.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation if establishment already exists',
        )

    def handle(self, *args, **options):
        owner_hna = options.get('owner_hna')
        force = options.get('force', False)

        try:
            # Check if establishment already exists
            existing_est = Establishment.objects.filter(
                slug='parahub-associacao'
            ).first()

            # Load terms content from ESTATUTOS.md
            terms_content = ''
            if ESTATUTOS_PATH.exists():
                terms_content = ESTATUTOS_PATH.read_text(encoding='utf-8')
                self.stdout.write(f'Loaded estatutos from {ESTATUTOS_PATH} ({len(terms_content)} chars)')
            else:
                self.stdout.write(self.style.WARNING(f'ESTATUTOS.md not found at {ESTATUTOS_PATH}'))

            if existing_est and not force:
                # Update existing establishment with new terms
                existing_est.terms_url = '/org/parahub-associacao/estatutos'
                existing_est.terms_content = terms_content
                existing_est.save(update_fields=['terms_url', 'terms_content'])
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Updated existing establishment: {existing_est.name} (ID: {existing_est.id})'
                    )
                )
                self.stdout.write(self.style.SUCCESS(f'  Terms URL: {existing_est.terms_url}'))
                self.stdout.write(self.style.SUCCESS(f'  Terms content: {len(terms_content)} chars'))
                return

            # Get owner profile
            if owner_hna:
                try:
                    local_name, domain = owner_hna.split('@')
                    owner_profile = Profile.objects.get(
                        local_name=local_name,
                        instance__domain=domain
                    )
                except ValueError:
                    raise CommandError(
                        f'Invalid HNA format: {owner_hna}. Expected format: username@domain'
                    )
                except Profile.DoesNotExist:
                    raise CommandError(f'Profile not found: {owner_hna}')
            else:
                owner_profile = Profile.objects.filter(
                    account__is_superuser=True,
                ).first()
                if not owner_profile:
                    raise CommandError(
                        'No superuser profile found. '
                        'Please specify --owner-hna or create a superuser first.'
                    )

            with transaction.atomic():
                if existing_est and force:
                    self.stdout.write(
                        self.style.WARNING(f'Deleting existing establishment: {existing_est.name}')
                    )
                    existing_est.delete()

                est = Establishment.objects.create(
                    owner=owner_profile,
                    name='PARAHUB - ASSOCIAÇÃO',
                    slug='parahub-associacao',
                    description=(
                        'Associação sem fins lucrativos para o desenvolvimento, apoio, '
                        'promoção e evolução de uma infraestrutura de informação global, '
                        'descentralizada e federada (Open Source). Registada em Portugal.'
                    ),
                    is_online=True,
                    organization_type=Establishment.OrganizationType.ASSOCIATION,
                    legal_entity_id='',
                    requires_terms_acceptance=True,
                    terms_url='/org/parahub-associacao/estatutos',
                    terms_content=terms_content,
                    member_visibility=Establishment.MemberVisibility.PUBLIC,
                    is_active=True,
                    is_verified=True,
                )

                EstablishmentMembership.objects.create(
                    profile=owner_profile,
                    establishment=est,
                    role=EstablishmentMembership.Role.OWNER,
                )

                self.stdout.write(
                    self.style.SUCCESS(f'Successfully created establishment: {est.name}')
                )
                self.stdout.write(self.style.SUCCESS(f'  ID: {est.id}'))
                self.stdout.write(self.style.SUCCESS(f'  Slug: {est.slug}'))
                self.stdout.write(self.style.SUCCESS(f'  Owner: {owner_profile.local_name}'))
                self.stdout.write(self.style.SUCCESS(f'  Type: {est.organization_type}'))
                self.stdout.write(self.style.SUCCESS(f'  Terms URL: {est.terms_url}'))
                self.stdout.write('')
                self.stdout.write(
                    'Users can now join the association by accepting the estatutos at /profile'
                )

        except Exception as e:
            raise CommandError(f'Failed to create establishment: {str(e)}')
