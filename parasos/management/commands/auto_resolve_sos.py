"""Auto-resolve SOS alerts that have been active for more than 2 hours with no responses."""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Auto-resolve stale SOS alerts (active > 2h without response)'

    def handle(self, *args, **options):
        from parasos.models import SOSAlert
        from parahub.services.ws_publish import ws_publish

        cutoff = timezone.now() - timedelta(hours=2)

        stale = SOSAlert.objects.filter(
            status=SOSAlert.Status.ACTIVE,
            created_at__lt=cutoff,
        )

        count = 0
        for alert in stale:
            alert.status = SOSAlert.Status.RESOLVED
            alert.resolved_at = timezone.now()
            alert.save(update_fields=['status', 'resolved_at'])

            # Notify via WS
            ws_publish(f"parasos:{alert.group_id}", {
                "type": "sos.resolved",
                "alert": {
                    "id": alert.id,
                    "status": "RESOLVED",
                    "auto_resolved": True,
                },
            })
            count += 1

        if count:
            self.stdout.write(self.style.SUCCESS(f'Auto-resolved {count} stale SOS alerts'))
        else:
            self.stdout.write('No stale alerts found')
