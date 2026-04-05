from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from geo.models import WorldObject, Establishment
from identity.models import Profile
from taxonomy.models import Category


class Command(BaseCommand):
    help = 'Create test establishments in Lisbon and Krasnoyarsk for directory system demo'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing test establishments before creating new ones',
        )
        parser.add_argument(
            '--location',
            type=str,
            choices=['lisbon', 'krasnoyarsk', 'all'],
            default='all',
            help='Which location to seed (default: all)',
        )

    def handle(self, *args, **options):
        reset = options['reset']
        location = options['location']

        # Get norn profile for ownership (real user, not is_test — visible in public listings)
        try:
            owner = Profile.objects.get(local_name='norn', instance__domain='parahub.io')
        except Profile.DoesNotExist:
            self.stdout.write(self.style.ERROR('norn profile not found'))
            return

        # Get or create category
        category, _ = Category.objects.get_or_create(
            slug='cafe-restaurant',
            defaults={
                'name': 'Cafe & Restaurant',
                'description': 'Cafes, restaurants, and food services'
            }
        )

        if reset:
            lisbon_names = ['Café Central', 'Pizzeria Napoli', 'Sushi Garden']
            krsk_names = ['Кофейня "У дома"', 'Пекарня "Хлебный дом"', 'Суши-бар "Токио"']
            if location in ['lisbon', 'all']:
                count = Establishment.objects.filter(name__in=lisbon_names).delete()[0]
                self.stdout.write(self.style.WARNING(f'Deleted {count} Lisbon establishments'))

            if location in ['krasnoyarsk', 'all']:
                count = Establishment.objects.filter(name__in=krsk_names).delete()[0]
                self.stdout.write(self.style.WARNING(f'Deleted {count} Krasnoyarsk establishments'))

        # Seed Lisbon
        if location in ['lisbon', 'all']:
            lisbon_count = self._seed_lisbon(owner, category)
            self.stdout.write(self.style.SUCCESS(f'✅ Lisbon: {lisbon_count} establishments'))

        # Seed Krasnoyarsk
        if location in ['krasnoyarsk', 'all']:
            krsk_count = self._seed_krasnoyarsk(owner, category)
            self.stdout.write(self.style.SUCCESS(f'✅ Krasnoyarsk: {krsk_count} establishments'))

        self.stdout.write(self.style.SUCCESS('\n🎉 Done!'))

    def _seed_lisbon(self, owner, category):
        """Create test establishments in Lisbon"""
        world_object, created = WorldObject.objects.get_or_create(
            xeno_source='seed',
            xeno_id='test/rua-augusta-123-lisboa',
            defaults={
                'location': Point(-9.137060, 38.711470, srid=4326),
                'country': 'PT',
                'city': 'Lisboa',
                'street': 'Rua Augusta',
                'house_number': '123',
                'postal_code': '1100-053',
                'full_address': 'Rua Augusta 123, 1100-053 Lisboa, Portugal',
                'building_type': 'commercial',
                'levels': 4
            }
        )

        if created:
            self.stdout.write(f'  Created world object: {world_object.full_address}')

        establishments_data = [
            {
                'name': 'Café Central',
                'description': 'Traditional Portuguese café with excellent pastéis de nata and coffee. Open since 1952.',
                'floor': '1',
                'office_number': 'A',
                'phone': '+351 21 123 4567',
                'email': 'info@cafecentral.pt',
                'website': 'https://cafecentral.pt',
                'opening_hours': {
                    'mon-fri': '07:00-20:00',
                    'sat': '08:00-22:00',
                    'sun': '09:00-18:00'
                },
                'attributes': {
                    'wifi': True,
                    'outdoor_seating': True,
                    'wheelchair_accessible': True,
                    'payment_methods': ['cash', 'card', 'mbway']
                }
            },
            {
                'name': 'Pizzeria Napoli',
                'description': 'Authentic Italian pizza made with imported ingredients. Family-owned since 1985.',
                'floor': '2',
                'office_number': '',
                'phone': '+351 21 987 6543',
                'email': 'reservas@pizzerianapoli.pt',
                'website': 'https://pizzerianapoli.pt',
                'opening_hours': {
                    'mon-thu': '12:00-23:00',
                    'fri-sat': '12:00-01:00',
                    'sun': 'closed'
                },
                'attributes': {
                    'delivery': True,
                    'takeaway': True,
                    'reservation': True,
                    'payment_methods': ['cash', 'card']
                }
            },
            {
                'name': 'Sushi Garden',
                'description': 'Fresh sushi and Japanese cuisine. All-you-can-eat available.',
                'floor': '3',
                'office_number': 'B',
                'phone': '+351 21 555 1234',
                'email': 'contact@sushigarden.pt',
                'website': '',
                'opening_hours': {
                    'tue-sun': '12:00-22:00',
                    'mon': 'closed'
                },
                'attributes': {
                    'wifi': True,
                    'vegan_options': True,
                    'payment_methods': ['cash', 'card', 'crypto']
                }
            }
        ]

        count = 0
        for est_data in establishments_data:
            est, created = Establishment.objects.get_or_create(
                name=est_data['name'],
                world_object=world_object,
                defaults={
                    'owner': owner,
                    'description': est_data['description'],
                    'category': category,
                    'floor': est_data['floor'],
                    'office_number': est_data['office_number'],
                    'phone': est_data['phone'],
                    'email': est_data['email'],
                    'website': est_data['website'],
                    'opening_hours': est_data['opening_hours'],
                    'attributes': est_data['attributes'],
                    'is_verified': True,
                    'views_count': 0
                }
            )
            if created:
                self.stdout.write(f'  Created: {est.name}')
                count += 1

        # Update world object counter
        world_object.establishments_count = world_object.establishments.filter(is_active=True).count()
        world_object.save()

        return count

    def _seed_krasnoyarsk(self, owner, category):
        """Create test establishments in Krasnoyarsk"""
        world_object, created = WorldObject.objects.get_or_create(
            xeno_source='seed',
            xeno_id='test/vavilova-43-krasnoyarsk',
            defaults={
                'location': Point(92.941685, 56.000111, srid=4326),
                'country': 'RU',
                'city': 'Красноярск',
                'street': 'Академика Вавилова',
                'house_number': '43',
                'postal_code': '660025',
                'full_address': 'ул. Академика Вавилова, 43, Красноярск, Красноярский край, 660025, Россия',
                'building_type': 'residential',
                'levels': 9
            }
        )

        if created:
            self.stdout.write(f'  Created world object: {world_object.full_address}')

        establishments_data = [
            {
                'name': 'Кофейня "У дома"',
                'description': 'Уютная кофейня на первом этаже. Свежая выпечка, авторский кофе.',
                'floor': '1',
                'phone': '+7 (391) 123-45-67',
                'email': 'info@u-doma.ru',
                'opening_hours': {
                    'пн-пт': '08:00-20:00',
                    'сб-вс': '09:00-21:00'
                },
                'attributes': {
                    'wifi': True,
                    'терраса': False,
                    'способы_оплаты': ['наличные', 'карта', 'СБП']
                }
            },
            {
                'name': 'Пекарня "Хлебный дом"',
                'description': 'Свежий хлеб и выпечка каждый день. Работаем с 1995 года.',
                'floor': '1',
                'phone': '+7 (391) 234-56-78',
                'email': 'zakaz@hleb-dom.ru',
                'website': 'https://hleb-dom.ru',
                'opening_hours': {
                    'пн-вс': '07:00-22:00'
                },
                'attributes': {
                    'доставка': True,
                    'самовывоз': True,
                    'способы_оплаты': ['наличные', 'карта']
                }
            },
            {
                'name': 'Суши-бар "Токио"',
                'description': 'Японская кухня, доставка по городу. All you can eat.',
                'floor': '2',
                'phone': '+7 (391) 345-67-89',
                'email': 'order@tokyo-sushi.ru',
                'website': 'https://tokyo-sushi.ru',
                'opening_hours': {
                    'вт-вс': '12:00-23:00',
                    'пн': 'выходной'
                },
                'attributes': {
                    'доставка': True,
                    'веганские_опции': True,
                    'способы_оплаты': ['наличные', 'карта', 'криптовалюта']
                }
            }
        ]

        count = 0
        for est_data in establishments_data:
            est, created = Establishment.objects.get_or_create(
                name=est_data['name'],
                world_object=world_object,
                defaults={
                    'owner': owner,
                    'description': est_data['description'],
                    'category': category,
                    'floor': est_data['floor'],
                    'phone': est_data['phone'],
                    'email': est_data.get('email', ''),
                    'website': est_data.get('website', ''),
                    'opening_hours': est_data['opening_hours'],
                    'attributes': est_data['attributes'],
                    'is_verified': True,
                    'views_count': 0
                }
            )
            if created:
                self.stdout.write(f'  Created: {est.name}')
                count += 1

        # Update world object counter
        world_object.establishments_count = world_object.establishments.filter(is_active=True).count()
        world_object.save()

        return count
