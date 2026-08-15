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

import math
import statistics
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

import orjson

# Last-resort per-segment time when there is neither an observation nor a
# scheduled duration (e.g. a stop missing from the representative trip).
ETA_DEFAULT_SEGMENT_S = 90.0

# Bayesian shrinkage: an observed segment estimate (FIFO median) is blended
# toward its scheduled duration as if the schedule were `ETA_PRIOR_STRENGTH`
# extra observations. With 10 samples the schedule barely moves the estimate;
# with 1 noisy sample it pulls it back toward a sane prior.
ETA_PRIOR_STRENGTH = 3.0

# Historical segment priors (written by the STT daemon per traversal into
# `transit:prior:{ds}:{from}:{to}` hashes; see prior_bucket): a bucket needs at
# least this many recorded traversals before its geometric mean is trusted as
# an estimate — below that, thin buckets (fresh feeds, night hours, weekends
# right after a Redis wipe) fall through to the scheduled path unchanged.
ETA_PRIOR_BUCKET_MIN_N = 5
# A bucket's evidence weight in the blend is capped as if it were one full
# FIFO of live observations — months of accumulation must not make the prior
# immune to the schedule (route detours, seasonal timetable changes).
ETA_PRIOR_MAX_WEIGHT = 10.0

# Redis TTL for the per-segment prior hashes (refreshed on every write, and on
# snapshot restore — see the sync_transit_priors command).
STT_PRIOR_TTL = 120 * 86400

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

# A vehicle whose last >10m move is older than this is "not moving right now";
# combined with the accumulated-dwell check in parked_beyond_grace it separates
# "driving between stops" from "parked mid-route with GPS micro-moves".
PARKED_MOVE_RECENT_S = 60.0

# A vprev state is only evidence of a live vehicle for as long as the poller
# keeps refreshing it. The RT poller hands STT only the vehicles whose feed
# timestamp is within 180s (the cutoff every display path uses) and evicts the
# rest from `transit:vdata`, while their vprev key lingers for the remainder of
# its TTL. Such a frozen state must not seed an ETA chain: the icon is already
# gone, and every guard that would have caught it (the zombie flag `z`, the
# snapped `sid`) lives in the vdata record that was just evicted — so without
# this the vehicle becomes MORE trusted the staler it gets, painting live ETAs
# for a bus that is nowhere on the page.
STT_STATE_MAX_AGE_S = 180.0


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


def prior_bucket(now: float, tz=None) -> str:
    """Hour-of-day × day-class bucket id for segment-prior aggregates.

    ``'{HH}{w|s|u}'`` in feed-local time (w=Mon-Fri, s=Sat, u=Sun) — transit
    traffic regimes follow service-local clock, not server UTC.
    """
    ldt = datetime.fromtimestamp(now, tz or dt_timezone.utc)
    wd = ldt.weekday()
    dc = 'w' if wd < 5 else ('s' if wd == 5 else 'u')
    return f'{ldt.hour:02d}{dc}'


_zoneinfo_cache: dict[str, ZoneInfo | None] = {}


def bucket_for(tz_name, now: float) -> str:
    """:func:`prior_bucket` for a timezone *name* (the readers' entry point).

    The daemon publishes each feed's GTFS ``agency_timezone`` as
    ``transit:tz:{ds_id}``; readers pass that value (str/bytes/None) here.
    Missing or unresolvable names fall back to UTC — wrong-bucket priors for a
    non-UTC feed only until the daemon's next cache refresh republishes the key.
    """
    if isinstance(tz_name, bytes):
        tz_name = tz_name.decode('utf-8', 'replace')
    tz = None
    if tz_name:
        if tz_name not in _zoneinfo_cache:
            try:
                _zoneinfo_cache[tz_name] = ZoneInfo(tz_name)
            except Exception:
                _zoneinfo_cache[tz_name] = None
        tz = _zoneinfo_cache[tz_name]
    return prior_bucket(now, tz)


def queue_prior_reads(pipe, stt_keys, bucket: str):
    """Queue one HMGET per segment for the historical-prior bucket, mirroring a
    list of ``transit:stt:*`` FIFO keys already queued on the same pipeline.

    Callers slice the pipeline result with the same ranges they use for the
    FIFO half and feed the rows to :func:`parse_priors`.
    """
    nf, lf = f'{bucket}:n', f'{bucket}:l'
    for sk in stt_keys:
        pipe.hmget('transit:prior:' + sk[len('transit:stt:'):], nf, lf)


def parse_priors(rows):
    """HMGET rows → per-segment ``(n, sum_ln)`` tuples (``None`` when the
    bucket is absent/corrupt). Accepts str or bytes values."""
    out = []
    for row in rows:
        try:
            n, sum_ln = int(row[0]), float(row[1])
        except (TypeError, ValueError, IndexError):
            out.append(None)
            continue
        out.append((n, sum_ln) if n > 0 else None)
    return out


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


def segment_infos(seg_observations, sched_offsets, seg_priors=None):
    """Estimate each segment's travel time with provenance.

    ``seg_observations[i]`` is the list of observed traversal times (str/float,
    possibly empty) for the segment from stop ``i`` to ``i+1``. ``sched_offsets``
    is the per-stop cumulative scheduled-seconds list from :func:`parse_rstops`.
    ``seg_priors[i]`` (optional, from :func:`parse_priors`) is the historical
    ``(n, sum_ln)`` bucket for the current hour × day-class.

    Live observations always win. The prior only replaces the *scheduled*
    estimate on segments with no live FIFO — exactly the 10–30 min horizon
    where chains run through stretches no recent vehicle has traversed. Its
    geometric mean ``exp(sum_ln/n)`` (≈ the median for lognormal travel times)
    is blended toward ``schedule × route delay factor`` with the same
    pseudo-count scheme as the observed branch, so a thin bucket leans on the
    schedule and a dense one dominates it — but never fully (see
    ``ETA_PRIOR_MAX_WEIGHT``).

    The observed estimate is the FIFO **median**, not the mean: recorded times
    include dwell at the departure stop, so an idiosyncratic layover (driver
    break, 15-25 min parked mid-route) lands one huge observation that would
    drag a mean — and the route delay factor derived from it — for the next
    ten traversals. The median ignores such minority outliers yet still tracks
    a real regime change (a jam, a timing-point dwell every bus makes) once it
    is the majority of the window — which a fixed rejection threshold cannot
    distinguish.

    Returns ``list[dict]`` (length ``len(seg_observations)``), each:
    ``{avg: float, samples: int, observed: bool, source: 'observed'|'scheduled'|'default'}``.
    """
    n_seg = len(seg_observations)
    sched_seg = _scheduled_segment_durations(sched_offsets, n_seg)

    obs_med = [None] * n_seg
    obs_n = [0] * n_seg
    for i, vals in enumerate(seg_observations):
        if vals:
            times = [float(v) for v in vals]
            obs_n[i] = len(times)
            obs_med[i] = statistics.median(times)

    # Route-wide delay factor from segments that are both observed and
    # scheduled — lets a couple of live observations calibrate the schedule-only
    # stretches ahead (a bus running late stays late). Built from the per-segment
    # medians so one layover-inflated segment cannot peg every unobserved
    # segment at the clamp.
    num = den = 0.0
    cnt = 0
    for i in range(n_seg):
        if obs_med[i] is not None and sched_seg[i] is not None:
            num += obs_med[i]
            den += sched_seg[i]
            cnt += 1
    factor = 1.0
    if den > 0 and cnt >= ETA_FACTOR_MIN_SEGMENTS:
        factor = min(ETA_FACTOR_MAX, max(ETA_FACTOR_MIN, num / den))

    out = []
    for i in range(n_seg):
        if obs_med[i] is not None:
            if sched_seg[i] is not None:
                k = ETA_PRIOR_STRENGTH
                avg = (obs_n[i] * obs_med[i] + k * sched_seg[i]) / (obs_n[i] + k)
            else:
                avg = obs_med[i]
            out.append({'avg': avg, 'samples': obs_n[i], 'observed': True, 'source': 'observed'})
        elif (pri := seg_priors[i] if seg_priors and i < len(seg_priors) else None) and pri[0] >= ETA_PRIOR_BUCKET_MIN_N:
            gmean = math.exp(pri[1] / pri[0])
            if sched_seg[i] is not None:
                w = min(float(pri[0]), ETA_PRIOR_MAX_WEIGHT)
                avg = (w * gmean + ETA_PRIOR_STRENGTH * sched_seg[i] * factor) / (w + ETA_PRIOR_STRENGTH)
            else:
                avg = gmean
            out.append({'avg': avg, 'samples': pri[0], 'observed': False, 'source': 'prior'})
        elif sched_seg[i] is not None:
            out.append({'avg': sched_seg[i] * factor, 'samples': 0, 'observed': False, 'source': 'scheduled'})
        else:
            out.append({'avg': ETA_DEFAULT_SEGMENT_S, 'samples': 0, 'observed': False, 'source': 'default'})
    return out


def segment_averages(seg_observations, sched_offsets, seg_priors=None):
    """Convenience: just the ``avg`` per segment (see :func:`segment_infos`)."""
    return [s['avg'] for s in segment_infos(seg_observations, sched_offsets, seg_priors)]


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


def _seg_dist(lat1, lon1, lat2, lon2):
    """Cheap local equirectangular distance in metres. Adequate for the
    intra-segment progress *ratio* below, where the earth-radius scale cancels."""
    mlat = math.radians((lat1 + lat2) * 0.5)
    dx = math.radians(lon2 - lon1) * math.cos(mlat)
    dy = math.radians(lat2 - lat1)
    return math.hypot(dx, dy) * 6371000.0


def remaining_segment_fraction(bus_lat, bus_lon, from_coord, to_coord):
    """Fraction of the current (origin -> next stop) segment still AHEAD of the
    vehicle, in ``[0.0, 1.0]``.

    The ETA chain charges the full average travel time of the origin segment,
    but a bus already part-way through it only has the leftover portion to go.
    Charging the whole segment is a systematic near-stop over-estimate (the bus
    arrives sooner than the plain segment sum predicts). Scaling the origin
    segment by this fraction removes it.

    Estimated from the live position as
    ``d(bus, next) / (d(bus, from) + d(bus, next))`` — a straight-line distance
    ratio, not a polyline projection: it needs no segment shape and is robust to
    lateral GPS offset (an off-line fix just pulls the ratio gently toward 0.5).
    Bounded to ``[0, 1]`` by construction, so it can only *reduce* the origin
    segment, never inflate it; it assumes roughly uniform speed across the
    segment (distance fraction ~= time fraction).

    Returns ``1.0`` (charge the whole segment — the pre-correction behaviour)
    whenever any coordinate is missing or degenerate, so callers degrade
    gracefully to the plain segment sum.
    """
    if bus_lat is None or bus_lon is None or not from_coord or not to_coord:
        return 1.0
    try:
        blat, blon = float(bus_lat), float(bus_lon)
        flat, flon = float(from_coord[0]), float(from_coord[1])
        tlat, tlon = float(to_coord[0]), float(to_coord[1])
    except (TypeError, ValueError, IndexError):
        return 1.0
    d_from = _seg_dist(blat, blon, flat, flon)
    d_next = _seg_dist(blat, blon, tlat, tlon)
    total = d_from + d_next
    if total <= 0:
        return 1.0
    return d_next / total


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


def stt_state_is_live(now_ts, poll_ts):
    """Whether a vprev state was refreshed by a recent poll — see
    ``STT_STATE_MAX_AGE_S``.

    ``poll_ts`` is the vprev ``pt`` field, stamped on every STT write path
    (initialisation included), so it marks the last poll that saw this vehicle
    *fresh*. A missing or zero value reads as NOT live: a live ETA badge needs
    positive evidence of a current fix, and a state written before the field
    existed expires within ``STT_VPREV_TTL`` anyway.
    """
    if not poll_ts:
        return False
    try:
        return (now_ts - float(poll_ts)) <= STT_STATE_MAX_AGE_S
    except (TypeError, ValueError):
        return False


def parked_beyond_grace(now_ts, move_ts, dwell_s):
    """Whether a vehicle is parked past the ETA grace within its current
    segment window AND not moving right now — such a bus must not seed an ETA
    chain: the chain assumes departure NOW, undercutting reality by the whole
    remaining layover (observed as stops_away=1 predictions arriving many
    minutes early). The accumulated per-segment dwell ``dw`` (maintained by the
    STT writer, reset on stop transition) is immune to the >10m GPS micro-moves
    that keep resetting the zombie clock ``mt`` — which is exactly how these
    buses dodge the zombie flag. The move-recency condition keeps a bus that
    has just PULLED OUT of a long dwell chaining normally while its ``dw``
    hasn't reset yet (no transition until the next bisector crossing).

    Missing data (legacy vprev without ``dw``, no ``mt``) reads as not parked.
    """
    if not move_ts or not dwell_s:
        return False
    return dwell_s > ZOMBIE_ETA_GRACE_S and (now_ts - move_ts) > PARKED_MOVE_RECENT_S


def origin_with_fraction(origin, bus_lat, bus_lon, coords):
    """Build a ``(origin, remaining_fraction)`` pair for
    :func:`cumulative_min_etas` from a vehicle's live position.

    Degrades to fraction ``1.0`` (charge the whole current segment) at the last
    stop or when coordinates are missing, so the result can be passed straight
    through. See :func:`remaining_segment_fraction` for the fraction itself.
    """
    if origin is None or origin < 0 or origin + 1 >= len(coords):
        return (origin, 1.0)
    return (origin, remaining_segment_fraction(bus_lat, bus_lon, coords[origin], coords[origin + 1]))


def cumulative_min_etas(source_ids, seg_avg, origins):
    """Min ETA (seconds) to each downstream stop across all vehicles.

    ``origins`` is an iterable of per-vehicle origins (from
    :func:`resolve_origin`). Each entry is either a bare index ``v`` or a
    ``(v, first_seg_fraction)`` pair; the fraction (0..1, see
    :func:`remaining_segment_fraction`) scales the vehicle's current segment by
    the portion still ahead of it — the same near-stop correction the
    single-chain readers apply. A bare index means fraction ``1.0`` (whole
    current segment).

    For a vehicle at index ``v`` the ETA to stop ``j>v`` is
    ``frac*seg_avg[v] + sum(seg_avg[v+1..j-1])``. Returns
    ``{stop_source_id: int seconds}`` for stops strictly ahead of at least one
    vehicle.
    """
    n = len(source_ids)
    etas = {}
    for item in origins:
        if isinstance(item, tuple):
            v, frac = item
        else:
            v, frac = item, 1.0
        if v is None or v < 0 or v >= n - 1:
            continue
        if frac is None:
            frac = 1.0
        cum = 0.0
        for j in range(v, n - 1):
            cum += seg_avg[j] * (frac if j == v else 1.0)
            s = source_ids[j + 1]
            if s not in etas or cum < etas[s]:
                etas[s] = int(cum)
    return etas
