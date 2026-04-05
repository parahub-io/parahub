#!/usr/bin/env python3
"""
Convert categories from single CSV to two-file format.

Old format (categories_i18n.csv):
  id,slug,parent_id,name_ru,name_en,name_pt,name_es,desc_ru,desc_en,desc_pt,desc_es

New format:
  categories.csv: id,slug,parent_id
  categories_i18n.csv: category_id,lang,name,description
"""
import csv
import sys

def convert():
    input_file = 'data/categories_i18n.csv'
    structure_file = 'data/categories.csv'
    i18n_file = 'data/categories_i18n.csv.new'

    print(f"Converting {input_file} to two-file format...")
    print(f"  Structure: {structure_file}")
    print(f"  i18n: {i18n_file}")

    categories_count = 0
    translations_count = 0

    with open(input_file, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)

        # Write structure file
        with open(structure_file, 'w', encoding='utf-8', newline='') as struct_file:
            struct_writer = csv.writer(struct_file)
            struct_writer.writerow(['id', 'slug', 'parent_id'])

            # Write i18n file
            with open(i18n_file, 'w', encoding='utf-8', newline='') as trans_file:
                trans_writer = csv.writer(trans_file)
                trans_writer.writerow(['category_id', 'lang', 'name', 'description'])

                for row in reader:
                    # Write structure
                    struct_writer.writerow([
                        row['id'],
                        row['slug'],
                        row['parent_id']
                    ])
                    categories_count += 1

                    # Write translations for each language
                    languages = [
                        ('en', row.get('name_en', ''), row.get('description_en', '')),
                        ('ru', row.get('name_ru', ''), row.get('description_ru', '')),
                        ('pt', row.get('name_pt', ''), row.get('description_pt', '')),
                        ('es', row.get('name_es', ''), row.get('description_es', ''))
                    ]

                    for lang, name, desc in languages:
                        if name:  # Only write if name exists
                            trans_writer.writerow([
                                row['id'],
                                lang,
                                name,
                                desc
                            ])
                            translations_count += 1

    print(f"\n✅ Conversion complete:")
    print(f"  Categories: {categories_count}")
    print(f"  Translations: {translations_count}")
    print(f"\nNext steps:")
    print(f"  1. Review {structure_file}")
    print(f"  2. Review {i18n_file}")
    print(f"  3. Backup old file: mv data/categories_i18n.csv data/categories_i18n.csv.old")
    print(f"  4. Activate new: mv {i18n_file} data/categories_i18n.csv")

if __name__ == '__main__':
    convert()
