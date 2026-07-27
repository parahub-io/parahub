"""Environmental stations API: public map feed + owner management.

The map feed is anonymous (public stations only) and reads the cached ``latest``
snapshot — never the reading hypertable — so it stays cheap. Owner endpoints
create/rename/move/delete stations, toggle visibility, and reveal the ingest
token/path used to point a device at wx.parahub.io.
"""

import csv
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from django.contrib.gis.geos import Point
from django.db import IntegrityError, connection
from django.http import StreamingHttpResponse
from django.utils import timezone
from ninja import Schema
from ninja.errors import HttpError

from parahub.auth import OptionalProfileAuth, ProfileAuth
from parahub.ratelimit import ratelimit, user_or_ip

from .base import public_owner_fields, router
from ..models import EnvReading, EnvStation, Property

# A station older than this reports as stale; the map dims it rather than
# implying the reading is current.
STALE_AFTER_SECONDS = 30 * 60


class EnvStationMapOut(Schema):
    id: str
    object_type: str = 'env_station'
    name: str
    source: str
    latitude: float
    longitude: float
    last_reading_at: Optional[str] = None
    age_seconds: Optional[int] = None
    stale: bool = False
    latest: dict = {}
    public_url: str = ''
    # Owner attribution — only when the owner opted in via show_owner
    owner_name: str = ''
    owner_cri: str = ''


class EnvStationOwnerOut(Schema):
    id: str
    object_type: str = 'env_station'
    name: str
    source: str
    latitude: float
    longitude: float
    is_public: bool
    show_owner: bool = False
    public_url: str = ''
    external_id: str = ''
    ingest_token: str
    ingest_path: str = ''
    property_id: Optional[str] = None
    last_reading_at: Optional[str] = None
    latest: dict = {}


class EnvStationCreate(Schema):
    name: str
    source: str = EnvStation.Source.GENERIC
    latitude: float
    longitude: float
    is_public: bool = False
    property_id: Optional[str] = None
    external_id: Optional[str] = None  # AirGradient serial / Ecowitt PASSKEY


class EnvStationPatch(Schema):
    name: Optional[str] = None
    is_public: Optional[bool] = None
    show_owner: Optional[bool] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    external_id: Optional[str] = None
    public_url: Optional[str] = None  # '' clears


def _age(station):
    if not station.last_reading_at:
        return None
    return int((timezone.now() - station.last_reading_at).total_seconds())


def _ingest_path(station) -> str:
    """The upload path a user pastes into the device (Ecowitt) — AirGradient
    matches on serial, so it has no per-station path."""
    if station.source == EnvStation.Source.ECOWITT:
        return f'/ecowitt/{station.ingest_token}'
    return ''


def _owner_out(st) -> EnvStationOwnerOut:
    return EnvStationOwnerOut(
        id=st.id, name=st.name, source=st.source,
        latitude=st.location.y, longitude=st.location.x,
        is_public=st.is_public, show_owner=st.show_owner,
        public_url=st.public_url or '',
        external_id=st.external_id,
        ingest_token=st.ingest_token, ingest_path=_ingest_path(st),
        property_id=st.property_id,
        last_reading_at=st.last_reading_at.isoformat() if st.last_reading_at else None,
        latest=st.latest or {},
    )


@router.get("/env-stations/map", response=List[EnvStationMapOut], auth=None)
@ratelimit(group='iot:env_map', key='ip', rate='120/m')
def env_stations_map(request):
    """Public environmental stations that have reported, for the map layer."""
    out = []
    qs = EnvStation.objects.filter(
        is_public=True, last_reading_at__isnull=False,
    ).select_related('owner').only(
        'id', 'name', 'source', 'location', 'last_reading_at', 'latest',
        'public_url', 'show_owner',
        'owner__local_name', 'owner__display_name', 'owner__name_public',
    )
    for st in qs:
        age = _age(st)
        owner_name, owner_cri = public_owner_fields(st.owner) if st.show_owner else ('', '')
        out.append(EnvStationMapOut(
            id=st.id, name=st.name, source=st.source,
            latitude=st.location.y, longitude=st.location.x,
            last_reading_at=st.last_reading_at.isoformat() if st.last_reading_at else None,
            age_seconds=age,
            stale=(age is not None and age > STALE_AFTER_SECONDS),
            latest=st.latest or {},
            public_url=st.public_url or '',
            owner_name=owner_name, owner_cri=owner_cri,
        ))
    return out


# Every metric column of EnvReading, in the order charts/CSV expose them.
READING_METRICS = [
    'temperature', 'humidity', 'pressure', 'wind_speed', 'wind_gust', 'wind_dir',
    'rain_rate', 'rain_daily', 'solar_radiation', 'uv',
    'pm01', 'pm25', 'pm10', 'co2', 'tvoc_index', 'nox_index',
]


class EnvReadingPoint(Schema):
    t: datetime
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_gust: Optional[float] = None
    wind_dir: Optional[float] = None
    rain_rate: Optional[float] = None
    rain_daily: Optional[float] = None
    solar_radiation: Optional[float] = None
    uv: Optional[float] = None
    pm01: Optional[float] = None
    pm25: Optional[float] = None
    pm10: Optional[float] = None
    co2: Optional[float] = None
    tvoc_index: Optional[float] = None
    nox_index: Optional[float] = None


class EnvReadingsOut(Schema):
    points: List[EnvReadingPoint]
    bucket_minutes: int = 0  # 0 = raw rows


def _readable_station(request, station_id: str) -> EnvStation:
    """Station if the caller may read its history: public → anyone,
    private → owner only. 404 either way so existence never leaks."""
    st = EnvStation.objects.filter(id=station_id).first()
    profile = getattr(request, 'auth_profile', None)
    if not st or (not st.is_public and (not profile or st.owner_id != profile.id)):
        raise HttpError(404, "Station not found")
    return st


@router.get("/env-stations/{station_id}/readings", response=EnvReadingsOut, auth=OptionalProfileAuth())
@ratelimit(group='iot:env_readings', key=user_or_ip, rate='60/m')
def env_station_readings(request, station_id: str, hours: int = 24):
    """Reading history for charts. Raw rows up to 48 h; 30-min averages beyond
    (time_bucket) so a week never ships thousands of points."""
    st = _readable_station(request, station_id)
    hours = max(1, min(hours, 168))
    since = timezone.now() - timedelta(hours=hours)

    if hours <= 48:
        rows = EnvReading.objects.filter(station=st, time__gte=since) \
            .order_by('time').values('time', *READING_METRICS)
        return EnvReadingsOut(points=[
            EnvReadingPoint(t=r['time'], **{m: r[m] for m in READING_METRICS}) for r in rows
        ])

    cols = ', '.join(f'avg({m}) AS {m}' for m in READING_METRICS)
    with connection.cursor() as cur:
        cur.execute(
            f"SELECT time_bucket(interval '30 minutes', time) AS bt, {cols} "
            f"FROM iot_env_reading WHERE station_id = %s AND time >= %s "
            f"GROUP BY bt ORDER BY bt",
            [st.id, since],
        )
        names = [c[0] for c in cur.description]
        points = [
            EnvReadingPoint(t=row[0], **dict(zip(names[1:], row[1:])))
            for row in cur.fetchall()
        ]
    return EnvReadingsOut(points=points, bucket_minutes=30)


class _CsvEcho:
    """Write-through buffer: csv.writer formats a row, we yield it as-is."""

    def write(self, value):
        return value


@router.get("/env-stations/{station_id}/readings.csv", auth=OptionalProfileAuth())
@ratelimit(group='iot:env_readings_csv', key=user_or_ip, rate='10/m')
def env_station_readings_csv(request, station_id: str, hours: int = 720):
    """Raw readings as a streamed CSV for offline analysis — up to the full
    365-day retention window."""
    st = _readable_station(request, station_id)
    hours = max(1, min(hours, 24 * 366))
    since = timezone.now() - timedelta(hours=hours)

    def rows():
        writer = csv.writer(_CsvEcho())
        yield writer.writerow(['time'] + READING_METRICS)
        qs = EnvReading.objects.filter(station=st, time__gte=since) \
            .order_by('time').values_list('time', *READING_METRICS) \
            .iterator(chunk_size=5000)
        for row in qs:
            yield writer.writerow(
                [row[0].isoformat()] + ['' if v is None else v for v in row[1:]])

    resp = StreamingHttpResponse(rows(), content_type='text/csv; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="env-station-{st.id}-{hours}h.csv"'
    return resp


@router.get("/env-stations", response=List[EnvStationOwnerOut], auth=ProfileAuth())
@ratelimit(group='iot:env_list', key=user_or_ip, rate='60/m')
def list_env_stations(request):
    """The caller's own environmental stations (includes ingest token/path)."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")
    return [_owner_out(st) for st in EnvStation.objects.filter(owner=profile)]


@router.post("/env-stations", response=EnvStationOwnerOut, auth=ProfileAuth())
@ratelimit(group='iot:env_create', key=user_or_ip, rate='20/m', method='POST')
def create_env_station(request, payload: EnvStationCreate):
    """Register a new environmental station and mint its ingest token."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")

    source = payload.source if payload.source in EnvStation.Source.values else EnvStation.Source.GENERIC
    prop = None
    if payload.property_id:
        prop = Property.objects.filter(id=payload.property_id, owner=profile).first()
        if not prop:
            raise HttpError(404, "Property not found")

    name = (payload.name or '').strip()[:100]
    if not name:
        raise HttpError(422, "Name is required")

    try:
        st = EnvStation.objects.create(
            owner=profile, name=name, source=source,
            location=Point(payload.longitude, payload.latitude),
            is_public=payload.is_public, property=prop,
            external_id=(payload.external_id or '').strip().lower()[:64],
            ingest_token=secrets.token_hex(10),
        )
    except IntegrityError:
        raise HttpError(409, "A station with this name already exists")
    return _owner_out(st)


@router.patch("/env-stations/{station_id}", response=EnvStationOwnerOut, auth=ProfileAuth())
@ratelimit(group='iot:env_patch', key=user_or_ip, rate='30/m')
def patch_env_station(request, station_id: str, payload: EnvStationPatch):
    """Rename, move, retag, or toggle public visibility of an owned station."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")
    st = EnvStation.objects.filter(id=station_id, owner=profile).first()
    if not st:
        raise HttpError(404, "Station not found")

    fields = []
    if payload.name is not None:
        st.name = payload.name.strip()[:100]
        fields.append('name')
    if payload.is_public is not None:
        st.is_public = payload.is_public
        fields.append('is_public')
    if payload.show_owner is not None:
        st.show_owner = payload.show_owner
        fields.append('show_owner')
    if payload.external_id is not None:
        st.external_id = payload.external_id.strip().lower()[:64]
        fields.append('external_id')
    if payload.public_url is not None:
        url = payload.public_url.strip()[:300]
        if url and not url.startswith('https://'):
            raise HttpError(422, "Public URL must start with https://")
        st.public_url = url
        fields.append('public_url')
    if payload.latitude is not None and payload.longitude is not None:
        st.location = Point(payload.longitude, payload.latitude)
        fields.append('location')

    if fields:
        try:
            st.save(update_fields=fields)
        except IntegrityError:
            raise HttpError(409, "A station with this name already exists")
    return _owner_out(st)


@router.delete("/env-stations/{station_id}", auth=ProfileAuth())
@ratelimit(group='iot:env_delete', key=user_or_ip, rate='20/m')
def delete_env_station(request, station_id: str):
    """Delete an owned station and its readings."""
    profile = request.auth_profile
    if not profile:
        raise HttpError(401, "Authentication required")
    st = EnvStation.objects.filter(id=station_id, owner=profile).first()
    if not st:
        raise HttpError(404, "Station not found")
    st.delete()
    return {"status": "deleted"}
