#!/usr/bin/env python3
"""
tools/u045cadence.py — U-GBP-045 from RUN 38's archive: when do the undrained AUDIO blocks and the
incomplete video frames fall, and does one cadence order both? (GitHub Issue #100)

    tools/u045cadence.py <GBP-AUDIO-007 log> <its -l2.bin>

Reads what RUN 38 already produced and decides nothing. It prints:

AUDIO  Where the undrained blocks fall inside the L2 window. The window's decoded stream, kept
       by the image before any correction, is a 128 Hz square wave: 16 samples per half-period,
       which means 15 plateau samples and one step sample. A block that was never drained removes
       one sample, so a half-period of 16 - k samples holds k losses. That locates every loss to
       its half-period, about 3.9 ms. It cannot place a loss inside a plateau. A sample's time is
       its index plus the losses before it, over the device's 4096 blocks per second. That time
       runs from the window's first kept sample, which has no absolute timestamp.

VIDEO  When the incomplete video frames fall, against the AI DMA callbacks. The log prints the
       first 128 and the last 64 of its EVENTS. Only the last 64 are contiguous with the end, so
       only they give a complete list over their span. An event's time is when the service
       closed the incomplete interval, and so is quantised to the frame. The callbacks' phase
       comes from LIVEM: the first and last callback, and their count.

The phase statistics are Rayleigh's: R is the length of the mean phase vector, from 0 (no
preferred phase) to 1 (all at one phase). The Monte Carlo draws random frame boundaries from the
same span with a fixed seed, so its figure is reproducible. Standard library only.
"""
import math
import random
import re
import sys

TB_HZ = 40500000.0
BLOCKS_PER_S = 4096.0
HALF = 16            # samples per half-period of sweep-0002's first A tone (128 Hz, period 32)
HIGH, LOW = 10000, -10000


def kv(s):
    return dict(re.findall(r"(\w+)=(\S*)", s))


def record(text, tag):
    m = re.search(r"^\d{6} %s (.*)$" % tag, text, re.M)
    if not m:
        raise ValueError("no %s record" % tag)
    return kv(m.group(1))


# ------------------------------------------------------------------------------------------ AUDIO

def half_periods(decoded):
    """(start index, length) of every half-period between two transitions of the kept stream.

    A mark is the index of the half's step sample, its last. When the step sample was not drained,
    the mark is the plateau's last sample, so the half that lost its step measures 15 and the next 16.
    CORRECTED 2026-09-24 (Issue #101): the mark was placed BETWEEN the two plateau samples, which made
    both halves 15.5, and rounding hid the loss -- 10 of RUN 38's 306 losses were missed that way."""
    cls = ["H" if v > HIGH else "L" if v < LOW else "E" for v in decoded]
    marks = []
    for i in range(len(decoded) - 1):
        if cls[i] == "E":
            marks.append(i)
        elif cls[i] != cls[i + 1] and cls[i + 1] != "E":
            marks.append(i)                           # a step with no intermediate sample: the plateau's end
    return [(marks[k], marks[k + 1] - marks[k]) for k in range(len(marks) - 1)]


def audio_losses(decoded):
    """[(device time in s from the first kept sample, losses in that half-period)], and the halves."""
    halves = half_periods(decoded)
    out, before = [], 0
    for start, length in halves:
        k = HALF - length
        if k > 0:
            out.append(((start + before) / BLOCKS_PER_S, k))
            before += k
    return out, halves


def episodes(losses, merge_s=0.0045):
    """Loss half-periods closer than about one half-period are one episode; return their starts."""
    starts, last = [], None
    for t, _k in losses:
        if last is None or t - last > merge_s:
            starts.append(t)
        last = t
    return starts


def rayleigh(times, period):
    """(R, mean phase in cycles, z) of `times` modulo `period`."""
    c = sum(math.cos(2 * math.pi * t / period) for t in times)
    s = sum(math.sin(2 * math.pi * t / period) for t in times)
    r = math.hypot(c, s) / len(times)
    return r, (math.atan2(s, c) / (2 * math.pi)) % 1.0, len(times) * r * r


def periodogram(times, lo_s, hi_s, step_s):
    best = None
    n = int(round((hi_s - lo_s) / step_s))
    for i in range(n + 1):
        p = lo_s + i * step_s
        r = rayleigh(times, p)[0]
        if best is None or r > best[0]:
            best = (r, p)
    return best


# ------------------------------------------------------------------------------------------ VIDEO

def ai_callbacks(text):
    m = record(text, "LIVEM")
    t_first, t_last, n = int(m["t_first"], 16), int(m["t_last"], 16), int(m["callbacks"])
    return t_first, (t_last - t_first) / float(n - 1)          # ticks, ticks per callback


def video_losses(text):
    """Tick of every incomplete_interval event in the contiguous tail of the printed EVENTS."""
    e = record(text, "EVENTS")
    n, shown = int(e["n"]), int(e["shown"])
    tail_from = n - 64 + 1 if shown < n else 1                  # the log prints the first 128 and the last 64
    out = []
    for m in re.finditer(r"^\d{6} EV (.*)$", text, re.M):
        d = kv(m.group(1))
        if d["type"] == "incomplete_interval" and int(d["seq"]) >= tail_from:
            out.append((int(d["f"]), int(d["t"], 16)))
    return out, tail_from


def frame_clock(text, tail_from):
    """Least-squares tick of frame f, from the resync events of the same contiguous tail."""
    pts = []
    for m in re.finditer(r"^\d{6} EV (.*)$", text, re.M):
        d = kv(m.group(1))
        if d["type"] == "resync" and int(d["seq"]) >= tail_from:
            pts.append((int(d["f"]), int(d["t"], 16)))
    n = float(len(pts))
    mf = sum(f for f, _ in pts) / n
    mt = sum(t for _, t in pts) / n
    b = sum((f - mf) * (t - mt) for f, t in pts) / sum((f - mf) ** 2 for f, _ in pts)
    return mt - b * mf, b


def monte_carlo(text, vids, t_first, per, trials, seed=7):
    """How often random frame boundaries in the same span phase-lock at least as strongly."""
    _v, tail_from = video_losses(text)
    a, b = frame_clock(text, tail_from)
    obs = rayleigh([(t - t_first) / TB_HZ for _f, t in vids], per / TB_HZ)[0]
    lo, hi = min(f for f, _ in vids), max(f for f, _ in vids)
    rng = random.Random(seed)
    hits = 0
    for _ in range(trials):
        fr = rng.sample(range(lo, hi + 1), len(vids))
        if rayleigh([(a + b * f - t_first) / TB_HZ for f in fr], per / TB_HZ)[0] >= obs:
            hits += 1
    return hits


# ------------------------------------------------------------------------------------------ report

def analyse(text, sidecar_bytes, trials=20000):
    sys.path.insert(0, __import__("os").path.dirname(__file__))
    import v22accept                                            # the frozen sidecar parser, reused as is
    decoded = v22accept.parse_sidecar(sidecar_bytes)["decoded"]
    losses, halves = audio_losses(decoded)
    starts = episodes(losses)
    t_first, per = ai_callbacks(text)
    p_ai = per / TB_HZ
    vids, tail_from = video_losses(text)
    org = int(record(text, "LIVET")["t_origin"], 16)
    phases_ms = sorted(((t - t_first) % per) / TB_HZ * 1e3 for _f, t in vids)
    cov = []
    for m in re.finditer(r"^\d{6} LIVESEC from=\d+ counts=([\d,]+)", text, re.M):
        cov += [int(c) for c in m.group(1).split(",")]
    first_full = int(math.ceil((min(t for _f, t in vids) - org) / TB_HZ))
    secs = list(range(first_full, len(cov)))
    vc = [sum(1 for _f, t in vids if s <= (t - org) / TB_HZ < s + 1) for s in secs]
    deficit = [int(BLOCKS_PER_S) - cov[s] for s in secs]
    ma, mv = sum(deficit) / float(len(secs)), sum(vc) / float(len(secs))
    num = sum((x - ma) * (y - mv) for x, y in zip(deficit, vc))
    den = math.sqrt(sum((x - ma) ** 2 for x in deficit) * sum((y - mv) ** 2 for y in vc))
    return {
        "samples": len(decoded), "halves": len(halves),
        "loss_halves": len(losses), "losses": sum(k for _t, k in losses),
        "episodes": len(starts), "span_s": (len(decoded) + sum(k for _t, k in losses)) / BLOCKS_PER_S,
        "ai_period_ms": p_ai * 1e3,
        "audio_R_ai": rayleigh(starts, p_ai)[0],
        "audio_R_tone_grid": rayleigh(starts, 2 * HALF * 4 / BLOCKS_PER_S)[0],   # 128 blocks: 8 half-periods
        "audio_peak": periodogram(starts, 0.0309, 0.0316, 0.000001),
        "audio_intervals_in_chunks": sorted(round((starts[i + 1] - starts[i]) / p_ai) for i in range(len(starts) - 1)),
        "video_n": len(vids), "video_tail_from_seq": tail_from,
        "video_R_ai": rayleigh([(t - t_first) / TB_HZ for _f, t in vids], p_ai)[0],
        "video_phase_ms": phases_ms,
        "video_mc_hits": monte_carlo(text, vids, t_first, per, trials), "video_mc_trials": trials,
        "per_second_r": num / den if den else None, "per_second_span": (secs[0], secs[-1]),
    }


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        text = f.read()
    with open(argv[2], "rb") as f:
        side = f.read()
    r = analyse(text, side)
    iv = r["audio_intervals_in_chunks"]
    print("AUDIO  %d undrained blocks in %d of %d half-periods of the L2 window (%.3f s of device time), %d episodes"
          % (r["losses"], r["loss_halves"], r["halves"], r["span_s"], r["episodes"]))
    print("       phase-lock to the AI chunk period %.4f ms: R = %.3f; to the tone's 128-block grid (31.25 ms): R = %.3f"
          % (r["ai_period_ms"], r["audio_R_ai"], r["audio_R_tone_grid"]))
    print("       periodogram 30.9..31.6 ms: peak R = %.3f at %.3f ms (resolution about 0.1 ms over this span)"
          % (r["audio_peak"][0], r["audio_peak"][1] * 1e3))
    print("       intervals between episodes, in chunk periods: %s"
          % ", ".join("%dx%d" % (k, iv.count(k)) for k in sorted(set(iv))))
    print("VIDEO  %d incomplete frames in the contiguous tail of EVENTS (seq >= %d)" % (r["video_n"], r["video_tail_from_seq"]))
    print("       phase after the preceding AI callback, ms: %s" % ", ".join("%.1f" % p for p in r["video_phase_ms"]))
    print("       phase-lock to the AI chunk period: R = %.3f; random frame boundaries at least as locked: %d of %d"
          % (r["video_R_ai"], r["video_mc_hits"], r["video_mc_trials"]))
    print("SECONDS audio deficit against incomplete frames, s = %d..%d: Pearson r = %.3f"
          % (r["per_second_span"][0], r["per_second_span"][1], r["per_second_r"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
