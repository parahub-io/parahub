"""
expire_shipments — enforce Shipment.expires_at:
  1. Expire shipments in AT_ORIGIN/AT_HUB/READY past their expires_at
  2. Expire CREATED shipments older than 7 days (never deposited)

Run hourly via systemd timer.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import logging

from logistics.models import Shipment, ShipmentEvent

logger = logging.getLogger(__name__)

CREATED_GRACE_DAYS = 7


class Command(BaseCommand):
    help = "Expire shipments past their expires_at or stale CREATED shipments"

    def handle(self, *args, **options):
        now = timezone.now()
        expired_count = 0

        # 1. Shipments with expires_at set and past due
        deposited_expired = Shipment.objects.filter(
            expires_at__lte=now,
            status__in=[
                Shipment.Status.AT_ORIGIN,
                Shipment.Status.AT_HUB,
                Shipment.Status.READY,
            ],
        ).select_related('sender', 'receiver', 'current_hub', 'current_hub__owner')

        for shipment in deposited_expired:
            shipment.status = Shipment.Status.EXPIRED
            shipment.save(update_fields=['status', 'updated_at'])

            ShipmentEvent.objects.create(
                shipment=shipment,
                event_type=ShipmentEvent.EventType.EXPIRED,
                hub=shipment.current_hub,
                actor=None,
                note='Auto-expired: storage period exceeded',
            )

            _notify_expired(shipment)
            expired_count += 1
            logger.info(
                f"Expired shipment PH-{shipment.tracking_code} "
                f"(was {shipment.status}, hub={shipment.current_hub})"
            )

        # 2. CREATED shipments never deposited — expire after grace period
        created_cutoff = now - timedelta(days=CREATED_GRACE_DAYS)
        stale_created = Shipment.objects.filter(
            status=Shipment.Status.CREATED,
            created_at__lt=created_cutoff,
        ).select_related('sender', 'receiver')

        for shipment in stale_created:
            shipment.status = Shipment.Status.EXPIRED
            shipment.save(update_fields=['status', 'updated_at'])

            ShipmentEvent.objects.create(
                shipment=shipment,
                event_type=ShipmentEvent.EventType.EXPIRED,
                actor=None,
                note=f'Auto-expired: not deposited within {CREATED_GRACE_DAYS} days',
            )

            _notify_expired(shipment)
            expired_count += 1
            logger.info(
                f"Expired stale CREATED shipment PH-{shipment.tracking_code} "
                f"(created {shipment.created_at.date()})"
            )

        self.stdout.write(f"expire_shipments: expired={expired_count}")


def _notify_expired(shipment):
    """Send WebSocket notification to sender, receiver, and hub operators about expiry."""
    try:
        from parahub.services.ws_publish import ws_publish
        data = {
            'id': shipment.id,
            'tracking_code': f"PH-{shipment.tracking_code}",
            'status': Shipment.Status.EXPIRED,
            'title': shipment.title,
        }
        notified_ids = set()
        for profile in (shipment.sender, shipment.receiver):
            ws_publish(f'user:{profile.account_id}', {
                'type': 'shipment.expired',
                'data': data,
            })
            notified_ids.add(profile.account_id)

        # Notify hub operators at current_hub
        if shipment.current_hub_id:
            from geo.models import EstablishmentMembership
            operator_account_ids = set(
                EstablishmentMembership.objects.filter(
                    establishment_id=shipment.current_hub_id,
                    role__in=['OWNER', 'ADMIN', 'MEMBER'],
                ).values_list('profile__account_id', flat=True)
            )
            operator_account_ids.add(shipment.current_hub.owner.account_id)
            for account_id in operator_account_ids - notified_ids:
                ws_publish(f'user:{account_id}', {
                    'type': 'shipment.expired',
                    'data': data,
                })
    except Exception as e:
        logger.warning(f"Failed to notify shipment expiry: {e}")
