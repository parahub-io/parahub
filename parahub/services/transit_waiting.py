"""
Waiting-passenger markers — "somebody is waiting for line N here, this direction".

A marker is a triple (stop, route, direction), never a bare stop: a passenger
waiting for a different line is noise to the driver and to the municipality, and
the direction is what nobody can infer for them — the two poles of a stop sit ten
metres apart, well inside browser GPS error, so the tap that places the marker IS
the direction signal. One marker per identity at a time; placing a new one clears
the old.

Storage is Redis-only (CQRS: no high-frequency writes to PostgreSQL). Durable
history for municipalities is a separate 1/min downsample — `snapshot_waiting`.

Lifetime is a rolling lease, not a fixed timeout:
  * a heartbeat from a visible page refreshes `beat` and re-arms the lease, so
    somebody standing for 40 minutes with the page open never vanishes;
  * a marker whose `beat` is older than ACTIVE_WINDOW still shows, dimmed — the
    phone went into a pocket, the human did not leave;
  * LEASE seconds after the last sign of life it is gone entirely;
  * the natural end is arrival: when a vehicle of the awaited (route, direction)
    reaches the stop the marker is dropped server-side (`clear_on_arrival`).

Identity is the profile when signed in, otherwise an HMAC of a client-generated
device id. Anonymous visitors are most of the traffic on stop pages and are
exactly the people standing at the stop, so locking this to accounts would cap
the feature at the number of registered users. Anonymous identities are capped
per IP because a cleared cookie would otherwise mint unlimited phantoms — with
one identity the worst case is one passenger drawn where none stands, which is
not worth a GPS gate that would break for everyone who denies geolocation.

**Placements, not one (stop, route) pair.** Thousands of Lisbon poles are shared
by two operators, each shipping its own `Stop` row, and the route page only ever
looks up its own feed's stop ids. So the caller resolves each awaited line to the
co-located pole that actually serves it (`geo.endpoints.transit.helpers`), and
the marker stores a list of `(ds_id, stop_source_id, route, direction)`
placements. Indexing by serving pole is also what makes the stop page correct for
free: its live layer already pools across co-located poles.
"""

import hashlib
import hmac
import logging
import time

import orjson
from django.conf import settings

from parahub.services.redis_pool import get_redis

logger = logging.getLogger(__name__)

# Beat younger than this → the page is open right now (solid icon).
ACTIVE_WINDOW = 90
# Hard cap since the last sign of life. Re-armed by every heartbeat.
LEASE = 600
# One human can plausibly be waiting for "the 13 or the 15, whichever comes".
MAX_ROUTES = 4
# Anonymous identities allowed to hold a marker from one address at a time.
# A coarse anti-script backstop, NOT a security boundary — deliberately loose:
# Portuguese mobile carriers run CGNAT, so thousands of real passengers share one
# address, and those phones are exactly the ones standing at the pole. A tight cap
# would lock out the target user to stop a troll who, per the threat model, can
# at worst draw one passenger where none stands. The per-IP key is a ZSET scored
# by lease expiry so departed identities fall out of the budget on their own —
# a plain SET only shrank via explicit clears, so on a busy shared address the
# cap filled with people who had long left and blocked the ones arriving.
ANON_PER_IP = 30
# GTFS ids are opaque strings; bound them the way the models do.
MAX_ID_LEN = 100


def _key_marker(identity: str) -> str:
    return f'transit:waiting:m:{identity}'


def key_route(ds_id: str, route_source_id: str) -> str:
    return f'transit:waiting:r:{ds_id}:{route_source_id}'


def key_stop(ds_id: str, stop_source_id: str) -> str:
    return f'transit:waiting:s:{ds_id}:{stop_source_id}'


def _key_ip(ip_hash: str) -> str:
    return f'transit:waiting:ip:{ip_hash}'


# GEO ZSET of occupied poles, member `{ds}:{stop}` — the map's bbox read. Kept
# separate from `transit:geo` (vehicles) so neither read ever filters the other.
KEY_GEO = 'transit:waiting:geo'

# Fired on every marker change regardless of route or stop: a map client watches
# a viewport, not a line, so it cannot subscribe to per-route channels.
CHANNEL_ANY = 'transit:waiting:any'


def channel_route(ds_id: str, route_source_id: str) -> str:
    return f'transit:waiting:route:{ds_id}:{route_source_id}'


def channel_stop(ds_id: str, stop_source_id: str) -> str:
    return f'transit:waiting:stop:{ds_id}:{stop_source_id}'


def _digest(value: str) -> str:
    """Keyed digest of a client-supplied identifier (device id, IP).

    Neither is ours to store in the clear: the device id is a stable
    cross-session handle and the IP is personal data. HMAC with the server
    secret keeps them usable as keys and useless as identifiers.
    """
    return hmac.new(
        settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256
    ).hexdigest()[:24]


def identity_for(profile_id: str | None, device_id: str | None) -> str | None:
    """`p:<profile>` when signed in, `d:<digest>` for an anonymous device."""
    if profile_id:
        return f'p:{profile_id}'
    if device_id and 8 <= len(device_id) <= 128:
        return f'd:{_digest(device_id)}'
    return None


def _valid_id(value) -> bool:
    return isinstance(value, str) and 0 < len(value) <= MAX_ID_LEN


def normalize_lines(raw) -> list[tuple[str, int]]:
    """Validate the requested [(route_source_id, direction_id), ...] set.

    Direction is coerced to 0/1 — the two values the whole transit pipeline uses
    (`transit:rstops:{route}:{dir}`, `RouteStop.direction_id`).
    """
    out = []
    if not isinstance(raw, (list, tuple)):
        return out
    for item in raw:
        if isinstance(item, dict):
            route, direction = item.get('route'), item.get('direction')
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            route, direction = item
        else:
            continue
        if not _valid_id(route):
            continue
        try:
            direction = 1 if int(direction) == 1 else 0
        except (TypeError, ValueError):
            direction = 0
        if (route, direction) not in out:
            out.append((route, direction))
        if len(out) >= MAX_ROUTES:
            break
    return out


class WaitingService:
    """Sync Redis writer/reader. The WS consumer reads the same keys with its own
    async connection and shares the pure decoders below."""

    @classmethod
    def _redis(cls):
        """Pooled sync client on db 0 — where the rest of the transit pipeline lives.

        NOT the Django cache URL: that points at db 1, while the RT daemon and
        both WS consumers read these keys off a plain `Redis(host, port)`, i.e.
        db 0. Writing to the cache db would leave every count empty and the
        arrival auto-clear silently dead, since pub/sub crosses databases but
        keys do not.
        """
        return get_redis()

    # ----- writes -----

    @classmethod
    def set_marker(cls, identity, ds_id, stop_source_id, placements, ip=None, pole_coords=None):
        """Place (or move) this identity's single marker.

        `placements` is `[(ds_id, stop_source_id, route_source_id, direction)]`,
        already resolved to the pole serving each line; `ds_id`/`stop_source_id`
        are the pole the human is standing at (the page they tapped on).
        `pole_coords` maps `(ds_id, stop_source_id) → (lat, lon)` and feeds the
        map's GEO index; omitting it just leaves the marker off the map.

        Returns `{'ok': True, 'marker': {...}}`, or `{'ok': False, 'error': ...}`
        with `ip_cap` / `invalid`.

        Moving is deliberately never rejected. The cost of a hop is the broadcast
        it triggers, not the Redis write, so it is floored where the fan-out
        happens — per subscriber, in the WS consumer. A cooldown on the mover is
        both unkind and useless here: it charges the honest user for correcting
        their own pole, while two taps (unmark, mark elsewhere) walk straight past
        it and cost one broadcast MORE than the move it forbids. The rate ceiling
        that does hold is the endpoint's, per identity and address.
        """
        if not (_valid_id(ds_id) and _valid_id(stop_source_id)) or not placements:
            return {'ok': False, 'error': 'invalid'}

        r = cls._redis()
        now = time.time()
        previous = cls.get_marker(identity)

        # Same pole, different lines (the passenger added "or the 15") continues
        # one wait; a different pole starts a new one.
        same_stop = bool(previous) and (previous['ds_id'], previous['stop_source_id']) == (ds_id, stop_source_id)

        is_anon = identity.startswith('d:')
        ip_key = None
        if is_anon and ip:
            ip_key = _key_ip(_digest(ip))
            # Only a NEW identity can breach the cap — an existing marker moving
            # is already counted, and re-checking would strand it half-erased.
            # Expired scores are swept first: the budget counts placements from
            # the last LEASE window, not everyone who ever stood here.
            if not previous:
                r.zremrangebyscore(ip_key, '-inf', now)
                if r.zcard(ip_key) >= ANON_PER_IP and r.zscore(ip_key, identity) is None:
                    return {'ok': False, 'error': 'ip_cap'}

        if previous:
            cls._unindex(r, identity, previous)

        beat = int(now)
        marker = {
            'ds': ds_id,
            'stop': stop_source_id,
            'pl': orjson.dumps([list(p) for p in placements]).decode(),
            'at': str(int(previous['declared_at']) if same_stop else beat),
            'beat': str(beat),
            # Remembered so clearing releases the per-IP slot; without it a
            # visitor who marks and unmarks would burn the address's budget for
            # a full lease while holding nothing.
            'iph': ip_key or (previous or {}).get('ip_key') or '',
        }

        pipe = r.pipeline(transaction=False)
        pipe.hset(_key_marker(identity), mapping=marker)
        pipe.expire(_key_marker(identity), LEASE)
        cls._index(pipe, identity, placements, beat)
        for (pole_ds, pole_stop), (lat, lon) in (pole_coords or {}).items():
            pipe.geoadd(KEY_GEO, values=[lon, lat, f'{pole_ds}:{pole_stop}'])
        if ip_key:
            pipe.zadd(ip_key, {identity: now + LEASE})
            pipe.expire(ip_key, LEASE)
        pipe.execute()

        cls._publish(r, placements)
        if previous:
            cls._publish(r, previous['placements'])

        return {'ok': True, 'marker': cls.get_marker(identity)}

    @classmethod
    def heartbeat(cls, identity):
        """Re-arm the lease and refresh `beat`. False when there is no marker
        left to refresh (expired, or cleared by arrival) — the client then knows
        to drop its local state without polling for it."""
        marker = cls.get_marker(identity)
        if not marker:
            return False

        r = cls._redis()
        beat = int(time.time())
        pipe = r.pipeline(transaction=False)
        pipe.hset(_key_marker(identity), 'beat', str(beat))
        pipe.expire(_key_marker(identity), LEASE)
        cls._index(pipe, identity, marker['placements'], beat)
        pipe.execute()

        # A beat crossing back over ACTIVE_WINDOW flips the icon from dimmed to
        # solid for every watcher, so it is a visible state change like any other.
        if beat - marker['beat'] > ACTIVE_WINDOW:
            cls._publish(r, marker['placements'])
        return True

    @classmethod
    def clear_marker(cls, identity):
        marker = cls.get_marker(identity)
        if not marker:
            return False
        r = cls._redis()
        cls._unindex(r, identity, marker)
        r.delete(_key_marker(identity))
        if marker['ip_key']:
            r.zrem(marker['ip_key'], identity)
        cls._publish(r, marker['placements'])
        return True

    @classmethod
    def clear_on_arrival(cls, ds_id, stop_source_id, arrived_lines):
        """Drop markers whose awaited line just pulled in — the honest end of a
        wait. `arrived_lines` is an iterable of (route_source_id, direction).

        A multi-line marker goes as soon as ANY awaited line arrives: the person
        boards whatever came first, which is why they listed several.
        """
        arrived = {(route, direction) for route, direction in arrived_lines}
        if not arrived:
            return 0

        r = cls._redis()
        raw = r.hgetall(key_stop(ds_id, stop_source_id))
        cleared = 0
        for identity, value in (raw or {}).items():
            entry = _decode(value)
            if not entry:
                continue
            awaited = {
                (pair[0], 1 if pair[1] == 1 else 0)
                for pair in entry.get('rd', [])
                if isinstance(pair, (list, tuple)) and len(pair) == 2
            }
            if awaited & arrived and cls.clear_marker(identity):
                cleared += 1
        return cleared

    @classmethod
    def _index(cls, pipe, identity, placements, beat):
        """(Re)write both indexes for every placement. Queued on a caller's pipe."""
        by_pole: dict[tuple[str, str], list] = {}
        for ds_id, stop_source_id, route, direction in placements:
            by_pole.setdefault((ds_id, stop_source_id), []).append([route, direction])
            pipe.hset(key_route(ds_id, route), identity, orjson.dumps({
                'b': beat, 'd': direction, 's': stop_source_id,
            }).decode())
            pipe.expire(key_route(ds_id, route), LEASE)
        for (ds_id, stop_source_id), lines in by_pole.items():
            pipe.hset(key_stop(ds_id, stop_source_id), identity, orjson.dumps({
                'b': beat, 'rd': lines,
            }).decode())
            pipe.expire(key_stop(ds_id, stop_source_id), LEASE)

    @classmethod
    def _unindex(cls, r, identity, marker):
        pipe = r.pipeline(transaction=False)
        poles = set()
        for ds_id, stop_source_id, route, _direction in marker['placements']:
            pipe.hdel(key_route(ds_id, route), identity)
            pipe.hdel(key_stop(ds_id, stop_source_id), identity)
            poles.add((ds_id, stop_source_id))
        pipe.execute()

        # Drop the pole from the map index only once the LAST person there is
        # gone — several people wait at one pole and one leaving must not erase
        # the others' pin.
        pipe = r.pipeline(transaction=False)
        for pole_ds, pole_stop in poles:
            pipe.hlen(key_stop(pole_ds, pole_stop))
        remaining = pipe.execute()
        empty = [f'{ds}:{stop}' for (ds, stop), n in zip(poles, remaining) if not n]
        if empty:
            r.zrem(KEY_GEO, *empty)

    @classmethod
    def _publish(cls, r, placements):
        """Nudge subscribers; they re-read Redis themselves. Markers change on a
        human tap, not on the 30s daemon tick, so they get their own channels —
        riding the tick would make an appearing passenger up to half a minute late.
        """
        payload = orjson.dumps({'t': int(time.time())})
        seen = {CHANNEL_ANY}
        pipe = r.pipeline(transaction=False)
        # Map clients watch a viewport, not a line, so they get the broad nudge.
        pipe.publish(CHANNEL_ANY, payload)
        for ds_id, stop_source_id, route, _direction in placements:
            for channel in (channel_stop(ds_id, stop_source_id), channel_route(ds_id, route)):
                if channel not in seen:
                    seen.add(channel)
                    pipe.publish(channel, payload)
        pipe.execute()

    # ----- reads -----

    @classmethod
    def get_marker(cls, identity):
        if not identity:
            return None
        raw = cls._redis().hgetall(_key_marker(identity))
        if not raw:
            return None
        try:
            placements = [
                (ds_id, stop_source_id, route, 1 if int(direction) == 1 else 0)
                for ds_id, stop_source_id, route, direction in orjson.loads(raw.get('pl', '[]'))
            ]
        except (orjson.JSONDecodeError, TypeError, ValueError):
            return None
        if not placements:
            return None
        return {
            'ds_id': raw.get('ds', ''),
            'stop_source_id': raw.get('stop', ''),
            'placements': placements,
            'lines': [(route, direction) for _ds, _stop, route, direction in placements],
            'declared_at': float(raw.get('at', 0) or 0),
            'beat': float(raw.get('beat', 0) or 0),
            'ip_key': raw.get('iph', ''),
        }

    @classmethod
    def route_counts(cls, ds_id, route_source_id):
        r = cls._redis()
        key = key_route(ds_id, route_source_id)
        counts, stale = decode_route_hash(r.hgetall(key))
        if stale:
            r.hdel(key, *stale)
        return counts

    @classmethod
    def stop_counts(cls, ds_id, stop_source_id):
        r = cls._redis()
        key = key_stop(ds_id, stop_source_id)
        counts, stale = decode_stop_hash(r.hgetall(key))
        if stale:
            r.hdel(key, *stale)
        return counts

    @classmethod
    def iter_occupied(cls):
        """Every live placement as (ds_id, route_source_id, direction,
        stop_source_id, total, active) — the snapshot daemon's whole input.
        SCANs the per-route index, so a multi-line marker is counted once per
        line it is waiting for, which is what an operator wants to see."""
        r = cls._redis()
        rows = []
        for key in r.scan_iter(match='transit:waiting:r:*', count=200):
            # `transit:waiting:r:{ds}:{route}` — data-source ids are ULIDs and
            # never contain ':', GTFS route ids sometimes do, so split once.
            ds_id, _, route_source_id = key[len('transit:waiting:r:'):].partition(':')
            if not route_source_id:
                continue
            counts, stale = decode_route_hash(r.hgetall(key))
            if stale:
                r.hdel(key, *stale)
            for direction, per_stop in counts.items():
                for stop_source_id, cell in per_stop.items():
                    rows.append((
                        ds_id, route_source_id, int(direction), stop_source_id,
                        cell['n'], cell['active'],
                    ))
        return rows


# ----- pure decoders (shared with the async WS consumer) -----

def _decode(value):
    try:
        return orjson.loads(value)
    except (orjson.JSONDecodeError, TypeError):
        return None


def decode_route_hash(raw, now=None):
    """`{identity: entry}` → (`{"0": {stop: {"n": total, "active": fresh}}}`, stale_identities).

    Members past the lease are reported back for a lazy HDEL: the index key's own
    TTL is re-armed by every write, so on a busy route a departed passenger would
    otherwise ride along forever.
    """
    now = now if now is not None else time.time()
    counts: dict[str, dict[str, dict[str, int]]] = {}
    stale = []
    for identity, value in (raw or {}).items():
        entry = _decode(value)
        if not entry:
            stale.append(identity)
            continue
        beat = float(entry.get('b', 0) or 0)
        if now - beat > LEASE:
            stale.append(identity)
            continue
        stop_source_id = entry.get('s') or ''
        if not stop_source_id:
            continue
        direction = str(1 if entry.get('d') == 1 else 0)
        cell = counts.setdefault(direction, {}).setdefault(
            stop_source_id, {'n': 0, 'active': 0}
        )
        cell['n'] += 1
        if now - beat <= ACTIVE_WINDOW:
            cell['active'] += 1
    return counts, stale


def decode_stop_people(raw, now=None):
    """`{identity: entry}` → (people, active_people, stale_identities).

    Counts *identities*, not lines: `decode_stop_hash` weights by awaited line,
    which is right for "how many for MY route" but would count somebody waiting
    for "the 13 or the 15" twice on a map pin that means "humans standing here".
    """
    now = now if now is not None else time.time()
    people = active = 0
    stale = []
    for identity, value in (raw or {}).items():
        entry = _decode(value)
        if not entry:
            stale.append(identity)
            continue
        beat = float(entry.get('b', 0) or 0)
        if now - beat > LEASE:
            stale.append(identity)
            continue
        people += 1
        if now - beat <= ACTIVE_WINDOW:
            active += 1
    return people, active, stale


def decode_stop_hash(raw, now=None):
    """`{identity: entry}` → (`[{route, direction, n, active}]`, stale_identities),
    sorted so the board rows render in a stable order."""
    now = now if now is not None else time.time()
    per_line: dict[tuple[str, int], dict[str, int]] = {}
    stale = []
    for identity, value in (raw or {}).items():
        entry = _decode(value)
        if not entry:
            stale.append(identity)
            continue
        beat = float(entry.get('b', 0) or 0)
        if now - beat > LEASE:
            stale.append(identity)
            continue
        for pair in entry.get('rd', []):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            route, direction = pair[0], (1 if pair[1] == 1 else 0)
            cell = per_line.setdefault((route, direction), {'n': 0, 'active': 0})
            cell['n'] += 1
            if now - beat <= ACTIVE_WINDOW:
                cell['active'] += 1
    rows = [
        {'route': route, 'direction': direction, 'n': cell['n'], 'active': cell['active']}
        for (route, direction), cell in per_line.items()
    ]
    rows.sort(key=lambda row: (row['route'], row['direction']))
    return rows, stale
