"""
Django management command to create OIDC application for PeerTube integration
"""

from django.core.management.base import BaseCommand
from oauth2_provider.models import Application
from django.contrib.auth import get_user_model
import secrets
import os

User = get_user_model()


class Command(BaseCommand):
    help = 'Creates or updates OIDC application for PeerTube integration'

    def handle(self, *args, **options):
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('No admin user found. Please create an admin user first.'))
            return

        client_secret = os.getenv('PEERTUBE_OIDC_CLIENT_SECRET')
        if not client_secret:
            client_secret = secrets.token_urlsafe(32)
            self.stdout.write(self.style.WARNING(
                f'PEERTUBE_OIDC_CLIENT_SECRET not set in environment. Generated new secret.'
            ))
            self.stdout.write(self.style.WARNING(
                f'Add this to your .env file: PEERTUBE_OIDC_CLIENT_SECRET={client_secret}'
            ))

        # Delete existing app to recreate with plain secret
        Application.objects.filter(name='PeerTube SSO').delete()

        app = Application.objects.create(
            name='PeerTube SSO',
            user=admin_user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris='https://video.parahub.io/plugins/auth-openid-connect/router/code-cb',
            client_id='peertube-sso-client',
            client_secret=client_secret,
            algorithm='RS256',
            skip_authorization=True,
        )

        self.stdout.write(self.style.SUCCESS(f'Created OIDC application for PeerTube'))
        self.stdout.write(f'\nClient ID: {app.client_id}')
        self.stdout.write(f'Client Secret (plain): {client_secret}')
        self.stdout.write(f'Redirect URI: {app.redirect_uris}')
        self.stdout.write('\nPeerTube OIDC Plugin Configuration:')
        self.stdout.write(f'  Client ID: {app.client_id}')
        self.stdout.write(f'  Client Secret: {client_secret}')
        self.stdout.write('  Discovery URL: https://parahub.io/.well-known/openid-configuration')
        self.stdout.write('  Scope: openid profile email')
        self.stdout.write('  Username claim: preferred_username')
        self.stdout.write('  Display name claim: name')
