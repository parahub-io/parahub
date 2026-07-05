"""
seed_civic_topics — curated taxonomy subset for civic polls and standing delegations.

Idempotent. Creates root 'civic-topics' + children with 6-language names.
Reference data is English-first (PK pattern); UI translates via name_i18n.
"""
from django.core.management.base import BaseCommand

from taxonomy.models import Category

TOPICS = [
    ('civic-health', 'Healthcare', '🩺',
     {'en': 'Healthcare', 'ru': 'Здравоохранение', 'pt': 'Saúde', 'es': 'Sanidad', 'de': 'Gesundheit', 'fr': 'Santé'}),
    ('civic-environment', 'Environment', '🌱',
     {'en': 'Environment', 'ru': 'Экология', 'pt': 'Ambiente', 'es': 'Medio ambiente', 'de': 'Umwelt', 'fr': 'Environnement'}),
    ('civic-transport', 'Transport', '🚌',
     {'en': 'Transport', 'ru': 'Транспорт', 'pt': 'Transportes', 'es': 'Transporte', 'de': 'Verkehr', 'fr': 'Transports'}),
    ('civic-economy', 'Economy', '💶',
     {'en': 'Economy', 'ru': 'Экономика', 'pt': 'Economia', 'es': 'Economía', 'de': 'Wirtschaft', 'fr': 'Économie'}),
    ('civic-education', 'Education', '🎓',
     {'en': 'Education', 'ru': 'Образование', 'pt': 'Educação', 'es': 'Educación', 'de': 'Bildung', 'fr': 'Éducation'}),
    ('civic-rights', 'Rights & society', '⚖️',
     {'en': 'Rights & society', 'ru': 'Права и общество', 'pt': 'Direitos e sociedade', 'es': 'Derechos y sociedad', 'de': 'Rechte & Gesellschaft', 'fr': 'Droits et société'}),
    ('civic-budget', 'Public budget', '🏛️',
     {'en': 'Public budget', 'ru': 'Публичный бюджет', 'pt': 'Orçamento público', 'es': 'Presupuesto público', 'de': 'Öffentlicher Haushalt', 'fr': 'Budget public'}),
    ('civic-safety', 'Safety', '🛟',
     {'en': 'Safety', 'ru': 'Безопасность', 'pt': 'Segurança', 'es': 'Seguridad', 'de': 'Sicherheit', 'fr': 'Sécurité'}),
]


class Command(BaseCommand):
    help = "Seed curated civic topic categories (root: civic-topics)"

    def handle(self, *args, **opts):
        root, created = Category.objects.update_or_create(
            slug='civic-topics',
            defaults={'name': 'Civic topics', 'is_active': True,
                      'description': 'Curated topics for civic opinion polls and standing delegations'},
        )
        self.stdout.write(f"root civic-topics: {'created' if created else 'exists'}")
        for order, (slug, name, icon, i18n) in enumerate(TOPICS):
            _, was_created = Category.objects.update_or_create(
                slug=slug,
                defaults={'name': name, 'parent': root, 'icon': icon,
                          'name_i18n': i18n, 'is_active': True, 'order': order},
            )
            self.stdout.write(f"  {'+' if was_created else '='} {slug}")
        self.stdout.write(self.style.SUCCESS(f"civic topics ready ({len(TOPICS)})"))
