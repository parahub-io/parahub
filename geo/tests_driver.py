"""
Tests for Driver Mode: who may start a shift, and the shift lifecycle.

Invariants:
- a shift injects a vehicle into the route's data source, which the public map
  and that source's GTFS-RT feed serve — so only the operator may start one,
  and an outsider with WoT verifications is still an outsider
- no duplicate active shifts per driver; a stale one (no heartbeat) auto-ends
- stop/active/history are scoped to the shift's own driver
"""

from unittest.mock import patch

from django.test import TestCase, RequestFactory
from django.utils import timezone
from ninja.errors import HttpError

from geo.models import (
    Agency, DriverShift, EstablishmentMembership, Place, Route, TransitDataSource,
)
from geo.endpoints.driver import (
    ShiftStartIn, get_active_shift, shift_history, start_shift, stop_shift,
)
from geo.tests import (
    _create_account, _create_establishment, _create_instance, _create_profile,
    _make_auth_request,
)


def _create_transit_chain():
    """An imported feed: no platform operator behind it."""
    place = Place.objects.create(name='Driver City', slug='driver-city', country_code='PT')
    ds = TransitDataSource.objects.create(name='Driver Source', format='gtfs')
    agency = Agency.objects.create(
        data_source=ds, source_id='DRV', name='Driver Agency',
        timezone='Europe/Lisbon', lang='pt',
    )
    route = Route.objects.create(
        agency=agency, place=place, source_id='BUS1',
        short_name='B1', long_name='Bus Line 1', route_type=3,
    )
    return place, ds, agency, route


class DriverShiftOperatorTest(TestCase):
    """Who may start a shift on which route."""

    def setUp(self):
        self.instance = _create_instance()
        self.factory = RequestFactory()

        # Outsider: WoT-verified, but belongs to no operator
        self.outsider_acc = _create_account(self.instance, 'bob')
        self.outsider = _create_profile(
            self.outsider_acc, self.instance, local_name='bob', is_verified_wot=True,
        )

        self.data_source = TransitDataSource.objects.create(
            name='Test DS', slug='test-ds', is_active=True,
        )

    def _make_route(self, agency):
        return Route.objects.create(
            agency=agency, source_id=f'route-{agency.id[:6]}',
            short_name='1', route_type=3,
        )

    def _start(self, profile, account, route, direction_id=0):
        from geo.endpoints.driver import start_shift, ShiftStartIn

        request = _make_auth_request(self.factory, account, profile, 'post')
        return start_shift(request, ShiftStartIn(route_id=route.id, direction_id=direction_id))

    # --- Imported feeds (no operator on the platform) ---

    def test_outsider_cannot_drive_imported_route(self):
        """The phantom-bus case: a GTFS-imported route has no platform operator."""
        agency = Agency.objects.create(
            name='Imported Operator', data_source=self.data_source, source_id='imported',
        )
        route = self._make_route(agency)

        with self.assertRaises(HttpError) as ctx:
            self._start(self.outsider, self.outsider_acc, route)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(DriverShift.objects.count(), 0)

    def test_staff_may_drive_any_route(self):
        """Staff keeps the override — the platform runs its own pilots."""
        staff_acc = _create_account(self.instance, 'admin', is_staff=True)
        staff = _create_profile(staff_acc, self.instance, local_name='admin')
        agency = Agency.objects.create(
            name='Imported Operator', data_source=self.data_source, source_id='imported',
        )
        route = self._make_route(agency)

        response = self._start(staff, staff_acc, route)
        self.assertEqual(response.route_id, route.id)

    # --- Solo operator (Agency.owner) ---

    def test_agency_owner_drives_own_route(self):
        owner_acc = _create_account(self.instance, 'carol')
        owner = _create_profile(
            owner_acc, self.instance, local_name='carol', is_verified_wot=True,
        )
        agency = Agency.objects.create(
            name='Solo Operator', data_source=self.data_source, source_id='solo',
            owner=owner, is_managed=True,
        )
        route = self._make_route(agency)

        response = self._start(owner, owner_acc, route)
        self.assertEqual(response.route_id, route.id)

    def test_agency_owner_without_wot_denied(self):
        """The solo path keeps the WoT gate: their vehicle lands on the public map."""
        owner_acc = _create_account(self.instance, 'dave')
        owner = _create_profile(owner_acc, self.instance, local_name='dave')
        agency = Agency.objects.create(
            name='Solo Operator', data_source=self.data_source, source_id='solo',
            owner=owner, is_managed=True,
        )
        route = self._make_route(agency)

        with self.assertRaises(HttpError) as ctx:
            self._start(owner, owner_acc, route)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_outsider_cannot_drive_someone_elses_managed_route(self):
        owner_acc = _create_account(self.instance, 'carol')
        owner = _create_profile(owner_acc, self.instance, local_name='carol')
        agency = Agency.objects.create(
            name='Solo Operator', data_source=self.data_source, source_id='solo',
            owner=owner, is_managed=True,
        )
        route = self._make_route(agency)

        with self.assertRaises(HttpError) as ctx:
            self._start(self.outsider, self.outsider_acc, route)
        self.assertEqual(ctx.exception.status_code, 403)

    # --- Organization operator (Agency.establishment) ---

    def test_employee_drives_organization_route_without_wot(self):
        """Employment is the trust anchor — a hired driver has no WoT web."""
        boss_acc = _create_account(self.instance, 'erin')
        boss = _create_profile(boss_acc, self.instance, local_name='erin')
        est = _create_establishment(boss, name='Municipal Operator', slug='municipal-operator')

        driver_acc = _create_account(self.instance, 'frank')
        driver = _create_profile(driver_acc, self.instance, local_name='frank')
        EstablishmentMembership.objects.create(
            profile=driver, establishment=est, role='EMPLOYEE',
        )

        agency = Agency.objects.create(
            name='Municipal Operator', data_source=self.data_source, source_id='municipal',
            establishment=est, is_managed=True,
        )
        route = self._make_route(agency)

        self.assertFalse(driver.is_verified_wot)
        response = self._start(driver, driver_acc, route)
        self.assertEqual(response.route_id, route.id)

    def test_plain_member_cannot_drive_organization_route(self):
        """The entry role is not an employment relation."""
        boss_acc = _create_account(self.instance, 'erin')
        boss = _create_profile(boss_acc, self.instance, local_name='erin')
        est = _create_establishment(boss, name='Municipal Operator', slug='municipal-operator')

        member_acc = _create_account(self.instance, 'grace')
        member = _create_profile(
            member_acc, self.instance, local_name='grace', is_verified_wot=True,
        )
        EstablishmentMembership.objects.create(
            profile=member, establishment=est, role='MEMBER',
        )

        agency = Agency.objects.create(
            name='Municipal Operator', data_source=self.data_source, source_id='municipal',
            establishment=est, is_managed=True,
        )
        route = self._make_route(agency)

        with self.assertRaises(HttpError) as ctx:
            self._start(member, member_acc, route)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_organization_survives_owner_change(self):
        """Access follows the establishment, not one personal account.

        The reason `Agency.establishment` is the primary path: a public body's
        network must not hang on whoever created the agency.
        """
        from geo.permissions import can_operate_agency

        boss_acc = _create_account(self.instance, 'erin')
        boss = _create_profile(boss_acc, self.instance, local_name='erin')
        est = _create_establishment(boss, name='Municipal Operator', slug='municipal-operator')

        admin_acc = _create_account(self.instance, 'heidi')
        admin = _create_profile(admin_acc, self.instance, local_name='heidi')
        EstablishmentMembership.objects.create(
            profile=admin, establishment=est, role='ADMIN',
        )

        agency = Agency.objects.create(
            name='Municipal Operator', data_source=self.data_source, source_id='municipal',
            establishment=est, owner=None, is_managed=True,
        )

        self.assertTrue(can_operate_agency(admin, agency))
        self.assertFalse(can_operate_agency(self.outsider, agency))


# ---------------------------------------------------------------------------
# Shift lifecycle (staff driver — the operator gate is covered above)
# ---------------------------------------------------------------------------

class DriverShiftLifecycleTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.acc = _create_account(self.inst, 'driver', is_staff=True)
        self.profile = _create_profile(self.acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()

    def _req(self, method='post'):
        return _make_auth_request(self.factory, self.acc, self.profile, method)

    def test_start_shift_creates_active(self):
        result = start_shift(self._req(), ShiftStartIn(route_id=str(self.route.id)))
        self.assertEqual(result.status, 'ACTIVE')
        self.assertEqual(result.route_short_name, 'B1')
        self.assertEqual(result.direction_id, 0)
        self.assertTrue(result.vehicle_id.startswith('D'))

    def test_start_shift_with_direction(self):
        result = start_shift(
            self._req(), ShiftStartIn(route_id=str(self.route.id), direction_id=1),
        )
        self.assertEqual(result.direction_id, 1)

    @patch('geo.endpoints.driver._is_heartbeat_alive', return_value=True)
    def test_start_duplicate_active_shift_rejected(self, _mock_hb):
        """Can't start new shift when heartbeat is still alive."""
        start_shift(self._req(), ShiftStartIn(route_id=str(self.route.id)))
        with self.assertRaises(HttpError) as ctx:
            start_shift(self._req(), ShiftStartIn(route_id=str(self.route.id)))
        self.assertEqual(ctx.exception.status_code, 409)

    @patch('geo.endpoints.driver._clean_transit_pipeline')
    @patch('geo.endpoints.driver._is_heartbeat_alive', return_value=False)
    def test_start_auto_ends_stale_shift(self, _mock_hb, _mock_clean):
        """Stale shift (no heartbeat) auto-ends when starting new shift."""
        old = start_shift(self._req(), ShiftStartIn(route_id=str(self.route.id)))
        new = start_shift(self._req(), ShiftStartIn(route_id=str(self.route.id)))
        self.assertEqual(new.status, 'ACTIVE')
        self.assertNotEqual(old.id, new.id)
        old_shift = DriverShift.objects.get(id=old.id)
        self.assertEqual(old_shift.status, 'ENDED')
        self.assertIsNotNone(old_shift.ended_at)

    @patch('geo.endpoints.driver._clean_transit_pipeline')
    def test_stop_shift_success(self, mock_clean):
        shift = DriverShift.objects.create(
            profile=self.profile, route=self.route,
            data_source=self.ds, vehicle_id='Dtest123',
        )
        result = stop_shift(self._req(), str(shift.id))
        self.assertEqual(result.status, 'ENDED')
        self.assertIsNotNone(result.ended_at)
        mock_clean.assert_called_once()

    @patch('geo.endpoints.driver._clean_transit_pipeline')
    def test_stop_already_ended_rejected(self, mock_clean):
        shift = DriverShift.objects.create(
            profile=self.profile, route=self.route,
            data_source=self.ds, vehicle_id='Dtest123',
            status='ENDED', ended_at=timezone.now(),
        )
        with self.assertRaises(HttpError) as ctx:
            stop_shift(self._req(), str(shift.id))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_stop_other_drivers_shift_404(self):
        """Can't stop someone else's shift."""
        acc2 = _create_account(self.inst, 'other_driver', is_staff=True)
        p2 = _create_profile(acc2, self.inst, local_name='other_driver')
        shift = DriverShift.objects.create(
            profile=p2, route=self.route,
            data_source=self.ds, vehicle_id='Dother',
        )
        with self.assertRaises(Exception):
            # get_object_or_404 raises Http404 (Django) for wrong profile
            stop_shift(self._req(), str(shift.id))


# ---------------------------------------------------------------------------
# Active shift / History
# ---------------------------------------------------------------------------

class DriverShiftQueryTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.acc = _create_account(self.inst, 'driver', is_staff=True)
        self.profile = _create_profile(self.acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()

    def _req(self, method='get'):
        return _make_auth_request(self.factory, self.acc, self.profile, method)

    @patch('geo.endpoints.driver._is_heartbeat_alive', return_value=False)
    def test_get_active_shift_returns_shift(self, _mock_hb):
        DriverShift.objects.create(
            profile=self.profile, route=self.route,
            data_source=self.ds, vehicle_id='Dactive',
        )
        status, result = get_active_shift(self._req())
        self.assertEqual(status, 200)
        self.assertEqual(result.status, 'ACTIVE')
        self.assertEqual(result.heartbeat_alive, False)

    @patch('geo.endpoints.driver._is_heartbeat_alive', return_value=True)
    def test_get_active_shift_heartbeat_alive(self, _mock_hb):
        DriverShift.objects.create(
            profile=self.profile, route=self.route,
            data_source=self.ds, vehicle_id='Dactive2',
        )
        status, result = get_active_shift(self._req())
        self.assertEqual(status, 200)
        self.assertEqual(result.heartbeat_alive, True)

    def test_get_active_shift_returns_204_when_none(self):
        status, result = get_active_shift(self._req())
        self.assertEqual(status, 204)
        self.assertIsNone(result)

    def test_get_active_shift_ignores_ended(self):
        DriverShift.objects.create(
            profile=self.profile, route=self.route,
            data_source=self.ds, vehicle_id='Dended',
            status='ENDED', ended_at=timezone.now(),
        )
        status, result = get_active_shift(self._req())
        self.assertEqual(status, 204)

    def test_history_returns_own_shifts(self):
        DriverShift.objects.create(
            profile=self.profile, route=self.route,
            data_source=self.ds, vehicle_id='D1',
            status='ENDED', ended_at=timezone.now(),
        )
        DriverShift.objects.create(
            profile=self.profile, route=self.route,
            data_source=self.ds, vehicle_id='D2',
        )
        result = shift_history(self._req())
        self.assertEqual(len(result), 2)

    def test_history_excludes_other_drivers(self):
        acc2 = _create_account(self.inst, 'other', is_staff=True)
        p2 = _create_profile(acc2, self.inst, local_name='other')
        DriverShift.objects.create(
            profile=p2, route=self.route,
            data_source=self.ds, vehicle_id='Dother',
        )
        result = shift_history(self._req())
        self.assertEqual(len(result), 0)

    def test_history_ordered_by_started_at_desc(self):
        s1 = DriverShift.objects.create(
            profile=self.profile, route=self.route,
            data_source=self.ds, vehicle_id='D1',
            status='ENDED', ended_at=timezone.now(),
        )
        s2 = DriverShift.objects.create(
            profile=self.profile, route=self.route,
            data_source=self.ds, vehicle_id='D2',
        )
        result = shift_history(self._req())
        # Most recent first
        self.assertEqual(result[0].id, str(s2.id))
        self.assertEqual(result[1].id, str(s1.id))
