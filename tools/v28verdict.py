#!/usr/bin/env python3
"""tools/v28verdict.py -- reads a gbp-audio-v28 (validation_run) SD log and prints every
pre-registered gate the run's own Hardware Issue (§4 there) freezes. THE ISSUE TEXT IS THE
AUTHORITY; this tool only implements it -- it decides PASS/FAIL/PENDING exactly as written there,
never anything beyond it, and computes no verdict the Issue does not already state.

    tools/v28verdict.py <log-file>

Reads main.c's own tag grammar directly (SYNCPE/SYNCPH via tools/v28syncpe.py; V28_3A/V28_3B/
V28ANCHOR/V28_SWEEP/V28_SWEEP_VERDICT/V28LABEL/V28C2/V28CORR as plain key=value lines, the same
`kv()` convention tools/vevents.py already uses). Standard library only.

UNITS (Issue #131's own Amendment 4, #128's own Amendment A): every TARGET the log carries is in
NATIVE 65536 Hz samples. This tool never compares one against an old-path (4096 Hz) figure; it
prints every TARGET three ways -- native, the old-path equivalent (/16), and milliseconds -- so a
reader used to either unit reads the right number, and no old-unit literal sneaks into a comparison
here the way it did in the ladder itself before Amendment A (gbp_v28_ladder.h's own history).

Z / PARTIAL RUNS (Amendment 5): a phase the run never reached (cut by Z, or the run ended before
reaching it) is NOT a gate failure -- it is simply not evaluated, reported as "not reached", never
FAIL or PASS. Admissibility only requires SYNCPE start+end for phases 0..the last one actually
reached; a phase's own PARTIAL record (3a/3b/sweep all mark one) is what says a REACHED phase was
cut before its own natural end.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v28syncpe  # noqa: E402

PHASE_NAMES = {0: "navigate", 1: "3a", 2: "3b", 3: "sweep"}
N_PHASES = 4

# gbp_v28_sweep.h's own enums (src/audio/gbp_v28_sweep.h) -- read directly, not re-derived.
SWEEP_KLASS_GATE, SWEEP_KLASS_INFO = 0, 1
SWEEP_OUTCOME_PASS = 1
SWEEP_GATE_N = 18
SWEEP_VERDICT_NAMES = {0: "PENDING", 1: "PASS", 2: "FAIL"}

# gbp_v28_ladder.h's own enum gbp_v28_anchor_source.
ANCHOR_SOURCE_NAMES = {"rule": "rule", "default": "default", "none": "none"}

NATIVE_RATIO = 16          # gbp_v28_ladder.h's own GBP_V28_NATIVE_RATIO (65536 / 4096)
NATIVE_RATE_HZ = 65536


def fmt_target(native):
    """'native (old, ms)' -- every TARGET printed in all three units at once, so a reader is never
    left to silently assume which one a bare number is (the exact class of error Amendment A guards
    the ladder itself against)."""
    old = native / NATIVE_RATIO
    ms = native * 1000.0 / NATIVE_RATE_HZ
    return "%d native (%.1f old, %.2f ms)" % (native, old, ms)


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
    """The capture layer: every REACHED phase's own SYNCPE start+end present, no store overflow/
    loss. A phase the run never reached (Z, or the run ended first) is not evaluated -- Amendment 5.
    A run that fails an evaluated check is INCONCLUSIVE regardless of what the domain gates below
    say (the Issue's own §4)."""
    syncpe = [r for r in (v28syncpe.parse_syncpe(l) for l in text.splitlines()) if r is not None]
    syncph = [r for r in (v28syncpe.parse_syncph(l) for l in text.splitlines()) if r is not None]
    v28c2 = find_last(text, "V28C2")
    v28corr = find_last(text, "V28CORR")
    problems = []

    started = set(int(s["p"]) for s in syncpe if s["edge"] == "start")
    ended = set(int(s["p"]) for s in syncpe if s["edge"] == "end")
    reached = started | ended
    last_reached = max(reached) if reached else -1
    not_reached = [p for p in range(N_PHASES) if p not in reached]

    for p in range(last_reached + 1):
        if p not in started:
            problems.append("phase %d (%s): reached but no SYNCPE start" % (p, PHASE_NAMES.get(p, "?")))
        if p not in ended:
            problems.append("phase %d (%s): reached but no SYNCPE end" % (p, PHASE_NAMES.get(p, "?")))

    if v28c2 is None:
        problems.append("no V28C2 record")
    else:
        # RUN 51 (Issue #131/#133/#135): ring_discarded (V28C2's own field, printed from
        # adec2.discarded) is NOT a capture-loss counter -- its own doc comment
        # (gbp_adec2.h) reads "samples the consumer dropped from the ring's head ON
        # PURPOSE". Every downward TARGET transition drives it: 3a's whole descent steps
        # down repeatedly, sweep walks the ladder both ways -- so it is structurally
        # guaranteed nonzero for any validation_run that gets past 3a's own first depth,
        # which is every informative run this round can ever produce. The Issue's own
        # text already says so: "V28C2's own overflow/lost/ring_discarded fields at 0
        # WHERE THE DESIGN SAYS THEY SHOULD BE" -- a qualifier this loop used to ignore,
        # blanket-failing admissibility on a healthy run's own normal descent (RUN 51's
        # own ring_discarded=15695 with zero of the genuine loss counters below). `lost`/
        # `syncpe_lost`/`lines_lost` stay checked: each is a real capture-integrity
        # counter the design DOES guarantee at 0, with no domain mechanism that spends it.
        for field in ("lost", "syncpe_lost", "lines_lost"):
            if field in v28c2 and int(v28c2[field]) != 0:
                problems.append("V28C2 %s=%s (nonzero)" % (field, v28c2[field]))

    if v28corr is None:
        problems.append("no V28CORR record")
    elif int(v28corr.get("overflow", "0")) != 0:
        problems.append("V28CORR overflow=%s (nonzero)" % v28corr["overflow"])

    cut = [(int(h["phase"]), h["reason"]) for h in syncph if h["reason"] != "complete"]
    used_z = any(reason == "z" for _phase, reason in cut)

    return {"pass": len(problems) == 0, "problems": problems, "cut_reasons": cut,
            "not_reached": not_reached, "last_reached": last_reached, "used_z": used_z,
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


def anchor_info(text):
    """Issue #131's own Amendment 1: the anchor 3b actually held at, and where it came from (rule/
    default/none), read from the dedicated V28ANCHOR record -- the only record of an anchor=none
    finding, since V28_3B then has no rows of its own at all."""
    r = find_last(text, "V28ANCHOR")
    if r is None:
        return {"have": False}
    return {"have": True, "target": int(r["target"]), "source": r["source"]}


def hold_3b(text):
    """AHEAD 1 at the anchor for 60 s; AHEAD 2 only if AHEAD 1 saw an underrun (Issue #128 §2).
    Also the 32-tap reversal condition (GBP-HW-351, Amendment B): recorded as fired/not fired from
    AHEAD 1's own clean-or-not, ONLY EVALUABLE when the anchor actually used is T256 (Issue #131's
    own Amendment 1 -- any other anchor, or none, and the reversal is simply not evaluable, never
    fired or not-fired)."""
    rows = find_all(text, "V28_3B")
    anchor = anchor_info(text)
    by_ahead = {}
    for r in rows:
        by_ahead[int(r["ahead"])] = r
    a1 = by_ahead.get(1)
    a2 = by_ahead.get(2)
    out = {"have_ahead1": a1 is not None, "have_ahead2": a2 is not None, "anchor": anchor}
    settled = {r["n"]: r for r in find_all(text, "V28_3BM")}     # Issue #136; absent before RUN 53's build
    for key, r in (("margin_ahead1", a1), ("margin_ahead2", a2)):
        if r is not None and "samples" in r:      # Issue #135's own margin fields; absent in older logs
            out[key] = {"min_ready": int(r["min_ready"]), "min_ring": int(r["min_ring"]),
                        "samples": int(r["samples"])}
            m = settled.get(r["n"])
            if m is not None:
                out[key].update({"ring0": int(m["ring0"]), "min_ring_late": int(m["min_ring_late"]),
                                 "samples_late": int(m["samples_late"])})
    if a1 is not None:
        out["ahead1_clean"] = int(a1["underrun_seen"]) == 0
        out["ahead1_partial"] = int(a1["partial"]) != 0
        # #128's own freeze text (§5): "the anchor used is T256" -- no source qualifier. A clean
        # hold at T256 is the observation named whether that T256 came from the rule or from the
        # frozen default (no confirmed floor at all): both are "the anchor used is T256". An
        # earlier draft of this tool required source=="rule" too, which the freeze never asked
        # for and would have wrongly withheld FIRED from a legitimate T256/default hold -- caught
        # at the Orchestrator's own review of Amendment 1. The source is still reported alongside,
        # never silently dropped, so a reader can tell rule from default apart regardless.
        anchor_is_t256 = anchor["have"] and anchor["target"] == 4096
        out["reversal_evaluable"] = anchor_is_t256
        out["reversal_fired"] = anchor_is_t256 and out["ahead1_clean"]
    if a2 is not None:
        out["ahead2_clean"] = int(a2["underrun_seen"]) == 0
        out["ahead2_partial"] = int(a2["partial"]) != 0
    return out


def sweep(text):
    """gbp_v28_sweep_verdict()'s own 18 GATE rows; every INFO row (T192's own 8 rungs + the
    repositioning move, and, from Issue #135 on, the PRELUDE row that opens the sweep -- 10 INFO rows
    in a log that carries it, 9 in RUN 51's) is recorded but never contributes to the verdict
    (src/audio/gbp_v28_sweep.c's own comment, quoted in the Issue). A log that carries the
    V28_SWEEPM line per record (meas_*, ring, ready, dup, drop, t_land) has them read alongside,
    keyed by n; an older log without them reads exactly as before."""
    rows = find_all(text, "V28_SWEEP")
    verdict_rows = find_all(text, "V28_SWEEP_VERDICT")
    gate_rows = [r for r in rows if int(r["klass"]) == SWEEP_KLASS_GATE]
    info_rows = [r for r in rows if int(r["klass"]) == SWEEP_KLASS_INFO]
    failing_gates = [r for r in gate_rows if int(r["outcome"]) != SWEEP_OUTCOME_PASS]
    verdict = int(verdict_rows[-1]["v"]) if verdict_rows else None
    measured = {r["n"]: r for r in find_all(text, "V28_SWEEPM")}     # Issue #135; absent in RUN 51's log
    cuts = {r["n"]: r for r in find_all(text, "V28_SWEEPC")}         # Issue #136; absent before RUN 53's build
    for n, m in measured.items():
        if n in cuts:
            m.update(cuts[n])
    # Issue #136, pre-registered before RUN 53 (#122 section 1(c)): NO CUT OF THE RING AFTER THE FIRST AUDIBLE
    # HAND-OFF, in any GATE row. Read from the log's own V28_SWEEPC records (cut_rel >= 0 with cut > 0), whatever
    # fail_reason the module gave the row.
    klass_of = {r["n"]: int(r["klass"]) for r in rows}
    late_cuts = sorted((int(n), int(c["cut"]), int(c["cut_rel"])) for n, c in cuts.items()
                       if int(c["cut"]) > 0 and int(c["cut_rel"]) >= 0 and klass_of.get(n) == SWEEP_KLASS_GATE)
    cut_gate = {"recorded": bool(cuts), "late_gate_cuts": late_cuts}
    return {"n_records": len(rows), "n_gate": len(gate_rows), "n_info": len(info_rows), "cut_gate": cut_gate,
            "failing_gates": failing_gates, "info_rows": info_rows, "measured": measured, "verdict": verdict,
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


FAIL_NAMES = {0: "NONE", 1: "OUT_OF_BAND", 2: "UNDERRUN", 3: "UNMASKED", 4: "SPLICE"}    # gbp_v28_sweep.h's enum


def _fail_name(v):
    """The frozen tool printed the bare number; the number stays first, the name follows it (Issue #136 added 4)."""
    try:
        return "%s (%s)" % (v, FAIL_NAMES.get(int(v), "?"))
    except ValueError:
        return v


def _trim_late(m):
    """Issue #136's landing fields (what the landing's trim cut; a rotation abandoned in flight), when the log has them."""
    if "cut" not in m:
        return ""
    return " cut %s (period %s vs unmute) rot_post %s fill_short %s late %s" % (m["cut"], m["cut_rel"], m["rot_post"],
                                                                            m["fill_short"], m["late"])


def render(out):
    lines = []
    a = out["admissibility"]
    lines.append("ADMISSIBILITY: %s" % ("PASS" if a["pass"] else "FAIL"))
    for p in a["problems"]:
        lines.append("  - %s" % p)
    for phase, reason in a["cut_reasons"]:
        lines.append("  note: phase %d (%s) ended with reason=%s (not `complete`)"
                     % (phase, PHASE_NAMES.get(phase, "?"), reason))
    if a["not_reached"]:
        lines.append("  not reached (neither PASS nor FAIL, not evaluated): phase(s) %s"
                     % ", ".join("%d (%s)" % (p, PHASE_NAMES.get(p, "?")) for p in a["not_reached"]))
    if a["used_z"]:
        lines.append("  note: the Operator used Z -- gates for unreached phases above are not evaluated")

    d = out["descent_3a"]
    if not d["have"]:
        lines.append("3A: no CONFIRM record -- the descent did not reach a confirm hold")
    else:
        lines.append("3A: lowest holding depth %s, %s, %s (over %d depths)"
                     % (fmt_target(d["target"]), "whole" if not d["partial"] else "PARTIAL",
                        "clean" if d["clean"] else "underrun=%d" % d["underruns"], d["n_depths"]))

    h = out["hold_3b"]
    anc = h["anchor"]
    if not anc["have"]:
        lines.append("3B: no V28ANCHOR record -- 3b's own phase was never reached")
    elif anc["source"] == "none":
        lines.append("3B: anchor=none (3a's own floor sits above every ladder rung) -- 3b did not hold")
    else:
        lines.append("3B: anchor %s, source=%s" % (fmt_target(anc["target"]), anc["source"]))
        if not h["have_ahead1"]:
            lines.append("3B: no AHEAD-1 record")
        else:
            lines.append("3B: AHEAD 1 %s%s" % ("clean" if h["ahead1_clean"] else "UNDERRUN",
                                               " (partial)" if h["ahead1_partial"] else ""))
            for key, name in (("margin_ahead1", "AHEAD 1"), ("margin_ahead2", "AHEAD 2")):
                m = h.get(key)
                if m is not None:
                    lines.append("3B: %s margin over %d samples: min READY %d, min ring %d (native pushes)"
                                 % (name, m["samples"], m["min_ready"], m["min_ring"]))
                    if "ring0" in m:                       # Issue #136: separates a landing transient from a steady margin
                        lines.append("3B: %s ring at the first sample %d; min ring over the %d samples taken 10 s or "
                                     "more after it %s" % (name, m["ring0"], m["samples_late"],
                                                           m["min_ring_late"] if m["samples_late"] else "(none)"))
            if h["have_ahead2"]:
                lines.append("3B: AHEAD 2 %s%s" % ("clean" if h["ahead2_clean"] else "UNDERRUN",
                                                   " (partial)" if h["ahead2_partial"] else ""))
            if h["reversal_evaluable"]:
                lines.append("3B: 32-tap reversal condition (GBP-HW-351) -- %s, anchor source=%s "
                             "(recorded, Amendment B: not acted on this round)"
                             % ("FIRED" if h["reversal_fired"] else "not fired", anc["source"]))
            else:
                lines.append("3B: 32-tap reversal condition (GBP-HW-351) -- NOT EVALUABLE (the anchor "
                             "used is not T256)")

    s = out["sweep"]
    lines.append("SWEEP: %d records (%d GATE, %d INFO); verdict=%s"
                 % (s["n_records"], s["n_gate"], s["n_info"], s["verdict_name"]))
    for r in s["failing_gates"]:
        lines.append("  FAIL gate n=%s: from %s (ahead %s) to %s (ahead %s) outcome=%s fail_reason=%s"
                     % (r["n"], fmt_target(int(r["from_t"])), r["from_a"], fmt_target(int(r["to_t"])),
                        r["to_a"], r["outcome"], _fail_name(r["fail"])))
        m = s["measured"].get(r["n"])
        if m is not None:                          # Issue #135's own measured fields
            lines.append("    measured from-state: target %s ahead %s ring %s ready %s; landed ring %s ready %s "
                         "residue %s dup %s drop %s%s"
                         % (m["meas_t"], m["meas_a"], m["meas_ring"], m["meas_ready"], m["ring"], m["ready"],
                            r["residue"], m["dup"], m["drop"], _trim_late(m)))

    for r in s["info_rows"]:                       # Issue #135: the prelude's own start state is RUN 52's headline datum
        m = s["measured"].get(r["n"])
        if m is None:
            continue
        lines.append("  INFO n=%s: from %s (ahead %s) to %s (ahead %s) outcome=%s fail_reason=%s residue %s"
                     % (r["n"], fmt_target(int(r["from_t"])), r["from_a"], fmt_target(int(r["to_t"])),
                        r["to_a"], r["outcome"], _fail_name(r["fail"]), r["residue"]))
        lines.append("    measured from-state: target %s ahead %s ring %s ready %s; landed ring %s ready %s "
                     "dup %s drop %s%s"
                     % (m["meas_t"], m["meas_a"], m["meas_ring"], m["meas_ready"], m["ring"], m["ready"],
                        m["dup"], m["drop"], _trim_late(m)))

    cg = s["cut_gate"]
    if not cg["recorded"]:
        lines.append("SWEEP: no cut after unmute (Issue #136 GATE condition) -- NOT RECORDED (this log predates it)")
    elif cg["late_gate_cuts"]:
        lines.append("SWEEP: no cut after unmute (Issue #136 GATE condition) -- FAIL at GATE n=%s"
                     % ", ".join("%d (%d samples, period %d)" % c for c in cg["late_gate_cuts"]))
    else:
        lines.append("SWEEP: no cut after unmute (Issue #136 GATE condition) -- PASS in every GATE row")

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
