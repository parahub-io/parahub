"""
Tests for the recurring-support and donation money paths.

Invariants that must never break (non-custodial: these records ARE the
platform's financial memory — no ledger sits behind them):
- start_or_renew is idempotent on ln_payment_hash (a client retry must not
  double-extend a paid period)
- a live renewal keeps its unused days; a lapsed one restarts from now
- cancel keeps access until the paid period ends
- the lifecycle command lapses/cancels exactly once and reminds once per cycle
- donations: is_supporter flips only on COMPLETED; SKIPPED stays out of
  history and totals; transparency counts COMPLETED only
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.utils import timezone
from ninja.errors import HttpError

from core.models import Instance
from finance import services
from finance.models import Donation, Payment, Subscription
from identity.models import Account, Profile
from parahub.endpoints.income import (
    DonationCreateRequest, my_donations, record_donation, transparency,
)


def _profile(instance, username):
    account = Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='x', instance=instance)
    return Profile.objects.create(
        account=account, instance=instance, local_name=username,
        display_name=username.title(), is_primary=True)


class SubscriptionServiceTests(TestCase):
    def setUp(self):
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.alice = _profile(self.instance, 'alice')
        self.bob = _profile(self.instance, 'bob')

    def test_start_creates_active_cycle_and_payment(self):
        sub, is_new = services.start_or_renew(self.alice, self.bob, 1000, 'hash1')
        self.assertTrue(is_new)
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertAlmostEqual(
            (sub.expires_at - timezone.now()).total_seconds(),
            services.CYCLE.total_seconds(), delta=5)
        payment = Payment.objects.get(ln_payment_hash='hash1')
        self.assertEqual(payment.subscription_id, sub.id)
        self.assertEqual(payment.amount_sats, 1000)
        self.assertEqual(payment.status, Payment.Status.COMPLETED)
        self.assertTrue(services.is_live_subscriber(self.alice, self.bob))

    def test_live_renewal_keeps_unused_days(self):
        sub, _ = services.start_or_renew(self.alice, self.bob, 1000, 'hash1')
        first_expiry = sub.expires_at
        sub, is_new = services.start_or_renew(self.alice, self.bob, 1000, 'hash2')
        self.assertFalse(is_new)
        self.assertEqual(sub.expires_at, first_expiry + services.CYCLE)

    def test_lapsed_renewal_restarts_from_now_and_counts_as_new(self):
        sub, _ = services.start_or_renew(self.alice, self.bob, 1000, 'hash1')
        Subscription.objects.filter(id=sub.id).update(
            status=Subscription.Status.LAPSED,
            expires_at=timezone.now() - timedelta(days=40))
        sub, is_new = services.start_or_renew(self.alice, self.bob, 1000, 'hash2')
        self.assertTrue(is_new)  # revival fires the "new subscriber" notification
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertAlmostEqual(
            (sub.expires_at - timezone.now()).total_seconds(),
            services.CYCLE.total_seconds(), delta=5)

    def test_replayed_payment_hash_does_not_double_extend(self):
        sub, _ = services.start_or_renew(self.alice, self.bob, 1000, 'hash1')
        expiry = sub.expires_at
        sub2, is_new = services.start_or_renew(self.alice, self.bob, 1000, 'hash1')
        self.assertEqual(sub2.id, sub.id)
        self.assertFalse(is_new)
        sub.refresh_from_db()
        self.assertEqual(sub.expires_at, expiry)
        self.assertEqual(Payment.objects.filter(subscription=sub).count(), 1)

    def test_cancel_keeps_access_until_expiry(self):
        sub, _ = services.start_or_renew(self.alice, self.bob, 1000, 'hash1')
        services.cancel(sub)
        sub.refresh_from_db()
        self.assertIsNotNone(sub.cancelled_at)
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertTrue(services.is_live_subscriber(self.alice, self.bob))

    def test_is_live_subscriber_edges(self):
        self.assertFalse(services.is_live_subscriber(None, self.bob))
        self.assertFalse(services.is_live_subscriber(self.alice, None))
        self.assertFalse(services.is_live_subscriber(self.alice, self.alice))
        self.assertFalse(services.is_live_subscriber(self.alice, self.bob))
        sub, _ = services.start_or_renew(self.alice, self.bob, 1000, 'hash1')
        Subscription.objects.filter(id=sub.id).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        self.assertFalse(services.is_live_subscriber(self.alice, self.bob))


class ProcessSubscriptionsCommandTests(TestCase):
    def setUp(self):
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.alice = _profile(self.instance, 'alice')
        self.bob = _profile(self.instance, 'bob')

    def _sub(self, **overrides):
        defaults = dict(
            subscriber=self.alice, recipient=self.bob, amount_sats=1000,
            status=Subscription.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(days=10))
        defaults.update(overrides)
        return Subscription.objects.create(**defaults)

    def test_expired_active_lapses(self):
        sub = self._sub(expires_at=timezone.now() - timedelta(hours=1))
        call_command('process_subscriptions')
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.LAPSED)

    def test_expired_cancelled_finalizes_as_cancelled(self):
        sub = self._sub(expires_at=timezone.now() - timedelta(hours=1),
                        cancelled_at=timezone.now() - timedelta(days=5))
        call_command('process_subscriptions')
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CANCELLED)

    @patch('notifications.services.notify_subscription_expiring')
    def test_reminder_fires_once_per_cycle(self, notify):
        sub = self._sub(expires_at=timezone.now() + timedelta(days=2))
        call_command('process_subscriptions')
        self.assertEqual(notify.call_count, 1)
        sub.refresh_from_db()
        self.assertIsNotNone(sub.last_reminder_at)
        call_command('process_subscriptions')  # same cycle → no second ping
        self.assertEqual(notify.call_count, 1)

    @patch('notifications.services.notify_subscription_expiring')
    def test_cancelled_subscriber_not_reminded(self, notify):
        self._sub(expires_at=timezone.now() + timedelta(days=2),
                  cancelled_at=timezone.now())
        call_command('process_subscriptions')
        notify.assert_not_called()

    @patch('notifications.services.notify_subscription_expiring')
    def test_dry_run_writes_nothing(self, notify):
        sub = self._sub(expires_at=timezone.now() - timedelta(hours=1))
        call_command('process_subscriptions', '--dry-run')
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        notify.assert_not_called()


class DonationEndpointTests(TestCase):
    def setUp(self):
        self.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test', public_key='k')
        self.alice = _profile(self.instance, 'alice')
        self.factory = RequestFactory()

    def _request(self):
        request = self.factory.post('/fake/')
        request.auth = self.alice
        request.auth_profile = self.alice
        return request

    def _donation(self, **overrides):
        data = dict(source='WALLET_SEND', source_amount_sats=100_000,
                    donation_amount_sats=100, support_level_at_time=Decimal('0.1'),
                    status='COMPLETED')
        data.update(overrides)
        return DonationCreateRequest(**data)

    def test_completed_donation_marks_supporter(self):
        self.assertFalse(self.alice.is_supporter)
        record_donation(self._request(), self._donation())
        self.alice.refresh_from_db()
        self.assertTrue(self.alice.is_supporter)

    def test_skipped_donation_does_not_mark_supporter(self):
        record_donation(self._request(), self._donation(
            status='SKIPPED', donation_amount_sats=0,
            support_level_at_time=Decimal('0')))
        self.alice.refresh_from_db()
        self.assertFalse(self.alice.is_supporter)

    def test_invalid_status_and_source_rejected(self):
        with self.assertRaises(HttpError):
            record_donation(self._request(), self._donation(status='NONSENSE'))
        with self.assertRaises(HttpError):
            record_donation(self._request(), self._donation(source='NONSENSE'))
        self.assertEqual(Donation.objects.count(), 0)

    def test_my_donations_hides_skipped_and_totals_completed_only(self):
        record_donation(self._request(), self._donation(donation_amount_sats=100))
        record_donation(self._request(), self._donation(
            status='SKIPPED', donation_amount_sats=0))
        record_donation(self._request(), self._donation(
            status='FAILED', donation_amount_sats=50))
        out = my_donations(self._request())
        self.assertEqual(out['total_donated_sats'], 100)
        statuses = {d['status'] for d in out['donations']}
        self.assertNotIn('SKIPPED', statuses)
        self.assertIn('FAILED', statuses)

    def test_transparency_counts_completed_only(self):
        record_donation(self._request(), self._donation(donation_amount_sats=100))
        record_donation(self._request(), self._donation(
            status='FAILED', donation_amount_sats=999))
        out = transparency(self._request())
        self.assertEqual(out['total_donated_sats'], 100)
        self.assertEqual(out['total_donations_count'], 1)
        self.assertEqual(out['supporters_count'], 1)
        self.assertEqual(out['by_source']['WALLET_SEND']['total_sats'], 100)
