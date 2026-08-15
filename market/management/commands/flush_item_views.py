"""
Persist Redis market view totals to Item.views_total.

Run hourly (parahub-market-views-flush.timer) so a Redis wipe loses at most
~1 hour of view counts. See parahub/services/item_views.py for the key layout.
"""

from django.core.management.base import BaseCommand

from parahub.services.item_views import flush_totals


class Command(BaseCommand):
    help = 'Flush Redis market view counters to Item.views_total'

    def handle(self, *args, **options):
        updated = flush_totals()
        self.stdout.write(self.style.SUCCESS(f'Flushed view totals for {updated} item(s)'))
