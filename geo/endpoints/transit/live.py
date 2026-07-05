"""
Realtime endpoints: live vehicles, vehicle history/state, STT ETA.
"""


import json
import logging
import time
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from datetime import datetime

from geo.models import Stop, Route, RouteStop, TransitDataSource, VehiclePositionHistory

from parahub.ratelimit import ratelimit
from parahub.services.redis_pool import get_redis
from parahub.services.transit_eta import (
    parse_rstops, segment_infos, segment_averages,
    build_index_map, resolve_origin, cumulative_min_etas, zombie_keeps_eta,
)

from .base import router

logger = logging.getLogger(__name__)

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

    r = get_redis()

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
    r = get_redis()

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

    route = get_object_or_404(
        Route.objects.select_related("agency__data_source"),
        place__slug=city_slug, slug=route_slug,
    )
    ds = route.agency.data_source if route.agency else None
    if not ds:
        return {"etas": {}}

    ds_id = str(ds.id)
    route_src = route.source_id

    r = get_redis()

    # Load stop sequence for this route+direction
    parsed = parse_rstops(r.get(f'transit:rstops:{route_src}:{direction}'))
    if not parsed:
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

    route = get_object_or_404(
        Route.objects.select_related("agency__data_source"),
        place__slug=city_slug, slug=route_slug,
    )
    ds = route.agency.data_source if route.agency else None
    if not ds:
        return {"error": "no data source"}

    ds_id = str(ds.id)
    route_src = route.source_id

    r = get_redis()

    # Load stop sequence
    parsed = parse_rstops(r.get(f'transit:rstops:{route_src}:{direction}'))
    if not parsed:
        return {"error": "no stop sequence", "vehicles": []}

    source_ids, _coords, sched_offsets = parsed
    if stop_source_id not in source_ids:
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
