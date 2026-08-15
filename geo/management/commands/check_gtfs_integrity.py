"""Cross-check every foreign key inside a cached GTFS feed — operator data-quality watch.

The importer silently drops rows whose references don't resolve, so a feed can lose
thousands of timetable entries without anything failing. This reports what was
dropped and why, per feed, from the RAW cached download (`gtfs_cache/{ds.id}.zip`) —
i.e. exactly what the operator published, before any normalisation of ours.

    python3 manage.py check_gtfs_integrity                    # every active feed
    python3 manage.py check_gtfs_integrity --feed stcp-porto
    python3 manage.py check_gtfs_integrity --json

Findings land in `TransitDataSource.last_import_stats['integrity']` together with
the feed's own `feed_version`, so "have they fixed it yet?" is a DB lookup against a
named upstream build rather than a re-derivation. The importer rewrites that dict on
every run, so schedule this AFTER `update_gtfs_feeds` (same weekly timer).

Counts are ROWS, not distinct ids: rows are the passenger-visible loss (CM
2026-08-02: 11 759 `stop_times` rows dropped — 10 766 with an empty `stop_id`, 993
pointing at a stop deleted from `stops.txt`). See PK/gtfs-feed-quirks.md.
"""
import csv
import io
import json
import os
import zipfile
from datetime import timezone as dt_tz

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from geo.management.commands.import_gtfs import _normalize_gtfs_zip
from geo.models import TransitDataSource

CACHE_DIR_NAME = 'gtfs_cache'
MAX_EXAMPLES = 5

# (child file, child column, parent file(s), parent column, empty_is_error)
# Empty values are tolerated where GTFS allows them (agency_id on single-agency
# feeds, optional shape_id) and flagged where the spec requires a value.
CHECKS = [
    ('routes.txt', 'agency_id', ('agency.txt',), 'agency_id', False),
    ('trips.txt', 'route_id', ('routes.txt',), 'route_id', True),
    ('trips.txt', 'service_id', ('calendar.txt', 'calendar_dates.txt'), 'service_id', True),
    ('trips.txt', 'shape_id', ('shapes.txt',), 'shape_id', False),
    ('stop_times.txt', 'trip_id', ('trips.txt',), 'trip_id', True),
    ('stop_times.txt', 'stop_id', ('stops.txt',), 'stop_id', True),
    ('stops.txt', 'parent_station', ('stops.txt',), 'stop_id', False),
]


class Command(BaseCommand):
    help = "Cross-check foreign keys in cached GTFS feeds and record the findings."

    def add_arguments(self, parser):
        parser.add_argument('--feed', help='Feed slug (default: every active feed with a cached ZIP)')
        parser.add_argument('--json', action='store_true', help='Emit JSON instead of a text report')
        parser.add_argument('--no-save', action='store_true',
                            help='Report only, do not touch last_import_stats')
        parser.add_argument('--strict', action='store_true',
                            help='Exit non-zero when any dangling reference is found')

    def handle(self, *args, **opts):
        from django.conf import settings
        cache_dir = os.path.join(settings.BASE_DIR, CACHE_DIR_NAME)

        feeds = TransitDataSource.objects.filter(is_active=True)
        if opts['feed']:
            feeds = feeds.filter(slug=opts['feed'])
            if not feeds:
                raise CommandError(f"no active feed with slug '{opts['feed']}'")

        results, dirty = {}, False
        for ds in feeds:
            path = os.path.join(cache_dir, f'{ds.id}.zip')
            if not os.path.exists(path):
                results[ds.slug] = {'error': 'no cached ZIP — run update_gtfs_feeds first'}
                continue
            # Nested-ZIP feeds (SEPTA ships google_bus.zip + google_rail.zip) must be
            # flattened first or they would silently go unchecked — the one outcome
            # this command exists to prevent.
            normalized, is_temp = _normalize_gtfs_zip(path)
            try:
                res = self._check_zip(normalized)
                res['normalized'] = is_temp
            except zipfile.BadZipFile:
                results[ds.slug] = {'error': 'cached file is not a ZIP'}
                continue
            except KeyError as exc:
                results[ds.slug] = {'error': f'not a flat GTFS ZIP (missing {exc})'}
                continue
            finally:
                if is_temp and os.path.exists(normalized):
                    os.unlink(normalized)

            results[ds.slug] = res
            if res.get('total_bad_rows'):
                dirty = True
            if not opts['no_save']:
                stats = dict(ds.last_import_stats or {})
                stats['integrity'] = res
                TransitDataSource.objects.filter(id=ds.id).update(last_import_stats=stats)

        if opts['json']:
            self.stdout.write(json.dumps(results, indent=2, default=str))
        else:
            self._print(results)

        if opts['strict'] and dirty:
            raise CommandError('dangling references found')

    # ------------------------------------------------------------------ helpers

    def _rows(self, zf, name):
        with zf.open(name) as fh:
            yield from csv.DictReader(io.TextIOWrapper(fh, 'utf-8-sig'))

    def _values(self, zf, names, column):
        """Union of a column across the parent files that exist in the ZIP."""
        out = set()
        for name in names:
            if name not in zf.namelist():
                continue
            for row in self._rows(zf, name):
                v = (row.get(column) or '').strip()
                if v:
                    out.add(v)
        return out

    def _check_zip(self, path):
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if 'stops.txt' not in names:                     # zip-of-zips / multi-feed bundle
                raise KeyError('stops.txt')

            feed_version = ''
            if 'feed_info.txt' in names:
                row = next(self._rows(zf, 'feed_info.txt'), {})
                feed_version = (row.get('feed_version') or '').strip()

            single_agency = 'agency.txt' in names and sum(1 for _ in self._rows(zf, 'agency.txt')) == 1

            checks, total = {}, 0
            for child, column, parents, parent_col, empty_is_error in CHECKS:
                if child not in names or not any(p in names for p in parents):
                    continue
                valid = self._values(zf, parents, parent_col)
                bad_ids, bad_rows, empty_rows, seen = set(), 0, 0, 0
                for row in self._rows(zf, child):
                    if column not in row:
                        break                                 # optional column absent
                    seen += 1
                    v = (row.get(column) or '').strip()
                    if not v:
                        if empty_is_error and not (column == 'agency_id' and single_agency):
                            empty_rows += 1
                        continue
                    if v not in valid:
                        bad_ids.add(v)
                        bad_rows += 1
                if not seen:
                    continue
                bad = bad_rows + empty_rows
                total += bad
                checks[f'{child}:{column}'] = {
                    'rows_scanned': seen,
                    'dangling_ids': len(bad_ids),
                    'dangling_rows': bad_rows,
                    'empty_required_rows': empty_rows,
                    'examples': sorted(bad_ids)[:MAX_EXAMPLES],
                }

            return {
                'checked_at': timezone.now().astimezone(dt_tz.utc).isoformat(timespec='seconds'),
                'feed_version': feed_version,
                'zip_bytes': os.path.getsize(path),
                'total_bad_rows': total,
                'checks': checks,
            }

    def _print(self, results):
        w = self.stdout.write
        for slug, res in results.items():
            w('')
            if 'error' in res:
                w(self.style.WARNING(f'{slug}: {res["error"]}'))
                continue
            head = f'{slug}  feed_version={res["feed_version"] or "—"}'
            total = res['total_bad_rows']
            w(self.style.MIGRATE_HEADING(head))
            if not total:
                w(self.style.SUCCESS('  all references resolve'))
                continue
            w(self.style.ERROR(f'  {total} row(s) will be dropped on import'))
            for name, c in res['checks'].items():
                bad = c['dangling_rows'] + c['empty_required_rows']
                if not bad:
                    continue
                bits = []
                if c['dangling_rows']:
                    bits.append(f'{c["dangling_rows"]} rows → {c["dangling_ids"]} missing id(s) '
                                f'{c["examples"]}')
                if c['empty_required_rows']:
                    bits.append(f'{c["empty_required_rows"]} rows with an empty required value')
                w(f'    {name}: ' + '; '.join(bits))
