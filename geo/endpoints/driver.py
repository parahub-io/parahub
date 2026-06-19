"""
Driver Mode API: self-service GPS broadcasting for transit drivers.

Drivers select a GTFS route and broadcast GPS from browser/tablet.
Positions flow through the same Redis transit pipeline as GTFS-RT.
WoT 3+ required (or staff).
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
            heartbeat_alive=heartbeat_alive,
        )


# --- Helpers ---

def _check_wot(profile):
    """WoT 3+ or staff required."""
    if profile.account.is_staff:
        return
    if not profile.is_verified_wot:
        raise HttpError(403, "WoT 3+ verification required for Driver Mode")


def _is_heartbeat_alive(shift: DriverShift) -> bool:
    """Check if driver heartbeat key exists in Redis (TTL 45s)."""
    import redis as _redis
    from django.conf import settings
    try:
        r = _redis.Redis(
            host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
            port=getattr(settings, 'REDIS_PORT', 6379),
        )
        alive = bool(r.exists(f'driver:heartbeat:{shift.id}'))
        r.close()
        return alive
    except Exception:
        return False


# --- Endpoints ---

@router.post("/start/", response=ShiftOut, auth=ProfileAuth())
@ratelimit(group='driver:start', key=user_or_ip, rate='10/m', method='POST')
def start_shift(request, payload: ShiftStartIn):
    """Start a driver shift — begin GPS broadcasting on a route."""
    profile = request.auth_profile
    _check_wot(profile)

    route = get_object_or_404(
        Route.objects.select_related('agency__data_source', 'place'),
        id=payload.route_id,
    )

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
    import redis as _redis
    from django.conf import settings

    try:
        r = _redis.Redis(
            host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
            port=getattr(settings, 'REDIS_PORT', 6379),
            decode_responses=True,
        )
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
        r.close()
    except Exception as e:
        logger.warning(f"Failed to clean transit pipeline for shift {shift.id}: {e}")
