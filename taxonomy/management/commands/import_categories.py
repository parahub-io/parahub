"""
Django management command to import categories from YAML structure.

Usage:
    python manage.py import_categories data/catalog-structure-ru.yaml.backup
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from taxonomy.models import Category
import yaml


class Command(BaseCommand):
    help = 'Import categories from YAML file'

    def add_arguments(self, parser):
        parser.add_argument(
            'yaml_file',
            type=str,
            help='Path to YAML file with category structure'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing categories before import'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without actually importing'
        )

    def handle(self, *args, **options):
        yaml_file = options['yaml_file']
        clear = options['clear']
        dry_run = options['dry_run']

        self.stdout.write(f"Reading categories from: {yaml_file}")

        # Load YAML
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        categories = data.get('categories', [])
        self.stdout.write(f"Found {len(categories)} top-level categories")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        if clear and not dry_run:
            self.stdout.write(self.style.WARNING("Clearing existing categories..."))
            Category.objects.all().delete()

        # Import categories
        with transaction.atomic():
            stats = self._import_categories(categories, parent=None, dry_run=dry_run)

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Import complete!"
            f"\n  Created: {stats['created']}"
            f"\n  Updated: {stats['updated']}"
            f"\n  Skipped: {stats['skipped']}"
            f"\n  Total: {stats['total']}"
        ))

    def _import_categories(self, categories, parent=None, dry_run=False, level=0):
        """Recursively import categories"""
        stats = {'created': 0, 'updated': 0, 'skipped': 0, 'total': 0}

        for cat_data in categories:
            stats['total'] += 1
            indent = "  " * level

            name = cat_data.get('name')
            slug = cat_data.get('slug')
            description = cat_data.get('description', '')
            icon = cat_data.get('icon', '')
            cat_type = cat_data.get('type', 'goods')

            # Handle i18n fields
            name_i18n = cat_data.get('name_i18n', {})
            description_i18n = cat_data.get('description_i18n', {})

            # If name_i18n is empty, populate with Russian name
            if not name_i18n:
                name_i18n = {'ru': name}

            self.stdout.write(f"{indent}{icon} {name} ({slug})")

            if dry_run:
                stats['created'] += 1
            else:
                # Create or update category
                category, created = Category.objects.update_or_create(
                    slug=slug,
                    defaults={
                        'name': name,
                        'description': description,
                        'parent': parent,
                        'icon': icon,
                        'category_type': cat_type,
                        'name_i18n': name_i18n,
                        'description_i18n': description_i18n,
                        'is_active': True,
                    }
                )

                if created:
                    stats['created'] += 1
                    self.stdout.write(self.style.SUCCESS(f"{indent}  ✓ Created"))
                else:
                    stats['updated'] += 1
                    self.stdout.write(self.style.WARNING(f"{indent}  ↻ Updated"))

            # Import children recursively (both in dry-run and real mode)
            children = cat_data.get('children', [])
            if children:
                child_stats = self._import_categories(
                    children,
                    parent=category if not dry_run else None,
                    dry_run=dry_run,
                    level=level + 1
                )
                for key in stats:
                    stats[key] += child_stats[key]

        return stats
