"""Set up Django Site object (domain + name).

Usage:
    python3 manage.py setup_site
"""
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create or update Django Site object for parahub.io'

    def handle(self, *args, **options):
        site, created = Site.objects.update_or_create(
            id=1,
            defaults={
                'domain': 'parahub.io',
                'name': 'Parahub',
            },
        )

        if created:
            self.stdout.write(self.style.SUCCESS('Site object created successfully'))
        else:
            self.stdout.write(self.style.SUCCESS('Site object updated successfully'))

        self.stdout.write(f'Site domain: {site.domain}')
        self.stdout.write(f'Site name: {site.name}')
