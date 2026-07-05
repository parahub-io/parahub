"""
Revert (undo) accumulated Phase-2 similarity corrections on OpenSky missions.

Each published mission tracks its CUMULATIVE similarity correction in
corr_ln_scale / corr_rotation_deg / corr_dx_m / corr_dy_m (composed about the
mission's Z17 centroid — see _compose_similarity_about_centroid). This command
applies the exact INVERSE similarity about the SAME centroid, which:
  - composes corr_* back to identity (0,0,0,0);
  - returns the saved ortho's geotransform to its pre-similarity, axis-aligned
    base (satellite/consensus translations are NOT in corr_* — they edit the
    affine directly — so they are preserved);
  - reclips + retiles + republishes from the de-rotated ortho.

The similarity step is a pure geotransform edit (no pixel resampling — see
_build_similarity_warp_script), so this is a LOSSLESS exact undo: the ortho
returns to the same pixels + affine it had before any similarity correction.

Motivation: a bad/experimental pose-graph solve (e.g. the σ-calibration
anchor_weight=5000 experiment, 2026-06-19) can be rolled back cleanly. Note the
satellite re-anchor path canNOT do this while the ortho carries a rotated
geotransform — `gdal_translate -projwin` rejects rotated rasters — so undoing
the similarity at the affine level is the only clean revert.

Run the apply as a transient systemd unit (retiling is multi-minute per mission;
see PK/troubleshooting.md § Long-Running Jobs). The math itself is sub-second.

Usage:
  python manage.py revert_opensky_similarity --missions=ULID1,ULID2 --dry-run
  python manage.py revert_opensky_similarity --missions=ULID1,ULID2
  python manage.py revert_opensky_similarity --all-corrected   # every mission with non-identity corr_*
"""
import math
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger('opensky')

# corr_* magnitudes below which a mission is already ~identity (skip).
IDENTITY_EPS_T = 0.01   # metres
IDENTITY_EPS_S = 1e-5   # |ln scale|
IDENTITY_EPS_R = 1e-4   # degrees


def _invert_about_centroid(corr):
    """Inverse of a similarity (ln_scale, rotation_deg, tx, ty) taken about a
    fixed centroid, in the same parameterization as
    _compose_similarity_about_centroid → compose(corr, inverse) == identity.

    C(p) = s·R·(p−c)+c+t ;  C⁻¹ has scale 1/s, rotation −θ, translation
    t' = −(1/s)·R⁻¹·t."""
    lns, rot, tx, ty = corr
    s = math.exp(lns)
    th = math.radians(rot)
    c, sn = math.cos(th), math.sin(th)
    inv_tx = -(1.0 / s) * (c * tx + sn * ty)
    inv_ty = -(1.0 / s) * (-sn * tx + c * ty)
    return (-lns, -rot, inv_tx, inv_ty)


class Command(BaseCommand):
    help = 'Undo accumulated Phase-2 similarity corrections (invert corr_* about centroid, retile)'

    def add_arguments(self, parser):
        parser.add_argument('--missions', type=str, help='Comma-separated mission ULIDs')
        parser.add_argument('--all-corrected', action='store_true',
                            help='All published missions whose corr_* is non-identity')
        parser.add_argument('--dry-run', action='store_true',
                            help='Show inverse deltas + verify cancellation; apply nothing')

    def handle(self, *args, **options):
        from geo.models import OpenSkyMission
        from geo.opensky_processor import (
            apply_similarity_correction_skystore, opensky_tile_lock,
            _z17_tile_bounds_3857, _compose_similarity_about_centroid,
        )

        base = OpenSkyMission.objects.filter(
            status=OpenSkyMission.Status.PUBLISHED,
            is_consolidation=False,
            superseded_by__isnull=True,
            tile_z__isnull=False, tile_x__isnull=False, tile_y__isnull=False,
        )

        if options['missions']:
            ids = [s.strip() for s in options['missions'].split(',') if s.strip()]
            missions = list(base.filter(id__in=ids))
            missing = set(ids) - {m.id for m in missions}
            if missing:
                self.stderr.write(self.style.WARNING(
                    f"Not found / not eligible (skipped): {', '.join(sorted(missing))}"))
        elif options['all_corrected']:
            missions = [m for m in base
                        if (m.corr_dx_m**2 + m.corr_dy_m**2) ** 0.5 >= IDENTITY_EPS_T
                        or abs(m.corr_ln_scale) >= IDENTITY_EPS_S
                        or abs(m.corr_rotation_deg) >= IDENTITY_EPS_R]
        else:
            self.stderr.write(self.style.ERROR("Provide --missions=... or --all-corrected"))
            return

        if not missions:
            self.stdout.write("No eligible missions.")
            return

        # Compute + verify all inverses up front (sub-second, no skystore). Refuse
        # to apply anything if any inverse fails to cancel its corr_* — a guard
        # against a convention drift in _compose_similarity_about_centroid.
        plan = []
        self.stdout.write(
            "mission       corr(lnS,rot,|t|)          inverse(lnS,rot,tx,ty)            residual")
        for m in sorted(missions, key=lambda x: x.id):
            corr = (m.corr_ln_scale, m.corr_rotation_deg, m.corr_dx_m, m.corr_dy_m)
            inv = _invert_about_centroid(corr)
            res = _compose_similarity_about_centroid(corr, inv)
            res_mag = sum(abs(v) for v in res)
            x0, y0, x1, y1 = _z17_tile_bounds_3857(m.tile_z, m.tile_x, m.tile_y, 0)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            ct = (corr[2]**2 + corr[3]**2) ** 0.5
            self.stdout.write(
                "%-13s (%+.4f,%+.3f,%.2fm)  (%+.4f,%+.3f,%+.2f,%+.2f)  %.1e"
                % (m.id[:12], corr[0], corr[1], ct, inv[0], inv[1], inv[2], inv[3], res_mag))
            if res_mag > 1e-9:
                self.stderr.write(self.style.ERROR(
                    f"  REFUSING ALL: inverse for {m.id[:12]} does not cancel "
                    f"(residual {res_mag:.2e}) — convention mismatch"))
                return
            plan.append((m.id, cx, cy, inv))

        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(
                f"[DRY RUN] {len(plan)} mission(s) would be reverted, nothing applied"))
            return

        # Apply under the shared tile lock (serialize vs the processor).
        self.stdout.write("Acquiring OpenSky tile lock...")
        applied = 0
        with opensky_tile_lock(blocking=True):
            for mid, cx, cy, inv in plan:
                try:
                    ok = apply_similarity_correction_skystore(
                        mid, cx, cy, inv[0], inv[1], inv[2], inv[3])
                    if ok:
                        applied += 1
                        m = OpenSkyMission.objects.get(id=mid)
                        nt = (m.corr_dx_m**2 + m.corr_dy_m**2) ** 0.5
                        self.stdout.write(self.style.SUCCESS(
                            f"  reverted {mid[:12]} ({applied}/{len(plan)}) — new corr_* "
                            f"lnS={m.corr_ln_scale:+.5f} rot={m.corr_rotation_deg:+.4f}° "
                            f"|t|={nt:.3f}m"))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"  SKIP {mid[:12]} — inverse below apply threshold "
                            f"(corr_* already ~identity)"))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"  FAILED {mid[:12]}: {e}"))
                    logger.error(f"Similarity revert failed for {mid}: {e}", exc_info=True)
        self.stdout.write(self.style.SUCCESS(f"Reverted {applied}/{len(plan)} mission(s)"))
