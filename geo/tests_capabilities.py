"""
Tests for the organization capability layer (`geo/permissions.py`) and the
endpoints that ask it: transit management, dispatch.

Invariants:
- capabilities are the single source; the legacy `*_ROLES` constants are aliases
- MEMBER (the self-service entry role) holds nothing
- an agency run by an organization is reachable through membership, and a
  dispatcher only ever sees their own operator's vehicles
"""

from unittest.mock import patch

from django.test import TestCase, SimpleTestCase, RequestFactory
from ninja.errors import HttpError

from geo.models import Agency, EstablishmentMembership, Route, TransitDataSource
from geo.permissions import (
    AUDITOR_MGMT_ROLES, DRIVING_ROLES, POSTING_ROLES, ROLE_CAPABILITIES,
    SIGNING_ROLES, TREASURER_MGMT_ROLES, agencies_for_capability,
    can_operate_agency, capability_roles, establishment_ids_with_capability,
    has_capability, require_capability,
)
from geo.tests import (
    _create_account, _create_establishment, _create_instance, _create_profile,
    _make_auth_request,
)
from iot.models import IoTDevice, VehicleAssignment


class CapabilityMapTest(SimpleTestCase):
    """The map is the contract."""

    def test_legacy_role_sets_are_aliases(self):
        self.assertIs(POSTING_ROLES, ROLE_CAPABILITIES['content.post'])
        self.assertIs(SIGNING_ROLES, ROLE_CAPABILITIES['content.sign'])
        self.assertIs(TREASURER_MGMT_ROLES, ROLE_CAPABILITIES['finance.treasury'])
        self.assertIs(AUDITOR_MGMT_ROLES, ROLE_CAPABILITIES['finance.audit'])
        self.assertIs(DRIVING_ROLES, ROLE_CAPABILITIES['transit.drive'])

    def test_member_holds_nothing(self):
        """The entry role a self-service join hands out grants no capability."""
        for capability, roles in ROLE_CAPABILITIES.items():
            with self.subTest(capability=capability):
                self.assertNotIn('MEMBER', roles)

    def test_unknown_capability_raises(self):
        with self.assertRaises(ValueError):
            capability_roles('transit.teleport')


class HasCapabilityTest(TestCase):
    def setUp(self):
        self.instance = _create_instance()
        self.owner_acc = _create_account(self.instance, 'alice')
        self.owner = _create_profile(self.owner_acc, self.instance)
        self.est = _create_establishment(self.owner, name='Operator', slug='operator')

    def _member(self, username, role):
        acc = _create_account(self.instance, username)
        profile = _create_profile(acc, self.instance, local_name=username)
        EstablishmentMembership.objects.create(
            profile=profile, establishment=self.est, role=role,
        )
        return acc, profile

    def test_owner_without_membership_row_holds_management(self):
        """`Establishment.owner` is an implicit OWNER — no membership row needed."""
        self.assertFalse(
            EstablishmentMembership.objects.filter(profile=self.owner).exists()
        )
        self.assertTrue(has_capability(self.owner, self.est, 'transit.manage'))
        self.assertTrue(has_capability(self.owner, self.est.id, 'transit.manage'))

    def test_employee_dispatches_but_does_not_manage(self):
        _, employee = self._member('bob', 'EMPLOYEE')
        self.assertTrue(has_capability(employee, self.est, 'transit.dispatch'))
        self.assertTrue(has_capability(employee, self.est, 'content.post'))
        self.assertFalse(has_capability(employee, self.est, 'transit.manage'))
        self.assertFalse(has_capability(employee, self.est, 'members.manage'))

    def test_contractor_drives_only(self):
        _, contractor = self._member('carol', 'CONTRACTOR')
        self.assertTrue(has_capability(contractor, self.est, 'transit.drive'))
        self.assertTrue(has_capability(contractor, self.est, 'tickets.validate'))
        self.assertFalse(has_capability(contractor, self.est, 'transit.dispatch'))
        self.assertFalse(has_capability(contractor, self.est, 'content.post'))

    def test_member_holds_nothing(self):
        _, member = self._member('dave', 'MEMBER')
        for capability in ROLE_CAPABILITIES:
            with self.subTest(capability=capability):
                self.assertFalse(has_capability(member, self.est, capability))

    def test_outsider_and_anonymous(self):
        acc = _create_account(self.instance, 'erin')
        outsider = _create_profile(acc, self.instance, local_name='erin')
        self.assertFalse(has_capability(outsider, self.est, 'content.post'))
        self.assertFalse(has_capability(None, self.est, 'content.post'))

    def test_require_capability_raises(self):
        acc = _create_account(self.instance, 'frank')
        outsider = _create_profile(acc, self.instance, local_name='frank')

        self.assertEqual(
            require_capability(self.est.id, self.owner, 'transit.manage').id, self.est.id
        )

        with self.assertRaises(HttpError) as ctx:
            require_capability(self.est.id, outsider, 'transit.manage')
        self.assertEqual(ctx.exception.status_code, 403)

        with self.assertRaises(HttpError) as ctx:
            require_capability('01ZZZZZZZZZZZZZZZZZZZZZZZZ', self.owner, 'transit.manage')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_inactive_establishment_is_gone(self):
        """A deactivated organization grants nothing, by every entry point."""
        _, employee = self._member('heidi', 'EMPLOYEE')
        self.est.is_active = False
        self.est.save(update_fields=['is_active'])

        with self.assertRaises(HttpError) as ctx:
            require_capability(self.est.id, self.owner, 'transit.manage')
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertNotIn(
            self.est.id, establishment_ids_with_capability(self.owner, 'transit.manage')
        )
        self.est.refresh_from_db()
        self.assertFalse(has_capability(self.owner, self.est, 'transit.manage'))
        self.assertFalse(has_capability(self.owner, self.est.id, 'transit.manage'))
        self.assertFalse(has_capability(employee, self.est.id, 'content.post'))

    def test_ids_with_capability_covers_owned_and_joined(self):
        _, employee = self._member('grace', 'EMPLOYEE')
        own = _create_establishment(employee, name='Side Business', slug='side-business')

        ids = establishment_ids_with_capability(employee, 'content.post')
        self.assertEqual(ids, {self.est.id, own.id})
        self.assertEqual(
            establishment_ids_with_capability(employee, 'transit.manage'), {own.id},
        )


class AgencyAccessTest(TestCase):
    """Agency access follows the organization, not the account that created it."""

    def setUp(self):
        self.instance = _create_instance()
        self.factory = RequestFactory()

        self.boss_acc = _create_account(self.instance, 'alice')
        self.boss = _create_profile(self.boss_acc, self.instance)
        self.est = _create_establishment(self.boss, name='Municipal Operator', slug='cm-operator')

        self.admin_acc = _create_account(self.instance, 'bob')
        self.admin = _create_profile(self.admin_acc, self.instance, local_name='bob')
        EstablishmentMembership.objects.create(
            profile=self.admin, establishment=self.est, role='ADMIN',
        )

        self.employee_acc = _create_account(self.instance, 'carol')
        self.employee = _create_profile(self.employee_acc, self.instance, local_name='carol')
        EstablishmentMembership.objects.create(
            profile=self.employee, establishment=self.est, role='EMPLOYEE',
        )

        self.outsider_acc = _create_account(self.instance, 'dave')
        self.outsider = _create_profile(self.outsider_acc, self.instance, local_name='dave')

        self.ds = TransitDataSource.objects.create(name='DS', slug='ds', is_active=True)
        self.org_agency = Agency.objects.create(
            name='Municipal Operator', data_source=self.ds, source_id='cm',
            establishment=self.est, is_managed=True,
        )

    def test_check_agency_access(self):
        from geo.endpoints.transit_manage import _check_agency_access

        request = _make_auth_request(self.factory, self.admin_acc, self.admin)
        self.assertEqual(_check_agency_access(request, self.org_agency), self.admin)

        for acc, profile in ((self.employee_acc, self.employee), (self.outsider_acc, self.outsider)):
            with self.subTest(profile=profile.local_name):
                request = _make_auth_request(self.factory, acc, profile)
                with self.assertRaises(HttpError) as ctx:
                    _check_agency_access(request, self.org_agency)
                self.assertEqual(ctx.exception.status_code, 403)

    def test_agencies_for_capability(self):
        solo = Agency.objects.create(
            name='Solo', data_source=self.ds, source_id='solo',
            owner=self.outsider, is_managed=True,
        )

        self.assertEqual(
            set(agencies_for_capability(self.admin, 'transit.manage').values_list('id', flat=True)),
            {self.org_agency.id},
        )
        self.assertEqual(
            set(agencies_for_capability(self.outsider, 'transit.manage').values_list('id', flat=True)),
            {solo.id},
        )
        self.assertFalse(
            agencies_for_capability(self.employee, 'transit.manage').exists()
        )
        self.assertTrue(
            agencies_for_capability(self.employee, 'transit.dispatch').exists()
        )

    def test_create_agency_for_organization_has_no_personal_owner(self):
        from geo.endpoints.transit_manage import create_agency, AgencyCreateIn

        est = _create_establishment(self.boss, name='Second Org', slug='second-org')
        EstablishmentMembership.objects.create(
            profile=self.admin, establishment=est, role='ADMIN',
        )

        request = _make_auth_request(self.factory, self.admin_acc, self.admin, 'post')
        out = create_agency(request, AgencyCreateIn(name='Second Org Transit', establishment_id=est.id))

        agency = Agency.objects.get(id=out.id)
        self.assertEqual(agency.establishment_id, est.id)
        self.assertIsNone(agency.owner_id)
        self.assertEqual(out.establishment_name, 'Second Org')
        # Access survives the creator leaving
        EstablishmentMembership.objects.filter(profile=self.admin, establishment=est).delete()
        self.assertFalse(can_operate_agency(self.admin, agency, 'transit.manage'))
        self.assertTrue(can_operate_agency(self.boss, agency, 'transit.manage'))

    def test_create_agency_requires_capability(self):
        from geo.endpoints.transit_manage import create_agency, AgencyCreateIn

        request = _make_auth_request(self.factory, self.employee_acc, self.employee, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_agency(request, AgencyCreateIn(name='Not Mine', establishment_id=self.est.id))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_staff_may_attach_any_organization(self):
        """Setting up a pilot for a municipality is a staff job, not a membership."""
        from geo.endpoints.transit_manage import create_agency, AgencyCreateIn

        est = _create_establishment(self.boss, name='Third Org', slug='third-org')
        staff_acc = _create_account(self.instance, 'admin', is_staff=True)
        staff = _create_profile(staff_acc, self.instance, local_name='admin')

        request = _make_auth_request(self.factory, staff_acc, staff, 'post')
        out = create_agency(request, AgencyCreateIn(name='Third Org Transit', establishment_id=est.id))
        self.assertEqual(Agency.objects.get(id=out.id).establishment_id, est.id)

    def test_one_agency_per_organization(self):
        from geo.endpoints.transit_manage import create_agency, AgencyCreateIn

        request = _make_auth_request(self.factory, self.admin_acc, self.admin, 'post')
        with self.assertRaises(HttpError) as ctx:
            create_agency(request, AgencyCreateIn(name='Duplicate', establishment_id=self.est.id))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_handover_of_a_solo_agency(self):
        from geo.endpoints.transit_manage import update_agency, AgencyCreateIn

        est = _create_establishment(self.boss, name='New Home', slug='new-home')
        solo = Agency.objects.create(
            name='Solo', data_source=TransitDataSource.objects.create(name='DS2', slug='ds2'),
            source_id='solo', owner=self.boss, is_managed=True,
        )

        request = _make_auth_request(self.factory, self.boss_acc, self.boss, 'patch')
        update_agency(request, solo.id, AgencyCreateIn(name='Solo', establishment_id=est.id))

        solo.refresh_from_db()
        self.assertEqual(solo.establishment_id, est.id)
        self.assertIsNone(solo.owner_id)


@patch('iot.endpoints.dispatch.TraccarService.invalidate_assignment_cache')
@patch('iot.endpoints.dispatch.TraccarService.get_positions_from_redis', return_value={})
class DispatchScopeTest(TestCase):
    """A dispatcher sees their operator's vehicles and nobody else's."""

    def setUp(self):
        self.instance = _create_instance()
        self.factory = RequestFactory()

        self.boss_acc = _create_account(self.instance, 'alice')
        self.boss = _create_profile(self.boss_acc, self.instance)
        self.est = _create_establishment(self.boss, name='Operator A', slug='operator-a')

        self.dispatcher_acc = _create_account(self.instance, 'bob')
        self.dispatcher = _create_profile(self.dispatcher_acc, self.instance, local_name='bob')
        EstablishmentMembership.objects.create(
            profile=self.dispatcher, establishment=self.est, role='EMPLOYEE',
        )

        self.stranger_acc = _create_account(self.instance, 'carol')
        self.stranger = _create_profile(self.stranger_acc, self.instance, local_name='carol')

        self.ds = TransitDataSource.objects.create(name='DS A', slug='ds-a', is_active=True)
        self.agency = Agency.objects.create(
            name='Operator A', data_source=self.ds, source_id='a',
            establishment=self.est, is_managed=True,
        )
        self.route = Route.objects.create(
            agency=self.agency, source_id='route-a', short_name='A1', route_type=3,
        )

        self.other_ds = TransitDataSource.objects.create(name='DS B', slug='ds-b', is_active=True)
        self.other_agency = Agency.objects.create(
            name='Operator B', data_source=self.other_ds, source_id='b',
        )
        self.other_route = Route.objects.create(
            agency=self.other_agency, source_id='route-b', short_name='B1', route_type=3,
        )

        self.device = self._device('Bus 1', self.dispatcher, 1001)
        self.other_device = self._device('Bus 2', self.stranger, 1002)

    def _device(self, name, owner, traccar_id):
        # traccar_device_id set so the post_save sync thread stays out of tests
        return IoTDevice.objects.create(
            name=name, device_type='TRACKER', owner=owner,
            device_id=name.replace(' ', '-').lower(), traccar_device_id=traccar_id,
        )

    def _assignment(self, device, route, date='2026-08-14'):
        return VehicleAssignment.objects.create(
            device=device, route=route, data_source=route.agency.data_source, date=date,
            created_by=device.owner,
        )

    def test_non_dispatcher_denied(self, *mocks):
        from iot.endpoints.dispatch import list_assignments

        request = _make_auth_request(self.factory, self.stranger_acc, self.stranger)
        with self.assertRaises(HttpError) as ctx:
            list_assignments(request)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_list_scoped_to_own_operator(self, *mocks):
        from iot.endpoints.dispatch import list_assignments

        mine = self._assignment(self.device, self.route)
        self._assignment(self.other_device, self.other_route)

        request = _make_auth_request(self.factory, self.dispatcher_acc, self.dispatcher,
                                     path='/fake/?date=2026-08-14')
        result = list_assignments(request)
        self.assertEqual([a.id for a in result], [mine.id])

    def test_staff_sees_every_operator(self, *mocks):
        from iot.endpoints.dispatch import list_assignments

        staff_acc = _create_account(self.instance, 'admin', is_staff=True)
        staff = _create_profile(staff_acc, self.instance, local_name='admin')
        self._assignment(self.device, self.route)
        self._assignment(self.other_device, self.other_route)

        request = _make_auth_request(self.factory, staff_acc, staff, path='/fake/?date=2026-08-14')
        self.assertEqual(len(list_assignments(request)), 2)

    def test_detail_of_a_foreign_assignment_is_404(self, *mocks):
        from iot.endpoints.dispatch import get_assignment
        from django.http import Http404

        foreign = self._assignment(self.other_device, self.other_route)

        request = _make_auth_request(self.factory, self.dispatcher_acc, self.dispatcher)
        with self.assertRaises(Http404):
            get_assignment(request, foreign.id)

    def test_create_on_a_foreign_route_denied(self, *mocks):
        from iot.endpoints.dispatch import create_assignment, AssignmentCreateIn

        request = _make_auth_request(self.factory, self.dispatcher_acc, self.dispatcher, 'post')
        payload = AssignmentCreateIn(
            device_id=self.device.id, route_id=self.other_route.id, date='2026-08-14',
        )
        with self.assertRaises(HttpError) as ctx:
            create_assignment(request, payload)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(VehicleAssignment.objects.count(), 0)

    def test_create_with_a_foreign_device_denied(self, *mocks):
        from iot.endpoints.dispatch import create_assignment, AssignmentCreateIn

        request = _make_auth_request(self.factory, self.dispatcher_acc, self.dispatcher, 'post')
        payload = AssignmentCreateIn(
            device_id=self.other_device.id, route_id=self.route.id, date='2026-08-14',
        )
        with self.assertRaises(HttpError) as ctx:
            create_assignment(request, payload)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(VehicleAssignment.objects.count(), 0)

    def test_create_on_own_route(self, *mocks):
        from iot.endpoints.dispatch import create_assignment, AssignmentCreateIn

        request = _make_auth_request(self.factory, self.dispatcher_acc, self.dispatcher, 'post')
        payload = AssignmentCreateIn(
            device_id=self.device.id, route_id=self.route.id, date='2026-08-14',
        )
        out = create_assignment(request, payload)
        self.assertEqual(out.route_id, self.route.id)
        self.assertEqual(VehicleAssignment.objects.count(), 1)

    def test_device_list_excludes_other_peoples_trackers(self, *mocks):
        from iot.endpoints.dispatch import list_available_devices

        request = _make_auth_request(self.factory, self.dispatcher_acc, self.dispatcher)
        self.assertEqual([d.id for d in list_available_devices(request)], [self.device.id])

    def test_route_list_scoped_to_own_operator(self, *mocks):
        from iot.endpoints.dispatch import list_dispatch_routes
        from django.utils import timezone as tz

        today = tz.localdate()
        self._assignment(self.device, self.route, date=today)
        self._assignment(self.other_device, self.other_route, date=today)

        request = _make_auth_request(self.factory, self.dispatcher_acc, self.dispatcher)
        self.assertEqual([r.id for r in list_dispatch_routes(request)], [self.route.id])
