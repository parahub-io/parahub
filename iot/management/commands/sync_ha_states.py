"""Sync HA entity states for all active HAHome instances."""
import asyncio
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from iot.models import HAHome
from iot import ha_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync Home Assistant entity states for all active homes'

    def handle(self, *args, **options):
        asyncio.run(self._sync_all())

    async def _sync_all(self):
        now = timezone.now()
        total_updated = 0
        total_errors = 0
        homes_synced = 0

        async for home in HAHome.objects.exclude(status='error'):
            # Respect per-home sync interval
            if home.last_seen:
                elapsed = (now - home.last_seen).total_seconds()
                if elapsed < home.sync_interval_seconds:
                    continue

            try:
                result = await ha_service.sync_home_entities(home)
                total_updated += result['updated']
                total_errors += result['errors']
                homes_synced += 1
            except Exception:
                logger.exception("Failed to sync home %s", home.name)
                total_errors += 1

        if homes_synced > 0:
            self.stdout.write(
                f"Synced {homes_synced} homes: {total_updated} entities updated, {total_errors} errors"
            )
