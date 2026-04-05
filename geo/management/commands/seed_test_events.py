from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from django.utils import timezone
from datetime import timedelta
from geo.models import Event, EventParticipant, WorldObject
from identity.models import Profile
from taxonomy.models import Category


class Command(BaseCommand):
    help = 'Create test events for events system demo'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing test events before creating new ones',
        )

    def handle(self, *args, **options):
        reset = options['reset']

        # Get test profiles
        try:
            alice = Profile.objects.get(local_name='alice', instance__domain='parahub.io')
        except Profile.DoesNotExist:
            self.stdout.write(self.style.ERROR('Alice profile not found. Run: python3 manage.py seed_test_users'))
            return

        try:
            bob = Profile.objects.get(local_name='bob', instance__domain='parahub.io')
        except Profile.DoesNotExist:
            bob = None

        try:
            charlie = Profile.objects.get(local_name='charlie', instance__domain='parahub.io')
        except Profile.DoesNotExist:
            charlie = None

        if reset:
            count = Event.objects.all().delete()[0]
            self.stdout.write(self.style.WARNING(f'Deleted {count} events'))

        # Get or create categories for events
        cat_defs = [
            ('sports-fitness', 'Sports & Fitness', '🏃'),
            ('education-workshop', 'Education & Workshop', '📚'),
            ('social-meetup', 'Social & Meetup', '🤝'),
            ('tech-it', 'Tech & IT', '💻'),
            ('music-culture', 'Music & Culture', '🎵'),
            ('food-dining', 'Food & Dining', '🍽️'),
            ('art-creative', 'Art & Creative', '🎨'),
            ('health-wellness', 'Health & Wellness', '💆'),
            ('nature-outdoors', 'Nature & Outdoors', '🌿'),
            ('gaming', 'Gaming', '🎮'),
            ('volunteering', 'Volunteering', '🤲'),
        ]
        cats = {}
        for slug, name, icon in cat_defs:
            cat, _ = Category.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'icon': icon, 'applicable_to': ['events']}
            )
            # Ensure applicable_to includes events
            if 'events' not in (cat.applicable_to or []):
                cat.applicable_to = list(set((cat.applicable_to or []) + ['events']))
                cat.save(update_fields=['applicable_to'])
            cats[slug] = cat

        sports_cat = cats['sports-fitness']
        education_cat = cats['education-workshop']
        social_cat = cats['social-meetup']
        tech_cat = cats['tech-it']

        now = timezone.now()

        # Create events
        events_data = [
            {
                'organizer': alice,
                'title': 'Morning Run in the Park',
                'description': 'Join us for a refreshing morning run! All fitness levels welcome.\n\nWe will meet at the main entrance and do a 5km loop. Bring water and comfortable running shoes.\n\nWeather permitting, we run every Saturday morning.',
                'category': sports_cat,
                'event_type': 'OFFLINE',
                'starts_at': now + timedelta(days=3, hours=8),
                'ends_at': now + timedelta(days=3, hours=10),
                'timezone': 'Europe/Lisbon',
                'location_name': 'Parque das Nacoes, main entrance',
                'location': Point(-9.0939, 38.7631, srid=4326),
                'max_participants': 20,
                'status': 'PUBLISHED',
            },
            {
                'organizer': alice,
                'title': 'Python Programming Workshop',
                'description': 'Learn Python basics in this hands-on workshop. Perfect for beginners!\n\nTopics covered:\n- Variables and data types\n- Control flow\n- Functions\n- Working with files\n\nBring your laptop with Python installed.',
                'category': tech_cat,
                'event_type': 'HYBRID',
                'starts_at': now + timedelta(days=7, hours=14),
                'ends_at': now + timedelta(days=7, hours=17),
                'timezone': 'Europe/Moscow',
                'location_name': 'TechHub Coworking, Meeting Room A',
                'location': Point(92.8932, 56.0097, srid=4326),
                'online_url': 'https://meet.jit.si/parahub-python-workshop',
                'max_participants': 30,
                'status': 'PUBLISHED',
            },
            {
                'organizer': alice,
                'title': 'Book Club: "The Master and Margarita"',
                'description': 'Monthly book club meeting to discuss Bulgakov\'s masterpiece.\n\nThis month we discuss chapters 15-25. New members welcome - just read the chapters beforehand!\n\nLight refreshments will be provided.',
                'category': education_cat,
                'event_type': 'OFFLINE',
                'starts_at': now + timedelta(days=14, hours=18),
                'ends_at': now + timedelta(days=14, hours=20),
                'timezone': 'Europe/Moscow',
                'location_name': 'Cafe "Margarita", 2nd floor',
                'location': Point(92.8521, 56.0153, srid=4326),
                'max_participants': 15,
                'status': 'PUBLISHED',
            },
            {
                'organizer': alice,
                'title': 'Online Yoga Session',
                'description': 'Relax and rejuvenate with a gentle yoga flow.\n\nSuitable for all levels. You will need:\n- Yoga mat or soft surface\n- Comfortable clothing\n- Water\n\nCamera on is encouraged but not required.',
                'category': sports_cat,
                'event_type': 'ONLINE',
                'starts_at': now + timedelta(days=2, hours=7),
                'ends_at': now + timedelta(days=2, hours=8),
                'timezone': 'UTC',
                'online_url': 'https://meet.jit.si/parahub-yoga-morning',
                'status': 'PUBLISHED',
            },
            {
                'organizer': alice,
                'title': 'Community Barbecue',
                'description': 'Summer community gathering with food, games, and great company!\n\nBring your own drinks. Vegetarian options available.\n\nKids and dogs welcome!',
                'category': social_cat,
                'event_type': 'OFFLINE',
                'starts_at': now + timedelta(days=21, hours=12),
                'ends_at': now + timedelta(days=21, hours=18),
                'timezone': 'Europe/Lisbon',
                'location_name': 'Community Garden, central area',
                'location': Point(-9.1427, 38.7169, srid=4326),
                'max_participants': 50,
                'status': 'PUBLISHED',
            },
            {
                'organizer': alice,
                'title': 'Cryptocurrency & Web3 Discussion',
                'description': 'Open discussion about current trends in crypto and web3.\n\nTopics:\n- DeFi updates\n- NFT market analysis\n- Regulatory landscape\n- Building on blockchain\n\nBring your questions!',
                'category': tech_cat,
                'event_type': 'ONLINE',
                'starts_at': now + timedelta(days=5, hours=19),
                'ends_at': now + timedelta(days=5, hours=21),
                'timezone': 'Europe/Moscow',
                'online_url': 'https://meet.jit.si/parahub-crypto-talk',
                'max_participants': 100,
                'status': 'PUBLISHED',
            },
            {
                'organizer': alice,
                'title': 'Cancelled Event Example',
                'description': 'This event was cancelled due to weather conditions.',
                'category': sports_cat,
                'event_type': 'OFFLINE',
                'starts_at': now + timedelta(days=1, hours=10),
                'timezone': 'UTC',
                'location_name': 'Beach volleyball court',
                'location': Point(-9.1521, 38.6871, srid=4326),
                'status': 'CANCELLED',
            },
            {
                'organizer': alice,
                'title': 'Full Event (No Spots Left)',
                'description': 'This event is at full capacity to demonstrate the "full" state.',
                'category': social_cat,
                'event_type': 'OFFLINE',
                'starts_at': now + timedelta(days=10, hours=19),
                'timezone': 'Europe/Lisbon',
                'location_name': 'Small meeting room',
                'location': Point(-9.1389, 38.7223, srid=4326),
                'max_participants': 2,
                'participants_count': 2,
                'status': 'PUBLISHED',
            },
        ]

        created_count = 0
        for event_data in events_data:
            event, created = Event.objects.get_or_create(
                title=event_data['title'],
                organizer=event_data['organizer'],
                defaults=event_data
            )
            if created:
                created_count += 1
                self.stdout.write(f'  Created: {event.title}')
            else:
                self.stdout.write(f'  Exists: {event.title}')

        # Add some participants
        if bob:
            morning_run = Event.objects.filter(title='Morning Run in the Park').first()
            if morning_run:
                EventParticipant.objects.get_or_create(
                    event=morning_run,
                    profile=bob,
                    defaults={'status': 'GOING'}
                )
                morning_run.participants_count = morning_run.event_participants.filter(status='GOING').count()
                morning_run.save(update_fields=['participants_count'])

        if charlie:
            yoga = Event.objects.filter(title='Online Yoga Session').first()
            if yoga:
                EventParticipant.objects.get_or_create(
                    event=yoga,
                    profile=charlie,
                    defaults={'status': 'MAYBE'}
                )

        self.stdout.write(self.style.SUCCESS(f'\n✅ Created {created_count} new events'))
        self.stdout.write(self.style.SUCCESS('🎉 Done!'))
