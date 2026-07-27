"""
Unit tests for parahub/services/transit_eta.py — the shared ETA primitives
used by all four ETA readers (WS consumer + 3 REST endpoints).

Pure functions, no DB/Redis — SimpleTestCase.
"""

import orjson

from django.test import SimpleTestCase

from parahub.services.transit_eta import (
    ETA_DEFAULT_SEGMENT_S,
    ZOMBIE_ETA_GRACE_S,
    parse_rstops,
    segment_infos,
    segment_averages,
    build_index_map,
    resolve_origin,
    cumulative_min_etas,
    zombie_keeps_eta,
    remaining_segment_fraction,
    origin_with_fraction,
)


def _rstops(entries):
    return orjson.dumps(entries)


class ParseRstopsTest(SimpleTestCase):
    def test_legacy_three_element_snapshot(self):
        raw = _rstops([["a", 1.0, 2.0], ["b", 3.0, 4.0]])
        source_ids, coords, sched = parse_rstops(raw)
        self.assertEqual(source_ids, ["a", "b"])
        self.assertEqual(coords, [(1.0, 2.0), (3.0, 4.0)])
        self.assertEqual(sched, [None, None])

    def test_four_element_snapshot(self):
        raw = _rstops([["a", 1.0, 2.0, 0], ["b", 3.0, 4.0, 60.5]])
        source_ids, _coords, sched = parse_rstops(raw)
        self.assertEqual(source_ids, ["a", "b"])
        self.assertEqual(sched, [0, 60.5])

    def test_null_offsets_stay_none(self):
        raw = _rstops([["a", 1.0, 2.0, None], ["b", 3.0, 4.0, 120]])
        _ids, _coords, sched = parse_rstops(raw)
        self.assertEqual(sched, [None, 120])

    def test_invalid_inputs(self):
        self.assertIsNone(parse_rstops(None))
        self.assertIsNone(parse_rstops(b""))
        self.assertIsNone(parse_rstops(b"garbage"))
        # fewer than 2 stops → useless for segments
        self.assertIsNone(parse_rstops(_rstops([["a", 1.0, 2.0]])))


class SegmentInfosTest(SimpleTestCase):
    OFFSETS = [0, 100, 200, 300, 400]  # 4 segments, 100 s scheduled each

    def test_default_when_no_observation_and_no_schedule(self):
        infos = segment_infos([[], []], [None, None, None])
        self.assertEqual([s["avg"] for s in infos],
                         [ETA_DEFAULT_SEGMENT_S, ETA_DEFAULT_SEGMENT_S])
        self.assertEqual([s["source"] for s in infos], ["default", "default"])

    def test_pure_schedule_factor_stays_one(self):
        infos = segment_infos([[], [], [], []], self.OFFSETS)
        self.assertEqual([s["avg"] for s in infos], [100, 100, 100, 100])
        self.assertEqual({s["source"] for s in infos}, {"scheduled"})
        self.assertEqual({s["observed"] for s in infos}, {False})

    def test_observed_shrinks_toward_scheduled_prior(self):
        # 1 observation of 30 s vs 120 s scheduled, K=3:
        # (1*30 + 3*120) / 4 = 97.5
        infos = segment_infos([["30"]], [0, 120])
        self.assertAlmostEqual(infos[0]["avg"], 97.5)
        self.assertEqual(infos[0]["samples"], 1)
        self.assertTrue(infos[0]["observed"])
        self.assertEqual(infos[0]["source"], "observed")

    def test_observed_without_schedule_is_plain_mean(self):
        infos = segment_infos([["40", "60"]], [None, None])
        self.assertAlmostEqual(infos[0]["avg"], 50.0)

    def test_delay_factor_scales_unobserved_segments(self):
        # Two observed segments running 2× their 100 s schedule → factor 2.0
        # applies to the unobserved-but-scheduled tail.
        infos = segment_infos([["200"], ["200"], [], []], self.OFFSETS)
        self.assertAlmostEqual(infos[2]["avg"], 200.0)
        self.assertAlmostEqual(infos[3]["avg"], 200.0)
        # Observed segments themselves get the shrinkage blend, not the factor:
        # (1*200 + 3*100) / 4 = 125
        self.assertAlmostEqual(infos[0]["avg"], 125.0)

    def test_delay_factor_clamped(self):
        high = segment_infos([["500"], ["500"], [], []], self.OFFSETS)
        self.assertAlmostEqual(high[2]["avg"], 200.0)  # 5× clamped to 2.0
        low = segment_infos([["20"], ["20"], [], []], self.OFFSETS)
        self.assertAlmostEqual(low[2]["avg"], 50.0)    # 0.2× clamped to 0.5

    def test_delay_factor_needs_two_calibration_segments(self):
        infos = segment_infos([["200"], [], [], []], self.OFFSETS)
        self.assertAlmostEqual(infos[1]["avg"], 100.0)  # factor stays 1.0

    def test_segment_averages_matches_infos(self):
        obs = [["200"], [], [], []]
        self.assertEqual(
            segment_averages(obs, self.OFFSETS),
            [s["avg"] for s in segment_infos(obs, self.OFFSETS)],
        )


class ResolveOriginTest(SimpleTestCase):
    def test_index_map_first_occurrence_wins(self):
        self.assertEqual(build_index_map(["a", "b", "a"]), {"a": 0, "b": 1})

    def test_sid_anchors_when_on_sequence(self):
        index_map = build_index_map(["a", "b", "c"])
        self.assertEqual(resolve_origin("b", 2, index_map), 1)

    def test_falls_back_to_idx(self):
        index_map = build_index_map(["a", "b", "c"])
        self.assertEqual(resolve_origin("zz", 2, index_map), 2)  # off-sequence
        self.assertEqual(resolve_origin(None, 2, index_map), 2)  # missing
        self.assertEqual(resolve_origin("", 2, index_map), 2)    # empty


class CumulativeMinEtasTest(SimpleTestCase):
    IDS = ["a", "b", "c", "d"]
    SEG = [10.0, 20.0, 30.0]

    def test_single_vehicle_chain_is_cumulative(self):
        self.assertEqual(
            cumulative_min_etas(self.IDS, self.SEG, [0]),
            {"b": 10, "c": 30, "d": 60},
        )

    def test_min_across_vehicles(self):
        self.assertEqual(
            cumulative_min_etas(self.IDS, self.SEG, [0, 2]),
            {"b": 10, "c": 30, "d": 30},
        )

    def test_terminal_and_invalid_origins_ignored(self):
        self.assertEqual(cumulative_min_etas(self.IDS, self.SEG, [3]), {})
        self.assertEqual(cumulative_min_etas(self.IDS, self.SEG, [None, -1]), {})

    def test_fraction_scales_only_first_segment(self):
        # vehicle at 0, half of its current segment already done -> first seg halved
        self.assertEqual(
            cumulative_min_etas(self.IDS, self.SEG, [(0, 0.5)]),
            {"b": 5, "c": 25, "d": 55},  # 10*.5=5, +20=25, +30=55
        )

    def test_bare_int_and_full_fraction_equivalent(self):
        self.assertEqual(
            cumulative_min_etas(self.IDS, self.SEG, [(0, 1.0)]),
            cumulative_min_etas(self.IDS, self.SEG, [0]),
        )

    def test_fraction_none_treated_as_full(self):
        self.assertEqual(
            cumulative_min_etas(self.IDS, self.SEG, [(0, None)]),
            cumulative_min_etas(self.IDS, self.SEG, [0]),
        )

    def test_min_across_mixed_int_and_tuple(self):
        # v0 full (d=60) vs v2 with half of its segment (d=15) -> min keeps 15
        self.assertEqual(
            cumulative_min_etas(self.IDS, self.SEG, [0, (2, 0.5)]),
            {"b": 10, "c": 30, "d": 15},
        )


class OriginWithFractionTest(SimpleTestCase):
    COORDS = [(38.70, -9.10), (38.70, -9.00), (38.70, -8.90)]

    def test_midpoint_first_segment(self):
        o, f = origin_with_fraction(0, 38.70, -9.05, self.COORDS)
        self.assertEqual(o, 0)
        self.assertAlmostEqual(f, 0.5, places=6)

    def test_last_stop_degrades_to_whole(self):
        self.assertEqual(origin_with_fraction(2, 38.70, -8.90, self.COORDS), (2, 1.0))

    def test_missing_position_degrades_to_whole(self):
        self.assertEqual(origin_with_fraction(0, None, None, self.COORDS), (0, 1.0))

    def test_none_origin_passthrough(self):
        self.assertEqual(origin_with_fraction(None, 38.70, -9.05, self.COORDS), (None, 1.0))


class ZombieKeepsEtaTest(SimpleTestCase):
    NOW = 1_000_000.0
    MAP = build_index_map(["s0", "s1", "s2", "s3"])

    def test_short_dwell_with_consistent_sid_keeps_eta(self):
        self.assertTrue(zombie_keeps_eta(self.NOW, self.NOW - 150, "s2", 2, self.MAP))
        # one stop off is still consistent (snap boundary)
        self.assertTrue(zombie_keeps_eta(self.NOW, self.NOW - 150, "s1", 2, self.MAP))

    def test_desynced_sid_excluded(self):
        self.assertFalse(zombie_keeps_eta(self.NOW, self.NOW - 150, "s0", 2, self.MAP))

    def test_terminal_layover_excluded(self):
        # Parked at the direction's first stop = layover, not a timing point
        self.assertFalse(zombie_keeps_eta(self.NOW, self.NOW - 150, "s0", 0, self.MAP))
        self.assertFalse(zombie_keeps_eta(self.NOW, self.NOW - 150, "s0", 1, self.MAP))
        # Parked at index 1 (stt_idx 0 within tolerance) is NOT the terminal
        self.assertTrue(zombie_keeps_eta(self.NOW, self.NOW - 150, "s1", 0, self.MAP))

    def test_long_parked_excluded_even_if_consistent(self):
        parked = self.NOW - (ZOMBIE_ETA_GRACE_S + 1)
        self.assertFalse(zombie_keeps_eta(self.NOW, parked, "s2", 2, self.MAP))

    def test_unverifiable_excluded(self):
        self.assertFalse(zombie_keeps_eta(self.NOW, 0, "s2", 2, self.MAP))      # no mt
        self.assertFalse(zombie_keeps_eta(self.NOW, None, "s2", 2, self.MAP))   # no mt
        self.assertFalse(zombie_keeps_eta(self.NOW, self.NOW - 150, None, 2, self.MAP))  # no sid
        self.assertFalse(zombie_keeps_eta(self.NOW, self.NOW - 150, "zz", 2, self.MAP))  # off-sequence


class RemainingSegmentFractionTest(SimpleTestCase):
    # Horizontal segment (constant latitude): the cos-latitude scale is identical
    # for both endpoint distances, so the ratio is exact and easy to reason about.
    A = (38.70, -9.10)
    B = (38.70, -9.00)

    def test_at_origin_charges_whole_segment(self):
        self.assertAlmostEqual(
            remaining_segment_fraction(38.70, -9.10, self.A, self.B), 1.0, places=6)

    def test_at_next_stop_charges_nothing(self):
        self.assertAlmostEqual(
            remaining_segment_fraction(38.70, -9.00, self.A, self.B), 0.0, places=6)

    def test_midpoint_is_half(self):
        self.assertAlmostEqual(
            remaining_segment_fraction(38.70, -9.05, self.A, self.B), 0.5, places=6)

    def test_quarter_and_three_quarter(self):
        # 25% along -> 75% still ahead
        self.assertAlmostEqual(
            remaining_segment_fraction(38.70, -9.075, self.A, self.B), 0.75, places=6)
        # 75% along -> 25% still ahead
        self.assertAlmostEqual(
            remaining_segment_fraction(38.70, -9.025, self.A, self.B), 0.25, places=6)

    def test_lateral_offset_pulls_toward_half_and_stays_bounded(self):
        # A perpendicular GPS offset over the midpoint stays ~0.5
        self.assertAlmostEqual(
            remaining_segment_fraction(38.71, -9.05, self.A, self.B), 0.5, places=6)
        # Always within [0, 1] anywhere along (and off) the segment
        for lon in (-9.10, -9.08, -9.05, -9.02, -9.00):
            f = remaining_segment_fraction(38.70, lon, self.A, self.B)
            self.assertGreaterEqual(f, 0.0)
            self.assertLessEqual(f, 1.0)

    def test_missing_or_degenerate_degrades_to_whole_segment(self):
        self.assertEqual(remaining_segment_fraction(None, -9.05, self.A, self.B), 1.0)
        self.assertEqual(remaining_segment_fraction(38.70, None, self.A, self.B), 1.0)
        self.assertEqual(remaining_segment_fraction(38.70, -9.05, None, self.B), 1.0)
        self.assertEqual(remaining_segment_fraction(38.70, -9.05, self.A, ()), 1.0)
        self.assertEqual(remaining_segment_fraction(38.70, -9.05, ("x", "y"), self.B), 1.0)
        # from == to at the vehicle's position (zero-length) -> no division by zero
        self.assertEqual(remaining_segment_fraction(38.70, -9.10, self.A, self.A), 1.0)


class MedianRobustnessTest(SimpleTestCase):
    """The observed estimate is the FIFO median: a single layover-inflated
    observation (dwell included in recorded times) must not drag the segment
    estimate nor peg the route delay factor."""

    OFFSETS = [0, 120, 240, 360, 480]

    def test_giant_observation_does_not_drag_estimate(self):
        # 40/45/1500 s on a 120 s-scheduled segment: median 45 blended with
        # the prior stays near schedule; a mean (528 s) would have landed ~324.
        infos = segment_infos([["40", "45", "1500"], [], [], []], self.OFFSETS)
        self.assertLess(infos[0]["avg"], 110)

    def test_majority_regime_change_is_tracked(self):
        # When most of the window says ~900 s (real jam / recurring dwell),
        # the estimate must follow, not reject it as an outlier.
        infos = segment_infos([["900", "880", "920", "40"], [], [], []], self.OFFSETS)
        self.assertGreater(infos[0]["avg"], 500)

    def test_factor_robust_to_giant(self):
        # Two observed segments, one poisoned by a layover: factor from
        # medians stays moderate instead of clamping at ETA_FACTOR_MAX, so
        # unobserved segments are not doubled.
        infos = segment_infos([["40", "45", "1500"], ["130"], [], []], self.OFFSETS)
        unobserved = infos[2]
        self.assertEqual(unobserved["source"], "scheduled")
        self.assertLess(unobserved["avg"], 120 * 1.2)


class ParkedBeyondGraceTest(SimpleTestCase):
    """Reader gate for buses parked past the ETA grace: cumulative segment
    dwell (dw) catches what GPS micro-moves hide from the zombie clock (mt),
    while the move-recency condition keeps a bus that just pulled out of a
    layover (dw not yet reset) chaining normally."""

    def test_long_parked_and_still_is_blocked(self):
        from parahub.services.transit_eta import parked_beyond_grace
        # dwelled 8 min this segment, last move 2 min ago -> no chain
        self.assertTrue(parked_beyond_grace(1000.0, 1000.0 - 120, 480.0))

    def test_short_dwell_passes(self):
        from parahub.services.transit_eta import parked_beyond_grace
        # 4 min at a timing point (below grace) -> keeps chaining
        self.assertFalse(parked_beyond_grace(1000.0, 1000.0 - 120, 240.0))

    def test_just_departed_after_layover_passes(self):
        from parahub.services.transit_eta import parked_beyond_grace
        # dw still large (no transition yet) but moving right now -> chains
        self.assertFalse(parked_beyond_grace(1000.0, 1000.0 - 10, 900.0))

    def test_missing_data_passes(self):
        from parahub.services.transit_eta import parked_beyond_grace
        self.assertFalse(parked_beyond_grace(1000.0, None, 900.0))
        self.assertFalse(parked_beyond_grace(1000.0, 1000.0 - 120, None))
        self.assertFalse(parked_beyond_grace(1000.0, 1000.0 - 120, 0))
