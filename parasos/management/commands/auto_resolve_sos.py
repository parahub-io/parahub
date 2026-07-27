"""Auto-resolve SOS alerts that have been active for more than 2 hours."""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Auto-resolve stale SOS alerts (active > 2h)'

    def handle(self, *args, **options):
        from parasos.models import SOSAlert
        from parahub.services.ws_publish import ws_publish

        cutoff = timezone.now() - timedelta(hours=2)

        stale = SOSAlert.objects.filter(
            status=SOSAlert.Status.ACTIVE,
            created_at__lt=cutoff,
        ).select_related('group')

        count = 0
        for alert in stale:
            alert.status = SOSAlert.Status.RESOLVED
            alert.resolved_at = timezone.now()
            alert.save(update_fields=['status', 'resolved_at'])

            # Notify via WS — top-level group_id/group_name are part of the
            # event contract (group page filters on group_id)
            ws_publish(f"parasos:{alert.group_id}", {
                "type": "sos.resolved",
                "group_id": alert.group_id,
                "group_name": alert.group.name,
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
