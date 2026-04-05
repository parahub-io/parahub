"""
Management command to sync PostgreSQL data to Neo4j graph
"""

from django.core.management.base import BaseCommand
from market.models import Item
from taxonomy.models import Category
from identity.models import Profile
from barter.graph_service import BarterGraphService


class Command(BaseCommand):
    help = 'Sync PostgreSQL data (Users, Categories, Items) to Neo4j graph'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Clear Neo4j graph before syncing'
        )
        parser.add_argument(
            '--users-only',
            action='store_true',
            help='Sync only users'
        )
        parser.add_argument(
            '--categories-only',
            action='store_true',
            help='Sync only categories'
        )
        parser.add_argument(
            '--items-only',
            action='store_true',
            help='Sync only items'
        )

    def handle(self, *args, **options):
        graph_service = BarterGraphService()

        if options['reset']:
            self.stdout.write(self.style.WARNING('Clearing Neo4j graph...'))
            clear_query = """
            MATCH (n)
            DETACH DELETE n
            """
            graph_service.client.execute_write(clear_query)
            self.stdout.write(self.style.SUCCESS('Graph cleared'))

        # Sync users
        if not options['categories_only'] and not options['items_only']:
            self.stdout.write('Syncing users...')
            profiles = Profile.objects.all()
            total = profiles.count()

            for i, profile in enumerate(profiles, 1):
                try:
                    graph_service.sync_user_to_graph(profile)
                    if i % 100 == 0:
                        self.stdout.write(f'  {i}/{total} users synced')
                except Exception as e:
                    self.stderr.write(f'Failed to sync user {profile.id}: {e}')

            self.stdout.write(self.style.SUCCESS(f'Synced {total} users'))

        # Sync categories
        if not options['users_only'] and not options['items_only']:
            self.stdout.write('Syncing categories...')
            # Order by parent_id nulls first (root categories first), then by order and id
            categories = Category.objects.all().order_by('parent_id', 'order', 'id')
            total = categories.count()

            for i, category in enumerate(categories, 1):
                try:
                    graph_service.sync_category_to_graph(category)
                    if i % 50 == 0:
                        self.stdout.write(f'  {i}/{total} categories synced')
                except Exception as e:
                    self.stderr.write(f'Failed to sync category {category.id}: {e}')

            self.stdout.write(self.style.SUCCESS(f'Synced {total} categories'))

        # Sync items
        if not options['users_only'] and not options['categories_only']:
            self.stdout.write('Syncing items...')
            items = Item.objects.filter(
                is_active=True,
                type__in=['CREDIT', 'DEBIT']
            ).select_related('owner', 'category')

            total = items.count()

            for i, item in enumerate(items, 1):
                if not item.owner or not item.category:
                    continue

                try:
                    graph_service.sync_item_to_graph(item)
                    if i % 100 == 0:
                        self.stdout.write(f'  {i}/{total} items synced')
                except Exception as e:
                    self.stderr.write(f'Failed to sync item {item.id}: {e}')

            self.stdout.write(self.style.SUCCESS(f'Synced {total} items'))

        # Show stats
        stats = graph_service.get_graph_stats()
        self.stdout.write(self.style.SUCCESS('\nNeo4j Graph Statistics:'))
        self.stdout.write(f"  Users: {stats.get('users', 0)}")
        self.stdout.write(f"  Categories: {stats.get('categories', 0)}")
        self.stdout.write(f"  Items: {stats.get('items', 0)}")
        self.stdout.write(f"  OWNS relationships: {stats.get('owns_relationships', 0)}")
        self.stdout.write(f"  IN_CATEGORY relationships: {stats.get('category_relationships', 0)}")
