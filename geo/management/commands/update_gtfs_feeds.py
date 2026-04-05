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

from geo.models import Agency, Route, Stop, TransitDataSource, Trip

CACHE_DIR = os.path.join(settings.BASE_DIR, 'gtfs_cache')

# Standard GTFS files to try when feed serves individual files instead of ZIP
GTFS_FILES = [
    'agency.txt', 'calendar.txt', 'calendar_dates.txt', 'routes.txt',
    'stops.txt', 'stop_times.txt', 'trips.txt', 'shapes.txt',
    'feed_info.txt', 'transfers.txt', 'frequencies.txt',
]
GTFS_REQUIRED = {'agency.txt', 'stops.txt', 'routes.txt', 'trips.txt', 'stop_times.txt'}


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
    headers = {'User-Agent': 'Mozilla/5.0 (parahub GTFS updater)'}
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


def _merge_gtfs_zips(zip_paths, output_path, skip_stop_times=True):
    """Merge multiple GTFS ZIPs into one with row-level deduplication."""
    merged = {}
    headers = {}
    seen = {}

    for zpath in zip_paths:
        with zipfile.ZipFile(zpath) as zf:
            for fname in zf.namelist():
                basename = os.path.basename(fname)
                if not basename.endswith('.txt') or basename.startswith('.'):
                    continue
                if skip_stop_times and basename == 'stop_times.txt':
                    continue
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

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for fname, rows in merged.items():
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=headers[fname])
            writer.writeheader()
            writer.writerows(rows)
            zout.writestr(fname, buf.getvalue())

    return sum(len(r) for r in merged.values())


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
            '--dry-run', action='store_true',
            help="Download and check hash but do not import",
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
        for ds in qs:
            result = self._process_feed(
                ds,
                force=options['force'],
                dry_run=options['dry_run'],
                from_cache=options['from_cache'],
            )
            results.append((ds.name, result))

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
                            resp = requests.get(url, stream=True, timeout=300, allow_redirects=True)
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
                            resp = requests.get(ds.url, stream=True, timeout=300)
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

            return {'skipped': False, 'stats': stats, 'from_cache': used_cache}

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
