"""Backtest the STT ETA engine against Carris Metropolitana ground truth.

CM's ``/v2/arrivals/by_stop/{stop}`` is a whole-service-day archive of every
departure at a stop, each carrying three clocks:

  * ``scheduled_arrival`` — the timetable.
  * ``estimated_arrival`` — CM's own SAE prediction (frozen near arrival).
  * ``observed_arrival``  — ground truth: the vehicle's actual passage time.

We never consumed this feed (we only read ``/v2/vehicles``), so our STT ETA
engine has never been measured against truth. This command does that, three
ways, always comparing predicted-minus-observed (positive = predicted late,
negative = predicted early):

  cm-baseline  Retrospective, no live capture. For departures that already
               carry ``observed``, how far off was CM's own ``estimated``?
               Establishes the bar our position-only engine is measured
               against. Caveat: the archived estimate is the value near
               arrival (short, unknown lead), so this is CM's *floor*, not
               its accuracy at the 5-10 min lead a live board consumes.

  collect      Forward capture over a live window. Every --interval seconds,
               for each monitored stop, records (a) our STT prediction per
               approaching vehicle (predicted arrival = now + eta), read from
               the real /eta/ endpoint so it matches what users see,
               (b) CM's live ``estimated`` for upcoming departures at the same
               moment, and (c) CM's ``observed`` inline -- logged once per
               departure as it settles -- so analyze needs no live harvest and
               replays identically. Appends JSONL to --out. Multi-hour windows
               MUST run as a transient systemd unit (a Bash-launched process
               freezes when the session idles) -- see PK/troubleshooting.md
               Long-Running Jobs.

  analyze      Joins a collect log to ``observed`` on (stop, trip_id) and
               reports error vs observed for our STT, CM's live estimate, and
               schedule-only, bucketed by actual lead. Prefers the ``observed``
               logged inline during collect (replayable, survives the archive's
               service-day rollover); stops with none fall back to a same-day
               live harvest.

Observed coverage is partial (0-75% per stop) and biased toward well-tracked
vehicles -- the same vehicles our STT tracks best -- so absolute numbers read
as "accuracy where truth exists", not over all service.

``observed_arrival`` is CM's own attribution and is provably corrupt at some
stops: it can be published while CM's own GPS still has the bus kilometres
away (loop patterns, e.g. line 4702 at Freeport Alcochete run 12-19 min of
city loop AFTER the record appears). Analyze therefore cross-checks every
observed against our raw GPS history (VehiclePositionHistory) and confirms,
corrects (re-times to the actual closest approach), or drops each pair --
both arms are scored against the same validated truth. Logs whose window has
already left GPS retention are scored against raw observed, with a warning.
"""
from __future__ import annotations

import json
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError

CM_API = "https://api.carrismetropolitana.pt/v2"
# Viação Alvorada / slug carris-metropolitana -- the CM TransitDataSource whose
# vehicles/trips/stops share source_ids byte-for-byte with the /v2 archive.
CM_DS_ID = "01KHH9S11PTVGCVQ7TAFJQNSGR"
# Agency our CM stops are imported under -- used to keep --auto stop picking to
# stops that exist in our DB (so the /eta/ endpoint can serve them). Our CM GTFS
# import is a partial subset of CM's live stop-id space, so many currently-active
# feed stop_ids are absent from our DB and cannot be predicted.
CM_AGENCY_NAME = "Viação Alvorada"
# Minimum observed coverage for a stop to be worth monitoring -- below this the
# ground truth is too sparse to join predictions against.
MIN_OBSERVED_COVERAGE = 0.30
# Minimum median stop_sequence -- terminals (origins, seq~1) have great observed
# coverage but nothing "approaches" them from earlier stops, so /eta/ is empty
# there. We want mid-route stops buses genuinely pass through.
MIN_MEDIAN_SEQ = 4
# |error| beyond this is a data glitch (wrong-trip match, feed gap), not a
# prediction error -- excluded from stats and reported separately.
OUTLIER_S = 1800
# Estimate/observed within this reads as CM converging estimate->observed at
# arrival (a degenerate ~0 error), reported apart so it can't flatter the MAE.
CONVERGED_S = 5

# Actual-lead buckets for analyze (seconds remaining when the prediction was made).
LEAD_BUCKETS = [(0, 120), (120, 300), (300, 600), (600, 1800)]

# Predicted-ETA micro-buckets: "when the board SAYS n seconds, what actually
# happens" -- the displayed-value view (the arriving-now cue reads the <=30s row).
PRED_BUCKETS = [(0, 30), (30, 60), (60, 120), (120, 300)]

# CM operates on Lisbon local time; hour-of-day slices follow service time, not
# server time.
TZ_LISBON = ZoneInfo("Europe/Lisbon")

# Ground-truth GPS validation (analyze): an observed arrival is CONFIRMED when
# a GPS fix of the attributed vehicle lies within GPS_NEAR_M of the stop no
# more than GPS_NEAR_S away in time. Otherwise the closest approach over
# [obs-GPS_SEARCH_BACK_S, obs+GPS_SEARCH_FWD_S] re-times the pair (CORRECTED),
# and a vehicle that never comes near drops it. GPS_NEAR_M allows for the
# ~60 s history downsampling (a bus crosses ~250-500 m between saved fixes).
GPS_NEAR_S = 120
GPS_NEAR_M = 300.0
GPS_SEARCH_BACK_S = 600
GPS_SEARCH_FWD_S = 2700


def _get_json(url, timeout=25, retries=2, pause=1.0):
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "parahub-eta-backtest"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            last = exc
            time.sleep(pause)
    raise last


def _stats(errs):
    """Bias/MAE/percentiles over a list of signed errors (seconds)."""
    if not errs:
        return None
    absv = sorted(abs(x) for x in errs)
    n = len(errs)
    return {
        "n": n,
        "bias": statistics.mean(errs),
        "mae": statistics.mean(absv),
        "p50": statistics.median(errs),
        "p90_abs": absv[min(n - 1, int(0.9 * (n - 1)))],
        "within60": 100.0 * sum(1 for x in absv if x <= 60) / n,
        "within120": 100.0 * sum(1 for x in absv if x <= 120) / n,
    }


def _fmt(s):
    if not s:
        return "        n=0"
    return (
        f"n={s['n']:>5}  bias={s['bias']:>+6.1f}s  MAE={s['mae']:>5.1f}s  "
        f"p50={s['p50']:>+6.1f}s  p90|={s['p90_abs']:>5.0f}s  "
        f"<=60s {s['within60']:>4.0f}%  <=120s {s['within120']:>4.0f}%"
    )


class Command(BaseCommand):
    help = "Backtest the STT ETA engine against CM /v2/arrivals observed ground truth."

    def add_arguments(self, parser):
        parser.add_argument("mode", choices=["cm-baseline", "collect", "analyze"])
        parser.add_argument("--stops", default="",
                            help="Comma-separated CM stop source_ids to monitor.")
        parser.add_argument("--auto", type=int, default=0,
                            help="Instead of --stops, pick the N busiest currently-active CM stops.")
        parser.add_argument("--out", default="/tmp/eta_backtest.jsonl",
                            help="collect: JSONL output path (appended). analyze: input path.")
        parser.add_argument("--interval", type=int, default=45,
                            help="collect: seconds between capture cycles.")
        parser.add_argument("--duration", type=int, default=3600,
                            help="collect: total run seconds.")
        parser.add_argument("--api-base", default="http://127.0.0.1:8000",
                            help="collect: base URL of the engine under test (prod :8000, dev slot 1 :8001).")

    def handle(self, *args, **opts):
        stops = self._resolve_stops(opts)
        mode = opts["mode"]
        if mode == "cm-baseline":
            self._cm_baseline(stops)
        elif mode == "collect":
            self._collect(stops, opts["api_base"], opts["out"], opts["interval"], opts["duration"])
        elif mode == "analyze":
            self._analyze(opts["out"])

    # ------------------------------------------------------------------ stops
    def _resolve_stops(self, opts):
        if opts["stops"]:
            return [s.strip() for s in opts["stops"].split(",") if s.strip()]
        if opts["auto"]:
            # collect needs stops the /eta/ endpoint can serve (present in our DB
            # AND with vehicles our STT is currently tracking toward them);
            # cm-baseline only hits CM's API so any live stop is fine.
            return self._auto_stops(opts["auto"], require_db=(opts["mode"] == "collect"),
                                    api_base=opts["api_base"])
        # analyze reads its stops from the log itself; the others need a set.
        if opts["mode"] != "analyze":
            raise CommandError("provide --stops or --auto")
        return []

    def _auto_stops(self, n, require_db, api_base=None):
        """Busiest currently-active CM stops worth backtesting against.

        For collect (require_db and api_base), the binding criterion is that our
        STT *currently returns >=1 approaching vehicle* for the stop -- probed on
        the same /eta/ users see. CM's "busiest" rank counts vehicles *sitting
        at* a stop, which says nothing about what's *approaching* it in our
        confirmed-tracking set, so without this probe --auto picks stops our
        engine can't predict (ours=0). The observed-coverage and mid-route
        gates are deliberately NOT applied here: collect logs ground truth
        inline as it settles over the window, so a busy served hub that reads 0%
        observed at 08:00 (day just started) is exactly what we want -- its
        observed accumulates during the run. Coverage/seq still gate the
        retrospective cm-baseline path, which has no forward capture.
        """
        veh = _get_json(f"{CM_API}/vehicles")
        ranked = [s for s, _ in Counter(v["stop_id"] for v in veh if v.get("stop_id")).most_common()]
        probe = require_db and api_base
        slug_of = {}
        if require_db:
            from geo.models import Stop
            for st in Stop.objects.filter(
                source_id__in=ranked, agency__name=CM_AGENCY_NAME, place__isnull=False,
            ).select_related("place"):
                slug_of.setdefault(st.source_id, (st.place.slug, st.slug))
            ranked = [s for s in ranked if s in slug_of]
        stops = []          # STT serves it AND CM publishes observed here (preferred)
        probe_only = []     # STT serves it but no observed in today's archive yet
        for sid in ranked:
            if len(stops) >= n:
                break
            if probe:
                place_slug, stop_slug = slug_of[sid]
                try:
                    d = _get_json(f"{api_base}/api/v1/geo/transit/stops/{place_slug}/{stop_slug}/eta/",
                                  timeout=10)
                except Exception:  # noqa: BLE001
                    continue
                if not d.get("vehicles"):
                    continue
                # STT serves it -- but also require CM to actually publish observed
                # here, else a structurally observed-barren hub (rich positions, no
                # ground truth -- e.g. Campo Grande) passes the probe yet yields zero
                # matched pairs. One observed anywhere in today's archive proves CM
                # tracks it; we deliberately do NOT gate on coverage %, which reads
                # ~0 at day-start for a served hub whose early departures haven't
                # passed yet. Served stops with no observed yet are held as a
                # fallback pool to top up pre-dawn runs (nothing has passed at all).
                try:
                    arr = _get_json(f"{CM_API}/arrivals/by_stop/{sid}", timeout=10)
                except Exception:  # noqa: BLE001
                    arr = []
                if any(r.get("observed_arrival_unix") for r in arr):
                    stops.append(sid)
                elif len(probe_only) < n:
                    probe_only.append(sid)
                continue
            try:
                arr = _get_json(f"{CM_API}/arrivals/by_stop/{sid}")
            except Exception:  # noqa: BLE001
                continue
            if not arr:
                continue
            coverage = sum(1 for r in arr if r.get("observed_arrival_unix")) / len(arr)
            seqs = [r["stop_sequence"] for r in arr if r.get("stop_sequence") is not None]
            median_seq = statistics.median(seqs) if seqs else 0
            if coverage >= MIN_OBSERVED_COVERAGE and median_seq >= MIN_MEDIAN_SEQ:
                stops.append(sid)
        n_fallback = 0
        if probe and len(stops) < n and probe_only:
            # pre-dawn / post-rollover: no served stop has observed yet -- top up
            # with probe-only stops (busiest-first) so collect still captures.
            fallback = [s for s in probe_only if s not in stops][:n - len(stops)]
            n_fallback = len(fallback)
            stops += fallback
        if probe:
            served = len(stops) - n_fallback
            tail = f", {n_fallback} probe-only fallback" if n_fallback else ""
            criteria = f"DB, STT serves >=1, CM publishes observed ({served} with observed{tail})"
        else:
            criteria = f"observed>={MIN_OBSERVED_COVERAGE:.0%}, mid-route seq>={MIN_MEDIAN_SEQ}"
        self.stdout.write(f"auto-selected {len(stops)} stops ({criteria}): {', '.join(stops)}")
        return stops

    # ------------------------------------------------------------ cm-baseline
    def _cm_baseline(self, stops):
        all_err, per_stop = [], []
        total = observed = converged = outliers = 0
        for s in stops:
            try:
                arr = _get_json(f"{CM_API}/arrivals/by_stop/{s}")
            except Exception as exc:  # noqa: BLE001 - report and continue
                self.stderr.write(f"  {s}: fetch failed ({exc})")
                continue
            total += len(arr)
            errs = []
            for r in arr:
                o, e = r.get("observed_arrival_unix"), r.get("estimated_arrival_unix")
                if not o:
                    continue
                observed += 1
                if not e:
                    continue
                d = e - o
                if abs(d) > OUTLIER_S:
                    outliers += 1
                    continue
                if abs(d) <= CONVERGED_S:
                    converged += 1
                errs.append(d)
            all_err += errs
            per_stop.append((s, len(arr), len(errs)))

        self.stdout.write("\n=== CM estimated vs observed (retrospective, whole service day) ===")
        for s, tot, n in per_stop:
            self.stdout.write(f"  stop {s:<8} departures={tot:>4}  usable est/obs pairs={n:>4}")
        cov = 100.0 * observed / total if total else 0
        self.stdout.write(
            f"\ntotal departures={total}  with observed={observed} ({cov:.0f}% coverage)  "
            f"usable pairs={len(all_err)}  converged(|err|<={CONVERGED_S}s)={converged}  "
            f"outliers(|err|>{OUTLIER_S}s excluded)={outliers}")
        self.stdout.write("CM estimate error   " + _fmt(_stats(all_err)))
        self.stdout.write("  (negative bias = CM predicts arrival EARLIER than the bus actually comes)")

    # ---------------------------------------------------------------- collect
    def _collect(self, stops, api_base, out, interval, duration):
        from geo.models import Stop
        from parahub.services.redis_pool import get_redis

        smap = {}
        rows = Stop.objects.filter(source_id__in=stops).select_related("place")
        for st in rows:
            place_slug = st.place.slug if st.place_id else None
            if st.source_id in smap and place_slug:
                self.stderr.write(f"  note: source_id {st.source_id} matches multiple stops; using {place_slug}/{st.slug}")
            if place_slug:
                smap[st.source_id] = (place_slug, st.slug)
        missing = [s for s in stops if s not in smap]
        if missing:
            self.stderr.write(f"  no slug for {len(missing)} stop(s), skipped for 'ours': {', '.join(missing)}")

        r = get_redis()
        start = time.time()
        end = start + duration
        next_tick = start
        cycles = ours_rows = cm_rows = obs_rows = 0
        # (stop, trip_id) already logged as observed -- once a departure carries
        # observed it stays in the archive all day; log each ground truth once.
        seen_obs = set()
        self.stdout.write(f"collecting {len(stops)} stops every {interval}s for {duration}s -> {out}")
        with open(out, "a") as f:
            while time.time() < end:
                cycle = int(time.time())
                for s in stops:
                    ours_rows += self._collect_ours(f, r, api_base, s, smap.get(s), cycle)
                    cw, ow = self._collect_cm(f, s, cycle, seen_obs)
                    cm_rows += cw
                    obs_rows += ow
                f.flush()
                cycles += 1
                # Absolute-tick schedule: sleep until the next multiple of
                # `interval` from start (or the run end), never busy-loop.
                next_tick += interval
                remaining = min(next_tick, end) - time.time()
                self.stderr.write(f"  cycle {cycles} @ +{cycle - int(start)}s  "
                                  f"ours={ours_rows} cm={cm_rows} obs={obs_rows}  sleep={max(0.0, remaining):.0f}s")
                if remaining > 0:
                    time.sleep(remaining)
        self.stdout.write(f"done: {cycles} cycles, {ours_rows} ours rows, {cm_rows} cm rows, {obs_rows} obs rows")

    def _collect_ours(self, f, r, api_base, stop, slug_pair, cycle):
        if not slug_pair:
            return 0
        place_slug, stop_slug = slug_pair
        try:
            data = _get_json(f"{api_base}/api/v1/geo/transit/stops/{place_slug}/{stop_slug}/eta/", timeout=10)
        except Exception:  # noqa: BLE001 - a single failed poll must not kill the run
            return 0
        written = 0
        for v in data.get("vehicles", []):
            eta = v.get("eta_seconds")
            if eta is None:
                continue
            vid = v.get("vehicle_id")
            tid = None
            raw = r.hget("transit:vdata", f"{CM_DS_ID}:{vid}")
            if raw:
                try:
                    tid = json.loads(raw).get("tid")
                except (ValueError, TypeError):
                    pass
            f.write(json.dumps({
                "k": "ours", "t": cycle, "stop": stop, "vehicle_id": vid, "trip_id": tid,
                "eta_s": eta, "pred_unix": cycle + eta, "stops_away": v.get("stops_away"),
                "obs_seg": v.get("observed_segments"), "tot_seg": v.get("total_segments"),
            }) + "\n")
            written += 1
        return written

    def _collect_cm(self, f, stop, cycle, seen_obs):
        """One by_stop poll, two record kinds: CM's live forward estimate ('cm')
        and ground-truth observed ('obs', logged once per departure). Logging
        observed inline makes analyze replayable and immune to the archive's
        service-day rollover -- it no longer needs a same-day live harvest.
        Returns (cm_written, obs_written)."""
        try:
            arr = _get_json(f"{CM_API}/arrivals/by_stop/{stop}", timeout=10)
        except Exception:  # noqa: BLE001
            return 0, 0
        cm_written = obs_written = 0
        for rr in arr:
            tid = rr.get("trip_id")
            obs = rr.get("observed_arrival_unix")
            if obs:
                key = (stop, tid)
                if tid and key not in seen_obs:
                    seen_obs.add(key)
                    f.write(json.dumps({
                        "k": "obs", "t": cycle, "stop": stop, "trip_id": tid,
                        "vehicle_id": rr.get("vehicle_id"),
                        "sched_unix": rr.get("scheduled_arrival_unix"), "obs_unix": obs,
                    }) + "\n")
                    obs_written += 1
                continue
            est = rr.get("estimated_arrival_unix")
            if not est:
                continue
            # keep only live forward predictions near now -- bounds file size and
            # matches what a board would actually show.
            if not (cycle - 60 <= est <= cycle + 900):
                continue
            f.write(json.dumps({
                "k": "cm", "t": cycle, "stop": stop, "trip_id": tid,
                "vehicle_id": rr.get("vehicle_id"), "sched_unix": rr.get("scheduled_arrival_unix"),
                "est_unix": est,
            }) + "\n")
            cm_written += 1
        return cm_written, obs_written

    # ---------------------------------------------------------------- analyze
    def _analyze(self, path):
        ours, cm, logged_obs = [], [], []
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    k = d.get("k")
                    if k == "ours":
                        ours.append(d)
                    elif k == "cm":
                        cm.append(d)
                    elif k == "obs":
                        logged_obs.append(d)
        except FileNotFoundError:
            raise CommandError(f"no such log: {path}")

        stops = sorted({d["stop"] for d in ours + cm})
        obs, sched, obs_veh = {}, {}, {}
        # Prefer ground truth logged inline during collect -- it's the actual
        # service day of the run and survives archive rollover. Only stops with
        # no logged observed fall back to a same-day live harvest (older logs).
        for d in logged_obs:
            tid = d.get("trip_id")
            if not tid:
                continue
            obs[(d["stop"], tid)] = d["obs_unix"]
            obs_veh[(d["stop"], tid)] = d.get("vehicle_id")
            if d.get("sched_unix"):
                sched[(d["stop"], tid)] = d["sched_unix"]
        harvest = [s for s in stops if not any(k[0] == s for k in obs)]
        # trip_ids repeat every service day, so a live harvest joined against a
        # log captured on a PAST day would match another day's departures.
        # Only harvest when the log's capture day is today (Lisbon service time).
        last_t = max((d["t"] for d in ours + cm), default=0)
        log_day = datetime.fromtimestamp(last_t, TZ_LISBON).date() if last_t else None
        if harvest and log_day != datetime.now(TZ_LISBON).date():
            self.stderr.write(f"  {len(harvest)} stop(s) have no logged observed and the log is "
                              f"from {log_day} (past service day) -- live harvest skipped")
            harvest = []
        if harvest:
            self.stderr.write(f"  no logged observed for {len(harvest)} stop(s); "
                              f"live-harvesting (same-service-day only): {', '.join(harvest)}")
        for s in harvest:
            try:
                arr = _get_json(f"{CM_API}/arrivals/by_stop/{s}")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"  {s}: observed harvest failed ({exc})")
                continue
            for r in arr:
                tid = r.get("trip_id")
                if not tid:
                    continue
                if r.get("observed_arrival_unix"):
                    obs[(s, tid)] = r["observed_arrival_unix"]
                    obs_veh[(s, tid)] = r.get("vehicle_id")
                if r.get("scheduled_arrival_unix"):
                    sched[(s, tid)] = r["scheduled_arrival_unix"]

        self._gps_validate(obs, obs_veh)

        def bucket(lead):
            for lo, hi in LEAD_BUCKETS:
                if lo <= lead < hi:
                    return f"{lo // 60}-{hi // 60}min"
            return None

        coll = defaultdict(lambda: defaultdict(list))  # method -> bucket -> errs
        matched = {"ours": 0, "cm": 0}
        joined = {"ours": [], "cm": []}  # (row, lead, err) per matched prediction
        for method, rows, pred_key in (("ours", ours, "pred_unix"), ("cm", cm, "est_unix")):
            for d in rows:
                key = (d["stop"], d.get("trip_id"))
                o = obs.get(key)
                if not o or not d.get("trip_id"):
                    continue
                lead = o - d["t"]
                b = bucket(lead)
                if not b:
                    continue
                err = d[pred_key] - o
                if abs(err) > OUTLIER_S:
                    continue
                matched[method] += 1
                coll[method][b].append(err)
                joined[method].append((d, lead, err))

        # schedule-only baseline: constant per departure, not lead-dependent.
        sched_err = [sc - o for key, o in obs.items() if (sc := sched.get(key))]

        harvest_set = set(harvest)
        n_harv = sum(1 for k in obs if k[0] in harvest_set)
        n_log = len(obs) - n_harv
        self.stdout.write("\n=== ETA accuracy vs observed ground truth (predicted - observed) ===")
        self.stdout.write(f"ground-truth departures: {len(obs)} "
                          f"({n_log} logged inline, {n_harv} live-harvested)   "
                          f"matched predictions: ours={matched['ours']} cm={matched['cm']}")
        self.stdout.write(f"\nschedule-only baseline   {_fmt(_stats(sched_err))}")
        for lo, hi in LEAD_BUCKETS:
            b = f"{lo // 60}-{hi // 60}min"
            self.stdout.write(f"\n-- lead {b} (bus was this far out when predicted) --")
            self.stdout.write(f"  our STT        {_fmt(_stats(coll['ours'][b]))}")
            self.stdout.write(f"  CM estimate    {_fmt(_stats(coll['cm'][b]))}")

        self._slices(joined)

    # --------------------------------------------------- ground-truth GPS check
    def _gps_validate(self, obs, obs_veh):
        """Cross-check every observed arrival against raw GPS history.

        Mutates ``obs`` in place: keeps confirmed pairs, re-times corrupt ones
        to the vehicle's actual closest approach to the stop, drops pairs whose
        vehicle never came near. Pairs without GPS coverage (retention passed,
        feed gap, unknown vehicle) are kept as-is and counted as unverified.
        """
        from bisect import bisect_left, bisect_right

        from geo.models import Stop, VehiclePositionHistory
        from parahub.services.transit_rt import make_flat_dist

        if not obs:
            return
        dist = make_flat_dist(38.7)  # CM = Lisbon metro area

        stop_pos = {}
        for sid, loc in Stop.objects.filter(
            source_id__in={k[0] for k in obs}, agency__data_source_id=CM_DS_ID,
        ).values_list("source_id", "location"):
            stop_pos[sid] = (loc.y, loc.x)

        vehicles = {v for v in obs_veh.values() if v}
        lo = datetime.fromtimestamp(min(obs.values()) - GPS_SEARCH_BACK_S, TZ_LISBON)
        hi = datetime.fromtimestamp(max(obs.values()) + GPS_SEARCH_FWD_S, TZ_LISBON)
        tracks = defaultdict(list)  # vid -> [(unix, lat, lon)] sorted
        qs = VehiclePositionHistory.objects.filter(
            data_source_id=CM_DS_ID, vehicle_id__in=vehicles, time__gte=lo, time__lte=hi,
        ).values_list("vehicle_id", "time", "latitude", "longitude")
        for vid, ts, lat, lon in qs.iterator(chunk_size=20000):
            tracks[vid].append((ts.timestamp(), lat, lon))
        if not tracks:
            self.stderr.write("  GPS validation unavailable (no position history for the "
                              "log window) -- scoring against raw observed")
            return
        for rows in tracks.values():
            rows.sort()

        confirmed = unverified = 0
        shifts, dropped = [], Counter()
        for key in list(obs.keys()):
            vid, pos = obs_veh.get(key), stop_pos.get(key[0])
            rows = tracks.get(vid)
            if not rows or not pos:
                unverified += 1
                continue
            o = obs[key]
            times = [r[0] for r in rows]
            i0, i1 = bisect_left(times, o - GPS_SEARCH_BACK_S), bisect_right(times, o + GPS_SEARCH_FWD_S)
            if i0 == i1:
                unverified += 1
                continue
            best_d, best_t, near_d = float("inf"), None, float("inf")
            for ts, lat, lon in rows[i0:i1]:
                d = dist(lat, lon, pos[0], pos[1])
                if d < best_d:
                    best_d, best_t = d, ts
                if abs(ts - o) <= GPS_NEAR_S and d < near_d:
                    near_d = d
            if near_d <= GPS_NEAR_M:
                confirmed += 1
            elif best_d <= GPS_NEAR_M:
                obs[key] = best_t
                shifts.append(best_t - o)
            else:
                del obs[key]
                dropped[key[0]] += 1
        parts = [f"confirmed={confirmed}", f"corrected={len(shifts)}",
                 f"dropped={sum(dropped.values())}", f"unverified={unverified}"]
        if shifts:
            parts.append(f"correction shift p50={statistics.median(shifts):+.0f}s "
                         f"max={max(shifts, key=abs):+.0f}s")
        self.stdout.write("ground-truth GPS validation: " + "  ".join(parts))
        if dropped:
            top = ", ".join(f"{s}×{n}" for s, n in dropped.most_common(4))
            self.stdout.write(f"  dropped (vehicle never near stop): {top}")

    # ----------------------------------------------------------------- slices
    def _slices(self, joined):
        diag_slices(joined, "cm", TZ_LISBON, self.stdout.write)


def diag_slices(joined, theirs, tz, write):
    """Diagnostic slices over the matched predictions (same population as
    the lead-bucket table). Each slice discriminates one bias hypothesis:
    stops_away (last-segment/dwell semantics vs uniform), chain observed
    share (FIFO history vs schedule fallback), hour of day (regime lag at
    peak onset/decay), predicted-ETA micro-buckets (what the displayed
    number actually means), and per-stop outliers (dwell-heavy hubs).

    Shared by the CM and HSL backtests: ``joined`` maps "ours" and ``theirs``
    to lists of (row, lead, err); ``tz`` is the feed's service timezone.
    """
    jours = joined["ours"]
    if not jours:
        return

    def cell(errs):
        if not errs:
            return "n=   0"
        n = len(errs)
        bias = statistics.mean(errs)
        mae = statistics.mean(abs(x) for x in errs)
        return f"n={n:>4} b={bias:+6.1f}s mae={mae:5.1f}s"

    write("\n=== diagnostic slices (ours, matched population) ===")

    sa_groups = [("1", lambda s: s == 1), ("2", lambda s: s == 2),
                 ("3-5", lambda s: 3 <= s <= 5), ("6+", lambda s: s >= 6)]
    write("\n-- by stops_away at prediction time --")
    for lo, hi in LEAD_BUCKETS:
        b = f"{lo // 60}-{hi // 60}min"
        cells = []
        for label, match in sa_groups:
            errs = [e for d, l, e in jours if lo <= l < hi
                    and isinstance(d.get("stops_away"), int) and match(d["stops_away"])]
            cells.append(f"sa {label:<3} {cell(errs)}")
        write(f"  {b:<9} " + " | ".join(cells))

    share_groups = [("0%", lambda r: r == 0), ("1-99%", lambda r: 0 < r < 1),
                    ("100%", lambda r: r >= 1)]
    write("\n-- by chain observed share (obs_seg/tot_seg) --")
    for lo, hi in LEAD_BUCKETS:
        b = f"{lo // 60}-{hi // 60}min"
        cells = []
        for label, match in share_groups:
            errs = [e for d, l, e in jours if lo <= l < hi
                    and d.get("tot_seg") and d.get("obs_seg") is not None
                    and match(d["obs_seg"] / d["tot_seg"])]
            cells.append(f"obs {label:<5} {cell(errs)}")
        write(f"  {b:<9} " + " | ".join(cells))

    city = tz.key.rsplit("/", 1)[-1]
    write(f"\n-- by hour of day ({city}; near = lead<5min, far = 5-30min) --")
    by_hour = defaultdict(lambda: defaultdict(list))
    for method in ("ours", theirs):
        for d, l, e in joined[method]:
            h = datetime.fromtimestamp(d["t"], tz).hour
            by_hour[h][f"{method}_{'near' if l < 300 else 'far'}"].append(e)
    for h in sorted(by_hour):
        g = by_hour[h]
        write(
            f"  {h:02d}h  ours near {cell(g['ours_near'])}  far {cell(g['ours_far'])}"
            f"  |  {theirs} near {cell(g[f'{theirs}_near'])}  far {cell(g[f'{theirs}_far'])}")

    write("\n-- by DISPLAYED eta (ours; err vs actual, med_lead = real seconds out) --")
    for plo, phi in PRED_BUCKETS:
        rows = [(l, e) for d, l, e in jours if plo <= d.get("eta_s", -1) < phi]
        errs = [e for _, e in rows]
        med_lead = statistics.median(l for l, _ in rows) if rows else 0
        write(f"  shows {plo:>3}-{phi:<3}s  {cell(errs)}  med_lead={med_lead:>4.0f}s")

    write("\n-- per-stop bias (ours, lead<5min, n>=25, worst |bias| first) --")
    per_stop = defaultdict(list)
    for d, l, e in jours:
        if l < 300:
            per_stop[d["stop"]].append(e)
    ranked = sorted(((s, es) for s, es in per_stop.items() if len(es) >= 25),
                    key=lambda kv: -abs(statistics.mean(kv[1])))
    for s, es in ranked[:8]:
        write(f"  stop {s:<8} {cell(es)}")
