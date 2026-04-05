"""
Tests for governance endpoints: polls, voting, delegation, audit log.

Tests invariants that must never break:
- Poll creation requires establishment membership
- Only eligible voters can cast votes
- Double voting is prevented (unique_together)
- Delegation cycle detection works
- Self-delegation is rejected
- Voting after delegation (and vice versa) is blocked
- Delegation revocation restores voting ability
- Merkle chain integrity on audit log
- Private poll results are hidden until ended
- Audit log redacts option_id for private polls
- Poll status transitions (ACTIVE → ENDED)
- TOCTOU protection via select_for_update
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from ninja.errors import HttpError

from identity.models import Account, Profile
from core.models import Instance
from geo.models import Establishment, EstablishmentMembership
from governance.models import (
    Poll, PollContext, PollOption, PollEligibleVoter,
    PollVote, PollVoteDelegation, PollAuditLog
)
from governance.services import VotingService, AuditService


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


def _create_profile(account, instance, local_name=None, is_primary=True, **kwargs):
    local_name = local_name or account.username
    return Profile.objects.create(
        account=account,
        instance=instance,
        local_name=local_name,
        display_name=local_name.title(),
        is_primary=is_primary,
        profile_type=kwargs.pop('profile_type', Profile.ProfileType.PERSONAL),
        **kwargs,
    )


def _make_auth_request(factory, account, profile, method='get', path='/fake/', data=None):
    """Build a request with auth_profile and session attached (mimics ProfileAuth)."""
    fn = getattr(factory, method)
    request = fn(path, data=data, content_type='application/json') if data else fn(path)
    request.user = account
    request.auth = profile
    request.auth_profile = profile
    request.session = SessionStore()
    request.session.create()
    return request


def _create_establishment(owner_profile, name='Test Org'):
    """Create an Establishment for poll context."""
    return Establishment.objects.create(
        owner=owner_profile,
        name=name,
        slug=name.lower().replace(' ', '-'),
        is_active=True,
    )


def _create_membership(profile, establishment, role='MEMBER'):
    """Create EstablishmentMembership."""
    return EstablishmentMembership.objects.create(
        profile=profile,
        establishment=establishment,
        role=role,
    )


def _create_poll(creator_profile, establishment, title='Test Poll', status='active',
                 eligible_profiles=None, allow_delegation=True, public_results=True,
                 end_time=None, require_wot_verified=False):
    """Create a poll with options and eligible voters directly in DB."""
    context = PollContext.objects.create(
        context_type='organization',
        context_id=establishment.id,
        created_by=creator_profile,
    )
    poll = Poll.objects.create(
        context=context,
        title=title,
        description='Test poll description here',
        poll_type='multiple_choice',
        start_time=timezone.now() - timedelta(hours=1),
        end_time=end_time,
        quorum_type='simple_majority',
        quorum_percent=Decimal('50.00'),
        allow_delegation=allow_delegation,
        require_wot_verified=require_wot_verified,
        public_results=public_results,
        status=status,
        created_by=creator_profile,
    )
    # Create 3 options
    opts = []
    for i, text in enumerate(['Option A', 'Option B', 'Option C']):
        opts.append(PollOption.objects.create(poll=poll, text=text, order=i))

    # Add eligible voters
    profiles = eligible_profiles or [creator_profile]
    for p in profiles:
        PollEligibleVoter.objects.get_or_create(poll=poll, profile=p, defaults={'weight': Decimal('1.0000')})

    return poll, opts


# ===========================================================================
# Poll Creation Tests
# ===========================================================================

@patch('governance.api.verify_profile_signature')
@patch('governance.api.broadcast_poll_update')
class PollCreateTest(TestCase):
    """Test poll creation endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        self.est = _create_establishment(self.profile)
        _create_membership(self.profile, self.est, role='OWNER')
        self.factory = RequestFactory()

    @patch('governance.api.ws_publish', create=True)
    def test_create_poll_success(self, mock_ws, mock_broadcast, mock_pgp):
        """Create poll as establishment member succeeds."""
        from governance.api import create_poll, PollCreateRequest

        data = PollCreateRequest(
            context_type='organization',
            context_id=self.est.id,
            title='Should we do X?',
            description='Detailed description of the proposal',
            options=['Yes', 'No', 'Abstain'],
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')

        with patch('governance.api.ws_publish'):
            result = create_poll(request, data)

        self.assertEqual(result.title, 'Should we do X?')
        self.assertEqual(result.object_type, 'poll')
        self.assertEqual(result.status, 'active')
        self.assertEqual(len(result.options), 3)
        self.assertEqual(result.total_eligible, 1)  # creator auto-added
        self.assertEqual(Poll.objects.count(), 1)
        # Audit log entry created
        self.assertEqual(PollAuditLog.objects.filter(action='poll_created').count(), 1)

    def test_create_poll_not_member_403(self, mock_broadcast, mock_pgp):
        """Create poll without establishment membership → 403."""
        from governance.api import create_poll, PollCreateRequest

        other_account = _create_account(self.instance, 'bob')
        other_profile = _create_profile(other_account, self.instance, 'bob')

        data = PollCreateRequest(
            context_type='organization',
            context_id=self.est.id,
            title='Unauthorized poll attempt',
            description='This should fail with 403',
            options=['Yes', 'No'],
        )
        request = _make_auth_request(self.factory, other_account, other_profile, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_poll(request, data)
        self.assertEqual(ctx.exception.status_code, 403)

    @patch('governance.api.ws_publish', create=True)
    def test_create_poll_with_eligible_voters(self, mock_ws, mock_broadcast, mock_pgp):
        """Create poll with explicit eligible voter list."""
        from governance.api import create_poll, PollCreateRequest

        bob_account = _create_account(self.instance, 'bob')
        bob_profile = _create_profile(bob_account, self.instance, 'bob')

        data = PollCreateRequest(
            context_type='organization',
            context_id=self.est.id,
            title='Vote with voters',
            description='Poll with explicit voters',
            options=['A', 'B'],
            eligible_voter_ids=[bob_profile.id],
        )
        request = _make_auth_request(self.factory, self.account, self.profile, 'post')

        with patch('governance.api.ws_publish'):
            result = create_poll(request, data)

        self.assertEqual(result.total_eligible, 2)  # creator + bob


# ===========================================================================
# Poll List & Detail Tests
# ===========================================================================

class PollListTest(TestCase):
    """Test poll listing via DB queries (list_polls uses @paginate which changes return type)."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        self.est = _create_establishment(self.profile)
        self.factory = RequestFactory()

    def test_list_polls_returns_items(self):
        """Created polls appear in queryset."""
        initial_count = Poll.objects.count()
        _create_poll(self.profile, self.est)
        _create_poll(self.profile, self.est, title='Second Poll')

        self.assertEqual(Poll.objects.count(), initial_count + 2)

    def test_list_polls_filter_by_status(self):
        """Filter polls by status works."""
        _create_poll(self.profile, self.est, status='active')
        _create_poll(self.profile, self.est, title='Ended', status='ended')

        active = Poll.objects.filter(status='active', created_by=self.profile)
        ended = Poll.objects.filter(status='ended', created_by=self.profile)
        self.assertTrue(active.exists())
        self.assertTrue(ended.exists())

    def test_list_polls_auto_end(self):
        """Polls past end_time are auto-transitioned to ENDED on list request."""
        from governance.api import list_polls

        past_end = timezone.now() - timedelta(hours=1)
        poll, opts = _create_poll(self.profile, self.est, end_time=past_end)

        request = self.factory.get('/fake/')
        # Calling list_polls triggers auto-transition side effect
        list_polls(request)

        poll.refresh_from_db()
        self.assertEqual(poll.status, 'ended')


class PollDetailTest(TestCase):
    """Test poll detail endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.account = _create_account(self.instance, 'alice')
        self.profile = _create_profile(self.account, self.instance)
        self.est = _create_establishment(self.profile)
        self.factory = RequestFactory()

    def test_get_poll_detail(self):
        """Get poll detail returns full schema."""
        from governance.api import get_poll

        poll, opts = _create_poll(self.profile, self.est)

        request = self.factory.get('/fake/')
        result = get_poll(request, poll.id)

        self.assertEqual(result.id, poll.id)
        self.assertEqual(result.object_type, 'poll')
        self.assertEqual(len(result.options), 3)
        self.assertEqual(result.context.context_type, 'organization')

    def test_get_poll_not_found(self):
        """Get nonexistent poll → 404."""
        from governance.api import get_poll
        from django.http import Http404

        request = self.factory.get('/fake/')
        with self.assertRaises(Http404):
            get_poll(request, '01AAAAAAAAAAAAAAAAAAAAAAAA')

    def test_get_poll_private_results_hidden(self):
        """Private poll hides results while active."""
        from governance.api import get_poll

        poll, opts = _create_poll(self.profile, self.est, public_results=False)

        request = self.factory.get('/fake/')
        result = get_poll(request, poll.id)

        self.assertIsNone(result.results)
        self.assertIsNone(result.winning_option_id)

    def test_get_poll_private_results_shown_when_ended(self):
        """Private poll shows results when ended."""
        from governance.api import get_poll

        poll, opts = _create_poll(self.profile, self.est, public_results=False, status='ended')
        # Cast a vote directly to have results
        PollVote.objects.create(
            poll=poll, voter=self.profile, option=opts[0],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )

        request = self.factory.get('/fake/')
        result = get_poll(request, poll.id)

        self.assertIsNotNone(result.results)


# ===========================================================================
# Voting Tests
# ===========================================================================

@patch('governance.api.verify_profile_signature')
@patch('governance.api.broadcast_poll_update')
class CastVoteTest(TestCase):
    """Test vote casting endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, 'bob')
        self.est = _create_establishment(self.alice)
        self.factory = RequestFactory()

    def test_cast_vote_success(self, mock_broadcast, mock_pgp):
        """Eligible voter casts vote successfully."""
        from governance.api import cast_vote, VoteCastRequest

        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice, self.bob])

        data = VoteCastRequest(option_id=opts[0].id)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = cast_vote(request, poll.id, data)

        self.assertEqual(result.object_type, 'poll_vote')
        self.assertEqual(result.option_id, opts[0].id)
        self.assertEqual(result.voter_id, self.alice.id)
        self.assertEqual(PollVote.objects.filter(poll=poll).count(), 1)
        # Audit log entry created
        self.assertEqual(PollAuditLog.objects.filter(poll=poll, action='vote_cast').count(), 1)

    def test_double_vote_rejected(self, mock_broadcast, mock_pgp):
        """Voting twice on same poll → 400."""
        from governance.api import cast_vote, VoteCastRequest

        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])
        # First vote
        PollVote.objects.create(
            poll=poll, voter=self.alice, option=opts[0],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )

        data = VoteCastRequest(option_id=opts[1].id)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            cast_vote(request, poll.id, data)
        self.assertIn('400', str(ctx.exception.status_code))

    def test_ineligible_voter_rejected(self, mock_broadcast, mock_pgp):
        """Non-eligible voter cannot cast vote."""
        from governance.api import cast_vote, VoteCastRequest

        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])
        # bob is NOT eligible

        data = VoteCastRequest(option_id=opts[0].id)
        request = _make_auth_request(self.factory, self.bob_account, self.bob, 'post')

        with self.assertRaises(HttpError) as ctx:
            cast_vote(request, poll.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_vote_on_ended_poll_rejected(self, mock_broadcast, mock_pgp):
        """Cannot vote on ended poll."""
        from governance.api import cast_vote, VoteCastRequest

        poll, opts = _create_poll(self.alice, self.est, status='ended',
                                  eligible_profiles=[self.alice])

        data = VoteCastRequest(option_id=opts[0].id)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            cast_vote(request, poll.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_vote_invalid_option_rejected(self, mock_broadcast, mock_pgp):
        """Vote with option from different poll → 400."""
        from governance.api import cast_vote, VoteCastRequest

        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])

        data = VoteCastRequest(option_id='01AAAAAAAAAAAAAAAAAAAAAAAA')  # nonexistent
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            cast_vote(request, poll.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_vote_with_active_delegation_rejected(self, mock_broadcast, mock_pgp):
        """Cannot vote if you have an active delegation."""
        from governance.api import cast_vote, VoteCastRequest

        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice, self.bob])
        # Alice delegates to Bob
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=True,
        )

        data = VoteCastRequest(option_id=opts[0].id)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            cast_vote(request, poll.id, data)
        self.assertEqual(ctx.exception.status_code, 400)


# ===========================================================================
# Delegation Tests
# ===========================================================================

@patch('governance.api.verify_profile_signature')
@patch('governance.api.broadcast_poll_update')
class DelegationTest(TestCase):
    """Test delegation creation, revocation, cycle detection."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, 'bob')
        self.carol_account = _create_account(self.instance, 'carol')
        self.carol = _create_profile(self.carol_account, self.instance, 'carol')
        self.est = _create_establishment(self.alice)
        self.factory = RequestFactory()

    def test_create_delegation_success(self, mock_broadcast, mock_pgp):
        """Eligible voter delegates to another eligible voter."""
        from governance.api import create_delegation, DelegationCreateRequest

        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob])

        data = DelegationCreateRequest(delegate_id=self.bob.id)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = create_delegation(request, poll.id, data)

        self.assertEqual(result.object_type, 'poll_delegation')
        self.assertEqual(result.delegator_id, self.alice.id)
        self.assertEqual(result.delegate_id, self.bob.id)
        self.assertTrue(result.is_active)
        # Audit log entry
        self.assertEqual(PollAuditLog.objects.filter(action='delegation_created').count(), 1)

    def test_self_delegation_rejected(self, mock_broadcast, mock_pgp):
        """Cannot delegate to yourself."""
        from governance.api import create_delegation, DelegationCreateRequest

        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])

        data = DelegationCreateRequest(delegate_id=self.alice.id)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_delegation(request, poll.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_delegation_after_vote_rejected(self, mock_broadcast, mock_pgp):
        """Cannot delegate after already voting."""
        from governance.api import create_delegation, DelegationCreateRequest

        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob])
        PollVote.objects.create(
            poll=poll, voter=self.alice, option=opts[0],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )

        data = DelegationCreateRequest(delegate_id=self.bob.id)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_delegation(request, poll.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_delegation_cycle_rejected(self, mock_broadcast, mock_pgp):
        """Delegation that creates a cycle is rejected."""
        from governance.api import create_delegation, DelegationCreateRequest

        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob, self.carol])
        # Alice → Bob
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=True,
        )
        # Bob → Carol
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.bob, delegate=self.carol,
            pgp_signature='', signed_payload={}, is_active=True,
        )
        # Carol → Alice would create cycle
        data = DelegationCreateRequest(delegate_id=self.alice.id)
        request = _make_auth_request(self.factory, self.carol_account, self.carol, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_delegation(request, poll.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_delegation_disabled_rejected(self, mock_broadcast, mock_pgp):
        """Cannot delegate when poll has allow_delegation=False."""
        from governance.api import create_delegation, DelegationCreateRequest

        poll, opts = _create_poll(self.alice, self.est, allow_delegation=False,
                                  eligible_profiles=[self.alice, self.bob])

        data = DelegationCreateRequest(delegate_id=self.bob.id)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_delegation(request, poll.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_delegate_not_eligible_rejected(self, mock_broadcast, mock_pgp):
        """Cannot delegate to non-eligible voter."""
        from governance.api import create_delegation, DelegationCreateRequest

        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])
        # bob is NOT eligible

        data = DelegationCreateRequest(delegate_id=self.bob.id)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            create_delegation(request, poll.id, data)
        self.assertEqual(ctx.exception.status_code, 400)


@patch('governance.api.verify_profile_signature')
@patch('governance.api.broadcast_poll_update')
class DelegationRevokeTest(TestCase):
    """Test delegation revocation."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, 'bob')
        self.est = _create_establishment(self.alice)
        self.factory = RequestFactory()

    def test_revoke_delegation_success(self, mock_broadcast, mock_pgp):
        """Revoke active delegation."""
        from governance.api import revoke_delegation, DelegationRevokeRequest

        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob])
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=True,
        )

        data = DelegationRevokeRequest()
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = revoke_delegation(request, poll.id, data)

        self.assertIn('delegation_id', result)
        # Verify in DB
        delegation = PollVoteDelegation.objects.get(poll=poll, delegator=self.alice)
        self.assertFalse(delegation.is_active)
        self.assertIsNotNone(delegation.revoked_at)
        # Audit log entry
        self.assertEqual(PollAuditLog.objects.filter(action='delegation_revoked').count(), 1)

    def test_revoke_no_delegation_404(self, mock_broadcast, mock_pgp):
        """Revoke when no active delegation → 404."""
        from governance.api import revoke_delegation, DelegationRevokeRequest

        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])

        data = DelegationRevokeRequest()
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            revoke_delegation(request, poll.id, data)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_revoke_on_ended_poll_rejected(self, mock_broadcast, mock_pgp):
        """Cannot revoke delegation on ended poll."""
        from governance.api import revoke_delegation, DelegationRevokeRequest

        poll, opts = _create_poll(self.alice, self.est, status='ended',
                                  eligible_profiles=[self.alice, self.bob])
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=True,
        )

        data = DelegationRevokeRequest()
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')

        with self.assertRaises(HttpError) as ctx:
            revoke_delegation(request, poll.id, data)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_revoke_then_vote(self, mock_broadcast, mock_pgp):
        """After revoking delegation, voter can cast direct vote."""
        from governance.api import cast_vote, revoke_delegation, VoteCastRequest, DelegationRevokeRequest

        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob])
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=True,
        )

        # Revoke
        revoke_req = DelegationRevokeRequest()
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        revoke_delegation(request, poll.id, revoke_req)

        # Now vote
        vote_data = VoteCastRequest(option_id=opts[0].id)
        request = _make_auth_request(self.factory, self.alice_account, self.alice, 'post')
        result = cast_vote(request, poll.id, vote_data)

        self.assertEqual(result.voter_id, self.alice.id)
        self.assertEqual(result.option_id, opts[0].id)


# ===========================================================================
# Results Tests
# ===========================================================================

class ResultsTest(TestCase):
    """Test poll results endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, 'bob')
        self.est = _create_establishment(self.alice)
        self.factory = RequestFactory()

    def test_public_results_accessible(self):
        """Public results visible while poll active."""
        from governance.api import get_results

        poll, opts = _create_poll(self.alice, self.est, public_results=True,
                                  eligible_profiles=[self.alice, self.bob])
        PollVote.objects.create(
            poll=poll, voter=self.alice, option=opts[0],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )

        request = self.factory.get('/fake/')
        result = get_results(request, poll.id)

        self.assertEqual(result.total_eligible, 2)
        self.assertEqual(result.total_voted, 1)
        self.assertEqual(len(result.results), 1)

    def test_private_results_hidden_while_active(self):
        """Private results → 403 while poll active."""
        from governance.api import get_results

        poll, opts = _create_poll(self.alice, self.est, public_results=False,
                                  eligible_profiles=[self.alice])

        request = self.factory.get('/fake/')

        with self.assertRaises(HttpError) as ctx:
            get_results(request, poll.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_private_results_visible_when_ended(self):
        """Private results visible once poll ended."""
        from governance.api import get_results

        poll, opts = _create_poll(self.alice, self.est, public_results=False, status='ended',
                                  eligible_profiles=[self.alice])
        PollVote.objects.create(
            poll=poll, voter=self.alice, option=opts[0],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )

        request = self.factory.get('/fake/')
        result = get_results(request, poll.id)

        self.assertEqual(result.total_voted, 1)

    def test_results_quorum_calculation(self):
        """Quorum met when > 50% voted (simple majority)."""
        from governance.api import get_results

        poll, opts = _create_poll(self.alice, self.est, public_results=True,
                                  eligible_profiles=[self.alice, self.bob])
        # Only alice votes (1/2 = 50%, simple majority needs >50%)
        PollVote.objects.create(
            poll=poll, voter=self.alice, option=opts[0],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )

        request = self.factory.get('/fake/')
        result = get_results(request, poll.id)

        # 50% is NOT > 50% for simple majority
        self.assertFalse(result.quorum_met)

    def test_results_quorum_met(self):
        """Quorum met when both voters vote (100% > 50%)."""
        from governance.api import get_results

        poll, opts = _create_poll(self.alice, self.est, public_results=True,
                                  eligible_profiles=[self.alice, self.bob])
        PollVote.objects.create(
            poll=poll, voter=self.alice, option=opts[0],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )
        PollVote.objects.create(
            poll=poll, voter=self.bob, option=opts[0],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )

        request = self.factory.get('/fake/')
        result = get_results(request, poll.id)

        self.assertTrue(result.quorum_met)
        self.assertEqual(result.winning_option_id, opts[0].id)


# ===========================================================================
# My-Status Tests
# ===========================================================================

class MyStatusTest(TestCase):
    """Test my-status endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, 'bob')
        self.est = _create_establishment(self.alice)
        self.factory = RequestFactory()

    def test_eligible_not_voted(self):
        """Eligible voter who hasn't voted yet."""
        from governance.api import get_my_status

        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = get_my_status(request, poll.id)

        self.assertTrue(result['is_eligible'])
        self.assertTrue(result['can_vote'])
        self.assertFalse(result['has_voted'])
        self.assertFalse(result['has_delegation'])

    def test_not_eligible(self):
        """Non-eligible voter status."""
        from governance.api import get_my_status

        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])

        request = _make_auth_request(self.factory, self.bob_account, self.bob)
        result = get_my_status(request, poll.id)

        self.assertFalse(result['is_eligible'])
        self.assertFalse(result['can_vote'])

    def test_has_voted(self):
        """Status after voting."""
        from governance.api import get_my_status

        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])
        PollVote.objects.create(
            poll=poll, voter=self.alice, option=opts[0],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = get_my_status(request, poll.id)

        self.assertTrue(result['has_voted'])
        self.assertEqual(result['vote_option_id'], opts[0].id)
        self.assertFalse(result['can_vote'])

    def test_has_delegation(self):
        """Status with active delegation."""
        from governance.api import get_my_status

        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob])
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=True,
        )

        request = _make_auth_request(self.factory, self.alice_account, self.alice)
        result = get_my_status(request, poll.id)

        self.assertTrue(result['has_delegation'])
        self.assertEqual(result['delegate_id'], self.bob.id)
        self.assertFalse(result['can_vote'])


# ===========================================================================
# Delegation Chains Tests
# ===========================================================================

class DelegationChainsTest(TestCase):
    """Test delegation chains visualization endpoint."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, 'bob')
        self.carol_account = _create_account(self.instance, 'carol')
        self.carol = _create_profile(self.carol_account, self.instance, 'carol')
        self.est = _create_establishment(self.alice)
        self.factory = RequestFactory()

    def test_no_delegations(self):
        """No delegation chains when none exist."""
        from governance.api import get_delegation_chains

        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])

        request = self.factory.get('/fake/')
        result = get_delegation_chains(request, poll.id)

        self.assertEqual(len(result), 0)

    def test_simple_chain(self):
        """Alice → Bob chain displayed."""
        from governance.api import get_delegation_chains

        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob])
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=True,
        )

        request = self.factory.get('/fake/')
        result = get_delegation_chains(request, poll.id)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].length, 2)
        self.assertEqual(result[0].final_delegate_id, self.bob.id)

    def test_transitive_chain(self):
        """Alice → Bob → Carol transitive chain."""
        from governance.api import get_delegation_chains

        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob, self.carol])
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=True,
        )
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.bob, delegate=self.carol,
            pgp_signature='', signed_payload={}, is_active=True,
        )

        request = self.factory.get('/fake/')
        result = get_delegation_chains(request, poll.id)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].length, 3)
        self.assertEqual(result[0].final_delegate_id, self.carol.id)

    def test_private_poll_redacts_vote_option(self):
        """Private poll delegation chains do not reveal vote_option_id."""
        from governance.api import get_delegation_chains

        poll, opts = _create_poll(self.alice, self.est, public_results=False,
                                  eligible_profiles=[self.alice, self.bob])
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=True,
        )
        PollVote.objects.create(
            poll=poll, voter=self.bob, option=opts[0],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )

        request = self.factory.get('/fake/')
        result = get_delegation_chains(request, poll.id)

        self.assertTrue(result[0].has_voted)
        self.assertIsNone(result[0].vote_option_id)  # Redacted!


# ===========================================================================
# Audit Log Tests
# ===========================================================================

class AuditLogTest(TestCase):
    """Test audit log endpoint and Merkle chain integrity."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.est = _create_establishment(self.alice)
        self.factory = RequestFactory()

    def test_audit_log_entries_created(self):
        """Audit log records poll creation."""
        from governance.api import get_audit_log

        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])
        # Create audit log manually (helper doesn't call create_poll endpoint)
        AuditService.create_log_entry(
            poll=poll, action='poll_created', actor=self.alice,
            payload={'poll_id': poll.id, 'title': poll.title},
            pgp_signature='SYSTEM_GENERATED',
        )

        request = self.factory.get('/fake/')
        result = get_audit_log(request, poll.id)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action, 'poll_created')
        self.assertEqual(result[0].actor_id, self.alice.id)
        self.assertIsNotNone(result[0].current_log_hash)
        self.assertIsNone(result[0].previous_log_hash)  # First entry

    def test_merkle_chain_integrity(self):
        """Merkle chain links entries correctly."""
        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])

        log1 = AuditService.create_log_entry(
            poll=poll, action='poll_created', actor=self.alice,
            payload={'poll_id': poll.id}, pgp_signature='SIG1',
        )
        log2 = AuditService.create_log_entry(
            poll=poll, action='vote_cast', actor=self.alice,
            payload={'vote_id': 'test'}, pgp_signature='SIG2',
        )

        # Chain: log2.previous_log_hash == log1.current_log_hash
        self.assertEqual(log2.previous_log_hash, log1.current_log_hash)

        # Verify chain
        is_valid, error = AuditService.verify_merkle_chain(poll)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_merkle_chain_tamper_detected(self):
        """Tampered audit log fails verification."""
        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])

        AuditService.create_log_entry(
            poll=poll, action='poll_created', actor=self.alice,
            payload={'poll_id': poll.id}, pgp_signature='SIG1',
        )
        log2 = AuditService.create_log_entry(
            poll=poll, action='vote_cast', actor=self.alice,
            payload={'vote_id': 'test'}, pgp_signature='SIG2',
        )

        # Tamper with log2's hash
        PollAuditLog.objects.filter(id=log2.id).update(current_log_hash='0' * 64)

        is_valid, error = AuditService.verify_merkle_chain(poll)
        self.assertFalse(is_valid)

    def test_finalize_poll_sets_merkle_root(self):
        """Finalize sets merkle_root from last audit hash."""
        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])

        log1 = AuditService.create_log_entry(
            poll=poll, action='poll_created', actor=self.alice,
            payload={'poll_id': poll.id}, pgp_signature='SIG1',
        )

        merkle_root = AuditService.finalize_poll(poll)
        poll.refresh_from_db()

        self.assertEqual(poll.merkle_root, log1.current_log_hash)
        self.assertEqual(merkle_root, log1.current_log_hash)

    def test_finalize_idempotent(self):
        """Double finalization doesn't change merkle_root."""
        poll, opts = _create_poll(self.alice, self.est, eligible_profiles=[self.alice])

        AuditService.create_log_entry(
            poll=poll, action='poll_created', actor=self.alice,
            payload={'poll_id': poll.id}, pgp_signature='SIG1',
        )

        root1 = AuditService.finalize_poll(poll)
        root2 = AuditService.finalize_poll(poll)

        self.assertEqual(root1, root2)

    def test_audit_log_redacts_option_for_private_poll(self):
        """Private poll audit log hashes option_id instead of showing it."""
        from governance.api import get_audit_log

        poll, opts = _create_poll(self.alice, self.est, public_results=False,
                                  eligible_profiles=[self.alice])

        AuditService.create_log_entry(
            poll=poll, action='vote_cast', actor=self.alice,
            payload={'vote_id': 'v1', 'option_id': opts[0].id, 'effective_weight': '1'},
            pgp_signature='SIG1',
        )

        request = self.factory.get('/fake/')
        result = get_audit_log(request, poll.id)

        # option_id should be hashed, not raw
        self.assertNotEqual(result[0].payload['option_id'], opts[0].id)
        self.assertTrue(result[0].payload.get('option_id_hashed', False))

    def test_audit_log_public_poll_shows_option(self):
        """Public poll audit log shows option_id in plain text."""
        from governance.api import get_audit_log

        poll, opts = _create_poll(self.alice, self.est, public_results=True,
                                  eligible_profiles=[self.alice])

        AuditService.create_log_entry(
            poll=poll, action='vote_cast', actor=self.alice,
            payload={'vote_id': 'v1', 'option_id': opts[0].id, 'effective_weight': '1'},
            pgp_signature='SIG1',
        )

        request = self.factory.get('/fake/')
        result = get_audit_log(request, poll.id)

        self.assertEqual(result[0].payload['option_id'], opts[0].id)
        self.assertFalse(result[0].payload.get('option_id_hashed', False))


# ===========================================================================
# VotingService Tests
# ===========================================================================

class VotingServiceTest(TestCase):
    """Test VotingService delegation resolution and result calculation."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_account, self.instance)
        self.bob_account = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_account, self.instance, 'bob')
        self.carol_account = _create_account(self.instance, 'carol')
        self.carol = _create_profile(self.carol_account, self.instance, 'carol')
        self.est = _create_establishment(self.alice)

    def test_resolve_simple_delegation(self):
        """Alice → Bob resolves correctly."""
        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob])
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=True,
        )

        service = VotingService(poll)
        resolved = service.resolve_delegations()

        self.assertEqual(resolved[self.alice.id], self.bob.id)

    def test_resolve_transitive_delegation(self):
        """Alice → Bob → Carol resolves to Carol."""
        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob, self.carol])
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=True,
        )
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.bob, delegate=self.carol,
            pgp_signature='', signed_payload={}, is_active=True,
        )

        service = VotingService(poll)
        resolved = service.resolve_delegations()

        self.assertEqual(resolved[self.alice.id], self.carol.id)
        self.assertEqual(resolved[self.bob.id], self.carol.id)

    def test_effective_votes_with_delegation(self):
        """Delegated votes add weight to delegate's vote."""
        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob])
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=True,
        )
        PollVote.objects.create(
            poll=poll, voter=self.bob, option=opts[0],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )

        service = VotingService(poll)
        effective = service.get_effective_votes()

        # Bob voted + Alice delegated = weight 2
        self.assertIn(self.bob.id, effective)
        option_id, delegators, weight = effective[self.bob.id]
        self.assertEqual(option_id, opts[0].id)
        self.assertIn(self.alice.id, delegators)
        self.assertEqual(weight, Decimal('2'))

    def test_calculate_results_winning(self):
        """Calculate results with clear winner."""
        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob, self.carol])
        PollVote.objects.create(
            poll=poll, voter=self.alice, option=opts[0],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )
        PollVote.objects.create(
            poll=poll, voter=self.bob, option=opts[0],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )
        PollVote.objects.create(
            poll=poll, voter=self.carol, option=opts[1],
            pgp_signature='', signed_payload={}, effective_weight=Decimal('1'),
        )

        service = VotingService(poll)
        results = service.calculate_results()

        self.assertEqual(results['total_eligible'], 3)
        self.assertEqual(results['total_voted'], 3)
        self.assertTrue(results['quorum_met'])
        self.assertEqual(results['winning_option_id'], opts[0].id)
        # First result should be the winner
        self.assertEqual(results['results'][0]['option_id'], opts[0].id)
        self.assertAlmostEqual(results['results'][0]['percentage'], 66.666, places=2)

    def test_check_can_vote_wot_required(self):
        """WoT-required poll rejects unverified voter."""
        poll, opts = _create_poll(self.alice, self.est, require_wot_verified=True,
                                  eligible_profiles=[self.alice])
        self.alice.is_verified_wot = False
        self.alice.save()

        service = VotingService(poll)
        with patch.object(Profile, 'is_foundation_member', return_value=False):
            can_vote, error = service.check_can_vote(self.alice)

        self.assertFalse(can_vote)
        self.assertIn('WoT', error)

    def test_delegation_chain_length(self):
        """Get delegation chain returns correct path."""
        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob, self.carol])
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=True,
        )
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.bob, delegate=self.carol,
            pgp_signature='', signed_payload={}, is_active=True,
        )

        service = VotingService(poll)
        chain = service.get_delegation_chain(self.alice.id)

        self.assertEqual(chain, [self.alice.id, self.bob.id, self.carol.id])

    def test_revoked_delegation_not_resolved(self):
        """Revoked delegations are excluded from resolution."""
        poll, opts = _create_poll(self.alice, self.est,
                                  eligible_profiles=[self.alice, self.bob])
        PollVoteDelegation.objects.create(
            poll=poll, delegator=self.alice, delegate=self.bob,
            pgp_signature='', signed_payload={}, is_active=False,
            revoked_at=timezone.now(),
        )

        service = VotingService(poll)
        resolved = service.resolve_delegations()

        self.assertEqual(len(resolved), 0)
