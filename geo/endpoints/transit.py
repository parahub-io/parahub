"""
Transit (GTFS) endpoints — agencies, routes, stops, schedules, vehicles.
"""

from ninja import Router
from ninja.errors import HttpError
from typing import Dict, Optional, List
from pydantic import BaseModel
import json
import random
import logging
import orjson
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.shortcuts import get_object_or_404
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db.models import Count, Max, Min, Q
from django.http import HttpResponse
from datetime import datetime

from geo.models import (
    Agency, Stop, Route, RouteStop, StopTime, CalendarDate,
    TransitDataSource, Place, Trip, VehiclePositionHistory,
)

from parahub.ratelimit import ratelimit

logger = logging.getLogger(__name__)

router = Router(tags=["Geo / Transit"])


# ===== Helpers =====

def _place_stop_filter(place):
    """Return a Q filter for stops within a Place (uses cached FK)."""
    return Q(place=place)


def _place_route_filter(place):
    """Return a Q filter for routes within a Place (uses cached FK)."""
    return Q(place=place)


def _routes_for_stop(stop, limit=10):
    """Return list of {short_name, route_color, route_type} for a stop, deduplicated by short_name."""
    rs_qs = (
        RouteStop.objects.filter(stop=stop)
        .select_related("route")
        .order_by("route__short_name", "route__source_id")
    )
    seen = set()
    result = []
    for rs in rs_qs:
        r = rs.route
        if r.short_name not in seen:
            seen.add(r.short_name)
            result.append({
                "short_name": r.short_name,
                "route_color": r.route_color,
                "route_type": r.route_type,
            })
            if len(result) >= limit:
                break
    return result


def _build_route_detail(route):
    """Build TransitRouteDetail from a Route instance (shared by ULID and slug endpoints)."""

    def _stop_list(direction_id):
        qs = (
            RouteStop.objects.filter(route=route, direction_id=direction_id)
            .select_related("stop", "stop__place")
            .order_by("sequence")
        )
        return [
            {
                "id": rs.stop.id,
                "source_id": rs.stop.source_id,
                "slug": rs.stop.slug,
                "place_slug": rs.stop.place.slug if rs.stop.place else "",
                "name": rs.stop.name,
                "lat": rs.stop.location.y,
                "lon": rs.stop.location.x,
                "sequence": rs.sequence,
            }
            for rs in qs
        ]

    directions = []
    for d_id in [0, 1]:
        trip = Trip.objects.filter(route=route, direction_id=d_id).first()
        if trip:
            directions.append({"direction_id": d_id, "headsign": trip.headsign})

    geojson = None
    if route.geometry:
        geojson = {
            "type": "LineString",
            "coordinates": list(route.geometry.coords),
        }

    stops_dir0 = _stop_list(0)
    # Fallback: legacy data imported before direction support
    if not stops_dir0:
        stops_dir0 = _stop_list(None)

    # M2M places this route passes through
    route_places = [
        TransitRoutePlaceItem(name=p.name, slug=p.slug, country_code=p.country_code)
        for p in route.places.all().order_by("name")
    ]

    return TransitRouteDetail(
        id=route.id,
        source_id=route.source_id,
        data_source_id=str(route.agency.data_source_id) if route.agency and route.agency.data_source_id else "",
        slug=route.slug,
        place_slug=route.place.slug if route.place else "",
        short_name=route.short_name,
        long_name=route.long_name,
        description=route.description,
        route_type=route.route_type,
        route_color=route.route_color,
        route_text_color=route.route_text_color,
        agency_id=str(route.agency_id),
        agency_name=route.agency.name if route.agency else "",
        stops=stops_dir0,
        stops_dir1=_stop_list(1),
        directions=directions,
        places=route_places,
        geometry=geojson,
    )


def _build_stop_detail(stop):
    """Build TransitStopResponse from a Stop instance (shared by ULID and slug endpoints)."""
    routes = (
        RouteStop.objects.filter(stop=stop)
        .select_related("route", "route__place")
        .order_by("route__short_name", "route__source_id")
    )
    # Deduplicate by short_name: GTFS variants (2110_0/1/2) share the same display name
    # Secondary sort by source_id ensures _0 (main path) is always picked first
    seen = set()
    unique_routes = []
    for rs in routes:
        if rs.route.short_name not in seen:
            seen.add(rs.route.short_name)
            unique_routes.append(rs)
    return TransitStopResponse(
        id=stop.id,
        slug=stop.slug,
        place_slug=stop.place.slug if stop.place else "",
        name=stop.name,
        source_id=stop.source_id,
        lat=stop.location.y,
        lon=stop.location.x,
        location_type=stop.location_type,
        agency_id=str(stop.agency_id),
        data_source_id=str(stop.agency.data_source_id) if stop.agency and stop.agency.data_source_id else "",
        routes=[
            {
                "id": rs.route.id,
                "slug": rs.route.slug,
                "place_slug": rs.route.place.slug if rs.route.place else "",
                "short_name": rs.route.short_name,
                "long_name": rs.route.long_name,
                "route_color": rs.route.route_color,
                "route_type": rs.route.route_type,
            }
            for rs in unique_routes
        ],
    )


def _get_stop_schedule_data(stop, date_param=None):
    """Schedule data for a stop."""
    from datetime import date as date_type

    if date_param:
        try:
            query_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            raise HttpError(400, "Invalid date format. Use YYYY-MM-DD")
    else:
        query_date = date_type.today()

    now_dt = datetime.now()
    now_time = now_dt.strftime("%H:%M:%S") if not date_param else "00:00:00"

    # Single query for both active and removed services
    cal_entries = CalendarDate.objects.filter(
        agency=stop.agency,
        date=query_date,
        exception_type__in=[1, 2],
    ).values_list("service_id", "exception_type")

    active_services = set()
    for service_id, exc_type in cal_entries:
        if exc_type == 1:
            active_services.add(service_id)
        else:
            active_services.discard(service_id)

    # Live vehicles currently at this stop from GTFS-RT Redis cache
    live_vehicles = []
    if not date_param and stop.agency and stop.agency.data_source_id:
        raw = cache.get(f'transit:rt:{stop.agency.data_source_id}')
        if raw:
            try:
                vehicles = json.loads(raw)
                cutoff = now_dt.timestamp() - 180  # vehicles seen in last 3 min
                for v in vehicles:
                    if v.get('sid') == stop.source_id and v.get('t', 0) >= cutoff:
                        live_vehicles.append({
                            "route_short_name": v.get('rn', ''),
                            "route_color": v.get('rc', ''),
                            "headsign": v.get('hs', ''),
                            "status": v.get('st', ''),
                            "vehicle_id": v.get('v', ''),
                        })
            except Exception:
                pass

    if not active_services:
        return {"stop_id": stop.id, "stop_name": stop.name, "date": str(query_date), "departures": [], "live_vehicles": live_vehicles}

    departures = (
        StopTime.objects.filter(
            stop=stop,
            trip__service_id__in=active_services,
            departure_time__gte=now_time,
        )
        .select_related("trip__route__place")
        .order_by("departure_time")[:30]
    )

    # Agency / data source info
    agency = stop.agency
    ds = agency.data_source if agency else None

    return {
        "stop_id": stop.id,
        "stop_name": stop.name,
        "date": str(query_date),
        "agency_name": agency.name if agency else "",
        "agency_url": agency.url if agency else "",
        "agency_timezone": agency.timezone if agency else "",
        "data_source_name": ds.name if ds else "",
        "data_source_url": ds.url if ds else "",
        "live_vehicles": live_vehicles,
        "departures": [
            {
                "departure_time": str(st.departure_time),
                "route_short_name": st.trip.route.short_name,
                "route_long_name": st.trip.route.long_name,
                "route_color": st.trip.route.route_color,
                "route_slug": st.trip.route.slug,
                "route_place_slug": st.trip.route.place.slug if st.trip.route.place else "",
                "headsign": st.trip.headsign,
                "trip_id": st.trip.id,
                "service_id": st.trip.service_id,
            }
            for st in departures
        ],
    }


# ===== Schemas =====

class TransitPlaceResponse(BaseModel):
    name: str
    slug: str
    country_code: str
    place_type: str
    stops_count: int = 0
    routes_count: int = 0


class AgencyResponse(BaseModel):
    id: str
    object_type: str = "transit_agency"
    name: str
    source_id: str
    url: str
    data_source_url: str = ""
    timezone: str
    lang: str
    routes_count: int = 0
    stops_count: int = 0
    last_imported_at: Optional[datetime] = None


class TransitRouteListItem(BaseModel):
    id: str
    object_type: str = "transit_route"
    slug: str = ""
    place_slug: str = ""
    short_name: str
    long_name: str
    route_type: int
    route_color: str
    route_text_color: str
    agency_id: str


class TransitRouteDirection(BaseModel):
    direction_id: int
    headsign: str = ""

class TransitRoutePlaceItem(BaseModel):
    name: str
    slug: str
    country_code: str

class TransitRouteDetail(BaseModel):
    id: str
    object_type: str = "transit_route"
    source_id: str = ""
    data_source_id: str = ""
    slug: str = ""
    place_slug: str = ""
    short_name: str
    long_name: str
    description: str
    route_type: int
    route_color: str
    route_text_color: str
    agency_id: str
    agency_name: str = ""
    stops: list = []          # direction_id=0 stops (or undirected)
    stops_dir1: list = []     # direction_id=1 stops (empty if route has no inbound direction)
    directions: list[TransitRouteDirection] = []
    places: list[TransitRoutePlaceItem] = []  # All places this route passes through
    geometry: Optional[Dict] = None


class TransitStopResponse(BaseModel):
    id: str
    object_type: str = "transit_stop"
    slug: str = ""
    place_slug: str = ""
    name: str
    source_id: str
    lat: float
    lon: float
    location_type: int
    agency_id: str
    data_source_id: str = ""
    routes: list = []


class ScheduleEntry(BaseModel):
    departure_time: str
    route_short_name: str
    route_color: str
    headsign: str
    trip_id: str


class TransitFeedResponse(BaseModel):
    id: str
    object_type: str = "transit_feed"
    name: str
    url: str
    format: str
    is_active: bool
    last_imported_at: Optional[datetime] = None
    last_error: str = ""
    rt_vehicles_url: str = ""
    agencies: List[str] = []
    routes_count: int = 0
    stops_count: int = 0
    trips_count: int = 0


# ===== Endpoints =====

@router.get("/transit/cities/", auth=None)
@ratelimit(group='transit:cities', key='ip', rate='120/m')
def list_transit_cities(request):
    """List places available for transit browsing (cached counts)."""
    places = Place.objects.exclude(slug='').filter(transit_stops_count__gt=0)
    return [
        TransitPlaceResponse(
            name=p.name,
            slug=p.slug,
            country_code=p.country_code,
            place_type=p.place_type,
            stops_count=p.transit_stops_count,
            routes_count=p.transit_routes_count,
        )
        for p in places
    ]


@router.get("/transit/discover/", auth=None)
@ratelimit(group='transit:discover', key='ip', rate='120/m')
def transit_discover(request, city: str = None):
    """Random stops and routes within a place for discovery."""
    if not city:
        raise HttpError(400, "city parameter required")
    place = Place.objects.filter(slug=city).first()
    if not place:
        raise HttpError(404, "Place not found")

    sf = _place_stop_filter(place)
    rf = _place_route_filter(place)

    stop_ids = list(Stop.objects.filter(sf).values_list('id', flat=True))
    route_ids = list(Route.objects.filter(rf).values_list('id', flat=True))
    stops_qs = Stop.objects.filter(id__in=random.sample(stop_ids, min(5, len(stop_ids))))
    routes_qs = Route.objects.filter(id__in=random.sample(route_ids, min(5, len(route_ids))))

    stops = []
    for s in stops_qs:
        stops.append({
            "id": s.id,
            "slug": s.slug,
            "place_slug": place.slug,
            "name": s.name,
            "lat": s.location.y,
            "lon": s.location.x,
            "location_type": s.location_type,
            "routes": _routes_for_stop(s),
        })

    routes = [
        {
            "id": r.id,
            "slug": r.slug,
            "place_slug": place.slug,
            "short_name": r.short_name,
            "long_name": r.long_name,
            "route_type": r.route_type,
            "route_color": r.route_color,
            "route_text_color": r.route_text_color,
            "agency_id": str(r.agency_id),
        }
        for r in routes_qs
    ]

    return {
        "city": {"name": place.name, "slug": place.slug},
        "stops": stops,
        "routes": routes,
    }


@router.get("/transit/search/", auth=None)
@ratelimit(group='transit:search', key='ip', rate='120/m')
def transit_search(request, q: str = "", city: str = None):
    """Search stops and routes by name, optionally scoped to a place."""
    if not q or len(q) < 2:
        return {"stops": [], "routes": []}

    stops_qs = Stop.objects.filter(name__icontains=q)
    routes_qs = Route.objects.filter(
        Q(short_name__icontains=q) | Q(long_name__icontains=q)
    )

    if city:
        place = Place.objects.filter(slug=city).first()
        if place:
            stops_qs = stops_qs.filter(_place_stop_filter(place))
            routes_qs = routes_qs.filter(_place_route_filter(place))

    stops_qs = stops_qs.select_related("place")[:20]
    routes_qs = routes_qs.select_related("place")[:20]

    stops = []
    for s in stops_qs:
        stops.append({
            "id": s.id,
            "slug": s.slug,
            "place_slug": s.place.slug if s.place else "",
            "name": s.name,
            "lat": s.location.y,
            "lon": s.location.x,
            "location_type": s.location_type,
            "routes": _routes_for_stop(s),
        })

    routes = [
        {
            "id": r.id,
            "slug": r.slug,
            "place_slug": r.place.slug if r.place else "",
            "short_name": r.short_name,
            "long_name": r.long_name,
            "route_type": r.route_type,
            "route_color": r.route_color,
            "route_text_color": r.route_text_color,
            "agency_id": str(r.agency_id),
        }
        for r in routes_qs
    ]

    return {"stops": stops, "routes": routes}


@router.get("/transit/feeds/", auth=None)
@ratelimit(group='transit:feeds', key='ip', rate='120/m')
def list_transit_feeds(request):
    """List all transit data sources with aggregated stats (raw SQL — data changes only on GTFS import)."""
    cache_key = 'transit:feeds_list'
    cached = cache.get(cache_key)
    if cached:
        return HttpResponse(cached, content_type='application/json')

    with connection.cursor() as cur:
        # Feed base data
        cur.execute("""
            SELECT ds.id, ds.name, ds.url, ds.format, ds.is_active,
                   ds.last_imported_at, ds.last_error, ds.rt_vehicles_url
            FROM geo_transitdatasource ds ORDER BY ds.name
        """)
        feed_rows = cur.fetchall()

        # Agency names per feed
        cur.execute("SELECT a.data_source_id, a.id, a.name FROM geo_agency a ORDER BY a.name")
        agency_rows = cur.fetchall()

        # Batch counts — one query each (fast GROUP BY, no lateral)
        cur.execute("SELECT agency_id, COUNT(*) FROM geo_route GROUP BY agency_id")
        routes_by_agency = dict(cur.fetchall())
        cur.execute("SELECT agency_id, COUNT(*) FROM geo_stop GROUP BY agency_id")
        stops_by_agency = dict(cur.fetchall())
        cur.execute(
            "SELECT r.agency_id, COUNT(*) FROM geo_trip t "
            "JOIN geo_route r ON t.route_id = r.id GROUP BY r.agency_id"
        )
        trips_by_agency = dict(cur.fetchall())

    # Group agencies by feed
    feed_agencies = {}  # feed_id -> [(agency_id, name), ...]
    for ds_id, aid, aname in agency_rows:
        feed_agencies.setdefault(ds_id, []).append((aid, aname))

    result = []
    for r in feed_rows:
        fid = r[0]
        agencies = feed_agencies.get(fid, [])
        agency_ids = [a[0] for a in agencies]
        result.append({
            'id': fid, 'object_type': 'transit_feed',
            'name': r[1], 'url': r[2], 'format': r[3],
            'is_active': r[4],
            'last_imported_at': r[5].isoformat().replace('+00:00', 'Z') if r[5] else None,
            'last_error': r[6] or '', 'rt_vehicles_url': r[7] or '',
            'agencies': [a[1] for a in agencies],
            'routes_count': sum(routes_by_agency.get(aid, 0) for aid in agency_ids),
            'stops_count': sum(stops_by_agency.get(aid, 0) for aid in agency_ids),
            'trips_count': sum(trips_by_agency.get(aid, 0) for aid in agency_ids),
        })
    body = orjson.dumps(result)
    cache.set(cache_key, body, 3600)
    return HttpResponse(body, content_type='application/json')


@router.get("/transit/agencies/", auth=None)
@ratelimit(group='transit:agencies', key='ip', rate='120/m')
def list_transit_agencies(request):
    """List all transit agencies (raw SQL — data changes only on GTFS import)."""
    cache_key = 'transit:agencies_list'
    cached = cache.get(cache_key)
    if cached:
        return HttpResponse(cached, content_type='application/json')

    with connection.cursor() as cur:
        cur.execute("""
            SELECT a.id, a.name, a.source_id, a.url, a.timezone, a.lang,
                   COALESCE(ds.url, '') AS data_source_url,
                   ds.last_imported_at,
                   (SELECT COUNT(*) FROM geo_route r WHERE r.agency_id = a.id) AS routes_count,
                   (SELECT COUNT(*) FROM geo_stop s WHERE s.agency_id = a.id) AS stops_count
            FROM geo_agency a
            LEFT JOIN geo_transitdatasource ds ON a.data_source_id = ds.id
            ORDER BY a.name
        """)
        rows = cur.fetchall()

    # Columns: id(0) name(1) source_id(2) url(3) timezone(4) lang(5) data_source_url(6)
    #          last_imported_at(7) routes_count(8) stops_count(9)
    result = [
        {
            'id': r[0], 'object_type': 'transit_agency',
            'name': r[1], 'source_id': r[2], 'url': r[3],
            'data_source_url': r[6], 'timezone': r[4], 'lang': r[5],
            'routes_count': r[8], 'stops_count': r[9],
            'last_imported_at': r[7].isoformat().replace('+00:00', 'Z') if r[7] else None,
        }
        for r in rows
    ]
    body = orjson.dumps(result)
    cache.set(cache_key, body, 3600)
    return HttpResponse(body, content_type='application/json')


@router.get("/transit/vehicles/geojson/", auth=None)
@ratelimit(group='transit:vehicles_geojson', key='ip', rate='120/m')
def transit_vehicles_geojson(request, bbox: str = None, agency_id: str = None):
    """Live vehicle positions from Redis cache (GTFS-RT)."""
    qs = TransitDataSource.objects.filter(is_active=True).exclude(rt_vehicles_url='')
    if agency_id:
        qs = qs.filter(agencies__id=agency_id)
    ds_ids = list(qs.values_list('id', flat=True))

    # Batch Redis reads instead of N individual cache.get calls
    cache_keys = [f'transit:rt:{ds_id}' for ds_id in ds_ids]
    cached = cache.get_many(cache_keys)
    all_vehicles = []
    for key in cache_keys:
        raw = cached.get(key)
        if raw:
            all_vehicles.extend(json.loads(raw))

    # Parse bbox early to filter vehicles before building features
    bbox_filter = None
    if bbox:
        try:
            w, s, e, n = [float(x) for x in bbox.split(',')]
            bbox_filter = (w, s, e, n)
        except Exception:
            pass

    # Pre-filter vehicles with valid coordinates (and bbox if provided)
    filtered = []
    for v in all_vehicles:
        lat, lon = v.get('lat'), v.get('lon')
        if not lat or not lon:
            continue
        if bbox_filter:
            w, s, e, n = bbox_filter
            if not (w <= lon <= e and s <= lat <= n):
                continue
        filtered.append(v)

    # Resolve stop source_id → {id, name} from DB (cached 30s)
    stop_src_ids = frozenset(v['sid'] for v in filtered if v.get('sid'))
    stop_lookup = {}
    if stop_src_ids:
        cache_key = 'transit:vehicle_stops'
        stop_lookup = cache.get(cache_key)
        if stop_lookup is None:
            stop_lookup = {}
            for s in Stop.objects.filter(source_id__in=stop_src_ids).only('id', 'source_id', 'name'):
                stop_lookup[s.source_id] = {'id': s.id, 'name': s.name}
            cache.set(cache_key, stop_lookup, 30)

    features = []
    for v in filtered:
        lat, lon = v.get('lat'), v.get('lon')
        stop_info = stop_lookup.get(v.get('sid', ''))

        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
            'properties': {
                'vehicle_id': v['v'],
                'bearing': v.get('b', 0),
                'speed': v.get('s', 0),
                'route_id': v.get('r', ''),
                'route_color': v.get('rc', '3b82f6'),
                'route_name': v.get('rn', ''),
                'status': v.get('st', ''),
                'timestamp': v.get('t', 0),
                'stop_source_id': v.get('sid', ''),
                'stop_id': stop_info['id'] if stop_info else None,
                'stop_name': stop_info['name'] if stop_info else None,
                'trip_source_id': v.get('tid', ''),
                'headsign': v.get('hs', ''),
                'direction_id': v.get('d'),
            },
        })

    return {'type': 'FeatureCollection', 'features': features}


@router.get("/transit/routes/geojson/", auth=None)
@ratelimit(group='transit:routes_geojson', key='ip', rate='120/m')
def transit_routes_geojson(request, agency_id: str = None, bbox: str = None):
    """
    GeoJSON FeatureCollection of routes with geometry (for map display).
    bbox format: west,south,east,north — filters routes intersecting the bbox.
    Without bbox, returns all routes (can be ~25MB, use with caution).
    """
    qs = Route.objects.filter(geometry__isnull=False)
    if agency_id:
        qs = qs.filter(agency_id=agency_id)

    if bbox:
        try:
            parts = [float(x) for x in bbox.split(",")]
            if len(parts) == 4:
                from django.contrib.gis.geos import Polygon
                west, south, east, north = parts
                bbox_poly = Polygon.from_bbox((west, south, east, north))
                bbox_poly.srid = 4326
                qs = qs.filter(geometry__intersects=bbox_poly)
        except (ValueError, IndexError):
            pass

    qs = qs.only("id", "short_name", "long_name", "route_type", "route_color", "route_text_color", "geometry")

    features = []
    for r in qs:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": list(r.geometry.coords),
            },
            "properties": {
                "id": r.id,
                "short_name": r.short_name,
                "long_name": r.long_name,
                "route_type": r.route_type,
                "route_color": r.route_color,
                "route_text_color": r.route_text_color,
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/transit/routes/", auth=None, response=List[TransitRouteListItem])
@ratelimit(group='transit:routes', key='ip', rate='120/m')
def list_transit_routes(request, agency_id: str = None, type: int = None):
    """List transit routes, optionally filtered by agency and route type."""
    version = cache.get("transit:routes:version", 0)
    cache_key = f"transit:routes:v{version}:{agency_id or 'all'}:{type if type is not None else 'all'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    qs = Route.objects.only(
        "id", "slug", "short_name", "long_name", "route_type",
        "route_color", "route_text_color", "agency_id", "place_id",
        "place__slug",
    ).select_related("place").order_by("short_name")
    if agency_id:
        qs = qs.filter(agency_id=agency_id)
    if type is not None:
        qs = qs.filter(route_type=type)
    qs = qs[:500]
    result = [
        TransitRouteListItem(
            id=r.id,
            slug=r.slug,
            place_slug=r.place.slug if r.place else "",
            short_name=r.short_name,
            long_name=r.long_name,
            route_type=r.route_type,
            route_color=r.route_color,
            route_text_color=r.route_text_color,
            agency_id=str(r.agency_id),
        )
        for r in qs
    ]
    cache.set(cache_key, result, 3600)  # 1h TTL — routes change only on GTFS import
    return result


@router.get("/transit/stops/geojson/", auth=None)
@ratelimit(group='transit:stops_geojson', key='ip', rate='120/m')
def transit_stops_geojson(request, agency_id: str = None, bbox: str = None):
    """
    GeoJSON FeatureCollection of stops (for map display).
    Raw SQL — ORM PostGIS field overhead is ~250ms on 5K stops.
    bbox format: west,south,east,north (e.g., -9.5,38.5,-8.5,39.0)
    Redis-cached with rounded bbox key (60s TTL).
    """
    # Round bbox to 2 decimal places (~1km grid) to reduce cache key cardinality
    bbox_key = 'none'
    parsed_bbox = None
    if bbox:
        try:
            parts = [float(x) for x in bbox.split(",")]
            if len(parts) == 4:
                parsed_bbox = tuple(round(x, 2) for x in parts)
                bbox_key = ','.join(str(x) for x in parsed_bbox)
        except (ValueError, IndexError):
            pass

    cache_key = f"transit:stops_geojson:{agency_id or 'all'}:{bbox_key}"
    cached = cache.get(cache_key)
    if cached:
        return HttpResponse(cached, content_type='application/json')

    conditions = ["s.location IS NOT NULL"]
    params = []

    if agency_id:
        conditions.append("s.agency_id = %s")
        params.append(agency_id)

    if parsed_bbox:
        west, south, east, north = parsed_bbox
        conditions.append(
            "s.location && ST_MakeEnvelope(%s, %s, %s, %s, 4326)::geography"
        )
        params.extend([west, south, east, north])

    where = " AND ".join(conditions)

    with connection.cursor() as cur:
        cur.execute(f"""
            SELECT s.id, s.name, s.source_id, s.location_type,
                   ST_X(s.location::geometry), ST_Y(s.location::geometry)
            FROM geo_stop s
            WHERE {where}
            LIMIT 5000
        """, params)
        rows = cur.fetchall()

    features = [
        {
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [r[4], r[5]]},
            'properties': {
                'id': r[0], 'name': r[1],
                'source_id': r[2], 'location_type': r[3],
            },
        }
        for r in rows
    ]
    body = orjson.dumps({'type': 'FeatureCollection', 'features': features})
    cache.set(cache_key, body, 60)  # 60s TTL — short enough for GTFS imports
    return HttpResponse(body, content_type='application/json')


@router.get("/transit/stops/nearby/", auth=None)
@ratelimit(group='transit:nearby_stops', key='ip', rate='120/m')
def list_nearby_transit_stops(request, lat: float = None, lon: float = None, r: int = 500, city: str = None):
    """Find GTFS stops near a point. Raw SQL with batch route lookup (eliminates N+1).
    r = radius in meters (default 500, max 5000).
    If city slug is provided and lat/lon missing, uses city center + city radius."""
    if lat is None or lon is None:
        if city:
            place = Place.objects.filter(slug=city).first()
            if not place:
                raise HttpError(404, "Place not found")
            if place.center_point:
                lat, lon, r = place.center_point.y, place.center_point.x, 30000
            else:
                raise HttpError(400, "Place has no center point")
        else:
            raise HttpError(400, "lat and lon required (or provide city)")
    r = min(r, 50000)

    with connection.cursor() as cur:
        # Fetch nearby stops
        cur.execute("""
            SELECT s.id, s.slug, s.name, s.source_id, s.location_type, s.agency_id,
                   ST_X(s.location::geometry), ST_Y(s.location::geometry),
                   COALESCE(p.slug, '') AS place_slug
            FROM geo_stop s
            LEFT JOIN geo_place p ON s.place_id = p.id
            WHERE ST_DWithin(s.location::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
            ORDER BY s.location::geography <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
            LIMIT 100
        """, [lon, lat, r, lon, lat])
        stop_rows = cur.fetchall()

    if not stop_rows:
        body = orjson.dumps({'type': 'FeatureCollection', 'features': []})
        return HttpResponse(body, content_type='application/json')

    # Batch route lookup for all stops at once (eliminates N+1)
    stop_ids = [row[0] for row in stop_rows]
    with connection.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (rs.stop_id, r.short_name)
                   rs.stop_id, r.short_name, r.route_color, r.route_type
            FROM geo_routestop rs
            JOIN geo_route r ON rs.route_id = r.id
            WHERE rs.stop_id = ANY(%s)
            ORDER BY rs.stop_id, r.short_name
        """, [stop_ids])
        route_rows = cur.fetchall()

    # Group routes by stop_id
    routes_by_stop = {}
    for rr in route_rows:
        routes_by_stop.setdefault(rr[0], []).append({
            'short_name': rr[1], 'route_color': rr[2], 'route_type': rr[3],
        })

    features = [
        {
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [r[6], r[7]]},
            'properties': {
                'id': r[0], 'slug': r[1], 'place_slug': r[8],
                'name': r[2], 'source_id': r[3],
                'location_type': r[4], 'agency_id': r[5],
                'routes': routes_by_stop.get(r[0], [])[:10],
            },
        }
        for r in stop_rows
    ]
    body = orjson.dumps({'type': 'FeatureCollection', 'features': features})
    return HttpResponse(body, content_type='application/json')


@router.get("/transit/stops/{city_slug}/{stop_slug}/", auth=None, response=TransitStopResponse)
@ratelimit(group='transit:stop_detail', key='ip', rate='120/m')
def get_transit_stop_by_slug(request, city_slug: str, stop_slug: str):
    """Stop detail by city/slug."""
    stop = get_object_or_404(Stop.objects.select_related("place", "agency"), place__slug=city_slug, slug=stop_slug)
    return _build_stop_detail(stop)


@router.get("/transit/stops/{city_slug}/{stop_slug}/schedule/", auth=None)
@ratelimit(group='transit:stop_schedule', key='ip', rate='120/m')
def get_stop_schedule_by_slug(request, city_slug: str, stop_slug: str, date: str = None):
    """Stop schedule by city/slug."""
    stop = get_object_or_404(Stop.objects.select_related("place", "agency", "agency__data_source"), place__slug=city_slug, slug=stop_slug)
    return _get_stop_schedule_data(stop, date)


@router.get("/transit/routes/{city_slug}/{route_slug}/", auth=None, response=TransitRouteDetail)
@ratelimit(group='transit:route_detail', key='ip', rate='120/m')
def get_transit_route_by_slug(request, city_slug: str, route_slug: str):
    """Route detail by city/slug."""
    route = get_object_or_404(Route.objects.select_related("agency__data_source", "place"), place__slug=city_slug, slug=route_slug)
    return _build_route_detail(route)


@router.get("/transit/routes/{city_slug}/{route_slug}/schedule/", auth=None)
@ratelimit(group='transit:route_schedule', key='ip', rate='120/m')
def get_route_schedule(request, city_slug: str, route_slug: str):
    """Next scheduled departures for each stop on a route (GTFS static), both directions."""
    from datetime import date as date_type, time as time_type

    route = get_object_or_404(
        Route.objects.select_related("agency", "place"),
        place__slug=city_slug, slug=route_slug,
    )
    query_date = date_type.today()
    now_time = datetime.now().strftime("%H:%M:%S")

    # Single query for both active and removed services
    cal_entries = CalendarDate.objects.filter(
        agency=route.agency,
        date=query_date,
        exception_type__in=[1, 2],
    ).values_list("service_id", "exception_type")

    active_services = set()
    for service_id, exc_type in cal_entries:
        if exc_type == 1:
            active_services.add(service_id)
        else:
            active_services.discard(service_id)

    empty = {"schedule": {"0": {}, "1": {}}, "first_departure": {}, "is_night": False}
    if not active_services:
        return empty

    base_qs = StopTime.objects.filter(
        trip__route=route,
        trip__service_id__in=active_services,
    )

    # Detect night route: all departures before 06:00
    time_range = base_qs.aggregate(max_dep=Max("departure_time"))
    is_night = bool(time_range["max_dep"] and time_range["max_dep"] <= time_type(6, 0))

    result = {"schedule": {}, "first_departure": {}, "is_night": is_night}

    for direction in (0, 1):
        dir_qs = base_qs.filter(trip__direction_id=direction)

        # Next departures after now per stop
        upcoming = (
            dir_qs.filter(departure_time__gte=now_time)
            .values("stop__source_id")
            .annotate(next_dep=Min("departure_time"))
        )
        schedule = {}
        for st in upcoming:
            dep = st["next_dep"]
            if dep:
                schedule[st["stop__source_id"]] = dep.strftime("%H:%M")

        result["schedule"][str(direction)] = schedule

        # First stop of this direction — always show next departure
        first_rs = (
            RouteStop.objects.filter(route=route, direction_id=direction)
            .order_by("sequence")
            .select_related("stop")
            .first()
        )
        if first_rs:
            src = first_rs.stop.source_id
            if src in schedule:
                result["first_departure"][str(direction)] = schedule[src]
            else:
                # All departures passed — show earliest (next service cycle)
                earliest = (
                    dir_qs.filter(stop=first_rs.stop)
                    .order_by("departure_time")
                    .values_list("departure_time", flat=True)
                    .first()
                )
                if earliest:
                    result["first_departure"][str(direction)] = earliest.strftime("%H:%M")

    return result


@router.get("/transit/routes/{city_slug}/{route_slug}/live/", auth=None)
@ratelimit(group='transit:route_live', key='ip', rate='120/m')
def get_route_live_vehicles(request, city_slug: str, route_slug: str):
    """Return stop_source_ids where vehicles of this route are currently present (from Redis GTFS-RT cache)."""
    route = get_object_or_404(
        Route.objects.select_related("agency__data_source", "place"),
        place__slug=city_slug, slug=route_slug
    )
    ds = route.agency.data_source if route.agency else None
    if not ds:
        return {"stop_ids": []}

    raw = cache.get(f'transit:rt:{ds.id}')
    if not raw:
        return {"stop_ids": []}

    vehicles = json.loads(raw)
    stop_ids = list({
        v['sid'] for v in vehicles
        if v.get('r') == route.source_id and v.get('sid')
    })
    return {"stop_ids": stop_ids}


@router.get("/transit/vehicles/{vehicle_id}/history/", auth=None)
@ratelimit(group='transit:vehicle_history', key='ip', rate='120/m')
def transit_vehicle_history(request, vehicle_id: str, ds_id: str = None,
                             hours: int = 1):
    """
    Vehicle position history from TimescaleDB.
    Returns GeoJSON LineString of positions over time.

    Args:
        vehicle_id: External vehicle ID from feed
        ds_id: Data source ID (optional, filters to specific feed)
        hours: Lookback window in hours (default 1, max 24)
    """
    from datetime import timedelta
    from django.utils import timezone as tz

    hours = min(max(hours, 1), 24)
    since = tz.now() - timedelta(hours=hours)

    qs = VehiclePositionHistory.objects.filter(
        vehicle_id=vehicle_id,
        time__gte=since,
    ).order_by('time')

    if ds_id:
        qs = qs.filter(data_source_id=ds_id)

    rows = list(qs.values_list(
        'time', 'latitude', 'longitude', 'bearing', 'speed',
        'route_source_id', 'stop_source_id', 'status',
    )[:500])

    if not rows:
        return {'type': 'FeatureCollection', 'features': []}

    coordinates = [[r[2], r[1]] for r in rows]  # [lon, lat]
    timestamps = [r[0].isoformat() for r in rows]
    bearings = [r[3] for r in rows]
    speeds = [r[4] for r in rows]

    feature = {
        'type': 'Feature',
        'geometry': {
            'type': 'LineString',
            'coordinates': coordinates,
        },
        'properties': {
            'vehicle_id': vehicle_id,
            'timestamps': timestamps,
            'bearings': bearings,
            'speeds': speeds,
            'route_source_id': rows[0][5],
            'points_count': len(rows),
        },
    }

    return {'type': 'FeatureCollection', 'features': [feature]}


@router.get("/transit/vehicles/state/", auth=None)
@ratelimit(group='transit:vehicle_state', key='ip', rate='120/m')
def get_vehicle_state(request, ds_id: str, vid: str):
    """Vehicle state from Redis: vdata + vprev (STT tracking state)."""
    import redis as sync_redis

    r = sync_redis.Redis(
        host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
        port=getattr(settings, 'REDIS_PORT', 6379),
        decode_responses=True,
    )

    result = {"vehicle_id": vid, "data_source_id": ds_id}

    # vdata (current position/route info from GTFS-RT)
    vdata_raw = r.hget('transit:vdata', f'{ds_id}:{vid}')
    if vdata_raw:
        try:
            result["vdata"] = json.loads(vdata_raw)
        except (json.JSONDecodeError, TypeError):
            pass

    # vprev (STT tracking state)
    vprev = r.hgetall(f'transit:vprev:{ds_id}:{vid}')
    if vprev:
        result["vprev"] = vprev

    # Resolve stop name if we have a stop source_id
    sid = result.get("vdata", {}).get("sid")
    if sid:
        stop = Stop.objects.filter(
            agency__data_source_id=ds_id, source_id=sid
        ).values_list("name", flat=True).first()
        if stop:
            result["stop_name"] = stop

    # Data source info
    ds = TransitDataSource.objects.filter(id=ds_id).values("name", "url").first()
    if ds:
        result["data_source_name"] = ds["name"]
        result["data_source_url"] = ds["url"]

    r.close()
    return result


@router.get("/transit/stops/{city_slug}/{stop_slug}/eta/", auth=None)
@ratelimit(group='transit:stop_eta', key='ip', rate='120/m')
def get_stop_eta(request, city_slug: str, stop_slug: str):
    """
    ETA of approaching vehicles to a specific stop.

    Returns vehicles that are confirmed-tracking on routes serving this stop,
    with estimated arrival time in seconds (chained segment averages from Redis).

    DB queries: 1 stop lookup + 1 RouteStop query (to find serving routes).
    All ETA math is pure Redis reads.
    """
    import redis as sync_redis

    stop = get_object_or_404(
        Stop.objects.select_related("agency__data_source", "place"),
        place__slug=city_slug, slug=stop_slug
    )
    ds = stop.agency.data_source if stop.agency else None
    if not ds:
        return {"stop": stop.source_id, "stop_name": stop.name, "vehicles": []}

    ds_id = str(ds.id)
    stop_src = stop.source_id

    # Find all routes serving this stop
    route_dirs = list(
        RouteStop.objects.filter(stop=stop)
        .values_list('route__source_id', 'direction_id')
    )
    if not route_dirs:
        return {"stop": stop_src, "stop_name": stop.name, "vehicles": []}

    # Normalize direction_id
    route_dir_set = {(r, d if d is not None else 0) for r, d in route_dirs}

    # Connect to Redis
    r = sync_redis.Redis(
        host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
        port=getattr(settings, 'REDIS_PORT', 6379),
        decode_responses=True,
    )

    # Load stop sequences from Redis for relevant routes
    # Key: transit:rstops:{route_src}:{dir} → JSON array of [source_id, lat, lon]
    route_seqs = {}  # (route_src, dir) → [source_id, ...]
    stop_target_idx = {}  # (route_src, dir) → index of target stop in sequence

    pipe = r.pipeline(transaction=False)
    rd_list = list(route_dir_set)
    for route_src, dir_id in rd_list:
        pipe.get(f'transit:rstops:{route_src}:{dir_id}')
    seq_results = pipe.execute()

    for (route_src, dir_id), raw in zip(rd_list, seq_results):
        if not raw:
            continue
        try:
            stops_list = json.loads(raw)  # [[source_id, lat, lon], ...]
        except (json.JSONDecodeError, TypeError):
            continue
        source_ids = [s[0] for s in stops_list]
        if stop_src in source_ids:
            route_seqs[(route_src, dir_id)] = source_ids
            stop_target_idx[(route_src, dir_id)] = source_ids.index(stop_src)

    if not route_seqs:
        r.close()
        return {"stop": stop_src, "stop_name": stop.name, "vehicles": []}

    # Scan vprev for confirmed vehicles on these routes
    vehicles_eta = []
    vprev_prefix = f'transit:vprev:{ds_id}:'
    cursor = 0

    while True:
        cursor, keys = r.scan(cursor, match=f'{vprev_prefix}*', count=500)
        if keys:
            pipe = r.pipeline(transaction=False)
            for key in keys:
                pipe.hgetall(key)
            states = pipe.execute()

            for key, state in zip(keys, states):
                if not state or state.get('st') != 'c':
                    continue

                v_route = state.get('r', '')
                v_dir = int(state.get('d', -1))
                v_idx = int(state.get('idx', 0))

                route_key = (v_route, v_dir)
                if route_key not in stop_target_idx:
                    continue

                target_idx = stop_target_idx[route_key]
                ordered_stops = route_seqs[route_key]

                # Vehicle must be BEFORE target stop
                if v_idx >= target_idx:
                    continue

                # Don't show vehicles that are too far away (>15 stops)
                stops_away = target_idx - v_idx
                if stops_away > 15:
                    continue

                # Chain segment averages
                seg_keys = []
                for i in range(v_idx, target_idx):
                    if i + 1 < len(ordered_stops):
                        seg_keys.append(f'transit:stt:{ds_id}:{ordered_stops[i]}:{ordered_stops[i + 1]}')

                if not seg_keys:
                    continue

                # Batch read all segment times
                pipe2 = r.pipeline(transaction=False)
                for sk in seg_keys:
                    pipe2.lrange(sk, 0, -1)
                seg_results = pipe2.execute()

                eta_seconds = 0.0
                observed_segments = 0
                for vals in seg_results:
                    if vals:
                        avg_time = sum(float(v) for v in vals) / len(vals)
                        eta_seconds += avg_time
                        observed_segments += 1
                    else:
                        eta_seconds += 90  # fallback: 90s per segment

                if eta_seconds <= 0:
                    continue

                vid = key[len(vprev_prefix):]
                vdata_raw = r.hget('transit:vdata', f'{ds_id}:{vid}')
                vdata = json.loads(vdata_raw) if vdata_raw else {}

                vehicles_eta.append({
                    'vehicle_id': vid,
                    'route': v_route,
                    'route_name': vdata.get('rn', ''),
                    'route_color': vdata.get('rc', '3b82f6'),
                    'headsign': vdata.get('hs', ''),
                    'direction': v_dir,
                    'eta_seconds': int(eta_seconds),
                    'eta_minutes': round(eta_seconds / 60, 1),
                    'stops_away': stops_away,
                    'observed_segments': observed_segments,
                    'total_segments': len(seg_keys),
                    'lat': vdata.get('lat'),
                    'lon': vdata.get('lon'),
                })

        if cursor == 0:
            break

    r.close()

    vehicles_eta.sort(key=lambda x: x['eta_seconds'])

    return {
        "stop": stop_src,
        "stop_name": stop.name,
        "vehicles": vehicles_eta[:20],
    }


@router.get("/transit/routes/{city_slug}/{route_slug}/eta/", auth=None)
@ratelimit(group='transit:route_eta', key='ip', rate='120/m')
def get_route_eta(request, city_slug: str, route_slug: str, direction: int = 0):
    """
    ETA predictions for all stops on a route.

    For each stop, returns the earliest predicted arrival time (seconds from now)
    from any confirmed-tracking vehicle approaching that stop.

    Pure Redis reads — no DB queries except initial route lookup.
    """
    import redis as sync_redis

    route = get_object_or_404(
        Route.objects.select_related("agency__data_source"),
        place__slug=city_slug, slug=route_slug,
    )
    ds = route.agency.data_source if route.agency else None
    if not ds:
        return {"etas": {}}

    ds_id = str(ds.id)
    route_src = route.source_id

    r = sync_redis.Redis(
        host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
        port=getattr(settings, 'REDIS_PORT', 6379),
        decode_responses=True,
    )

    # Load stop sequence for this route+direction
    raw = r.get(f'transit:rstops:{route_src}:{direction}')
    if not raw:
        r.close()
        return {"etas": {}}

    try:
        stops_list = json.loads(raw)  # [[source_id, lat, lon], ...]
    except (json.JSONDecodeError, TypeError):
        r.close()
        return {"etas": {}}

    if len(stops_list) < 2:
        r.close()
        return {"etas": {}}

    source_ids = [s[0] for s in stops_list]
    stop_coords = [(s[1], s[2]) for s in stops_list]
    num_stops = len(source_ids)

    # Batch-read ALL segment travel times for consecutive stop pairs
    seg_keys = [
        f'transit:stt:{ds_id}:{source_ids[i]}:{source_ids[i + 1]}'
        for i in range(num_stops - 1)
    ]
    pipe = r.pipeline(transaction=False)
    for sk in seg_keys:
        pipe.lrange(sk, 0, -1)
    seg_results = pipe.execute()

    # Pre-compute segment averages: seg_avg[i] = avg time from stop i to stop i+1
    seg_avg = []
    for vals in seg_results:
        if vals:
            avg_time = sum(float(v) for v in vals) / len(vals)
            seg_avg.append(avg_time)
        else:
            seg_avg.append(90.0)  # fallback: 90s per unobserved segment

    # Scan vprev for confirmed/tentative vehicles on this route+direction
    vprev_prefix = f'transit:vprev:{ds_id}:'
    vehicle_indices = []  # [(vehicle_stop_idx, ...)]
    tracked_vids = set()  # vehicle IDs already tracked by STT
    cursor = 0

    while True:
        cursor, keys = r.scan(cursor, match=f'{vprev_prefix}*', count=500)
        if keys:
            pipe = r.pipeline(transaction=False)
            for key in keys:
                pipe.hgetall(key)
            states = pipe.execute()

            for key, state in zip(keys, states):
                if not state:
                    continue
                if state.get('r') != route_src:
                    continue
                # Track ALL vehicles on this route for fallback exclusion
                vid = key[len(vprev_prefix):]
                tracked_vids.add(vid)
                # Only use confirmed/tentative on target direction for ETA
                if state.get('st') not in ('c', 't'):
                    continue
                if int(state.get('d', -1)) != direction:
                    continue
                v_idx = int(state.get('idx', 0))
                vehicle_indices.append(v_idx)

        if cursor == 0:
            break

    # Fallback: if no useful tracked vehicles (all at last stop), use GTFS-RT.
    # Only for vehicles NOT already tracked by STT (avoids re-snapping
    # terminal vehicles to wrong intermediate stops).
    if not any(idx < num_stops - 1 for idx in vehicle_indices):
        import time as _time
        now_ts = _time.time()
        members_key = f'transit:members:{ds_id}'
        member_ids = r.smembers(members_key)
        if member_ids:
            raw_values = r.hmget('transit:vdata', *member_ids)
            for raw_v in raw_values:
                if not raw_v:
                    continue
                try:
                    v = json.loads(raw_v)
                except (json.JSONDecodeError, TypeError):
                    continue
                if v.get('r') != route_src:
                    continue
                # Skip zombie vehicles and stale data (>5 min)
                if v.get('z'):
                    continue
                v_ts = v.get('t')
                if v_ts and (now_ts - v_ts) > 300:
                    continue
                # Skip vehicles already tracked by STT (they're at terminal)
                vid = v.get('v', '')
                if vid in tracked_vids:
                    continue
                v_dir = v.get('d')
                if v_dir is None:
                    continue
                if int(v_dir) != direction:
                    continue
                vlat, vlon = v.get('lat'), v.get('lon')
                if vlat is None or vlon is None:
                    continue
                # Find nearest stop by coordinates
                best_idx = 0
                best_dist = float('inf')
                for i, (slat, slon) in enumerate(stop_coords):
                    d2 = (vlat - slat) ** 2 + (vlon - slon) ** 2
                    if d2 < best_dist:
                        best_dist = d2
                        best_idx = i
                vehicle_indices.append(best_idx)

    r.close()

    if not vehicle_indices:
        return {"etas": {}}

    # For each stop, find the nearest approaching vehicle and compute cumulative ETA
    # For a vehicle at stop_idx v, ETA to stop j (j > v) = sum(seg_avg[v..j-1])
    # Pre-compute cumulative sums from each vehicle position
    etas = {}  # stop_source_id → min eta_seconds

    for v_idx in vehicle_indices:
        if v_idx >= num_stops - 1:
            continue

        cumulative = 0.0
        for j in range(v_idx, num_stops - 1):
            cumulative += seg_avg[j]
            stop_src = source_ids[j + 1]
            if stop_src not in etas or cumulative < etas[stop_src]:
                etas[stop_src] = int(cumulative)

    return {"etas": etas}


@router.get("/transit/routes/{city_slug}/{route_slug}/eta/{stop_source_id}/", auth=None)
@ratelimit(group='transit:route_eta_detail', key='ip', rate='120/m')
def get_route_eta_detail(request, city_slug: str, route_slug: str,
                         stop_source_id: str, direction: int = 0):
    """
    Detailed ETA breakdown for a specific stop on a route.

    Shows all approaching vehicles with per-segment travel time chains,
    observed vs fallback segments, vehicle state from Redis.
    """
    import redis as sync_redis

    route = get_object_or_404(
        Route.objects.select_related("agency__data_source"),
        place__slug=city_slug, slug=route_slug,
    )
    ds = route.agency.data_source if route.agency else None
    if not ds:
        return {"error": "no data source"}

    ds_id = str(ds.id)
    route_src = route.source_id

    r = sync_redis.Redis(
        host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
        port=getattr(settings, 'REDIS_PORT', 6379),
        decode_responses=True,
    )

    # Load stop sequence
    raw = r.get(f'transit:rstops:{route_src}:{direction}')
    if not raw:
        r.close()
        return {"error": "no stop sequence", "vehicles": []}

    try:
        stops_list = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        r.close()
        return {"error": "bad stop sequence", "vehicles": []}

    source_ids = [s[0] for s in stops_list]
    if stop_source_id not in source_ids:
        r.close()
        return {"error": "stop not in sequence", "vehicles": []}

    target_idx = source_ids.index(stop_source_id)
    num_stops = len(source_ids)

    # Batch-read ALL segment travel times
    all_seg_keys = [
        f'transit:stt:{ds_id}:{source_ids[i]}:{source_ids[i + 1]}'
        for i in range(num_stops - 1)
    ]
    pipe = r.pipeline(transaction=False)
    for sk in all_seg_keys:
        pipe.lrange(sk, 0, -1)
    all_seg_results = pipe.execute()

    # Segment raw data: index i → {times: [...], avg: float, observed: bool}
    seg_data = []
    for vals in all_seg_results:
        if vals:
            times = [float(v) for v in vals]
            seg_data.append({
                'times': [round(t, 1) for t in times],
                'avg': round(sum(times) / len(times), 1),
                'observed': True,
            })
        else:
            seg_data.append({
                'times': [],
                'avg': 90.0,
                'observed': False,
            })

    # Scan vprev for vehicles on this route+direction (any state)
    vprev_prefix = f'transit:vprev:{ds_id}:'
    vehicles_detail = []
    cursor = 0

    while True:
        cursor, keys = r.scan(cursor, match=f'{vprev_prefix}*', count=500)
        if keys:
            pipe = r.pipeline(transaction=False)
            for key in keys:
                pipe.hgetall(key)
            states = pipe.execute()

            for key, state in zip(keys, states):
                if not state:
                    continue
                if state.get('r') != route_src:
                    continue

                v_dir = int(state.get('d', -1))
                if v_dir != direction:
                    continue

                vid = key[len(vprev_prefix):]
                v_idx = int(state.get('idx', 0))
                st = state.get('st', '?')
                stall = int(state.get('stall', 0))

                # Vehicle data from transit:vdata
                vdata_raw = r.hget('transit:vdata', f'{ds_id}:{vid}')
                vdata = json.loads(vdata_raw) if vdata_raw else {}

                is_approaching = v_idx < target_idx and st in ('c', 't')
                stops_away = target_idx - v_idx if is_approaching else None

                # Build segment chain if approaching
                segments_chain = []
                eta_seconds = 0.0
                observed_count = 0
                fallback_count = 0

                if is_approaching:
                    for i in range(v_idx, target_idx):
                        if i < len(seg_data):
                            sd = seg_data[i]
                            eta_seconds += sd['avg']
                            segments_chain.append({
                                'from': source_ids[i],
                                'to': source_ids[i + 1],
                                'avg_s': sd['avg'],
                                'samples': len(sd['times']),
                                'observed': sd['observed'],
                            })
                            if sd['observed']:
                                observed_count += 1
                            else:
                                fallback_count += 1

                vehicles_detail.append({
                    'vehicle_id': vid,
                    'state': {
                        'status': {'c': 'confirmed', 't': 'tentative', 'd': 'dual'}.get(st, st),
                        'stop_index': v_idx,
                        'stop_id': source_ids[v_idx] if v_idx < num_stops else '?',
                        'stall_count': stall,
                        'direction': v_dir,
                        'last_transition': state.get('t', ''),
                        'lat': state.get('lat', ''),
                        'lon': state.get('lon', ''),
                    },
                    'live': {
                        'lat': vdata.get('lat'),
                        'lon': vdata.get('lon'),
                        'speed': vdata.get('s'),
                        'bearing': vdata.get('b'),
                        'status': vdata.get('st', ''),
                        'headsign': vdata.get('hs', ''),
                        'zombie': bool(vdata.get('z')),
                    },
                    'is_approaching': is_approaching,
                    'stops_away': stops_away,
                    'eta_seconds': int(eta_seconds) if is_approaching else None,
                    'observed_segments': observed_count,
                    'fallback_segments': fallback_count,
                    'segments': segments_chain,
                })

        if cursor == 0:
            break

    r.close()

    # Sort: approaching vehicles first (by ETA), then non-approaching
    vehicles_detail.sort(key=lambda x: (
        0 if x['is_approaching'] else 1,
        x['eta_seconds'] or 99999,
    ))

    return {
        'stop_source_id': stop_source_id,
        'stop_index': target_idx,
        'route_source_id': route_src,
        'direction': direction,
        'data_source_id': ds_id,
        'total_stops': num_stops,
        'vehicles': vehicles_detail,
    }


# ===== GTFS Relay Endpoints =====


@router.get("/transit/gtfs/feeds/", auth=None)
@ratelimit(group='transit:gtfs_feeds', key='ip', rate='120/m')
def gtfs_relay_feeds(request):
    """List available GTFS feeds with relay URLs."""
    feeds = TransitDataSource.objects.filter(is_active=True).exclude(slug='')
    return [
        {
            "slug": ds.slug,
            "name": ds.name,
            "gtfs_static_url": f"/api/v1/geo/transit/gtfs/static/{ds.slug}/",
            "gtfs_rt_url": f"/api/v1/geo/transit/gtfs-rt/vehicle-positions/{ds.slug}/",
            **({"gtfs_rt_alerts_url": f"/api/v1/geo/transit/gtfs-rt/service-alerts/{ds.slug}/"} if ds.rt_alerts_url else {}),
            "last_imported_at": ds.last_imported_at.isoformat() if ds.last_imported_at else None,
        }
        for ds in feeds
    ]


@router.get("/transit/gtfs/static/{slug}/", auth=None)
@ratelimit(group='transit:gtfs_static', key='ip', rate='30/m')
def gtfs_static_download(request, slug: str):
    """Serve cached GTFS static ZIP for a data source."""
    import os
    from django.http import FileResponse

    ds = get_object_or_404(TransitDataSource, slug=slug, is_active=True)
    cache_path = os.path.join(settings.BASE_DIR, 'gtfs_cache', f'{ds.id}.zip')

    if not os.path.exists(cache_path):
        raise HttpError(404, "GTFS file not cached yet")

    return FileResponse(
        open(cache_path, 'rb'),
        content_type='application/zip',
        as_attachment=True,
        filename=f'{slug}.zip',
    )


@router.get("/transit/gtfs-rt/vehicle-positions/{slug}/", auth=None)
@ratelimit(group='transit:gtfs_rt', key='ip', rate='120/m')
def gtfs_rt_vehicle_positions(request, slug: str):
    """Serve GTFS-RT VehiclePositions protobuf (relay from Redis cache)."""
    import time as _time
    import redis as sync_redis
    from django.http import HttpResponse
    from google.transit import gtfs_realtime_pb2

    ds = get_object_or_404(TransitDataSource, slug=slug, is_active=True)
    ds_id = str(ds.id)

    # Check for cached protobuf (15s TTL)
    pb_cache_key = f'transit:rt:pb:{ds_id}'
    r = sync_redis.Redis(
        host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
        port=getattr(settings, 'REDIS_PORT', 6379),
    )

    cached = r.get(pb_cache_key)
    if cached:
        r.close()
        return HttpResponse(cached, content_type='application/x-protobuf')

    # Build protobuf from Redis vehicle data
    member_ids = r.smembers(f'transit:members:{ds_id}')

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = '2.0'
    feed.header.incrementality = gtfs_realtime_pb2.FeedHeader.FULL_DATASET
    feed.header.timestamp = int(_time.time())

    if member_ids:
        raw_values = r.hmget('transit:vdata', *[m.decode() if isinstance(m, bytes) else m for m in member_ids])
        status_map = {'INCOMING_AT': 0, 'STOPPED_AT': 1, 'IN_TRANSIT_TO': 2}

        for raw in raw_values:
            if not raw:
                continue
            try:
                v = json.loads(raw if isinstance(raw, str) else raw.decode())
            except (json.JSONDecodeError, TypeError):
                continue

            entity = feed.entity.add()
            vid = v.get('v', '')
            entity.id = vid
            vp = entity.vehicle
            vp.vehicle.id = vid
            vp.trip.route_id = v.get('r', '')
            vp.trip.direction_id = v.get('d', 0) or 0
            vp.position.latitude = v.get('lat', 0)
            vp.position.longitude = v.get('lon', 0)
            vp.position.bearing = v.get('b', 0) or 0
            vp.position.speed = (v.get('s', 0) or 0) / 3.6  # km/h → m/s
            vp.timestamp = v.get('t', 0)
            vp.stop_id = v.get('sid', '')
            vp.current_status = status_map.get(v.get('st', ''), 2)

    serialized = feed.SerializeToString()

    # Cache for 15 seconds
    r.setex(pb_cache_key, 15, serialized)
    r.close()

    return HttpResponse(serialized, content_type='application/x-protobuf')


@router.get("/transit/gtfs-rt/vehicle-positions/{slug}.json", auth=None)
@ratelimit(group='transit:gtfs_rt_json', key='ip', rate='120/m')
def gtfs_rt_vehicle_positions_json(request, slug: str):
    """GTFS-RT vehicle positions as JSON (convenience endpoint)."""
    import redis as sync_redis

    ds = get_object_or_404(TransitDataSource, slug=slug, is_active=True)
    ds_id = str(ds.id)

    r = sync_redis.Redis(
        host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
        port=getattr(settings, 'REDIS_PORT', 6379),
        decode_responses=True,
    )
    member_ids = r.smembers(f'transit:members:{ds_id}')
    vehicles = []

    if member_ids:
        raw_values = r.hmget('transit:vdata', *member_ids)
        for raw in raw_values:
            if raw:
                try:
                    vehicles.append(json.loads(raw))
                except (json.JSONDecodeError, TypeError):
                    pass

    r.close()
    return {"slug": slug, "name": ds.name, "vehicles": vehicles}


@router.get("/transit/gtfs-rt/service-alerts/{slug}/", auth=None)
@ratelimit(group='transit:gtfs_alerts', key='ip', rate='120/m')
def gtfs_rt_service_alerts(request, slug: str):
    """Serve GTFS-RT ServiceAlerts protobuf (relay from Redis cache)."""
    import time as _time
    import redis as sync_redis
    from django.http import HttpResponse
    from google.transit import gtfs_realtime_pb2

    ds = get_object_or_404(TransitDataSource, slug=slug, is_active=True)
    ds_id = str(ds.id)

    r = sync_redis.Redis(
        host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
        port=getattr(settings, 'REDIS_PORT', 6379),
    )

    # Relay raw protobuf if available (stored by fetch_transit_alerts daemon)
    cached_pb = r.get(f'transit:alerts:pb:{ds_id}')
    if cached_pb:
        r.close()
        return HttpResponse(cached_pb, content_type='application/x-protobuf')

    # No cached data — return empty feed
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = '2.0'
    feed.header.incrementality = gtfs_realtime_pb2.FeedHeader.FULL_DATASET
    feed.header.timestamp = int(_time.time())

    r.close()
    return HttpResponse(feed.SerializeToString(), content_type='application/x-protobuf')


@router.get("/transit/gtfs-rt/service-alerts/{slug}.json", auth=None)
@ratelimit(group='transit:gtfs_alerts_json', key='ip', rate='120/m')
def gtfs_rt_service_alerts_json(request, slug: str):
    """GTFS-RT service alerts as JSON."""
    import redis as sync_redis

    ds = get_object_or_404(TransitDataSource, slug=slug, is_active=True)
    ds_id = str(ds.id)

    r = sync_redis.Redis(
        host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
        port=getattr(settings, 'REDIS_PORT', 6379),
        decode_responses=True,
    )

    raw = r.get(f'transit:alerts:{ds_id}')
    r.close()

    alerts = json.loads(raw) if raw else []
    return {"slug": slug, "name": ds.name, "alerts": alerts}
