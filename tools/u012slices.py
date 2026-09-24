#!/usr/bin/env python3
"""
tools/u012slices.py — GitHub Issue #118: does decoding the AUDIO block's slices recover the bandwidth that the
runtime's one-value-per-block decode throws away? DESCRIPTIVE, host-side, on archived bytes; it decides nothing.

    tools/u012slices.py [--json <out>]        (reads the versioned RUN 33 / RUN 34 raw captures)

WHAT THE ARCHIVE HOLDS. Whole 4 096-byte AUDIO blocks exist only for RUN 30-35's stimulus-ROM tones (OGBPAW1,
1 280 blocks a run); RUN 33 and RUN 34 are versioned. The live family (RUN 38-42, the game) kept ONE decoded value per
block, so a game's slices were never stored and are not reconstructed here.

THREE DECODES OF THE SAME BYTES, over each press window's sliced region (blocks 96-255, §V11.9):
  block   the runtime's: one value per block, the block's one-bit count (4 096/s nominal)
  pair    one value per two 256-byte slices (32 768/s nominal): GBP-HW-315's grid, every transition on an even slice
  slice   one value per 256-byte slice (65 536/s nominal)
"Nominal" because a slice's place in time assumes the sixteen slices are uniform (U-GBP-041, a HYPOTHESIS): every Hz
figure of the pair and slice decodes is conditional on it. The block decode's rate is not.

THE REFERENCE is the programmed tone itself: a 50 % square wave of the period tools/v17pred.py froze for the window
(P blocks, 128-1 024 Hz), sampled at the decode's own rate, at the phase that best fits -- the one free parameter.
Per decode it reports:
  high      the fraction of the tone's AC energy above 2 048 Hz (Parseval over the DFT; the region holds a whole
            number of periods, so the harmonics fall on bins), against the ideal square's own fraction. For the
            block decode this is 0 by IDENTITY -- its Nyquist is the cut -- so it is not a measurement and it is
            not tabulated; the record says "by its rate"
  corr      the correlation with the ideal square at its best phase
  harmonics each odd harmonic's amplitude over the fundamental's, up to the decode's Nyquist, against the ideal's
  in band   for the block decode, its own |H_n| / |H_1| at the harmonics below 2 048 Hz, beside the pair decode's:
            the runtime's value is a boxcar over eight pair values then a decimation by eight with no anti-alias
            stage, so the harmonics above the cut are attenuated and FOLDED onto in-band bins, not removed, and the
            in-band ratios move with where the edge falls in the block
Rules reused, not re-derived: tools/awinparse.py (the file), tools/v18block.py's slice counts, tools/v11sweep.py's
schedule and onset, tools/v17pred.py's frozen periods.

Standard library only; reads the fixtures, writes the JSON it is asked to.
"""
import cmath
import gzip
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import awinparse  # noqa: E402
import v11sweep  # noqa: E402
import v17pred  # noqa: E402
import v18block  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = {33: os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz"),
            34: os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-23-stream-0016-run34-audio.bin.gz")}
BLOCK_RATE = 4096
CUT_HZ = 2048.0
ONSET = v11sweep.ONSET_SLICE_BLOCKS
SLICES = v18block.SLICES
DECODES = (("block", 1), ("pair", SLICES // 2), ("slice", SLICES))     # values per block


def decode(region, per_block):
    """One value per 1/per_block of a block: the one-bit count of that part, from v18block's slice counts."""
    out = []
    group = SLICES // per_block
    for b in region:
        c = v18block.slice_counts(b)
        out += [float(sum(c[i * group:(i + 1) * group])) for i in range(per_block)]
    return out


def _dft(x, k):
    n = len(x)
    return sum(x[t] * cmath.exp(-2j * math.pi * k * t / n) for t in range(n))


def high_fraction(x, fs, cut=CUT_HZ):
    """The fraction of x's AC energy above `cut` Hz, by Parseval: total minus the bins at or below it."""
    n = len(x)
    m = sum(x) / n
    d = [v - m for v in x]
    total = sum(v * v for v in d)
    kmax = int(cut * n / fs)
    low = sum(2 * abs(_dft(d, k)) ** 2 / n for k in range(1, kmax + 1))
    if 2 * kmax == n:
        low -= abs(_dft(d, kmax)) ** 2 / n                # a Nyquist bin counts once
    return (total - low) / total if total else 0.0


def square(n, period, phase):
    return [1.0 if (t + phase) % period < period // 2 else -1.0 for t in range(n)]


def correlation(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    da, db = [v - ma for v in a], [v - mb for v in b]
    den = math.sqrt(sum(v * v for v in da) * sum(v * v for v in db))
    return sum(p * q for p, q in zip(da, db)) / den if den else 0.0


def best_square(x, period):
    best = None
    for ph in range(period):
        c = correlation(x, square(len(x), period, ph))
        if best is None or c > best[0]:
            best = (c, ph)
    return best


def harmonics(x, periods_in_region, per_block):
    """|H_n| / |H_1| for odd n below the decode's Nyquist."""
    m = sum(x) / len(x)
    d = [v - m for v in x]
    h1 = abs(_dft(d, periods_in_region))
    out = {}
    n = 3
    while n * periods_in_region < len(x) / 2.0:
        out[n] = abs(_dft(d, n * periods_in_region)) / h1
        n += 2
    return out


def analyse_window(region, period):
    per = {}
    periods_in_region = len(region) // period
    f0 = BLOCK_RATE / float(period)
    for name, pb in DECODES:
        x = decode(region, pb)
        fs = BLOCK_RATE * pb
        row = {"rate": fs, "values": len(x), "high": high_fraction(x, fs)}
        if pb > 1:
            corr, ph = best_square(x, period * pb)
            ideal = square(len(x), period * pb, ph)
            row.update(corr=corr, phase=ph, ideal_high=high_fraction(ideal, fs),
                       harmonics=harmonics(x, periods_in_region, pb),
                       ideal_harmonics=harmonics(ideal, periods_in_region, pb))
        else:
            row["harmonics"] = harmonics(x, periods_in_region, pb)        # in band by construction: n f0 < 2 048
        per[name] = row
    per["in_band"] = dict((n, {"block": per["block"]["harmonics"][n], "pair": per["pair"]["harmonics"][n]})
                          for n in per["block"]["harmonics"])
    return {"period_blocks": period, "f0_hz": f0, "decodes": per}


def load(path):
    with open(path, "rb") as f:
        data = f.read()
    if path.endswith(".gz"):
        data = gzip.decompress(data)
    h, anchors, off = awinparse.parse(data)
    return anchors, awinparse.windows(data, h, anchors, off)


def analyse(path):
    anchors, wins = load(path)
    press = [a for a in anchors if a["kind"] == 1]
    axis = v11sweep.derive_schedule([a["keys"] for a in press])
    periods = [int(p["period"]) for p in v17pred.predict(axis)]
    out = {"axis": axis, "windows": [], "controls": []}
    for wi, w in enumerate(wins):
        if anchors[wi]["kind"] == 1:
            r = analyse_window(w[ONSET:], periods[press.index(anchors[wi])])
            r["index"] = wi
            out["windows"].append(r)
        else:
            pair = decode(w[ONSET:], SLICES // 2)
            m = sum(pair) / len(pair)
            out["controls"].append({"index": wi, "pair_sd_bits": math.sqrt(sum((v - m) ** 2 for v in pair) / len(pair))})
    return out


AI_HZ = 32028.483                    # GBP-HW-325: the AI's frames per second of the console's timebase
CHUNK_FRAMES = 1000                  # GBP_APLAY_FRAMES
UPSAMPLE = (125, 16)                 # 4 096 -> 32 000: 125 output frames per 16 decoded samples (src/audio/gbp_aplay.h)
LOST_PER_S = {"RUN 38": 1626 / 64.0, "RUN 42": 465 / 64.0}    # GBP-HW-322 / GBP-HW-337: NOT DRAINED over C's 64 s
DUP_OBSERVED = {"RUN 38": 30.703}                              # GBP-HW-325: net DUP per second


def costs():
    """What a slice decode multiplies, in today's units (src/audio/gbp_aplay.h), and what the one-correction-per-chunk
    unit can slew against what the record says it must: arithmetic on recorded figures, nothing measured here."""
    chunks_per_s = AI_HZ / CHUNK_FRAMES                                          # 32.028: the correction ceiling
    consumed = AI_HZ * UPSAMPLE[1] / UPSAMPLE[0]                                 # 4 099.65 decoded samples/s
    need = dict((run, consumed - (BLOCK_RATE - lost)) for run, lost in LOST_PER_S.items())   # samples/s of DUP
    rates = {"block": BLOCK_RATE, "pair": BLOCK_RATE * 8, "slice": BLOCK_RATE * 16}
    return {"decoded_per_s": rates,
            "ring_1s_samples": dict(rates),
            "ring_1s_kib": dict((k, 2 * v / 1024.0) for k, v in rates.items()),
            "target_0_5s_samples": dict((k, v // 2) for k, v in rates.items()),
            "pushes_per_1000_frame_chunk": {"block": 128, "pair": 1024, "slice": 2048},
            "correction_ceiling_per_s": chunks_per_s,
            "one_correction_per_chunk_ms_per_s": dict((k, chunks_per_s * 1000.0 / v) for k, v in rates.items()),
            "consumed_decoded_per_s": consumed,
            "need_samples_per_s": need,
            "need_ms_per_s": dict((k, v * 1000.0 / BLOCK_RATE) for k, v in need.items()),
            "observed_dup_per_s": DUP_OBSERVED,
            "observed_dup_ms_per_s": dict((k, v * 1000.0 / BLOCK_RATE) for k, v in DUP_OBSERVED.items())}


def main(argv):
    res = {}
    for run, path in sorted(FIXTURES.items()):
        res[str(run)] = r = analyse(path)
        print("RUN %d (axis %s)" % (run, r["axis"]))
        for w in r["windows"]:
            d = w["decodes"]
            hp, hi = d["pair"]["harmonics"], d["pair"]["ideal_harmonics"]
            print("  w%d  P %2d  f0 %6.1f Hz   above 2 048 Hz: pair %.4f (ideal %.4f)  slice %.4f (ideal %.4f)"
                  "   corr pair %.5f slice %.5f   pair harmonics 3..%d, largest |measured - ideal| %.4f"
                  % (w["index"], w["period_blocks"], w["f0_hz"], d["pair"]["high"],
                     d["pair"]["ideal_high"], d["slice"]["high"], d["slice"]["ideal_high"], d["pair"]["corr"],
                     d["slice"]["corr"], max(hp), max(abs(hp[n] - hi[n]) for n in hp)))
            if d["in_band"]:
                print("      in band, block against pair |H_n/H_1|: %s"
                      % "  ".join("n=%d %.3f/%.3f" % (n, v["block"], v["pair"]) for n, v in sorted(d["in_band"].items())))
        for c in r["controls"]:
            print("  w%d  control: pair decode s.d. %.3f bits" % (c["index"], c["pair_sd_bits"]))
    res["costs"] = c = costs()
    print("costs (arithmetic): correction ceiling %.3f/s; consumed %.2f decoded/s; need RUN 38 %.2f/s = %.2f ms/s "
          "(observed %.3f/s = %.2f ms/s), RUN 42 %.2f/s = %.2f ms/s; one correction per chunk at the pair rate %.2f ms/s"
          % (c["correction_ceiling_per_s"], c["consumed_decoded_per_s"], c["need_samples_per_s"]["RUN 38"],
             c["need_ms_per_s"]["RUN 38"], c["observed_dup_per_s"]["RUN 38"], c["observed_dup_ms_per_s"]["RUN 38"],
             c["need_samples_per_s"]["RUN 42"], c["need_ms_per_s"]["RUN 42"], c["one_correction_per_chunk_ms_per_s"]["pair"]))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(res, f, sort_keys=True, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
