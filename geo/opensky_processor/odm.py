"""
Step 2 — ODM reconstruction on skystore (Docker GPU): the per-mission runner,
the split-merge consolidation runner, failure-log capture, and the
detached-container await/re-adopt loop.
"""

import logging
import subprocess

from .constants import (
    ODM_MAX_CONCURRENCY, ODM_RESOLUTION, ODM_SPLIT, ODM_SPLIT_OVERLAP,
    SKYSTORE_FAST_PROCESSING, SKYSTORE_ODM_IMAGE, SKYSTORE_OPENSKY,
)
from .remote import _skystore_ssh

logger = logging.getLogger(__name__)


def run_odm_skystore(mission_id: str) -> str:
    """Run ODM on skystore via SSH + Docker GPU. Returns remote orthophoto path."""
    remote_images = f"{SKYSTORE_OPENSKY}/missions/{mission_id}/images"
    remote_processing = f"{SKYSTORE_FAST_PROCESSING}/{mission_id}"
    remote_ortho = f"{remote_processing}/odm_orthophoto/odm_orthophoto.tif"
    container_name = f"odm-{mission_id[:12]}"

    # Skip if previous run already produced orthophoto (e.g. crashed at report stage)
    check = _skystore_ssh(f"test -f {remote_ortho} && echo exists || echo missing")
    if "exists" in check.stdout:
        logger.info(f"ODM orthophoto already exists, skipping ODM run: {remote_ortho}")
        return remote_ortho

    # Clean previous run (Docker creates root-owned files) and prepare project dir on SSD
    _skystore_ssh(f"sudo rm -rf {remote_processing} && mkdir -p {remote_processing}")
    # Remove stale container with same name if exists
    _skystore_ssh(f"docker rm -f {container_name} 2>/dev/null || true")
    # Symlink source images (on HDD) into processing dir (on SSD)
    _skystore_ssh(f"ln -sfn {remote_images} {remote_processing}/images")
    # --end-with odm_orthophoto: skip odm_report stage (broken in current ODM image due to numpy 1.x/2.x conflict)
    docker_cmd = (
        f"docker run --name {container_name} --gpus all"
        f" -v {SKYSTORE_FAST_PROCESSING}:{SKYSTORE_FAST_PROCESSING}"
        f" -v {SKYSTORE_OPENSKY}/missions:{SKYSTORE_OPENSKY}/missions:ro"
        f" {SKYSTORE_ODM_IMAGE}"
        f" --project-path {SKYSTORE_FAST_PROCESSING}"
        f" --orthophoto-resolution {ODM_RESOLUTION}"
        f" --feature-quality high"
        f" --pc-quality high"
        f" --max-concurrency {ODM_MAX_CONCURRENCY}"
        f" --dsm"
        # NO --optimize-disk-space since the 2TB NVMe (2026-06-12): it was for the
        # 87GB-SSD era and deletes resume checkpoints (features/matches/dmaps) —
        # a power-loss restart then re-derives ~1.5h. Peak ~300GB fits easily;
        # scratch is removed on success anyway.
        f" --end-with odm_orthophoto"
        f" {mission_id}"
    )
    logger.info(f"Running ODM on skystore: {docker_cmd}")
    try:
        _skystore_ssh(docker_cmd, timeout=28800)  # 8h timeout (large missions)
    except subprocess.CalledProcessError:
        # Capture docker logs before cleanup
        _save_odm_failure_logs(mission_id, container_name)
        raise
    finally:
        # Remove container (logs already saved on failure)
        _skystore_ssh(f"docker rm -f {container_name} 2>/dev/null || true")
    result = _skystore_ssh(f"test -f {remote_ortho} && echo ok")
    if "ok" not in result.stdout:
        raise RuntimeError("ODM on skystore failed to produce orthophoto")
    return remote_ortho


def _save_odm_failure_logs(mission_id: str, container_name: str):
    """Save docker logs and system state to skystore for post-mortem analysis."""
    log_dir = f"{SKYSTORE_OPENSKY}/missions/{mission_id}/failure_logs"
    try:
        _skystore_ssh(f"mkdir -p {log_dir}")
        # Docker logs (last 500 lines)
        _skystore_ssh(
            f"docker logs --tail 500 {container_name} > {log_dir}/odm_stdout.log 2> {log_dir}/odm_stderr.log || true"
        )
        # System state at time of failure
        _skystore_ssh(
            f"echo '=== dmesg (OOM) ===' > {log_dir}/system.log"
            f" && dmesg -T 2>/dev/null | grep -i -E 'oom|kill|memory' | tail -30 >> {log_dir}/system.log || true"
            f" && echo '\\n=== free ===' >> {log_dir}/system.log"
            f" && free -h >> {log_dir}/system.log"
            f" && echo '\\n=== df ===' >> {log_dir}/system.log"
            f" && df -h /fast-processing /skystore >> {log_dir}/system.log"
        )
        logger.error(f"ODM failure logs saved to skystore: {log_dir}")
    except Exception as ex:
        logger.error(f"Failed to save ODM failure logs: {ex}")


def run_odm_splitmerge_skystore(consolidation_id: str, no_split: bool = False,
                                gps_accuracy: float = None) -> str:
    """Run ODM joint reconstruction on a prepared combined project.

    Assumes process_consolidation() has already populated
    /fast-processing/{cid}/images with all members' photos (prefixed). Returns
    the merged orthophoto path. Default adds --split/--split-overlap (memory-
    bounded submodels); `no_split=True` runs ONE global model — no submodel
    alignment step to fail (run-4 merged quadrants 26-49m apart), at the cost
    of a single big dense fusion (~65MB/img at high — budget RAM+swap; the
    48GB+80G-swap skystore covers the 1446-photo church cluster).

    gps_accuracy overrides ODM's --gps-accuracy (default 3m). For a CROSS-SEASON
    consolidation the 3m default is too tight: each flight-day carries its own
    absolute DJI-GPS bias (~10-24m, measured 2026-06-12), and a 3m GPS sigma
    pins each flight to its biased coords in BA, so cross-season feature matches
    (which exist) cannot weld the blocks — the merged mosaic comes out displaced
    per-flight (run-5b gate refusal, spread 10.8m). Raising it to ~30m lets the
    features dominate relative geometry (biases fall inside 1σ → treated as
    noise); absolute georef is then restored by the members anchor. See
    PK/opensky-system.md § GPS weight.
    """
    r_processing = f"{SKYSTORE_FAST_PROCESSING}/{consolidation_id}"
    r_ortho = f"{r_processing}/odm_orthophoto/odm_orthophoto.tif"
    container_name = f"odmsm-{consolidation_id[:10]}"

    # Skip if a previous run already produced the merged ortho (resume)
    check = _skystore_ssh(f"test -f {r_ortho} && echo exists || echo missing")
    if "exists" in check.stdout:
        logger.info(f"Split-merge ortho already exists, skipping ODM: {r_ortho}")
        return r_ortho

    # Re-adopt a still-running container instead of killing it: the container
    # is local to skystore and survives tunnel flaps / orchestrator restarts —
    # only our visibility dies. rm -f here would murder hours of healthy ODM.
    st = _skystore_ssh(
        f"docker inspect -f '{{{{.State.Status}}}}' {container_name} 2>/dev/null || echo absent")
    status = (st.stdout or 'absent').strip().splitlines()[-1]
    if status == 'running':
        logger.info(
            f"ODM container {container_name} already running — re-adopting "
            f"(orchestrator restart while ODM in flight)")
        return _await_odm_container(consolidation_id, container_name, r_ortho)

    _skystore_ssh(f"docker rm -f {container_name} 2>/dev/null || true")

    # A PARTIAL features/ dir (run killed mid-extraction) makes ODM skip
    # detection entirely (its stage gate is dir-existence, per-image skip lives
    # only INSIDE detect_features) and then crash instantly in match_features.
    # Clear it for a clean re-detect; complete features (== image count) and
    # absent features are both fine as-is.
    n_imgs = (_skystore_ssh(f"ls {r_processing}/images 2>/dev/null | wc -l").stdout or '0').strip()
    n_feat = (_skystore_ssh(f"ls {r_processing}/opensfm/features 2>/dev/null | wc -l").stdout or '0').strip()
    if n_feat.isdigit() and n_imgs.isdigit() and 0 < int(n_feat) < int(n_imgs):
        logger.info(
            f"Consolidation {consolidation_id[:8]}: partial features dir "
            f"({n_feat}/{n_imgs}) — clearing for clean re-detect")
        _skystore_ssh(f"sudo rm -rf {r_processing}/opensfm/features")

    docker_cmd = (
        f"docker run -d --name {container_name} --gpus all"
        f" -v {SKYSTORE_FAST_PROCESSING}:{SKYSTORE_FAST_PROCESSING}"
        f" {SKYSTORE_ODM_IMAGE}"
        f" --project-path {SKYSTORE_FAST_PROCESSING}"
        f" --orthophoto-resolution {ODM_RESOLUTION}"
        f" --feature-quality high"
        # pc-quality high needs ~41GB RAM+swap for a cross-season consolidation
        # (medium ≈34GB): on the 16GB skystore OpenMVS DensifyPointCloud OOM-killed
        # 3x with swap 100% full. Fusion memory is nearly insensitive to pc-quality
        # (high→medium −12%; `low` is NOT a validated escape). Seamlessness comes
        # from the joint SfM, not pc-quality — on 16GB add a second swapfile or
        # consolidate per column-pair. See PK/opensky-system.md § Memory budget.
        f" --pc-quality high"
        f" --max-concurrency {ODM_MAX_CONCURRENCY}"
        f" --dsm"
        # NO --optimize-disk-space (see process_mission): on 1.7T NVMe it only
        # destroys resume checkpoints — cost ~1.5h re-derive per interruption.
        + (f" --gps-accuracy {gps_accuracy}" if gps_accuracy else "")
        + ("" if no_split else f" --split {ODM_SPLIT} --split-overlap {ODM_SPLIT_OVERLAP}")
        + f" --end-with odm_orthophoto"
        f" {consolidation_id}"
    )
    # Run detached so the multi-hour job lives in the docker daemon, independent
    # of this SSH session. Then poll the container until it exits.
    logger.info(f"Running ODM split-merge on skystore: {docker_cmd}")
    _skystore_ssh(docker_cmd, timeout=120)
    return _await_odm_container(consolidation_id, container_name, r_ortho)


def _await_odm_container(consolidation_id: str, container_name: str, r_ortho: str) -> str:
    """Block until the detached ODM container exits; save its full log; verify ortho.

    The container is removed ONLY once it has provably exited — on transport
    errors (tunnel flap, orchestrator death) it is left running so a restarted
    orchestrator re-adopts it instead of redoing hours of reconstruction.
    """
    container_done = False
    try:
        result = _skystore_ssh(f"docker wait {container_name}", timeout=57600)  # 16h ceiling
        exit_code = (result.stdout or '').strip().splitlines()[-1] if result.stdout.strip() else '?'
        container_done = True
        if exit_code != '0':
            _save_odm_failure_logs(consolidation_id, container_name)
            raise RuntimeError(f"ODM split-merge exited {exit_code}")
    finally:
        # Keep the FULL ODM log on success too — the run-4 submodel-merge
        # failure (quadrants 26-49m apart) had no forensics because logs died
        # with the container and scratch was cleaned on "success".
        try:
            _skystore_ssh(
                f"mkdir -p {SKYSTORE_OPENSKY}/missions/{consolidation_id} && "
                f"docker logs {container_name} > {SKYSTORE_OPENSKY}/missions/{consolidation_id}/odm_splitmerge.log 2>&1 || true",
                timeout=300,
            )
            if container_done:
                _skystore_ssh(f"docker rm -f {container_name} 2>/dev/null || true")
        except Exception as log_err:  # never mask the real failure with log plumbing
            logger.warning(f"Could not save ODM log / remove container (tunnel down?): {log_err}")

    ok = _skystore_ssh(f"test -f {r_ortho} && echo ok || echo no")
    if "ok" not in ok.stdout:
        raise RuntimeError("ODM split-merge produced no merged orthophoto")
    return r_ortho
