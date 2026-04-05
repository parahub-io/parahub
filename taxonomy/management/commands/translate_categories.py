"""
Django management command to add English translations to categories.

Usage:
    python manage.py translate_categories [--level 0] [--dry-run]
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from taxonomy.models import Category


# Translation dictionary: Russian -> English
TRANSLATIONS = {
    # Top level (26 categories)
    "Транспорт": "Transport",
    "Недвижимость": "Real Estate",
    "Электроника": "Electronics",
    "Телефоны и гаджеты": "Phones & Gadgets",
    "Бытовая техника": "Appliances",
    "Для дома и сада": "Home & Garden",
    "Одежда и обувь": "Fashion & Footwear",
    "Красота и здоровье": "Beauty & Health",
    "Детские товары": "Kids & Baby",
    "Хобби и спорт": "Hobby & Sports",
    "Продукты питания": "Food & Beverages",
    "Животные": "Pets & Animals",
    "Бизнес и оборудование": "Business & Equipment",
    "Ремонт и строительство": "Repair & Construction",
    "Транспортные услуги": "Transport Services",
    "Ремонт техники": "Repair Services",
    "Автосервисы": "Auto Services",
    "IT и разработка": "IT & Development",
    "Образование и тренинги": "Education & Training",
    "Бизнес-услуги": "Business Services",
    "Организация мероприятий": "Event Organization",
    "Домашние услуги": "Home Services",
    "Работа и вакансии": "Jobs & Vacancies",
    "Туризм и отдых": "Tourism & Travel",
    "Прочие услуги": "Other Services",

    # Transport (level 1)
    "Легковые автомобили": "Cars",
    "Мотоциклы и мототехника": "Motorcycles",
    "Грузовики и спецтехника": "Trucks & Special Equipment",
    "Водный транспорт": "Water Transport",
    "Запчасти и аксессуары": "Parts & Accessories",
    "Велосипеды и самокаты": "Bicycles & Scooters",

    # Real Estate
    "Квартиры": "Apartments",
    "Комнаты": "Rooms",
    "Дома и дачи": "Houses & Cottages",
    "Земельные участки": "Land",
    "Коммерческая недвижимость": "Commercial Real Estate",
    "Продажа квартир": "Apartments for Sale",
    "Аренда квартир": "Apartments for Rent",
    "Посуточная аренда": "Daily Rent",
    "Продажа комнат": "Rooms for Sale",
    "Аренда комнат": "Rooms for Rent",
    "Продажа домов": "Houses for Sale",
    "Аренда домов": "Houses for Rent",
    "Продажа участков": "Land for Sale",
    "Аренда участков": "Land for Rent",
    "Офисы": "Offices",
    "Торговые помещения": "Retail Spaces",
    "Склады и производство": "Warehouses & Manufacturing",
    "Гаражи и парковки": "Garages & Parking",

    # Electronics
    "Компьютеры и ноутбуки": "Computers & Laptops",
    "Комплектующие": "Components",
    "Периферия": "Peripherals",
    "Сетевое оборудование": "Networking Equipment",
    "Серверы и СХД": "Servers & Storage",
    "Оргтехника": "Office Equipment",
    "Программное обеспечение": "Software",
    "Игровые консоли и игры": "Gaming Consoles & Games",

    # Common terms
    "Другое": "Other",
    "Разное": "Miscellaneous",
    "Аксессуары": "Accessories",
    "Запчасти": "Parts",
    "Услуги": "Services",
    "Ремонт": "Repair",
    "Установка": "Installation",
    "Обслуживание": "Maintenance",
    "Продажа": "Sale",
    "Аренда": "Rent",
}


class Command(BaseCommand):
    help = 'Add English translations to categories'

    def add_arguments(self, parser):
        parser.add_argument(
            '--level',
            type=int,
            default=None,
            help='Translate only specific level (0=top, 1=second, etc). If not specified, translates all.'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be translated without actually translating'
        )

    def handle(self, *args, **options):
        level = options['level']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        # Get categories to translate
        if level is not None:
            # Get categories at specific depth
            if level == 0:
                categories = Category.objects.filter(parent__isnull=True)
            else:
                # This is tricky - need to traverse tree
                categories = self._get_categories_at_level(level)

            self.stdout.write(f"Translating level {level} categories...")
        else:
            categories = Category.objects.all()
            self.stdout.write(f"Translating all categories...")

        self.stdout.write(f"Found {categories.count()} categories")

        stats = {'translated': 0, 'skipped': 0, 'missing': 0}

        with transaction.atomic():
            for category in categories:
                result = self._translate_category(category, dry_run)
                stats[result] += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Translation complete!"
            f"\n  Translated: {stats['translated']}"
            f"\n  Skipped (already has EN): {stats['skipped']}"
            f"\n  Missing in dictionary: {stats['missing']}"
        ))

        if stats['missing'] > 0:
            self.stdout.write(self.style.WARNING(
                f"\nℹ Some categories don't have translations in dictionary."
                f"\n  Add them to TRANSLATIONS dict in this script."
            ))

    def _get_categories_at_level(self, target_level):
        """Get all categories at specific depth level"""
        categories = []

        def traverse(cat, current_level):
            if current_level == target_level:
                categories.append(cat)
            else:
                for child in cat.children.all():
                    traverse(child, current_level + 1)

        # Start from root
        for root in Category.objects.filter(parent__isnull=True):
            traverse(root, 0)

        return categories

    def _translate_category(self, category, dry_run=False):
        """Translate a single category"""
        ru_name = category.name

        # Check if already has English translation
        if category.name_i18n.get('en'):
            self.stdout.write(f"  ⊘ {ru_name} - already has EN translation")
            return 'skipped'

        # Look up translation
        en_name = TRANSLATIONS.get(ru_name)

        if not en_name:
            self.stdout.write(self.style.ERROR(f"  ✗ {ru_name} - NO TRANSLATION"))
            return 'missing'

        if dry_run:
            self.stdout.write(f"  ✓ {ru_name} → {en_name}")
            return 'translated'

        # Update category
        category.name_i18n['en'] = en_name

        # Also update description if exists
        if category.description and not category.description_i18n.get('en'):
            # For now, just copy Russian description as placeholder
            category.description_i18n['en'] = category.description

        category.save()

        self.stdout.write(self.style.SUCCESS(f"  ✓ {ru_name} → {en_name}"))
        return 'translated'
