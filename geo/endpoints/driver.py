"""
Driver Mode API: self-service GPS broadcasting for transit drivers.

Drivers select a route and broadcast GPS from browser/tablet.
Positions flow through the same Redis transit pipeline as GTFS-RT.

A shift publishes into the route operator's public feed, so it is an operator
function: staff, the agency owner (WoT 3+, the self-serve path), or a member of
the organization that runs the agency (employment is the trust anchor there).
"""

import logging
from typing import List, Optional

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from geo.models import DriverShift, Route
from geo.permissions import can_operate_agency

logger = logging.getLogger(__name__)
router = Router(tags=["Driver"])


# --- Schemas ---

class ShiftStartIn(Schema):
    route_id: str
    direction_id: int = 0


class ShiftOut(Schema):
    id: str
    object_type: str = "driver_shift"
    route_id: str
    route_short_name: str
    route_long_name: str
    route_color: str
    route_type: int
    route_source_id: str
    data_source_id: str
    direction_id: int
    vehicle_id: str
    status: str
    started_at: str
    ended_at: Optional[str] = None
    position_count: int
    place_slug: str = ""
    # Route detail (both directions' stop lists, headsigns, geometry) is only
    # addressable by place+route slug — the HUD route ladder needs both.
    route_slug: str = ""
    heartbeat_alive: Optional[bool] = None

    @classmethod
    def from_shift(cls, s: DriverShift, heartbeat_alive: Optional[bool] = None):
        return cls(
            id=str(s.id),
            route_id=str(s.route_id),
            route_short_name=s.route.short_name,
            route_long_name=s.route.long_name,
            route_color=s.route.route_color or "",
            route_type=s.route.route_type,
            route_source_id=s.route.source_id,
            data_source_id=str(s.data_source_id),
            direction_id=s.direction_id,
            vehicle_id=s.vehicle_id,
            status=s.status,
            started_at=s.started_at.isoformat(),
            ended_at=s.ended_at.isoformat() if s.ended_at else None,
            position_count=s.position_count,
            place_slug=s.route.place.slug if s.route.place else "",
            route_slug=s.route.slug,
            heartbeat_alive=heartbeat_alive,
        )


# --- Helpers ---

def _check_wot(profile):
    """WoT 3+ or staff required."""
    if profile.account.is_staff:
        return
    if not profile.is_verified_wot:
        raise HttpError(403, "WoT 3+ verification required for Driver Mode")


def _check_route_operator(profile, route):
    """
    Only the route's operator may broadcast on it.

    A shift injects a vehicle into `transit:vdata` under the route's data
    source, which is what the public map and that source's GTFS-RT feed serve —
    so an outsider starting a shift is a phantom bus on someone else's line.

    Solo operator (`Agency.owner`) still passes the WoT gate: their vehicles
    show up on the public map and the social graph is the only anchor they have.
    An employee of the organization running the agency does not — the employment
    relation is the anchor, and hired drivers will not have three in-person
    verifications.
    """
    if profile.account.is_staff:
        return

    agency = route.agency

    if agency.owner_id and agency.owner_id == profile.id:
        _check_wot(profile)
        return

    if agency.establishment_id and can_operate_agency(profile, agency, 'transit.drive'):
        return

    raise HttpError(403, "Driver Mode is limited to routes of your own operator")


def _is_heartbeat_alive(shift: DriverShift) -> bool:
    """Check if driver heartbeat key exists in Redis (TTL 45s)."""
    from parahub.services.redis_pool import get_redis
    try:
        return bool(get_redis().exists(f'driver:heartbeat:{shift.id}'))
    except Exception:
        return False


# --- Endpoints ---

@router.post("/start/", response=ShiftOut, auth=ProfileAuth())
@ratelimit(group='driver:start', key=user_or_ip, rate='10/m', method='POST')
def start_shift(request, payload: ShiftStartIn):
    """Start a driver shift — begin GPS broadcasting on a route."""
    profile = request.auth_profile

    route = get_object_or_404(
        Route.objects.select_related('agency__data_source', 'place'),
        id=payload.route_id,
    )
    _check_route_operator(profile, route)

    # Check no active shift already
    active_shift = (
        DriverShift.objects
        .filter(profile=profile, status='ACTIVE')
        .select_related('route__place', 'data_source')
        .first()
    )
    if active_shift:
        if _is_heartbeat_alive(active_shift):
            raise HttpError(409, "You already have an active shift. Stop it first.")
        # Stale shift (heartbeat expired) — auto-end it so driver can start fresh
        active_shift.status = 'ENDED'
        active_shift.ended_at = timezone.now()
        active_shift.save(update_fields=['status', 'ended_at', 'updated_at'])
        _clean_transit_pipeline(active_shift)
        logger.info(f"Auto-ended stale shift {active_shift.id} for profile {profile.id}")

    vehicle_id = f"D{profile.id[:8]}"
    shift = DriverShift.objects.create(
        profile=profile,
        route=route,
        data_source=route.agency.data_source,
        direction_id=payload.direction_id,
        vehicle_id=vehicle_id,
    )

    shift = (
        DriverShift.objects
        .select_related('route__agency__data_source', 'route__place')
        .get(id=shift.id)
    )
    return ShiftOut.from_shift(shift)


@router.post("/stop/{shift_id}/", response=ShiftOut, auth=ProfileAuth())
@ratelimit(group='driver:stop', key=user_or_ip, rate='10/m', method='POST')
def stop_shift(request, shift_id: str):
    """End a driver shift — stop GPS broadcasting."""
    profile = request.auth_profile

    shift = get_object_or_404(
        DriverShift.objects.select_related('route__place', 'data_source'),
        id=shift_id,
        profile=profile,
    )
    if shift.status != 'ACTIVE':
        raise HttpError(400, "Shift is not active")

    shift.status = 'ENDED'
    shift.ended_at = timezone.now()
    shift.save(update_fields=['status', 'ended_at', 'updated_at'])

    # Clean Redis transit pipeline
    _clean_transit_pipeline(shift)

    return ShiftOut.from_shift(shift)


@router.get("/active/", response={200: ShiftOut, 204: None}, auth=ProfileAuth())
@ratelimit(group='driver:active', key=user_or_ip, rate='60/m')
def get_active_shift(request):
    """Get current active shift for the authenticated user."""
    profile = request.auth_profile

    shift = (
        DriverShift.objects
        .filter(profile=profile, status='ACTIVE')
        .select_related('route__agency__data_source', 'route__place')
        .first()
    )
    if not shift:
        return 204, None
    return 200, ShiftOut.from_shift(shift, heartbeat_alive=_is_heartbeat_alive(shift))


@router.get("/history/", response=List[ShiftOut], auth=ProfileAuth())
@ratelimit(group='driver:history', key=user_or_ip, rate='30/m')
def shift_history(request):
    """List past shifts for the authenticated user (last 50)."""
    profile = request.auth_profile

    shifts = (
        DriverShift.objects
        .filter(profile=profile)
        .select_related('route__place')
        .order_by('-started_at')[:50]
    )
    return [ShiftOut.from_shift(s) for s in shifts]


def _clean_transit_pipeline(shift: DriverShift):
    """Remove driver vehicle from Redis transit keys."""
    from parahub.services.redis_pool import get_redis

    try:
        r = get_redis()
        ds_id = str(shift.data_source_id)
        member = f"{ds_id}:{shift.vehicle_id}"
        pipe = r.pipeline(transaction=False)
        pipe.zrem('transit:geo', member)
        pipe.hdel('transit:vdata', member)
        pipe.srem(f'transit:members:{ds_id}', member)
        pipe.delete(f'driver:heartbeat:{shift.id}')
        pipe.execute()
        # Signal map consumers to refresh
        r.publish('transit:tick', str(int(timezone.now().timestamp())))
    except Exception as e:
        logger.warning(f"Failed to clean transit pipeline for shift {shift.id}: {e}")
