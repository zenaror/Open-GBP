#!/usr/bin/env python3
"""
tools/v28ahead.py — GitHub Issue #122: how fast the chain puts a chunk back into READY after the AI takes one, measured
on the archived traces, and the margin that leaves against a producer stall at each READY depth (GBP_APLAY_AHEAD).
DESCRIPTIVE, host-side, on versioned fixtures; it decides nothing.

    tools/v28ahead.py [--json <out>]

WHAT IT READS. The two runs whose traces keep every AI DMA callback and every `flush_queue` step (the instant a produced
chunk joins READY; a flush_queue is always kept, and neither trace dropped a record), through the frozen builders that
made their reports:
  RUN 39  trace-0001, every chunk produced in 16-push calls          tools/v23report.py
  RUN 40  split-0001, 8- and 16-push chunks interleaved by a seed    tools/v24report.py
The runtime has produced in 8-push calls since #109, so RUN 40's 8-push arm is the one that describes it. A chunk's arm
is bit 0 of the tag on the production step that finished it, the one just before its flush_queue (1 = 8 pushes;
poc/gbp-audio-split/source/main.c, split_tag). Both runs held AHEAD 4 and TARGET 2048 on the stimulus ROM, not a game.
No game run has a trace.

THE REFILL LATENCY. For every callback, the time from its entry to the end of the first flush_queue after it: how long
the producer took to put back the chunk the callback took. It is MEASURED only on these two stimulus-ROM runs, at
AHEAD 4 and TARGET 2048, where no mute ever ran (one flush_queue per callback interval). That the producer's timing
does not depend on AHEAD is INFERENCE from the code, and only in the steady state at equal TARGET: at TARGET >= 146 the
correction pins the chunk-start fill near TARGET - 16.5 >= 129, so the ring does not hold a chunk's start back; after
a drain loss, a TARGET whose surplus above the 129-sample gate is small (about TARGET - 145.5) can.

THE MARGIN. A READY queue of A chunks survives a producer stop that begins just after a hand-off if the stop plus the
refill ends before the A-th hand-off after it: margin(A) = A x period - refill. It is printed from the 8-push arm's
largest refill, so its transfer to a game and to AHEAD < 4 is INFERENCE. The largest stall this project has measured is
one 64 KiB SD write inside the pump slot, 24.43 ms (GBP-HW-320); no SD write happens during a session. The images start
the AI only when READY holds at least 2 (poc/gbp-audio-sync/source/main.c), so AHEAD 1 needs another start sequence or
a lowering after the start.

THE PUMP. How often the pump slot ran, per run, from STREAMPUMP and CLOCKSEC: the traced stimulus runs beside the game
runs, since a chunk takes a fixed number of pump runs (128 pushes in 8-push calls: 16) and the game's refill is not
traced.

THE LATENCY OF THE CHAIN (INFERENCE from the code: stock is conserved between corrections). At the instant a callback
hands a chunk over and the producer starts the next one, the stock ahead of a sample entering the ring is the ring's
chunk-start fill c (whose first 128 samples are the chunk about to be produced), the A - 1 READY chunks, the chunk just
programmed and the chunk just started: c + 128 (A + 1) samples, plus the resampler's 8. The (A + 1) term rests on the
code and the DMA hand-off's semantics only; no measurement tests it. So L(T, A) = (c + 128 (A + 1) + 8) / 4.096 ms with c at the
DUP edge, TARGET - 16.5, in the deficit regime RUN 43 ran (dup only, drop 0). Only T + 128 A enters it. It covers the
ring to the DAC's input; capture-to-drain, the AI's FIFO and DAC, the television and the video path are not in it. Its
check against a MEASURED quantity: the ring's time-mean fill, which a take of 128 samples over 16 pump runs followed
by a linear refill puts at c - (128 - 4.096 x take_ms) / 2, i.e. TARGET - 71.6 at RUN 43's pump rate, against the
per-second means RUN 43 measured, printed here from its versioned log through tools/v27report.py: -71.1 at every
target it held, 384 to 3 584 (GBP-HW-341 records the two arms' "71 samples under the target"). Below 384 neither the
offset nor the correction's hold has been measured.

THE DEFICIT. RUN 43's consumption, 128 samples per AI callback period (LIVEM: callbacks, t_first, t_last), less its
arrivals, the mean AUDIO blocks per whole second of the session (the per-second counts through tools/v27report.py,
the first and the last, partial, seconds left out). With no correction below TARGET 146, the stock falls at that rate:
one chunk per 128 / deficit seconds, 1 / 4.096 ms of latency per sample. Above it the DUP adds at most one sample per
chunk, so a loss of stock is repaid at (1 / period) - deficit samples per second.

THE LADDER. The latencies of a nulling ladder in 128-sample steps, TARGET down first to 192 and then AHEAD, as the #122
report sets it out; a proposal's arithmetic, not a frozen scale.

What it does NOT measure: the refill during a GAME (RUN 41-43 kept no trace), runs of consecutive pump skips, the
producer at a READY depth or a TARGET it never ran, and any stall longer than these runs happened to contain.

Standard library only; reads the fixtures, writes the JSON it is asked to.
"""
import bisect
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import v23report  # noqa: E402
import v24report  # noqa: E402
import v27report  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FXD = os.path.join(ROOT, "captures", "fixtures")
TRACED = {39: (v23report, os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-trace-0001-run39")),
          40: (v24report, os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-split-0001-run40"))}
GAMES = {41: os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-game-0001-run41.log"),
         42: os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-game-0002-run42.log"),
         43: os.path.join(FXD, "hw-gamecube-gbp-2026-09-25-sync-0001-run43.log")}
TB_HZ = 40500000
LARGEST_STALL_MS = 24.43            # GBP-HW-320
AHEADS = (1, 2, 3, 4)
RATE_PER_MS = 4.096                 # decoded samples per millisecond
CHUNK = 128                         # samples per chunk (GBP_APLAY_PUSHES)
BAND_EDGE = 16.5                    # the chunk-start fill sits at TARGET - 16.5 under DUP-only correction
FIR = 8                             # the resampler's delay, in input samples
TAKE_RUNS = 16                      # pump runs per chunk: 128 pushes in 8-push calls
TARGETS = (512, 384, 256, 192, 146)
LADDER = ((704, 4), (576, 4), (448, 4), (320, 4), (192, 4), (192, 3), (192, 2), (192, 1))
STARTUP_S = 6                       # RUN 43's ring recovers from the AI start by second 6 (fill - target -79 at s5, -71 at s6)


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def build(n):
    mod, fx = TRACED[n]
    with open(fx + "-trace.bin", "rb") as f:
        data = f.read()
    return mod.build(read(fx + ".log"), data)


def pump_rate(text):
    """(runs, capture_s, runs per second): calls the pump slot made, less those skipped for a pending cause."""
    kv = dict(re.findall(r"(\w+)=([0-9.]+)", re.search(r"^\d{6} STREAMPUMP .*$", text, re.M).group(0)))
    cap = float(re.search(r"^\d{6} CLOCKSEC capture_s=([0-9.]+)", text, re.M).group(1))
    runs = int(kv["calls"]) - int(kv["skipped_cause_pending"])
    return runs, cap, runs / cap


def refills(rep):
    """[(refill_ms, arm)] for every callback followed by a flush_queue; arm 8 or 16 when the trace tags it."""
    steps = rep["steps"]
    tags = rep.get("step_tag")
    fq = sorted(s for s in steps if s[2] == "flush_queue")
    arm = {}
    if tags is not None:
        prod = sorted((s[1], t) for s, t in zip(steps, tags) if s[2] == "produce")
        ends = [p[0] for p in prod]
        for s in fq:
            i = bisect.bisect_right(ends, s[0]) - 1
            if i < 0:
                raise ValueError("a flush_queue at %d has no production step before it" % s[0])
            arm[s[1]] = 8 if prod[i][1] & 1 else 16
    q = [s[1] for s in fq]
    out = []
    for c, _x in rep["callbacks"]:
        i = bisect.bisect_right(q, c)
        if i < len(q):
            out.append(((q[i] - c) * 1000.0 / TB_HZ, arm.get(q[i], 16)))
    return out


def latency_ms(target, ahead):
    """The chain's share of the audio path at (TARGET, AHEAD), ms."""
    return (target - BAND_EDGE + CHUNK * (ahead + 1) + FIR) / RATE_PER_MS


def mean_fill_offset(pump_per_s):
    """The ring's time-mean fill less TARGET, from the chunk-start fill and the take over TAKE_RUNS pump runs."""
    take_ms = TAKE_RUNS * 1000.0 / pump_per_s
    return -(BAND_EDGE + (CHUNK - RATE_PER_MS * take_ms) / 2.0)


def measured_offsets(text):
    """RUN 43's per-second ring fill less its target, by target: the settled seconds (no mute, no settling, blocks
    counted) from STARTUP_S on, through the frozen report builder."""
    by = {}
    for s in v27report.build(text)["seconds"]:
        if s["s"] >= STARTUP_S and not s["mute"] and not s["settling"] and s["count"] > 0:
            by.setdefault(str(s["target"]), []).append(s["fill"] - s["target"])
    return dict((t, {"n": len(v), "mean": sum(v) / len(v), "min": min(v), "max": max(v)}) for t, v in by.items())


def deficit(text):
    """(consumed, arrived, deficit) in decoded samples per second, RUN 43's."""
    m = dict(re.findall(r"(\w+)=(\w+)", re.search(r"^\d{6} LIVEM .*$", text, re.M).group(0)))
    period_s = (int(m["t_last"], 16) - int(m["t_first"], 16)) / float(TB_HZ) / (int(m["callbacks"]) - 1)
    counts = [s["count"] for s in v27report.build(text)["seconds"]][1:-1]
    consumed, arrived = CHUNK / period_s, sum(counts) / float(len(counts))
    return consumed, arrived, consumed - arrived


def dist(values):
    x = sorted(values)
    n = len(x)
    return {"n": n, "median": x[n // 2], "p99": x[int(0.99 * n)], "max": x[-1]}


def analyse():
    runs = {}
    period = None
    for n in sorted(TRACED):
        rep = build(n)
        cbs = [e for e, _x in rep["callbacks"]]
        periods = sorted((b - a) * 1000.0 / TB_HZ for a, b in zip(cbs, cbs[1:]))
        r = refills(rep)
        q = sorted(s[1] for s in rep["steps"] if s[2] == "flush_queue")
        per = {}
        for a, b in zip(cbs, cbs[1:]):
            k = bisect.bisect_left(q, b) - bisect.bisect_left(q, a)
            per[str(k)] = per.get(str(k), 0) + 1
        fx = TRACED[n][1] + ".log"
        runs[str(n)] = {"callbacks": len(cbs), "flush_queue": sum(1 for s in rep["steps"] if s[2] == "flush_queue"),
                        "dropped": sum(v for v in rep["trace"]["dropped"].values()),
                        "flushes_per_interval": per,
                        "period_ms": periods[len(periods) // 2],
                        "arms": dict((str(a), dist([v for v, m in r if m == a])) for a in (8, 16)
                                     if any(m == a for _v, m in r)),
                        "pump_per_s": pump_rate(read(fx))[2]}
        period = runs[str(n)]["period_ms"] if period is None else min(period, runs[str(n)]["period_ms"])
    worst8 = runs["40"]["arms"]["8"]["max"]
    games = dict((str(n), pump_rate(read(p))[2]) for n, p in sorted(GAMES.items()))
    return {"traced": runs,
            "games_pump_per_s": games,
            "latency_ms": dict((str(t), dict((str(a), latency_ms(t, a)) for a in AHEADS)) for t in TARGETS),
            "mean_fill_offset_run43": mean_fill_offset(games["43"]),
            "measured_offset_run43": measured_offsets(read(GAMES[43])),
            "deficit_run43": deficit(read(GAMES[43])),
            "ladder_ms": [[t, a, t + CHUNK * a, latency_ms(t, a)] for t, a in LADDER],
            "period_ms": period, "refill_8push_max_ms": worst8, "largest_stall_ms": LARGEST_STALL_MS,
            "margin_ms": dict((str(a), a * period - worst8) for a in AHEADS)}


def main(argv):
    r = analyse()
    for n, x in r["traced"].items():
        arms = "; ".join("%s-push n=%d median %.2f p99 %.2f max %.2f ms" % (a, d["n"], d["median"], d["p99"], d["max"])
                         for a, d in sorted(x["arms"].items(), key=lambda kv: int(kv[0])))
        print("RUN %s: %d callbacks, %d flush_queue, %d records dropped, period %.3f ms, pump %.0f runs/s; %s"
              % (n, x["callbacks"], x["flush_queue"], x["dropped"], x["period_ms"], x["pump_per_s"], arms))
    print("game runs, pump runs/s: %s" % ", ".join("RUN %s %.0f" % kv for kv in r["games_pump_per_s"].items()))
    print("margin against a producer stall, from the 8-push arm's largest refill %.2f ms: %s; largest measured stall "
          "%.2f ms" % (r["refill_8push_max_ms"], ", ".join("AHEAD %s %.1f ms" % kv for kv in r["margin_ms"].items()),
                       r["largest_stall_ms"]))
    print("chain latency, ms (TARGET x AHEAD 4 / 3 / 2 / 1):")
    for t in TARGETS:
        print("  T%-4d %s" % (t, "  ".join("%6.1f" % r["latency_ms"][str(t)][str(a)] for a in (4, 3, 2, 1))))
    print("the ring's mean fill against TARGET, from the take at RUN 43's pump rate: %.2f samples; measured: %s"
          % (r["mean_fill_offset_run43"], ", ".join("T%s %.2f (n=%d)" % (t, d["mean"], d["n"]) for t, d in
                                                    sorted(r["measured_offset_run43"].items(), key=lambda kv: int(kv[0])))))
    c, a, d = r["deficit_run43"]
    ceiling = c / CHUNK                                          # one DUP per chunk at most
    print("RUN 43: consumed %.2f, arrived %.2f samples/s: deficit %.2f/s = one chunk per %.1f s, %.2f ms of latency "
          "per s; the correction's ceiling %.2f/s, so a loss is repaid at %.2f samples/s net"
          % (c, a, d, CHUNK / d, d / RATE_PER_MS, ceiling, ceiling - d))
    print("ladder: %s" % " | ".join("T%d A%d %.1f" % (t, a, l) for t, a, _s, l in r["ladder_ms"]))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(r, f, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
