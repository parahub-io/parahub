"""
Step 1 — ingest: move uploaded photos from Hetzner to skystore, and reclaim
orphaned ODM scratch left behind by past failures.
"""

import logging
import os
import shutil
import time

from .constants import OPENSKY_BASE, SKYSTORE_FAST_PROCESSING, SKYSTORE_OPENSKY
from .remote import _skystore_rsync, _skystore_ssh

logger = logging.getLogger(__name__)


def upload_to_skystore(mission_id: str):
    """Move uploaded mission photos from Hetzner to skystore, delete local copy."""
    local_images = f"{OPENSKY_BASE}/missions/{mission_id}/images/"
    remote_mission = f"{SKYSTORE_OPENSKY}/missions/{mission_id}/"
    if not os.path.exists(local_images):
        raise FileNotFoundError(f"Local images not found: {local_images}")
    _skystore_ssh(f"mkdir -p {remote_mission}images")
    _skystore_rsync(local_images, f"{remote_mission}images/", timeout=1200)
    # Verify file count matches
    local_count = len([f for f in os.listdir(local_images) if f.lower().endswith(('.jpg', '.jpeg'))])
    result = _skystore_ssh(f"ls {remote_mission}images/*.jpg {remote_mission}images/*.JPG {remote_mission}images/*.jpeg 2>/dev/null | wc -l")
    remote_count = int(result.stdout.strip())
    if remote_count < local_count:
        raise RuntimeError(f"Upload verification failed: local={local_count}, remote={remote_count}")
    # Delete local copy
    shutil.rmtree(f"{OPENSKY_BASE}/missions/{mission_id}", ignore_errors=True)
    logger.info(f"Uploaded {local_count} photos to skystore, deleted local copy")


# Reclaim orphaned ODM scratch. /fast-processing is only 87 GB SSD and leaks when
# a run fails: process_mission keeps the temp dir "for diagnostics" (lightweight
# failure_logs are saved separately on skystore) and clears it only on retry —
# which may never come. Sweep dirs whose mission is no longer PROCESSING and
# untouched for > FAST_PROCESSING_ORPHAN_HOURS. Unknown dirs (manual experiments,
# lost+found) are left alone. The freshest failure stays briefly for live debug.
FAST_PROCESSING_ORPHAN_HOURS = 24


def sweep_orphaned_processing_dirs() -> int:
    """Delete stale /fast-processing/<mission_id> dirs for non-PROCESSING missions.

    Safe by construction: only removes a dir named after a known ULID whose mission
    is not currently PROCESSING (never yanks an active run) and whose mtime is older
    than the threshold. Returns the number of dirs reclaimed.
    """
    from geo.models import OpenSkyMission
    try:
        res = _skystore_ssh(
            f"find {SKYSTORE_FAST_PROCESSING} -maxdepth 1 -mindepth 1 -type d -printf '%f %T@\\n'"
        )
    except Exception as e:
        logger.warning(f"orphan sweep: cannot list {SKYSTORE_FAST_PROCESSING}: {e}")
        return 0

    now = time.time()
    cutoff = FAST_PROCESSING_ORPHAN_HOURS * 3600
    removed = 0
    for line in res.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        name, mtime = parts
        # Only ULID-named mission dirs (26 chars, Crockford base32). Skip everything else.
        if len(name) != 26 or not name.isalnum():
            continue
        try:
            age = now - float(mtime)
        except ValueError:
            continue
        if age < cutoff:
            continue
        m = OpenSkyMission.objects.filter(id=name).first()
        if m and m.status == OpenSkyMission.Status.PROCESSING:
            continue  # never reclaim an active run's scratch
        try:
            _skystore_ssh(f"sudo rm -rf {SKYSTORE_FAST_PROCESSING}/{name}")
            removed += 1
            logger.info(
                f"orphan sweep: reclaimed {SKYSTORE_FAST_PROCESSING}/{name} "
                f"(status={m.status if m else 'DELETED'}, age={age / 3600:.0f}h)"
            )
        except Exception as e:
            logger.warning(f"orphan sweep: failed to remove {name}: {e}")
    return removed
