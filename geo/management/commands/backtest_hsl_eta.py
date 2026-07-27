"""Benchmark the STT ETA engine against HSL Helsinki's official predictions.

Same predicted-minus-actual methodology as ``backtest_transit_eta`` (the CM
benchmark), but with a fundamentally better ground truth: HSL's HFP MQTT feed
(open broker, mqtt.hsl.fi) publishes explicit per-stop events from the
vehicle itself -- ``ars`` (halted at the stop) and ``pas`` (passed a stop it
serves without halting) -- with sub-second timestamps. No GPS re-validation
needed; truth here is doors-level.

The comparison arm is HSL's own prediction stack: the GTFS-RT TripUpdates
feed (same open realtime host our VP poller uses), sampled once per capture
cycle for the monitored stops.

Identity quirk that shapes every join: HSL publishes EMPTY ``trip_id`` in
both VehiclePositions and TripUpdates, so nothing here can join on trip_id.

  * ours  -> truth: by (stop, vehicle). /eta/'s vehicle_id ("22/1226") is
    exactly the HFP topic's operator/vehicle pair, zero-padding stripped.
    A prediction made at t matches the vehicle's NEXT ars/pas at that stop.
  * HSL   -> truth: by journey identity (route, direction, oday, start),
    present verbatim in both TripUpdates descriptors and HFP payloads
    (HFP dir is 1/2 = GTFS direction_id + 1; HFP start "HH:mm" =
    TU start_time[:5]).

The HFP payload also carries the timetabled arrival (``ttarr``), so the
schedule-only baseline comes free with each truth event.

collect MUST run under a transient systemd unit for multi-hour windows
(a Bash-launched process freezes when the session idles) -- see
PK/troubleshooting.md Long-Running Jobs.

Stop picking recipe (no CM-style archive to rank by): rank stop source_ids
by how many live vdata vehicles currently head to them (optionally filtered
to a route_type for mode diversity), then keep stops whose /eta/ answers
with >=1 vehicle -- that is what --auto does, bus-heavy by construction.
"""
from __future__ import annotations

import json
import queue
import ssl
import statistics
import threading
import time
import urllib.request
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError

from geo.management.commands.backtest_transit_eta import (
    LEAD_BUCKETS, OUTLIER_S, _fmt, _get_json, _stats, diag_slices)

HSL_DS_ID = "01KJWTTNWJ7G8V4Q7D8CBRWYZ8"
TU_URL = "https://realtime.hsl.fi/realtime/trip-updates/v2/hsl"
MQTT_HOST, MQTT_PORT = "mqtt.hsl.fi", 8883
TZ_HELSINKI = ZoneInfo("Europe/Helsinki")

# HFP event types that time a vehicle reaching a stop. dep is deliberately
# excluded: its topic next_stop field already points at the FOLLOWING stop,
# and arrival (not departure) is what the ETA promises.
HFP_EVENTS = ("ars", "pas")

# TripUpdates rows kept per cycle: arrivals within [now-60, now+1800] --
# mirrors the CM collect window, sized to the largest lead bucket.
TU_KEEP_PAST_S, TU_KEEP_FWD_S = 60, 1800

# A prediction matches the first truth event no further than this ahead;
# beyond it the vehicle was reassigned/diverted, not predicted late.
MATCH_FWD_S = 2700

# Two HFP events of the same kind for the same (stop, vehicle) within this
# window are broker re-emits, not two passages.
DEDUPE_S = 45


def _iso_unix(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def parse_hfp(topic, payload):
    """One HFP MQTT message -> flat truth record (or None if malformed).

    The payload's ``stop`` is authoritative for which stop the event refers
    to. The vehicle key comes from the TOPIC's operator/vehicle levels: the
    payload ``oper`` is the block operator and can differ (e.g. Espoo 173Z:
    topic 0018 vs payload 6), while the GTFS-RT vehicle_id our /eta/ exposes
    is built from the topic pair.
    """
    parts = topic.split("/")
    if len(parts) < 14:
        return None
    ev = parts[5]
    try:
        body = json.loads(payload)
        inner = body[ev.upper()]
        veh = f"{int(parts[7])}/{int(parts[8])}"
        rec = {
            "k": "hfp", "ev": ev,
            "stop": str(inner["stop"]),
            "veh": veh,
            "route": inner.get("route") or "",
            "dir": int(inner["dir"]) - 1,
            "oday": inner.get("oday") or "",
            "start": inner.get("start") or "",
            "tst_unix": _iso_unix(inner.get("tst")) or float(inner["tsi"]),
            "ttarr_unix": _iso_unix(inner.get("ttarr")),
            "dl": inner.get("dl"),
            "drst": inner.get("drst"),
        }
    except (ValueError, TypeError, KeyError):
        return None
    if not rec["stop"] or rec["stop"] == "None":
        return None
    return rec


class Command(BaseCommand):
    help = "Benchmark the STT ETA engine against HSL HFP ars/pas ground truth."

    def add_arguments(self, parser):
        parser.add_argument("mode", choices=["collect", "analyze"])
        parser.add_argument("--stops", default="",
                            help="Comma-separated HSL stop source_ids to monitor.")
        parser.add_argument("--auto", type=int, default=0,
                            help="Instead of --stops, pick the N busiest currently-served HSL stops.")
        parser.add_argument("--out", default="/tmp/eta_hsl_backtest.jsonl",
                            help="collect: JSONL output path (appended). analyze: input path.")
        parser.add_argument("--interval", type=int, default=30,
                            help="collect: seconds between capture cycles.")
        parser.add_argument("--duration", type=int, default=3600,
                            help="collect: total run seconds.")
        parser.add_argument("--api-base", default="http://127.0.0.1:8000",
                            help="collect: base URL of the engine under test.")
        parser.add_argument("--trail", type=int, default=MATCH_FWD_S,
                            help="collect: seconds to keep capturing truth after the last "
                                 "cycle, so tail predictions still meet their event.")

    def handle(self, *args, **opts):
        mode = opts["mode"]
        if mode == "collect":
            stops = self._resolve_stops(opts)
            self._collect(stops, opts["api_base"], opts["out"], opts["interval"],
                          opts["duration"], opts["trail"])
        else:
            self._analyze(opts["out"])

    # ------------------------------------------------------------------ stops
    def _resolve_stops(self, opts):
        if opts["stops"]:
            return [s.strip() for s in opts["stops"].split(",") if s.strip()]
        if opts["auto"]:
            return self._auto_stops(opts["auto"], opts["api_base"])
        raise CommandError("collect needs --stops or --auto")

    def _auto_stops(self, n, api_base):
        from parahub.services.redis_pool import get_redis

        r = get_redis()
        cnt = Counter()
        for key, raw in r.hgetall("transit:vdata").items():
            if not key.startswith(HSL_DS_ID + ":"):
                continue
            try:
                sid = json.loads(raw).get("sid")
            except ValueError:
                continue
            if sid:
                cnt[sid] += 1
        ranked = [s for s, _ in cnt.most_common(n * 6)]
        smap = self._slug_map(ranked)
        picked = []
        for sid in ranked:
            if len(picked) >= n:
                break
            if sid not in smap:
                continue
            place_slug, stop_slug = smap[sid]
            try:
                d = _get_json(f"{api_base}/api/v1/geo/transit/stops/{place_slug}/{stop_slug}/eta/",
                              timeout=10)
            except Exception:  # noqa: BLE001
                continue
            if d.get("vehicles"):
                picked.append(sid)
        self.stdout.write(f"auto-selected {len(picked)} stops (busiest vdata sids, "
                          f"/eta/ serves >=1): {', '.join(picked)}")
        return picked

    def _slug_map(self, source_ids):
        from geo.models import Stop

        smap = {}
        for st in Stop.objects.filter(
            source_id__in=source_ids, agency__data_source_id=HSL_DS_ID, place__isnull=False,
        ).select_related("place"):
            smap.setdefault(st.source_id, (st.place.slug, st.slug))
        return smap

    # ---------------------------------------------------------------- collect
    def _collect(self, stops, api_base, out, interval, duration, trail):
        import paho.mqtt.client as mqtt

        smap = self._slug_map(stops)
        missing = [s for s in stops if s not in smap]
        if missing:
            self.stderr.write(f"  no slug for {len(missing)} stop(s), skipped for 'ours': "
                              f"{', '.join(missing)}")
        stop_set = set(stops)

        q = queue.SimpleQueue()
        mq_stats = Counter()

        def on_connect(client, userdata, flags, reason_code, properties):
            mq_stats["connects"] += 1
            for ev in HFP_EVENTS:
                for sid in stops:
                    # topic level 13 (next_stop) equals the event's stop for
                    # ars/pas -- broker-side pre-filter; payload re-checked.
                    client.subscribe(f"/hfp/v2/journey/ongoing/{ev}/+/+/+/+/+/+/+/{sid}/#", qos=0)

        def on_disconnect(client, userdata, flags, reason_code, properties):
            mq_stats["disconnects"] += 1

        def on_message(client, userdata, msg):
            rec = parse_hfp(msg.topic, msg.payload)
            if not rec:
                mq_stats["parse_errors"] += 1
                return
            if rec["stop"] in stop_set:
                q.put(rec)
            else:
                mq_stats["off_stop"] += 1

        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
        c.on_connect = on_connect
        c.on_disconnect = on_disconnect
        c.on_message = on_message
        c.reconnect_delay_set(min_delay=1, max_delay=30)
        c.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        c.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        c.loop_start()

        start = time.time()
        end = start + duration
        next_tick = start
        cycles = ours_rows = hsl_rows = hfp_rows = 0
        self.stdout.write(f"collecting {len(stops)} stops every {interval}s for {duration}s -> {out}")
        try:
            with open(out, "a") as f:
                while time.time() < end:
                    cycle = int(time.time())
                    hfp_rows += self._drain_hfp(f, q)
                    for s in stops:
                        ours_rows += self._collect_ours(f, api_base, s, smap.get(s), cycle)
                    hsl_rows += self._collect_tu(f, stop_set, cycle)
                    f.flush()
                    cycles += 1
                    next_tick += interval
                    remaining = min(next_tick, end) - time.time()
                    self.stderr.write(
                        f"  cycle {cycles} @ +{cycle - int(start)}s  ours={ours_rows} "
                        f"hsl={hsl_rows} hfp={hfp_rows}  mqtt={dict(mq_stats)}  "
                        f"sleep={max(0.0, remaining):.0f}s")
                    if remaining > 0:
                        time.sleep(remaining)
                # trailing truth: events for the last predictions land after
                # the final cycle; give them one match window before closing.
                if trail > 0:
                    self.stderr.write(f"  final drain: waiting {trail}s for trailing truth events")
                    time.sleep(trail)
                    hfp_rows += self._drain_hfp(f, q)
        finally:
            c.loop_stop()
            c.disconnect()
        self.stdout.write(f"done: {cycles} cycles, {ours_rows} ours rows, "
                          f"{hsl_rows} hsl rows, {hfp_rows} hfp truth rows  mqtt={dict(mq_stats)}")

    def _drain_hfp(self, f, q):
        written = 0
        while True:
            try:
                rec = q.get_nowait()
            except queue.Empty:
                return written
            f.write(json.dumps(rec) + "\n")
            written += 1

    def _collect_ours(self, f, api_base, stop, slug_pair, cycle):
        if not slug_pair:
            return 0
        place_slug, stop_slug = slug_pair
        try:
            data = _get_json(f"{api_base}/api/v1/geo/transit/stops/{place_slug}/{stop_slug}/eta/",
                             timeout=10)
        except Exception:  # noqa: BLE001 - a single failed poll must not kill the run
            return 0
        written = 0
        for v in data.get("vehicles", []):
            eta = v.get("eta_seconds")
            if eta is None:
                continue
            f.write(json.dumps({
                "k": "ours", "t": cycle, "stop": stop, "vehicle_id": v.get("vehicle_id"),
                "route": v.get("route"), "dir": v.get("direction"),
                "eta_s": eta, "pred_unix": cycle + eta, "stops_away": v.get("stops_away"),
                "obs_seg": v.get("observed_segments"), "tot_seg": v.get("total_segments"),
            }) + "\n")
            written += 1
        return written

    def _collect_tu(self, f, stop_set, cycle):
        """One TripUpdates poll -> 'hsl' rows (their live prediction) for the
        monitored stops, arrivals within the keep window."""
        from google.transit import gtfs_realtime_pb2

        try:
            req = urllib.request.Request(TU_URL, headers={"User-Agent": "parahub-eta-backtest"})
            raw = urllib.request.urlopen(req, timeout=20).read()
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(raw)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f"  TU poll failed: {exc}")
            return 0
        written = 0
        for e in feed.entity:
            if not e.HasField("trip_update"):
                continue
            tu = e.trip_update
            trip = tu.trip
            if trip.schedule_relationship == trip.CANCELED:
                continue
            sd = trip.start_date
            oday = f"{sd[:4]}-{sd[4:6]}-{sd[6:]}" if len(sd) == 8 else sd
            start = trip.start_time[:5]
            for s in tu.stop_time_update:
                if s.stop_id not in stop_set or s.schedule_relationship == s.SKIPPED:
                    continue
                at = s.arrival.time or s.departure.time
                if not at or not (cycle - TU_KEEP_PAST_S <= at <= cycle + TU_KEEP_FWD_S):
                    continue
                f.write(json.dumps({
                    "k": "hsl", "t": cycle, "stop": s.stop_id, "route": trip.route_id,
                    "dir": trip.direction_id, "oday": oday, "start": start,
                    "est_unix": at, "seq": s.stop_sequence,
                }) + "\n")
                written += 1
        return written

    # ---------------------------------------------------------------- analyze
    def _analyze(self, path):
        ours, hsl, hfp = [], [], []
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
                    elif k == "hsl":
                        hsl.append(d)
                    elif k == "hfp":
                        hfp.append(d)
        except FileNotFoundError:
            raise CommandError(f"no such log: {path}")

        # Truth event lists under both join identities. Same-kind re-emits
        # within DEDUPE_S collapse; an ars and a pas can't both fire for one
        # passage (halted vs not), so kinds don't need cross-deduping.
        by_veh, by_trip = defaultdict(list), defaultdict(list)
        sched_err, ev_mix = [], Counter()
        last_ev = {}
        for h in sorted(hfp, key=lambda d: d["tst_unix"]):
            ts = h["tst_unix"]
            dk = (h["stop"], h["veh"], h["ev"])
            if dk in last_ev and ts - last_ev[dk] < DEDUPE_S:
                continue
            last_ev[dk] = ts
            ev_mix[h["ev"]] += 1
            by_veh[(h["stop"], h["veh"])].append(ts)
            by_trip[(h["stop"], h["route"], h["dir"], h["oday"], h["start"])].append(ts)
            if h.get("ttarr_unix"):
                sched_err.append(h["ttarr_unix"] - ts)
        for lists in (by_veh, by_trip):
            for v in lists.values():
                v.sort()

        def bucket(lead):
            for lo, hi in LEAD_BUCKETS:
                if lo <= lead < hi:
                    return f"{lo // 60}-{hi // 60}min"
            return None

        coll = defaultdict(lambda: defaultdict(list))
        joined = {"ours": [], "hsl": []}
        miss = defaultdict(Counter)

        def match(method, rows, truth, key_fn, pred_fn):
            for d in rows:
                evs = truth.get(key_fn(d))
                if not evs:
                    miss[method]["no_truth_key"] += 1
                    continue
                i = bisect_left(evs, d["t"])
                if i == len(evs):
                    miss[method]["no_event_after"] += 1
                    continue
                lead = evs[i] - d["t"]
                if lead > MATCH_FWD_S:
                    miss[method]["event_too_far"] += 1
                    continue
                b = bucket(lead)
                if not b:
                    miss[method]["lead_beyond_buckets"] += 1
                    continue
                err = pred_fn(d) - evs[i]
                if abs(err) > OUTLIER_S:
                    miss[method]["outlier"] += 1
                    continue
                coll[method][b].append(err)
                joined[method].append((d, lead, err))

        match("ours", ours, by_veh,
              lambda d: (d["stop"], d.get("vehicle_id")),
              lambda d: d["pred_unix"])
        match("hsl", hsl, by_trip,
              lambda d: (d["stop"], d["route"], d["dir"], d["oday"], d["start"]),
              lambda d: d["est_unix"])

        n_events = sum(ev_mix.values())
        self.stdout.write("\n=== ETA accuracy vs HFP ground truth (predicted - actual) ===")
        self.stdout.write(
            f"truth events: {n_events} ({', '.join(f'{k}={v}' for k, v in ev_mix.most_common())})   "
            f"matched predictions: ours={len(joined['ours'])} hsl={len(joined['hsl'])}")
        for method in ("ours", "hsl"):
            total = len(ours) if method == "ours" else len(hsl)
            parts = ", ".join(f"{k}={v}" for k, v in miss[method].most_common()) or "none"
            self.stdout.write(f"  {method}: {total} rows, unmatched: {parts}")
        self.stdout.write(f"\nschedule-only baseline   {_fmt(_stats(sched_err))}")
        for lo, hi in LEAD_BUCKETS:
            b = f"{lo // 60}-{hi // 60}min"
            self.stdout.write(f"\n-- lead {b} (vehicle was this far out when predicted) --")
            self.stdout.write(f"  our STT        {_fmt(_stats(coll['ours'][b]))}")
            self.stdout.write(f"  HSL official   {_fmt(_stats(coll['hsl'][b]))}")

        diag_slices(joined, "hsl", TZ_HELSINKI, self.stdout.write)
