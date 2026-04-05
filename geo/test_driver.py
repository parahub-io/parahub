"""
Tests for driver mode endpoints: shift start/stop, active shift, history.

Tests invariants that must never break:
- WoT 2+ or staff required (is_verified_wot check)
- No duplicate active shifts per driver
- Stop shift only works on ACTIVE shifts
- Shift owner only (can't stop someone else's shift)
- History returns driver's own shifts
- Active shift returns 204 when none exists
- Transit pipeline cleaned on shift stop
"""

from unittest.mock import patch

from django.test import TestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from ninja.errors import HttpError

from identity.models import Account, Profile
from core.models import Instance
from geo.models import Place, TransitDataSource, Agency, Route, DriverShift
from geo.endpoints.driver import (
    start_shift, stop_shift, get_active_shift, shift_history,
    ShiftStartIn,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_instance():
    return Instance.objects.create(
        domain='test.parahub.io', name='Test Instance', public_key='test-key',
    )


def _create_account(instance, username='driver', is_staff=False, **kwargs):
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


def _make_request(factory, account, profile, method='get', path='/fake/', data=None):
    fn = getattr(factory, method)
    request = fn(path, data=data, content_type='application/json') if data else fn(path)
    request.user = account
    request.auth = profile
    request.auth_profile = profile
    request.session = SessionStore()
    request.session.create()
    return request


def _create_transit_chain():
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


# ---------------------------------------------------------------------------
# WoT access control
# ---------------------------------------------------------------------------

class DriverWoTAccessTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.place, self.ds, self.agency, self.route = _create_transit_chain()

    def test_start_shift_non_wot_non_staff_rejected(self):
        acc = _create_account(self.inst, 'nobody')
        p = _create_profile(acc, self.inst)
        p.is_verified_wot = False
        p.save()
        req = _make_request(self.factory, acc, p, 'post')
        with self.assertRaises(HttpError) as ctx:
            start_shift(req, ShiftStartIn(route_id=str(self.route.id)))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_start_shift_staff_bypasses_wot(self):
        acc = _create_account(self.inst, 'staffdriver', is_staff=True)
        p = _create_profile(acc, self.inst)
        p.is_verified_wot = False
        p.save()
        req = _make_request(self.factory, acc, p, 'post')
        result = start_shift(req, ShiftStartIn(route_id=str(self.route.id)))
        self.assertEqual(result.status, 'ACTIVE')

    def test_start_shift_verified_wot_ok(self):
        acc = _create_account(self.inst, 'wotdriver')
        p = _create_profile(acc, self.inst)
        p.is_verified_wot = True
        p.save()
        req = _make_request(self.factory, acc, p, 'post')
        result = start_shift(req, ShiftStartIn(route_id=str(self.route.id)))
        self.assertEqual(result.status, 'ACTIVE')
        self.assertEqual(result.object_type, 'driver_shift')


# ---------------------------------------------------------------------------
# Shift lifecycle
# ---------------------------------------------------------------------------

class DriverShiftLifecycleTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.inst = _create_instance()
        self.acc = _create_account(self.inst, 'driver', is_staff=True)
        self.profile = _create_profile(self.acc, self.inst)
        self.place, self.ds, self.agency, self.route = _create_transit_chain()

    def _req(self, method='post'):
        return _make_request(self.factory, self.acc, self.profile, method)

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
        # Old shift should be ended
        from geo.models import DriverShift
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
        p2 = _create_profile(acc2, self.inst)
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
        return _make_request(self.factory, self.acc, self.profile, method)

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
        p2 = _create_profile(acc2, self.inst)
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
