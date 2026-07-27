"""
seed_eu_territory — create the European Union supranational territory and link
its member countries as children.

The EU sits one level above ``country``. Because a voter's residency chain is
resolved by walking ``parent`` links, making the EU the parent of each member
country means every resident of a member state automatically rolls up into the
EU scope — no special-case eligibility code. See PK/civic-polls-system.md.

Idempotent: safe to re-run (e.g. after new country rows are imported).

Usage:
    python3 manage.py seed_eu_territory
"""
from django.core.management.base import BaseCommand

from geo.models import Territory

# ISO 3166-1 alpha-2 of the 27 EU member states.
EU_MEMBERS = [
    'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR',
    'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK',
    'SI', 'ES', 'SE',
]


class Command(BaseCommand):
    help = "Create the EU supranational territory and parent-link member countries"

    def handle(self, *args, **opts):
        eu, created = Territory.objects.update_or_create(
            country='EU', level=Territory.Level.EU, code='EU',
            defaults={'name': 'European Union', 'is_active': True},
        )
        self.stdout.write(f"EU territory {'created' if created else 'exists'}: {eu.id}")

        linked, missing = 0, []
        for iso in EU_MEMBERS:
            country = Territory.objects.filter(
                level=Territory.Level.COUNTRY, code=iso,
            ).first()
            if country is None:
                missing.append(iso)
                continue
            if country.parent_id != eu.id:
                country.parent = eu
                country.save(update_fields=['parent'])
                linked += 1

        self.stdout.write(f"Linked {linked} member countries to the EU (already-linked skipped)")
        if missing:
            self.stderr.write(f"Missing country rows (run import_territories --countries): {missing}")
