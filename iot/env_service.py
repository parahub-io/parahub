"""Environmental station ingest helpers, shared by the push endpoints
(``ingest_views``) and the AirGradient poll bridge (``poll_env_stations``).

Every parser returns a dict of normalized SI metric values (°C, %, hPa, km/h,
mm, µg/m³, ppm). Missing metrics are simply absent; ``record_reading`` stores
the subset and refreshes the station's compact map snapshot.
"""

from django.utils import timezone

from parahub.services.ws_publish import ws_publish

from .aqi import us_aqi_pm25
from .models import EnvReading

# Metrics carried in the map/panel snapshot and the reading row.
SNAPSHOT_FIELDS = [
    'temperature', 'humidity', 'pressure', 'wind_speed', 'wind_gust',
    'wind_dir', 'rain_rate', 'rain_daily', 'solar_radiation', 'uv',
    'pm01', 'pm25', 'pm10', 'co2', 'tvoc_index', 'nox_index',
]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _f2c(v):
    v = _f(v)
    return round((v - 32) * 5.0 / 9.0, 2) if v is not None else None


def _mph2kmh(v):
    v = _f(v)
    return round(v * 1.609344, 2) if v is not None else None


def _inhg2hpa(v):
    v = _f(v)
    return round(v * 33.863886, 2) if v is not None else None


def _in2mm(v):
    v = _f(v)
    return round(v * 25.4, 2) if v is not None else None


def from_ecowitt(post):
    """Ecowitt "Customized upload" form fields (imperial) → normalized SI dict.

    Ecowitt posts application/x-www-form-urlencoded; ``post`` is a QueryDict /
    plain dict. Only outdoor fields are mapped (indoor tempinf/humidityin are
    left in ``raw``). See the Fine Offset / Ecowitt protocol.
    """
    return {
        'temperature': _f2c(post.get('tempf')),
        'humidity': _f(post.get('humidity')),
        'pressure': _inhg2hpa(post.get('baromrelin')),
        'wind_speed': _mph2kmh(post.get('windspeedmph')),
        'wind_gust': _mph2kmh(post.get('windgustmph')),
        'wind_dir': _f(post.get('winddir')),
        'rain_rate': _in2mm(post.get('rainratein')),
        'rain_daily': _in2mm(post.get('dailyrainin')),
        'solar_radiation': _f(post.get('solarradiation')),
        'uv': _f(post.get('uv')),
        # Some Ecowitt gateways relay an attached PM2.5 channel.
        'pm25': _f(post.get('pm25') or post.get('pm25_ch1')),
    }


def from_airgradient(data):
    """AirGradient measurement JSON → normalized SI dict.

    Keys match the local ``/measures/current`` schema (verified live on an
    O-1PST). Temperature/humidity already SI; PM already µg/m³. Prefers the
    compensated PM2.5/temp/humidity when present (the device's corrected values).
    """
    return {
        'temperature': _f(data.get('atmpCompensated', data.get('atmp'))),
        'humidity': _f(data.get('rhumCompensated', data.get('rhum'))),
        'pm01': _f(data.get('pm01')),
        'pm25': _f(data.get('pm02Compensated', data.get('pm02'))),
        'pm10': _f(data.get('pm10')),
        'co2': _f(data.get('rco2')),
        'tvoc_index': _f(data.get('tvocIndex')),
        'nox_index': _f(data.get('noxIndex')),
    }


def record_reading(station, values, raw=None, at=None):
    """Persist an ``EnvReading`` from normalized values and refresh the station
    snapshot. None values are dropped. Returns the reading."""
    at = at or timezone.now()
    fields = {k: values.get(k) for k in SNAPSHOT_FIELDS if values.get(k) is not None}
    reading = EnvReading(station=station, time=at, raw=raw or {}, **fields)
    reading.save()

    snap = dict(fields)
    aqi, category = us_aqi_pm25(fields.get('pm25'))
    if aqi is not None:
        snap['aqi'] = aqi
        snap['aqi_category'] = category
    station.latest = snap
    station.last_reading_at = at
    station.save(update_fields=['latest', 'last_reading_at'])

    # Live push to any open map panel subscribed to this station (public feed,
    # see parahub/consumers/env.py). Fire-and-forget; ws_publish swallows errors.
    ws_publish('env:tick', {
        'id': station.id,
        'name': station.name,
        'source': station.source,
        'is_public': station.is_public,
        'lat': station.location.y,
        'lon': station.location.x,
        'last_reading_at': at.isoformat(),
        'latest': snap,
    })
    return reading
