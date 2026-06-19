"""
Auto-update GTFS static feeds registered in TransitDataSource.

Downloaded ZIPs are cached in BASE_DIR/gtfs_cache/{ds.id}.zip.
On download failure the cached file is used as fallback.

Usage:
    python3 manage.py update_gtfs_feeds
    python3 manage.py update_gtfs_feeds --force
    python3 manage.py update_gtfs_feeds --feed https://api.carrismetropolitana.pt/gtfs
    python3 manage.py update_gtfs_feeds --from-cache   # skip download, reimport from cache
    python3 manage.py update_gtfs_feeds --dry-run
"""

import csv
import hashlib
import io
import os
import shutil
import tempfile
import time
import zipfile
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone as dj_timezone

from geo.management.commands.import_gtfs import HTTP_HEADERS, _normalize_gtfs_zip

from geo.models import Agency, Route, Stop, TransitDataSource, Trip

CACHE_DIR = os.path.join(settings.BASE_DIR, 'gtfs_cache')

# Standard GTFS files to try when feed serves individual files instead of ZIP
GTFS_FILES = [
    'agency.txt', 'calendar.txt', 'calendar_dates.txt', 'routes.txt',
    'stops.txt', 'stop_times.txt', 'trips.txt', 'shapes.txt',
    'feed_info.txt', 'transfers.txt', 'frequencies.txt',
]
GTFS_REQUIRED = {'agency.txt', 'stops.txt', 'routes.txt', 'trips.txt', 'stop_times.txt'}

MOTIS_INPUT_DIR = '/opt/motis/input'
MOTIS_CONTAINER = 'parahub-motis'


def _cache_path(ds):
    return os.path.join(CACHE_DIR, f'{ds.id}.zip')


def _count_for_source(ds):
    agency_ids = list(Agency.objects.filter(data_source=ds).values_list('id', flat=True))
    return {
        'agencies': Agency.objects.filter(data_source=ds).count(),
        'stops': Stop.objects.filter(agency_id__in=agency_ids).count(),
        'routes': Route.objects.filter(agency_id__in=agency_ids).count(),
        'trips': Trip.objects.filter(route__agency_id__in=agency_ids).count(),
    }


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _is_valid_zip(path):
    """Check if file is a valid ZIP archive."""
    try:
        with zipfile.ZipFile(path, 'r') as zf:
            return len(zf.namelist()) > 0
    except (zipfile.BadZipFile, OSError):
        return False


def _bundle_gtfs_from_url(base_url, output_path, stdout=None):
    """Download individual GTFS .txt files from a directory URL and bundle into ZIP.

    Some operators (e.g. Wiener Linien) serve GTFS as individual files
    at a directory URL rather than a single ZIP download.
    """
    base = base_url.rstrip('/')
    headers = HTTP_HEADERS
    downloaded = {}

    for fname in GTFS_FILES:
        url = f'{base}/{fname}'
        try:
            resp = requests.get(url, headers=headers, timeout=60)
            start = resp.content.lstrip(b'\xef\xbb\xbf \t\r\n')[:15].lower()
            is_html = start.startswith(b'<!doctype') or start.startswith(b'<html')
            if resp.status_code == 200 and not is_html:
                downloaded[fname] = resp.content
                if stdout:
                    stdout.write(f"    fetched {fname} ({len(resp.content)} bytes)")
        except requests.RequestException:
            pass

    missing = GTFS_REQUIRED - set(downloaded.keys())
    if missing:
        raise RuntimeError(
            f"Cannot bundle GTFS from {base_url}: missing required files: {', '.join(sorted(missing))}"
        )

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname, content in downloaded.items():
            zf.writestr(fname, content)

    if stdout:
        stdout.write(f"    bundled {len(downloaded)} files into ZIP")


def _is_multi_url(url_text):
    """Check if URL field contains multiple URLs (one per line)."""
    urls = [u.strip() for u in url_text.strip().splitlines() if u.strip()]
    return len(urls) > 1, urls


# Primary key fields for GTFS deduplication
_GTFS_PK = {
    'agency.txt': 'agency_id',
    'routes.txt': 'route_id',
    'trips.txt': 'trip_id',
    'stops.txt': 'stop_id',
    'calendar.txt': 'service_id',
}


def _stream_merge_stop_times(zip_paths, zout):
    """Stream-merge stop_times.txt across feeds into an already-open output zip.

    stop_times is far too large to buffer like the other GTFS files — MTA Bus
    NYC's 5 boroughs are ~5-7M rows (~5GB as Python dicts). Rows are instead
    concatenated feed-by-feed straight into the zip entry. No dedup: trips are
    already deduped by trip_id upstream and per-feed trip_id namespaces don't
    collide (MTA boroughs), so no two feeds emit stop_times for the same trip.
    Returns the number of data rows written.
    """
    # Pass 1: union header (cheap — one header line per feed)
    union_header = []
    seen_h = set()
    sources = []  # (zpath, inner_fname)
    for zpath in zip_paths:
        with zipfile.ZipFile(zpath) as zf:
            for fname in zf.namelist():
                basename = os.path.basename(fname)
                if basename != 'stop_times.txt' or basename.startswith('.'):
                    continue
                sources.append((zpath, fname))
                with zf.open(fname) as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding='utf-8-sig'))
                    for h in next(reader, []):
                        if h not in seen_h:
                            seen_h.add(h)
                            union_header.append(h)
    if not sources:
        return 0

    # Pass 2: stream rows straight into the zip entry (never all in memory)
    count = 0
    entry = zout.open('stop_times.txt', mode='w', force_zip64=True)
    text_out = io.TextIOWrapper(entry, encoding='utf-8', newline='')
    try:
        writer = csv.DictWriter(text_out, fieldnames=union_header, extrasaction='ignore')
        writer.writeheader()
        for zpath, fname in sources:
            with zipfile.ZipFile(zpath) as zf, zf.open(fname) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig'))
                for row in reader:
                    writer.writerow(row)
                    count += 1
    finally:
        text_out.close()  # flushes + closes the zip entry
    return count


def _merge_gtfs_zips(zip_paths, output_path, skip_stop_times=False):
    """Merge multiple GTFS ZIPs into one with row-level deduplication.

    All GTFS files except stop_times.txt are read fully into memory and deduped
    by GTFS primary key. stop_times.txt is delegated to _stream_merge_stop_times
    (streamed, not buffered) — a multi-feed set like MTA Bus NYC's 5 boroughs is
    5-7M rows, too large to hold as dicts. skip_stop_times=True drops it entirely
    (legacy behaviour — leaves stops/routes unconnected, no schedule; only use
    when stop_times is deliberately unwanted).
    """
    merged = {}
    headers = {}
    seen = {}

    for zpath in zip_paths:
        with zipfile.ZipFile(zpath) as zf:
            for fname in zf.namelist():
                basename = os.path.basename(fname)
                if not basename.endswith('.txt') or basename.startswith('.'):
                    continue
                if basename == 'stop_times.txt':
                    continue  # streamed separately below (never buffered)
                with zf.open(fname) as f:
                    text = io.TextIOWrapper(f, encoding='utf-8-sig')
                    reader = csv.DictReader(text)
                    rows = list(reader)
                    if basename not in merged:
                        merged[basename] = []
                        headers[basename] = list(reader.fieldnames or [])
                        seen[basename] = set()
                    else:
                        # Union headers from all source ZIPs
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
                            key = None
                        if key is None or key not in seen[basename]:
                            merged[basename].append(row)
                            if key is not None:
                                seen[basename].add(key)

    st_rows = 0
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for fname, rows in merged.items():
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=headers[fname])
            writer.writeheader()
            writer.writerows(rows)
            zout.writestr(fname, buf.getvalue())

        if not skip_stop_times:
            st_rows = _stream_merge_stop_times(zip_paths, zout)

    return sum(len(r) for r in merged.values()) + st_rows


def _sync_to_motis(ds, zip_path, stdout=None):
    """Copy fresh GTFS ZIP into /opt/motis/input/ under canonical name.

    Nested-zip feeds (SEPTA) are flattened via _normalize_gtfs_zip first —
    MOTIS reads the raw file, so it must be a standard flat GTFS.

    Returns True if the destination file was created or changed (caller
    should then restart MOTIS), False if it was already identical (no-op).
    """
    if not ds.motis_input_name:
        return False

    normalized_path, is_temp = _normalize_gtfs_zip(zip_path, stdout=stdout)
    try:
        dest = os.path.join(MOTIS_INPUT_DIR, ds.motis_input_name)
        if os.path.exists(dest) and _sha256_file(dest) == _sha256_file(normalized_path):
            return False
        tmp = dest + '.tmp'
        shutil.copyfile(normalized_path, tmp)
        os.replace(tmp, dest)
        return True
    finally:
        if is_temp and os.path.exists(normalized_path):
            os.unlink(normalized_path)


def _reimport_motis(stdout):
    """Full MOTIS re-import cycle: stop server, run `/motis import`, start server.

    MOTIS `server` mode reads pre-built /data/ (nigiri timetable, OSR) — NOT
    raw /input/*.zip. A simple `docker restart` does NOT pick up new /input/
    files, so we must do a full re-import to refresh transit data.

    Duration: ~6-30 min typically (osr/matches cached), up to ~2h on cold
    cache. Server is unavailable for routing during this window.

    On failure (import non-zero exit): /data/ may be partially overwritten;
    attempts to start server anyway so error surfaces via /api/v1/plan
    returning errors rather than silently serving stale data. No automatic
    rollback yet — see `.todo/motis-blue-green-reimport.md`.
    """
    import subprocess
    try:
        inspect = subprocess.run(
            ['docker', 'inspect', MOTIS_CONTAINER, '--format', '{{.Config.Image}}'],
            check=True, capture_output=True, text=True, timeout=10,
        )
        image = inspect.stdout.strip()
        if not image:
            stdout.write(f"  WARN: could not determine MOTIS image — skipping re-import")
            return False
        stdout.write(f"  MOTIS re-import: image={image}")

        stdout.write(f"  MOTIS: stopping server...")
        subprocess.run(['docker', 'compose', 'stop', 'motis'],
                       cwd='/opt/parahub', check=True, capture_output=True, timeout=120)

        stdout.write(f"  MOTIS: /motis import (typically 6-30min, up to 2h cold cache)...")
        import_proc = subprocess.run(
            [
                'docker', 'run', '--rm',
                '--name', 'parahub-motis-import',
                '-w', '/data',
                '-v', '/opt/motis/data:/data',
                '-v', '/opt/motis/input:/input',
                '-v', '/opt/planet/planet-latest.osm.pbf:/input/planet-latest.osm.pbf:ro',
                '--network', 'none',
                '--memory=32g', '--cpus=8',
                image,
                '/motis', 'import', 'config.yml',
            ],
            capture_output=True, text=True, timeout=10800,
        )

        if import_proc.returncode != 0:
            stdout.write(f"  ERROR: MOTIS import rc={import_proc.returncode}")
            tail = (import_proc.stderr or import_proc.stdout or '')[-800:]
            stdout.write(f"  output tail: {tail}")
            subprocess.run(['docker', 'compose', 'up', '-d', 'motis'],
                           cwd='/opt/parahub', capture_output=True, timeout=120)
            return False

        stdout.write(f"  MOTIS: import done, starting server...")
        subprocess.run(['docker', 'compose', 'up', '-d', 'motis'],
                       cwd='/opt/parahub', check=True, capture_output=True, timeout=120)
        stdout.write(f"  MOTIS: server up with fresh data")
        return True

    except subprocess.TimeoutExpired as e:
        stdout.write(f"  ERROR: MOTIS re-import timeout after {e.timeout}s")
        return False
    except Exception as e:
        stdout.write(f"  WARN: MOTIS re-import failed: {e}")
        return False


def _delta_str(delta):
    if delta > 0:
        return f'+{delta}'
    elif delta < 0:
        return str(delta)
    return '='


class Command(BaseCommand):
    help = "Download and update all active GTFS static feeds, skipping unchanged ones"

    def add_arguments(self, parser):
        parser.add_argument(
            '--feed', metavar='URL',
            help="Update only this feed URL (default: all active GTFS feeds)",
        )
        parser.add_argument(
            '--force', action='store_true',
            help="Re-import even if file hash unchanged",
        )
        parser.add_argument(
            '--from-cache', action='store_true',
            help="Skip download, reimport from cached ZIP (useful when upstream is down)",
        )
        parser.add_argument(
            '--no-motis-reimport', action='store_true',
            help="Sync new ZIPs to /opt/motis/input/ but skip the MOTIS re-import cycle at the end",
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Download and check hash but do not import",
        )
        parser.add_argument(
            '--no-group-recompute', action='store_true',
            help="Skip the StopGroup (virtual stops) recompute at the end",
        )

    def handle(self, *args, **options):
        os.makedirs(CACHE_DIR, exist_ok=True)

        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
        self.stdout.write(f"=== GTFS Update {now_str} ===")

        qs = TransitDataSource.objects.filter(is_active=True, format='gtfs').exclude(url='')
        if options['feed']:
            qs = qs.filter(url=options['feed'])
            if not qs.exists():
                self.stderr.write(f"No active GTFS feed found with URL: {options['feed']}")
                return

        results = []
        any_motis_synced = False
        for ds in qs:
            result = self._process_feed(
                ds,
                force=options['force'],
                dry_run=options['dry_run'],
                from_cache=options['from_cache'],
            )
            if result.get('motis_synced'):
                any_motis_synced = True
            results.append((ds.name, result))

        if any_motis_synced and not options['dry_run'] and not options['no_motis_reimport']:
            self.stdout.write("")
            self.stdout.write("MOTIS inputs changed — full re-import cycle...")
            _reimport_motis(self.stdout)

        imported_any = any(
            not r.get('skipped') and not r.get('error') and not r.get('dry_run')
            for _, r in results
        )
        if imported_any and not options['no_group_recompute']:
            self.stdout.write("")
            self.stdout.write("Stops changed — recomputing virtual stop groups...")
            try:
                call_command('recompute_stop_groups', stdout=self.stdout, stderr=self.stderr)
            except Exception as e:  # feeds are already imported — don't fail the run
                self.stderr.write(self.style.ERROR(f"StopGroup recompute failed: {e}"))

        self.stdout.write("")
        for name, result in results:
            self.stdout.write(self._format_result(name, result))

    def _process_feed(self, ds, force=False, dry_run=False, from_cache=False):
        started_at = datetime.now(timezone.utc)
        t0 = time.time()
        cache_path = _cache_path(ds)

        zip_path = None
        used_cache = False
        tmp_path = None

        try:
            if from_cache:
                if not os.path.exists(cache_path):
                    return {'error': f'No cached file at {cache_path}'}
                zip_path = cache_path
                used_cache = True
                size_mb = os.path.getsize(zip_path) / 1024 / 1024
                self.stdout.write(f"  {ds.name}: using cache ({size_mb:.1f} MB)")
            else:
                is_multi, urls = _is_multi_url(ds.url)

                if is_multi:
                    # Multi-URL: download all, merge with dedup
                    self.stdout.write(f"  Downloading {ds.name}: {len(urls)} URLs")
                    try:
                        part_paths = []
                        for url in urls:
                            self.stdout.write(f"    {url}")
                            fd, part_path = tempfile.mkstemp(suffix='.zip', prefix='gtfs_part_')
                            os.close(fd)
                            resp = requests.get(url, headers=HTTP_HEADERS, stream=True, timeout=300, allow_redirects=True)
                            resp.raise_for_status()
                            with open(part_path, 'wb') as f:
                                for chunk in resp.iter_content(65536):
                                    f.write(chunk)
                            part_paths.append(part_path)

                        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.zip', prefix='gtfs_merged_')
                        os.close(tmp_fd)
                        total_rows = _merge_gtfs_zips(part_paths, tmp_path)
                        self.stdout.write(f"  {ds.name}: merged {len(urls)} feeds ({total_rows} rows)")

                        for p in part_paths:
                            os.unlink(p)

                        shutil.move(tmp_path, cache_path)
                        tmp_path = None
                        zip_path = cache_path
                        size_mb = os.path.getsize(zip_path) / 1024 / 1024
                        self.stdout.write(f"  {ds.name}: {size_mb:.1f} MB cached")
                    except Exception as dl_err:
                        # Clean up partial downloads
                        for p in part_paths:
                            if os.path.exists(p):
                                os.unlink(p)
                        if os.path.exists(cache_path):
                            zip_path = cache_path
                            used_cache = True
                            self.stdout.write(
                                f"  {ds.name}: multi-URL download failed ({dl_err}), "
                                f"falling back to cache"
                            )
                        else:
                            raise
                else:
                    # Single URL download
                    self.stdout.write(f"  Downloading {ds.name}: {ds.url}")
                    try:
                        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.zip', prefix='gtfs_')
                        os.close(tmp_fd)
                        need_bundle = False

                        try:
                            resp = requests.get(ds.url, headers=HTTP_HEADERS, stream=True, timeout=300)
                            resp.raise_for_status()
                            with open(tmp_path, 'wb') as f:
                                for chunk in resp.iter_content(65536):
                                    f.write(chunk)
                            need_bundle = not _is_valid_zip(tmp_path)
                        except requests.RequestException:
                            need_bundle = True

                        if need_bundle:
                            self.stdout.write(
                                f"  {ds.name}: not a ZIP download, "
                                f"fetching individual GTFS files..."
                            )
                            _bundle_gtfs_from_url(ds.url, tmp_path, stdout=self.stdout)

                        # Move to persistent cache
                        shutil.move(tmp_path, cache_path)
                        tmp_path = None  # moved, don't delete in finally
                        zip_path = cache_path
                        size_mb = os.path.getsize(zip_path) / 1024 / 1024
                        self.stdout.write(f"  {ds.name}: {size_mb:.1f} MB downloaded, cached")
                    except Exception as dl_err:
                        if os.path.exists(cache_path):
                            zip_path = cache_path
                            used_cache = True
                            size_mb = os.path.getsize(zip_path) / 1024 / 1024
                            self.stdout.write(
                                f"  {ds.name}: download failed ({dl_err}), "
                                f"falling back to cache ({size_mb:.1f} MB)"
                            )
                        else:
                            raise

            file_hash = _sha256_file(zip_path)
            size_mb = os.path.getsize(zip_path) / 1024 / 1024
            self.stdout.write(f"  {ds.name}: sha256={file_hash[:16]}...")

            # Check if unchanged (skip only when freshly downloaded, not from_cache)
            if not force and not from_cache and not used_cache and file_hash == ds.last_import_hash:
                stats = {
                    'started_at': started_at.isoformat(),
                    'duration_s': round(time.time() - t0, 1),
                    'skipped': True,
                    'error': None,
                }
                if not dry_run:
                    ds.last_import_stats = stats
                    ds.save(update_fields=['last_import_stats'])
                return {'skipped': True, 'reason': 'hash match'}

            if dry_run:
                return {
                    'skipped': False,
                    'dry_run': True,
                    'hash': file_hash,
                    'size_mb': round(size_mb, 1),
                    'would_import': True,
                    'from_cache': used_cache,
                }

            # Count before
            before = _count_for_source(ds)

            # Import
            self.stdout.write(f"  {ds.name}: importing...")
            call_command('import_gtfs', file=zip_path, feed_url=ds.url,
                         verbosity=0)

            # Count after
            after = _count_for_source(ds)
            duration = round(time.time() - t0, 1)

            def diff(key):
                return {'before': before[key], 'after': after[key], 'delta': after[key] - before[key]}

            stats = {
                'started_at': started_at.isoformat(),
                'duration_s': duration,
                'skipped': False,
                'agencies': diff('agencies'),
                'stops': diff('stops'),
                'routes': diff('routes'),
                'trips': diff('trips'),
                'error': None,
            }

            ds.last_import_hash = file_hash
            ds.last_import_stats = stats
            ds.last_imported_at = dj_timezone.now()
            ds.last_error = ''
            ds.save(update_fields=['last_import_hash', 'last_import_stats', 'last_imported_at', 'last_error'])

            motis_synced = _sync_to_motis(ds, zip_path, stdout=self.stdout)
            if motis_synced:
                self.stdout.write(f"  {ds.name}: synced to MOTIS /input/{ds.motis_input_name}")

            return {'skipped': False, 'stats': stats, 'from_cache': used_cache, 'motis_synced': motis_synced}

        except Exception as e:
            duration = round(time.time() - t0, 1)
            error_str = str(e)
            self.stderr.write(f"  ERROR {ds.name}: {error_str}")

            stats = {
                'started_at': started_at.isoformat(),
                'duration_s': duration,
                'skipped': False,
                'error': error_str,
            }
            if not dry_run:
                ds.last_error = error_str
                ds.last_import_stats = stats
                ds.save(update_fields=['last_error', 'last_import_stats'])

            return {'error': error_str}

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _format_result(self, name, result):
        pad = 30
        label = f"{name}:"

        if result.get('error'):
            return f"  {label:<{pad}} ERROR: {result['error']}"

        if result.get('skipped'):
            return f"  {label:<{pad}} skipped (unchanged, hash match)"

        if result.get('dry_run'):
            src = " [from cache]" if result.get('from_cache') else ""
            return (f"  {label:<{pad}} [dry-run] would import "
                    f"{result['size_mb']} MB, hash={result['hash'][:16]}...{src}")

        s = result['stats']
        r = s['routes']
        st = s['stops']
        tr = s['trips']
        dur = s['duration_s']
        src = " [from cache]" if result.get('from_cache') else ""

        return (
            f"  {label:<{pad}} "
            f"{r['after']} routes ({_delta_str(r['delta'])}), "
            f"{st['after']} stops ({_delta_str(st['delta'])}), "
            f"{tr['after']} trips ({_delta_str(tr['delta'])}) "
            f"— {dur}s{src}"
        )
