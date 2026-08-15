"""
UGC moderation tests: content reporting + user blocking enforcement
(Play User-Generated Content policy).

Covers: report creation (resolution, dedup, own-content refusal), block
endpoints, and the block filters on the item list (BOTH the raw-SQL and the
ORM path), comment list, profile search and DM creation.
"""

import orjson
from django.http import HttpResponse
from django.test import TestCase, RequestFactory
from ninja.errors import HttpError

from core.endpoints.comments import list_comments
from core.endpoints.reports import (
    ReportInput, ResolveInput, create_report, report_queue, resolve_report,
)
from core.models import ContentReport, Instance, ObjectComment
from identity.models import Account, Profile, ProfileBlock
from identity.services.blocks import (
    blocked_ids_for_request, blocked_profile_ids, dm_blocked_between_accounts,
)
from market.models import Item
from parahub.endpoints.items import list_items
from parahub.endpoints.profiles.blocks import (
    block_profile, list_blocked_profiles, unblock_profile,
)
from parahub.endpoints.profiles.core import search_profiles

MARKER = 'ModProbe'


class ModerationTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.instance = Instance.objects.create(
            domain='test.parahub.io', name='Test Instance', public_key='test-key')

        def make_profile(username, **kwargs):
            account = Account.objects.create_user(
                username=username, email=f'{username}@test.parahub.io',
                password='x', instance=cls.instance)
            return Profile.objects.create(
                account=account, instance=cls.instance, local_name=username,
                display_name=f'{username.title()} Real', is_primary=True,
                profile_type=Profile.ProfileType.PERSONAL, **kwargs)

        cls.alice = make_profile('modalice')
        cls.bob = make_profile('modbob')
        cls.carol = make_profile('modcarol')
        # Second profile on Bob's account (pseudonymity checks)
        cls.bob_pseudo = Profile.objects.create(
            account=cls.bob.account, instance=cls.instance,
            local_name='modbob-pseudo', display_name='Shadow',
            profile_type=Profile.ProfileType.PSEUDONYMOUS)

        cls.bob_item = Item.objects.create(
            owner=cls.bob, title=f'{MARKER} bob offer', type='CREDIT',
            pricing_options=[{'type': 'sale', 'amount': '5.00',
                              'currency': 'EUR', 'unit': 'pcs'}])
        cls.carol_item = Item.objects.create(
            owner=cls.carol, title=f'{MARKER} carol offer', type='CREDIT',
            pricing_options=[])

        cls.bob_comment = ObjectComment.objects.create(
            object_id=cls.carol_item.id, author=cls.bob, text='from bob')
        cls.carol_comment = ObjectComment.objects.create(
            object_id=cls.carol_item.id, author=cls.carol, text='from carol')

        cls.factory = RequestFactory()

    def _request(self, viewer=None, path='/api/v1/test/'):
        request = self.factory.get(path)
        if viewer is not None:
            request.user = viewer.account
            request.auth = viewer
            request.auth_profile = viewer
        return request


class ContentReportTests(ModerationTestBase):
    def test_report_item_resolves_author_and_excerpt(self):
        status, resp = create_report(self._request(self.alice), ReportInput(
            object_id=self.bob_item.id, reason='FRAUD', details='  suspicious  '))
        self.assertEqual(status, 201)
        report = ContentReport.objects.get(id=resp.id)
        self.assertEqual(report.object_type, 'item')
        self.assertEqual(report.reported_profile_id, self.bob.id)
        self.assertEqual(report.excerpt, f'{MARKER} bob offer')
        self.assertEqual(report.details, 'suspicious')
        self.assertEqual(report.status, ContentReport.Status.PENDING)

    def test_report_profile_and_comment(self):
        status, resp = create_report(self._request(self.alice), ReportInput(
            object_id=self.bob.id, reason='HARASSMENT'))
        self.assertEqual(status, 201)
        self.assertEqual(resp.target_type, 'profile')
        self.assertEqual(
            ContentReport.objects.get(id=resp.id).reported_profile_id, self.bob.id)

        status, resp = create_report(self._request(self.alice), ReportInput(
            object_id=self.bob_comment.id, reason='SPAM'))
        self.assertEqual(status, 201)
        self.assertEqual(resp.target_type, 'objectcomment')
        self.assertEqual(
            ContentReport.objects.get(id=resp.id).excerpt, 'from bob')

    def test_duplicate_pending_report_refused(self):
        create_report(self._request(self.alice), ReportInput(
            object_id=self.bob_item.id, reason='SPAM'))
        with self.assertRaises(HttpError) as ctx:
            create_report(self._request(self.alice), ReportInput(
                object_id=self.bob_item.id, reason='FRAUD'))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(getattr(ctx.exception, 'code', ''), 'report_already_pending')

    def test_reviewed_report_allows_new_one(self):
        _, resp = create_report(self._request(self.alice), ReportInput(
            object_id=self.bob_item.id, reason='SPAM'))
        ContentReport.objects.filter(id=resp.id).update(
            status=ContentReport.Status.DISMISSED)
        status, _ = create_report(self._request(self.alice), ReportInput(
            object_id=self.bob_item.id, reason='FRAUD'))
        self.assertEqual(status, 201)

    def test_cannot_report_own_content(self):
        with self.assertRaises(HttpError) as ctx:
            create_report(self._request(self.bob), ReportInput(
                object_id=self.bob_item.id, reason='SPAM'))
        self.assertEqual(getattr(ctx.exception, 'code', ''), 'report_own_content')

    def test_unknown_target_404(self):
        with self.assertRaises(HttpError) as ctx:
            create_report(self._request(self.alice), ReportInput(
                object_id='0' * 26, reason='SPAM'))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_invalid_reason_refused(self):
        with self.assertRaises(HttpError) as ctx:
            create_report(self._request(self.alice), ReportInput(
                object_id=self.bob_item.id, reason='BOGUS'))
        self.assertEqual(getattr(ctx.exception, 'code', ''), 'report_invalid_reason')


class ModerationQueueTests(ModerationTestBase):
    """
    The queue behind the reports (`moderation.review`).

    Two things worth pinning: reading it is a capability, not `is_staff`; and a
    verdict lands on the *object*, closing every pending report on it at once.
    """

    def setUp(self):
        from django.contrib.auth.models import Group
        self.moderators, _ = Group.objects.get_or_create(name='moderators')

    def _mod(self, profile=None):
        profile = profile or self.alice
        profile.account.groups.add(self.moderators)
        profile.account.refresh_from_db()
        return self._request(profile)

    def _report(self, reporter, target_id, reason='SPAM'):
        _, resp = create_report(self._request(reporter), ReportInput(
            object_id=target_id, reason=reason))
        return ContentReport.objects.get(id=resp.id)

    def test_the_queue_is_a_capability_not_a_role(self):
        with self.assertRaises(HttpError) as ctx:
            report_queue(self._request(self.alice))
        self.assertEqual(ctx.exception.status_code, 403)

        status, page = report_queue(self._mod())
        self.assertEqual(status, 200)
        self.assertEqual(page.items, [])

    def test_a_row_carries_the_context_a_verdict_needs(self):
        self._report(self.alice, self.bob_item.id, reason='FRAUD')
        _, page = report_queue(self._mod())

        row = page.items[0]
        self.assertEqual(row.target_type, 'item')
        self.assertEqual(row.excerpt, f'{MARKER} bob offer')
        self.assertEqual(row.reporter.local_name, 'modalice')
        self.assertEqual(row.reported_profile.local_name, 'modbob')
        self.assertEqual(page.pending_total, 1)

    def test_filters_and_the_repeat_signal(self):
        self._report(self.alice, self.bob_item.id, reason='FRAUD')
        second = self._report(self.carol, self.bob_comment.id, reason='SPAM')
        ContentReport.objects.filter(id=second.id).update(
            status=ContentReport.Status.ACTIONED)

        request = self._mod()
        _, pending = report_queue(request)
        self.assertEqual([r.id for r in pending.items],
                         list(ContentReport.objects.filter(
                             status=ContentReport.Status.PENDING).values_list('id', flat=True)))

        _, actioned = report_queue(request, status='ACTIONED')
        self.assertEqual(len(actioned.items), 1)
        # Both reports are against bob, one of them upheld.
        self.assertEqual(actioned.items[0].author_reports_total, 2)
        self.assertEqual(actioned.items[0].author_reports_actioned, 1)

        _, by_reason = report_queue(request, status='', reason='FRAUD')
        self.assertEqual(len(by_reason.items), 1)
        _, by_type = report_queue(request, status='', object_type='objectcomment')
        self.assertEqual(len(by_type.items), 1)

    def test_unknown_filter_values_are_400(self):
        request = self._mod()
        for kwargs in ({'status': 'MAYBE'}, {'reason': 'BOGUS'}):
            with self.subTest(**kwargs):
                with self.assertRaises(HttpError) as ctx:
                    report_queue(request, **kwargs)
                self.assertEqual(ctx.exception.status_code, 400)

    def test_a_verdict_closes_every_pending_report_on_the_object(self):
        """Five people report one item; the moderator decides once."""
        first = self._report(self.alice, self.bob_item.id)
        self._report(self.carol, self.bob_item.id, reason='FRAUD')
        untouched = self._report(self.alice, self.bob_comment.id)

        status, out = resolve_report(self._mod(), first.id,
                                     ResolveInput(status='ACTIONED', note='removed'))
        self.assertEqual(status, 200)
        self.assertEqual(out.resolved, 2)

        for report in (first, ContentReport.objects.get(reporter=self.carol,
                                                        object_id=self.bob_item.id)):
            report.refresh_from_db()
            self.assertEqual(report.status, ContentReport.Status.ACTIONED)
            self.assertEqual(report.reviewed_by_id, self.alice.account.id)
            self.assertIsNotNone(report.reviewed_at)
            self.assertEqual(report.resolution_note, 'removed')

        untouched.refresh_from_db()
        self.assertEqual(untouched.status, ContentReport.Status.PENDING)

    def test_a_verdict_can_be_corrected(self):
        report = self._report(self.alice, self.bob_item.id)
        request = self._mod()
        resolve_report(request, report.id, ResolveInput(status='ACTIONED'))
        _, out = resolve_report(request, report.id,
                                ResolveInput(status='DISMISSED', note='mine, sorry'))
        self.assertEqual(out.resolved, 1)
        report.refresh_from_db()
        self.assertEqual(report.status, ContentReport.Status.DISMISSED)

    def test_resolution_must_be_a_verdict(self):
        report = self._report(self.alice, self.bob_item.id)
        with self.assertRaises(HttpError) as ctx:
            resolve_report(self._mod(), report.id, ResolveInput(status='PENDING'))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_resolving_needs_the_capability_too(self):
        report = self._report(self.alice, self.bob_item.id)
        with self.assertRaises(HttpError) as ctx:
            resolve_report(self._request(self.carol), report.id,
                           ResolveInput(status='DISMISSED'))
        self.assertEqual(ctx.exception.status_code, 403)
        report.refresh_from_db()
        self.assertEqual(report.status, ContentReport.Status.PENDING)


class BlockEndpointTests(ModerationTestBase):
    def test_block_unblock_cycle(self):
        status, resp = block_profile(self._request(self.alice), self.bob.id)
        self.assertEqual(status, 201)
        self.assertTrue(ProfileBlock.objects.filter(
            blocker=self.alice, blocked=self.bob).exists())

        # Idempotent re-block
        status, _ = block_profile(self._request(self.alice), self.bob.local_name)
        self.assertEqual(status, 201)
        self.assertEqual(ProfileBlock.objects.filter(blocker=self.alice).count(), 1)

        resp = list_blocked_profiles(self._request(self.alice))
        self.assertEqual(resp.count, 1)
        self.assertEqual(resp.items[0].id, self.bob.id)

        status, resp = unblock_profile(self._request(self.alice), self.bob.id)
        self.assertEqual(status, 200)
        self.assertFalse(ProfileBlock.objects.filter(blocker=self.alice).exists())

    def test_cannot_block_own_account_profiles(self):
        with self.assertRaises(HttpError):
            block_profile(self._request(self.bob), self.bob_pseudo.id)

    def test_blocked_ids_span_viewer_profiles_only(self):
        ProfileBlock.objects.create(blocker=self.alice, blocked=self.bob)
        # Blocker side spans the whole account…
        self.assertEqual(blocked_profile_ids(self.alice.account_id), [self.bob.id])
        # …but the blocked side stays per-profile: Bob's pseudonym is NOT swept in
        self.assertNotIn(self.bob_pseudo.id,
                         blocked_profile_ids(self.alice.account_id))
        self.assertEqual(blocked_profile_ids(None), [])

    def test_dm_blocked_both_directions_account_wide(self):
        self.assertFalse(dm_blocked_between_accounts(
            self.alice.account_id, self.bob.account_id))
        # Alice blocks only Bob's pseudonym — the DM channel still closes
        ProfileBlock.objects.create(blocker=self.alice, blocked=self.bob_pseudo)
        self.assertTrue(dm_blocked_between_accounts(
            self.alice.account_id, self.bob.account_id))
        self.assertTrue(dm_blocked_between_accounts(
            self.bob.account_id, self.alice.account_id))

    def test_create_dm_endpoint_refuses_blocked(self):
        from parahub.endpoints.matrix_auth import CreateDMRequest, create_dm_room
        ProfileBlock.objects.create(blocker=self.alice, blocked=self.bob)
        request = self.factory.post('/api/v1/matrix/create-dm')
        request.user = self.alice.account
        with self.assertRaises(HttpError) as ctx:
            create_dm_room(request, CreateDMRequest(
                target_account_id=self.bob.account_id))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(getattr(ctx.exception, 'code', ''), 'dm_blocked')


class BlockEnforcementTests(ModerationTestBase):
    def setUp(self):
        ProfileBlock.objects.create(blocker=self.alice, blocked=self.bob)

    def _raw_items(self, viewer):
        resp = list_items(self._request(viewer, '/api/v1/items/'))
        self.assertIsInstance(resp, HttpResponse, 'raw path did not run')
        return orjson.loads(resp.content)['items']

    def _orm_items(self, viewer):
        resp = list_items(self._request(viewer, '/api/v1/items/'), q=MARKER)
        self.assertIsInstance(resp, dict, 'ORM path did not run')
        return [i.model_dump(mode='json') for i in resp['items']]

    def test_items_hidden_from_blocker_raw_and_orm(self):
        for items in (self._raw_items(self.alice), self._orm_items(self.alice)):
            ids = {i['id'] for i in items}
            self.assertNotIn(self.bob_item.id, ids)
            self.assertIn(self.carol_item.id, ids)

    def test_items_visible_to_other_viewers(self):
        for items in (self._raw_items(self.carol), self._orm_items(self.carol)):
            self.assertIn(self.bob_item.id, {i['id'] for i in items})
        # The blocked user keeps seeing their own listings
        for items in (self._raw_items(self.bob), self._orm_items(self.bob)):
            self.assertIn(self.bob_item.id, {i['id'] for i in items})

    def test_comments_hidden_from_blocker_only(self):
        ids = {c.id for c in list_comments(
            self._request(self.alice), object_id=self.carol_item.id)}
        self.assertEqual(ids, {self.carol_comment.id})

        anon_ids = {c.id for c in list_comments(
            self._request(), object_id=self.carol_item.id)}
        self.assertEqual(anon_ids, {self.bob_comment.id, self.carol_comment.id})

    def test_profile_search_hides_blocked(self):
        resp = search_profiles(self._request(self.alice), q='modbob')
        ids = {p.id for p in resp['items']}
        self.assertNotIn(self.bob.id, ids)

        resp = search_profiles(self._request(self.carol), q='modbob')
        ids = {p.id for p in resp['items']}
        self.assertIn(self.bob.id, ids)

    def test_blocked_ids_for_request_anonymous(self):
        self.assertEqual(blocked_ids_for_request(self._request()), [])
