"""
governance_tick — периодическая задача для governance:
  1. DRAFT → ACTIVE  (start_time <= now)
  2. ACTIVE → ENDED  (end_time <= now) + finalize Merkle
  3. Предупреждения неголосовавшим за warning_hours до конца

Запускать каждые 15-60 минут через systemd timer.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import logging

from governance.models import Poll, PollEligibleVoter, PollVote
from governance.services import AuditService

logger = logging.getLogger(__name__)


def _send_warning_notifications(poll):
    """Send WebSocket + push notifications to eligible voters who haven't voted."""
    try:
        from parahub.services.ws_publish import ws_publish
        from notifications.services import notify_poll_closing_soon

        voted_profile_ids = set(
            PollVote.objects.filter(poll=poll).values_list('voter_id', flat=True)
        )

        not_voted = PollEligibleVoter.objects.filter(
            poll=poll
        ).exclude(profile_id__in=voted_profile_ids).select_related('profile__account')

        poll_data = {
            'id': poll.id,
            'title': poll.title,
            'end_time': poll.end_time.isoformat() if poll.end_time else None,
            'warning_hours': poll.warning_hours,
        }
        payload = {'type': 'poll.vote_reminder', 'poll': poll_data}

        hours_left = int((poll.end_time - timezone.now()).total_seconds() / 3600)

        sent = 0
        for ev in not_voted:
            account = ev.profile.account
            if account:
                ws_publish(f"user:{account.id}", payload)
                notify_poll_closing_soon(account, poll, hours_left)
                sent += 1

        logger.info(f"Poll {poll.id[:8]}: sent {sent} vote reminders ({poll.warning_hours}h warning)")
    except Exception as e:
        logger.error(f"Failed to send warnings for poll {poll.id[:8]}: {e}")


class Command(BaseCommand):
    help = "Governance periodic tick: auto-transitions + vote reminders"

    def handle(self, *args, **options):
        now = timezone.now()

        # 1. DRAFT → ACTIVE
        activated = Poll.objects.filter(
            status=Poll.Status.DRAFT,
            start_time__lte=now,
        ).update(status=Poll.Status.ACTIVE)
        if activated:
            logger.info(f"governance_tick: activated {activated} polls")

        # 2. ACTIVE → ENDED + finalize Merkle
        to_end = list(Poll.objects.filter(
            status=Poll.Status.ACTIVE,
            end_time__isnull=False,
            end_time__lt=now,
        ))
        for poll in to_end:
            Poll.objects.filter(id=poll.id).update(status=Poll.Status.ENDED)
            poll.refresh_from_db()
            AuditService.finalize_poll(poll)
            logger.info(f"governance_tick: ended poll {poll.id[:8]} '{poll.title}'")

        # 3. Предупреждения за warning_hours
        # Находим активные голосования у которых end_time через [warning_hours - 1h, warning_hours + 1h]
        # (окно ±1h чтобы не пропустить при запуске каждые 30 мин)
        # Opinion polls have no eligible voters, so the reminder pass skips them naturally.
        warned = 0
        active_with_end = Poll.objects.filter(
            status=Poll.Status.ACTIVE,
            end_time__isnull=False,
        ).exclude(warning_hours=0)

        for poll in active_with_end:
            time_left = poll.end_time - now
            warning_window = timedelta(hours=poll.warning_hours)
            # Попадает ли в окно [warning_hours - 1h, warning_hours]
            if timedelta(hours=poll.warning_hours - 1) <= time_left <= warning_window:
                _send_warning_notifications(poll)
                warned += 1

        # 4. Opinion polls: aggregate-and-purge raw pseudonymous votes 30 days after end
        # (data minimization — PK/civic-polls-system.md; frozen_results keeps the aggregates)
        purged = 0
        from governance import civic
        purge_before = now - timedelta(days=30)
        purge_candidates = Poll.objects.filter(
            poll_class=Poll.PollClass.OPINION,
            status=Poll.Status.ENDED,
            end_time__isnull=False,
            end_time__lt=purge_before,
            frozen_results__isnull=True,
        )
        for poll in purge_candidates:
            try:
                if civic.freeze_and_purge(poll):
                    purged += 1
            except Exception as e:
                logger.error(f"governance_tick: freeze_and_purge failed for {poll.id[:8]}: {e}")

        self.stdout.write(
            f"governance_tick: activated={activated}, ended={len(to_end)}, warned={warned}, purged={purged}"
        )
