"""
Step 3.5 / Phase 1 — translation consensus: robust weighted average of ORB
edges with median outlier filter and satellite-anchor damping, plus the
fixed-shift warp script and the apply+retile path for published missions.
"""

import logging
import shlex

from .common import _is_superseded
from .constants import (
    MAX_CONSENSUS_SHIFT_M, MIN_CONSENSUS_SHIFT_M, OUTLIER_FLOOR_M,
    OUTLIER_MEDIAN_MULTIPLE, SATELLITE_DAMPING_WEIGHT,
    SKYSTORE_FAST_PROCESSING, SKYSTORE_OPENSKY,
)
from .pose_graph import _mark_georef_changed, measure_orb_edges_skystore
from .remote import _skystore_ssh
from .tiles import _reclip_retile_publish

logger = logging.getLogger(__name__)


def _build_apply_shift_script(r_src, r_dst, dx_m, dy_m):
    """Build script to apply a fixed (dx, dy) translation to a target ortho's
    georeference via rasterio Affine transform.
    """
    return f'''
import rasterio
from rasterio.transform import Affine
with rasterio.open("{r_src}") as src:
    new_tf = Affine(
        src.transform.a, src.transform.b, src.transform.c + {dx_m:.6f},
        src.transform.d, src.transform.e, src.transform.f + {dy_m:.6f},
    )
    profile = src.profile.copy()
    profile.update(transform=new_tf)
    with rasterio.open("{r_dst}", "w", **profile) as dst:
        for i in range(1, src.count + 1):
            dst.write(src.read(i), i)
print("APPLY_OK")
'''


def compute_consensus_shift(mission_id: str, edges: list):
    """Robust weighted consensus from ORB edges + satellite anchor damping.

    1. Outlier filter: reject edges where |shift| > max(3×median, 2m floor).
    2. Weighted average: weight = overlap_m2 × inlier_ratio.
    3. Satellite anchor: virtual (0,0) edge with SATELLITE_DAMPING_WEIGHT.
       Damps oscillation + prevents unbounded group drift from absolute frame.
       (Satellite alignment already baked into ortho position — (0,0) means
       'stay at satellite-corrected position'.)

    Returns dict {avg_dx, avg_dy, n_used, n_filtered_outliers, shift_m, total_weight}.
    """
    import statistics

    if not edges:
        return {
            'avg_dx': 0.0, 'avg_dy': 0.0,
            'n_used': 0, 'n_filtered_outliers': 0,
            'shift_m': 0.0, 'total_weight': 0.0,
        }

    mags = [(e['dx_m']**2 + e['dy_m']**2) ** 0.5 for e in edges]
    med = statistics.median(mags)
    threshold = max(OUTLIER_MEDIAN_MULTIPLE * med, OUTLIER_FLOOR_M)

    kept = []
    n_outliers = 0
    for e, mag in zip(edges, mags):
        if mag > threshold:
            n_outliers += 1
            logger.info(
                f"Consensus {mission_id}: FILTER outlier {e['neighbor_id'][-5:]} "
                f"|shift|={mag:.2f}m > threshold={threshold:.2f}m (median={med:.2f}m)"
            )
        else:
            kept.append(e)

    if not kept:
        return {
            'avg_dx': 0.0, 'avg_dy': 0.0,
            'n_used': 0, 'n_filtered_outliers': n_outliers,
            'shift_m': 0.0, 'total_weight': 0.0,
        }

    total_w = SATELLITE_DAMPING_WEIGHT
    sum_dx = 0.0
    sum_dy = 0.0
    for e in kept:
        w = e['overlap_m2'] * e['inlier_ratio']
        total_w += w
        sum_dx += w * e['dx_m']
        sum_dy += w * e['dy_m']

    avg_dx = sum_dx / total_w
    avg_dy = sum_dy / total_w
    shift_m = (avg_dx ** 2 + avg_dy ** 2) ** 0.5

    return {
        'avg_dx': avg_dx, 'avg_dy': avg_dy,
        'n_used': len(kept), 'n_filtered_outliers': n_outliers,
        'shift_m': shift_m, 'total_weight': total_w,
    }


def apply_consensus_alignment_skystore(mission_id: str):
    """Phase 1 pose-graph consensus re-alignment for a published mission.

    See PK/opensky-system.md § Pose Graph Architecture. Flow:
    1. Measurement: runs multi-neighbor ORB script — emits EDGE lines only.
    2. Persist edges to DB (OpenSkyPoseEdge.ORB_PAIR).
    3. Consensus: apply 3×median outlier filter + satellite-anchor damping to
       compute weighted-average shift.
    4. If |shift| ≥ MIN_CONSENSUS_SHIFT_M: apply shift to saved ortho, retile.

    Returns True if the shift was applied, False otherwise.
    """
    if _is_superseded(mission_id):
        return False
    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission_id}.tif"
    r_tmp = f"{SKYSTORE_FAST_PROCESSING}/_consensus_{mission_id}"
    r_aligned = f"{r_tmp}/aligned.tif"

    try:
        _skystore_ssh(f"mkdir -p {r_tmp}")

        # Steps 1-2: Measure ORB shifts vs all overlapping neighbors + persist
        edges = measure_orb_edges_skystore(mission_id)

        # Step 3: Robust consensus (median outlier filter + satellite damping)
        cs = compute_consensus_shift(mission_id, edges)
        logger.info(
            f"Consensus {mission_id}: edges_measured={len(edges)} used={cs['n_used']} "
            f"outliers_filtered={cs['n_filtered_outliers']} "
            f"shift=({cs['avg_dx']:+.2f},{cs['avg_dy']:+.2f})m |s|={cs['shift_m']:.2f}m"
        )

        if cs['shift_m'] < MIN_CONSENSUS_SHIFT_M:
            logger.info(f"Consensus {mission_id}: stable (shift below {MIN_CONSENSUS_SHIFT_M}m threshold)")
            return False

        if cs['shift_m'] > MAX_CONSENSUS_SHIFT_M:
            logger.warning(
                f"Consensus {mission_id}: shift {cs['shift_m']:.2f}m exceeds "
                f"MAX_CONSENSUS_SHIFT_M={MAX_CONSENSUS_SHIFT_M} — NOT applying (safety cap)"
            )
            return False

        # Step 4: Apply shift to saved (unclipped) ortho, then reclip+retile+publish
        apply_script = _build_apply_shift_script(r_ortho, r_aligned, cs['avg_dx'], cs['avg_dy'])
        _skystore_ssh(f"python3 -c {shlex.quote(apply_script)}", timeout=300)
        _skystore_ssh(f"cp {r_aligned} {r_ortho}")
        # Physical georef change — edges measured before this (including the
        # ones written above in Step 2) no longer describe the on-disk frame.
        _mark_georef_changed(mission_id)

        tiles_count = _reclip_retile_publish(mission_id, r_ortho, r_tmp)
        logger.info(f"Consensus {mission_id}: applied + retiled, {tiles_count} tiles")
        return True

    finally:
        try:
            _skystore_ssh(f"rm -rf {r_tmp}")
        except Exception:
            pass
