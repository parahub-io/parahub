"""Shared ETA primitives for the STT (Segment Travel Time) engine.

Single source of truth for the two things every ETA reader needs to agree on:

1. **Segment travel-time estimation** — how long the bus takes between two
   adjacent stops. Observed traversals (Redis FIFO) are the truth when we have
   them; otherwise we fall back to the GTFS *scheduled* segment duration scaled
   by the route's current observed delay, and only to a flat constant when even
   the schedule is unknown. (Replaces the old flat 90 s fallback, which made
   unobserved stretches read as crude `n×90 s` guesses.)

2. **Vehicle origin resolution** — which stop the ETA chain starts from. This is
   anchored to the feed/displayed snapped stop (`sid`, what drives the on-map
   icon), NOT the internal STT `idx`. The two can drift by a stop or two; when
   they do, the stop STT thinks the bus is *at* gets no forward ETA while the
   icon sits elsewhere, leaving a gap that falls back to the static schedule —
   the "stuck, un-recalculated" stop. Anchoring on `sid` keeps the live block
   contiguous and the ETA origin consistent with what the user sees.

These are pure functions over already-fetched data, so both the async WS
consumer (`parahub/consumers/transit.py`) and the sync REST endpoints
(`geo/endpoints/transit.py`) call the exact same logic.
"""
from __future__ import annotations

import orjson

# Last-resort per-segment time when there is neither an observation nor a
# scheduled duration (e.g. a stop missing from the representative trip).
ETA_DEFAULT_SEGMENT_S = 90.0

# Bayesian shrinkage: an observed segment average is blended toward its
# scheduled duration as if the schedule were `ETA_PRIOR_STRENGTH` extra
# observations. With 10 samples the schedule barely moves the estimate; with 1
# noisy sample it pulls it back toward a sane prior.
ETA_PRIOR_STRENGTH = 3.0

# The route-wide observed/scheduled delay factor (applied to *unobserved*
# segments) is clamped so a single weird segment can't blow up the whole tail.
ETA_FACTOR_MIN = 0.5
ETA_FACTOR_MAX = 2.0
# Need at least this many observed-and-scheduled segments before we trust a
# delay factor; otherwise stay at 1.0 (pure schedule).
ETA_FACTOR_MIN_SEGMENTS = 2

# Zombie dwell grace: a zombie-flagged bus (no movement > ~2 min) parked less
# than this in total still contributes ETAs, provided its feed sid agrees with
# the STT idx (±ZOMBIE_SID_IDX_TOL). Timing-point dwells run 2-5 min and are
# live buses; suppressing them blanks the route page mid-trip. The cap bounds
# the optimism error (ETA assumes departure now) and cuts off layovers; the
# sid-consistency check is what excludes the stale-sid bogus chains (operators
# report the next trip's origin during layover, observed ~25 stops off).
ZOMBIE_ETA_GRACE_S = 300.0
ZOMBIE_SID_IDX_TOL = 1


def parse_rstops(raw):
    """Parse a ``transit:rstops:{route}:{dir}`` snapshot.

    Each entry is ``[source_id, lat, lon]`` or, on newer snapshots,
    ``[source_id, lat, lon, sched_offset_s]`` where ``sched_offset_s`` is the
    cumulative scheduled seconds from the first stop.

    Returns ``(source_ids, coords, sched_offsets)`` or ``None`` when the
    snapshot is missing/too short. ``sched_offsets`` is a list aligned with the
    stops (``float`` or ``None`` per stop) — all ``None`` on legacy snapshots
    that predate scheduled offsets, which the estimators degrade gracefully on.
    """
    if not raw:
        return None
    try:
        arr = orjson.loads(raw)
    except (orjson.JSONDecodeError, TypeError, ValueError):
        return None
    if not arr or len(arr) < 2:
        return None
    source_ids = [s[0] for s in arr]
    coords = [(s[1], s[2]) for s in arr]
    sched_offsets = [
        (s[3] if len(s) > 3 and isinstance(s[3], (int, float)) else None)
        for s in arr
    ]
    return source_ids, coords, sched_offsets


def _scheduled_segment_durations(sched_offsets, n_seg):
    """Per-segment scheduled seconds from cumulative offsets (``None`` if either
    endpoint offset is unknown or non-positive)."""
    sched_seg = [None] * n_seg
    if not sched_offsets or len(sched_offsets) < n_seg + 1:
        return sched_seg
    for i in range(n_seg):
        a, b = sched_offsets[i], sched_offsets[i + 1]
        if a is not None and b is not None:
            d = float(b) - float(a)
            if d > 0:
                sched_seg[i] = d
    return sched_seg


def segment_infos(seg_observations, sched_offsets):
    """Estimate each segment's travel time with provenance.

    ``seg_observations[i]`` is the list of observed traversal times (str/float,
    possibly empty) for the segment from stop ``i`` to ``i+1``. ``sched_offsets``
    is the per-stop cumulative scheduled-seconds list from :func:`parse_rstops`.

    Returns ``list[dict]`` (length ``len(seg_observations)``), each:
    ``{avg: float, samples: int, observed: bool, source: 'observed'|'scheduled'|'default'}``.
    """
    n_seg = len(seg_observations)
    sched_seg = _scheduled_segment_durations(sched_offsets, n_seg)

    obs_mean = [None] * n_seg
    obs_n = [0] * n_seg
    for i, vals in enumerate(seg_observations):
        if vals:
            times = [float(v) for v in vals]
            obs_n[i] = len(times)
            obs_mean[i] = sum(times) / len(times)

    # Route-wide delay factor from segments that are both observed and
    # scheduled — lets a couple of live observations calibrate the schedule-only
    # stretches ahead (a bus running late stays late).
    num = den = 0.0
    cnt = 0
    for i in range(n_seg):
        if obs_mean[i] is not None and sched_seg[i] is not None:
            num += obs_mean[i]
            den += sched_seg[i]
            cnt += 1
    factor = 1.0
    if den > 0 and cnt >= ETA_FACTOR_MIN_SEGMENTS:
        factor = min(ETA_FACTOR_MAX, max(ETA_FACTOR_MIN, num / den))

    out = []
    for i in range(n_seg):
        if obs_mean[i] is not None:
            if sched_seg[i] is not None:
                k = ETA_PRIOR_STRENGTH
                avg = (obs_n[i] * obs_mean[i] + k * sched_seg[i]) / (obs_n[i] + k)
            else:
                avg = obs_mean[i]
            out.append({'avg': avg, 'samples': obs_n[i], 'observed': True, 'source': 'observed'})
        elif sched_seg[i] is not None:
            out.append({'avg': sched_seg[i] * factor, 'samples': 0, 'observed': False, 'source': 'scheduled'})
        else:
            out.append({'avg': ETA_DEFAULT_SEGMENT_S, 'samples': 0, 'observed': False, 'source': 'default'})
    return out


def segment_averages(seg_observations, sched_offsets):
    """Convenience: just the ``avg`` per segment (see :func:`segment_infos`)."""
    return [s['avg'] for s in segment_infos(seg_observations, sched_offsets)]


def build_index_map(source_ids):
    """``source_id -> first index`` (first occurrence wins for the rare case of a
    stop repeated in a sequence)."""
    m = {}
    for i, s in enumerate(source_ids):
        if s not in m:
            m[s] = i
    return m


def resolve_origin(sid, stt_idx, index_map):
    """Where the ETA chain starts for one vehicle.

    Prefer the feed/displayed snapped stop ``sid`` (what the on-map icon shows)
    so the live block stays contiguous and the origin matches what the user
    sees; fall back to the STT ``idx`` when ``sid`` is missing or not on this
    sequence.
    """
    if sid:
        i = index_map.get(sid)
        if i is not None:
            return i
    return stt_idx


def zombie_keeps_eta(now_ts, move_ts, sid, stt_idx, index_map):
    """Whether a zombie-flagged vehicle still contributes ETAs.

    True only for a short dwell (parked < ``ZOMBIE_ETA_GRACE_S`` total, measured
    from the vprev ``mt`` last-movement timestamp) whose feed ``sid`` agrees
    with the STT ``stt_idx`` (±``ZOMBIE_SID_IDX_TOL``) — see the constants'
    comment. Anything unverifiable (no ``mt``, no ``sid``, sid not on this
    sequence) is excluded: only the readers' primary path calls this, where
    both vprev and vdata are at hand; fallback paths keep the strict skip.

    A zombie parked at the direction's FIRST stop gets no grace: that is a
    terminal layover, not a mid-trip timing point — the trip hasn't started,
    and an ETA chain from there ("departs right now") systematically undercuts
    the scheduled departure that the static-schedule badge would show instead.
    """
    if not move_ts or (now_ts - move_ts) > ZOMBIE_ETA_GRACE_S:
        return False
    if not sid:
        return False
    i = index_map.get(sid)
    if i is None or abs(i - stt_idx) > ZOMBIE_SID_IDX_TOL:
        return False
    return i != 0


def cumulative_min_etas(source_ids, seg_avg, origins):
    """Min ETA (seconds) to each downstream stop across all vehicles.

    ``origins`` is an iterable of per-vehicle origin indices (from
    :func:`resolve_origin`). For a vehicle at index ``v`` the ETA to stop ``j>v``
    is ``sum(seg_avg[v..j-1])``. Returns ``{stop_source_id: int seconds}`` for
    stops strictly ahead of at least one vehicle.
    """
    n = len(source_ids)
    etas = {}
    for v in origins:
        if v is None or v < 0 or v >= n - 1:
            continue
        cum = 0.0
        for j in range(v, n - 1):
            cum += seg_avg[j]
            s = source_ids[j + 1]
            if s not in etas or cum < etas[s]:
                etas[s] = int(cum)
    return etas
