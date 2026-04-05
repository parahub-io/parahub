"""Check InactivityWatch entries and trigger WARNING alerts when thresholds exceeded."""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Check inactivity monitors and send alerts when thresholds exceeded'

    def handle(self, *args, **options):
        from parasos.models import InactivityWatch, SOSAlert
        from notifications.services import send_push_notification
        from parahub.services.ws_publish import ws_publish

        now = timezone.now()
        current_hour = now.hour

        watches = InactivityWatch.objects.filter(
            is_active=True,
            last_activity_at__isnull=False,
        ).select_related('group', 'watched_profile', 'watched_profile__account')

        alerts_sent = 0
        for watch in watches:
            # Skip if outside check hours
            if watch.check_start_hour <= watch.check_end_hour:
                if current_hour < watch.check_start_hour or current_hour >= watch.check_end_hour:
                    continue
            else:
                # Wraps midnight (e.g. 22-8)
                if watch.check_end_hour <= current_hour < watch.check_start_hour:
                    continue

            # Check inactivity threshold
            inactive_hours = (now - watch.last_activity_at).total_seconds() / 3600
            if inactive_hours < watch.max_inactivity_hours:
                continue

            # Avoid alert spam: don't re-alert within double the threshold
            if watch.last_alert_at:
                min_interval = timedelta(hours=watch.max_inactivity_hours * 2)
                if now - watch.last_alert_at < min_interval:
                    continue

            # Create WARNING alert in the group
            watched_name = watch.watched_profile.display_name or watch.watched_profile.hna or "Someone"
            hours_ago = int(inactive_hours)

            alert = SOSAlert.objects.create(
                group=watch.group,
                sender=watch.watched_profile,
                level='WARNING',
                category='MEDICAL',
                message=f"No activity detected for {watched_name} in the last {hours_ago} hours",
                source='HA_AUTOMATION',
            )

            watch.last_alert_at = now
            watch.save(update_fields=['last_alert_at'])

            # Notify watchers via push
            for watcher in watch.watchers.select_related('account').all():
                try:
                    send_push_notification(
                        watcher.account,
                        f"ParaSOS: {watch.group.name}",
                        f"No activity from {watched_name} for {hours_ago}h",
                        data={
                            'type': 'inactivity_alert',
                            'alert_id': alert.id,
                            'group_id': watch.group_id,
                            'requireInteraction': True,
                        },
                        url=f"/parasos/{watch.group_id}",
                    )
                except Exception:
                    pass

            # WS broadcast
            ws_publish(f"parasos:{watch.group_id}", {
                "type": "sos.new",
                "alert": {
                    "id": alert.id,
                    "level": "WARNING",
                    "category": "MEDICAL",
                    "message": alert.message,
                    "status": "ACTIVE",
                    "sender_id": watch.watched_profile_id,
                    "sender_display_name": watched_name,
                    "created_at": alert.created_at.isoformat(),
                },
            })

            alerts_sent += 1
            self.stdout.write(f'  Alert sent for {watched_name} in {watch.group.name}')

        if alerts_sent:
            self.stdout.write(self.style.SUCCESS(f'Sent {alerts_sent} inactivity alerts'))
        else:
            self.stdout.write('No inactivity thresholds exceeded')
