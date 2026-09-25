#!/usr/bin/env python3
"""
tools/v123chain.py — GitHub Issue #123: what decoding at the native rate would cost the chain, measured where the
hardware measured and computed where it did not. DESCRIPTIVE, host-side; it decides nothing and builds nothing.

    tools/v123chain.py [--json <out>]

1. THE MEASURED COST OF PRODUCTION TODAY. RUN 40's floorless sample (every chain step of every 8th AI cycle, split-0001,
   tools/v24report.py) times every production call on hardware. A call's tag says its arm (bit 0: 8 pushes, else 16)
   and whether it started the chunk (bit 1). The medians of the non-first calls give the cost per push (their slope) and
   per call (their intercept); a chunk of the runtime's 8-push calls is one first call and fifteen others. A push is one
   decoded sample through the 125/16 resampler: 7.8125 output frames of 16 taps, 125 multiply-accumulates.

2. THE FILTER. Today's (gbp_aresamp_coef.h, read from the committed table) and candidates for 65 536 -> 32 000 Hz
   (L/M = 125/256): a Kaiser-windowed sinc prototype, cut off at the output's 16 kHz, N taps per phase. For each: the
   passband's worst deviation up to Fp and the stopband's least attenuation from 32 000 - Fp to twice the input rate
   (what folds into the passband), for Fp = 5 256 Hz (half of RUN 43's 10 512 Hz hold, GBP-HW-346's game band) and
   12 000 Hz; the delay, N/2 input samples. Today's interpolator is read against its own job: passband 0..1 500 Hz,
   stopband its first images from 4 096 - 1 500 Hz to 16 kHz. Evaluated on a 250 Hz grid, not proved: a grid can
   miss a narrow peak.

3. THE INSTRUCTION MODEL (INFERENCE), for what section 1 cannot separate: its slope is 125 MACs AND one input's
   handling at once, so the hardware alone does not say how a native chain -- 16 times the inputs a channel, twice
   the channels -- would cost. The resampler compiled for the Gekko (powerpc-eabi-gcc -O2 -mogc -mcpu=750, the
   images' flags, in the project's container: `docker compose run --rm -T dev powerpc-eabi-objdump -d` of
   gbp_aresamp.o and gbp_adec.o) counts: 9 instructions a tap (the inner loop), 27 more an output frame (its setup,
   rounding, clamp and store), 46 a push that makes an output and 28 one that does not; the block popcount, 4 a byte.
   Assumed on top: 15 a take (the ring's pop) and 8 a frame for the chunk's big-endian store. At one instruction a
   cycle and 12 CPU cycles a tick, the model is CALIBRATED against section 1's measured chunk: the ratio of the two is
   applied to every native estimate. Cache traffic is not modelled.
   THE PRICE IN MARGIN. A production call is a stretch the drain cannot run in, and longer stretches lose more AUDIO
   blocks (GBP-HW-332). Holding today's call length (RUN 40's 8-push median) turns more work into MORE CALLS a chunk,
   and a chunk's refill after a hand-off then takes at least that many pump runs: at RUN 43's pump rate (3 676 a
   second, tools/v28ahead.py) that is the NOMINAL refill, one call a pump run and no gap. The hardware's refill is
   longer: RUN 40's 8-push arm, 16 calls, measured a median of 4.86 ms and a largest of 6.12 ms against a nominal
   4.23 ms at its own pump rate (tools/v28ahead.py). tools/v28ahead.py's margin is A x 31.222 ms less that LARGEST
   refill, so the native refill is also carried to that basis, two ways, because one run cannot say how the excess
   grows with the calls: SCALED (the nominal x 6.12 / 4.23, the excess growing with the refill) and ADDITIVE (the
   nominal + 1.89 ms, the excess a fixed tail). The margin is given on the nominal and on both.

4. THE BUDGET, ARITHMETIC (every figure beyond section 1 is INFERENCE and says so):
     corrections  k per 1 000-frame chunk at 32.03 chunks/s, each one sample of the decode rate: the slew it allows;
     production   multiply-accumulates per chunk against today's 16 000, mono and stereo; the CPU share IF section 1's
                  whole measured chunk, its per-call and first-call overheads included, scaled with them (MAC scaling
                  only: above section 1's cost per MAC alone, and BELOW section 3's model for the 16- and 32-tap
                  chains, which adds the native inputs' handling). The native chain's per-input overhead (2 048 inputs
                  a chunk instead of 128) is NOT measured, and this figure leaves it out (section 3 models it, as
                  INFERENCE): the first native image must time it
     decode       bytes a block's decode must count (today all 4 096; per channel per slice, 64 of each 256: 1 024) and
                  values a block yields (1; 32 per channel pair per slice)
     latency      the resampler's delay today against each candidate's
     memory       the coefficient table and a ring at the native rate

Standard library only; reads the fixtures and the committed header, writes the JSON it is asked to.
"""
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import v28ahead  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COEF_H = os.path.join(ROOT, "src", "audio", "gbp_aresamp_coef.h")
TB_HZ = 40500000
AI_CYCLE_TICKS = 1264500                 # one 1 000-frame chunk at the AI's measured 32 028.478 Hz (RUN 40/43)
CHUNKS_PER_S = TB_HZ / float(AI_CYCLE_TICKS)
FRAMES = 1000                            # output frames per chunk (GBP_APLAY_FRAMES)
OUT_HZ = 32000                           # the resampler's nominal output rate
TODAY = {"rate": 4096, "taps": 16, "pushes": 128}
RATES = (4096, 32768, 65536)
CANDIDATES = ((16, 5.65), (32, 5.65), (32, 7.86), (48, 7.86), (64, 7.86))   # (taps per phase, Kaiser beta)
# the instruction model (section 3): counts from the Gekko disassembly, and the two assumed on top
TAP_INSTR, FRAME_INSTR = 9, 27
PUSH_OUT_INSTR, PUSH_NONE_INSTR = 46, 28
TAKE_INSTR, STORE_INSTR = 15, 8
POPCOUNT_INSTR_PER_BYTE = 4
CYCLES_PER_TICK = 12                     # 486 MHz / 40.5 MHz
FPS = (5256.0, 12000.0)
L_NATIVE = 125                           # 65 536 -> 32 000 = 125 / 256


def median(x):
    s = sorted(x)
    return s[len(s) // 2]


def production_cost():
    """Section 1, from RUN 40's floorless sample."""
    rep = v28ahead.build(40)
    by = {}
    for s, e, kind, tag in rep["sample"]["steps"]:
        if kind != "produce" or tag == 0:
            continue
        key = (8 if tag & 1 else 16, bool(tag & 2))
        by.setdefault(key, []).append(e - s)
    m8, m16 = median(by[(8, False)]), median(by[(16, False)])
    slope = (m16 - m8) / 8.0
    first8 = median(by[(8, True)])
    chunk8 = first8 + (TODAY["pushes"] // 8 - 1) * m8
    return {"n": dict(("%d%s" % (k[0], "first" if k[1] else ""), len(v)) for k, v in by.items()),
            "median": {"8": m8, "16": m16, "8first": first8, "16first": median(by[(16, True)])},
            "per_push": slope, "per_call": m8 - 8 * slope, "per_mac": slope / 125.0,
            "chunk_8push": chunk8, "cpu_share": chunk8 / float(AI_CYCLE_TICKS)}


def bessel_i0(x):
    s, term, k = 1.0, 1.0, 1
    while term > 1e-12 * s:
        term *= (x / (2.0 * k)) ** 2
        s += term
        k += 1
    return s


def prototype(taps, beta, fin, cutoff, L):
    """A Kaiser-windowed sinc sampled at L per input sample, spanning taps input samples; DC gain L."""
    half = taps / 2.0
    n0 = int(round(half * L))
    h = []
    for n in range(-n0, n0 + 1):
        t = n / float(L)                                     # input samples
        x = 2.0 * cutoff / fin * t
        s = 1.0 if x == 0 else math.sin(math.pi * x) / (math.pi * x)
        r = t / half
        w = bessel_i0(beta * math.sqrt(max(0.0, 1.0 - r * r))) / bessel_i0(beta) if abs(r) <= 1.0 else 0.0
        h.append(2.0 * cutoff / fin * s * w)
    g = sum(h)
    return [v * L / g for v in h]


def response(h, f, fs):
    """|H(f)| / L for a symmetric filter h at sampling rate fs (the upsampled rate)."""
    c = (len(h) - 1) / 2.0
    acc = 0.0
    for n, v in enumerate(h):
        acc += v * math.cos(2.0 * math.pi * f * (n - c) / fs)
    return abs(acc)


def filter_figures(h, fin, L, fp, stop_lo, stop_hi):
    """(worst passband deviation dB up to fp, least attenuation dB over [stop_lo, stop_hi]) on a 250 Hz grid."""
    fs = fin * L
    dc = response(h, 0.0, fs)
    pb = [response(h, fp * i / 24.0, fs) / dc for i in range(25)]
    dev = max(abs(20.0 * math.log10(max(v, 1e-12))) for v in pb)
    stop = []
    f = stop_lo
    while f <= stop_hi:
        stop.append(response(h, f, fs) / dc)
        f += 250.0
    return dev, -20.0 * math.log10(max(max(stop), 1e-12))


def todays_filter():
    with open(COEF_H, encoding="utf-8") as f:
        txt = f.read()
    rows = re.findall(r"\{([-0-9, ]+)\}", txt[txt.index("GBP_ARESAMP_COEF["):])
    table = [[int(v) for v in r.split(",")] for r in rows]
    L, taps = len(table), len(table[0])
    # interleave the phases back into one prototype: tap m of phase p sits at offset (7 - m) + p / L input samples
    points = {}
    for p in range(L):
        for m in range(taps):
            points[round(((taps // 2 - 1) - m) * L + p)] = table[p][m] / 32768.0
    lo, hi = min(points), max(points)
    h = [points.get(n, 0.0) for n in range(lo, hi + 1)]
    return h, L, taps


def chunk_instructions(rate, taps, channels):
    """The instruction model's count for one 1 000-frame chunk (section 3)."""
    inputs = FRAMES * rate // OUT_HZ if rate > 4096 else TODAY["pushes"]
    if rate == 4096:                                     # every input makes 7 or 8 outputs
        per_ch = inputs * (PUSH_OUT_INSTR + TAKE_INSTR) + FRAMES * (FRAME_INSTR + TAP_INSTR * taps)
    else:                                                # an input makes 0 or 1 output: FRAMES of them do
        per_ch = (FRAMES * PUSH_OUT_INSTR + (inputs - FRAMES) * PUSH_NONE_INSTR + inputs * TAKE_INSTR
                  + FRAMES * (FRAME_INSTR + TAP_INSTR * taps))
    return channels * per_ch + FRAMES * STORE_INSTR


def analyse():
    prod = production_cost()
    h0, L0, taps0 = todays_filter()
    # today's interpolator: its passband is the decode's 0..1 500 Hz, its stopband the input's first images, from
    # 4 096 - 1 500 Hz to the AI's 16 kHz
    filters = {"today_4096_N16": {"delay_ms": taps0 / 2.0 / 4096 * 1000.0,
                                  "fp": {"1500": filter_figures(h0, 4096, L0, 1500.0, 4096 - 1500.0, 16000.0)}}}
    # the native decimator: what folds into 0..Fp comes from OUT_HZ - Fp up; evaluated to 2 x the input rate
    for taps, beta in CANDIDATES:
        h = prototype(taps, beta, 65536, 16000.0, L_NATIVE)
        filters["65536_N%d_b%.2f" % (taps, beta)] = {
            "delay_ms": taps / 2.0 / 65536 * 1000.0,
            "fp": dict(("%d" % fp, filter_figures(h, 65536, L_NATIVE, fp, OUT_HZ - fp, 2.0 * 65536))
                       for fp in FPS)}
    corrections = {}
    for rate, k in ((4096, 1), (32768, 8), (65536, 16), (65536, 8)):
        corrections["%d_k%d" % (rate, k)] = {"per_s": k * CHUNKS_PER_S, "each_us": 1e6 / rate,
                                              "ms_per_s": k * CHUNKS_PER_S * 1000.0 / rate}
    macs_today = FRAMES * TODAY["taps"]
    production = {}
    for taps, _b in CANDIDATES:
        for ch in (1, 2):
            macs = FRAMES * taps * ch
            production["N%d_ch%d" % (taps, ch)] = {"macs": macs, "ratio": macs / float(macs_today),
                                                   "cpu_if_mac_scaled": prod["cpu_share"] * macs / float(macs_today)}
    pump_per_s = v28ahead.pump_rate(v28ahead.read(v28ahead.GAMES[43]))[2]
    ahead = v28ahead.analyse()["traced"]["40"]
    arm8 = ahead["arms"]["8"]
    basis = {"run40_pump_per_s": ahead["pump_per_s"], "run40_nominal_ms": 16 * 1000.0 / ahead["pump_per_s"],
             "run40_median_ms": arm8["median"], "run40_max_ms": arm8["max"]}
    basis["ratio_max"] = basis["run40_max_ms"] / basis["run40_nominal_ms"]
    basis["ratio_median"] = basis["run40_median_ms"] / basis["run40_nominal_ms"]
    basis["excess_max_ms"] = basis["run40_max_ms"] - basis["run40_nominal_ms"]

    def refill_forms(nominal):
        forms = {"nominal": nominal, "worst_scaled": nominal * basis["ratio_max"],
                 "worst_additive": nominal + basis["excess_max_ms"]}
        return forms, dict((f, dict((str(a), a * period_ms - r) for a in (1, 2))) for f, r in forms.items())
    period_ms = AI_CYCLE_TICKS * 1000.0 / TB_HZ
    model_today = chunk_instructions(4096, 16, 1) / float(CYCLES_PER_TICK)
    calib = prod["chunk_8push"] / model_today
    native = {}
    for rate in (65536, 32768):
        for taps in (16, 32):
            for ch in (1, 2):
                ticks = chunk_instructions(rate, taps, ch) / float(CYCLES_PER_TICK) * calib
                calls = int(math.ceil(ticks / prod["median"]["8"]))
                refill = calls * 1000.0 / pump_per_s
                forms, margins = refill_forms(refill)
                native["%d_N%d_ch%d" % (rate, taps, ch)] = {
                    "ticks": ticks, "cpu": ticks / AI_CYCLE_TICKS, "x_today": ticks / prod["chunk_8push"],
                    "calls_at_todays_length": calls, "refill_ms": refill,
                    "margin_ms": margins["nominal"], "refill_forms_ms": forms, "margin_forms_ms": margins}
    today_calls = TODAY["pushes"] // 8
    today_forms, today_margins = refill_forms(today_calls * 1000.0 / pump_per_s)
    model = {"today_ticks": model_today, "calibration": calib, "native": native, "pump_per_s": pump_per_s,
             "today_refill_ms": today_calls * 1000.0 / pump_per_s, "refill_basis": basis,
             "today_refill_forms_ms": today_forms, "today_margin_forms_ms": today_margins,
             "decode_instr_per_block": {"today": 4096 * POPCOUNT_INSTR_PER_BYTE,
                                        "per_channel_slice": 1024 * POPCOUNT_INSTR_PER_BYTE},
             "values_per_s": {"today": 4096, "native_stereo": 65536 * 2}}
    return {"production_today": prod, "filters": filters, "corrections": corrections, "production": production,
            "model": model,
            "decode": {"bytes_counted": {"today": 4096, "per_channel_slice": 16 * 64},
                       "values_per_block": {"today": 1, "per_channel_slice": 16 * 2}},
            "inputs_per_chunk": dict(("%d" % r, FRAMES * r // OUT_HZ) for r in RATES if r >= 32768),
            "memory": {"coef_bytes": dict(("N%d" % t, 125 * t * 4) for t, _b in CANDIDATES),
                       "ring_bytes_1s_stereo_65536": 65536 * 2 * 2,
                       "target_0125s_stereo_65536": int(65536 * 0.125) * 2 * 2}}


def main(argv):
    r = analyse()
    p = r["production_today"]
    print("production today (RUN 40, hardware): non-first call median %d ticks (8 pushes), %d (16); first %d / %d; "
          "%.1f ticks a push, %.1f a call, %.3f a MAC; a chunk of 8-push calls %d ticks = %.2f %% of the CPU"
          % (p["median"]["8"], p["median"]["16"], p["median"]["8first"], p["median"]["16first"], p["per_push"],
             p["per_call"], p["per_mac"], p["chunk_8push"], 100 * p["cpu_share"]))
    for name, f in r["filters"].items():
        print("filter %-18s delay %.3f ms; %s" % (name, f["delay_ms"], "; ".join(
            "Fp %s: passband %.2f dB, stop %.1f dB" % (fp, v[0], v[1]) for fp, v in f["fp"].items())))
    for name, c in r["corrections"].items():
        print("corrections %-10s %.1f /s of %.1f us = %.2f ms/s" % (name, c["per_s"], c["each_us"], c["ms_per_s"]))
    for name, c in r["production"].items():
        print("production %-7s %6d MACs a chunk = %.1f x today; %.2f %% of the CPU IF the whole measured chunk "
              "scaled with MACs (INFERENCE)" % (name, c["macs"], c["ratio"], 100 * c["cpu_if_mac_scaled"]))
    m = r["model"]
    print("instruction model: today's chunk %.0f ticks against %d measured (calibration %.3f)"
          % (m["today_ticks"], p["chunk_8push"], m["calibration"]))
    for name, c in m["native"].items():
        print("  native %-14s %6.0f ticks a chunk = %.1f x today = %.2f %% of the CPU; at today's call length %d "
              "calls, a nominal refill of ~%.1f ms, AHEAD 1 / 2 margin %.1f / %.1f ms (INFERENCE)"
              % (name, c["ticks"], c["x_today"], 100 * c["cpu"], c["calls_at_todays_length"], c["refill_ms"],
                 c["margin_ms"]["1"], c["margin_ms"]["2"]))
        for f in ("worst_scaled", "worst_additive"):
            print("  %-23s %s refill ~%.1f ms, AHEAD 1 / 2 margin %.1f / %.1f ms"
                  % ("", f, c["refill_forms_ms"][f], c["margin_forms_ms"][f]["1"], c["margin_forms_ms"][f]["2"]))
    b = m["refill_basis"]
    print("  today: 16 calls, a nominal refill of ~%.1f ms at %.0f pump runs a second; worst scaled %.1f, additive "
          "%.1f ms" % (m["today_refill_ms"], m["pump_per_s"], m["today_refill_forms_ms"]["worst_scaled"],
                       m["today_refill_forms_ms"]["worst_additive"]))
    print("  the basis: RUN 40's 8-push refill median %.2f / largest %.2f ms against a nominal %.2f ms at %.0f pump "
          "runs a second (x %.3f / + %.2f ms)" % (b["run40_median_ms"], b["run40_max_ms"], b["run40_nominal_ms"],
                                                    b["run40_pump_per_s"], b["ratio_max"], b["excess_max_ms"]))
    print("  decode instructions a block %s; values a second %s" % (m["decode_instr_per_block"], m["values_per_s"]))
    print("decode: bytes counted a block %s; values a block %s; inputs a chunk %s" % (
        r["decode"]["bytes_counted"], r["decode"]["values_per_block"], r["inputs_per_chunk"]))
    print("memory: %s" % r["memory"])
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(r, f, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
