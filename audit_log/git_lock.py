"""
Stale git index.lock recovery.

GitPython never removes an index.lock left behind by a crashed process, so a
single dead writer permanently blocks every later commit (keyring, registry,
OTS batches) — and all those callers treat commit failures as non-fatal, so
the pipeline degrades silently. Incident 2026-06-29: one stale lock froze the
public audit/federation registry for five weeks.
"""
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# A legitimate index write holds the lock for well under a second; the most
# frequent writer (batch_ots_stamp) runs every 10 minutes. Anything older
# than this belongs to a dead process.
STALE_LOCK_AGE_SECONDS = 600


def clear_stale_index_lock(repo_path) -> bool:
    """Remove {repo_path}/.git/index.lock if older than STALE_LOCK_AGE_SECONDS.

    Returns True if a stale lock was removed.
    """
    lock = Path(repo_path) / '.git' / 'index.lock'
    try:
        age = time.time() - lock.stat().st_mtime
    except FileNotFoundError:
        return False
    if age < STALE_LOCK_AGE_SECONDS:
        return False
    try:
        lock.unlink()
    except FileNotFoundError:
        return False  # another process cleaned it up first
    logger.warning(f"Removed stale git index.lock (age {int(age)}s): {lock}")
    return True
