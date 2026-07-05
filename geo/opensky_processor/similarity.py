"""
Phase 2 — similarity bundle adjustment (delta space): the two-stage solver,
similarity composition bookkeeping, the lossless geotransform warp script, and
the apply+retile path. See PK/opensky-system.md § Phase 2 for the
frame-freshness invariant and why the solve is two-stage, not joint.
"""

import logging
import math
import shlex

from .common import _is_superseded
from .constants import (
    OUTLIER_FLOOR_M, OUTLIER_MEDIAN_MULTIPLE, SATELLITE_DAMPING_WEIGHT,
    SIM_APPLY_ROT_DEG, SIM_APPLY_SCALE, SIM_APPLY_TRANS_M, SIM_GAUGE_PRIOR,
    SIM_ROT_OUTLIER_FLOOR_DEG, SIM_SCALE_OUTLIER_FLOOR, SIM_TRANS_PRIOR,
    SKYSTORE_FAST_PROCESSING, SKYSTORE_OPENSKY,
)
from .pose_graph import _mark_georef_changed
from .remote import _skystore_ssh
from .tiles import _reclip_retile_publish

logger = logging.getLogger(__name__)


def solve_similarity_ba(centroids: dict, bounds: dict, orb_edges: list, anchored_ids: set,
                        anchor_weight: float = None) -> dict:
    """Global 2D similarity bundle adjustment over a mission cluster.

    Each mission i gets a correction: scale e^{u_i}, rotation ω_i, centroid
    translation (tx_i,ty_i), applied about its EPSG:3857 centroid c_i.

    Solved in two stages (DELIBERATELY two-stage, not joint — see below):
      Stage 1: two independent weighted-Laplacian scalar solves for u_i (ln s)
               and ω_i (rad) from the DIRECT relative measurements only
               (u_i−u_j=ln s_ij; ω_i−ω_j=θ_ij) + a weak identity prior (gauge).
      Stage 2: translation T_i from (T_i−T_j) = r_ij − lever_i + lever_j, where
               lever_i = u_i·d_i + ω_i·(J·d_i), d_i = x_ref − c_i, x_ref = the
               point where r_ij was measured (M's pixel-(0,0) = window
               west/north corner). Satellite anchors pin T_i→0 ("stay here").

    WHY NOT a joint 4N solve: in a joint system the anchored translations
    observe the cluster's common scale/rotation through the lever terms (the
    anchor baseline). Satellite anchoring is 1-2m-noisy while its solver weight
    (2e5, Phase-1 damping semantics) vastly overstates its precision — so a
    joint solve FABRICATES common-mode scale from anchor noise: ~1.5m of
    inter-anchor residual on a ~300m baseline reads as ~0.5% cluster-wide
    shrink. Observed live 2026-06-11: direct scale measurements said identity
    (median +106ppm) while the joint solution proposed −5000ppm common-mode and
    1-4m moves on a visually settled cluster. Two-stage keeps u/ω sourced from
    the precise direct similarity measurements only; the cost is a small gauge
    tension (~mean(u)·baseline, ≈10cm at production magnitudes) when ≥2 anchors
    exist, since stage 1's identity prior picks the gauge instead of the
    anchors. Guarded by tests_opensky_similarity (anchor-noise robustness).

    Args:
      centroids: {mid: (cx, cy)} EPSG:3857 ortho centroids.
      bounds:    {mid: (left, bottom, right, top)} EPSG:3857.
      orb_edges: [{a, b, ln_s, theta_rad, dx, dy, w, xref?}] — a,b are mids;
                 corrections to apply to a to align onto b (same convention as
                 dx_m/dy_m). Optional xref=(x,y) is the exact point where the
                 translation was measured (window west/north corner, stored as
                 ref_x/y_3857); without it the nominal bbox-intersection corner
                 is used (adds ~0.2-0.5m lever error when extents differ).
      anchored_ids: mids that have a SATELLITE_ANCHOR (translation pinned).
    Returns {mid: {'ln_scale','rotation_deg','tx','ty','translation_only'(bool)}}.

    The solution is a DELTA from the missions' CURRENT on-disk georefs: edges
    must be measured against the current orthos (see edge freshness in
    realign_opensky_similarity), and anchors mean "don't move from here".
    """
    import numpy as np
    import statistics
    from scipy.sparse import csr_matrix
    from scipy.sparse.linalg import lsmr

    if anchor_weight is None:
        anchor_weight = SATELLITE_DAMPING_WEIGHT

    mids = sorted(centroids.keys())
    idx = {m: k for k, m in enumerate(mids)}
    N = len(mids)
    if N == 0:
        return {}

    # Only edges between missions we're solving.
    edges = [e for e in orb_edges if e['a'] in idx and e['b'] in idx]

    # Per-component robust outlier filter (median-multiple with a floor).
    # KNOWN LIMITATION: a mission genuinely sitting several metres off its
    # neighbours produces edges that LOOK like outliers and get rejected here,
    # leaving its (worst-in-cluster) seam unfixed. Reciprocal mirroring
    # (|r_ab+r_ba| ≈ 0 for real misalignment, metres for junk) distinguishes
    # them, but a trust-bypass must exempt ONLY the translation component —
    # prototyped 2026-06-11, it let the low-confidence SCALE noise of trusted
    # edges (±1%) through to stage 1 and overshot sparsely-connected missions
    # (11m move from one low-conf pair). Needs per-component trust before
    # enabling; see PK § Phase 2.
    def thr(vals, floor):
        if not vals:
            return float('inf')
        m = statistics.median([abs(v) for v in vals])
        return max(OUTLIER_MEDIAN_MULTIPLE * m, floor)
    th_s = thr([e['ln_s'] for e in edges], SIM_SCALE_OUTLIER_FLOOR)
    th_r = thr([e['theta_rad'] for e in edges], np.radians(SIM_ROT_OUTLIER_FLOOR_DEG))
    th_t = thr([(e['dx']**2 + e['dy']**2) ** 0.5 for e in edges], OUTLIER_FLOOR_M)
    edges = [e for e in edges
             if abs(e['ln_s']) <= th_s and abs(e['theta_rad']) <= th_r
             and (e['dx']**2 + e['dy']**2) ** 0.5 <= th_t]

    has_anchor = bool(anchored_ids & set(mids))
    lsmr_opts = dict(atol=1e-12, btol=1e-12, conlim=1e10, maxiter=max(1000, 50 * N))

    def solve_scalar(rel_key):
        """Weighted Laplacian: x_i - x_j = rel + weak identity prior → x≈0 gauge."""
        rows, cols, dat, rhs = [], [], [], []
        r = 0
        for e in edges:
            w = e['w'] ** 0.5
            rows += [r, r]; cols += [idx[e['a']], idx[e['b']]]; dat += [w, -w]
            rhs.append(w * e[rel_key]); r += 1
        for k in range(N):
            rows.append(r); cols.append(k); dat.append(SIM_GAUGE_PRIOR); rhs.append(0.0); r += 1
        A = csr_matrix((dat, (rows, cols)), shape=(r, N))
        return lsmr(A, np.array(rhs), **lsmr_opts)[0]

    # Stage 1: scale & rotation from direct relative measurements only (never
    # from translations/anchors — see docstring). If no usable edges, identity.
    if edges:
        u = solve_scalar('ln_s')
        om = solve_scalar('theta_rad')
    else:
        u = np.zeros(N); om = np.zeros(N)

    # Stage 2: translation with stage-1 lever arms folded into the rhs.
    rows, cols, dat, rhs = [], [], [], []
    r = 0
    for e in edges:
        i, j = idx[e['a']], idx[e['b']]
        w = e['w'] ** 0.5
        if e.get('xref'):
            xref = e['xref']   # exact measured window corner (ref_x/y_3857)
        else:
            bi, bj = bounds[e['a']], bounds[e['b']]
            xref = (max(bi[0], bj[0]), min(bi[3], bj[3]))   # nominal fallback = M pixel(0,0)
        ci, cj = centroids[e['a']], centroids[e['b']]
        dix, diy = xref[0] - ci[0], xref[1] - ci[1]
        djx, djy = xref[0] - cj[0], xref[1] - cj[1]
        # lever = u·d + ω·(J·d), J·d = (-dy, dx)
        lev_i = (u[i] * dix + om[i] * (-diy), u[i] * diy + om[i] * (dix))
        lev_j = (u[j] * djx + om[j] * (-djy), u[j] * djy + om[j] * (djx))
        for c, dval in enumerate((e['dx'], e['dy'])):
            rows += [r, r]; cols += [2*i + c, 2*j + c]; dat += [w, -w]
            rhs.append(w * (dval - (lev_i[c] - lev_j[c]))); r += 1
    aw = anchor_weight ** 0.5
    for m in (anchored_ids & set(mids)):
        i = idx[m]
        rows.append(r); cols.append(2*i); dat.append(aw); rhs.append(0.0); r += 1
        rows.append(r); cols.append(2*i + 1); dat.append(aw); rhs.append(0.0); r += 1
    for k in range(2 * N):   # tiny prior pins unanchored components numerically
        rows.append(r); cols.append(k); dat.append(SIM_TRANS_PRIOR); rhs.append(0.0); r += 1
    A = csr_matrix((dat, (rows, cols)), shape=(r, 2 * N))
    t = lsmr(A, np.array(rhs), **lsmr_opts)[0]

    return {
        m: {
            'ln_scale': float(u[idx[m]]),
            'rotation_deg': float(np.degrees(om[idx[m]])),
            'tx': float(t[2*idx[m]]),
            'ty': float(t[2*idx[m] + 1]),
            'translation_only': not has_anchor,
        }
        for m in mids
    }


def _compose_similarity_about_centroid(old: tuple, delta: tuple) -> tuple:
    """Compose two similarity corrections taken about the SAME centroid:
    apply `old` first, then `delta`. Each is (ln_scale, rotation_deg, tx, ty).

    C(p) = s0·R0·(p−c) + c + t0;  D(C(p)) = s0·sd·Rd·R0·(p−c) + c + (sd·Rd·t0 + td)
    → scale/rotation add in log/angle space, old translation is carried through
    delta's scale+rotation. Used only for the cumulative corr_* bookkeeping.
    """
    ln_s = old[0] + delta[0]
    rot = old[1] + delta[1]
    s_d = math.exp(delta[0])
    th = math.radians(delta[1])
    cos_t, sin_t = math.cos(th), math.sin(th)
    tx = s_d * (cos_t * old[2] - sin_t * old[3]) + delta[2]
    ty = s_d * (sin_t * old[2] + cos_t * old[3]) + delta[3]
    return (ln_s, rot, tx, ty)


def _build_similarity_warp_script(r_src, r_dst, cx, cy, ln_scale, rot_deg, tx, ty):
    """Compose a 2D similarity (scale e^lnS, rotation rot_deg, translation t),
    taken about the EPSG:3857 centroid (cx,cy), into the ortho's geotransform.

    p' = sR(p − c) + c + t = sR·p + (c + t − sR·c). Edits only the geotransform
    (lossless — no pixel resampling); the rotated grid is de-rotated later by the
    Z17 reclip gdalwarp. rasterio `W * src.transform` composes pixel→map then map→map.
    """
    return f'''
import math, rasterio
from rasterio.transform import Affine
s = math.exp({ln_scale}); th = math.radians({rot_deg})
cosT = s * math.cos(th); sinT = s * math.sin(th)
cx, cy, tx, ty = {cx}, {cy}, {tx}, {ty}
ox = tx + cx - (cosT * cx - sinT * cy)
oy = ty + cy - (sinT * cx + cosT * cy)
W = Affine(cosT, -sinT, ox, sinT, cosT, oy)
with rasterio.open("{r_src}") as src:
    profile = src.profile.copy()
    profile.update(transform=(W * src.transform), BIGTIFF="IF_SAFER")
    with rasterio.open("{r_dst}", "w", **profile) as dst:
        for i in range(1, src.count + 1):
            dst.write(src.read(i), i)
print("WARP_OK")
'''


def apply_similarity_correction_skystore(mission_id: str, cx: float, cy: float,
                                         d_lns: float, d_rot: float,
                                         d_tx: float, d_ty: float) -> bool:
    """Apply a Phase-2 similarity DELTA (about centroid cx,cy in EPSG:3857) to
    a mission's saved ortho, then reclip+retile+publish.

    The arguments are the solver's output = the correction to the mission's
    CURRENT on-disk georef (the solve consumed only edges measured against it —
    see edge freshness in realign_opensky_similarity). corr_* accumulates the
    composition for bookkeeping; nothing re-derives state from it. Returns True
    if applied (above threshold).
    """
    if _is_superseded(mission_id):
        return False
    from geo.models import OpenSkyMission
    m = OpenSkyMission.objects.get(id=mission_id)

    if ((d_tx**2 + d_ty**2) ** 0.5 < SIM_APPLY_TRANS_M
            and abs(d_lns) < SIM_APPLY_SCALE and abs(d_rot) < SIM_APPLY_ROT_DEG):
        return False  # below apply threshold — leave tiles untouched

    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission_id}.tif"
    r_tmp = f"{SKYSTORE_FAST_PROCESSING}/_sim_{mission_id}"
    r_warped = f"{r_tmp}/sim_warped.tif"
    try:
        _skystore_ssh(f"mkdir -p {r_tmp}")
        warp_script = _build_similarity_warp_script(
            r_ortho, r_warped, cx, cy, d_lns, d_rot, d_tx, d_ty)
        _skystore_ssh(f"python3 -c {shlex.quote(warp_script)}", timeout=600)
        _skystore_ssh(f"cp {r_warped} {r_ortho}")
        # The on-disk frame just changed — every existing edge touching this
        # mission is stale from this point on.
        _mark_georef_changed(mission_id)

        tiles_count = _reclip_retile_publish(mission_id, r_ortho, r_tmp)

        (m.corr_ln_scale, m.corr_rotation_deg, m.corr_dx_m, m.corr_dy_m) = (
            _compose_similarity_about_centroid(
                (m.corr_ln_scale, m.corr_rotation_deg, m.corr_dx_m, m.corr_dy_m),
                (d_lns, d_rot, d_tx, d_ty)))
        m.save(update_fields=['corr_ln_scale', 'corr_rotation_deg', 'corr_dx_m', 'corr_dy_m'])
        logger.info(
            f"Similarity {mission_id[:8]}: applied Δ(lnS={d_lns:+.4f}, rot={d_rot:+.3f}°, "
            f"t={(d_tx**2 + d_ty**2) ** 0.5:.2f}m), {tiles_count} tiles"
        )
        return True
    finally:
        try:
            _skystore_ssh(f"rm -rf {r_tmp}")
        except Exception:
            pass
