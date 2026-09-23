#!/usr/bin/env python3
"""
tools/v19report.py — the drain image's log -> the report tools/v19drain.py reads
(GitHub Issue #84, GBP-AUDIO-005).

    tools/v19report.py <GBP-AUDIO-005 log> [--json <out>]

`tools/v19drain.py` holds §V19's three gates and is frozen at 364be84. It reads a
report it does not know how to make. This file makes it, from the `DRAIN*`
records `poc/gbp-audio-drain-probe` writes, and it is frozen BEFORE the run for
the same reason the gates are: every choice here is one the data could otherwise
be argued into. Each one is §V19.11 AMENDMENT 4 A4.7's, and none is new.

WHAT IT BUILDS

  phase_b   counts          the per-second counts of PHASE B, seconds 0..59 (DRAINSEC)
            phase_s         PHASE B's measured length, from its start to its hand-over (DRAINT)
            counter_total   the sum of those 60 counts                         (DRAIND1)
            timebase_total  the service's OWN completion counter over the phase (DRAIND1)
  phase_c   write_bytes     65 536, as the image states it                     (DRAIND2)
            coverage_before the counter's second 64 / 4096
            gap_blocks      sum of (4096 - count) over seconds 65 .. the one the write returned in
            coverage_after  the first whole second after that / 4096
            (absent when the write was not made: D2 is then UNMEASURED, said, not guessed)
  phase_a   steps           the steps that RAN, in sweep order (DRAINA); `periods` is
                            [pmin, pmax] -- the image keeps the count, the minimum and the
                            maximum, which are exactly what §V19.4's rule reads
                            (bool, min, max); the count rides beside as `period_count`
            control_before_phase   CONTROL2 passed                             (DRAIN)
            recovered       the recovery window passed                         (DRAIN)
            edge_recoverable per step: steps_visible / crossings, None with no crossing

Standard library only. Reads a log; writes a JSON; decides nothing.
"""
import json
import re
import sys

TB_HZ = 40500000
RATE = 4096
B_SECONDS = 60
D2_MARK_S = 65
PROGRAMMED_PERIOD = 32


def _kv(line):
    return dict(re.findall(r"(\w+)=(\S*)", line))


def records(text):
    """Every DRAIN* record, by tag, in order. The ringlog prefixes each line with a
    six-digit sequence number, and the SD log keeps it."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\d{6} (DRAIN[A-Z0-9]*) (.*)$", line)
        if m:
            out.setdefault(m.group(1), []).append(m.group(2))
    return out


def per_second(recs):
    counts = []
    for body in recs.get("DRAINSEC", []):
        kv = _kv(body)
        start = int(kv["from"])
        if start != len(counts):
            raise ValueError("DRAINSEC lines are not contiguous: from=%d after %d counts" % (start, len(counts)))
        counts.extend(int(x) for x in kv["counts"].split(",") if x != "")
    return counts


def build(text):
    recs = records(text)
    if "DRAIN" not in recs:
        raise ValueError("no DRAIN record: not a GBP-AUDIO-005 log")
    head = dict(_kv(recs["DRAIN"][0]), **_kv(recs["DRAINN"][0]))
    t = _kv(recs["DRAINT"][0])
    d1 = _kv(recs["DRAIND1"][0])
    d2 = dict(_kv(recs["DRAIND2"][0]), **_kv(recs["DRAINGAP"][0]))
    ident = {}
    for line in text.splitlines():
        m = re.match(r"^\d{6} IDENT (.*)$", line)
        if m:
            ident = _kv(m.group(1))
            break
    tb = int(t["tb_hz"])
    if tb != TB_HZ:
        raise ValueError("timebase %d is not the 40.5 MHz every §V19 boundary is counted in" % tb)
    counts = per_second(recs)
    report = {"test_id": ident.get("test"), "build_id": ident.get("build"), "commit": ident.get("commit"),
              "phase_reached": head["phase"], "control1_ok": head["control1_ok"] == "1",
              "control1_gave_up": head["control1_gave_up"] == "1",
              "a_presses": int(head["a_presses"]), "other_presses": int(head["other_presses"]),
              "failures": int(head["failures"]), "sec_overflow": int(head["sec_overflow"])}

    # ---- PHASE B (D1)
    b_ticks = int(d1["b_ticks"])
    report["phase_b"] = {"counts": counts[:B_SECONDS], "phase_s": b_ticks / float(tb),
                         "counter_total": int(d1["counter_total"]), "timebase_total": int(d1["timebase_total"])}

    # ---- PHASE C (D2): only when the write was made
    t_b = int(t["t_b"], 16)
    made = d2["open_rc"] == "0" and d2["done"] == "1" and d2["write_rc"] == "0"
    if made:
        w0, w1 = int(d2["t_w0"], 16), int(d2["t_w1"], 16)
        s0 = (w0 - t_b) // tb
        s1 = (w1 - t_b) // tb
        if s0 != D2_MARK_S:
            raise ValueError("the write began in second %d, not the frozen mark %d" % (s0, D2_MARK_S))
        if s1 + 1 >= len(counts):
            raise ValueError("no whole second after the write in the counter")
        report["phase_c"] = {"write_bytes": int(d2["bytes"]),
                             "coverage_before": counts[D2_MARK_S - 1] / float(RATE),
                             "gap_blocks": sum(RATE - counts[s] for s in range(D2_MARK_S, s1 + 1)),
                             "coverage_after": counts[s1 + 1] / float(RATE),
                             "write_us": (w1 - w0) * 1e6 / tb,
                             "seconds_spanned": [D2_MARK_S, s1],
                             "gap_max_c_us": int(d2["gap_max_c"]) * 1e6 / tb,
                             "gap_max_b_us": int(d2["gap_max_b"]) * 1e6 / tb}
    else:
        report["phase_c"] = None
        report["phase_c_unmeasured"] = ("open_rc=%s write_rc=%s done=%s: the D2 write was not made, so D2 is "
                                        "UNMEASURED" % (d2["open_rc"], d2["write_rc"], d2["done"]))

    # ---- PHASE A (QUESTION A)
    steps = []
    second = {_kv(b)["step"]: _kv(b) for b in recs.get("DRAINA2", [])}
    for body in recs.get("DRAINA", []):
        kv = dict(_kv(body), **second[_kv(body)["step"]])
        if kv["ran"] != "1":
            continue
        n_per = int(kv["periods"])
        cross = int(kv["crossings"])
        steps.append({"n": int(kv["n"], 16), "programmed_period": PROGRAMMED_PERIOD,
                      "periods": [int(kv["pmin"]), int(kv["pmax"])] if n_per else [],
                      "period_count": n_per, "off": int(kv["off"]),
                      "edge_recoverable": (int(kv["steps_visible"]) / float(cross)) if cross else None,
                      "wrong_len": int(kv["wrong_len"])})
    report["phase_a"] = {"steps": steps, "control_before_phase": head["control2_ok"] == "1",
                         "recovered": head["recovered"] == "1"}
    return report


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        rep = build(f.read())
    text = json.dumps(rep, indent=2, sort_keys=True)
    if "--json" in argv:
        out = argv[argv.index("--json") + 1]
        with open(out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
