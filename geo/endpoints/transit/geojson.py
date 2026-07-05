"""
GeoJSON endpoints for map rendering: vehicles, routes, stops.
"""


import json
import logging
import orjson
from django.core.cache import cache
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse
from datetime import datetime

from geo.models import Stop, Route, TransitDataSource

from parahub.ratelimit import ratelimit

from .base import router

logger = logging.getLogger(__name__)

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
