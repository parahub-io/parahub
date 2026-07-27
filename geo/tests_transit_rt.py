"""
Tests for RouteCache._load_all() — verifies all raw SQL queries are valid.

Catches SQL syntax errors (missing aliases, bad JOINs) that crash
per-source RT fetchers at startup.
"""

from django.test import TestCase

from geo.models import TransitDataSource, Route
from parahub.services.transit_rt import RouteCache


class RouteCacheLoadAllTest(TestCase):
    """Ensure _load_all executes without SQL errors."""

    def test_load_all_no_filter(self):
        """_load_all(None) — loads all routes, no WHERE clause."""
        cache = RouteCache()
        # Should not raise ProgrammingError
        route_info, headsign_info, shapes, stop_seqs, ds_tz = cache._load_all(data_source_ids=None)
        self.assertIsInstance(route_info, dict)
        self.assertIsInstance(headsign_info, dict)
        self.assertIsInstance(shapes, dict)
        self.assertIsInstance(stop_seqs, dict)

    def test_load_all_with_filter(self):
        """_load_all([ids]) — filtered mode, activates WHERE t.route_id = ANY(...)."""
        # Find a data source that has routes (exercises the SQL filter path)
        ds_with_routes = None
        for ds in TransitDataSource.objects.filter(is_active=True):
            if Route.objects.filter(agency__data_source=ds).exists():
                ds_with_routes = ds
                break

        if ds_with_routes is None:
            # No data sources with routes in test DB — use a dummy ID
            # This still exercises the SQL with an empty ANY() array
            from geo.models import Agency
            dummy_ds = TransitDataSource.objects.create(
                name='Test DS', slug='test-ds', is_active=True,
            )
            dummy_agency = Agency.objects.create(
                name='Test Agency', data_source=dummy_ds, source_id='test-agency',
            )
            Route.objects.create(
                agency=dummy_agency, source_id='test-route',
                short_name='T1', route_type=3,
            )
            ds_id = dummy_ds.id
        else:
            ds_id = ds_with_routes.id

        cache = RouteCache()
        # Should not raise ProgrammingError
        route_info, headsign_info, shapes, stop_seqs, ds_tz = cache._load_all(
            data_source_ids=[ds_id]
        )
        self.assertIsInstance(route_info, dict)
        self.assertIsInstance(shapes, dict)

    def test_load_all_with_nonexistent_ids(self):
        """_load_all with IDs that match no routes — should return empty, not crash."""
        cache = RouteCache()
        route_info, headsign_info, shapes, stop_seqs, ds_tz = cache._load_all(
            data_source_ids=['01ZZZZZZZZZZZZZZZZZZZZZZZZ']
        )
        self.assertEqual(route_info, {})
        self.assertEqual(headsign_info, {})
        self.assertEqual(shapes, {})
        self.assertEqual(stop_seqs, {})


class TrackForwardSegmentSplitTest(TestCase):
    """SttProcessor._track_forward: travel time is split across ALL traversed
    segments (scheduled-duration weights, distance fallback) and each share is
    validated against its own segment — a multi-stop advance no longer writes
    the whole poll interval into the first segment only."""

    LAT0, LON = 38.700, -9.150

    def _processor(self, sched_offsets):
        from parahub.services.transit_rt import RouteCache, SttProcessor, StopPoint
        seq = [
            StopPoint(source_id=f"S{i}", lat=self.LAT0 + 0.003 * i, lon=self.LON,
                      sched_offset=(float(sched_offsets[i]) if sched_offsets[i] is not None else None))
            for i in range(len(sched_offsets))
        ]
        cache = RouteCache()
        cache.stop_seqs[("R1", 0)] = seq
        return SttProcessor(cache), seq

    def _advance(self, proc, pos_stops, idx, t_last, now):
        state = {"r": "R1", "d": "0", "st": "c", "idx": str(idx),
                 "t": str(t_last), "stall": "0"}
        return proc._track_forward(
            state, self.LAT0 + 0.003 * pos_stops, self.LON, "R1", "DS", now, 0)

    def test_single_advance_records_full_time(self):
        proc, _ = self._processor([0, 40, 120, 160, 280, 320])
        action, ns = self._advance(proc, pos_stops=1.2, idx=0, t_last=1000.0, now=1050.0)
        self.assertEqual(action, "segment")
        self.assertEqual(ns["idx"], "1")
        segs = ns.get("_segs")
        self.assertEqual(len(segs), 1)
        key, share = segs[0]
        self.assertTrue(key.endswith(":S0:S1"))
        self.assertAlmostEqual(share, 50.0)

    def test_skip_splits_by_scheduled_durations(self):
        # Segments S0-S1/S1-S2/S2-S3 scheduled 40/80/40 s; 90 s elapsed while
        # the bus advanced three stops => shares 22.5 / 45 / 22.5.
        proc, _ = self._processor([0, 40, 120, 160, 280, 320])
        action, ns = self._advance(proc, pos_stops=3.2, idx=0, t_last=1000.0, now=1090.0)
        self.assertEqual(action, "segment")
        self.assertEqual(ns["idx"], "3")
        segs = ns.get("_segs")
        self.assertEqual([k.split(":")[-2:] for k, _ in segs],
                         [["S0", "S1"], ["S1", "S2"], ["S2", "S3"]])
        self.assertAlmostEqual(segs[0][1], 22.5)
        self.assertAlmostEqual(segs[1][1], 45.0)
        self.assertAlmostEqual(segs[2][1], 22.5)

    def test_skip_falls_back_to_distance_weights(self):
        # One missing sched_offset in the span => equal-distance stops split
        # 90 s into three equal 30 s shares.
        proc, _ = self._processor([0, 40, None, 160, 280, 320])
        action, ns = self._advance(proc, pos_stops=3.2, idx=0, t_last=1000.0, now=1090.0)
        self.assertEqual(action, "segment")
        segs = ns.get("_segs")
        self.assertEqual(len(segs), 3)
        for _, share in segs:
            self.assertAlmostEqual(share, 30.0)

    def test_teleport_shares_filtered_by_min_travel(self):
        # 20 stops in 40 s => ~2 s per segment, all below STT_MIN_TRAVEL_S:
        # nothing recorded (previously wrote the whole 40 s into one segment).
        proc, _ = self._processor([60 * i for i in range(30)])
        action, ns = self._advance(proc, pos_stops=20.3, idx=0, t_last=1000.0, now=1040.0)
        self.assertEqual(action, "segment")
        self.assertEqual(ns["idx"], "20")
        self.assertNotIn("_segs", ns)


class TrackForwardStallSemanticsTest(TestCase):
    """Stall = consecutive polls moving AWAY from the next stop. A dwell or a
    long-segment traversal must not re-init (the old any-no-progress counter
    wiped the time anchor mid-dwell/mid-segment, truncating long recorded
    segment times to ~stall-window seconds)."""

    LAT0, LON = 38.700, -9.150

    def _processor(self):
        from parahub.services.transit_rt import RouteCache, SttProcessor, StopPoint
        seq = [StopPoint(source_id=f"S{i}", lat=self.LAT0 + 0.003 * i, lon=self.LON,
                         sched_offset=float(60 * i)) for i in range(6)]
        cache = RouteCache()
        cache.stop_seqs[("R1", 0)] = seq
        return SttProcessor(cache)

    def _poll(self, proc, prev_stops, cur_stops, stall):
        state = {"r": "R1", "d": "0", "st": "c", "idx": "2", "t": "1000",
                 "stall": str(stall),
                 "lat": str(self.LAT0 + 0.003 * prev_stops), "lon": str(self.LON)}
        return proc._track_forward(
            state, self.LAT0 + 0.003 * cur_stops, self.LON, "R1", "DS", 1090.0, stall)

    def test_dwell_keeps_stall_and_time_anchor(self):
        # Parked bus: d_next unchanged => stall stays, no re-init, `t` intact.
        action, ns = self._poll(self._processor(), prev_stops=2.1, cur_stops=2.1, stall=2)
        self.assertEqual(action, "update")
        self.assertEqual(ns["stall"], "2")
        self.assertEqual(ns["t"], "1000")

    def test_approaching_resets_stall(self):
        # Mid-segment progress toward the next stop (no transition yet)
        # clears the counter entirely.
        action, ns = self._poll(self._processor(), prev_stops=2.1, cur_stops=2.3, stall=2)
        self.assertEqual(action, "update")
        self.assertEqual(ns["stall"], "0")
        self.assertEqual(ns["t"], "1000")

    def test_moving_away_still_reinits(self):
        # Third consecutive away-move => direction re-resolved, time anchor
        # reset (this is the wrong-direction case stall exists for).
        action, ns = self._poll(self._processor(), prev_stops=2.1, cur_stops=1.9, stall=2)
        self.assertEqual(action, "update")
        self.assertEqual(ns["t"], str(1090.0))


class TrackForwardDwellSubtractionTest(TestCase):
    """Stationary time beyond STT_DWELL_KEEP_S accumulated in vprev `dw` is
    subtracted from the recorded segment time — a layover no longer bakes a
    giant observation into the FIFO — while normal boarding/timing dwells
    (<= keep threshold) stay in the observation."""

    LAT0, LON = 38.700, -9.150

    def _run(self, dw, t_last, now):
        from parahub.services.transit_rt import RouteCache, SttProcessor, StopPoint
        # ~1.1 km segments: the crawl-speed validation cap (seg_dist / 3 m/s)
        # must sit above the recorded times under test (220 s / 150 s).
        seq = [StopPoint(source_id=f"S{i}", lat=self.LAT0 + 0.01 * i, lon=self.LON,
                         sched_offset=float(180 * i)) for i in range(6)]
        cache = RouteCache()
        cache.stop_seqs[("R1", 0)] = seq
        proc = SttProcessor(cache)
        state = {"r": "R1", "d": "0", "st": "c", "idx": "0", "t": str(t_last),
                 "stall": "0", "dw": str(dw)}
        return proc._track_forward(
            state, self.LAT0 + 0.01 * 1.2, self.LON, "R1", "DS", now, 0)

    def test_layover_excess_subtracted(self):
        # 1300 s wall time, 1200 s of it parked: excess 1080 s subtracted,
        # recorded time = 220 s (drive + kept 120 s dwell), dw reset.
        action, ns = self._run(dw=1200.0, t_last=1000.0, now=2300.0)
        self.assertEqual(action, "segment")
        segs = ns.get("_segs")
        self.assertEqual(len(segs), 1)
        self.assertAlmostEqual(segs[0][1], 220.0)
        self.assertEqual(ns["dw"], "0")

    def test_normal_dwell_kept(self):
        # 90 s stationary (boarding/lights) is within the keep threshold:
        # recorded time is the full wall time.
        action, ns = self._run(dw=90.0, t_last=1000.0, now=1150.0)
        self.assertEqual(action, "segment")
        self.assertAlmostEqual(ns["_segs"][0][1], 150.0)


class PriorBucketTest(TestCase):
    """prior_bucket: hour x day-class id in feed-local time."""

    def test_day_classes(self):
        from zoneinfo import ZoneInfo

        from parahub.services.transit_rt import prior_bucket
        lisbon = ZoneInfo("Europe/Lisbon")
        # 2026-07-13 = Monday, 14:30 UTC = 15:30 Lisbon (WEST, UTC+1)
        self.assertEqual(prior_bucket(1783953000, lisbon), "15w")
        # 2026-07-18 = Saturday, 2026-07-19 = Sunday
        self.assertEqual(prior_bucket(1784385000, lisbon), "15s")
        self.assertEqual(prior_bucket(1784471400, lisbon), "15u")

    def test_local_midnight_rolls_day_class(self):
        from zoneinfo import ZoneInfo

        from parahub.services.transit_rt import prior_bucket
        helsinki = ZoneInfo("Europe/Helsinki")  # UTC+3 in summer
        # Friday 22:30 UTC = Saturday 01:30 in Helsinki:
        # the bucket must follow feed-local service time.
        self.assertEqual(prior_bucket(1784327400, helsinki), "01s")
        self.assertEqual(prior_bucket(1784327400, None), "22w")  # UTC fallback

    def test_zero_padding(self):
        from zoneinfo import ZoneInfo

        from parahub.services.transit_rt import prior_bucket
        # 2026-07-13 08:05 UTC = 09:05 Lisbon (Monday)
        self.assertEqual(prior_bucket(1783929900, ZoneInfo("Europe/Lisbon")), "09w")
