"""
Tests for member management: hiring, role changes, invitations and join requests.

Invariants:
- a role is never handed out above the granter's own level
- authority (ADMIN and up) is never created without the person accepting it;
  taking authority away needs no consent
- a pending proposal is not a membership row, so it grants nothing
- a link invite is bearer authority and may not carry a role that grants further
"""

from datetime import timedelta

from django.test import TestCase, SimpleTestCase, RequestFactory
from django.utils import timezone
from ninja.errors import HttpError

from geo.models import Establishment, EstablishmentInvite, EstablishmentMembership
from geo.permissions import DIRECT_GRANT_ROLES, ROLE_RANK, actor_rank, role_rank
from geo.endpoints.members import (
    accept_invite, add_member, create_invite, decline_invite, get_invite,
    list_invites, my_invites, remove_member, update_member, withdraw_invite,
    InviteCreateIn, MemberHireIn, MemberPatchIn,
)
from geo.tests import (
    _create_account, _create_establishment, _create_instance, _create_profile,
    _make_auth_request,
)


class RoleRankTest(SimpleTestCase):
    """The delegation rule is this comparison and nothing else."""

    def test_owner_outranks_admin_outranks_hires(self):
        self.assertGreater(role_rank('OWNER'), role_rank('ADMIN'))
        self.assertGreater(role_rank('ADMIN'), role_rank('EMPLOYEE'))
        self.assertEqual(role_rank('EMPLOYEE'), role_rank('CONTRACTOR'))
        self.assertGreater(role_rank('EMPLOYEE'), role_rank('MEMBER'))

    def test_unknown_role_ranks_below_member(self):
        self.assertLess(role_rank('SYSADMIN'), ROLE_RANK['MEMBER'])

    def test_every_role_has_a_rank(self):
        """A role missing from the ladder would sit under it and be grantable by anyone."""
        self.assertEqual(set(ROLE_RANK), set(EstablishmentMembership.Role.values))

    def test_only_hired_roles_are_direct(self):
        """Everything else needs the person to say yes."""
        self.assertEqual(DIRECT_GRANT_ROLES, {'EMPLOYEE', 'CONTRACTOR'})


class MembershipTestBase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.instance = _create_instance()
        self.owner_acc = _create_account(self.instance, 'alice')
        self.owner = _create_profile(self.owner_acc, self.instance)
        self.est = _create_establishment(self.owner, name='Câmara', slug='camara')

        self.admin_acc, self.admin = self._person('bob')
        EstablishmentMembership.objects.create(
            profile=self.admin, establishment=self.est, role='ADMIN')
        self.outsider_acc, self.outsider = self._person('carol')

    def _person(self, username):
        acc = _create_account(self.instance, username)
        return acc, _create_profile(acc, self.instance, local_name=username)

    def _member(self, username, role='MEMBER'):
        acc, profile = self._person(username)
        EstablishmentMembership.objects.create(
            profile=profile, establishment=self.est, role=role)
        return acc, profile

    def _req(self, account, profile, method='post', staff=False):
        account.is_staff = staff
        return _make_auth_request(self.factory, account, profile, method)

    def _assert_http(self, code, fn, *args, **kwargs):
        with self.assertRaises(HttpError) as ctx:
            fn(*args, **kwargs)
        self.assertEqual(ctx.exception.status_code, code)
        return ctx.exception


class ActorRankTest(MembershipTestBase):
    def test_owner_field_ranks_as_owner_without_a_membership_row(self):
        self.assertFalse(EstablishmentMembership.objects.filter(profile=self.owner).exists())
        self.assertEqual(actor_rank(self.owner, self.est), ROLE_RANK['OWNER'])

    def test_outsider_ranks_below_member(self):
        self.assertEqual(actor_rank(self.outsider, self.est), -1)
        self.assertEqual(actor_rank(None, self.est), -1)

    def test_membership_row_decides_for_everyone_else(self):
        self.assertEqual(actor_rank(self.admin, self.est), ROLE_RANK['ADMIN'])


class HireTest(MembershipTestBase):
    def test_admin_hires_an_employee_directly(self):
        _, target = self._person('dave')
        out = add_member(
            self._req(self.admin_acc, self.admin, 'put'), self.est.id, target.id,
            MemberHireIn(role='EMPLOYEE', position_title='Motorista'),
        )
        self.assertEqual(out.role, 'EMPLOYEE')
        self.assertEqual(out.position_title, 'Motorista')
        self.assertTrue(EstablishmentMembership.objects.filter(
            establishment=self.est, profile=target, role='EMPLOYEE').exists())

    def test_admin_cannot_be_assigned_directly(self):
        """Authority needs acceptance — the hire path refuses it."""
        _, target = self._person('dave')
        self._assert_http(
            400, add_member, self._req(self.admin_acc, self.admin, 'put'),
            self.est.id, target.id, MemberHireIn(role='ADMIN'),
        )
        self.assertFalse(EstablishmentMembership.objects.filter(profile=target).exists())

    def test_member_cannot_hire(self):
        _, plain = self._member('erin', 'MEMBER')
        _, target = self._person('dave')
        self._assert_http(
            403, add_member, self._req(plain.account, plain, 'put'),
            self.est.id, target.id, MemberHireIn(role='EMPLOYEE'),
        )

    def test_employee_cannot_hire(self):
        """`members.manage` is OWNER/ADMIN — a dispatcher does not staff the org."""
        _, employee = self._member('frank', 'EMPLOYEE')
        _, target = self._person('dave')
        self._assert_http(
            403, add_member, self._req(employee.account, employee, 'put'),
            self.est.id, target.id, MemberHireIn(role='EMPLOYEE'),
        )

    def test_existing_member_is_rejected(self):
        _, plain = self._member('erin', 'MEMBER')
        self._assert_http(
            400, add_member, self._req(self.admin_acc, self.admin, 'put'),
            self.est.id, plain.id, MemberHireIn(role='EMPLOYEE'),
        )

    def test_staff_may_seat_the_first_hire(self):
        """Onboarding a pilot organization happens before anyone inside it can act."""
        staff_acc, staff_profile = self._person('norn')
        _, target = self._person('dave')
        out = add_member(
            self._req(staff_acc, staff_profile, 'put', staff=True), self.est.id, target.id,
            MemberHireIn(role='EMPLOYEE'),
        )
        self.assertEqual(out.role, 'EMPLOYEE')

    def test_inactive_organization_is_gone(self):
        self.est.is_active = False
        self.est.save(update_fields=['is_active'])
        _, target = self._person('dave')
        self._assert_http(
            404, add_member, self._req(self.admin_acc, self.admin, 'put'),
            self.est.id, target.id, MemberHireIn(role='EMPLOYEE'),
        )


class RoleChangeTest(MembershipTestBase):
    def test_owner_demotes_an_admin(self):
        out = update_member(
            self._req(self.owner_acc, self.owner, 'patch'), self.est.id, self.admin.id,
            MemberPatchIn(role='MEMBER'),
        )
        self.assertEqual(out.role, 'MEMBER')

    def test_promotion_into_authority_is_refused(self):
        _, plain = self._member('erin', 'MEMBER')
        self._assert_http(
            400, update_member, self._req(self.owner_acc, self.owner, 'patch'),
            self.est.id, plain.id, MemberPatchIn(role='ADMIN'),
        )
        plain.refresh_from_db()
        self.assertEqual(
            EstablishmentMembership.objects.get(profile=plain, establishment=self.est).role,
            'MEMBER',
        )

    def test_promotion_to_a_hired_role_is_direct(self):
        _, plain = self._member('erin', 'MEMBER')
        out = update_member(
            self._req(self.admin_acc, self.admin, 'patch'), self.est.id, plain.id,
            MemberPatchIn(role='CONTRACTOR'),
        )
        self.assertEqual(out.role, 'CONTRACTOR')

    def test_admin_cannot_reach_the_owner(self):
        _, second_owner = self._member('gina', 'OWNER')
        self._assert_http(
            403, update_member, self._req(self.admin_acc, self.admin, 'patch'),
            self.est.id, second_owner.id, MemberPatchIn(role='MEMBER'),
        )

    def test_owner_field_holder_is_untouchable(self):
        """The organization's owner is not demoted through the member list."""
        EstablishmentMembership.objects.create(
            profile=self.owner, establishment=self.est, role='OWNER')
        staff_acc, staff_profile = self._person('norn')
        self._assert_http(
            403, update_member, self._req(staff_acc, staff_profile, 'patch', staff=True),
            self.est.id, self.owner.id, MemberPatchIn(role='MEMBER'),
        )

    def test_nobody_changes_their_own_role(self):
        self._assert_http(
            400, update_member, self._req(self.admin_acc, self.admin, 'patch'),
            self.est.id, self.admin.id, MemberPatchIn(role='OWNER'),
        )

    def test_position_title_alone_is_allowed(self):
        _, plain = self._member('erin', 'MEMBER')
        out = update_member(
            self._req(self.admin_acc, self.admin, 'patch'), self.est.id, plain.id,
            MemberPatchIn(position_title='Secretária'),
        )
        self.assertEqual(out.position_title, 'Secretária')
        self.assertEqual(out.role, 'MEMBER')

    def test_founder_level_is_owner_only(self):
        """`fundador` mints a WoT seed verifier — an admin must not be able to."""
        _, plain = self._member('erin', 'MEMBER')
        self._assert_http(
            403, update_member, self._req(self.admin_acc, self.admin, 'patch'),
            self.est.id, plain.id, MemberPatchIn(membership_level='fundador'),
        )
        out = update_member(
            self._req(self.owner_acc, self.owner, 'patch'), self.est.id, plain.id,
            MemberPatchIn(membership_level='fundador'),
        )
        self.assertEqual(out.membership_level, 'fundador')

    def test_admin_may_grant_the_lower_levels(self):
        _, plain = self._member('erin', 'MEMBER')
        out = update_member(
            self._req(self.admin_acc, self.admin, 'patch'), self.est.id, plain.id,
            MemberPatchIn(membership_level='efetivo'),
        )
        self.assertEqual(out.membership_level, 'efetivo')

    def test_unknown_level_is_rejected(self):
        _, plain = self._member('erin', 'MEMBER')
        self._assert_http(
            400, update_member, self._req(self.owner_acc, self.owner, 'patch'),
            self.est.id, plain.id, MemberPatchIn(membership_level='presidente'),
        )

    def test_non_member_is_not_found(self):
        self._assert_http(
            404, update_member, self._req(self.owner_acc, self.owner, 'patch'),
            self.est.id, self.outsider.id, MemberPatchIn(role='MEMBER'),
        )


class RemoveMemberTest(MembershipTestBase):
    def test_admin_removes_a_member(self):
        _, plain = self._member('erin', 'MEMBER')
        remove_member(self._req(self.admin_acc, self.admin, 'delete'), self.est.id, plain.id)
        self.assertFalse(EstablishmentMembership.objects.filter(
            establishment=self.est, profile=plain).exists())

    def test_admin_cannot_remove_the_owner(self):
        EstablishmentMembership.objects.create(
            profile=self.owner, establishment=self.est, role='OWNER')
        self._assert_http(
            403, remove_member, self._req(self.admin_acc, self.admin, 'delete'),
            self.est.id, self.owner.id,
        )

    def test_removing_yourself_points_at_leave(self):
        self._assert_http(
            400, remove_member, self._req(self.admin_acc, self.admin, 'delete'),
            self.est.id, self.admin.id,
        )


class InviteTest(MembershipTestBase):
    def _invite(self, actor_acc, actor, **kwargs):
        return create_invite(self._req(actor_acc, actor), self.est.id, InviteCreateIn(**kwargs))

    def test_targeted_invite_creates_no_membership(self):
        _, target = self._person('dave')
        inv = self._invite(self.admin_acc, self.admin, profile_id=target.id, role='ADMIN')
        self.assertEqual(inv.status, 'PENDING')
        self.assertIsNone(inv.token)
        self.assertFalse(EstablishmentMembership.objects.filter(profile=target).exists())

    def test_accepting_grants_the_role(self):
        target_acc, target = self._person('dave')
        inv = self._invite(self.admin_acc, self.admin, profile_id=target.id, role='ADMIN',
                           position_title='Vice-Presidente')
        accept_invite(self._req(target_acc, target), inv.id)

        membership = EstablishmentMembership.objects.get(establishment=self.est, profile=target)
        self.assertEqual(membership.role, 'ADMIN')
        self.assertEqual(membership.position_title, 'Vice-Presidente')
        self.assertEqual(
            EstablishmentInvite.objects.get(id=inv.id).status, 'ACCEPTED')

    def test_someone_else_cannot_accept_a_named_invite(self):
        _, target = self._person('dave')
        inv = self._invite(self.admin_acc, self.admin, profile_id=target.id, role='ADMIN')
        self._assert_http(403, accept_invite, self._req(self.outsider_acc, self.outsider), inv.id)

    def test_admin_cannot_invite_an_owner(self):
        _, target = self._person('dave')
        self._assert_http(
            403, self._invite, self.admin_acc, self.admin, profile_id=target.id, role='OWNER')

    def test_owner_may_invite_an_owner(self):
        _, target = self._person('dave')
        inv = self._invite(self.owner_acc, self.owner, profile_id=target.id, role='OWNER')
        self.assertEqual(inv.role, 'OWNER')

    def test_invite_by_handle(self):
        _, target = self._person('dave')
        inv = self._invite(self.admin_acc, self.admin, hna=f'@{target.hna}', role='EMPLOYEE')
        self.assertEqual(inv.target_profile_id, target.id)

    def test_unknown_handle_is_not_found(self):
        self._assert_http(
            404, self._invite, self.admin_acc, self.admin, hna='nobody@test.parahub.io')

    def test_reinviting_replaces_the_pending_offer(self):
        _, target = self._person('dave')
        first = self._invite(self.admin_acc, self.admin, profile_id=target.id, role='MEMBER')
        second = self._invite(self.admin_acc, self.admin, profile_id=target.id, role='EMPLOYEE')
        self.assertEqual(first.id, second.id)
        self.assertEqual(EstablishmentInvite.objects.filter(target_profile=target).count(), 1)
        self.assertEqual(second.role, 'EMPLOYEE')

    def test_existing_member_cannot_be_invited(self):
        _, plain = self._member('erin', 'MEMBER')
        self._assert_http(
            400, self._invite, self.admin_acc, self.admin, profile_id=plain.id, role='EMPLOYEE')

    def test_expired_invite_is_refused(self):
        target_acc, target = self._person('dave')
        inv = self._invite(self.admin_acc, self.admin, profile_id=target.id, role='EMPLOYEE')
        EstablishmentInvite.objects.filter(id=inv.id).update(
            expires_at=timezone.now() - timedelta(hours=1))
        self._assert_http(400, accept_invite, self._req(target_acc, target), inv.id)
        self.assertFalse(EstablishmentMembership.objects.filter(profile=target).exists())

    def test_declining_leaves_no_membership(self):
        target_acc, target = self._person('dave')
        inv = self._invite(self.admin_acc, self.admin, profile_id=target.id, role='EMPLOYEE')
        decline_invite(self._req(target_acc, target), inv.id)
        self.assertEqual(EstablishmentInvite.objects.get(id=inv.id).status, 'DECLINED')
        self.assertFalse(EstablishmentMembership.objects.filter(profile=target).exists())

    def test_a_resolved_invite_cannot_be_reused(self):
        target_acc, target = self._person('dave')
        inv = self._invite(self.admin_acc, self.admin, profile_id=target.id, role='EMPLOYEE')
        accept_invite(self._req(target_acc, target), inv.id)
        self._assert_http(400, accept_invite, self._req(target_acc, target), inv.id)

    def test_organization_withdraws_an_offer(self):
        target_acc, target = self._person('dave')
        inv = self._invite(self.admin_acc, self.admin, profile_id=target.id, role='EMPLOYEE')
        withdraw_invite(self._req(self.admin_acc, self.admin, 'delete'), inv.id)
        self._assert_http(400, accept_invite, self._req(target_acc, target), inv.id)

    def test_outsider_cannot_invite(self):
        self._assert_http(
            403, self._invite, self.outsider_acc, self.outsider, role='MEMBER')


class LinkInviteTest(MembershipTestBase):
    def test_link_invite_carries_a_token(self):
        inv = create_invite(
            self._req(self.admin_acc, self.admin), self.est.id,
            InviteCreateIn(role='EMPLOYEE'),
        )
        self.assertTrue(inv.token)
        self.assertIsNone(inv.target_profile_id)

    def test_whoever_holds_the_link_becomes_the_member(self):
        inv = create_invite(
            self._req(self.admin_acc, self.admin), self.est.id,
            InviteCreateIn(role='EMPLOYEE'),
        )
        accept_invite(self._req(self.outsider_acc, self.outsider), inv.token)
        membership = EstablishmentMembership.objects.get(
            establishment=self.est, profile=self.outsider)
        self.assertEqual(membership.role, 'EMPLOYEE')
        self.assertEqual(
            EstablishmentInvite.objects.get(id=inv.id).target_profile_id, self.outsider.id)

    def test_a_link_is_single_use(self):
        """The secret can be forwarded — the offer behind it cannot be reused."""
        inv = create_invite(
            self._req(self.admin_acc, self.admin), self.est.id,
            InviteCreateIn(role='EMPLOYEE'),
        )
        accept_invite(self._req(self.outsider_acc, self.outsider), inv.token)
        second_acc, second = self._person('dave')
        self._assert_http(400, accept_invite, self._req(second_acc, second), inv.token)
        self.assertFalse(EstablishmentMembership.objects.filter(profile=second).exists())

    def test_the_id_alone_does_not_open_a_link_invite(self):
        """Without the secret it is not an invitation to anyone."""
        inv = create_invite(
            self._req(self.admin_acc, self.admin), self.est.id,
            InviteCreateIn(role='EMPLOYEE'),
        )
        self._assert_http(403, accept_invite, self._req(self.outsider_acc, self.outsider), inv.id)

    def test_authority_may_not_be_sent_as_a_link(self):
        """A leaked link must never cost the organization control of itself."""
        self._assert_http(
            400, create_invite, self._req(self.owner_acc, self.owner), self.est.id,
            InviteCreateIn(role='ADMIN'),
        )

    def test_token_is_hidden_from_the_recipient(self):
        target_acc, target = self._person('dave')
        inv = create_invite(
            self._req(self.admin_acc, self.admin), self.est.id,
            InviteCreateIn(profile_id=target.id, role='EMPLOYEE'),
        )
        seen = get_invite(self._req(target_acc, target, 'get'), inv.id)
        self.assertIsNone(seen.token)
        by_org = get_invite(self._req(self.admin_acc, self.admin, 'get'), inv.id)
        self.assertEqual(by_org.role, 'EMPLOYEE')

    def test_strangers_cannot_read_a_named_invite(self):
        _, target = self._person('dave')
        inv = create_invite(
            self._req(self.admin_acc, self.admin), self.est.id,
            InviteCreateIn(profile_id=target.id, role='EMPLOYEE'),
        )
        self._assert_http(
            403, get_invite, self._req(self.outsider_acc, self.outsider, 'get'), inv.id)


class JoinRequestTest(MembershipTestBase):
    """`membership_policy=REQUEST`: applying is not joining."""

    def setUp(self):
        super().setUp()
        self.est.membership_policy = Establishment.MembershipPolicy.REQUEST
        self.est.save(update_fields=['membership_policy'])

    def _join(self, account, profile):
        from geo.endpoints.buildings import join_establishment, JoinEstablishmentRequest
        return join_establishment(
            self._req(account, profile), self.est.id, JoinEstablishmentRequest())

    def test_applying_creates_no_membership(self):
        status, body = self._join(self.outsider_acc, self.outsider)
        self.assertEqual(status, 202)
        self.assertEqual(body['status'], 'pending')
        self.assertFalse(EstablishmentMembership.objects.filter(profile=self.outsider).exists())

    def test_applying_twice_returns_the_same_application(self):
        _, first = self._join(self.outsider_acc, self.outsider)
        _, second = self._join(self.outsider_acc, self.outsider)
        self.assertEqual(first['invite_id'], second['invite_id'])
        self.assertEqual(EstablishmentInvite.objects.filter(
            target_profile=self.outsider).count(), 1)

    def test_approval_creates_the_membership(self):
        _, body = self._join(self.outsider_acc, self.outsider)
        accept_invite(self._req(self.admin_acc, self.admin), body['invite_id'])
        membership = EstablishmentMembership.objects.get(
            establishment=self.est, profile=self.outsider)
        self.assertEqual(membership.role, 'MEMBER')
        self.assertEqual(membership.membership_level, 'apoiante')

    def test_an_applicant_cannot_approve_themselves(self):
        _, body = self._join(self.outsider_acc, self.outsider)
        self._assert_http(
            403, accept_invite, self._req(self.outsider_acc, self.outsider), body['invite_id'])

    def test_declining_an_application(self):
        _, body = self._join(self.outsider_acc, self.outsider)
        decline_invite(self._req(self.admin_acc, self.admin), body['invite_id'])
        self.assertFalse(EstablishmentMembership.objects.filter(profile=self.outsider).exists())

    def test_an_applicant_withdraws_their_own_application(self):
        _, body = self._join(self.outsider_acc, self.outsider)
        withdraw_invite(
            self._req(self.outsider_acc, self.outsider, 'delete'), body['invite_id'])
        self.assertEqual(
            EstablishmentInvite.objects.get(id=body['invite_id']).status, 'WITHDRAWN')

    def test_an_admin_cannot_withdraw_someone_elses_application(self):
        """Revoking is for whoever proposed — the organization declines instead."""
        _, body = self._join(self.outsider_acc, self.outsider)
        self._assert_http(
            403, withdraw_invite, self._req(self.admin_acc, self.admin, 'delete'),
            body['invite_id'])

    def test_accepting_an_invite_closes_the_pending_application(self):
        """Both directions may be pending at once; the membership settles both."""
        target_acc, target = self._person('dave')
        est_invite = create_invite(
            self._req(self.admin_acc, self.admin), self.est.id,
            InviteCreateIn(profile_id=target.id, role='EMPLOYEE'))
        _, body = self._join(target_acc, target)
        self.assertNotEqual(est_invite.id, body['invite_id'])

        accept_invite(self._req(target_acc, target), est_invite.id)

        self.assertEqual(
            EstablishmentInvite.objects.get(id=body['invite_id']).status, 'SUPERSEDED')
        self.assertEqual(
            list_invites(self._req(self.admin_acc, self.admin, 'get'), self.est.id), [])

    def test_hiring_closes_the_pending_application(self):
        target_acc, target = self._person('dave')
        _, body = self._join(target_acc, target)
        add_member(self._req(self.admin_acc, self.admin, 'put'), self.est.id, target.id,
                   MemberHireIn(role='EMPLOYEE'))
        self.assertEqual(
            EstablishmentInvite.objects.get(id=body['invite_id']).status, 'SUPERSEDED')

    def test_invite_only_still_refuses(self):
        self.est.membership_policy = Establishment.MembershipPolicy.INVITE
        self.est.save(update_fields=['membership_policy'])
        self._assert_http(403, self._join, self.outsider_acc, self.outsider)

    def test_open_still_joins_immediately(self):
        self.est.membership_policy = Establishment.MembershipPolicy.OPEN
        self.est.save(update_fields=['membership_policy'])
        out = self._join(self.outsider_acc, self.outsider)
        self.assertEqual(out.role, 'MEMBER')
        self.assertTrue(EstablishmentMembership.objects.filter(profile=self.outsider).exists())


class QueueTest(MembershipTestBase):
    def test_organization_sees_both_directions(self):
        _, target = self._person('dave')
        create_invite(self._req(self.admin_acc, self.admin), self.est.id,
                      InviteCreateIn(profile_id=target.id, role='EMPLOYEE'))
        EstablishmentInvite.objects.create(
            establishment=self.est, direction='REQUEST', target_profile=self.outsider,
            created_by=self.outsider, role='MEMBER')

        rows = list_invites(self._req(self.admin_acc, self.admin, 'get'), self.est.id)
        self.assertEqual({r.direction for r in rows}, {'INVITE', 'REQUEST'})

    def test_resolved_rows_stay_as_the_record(self):
        target_acc, target = self._person('dave')
        inv = create_invite(self._req(self.admin_acc, self.admin), self.est.id,
                            InviteCreateIn(profile_id=target.id, role='EMPLOYEE'))
        accept_invite(self._req(target_acc, target), inv.id)

        self.assertEqual(len(list_invites(self._req(self.admin_acc, self.admin, 'get'), self.est.id)), 0)
        history = list_invites(self._req(self.admin_acc, self.admin, 'get'), self.est.id, status='all')
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].status, 'ACCEPTED')
        self.assertEqual(history[0].created_by_hna, self.admin.hna)

    def test_outsider_cannot_read_the_queue(self):
        self._assert_http(
            403, list_invites, self._req(self.outsider_acc, self.outsider, 'get'), self.est.id)

    def test_my_invites_shows_what_waits_on_me(self):
        target_acc, target = self._person('dave')
        create_invite(self._req(self.admin_acc, self.admin), self.est.id,
                      InviteCreateIn(profile_id=target.id, role='EMPLOYEE'))

        rows = my_invites(self._req(target_acc, target, 'get'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].establishment_name, 'Câmara')
        self.assertIsNone(rows[0].token)
        self.assertEqual(len(my_invites(self._req(self.outsider_acc, self.outsider, 'get'))), 0)
