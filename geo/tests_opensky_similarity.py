"""
Phase-2 similarity BA tests — delta semantics, edge freshness, lever-arm x_ref.

Covers the frame-consistency invariant (see realign_opensky_similarity
docstring): the solver works in DELTA space against fresh edges, so a
solve→apply→remeasure→solve cycle must converge to zero (no oscillation, no
mass-undo) — the failure mode of the former cumulative interpretation.

Run: python3 manage.py test geo.tests_opensky_similarity
"""

import math
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from geo.opensky_processor import (
    solve_similarity_ba,
    _compose_similarity_about_centroid,
    _edge_is_fresh,
    _parse_alignment_output,
    SIM_APPLY_TRANS_M,
    SIM_APPLY_SCALE,
    SIM_APPLY_ROT_DEG,
)


# ── Pure-math helpers ────────────────────────────────────────────

def _disp(state, c, x):
    """Displacement of point x under a linearized similarity-about-centroid
    state (u=ln_scale, omega_rad, tx, ty): u·d + ω·J·d + t, d = x − c."""
    u, om, tx, ty = state
    dx, dy = x[0] - c[0], x[1] - c[1]
    return (u * dx + om * (-dy) + tx, u * dy + om * dx + ty)


def _measure_edge(a, b, states, centroids, xref, w=1e4):
    """Synthesize the ORB measurement for edge a→b given current states:
    dx/dy = correction to apply to a at xref; ln_s/θ = relative scale/rotation."""
    da = _disp(states[a], centroids[a], xref)
    db = _disp(states[b], centroids[b], xref)
    return {
        'a': a, 'b': b,
        'ln_s': states[b][0] - states[a][0],
        'theta_rad': states[b][1] - states[a][1],
        'dx': db[0] - da[0], 'dy': db[1] - da[1],
        'w': w, 'xref': xref,
    }


def _edge_residual(e, sol, centroids):
    """Constraint violation of edge e under solution sol (0 = seam closed)."""
    sa = (sol[e['a']]['ln_scale'], math.radians(sol[e['a']]['rotation_deg']),
          sol[e['a']]['tx'], sol[e['a']]['ty'])
    sb = (sol[e['b']]['ln_scale'], math.radians(sol[e['b']]['rotation_deg']),
          sol[e['b']]['tx'], sol[e['b']]['ty'])
    da = _disp(sa, centroids[e['a']], e['xref'])
    db = _disp(sb, centroids[e['b']], e['xref'])
    return ((e['dx'] - (da[0] - db[0])) ** 2 + (e['dy'] - (da[1] - db[1])) ** 2) ** 0.5


def _grid_setup():
    """2×2 mission grid (300m cells), centroids + bounds."""
    cell = 300.0
    centroids, bounds = {}, {}
    for k, (gx, gy) in enumerate([(0, 0), (1, 0), (0, 1), (1, 1)]):
        mid = f"M{k}"
        cx, cy = gx * cell, gy * cell
        centroids[mid] = (cx, cy)
        bounds[mid] = (cx - 190, cy - 190, cx + 190, cy + 190)  # cell/2 + 40m buffer
    return centroids, bounds


GRID_EDGE_PAIRS = [('M0', 'M1'), ('M1', 'M0'), ('M2', 'M3'), ('M3', 'M2'),
                   ('M0', 'M2'), ('M2', 'M0'), ('M1', 'M3'), ('M3', 'M1')]


class SolverDeltaSemanticsTests(TestCase):
    def _solve_states(self, states, centroids, bounds, anchored):
        edges = []
        for a, b in GRID_EDGE_PAIRS:
            xref = (max(bounds[a][0], bounds[b][0]), min(bounds[a][3], bounds[b][3]))
            edges.append(_measure_edge(a, b, states, centroids, xref))
        return edges, solve_similarity_ba(centroids, bounds, edges, anchored_ids=anchored)

    def test_edge_residuals_zero_after_solve(self):
        """Seam-invariance: solved corrections close every edge.

        Truth has mean(u)=mean(ω)=0 (realistic: per-flight GPS scale errors are
        zero-mean) — then stage 1's identity-prior gauge coincides with the
        anchor-consistent gauge and closure is exact. A non-zero cluster-mean
        scale leaves a bounded ~mean(u)·baseline tension instead (deliberate
        two-stage tradeoff — see solve_similarity_ba docstring).
        """
        centroids, bounds = _grid_setup()
        states = {  # current misalignment (u, ω_rad, tx, ty); mean(u)=mean(ω)=0
            'M0': (0.004, math.radians(0.15), 0.0, 0.0),    # anchored: t=0
            'M1': (-0.006, math.radians(-0.10), 1.2, -0.8),
            'M2': (0.005, math.radians(0.05), 0.0, 0.0),    # anchored: t=0
            'M3': (-0.003, math.radians(-0.10), -1.5, 2.1),
        }
        edges, sol = self._solve_states(states, centroids, bounds, {'M0', 'M2'})
        for e in edges:
            self.assertLess(_edge_residual(e, sol, centroids), 1e-3,
                            f"edge {e['a']}→{e['b']} residual not closed")

    def test_anchor_noise_does_not_leak_into_scale(self):
        """Anchored missions carry 1-2m satellite noise in their translations.
        Scale/rotation must come from the DIRECT relative measurements only — a
        joint solve would read the noisy anchor baseline as common-mode scale
        (observed live 2026-06-11: identity direct scales vs −5000ppm joint
        solution). Guard: zero direct similarity + noisy anchor translations
        must yield zero scale/rotation."""
        centroids, bounds = _grid_setup()
        states = {  # u=ω=0 everywhere; anchored missions sit 1-2m off (sat noise)
            'M0': (0.0, 0.0, 1.2, -0.9),
            'M1': (0.0, 0.0, 0.3, 0.4),
            'M2': (0.0, 0.0, -1.0, 0.6),
            'M3': (0.0, 0.0, -0.2, -1.4),
        }
        _, sol = self._solve_states(states, centroids, bounds, {'M0', 'M2'})
        for m, s in sol.items():
            self.assertLess(abs(s['ln_scale']), 1e-6, m)
            self.assertLess(abs(s['rotation_deg']), 1e-6, m)

    def test_solve_apply_remeasure_converges_to_zero(self):
        """THE frame-consistency invariant: after applying the solved deltas,
        a remeasure+resolve cycle finds nothing left to do (no oscillation)."""
        centroids, bounds = _grid_setup()
        states = {
            'M0': (0.004, math.radians(0.15), 0.0, 0.0),
            'M1': (-0.006, math.radians(-0.10), 1.2, -0.8),
            'M2': (0.002, math.radians(0.05), 0.0, 0.0),
            'M3': (-0.003, math.radians(0.20), -1.5, 2.1),
        }
        _, sol = self._solve_states(states, centroids, bounds, {'M0', 'M2'})
        # Apply: corrections add to the displacement state (linearized).
        new_states = {
            m: (states[m][0] + sol[m]['ln_scale'],
                states[m][1] + math.radians(sol[m]['rotation_deg']),
                states[m][2] + sol[m]['tx'],
                states[m][3] + sol[m]['ty'])
            for m in states
        }
        _, sol2 = self._solve_states(new_states, centroids, bounds, {'M0', 'M2'})
        for m, s in sol2.items():
            self.assertLess(abs(s['ln_scale']), SIM_APPLY_SCALE / 10, m)
            self.assertLess(abs(s['rotation_deg']), SIM_APPLY_ROT_DEG / 10, m)
            self.assertLess((s['tx'] ** 2 + s['ty'] ** 2) ** 0.5, SIM_APPLY_TRANS_M / 10, m)

    def test_unconfirmed_huge_edge_is_rejected(self):
        """A one-directional garbage edge (no mirroring reciprocal) must be
        magnitude-filtered and leave the solution untouched. NOTE the known
        flip side (documented in solve_similarity_ba): a REAL far-off mission's
        edges also look like outliers — the reciprocal-trust rescue was
        prototyped 2026-06-11 but deferred (it leaked low-confidence scale
        noise into stage 1); when implemented, it must exempt the translation
        component only."""
        cell = 300.0
        centroids = {f'M{k}': (k * cell, 0.0) for k in range(5)}
        bounds = {m: (c[0] - 190, c[1] - 190, c[0] + 190, c[1] + 190)
                  for m, c in centroids.items()}
        states = {
            'M0': (0.0, 0.0, 0.0, 0.0),      # anchored
            'M1': (0.0, 0.0, 0.1, -0.05),
            'M2': (0.0, 0.0, -0.1, 0.05),
            'M3': (0.0, 0.0, 0.05, 0.1),
            'M4': (0.0, 0.0, 0.15, 0.05),
        }
        edges = []
        for k in range(4):
            a, b = f'M{k}', f'M{k+1}'
            xref = (max(bounds[a][0], bounds[b][0]), min(bounds[a][3], bounds[b][3]))
            edges.append(_measure_edge(a, b, states, centroids, xref))
            edges.append(_measure_edge(b, a, states, centroids, xref))
        sol = solve_similarity_ba(centroids, bounds, edges, anchored_ids={'M0'})
        junk = dict(_measure_edge('M1', 'M0', states, centroids,
                                  (max(bounds['M1'][0], bounds['M0'][0]),
                                   min(bounds['M1'][3], bounds['M0'][3]))),
                    dx=25.0, dy=-19.0)
        sol_junk = solve_similarity_ba(centroids, bounds, edges + [junk],
                                       anchored_ids={'M0'})
        for m in sol:
            d = ((sol_junk[m]['tx'] - sol[m]['tx']) ** 2
                 + (sol_junk[m]['ty'] - sol[m]['ty']) ** 2) ** 0.5
            self.assertLess(d, 0.05, f"unconfirmed junk edge must not move {m}")

    def test_xref_overrides_bbox_fallback(self):
        """Solver must reference the lever-arm at the measured xref, not the
        nominal bbox corner — residual evaluated AT xref closes only then."""
        centroids, bounds = _grid_setup()
        states = {
            'M0': (0.0, 0.0, 0.0, 0.0),
            'M1': (0.012, math.radians(0.4), 0.5, -0.3),  # strong scale+rot
            'M2': (0.0, 0.0, 0.0, 0.0),
            'M3': (0.0, 0.0, 0.0, 0.0),
        }
        # Measure M1→M0 at a point 60m away from the nominal corner.
        nominal = (max(bounds['M1'][0], bounds['M0'][0]),
                   min(bounds['M1'][3], bounds['M0'][3]))
        true_xref = (nominal[0], nominal[1] - 60.0)
        e = _measure_edge('M1', 'M0', states, centroids, true_xref)

        sol_with = solve_similarity_ba(centroids, bounds, [e], anchored_ids={'M0'})
        self.assertLess(_edge_residual(e, sol_with, centroids), 1e-3)

        e_no_xref = dict(e, xref=None)
        sol_without = solve_similarity_ba(centroids, bounds, [e_no_xref], anchored_ids={'M0'})
        # Fallback references the wrong point → residual at the TRUE xref stays
        # of order (Δu, Δω)·60m ≈ 0.7m+0.4m — the systematic error xref removes.
        self.assertGreater(_edge_residual(e, sol_without, centroids), 0.3)


class ComposeSimilarityTests(TestCase):
    def test_matches_matrix_composition(self):
        """corr_* bookkeeping composition == exact affine composition."""
        c = (100.0, 200.0)
        old = (0.01, 0.5, 2.0, -1.0)
        delta = (-0.004, -0.2, 0.7, 0.3)

        def apply(state, p):
            s = math.exp(state[0]); th = math.radians(state[1])
            dx, dy = p[0] - c[0], p[1] - c[1]
            return (s * (math.cos(th) * dx - math.sin(th) * dy) + c[0] + state[2],
                    s * (math.sin(th) * dx + math.cos(th) * dy) + c[1] + state[3])

        comp = _compose_similarity_about_centroid(old, delta)
        for p in [(0.0, 0.0), (150.0, 180.0), (-300.0, 1000.0)]:
            expected = apply(delta, apply(old, p))
            got = apply(comp, p)
            self.assertAlmostEqual(got[0], expected[0], places=6)
            self.assertAlmostEqual(got[1], expected[1], places=6)


class EdgeFreshnessTests(TestCase):
    def test_edge_is_fresh(self):
        t0 = timezone.now()
        before, after = t0 - timedelta(hours=1), t0 + timedelta(hours=1)
        self.assertTrue(_edge_is_fresh(after, t0, None))
        self.assertTrue(_edge_is_fresh(after, t0, t0))
        self.assertTrue(_edge_is_fresh(t0, None, None))      # never changed
        self.assertFalse(_edge_is_fresh(before, t0, None))   # one endpoint newer
        self.assertFalse(_edge_is_fresh(before, None, t0))
        self.assertFalse(_edge_is_fresh(t0, t0, None))       # not strictly after


class ParseAlignmentOutputTests(TestCase):
    def test_parses_xref_fields_and_legacy(self):
        out = (
            "EDGE:N1:1.5:-0.5:12000.0:0.80:1.002000:-0.1500:-934000.50:5170000.25\n"
            "EDGE:N2:0.3:0.1:8000.0:0.60:0.999000:0.0500\n"   # legacy 8-field
            "SKIP:N3:overlap_too_small_1.00pct\n"
        )
        edges = _parse_alignment_output('TEST', out)
        self.assertEqual(len(edges), 2)
        self.assertEqual(edges[0]['ref_x_3857'], -934000.50)
        self.assertEqual(edges[0]['ref_y_3857'], 5170000.25)
        self.assertIsNone(edges[1]['ref_x_3857'])
        self.assertIsNone(edges[1]['ref_y_3857'])


class CommandFreshnessWiringTests(TestCase):
    """DB wiring: stale edges are skipped, command aborts without fresh edges,
    --region clamp discovers neighbors on BOTH edge directions."""

    def _mk_mission(self, tile_x, tile_y, **kw):
        from geo.models import OpenSkyMission
        return OpenSkyMission.objects.create(
            status=OpenSkyMission.Status.PUBLISHED,
            tile_z=17, tile_x=tile_x, tile_y=tile_y,
            name=f"{tile_x}x{tile_y}", **kw,
        )

    def _mk_edge(self, a, b, **kw):
        from geo.models import OpenSkyPoseEdge
        defaults = dict(edge_type=OpenSkyPoseEdge.EdgeType.ORB_PAIR,
                        dx_m=0.1, dy_m=0.1, rel_scale=1.001, rel_rotation_deg=0.01,
                        weight=1e4, confidence=0.8, overlap_area_m2=1e4)
        defaults.update(kw)
        return OpenSkyPoseEdge.objects.create(mission_a=a, mission_b=b, **defaults)

    def test_all_edges_stale_aborts_with_hint(self):
        past = timezone.now() - timedelta(hours=1)
        m1 = self._mk_mission(62484, 48643)
        m2 = self._mk_mission(62485, 48643)
        self._mk_edge(m1, m2)
        self._mk_edge(m2, m1)
        # Both orthos "changed" after measurement → everything stale.
        from geo.models import OpenSkyPoseEdge
        OpenSkyPoseEdge.objects.update(measured_at=past)
        from geo.models import OpenSkyMission
        OpenSkyMission.objects.update(georef_changed_at=timezone.now())

        out, err = StringIO(), StringIO()
        call_command('realign_opensky_similarity', '--all', '--dry-run',
                     stdout=out, stderr=err)
        self.assertIn('No fresh ORB edges', err.getvalue())

    def test_fresh_edges_solve_dry_run(self):
        m1 = self._mk_mission(62484, 48643, georef_changed_at=timezone.now())
        m2 = self._mk_mission(62485, 48643, georef_changed_at=timezone.now())
        self._mk_edge(m1, m2)  # auto_now measured_at > georef_changed_at → fresh
        self._mk_edge(m2, m1)
        out = StringIO()
        call_command('realign_opensky_similarity', '--all', '--dry-run', stdout=out)
        self.assertIn('DRY RUN', out.getvalue())
        self.assertIn('would be re-tiled', out.getvalue())

    def test_cross_season_edges_dropped(self):
        """ORB edges between captures >SIM_MAX_SEASON_GAP_DAYS apart are junk
        (appearance change breaks matching) — must be excluded from the solve."""
        now = timezone.now()
        m1 = self._mk_mission(62484, 48643, captured_at=now - timedelta(days=90))
        m2 = self._mk_mission(62485, 48643, captured_at=now)
        self._mk_edge(m1, m2)
        self._mk_edge(m2, m1)
        out, err = StringIO(), StringIO()
        call_command('realign_opensky_similarity', '--all', '--dry-run',
                     stdout=out, stderr=err)
        self.assertIn('cross-season edge(s) skipped', out.getvalue())
        self.assertIn('No fresh ORB edges', err.getvalue())

    def test_region_clamp_is_bidirectional(self):
        # Region Z10 (488, 380) ⊃ Z17 tile 62484,48643 (62484//128=488, 48643//128=380).
        m_in = self._mk_mission(62484, 48643)
        m_in2 = self._mk_mission(62485, 48643)
        # Out-of-region neighbor (different Z10 column) whose edge points INTO
        # the region (it is mission_a) — the old one-directional query missed it.
        m_out = self._mk_mission(62593, 48643)  # 62593//128 = 489
        self._mk_edge(m_in, m_in2)
        self._mk_edge(m_in2, m_in)
        self._mk_edge(m_out, m_in)  # only a→b direction, a outside
        out = StringIO()
        call_command('realign_opensky_similarity', '--region=488,380', '--dry-run',
                     stdout=out)
        self.assertIn('2 free + 1 clamped', out.getvalue())
