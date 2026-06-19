"""
Phase-2 pose-graph SIMILARITY bundle adjustment — see PK/opensky-system.md
§ Pose Graph Architecture.

Phase 1 (consensus) only corrects per-mission TRANSLATION, so neighbouring
orthos still disagree by scale (per-flight GPS ~±1-2%) + rotation (slope DSM) —
seams that grow with distance from each mission's centre (~5 m corners). This
solves a similarity DELTA per mission in ONE batch from the scale+rotation the
ORB step measures, and applies it as a cheap georeferencing warp (no
re-reconstruction).

FRAME FRESHNESS (correctness invariant): the solver works in DELTA space
against the missions' CURRENT on-disk georefs, so it may only consume edges
measured AFTER the last physical georef change of BOTH endpoints
(`georef_changed_at`, bumped by publish / satellite / consensus / similarity
applies). Stale edges describe frames that no longer exist — using them would
re-derive already-applied corrections (mass-undo / double-apply). Standard
workflow:

  python manage.py measure_opensky_edges --all          # refresh edges
  python manage.py realign_opensky_similarity --all --dry-run
  python manage.py realign_opensky_similarity --all

Other usage:
  python manage.py realign_opensky_similarity --missions=ULID1,ULID2,...
  python manage.py realign_opensky_similarity --region=<Z10x,Z10y>    # + 1-ring clamp

Run the apply phase as a transient systemd unit (retiling movers is multi-hour;
see PK/troubleshooting.md § session-freeze). The solve itself is sub-second.
"""
import math
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger('opensky')

Z17_TO_Z10 = 1 << 7  # 7 zoom levels between Z17 cells and a Z10 super-tile


class Command(BaseCommand):
    help = 'Phase-2 similarity bundle adjustment (global scale+rotation+translation)'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true', help='Solve all published missions in one batch')
        parser.add_argument('--missions', type=str, help='Comma-separated mission ULIDs (explicit set)')
        parser.add_argument('--region', type=str, help='Z10 super-tile "x,y" (solves it + a 1-ring clamp)')
        parser.add_argument('--dry-run', action='store_true', help='Solve + report corrections; apply nothing')
        parser.add_argument('--apply-threshold', type=float, default=None,
                            help='Override translation apply threshold (m)')
        parser.add_argument('--max-season-gap', type=int, default=None,
                            help='Override SIM_MAX_SEASON_GAP_DAYS (default 45) — the capture-day '
                                 'gap above which an ORB edge is skipped as cross-season. DIAGNOSTIC: '
                                 'raise it to test whether cross-season ground seams can close via '
                                 'pose-graph (cross-season ortho-ORB is unreliable in general; only '
                                 'use when reciprocals mirror).')
        parser.add_argument('--anchor-weight', type=float, default=None,
                            help='Override satellite anchor weight in the translation stage '
                                 '(default SATELLITE_DAMPING_WEIGHT=2e5). σ-calibrated ~5e3 makes '
                                 'anchors 25-50x WEAKER than big ORB edges → trusts neighbour seams '
                                 'over noisy satellite → relative seams close to ~0.3m at the cost of '
                                 '~1-2m absolute drift (PK § Known calibration limit). Only affects '
                                 'SAME-season seams — cross-season ORB edges are skipped as unreliable.')

    def handle(self, *args, **options):
        from geo.models import OpenSkyMission, OpenSkyPoseEdge
        from geo.opensky_processor import (
            solve_similarity_ba, apply_similarity_correction_skystore,
            opensky_tile_lock, _z17_tile_bounds_3857, _edge_is_fresh,
            SIM_APPLY_TRANS_M, SIM_APPLY_SCALE, SIM_APPLY_ROT_DEG,
            SIM_MAX_SEASON_GAP_DAYS,
        )

        dry_run = options['dry_run']

        base = OpenSkyMission.objects.filter(
            status=OpenSkyMission.Status.PUBLISHED,
            is_consolidation=False,
            superseded_by__isnull=True,
            tile_z__isnull=False, tile_x__isnull=False, tile_y__isnull=False,
        )

        # --- Resolve the free (solved) set + clamped 1-ring ---
        clamped_ids = set()
        if options['missions']:
            ids = [s.strip() for s in options['missions'].split(',') if s.strip()]
            free = list(base.filter(id__in=ids))
        elif options['region']:
            try:
                zx, zy = (int(v) for v in options['region'].split(','))
            except ValueError:
                self.stderr.write(self.style.ERROR("--region must be 'z10x,z10y'")); return
            free = [m for m in base if m.tile_x // Z17_TO_Z10 == zx and m.tile_y // Z17_TO_Z10 == zy]
            free_ids = {m.id for m in free}
            # 1-ring clamp: missions outside the region that share an ORB edge
            # with an in-region mission are included as FIXED boundary anchors
            # (honours cross-region edges, keeps per-region gauge consistent).
            # Edges are directional (mission_a = whoever measured) and often
            # exist in one direction only — query BOTH sides, else a neighbor
            # whose edge points INTO the region is silently dropped and the
            # border seam can reopen.
            orb_all = OpenSkyPoseEdge.objects.filter(edge_type=OpenSkyPoseEdge.EdgeType.ORB_PAIR)
            nbr_b = orb_all.filter(mission_a_id__in=free_ids).values_list('mission_b_id', flat=True)
            nbr_a = orb_all.filter(mission_b_id__in=free_ids).values_list('mission_a_id', flat=True)
            clamped_ids = (set(nbr_b) | set(nbr_a)) - free_ids - {None}
        elif options['all']:
            free = list(base)
        else:
            self.stderr.write(self.style.ERROR("Provide --all, --missions=..., or --region=x,y")); return

        free_ids = {m.id for m in free}
        if len(free_ids) < 2:
            self.stderr.write(self.style.ERROR("Need >= 2 missions to solve")); return

        solve_ids = free_ids | clamped_ids
        solve_missions = list(OpenSkyMission.objects.filter(id__in=solve_ids))

        # --- Geometry (EPSG:3857): centroid = Z17 cell centre; bounds = cell +
        # flight buffer so adjacent cells overlap (lever-arm reference point). ---
        centroids, bounds = {}, {}
        for m in solve_missions:
            x0, y0, x1, y1 = _z17_tile_bounds_3857(m.tile_z, m.tile_x, m.tile_y, buffer_m=0)
            centroids[m.id] = ((x0 + x1) / 2, (y0 + y1) / 2)
            bx0, by0, bx1, by1 = _z17_tile_bounds_3857(m.tile_z, m.tile_x, m.tile_y, buffer_m=40)
            bounds[m.id] = (bx0, by0, bx1, by1)

        # --- ORB edges among the solve set: FRESH (frame invariant) and
        # SAME-SEASON only (cross-season ortho-ORB is structurally unreliable —
        # reciprocals disagree by metres; see SIM_MAX_SEASON_GAP_DAYS). ---
        georef_changed = {m.id: m.georef_changed_at for m in solve_missions}
        captured = {m.id: (m.captured_at or m.uploaded_at) for m in solve_missions}
        orb = OpenSkyPoseEdge.objects.filter(
            edge_type=OpenSkyPoseEdge.EdgeType.ORB_PAIR,
            mission_a_id__in=solve_ids, mission_b_id__in=solve_ids,
        )
        max_gap = options['max_season_gap'] if options['max_season_gap'] is not None else SIM_MAX_SEASON_GAP_DAYS
        edges, n_stale, n_cross_season = [], 0, 0
        for e in orb:
            if not _edge_is_fresh(e.measured_at,
                                  georef_changed.get(e.mission_a_id),
                                  georef_changed.get(e.mission_b_id)):
                n_stale += 1
                continue
            ca, cb = captured.get(e.mission_a_id), captured.get(e.mission_b_id)
            if ca and cb and abs((ca - cb).days) > max_gap:
                n_cross_season += 1
                continue
            edges.append({
                'a': e.mission_a_id, 'b': e.mission_b_id,
                'ln_s': math.log(e.rel_scale) if e.rel_scale > 0 else 0.0,
                'theta_rad': math.radians(e.rel_rotation_deg),
                'dx': e.dx_m, 'dy': e.dy_m,
                'w': max(e.weight, 1e-6),
                'xref': ((e.ref_x_3857, e.ref_y_3857)
                         if e.ref_x_3857 is not None and e.ref_y_3857 is not None else None),
            })
        if n_stale:
            self.stdout.write(self.style.WARNING(
                f"{n_stale} stale edge(s) skipped (measured before an endpoint's last "
                f"georef change) — run `measure_opensky_edges` to refresh them"))
        if n_cross_season:
            self.stdout.write(
                f"{n_cross_season} cross-season edge(s) skipped (captures >"
                f"{SIM_MAX_SEASON_GAP_DAYS}d apart — ortho-ORB unreliable across seasons; "
                f"those seams need consolidation/sfm_bridge)")
        if not edges:
            self.stderr.write(self.style.ERROR(
                "No fresh ORB edges in the solve set — run "
                "`python manage.py measure_opensky_edges --all` first, then re-run this."))
            return

        anchored = set(OpenSkyPoseEdge.objects.filter(
            edge_type=OpenSkyPoseEdge.EdgeType.SATELLITE_ANCHOR,
            mission_a_id__in=solve_ids,
        ).values_list('mission_a_id', flat=True))
        # Clamped 1-ring missions are pinned at their current position too.
        anchored |= clamped_ids

        from geo.opensky_processor import SATELLITE_DAMPING_WEIGHT
        aw = options['anchor_weight'] if options['anchor_weight'] is not None else SATELLITE_DAMPING_WEIGHT
        self.stdout.write(
            f"Solving similarity BA: {len(free_ids)} free + {len(clamped_ids)} clamped, "
            f"{len(edges)} ORB edges, {len(anchored & solve_ids)} anchored, "
            f"anchor_weight={aw:.0f}{' (σ-calibrated)' if options['anchor_weight'] is not None else ' (default)'}")

        sol = solve_similarity_ba(centroids, bounds, edges, anchored_ids=anchored,
                                  anchor_weight=options['anchor_weight'])
        if not sol:
            self.stderr.write(self.style.ERROR("Solver returned nothing")); return
        if any(v.get('translation_only') for v in sol.values()):
            self.stdout.write(self.style.WARNING(
                "No satellite anchors in set — scale/rotation gauge from prior only"))

        # --- Report (solved DELTAS + which would move) ---
        thr_t = options['apply_threshold'] if options['apply_threshold'] is not None else SIM_APPLY_TRANS_M
        movers = []
        self.stdout.write("mission      Δln_s(ppm) Δrot(°)  |Δt|(m)   move?")
        for m in sorted(free, key=lambda x: x.id):
            s = sol[m.id]
            d_t = (s['tx'] ** 2 + s['ty'] ** 2) ** 0.5
            move = (d_t >= thr_t or abs(s['ln_scale']) >= SIM_APPLY_SCALE
                    or abs(s['rotation_deg']) >= SIM_APPLY_ROT_DEG)
            if move:
                movers.append(m.id)
            self.stdout.write(
                f"{m.id[:12]} {s['ln_scale']*1e6:+10.0f} {s['rotation_deg']:+7.3f} "
                f"{d_t:7.2f}   {'YES' if move else 'no'}")
        self.stdout.write(f"{len(movers)}/{len(free)} missions would be re-tiled")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("[DRY RUN] nothing applied")); return
        if not movers:
            self.stdout.write("Nothing to apply (all below threshold)"); return

        # --- Apply movers under the shared tile lock (serialize vs processor) ---
        self.stdout.write("Acquiring OpenSky tile lock...")
        applied = 0
        with opensky_tile_lock(blocking=True):
            for mid in movers:
                s = sol[mid]
                cx, cy = centroids[mid]
                try:
                    if apply_similarity_correction_skystore(
                        mid, cx, cy, s['ln_scale'], s['rotation_deg'], s['tx'], s['ty']):
                        applied += 1
                        self.stdout.write(self.style.SUCCESS(f"  applied {mid[:12]} ({applied}/{len(movers)})"))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"  FAILED {mid[:12]}: {e}"))
                    logger.error(f"Similarity apply failed for {mid}: {e}", exc_info=True)
        self.stdout.write(self.style.SUCCESS(f"Applied similarity correction to {applied} mission(s)"))
