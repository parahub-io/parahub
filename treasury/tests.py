"""
Tests for treasury endpoints: proposals, voting, epochs, expenses.

Tests invariants that must never break:
- Only eligible members (correct membership level) can vote
- Allocation validation: all active categories present, sum=100%, no negatives
- Median calculation is correct (statistics.median + normalization)
- Merkle root is deterministic and changes with different inputs
- Merkle chain audit log integrity (each entry links to previous)
- Epoch freeze captures correct snapshot
- Expense permissions: only treasurer/owner/admin can create
- Expense approval: only auditor/owner/admin can approve/reject
- Only DRAFT expenses can be edited or status-changed
- Treasury must be enabled for all operations
- One allocation per profile per establishment (unique constraint)
"""

import hashlib
import json
import statistics
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from ninja.errors import HttpError

from identity.models import Account, Profile
from core.models import Instance
from geo.models import Establishment, EstablishmentMembership
from treasury.models import (
    BudgetCategory, BudgetAllocation, BudgetEpoch,
    Expense, TreasuryAuditLog,
)
from treasury.services import TreasuryService, TreasuryAuditService


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
    """Build a request with auth attached (mimics ProfileAuth)."""
    fn = getattr(factory, method)
    request = fn(path, data=data, content_type='application/json') if data else fn(path)
    request.user = account
    request.auth = profile
    request.auth_profile = profile
    request.session = SessionStore()
    request.session.create()
    return request


def _create_treasury_establishment(owner_profile, slug='test-org', levels=None):
    """Create an Establishment with treasury enabled."""
    return Establishment.objects.create(
        owner=owner_profile,
        name='Test Org',
        slug=slug,
        is_active=True,
        treasury_enabled=True,
        treasury_eligible_levels=levels or ['efetivo', 'fundador'],
    )


def _create_membership(profile, establishment, role='MEMBER', level='efetivo', **kwargs):
    return EstablishmentMembership.objects.create(
        profile=profile,
        establishment=establishment,
        role=role,
        membership_level=level,
        **kwargs,
    )


def _create_categories(establishment, count=3):
    """Create budget categories, return list of category objects."""
    slugs = ['operations', 'team', 'development', 'marketing', 'community', 'reserve']
    cats = []
    for i in range(min(count, len(slugs))):
        cats.append(BudgetCategory.objects.create(
            establishment=establishment,
            name=slugs[i].title(),
            slug=slugs[i],
            icon='settings',
            order=i,
        ))
    return cats


def _make_allocations(categories, values=None):
    """Build allocations dict. values is list of floats summing to 100."""
    if values is None:
        # Equal distribution
        per_cat = round(100.0 / len(categories), 2)
        values = [per_cat] * len(categories)
        # Adjust last to make sum exactly 100
        values[-1] = round(100.0 - sum(values[:-1]), 2)
    return {cat.id: values[i] for i, cat in enumerate(categories)}


# ===========================================================================
# Service Layer Tests
# ===========================================================================

class TestTreasuryEligibility(TestCase):
    """Test eligibility rules for treasury voting."""

    def setUp(self):
        self.instance = _create_instance()
        self.acc_owner = _create_account(self.instance, 'owner')
        self.prof_owner = _create_profile(self.acc_owner, self.instance)
        self.est = _create_treasury_establishment(self.prof_owner)

        self.acc_alice = _create_account(self.instance, 'alice')
        self.prof_alice = _create_profile(self.acc_alice, self.instance, 'alice')
        self.acc_bob = _create_account(self.instance, 'bob')
        self.prof_bob = _create_profile(self.acc_bob, self.instance, 'bob')

    def test_eligible_with_correct_level(self):
        _create_membership(self.prof_alice, self.est, level='efetivo')
        self.assertTrue(TreasuryService.is_eligible(self.prof_alice, self.est))

    def test_eligible_fundador_level(self):
        _create_membership(self.prof_alice, self.est, level='fundador')
        self.assertTrue(TreasuryService.is_eligible(self.prof_alice, self.est))

    def test_not_eligible_apoiante(self):
        """Apoiante not in eligible levels → cannot vote."""
        _create_membership(self.prof_alice, self.est, level='apoiante')
        self.assertFalse(TreasuryService.is_eligible(self.prof_alice, self.est))

    def test_not_eligible_no_membership(self):
        self.assertFalse(TreasuryService.is_eligible(self.prof_alice, self.est))

    def test_not_eligible_empty_levels(self):
        """If establishment has no eligible levels configured, nobody can vote."""
        self.est.treasury_eligible_levels = []
        self.est.save()
        _create_membership(self.prof_alice, self.est, level='efetivo')
        self.assertFalse(TreasuryService.is_eligible(self.prof_alice, self.est))

    def test_get_eligible_profiles_returns_correct_set(self):
        _create_membership(self.prof_alice, self.est, level='efetivo')
        _create_membership(self.prof_bob, self.est, level='apoiante')
        eligible = TreasuryService.get_eligible_profiles(self.est)
        self.assertEqual(set(eligible.values_list('id', flat=True)), {self.prof_alice.id})

    def test_get_eligible_profiles_multiple(self):
        _create_membership(self.prof_alice, self.est, level='efetivo')
        _create_membership(self.prof_bob, self.est, level='fundador')
        eligible = TreasuryService.get_eligible_profiles(self.est)
        self.assertEqual(eligible.count(), 2)


class TestAllocationValidation(TestCase):
    """Test allocation validation rules."""

    def setUp(self):
        self.instance = _create_instance()
        self.acc = _create_account(self.instance, 'owner')
        self.prof = _create_profile(self.acc, self.instance)
        self.est = _create_treasury_establishment(self.prof)
        self.cats = _create_categories(self.est, 3)

    def test_valid_allocation(self):
        allocs = _make_allocations(self.cats, [40.0, 30.0, 30.0])
        is_valid, err = TreasuryService.validate_allocations(allocs, self.est)
        self.assertTrue(is_valid)
        self.assertIsNone(err)

    def test_valid_all_in_one_category(self):
        allocs = _make_allocations(self.cats, [100.0, 0.0, 0.0])
        is_valid, err = TreasuryService.validate_allocations(allocs, self.est)
        self.assertTrue(is_valid)

    def test_reject_missing_category(self):
        allocs = {self.cats[0].id: 50.0, self.cats[1].id: 50.0}
        # Missing cats[2]
        is_valid, err = TreasuryService.validate_allocations(allocs, self.est)
        self.assertFalse(is_valid)
        self.assertIn('Missing', err)

    def test_reject_unknown_category(self):
        allocs = _make_allocations(self.cats, [30.0, 30.0, 40.0])
        allocs['FAKE_ID_XXXX'] = 0.0
        is_valid, err = TreasuryService.validate_allocations(allocs, self.est)
        self.assertFalse(is_valid)
        self.assertIn('Unknown', err)

    def test_reject_negative_value(self):
        allocs = _make_allocations(self.cats, [-10.0, 60.0, 50.0])
        is_valid, err = TreasuryService.validate_allocations(allocs, self.est)
        self.assertFalse(is_valid)
        self.assertIn('Negative', err)

    def test_reject_sum_not_100(self):
        allocs = _make_allocations(self.cats, [30.0, 30.0, 30.0])
        is_valid, err = TreasuryService.validate_allocations(allocs, self.est)
        self.assertFalse(is_valid)
        self.assertIn('Sum must be 100', err)

    def test_tolerance_within_001(self):
        """Sum 99.995 should pass (within ±0.01 tolerance)."""
        allocs = _make_allocations(self.cats, [33.335, 33.33, 33.335])
        is_valid, err = TreasuryService.validate_allocations(allocs, self.est)
        self.assertTrue(is_valid)

    def test_tolerance_exceeded(self):
        """Sum 99.5 should fail (exceeds ±0.01)."""
        allocs = _make_allocations(self.cats, [33.0, 33.0, 33.5])
        is_valid, err = TreasuryService.validate_allocations(allocs, self.est)
        self.assertFalse(is_valid)

    def test_ignores_inactive_categories(self):
        """Inactive categories should not be required."""
        self.cats[2].is_active = False
        self.cats[2].save()
        allocs = {self.cats[0].id: 50.0, self.cats[1].id: 50.0}
        is_valid, err = TreasuryService.validate_allocations(allocs, self.est)
        self.assertTrue(is_valid)


class TestMedianCalculation(TestCase):
    """Test median voting algorithm correctness."""

    def setUp(self):
        self.instance = _create_instance()
        self.acc = _create_account(self.instance, 'owner')
        self.prof = _create_profile(self.acc, self.instance)
        self.est = _create_treasury_establishment(self.prof)
        self.cats = _create_categories(self.est, 3)

    def _add_voter(self, username, values):
        acc = _create_account(self.instance, username)
        prof = _create_profile(acc, self.instance, username)
        _create_membership(prof, self.est, level='efetivo')
        allocs = _make_allocations(self.cats, values)
        BudgetAllocation.objects.create(
            establishment=self.est, profile=prof, allocations=allocs,
        )
        return prof

    def test_single_voter_gets_own_values(self):
        self._add_voter('alice', [50.0, 30.0, 20.0])
        medians = TreasuryService.calculate_current_medians(self.est)
        self.assertEqual(len(medians), 3)
        # Single voter: normalized medians = original values
        total = sum(m['median_percent'] for m in medians)
        self.assertAlmostEqual(total, 100.0, places=1)

    def test_two_voters_median_is_average(self):
        """With 2 voters, median = average of the two values."""
        self._add_voter('alice', [60.0, 20.0, 20.0])
        self._add_voter('bob', [40.0, 40.0, 20.0])
        medians = TreasuryService.calculate_current_medians(self.est)
        # Raw medians: 50, 30, 20 → sum=100 → normalized: 50, 30, 20
        by_slug = {m['slug']: m['median_percent'] for m in medians}
        self.assertAlmostEqual(by_slug['operations'], 50.0, places=1)
        self.assertAlmostEqual(by_slug['team'], 30.0, places=1)
        self.assertAlmostEqual(by_slug['development'], 20.0, places=1)

    def test_three_voters_true_median(self):
        """With 3 voters, median picks the middle value."""
        self._add_voter('alice', [70.0, 20.0, 10.0])
        self._add_voter('bob', [40.0, 30.0, 30.0])
        self._add_voter('carol', [50.0, 25.0, 25.0])
        medians = TreasuryService.calculate_current_medians(self.est)
        # Raw medians: ops=[40,50,70]→50, team=[20,25,30]→25, dev=[10,25,30]→25
        # Sum raw = 100 → normalized: 50, 25, 25
        by_slug = {m['slug']: m['median_percent'] for m in medians}
        self.assertAlmostEqual(by_slug['operations'], 50.0, places=1)
        self.assertAlmostEqual(by_slug['team'], 25.0, places=1)
        self.assertAlmostEqual(by_slug['development'], 25.0, places=1)

    def test_normalization_when_medians_dont_sum_100(self):
        """Medians from diverse voters may not sum to 100 → normalization required."""
        self._add_voter('alice', [80.0, 10.0, 10.0])
        self._add_voter('bob', [10.0, 80.0, 10.0])
        self._add_voter('carol', [10.0, 10.0, 80.0])
        medians = TreasuryService.calculate_current_medians(self.est)
        # Raw medians: all 10 (each is median of [10,10,80]) → sum=30
        # Normalized: 33.3, 33.3, 33.3
        total = sum(m['median_percent'] for m in medians)
        self.assertAlmostEqual(total, 100.0, places=0)
        for m in medians:
            self.assertAlmostEqual(m['median_percent'], 33.3, places=0)

    def test_no_voters_all_zero(self):
        medians = TreasuryService.calculate_current_medians(self.est)
        self.assertEqual(len(medians), 3)
        for m in medians:
            self.assertEqual(m['median_percent'], 0.0)
            self.assertEqual(m['voter_count'], 0)

    def test_voter_count_correct(self):
        self._add_voter('alice', [50.0, 30.0, 20.0])
        self._add_voter('bob', [40.0, 40.0, 20.0])
        medians = TreasuryService.calculate_current_medians(self.est)
        for m in medians:
            self.assertEqual(m['voter_count'], 2)

    def test_ineligible_voter_excluded(self):
        """Allocations from ineligible profiles are ignored."""
        self._add_voter('alice', [50.0, 30.0, 20.0])
        # Bob with apoiante level (not eligible)
        acc_bob = _create_account(self.instance, 'bob')
        prof_bob = _create_profile(acc_bob, self.instance, 'bob')
        _create_membership(prof_bob, self.est, level='apoiante')
        BudgetAllocation.objects.create(
            establishment=self.est, profile=prof_bob,
            allocations=_make_allocations(self.cats, [10.0, 10.0, 80.0]),
        )
        medians = TreasuryService.calculate_current_medians(self.est)
        for m in medians:
            self.assertEqual(m['voter_count'], 1)


class TestMerkleRoot(TestCase):
    """Test Merkle root calculation for epoch snapshots."""

    def test_empty_snapshot(self):
        root = TreasuryService._calculate_merkle_root([])
        expected = hashlib.sha256(b'empty').hexdigest()
        self.assertEqual(root, expected)

    def test_single_voter(self):
        snapshot = [{'profile_id': 'A', 'hna': 'alice', 'allocations': {'x': 50, 'y': 50}, 'pgp_signature': ''}]
        root = TreasuryService._calculate_merkle_root(snapshot)
        self.assertEqual(len(root), 64)  # SHA256 hex

    def test_deterministic(self):
        """Same input → same root."""
        snapshot = [
            {'profile_id': 'A', 'hna': 'alice', 'allocations': {'x': 50, 'y': 50}, 'pgp_signature': ''},
            {'profile_id': 'B', 'hna': 'bob', 'allocations': {'x': 60, 'y': 40}, 'pgp_signature': ''},
        ]
        root1 = TreasuryService._calculate_merkle_root(snapshot)
        root2 = TreasuryService._calculate_merkle_root(snapshot)
        self.assertEqual(root1, root2)

    def test_different_data_different_root(self):
        snap1 = [{'profile_id': 'A', 'hna': 'alice', 'allocations': {'x': 50, 'y': 50}, 'pgp_signature': ''}]
        snap2 = [{'profile_id': 'A', 'hna': 'alice', 'allocations': {'x': 60, 'y': 40}, 'pgp_signature': ''}]
        root1 = TreasuryService._calculate_merkle_root(snap1)
        root2 = TreasuryService._calculate_merkle_root(snap2)
        self.assertNotEqual(root1, root2)

    def test_order_independent_by_profile_id(self):
        """Sorting by profile_id ensures order doesn't matter."""
        snap_ab = [
            {'profile_id': 'A', 'hna': 'alice', 'allocations': {'x': 50}, 'pgp_signature': ''},
            {'profile_id': 'B', 'hna': 'bob', 'allocations': {'x': 60}, 'pgp_signature': ''},
        ]
        snap_ba = [
            {'profile_id': 'B', 'hna': 'bob', 'allocations': {'x': 60}, 'pgp_signature': ''},
            {'profile_id': 'A', 'hna': 'alice', 'allocations': {'x': 50}, 'pgp_signature': ''},
        ]
        self.assertEqual(
            TreasuryService._calculate_merkle_root(snap_ab),
            TreasuryService._calculate_merkle_root(snap_ba),
        )

    def test_odd_number_of_leaves(self):
        """3 leaves: last leaf pairs with itself."""
        snapshot = [
            {'profile_id': 'A', 'hna': 'a', 'allocations': {'x': 33}, 'pgp_signature': ''},
            {'profile_id': 'B', 'hna': 'b', 'allocations': {'x': 33}, 'pgp_signature': ''},
            {'profile_id': 'C', 'hna': 'c', 'allocations': {'x': 34}, 'pgp_signature': ''},
        ]
        root = TreasuryService._calculate_merkle_root(snapshot)
        self.assertEqual(len(root), 64)


class TestUpdateAllocation(TestCase):
    """Test allocation create/update."""

    def setUp(self):
        self.instance = _create_instance()
        self.acc = _create_account(self.instance, 'owner')
        self.prof = _create_profile(self.acc, self.instance)
        self.est = _create_treasury_establishment(self.prof)
        self.cats = _create_categories(self.est, 3)

    def test_create_allocation(self):
        allocs = _make_allocations(self.cats, [40.0, 30.0, 30.0])
        obj = TreasuryService.update_allocation(self.prof, self.est, allocs)
        self.assertEqual(obj.allocations, allocs)
        self.assertEqual(BudgetAllocation.objects.count(), 1)

    def test_update_existing_allocation(self):
        allocs1 = _make_allocations(self.cats, [40.0, 30.0, 30.0])
        TreasuryService.update_allocation(self.prof, self.est, allocs1)
        allocs2 = _make_allocations(self.cats, [50.0, 25.0, 25.0])
        obj = TreasuryService.update_allocation(self.prof, self.est, allocs2)
        self.assertEqual(obj.allocations, allocs2)
        self.assertEqual(BudgetAllocation.objects.count(), 1)  # Still one

    def test_unique_per_profile_per_establishment(self):
        """Different profiles can have allocations for same establishment."""
        acc2 = _create_account(self.instance, 'bob')
        prof2 = _create_profile(acc2, self.instance, 'bob')
        allocs = _make_allocations(self.cats, [40.0, 30.0, 30.0])
        TreasuryService.update_allocation(self.prof, self.est, allocs)
        TreasuryService.update_allocation(prof2, self.est, allocs)
        self.assertEqual(BudgetAllocation.objects.count(), 2)


class TestEpochFreeze(TestCase):
    """Test epoch freeze snapshot and Merkle root."""

    def setUp(self):
        self.instance = _create_instance()
        self.acc_owner = _create_account(self.instance, 'owner')
        self.prof_owner = _create_profile(self.acc_owner, self.instance)
        self.est = _create_treasury_establishment(self.prof_owner)
        self.cats = _create_categories(self.est, 3)

    def _add_voter_with_allocation(self, username, values):
        acc = _create_account(self.instance, username)
        prof = _create_profile(acc, self.instance, username)
        _create_membership(prof, self.est, level='efetivo')
        allocs = _make_allocations(self.cats, values)
        BudgetAllocation.objects.create(
            establishment=self.est, profile=prof, allocations=allocs,
        )
        return prof

    def test_freeze_creates_epoch(self):
        self._add_voter_with_allocation('alice', [50.0, 30.0, 20.0])
        epoch = TreasuryService.freeze_epoch(
            self.est, '2026-02', date(2026, 2, 1), date(2026, 2, 28)
        )
        self.assertEqual(epoch.status, BudgetEpoch.Status.FINALIZED)
        self.assertEqual(epoch.label, '2026-02')
        self.assertIsNotNone(epoch.finalized_at)
        self.assertEqual(epoch.total_eligible, 1)
        self.assertEqual(epoch.total_participants, 1)

    def test_freeze_captures_individual_snapshot(self):
        self._add_voter_with_allocation('alice', [50.0, 30.0, 20.0])
        self._add_voter_with_allocation('bob', [40.0, 40.0, 20.0])
        epoch = TreasuryService.freeze_epoch(
            self.est, '2026-02', date(2026, 2, 1), date(2026, 2, 28)
        )
        self.assertEqual(len(epoch.individual_allocations_snapshot), 2)
        self.assertEqual(epoch.total_participants, 2)

    def test_freeze_has_merkle_root(self):
        self._add_voter_with_allocation('alice', [50.0, 30.0, 20.0])
        epoch = TreasuryService.freeze_epoch(
            self.est, '2026-02', date(2026, 2, 1), date(2026, 2, 28)
        )
        self.assertEqual(len(epoch.merkle_root), 64)

    def test_freeze_frozen_allocations_are_medians(self):
        self._add_voter_with_allocation('alice', [60.0, 20.0, 20.0])
        self._add_voter_with_allocation('bob', [40.0, 40.0, 20.0])
        epoch = TreasuryService.freeze_epoch(
            self.est, '2026-02', date(2026, 2, 1), date(2026, 2, 28)
        )
        self.assertTrue(len(epoch.frozen_allocations) > 0)
        total = sum(a['median_percent'] for a in epoch.frozen_allocations)
        self.assertAlmostEqual(total, 100.0, places=0)

    def test_freeze_empty_no_voters(self):
        epoch = TreasuryService.freeze_epoch(
            self.est, '2026-02', date(2026, 2, 1), date(2026, 2, 28)
        )
        self.assertEqual(epoch.total_participants, 0)
        self.assertEqual(len(epoch.individual_allocations_snapshot), 0)

    def test_freeze_excludes_ineligible(self):
        """Voters with apoiante level excluded from freeze."""
        self._add_voter_with_allocation('alice', [50.0, 30.0, 20.0])
        acc_bob = _create_account(self.instance, 'bob')
        prof_bob = _create_profile(acc_bob, self.instance, 'bob')
        _create_membership(prof_bob, self.est, level='apoiante')
        BudgetAllocation.objects.create(
            establishment=self.est, profile=prof_bob,
            allocations=_make_allocations(self.cats, [10.0, 10.0, 80.0]),
        )
        epoch = TreasuryService.freeze_epoch(
            self.est, '2026-02', date(2026, 2, 1), date(2026, 2, 28)
        )
        self.assertEqual(epoch.total_participants, 1)


class TestAuditChain(TestCase):
    """Test Merkle-chain audit log integrity."""

    def setUp(self):
        self.instance = _create_instance()
        self.acc = _create_account(self.instance, 'owner')
        self.prof = _create_profile(self.acc, self.instance)
        self.est = _create_treasury_establishment(self.prof)

    def test_first_entry_has_no_previous(self):
        entry = TreasuryAuditService.create_log_entry(
            self.est, 'allocation_updated', {'test': True}, actor=self.prof,
        )
        self.assertIsNone(entry.previous_log_hash)
        self.assertEqual(len(entry.current_log_hash), 64)

    def test_chain_links_correctly(self):
        e1 = TreasuryAuditService.create_log_entry(
            self.est, 'allocation_updated', {'step': 1}, actor=self.prof,
        )
        e2 = TreasuryAuditService.create_log_entry(
            self.est, 'allocation_updated', {'step': 2}, actor=self.prof,
        )
        self.assertEqual(e2.previous_log_hash, e1.current_log_hash)

    def test_three_entry_chain(self):
        e1 = TreasuryAuditService.create_log_entry(
            self.est, 'category_created', {'cat': 'ops'}, actor=self.prof,
        )
        e2 = TreasuryAuditService.create_log_entry(
            self.est, 'allocation_updated', {'step': 1}, actor=self.prof,
        )
        e3 = TreasuryAuditService.create_log_entry(
            self.est, 'epoch_finalized', {'label': '2026-02'},
        )
        self.assertIsNone(e1.previous_log_hash)
        self.assertEqual(e2.previous_log_hash, e1.current_log_hash)
        self.assertEqual(e3.previous_log_hash, e2.current_log_hash)

    def test_hash_is_deterministic_for_same_data(self):
        """Hash depends on action + actor + payload + timestamp + previous."""
        entry = TreasuryAuditService.create_log_entry(
            self.est, 'allocation_updated', {'x': 1}, actor=self.prof,
        )
        # Verify hash by recomputing
        hash_data = {
            'previous_hash': entry.previous_log_hash,
            'action': 'allocation_updated',
            'actor_id': self.prof.id,
            'establishment_id': self.est.id,
            'payload': {'x': 1},
            'timestamp': entry.timestamp.isoformat(),
        }
        expected = hashlib.sha256(json.dumps(hash_data, sort_keys=True).encode()).hexdigest()
        self.assertEqual(entry.current_log_hash, expected)

    def test_per_establishment_scoping(self):
        """Each establishment has its own chain."""
        acc2 = _create_account(self.instance, 'owner2')
        prof2 = _create_profile(acc2, self.instance, 'owner2')
        est2 = _create_treasury_establishment(prof2, slug='org2')

        e1 = TreasuryAuditService.create_log_entry(
            self.est, 'allocation_updated', {'est': 1}, actor=self.prof,
        )
        e2 = TreasuryAuditService.create_log_entry(
            est2, 'allocation_updated', {'est': 2}, actor=prof2,
        )
        # est2's first entry should have no previous (separate chain)
        self.assertIsNone(e2.previous_log_hash)

    def test_system_actor_null(self):
        entry = TreasuryAuditService.create_log_entry(
            self.est, 'epoch_finalized', {'label': '2026-02'},
        )
        self.assertIsNone(entry.actor)

    def test_verify_valid_chain(self):
        TreasuryAuditService.create_log_entry(
            self.est, 'allocation_updated', {'step': 1}, actor=self.prof,
        )
        TreasuryAuditService.create_log_entry(
            self.est, 'expense_created', {'step': 2}, actor=self.prof,
        )
        TreasuryAuditService.create_log_entry(
            self.est, 'epoch_finalized', {'label': '2026-02'},
        )
        is_valid, error = TreasuryAuditService.verify_merkle_chain(self.est)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_verify_detects_tampered_hash(self):
        TreasuryAuditService.create_log_entry(
            self.est, 'allocation_updated', {'step': 1}, actor=self.prof,
        )
        e2 = TreasuryAuditService.create_log_entry(
            self.est, 'expense_created', {'step': 2}, actor=self.prof,
        )
        # Tamper with hash
        TreasuryAuditLog.objects.filter(id=e2.id).update(current_log_hash='bad' * 16)
        is_valid, error = TreasuryAuditService.verify_merkle_chain(self.est)
        self.assertFalse(is_valid)
        self.assertIn('Hash mismatch', error)

    def test_verify_detects_broken_chain(self):
        TreasuryAuditService.create_log_entry(
            self.est, 'allocation_updated', {'step': 1}, actor=self.prof,
        )
        e2 = TreasuryAuditService.create_log_entry(
            self.est, 'expense_created', {'step': 2}, actor=self.prof,
        )
        # Break chain link
        TreasuryAuditLog.objects.filter(id=e2.id).update(previous_log_hash='wrong' * 12)
        is_valid, error = TreasuryAuditService.verify_merkle_chain(self.est)
        self.assertFalse(is_valid)
        self.assertIn('Chain break', error)

    def test_verify_empty_chain(self):
        is_valid, error = TreasuryAuditService.verify_merkle_chain(self.est)
        self.assertTrue(is_valid)
        self.assertIsNone(error)


class TestParticipationStats(TestCase):
    """Test participation stats calculation."""

    def setUp(self):
        self.instance = _create_instance()
        self.acc = _create_account(self.instance, 'owner')
        self.prof = _create_profile(self.acc, self.instance)
        self.est = _create_treasury_establishment(self.prof)
        self.cats = _create_categories(self.est, 3)

    def test_zero_eligible(self):
        stats = TreasuryService.get_participation_stats(self.est)
        self.assertEqual(stats['total_eligible'], 0)
        self.assertEqual(stats['total_participants'], 0)
        self.assertEqual(stats['participation_percent'], 0)

    def test_eligible_but_no_voters(self):
        acc = _create_account(self.instance, 'alice')
        prof = _create_profile(acc, self.instance, 'alice')
        _create_membership(prof, self.est, level='efetivo')
        stats = TreasuryService.get_participation_stats(self.est)
        self.assertEqual(stats['total_eligible'], 1)
        self.assertEqual(stats['total_participants'], 0)
        self.assertEqual(stats['participation_percent'], 0)

    def test_full_participation(self):
        acc = _create_account(self.instance, 'alice')
        prof = _create_profile(acc, self.instance, 'alice')
        _create_membership(prof, self.est, level='efetivo')
        BudgetAllocation.objects.create(
            establishment=self.est, profile=prof,
            allocations=_make_allocations(self.cats),
        )
        stats = TreasuryService.get_participation_stats(self.est)
        self.assertEqual(stats['total_eligible'], 1)
        self.assertEqual(stats['total_participants'], 1)
        self.assertEqual(stats['participation_percent'], 100.0)


# ===========================================================================
# API Endpoint Tests
# ===========================================================================

class TestCategoryEndpoints(TestCase):
    """Test category list endpoint."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.acc = _create_account(self.instance, 'owner')
        self.prof = _create_profile(self.acc, self.instance)
        self.est = _create_treasury_establishment(self.prof)
        self.cats = _create_categories(self.est, 4)

    def test_list_categories_public(self):
        from treasury.api import list_categories
        request = self.factory.get('/fake/')
        result = list_categories(request, self.est.slug)
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0].object_type, 'budget_category')

    def test_list_categories_excludes_inactive(self):
        from treasury.api import list_categories
        self.cats[0].is_active = False
        self.cats[0].save()
        request = self.factory.get('/fake/')
        result = list_categories(request, self.est.slug)
        self.assertEqual(len(result), 3)

    def test_404_treasury_not_enabled(self):
        from treasury.api import list_categories
        self.est.treasury_enabled = False
        self.est.save()
        request = self.factory.get('/fake/')
        with self.assertRaises(HttpError) as ctx:
            list_categories(request, self.est.slug)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_404_nonexistent_slug(self):
        from treasury.api import list_categories
        request = self.factory.get('/fake/')
        with self.assertRaises(HttpError) as ctx:
            list_categories(request, 'nonexistent-slug')
        self.assertEqual(ctx.exception.status_code, 404)


class TestCurrentBudgetEndpoint(TestCase):
    """Test current budget medians endpoint."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.acc = _create_account(self.instance, 'owner')
        self.prof = _create_profile(self.acc, self.instance)
        self.est = _create_treasury_establishment(self.prof)
        self.cats = _create_categories(self.est, 3)

    def test_current_budget_public(self):
        from treasury.api import current_budget
        request = self.factory.get('/fake/')
        result = current_budget(request, self.est.slug)
        self.assertEqual(len(result.medians), 3)
        self.assertEqual(result.total_eligible, 0)

    def test_current_budget_with_voters(self):
        from treasury.api import current_budget
        acc_a = _create_account(self.instance, 'alice')
        prof_a = _create_profile(acc_a, self.instance, 'alice')
        _create_membership(prof_a, self.est, level='efetivo')
        BudgetAllocation.objects.create(
            establishment=self.est, profile=prof_a,
            allocations=_make_allocations(self.cats, [50.0, 30.0, 20.0]),
        )
        request = self.factory.get('/fake/')
        result = current_budget(request, self.est.slug)
        self.assertEqual(result.total_eligible, 1)
        self.assertEqual(result.total_participants, 1)
        total = sum(m.median_percent for m in result.medians)
        self.assertAlmostEqual(total, 100.0, places=0)


class TestMyAllocationEndpoint(TestCase):
    """Test user allocation retrieval endpoint."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.acc = _create_account(self.instance, 'owner')
        self.prof = _create_profile(self.acc, self.instance)
        self.est = _create_treasury_establishment(self.prof)
        self.cats = _create_categories(self.est, 3)

    def test_not_eligible_returns_false(self):
        from treasury.api import my_allocation
        # No membership → not eligible
        request = _make_auth_request(self.factory, self.acc, self.prof)
        result = my_allocation(request, self.est.slug)
        self.assertFalse(result.is_eligible)

    def test_eligible_no_allocation_needs_update(self):
        from treasury.api import my_allocation
        _create_membership(self.prof, self.est, level='efetivo')
        request = _make_auth_request(self.factory, self.acc, self.prof)
        result = my_allocation(request, self.est.slug)
        self.assertTrue(result.is_eligible)
        self.assertTrue(result.needs_update)
        self.assertIsNone(result.allocation)

    def test_eligible_with_allocation(self):
        from treasury.api import my_allocation
        _create_membership(self.prof, self.est, level='efetivo')
        allocs = _make_allocations(self.cats)
        BudgetAllocation.objects.create(
            establishment=self.est, profile=self.prof, allocations=allocs,
        )
        request = _make_auth_request(self.factory, self.acc, self.prof)
        result = my_allocation(request, self.est.slug)
        self.assertTrue(result.is_eligible)
        self.assertFalse(result.needs_update)
        self.assertIsNotNone(result.allocation)

    def test_needs_update_when_categories_changed(self):
        from treasury.api import my_allocation
        _create_membership(self.prof, self.est, level='efetivo')
        allocs = _make_allocations(self.cats)
        BudgetAllocation.objects.create(
            establishment=self.est, profile=self.prof, allocations=allocs,
        )
        # Add a new category → allocation missing it
        BudgetCategory.objects.create(
            establishment=self.est, name='New Cat', slug='new-cat', order=10,
        )
        request = _make_auth_request(self.factory, self.acc, self.prof)
        result = my_allocation(request, self.est.slug)
        self.assertTrue(result.needs_update)


@patch('treasury.api.verify_profile_signature')
class TestUpdateAllocationEndpoint(TestCase):
    """Test allocation update endpoint with PGP mocked."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.acc = _create_account(self.instance, 'owner')
        self.prof = _create_profile(self.acc, self.instance)
        self.est = _create_treasury_establishment(self.prof)
        self.cats = _create_categories(self.est, 3)
        _create_membership(self.prof, self.est, level='efetivo')

    @patch('treasury.api._broadcast_treasury_update')
    def test_update_allocation_success(self, mock_ws, mock_pgp):
        from treasury.api import update_allocation, AllocationIn
        allocs = _make_allocations(self.cats, [40.0, 30.0, 30.0])
        data = AllocationIn(allocations=allocs)
        request = _make_auth_request(self.factory, self.acc, self.prof, method='put',
                                     data=json.dumps(data.dict()), path='/fake/')
        result = update_allocation(request, self.est.slug, data)
        self.assertEqual(result.object_type, 'budget_allocation')
        self.assertEqual(BudgetAllocation.objects.count(), 1)
        # Audit log created
        self.assertEqual(TreasuryAuditLog.objects.count(), 1)
        log = TreasuryAuditLog.objects.first()
        self.assertEqual(log.action, 'allocation_updated')

    @patch('treasury.api._broadcast_treasury_update')
    def test_update_allocation_not_eligible(self, mock_ws, mock_pgp):
        from treasury.api import update_allocation, AllocationIn
        # Remove membership
        EstablishmentMembership.objects.all().delete()
        allocs = _make_allocations(self.cats, [40.0, 30.0, 30.0])
        data = AllocationIn(allocations=allocs)
        request = _make_auth_request(self.factory, self.acc, self.prof, method='put',
                                     data=json.dumps(data.dict()), path='/fake/')
        with self.assertRaises(HttpError) as ctx:
            update_allocation(request, self.est.slug, data)
        self.assertEqual(ctx.exception.status_code, 403)

    @patch('treasury.api._broadcast_treasury_update')
    def test_update_allocation_invalid_sum(self, mock_ws, mock_pgp):
        from treasury.api import update_allocation, AllocationIn
        allocs = _make_allocations(self.cats, [30.0, 30.0, 30.0])
        data = AllocationIn(allocations=allocs)
        request = _make_auth_request(self.factory, self.acc, self.prof, method='put',
                                     data=json.dumps(data.dict()), path='/fake/')
        with self.assertRaises(HttpError) as ctx:
            update_allocation(request, self.est.slug, data)
        self.assertEqual(ctx.exception.status_code, 400)

    @patch('treasury.api._broadcast_treasury_update')
    def test_websocket_broadcast_on_update(self, mock_ws, mock_pgp):
        from treasury.api import update_allocation, AllocationIn
        allocs = _make_allocations(self.cats, [40.0, 30.0, 30.0])
        data = AllocationIn(allocations=allocs)
        request = _make_auth_request(self.factory, self.acc, self.prof, method='put',
                                     data=json.dumps(data.dict()), path='/fake/')
        update_allocation(request, self.est.slug, data)
        mock_ws.assert_called_once()


class TestEpochEndpoints(TestCase):
    """Test epoch list and detail endpoints (list_epochs uses @paginate → test via DB)."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.acc = _create_account(self.instance, 'owner')
        self.prof = _create_profile(self.acc, self.instance)
        self.est = _create_treasury_establishment(self.prof)
        self.cats = _create_categories(self.est, 3)

    def _freeze_epoch(self, label='2026-02'):
        return TreasuryService.freeze_epoch(
            self.est, label, date(2026, 2, 1), date(2026, 2, 28)
        )

    def test_list_epochs_empty(self):
        epochs = BudgetEpoch.objects.filter(establishment=self.est)
        self.assertEqual(epochs.count(), 0)

    def test_list_epochs_with_data(self):
        self._freeze_epoch('2026-01')
        self._freeze_epoch('2026-02')
        epochs = BudgetEpoch.objects.filter(establishment=self.est).order_by('-start_date')
        self.assertEqual(epochs.count(), 2)
        self.assertEqual(epochs.first().status, 'finalized')

    def test_epoch_detail(self):
        from treasury.api import epoch_detail
        epoch = self._freeze_epoch()
        request = self.factory.get('/fake/')
        result = epoch_detail(request, self.est.slug, epoch.id)
        self.assertEqual(result.label, '2026-02')
        self.assertEqual(result.merkle_root, epoch.merkle_root)
        self.assertIsNotNone(result.finalized_at)

    def test_epoch_detail_404(self):
        from treasury.api import epoch_detail
        request = self.factory.get('/fake/')
        with self.assertRaises(HttpError) as ctx:
            epoch_detail(request, self.est.slug, 'NONEXISTENT_EPOCH_ID_XYZ')
        self.assertEqual(ctx.exception.status_code, 404)


class TestStatsEndpoint(TestCase):
    """Test participation stats endpoint."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.acc = _create_account(self.instance, 'owner')
        self.prof = _create_profile(self.acc, self.instance)
        self.est = _create_treasury_establishment(self.prof)

    def test_stats_public(self):
        from treasury.api import participation_stats
        request = self.factory.get('/fake/')
        result = participation_stats(request, self.est.slug)
        self.assertEqual(result.total_eligible, 0)
        self.assertEqual(result.participation_percent, 0)


class TestAuditLogEndpoint(TestCase):
    """Test audit log list endpoint (uses @paginate → test via DB)."""

    def setUp(self):
        self.instance = _create_instance()
        self.acc = _create_account(self.instance, 'owner')
        self.prof = _create_profile(self.acc, self.instance)
        self.est = _create_treasury_establishment(self.prof)

    def test_audit_log_empty(self):
        logs = TreasuryAuditLog.objects.filter(establishment=self.est)
        self.assertEqual(logs.count(), 0)

    def test_audit_log_with_entries(self):
        TreasuryAuditService.create_log_entry(
            self.est, 'allocation_updated', {'test': True}, actor=self.prof,
        )
        TreasuryAuditService.create_log_entry(
            self.est, 'epoch_finalized', {'label': '2026-02'},
        )
        logs = TreasuryAuditLog.objects.filter(establishment=self.est).order_by('-timestamp')
        self.assertEqual(logs.count(), 2)
        self.assertEqual(logs.first().action, 'epoch_finalized')


# ===========================================================================
# Expense Endpoint Tests
# ===========================================================================

class TestExpensePermissions(TestCase):
    """Test expense creation/management permissions."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.acc_owner = _create_account(self.instance, 'owner')
        self.prof_owner = _create_profile(self.acc_owner, self.instance)
        self.est = _create_treasury_establishment(self.prof_owner)
        self.cats = _create_categories(self.est, 3)

        # Treasurer
        self.acc_treas = _create_account(self.instance, 'treasurer')
        self.prof_treas = _create_profile(self.acc_treas, self.instance, 'treasurer')
        _create_membership(self.prof_treas, self.est, level='efetivo', is_treasurer=True)

        # Auditor
        self.acc_auditor = _create_account(self.instance, 'auditor')
        self.prof_auditor = _create_profile(self.acc_auditor, self.instance, 'auditor')
        _create_membership(self.prof_auditor, self.est, level='efetivo', is_auditor=True)

        # Regular member
        self.acc_member = _create_account(self.instance, 'member')
        self.prof_member = _create_profile(self.acc_member, self.instance, 'member')
        _create_membership(self.prof_member, self.est, level='efetivo')

        # Admin
        self.acc_admin = _create_account(self.instance, 'admin')
        self.prof_admin = _create_profile(self.acc_admin, self.instance, 'admin')
        _create_membership(self.prof_admin, self.est, role='ADMIN', level='efetivo')

    def _create_expense_request(self, account, profile, amount=100.0):
        from treasury.api import ExpenseIn
        data = ExpenseIn(
            amount=amount, description='Office supplies',
            date='2026-03-01', category_id=self.cats[0].id,
        )
        return _make_auth_request(
            self.factory, account, profile, method='post',
            data=json.dumps(data.dict()), path='/fake/'
        ), data

    def test_owner_can_create_expense(self):
        from treasury.api import create_expense
        request, data = self._create_expense_request(self.acc_owner, self.prof_owner)
        result = create_expense(request, self.est.slug, data)
        self.assertEqual(result.object_type, 'treasury_expense')
        self.assertEqual(float(result.amount), 100.0)

    def test_treasurer_can_create_expense(self):
        from treasury.api import create_expense
        request, data = self._create_expense_request(self.acc_treas, self.prof_treas)
        result = create_expense(request, self.est.slug, data)
        self.assertEqual(result.object_type, 'treasury_expense')

    def test_admin_can_create_expense(self):
        from treasury.api import create_expense
        request, data = self._create_expense_request(self.acc_admin, self.prof_admin)
        result = create_expense(request, self.est.slug, data)
        self.assertEqual(result.object_type, 'treasury_expense')

    def test_regular_member_cannot_create_expense(self):
        from treasury.api import create_expense
        request, data = self._create_expense_request(self.acc_member, self.prof_member)
        with self.assertRaises(HttpError) as ctx:
            create_expense(request, self.est.slug, data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_auditor_cannot_create_expense(self):
        """Auditor can approve but not create expenses."""
        from treasury.api import create_expense
        request, data = self._create_expense_request(self.acc_auditor, self.prof_auditor)
        with self.assertRaises(HttpError) as ctx:
            create_expense(request, self.est.slug, data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_expense_creates_audit_log(self):
        from treasury.api import create_expense
        request, data = self._create_expense_request(self.acc_owner, self.prof_owner)
        create_expense(request, self.est.slug, data)
        log = TreasuryAuditLog.objects.filter(action='expense_created').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.payload['amount'], '100.0')

    def test_create_expense_auto_epoch_label(self):
        """If no epoch_label provided, defaults to date's YYYY-MM."""
        from treasury.api import create_expense, ExpenseIn
        data = ExpenseIn(amount=50.0, description='Test', date='2026-03-15')
        request = _make_auth_request(
            self.factory, self.acc_owner, self.prof_owner, method='post',
            data=json.dumps(data.dict()), path='/fake/'
        )
        result = create_expense(request, self.est.slug, data)
        self.assertEqual(result.epoch_label, '2026-03')

    def test_create_expense_invalid_category(self):
        from treasury.api import create_expense, ExpenseIn
        data = ExpenseIn(
            amount=50.0, description='Test', date='2026-03-01',
            category_id='NONEXISTENT_CAT',
        )
        request = _make_auth_request(
            self.factory, self.acc_owner, self.prof_owner, method='post',
            data=json.dumps(data.dict()), path='/fake/'
        )
        with self.assertRaises(HttpError) as ctx:
            create_expense(request, self.est.slug, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_expense_invalid_date(self):
        from treasury.api import create_expense, ExpenseIn
        data = ExpenseIn(amount=50.0, description='Test', date='not-a-date')
        request = _make_auth_request(
            self.factory, self.acc_owner, self.prof_owner, method='post',
            data=json.dumps(data.dict()), path='/fake/'
        )
        with self.assertRaises(HttpError) as ctx:
            create_expense(request, self.est.slug, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_expense_no_category(self):
        """Expense without category is valid."""
        from treasury.api import create_expense, ExpenseIn
        data = ExpenseIn(amount=50.0, description='Uncategorized', date='2026-03-01')
        request = _make_auth_request(
            self.factory, self.acc_owner, self.prof_owner, method='post',
            data=json.dumps(data.dict()), path='/fake/'
        )
        result = create_expense(request, self.est.slug, data)
        self.assertIsNone(result.category_id)


class TestExpenseUpdate(TestCase):
    """Test expense update endpoint."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.acc_owner = _create_account(self.instance, 'owner')
        self.prof_owner = _create_profile(self.acc_owner, self.instance)
        self.est = _create_treasury_establishment(self.prof_owner)
        self.cats = _create_categories(self.est, 3)
        self.expense = Expense.objects.create(
            establishment=self.est, category=self.cats[0],
            created_by=self.prof_owner, amount=Decimal('100.00'),
            description='Office supplies', date=date(2026, 3, 1),
            status='DRAFT', epoch_label='2026-03',
        )

    def test_owner_can_update_draft(self):
        from treasury.api import update_expense, ExpenseUpdateIn
        data = ExpenseUpdateIn(amount=200.0, description='Updated')
        request = _make_auth_request(
            self.factory, self.acc_owner, self.prof_owner, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        result = update_expense(request, self.est.slug, self.expense.id, data)
        self.assertEqual(float(result.amount), 200.0)
        self.assertEqual(result.description, 'Updated')

    def test_cannot_update_approved_expense(self):
        from treasury.api import update_expense, ExpenseUpdateIn
        self.expense.status = 'APPROVED'
        self.expense.save()
        data = ExpenseUpdateIn(amount=200.0)
        request = _make_auth_request(
            self.factory, self.acc_owner, self.prof_owner, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        with self.assertRaises(HttpError) as ctx:
            update_expense(request, self.est.slug, self.expense.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_creator_can_update_own_expense(self):
        from treasury.api import update_expense, ExpenseUpdateIn
        # Create expense by a treasurer, then they update it
        acc_t = _create_account(self.instance, 'treasurer')
        prof_t = _create_profile(acc_t, self.instance, 'treasurer')
        _create_membership(prof_t, self.est, is_treasurer=True)
        expense = Expense.objects.create(
            establishment=self.est, created_by=prof_t,
            amount=Decimal('50.00'), description='Test',
            date=date(2026, 3, 1), status='DRAFT',
        )
        data = ExpenseUpdateIn(description='Updated by creator')
        request = _make_auth_request(
            self.factory, acc_t, prof_t, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        result = update_expense(request, self.est.slug, expense.id, data)
        self.assertEqual(result.description, 'Updated by creator')

    def test_regular_member_cannot_update(self):
        from treasury.api import update_expense, ExpenseUpdateIn
        acc_m = _create_account(self.instance, 'member')
        prof_m = _create_profile(acc_m, self.instance, 'member')
        _create_membership(prof_m, self.est, level='efetivo')
        data = ExpenseUpdateIn(amount=200.0)
        request = _make_auth_request(
            self.factory, acc_m, prof_m, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        with self.assertRaises(HttpError) as ctx:
            update_expense(request, self.est.slug, self.expense.id, data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_update_nonexistent_expense(self):
        from treasury.api import update_expense, ExpenseUpdateIn
        data = ExpenseUpdateIn(amount=200.0)
        request = _make_auth_request(
            self.factory, self.acc_owner, self.prof_owner, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        with self.assertRaises(HttpError) as ctx:
            update_expense(request, self.est.slug, 'NONEXISTENT_ID_XYZ', data)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_update_category_to_null(self):
        from treasury.api import update_expense, ExpenseUpdateIn
        data = ExpenseUpdateIn(category_id='')
        request = _make_auth_request(
            self.factory, self.acc_owner, self.prof_owner, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        result = update_expense(request, self.est.slug, self.expense.id, data)
        self.assertIsNone(result.category_id)

    def test_update_invalid_date(self):
        from treasury.api import update_expense, ExpenseUpdateIn
        data = ExpenseUpdateIn(date='bad-date')
        request = _make_auth_request(
            self.factory, self.acc_owner, self.prof_owner, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        with self.assertRaises(HttpError) as ctx:
            update_expense(request, self.est.slug, self.expense.id, data)
        self.assertEqual(ctx.exception.status_code, 400)


class TestExpenseApproval(TestCase):
    """Test expense approval/rejection permissions and state machine."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.acc_owner = _create_account(self.instance, 'owner')
        self.prof_owner = _create_profile(self.acc_owner, self.instance)
        self.est = _create_treasury_establishment(self.prof_owner)

        self.acc_auditor = _create_account(self.instance, 'auditor')
        self.prof_auditor = _create_profile(self.acc_auditor, self.instance, 'auditor')
        _create_membership(self.prof_auditor, self.est, level='efetivo', is_auditor=True)

        self.acc_treas = _create_account(self.instance, 'treasurer')
        self.prof_treas = _create_profile(self.acc_treas, self.instance, 'treasurer')
        _create_membership(self.prof_treas, self.est, level='efetivo', is_treasurer=True)

        self.acc_member = _create_account(self.instance, 'member')
        self.prof_member = _create_profile(self.acc_member, self.instance, 'member')
        _create_membership(self.prof_member, self.est, level='efetivo')

        self.expense = Expense.objects.create(
            establishment=self.est, created_by=self.prof_treas,
            amount=Decimal('100.00'), description='Office supplies',
            date=date(2026, 3, 1), status='DRAFT', epoch_label='2026-03',
        )

    def test_auditor_can_approve(self):
        from treasury.api import update_expense_status, ExpenseStatusIn
        data = ExpenseStatusIn(status='APPROVED')
        request = _make_auth_request(
            self.factory, self.acc_auditor, self.prof_auditor, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        result = update_expense_status(request, self.est.slug, self.expense.id, data)
        self.assertEqual(result.status, 'APPROVED')

    def test_auditor_can_reject(self):
        from treasury.api import update_expense_status, ExpenseStatusIn
        data = ExpenseStatusIn(status='REJECTED')
        request = _make_auth_request(
            self.factory, self.acc_auditor, self.prof_auditor, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        result = update_expense_status(request, self.est.slug, self.expense.id, data)
        self.assertEqual(result.status, 'REJECTED')

    def test_owner_can_approve(self):
        from treasury.api import update_expense_status, ExpenseStatusIn
        data = ExpenseStatusIn(status='APPROVED')
        request = _make_auth_request(
            self.factory, self.acc_owner, self.prof_owner, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        result = update_expense_status(request, self.est.slug, self.expense.id, data)
        self.assertEqual(result.status, 'APPROVED')

    def test_treasurer_cannot_approve(self):
        """Treasurer creates expenses but cannot approve them (separation of duties)."""
        from treasury.api import update_expense_status, ExpenseStatusIn
        data = ExpenseStatusIn(status='APPROVED')
        request = _make_auth_request(
            self.factory, self.acc_treas, self.prof_treas, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        with self.assertRaises(HttpError) as ctx:
            update_expense_status(request, self.est.slug, self.expense.id, data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_member_cannot_approve(self):
        from treasury.api import update_expense_status, ExpenseStatusIn
        data = ExpenseStatusIn(status='APPROVED')
        request = _make_auth_request(
            self.factory, self.acc_member, self.prof_member, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        with self.assertRaises(HttpError) as ctx:
            update_expense_status(request, self.est.slug, self.expense.id, data)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_cannot_approve_already_approved(self):
        from treasury.api import update_expense_status, ExpenseStatusIn
        self.expense.status = 'APPROVED'
        self.expense.save()
        data = ExpenseStatusIn(status='REJECTED')
        request = _make_auth_request(
            self.factory, self.acc_auditor, self.prof_auditor, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        with self.assertRaises(HttpError) as ctx:
            update_expense_status(request, self.est.slug, self.expense.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cannot_approve_rejected(self):
        from treasury.api import update_expense_status, ExpenseStatusIn
        self.expense.status = 'REJECTED'
        self.expense.save()
        data = ExpenseStatusIn(status='APPROVED')
        request = _make_auth_request(
            self.factory, self.acc_auditor, self.prof_auditor, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        with self.assertRaises(HttpError) as ctx:
            update_expense_status(request, self.est.slug, self.expense.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_invalid_status_value(self):
        from treasury.api import update_expense_status, ExpenseStatusIn
        data = ExpenseStatusIn(status='PENDING')
        request = _make_auth_request(
            self.factory, self.acc_auditor, self.prof_auditor, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        with self.assertRaises(HttpError) as ctx:
            update_expense_status(request, self.est.slug, self.expense.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_approve_creates_audit_log(self):
        from treasury.api import update_expense_status, ExpenseStatusIn
        data = ExpenseStatusIn(status='APPROVED')
        request = _make_auth_request(
            self.factory, self.acc_auditor, self.prof_auditor, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        update_expense_status(request, self.est.slug, self.expense.id, data)
        log = TreasuryAuditLog.objects.filter(action='expense_approved').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.payload['new_status'], 'APPROVED')
        self.assertEqual(log.actor_id, self.prof_auditor.id)

    def test_approve_nonexistent(self):
        from treasury.api import update_expense_status, ExpenseStatusIn
        data = ExpenseStatusIn(status='APPROVED')
        request = _make_auth_request(
            self.factory, self.acc_auditor, self.prof_auditor, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        with self.assertRaises(HttpError) as ctx:
            update_expense_status(request, self.est.slug, 'NONEXISTENT_XYZ', data)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_admin_can_approve(self):
        from treasury.api import update_expense_status, ExpenseStatusIn
        acc_a = _create_account(self.instance, 'admin')
        prof_a = _create_profile(acc_a, self.instance, 'admin')
        _create_membership(prof_a, self.est, role='ADMIN', level='efetivo')
        data = ExpenseStatusIn(status='APPROVED')
        request = _make_auth_request(
            self.factory, acc_a, prof_a, method='put',
            data=json.dumps(data.dict()), path='/fake/'
        )
        result = update_expense_status(request, self.est.slug, self.expense.id, data)
        self.assertEqual(result.status, 'APPROVED')


class TestExpenseListEndpoint(TestCase):
    """Test expense listing with filters."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.acc = _create_account(self.instance, 'owner')
        self.prof = _create_profile(self.acc, self.instance)
        self.est = _create_treasury_establishment(self.prof)
        self.cats = _create_categories(self.est, 2)

        for i in range(3):
            Expense.objects.create(
                establishment=self.est, category=self.cats[0],
                created_by=self.prof, amount=Decimal(f'{(i + 1) * 100}'),
                description=f'Expense {i}', date=date(2026, 3, i + 1),
                status='DRAFT' if i < 2 else 'APPROVED',
                epoch_label='2026-03',
            )

    def test_list_all_expenses(self):
        from treasury.api import list_expenses
        request = self.factory.get('/fake/')
        result = list_expenses(request, self.est.slug)
        self.assertEqual(len(result), 3)

    def test_filter_by_status(self):
        from treasury.api import list_expenses
        request = self.factory.get('/fake/')
        result = list_expenses(request, self.est.slug, status='DRAFT')
        self.assertEqual(len(result), 2)

    def test_filter_by_epoch(self):
        from treasury.api import list_expenses
        Expense.objects.create(
            establishment=self.est, created_by=self.prof,
            amount=Decimal('50'), description='Old',
            date=date(2026, 2, 15), epoch_label='2026-02',
        )
        request = self.factory.get('/fake/')
        result = list_expenses(request, self.est.slug, epoch='2026-02')
        self.assertEqual(len(result), 1)

    def test_list_expenses_public(self):
        """Expenses are public (transparency)."""
        from treasury.api import list_expenses
        request = self.factory.get('/fake/')
        result = list_expenses(request, self.est.slug)
        self.assertTrue(len(result) > 0)
        self.assertEqual(result[0].object_type, 'treasury_expense')
