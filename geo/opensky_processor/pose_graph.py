"""
Pose graph observations (PK/opensky-system.md § Pose Graph Architecture):
multi-neighbor ORB measurement, EDGE/SKIP output parsing, OpenSkyPoseEdge
persistence, and the frame-freshness invariant (georef_changed_at vs
measured_at) that gates every Phase-2 solve.
"""

import logging
import shlex

from django.utils import timezone

from .constants import SKYSTORE_OPENSKY
from .remote import _skystore_ssh

logger = logging.getLogger(__name__)


def _build_multi_neighbor_alignment_script(mission_id, r_target, r_orthos, max_shift_m=None):
    """Build multi-neighbor ORB MEASUREMENT script for skystore.

    Discovers all reference orthos with ≥MIN_OVERLAP_RATIO of target area,
    measures ORB shift vs each, emits EDGE lines. Does NOT apply any shift —
    the consensus computation (with median outlier filter + satellite anchor
    damping) runs in Python on Hetzner, and shift application is a separate
    step (`_build_apply_shift_script`).

    Emits stdout lines for Python parsing:
    - EDGE:<neighbor_id>:<dx_m>:<dy_m>:<overlap_m2>:<inlier_ratio>  — per-pair measurement
    - SKIP:<neighbor_id>:<reason>                                   — neighbor rejected

    Constraints (critical — past bug shifted orthos by 1+ km):
    - Per-neighbor overlap ≥ MIN_OVERLAP_RATIO of target area
    - Both windows loaded at COMMON pixel grid of intersection (same geographic resolution)
    - Per-edge shift capped at MAX_EDGE_SHIFT_M (10 m). Legitimate inter-mission
      shifts after satellite alignment are <7 m; anything beyond is a spurious
      ORB match. Tighter than before (was 30 m) — past incident with 13 m and
      18 m outliers poisoning consensus demonstrated 30 m was too permissive.
      Callers measuring a KNOWN-large offset (e.g. realigning a mis-anchored
      consolidation onto its members) pass an explicit `max_shift_m`.
    - Overlap ratio is taken vs the SMALLER of the two ortho areas: a 4-cell
      consolidation vs a single-cell neighbour overlaps <5% of the big side
      but ~20%+ of the small side — the old target-only ratio silently skipped
      ALL ring neighbours of a merged ortho (2026-06-12 mis-anchor incident).
    """
    MAX_EDGE_SHIFT_M = float(max_shift_m) if max_shift_m else 10.0
    MIN_OVERLAP_RATIO = 0.05
    MIN_WINDOW_PX = 64
    MAX_WINDOW_SIDE_PX = 2000
    return f'''
import os, sys, glob, re
import cv2
import numpy as np
import rasterio
from rasterio.windows import from_bounds

target = "{r_target}"
orthos_dir = "{r_orthos}"
mission_id = "{mission_id}"
MAX_EDGE_SHIFT_M = {MAX_EDGE_SHIFT_M}
MIN_OVERLAP_RATIO = {MIN_OVERLAP_RATIO}
MIN_WINDOW_PX = {MIN_WINDOW_PX}
MAX_WINDOW_SIDE_PX = {MAX_WINDOW_SIDE_PX}

ULID_RE = re.compile(r'(0[0-9A-HJKMNP-TV-Z]{{25}})', re.IGNORECASE)

def neighbor_id_from_path(p):
    m = ULID_RE.search(os.path.basename(p))
    return m.group(1).upper() if m else os.path.splitext(os.path.basename(p))[0]

with rasterio.open(target) as src:
    tgt_bounds = src.bounds
    tgt_area = (tgt_bounds.right - tgt_bounds.left) * (tgt_bounds.top - tgt_bounds.bottom)

refs = [r for r in glob.glob(os.path.join(orthos_dir, "*.tif")) if mission_id not in os.path.basename(r)]
if not refs:
    sys.exit(0)

def bbox_overlap(b1, b2):
    L = max(b1.left, b2.left); R = min(b1.right, b2.right)
    B = max(b1.bottom, b2.bottom); T = min(b1.top, b2.top)
    if L >= R or B >= T:
        return 0.0, None
    return (R - L) * (T - B), (L, B, R, T)

def load_isect(path, isect_L, isect_B, isect_R, isect_T, win_w, win_h):
    with rasterio.open(path) as src:
        win = from_bounds(isect_L, isect_B, isect_R, isect_T, src.transform)
        data = src.read(1, window=win, out_shape=(win_h, win_w),
                        resampling=rasterio.enums.Resampling.bilinear)
        if data.dtype != np.uint8:
            if data.max() > 0:
                data = (data / data.max() * 255).astype(np.uint8)
            else:
                data = data.astype(np.uint8)
    return data

for rp in refs:
    nid = neighbor_id_from_path(rp)
    try:
        with rasterio.open(rp) as rs:
            ref_bounds = rs.bounds
            overlap_area, isect = bbox_overlap(tgt_bounds, ref_bounds)
    except Exception as e:
        print(f"SKIP:{{nid}}:cannot_open:{{e}}")
        continue
    if overlap_area <= 0:
        continue
    ref_area = (ref_bounds.right - ref_bounds.left) * (ref_bounds.top - ref_bounds.bottom)
    overlap_ratio = overlap_area / max(min(tgt_area, ref_area), 1.0)
    if overlap_ratio < MIN_OVERLAP_RATIO:
        print(f"SKIP:{{nid}}:overlap_too_small_{{overlap_ratio*100:.2f}}pct")
        continue

    isect_L, isect_B, isect_R, isect_T = isect
    isect_w_m = isect_R - isect_L
    isect_h_m = isect_T - isect_B
    res_m_per_px = max(isect_w_m, isect_h_m) / MAX_WINDOW_SIDE_PX
    win_w = max(1, int(round(isect_w_m / res_m_per_px)))
    win_h = max(1, int(round(isect_h_m / res_m_per_px)))
    if win_w < MIN_WINDOW_PX or win_h < MIN_WINDOW_PX:
        print(f"SKIP:{{nid}}:window_too_small_{{win_w}}x{{win_h}}")
        continue

    try:
        tgt_gray = load_isect(target, isect_L, isect_B, isect_R, isect_T, win_w, win_h)
        ref_gray = load_isect(rp, isect_L, isect_B, isect_R, isect_T, win_w, win_h)
    except Exception as e:
        print(f"SKIP:{{nid}}:load_failed:{{e}}")
        continue

    orb = cv2.ORB_create(5000)
    kp_ref, des_ref = orb.detectAndCompute(ref_gray, None)
    kp_tgt, des_tgt = orb.detectAndCompute(tgt_gray, None)
    if des_ref is None or des_tgt is None or len(kp_ref) < 10 or len(kp_tgt) < 10:
        print(f"SKIP:{{nid}}:insufficient_features")
        continue

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = sorted(bf.match(des_ref, des_tgt), key=lambda m: m.distance)[:50]
    if len(matches) < 6:
        print(f"SKIP:{{nid}}:insufficient_matches_{{len(matches)}}")
        continue

    src_pts = np.float32([kp_ref[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_tgt[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    M, inliers = cv2.estimateAffinePartial2D(dst_pts, src_pts, method=cv2.RANSAC, ransacReprojThreshold=5.0)
    if M is None or inliers is None or int(np.sum(inliers)) < 4:
        print(f"SKIP:{{nid}}:ransac_failed")
        continue

    inlier_count = int(np.sum(inliers))
    inlier_ratio = inlier_count / float(len(matches))
    pixel_dx = float(M[0, 2])
    pixel_dy = float(M[1, 2])
    geo_dx = pixel_dx * res_m_per_px
    geo_dy = -pixel_dy * res_m_per_px
    shift_m = (geo_dx ** 2 + geo_dy ** 2) ** 0.5
    if shift_m > MAX_EDGE_SHIFT_M:
        print(f"SKIP:{{nid}}:shift_too_large_{{shift_m:.2f}}m")
        continue

    # Similarity components of M=[[a,-b,tx],[b,a,ty]] mapping target_a -> ref_b.
    # rel_scale = size(b)/size(a). rel_rot_deg uses +atan2(b,a): M's screen-frame
    # rotation IS the rotation-to-apply-to-a-to-align-onto-b, matching the
    # translation convention (geo_dx/dy are also corrections-to-apply-to-a, not
    # offsets — verified by synthetic test: dE=+2 -> geo_dx=-2, rot=+1 -> rel_rot=-1).
    a = float(M[0, 0]); bb = float(M[1, 0])
    rel_scale = (a * a + bb * bb) ** 0.5
    rel_rot_deg = np.degrees(np.arctan2(bb, a))
    # Hard-gate spurious similarity: legitimate inter-flight scale <2%, rot <few deg.
    if abs(rel_scale - 1.0) > 0.05 or abs(rel_rot_deg) > 5.0:
        print(f"SKIP:{{nid}}:similarity_out_of_range_s{{rel_scale:.4f}}_r{{rel_rot_deg:.2f}}")
        continue

    # isect_L/isect_T = (west, north) corner of the measured window = the world
    # point where the translation (M's pixel-(0,0) component) is referenced.
    # The Phase-2 lever-arm needs this exact point (stored as ref_x/y_3857).
    print(f"EDGE:{{nid}}:{{geo_dx:.4f}}:{{geo_dy:.4f}}:{{overlap_area:.1f}}:{{inlier_ratio:.4f}}:{{rel_scale:.6f}}:{{rel_rot_deg:.4f}}:{{isect_L:.2f}}:{{isect_T:.2f}}")
'''


def _parse_alignment_output(mission_id: str, stdout: str):
    """Parse multi-neighbor measurement script stdout.

    Returns list of edge dicts: {neighbor_id, dx_m, dy_m, overlap_m2, inlier_ratio}.
    SKIP lines are logged at debug level.
    """
    edges = []
    for line in (stdout or '').strip().splitlines():
        line = line.strip()
        if line.startswith('EDGE:'):
            parts = line.split(':')
            if len(parts) >= 6:
                try:
                    e = {
                        'neighbor_id': parts[1],
                        'dx_m': float(parts[2]),
                        'dy_m': float(parts[3]),
                        'overlap_m2': float(parts[4]),
                        'inlier_ratio': float(parts[5]),
                        # Legacy 6-field lines have no similarity → identity.
                        'rel_scale': float(parts[6]) if len(parts) >= 7 else 1.0,
                        'rel_rotation_deg': float(parts[7]) if len(parts) >= 8 else 0.0,
                        # Translation reference point (window west/north corner);
                        # None on legacy 8-field lines → solver falls back to
                        # the nominal cell-intersection corner.
                        'ref_x_3857': float(parts[8]) if len(parts) >= 10 else None,
                        'ref_y_3857': float(parts[9]) if len(parts) >= 10 else None,
                    }
                    edges.append(e)
                except ValueError:
                    logger.warning(f"Consensus {mission_id}: bad EDGE line: {line}")
        elif line.startswith('SKIP:'):
            logger.debug(f"Consensus {mission_id}: {line}")
    return edges


def _write_orb_edges(mission_id: str, edges: list):
    """Upsert ORB_PAIR pose edges into DB."""
    from geo.models import OpenSkyMission, OpenSkyPoseEdge
    if not edges:
        return
    neighbor_ids = {e['neighbor_id'] for e in edges}
    existing_neighbors = set(
        OpenSkyMission.objects.filter(id__in=neighbor_ids).values_list('id', flat=True)
    )
    for e in edges:
        if e['neighbor_id'] not in existing_neighbors:
            logger.warning(f"Consensus {mission_id}: neighbor {e['neighbor_id']} not in DB, skipping edge")
            continue
        OpenSkyPoseEdge.objects.update_or_create(
            mission_a_id=mission_id,
            mission_b_id=e['neighbor_id'],
            edge_type=OpenSkyPoseEdge.EdgeType.ORB_PAIR,
            defaults={
                'dx_m': e['dx_m'],
                'dy_m': e['dy_m'],
                'weight': e['overlap_m2'] * e['inlier_ratio'],
                'confidence': e['inlier_ratio'],
                'overlap_area_m2': e['overlap_m2'],
                'rel_scale': e.get('rel_scale', 1.0),
                'rel_rotation_deg': e.get('rel_rotation_deg', 0.0),
                'ref_x_3857': e.get('ref_x_3857'),
                'ref_y_3857': e.get('ref_y_3857'),
            },
        )


def _write_satellite_anchor(mission_id: str, dx_m: float, dy_m: float, cc: float):
    """Upsert SATELLITE_ANCHOR pose edge into DB.

    Satellite anchor represents the absolute-frame shift observed by ECC
    against ESRI World Imagery. mission_b is NULL (absolute reference).
    """
    from geo.models import OpenSkyPoseEdge
    OpenSkyPoseEdge.objects.update_or_create(
        mission_a_id=mission_id,
        mission_b=None,
        edge_type=OpenSkyPoseEdge.EdgeType.SATELLITE_ANCHOR,
        defaults={
            'dx_m': dx_m,
            'dy_m': dy_m,
            'weight': 1.0,
            'confidence': cc,
            'overlap_area_m2': 0.0,
            # Anchors observe translation only — similarity is identity.
            'rel_scale': 1.0,
            'rel_rotation_deg': 0.0,
        },
    )


def measure_orb_edges_skystore(mission_id: str) -> list:
    """Measure ORB pose edges vs all overlapping neighbors and persist to DB.

    MEASURE-ONLY: no consensus math, no warp, no retile — safe on any published
    mission incl. right before a Phase-2 solve (this is how edges are refreshed
    after physical georef changes; see `measure_opensky_edges` command).
    Returns the parsed edge list.
    """
    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{mission_id}.tif"
    r_orthos = f"{SKYSTORE_OPENSKY}/orthos"
    measurement_script = _build_multi_neighbor_alignment_script(
        mission_id, r_ortho, r_orthos,
    )
    result = _skystore_ssh(f"python3 -c {shlex.quote(measurement_script)}", timeout=3600)
    edges = _parse_alignment_output(mission_id, result.stdout or '')
    _write_orb_edges(mission_id, edges)
    return edges


def _mark_georef_changed(mission_id: str):
    """Record that the saved ortho's georeference just changed physically.

    Every pose edge measured BEFORE this moment describes a frame that no
    longer exists on disk — the Phase-2 solver filters them out via
    `_edge_is_fresh`. Call after EVERY physical georef mutation of
    /skystore/opensky/orthos/{id}.tif (publish, satellite/consensus shift,
    similarity warp).
    """
    from geo.models import OpenSkyMission
    OpenSkyMission.objects.filter(id=mission_id).update(georef_changed_at=timezone.now())


def _edge_is_fresh(measured_at, *georef_changed_ats) -> bool:
    """True if the edge was measured AFTER the last physical georef change of
    BOTH endpoint orthos (None = ortho never changed since field introduction)."""
    latest = max((g for g in georef_changed_ats if g is not None), default=None)
    return latest is None or measured_at > latest
