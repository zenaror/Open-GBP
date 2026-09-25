#!/usr/bin/env python3
"""
tools/v27accept.py — the gates of HARDWARE_TESTS.md §V27 (GitHub Issue #117), the latency round: is the perceived
audio offset the cushion? `TARGET` is the only variable.

    tools/v27accept.py <report JSON from tools/v27report.py> [--declaration <json>] [--json <out>]

FROZEN BEFORE THE IMAGE EXISTS, on synthetic reports only (tests/host/test_v27accept.py). §V27.0-§V27.11 as posted
on #117; the amendment window closed with §V27.11. Nothing here is adjusted after data.
§V27.14 (2026-09-24, before any run) re-froze PHASE 3's failure criterion and its width -- the frozen criterion
`underruns > 0` could not fire inside a 6 s dwell at any visited depth (the READY queue drains in ~47 s) -- and
added the confirmation hold; this file's phase_3 carries it, re-pinned as §V22 AMENDMENT 1 was.

THE REPORT it reads (tools/v27report.py, written with the image) is a JSON with:
  cfg        deep, shallow, floor (samples: today's realisation of 0.500 / 0.125 / 0.09375 s), mute_chunks,
             step_mute_chunks, p2_lo, p2_hi, p2_step, p3_step, p3_dwell_s, caps {p1, p2, p3, session} (seconds)
  assign     null when absent (t5), else {seed, initial, schedule: 18 x "REAL"|"NULL", p2_starts, p2_dirs}
  press      {t_press, before_prompt}                                                                     (t3)
  phases     p1/p2/p3: {t_start, t_end, ended: "complete"|"cap"|"session"|"z"|null}
  switches   one per Phase 1 switch, in order: {seq, kind, from, to, t, discard, answer, t_answer}
             answer is "MORE", "LESS", "SAME" or null (never answered)
  nulling    one per confirmed Phase 2 setting: {seq, start, direction, steps, target, t}
  descent    one per Phase 3 depth: {target, kind: "STEP"|"BISECT"|"CONFIRM", fill_mean, underruns, overflow, dup,
             drop, lost, starved, t_start, t_end, partial}; CONFIRM is §V27.14's hold at the highest failing depth
  seconds    one per whole second of the session: {s, phase (1, 2 or 3; 0 before Phase 1), target, mute (bool),
             settling (bool), count (AUDIO blocks drained), fill (the second's mean fill), underruns, overflow};
             "settling" marks the seconds a transition's after-effects cover. THE ARMS ARE PHASE 1's SECONDS ONLY:
             a Phase 2 setting that happens to sit at 2 048 or 512 is not an arm
  counters   the chain's counters at the end

THE GATES, in §V27's words and numbers
  (t5)  no assignment or no 18-switch schedule in the log         -> the run is unblinded: Phases 1 and 2 VOID
  (t3)  the A press before the prompt                              -> INCONCLUSIVE, as §V26's (s4)
  M1    per arm, over its SETTLED seconds (the arm's target, not a mute second, not a settling second):
        the mean fill lies in [TARGET - 256, TARGET + 16]; and the arms' means differ by DELTA-TARGET +/- 256
        (1 280..1 792 at today's rate)                                                          (§V27.9 O2)
  (t1)  M1 fails                                                   -> INCONCLUSIVE, a build defect; every
                                                                      perceptual result is VOID
  M2/M3 underruns = 0 and overflow = 0 in both arms, over the arm's non-mute seconds
  (t2)  underruns > 0 in either arm                                -> Phase 1 INCONCLUSIVE; M1-M4 still report
  M4    lost AUDIO blocks per second per arm, over the arm's non-mute seconds: REPORTED, not gated
  PHASE 1 (§V27.10): 12 REAL + 6 NULL switches; D = real switches answered in the PREDICTED direction
        (DEEP -> SHALLOW predicts LESS, SHALLOW -> DEEP predicts MORE; SAME or no answer is not predicted).
        nulls judged a change (MORE or LESS) >= 4 of 6  -> INCONCLUSIVE regardless of D
        fewer than 18 answered                          -> INCONCLUSIVE (the cap, §V27.10)
        D >= 10 CONFIRMS   (P = 79/4096 under chance 1/2)
        D <= 6  REFUTES
        D 7..9  UNRESOLVED
  PHASE 2 (§V27.3, t4): fewer than 3 confirmed settings -> INCONCLUSIVE; else the null targets are REPORTED with
        their mean, min and max, in samples and seconds
  PHASE 3 (§V27.11, the criterion and the width re-frozen by §V27.14): a depth FAILS when, over its dwell,
        dup == 0 AND starved > 0 -- the correction stopped holding the level (the DUP could not fire and the ring
        could not give a WANTED chunk: `starved` is gbp_aplay's ring_gated over the dwell, never its starved_steps,
        which also counts the wait after every chunk). A dwell cut before its end with dup == 0 observes nothing
        (no DUP yet; the predicate is over the whole dwell) and is read by neither side; a cut dwell with dup > 0
        has held (dup never decreases). It is NOT the
        depth at which the audio fails: the underrun that follows is
        inevitable but comes ~47 s later, longer than the dwell. The interval (highest failing, lowest holding]
        is the lowest depth THE CORRECTION CAN HOLD; MEASURED when its width is <= 2, else BRACKETED; the
        predicted 145 inside it or not, DESCRIPTIVE. The CONFIRM row (§V27.14 §4), the hold at the highest
        failing depth, is read apart: an underrun in it -> the inevitability OBSERVED, with the hold's length;
        none -> NOT OBSERVED, with the hold's length, never "held".
  The declaration (§V27.6): his words, recorded verbatim beside the counts; they gate nothing here.

EVERY INPUT A GATE DEPENDS ON IS PRINTED (the requirement Issue #115 left: never only in the JSON).
Standard library only; reads the report it is given, writes nothing unless asked.
"""
import json
import sys
from fractions import Fraction

BLOCKS_PER_S = 4096
REAL, NULL = 12, 6
D_CONFIRMS, D_REFUTES = 10, 6
NULLS_CHANGE_MAX = 3                       # >= 4 of 6 judged a change -> INCONCLUSIVE
P2_MIN_SETTINGS = 3
M1_BELOW, M1_ABOVE = 256, 16               # [TARGET - 256, TARGET + 16]
SEP_TOL = 256                              # DELTA-TARGET +/- 256
DUP_FLOOR_MODEL = 145                      # the model §V27.11 asks Phase 3 to test: PUSHES + 1 + BAND
P3_MEASURED_WIDTH = 2                      # §V27.14 §3: (144, 146] tests 145 to +/-1; §V27.11's 8 could not
P_CONFIRMS = Fraction(79, 4096)            # P(D >= 10 | 12, 1/2)


def predicted(sw):
    """The answer §V27.10 predicts for a REAL switch; None for a NULL one."""
    if sw["kind"] != "REAL":
        return None
    return "LESS" if sw["to"] < sw["from"] else "MORE"


def arms(report):
    cfg = report["cfg"]
    return {"DEEP": cfg["deep"], "SHALLOW": cfg["shallow"]}


def arm_seconds(report):
    """Per arm: the settled seconds (M1) and the non-mute seconds (M2-M4)."""
    out = {}
    for name, target in arms(report).items():
        secs = [s for s in report["seconds"] if s["target"] == target and s.get("phase") == 1]
        out[name] = {"target": target,
                     "settled": [s for s in secs if not s["mute"] and not s["settling"]],
                     "live": [s for s in secs if not s["mute"]]}
    return out


def question_M(report):
    a = arm_seconds(report)
    per = {}
    for name in ("DEEP", "SHALLOW"):
        settled, live, t = a[name]["settled"], a[name]["live"], a[name]["target"]
        fill = (sum(s["fill"] for s in settled) / float(len(settled))) if settled else None
        lost = sum(BLOCKS_PER_S - s["count"] for s in live)
        per[name] = {"target": t, "settled_seconds": len(settled), "live_seconds": len(live),
                     "fill_mean": fill,
                     "fill_ok": (fill is not None and t - M1_BELOW <= fill <= t + M1_ABOVE),
                     "underruns": sum(s["underruns"] for s in live),
                     "overflow": sum(s["overflow"] for s in live),
                     "lost_blocks": lost,
                     "lost_per_s": (lost / float(len(live))) if live else None}
    fd, fs = per["DEEP"]["fill_mean"], per["SHALLOW"]["fill_mean"]
    delta = per["DEEP"]["target"] - per["SHALLOW"]["target"]
    sep = (fd - fs) if (fd is not None and fs is not None) else None
    sep_ok = sep is not None and delta - SEP_TOL <= sep <= delta + SEP_TOL
    m1 = per["DEEP"]["fill_ok"] and per["SHALLOW"]["fill_ok"] and sep_ok
    m2 = per["DEEP"]["underruns"] == 0 and per["SHALLOW"]["underruns"] == 0
    m3 = per["DEEP"]["overflow"] == 0 and per["SHALLOW"]["overflow"] == 0
    return {"arms": per, "separation": sep, "separation_band": [delta - SEP_TOL, delta + SEP_TOL],
            "separation_ok": sep_ok, "M1": "PASS" if m1 else "FAIL", "M2": "PASS" if m2 else "FAIL",
            "M3": "PASS" if m3 else "FAIL",
            "M4": dict((n, per[n]["lost_per_s"]) for n in per)}


def phase_1(report, m, unblinded, press_early):
    sw = report.get("switches", [])
    real = [s for s in sw if s["kind"] == "REAL"]
    nulls = [s for s in sw if s["kind"] == "NULL"]
    answered = [s for s in sw if s.get("answer") in ("MORE", "LESS", "SAME")]
    D = sum(1 for s in real if s.get("answer") == predicted(s))
    null_change = sum(1 for s in nulls if s.get("answer") in ("MORE", "LESS"))
    out = {"switches": len(sw), "real": len(real), "nulls": len(nulls), "answered": len(answered),
           "D": D, "null_change": null_change, "p_confirms": str(P_CONFIRMS),
           "schedule_ok": len(real) == REAL and len(nulls) == NULL}
    if unblinded:
        out.update(verdict="VOID", why="the assignment or the schedule is absent from the log (t5): unblinded")
    elif press_early:
        out.update(verdict="INCONCLUSIVE", why="the A press came before the prompt (t3)")
    elif m["M1"] != "PASS":
        out.update(verdict="INCONCLUSIVE", why="M1 failed: the manipulation did not happen (t1); a build defect")
    elif m["M2"] != "PASS":
        out.update(verdict="INCONCLUSIVE", why="underruns in an arm (t2): dropouts contaminate the judgement")
    elif not out["schedule_ok"]:
        out.update(verdict="VOID", why="the schedule is not 12 REAL + 6 NULL (t5)")
    elif null_change > NULLS_CHANGE_MAX:
        out.update(verdict="INCONCLUSIVE",
                   why="%d of %d null switches judged a change (>= 4): the judgement is keyed to the transition, "
                       "not to the lag" % (null_change, len(nulls)))
    elif len(answered) < REAL + NULL:
        out.update(verdict="INCONCLUSIVE", why="%d of 18 switches answered: the schedule is incomplete (cap)"
                                               % len(answered))
    elif D >= D_CONFIRMS:
        out.update(verdict="CONFIRMS", why="D = %d of 12 real switches in the predicted direction (>= 10; "
                                           "P = 79/4096 under chance 1/2); nulls judged a change %d of 6"
                                           % (D, null_change))
    elif D <= D_REFUTES:
        out.update(verdict="REFUTES", why="D = %d of 12 (<= 6): at or below the conservative chance level; "
                                          "the cushion is not what he hears" % D)
    else:
        out.update(verdict="UNRESOLVED", why="D = %d of 12 (7..9): neither" % D)
    return out


def phase_2(report, unblinded, press_early, m1_ok):
    settings = report.get("nulling", [])
    targets = [x["target"] for x in settings]
    out = {"settings": len(settings), "targets": targets}
    if targets:
        out.update(mean=sum(targets) / float(len(targets)), min=min(targets), max=max(targets),
                   mean_s=sum(targets) / float(len(targets)) / BLOCKS_PER_S)
    if unblinded:
        out.update(verdict="VOID", why="unblinded (t5)")
    elif press_early:
        out.update(verdict="INCONCLUSIVE", why="the A press came before the prompt (t3)")
    elif not m1_ok:
        out.update(verdict="INCONCLUSIVE", why="M1 failed (t1)")
    elif len(settings) < P2_MIN_SETTINGS:
        out.update(verdict="INCONCLUSIVE", why="%d of %d settings completed (t4)" % (len(settings), P2_MIN_SETTINGS))
    else:
        floor = report["cfg"]["floor"]
        at_floor = sum(1 for t in targets if t <= floor)
        out.update(verdict="MEASURED", at_floor=at_floor,
                   why="%d settings; null TARGET %d..%d, mean %.1f samples = %.4f s%s"
                       % (len(settings), min(targets), max(targets), out["mean"], out["mean_s"],
                          "; %d at the floor: the residue is bounded below by what remains there" % at_floor
                          if at_floor else ""))
    return out


def depth_fails(row):
    """§V27.14 §1: the correction stopped holding the level over the dwell."""
    return row["dup"] == 0 and row["starved"] > 0


def phase_3(report):
    # a dwell cut before its end with dup == 0 is no observation: no DUP YET (review round 3: a cut 20 ms into
    # 146 turned (144, 146] into a confident (146, 148]); with dup > 0 it has held (dup never decreases). The
    # builder routes the former to descent_unfinished; this guard keeps a report built otherwise from bringing
    # the defect back
    rows = [r for r in report.get("descent", []) if r["kind"] != "CONFIRM" and not (r.get("partial") and r["dup"] == 0)]
    holds = [r for r in report.get("descent", []) if r["kind"] == "CONFIRM"]
    holding = [r["target"] for r in rows if not depth_fails(r)]
    failing = [r["target"] for r in rows if depth_fails(r)]
    unfinished = [r["target"] for r in report.get("descent_unfinished", [])]
    ended = (report.get("phases") or {}).get("p3") or {}
    out = {"depths": len(rows), "holding": holding, "failing": failing, "unfinished": unfinished,
           "ended": ended.get("ended")}
    if not rows:
        out.update(verdict="NOT RUN", why=("no whole dwell: %d cut (%s), ended=%s -- the phase ran and observed nothing"
                                           % (len(unfinished), unfinished, ended.get("ended")) if unfinished else
                                           "no depth recorded"))
    elif not failing:
        out.update(verdict="NOT REACHED",
                   why="no depth failed: the correction held the level at every depth down to %d; the edge lies "
                       "below the descent" % min(holding))
    else:
        lo = max(failing)                               # the highest failing depth is the bracket's low end
        hi = min(t for t in holding if t > lo) if any(t > lo for t in holding) else None
        width = (hi - lo) if hi is not None else None
        out.update(interval=[lo, hi], width=width, model=DUP_FLOOR_MODEL,
                   model_inside=(hi is not None and lo < DUP_FLOOR_MODEL <= hi),
                   verdict="MEASURED" if width is not None and width <= P3_MEASURED_WIDTH else "BRACKETED",
                   why="the lowest depth the correction can hold lies in (%d, %s], width %s -- NOT the lowest depth "
                       "at which audio survives%s"
                       % (lo, hi, width, "; the model's 145 %s" % ("inside" if hi is not None and
                                                                  lo < DUP_FLOOR_MODEL <= hi else "OUTSIDE")))
    if holds:
        h = holds[-1]
        length_s = (h["t_end"] - h["t_start"]) / float(report.get("tb_hz", 40500000))
        out["confirm"] = {"target": h["target"], "underruns": h["underruns"], "length_s": round(length_s, 3),
                          "partial": bool(h.get("partial"))}
        out["confirm"]["verdict"] = "OBSERVED" if h["underruns"] > 0 else "NOT OBSERVED"
        out["confirm"]["why"] = ("an underrun at %d within %.1f s of holding it: the inevitability observed"
                                 % (h["target"], length_s) if h["underruns"] > 0 else
                                 "no underrun at %d in %.1f s of holding it%s -- not observed, never \"held\""
                                 % (h["target"], length_s, " (the hold was cut)" if h.get("partial") else ""))
    return out


def evaluate(report, declaration=None):
    unblinded = not report.get("assign") or len(report["assign"].get("schedule", [])) != REAL + NULL
    press_early = bool(report.get("press", {}).get("before_prompt"))
    m = question_M(report)
    p1 = phase_1(report, m, unblinded, press_early)
    p2 = phase_2(report, unblinded, press_early, m["M1"] == "PASS")
    p3 = phase_3(report)
    return {"test_id": report.get("test_id"), "build_id": report.get("build_id"), "commit": report.get("commit"),
            "unblinded": unblinded, "press_early": press_early, "M": m, "phase1": p1, "phase2": p2, "phase3": p3,
            "counters": report.get("counters"), "cfg": report["cfg"],
            "declaration": declaration}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        report = json.load(f)
    decl = None
    if "--declaration" in argv:
        with open(argv[argv.index("--declaration") + 1], encoding="utf-8") as f:
            decl = json.load(f)
    r = evaluate(report, decl)
    c, m = r["cfg"], r["M"]
    print("%s / %s / %s" % (r["test_id"], r["build_id"], r["commit"]))
    print("  levels  DEEP %d  SHALLOW %d  FLOOR %d samples at %d/s; mute %d chunks, step mute %d; caps p1 %d p2 %d p3 %d "
          "session %d s" % (c["deep"], c["shallow"], c["floor"], BLOCKS_PER_S, c["mute_chunks"], c["step_mute_chunks"],
                            c["caps"]["p1"], c["caps"]["p2"], c["caps"]["p3"], c["caps"]["session"]))
    print("  blinding  assignment %s; press before prompt %s" % ("ABSENT (t5)" if r["unblinded"] else "present",
                                                                 r["press_early"]))
    for name in ("DEEP", "SHALLOW"):
        a = m["arms"][name]
        print("  %-7s target %d  settled s %d  live s %d  fill mean %s  in [%d, %d] %s  underruns %d  overflow %d  "
              "lost %d = %s/s"
              % (name, a["target"], a["settled_seconds"], a["live_seconds"],
                 "-" if a["fill_mean"] is None else "%.1f" % a["fill_mean"], a["target"] - M1_BELOW,
                 a["target"] + M1_ABOVE, a["fill_ok"], a["underruns"], a["overflow"], a["lost_blocks"],
                 "-" if a["lost_per_s"] is None else "%.3f" % a["lost_per_s"]))
    print("  M1 %s  separation %s in [%d, %d] %s;  M2 %s;  M3 %s;  M4 reported above"
          % (m["M1"], "-" if m["separation"] is None else "%.1f" % m["separation"], m["separation_band"][0],
             m["separation_band"][1], m["separation_ok"], m["M2"], m["M3"]))
    p1 = r["phase1"]
    print("  PHASE 1  %-12s switches %d (real %d, null %d), answered %d, D %d, nulls judged a change %d, "
          "P(confirm | chance 1/2) %s: %s"
          % (p1["verdict"], p1["switches"], p1["real"], p1["nulls"], p1["answered"], p1["D"], p1["null_change"],
             p1["p_confirms"], p1["why"]))
    for s in report.get("switches", []):
        print("      switch %2d %-4s %4d -> %4d  discard %5d  answer %-4s predicted %s"
              % (s["seq"], s["kind"], s["from"], s["to"], s["discard"], s.get("answer"), predicted(s)))
    p2 = r["phase2"]
    print("  PHASE 2  %-12s %s" % (p2["verdict"], p2["why"]))
    for x in report.get("nulling", []):
        print("      setting %d  start %d  %s  %d steps -> %d" % (x["seq"], x["start"], x["direction"], x["steps"],
                                                                  x["target"]))
    p3 = r["phase3"]
    print("  PHASE 3  %-12s %s  (ended=%s)" % (p3["verdict"], p3["why"], p3.get("ended")))
    if "confirm" in p3:
        print("  PHASE 3 HOLD  %-12s %s" % (p3["confirm"]["verdict"], p3["confirm"]["why"]))
    for d in report.get("descent", []):
        print("      %-7s target %4d  %-5s fill %s  underruns %d  overflow %d  dup %d  starved %d  drop %d  lost %d"
              % (d["kind"], d["target"], "-" if d["kind"] == "CONFIRM" else
                 ("CUT" if d.get("partial") and d["dup"] == 0 else ("FAILS" if depth_fails(d) else "holds")),
                 "-" if d.get("fill_mean") is None else "%.1f" % d["fill_mean"],
                 d["underruns"], d["overflow"], d["dup"], d["starved"], d["drop"], d["lost"]))
    for d in report.get("descent_unfinished", []):
        print("      %-7s target %4d  CUT   fill %s  underruns %d  overflow %d  dup %d  starved %d  (read by neither side)"
              % (d["kind"], d["target"], "-" if d.get("fill_mean") is None else "%.1f" % d["fill_mean"],
                 d["underruns"], d["overflow"], d["dup"], d["starved"]))
    if decl is not None:
        print("  DECLARATION (his words, gating nothing): %s" % json.dumps(decl, ensure_ascii=False, sort_keys=True))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(r, f, sort_keys=True, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
