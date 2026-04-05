"""
Export categories to two-file format.

Structure file: data/categories.csv (id, slug, parent_id, icon, order, sale_only)
i18n file: data/categories_i18n.csv (category_id, lang, name, description)

Usage:
    python manage.py export_categories_csv [--output-dir data]
"""

import csv
import os
from django.core.management.base import BaseCommand
from taxonomy.models import Category


class Command(BaseCommand):
    help = 'Export categories to two-file format (structure + i18n)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default='data',
            help='Output directory for CSV files'
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir']
        structure_file = f'{output_dir}/categories.csv'
        i18n_file = f'{output_dir}/categories_i18n.csv'

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        self.stdout.write(self.style.SUCCESS(f"\n📁 Exporting categories to:"))
        self.stdout.write(f"  Structure: {structure_file}")
        self.stdout.write(f"  i18n: {i18n_file}\n")

        categories = Category.objects.all().order_by('id')
        total = categories.count()

        self.stdout.write(f"Found {total} categories\n")

        # Export structure
        self.stdout.write("Exporting structure...")
        with open(structure_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'slug', 'parent_id', 'icon', 'order', 'sale_only', 'applicable_to'])

            for cat in categories:
                writer.writerow([
                    cat.id,
                    cat.slug,
                    cat.parent.id if cat.parent else '',
                    cat.icon or '',
                    cat.order,
                    'true' if cat.sale_only else 'false',
                    '|'.join(cat.applicable_to) if cat.applicable_to else 'market',
                ])

        self.stdout.write(self.style.SUCCESS(f"  ✓ Wrote {total} categories"))

        # Export translations
        self.stdout.write("\nExporting translations...")
        translation_count = 0

        with open(i18n_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['category_id', 'lang', 'name', 'description'])

            for cat in categories:
                # English (default fields)
                if cat.name:
                    writer.writerow([
                        cat.id,
                        'en',
                        cat.name,
                        cat.description or ''
                    ])
                    translation_count += 1

                # Other languages from JSONFields
                for lang in ['ru', 'pt', 'es']:
                    name = cat.name_i18n.get(lang, '')
                    desc = cat.description_i18n.get(lang, '')

                    if name:  # Only write if name exists
                        writer.writerow([
                            cat.id,
                            lang,
                            name,
                            desc
                        ])
                        translation_count += 1

        self.stdout.write(self.style.SUCCESS(f"  ✓ Wrote {translation_count} translations"))

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Export complete!\n"
            f"  Categories: {total}\n"
            f"  Translations: {translation_count}\n"
        ))
