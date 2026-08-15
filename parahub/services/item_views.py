"""
Market item view counters — Redis-backed (CQRS: no per-view PostgreSQL writes).

Semantics: one view per viewer per item per 24 h (dedup marker), so the
"views" number reads as unique daily visitors rather than raw page hits.
Views are recorded by a client-side beacon (POST /items/{id}/view/), which
also keeps crawlers out of the numbers — bots don't fire JS beacons.

Durability: lifetime totals live in a Redis hash and are flushed hourly to
Item.views_total (management command `flush_item_views`), so a Redis wipe
loses at most ~1 hour of counts; the first increment after a wipe lazily
re-seeds the hash entry from PostgreSQL.

Keys (all in settings.REDIS_APP_DB):
  market:views:total                  HASH item_id -> lifetime views
  market:views:h:<YYYYMMDDHH>         HASH item_id -> views that hour (UTC, TTL 26 h)
  market:views:seen:<item>:<viewer>   dedup marker (TTL 24 h)
  market:views:dirty                  SET of item_ids with unflushed totals
"""

from datetime import datetime, timedelta, timezone

from django.conf import settings

from parahub.services.redis_pool import get_redis

KEY_TOTAL = 'market:views:total'
KEY_DIRTY = 'market:views:dirty'
HOUR_KEY_PREFIX = 'market:views:h:'
SEEN_KEY_PREFIX = 'market:views:seen:'
HOUR_FMT = '%Y%m%d%H'
SEEN_TTL = 24 * 3600
# Bucket must outlive the 24 h read window that starts at the end of its hour.
BUCKET_TTL = 26 * 3600


def _r():
    return get_redis(db=settings.REDIS_APP_DB)


def _hour_keys(count: int = 24) -> list[str]:
    """Bucket keys for the current hour and the (count-1) hours before it."""
    now = datetime.now(timezone.utc)
    return [
        f'{HOUR_KEY_PREFIX}{(now - timedelta(hours=i)).strftime(HOUR_FMT)}'
        for i in range(count)
    ]


def record_view(item_id: str, viewer_key: str) -> bool:
    """
    Count one view. Returns False when this viewer already viewed the item
    within the last 24 h (deduplicated), True when the view was counted.
    """
    r = _r()
    if not r.set(f'{SEEN_KEY_PREFIX}{item_id}:{viewer_key}', '1', nx=True, ex=SEEN_TTL):
        return False
    bucket = _hour_keys(count=1)[0]
    pipe = r.pipeline()
    pipe.hincrby(KEY_TOTAL, item_id, 1)
    pipe.hincrby(bucket, item_id, 1)
    pipe.expire(bucket, BUCKET_TTL)
    pipe.sadd(KEY_DIRTY, item_id)
    total = pipe.execute()[0]
    if total == 1:
        # First increment ever OR first after a Redis wipe — re-seed from PG.
        from market.models import Item
        db_total = (
            Item.objects.filter(id=item_id)
            .values_list('views_total', flat=True)
            .first()
        ) or 0
        if db_total:
            r.hincrby(KEY_TOTAL, item_id, db_total)
    return True


def get_stats(item_ids, db_totals: dict | None = None) -> dict:
    """
    Batch counters: {item_id: {'total': int, 'last24h': int}}.

    db_totals ({item_id: views_total from PG}) covers the Redis-wipe window
    before the lazy re-seed fires: the reported total is max(redis, db).
    """
    ids = list(item_ids)
    if not ids:
        return {}
    r = _r()
    pipe = r.pipeline()
    pipe.hmget(KEY_TOTAL, ids)
    hour_keys = _hour_keys()
    for hk in hour_keys:
        pipe.hmget(hk, ids)
    rows = pipe.execute()
    totals, hourly = rows[0], rows[1:]
    out = {}
    for idx, item_id in enumerate(ids):
        redis_total = int(totals[idx] or 0)
        db_total = int((db_totals or {}).get(item_id) or 0)
        out[item_id] = {
            'total': max(redis_total, db_total),
            'last24h': sum(int(h[idx] or 0) for h in hourly),
        }
    return out


def flush_totals() -> int:
    """
    Persist dirty Redis totals to Item.views_total. Returns items updated.
    Hash entries of deleted items are dropped so the hash can't grow forever.
    """
    from market.models import Item

    r = _r()
    dirty = list(r.smembers(KEY_DIRTY))
    if not dirty:
        return 0
    totals = r.hmget(KEY_TOTAL, dirty)
    counted = {i: int(t) for i, t in zip(dirty, totals) if t is not None}
    existing = set(
        Item.objects.filter(id__in=counted).values_list('id', flat=True)
    )
    updates = [
        Item(id=item_id, views_total=total)
        for item_id, total in counted.items()
        if item_id in existing
    ]
    if updates:
        # bulk_update bypasses Item.save() — no optimistic-lock version bump.
        Item.objects.bulk_update(updates, ['views_total'])
    orphans = [i for i in dirty if i not in existing]
    pipe = r.pipeline()
    if orphans:
        pipe.hdel(KEY_TOTAL, *orphans)
    pipe.srem(KEY_DIRTY, *dirty)
    pipe.execute()
    return len(updates)
