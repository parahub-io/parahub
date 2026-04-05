"""
Tests for debts endpoints: create, list, detail, confirm, repay, repayments.

Tests invariants that must never break:
- Auth required for all endpoints
- Creator logic: debtor creates → ACTIVE, creditor creates → PENDING
- Confirm/reject permissions (only the non-creator party)
- Repayment only by creditor
- Amount validation (positive, not exceeding remaining)
- Access control (only creditor/debtor can view)
- Status transitions (PENDING → ACTIVE → PARTIALLY_SETTLED → FULLY_SETTLED)
- Cancellation via reject
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, SimpleTestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from ninja.errors import HttpError

from identity.models import Account, Profile
from core.models import Instance
from debts.models import Debt, DebtRepayment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_instance():
    return Instance.objects.create(
        domain='test.parahub.io',
        name='Test Instance',
        public_key='test-key',
    )


def _create_account(instance, username='alice', **kwargs):
    return Account.objects.create_user(
        username=username,
        email=f'{username}@test.parahub.io',
        password='testpass123',
        instance=instance,
        **kwargs,
    )


def _create_profile(account, instance, local_name=None, **kwargs):
    local_name = local_name or account.username
    return Profile.objects.create(
        account=account,
        instance=instance,
        local_name=local_name,
        display_name=local_name.title(),
        is_primary=True,
        profile_type=kwargs.pop('profile_type', Profile.ProfileType.PERSONAL),
        **kwargs,
    )


def _make_auth_request(factory, account, profile, method='get', path='/fake/', data=None):
    """Build a request with auth_profile and session attached (mimics ProfileAuth)."""
    fn = getattr(factory, method)
    if data:
        request = fn(path, data=data, content_type='application/json')
    else:
        request = fn(path)
    request.user = account
    request.auth = profile
    request.auth_profile = profile
    request.session = SessionStore()
    request.session.create()
    return request


def _create_debt(creditor, debtor, amount=Decimal('1000.00'), currency='EUR',
                 status=Debt.Status.ACTIVE, created_by=None, **kwargs):
    """Create a Debt directly in DB."""
    return Debt.objects.create(
        creditor=creditor,
        debtor=debtor,
        amount=amount,
        remaining_amount=amount,
        currency=currency,
        status=status,
        created_by=created_by or debtor,
        **kwargs,
    )


# ===========================================================================
# Model-level tests (SimpleTestCase — no DB)
# ===========================================================================

class DebtModelLogicTest(SimpleTestCase):
    """Test Debt model methods without DB."""

    def test_status_choices(self):
        self.assertEqual(Debt.Status.DRAFT, 'DRAFT')
        self.assertEqual(Debt.Status.PENDING_CONFIRMATION, 'PENDING_CONFIRMATION')
        self.assertEqual(Debt.Status.ACTIVE, 'ACTIVE')
        self.assertEqual(Debt.Status.PARTIALLY_SETTLED, 'PARTIALLY_SETTLED')
        self.assertEqual(Debt.Status.FULLY_SETTLED, 'FULLY_SETTLED')
        self.assertEqual(Debt.Status.CANCELLED, 'CANCELLED')

    def test_repayment_type_choices(self):
        self.assertEqual(DebtRepayment.RepaymentType.MANUAL, 'MANUAL')
        self.assertEqual(DebtRepayment.RepaymentType.CYCLE_CLEARING, 'CYCLE_CLEARING')

    def test_is_active_property(self):
        debt = Debt()
        debt.status = Debt.Status.ACTIVE
        debt.remaining_amount = Decimal('100')
        self.assertTrue(debt.is_active)

        debt.status = Debt.Status.PARTIALLY_SETTLED
        self.assertTrue(debt.is_active)

        debt.status = Debt.Status.FULLY_SETTLED
        self.assertFalse(debt.is_active)

        debt.status = Debt.Status.CANCELLED
        self.assertFalse(debt.is_active)

        debt.status = Debt.Status.PENDING_CONFIRMATION
        self.assertFalse(debt.is_active)

        # Active status but zero remaining
        debt.status = Debt.Status.ACTIVE
        debt.remaining_amount = Decimal('0')
        self.assertFalse(debt.is_active)

    def test_percent_settled_property(self):
        debt = Debt()
        debt.amount = Decimal('1000')
        debt.remaining_amount = Decimal('1000')
        self.assertEqual(debt.percent_settled, Decimal('0.0'))

        debt.remaining_amount = Decimal('500')
        self.assertEqual(debt.percent_settled, Decimal('50.0'))

        debt.remaining_amount = Decimal('0')
        self.assertEqual(debt.percent_settled, Decimal('100.0'))

    def test_percent_settled_zero_amount(self):
        debt = Debt()
        debt.amount = Decimal('0')
        debt.remaining_amount = Decimal('0')
        self.assertEqual(debt.percent_settled, Decimal('100.0'))


# ===========================================================================
# DB-backed tests: Debt Creation
# ===========================================================================

@patch('debts.signals.graph_service')
@patch('parahub.services.ws_publish.ws_publish')
@patch('notifications.services.notify_new_debt')
class DebtCreateTest(TestCase):
    """Test debt creation endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance)
        self.factory = RequestFactory()

    def test_debtor_creates_debt_active_immediately(self, mock_notify, mock_ws, mock_graph):
        """When debtor creates debt (admits owing), status is ACTIVE immediately."""
        from debts.api import create_debt, DebtCreateRequest

        data = DebtCreateRequest(
            creditor_id=self.alice.id,
            debtor_id=self.bob.id,
            amount=Decimal('500.00'),
            currency='EUR',
        )
        # Bob (debtor) creates the debt
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        response = create_debt(request, data)

        self.assertEqual(response.status, 'ACTIVE')
        self.assertEqual(response.amount, Decimal('500.00'))
        self.assertEqual(response.remaining_amount, Decimal('500.00'))
        self.assertEqual(response.creditor_id, self.alice.id)
        self.assertEqual(response.debtor_id, self.bob.id)
        self.assertEqual(response.currency, 'EUR')
        self.assertEqual(response.object_type, 'debt')
        self.assertIsNotNone(response.confirmed_by_debtor_at)

    def test_creditor_creates_debt_pending(self, mock_notify, mock_ws, mock_graph):
        """When creditor creates debt, status is PENDING_CONFIRMATION."""
        from debts.api import create_debt, DebtCreateRequest

        data = DebtCreateRequest(
            creditor_id=self.alice.id,
            debtor_id=self.bob.id,
            amount=Decimal('1000.00'),
            currency='USD',
        )
        # Alice (creditor) creates the debt
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        response = create_debt(request, data)

        self.assertEqual(response.status, 'PENDING_CONFIRMATION')
        self.assertIsNotNone(response.confirmed_by_creditor_at)
        self.assertIsNone(response.confirmed_by_debtor_at)

    def test_create_debt_with_description(self, mock_notify, mock_ws, mock_graph):
        """Debt creation with description."""
        from debts.api import create_debt, DebtCreateRequest

        data = DebtCreateRequest(
            creditor_id=self.alice.id,
            debtor_id=self.bob.id,
            amount=Decimal('250.00'),
            description='Loan for bicycle repair',
        )
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        response = create_debt(request, data)

        self.assertEqual(response.description, 'Loan for bicycle repair')

    def test_create_debt_invalid_amount_zero(self, mock_notify, mock_ws, mock_graph):
        """Amount must be positive."""
        from debts.api import create_debt, DebtCreateRequest

        data = DebtCreateRequest(
            creditor_id=self.alice.id,
            debtor_id=self.bob.id,
            amount=Decimal('0'),
        )
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_debt(request, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_debt_invalid_amount_negative(self, mock_notify, mock_ws, mock_graph):
        """Negative amount rejected."""
        from debts.api import create_debt, DebtCreateRequest

        data = DebtCreateRequest(
            creditor_id=self.alice.id,
            debtor_id=self.bob.id,
            amount=Decimal('-100'),
        )
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_debt(request, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_debt_nonexistent_profile(self, mock_notify, mock_ws, mock_graph):
        """Creating debt with nonexistent profile returns 404."""
        from debts.api import create_debt, DebtCreateRequest

        data = DebtCreateRequest(
            creditor_id='01NONEXISTENT000000000000',
            debtor_id=self.bob.id,
            amount=Decimal('100'),
        )
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_debt(request, data)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_create_debt_default_currency(self, mock_notify, mock_ws, mock_graph):
        """Default currency is EUR."""
        from debts.api import create_debt, DebtCreateRequest

        data = DebtCreateRequest(
            creditor_id=self.alice.id,
            debtor_id=self.bob.id,
            amount=Decimal('100'),
        )
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        response = create_debt(request, data)
        self.assertEqual(response.currency, 'EUR')

    def test_create_debt_created_by_set(self, mock_notify, mock_ws, mock_graph):
        """created_by_id is set to the creator's profile."""
        from debts.api import create_debt, DebtCreateRequest

        data = DebtCreateRequest(
            creditor_id=self.alice.id,
            debtor_id=self.bob.id,
            amount=Decimal('100'),
        )
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        response = create_debt(request, data)
        self.assertEqual(response.created_by_id, self.bob.id)

    def test_create_debt_percent_settled_zero(self, mock_notify, mock_ws, mock_graph):
        """New debt starts at 0% settled."""
        from debts.api import create_debt, DebtCreateRequest

        data = DebtCreateRequest(
            creditor_id=self.alice.id,
            debtor_id=self.bob.id,
            amount=Decimal('100'),
        )
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        response = create_debt(request, data)
        self.assertEqual(response.percent_settled, Decimal('0'))


# ===========================================================================
# DB-backed tests: Debt Listing
# ===========================================================================

@patch('debts.signals.graph_service')
@patch('parahub.services.ws_publish.ws_publish')
@patch('notifications.services.notify_new_debt')
class DebtListTest(TestCase):
    """Test debt listing endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance)
        self.carl_account = _create_account(self.instance, 'carl')
        self.carl = _create_profile(self.carl_account, self.instance)
        self.factory = RequestFactory()

    def test_list_debts_empty(self, mock_notify, mock_ws, mock_graph):
        """List returns empty when no debts exist."""
        from debts.api import list_debts

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = list_debts(request, mine_only=True)
        self.assertEqual(len(result), 0)

    def test_list_debts_mine_only(self, mock_notify, mock_ws, mock_graph):
        """mine_only=True returns only debts involving the requester."""
        from debts.api import list_debts

        _create_debt(self.alice, self.bob, Decimal('100'))  # Alice-Bob
        _create_debt(self.carl, self.bob, Decimal('200'))   # Carl-Bob
        _create_debt(self.alice, self.carl, Decimal('300'))  # Alice-Carl

        # Alice sees debts where she's creditor or debtor (2 debts)
        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = list_debts(request, mine_only=True)
        self.assertEqual(len(result), 2)

        # Bob sees 2 debts (both as debtor)
        request = _make_auth_request(self.factory, self.bob_account, self.bob)
        result = list_debts(request, mine_only=True)
        self.assertEqual(len(result), 2)

    def test_list_debts_all(self, mock_notify, mock_ws, mock_graph):
        """mine_only=False returns all debts."""
        from debts.api import list_debts

        _create_debt(self.alice, self.bob, Decimal('100'))
        _create_debt(self.carl, self.bob, Decimal('200'))

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = list_debts(request, mine_only=False)
        self.assertEqual(len(result), 2)

    def test_list_debts_filter_by_status(self, mock_notify, mock_ws, mock_graph):
        """Filter debts by status."""
        from debts.api import list_debts

        _create_debt(self.alice, self.bob, Decimal('100'), status=Debt.Status.ACTIVE)
        _create_debt(self.alice, self.bob, Decimal('200'), status=Debt.Status.PENDING_CONFIRMATION)

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = list_debts(request, status='ACTIVE', mine_only=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, 'ACTIVE')

    def test_list_debts_response_fields(self, mock_notify, mock_ws, mock_graph):
        """Verify all response fields are present."""
        from debts.api import list_debts

        _create_debt(self.alice, self.bob, Decimal('500'), description='Test debt')

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = list_debts(request, mine_only=True)
        self.assertEqual(len(result), 1)
        debt_resp = result[0]
        self.assertEqual(debt_resp.object_type, 'debt')
        self.assertEqual(debt_resp.amount, Decimal('500'))
        self.assertEqual(debt_resp.description, 'Test debt')
        self.assertIsNotNone(debt_resp.created_at)

    def test_list_debts_ordered_by_created_at_desc(self, mock_notify, mock_ws, mock_graph):
        """Debts are ordered newest first."""
        from debts.api import list_debts

        d1 = _create_debt(self.alice, self.bob, Decimal('100'))
        d2 = _create_debt(self.alice, self.bob, Decimal('200'))

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = list_debts(request, mine_only=True)
        self.assertEqual(result[0].id, d2.id)
        self.assertEqual(result[1].id, d1.id)

    def test_list_debts_limited_to_100(self, mock_notify, mock_ws, mock_graph):
        """List endpoint caps at 100 results."""
        from debts.api import list_debts

        for i in range(105):
            _create_debt(self.alice, self.bob, Decimal('10'))

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = list_debts(request, mine_only=True)
        self.assertEqual(len(result), 100)


# ===========================================================================
# DB-backed tests: Debt Detail
# ===========================================================================

@patch('debts.signals.graph_service')
@patch('parahub.services.ws_publish.ws_publish')
@patch('notifications.services.notify_new_debt')
class DebtDetailTest(TestCase):
    """Test debt detail endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance)
        self.carl_account = _create_account(self.instance, 'carl')
        self.carl = _create_profile(self.carl_account, self.instance)
        self.factory = RequestFactory()

    def test_get_debt_as_creditor(self, mock_notify, mock_ws, mock_graph):
        """Creditor can view debt details."""
        from debts.api import get_debt

        debt = _create_debt(self.alice, self.bob, Decimal('500'))

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = get_debt(request, debt.id)
        self.assertEqual(result.id, debt.id)
        self.assertEqual(result.amount, Decimal('500'))

    def test_get_debt_as_debtor(self, mock_notify, mock_ws, mock_graph):
        """Debtor can view debt details."""
        from debts.api import get_debt

        debt = _create_debt(self.alice, self.bob, Decimal('500'))

        request = _make_auth_request(self.factory, self.bob_account, self.bob)
        result = get_debt(request, debt.id)
        self.assertEqual(result.id, debt.id)

    def test_get_debt_as_third_party_forbidden(self, mock_notify, mock_ws, mock_graph):
        """Third party cannot view debt."""
        from debts.api import get_debt

        debt = _create_debt(self.alice, self.bob, Decimal('500'))

        request = _make_auth_request(self.factory, self.carl_account, self.carl)
        with self.assertRaises(HttpError) as ctx:
            get_debt(request, debt.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_get_debt_not_found(self, mock_notify, mock_ws, mock_graph):
        """Nonexistent debt returns 404."""
        from debts.api import get_debt

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        with self.assertRaises(HttpError) as ctx:
            get_debt(request, '01NONEXISTENT000000000000')
        self.assertEqual(ctx.exception.status_code, 404)


# ===========================================================================
# DB-backed tests: Debt Confirmation
# ===========================================================================

@patch('debts.signals.graph_service')
@patch('parahub.services.ws_publish.ws_publish')
@patch('notifications.services.notify_new_debt')
class DebtConfirmTest(TestCase):
    """Test debt confirmation and rejection."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance)
        self.carl_account = _create_account(self.instance, 'carl')
        self.carl = _create_profile(self.carl_account, self.instance)
        self.factory = RequestFactory()

    def test_debtor_confirms_pending_debt(self, mock_notify, mock_ws, mock_graph):
        """Debtor confirms a PENDING debt created by creditor → ACTIVE."""
        from debts.api import confirm_debt, ConfirmDebtRequest
        from django.utils import timezone

        debt = _create_debt(
            self.alice, self.bob, Decimal('1000'),
            status=Debt.Status.PENDING_CONFIRMATION,
            created_by=self.alice,
            confirmed_by_creditor_at=timezone.now(),
        )

        data = ConfirmDebtRequest(confirmed=True)
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        result = confirm_debt(request, debt.id, data)

        self.assertEqual(result.status, 'ACTIVE')
        self.assertIsNotNone(result.confirmed_by_debtor_at)
        self.assertIsNotNone(result.confirmed_by_creditor_at)

    def test_creditor_confirms_debt_created_by_debtor(self, mock_notify, mock_ws, mock_graph):
        """Creditor confirms a debt that debtor created (already ACTIVE, but creditor adds confirmation)."""
        from debts.api import confirm_debt, ConfirmDebtRequest
        from django.utils import timezone

        debt = _create_debt(
            self.alice, self.bob, Decimal('500'),
            status=Debt.Status.ACTIVE,
            created_by=self.bob,
            confirmed_by_debtor_at=timezone.now(),
        )

        data = ConfirmDebtRequest(confirmed=True)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = confirm_debt(request, debt.id, data)

        self.assertEqual(result.status, 'ACTIVE')
        self.assertIsNotNone(result.confirmed_by_creditor_at)

    def test_debtor_rejects_pending_debt(self, mock_notify, mock_ws, mock_graph):
        """Debtor rejects a PENDING debt → CANCELLED."""
        from debts.api import confirm_debt, ConfirmDebtRequest
        from django.utils import timezone

        debt = _create_debt(
            self.alice, self.bob, Decimal('1000'),
            status=Debt.Status.PENDING_CONFIRMATION,
            created_by=self.alice,
            confirmed_by_creditor_at=timezone.now(),
        )

        data = ConfirmDebtRequest(confirmed=False)
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        result = confirm_debt(request, debt.id, data)

        self.assertEqual(result.status, 'CANCELLED')

    def test_creditor_rejects_debt(self, mock_notify, mock_ws, mock_graph):
        """Creditor can also reject → CANCELLED."""
        from debts.api import confirm_debt, ConfirmDebtRequest

        debt = _create_debt(
            self.alice, self.bob, Decimal('500'),
            status=Debt.Status.ACTIVE,
            created_by=self.bob,
        )

        data = ConfirmDebtRequest(confirmed=False)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = confirm_debt(request, debt.id, data)

        self.assertEqual(result.status, 'CANCELLED')

    def test_third_party_cannot_confirm(self, mock_notify, mock_ws, mock_graph):
        """Third party cannot confirm/reject a debt."""
        from debts.api import confirm_debt, ConfirmDebtRequest

        debt = _create_debt(
            self.alice, self.bob, Decimal('500'),
            status=Debt.Status.PENDING_CONFIRMATION,
        )

        data = ConfirmDebtRequest(confirmed=True)
        request = _make_auth_request(self.factory, self.carl_account, self.carl, 'post')
        with self.assertRaises(HttpError) as ctx:
            confirm_debt(request, debt.id, data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_confirm_nonexistent_debt(self, mock_notify, mock_ws, mock_graph):
        """Confirming nonexistent debt returns 404."""
        from debts.api import confirm_debt, ConfirmDebtRequest

        data = ConfirmDebtRequest(confirmed=True)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        with self.assertRaises(HttpError) as ctx:
            confirm_debt(request, '01NONEXISTENT000000000000', data)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_double_confirm_is_idempotent(self, mock_notify, mock_ws, mock_graph):
        """Confirming twice doesn't change the already-set timestamp."""
        from debts.api import confirm_debt, ConfirmDebtRequest
        from django.utils import timezone

        debt = _create_debt(
            self.alice, self.bob, Decimal('500'),
            status=Debt.Status.PENDING_CONFIRMATION,
            created_by=self.alice,
            confirmed_by_creditor_at=timezone.now(),
        )

        data = ConfirmDebtRequest(confirmed=True)
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        result1 = confirm_debt(request, debt.id, data)
        first_ts = result1.confirmed_by_debtor_at

        # Confirm again
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        result2 = confirm_debt(request, debt.id, data)
        self.assertEqual(result2.confirmed_by_debtor_at, first_ts)


# ===========================================================================
# DB-backed tests: Repayment
# ===========================================================================

@patch('debts.signals.graph_service')
@patch('parahub.services.ws_publish.ws_publish')
@patch('notifications.services.notify_new_debt')
class DebtRepaymentCreateTest(TestCase):
    """Test repayment creation endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)  # creditor
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance)  # debtor
        self.carl_account = _create_account(self.instance, 'carl')
        self.carl = _create_profile(self.carl_account, self.instance)
        self.factory = RequestFactory()

    def test_creditor_creates_partial_repayment(self, mock_notify, mock_ws, mock_graph):
        """Creditor records partial repayment → remaining decreases."""
        from debts.api import create_repayment, RepayDebtRequest

        debt = _create_debt(self.alice, self.bob, Decimal('1000'))
        data = RepayDebtRequest(amount=Decimal('300'), notes='Cash payment')
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = create_repayment(request, debt.id, data)

        self.assertEqual(result.amount, Decimal('300'))
        self.assertEqual(result.repayment_type, 'MANUAL')
        self.assertEqual(result.notes, 'Cash payment')
        self.assertEqual(result.object_type, 'debt_repayment')
        self.assertEqual(result.debt_id, debt.id)
        self.assertEqual(result.created_by_id, self.alice.id)

        # Verify debt updated
        debt.refresh_from_db()
        self.assertEqual(debt.remaining_amount, Decimal('700'))
        self.assertEqual(debt.status, Debt.Status.PARTIALLY_SETTLED)

    def test_creditor_creates_full_repayment(self, mock_notify, mock_ws, mock_graph):
        """Full repayment → debt becomes FULLY_SETTLED."""
        from debts.api import create_repayment, RepayDebtRequest

        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        data = RepayDebtRequest(amount=Decimal('500'))
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        create_repayment(request, debt.id, data)

        debt.refresh_from_db()
        self.assertEqual(debt.remaining_amount, Decimal('0'))
        self.assertEqual(debt.status, Debt.Status.FULLY_SETTLED)

    def test_debtor_cannot_create_repayment(self, mock_notify, mock_ws, mock_graph):
        """Only creditor can record repayment."""
        from debts.api import create_repayment, RepayDebtRequest

        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        data = RepayDebtRequest(amount=Decimal('100'))
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_repayment(request, debt.id, data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_third_party_cannot_create_repayment(self, mock_notify, mock_ws, mock_graph):
        """Third party cannot record repayment."""
        from debts.api import create_repayment, RepayDebtRequest

        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        data = RepayDebtRequest(amount=Decimal('100'))
        request = _make_auth_request(self.factory, self.carl_account, self.carl, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_repayment(request, debt.id, data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_repayment_exceeds_remaining(self, mock_notify, mock_ws, mock_graph):
        """Repayment amount exceeding remaining is rejected."""
        from debts.api import create_repayment, RepayDebtRequest

        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        data = RepayDebtRequest(amount=Decimal('600'))
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_repayment(request, debt.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_repayment_zero_amount(self, mock_notify, mock_ws, mock_graph):
        """Zero repayment is rejected."""
        from debts.api import create_repayment, RepayDebtRequest

        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        data = RepayDebtRequest(amount=Decimal('0'))
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_repayment(request, debt.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_repayment_negative_amount(self, mock_notify, mock_ws, mock_graph):
        """Negative repayment is rejected."""
        from debts.api import create_repayment, RepayDebtRequest

        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        data = RepayDebtRequest(amount=Decimal('-50'))
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_repayment(request, debt.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_repayment_on_nonexistent_debt(self, mock_notify, mock_ws, mock_graph):
        """Repayment on nonexistent debt returns 404."""
        from debts.api import create_repayment, RepayDebtRequest

        data = RepayDebtRequest(amount=Decimal('100'))
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_repayment(request, '01NONEXISTENT000000000000', data)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_multiple_partial_repayments(self, mock_notify, mock_ws, mock_graph):
        """Multiple partial repayments reduce remaining correctly."""
        from debts.api import create_repayment, RepayDebtRequest

        debt = _create_debt(self.alice, self.bob, Decimal('1000'))

        # First repayment: 300
        data = RepayDebtRequest(amount=Decimal('300'))
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        create_repayment(request, debt.id, data)

        debt.refresh_from_db()
        self.assertEqual(debt.remaining_amount, Decimal('700'))
        self.assertEqual(debt.status, Debt.Status.PARTIALLY_SETTLED)

        # Second repayment: 700 (fully settle)
        data = RepayDebtRequest(amount=Decimal('700'))
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        create_repayment(request, debt.id, data)

        debt.refresh_from_db()
        self.assertEqual(debt.remaining_amount, Decimal('0'))
        self.assertEqual(debt.status, Debt.Status.FULLY_SETTLED)

    def test_repayment_notes_optional(self, mock_notify, mock_ws, mock_graph):
        """Notes are optional in repayment."""
        from debts.api import create_repayment, RepayDebtRequest

        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        data = RepayDebtRequest(amount=Decimal('100'))
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = create_repayment(request, debt.id, data)
        self.assertEqual(result.notes, '')


# ===========================================================================
# DB-backed tests: List Repayments
# ===========================================================================

@patch('debts.signals.graph_service')
@patch('parahub.services.ws_publish.ws_publish')
@patch('notifications.services.notify_new_debt')
class DebtRepaymentListTest(TestCase):
    """Test repayment listing endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance)
        self.carl_account = _create_account(self.instance, 'carl')
        self.carl = _create_profile(self.carl_account, self.instance)
        self.factory = RequestFactory()

    def test_list_repayments_empty(self, mock_notify, mock_ws, mock_graph):
        """No repayments returns empty list."""
        from debts.api import list_debt_repayments

        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = list_debt_repayments(request, debt.id)
        self.assertEqual(len(result), 0)

    def test_list_repayments_creditor(self, mock_notify, mock_ws, mock_graph):
        """Creditor can list repayments."""
        from debts.api import list_debt_repayments

        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        DebtRepayment.objects.create(
            debt=debt,
            amount=Decimal('100'),
            repayment_type=DebtRepayment.RepaymentType.MANUAL,
            created_by=self.alice,
        )
        DebtRepayment.objects.create(
            debt=debt,
            amount=Decimal('200'),
            repayment_type=DebtRepayment.RepaymentType.MANUAL,
            created_by=self.alice,
        )

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = list_debt_repayments(request, debt.id)
        self.assertEqual(len(result), 2)

    def test_list_repayments_debtor(self, mock_notify, mock_ws, mock_graph):
        """Debtor can list repayments too."""
        from debts.api import list_debt_repayments

        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        DebtRepayment.objects.create(
            debt=debt,
            amount=Decimal('100'),
            repayment_type=DebtRepayment.RepaymentType.MANUAL,
            created_by=self.alice,
        )

        request = _make_auth_request(self.factory, self.bob_account, self.bob)
        result = list_debt_repayments(request, debt.id)
        self.assertEqual(len(result), 1)

    def test_list_repayments_third_party_forbidden(self, mock_notify, mock_ws, mock_graph):
        """Third party cannot list repayments."""
        from debts.api import list_debt_repayments

        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        request = _make_auth_request(self.factory, self.carl_account, self.carl)
        with self.assertRaises(HttpError) as ctx:
            list_debt_repayments(request, debt.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_list_repayments_nonexistent_debt(self, mock_notify, mock_ws, mock_graph):
        """List repayments for nonexistent debt returns 404."""
        from debts.api import list_debt_repayments

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        with self.assertRaises(HttpError) as ctx:
            list_debt_repayments(request, '01NONEXISTENT000000000000')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_list_repayments_ordered_newest_first(self, mock_notify, mock_ws, mock_graph):
        """Repayments ordered by created_at descending."""
        from debts.api import list_debt_repayments

        debt = _create_debt(self.alice, self.bob, Decimal('1000'))
        r1 = DebtRepayment.objects.create(
            debt=debt,
            amount=Decimal('100'),
            repayment_type=DebtRepayment.RepaymentType.MANUAL,
            created_by=self.alice,
        )
        r2 = DebtRepayment.objects.create(
            debt=debt,
            amount=Decimal('200'),
            repayment_type=DebtRepayment.RepaymentType.MANUAL,
            created_by=self.alice,
        )

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = list_debt_repayments(request, debt.id)
        self.assertEqual(result[0].id, r2.id)
        self.assertEqual(result[1].id, r1.id)

    def test_repayment_response_fields(self, mock_notify, mock_ws, mock_graph):
        """Verify repayment response fields."""
        from debts.api import list_debt_repayments

        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        DebtRepayment.objects.create(
            debt=debt,
            amount=Decimal('100'),
            repayment_type=DebtRepayment.RepaymentType.MANUAL,
            notes='Cash payment',
            created_by=self.alice,
        )

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = list_debt_repayments(request, debt.id)
        rep = result[0]
        self.assertEqual(rep.object_type, 'debt_repayment')
        self.assertEqual(rep.amount, Decimal('100'))
        self.assertEqual(rep.repayment_type, 'MANUAL')
        self.assertEqual(rep.notes, 'Cash payment')
        self.assertEqual(rep.debt_id, debt.id)
        self.assertIsNotNone(rep.created_at)


# ===========================================================================
# Integration: Full Debt Lifecycle
# ===========================================================================

@patch('debts.signals.graph_service')
@patch('parahub.services.ws_publish.ws_publish')
@patch('notifications.services.notify_new_debt')
class DebtLifecycleTest(TestCase):
    """Test full debt lifecycle: create → confirm → repay → settle."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance)
        self.factory = RequestFactory()

    def test_creditor_creates_debtor_confirms_then_repay(self, mock_notify, mock_ws, mock_graph):
        """Full lifecycle: creditor creates → debtor confirms → creditor repays."""
        from debts.api import (
            create_debt, confirm_debt, create_repayment,
            DebtCreateRequest, ConfirmDebtRequest, RepayDebtRequest,
        )

        # 1. Alice (creditor) creates debt
        data = DebtCreateRequest(
            creditor_id=self.alice.id,
            debtor_id=self.bob.id,
            amount=Decimal('1000'),
            currency='EUR',
            description='Loan for equipment',
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = create_debt(request, data)
        debt_id = result.id
        self.assertEqual(result.status, 'PENDING_CONFIRMATION')

        # 2. Bob (debtor) confirms
        confirm_data = ConfirmDebtRequest(confirmed=True)
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        result = confirm_debt(request, debt_id, confirm_data)
        self.assertEqual(result.status, 'ACTIVE')

        # 3. Alice records partial repayment
        repay_data = RepayDebtRequest(amount=Decimal('400'), notes='First payment')
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        create_repayment(request, debt_id, repay_data)

        debt = Debt.objects.get(id=debt_id)
        self.assertEqual(debt.remaining_amount, Decimal('600'))
        self.assertEqual(debt.status, Debt.Status.PARTIALLY_SETTLED)

        # 4. Alice records full remaining repayment
        repay_data = RepayDebtRequest(amount=Decimal('600'), notes='Final payment')
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        create_repayment(request, debt_id, repay_data)

        debt.refresh_from_db()
        self.assertEqual(debt.remaining_amount, Decimal('0'))
        self.assertEqual(debt.status, Debt.Status.FULLY_SETTLED)
        self.assertEqual(debt.percent_settled, Decimal('100.0'))

    def test_debtor_self_admits_then_repay(self, mock_notify, mock_ws, mock_graph):
        """Debtor admits debt → immediately ACTIVE → repay to settle."""
        from debts.api import (
            create_debt, create_repayment,
            DebtCreateRequest, RepayDebtRequest,
        )

        # Bob (debtor) creates debt (self-admitted)
        data = DebtCreateRequest(
            creditor_id=self.alice.id,
            debtor_id=self.bob.id,
            amount=Decimal('200'),
        )
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        result = create_debt(request, data)
        self.assertEqual(result.status, 'ACTIVE')

        # Alice records full repayment
        repay_data = RepayDebtRequest(amount=Decimal('200'))
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        create_repayment(request, result.id, repay_data)

        debt = Debt.objects.get(id=result.id)
        self.assertEqual(debt.status, Debt.Status.FULLY_SETTLED)

    def test_create_then_reject(self, mock_notify, mock_ws, mock_graph):
        """Creditor creates, debtor rejects → CANCELLED."""
        from debts.api import create_debt, confirm_debt, DebtCreateRequest, ConfirmDebtRequest

        data = DebtCreateRequest(
            creditor_id=self.alice.id,
            debtor_id=self.bob.id,
            amount=Decimal('5000'),
        )
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = create_debt(request, data)
        self.assertEqual(result.status, 'PENDING_CONFIRMATION')

        # Bob rejects
        confirm_data = ConfirmDebtRequest(confirmed=False)
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        result = confirm_debt(request, result.id, confirm_data)
        self.assertEqual(result.status, 'CANCELLED')


# ===========================================================================
# Model save() auto-status tests
# ===========================================================================

@patch('debts.signals.graph_service')
@patch('parahub.services.ws_publish.ws_publish')
@patch('notifications.services.notify_new_debt')
class DebtModelSaveTest(TestCase):
    """Test Debt model save() auto-status logic."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance)

    def test_save_sets_remaining_on_create(self, mock_notify, mock_ws, mock_graph):
        """remaining_amount auto-set to amount on creation."""
        debt = Debt.objects.create(
            creditor=self.alice,
            debtor=self.bob,
            amount=Decimal('500'),
            remaining_amount=Decimal('0'),  # explicitly zero, but save should NOT override when explicitly set
            currency='EUR',
            status=Debt.Status.ACTIVE,
            created_by=self.bob,
        )
        # When remaining_amount is explicitly set to 0 (falsy), save() sets it to amount
        debt.refresh_from_db()
        self.assertEqual(debt.remaining_amount, Decimal('500'))

    def test_auto_fully_settled(self, mock_notify, mock_ws, mock_graph):
        """Setting remaining_amount to 0 auto-changes status to FULLY_SETTLED."""
        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        debt.remaining_amount = Decimal('0')
        debt.save()
        debt.refresh_from_db()
        self.assertEqual(debt.status, Debt.Status.FULLY_SETTLED)

    def test_auto_partially_settled(self, mock_notify, mock_ws, mock_graph):
        """Reducing remaining_amount while ACTIVE → PARTIALLY_SETTLED."""
        debt = _create_debt(self.alice, self.bob, Decimal('500'))
        debt.remaining_amount = Decimal('300')
        debt.save()
        debt.refresh_from_db()
        self.assertEqual(debt.status, Debt.Status.PARTIALLY_SETTLED)
