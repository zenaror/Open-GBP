#!/usr/bin/env python3
"""tools/v28null.py -- GitHub Issue #139 / #141: the perceptual run's nulling, read from its SD log (V28_NULL records) as (T, A, L) and the frozen CENSORED verdicts.

    tools/v28null.py <perceptual_no_phase1 log> [--label bounded|assumed|M1|M2]

WHAT THE RUN MEASURES (#128 sections 3-4, the ladder). The Operator moves the audio path's latency one rung at a time along the eight rungs the validation run held (gbp_v28_ladder.h
GBP_V28_RUNG, deepest first: T704A4 ... T256A4, T256A3, T256A2, T256A1) until audio and picture look synchronised, and confirms; every setting starts at a seeded rung with a seeded
mapping of the two stick edges. Each setting is recorded as (T, A) and converted to a modelled L (tools/v28latency.py: ring entry -> the AI's DMA reload, the AUDIO PATH's own latency,
NOT the audio-versus-video offset: what the null says is the audio latency at which he judged the two aligned, the video path and everything outside the audio path being constant).

THE LABEL. L rests on the AI DMA's hand-off semantics (tools/v28latency.py, HARDWARE_TESTS.md V28.26): `bounded` (the default, RUN 56's reading: every L as tabulated or +31.222 ms),
`assumed` (as tabulated), `M1` (RUN 57 resolved AHEAD + 1: as tabulated, CORROBORATED with the address stage assumed identical), `M2` (RUN 57 resolved AHEAD + 2: +31.222 ms). The
tabulated L is INFERENCE in every case (a chunk-start level c = T - 268, valid while the loss is below about 0.65 %).

CENSORED (#128 section 4, per setting and per END, recorded at the moment it happens): a setting confirmed at the FLOOR rung (T256 A1) after at least one press against the floor is
censored at the floor (the null lies at or below it); the mirror, confirmed at the TOP rung (T704 A4) after at least one press against the top, is censored at the top (the null lies at or
above it: the symmetric reading, not named in #128 section 4). VERDICT: fewer than 3 settings completed -> INCONCLUSIVE (t4, section V27.5); every completed setting censored at the floor
-> AT THE VALIDATED FLOOR (T, A, L); every one at the top -> AT THE LADDER'S TOP; otherwise the null is estimated from the uncensored settings and k of n censored (each end) is reported.
Precedence: (t5) the assignment or the randomisation is absent from the log, (t3) a press before the prompt and (t1) the manipulation check are the Executor's mechanistic gates,
tools/v28verdict.py's, not this reader's.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v28latency as L  # noqa: E402

RUNGS = ((11264, 4), (9216, 4), (7168, 4), (5120, 4), (4096, 4), (4096, 3), (4096, 2), (4096, 1))   # gbp_v28_ladder.h GBP_V28_RUNG, deepest first (pinned by tests)
LABELS = ("bounded", "assumed", "M1", "M2")
MIN_SETTINGS = 3


def read_settings(text):
    """Every V28_NULL record as a dict, in order."""
    out = []
    for m in re.finditer(r"^\d{6} V28_NULL (n=.*)$", text, re.M):
        d = dict(re.findall(r"(\S+)=(\S+)", m.group(1)))
        out.append({"n": int(d["n"]), "start": int(d["start"]), "dir": int(d["dir"]), "steps": int(d["steps"]), "deeper": int(d["deeper"]), "shallower": int(d["shallower"]),
                    "floor_refused": int(d["floor_refused"]), "top_refused": int(d["top_refused"]), "rung": int(d["rung"]), "target": int(d["target"]),
                    "ahead": int(d["ahead"]), "t": int(d["t"], 16)})
    return out


def read_mech(text):
    """Every V28_NULLM record (the ring's level and the READY chunks at each confirm, and the underruns / dropped samples during the setting), keyed by n."""
    out = {}
    for m in re.finditer(r"^\d{6} V28_NULLM (n=.*)$", text, re.M):
        d = dict(re.findall(r"(\S+)=(\S+)", m.group(1)))
        out[int(d["n"])] = {k: int(d[k]) for k in ("ring", "ready", "underruns", "overflow")}
    return out


# THE MECHANISTIC GATE, pre-registered (HARDWARE_TESTS.md V28.28), the Executor's and not the Operator's: at each confirm the ring sits at or below the rung's target and no more than a
# chunk and a band and some slack (2 300) under it (RUN 56's 3b hold at T4096: minimum 2 256, i.e. 1 840 under), READY is AHEAD - 1 or AHEAD, and the setting saw no underrun and no dropped sample.
RING_UNDER_MAX = 2300


def gate_of(s, mech):
    if mech is None:
        return None
    return {"fill": s["target"] - RING_UNDER_MAX <= mech["ring"] <= s["target"], "ready": s["ahead"] - 1 <= mech["ready"] <= s["ahead"],
            "underruns": mech["underruns"] == 0, "overflow": mech["overflow"] == 0}


def rung_l(rung):
    t, a = RUNGS[rung]
    return L.latency_ms(L.c_of_target(t), a)


def shift(label):
    """(low, high) added to every tabulated L under the label."""
    return {"bounded": (0.0, L.PERIOD_MS), "assumed": (0.0, 0.0), "M1": (0.0, 0.0), "M2": (L.PERIOD_MS, L.PERIOD_MS)}[label]


def classify(s):
    if s["rung"] == len(RUNGS) - 1 and s["floor_refused"] >= 1:
        return "floor"
    if s["rung"] == 0 and s["top_refused"] >= 1:
        return "top"
    return "interior"


def consistent(s):
    """The record's own (T, A) must be the rung's: a defect in the log otherwise, never a finding."""
    return (s["target"], s["ahead"]) == RUNGS[s["rung"]]


def analyse(text, label="bounded"):
    st = read_settings(text)
    mech = read_mech(text)
    lo, hi = shift(label)
    rows = []
    for s in st:
        cls = classify(s)
        base = rung_l(s["rung"])
        rows.append(dict(s, cls=cls, L=base, L_lo=base + lo, L_hi=base + hi, ok=consistent(s), mech=mech.get(s["n"]), gate=gate_of(s, mech.get(s["n"]))))
    n = len(rows)
    kf = sum(1 for r in rows if r["cls"] == "floor")
    kt = sum(1 for r in rows if r["cls"] == "top")
    inter = [r for r in rows if r["cls"] == "interior"]
    gated = [r for r in rows if r["gate"] is not None]
    out = {"gates": {k: (sum(1 for r in gated if r["gate"][k]), len(gated)) for k in ("fill", "ready", "underruns", "overflow")}, "missing_mech": n_missing(rows),
           "label": label, "settings": rows, "n": n, "k_floor": kf, "k_top": kt, "interior": len(inter), "inconsistent": sum(1 for r in rows if not r["ok"])}
    if n < MIN_SETTINGS:
        out["verdict"] = "INCONCLUSIVE (t4): %d of the %d settings the rule needs completed" % (n, MIN_SETTINGS)
    elif kf == n:
        out["verdict"] = "AT THE VALIDATED FLOOR (T%d, A%d, L %s): every completed setting (%d) confirmed at the floor after pressing against it" % (
            RUNGS[-1][0] // 16, RUNGS[-1][1], fmt(rung_l(len(RUNGS) - 1), lo, hi), n)
    elif kt == n:
        out["verdict"] = "AT THE LADDER'S TOP (T%d, A%d, L %s): every completed setting (%d) confirmed at the top after pressing against it (the symmetric reading; not named in #128 section 4)" % (
            RUNGS[0][0] // 16, RUNGS[0][1], fmt(rung_l(0), lo, hi), n)
    else:
        ls = sorted(r["L"] for r in inter)
        if ls:
            med = ls[len(ls) // 2] if len(ls) % 2 else (ls[len(ls) // 2 - 1] + ls[len(ls) // 2]) / 2.0
            out["null_L"] = med
            out["verdict"] = "NULL ESTIMATED from the %d uncensored setting(s) of %d: median L %s, range %.1f-%.1f; censored at the floor %d, at the top %d" % (
                len(inter), n, fmt(med, lo, hi), ls[0], ls[-1], kf, kt)
            if kf:
                out["verdict"] += " (the floor-censored settings lie AT OR BELOW the floor, so the median is biased UP)"
            if kt:
                out["verdict"] += " (the top-censored settings lie AT OR ABOVE the top, so the median is biased DOWN)"
        else:
            out["verdict"] = "NO UNCENSORED SETTING: %d at the floor, %d at the top of %d" % (kf, kt, n)
    return out


def n_missing(rows):
    return sum(1 for r in rows if r["gate"] is None)


def fmt(x, lo, hi):
    if hi > lo:
        return "%.1f-%.1f ms" % (x + lo, x + hi)
    return "%.1f ms" % (x + lo)


def render(a):
    out = []
    w = out.append
    w("PERCEPTUAL NULLING, %d setting(s) -- label %s (%s)" % (a["n"], a["label"], {
        "bounded": "every L as tabulated or +31.222 ms: RUN 56's reading, the DMA's hand-off semantics not resolved",
        "assumed": "every L as tabulated: the DMA semantics ASSUMED", "M1": "AHEAD + 1, RUN 57's marked block: as tabulated, CORROBORATED (address stage assumed identical)",
        "M2": "AHEAD + 2, RUN 57's marked block: every L +31.222 ms, CORROBORATED (address stage assumed identical)"}[a["label"]]))
    w("  L = the AUDIO PATH's latency (ring -> AI), INFERENCE; NOT the audio-versus-video offset (the video path is not here)")
    for r in a["settings"]:
        w("  setting %2d  start rung %d  dir %s  steps %2d (deeper %d, shallower %d)  floor presses %d  top presses %d  ->  rung %d = (T%d, A%d)  L %s  [%s]%s" % (
            r["n"] + 1, r["start"], "LEFT=deeper" if r["dir"] == 0 else "LEFT=shallower", r["steps"], r["deeper"], r["shallower"], r["floor_refused"], r["top_refused"],
            r["rung"], r["target"] // 16, r["ahead"], fmt(r["L"], r["L_lo"] - r["L"], r["L_hi"] - r["L"]), r["cls"], "" if r["ok"] else "  INCONSISTENT: (T, A) is not the rung's"))
    g = a["gates"]
    w("  MECHANISTIC GATE (the Executor's): fill tracks the target %d of %d, READY at AHEAD-1 or AHEAD %d of %d, no underrun %d of %d, no dropped sample %d of %d%s" % (
        g["fill"][0], g["fill"][1], g["ready"][0], g["ready"][1], g["underruns"][0], g["underruns"][1], g["overflow"][0], g["overflow"][1],
        "" if not a["missing_mech"] else "; %d setting(s) with no V28_NULLM record" % a["missing_mech"]))
    if g["fill"][1] and g["fill"][0] < g["fill"][1]:
        w("  (t1) THE FILL DID NOT TRACK THE TARGET at %d setting(s): the manipulation did not happen there; every perceptual result at those settings is void" % (g["fill"][1] - g["fill"][0]))
    if g["underruns"][1] and g["underruns"][0] < g["underruns"][1]:
        w("  (t2) an underrun in %d setting(s): audible dropouts are heard as instability, not latency, and contaminate the judgement there" % (g["underruns"][1] - g["underruns"][0]))
    w("  VERDICT: " + a["verdict"])
    if a["inconsistent"]:
        w("  DEFECT: %d record(s) whose (T, A) is not their rung's (T, A): a defect in the log, not a finding" % a["inconsistent"])
    return "\n".join(out)


def main(argv):
    label = "bounded"
    args = [x for x in argv[1:] if not x.startswith("--")]
    if "--label" in argv:
        label = argv[argv.index("--label") + 1]
        args = [x for x in args if x != label]
    if label not in LABELS or not args:
        print(__doc__)
        return 2
    with open(args[0], encoding="utf-8", errors="replace") as f:
        print(render(analyse(f.read(), label)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
