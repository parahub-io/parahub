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
import time
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.shortcuts import get_object_or_404
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db.models import Count, Q
from django.db.models.functions import Length
from django.http import HttpResponse
from django.utils import timezone as dj_timezone
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from geo.models import (
    Agency, Stop, StopGroup, Route, RouteStop, StopTime, CalendarDate,
    TransitDataSource, Place, Trip, VehiclePositionHistory,
)

from parahub.ratelimit import ratelimit
from parahub.services.transit_eta import (
    parse_rstops, segment_infos, segment_averages,
    build_index_map, resolve_origin, cumulative_min_etas, zombie_keeps_eta,
)

logger = logging.getLogger(__name__)

router = Router(tags=["Geo / Transit"])


# ===== Helpers =====

def _place_descend_q(place, field='place'):
    """Q matching records whose place FK is `place` or any of its descendants.

    The Place hierarchy is a fixed 3-level tree (country → region → city), so
    two parent_place hops cover every descendant without materializing id lists.
    Needed because import assigns the smallest containing polygon: a region
    scope must also match records assigned to its cities.
    """
    return (
        Q(**{field: place})
        | Q(**{f'{field}__parent_place': place})
        | Q(**{f'{field}__parent_place__parent_place': place})
    )


def _place_stop_filter(place):
    """Return a Q filter for stops within a Place (cached FK, hierarchy-aware)."""
    return _place_descend_q(place)


def _agency_local_now(agency):
    """Current (date, "HH:MM:SS") in the agency's GTFS timezone.

    GTFS `departure_time` is wall-clock in the agency's declared timezone
    (agency.txt `agency_timezone`), but the server runs in UTC
    (settings.TIME_ZONE='UTC', USE_TZ=True). Comparing `departure_time`
    against a naive `datetime.now()` shifts "now" by the agency's UTC offset
    — "next departure" lands an hour early for Europe/Lisbon in summer (WEST),
    4-5h off for US feeds. Convert to the agency's zone so schedule windows
    line up with the operator's clock. Falls back to UTC if tz missing/invalid.
    """
    tzname = (getattr(agency, "timezone", "") or "").strip()
    try:
        tz = ZoneInfo(tzname) if tzname else ZoneInfo("UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    now_local = dj_timezone.now().astimezone(tz)
    return now_local.date(), now_local.strftime("%H:%M:%S")


def _place_route_filter(place):
    """Return a Q filter for routes within a Place.

    Matches the majority-place FK or any place the route passes through
    (`places` M2M — inter-city routes like CM 1723 Carnaxide→Lisboa would
    otherwise be invisible in their destination city), both hierarchy-aware.
    Callers must apply .distinct(): the M2M join can multiply rows.
    """
    return _place_descend_q(place) | _place_descend_q(place, 'places')


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


def _routes_for_stops(stop_ids, limit=10):
    """Batch variant of _routes_for_stop: {stop_id: [{short_name, route_color, route_type}]}."""
    if not stop_ids:
        return {}
    with connection.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (rs.stop_id, r.short_name)
                   rs.stop_id, r.short_name, r.route_color, r.route_type
            FROM geo_routestop rs
            JOIN geo_route r ON rs.route_id = r.id
            WHERE rs.stop_id = ANY(%s)
            ORDER BY rs.stop_id, r.short_name
        """, [list(stop_ids)])
        rows = cur.fetchall()
    result = {}
    for sid, short_name, color, rtype in rows:
        lst = result.setdefault(sid, [])
        if len(lst) < limit:
            lst.append({'short_name': short_name, 'route_color': color, 'route_type': rtype})
    return result


def _merged_route_badges(routes_lists, limit=10):
    """Union of member badge lists for a virtual stop card, deduped by short_name.
    Sorted by mode first (tram/metro/rail before bus) so the cap never drops a
    hub's headline line in favour of the tenth bus."""
    seen, merged = set(), []
    for routes in routes_lists:
        for r in routes:
            if r['short_name'] not in seen:
                seen.add(r['short_name'])
                merged.append(r)
    merged.sort(key=lambda r: (r['route_type'], r['short_name']))
    return merged[:limit]


# ── Line grouping (percursos) — single source of truth ──────────────────────
# A "line" groups path-variants that share (agency, line_id, short_name); the
# canonical/main variant is the lowest path_type. Two invariants every read
# site must agree on (search collapse, route-detail variants, future export):
#   1. Only feeds with a line_id grouping collapse. A line_id-less route always
#      stands alone — never merged with another route that happens to share a
#      short_name within the agency.
#   2. short_name must match too: CM path-variants share the line number
#      (2754_0/_1/_2 → "2754"), whereas operators like MBTA use line_id as a
#      loose route-family (line-Green = B/C/D/E branches + replacement
#      shuttles); short_name scoping keeps real percursos and drops that noise.
# See PK/gtfs-feed-quirks.md "Line grouping ext".
LINE_CANONICAL_ORDER = ("path_type", "source_id")  # first = canonical (main) variant


def line_key_fields(route_id, agency_id, line_id, short_name):
    """Line grouping key from raw fields — the single source of truth for the
    collapse rule. line_id-less routes get a unique standalone key (never
    collapsed). line_group_key() wraps this for Route instances; the discover
    collapse calls it on values_list rows (no full Route load per city)."""
    if not line_id:
        return ("_standalone", str(route_id))
    return (str(agency_id), line_id, short_name)


def line_group_key(route):
    """Stable grouping key for in-Python collapse of a route's line."""
    return line_key_fields(route.id, route.agency_id, route.line_id, route.short_name)


def line_siblings(route):
    """All path-variants (percursos) of a route's line, canonical-first.
    Caller guards on route.line_id (a line_id-less route has no variants)."""
    return list(
        Route.objects.filter(
            agency_id=route.agency_id, line_id=route.line_id, short_name=route.short_name
        )
        .select_related("place")
        .order_by(*LINE_CANONICAL_ORDER)
    )


def _build_route_detail(route):
    """Build TransitRouteDetail from a Route instance (shared by ULID and slug endpoints)."""

    def _stop_item(stop, sequence):
        return {
            "id": stop.id,
            "source_id": stop.source_id,
            "slug": stop.slug,
            "place_slug": stop.place.slug if stop.place else "",
            "name": stop.name,
            "lat": stop.location.y,
            "lon": stop.location.x,
            "sequence": sequence,
        }

    def _stop_list(direction_id):
        # A single route_id can bundle several stop patterns — night-tram
        # branches, short-turns, depot runs — that each restart stop_sequence
        # at 1. RouteStop dedups on (route, stop, direction), so unioning them
        # and ordering by `sequence` interleaves the branches into a physically
        # impossible list (the "ragged" route page, ~1/3 of all routes). One
        # real Trip is travel-ordered by construction, so render the most
        # complete pattern: the trip with the most stops in this direction
        # (same "longest representative" rule used for Route.geometry/RouteCache
        # shapes). Stops unique to a shorter branch aren't shown — surfacing
        # those is the percursos job (line_id grouping), a separate concern.
        rep = (
            Trip.objects.filter(route=route, direction_id=direction_id)
            .annotate(n_stops=Count("stop_times"))
            .order_by("-n_stops", "id")
            .first()
        )
        if rep is None:
            # No trip for this direction (legacy import without direction, or a
            # direction that only ever had RouteStops). Fall back to the deduped
            # union — interleaving is possible here but it's the best available.
            qs = (
                RouteStop.objects.filter(route=route, direction_id=direction_id)
                .select_related("stop", "stop__place")
                .order_by("sequence")
            )
            return [_stop_item(rs.stop, rs.sequence) for rs in qs]
        sts = (
            StopTime.objects.filter(trip=rep)
            .select_related("stop", "stop__place")
            .order_by("stop_sequence")
        )
        return [_stop_item(st.stop, st.stop_sequence) for st in sts]

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

    # Sibling path-variants (percursos) of the same line, canonical-first.
    # Grouping rule lives in line_siblings / line_group_key (single source of truth).
    variants = []
    canonical_slug = ""
    if route.line_id:
        siblings = line_siblings(route)
        # Which siblings run today? (feed-wide calendar, scoped by data source.)
        # Used only to dim a variant when OTHER variants run today and it doesn't —
        # if none run (holiday / no calendar) running_ids stays empty → no dimming.
        running_ids = set()
        live_source_ids = set()
        if len(siblings) > 1:
            # Calendar "today" in the agency's timezone, not server UTC — else
            # near midnight the wrong day's calendar dims a running variant.
            _today, _ = _agency_local_now(route.agency)
            ds_id = route.agency.data_source_id
            cal_scope = Q(agency__data_source_id=ds_id) if ds_id else Q(agency_id=route.agency_id)
            active, removed = set(), set()
            for sid, ex in CalendarDate.objects.filter(
                cal_scope, date=_today, exception_type__in=[1, 2]
            ).values_list("service_id", "exception_type"):
                (active if ex == 1 else removed).add(sid)
            active -= removed
            if active:
                running_ids = set(
                    Trip.objects.filter(route__in=siblings, service_id__in=active)
                    .values_list("route_id", flat=True).distinct()
                )
            # Live overrides static: a variant the calendar marks "off" but that has a
            # vehicle reporting in the last 3 min IS running (observed GPS > static).
            # Freshness is essential — CM's /v2/vehicles retains a parked bus's last
            # fix for hours, so without the cutoff a yesterday-evening ghost would flip
            # a non-running feeder to "running". Only read RT when a sibling would
            # otherwise be dimmed (keeps the common path free of a Redis hit).
            if running_ids and any(s.id not in running_ids for s in siblings):
                raw = cache.get(f'transit:rt:{ds_id}') if ds_id else None
                if raw:
                    _cutoff = datetime.now().timestamp() - 180
                    live_source_ids = {
                        v.get('r') for v in json.loads(raw) if v.get('t', 0) >= _cutoff
                    }
        for sib in siblings:
            sib_dirs = []
            for d_id in [0, 1]:
                t = Trip.objects.filter(route=sib, direction_id=d_id).first()
                if t:
                    sib_dirs.append(TransitRouteDirection(direction_id=d_id, headsign=t.headsign))
            variants.append(TransitRouteVariant(
                slug=sib.slug,
                place_slug=sib.place.slug if sib.place else "",
                source_id=sib.source_id,
                long_name=sib.long_name,
                path_type=sib.path_type,
                directions=sib_dirs,
                is_current=(sib.id == route.id),
                runs_today=(
                    True if not running_ids
                    else (sib.id in running_ids or sib.source_id in live_source_ids)
                ),
            ))
        if variants:
            canonical_slug = variants[0].slug  # lowest path_type

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
        agency_timezone=route.agency.timezone if route.agency else "",
        line_id=route.line_id,
        line_long_name=route.line_long_name,
        canonical_slug=canonical_slug,
        variants=variants,
        stops=stops_dir0,
        stops_dir1=_stop_list(1),
        directions=directions,
        places=route_places,
        geometry=geojson,
    )


def _stop_directions_bulk(stop_ids, limit=3):
    """{stop_id: [top destination names]} — the busiest trip headsigns served
    from each pole, ranked by departure count. A direction label so same-name,
    opposite-direction poles (the two sides of a road, grouped into one
    StopGroup) are tellable apart: «R 1 Maio 109 → Loures» vs «→ Póvoa, Alverca».
    Near-duplicate feed spellings ('Santo Antão do Tojal' vs the typo
    'Santo Antão  doTojal') merge on a whitespace/case-insensitive key, keeping
    the busiest spelling for display and summing their counts for the ranking."""
    stop_ids = list(stop_ids)
    if not stop_ids:
        return {}
    rows = (
        StopTime.objects.filter(stop_id__in=stop_ids)
        .exclude(trip__headsign="")
        .values("stop_id", "trip__headsign")
        .annotate(n=Count("*"))
    )
    per_stop: dict = {}
    for r in rows:
        bucket = per_stop.setdefault(r["stop_id"], {})
        hs = r["trip__headsign"]
        n = r["n"]
        key = "".join(hs.split()).casefold()
        cur = bucket.get(key)
        if cur is None:
            bucket[key] = {"name": hs, "best": n, "total": n}
        else:
            cur["total"] += n
            if n > cur["best"]:
                cur["best"], cur["name"] = n, hs
    return {
        sid: [m["name"] for m in sorted(b.values(), key=lambda x: -x["total"])[:limit]]
        for sid, b in per_stop.items()
    }


def _stop_directions(stop, limit=3):
    """Direction label for a single pole. See _stop_directions_bulk."""
    return _stop_directions_bulk([stop.id], limit).get(stop.id, [])


def _build_stop_group(stop):
    """Virtual-stop block for the stop detail page: all members incl. self."""
    if not stop.group_id:
        return None
    group = stop.group
    members = list(
        Stop.objects.filter(group_id=stop.group_id, location_type__lte=1)
        .select_related("place", "agency")
        .order_by("id")
    )
    member_ids = [m.id for m in members]
    badges = _routes_for_stops(member_ids)
    directions = _stop_directions_bulk(member_ids)
    return {
        "id": group.id,
        "name": group.name,
        "member_count": group.member_count,
        "lat": group.location.y,
        "lon": group.location.x,
        "stops": [
            {
                "id": m.id,
                "slug": m.slug,
                "place_slug": m.place.slug if m.place else "",
                "name": m.name,
                "agency_name": m.agency.name if m.agency else "",
                "location_type": m.location_type,
                "lat": m.location.y,
                "lon": m.location.x,
                "routes": badges.get(m.id, []),
                "directions": directions.get(m.id, []),
            }
            for m in members
        ],
    }


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
        directions=_stop_directions(stop),
        group=_build_stop_group(stop),
    )


SECONDS_PER_DAY = 86400


def _secs_to_hhmm(secs):
    """Wall-clock HH:MM from GTFS seconds-since-service-midnight (may exceed
    86400 for night service: 91200 → '01:20')."""
    secs %= SECONDS_PER_DAY
    return f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}"


def _secs_to_hhmmss(secs):
    secs %= SECONDS_PER_DAY
    return f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"


def _time_to_secs(t):
    """Seconds since midnight from a datetime.time or a 'HH:MM:SS' string
    (_agency_local_now returns the latter; StopTime.departure_time the former)."""
    if isinstance(t, str):
        parts = (t.split(":") + ["0", "0"])[:3]
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return t.hour * 3600 + t.minute * 60 + t.second


def _dep_secs(departure_secs, departure_time):
    """Effective extended departure seconds. Uses the unwrapped `departure_secs`
    when present; falls back to the %24 `departure_time` for feeds imported
    before that field existed (night service stays wrapped = old behaviour,
    until the feed is re-imported). See StopTime.departure_secs."""
    return departure_secs if departure_secs is not None else _time_to_secs(departure_time)


def _active_services_window(agency, query_date):
    """(today_services, yesterday_services) active on query_date and the day
    before, in ONE query. Calendar is feed-wide → scope by data source, not
    agency (multi-agency feeds, e.g. CM's 4). Yesterday is needed because a
    night trip stored at 25:20 belongs to the PREVIOUS service date but runs
    in query_date's early morning — without it, a night route checked at 02:00
    shows tonight's distant departures instead of the tram arriving now."""
    ds_id = agency.data_source_id
    scope = Q(agency__data_source_id=ds_id) if ds_id else Q(agency_id=agency.id)
    yest = query_date - timedelta(days=1)
    add = {query_date: set(), yest: set()}
    rem = {query_date: set(), yest: set()}
    for sid, exc, d in CalendarDate.objects.filter(
        scope, date__in=[query_date, yest], exception_type__in=[1, 2]
    ).values_list("service_id", "exception_type", "date"):
        (add if exc == 1 else rem)[d].add(sid)
    return add[query_date] - rem[query_date], add[yest] - rem[yest]


def _timeline_positions(svc_id, dep_secs, today_services, yest_services, now_secs):
    """Upcoming 'query-date 00:00'-relative positions for one departure. A
    service active on query_date contributes `dep_secs`; one active the day
    before contributes `dep_secs - 86400` (so only its extended >24:00 trips
    can still be upcoming). Returns the positions ≥ now_secs (0, 1 or 2).
    Display time for any position = position % 86400 = wall clock."""
    out = []
    if svc_id in today_services and dep_secs >= now_secs:
        out.append(dep_secs)
    if yest_services and svc_id in yest_services:
        p = dep_secs - SECONDS_PER_DAY
        if p >= now_secs:
            out.append(p)
    return out


def _get_stop_schedule_data(stop, date_param=None):
    """Schedule data for a stop."""
    if date_param:
        try:
            query_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            raise HttpError(400, "Invalid date format. Use YYYY-MM-DD")
        now_secs = 0  # explicit date → whole-day view
    else:
        # GTFS departure_time is wall-clock in the agency's timezone; the server
        # is UTC. Compute "now" in the agency's zone so departures don't shift by
        # the UTC offset (see _agency_local_now).
        query_date, _now_time = _agency_local_now(stop.agency)
        now_secs = _time_to_secs(_now_time)

    now_dt = datetime.now()

    # Active services for query_date + the day before (a night trip stored at
    # 24:00+ belongs to the previous service date but runs in today's small
    # hours). Calendar is feed-wide → scoped by data source (see helper).
    today_services, yest_services = _active_services_window(stop.agency, query_date)

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

    if not today_services and not yest_services:
        return {"stop_id": stop.id, "stop_name": stop.name, "date": str(query_date), "departures": [], "live_vehicles": live_vehicles}

    # Wrap-aware upcoming departures: pull this stop's stop_times for both service
    # dates, compute each one's timeline position (>= now), sort chronologically,
    # keep the next 30. Night departures (24:00+) thus sort and display in real
    # order across midnight instead of being dropped by a naive >= now filter.
    candidates = []  # (position_secs, StopTime)
    for st in (
        StopTime.objects.filter(
            stop=stop,
            trip__service_id__in=(today_services | yest_services),
        ).select_related("trip__route__place")
    ):
        eff = _dep_secs(st.departure_secs, st.departure_time)
        for pos in _timeline_positions(st.trip.service_id, eff, today_services, yest_services, now_secs):
            candidates.append((pos, st))
    candidates.sort(key=lambda c: c[0])
    departures = candidates[:30]

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
                "departure_time": _secs_to_hhmmss(pos),
                "route_short_name": st.trip.route.short_name,
                "route_long_name": st.trip.route.long_name,
                "route_color": st.trip.route.route_color,
                "route_type": st.trip.route.route_type,
                "route_source_id": st.trip.route.source_id,
                "route_slug": st.trip.route.slug,
                "route_place_slug": st.trip.route.place.slug if st.trip.route.place else "",
                "headsign": st.trip.headsign,
                "direction_id": st.trip.direction_id if st.trip.direction_id is not None else 0,
                "trip_id": st.trip.id,
                "service_id": st.trip.service_id,
            }
            for pos, st in departures
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

class TransitRouteVariant(BaseModel):
    """A sibling path-variant of the same line (CM percurso)."""
    slug: str = ""
    place_slug: str = ""
    source_id: str = ""
    long_name: str = ""
    path_type: int = 0
    directions: list[TransitRouteDirection] = []
    is_current: bool = False
    runs_today: bool = True  # False only when other variants run today and this one doesn't

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
    agency_timezone: str = ""  # GTFS agency tz (Europe/Lisbon …) — frontend renders live ETA/now in stop's zone, not browser's
    # Line grouping (CM ext): multiple variants share line_id; canonical = lowest path_type.
    line_id: str = ""
    line_long_name: str = ""
    canonical_slug: str = ""  # slug of the canonical (lowest path_type) variant; empty if single-variant
    variants: list[TransitRouteVariant] = []  # all path-variants of this line (incl. current)
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
    # Unabbreviated GTFS tts_stop_name (driver-mode TTS, screen-reader aria-label);
    # "" when the feed omits it. Not shown as visible text — name stays the display label.
    tts_name: str = ""
    source_id: str
    lat: float
    lon: float
    location_type: int
    agency_id: str
    data_source_id: str = ""
    routes: list = []
    # Top destinations served from THIS pole (busiest trip headsigns) — the
    # direction label that disambiguates same-name opposite-direction poles.
    directions: list = []
    # Virtual stop this physical stop belongs to: {id, name, member_count, lat,
    # lon, stops: [member dicts incl. self]} — null when ungrouped
    group: Optional[Dict] = None


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

    # Discovery pools = all candidate stop ids + canonical route ids for the
    # place. They change only on GTFS import, but the per-place scan is expensive
    # (full stop table), so cache them per place. random.sample stays per-request
    # so every visit still gets fresh picks from the full pool. TTL bounds how
    # long a newly-imported stop takes to become discoverable (~1h).
    pool_key = f"transit:discover:pool:{place.id}"
    _pool = cache.get(pool_key)
    if _pool is not None:
        _pool = json.loads(_pool)
        stop_ids, route_ids = _pool["stops"], _pool["routes"]
    else:
        # Descendant place ids as a subquery (place FK + 2 hierarchy hops). The
        # OR-over-joins form (_place_stop_filter) makes PG sort the entire stop
        # table (~1.1s); the IN-subquery uses the place_id index (~0.3s). Same
        # result set (verified). Route filter keeps the join form — routes are a
        # small table and the subquery form plans far worse there.
        descend_ids = Place.objects.filter(
            Q(id=place.id) | Q(parent_place_id=place.id)
            | Q(parent_place__parent_place_id=place.id)
        ).values('id')
        stop_ids = list(
            Stop.objects.filter(place_id__in=descend_ids).values_list('id', flat=True)
        )
        # Collapse each line's path-variants to its canonical representative before
        # sampling, so a discovery link lands on the main variant (lowest path_type,
        # then source_id) and never a minor feeder. Same canonical definition as the
        # search collapse and route-detail's canonical_slug (LINE_CANONICAL_ORDER +
        # line_key_fields). distinct() because _place_route_filter joins the places
        # M2M; path_type/source_id are in the select so SELECT DISTINCT + ORDER BY
        # is valid, and global (path_type, source_id) order makes the first row seen
        # per line its canonical one.
        canonical_by_line: dict = {}
        for rid, agency_id, line_id, short_name, _pt, _sid in (
            Route.objects.filter(_place_route_filter(place))
            .order_by(*LINE_CANONICAL_ORDER)
            .values_list("id", "agency_id", "line_id", "short_name", "path_type", "source_id")
            .distinct()
        ):
            canonical_by_line.setdefault(line_key_fields(rid, agency_id, line_id, short_name), rid)
        route_ids = list(canonical_by_line.values())
        cache.set(pool_key, json.dumps({"stops": stop_ids, "routes": route_ids}), 3600)

    stops_qs = Stop.objects.filter(
        id__in=random.sample(stop_ids, min(5, len(stop_ids)))
    ).select_related("place")
    routes_qs = Route.objects.filter(
        id__in=random.sample(route_ids, min(5, len(route_ids)))
    ).select_related("place")

    # place_slug must be the record's own place, not the queried one: detail
    # pages resolve by the record's place slug, and a hierarchy-scoped query
    # (region) returns records assigned to child cities.
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

    stops_qs = Stop.objects.filter(name__icontains=q, location_type__lte=1)
    routes_qs = Route.objects.filter(
        Q(short_name__icontains=q) | Q(long_name__icontains=q)
    )

    if city:
        place = Place.objects.filter(slug=city).first()
        if place:
            stops_qs = stops_qs.filter(_place_stop_filter(place))
            routes_qs = routes_qs.filter(_place_route_filter(place))

    # Wider window before the virtual-stop collapse below (direction poles and
    # cross-feed duplicates fold into one result), capped to 20 after.
    # Shortest names first ≈ most exact match («Alameda» hub above
    # «Alameda Silva Porto (Supermercado)»); id tie-break keeps it deterministic.
    stops_qs = stops_qs.select_related("place", "group").order_by(Length("name"), "id")[:60]
    # Canonical-first (path_type asc) so each line's main variant is the kept
    # representative when path-variants get collapsed below. distinct() because
    # _place_route_filter joins the places M2M.
    routes_qs = routes_qs.select_related("place").order_by("path_type", "id").distinct()[:100]

    # Collapse grouped stops: one result per StopGroup (same pattern as the route
    # line collapse below). The first matched member carries the navigation slug;
    # name/coords come from the virtual stop, badges merge across matched members.
    stops = []
    stop_by_group: dict = {}
    for s in stops_qs:
        badges = _routes_for_stop(s)
        if s.group_id and s.group:
            existing = stop_by_group.get(s.group_id)
            if existing is not None:
                existing["routes"] = _merged_route_badges([existing["routes"], badges])
                continue
            entry = {
                "id": s.id,
                "slug": s.slug,
                "place_slug": s.place.slug if s.place else "",
                "name": s.group.name,
                "lat": s.group.location.y,
                "lon": s.group.location.x,
                "location_type": s.location_type,
                "group_id": s.group_id,
                "member_count": s.group.member_count,
                "routes": badges,
            }
            stop_by_group[s.group_id] = entry
            stops.append(entry)
        else:
            stops.append({
                "id": s.id,
                "slug": s.slug,
                "place_slug": s.place.slug if s.place else "",
                "name": s.name,
                "lat": s.location.y,
                "lon": s.location.x,
                "location_type": s.location_type,
                "member_count": 1,
                "routes": badges,
            })
    stops = stops[:20]

    # Direction label per shown result (its navigation-target pole) — one query.
    dir_map = _stop_directions_bulk([e["id"] for e in stops])
    for e in stops:
        e["directions"] = dir_map.get(e["id"], [])

    # Collapse path-variants (percursos) into one result, keeping the canonical/main
    # route (lowest path_type, seen first — routes_qs is path_type-ascending). Grouping
    # rule (incl. why line_id-less routes stay distinct) lives in line_group_key.
    collapsed: dict = {}
    for r in routes_qs:
        key = line_group_key(r)
        existing = collapsed.get(key)
        if existing is not None:
            existing["variant_count"] += 1
            continue
        collapsed[key] = {
            "id": r.id,
            "slug": r.slug,
            "place_slug": r.place.slug if r.place else "",
            "short_name": r.short_name,
            "long_name": r.long_name,
            "route_type": r.route_type,
            "route_color": r.route_color,
            "route_text_color": r.route_text_color,
            "agency_id": str(r.agency_id),
            "variant_count": 1,
        }
    routes = sorted(collapsed.values(), key=lambda x: x["short_name"])[:20]

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
    """Live vehicle positions from Redis cache (GTFS-RT + reconstructed metro)."""
    # Feeds that publish live vehicles: GPS feeds (rt_vehicles_url set) OR
    # rail/metro feeds whose positions are reconstructed from an arrivals API
    # (rt_kind='arrivals', empty rt_vehicles_url). Both write transit:rt:{ds_id}.
    qs = TransitDataSource.objects.filter(is_active=True).filter(
        ~Q(rt_vehicles_url='') | Q(rt_kind='arrivals')
    )
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

    # Pre-filter vehicles with valid coordinates (and bbox if provided).
    # Freshness cutoff: same 180s convention as the WS map feed and route-page
    # reads — stale parked-bus fixes (CM retains them for hours) stay in Redis
    # for diagnostics but are never served for display.
    cutoff = datetime.now().timestamp() - 180
    filtered = []
    for v in all_vehicles:
        if v.get('t', 0) < cutoff:
            continue
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
                'bearing': v.get('b'),
                'has_bearing': 1 if isinstance(v.get('b'), (int, float)) else 0,
                'speed': v.get('s', 0),
                'route_id': v.get('r', ''),
                'route_color': v.get('rc') or '3b82f6',
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

    # location_type 2/3/4 (entrances, pathway nodes, boarding areas) are not
    # rideable stops — display surfaces show lt <= 1 only.
    conditions = ["s.location IS NOT NULL", "s.location_type <= 1"]
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
                   ST_X(s.location::geometry), ST_Y(s.location::geometry), s.group_id
            FROM geo_stop s
            WHERE {where}
            LIMIT 5000
        """, params)
        rows = cur.fetchall()

    features = []
    for r in rows:
        props = {
            'id': r[0], 'name': r[1],
            'source_id': r[2], 'location_type': r[3],
        }
        if r[6]:
            # key omitted (not null) when ungrouped — map layers filter on ['has', 'group_id']
            props['group_id'] = r[6]
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [r[4], r[5]]},
            'properties': props,
        })

    # Virtual stops (StopGroup) ride in the same response; the client renders them
    # below z17 and switches to physical poles above. Skipped for agency-scoped
    # calls (operations view) — groups span agencies.
    if not agency_id:
        g_conditions = []
        g_params = []
        if parsed_bbox:
            west, south, east, north = parsed_bbox
            g_conditions.append("g.location && ST_MakeEnvelope(%s, %s, %s, %s, 4326)::geography")
            g_params.extend([west, south, east, north])
        g_where = ("WHERE " + " AND ".join(g_conditions)) if g_conditions else ""
        with connection.cursor() as cur:
            cur.execute(f"""
                SELECT g.id, g.name, g.member_count,
                       ST_X(g.location::geometry), ST_Y(g.location::geometry)
                FROM geo_stopgroup g
                {g_where}
                LIMIT 5000
            """, g_params)
            for g in cur.fetchall():
                features.append({
                    'type': 'Feature',
                    'geometry': {'type': 'Point', 'coordinates': [g[3], g[4]]},
                    'properties': {
                        'id': g[0], 'name': g[1], 'kind': 'virtual',
                        'member_count': g[2],
                    },
                })

    body = orjson.dumps({'type': 'FeatureCollection', 'features': features})
    cache.set(cache_key, body, 60)  # 60s TTL — short enough for GTFS imports
    return HttpResponse(body, content_type='application/json')


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

    features = []
    seen_groups = set()
    for row in stop_rows:
        gid = row[9]
        if not gid or gid not in groups:
            features.append({
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [row[6], row[7]]},
                'properties': stop_props(row, routes_by_stop),
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
    route = get_object_or_404(
        Route.objects.select_related("agency", "place"),
        place__slug=city_slug, slug=route_slug,
    )
    # GTFS departure_time is wall-clock in the agency's timezone; the server is
    # UTC. Compare "now" in the agency's zone so "next departure" doesn't shift
    # by the UTC offset (see _agency_local_now).
    query_date, now_time = _agency_local_now(route.agency)

    # Service-day window: query_date + the day before. Night trips stored at
    # 24:00+ belong to the PREVIOUS service date but run in today's small hours,
    # so a night route checked at 02:00 must see yesterday's still-running trams,
    # not only tonight's distant ones. (See _active_services_window.)
    now_secs = _time_to_secs(now_time)

    # Output is minute-resolution and static GTFS is stable within a day, so the
    # result only changes when the agency-local minute rolls over. Memoize per
    # (route, agency-local minute): all viewers polling within the same minute
    # share one StopTime scan instead of each client re-scanning every 60s. The
    # key embeds the date+minute, so the next minute is a fresh miss and a daily
    # GTFS re-import surfaces then; TTL expires at the minute boundary. Live
    # ETA/RT is unaffected (separate WS path).
    sched_cache_key = f"transit:schedule:{route.id}:{query_date.isoformat()}:{now_secs // 60}"
    _cached = cache.get(sched_cache_key)
    if _cached is not None:
        return json.loads(_cached)
    sched_ttl = max(5, 60 - now_secs % 60)

    today_services, yest_services = _active_services_window(route.agency, query_date)

    empty = {"schedule": {"0": {}, "1": {}}, "schedule_next": {"0": {}, "1": {}}, "first_departure": {}, "is_night": False, "variants_profile": {}}
    if not today_services and not yest_services:
        cache.set(sched_cache_key, json.dumps(empty), sched_ttl)
        return empty

    all_services = today_services | yest_services
    rows = StopTime.objects.filter(
        trip__route=route,
        trip__service_id__in=all_services,
    ).values_list(
        "stop__source_id", "trip__direction_id", "trip__service_id",
        "departure_secs", "departure_time", "stop_sequence",
    )

    # One pass: per-direction next departure per stop (wrap-aware), the line
    # origin's next departure (seq==1), and whether the route runs past midnight.
    sched = {0: {}, 1: {}}       # src -> soonest upcoming departure position
    sched2 = {0: {}, 1: {}}      # src -> 2nd-soonest = the FOLLOWING trip's arrival
    first_up = {0: None, 1: None}    # min upcoming origin position
    first_any = {0: None, 1: None}   # min origin departure secs (next-cycle fallback)
    max_secs = -1
    for src, dir_id, svc, dsecs, dtime, seq in rows:
        if dir_id not in (0, 1):
            continue
        eff = _dep_secs(dsecs, dtime)
        if eff > max_secs:
            max_secs = eff
        positions = _timeline_positions(svc, eff, today_services, yest_services, now_secs)
        # Keep the two smallest upcoming positions per stop. Each position is a
        # distinct trip (a trip visits a stop once per service-day), so the
        # 2nd-smallest is the FOLLOWING trip's arrival here — what the route page
        # shows on a stop a live bus has already served (instead of going blank).
        # See scheduledTimeFor() / schedule_next on the frontend.
        for p in positions:
            p0 = sched[dir_id].get(src)
            if p0 is None or p < p0:
                if p0 is not None:
                    sched2[dir_id][src] = p0
                sched[dir_id][src] = p
            elif p != p0:
                p1 = sched2[dir_id].get(src)
                if p1 is None or p < p1:
                    sched2[dir_id][src] = p
        if positions:
            pmin = min(positions)
            if seq == 1 and (first_up[dir_id] is None or pmin < first_up[dir_id]):
                first_up[dir_id] = pmin
        # Next-cycle fallback (shown when nothing upcoming): today's earliest
        # origin departure only — not yesterday's, which already ran.
        if seq == 1 and svc in today_services and (first_any[dir_id] is None or eff < first_any[dir_id]):
            first_any[dir_id] = eff

    is_night = max_secs >= SECONDS_PER_DAY

    # Per-variant departure-hour profile for the variants dropdown strips
    # (slug → sorted wall-clock hours with departures today). One query for the
    # whole line; skipped entirely for single-variant routes.
    variants_profile = {}
    if route.line_id:
        siblings = line_siblings(route)
        if len(siblings) > 1:
            slug_by_id = {s.id: s.slug for s in siblings}
            hours = {}
            for rid, dsecs, dtime in StopTime.objects.filter(
                trip__route__in=siblings,
                trip__service_id__in=today_services,
                stop_sequence=1,
            ).values_list("trip__route_id", "departure_secs", "departure_time"):
                hours.setdefault(slug_by_id[rid], set()).add((_dep_secs(dsecs, dtime) // 3600) % 24)
            variants_profile = {slug: sorted(hs) for slug, hs in hours.items()}

    result = {
        "schedule": {str(d): {src: _secs_to_hhmm(p) for src, p in sched[d].items()} for d in (0, 1)},
        "schedule_next": {str(d): {src: _secs_to_hhmm(p) for src, p in sched2[d].items()} for d in (0, 1)},
        "first_departure": {
            str(d): _secs_to_hhmm(first_up[d] if first_up[d] is not None else first_any[d])
            for d in (0, 1)
            if first_up[d] is not None or first_any[d] is not None
        },
        "is_night": is_night,
        "variants_profile": variants_profile,
    }
    cache.set(sched_cache_key, json.dumps(result), sched_ttl)
    return result


@router.get("/transit/routes/{city_slug}/{route_slug}/timetable/", auth=None)
@ratelimit(group='transit:route_timetable', key='ip', rate='60/m')
def get_route_timetable(request, city_slug: str, route_slug: str):
    """Line timetable for the next 7 days (agency-local today..+6) in one
    payload — the modal switches days client-side with no extra requests.
    Per day: every departure from the first stop of each direction, across
    ALL path-variants of the line (variant marked per departure). Line-level —
    the same timetable regardless of which variant's page anchors it."""
    route = get_object_or_404(
        Route.objects.select_related("agency", "place"),
        place__slug=city_slug, slug=route_slug,
    )

    today_local, _ = _agency_local_now(route.agency)
    dates = [today_local + timedelta(days=i) for i in range(7)]

    # Static GTFS changes only on feed re-import; the entry expires at
    # agency-local midnight so the 7-day window always starts at "today".
    cache_key = f"transit:timetable7:{route.id}:{today_local.isoformat()}"
    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)

    siblings = line_siblings(route) if route.line_id else [route]

    # Feed-wide calendar scope (multi-agency feeds — same rule as /schedule/),
    # all 7 dates in one query.
    _ds_id = route.agency.data_source_id
    _cal_scope = Q(agency__data_source_id=_ds_id) if _ds_id else Q(agency_id=route.agency_id)
    active_by_date = {d: set() for d in dates}
    removed_by_date = {d: set() for d in dates}
    for service_id, exc_type, cal_date in CalendarDate.objects.filter(
        _cal_scope, date__in=dates, exception_type__in=[1, 2]
    ).values_list("service_id", "exception_type", "date"):
        (active_by_date if exc_type == 1 else removed_by_date)[cal_date].add(service_id)
    for d in dates:
        active_by_date[d] -= removed_by_date[d]

    variants = [
        {
            "slug": s.slug,
            "place_slug": s.place.slug if s.place else "",
            "long_name": s.long_name,
            "is_current": s.id == route.id,
        }
        for s in siblings
    ]
    sib_index = {s.id: i for i, s in enumerate(siblings)}

    # One stop-times query over the union of the week's services; per-day
    # filtering happens in Python (a trip's service repeats across dates).
    all_services = set().union(*active_by_date.values())
    rows = []
    if all_services:
        rows = list(
            StopTime.objects.filter(
                trip__route__in=siblings,
                trip__service_id__in=all_services,
                stop_sequence=1,
            )
            .values_list(
                "trip__route_id", "trip__direction_id", "trip__headsign",
                "trip__service_id", "departure_secs", "departure_time",
            )
        )

    days = []
    for day in dates:
        active = active_by_date[day]
        headsigns = {}
        departures = {0: [], 1: []}
        # Direction header = headsign of the most canonical variant serving it
        # (lowest sib_index) — an edge-of-day variant's terminus must not label
        # the whole direction.
        headsign_rank = {}
        # Dedup overlapping services: when a public holiday falls on a Saturday/
        # weekday that has its own service, some feeds ADD the holiday service
        # without REMOVEing the regular one (Carris Lisboa, Santo António
        # 13-06-2026) — both carry identical trips, doubling every departure.
        # Collapse by (time, variant); distinct variants at the same minute
        # (different si) are kept — they're marked apart by superscript.
        seen = {0: set(), 1: set()}
        for route_id, dir_id, headsign, service_id, dsecs, dep in rows:
            if service_id not in active:
                continue
            d = dir_id if dir_id in (0, 1) else 0
            si = sib_index[route_id]
            if headsign and si < headsign_rank.get(d, len(siblings)):
                headsign_rank[d] = si
                headsigns[d] = headsign
            secs = _dep_secs(dsecs, dep)
            dep_str = _secs_to_hhmm(secs)
            if (dep_str, si) in seen[d]:
                continue
            seen[d].add((dep_str, si))
            departures[d].append((secs, dep_str, si))
        for d in (0, 1):
            # Sort by real extended seconds so night departures (24:00+) order
            # after the evening ones instead of jumping to the top as 00:xx.
            departures[d].sort(key=lambda x: x[0])
        days.append({
            "date": day.isoformat(),
            "is_today": day == today_local,
            "directions": [
                {"direction_id": d, "headsign": headsigns.get(d, ""),
                 "departures": [{"t": t, "v": si} for _s, t, si in departures[d]]}
                for d in (0, 1)
                if departures[d]
            ],
        })

    result = {"variants": variants, "days": days}

    # TTL: until agency-local midnight (max 24h) — keeps "today" honest and lets
    # daily GTFS re-imports surface within a day without explicit invalidation.
    tzname = (getattr(route.agency, "timezone", "") or "").strip()
    try:
        tz = ZoneInfo(tzname) if tzname else ZoneInfo("UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    now_local = dj_timezone.now().astimezone(tz)
    ttl = max(300, 86400 - (now_local.hour * 3600 + now_local.minute * 60 + now_local.second))
    cache.set(cache_key, json.dumps(result), ttl)
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
    # Only vehicles seen in the last 3 min — CM's /v2/vehicles retains a parked bus's
    # last fix for hours, which would otherwise render a stale "vehicle here" marker
    # (mirrors the stop-schedule live_vehicles cutoff).
    cutoff = datetime.now().timestamp() - 180
    stop_ids = list({
        v['sid'] for v in vehicles
        if v.get('r') == route.source_id and v.get('sid') and v.get('t', 0) >= cutoff
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
    # Key: transit:rstops:{route_src}:{dir} → [[source_id, lat, lon, sched_off], ...]
    route_seqs = {}     # (route_src, dir) → [source_id, ...]
    route_sched = {}    # (route_src, dir) → cumulative scheduled offsets
    route_idxmap = {}   # (route_src, dir) → {source_id: index}
    stop_target_idx = {}  # (route_src, dir) → index of target stop in sequence

    pipe = r.pipeline(transaction=False)
    rd_list = list(route_dir_set)
    for route_src, dir_id in rd_list:
        pipe.get(f'transit:rstops:{route_src}:{dir_id}')
    seq_results = pipe.execute()

    for (route_src, dir_id), raw in zip(rd_list, seq_results):
        parsed = parse_rstops(raw)
        if not parsed:
            continue
        source_ids, _coords, sched = parsed
        if stop_src in source_ids:
            route_seqs[(route_src, dir_id)] = source_ids
            route_sched[(route_src, dir_id)] = sched
            route_idxmap[(route_src, dir_id)] = build_index_map(source_ids)
            stop_target_idx[(route_src, dir_id)] = source_ids.index(stop_src)

    if not route_seqs:
        r.close()
        return {"stop": stop_src, "stop_name": stop.name, "vehicles": []}

    # Per-route segment model (observed avg / scheduled prior / default), memoized
    # so the route's segments are read once even with several vehicles on it.
    seg_info_cache = {}

    def _seg_infos_for(route_key):
        if route_key not in seg_info_cache:
            ordered = route_seqs[route_key]
            keys = [
                f'transit:stt:{ds_id}:{ordered[i]}:{ordered[i + 1]}'
                for i in range(len(ordered) - 1)
            ]
            p = r.pipeline(transaction=False)
            for sk in keys:
                p.lrange(sk, 0, -1)
            seg_info_cache[route_key] = segment_infos(p.execute(), route_sched[route_key])
        return seg_info_cache[route_key]

    # Scan vprev for confirmed vehicles on these routes
    vehicles_eta = []
    vprev_prefix = f'transit:vprev:{ds_id}:'
    cursor = 0
    now_ts = time.time()

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

                vid = key[len(vprev_prefix):]
                vdata_raw = r.hget('transit:vdata', f'{ds_id}:{vid}')
                vdata = json.loads(vdata_raw) if vdata_raw else {}

                # Skip zombies (parked): stale feed sid → not a live arrival.
                # Exception: short dwell with sid consistent with the STT idx
                # (timing point) still counts — see zombie_keeps_eta.
                if vdata.get('z') and not zombie_keeps_eta(
                    now_ts, float(state.get('mt') or 0), vdata.get('sid'),
                    v_idx, route_idxmap[route_key],
                ):
                    continue

                # Anchor origin to the displayed snapped stop (sid), not STT idx.
                origin = resolve_origin(vdata.get('sid'), v_idx, route_idxmap[route_key])

                # Vehicle must be BEFORE target stop, and not too far (>15 stops)
                if origin >= target_idx:
                    continue
                stops_away = target_idx - origin
                if stops_away > 15:
                    continue

                # Chain segment estimates from origin to the target stop
                chain = _seg_infos_for(route_key)[origin:target_idx]
                if not chain:
                    continue
                eta_seconds = sum(s['avg'] for s in chain)
                observed_segments = sum(1 for s in chain if s['observed'])

                if eta_seconds <= 0:
                    continue

                vehicles_eta.append({
                    'vehicle_id': vid,
                    'route': v_route,
                    'route_name': vdata.get('rn', ''),
                    'route_color': vdata.get('rc') or '3b82f6',
                    'headsign': vdata.get('hs', ''),
                    'direction': v_dir,
                    'eta_seconds': int(eta_seconds),
                    'eta_minutes': round(eta_seconds / 60, 1),
                    'stops_away': stops_away,
                    'observed_segments': observed_segments,
                    'total_segments': len(chain),
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
    parsed = parse_rstops(r.get(f'transit:rstops:{route_src}:{direction}'))
    if not parsed:
        r.close()
        return {"etas": {}}

    source_ids, stop_coords, sched_offsets = parsed
    num_stops = len(source_ids)
    index_map = build_index_map(source_ids)

    # Batch-read ALL segment travel times → seg_avg (observed avg, else scheduled
    # prior, else default) via shared estimator.
    seg_keys = [
        f'transit:stt:{ds_id}:{source_ids[i]}:{source_ids[i + 1]}'
        for i in range(num_stops - 1)
    ]
    pipe = r.pipeline(transaction=False)
    for sk in seg_keys:
        pipe.lrange(sk, 0, -1)
    seg_results = pipe.execute()
    seg_avg = segment_averages(seg_results, sched_offsets)

    # Scan vprev for confirmed/tentative vehicles on this route+direction.
    # Collect (vid, stt_idx, move_ts); anchor ETA origin to the displayed sid below.
    vprev_prefix = f'transit:vprev:{ds_id}:'
    dir_tracked = []      # (vid, stt_idx, move_ts) on target direction
    tracked_vids = set()  # all vehicle IDs on this route (fallback exclusion)
    cursor = 0

    while True:
        cursor, keys = r.scan(cursor, match=f'{vprev_prefix}*', count=500)
        if keys:
            pipe = r.pipeline(transaction=False)
            for key in keys:
                pipe.hgetall(key)
            states = pipe.execute()

            for key, state in zip(keys, states):
                if not state or state.get('r') != route_src:
                    continue
                vid = key[len(vprev_prefix):]
                tracked_vids.add(vid)
                if state.get('st') not in ('c', 't'):
                    continue
                if int(state.get('d', -1)) != direction:
                    continue
                dir_tracked.append((vid, int(state.get('idx', 0)), float(state.get('mt') or 0)))

        if cursor == 0:
            break

    # Anchor each tracked vehicle's ETA origin to its displayed snapped stop (sid),
    # not the STT idx — keeps the chain consistent with the on-map icon. Skip
    # zombies (parked): their feed sid can be stale → bogus chain. Exception:
    # short dwell with sid consistent with the STT idx (timing point) still
    # counts — see zombie_keeps_eta.
    vehicle_indices = []
    now_ts = time.time()
    if dir_tracked:
        sid_vals = r.hmget('transit:vdata', *[f'{ds_id}:{vid}' for vid, _, _ in dir_tracked])
        for (vid, stt_idx, move_ts), raw_v in zip(dir_tracked, sid_vals):
            sid = None
            if raw_v:
                try:
                    vv = json.loads(raw_v)
                except (json.JSONDecodeError, TypeError):
                    vv = None
                if vv is not None:
                    sid = vv.get('sid')
                    if vv.get('z') and not zombie_keeps_eta(
                        now_ts, move_ts, sid, stt_idx, index_map,
                    ):
                        continue
            vehicle_indices.append(resolve_origin(sid, stt_idx, index_map))

    # Fallback: if no useful tracked vehicles (all at last stop), use GTFS-RT.
    # Only for vehicles NOT already tracked by STT (avoids re-snapping
    # terminal vehicles to wrong intermediate stops).
    if not any(idx < num_stops - 1 for idx in vehicle_indices):
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
                sid = v.get('sid')
                origin = index_map.get(sid) if sid else None
                if origin is None:
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
                    origin = best_idx
                vehicle_indices.append(origin)

    r.close()

    if not vehicle_indices:
        return {"etas": {}}

    return {"etas": cumulative_min_etas(source_ids, seg_avg, vehicle_indices)}


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
    parsed = parse_rstops(r.get(f'transit:rstops:{route_src}:{direction}'))
    if not parsed:
        r.close()
        return {"error": "no stop sequence", "vehicles": []}

    source_ids, _coords, sched_offsets = parsed
    if stop_source_id not in source_ids:
        r.close()
        return {"error": "stop not in sequence", "vehicles": []}

    target_idx = source_ids.index(stop_source_id)
    num_stops = len(source_ids)
    index_map = build_index_map(source_ids)

    # Batch-read ALL segment travel times
    all_seg_keys = [
        f'transit:stt:{ds_id}:{source_ids[i]}:{source_ids[i + 1]}'
        for i in range(num_stops - 1)
    ]
    pipe = r.pipeline(transaction=False)
    for sk in all_seg_keys:
        pipe.lrange(sk, 0, -1)
    all_seg_results = pipe.execute()

    # Segment model: avg (observed avg, else scheduled prior, else default),
    # samples, observed flag, and the estimate source for the breakdown UI.
    infos = segment_infos(all_seg_results, sched_offsets)
    seg_data = [
        {
            'times': [round(float(v), 1) for v in all_seg_results[i]],
            'avg': round(info['avg'], 1),
            'samples': info['samples'],
            'observed': info['observed'],
            'source': info['source'],
        }
        for i, info in enumerate(infos)
    ]

    # Scan vprev for vehicles on this route+direction (any state)
    vprev_prefix = f'transit:vprev:{ds_id}:'
    vehicles_detail = []
    cursor = 0
    now_ts = time.time()

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

                # Anchor the ETA chain to the displayed snapped stop (sid), not
                # the STT idx (which can run a stop ahead/behind the icon).
                # Zombies (parked) contribute no ETA — feed sid can be stale —
                # but still appear in the list with their live.zombie flag.
                # Exception: short dwell with sid consistent with the STT idx
                # (timing point) still gets a chain — see zombie_keeps_eta.
                origin = resolve_origin(vdata.get('sid'), v_idx, index_map)
                zombie_blocked = vdata.get('z') and not zombie_keeps_eta(
                    now_ts, float(state.get('mt') or 0), vdata.get('sid'),
                    v_idx, index_map,
                )
                is_approaching = origin < target_idx and st in ('c', 't') and not zombie_blocked
                stops_away = target_idx - origin if is_approaching else None

                # Build segment chain if approaching
                segments_chain = []
                eta_seconds = 0.0
                observed_count = 0
                fallback_count = 0

                if is_approaching:
                    for i in range(origin, target_idx):
                        if i < len(seg_data):
                            sd = seg_data[i]
                            eta_seconds += sd['avg']
                            segments_chain.append({
                                'from': source_ids[i],
                                'to': source_ids[i + 1],
                                'avg_s': sd['avg'],
                                'samples': sd['samples'],
                                'observed': sd['observed'],
                                'source': sd['source'],
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
                        'eta_origin_index': origin,
                        'eta_origin_stop': source_ids[origin] if origin < num_stops else '?',
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
            # Only set bearing when we actually have one — leaving it unset keeps
            # HasField False downstream instead of claiming a spurious due-north heading.
            if v.get('b') is not None:
                vp.position.bearing = v.get('b')
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
