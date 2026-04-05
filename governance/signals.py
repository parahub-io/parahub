"""
Django signals for governance app.

Push notifications for governance events:
- Poll activated -> notify eligible voters
- Delegation created -> notify delegate
"""

import logging
from threading import Thread

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='governance.Poll')
def notify_eligible_voters_on_poll_active(sender, instance, created, **kwargs):
    """
    When a poll is created with status=ACTIVE, send push notifications
    to all eligible voters except the creator.
    """
    if not created:
        return
    if instance.status != 'active':
        return

    poll_id = instance.id
    creator_id = instance.created_by_id

    def _send():
        try:
            from governance.models import Poll, PollEligibleVoter
            from notifications.services import notify_new_poll

            poll = Poll.objects.select_related('created_by').get(id=poll_id)
            creator_profile = poll.created_by

            eligible = PollEligibleVoter.objects.filter(
                poll=poll
            ).exclude(
                profile_id=creator_id
            ).select_related('profile__account')

            sent = 0
            for ev in eligible:
                account = ev.profile.account
                if account:
                    notify_new_poll(account, poll, creator_profile)
                    sent += 1

            logger.info(f"[governance] Sent new_poll notifications to {sent} voters for poll {poll_id}")
        except Exception as e:
            logger.error(f"[governance] Failed to send poll notifications for {poll_id}: {e}")

    transaction.on_commit(lambda: Thread(target=_send, daemon=True).start())


@receiver(post_save, sender='governance.PollVoteDelegation')
def notify_delegate_on_delegation(sender, instance, created, **kwargs):
    """
    When a delegation is created/re-activated, notify the delegate
    that someone delegated their vote.
    """
    if not instance.is_active:
        return

    delegation_id = instance.id
    poll_id = instance.poll_id
    delegator_id = instance.delegator_id
    delegate_id = instance.delegate_id

    def _send():
        try:
            from governance.models import Poll
            from identity.models import Profile
            from notifications.services import notify_delegation_received

            poll = Poll.objects.get(id=poll_id)
            delegator = Profile.objects.select_related('account').get(id=delegator_id)
            delegate = Profile.objects.select_related('account').get(id=delegate_id)

            if delegate.account:
                notify_delegation_received(delegate.account, poll, delegator)
                logger.info(f"[governance] Sent delegation_received to {delegate_id} for poll {poll_id}")
        except Exception as e:
            logger.error(f"[governance] Failed to send delegation notification {delegation_id}: {e}")

    transaction.on_commit(lambda: Thread(target=_send, daemon=True).start())
