"""
Dispatch API: assign GPS tracker devices to transit routes.

Staff-only endpoints for fleet management.
Assigned devices inject positions into transit:geo pipeline,
making them visible to passengers as regular transit vehicles.
"""

import json
import logging
from datetime import date, datetime, timezone as dt_tz
from typing import List, Optional

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from iot.models import IoTDevice, VehicleAssignment
from iot.services import TraccarService, _get_tracker_redis
from geo.models import Route, TransitDataSource

logger = logging.getLogger(__name__)
router = Router(tags=["Dispatch"])


# --- Schemas ---

class AssignmentCreateIn(Schema):
    device_id: str
    route_id: str
    direction_id: int = 0
    date: date
    display_vehicle_id: str = ""
    notes: str = ""


class AssignmentUpdateIn(Schema):
    status: str
    notes: Optional[str] = None


class AssignmentOut(Schema):
    id: str
    object_type: str = "vehicle_assignment"
    device_id: str
    device_name: str
    route_id: str
    route_name: str
    route_color: str
    data_source_id: str
    direction_id: int
    date: date
    status: str
    display_vehicle_id: str
    notes: str
    created_at: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed: Optional[float] = None

    @classmethod
    def from_assignment(cls, a: VehicleAssignment, redis_pos: dict = None):
        data = {
            "id": str(a.id),
            "device_id": str(a.device_id),
            "device_name": a.device.name,
            "route_id": str(a.route_id),
            "route_name": a.route.short_name,
            "route_color": a.route.route_color or "",
            "data_source_id": str(a.data_source_id),
            "direction_id": a.direction_id,
            "date": a.date,
            "status": a.status,
            "display_vehicle_id": a.display_vehicle_id,
            "notes": a.notes,
            "created_at": a.created_at.isoformat(),
        }
        if redis_pos:
            data["latitude"] = redis_pos.get("lat")
            data["longitude"] = redis_pos.get("lon")
            data["speed"] = redis_pos.get("spd")
        return cls(**data)


class DispatchRouteOut(Schema):
    id: str
    short_name: str
    long_name: str
    route_color: str
    route_type: int
    active_count: int
    place_slug: str = ""


class AvailableDeviceOut(Schema):
    id: str
    name: str
    device_id: Optional[str]
    last_seen: Optional[str]
    has_position: bool = False


# --- Helpers ---

def _staff_check(request):
    if not request.user or not request.user.is_staff:
        raise HttpError(403, "Staff only")
    return request.auth_profile


# --- Endpoints ---

@router.post("/assignments/", response=AssignmentOut, auth=ProfileAuth())
@ratelimit(group='dispatch:create', key=user_or_ip, rate='30/m', method='POST')
def create_assignment(request, payload: AssignmentCreateIn):
    """Create a vehicle assignment (dispatch device to route)."""
    profile = _staff_check(request)

    device = get_object_or_404(IoTDevice, id=payload.device_id, device_type="TRACKER")
    route = get_object_or_404(Route, id=payload.route_id)
    data_source = route.agency.data_source

    # Check no active assignment for this device+date
    existing = VehicleAssignment.objects.filter(
        device=device,
        date=payload.date,
        status__in=["ASSIGNED", "ACTIVE"],
    ).exists()
    if existing:
        raise HttpError(409, "Device already assigned for this date")

    assignment = VehicleAssignment.objects.create(
        device=device,
        route=route,
        data_source=data_source,
        direction_id=payload.direction_id,
        date=payload.date,
        display_vehicle_id=payload.display_vehicle_id,
        notes=payload.notes,
        created_by=profile,
    )
    TraccarService.invalidate_assignment_cache(str(device.id))

    assignment = (
        VehicleAssignment.objects
        .select_related("device", "route")
        .get(id=assignment.id)
    )
    return AssignmentOut.from_assignment(assignment)


@router.get("/assignments/", response=List[AssignmentOut], auth=ProfileAuth())
@ratelimit(group='dispatch:list', key=user_or_ip, rate='60/m')
def list_assignments(request):
    """List today's assignments with live positions."""
    _staff_check(request)

    target_date = request.GET.get("date", str(timezone.localdate()))
    assignments = list(
        VehicleAssignment.objects
        .filter(date=target_date)
        .select_related("device", "route")
        .order_by("route__short_name", "direction_id")
    )

    # Batch read live positions from Redis
    device_ulids = [str(a.device_id) for a in assignments]
    positions = TraccarService.get_positions_from_redis(device_ulids) if device_ulids else {}

    return [
        AssignmentOut.from_assignment(a, positions.get(str(a.device_id)))
        for a in assignments
    ]


@router.get("/assignments/{assignment_id}/", response=AssignmentOut, auth=ProfileAuth())
@ratelimit(group='dispatch:detail', key=user_or_ip, rate='60/m')
def get_assignment(request, assignment_id: str):
    """Get single assignment detail."""
    _staff_check(request)

    a = get_object_or_404(
        VehicleAssignment.objects.select_related("device", "route"),
        id=assignment_id,
    )
    positions = TraccarService.get_positions_from_redis([str(a.device_id)])
    return AssignmentOut.from_assignment(a, positions.get(str(a.device_id)))


@router.patch("/assignments/{assignment_id}/", response=AssignmentOut, auth=ProfileAuth())
@ratelimit(group='dispatch:update', key=user_or_ip, rate='30/m', method='PATCH')
def update_assignment(request, assignment_id: str, payload: AssignmentUpdateIn):
    """Update assignment status (COMPLETED/CANCELLED)."""
    _staff_check(request)

    a = get_object_or_404(
        VehicleAssignment.objects.select_related("device", "route", "data_source"),
        id=assignment_id,
    )

    valid_statuses = ["ASSIGNED", "ACTIVE", "COMPLETED", "CANCELLED"]
    if payload.status not in valid_statuses:
        raise HttpError(400, f"Invalid status. Must be one of: {valid_statuses}")

    a.status = payload.status
    if payload.notes is not None:
        a.notes = payload.notes
    a.save(update_fields=["status", "notes", "updated_at"])

    # Clean transit pipeline on completion/cancellation
    if payload.status in ("COMPLETED", "CANCELLED"):
        vid = a.display_vehicle_id or f"D{str(a.device_id)[:8]}"
        ds_id = str(a.data_source_id)
        member = f"{ds_id}:{vid}"
        try:
            r = _get_tracker_redis()
            pipe = r.pipeline(transaction=False)
            pipe.zrem("transit:geo", member)
            pipe.hdel("transit:vdata", member)
            pipe.srem(f"transit:members:{ds_id}", member)
            pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to clean transit pipeline for {member}: {e}")

    TraccarService.invalidate_assignment_cache(str(a.device_id))
    return AssignmentOut.from_assignment(a)


@router.get("/routes/", response=List[DispatchRouteOut], auth=ProfileAuth())
@ratelimit(group='dispatch:routes', key=user_or_ip, rate='60/m')
def list_dispatch_routes(request):
    """List routes with active assignment counts for dispatch panel."""
    _staff_check(request)

    from django.db.models import Count, Q
    today = timezone.localdate()
    routes = (
        Route.objects
        .filter(
            vehicle_assignments__date=today,
            vehicle_assignments__status__in=["ASSIGNED", "ACTIVE"],
        )
        .annotate(
            active_count=Count(
                "vehicle_assignments",
                filter=Q(
                    vehicle_assignments__date=today,
                    vehicle_assignments__status__in=["ASSIGNED", "ACTIVE"],
                ),
            )
        )
        .select_related("place")
        .order_by("short_name")
        .distinct()
    )

    return [
        DispatchRouteOut(
            id=str(r.id),
            short_name=r.short_name,
            long_name=r.long_name,
            route_color=r.route_color or "",
            route_type=r.route_type,
            active_count=r.active_count,
            place_slug=r.place.slug if r.place else "",
        )
        for r in routes
    ]


@router.get("/devices/", response=List[AvailableDeviceOut], auth=ProfileAuth())
@ratelimit(group='dispatch:devices', key=user_or_ip, rate='60/m')
def list_available_devices(request):
    """List tracker devices available for assignment (not assigned today)."""
    _staff_check(request)

    today = timezone.localdate()
    assigned_device_ids = set(
        VehicleAssignment.objects
        .filter(date=today, status__in=["ASSIGNED", "ACTIVE"])
        .values_list("device_id", flat=True)
    )

    devices = IoTDevice.objects.filter(device_type="TRACKER").order_by("name")

    # Check which devices have live positions
    all_ids = [str(d.id) for d in devices]
    positions = TraccarService.get_positions_from_redis(all_ids) if all_ids else {}

    result = []
    for d in devices:
        did = str(d.id)
        if did in assigned_device_ids:
            continue
        # Derive last_seen from Redis if available, fallback to PG
        pos = positions.get(did)
        if pos and pos.get('t'):
            ls = datetime.fromtimestamp(pos['t'], tz=dt_tz.utc).isoformat()
        elif d.last_seen:
            ls = d.last_seen.isoformat()
        else:
            ls = None
        result.append(AvailableDeviceOut(
            id=did,
            name=d.name,
            device_id=d.device_id,
            last_seen=ls,
            has_position=did in positions,
        ))
    return result
