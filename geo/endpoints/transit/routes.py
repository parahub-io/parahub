"""
Route endpoints: route detail by slug, route schedule.
"""


from typing import List
import json
import logging
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from datetime import datetime

from geo.models import Route, RouteStop, StopTime, CalendarDate, Trip

from parahub.ratelimit import ratelimit

from .base import router
from .helpers import _agency_local_now, _interchange_modes_for_stops, line_siblings
from .schedule import _active_services_window, _dep_secs, _night_route_ids, _secs_to_hhmm, _time_to_secs, _timeline_positions
from .schemas import TransitRouteDetail, TransitRouteDirection, TransitRouteListItem, TransitRoutePlaceItem, TransitRouteVariant

logger = logging.getLogger(__name__)

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
    stops_dir1 = _stop_list(1)

    # Mark stops that are intermodal interchanges (their location offers a mode
    # other than this route's) so the page can flag "change to metro/rail here".
    inter = _interchange_modes_for_stops(
        {s["id"] for s in stops_dir0} | {s["id"] for s in stops_dir1}
    )
    for s in stops_dir0:
        s["interchange_modes"] = inter.get(s["id"], [])
    for s in stops_dir1:
        s["interchange_modes"] = inter.get(s["id"], [])

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
        stops_dir1=stops_dir1,
        directions=directions,
        places=route_places,
        geometry=geojson,
    )

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
    for src, dir_id, svc, dsecs, dtime, seq in rows:
        if dir_id not in (0, 1):
            continue
        eff = _dep_secs(dsecs, dtime)
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

    # Night-route badge: classified per-route over all services (not just the
    # active window) so the route page and the /transit list — which share
    # _night_route_ids — never disagree about the same route.
    is_night = bool(_night_route_ids([route.id]))

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
