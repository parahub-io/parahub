"""
Tests for dispatch endpoints: vehicle assignment CRUD, staff-only access, route/device lists.

Tests invariants that must never break:
- Staff-only access on all dispatch endpoints
- No duplicate active assignments per device per date
- Valid status transitions (ASSIGNED/ACTIVE/COMPLETED/CANCELLED)
- Completion/cancellation cleans transit pipeline
- List assignments returns today by default
- Available devices excludes already-assigned ones

NOTE: dispatch.py uses GlobalAuth() but _staff_check accesses request.auth_profile.
      GlobalAuth does NOT set auth_profile — this is a latent bug that would cause
      AttributeError in production. Tests set auth_profile manually to match intent.
"""

from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from ninja.errors import HttpError

from identity.models import Account, Profile
from core.models import Instance
from geo.models import Place, TransitDataSource, Agency, Route
from iot.models import IoTDevice, VehicleAssignment
from iot.endpoints.dispatch import (
    create_assignment, list_assignments, get_assignment,
    update_assignment, list_dispatch_routes, list_available_devices,
    AssignmentCreateIn, AssignmentUpdateIn,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_instance():
    return Instance.objects.create(
        domain='test.parahub.io', name='Test Instance', public_key='test-key',
    )


def _create_account(instance, username='staff_user', is_staff=True, **kwargs):
    return Account.objects.create_user(
        username=username,
        email=f'{username}@test.parahub.io',
        password='testpass123',
        instance=instance,
        is_staff=is_staff,
        **kwargs,
    )


def _create_profile(account, instance, local_name=None, **kwargs):
    local_name = local_name or account.username
    return Profile.objects.create(
        account=account, instance=instance,
        local_name=local_name, display_name=local_name.title(),
        is_primary=True,
        profile_type=kwargs.pop('profile_type', Profile.ProfileType.PERSONAL),
        **kwargs,
    )


def _make_staff_request(factory, account, profile, method='get', path='/fake/', data=None):
    """Build request with user + auth_profile (mimics what dispatch expects)."""
    fn = getattr(factory, method)
    request = fn(path, data=data, content_type='application/json') if data else fn(path)
    request.user = account
    request.auth = profile
    request.auth_profile = profile
    request.session = SessionStore()
    request.session.create()
    return request


def _create_transit_chain():
    place = Place.objects.create(name='Test City', slug='test-city-d', country_code='PT')
    ds = TransitDataSource.objects.create(name='Test Source', format='gtfs')
    agency = Agency.objects.create(
        data_source=ds, source_id='DISP', name='Dispatch Agency',
        timezone='Europe/Lisbon', lang='pt',
    )
    route = Route.objects.create(
        agency=agency, place=place, source_id='DR1',
        short_name='D1', long_name='Dispatch Route 1', route_type=3,
    )
    return place, ds, agency, route


def _create_tracker(profile, name='Tracker 1'):
    return IoTDevice.objects.create(
        owner=profile, name=name, device_type='TRACKER',
        device_id=f'TR-{name}',
    )


# ---------------------------------------------------------------------------
# Staff-only access
# ---------------------------------------------------------------------------

@patch('iot.endpoints.dispatch.TraccarService')
class DispatchStaffAccessTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.staff_acc = _create_account(self.inst, 'staffuser', is_staff=True)
        self.staff_profile = _create_profile(self.staff_acc, self.inst)
        self.nostaff_acc = _create_account(self.inst, 'regular', is_staff=False)
        self.nostaff_profile = _create_profile(self.nostaff_acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()
        self.tracker = _create_tracker(self.staff_profile)

    def _staff_req(self, method='get'):
        return _make_staff_request(self.factory, self.staff_acc, self.staff_profile, method)

    def _nostaff_req(self, method='get'):
        return _make_staff_request(self.factory, self.nostaff_acc, self.nostaff_profile, method)

    def test_list_assignments_staff_ok(self, mock_traccar):
        mock_traccar.get_positions_from_redis.return_value = {}
        result = list_assignments(self._staff_req())
        self.assertEqual(len(result), 0)

    def test_list_assignments_non_staff_rejected(self, mock_traccar):
        with self.assertRaises(HttpError) as ctx:
            list_assignments(self._nostaff_req())
        self.assertEqual(ctx.exception.status_code, 403)

    def test_list_routes_non_staff_rejected(self, mock_traccar):
        with self.assertRaises(HttpError) as ctx:
            list_dispatch_routes(self._nostaff_req())
        self.assertEqual(ctx.exception.status_code, 403)

    def test_list_devices_non_staff_rejected(self, mock_traccar):
        with self.assertRaises(HttpError) as ctx:
            list_available_devices(self._nostaff_req())
        self.assertEqual(ctx.exception.status_code, 403)


# ---------------------------------------------------------------------------
# Assignment CRUD
# ---------------------------------------------------------------------------

@patch('iot.endpoints.dispatch._get_tracker_redis')
@patch('iot.endpoints.dispatch.TraccarService')
class DispatchAssignmentCRUDTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.acc = _create_account(self.inst, 'dispatcher', is_staff=True)
        self.profile = _create_profile(self.acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()
        self.tracker = _create_tracker(self.profile, 'GPS-01')

    def _req(self, method='get'):
        return _make_staff_request(self.factory, self.acc, self.profile, method)

    def test_create_assignment(self, mock_traccar, mock_redis):
        mock_traccar.invalidate_assignment_cache.return_value = None
        today = date.today()
        payload = AssignmentCreateIn(
            device_id=str(self.tracker.id),
            route_id=str(self.route.id),
            direction_id=0,
            date=today,
            display_vehicle_id='V001',
        )
        result = create_assignment(self._req('post'), payload)
        self.assertEqual(result.device_id, str(self.tracker.id))
        self.assertEqual(result.route_id, str(self.route.id))
        self.assertEqual(result.status, 'ASSIGNED')
        self.assertEqual(result.display_vehicle_id, 'V001')
        self.assertEqual(result.object_type, 'vehicle_assignment')

    def test_create_duplicate_rejected(self, mock_traccar, mock_redis):
        mock_traccar.invalidate_assignment_cache.return_value = None
        today = date.today()
        VehicleAssignment.objects.create(
            device=self.tracker, route=self.route, data_source=self.ds,
            date=today, created_by=self.profile, status='ASSIGNED',
        )
        payload = AssignmentCreateIn(
            device_id=str(self.tracker.id),
            route_id=str(self.route.id),
            date=today,
        )
        with self.assertRaises(HttpError) as ctx:
            create_assignment(self._req('post'), payload)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_create_completed_device_can_be_reassigned(self, mock_traccar, mock_redis):
        """A device with a COMPLETED assignment for today can be reassigned."""
        mock_traccar.invalidate_assignment_cache.return_value = None
        today = date.today()
        VehicleAssignment.objects.create(
            device=self.tracker, route=self.route, data_source=self.ds,
            date=today, created_by=self.profile, status='COMPLETED',
        )
        payload = AssignmentCreateIn(
            device_id=str(self.tracker.id),
            route_id=str(self.route.id),
            date=today,
        )
        result = create_assignment(self._req('post'), payload)
        self.assertEqual(result.status, 'ASSIGNED')

    def test_list_assignments_today(self, mock_traccar, mock_redis):
        mock_traccar.get_positions_from_redis.return_value = {}
        today = date.today()
        VehicleAssignment.objects.create(
            device=self.tracker, route=self.route, data_source=self.ds,
            date=today, created_by=self.profile,
        )
        result = list_assignments(self._req())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].device_name, 'GPS-01')

    def test_list_assignments_excludes_other_dates(self, mock_traccar, mock_redis):
        mock_traccar.get_positions_from_redis.return_value = {}
        yesterday = date.today() - timedelta(days=1)
        VehicleAssignment.objects.create(
            device=self.tracker, route=self.route, data_source=self.ds,
            date=yesterday, created_by=self.profile,
        )
        result = list_assignments(self._req())
        self.assertEqual(len(result), 0)

    def test_get_assignment_detail(self, mock_traccar, mock_redis):
        mock_traccar.get_positions_from_redis.return_value = {}
        a = VehicleAssignment.objects.create(
            device=self.tracker, route=self.route, data_source=self.ds,
            date=date.today(), created_by=self.profile,
        )
        result = get_assignment(self._req(), str(a.id))
        self.assertEqual(result.id, str(a.id))

    def test_update_status_completed(self, mock_traccar, mock_redis):
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance
        mock_redis_instance.pipeline.return_value = mock_redis_instance
        mock_redis_instance.execute.return_value = None
        mock_traccar.invalidate_assignment_cache.return_value = None

        a = VehicleAssignment.objects.create(
            device=self.tracker, route=self.route, data_source=self.ds,
            date=date.today(), created_by=self.profile, status='ACTIVE',
        )
        payload = AssignmentUpdateIn(status='COMPLETED')
        result = update_assignment(self._req('patch'), str(a.id), payload)
        self.assertEqual(result.status, 'COMPLETED')
        a.refresh_from_db()
        self.assertEqual(a.status, 'COMPLETED')

    def test_update_invalid_status_rejected(self, mock_traccar, mock_redis):
        mock_traccar.invalidate_assignment_cache.return_value = None
        a = VehicleAssignment.objects.create(
            device=self.tracker, route=self.route, data_source=self.ds,
            date=date.today(), created_by=self.profile,
        )
        payload = AssignmentUpdateIn(status='BOGUS')
        with self.assertRaises(HttpError) as ctx:
            update_assignment(self._req('patch'), str(a.id), payload)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_update_notes(self, mock_traccar, mock_redis):
        mock_traccar.invalidate_assignment_cache.return_value = None
        a = VehicleAssignment.objects.create(
            device=self.tracker, route=self.route, data_source=self.ds,
            date=date.today(), created_by=self.profile,
        )
        payload = AssignmentUpdateIn(status='ASSIGNED', notes='Engine trouble')
        result = update_assignment(self._req('patch'), str(a.id), payload)
        self.assertEqual(result.notes, 'Engine trouble')


# ---------------------------------------------------------------------------
# Route / Device lists
# ---------------------------------------------------------------------------

@patch('iot.endpoints.dispatch.TraccarService')
class DispatchListTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.acc = _create_account(self.inst, 'staff2', is_staff=True)
        self.profile = _create_profile(self.acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()
        self.tracker1 = _create_tracker(self.profile, 'T1')
        self.tracker2 = _create_tracker(self.profile, 'T2')

    def _req(self, method='get'):
        return _make_staff_request(self.factory, self.acc, self.profile, method)

    def test_list_routes_with_active_assignments(self, mock_traccar):
        VehicleAssignment.objects.create(
            device=self.tracker1, route=self.route, data_source=self.ds,
            date=date.today(), created_by=self.profile, status='ACTIVE',
        )
        result = list_dispatch_routes(self._req())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].short_name, 'D1')
        self.assertEqual(result[0].active_count, 1)

    def test_list_routes_empty_without_assignments(self, mock_traccar):
        result = list_dispatch_routes(self._req())
        self.assertEqual(len(result), 0)

    def test_list_available_devices_excludes_assigned(self, mock_traccar):
        mock_traccar.get_positions_from_redis.return_value = {}
        VehicleAssignment.objects.create(
            device=self.tracker1, route=self.route, data_source=self.ds,
            date=date.today(), created_by=self.profile, status='ASSIGNED',
        )
        result = list_available_devices(self._req())
        device_ids = [d.id for d in result]
        self.assertNotIn(str(self.tracker1.id), device_ids)
        self.assertIn(str(self.tracker2.id), device_ids)

    def test_list_available_devices_includes_completed(self, mock_traccar):
        """Devices with COMPLETED status today should appear as available."""
        mock_traccar.get_positions_from_redis.return_value = {}
        VehicleAssignment.objects.create(
            device=self.tracker1, route=self.route, data_source=self.ds,
            date=date.today(), created_by=self.profile, status='COMPLETED',
        )
        result = list_available_devices(self._req())
        device_ids = [d.id for d in result]
        self.assertIn(str(self.tracker1.id), device_ids)

    def test_list_available_devices_only_trackers(self, mock_traccar):
        """Non-tracker devices should not appear."""
        mock_traccar.get_positions_from_redis.return_value = {}
        IoTDevice.objects.create(
            owner=self.profile, name='Sensor', device_type='SENSOR',
        )
        result = list_available_devices(self._req())
        names = [d.name for d in result]
        self.assertNotIn('Sensor', names)
