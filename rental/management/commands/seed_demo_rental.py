"""
Seed demo rental bookables (SEO-isolated).

Creates two bookable demo items so /rental is explorable:
  - RANGE: an electric motorcycle rented per day (with one existing booking)
  - SLOTS: a rehearsal room rented per hour

Demo isolation: each item carries `attributes['__demo_seed']=True` (drives the
API `is_demo` flag) and `spec_data['__demo_seed']=True` (cleanup convention,
matching seed_demo_items). --reset removes only marked demo data.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from identity.models import Profile
from market.models import Item
from geo.models import Establishment
from rental.models import Bookable, Availability, Booking

DEMO_MARKER = '__demo_seed'


class Command(BaseCommand):
    help = 'Create demo rental bookables (RANGE motorcycle + SLOTS room), SEO-isolated'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Delete demo rental items before recreating (only demo data)')

    def _owner(self):
        # Prefer the alice test profile, then a superuser, then anyone.
        return (Profile.objects.filter(local_name='alice', instance__domain='parahub.io').first()
                or Profile.objects.filter(account__is_superuser=True).first()
                or Profile.objects.first())

    def handle(self, *args, **opts):
        owner = self._owner()
        if not owner:
            self.stderr.write('No Profile found — seed users first.')
            return

        if opts['reset']:
            n = Item.objects.filter(spec_data__has_key=DEMO_MARKER,
                                    attributes__has_key=DEMO_MARKER).delete()
            self.stdout.write(f'Reset: removed {n[0]} demo rental objects')

        # Attach to an establishment the owner manages, if any (else P2P).
        est = Establishment.objects.filter(owner=owner, is_active=True).first()
        marker = {DEMO_MARKER: True}
        now = timezone.now()

        # --- RANGE: electric motorcycle, per day ---
        moto = Item.objects.create(
            owner=owner, establishment=est, type=Item.ItemType.CREDIT,
            title='Sur-Ron Ultra Bee — demo rental',
            description='Electric motorcycle, rented per day. Demonstration listing.',
            pricing_options=[{'type': 'rent', 'amount': 25, 'currency': 'EUR', 'unit': 'day'}],
            attributes=dict(marker), spec_data=dict(marker),
        )
        mb = Bookable.objects.create(item=moto, booking_mode=Bookable.Mode.RANGE,
                                     confirmation=Bookable.Confirmation.AUTO)
        Availability.objects.create(bookable=mb, start='08:00', stop='20:00')
        Booking.objects.create(bookable=mb, renter=owner, created_by=owner,
                               start=now + timedelta(days=2), end=now + timedelta(days=4),
                               status=Booking.Status.CONFIRMED, price_total=50, currency='EUR',
                               mode='RANGE', unit='day', msg='demo')

        # --- SLOTS: rehearsal room, per hour ---
        room = Item.objects.create(
            owner=owner, establishment=est, type=Item.ItemType.CREDIT,
            title='Rehearsal room «Som» — Hall A (demo)',
            description='Rehearsal room, rented per hour. Demonstration listing.',
            pricing_options=[{'type': 'rent', 'amount': 10, 'currency': 'EUR', 'unit': 'hour'}],
            attributes=dict(marker), spec_data=dict(marker),
        )
        rb = Bookable.objects.create(item=room, booking_mode=Bookable.Mode.SLOTS,
                                     confirmation=Bookable.Confirmation.AUTO)
        Availability.objects.create(bookable=rb, start='09:00', stop='18:00', slot_minutes=60)

        self.stdout.write(self.style.SUCCESS(
            f'Seeded demo rentals (owner={owner.local_name or owner.id}, '
            f'establishment={est.slug if est else "P2P"}):'))
        self.stdout.write(f'  RANGE /rental/{moto.id}')
        self.stdout.write(f'  SLOTS /rental/{room.id}')
