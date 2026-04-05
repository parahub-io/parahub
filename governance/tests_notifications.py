"""
Tests for governance notification signals and services.

Tests:
- notify_new_poll sends push to user, skips if prefs disabled
- notify_delegation_received sends push to delegate with correct content
- notify_poll_closing_soon sends push with correct hours_left
- governance_tick _send_warning_notifications sends push to non-voters only
- Signal handlers are wired correctly (registered on correct models)
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from core.models import Instance
from identity.models import Account, Profile
from governance.models import (
    Poll, PollContext, PollOption, PollEligibleVoter,
    PollVote,
)


def _create_instance():
    return Instance.objects.create(
        domain='test.parahub.io',
        name='Test Instance',
        public_key='test-key',
    )


def _create_account(instance, username='alice'):
    return Account.objects.create_user(
        username=username,
        email=f'{username}@test.parahub.io',
        password='testpass123',
        instance=instance,
    )


def _create_profile(account, instance, local_name=None, **kwargs):
    local_name = local_name or account.username
    return Profile.objects.create(
        account=account,
        instance=instance,
        local_name=local_name,
        display_name=local_name.title(),
        is_primary=True,
        profile_type=Profile.ProfileType.PERSONAL,
        **kwargs,
    )


def _create_poll_with_voters(creator_profile, voter_profiles):
    """Create an active poll with eligible voters. Returns poll."""
    context = PollContext.objects.create(
        context_type='adhoc',
        context_id=creator_profile.id,
        created_by=creator_profile,
    )
    poll = Poll.objects.create(
        context=context,
        title='Test Poll',
        description='Test description',
        poll_type='simple',
        start_time=timezone.now(),
        end_time=timezone.now() + timedelta(days=7),
        status='active',
        created_by=creator_profile,
    )
    PollOption.objects.create(poll=poll, text='Yes', order=0)
    PollOption.objects.create(poll=poll, text='No', order=1)

    PollEligibleVoter.objects.create(
        poll=poll, profile=creator_profile, weight=Decimal('1.0000')
    )
    for vp in voter_profiles:
        PollEligibleVoter.objects.create(
            poll=poll, profile=vp, weight=Decimal('1.0000')
        )
    return poll


class NotifyNewPollTest(TestCase):
    """Test notify_new_poll service function."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice_profile = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob_profile = _create_profile(self.bob_account, self.instance)

    @patch('notifications.services.send_push_notification')
    def test_sends_push_to_voter(self, mock_push):
        """notify_new_poll sends push notification with correct data."""
        poll = _create_poll_with_voters(self.alice_profile, [self.bob_profile])
        from notifications.services import notify_new_poll

        notify_new_poll(self.bob_account, poll, self.alice_profile)

        mock_push.assert_called_once()
        args, kwargs = mock_push.call_args
        self.assertEqual(args[0].id, self.bob_account.id)
        self.assertIn(poll.title, args[2])  # body contains poll title
        self.assertEqual(kwargs['data']['type'], 'new_poll')
        self.assertEqual(kwargs['url'], f'/governance/polls/{poll.id}')

    @patch('notifications.services.send_push_notification')
    def test_respects_governance_prefs_disabled(self, mock_push):
        """User with governance=False should not get notification."""
        self.bob_profile.notification_prefs = {'governance': False}
        self.bob_profile.save(update_fields=['notification_prefs'])

        poll = _create_poll_with_voters(self.alice_profile, [self.bob_profile])
        from notifications.services import notify_new_poll

        result = notify_new_poll(self.bob_account, poll, self.alice_profile)

        self.assertEqual(result, (0, 0))
        mock_push.assert_not_called()


class NotifyDelegationReceivedTest(TestCase):
    """Test notify_delegation_received service function."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice_profile = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob_profile = _create_profile(self.bob_account, self.instance)

    @patch('notifications.services.send_push_notification')
    def test_sends_push_to_delegate(self, mock_push):
        """notify_delegation_received sends push to delegate with correct data."""
        poll = _create_poll_with_voters(self.alice_profile, [self.bob_profile])
        from notifications.services import notify_delegation_received

        notify_delegation_received(self.bob_account, poll, self.alice_profile)

        mock_push.assert_called_once()
        args, kwargs = mock_push.call_args
        self.assertEqual(args[0].id, self.bob_account.id)
        self.assertIn(self.alice_profile.display_name, args[2])  # delegator name in body
        self.assertIn(poll.title, args[2])  # poll title in body
        self.assertEqual(kwargs['data']['type'], 'delegation_received')
        self.assertEqual(kwargs['data']['delegator_id'], self.alice_profile.id)

    @patch('notifications.services.send_push_notification')
    def test_respects_governance_prefs_disabled(self, mock_push):
        """User with governance=False should not get delegation notification."""
        self.bob_profile.notification_prefs = {'governance': False}
        self.bob_profile.save(update_fields=['notification_prefs'])

        poll = _create_poll_with_voters(self.alice_profile, [self.bob_profile])
        from notifications.services import notify_delegation_received

        result = notify_delegation_received(self.bob_account, poll, self.alice_profile)

        self.assertEqual(result, (0, 0))
        mock_push.assert_not_called()


class NotifyPollClosingSoonTest(TestCase):
    """Test notify_poll_closing_soon service function."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice_profile = _create_profile(self.alice_account, self.instance)

    @patch('notifications.services.send_push_notification')
    def test_sends_push_with_hours(self, mock_push):
        """notify_poll_closing_soon includes hours_left in body."""
        poll = _create_poll_with_voters(self.alice_profile, [])
        from notifications.services import notify_poll_closing_soon

        notify_poll_closing_soon(self.alice_account, poll, 12)

        mock_push.assert_called_once()
        args, kwargs = mock_push.call_args
        self.assertIn('12', args[2])  # hours in body
        self.assertIn(poll.title, args[2])
        self.assertEqual(kwargs['data']['type'], 'poll_closing_soon')


class GovernanceTickWarningTest(TestCase):
    """Test _send_warning_notifications from governance_tick command."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice_profile = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob_profile = _create_profile(self.bob_account, self.instance)
        self.charlie_account = _create_account(self.instance, 'charlie')
        self.charlie_profile = _create_profile(self.charlie_account, self.instance)

    @patch('notifications.services.send_push_notification')
    @patch('parahub.services.ws_publish.ws_publish')
    def test_warns_non_voters_only(self, mock_ws, mock_push):
        """_send_warning_notifications sends to voters who haven't voted."""
        poll = _create_poll_with_voters(
            self.alice_profile, [self.bob_profile, self.charlie_profile]
        )
        poll.end_time = timezone.now() + timedelta(hours=23)
        poll.warning_hours = 24
        poll.save(update_fields=['end_time', 'warning_hours'])

        # Alice votes
        option = poll.options.first()
        PollVote.objects.create(
            poll=poll, voter=self.alice_profile, option=option,
            pgp_signature='sig', signed_payload={}, effective_weight=Decimal('1'),
        )

        from governance.management.commands.governance_tick import _send_warning_notifications
        _send_warning_notifications(poll)

        # Bob and Charlie get notifications (not Alice who voted)
        self.assertEqual(mock_push.call_count, 2)
        notified_ids = {c[0][0].id for c in mock_push.call_args_list}
        self.assertIn(self.bob_account.id, notified_ids)
        self.assertIn(self.charlie_account.id, notified_ids)
        self.assertNotIn(self.alice_account.id, notified_ids)

    @patch('notifications.services.send_push_notification')
    @patch('parahub.services.ws_publish.ws_publish')
    def test_warns_respects_prefs(self, mock_ws, mock_push):
        """User with governance=False skips push but still gets WS."""
        self.bob_profile.notification_prefs = {'governance': False}
        self.bob_profile.save(update_fields=['notification_prefs'])

        poll = _create_poll_with_voters(self.alice_profile, [self.bob_profile])
        poll.end_time = timezone.now() + timedelta(hours=23)
        poll.warning_hours = 24
        poll.save(update_fields=['end_time', 'warning_hours'])

        # Alice votes so only bob remains as non-voter
        option = poll.options.first()
        PollVote.objects.create(
            poll=poll, voter=self.alice_profile, option=option,
            pgp_signature='sig', signed_payload={}, effective_weight=Decimal('1'),
        )

        from governance.management.commands.governance_tick import _send_warning_notifications
        _send_warning_notifications(poll)

        # WS sent to bob (governance_tick sends WS regardless of prefs)
        self.assertEqual(mock_ws.call_count, 1)
        # Push skipped due to prefs
        mock_push.assert_not_called()


class SignalRegistrationTest(TestCase):
    """Test that governance signals are registered correctly."""

    def test_signals_module_loads(self):
        """governance.signals can be imported without error."""
        import governance.signals  # noqa: F401

    def test_poll_signal_registered(self):
        """post_save on Poll has our notification handler."""
        from django.db.models.signals import post_save
        from governance.models import Poll
        receivers = [r[1]() for r in post_save.receivers if r[1]() is not None]
        handler_names = [getattr(r, '__name__', '') for r in receivers]
        self.assertIn('notify_eligible_voters_on_poll_active', handler_names)

    def test_delegation_signal_registered(self):
        """post_save on PollVoteDelegation has our notification handler."""
        from django.db.models.signals import post_save
        from governance.models import PollVoteDelegation
        receivers = [r[1]() for r in post_save.receivers if r[1]() is not None]
        handler_names = [getattr(r, '__name__', '') for r in receivers]
        self.assertIn('notify_delegate_on_delegation', handler_names)
