"""Create superuser account with local Instance.

Usage:
    python3 manage.py create_superuser_account
    SUPERUSER_PASSWORD=secret python3 manage.py create_superuser_account
"""
import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models import Instance


class Command(BaseCommand):
    help = 'Create superuser account and local Instance'

    def handle(self, *args, **options):
        instance, _ = Instance.objects.get_or_create(
            domain='localhost',
            defaults={
                'name': 'Local ParaHub Instance',
                'public_key': 'placeholder_public_key',
                'is_active': True,
            },
        )

        User = get_user_model()
        password = os.environ.get('SUPERUSER_PASSWORD', secrets.token_urlsafe(16))

        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@parahub.local',
                password=password,
                instance=instance,
            )
            self.stdout.write(self.style.SUCCESS('Superuser created successfully'))
            self.stdout.write(f'Username: admin')
            self.stdout.write(f'Password: {password}')
        else:
            self.stdout.write('Superuser already exists')
