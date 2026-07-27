"""Discover GTFS-RT candidate feeds from the Mobility Database catalog.

The Mobility Database (https://mobilitydatabase.org, MobilityData) is a catalog of
feed *metadata*, not a data host: it indexes the operator URLs and how to reach
them. Its schema maps almost 1:1 onto our TransitDataSource, so it turns our hard
feed policy ("only feeds with static + RT vehicle GPS") into a single query:

    data_type == 'gtfs_rt'  AND  'vp' in entity_type   -> has VehiclePositions
    static_reference resolves to a gtfs feed           -> has the paired static

This command downloads the catalog CSV, applies that filter (plus region/provider
filters), resolves each RT feed's paired static via `static_reference`, drops feeds
we already ingest (URL match against existing TransitDataSource), and prints a
shortlist to review. It NEVER creates a TransitDataSource — a new feed is always a
deliberate per-feed decision (coverage rationale + our own validation), and the
catalog's "vp exists" is not proof of usable GPS (cf. MTA Subway lat/lon=0, Metro
Lisboa arrivals-not-GPS, CM 15h ghosts). Validate every pick with the RT health
sampler before wiring it in.

The catalog stores auth *metadata* (type + param name + info URL), never the actual
API key. Feeds with auth_type != 0 are flagged; you still register with the operator.

Usage:
    python3 manage.py discover_gtfs_candidates --country PT
    python3 manage.py discover_gtfs_candidates --country PT,ES --provider carris
    python3 manage.py discover_gtfs_candidates --bbox=-9.5,38.6,-9.0,38.9   # lisbon-ish (=form: negative lon)
    python3 manage.py discover_gtfs_candidates --country FI --json --out /tmp/fi.json
    python3 manage.py discover_gtfs_candidates --country PT --include-existing
    python3 manage.py discover_gtfs_candidates --refresh          # re-download catalog
"""

import csv
import json
import os
import sys

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from geo.models import TransitDataSource

CATALOG_URL = 'https://files.mobilitydatabase.org/feeds_v2.csv'
CACHE_DIR = os.path.join(settings.BASE_DIR, 'gtfs_cache')
CACHE_PATH = os.path.join(CACHE_DIR, 'mobility_db_feeds_v2.csv')

AUTH_LABEL = {
    '0': 'none',
    '1': 'key-in-url',   # append ?<param>=<KEY>
    '2': 'http-header',  # -> maps to TransitDataSource.rt_headers
    '3': 'ad-hoc',
}


def _norm_url(u):
    """Normalize a URL for cross-source equality: drop scheme, trailing slash, case."""
    if not u:
        return ''
    u = u.strip()
    if '://' in u:
        u = u.split('://', 1)[1]
    return u.rstrip('/').lower()


class Command(BaseCommand):
    help = "Discover GTFS-RT VehiclePositions candidate feeds from the Mobility Database catalog."

    def add_arguments(self, parser):
        parser.add_argument('--country', default='', help='Comma-separated ISO country codes (e.g. PT,ES). Empty = all.')
        parser.add_argument('--provider', default='', help='Case-insensitive substring match on provider name.')
        parser.add_argument('--municipality', default='', help='Case-insensitive substring match on municipality.')
        parser.add_argument('--bbox', default='', help='Spatial filter minlon,minlat,maxlon,maxlat (feed bbox must overlap).')
        parser.add_argument('--status', default='active',
                            help="Comma-separated catalog status to keep (default 'active'). Use 'all' to keep any.")
        parser.add_argument('--allow-orphan-rt', action='store_true',
                            help='Include vp feeds with no resolvable static in the catalog (default: drop them; our policy needs static+RT).')
        parser.add_argument('--include-existing', action='store_true',
                            help='Show feeds we already ingest (matched by URL), marked [known]. Default: hide them.')
        parser.add_argument('--refresh', action='store_true', help='Re-download the catalog CSV even if cached.')
        parser.add_argument('--csv', default='', help='Use a local catalog CSV instead of downloading.')
        parser.add_argument('--json', action='store_true', help='Emit JSON instead of a table.')
        parser.add_argument('--out', default='', help='Write output to this file instead of stdout.')
        parser.add_argument('--limit', type=int, default=0, help='Cap the number of candidates shown (0 = no cap).')

    # ---- catalog loading -------------------------------------------------

    def _load_catalog(self, opts):
        path = opts['csv'] or CACHE_PATH
        if opts['csv']:
            if not os.path.exists(path):
                raise CommandError(f'--csv file not found: {path}')
        elif opts['refresh'] or not os.path.exists(path):
            self.stderr.write(f'Downloading catalog: {CATALOG_URL}')
            os.makedirs(CACHE_DIR, exist_ok=True)
            try:
                resp = requests.get(CATALOG_URL, timeout=120)
                resp.raise_for_status()
            except requests.RequestException as exc:
                raise CommandError(f'catalog download failed: {exc!r}')
            with open(path, 'wb') as fh:
                fh.write(resp.content)
        # rows carry long free-text fields; lift the CSV field cap
        csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
        with open(path, newline='', encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
        return rows

    # ---- filtering -------------------------------------------------------

    def handle(self, *args, **opts):
        rows = self._load_catalog(opts)
        by_id = {r['id']: r for r in rows}

        def resolve_static(rt_row):
            """Follow static_reference (one redirect hop) to the paired static feed."""
            ref = (rt_row.get('static_reference') or '').strip()
            # static_reference is usually a single id; tolerate a pipe list
            for candidate in ref.split('|'):
                st = by_id.get(candidate.strip())
                if not st:
                    continue
                if st.get('status') == 'deprecated' and (st.get('redirect.id') or '').strip():
                    st = by_id.get(st['redirect.id'].strip(), st)
                return st
            return None

        countries = {c.strip().upper() for c in opts['country'].split(',') if c.strip()}
        statuses = None if opts['status'].strip().lower() == 'all' else \
            {s.strip().lower() for s in opts['status'].split(',') if s.strip()}
        provider_q = opts['provider'].strip().lower()
        muni_q = opts['municipality'].strip().lower()
        bbox = self._parse_bbox(opts['bbox'])

        # URLs we already ingest (static + RT + alerts), for the "known" flag
        existing = set()
        for ds in TransitDataSource.objects.all():
            for blob in (ds.url, ds.rt_vehicles_url, ds.rt_alerts_url):
                for line in (blob or '').splitlines():
                    n = _norm_url(line)
                    if n:
                        existing.add(n)

        candidates = []
        for r in rows:
            if r.get('data_type') != 'gtfs_rt':
                continue
            if 'vp' not in (r.get('entity_type') or '').split('|'):
                continue
            if statuses is not None and (r.get('status') or '').lower() not in statuses:
                continue
            if countries and (r.get('location.country_code') or '').upper() not in countries:
                continue
            if provider_q and provider_q not in (r.get('provider') or '').lower():
                continue
            if muni_q and muni_q not in (r.get('location.municipality') or '').lower():
                continue
            if bbox and not self._bbox_overlaps(r, bbox):
                continue

            static = resolve_static(r)
            if static is None and not opts['allow_orphan_rt']:
                continue

            rt_url = (r.get('urls.direct_download') or '').strip()
            static_url = (static or {}).get('urls.direct_download', '').strip()
            known = _norm_url(rt_url) in existing or (static_url and _norm_url(static_url) in existing)
            if known and not opts['include_existing']:
                continue

            auth = (r.get('urls.authentication_type') or '0').strip() or '0'
            candidates.append({
                'provider': r.get('provider', ''),
                'name': r.get('name', ''),
                'country': r.get('location.country_code', ''),
                'subdivision': r.get('location.subdivision_name', ''),
                'municipality': r.get('location.municipality', ''),
                'status': r.get('status', ''),
                'rt_id': r.get('id', ''),
                'rt_vehicles_url': rt_url,
                'auth_type': auth,
                'auth_label': AUTH_LABEL.get(auth, auth),
                'api_key_parameter_name': r.get('urls.api_key_parameter_name', ''),
                'authentication_info_url': r.get('urls.authentication_info', ''),
                'needs_key': auth not in ('0', ''),
                'static_id': (static or {}).get('id', ''),
                'static_url': static_url,
                'license': r.get('urls.license', '') or (static or {}).get('urls.license', ''),
                'contact_email': r.get('feed_contact_email', ''),
                'known': known,
            })

        # stable, deterministic ordering (no clock/random available in commands anyway)
        candidates.sort(key=lambda c: (c['known'], c['country'], c['provider'].lower(), c['municipality'].lower()))
        if opts['limit'] > 0:
            candidates = candidates[:opts['limit']]

        self._emit(candidates, opts)

    # ---- geometry helpers ------------------------------------------------

    @staticmethod
    def _parse_bbox(s):
        if not s.strip():
            return None
        try:
            minlon, minlat, maxlon, maxlat = (float(x) for x in s.split(','))
        except ValueError:
            raise CommandError('--bbox must be minlon,minlat,maxlon,maxlat (4 floats)')
        return (minlon, minlat, maxlon, maxlat)

    @staticmethod
    def _bbox_overlaps(r, bbox):
        try:
            fmin_lat = float(r['location.bounding_box.minimum_latitude'])
            fmax_lat = float(r['location.bounding_box.maximum_latitude'])
            fmin_lon = float(r['location.bounding_box.minimum_longitude'])
            fmax_lon = float(r['location.bounding_box.maximum_longitude'])
        except (ValueError, KeyError):
            return False  # no bbox in catalog -> can't spatially confirm, exclude
        minlon, minlat, maxlon, maxlat = bbox
        return not (fmax_lon < minlon or fmin_lon > maxlon or fmax_lat < minlat or fmin_lat > maxlat)

    # ---- output ----------------------------------------------------------

    def _emit(self, candidates, opts):
        if opts['json']:
            text = json.dumps(candidates, ensure_ascii=False, indent=2)
        else:
            text = self._render_table(candidates)
        if opts['out']:
            with open(opts['out'], 'w', encoding='utf-8') as fh:
                fh.write(text + ('\n' if not opts['json'] else ''))
            self.stderr.write(self.style.SUCCESS(f'wrote {len(candidates)} candidates -> {opts["out"]}'))
        else:
            self.stdout.write(text)

    def _render_table(self, candidates):
        if not candidates:
            return '(no candidates match the filters)'
        new = sum(1 for c in candidates if not c['known'])
        keyed = sum(1 for c in candidates if c['needs_key'])
        lines = []
        for i, c in enumerate(candidates, 1):
            loc = ' / '.join(x for x in (c['municipality'], c['subdivision'], c['country']) if x)
            tags = []
            if c['known']:
                tags.append('known')
            if c['needs_key']:
                tags.append(f'key:{c["auth_label"]}')
            if not c['static_id']:
                tags.append('no-static')
            tag_s = ('  [' + ', '.join(tags) + ']') if tags else ''
            lines.append(f'{i:>3}. {c["provider"]} — {loc}  ({c["status"]}){tag_s}')
            lines.append(f'       rt     : {c["rt_vehicles_url"]}')
            lines.append(f'       static : {c["static_url"] or "(none in catalog)"}')
            if c['needs_key'] and c['authentication_info_url']:
                param = f' param={c["api_key_parameter_name"]}' if c['api_key_parameter_name'] else ''
                lines.append(f'       auth   : {c["authentication_info_url"]}{param}')
            if c['license']:
                lines.append(f'       license: {c["license"]}')
        header = (f'{len(candidates)} candidate(s): {new} new, '
                  f'{len(candidates) - new} already ingested, {keyed} need an API key\n'
                  f'(vet each with sample_feed_health before creating a TransitDataSource)\n')
        return header + '\n'.join(lines)
