"""
Django management command to set up OIDC application for Matrix Synapse
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from oauth2_provider.models import Application
import secrets
import string

User = get_user_model()


class Command(BaseCommand):
    help = 'Creates or updates the OIDC application for Matrix Synapse integration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--regenerate-secret',
            action='store_true',
            help='Generate a new client secret',
        )

    def handle(self, *args, **options):
        self.stdout.write('Setting up Matrix Synapse OIDC application...')
        
        # Generate a secure client secret if needed
        if options['regenerate_secret']:
            alphabet = string.ascii_letters + string.digits
            client_secret = ''.join(secrets.choice(alphabet) for _ in range(64))
            self.stdout.write(self.style.WARNING(f'New client secret generated: {client_secret}'))
            self.stdout.write(self.style.WARNING('Please update this in synapse/config/homeserver.yaml'))
        else:
            client_secret = getattr(settings, 'SYNAPSE_OIDC_CLIENT_SECRET', '') or 'change-me'
        
        # Get or create a superuser for the application owner
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('No superuser found. Please create one first.'))
            return
        
        # Create or update the OIDC application
        # Note: We need to use update_or_create with raw SQL for client_secret
        # because django-oauth-toolkit hashes it by default
        app, created = Application.objects.update_or_create(
            client_id='synapse-client',
            defaults={
                'name': 'Matrix Synapse',
                'user': admin_user,
                'client_type': Application.CLIENT_CONFIDENTIAL,
                'authorization_grant_type': Application.GRANT_AUTHORIZATION_CODE,
                'redirect_uris': 'https://parahub.io/_synapse/client/oidc/callback',
                'algorithm': Application.HS256_ALGORITHM,
                'skip_authorization': True,  # Auto-approve for internal service
            }
        )
        
        # Set the client_secret directly without hashing
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE oauth2_provider_application SET client_secret = %s WHERE client_id = %s",
                [client_secret, 'synapse-client']
            )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ Created OIDC application: {app.client_id}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'✓ Updated OIDC application: {app.client_id}'))
        
        # Display application details
        self.stdout.write('\nApplication details:')
        self.stdout.write(f'  Client ID: {app.client_id}')
        self.stdout.write(f'  Client Secret: {client_secret}')  # Show the actual secret, not the hashed one
        self.stdout.write(f'  Redirect URI: {app.redirect_uris}')
        self.stdout.write(f'  Grant Type: {app.authorization_grant_type}')
        
        self.stdout.write(self.style.SUCCESS('\n✓ Matrix OIDC setup complete!'))