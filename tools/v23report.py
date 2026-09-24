#!/usr/bin/env python3
"""
tools/v23report.py — Run A's log and trace -> the report tools/v23accept.py reads
(GitHub Issue #101, HARDWARE_TESTS §V23).

    tools/v23report.py <GBP-AUDIO-008 log> <its -trace.bin> [--json <out>]

`tools/v23accept.py` holds §V23's gates and was frozen before the image existed. It reads a report
it does not know how to make; this file makes it, from the `LIVE*` records of poc/gbp-audio-trace and
the trace sidecar src/audio/gbp_atrace writes. It is frozen WITH the image, before any run, for the
reason §V22's builder was: every choice here is one the data could otherwise be argued into.

WHAT IT BUILDS, and from where

  window     t_origin and t_end (LIVET); the per-second coverage of C's WHOLE 1.000 s windows
             (LIVESEC), as tools/v22report.py counts them; the session's FRAMECAP incomplete count
             (its last FRAMECAP record)
  audio      every decoded sample of C's window and its completion tick, absolute: the first tick
             plus the u16 deltas, a saturated delta taking its tick from the side ring
  video      every VIDEO completion of the session and its frame-start flag, absolute, the same way
  ai_span    [t_ai_start, t_ai_stop] (LIVET2)
  callbacks  [entry, exit] of every AI DMA callback
  steps      [start, end, kind, end of the recorder's own write]
  recorder   the other recorder writes per AI callback cycle, aligned to the callbacks (cycle k is
             after callback k), with the writes before the first callback apart, and the largest
             single write
  trace      the records' own counts and what they dropped, beside the report, deciding nothing

It REFUSES, with the reason, rather than guess: a bad magic, version or CRC; a timebase that is not
40.5 MHz; a trace whose counts are not the ones the log's LIVETRACE record gives (another run's
trace); a saturated delta whose tick the side ring could not keep (absolute time would be lost
from there on). Standard library only. Reads a log and a trace; writes the JSON it is asked to.
"""
import json
import re
import struct
import sys
import zlib

TB_HZ = 40500000
RATE = 4096
MAGIC = b"OGBPTRC1"
A_SAT, V_START, V_SAT = 0xFFFF, 0x8000, 0x7FFF
KINDS = {1: "produce", 2: "flush_queue", 3: "process"}
HIST_BINS = 32


def _kv(line):
    return dict(re.findall(r"(\w+)=(\S*)", line))


def records(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\d{6} ([A-Z][A-Z0-9]*) (.*)$", line)
        if m:
            out.setdefault(m.group(1), []).append(m.group(2))
    return out


def parse_trace(data):
    if len(data) < 0x274 + 4:
        raise ValueError("the trace is %d bytes, shorter than its header" % len(data))
    if data[:8] != MAGIC:
        raise ValueError("bad magic %r" % data[:8])
    if zlib.crc32(data[:-4]) & 0xFFFFFFFF != struct.unpack(">I", data[-4:])[0]:
        raise ValueError("the trace's CRC-32 does not match its bytes")
    version, tb = struct.unpack(">2I", data[8:0x10])
    if version != 1:
        raise ValueError("version %d" % version)
    a_n, a_sat_n, v_n, v_sat_n, cb_n, step_n, cycles_n = struct.unpack(">7I", data[0x10:0x2C])
    dropped = struct.unpack(">6I", data[0x2C:0x44])
    a_first, v_first, step_base = struct.unpack(">3Q", data[0x44:0x5C])
    floor, cost_max = struct.unpack(">2I", data[0x5C:0x64])
    calls = struct.unpack(">4I", data[0x64:0x74])
    hist = struct.unpack(">%dI" % (4 * HIST_BINS), data[0x74:0x74 + 16 * HIST_BINS])
    o = 0x74 + 16 * HIST_BINS
    need = o + 2 * a_n + 2 * a_n + 12 * a_sat_n + 2 * v_n + 12 * v_sat_n + 16 * cb_n + 12 * step_n + 4 * cycles_n + 4
    if len(data) != need:
        raise ValueError("the trace is %d bytes, its counts say %d" % (len(data), need))
    decoded = struct.unpack(">%dh" % a_n, data[o:o + 2 * a_n]); o += 2 * a_n
    a_delta = struct.unpack(">%dH" % a_n, data[o:o + 2 * a_n]); o += 2 * a_n
    a_sat = [struct.unpack(">IQ", data[o + 12 * i:o + 12 * i + 12]) for i in range(a_sat_n)]; o += 12 * a_sat_n
    v_rec = struct.unpack(">%dH" % v_n, data[o:o + 2 * v_n]); o += 2 * v_n
    v_sat = [struct.unpack(">IQ", data[o + 12 * i:o + 12 * i + 12]) for i in range(v_sat_n)]; o += 12 * v_sat_n
    cbs = [struct.unpack(">QII", data[o + 16 * i:o + 16 * i + 16]) for i in range(cb_n)]; o += 16 * cb_n
    steps = [struct.unpack(">IIHBB", data[o + 12 * i:o + 12 * i + 12]) for i in range(step_n)]; o += 12 * step_n
    cycles = struct.unpack(">%dI" % cycles_n, data[o:o + 4 * cycles_n])
    names = ("a_dropped", "a_sat_dropped", "v_dropped", "v_sat_dropped", "cb_dropped", "step_dropped")
    return {"tb_hz": tb, "a_first": a_first, "decoded": list(decoded), "a_delta": list(a_delta), "a_sat": a_sat,
            "v_first": v_first, "v_rec": list(v_rec), "v_sat": v_sat, "callbacks": cbs, "step_base": step_base,
            "steps": steps, "cycles": list(cycles), "dropped": dict(zip(names, dropped)), "floor": floor,
            "cost_max": cost_max, "calls": {"produce": calls[1], "flush_queue": calls[2], "process": calls[3]},
            "hist": {"produce": list(hist[HIST_BINS:2 * HIST_BINS]), "process": list(hist[3 * HIST_BINS:])}}


def absolute(first, deltas, sat, mask, sat_value, what):
    """The absolute tick of every record from the first tick, the deltas and the side ring."""
    ring = dict(sat)
    out, t = [], first
    for i, d in enumerate(deltas):
        v = d & mask
        if i == 0:
            t = first
        elif v == sat_value:
            if i not in ring:
                raise ValueError("%s record %d saturated and its tick was not kept: absolute time is lost "
                                 "from there on" % (what, i))
            t = ring[i]
        else:
            t += v
        out.append(t)
    return out


def build(text, trace_bytes):
    recs = records(text)
    tr = parse_trace(trace_bytes)
    if tr["tb_hz"] != TB_HZ:
        raise ValueError("timebase %d is not the 40.5 MHz every §V23 window is counted in" % tr["tb_hz"])
    if "LIVETRACE" not in recs:
        raise ValueError("no LIVETRACE record: the log does not describe a trace")
    lt = _kv(recs["LIVETRACE"][-1])
    held = {"a": len(tr["decoded"]), "a_sat": len(tr["a_sat"]), "v": len(tr["v_rec"]), "v_sat": len(tr["v_sat"]),
            "cb": len(tr["callbacks"]), "steps": len(tr["steps"]), "cycles": len(tr["cycles"])}
    for k in sorted(held):
        if int(lt[k]) != held[k]:
            raise ValueError("the trace is not this log's: LIVETRACE says %s=%s, the trace holds %d" % (k, lt[k], held[k]))
    t = _kv(recs["LIVET"][0])
    t2 = _kv(recs["LIVET2"][0])
    if "LIVE" not in recs:
        raise ValueError("no LIVE record: not a GBP-AUDIO-008 log")
    head = _kv(recs["LIVE"][0])
    ident = _kv(recs["IDENT"][0]) if "IDENT" in recs else {}
    t_origin, t_end = int(t["t_origin"], 16), int(t["t_end"], 16)
    if head["phase"] == "done" and t_origin:
        ticks = t_end - t_origin
    elif t_origin and int(t2["t_last_block"], 16) > t_origin:
        ticks = int(t2["t_last_block"], 16) - t_origin
    else:
        ticks = 0
    whole = ticks // TB_HZ
    coverage = []
    for line in recs.get("LIVESEC", []):
        kv = _kv(line)
        if int(kv["from"]) != len(coverage):
            raise ValueError("LIVESEC lines are not contiguous: from=%s after %d values" % (kv["from"], len(coverage)))
        coverage += [int(c) for c in kv["counts"].split(",") if c]
    coverage = coverage[:whole]
    fc = _kv(recs["FRAMECAP"][-1]) if "FRAMECAP" in recs else {}
    a_ticks = absolute(tr["a_first"], tr["a_delta"], tr["a_sat"], 0xFFFF, A_SAT, "AUDIO")
    v_ticks = absolute(tr["v_first"], tr["v_rec"], tr["v_sat"], 0x7FFF, V_SAT, "VIDEO")
    base = tr["step_base"]
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
        "steps": [[base + s, base + s + d, KINDS[k], base + s + d + r] for s, d, r, k, _z in tr["steps"]],
        "recorder": {"tap_ticks_per_cycle": cycles[1:], "tap_before_first": cycles[0] if cycles else 0,
                     "tap_max_write": tr["cost_max"]},
        "trace": {"dropped": tr["dropped"], "floor": tr["floor"], "calls": tr["calls"], "hist": tr["hist"],
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
