#!/usr/bin/env python3
"""
Apply translations from batch files to database.
"""

import sys
import os

# Add project to path
sys.path.insert(0, '/opt/parahub')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parahub.settings')

import django
django.setup()

from taxonomy.models import Category


def parse_batch_file(filepath):
    """Parse translation batch file"""
    translations = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) >= 4:
                ru = parts[0]
                en = parts[1]
                pt = parts[2]
                es = parts[3]
                translations[ru] = {'en': en, 'pt': pt, 'es': es}
    return translations


def apply_translations(translations):
    """Apply translations to database"""
    updated = 0
    for category in Category.objects.all():
        if category.name in translations:
            trans = translations[category.name]
            changed = False

            for lang in ['en', 'pt', 'es']:
                if trans[lang] and not category.name_i18n.get(lang):
                    category.name_i18n[lang] = trans[lang]
                    changed = True

            if changed:
                category.save()
                updated += 1
                print(f"✓ {category.slug}: {trans['en']}")

    return updated


def main():
    import glob

    # Find all batch files
    batch_files = sorted(glob.glob('/opt/parahub/scripts/batch*.txt'))

    if not batch_files:
        print("No batch files found!")
        return

    print(f"Found {len(batch_files)} batch files\n")

    total_updated = 0
    for batch_file in batch_files:
        print(f"\nProcessing {os.path.basename(batch_file)}...")
        translations = parse_batch_file(batch_file)
        print(f"  Loaded {len(translations)} translations")

        updated = apply_translations(translations)
        total_updated += updated
        print(f"  Updated {updated} categories")

    # Show final statistics
    print(f"\n{'='*60}")
    print(f"Total updated: {total_updated}")
    print(f"{'='*60}\n")

    total = Category.objects.count()
    with_en = Category.objects.exclude(name_i18n__en__isnull=True).exclude(name_i18n__en='').count()
    with_pt = Category.objects.exclude(name_i18n__pt__isnull=True).exclude(name_i18n__pt='').count()
    with_es = Category.objects.exclude(name_i18n__es__isnull=True).exclude(name_i18n__es='').count()

    print(f"Translation coverage:")
    print(f"  EN: {with_en}/{total} ({with_en*100//total}%)")
    print(f"  PT: {with_pt}/{total} ({with_pt*100//total}%)")
    print(f"  ES: {with_es}/{total} ({with_es*100//total}%)")

    remaining_en = total - with_en
    print(f"\nStill need to translate: {remaining_en} categories")


if __name__ == '__main__':
    main()
