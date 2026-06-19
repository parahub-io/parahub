"""
CMS Git Mirror — syncs Post edits to git repos.

Two repos per establishment:
  - Editorial (private): drafts + published history, Gitea issues for discussions
  - Public mirror: published posts only, federated to other nodes

Architecture follows RegistryService pattern (GitPython, local repos with Gitea remotes).
"""
import json
import logging
import shutil
import time
from datetime import timezone
from pathlib import Path
from typing import Optional

import git
from django.conf import settings

logger = logging.getLogger(__name__)


def _cms_git_root() -> Path:
    return Path(getattr(settings, 'CMS_GIT_ROOT', '/opt/parahub/cms-repos'))


def _post_dir_name(post) -> str:
    """Directory name for a post in git: slug (unique per establishment)."""
    return post.slug


def _build_meta(post) -> dict:
    """Build meta.json content for a post."""
    meta = {
        'id': post.id,
        'title': post.title,
        'slug': post.slug,
        'language': post.language,
        'status': post.status,
        'excerpt': post.excerpt or '',
        'publish_order': post.publish_order,
        'author_id': post.author_id,
        'establishment_slug': post.establishment.slug if post.establishment else None,
    }

    if post.author:
        meta['author_hna'] = getattr(post.author, 'hna', '')

    if post.published_at:
        meta['published_at'] = post.published_at.isoformat()

    if post.translation_of_id:
        meta['translation_of_id'] = post.translation_of_id
        if post.translation_of:
            meta['translation_of_slug'] = post.translation_of.slug

    tags = list(post.tags.values_list('name', flat=True))
    if tags:
        meta['tags'] = tags

    if post.featured_image_id:
        meta['featured_image_id'] = post.featured_image_id

    meta['updated_at'] = post.updated_at.astimezone(timezone.utc).isoformat()
    return meta


def _write_post_files(base_dir: Path, post) -> list[str]:
    """Write content.md + meta.json for a post. Returns list of written paths."""
    post_dir = base_dir / _post_dir_name(post)
    post_dir.mkdir(parents=True, exist_ok=True)

    content_path = post_dir / 'content.md'
    meta_path = post_dir / 'meta.json'

    content_path.write_text(post.content or '', encoding='utf-8')
    meta_path.write_text(
        json.dumps(_build_meta(post), indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    return [str(content_path), str(meta_path)]


def _clear_stale_lock(repo_path: Path):
    """Remove index.lock if older than 60s — left by killed daemon threads."""
    lock = repo_path / '.git' / 'index.lock'
    if lock.exists():
        age = time.time() - lock.stat().st_mtime
        if age > 60:
            lock.unlink()
            logger.warning(f'Removed stale index.lock ({age:.0f}s old) in {repo_path}')


def _ensure_repo(repo_path: Path) -> git.Repo:
    """Get or init a git repo at the given path."""
    repo_path.mkdir(parents=True, exist_ok=True)
    _clear_stale_lock(repo_path)
    try:
        return git.Repo(repo_path)
    except git.InvalidGitRepositoryError:
        repo = git.Repo.init(repo_path)
        # Initial commit so we have a HEAD
        readme = repo_path / 'README.md'
        readme.write_text('# CMS Repository\n')
        repo.index.add([str(readme)])
        repo.index.commit('init: CMS repository')
        return repo


class CMSGitMirror:
    """
    Mirrors CMS Post changes to git repositories.

    Editorial repos (private, per-establishment):
      {CMS_GIT_ROOT}/editorial/{establishment_slug}/
        drafts/{post_slug}/content.md + meta.json
        published/{post_slug}/content.md + meta.json

    Public repo (federated):
      {CMS_GIT_ROOT}/public/
        {establishment_slug}/{post_slug}/content.md + meta.json
    """

    def __init__(self):
        self.root = _cms_git_root()

    # ── Editorial repo operations ──────────────────────────────────────

    def _editorial_repo(self, establishment_slug: str) -> git.Repo:
        return _ensure_repo(self.root / 'editorial' / establishment_slug)

    def sync_draft(self, post) -> Optional[str]:
        """Commit a draft post to the editorial repo. Returns commit hash."""
        if not post.establishment:
            return None

        slug = post.establishment.slug
        repo = self._editorial_repo(slug)
        drafts_dir = Path(repo.working_dir) / 'drafts'

        files = _write_post_files(drafts_dir, post)
        repo.index.add(files)

        # Check if there are actual changes to commit
        if not repo.index.diff('HEAD') and not repo.untracked_files:
            logger.debug(f'No changes for draft {post.slug} ({post.language})')
            return None

        try:
            commit = repo.index.commit(
                f'draft: {post.slug} ({post.language})'
            )
            logger.info(
                f'Editorial commit {commit.hexsha[:8]}: '
                f'draft {post.slug} ({post.language})'
            )
            self._push_silent(repo)
            return commit.hexsha
        except Exception as e:
            logger.error(f'Failed to commit draft {post.slug}: {e}')
            return None

    def sync_publish(self, post) -> Optional[str]:
        """
        Move post from drafts/ to published/ in editorial repo,
        then mirror to public repo. Returns public commit hash.
        """
        if not post.establishment:
            return None

        slug = post.establishment.slug
        repo = self._editorial_repo(slug)
        working = Path(repo.working_dir)

        draft_dir = working / 'drafts' / _post_dir_name(post)
        pub_dir = working / 'published' / _post_dir_name(post)

        # Write to published/ (even if draft/ doesn't exist — idempotent)
        pub_dir.mkdir(parents=True, exist_ok=True)
        pub_files = _write_post_files(working / 'published', post)
        repo.index.add(pub_files)

        # Remove from drafts/ if it exists
        removed = []
        if draft_dir.exists():
            for f in draft_dir.iterdir():
                removed.append(str(f))
            repo.index.remove(removed, working_tree=True)
            if draft_dir.exists():
                shutil.rmtree(draft_dir)

        try:
            commit = repo.index.commit(
                f'publish: {post.slug} ({post.language})'
            )
            logger.info(
                f'Editorial commit {commit.hexsha[:8]}: '
                f'publish {post.slug} ({post.language})'
            )
            self._push_silent(repo)
        except Exception as e:
            logger.error(f'Failed to commit publish {post.slug} in editorial: {e}')

        # Mirror to public repo
        return self._sync_to_public(post)

    # ── Public repo operations ─────────────────────────────────────────

    def _public_repo(self) -> git.Repo:
        return _ensure_repo(self.root / 'public')

    def _sync_to_public(self, post) -> Optional[str]:
        """Write a published post to the public federated repo."""
        if not post.establishment:
            return None

        repo = self._public_repo()
        est_dir = Path(repo.working_dir) / post.establishment.slug

        files = _write_post_files(est_dir, post)

        # Add PGP signature if available
        sig = self._sign_with_node_key(post)
        if sig:
            sig_path = est_dir / _post_dir_name(post) / 'signature.asc'
            sig_path.write_text(sig, encoding='utf-8')
            files.append(str(sig_path))

        repo.index.add(files)

        if not repo.index.diff('HEAD') and not repo.untracked_files:
            return None

        try:
            commit = repo.index.commit(
                f'publish: {post.establishment.slug}/{post.slug} ({post.language})'
            )
            logger.info(
                f'Public commit {commit.hexsha[:8]}: '
                f'{post.establishment.slug}/{post.slug} ({post.language})'
            )
            self._push_silent(repo)
            return commit.hexsha
        except Exception as e:
            logger.error(f'Failed to commit to public repo {post.slug}: {e}')
            return None

    def unpublish(self, post) -> Optional[str]:
        """Remove a post from the public repo (e.g. reverted to draft/archived)."""
        if not post.establishment:
            return None

        repo = self._public_repo()
        post_dir = Path(repo.working_dir) / post.establishment.slug / _post_dir_name(post)

        if not post_dir.exists():
            return None

        files = [str(f) for f in post_dir.iterdir()]
        if not files:
            return None

        try:
            repo.index.remove(files, working_tree=True)
            if post_dir.exists():
                shutil.rmtree(post_dir)
            commit = repo.index.commit(
                f'unpublish: {post.establishment.slug}/{post.slug} ({post.language})'
            )
            logger.info(f'Public commit {commit.hexsha[:8]}: unpublish {post.slug}')
            self._push_silent(repo)
            return commit.hexsha
        except Exception as e:
            logger.error(f'Failed to unpublish {post.slug}: {e}')
            return None

    # ── Node PGP signing ───────────────────────────────────────────────

    def _sign_with_node_key(self, post) -> Optional[str]:
        """Sign post content hash with the node PGP key."""
        import hashlib
        import subprocess
        import tempfile

        fingerprint = getattr(settings, 'FEDERATION_NODE_PGP_FINGERPRINT', '')
        if not fingerprint:
            return None

        content_hash = hashlib.sha256(
            (post.content or '').encode('utf-8')
        ).hexdigest()

        data = json.dumps({
            'post_id': post.id,
            'slug': post.slug,
            'language': post.language,
            'content_sha256': content_hash,
            'published_at': post.published_at.isoformat() if post.published_at else None,
        }, sort_keys=True, separators=(',', ':'))

        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                f.write(data)
                f.flush()
                result = subprocess.run(
                    ['gpg', '--batch', '--yes', '--armor',
                     '--local-user', fingerprint,
                     '--detach-sign', f.name],
                    capture_output=True, text=True, timeout=10,
                )
                sig_file = f.name + '.asc'
                if result.returncode == 0 and Path(sig_file).exists():
                    signature = Path(sig_file).read_text()
                    Path(sig_file).unlink(missing_ok=True)
                    Path(f.name).unlink(missing_ok=True)
                    return signature
                Path(f.name).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f'Node PGP signing failed for post {post.slug}: {e}')

        return None

    # ── Push helper ────────────────────────────────────────────────────

    @staticmethod
    def _push_silent(repo: git.Repo):
        """Push to origin if remote exists. Fail silently."""
        try:
            if 'origin' in [r.name for r in repo.remotes]:
                repo.remotes.origin.push()
        except Exception as e:
            logger.warning(f'Git push failed (will retry later): {e}')

    # ── Bulk operations ────────────────────────────────────────────────

    def initial_sync(self, establishment_slug: str = None):
        """
        Mirror all existing posts to git.
        Call once during setup, or to catch up after missed signals.
        """
        from cms.models import Post

        qs = Post.objects.select_related(
            'author', 'establishment', 'translation_of',
        ).prefetch_related('tags')

        if establishment_slug:
            qs = qs.filter(establishment__slug=establishment_slug)
        else:
            qs = qs.filter(establishment__isnull=False)

        synced = {'drafts': 0, 'published': 0}

        for post in qs.iterator(chunk_size=50):
            if post.status == 'published':
                self.sync_publish(post)
                synced['published'] += 1
            else:
                self.sync_draft(post)
                synced['drafts'] += 1

        logger.info(
            f'Initial sync complete: {synced["drafts"]} drafts, '
            f'{synced["published"]} published'
        )
        return synced
