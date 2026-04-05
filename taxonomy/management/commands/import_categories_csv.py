"""
Import categories from two-file format.

Structure file: data/categories.csv (id, slug, parent_id, icon, order, sale_only)
i18n file: data/categories_i18n.csv (category_id, lang, name, description)

Usage:
    python manage.py import_categories_csv [--dry-run] [--structure-only] [--i18n-only]
"""

import csv
from django.core.management.base import BaseCommand
from django.db import transaction
from taxonomy.models import Category


class Command(BaseCommand):
    help = 'Import categories from two-file format (structure + i18n)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without actually importing'
        )
        parser.add_argument(
            '--structure-only',
            action='store_true',
            help='Only import structure (categories.csv)'
        )
        parser.add_argument(
            '--i18n-only',
            action='store_true',
            help='Only import translations (categories_i18n.csv)'
        )
        parser.add_argument(
            '--structure-file',
            type=str,
            default='data/categories.csv',
            help='Path to structure CSV file'
        )
        parser.add_argument(
            '--i18n-file',
            type=str,
            default='data/categories_i18n.csv',
            help='Path to i18n CSV file'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        structure_only = options['structure_only']
        i18n_only = options['i18n_only']
        structure_file = options['structure_file']
        i18n_file = options['i18n_file']

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made\n"))

        stats = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
            'translations': {}
        }

        with transaction.atomic():
            # Import structure
            if not i18n_only:
                self.stdout.write(self.style.SUCCESS(f"\n📁 Importing structure from {structure_file}"))
                self._import_structure(structure_file, stats, dry_run)

            # Import translations
            if not structure_only:
                self.stdout.write(self.style.SUCCESS(f"\n🌐 Importing translations from {i18n_file}"))
                self._import_i18n(i18n_file, stats, dry_run)

            if dry_run:
                transaction.set_rollback(True)

        # Print summary
        self.stdout.write(self.style.SUCCESS(
            f"\n{'DRY RUN ' if dry_run else ''}Import complete!\n"
            f"  Created: {stats['created']}\n"
            f"  Updated: {stats['updated']}\n"
            f"  Skipped: {stats['skipped']}\n"
            f"  Errors: {stats['errors']}\n"
        ))

        if stats['translations']:
            self.stdout.write("\nTranslations added:")
            for lang, count in sorted(stats['translations'].items()):
                self.stdout.write(f"  {lang.upper()}: {count}")

    def _import_structure(self, filename, stats, dry_run):
        """Import category structure (id, slug, parent_id)"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File not found: {filename}"))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading CSV: {e}"))
            return

        self.stdout.write(f"Found {len(rows)} categories\n")

        # First pass: create all categories without parent links
        category_map = {}
        for row in rows:
            try:
                cat_id = row['id']
                slug = row['slug']
                parent_id = row['parent_id']
                icon = row.get('icon', '')
                order = int(row.get('order', 0))
                sale_only = row.get('sale_only', 'false').lower() == 'true'
                applicable_to_raw = row.get('applicable_to', '')
                applicable_to = [x.strip() for x in applicable_to_raw.split('|') if x.strip()] if applicable_to_raw else []

                # Check if exists
                try:
                    category = Category.objects.get(id=cat_id)
                    category_map[cat_id] = category

                    # Update fields if changed
                    updated = False
                    if category.slug != slug:
                        category.slug = slug
                        updated = True
                    if category.icon != icon:
                        category.icon = icon if icon else None
                        updated = True
                    if category.order != order:
                        category.order = order
                        updated = True
                    if category.sale_only != sale_only:
                        category.sale_only = sale_only
                        updated = True
                    if applicable_to and sorted(category.applicable_to) != sorted(applicable_to):
                        category.applicable_to = applicable_to
                        updated = True

                    if updated:
                        if not dry_run:
                            category.save()
                        self.stdout.write(f"  ✓ Updated: {cat_id} ({slug})")
                        stats['updated'] += 1
                    else:
                        stats['skipped'] += 1

                except Category.DoesNotExist:
                    # Create new category
                    category = Category(
                        id=cat_id,
                        slug=slug,
                        name=slug.replace('-', ' ').title(),  # Temporary name
                        icon=icon if icon else None,
                        order=order,
                        sale_only=sale_only,
                        applicable_to=applicable_to if applicable_to else ['market'],
                    )
                    if not dry_run:
                        category.save()
                    category_map[cat_id] = category
                    self.stdout.write(f"  + Created: {cat_id} ({slug})")
                    stats['created'] += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {row.get('id', 'unknown')}: {e}"))
                stats['errors'] += 1

        # Second pass: set parent relationships
        for row in rows:
            cat_id = row['id']
            parent_id = row['parent_id']

            if parent_id and parent_id in category_map:
                category = category_map[cat_id]
                parent = category_map[parent_id]

                if category.parent != parent:
                    category.parent = parent
                    if not dry_run:
                        category.save()

    def _import_i18n(self, filename, stats, dry_run):
        """Import translations (category_id, lang, name, description)"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File not found: {filename}"))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading CSV: {e}"))
            return

        self.stdout.write(f"Found {len(rows)} translations\n")

        # Group by category
        by_category = {}
        for row in rows:
            cat_id = row['category_id']
            if cat_id not in by_category:
                by_category[cat_id] = []
            by_category[cat_id].append(row)

        # Process each category
        for cat_id, translations in by_category.items():
            try:
                category = Category.objects.get(id=cat_id)
                has_updates = False

                for trans in translations:
                    lang = trans['lang']
                    name = trans['name'].strip()
                    description = trans.get('description', '').strip()

                    # Update name
                    if name:
                        if lang == 'en':
                            # English is the default name field
                            if category.name != name:
                                category.name = name
                                has_updates = True
                        else:
                            # Other languages go into name_i18n
                            if category.name_i18n.get(lang) != name:
                                category.name_i18n[lang] = name
                                has_updates = True

                        if lang not in stats['translations']:
                            stats['translations'][lang] = 0
                        stats['translations'][lang] += 1

                    # Update description
                    if description:
                        if lang == 'en':
                            if category.description != description:
                                category.description = description
                                has_updates = True
                        else:
                            if category.description_i18n.get(lang) != description:
                                category.description_i18n[lang] = description
                                has_updates = True

                if has_updates:
                    if not dry_run:
                        category.save()
                    self.stdout.write(f"  ✓ {category.slug}: {len(translations)} translations")
                    stats['updated'] += 1

            except Category.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"  ✗ Category {cat_id} not found"))
                stats['errors'] += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error {cat_id}: {e}"))
                stats['errors'] += 1
