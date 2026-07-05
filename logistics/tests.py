"""
Tests for carpool endpoints: ride requests, bookings, reviews.

Tests invariants that must never break:
- Auth required for all endpoints
- WoT verification required to create ride requests
- Passenger-driver role separation (can't offer on own request)
- Booking status transitions (OFFERED → CONFIRMED → COMPLETED | CANCELLED)
- Accept offer: confirms one, cancels others, deactivates request
- Cancel request: deactivates + cancels all OFFERED bookings
- Review only on COMPLETED bookings, one per person per booking
- Access control: only passenger sees bookings on request detail
- Booking update: only driver or passenger can update
- Duplicate offer prevention (active offer per driver per request)
- Request expiry (60 min TTL)
"""

from datetime import timedelta
from unittest.mock import patch, AsyncMock, MagicMock

from django.test import TestCase, SimpleTestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.gis.geos import Point
from django.utils import timezone
from ninja.errors import HttpError

from identity.models import Account, Profile
from core.models import Instance
from logistics.models import RideRequest, RideBooking, RideReview
from geo.models import TransitDataSource, Agency, Stop


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


def _create_profile(account, instance, local_name=None, is_verified_wot=False, **kwargs):
    local_name = local_name or account.username
    return Profile.objects.create(
        account=account,
        instance=instance,
        local_name=local_name,
        display_name=local_name.title(),
        is_primary=True,
        is_verified_wot=is_verified_wot,
        profile_type=kwargs.pop('profile_type', Profile.ProfileType.PERSONAL),
        **kwargs,
    )


def _make_auth_request(factory, account, profile, method='get', path='/fake/', data=None):
    """Build a request with auth_profile and session attached (mimics ProfileAuth)."""
    fn = getattr(factory, method)
    if data:
        request = fn(path, data=data, content_type='application/json')
    else:
        request = fn(path)
    request.user = account
    request.auth = profile
    request.auth_profile = profile
    request.session = SessionStore()
    request.session.create()
    return request


def _create_stops(agency):
    """Create origin and destination stops for testing."""
    origin = Stop.objects.create(
        agency=agency,
        name='Origin Station',
        source_id='origin-1',
        location=Point(-9.1393, 38.7223, srid=4326),
    )
    destination = Stop.objects.create(
        agency=agency,
        name='Destination Station',
        source_id='dest-1',
        location=Point(-9.1500, 38.7300, srid=4326),
    )
    return origin, destination


def _create_ride_request(passenger, origin, destination, price_sats=500,
                         passengers_count=1, is_active=True, **kwargs):
    """Create a RideRequest directly in DB."""
    return RideRequest.objects.create(
        passenger=passenger,
        origin_stop=origin,
        destination_stop=destination,
        price_sats=price_sats,
        passengers_count=passengers_count,
        is_active=is_active,
        **kwargs,
    )


def _create_booking(ride_request, driver, status=RideBooking.Status.OFFERED, **kwargs):
    """Create a RideBooking directly in DB."""
    return RideBooking.objects.create(
        request=ride_request,
        driver=driver,
        status=status,
        **kwargs,
    )


def _create_review(booking, reviewer, reviewee, rating=4, comment='Good ride'):
    """Create a RideReview directly in DB."""
    return RideReview.objects.create(
        booking=booking,
        reviewer=reviewer,
        reviewee=reviewee,
        rating=rating,
        comment=comment,
    )


# ===========================================================================
# Model-level tests (SimpleTestCase — no DB)
# ===========================================================================

class RideBookingStatusTest(SimpleTestCase):
    """Test RideBooking status choices."""

    def test_status_choices(self):
        self.assertEqual(RideBooking.Status.OFFERED, 'OFFERED')
        self.assertEqual(RideBooking.Status.CONFIRMED, 'CONFIRMED')
        self.assertEqual(RideBooking.Status.COMPLETED, 'COMPLETED')
        self.assertEqual(RideBooking.Status.CANCELLED, 'CANCELLED')

    def test_default_status_is_offered(self):
        booking = RideBooking()
        self.assertEqual(booking.status, 'OFFERED')

    def test_default_available_seats(self):
        booking = RideBooking()
        self.assertEqual(booking.available_seats, 3)


class RideRequestModelTest(SimpleTestCase):
    """Test RideRequest model defaults."""

    def test_default_is_active(self):
        req = RideRequest()
        self.assertTrue(req.is_active)

    def test_default_passengers_count(self):
        req = RideRequest()
        self.assertEqual(req.passengers_count, 1)


class RideReviewModelTest(SimpleTestCase):
    """Test RideReview validators."""

    def test_rating_validators_exist(self):
        field = RideReview._meta.get_field('rating')
        validator_values = [v.limit_value for v in field.validators]
        self.assertIn(1, validator_values)
        self.assertIn(5, validator_values)


# ===========================================================================
# Schema validation tests (SimpleTestCase — no DB)
# ===========================================================================

class SchemaValidationTest(SimpleTestCase):
    """Test Pydantic schema validation."""

    def test_ride_request_create_valid(self):
        from parahub.endpoints.rides import RideRequestCreate
        schema = RideRequestCreate(
            origin_stop_id='01TEST',
            destination_stop_id='02TEST',
            price_sats=100,
            passengers_count=2,
            note='Test note',
        )
        self.assertEqual(schema.price_sats, 100)
        self.assertEqual(schema.passengers_count, 2)

    def test_ride_request_create_defaults(self):
        from parahub.endpoints.rides import RideRequestCreate
        schema = RideRequestCreate(
            origin_stop_id='01TEST',
            destination_stop_id='02TEST',
            price_sats=0,
        )
        self.assertEqual(schema.passengers_count, 1)
        self.assertEqual(schema.note, '')

    def test_ride_request_negative_price_rejected(self):
        from parahub.endpoints.rides import RideRequestCreate
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RideRequestCreate(
                origin_stop_id='01TEST',
                destination_stop_id='02TEST',
                price_sats=-1,
            )

    def test_ride_request_passengers_count_bounds(self):
        from parahub.endpoints.rides import RideRequestCreate
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RideRequestCreate(
                origin_stop_id='01TEST',
                destination_stop_id='02TEST',
                price_sats=100,
                passengers_count=0,
            )
        with self.assertRaises(ValidationError):
            RideRequestCreate(
                origin_stop_id='01TEST',
                destination_stop_id='02TEST',
                price_sats=100,
                passengers_count=11,
            )

    def test_booking_offer_create_defaults(self):
        from parahub.endpoints.rides import BookingOfferCreate
        schema = BookingOfferCreate()
        self.assertEqual(schema.driver_note, '')
        self.assertEqual(schema.available_seats, 3)

    def test_booking_offer_seats_bounds(self):
        from parahub.endpoints.rides import BookingOfferCreate
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            BookingOfferCreate(available_seats=0)
        with self.assertRaises(ValidationError):
            BookingOfferCreate(available_seats=21)

    def test_booking_status_update_valid_values(self):
        from parahub.endpoints.rides import BookingStatusUpdate
        from pydantic import ValidationError
        s1 = BookingStatusUpdate(status='COMPLETED')
        self.assertEqual(s1.status, 'COMPLETED')
        s2 = BookingStatusUpdate(status='CANCELLED')
        self.assertEqual(s2.status, 'CANCELLED')
        with self.assertRaises(ValidationError):
            BookingStatusUpdate(status='OFFERED')
        with self.assertRaises(ValidationError):
            BookingStatusUpdate(status='CONFIRMED')
        with self.assertRaises(ValidationError):
            BookingStatusUpdate(status='invalid')

    def test_review_create_rating_bounds(self):
        from parahub.endpoints.rides import ReviewCreate
        from pydantic import ValidationError
        ReviewCreate(rating=1)
        ReviewCreate(rating=5)
        with self.assertRaises(ValidationError):
            ReviewCreate(rating=0)
        with self.assertRaises(ValidationError):
            ReviewCreate(rating=6)

    def test_review_create_defaults(self):
        from parahub.endpoints.rides import ReviewCreate
        schema = ReviewCreate(rating=3)
        self.assertEqual(schema.comment, '')

    def test_route_location_bounds(self):
        from parahub.endpoints.rides import RouteLocation
        from pydantic import ValidationError
        RouteLocation(lat=0, lon=0)
        RouteLocation(lat=90, lon=180)
        RouteLocation(lat=-90, lon=-180)
        with self.assertRaises(ValidationError):
            RouteLocation(lat=91, lon=0)
        with self.assertRaises(ValidationError):
            RouteLocation(lat=0, lon=181)

    def test_route_search_body_defaults(self):
        from parahub.endpoints.rides import RouteSearchBody, RouteLocation
        body = RouteSearchBody(
            origin=RouteLocation(lat=38.7, lon=-9.1),
            destination=RouteLocation(lat=38.8, lon=-9.2),
        )
        self.assertEqual(body.corridor_km, 0.5)

    def test_route_search_corridor_bounds(self):
        from parahub.endpoints.rides import RouteSearchBody, RouteLocation
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RouteSearchBody(
                origin=RouteLocation(lat=38.7, lon=-9.1),
                destination=RouteLocation(lat=38.8, lon=-9.2),
                corridor_km=0.05,
            )
        with self.assertRaises(ValidationError):
            RouteSearchBody(
                origin=RouteLocation(lat=38.7, lon=-9.1),
                destination=RouteLocation(lat=38.8, lon=-9.2),
                corridor_km=5.1,
            )


# ===========================================================================
# Polyline decoding tests (SimpleTestCase — no DB)
# ===========================================================================

class PolylineDecodeTest(SimpleTestCase):
    """Test Valhalla polyline6 decoder."""

    def test_decode_empty_string(self):
        from parahub.endpoints.rides import _decode_polyline6
        result = _decode_polyline6('')
        self.assertEqual(result, [])

    def test_decode_returns_lon_lat_tuples(self):
        from parahub.endpoints.rides import _decode_polyline6
        result = _decode_polyline6('_p~iF~ps|U')
        self.assertIsInstance(result, list)
        if result:
            self.assertEqual(len(result[0]), 2)


# ===========================================================================
# Endpoint tests (TestCase — with DB)
# ===========================================================================

class CarpoolTestBase(TestCase):
    """Base class with common setup for carpool endpoint tests."""

    @classmethod
    def setUpTestData(cls):
        cls.instance = _create_instance()

        cls.passenger_account = _create_account(cls.instance, 'passenger')
        cls.passenger = _create_profile(
            cls.passenger_account, cls.instance, 'passenger', is_verified_wot=True,
        )

        cls.driver_account = _create_account(cls.instance, 'driver')
        cls.driver = _create_profile(
            cls.driver_account, cls.instance, 'driver', is_verified_wot=True,
        )

        cls.driver2_account = _create_account(cls.instance, 'driver2')
        cls.driver2 = _create_profile(
            cls.driver2_account, cls.instance, 'driver2', is_verified_wot=True,
        )

        cls.unverified_account = _create_account(cls.instance, 'unverified')
        cls.unverified = _create_profile(
            cls.unverified_account, cls.instance, 'unverified', is_verified_wot=False,
        )

        cls.bystander_account = _create_account(cls.instance, 'bystander')
        cls.bystander = _create_profile(
            cls.bystander_account, cls.instance, 'bystander', is_verified_wot=True,
        )

        cls.data_source = TransitDataSource.objects.create(
            name='Test Source', format='gtfs',
        )
        cls.agency = Agency.objects.create(
            data_source=cls.data_source,
            name='Test Agency',
            timezone='Europe/Lisbon',
            lang='pt',
        )
        cls.origin, cls.destination = _create_stops(cls.agency)

        cls.factory = RequestFactory()


# ---------------------------------------------------------------------------
# Create ride request tests
# ---------------------------------------------------------------------------

class CreateRideRequestTest(CarpoolTestBase):
    """Test POST /rides/requests/ endpoint."""

    def _call(self, profile, account, data):
        from parahub.endpoints.rides import create_request, RideRequestCreate
        body = RideRequestCreate(**data)
        request = _make_auth_request(self.factory, account, profile, 'post')
        return create_request(request, body)

    def test_create_request_success(self):
        """Verified passenger can create a ride request."""
        result = self._call(self.passenger, self.passenger_account, {
            'origin_stop_id': self.origin.id,
            'destination_stop_id': self.destination.id,
            'price_sats': 500,
            'passengers_count': 2,
            'note': 'Need a ride please',
        })
        self.assertEqual(result['object_type'], 'ride_request')
        self.assertEqual(result['price_sats'], 500)
        self.assertEqual(result['passengers_count'], 2)
        self.assertEqual(result['note'], 'Need a ride please')
        self.assertTrue(result['is_active'])
        self.assertIsNotNone(result['origin_stop'])
        self.assertIsNotNone(result['destination_stop'])
        self.assertEqual(result['passenger']['id'], self.passenger.id)

    def test_create_request_wot_required(self):
        """Unverified user cannot create ride request."""
        with self.assertRaises(HttpError) as ctx:
            self._call(self.unverified, self.unverified_account, {
                'origin_stop_id': self.origin.id,
                'destination_stop_id': self.destination.id,
                'price_sats': 100,
            })
        self.assertEqual(ctx.exception.status_code, 403)

    def test_create_request_invalid_origin(self):
        """Non-existent origin stop returns 400."""
        with self.assertRaises(HttpError) as ctx:
            self._call(self.passenger, self.passenger_account, {
                'origin_stop_id': 'nonexistent',
                'destination_stop_id': self.destination.id,
                'price_sats': 100,
            })
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_request_invalid_destination(self):
        """Non-existent destination stop returns 400."""
        with self.assertRaises(HttpError) as ctx:
            self._call(self.passenger, self.passenger_account, {
                'origin_stop_id': self.origin.id,
                'destination_stop_id': 'nonexistent',
                'price_sats': 100,
            })
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_request_zero_price(self):
        """Zero price is valid (free ride)."""
        result = self._call(self.passenger, self.passenger_account, {
            'origin_stop_id': self.origin.id,
            'destination_stop_id': self.destination.id,
            'price_sats': 0,
        })
        self.assertEqual(result['price_sats'], 0)

    def test_create_request_defaults(self):
        """Default passengers_count=1, note=''."""
        result = self._call(self.passenger, self.passenger_account, {
            'origin_stop_id': self.origin.id,
            'destination_stop_id': self.destination.id,
            'price_sats': 100,
        })
        self.assertEqual(result['passengers_count'], 1)
        self.assertEqual(result['note'], '')


# ---------------------------------------------------------------------------
# List my requests tests
# ---------------------------------------------------------------------------

class ListMyRequestsTest(CarpoolTestBase):
    """Test GET /rides/requests/ endpoint."""

    def _call(self, profile, account):
        from parahub.endpoints.rides import my_requests
        request = _make_auth_request(self.factory, account, profile)
        return my_requests(request)

    def test_list_own_active_requests(self):
        """Returns only my active, non-expired requests."""
        req1 = _create_ride_request(self.passenger, self.origin, self.destination)
        req2 = _create_ride_request(self.passenger, self.origin, self.destination, is_active=False)
        result = self._call(self.passenger, self.passenger_account)
        ids = [r['id'] for r in result]
        self.assertIn(req1.id, ids)
        self.assertNotIn(req2.id, ids)

    def test_list_excludes_other_users(self):
        """Does not show other users' requests."""
        _create_ride_request(self.driver, self.origin, self.destination)
        result = self._call(self.passenger, self.passenger_account)
        self.assertEqual(len(result), 0)

    def test_list_excludes_expired(self):
        """Requests older than 60 min are excluded."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        RideRequest.objects.filter(id=req.id).update(
            created_at=timezone.now() - timedelta(minutes=61)
        )
        result = self._call(self.passenger, self.passenger_account)
        ids = [r['id'] for r in result]
        self.assertNotIn(req.id, ids)

    def test_list_empty_when_none(self):
        """Returns empty list when no requests."""
        result = self._call(self.passenger, self.passenger_account)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Get request detail tests
# ---------------------------------------------------------------------------

class GetRequestDetailTest(CarpoolTestBase):
    """Test GET /rides/requests/{id}/ endpoint."""

    def _call(self, profile, account, request_id):
        from parahub.endpoints.rides import get_request
        request = _make_auth_request(self.factory, account, profile)
        return get_request(request, request_id)

    def test_passenger_sees_bookings(self):
        """Passenger can see driver offers on their own request."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        _create_booking(req, self.driver)
        result = self._call(self.passenger, self.passenger_account, req.id)
        self.assertIn('bookings', result)
        self.assertEqual(len(result['bookings']), 1)

    def test_non_owner_cannot_see_bookings(self):
        """Other users see request but not bookings (IDOR protection)."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        _create_booking(req, self.driver)
        result = self._call(self.driver, self.driver_account, req.id)
        self.assertNotIn('bookings', result)

    def test_nonexistent_request_404(self):
        """Non-existent request returns 404."""
        with self.assertRaises(HttpError) as ctx:
            self._call(self.passenger, self.passenger_account, 'nonexistent')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_response_includes_object_type(self):
        """Response includes object_type field."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        result = self._call(self.passenger, self.passenger_account, req.id)
        self.assertEqual(result['object_type'], 'ride_request')

    def test_response_includes_stop_info(self):
        """Response includes origin and destination stop info."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        result = self._call(self.passenger, self.passenger_account, req.id)
        self.assertEqual(result['origin_stop']['name'], 'Origin Station')
        self.assertEqual(result['destination_stop']['name'], 'Destination Station')


# ---------------------------------------------------------------------------
# Cancel request tests
# ---------------------------------------------------------------------------

class CancelRequestTest(CarpoolTestBase):
    """Test DELETE /rides/requests/{id}/ endpoint."""

    def _call(self, profile, account, request_id):
        from parahub.endpoints.rides import cancel_request
        request = _make_auth_request(self.factory, account, profile, 'delete')
        return cancel_request(request, request_id)

    def test_cancel_own_request(self):
        """Passenger can cancel their own request."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        result = self._call(self.passenger, self.passenger_account, req.id)
        self.assertTrue(result['success'])
        req.refresh_from_db()
        self.assertFalse(req.is_active)

    def test_cancel_cancels_offered_bookings(self):
        """Cancelling request cancels all OFFERED bookings."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        b1 = _create_booking(req, self.driver, status=RideBooking.Status.OFFERED)
        b2 = _create_booking(req, self.driver2, status=RideBooking.Status.OFFERED)
        self._call(self.passenger, self.passenger_account, req.id)
        b1.refresh_from_db()
        b2.refresh_from_db()
        self.assertEqual(b1.status, 'CANCELLED')
        self.assertEqual(b2.status, 'CANCELLED')

    def test_cancel_does_not_affect_confirmed_bookings(self):
        """Cancelling request does not cancel already-confirmed bookings."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        b = _create_booking(req, self.driver, status=RideBooking.Status.CONFIRMED)
        self._call(self.passenger, self.passenger_account, req.id)
        b.refresh_from_db()
        self.assertEqual(b.status, 'CONFIRMED')

    def test_cannot_cancel_others_request(self):
        """Cannot cancel another user's request."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, req.id)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_cancel_nonexistent_404(self):
        """Non-existent request returns 404."""
        with self.assertRaises(HttpError) as ctx:
            self._call(self.passenger, self.passenger_account, 'nonexistent')
        self.assertEqual(ctx.exception.status_code, 404)


# ---------------------------------------------------------------------------
# Offer ride tests
# ---------------------------------------------------------------------------

class OfferRideTest(CarpoolTestBase):
    """Test POST /rides/requests/{id}/offer/ endpoint."""

    def _call(self, profile, account, request_id, data=None):
        from parahub.endpoints.rides import offer_ride, BookingOfferCreate
        data = data or {}
        body = BookingOfferCreate(**data)
        request = _make_auth_request(self.factory, account, profile, 'post')
        return offer_ride(request, request_id, body)

    def test_offer_ride_success(self):
        """Driver can offer a ride on an active request."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        result = self._call(self.driver, self.driver_account, req.id, {
            'driver_note': 'I can pick you up',
            'available_seats': 4,
        })
        self.assertEqual(result['object_type'], 'ride_booking')
        self.assertEqual(result['status'], 'OFFERED')
        self.assertEqual(result['driver_note'], 'I can pick you up')
        self.assertEqual(result['available_seats'], 4)

    def test_offer_defaults(self):
        """Default driver_note='' and available_seats=3."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        result = self._call(self.driver, self.driver_account, req.id)
        self.assertEqual(result['driver_note'], '')
        self.assertEqual(result['available_seats'], 3)

    def test_cannot_offer_on_own_request(self):
        """Cannot offer ride on own request."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        with self.assertRaises(HttpError) as ctx:
            self._call(self.passenger, self.passenger_account, req.id)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cannot_offer_on_inactive_request(self):
        """Cannot offer on deactivated request."""
        req = _create_ride_request(self.passenger, self.origin, self.destination, is_active=False)
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, req.id)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cannot_offer_on_expired_request(self):
        """Cannot offer on request older than 60 minutes."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        RideRequest.objects.filter(id=req.id).update(
            created_at=timezone.now() - timedelta(minutes=61)
        )
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, req.id)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_duplicate_offer_rejected(self):
        """Cannot make a second active offer on same request."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        self._call(self.driver, self.driver_account, req.id)
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, req.id)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_can_reoffer_after_cancellation(self):
        """Can offer again after previous offer was cancelled."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        _create_booking(req, self.driver, status=RideBooking.Status.CANCELLED)
        result = self._call(self.driver, self.driver_account, req.id)
        self.assertEqual(result['status'], 'OFFERED')

    def test_multiple_drivers_can_offer(self):
        """Multiple drivers can offer on the same request."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        r1 = self._call(self.driver, self.driver_account, req.id)
        r2 = self._call(self.driver2, self.driver2_account, req.id)
        self.assertEqual(r1['status'], 'OFFERED')
        self.assertEqual(r2['status'], 'OFFERED')
        self.assertNotEqual(r1['id'], r2['id'])

    def test_offer_nonexistent_request_404(self):
        """Non-existent request returns 404."""
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, 'nonexistent')
        self.assertEqual(ctx.exception.status_code, 404)


# ---------------------------------------------------------------------------
# Accept offer tests
# ---------------------------------------------------------------------------

class AcceptOfferTest(CarpoolTestBase):
    """Test PATCH /rides/requests/{id}/accept/ endpoint."""

    def _accept(self, profile, account, request_id, booking_id, dm_return=None):
        from parahub.endpoints.rides import accept_offer, AcceptOfferBody
        body = AcceptOfferBody(booking_id=booking_id)
        request = _make_auth_request(self.factory, account, profile, 'patch')
        with patch('parahub.endpoints.matrix_auth.create_dm_between_accounts', return_value=dm_return):
            return accept_offer(request, request_id, body)

    def test_accept_offer_success(self):
        """Passenger can accept a driver's offer."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver)
        result = self._accept(self.passenger, self.passenger_account, req.id, booking.id)
        self.assertEqual(result['status'], 'CONFIRMED')
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CONFIRMED')

    def test_accept_deactivates_request(self):
        """Accepting an offer deactivates the request."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver)
        self._accept(self.passenger, self.passenger_account, req.id, booking.id)
        req.refresh_from_db()
        self.assertFalse(req.is_active)

    def test_accept_cancels_other_offers(self):
        """Accepting one offer cancels all other OFFERED bookings."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        b1 = _create_booking(req, self.driver)
        b2 = _create_booking(req, self.driver2)
        self._accept(self.passenger, self.passenger_account, req.id, b1.id)
        b1.refresh_from_db()
        b2.refresh_from_db()
        self.assertEqual(b1.status, 'CONFIRMED')
        self.assertEqual(b2.status, 'CANCELLED')

    def test_accept_creates_matrix_dm(self):
        """Accepting stores matrix_room_id on booking."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver)
        self._accept(self.passenger, self.passenger_account, req.id, booking.id, dm_return='!test:room')
        booking.refresh_from_db()
        self.assertEqual(booking.matrix_room_id, '!test:room')

    def test_accept_matrix_failure_does_not_block(self):
        """Matrix DM failure doesn't block acceptance."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver)
        from parahub.endpoints.rides import accept_offer, AcceptOfferBody
        body = AcceptOfferBody(booking_id=booking.id)
        request = _make_auth_request(self.factory, self.passenger_account, self.passenger, 'patch')
        with patch('parahub.endpoints.matrix_auth.create_dm_between_accounts', side_effect=Exception('Matrix down')):
            result = accept_offer(request, req.id, body)
        self.assertEqual(result['status'], 'CONFIRMED')
        booking.refresh_from_db()
        self.assertEqual(booking.matrix_room_id, '')

    def test_accept_not_own_request_404(self):
        """Cannot accept offers on someone else's request."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver)
        from parahub.endpoints.rides import accept_offer, AcceptOfferBody
        body = AcceptOfferBody(booking_id=booking.id)
        request = _make_auth_request(self.factory, self.driver2_account, self.driver2, 'patch')
        with self.assertRaises(HttpError) as ctx:
            accept_offer(request, req.id, body)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_accept_already_processed_offer_404(self):
        """Cannot accept an already-confirmed offer."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.CONFIRMED)
        from parahub.endpoints.rides import accept_offer, AcceptOfferBody
        body = AcceptOfferBody(booking_id=booking.id)
        request = _make_auth_request(self.factory, self.passenger_account, self.passenger, 'patch')
        with self.assertRaises(HttpError) as ctx:
            accept_offer(request, req.id, body)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_accept_inactive_request_404(self):
        """Cannot accept on an already-inactive request."""
        req = _create_ride_request(self.passenger, self.origin, self.destination, is_active=False)
        booking = _create_booking(req, self.driver)
        from parahub.endpoints.rides import accept_offer, AcceptOfferBody
        body = AcceptOfferBody(booking_id=booking.id)
        request = _make_auth_request(self.factory, self.passenger_account, self.passenger, 'patch')
        with self.assertRaises(HttpError) as ctx:
            accept_offer(request, req.id, body)
        self.assertEqual(ctx.exception.status_code, 404)


# ---------------------------------------------------------------------------
# Search requests tests
# ---------------------------------------------------------------------------

class SearchRequestsTest(CarpoolTestBase):
    """Test GET /rides/search/ endpoint."""

    def _call(self, profile, account, lat, lon, radius_km=2):
        from parahub.endpoints.rides import search_requests
        request = _make_auth_request(self.factory, account, profile)
        return search_requests(request, lat=lat, lon=lon, radius_km=radius_km)

    def test_search_finds_nearby_requests(self):
        """Search finds active requests near the driver's location."""
        _create_ride_request(self.passenger, self.origin, self.destination)
        result = self._call(self.driver, self.driver_account,
                           lat=38.7223, lon=-9.1393, radius_km=1)
        self.assertEqual(len(result), 1)
        self.assertIn('distance_m', result[0])

    def test_search_excludes_inactive(self):
        """Search excludes inactive requests."""
        _create_ride_request(self.passenger, self.origin, self.destination, is_active=False)
        result = self._call(self.driver, self.driver_account,
                           lat=38.7223, lon=-9.1393, radius_km=50)
        self.assertEqual(len(result), 0)

    def test_search_excludes_expired(self):
        """Search excludes requests older than 60 minutes."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        RideRequest.objects.filter(id=req.id).update(
            created_at=timezone.now() - timedelta(minutes=61)
        )
        result = self._call(self.driver, self.driver_account,
                           lat=38.7223, lon=-9.1393, radius_km=50)
        self.assertEqual(len(result), 0)

    def test_search_excludes_far_away(self):
        """Search excludes requests outside radius."""
        _create_ride_request(self.passenger, self.origin, self.destination)
        result = self._call(self.driver, self.driver_account,
                           lat=40.0, lon=-8.0, radius_km=1)
        self.assertEqual(len(result), 0)

    def test_search_radius_capped_at_50km(self):
        """Radius is capped at 50km."""
        _create_ride_request(self.passenger, self.origin, self.destination)
        result = self._call(self.driver, self.driver_account,
                           lat=38.7223, lon=-9.1393, radius_km=100)
        self.assertEqual(len(result), 1)

    def test_search_returns_distance(self):
        """Search results include distance_m field."""
        _create_ride_request(self.passenger, self.origin, self.destination)
        result = self._call(self.driver, self.driver_account,
                           lat=38.7223, lon=-9.1393, radius_km=1)
        self.assertIn('distance_m', result[0])
        self.assertIsInstance(result[0]['distance_m'], int)


# ---------------------------------------------------------------------------
# Route-based search tests
# ---------------------------------------------------------------------------

class RouteSearchTest(CarpoolTestBase):
    """Test POST /rides/search/route/ endpoint."""

    @patch('parahub.endpoints.rides._get_valhalla_route',
           new_callable=AsyncMock, return_value=None)
    def test_valhalla_failure_returns_502(self, mock_route):
        """Returns 502 when Valhalla route calculation fails."""
        import asyncio
        from parahub.endpoints.rides import search_by_route, RouteSearchBody, RouteLocation
        body = RouteSearchBody(
            origin=RouteLocation(lat=38.7, lon=-9.1),
            destination=RouteLocation(lat=38.8, lon=-9.2),
        )
        request = _make_auth_request(self.factory, self.driver_account, self.driver, 'post')
        with self.assertRaises(HttpError) as ctx:
            asyncio.run(search_by_route(request, body))
        self.assertEqual(ctx.exception.status_code, 502)


# ---------------------------------------------------------------------------
# My bookings tests
# ---------------------------------------------------------------------------

class MyBookingsTest(CarpoolTestBase):
    """Test GET /rides/bookings/ endpoint."""

    def _call(self, profile, account):
        from parahub.endpoints.rides import my_bookings
        request = _make_auth_request(self.factory, account, profile)
        return my_bookings(request)

    def test_driver_sees_own_bookings(self):
        """Driver sees bookings where they are the driver."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver)
        result = self._call(self.driver, self.driver_account)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], booking.id)
        self.assertEqual(result[0]['role'], 'driver')

    def test_passenger_sees_bookings(self):
        """Passenger sees bookings on their requests."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        _create_booking(req, self.driver)
        result = self._call(self.passenger, self.passenger_account)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['role'], 'passenger')

    def test_bystander_sees_nothing(self):
        """Unrelated user sees no bookings."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        _create_booking(req, self.driver)
        result = self._call(self.bystander, self.bystander_account)
        self.assertEqual(len(result), 0)

    def test_includes_request_info(self):
        """Booking response includes nested request data."""
        req = _create_ride_request(self.passenger, self.origin, self.destination, price_sats=999)
        _create_booking(req, self.driver)
        result = self._call(self.driver, self.driver_account)
        self.assertIn('request', result[0])
        self.assertEqual(result[0]['request']['price_sats'], 999)

    def test_booking_object_type(self):
        """Response includes object_type=ride_booking."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        _create_booking(req, self.driver)
        result = self._call(self.driver, self.driver_account)
        self.assertEqual(result[0]['object_type'], 'ride_booking')


# ---------------------------------------------------------------------------
# Update booking status tests
# ---------------------------------------------------------------------------

class UpdateBookingTest(CarpoolTestBase):
    """Test PATCH /rides/bookings/{id}/ endpoint."""

    def _call(self, profile, account, booking_id, status):
        from parahub.endpoints.rides import update_booking, BookingStatusUpdate
        body = BookingStatusUpdate(status=status)
        request = _make_auth_request(self.factory, account, profile, 'patch')
        return update_booking(request, booking_id, body)

    def test_complete_confirmed_booking(self):
        """Driver can mark confirmed booking as completed."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.CONFIRMED)
        result = self._call(self.driver, self.driver_account, booking.id, 'COMPLETED')
        self.assertEqual(result['status'], 'COMPLETED')

    def test_passenger_can_complete(self):
        """Passenger can also mark booking as completed."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.CONFIRMED)
        result = self._call(self.passenger, self.passenger_account, booking.id, 'COMPLETED')
        self.assertEqual(result['status'], 'COMPLETED')

    def test_cannot_complete_offered_booking(self):
        """Cannot complete a booking that is still in OFFERED status."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.OFFERED)
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, booking.id, 'COMPLETED')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cancel_offered_booking(self):
        """Driver can cancel an OFFERED booking."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver)
        result = self._call(self.driver, self.driver_account, booking.id, 'CANCELLED')
        self.assertEqual(result['status'], 'CANCELLED')

    def test_cancel_confirmed_booking(self):
        """Driver can cancel a CONFIRMED booking."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.CONFIRMED)
        result = self._call(self.driver, self.driver_account, booking.id, 'CANCELLED')
        self.assertEqual(result['status'], 'CANCELLED')

    def test_cannot_cancel_completed_booking(self):
        """Cannot cancel a completed booking."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.COMPLETED)
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, booking.id, 'CANCELLED')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cannot_cancel_already_cancelled(self):
        """Cannot cancel an already cancelled booking."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.CANCELLED)
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, booking.id, 'CANCELLED')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_bystander_cannot_update(self):
        """Unrelated user cannot update booking status."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.CONFIRMED)
        with self.assertRaises(HttpError) as ctx:
            self._call(self.bystander, self.bystander_account, booking.id, 'COMPLETED')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_nonexistent_booking_404(self):
        """Non-existent booking returns 404."""
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, 'nonexistent', 'COMPLETED')
        self.assertEqual(ctx.exception.status_code, 404)


# ---------------------------------------------------------------------------
# Review tests
# ---------------------------------------------------------------------------

class LeaveReviewTest(CarpoolTestBase):
    """Test POST /rides/bookings/{id}/review/ endpoint."""

    def _call(self, profile, account, booking_id, data):
        from parahub.endpoints.rides import leave_review, ReviewCreate
        body = ReviewCreate(**data)
        request = _make_auth_request(self.factory, account, profile, 'post')
        return leave_review(request, booking_id, body)

    def test_driver_reviews_passenger(self):
        """Driver can review passenger after completed ride."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.COMPLETED)
        result = self._call(self.driver, self.driver_account, booking.id, {
            'rating': 5, 'comment': 'Great passenger',
        })
        self.assertEqual(result['object_type'], 'ride_review')
        self.assertEqual(result['rating'], 5)
        self.assertEqual(result['comment'], 'Great passenger')
        self.assertEqual(result['reviewer']['id'], self.driver.id)
        self.assertEqual(result['reviewee']['id'], self.passenger.id)

    def test_passenger_reviews_driver(self):
        """Passenger can review driver after completed ride."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.COMPLETED)
        result = self._call(self.passenger, self.passenger_account, booking.id, {
            'rating': 4, 'comment': 'Nice driver',
        })
        self.assertEqual(result['reviewer']['id'], self.passenger.id)
        self.assertEqual(result['reviewee']['id'], self.driver.id)

    def test_mutual_reviews_allowed(self):
        """Both driver and passenger can review each other on same booking."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.COMPLETED)
        r1 = self._call(self.driver, self.driver_account, booking.id, {'rating': 5})
        r2 = self._call(self.passenger, self.passenger_account, booking.id, {'rating': 4})
        self.assertNotEqual(r1['id'], r2['id'])

    def test_cannot_review_twice(self):
        """Same person cannot review the same booking twice."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.COMPLETED)
        self._call(self.driver, self.driver_account, booking.id, {'rating': 5})
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, booking.id, {'rating': 3})
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cannot_review_non_completed(self):
        """Cannot review a booking that is not completed."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.CONFIRMED)
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, booking.id, {'rating': 5})
        self.assertEqual(ctx.exception.status_code, 404)

    def test_cannot_review_offered(self):
        """Cannot review OFFERED booking."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.OFFERED)
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, booking.id, {'rating': 3})
        self.assertEqual(ctx.exception.status_code, 404)

    def test_cannot_review_cancelled(self):
        """Cannot review cancelled booking."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.CANCELLED)
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, booking.id, {'rating': 2})
        self.assertEqual(ctx.exception.status_code, 404)

    def test_bystander_cannot_review(self):
        """Unrelated user cannot review a booking."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.COMPLETED)
        with self.assertRaises(HttpError) as ctx:
            self._call(self.bystander, self.bystander_account, booking.id, {'rating': 1})
        self.assertEqual(ctx.exception.status_code, 403)

    def test_review_default_comment(self):
        """Default comment is empty string."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.COMPLETED)
        result = self._call(self.driver, self.driver_account, booking.id, {'rating': 4})
        self.assertEqual(result['comment'], '')

    def test_nonexistent_booking_404(self):
        """Non-existent booking returns 404."""
        with self.assertRaises(HttpError) as ctx:
            self._call(self.driver, self.driver_account, 'nonexistent', {'rating': 5})
        self.assertEqual(ctx.exception.status_code, 404)


# ---------------------------------------------------------------------------
# Profile brief / ride rating tests
# ---------------------------------------------------------------------------

class ProfileBriefTest(CarpoolTestBase):
    """Test _profile_brief() helper with ride rating aggregation."""

    def test_no_reviews_no_rating(self):
        """Profile with no reviews has no ride_rating."""
        from parahub.endpoints.rides import _profile_brief
        brief = _profile_brief(self.driver)
        self.assertIsNone(brief['ride_rating'])
        self.assertEqual(brief['ride_count'], 0)

    def test_ride_rating_calculated(self):
        """Profile brief shows average rating from completed rides."""
        from parahub.endpoints.rides import _profile_brief
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        b1 = _create_booking(req, self.driver, status=RideBooking.Status.COMPLETED)
        _create_review(b1, self.passenger, self.driver, rating=5)

        req2 = _create_ride_request(self.passenger, self.origin, self.destination)
        b2 = _create_booking(req2, self.driver, status=RideBooking.Status.COMPLETED)
        _create_review(b2, self.passenger, self.driver, rating=3)

        brief = _profile_brief(self.driver)
        self.assertEqual(brief['ride_rating'], 4.0)
        self.assertEqual(brief['ride_count'], 2)

    def test_profile_brief_includes_display_name(self):
        """Profile brief includes display_name."""
        from parahub.endpoints.rides import _profile_brief
        brief = _profile_brief(self.driver)
        self.assertEqual(brief['display_name'], 'Driver')
        self.assertEqual(brief['id'], self.driver.id)


# ---------------------------------------------------------------------------
# Full lifecycle integration tests
# ---------------------------------------------------------------------------

class RideLifecycleTest(CarpoolTestBase):
    """Test complete ride lifecycle: request → offer → accept → complete → review."""

    def test_full_happy_path(self):
        """Full lifecycle: create request, offer, accept, complete, review."""
        from parahub.endpoints.rides import (
            create_request, offer_ride, accept_offer, update_booking, leave_review,
            RideRequestCreate, BookingOfferCreate, AcceptOfferBody,
            BookingStatusUpdate, ReviewCreate,
        )

        # 1. Passenger creates request
        req_body = RideRequestCreate(
            origin_stop_id=self.origin.id,
            destination_stop_id=self.destination.id,
            price_sats=1000,
            passengers_count=1,
        )
        req = _make_auth_request(self.factory, self.passenger_account, self.passenger, 'post')
        req_result = create_request(req, req_body)
        request_id = req_result['id']
        self.assertTrue(req_result['is_active'])

        # 2. Driver offers ride
        offer_body = BookingOfferCreate(driver_note='On my way', available_seats=4)
        req = _make_auth_request(self.factory, self.driver_account, self.driver, 'post')
        offer_result = offer_ride(req, request_id, offer_body)
        booking_id = offer_result['id']
        self.assertEqual(offer_result['status'], 'OFFERED')

        # 3. Passenger accepts offer
        with patch('parahub.endpoints.matrix_auth.create_dm_between_accounts', return_value='!dm:room'):
            accept_body = AcceptOfferBody(booking_id=booking_id)
            req = _make_auth_request(self.factory, self.passenger_account, self.passenger, 'patch')
            accept_result = accept_offer(req, request_id, accept_body)
        self.assertEqual(accept_result['status'], 'CONFIRMED')

        # 4. Driver marks completed
        complete_body = BookingStatusUpdate(status='COMPLETED')
        req = _make_auth_request(self.factory, self.driver_account, self.driver, 'patch')
        complete_result = update_booking(req, booking_id, complete_body)
        self.assertEqual(complete_result['status'], 'COMPLETED')

        # 5. Both parties review
        review_body = ReviewCreate(rating=5, comment='Excellent')
        req = _make_auth_request(self.factory, self.passenger_account, self.passenger, 'post')
        passenger_review = leave_review(req, booking_id, review_body)
        self.assertEqual(passenger_review['rating'], 5)

        review_body = ReviewCreate(rating=4, comment='Good passenger')
        req = _make_auth_request(self.factory, self.driver_account, self.driver, 'post')
        driver_review = leave_review(req, booking_id, review_body)
        self.assertEqual(driver_review['rating'], 4)

    def test_competitive_offers_lifecycle(self):
        """Two drivers offer, one accepted, other cancelled."""
        from parahub.endpoints.rides import (
            create_request, offer_ride, accept_offer,
            RideRequestCreate, BookingOfferCreate, AcceptOfferBody,
        )

        req_body = RideRequestCreate(
            origin_stop_id=self.origin.id,
            destination_stop_id=self.destination.id,
            price_sats=500,
        )
        req = _make_auth_request(self.factory, self.passenger_account, self.passenger, 'post')
        req_result = create_request(req, req_body)
        request_id = req_result['id']

        offer_body = BookingOfferCreate(available_seats=2)
        req = _make_auth_request(self.factory, self.driver_account, self.driver, 'post')
        offer1 = offer_ride(req, request_id, offer_body)

        req = _make_auth_request(self.factory, self.driver2_account, self.driver2, 'post')
        offer2 = offer_ride(req, request_id, offer_body)

        with patch('parahub.endpoints.matrix_auth.create_dm_between_accounts', return_value=None):
            accept_body = AcceptOfferBody(booking_id=offer2['id'])
            req = _make_auth_request(self.factory, self.passenger_account, self.passenger, 'patch')
            accept_offer(req, request_id, accept_body)

        b1 = RideBooking.objects.get(id=offer1['id'])
        b2 = RideBooking.objects.get(id=offer2['id'])
        self.assertEqual(b1.status, 'CANCELLED')
        self.assertEqual(b2.status, 'CONFIRMED')

        ride_req = RideRequest.objects.get(id=request_id)
        self.assertFalse(ride_req.is_active)


# ---------------------------------------------------------------------------
# Stop info helper tests
# ---------------------------------------------------------------------------

class StopInfoHelperTest(CarpoolTestBase):
    """Test _stop_info() helper."""

    def test_stop_info_returns_data(self):
        from parahub.endpoints.rides import _stop_info
        info = _stop_info(self.origin)
        self.assertEqual(info['id'], self.origin.id)
        self.assertEqual(info['name'], 'Origin Station')
        self.assertAlmostEqual(info['lat'], 38.7223, places=3)
        self.assertAlmostEqual(info['lon'], -9.1393, places=3)

    def test_stop_info_none(self):
        from parahub.endpoints.rides import _stop_info
        self.assertIsNone(_stop_info(None))


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

class EdgeCaseTest(CarpoolTestBase):
    """Test edge cases and boundary conditions."""

    def test_request_with_null_stops_after_deletion(self):
        """Request still works if stops are deleted (SET_NULL)."""
        extra_origin = Stop.objects.create(
            agency=self.agency, name='Temp Origin', source_id='temp-o',
            location=Point(-9.2, 38.8, srid=4326),
        )
        extra_dest = Stop.objects.create(
            agency=self.agency, name='Temp Dest', source_id='temp-d',
            location=Point(-9.3, 38.9, srid=4326),
        )
        req = _create_ride_request(self.passenger, extra_origin, extra_dest)
        extra_origin.delete()
        extra_dest.delete()
        req.refresh_from_db()
        self.assertIsNone(req.origin_stop)
        self.assertIsNone(req.destination_stop)

    def test_booking_response_null_matrix_room(self):
        """Booking response handles empty matrix_room_id."""
        from parahub.endpoints.rides import _booking_response
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver)
        result = _booking_response(booking)
        self.assertIsNone(result['matrix_room_id'])

    def test_booking_response_with_matrix_room(self):
        """Booking response includes matrix_room_id when set."""
        from parahub.endpoints.rides import _booking_response
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, matrix_room_id='!test:room')
        result = _booking_response(booking)
        self.assertEqual(result['matrix_room_id'], '!test:room')

    def test_unique_review_constraint(self):
        """DB-level unique constraint prevents duplicate reviews."""
        from django.db import IntegrityError
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        booking = _create_booking(req, self.driver, status=RideBooking.Status.COMPLETED)
        _create_review(booking, self.driver, self.passenger, rating=5)
        with self.assertRaises(IntegrityError):
            _create_review(booking, self.driver, self.passenger, rating=3)

    def test_request_ordering(self):
        """Requests are ordered by -created_at."""
        r1 = _create_ride_request(self.passenger, self.origin, self.destination)
        r2 = _create_ride_request(self.passenger, self.origin, self.destination)
        qs = RideRequest.objects.filter(passenger=self.passenger)
        self.assertEqual(qs[0].id, r2.id)
        self.assertEqual(qs[1].id, r1.id)

    def test_booking_ordering(self):
        """Bookings are ordered by -created_at."""
        req = _create_ride_request(self.passenger, self.origin, self.destination)
        b1 = _create_booking(req, self.driver)
        b2 = _create_booking(req, self.driver2)
        qs = RideBooking.objects.filter(request=req)
        self.assertEqual(qs[0].id, b2.id)
        self.assertEqual(qs[1].id, b1.id)


# ===========================================================================
# Shipment expire_shipments command tests
# ===========================================================================

from unittest.mock import patch as mock_patch
from logistics.models import Shipment, ShipmentEvent
from geo.models import Establishment, WorldObject


def _create_establishment(owner, name='Hub A'):
    """Create a minimal Establishment for shipment tests."""
    return Establishment.objects.create(
        owner=owner,
        name=name,
    )


def _create_shipment(sender, receiver, origin_hub, destination_hub,
                     status=Shipment.Status.CREATED, **kwargs):
    """Create a Shipment directly in DB."""
    return Shipment.objects.create(
        sender=sender,
        receiver=receiver,
        origin_hub=origin_hub,
        destination_hub=destination_hub,
        title='Test Parcel',
        size_category=Shipment.SizeCategory.M,
        status=status,
        **kwargs,
    )


class ExpireShipmentsTestBase(TestCase):
    """Base for expire_shipments command tests."""

    def setUp(self):
        self.instance = _create_instance()
        self.alice_account = _create_account(self.instance, username='alice_ship')
        self.alice_profile = _create_profile(self.alice_account, self.instance, local_name='alice_ship')
        self.bob_account = _create_account(self.instance, username='bob_ship')
        self.bob_profile = _create_profile(self.bob_account, self.instance, local_name='bob_ship')

        self.hub_a = _create_establishment(self.alice_profile, name='Hub A')
        self.hub_b = _create_establishment(self.bob_profile, name='Hub B')


class ExpireDepositedShipmentsTest(ExpireShipmentsTestBase):
    """Test expiry of deposited shipments past expires_at."""

    @mock_patch('logistics.management.commands.expire_shipments._notify_expired')
    def test_at_origin_past_expiry_gets_expired(self, mock_notify):
        ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.AT_ORIGIN,
            current_hub=self.hub_a,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        from django.core.management import call_command
        call_command('expire_shipments')
        ship.refresh_from_db()
        self.assertEqual(ship.status, Shipment.Status.EXPIRED)

    @mock_patch('logistics.management.commands.expire_shipments._notify_expired')
    def test_at_hub_past_expiry_gets_expired(self, mock_notify):
        ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.AT_HUB,
            current_hub=self.hub_a,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        from django.core.management import call_command
        call_command('expire_shipments')
        ship.refresh_from_db()
        self.assertEqual(ship.status, Shipment.Status.EXPIRED)

    @mock_patch('logistics.management.commands.expire_shipments._notify_expired')
    def test_ready_past_expiry_gets_expired(self, mock_notify):
        ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.READY,
            current_hub=self.hub_b,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        from django.core.management import call_command
        call_command('expire_shipments')
        ship.refresh_from_db()
        self.assertEqual(ship.status, Shipment.Status.EXPIRED)

    @mock_patch('logistics.management.commands.expire_shipments._notify_expired')
    def test_event_created_on_expiry(self, mock_notify):
        ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.AT_ORIGIN,
            current_hub=self.hub_a,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        from django.core.management import call_command
        call_command('expire_shipments')
        event = ShipmentEvent.objects.filter(shipment=ship).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, ShipmentEvent.EventType.EXPIRED)
        self.assertIn('storage period exceeded', event.note)

    @mock_patch('logistics.management.commands.expire_shipments._notify_expired')
    def test_future_expiry_not_touched(self, mock_notify):
        ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.AT_ORIGIN,
            current_hub=self.hub_a,
            expires_at=timezone.now() + timedelta(days=3),
        )
        from django.core.management import call_command
        call_command('expire_shipments')
        ship.refresh_from_db()
        self.assertEqual(ship.status, Shipment.Status.AT_ORIGIN)


class ExpireUnaffectedStatusesTest(ExpireShipmentsTestBase):
    """Test that DELIVERED/CANCELLED/IN_TRANSIT shipments are NOT expired."""

    @mock_patch('logistics.management.commands.expire_shipments._notify_expired')
    def test_delivered_not_expired(self, mock_notify):
        ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.DELIVERED,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        from django.core.management import call_command
        call_command('expire_shipments')
        ship.refresh_from_db()
        self.assertEqual(ship.status, Shipment.Status.DELIVERED)

    @mock_patch('logistics.management.commands.expire_shipments._notify_expired')
    def test_cancelled_not_expired(self, mock_notify):
        ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.CANCELLED,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        from django.core.management import call_command
        call_command('expire_shipments')
        ship.refresh_from_db()
        self.assertEqual(ship.status, Shipment.Status.CANCELLED)

    @mock_patch('logistics.management.commands.expire_shipments._notify_expired')
    def test_in_transit_not_expired(self, mock_notify):
        """IN_TRANSIT is not in the expired-status filter."""
        ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.IN_TRANSIT,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        from django.core.management import call_command
        call_command('expire_shipments')
        ship.refresh_from_db()
        self.assertEqual(ship.status, Shipment.Status.IN_TRANSIT)


class ExpireStaleCreatedShipmentsTest(ExpireShipmentsTestBase):
    """Test stale CREATED shipments (>7 days) get expired."""

    @mock_patch('logistics.management.commands.expire_shipments._notify_expired')
    def test_stale_created_expired(self, mock_notify):
        ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.CREATED,
        )
        # Backdate created_at to 8 days ago
        Shipment.objects.filter(id=ship.id).update(
            created_at=timezone.now() - timedelta(days=8)
        )
        from django.core.management import call_command
        call_command('expire_shipments')
        ship.refresh_from_db()
        self.assertEqual(ship.status, Shipment.Status.EXPIRED)

    @mock_patch('logistics.management.commands.expire_shipments._notify_expired')
    def test_stale_created_event_note(self, mock_notify):
        ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.CREATED,
        )
        Shipment.objects.filter(id=ship.id).update(
            created_at=timezone.now() - timedelta(days=8)
        )
        from django.core.management import call_command
        call_command('expire_shipments')
        event = ShipmentEvent.objects.filter(shipment=ship).first()
        self.assertIsNotNone(event)
        self.assertIn('not deposited within 7 days', event.note)

    @mock_patch('logistics.management.commands.expire_shipments._notify_expired')
    def test_recent_created_not_expired(self, mock_notify):
        """CREATED shipment within grace period stays."""
        ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.CREATED,
        )
        from django.core.management import call_command
        call_command('expire_shipments')
        ship.refresh_from_db()
        self.assertEqual(ship.status, Shipment.Status.CREATED)

    @mock_patch('logistics.management.commands.expire_shipments._notify_expired')
    def test_mixed_batch(self, mock_notify):
        """Multiple shipments: only eligible ones get expired."""
        expired_ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.AT_ORIGIN,
            current_hub=self.hub_a,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        active_ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.AT_ORIGIN,
            current_hub=self.hub_a,
            expires_at=timezone.now() + timedelta(days=3),
        )
        delivered_ship = _create_shipment(
            self.alice_profile, self.bob_profile, self.hub_a, self.hub_b,
            status=Shipment.Status.DELIVERED,
        )
        from django.core.management import call_command
        call_command('expire_shipments')

        expired_ship.refresh_from_db()
        active_ship.refresh_from_db()
        delivered_ship.refresh_from_db()

        self.assertEqual(expired_ship.status, Shipment.Status.EXPIRED)
        self.assertEqual(active_ship.status, Shipment.Status.AT_ORIGIN)
        self.assertEqual(delivered_ship.status, Shipment.Status.DELIVERED)
