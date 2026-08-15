"""Durable snapshot + restore for the transit segment priors keyspace.

Redis runs with persistence deliberately disabled (`save ""` — see
PK/infrastructure.md § Redis): everything it holds is rebuildable, EXCEPT
`transit:prior:*`, whose months of accumulated traversal statistics ARE the
data. This command is the persistence exception for that one keyspace:

- **dump**: SCAN all prior hashes and write them to a gzipped JSONL snapshot
  (atomic rename, previous generation kept as `*.prev.jsonl.gz`).
- **restore**: after a Redis wipe, merge the last snapshot back. All bucket
  fields are increment-only accumulators (`:n` count, `:l` sum of ln), so the
  merge is HINCRBY/HINCRBYFLOAT — exact even when post-wipe traffic has
  already written fresh increments on top of the empty keyspace.

A marker key (no TTL) records that the current Redis generation has been
seeded; it dies together with the data in a wipe, which is precisely when the
next run must restore again. Restore always runs before dump, so a post-wipe
run can never overwrite a good snapshot with a near-empty one.

Scheduled via `parahub-priors-sync.timer` (boot + every 6h); the loss window
after a crash is at most one timer interval of increments.
"""

import gzip
import os
from datetime import datetime, timezone

import orjson
from django.core.management.base import BaseCommand

from parahub.services.redis_pool import get_redis
from parahub.services.transit_eta import STT_PRIOR_TTL

DEFAULT_DIR = '/var/lib/parahub/transit-priors'
DEFAULT_PATTERN = 'transit:prior:*'
DEFAULT_MARKER = 'transit:priors:seeded'
SNAPSHOT_NAME = 'priors.jsonl.gz'
PREV_NAME = 'priors.prev.jsonl.gz'
PIPE_BATCH = 2000


class Command(BaseCommand):
    help = 'Snapshot transit segment priors to disk and restore them after a Redis wipe'

    def add_arguments(self, parser):
        parser.add_argument('--dir', default=DEFAULT_DIR, help='Snapshot directory')
        parser.add_argument('--pattern', default=DEFAULT_PATTERN, help='Redis key pattern to snapshot')
        parser.add_argument('--marker', default=DEFAULT_MARKER, help='Seed-marker key for the current Redis generation')
        parser.add_argument('--dump-only', action='store_true', help='Skip the restore phase')
        parser.add_argument('--restore-only', action='store_true', help='Skip the dump phase')

    def handle(self, *args, **opts):
        r = get_redis()
        os.makedirs(opts['dir'], exist_ok=True)
        if not opts['dump_only']:
            self._restore(r, opts)
        if not opts['restore_only']:
            self._dump(r, opts)

    # --- restore ---------------------------------------------------------

    def _snapshot_path(self, dirname):
        """Current snapshot, falling back to the previous generation (covers a
        crash between the two renames of the dump rotation)."""
        for name in (SNAPSHOT_NAME, PREV_NAME):
            path = os.path.join(dirname, name)
            if os.path.exists(path):
                return path
        return None

    def _restore(self, r, opts):
        if r.exists(opts['marker']):
            self.stdout.write('restore: marker present, keyspace already seeded — skip')
            return
        stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        # A concurrent run (manual + timer) must not merge the snapshot twice —
        # the increments would double every bucket.
        if not r.set(opts['marker'] + ':lock', stamp, nx=True, ex=600):
            self.stdout.write('restore: another restore is in progress — skip')
            return
        path = self._snapshot_path(opts['dir'])
        if path is None:
            r.set(opts['marker'], f'{stamp} first-run no-snapshot')
            self.stdout.write('restore: no snapshot yet (first run) — marker set')
            return

        keys = fields = skipped = 0
        pipe = r.pipeline(transaction=False)
        queued = 0
        with gzip.open(path, 'rb') as fh:
            for line in fh:
                try:
                    key, mapping = orjson.loads(line)
                except orjson.JSONDecodeError:
                    skipped += 1
                    continue
                keys += 1
                for f, v in mapping.items():
                    try:
                        if f.endswith(':n'):
                            pipe.hincrby(key, f, int(v))
                        elif f.endswith(':l'):
                            pipe.hincrbyfloat(key, f, float(v))
                        else:
                            continue
                    except (TypeError, ValueError):
                        skipped += 1
                        continue
                    fields += 1
                    queued += 1
                pipe.expire(key, STT_PRIOR_TTL)
                queued += 1
                if queued >= PIPE_BATCH:
                    pipe.execute()
                    pipe = r.pipeline(transaction=False)
                    queued = 0
        if queued:
            pipe.execute()
        r.set(opts['marker'], f'{stamp} restored keys={keys} fields={fields} from {os.path.basename(path)}')
        self.stdout.write(self.style.SUCCESS(
            f'restore: merged {keys} keys / {fields} fields from {path}'
            + (f' ({skipped} skipped)' if skipped else '')))

    # --- dump ------------------------------------------------------------

    def _dump(self, r, opts):
        current = os.path.join(opts['dir'], SNAPSHOT_NAME)
        prev = os.path.join(opts['dir'], PREV_NAME)
        tmp = current + '.tmp'

        keys = 0
        with gzip.open(tmp, 'wb', compresslevel=6) as out:
            batch = []
            pipe = r.pipeline(transaction=False)
            # _type guards against non-hash keys sneaking into the pattern
            # (e.g. a marker key under a test namespace) — HGETALL would
            # WRONGTYPE the whole pipeline batch.
            for k in r.scan_iter(opts['pattern'], count=1000, _type='hash'):
                batch.append(k)
                pipe.hgetall(k)
                if len(batch) >= PIPE_BATCH:
                    keys += self._write_batch(out, batch, pipe.execute())
                    batch = []
                    pipe = r.pipeline(transaction=False)
            if batch:
                keys += self._write_batch(out, batch, pipe.execute())
            out.flush()
            os.fsync(out.fileno())

        if keys == 0:
            # Empty keyspace (Redis just wiped and no snapshot existed): a
            # zero-key snapshot has nothing to protect and must not rotate a
            # real one into oblivion.
            os.unlink(tmp)
            self.stdout.write('dump: keyspace empty — snapshot untouched')
            return
        if os.path.exists(current):
            os.replace(current, prev)
        os.replace(tmp, current)
        self.stdout.write(self.style.SUCCESS(
            f'dump: {keys} keys → {current} ({os.path.getsize(current) // 1024} KiB)'))

    @staticmethod
    def _write_batch(out, batch_keys, batch_vals):
        n = 0
        for k, mapping in zip(batch_keys, batch_vals):
            if not mapping:
                continue
            out.write(orjson.dumps([k, mapping]) + b'\n')
            n += 1
        return n
