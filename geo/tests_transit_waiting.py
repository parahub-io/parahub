"""
Unit tests for parahub/services/transit_waiting.py — the pure decoders shared
by the sync REST service, both WS consumers and the RT daemon, plus input
normalization and identity derivation, and the push floor those consumers share.

Pure functions, no DB/Redis — SimpleTestCase. The counting semantics here have
already regressed once in the wild (co-located pole double count, caught only
by manual verification), so the line-weighted vs per-person distinction gets
explicit contrast tests.
"""

import asyncio
from unittest import IsolatedAsyncioTestCase

import orjson

from django.test import SimpleTestCase

from parahub.consumers.push_floor import TrailingFloor

from parahub.services.transit_waiting import (
    ACTIVE_WINDOW,
    LEASE,
    MAX_ROUTES,
    decode_route_hash,
    decode_stop_hash,
    decode_stop_people,
    identity_for,
    normalize_lines,
)

NOW = 1_000_000.0


def _route_entry(beat, direction=0, stop='S1'):
    """A member of `transit:waiting:r:{ds}:{route}`."""
    return orjson.dumps({'b': beat, 'd': direction, 's': stop}).decode()


def _stop_entry(beat, lines):
    """A member of `transit:waiting:s:{ds}:{stop}`; `lines` = [[route, dir], ...]."""
    return orjson.dumps({'b': beat, 'rd': lines}).decode()


class NormalizeLinesTest(SimpleTestCase):
    def test_accepts_dicts_and_pairs(self):
        self.assertEqual(
            normalize_lines([{'route': 'R1', 'direction': 1}, ('R2', 0), ['R3', 1]]),
            [('R1', 1), ('R2', 0), ('R3', 1)],
        )

    def test_direction_coerced_to_binary(self):
        # Anything that is not exactly 1 becomes 0 — the two values the whole
        # transit pipeline uses.
        self.assertEqual(
            normalize_lines([('R1', '1'), ('R2', 2), ('R3', None), ('R4', 'x')]),
            [('R1', 1), ('R2', 0), ('R3', 0), ('R4', 0)],
        )

    def test_dedup_and_cap(self):
        lines = [(f'R{i}', 0) for i in range(MAX_ROUTES + 3)]
        self.assertEqual(len(normalize_lines(lines + lines)), MAX_ROUTES)
        self.assertEqual(normalize_lines([('R1', 0), ('R1', 0)]), [('R1', 0)])
        # Same route, other direction is a different line.
        self.assertEqual(normalize_lines([('R1', 0), ('R1', 1)]), [('R1', 0), ('R1', 1)])

    def test_garbage_dropped(self):
        self.assertEqual(normalize_lines('not-a-list'), [])
        self.assertEqual(normalize_lines([('R1',), 42, None, {'direction': 1}]), [])
        self.assertEqual(normalize_lines([('', 0), ('x' * 101, 0)]), [])


class IdentityForTest(SimpleTestCase):
    def test_profile_wins_over_device(self):
        self.assertEqual(identity_for('P1', 'a' * 16), 'p:P1')

    def test_device_is_hashed_and_stable(self):
        a = identity_for(None, 'a' * 16)
        b = identity_for(None, 'a' * 16)
        c = identity_for(None, 'b' * 16)
        self.assertTrue(a.startswith('d:'))
        self.assertNotIn('a' * 16, a)  # never the raw id
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_device_length_bounds(self):
        self.assertIsNone(identity_for(None, 'short'))
        self.assertIsNone(identity_for(None, 'x' * 129))
        self.assertIsNone(identity_for(None, None))
        self.assertIsNone(identity_for(None, ''))


class DecodeRouteHashTest(SimpleTestCase):
    def test_counts_by_direction_and_stop(self):
        counts, stale = decode_route_hash({
            'i1': _route_entry(NOW, 0, 'S1'),
            'i2': _route_entry(NOW, 0, 'S1'),
            'i3': _route_entry(NOW, 1, 'S2'),
        }, now=NOW)
        self.assertEqual(stale, [])
        self.assertEqual(counts['0']['S1'], {'n': 2, 'active': 2})
        self.assertEqual(counts['1']['S2'], {'n': 1, 'active': 1})

    def test_active_window_boundary(self):
        counts, stale = decode_route_hash({
            'fresh': _route_entry(NOW - ACTIVE_WINDOW),        # inclusive: active
            'dimmed': _route_entry(NOW - ACTIVE_WINDOW - 1),   # pocketed, still there
        }, now=NOW)
        self.assertEqual(stale, [])
        self.assertEqual(counts['0']['S1'], {'n': 2, 'active': 1})

    def test_lease_boundary_reports_stale(self):
        counts, stale = decode_route_hash({
            'held': _route_entry(NOW - LEASE),                 # inclusive: still held
            'gone': _route_entry(NOW - LEASE - 1),
        }, now=NOW)
        self.assertEqual(stale, ['gone'])
        self.assertEqual(counts['0']['S1'], {'n': 1, 'active': 0})

    def test_garbage_reports_stale(self):
        counts, stale = decode_route_hash({'bad': 'not json'}, now=NOW)
        self.assertEqual(counts, {})
        self.assertEqual(stale, ['bad'])

    def test_empty_and_none(self):
        self.assertEqual(decode_route_hash({}, now=NOW), ({}, []))
        self.assertEqual(decode_route_hash(None, now=NOW), ({}, []))


class DecodeStopHashTest(SimpleTestCase):
    def test_multi_line_marker_counts_once_per_line(self):
        # "The 13 or the 15, whichever comes" — one person, two board rows:
        # that is what "how many are waiting for MY route" means.
        rows, stale = decode_stop_hash({
            'i1': _stop_entry(NOW, [['13', 0], ['15', 0]]),
        }, now=NOW)
        self.assertEqual(stale, [])
        self.assertEqual(rows, [
            {'route': '13', 'direction': 0, 'n': 1, 'active': 1},
            {'route': '15', 'direction': 0, 'n': 1, 'active': 1},
        ])

    def test_stable_sort_and_direction_split(self):
        rows, _ = decode_stop_hash({
            'i1': _stop_entry(NOW - ACTIVE_WINDOW - 1, [['15', 1]]),
            'i2': _stop_entry(NOW, [['13', 0]]),
            'i3': _stop_entry(NOW, [['13', 1]]),
        }, now=NOW)
        self.assertEqual(rows, [
            {'route': '13', 'direction': 0, 'n': 1, 'active': 1},
            {'route': '13', 'direction': 1, 'n': 1, 'active': 1},
            {'route': '15', 'direction': 1, 'n': 1, 'active': 0},
        ])

    def test_malformed_pairs_skipped(self):
        rows, stale = decode_stop_hash({
            'i1': _stop_entry(NOW, [['13'], 'junk', ['13', 0, 9], ['15', 1]]),
        }, now=NOW)
        self.assertEqual(stale, [])
        self.assertEqual(rows, [{'route': '15', 'direction': 1, 'n': 1, 'active': 1}])


class DecodeStopPeopleTest(SimpleTestCase):
    def test_multi_line_marker_is_one_person(self):
        # The map-pin contrast to decode_stop_hash: same hash, but a human
        # waiting for two lines is ONE human standing at the pole.
        raw = {'i1': _stop_entry(NOW, [['13', 0], ['15', 0]])}
        people, active, stale = decode_stop_people(raw, now=NOW)
        self.assertEqual((people, active, stale), (1, 1, []))
        rows, _ = decode_stop_hash(raw, now=NOW)
        self.assertEqual(sum(r['n'] for r in rows), 2)  # line-weighted view

    def test_active_split_and_stale(self):
        people, active, stale = decode_stop_people({
            'fresh': _stop_entry(NOW, [['13', 0]]),
            'dimmed': _stop_entry(NOW - ACTIVE_WINDOW - 1, [['13', 0]]),
            'gone': _stop_entry(NOW - LEASE - 1, [['13', 0]]),
            'bad': 'not json',
        }, now=NOW)
        self.assertEqual((people, active), (2, 1))
        self.assertEqual(sorted(stale), ['bad', 'gone'])


class TrailingFloorTest(IsolatedAsyncioTestCase):
    """The push floor shared by both WS consumers.

    What matters is not the rate — it is that the LAST state always lands. A
    plain floor drops whichever nudge came last, which is precisely the one
    everybody should end up seeing, and leaves every watcher stale until an
    unrelated tick refreshes them.
    """

    def setUp(self):
        self.sent = []

    async def _send(self):
        # Reads its data at fire time, like the real senders do.
        self.sent.append(self.state)

    def _floor(self, interval=0.05):
        self.state = 'a'
        return TrailingFloor(interval, self._send, 'test')

    async def test_first_nudge_is_immediate(self):
        floor = self._floor()
        await floor.nudge()
        self.assertEqual(self.sent, ['a'])

    async def test_burst_collapses_and_carries_the_final_state(self):
        floor = self._floor(interval=0.05)
        await floor.nudge()                     # goes out at once
        for value in ('b', 'c', 'd'):
            self.state = value
            await floor.nudge()                 # inside the floor → collapse
        self.assertEqual(self.sent, ['a'])
        await asyncio.sleep(0.12)
        # One trailing send, and it carries 'd' — not 'b', not 'c'.
        self.assertEqual(self.sent, ['a', 'd'])

    async def test_quiet_period_is_not_delayed(self):
        floor = self._floor(interval=0.02)
        await floor.nudge()
        await asyncio.sleep(0.05)
        self.state = 'b'
        await floor.nudge()
        self.assertEqual(self.sent, ['a', 'b'])  # second one immediate too

    async def test_cancel_drops_the_queued_send(self):
        floor = self._floor(interval=0.05)
        await floor.nudge()
        self.state = 'b'
        await floor.nudge()
        floor.cancel()
        await asyncio.sleep(0.12)
        self.assertEqual(self.sent, ['a'])

    async def test_failing_send_does_not_wedge_the_floor(self):
        """A send raising on the immediate path reaches the caller — the pub/sub
        dispatcher logs and moves on — and a trailing one is swallowed. Either
        way the floor stays usable rather than stuck holding a dead task."""
        async def boom():
            raise RuntimeError('socket closed')

        self.state = 'a'
        floor = TrailingFloor(0.02, boom, 'test')
        with self.assertRaises(RuntimeError):
            await floor.nudge()
        await floor.nudge()          # queued behind the floor, fails quietly
        await asyncio.sleep(0.06)
        self.assertIsNone(floor._task)

        floor._send = self._send
        self.state = 'b'
        await floor.nudge()
        self.assertEqual(self.sent, ['b'])
