"""
Сервис для интеграции с Traccar.

Uses direct DB access (Traccar PostgreSQL on port 5435) as primary method,
since Traccar's REST API is blocked by openid.force=true.

Hot path (webhook): Traccar → Redis (GEOADD + HSET + PUBLISH), zero PG writes.
Cold path (daemon): Redis pending → batch INSERT to TimescaleDB (1/min).
"""
import json
import secrets
import base64
import os
import logging
import time as _time
from typing import Optional, Dict, Any, List
from django.db import transaction
from django.conf import settings
from cryptography.fernet import Fernet
from django.contrib.gis.geos import Point
from django.utils import timezone
from datetime import datetime

import math
import pytz
import redis
import psycopg2
import psycopg2.extras

from identity.models import Profile
from .models import IoTDevice, TraccarUser, TrackerLocation, TrackerHistory

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Redis connection pool for tracker pipeline
# ------------------------------------------------------------------ #
_tracker_redis_pool: redis.ConnectionPool | None = None


def _get_tracker_redis() -> redis.Redis:
    """Get sync Redis client for tracker pipeline (connection-pooled)."""
    global _tracker_redis_pool
    if _tracker_redis_pool is None:
        _tracker_redis_pool = redis.ConnectionPool(
            host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
            port=getattr(settings, 'REDIS_PORT', 6379),
            decode_responses=True,
        )
    return redis.Redis(connection_pool=_tracker_redis_pool)


# Traccar DB connection config (separate PostgreSQL instance)
TRACCAR_DB = {
    'host': os.getenv('TRACCAR_DB_HOST', 'localhost'),
    'port': int(os.getenv('TRACCAR_DB_PORT', '5435')),
    'database': os.getenv('TRACCAR_DB_NAME', 'traccar'),
    'user': os.getenv('TRACCAR_DB_USER', 'traccar'),
    'password': os.getenv('TRACCAR_DB_PASSWORD', ''),
}


class TraccarService:
    """Сервис для управления пользователями и устройствами в Traccar.

    Primary access: direct PostgreSQL queries to Traccar DB (port 5435).
    Traccar REST API is unavailable because openid.force=true blocks basic auth.
    """

    # Ключ шифрования для паролей
    ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')

    if not ENCRYPTION_KEY:
        error_msg = (
            "ENCRYPTION_KEY not found in environment variables. "
            "Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        cipher = Fernet(ENCRYPTION_KEY if isinstance(ENCRYPTION_KEY, bytes) else ENCRYPTION_KEY.encode())
    except Exception as e:
        error_msg = f"Invalid ENCRYPTION_KEY: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # ------------------------------------------------------------------ #
    #  DB connection
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_db():
        """Get a connection to Traccar PostgreSQL."""
        return psycopg2.connect(**TRACCAR_DB)

    # ------------------------------------------------------------------ #
    #  Encryption helpers
    # ------------------------------------------------------------------ #

    @classmethod
    def encrypt_password(cls, password: str) -> str:
        return cls.cipher.encrypt(password.encode()).decode()

    @classmethod
    def decrypt_password(cls, encrypted_password: str) -> str:
        return cls.cipher.decrypt(encrypted_password.encode()).decode()

    # ------------------------------------------------------------------ #
    #  Sync: import devices from Traccar into Parahub
    # ------------------------------------------------------------------ #

    @classmethod
    def sync_devices_from_traccar(cls, profile: Profile) -> int:
        """Import/sync devices from Traccar DB for a Parahub profile.

        Finds the Traccar user by matching email, then imports all their
        devices as IoTDevice(type=TRACKER) records.
        Returns count of newly imported devices.
        """
        email = profile.account.email
        if not email:
            return 0

        conn = cls._get_db()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # Find Traccar user by email (OIDC-created)
                cur.execute(
                    "SELECT id, email, name FROM tc_users WHERE email = %s",
                    (email,),
                )
                tc_user = cur.fetchone()
                if not tc_user:
                    return 0

                traccar_user_id = tc_user['id']

                # Ensure TraccarUser record exists in Parahub
                traccar_account, _ = TraccarUser.objects.update_or_create(
                    profile=profile,
                    defaults={
                        'traccar_user_id': traccar_user_id,
                        'traccar_username': email,
                        'traccar_password_encrypted': cls.encrypt_password('oidc-managed'),
                    },
                )

                # Get all devices for this Traccar user
                cur.execute("""
                    SELECT d.id, d.name, d.uniqueid, d.status, d.lastupdate, d.category
                    FROM tc_devices d
                    JOIN tc_user_device ud ON d.id = ud.deviceid
                    WHERE ud.userid = %s
                    ORDER BY d.id
                """, (traccar_user_id,))
                traccar_devices = cur.fetchall()
        finally:
            conn.close()

        # Already linked device IDs
        existing_ids = set(
            IoTDevice.objects.filter(
                owner=profile,
                traccar_device_id__isnull=False,
            ).values_list('traccar_device_id', flat=True)
        )

        imported = 0
        for td in traccar_devices:
            td_id = td['id']
            if td_id in existing_ids:
                # Update name/status for existing devices
                last_update = td['lastupdate']
                if last_update and last_update.tzinfo is None:
                    last_update = last_update.replace(tzinfo=pytz.UTC)
                IoTDevice.objects.filter(
                    owner=profile, traccar_device_id=td_id
                ).update(
                    name=td['name'],
                    last_seen=last_update,
                )
                continue

            # Check if device_id (uniqueId) already exists unlinked
            existing = IoTDevice.objects.filter(
                owner=profile, device_id=td['uniqueid'],
            ).first()

            if existing:
                # Make datetime timezone-aware
                last_update = td['lastupdate']
                if last_update and last_update.tzinfo is None:
                    last_update = last_update.replace(tzinfo=pytz.UTC)

                existing.traccar_device_id = td_id
                existing.name = td['name']
                existing.last_seen = last_update
                existing.save(update_fields=['traccar_device_id', 'name', 'last_seen'])
            else:
                last_update = td['lastupdate']
                if last_update and last_update.tzinfo is None:
                    last_update = last_update.replace(tzinfo=pytz.UTC)

                IoTDevice.objects.create(
                    owner=profile,
                    name=td['name'],
                    device_type='TRACKER',
                    device_id=td['uniqueid'],
                    traccar_device_id=td_id,
                    last_seen=last_update,
                    connection_info={
                        'traccar_device_id': td_id,
                        'traccar_unique_id': td['uniqueid'],
                        'traccar_category': td['category'] or '',
                        'traccar_status': td['status'] or '',
                    },
                )
            imported += 1

        return imported

    # ------------------------------------------------------------------ #
    #  Position fetching (direct DB)
    # ------------------------------------------------------------------ #

    @classmethod
    def get_positions_for_devices(cls, traccar_device_ids: List[int]) -> Dict[int, Dict]:
        """Batch-fetch latest positions for multiple devices from Traccar DB.

        Returns dict: {traccar_device_id: position_dict}
        """
        if not traccar_device_ids:
            return {}

        conn = cls._get_db()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # Use tc_devices.positionid to directly fetch the latest position
                # (O(1) PK lookup instead of DISTINCT ON + sort over millions of rows)
                cur.execute("""
                    SELECT
                        d.id as deviceid, p.latitude, p.longitude, p.altitude,
                        p.speed, p.course, p.accuracy, p.attributes,
                        p.devicetime, d.status
                    FROM tc_devices d
                    JOIN tc_positions p ON p.id = d.positionid
                    WHERE d.id = ANY(%s)
                """, (traccar_device_ids,))

                result = {}
                for row in cur.fetchall():
                    attrs = row['attributes']
                    if isinstance(attrs, str):
                        try:
                            attrs = json.loads(attrs)
                        except (json.JSONDecodeError, TypeError):
                            attrs = {}
                    elif attrs is None:
                        attrs = {}

                    result[row['deviceid']] = {
                        'latitude': row['latitude'],
                        'longitude': row['longitude'],
                        'altitude': row['altitude'],
                        'speed': row['speed'],
                        'course': row['course'],
                        'accuracy': row['accuracy'],
                        'attributes': attrs,
                        'deviceTime': row['devicetime'].isoformat() if row['devicetime'] else None,
                        'traccar_status': (row['status'] or 'unknown').strip(),
                    }
                return result
        finally:
            conn.close()

    @classmethod
    def get_device_position(cls, traccar_device_id: int) -> Optional[Dict[str, Any]]:
        """Get latest position for a single device from Traccar DB."""
        positions = cls.get_positions_for_devices([traccar_device_id])
        return positions.get(traccar_device_id)

    # ------------------------------------------------------------------ #
    #  Webhook: Redis-first position pipeline (zero PG writes in hot path)
    # ------------------------------------------------------------------ #

    # Cache: traccar_device_id → (device_ulid, device_name, owner_id)
    _device_cache: Dict[int, tuple] = {}
    _device_cache_by_uid: Dict[str, tuple] = {}

    # Cache: device_ulid → assignment dict or None. TTL 60s.
    _assignment_cache: Dict[str, tuple] = {}  # ulid → (timestamp, dict|None)
    _ASSIGNMENT_TTL = 60

    # Cache: stop sequences + shapes for transit bridge stop snapping. TTL 600s.
    _stop_seqs: Dict[tuple, list] = {}  # (route_source_id, direction_id) → [StopPoint]
    _snap_shapes: Dict[tuple, Any] = {}  # (route_source_id, direction_id) → ShapeData
    _stop_seqs_ts: float = 0
    _STOP_SEQS_TTL = 600

    @classmethod
    def _get_assignment(cls, device_ulid: str) -> Optional[Dict]:
        """Get active VehicleAssignment for device (cached 60s)."""
        now = _time.time()
        cached = cls._assignment_cache.get(device_ulid)
        if cached and (now - cached[0]) < cls._ASSIGNMENT_TTL:
            return cached[1]

        from .models import VehicleAssignment
        from django.utils import timezone as tz
        today = tz.localdate()
        assignment = (
            VehicleAssignment.objects
            .filter(
                device_id=device_ulid,
                date=today,
                status__in=['ASSIGNED', 'ACTIVE'],
            )
            .select_related('route', 'route__agency', 'data_source')
            .first()
        )
        if assignment:
            route = assignment.route
            info = {
                'assignment_id': str(assignment.id),
                'ds_id': str(assignment.data_source_id),
                'route_source_id': route.source_id,
                'route_color': route.route_color or '',
                'route_name': route.short_name,
                'route_type': route.route_type,
                'direction_id': assignment.direction_id,
                'vehicle_id': assignment.display_vehicle_id or f'D{device_ulid[:8]}',
                'status': assignment.status,
            }
            cls._assignment_cache[device_ulid] = (now, info)
            return info

        cls._assignment_cache[device_ulid] = (now, None)
        return None

    @classmethod
    def invalidate_assignment_cache(cls, device_ulid: str):
        """Called from dispatch API on assignment create/update/cancel."""
        cls._assignment_cache.pop(device_ulid, None)

    @classmethod
    def _load_snap_cache(cls):
        """Load stop sequences + shapes from DB (cached 600s)."""
        now = _time.time()
        if cls._stop_seqs and (now - cls._stop_seqs_ts) < cls._STOP_SEQS_TTL:
            return

        from geo.models import RouteStop, Trip
        from parahub.services.transit_rt import StopPoint, StopOnShape, ShapeData

        # 1. Stop sequences
        route_stops_map: Dict[int, list] = {}  # route.id → [(source_id, name, Point)]
        stop_seqs_raw: Dict[tuple, list] = {}
        for rs in (RouteStop.objects
                   .select_related('stop', 'route')
                   .only('route_id', 'route__source_id', 'stop__source_id',
                         'stop__name', 'stop__location', 'sequence', 'direction_id')
                   .order_by('route_id', 'direction_id', 'sequence')):
            route_src = rs.route.source_id
            dir_id = rs.direction_id if rs.direction_id is not None else 0
            loc = rs.stop.location
            stop_seqs_raw.setdefault((route_src, dir_id), []).append(
                (rs.sequence, StopPoint(source_id=rs.stop.source_id, lat=loc.y, lon=loc.x))
            )
            route_stops_map.setdefault(rs.route_id, []).append(
                (rs.stop.source_id, rs.stop.name, rs.stop.location)
            )

        stop_seqs = {}
        for key, items in stop_seqs_raw.items():
            items.sort(key=lambda x: x[0])
            stop_seqs[key] = [sp for _, sp in items]

        # 2. Shapes (for shape-projection snapping when available)
        # Uses deduplicated Shape table via shape_ref FK
        shapes: Dict[tuple, Any] = {}
        seen = set()
        for trip in (Trip.objects
                     .exclude(shape_ref__isnull=True)
                     .select_related('route', 'shape_ref')
                     .only('route__source_id', 'route_id', 'direction_id',
                           'shape_ref__geometry', 'shape_ref__length_m')
                     .iterator(chunk_size=2000)):
            key = (trip.route.source_id, trip.direction_id)
            if key in seen:
                continue
            seen.add(key)

            line = trip.shape_ref.geometry if trip.shape_ref else None
            if not line or len(line.coords) < 2:
                continue

            stops_data = route_stops_map.get(trip.route_id, [])
            stops_on_shape = []
            for src_id, name, stop_point in stops_data:
                fraction = line.project_normalized(stop_point)
                stops_on_shape.append(StopOnShape(
                    source_id=src_id, name=name, fraction=fraction,
                ))
            stops_on_shape.sort(key=lambda s: s.fraction)

            length_m = trip.shape_ref.length_m if trip.shape_ref else 0.0

            shapes[key] = ShapeData(line=line, stops=stops_on_shape, length_m=length_m)

        cls._stop_seqs = stop_seqs
        cls._snap_shapes = shapes
        cls._stop_seqs_ts = now
        logger.info(
            f"Snap cache loaded: {len(stop_seqs)} stop-seqs, {len(shapes)} shapes"
        )

    @classmethod
    def _snap_nearest_stop(cls, lat: float, lon: float,
                           route_source_id: str, direction_id: int | None) -> str:
        """Snap vehicle to nearest stop. Shape-projection if available, distance fallback."""
        cls._load_snap_cache()

        # --- Try shape-projection first (more accurate: respects route geometry) ---
        from django.contrib.gis.geos import Point as GEOSPoint
        import bisect

        shape_data = cls._snap_shapes.get((route_source_id, direction_id))
        if shape_data is None and direction_id is None:
            sd0 = cls._snap_shapes.get((route_source_id, 0))
            sd1 = cls._snap_shapes.get((route_source_id, 1))
            if sd0 and sd1:
                pt = GEOSPoint(lon, lat, srid=4326)
                shape_data = sd0 if sd0.line.distance(pt) <= sd1.line.distance(pt) else sd1
            else:
                shape_data = sd0 or sd1

        if shape_data and shape_data.stops:
            pt = GEOSPoint(lon, lat, srid=4326)
            dist_m = shape_data.line.distance(pt) * 100000
            if dist_m <= 500:
                frac = shape_data.line.project_normalized(pt)
                fractions = [s.fraction for s in shape_data.stops]
                idx = bisect.bisect_left(fractions, frac)
                best_stop = None
                best_diff = float('inf')
                for ci in [idx - 1, idx, idx + 1]:
                    if 0 <= ci < len(shape_data.stops):
                        diff = abs(shape_data.stops[ci].fraction - frac)
                        if diff < best_diff:
                            best_diff = diff
                            best_stop = shape_data.stops[ci]
                if best_stop:
                    return best_stop.source_id

        # --- Fallback: nearest stop by distance (works without shapes) ---
        stops = cls._stop_seqs.get((route_source_id, direction_id))
        if not stops and direction_id is None:
            stops = cls._stop_seqs.get((route_source_id, 0)) or cls._stop_seqs.get((route_source_id, 1))

        if not stops:
            return ''

        cos_lat = math.cos(math.radians(lat))
        best_sp = None
        best_dist_sq = float('inf')
        for sp in stops:
            dlat = (sp.lat - lat) * 110540
            dlon = (sp.lon - lon) * 111320 * cos_lat
            d_sq = dlat * dlat + dlon * dlon
            if d_sq < best_dist_sq:
                best_dist_sq = d_sq
                best_sp = sp

        if best_sp is None or best_dist_sq > 500 * 500:
            return ''

        return best_sp.source_id

    @classmethod
    def _lookup_device(cls, traccar_device_id, device_unique_id) -> Optional[tuple]:
        """Lookup device with in-memory cache. Returns (ulid, name, owner_id) or None."""
        # Try cache first
        if traccar_device_id and traccar_device_id in cls._device_cache:
            return cls._device_cache[traccar_device_id]
        if device_unique_id and device_unique_id in cls._device_cache_by_uid:
            return cls._device_cache_by_uid[device_unique_id]

        # DB lookup
        device = None
        if traccar_device_id:
            device = IoTDevice.objects.filter(
                traccar_device_id=traccar_device_id,
                device_type='TRACKER',
            ).select_related('owner').first()
        if not device and device_unique_id:
            device = IoTDevice.objects.filter(
                device_id=device_unique_id,
                device_type='TRACKER',
            ).select_related('owner').first()

        if not device:
            return None

        info = (str(device.id), device.name, str(device.owner_id))
        if traccar_device_id:
            cls._device_cache[traccar_device_id] = info
        if device_unique_id:
            cls._device_cache_by_uid[device_unique_id] = info
        return info

    @classmethod
    def process_position_redis(cls, data: Dict[str, Any]) -> bool:
        """Process position via Redis pipeline (zero PostgreSQL writes).

        Writes: GEOADD tracker:geo, HSET tracker:vdata, HSET tracker:pending,
        PUBLISH tracker:tick. DB write limited to device.last_seen update.
        """
        try:
            traccar_device_id = data.get('device', {}).get('id')
            device_unique_id = data.get('device', {}).get('uniqueId')

            if not traccar_device_id and not device_unique_id:
                return False

            device_info = cls._lookup_device(traccar_device_id, device_unique_id)
            if not device_info:
                return False

            device_ulid, device_name, owner_id = device_info

            position = data.get('position', {})
            lat = position.get('latitude', 0)
            lon = position.get('longitude', 0)
            if not lat and not lon:
                return False

            speed_knots = position.get('speed', 0) or 0
            speed_kmh = round(speed_knots * 1.852, 1)
            battery = position.get('attributes', {}).get('batteryLevel')
            now = int(_time.time())

            # Use Traccar fixTime if available, else serverTime, else now
            fix_time = position.get('fixTime') or position.get('serverTime')
            pos_epoch = now
            if fix_time:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(fix_time.replace('Z', '+00:00'))
                    pos_epoch = int(dt.timestamp())
                except (ValueError, AttributeError):
                    pass

            # Skip if existing position in Redis is newer or too recent (<5s throttle)
            r = _get_tracker_redis()
            existing_raw = r.hget('tracker:vdata', device_ulid)
            if existing_raw:
                try:
                    existing_t = json.loads(existing_raw).get('t', 0)
                    if pos_epoch < existing_t:
                        return False  # late GPS buffer — discard
                    if pos_epoch - existing_t < 5:
                        return False  # throttle: max 1 update per 5s per device
                except (json.JSONDecodeError, TypeError):
                    pass

            vdata = json.dumps({
                'dev': device_ulid,
                'name': device_name,
                'owner': owner_id,
                'lat': lat,
                'lon': lon,
                'spd': speed_kmh,
                'hdg': position.get('course'),
                'alt': position.get('altitude'),
                'bat': int(battery) if battery is not None else None,
                'sat': position.get('attributes', {}).get('sat'),
                'acc': position.get('accuracy'),
                't': pos_epoch,
            }, separators=(',', ':'))

            pipe = r.pipeline(transaction=False)
            pipe.geoadd('tracker:geo', (lon, lat, device_ulid))
            pipe.hset('tracker:vdata', device_ulid, vdata)
            pipe.hset('tracker:pending', device_ulid, vdata)
            pipe.publish('tracker:tick', device_ulid)
            pipe.execute()

            # last_seen is derived from Redis tracker:vdata['t'] at read time
            # (no per-position PG write — saves ~19K writes/day)

            # --- Transit bridge: inject into transit pipeline if assigned ---
            assignment = cls._get_assignment(device_ulid)
            if assignment:
                ds_id = assignment['ds_id']
                vid = assignment['vehicle_id']
                member = f'{ds_id}:{vid}'
                bearing = position.get('course')

                transit_vdata = json.dumps({
                    'v': vid,
                    'lat': lat, 'lon': lon,
                    'b': bearing,
                    's': speed_kmh,
                    'r': assignment['route_source_id'],
                    'rc': assignment['route_color'],
                    'rn': assignment['route_name'],
                    'rt': assignment['route_type'],
                    'st': 'IN_TRANSIT_TO',
                    't': now,
                    'tid': '',
                    'sid': cls._snap_nearest_stop(lat, lon, assignment['route_source_id'], assignment['direction_id']),
                    'd': assignment['direction_id'],
                    'src': 'dispatch',
                }, separators=(',', ':'))

                pipe2 = r.pipeline(transaction=False)
                pipe2.geoadd('transit:geo', (lon, lat, member))
                pipe2.hset('transit:vdata', member, transit_vdata)
                pipe2.sadd(f'transit:members:{ds_id}', member)
                pipe2.expire(f'transit:members:{ds_id}', 300)
                pipe2.publish('transit:tick', str(now))
                pipe2.execute()

                # Auto-activate on first position
                if assignment['status'] == 'ASSIGNED':
                    from .models import VehicleAssignment
                    VehicleAssignment.objects.filter(
                        id=assignment['assignment_id'],
                        status='ASSIGNED',
                    ).update(status='ACTIVE')
                    cls.invalidate_assignment_cache(device_ulid)

            return True

        except Exception as e:
            logger.error(f"Error processing position (Redis): {e}", exc_info=True)
            return False

    # ------------------------------------------------------------------ #
    #  Legacy webhook (deprecated — kept for rollback safety)
    # ------------------------------------------------------------------ #

    @classmethod
    def process_position_webhook(cls, data: Dict[str, Any]) -> bool:
        """DEPRECATED: Old PostgreSQL-per-position path. Use process_position_redis()."""
        try:
            traccar_device_id = data.get('device', {}).get('id')
            device_unique_id = data.get('device', {}).get('uniqueId')

            if not traccar_device_id and not device_unique_id:
                return False

            device = None
            if traccar_device_id:
                device = IoTDevice.objects.filter(
                    traccar_device_id=traccar_device_id,
                    device_type='TRACKER',
                ).first()
            if not device and device_unique_id:
                device = IoTDevice.objects.filter(
                    device_id=device_unique_id,
                    device_type='TRACKER',
                ).first()

            if not device:
                return False

            position = data.get('position', {})
            if not position.get('latitude') and not position.get('longitude'):
                return False

            location = Point(
                position.get('longitude', 0),
                position.get('latitude', 0),
                srid=4326,
            )

            device_time_str = position.get('deviceTime', '')
            device_timestamp = datetime.fromisoformat(
                device_time_str.replace('Z', '+00:00')
            ) if device_time_str else timezone.now()

            speed_knots = position.get('speed', 0) or 0
            speed_kmh = speed_knots * 1.852
            battery = position.get('attributes', {}).get('batteryLevel')

            TrackerLocation.objects.update_or_create(
                device=device,
                defaults={
                    'location': location,
                    'altitude': position.get('altitude'),
                    'speed': speed_kmh,
                    'heading': position.get('course'),
                    'accuracy': position.get('accuracy'),
                    'battery_level': int(battery) if battery is not None else None,
                    'satellites': position.get('attributes', {}).get('sat'),
                    'device_timestamp': device_timestamp,
                },
            )

            device.last_seen = device_timestamp
            device.save(update_fields=['last_seen'])

            return True

        except Exception as e:
            logger.error(f"Error processing position webhook: {e}", exc_info=True)
            return False

    # ------------------------------------------------------------------ #
    #  Device status (direct DB)
    # ------------------------------------------------------------------ #

    @classmethod
    def get_device_status(cls, traccar_device_id: int) -> Optional[Dict[str, Any]]:
        """Get device status from Traccar DB."""
        conn = cls._get_db()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    "SELECT id, name, uniqueid, status, lastupdate FROM tc_devices WHERE id = %s",
                    (traccar_device_id,),
                )
                row = cur.fetchone()
                if row:
                    return dict(row)
                return None
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    #  Delete device (direct DB)
    # ------------------------------------------------------------------ #

    @classmethod
    def delete_device(cls, traccar_device_id: int) -> bool:
        """Delete device from Traccar DB."""
        conn = cls._get_db()
        try:
            with conn.cursor() as cur:
                # Remove permissions first
                cur.execute("DELETE FROM tc_user_device WHERE deviceid = %s", (traccar_device_id,))
                cur.execute("DELETE FROM tc_group_device WHERE deviceid = %s", (traccar_device_id,))
                # Remove positions
                cur.execute("DELETE FROM tc_positions WHERE deviceid = %s", (traccar_device_id,))
                # Remove device
                cur.execute("DELETE FROM tc_devices WHERE id = %s", (traccar_device_id,))
                conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete Traccar device {traccar_device_id}: {e}")
            return False
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    #  Legacy: password/token helpers (kept for backward compatibility)
    # ------------------------------------------------------------------ #

    @classmethod
    def generate_sso_token(cls, traccar_user: TraccarUser) -> str:
        username = traccar_user.traccar_username
        password = cls.decrypt_password(traccar_user.traccar_password_encrypted)
        credentials = f"{username}:{password}"
        return base64.b64encode(credentials.encode()).decode()

    # ------------------------------------------------------------------ #
    #  Redis reads for live tracker positions
    # ------------------------------------------------------------------ #

    @classmethod
    def get_positions_from_redis(cls, device_ulids: List[str]) -> Dict[str, Dict]:
        """Batch-read live positions from Redis tracker:vdata.

        Returns dict: {device_ulid: parsed_vdata_dict}
        """
        if not device_ulids:
            return {}
        r = _get_tracker_redis()
        raw_values = r.hmget('tracker:vdata', *device_ulids)
        result = {}
        for ulid, raw in zip(device_ulids, raw_values):
            if raw:
                try:
                    result[ulid] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    pass
        return result

    @classmethod
    def cleanup_device_redis(cls, device_ulid: str):
        """Remove device from Redis geo index + vdata on deletion."""
        try:
            r = _get_tracker_redis()
            pipe = r.pipeline(transaction=False)
            pipe.zrem('tracker:geo', device_ulid)
            pipe.hdel('tracker:vdata', device_ulid)
            pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to cleanup Redis for device {device_ulid}: {e}")
