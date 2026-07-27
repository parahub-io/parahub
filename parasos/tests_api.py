"""
Tests for ParaSOS API endpoints: groups, membership, alerts, invites.

Invariants that must never break:
- WoT 3+ required to create safety groups
- PRIVATE groups 404 for non-members everywhere (existence stays hidden)
- Alert data (sender location, history, responses) is members-only
- PRIVATE join requires a valid invite token; uses_count increments
- max_members enforced on join; last admin cannot leave
- Only admin can update/delete a group; delete resolves active alerts
  and deactivates invites
- Explicit null clears quiet hours on update; omitted fields stay untouched
- SOS: members only, one active alert per sender, sender can't respond
  to own alert, only sender/admin resolves
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, RequestFactory, override_settings
from django.contrib.gis.geos import Point
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from ninja.errors import HttpError
from django.http import Http404

from identity.models import Account, Profile, Verification
from core.models import Instance
from parasos.models import (
    SafetyGroup, SafetyGroupMember, SOSAlert, SOSResponse, GroupInvite,
)
from parasos.api import (
    create_group, get_group, update_group, delete_group,
    join_group, leave_group, send_sos, respond_to_sos, resolve_sos,
    get_alert, get_alert_responses, create_invite, delete_invite,
    get_invite_info, _get_group_for_member,
    GroupCreateInput, GroupUpdateInput, JoinGroupInput, SOSInput,
    SOSResponseInput, InviteCreateInput, LocationInput,
)


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


def _add_verifications(profile, count=3):
    instance = profile.instance
    for i in range(count):
        acc = _create_account(instance, f'v{i}_{profile.local_name}')
        vp = _create_profile(acc, instance, local_name=f'v{i}_{profile.local_name}')
        Verification.objects.create(verifier=vp, verified_profile=profile, is_active=True)


def _make_auth_request(factory, account, profile, method='get', path='/fake/'):
    fn = getattr(factory, method)
    request = fn(path)
    request.user = account
    request.auth = profile
    request.auth_profile = profile
    request.session = SessionStore()
    request.session.create()
    return request


def _create_group_db(creator, name='Test Group', visibility='PUBLIC', **kwargs):
    """Create a group + creator ADMIN membership directly in DB."""
    group = SafetyGroup.objects.create(
        name=name,
        description=kwargs.pop('description', ''),
        visibility=visibility,
        created_by=creator,
        center=kwargs.pop('center', Point(-8.386, 41.842, srid=4326)),
        radius_m=kwargs.pop('radius_m', 1000),
        **kwargs,
    )
    SafetyGroupMember.objects.create(
        group=group, profile=creator,
        role=SafetyGroupMember.Role.ADMIN,
        presence=SafetyGroupMember.Presence.LOCAL,
    )
    group.members_count = 1
    group.save(update_fields=['members_count'])
    return group


def _add_member(group, profile, role='MEMBER'):
    member = SafetyGroupMember.objects.create(
        group=group, profile=profile, role=role,
        presence=SafetyGroupMember.Presence.LOCAL,
    )
    group.members_count = group.members.count()
    group.save(update_fields=['members_count'])
    return member


class ParasosTestBase(TestCase):
    """Common fixtures: two users, matrix/background side effects mocked."""

    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.alice_acc = _create_account(self.instance, 'alice')
        self.alice = _create_profile(self.alice_acc, self.instance)
        self.bob_acc = _create_account(self.instance, 'bob')
        self.bob = _create_profile(self.bob_acc, self.instance)

        patches = [
            patch('parasos.api._create_group_matrix_room', return_value=None),
            patch('parasos.api._join_group_matrix_room', return_value=False),
            patch('parasos.api.spawn'),
            patch('parahub.services.ws_publish.ws_publish'),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _req(self, profile, method='get'):
        return _make_auth_request(self.factory, profile.account, profile, method=method)


# ===========================================================================
# Group creation
# ===========================================================================

@override_settings(RATELIMIT_ENABLE=False)
class GroupCreateTest(ParasosTestBase):

    def test_wot_below_3_rejected(self):
        request = self._req(self.alice, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_group(request, GroupCreateInput(name='My Group'))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_wot_3_creates_group_with_admin_membership(self):
        _add_verifications(self.alice)
        request = self._req(self.alice, 'post')
        result = create_group(request, GroupCreateInput(
            name='My Group',
            center=LocationInput(latitude=41.842, longitude=-8.386),
            radius_m=1500,
        ))
        self.assertTrue(result.is_admin)
        group = SafetyGroup.objects.get(id=result.id)
        self.assertEqual(group.members_count, 1)
        self.assertTrue(SafetyGroupMember.objects.filter(
            group=group, profile=self.alice, role='ADMIN').exists())

    def test_location_free_group(self):
        _add_verifications(self.alice)
        request = self._req(self.alice, 'post')
        result = create_group(request, GroupCreateInput(name='Friends & Family'))
        self.assertIsNone(result.center)


# ===========================================================================
# Visibility / membership gates (security invariants)
# ===========================================================================

@override_settings(RATELIMIT_ENABLE=False)
class VisibilityTest(ParasosTestBase):

    def setUp(self):
        super().setUp()
        self.public_group = _create_group_db(self.alice, 'Public G', 'PUBLIC')
        self.private_group = _create_group_db(self.alice, 'Private G', 'PRIVATE')

    def test_public_group_visible_to_non_member(self):
        result = get_group(self._req(self.bob), self.public_group.id)
        self.assertFalse(result.is_member)
        self.assertIsNone(result.matrix_room_id)

    def test_private_group_404_for_non_member(self):
        with self.assertRaises(HttpError) as ctx:
            get_group(self._req(self.bob), self.private_group.id)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_private_group_visible_to_member(self):
        _add_member(self.private_group, self.bob)
        result = get_group(self._req(self.bob), self.private_group.id)
        self.assertTrue(result.is_member)

    def test_inactive_group_404(self):
        self.public_group.is_active = False
        self.public_group.save(update_fields=['is_active'])
        with self.assertRaises(HttpError) as ctx:
            get_group(self._req(self.alice), self.public_group.id)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_member_gate_403_on_public_group(self):
        with self.assertRaises(HttpError) as ctx:
            _get_group_for_member(self.public_group.id, self.bob)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_member_gate_404_on_private_group(self):
        with self.assertRaises(HttpError) as ctx:
            _get_group_for_member(self.private_group.id, self.bob)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_alert_detail_members_only(self):
        alert = SOSAlert.objects.create(
            group=self.public_group, sender=self.alice,
            level='EMERGENCY', location=Point(-8.4, 41.8, srid=4326),
        )
        with self.assertRaises(HttpError) as ctx:
            get_alert(self._req(self.bob), alert.id)
        self.assertEqual(ctx.exception.status_code, 403)
        # member sees it, with location
        result = get_alert(self._req(self.alice), alert.id)
        self.assertIsNotNone(result.location)

    def test_alert_responses_members_only(self):
        alert = SOSAlert.objects.create(
            group=self.public_group, sender=self.alice, level='WARNING',
        )
        with self.assertRaises(HttpError) as ctx:
            get_alert_responses(self._req(self.bob), alert.id)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(get_alert_responses(self._req(self.alice), alert.id), [])


# ===========================================================================
# Join / leave
# ===========================================================================

@override_settings(RATELIMIT_ENABLE=False)
class JoinLeaveTest(ParasosTestBase):

    def setUp(self):
        super().setUp()
        self.group = _create_group_db(self.alice, 'Join G', 'PUBLIC')

    def test_join_public(self):
        result = join_group(self._req(self.bob, 'post'), self.group.id, JoinGroupInput())
        self.assertTrue(result['success'])
        self.assertEqual(result['members_count'], 2)

    def test_join_twice_rejected(self):
        join_group(self._req(self.bob, 'post'), self.group.id, JoinGroupInput())
        with self.assertRaises(HttpError) as ctx:
            join_group(self._req(self.bob, 'post'), self.group.id, JoinGroupInput())
        self.assertEqual(ctx.exception.status_code, 400)

    def test_join_full_group_rejected(self):
        self.group.max_members = 1
        self.group.save(update_fields=['max_members'])
        with self.assertRaises(HttpError) as ctx:
            join_group(self._req(self.bob, 'post'), self.group.id, JoinGroupInput())
        self.assertEqual(ctx.exception.status_code, 400)

    def test_private_join_requires_invite(self):
        private = _create_group_db(self.alice, 'Priv', 'PRIVATE')
        with self.assertRaises(HttpError) as ctx:
            join_group(self._req(self.bob, 'post'), private.id, JoinGroupInput())
        self.assertEqual(ctx.exception.status_code, 403)

        with self.assertRaises(HttpError):
            join_group(self._req(self.bob, 'post'), private.id,
                       JoinGroupInput(invite_token='bogus'))

        invite = GroupInvite.objects.create(group=private, created_by=self.alice)
        result = join_group(self._req(self.bob, 'post'), private.id,
                            JoinGroupInput(invite_token=invite.token))
        self.assertTrue(result['success'])
        invite.refresh_from_db()
        self.assertEqual(invite.uses_count, 1)

    def test_expired_invite_rejected(self):
        private = _create_group_db(self.alice, 'Priv2', 'PRIVATE')
        invite = GroupInvite.objects.create(
            group=private, created_by=self.alice,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        with self.assertRaises(HttpError) as ctx:
            join_group(self._req(self.bob, 'post'), private.id,
                       JoinGroupInput(invite_token=invite.token))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_leave(self):
        _add_member(self.group, self.bob)
        result = leave_group(self._req(self.bob, 'post'), self.group.id)
        self.assertEqual(result['members_count'], 1)

    def test_last_admin_cannot_leave(self):
        _add_member(self.group, self.bob)
        with self.assertRaises(HttpError) as ctx:
            leave_group(self._req(self.alice, 'post'), self.group.id)
        self.assertEqual(ctx.exception.status_code, 400)


# ===========================================================================
# Update / delete
# ===========================================================================

@override_settings(RATELIMIT_ENABLE=False)
class UpdateDeleteTest(ParasosTestBase):

    def setUp(self):
        super().setUp()
        self.group = _create_group_db(
            self.alice, 'Upd G', 'PUBLIC',
            quiet_hours_start=23, quiet_hours_end=7,
        )

    def test_update_requires_admin(self):
        _add_member(self.group, self.bob)
        with self.assertRaises(HttpError) as ctx:
            update_group(self._req(self.bob, 'put'), self.group.id,
                         GroupUpdateInput(name='Hacked'))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_update_fields(self):
        result = update_group(self._req(self.alice, 'put'), self.group.id,
                              GroupUpdateInput(name='Renamed', visibility='PRIVATE'))
        self.assertEqual(result.name, 'Renamed')
        self.assertEqual(result.visibility, 'PRIVATE')
        # omitted fields untouched
        self.assertEqual(result.quiet_hours_start, 23)

    def test_update_clears_quiet_hours_with_explicit_null(self):
        result = update_group(self._req(self.alice, 'put'), self.group.id,
                              GroupUpdateInput(quiet_hours_start=None, quiet_hours_end=None))
        self.assertIsNone(result.quiet_hours_start)
        self.assertIsNone(result.quiet_hours_end)

    def test_delete_requires_admin(self):
        _add_member(self.group, self.bob)
        with self.assertRaises(HttpError) as ctx:
            delete_group(self._req(self.bob, 'delete'), self.group.id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_delete_resolves_alerts_and_invites(self):
        alert = SOSAlert.objects.create(group=self.group, sender=self.alice, level='WARNING')
        invite = GroupInvite.objects.create(group=self.group, created_by=self.alice)

        status, _ = delete_group(self._req(self.alice, 'delete'), self.group.id)
        self.assertEqual(status, 204)

        self.group.refresh_from_db()
        alert.refresh_from_db()
        invite.refresh_from_db()
        self.assertFalse(self.group.is_active)
        self.assertEqual(alert.status, SOSAlert.Status.RESOLVED)
        self.assertIsNotNone(alert.resolved_at)
        self.assertFalse(invite.is_active)


# ===========================================================================
# SOS alerts
# ===========================================================================

@override_settings(RATELIMIT_ENABLE=False)
class SOSAlertTest(ParasosTestBase):

    def setUp(self):
        super().setUp()
        self.group = _create_group_db(self.alice, 'SOS G', 'PUBLIC')
        _add_member(self.group, self.bob)

    def test_send_requires_membership(self):
        carol_acc = _create_account(self.instance, 'carol')
        carol = _create_profile(carol_acc, self.instance)
        with self.assertRaises(HttpError) as ctx:
            send_sos(self._req(carol, 'post'), self.group.id, SOSInput(level='INFO'))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_send_and_duplicate_blocked(self):
        result = send_sos(self._req(self.alice, 'post'), self.group.id,
                          SOSInput(level='EMERGENCY', message='help'))
        self.assertEqual(result.status, 'ACTIVE')
        with self.assertRaises(HttpError) as ctx:
            send_sos(self._req(self.alice, 'post'), self.group.id, SOSInput(level='INFO'))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_respond_flow(self):
        alert = SOSAlert.objects.create(group=self.group, sender=self.alice, level='EMERGENCY')

        # sender can't respond to own alert
        with self.assertRaises(HttpError) as ctx:
            respond_to_sos(self._req(self.alice, 'post'), alert.id,
                           SOSResponseInput(status='SEEN'))
        self.assertEqual(ctx.exception.status_code, 400)

        result = respond_to_sos(self._req(self.bob, 'post'), alert.id,
                                SOSResponseInput(status='ON_WAY'))
        self.assertEqual(result['seen_count'], 1)
        self.assertEqual(result['responding_count'], 1)

        # updating own response doesn't duplicate
        result = respond_to_sos(self._req(self.bob, 'post'), alert.id,
                                SOSResponseInput(status='UNABLE'))
        self.assertEqual(result['seen_count'], 1)
        self.assertEqual(result['responding_count'], 0)

    def test_resolve_only_sender_or_admin(self):
        alert = SOSAlert.objects.create(group=self.group, sender=self.alice, level='WARNING')
        carol_acc = _create_account(self.instance, 'carol')
        carol = _create_profile(carol_acc, self.instance)
        _add_member(self.group, carol)

        with self.assertRaises(HttpError) as ctx:
            resolve_sos(self._req(carol, 'post'), alert.id)
        self.assertEqual(ctx.exception.status_code, 403)

        result = resolve_sos(self._req(self.alice, 'post'), alert.id, false_alarm=True)
        self.assertEqual(result['status'], SOSAlert.Status.FALSE_ALARM)


# ===========================================================================
# Invites
# ===========================================================================

@override_settings(RATELIMIT_ENABLE=False)
class InviteTest(ParasosTestBase):

    def setUp(self):
        super().setUp()
        self.group = _create_group_db(self.alice, 'Inv G', 'PRIVATE')

    def test_create_requires_admin(self):
        _add_member(self.group, self.bob)
        with self.assertRaises(HttpError) as ctx:
            create_invite(self._req(self.bob, 'post'), self.group.id, InviteCreateInput())
        self.assertEqual(ctx.exception.status_code, 403)

    def test_create_and_public_info(self):
        result = create_invite(self._req(self.alice, 'post'), self.group.id, InviteCreateInput())
        self.assertTrue(result.is_valid)

        # public info endpoint works without auth
        anon = self.factory.get('/fake/')
        info = get_invite_info(anon, result.token)
        self.assertEqual(info['group_id'], self.group.id)
        self.assertTrue(info['is_valid'])

    def test_delete_deactivates(self):
        invite = GroupInvite.objects.create(group=self.group, created_by=self.alice)
        delete_invite(self._req(self.alice, 'delete'), invite.id)
        invite.refresh_from_db()
        self.assertFalse(invite.is_active)
