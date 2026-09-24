#!/usr/bin/env python3
"""
tools/v26accept.py — §V26's gates, frozen BEFORE the image exists (GitHub Issue #113).

    tools/v26accept.py <report.json> [--sidecar <l2 file>] [--declaration <json>] [--json <out>]

Phase 6's acceptance, second attempt. `HARDWARE_TESTS.md` §V26 is the pre-registration: §V26.0-§V26.6 the
Issue body, §V26.7 the Orchestrator's decisions (which REPLACE §V26.3 and §V26.5), §V26.8 the readings it
confirmed. This module is written before the image produces any data and is exercised on SYNTHETIC vectors
only (`tests/host/test_v26accept.py`). Nothing here may be edited once data exists.

WHAT IT IS: tools/v25accept.py (as amended at 4591f9b) WITH ONE FUNCTION REPLACED -- `video_clause`, V's
start-up clause. L2, C, A, R, M, the GAIN rule, the declaration's checks, V's picture and controls, and
§V25.5's closure are v25accept's own code, run unchanged: `evaluate` swaps the one function in for the
duration of the call and restores it. Nothing else is redefined (a test pins that).

THE REPLACED CLAUSE (§V26.7 1 & 2, readings (s1)-(s6))

  P  = the before-AI incomplete frame IN FLIGHT at the press, if any:
         t_first_block <= t_press < t_first_block of the NEXT stored frame        (at most one)
  Q  = every other before-AI incomplete frame
  B  = the bound, READ FROM THE LOG: the largest close_frame among the run's EPISODE records
       (the preserved start-up episodes; 197 in RUN 40 and RUN 41), in the frame store's own index space

  the start-up clause HOLDS iff  |Q| = 13  AND  every Q frame's store index <= B
  the outside clause HOLDS iff   the start-up clause holds AND no incomplete frame lies AFTER the AI span (s1)
  the video clause HOLDS iff     the outside clause holds AND
                                 E_inside x 2 567 047 476 <= 44 x (t_ai_stop - t_ai_start)   (§V25.10, unchanged)

  INCONCLUSIVE (never FAIL):
    the window never opened; the frame store filled or does not reconcile with FRAMECAP (as §V25);
    the before-AI list is missing, capped (more than 64 frames) or not the length LIVEVINC counts;
    no EPISODE record, so no B;
    P's own index <= B -- an early press can absorb a signature frame, and the rule cannot separate
    the two there (s4)

  REPORTED beside it, deciding nothing: E_outside as §V25 counted it (before + after - 13), P's position
  relative to t_press, Q's indices. THE CONFOUND (§V26.7 3): in this image the press and the first VI
  hand-over coincide, so P cannot be attributed between the console prints and the hand-over; a hand-over
  frame one frame later lands in Q, beyond B, and FAILS.

THE REPORT is tools/v25accept.py's, plus, from tools/v26report.py (frozen with the image):
  "t_press": int
  "video": {..., "before_frames": [[store index, t_first_block, t_last_block, t_next_first_block], ...],
            "before_listed": int, "before_capped": bool, "episodes_close_max": int | null}

Standard library only. Reads a report, a sidecar and a declaration; writes the JSON it is asked to;
authorises nothing.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v25accept  # noqa: E402

TB_HZ = v25accept.TB_HZ
START_UP_SIGNATURE = 13
BEFORE_LIST_CAP = 64


def video_clause(report):
    """§V26.7 1 & 2 with readings (s1)-(s6): V's video clause, replacing v25accept.video_clause."""
    v = report.get("video") or {}
    out = {"verdict": None, "why": "", "E_outside": None, "E_inside": None, "ai_seconds": None, "rate": None,
           "per_second": list(v.get("per_second", [])), "context": v25accept.V_CONTEXT,
           "label": "a guard against gross breakage, NOT a claim the video is unaffected",
           "P": None, "Q_indices": None, "bound": v.get("episodes_close_max"),
           "confound": "P cannot be attributed between the console prints and the first VI hand-over, which "
                       "coincide at the press (§V26.7 3)"}
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
    e_in = v["inside"]
    out.update(E_outside=v["before"] + v["after"] - START_UP_SIGNATURE, E_inside=e_in,
               ai_seconds=ai_ticks / float(TB_HZ), rate=e_in * float(TB_HZ) / ai_ticks)
    frames = v.get("before_frames")
    if frames is None or v.get("before_capped") or len(frames) != v["before"]:
        out.update(verdict="INCONCLUSIVE",
                   why="the before-AI frames are not all located (listed %s of %d%s)"
                       % (None if frames is None else len(frames), v["before"],
                          ", capped at %d" % BEFORE_LIST_CAP if v.get("before_capped") else ""))
        return out
    bound = v.get("episodes_close_max")
    if bound is None:
        out.update(verdict="INCONCLUSIVE", why="no EPISODE record in the log, so no start-up bound")
        return out
    t_press = report.get("t_press") or 0
    p = [f for f in frames if t_press and f[1] <= t_press < f[3]]
    if len(p) > 1:
        out.update(verdict="INCONCLUSIVE", why="%d frames in flight at one press: the store is not ordered" % len(p))
        return out
    q = [f for f in frames if f not in p]
    out.update(P=({"index": p[0][0], "first_ms": (p[0][1] - t_press) * 1e3 / TB_HZ,
                   "last_ms": (p[0][2] - t_press) * 1e3 / TB_HZ, "next_ms": (p[0][3] - t_press) * 1e3 / TB_HZ}
                  if p else None),
               Q_indices=[f[0] for f in q])
    if p and p[0][0] <= bound:
        out.update(verdict="INCONCLUSIVE",
                   why="the press was read inside the start-up span (P's index %d <= %d): P may be a signature "
                       "frame, and the rule cannot separate the two (s4)" % (p[0][0], bound))
        return out
    beyond = [f[0] for f in q if f[0] > bound]
    if v["after"] != 0:
        out.update(verdict="DOES NOT HOLD", why="%d incomplete frame(s) AFTER the AI span (s1)" % v["after"])
    elif len(q) != START_UP_SIGNATURE:
        out.update(verdict="DOES NOT HOLD",
                   why="|Q| = %d, not 13 (%d before the AI, P %s)" % (len(q), v["before"], "present" if p else "absent"))
    elif beyond:
        out.update(verdict="DOES NOT HOLD",
                   why="Q frame(s) %s lie beyond the start-up span (index > %d)" % (beyond, bound))
    elif e_in * v25accept.V_REF_TICKS > v25accept.V_REF_E * ai_ticks:
        out.update(verdict="DOES NOT HOLD",
                   why="E inside the AI span is %d over %d ticks: %d x 2567047476 > 44 x %d (§V25.10)"
                       % (e_in, ai_ticks, e_in, ai_ticks))
    else:
        out.update(verdict="HOLDS",
                   why="|Q| = 13, all within the start-up span (<= %d); P %s; none after; E inside %d over %d "
                       "ticks: %d x 2567047476 <= 44 x %d" % (bound, "present, in flight at the press" if p
                                                               else "absent", e_in, ai_ticks, e_in, ai_ticks))
    return out


class _Replaced(object):
    """v25accept with its one function replaced, for the duration of a call, and restored."""

    def __enter__(self):
        self.saved = v25accept.video_clause
        v25accept.video_clause = video_clause
        return self

    def __exit__(self, *exc):
        v25accept.video_clause = self.saved
        return False


def evaluate(report, sidecar_bytes=None, declaration=None):
    with _Replaced():
        return v25accept.evaluate(report, sidecar_bytes, declaration)


def main(argv):
    with _Replaced():
        rc = v25accept.main(argv)
    if len(argv) >= 2:
        with open(argv[1], encoding="utf-8") as f:
            vid = video_clause(json.load(f))
        print("  V's start-up clause (§V26.7): P %s; Q indices %s; bound %s" % (vid["P"], vid["Q_indices"],
                                                                               vid["bound"]))
        print("      %s" % vid["confound"])
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
