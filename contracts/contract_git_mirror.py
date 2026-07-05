"""
Contract Git Mirror — DB → private per-contract git repo.

Each contract gets its own LOCAL, PRIVATE repo at
{CONTRACTS_GIT_ROOT}/{contract_ulid}/ holding a self-contained proof bundle:

    contract.<fmt>        the agreement body (document_text); written only when a
                          body exists — legacy hash-only / upload contracts keep
                          their text off the server, so the file is omitted.
    canonical.json        the exact bytes both parties PGP-signed
                          (Contract.get_canonical_text()).
    meta.json             structured front-matter: parties, kind, status,
                          item_ids, booking_id, file_sha256, lifecycle timestamps.
    signatures/creator.asc, signatures/partner.asc   detached PGP signatures,
                          written as they appear over the contract lifecycle.

Clone the repo and everything verifies offline: check the signatures against
canonical.json, and file_sha256 == sha256(the contract body). git log/blame give
the redline history for free.

PRIVACY: these repos are LOCAL-ONLY — never pushed to a remote, never federated.
A P2P contract between individuals is private (git-centric-architecture.md). The
repo is a second server-side copy of data the DB already holds; the DB stays
authoritative (one-way DB → git, exactly the CMS mirror posture).

WRITER MODEL: a single-threaded drainer (contract_mirror_drain, on a systemd
timer) is the ONLY writer. The CMS post_save+daemon-thread mirror was removed
2026-04-11 after .git/index.lock races and intermediate-state corruption — do not
reintroduce per-save threads here.
"""
import json
import logging
import time
from datetime import timezone as dt_timezone
from pathlib import Path
from typing import Optional

import git
from django.conf import settings

logger = logging.getLogger(__name__)


def _contracts_git_root() -> Path:
    return Path(getattr(settings, 'CONTRACTS_GIT_ROOT', '/opt/parahub/contracts-repos'))


def _clear_stale_lock(repo_path: Path):
    """Remove index.lock left by a killed writer (older than 60s)."""
    lock = repo_path / '.git' / 'index.lock'
    if lock.exists():
        age = time.time() - lock.stat().st_mtime
        if age > 60:
            lock.unlink()
            logger.warning(f'Removed stale index.lock ({age:.0f}s old) in {repo_path}')


def _ensure_repo(repo_path: Path) -> git.Repo:
    """Get or init the per-contract repo (with a HEAD and a local commit identity)."""
    repo_path.mkdir(parents=True, exist_ok=True)
    _clear_stale_lock(repo_path)
    try:
        return git.Repo(repo_path)
    except git.InvalidGitRepositoryError:
        repo = git.Repo.init(repo_path)
        # Local commit identity so commits work regardless of global git config.
        with repo.config_writer() as cw:
            cw.set_value('user', 'name', 'Parahub Contract Mirror')
            cw.set_value('user', 'email', 'noreply@parahub.io')
        readme = repo_path / 'README.md'
        readme.write_text(
            f'# Contract {repo_path.name}\n\n'
            'Private, local-only proof bundle for one P2P contract: the agreement '
            'body, the exact signed bytes (canonical.json), detached PGP signatures, '
            'and structured metadata (meta.json).\n\n'
            'DB is authoritative (one-way DB → git mirror). Never pushed, never '
            'federated.\n',
            encoding='utf-8',
        )
        repo.index.add([str(readme)])
        repo.index.commit('init: contract repository')
        return repo


def _body_filename(contract) -> str:
    ext = 'md' if contract.document_format == 'markdown' else 'html'
    return f'contract.{ext}'


def _build_meta(contract) -> dict:
    """Structured front-matter mirrored alongside the body."""
    meta = {
        'id': contract.id,
        'object_type': 'contract',
        'title': contract.title,
        'kind': contract.kind,
        'status': contract.status,
        'creator_id': contract.creator_id,
        'partner_id': contract.partner_id,
        'arbiter_id': contract.arbiter_id,
        'file_sha256': contract.file_sha256,
        'document_format': contract.document_format,
        'has_body': bool(contract.document_text),
        'item_ids': sorted(contract.items.values_list('id', flat=True)),
        'arbitration_level': contract.arbitration_level,
        'created_at': contract.created_at.isoformat(),
        'creator_signed_at': contract.creator_signed_at.isoformat() if contract.creator_signed_at else None,
        'partner_signed_at': contract.partner_signed_at.isoformat() if contract.partner_signed_at else None,
        'creator_completed_at': contract.creator_completed_at.isoformat() if contract.creator_completed_at else None,
        'partner_completed_at': contract.partner_completed_at.isoformat() if contract.partner_completed_at else None,
        'updated_at': contract.updated_at.astimezone(dt_timezone.utc).isoformat(),
    }
    # Linked rental booking (reverse FK; optional, best-effort — keeps identity
    # decoupled from rental at import time).
    try:
        from rental.models import Booking
        bk = Booking.objects.filter(contract_id=contract.id).values_list('id', flat=True).first()
        if bk:
            meta['booking_id'] = bk
    except Exception:
        pass
    return meta


class ContractGitMirror:
    """Mirrors Contract rows to private per-contract git repos (DB → git, one-way)."""

    def __init__(self):
        self.root = _contracts_git_root()

    def _contract_repo(self, contract) -> git.Repo:
        return _ensure_repo(self.root / contract.id)

    def sync(self, contract) -> Optional[str]:
        """Write the proof bundle for one contract; commit only if it changed.

        Returns the new commit hash, or None when there was nothing to commit.
        """
        repo = self._contract_repo(contract)
        working = Path(repo.working_dir)
        added: list[str] = []

        # Body: write when present; otherwise drop any previously-written body
        # (handles a cleared body or a format change — keep the tree honest).
        existing_bodies = list(working.glob('contract.*'))
        if contract.document_text:
            body_path = working / _body_filename(contract)
            body_path.write_text(contract.document_text, encoding='utf-8')
            added.append(str(body_path))
            for f in existing_bodies:
                if f != body_path:
                    repo.index.remove([str(f)], working_tree=True)
        else:
            for f in existing_bodies:
                repo.index.remove([str(f)], working_tree=True)

        # Canonical signed bytes + structured metadata
        canonical_path = working / 'canonical.json'
        canonical_path.write_text(contract.get_canonical_text() + '\n', encoding='utf-8')
        added.append(str(canonical_path))

        meta_path = working / 'meta.json'
        meta_path.write_text(
            json.dumps(_build_meta(contract), indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )
        added.append(str(meta_path))

        # Detached signatures (as they appear over the contract lifecycle)
        sig_dir = working / 'signatures'
        sig_dir.mkdir(exist_ok=True)
        if contract.creator_signature:
            p = sig_dir / 'creator.asc'
            p.write_text(contract.creator_signature, encoding='utf-8')
            added.append(str(p))
        if contract.partner_signature:
            p = sig_dir / 'partner.asc'
            p.write_text(contract.partner_signature, encoding='utf-8')
            added.append(str(p))

        repo.index.add(added)

        if not repo.index.diff('HEAD') and not repo.untracked_files:
            return None

        try:
            commit = repo.index.commit(f'{contract.status.lower()}: {contract.title[:60]}')
        except Exception as e:
            logger.error(f'Contract mirror commit failed for {contract.id[:8]}: {e}')
            return None

        logger.info(f'Contract mirror {commit.hexsha[:8]}: {contract.status} {contract.id[:8]}')
        self._push_silent(repo)
        return commit.hexsha

    @staticmethod
    def _push_silent(repo: git.Repo):
        """Push to origin if a remote is configured.

        No remote yet (local-only). Kept so the Gitea-negotiation slice can add a
        private remote without touching this code path.
        """
        try:
            if 'origin' in [r.name for r in repo.remotes]:
                repo.remotes.origin.push()
        except Exception as e:
            logger.warning(f'Contract mirror push failed (will retry later): {e}')

    def sync_all(self) -> int:
        """Mirror every contract once (cold-start / catch-up). Returns commit count."""
        from contracts.models import Contract
        qs = Contract.objects.select_related(
            'creator', 'partner', 'arbiter',
        ).prefetch_related('items')
        n = 0
        for contract in qs.iterator(chunk_size=50):
            if self.sync(contract):
                n += 1
        logger.info(f'Contract mirror sync_all: {n} contracts committed')
        return n
