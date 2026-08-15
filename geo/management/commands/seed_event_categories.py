"""
seed_event_categories — canonical taxonomy roots for the events domain.

Idempotent. Creates the 10 event roots with 6-language names and keeps
`applicable_to` containing "events". Existing translations are never
overwritten — only missing languages are filled in.

Reference data is English-first (PK pattern); the UI reads name_i18n.
"""
from django.core.management.base import BaseCommand

from taxonomy.models import Category

# (slug, icon, {lang: name})
EVENT_ROOTS = [
    ('sports-fitness', '🏃',
     {'en': 'Sports & Fitness', 'ru': 'Спорт и фитнес', 'pt': 'Desporto e fitness',
      'es': 'Deporte y fitness', 'de': 'Sport & Fitness', 'fr': 'Sports et fitness'}),
    ('education-workshop', '📚',
     {'en': 'Education & Workshop', 'ru': 'Образование и мастер-классы', 'pt': 'Educação e workshops',
      'es': 'Educación y talleres', 'de': 'Bildung & Workshops', 'fr': 'Éducation et ateliers'}),
    ('social-meetup', '🤝',
     {'en': 'Social & Meetup', 'ru': 'Встречи и общение', 'pt': 'Social e encontros',
      'es': 'Social y encuentros', 'de': 'Treffen & Soziales', 'fr': 'Rencontres et social'}),
    ('tech-it', '💻',
     {'en': 'Tech & IT', 'ru': 'Технологии и IT', 'pt': 'Tecnologia e TI',
      'es': 'Tecnología y TI', 'de': 'Technik & IT', 'fr': 'Tech et informatique'}),
    ('music-culture', '🎵',
     {'en': 'Music & Culture', 'ru': 'Музыка и культура', 'pt': 'Música e cultura',
      'es': 'Música y cultura', 'de': 'Musik & Kultur', 'fr': 'Musique et culture'}),
    ('food-dining', '🍽️',
     {'en': 'Food & Dining', 'ru': 'Еда и гастрономия', 'pt': 'Comida e restauração',
      'es': 'Comida y gastronomía', 'de': 'Essen & Gastronomie', 'fr': 'Cuisine et gastronomie'}),
    ('art-creative', '🎨',
     {'en': 'Art & Creative', 'ru': 'Искусство и творчество', 'pt': 'Arte e criatividade',
      'es': 'Arte y creatividad', 'de': 'Kunst & Kreatives', 'fr': 'Art et création'}),
    ('health-wellness', '💆',
     {'en': 'Health & Wellness', 'ru': 'Здоровье и благополучие', 'pt': 'Saúde e bem-estar',
      'es': 'Salud y bienestar', 'de': 'Gesundheit & Wohlbefinden', 'fr': 'Santé et bien-être'}),
    ('nature-outdoors', '🌿',
     {'en': 'Nature & Outdoors', 'ru': 'Природа и активный отдых', 'pt': 'Natureza e ar livre',
      'es': 'Naturaleza y aire libre', 'de': 'Natur & Draußen', 'fr': 'Nature et plein air'}),
    ('volunteering', '🤲',
     {'en': 'Volunteering', 'ru': 'Волонтёрство', 'pt': 'Voluntariado',
      'es': 'Voluntariado', 'de': 'Ehrenamt', 'fr': 'Bénévolat'}),
]


class Command(BaseCommand):
    help = "Seed the canonical event category roots (10, six languages each)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--force-names', action='store_true',
            help='Also replace names that differ from this file (use after correcting a translation here)')

    def handle(self, *args, **opts):
        for order, (slug, icon, i18n) in enumerate(EVENT_ROOTS):
            cat, created = Category.objects.get_or_create(
                slug=slug,
                defaults={'name': i18n['en'], 'icon': icon,
                          'applicable_to': ['events'], 'order': order, 'is_active': True},
            )
            changed = []

            # Fill missing languages only — curated translations stay as they are.
            # --force-names makes this file authoritative instead, so a fix here
            # reaches a database that already holds the old wording.
            names = dict(cat.name_i18n or {})
            added = [lang for lang, name in i18n.items()
                     if not names.get(lang) or (opts['force_names'] and names[lang] != name)]
            if added:
                names.update({lang: i18n[lang] for lang in added})
                cat.name_i18n = names
                changed.append('name_i18n')

            domains = list(cat.applicable_to or [])
            if 'events' not in domains:
                cat.applicable_to = domains + ['events']
                changed.append('applicable_to')

            if not cat.icon:
                cat.icon = icon
                changed.append('icon')

            if changed:
                cat.save(update_fields=changed)

            mark = '+' if created else ('~' if changed else '=')
            langs = f" +{','.join(sorted(added))}" if added else ''
            self.stdout.write(f"  {mark} {slug}{langs}")

        self.stdout.write(self.style.SUCCESS(f"event categories ready ({len(EVENT_ROOTS)})"))
