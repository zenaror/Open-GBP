#!/usr/bin/env python3
"""tools/v28latency.py -- GitHub Issue #139 (U-GBP-049): L(T, A), the latency of the NATIVE audio path, from measured levels.

    tools/v28latency.py [<validation_run log>] [--json <out>]

THE DEFINITION (written once; tests/unit/test_v28_stock.c proves it on the real chain and quotes it). The latency of a sample is the time from its
entering the decoder's ring to its being PLAYED at the AI. The AI plays continuously, one chunk of 2048 input-domain samples (1000 frames) a
hand-off period, so that time is the number of input-domain samples AHEAD of the sample -- the STOCK S -- divided by the playout rate:

    S = ring + (pushes already in the chunk being filled) + 2048 x READY + 2048 (the chunk PROGRAMMED at the last hand-off)
        + 2048 x (1 - phi)                      (phi: the fraction of the hand-off period elapsed; the last term is the unplayed part of the playing chunk)
    L = S / playout rate  +  the resampler's delay

gbp_aplay2's producer only MOVES samples (ring -> chunk being filled -> READY) and the hand-off moves a chunk (READY -> programmed -> playing), so S
changes only by the feed (+), the playout (-) and one sample per DUP (+) or DROP (-). THE SAWTOOTH THE RING SHOWS IS IN HOW THE STOCK IS SPLIT, NOT IN ITS
TOTAL: on the real chain S is flat to about 0.34 ms at every AHEAD and TARGET tried, while the ring alone swings by 1.5 chunks. At a chunk start READY = AHEAD - 1, so

    S = c + 2048 (AHEAD + 1) - 2048 phi,   c = the ring at the chunk's start (gbp_aplay2's cur_s0)

-- the structure of #122's 4096 Hz formula, c + 128 (A + 1) + 8, in native samples.

CLOCKS, MEASURED, never nominal: the playout rate is the AI's 32 028.483 frames a second (GBP-HW-325, RUN 38's MEASUREMENT M; nominal 32 000 is 0.09 % off),
so 2048 input samples take 1000 / 32 028.483 s = 31.222 ms; the feed is the run's own `blocks_in` over its own seconds x 16 samples a block (RUN 55's 3b hold:
4 081.5 blocks a second, 65 303 samples a second), not 4096 a second. The resampler's group delay is GBP-HW-350's 0.122 ms (16 taps at 65 536 Hz).

WHAT L EXCLUDES, in every table this tool prints: it is ring entry -> AI output, the AUDIO PATH'S OWN latency. It leaves out everything BEFORE the tap (the
AGB, the Game Boy Player, the HSP drain and the decode's own scheduling) and everything AFTER the AI (its DMA and DAC, the television's audio path). It is NOT
the audio-versus-video OFFSET the perceptual run nulls: that needs the video path's latency too, which this tool does not have.

WHERE c COMES FROM. With the loss below the corrector's authority the chunk start sits at target - BAND (256) less a few samples: RUN 55's 3b hold, `mean_cs`
3 828 at target 4 096 (-268); the calibrated host, 3 826-3 837 at feeds 0.18-0.65 % slow (-259..-270). c cannot fall below the production gate, 2 049:
a chunk starts only when the ring holds 2 049, so at TARGET <= 2 317 the chunk-start level is the gate and L(T, A) stops falling (the design's floor). The spread of c on the console
is what the ring's minimum shows: min ring = c_min - 2048 + feed x tau, tau the production time of a 64-push chunk (32 pump calls), so c_min is derived from `min_ring_late`
and the run's own pump cadence; the upper spread is not logged (the corrector only adds samples below the band, so c has no reason to exceed its mean by much; the host's is +5).

Standard library only.
"""
import json
import os
import re
import sys

PUSHES = 2048
FRAMES = 1000
AI_HZ = 32028.483                  # GBP-HW-325 (RUN 38's MEASUREMENT M)
AI_HZ_NOMINAL = 32000.0
PERIOD_MS = FRAMES / AI_HZ * 1000.0                 # 31.222 ms
RATE = PUSHES / (PERIOD_MS / 1000.0)                # input-domain samples played a second: 65 594
RESAMPLER_MS = 0.122                                # GBP-HW-350
BAND = 256
GATE = PUSHES + 1                                   # a chunk starts only when the ring holds this
C_BELOW_TARGET = 268                                # RUN 55, 3b at T4096: mean chunk start 3 828 = target - 268
PHI_START = 0.0055                                  # the phase at which a chunk starts (the host: 0.002-0.008 of a period)
LADDER_T = (11264, 9216, 7168, 5120, 4096, 3072)    # gbp_v28_ladder.h: T704 T576 T448 T320 T256 T192, native samples
AHEADS = (4, 3, 2, 1)
STEP_CALLS = 32                                     # a 64-push chunk is 2048 / 64 pump calls


def c_of_target(target):
    """The chunk-start level the corrector holds at `target` (native samples): target - 268, floored at the production gate."""
    return max(target - C_BELOW_TARGET, GATE)


def stock_at_chunk_start(c, ahead, phi=PHI_START):
    return c + PUSHES * (ahead + 1) - PUSHES * phi


def latency_ms(c, ahead, phi=PHI_START, rate=RATE):
    """L in ms for a chunk-start level c and AHEAD: the stock over the playout rate, plus the resampler's delay."""
    return stock_at_chunk_start(c, ahead, phi) / rate * 1000.0 + RESAMPLER_MS


def ladder():
    return [(t, a, c_of_target(t), latency_ms(c_of_target(t), a)) for t in LADDER_T for a in AHEADS]


def floor_ms(ahead):
    """The design's floor at an AHEAD: the chunk start on the production gate."""
    return latency_ms(GATE, ahead)


def old_formula_ms(target, ahead):
    """#122's 4096 Hz formula, L = (c + 128 (A + 1) + 8) / 4.096 ms with c = TARGET - 16.5, TARGET in OLD samples (native / 16)."""
    return (target / 16.0 - 16.5 + 128.0 * (ahead + 1) + 8.0) / 4.096


def old_terms_ms(target, ahead):
    """The old formula's three terms: ring, chunks, resampler."""
    return ((target / 16.0 - 16.5) / 4.096, 128.0 * (ahead + 1) / 4.096, 8.0 / 4.096)


def new_terms_ms(target, ahead):
    c = c_of_target(target)
    return (c / RATE * 1000.0, PUSHES * (ahead + 1) / RATE * 1000.0, -PUSHES * PHI_START / RATE * 1000.0, RESAMPLER_MS)


def kv(rest):
    return dict(re.findall(r"(\S+)=(\S+)", rest))


def from_log(text):
    """The 3b hold's measured levels and what they give, from a validation_run log that carries V28_3BM and V28PHC (RUN 55 on)."""
    m3b = [kv(m.group(1)) for m in re.finditer(r"^\d{6} V28_3B (.*)$", text, re.M)]
    m3bm = [kv(m.group(1)) for m in re.finditer(r"^\d{6} V28_3BM (.*)$", text, re.M)]
    anchor = re.search(r"^\d{6} V28ANCHOR target=(\d+)", text, re.M)
    phc = {int(kv(m.group(1))["p"]): kv(m.group(1)) for m in re.finditer(r"^\d{6} V28PHC (.*)$", text, re.M)}
    if not (m3b and m3bm and anchor and 2 in phc):
        return None
    a1 = [r for r in m3b if r["ahead"] == "1"][0]
    bm = [r for r in m3bm if r["n"] == a1["n"]][0]
    target = int(anchor.group(1))
    tb = 40_500_000
    t_set, t_done = int(a1["t_set"], 16), int(a1["t_done"], 16)
    secs = (t_done - t_set) / tb
    samples = int(a1["samples"])
    calls_per_period = samples / (secs / (PERIOD_MS / 1000.0))
    blocks_s = int(phc[2]["blocks_in"]) / ((int(phc[2]["t1"], 16) - int(phc[2]["t0"], 16)) / tb)
    feed = blocks_s * 16.0
    tau_ms = STEP_CALLS / calls_per_period * PERIOD_MS
    feed_tau = feed * tau_ms / 1000.0
    c = int(bm["mean_cs"])
    c_min = int(bm["min_ring_late"]) + PUSHES - feed_tau
    ring_mean_model = c - (PUSHES - feed_tau) / 2.0
    return {"target": target, "ahead": 1, "hold_s": secs, "calls_per_period": calls_per_period, "feed_hz": feed,
            "blocks_s": blocks_s, "tau_ms": tau_ms, "feed_tau": feed_tau, "mean_cs": c, "mean_ring": int(bm["mean_ring"]),
            "min_ring_late": int(bm["min_ring_late"]), "c_min": c_min, "ring_mean_model": ring_mean_model,
            "L_mean_ms": latency_ms(c, 1), "L_low_ms": latency_ms(c_min, 1), "L_of_target_ms": latency_ms(c_of_target(target), 1),
            "underrun_seen": int(a1["underrun_seen"]), "chunk_starts": int(bm["chunk_starts"])}


def render(measured):
    out = []
    w = out.append
    w("L(T, A): the NATIVE audio path's own latency, ring entry -> AI output (ms). Stock over the playout rate, plus the resampler's %.3f ms." % RESAMPLER_MS)
    w("Clocks (measured): AI %.3f Hz (GBP-HW-325; nominal %.0f), 2048 samples = %.3f ms, playout rate %.0f samples/s; the feed is the run's own blocks_in x 16 (RUN 55: 65 303/s)."
      % (AI_HZ, AI_HZ_NOMINAL, PERIOD_MS, RATE))
    w("EXCLUDED: everything before the tap (AGB, Game Boy Player, HSP drain, decode scheduling) and everything after the AI (DMA, DAC, the television's audio path).")
    w("This is NOT the audio-versus-video OFFSET the perceptual run nulls: that needs the video path's latency, which is not here.")
    w("")
    w("chunk-start level c = TARGET - %d (RUN 55, 3b at T4096: mean_cs 3 828), floored at the production gate %d; phi at a chunk start %.4f of a period." % (C_BELOW_TARGET, GATE, PHI_START))
    w("  TARGET      native   (ms of ring)   c      L at AHEAD 4      3      2      1")
    by_t = {}
    for t, a, c, l in ladder():
        by_t.setdefault(t, {})[a] = (c, l)
    names = {11264: "T704", 9216: "T576", 7168: "T448", 5120: "T320", 4096: "T256", 3072: "T192"}
    for t in LADDER_T:
        row = by_t[t]
        w("  %-6s  %9d   (%6.1f ms)   %5d   %13.1f %7.1f %6.1f %6.1f" % (names[t], t, t / RATE * 1000.0, row[4][0], row[4][1], row[3][1], row[2][1], row[1][1]))
    w("  the design's floor (chunk start on the production gate %d): AHEAD 4 %.1f, 3 %.1f, 2 %.1f, 1 %.1f ms" % ((GATE,) + tuple(floor_ms(a) for a in AHEADS)))
    w("")
    o, n = old_terms_ms(4096, 1), new_terms_ms(4096, 1)
    w("The old figure at T256 / A1: #122's formula gives %.1f ms (ring %.2f + chunks %.2f + resampler %.2f). Native: %.1f ms (ring %.2f + chunks %.2f + phase %+.2f + resampler %.2f)."
      % (old_formula_ms(4096, 1), o[0], o[1], o[2], latency_ms(c_of_target(4096), 1), n[0], n[1], n[2], n[3]))
    w("  the change, by term: resampler %+.2f ms (the 16-tap filter at 65 536 Hz against the old 8 samples at 4 096), ring %+.2f (c sits at TARGET - BAND - 12 in both), "
      "chunks %+.2f (the AI's measured clock against the nominal), phase %+.2f (a chunk starts %.4f of a period after the hand-off)"
      % (n[3] - o[2], n[0] - o[0], n[1] - o[1], n[2], PHI_START))
    if measured:
        m = measured
        w("")
        w("RUN 55's 3b hold, measured (AHEAD 1, target %d, %.1f s, underrun_seen %d, %d chunk starts):" % (m["target"], m["hold_s"], m["underrun_seen"], m["chunk_starts"]))
        w("  pump cadence %.1f calls a period; feed %.0f samples/s (blocks_in %.1f/s); production tau = %d calls = %.2f ms = %.0f samples of feed" % (
            m["calls_per_period"], m["feed_hz"], m["blocks_s"], STEP_CALLS, m["tau_ms"], m["feed_tau"]))
        w("  mean chunk start c = %d (%+d vs target): L = %.2f ms" % (m["mean_cs"], m["mean_cs"] - m["target"], m["L_mean_ms"]))
        w("  lowest chunk start, derived from min ring after 10 s (%d): c_min = %.0f: L = %.2f ms (%.2f ms below the mean's)" % (
            m["min_ring_late"], m["c_min"], m["L_low_ms"], m["L_mean_ms"] - m["L_low_ms"]))
        w("  the model's check: mean ring = c - (2048 - feed x tau)/2 = %.0f, measured %d (%+.0f)" % (m["ring_mean_model"], m["mean_ring"], m["mean_ring"] - m["ring_mean_model"]))
        w("  the table's own value at this rung (c = target - %d): %.2f ms" % (C_BELOW_TARGET, m["L_of_target_ms"]))
    return "\n".join(out)


def main(argv):
    measured = None
    args = [a for a in argv[1:] if not a.startswith("--")]
    if "--json" in argv:
        args = [a for a in args if a != argv[argv.index("--json") + 1]]
    if args:
        with open(args[0], encoding="utf-8", errors="replace") as f:
            measured = from_log(f.read())
    print(render(measured))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump({"ladder": ladder(), "measured": measured, "floor_ms": dict((a, floor_ms(a)) for a in AHEADS)}, f, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
