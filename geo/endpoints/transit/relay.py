"""
GTFS relay endpoints: static feed downloads and GTFS-RT mirrors.
"""


from ninja.errors import HttpError
import json
import logging
from django.conf import settings
from django.shortcuts import get_object_or_404

from geo.models import TransitDataSource

from parahub.ratelimit import ratelimit
from parahub.services.redis_pool import get_redis

from .base import router

logger = logging.getLogger(__name__)

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
    from django.http import HttpResponse
    from google.transit import gtfs_realtime_pb2

    ds = get_object_or_404(TransitDataSource, slug=slug, is_active=True)
    ds_id = str(ds.id)

    # Check for cached protobuf (15s TTL)
    pb_cache_key = f'transit:rt:pb:{ds_id}'
    r = get_redis(decode_responses=False)

    cached = r.get(pb_cache_key)
    if cached:
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

    return HttpResponse(serialized, content_type='application/x-protobuf')

@router.get("/transit/gtfs-rt/vehicle-positions/{slug}.json", auth=None)
@ratelimit(group='transit:gtfs_rt_json', key='ip', rate='120/m')
def gtfs_rt_vehicle_positions_json(request, slug: str):
    """GTFS-RT vehicle positions as JSON (convenience endpoint)."""

    ds = get_object_or_404(TransitDataSource, slug=slug, is_active=True)
    ds_id = str(ds.id)

    r = get_redis()
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

    return {"slug": slug, "name": ds.name, "vehicles": vehicles}

@router.get("/transit/gtfs-rt/service-alerts/{slug}/", auth=None)
@ratelimit(group='transit:gtfs_alerts', key='ip', rate='120/m')
def gtfs_rt_service_alerts(request, slug: str):
    """Serve GTFS-RT ServiceAlerts protobuf (relay from Redis cache)."""
    import time as _time
    from django.http import HttpResponse
    from google.transit import gtfs_realtime_pb2

    ds = get_object_or_404(TransitDataSource, slug=slug, is_active=True)
    ds_id = str(ds.id)

    r = get_redis(decode_responses=False)

    # Relay raw protobuf if available (stored by fetch_transit_alerts daemon)
    cached_pb = r.get(f'transit:alerts:pb:{ds_id}')
    if cached_pb:
        return HttpResponse(cached_pb, content_type='application/x-protobuf')

    # No cached data — return empty feed
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = '2.0'
    feed.header.incrementality = gtfs_realtime_pb2.FeedHeader.FULL_DATASET
    feed.header.timestamp = int(_time.time())

    return HttpResponse(feed.SerializeToString(), content_type='application/x-protobuf')

@router.get("/transit/gtfs-rt/service-alerts/{slug}.json", auth=None)
@ratelimit(group='transit:gtfs_alerts_json', key='ip', rate='120/m')
def gtfs_rt_service_alerts_json(request, slug: str):
    """GTFS-RT service alerts as JSON."""

    ds = get_object_or_404(TransitDataSource, slug=slug, is_active=True)
    ds_id = str(ds.id)

    r = get_redis()

    raw = r.get(f'transit:alerts:{ds_id}')

    alerts = json.loads(raw) if raw else []
    return {"slug": slug, "name": ds.name, "alerts": alerts}
