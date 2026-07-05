"""
Import GTFS static feed (ZIP) into geo models.

Usage:
    python3 manage.py import_gtfs --url https://api.carrismetropolitana.pt/gtfs
    python3 manage.py import_gtfs --file /tmp/carris_metropolitana_gtfs.zip
    python3 manage.py import_gtfs --url https://... --skip-stop-times --skip-shapes
    python3 manage.py import_gtfs --url https://... --reset
"""

import csv
import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from collections import defaultdict
from datetime import datetime

import requests

logger = logging.getLogger(__name__)
from django.contrib.gis.geos import LineString, Point
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction

from geo.models import Agency, CalendarDate, Place, Route, RouteStop, Shape, Stop, StopTime, TransitDataSource, Trip


# Some operators (e.g. Metro de Lisboa) return 403 to requests with no
# User-Agent — always send a browser-like UA on GTFS downloads.
# Single source of truth: update_gtfs_feeds imports this too.
HTTP_HEADERS = {'User-Agent': 'Mozilla/5.0 (parahub GTFS updater)'}


# Feeds (TransitDataSource.slug) whose route_id encodes line grouping as
# "<line>_<variant>" but ship no line_id/path_type columns (CM ext) — line_id
# and path_type are synthesized from route_id so percursos grouping (search
# collapse, variants selector) works. Strictly opt-in: elsewhere short_name
# collisions mean *distinct* routes (PID "MHD 4" = Benešov and Kolín city
# buses, NYC "S" = three different shuttles). Before adding a feed verify
# every short_name maps to exactly one route_id prefix — PK/gtfs-feed-quirks.md.
SYNTHESIZE_LINE_ID_FEEDS = {"carris-lisboa", "carris-metropolitana"}
_VARIANT_ROUTE_ID_RE = re.compile(r"^(.+)_(\d+)$")

# Rail feeds that ship no line_id and no usable route_id grouping, but whose
# route_short_name IS the public line name shared across O-D path-variants
# (CP: "Linha de Cascais" on 9 direction/short-turn route_ids like
# 25-94_69005-94_69260). line_id is synthesized from short_name so percursos
# collapse. path_type can't come from the feed (all 0) → it's ranked
# post-import by geometry length so the FULL line (longest) is canonical, not a
# lexically-first short-turn (Cais do Sodré→Algés over Cascais); see
# _rank_synth_path_type. Gated to route_type 109 (Suburban Railway): CP's
# long-distance services share a short_name that is a service CLASS
# (AP/IC/IR/R), not a line — grouping those would fabricate one nationwide "R"
# line. PK/gtfs-feed-quirks.md "Line grouping ext".
SYNTHESIZE_LINE_ID_FROM_SHORTNAME = {"cp-rail"}
_SUBURBAN_RAIL_ROUTE_TYPE = 109


# Primary key fields for GTFS deduplication during multi-ZIP merge
_GTFS_PK = {
    'agency.txt': 'agency_id',
    'routes.txt': 'route_id',
    'trips.txt': 'trip_id',
    'stops.txt': 'stop_id',
    'calendar.txt': 'service_id',
}


def _normalize_gtfs_zip(zip_path, stdout=None):
    """Normalize a GTFS ZIP: handle nested ZIPs (ZIP-in-ZIP) transparently.

    Returns (normalized_path, is_temp) where is_temp=True means caller must delete.
    - Standard GTFS (agency.txt at root): returns as-is
    - Nested ZIPs (e.g. SEPTA: google_bus.zip + google_rail.zip inside): extracts,
      merges all inner GTFS feeds with row-level deduplication, returns merged ZIP
    """
    with zipfile.ZipFile(zip_path, 'r') as zf:
        names = zf.namelist()
        # Standard GTFS — agency.txt in root
        if 'agency.txt' in names:
            return zip_path, False

        # Check for nested ZIPs
        inner_zips = [n for n in names if n.endswith('.zip') and '/' not in n]
        if not inner_zips:
            # Maybe files are in a subdirectory
            for n in names:
                if n.endswith('agency.txt'):
                    return zip_path, False
            raise ValueError(f"Not a valid GTFS ZIP: no agency.txt and no nested .zip files found")

        if stdout:
            stdout.write(f"  Nested GTFS detected: {', '.join(inner_zips)} — merging with dedup")

        merged = {}   # filename -> list of row dicts
        headers = {}  # filename -> fieldnames
        seen = {}     # filename -> set of primary keys

        for inner_name in inner_zips:
            with zf.open(inner_name) as inner_file:
                inner_data = inner_file.read()
                with zipfile.ZipFile(io.BytesIO(inner_data)) as iz:
                    for fname in iz.namelist():
                        basename = os.path.basename(fname)
                        if not basename.endswith('.txt') or basename.startswith('.'):
                            continue
                        with iz.open(fname) as f:
                            text = io.TextIOWrapper(f, encoding='utf-8-sig')
                            reader = csv.DictReader(text)
                            rows = list(reader)
                            if basename not in merged:
                                merged[basename] = []
                                headers[basename] = list(reader.fieldnames or [])
                                seen[basename] = set()
                            else:
                                # Union headers from all inner zips (e.g. SEPTA
                                # rail adds 'cemv_support' to agency.txt)
                                existing_h = set(headers[basename])
                                for h in (reader.fieldnames or []):
                                    if h not in existing_h:
                                        headers[basename].append(h)
                                        existing_h.add(h)

                            pk_field = _GTFS_PK.get(basename)
                            for row in rows:
                                if pk_field:
                                    key = row.get(pk_field, '')
                                elif basename == 'calendar_dates.txt':
                                    key = f"{row.get('service_id', '')}_{row.get('date', '')}"
                                elif basename == 'shapes.txt':
                                    key = f"{row.get('shape_id', '')}_{row.get('shape_pt_sequence', '')}"
                                else:
                                    key = None  # no dedup for unknown files

                                if key is None or key not in seen[basename]:
                                    merged[basename].append(row)
                                    if key is not None:
                                        seen[basename].add(key)

        fd, out_path = tempfile.mkstemp(suffix='.zip', prefix='gtfs_merged_')
        os.close(fd)
        with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for fname, rows in merged.items():
                buf = io.StringIO()
                writer = csv.DictWriter(buf, fieldnames=headers[fname])
                writer.writeheader()
                writer.writerows(rows)
                zout.writestr(fname, buf.getvalue())

        if stdout:
            stdout.write(f"  Merged: {sum(len(r) for r in merged.values())} rows across {len(merged)} files")
        return out_path, True


# Safe gtfstidy flags (never touch IDs):
# -S remove redundant shapes, -C remove duplicate services,
# -D drop erroneous entries, -n check null coords, -s minimize shapes (Douglas-Peucker)
# --keep-ids preserve all IDs (critical for RT matching)
# -F keep-additional-fields: gtfstidy otherwise drops every column it doesn't
#    itself use — including tts_stop_name (and parish/locality/municipality).
#    We need tts_stop_name (Stop.tts_name, driver-mode TTS). Additive only:
#    keeps extra columns, drops no rows, changes no IDs. MOTIS/import ignore
#    columns they don't read.
# NOT used: -O (orphan removal — too aggressive, drops routes with empty stop_times),
#           -R (route dedup — merges route_ids), -I/-P/-T (ID changes)
_GTFSTIDY_FLAGS = ['-SCDns', '--keep-ids', '-F']


def _gtfstidy(zip_path, stdout=None):
    """Run gtfstidy on a GTFS ZIP for safe cleanup. Returns (path, is_temp, stats).

    Graceful degradation: if gtfstidy not installed or fails, returns original.
    Safety net: if routes drop >5% or stops drop >10%, reverts to original.
    """
    tidy_bin = shutil.which('gtfstidy')
    if not tidy_bin:
        return zip_path, False, None

    # Count before
    try:
        before = _count_gtfs_entities(zip_path)
    except Exception:
        return zip_path, False, None

    fd, out_path = tempfile.mkstemp(suffix='.zip', prefix='gtfs_tidy_')
    os.close(fd)

    try:
        cmd = [tidy_bin] + _GTFSTIDY_FLAGS + ['-o', out_path, zip_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.warning(f'gtfstidy failed (rc={result.returncode}): {result.stderr[:200]}')
            os.unlink(out_path)
            return zip_path, False, {'error': result.stderr[:200]}

        # Count after
        after = _count_gtfs_entities(out_path)

        # Safety net
        stats = {}
        for key in before:
            b, a = before[key], after[key]
            delta = a - b
            pct = (delta / b * 100) if b else 0
            stats[key] = {'before': b, 'after': a, 'delta': delta, 'pct': round(pct, 1)}

        route_drop = -stats.get('routes', {}).get('pct', 0)
        stop_drop = -stats.get('stops', {}).get('pct', 0)

        if route_drop > 5 or stop_drop > 10:
            logger.warning(
                f'gtfstidy safety net triggered: routes -{route_drop:.1f}%, '
                f'stops -{stop_drop:.1f}% — reverting to original'
            )
            os.unlink(out_path)
            stats['reverted'] = True
            return zip_path, False, stats

        # Parse stderr for gtfstidy report
        tidy_report = result.stderr.strip() if result.stderr else ''
        stats['report'] = tidy_report[:500]

        orig_size = os.path.getsize(zip_path)
        tidy_size = os.path.getsize(out_path)
        stats['size'] = {'before': orig_size, 'after': tidy_size,
                         'saved_pct': round((1 - tidy_size / orig_size) * 100, 1) if orig_size else 0}

        if stdout:
            stdout.write(
                f"  gtfstidy: {tidy_size/1024/1024:.1f}MB "
                f"(was {orig_size/1024/1024:.1f}MB, -{stats['size']['saved_pct']}%)"
            )
            for key, s in stats.items():
                if isinstance(s, dict) and 'delta' in s and s['delta'] != 0:
                    stdout.write(f"    {key}: {s['before']} → {s['after']} ({s['delta']:+d})")

        return out_path, True, stats

    except subprocess.TimeoutExpired:
        logger.warning('gtfstidy timed out (300s)')
        if os.path.exists(out_path):
            os.unlink(out_path)
        return zip_path, False, {'error': 'timeout'}
    except Exception as e:
        logger.warning(f'gtfstidy error: {e}')
        if os.path.exists(out_path):
            os.unlink(out_path)
        return zip_path, False, {'error': str(e)[:200]}


def _count_gtfs_entities(zip_path):
    """Quick count of key GTFS entities in a ZIP."""
    counts = {}
    with zipfile.ZipFile(zip_path) as zf:
        for fname, key in [('routes.txt', 'routes'), ('stops.txt', 'stops'), ('trips.txt', 'trips')]:
            if fname in zf.namelist():
                with zf.open(fname) as f:
                    counts[key] = sum(1 for _ in csv.reader(io.TextIOWrapper(f, encoding='utf-8-sig'))) - 1  # minus header
            else:
                counts[key] = 0
    return counts


def backfill_empty_headsigns(agency_ids=None, batch_size=5000):
    """Fill empty Trip.headsign with the trip's terminus (its last stop's name).

    GTFS permits a blank trip_headsign; some operators (Carris Lisboa: 165 968/
    165 968) leave it empty feed-wide, which erases the (route, direction) label
    everywhere it's derived from headsign — the stop-page direction subtitle, the
    sibling-pole list, the live "at stop"/"approaching" rows (via RouteCache's
    headsign_info) and the schedule. The GTFS-standard fallback is the trip's final
    stop, so two same-name opposite-direction poles read e.g. "→ Cidade
    Universitária" vs "→ Damaia Cima". The route page stays header-free (that's a
    deliberate 2026-06-12 owner decision, enforced in the frontend — it renders no
    direction header element, so this backfill never revives one there).

    Derives the terminus from StopTimes already in the DB, so it must run AFTER
    stop_times import (a no-op under fast/skip-stop_times mode — nothing to read).
    Only touches still-empty headsigns. Returns the number of trips updated.
    """
    st = StopTime.objects.filter(trip__headsign="")
    if agency_ids is not None:
        st = st.filter(trip__route__agency_id__in=agency_ids)
    # Terminus = stop at the highest stop_sequence of each trip (Postgres DISTINCT ON).
    # Materialized (one row per empty-headsign trip) so the bulk_update writes below
    # don't run against an open server-side cursor on the same connection.
    term_rows = list(
        st.order_by("trip_id", "-stop_sequence")
        .distinct("trip_id")
        .values_list("trip_id", "stop__name")
    )
    buf, updated = [], 0
    for trip_id, name in term_rows:
        if not name:
            continue
        buf.append(Trip(id=trip_id, headsign=name[:255]))
        if len(buf) >= batch_size:
            Trip.objects.bulk_update(buf, ["headsign"])
            updated += len(buf)
            buf = []
    if buf:
        Trip.objects.bulk_update(buf, ["headsign"])
        updated += len(buf)
    return updated


class Command(BaseCommand):
    help = "Import GTFS static feed from ZIP (URL or local file)"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--url", help="URL to download GTFS ZIP from")
        group.add_argument("--file", help="Path to local GTFS ZIP file")
        parser.add_argument("--reset", action="store_true",
                            help="Delete existing data for this feed before import")
        parser.add_argument("--skip-stop-times", action="store_true",
                            help="Skip importing stop_times.txt (15M+ rows)")
        parser.add_argument("--skip-shapes", action="store_true",
                            help="Skip importing shapes.txt")
        parser.add_argument("--feed-url",
                            help="Feed URL identifier (required with --file to distinguish agencies)")

    def handle(self, *args, **options):
        t0 = time.time()

        # Get ZIP file path
        if options["url"]:
            zip_path = self._download(options["url"])
            feed_url = options["url"]
        else:
            zip_path = options["file"]
            feed_url = options.get("feed_url") or ""
            if not feed_url:
                self.stderr.write(
                    self.style.WARNING(
                        "WARNING: No --feed-url specified. Agency will be matched by "
                        "source_id + no data_source. Use --feed-url to avoid "
                        "collisions with other feeds that have the same agency_id."
                    )
                )

        if not os.path.exists(zip_path):
            self.stderr.write(f"File not found: {zip_path}")
            return

        self.stdout.write(f"Opening {zip_path} ({os.path.getsize(zip_path) / 1024 / 1024:.1f} MB)")

        downloaded = options["url"] is not None  # Track if we downloaded (to clean up)
        normalized_path, normalized_is_temp = _normalize_gtfs_zip(zip_path, stdout=self.stdout)
        tidied_path, tidied_is_temp, tidy_stats = _gtfstidy(normalized_path, stdout=self.stdout)
        final_path = tidied_path
        try:
            with zipfile.ZipFile(final_path, "r") as zf:
                available = set(zf.namelist())
                self.stdout.write(f"Files in ZIP: {', '.join(sorted(available))}")

                with transaction.atomic():
                    # 1. Agency
                    agency = self._import_agency(zf, feed_url)

                    # All agencies from this data source (for multi-agency GTFS)
                    all_agencies = list(getattr(self, '_agency_map', {}).values()) or [agency]

                    if options["reset"]:
                        self.stdout.write("Resetting existing data for this agency...")
                        # Delete in FK-safe order
                        st_count = StopTime.objects.filter(trip__route__agency__in=all_agencies).count()
                        if st_count:
                            StopTime.objects.filter(trip__route__agency__in=all_agencies).delete()
                            self.stdout.write(f"  Deleted {st_count} stop_times")
                        RouteStop.objects.filter(route__agency__in=all_agencies).delete()
                        Trip.objects.filter(route__agency__in=all_agencies).delete()
                        Route.objects.filter(agency__in=all_agencies).delete()
                        Stop.objects.filter(agency=agency).delete()
                        CalendarDate.objects.filter(agency=agency).delete()
                        self.stdout.write("  Reset complete")

                    # 2. CalendarDate (delete once, then calendar.txt + calendar_dates.txt)
                    CalendarDate.objects.filter(agency=agency).delete()
                    if "calendar.txt" in available:
                        self._import_calendar(zf, agency)
                    if "calendar_dates.txt" in available:
                        self._import_calendar_dates(zf, agency)

                    # 3. Stops
                    stop_map, stop_changes = self._import_stops(zf, agency)

                    # 4. Routes
                    route_map, route_changes = self._import_routes(zf, agency)

                    # 5. Shapes
                    shape_map = {}
                    if not options["skip_shapes"] and "shapes.txt" in available:
                        shape_map = self._import_shapes(zf, agency)

                    # 6. Trips
                    trip_map = self._import_trips(zf, agency, route_map, shape_map)

                    # 7. RouteStops (built from stop_times)
                    if not options["skip_stop_times"] and "stop_times.txt" in available:
                        # 8. StopTimes + RouteStops
                        self._import_stop_times(zf, trip_map, stop_map, route_map)
                        # 8b. Fill blank trip_headsign with the trip terminus so
                        #     direction labels work even for feeds that ship empty
                        #     headsigns (Carris). Needs the StopTimes just imported.
                        n_hs = backfill_empty_headsigns(all_agencies)
                        if n_hs:
                            self.stdout.write(f"  Backfilled {n_hs} blank trip headsigns from terminus")
                    elif "stop_times.txt" in available:
                        # Build RouteStops from stop_times without importing all rows
                        self._build_route_stops_fast(zf, trip_map, stop_map, route_map)

                    # 9. Route geometry from shapes
                    for ag in all_agencies:
                        self._assign_route_geometry(ag, shape_map, route_map)

                    # 9b. Feeds whose line_id is synthesized from short_name carry
                    #     no native path_type (all variants 0) → rank by geometry
                    #     length so the full line (longest) is the canonical
                    #     path_type=0, not a lexically-first short-turn.
                    if agency.data_source and agency.data_source.slug in SYNTHESIZE_LINE_ID_FROM_SHORTNAME:
                        self._rank_synth_path_type(all_agencies)

                    # 10. Conditional place assignment
                    has_place_changes = (
                        stop_changes["created"] or stop_changes["removed"]
                        or stop_changes["location_changed"]
                    )
                    if has_place_changes or options["reset"]:
                        # Reset route.place_id for routes with stops that lost their place
                        Route.objects.filter(
                            agency__in=all_agencies,
                            route_stops__stop__place_id__isnull=True,
                        ).distinct().update(place_id=None)

                        # Stops use primary agency; routes need all agencies
                        self._assign_place_fks(agency)
                        for ag in all_agencies:
                            self._populate_route_places_m2m(ag)
                            self._assign_orphan_places(ag)
                    else:
                        self.stdout.write("\n  Skipping place assignment (no stop location/create/remove changes)")

                    # 11. Conditional slug generation
                    has_slug_changes = (
                        stop_changes["created"] or stop_changes["name_changed"]
                        or route_changes["created"] or route_changes["name_changed"]
                    )
                    if has_slug_changes or options["reset"]:
                        # Stop slugs: primary agency only (stops share one agency)
                        # Route slugs: all agencies
                        self._generate_slugs(agency)
                        for ag in all_agencies:
                            if ag.id != agency.id:
                                self._generate_route_slugs(ag)
                    else:
                        self.stdout.write("  Skipping slug generation (no name changes)")

                    # 13. Update last_imported_at on data source
                    from django.utils import timezone as tz
                    if agency.data_source:
                        TransitDataSource.objects.filter(pk=agency.data_source_id).update(last_imported_at=tz.now())
                        self.stdout.write(f"\n  Updated data source last_imported_at")
        finally:
            if tidied_is_temp and os.path.exists(tidied_path):
                os.unlink(tidied_path)
            if normalized_is_temp and os.path.exists(normalized_path):
                os.unlink(normalized_path)
            if downloaded:
                os.unlink(zip_path)

        # Update planner statistics for all affected tables
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "ANALYZE geo_place, geo_stop, geo_route, geo_routestop,"
                " geo_trip, geo_stoptime, geo_calendardate"
            )
        self.stdout.write("  ANALYZE complete on 7 transit tables")

        elapsed = time.time() - t0
        self.stdout.write(self.style.SUCCESS(
            f"\nImport complete in {elapsed:.0f}s"
        ))

    def _download(self, url):
        """Download GTFS ZIP to a unique temp file (safe for parallel runs)."""
        self.stdout.write(f"Downloading {url}...")
        resp = requests.get(url, headers=HTTP_HEADERS, stream=True, timeout=120)
        resp.raise_for_status()
        size = int(resp.headers.get("content-length", 0))
        self.stdout.write(f"  Content-Length: {size / 1024 / 1024:.1f} MB")

        fd, path = tempfile.mkstemp(suffix=".zip", prefix="gtfs_")
        downloaded = 0
        with os.fdopen(fd, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if size:
                    pct = downloaded * 100 // size
                    self.stdout.write(f"  {pct}% ({downloaded / 1024 / 1024:.1f} MB)", ending="\r")
        self.stdout.write(f"\n  Saved to {path}")
        return path

    def _read_csv(self, zf, filename):
        """Read a CSV file from the ZIP, yielding dicts."""
        with zf.open(filename) as f:
            # Handle BOM
            text = io.TextIOWrapper(f, encoding="utf-8-sig")
            reader = csv.DictReader(text)
            for row in reader:
                yield row

    def _import_agency(self, zf, feed_url):
        """Import agency.txt — handles multi-agency GTFS feeds.

        Returns (primary_agency, agency_map) where agency_map maps
        GTFS agency_id -> Django Agency. Primary agency is the first row,
        used for stops/calendar (which lack agency_id in GTFS spec).
        """
        self.stdout.write("\n[1/9] Importing agencies...")
        rows = list(self._read_csv(zf, "agency.txt"))
        if not rows:
            raise ValueError("agency.txt is empty")

        # Get or create TransitDataSource for this feed URL
        data_source = None
        if feed_url:
            agency_name = rows[0].get("agency_name", "").strip()
            data_source, ds_created = TransitDataSource.objects.get_or_create(
                url=feed_url,
                defaults={
                    "name": agency_name,
                    "format": "gtfs",
                },
            )
            if ds_created:
                self.stdout.write(f"  Created data source: {feed_url}")
                # Policy: only import feeds that have RT vehicle data configured
                has_rt = bool(data_source.rt_vehicles_url and data_source.rt_vehicles_url.strip())
                if not has_rt:
                    self.stderr.write(self.style.ERROR(
                        "BLOCKED: New feed has no GTFS-RT vehicle URL configured. "
                        "Policy: only import feeds where both static + RT data are available. "
                        "First create the TransitDataSource in Django admin with rt_vehicles_url set, "
                        "then run import_gtfs."
                    ))
                    data_source.delete()
                    raise SystemExit(1)

        # Create/update ALL agencies from agency.txt
        agency_map = {}  # gtfs_agency_id -> Django Agency
        primary_agency = None
        for row in rows:
            source_id = row.get("agency_id", "").strip()
            name = row.get("agency_name", "").strip()

            agency, created = Agency.objects.update_or_create(
                source_id=source_id,
                data_source=data_source,
                defaults={
                    "name": name,
                    "url": row.get("agency_url", "").strip(),
                    "timezone": row.get("agency_timezone", "UTC").strip(),
                    "lang": row.get("agency_lang", "").strip(),
                }
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"  {action} agency: {name} (id={agency.id[:8]})")
            agency_map[source_id] = agency
            if primary_agency is None:
                primary_agency = agency

        # Single-agency feed: map empty string to the only agency
        if len(rows) == 1:
            agency_map[""] = primary_agency

        self._agency_map = agency_map
        return primary_agency

    def _import_calendar(self, zf, agency):
        """Import calendar.txt — expand weekday patterns into individual CalendarDate rows (type=1)."""
        from datetime import date as date_type, timedelta
        self.stdout.write("\n[2a/9] Importing calendar.txt (expanding to dates)...")

        DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        batch = []
        count = 0
        for row in self._read_csv(zf, "calendar.txt"):
            service_id = row.get("service_id", "").strip()
            start_str = row.get("start_date", "").strip()
            end_str = row.get("end_date", "").strip()
            if not service_id or not start_str or not end_str:
                continue
            try:
                start_dt = datetime.strptime(start_str, "%Y%m%d").date()
                end_dt = datetime.strptime(end_str, "%Y%m%d").date()
            except ValueError:
                continue

            # weekday() returns 0=Mon, 6=Sun; GTFS columns are Mon(0)..Sun(6)
            weekday_flags = [int(row.get(d, "0").strip() or "0") for d in DAYS]

            current = start_dt
            while current <= end_dt:
                if weekday_flags[current.weekday()]:
                    batch.append(CalendarDate(
                        agency=agency,
                        service_id=service_id,
                        date=current,
                        exception_type=1,
                    ))
                    count += 1
                    if len(batch) >= 5000:
                        CalendarDate.objects.bulk_create(batch, ignore_conflicts=True)
                        batch.clear()
                current += timedelta(days=1)

        if batch:
            CalendarDate.objects.bulk_create(batch, ignore_conflicts=True)
        self.stdout.write(f"  Expanded {count} service dates from calendar.txt")

    def _import_calendar_dates(self, zf, agency):
        """Import calendar_dates.txt — overrides/adds to calendar.txt entries."""
        self.stdout.write("\n[2b/9] Importing calendar_dates.txt...")

        batch = []
        count = 0
        for row in self._read_csv(zf, "calendar_dates.txt"):
            service_id = row.get("service_id", "").strip()
            date_str = row.get("date", "").strip()
            exc_type = int(row.get("exception_type", "1").strip())

            try:
                date = datetime.strptime(date_str, "%Y%m%d").date()
            except ValueError:
                continue

            batch.append(CalendarDate(
                agency=agency,
                service_id=service_id,
                date=date,
                exception_type=exc_type,
            ))
            count += 1

            if len(batch) >= 5000:
                # update_conflicts: lets calendar_dates.txt override calendar.txt entries
                CalendarDate.objects.bulk_create(
                    batch,
                    update_conflicts=True,
                    unique_fields=["agency", "service_id", "date"],
                    update_fields=["exception_type"],
                )
                batch.clear()

        if batch:
            CalendarDate.objects.bulk_create(
                batch,
                update_conflicts=True,
                unique_fields=["agency", "service_id", "date"],
                update_fields=["exception_type"],
            )

        self.stdout.write(f"  Imported {count} calendar date exceptions")

    def _import_stops(self, zf, agency):
        """Import stops.txt with upsert + change detection. Returns ({source_id: Stop.pk}, changes_dict)."""
        self.stdout.write("\n[3/9] Importing stops...")

        # Read feed data
        stops_data = []
        feed_source_ids = set()
        for row in self._read_csv(zf, "stops.txt"):
            gtfs_id = row.get("stop_id", "").strip()
            lat = row.get("stop_lat", "").strip()
            lon = row.get("stop_lon", "").strip()
            if not lat or not lon:
                continue

            loc_type = int(row.get("location_type", "0").strip() or "0")
            parent_id = row.get("parent_station", "").strip()

            stops_data.append({
                "gtfs_id": gtfs_id,
                "name": row.get("stop_name", "").strip(),
                "tts_name": row.get("tts_stop_name", "").strip(),
                "lat": float(lat),
                "lon": float(lon),
                "location_type": loc_type,
                "parent_gtfs_id": parent_id,
            })
            feed_source_ids.add(gtfs_id)

        # Load existing stops for this agency
        existing = {s.source_id: s for s in Stop.objects.filter(agency=agency)}

        to_create = []
        to_update = []
        location_changed = 0
        name_changed = 0
        skipped = 0

        for sd in stops_data:
            loc = Point(sd["lon"], sd["lat"], srid=4326)
            if sd["gtfs_id"] in existing:
                stop = existing[sd["gtfs_id"]]
                changed = False

                # Detect location change (compare coords with tolerance)
                old_loc = stop.location
                if abs(old_loc.x - sd["lon"]) > 1e-6 or abs(old_loc.y - sd["lat"]) > 1e-6:
                    stop.location = loc
                    stop.place_id = None  # Force place reassignment
                    stop.slug = ""  # Clear slug — may not be unique in new place
                    location_changed += 1
                    changed = True

                # Detect name change
                if stop.name != sd["name"]:
                    stop.name = sd["name"]
                    stop.slug = ""  # Force slug regeneration
                    name_changed += 1
                    changed = True

                if stop.location_type != sd["location_type"]:
                    stop.location_type = sd["location_type"]
                    changed = True

                # tts_name change (no slug/place impact — display/TTS only)
                if stop.tts_name != sd["tts_name"]:
                    stop.tts_name = sd["tts_name"]
                    changed = True

                if changed:
                    to_update.append(stop)
                else:
                    skipped += 1
            else:
                to_create.append(Stop(
                    agency=agency,
                    source_id=sd["gtfs_id"],
                    name=sd["name"],
                    tts_name=sd["tts_name"],
                    location=loc,
                    location_type=sd["location_type"],
                ))

        if to_create:
            Stop.objects.bulk_create(to_create, batch_size=5000)
        if to_update:
            Stop.objects.bulk_update(
                to_update,
                ["name", "tts_name", "location", "location_type", "slug", "place_id"],
                batch_size=5000,
            )

        # Delete stops removed from feed (cascade deletes StopTimes, RouteStops)
        removed = set(existing.keys()) - feed_source_ids
        if removed:
            Stop.objects.filter(agency=agency, source_id__in=removed).delete()
            self.stdout.write(f"  Removed {len(removed)} stale stops")

        # Build map
        stop_map = {}
        for s in Stop.objects.filter(agency=agency).only("id", "source_id"):
            stop_map[s.source_id] = s.pk

        # Resolve parent_station
        parent_updates = []
        for sd in stops_data:
            if sd["parent_gtfs_id"] and sd["parent_gtfs_id"] in stop_map:
                pk = stop_map[sd["gtfs_id"]]
                parent_pk = stop_map[sd["parent_gtfs_id"]]
                parent_updates.append((pk, parent_pk))

        if parent_updates:
            from django.db import connection
            with connection.cursor() as cursor:
                for pk, parent_pk in parent_updates:
                    cursor.execute(
                        "UPDATE geo_stop SET parent_station_id = %s WHERE id = %s",
                        [parent_pk, pk]
                    )
            self.stdout.write(f"  Resolved {len(parent_updates)} parent stations")

        self.stdout.write(
            f"  Stops: {len(to_create)} created, {len(to_update)} updated, "
            f"{skipped} unchanged, {len(removed)} removed"
        )
        if location_changed or name_changed:
            self.stdout.write(f"  Changes: {location_changed} location, {name_changed} name")

        changes = {
            "created": len(to_create),
            "updated": len(to_update),
            "removed": len(removed),
            "location_changed": location_changed,
            "name_changed": name_changed,
        }
        return stop_map, changes

    def _import_routes(self, zf, agency):
        """Import routes.txt with upsert + change detection. Returns ({source_id: Route.pk}, changes_dict).

        Multi-agency GTFS: routes are assigned to the correct agency via
        the agency_id column in routes.txt (matched against self._agency_map).
        """
        self.stdout.write("\n[4/9] Importing routes...")
        agency_map = getattr(self, '_agency_map', {})
        ds = agency.data_source
        synthesize_line_id = ds is not None and ds.slug in SYNTHESIZE_LINE_ID_FEEDS
        synth_line_from_name = ds is not None and ds.slug in SYNTHESIZE_LINE_ID_FROM_SHORTNAME

        routes_data = []
        feed_source_ids = set()
        for row in self._read_csv(zf, "routes.txt"):
            gtfs_id = row.get("route_id", "").strip()
            gtfs_agency_id = row.get("agency_id", "").strip()
            rd = {
                "gtfs_id": gtfs_id,
                "gtfs_agency_id": gtfs_agency_id,
                "short_name": row.get("route_short_name", "").strip()[:50],
                "long_name": row.get("route_long_name", "").strip()[:255],
                "description": row.get("route_desc", "").strip(),
                "route_type": int(row.get("route_type", "3").strip() or "3"),
                "route_color": row.get("route_color", "").strip()[:6],
                "route_text_color": row.get("route_text_color", "").strip()[:6],
                # Non-standard line grouping (CM ext). Absent on standard feeds → blank.
                "line_id": row.get("line_id", "").strip()[:100],
                "line_long_name": row.get("line_long_name", "").strip()[:255],
                "path_type": int(row.get("path_type", "0").strip() or "0"),
            }
            if synthesize_line_id and not rd["line_id"]:
                m = _VARIANT_ROUTE_ID_RE.match(gtfs_id)
                if m:
                    rd["line_id"] = m.group(1)[:100]
                    rd["path_type"] = int(m.group(2))
            elif (synth_line_from_name and not rd["line_id"]
                  and rd["route_type"] == _SUBURBAN_RAIL_ROUTE_TYPE and rd["short_name"]):
                # Group O-D variants by the line name. path_type stays 0 here;
                # _rank_synth_path_type ranks it by geometry length post-import.
                rd["line_id"] = rd["short_name"][:100]
            routes_data.append(rd)
            feed_source_ids.add(gtfs_id)

        # For multi-agency feeds, load existing routes for ALL agencies in this data source
        all_agencies = list(agency_map.values()) if agency_map else [agency]
        # Key by (agency_id, source_id) to handle same source_id across agencies
        existing_by_agency = {}  # {agency_id: {source_id: Route}}
        for ag in all_agencies:
            existing_by_agency[ag.id] = {r.source_id: r for r in Route.objects.filter(agency=ag)}
        # Also build flat lookup for backwards compat (any agency)
        existing_any = {}
        for agency_routes in existing_by_agency.values():
            existing_any.update(agency_routes)

        to_create = []
        to_update = []
        name_changed = 0
        skipped = 0

        for rd in routes_data:
            # Resolve the correct agency for this route
            route_agency = agency_map.get(rd["gtfs_agency_id"], agency) if agency_map else agency

            # Look up existing route: first in the correct agency, then any agency
            route_existing = existing_by_agency.get(route_agency.id, {}).get(rd["gtfs_id"])
            if not route_existing:
                # Check other agencies (route may have been misassigned previously)
                route_existing = existing_any.get(rd["gtfs_id"])

            if route_existing:
                route = route_existing
                changed = False

                # Move route to correct agency if it was misassigned
                if route.agency_id != route_agency.id:
                    route.agency = route_agency
                    route.slug = ""  # Reset slug for new agency context
                    changed = True

                # Detect short_name change → reset slug
                if route.short_name != rd["short_name"]:
                    route.short_name = rd["short_name"]
                    route.slug = ""  # Force slug regeneration
                    name_changed += 1
                    changed = True

                if route.long_name != rd["long_name"]:
                    route.long_name = rd["long_name"]
                    changed = True

                if route.description != rd["description"]:
                    route.description = rd["description"]
                    changed = True

                if route.route_type != rd["route_type"]:
                    route.route_type = rd["route_type"]
                    changed = True

                if route.route_color != rd["route_color"]:
                    route.route_color = rd["route_color"]
                    changed = True

                if route.route_text_color != rd["route_text_color"]:
                    route.route_text_color = rd["route_text_color"]
                    changed = True

                if route.line_id != rd["line_id"]:
                    route.line_id = rd["line_id"]
                    changed = True

                if route.line_long_name != rd["line_long_name"]:
                    route.line_long_name = rd["line_long_name"]
                    changed = True

                if route.path_type != rd["path_type"]:
                    route.path_type = rd["path_type"]
                    changed = True

                if changed:
                    to_update.append(route)
                else:
                    skipped += 1
            else:
                to_create.append(Route(
                    agency=route_agency,
                    source_id=rd["gtfs_id"],
                    short_name=rd["short_name"],
                    long_name=rd["long_name"],
                    description=rd["description"],
                    route_type=rd["route_type"],
                    route_color=rd["route_color"],
                    route_text_color=rd["route_text_color"],
                    line_id=rd["line_id"],
                    line_long_name=rd["line_long_name"],
                    path_type=rd["path_type"],
                ))

        if to_create:
            Route.objects.bulk_create(to_create, batch_size=5000)
        if to_update:
            Route.objects.bulk_update(to_update, [
                "agency", "short_name", "long_name", "description", "route_type",
                "route_color", "route_text_color", "slug",
                "line_id", "line_long_name", "path_type",
            ], batch_size=5000)

        # Clean up duplicate routes: if same source_id exists under multiple agencies,
        # keep only the one just processed (in to_update/to_create), delete the rest.
        # This handles legacy data where routes were duplicated across agencies.
        if len(all_agencies) > 1:
            processed_ids = set()
            for r in to_update:
                processed_ids.add(r.id)
            for r in to_create:
                if r.id:
                    processed_ids.add(r.id)
            # Also include existing routes that were skipped (unchanged)
            for rd in routes_data:
                route_agency = agency_map.get(rd["gtfs_agency_id"], agency) if agency_map else agency
                route_existing = existing_by_agency.get(route_agency.id, {}).get(rd["gtfs_id"])
                if route_existing:
                    processed_ids.add(route_existing.id)

            # Delete routes with same source_id but different id (the duplicates)
            from django.db import connection
            with connection.cursor() as c:
                agency_ids = [str(a.id) for a in all_agencies]
                c.execute("""
                    DELETE FROM geo_route WHERE id IN (
                        SELECT r.id FROM geo_route r
                        WHERE r.agency_id = ANY(%s)
                          AND r.source_id IN (
                              SELECT source_id FROM geo_route
                              WHERE agency_id = ANY(%s)
                              GROUP BY source_id HAVING COUNT(*) > 1
                          )
                          AND r.id != ALL(%s)
                    )
                """, [agency_ids, agency_ids, list(processed_ids) if processed_ids else ['']])
                if c.rowcount:
                    self.stdout.write(f"  Cleaned up {c.rowcount} duplicate routes across agencies")

        # Delete routes removed from feed (cascade deletes Trips, StopTimes, RouteStops)
        all_existing_ids = set(existing_any.keys())
        removed = all_existing_ids - feed_source_ids
        if removed:
            Route.objects.filter(agency__in=all_agencies, source_id__in=removed).delete()
            self.stdout.write(f"  Removed {len(removed)} stale routes")

        route_map = {}
        for r in Route.objects.filter(agency__in=all_agencies).only("id", "source_id"):
            route_map[r.source_id] = r.pk

        self.stdout.write(
            f"  Routes: {len(to_create)} created, {len(to_update)} updated, "
            f"{skipped} unchanged, {len(removed)} removed"
        )
        if name_changed:
            self.stdout.write(f"  Changes: {name_changed} short_name")

        # Invalidate transit routes cache (old version keys expire naturally)
        v = cache.get("transit:routes:version", 0)
        cache.set("transit:routes:version", v + 1, None)

        changes = {
            "created": len(to_create),
            "updated": len(to_update),
            "removed": len(removed),
            "name_changed": name_changed,
        }
        return route_map, changes

    def _import_shapes(self, zf, agency):
        """Import shapes.txt into Shape model (deduplicated by source_id per agency).
        Returns {gtfs_shape_id: Shape instance}."""
        self.stdout.write("\n[5/9] Importing shapes...")
        points = defaultdict(list)
        count = 0

        for row in self._read_csv(zf, "shapes.txt"):
            shape_id = row.get("shape_id", "").strip()
            lat = row.get("shape_pt_lat", "").strip()
            lon = row.get("shape_pt_lon", "").strip()
            seq = int(row.get("shape_pt_sequence", "0").strip())
            if not lat or not lon:
                continue
            points[shape_id].append((seq, float(lon), float(lat)))
            count += 1

        # Build geometry dict from parsed points
        geometries = {}
        for shape_id, pts in points.items():
            pts.sort(key=lambda x: x[0])
            coords = [(p[1], p[2]) for p in pts]
            if len(coords) >= 2:
                geometries[shape_id] = LineString(coords, srid=4326)

        # Load existing shapes for this agency
        existing = {s.source_id: s for s in Shape.objects.filter(agency=agency)}

        to_create = []
        to_update = []
        shape_map = {}  # gtfs_shape_id → Shape instance

        for shape_id, geom in geometries.items():
            if shape_id in existing:
                shape_obj = existing[shape_id]
                shape_map[shape_id] = shape_obj
                # Update geometry if changed (rare but possible on feed update)
                if shape_obj.geometry.wkb != geom.wkb:
                    shape_obj.geometry = geom
                    shape_obj.length_m = geom.transform(4326, clone=True).length  # will compute in DB
                    to_update.append(shape_obj)
            else:
                shape_obj = Shape(
                    agency=agency,
                    source_id=shape_id,
                    geometry=geom,
                    length_m=0,  # will be computed in bulk below
                )
                to_create.append(shape_obj)
                shape_map[shape_id] = shape_obj

        if to_create:
            Shape.objects.bulk_create(to_create, batch_size=5000)
        if to_update:
            Shape.objects.bulk_update(to_update, ["geometry", "length_m"], batch_size=5000)

        # Compute length_m in bulk via DB (ST_Length on geography is accurate)
        if to_create or to_update:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE geo_shape SET length_m = ST_Length(geometry::geography)
                    WHERE agency_id = %s AND length_m = 0
                """, [agency.id])

        # Delete shapes removed from feed
        feed_ids = set(geometries.keys())
        stale = set(existing.keys()) - feed_ids
        if stale:
            Shape.objects.filter(agency=agency, source_id__in=stale).delete()
            self.stdout.write(f"  Removed {len(stale)} stale shapes")

        self.stdout.write(f"  Parsed {count} shape points → {len(geometries)} shapes "
                          f"({len(to_create)} created, {len(to_update)} updated)")
        return shape_map

    def _import_trips(self, zf, agency, route_map, shape_map):
        """Import trips.txt with upsert (preserves ULIDs). Returns {source_id: (Trip.pk, route_pk, shape_id, dir_id)}.
        shape_map: {gtfs_shape_id: Shape instance} from _import_shapes."""
        self.stdout.write("\n[6/9] Importing trips...")

        # Load existing trips for all agencies in this data source
        agency_map = getattr(self, '_agency_map', {})
        all_agencies = list(agency_map.values()) if agency_map else [agency]
        existing = {
            t.source_id: t
            for t in Trip.objects.filter(route__agency__in=all_agencies).only(
                "id", "source_id", "route_id", "headsign", "service_id", "direction_id", "shape_ref_id"
            )
        }

        # Read feed data
        feed_data = []  # (source_id, route_pk, headsign, service_id, dir_id, shape_id)
        feed_source_ids = set()

        for row in self._read_csv(zf, "trips.txt"):
            trip_src_id = row.get("trip_id", "").strip()
            route_src_id = row.get("route_id", "").strip()
            shape_id = row.get("shape_id", "").strip()
            service_id = row.get("service_id", "").strip()
            direction_id = row.get("direction_id", "").strip()
            dir_id = int(direction_id) if direction_id else None

            route_pk = route_map.get(route_src_id)
            if not route_pk:
                continue

            headsign = row.get("trip_headsign", "").strip()[:255]
            feed_data.append((trip_src_id, route_pk, headsign, service_id, dir_id, shape_id))
            feed_source_ids.add(trip_src_id)

        to_create = []
        to_update = []
        skipped = 0

        for trip_src_id, route_pk, headsign, service_id, dir_id, shape_id in feed_data:
            shape_obj = shape_map.get(shape_id) if shape_id else None
            shape_ref_id = shape_obj.id if shape_obj else None

            if trip_src_id in existing:
                trip = existing[trip_src_id]
                changed = False

                if trip.route_id != route_pk:
                    trip.route_id = route_pk
                    changed = True
                if trip.headsign != headsign:
                    trip.headsign = headsign
                    changed = True
                if trip.service_id != service_id:
                    trip.service_id = service_id
                    changed = True
                if trip.direction_id != dir_id:
                    trip.direction_id = dir_id
                    changed = True
                if trip.shape_ref_id != shape_ref_id:
                    trip.shape_ref_id = shape_ref_id
                    changed = True

                if changed:
                    to_update.append(trip)
                else:
                    skipped += 1
            else:
                to_create.append(Trip(
                    route_id=route_pk,
                    source_id=trip_src_id,
                    headsign=headsign,
                    service_id=service_id,
                    direction_id=dir_id,
                    shape_ref_id=shape_ref_id,
                ))

        if to_create:
            Trip.objects.bulk_create(to_create, batch_size=5000)
        if to_update:
            Trip.objects.bulk_update(
                to_update,
                ["route_id", "headsign", "service_id", "direction_id", "shape_ref_id"],
                batch_size=5000,
            )

        # Delete trips removed from feed (cascade deletes their StopTimes)
        removed = set(existing.keys()) - feed_source_ids
        if removed:
            Trip.objects.filter(route__agency__in=all_agencies, source_id__in=removed).delete()
            self.stdout.write(f"  Removed {len(removed)} stale trips")

        # Build trip_info map: {source_id: (Trip.pk, route_pk, shape_id, dir_id)}
        # Re-read PKs for created trips
        trip_pk_map = {}
        for t in Trip.objects.filter(route__agency__in=all_agencies).only("id", "source_id"):
            trip_pk_map[t.source_id] = t.pk

        trip_info = {}
        for trip_src_id, route_pk, headsign, service_id, dir_id, shape_id in feed_data:
            pk = trip_pk_map.get(trip_src_id)
            if pk:
                trip_info[trip_src_id] = (pk, route_pk, shape_id, dir_id)

        self.stdout.write(
            f"  Trips: {len(to_create)} created, {len(to_update)} updated, "
            f"{skipped} unchanged, {len(removed)} removed"
        )
        return trip_info

    def _build_route_stops_fast(self, zf, trip_map, stop_map, route_map):
        """Build RouteStop from stop_times without importing all rows."""
        self.stdout.write("\n[7/9] Building route stops (fast mode)...")

        # (route_pk, direction_id) → {stop_pk: min_sequence}
        route_stops = defaultdict(dict)
        count = 0

        for row in self._read_csv(zf, "stop_times.txt"):
            trip_src_id = row.get("trip_id", "").strip()
            stop_src_id = row.get("stop_id", "").strip()
            seq = int(row.get("stop_sequence", "0").strip())

            trip_info = trip_map.get(trip_src_id)
            if not trip_info:
                continue
            _, route_pk, _, direction_id = trip_info

            stop_pk = stop_map.get(stop_src_id)
            if not stop_pk:
                continue

            key = (route_pk, direction_id)
            existing_seq = route_stops[key].get(stop_pk)
            if existing_seq is None or seq < existing_seq:
                route_stops[key][stop_pk] = seq

            count += 1
            if count % 1_000_000 == 0:
                self.stdout.write(f"  Scanned {count / 1_000_000:.0f}M stop_time rows...")

        # Delete existing
        route_pks = list(route_map.values())
        RouteStop.objects.filter(route_id__in=route_pks).delete()

        batch = []
        for (route_pk, direction_id), stops in route_stops.items():
            for stop_pk, seq in stops.items():
                batch.append(RouteStop(
                    route_id=route_pk,
                    stop_id=stop_pk,
                    sequence=seq,
                    direction_id=direction_id,
                ))

        RouteStop.objects.bulk_create(batch, batch_size=5000, ignore_conflicts=True)
        self.stdout.write(f"  Built {len(batch)} route-stop links from {count} rows")

    def _import_stop_times(self, zf, trip_map, stop_map, route_map):
        """Import stop_times.txt + build RouteStops."""
        self.stdout.write("\n[7/9] Importing stop_times (this may take a while)...")

        # Also build route stops as we go
        route_stops = defaultdict(dict)  # (route_pk, direction_id) → {stop_pk: min_sequence}

        # Delete existing stop_times and route_stops
        trip_pks = [info[0] for info in trip_map.values()]
        route_pks = list(route_map.values())

        self.stdout.write("  Deleting existing stop_times...")
        StopTime.objects.filter(trip_id__in=trip_pks).delete()
        RouteStop.objects.filter(route_id__in=route_pks).delete()

        batch = []
        count = 0
        created = 0

        for row in self._read_csv(zf, "stop_times.txt"):
            trip_src_id = row.get("trip_id", "").strip()
            stop_src_id = row.get("stop_id", "").strip()
            seq = int(row.get("stop_sequence", "0").strip())

            trip_info = trip_map.get(trip_src_id)
            if not trip_info:
                continue
            trip_pk, route_pk, _, direction_id = trip_info

            stop_pk = stop_map.get(stop_src_id)
            if not stop_pk:
                continue

            dep_raw = row.get("departure_time", "").strip()
            arr_time = self._parse_gtfs_time(row.get("arrival_time", "").strip())
            dep_time = self._parse_gtfs_time(dep_raw)
            if not arr_time or not dep_time:
                continue

            batch.append(StopTime(
                trip_id=trip_pk,
                stop_id=stop_pk,
                arrival_time=arr_time,
                departure_time=dep_time,
                departure_secs=self._parse_gtfs_secs(dep_raw),
                stop_sequence=seq,
            ))

            # Track route stops per direction
            key = (route_pk, direction_id)
            existing_seq = route_stops[key].get(stop_pk)
            if existing_seq is None or seq < existing_seq:
                route_stops[key][stop_pk] = seq

            count += 1

            if len(batch) >= 50_000:
                StopTime.objects.bulk_create(batch, batch_size=10000, ignore_conflicts=True)
                created += len(batch)
                batch.clear()
                self.stdout.write(f"  Processed {count / 1_000_000:.1f}M rows ({created} created)...")

        if batch:
            StopTime.objects.bulk_create(batch, batch_size=10000, ignore_conflicts=True)
            created += len(batch)

        self.stdout.write(f"  Imported {created} stop_times from {count} rows")

        # Build RouteStops
        self.stdout.write("\n[8/9] Building route stops...")
        rs_batch = []
        for (route_pk, direction_id), stops in route_stops.items():
            for stop_pk, seq in stops.items():
                rs_batch.append(RouteStop(
                    route_id=route_pk,
                    stop_id=stop_pk,
                    sequence=seq,
                    direction_id=direction_id,
                ))
        RouteStop.objects.bulk_create(rs_batch, batch_size=5000, ignore_conflicts=True)
        self.stdout.write(f"  Built {len(rs_batch)} route-stop links")

    def _parse_gtfs_time(self, time_str):
        """Parse GTFS time (HH:MM:SS, hours can be >= 24). Returns time string with wrapped hours."""
        if not time_str:
            return None
        parts = time_str.split(":")
        if len(parts) != 3:
            return None
        try:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return None
        # Wrap hours >= 24
        h = h % 24
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _parse_gtfs_secs(self, time_str):
        """GTFS time → seconds from service-day start, NOT wrapped (24:20→88800).
        Preserves the day-offset that _parse_gtfs_time loses to %24, so night
        service orders/displays correctly across midnight. None if unparseable."""
        if not time_str:
            return None
        parts = time_str.split(":")
        if len(parts) != 3:
            return None
        try:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return None
        return h * 3600 + m * 60 + s

    def _assign_route_geometry(self, agency, shape_map, route_map):
        """Assign Route.geometry from each route's longest shape (max length_m).

        Not "first trip's shape": trips of one route_id can reference short-turn
        shape variants (e.g. Metro de Lisboa Az: 693-trip full line + 2-trip
        short-turns), and an arbitrary pick can truncate the drawn route line.
        """
        self.stdout.write("\n[9/9] Assigning route geometry...")
        if not shape_map:
            self.stdout.write("  No shapes available, skipping")
            return

        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE geo_route r
                SET geometry = pick.geometry
                FROM (
                    SELECT DISTINCT ON (t.route_id) t.route_id, sh.geometry
                    FROM geo_trip t
                    JOIN geo_route rt ON rt.id = t.route_id
                    JOIN geo_shape sh ON sh.id = t.shape_ref_id
                    WHERE rt.agency_id = %s AND t.shape_ref_id IS NOT NULL
                    ORDER BY t.route_id, sh.length_m DESC NULLS LAST
                ) pick
                WHERE r.id = pick.route_id
                """,
                [str(agency.id)],
            )
            updated = cursor.rowcount

        self.stdout.write(f"  Assigned geometry to {updated} routes")

    def _rank_synth_path_type(self, agencies):
        """Rank path_type by descending geometry length within each synthesized
        line group (agency, line_id, short_name): longest variant → 0 (canonical).

        For feeds whose line_id is synthesized from short_name (SYNTHESIZE_LINE_ID_
        FROM_SHORTNAME) and which ship no native path_type. All canonical pickers
        (search / discover / sitemap / route-detail) key on LINE_CANONICAL_ORDER
        = (path_type, source_id), so this makes the full line — not a lexically
        smallest short-turn — the representative everywhere. Geometry-less
        variants sort last; ties broken by source_id for a stable order."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE geo_route r
                SET path_type = ranked.rn
                FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY agency_id, line_id, short_name
                        ORDER BY ST_Length(geometry::geography) DESC NULLS LAST, source_id
                    ) - 1 AS rn
                    FROM geo_route
                    WHERE agency_id = ANY(%s) AND line_id <> ''
                ) ranked
                WHERE r.id = ranked.id AND r.path_type IS DISTINCT FROM ranked.rn
                """,
                [[str(a.id) for a in agencies]],
            )
            self.stdout.write(f"  Ranked path_type for {cursor.rowcount} synthesized-line routes")

    def _assign_place_fks(self, agency):
        """Assign Stop.place and Route.place FKs via spatial query, update Place cached counts."""
        from django.db import connection

        self.stdout.write("\n[10] Assigning Place FKs...")

        # Assign Stop.place via ST_Within — prefer smallest containing polygon
        # (municipality over metro area) using ORDER BY ST_Area ASC
        with connection.cursor() as c:
            c.execute("""
                UPDATE geo_stop s SET place_id = (
                    SELECT p.id FROM geo_place p
                    WHERE p.geometry IS NOT NULL AND p.slug != ''
                      AND ST_Within(s.location::geometry, p.geometry::geometry)
                    ORDER BY ST_Area(p.geometry::geometry) ASC,
                             CASE p.place_type
                                 WHEN 'city' THEN 0
                                 WHEN 'region' THEN 1
                                 WHEN 'country' THEN 2
                                 ELSE 3
                             END ASC
                    LIMIT 1
                ) WHERE s.agency_id = %s AND s.place_id IS NULL
            """, [str(agency.id)])
            self.stdout.write(f"  Stops assigned to places: {c.rowcount}")

        # Assign Route.place from majority stop place (only routes without place)
        with connection.cursor() as c:
            c.execute("""
                UPDATE geo_route r
                SET place_id = sub.place_id
                FROM (
                    SELECT rs.route_id, s.place_id,
                           ROW_NUMBER() OVER (PARTITION BY rs.route_id ORDER BY COUNT(*) DESC) as rn
                    FROM geo_routestop rs
                    JOIN geo_stop s ON s.id = rs.stop_id
                    WHERE s.place_id IS NOT NULL
                      AND rs.route_id IN (SELECT id FROM geo_route WHERE agency_id = %s AND place_id IS NULL)
                    GROUP BY rs.route_id, s.place_id
                ) sub
                WHERE r.id = sub.route_id AND sub.rn = 1
            """, [str(agency.id)])
            self.stdout.write(f"  Routes assigned to places: {c.rowcount}")

        # Update cached counts on Place
        with connection.cursor() as c:
            c.execute("""
                UPDATE geo_place p
                SET transit_stops_count = COALESCE(sc.cnt, 0),
                    transit_routes_count = COALESCE(rc.cnt, 0)
                FROM (SELECT place_id, COUNT(*) cnt FROM geo_stop WHERE place_id IS NOT NULL GROUP BY place_id) sc
                FULL OUTER JOIN (SELECT place_id, COUNT(*) cnt FROM geo_route WHERE place_id IS NOT NULL GROUP BY place_id) rc
                    ON sc.place_id = rc.place_id
                WHERE p.id = COALESCE(sc.place_id, rc.place_id)
                  AND p.slug != ''
            """)
            self.stdout.write(f"  Updated cached counts on {c.rowcount} places")

    def _populate_route_places_m2m(self, agency):
        """Populate Route.places M2M from distinct stop places per route."""
        from django.db import connection

        self.stdout.write("\n[10b] Populating Route.places M2M...")

        with connection.cursor() as c:
            # Clear existing M2M for this agency's routes
            c.execute("""
                DELETE FROM geo_route_places
                WHERE route_id IN (SELECT id FROM geo_route WHERE agency_id = %s)
            """, [str(agency.id)])

            # Insert distinct place per route from stops
            c.execute("""
                INSERT INTO geo_route_places (route_id, place_id)
                SELECT DISTINCT rs.route_id, s.place_id
                FROM geo_routestop rs
                JOIN geo_stop s ON s.id = rs.stop_id
                WHERE s.place_id IS NOT NULL
                  AND rs.route_id IN (SELECT id FROM geo_route WHERE agency_id = %s)
                ON CONFLICT DO NOTHING
            """, [str(agency.id)])
            self.stdout.write(f"  Route-Place M2M links created: {c.rowcount}")

    def _assign_orphan_places(self, agency):
        """Assign stops/routes without a place to the nearest Place (scoped to agency)."""
        from django.db import connection

        self.stdout.write("\n[11] Assigning orphan stops/routes to nearest Place...")
        with connection.cursor() as c:
            c.execute("""
                UPDATE geo_stop s SET place_id = (
                    SELECT p.id FROM geo_place p
                    WHERE p.slug != '' AND p.center_point IS NOT NULL
                    ORDER BY s.location::geometry <-> p.center_point::geometry LIMIT 1
                ) WHERE s.place_id IS NULL AND s.agency_id = %s
            """, [str(agency.id)])
            self.stdout.write(f"  Orphan stops assigned: {c.rowcount}")

        with connection.cursor() as c:
            c.execute("""
                UPDATE geo_route r SET place_id = sub.place_id
                FROM (
                    SELECT rs.route_id, s.place_id,
                           ROW_NUMBER() OVER (PARTITION BY rs.route_id ORDER BY COUNT(*) DESC) as rn
                    FROM geo_routestop rs
                    JOIN geo_stop s ON s.id = rs.stop_id
                    WHERE s.place_id IS NOT NULL
                      AND rs.route_id IN (SELECT id FROM geo_route WHERE agency_id = %s AND place_id IS NULL)
                    GROUP BY rs.route_id, s.place_id
                ) sub
                WHERE r.id = sub.route_id AND sub.rn = 1
            """, [str(agency.id)])
            self.stdout.write(f"  Orphan routes assigned: {c.rowcount}")

    def _generate_slugs(self, agency):
        """Generate slugs for stops/routes that have slug='' (new records)."""
        from collections import defaultdict
        from django.utils.text import slugify

        self.stdout.write("\n[12] Generating slugs for new records...")

        # Stops
        stops_by_place = defaultdict(list)
        for s in Stop.objects.filter(agency=agency, slug="", place__isnull=False).order_by("source_id"):
            stops_by_place[s.place_id].append(s)

        stop_count = 0
        for place_id, stops in stops_by_place.items():
            existing = set(
                Stop.objects.filter(place_id=place_id).exclude(slug="").values_list("slug", flat=True)
            )
            used = set(existing)
            to_update = []
            for s in stops:
                base = slugify(s.name) or f"stop-{s.source_id}"
                base = base[:140]
                slug = base
                counter = 2
                while slug in used:
                    slug = f"{base}-{counter}"
                    counter += 1
                used.add(slug)
                s.slug = slug
                to_update.append(s)
            if to_update:
                Stop.objects.bulk_update(to_update, ["slug"], batch_size=5000)
                stop_count += len(to_update)

        # Routes
        routes_by_place = defaultdict(list)
        for r in Route.objects.filter(agency=agency, slug="", place__isnull=False).order_by("source_id"):
            routes_by_place[r.place_id].append(r)

        route_count = 0
        for place_id, routes in routes_by_place.items():
            existing = set(
                Route.objects.filter(place_id=place_id).exclude(slug="").values_list("slug", flat=True)
            )
            used = set(existing)
            to_update = []
            for r in routes:
                base = slugify(r.short_name) or f"route-{r.source_id}"
                base = base[:90]
                slug = base
                counter = 2
                while slug in used:
                    slug = f"{base}-{counter}"
                    counter += 1
                used.add(slug)
                r.slug = slug
                to_update.append(r)
            if to_update:
                Route.objects.bulk_update(to_update, ["slug"], batch_size=5000)
                route_count += len(to_update)

        self.stdout.write(f"  Generated slugs: {stop_count} stops, {route_count} routes")

    def _generate_route_slugs(self, agency):
        """Generate slugs for routes only (for secondary agencies in multi-agency GTFS)."""
        from collections import defaultdict
        from django.utils.text import slugify

        routes_by_place = defaultdict(list)
        for r in Route.objects.filter(agency=agency, slug="", place__isnull=False).order_by("source_id"):
            routes_by_place[r.place_id].append(r)

        if not routes_by_place:
            return

        route_count = 0
        for place_id, routes in routes_by_place.items():
            existing = set(
                Route.objects.filter(place_id=place_id).exclude(slug="").values_list("slug", flat=True)
            )
            used = set(existing)
            to_update = []
            for r in routes:
                base = slugify(r.short_name) or f"route-{r.source_id}"
                base = base[:90]
                slug = base
                counter = 2
                while slug in used:
                    slug = f"{base}-{counter}"
                    counter += 1
                used.add(slug)
                r.slug = slug
                to_update.append(r)
            if to_update:
                Route.objects.bulk_update(to_update, ["slug"], batch_size=5000)
                route_count += len(to_update)

        if route_count:
            self.stdout.write(f"  Generated route slugs for {agency.name}: {route_count}")
