"""Seed test ticket types for development."""
from django.core.management.base import BaseCommand
from tickets.models import TicketType
from identity.models import Profile
from geo.models import Route


class Command(BaseCommand):
    help = 'Create test ticket types for transit routes'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete existing test ticket types first')

    def handle(self, *args, **options):
        if options['reset']:
            count = TicketType.objects.filter(name__startswith='Test').delete()[0]
            self.stdout.write(f'Deleted {count} test ticket types')

        # Find a profile with ln_address (or first staff)
        operator = Profile.objects.filter(ln_address__gt='').first()
        if not operator:
            operator = Profile.objects.filter(account__is_staff=True).first()
        if not operator:
            self.stderr.write('No suitable operator profile found')
            return

        # Pick some routes
        routes = Route.objects.filter(slug__gt='').order_by('?')[:3]
        if not routes:
            self.stderr.write('No routes found')
            return

        created = 0
        for route in routes:
            tt, is_new = TicketType.objects.get_or_create(
                route=route,
                operator=operator,
                category='TRANSIT',
                defaults={
                    'name': f'Test Single Ride — {route.short_name}',
                    'description': f'Single ride ticket for route {route.short_name}',
                    'price_sats': 100,
                    'is_active': True,
                },
            )
            if is_new:
                created += 1
                self.stdout.write(f'  Created: {tt.name} ({tt.price_sats} sats)')

        self.stdout.write(self.style.SUCCESS(f'Created {created} test ticket types (operator: {operator.display_name})'))
