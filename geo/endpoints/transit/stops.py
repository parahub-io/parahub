"""
Stop endpoints: nearby list, stop detail by slug, stop schedule.
"""


from ninja.errors import HttpError
import logging
import orjson
from django.db import connection
from django.shortcuts import get_object_or_404
from django.db.models import Count
from django.http import HttpResponse

from geo.models import Stop, StopGroup, RouteStop, Place

from parahub.ratelimit import ratelimit

from .base import router
from .helpers import _grouped_pole_members, _interchange_modes_for_stops, _merged_route_badges, _route_mode_counts_combined, _routes_for_stops, _stop_directions_combined
from .schedule import _get_stop_schedule_data
from .schemas import TransitStopResponse

logger = logging.getLogger(__name__)

def _build_stop_group(stop, sibling_clusters):
    """Virtual-stop block for the stop page: the OTHER physical poles at this
    location, one row per pole. Co-located cross-operator rows are already merged
    into the page itself (see _build_stop_detail), so they are NOT repeated here.
    Each row's representative (most-served) member carries the nav slug + display;
    its cluster's lines are pooled into the mode counter. null when ungrouped."""
    if not stop.group_id:
        return None
    group = stop.group
    all_sibling_ids = [m.id for cl in sibling_clusters for m in cl]
    route_counts = {}
    if all_sibling_ids:
        route_counts = {
            r["stop_id"]: r["n"]
            for r in RouteStop.objects.filter(stop_id__in=all_sibling_ids)
            .values("stop_id").annotate(n=Count("route", distinct=True))
        }
    rows = []
    for cl in sibling_clusters:
        rep = max(cl, key=lambda m: route_counts.get(m.id, 0))
        cl_ids = [m.id for m in cl]
        agencies = []
        for m in cl:
            an = m.agency.name if m.agency else ""
            if an and an not in agencies:
                agencies.append(an)
        modes = _route_mode_counts_combined(cl_ids)
        rows.append({
            "id": rep.id,
            "slug": rep.slug,
            "place_slug": rep.place.slug if rep.place else "",
            "name": rep.name,
            "agency_name": " · ".join(agencies),
            "location_type": rep.location_type,
            "lat": rep.location.y,
            "lon": rep.location.x,
            "route_modes": modes,
            "directions": _stop_directions_combined(cl_ids),
        })
    # Most-served pole first (hubs above minor/night poles).
    rows.sort(key=lambda r: -sum(mc["count"] for mc in r["route_modes"]))
    return {
        "id": group.id,
        "name": group.name,
        "member_count": group.member_count,
        "lat": group.location.y,
        "lon": group.location.x,
        "stops": rows,
    }

def _build_stop_detail(stop):
    """Build TransitStopResponse from a Stop instance (shared by ULID and slug
    endpoints). Co-located cross-operator poles (the same physical boarding point)
    are merged: routes + directions union over them, so the rider sees every line
    they can board here — not just the feed whose slug they happened to open."""
    colocated, sibling_clusters = _grouped_pole_members(stop)
    colocated_ids = [m.id for m in colocated]
    routes = (
        RouteStop.objects.filter(stop_id__in=colocated_ids)
        .select_related("route", "route__place")
        .order_by("route__short_name", "route__source_id")
    )
    # Deduplicate by short_name: GTFS variants (2110_0/1/2) share the same display
    # name; secondary sort by source_id picks _0 (main path) first.
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
        tts_name=stop.tts_name,
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
        directions=_stop_directions_combined(colocated_ids),
        interchange_modes=_interchange_modes_for_stops([stop.id]).get(stop.id, []),
        group=_build_stop_group(stop, sibling_clusters),
    )

@router.get("/transit/stops/nearby/", auth=None)
@ratelimit(group='transit:nearby_stops', key='ip', rate='120/m')
def list_nearby_transit_stops(request, lat: float = None, lon: float = None, r: int = 500,
                              city: str = None, group: int = 0):
    """Find GTFS stops near a point. Raw SQL with batch route lookup (eliminates N+1).
    r = radius in meters (default 500, max 5000).
    If city slug is provided and lat/lon missing, uses city center + city radius.
    group=1 collapses grouped stops into one virtual-stop card per StopGroup
    (geometry = centroid, merged badges, full member list); default 0 keeps the
    flat physical list (StopPicker/rides consumers)."""
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
        # Fetch nearby stops (lt 2/3/4 = entrances/pathways — not rideable, hidden)
        cur.execute("""
            SELECT s.id, s.slug, s.name, s.source_id, s.location_type, s.agency_id,
                   ST_X(s.location::geometry), ST_Y(s.location::geometry),
                   COALESCE(p.slug, '') AS place_slug, s.group_id
            FROM geo_stop s
            LEFT JOIN geo_place p ON s.place_id = p.id
            WHERE ST_DWithin(s.location::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
              AND s.location_type <= 1
            ORDER BY s.location::geography <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
            LIMIT 100
        """, [lon, lat, r, lon, lat])
        stop_rows = cur.fetchall()

    if not stop_rows:
        body = orjson.dumps({'type': 'FeatureCollection', 'features': []})
        return HttpResponse(body, content_type='application/json')

    def stop_props(row, routes_by_stop):
        props = {
            'id': row[0], 'slug': row[1], 'place_slug': row[8],
            'name': row[2], 'source_id': row[3],
            'location_type': row[4], 'agency_id': row[5],
            'routes': routes_by_stop.get(row[0], []),
        }
        if row[9]:
            props['group_id'] = row[9]
        return props

    if not group:
        routes_by_stop = _routes_for_stops([row[0] for row in stop_rows])
        features = [
            {
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [row[6], row[7]]},
                'properties': stop_props(row, routes_by_stop),
            }
            for row in stop_rows
        ]
        body = orjson.dumps({'type': 'FeatureCollection', 'features': features})
        return HttpResponse(body, content_type='application/json')

    # group=1: one card per virtual stop. Rows are distance-ordered, so the first
    # member seen fixes the card position in the list (min member distance).
    group_ids = [row[9] for row in stop_rows if row[9]]
    groups = {g.id: g for g in StopGroup.objects.filter(id__in=group_ids)} if group_ids else {}
    members_by_group = {}
    if groups:
        with connection.cursor() as cur:
            # All members, including those outside the radius — the card is complete
            cur.execute("""
                SELECT s.id, s.slug, s.name, s.source_id, s.location_type, s.agency_id,
                       ST_X(s.location::geometry), ST_Y(s.location::geometry),
                       COALESCE(p.slug, '') AS place_slug, s.group_id
                FROM geo_stop s
                LEFT JOIN geo_place p ON s.place_id = p.id
                WHERE s.group_id = ANY(%s) AND s.location_type <= 1
                ORDER BY s.group_id, s.id
            """, [list(groups)])
            for row in cur.fetchall():
                members_by_group.setdefault(row[9], []).append(row)

    member_ids = [row[0] for rows in members_by_group.values() for row in rows]
    routes_by_stop = _routes_for_stops(set(member_ids) | {row[0] for row in stop_rows})
    # Group-aware interchange modes per emitted card (one representative pole per
    # group resolves the whole cluster's modes; ungrouped poles resolve their own).
    rep_ids = [
        (members_by_group[row[9]][0][0] if row[9] in groups and members_by_group.get(row[9]) else row[0])
        for row in stop_rows
    ]
    inter_map = _interchange_modes_for_stops(rep_ids)

    features = []
    seen_groups = set()
    for row in stop_rows:
        gid = row[9]
        if not gid or gid not in groups:
            props = stop_props(row, routes_by_stop)
            props['interchange_modes'] = inter_map.get(row[0], [])
            features.append({
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [row[6], row[7]]},
                'properties': props,
            })
            continue
        if gid in seen_groups:
            continue
        seen_groups.add(gid)
        g = groups[gid]
        members = members_by_group.get(gid, [])
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [g.location.x, g.location.y]},
            'properties': {
                'id': g.id, 'kind': 'virtual', 'name': g.name,
                'member_count': g.member_count,
                'interchange_modes': inter_map.get(members[0][0], []) if members else [],
                'routes': _merged_route_badges([routes_by_stop.get(m[0], []) for m in members]),
                'stops': [
                    {**stop_props(m, routes_by_stop),
                     'lat': m[7], 'lon': m[6]}
                    for m in members
                ],
            },
        })
    body = orjson.dumps({'type': 'FeatureCollection', 'features': features})
    return HttpResponse(body, content_type='application/json')

@router.get("/transit/stops/{city_slug}/{stop_slug}/", auth=None, response=TransitStopResponse)
@ratelimit(group='transit:stop_detail', key='ip', rate='120/m')
def get_transit_stop_by_slug(request, city_slug: str, stop_slug: str):
    """Stop detail by city/slug."""
    stop = get_object_or_404(Stop.objects.select_related("place", "agency", "group"), place__slug=city_slug, slug=stop_slug)
    return _build_stop_detail(stop)

@router.get("/transit/stops/{city_slug}/{stop_slug}/schedule/", auth=None)
@ratelimit(group='transit:stop_schedule', key='ip', rate='120/m')
def get_stop_schedule_by_slug(request, city_slug: str, stop_slug: str, date: str = None):
    """Stop schedule by city/slug."""
    stop = get_object_or_404(Stop.objects.select_related("place", "agency", "agency__data_source"), place__slug=city_slug, slug=stop_slug)
    return _get_stop_schedule_data(stop, date)
