"""
Transit Management API: CRUD for agencies, routes, stops.

Allows transit companies to manage their operations via web UI.
Staff can manage any agency; agency owners can manage their own.
"""

import io
import csv
import json
import logging
import zipfile
import time as _time
from typing import List, Optional

import requests
from django.conf import settings
from django.contrib.gis.geos import Point, LineString
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from ninja import Router, Schema
from ninja.errors import HttpError

from parahub.auth import ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip
from core.models import generate_ulid
from geo.models import (
    Agency, Stop, Route, RouteStop, Shape, Trip, StopTime, CalendarDate,
    TransitDataSource, Place,
)

logger = logging.getLogger(__name__)
router = Router(tags=["Transit Manage"])

VALHALLA_URL = "http://127.0.0.1:8002"


# --- Permission helpers ---

def _check_agency_access(request, agency):
    """Check user is staff or agency owner."""
    if request.user.is_staff:
        return request.auth_profile
    profile = request.auth_profile
    if agency.owner_id and agency.owner_id == profile.id:
        return profile
    raise HttpError(403, "No access to this agency")


def _get_managed_agencies(request):
    """Get agencies accessible to current user."""
    if request.user.is_staff:
        return Agency.objects.filter(is_managed=True)
    profile = request.auth_profile
    return Agency.objects.filter(is_managed=True, owner=profile)


# --- Schemas ---

class AgencyCreateIn(Schema):
    name: str
    timezone: str = "Europe/Lisbon"
    lang: str = "pt"
    url: str = ""


class AgencyOut(Schema):
    id: str
    object_type: str = "agency"
    name: str
    timezone: str
    lang: str
    url: str
    data_source_id: str = ""
    data_source_slug: str = ""
    is_managed: bool = True
    routes_count: int = 0
    stops_count: int = 0


class StopCreateIn(Schema):
    agency_id: str
    name: str
    lat: float
    lon: float


class StopUpdateIn(Schema):
    name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class StopOut(Schema):
    id: str
    object_type: str = "stop"
    source_id: str
    name: str
    lat: float
    lon: float
    agency_id: str


class RouteCreateIn(Schema):
    agency_id: str
    short_name: str
    long_name: str = ""
    route_type: int = 3  # bus
    route_color: str = "3b82f6"
    description: str = ""


class RouteUpdateIn(Schema):
    short_name: Optional[str] = None
    long_name: Optional[str] = None
    route_type: Optional[int] = None
    route_color: Optional[str] = None
    description: Optional[str] = None


class RouteStopIn(Schema):
    stop_id: str
    sequence: int


class RouteStopsUpdateIn(Schema):
    direction_id: int = 0
    stops: List[RouteStopIn]


class RouteStopOut(Schema):
    stop_id: str
    stop_name: str
    lat: float
    lon: float
    sequence: int


class RouteDetailOut(Schema):
    id: str
    object_type: str = "route"
    source_id: str
    short_name: str
    long_name: str
    route_type: int
    route_color: str
    description: str
    agency_id: str
    agency_name: str = ""
    stops_outbound: List[RouteStopOut] = []
    stops_inbound: List[RouteStopOut] = []
    has_shape: bool = False


class ShapePreviewIn(Schema):
    stops: List[dict]  # [{"lat": ..., "lon": ...}, ...]
    costing: str = "bus"


# --- Agency Endpoints ---

@router.post("/agencies/", response=AgencyOut, auth=ProfileAuth())
@ratelimit(group='transit_manage:create_agency', key=user_or_ip, rate='10/m', method='POST')
def create_agency(request, payload: AgencyCreateIn):
    """Create a managed transit agency."""
    profile = request.auth_profile
    if not request.user.is_staff:
        # Non-staff can create their own agencies
        existing = Agency.objects.filter(owner=profile, is_managed=True).count()
        if existing >= 3:
            raise HttpError(400, "Maximum 3 agencies per user")

    slug = slugify(payload.name)[:50] or "agency"
    # Ensure unique slug
    base_slug = slug
    n = 1
    while TransitDataSource.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{n}"
        n += 1

    with transaction.atomic():
        ds = TransitDataSource.objects.create(
            name=f"{payload.name}",
            format="managed",
            is_active=True,
            slug=slug,
        )
        agency = Agency.objects.create(
            data_source=ds,
            owner=profile,
            is_managed=True,
            source_id=str(ds.id)[:8],
            name=payload.name,
            url=payload.url,
            timezone=payload.timezone,
            lang=payload.lang,
        )

    return _agency_to_out(agency)


@router.get("/agencies/", response=List[AgencyOut], auth=ProfileAuth())
@ratelimit(group='transit_manage:list_agencies', key=user_or_ip, rate='60/m')
def list_agencies(request):
    """List managed agencies accessible to current user."""
    agencies = _get_managed_agencies(request).select_related("data_source").annotate(
        routes_count=Count("routes"),
        stops_count=Count("stops"),
    )
    return [_agency_to_out(a) for a in agencies]


@router.patch("/agencies/{agency_id}/", response=AgencyOut, auth=ProfileAuth())
@ratelimit(group='transit_manage:update_agency', key=user_or_ip, rate='30/m', method='PATCH')
def update_agency(request, agency_id: str, payload: AgencyCreateIn):
    """Update managed agency."""
    agency = get_object_or_404(Agency, id=agency_id, is_managed=True)
    _check_agency_access(request, agency)

    agency.name = payload.name
    agency.timezone = payload.timezone
    agency.lang = payload.lang
    agency.url = payload.url
    agency.save(update_fields=["name", "timezone", "lang", "url", "updated_at"])

    if agency.data_source:
        agency.data_source.name = payload.name
        agency.data_source.save(update_fields=["name"])

    return _agency_to_out(agency)


def _agency_to_out(agency):
    rc = getattr(agency, "routes_count", None)
    sc = getattr(agency, "stops_count", None)
    if rc is None:
        rc = agency.routes.count()
    if sc is None:
        sc = agency.stops.count()
    return AgencyOut(
        id=str(agency.id),
        name=agency.name,
        timezone=agency.timezone,
        lang=agency.lang,
        url=agency.url,
        data_source_id=str(agency.data_source_id) if agency.data_source_id else "",
        data_source_slug=agency.data_source.slug if agency.data_source else "",
        is_managed=agency.is_managed,
        routes_count=rc,
        stops_count=sc,
    )


# --- Stop Endpoints ---

@router.post("/stops/", response=StopOut, auth=ProfileAuth())
@ratelimit(group='transit_manage:create_stop', key=user_or_ip, rate='60/m', method='POST')
def create_stop(request, payload: StopCreateIn):
    """Create a stop for a managed agency."""
    agency = get_object_or_404(Agency, id=payload.agency_id, is_managed=True)
    _check_agency_access(request, agency)

    location = Point(payload.lon, payload.lat, srid=4326)

    # Auto-assign place via spatial lookup
    place = _find_place(location)

    sid = f"M{generate_ulid()}"
    base_slug = slugify(payload.name)[:90]
    slug = f"{base_slug}-{sid[-6:].lower()}" if base_slug else sid[-8:].lower()

    stop = Stop.objects.create(
        agency=agency,
        place=place,
        source_id=sid,
        slug=slug,
        name=payload.name,
        location=location,
        location_type=0,
    )

    return _stop_to_out(stop)


@router.get("/stops/", response=List[StopOut], auth=ProfileAuth())
@ratelimit(group='transit_manage:list_stops', key=user_or_ip, rate='60/m')
def list_stops(request, agency_id: str, q: str = "", limit: int = 100):
    """List stops for a managed agency."""
    agency = get_object_or_404(Agency, id=agency_id, is_managed=True)
    _check_agency_access(request, agency)

    qs = agency.stops.all()
    if q:
        qs = qs.filter(name__icontains=q)
    return [_stop_to_out(s) for s in qs[:limit]]


@router.get("/stops/nearby/", response=List[StopOut], auth=ProfileAuth())
@ratelimit(group='transit_manage:nearby_stops', key=user_or_ip, rate='60/m')
def nearby_stops(request, lat: float, lon: float, radius: int = 500, agency_id: str = ""):
    """Find stops near a point (any agency). Radius in meters."""
    from django.contrib.gis.db.models.functions import Distance

    pt = Point(lon, lat, srid=4326)
    qs = Stop.objects.filter(
        location__dwithin=(pt, radius / 111320.0)  # rough degrees
    ).annotate(
        dist=Distance("location", pt)
    ).order_by("dist")[:50]

    return [_stop_to_out(s) for s in qs]


@router.patch("/stops/{stop_id}/", response=StopOut, auth=ProfileAuth())
@ratelimit(group='transit_manage:update_stop', key=user_or_ip, rate='60/m', method='PATCH')
def update_stop(request, stop_id: str, payload: StopUpdateIn):
    """Update a managed stop."""
    stop = get_object_or_404(Stop.objects.select_related("agency"), id=stop_id)
    if not stop.agency.is_managed:
        raise HttpError(403, "Cannot edit GTFS-imported stops")
    _check_agency_access(request, stop.agency)

    if payload.name is not None:
        stop.name = payload.name
        base_slug = slugify(payload.name)[:90]
        stop.slug = f"{base_slug}-{stop.source_id[-6:].lower()}" if base_slug else stop.source_id[-8:].lower()
    if payload.lat is not None and payload.lon is not None:
        stop.location = Point(payload.lon, payload.lat, srid=4326)
        stop.place = _find_place(stop.location)
    stop.save()

    return _stop_to_out(stop)


@router.delete("/stops/{stop_id}/", auth=ProfileAuth())
@ratelimit(group='transit_manage:delete_stop', key=user_or_ip, rate='30/m', method='DELETE')
def delete_stop(request, stop_id: str):
    """Delete a managed stop (only if not used in routes)."""
    stop = get_object_or_404(Stop.objects.select_related("agency"), id=stop_id)
    if not stop.agency.is_managed:
        raise HttpError(403, "Cannot delete GTFS-imported stops")
    _check_agency_access(request, stop.agency)

    if RouteStop.objects.filter(stop=stop).exists():
        raise HttpError(409, "Stop is used in routes — remove from routes first")

    stop.delete()
    return {"ok": True}


def _stop_to_out(stop):
    return StopOut(
        id=str(stop.id),
        source_id=stop.source_id,
        name=stop.name,
        lat=stop.location.y,
        lon=stop.location.x,
        agency_id=str(stop.agency_id),
    )


def _find_place(location):
    """Spatial lookup: find smallest Place containing this point."""
    places = Place.objects.filter(
        geometry__contains=location
    ).order_by("place_type")  # city < region < country
    # Prefer city over region
    for p in places:
        if p.place_type == "city":
            return p
    return places.first()


# --- Route Endpoints ---

@router.post("/routes/", response=RouteDetailOut, auth=ProfileAuth())
@ratelimit(group='transit_manage:create_route', key=user_or_ip, rate='30/m', method='POST')
def create_route(request, payload: RouteCreateIn):
    """Create a route for a managed agency."""
    agency = get_object_or_404(Agency, id=payload.agency_id, is_managed=True)
    _check_agency_access(request, agency)

    rsid = f"M{generate_ulid()}"
    rslug = slugify(payload.short_name)[:40]
    rslug = f"{rslug}-{rsid[-6:].lower()}" if rslug else rsid[-8:].lower()

    route = Route.objects.create(
        agency=agency,
        source_id=rsid,
        slug=rslug,
        short_name=payload.short_name,
        long_name=payload.long_name,
        route_type=payload.route_type,
        route_color=payload.route_color.lstrip("#")[:6],
        description=payload.description,
    )

    return _route_detail(route)


@router.get("/routes/", response=List[RouteDetailOut], auth=ProfileAuth())
@ratelimit(group='transit_manage:list_routes', key=user_or_ip, rate='60/m')
def list_routes(request, agency_id: str):
    """List routes for a managed agency."""
    agency = get_object_or_404(Agency, id=agency_id, is_managed=True)
    _check_agency_access(request, agency)

    routes = agency.routes.all().order_by("short_name")
    return [_route_detail(r) for r in routes]


@router.get("/routes/{route_id}/", response=RouteDetailOut, auth=ProfileAuth())
@ratelimit(group='transit_manage:get_route', key=user_or_ip, rate='60/m')
def get_route(request, route_id: str):
    """Get route detail with stops."""
    route = get_object_or_404(Route.objects.select_related("agency"), id=route_id)
    if route.agency.is_managed:
        _check_agency_access(request, route.agency)
    return _route_detail(route)


@router.patch("/routes/{route_id}/", response=RouteDetailOut, auth=ProfileAuth())
@ratelimit(group='transit_manage:update_route', key=user_or_ip, rate='30/m', method='PATCH')
def update_route(request, route_id: str, payload: RouteUpdateIn):
    """Update route metadata."""
    route = get_object_or_404(Route.objects.select_related("agency"), id=route_id)
    if not route.agency.is_managed:
        raise HttpError(403, "Cannot edit GTFS-imported routes")
    _check_agency_access(request, route.agency)

    if payload.short_name is not None:
        route.short_name = payload.short_name
        rslug = slugify(payload.short_name)[:40]
        route.slug = f"{rslug}-{route.source_id[-6:].lower()}" if rslug else route.source_id[-8:].lower()
    if payload.long_name is not None:
        route.long_name = payload.long_name
    if payload.route_type is not None:
        route.route_type = payload.route_type
    if payload.route_color is not None:
        route.route_color = payload.route_color.lstrip("#")[:6]
    if payload.description is not None:
        route.description = payload.description
    route.save()

    return _route_detail(route)


@router.put("/routes/{route_id}/stops/", response=RouteDetailOut, auth=ProfileAuth())
@ratelimit(group='transit_manage:update_route_stops', key=user_or_ip, rate='30/m', method='PUT')
def update_route_stops(request, route_id: str, payload: RouteStopsUpdateIn):
    """Replace stop sequence for a direction. Auto-generates shape via Valhalla."""
    route = get_object_or_404(Route.objects.select_related("agency"), id=route_id)
    if not route.agency.is_managed:
        raise HttpError(403, "Cannot edit GTFS-imported routes")
    _check_agency_access(request, route.agency)

    stop_ids = [s.stop_id for s in payload.stops]
    stops_map = {str(s.id): s for s in Stop.objects.filter(id__in=stop_ids)}

    if len(stops_map) != len(stop_ids):
        raise HttpError(400, "Some stop IDs not found")

    dir_id = payload.direction_id

    with transaction.atomic():
        # Remove old stops for this direction
        RouteStop.objects.filter(route=route, direction_id=dir_id).delete()

        # Create new sequence
        for item in payload.stops:
            RouteStop.objects.create(
                route=route,
                stop=stops_map[item.stop_id],
                sequence=item.sequence,
                direction_id=dir_id,
            )

        # Generate shape via Valhalla
        ordered_stops = [stops_map[s.stop_id] for s in sorted(payload.stops, key=lambda x: x.sequence)]
        shape_geom = _generate_shape(ordered_stops, route.route_type)

        # Create/update Shape for this direction
        shape_obj = None
        if shape_geom:
            shape_source_id = f"{route.source_id}_d{dir_id}"
            from django.db import connection
            shape_obj, _ = Shape.objects.update_or_create(
                agency=route.agency,
                source_id=shape_source_id,
                defaults={"geometry": shape_geom, "length_m": 0},
            )
            # Compute accurate length via DB
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE geo_shape SET length_m = ST_Length(geometry::geography) WHERE id = %s",
                    [shape_obj.id],
                )

        # Create/update Trip with shape_ref for this direction
        trip, _ = Trip.objects.update_or_create(
            route=route,
            direction_id=dir_id,
            defaults={
                "source_id": f"{route.source_id}_d{dir_id}",
                "headsign": route.long_name or route.short_name,
                "service_id": f"managed_{route.agency_id}",
                "shape_ref": shape_obj,
            },
        )

        # Update route geometry (use outbound shape by default)
        if dir_id == 0 and shape_geom:
            route.geometry = shape_geom
            route.save(update_fields=["geometry", "updated_at"])

        # Assign place from stops
        _assign_route_place(route)

    # Invalidate snap cache
    from iot.services import TraccarService
    TraccarService._stop_seqs_ts = 0

    return _route_detail(route)


@router.delete("/routes/{route_id}/", auth=ProfileAuth())
@ratelimit(group='transit_manage:delete_route', key=user_or_ip, rate='30/m', method='DELETE')
def delete_route(request, route_id: str):
    """Delete a managed route."""
    route = get_object_or_404(Route.objects.select_related("agency"), id=route_id)
    if not route.agency.is_managed:
        raise HttpError(403, "Cannot delete GTFS-imported routes")
    _check_agency_access(request, route.agency)

    route.delete()
    return {"ok": True}


# --- Shape Generation ---

@router.post("/routes/preview-shape/", auth=ProfileAuth())
@ratelimit(group='transit_manage:preview_shape', key=user_or_ip, rate='30/m', method='POST')
def preview_shape(request, payload: ShapePreviewIn):
    """Preview route shape: stops → Valhalla → GeoJSON LineString."""
    if len(payload.stops) < 2:
        raise HttpError(400, "At least 2 stops required")

    locations = [{"lat": s["lat"], "lon": s["lon"]} for s in payload.stops]
    costing = payload.costing if payload.costing in ("bus", "auto", "bicycle") else "bus"

    try:
        resp = requests.post(f"{VALHALLA_URL}/route", json={
            "locations": locations,
            "costing": costing,
            "directions_options": {"units": "km"},
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"Valhalla route failed: {e}")
        # Fallback: straight line through stops
        coords = [[s["lon"], s["lat"]] for s in payload.stops]
        return {"type": "LineString", "coordinates": coords, "fallback": True}

    # Decode Valhalla shape (encoded polyline with 6-decimal precision)
    shape_points = _decode_polyline(data["trip"]["legs"][0]["shape"])
    coords = [[lon, lat] for lat, lon in shape_points]

    return {"type": "LineString", "coordinates": coords}


def _generate_shape(stops, route_type=3):
    """Generate LineString shape from ordered stops via Valhalla bus routing."""
    if len(stops) < 2:
        return None

    locations = [{"lat": s.location.y, "lon": s.location.x} for s in stops]
    costing = "bus" if route_type == 3 else "auto"

    try:
        resp = requests.post(f"{VALHALLA_URL}/route", json={
            "locations": locations,
            "costing": costing,
            "directions_options": {"units": "km"},
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"Valhalla shape generation failed: {e}, using straight line")
        coords = [(s.location.x, s.location.y) for s in stops]
        return LineString(coords, srid=4326) if len(coords) >= 2 else None

    shape_points = _decode_polyline(data["trip"]["legs"][0]["shape"])
    coords = [(lon, lat) for lat, lon in shape_points]
    return LineString(coords, srid=4326) if len(coords) >= 2 else None


def _decode_polyline(encoded, precision=6):
    """Decode Valhalla encoded polyline (precision 6)."""
    inv = 10 ** -precision
    result = []
    lat = lon = 0
    i = 0
    while i < len(encoded):
        for coord in range(2):
            shift = 0
            value = 0
            while True:
                c = ord(encoded[i]) - 63
                i += 1
                value |= (c & 0x1F) << shift
                shift += 5
                if c < 0x20:
                    break
            if value & 1:
                value = ~value
            value >>= 1
            if coord == 0:
                lat += value
            else:
                lon += value
        result.append((lat * inv, lon * inv))
    return result


def _assign_route_place(route):
    """Assign route.place from majority stop place."""
    place_ids = list(
        RouteStop.objects.filter(route=route)
        .exclude(stop__place__isnull=True)
        .values_list("stop__place", flat=True)
    )
    if not place_ids:
        return

    from collections import Counter
    most_common = Counter(place_ids).most_common(1)[0][0]
    route.place_id = most_common
    route.save(update_fields=["place_id", "updated_at"])

    # M2M places
    unique_places = set(place_ids)
    route.places.set(unique_places)


def _route_detail(route):
    """Build RouteDetailOut with stop sequences."""
    stops_out = RouteStop.objects.filter(route=route).select_related("stop").order_by("sequence")

    outbound = []
    inbound = []
    for rs in stops_out:
        item = RouteStopOut(
            stop_id=str(rs.stop_id),
            stop_name=rs.stop.name,
            lat=rs.stop.location.y,
            lon=rs.stop.location.x,
            sequence=rs.sequence,
        )
        if rs.direction_id == 1:
            inbound.append(item)
        else:
            outbound.append(item)

    has_shape = Trip.objects.filter(route=route).exclude(shape_ref__isnull=True).exists()

    return RouteDetailOut(
        id=str(route.id),
        source_id=route.source_id,
        short_name=route.short_name,
        long_name=route.long_name,
        route_type=route.route_type,
        route_color=route.route_color or "3b82f6",
        description=route.description,
        agency_id=str(route.agency_id),
        agency_name=route.agency.name if hasattr(route, "agency") and route.agency else "",
        stops_outbound=outbound,
        stops_inbound=inbound,
        has_shape=has_shape,
    )


# --- GTFS Static Export ---

@router.get("/gtfs/export/{agency_id}/", auth=None)
@ratelimit(group='transit:gtfs_export', key='ip', rate='10/m')
def gtfs_export(request, agency_id: str):
    """Generate and serve GTFS ZIP for a managed agency."""
    agency = get_object_or_404(Agency, id=agency_id, is_managed=True)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # agency.txt
        zf.writestr("agency.txt", _gtfs_csv([
            ["agency_id", "agency_name", "agency_url", "agency_timezone", "agency_lang"],
            [agency.source_id, agency.name, agency.url or "https://parahub.io", agency.timezone, agency.lang],
        ]))

        # stops.txt
        stops = list(agency.stops.all())
        rows = [["stop_id", "stop_name", "stop_lat", "stop_lon", "location_type"]]
        for s in stops:
            rows.append([s.source_id, s.name, f"{s.location.y:.6f}", f"{s.location.x:.6f}", str(s.location_type)])
        zf.writestr("stops.txt", _gtfs_csv(rows))

        # routes.txt
        routes = list(agency.routes.all())
        rows = [["route_id", "agency_id", "route_short_name", "route_long_name", "route_type", "route_color", "route_text_color"]]
        for r in routes:
            rows.append([r.source_id, agency.source_id, r.short_name, r.long_name, str(r.route_type), r.route_color, r.route_text_color])
        zf.writestr("routes.txt", _gtfs_csv(rows))

        # trips.txt + shapes.txt
        trips = list(Trip.objects.filter(route__agency=agency).select_related("route", "shape_ref"))
        trip_rows = [["trip_id", "route_id", "service_id", "trip_headsign", "direction_id", "shape_id"]]
        shape_rows = [["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"]]
        exported_shapes = set()  # track already-exported shape IDs

        for t in trips:
            shape_id = ""
            if t.shape_ref and t.shape_ref.geometry and len(t.shape_ref.geometry.coords) >= 2:
                shape_id = t.shape_ref.source_id or f"shape_{t.source_id}"
                if shape_id not in exported_shapes:
                    exported_shapes.add(shape_id)
                    for seq, (lon, lat) in enumerate(t.shape_ref.geometry.coords):
                        shape_rows.append([shape_id, f"{lat:.6f}", f"{lon:.6f}", str(seq)])

            trip_rows.append([
                t.source_id,
                t.route.source_id,
                t.service_id,
                t.headsign,
                str(t.direction_id or 0),
                shape_id,
            ])
        zf.writestr("trips.txt", _gtfs_csv(trip_rows))
        if len(shape_rows) > 1:
            zf.writestr("shapes.txt", _gtfs_csv(shape_rows))

        # calendar.txt (required by GTFS spec)
        service_ids = sorted(set(t.service_id for t in trips if t.service_id))
        if service_ids:
            from datetime import date, timedelta
            today = date.today()
            end_date = today + timedelta(days=365)
            cal_rows = [["service_id", "monday", "tuesday", "wednesday", "thursday",
                         "friday", "saturday", "sunday", "start_date", "end_date"]]
            for sid in service_ids:
                cal_rows.append([sid, "1", "1", "1", "1", "1", "1", "1",
                                 today.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")])
            zf.writestr("calendar.txt", _gtfs_csv(cal_rows))

        # calendar_dates.txt (if any exceptions exist)
        cal_dates = list(CalendarDate.objects.filter(agency=agency).order_by("date"))
        if cal_dates:
            cd_rows = [["service_id", "date", "exception_type"]]
            for cd in cal_dates:
                cd_rows.append([cd.service_id, cd.date.strftime("%Y%m%d"), str(cd.exception_type)])
            zf.writestr("calendar_dates.txt", _gtfs_csv(cd_rows))

        # stop_times.txt (required by GTFS spec)
        stop_times = list(
            StopTime.objects.filter(trip__route__agency=agency)
            .select_related("stop", "trip")
            .order_by("trip_id", "stop_sequence")
        )
        if stop_times:
            rows = [["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]]
            for st in stop_times:
                rows.append([
                    st.trip.source_id,
                    st.arrival_time.strftime("%H:%M:%S"),
                    st.departure_time.strftime("%H:%M:%S"),
                    st.stop.source_id,
                    str(st.stop_sequence),
                ])
            zf.writestr("stop_times.txt", _gtfs_csv(rows))
        else:
            # Generate synthetic stop_times from RouteStops (managed agencies without schedules)
            rows = [["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]]
            for t in trips:
                route_stops = list(
                    RouteStop.objects.filter(route=t.route, direction_id=t.direction_id)
                    .select_related("stop").order_by("sequence")
                )
                if not route_stops:
                    route_stops = list(
                        RouteStop.objects.filter(route=t.route)
                        .select_related("stop").order_by("sequence")
                    )
                for i, rs in enumerate(route_stops):
                    minutes = 360 + i * 2  # Start 06:00, 2-min intervals
                    h, m = divmod(minutes, 60)
                    time_str = f"{h:02d}:{m:02d}:00"
                    rows.append([t.source_id, time_str, time_str, rs.stop.source_id, str(i)])
            zf.writestr("stop_times.txt", _gtfs_csv(rows))

    buf.seek(0)
    slug = agency.data_source.slug if agency.data_source else slugify(agency.name)
    response = HttpResponse(buf.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{slug}.gtfs.zip"'
    return response


def _gtfs_csv(rows):
    """Write rows as CSV string."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerows(rows)
    return out.getvalue()
