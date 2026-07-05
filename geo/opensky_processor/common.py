"""
Shared runtime services: the tile advisory lock, realtime WS publishing,
reverse geocoding, and the superseded-mission guard.
"""

import json
import logging
from contextlib import contextmanager

import requests

from django.db import connection

logger = logging.getLogger(__name__)


# Session-level Postgres advisory lock serializing all latest/ + OpenSkyTileLayer
# mutations. The per-mission processor (process_opensky_queue) and the manual
# consolidation must not write the same tile coords concurrently. The processor
# try-acquires and skips a tick if held; consolidation blocks (operator action).
OPENSKY_TILE_LOCK_KEY = 478215


@contextmanager
def opensky_tile_lock(blocking: bool = True):
    """Acquire the shared OpenSky tile advisory lock. Yields True if held.

    blocking=True waits for the lock (consolidation); blocking=False try-locks
    and yields False if another holder has it (processor — skip this tick).
    Auto-released on connection close if the process dies mid-run.
    """
    with connection.cursor() as cur:
        if blocking:
            cur.execute("SELECT pg_advisory_lock(%s)", [OPENSKY_TILE_LOCK_KEY])
            acquired = True
        else:
            cur.execute("SELECT pg_try_advisory_lock(%s)", [OPENSKY_TILE_LOCK_KEY])
            acquired = bool(cur.fetchone()[0])
        try:
            yield acquired
        finally:
            if acquired:
                with connection.cursor() as c2:
                    c2.execute("SELECT pg_advisory_unlock(%s)", [OPENSKY_TILE_LOCK_KEY])


def _publish_mission_update(mission_id: str, data: dict):
    """Publish mission update to Redis for real-time WebSocket delivery."""
    import redis as _redis
    try:
        r = _redis.Redis()
        payload = json.dumps({'type': 'opensky.mission_updated', 'mission_id': str(mission_id), **data})
        r.publish('opensky:missions', payload)
    except Exception as e:
        logger.warning(f'Failed to publish opensky update: {e}')


# Local Pelias geocoder (same host as the backend).
PELIAS_URL = "http://localhost:4000"


def reverse_geocode_place(lat, lng):
    """Reverse-geocode a coordinate to ``(place_label, place_region)`` via local Pelias.

    Restricted to area-level layers (parish / municipality / county / region) so an
    open-countryside survey resolves to its parish rather than the nearest street.
    Mirrors the frontend card readout (placeName / placeRegion). Returns ``('', '')``
    on any failure so the caller leaves the existing stored value untouched.
    """
    if lat is None or lng is None:
        return '', ''
    try:
        resp = requests.get(
            f"{PELIAS_URL}/v1/reverse",
            params={
                'point.lat': lat,
                'point.lon': lng,
                'size': 1,
                'layers': 'locality,localadmin,county,region',
            },
            timeout=5,
        )
        resp.raise_for_status()
        features = resp.json().get('features', [])
        if not features:
            return '', ''
        p = features[0].get('properties', {})
        label = (p.get('locality') or p.get('localadmin') or p.get('name')
                 or p.get('county') or p.get('region') or '')
        region = ' · '.join(x for x in (p.get('region'), p.get('country')) if x)
        return label, region
    except Exception as e:
        logger.warning(f"reverse_geocode_place({lat},{lng}) failed: {e}")
        return '', ''


def _is_superseded(mission_id: str) -> bool:
    """True if this mission must be skipped by the per-mission realign/retile
    paths (consensus, satellite, similarity, retile). Two cases:
    - a MEMBER of a consolidation: re-tiling it re-plants its tiles + grabs a
      fresh max layer_order, inverting above the super-tile (re-introduces seam);
    - a CONSOLIDATION itself: it has NULL tile_z/x/y, so the Z17-clip in
      _reclip_retile_publish is skipped → tiling the UNCLIPPED merged ortho
      spills across many neighbour cells (incident 2026-06-09). Consolidations
      are products, not flights — they are never consensus/similarity-realigned."""
    from geo.models import OpenSkyMission
    m = OpenSkyMission.objects.filter(id=mission_id).first()
    if m and m.is_consolidation:
        logger.info(f"{mission_id[:8]} is a consolidation — skipping per-mission realign/retile")
        return True
    if m and m.superseded_by_id:
        logger.info(
            f"{mission_id[:8]} is superseded by consolidation {m.superseded_by_id[:8]} "
            f"— skipping realign/retile (delete the consolidation to re-enable)")
        return True
    return False
