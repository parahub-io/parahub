"""
Route timetable endpoints: 7-day and seasonal grids, printable PDF.
"""


import json
import logging
import unicodedata
from collections import defaultdict
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone as dj_timezone
from datetime import timedelta
from zoneinfo import ZoneInfo

from geo.models import Route, StopTime, CalendarDate, Trip

from parahub.ratelimit import ratelimit

from .base import router
from .helpers import _agency_local_now, _mode_of_route_type, line_siblings
from .routes import _build_route_detail
from .schedule import _dep_secs, _secs_to_hhmm

logger = logging.getLogger(__name__)

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
    return _route_timetable_7day(route)

def _route_timetable_7day(route):
    """7-day line timetable payload (see get_route_timetable). Extracted so the
    branded PDF export reuses the exact same data the modal renders."""
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

# ── Seasonal timetable columns (for the printable PDF sheet) ────────────────
# Day-type tokens stripped from a GTFS service_id to recover its season label.
_DAYTYPE_TOKENS = {
    "util", "uteis", "semana", "workday", "weekday", "laboral", "laborable",
    "sabado", "sabados", "saturday", "samedi", "samstag", "sat",
    "domingo", "domingos", "domingoferiado", "feriado", "feriados",
    "sunday", "holiday", "holidays", "dimanche", "sonntag", "feiertag", "sun",
}

# Known PT period tokens → i18n key suffix; everything else shows the raw feed
# token (best-effort cosmetic — grouping never depends on this).
_SEASON_CANON = {
    "inverno": "winter", "verao": "summer", "primavera": "spring", "outono": "autumn",
    "agosto": "august", "ferias escolares": "school_holidays", "ferias": "school_holidays",
    "natal": "christmas", "ano novo": "new_year", "natal & ano novo": "christmas_new_year",
    "pascoa": "easter", "feriados": "holidays",
}

def _strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def _season_label(service_id):
    """Best-effort season/period label from a service_id like 'Inverno_Util_20260606'
    → 'Inverno'. Drops the day-type token and any date/version token; '' if nothing
    meaningful remains. Returns (raw_label, canon_key|None)."""
    keep = []
    for p in (x.strip() for x in service_id.split("_")):
        if not p:
            continue
        norm = _strip_accents(p).lower()
        if norm.isdigit() or norm in _DAYTYPE_TOKENS:
            continue
        keep.append(p)
    raw = " ".join(keep)
    canon = _SEASON_CANON.get(_strip_accents(raw).lower()) if raw else None
    return raw, canon

def _classify_daytype(hist):
    """Coarse day-type from a 7-slot weekday histogram (Mon..Sun)."""
    wk, sat, sun = sum(hist[0:5]), hist[5], hist[6]
    total = wk + sat + sun
    if total == 0:
        return "weekday"
    if sun >= wk and sun >= sat:
        return "sun"
    if sat >= wk and sat >= sun:
        return "sat"
    if wk > 0 and sat > 0 and sun > 0 and (sat + sun) >= 0.4 * total:
        return "all"
    return "weekday"

# A schedule group covering fewer than this many service dates in the window is a
# rare special (Christmas, single public holiday) — footnoted, not a column.
_SEASONAL_SPECIAL_MAX_DATES = 3

_DAYTYPE_RANK = {"all": 0, "weekday": 1, "sat": 2, "sun": 3}

def _route_timetable_seasonal(route, window_days=365):
    """Group this line's services into seasonal timetable columns for the print
    sheet. Columns are formed by IDENTICAL departure schedule (feed-agnostic):
    services with the same first-stop departures across both directions collapse
    into one column — exactly how an operator merges e.g. 'Inverno' + 'Férias
    Escolares' weekdays into one printed column. Each column is labelled by its
    day-type (derived from the weekday spread of its real service dates, not by
    parsing names) plus a best-effort season hint. Rare specials (few dates) are
    returned separately for a footnote."""
    siblings = line_siblings(route) if route.line_id else [route]
    sib_index = {s.id: i for i, s in enumerate(siblings)}

    today_local, _ = _agency_local_now(route.agency)
    cache_key = f"transit:seasonal:{route.id}:{today_local.isoformat()}"
    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)

    horizon = today_local + timedelta(days=window_days)
    svc_ids = set(
        Trip.objects.filter(route__in=siblings).values_list("service_id", flat=True).distinct()
    )
    result = {"columns": [], "specials": [], "variants": [], "period": None}
    if svc_ids:
        ds_id = route.agency.data_source_id
        scope = Q(agency__data_source_id=ds_id) if ds_id else Q(agency_id=route.agency_id)
        added, removed = defaultdict(set), defaultdict(set)
        for sid, ex, d in CalendarDate.objects.filter(
            scope, service_id__in=svc_ids, date__gte=today_local, date__lte=horizon,
            exception_type__in=[1, 2],
        ).values_list("service_id", "exception_type", "date"):
            (added if ex == 1 else removed)[sid].add(d)
        dates_by_svc = {sid: (added[sid] - removed.get(sid, set())) for sid in svc_ids}
        dates_by_svc = {sid: ds for sid, ds in dates_by_svc.items() if ds}

        # first-stop departures per (service, direction): {secs: min sibling index}
        dep = defaultdict(lambda: defaultdict(dict))
        if dates_by_svc:
            for sid, dir_id, rid, dsecs, dtime in StopTime.objects.filter(
                trip__route__in=siblings, trip__service_id__in=list(dates_by_svc),
                stop_sequence=1,
            ).values_list(
                "trip__service_id", "trip__direction_id", "trip__route_id",
                "departure_secs", "departure_time",
            ):
                d = dir_id if dir_id in (0, 1) else 0
                secs = _dep_secs(dsecs, dtime)
                si = sib_index.get(rid, 0)
                cur = dep[sid][d].get(secs)
                if cur is None or si < cur:
                    dep[sid][d][secs] = si

        # group services by identical (dir0, dir1) departure fingerprint
        groups = defaultdict(list)
        for sid in dates_by_svc:
            key = (frozenset(dep[sid].get(0, {})), frozenset(dep[sid].get(1, {})))
            groups[key].append(sid)

        all_dates = set()
        used_variants = set()
        cols, specials = [], []
        for sids in groups.values():
            gdates = set().union(*(dates_by_svc[s] for s in sids))
            all_dates |= gdates
            hist = [0] * 7
            for d in gdates:
                hist[d.weekday()] += 1
            rep = sids[0]
            dirs = {}
            for d in (0, 1):
                items = sorted(dep[rep].get(d, {}).items())  # (secs, si)
                for _s, si in items:
                    if si > 0:
                        used_variants.add(si)
                dirs[str(d)] = [{"t": _secs_to_hhmm(s), "v": si} for s, si in items]
            raws, canons = [], []
            for s in sids:
                raw, canon = _season_label(s)
                if raw and raw not in raws:
                    raws.append(raw)
                    canons.append(canon)
            entry = {
                "day_type": _classify_daytype(hist),
                "seasons": raws,
                "season_keys": canons,
                "n_dates": len(gdates),
                "dir": dirs,
            }
            (specials if len(gdates) < _SEASONAL_SPECIAL_MAX_DATES else cols).append(entry)

        cols.sort(key=lambda c: (_DAYTYPE_RANK.get(c["day_type"], 9), -c["n_dates"]))
        # Show the season hint only where a day-type splits into >1 column.
        dt_counts = defaultdict(int)
        for c in cols:
            dt_counts[c["day_type"]] += 1
        for c in cols:
            c["show_seasons"] = dt_counts[c["day_type"]] > 1

        specials.sort(key=lambda c: c["n_dates"])

        result["columns"] = cols
        result["specials"] = [
            {"seasons": c["seasons"], "season_keys": c["season_keys"], "n_dates": c["n_dates"],
             "day_type": c["day_type"]}
            for c in specials
        ]
        result["variants"] = [
            {"index": i, "slug": s.slug, "place_slug": s.place.slug if s.place else "",
             "long_name": s.long_name}
            for s, i in ((s, sib_index[s.id]) for s in siblings)
            if i in used_variants
        ]
        if all_dates:
            result["period"] = [min(all_dates).isoformat(), max(all_dates).isoformat()]

    tzname = (getattr(route.agency, "timezone", "") or "").strip()
    try:
        tz = ZoneInfo(tzname) if tzname else ZoneInfo("UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    now_local = dj_timezone.now().astimezone(tz)
    ttl = max(300, 86400 - (now_local.hour * 3600 + now_local.minute * 60 + now_local.second))
    cache.set(cache_key, json.dumps(result), ttl)
    return result

@router.get("/transit/routes/{city_slug}/{route_slug}/timetable.pdf", auth=None)
@ratelimit(group='transit:route_timetable_pdf', key='ip', rate='20/m')
def get_route_timetable_pdf(request, city_slug: str, route_slug: str, lang: str = "en"):
    """Branded (Parahub) printable timetable sheet — the "Download PDF" button in
    the timetable modal. One A4 page per direction: stop list (with intermodal-
    interchange markers) on the left + a SEASONAL departure table on the right
    (hour rows × one column per service pattern: weekday / Saturday / Sunday,
    split by season where the schedule differs). Date-independent: it shows the
    whole editorial period. Reuses _route_timetable_seasonal + _build_route_detail
    (no new data derived)."""
    from parahub.services.transit_timetable_pdf import generate_timetable_pdf

    route = get_object_or_404(
        Route.objects.select_related("agency", "place"),
        place__slug=city_slug, slug=route_slug,
    )

    seasonal = _route_timetable_seasonal(route)

    # Stop lists (with interchange modes) + canonical headsigns from route detail.
    detail = _build_route_detail(route)
    stops_by_dir = {0: detail.stops, 1: detail.stops_dir1}
    detail_headsign = {d.direction_id: d.headsign for d in detail.directions}

    # Interchange markers show only what you can transfer TO — drop the route's
    # own mode bucket, same as the page's <TransitInterchangeBadge :exclude>.
    own_mode = _mode_of_route_type(route.route_type)

    directions_ctx = []
    for d_id in (0, 1):
        stops = stops_by_dir.get(d_id) or []
        columns = [
            {"day_type": col["day_type"], "seasons": col["seasons"],
             "season_keys": col["season_keys"], "show_seasons": col["show_seasons"],
             "departures": col["dir"].get(str(d_id), [])}
            for col in seasonal["columns"]
        ]
        columns = [col for col in columns if col["departures"]]
        if not stops and not columns:
            continue
        directions_ctx.append({
            "arrow": "←" if d_id == 1 else "→",
            "headsign": detail_headsign.get(d_id) or "",
            "stops": [
                {"name": s["name"],
                 "modes": [m for m in s.get("interchange_modes", []) if m != own_mode]}
                for s in stops
            ],
            "columns": columns,
        })

    legend = [
        {"index": v["index"], "long_name": v["long_name"]}
        for v in seasonal["variants"] if v["index"] > 0
    ]

    page_url = f"https://parahub.io/transit/route/{city_slug}/{route_slug}"
    pdf = generate_timetable_pdf(
        short_name=route.short_name,
        long_name=route.long_name,
        route_type=route.route_type,
        route_color=route.route_color,
        route_text_color=route.route_text_color,
        agency_name=route.agency.name if route.agency else "",
        directions=directions_ctx,
        specials=seasonal["specials"],
        variants=legend,
        period=seasonal["period"],
        page_url=page_url,
        lang=lang,
    )

    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in (route.short_name or route.slug))
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="parahub-{safe}-timetable.pdf"'
    return resp
