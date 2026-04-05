from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from geo.models import WorldObject, Establishment
from identity.models import Account, Profile
from taxonomy.models import Category


class Command(BaseCommand):
    help = 'Create 25+ demo establishments across European cities for Show HN readiness'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete demo establishments before recreating',
        )

    # Cities with buildings and establishments
    CITIES = [
        # Lisbon — primary community
        {
            'building': {
                'full_address': 'Rua do Carmo 45, 1200-093 Lisboa, Portugal',
                'location': Point(-9.14057, 38.71185, srid=4326),
                'country': 'PT', 'city': 'Lisboa',
                'street': 'Rua do Carmo', 'house_number': '45',
                'postal_code': '1200-093', 'building_type': 'commercial', 'levels': 5,
            },
            'establishments': [
                {
                    'name': 'TechHub Lisboa',
                    'description': 'Coworking space with high-speed internet, meeting rooms, and community events. Monthly and daily passes available.',
                    'category_slug': 'web-development',
                    'floor': '3', 'phone': '+351 21 340 5678',
                    'email': 'hello@techhub-lisboa.pt',
                    'website': 'https://techhub-lisboa.pt',
                    'opening_hours': {'mon-fri': '08:00-22:00', 'sat': '09:00-18:00', 'sun': 'closed'},
                    'attributes': {'wifi': True, 'meeting_rooms': 4, 'desks': 40, 'printer': True, 'coffee_machine': True},
                },
                {
                    'name': 'Padaria Artesanal',
                    'description': 'Artisan bakery with sourdough bread, pastéis de nata, and organic flour products baked fresh daily.',
                    'category_slug': 'bakery',
                    'floor': '0', 'phone': '+351 21 341 2233',
                    'email': 'encomendas@padaria-artesanal.pt',
                    'opening_hours': {'mon-sat': '06:30-19:00', 'sun': '07:00-14:00'},
                    'attributes': {'organic': True, 'gluten_free_options': True, 'takeaway': True},
                },
            ],
        },
        {
            'building': {
                'full_address': 'Av. da Liberdade 180, 1250-146 Lisboa, Portugal',
                'location': Point(-9.14497, 38.72098, srid=4326),
                'country': 'PT', 'city': 'Lisboa',
                'street': 'Av. da Liberdade', 'house_number': '180',
                'postal_code': '1250-146', 'building_type': 'commercial', 'levels': 8,
            },
            'establishments': [
                {
                    'name': 'Estúdio Foto Lisboa',
                    'description': 'Professional photography studio. Portraits, product photography, and event coverage. Equipment rental available.',
                    'category_slug': 'photography',
                    'floor': '2', 'phone': '+351 21 355 7890',
                    'email': 'studio@fotolisboa.pt',
                    'website': 'https://fotolisboa.pt',
                    'opening_hours': {'mon-fri': '09:00-19:00', 'sat': '10:00-16:00'},
                    'attributes': {'studio_size_m2': 120, 'equipment_rental': True, 'green_screen': True},
                },
                {
                    'name': 'Bike Repair Chiado',
                    'description': 'Bicycle repair shop and accessories. All brands serviced. Quick tune-ups and full overhauls.',
                    'category_slug': 'bicycles',
                    'floor': '0', 'phone': '+351 21 356 1234',
                    'email': 'info@bikechiado.pt',
                    'opening_hours': {'mon-fri': '09:00-18:30', 'sat': '10:00-15:00'},
                    'attributes': {'brands': 'all', 'ebike_service': True, 'parts_in_stock': True},
                },
                {
                    'name': 'Contabilidade Santos & Filhos',
                    'description': 'Accounting and tax consulting for individuals and businesses. English, Portuguese, and French spoken.',
                    'category_slug': 'accounting',
                    'floor': '5', 'phone': '+351 21 357 4567',
                    'email': 'info@santosfilhos.pt',
                    'website': 'https://santosfilhos.pt',
                    'opening_hours': {'mon-fri': '09:00-18:00'},
                    'attributes': {'languages': ['pt', 'en', 'fr'], 'online_consultations': True},
                },
            ],
        },
        # Porto
        {
            'building': {
                'full_address': 'Rua de Santa Catarina 312, 4000-442 Porto, Portugal',
                'location': Point(-8.60613, 41.14932, srid=4326),
                'country': 'PT', 'city': 'Porto',
                'street': 'Rua de Santa Catarina', 'house_number': '312',
                'postal_code': '4000-442', 'building_type': 'commercial', 'levels': 4,
            },
            'establishments': [
                {
                    'name': 'Porto Vintage Market',
                    'description': 'Vintage and second-hand electronics. Refurbished laptops, phones, and audio equipment with 6-month warranty.',
                    'category_slug': 'electronics',
                    'floor': '1', 'phone': '+351 22 200 3456',
                    'email': 'loja@portovintage.pt',
                    'opening_hours': {'mon-sat': '10:00-19:00', 'sun': '11:00-17:00'},
                    'attributes': {'warranty_months': 6, 'trade_in': True, 'repair_service': True},
                },
                {
                    'name': 'Café Majestic Copy',
                    'description': 'Traditional Porto café serving specialty coffee, francesinha, and Portuguese wines. Live fado on Fridays.',
                    'category_slug': 'cafe-restaurant',
                    'floor': '0', 'phone': '+351 22 201 5678',
                    'email': 'reservas@cafemajesticcopy.pt',
                    'opening_hours': {'mon-thu': '08:00-22:00', 'fri-sat': '08:00-00:00', 'sun': '09:00-20:00'},
                    'attributes': {'wifi': True, 'outdoor_seating': True, 'live_music': 'friday', 'wheelchair_accessible': True},
                },
                {
                    'name': 'Porto Print Lab',
                    'description': '3D printing and traditional printing services. Business cards, posters, prototypes, and custom designs.',
                    'category_slug': 'printing',
                    'floor': '2', 'phone': '+351 22 202 7890',
                    'email': 'print@portoprintlab.pt',
                    'website': 'https://portoprintlab.pt',
                    'opening_hours': {'mon-fri': '09:00-18:00'},
                    'attributes': {'3d_printing': True, 'large_format': True, 'same_day': True},
                },
            ],
        },
        # Berlin
        {
            'building': {
                'full_address': 'Oranienstraße 25, 10999 Berlin, Germany',
                'location': Point(13.42104, 52.50153, srid=4326),
                'country': 'DE', 'city': 'Berlin',
                'street': 'Oranienstraße', 'house_number': '25',
                'postal_code': '10999', 'building_type': 'mixed', 'levels': 6,
            },
            'establishments': [
                {
                    'name': 'Kreuzberg Fahrradwerkstatt',
                    'description': 'Community bicycle workshop. DIY repair stations, used bike sales, and weekly repair courses.',
                    'category_slug': 'bicycles',
                    'floor': '0', 'phone': '+49 30 612 3456',
                    'email': 'werkstatt@kreuzberg-rad.de',
                    'opening_hours': {'mon-fri': '10:00-19:00', 'sat': '10:00-16:00'},
                    'attributes': {'diy_stations': 6, 'used_bikes': True, 'courses': True, 'ebike': True},
                },
                {
                    'name': 'Café Neukölln',
                    'description': 'Third-wave coffee roasters with in-house bakery. Specialty beans from small farms. Vegan-friendly.',
                    'category_slug': 'cafe-restaurant',
                    'floor': '0', 'phone': '+49 30 613 7890',
                    'email': 'hallo@cafeneukoelln.de',
                    'opening_hours': {'mon-fri': '07:30-20:00', 'sat-sun': '09:00-19:00'},
                    'attributes': {'wifi': True, 'vegan_options': True, 'own_roastery': True, 'outdoor_seating': True},
                },
                {
                    'name': 'Berlin Design Studio',
                    'description': 'Graphic design and branding agency. Logo design, web design, print materials. Multilingual team.',
                    'category_slug': 'graphic-design',
                    'floor': '4', 'phone': '+49 30 614 2345',
                    'email': 'hello@berlindesign.studio',
                    'website': 'https://berlindesign.studio',
                    'opening_hours': {'mon-fri': '09:00-18:00'},
                    'attributes': {'languages': ['de', 'en', 'es'], 'remote_ok': True},
                },
                {
                    'name': 'Schlüsseldienst Mitte',
                    'description': 'Locksmith service covering all Berlin districts. Emergency 24h service. Lock replacement and key duplication.',
                    'category_slug': 'locksmith',
                    'floor': '0', 'phone': '+49 30 615 6789',
                    'email': 'info@schluessel-mitte.de',
                    'opening_hours': {'mon-sun': '00:00-24:00'},
                    'attributes': {'emergency_24h': True, 'all_districts': True, 'electronic_locks': True},
                },
            ],
        },
        # Paris
        {
            'building': {
                'full_address': '15 Rue Oberkampf, 75011 Paris, France',
                'location': Point(2.37012, 48.86541, srid=4326),
                'country': 'FR', 'city': 'Paris',
                'street': 'Rue Oberkampf', 'house_number': '15',
                'postal_code': '75011', 'building_type': 'commercial', 'levels': 5,
            },
            'establishments': [
                {
                    'name': 'Atelier de Couture Marie',
                    'description': 'Tailoring and alteration services. Custom-made clothing, wedding dresses, and vintage restoration.',
                    'category_slug': 'cleaning',  # closest available
                    'floor': '1', 'phone': '+33 1 43 55 12 34',
                    'email': 'marie@ateliermarie.fr',
                    'opening_hours': {'mon-fri': '10:00-19:00', 'sat': '10:00-17:00'},
                    'attributes': {'custom_made': True, 'alterations': True, 'wedding': True},
                },
                {
                    'name': 'Électricien Paris 11',
                    'description': 'Licensed electrician. Residential and commercial installations, smart home setup, EV charger installation.',
                    'category_slug': 'electrical',
                    'floor': '0', 'phone': '+33 1 43 56 78 90',
                    'email': 'devis@electricien-paris11.fr',
                    'opening_hours': {'mon-fri': '08:00-18:00', 'sat': '09:00-13:00'},
                    'attributes': {'ev_charger': True, 'smart_home': True, 'emergency': True, 'certified': True},
                },
                {
                    'name': 'Boulangerie du Marais',
                    'description': 'Traditional French bakery. Baguettes, croissants, pain au chocolat, and seasonal pastries since 1978.',
                    'category_slug': 'bakery',
                    'floor': '0', 'phone': '+33 1 43 57 11 22',
                    'opening_hours': {'tue-sat': '06:30-20:00', 'sun': '07:00-13:00', 'mon': 'closed'},
                    'attributes': {'organic_flour': True, 'gluten_free': False, 'catering': True},
                },
            ],
        },
        # London
        {
            'building': {
                'full_address': '42 Camden High Street, London NW1 0JH, UK',
                'location': Point(-0.14264, 51.53517, srid=4326),
                'country': 'GB', 'city': 'London',
                'street': 'Camden High Street', 'house_number': '42',
                'postal_code': 'NW1 0JH', 'building_type': 'commercial', 'levels': 3,
            },
            'establishments': [
                {
                    'name': 'Camden Fitness Hub',
                    'description': 'Community gym with personal training, group classes, and recovery zone. No contracts, pay-as-you-go available.',
                    'category_slug': 'fitness',
                    'floor': '0-1', 'phone': '+44 20 7485 1234',
                    'email': 'info@camdenfitness.co.uk',
                    'website': 'https://camdenfitness.co.uk',
                    'opening_hours': {'mon-fri': '06:00-22:00', 'sat-sun': '08:00-20:00'},
                    'attributes': {'classes': ['yoga', 'hiit', 'boxing', 'pilates'], 'personal_training': True, 'showers': True},
                },
                {
                    'name': 'The Moving Co.',
                    'description': 'Local and long-distance moving services. Packing, storage, and furniture assembly. Free estimates.',
                    'category_slug': 'moving',
                    'floor': '2', 'phone': '+44 20 7486 5678',
                    'email': 'book@themovingco.co.uk',
                    'website': 'https://themovingco.co.uk',
                    'opening_hours': {'mon-sat': '07:00-20:00', 'sun': '09:00-17:00'},
                    'attributes': {'storage': True, 'packing_service': True, 'insurance': True, 'free_estimate': True},
                },
                {
                    'name': 'Paws & Claws Veterinary',
                    'description': 'Full-service veterinary clinic. Vaccinations, surgery, dental care, and 24h emergency line.',
                    'category_slug': 'veterinary',
                    'floor': '0', 'phone': '+44 20 7487 9012',
                    'email': 'appointments@pawsclaws.vet',
                    'website': 'https://pawsclaws.vet',
                    'opening_hours': {'mon-fri': '08:00-20:00', 'sat': '09:00-17:00', 'sun': '10:00-14:00'},
                    'attributes': {'emergency_24h': True, 'surgery': True, 'dental': True, 'boarding': False},
                },
            ],
        },
        # Helsinki
        {
            'building': {
                'full_address': 'Fredrikinkatu 33, 00120 Helsinki, Finland',
                'location': Point(24.93753, 60.16496, srid=4326),
                'country': 'FI', 'city': 'Helsinki',
                'street': 'Fredrikinkatu', 'house_number': '33',
                'postal_code': '00120', 'building_type': 'commercial', 'levels': 5,
            },
            'establishments': [
                {
                    'name': 'Helsinki Sports Gear',
                    'description': 'New and used sports equipment. Skiing, cycling, hiking, and water sports. Trade-in program available.',
                    'category_slug': 'sports-equipment',
                    'floor': '0', 'phone': '+358 9 1234 567',
                    'email': 'myynti@helsinkisports.fi',
                    'opening_hours': {'mon-fri': '10:00-19:00', 'sat': '10:00-16:00'},
                    'attributes': {'trade_in': True, 'rental': True, 'used_gear': True, 'ski_tuning': True},
                },
                {
                    'name': 'Puhdistuspalvelu Clean & Fresh',
                    'description': 'Professional cleaning services. Offices, apartments, post-renovation, and window cleaning.',
                    'category_slug': 'cleaning',
                    'floor': '3', 'phone': '+358 9 2345 678',
                    'email': 'tilaus@cleanfresh.fi',
                    'opening_hours': {'mon-fri': '07:00-17:00'},
                    'attributes': {'eco_products': True, 'window_cleaning': True, 'post_renovation': True},
                },
            ],
        },
        # Madrid
        {
            'building': {
                'full_address': 'Calle de Fuencarral 72, 28004 Madrid, Spain',
                'location': Point(-3.70125, 40.42568, srid=4326),
                'country': 'ES', 'city': 'Madrid',
                'street': 'Calle de Fuencarral', 'house_number': '72',
                'postal_code': '28004', 'building_type': 'commercial', 'levels': 6,
            },
            'establishments': [
                {
                    'name': 'Fontanería Rápida Madrid',
                    'description': 'Emergency plumbing service. Leak repairs, pipe installations, boiler maintenance. All districts covered.',
                    'category_slug': 'plumbing',
                    'floor': '0', 'phone': '+34 91 234 5678',
                    'email': 'urgencias@fontaneria-rapida.es',
                    'opening_hours': {'mon-sun': '00:00-24:00'},
                    'attributes': {'emergency_24h': True, 'boiler_service': True, 'free_estimate': True},
                },
                {
                    'name': 'Estudio Interior Madrid',
                    'description': 'Interior design studio. Residential and commercial projects. 3D visualization, furniture sourcing, and project management.',
                    'category_slug': 'interior-design',
                    'floor': '4', 'phone': '+34 91 345 6789',
                    'email': 'proyectos@interioresmadrid.es',
                    'website': 'https://interioresmadrid.es',
                    'opening_hours': {'mon-fri': '09:30-19:00'},
                    'attributes': {'3d_visualization': True, 'commercial': True, 'residential': True},
                },
                {
                    'name': 'Taller de Coches Fuencarral',
                    'description': 'Full-service auto repair shop. MOT preparation, engine diagnostics, brake service, and bodywork.',
                    'category_slug': 'auto-services',
                    'floor': '0', 'phone': '+34 91 456 7890',
                    'email': 'cita@tallerfuencarral.es',
                    'opening_hours': {'mon-fri': '08:00-18:00', 'sat': '09:00-14:00'},
                    'attributes': {'diagnostics': True, 'mot_prep': True, 'electric_vehicles': True, 'courtesy_car': True},
                },
            ],
        },
        # New York (henry's location)
        {
            'building': {
                'full_address': '123 Smith Street, Brooklyn, NY 11201, USA',
                'location': Point(-73.98924, 40.68614, srid=4326),
                'country': 'US', 'city': 'Brooklyn',
                'street': 'Smith Street', 'house_number': '123',
                'postal_code': '11201', 'building_type': 'commercial', 'levels': 4,
            },
            'establishments': [
                {
                    'name': 'Brooklyn Express Delivery',
                    'description': 'Same-day local delivery service. Packages, documents, and food delivery by bike couriers.',
                    'category_slug': 'delivery',
                    'floor': '0', 'phone': '+1 718 555 0123',
                    'email': 'dispatch@bkexpress.nyc',
                    'website': 'https://bkexpress.nyc',
                    'opening_hours': {'mon-sun': '08:00-22:00'},
                    'attributes': {'same_day': True, 'bike_courier': True, 'tracking': True},
                },
                {
                    'name': 'Code & Coffee BK',
                    'description': 'Developer-friendly café with fast wifi, power outlets at every table, and quiet work zones. Monthly membership.',
                    'category_slug': 'cafe-restaurant',
                    'floor': '1', 'phone': '+1 718 555 0456',
                    'email': 'hi@codecoffeebk.com',
                    'opening_hours': {'mon-fri': '07:00-21:00', 'sat-sun': '08:00-20:00'},
                    'attributes': {'wifi_speed_mbps': 500, 'power_outlets': True, 'quiet_zone': True, 'meeting_room': True},
                },
            ],
        },
    ]

    # Marker to identify demo establishments (stored in attributes)
    DEMO_MARKER = '__demo_seed'

    def handle(self, *args, **options):
        reset = options['reset']

        # Get test user profiles for ownership
        test_profiles = list(
            Profile.objects.filter(account__groups__name='test_users')
            .order_by('account__username')
        )
        if not test_profiles:
            self.stdout.write(self.style.ERROR(
                'No test users found. Run: python3 manage.py seed_test_users --count 8'
            ))
            return

        if reset:
            # Delete establishments with demo marker
            deleted = Establishment.objects.filter(
                attributes__has_key=self.DEMO_MARKER
            ).delete()
            self.stdout.write(self.style.WARNING(f'Deleted {deleted[0]} demo establishments'))

        # Pre-fetch categories
        categories = {}
        for city_data in self.CITIES:
            for est in city_data['establishments']:
                slug = est['category_slug']
                if slug not in categories:
                    try:
                        categories[slug] = Category.objects.get(slug=slug)
                    except Category.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f'Category not found: {slug}, will skip'))
                        categories[slug] = None

        total_created = 0
        profile_idx = 0

        for city_data in self.CITIES:
            bld = city_data['building']

            # Get or create world object
            world_object, created = WorldObject.objects.get_or_create(
                xeno_source='seed',
                xeno_id=f"demo/{bld['full_address'][:80]}",
                defaults={
                    'location': bld['location'],
                    'country': bld['country'],
                    'city': bld['city'],
                    'street': bld['street'],
                    'house_number': bld['house_number'],
                    'postal_code': bld['postal_code'],
                    'full_address': bld['full_address'],
                    'building_type': bld.get('building_type', 'commercial'),
                    'levels': bld.get('levels', 4),
                }
            )
            if created:
                self.stdout.write(f'  WorldObject: {world_object.full_address}')

            for est_data in city_data['establishments']:
                category = categories.get(est_data['category_slug'])
                if not category:
                    continue

                # Distribute ownership across test profiles
                owner = test_profiles[profile_idx % len(test_profiles)]
                profile_idx += 1

                # Build attributes with demo marker
                attrs = est_data.get('attributes', {}).copy()
                attrs[self.DEMO_MARKER] = True

                est, created = Establishment.objects.get_or_create(
                    name=est_data['name'],
                    world_object=world_object,
                    defaults={
                        'owner': owner,
                        'description': est_data['description'],
                        'category': category,
                        'floor': est_data.get('floor', ''),
                        'phone': est_data.get('phone', ''),
                        'email': est_data.get('email', ''),
                        'website': est_data.get('website', ''),
                        'opening_hours': est_data.get('opening_hours', {}),
                        'attributes': attrs,
                        'is_verified': True,
                        'views_count': 0,
                    }
                )
                if created:
                    total_created += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'  + {est.name} ({world_object.city}) — owner: {owner.local_name}'
                    ))

            # Update world object counter
            world_object.establishments_count = world_object.establishments.filter(is_active=True).count()
            world_object.save(update_fields=['establishments_count'])

        self.stdout.write(self.style.SUCCESS(
            f'\nTotal: {total_created} demo establishments created across {len(self.CITIES)} world objects'
        ))
