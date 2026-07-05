"""
Split-merge consolidation (see PK/opensky-system.md § Consolidation).

A cluster of overlapping missions disagrees at its Z17 seams by an AFFINE
residual (per-flight GPS scale + independent DSMs) that the per-mission 2D
consensus can't remove. Joint ODM reconstruction of ALL members' photos
(--split / --split-overlap) yields ONE seamless ortho. The consolidation is
itself an OpenSkyMission row (is_consolidation=True) tiled at max layer_order;
its members keep their own tiles/orthos and point back via superseded_by, so
the consolidation can be deleted to roll back.
"""

import logging
import math
import shlex

from django.contrib.gis.geos import Polygon
from django.utils import timezone

from .common import _publish_mission_update, reverse_geocode_place
from .consensus import _build_apply_shift_script, compute_consensus_shift
from .constants import (
    MAX_CONSENSUS_SHIFT_M, MAX_CONSOLIDATION_PHOTOS, MIN_CONSENSUS_SHIFT_M,
    MIN_FAST_PROCESSING_FREE_GB, SATELLITE_CACHE_DIR, SIM_APPLY_ROT_DEG,
    SIM_APPLY_SCALE, SKYSTORE_FAST_PROCESSING, SKYSTORE_OPENSKY,
    SKYSTORE_TILES, TILE_MAX_ZOOM, TILE_MIN_ZOOM, WEBP_QUALITY,
)
from .odm import run_odm_splitmerge_skystore
from .pose_graph import (
    _build_multi_neighbor_alignment_script, _mark_georef_changed,
    _parse_alignment_output, _write_orb_edges, _write_satellite_anchor,
)
from .remote import _skystore_ssh
from .satellite import _build_satellite_alignment_script
from .similarity import _build_similarity_warp_script
from .tiles import (
    _build_tms_to_xyz_webp_script, _build_update_latest_script,
    _clear_self_owned_latest_tiles, _consolidation_union_bounds_3857,
    _record_tile_layers, _reclip_retile_publish,
    composite_partial_consolidation_tiles, rebuild_overview_latest,
    rebuild_tiles_after_deletion,
)

logger = logging.getLogger(__name__)


# A large ECC shift needs a strong correlation to be believable: the merged
# church ortho got a bogus +10.2/-10.7m "lock" at cc=0.177 (2026-06-12),
# compounding an ~18m raw-GPS bias into a 33m mis-anchor. Ordinary missions
# keep the script-level floor (0.15) — this gate applies where a big jump is
# claimed on weak evidence.
SAT_LARGE_SHIFT_M = 5.0
SAT_LARGE_SHIFT_MIN_CC = 0.35


def _measure_consolidation_vs_members(consolidation_id: str, member_ids: list,
                                      max_shift_m: float = 60.0) -> list:
    """ORB-measure the consolidation ortho against its members' saved orthos.

    Members render the SAME photos over the same cells, so this is same-content
    matching — the strongest possible reference for placing a merged ortho into
    the frame the rest of the map already agrees with. Returns edge dicts
    (corrections to apply to the CONSOLIDATION). Diagnostic refs dir is
    temporary; nothing is written to the pose graph (members are superseded).
    """
    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{consolidation_id}.tif"
    r_refs = f"{SKYSTORE_FAST_PROCESSING}/_memref_{consolidation_id}"
    _skystore_ssh(f"rm -rf {r_refs} && mkdir -p {r_refs}")
    for mid in member_ids:
        _skystore_ssh(f"ln -sfn {SKYSTORE_OPENSKY}/orthos/{mid}.tif {r_refs}/{mid}.tif")
    try:
        script = _build_multi_neighbor_alignment_script(
            consolidation_id, r_ortho, r_refs, max_shift_m=max_shift_m)
        res = _skystore_ssh(f"python3 -c {shlex.quote(script)}", timeout=3600)
        return _parse_alignment_output(consolidation_id, res.stdout or '')
    finally:
        _skystore_ssh(f"rm -rf {r_refs}")


def _fit_similarity_to_members(edges):
    """Least-squares 2D similarity (scale, rotation, translation about the EPSG:3857
    centroid of the member overlap windows) that best maps the merged consolidation
    ortho onto its members' frame. Input = same-content member edges from
    `_measure_consolidation_vs_members` (dx/dy at ref_x/y_3857). Returns
    (cx, cy, ln_scale, rot_deg, tx, ty) — the correction to apply to the
    consolidation — or None if there are <3 edges or the fit leaves the sane
    similarity envelope (|s-1|>5% or |θ|>5°, matching the Phase-2 ORB gate) so the
    caller falls back to a pure translation.

    Fit on the TRANSLATION field, NOT the per-edge `rel_scale`: members are precise
    same-content references (<1 m), so the spatial arrangement of their displacement
    vectors is the clean global-scale signal, whereas per-patch ORB rel_scale is
    lean/parallax-contaminated (church June 4-cell: rel_scale mean +1.4% overcorrects
    to 3.1 m spread; the translation-field scale +0.86% lands 1.98 m — under the gate).
    This is the OPPOSITE of the multi-mission Phase-2 BA (noisy satellite anchors →
    scale must come from direct rel_scale, see § Phase 2) because here the reference
    is precise. A pure translation cannot remove a per-flight GPS scale drift, which
    is why translation-only members anchoring left the joint ortho 3 m bent.
    """
    if len(edges) < 3:
        return None
    import numpy as np
    P = np.array([[e['ref_x_3857'], e['ref_y_3857']] for e in edges], float)
    D = np.array([[e['dx_m'], e['dy_m']] for e in edges], float)
    w = np.array([max(e['overlap_m2'] * e['inlier_ratio'], 1e-6) for e in edges], float)
    cx, cy = P.mean(axis=0)
    Pc = P - (cx, cy)
    Tc = Pc + D
    # weighted similarity lstsq: [x';y'] = [[x,-y,1,0],[y,x,0,1]] · [a,b,tx,ty]
    rows, rhs, sw = [], [], []
    for (x, y), (tx_, ty_), wi in zip(Pc, Tc, w):
        s = wi ** 0.5
        rows += [[x, -y, 1.0, 0.0], [y, x, 0.0, 1.0]]
        rhs += [tx_, ty_]
        sw += [s, s]
    sw = np.array(sw)
    a, b, tx, ty = np.linalg.lstsq(np.array(rows) * sw[:, None], np.array(rhs) * sw, rcond=None)[0]
    ln_scale = math.log(math.hypot(a, b))
    rot_deg = math.degrees(math.atan2(b, a))
    if abs(ln_scale) > 0.05 or abs(rot_deg) > 5.0:
        logger.warning(
            f"Members similarity fit out of envelope (scale {(math.exp(ln_scale)-1)*100:+.1f}%, "
            f"rot {rot_deg:+.2f}°) — falling back to translation")
        return None
    return float(cx), float(cy), float(ln_scale), float(rot_deg), float(tx), float(ty)


def realign_consolidation_to_members(consolidation_id: str, dry_run: bool = False) -> bool:
    """Shift a published consolidation onto its members' frame, then retile.

    Recovery/maintenance path for a mis-anchored super-tile (see 2026-06-12:
    weak-cc satellite lock left the church consolidation 33m off; members ARE
    the ground truth the surrounding map was aligned to). Weighted average of
    member ORB edges, no satellite damping (members define the frame), sanity
    bounds instead of the 10m consensus cap. Returns True if applied.
    """
    from geo.models import OpenSkyMission
    con = OpenSkyMission.objects.filter(id=consolidation_id, is_consolidation=True).first()
    if not con:
        logger.error(f"{consolidation_id} is not a consolidation")
        return False
    member_ids = list(con.members.values_list('member_id', flat=True))
    if not member_ids:
        logger.error(f"Consolidation {consolidation_id}: no members")
        return False

    edges = _measure_consolidation_vs_members(consolidation_id, member_ids)
    if len(edges) < 2:
        logger.error(
            f"Consolidation {consolidation_id}: only {len(edges)} member edge(s) measured — "
            f"refusing to realign on a single observation")
        return False
    w_sum = sum(e['overlap_m2'] * e['inlier_ratio'] for e in edges)
    dx = sum(e['dx_m'] * e['overlap_m2'] * e['inlier_ratio'] for e in edges) / w_sum
    dy = sum(e['dy_m'] * e['overlap_m2'] * e['inlier_ratio'] for e in edges) / w_sum
    spread = max(((e['dx_m'] - dx) ** 2 + (e['dy_m'] - dy) ** 2) ** 0.5 for e in edges)
    shift = (dx ** 2 + dy ** 2) ** 0.5
    logger.info(
        f"Consolidation {consolidation_id[:8]} vs {len(edges)} members: "
        f"shift=({dx:+.2f},{dy:+.2f})m |s|={shift:.2f}m spread={spread:.2f}m")
    if spread > 3.0:
        logger.error(f"Member edges disagree by {spread:.2f}m (>3m) — refusing to realign")
        return False
    if shift < MIN_CONSENSUS_SHIFT_M:
        logger.info("Already aligned to members (below threshold)")
        return False
    if dry_run:
        logger.info("[DRY RUN] nothing applied")
        return False

    r_ortho = f"{SKYSTORE_OPENSKY}/orthos/{consolidation_id}.tif"
    r_tmp = f"{SKYSTORE_FAST_PROCESSING}/_conrealign_{consolidation_id}"
    r_shifted = f"{r_tmp}/shifted.tif"
    try:
        _skystore_ssh(f"mkdir -p {r_tmp}")
        apply_script = _build_apply_shift_script(r_ortho, r_shifted, dx, dy)
        _skystore_ssh(f"python3 -c {shlex.quote(apply_script)}", timeout=600)
        _skystore_ssh(f"cp {r_shifted} {r_ortho}")
        _mark_georef_changed(consolidation_id)
        tiles_count = _reclip_retile_publish(consolidation_id, r_ortho, r_tmp)
        logger.info(f"Consolidation {consolidation_id[:8]}: realigned to members + retiled, {tiles_count} tiles")
        return True
    finally:
        try:
            _skystore_ssh(f"rm -rf {r_tmp}")
        except Exception:
            pass


def _anchor_merged_ortho(consolidation_id: str, r_ortho: str, r_tmp: str, member_ids: list):
    """Anchor the raw-GPS merged ortho to the established map frame. Order:
    (1) ORB vs the MEMBERS' saved orthos (same content — the strongest and
    only season-proof reference; the members already sit in the frame the
    whole map agrees with); (2) satellite ECC as cross-check, applied only if
    small or strongly correlated; (3) ORB consensus vs NON-member neighbours
    (ring refinement). Mutates r_ortho in place.
    """
    # --- (1) Members anchor (primary): same-content ORB, TWO-STAGE.
    # (1a) COARSE weighted-mean translation positions the merged ortho into the
    #      member frame. The raw merged-GPS ortho is ~5 m off, so its ORB overlap
    #      windows mis-register and a similarity measured on it is unreliable (run-2
    #      raw fit gave +0.32%/-0.35° vs the +0.86%/+0.09° measured post-translation).
    # (1b) FINE 2D similarity, re-measured on the now-aligned ortho, removes the
    #      per-flight GPS scale drift (~0.9%) that a pure translation CANNOT — church
    #      June 4-cell: translation-only leaves 3.0 m member spread, +similarity
    #      1.9 m (under the 2.5 m gate). Fit on the precise member translation field,
    #      not the lean-contaminated per-patch rel_scale (see _fit_similarity_to_members).
    #      The lossless warp leaves a ROTATED geotransform; unlike the Phase-2 path it
    #      is not immediately reclipped, and the satellite/ring cross-checks that
    #      follow (gdal_translate -projwin) + the gate assume north-up — so de-rotate
    #      to north-up now (bakes the similarity into pixels; rotation <0.5° → near
    #      lossless). 2 edges → translation only (2D similarity underdetermined). ---
    # `members_anchored` makes the satellite + ring steps below LOG-ONLY cross-checks
    # once we have a members frame: same-content members ORB is the precise reference,
    # while satellite ECC (~1-2 m, weak cc) and the non-member ring PULL a good anchor
    # off — run-3: sat cc=0.16 + ring +1.5 m dragged a 0.07 m residual to 1.15 m and
    # failed the gate. See PK/opensky-system.md § Consolidation (anchor order).
    members_anchored = False
    edges = _measure_consolidation_vs_members(consolidation_id, member_ids)
    if len(edges) >= 2:
        members_anchored = True
        w_sum = sum(e['overlap_m2'] * e['inlier_ratio'] for e in edges)
        mdx = sum(e['dx_m'] * e['overlap_m2'] * e['inlier_ratio'] for e in edges) / w_sum
        mdy = sum(e['dy_m'] * e['overlap_m2'] * e['inlier_ratio'] for e in edges) / w_sum
        mshift = (mdx ** 2 + mdy ** 2) ** 0.5
        logger.info(
            f"Consolidation {consolidation_id[:8]}: members anchor (translation) "
            f"({mdx:+.2f},{mdy:+.2f})m |s|={mshift:.2f}m from {len(edges)} member edge(s)")
        if mshift >= MIN_CONSENSUS_SHIFT_M:
            r_mem = f"{r_tmp}/member_aligned.tif"
            _skystore_ssh(f"python3 -c {shlex.quote(_build_apply_shift_script(r_ortho, r_mem, mdx, mdy))}",
                          timeout=600)
            _skystore_ssh(f"cp {r_mem} {r_ortho}")
            logger.info(f"Consolidation {consolidation_id[:8]}: applied members anchor (translation)")
            # re-measure on the aligned ortho for a reliable similarity fit
            edges = _measure_consolidation_vs_members(consolidation_id, member_ids)
        sim = _fit_similarity_to_members(edges)
        if sim is not None:
            cx, cy, d_lns, d_rot, d_tx, d_ty = sim
            if (abs(d_lns) >= SIM_APPLY_SCALE or abs(d_rot) >= SIM_APPLY_ROT_DEG
                    or (d_tx ** 2 + d_ty ** 2) ** 0.5 >= MIN_CONSENSUS_SHIFT_M):
                logger.info(
                    f"Consolidation {consolidation_id[:8]}: members similarity refinement "
                    f"scale={(math.exp(d_lns) - 1) * 100:+.2f}% rot={d_rot:+.3f}° "
                    f"t=({d_tx:+.2f},{d_ty:+.2f})m from {len(edges)} member edge(s)")
                r_sim = f"{r_tmp}/member_sim.tif"
                _skystore_ssh(
                    f"python3 -c {shlex.quote(_build_similarity_warp_script(r_ortho, r_sim, cx, cy, d_lns, d_rot, d_tx, d_ty))}",
                    timeout=600)
                # de-rotate the warped grid back to north-up (the cross-checks below
                # and the reclip cannot consume a rotated raster reliably)
                r_sim_nu = f"{r_tmp}/member_sim_nu.tif"
                _skystore_ssh(
                    f"gdalwarp -r lanczos -co COMPRESS=LZW -co TILED=YES -co BIGTIFF=IF_SAFER "
                    f"-dstnodata 0 -overwrite {r_sim} {r_sim_nu}", timeout=1800)
                _skystore_ssh(f"cp {r_sim_nu} {r_ortho}")
                logger.info(f"Consolidation {consolidation_id[:8]}: applied members similarity refinement")
    else:
        logger.warning(
            f"Consolidation {consolidation_id[:8]}: members anchor unavailable "
            f"({len(edges)} edge(s)) — falling back to satellite/ring only")

    # --- (2) Satellite anchor (cross-check; gated against weak-cc big jumps) ---
    r_sat = f"{r_tmp}/sat_aligned.tif"
    sat_script = _build_satellite_alignment_script(r_ortho, r_sat, SATELLITE_CACHE_DIR)
    sat_res = _skystore_ssh(f"python3 -c {shlex.quote(sat_script)}", timeout=600)
    sat_dx = sat_dy = sat_cc = 0.0
    for line in (sat_res.stdout or '').strip().splitlines():
        if line.startswith('SAT_RESULT:'):
            try:
                p = line.split(':'); sat_dx, sat_dy, sat_cc = float(p[1]), float(p[2]), float(p[3])
            except (ValueError, IndexError):
                pass
    sat_shift = (sat_dx ** 2 + sat_dy ** 2) ** 0.5
    if "aligned" in _skystore_ssh(f"test -f {r_sat} && echo aligned || echo identity").stdout:
        if sat_shift > SAT_LARGE_SHIFT_M and sat_cc < SAT_LARGE_SHIFT_MIN_CC:
            logger.warning(
                f"Consolidation {consolidation_id[:8]}: satellite suggests "
                f"({sat_dx:+.2f},{sat_dy:+.2f})m at weak cc={sat_cc:.3f} — NOT applying "
                f"(large shift needs cc>={SAT_LARGE_SHIFT_MIN_CC}; 2026-06-12 bogus-lock incident)")
        elif members_anchored:
            logger.info(
                f"Consolidation {consolidation_id[:8]}: satellite cross-check "
                f"({sat_dx:+.2f},{sat_dy:+.2f}) cc={sat_cc:.3f} — log-only (members anchor authoritative)")
        else:
            _skystore_ssh(f"cp {r_sat} {r_ortho}")
            _write_satellite_anchor(consolidation_id, sat_dx, sat_dy, sat_cc)
            logger.info(f"Consolidation {consolidation_id[:8]}: satellite-anchored ({sat_dx:+.2f},{sat_dy:+.2f}) cc={sat_cc:.3f}")
    else:
        logger.info(f"Consolidation {consolidation_id[:8]}: satellite anchor — no correction")

    # --- ORB consensus vs NON-member neighbors only ---
    # Build a refs dir of orthos for missions that are NOT members and NOT this
    # consolidation, so the merged ortho aligns to the surrounding ring (keeps
    # the super-tile seamless against the rest of the map), never to a member.
    r_refs = f"{r_tmp}/refs"
    listing = _skystore_ssh(f"ls {SKYSTORE_OPENSKY}/orthos/ 2>/dev/null | grep '\\.tif$' || true")
    exclude = set(member_ids) | {consolidation_id}
    ref_ids = [
        fn[:-4] for fn in (listing.stdout or '').split()
        if fn.endswith('.tif') and fn[:-4] not in exclude
    ]
    if ref_ids:
        _skystore_ssh(f"rm -rf {r_refs} && mkdir -p {r_refs}")
        for rid in ref_ids:
            _skystore_ssh(f"ln -sfn {SKYSTORE_OPENSKY}/orthos/{rid}.tif {r_refs}/{rid}.tif")
        meas_script = _build_multi_neighbor_alignment_script(consolidation_id, r_ortho, r_refs)
        meas = _skystore_ssh(f"python3 -c {shlex.quote(meas_script)}", timeout=3600)
        edges = _parse_alignment_output(consolidation_id, meas.stdout or '')
        _write_orb_edges(consolidation_id, edges)
        cs = compute_consensus_shift(consolidation_id, edges)
        logger.info(
            f"Consolidation {consolidation_id[:8]}: ORB vs {len(ref_ids)} non-members "
            f"edges={len(edges)} used={cs['n_used']} shift=({cs['avg_dx']:+.2f},{cs['avg_dy']:+.2f})m |s|={cs['shift_m']:.2f}m"
        )
        if members_anchored:
            logger.info(
                f"Consolidation {consolidation_id[:8]}: ring cross-check "
                f"({cs['avg_dx']:+.2f},{cs['avg_dy']:+.2f})m |s|={cs['shift_m']:.2f}m — "
                f"log-only (members anchor authoritative)")
        elif MIN_CONSENSUS_SHIFT_M <= cs['shift_m'] <= MAX_CONSENSUS_SHIFT_M:
            r_shifted = f"{r_tmp}/orb_shifted.tif"
            apply_script = _build_apply_shift_script(r_ortho, r_shifted, cs['avg_dx'], cs['avg_dy'])
            _skystore_ssh(f"python3 -c {shlex.quote(apply_script)}", timeout=300)
            _skystore_ssh(f"cp {r_shifted} {r_ortho}")
            logger.info(f"Consolidation {consolidation_id[:8]}: applied ORB consensus shift")


def process_consolidation(consolidation_id: str, no_split: bool = False,
                          resume: bool = False, gps_accuracy: float = None) -> bool:
    """Build a seamless super-tile from a consolidation's member missions.

    Mirrors process_mission(): joint ODM split-merge → reproject → satellite +
    ORB anchor → union-clip → tile → override latest/ (clear members, plant
    consolidation) → publish + supersede members. On failure, heals latest/
    from the surviving member tiles and leaves members un-superseded.

    resume=True keeps the existing scratch dir when all photos are already
    pooled (count match) — ODM then skips its completed stages, so a run
    interrupted mid-pipeline (e.g. skystore power loss) loses only the stage
    it died in, not the hours of SfM before it. Falls back to a clean re-pool
    on any count mismatch.
    """
    from geo.models import OpenSkyMission, OpenSkyTileLayer

    con = OpenSkyMission.objects.filter(id=consolidation_id, is_consolidation=True).first()
    if not con:
        logger.error(f"Consolidation {consolidation_id} not found / not a consolidation")
        return False

    members = [link.member for link in con.members.select_related('member').order_by('order')]
    member_ids = [m.id for m in members]
    if len(members) < 2:
        logger.error(f"Consolidation {consolidation_id}: needs >=2 members, has {len(members)}")
        return False
    not_pub = [m.id[:8] for m in members if m.status != OpenSkyMission.Status.PUBLISHED]
    if not_pub:
        logger.error(f"Consolidation {consolidation_id}: members not PUBLISHED: {not_pub}")
        return False

    r_proc = f"{SKYSTORE_FAST_PROCESSING}/{consolidation_id}"
    r_images = f"{r_proc}/images"
    r_ortho_saved = f"{SKYSTORE_OPENSKY}/orthos/{consolidation_id}.tif"
    r_tiles_mission = f"{SKYSTORE_TILES}/missions/{consolidation_id}"
    r_tiles_latest = f"{SKYSTORE_TILES}/latest"

    try:
        # --- Mark PROCESSING + union area/center ---
        union = _consolidation_union_bounds_3857(members)
        if not union:
            logger.error(f"Consolidation {consolidation_id}: no member has tile_z/x/y")
            return False
        from pyproj import Transformer
        t = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
        sw_lng, sw_lat = t.transform(union[0], union[1])
        ne_lng, ne_lat = t.transform(union[2], union[3])
        con.status = OpenSkyMission.Status.PROCESSING
        con.processing_started_at = timezone.now()
        con.processing_step = OpenSkyMission.ProcessingStep.ODM
        con.error_message = ''
        con.area = Polygon((
            (sw_lng, sw_lat), (ne_lng, sw_lat), (ne_lng, ne_lat), (sw_lng, ne_lat), (sw_lng, sw_lat),
        ))
        con.center_lat = (sw_lat + ne_lat) / 2
        con.center_lng = (sw_lng + ne_lng) / 2
        con.tile_z = con.tile_x = con.tile_y = None  # spans many cells — keep NULL
        con.save(update_fields=[
            'status', 'processing_started_at', 'processing_step', 'error_message',
            'area', 'center_lat', 'center_lng', 'tile_z', 'tile_x', 'tile_y',
        ])
        _publish_mission_update(con.id, {'status': 'PROCESSING', 'processing_step': 'odm'})

        # --- Step 1: pre-flight photo cap + disk ---
        total_photos = sum(m.source_photos_count for m in members)
        if total_photos > MAX_CONSOLIDATION_PHOTOS:
            raise RuntimeError(
                f"cluster has {total_photos} photos > cap {MAX_CONSOLIDATION_PHOTOS}; split the cluster")
        dfres = _skystore_ssh(f"df -BG --output=avail {SKYSTORE_FAST_PROCESSING} | tail -1")
        free_gb = int(''.join(c for c in (dfres.stdout or '0').strip() if c.isdigit()) or '0')
        if free_gb < MIN_FAST_PROCESSING_FREE_GB:
            raise RuntimeError(
                f"/fast-processing has {free_gb}G free < {MIN_FAST_PROCESSING_FREE_GB}G required")

        # --- Step 2: combined project — copy each member's photos with its prefix ---
        pooled = False
        if resume:
            n_existing = (_skystore_ssh(f"ls {r_images} 2>/dev/null | wc -l").stdout or '0').strip()
            if n_existing.isdigit() and int(n_existing) == total_photos:
                logger.info(
                    f"Consolidation {consolidation_id[:8]}: resume — {n_existing} photos already "
                    f"pooled, keeping scratch (ODM skips completed stages)")
                pooled = True
            else:
                logger.info(
                    f"Consolidation {consolidation_id[:8]}: resume requested but images dir has "
                    f"{n_existing} != {total_photos} photos — re-pooling from scratch")
        if not pooled:
            _skystore_ssh(f"sudo rm -rf {r_proc} && mkdir -p {r_images}")
            for link in con.members.order_by('order'):
                src = f"{SKYSTORE_OPENSKY}/missions/{link.member_id}/images"
                # find -iname matches .jpg/.JPG and exits 0 on no match (a bare glob
                # would iterate the literal pattern and fail the loop).
                _skystore_ssh(
                    f'find {src} -maxdepth 1 -type f -iname "*.jpg" | '
                    f'while read f; do cp "$f" {r_images}/{link.prefix}$(basename "$f"); done',
                    timeout=3600,
                )
            n_copied = _skystore_ssh(f"ls {r_images} | wc -l").stdout.strip()
            logger.info(f"Consolidation {consolidation_id[:8]}: pooled {n_copied} photos from {len(members)} missions")

        # --- Step 3: ODM split-merge ---
        con.processing_step = OpenSkyMission.ProcessingStep.ODM
        con.save(update_fields=['processing_step'])
        r_merged = run_odm_splitmerge_skystore(consolidation_id, no_split=no_split,
                                               gps_accuracy=gps_accuracy)

        # --- Step 4: reproject to EPSG:3857 ---
        r_3857 = f"{r_proc}/orthophoto_3857.tif"
        _skystore_ssh(
            f"gdalwarp -t_srs EPSG:3857 -r lanczos -co COMPRESS=LZW -co TILED=YES "
            f"-overwrite {r_merged} {r_3857}", timeout=1800)
        # Save unclipped (needed for ORB neighbor reads + future re-alignment)
        _skystore_ssh(f"cp {r_3857} {r_ortho_saved}")

        # --- Step 5 / 5b: members + satellite + ORB anchor to absolute frame ---
        con.processing_step = OpenSkyMission.ProcessingStep.ALIGNMENT
        con.save(update_fields=['processing_step'])
        _anchor_merged_ortho(consolidation_id, r_ortho_saved, r_proc, member_ids)

        # --- Step 5.9: VERIFICATION GATE — refuse to publish a merged ortho
        # that disagrees with its members. Same-content ORB per member; the mean
        # (residual) must be ~0 after the anchor (gross mis-anchor catch), and the
        # SPREAD = max per-member deviation from that mean.
        # The spread threshold is SPLIT-MODE dependent:
        #   --split  → 2.5m: spread catches piecewise submodel-merge failures
        #              (run-4 2026-06-12: quadrants 26-49m apart, melted patchwork).
        #   --no-split → 4.0m: ONE global model, so there is NO submodel-merge mode
        #              to fail. The spread floor is then the legitimate residual of a
        #              similarity-anchored same-season block — the consolidation
        #              renders buildings differently from each leaning single-mission
        #              member, and the weakest-overlap member dominates the max
        #              (01KV2R18 June 4-cell: residual 0.25m, spread 2.70m from one
        #              inl=0.52 member while the other 3 agree ≤1.4m). 4.0m still
        #              catches a cross-season joint warp (10.8m) and any gross break.
        #              (TODO: an inlier-weighted/2nd-largest spread would be less
        #              single-weak-member sensitive than max — defer until needed.) ---
        ver_edges = _measure_consolidation_vs_members(consolidation_id, member_ids)
        if len(ver_edges) >= 2:
            vw = sum(e['overlap_m2'] * e['inlier_ratio'] for e in ver_edges)
            vdx = sum(e['dx_m'] * e['overlap_m2'] * e['inlier_ratio'] for e in ver_edges) / vw
            vdy = sum(e['dy_m'] * e['overlap_m2'] * e['inlier_ratio'] for e in ver_edges) / vw
            vshift = (vdx ** 2 + vdy ** 2) ** 0.5
            vspread = max(((e['dx_m'] - vdx) ** 2 + (e['dy_m'] - vdy) ** 2) ** 0.5 for e in ver_edges)
            spread_gate = 4.0 if no_split else 2.5
            logger.info(
                f"Consolidation {consolidation_id[:8]}: member verification "
                f"residual=({vdx:+.2f},{vdy:+.2f})m |s|={vshift:.2f}m spread={vspread:.2f}m "
                f"(gate 1.0/{spread_gate}m)")
            if vshift > 1.0 or vspread > spread_gate:
                raise RuntimeError(
                    f"merged ortho disagrees with members (residual {vshift:.2f}m, "
                    f"spread {vspread:.2f}m > 1.0/{spread_gate}m gate) — refusing to "
                    f"publish; see odm_splitmerge.log")
        else:
            logger.warning(
                f"Consolidation {consolidation_id[:8]}: verification gate skipped "
                f"({len(ver_edges)} member edge(s) measurable)")

        # --- Step 7: clip to union rectangle (Z17-aligned → no partial tiles) ---
        con.processing_step = OpenSkyMission.ProcessingStep.TILING
        con.save(update_fields=['processing_step'])
        r_clipped = f"{r_proc}/orthophoto_clipped.tif"
        _skystore_ssh(
            f"gdalwarp -te {union[0]} {union[1]} {union[2]} {union[3]} -te_srs EPSG:3857 "
            f"-r lanczos -co COMPRESS=LZW -co TILED=YES -dstnodata 0 -overwrite "
            f"{r_ortho_saved} {r_clipped}", timeout=1800)

        # --- Step 8: gdal2tiles → TMS → XYZ WebP ---
        r_tms = f"{r_proc}/tiles_tms"
        _skystore_ssh(
            f"gdal2tiles.py -z {TILE_MIN_ZOOM}-{TILE_MAX_ZOOM} -w none -r lanczos "
            f"--processes=3 {r_clipped} {r_tms}", timeout=57600)
        _skystore_ssh(f"rm -rf {r_tiles_mission} && mkdir -p {r_tiles_mission}")
        conv = _skystore_ssh(
            f"python3 -c {shlex.quote(_build_tms_to_xyz_webp_script(r_tms, r_tiles_mission, WEBP_QUALITY))}",
            timeout=3600)
        tiles_count = tiles_size = 0
        for line in conv.stdout.strip().splitlines():
            if line.startswith("TILES_RESULT:"):
                _, tc, ts = line.split(":"); tiles_count, tiles_size = int(tc), int(ts)

        # --- Step 9: record tile layers at fresh max layer_order (on top) ---
        OpenSkyTileLayer.objects.filter(mission_id=consolidation_id).delete()
        _record_tile_layers(consolidation_id, r_tiles_mission)

        # --- Step 10: override latest/ — clear each member's own tiles, then plant ---
        # Z17+ latest/ is size-wins (NOT layer_order). Clearing member-owned coords
        # frees them so the consolidation's real tiles win vs nothing; non-member
        # neighbor coords are untouched (their real tile beats our ~200B placeholder).
        # COMPOSITE GUARD: clear a member coord ONLY where the consolidation has a
        # real tile (override_tiles_dir). Where the consolidation ortho has a nodata
        # hole (empty ~200B placeholder), the member tile is KEPT and survives the
        # size-wins plant (202B <= member → skipped) → the hole is filled by the
        # member, never lost. The alignment gate does NOT verify completeness.
        composite_filled = 0
        for mid in member_ids:
            composite_filled += _clear_self_owned_latest_tiles(
                mid, r_tiles_latest, f"{SKYSTORE_TILES}/missions/{mid}",
                override_tiles_dir=r_tiles_mission)
        if composite_filled:
            logger.warning(
                f"Consolidation {consolidation_id[:8]}: COMPLETENESS — {composite_filled} member "
                f"tile coord(s) kept as composite-fill (joint ODM left nodata holes there). "
                f"Coverage preserved by members; reconstruction is incomplete — see odm_splitmerge.log")
        _skystore_ssh(
            f"python3 -c {shlex.quote(_build_update_latest_script(r_tiles_mission, r_tiles_latest, consolidation_id))}",
            timeout=600)
        # z<=16 overview: layer_order DOES apply here → max-order consolidation on top.
        rebuild_overview_latest(consolidation_id)
        # z>=17: pixel-composite any tile that is not fully opaque (consolidation
        # ortho sub-tile nodata holes at middle zooms) from members underneath —
        # closes partial holes that the size-wins plant / composite-guard can't.
        composite_partial_consolidation_tiles(consolidation_id)

        # --- Step 11: publish + supersede members ---
        OpenSkyMission.objects.filter(id__in=member_ids).update(superseded_by=con)
        con.status = OpenSkyMission.Status.PUBLISHED
        con.published_at = timezone.now()
        con.georef_changed_at = timezone.now()  # fresh ortho saved + anchored above
        con.tiles_count = tiles_count
        con.tiles_size_mb = round(tiles_size / 1024 / 1024, 2)
        con.min_zoom = TILE_MIN_ZOOM
        con.max_zoom = TILE_MAX_ZOOM
        con.place_label, con.place_region = reverse_geocode_place(con.center_lat, con.center_lng)
        con.processing_step = ''
        con.save()
        _publish_mission_update(con.id, {
            'status': 'PUBLISHED', 'processing_step': '',
            'published_at': con.published_at.isoformat(), 'tiles_count': con.tiles_count,
        })

        # --- Step 12: cleanup scratch on success ---
        _skystore_ssh(f"sudo rm -rf {r_proc}")
        logger.info(f"Consolidation {consolidation_id} published: {len(members)} missions → {tiles_count} tiles")
        return True

    except Exception as e:
        logger.error(f"Error consolidating {consolidation_id}: {e}", exc_info=True)
        # Heal latest/: recomposite the consolidation's coords from surviving
        # contributors (members keep their tiles + DB rows) so no holes remain
        # from a partial clear/plant. No-op if we failed before any latest/ write.
        try:
            rebuild_tiles_after_deletion(consolidation_id)
        except Exception as he:
            logger.error(f"Consolidation heal failed for {consolidation_id}: {he}")
        con.status = OpenSkyMission.Status.FAILED
        con.processing_step = ''
        con.error_message = str(e)[:2000]
        con.save(update_fields=['status', 'processing_step', 'error_message'])
        _publish_mission_update(con.id, {'status': 'FAILED', 'processing_step': '', 'error_message': con.error_message})
        logger.error(f"Consolidation scratch preserved for diagnostics: {r_proc}")
        return False
