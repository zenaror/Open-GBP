#!/usr/bin/env python3
"""
tools/u045window.py — GitHub Issue #116: the live family's AUDIO loss rates re-derived WITHOUT L2's window.
DESCRIPTIVE: it restates published figures, and decides nothing.

    tools/u045window.py [--json <out>]         (reads the versioned fixtures of RUN 38-42)

WHY. L2 is test instrumentation (§V22). In every image of the family it is armed LIVE_L2_FROM_S = 20 s into C's
64 s window and keeps 320 chunks, 10 s; while its kept chunks are handed to the AI DMA, gbp_aplay_process CRCs each
one (src/audio/gbp_aplay.c). Every rate this project published for the family was integrated over C's WHOLE window,
so it carries the instrument's cost, in a different proportion in each run (GBP-HW-338).

THE INSTRUMENT'S FOOTPRINT, MEASURED, not assumed. The two traced runs (RUN 39, RUN 40) keep only the steps longer
than their 200-tick floor. Of 239 189 and 237 493 `process` calls, exactly 320 were kept in each -- one per AI cycle, in 320
consecutive cycles -- and 320 is GBP_APLAY_L2_CHUNKS: the kept `process` steps ARE the CRC. The keep itself (one
store per push, in `produce`) lengthens a production step by a few ticks and is not separately visible.
  inside     the cycles from the one in which L2 is armed (t_origin + 20 s) to the one holding the last CRC step
  checks     the CRC's cycles alone; and C's whole seconds 20-29, the only definition the untraced runs allow
The CRC's last step ends about 0.1 s into second 30, so the whole-second figures are also given with second 30
dropped from "outside" (53 s).

EVERY RULE IT USES IS A FROZEN ONE:
  per second        tools/v22report.py's coverage (LIVESEC): 4 096 minus the blocks counted in each whole second
  the traces        tools/v23report.py (RUN 39) and tools/v24report.py (RUN 40), as their ingestions built them
  the losses        tools/v23accept.py's audio_losses(), each mapped to the cycle of the callback before its tick
  P                 tools/v23accept.py's question_P(), called on each subset
  the arms          tools/u045arms.py's arms_of_cycles() (§V24.7 (r5))
  QUESTION S        tools/v24accept.py's arithmetic -- mean(half)/mean(full), the percentile bootstrap within each
                    arm and the one-sided permutation, 20 000 each, seed 24 -- reimplemented here ONLY so that it
                    can run on a subset of cycles; on all the analysed cycles it reproduces the frozen tool's
                    output exactly, and tests/host/test_u045_window.py holds it to that
  R's prior         tests/host/test_v25_prior.py's per-arm Sum k over the arm's cycle time, and its count deficit

Standard library only; reads the fixtures, writes the JSON it is asked to.
"""
import bisect
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import u045arms  # noqa: E402
import v22report  # noqa: E402
import v23accept  # noqa: E402
import v23report  # noqa: E402
import v24accept  # noqa: E402
import v24report  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FXD = os.path.join(ROOT, "captures", "fixtures")
FAMILY = {38: "hw-gamecube-gbp-2026-09-24-live-0001-run38",
          39: "hw-gamecube-gbp-2026-09-24-trace-0001-run39",
          40: "hw-gamecube-gbp-2026-09-24-split-0001-run40",
          41: "hw-gamecube-gbp-2026-09-24-game-0001-run41",
          42: "hw-gamecube-gbp-2026-09-24-game-0002-run42"}
TB_HZ = 40500000
BLOCKS_PER_S = 4096
L2_FROM_S, L2_CHUNKS, WINDOW_S = 20, 320, 64
IN_S = range(L2_FROM_S, L2_FROM_S + 10)          # C's whole seconds 20-29
TRIALS, SEED, CI_Q = v24accept.S_TRIALS, v24accept.S_SEED, v24accept.CI_Q


def _read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8", "errors": "replace"})) as f:
        return f.read()


# ---------------------------------------------------------------------------- per whole second, every run

def per_second(text):
    """C's per-second losses and the three rates: whole (64 s), outside (54 s), inside (10 s)."""
    recs = v22report.records(text)
    cfg = v22report._kv(recs["LIVECFG2"][0])
    if (int(cfg["l2_from_s"]), int(cfg["l2_chunks"])) != (L2_FROM_S, L2_CHUNKS):
        raise ValueError("L2 is not armed at %d s for %d chunks in this log" % (L2_FROM_S, L2_CHUNKS))
    cov = v22report.build(text)["window"]["coverage"]
    if len(cov) != WINDOW_S:
        raise ValueError("C's window has %d whole seconds, not %d" % (len(cov), WINDOW_S))
    lost = [BLOCKS_PER_S - c for c in cov]
    inside = [lost[s] for s in IN_S]
    outside = [x for s, x in enumerate(lost) if s not in IN_S]
    out53 = [x for s, x in enumerate(lost) if s not in IN_S and s != IN_S[-1] + 1]
    return {"lost": lost,
            "whole": {"blocks": sum(lost), "seconds": WINDOW_S},
            "outside": {"blocks": sum(outside), "seconds": len(outside), "min": min(outside), "max": max(outside)},
            "inside": {"blocks": sum(inside), "seconds": len(inside), "min": min(inside), "max": max(inside)},
            "outside_without_s30": {"blocks": sum(out53), "seconds": len(out53)}}


# ---------------------------------------------------------------------------- the traced runs

def footprint(report):
    """The CRC, located in the trace: the kept `process` steps, one per cycle, 320 consecutive cycles."""
    ent = sorted(c[0] for c in report["callbacks"])
    proc = [s for s in report["steps"] if s[2] == "process"]
    cyc = [bisect.bisect_right(ent, s[0]) - 1 for s in proc]
    if len(proc) != L2_CHUNKS or len(set(cyc)) != L2_CHUNKS or cyc[-1] - cyc[0] != L2_CHUNKS - 1:
        raise ValueError("the kept process steps are not one per cycle over %d consecutive cycles" % L2_CHUNKS)
    t0 = report["window"]["t_origin"]
    arm_t = t0 + L2_FROM_S * TB_HZ
    dur = sorted(s[1] - s[0] for s in proc)
    return {"crc_cycles": [cyc[0], cyc[-1]], "armed_cycle": bisect.bisect_right(ent, arm_t) - 1,
            "crc_from_ticks": proc[0][0] - t0, "crc_to_ticks": proc[-1][1] - t0,
            "crc_step_ticks": {"min": dur[0], "p50": dur[len(dur) // 2], "max": dur[-1]},
            "process_calls": report["trace"]["calls"]["process"], "floor_ticks": report["trace"]["floor"]}


def _cycle_of(ent):
    return lambda t: bisect.bisect_right(ent, t) - 1


def trace_split(report, fp):
    """Loss gaps, Sum k, P and the phase, inside the footprint and outside it (the analysed cycles only)."""
    ent = sorted(c[0] for c in report["callbacks"])
    cyc = _cycle_of(ent)
    ncyc = len(ent) - 1
    lo, hi = fp["armed_cycle"], fp["crc_cycles"][1]
    a = report["audio"]
    losses = [x for x in v23accept.audio_losses(a["decoded"], a["ticks"]) if 0 <= cyc(x["t"]) < ncyc]
    out = {}
    for name, keep, n in (("inside", lambda c: lo <= c <= hi, hi - lo + 1),
                          ("outside", lambda c: not (lo <= c <= hi), ncyc - (hi - lo + 1))):
        sub = [x for x in losses if keep(cyc(x["t"]))]
        P = v23accept.question_P(sub, report["steps"], report["callbacks"], TB_HZ)
        tenth = sum(1 for x in sub if (x["t"] - ent[cyc(x["t"])]) * 10 < ent[cyc(x["t"]) + 1] - ent[cyc(x["t"])])
        out[name] = {"cycles": n, "loss_gaps": len(sub), "sum_k": sum(x["k"] for x in sub),
                     "P": dict((k, v) for k, v in P["counts"].items() if v), "P_decision": P["decision"],
                     "first_tenth": tenth}
    return out


def s_stats(h, f, trials=TRIALS):
    """tools/v24accept.py's QUESTION S arithmetic, on the per-cycle counts it is given."""
    mean = lambda v: sum(v) / float(len(v))
    rng = random.Random(SEED)
    ratios = []
    for _ in range(trials):
        bh = sum(rng.choices(h, k=len(h))) / float(len(h))
        bf = sum(rng.choices(f, k=len(f))) / float(len(f))
        ratios.append(bh / bf if bf else float("inf"))
    ratios.sort()
    ci = [ratios[int(CI_Q[0] * (trials - 1))], ratios[int(CI_Q[1] * (trials - 1))]]
    counts, nh = h + f, len(h)
    obs = mean(h) - mean(f)
    rng = random.Random(SEED)
    idx = list(range(len(counts)))
    hits = 0
    for _ in range(trials):
        rng.shuffle(idx)
        sh = sum(counts[i] for i in idx[:nh])
        if sh / float(nh) - (sum(counts) - sh) / float(len(counts) - nh) <= obs:
            hits += 1
    return {"ratio": mean(h) / mean(f), "ci90": ci, "difference_per_cycle": obs, "p": hits / float(trials)}


def arms_split(report, fp, trials=TRIALS):
    """RUN 40 by arm and by the footprint: cycles, loss gaps, Sum k, seconds, count deficit, and QUESTION S."""
    ent, arm_of = u045arms.arms_of_cycles(report)
    cyc = _cycle_of(ent)
    a = report["audio"]
    ticks = a["ticks"]
    gaps, sk, located = dict((c, 0) for c in arm_of), dict((c, 0) for c in arm_of), dict((c, []) for c in arm_of)
    for x in v23accept.audio_losses(a["decoded"], ticks):
        c = cyc(x["t"])
        if c in gaps:
            gaps[c] += 1
            sk[c] += x["k"]
            located[c].append(x)
    lo, hi = fp["armed_cycle"], fp["crc_cycles"][1]
    c0, c1 = fp["crc_cycles"]
    t0 = report["window"]["t_origin"]
    sec = lambda c: (ent[c] - t0) // TB_HZ
    views = (("all", lambda c: True),
             ("inside", lambda c: lo <= c <= hi), ("outside", lambda c: not (lo <= c <= hi)),
             ("crc_only", lambda c: c0 <= c <= c1), ("not_crc", lambda c: not (c0 <= c <= c1)),
             ("seconds_20_29", lambda c: sec(c) in IN_S), ("other_seconds", lambda c: sec(c) not in IN_S))
    out = {}
    for name, keep in views:
        v = {}
        per = {}
        for arm, an in ((u045arms.v24accept.HALF, "half"), (u045arms.v24accept.FULL, "full")):
            cs = [c for c in sorted(arm_of) if arm_of[c] == arm and keep(c)]
            ticks_in = sum(ent[c + 1] - ent[c] for c in cs)
            counted = sum(bisect.bisect_left(ticks, ent[c + 1]) - bisect.bisect_left(ticks, ent[c]) for c in cs)
            per[an] = [gaps[c] for c in cs]
            v[an] = {"cycles": len(cs), "loss_gaps": sum(per[an]), "sum_k": sum(sk[c] for c in cs),
                     "cycle_ticks": ticks_in, "counted_blocks": counted}
            if name in ("all", "inside", "outside"):
                P = v23accept.question_P([x for c in cs for x in located[c]], report["steps"], report["callbacks"],
                                         TB_HZ)
                v[an]["P"] = dict((k, n) for k, n in P["counts"].items() if n)
        v["S"] = s_stats(per["half"], per["full"], trials)
        out[name] = v
    return out


def rate(blocks, seconds):
    return blocks / float(seconds)


def traces():
    """RUN 39's and RUN 40's reports, built by the frozen builders from the versioned fixtures."""
    rep39 = v23report.build(_read(os.path.join(FXD, FAMILY[39] + ".log")),
                            _read(os.path.join(FXD, FAMILY[39] + "-trace.bin"), "rb"))
    rep40 = v24report.build(_read(os.path.join(FXD, FAMILY[40] + ".log")),
                            _read(os.path.join(FXD, FAMILY[40] + "-trace.bin"), "rb"))
    return rep39, rep40


def derive(trials=TRIALS, reports=None):
    runs = {}
    for n, stem in sorted(FAMILY.items()):
        runs[n] = per_second(_read(os.path.join(FXD, stem + ".log")))
    rep39, rep40 = reports or traces()
    fp = {39: footprint(rep39), 40: footprint(rep40)}
    return {"per_second": runs,
            "footprint": fp,
            "traces": {39: trace_split(rep39, fp[39]), 40: trace_split(rep40, fp[40])},
            "arms": arms_split(rep40, fp[40], trials),
            "status": "DESCRIPTIVE: restates published figures with L2's window excluded; decides nothing"}


def main(argv):
    d = derive()
    print("C's window, lost AUDIO blocks: whole 64 s | outside 54 s | inside 10 s (s20-29) | outside without s30")
    for n, r in sorted(d["per_second"].items()):
        w, o, i, o53 = r["whole"], r["outside"], r["inside"], r["outside_without_s30"]
        print("  RUN %d  %5d /64 = %6.3f/s | %5d /54 = %6.3f/s | %4d /10 = %6.3f/s | %5d /53 = %6.3f/s"
              % (n, w["blocks"], rate(w["blocks"], 64), o["blocks"], rate(o["blocks"], 54), i["blocks"],
                 rate(i["blocks"], 10), o53["blocks"], rate(o53["blocks"], 53)))
    for n, fp in sorted(d["footprint"].items()):
        print("  RUN %d  CRC steps: cycles %d-%d, %.4f-%.4f s into C's window, %d ticks median; armed in cycle %d"
              % (n, fp["crc_cycles"][0], fp["crc_cycles"][1], fp["crc_from_ticks"] / float(TB_HZ),
                 fp["crc_to_ticks"] / float(TB_HZ), fp["crc_step_ticks"]["p50"], fp["armed_cycle"]))
    for n, t in sorted(d["traces"].items()):
        for side in ("inside", "outside"):
            s = t[side]
            print("  RUN %d  %-7s %4d cycles  %4d loss gaps (%.4f/cycle)  Sum k %4d  P %s  first tenth %d"
                  % (n, side, s["cycles"], s["loss_gaps"], s["loss_gaps"] / float(s["cycles"]), s["sum_k"],
                     json.dumps(s["P"], sort_keys=True), s["first_tenth"]))
    print("RUN 40 by arm (QUESTION S's arithmetic):")
    for name, v in d["arms"].items():
        h, f, s = v["half"], v["full"], v["S"]
        print("  %-14s half %4d cyc %3d gaps (%.4f) Sum k %3d over %.3f s | full %4d cyc %3d gaps (%.4f) Sum k %3d "
              "over %.3f s | ratio %.4f, 90 %% CI [%.4f, %.4f], p %.5f"
              % (name, h["cycles"], h["loss_gaps"], h["loss_gaps"] / float(h["cycles"]), h["sum_k"],
                 h["cycle_ticks"] / float(TB_HZ), f["cycles"], f["loss_gaps"], f["loss_gaps"] / float(f["cycles"]),
                 f["sum_k"], f["cycle_ticks"] / float(TB_HZ), s["ratio"], s["ci90"][0], s["ci90"][1], s["p"]))
        for an in ("half", "full"):
            x = v[an]
            print("      %s: %.3f blocks/s by Sum k, %.3f by the count deficit%s" % (
                an, x["sum_k"] * TB_HZ / float(x["cycle_ticks"]),
                (BLOCKS_PER_S * x["cycle_ticks"] / float(TB_HZ) - x["counted_blocks"]) * TB_HZ / float(x["cycle_ticks"]),
                ("; P " + json.dumps(x["P"], sort_keys=True)) if "P" in x else ""))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(d, f, sort_keys=True, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
