#!/usr/bin/env python3
"""
tools/v23floor.py — §V23.10: `QUESTION P`'s `neither`, set against what the step floor did not keep
(GitHub Issue #101).

    tools/v23floor.py <report JSON from tools/v23report.py> [--json <out>]

WHY. trace-0001 keeps a produce or a process step only when it lasts at least the floor (200 ticks);
every call is counted and histogrammed by log2 of its duration. A sub-floor step is 2 % of an AUDIO
block period and can never win `QUESTION P`'s longest-overlap attribution on its own, but a CLUSTER of
them could be the cause and would land in `neither`. The Orchestrator's confirmation of the floor
(§V23.10) requires the report to set `neither` against the sub-floor step count and the total
sub-floor time, so a large `neither` is not ambiguous between "nothing in the chain did it" and "the
floor hid what did". This computes that comparison. It decides nothing and sets no threshold: it is
printed whatever `neither` is.

WHAT THE RECORD ALLOWS, and so what this reports.
  count   EXACT, per kind: every call minus every kept step -- when the step buffer dropped nothing.
          When it dropped some (trace.dropped.step_dropped), an interval: a dropped step may have been
          above the floor, and the drop is not split by kind.
  time    AN INTERVAL, never a figure: the recorder keeps no sum of sub-floor durations, only the
          log2 histogram of every call. A bin [2^b, 2^(b+1)) wholly under the floor contributes its
          count times its lower and upper edge; the bin the floor falls in contributes its sub-floor
          part (its count minus the kept steps in it) times its lower edge and floor - 1. The interval
          is therefore within a factor of 2.
  P       `neither` and the losses located, from the FROZEN tools/v23accept.py (`QUESTION P`).

It REFUSES a report whose histogram does not add up to its call count for a kind, or whose kept steps
fall outside the floor rule. Standard library only; reads a report, writes the JSON it is asked to.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import v23accept  # noqa: E402

TB_HZ = 40500000
KINDS = ("produce", "process")          # flush_queue is always kept: nothing of it is under the floor
BINS = 32


def _edges(b):
    """[lo, hi] of log2 bin b in ticks, as src/audio/gbp_atrace.c bins a duration."""
    if b == 0:
        return 0, 1
    hi = (1 << (b + 1)) - 1
    return 1 << b, (hi if b < BINS - 1 else float("inf"))


def _bin(d):
    b = 0
    while d > 1 and b < BINS - 1:
        d >>= 1
        b += 1
    return b


def sub_floor(report):
    tr = report["trace"]
    floor = tr["floor"]
    dropped = tr["dropped"]["step_dropped"]
    out, tot = {}, {"straddle": 0, "below": 0, "t_below": [0, 0], "t_straddle_edges": None}
    for kind in KINDS:
        hist, calls = tr["hist"][kind], tr["calls"][kind]
        if sum(hist) != calls:
            raise ValueError("%s: the histogram holds %d calls, the count says %d" % (kind, sum(hist), calls))
        kept = [s[1] - s[0] for s in report["steps"] if s[2] == kind]
        if any(d < floor for d in kept):
            raise ValueError("%s: a kept step is under the floor of %d ticks" % (kind, floor))
        kept_bin = [0] * BINS
        for d in kept:
            kept_bin[_bin(d)] += 1
        below = straddle = 0
        t_lo = t_hi = 0
        s_lo = s_hi = None
        for b in range(BINS):
            lo, hi = _edges(b)
            if hi < floor:                                   # wholly under the floor
                below += hist[b]
                t_lo += hist[b] * lo
                t_hi += hist[b] * hi
            elif lo < floor:                                 # the floor falls in this bin
                straddle = hist[b] - kept_bin[b]
                if straddle < 0:
                    raise ValueError("%s: bin %d holds fewer calls than kept steps" % (kind, b))
                s_lo, s_hi = lo, floor - 1
            elif hist[b] < kept_bin[b]:
                raise ValueError("%s: bin %d holds fewer calls than kept steps" % (kind, b))
        n_max = below + straddle
        n_min = below + max(0, straddle - dropped)
        out[kind] = {"calls": calls, "kept": len(kept), "count_min": n_min, "count_max": n_max,
                     "time_ticks_min": t_lo + (n_min - below) * (s_lo or 0),
                     "time_ticks_max": t_hi + straddle * (s_hi or 0)}
        tot["straddle"] += straddle
        tot["below"] += below
        tot["t_below"][0] += t_lo
        tot["t_below"][1] += t_hi
        tot["t_straddle_edges"] = (s_lo, s_hi)
    s_lo, s_hi = tot["t_straddle_edges"] or (0, 0)
    n_max = tot["below"] + tot["straddle"]
    n_min = tot["below"] + max(0, tot["straddle"] - dropped)
    total = {"count_min": n_min, "count_max": n_max,
             "time_ticks_min": tot["t_below"][0] + (n_min - tot["below"]) * (s_lo or 0),
             "time_ticks_max": tot["t_below"][1] + tot["straddle"] * (s_hi or 0)}
    return out, total, floor, dropped


def compare(report):
    tb = report.get("tb_hz", TB_HZ)
    per_kind, total, floor, dropped = sub_floor(report)
    a = report["audio"]
    losses = v23accept.audio_losses(a["decoded"], a["ticks"])
    p = v23accept.question_P(losses, report.get("steps", []), report.get("callbacks", []), tb)
    w = report["window"]
    secs = (w["t_end"] - w["t_origin"]) / float(tb) if w["t_end"] > w["t_origin"] else None
    total["time_ms_min"] = total["time_ticks_min"] * 1000.0 / tb
    total["time_ms_max"] = total["time_ticks_max"] * 1000.0 / tb
    if secs:
        total["per_second_min"] = total["count_min"] / secs
        total["per_second_max"] = total["count_max"] / secs
        total["time_fraction_min"] = total["time_ticks_min"] / float(w["t_end"] - w["t_origin"])
        total["time_fraction_max"] = total["time_ticks_max"] / float(w["t_end"] - w["t_origin"])
    return {"floor_ticks": floor, "step_dropped": dropped, "window_seconds": secs,
            "P": {"losses": p["losses"], "neither": p["counts"]["neither"], "counts": p["counts"],
                  "decision": p["decision"]},
            "sub_floor": per_kind, "sub_floor_total": total,
            "reading": ("no threshold: %d of %d loss gaps went to `neither`; the steps the floor did not keep "
                        "number %d..%d and ran %.3f..%.3f ms in all"
                        % (p["counts"]["neither"], p["losses"], total["count_min"], total["count_max"],
                           total["time_ms_min"], total["time_ms_max"]))}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        out = compare(json.load(f))
    text = json.dumps(out, indent=2, sort_keys=True)
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
