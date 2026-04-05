from django.core.management.base import BaseCommand
from django.utils import timezone
from iot.models import MeshSubscription


class Command(BaseCommand):
    help = 'Mark expired mesh WiFi subscriptions'

    def handle(self, *args, **options):
        now = timezone.now()
        expired = MeshSubscription.objects.filter(
            status='ACTIVE',
            expires_at__lte=now,
        ).update(status='EXPIRED')

        # Also expire old pending invoices (>1 hour)
        stale = MeshSubscription.objects.filter(
            status='PENDING',
            created_at__lte=now - timezone.timedelta(hours=1),
        ).update(status='EXPIRED')

        if expired or stale:
            self.stdout.write(f"Expired {expired} active, {stale} stale pending subscriptions")
        else:
            self.stdout.write("No subscriptions to expire")
