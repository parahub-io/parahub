"""
Daemon: Metro de Lisboa live layer (rt_kind='arrivals').

ML has no GPS (trains in tunnels). Its real-time API publishes arrival-time
predictions per station (`tempoChegada1/2/3` seconds). parahub's entire live
layer is vehicle-position-centric, so we *reconstruct* train positions by
interpolating along the GTFS route geometry we imported, then emit standard
`vehicles` dicts into the SAME Redis pipeline as `fetch_transit_rt` — so metro
trains appear on /map and route pages, and get an ETA, with no new frontend.

Pipeline parity with fetch_transit_rt (same Redis contract):
  - Django cache  transit:rt:{ds_id}          (schedule endpoint reads this)
  - GEO           transit:geo  + transit:vdata (map GEOSEARCH)
  - members set   transit:members:{ds_id}      (stale cleanup, 300s TTL)
  - route batch   transit_route:{ds_id}_{rsrc} (route-page live icons)
  - tick          transit:tick                 (WS refresh signal)

STT is intentionally NOT run: positions are derived from authoritative arrival
predictions, so ETA = tempoChegada directly (no segment-time learning needed).
Headsign = the train's true terminus via the destino crosswalk (/infoDestinos),
falling back to the geometric line end — short-turn trains (Campo Grande,
Martim Moniz, ...) would otherwise be labeled with the full-line terminus.

Credentials: .secrets/ml_credentials.json (gitignored). The PoC set is the
leaked legacy Bustime creds — replace with Parahub-registered creds before
real use. TLS: pinned CA chain (CA_BUNDLE) — the gateway omits its intermediate.
Systemd: parahub-ml-rt.service (persistent; line models self-refresh every
MODELS_TTL_S, so weekly GTFS reimports need no restart hook).

Usage:
    python3 manage.py fetch_metro_lisboa_rt --once --dry-run   # print positions, no Redis
    python3 manage.py fetch_metro_lisboa_rt --once             # one poll → Redis
    python3 manage.py fetch_metro_lisboa_rt                    # daemon loop
"""

import base64
import json
import logging
import math
import os
import time
from dataclasses import dataclass, field

import orjson
import redis as redis_sync
import requests
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from geo.models import Agency, Stop, TransitDataSource
from parahub.services.transit_rt import RouteCache

logger = logging.getLogger(__name__)

SLUG = 'metro-lisboa'
ARRIVALS_EP = '/tempoEspera/Estacao/todos'
DESTINOS_EP = '/infoDestinos/todos'
CREDS_PATH = os.path.join(settings.BASE_DIR, '.secrets', 'ml_credentials.json')
# api.metrolisboa.pt:8243 (WSO2 gateway) serves its leaf cert without the
# intermediate, so the default trust store can't build the chain. Pin the
# Sectigo OV R36 intermediate + Root R46 instead of verify=False; fails
# closed (surfaces in last_error) if ML ever changes CA — update the file.
CA_BUNDLE = os.path.join(settings.BASE_DIR, 'geo', 'data', 'ml_ca_chain.pem')
MODELS_TTL_S = 600       # rebuild line models — GTFS reimport can swap shapes under us

# Interpolation guards
SEG_TIME_MIN = 30        # s — clamp estimated inter-station travel time
SEG_TIME_MAX = 240
SEG_TIME_FALLBACK = 90
MEMBERS_TTL = 300        # mirror fetch_transit_rt


def _sstr(v):
    """ML API fields switch between str and int across releases (id_destino,
    comboio, tempoChegada turned int 2026-06-12) — coerce before .strip()."""
    return str(v).strip() if v is not None else ''


# ---------------------------------------------------------------------------
# Line model: canonical geometry + station→fraction for one metro line
# ---------------------------------------------------------------------------

@dataclass
class LineModel:
    route_src: str
    line: object                       # GEOS LineString (SRID 4326)
    color: str
    short_name: str
    route_type: int
    place_slug: str
    route_slug: str
    canon_dir: int
    order: list = field(default_factory=list)          # [station_code,...] ascending fraction
    frac: dict = field(default_factory=dict)           # station_code → fraction
    coord: dict = field(default_factory=dict)          # station_code → (lat, lon)
    name: dict = field(default_factory=dict)           # station_code → station name

    @property
    def station_set(self):
        return set(self.order)


def _bearing(lat1, lon1, lat2, lon2):
    """Initial bearing (deg) from point 1 to point 2."""
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) -
         math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dlon))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


class Command(BaseCommand):
    help = "Daemon: Metro de Lisboa live trains via arrival-time interpolation"

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Single poll then exit')
        parser.add_argument('--dry-run', action='store_true',
                            help='Reconstruct + print positions, do not write Redis')
        parser.add_argument('--interval', type=int, default=0,
                            help='Override poll interval seconds (0 = ds.rt_interval)')

    # -- credentials / auth ------------------------------------------------

    def _load_creds(self):
        if not os.path.exists(CREDS_PATH):
            raise CommandError(f"Missing ML credentials at {CREDS_PATH}")
        with open(CREDS_PATH) as f:
            return json.load(f)

    def _auth(self, creds):
        h = {"Authorization": "Basic " + base64.b64encode(
            f"{creds['consumer_key']}:{creds['consumer_secret']}".encode()).decode()}
        r = requests.post(creds['token_url'],
                          data={"grant_type": "password",
                                "username": creds['username'], "password": creds['password']},
                          headers=h, verify=CA_BUNDLE, timeout=30)
        r.raise_for_status()
        j = r.json()
        self._token = j['access_token']
        self._token_exp = time.time() + j.get('expires_in', 3600) - 120

    def _get(self, creds, ep):
        if not getattr(self, '_token', None) or time.time() >= self._token_exp:
            self._auth(creds)
        r = requests.get(creds['base_url'] + ep,
                         headers={"Authorization": f"Bearer {self._token}", "accept": "application/json"},
                         verify=CA_BUNDLE, timeout=30)
        r.raise_for_status()
        return r.json()

    # -- line models -------------------------------------------------------

    def _build_models(self, ds_id):
        """Per-line canonical geometry + station→fraction, station-normalized."""
        rc = RouteCache()
        route_info, headsign_info, shapes, stop_seqs = rc._load_all([ds_id])

        # station normalization (platform → parent station) so ML 2-letter
        # station ids (CG) match GTFS route-stop ids that are platform-level (CG4).
        # Agency identity = (source_id, data_source), never source_id alone — the
        # feed has exactly one agency, so scope by data source.
        ag = Agency.objects.get(data_source_id=ds_id)
        norm = {}
        for s in Stop.objects.filter(agency=ag).select_related("parent_station"):
            norm[s.source_id] = s.parent_station.source_id if s.parent_station else s.source_id

        # group shapes by route; pick the most-complete (most stations, then longest)
        by_route = {}
        for (rsrc, d), sd in shapes.items():
            by_route.setdefault(rsrc, []).append((d, sd))

        models = {}
        for rsrc, variants in by_route.items():
            def score(item):
                d, sd = item
                codes = {norm.get(st.source_id, st.source_id) for st in sd.stops}
                return (len(codes), sd.length_m)
            canon_dir, sd = max(variants, key=score)

            color, short_name, place_slug, rtype, route_slug = route_info.get(
                rsrc, ('', '', '', 1, ''))

            m = LineModel(route_src=rsrc, line=sd.line, color=color,
                          short_name=short_name, route_type=rtype, place_slug=place_slug,
                          route_slug=route_slug, canon_dir=canon_dir)

            seen = set()
            for st in sorted(sd.stops, key=lambda x: x.fraction):
                code = norm.get(st.source_id, st.source_id)
                if code in seen:
                    continue
                seen.add(code)
                pt = sd.line.interpolate_normalized(st.fraction)
                m.order.append(code)
                m.frac[code] = st.fraction
                m.coord[code] = (pt.y, pt.x)
                m.name[code] = st.name
            models[rsrc] = m
        return models

    def _load_destinos(self, creds, models):
        """destino id → display name (ML's arrivals carry a numeric destino code).

        Resolving it gives the train's TRUE terminus — short-turn trains would
        otherwise inherit the geometric line end. Names are matched back to the
        imported GTFS station names (ML writes "Baixa-Chiado", GTFS "Baixa /
        Chiado") so headsigns stay consistent with the rest of the UI; unmatched
        names pass through as-is. Failure → empty map → geometric fallback.
        """
        def norm(s):
            return ''.join(ch for ch in s.lower() if ch.isalnum())

        station_names = {}
        for m in models.values():
            for name in m.name.values():
                station_names.setdefault(norm(name), name)
        out = {}
        try:
            data = self._get(creds, DESTINOS_EP)
            rows = data.get('resposta', []) if isinstance(data, dict) else []
            for row in rows:
                did = _sstr(row.get('id_destino'))
                nome = _sstr(row.get('nome_destino'))
                if did and nome:
                    out[did] = station_names.get(norm(nome), nome)
        except Exception as e:
            logger.warning(f"ML destinos crosswalk unavailable ({e}) — geometric headsigns")
        return out

    # -- reconstruction ----------------------------------------------------

    def _reconstruct(self, arrivals, models, destinos, now):
        """ML arrival records → list of reconstructed vehicle dicts."""
        # group predictions by train number
        trains = {}   # comboio → list[(station, tempo_s, destino)]
        for a in arrivals:
            station = _sstr(a.get('stop_id'))
            if _sstr(a.get('sairServico')) == '1' or not station:
                continue
            for n in (1, 2, 3):
                key = 'comboio' if n == 1 else f'comboio{n}'
                tkey = f'tempoChegada{n}'
                c = _sstr(a.get(key))
                t = _sstr(a.get(tkey))
                if not c or not t or t == '--':
                    continue
                try:
                    ts = int(t)
                except ValueError:
                    continue
                trains.setdefault(c, []).append((station, ts, a.get('destino', '')))

        vehicles = []
        for comboio, obs in trains.items():
            # dedup by station keeping smallest tempo; sort by tempo asc
            best = {}
            for station, ts, dest in obs:
                if station not in best or ts < best[station][0]:
                    best[station] = (ts, dest)
            seq = sorted(((ts, st, dest) for st, (ts, dest) in best.items()))
            if not seq:
                continue

            # identify line: route whose station set covers the most of this train
            cand = [(len(m.station_set & {st for _, st, _ in seq}), rsrc, m)
                    for rsrc, m in models.items()]
            overlap, rsrc, m = max(cand)
            if overlap == 0:
                continue

            # keep only stations on this line, re-sort
            seq = [(ts, st, dest) for ts, st, dest in seq if st in m.frac]
            if not seq:
                continue
            t_next, s_next, dest = seq[0]
            f_next = m.frac[s_next]

            v = self._mk_vehicle(comboio, m, seq, t_next, s_next, f_next, now,
                                 dest_name=destinos.get(_sstr(dest)))
            if v:
                vehicles.append(v)
        return vehicles

    def _mk_vehicle(self, comboio, m, seq, t_next, s_next, f_next, now, dest_name=None):
        # travel direction along the fraction axis: how fraction changes as
        # tempoChegada grows (later stations the train will reach)
        dir_sign = 0
        for ts, st, _ in seq[1:]:
            df = m.frac[st] - f_next
            if abs(df) > 1e-6:
                dir_sign = 1 if df > 0 else -1
                break

        idx = m.order.index(s_next)
        if dir_sign == 0:
            # single observation / ambiguous — sit the train at the station
            lat, lon = m.coord[s_next]
            pos_frac = f_next
            term = m.order[-1]
        else:
            prev_idx = idx - dir_sign            # station the train just departed
            if 0 <= prev_idx < len(m.order):
                s_prev = m.order[prev_idx]
                f_prev = m.frac[s_prev]
            else:
                s_prev, f_prev = s_next, f_next   # at terminus, nothing behind
            # estimate prev→next segment time from next→after delta
            seg_time = SEG_TIME_FALLBACK
            if len(seq) >= 2:
                d = seq[1][0] - t_next
                if d > 0:
                    seg_time = min(max(d, SEG_TIME_MIN), SEG_TIME_MAX)
            along = 1.0 - (t_next / seg_time) if seg_time else 1.0
            along = min(max(along, 0.0), 1.0)
            pos_frac = f_prev + along * (f_next - f_prev)
            pt = m.line.interpolate_normalized(pos_frac)
            lat, lon = pt.y, pt.x
            term = m.order[-1] if dir_sign > 0 else m.order[0]

        nlat, nlon = m.coord[s_next]
        # None when the train sits exactly on the next station (no movement vector)
        # — the map skips the direction chevron rather than drawing a spurious north arrow.
        bearing = _bearing(lat, lon, nlat, nlon) if (lat, lon) != (nlat, nlon) else None
        # the fraction axis runs in the canonical shape's travel direction, which
        # is GTFS direction canon_dir — not always 0 (Az/Am canonical shapes are dir 1)
        direction_id = m.canon_dir if dir_sign >= 0 else 1 - m.canon_dir

        return {
            'v': comboio,
            'lat': round(lat, 6),
            'lon': round(lon, 6),
            'b': None if bearing is None else round(bearing),
            's': 0,
            'r': m.route_src,
            'rc': m.color,
            'rn': m.short_name,
            'rt': m.route_type,
            'st': 'INCOMING_AT' if t_next < 30 else 'IN_TRANSIT_TO',
            't': int(now),
            'tid': '',
            'sid': s_next,
            'd': direction_id,
            'hs': dest_name or m.name.get(term, ''),
            'ps': m.place_slug,
            'rs': m.route_slug,
            'eta': t_next,
        }

    # -- publish (mirror fetch_transit_rt Redis contract) ------------------

    def _publish(self, r, ds_id, vehicles, now):
        ds_id_str = str(ds_id)
        cache.set(f'transit:rt:{ds_id}', orjson.dumps(vehicles), timeout=180)

        current = set()
        pipe = r.pipeline(transaction=False)
        for v in vehicles:
            member = f'{ds_id_str}:{v["v"]}'
            current.add(member)
            pipe.geoadd('transit:geo', (v['lon'], v['lat'], member))
            pipe.hset('transit:vdata', member, orjson.dumps(v))
        pipe.execute()

        prev_key = f'transit:members:{ds_id_str}'
        prev = {m.decode() if isinstance(m, bytes) else m for m in (r.smembers(prev_key) or set())}
        stale = prev - current
        if stale:
            pipe = r.pipeline(transaction=False)
            pipe.zrem('transit:geo', *stale)
            pipe.hdel('transit:vdata', *stale)
            pipe.execute()
        if current:
            r.delete(prev_key)
            r.sadd(prev_key, *current)
            r.expire(prev_key, MEMBERS_TTL)

        # route batch + tick
        routes_batch = {}
        for v in vehicles:
            g = f'transit_route:{ds_id_str}_{v["r"]}'
            b = routes_batch.setdefault(g, {'vehicles': [], 'stop_ids': set()})
            b['vehicles'].append(v)
            if v.get('sid'):
                b['stop_ids'].add(v['sid'])
        pipe = r.pipeline(transaction=False)
        pipe.publish('transit:tick', str(int(now)))
        for g, b in routes_batch.items():
            pipe.publish(g, orjson.dumps({'vehicles': b['vehicles'], 'stop_ids': list(b['stop_ids'])}))
        pipe.execute()

    # -- main loop ---------------------------------------------------------

    def handle(self, **opts):
        ds = TransitDataSource.objects.filter(slug=SLUG, is_active=True).first()
        if not ds:
            raise CommandError(f"No active TransitDataSource slug={SLUG}")
        creds = self._load_creds()
        models = self._build_models(ds.id)
        destinos = self._load_destinos(creds, models)
        models_built = time.monotonic()
        self.stdout.write(f"Loaded {len(models)} line models: "
                          + ", ".join(f"{k}({len(m.order)} st)" for k, m in models.items())
                          + f"; {len(destinos)} destino codes")

        r = None if opts['dry_run'] else redis_sync.Redis(
            host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
            port=getattr(settings, 'REDIS_PORT', 6379))
        interval = opts['interval'] or ds.rt_interval or 10

        while True:
            t0 = time.time()
            try:
                if time.monotonic() - models_built > MODELS_TTL_S:
                    models = self._build_models(ds.id)
                    destinos = self._load_destinos(creds, models)
                    models_built = time.monotonic()
                data = self._get(creds, ARRIVALS_EP)
                arrivals = data.get('resposta', []) if isinstance(data, dict) else []
                now = time.time()
                vehicles = self._reconstruct(arrivals, models, destinos, now)
                if opts['dry_run']:
                    self._print(vehicles, models)
                else:
                    self._publish(r, ds.id, vehicles, now)
                TransitDataSource.objects.filter(id=ds.id).update(last_error='')
                logger.info(f"ML: {len(arrivals)} records → {len(vehicles)} trains "
                            f"in {(time.time()-t0)*1000:.0f}ms")
                self.stdout.write(f"  {len(arrivals)} arrival records → {len(vehicles)} trains")
            except Exception as e:
                logger.error(f"ML poll failed: {e}")
                self.stderr.write(self.style.ERROR(f"poll failed: {e}"))
                TransitDataSource.objects.filter(id=ds.id).update(last_error=str(e)[:500])

            if opts['once']:
                break
            time.sleep(max(interval - (time.time() - t0), 1))

    def _print(self, vehicles, models):
        self.stdout.write(f"  reconstructed {len(vehicles)} trains:")
        for v in sorted(vehicles, key=lambda x: (x['r'], x['eta']))[:60]:
            m = models[v['r']]
            self.stdout.write(
                f"    {v['rn']:3s} train {v['v']:4s} @ ({v['lat']:.5f},{v['lon']:.5f}) "
                f"→ {v['sid']:3s}({m.name.get(v['sid'],''):16s}) in {v['eta']:4d}s "
                f"hdg→{v['hs']:14s} b={v['b']:3d} d={v['d']}")
