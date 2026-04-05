"""
Initialize Neo4j database with indexes and constraints
"""

from django.core.management.base import BaseCommand
from barter.neo4j_client import Neo4jClient


class Command(BaseCommand):
    help = 'Initialize Neo4j with indexes and constraints for barter system'

    def handle(self, *args, **options):
        client = Neo4jClient()

        self.stdout.write('Initializing Neo4j indexes and constraints...')

        queries = [
            # Constraints (ensures uniqueness)
            "CREATE CONSTRAINT user_cri_unique IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
            "CREATE CONSTRAINT item_cri_unique IF NOT EXISTS FOR (i:Item) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT category_cri_unique IF NOT EXISTS FOR (c:Category) REQUIRE c.id IS UNIQUE",

            # Indexes for fast lookups
            "CREATE INDEX user_display_name_idx IF NOT EXISTS FOR (u:User) ON (u.display_name)",
            "CREATE INDEX item_type_active_idx IF NOT EXISTS FOR (i:Item) ON (i.type, i.is_active)",
            "CREATE INDEX item_owner_idx IF NOT EXISTS FOR (i:Item) ON (i.owner_id)",
            "CREATE INDEX item_category_idx IF NOT EXISTS FOR (i:Item) ON (i.category_id)",
            "CREATE INDEX category_slug_idx IF NOT EXISTS FOR (c:Category) ON (c.slug)",

            # Point index for geospatial queries
            "CREATE POINT INDEX item_location_idx IF NOT EXISTS FOR (i:Item) ON (i.location)",
        ]

        for query in queries:
            try:
                client.execute_write(query)
                self.stdout.write(self.style.SUCCESS(f'  ✓ {query[:60]}...'))
            except Exception as e:
                # Neo4j returns error if constraint/index already exists
                if "already exists" in str(e) or "An equivalent" in str(e):
                    self.stdout.write(self.style.WARNING(f'  ~ {query[:60]}... (already exists)'))
                else:
                    self.stderr.write(self.style.ERROR(f'  ✗ {query[:60]}... ERROR: {e}'))

        # Verify connectivity
        if client.verify_connectivity():
            self.stdout.write(self.style.SUCCESS('\n✓ Neo4j connection verified'))
        else:
            self.stderr.write(self.style.ERROR('\n✗ Neo4j connection failed'))

        # Show existing constraints and indexes
        self.stdout.write('\nExisting constraints:')
        constraints = client.execute_read("SHOW CONSTRAINTS")
        for constraint in constraints:
            self.stdout.write(f"  - {constraint.get('name', 'N/A')}")

        self.stdout.write('\nExisting indexes:')
        indexes = client.execute_read("SHOW INDEXES")
        for index in indexes:
            self.stdout.write(f"  - {index.get('name', 'N/A')}")

        self.stdout.write(self.style.SUCCESS('\n✓ Neo4j initialization complete'))
