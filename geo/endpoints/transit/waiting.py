"""
Waiting-passenger markers — write path.

The read path is the transit WebSocket (`waiting` inside `route_vehicles` and
`stop_live`); this router only places, refreshes and clears a marker. It is
deliberately open to anonymous visitors: most stop-page traffic is signed out,
and that is exactly the person standing at the pole. Lifetime, identity and the
anti-abuse model live in `parahub.services.transit_waiting`.
"""

import logging
from typing import List, Optional

from django.db.models import Count, F
from ninja import Schema
from ninja.errors import HttpError

from geo.models import RouteStop, Stop
from parahub.auth import optional_profile_auth
from parahub.ratelimit import get_ip, ratelimit, user_or_ip
from parahub.services.transit_waiting import WaitingService, identity_for, normalize_lines

from .base import router
from .helpers import _grouped_pole_members

logger = logging.getLogger(__name__)


class WaitingLine(Schema):
    route: str
    direction: int = 0


class WaitingSetIn(Schema):
    ds_id: str
    stop_source_id: str
    lines: List[WaitingLine]
    device_id: Optional[str] = None


class WaitingIdentityIn(Schema):
    device_id: Optional[str] = None


class WaitingMarkerOut(Schema):
    ds_id: str
    stop_source_id: str
    lines: List[WaitingLine]
    declared_at: float
    beat: float


class WaitingStateOut(Schema):
    marker: Optional[WaitingMarkerOut] = None
    waiting: List[dict] = []


def _identity(request, device_id):
    """Profile when signed in, hashed device id otherwise."""
    profile = getattr(request, 'auth_profile', None)
    identity = identity_for(str(profile.id) if profile else None, device_id)
    if not identity:
        raise HttpError(400, 'device_id required when signed out')
    return identity


def _marker_out(marker):
    if not marker:
        return None
    return {
        'ds_id': marker['ds_id'],
        'stop_source_id': marker['stop_source_id'],
        'lines': [{'route': route, 'direction': direction} for route, direction in marker['lines']],
        'declared_at': marker['declared_at'],
        'beat': marker['beat'],
    }


def _resolve_placements(stop, lines):
    """Pin every requested line to the co-located pole that actually serves it.

    Two operators sharing one physical pole each ship their own `Stop` row, and a
    route page only ever looks up its own feed's stop ids — so a marker filed
    under the page's stop would be invisible on half the lines the page lists.
    Lines that no co-located pole serves in the requested direction are dropped:
    this is the only write path into the municipal history, so nothing
    unverifiable gets in.

    Returns `(placements, pole_coords)`; the coords feed the map's GEO index.
    """
    colocated, _siblings = _grouped_pole_members(stop)
    serving, coords = {}, {}
    for pole in colocated:
        ds_id = str(pole.agency.data_source_id) if pole.agency and pole.agency.data_source_id else ''
        if not ds_id or (ds_id, pole.source_id) in coords:
            continue
        coords[(ds_id, pole.source_id)] = (pole.location.y, pole.location.x)
        # Pooled by (ds, source_id), NOT `stop=pole`: a feed can ship the same
        # source_id as several Stop rows (17k+ pairs network-wide) with the
        # RouteStop links hanging off a row that is not in this cluster — and
        # (ds, source_id) is the unit every Redis key downstream is derived from.
        pairs = RouteStop.objects.filter(
            stop__source_id=pole.source_id,
            stop__agency__data_source_id=ds_id,
        ).values_list('route__source_id', 'direction_id')
        for route_source_id, direction in pairs:
            key = (route_source_id, direction if direction is not None else 0)
            serving.setdefault(key, (ds_id, pole.source_id))

    placements = []
    used_poles = set()
    for route, direction in lines:
        pole = serving.get((route, direction))
        if pole:
            placements.append((pole[0], pole[1], route, direction))
            used_poles.add(pole)
    return placements, {k: v for k, v in coords.items() if k in used_poles}


@router.post("/transit/waiting/", response=WaitingStateOut, auth=optional_profile_auth)
@ratelimit(group='transit:waiting:set', key=user_or_ip, rate='30/m')
def set_waiting(request, data: WaitingSetIn):
    """Place or move this identity's single waiting marker."""
    identity = _identity(request, data.device_id)
    lines = normalize_lines([{'route': line.route, 'direction': line.direction} for line in data.lines])
    if not lines:
        raise HttpError(400, 'at least one line required')

    # Several Stop rows can carry this (ds, source_id); a bare .first() is
    # arbitrary and can land on an ungrouped, route-less duplicate whose cluster
    # is just itself. Prefer a grouped row (brings the co-located cross-operator
    # poles), then the one with route links — deterministic either way.
    stop = (Stop.objects.select_related('agency', 'group')
            .filter(source_id=data.stop_source_id, agency__data_source_id=data.ds_id)
            .annotate(n_routes=Count('route_stops'))
            .order_by(F('group').desc(nulls_last=True), '-n_routes', 'id')
            .first())
    if not stop:
        raise HttpError(404, 'stop not found')

    placements, pole_coords = _resolve_placements(stop, lines)
    if not placements:
        raise HttpError(400, 'no requested line serves this stop in that direction')

    result = WaitingService.set_marker(
        identity, data.ds_id, data.stop_source_id, placements,
        ip=get_ip(request), pole_coords=pole_coords,
    )
    if not result['ok']:
        # `detail` is a machine code the client maps to its own i18n message —
        # never prose, which would turn error wording into a wire protocol.
        # Moving is never refused here; the only 429 the service raises is the
        # per-address anonymous cap, and "too fast" comes from @ratelimit above.
        if result['error'] == 'ip_cap':
            raise HttpError(429, 'ip_cap')
        raise HttpError(400, 'invalid')

    return {
        'marker': _marker_out(result['marker']),
        'waiting': WaitingService.stop_counts(data.ds_id, data.stop_source_id),
    }


@router.post("/transit/waiting/beat/", auth=optional_profile_auth)
@ratelimit(group='transit:waiting:beat', key=user_or_ip, rate='120/m')
def beat_waiting(request, data: WaitingIdentityIn):
    """Heartbeat from a visible page: re-arm the lease.

    `alive: false` means the marker is gone (lease ran out, or the awaited bus
    arrived and the server dropped it) — the client clears its own state on that
    answer instead of polling for it.
    """
    identity = _identity(request, data.device_id)
    return {'alive': WaitingService.heartbeat(identity)}


@router.post("/transit/waiting/clear/", auth=optional_profile_auth)
@ratelimit(group='transit:waiting:clear', key=user_or_ip, rate='60/m')
def clear_waiting(request, data: WaitingIdentityIn):
    """Remove the marker — an explicit "I am no longer waiting" tap.

    Closing the page deliberately does NOT come through here: the lease already
    retires an abandoned marker, and a reload would otherwise wipe the marker of
    somebody who is still standing at the pole. POST rather than DELETE because
    the identity travels in the body, like every other call in this router.
    """
    identity = _identity(request, data.device_id)
    return {'cleared': WaitingService.clear_marker(identity)}


@router.post("/transit/waiting/mine/", response=WaitingStateOut, auth=optional_profile_auth)
@ratelimit(group='transit:waiting:mine', key=user_or_ip, rate='60/m')
def my_waiting(request, data: WaitingIdentityIn):
    """Restore the marker after a reload so the page reopens in the right state.

    POST, not GET: the device id travels in the body like everywhere else in
    this router — a query parameter would land the raw id in access logs, which
    is exactly what hashing it server-side is meant to avoid.
    """
    identity = identity_for(
        str(getattr(request, 'auth_profile').id) if getattr(request, 'auth_profile', None) else None,
        data.device_id,
    )
    marker = WaitingService.get_marker(identity) if identity else None
    return {
        'marker': _marker_out(marker),
        'waiting': (
            WaitingService.stop_counts(marker['ds_id'], marker['stop_source_id'])
            if marker else []
        ),
    }
