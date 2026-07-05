"""
Tests for civic opinion polls (PK/civic-polls-system.md).

Invariants that must never break:
- voter_token is stable per (profile, poll) and never collides across polls
- OpinionVote rows carry no profile linkage (pseudonymization)
- Consent gate (422), scope gate (403), country account-age gate (403), cooldown (429)
- Hide-until-vote: eligible non-voters see participation only
- Quantization below CIVIC_LIVE_THRESHOLD: no exact counts, percent step 10
- k>=5 territorial breakdown gating
- Erasure round-trip removes votes, heals aggregates, keeps Merkle chain valid
- freeze_and_purge drops raw rows and serves frozen aggregates
- Merkle chain verifies with mixed identified + NULL-actor entries
- Feed scoping follows the residency chain
- Territory poll creation is staff-only (MVP)
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone
from ninja.errors import HttpError

from identity.models import Account, Profile
from core.models import Instance
from geo.models import Territory
from governance.models import Poll, PollContext, PollOption, OpinionVote, PollAuditLog
from governance.services import AuditService
from governance import civic
from governance.civic_api import civic_feed


TEST_SECRET = 'test-civic-secret-do-not-use'


def _mk_account(instance, username):
    return Account.objects.create_user(
        username=username, email=f'{username}@test.parahub.io',
        password='testpass123', instance=instance,
    )


def _mk_profile(account, instance):
    return Profile.objects.create(
        account=account, instance=instance, local_name=account.username,
        display_name=account.username.title(), is_primary=True,
        profile_type=Profile.ProfileType.PERSONAL,
    )


@override_settings(CIVIC_VOTE_SECRET=TEST_SECRET)
class CivicPollTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test Instance', public_key='test-key')

        # Synthetic territory fixture (codes are test-local, not reference data)
        cls.pt = Territory.objects.create(country='PT', level='country', code='PT', name='Portugal')
        cls.region = Territory.objects.create(
            country='PT', level='region', code='PT11', name='Norte', parent=cls.pt)
        cls.muni_a = Territory.objects.create(
            country='PT', level='municipality', code='9901', name='Test Muni A', parent=cls.region)
        cls.muni_b = Territory.objects.create(
            country='PT', level='municipality', code='9902', name='Test Muni B', parent=cls.region)
        cls.parish_a = Territory.objects.create(
            country='PT', level='parish', code='990101', name='Test Parish A', parent=cls.muni_a)
        cls.parish_b = Territory.objects.create(
            country='PT', level='parish', code='990201', name='Test Parish B', parent=cls.muni_b)

    def setUp(self):
        self.factory = RequestFactory()
        self._redis_polls = []
        self.alice = self._citizen('alice', self.parish_a)
        self.bob = self._citizen('bob', self.parish_a)

    def tearDown(self):
        r = civic._redis()
        for poll_id in self._redis_polls:
            for code in r.smembers(f"civic:{poll_id}:terrs"):
                r.delete(f"civic:{poll_id}:terr:{code}")
            r.delete(f"civic:{poll_id}:counts", f"civic:{poll_id}:counts_v",
                     f"civic:{poll_id}:terrs", f"civic:{poll_id}:ws")

    # ------------------------------------------------------------------ helpers

    def _citizen(self, username, parish, consent=True, verified=False):
        account = _mk_account(self.instance, username)
        profile = _mk_profile(account, self.instance)
        profile.residency_territory = parish
        profile.civic_opinion_consent = consent
        profile.civic_opinion_consent_at = timezone.now() if consent else None
        profile.is_verified_wot = verified
        profile.save()
        # Country-age gate is tested explicitly; other tests use aged accounts
        account.date_joined = timezone.now() - timedelta(days=30)
        account.save(update_fields=['date_joined'])
        return profile

    def _opinion_poll(self, territory, title='Civic test poll', options=('For', 'Against', 'Undecided')):
        ctx = PollContext.objects.create(
            context_type=PollContext.ContextType.TERRITORY,
            context_id=territory.id, created_by=self.alice)
        poll = Poll.objects.create(
            context=ctx, title=title, description='test', start_time=timezone.now(),
            poll_class=Poll.PollClass.OPINION, ballot_mode=Poll.BallotMode.ANONYMOUS,
            allow_delegation=False, status=Poll.Status.ACTIVE, created_by=self.alice)
        for i, text in enumerate(options):
            PollOption.objects.create(poll=poll, text=text, order=i)
        self._redis_polls.append(poll.id)
        return poll

    def _vote(self, poll, profile, option):
        civic._redis().delete(f"civic:cd:{poll.id}:{profile.id}")
        # TestCase wraps tests in a never-committed transaction, so transaction.on_commit
        # (Redis delta + WS broadcast) must be executed explicitly
        with self.captureOnCommitCallbacks(execute=True):
            return civic.cast_opinion_vote(poll, profile, option)

    # ------------------------------------------------------------------ tokens & rows

    def test_voter_token_stable_and_distinct(self):
        poll = self._opinion_poll(self.muni_a)
        poll2 = self._opinion_poll(self.muni_a)
        t1 = civic.voter_token(self.alice.id, poll.id)
        self.assertEqual(t1, civic.voter_token(self.alice.id, poll.id))
        self.assertNotEqual(t1, civic.voter_token(self.bob.id, poll.id))
        self.assertNotEqual(t1, civic.voter_token(self.alice.id, poll2.id))
        self.assertEqual(len(t1), 64)

    def test_vote_row_is_pseudonymous(self):
        poll = self._opinion_poll(self.muni_a)
        option = poll.options.first()
        res = self._vote(poll, self.alice, option)
        row = OpinionVote.objects.get(poll=poll)
        self.assertNotIn(self.alice.id, str(row.payload))
        self.assertEqual(row.voter_territory, self.muni_a.code)  # coarsened to municipality
        self.assertFalse(hasattr(row, 'voter_id'))
        self.assertTrue(res['receipt'])

    def test_residency_chain_and_coarsening(self):
        chain = civic.residency_chain(self.alice)
        self.assertEqual([t.level for t in chain], ['parish', 'municipality', 'region', 'country'])
        self.assertEqual(civic.municipality_code(chain), self.muni_a.code)
        # Country fallback via country_code
        nomad = self._citizen('nomad', None)
        nomad.residency_territory = None
        nomad.country_code = 'PT'
        nomad.save()
        chain = civic.residency_chain(nomad)
        self.assertEqual([t.level for t in chain], ['country'])

    # ------------------------------------------------------------------ gates

    def test_consent_gate(self):
        poll = self._opinion_poll(self.muni_a)
        noconsent = self._citizen('carol', self.parish_a, consent=False)
        with self.assertRaises(civic.CivicVoteError) as ctx:
            self._vote(poll, noconsent, poll.options.first())
        self.assertEqual(ctx.exception.status, 422)

    def test_scope_gate(self):
        poll = self._opinion_poll(self.muni_a)
        outsider = self._citizen('dave', self.parish_b)  # muni B resident, muni A poll
        with self.assertRaises(civic.CivicVoteError) as ctx:
            self._vote(poll, outsider, poll.options.first())
        self.assertEqual(ctx.exception.status, 403)
        # But region/country polls accept both
        region_poll = self._opinion_poll(self.region)
        self.assertTrue(self._vote(region_poll, outsider, region_poll.options.first())['receipt'])

    def test_country_account_age_gate(self):
        poll = self._opinion_poll(self.pt)
        fresh = self._citizen('eve', self.parish_a)
        fresh.account.date_joined = timezone.now()
        fresh.account.save(update_fields=['date_joined'])
        with self.assertRaises(civic.CivicVoteError) as ctx:
            self._vote(poll, fresh, poll.options.first())
        self.assertEqual(ctx.exception.status, 403)
        with override_settings(CIVIC_COUNTRY_MIN_ACCOUNT_AGE_DAYS=0):
            self.assertTrue(self._vote(poll, fresh, poll.options.first())['receipt'])

    def test_cooldown_and_revote(self):
        poll = self._opinion_poll(self.muni_a)
        o1, o2 = list(poll.options.all())[:2]
        self._vote(poll, self.alice, o1)
        with self.assertRaises(civic.CivicVoteError) as ctx:
            civic.cast_opinion_vote(poll, self.alice, o2)  # no cooldown reset
        self.assertEqual(ctx.exception.status, 429)
        res = self._vote(poll, self.alice, o2)  # cooldown cleared by helper
        self.assertTrue(res['changed'])
        self.assertEqual(res['n'], 1)  # re-vote, not a second voice
        row = OpinionVote.objects.get(poll=poll)
        self.assertEqual(row.payload['option'], o2.id)

    def test_wot_required_gate(self):
        poll = self._opinion_poll(self.muni_a)
        poll.require_wot_verified = True
        poll.save(update_fields=['require_wot_verified'])
        with self.assertRaises(civic.CivicVoteError) as ctx:
            self._vote(poll, self.alice, poll.options.first())
        self.assertEqual(ctx.exception.status, 403)
        verified = self._citizen('vera', self.parish_a, verified=True)
        self.assertTrue(self._vote(poll, verified, poll.options.first())['receipt'])

    # ------------------------------------------------------------------ results visibility

    def test_hide_until_vote(self):
        poll = self._opinion_poll(self.muni_a)
        self._vote(poll, self.alice, poll.options.first())
        # Voter sees distribution
        self.assertFalse(civic.get_opinion_results(poll, self.alice)['hidden'])
        # Eligible non-voter sees participation only
        res_bob = civic.get_opinion_results(poll, self.bob)
        self.assertTrue(res_bob['hidden'])
        self.assertIsNone(res_bob['options'])
        self.assertEqual(res_bob['n_display'], '<5')
        # Anonymous / out-of-scope viewers see the distribution
        self.assertFalse(civic.get_opinion_results(poll, None)['hidden'])
        outsider = self._citizen('frank', self.parish_b)
        self.assertFalse(civic.get_opinion_results(poll, outsider)['hidden'])
        # After end everyone sees
        poll.status = Poll.Status.ENDED
        poll.save(update_fields=['status'])
        self.assertFalse(civic.get_opinion_results(poll, self.bob)['hidden'])

    @override_settings(CIVIC_LIVE_THRESHOLD=3)
    def test_quantization_threshold(self):
        poll = self._opinion_poll(self.muni_a)
        o1 = poll.options.first()
        self._vote(poll, self.alice, o1)
        res = civic.get_opinion_results(poll, self.alice)
        self.assertTrue(res['quantized'])
        self.assertIsNone(res['n'])
        self.assertIsNone(res['options'][0]['count'])
        self.assertEqual(res['options'][0]['percent'] % 10, 0)
        self.assertIsNone(res['by_territory'])
        # Cross the threshold
        self._vote(poll, self.bob, o1)
        third = self._citizen('gina', self.parish_a)
        self._vote(poll, third, o1)
        res = civic.get_opinion_results(poll, self.alice)
        self.assertFalse(res['quantized'])
        self.assertEqual(res['n'], 3)
        self.assertEqual(res['options'][0]['count'], 3)

    @override_settings(CIVIC_LIVE_THRESHOLD=3)
    def test_breakdown_k_gating(self):
        poll = self._opinion_poll(self.region)
        o1 = poll.options.first()
        # 5 voters from muni A, 2 from muni B
        for i in range(5):
            voter = self._citizen(f'a{i}', self.parish_a)
            self._vote(poll, voter, o1)
        for i in range(2):
            voter = self._citizen(f'b{i}', self.parish_b)
            self._vote(poll, voter, o1)
        res = civic.get_opinion_results(poll, None)
        codes = [t['code'] for t in res['by_territory']]
        self.assertIn(self.muni_a.code, codes)      # n=5 shown
        self.assertNotIn(self.muni_b.code, codes)   # n=2 hidden (k>=5)

    # ------------------------------------------------------------------ verified split

    @override_settings(CIVIC_LIVE_THRESHOLD=2)
    def test_verified_split(self):
        poll = self._opinion_poll(self.muni_a)
        o1, o2 = list(poll.options.all())[:2]
        verified = self._citizen('wanda', self.parish_a, verified=True)
        self._vote(poll, self.alice, o1)
        self._vote(poll, verified, o2)
        res = civic.get_opinion_results(poll, None)
        by_id = {o['option_id']: o for o in res['options']}
        self.assertEqual(by_id[o1.id]['count'], 1)
        self.assertEqual(by_id[o1.id]['count_verified'], 0)
        self.assertEqual(by_id[o2.id]['count_verified'], 1)

    # ------------------------------------------------------------------ erasure / purge / audit

    def test_erasure_roundtrip(self):
        poll = self._opinion_poll(self.muni_a)
        self._vote(poll, self.alice, poll.options.first())
        self._vote(poll, self.bob, poll.options.first())
        erased = civic.erase_civic_data(self.alice)
        self.assertEqual(erased, 1)
        token = civic.voter_token(self.alice.id, poll.id)
        self.assertFalse(OpinionVote.objects.filter(poll=poll, voter_token=token).exists())
        self.assertEqual(OpinionVote.objects.filter(poll=poll).count(), 1)
        truth = civic.recount_poll(poll, verify_only=True)
        self.assertEqual(sum(truth['counts'].values()), 1)
        ok, err = AuditService.verify_merkle_chain(poll)
        self.assertTrue(ok, err)
        self.assertTrue(PollAuditLog.objects.filter(poll=poll, action='opinion_erased').exists())

    def test_freeze_and_purge(self):
        poll = self._opinion_poll(self.muni_a)
        self._vote(poll, self.alice, poll.options.first())
        poll.status = Poll.Status.ENDED
        poll.save(update_fields=['status'])
        self.assertTrue(civic.freeze_and_purge(poll))
        poll.refresh_from_db()
        self.assertIsNotNone(poll.frozen_results)
        self.assertFalse(OpinionVote.objects.filter(poll=poll).exists())
        res = civic.get_opinion_results(poll, self.alice)
        self.assertTrue(res['frozen'])
        # Idempotent
        self.assertFalse(civic.freeze_and_purge(poll))

    def test_merkle_chain_with_mixed_actors(self):
        poll = self._opinion_poll(self.muni_a)
        AuditService.create_log_entry(poll=poll, action='poll_created', actor=self.alice,
                                      payload={'x': 1}, pgp_signature='SYSTEM')
        self._vote(poll, self.bob, poll.options.first())  # NULL-actor entry
        AuditService.create_log_entry(poll=poll, action='poll_ended', actor=self.alice,
                                      payload={'y': 2}, pgp_signature='SYSTEM')
        ok, err = AuditService.verify_merkle_chain(poll)
        self.assertTrue(ok, err)
        anon = PollAuditLog.objects.get(poll=poll, action='opinion_vote')
        self.assertIsNone(anon.actor)
        self.assertEqual(anon.actor_ulid, '')

    def test_receipt_included_in_chain(self):
        poll = self._opinion_poll(self.muni_a)
        res = self._vote(poll, self.alice, poll.options.first())
        entry = PollAuditLog.objects.get(poll=poll, current_log_hash=res['receipt'])
        self.assertEqual(entry.action, 'opinion_vote')
        self.assertIsNone(entry.actor)

    def test_recount_heals_drift(self):
        poll = self._opinion_poll(self.muni_a)
        o1 = poll.options.first()
        self._vote(poll, self.alice, o1)
        r = civic._redis()
        r.hset(f"civic:{poll.id}:counts", o1.id, 999)  # corrupt
        civic.recount_poll(poll)
        self.assertEqual(int(r.hget(f"civic:{poll.id}:counts", o1.id)), 1)

    # ------------------------------------------------------------------ feed & creation

    def test_feed_scoping(self):
        p_parish = self._opinion_poll(self.parish_a, title='parish poll')
        p_muni = self._opinion_poll(self.muni_a, title='muni poll')
        p_region = self._opinion_poll(self.region, title='region poll')
        p_country = self._opinion_poll(self.pt, title='country poll')
        p_other = self._opinion_poll(self.parish_b, title='other parish poll')

        request = self.factory.get('/fake/')
        request.auth_profile = self.alice
        items = civic_feed(request)
        titles = {i.title for i in items}
        self.assertEqual(titles, {'parish poll', 'muni poll', 'region poll', 'country poll'})
        self.assertNotIn('other parish poll', titles)

        # Anonymous with country param sees country level only
        request = self.factory.get('/fake/')
        items = civic_feed(request, country='PT')
        self.assertEqual({i.title for i in items}, {'country poll'})

        # comments_enabled only at local levels (U4)
        by_title = {i.title: i for i in civic_feed(self._auth_req(self.alice))}
        self.assertTrue(by_title['parish poll'].comments_enabled)
        self.assertTrue(by_title['muni poll'].comments_enabled)
        self.assertFalse(by_title['region poll'].comments_enabled)
        self.assertFalse(by_title['country poll'].comments_enabled)

    def _auth_req(self, profile):
        request = self.factory.get('/fake/')
        request.auth_profile = profile
        return request

    def test_territory_poll_creation_staff_only(self):
        from governance.api import create_poll, PollCreateRequest
        data = PollCreateRequest(
            context_type='territory', context_id=self.muni_a.id,
            title='Civic creation test', description='longer description here',
            options=['A', 'B'], poll_class='opinion',
        )
        request = self.factory.post('/fake/')
        request.auth_profile = self.alice
        with self.assertRaises(HttpError) as ctx:
            create_poll(request, data)
        self.assertEqual(ctx.exception.status_code, 403)

        self.alice.account.is_staff = True
        self.alice.account.save(update_fields=['is_staff'])
        result = create_poll(request, data)
        poll = Poll.objects.get(id=result.id)
        self._redis_polls.append(poll.id)
        self.assertEqual(poll.poll_class, 'opinion')
        self.assertEqual(poll.ballot_mode, 'anonymous')
        self.assertFalse(poll.allow_delegation)
        self.assertEqual(poll.eligible_voters.count(), 0)


@override_settings(CIVIC_VOTE_SECRET=TEST_SECRET)
class CommunityPollTestCase(TestCase):
    """Household/condominium open-ballot opinion polls (Phase 1.5)."""

    @classmethod
    def setUpTestData(cls):
        cls.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test Instance', public_key='test-key')

    def setUp(self):
        self.factory = RequestFactory()
        self.owner = _mk_profile(_mk_account(self.instance, 'owner'), self.instance)
        self.member = _mk_profile(_mk_account(self.instance, 'member'), self.instance)
        self.outsider = _mk_profile(_mk_account(self.instance, 'outsider'), self.instance)

        from django.contrib.gis.geos import Point
        from iot.models import Property, PropertyMember
        self.prop = Property.objects.create(
            owner=self.owner, name='Test Home',
            location=Point(-8.42, 42.03, srid=4326), property_type='apartment')
        PropertyMember.objects.create(property=self.prop, profile=self.member, invited_by=self.owner)

    def _req(self, profile, method='get'):
        request = getattr(self.factory, method)('/fake/')
        request.auth_profile = profile
        return request

    def _create_household_poll(self, creator):
        from governance.api import create_poll, PollCreateRequest
        data = PollCreateRequest(
            context_type='household', context_id=self.prop.id,
            title='Cat or dog in this home?', description='the eternal question',
            options=['Cat', 'Dog'],
        )
        result = create_poll(self._req(creator, 'post'), data)
        return Poll.objects.get(id=result.id)

    def test_member_creates_open_opinion_poll(self):
        poll = self._create_household_poll(self.member)
        self.assertEqual(poll.poll_class, 'opinion')
        self.assertEqual(poll.ballot_mode, 'open')
        self.assertTrue(poll.allow_delegation)  # liquid democracy sandbox
        eligible = set(poll.eligible_voters.values_list('profile_id', flat=True))
        self.assertEqual(eligible, {self.owner.id, self.member.id})

    def test_outsider_cannot_create(self):
        with self.assertRaises(HttpError) as ctx:
            self._create_household_poll(self.outsider)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_audience_sync_add_and_remove(self):
        from iot.models import PropertyMember
        from governance.civic import sync_poll_audience
        from governance.models import PollEligibleVoter
        poll = self._create_household_poll(self.owner)
        # New member joins → sync adds
        PropertyMember.objects.create(property=self.prop, profile=self.outsider, invited_by=self.owner)
        sync_poll_audience(poll)
        self.assertTrue(PollEligibleVoter.objects.filter(poll=poll, profile=self.outsider).exists())
        # Leaves without voting → removed
        PropertyMember.objects.filter(property=self.prop, profile=self.outsider).delete()
        sync_poll_audience(poll)
        self.assertFalse(PollEligibleVoter.objects.filter(poll=poll, profile=self.outsider).exists())

    def test_open_ballots_audience_gate(self):
        from governance.civic_api import open_ballots
        from governance.models import PollVote
        poll = self._create_household_poll(self.owner)
        option = poll.options.first()
        PollVote.objects.create(poll=poll, voter=self.member, option=option,
                                pgp_signature='', signed_payload={}, effective_weight=1)
        ballots = open_ballots(self._req(self.owner), poll.id)
        self.assertEqual(len(ballots), 1)
        self.assertEqual(ballots[0]['option_text'], option.text)
        with self.assertRaises(HttpError) as ctx:
            open_ballots(self._req(self.outsider), poll.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_condominium_audience(self):
        from geo.models import Establishment, CondominiumFraction
        from governance.civic import resolve_context_audience
        condo = Establishment.objects.create(owner=self.owner, name='Test Condo', slug='test-condo-x1')
        CondominiumFraction.objects.create(establishment=condo, identifier='1-A',
                                           permilagem=100, resident=self.member)
        CondominiumFraction.objects.create(establishment=condo, identifier='1-B',
                                           permilagem=100, resident=self.outsider)
        CondominiumFraction.objects.create(establishment=condo, identifier='GAR',
                                           permilagem=50, resident=None)
        audience = resolve_context_audience('condominium', condo.id)
        self.assertEqual(audience, {self.member.id, self.outsider.id})

    def test_feed_includes_household(self):
        from governance.civic_api import civic_feed
        from governance.models import PollVote
        poll = self._create_household_poll(self.owner)
        PollVote.objects.create(poll=poll, voter=self.member, option=poll.options.first(),
                                pgp_signature='', signed_payload={}, effective_weight=1)
        items = civic_feed(self._req(self.member))
        hh = [i for i in items if i.scope_level == 'household']
        self.assertEqual(len(hh), 1)
        self.assertEqual(hh[0].scope_name, 'Test Home')
        self.assertTrue(hh[0].has_voted)
        self.assertEqual(hh[0].n_display, '1')
        # Outsider's feed has none
        items_out = civic_feed(self._req(self.outsider))
        self.assertFalse([i for i in items_out if i.scope_level == 'household'])
        # Scope filter
        items_hh = civic_feed(self._req(self.member), scope='household')
        self.assertTrue(all(i.scope_level == 'household' for i in items_hh))
        self.assertEqual(len(items_hh), 1)


@override_settings(CIVIC_VOTE_SECRET=TEST_SECRET)
class SliderPollTestCase(CivicPollTestCase):
    """Slider polls (Phase 2): status-quo-relative -2..+2 axes."""

    def _slider_poll(self, territory, axes=('Healthcare', 'Transport')):
        ctx = PollContext.objects.create(
            context_type=PollContext.ContextType.TERRITORY,
            context_id=territory.id, created_by=self.alice)
        poll = Poll.objects.create(
            context=ctx, title='Slider test', description='test', start_time=timezone.now(),
            poll_class=Poll.PollClass.OPINION, ballot_mode=Poll.BallotMode.ANONYMOUS,
            poll_type=Poll.PollType.SLIDERS,
            allow_delegation=False, status=Poll.Status.ACTIVE, created_by=self.alice)
        for i, text in enumerate(axes):
            PollOption.objects.create(poll=poll, text=text, order=i)
        self._redis_polls.append(poll.id)
        return poll

    def _slide(self, poll, profile, values):
        civic._redis().delete(f"civic:cd:{poll.id}:{profile.id}")
        with self.captureOnCommitCallbacks(execute=True):
            return civic.cast_slider_vote(poll, profile, values)

    def tearDown(self):
        r = civic._redis()
        for poll_id in self._redis_polls:
            for opt_id in PollOption.objects.filter(poll_id=poll_id).values_list('id', flat=True):
                r.delete(f"civic:{poll_id}:hist:{opt_id}", f"civic:{poll_id}:hist_v:{opt_id}")
        super().tearDown()

    def test_slider_vote_and_median(self):
        poll = self._slider_poll(self.muni_a)
        a1, a2 = list(poll.options.all())
        res = self._slide(poll, self.alice, {a1.id: 2, a2.id: -1})
        self.assertTrue(res['receipt'])
        self.assertEqual(res['n'], 1)
        self._slide(poll, self.bob, {a1.id: 1, a2.id: -2})

        results = civic.get_opinion_results(poll, self.alice)
        self.assertEqual(results['poll_type'], 'sliders')
        by_axis = {a['option_id']: a for a in results['axes']}
        self.assertEqual(by_axis[a1.id]['median'], 1.5)   # {2,1} → 1.5
        self.assertEqual(by_axis[a2.id]['median'], -1.5)  # {-1,-2} → -1.5
        self.assertTrue(results['quantized'])
        self.assertIsNone(by_axis[a1.id]['distribution'])  # counts hidden below threshold
        self.assertEqual(results['my_values'], {a1.id: 2, a2.id: -1})

    def test_slider_validation(self):
        poll = self._slider_poll(self.muni_a)
        a1, a2 = list(poll.options.all())
        with self.assertRaises(civic.CivicVoteError):
            self._slide(poll, self.alice, {a1.id: 3, a2.id: 0})   # out of range
        with self.assertRaises(civic.CivicVoteError):
            self._slide(poll, self.alice, {a1.id: 1})             # missing axis
        with self.assertRaises(civic.CivicVoteError):
            self._slide(poll, self.alice, {a1.id: 1, a2.id: 0, 'X' * 26: 1})  # unknown axis

    def test_slider_revote_delta_and_recount(self):
        poll = self._slider_poll(self.muni_a)
        a1, a2 = list(poll.options.all())
        self._slide(poll, self.alice, {a1.id: 2, a2.id: 0})
        self._slide(poll, self.alice, {a1.id: -2, a2.id: 0})  # revote flips axis 1
        r = civic._redis()
        hist = {k: int(v) for k, v in r.hgetall(f"civic:{poll.id}:hist:{a1.id}").items()}
        self.assertEqual(hist.get('2', 0), 0)
        self.assertEqual(hist.get('-2', 0), 1)
        # recount reproduces redis exactly
        truth = civic.recount_poll(poll, verify_only=True)
        self.assertEqual(truth['hist'][a1.id], {-2: 1})
        # single voter → n stays 1
        results = civic.get_opinion_results(poll, None)
        self.assertEqual(results['n_display'], '<5')

    def test_slider_hide_until_vote_and_freeze(self):
        poll = self._slider_poll(self.muni_a)
        a1, a2 = list(poll.options.all())
        self._slide(poll, self.alice, {a1.id: 1, a2.id: 1})
        hidden = civic.get_opinion_results(poll, self.bob)
        self.assertTrue(hidden['hidden'])
        self.assertIsNone(hidden['axes'])

        poll.status = Poll.Status.ENDED
        poll.save(update_fields=['status'])
        self.assertTrue(civic.freeze_and_purge(poll))
        poll.refresh_from_db()
        self.assertEqual(poll.frozen_results['poll_type'], 'sliders')
        self.assertFalse(OpinionVote.objects.filter(poll=poll).exists())
        frozen_view = civic.get_opinion_results(poll, self.bob)
        self.assertTrue(frozen_view['frozen'])
        self.assertEqual(frozen_view['axes'][0]['median'], 1)

    def test_slider_erasure(self):
        poll = self._slider_poll(self.muni_a)
        a1, a2 = list(poll.options.all())
        self._slide(poll, self.alice, {a1.id: 2, a2.id: 2})
        self._slide(poll, self.bob, {a1.id: -2, a2.id: -2})
        civic.erase_civic_data(self.alice)
        truth = civic.recount_poll(poll, verify_only=True)
        self.assertEqual(truth['hist'][a1.id], {-2: 1})
        ok, err = AuditService.verify_merkle_chain(poll)
        self.assertTrue(ok, err)


@override_settings(CIVIC_VOTE_SECRET=TEST_SECRET)
class StandingDelegationTestCase(CivicPollTestCase):
    """Standing delegations (Phase 2.5): materialized pseudonymous rows."""

    def setUp(self):
        super().setUp()
        from taxonomy.models import Category
        self.topic_root, _ = Category.objects.get_or_create(
            slug='civic-topics', defaults={'name': 'Civic topics'})
        self.topic_health, _ = Category.objects.get_or_create(
            slug='civic-health', defaults={'name': 'Healthcare', 'parent': self.topic_root})
        self.carol = self._citizen('dcarol', self.parish_a)

    def _delegate(self, delegator, delegate, topic=None, territory=None, accept=True):
        from governance.models import StandingDelegation
        d = StandingDelegation.objects.create(
            delegator=delegator, delegate=delegate,
            scope_type='topic' if topic else 'territory',
            topic=topic, territory=territory,
        )
        if accept:
            d.accepted_at = timezone.now()
            d.save(update_fields=['accepted_at'])
        return d

    def _topic_poll(self, territory, topic):
        poll = self._opinion_poll(territory)
        poll.topic = topic
        poll.save(update_fields=['topic'])
        return poll

    def test_materialize_on_delegate_vote(self):
        from governance.civic_delegation import recompute_poll_materialization
        poll = self._topic_poll(self.muni_a, self.topic_health)
        self._delegate(self.alice, self.bob, topic=self.topic_health)
        option = poll.options.first()
        self._vote(poll, self.bob, option)  # triggers recompute in _after_commit

        alice_row = OpinionVote.objects.get(
            poll=poll, voter_token=civic.voter_token(self.alice.id, poll.id))
        self.assertTrue(alice_row.via_delegation)
        self.assertEqual(alice_row.payload['option'], option.id)
        self.assertEqual(alice_row.voter_territory, self.muni_a.code)  # alice's municipality
        # Aggregates count both voices
        truth = civic.recount_poll(poll, verify_only=True)
        self.assertEqual(truth['counts'][option.id], 2)

    def test_unaccepted_delegation_does_not_materialize(self):
        poll = self._topic_poll(self.muni_a, self.topic_health)
        self._delegate(self.alice, self.bob, topic=self.topic_health, accept=False)
        self._vote(poll, self.bob, poll.options.first())
        self.assertFalse(OpinionVote.objects.filter(
            poll=poll, voter_token=civic.voter_token(self.alice.id, poll.id)).exists())

    def test_territory_scope_covers_subtree(self):
        # Delegation on the REGION covers a municipal poll inside it
        poll = self._opinion_poll(self.muni_a)
        self._delegate(self.alice, self.bob, territory=self.region)
        self._vote(poll, self.bob, poll.options.first())
        self.assertTrue(OpinionVote.objects.filter(
            poll=poll, voter_token=civic.voter_token(self.alice.id, poll.id),
            via_delegation=True).exists())

    def test_topic_beats_territory(self):
        from governance.civic_delegation import build_delegation_graph
        poll = self._topic_poll(self.muni_a, self.topic_health)
        self._delegate(self.alice, self.bob, territory=self.region)
        self._delegate(self.alice, self.carol, topic=self.topic_health)
        graph = build_delegation_graph(poll)
        self.assertEqual(graph[self.alice.id], self.carol.id)

    def test_transitive_chain_and_cycle(self):
        from governance.civic_delegation import build_delegation_graph, resolve_terminal
        poll = self._opinion_poll(self.muni_a)
        self._delegate(self.alice, self.bob, territory=self.region)
        self._delegate(self.bob, self.carol, territory=self.region)
        graph = build_delegation_graph(poll)
        self.assertEqual(resolve_terminal(self.alice.id, graph), self.carol.id)
        # Close the cycle: carol → alice
        self._delegate(self.carol, self.alice, territory=self.region)
        graph = build_delegation_graph(poll)
        self.assertIsNone(resolve_terminal(self.alice.id, graph))

    def test_own_vote_beats_delegation(self):
        poll = self._opinion_poll(self.muni_a)
        o1, o2 = list(poll.options.all())[:2]
        self._delegate(self.alice, self.bob, territory=self.region)
        self._vote(poll, self.bob, o1)     # materializes alice → o1
        self._vote(poll, self.alice, o2)   # own vote overrides
        row = OpinionVote.objects.get(poll=poll, voter_token=civic.voter_token(self.alice.id, poll.id))
        self.assertFalse(row.via_delegation)
        self.assertEqual(row.payload['option'], o2.id)
        # Delegate re-votes: alice's own row must NOT be touched
        civic._redis().delete(f"civic:cd:{poll.id}:{self.bob.id}")
        self._vote(poll, self.bob, o2)
        row.refresh_from_db()
        self.assertFalse(row.via_delegation)

    def test_revoke_melts_materialized_row(self):
        from governance.civic_delegation import recompute_for_delegation
        poll = self._opinion_poll(self.muni_a)
        d = self._delegate(self.alice, self.bob, territory=self.region)
        self._vote(poll, self.bob, poll.options.first())
        token = civic.voter_token(self.alice.id, poll.id)
        self.assertTrue(OpinionVote.objects.filter(poll=poll, voter_token=token).exists())
        d.revoked_at = timezone.now()
        d.is_active = False
        d.save(update_fields=['revoked_at', 'is_active'])
        recompute_for_delegation(d)
        self.assertFalse(OpinionVote.objects.filter(poll=poll, voter_token=token).exists())
        truth = civic.recount_poll(poll, verify_only=True)
        self.assertEqual(sum(truth['counts'].values()), 1)

    def test_out_of_scope_delegator_not_materialized(self):
        poll = self._opinion_poll(self.muni_a)
        outsider = self._citizen('dave2', self.parish_b)  # muni B, poll is muni A
        self._delegate(outsider, self.bob, territory=self.region)
        self._vote(poll, self.bob, poll.options.first())
        self.assertFalse(OpinionVote.objects.filter(
            poll=poll, voter_token=civic.voter_token(outsider.id, poll.id)).exists())

    def test_viewer_delegation_info(self):
        from governance.civic_delegation import viewer_delegation_info
        poll = self._opinion_poll(self.muni_a)
        self._delegate(self.alice, self.bob, territory=self.region)
        info = viewer_delegation_info(poll, self.alice)
        self.assertEqual(info['delegate_id'], self.bob.id)
        self.assertFalse(info['has_cast'])
        self._vote(poll, self.bob, poll.options.first())
        info = viewer_delegation_info(poll, self.alice)
        self.assertTrue(info['has_cast'])
        # results carry the flag
        res = civic.get_opinion_results(poll, self.alice)
        self.assertTrue(res['my_vote_via'])
        self.assertEqual(res['delegation']['delegate_hna'], self.bob.hna)

    def test_erasure_revokes_delegations(self):
        poll = self._opinion_poll(self.muni_a)
        self._delegate(self.alice, self.bob, territory=self.region)
        self._vote(poll, self.bob, poll.options.first())
        civic.erase_civic_data(self.alice)
        from governance.models import StandingDelegation
        self.assertFalse(StandingDelegation.objects.filter(
            delegator=self.alice, is_active=True).exists())
        self.assertFalse(OpinionVote.objects.filter(
            poll=poll, voter_token=civic.voter_token(self.alice.id, poll.id)).exists())


@override_settings(CIVIC_VOTE_SECRET=TEST_SECRET, CIVIC_IDEA_SUPPORT_THRESHOLD=3)
class CivicIdeaTestCase(CivicPollTestCase):
    """Ideas pipeline (Phase 3): support threshold → review → promote/reject."""

    def _req(self, profile, method='post'):
        request = getattr(self.factory, method)('/fake/')
        request.auth_profile = profile
        return request

    def _idea(self, author, territory=None):
        from governance.civic_api import create_idea, IdeaCreateRequest
        return create_idea(self._req(author), IdeaCreateRequest(
            territory_id=(territory or self.muni_a).id,
            title='More benches in the park please',
            body='The riverside park has nowhere to sit for elderly residents.',
        ))

    def test_create_and_author_autosupport(self):
        out = self._idea(self.alice)
        self.assertEqual(out['support_count'], 1)
        self.assertTrue(out['supported_by_me'])
        self.assertEqual(out['status'], 'open')

    def test_out_of_scope_creation_rejected(self):
        from governance.civic_api import create_idea, IdeaCreateRequest
        outsider = self._citizen('ida', self.parish_b)
        with self.assertRaises(HttpError) as ctx:
            create_idea(self._req(outsider), IdeaCreateRequest(
                territory_id=self.parish_a.id, title='Out of scope idea',
                body='I do not even live here but have opinions.'))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_threshold_moves_to_review(self):
        from governance.civic_api import support_idea
        from governance.models import CivicIdea
        out = self._idea(self.alice)
        support_idea(self._req(self.bob), out['id'])
        third = self._citizen('ines', self.parish_a)
        result = support_idea(self._req(third), out['id'])
        self.assertEqual(result['support_count'], 3)
        self.assertEqual(result['status'], 'review')
        # unsupport below threshold does NOT reopen (review is sticky for staff)
        from governance.civic_api import unsupport_idea
        result = unsupport_idea(self._req(third), out['id'])
        self.assertEqual(result['support_count'], 2)
        self.assertEqual(CivicIdea.objects.get(id=out['id']).status, 'review')

    def test_supporters_never_exposed(self):
        from governance.civic_api import list_ideas, support_idea
        out = self._idea(self.alice)
        support_idea(self._req(self.bob), out['id'])
        listed = list_ideas(self._req(self.bob, 'get'))
        item = [i for i in listed if i['id'] == out['id']][0]
        self.assertNotIn('supporters', item)
        self.assertNotIn(self.bob.id, str(item))
        self.assertTrue(item['supported_by_me'])
        # another viewer does not learn who supported
        viewer = self._citizen('vera2', self.parish_a)
        listed = list_ideas(self._req(viewer, 'get'))
        item = [i for i in listed if i['id'] == out['id']][0]
        self.assertFalse(item['supported_by_me'])
        self.assertEqual(item['support_count'], 2)

    def test_promote_links_poll_and_sets_status(self):
        from governance.api import create_poll, PollCreateRequest
        from governance.models import CivicIdea
        out = self._idea(self.alice)
        self.alice.account.is_staff = True
        self.alice.account.save(update_fields=['is_staff'])
        poll_out = create_poll(self._req(self.alice), PollCreateRequest(
            context_type='territory', context_id=self.muni_a.id,
            title='Benches in the riverside park?', description='Formulated from a citizen idea.',
            options=['Yes, add benches', 'No', 'Undecided'],
            poll_class='opinion', from_idea_id=out['id'],
        ))
        idea = CivicIdea.objects.get(id=out['id'])
        self.assertEqual(idea.status, 'promoted')
        self.assertEqual(idea.promoted_poll_id, poll_out.id)

    def test_reject_staff_only(self):
        from governance.civic_api import reject_idea, IdeaRejectRequest
        out = self._idea(self.alice)
        with self.assertRaises(HttpError) as ctx:
            reject_idea(self._req(self.bob), out['id'], IdeaRejectRequest(note='no'))
        self.assertEqual(ctx.exception.status_code, 403)
        self.bob.account.is_staff = True
        self.bob.account.save(update_fields=['is_staff'])
        res = reject_idea(self._req(self.bob), out['id'], IdeaRejectRequest(note='duplicate'))
        self.assertEqual(res['status'], 'rejected')

    def test_ideas_feed_scoping(self):
        from governance.civic_api import list_ideas
        self._idea(self.alice, territory=self.muni_a)
        outsider = self._citizen('joel', self.parish_b)
        self._idea(outsider, territory=self.muni_b)
        mine = list_ideas(self._req(self.alice, 'get'))
        self.assertTrue(all(i['territory_id'] != self.muni_b.id for i in mine))
