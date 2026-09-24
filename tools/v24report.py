#!/usr/bin/env python3
"""
tools/v24report.py — Run B's log and trace -> the report tools/v24accept.py reads
(GitHub Issue #105, HARDWARE_TESTS §V24).

    tools/v24report.py <GBP-AUDIO-009 log> <its -trace.bin> [--json <out>]

`tools/v24accept.py` holds §V24's gates and was frozen before the image existed. This file makes its report
from the `LIVE*` records of poc/gbp-audio-split and the VERSION-2 trace sidecar src/audio/gbp_atrace writes
there. It is frozen WITH the image, before any run. What §V23 read is built exactly as tools/v23report.py
builds it (the record parser and the absolute-tick rebuild are that frozen file's own functions); the
additions are Run B's:

  step_tag   the spare byte of every kept step: the chunk's applied arm, a first-step mark, seq mod 64
  sample     §V24.4's floorless steps of every sample_every-th AI cycle, absolute: [start, end, kind, tag]
  split      LIVESPLIT: the chunks handed each arm, the seed, the sample's counts
  trace      as tools/v23report.py writes it, plus the sample's dropped count

It REFUSES, with the reason, rather than guess:
- a bad magic or CRC, or a version that is not 2;
- a timebase that is not 40.5 MHz;
- a trace whose counts are not the log's LIVETRACE and LIVESPLIT;
- a seed that is not the frozen 0x9E3779B9;
- a saturated delta whose tick was not kept.

Standard library only.
"""
import json
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import v23report  # noqa: E402

TB_HZ = 40500000
SEED = 0x9E3779B9
MAGIC = b"OGBPTRC1"
A_SAT, V_START, V_SAT = 0xFFFF, 0x8000, 0x7FFF
KINDS = {1: "produce", 2: "flush_queue", 3: "process"}
HIST_BINS = 32


def parse_trace(data):
    if len(data) < 0x274 + 4:
        raise ValueError("the trace is %d bytes, shorter than its header" % len(data))
    if data[:8] != MAGIC:
        raise ValueError("bad magic %r" % data[:8])
    if zlib.crc32(data[:-4]) & 0xFFFFFFFF != struct.unpack(">I", data[-4:])[0]:
        raise ValueError("the trace's CRC-32 does not match its bytes")
    version, tb = struct.unpack(">2I", data[8:0x10])
    if version != 2:
        raise ValueError("version %d: Run B's trace is version 2 (tags and the floorless sample)" % version)
    a_n, a_sat_n, v_n, v_sat_n, cb_n, step_n, cycles_n = struct.unpack(">7I", data[0x10:0x2C])
    dropped = struct.unpack(">6I", data[0x2C:0x44])
    a_first, v_first, step_base = struct.unpack(">3Q", data[0x44:0x5C])
    floor, cost_max = struct.unpack(">2I", data[0x5C:0x64])
    calls = struct.unpack(">4I", data[0x64:0x74])
    hist = struct.unpack(">%dI" % (4 * HIST_BINS), data[0x74:0x74 + 16 * HIST_BINS])
    o = 0x74 + 16 * HIST_BINS
    decoded = struct.unpack(">%dh" % a_n, data[o:o + 2 * a_n]); o += 2 * a_n
    a_delta = struct.unpack(">%dH" % a_n, data[o:o + 2 * a_n]); o += 2 * a_n
    a_sat = [struct.unpack(">IQ", data[o + 12 * i:o + 12 * i + 12]) for i in range(a_sat_n)]; o += 12 * a_sat_n
    v_rec = struct.unpack(">%dH" % v_n, data[o:o + 2 * v_n]); o += 2 * v_n
    v_sat = [struct.unpack(">IQ", data[o + 12 * i:o + 12 * i + 12]) for i in range(v_sat_n)]; o += 12 * v_sat_n
    cbs = [struct.unpack(">QII", data[o + 16 * i:o + 16 * i + 16]) for i in range(cb_n)]; o += 16 * cb_n
    steps = [struct.unpack(">IIHBB", data[o + 12 * i:o + 12 * i + 12]) for i in range(step_n)]; o += 12 * step_n
    cycles = struct.unpack(">%dI" % cycles_n, data[o:o + 4 * cycles_n]); o += 4 * cycles_n
    if len(data) < o + 20 + 4:
        raise ValueError("the trace ends before its sample block")
    sample_every, sample_n, sample_dropped = struct.unpack(">3I", data[o:o + 12])
    sample_base = struct.unpack(">Q", data[o + 12:o + 20])[0]
    o += 20
    sample = [struct.unpack(">IIHBB", data[o + 12 * i:o + 12 * i + 12]) for i in range(sample_n)]
    o += 12 * sample_n
    if len(data) != o + 4:
        raise ValueError("the trace is %d bytes, its counts say %d" % (len(data), o + 4))
    names = ("a_dropped", "a_sat_dropped", "v_dropped", "v_sat_dropped", "cb_dropped", "step_dropped")
    return {"tb_hz": tb, "a_first": a_first, "decoded": list(decoded), "a_delta": list(a_delta), "a_sat": a_sat,
            "v_first": v_first, "v_rec": list(v_rec), "v_sat": v_sat, "callbacks": cbs, "step_base": step_base,
            "steps": steps, "cycles": list(cycles), "dropped": dict(zip(names, dropped)), "floor": floor,
            "cost_max": cost_max, "calls": {"produce": calls[1], "flush_queue": calls[2], "process": calls[3]},
            "hist": {"produce": list(hist[HIST_BINS:2 * HIST_BINS]), "process": list(hist[3 * HIST_BINS:])},
            "sample_every": sample_every, "sample_dropped": sample_dropped, "sample_base": sample_base,
            "sample": sample}


def build(text, trace_bytes):
    recs = v23report.records(text)
    tr = parse_trace(trace_bytes)
    if tr["tb_hz"] != TB_HZ:
        raise ValueError("timebase %d is not the 40.5 MHz every §V24 window is counted in" % tr["tb_hz"])
    for tag in ("LIVE", "LIVET", "LIVET2", "LIVETRACE", "LIVESPLIT"):
        if tag not in recs:
            raise ValueError("no %s record: not a GBP-AUDIO-009 log that describes its trace" % tag)
    lt = v23report._kv(recs["LIVETRACE"][-1])
    held = {"a": len(tr["decoded"]), "a_sat": len(tr["a_sat"]), "v": len(tr["v_rec"]), "v_sat": len(tr["v_sat"]),
            "cb": len(tr["callbacks"]), "steps": len(tr["steps"]), "cycles": len(tr["cycles"])}
    for k in sorted(held):
        if int(lt[k]) != held[k]:
            raise ValueError("the trace is not this log's: LIVETRACE says %s=%s, the trace holds %d" % (k, lt[k], held[k]))
    sp = v23report._kv(recs["LIVESPLIT"][-1])
    if int(sp["seed"], 16) != SEED:
        raise ValueError("the image's seed %s is not the frozen 0x%08x (§V24.7)" % (sp["seed"], SEED))
    if (int(sp["sample_every"]), int(sp["sample"]), int(sp["sample_dropped"])) != \
            (tr["sample_every"], len(tr["sample"]), tr["sample_dropped"]):
        raise ValueError("the trace's sample is not this log's LIVESPLIT")
    t = v23report._kv(recs["LIVET"][0])
    t2 = v23report._kv(recs["LIVET2"][0])
    head = v23report._kv(recs["LIVE"][0])
    ident = v23report._kv(recs["IDENT"][0]) if "IDENT" in recs else {}
    t_origin, t_end = int(t["t_origin"], 16), int(t["t_end"], 16)
    if head["phase"] == "done" and t_origin:
        ticks = t_end - t_origin
    elif t_origin and int(t2["t_last_block"], 16) > t_origin:
        ticks = int(t2["t_last_block"], 16) - t_origin
    else:
        ticks = 0
    coverage = []
    for line in recs.get("LIVESEC", []):
        kv = v23report._kv(line)
        if int(kv["from"]) != len(coverage):
            raise ValueError("LIVESEC lines are not contiguous: from=%s after %d values" % (kv["from"], len(coverage)))
        coverage += [int(c) for c in kv["counts"].split(",") if c]
    coverage = coverage[:ticks // TB_HZ]
    fc = v23report._kv(recs["FRAMECAP"][-1]) if "FRAMECAP" in recs else {}
    a_ticks = v23report.absolute(tr["a_first"], tr["a_delta"], tr["a_sat"], 0xFFFF, A_SAT, "AUDIO")
    v_ticks = v23report.absolute(tr["v_first"], tr["v_rec"], tr["v_sat"], 0x7FFF, V_SAT, "VIDEO")
    base, sbase = tr["step_base"], tr["sample_base"]
    cycles = tr["cycles"]
    return {
        "test_id": ident.get("test"), "build_id": ident.get("build"), "commit": ident.get("commit"),
        "tb_hz": TB_HZ,
        "window": {"t_origin": t_origin, "t_end": t_end, "coverage": coverage,
                   "framecap_session": int(fc["incomplete"]) if "incomplete" in fc else None},
        "audio": {"ticks": a_ticks, "decoded": tr["decoded"]},
        "video": {"ticks": v_ticks, "start": [1 if r & V_START else 0 for r in tr["v_rec"]]},
        "ai_span": [int(t2["t_ai_start"], 16), int(t2["t_ai_stop"], 16)],
        "callbacks": [[e, e + d] for e, d, _rec in tr["callbacks"]],
        "steps": [[base + s, base + s + d, KINDS[k], base + s + d + r] for s, d, r, k, _tag in tr["steps"]],
        "step_tag": [tag for _s, _d, _r, _k, tag in tr["steps"]],
        "recorder": {"tap_ticks_per_cycle": cycles[1:], "tap_before_first": cycles[0] if cycles else 0,
                     "tap_max_write": tr["cost_max"]},
        "sample": {"every": tr["sample_every"], "dropped": tr["sample_dropped"],
                   "steps": [[sbase + s, sbase + s + d, KINDS.get(k, "kind%d" % k), tag]
                             for s, d, _r, k, tag in tr["sample"]]},
        "split": {"half": int(sp["half"]), "full": int(sp["full"]), "seed": int(sp["seed"], 16)},
        "trace": {"dropped": dict(tr["dropped"], sample_dropped=tr["sample_dropped"]), "floor": tr["floor"],
                  "calls": tr["calls"], "hist": tr["hist"],
                  "callback_rec_max": max((r for _e, _d, r in tr["callbacks"]), default=0)},
    }


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        text = f.read()
    with open(argv[2], "rb") as f:
        rep = build(text, f.read())
    out = json.dumps(rep, sort_keys=True)
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            f.write(out + "\n")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
