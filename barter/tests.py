from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from ninja.errors import HttpError

from barter.graph_service import BarterGraphService


class BuildItemsChainQueryTest(SimpleTestCase):
    def setUp(self):
        self.svc = BarterGraphService.__new__(BarterGraphService)

    def test_length_2_structure(self):
        q = self.svc._build_items_chain_query(2)
        self.assertIn("offered1:Item {type: 'CREDIT'", q)
        self.assertIn("wanted1:Item {type: 'DEBIT'", q)
        self.assertIn("<-[:OWNS]-(u2:User)", q)
        self.assertIn("WHERE u2.id <> start.id", q)
        # closes back to start
        self.assertIn("<-[:OWNS]-(start)", q)
        # chain output
        self.assertIn("start.id, u2.id, start.id", q)
        self.assertIn("cat1.id, cat2.id", q)
        self.assertIn("RETURN DISTINCT chain, categories", q)
        self.assertIn("LIMIT 500", q)
        # no u3 should appear
        self.assertNotIn("u3", q)

    def test_length_3_structure(self):
        q = self.svc._build_items_chain_query(3)
        self.assertIn("<-[:OWNS]-(u2:User)", q)
        self.assertIn("<-[:OWNS]-(u3:User)", q)
        # u3 must exclude both start and u2
        self.assertIn("u3.id <> start.id AND u3.id <> u2.id", q)
        self.assertIn("start.id, u2.id, u3.id, start.id", q)
        self.assertIn("cat1.id, cat2.id, cat3.id", q)
        self.assertNotIn("u4", q)

    def test_length_4_structure(self):
        q = self.svc._build_items_chain_query(4)
        self.assertIn("u4", q)
        # u4 must exclude start, u2, u3
        self.assertIn("u4.id <> start.id AND u4.id <> u2.id AND u4.id <> u3.id", q)
        self.assertIn("start.id, u2.id, u3.id, u4.id, start.id", q)
        self.assertIn("cat1.id, cat2.id, cat3.id, cat4.id", q)

    def test_length_5_structure(self):
        q = self.svc._build_items_chain_query(5)
        self.assertIn("u5", q)
        self.assertIn("u5.id <> start.id AND u5.id <> u2.id AND u5.id <> u3.id AND u5.id <> u4.id", q)
        self.assertIn("start.id, u2.id, u3.id, u4.id, u5.id, start.id", q)
        self.assertIn("cat1.id, cat2.id, cat3.id, cat4.id, cat5.id", q)

    def test_all_items_are_active(self):
        for length in range(2, 6):
            q = self.svc._build_items_chain_query(length)
            # Every item match must require is_active: true
            credit_count = q.count("type: 'CREDIT', is_active: true")
            debit_count = q.count("type: 'DEBIT', is_active: true")
            self.assertEqual(credit_count, length, f"length={length}: expected {length} CREDIT matches")
            self.assertEqual(debit_count, length, f"length={length}: expected {length} DEBIT matches")


class BuildDebtChainQueryTest(SimpleTestCase):
    def setUp(self):
        self.svc = BarterGraphService.__new__(BarterGraphService)

    def test_length_2_structure(self):
        q = self.svc._build_debt_chain_query(2)
        self.assertIn("type: 'DEBT', is_active: true", q)
        self.assertIn("debt1.is_debt = true", q)
        self.assertIn("debt2.creditor_id = start.id", q)
        self.assertIn("start.id, u2.id, start.id", q)
        self.assertIn("'DEBT', 'DEBT'", q)
        self.assertNotIn("u3", q)

    def test_length_3_structure(self):
        q = self.svc._build_debt_chain_query(3)
        self.assertIn("u3:User {id: debt2.creditor_id}", q)
        self.assertIn("u3.id <> start.id AND u3.id <> u2.id", q)
        self.assertIn("debt3.creditor_id = start.id", q)
        self.assertIn("start.id, u2.id, u3.id, start.id", q)
        self.assertIn("'DEBT', 'DEBT', 'DEBT'", q)

    def test_length_5_structure(self):
        q = self.svc._build_debt_chain_query(5)
        self.assertIn("u5", q)
        self.assertIn("debt5.creditor_id = start.id", q)
        self.assertIn("'DEBT', 'DEBT', 'DEBT', 'DEBT', 'DEBT'", q)

    def test_debt_count_matches_length(self):
        for length in range(2, 6):
            q = self.svc._build_debt_chain_query(length)
            debt_items = q.count("type: 'DEBT', is_active: true")
            self.assertEqual(debt_items, length, f"length={length}: expected {length} DEBT item matches")


class FindBarterChainsCypherTest(SimpleTestCase):
    """Tests that find_barter_chains builds the correct UNION ALL structure."""

    def setUp(self):
        self.svc = BarterGraphService.__new__(BarterGraphService)
        self.svc.client = MagicMock()
        self.svc.client.execute_read.return_value = []

    def _run(self, max_length, constance_max=5):
        with patch('constance.config') as mock_cfg:
            mock_cfg.BARTER_MAX_CHAIN_LENGTH = constance_max
            self.svc.find_barter_chains(user_id='user-1', max_length=max_length)
        return self.svc.client.execute_read.call_args[0][0]

    def test_max_length_2_generates_2_blocks(self):
        q = self._run(max_length=2)
        # 1 items block + 1 debt block = 1 UNION ALL separator
        self.assertEqual(q.count("UNION ALL"), 1)
        self.assertIn("Items cycle length 2", q)
        self.assertIn("Debt cycle length 2", q)
        self.assertNotIn("length 3", q)

    def test_max_length_3_generates_4_blocks(self):
        q = self._run(max_length=3)
        self.assertEqual(q.count("UNION ALL"), 3)
        self.assertIn("Items cycle length 2", q)
        self.assertIn("Debt cycle length 2", q)
        self.assertIn("Items cycle length 3", q)
        self.assertIn("Debt cycle length 3", q)

    def test_max_length_5_generates_8_blocks(self):
        q = self._run(max_length=5)
        self.assertEqual(q.count("UNION ALL"), 7)
        for length in range(2, 6):
            self.assertIn(f"Items cycle length {length}", q)
            self.assertIn(f"Debt cycle length {length}", q)

    def test_constance_cap_is_respected(self):
        # User requests 5, but Constance allows only 3
        q = self._run(max_length=5, constance_max=3)
        self.assertIn("length 3", q)
        self.assertNotIn("length 4", q)

    def test_user_max_length_below_constance_is_respected(self):
        # User requests 2, Constance allows 5 — use user's value
        q = self._run(max_length=2, constance_max=5)
        self.assertNotIn("length 3", q)

    def test_minimum_length_is_2(self):
        # Even if somehow max_length=1 is passed, min is 2
        q = self._run(max_length=1)
        self.assertIn("length 2", q)

    def test_user_id_param_passed(self):
        with patch('constance.config') as mock_cfg:
            mock_cfg.BARTER_MAX_CHAIN_LENGTH = 3
            self.svc.find_barter_chains(user_id='abc-123', max_length=3)
        params = self.svc.client.execute_read.call_args[0][1]
        self.assertEqual(params['user_id'], 'abc-123')


# ---------------------------------------------------------------------------
# Endpoint Tests
# ---------------------------------------------------------------------------

from identity.models import Account, Profile
from core.models import Instance
from taxonomy.models import Category
from market.models import Item
from barter.models import Exchange, ExchangeSwap, ExchangeApproval


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
    fn = getattr(factory, method)
    request = fn(path, data=data, content_type='application/json') if data else fn(path)
    request.user = account
    request.auth = profile
    request.auth_profile = profile
    request.session = SessionStore()
    request.session.create()
    return request


def _create_exchange(user_chain, category=None, status='PENDING'):
    return Exchange.objects.create(
        user_chain=user_chain,
        category=category,
        status=status,
    )


class GraphStatsEndpointTest(TestCase):
    """Tests for GET /api/v1/barter/graph-stats (public endpoint)."""

    @patch('barter.api.graph_service')
    def test_graph_stats_returns_counts(self, mock_svc):
        mock_svc.get_graph_stats.return_value = {
            'users': 10,
            'items': 25,
            'categories': 5,
            'owns_relationships': 25,
            'category_relationships': 20,
        }
        from barter.api import get_graph_stats
        factory = RequestFactory()
        request = factory.get('/fake/')
        result = get_graph_stats(request)
        self.assertEqual(result.users, 10)
        self.assertEqual(result.items, 25)
        self.assertEqual(result.categories, 5)
        self.assertEqual(result.owns_relationships, 25)
        self.assertEqual(result.category_relationships, 20)

    @patch('barter.api.graph_service')
    def test_graph_stats_returns_zeros_on_error(self, mock_svc):
        mock_svc.get_graph_stats.side_effect = Exception('Neo4j down')
        from barter.api import get_graph_stats
        factory = RequestFactory()
        request = factory.get('/fake/')
        result = get_graph_stats(request)
        self.assertEqual(result.users, 0)
        self.assertEqual(result.items, 0)

    @patch('barter.api.graph_service')
    def test_graph_stats_no_auth_required(self, mock_svc):
        """Public endpoint — works without authentication."""
        mock_svc.get_graph_stats.return_value = {
            'users': 1, 'items': 2, 'categories': 3,
            'owns_relationships': 4, 'category_relationships': 5,
        }
        from barter.api import get_graph_stats
        factory = RequestFactory()
        request = factory.get('/fake/')
        # No request.auth set — should still work
        result = get_graph_stats(request)
        self.assertEqual(result.users, 1)


class OpportunitiesEndpointTest(TestCase):
    """Tests for GET /api/v1/barter/opportunities (auth required)."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.account = _create_account(self.instance)
        self.profile = _create_profile(self.account, self.instance)

    @patch('barter.api.graph_service')
    def test_opportunities_returns_chains(self, mock_svc):
        mock_svc.find_barter_chains.return_value = [
            {
                'users': [
                    {'id': self.profile.id, 'display_name': 'Alice'},
                    {'id': 'user-bob', 'display_name': 'Bob'},
                    {'id': self.profile.id, 'display_name': 'Alice'},
                ],
                'swaps': [
                    {'from_user': self.profile.id, 'to_user': 'user-bob',
                     'offered_items': [], 'wanted_items': [], 'category_id': None},
                ],
            }
        ]
        from barter.api import get_barter_opportunities
        request = _make_auth_request(self.factory, self.account, self.profile)
        with patch('constance.config') as mock_cfg:
            mock_cfg.BARTER_MAX_CHAIN_LENGTH = 5
            result = get_barter_opportunities(request)
        self.assertEqual(result['user_id'], self.profile.id)
        self.assertEqual(result['chains_count'], 1)
        self.assertEqual(len(result['chains']), 1)

    @patch('barter.api.graph_service')
    def test_opportunities_empty_graph(self, mock_svc):
        mock_svc.find_barter_chains.return_value = []
        from barter.api import get_barter_opportunities
        request = _make_auth_request(self.factory, self.account, self.profile)
        with patch('constance.config') as mock_cfg:
            mock_cfg.BARTER_MAX_CHAIN_LENGTH = 5
            result = get_barter_opportunities(request)
        self.assertEqual(result['chains_count'], 0)
        self.assertEqual(result['chains'], [])

    @patch('barter.api.graph_service')
    def test_opportunities_max_length_capped_by_constance(self, mock_svc):
        mock_svc.find_barter_chains.return_value = []
        from barter.api import get_barter_opportunities
        request = _make_auth_request(self.factory, self.account, self.profile)
        with patch('constance.config') as mock_cfg:
            mock_cfg.BARTER_MAX_CHAIN_LENGTH = 3
            get_barter_opportunities(request, max_length=10)
        # graph_service should be called with min(10, 3) = 3
        mock_svc.find_barter_chains.assert_called_once()
        _, kwargs = mock_svc.find_barter_chains.call_args
        self.assertEqual(kwargs['max_length'], 3)

    @patch('barter.api.graph_service')
    def test_opportunities_passes_category_filter(self, mock_svc):
        mock_svc.find_barter_chains.return_value = []
        from barter.api import get_barter_opportunities
        request = _make_auth_request(self.factory, self.account, self.profile)
        with patch('constance.config') as mock_cfg:
            mock_cfg.BARTER_MAX_CHAIN_LENGTH = 5
            get_barter_opportunities(request, category_id='cat-123')
        _, kwargs = mock_svc.find_barter_chains.call_args
        self.assertEqual(kwargs['category_id'], 'cat-123')

    @patch('barter.api.graph_service')
    def test_opportunities_neo4j_error_propagates(self, mock_svc):
        mock_svc.find_barter_chains.side_effect = Exception('Neo4j timeout')
        from barter.api import get_barter_opportunities
        request = _make_auth_request(self.factory, self.account, self.profile)
        with patch('constance.config') as mock_cfg:
            mock_cfg.BARTER_MAX_CHAIN_LENGTH = 5
            with self.assertRaises(Exception):
                get_barter_opportunities(request)


class ExchangeDetailEndpointTest(TestCase):
    """Tests for GET /api/v1/barter/exchanges/{id} (auth required)."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.account = _create_account(self.instance)
        self.profile = _create_profile(self.account, self.instance)
        self.cat = Category.objects.create(name='Electronics', slug='electronics')
        self.exchange = _create_exchange(
            user_chain=[self.profile.id, 'user-bob', self.profile.id],
            category=self.cat,
        )

    def test_get_exchange_success(self):
        from barter.api import get_exchange
        request = _make_auth_request(self.factory, self.account, self.profile)
        result = get_exchange(request, self.exchange.id)
        self.assertEqual(result['cri'], self.exchange.id)
        self.assertEqual(result['status'], 'PENDING')
        self.assertEqual(result['category'], self.cat.id)

    def test_get_exchange_with_prefix(self):
        """EXC- prefix is stripped."""
        from barter.api import get_exchange
        request = _make_auth_request(self.factory, self.account, self.profile)
        result = get_exchange(request, f'EXC-{self.exchange.id}')
        self.assertEqual(result['cri'], self.exchange.id)

    def test_get_exchange_not_found(self):
        from barter.api import get_exchange
        request = _make_auth_request(self.factory, self.account, self.profile)
        result = get_exchange(request, 'nonexistent-id')
        # Returns tuple (body, status_code) for 404
        self.assertEqual(result, ({'error': 'Exchange not found'}, 404))

    def test_get_exchange_shows_approvals(self):
        from barter.api import get_exchange
        ExchangeApproval.objects.create(
            exchange=self.exchange,
            user=self.profile,
            approved=True,
        )
        request = _make_auth_request(self.factory, self.account, self.profile)
        result = get_exchange(request, self.exchange.id)
        self.assertEqual(len(result['approvals']), 1)
        self.assertTrue(result['approvals'][0]['approved'])

    def test_get_exchange_participants(self):
        from barter.api import get_exchange
        request = _make_auth_request(self.factory, self.account, self.profile)
        result = get_exchange(request, self.exchange.id)
        # participants is unique set excluding the closing element
        self.assertIn(self.profile.id, result['participants'])
        self.assertIn('user-bob', result['participants'])


class ApproveExchangeEndpointTest(TestCase):
    """Tests for POST /api/v1/barter/exchanges/{id}/approve (auth required)."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance, 'alice')
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, 'bob')
        self.exchange = _create_exchange(
            user_chain=[self.alice.id, self.bob.id, self.alice.id],
        )

    def test_approve_as_participant(self):
        from barter.api import approve_exchange, ApprovalRequest
        data = ApprovalRequest(approved=True)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = approve_exchange(request, self.exchange.id, data)
        self.assertTrue(result['approved'])
        self.assertEqual(result['exchange_cri'], self.exchange.id)
        self.assertTrue(result['created'])

    def test_reject_as_participant(self):
        from barter.api import approve_exchange, ApprovalRequest
        data = ApprovalRequest(approved=False)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = approve_exchange(request, self.exchange.id, data)
        self.assertFalse(result['approved'])
        # Exchange status should be REJECTED after a rejection
        self.exchange.refresh_from_db()
        self.assertEqual(self.exchange.status, 'REJECTED')

    def test_approve_non_participant_403(self):
        from barter.api import approve_exchange, ApprovalRequest
        charlie_account = _create_account(self.instance, 'charlie')
        charlie = _create_profile(charlie_account, self.instance, 'charlie')
        data = ApprovalRequest(approved=True)
        request = _make_auth_request(self.factory, charlie_account, charlie, 'post')
        result = approve_exchange(request, self.exchange.id, data)
        self.assertEqual(result, ({'error': 'You are not a participant in this exchange'}, 403))

    def test_approve_nonexistent_exchange_404(self):
        from barter.api import approve_exchange, ApprovalRequest
        data = ApprovalRequest(approved=True)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = approve_exchange(request, 'fake-id', data)
        self.assertEqual(result, ({'error': 'Exchange not found'}, 404))

    def test_all_approve_sets_status_approved(self):
        """When all participants approve, exchange status becomes APPROVED."""
        from barter.api import approve_exchange, ApprovalRequest
        # Alice approves
        data = ApprovalRequest(approved=True)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        approve_exchange(request, self.exchange.id, data)
        self.exchange.refresh_from_db()
        self.assertEqual(self.exchange.status, 'PENDING')  # Only 1/2 approved

        # Bob approves
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')
        result = approve_exchange(request, self.exchange.id, data)
        self.exchange.refresh_from_db()
        self.assertEqual(self.exchange.status, 'APPROVED')

    def test_update_approval_idempotent(self):
        """Updating an existing approval updates rather than creates duplicate."""
        from barter.api import approve_exchange, ApprovalRequest
        data = ApprovalRequest(approved=True)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result1 = approve_exchange(request, self.exchange.id, data)
        self.assertTrue(result1['created'])

        # Change mind — reject
        data2 = ApprovalRequest(approved=False)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result2 = approve_exchange(request, self.exchange.id, data2)
        self.assertFalse(result2['created'])
        self.assertFalse(result2['approved'])
        # Only one approval record should exist
        self.assertEqual(ExchangeApproval.objects.filter(
            exchange=self.exchange, user=self.alice
        ).count(), 1)

    def test_approve_with_exc_prefix(self):
        from barter.api import approve_exchange, ApprovalRequest
        data = ApprovalRequest(approved=True)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = approve_exchange(request, f'EXC-{self.exchange.id}', data)
        self.assertTrue(result['approved'])


class MyExchangesEndpointTest(TestCase):
    """Tests for GET /api/v1/barter/my-exchanges (auth required)."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance, 'alice')
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, 'bob')

    def test_returns_user_exchanges(self):
        from barter.api import get_my_exchanges
        _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id])
        _create_exchange(user_chain=[self.alice.id, 'user-c', self.alice.id])
        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = get_my_exchanges(request)
        self.assertEqual(len(result['exchanges']), 2)

    def test_excludes_other_user_exchanges(self):
        from barter.api import get_my_exchanges
        _create_exchange(user_chain=['user-x', 'user-y', 'user-x'])
        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = get_my_exchanges(request)
        self.assertEqual(len(result['exchanges']), 0)

    def test_filter_by_status(self):
        from barter.api import get_my_exchanges
        _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id], status='PENDING')
        _create_exchange(user_chain=[self.alice.id, 'user-c', self.alice.id], status='COMPLETED')
        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = get_my_exchanges(request, status='PENDING')
        self.assertEqual(len(result['exchanges']), 1)
        self.assertEqual(result['exchanges'][0]['status'], 'PENDING')

    def test_no_status_filter_returns_all(self):
        from barter.api import get_my_exchanges
        _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id], status='PENDING')
        _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id], status='APPROVED')
        _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id], status='REJECTED')
        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = get_my_exchanges(request)
        self.assertEqual(len(result['exchanges']), 3)

    def test_exchanges_ordered_by_created_at_desc(self):
        from barter.api import get_my_exchanges
        e1 = _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id])
        e2 = _create_exchange(user_chain=[self.alice.id, 'user-c', self.alice.id])
        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = get_my_exchanges(request)
        # Most recent first
        self.assertEqual(result['exchanges'][0]['cri'], e2.id)

    def test_exchanges_capped_at_50(self):
        from barter.api import get_my_exchanges
        for i in range(55):
            _create_exchange(user_chain=[self.alice.id, f'user-{i}', self.alice.id])
        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = get_my_exchanges(request)
        self.assertEqual(len(result['exchanges']), 50)


class ExchangeModelTest(TestCase):
    """Tests for Exchange model business logic."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance, 'alice')
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, 'bob')

    def test_participants_excludes_closing_duplicate(self):
        exc = _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id])
        participants = exc.participants
        self.assertEqual(len(participants), 2)
        self.assertIn(self.alice.id, participants)
        self.assertIn(self.bob.id, participants)

    def test_check_all_approved_updates_status(self):
        exc = _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id])
        ExchangeApproval.objects.create(exchange=exc, user=self.alice, approved=True)
        ExchangeApproval.objects.create(exchange=exc, user=self.bob, approved=True)
        result = exc.check_all_approved()
        self.assertTrue(result)
        exc.refresh_from_db()
        self.assertEqual(exc.status, 'APPROVED')

    def test_check_all_approved_false_when_partial(self):
        exc = _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id])
        ExchangeApproval.objects.create(exchange=exc, user=self.alice, approved=True)
        result = exc.check_all_approved()
        self.assertFalse(result)
        exc.refresh_from_db()
        self.assertEqual(exc.status, 'PENDING')

    def test_check_any_rejected_updates_status(self):
        exc = _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id])
        ExchangeApproval.objects.create(exchange=exc, user=self.alice, approved=False)
        result = exc.check_any_rejected()
        self.assertTrue(result)
        exc.refresh_from_db()
        self.assertEqual(exc.status, 'REJECTED')

    def test_approval_save_auto_updates_exchange_status(self):
        """ExchangeApproval.save() triggers status check automatically."""
        exc = _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id])
        ExchangeApproval.objects.create(exchange=exc, user=self.alice, approved=True)
        ExchangeApproval.objects.create(exchange=exc, user=self.bob, approved=True)
        exc.refresh_from_db()
        self.assertEqual(exc.status, 'APPROVED')

    def test_approval_rejection_auto_updates_exchange_status(self):
        exc = _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id])
        ExchangeApproval.objects.create(exchange=exc, user=self.alice, approved=False)
        exc.refresh_from_db()
        self.assertEqual(exc.status, 'REJECTED')

    def test_unique_together_prevents_double_approval(self):
        exc = _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id])
        ExchangeApproval.objects.create(exchange=exc, user=self.alice, approved=True)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            ExchangeApproval.objects.create(exchange=exc, user=self.alice, approved=True)

    def test_exchange_str(self):
        exc = _create_exchange(user_chain=[self.alice.id, self.bob.id, self.alice.id])
        s = str(exc)
        self.assertIn('2 participants', s)
        self.assertIn('PENDING', s)

    def test_three_party_exchange_requires_all_three(self):
        charlie_account = _create_account(self.instance, 'charlie')
        charlie = _create_profile(charlie_account, self.instance, 'charlie')
        exc = _create_exchange(
            user_chain=[self.alice.id, self.bob.id, charlie.id, self.alice.id],
        )
        self.assertEqual(len(exc.participants), 3)
        ExchangeApproval.objects.create(exchange=exc, user=self.alice, approved=True)
        ExchangeApproval.objects.create(exchange=exc, user=self.bob, approved=True)
        exc.refresh_from_db()
        self.assertEqual(exc.status, 'PENDING')  # Still missing charlie
        ExchangeApproval.objects.create(exchange=exc, user=charlie, approved=True)
        exc.refresh_from_db()
        self.assertEqual(exc.status, 'APPROVED')


class ChainNormalizationTest(SimpleTestCase):
    """Tests for _normalize_chain deduplication logic."""

    def setUp(self):
        self.svc = BarterGraphService.__new__(BarterGraphService)

    def test_normalize_starts_with_user_id(self):
        chain = ['B', 'C', 'A', 'B']
        cats = ['cat1', 'cat2', 'cat3']
        result, rotated_cats, sig = self.svc._normalize_chain(chain, cats, 'A')
        self.assertEqual(result[0], 'A')
        self.assertEqual(result[-1], 'A')

    def test_normalize_rotates_categories(self):
        chain = ['B', 'C', 'A', 'B']
        cats = ['cat1', 'cat2', 'cat3']
        result, rotated_cats, sig = self.svc._normalize_chain(chain, cats, 'A')
        # A is at index 2, so categories rotate: [cat3, cat1, cat2]
        self.assertEqual(rotated_cats, ['cat3', 'cat1', 'cat2'])

    def test_normalize_same_cycle_same_signature(self):
        """Different rotations of same cycle produce same signature."""
        cats = ['c1', 'c2', 'c3']
        _, _, sig1 = self.svc._normalize_chain(['A', 'B', 'C', 'A'], cats, 'A')
        _, _, sig2 = self.svc._normalize_chain(['B', 'C', 'A', 'B'], cats, 'A')
        self.assertEqual(sig1, sig2)

    def test_normalize_user_not_in_chain(self):
        chain = ['B', 'C', 'B']
        cats = ['c1', 'c2']
        result, _, _ = self.svc._normalize_chain(chain, cats, 'X')
        # Returns original chain when user not found
        self.assertEqual(result, chain)


class GroupTwoWayExchangesTest(SimpleTestCase):
    """Tests for _group_two_way_exchanges deduplication."""

    def setUp(self):
        self.svc = BarterGraphService.__new__(BarterGraphService)

    def test_two_way_merges_swaps(self):
        chains = [
            {
                'users': ['A', 'B', 'A'],
                'swaps': [
                    {'from_user': 'A', 'to_user': 'B', 'offered_items': [{'id': 'i1'}], 'wanted_items': []},
                    {'from_user': 'B', 'to_user': 'A', 'offered_items': [{'id': 'i2'}], 'wanted_items': []},
                ],
            },
            {
                'users': ['A', 'B', 'A'],
                'swaps': [
                    {'from_user': 'A', 'to_user': 'B', 'offered_items': [{'id': 'i3'}], 'wanted_items': []},
                    {'from_user': 'B', 'to_user': 'A', 'offered_items': [{'id': 'i4'}], 'wanted_items': []},
                ],
            },
        ]
        result = self.svc._group_two_way_exchanges(chains, 'A')
        self.assertEqual(len(result), 1)  # Merged into one opportunity
        # User A offers i1 + i3
        a_swap = [s for s in result[0]['swaps'] if s['from_user'] == 'A'][0]
        offered_ids = {item['id'] for item in a_swap['offered_items']}
        self.assertEqual(offered_ids, {'i1', 'i3'})

    def test_three_way_keeps_separate(self):
        chains = [
            {
                'users': ['A', 'B', 'C', 'A'],
                'swaps': [
                    {'from_user': 'A', 'to_user': 'B', 'offered_items': [{'id': 'x'}], 'wanted_items': []},
                ],
            },
        ]
        result = self.svc._group_two_way_exchanges(chains, 'A')
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]['users']), 4)  # A, B, C, A

    def test_deduplicates_items_by_id(self):
        chains = [
            {
                'users': ['A', 'B', 'A'],
                'swaps': [
                    {'from_user': 'A', 'to_user': 'B', 'offered_items': [{'id': 'same'}], 'wanted_items': []},
                ],
            },
            {
                'users': ['A', 'B', 'A'],
                'swaps': [
                    {'from_user': 'A', 'to_user': 'B', 'offered_items': [{'id': 'same'}], 'wanted_items': []},
                ],
            },
        ]
        result = self.svc._group_two_way_exchanges(chains, 'A')
        a_swap = [s for s in result[0]['swaps'] if s['from_user'] == 'A'][0]
        self.assertEqual(len(a_swap['offered_items']), 1)  # Deduplicated
