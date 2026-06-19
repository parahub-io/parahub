"""Seed test ticket types for development."""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q

from tickets.models import TicketType
from identity.models import Profile
from geo.models import Establishment, Route


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
                name=f'Test Single Ride — {route.short_name}',
                defaults={
                    'description': f'Single ride ticket for route {route.short_name}',
                    'price_sats': 100,
                    'is_active': True,
                },
            )
            if is_new:
                created += 1
                self.stdout.write(f'  Created: {tt.name} ({tt.price_sats} sats)')

        # EUR-priced type with 90-min validity window (sats quoted at purchase time)
        eur_route = routes[0]
        tt, is_new = TicketType.objects.get_or_create(
            route=eur_route,
            operator=operator,
            category='TRANSIT',
            name=f'Test Single Ride (EUR) — {eur_route.short_name}',
            defaults={
                'description': f'EUR-priced single ride for route {eur_route.short_name}',
                'price_eur': Decimal('1.50'),
                'price_sats': None,
                'validity_minutes': 90,
                'is_active': True,
            },
        )
        if is_new:
            created += 1
            self.stdout.write(f'  Created: {tt.name} ({tt.price_eur} EUR, 90 min)')

        # Concession (student) EUR type with window
        tt, is_new = TicketType.objects.get_or_create(
            route=eur_route,
            operator=operator,
            category='TRANSIT',
            name=f'Test Student Ride — {eur_route.short_name}',
            defaults={
                'description': f'Student fare for route {eur_route.short_name}',
                'price_eur': Decimal('0.75'),
                'price_sats': None,
                'validity_minutes': 90,
                'concession_category': 'STUDENT',
                'is_active': True,
            },
        )
        if is_new:
            created += 1
            self.stdout.write(f'  Created: {tt.name} ({tt.price_eur} EUR, STUDENT)')

        # Network-wide day pass on the route's agency (24h window)
        tt, is_new = TicketType.objects.get_or_create(
            agency=eur_route.agency,
            operator=operator,
            category='TRANSIT',
            name=f'Test Day Pass — {eur_route.agency.name}',
            defaults={
                'description': f'Network-wide day pass for {eur_route.agency.name}',
                'price_eur': Decimal('4.00'),
                'price_sats': None,
                'validity_minutes': 1440,
                'is_active': True,
            },
        )
        if is_new:
            created += 1
            self.stdout.write(f'  Created: {tt.name} ({tt.price_eur} EUR, 24h, network)')

        # Establishment-operated type, if any establishment has a payment address
        est = Establishment.objects.filter(
            Q(ln_address__gt='') | Q(spark_address__gt=''),
        ).first()
        if est:
            tt, is_new = TicketType.objects.get_or_create(
                route=eur_route,
                operator=operator,
                operator_establishment=est,
                category='TRANSIT',
                name=f'Test Org Ride — {eur_route.short_name}',
                defaults={
                    'description': f'Establishment-operated ticket ({est.name})',
                    'price_eur': Decimal('2.00'),
                    'price_sats': None,
                    'is_active': True,
                },
            )
            if is_new:
                created += 1
                self.stdout.write(f'  Created: {tt.name} (operator: {est.name})')
        else:
            self.stdout.write('  No establishment with payment address — skipped org-operated type')

        self.stdout.write(self.style.SUCCESS(f'Created {created} test ticket types (operator: {operator.display_name})'))
