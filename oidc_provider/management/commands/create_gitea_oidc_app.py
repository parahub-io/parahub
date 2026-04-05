"""
Django management command to create OIDC application for Gitea integration
"""

from django.core.management.base import BaseCommand
from oauth2_provider.models import Application
from django.contrib.auth import get_user_model
from django.conf import settings
import secrets
import os

User = get_user_model()


class Command(BaseCommand):
    help = 'Creates or updates OIDC application for Gitea integration'

    def handle(self, *args, **options):
        # Get or create admin user
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('No admin user found. Please create an admin user first.'))
            return

        # Get client secret from environment or generate a secure one
        client_secret = os.getenv('GITEA_OIDC_CLIENT_SECRET')
        if not client_secret:
            client_secret = secrets.token_urlsafe(32)
            self.stdout.write(self.style.WARNING(
                f'GITEA_OIDC_CLIENT_SECRET not set in environment. Generated new secret.'
            ))
            self.stdout.write(self.style.WARNING(
                f'Add this to your .env file: GITEA_OIDC_CLIENT_SECRET={client_secret}'
            ))

        # Delete existing app to recreate with plain secret
        Application.objects.filter(name='Gitea SSO').delete()

        # Create new application with plain secret (django-oauth-toolkit will hash it)
        app = Application.objects.create(
            name='Gitea SSO',
            user=admin_user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris='https://git.parahub.io/user/oauth2/parahub/callback',
            client_id='gitea-sso-client',
            client_secret=client_secret,
            skip_authorization=True,  # Auto-approve for seamless SSO
        )
        created = True

        if created:
            self.stdout.write(self.style.SUCCESS(f'Created OIDC application for Gitea'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Updated OIDC application for Gitea'))

        self.stdout.write(f'\nClient ID: {app.client_id}')
        self.stdout.write(f'Client Secret (plain): {client_secret}')
        self.stdout.write(f'Client Secret (hashed in DB): {app.client_secret}')
        self.stdout.write(f'Redirect URI: {app.redirect_uris}')
        self.stdout.write('\nUse the plain client secret for Gitea OIDC configuration!')
        self.stdout.write('\nGitea OIDC Configuration:')
        self.stdout.write('  Provider Name: Parahub')
        self.stdout.write(f'  Client ID: {app.client_id}')
        self.stdout.write(f'  Client Secret: {client_secret}')
        self.stdout.write('  OpenID Connect Discovery URL: https://parahub.io/.well-known/openid-configuration')
        self.stdout.write('  OR manually configure:')
        self.stdout.write('    Authorization URL: https://parahub.io/o/authorize/')
        self.stdout.write('    Token URL: https://parahub.io/o/token/')
        self.stdout.write('    UserInfo URL: https://parahub.io/o/userinfo/')
