"""
Shared transit domain helpers: agency time, line grouping, route badges,
modes/directions per stop, physical pole clustering.
"""


import logging
from math import radians, sin, cos, asin, sqrt
from django.core.cache import cache
from django.db import connection
from django.db.models import Count
from django.utils import timezone as dj_timezone
from zoneinfo import ZoneInfo

from geo.models import Stop, Route, RouteStop, StopTime


logger = logging.getLogger(__name__)

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

# ── Intermodal interchange detection ────────────────────────────────────────
# A stop is an interchange when the transport MODES reachable at its location
# span more than one — e.g. a bus pole grouped with a metro station, or a single
# pole served by both tram and bus. "Location" = the stop itself unioned with its
# StopGroup siblings (the cluster of nearby poles/platforms recompute already
# builds). GTFS route_type → coarse mode bucket (extended 100-1599 folded in).
def _mode_of_route_type(rt):
    if rt is None:
        return 'bus'
    if rt == 2 or 100 <= rt <= 199:
        return 'rail'
    if rt == 1 or 400 <= rt <= 499:
        return 'metro'
    if rt == 0 or 900 <= rt <= 999:
        return 'tram'
    if rt == 4 or 1000 <= rt <= 1399:
        return 'ferry'
    if rt == 7 or 1400 <= rt <= 1499:
        return 'funicular'
    if rt == 1100:
        return 'air'
    return 'bus'  # 3, 11 (trolley), 200-299 (coach), 700-799, 1500-1599, …

# Canonical GTFS route_type per coarse mode — drives the sibling-pole per-mode
# counter's icon + i18n label (mirror of frontend useTransitHelpers MODE_ROUTE_TYPE).
_MODE_CANONICAL_RT = {
    'tram': 0, 'metro': 1, 'rail': 2, 'bus': 3,
    'ferry': 4, 'funicular': 7, 'air': 1100,
}

def _interchange_modes_for_stops(stop_ids):
    """{stop_id: sorted[modes]} for the stops whose location offers >1 transport
    mode. The mode set = this pole's own routes' modes unioned with those of its
    StopGroup siblings, so a bus pole adjacent to a rail/metro station is flagged
    even though the platforms are distinct physical Stop rows. Stops spanning a
    single mode are omitted (not interchanges). Two batched queries; group
    membership comes from the precomputed Stop.group FK (recompute-owned)."""
    stop_ids = list(stop_ids)
    if not stop_ids:
        return {}
    # 1. Group membership for the input stops; expand to every sibling pole so a
    #    single-mode input pole still sees the other modes at the same location.
    group_of = {}
    group_ids = set()
    for sid, gid in Stop.objects.filter(id__in=stop_ids).values_list('id', 'group_id'):
        group_of[sid] = gid
        if gid:
            group_ids.add(gid)
    members_by_group = {}
    relevant = set(stop_ids)
    if group_ids:
        for sid, gid in (
            Stop.objects.filter(group_id__in=group_ids, location_type__lte=1)
            .values_list('id', 'group_id')
        ):
            members_by_group.setdefault(gid, []).append(sid)
            relevant.add(sid)
    # 2. Modes serving each relevant pole (one RouteStop⋈Route scan).
    modes_by_stop = {}
    with connection.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT rs.stop_id, r.route_type
            FROM geo_routestop rs JOIN geo_route r ON rs.route_id = r.id
            WHERE rs.stop_id = ANY(%s)
        """, [list(relevant)])
        for sid, rt in cur.fetchall():
            modes_by_stop.setdefault(sid, set()).add(_mode_of_route_type(rt))
    # 3. Union over self + siblings; keep only multi-mode locations.
    out = {}
    for sid in stop_ids:
        gid = group_of.get(sid)
        member_ids = members_by_group.get(gid) if gid else None
        modes = set(modes_by_stop.get(sid, set()))
        for mid in (member_ids or []):
            modes |= modes_by_stop.get(mid, set())
        if len(modes) > 1:
            out[sid] = sorted(modes)
    return out

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

def _headsign_buckets(stop_ids):
    """{stop_id: {norm_key: {spelling: departure_count}}} — trip headsigns
    served from each pole, keyed by a whitespace/case-insensitive form so
    near-duplicate feed spellings ('Santo Antão do Tojal' vs the typo
    'Santo Antão  doTojal') share a bucket. Static-GTFS aggregate over the
    45M-row stop-time table (~10ms each, was 750K+ calls/week) — cached per
    stop for 24h; nightly feed re-imports refresh within a day."""
    stop_ids = [str(s) for s in stop_ids]
    out, missing = {}, []
    cached = cache.get_many([f"transit:hsb:{sid}" for sid in stop_ids])
    for sid in stop_ids:
        bucket = cached.get(f"transit:hsb:{sid}")
        if bucket is None:
            missing.append(sid)
        else:
            out[sid] = bucket
    if missing:
        rows = (
            StopTime.objects.filter(stop_id__in=missing)
            .exclude(trip__headsign="")
            .values("stop_id", "trip__headsign")
            .annotate(n=Count("*"))
        )
        fresh = {sid: {} for sid in missing}
        for r in rows:
            bucket = fresh[str(r["stop_id"])]
            hs = r["trip__headsign"]
            key = "".join(hs.split()).casefold()
            spellings = bucket.setdefault(key, {})
            spellings[hs] = spellings.get(hs, 0) + r["n"]
        cache.set_many({f"transit:hsb:{sid}": b for sid, b in fresh.items()}, 24 * 3600)
        out.update(fresh)
    return out

def _top_directions(bucket, limit):
    """Top destination names from a headsign bucket: ranked by total departure
    count per normalized key, displayed with the busiest spelling."""
    ranked = sorted(
        bucket.values(),
        key=lambda spellings: -sum(spellings.values()),
    )[:limit]
    return [max(spellings.items(), key=lambda kv: kv[1])[0] for spellings in ranked]

def _stop_directions_bulk(stop_ids, limit=3):
    """{stop_id: [top destination names]} — the busiest trip headsigns served
    from each pole, ranked by departure count. A direction label so same-name,
    opposite-direction poles (the two sides of a road, grouped into one
    StopGroup) are tellable apart: «R 1 Maio 109 → Loures» vs «→ Póvoa, Alverca»."""
    stop_ids = list(stop_ids)
    if not stop_ids:
        return {}
    return {
        sid: _top_directions(bucket, limit)
        for sid, bucket in _headsign_buckets(stop_ids).items()
    }

# ── Physical-pole merge (co-located cross-operator poles) ───────────────────
# A StopGroup clusters every pole/platform of a location within 50m (search/map
# dedup). The stop page needs a finer cut: the SAME physical boarding point can
# carry two Stop rows because two operators each ship their own (Carris + Carris
# Metropolitana share thousands of Lisbon poles). A rider at the shelter wants
# every line they can board there in ONE view — not half on another logical stop.
COLOCATED_POLE_M = 5.0

def _haversine_m(lon1, lat1, lon2, lat2):
    dlon = radians(lon2 - lon1)
    dlat = radians(lat2 - lat1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371000 * asin(sqrt(h))

def _physical_pole_clusters(members):
    """Partition StopGroup members into physical boarding points. Two members
    merge iff DIFFERENT agencies within COLOCATED_POLE_M (two operators, one
    shelter, same travel direction). Same-agency members never merge. Union-find;
    returns list[list[Stop]]."""
    n = len(members)
    parent = list(range(n))

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for i in range(n):
        for j in range(i + 1, n):
            a, b = members[i], members[j]
            if a.agency_id != b.agency_id and _haversine_m(
                a.location.x, a.location.y, b.location.x, b.location.y
            ) <= COLOCATED_POLE_M:
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[ra] = rb

    buckets = {}
    for i in range(n):
        buckets.setdefault(find(i), []).append(members[i])
    return list(buckets.values())

def _grouped_pole_members(stop):
    """(colocated, sibling_clusters). `colocated` = Stop rows at the SAME physical
    pole as `stop`, incl. self (cross-operator rows merged — the page presents
    these as one boarding point). `sibling_clusters` = the OTHER physical poles of
    the StopGroup, each its own merged cluster. ([stop], []) when ungrouped."""
    if not stop.group_id:
        return [stop], []
    members = list(
        Stop.objects.filter(group_id=stop.group_id, location_type__lte=1)
        .select_related("place", "agency")
    )
    colocated, siblings = None, []
    for cl in _physical_pole_clusters(members):
        if any(m.id == stop.id for m in cl):
            colocated = cl
        else:
            siblings.append(cl)
    if colocated is None:  # stop not in its own group member set (shouldn't happen)
        colocated = [stop]
    return colocated, siblings

def _stop_directions_combined(stop_ids, limit=3):
    """Top destinations across SEVERAL co-located poles, pooled as one boarding
    point. Same headsign aggregation as _stop_directions_bulk, summed over all
    stop_ids (co-located poles share a travel direction, so pooling is sound)."""
    stop_ids = list(stop_ids)
    if not stop_ids:
        return []
    merged: dict = {}
    for bucket in _headsign_buckets(stop_ids).values():
        for key, spellings in bucket.items():
            pooled = merged.setdefault(key, {})
            for hs, n in spellings.items():
                pooled[hs] = pooled.get(hs, 0) + n
    return _top_directions(merged, limit)

def _route_mode_counts_combined(stop_ids):
    """[{type, count}] distinct serving lines per coarse mode, pooled across
    stop_ids (a pole shared by several operators). Combined variant of
    _route_mode_counts_for_stops (which is per-stop)."""
    stop_ids = list(stop_ids)
    if not stop_ids:
        return []
    modes: dict = {}
    with connection.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT r.short_name, r.route_type
            FROM geo_routestop rs JOIN geo_route r ON rs.route_id = r.id
            WHERE rs.stop_id = ANY(%s)
        """, [stop_ids])
        for short_name, rt in cur.fetchall():
            modes.setdefault(_mode_of_route_type(rt), set()).add(short_name)
    return sorted(
        ({"type": _MODE_CANONICAL_RT.get(m, 3), "count": len(names)}
         for m, names in modes.items()),
        key=lambda x: x["type"],
    )
