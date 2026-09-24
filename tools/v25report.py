#!/usr/bin/env python3
"""
tools/v25report.py — game-0001's log -> the report tools/v25accept.py reads (GitHub Issue #110,
Phase 6's acceptance on a real cartridge, HARDWARE_TESTS §V25).

    tools/v25report.py <GBP-AUDIO-010 log> [--sidecar <l2 file>] [--json <out>]

`tools/v25accept.py` holds §V25's gates and was frozen (54383e6) before the image existed. It reads
a report it does not know how to make. This file makes it, from the LIVE* records
`poc/gbp-audio-game` writes and the probe's own FRAMECAP record, and it is frozen WITH the image,
before any run, for the reason every builder since §V19's is: each choice here is one the data
could otherwise be argued into. None is new; each is §V22's builder's or §V25's readings'.

WHAT IT BUILDS

  window_opened   the window's ORIGIN was set (LIVET t_origin != 0): the press came and the
                  delay passed (§V25.7 2(a), (r1))
  presses         a, other, after, press_before_prompt -- as tools/v22report.py reads them
  window          tools/v22report.py's shape and rules, unchanged: ticks is t_end - t_origin when
                  the window CLOSED (phase done), otherwise t_last_block - t_origin; coverage and
                  fill are the WHOLE 1.000 s windows only; not_drained = 4096 x those windows
                  minus the blocks they counted (R's instrument, (r9)); overflow, underrun, DUP,
                  DROP; l is L's period reader, DESCRIPTIVE ((r2))
  m               the AI callbacks, first and last instant
  calibration     LIVECAL: rest_sum, rest_n, pmin, pmax -- reported, never gated ((r3))
  clipped         LIVEC clipped= ((r4))
  video           LIVEVINC and LIVEVSEC ((r7)); framecap_incomplete is LIVEVINC's own copy of
                  the counter, and the probe's FRAMECAP record must agree with it or the build
                  REFUSES the log; t_ai_start / t_ai_stop from LIVET2
  l2_sidecar      "present" or "absent: <why>", by tools/v22report.py's rule (§V22.9 A1)

A log without LIVEGAME origin=press is not a game-0001 log and is REFUSED.

Standard library only. Reads a log (and checks a file exists); writes a JSON; decides nothing.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v22report  # noqa: E402

TB_HZ = 40500000
RATE = 4096


def build(text, sidecar_path=None):
    recs = v22report.records(text)
    kv = v22report._kv
    if "LIVEGAME" not in recs or kv(recs["LIVEGAME"][0]).get("origin") != "press":
        raise ValueError("no LIVEGAME origin=press record: not a GBP-AUDIO-010 (game-0001) log")
    head = kv(recs["LIVE"][0])
    t = kv(recs["LIVET"][0])
    t2 = kv(recs["LIVET2"][0])
    l = kv(recs["LIVEL"][0])
    c = kv(recs["LIVEC"][0])
    m = kv(recs["LIVEM"][0])
    cal = kv(recs["LIVECAL"][0])
    vinc = kv(recs["LIVEVINC"][0])
    ident = {}
    framecap = None
    for line in text.splitlines():
        mm = re.match(r"^\d{6} IDENT (.*)$", line)
        if mm and not ident:
            ident = kv(mm.group(1))
        mm = re.match(r"^\d{6} FRAMECAP (.*)$", line)
        if mm:
            framecap = int(kv(mm.group(1))["incomplete"])
    tb = int(t["tb_hz"])
    if tb != TB_HZ:
        raise ValueError("timebase %d is not the 40.5 MHz every §V25 window is counted in" % tb)
    if framecap is None or framecap != int(vinc["framecap"]):
        raise ValueError("FRAMECAP incomplete=%s does not agree with LIVEVINC framecap=%s" % (framecap, vinc["framecap"]))
    t_origin, t_end = int(t["t_origin"], 16), int(t["t_end"], 16)
    if head["phase"] == "done" and t_origin:
        ticks = t_end - t_origin
    elif t_origin and int(t2["t_last_block"], 16) > t_origin:
        ticks = int(t2["t_last_block"], 16) - t_origin
    else:
        ticks = 0
    whole = ticks // tb
    coverage = v22report.series(recs, "LIVESEC", "counts")[:whole]
    fill = v22report.series(recs, "LIVEFILL", "fill")[:whole]
    vsec = v22report.series(recs, "LIVEVSEC", "counts")
    if len(vsec) != int(vinc["secs"]):
        raise ValueError("LIVEVSEC carries %d seconds, LIVEVINC says %s" % (len(vsec), vinc["secs"]))
    report = {
        "test_id": ident.get("test"), "build_id": ident.get("build"), "commit": ident.get("commit"),
        "window_opened": bool(t_origin), "phase_reached": head["phase"],
        "presses": {"a": int(head["presses_a"]), "other": int(head["presses_other"])},
        "presses_after": int(head["presses_after"]),
        "press_before_prompt": head["press_before_prompt"] == "1",
        "window": {"ticks": ticks, "coverage": coverage,
                   "l": {"periods": int(l["periods"]), "pmin": int(l["pmin"]), "pmax": int(l["pmax"])},
                   "not_drained": max(0, RATE * len(coverage) - sum(coverage)),
                   "overflow": int(c["overflow"]), "underrun": int(c["underruns"]),
                   "fill": fill, "corrections": {"dup": int(c["dup"]), "drop": int(c["drop"])}},
        "m": {"callbacks": int(m["callbacks"]), "t_first": int(m["t_first"], 16),
              "t_last": int(m["t_last"], 16), "frames_per_callback": int(m["frames_per_callback"])},
        "calibration": {"rest_sum": int(cal["rest_sum"]), "rest_n": int(cal["rest_n"]),
                        "pmin": int(cal["pmin"]), "pmax": int(cal["pmax"])},
        "clipped": int(c["clipped"]),
        "video": {"framecap_incomplete": int(vinc["framecap"]), "stored": int(vinc["stored"]),
                  "store_full": int(vinc["store_full"]), "before": int(vinc["before"]),
                  "inside": int(vinc["inside"]), "after": int(vinc["after"]), "per_second": vsec,
                  "sec_overflow": int(vinc["sec_overflow"]),
                  "t_ai_start": int(t2["t_ai_start"], 16), "t_ai_stop": int(t2["t_ai_stop"], 16)},
    }
    save = recs.get("LIVEL2SAVE")
    if not save:
        why = "the log records no attempt to save it"
    else:
        s = kv(save[-1])
        if (s["open"], s["write"], s["close"]) != ("0", "0", "0"):
            why = "the log says its save failed (open=%s write=%s close=%s)" % (s["open"], s["write"], s["close"])
        elif sidecar_path is not None and not os.path.exists(sidecar_path):
            why = "the file %s is missing" % sidecar_path
        else:
            why = None
    report["l2_sidecar"] = "present" if why is None else "absent: " + why
    return report


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    side = argv[argv.index("--sidecar") + 1] if "--sidecar" in argv else None
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        rep = build(f.read(), side)
    text = json.dumps(rep, indent=2, sort_keys=True)
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
