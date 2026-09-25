#!/usr/bin/env python3
"""
tools/v28budget.py — GitHub Issue #122: the next sync session's budget, in EVENTS and in the SECONDS they buy, beside
the PHASE budget it has to hold and the MEMORY that pays for both. DESCRIPTIVE arithmetic on RUN 43's versioned log; it
decides nothing and sets no size. The Orchestrator freezes §V28 against these figures.

    tools/v28budget.py [--json <out>]

THE RATE is RUN 43's, as tools/vevents.py measures it (16 384 records over 249.734 s of capture, GBP-HW-344). Beside it:
the margin the proposal carries (x 1.2, which the guard rounds up to 79/s), one record per frame at 59.727 Hz, and the
episode path's 5/3 per frame, which bounds the episode path only.

THE SPANS are counted from the capture start, where the store starts filling. The session's own cap is 720 s from the
ORIGIN; the safety wall is 785 s from the CONTROL transform, 0.108 s before the capture start in RUN 43 (CLOCKS epoch
and capture_start). The latest origin a press in time can give is 51.11 s after the control transform
(poc/gbp-audio-sync/source/main.c, the PLAY_SAFETY_SECONDS comment).

THE MEMORY is sync-0001's, from RUN 43's ENVMEM / ENVSTORE / SYNCCFG2: bss_end, arena1_hi, the three 614 400 B
framebuffers allocated above bss_end, 64 B per event record, 192 B per frame record, the ride-along's raw store of
awr_blocks x 4 096 B. A static store's change moves bss_end one for one, and the free arena is arena1_hi less
bss_end + the framebuffers rounded up to a 4 KiB page (RUN 43: exactly its 2 269 184 B; alignment padding a new layout
adds is not modelled). The HEAP FLOOR is the smallest free arena a physical run has had and still saved to SD:
`ENVFULL arena1_free=1650688`, GBP-HW-262 (RUN 14 / RUN 15, stream-0014; the same figure on stream-0015 in RUN 16-18,
HARDWARE_TESTS.md). That sync-0001's save needs no more is INFERENCE (the same save path).
A WALL of W seconds needs an event store of W x 79 and a frame store of W x 60 records (the frame store's own guard,
main.c); the ceiling is the largest W whose two stores leave the free arena at or above the floor. What remains above
the floor is also counted in 76 800 B units (one 240x160 RGB5A3 texture), with and without a 16 384 B double-buffered
label texture.

THE PHASES are §V27's caps (SYNCCFG2), RUN 43's actual durations (LIVET, SYNCPH), and the session plans set out in the
#122 report. A plan names its phases and its session cap. Phase 0 has no cap in gbp_async (it lasts until his first
press), so a plan gives it an ALLOWANCE and the session cap sits above the phases' sum by a SLACK: the seconds Phase 0
may overrun before the session cap cuts the plan's last phase. The plan's wall is its session cap plus §V27's 65 s
(785 - 720: the latest origin, 51.11 s, and 13.89 s above it); its stores are the wall at the guards' rates; the records
it needs run from the capture start to the latest origin's session end, at the measured rate and at x 1.2.

Standard library only; reads the fixture, writes the JSON it is asked to.
"""
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vevents  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN43 = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-25-sync-0001-run43.log")
HEAP_FLOOR = 1650688          # GBP-HW-262: ENVFULL arena1_free=1650688 (RUN 14/15, stream-0014), saved to SD
MARGIN = 1.2
GUARD_EVENTS_PER_S = 79       # ceil(65.606 x 1.2)
GUARD_FRAMES_PER_S = 60       # main.c: PLAY_FRAME_RECORDS >= PLAY_SAFETY_SECONDS * 60u
WALL_S = 785                  # PLAY_SAFETY_SECONDS, from the control transform
SESSION_S = 720               # cap_session, from the origin
LATEST_ORIGIN_S = 51.11       # from the control transform
AWR_BLOCK = 4096
PAGE = 4096
TEXTURE = 76800               # one 240x160 RGB5A3 frame
LABEL = 16384                 # a 256x16 RGB5A3 label, double-buffered
WALL_ABOVE_SESSION_S = 65     # 785 - 720 (§V27.10)
P0_ALLOWANCE_S = 60           # a proposal: RUN 43's Phase 0 took 38.47 s
SLACK_S = 60                  # a proposal: Phase 0 may run 60 s past its allowance before the last phase is cut
PLANS = {
    # name: ([(phase, seconds, what the seconds are)], session cap or None for sum + SLACK_S)
    "v27_as_frozen": ([("p0", None, "RUN 43"), ("p1", 300, "cap"), ("p2", 240, "cap"), ("p3", 180, "cap")], 720),
    "v27_with_3b": ([("p0", None, "RUN 43"), ("p1", 300, "cap"), ("p2", 240, "cap"), ("p3", 198, "3a + 3b")], 720),
    "validation_run": ([("p0", P0_ALLOWANCE_S, "allowance"), ("3a", 138, "§V27 budget"),
                        ("3b", 120, "AHEAD holds: 1, then 2 on an underrun"), ("sweep", 60, "ROTATE steps")], None),
    "perceptual_no_phase1": ([("p0", P0_ALLOWANCE_S, "allowance"), ("nulling", 240, "cap")], None),
    "perceptual_phase1": ([("p0", P0_ALLOWANCE_S, "allowance"), ("p1", 220, "cap"), ("nulling", 240, "cap")], None),
    "one_session_descent_first": ([("p0", P0_ALLOWANCE_S, "allowance"), ("3a", 138, "§V27 budget"),
                                   ("3b", 120, "AHEAD holds"), ("washout", 60, "at 512 / AHEAD 4"),
                                   ("nulling", 240, "cap")], None),
}


def rec(text, tag):
    m = re.search(r"^\d{6} %s (.*)$" % tag, text, re.M)
    if not m:
        raise ValueError("no %s record" % tag)
    return vevents.kv(m.group(1))


def facts(text):
    ev = vevents.analyse(text)
    clocks, mem, store, cfg2 = rec(text, "CLOCKS"), rec(text, "ENVMEM"), rec(text, "ENVSTORE"), rec(text, "SYNCCFG2")
    livet = rec(text, "LIVET")
    tb = int(clocks["tb_hz"])
    cs = int(clocks["capture_start"], 16)
    ph = dict((int(k["phase"]), k) for k in (vevents.kv(m) for m in re.findall(r"^\d{6} SYNCPH (.*)$", text, re.M)))
    n_xfb, xfb = (int(x) for x in mem["xfb"].split("x"))
    t_origin = int(livet["t_origin"], 16)
    return {"rate": ev["per_s"], "tb": tb, "capture_after_control_s": (cs - int(clocks["epoch"], 16)) / float(tb),
            "origin_s": (t_origin - cs) / float(tb), "arena1_free": int(mem["arena1_free"]),
            "bss_end": int(mem["bss_end"], 16), "arena1_lo": int(mem["arena1_lo"], 16),
            "arena1_hi": int(mem["arena1_hi"], 16), "xfb_bytes": n_xfb * xfb,
            "event_bytes": int(mem["events_bytes"]), "event_record": int(mem["events_bytes"]) // int(
                store["events"].split("/")[0]),
            "frame_bytes": int(mem["frames_bytes"]), "frame_record": int(mem["frames_bytes"]) // int(
                store["frames"].split("/")[0]),
            "awr_bytes": int(cfg2["awr_blocks"]) * AWR_BLOCK,
            "caps": {"p1": int(cfg2["cap_p1"]), "p2": int(cfg2["cap_p2"]), "p3": int(cfg2["cap_p3"]),
                     "session": int(cfg2["cap_session"])},
            "actual": {"p0": (int(ph[1]["t_start"], 16) - t_origin) / float(tb),
                       "p1": (int(ph[1]["t_end"], 16) - int(ph[1]["t_start"], 16)) / float(tb),
                       "p2_until_stop": (int(rec(text, "SYNCEND")["t"], 16) - int(ph[2]["t_start"], 16)) / float(tb)}}


def rates(f):
    return {"measured": f["rate"], "margin": f["rate"] * MARGIN, "one_per_frame": vevents.FRAME_HZ,
            "episode_ceiling": vevents.EPISODE_CEILING * vevents.FRAME_HZ}


def need(seconds, rate):
    return int(math.ceil(seconds * rate - 1e-9))


def free_arena(f, events, frames, awr_kept):
    """The free arena with stores of `events` and `frames` records, with or without the ride-along's store."""
    delta = (events * f["event_record"] - f["event_bytes"]) + (frames * f["frame_record"] - f["frame_bytes"]) \
        - (0 if awr_kept else f["awr_bytes"])
    lo = -(-(f["bss_end"] + delta + f["xfb_bytes"]) // PAGE) * PAGE
    return f["arena1_hi"] - lo


def option(f, events, frames, awr_kept):
    free = free_arena(f, events, frames, awr_kept)
    room = free - HEAP_FLOOR
    return {"events": events, "frames": frames, "awr_kept": awr_kept, "event_bytes": events * f["event_record"],
            "arena1_left": free, "above_floor": room, "floor_kept": room >= 0,
            "units": max(0, room // TEXTURE), "units_with_label": max(0, (room - LABEL) // TEXTURE),
            "seconds": dict((k, events / r) for k, r in rates(f).items())}


def largest_events(f, frames, awr_kept):
    """The largest event store that keeps the floor. Page rounding makes the first estimate miss either way."""
    n = max(0, (free_arena(f, 0, frames, awr_kept) - HEAP_FLOOR) // f["event_record"])
    while free_arena(f, n + 1, frames, awr_kept) >= HEAP_FLOOR:
        n += 1
    while n > 0 and free_arena(f, n, frames, awr_kept) < HEAP_FLOOR:
        n -= 1
    return n


def wall_ceiling(f, awr_kept):
    """The largest whole-second wall whose event (x79/s) and frame (x60/s) stores keep the floor."""
    w = 0
    while free_arena(f, (w + 1) * GUARD_EVENTS_PER_S, (w + 1) * GUARD_FRAMES_PER_S, awr_kept) >= HEAP_FLOOR:
        w += 1
    return w


def plans(f):
    r = rates(f)
    out = {}
    for name, (rows, cap) in PLANS.items():
        secs = [(p, f["actual"]["p0"] if s is None else s, what) for p, s, what in rows]
        total = sum(s for _p, s, _w in secs)
        cap = int(math.ceil(total + SLACK_S)) if cap is None else cap
        wall = cap + WALL_ABOVE_SESSION_S
        span = LATEST_ORIGIN_S - f["capture_after_control_s"] + cap
        ev, fr = wall * GUARD_EVENTS_PER_S, wall * GUARD_FRAMES_PER_S
        out[name] = {"phases": secs, "sum_s": total, "cap_s": cap, "slack_s": cap - total, "wall_s": wall,
                     "records": {"measured": need(span, r["measured"]), "margin": need(span, r["margin"])},
                     "events": ev, "frames": fr,
                     "awr_kept": option(f, ev, fr, True), "awr_dropped": option(f, ev, fr, False)}
    return out


def analyse(text):
    f = facts(text)
    r = rates(f)
    to_cs = f["capture_after_control_s"]
    spans = {"capture_start_to_origin": f["origin_s"],
             "run43_origin_plus_session": f["origin_s"] + SESSION_S,
             "latest_origin_plus_session": LATEST_ORIGIN_S - to_cs + SESSION_S,
             "wall": WALL_S - to_cs}
    frames_now = f["frame_bytes"] // f["frame_record"]
    phases = [("p0", None, f["actual"]["p0"]), ("p1", f["caps"]["p1"], f["actual"]["p1"]),
              ("p2", f["caps"]["p2"], f["actual"]["p2_until_stop"]), ("p3", f["caps"]["p3"], None),
              ("p3b", 60, None)]
    walls = {"awr_kept": wall_ceiling(f, True), "awr_dropped": wall_ceiling(f, False)}
    return {"facts": f, "rates": r, "spans_s": spans,
            "needed": dict((s, dict((k, need(v, rv)) for k, rv in r.items())) for s, v in spans.items()),
            "phases": [{"phase": p, "cap_s": c, "run43_s": a,
                        "records_at_cap": None if c is None else dict((k, need(c, rv)) for k, rv in r.items()),
                        "records_run43": None if a is None else dict((k, need(a, rv)) for k, rv in r.items())}
                       for p, c, a in phases],
            "plans": plans(f),
            "wall_ceiling_s": walls,
            "options": {"today": option(f, f["event_bytes"] // f["event_record"], frames_now, True),
                        "largest_awr_kept": option(f, largest_events(f, frames_now, True), frames_now, True),
                        "largest_awr_dropped": option(f, largest_events(f, frames_now, False), frames_now, False),
                        "wall785_awr_dropped": option(f, WALL_S * GUARD_EVENTS_PER_S, frames_now, False)},
            "guard_events_per_s": GUARD_EVENTS_PER_S}


def main(argv):
    with open(RUN43, encoding="utf-8", errors="replace") as fh:
        out = analyse(fh.read())
    r = out["rates"]
    print("rates/s: measured %.3f, x%.1f %.3f (guard %d), one per frame %.3f, episode ceiling %.3f"
          % (r["measured"], MARGIN, r["margin"], out["guard_events_per_s"], r["one_per_frame"], r["episode_ceiling"]))
    for s, v in out["spans_s"].items():
        n = out["needed"][s]
        print("%-28s %7.2f s  records: %6d measured  %6d x1.2  %6d one/frame  %6d 5/3"
              % (s, v, n["measured"], n["margin"], n["one_per_frame"], n["episode_ceiling"]))
    for p in out["phases"]:
        print("%-4s cap %s s (RUN 43 %s s): records at cap %s; in RUN 43 %s"
              % (p["phase"], p["cap_s"], "-" if p["run43_s"] is None else "%.2f" % p["run43_s"],
                 p["records_at_cap"] and "%d / %d" % (p["records_at_cap"]["measured"], p["records_at_cap"]["margin"]),
                 p["records_run43"] and "%d / %d" % (p["records_run43"]["measured"], p["records_run43"]["margin"])))
    for k, p in out["plans"].items():
        print("plan %-26s %s = %.2f s; session cap %d s (slack %.2f); wall %d s; records %d measured, %d x1.2; "
              "stores %d events + %d frames: floor %s with the ride-along (%+d B), %s without (%+d B)"
              % (k, " + ".join("%s %.2f" % (n, s) for n, s, _w in p["phases"]), p["sum_s"], p["cap_s"],
                 p["slack_s"], p["wall_s"], p["records"]["measured"], p["records"]["margin"], p["events"],
                 p["frames"], "kept" if p["awr_kept"]["floor_kept"] else "BROKEN", p["awr_kept"]["above_floor"],
                 "kept" if p["awr_dropped"]["floor_kept"] else "BROKEN", p["awr_dropped"]["above_floor"]))
    print("wall ceiling (events x%d/s = %d B/s and frames x%d/s = %d B/s above the floor): %d s with the ride-along, "
          "%d s without" % (GUARD_EVENTS_PER_S, GUARD_EVENTS_PER_S * out["facts"]["event_record"], GUARD_FRAMES_PER_S,
                            GUARD_FRAMES_PER_S * out["facts"]["frame_record"], out["wall_ceiling_s"]["awr_kept"],
                            out["wall_ceiling_s"]["awr_dropped"]))
    for k, o in out["options"].items():
        print("%-20s events %6d frames %6d awr %-5s arena1 left %9d B (%+9d vs floor)  76 800 B units %d (%d with label)  "
              "buys %.1f s measured, %.1f s x1.2, %.1f s 5/3"
              % (k, o["events"], o["frames"], o["awr_kept"], o["arena1_left"], o["above_floor"], o["units"],
                 o["units_with_label"], o["seconds"]["measured"], o["seconds"]["margin"],
                 o["seconds"]["episode_ceiling"]))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as fh:
            json.dump(out, fh, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
