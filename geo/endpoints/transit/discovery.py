"""
Discovery endpoints: cities, per-city discover payload, search, feeds, agencies.
"""


from ninja.errors import HttpError
import json
import random
import logging
import orjson
from django.core.cache import cache
from django.db import connection
from django.db.models import Q
from django.db.models.functions import Length
from django.http import HttpResponse

from geo.models import Stop, Route, Place

from parahub.ratelimit import ratelimit

from .base import router
from .helpers import LINE_CANONICAL_ORDER, _interchange_modes_for_stops, _merged_route_badges, _routes_for_stop, _stop_directions_bulk, line_group_key, line_key_fields
from .schedule import _night_route_ids
from .schemas import TransitPlaceResponse

logger = logging.getLogger(__name__)

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

def _place_route_filter(place):
    """Return a Q filter for routes within a Place.

    Matches the majority-place FK or any place the route passes through
    (`places` M2M — inter-city routes like CM 1723 Carnaxide→Lisboa would
    otherwise be invisible in their destination city), both hierarchy-aware.
    Callers must apply .distinct(): the M2M join can multiply rows.
    """
    return _place_descend_q(place) | _place_descend_q(place, 'places')

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
    inter_map = _interchange_modes_for_stops([s["id"] for s in stops])
    for s in stops:
        s["interchange_modes"] = inter_map.get(s["id"], [])

    night_ids = _night_route_ids([r.id for r in routes_qs])
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
            "is_night": r.id in night_ids,
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
    # Intermodal interchange flag — group-aware (the navigation pole's whole
    # cluster), so a bus result grouped with a metro station is marked even when
    # only the bus poles matched the query (merged badges would miss it).
    inter_map = _interchange_modes_for_stops([e["id"] for e in stops])
    for e in stops:
        e["directions"] = dir_map.get(e["id"], [])
        e["interchange_modes"] = inter_map.get(e["id"], [])

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
    night_ids = _night_route_ids([r["id"] for r in routes])
    for r in routes:
        r["is_night"] = r["id"] in night_ids

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
