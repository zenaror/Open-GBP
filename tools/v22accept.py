#!/usr/bin/env python3
"""
tools/v22accept.py — §V22's gates, frozen BEFORE the POC exists (GitHub Issue #92).

    tools/v22accept.py <report.json> [<l2-sidecar>]

Phase 6's acceptance. This module decides QUESTION L, QUESTION L2 and QUESTION C,
and reports MEASUREMENT M and §V22.4's correction rate, exactly as
`HARDWARE_TESTS.md` §V22 (with the readings §V22.8 records) freezes them. It is
written before the POC produces any data, and it is exercised on SYNTHETIC vectors
only (`tests/host/test_v22accept.py`). Nothing here may be edited once data exists.

WHAT IS FROZEN HERE AND WHY EACH PART IS

  L   the tone's identity. One A press selects sweep-0002's 128 Hz = period 32
      AUDIO blocks. PASS is min == max == 32 over QUESTION C's window, read on the
      decoder's output BEFORE any clock correction (§V22.8 (e): after them, every
      duplicate makes one period 33 and the gate fails on a healthy system).
      INCONCLUSIVE: the positive control (§V19.11 A4.7) did not pass, the press
      count was not exactly one A and nothing else (§V22.8 (r)), the window is
      shorter than 60 s, or any 1.000 s window's coverage is under D1's 0.999.

  L2  the leg nothing had tested: decode -> resample -> AI. The host recomputes
      the frozen gbp_aresamp over the kept decoded stream, applying the recorded
      corrections and silence chunks, from the kept resampler state, and must
      reproduce the CRC of the chunks handed to AUDIO_InitDMA EXACTLY. No
      threshold. As §V22.2 is written it has no INCONCLUSIVE arm: a missing,
      short or malformed record is a FAIL, reported with its reason.

  C   survival. PASS is zero OVERFLOW and zero UNDERRUN over >= 60 s. The three
      losses are never conflated and are all reported, with the per-second
      coverage and ring-fill series IN FULL. A PASS is never "no loss".

  M   the AI's real rate, from DMA callback timestamps in 40.5 MHz ticks.
      Not a gate: it corroborates Dolphin's 32 028.5 Hz or refutes it.

THE REPORT (JSON, produced from the POC's log by the POC's own report builder):

  {"test_id", "build_id", "commit",
   "presses":  {"a": int, "other": int},                 boot .. end of C's window
   "control":  {"ran": bool, "gave_up": bool, "blocks": int,
                "periods": int, "pmin": int, "pmax": int},
   "window":   {"ticks": int,                            C's window, from the origin
                "coverage": [int, ...],                  AUDIO blocks drained per whole 1.000 s window
                "l": {"periods": int, "pmin": int, "pmax": int},   pre-correction stream
                "not_drained": int, "overflow": int, "underrun": int,
                "fill": [int, ...],                      ring fill at each 1.000 s boundary
                "corrections": {"dup": int, "drop": int}},
   "m":        {"callbacks": int, "t_first": int, "t_last": int, "frames_per_callback": int}}

THE L2 SIDECAR (big-endian, as the console writes it):

  0x00  8     magic "OGBPL2S1"
  0x08  u32   version = 1
  0x0C  u32   chunk_frames          frames per AI chunk (a frame is L,R s16, the same sample)
  0x10  u32   chunks                the window, in whole AI chunks
  0x14  u32   crc                   CRC-32 of those chunks' bytes as handed to AUDIO_InitDMA
  0x18  u32   acc                   gbp_aresamp phase accumulator at the window's start
  0x1C  u32   hpos                  gbp_aresamp history position at the window's start
  0x20  s16x16 hist                 gbp_aresamp history ring at the window's start, as stored
  0x40  u32   n_samples             decoded samples kept (pre-correction, as they left the decoder)
  0x44  u32   n_events
  0x48  (u32 kind, u32 index) x n_events
              kind 1 DUP      the decoded sample at `index` was pushed twice
              kind 2 DROP     the decoded sample at `index` was not pushed
              kind 3 SILENCE  the window's chunk `index` was handed as silence, the resampler not advanced
  ....  s16 x n_samples         the kept decoded stream
  ....  u32                     CRC-32 of every byte before it

  The kept state is the resampler's IMMEDIATELY BEFORE the first push of the
  window, and the window's first frame is that push's first output.

Standard library only. Reads a report and a sidecar; writes nothing; authorises nothing.
"""
import json
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_aresamp  # noqa: E402  (the table src/audio/gbp_aresamp_coef.h is generated from)

# ---------------------------------------------------------------- frozen constants

TB_HZ = 40500000            # the console timebase every §V22 window is counted in
RATE = 4096                 # AUDIO blocks per second (GBP-HW-301)
PROGRAMMED_PERIOD = 32      # one A press: sweep-0002's first A-schedule tone, 128 Hz
CONTROL_BLOCKS = 2048       # §V19.11 A4.7
CONTROL_MIN_PERIODS = 48    # §V19.11 A4.7
D1_THRESHOLD = 0.999        # D1's, per 1.000 s window
C_MIN_S = 60.0              # QUESTION C's window, and L's (§V22.8 (c))
L2_MIN_FRAMES = 320000      # §V22.2: 10 s at the AI's nominal 32 000 frames/s
AI_NOMINAL_HZ = 32000.0
AI_MODEL_HZ = 108000000.0 / 3372.0   # Dolphin's model, a HYPOTHESIS (§V22.4)
RS_L, RS_M, RS_TAPS = 125, 16, 16

L2_MAGIC = b"OGBPL2S1"
EV_DUP, EV_DROP, EV_SILENCE = 1, 2, 3


# ------------------------------------------------------------------- QUESTION L

def question_L(report):
    """§V22.1 with §V22.8 (c), (d), (e) and (r)."""
    out = {"verdict": None, "why": "", "l": report["window"]["l"]}
    p = report["presses"]
    if p["a"] != 1 or p["other"] != 0:
        out.update(verdict="INCONCLUSIVE", why="press count was A=%d, other=%d, not exactly one A and nothing else"
                                               % (p["a"], p["other"]))
        return out
    c = report["control"]
    ok = (c["ran"] and not c["gave_up"] and c["blocks"] == CONTROL_BLOCKS and c["periods"] >= CONTROL_MIN_PERIODS
          and c["pmin"] == c["pmax"] == PROGRAMMED_PERIOD)
    if not ok:
        out.update(verdict="INCONCLUSIVE", why="the positive control did not pass (ran=%s gave_up=%s blocks=%d "
                                               "periods=%d pmin=%d pmax=%d): no tone, not a FAIL"
                                               % (c["ran"], c["gave_up"], c["blocks"], c["periods"], c["pmin"],
                                                  c["pmax"]))
        return out
    w = report["window"]
    seconds = w["ticks"] / float(TB_HZ)
    if seconds < C_MIN_S:
        out.update(verdict="INCONCLUSIVE", why="the window ran %.3f s, under the frozen %.1f s" % (seconds, C_MIN_S))
        return out
    low = [(i, n) for i, n in enumerate(w["coverage"]) if n / float(RATE) < D1_THRESHOLD]
    if low:
        out.update(verdict="INCONCLUSIVE", why="%d 1.000 s window(s) under D1's %.3f, first %d at %d AUDIO blocks: "
                                               "a drain result, not a playback one" % (len(low), D1_THRESHOLD,
                                                                                        low[0][0], low[0][1]))
        return out
    l = w["l"]
    if l["periods"] > 0 and l["pmin"] == l["pmax"] == PROGRAMMED_PERIOD:
        out.update(verdict="PASS", why="%d periods, min == max == %d, on the decoder's output before any correction"
                                       % (l["periods"], PROGRAMMED_PERIOD))
    else:
        out.update(verdict="FAIL", why="%d periods, min %d, max %d against the programmed %d"
                                       % (l["periods"], l["pmin"], l["pmax"], PROGRAMMED_PERIOD))
    return out


# ------------------------------------------------------------------ QUESTION L2

def parse_sidecar(data):
    """The L2 sidecar, strictly. Raises ValueError with the reason."""
    if len(data) < 0x48 + 4:
        raise ValueError("the sidecar is %d bytes, shorter than its header" % len(data))
    if data[:8] != L2_MAGIC:
        raise ValueError("bad magic %r" % data[:8])
    if zlib.crc32(data[:-4]) & 0xFFFFFFFF != struct.unpack(">I", data[-4:])[0]:
        raise ValueError("the sidecar's own CRC-32 does not match its bytes")
    version, chunk_frames, chunks, crc, acc, hpos = struct.unpack(">6I", data[8:0x20])
    if version != 1:
        raise ValueError("version %d" % version)
    hist = list(struct.unpack(">16h", data[0x20:0x40]))
    n_samples, n_events = struct.unpack(">2I", data[0x40:0x48])
    o = 0x48
    need = o + 8 * n_events + 2 * n_samples + 4
    if len(data) != need:
        raise ValueError("the sidecar is %d bytes, its counts say %d" % (len(data), need))
    events = [struct.unpack(">2I", data[o + 8 * k:o + 8 * k + 8]) for k in range(n_events)]
    o += 8 * n_events
    decoded = list(struct.unpack(">%dh" % n_samples, data[o:o + 2 * n_samples]))
    if not (0 <= acc < RS_L) or not (0 <= hpos < RS_TAPS) or chunk_frames == 0 or chunks == 0:
        raise ValueError("acc=%d hpos=%d chunk_frames=%d chunks=%d out of range" % (acc, hpos, chunk_frames, chunks))
    return {"chunk_frames": chunk_frames, "chunks": chunks, "crc": crc, "acc": acc, "hpos": hpos, "hist": hist,
            "events": events, "decoded": decoded}


def corrected(decoded, events, chunks):
    """The sequence the resampler was fed, and the window's silence chunks."""
    dup, drop, silence = set(), set(), set()
    for kind, index in events:
        if kind == EV_DUP and index < len(decoded):
            dup.add(index)
        elif kind == EV_DROP and index < len(decoded):
            drop.add(index)
        elif kind == EV_SILENCE and index < chunks:
            silence.add(index)
        else:
            raise ValueError("event kind %d at index %d is not legal here" % (kind, index))
    if dup & drop:
        raise ValueError("sample %d is both duplicated and dropped" % min(dup & drop))
    seq = []
    for i, v in enumerate(decoded):
        if i in drop:
            continue
        seq.append(v)
        if i in dup:
            seq.append(v)
    return seq, silence


def _q15(v):
    q = (v + 16384) >> 15 if v >= 0 else -(((-v) + 16384) >> 15)
    return max(-32767, min(32767, q))


def resample_from(state, seq, frames_needed, rows=None):
    """gbp_aresamp, restated in integers, from a kept state. Returns (frames, pushes used)."""
    rows = rows or gen_aresamp.table()
    hist, hpos, acc = list(state["hist"]), state["hpos"], state["acc"]
    out, used = [], 0
    for v in seq:
        if len(out) >= frames_needed:
            break
        hist[hpos] = v
        hpos = (hpos + 1) % RS_TAPS
        while acc < RS_L:
            h = rows[acc]
            out.append(_q15(sum(h[m] * hist[(hpos + m) % RS_TAPS] for m in range(RS_TAPS))))
            acc += RS_M
        acc -= RS_L
        used += 1
    return out, used


def question_L2(sidecar_bytes):
    """§V22.2 with its preconditions. PASS or FAIL, and why."""
    out = {"verdict": None, "why": "", "crc_kept": None, "crc_host": None, "frames": 0}
    if sidecar_bytes is None:
        out.update(verdict="FAIL", why="no L2 record: nothing for the host to reproduce")
        return out
    try:
        s = parse_sidecar(sidecar_bytes)
        seq, silence = corrected(s["decoded"], s["events"], s["chunks"])
    except ValueError as e:
        out.update(verdict="FAIL", why="the L2 record is malformed: %s" % e)
        return out
    frames_window = s["chunks"] * s["chunk_frames"]
    out.update(crc_kept=s["crc"], frames=frames_window)
    if frames_window < L2_MIN_FRAMES:
        out.update(verdict="FAIL", why="the window is %d frames, under §V22.2's %d (10 s)" % (frames_window,
                                                                                            L2_MIN_FRAMES))
        return out
    need = (s["chunks"] - len(silence)) * s["chunk_frames"]
    frames, used = resample_from(s, seq, need)
    if len(frames) < need:
        out.update(verdict="FAIL", why="the kept stream yields %d frames, the window needs %d" % (len(frames), need))
        return out
    if used != len(seq):
        out.update(verdict="FAIL", why="the kept stream has %d samples the window did not use" % (len(seq) - used))
        return out
    body = bytearray()
    k = 0
    silent = b"\x00\x00\x00\x00" * s["chunk_frames"]
    for c in range(s["chunks"]):
        if c in silence:
            body += silent
            continue
        for y in frames[k:k + s["chunk_frames"]]:
            body += struct.pack(">hh", y, y)
        k += s["chunk_frames"]
    crc = zlib.crc32(bytes(body)) & 0xFFFFFFFF
    out["crc_host"] = crc
    if crc == s["crc"]:
        out.update(verdict="PASS", why="the host reproduced the CRC %08x of %d chunks x %d frames exactly "
                                       "(%d DUP, %d DROP, %d SILENCE applied)"
                                       % (crc, s["chunks"], s["chunk_frames"],
                                          sum(1 for e in s["events"] if e[0] == EV_DUP),
                                          sum(1 for e in s["events"] if e[0] == EV_DROP), len(silence)))
    else:
        out.update(verdict="FAIL", why="the host computes %08x, the console handed %08x" % (crc, s["crc"]))
    return out


# ------------------------------------------------------------------- QUESTION C

def question_C(report):
    """§V22.3. PASS is zero OVERFLOW and zero UNDERRUN; everything else is reported beside it."""
    w = report["window"]
    seconds = w["ticks"] / float(TB_HZ)
    out = {"verdict": None, "why": "", "seconds": seconds, "not_drained": w["not_drained"],
           "overflow": w["overflow"], "underrun": w["underrun"], "coverage": list(w["coverage"]),
           "fill": list(w["fill"]), "corrections": dict(w["corrections"])}
    if seconds < C_MIN_S:
        out.update(verdict="INCONCLUSIVE", why="the window ran %.3f s, under the frozen %.1f s" % (seconds, C_MIN_S))
        return out
    if w["overflow"] == 0 and w["underrun"] == 0:
        out.update(verdict="PASS", why="zero OVERFLOW and zero UNDERRUN over %.3f s; NOT DRAINED %d AUDIO blocks; "
                                       "%d DUP and %d DROP corrections. That is what the counters say, and it is "
                                       "NOT a claim of no loss." % (seconds, w["not_drained"],
                                                                    w["corrections"]["dup"],
                                                                    w["corrections"]["drop"]))
    else:
        out.update(verdict="FAIL", why="OVERFLOW %d, UNDERRUN %d over %.3f s (NOT DRAINED %d)"
                                       % (w["overflow"], w["underrun"], seconds, w["not_drained"]))
    return out


# -------------------------------------------------------------- MEASUREMENT M

def measurement_M(report):
    """§V22.5. The AI's rate in frames per second of the console's own timebase."""
    m = report.get("m")
    if not m or m["callbacks"] < 2 or m["t_last"] <= m["t_first"]:
        return {"rate_hz": None, "why": "fewer than two timed DMA callbacks"}
    rate = m["frames_per_callback"] * (m["callbacks"] - 1) * float(TB_HZ) / (m["t_last"] - m["t_first"])
    return {"rate_hz": rate, "ppm_vs_nominal": (rate / AI_NOMINAL_HZ - 1.0) * 1e6,
            "ppm_vs_dolphin_model": (rate / AI_MODEL_HZ - 1.0) * 1e6, "callbacks": m["callbacks"]}


def correction_rate(report, m=None):
    """§V22.4, FROZEN as a REPORT: observed net duplicates per second against the rate the
    clock model predicts, so a rate far from it reads as a wrong model and not as a stall."""
    w = report["window"]
    seconds = w["ticks"] / float(TB_HZ)
    drained = sum(w["coverage"]) / float(len(w["coverage"])) if w["coverage"] else None
    obs = (w["corrections"]["dup"] - w["corrections"]["drop"]) / seconds if seconds > 0 else None
    out = {"observed_net_dup_per_s": obs, "drain_blocks_per_s": drained,
           "predicted_by_dolphin_model": (AI_MODEL_HZ * RS_M / RS_L - drained) if drained else None}
    if m and m.get("rate_hz") and drained:
        out["predicted_by_measured_ai"] = m["rate_hz"] * RS_M / RS_L - drained
    return out


# ------------------------------------------------------------------------- report

def evaluate(report, sidecar_bytes=None):
    m = measurement_M(report)
    return {"test_id": report.get("test_id"), "build_id": report.get("build_id"),
            "L": question_L(report), "L2": question_L2(sidecar_bytes), "C": question_C(report),
            "M": m, "corrections": correction_rate(report, m)}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        report = json.load(f)
    side = None
    if len(argv) > 2:
        with open(argv[2], "rb") as f:
            side = f.read()
    r = evaluate(report, side)
    print("%s / %s" % (r["test_id"], r["build_id"]))
    for q in ("L", "L2", "C"):
        print("  %-3s %-13s %s" % (q, r[q]["verdict"], r[q]["why"]))
    c = r["C"]
    print("     three losses: NOT DRAINED %d  OVERFLOW %d  UNDERRUN %d" % (c["not_drained"], c["overflow"],
                                                                         c["underrun"]))
    print("     per-second coverage and ring fill (reported IN FULL, PASS or FAIL):")
    for i in range(max(len(c["coverage"]), len(c["fill"]))):
        cov = c["coverage"][i] if i < len(c["coverage"]) else None
        fill = c["fill"][i] if i < len(c["fill"]) else None
        print("       s=%3d  drained %s  fill %s" % (i, cov, fill))
    m = r["M"]
    if m.get("rate_hz"):
        print("  M   AI rate %.3f Hz over %d callbacks (%+.1f ppm vs 32 000, %+.1f ppm vs Dolphin's 32 028.5)"
              % (m["rate_hz"], m["callbacks"], m["ppm_vs_nominal"], m["ppm_vs_dolphin_model"]))
    else:
        print("  M   %s" % m["why"])
    k = r["corrections"]
    print("  corrections: observed net DUP %s /s; predicted %s /s by Dolphin's model%s"
          % (None if k["observed_net_dup_per_s"] is None else "%.3f" % k["observed_net_dup_per_s"],
             None if k["predicted_by_dolphin_model"] is None else "%.3f" % k["predicted_by_dolphin_model"],
             "" if "predicted_by_measured_ai" not in k else ", %.3f /s by M" % k["predicted_by_measured_ai"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
