"""
Carpool API endpoints.
Passenger-driven marketplace: passenger creates request, drivers offer rides.
"""

from ninja import Router
from ninja.errors import HttpError
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import timedelta
from django.utils import timezone
from django.contrib.gis.geos import Point, LineString
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Avg, Count, Value
import logging
import requests as http_requests

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from logistics.models import RideRequest, RideBooking, RideReview

logger = logging.getLogger(__name__)

rides_router = Router()

RIDE_REQUEST_TTL_MINUTES = 60


# --- Schemas ---

class StopInfo(BaseModel):
    id: str
    name: str
    lat: float
    lon: float

class ProfileBrief(BaseModel):
    id: str
    display_name: str
    hna: Optional[str] = None
    avatar_url: Optional[str] = None
    ride_rating: Optional[float] = None
    ride_count: int = 0

class RideRequestCreate(BaseModel):
    origin_stop_id: str
    destination_stop_id: str
    price_sats: int = Field(ge=0)
    passengers_count: int = Field(default=1, ge=1, le=10)
    note: str = Field(default='', max_length=500)

class BookingOfferCreate(BaseModel):
    driver_note: str = Field(default='', max_length=500)
    available_seats: int = Field(default=3, ge=1, le=20)

class AcceptOfferBody(BaseModel):
    booking_id: str

class BookingStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(COMPLETED|CANCELLED)$")


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default='', max_length=1000)


class RouteLocation(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RouteSearchBody(BaseModel):
    origin: RouteLocation
    destination: RouteLocation
    corridor_km: float = Field(default=0.5, ge=0.1, le=5.0)


# --- Helpers ---

def _stop_info(stop) -> Optional[dict]:
    if not stop:
        return None
    return {
        'id': stop.id,
        'name': stop.name,
        'lat': stop.location.y,
        'lon': stop.location.x,
    }

def _load_ride_stats(profile_ids):
    """Batch-load ride review stats for multiple profiles. Returns {profile_id: {avg_rating, count}}."""
    if not profile_ids:
        return {}
    stats = RideReview.objects.filter(
        reviewee_id__in=profile_ids
    ).values('reviewee_id').annotate(
        avg_rating=Avg('rating'),
        count=Count('id'),
    )
    return {s['reviewee_id']: s for s in stats}


def _profile_brief(profile, ride_stats_map=None) -> dict:
    if ride_stats_map is not None:
        stats = ride_stats_map.get(profile.id, {})
        avg_rating = stats.get('avg_rating')
        ride_count = stats.get('count', 0)
    else:
        stats = RideReview.objects.filter(reviewee=profile).aggregate(
            avg_rating=Avg('rating'),
            count=Count('id'),
        )
        avg_rating = stats['avg_rating']
        ride_count = stats['count']
    return {
        'id': profile.id,
        'display_name': profile.display_name,
        'hna': profile.hna,
        'avatar_url': profile.avatar_url if hasattr(profile, 'avatar_url') else None,
        'ride_rating': round(avg_rating, 1) if avg_rating else None,
        'ride_count': ride_count,
    }

def _booking_response(booking, ride_stats_map=None) -> dict:
    return {
        'id': booking.id,
        'object_type': 'ride_booking',
        'status': booking.status,
        'driver': _profile_brief(booking.driver, ride_stats_map),
        'driver_note': booking.driver_note,
        'available_seats': booking.available_seats,
        'matrix_room_id': booking.matrix_room_id or None,
        'created_at': booking.created_at.isoformat(),
    }

def _request_response(req, include_bookings=False, ride_stats_map=None) -> dict:
    data = {
        'id': req.id,
        'object_type': 'ride_request',
        'passenger': _profile_brief(req.passenger, ride_stats_map),
        'origin_stop': _stop_info(req.origin_stop),
        'destination_stop': _stop_info(req.destination_stop),
        'price_sats': req.price_sats,
        'passengers_count': req.passengers_count,
        'note': req.note,
        'is_active': req.is_active,
        'created_at': req.created_at.isoformat(),
        'bookings_count': getattr(req, '_bookings_count', None) or req.bookings.count(),
    }
    if include_bookings:
        bookings = req.bookings.select_related('driver').order_by('-created_at')
        data['bookings'] = [_booking_response(b, ride_stats_map) for b in bookings]
    return data

def _active_requests_qs():
    """Queryset for active, non-expired ride requests."""
    cutoff = timezone.now() - timedelta(minutes=RIDE_REQUEST_TTL_MINUTES)
    return RideRequest.objects.filter(
        is_active=True,
        created_at__gte=cutoff,
    ).select_related('passenger', 'origin_stop', 'destination_stop')


def _decode_polyline6(encoded: str) -> list[tuple[float, float]]:
    """Decode Valhalla polyline6 to list of (lon, lat) tuples (GIS order)."""
    result = []
    i = lat = lng = 0
    while i < len(encoded):
        for idx in range(2):
            shift = val = 0
            while True:
                b = ord(encoded[i]) - 63
                i += 1
                val |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            if val & 1:
                val = ~(val >> 1)
            else:
                val >>= 1
            if idx == 0:
                lat += val
            else:
                lng += val
        result.append((lng * 1e-6, lat * 1e-6))  # lon, lat for GIS
    return result


def _get_valhalla_route(origin: RouteLocation, destination: RouteLocation) -> Optional[LineString]:
    """Get route geometry from Valhalla as PostGIS LineString."""
    try:
        resp = http_requests.post(
            'http://localhost:8002/route',
            json={
                'locations': [
                    {'lat': origin.lat, 'lon': origin.lon},
                    {'lat': destination.lat, 'lon': destination.lon},
                ],
                'costing': 'auto',
                'shape_format': 'polyline6',
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"Valhalla route request failed: {e}")
        return None

    legs = data.get('trip', {}).get('legs', [])
    if not legs:
        return None

    all_coords = []
    for leg in legs:
        shape = leg.get('shape', '')
        if shape:
            all_coords.extend(_decode_polyline6(shape))

    if len(all_coords) < 2:
        return None

    return LineString(all_coords, srid=4326)


# --- Passenger Endpoints ---

@rides_router.post("/requests/", response={200: dict, 400: dict, 403: dict}, auth=ProfileAuth())
@ratelimit(group='rides:create_request', key=user_or_ip, rate='10/m', method='POST')
def create_request(request, body: RideRequestCreate):
    """Create a ride request. Requires WoT 2+ verification."""
    profile = request.auth
    if not profile.is_verified_wot:
        raise HttpError(403, "WoT verification required to create ride requests")

    from geo.models import Stop
    origin = Stop.objects.filter(id=body.origin_stop_id).first()
    if not origin:
        raise HttpError(400, "Origin stop not found")
    destination = Stop.objects.filter(id=body.destination_stop_id).first()
    if not destination:
        raise HttpError(400, "Destination stop not found")

    ride_req = RideRequest.objects.create(
        passenger=profile,
        origin_stop=origin,
        destination_stop=destination,
        price_sats=body.price_sats,
        passengers_count=body.passengers_count,
        note=body.note,
    )
    return _request_response(ride_req)


@rides_router.get("/requests/", auth=ProfileAuth())
@ratelimit(group='rides:my_requests', key=user_or_ip, rate='30/m')
def my_requests(request):
    """List my active ride requests."""
    profile = request.auth
    cutoff = timezone.now() - timedelta(minutes=RIDE_REQUEST_TTL_MINUTES)
    qs = RideRequest.objects.filter(
        passenger=profile,
        is_active=True,
        created_at__gte=cutoff,
    ).select_related('passenger', 'origin_stop', 'destination_stop').annotate(
        _bookings_count=Count('bookings')
    )
    results = list(qs)
    profile_ids = {r.passenger_id for r in results}
    stats_map = _load_ride_stats(profile_ids)
    return [_request_response(r, ride_stats_map=stats_map) for r in results]


@rides_router.get("/requests/{request_id}/", response={200: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='rides:request_detail', key=user_or_ip, rate='30/m')
def get_request(request, request_id: str):
    """Get request detail with driver offers (bookings visible to passenger only)."""
    profile = request.auth
    ride_req = RideRequest.objects.filter(id=request_id).select_related(
        'passenger', 'origin_stop', 'destination_stop'
    ).first()
    if not ride_req:
        raise HttpError(404, "Request not found")
    # Only the passenger can see driver offers to prevent IDOR
    is_owner = ride_req.passenger_id == profile.id
    resp = _request_response(ride_req, include_bookings=is_owner)

    # Include whether the viewer has already reviewed any booking for this request
    resp['viewer_has_reviewed'] = RideReview.objects.filter(
        booking__request=ride_req,
        reviewer=profile,
    ).exists()

    return resp


@rides_router.delete("/requests/{request_id}/", response={200: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='rides:cancel_request', key=user_or_ip, rate='10/m', method='DELETE')
def cancel_request(request, request_id: str):
    """Cancel own request."""
    profile = request.auth
    ride_req = RideRequest.objects.filter(id=request_id, passenger=profile).first()
    if not ride_req:
        raise HttpError(404, "Request not found")

    ride_req.is_active = False
    ride_req.save(update_fields=['is_active', 'updated_at'])

    # Cancel all pending offers
    ride_req.bookings.filter(status=RideBooking.Status.OFFERED).update(
        status=RideBooking.Status.CANCELLED
    )

    return {"success": True}


@rides_router.patch("/requests/{request_id}/accept/", response={200: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='rides:accept_offer', key=user_or_ip, rate='10/m', method='PATCH')
def accept_offer(request, request_id: str, body: AcceptOfferBody):
    """Passenger accepts a specific driver offer."""
    profile = request.auth
    ride_req = RideRequest.objects.filter(id=request_id, passenger=profile, is_active=True).first()
    if not ride_req:
        raise HttpError(404, "Request not found or not yours")

    booking = RideBooking.objects.filter(
        id=body.booking_id,
        request=ride_req,
        status=RideBooking.Status.OFFERED,
    ).select_related('driver').first()
    if not booking:
        raise HttpError(404, "Offer not found or already processed")

    # Confirm this booking
    booking.status = RideBooking.Status.CONFIRMED
    booking.save(update_fields=['status', 'updated_at'])

    # Cancel all other offers for this request
    ride_req.bookings.filter(status=RideBooking.Status.OFFERED).exclude(id=booking.id).update(
        status=RideBooking.Status.CANCELLED
    )

    # Deactivate the request (no more offers needed)
    ride_req.is_active = False
    ride_req.save(update_fields=['is_active', 'updated_at'])

    # Auto-create Matrix DM
    try:
        from parahub.endpoints.matrix_auth import create_dm_between_accounts
        room_id = create_dm_between_accounts(
            str(profile.account_id),
            str(booking.driver.account_id),
        )
        if room_id:
            booking.matrix_room_id = room_id
            booking.save(update_fields=['matrix_room_id', 'updated_at'])
    except Exception as e:
        logger.warning(f"Failed to create Matrix DM for ride booking: {e}")

    return _booking_response(booking)


# --- Driver Endpoints ---

@rides_router.get("/search/", auth=ProfileAuth())
@ratelimit(group='rides:search', key=user_or_ip, rate='30/m')
def search_requests(request, lat: float, lon: float, radius_km: float = 2):
    """Search active ride requests near driver's location."""
    profile = request.auth
    radius_km = min(radius_km, 50)
    driver_point = Point(lon, lat, srid=4326)

    qs = _active_requests_qs().exclude(
        passenger=profile,
    ).filter(
        origin_stop__location__distance_lte=(driver_point, D(km=radius_km)),
    ).annotate(
        distance=Distance('origin_stop__location', driver_point),
    ).order_by('distance')

    results = list(qs)
    profile_ids = {r.passenger_id for r in results}
    stats_map = _load_ride_stats(profile_ids)
    return [
        {**_request_response(r, ride_stats_map=stats_map), 'distance_m': round(r.distance.m)}
        for r in results
    ]


@rides_router.post("/search/route/", response={200: list, 502: dict}, auth=ProfileAuth())
@ratelimit(group='rides:search_route', key=user_or_ip, rate='20/m', method='POST')
def search_by_route(request, body: RouteSearchBody):
    """Search active ride requests along driver's planned route.

    Calls Valhalla to get route geometry, then finds requests where both
    origin and destination stops are within the corridor, in the correct
    direction along the route.
    """
    route_line = _get_valhalla_route(body.origin, body.destination)
    if route_line is None:
        raise HttpError(502, "Could not calculate route")

    from django.contrib.gis.db.models.functions import LineLocatePoint

    corridor = D(km=body.corridor_km)

    # Find requests where BOTH stops are within the corridor of the route
    profile = request.auth
    qs = _active_requests_qs().exclude(
        passenger=profile,
    ).filter(
        origin_stop__location__distance_lte=(route_line, corridor),
        destination_stop__location__distance_lte=(route_line, corridor),
    ).annotate(
        origin_fraction=LineLocatePoint(Value(route_line), 'origin_stop__location'),
        dest_fraction=LineLocatePoint(Value(route_line), 'destination_stop__location'),
        origin_distance=Distance('origin_stop__location', route_line),
        dest_distance=Distance('destination_stop__location', route_line),
    )

    matched = list(qs)
    profile_ids = {r.passenger_id for r in matched}
    stats_map = _load_ride_stats(profile_ids)

    results = []
    for r in matched:
        # Filter: origin must come before destination along route direction
        if r.origin_fraction >= r.dest_fraction:
            continue
        results.append({
            **_request_response(r, ride_stats_map=stats_map),
            'origin_distance_m': round(r.origin_distance.m),
            'dest_distance_m': round(r.dest_distance.m),
            'origin_fraction': round(r.origin_fraction, 4),
            'dest_fraction': round(r.dest_fraction, 4),
        })

    # Sort by position along route (earliest pickup first)
    results.sort(key=lambda x: x['origin_fraction'])
    return results


@rides_router.post("/requests/{request_id}/offer/", response={200: dict, 400: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='rides:offer', key=user_or_ip, rate='10/m', method='POST')
def offer_ride(request, request_id: str, body: BookingOfferCreate):
    """Driver offers to drive for a request."""
    profile = request.auth
    ride_req = RideRequest.objects.filter(id=request_id).select_related('passenger').first()
    if not ride_req:
        raise HttpError(404, "Request not found")
    if not ride_req.is_active:
        raise HttpError(400, "Request is no longer active")

    # Check expiry
    cutoff = timezone.now() - timedelta(minutes=RIDE_REQUEST_TTL_MINUTES)
    if ride_req.created_at < cutoff:
        raise HttpError(400, "Request has expired")

    # Can't offer on own request
    if ride_req.passenger_id == profile.id:
        raise HttpError(400, "Cannot offer ride on your own request")

    # Check if already offered
    existing = RideBooking.objects.filter(
        request=ride_req, driver=profile
    ).exclude(status=RideBooking.Status.CANCELLED).first()
    if existing:
        raise HttpError(400, "You already have an active offer for this request")

    booking = RideBooking.objects.create(
        request=ride_req,
        driver=profile,
        driver_note=body.driver_note,
        available_seats=body.available_seats,
    )
    return _booking_response(booking)


# --- Shared Endpoints ---

@rides_router.get("/bookings/", auth=ProfileAuth())
@ratelimit(group='rides:my_bookings', key=user_or_ip, rate='30/m')
def my_bookings(request):
    """List my bookings (as driver or passenger)."""
    from django.db.models import Q
    profile = request.auth
    qs = RideBooking.objects.filter(
        Q(driver=profile) | Q(request__passenger=profile)
    ).select_related(
        'driver', 'request__passenger', 'request__origin_stop', 'request__destination_stop'
    ).order_by('-created_at')[:50]

    bookings = list(qs)
    profile_ids = set()
    for b in bookings:
        profile_ids.add(b.driver_id)
        profile_ids.add(b.request.passenger_id)
    stats_map = _load_ride_stats(profile_ids)

    results = []
    for b in bookings:
        data = _booking_response(b, ride_stats_map=stats_map)
        data['request'] = _request_response(b.request, ride_stats_map=stats_map)
        data['role'] = 'driver' if b.driver_id == profile.id else 'passenger'
        results.append(data)
    return results


@rides_router.patch("/bookings/{booking_id}/", response={200: dict, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='rides:update_booking', key=user_or_ip, rate='20/m', method='PATCH')
def update_booking(request, booking_id: str, body: BookingStatusUpdate):
    """Mark booking as completed or cancelled."""
    profile = request.auth
    new_status = body.status

    booking = RideBooking.objects.filter(id=booking_id).select_related(
        'driver', 'request__passenger'
    ).first()
    if not booking:
        raise HttpError(404, "Booking not found")

    # Only driver or passenger can update
    is_driver = booking.driver_id == profile.id
    is_passenger = booking.request.passenger_id == profile.id
    if not is_driver and not is_passenger:
        raise HttpError(403, "Not your booking")

    # Can only complete confirmed bookings
    if new_status == 'COMPLETED' and booking.status != RideBooking.Status.CONFIRMED:
        raise HttpError(400, "Can only complete confirmed bookings")

    # Can cancel offered or confirmed bookings
    if new_status == 'CANCELLED' and booking.status not in (
        RideBooking.Status.OFFERED, RideBooking.Status.CONFIRMED
    ):
        raise HttpError(400, "Cannot cancel this booking")

    booking.status = new_status
    booking.save(update_fields=['status', 'updated_at'])
    return _booking_response(booking)


@rides_router.post("/bookings/{booking_id}/review/", response={200: dict, 400: dict, 403: dict, 404: dict}, auth=ProfileAuth())
@ratelimit(group='rides:review', key=user_or_ip, rate='10/m', method='POST')
def leave_review(request, booking_id: str, body: ReviewCreate):
    """Leave a review after a completed ride."""
    profile = request.auth

    booking = RideBooking.objects.filter(
        id=booking_id,
        status=RideBooking.Status.COMPLETED,
    ).select_related('driver', 'request__passenger').first()
    if not booking:
        raise HttpError(404, "Completed booking not found")

    is_driver = booking.driver_id == profile.id
    is_passenger = booking.request.passenger_id == profile.id
    if not is_driver and not is_passenger:
        raise HttpError(403, "Not your booking")

    # Determine reviewee
    reviewee = booking.request.passenger if is_driver else booking.driver

    # Check for existing review
    if RideReview.objects.filter(booking=booking, reviewer=profile).exists():
        raise HttpError(400, "You already reviewed this ride")

    review = RideReview.objects.create(
        booking=booking,
        reviewer=profile,
        reviewee=reviewee,
        rating=body.rating,
        comment=body.comment,
    )
    return {
        'id': review.id,
        'object_type': 'ride_review',
        'rating': review.rating,
        'comment': review.comment,
        'reviewer': _profile_brief(profile),
        'reviewee': _profile_brief(reviewee),
        'created_at': review.created_at.isoformat(),
    }
