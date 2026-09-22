#!/usr/bin/env python3
"""
tools/tprime.py — §V7.9's QUESTION T′, computed exactly as §V7.9.2 – §V7.9.5
fix it, applied at the ingestion of RUN 30 (GitHub Issues #57, #62).

WHEN THIS WAS WRITTEN, AND THE RISK NAMED. §V7.9 froze the population, the
classifier, the quantity, the statistic and all four thresholds on 2026-09-22
(Issues #53 and #54) -- before any run T′ could be applied to. THIS FILE was
written at the ingestion, because no implementation existed, and that is the
one thing about it worth distrusting. So it implements the frozen text
literally and nothing else:

  population   CYCF/CYCFT and CYCL/CYCLT only -- NOT CYCE. §V7.9.2 names those two
               record pairs and the index is provenance, never a matching key.
  classifier   VIDEO-CARRYING when the cycle's v= field is 1/1, AUDIO-ONLY otherwise;
               applied to BOTH runs; an undeterminable record is EXCLUDED and counted.
  quantity     rearm - ack, in ticks of the run's own time base, from the CYC*T record
               of the same cycle (joined by the record's own i=, which pairs CYCF with
               CYCFT inside one run -- provenance within a run, not across runs).
  statistic    the MEDIAN of each class, with the full ordered list reported beside it.
  minimum      5 cycles in EACH class in EACH run, or INCONCLUSIVE naming the short class.
  thresholds   §V7.9.3's, with §V7.9.7's amendment IN FORCE: "unchanged" <= 1 tick,
               "not longer" a direction with no magnitude, "not lower" >= 0.995
               (DERIVED from the archive's 0.110 % between-build spread, Issue #54),
               "far from" > 5 percentage points.

It decides nothing that §V7.9.5 does not decide, and it reports every figure it
used so the reading can be checked without it.
"""
import re
import statistics


def _ticks(v):
    return int(v, 16)


def cycles(text):
    """The CYCF/CYCL records of one log, joined to their CYCFT/CYCLT timestamps."""
    out, excluded = [], 0
    for tag in ("CYCF", "CYCL"):
        head = dict((m.group(1), m.group(0)) for m in
                    re.finditer(r"^\d+ %s i=(\d+) .*$" % tag, text, re.M))
        time = dict((m.group(1), m.group(0)) for m in
                    re.finditer(r"^\d+ %sT i=(\d+) .*$" % tag, text, re.M))
        for i, line in sorted(head.items(), key=lambda kv: int(kv[0])):
            t = time.get(i)
            v = re.search(r" v=(\S+)", line)
            a = re.search(r" ack=([0-9a-f]+)", t or "")
            r = re.search(r" rearm=([0-9a-f]+)", t or "")
            if not (t and v and a and r):
                excluded += 1
                continue
            out.append({"tag": tag, "i": int(i),
                        "video": v.group(1) == "1/1",
                        "ticks": _ticks(r.group(1)) - _ticks(a.group(1))})
    return out, excluded


def classes(text):
    cyc, excluded = cycles(text)
    video = sorted(c["ticks"] for c in cyc if c["video"])
    audio = sorted(c["ticks"] for c in cyc if not c["video"])
    return {"video": video, "audio_only": audio, "excluded": excluded, "n": len(cyc)}


def rates(text, tb_hz=40500000):
    """The delivery rate and skipped_cause_pending %, the same two quantities
    §V7.9.7 derived its bounds from."""
    c = re.search(r"^\d+ COUNTERS ([^\n]+)$", text, re.M)
    p = re.search(r"^\d+ STREAMPUMP ([^\n]+)$", text, re.M)
    st = re.search(r"t_capture_start=([0-9a-f]+)", text)
    td = re.search(r"teardown_begin=([0-9a-f]+)", text)
    if not (c and p and st and td):
        return None
    cd = dict(re.findall(r"(\w+)=([\w/\.]+)", c.group(1)))
    pd = dict(re.findall(r"(\w+)=(\d+)", p.group(1)))
    win = (_ticks(td.group(1)) - _ticks(st.group(1))) / tb_hz
    if win <= 0:
        return None
    return {"deliveries": int(cd["deliveries"]), "seconds": win,
            "rate": int(cd["deliveries"]) / win,
            "skipped_pct": 100.0 * int(pd["skipped_cause_pending"]) / int(pd["calls"])}


def fault(text):
    """§V7.9.5's FAULT gate, checked FIRST and deciding alone."""
    why = []
    if re.search(r"^\d+ CYCA ", text, re.M):
        why.append("an anomaly record (CYCA) exists")
    m = re.search(r"main_w1c=(\d+)", text)
    if m and int(m.group(1)) > 0:
        why.append("main_w1c=%s" % m.group(1))
    m = re.search(r"reentry=(\d+)", text)
    if m and int(m.group(1)) > 0:
        why.append("reentry=%s" % m.group(1))
    m = re.search(r"^\d+ VSTATE end status=(\S+) class=(\S+)", text, re.M)
    if m and m.group(2) != "ok":
        why.append("service status %s" % m.group(1))
    # transport_ok appears TWICE in a log with different meanings: the DET record
    # counts how many detection runs found the transport ok (4 of 4), and the
    # VSTATE end record carries the service's own boolean. The gate is the
    # SERVICE's, so it is read from the VSTATE end record and from nowhere else --
    # the first match in the file is the detector's and would fail every run.
    m = re.search(r"^\d+ VSTATE end .*\btransport_ok=(\d+)", text, re.M)
    if m and int(m.group(1)) != 1:
        why.append("service transport_ok=%s" % m.group(1))
    return why


def question_tprime(new_text, ref_text, new_name="new", ref_name="reference"):
    """§V7.9.5's decision rule, in its own order."""
    report = {"new": new_name, "reference": ref_name}
    f = fault(new_text) + ["reference: " + w for w in fault(ref_text)]
    report["fault_why"] = f
    n, r = classes(new_text), classes(ref_text)
    report["classes"] = {"new": n, "reference": r}
    report["rates"] = {"new": rates(new_text), "reference": rates(ref_text)}
    if f:
        report["verdict"] = "FAULT"
        return report
    short = [("%s %s" % (who, cls))
             for who, d in (("new", n), ("reference", r))
             for cls in ("video", "audio_only") if len(d[cls]) < 5]
    if short:
        report["verdict"] = "INCONCLUSIVE"
        report["why"] = "fewer than 5 cycles in: " + ", ".join(short)
        return report
    med = lambda xs: statistics.median(xs)
    report["medians"] = {"new_audio": med(n["audio_only"]), "ref_audio": med(r["audio_only"]),
                         "new_video": med(n["video"]), "ref_video": med(r["video"])}
    control_unchanged = abs(med(n["audio_only"]) - med(r["audio_only"])) <= 1
    report["control_unchanged"] = control_unchanged
    if not control_unchanged:
        report["verdict"] = "INCONCLUSIVE"
        report["why"] = ("the AUDIO-only control is not unchanged (%s against %s): something moved that the "
                         "removal does not touch" % (med(n["audio_only"]), med(r["audio_only"])))
        return report
    checks = {"not_longer": med(n["video"]) <= med(r["video"])}
    rn, rr = report["rates"]["new"], report["rates"]["reference"]
    if rn and rr:
        # §V7.9.3 wrote 0.99 and §V7.9.7 (Issue #54) DERIVED it to 0.995 from the
        # archive's own between-build spread (0.110 %), before any run T' judges.
        # The amended number is the one in force; the frozen text keeps its words.
        checks["not_lower"] = rn["rate"] >= 0.995 * rr["rate"]
        checks["not_far_from"] = abs(rn["skipped_pct"] - rr["skipped_pct"]) <= 5.0
    report["checks"] = checks
    report["verdict"] = "NOMINAL" if all(checks.values()) else "ANOMALOUS"
    return report


if __name__ == "__main__":
    import sys, json
    new = open(sys.argv[1], encoding="utf-8").read()
    ref = open(sys.argv[2], encoding="utf-8").read()
    print(json.dumps(question_tprime(new, ref, sys.argv[1], sys.argv[2]), indent=2, default=str))
