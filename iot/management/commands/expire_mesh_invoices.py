from django.core.management.base import BaseCommand
from django.utils import timezone
from iot.models import MeshPassCredit


class Command(BaseCommand):
    help = 'Expire stale pending mesh pass invoices (>1 hour unpaid)'

    def handle(self, *args, **options):
        # Pass expiry itself needs no job: routers recompute paid clients from
        # active passes on every heartbeat, so lapsed passes drop off within
        # 5 minutes. Only unpaid Lightning invoices need cleaning up.
        now = timezone.now()
        stale = MeshPassCredit.objects.filter(
            status='PENDING',
            created_at__lte=now - timezone.timedelta(hours=1),
        ).update(status='EXPIRED')

        if stale:
            self.stdout.write(f"Expired {stale} stale pending invoices")
        else:
            self.stdout.write("No invoices to expire")
