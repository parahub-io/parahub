"""
Drain pending CMS mirror updates from DB to git.

Replaces the legacy per-save signal handler (which spawned daemon threads that
raced on .git/index.lock and left the mirror in inconsistent states). This
command runs single-threaded on a systemd timer, so races are physically
impossible.

Flow:
  1. Read last_sync_ts from Redis (default: epoch).
  2. Snapshot now() as new_sync_ts.
  3. Find Post.objects.filter(updated_at > last_sync_ts) — incremental sync.
  4. For each: sync_draft or sync_publish (same branching as the old signal).
  5. Clean orphan dirs: directories on disk for slugs no longer in DB (slug renames).
  6. On success, set last_sync_ts = new_sync_ts. On any sync error, leave it alone
     so the next tick retries.

Usage:
  python3 manage.py cms_mirror_drain                 # incremental
  python3 manage.py cms_mirror_drain --full          # force full resync
  python3 manage.py cms_mirror_drain --establishment parahub-associacao
  python3 manage.py cms_mirror_drain --dry-run       # show what would change
"""
import logging
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

import git
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.utils import timezone

from cms.git_mirror import CMSGitMirror
from cms.models import Post

logger = logging.getLogger(__name__)

LAST_SYNC_KEY = 'cms:mirror:last_sync_ts'


class Command(BaseCommand):
    help = 'Drain pending CMS mirror updates from DB to git (single-threaded)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--full',
            action='store_true',
            help='Ignore last_sync_ts and re-sync all posts',
        )
        parser.add_argument(
            '--establishment',
            help='Limit to one establishment slug',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='List posts that would sync, without touching git',
        )

    def handle(self, *args, full=False, establishment=None, dry_run=False, **kwargs):
        mirror = CMSGitMirror()
        now = timezone.now()

        # Determine watermark
        last_sync_iso = cache.get(LAST_SYNC_KEY)
        if full or not last_sync_iso:
            last_sync = datetime(2000, 1, 1, tzinfo=dt_timezone.utc)
            mode = 'full' if full else 'cold-start'
        else:
            last_sync = datetime.fromisoformat(last_sync_iso)
            mode = 'incremental'

        # Query changed posts (incremental)
        qs = Post.objects.select_related(
            'author', 'establishment', 'translation_of',
        ).prefetch_related('tags').filter(
            establishment__isnull=False,
            updated_at__gt=last_sync,
        ).order_by('updated_at')

        if establishment:
            qs = qs.filter(establishment__slug=establishment)

        changed_posts = list(qs)

        if dry_run:
            self.stdout.write(f'[{mode}] last_sync={last_sync.isoformat()} now={now.isoformat()}')
            self.stdout.write(f'{len(changed_posts)} posts would sync:')
            for p in changed_posts[:50]:
                self.stdout.write(
                    f'  {p.status:9s} {p.language} {p.establishment.slug}/{p.slug} '
                    f'(updated_at={p.updated_at.isoformat()})'
                )
            if len(changed_posts) > 50:
                self.stdout.write(f'  ... and {len(changed_posts) - 50} more')
            return

        # Sync each post (single-threaded, no races)
        synced = {'drafts': 0, 'published': 0, 'errors': 0}
        published_broadcasts = []

        for post in changed_posts:
            try:
                if post.status == 'published':
                    commit = mirror.sync_publish(post)
                    if commit:
                        published_broadcasts.append((post, commit))
                    synced['published'] += 1
                else:
                    # Draft or archived — remove from public mirror (idempotent) + write to editorial
                    mirror.unpublish(post)
                    mirror.sync_draft(post)
                    synced['drafts'] += 1
            except Exception as e:
                logger.error(
                    f'cms_mirror_drain: failed to sync {post.establishment.slug}/{post.slug} ({post.language}): {e}',
                    exc_info=True,
                )
                synced['errors'] += 1

        # Fire federation WS broadcasts for successfully published posts
        for post, commit_hash in published_broadcasts:
            try:
                from cms.signals import _broadcast_cms_update
                _broadcast_cms_update(post, commit_hash)
            except Exception as e:
                logger.warning(f'cms_mirror_drain: WS broadcast failed for {post.slug}: {e}')

        # Clean orphan directories (slug renames)
        orphans_cleaned = self._clean_orphans(mirror, establishment_slug=establishment)

        # Advance watermark only if all syncs succeeded. Errors retry next tick.
        if synced['errors'] == 0:
            cache.set(LAST_SYNC_KEY, now.isoformat(), timeout=None)
        else:
            logger.warning(
                f'cms_mirror_drain: {synced["errors"]} errors — watermark NOT advanced'
            )

        summary = (
            f'cms_mirror_drain [{mode}]: '
            f'{synced["drafts"]} drafts, {synced["published"]} published, '
            f'{synced["errors"]} errors, {orphans_cleaned} orphans cleaned'
        )
        logger.info(summary)
        self.stdout.write(summary)

    def _clean_orphans(self, mirror: CMSGitMirror, establishment_slug: str = None) -> int:
        """
        Find and git-rm draft directories whose slug no longer exists in DB.

        Slug renames are not handled by sync_draft (which only writes to the current
        slug's directory). Old directories accumulate as dead weight until cleaned.
        """
        root = mirror.root / 'editorial'
        if not root.exists():
            return 0

        cleaned = 0
        for est_dir in root.iterdir():
            if not est_dir.is_dir():
                continue
            if establishment_slug and est_dir.name != establishment_slug:
                continue

            drafts_dir = est_dir / 'drafts'
            if not drafts_dir.exists():
                continue

            # Current DB slugs for this establishment (drafts + archived)
            db_slugs = set(
                Post.objects.filter(
                    establishment__slug=est_dir.name,
                    status__in=['draft', 'archived'],
                ).values_list('slug', flat=True)
            )

            orphans = [
                d.name for d in drafts_dir.iterdir()
                if d.is_dir() and d.name not in db_slugs
            ]

            if not orphans:
                continue

            try:
                repo = git.Repo(est_dir)
                paths = [f'drafts/{slug}' for slug in orphans]
                repo.index.remove(paths, working_tree=True, r=True)
                repo.index.commit(
                    f'cleanup: remove {len(orphans)} orphan draft dir(s)'
                )
                mirror._push_silent(repo)
                cleaned += len(orphans)
                logger.info(
                    f'cms_mirror_drain: cleaned {len(orphans)} orphans in {est_dir.name}: {orphans}'
                )
            except Exception as e:
                logger.error(
                    f'cms_mirror_drain: orphan cleanup failed for {est_dir.name}: {e}',
                    exc_info=True,
                )

        return cleaned
