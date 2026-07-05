"""
Weather endpoint — cached proxy over Open-Meteo (data CC-BY 4.0).

Planetary architecture: every request is snapped to a coarse ~0.1° grid
(~11 km, matching the weather models' 1–25 km resolution) and cached in Redis
for 30 min. All users looking at the same cell share a single upstream call —
Redis absorbs the load, Open-Meteo sees only a trickle. A single-flight lock
collapses concurrent cold-cell misses, and a longer "last-good" copy keeps the
HUD populated through a brief upstream outage.

Upstream is abstracted behind this endpoint: pointing OPEN_METEO_URL at a
self-hosted Open-Meteo instance later is a one-line change, transparent to the
frontend. Reused by the map HUD and transit-stop weather displays.
"""

import logging

import httpx
import orjson
from django.core.cache import cache
from django.http import HttpResponse
from ninja import Router

from parahub.ratelimit import ratelimit

logger = logging.getLogger(__name__)

router = Router(tags=["Geo / Weather"])

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Remote upstream: keep the ceiling tight so an Open-Meteo stall can't pin a
# request for long (the endpoint is async — the wait doesn't hold a sync slot,
# but the client is still waiting).
OPEN_METEO_TIMEOUT = httpx.Timeout(6.0, connect=2.0)

# Grid cell size in degrees. ~0.1° ≈ 11 km: matches model resolution and keeps
# the reading stable while panning within a city (fewer upstream calls).
GRID = 0.1

# 30 min: Open-Meteo's `current` refreshes ~every 15 min, so this never serves
# data older than one extra cycle while halving upstream load vs a 15 min TTL.
TTL_FRESH = 1800
# 6 h last-good fallback if Open-Meteo is unreachable on a cold cell.
TTL_STALE = 6 * 3600

CURRENT_FIELDS = (
    "temperature_2m,apparent_temperature,weather_code,is_day,"
    "precipitation,wind_speed_10m,wind_direction_10m,wind_gusts_10m"
)


def _snap(value: float) -> float:
    """Snap a coordinate to its grid-cell centre (2 dp, grid-aligned)."""
    return round(round(value / GRID) * GRID, 2)


async def _fetch_upstream(clat: float, clon: float):
    """Call Open-Meteo for a cell centre; return a normalized dict or None."""
    try:
        async with httpx.AsyncClient(timeout=OPEN_METEO_TIMEOUT) as client:
            resp = await client.get(
                OPEN_METEO_URL,
                params={
                    "latitude": clat,
                    "longitude": clon,
                    "current": CURRENT_FIELDS,
                    "wind_speed_unit": "kmh",
                    "timezone": "auto",
                },
            )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Open-Meteo fetch failed for %s,%s: %s", clat, clon, e)
        return None

    cur = data.get("current") or {}
    if cur.get("temperature_2m") is None:
        return None

    return {
        "available": True,
        "cell": {"lat": clat, "lon": clon},
        "observed_at": cur.get("time"),
        "temperature": cur.get("temperature_2m"),
        "apparent_temperature": cur.get("apparent_temperature"),
        "weather_code": cur.get("weather_code"),
        "is_day": bool(cur.get("is_day", 1)),
        "precipitation": cur.get("precipitation"),
        # Meteorological convention: degrees the wind blows FROM (0 = from north).
        "wind_direction": cur.get("wind_direction_10m"),
        "wind_speed": cur.get("wind_speed_10m"),
        "wind_gusts": cur.get("wind_gusts_10m"),
        "units": {"temperature": "°C", "wind_speed": "km/h"},
        "attribution": {
            "name": "Open-Meteo.com",
            "url": "https://open-meteo.com/",
            "license": "CC BY 4.0",
        },
    }


@router.get("/weather", auth=None)
@ratelimit(group='geo:weather', key='ip', rate='120/m')
async def weather(request, lat: float, lon: float):
    """
    Current weather near (lat, lon), snapped to a shared ~11 km grid cell and
    cached 30 min. Returns ``{"available": false}`` if Open-Meteo is unreachable
    and no recent value is known.
    """
    clat, clon = _snap(lat), _snap(lon)
    key = f"geo:wx:{clat:.2f}:{clon:.2f}"
    stale_key = f"{key}:last"
    lock_key = f"{key}:lock"

    cached = await cache.aget(key)
    if cached:
        return HttpResponse(cached, content_type='application/json')

    # Single-flight: collapse concurrent cold-cell misses into one upstream call.
    got_lock = await cache.aadd(lock_key, 1, 20)
    if not got_lock:
        stale = await cache.aget(stale_key)
        if stale:
            return HttpResponse(stale, content_type='application/json')
        # No prior data and another request is already fetching: fall through and
        # fetch too (rare cold-start race — better than returning nothing).

    payload = await _fetch_upstream(clat, clon)
    if payload is None:
        if got_lock:
            await cache.adelete(lock_key)
        stale = await cache.aget(stale_key)
        if stale:
            return HttpResponse(stale, content_type='application/json')
        return HttpResponse(orjson.dumps({"available": False}),
                            content_type='application/json')

    body = orjson.dumps(payload)
    await cache.aset(key, body, TTL_FRESH)
    await cache.aset(stale_key, body, TTL_STALE)
    if got_lock:
        await cache.adelete(lock_key)
    return HttpResponse(body, content_type='application/json')
