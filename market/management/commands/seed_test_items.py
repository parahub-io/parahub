from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from django.core.files.base import ContentFile
from market.models import Item
from core.models import ObjectPhoto
from identity.models import Account, Profile
from taxonomy.models import Category
import random
import requests
from io import BytesIO


class Command(BaseCommand):
    help = 'Create test items for test users'

    # Sample images URLs (using Unsplash for quality photos)
    IMAGE_URLS = {
        'bicycles': [
            'https://images.unsplash.com/photo-1485965120184-e220f721d03e?w=800',
            'https://images.unsplash.com/photo-1571333250630-f0230c320b6d?w=800',
        ],
        'laptops': [
            'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=800',
            'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=800',
        ],
        'furniture': [
            'https://images.unsplash.com/photo-1615066390971-03e4e1c36ddf?w=800',
            'https://images.unsplash.com/photo-1606744824163-985d376605aa?w=800',
        ],
        'musical-instruments': [
            'https://images.unsplash.com/photo-1510915361894-db8b60106cb1?w=800',
            'https://images.unsplash.com/photo-1525201548942-d8732f6617a0?w=800',
        ],
        'photography': [
            'https://images.unsplash.com/photo-1502920917128-1aa500764cbd?w=800',
            'https://images.unsplash.com/photo-1606761568499-6d2451b23c66?w=800',
        ],
        'plumbing': [
            'https://images.unsplash.com/photo-1607472586893-edb57bdc0e39?w=800',
            'https://images.unsplash.com/photo-1581858726788-75bc0f6a952d?w=800',
        ],
        'power-tools': [
            'https://images.unsplash.com/photo-1572981779307-38b8cabb2407?w=800',
            'https://images.unsplash.com/photo-1504148455328-c376907d081c?w=800',
        ],
        'tents': [
            'https://images.unsplash.com/photo-1478131143081-80f7f84ca84d?w=800',
            'https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?w=800',
        ],
        'projectors': [
            'https://images.unsplash.com/photo-1560258018-c7db7645254e?w=800',
            'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800',
        ],
    }

    def download_image(self, url):
        """Download image from URL and return ContentFile"""
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                img_content = ContentFile(response.content)
                # Extract filename from URL or generate one
                filename = url.split('/')[-1].split('?')[0] + '.jpg'
                return img_content, filename
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Failed to download image: {e}'))
        return None, None

    def add_item_images(self, item, category_slug):
        """Add images to an item based on category slug"""
        if category_slug in self.IMAGE_URLS:
            image_urls = self.IMAGE_URLS[category_slug]
            # Add 1-2 random images from the category
            num_images = random.randint(1, min(2, len(image_urls)))
            selected_urls = random.sample(image_urls, num_images)

            for order, img_url in enumerate(selected_urls):
                img_content, filename = self.download_image(img_url)
                if img_content and filename:
                    item_image = ObjectPhoto(object_id=item.id, order=order, uploaded_by=item.owner)
                    item_image.image.save(filename, img_content, save=True)

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing test items before creating new ones',
        )

    def handle(self, *args, **options):
        reset = options['reset']

        # Get test users (from test_users group)
        test_accounts = Account.objects.filter(groups__name='test_users')
        if not test_accounts.exists():
            self.stdout.write(self.style.ERROR(
                'No test accounts found. Run: python3 manage.py seed_test_users'
            ))
            return

        # Get profiles for test accounts
        test_profiles = Profile.objects.filter(account__in=test_accounts)

        if reset:
            self.stdout.write('Deleting existing test items...')
            deleted = Item.objects.filter(owner__in=test_profiles).delete()
            self.stdout.write(self.style.WARNING(
                f'Deleted {deleted[0]} items'
            ))

        # Get categories for items
        try:
            cat_bicycles = Category.objects.get(slug='bicycles')
            cat_laptops = Category.objects.get(slug='laptops')
            cat_furniture = Category.objects.get(slug='furniture')
            cat_instruments = Category.objects.get(slug='musical-instruments')
            cat_photography = Category.objects.get(slug='photography')
            cat_plumbing = Category.objects.get(slug='plumbing')
            cat_power_tools = Category.objects.get(slug='power-tools')
            cat_tents = Category.objects.get(slug='tents')
            cat_projectors = Category.objects.get(slug='projectors')
        except Category.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(f'Required category not found: {e}'))
            return

        # Sample item templates
        credit_items = [
            # GOODS - Предлагаю товары
            {
                'title': 'Vintage Bicycle',
                'description': 'Classic steel frame bicycle in excellent condition. Perfect for city rides.',
                'category': cat_bicycles,
                'pricing_options': [{'type': 'sale', 'amount': 150, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'bicycles',
            },
            {
                'title': 'Laptop Dell XPS 13',
                'description': 'Used laptop, i5 processor, 8GB RAM, 256GB SSD. Works perfectly.',
                'category': cat_laptops,
                'pricing_options': [{'type': 'sale', 'amount': 450, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer', 'lightning'],
                'image_category': 'laptops',
            },
            {
                'title': 'Wooden Dining Table',
                'description': 'Handmade oak dining table, seats 6 people. Some wear marks.',
                'category': cat_furniture,
                'pricing_options': [{'type': 'sale', 'amount': 200, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash'],
                'image_category': 'furniture',
            },
            {
                'title': 'Guitar Acoustic Yamaha',
                'description': 'Acoustic guitar in good condition with soft case included.',
                'category': cat_instruments,
                'pricing_options': [{'type': 'sale', 'amount': 120, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'lightning'],
                'image_category': 'musical-instruments',
            },
            # SERVICES - Предлагаю услуги
            {
                'title': 'Photography Services',
                'description': 'Event photography, portraits, product photos. Professional equipment.',
                'category': cat_photography,
                'pricing_options': [{'type': 'sale', 'amount': 80, 'currency': 'EUR', 'unit': 'hour'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'photography',
            },
            {
                'title': 'Plumbing Services',
                'description': 'Professional plumbing services: repairs, installations, emergencies.',
                'category': cat_plumbing,
                'pricing_options': [{'type': 'sale', 'amount': 40, 'currency': 'EUR', 'unit': 'hour'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'plumbing',
            },
            # RENTAL pricing - Предлагаю товары в аренду
            {
                'title': 'Power Drill Set',
                'description': 'Professional power drill with various bits. Perfect for DIY projects. Available for rent.',
                'category': cat_power_tools,
                'pricing_options': [{'type': 'rent', 'amount': 10, 'currency': 'EUR', 'unit': 'day'}],
                'accepted_payment_methods': ['cash'],
                'image_category': 'power-tools',
            },
            {
                'title': 'Camping Tent 4-person',
                'description': 'Spacious camping tent with rainfly. Easy setup. Available for rent.',
                'category': cat_tents,
                'pricing_options': [{'type': 'rent', 'amount': 20, 'currency': 'EUR', 'unit': 'day'}],
                'accepted_payment_methods': ['cash', 'lightning'],
                'image_category': 'tents',
            },
            # Additional items for creating barter cycles
            # For 2-way cycle: bikes <-> laptops
            {
                'title': 'City Bike with Basket',
                'description': 'Comfortable city bike with front basket. Great for shopping and commuting.',
                'category': cat_bicycles,
                'pricing_options': [{'type': 'sale', 'amount': 180, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'bicycles',
            },
            {
                'title': 'MacBook Pro 2019',
                'description': 'MacBook Pro 13", i5, 16GB RAM, 512GB SSD. Excellent condition.',
                'category': cat_laptops,
                'pricing_options': [{'type': 'sale', 'amount': 800, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'laptops',
            },
            # For 2-way cycle: furniture <-> musical instruments
            {
                'title': 'Vintage Armchair',
                'description': 'Comfortable vintage armchair, recently reupholstered.',
                'category': cat_furniture,
                'pricing_options': [{'type': 'sale', 'amount': 120, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash'],
                'image_category': 'furniture',
            },
            {
                'title': 'Electric Keyboard',
                'description': 'Yamaha electric keyboard, 61 keys, with stand and pedal.',
                'category': cat_instruments,
                'pricing_options': [{'type': 'sale', 'amount': 150, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'musical-instruments',
            },
            # For 3-way cycle: photography services -> plumbing services -> power tools rental
            {
                'title': 'Photography & Video',
                'description': 'Professional photography and video services for any event.',
                'category': cat_photography,
                'pricing_options': [{'type': 'sale', 'amount': 100, 'currency': 'EUR', 'unit': 'hour'}],
                'accepted_payment_methods': ['cash', 'bank_transfer', 'lightning'],
                'image_category': 'photography',
            },
            {
                'title': 'Plumbing & Heating',
                'description': 'Expert plumbing and heating services. Fast response.',
                'category': cat_plumbing,
                'pricing_options': [{'type': 'sale', 'amount': 50, 'currency': 'EUR', 'unit': 'hour'}],
                'accepted_payment_methods': ['cash'],
                'image_category': 'plumbing',
            },
            {
                'title': 'Professional Tool Set',
                'description': 'Complete professional tool set available for rent. Includes drills, saws, sanders.',
                'category': cat_power_tools,
                'pricing_options': [{'type': 'rent', 'amount': 25, 'currency': 'EUR', 'unit': 'day'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'power-tools',
            },
            # For 3-way cycle: tents rental -> projector rental -> bicycles
            {
                'title': 'Large Family Tent',
                'description': '6-person tent with separate rooms. Perfect for family camping.',
                'category': cat_tents,
                'pricing_options': [{'type': 'rent', 'amount': 30, 'currency': 'EUR', 'unit': 'day'}],
                'accepted_payment_methods': ['cash'],
                'image_category': 'tents',
            },
            {
                'title': 'HD Projector',
                'description': 'Full HD projector, 3000 lumens. Great for presentations and movies.',
                'category': cat_projectors,
                'pricing_options': [{'type': 'rent', 'amount': 25, 'currency': 'EUR', 'unit': 'day'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'projectors',
            },
            {
                'title': 'Racing Bike',
                'description': 'Lightweight racing bike, carbon frame. Perfect for long rides.',
                'category': cat_bicycles,
                'pricing_options': [{'type': 'sale', 'amount': 600, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer', 'lightning'],
                'image_category': 'bicycles',
            },
        ]

        debit_items = [
            # GOODS - Хочу купить товары
            {
                'title': 'Mountain Bike',
                'description': 'Looking for mountain bike in good condition, 26-29 inch wheels.',
                'category': cat_bicycles,
                'pricing_options': [{'type': 'sale', 'amount': 300, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'bicycles',
            },
            {
                'title': 'Used Laptop',
                'description': 'Looking for used laptop for programming, min 8GB RAM.',
                'category': cat_laptops,
                'pricing_options': [{'type': 'sale', 'amount': 400, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash'],
                'image_category': 'laptops',
            },
            {
                'title': 'Bookshelf',
                'description': 'Looking for wooden bookshelf, at least 5 shelves.',
                'category': cat_furniture,
                'pricing_options': [{'type': 'sale', 'amount': 50, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'furniture',
            },
            {
                'title': 'Guitar for Beginner',
                'description': 'Looking for affordable acoustic guitar for beginner.',
                'category': cat_instruments,
                'pricing_options': [{'type': 'sale', 'amount': 80, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash'],
                'image_category': 'musical-instruments',
            },
            # SERVICES - Хочу услуги
            {
                'title': 'Photographer for Event',
                'description': 'Looking for photographer for birthday party, 3-4 hours.',
                'category': cat_photography,
                'pricing_options': [{'type': 'sale', 'amount': 200, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'photography',
            },
            {
                'title': 'Plumber Needed',
                'description': 'Looking for experienced plumber to fix bathroom sink.',
                'category': cat_plumbing,
                'pricing_options': [{'type': 'sale', 'amount': 40, 'currency': 'EUR', 'unit': 'hour'}],
                'accepted_payment_methods': ['cash', 'lightning'],
                'image_category': 'plumbing',
            },
            # GOODS with RENTAL pricing - Хочу арендовать товары
            {
                'title': 'Need Power Tools',
                'description': 'Looking to rent power drill and saw for weekend DIY project.',
                'category': cat_power_tools,
                'pricing_options': [{'type': 'rent', 'amount': 15, 'currency': 'EUR', 'unit': 'day'}],
                'accepted_payment_methods': ['cash'],
                'image_category': 'power-tools',
            },
            {
                'title': 'Projector for Presentation',
                'description': 'Need projector for business presentation, just for one evening.',
                'category': cat_projectors,
                'pricing_options': [{'type': 'rent', 'amount': 30, 'currency': 'EUR', 'unit': 'day'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'projectors',
            },
            # Additional items for creating barter cycles - matching CREDIT items above
            # For 2-way cycle: bikes <-> laptops
            {
                'title': 'Looking for Laptop',
                'description': 'Need a good laptop for work, preferably MacBook or similar. Willing to pay well.',
                'category': cat_laptops,
                'pricing_options': [{'type': 'sale', 'amount': 750, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'laptops',
            },
            {
                'title': 'Need City Bike',
                'description': 'Looking for comfortable city bike for daily commute.',
                'category': cat_bicycles,
                'pricing_options': [{'type': 'sale', 'amount': 200, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'bicycles',
            },
            # For 2-way cycle: furniture <-> musical instruments
            {
                'title': 'Want Musical Keyboard',
                'description': 'Looking for electric keyboard for learning to play.',
                'category': cat_instruments,
                'pricing_options': [{'type': 'sale', 'amount': 140, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'musical-instruments',
            },
            {
                'title': 'Need Armchair',
                'description': 'Looking for comfortable armchair for reading corner.',
                'category': cat_furniture,
                'pricing_options': [{'type': 'sale', 'amount': 100, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash'],
                'image_category': 'furniture',
            },
            # For 3-way cycle: A offers photography → wants power tools, B offers plumbing → wants photography, C offers power tools → wants plumbing
            {
                'title': 'Need Professional Tools',
                'description': 'Looking to rent professional tool set for home renovation project.',
                'category': cat_power_tools,
                'pricing_options': [{'type': 'rent', 'amount': 20, 'currency': 'EUR', 'unit': 'day'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'power-tools',
            },
            {
                'title': 'Need Photographer',
                'description': 'Looking for professional photographer for wedding event.',
                'category': cat_photography,
                'pricing_options': [{'type': 'sale', 'amount': 400, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer', 'lightning'],
                'image_category': 'photography',
            },
            {
                'title': 'Plumber Needed for Renovation',
                'description': 'Looking for experienced plumber for bathroom renovation project.',
                'category': cat_plumbing,
                'pricing_options': [{'type': 'sale', 'amount': 50, 'currency': 'EUR', 'unit': 'hour'}],
                'accepted_payment_methods': ['cash'],
                'image_category': 'plumbing',
            },
            # For 3-way cycle: A offers tent → wants projector, B offers projector → wants bike, C offers bike → wants tent
            {
                'title': 'Need Projector for Event',
                'description': 'Looking to rent HD projector for outdoor movie night.',
                'category': cat_projectors,
                'pricing_options': [{'type': 'rent', 'amount': 20, 'currency': 'EUR', 'unit': 'day'}],
                'accepted_payment_methods': ['cash', 'bank_transfer'],
                'image_category': 'projectors',
            },
            {
                'title': 'Want Racing Bike',
                'description': 'Looking for high-quality racing bike for training.',
                'category': cat_bicycles,
                'pricing_options': [{'type': 'sale', 'amount': 550, 'currency': 'EUR'}],
                'accepted_payment_methods': ['cash', 'bank_transfer', 'lightning'],
                'image_category': 'bicycles',
            },
            {
                'title': 'Need Camping Tent',
                'description': 'Looking to rent large tent for family camping trip.',
                'category': cat_tents,
                'pricing_options': [{'type': 'rent', 'amount': 25, 'currency': 'EUR', 'unit': 'day'}],
                'accepted_payment_methods': ['cash'],
                'image_category': 'tents',
            },
        ]

        created_count = 0

        # Shuffle lists to get unique items for each user
        random.shuffle(credit_items)
        random.shuffle(debit_items)

        for idx, profile in enumerate(test_profiles):
            # Get unique items for this user (2 credits + 2 debits)
            user_credit_items = credit_items[idx*2:(idx+1)*2]
            user_debit_items = debit_items[idx*2:(idx+1)*2]

            # Create CREDIT items (offers)
            for item_data in user_credit_items:
                # Add small location offset from profile location
                location = None
                if profile.location:
                    lat = profile.location.y + random.uniform(-0.01, 0.01)
                    lon = profile.location.x + random.uniform(-0.01, 0.01)
                    location = Point(lon, lat, srid=4326)

                category = item_data['category']

                item = Item.objects.create(
                    owner=profile,
                    title=item_data['title'],
                    description=item_data['description'],
                    type='CREDIT',
                    category=category,
                    pricing_options=item_data['pricing_options'],
                    accepted_payment_methods=item_data['accepted_payment_methods'],
                    location=location,
                )
                created_count += 1

                # Add images for this item
                image_cat = item_data.get('image_category')
                if image_cat and image_cat in self.IMAGE_URLS:
                    image_urls = self.IMAGE_URLS[image_cat]
                    # Add 1-2 random images from the category
                    num_images = random.randint(1, min(2, len(image_urls)))
                    selected_urls = random.sample(image_urls, num_images)

                    for order, img_url in enumerate(selected_urls):
                        img_content, filename = self.download_image(img_url)
                        if img_content and filename:
                            item_image = ObjectPhoto(object_id=item.id, order=order, uploaded_by=item.owner)
                            item_image.image.save(filename, img_content, save=True)

            # Create DEBIT items (requests)
            for item_data in user_debit_items:
                # Add small location offset from profile location
                location = None
                if profile.location:
                    lat = profile.location.y + random.uniform(-0.01, 0.01)
                    lon = profile.location.x + random.uniform(-0.01, 0.01)
                    location = Point(lon, lat, srid=4326)

                category = item_data['category']

                item = Item.objects.create(
                    owner=profile,
                    title=item_data['title'],
                    description=item_data['description'],
                    type='DEBIT',
                    category=category,
                    pricing_options=item_data['pricing_options'],
                    accepted_payment_methods=item_data['accepted_payment_methods'],
                    location=location,
                )
                created_count += 1

                # Add images for this item
                image_cat = item_data.get('image_category')
                if image_cat and image_cat in self.IMAGE_URLS:
                    image_urls = self.IMAGE_URLS[image_cat]
                    # Add 1-2 random images from the category
                    num_images = random.randint(1, min(2, len(image_urls)))
                    selected_urls = random.sample(image_urls, num_images)

                    for order, img_url in enumerate(selected_urls):
                        img_content, filename = self.download_image(img_url)
                        if img_content and filename:
                            item_image = ObjectPhoto(object_id=item.id, order=order, uploaded_by=item.owner)
                            item_image.image.save(filename, img_content, save=True)

            self.stdout.write(self.style.SUCCESS(
                f'Created 4 unique items for {profile.hna}'
            ))

        # Create GUARANTEED BARTER CYCLES for testing
        # Get specific users (alice, bob, charlie)
        self.stdout.write(self.style.SUCCESS('\nCreating guaranteed barter cycles...'))

        try:
            alice = Profile.objects.get(account__username='alice', account__groups__name='test_users')
            bob = Profile.objects.get(account__username='bob', account__groups__name='test_users')
            charlie = Profile.objects.get(account__username='charlie', account__groups__name='test_users')

            #  2-WAY CYCLE 1: alice (City Bike) <-> bob (Laptop)
            # Alice offers City Bike
            item = Item.objects.create(
                owner=alice, type='CREDIT', category=cat_bicycles,
                title='City Bike', description='Comfortable city bike with front basket. Great for shopping.',
                pricing_options=[{'type': 'sale', 'amount': 180, 'currency': 'EUR'}],
                accepted_payment_methods=['cash'],
                location=alice.location
            )
            self.add_item_images(item, 'bicycles')

            # Bob wants City Bike
            item = Item.objects.create(
                owner=bob, type='DEBIT', category=cat_bicycles,
                title='Looking for City Bike', description='Need comfortable city bike for daily commuting.',
                pricing_options=[{'type': 'sale', 'amount': 180, 'currency': 'EUR'}],
                accepted_payment_methods=['cash'],
                location=bob.location
            )
            self.add_item_images(item, 'bicycles')

            # Bob offers Laptop
            item = Item.objects.create(
                owner=bob, type='CREDIT', category=cat_laptops,
                title='Dell Laptop i5', description='Dell laptop with i5 processor, 8GB RAM. Perfect for work.',
                pricing_options=[{'type': 'sale', 'amount': 500, 'currency': 'EUR'}],
                accepted_payment_methods=['cash'],
                location=bob.location
            )
            self.add_item_images(item, 'laptops')

            # Alice wants Laptop
            item = Item.objects.create(
                owner=alice, type='DEBIT', category=cat_laptops,
                title='Need Work Laptop', description='Looking for reliable laptop for programming and office work.',
                pricing_options=[{'type': 'sale', 'amount': 500, 'currency': 'EUR'}],
                accepted_payment_methods=['cash'],
                location=alice.location
            )
            self.add_item_images(item, 'laptops')

            created_count += 4
            self.stdout.write(self.style.SUCCESS('  ✓ 2-way cycle 1: alice (bikes) <-> bob (laptops)'))

            # 2-WAY CYCLE 2: alice (Armchair) <-> charlie (Keyboard)
            # Alice offers Armchair
            item = Item.objects.create(
                owner=alice, type='CREDIT', category=cat_furniture,
                title='Vintage Reading Armchair', description='Comfortable vintage armchair, perfect for reading corner',
                pricing_options=[{'type': 'sale', 'amount': 120, 'currency': 'EUR'}],
                accepted_payment_methods=['cash'],
                location=alice.location
            )
            self.add_item_images(item, 'furniture')
            # Charlie wants Armchair
            item = Item.objects.create(
                owner=charlie, type='DEBIT', category=cat_furniture,
                title='Looking for Comfortable Armchair', description='Need comfortable armchair for home office',
                pricing_options=[{'type': 'sale', 'amount': 120, 'currency': 'EUR'}],
                accepted_payment_methods=['cash'],
                location=charlie.location
            )
            self.add_item_images(item, 'furniture')
            # Charlie offers Keyboard
            item = Item.objects.create(
                owner=charlie, type='CREDIT', category=cat_instruments,
                title='Yamaha PSR Electric Keyboard', description='61-key electric keyboard with built-in speakers and stand',
                pricing_options=[{'type': 'sale', 'amount': 150, 'currency': 'EUR'}],
                accepted_payment_methods=['cash'],
                location=charlie.location
            )
            self.add_item_images(item, 'musical-instruments')
            # Alice wants Keyboard
            item = Item.objects.create(
                owner=alice, type='DEBIT', category=cat_instruments,
                title='Need Electric Keyboard for Learning', description='Looking for electric keyboard to learn piano',
                pricing_options=[{'type': 'sale', 'amount': 150, 'currency': 'EUR'}],
                accepted_payment_methods=['cash'],
                location=alice.location
            )
            self.add_item_images(item, 'musical-instruments')
            created_count += 4
            self.stdout.write(self.style.SUCCESS('  ✓ 2-way cycle 2: alice (furniture) <-> charlie (instruments)'))

            # 3-WAY CYCLE 1: alice (Photography) → bob (Plumbing) → charlie (Tools) → alice
            # Alice offers Photography, wants Tools
            item = Item.objects.create(
                owner=alice, type='CREDIT', category=cat_photography,
                title='Professional Event Photography', description='Wedding and corporate event photography with professional equipment',
                pricing_options=[{'type': 'sale', 'amount': 80, 'currency': 'EUR', 'unit': 'hour'}],
                accepted_payment_methods=['cash'],
                location=alice.location
            )
            self.add_item_images(item, 'photography')
            item = Item.objects.create(
                owner=alice, type='DEBIT', category=cat_power_tools,
                title='Need Professional Tool Set Rental', description='Looking for complete tool set for weekend renovation',
                pricing_options=[{'type': 'rent', 'amount': 20, 'currency': 'EUR', 'unit': 'day'}],
                accepted_payment_methods=['cash'],
                location=alice.location
            )
            self.add_item_images(item, 'power-tools')
            # Bob offers Plumbing, wants Photography
            item = Item.objects.create(
                owner=bob, type='CREDIT', category=cat_plumbing,
                title='Emergency Plumbing Service', description='Fast plumbing repairs and installations, 24/7 available',
                pricing_options=[{'type': 'sale', 'amount': 50, 'currency': 'EUR', 'unit': 'hour'}],
                accepted_payment_methods=['cash'],
                location=bob.location
            )
            self.add_item_images(item, 'plumbing')
            item = Item.objects.create(
                owner=bob, type='DEBIT', category=cat_photography,
                title='Photographer Needed for Family Event', description='Looking for professional photographer for anniversary party',
                pricing_options=[{'type': 'sale', 'amount': 80, 'currency': 'EUR', 'unit': 'hour'}],
                accepted_payment_methods=['cash'],
                location=bob.location
            )
            self.add_item_images(item, 'photography')
            # Charlie offers Tools, wants Plumbing
            item = Item.objects.create(
                owner=charlie, type='CREDIT', category=cat_power_tools,
                title='Complete Workshop Tool Collection', description='Professional grade tools: drills, saws, sanders, and more',
                pricing_options=[{'type': 'rent', 'amount': 20, 'currency': 'EUR', 'unit': 'day'}],
                accepted_payment_methods=['cash'],
                location=charlie.location
            )
            self.add_item_images(item, 'power-tools')
            item = Item.objects.create(
                owner=charlie, type='DEBIT', category=cat_plumbing,
                title='Plumber Needed for Kitchen Renovation', description='Looking for experienced plumber for kitchen sink installation',
                pricing_options=[{'type': 'sale', 'amount': 50, 'currency': 'EUR', 'unit': 'hour'}],
                accepted_payment_methods=['cash'],
                location=charlie.location
            )
            self.add_item_images(item, 'plumbing')
            created_count += 6
            self.stdout.write(self.style.SUCCESS('  ✓ 3-way cycle 1: alice (photo) → bob (plumb) → charlie (tools) → alice'))

            # 3-WAY CYCLE 2: alice (Tent) → bob (Projector) → charlie (Bike) → alice
            # Alice offers Tent, wants Bike
            item = Item.objects.create(
                owner=alice, type='CREDIT', category=cat_tents,
                title='Spacious 6-Person Family Tent', description='Waterproof camping tent with separate bedrooms, perfect for family trips',
                pricing_options=[{'type': 'rent', 'amount': 25, 'currency': 'EUR', 'unit': 'day'}],
                accepted_payment_methods=['cash'],
                location=alice.location
            )
            self.add_item_images(item, 'tents')
            item = Item.objects.create(
                owner=alice, type='DEBIT', category=cat_bicycles,
                title='Looking for Carbon Frame Racing Bike', description='Need lightweight racing bike for marathon training',
                pricing_options=[{'type': 'sale', 'amount': 600, 'currency': 'EUR'}],
                accepted_payment_methods=['cash'],
                location=alice.location
            )
            self.add_item_images(item, 'bicycles')
            # Bob offers Projector, wants Tent
            item = Item.objects.create(
                owner=bob, type='CREDIT', category=cat_projectors,
                title='4K Business Projector', description='High-quality 4K projector with 3500 lumens, perfect for presentations',
                pricing_options=[{'type': 'rent', 'amount': 25, 'currency': 'EUR', 'unit': 'day'}],
                accepted_payment_methods=['cash'],
                location=bob.location
            )
            self.add_item_images(item, 'projectors')
            item = Item.objects.create(
                owner=bob, type='DEBIT', category=cat_tents,
                title='Need Large Tent for Camping Weekend', description='Looking for family tent rental for mountain camping trip',
                pricing_options=[{'type': 'rent', 'amount': 25, 'currency': 'EUR', 'unit': 'day'}],
                accepted_payment_methods=['cash'],
                location=bob.location
            )
            self.add_item_images(item, 'tents')
            # Charlie offers Racing Bike, wants Projector
            item = Item.objects.create(
                owner=charlie, type='CREDIT', category=cat_bicycles,
                title='Professional Carbon Road Bike', description='Shimano Ultegra groupset, lightweight carbon frame, excellent condition',
                pricing_options=[{'type': 'sale', 'amount': 600, 'currency': 'EUR'}],
                accepted_payment_methods=['cash'],
                location=charlie.location
            )
            self.add_item_images(item, 'bicycles')
            item = Item.objects.create(
                owner=charlie, type='DEBIT', category=cat_projectors,
                title='Need Projector for Home Theater', description='Looking for HD or 4K projector rental for weekend movie night',
                pricing_options=[{'type': 'rent', 'amount': 25, 'currency': 'EUR', 'unit': 'day'}],
                accepted_payment_methods=['cash'],
                location=charlie.location
            )
            self.add_item_images(item, 'projectors')
            created_count += 6
            self.stdout.write(self.style.SUCCESS('  ✓ 3-way cycle 2: alice (tent) → bob (proj) → charlie (bike) → alice'))

        except Profile.DoesNotExist:
            self.stdout.write(self.style.WARNING(
                'Could not find alice/bob/charlie profiles - skipping guaranteed cycles'
            ))

        self.stdout.write(self.style.SUCCESS(
            f'\nTotal: {created_count} items created for {test_profiles.count()} users'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'Random items + Guaranteed barter cycles'
        ))
