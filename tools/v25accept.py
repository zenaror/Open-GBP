#!/usr/bin/env python3
"""
tools/v25accept.py — §V25's gates, frozen BEFORE the image exists (GitHub Issue #110).

    tools/v25accept.py <report.json> [--sidecar <l2 file>] [--declaration <json>] [--json <out>]

Phase 6's acceptance on a REAL cartridge. `HARDWARE_TESTS.md` §V25 is the pre-registration:
§V25.0-§V25.6 the Issue body, §V25.7 the Orchestrator's decisions (which govern where they
decide), §V25.8 the readings the Orchestrator confirmed. This module is written before the
image produces any data and is exercised on SYNTHETIC vectors only
(`tests/host/test_v25accept.py`). Nothing here may be edited once data exists.

WHAT IS FROZEN HERE, AND WHERE EACH PART COMES FROM

  L2  UNCHANGED: tools/v22accept.py's question_L2, imported, not copied (§V25.1). The L2
      record is passed only when the report says it is "present" (§V22.9 A1).
  C   UNCHANGED: tools/v22accept.py's question_C (§V25.1): zero OVERFLOW and zero UNDERRUN
      over >= 60 s.
  M   UNCHANGED: tools/v22accept.py's measurement_M (§V25.1). Not a gate.

  R   §V25.2 as §V25.7 1 restates it, read by (r9). NOT A GATE. Blocks lost per second =
      the report's `not_drained` (4096 x the whole 1.000 s windows of C's window, minus the
      blocks they counted) / those whole seconds. The prior is RUN 40's half arm, 8.39
      blocks/s; the band [5.59, 12.59] is INCLUSIVE:
          AS EXPECTED   inside the band
          WORSE         above it          BETTER   below it
      "this run's workload against RUN 40's" -- NEVER "a game's audio load", which is
      impossible by construction (§V25.7 1). 9.23 is reported beside, with its reason, and
      A4.3's no-chain floor as context.

  A   §V25.3 as §V25.7 3(a) and 3(b) decide, read by (r11) and the Orchestrator's reading
      (a). THE OPERATOR IS THE INSTRUMENT: the verdict is HIS, from the declaration. One
      rule overrides it, and only toward GAIN:
          GAIN  iff  his A_STABILITY is FAIL or QUALIFIED
                AND  the decoder's clip counter is > 0
                AND  distortion is the ONLY defect he marked "yes"
      GAIN is a finding about the gain, not instability, and it is NOT PASS: Phase 6 stays
      open. Any other defect marked "yes" leaves his verdict standing, the clip count beside.

  V   §V25.4 as §V25.7 4 decides, read by (r7) and (r10). PASS only if ALL of:
          the video clause HOLDS:  E_outside == 0  AND
                                   E_inside x 2 567 047 476  <=  44 x (t_ai_stop - t_ai_start)
              E_outside = incomplete frames BEFORE + AFTER the AI span - 13
              E_inside  = incomplete frames INSIDE it, by each frame's t_last_block
              the bound is RUN 40's own rate in the two integers it measured -- 44 incomplete
              frames over 2 567 047 476 ticks of the 40.5 MHz timebase -- compared in integers,
              inclusive (§V25.10, AMENDMENT 1). 0.69418272.../s is CONTEXT, never the threshold
          and he reports the PICTURE normal and the CONTROLS responding.
      E_outside != 0 in EITHER direction is not a PASS. A guard against gross breakage, NOT
      a claim the video is unaffected; E_inside's rate is reported beside the half arm's
      0.19/s as CONTEXT.

  PHASE 6 (§V25.5)   CLOSES iff L2, C, A and V are all PASS. Any other combination leaves it
      OPEN, and the report says which clause and why. A partial result is not a partial
      closure. R and M decide nothing.

  INCONCLUSIVE (r12)   the window never opened: every gate. C's window under 60 s, or L2's
      record absent: v22accept's own rules. No declaration: A and V. The frame store full,
      or its incomplete frames not reconciling with FRAMECAP: V's video clause.

THE REPORT (JSON, from the image's log by tools/v25report.py, frozen with the image):

  {"test_id", "build_id", "commit", "window_opened": bool, "phase_reached": str,
   "presses": {"a", "other"}, "presses_after": int, "press_before_prompt": bool,
   "window": {...}          tools/v22accept.py's shape, unchanged (C, and R's not_drained)
   "m": {...}               tools/v22accept.py's shape, unchanged
   "calibration": {"rest_sum", "rest_n", "pmin", "pmax"}           REPORTED, never gated
   "clipped": int                                                  the decoder's clip counter
   "video": {"framecap_incomplete", "stored", "store_full", "before", "inside", "after",
             "per_second": [int, ...], "t_ai_start", "t_ai_stop"},
   "l2_sidecar": "present" | "absent: <why>"}

THE DECLARATION (JSON, a structured transcription of the Operator's words, recorded
verbatim on the Hardware Issue first):

  {"a_stability": "PASS" | "FAIL" | "QUALIFIED",
   "defects": {"dropouts", "stutter", "clicks", "crackle", "wobble", "distortion":
               "yes" | "no" | "unsure"},
   "a_words": str, "a_fidelity": str,
   "picture": "normal" | "not normal", "picture_words": str,
   "controls": "responded" | "did not", "controls_words": str}

  A malformed declaration is REFUSED (ValueError), and so is a contradictory one: PASS with a
  defect marked "yes". A refusal is a transcription to redo with him, never a verdict.

Standard library only. Reads a report, a sidecar and a declaration; writes the JSON it is asked
to; authorises nothing.
"""
import json
import os
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v22accept  # noqa: E402

# ---------------------------------------------------------------- frozen constants

TB_HZ = 40500000
RATE = 4096

# R (§V25.7 1, (r9))
R_PRIOR = Fraction(839, 100)          # RUN 40's half arm: Sum k = 266 blocks over 31.690 s
R_BAND = (Fraction(559, 100), Fraction(1259, 100))   # 1.5 x, INCLUSIVE
R_BESIDE = Fraction(923, 100)
R_BESIDE_WHY = ("RUN 40's half arm by the per-cycle COUNT split (292.6 blocks): arrival jitter at cycle "
                "boundaries moves blocks between arms -- the two arms' count deficits sum to 1236 against "
                "the window's 1216.2")
R_FLOOR = ("A4.3, this cartridge on play-0001 with no chain: a fixed 67-72-block start-up deficit, about "
           "0 blocks/s in steady state -- a FLOOR, not an expectation")
R_DIFFERENCES = (
    "(i) no §V23/§V24 recorder: cheaper, toward BETTER",
    "(ii) no interleave with 16-push chunks",
    "(iii) a moving picture: play-0001's event machinery (RUN 21 filled 16384 events in 273.8 s)",
    "(iv) presses: each KEY line is a ringlog vsnprintf (RUN 40 had 3)",
    "(v) the VI hand-over restored (two register writes per presented frame)",
)
R_READING = ("this run's workload against RUN 40's -- one run cannot separate the five differences; never "
             "\"a game's audio load\", which the chain cannot have (§V25.7 1)")

# V (§V25.7 4, (r7), (r10))
START_UP_SIGNATURE = 13
# §V25.10 AMENDMENT 1: RUN 40's own integers, never a decimal. A run exactly at RUN 40's rate HOLDS,
# with equality: E_inside x V_REF_TICKS <= V_REF_E x (t_ai_stop - t_ai_start), in 40.5 MHz ticks
V_REF_E = 44                          # RUN 40's incomplete frames inside its AI span (FRAMECAP 57 = 13 + 44)
V_REF_TICKS = 2567047476              # RUN 40's AI span, t_ai_stop - t_ai_start (LIVET2)
V_CONTEXT = "RUN 40's half arm: 0.19/s (6 of 44 by gap time, DESCRIPTIVE -- GBP-HW-334), CONTEXT only"

# A (§V25.7 3(a), 3(b), (r11))
A_VERDICTS = ("PASS", "FAIL", "QUALIFIED")
DEFECTS = ("dropouts", "stutter", "clicks", "crackle", "wobble", "distortion")
DEFECT_ANSWERS = ("yes", "no", "unsure")
PICTURE = ("normal", "not normal")
CONTROLS = ("responded", "did not")


def _f(x):
    return None if x is None else float(x)


# ------------------------------------------------------------------- QUESTION R

def question_R(report):
    """§V25.2 as §V25.7 1 restates it, (r9). A measurement against a prior; decides nothing."""
    w = report["window"]
    out = {"reading": None, "why": "", "blocks_lost_per_s": None, "not_drained": w.get("not_drained"),
           "seconds": len(w.get("coverage", [])),
           "per_second_lost": [RATE - c for c in w.get("coverage", [])],
           "prior": float(R_PRIOR), "band": [float(R_BAND[0]), float(R_BAND[1])],
           "beside": float(R_BESIDE), "beside_why": R_BESIDE_WHY, "floor": R_FLOOR,
           "differences": list(R_DIFFERENCES), "interpretation": R_READING}
    if not report.get("window_opened") or not w.get("coverage"):
        out.update(reading="NOT MEASURED", why="no whole 1.000 s window of C's was counted")
        return out
    rate = Fraction(w["not_drained"], len(w["coverage"]))
    out["blocks_lost_per_s"] = float(rate)
    if rate > R_BAND[1]:
        out.update(reading="WORSE", why="%.3f blocks/s, above the band [5.59, 12.59]" % rate)
    elif rate < R_BAND[0]:
        out.update(reading="BETTER", why="%.3f blocks/s, below the band [5.59, 12.59]" % rate)
    else:
        out.update(reading="AS EXPECTED", why="%.3f blocks/s, inside the band [5.59, 12.59]" % rate)
    return out


# --------------------------------------------------------- the declaration, checked

def check_declaration(d):
    """Refuses a malformed or contradictory transcription. Returns it unchanged."""
    if not isinstance(d, dict):
        raise ValueError("the declaration is not an object")
    if d.get("a_stability") not in A_VERDICTS:
        raise ValueError("a_stability must be one of %s, not %r" % (A_VERDICTS, d.get("a_stability")))
    defects = d.get("defects")
    if not isinstance(defects, dict) or sorted(defects) != sorted(DEFECTS):
        raise ValueError("defects must name exactly %s" % (DEFECTS,))
    for k in DEFECTS:
        if defects[k] not in DEFECT_ANSWERS:
            raise ValueError("defects[%r] must be one of %s, not %r" % (k, DEFECT_ANSWERS, defects[k]))
    if d.get("picture") not in PICTURE:
        raise ValueError("picture must be one of %s, not %r" % (PICTURE, d.get("picture")))
    if d.get("controls") not in CONTROLS:
        raise ValueError("controls must be one of %s, not %r" % (CONTROLS, d.get("controls")))
    for k in ("a_words", "a_fidelity", "picture_words", "controls_words"):
        if not isinstance(d.get(k), str):
            raise ValueError("%s must be his words, as a string (empty if he said nothing)" % k)
    if d["a_stability"] == "PASS" and any(defects[k] == "yes" for k in DEFECTS):
        raise ValueError("PASS with a defect marked yes is contradictory: re-ask him, do not decide for him")
    return d


# ------------------------------------------------------------------- QUESTION A

def question_A(declaration, clipped):
    """§V25.3 with §V25.7 3(a) and 3(b): his verdict, overridden toward GAIN only."""
    out = {"verdict": None, "why": "", "his_verdict": None, "defects_yes": [], "clipped": clipped,
           "a_words": None, "a_fidelity": None,
           "fidelity_note": "A-FIDELITY is his words and NOT gated: the chain carries nothing above ~2 kHz "
                            "(4096 samples/s), and whether the stream is L, R or a mix is UNKNOWN (§V25.7 3(a))",
           "blinding": "none used, claimed or possible, and that is not a defect here (§V25.3)"}
    if declaration is None:
        out.update(verdict="INCONCLUSIVE", why="no declaration: the Operator is the instrument and has not spoken")
        return out
    d = check_declaration(declaration)
    yes = [k for k in DEFECTS if d["defects"][k] == "yes"]
    out.update(his_verdict=d["a_stability"], defects_yes=yes, a_words=d["a_words"], a_fidelity=d["a_fidelity"])
    if d["a_stability"] == "PASS":
        out.update(verdict="PASS", why="he reports the game's audio sounds as it should")
    elif clipped > 0 and yes == ["distortion"]:
        out.update(verdict="GAIN", why="he reports %s, the decoder clipped %d samples, and distortion is the ONLY "
                                       "defect he marked: a finding about the gain, NOT instability (§V25.7 3(b)). "
                                       "GAIN is not PASS: Phase 6 stays open and the gain becomes its own decision"
                                       % (d["a_stability"], clipped))
    else:
        out.update(verdict=d["a_stability"],
                   why="his verdict, %s; defects marked yes: %s; the decoder clipped %d samples"
                       % (d["a_stability"], ", ".join(yes) if yes else "none", clipped))
    return out


# ------------------------------------------------------------------- QUESTION V

def video_clause(report):
    """§V25.7 4, (r7) and (r10): E over the start-up signature, located by the frame store."""
    v = report.get("video") or {}
    out = {"verdict": None, "why": "", "E_outside": None, "E_inside": None, "ai_seconds": None,
           "rate": None, "per_second": list(v.get("per_second", [])), "context": V_CONTEXT,
           "label": "a guard against gross breakage, NOT a claim the video is unaffected"}
    if not report.get("window_opened"):
        out.update(verdict="INCONCLUSIVE", why="the window never opened")
        return out
    if v.get("store_full"):
        out.update(verdict="INCONCLUSIVE", why="the frame store filled: its incomplete frames are not all there")
        return out
    parts = v["before"] + v["inside"] + v["after"]
    if v["stored"] != v["framecap_incomplete"] or parts != v["stored"]:
        out.update(verdict="INCONCLUSIVE",
                   why="the frame store does not reconcile: stored %d, FRAMECAP %d, before+inside+after %d"
                       % (v["stored"], v["framecap_incomplete"], parts))
        return out
    ai_ticks = v["t_ai_stop"] - v["t_ai_start"]
    if ai_ticks <= 0:
        out.update(verdict="INCONCLUSIVE", why="no AI span")
        return out
    e_out = v["before"] + v["after"] - START_UP_SIGNATURE
    e_in = v["inside"]
    rate = Fraction(e_in * TB_HZ, ai_ticks)
    out.update(E_outside=e_out, E_inside=e_in, ai_seconds=ai_ticks / float(TB_HZ), rate=float(rate))
    if e_out != 0:
        out.update(verdict="DOES NOT HOLD",
                   why="E outside the AI span is %+d: the start-up signature of 13 changed (%d before, %d after)"
                       % (e_out, v["before"], v["after"]))
    elif e_in * V_REF_TICKS > V_REF_E * ai_ticks:
        out.update(verdict="DOES NOT HOLD",
                   why="E inside the AI span is %d over %d ticks (%.4f/s): %d x 2567047476 > 44 x %d, above RUN "
                       "40's own rate (§V25.10)" % (e_in, ai_ticks, rate, e_in, ai_ticks))
    else:
        out.update(verdict="HOLDS",
                   why="E outside 0; E inside %d over %d ticks (%.4f/s): %d x 2567047476 <= 44 x %d, at or under "
                       "RUN 40's own rate (§V25.10)" % (e_in, ai_ticks, rate, e_in, ai_ticks))
    return out


def question_V(report, declaration):
    """§V25.4: the video clause AND his picture AND his controls. Anything else is reported as it is."""
    vid = video_clause(report)
    out = {"verdict": None, "why": "", "video": vid, "picture": None, "controls": None,
           "picture_words": None, "controls_words": None}
    if declaration is not None:
        d = check_declaration(declaration)
        out.update(picture=d["picture"], controls=d["controls"], picture_words=d["picture_words"],
                   controls_words=d["controls_words"])
    failed = []
    if vid["verdict"] == "DOES NOT HOLD":
        failed.append("the video clause: " + vid["why"])
    if out["picture"] == "not normal":
        failed.append("he reports the picture NOT normal")
    if out["controls"] == "did not":
        failed.append("he reports the controls did NOT respond")
    if failed:
        out.update(verdict="NOT PASS", why="; ".join(failed))
    elif vid["verdict"] == "INCONCLUSIVE" or declaration is None:
        out.update(verdict="INCONCLUSIVE", why="; ".join(x for x in (
            ("the video clause: " + vid["why"]) if vid["verdict"] == "INCONCLUSIVE" else "",
            "no declaration: picture and controls unreported" if declaration is None else "") if x))
    else:
        out.update(verdict="PASS", why="the video clause holds, and he reports the picture normal and the "
                                       "controls responding")
    return out


# ------------------------------------------------------------------------- the run

def evaluate(report, sidecar_bytes=None, declaration=None):
    opened = bool(report.get("window_opened"))
    present = report.get("l2_sidecar") == "present"
    if not opened:
        l2 = {"verdict": "INCONCLUSIVE", "why": "the window never opened: nothing was decoded or played",
              "silence_fraction": None}
        c = {"verdict": "INCONCLUSIVE", "why": "the window never opened", "not_drained": None,
             "overflow": None, "underrun": None, "coverage": [], "fill": []}
    else:
        if present and sidecar_bytes is None:
            l2 = {"verdict": "INCONCLUSIVE", "why": "the report says the L2 record is present, but it was not "
                                                    "supplied to this tool", "silence_fraction": None}
        else:
            l2 = v22accept.question_L2(sidecar_bytes if present else None)
        c = v22accept.question_C(report)
    m = v22accept.measurement_M(report)
    r = question_R(report)
    if opened:
        a = question_A(declaration, int(report.get("clipped", 0)))
        v = question_V(report, declaration)
    else:
        a = question_A(None, int(report.get("clipped", 0)))
        a.update(why="the window never opened")
        v = question_V(report, None)
        v.update(verdict="INCONCLUSIVE", why="the window never opened")
    clauses = (("L2", l2), ("C", c), ("A", a), ("V", v))
    open_ = [(name, q["verdict"], q["why"]) for name, q in clauses if q["verdict"] != "PASS"]
    phase6 = {"verdict": "CLOSES" if not open_ else "STAYS OPEN",
              "why": ("L2, C, A and V all PASS (§V25.5)" if not open_ else
                      "not all four PASS (§V25.5); a partial result is not a partial closure"),
              "clauses_not_pass": [{"clause": n, "verdict": vd, "why": w} for n, vd, w in open_]}
    cal = report.get("calibration") or {}
    reported = {
        "calibration": dict(cal, spread=(cal["pmax"] - cal["pmin"]) if "pmax" in cal and "pmin" in cal else None,
                            note="REPORTED, never gated: a silent span has a spread of a few bits (§V25.7 2(b))"),
        "clipped": report.get("clipped"),
        "l_descriptive": (report.get("window") or {}).get("l"),
        "l_note": "L's period reader, DESCRIPTIVE: QUESTION L does not carry over (§V25.0, (r2))",
        "presses": report.get("presses"), "presses_after": report.get("presses_after"),
        "press_before_prompt": report.get("press_before_prompt"),
        "phase_reached": report.get("phase_reached"),
    }
    corr = v22accept.correction_rate(report, m) if opened and (report.get("window") or {}).get("ticks") else None
    return {"test_id": report.get("test_id"), "build_id": report.get("build_id"), "commit": report.get("commit"),
            "L2": l2, "C": c, "M": m, "R": r, "A": a, "V": v, "phase6": phase6, "reported": reported,
            "corrections": corr}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        report = json.load(f)
    side = decl = None
    if "--sidecar" in argv:
        with open(argv[argv.index("--sidecar") + 1], "rb") as f:
            side = f.read()
    if "--declaration" in argv:
        with open(argv[argv.index("--declaration") + 1], encoding="utf-8") as f:
            decl = json.load(f)
    r = evaluate(report, side, decl)
    print("%s / %s / %s" % (r["test_id"], r["build_id"], r["commit"]))
    for q in ("L2", "C", "A", "V"):
        print("  %-3s %-13s %s" % (q, r[q]["verdict"], r[q]["why"]))
    if r["L2"].get("silence_fraction") is not None:
        print("      silence fraction of the L2 window: %.4f (§V22.9 A2)" % r["L2"]["silence_fraction"])
    a = r["A"]
    print("      A-FIDELITY, his words, NOT gated: %r" % a["a_fidelity"])
    print("      %s" % a["fidelity_note"])
    v = r["V"]["video"]
    print("      video: E outside %s, E inside %s over %s s = %s/s; %s" % (
        v["E_outside"], v["E_inside"], None if v["ai_seconds"] is None else "%.3f" % v["ai_seconds"],
        None if v["rate"] is None else "%.4f" % v["rate"], v["context"]))
    print("      video per second of the AI span: %s" % v["per_second"])
    print("      picture %s (%r); controls %s (%r)" % (r["V"]["picture"], r["V"]["picture_words"],
                                                       r["V"]["controls"], r["V"]["controls_words"]))
    rr = r["R"]
    print("  R   %-13s %s -- NOT A GATE" % (rr["reading"], rr["why"]))
    print("      prior 8.39 blocks/s (RUN 40's half arm); beside it 9.23: %s" % rr["beside_why"])
    print("      %s" % rr["floor"])
    print("      reading: %s" % rr["interpretation"])
    for d in rr["differences"]:
        print("        %s" % d)
    print("      blocks lost per whole second of C's window: %s" % rr["per_second_lost"])
    m = r["M"]
    if m.get("rate_hz"):
        print("  M   AI rate %.3f Hz over %d callbacks (%+.1f ppm vs 32 000)" % (m["rate_hz"], m["callbacks"],
                                                                             m["ppm_vs_nominal"]))
    else:
        print("  M   %s" % m["why"])
    cal = r["reported"]["calibration"]
    print("  reported: calibration %s; clipped %s; L (DESCRIPTIVE) %s" % (
        {k: cal.get(k) for k in ("rest_sum", "rest_n", "pmin", "pmax", "spread")}, r["reported"]["clipped"],
        r["reported"]["l_descriptive"]))
    p6 = r["phase6"]
    print("  PHASE 6  %s -- %s" % (p6["verdict"], p6["why"]))
    for c in p6["clauses_not_pass"]:
        print("           %s %s: %s" % (c["clause"], c["verdict"], c["why"]))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            f.write(json.dumps(r, indent=2, sort_keys=True, default=_f) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
