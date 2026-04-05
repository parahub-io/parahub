"""
Seed demo items for barter matching (Show HN readiness).
Creates complementary CREDIT/DEBIT pairs across test users so barter chains exist.

Barter chain design:
  Alice offers electronics, wants photography → matches with Charlie
  Bob offers bicycles, wants electronics → matches with Alice
  Charlie offers photography, wants bicycles → matches with Bob
  → 3-way chain: Alice → Bob → Charlie → Alice

Plus direct 2-way pairs in other categories.
"""
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point

from identity.models import Profile
from market.models import Item
from taxonomy.models import Category

# Marker stored in spec_data for identification and cleanup
DEMO_MARKER = '__demo_seed'


class Command(BaseCommand):
    help = 'Create demo items with complementary barter pairs for Show HN readiness'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete demo items before recreating (only demo data)',
        )

    def _get_test_profiles(self):
        profiles = {}
        for name in ('alice', 'bob', 'charlie'):
            try:
                profiles[name] = Profile.objects.get(
                    local_name=name, instance__domain='parahub.io'
                )
            except Profile.DoesNotExist:
                pass
        return profiles

    # Item definitions: (owner_key, type, title, description, category_slug, pricing, location, language, country)
    ITEMS = [
        # === 3-way barter chain ===
        # Alice: offers electronics, wants photography
        ('alice', 'CREDIT', 'Raspberry Pi 4 Model B (4GB) with case and cables',
         'Barely used Raspberry Pi 4 with official case, power supply, and micro-HDMI cable. '
         'Perfect for home automation, media center, or learning to code.',
         'electronics',
         [{'type': 'sale', 'amount': 45, 'currency': 'EUR'}],
         Point(-9.1399, 38.7169, srid=4326), 'en', 'PT'),

        ('alice', 'DEBIT', 'Looking for portrait photography session',
         'Need professional headshots for my profile and CV. '
         'Studio or outdoor, 10-15 edited photos. Lisbon area preferred.',
         'photography',
         [{'type': 'sale', 'amount': 60, 'currency': 'EUR'}],
         Point(-9.1399, 38.7169, srid=4326), 'en', 'PT'),

        # Bob: offers bicycles, wants electronics
        ('bob', 'CREDIT', 'Vintage road bike — Peugeot PX-10, restored',
         'Classic 1980s Peugeot PX-10 road bike. Fully restored: new tires, cables, bar tape. '
         'Reynolds 531 frame, 56cm. Ready to ride.',
         'bicycles',
         [{'type': 'sale', 'amount': 280, 'currency': 'EUR'}],
         Point(-9.1427, 38.7223, srid=4326), 'en', 'PT'),

        ('bob', 'DEBIT', 'Want: Arduino or Raspberry Pi for home weather station',
         'Building a weather station for my balcony garden. '
         'Need a microcontroller board with temperature/humidity sensor capability.',
         'electronics',
         [{'type': 'sale', 'amount': 40, 'currency': 'EUR'}],
         Point(-9.1427, 38.7223, srid=4326), 'en', 'PT'),

        # Charlie: offers photography, wants bicycles
        ('charlie', 'CREDIT', 'Professional photography session — portraits and events',
         'I\'m a freelance photographer offering portrait sessions, small event coverage, '
         'and product photography. Portfolio available on request. '
         'Includes 15 edited high-res photos.',
         'photography',
         [{'type': 'sale', 'amount': 80, 'currency': 'EUR'}],
         Point(-9.1521, 38.7271, srid=4326), 'en', 'PT'),

        ('charlie', 'DEBIT', 'Looking for a commuter bicycle',
         'Need a reliable bicycle for daily commute in Lisbon. '
         'City bike or hybrid preferred. Gears and lights are a plus.',
         'bicycles',
         [{'type': 'sale', 'amount': 200, 'currency': 'EUR'}],
         Point(-9.1521, 38.7271, srid=4326), 'en', 'PT'),

        # === 2-way direct exchanges ===
        # Alice offers web dev, Bob wants web dev
        ('alice', 'CREDIT', 'Website setup — Nuxt 3 / Vue, responsive design',
         'I can build a simple business website or landing page using Nuxt 3. '
         'Includes responsive design, SEO basics, and deployment help. '
         '1-2 weeks turnaround.',
         'web-development',
         [{'type': 'sale', 'amount': 300, 'currency': 'EUR'}],
         None, 'en', ''),

        ('bob', 'DEBIT', 'Need a website for my bike repair workshop',
         'Looking for someone to create a simple website for my bicycle repair shop. '
         'Need: services page, contact form, opening hours, location map.',
         'web-development',
         [{'type': 'sale', 'amount': 250, 'currency': 'EUR'}],
         Point(-9.1427, 38.7223, srid=4326), 'en', 'PT'),

        # Bob offers tools, Charlie wants tools (direct exchange)
        ('bob', 'CREDIT', 'Complete bicycle repair toolkit — Park Tool',
         'Professional-grade Park Tool set: hex wrenches, chain breaker, spoke wrench, '
         'cable cutters, bottom bracket tool. Everything for home bike maintenance.',
         'tools',
         [{'type': 'rent', 'amount': 5, 'currency': 'EUR', 'unit': 'day'}],
         Point(-9.1427, 38.7223, srid=4326), 'en', 'PT'),

        ('charlie', 'DEBIT', 'Need bike tools for a weekend project',
         'Working on restoring a friend\'s old bicycle. Need a good set of bike-specific tools '
         'for a weekend. Especially need a chain breaker and spoke wrench.',
         'tools',
         [{'type': 'rent', 'amount': 5, 'currency': 'EUR', 'unit': 'day'}],
         Point(-9.1521, 38.7271, srid=4326), 'en', 'PT'),

        # Charlie offers design, Alice wants design
        ('charlie', 'CREDIT', 'Logo and brand identity design',
         'Graphic designer offering logo creation with full brand kit: '
         'logo variants, color palette, typography guide, and social media templates. '
         '2 revision rounds included.',
         'graphic-design',
         [{'type': 'sale', 'amount': 150, 'currency': 'EUR'}],
         None, 'en', ''),

        ('alice', 'DEBIT', 'Need a logo for my community project',
         'Starting a neighborhood composting initiative and need a simple, '
         'friendly logo. Should work in color and monochrome. '
         'Open to creative ideas!',
         'graphic-design',
         [{'type': 'sale', 'amount': 100, 'currency': 'EUR'}],
         Point(-9.1399, 38.7169, srid=4326), 'en', 'PT'),
    ]

    def handle(self, *args, **options):
        if options['reset']:
            deleted = Item.objects.filter(spec_data__has_key=DEMO_MARKER).delete()
            self.stdout.write(self.style.WARNING(f'Deleted {deleted[0]} demo items'))

        profiles = self._get_test_profiles()
        if len(profiles) < 3:
            self.stdout.write(self.style.ERROR(
                'Need alice, bob, charlie. Run: python3 manage.py seed_test_users --count 3'
            ))
            return

        # Pre-fetch categories
        cat_slugs = set(item[4] for item in self.ITEMS)
        categories = {}
        for slug in cat_slugs:
            try:
                categories[slug] = Category.objects.get(slug=slug)
            except Category.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'Category not found: {slug}'))

        created = 0
        for owner_key, item_type, title, desc, cat_slug, pricing, location, lang, country in self.ITEMS:
            category = categories.get(cat_slug)
            if not category:
                continue

            owner = profiles[owner_key]
            _, is_new = Item.objects.get_or_create(
                title=title,
                owner=owner,
                defaults={
                    'type': item_type,
                    'description': desc,
                    'category': category,
                    'pricing_options': pricing,
                    'location': location,
                    'language': lang,
                    'country_code': country,
                    'is_active': True,
                    'is_international': not country,
                    'spec_data': {DEMO_MARKER: True},
                }
            )
            if is_new:
                created += 1
                self.stdout.write(f'  + [{item_type}] {title} ({owner_key})')

        self.stdout.write(self.style.SUCCESS(f'\nTotal: {created} demo items created'))
        self.stdout.write(
            'Barter chains: Alice(electronics→photography) ↔ '
            'Bob(bicycles→electronics) ↔ Charlie(photography→bicycles)'
        )
        self.stdout.write('Run "python3 manage.py sync_to_neo4j" to update barter graph')
