#!/usr/bin/env python3
"""tools/v28verdict.py -- reads a gbp-audio-v28 (validation_run) SD log and prints every
pre-registered gate the run's own Hardware Issue (§4 there) freezes. THE ISSUE TEXT IS THE
AUTHORITY; this tool only implements it -- it decides PASS/FAIL/PENDING exactly as written there,
never anything beyond it, and computes no verdict the Issue does not already state.

    tools/v28verdict.py <log-file>

Reads main.c's own tag grammar directly (SYNCPE/SYNCPH via tools/v28syncpe.py; V28_3A/V28_3B/
V28_SWEEP/V28_SWEEP_VERDICT/V28LABEL/V28C2/V28CORR as plain key=value lines, the same `kv()`
convention tools/vevents.py already uses). Standard library only.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v28syncpe  # noqa: E402

PHASE_NAMES = {0: "navigate", 1: "3a", 2: "3b", 3: "sweep"}

# gbp_v28_sweep.h's own enums (src/audio/gbp_v28_sweep.h) -- read directly, not re-derived.
SWEEP_KLASS_GATE, SWEEP_KLASS_INFO = 0, 1
SWEEP_OUTCOME_PASS = 1
SWEEP_GATE_N = 18
SWEEP_VERDICT_NAMES = {0: "PENDING", 1: "PASS", 2: "FAIL"}


def kv(rest):
    """'a=1 b=2 c=xyz' -> {'a': '1', ...}, tools/vevents.py's own kv() convention."""
    out = {}
    for tok in rest.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out.setdefault(k, v)
    return out


def find_all(text, tag):
    """Every `<seq> TAG k=v ...` or bare `TAG k=v ...` line, in order, as a list of dicts."""
    return [kv(m.group(1)) for m in re.finditer(r"^(?:\d+\s+)?%s\s+(.*)$" % re.escape(tag), text, re.M)]


def find_last(text, tag):
    r = find_all(text, tag)
    return r[-1] if r else None


def admissibility(text):
    """The capture layer: every phase's own SYNCPE start+end present, no store overflow/loss, and
    every SYNCPH reason accounted for. A run that fails this is INCONCLUSIVE regardless of what the
    domain gates below say (the Issue's own §4)."""
    syncpe = [r for r in (v28syncpe.parse_syncpe(l) for l in text.splitlines()) if r is not None]
    syncph = [r for r in (v28syncpe.parse_syncph(l) for l in text.splitlines()) if r is not None]
    v28c2 = find_last(text, "V28C2")
    v28corr = find_last(text, "V28CORR")
    problems = []

    started = set(s["p"] for s in syncpe if s["edge"] == "start")
    ended = set(s["p"] for s in syncpe if s["edge"] == "end")
    for p in range(4):
        if p not in started:
            problems.append("phase %d (%s): no SYNCPE start" % (p, PHASE_NAMES.get(p, "?")))
        if p not in ended:
            problems.append("phase %d (%s): no SYNCPE end" % (p, PHASE_NAMES.get(p, "?")))

    if v28c2 is None:
        problems.append("no V28C2 record")
    else:
        for field in ("lost", "ring_discarded", "syncpe_lost", "lines_lost"):
            if field in v28c2 and int(v28c2[field]) != 0:
                problems.append("V28C2 %s=%s (nonzero)" % (field, v28c2[field]))

    if v28corr is None:
        problems.append("no V28CORR record")
    elif int(v28corr.get("overflow", "0")) != 0:
        problems.append("V28CORR overflow=%s (nonzero)" % v28corr["overflow"])

    cut = [(int(h["phase"]), h["reason"]) for h in syncph if h["reason"] != "complete"]

    return {"pass": len(problems) == 0, "problems": problems, "cut_reasons": cut,
            "syncpe_count": len(syncpe), "syncph_count": len(syncph)}


def descent_3a(text):
    """The lowest depth the correction can HOLD -- a MEASUREMENT, not a pass/fail (the Issue's own
    §4, carried over from RUN 43's own template): the last CONFIRM record's own target, whether it
    ran whole (not partial) and clean (no underruns)."""
    rows = find_all(text, "V28_3A")
    confirms = [r for r in rows if int(r["kind"]) == 2]
    if not confirms:
        return {"have": False}
    last = confirms[-1]
    return {"have": True, "target": int(last["target"]), "partial": int(last["partial"]) != 0,
            "clean": int(last["underruns"]) == 0, "underruns": int(last["underruns"]),
            "n_depths": len(rows)}


def hold_3b(text):
    """AHEAD 1 at the T256 anchor for 60 s; AHEAD 2 only if AHEAD 1 saw an underrun (Issue #128
    §2). Also the 32-tap reversal condition (GBP-HW-351, Amendment B): recorded as fired/not fired
    from AHEAD 1's own clean-or-not, never acted on this round."""
    rows = find_all(text, "V28_3B")
    by_ahead = {}
    for r in rows:
        by_ahead[int(r["ahead"])] = r
    a1 = by_ahead.get(1)
    a2 = by_ahead.get(2)
    out = {"have_ahead1": a1 is not None, "have_ahead2": a2 is not None}
    if a1 is not None:
        out["ahead1_clean"] = int(a1["underrun_seen"]) == 0
        out["ahead1_partial"] = int(a1["partial"]) != 0
        out["reversal_fired"] = out["ahead1_clean"]
    if a2 is not None:
        out["ahead2_clean"] = int(a2["underrun_seen"]) == 0
        out["ahead2_partial"] = int(a2["partial"]) != 0
    return out


def sweep(text):
    """gbp_v28_sweep_verdict()'s own 18 GATE rows (TABLE[0..17]); the remaining 9 (T192's own 8
    rungs + the one repositioning move) are recorded but never contribute to the verdict
    (src/audio/gbp_v28_sweep.c's own comment, quoted in the Issue)."""
    rows = find_all(text, "V28_SWEEP")
    verdict_rows = find_all(text, "V28_SWEEP_VERDICT")
    gate_rows = [r for r in rows if int(r["klass"]) == SWEEP_KLASS_GATE]
    info_rows = [r for r in rows if int(r["klass"]) == SWEEP_KLASS_INFO]
    failing_gates = [r for r in gate_rows if int(r["outcome"]) != SWEEP_OUTCOME_PASS]
    verdict = int(verdict_rows[-1]["v"]) if verdict_rows else None
    return {"n_records": len(rows), "n_gate": len(gate_rows), "n_info": len(info_rows),
            "failing_gates": failing_gates, "verdict": verdict,
            "verdict_name": SWEEP_VERDICT_NAMES.get(verdict, "?")}


def label_cost(text):
    r = find_last(text, "V28LABEL")
    if r is None:
        return {"have": False}
    return {"have": True, "renders": int(r["renders"]), "ticks_last": int(r["ticks_last"]),
            "ticks_max": int(r["ticks_max"])}


def analyse(text):
    return {"admissibility": admissibility(text), "descent_3a": descent_3a(text),
            "hold_3b": hold_3b(text), "sweep": sweep(text), "label": label_cost(text)}


def render(out):
    lines = []
    a = out["admissibility"]
    lines.append("ADMISSIBILITY: %s" % ("PASS" if a["pass"] else "FAIL"))
    for p in a["problems"]:
        lines.append("  - %s" % p)
    for phase, reason in a["cut_reasons"]:
        lines.append("  note: phase %d (%s) ended with reason=%s (not `complete`)"
                     % (phase, PHASE_NAMES.get(phase, "?"), reason))

    d = out["descent_3a"]
    if not d["have"]:
        lines.append("3A: no CONFIRM record -- the descent did not reach a confirm hold")
    else:
        lines.append("3A: lowest holding depth target=%d %s %s (over %d depths)"
                     % (d["target"], "whole" if not d["partial"] else "PARTIAL",
                        "clean" if d["clean"] else "underrun=%d" % d["underruns"], d["n_depths"]))

    h = out["hold_3b"]
    if not h["have_ahead1"]:
        lines.append("3B: no AHEAD-1 record")
    else:
        lines.append("3B: AHEAD 1 %s%s" % ("clean" if h["ahead1_clean"] else "UNDERRUN",
                                           " (partial)" if h["ahead1_partial"] else ""))
        if h["have_ahead2"]:
            lines.append("3B: AHEAD 2 %s%s" % ("clean" if h["ahead2_clean"] else "UNDERRUN",
                                               " (partial)" if h["ahead2_partial"] else ""))
        lines.append("3B: 32-tap reversal condition (GBP-HW-351) -- %s (recorded, Amendment B: not "
                     "acted on this round)" % ("FIRED" if h["reversal_fired"] else "not fired"))

    s = out["sweep"]
    lines.append("SWEEP: %d records (%d GATE, %d INFO); verdict=%s"
                 % (s["n_records"], s["n_gate"], s["n_info"], s["verdict_name"]))
    for r in s["failing_gates"]:
        lines.append("  FAIL gate n=%s: from (%s,%s) to (%s,%s) outcome=%s fail_reason=%s"
                     % (r["n"], r["from_t"], r["from_a"], r["to_t"], r["to_a"], r["outcome"], r["fail"]))

    lbl = out["label"]
    if lbl["have"]:
        lines.append("LABEL COST: %d renders, ticks_last=%d, ticks_max=%d (informational, same pump "
                     "slot as 3B's own AHEAD margin)" % (lbl["renders"], lbl["ticks_last"], lbl["ticks_max"]))
    else:
        lines.append("LABEL COST: no V28LABEL record")

    return "\n".join(lines)


def main(argv):
    if len(argv) != 2:
        print("usage: v28verdict.py <log-file>", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        text = f.read()
    print(render(analyse(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
