"""
Schedule computation: GTFS service-day seconds, active service windows,
stop day rows and the stop schedule payload.
"""


from ninja.errors import HttpError
import json
import logging
from django.core.cache import cache
from django.db.models import Q
from datetime import datetime, timedelta

from geo.models import StopTime, CalendarDate


from .helpers import _agency_local_now, _grouped_pole_members

logger = logging.getLogger(__name__)

SECONDS_PER_DAY = 86400

# "Night route" daytime test: a genuine night-only line has ZERO departures in
# the broad daytime window 07:00–19:00 (covers day + morning peak + early
# evening, so commuter expresses and evening lines aren't counted as night).
NIGHT_DAYTIME_START_SECS = 7 * 3600   # 07:00

NIGHT_DAYTIME_END_SECS = 19 * 3600    # 19:00

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

def _night_route_ids(route_ids):
    """Subset of route_ids that are genuine night-only services: they have
    after-midnight service (any stop_time at/after 24:00 — GTFS extended hours)
    AND run exclusively at night (ZERO departures in the daytime window
    07:00–19:00). The daytime clause excludes all-day lines that merely close
    after midnight — metro, frequent urban buses — which the bare ≥24:00 test
    mis-flagged (e.g. Metro de Lisboa Vermelha runs ~800 departures/hour all
    day yet crosses midnight). Single source of truth for the "night route"
    badge so the /transit list agrees with the route page. Empty for feeds
    imported before departure_secs existed (degrades to non-night, same as the
    wrapped-time readers)."""
    if not route_ids:
        return set()
    crosses_midnight = set(
        StopTime.objects.filter(
            trip__route_id__in=route_ids, departure_secs__gte=SECONDS_PER_DAY
        ).values_list("trip__route_id", flat=True).distinct()
    )
    if not crosses_midnight:
        return set()
    has_daytime = set(
        StopTime.objects.filter(
            trip__route_id__in=crosses_midnight,
            departure_secs__gte=NIGHT_DAYTIME_START_SECS,
            departure_secs__lt=NIGHT_DAYTIME_END_SECS,
        ).values_list("trip__route_id", flat=True).distinct()
    )
    return crosses_midnight - has_daytime

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

def _stop_day_rows(stop, service_ids, query_date):
    """Flattened stop-times of one pole for one service day. The
    StopTime⋈Trip⋈Route⋈Place join is the hottest DB query on the platform
    (~200ms on hub poles, 57K+ calls/week); the result is static GTFS, so one
    cache entry per (pole, date) serves every schedule view that day. TTL 6h
    caps how long a mid-day feed re-import can stay stale."""
    ck = f"transit:sched:{stop.id}:{query_date}"
    rows = cache.get(ck)
    if rows is None:
        rows = [
            {
                "eff": _dep_secs(st.departure_secs, st.departure_time),
                "svc": st.trip.service_id,
                "hs": st.trip.headsign,
                "dir": st.trip.direction_id if st.trip.direction_id is not None else 0,
                "tid": st.trip.id,
                "rsn": st.trip.route.short_name,
                "rln": st.trip.route.long_name,
                "rc": st.trip.route.route_color,
                "rt": st.trip.route.route_type,
                "rsid": st.trip.route.source_id,
                "rslug": st.trip.route.slug,
                "rps": st.trip.route.place.slug if st.trip.route.place else "",
            }
            for st in StopTime.objects.filter(
                stop=stop,
                trip__service_id__in=service_ids,
            ).select_related("trip__route__place")
        ]
        cache.set(ck, rows, 6 * 3600)
    return rows

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

    # Co-located cross-operator poles are one physical boarding point — pool their
    # departures + live so a rider sees every line leaving here, not just one feed.
    colocated, _siblings = _grouped_pole_members(stop)

    # Live vehicles at any co-located pole. Each pole's live comes from ITS OWN
    # data source's GTFS-RT cache (operators differ); read each cache once.
    live_vehicles = []
    if not date_param:
        cutoff = now_dt.timestamp() - 180  # vehicles seen in last 3 min
        rt_by_ds: dict = {}
        for cs in colocated:
            ds_id = cs.agency.data_source_id if cs.agency else None
            if not ds_id:
                continue
            if ds_id not in rt_by_ds:
                raw = cache.get(f'transit:rt:{ds_id}')
                try:
                    rt_by_ds[ds_id] = json.loads(raw) if raw else []
                except Exception:
                    rt_by_ds[ds_id] = []
            for v in rt_by_ds[ds_id]:
                if v.get('sid') == cs.source_id and v.get('t', 0) >= cutoff:
                    live_vehicles.append({
                        "route_short_name": v.get('rn', ''),
                        "route_color": v.get('rc', ''),
                        "headsign": v.get('hs', ''),
                        "status": v.get('st', ''),
                        "vehicle_id": v.get('v', ''),
                    })

    # Wrap-aware upcoming departures, pooled across co-located poles. Each pole
    # uses ITS OWN agency's active-service window (operators have distinct
    # calendars); query_date / now are shared (one location → one timezone).
    # Active services span query_date + the day before, so a night trip stored at
    # 24:00+ (previous service date, runs in today's small hours) still shows.
    candidates = []  # (position_secs, cached row dict)
    for cs in colocated:
        today_services, yest_services = _active_services_window(cs.agency, query_date)
        if not today_services and not yest_services:
            continue
        for row in _stop_day_rows(cs, today_services | yest_services, query_date):
            for pos in _timeline_positions(row["svc"], row["eff"], today_services, yest_services, now_secs):
                candidates.append((pos, row))
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
                "route_short_name": row["rsn"],
                "route_long_name": row["rln"],
                "route_color": row["rc"],
                "route_type": row["rt"],
                "route_source_id": row["rsid"],
                "route_slug": row["rslug"],
                "route_place_slug": row["rps"],
                "headsign": row["hs"],
                "direction_id": row["dir"],
                "trip_id": row["tid"],
                "service_id": row["svc"],
            }
            for pos, row in departures
        ],
    }
