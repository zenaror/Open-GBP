#!/usr/bin/env python3
"""
tools/v22report.py — the live image's log -> the report tools/v22accept.py reads
(GitHub Issue #92, Phase 6's acceptance).

    tools/v22report.py <GBP-AUDIO-007 log> [--sidecar <l2 file>] [--json <out>]

`tools/v22accept.py` holds §V22's gates and is frozen (94b478d, amended at dfb0a96).
It reads a report it does not know how to make. This file makes it, from the `LIVE*`
records `poc/gbp-audio-live` writes, and it is frozen WITH the image, before the run,
for the reason §V19's builder was: every choice here is one the data could otherwise
be argued into. None is new; each is §V22's or its readings'.

WHAT IT BUILDS

  presses   a, other           from boot until C's window closed (§V22.8 (r), §V22.9 A3)
  control   the LAST control window's figures, ran / gave_up (§V19.11 A4.7)
  window    ticks              C's window: t_end - t_origin when the window CLOSED
                               (phase done); otherwise t_last_block - t_origin, which
                               is shorter and makes C and L INCONCLUSIVE, as frozen
            coverage, fill     the WHOLE 1.000 s windows only: floor(ticks / tb_hz)
            l                  L, on the decoder's output before any correction
            not_drained        4096 x whole windows - the blocks they counted, >= 0
            overflow           the decoder's ring (gbp_adec)
            underrun           AI chunks starved while playing (gbp_aplay)
            corrections        DUP and DROP
  m         the AI callbacks, first and last instant (§V22.5)

  l2_sidecar  "present" or "absent: <why>" -- §V22.9 A1: the record is ABSENT when the
              log says its save failed or was never attempted, or when the file named
              is missing. The caller passes the sidecar to tools/v22accept.py only when
              this says "present".

Standard library only. Reads a log (and checks a file exists); writes a JSON; decides nothing.
"""
import json
import os
import re
import sys

TB_HZ = 40500000
RATE = 4096


def _kv(line):
    return dict(re.findall(r"(\w+)=(\S*)", line))


def records(text):
    """Every LIVE* record, by tag, in order. The ringlog prefixes each line with a
    six-digit sequence number, and the SD log keeps it."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\d{6} (LIVE[A-Z0-9]*) (.*)$", line)
        if m:
            out.setdefault(m.group(1), []).append(m.group(2))
    return out


def series(recs, tag, field):
    vals = []
    for body in recs.get(tag, []):
        kv = _kv(body)
        start = int(kv["from"])
        if start != len(vals):
            raise ValueError("%s lines are not contiguous: from=%d after %d values" % (tag, start, len(vals)))
        vals.extend(int(x) for x in kv[field].split(",") if x != "")
    return vals


def build(text, sidecar_path=None):
    recs = records(text)
    if "LIVE" not in recs:
        raise ValueError("no LIVE record: not a GBP-AUDIO-007 log")
    head = _kv(recs["LIVE"][0])
    ctl = _kv(recs["LIVECTL"][0])
    t = _kv(recs["LIVET"][0])
    t2 = _kv(recs["LIVET2"][0])
    l = _kv(recs["LIVEL"][0])
    c = _kv(recs["LIVEC"][0])
    m = _kv(recs["LIVEM"][0])
    ident = {}
    for line in text.splitlines():
        mm = re.match(r"^\d{6} IDENT (.*)$", line)
        if mm:
            ident = _kv(mm.group(1))
            break
    tb = int(t["tb_hz"])
    if tb != TB_HZ:
        raise ValueError("timebase %d is not the 40.5 MHz every §V22 window is counted in" % tb)
    t_origin, t_end = int(t["t_origin"], 16), int(t["t_end"], 16)
    if head["phase"] == "done" and t_origin:
        ticks = t_end - t_origin
    elif t_origin and int(t2["t_last_block"], 16) > t_origin:
        ticks = int(t2["t_last_block"], 16) - t_origin
    else:
        ticks = 0
    whole = ticks // tb
    coverage = series(recs, "LIVESEC", "counts")[:whole]
    fill = series(recs, "LIVEFILL", "fill")[:whole]
    report = {
        "test_id": ident.get("test"), "build_id": ident.get("build"), "commit": ident.get("commit"),
        "phase_reached": head["phase"],
        "presses": {"a": int(head["presses_a"]), "other": int(head["presses_other"])},
        "presses_after": int(head["presses_after"]),
        "press_before_prompt": head["press_before_prompt"] == "1",
        "control": {"ran": int(head["windows"]) > 0, "gave_up": head["gave_up"] == "1",
                    "blocks": int(ctl["blocks"]), "periods": int(ctl["periods"]),
                    "pmin": int(ctl["pmin"]), "pmax": int(ctl["pmax"])},
        "window": {"ticks": ticks, "coverage": coverage,
                   "l": {"periods": int(l["periods"]), "pmin": int(l["pmin"]), "pmax": int(l["pmax"])},
                   "not_drained": max(0, RATE * len(coverage) - sum(coverage)),
                   "overflow": int(c["overflow"]), "underrun": int(c["underruns"]),
                   "fill": fill, "corrections": {"dup": int(c["dup"]), "drop": int(c["drop"])}},
        "m": {"callbacks": int(m["callbacks"]), "t_first": int(m["t_first"], 16),
              "t_last": int(m["t_last"], 16), "frames_per_callback": int(m["frames_per_callback"])},
    }
    # §V22.9 A1: present or ABSENT, from the log's own account of the save
    save = recs.get("LIVEL2SAVE")
    if not save:
        why = "the log records no attempt to save it"
    else:
        s = _kv(save[-1])
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
