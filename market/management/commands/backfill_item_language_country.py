"""
Backfill language (auto-detect from text) and country_code (from coordinates via Pelias)
for all existing market items.

Usage:
    python manage.py backfill_item_language_country
    python manage.py backfill_item_language_country --language-only
    python manage.py backfill_item_language_country --country-only
    python manage.py backfill_item_language_country --batch-size 50
"""

from django.core.management.base import BaseCommand
from market.models import Item
from geo.utils import detect_content_language, get_country_code_from_coords


class Command(BaseCommand):
    help = 'Backfill language and country_code for existing market items'

    def add_arguments(self, parser):
        parser.add_argument('--language-only', action='store_true', help='Only update language field')
        parser.add_argument('--country-only', action='store_true', help='Only update country_code field')
        parser.add_argument('--batch-size', type=int, default=100, help='Items per batch (default: 100)')

    def handle(self, *args, **options):
        language_only = options['language_only']
        country_only = options['country_only']
        batch_size = options['batch_size']

        do_language = not country_only
        do_country = not language_only

        queryset = Item.objects.select_related('owner').all()
        total = queryset.count()
        self.stdout.write(f"Processing {total} items (batch_size={batch_size})...")

        updated = 0
        errors = 0
        offset = 0

        while offset < total:
            batch = list(queryset[offset:offset + batch_size])
            to_save = []

            for item in batch:
                changed = False
                try:
                    if do_language:
                        new_lang = detect_content_language(
                            item.title, item.description or '',
                            fallback=item.owner.preferred_language or '',
                        )
                        if new_lang != item.language:
                            item.language = new_lang
                            changed = True

                    if do_country and item.location:
                        new_country = get_country_code_from_coords(
                            item.location.y, item.location.x
                        )
                        if new_country != item.country_code:
                            item.country_code = new_country
                            changed = True

                    if changed:
                        to_save.append(item)
                except Exception as e:
                    errors += 1
                    self.stderr.write(f"  Error processing item {item.id}: {e}")

            if to_save:
                update_fields = []
                if do_language:
                    update_fields.append('language')
                if do_country:
                    update_fields.append('country_code')
                Item.objects.bulk_update(to_save, update_fields)
                updated += len(to_save)
                self.stdout.write(f"  Batch {offset}–{offset + len(batch)}: updated {len(to_save)}")

            offset += batch_size

        self.stdout.write(self.style.SUCCESS(
            f"Done. Updated {updated}/{total} items. Errors: {errors}."
        ))
