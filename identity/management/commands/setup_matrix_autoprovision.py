"""
Django management command to set up automatic Matrix user provisioning
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import httpx
import json


class Command(BaseCommand):
    help = 'Configure Synapse for automatic user provisioning and set admin token'

    def add_arguments(self, parser):
        parser.add_argument(
            '--admin-user',
            type=str,
            default='admin',
            help='Admin user for Synapse',
        )
        parser.add_argument(
            '--shared-secret',
            type=str,
            default=settings.SYNAPSE_REGISTRATION_SHARED_SECRET,
            help='Shared secret for user registration (default: from settings/env)',
        )

    def handle(self, *args, **options):
        self.stdout.write('Setting up Matrix auto-provisioning...')
        
        admin_user = options['admin_user']
        shared_secret = options['shared_secret']
        
        # Update Django settings with shared secret
        settings_file = '/opt/parahub/parahub/settings.py'
        
        settings_additions = f"""
# Matrix/Synapse Integration Settings
SYNAPSE_REGISTRATION_SHARED_SECRET = '{shared_secret}'
SYNAPSE_ADMIN_USER = '{admin_user}'
"""
        
        # Check if settings already exist
        try:
            with open(settings_file, 'r') as f:
                content = f.read()
                if 'SYNAPSE_REGISTRATION_SHARED_SECRET' not in content:
                    with open(settings_file, 'a') as f:
                        f.write(settings_additions)
                    self.stdout.write(self.style.SUCCESS('✓ Added Matrix settings to Django configuration'))
                else:
                    self.stdout.write(self.style.WARNING('Matrix settings already exist in Django configuration'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to update settings: {e}'))
        
        # Update Synapse configuration to enable shared secret registration
        synapse_config_file = '/opt/parahub/synapse/config/homeserver.yaml'
        
        try:
            with open(synapse_config_file, 'r') as f:
                lines = f.readlines()
            
            # Find and update registration_shared_secret
            updated = False
            for i, line in enumerate(lines):
                if line.startswith('registration_shared_secret:'):
                    lines[i] = f'registration_shared_secret: "{shared_secret}"\n'
                    updated = True
                    break
            
            if updated:
                with open(synapse_config_file, 'w') as f:
                    f.writelines(lines)
                self.stdout.write(self.style.SUCCESS('✓ Updated Synapse configuration with shared secret'))
            else:
                self.stdout.write(self.style.WARNING('registration_shared_secret not found in Synapse config'))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to update Synapse config: {e}'))
        
        self.stdout.write(self.style.SUCCESS('\n✓ Matrix auto-provisioning setup complete!'))
        self.stdout.write('\nNext steps:')
        self.stdout.write('1. Restart Synapse: docker restart parahub-synapse')
        self.stdout.write('2. Restart Django: sudo systemctl restart parahub-uvicorn')
        self.stdout.write('3. Test the integration at /messages')