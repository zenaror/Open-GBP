#!/usr/bin/env python3
"""
tools/v125ref.py — GitHub Issue #125, step 3: the audio parameters of the two reference implementations, recomputed from
the private binaries, so that every figure the records quote from a reference's TABLES and SDA constants is this tool's
output, not a transcription. The figures read from the CODE are not recomputed here: the output rings and voice delays,
the landing buffers, the Disc's 640 / 180 / 320-sample ring figures, the AI buffer sizes and the fade constants. They
rest on the reading's decompiles (their manifest: docs/research/manifests/issue-125-ghidra125.sha256).

    tools/v125ref.py [--json <out>]

WHAT IT READS, never writes and never prints: the Start-up Disc's main.dol (input/extracted/gbp-disc/sys/main.dol) and
the three GBI editions (input/gbi/apps/<e>/<e>.dol, unpacked in memory by tools/gbi_unpack.py). It prints derived
parameters (sums, responses, ratios, identities) and a few raw PARAMETERS: the Disc's three 16.16 steps, its four edge
classes, its five SDA2 constants, the gain curve's end points and GBI's filter-flag bytes. It never prints or stores the
large tables (byte LUT, window, resampler, gain curve, edge positions) or GBI's filter coefficients. Absent inputs are
reported absent.

WHERE THE TABLES ARE is a LOCATOR taken from the headless Ghidra reading of #125 (build/analysis/ghidra125/, private):
the address of each table the audio path reads. What a table IS is not taken from the reading; it is checked here
against a construction from first principles where one exists (the centred popcount, the per-bit weight, the squared
gain law, the edge-position masks) and measured where none does (the window, the resampler, the biquad presets).

THE DISC (addresses are the DOL's own):
  byte LUT    256 f32   the value of one stream byte           -> linear in its bits? weight per bit, centre
  window      256 f32   the decimator's coefficients           -> sum, symmetry, response (bytes at 2^21 Hz)
  resampler   128 x 4   Q15 taps                               -> per-phase sums, phase-averaged response
  steps       3 u32     16.16 input samples per output         -> ratios, output rates vs 32 000 and 32 028.483
  classes     4 s32     the edge-spacing classes, in bytes
  gain        128 f32   the volume curve                       -> equal to (k / 127)^2 ?
  edgepos     256 s8    bit position of a byte's first rising edge -> equal to the constructed table, all 256?
  masks       8 bytes   at r13 - 0x7840                        -> equal to 0xFF >> p ?
  constants   SDA2 (r2) floats the decode and the clamp use
THE GBI EDITIONS (load 0x80003100, VERIFIED here by construction: the code builds each anchor's address):
  the s16 centred-popcount table and the f32 (popcount - 4) x 8192 table, found by CONTENT (constructed patterns);
  the two biquad presets and the default coefficients (r13 + an offset per edition), compared across editions and
  measured at the byte rate 2^21 Hz; the filter flag the hand-off tests (its initial byte decides the DEFAULT converter,
  and its address is verified by construction too, with the site that builds it); the AESND default output rate
  54 MHz / 1124 as a float, held as a double; and LIBAESND's mixer microcode, found by its sha256 alone.

Every Hz figure assumes one stream bit per AGB cycle at 2^24 Hz and uniform slices (U-GBP-041, a HYPOTHESIS).
DESCRIPTIVE: what a reference does is a LEAD for the hardware (#125 §4), never a measurement of it.

Standard library only.
"""
import cmath
import hashlib
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gbi_unpack  # noqa: E402
import v125const  # noqa: E402

AGB_HZ = 2 ** 24
BYTE_HZ = AGB_HZ // 8                  # one stream byte = 8 AGB cycles
DEC_HZ = 32768.0                       # the Disc's decimated rate: one output per 64 stream bytes (the reading)
AI_NOMINAL = 32000.0
AI_MEASURED = 32028.483                # GBP-HW-325, RUN 38: the GameCube's AI in its 32 kHz mode

DISC = {"lut": 0x801B39A0, "window": 0x801B3DA0, "resampler": 0x801B41A0, "steps": 0x801B3680,
        "classes": 0x801B398C, "gain": 0x801B368C, "edgepos": 0x801B388C}
DISC_R13_MASKS = -0x7840
DISC_R2_CONSTS = {"zero": -0x7920, "clip_hi": -0x791C, "clip_lo": -0x7918, "norm": -0x7908, "mono": -0x7904}
FREQS = (1000, 2000, 5256, 8000, 10000, 12000, 14000, 16000, 16384, 20000, 24000, 32768, 65536, 131072)

GBI_LOAD = v125const.LOAD
GBI_PRESETS = {"gbi": (0x800956D8, 0x800956E8), "gbihf": (0x80082F10, 0x80082F20), "gbisr": (0x8008B20C, 0x8008B21C)}
GBI_DEFAULT_R13 = {"gbi": 0x550, "gbihf": 0xB4, "gbisr": 0x568}
GBI_FILTER_FLAG = {"gbi": 0x800B0AD9, "gbihf": 0x80099119, "gbisr": 0x800A9421}   # the byte the hand-off tests
DFORM = v125const.DFORM
# LIBAESND's mixer microcode: `gcdsptool -c libaesnd/dspcode/dspmixer.s` of LIBOGC2 ca03fb7, in
# ghcr.io/extremscorner/libogc2:20260805 (the same bytes as that image's libaesnd.a). Found here by its hash alone.
AESND_MIXER_SHA256 = "aad1814397f8a2f18458b2edbb29360fb7436030f2ca6fe283226a96876dbb3b"
AESND_MIXER_LEN = 1088


def popcount(b):
    return bin(b).count("1")


def centred_popcount_s16():
    return b"".join(struct.pack(">h", popcount(b) - 4) for b in range(256))


def centred_popcount_f32(scale=8192.0):
    return b"".join(struct.pack(">f", (popcount(b) - 4) * scale) for b in range(256))


# ---------------------------------------------------------------------------------------------------------------------
# responses (pure functions, tested on constructions)

def fir_response(coefs, f, fs):
    """|sum c_k e^{-j 2 pi f k / fs}| / |sum c_k|: a FIR's gain at f, normalised to DC."""
    s = sum(c * cmath.exp(-2j * math.pi * f * k / fs) for k, c in enumerate(coefs))
    return abs(s) / abs(sum(coefs))


def boxcar8(f):
    """the gain of summing 8 consecutive AGB cycles (one byte's popcount), normalised to DC."""
    if f == 0:
        return 1.0
    x = math.pi * f / AGB_HZ
    return abs(math.sin(8 * x) / (8 * math.sin(x)))


def decimator_response(window, f):
    """the Disc's per-byte popcount times its window, at f (Hz), DC-normalised."""
    return fir_response(window, f, BYTE_HZ) * boxcar8(f)


def resampler_response(taps, f, fs=DEC_HZ, q=32768.0):
    """RMS over the phases of each phase's 4-tap gain at f: the phase-averaged power response."""
    n = len(taps) // 4
    p2 = [abs(sum(taps[4 * p + k] / q * cmath.exp(-2j * math.pi * f * k / fs) for k in range(4))) ** 2
          for p in range(n)]
    return math.sqrt(sum(p2) / n)


def biquad_response(b0, b1, b2, a1, a2, f, fs=float(BYTE_HZ)):
    z = cmath.exp(-2j * math.pi * f / fs)
    return abs((b0 + b1 * z + b2 * z * z) / (1 + a1 * z + a2 * z * z))


def minus3db(h, lo=100.0, hi=60000.0):
    """a frequency (Hz) in (lo, hi) where a response h falls through 1/sqrt 2, by bisection: h(lo) must be above
    -3 dB and h(hi) below, or ValueError. With one crossing in the interval it is THE -3 dB point."""
    target = 2 ** -0.5
    if not h(lo) > target > h(hi):
        raise ValueError("-3 dB is not bracketed by %g and %g Hz" % (lo, hi))
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if h(m) > target else (lo, m)
    return lo


def peak(h, lo=0.0, hi=16000.0):
    """(|H|, Hz) at the response's maximum over [lo, hi]: a 1 Hz scan, then a golden-section refinement to 0.01 Hz,
    both on UNROUNDED values (#125's review: rounding before the max let ties pick the plateau's top edge)."""
    f0 = max((h(float(f)), float(f)) for f in range(int(lo), int(hi) + 1))[1]
    a, b = max(lo, f0 - 1.0), min(hi, f0 + 1.0)
    g = (math.sqrt(5) - 1) / 2
    while b - a > 0.01:
        c, d = b - g * (b - a), a + g * (b - a)
        if h(c) >= h(d):
            b = d
        else:
            a = c
    return max((h(x), x) for x in (a, (a + b) / 2, b))               # a maximum on the boundary (DC) is an endpoint


def first_rising_edge_table():
    """byte -> the bit position (1..7, MSB first in time) of its first 0 -> 1 transition, 0 where it has none."""
    out = []
    for b in range(256):
        bits = [(b >> (7 - t)) & 1 for t in range(8)]
        out.append(next((t for t in range(1, 8) if bits[t - 1] == 0 and bits[t] == 1), 0))
    return out


def step_rates(steps):
    """16.16 input-per-output steps -> (ratio, outputs per second from a DEC_HZ input, % vs 32 000, % vs measured)."""
    out = []
    for s in steps:
        r = s / 65536.0
        o = DEC_HZ / r
        out.append({"step": "0x%X" % s, "ratio": round(r, 6), "outputs_per_s": round(o, 1),
                    "vs_32000_pct": round(100 * (o / AI_NOMINAL - 1), 3),
                    "vs_measured_pct": round(100 * (o / AI_MEASURED - 1), 3)})
    return out


def lut_linearity(lut):
    """(per-bit weights, centre, max deviation from linear-in-bits) of a 256-entry byte LUT."""
    w = [lut[1 << i] - lut[0] for i in range(8)]
    dev = max(abs(lut[b] - lut[0] - sum(w[i] for i in range(8) if b >> i & 1)) for b in range(256))
    return w, lut[0], dev


# ---------------------------------------------------------------------------------------------------------------------
# reading the binaries

def region_reader(regions):
    def rd(a, n):
        for base, buf, _c in regions:
            if base <= a and a + n <= base + len(buf):
                return buf[a - base:a - base + n]
        raise KeyError("0x%08X not mapped" % a)
    return rd


def sda_base(regions, reg):
    """the first lis reg,hi ; ori|addi reg,reg,lo pair in the code: the SDA base the start-up code loads."""
    for base, buf, is_code in regions:
        if not is_code:
            continue
        ws = struct.unpack_from(">%dI" % (len(buf) // 4), buf)
        for i in range(len(ws) - 1):
            w, w2 = ws[i], ws[i + 1]
            if w >> 26 == 15 and (w >> 16) & 31 == 0 and (w >> 21) & 31 == reg:
                if w2 >> 26 == 24 and (w2 >> 21) & 31 == reg and (w2 >> 16) & 31 == reg:
                    return ((w & 0xFFFF) << 16) | (w2 & 0xFFFF)
                if w2 >> 26 == 14 and (w2 >> 21) & 31 == reg and (w2 >> 16) & 31 == reg:
                    return (((w & 0xFFFF) << 16) + v125const.sext16(w2 & 0xFFFF)) & 0xFFFFFFFF
    return None


def built_addresses(regions, targets, lookahead=8):
    """{target: [lis address]} where the code builds a target from lis rD,hi within `lookahead` instructions:
    by addi rE,rD,lo or a load/store d(rD) (hi + lo), or in two steps, addi rE,rD,lo then a load/store d(rE)
    (hi + lo + d), which is how a field of a structure is reached. rA = 0 is a literal zero, so a lis of r0 is never a
    base, at either step. The second step's load must read the addi's destination, within `lookahead` instructions
    counted from the addi. Each lis is listed once per target."""
    hits = dict((t, []) for t in targets)
    sx = v125const.sext16
    for base, buf, is_code in regions:
        if not is_code:
            continue
        ws = struct.unpack_from(">%dI" % (len(buf) // 4), buf)
        for i, w in enumerate(ws):
            if w >> 26 != 15 or (w >> 16) & 31 != 0 or (w >> 21) & 31 == 0:
                continue
            rd, hi = (w >> 21) & 31, (w & 0xFFFF) << 16
            for j in range(i + 1, min(len(ws), i + 1 + lookahead)):
                w2 = ws[j]
                op2, ra2, rt2 = w2 >> 26, (w2 >> 16) & 31, (w2 >> 21) & 31
                if ra2 != rd or not (op2 == 14 or op2 in DFORM):
                    continue
                v = (hi + sx(w2 & 0xFFFF)) & 0xFFFFFFFF
                if v in hits and base + 4 * i not in hits[v]:
                    hits[v].append(base + 4 * i)
                if op2 == 14 and rt2 != 0:
                    for k in range(j + 1, min(len(ws), j + 1 + lookahead)):
                        w3 = ws[k]
                        if w3 >> 26 in DFORM and (w3 >> 16) & 31 == rt2:
                            v3 = (v + sx(w3 & 0xFFFF)) & 0xFFFFFFFF
                            if v3 in hits and base + 4 * i not in hits[v3]:
                                hits[v3].append(base + 4 * i)
    return hits


def disc_params(regions):
    rd = region_reader(regions)
    f32s = lambda a, n: list(struct.unpack(">%df" % n, rd(a, 4 * n)))
    lut = f32s(DISC["lut"], 256)
    window = f32s(DISC["window"], 256)
    taps = list(struct.unpack(">512h", rd(DISC["resampler"], 1024)))
    steps = list(struct.unpack(">3I", rd(DISC["steps"], 12)))
    classes = list(struct.unpack(">4i", rd(DISC["classes"], 16)))
    gain = f32s(DISC["gain"], 128)
    edgepos = list(struct.unpack(">256b", rd(DISC["edgepos"], 256)))
    r2, r13 = sda_base(regions, 2), sda_base(regions, 13)
    masks = list(rd(r13 + DISC_R13_MASKS, 8))
    consts = dict((k, struct.unpack(">f", rd(r2 + off, 4))[0]) for k, off in DISC_R2_CONSTS.items())
    w, centre, dev = lut_linearity(lut)
    row_sums = [sum(taps[4 * p:4 * p + 4]) for p in range(128)]
    chain = lambda f: decimator_response(window, f) * resampler_response(taps, f)
    return {
        "r2": "0x%08X" % r2, "r13": "0x%08X" % r13,
        "lut": {"per_bit": sorted(set(w)), "centre": centre, "nonlinearity": dev,
                "is_centred_popcount_times_7000": all(lut[b] == (popcount(b) - 4) * 7000.0 for b in range(256))},
        "window": {"taps": len(window), "sum": sum(window), "symmetric": all(window[k] == window[255 - k]
                                                                            for k in range(256)),
                   "negative_taps": sum(1 for c in window if c < 0), "peak_index": window.index(max(window))},
        "decimator": {"response": dict((str(f), round(decimator_response(window, f), 6)) for f in FREQS),
                      "minus3db_hz": round(minus3db(lambda f: decimator_response(window, f), 1000.0, 16000.0))},
        "resampler": {"phases": 128, "taps": 4, "row_sum_min": min(row_sums), "row_sum_max": max(row_sums),
                      "response": dict((str(f), round(resampler_response(taps, f), 6))
                                       for f in (5256, 8000, 12000, 16000))},
        "chain": {"response": dict((str(f), round(chain(f), 6)) for f in (1000, 2000, 5256, 8000, 10000, 12000, 16000)),
                  "minus3db_hz": round(minus3db(chain, 1000.0, 16000.0))},
        "steps": step_rates(steps),
        "classes_bytes": classes,
        "gain": {"square_law_127_max_dev": max(abs(gain[k] - (k / 127.0) ** 2) for k in range(128)),
                 "monotone": all(gain[k] < gain[k + 1] for k in range(127)),
                 "first": gain[0], "last": gain[127]},
        "edgepos": {"values": sorted(set(edgepos)),
                    "is_first_rising_edge_table": edgepos == first_rising_edge_table()},
        "masks_are_ff_shifted": masks == [0xFF >> p for p in range(8)],
        "constants": consts,
    }


def gbi_params(images):
    out = {}
    int_pat, flt_pat = centred_popcount_s16(), centred_popcount_f32()
    analog_ref = None
    for e, img in images.items():
        if img is None:
            out[e] = None
            continue
        regions = [(GBI_LOAD, img, True)]
        rd = region_reader(regions)
        int_at = [GBI_LOAD + i for i in find_all(img, int_pat)]
        flt_at = [GBI_LOAD + i for i in find_all(img, flt_pat)]
        pa, po = GBI_PRESETS[e]
        analog = list(struct.unpack(">4f", rd(pa, 16)))          # coefficients: used here, never stored or printed
        original = list(struct.unpack(">4f", rd(po, 16)))
        r13 = sda_base(regions, 13)
        default = list(struct.unpack(">5f", rd(r13 + GBI_DEFAULT_R13[e], 20)))
        flag = GBI_FILTER_FLAG[e]
        built = built_addresses(regions, int_at + flt_at + [pa, po, flag])
        aesnd = struct.pack(">d", struct.unpack(">f", struct.pack(">f", 54000000.0 / 1124.0))[0])
        rec = {"int_table_at": ["0x%08X" % a for a in int_at], "float_table_at": ["0x%08X" % a for a in flt_at],
               "built_by_code": dict(("0x%08X" % t, len(v)) for t, v in built.items() if t != flag),
               "filter_flag_at": "0x%08X" % flag, "filter_flag_built": len(built[flag]),
               "filter_flag_built_at": ["0x%08X" % a for a in built[flag]],
               "aesnd_mixer_at": ["0x%08X" % a for a in find_by_hash(img, AESND_MIXER_SHA256, AESND_MIXER_LEN)],
               "filter_flag_initial": rd(flag, 1)[0],
               "default_coefs_are_analog": default == [analog[0], analog[1], analog[0], analog[2], analog[3]],
               "aesnd_default_rate_doubles": len(find_all(img, aesnd))}
        for name, (b0, b1, a1, a2) in (("analog", analog), ("original", original)):
            h = lambda f, b0=b0, b1=b1, a1=a1, a2=a2: biquad_response(b0, b1, b0, a1, a2, f)
            rec[name + "_dc"] = round(h(0.0), 6)
            rec[name + "_response"] = dict((str(f), round(h(f), 4)) for f in (5256, 12000, 16384, 32768, 65536))
            rec[name + "_minus3db_hz"] = round(minus3db(h, 1000.0, 60000.0))
            pv, pf = peak(h)
            rec[name + "_peak"] = (round(pv, 4), int(round(pf)))              # (value, 0) = the maximum is at DC
        if analog_ref is None:
            analog_ref = (analog, original)
        rec["presets_equal_gbi"] = (analog, original) == analog_ref
        out[e] = rec
    return out


def find_by_hash(img, sha, length, align=32):
    """load addresses of every `align`-aligned window of `length` bytes whose sha256 is `sha`: a known blob found
    without holding its bytes."""
    return [GBI_LOAD + o for o in range(0, len(img) - length + 1, align)
            if hashlib.sha256(img[o:o + length]).hexdigest() == sha]


def find_all(buf, pat):
    out, i = [], buf.find(pat)
    while i >= 0:
        out.append(i)
        i = buf.find(pat, i + 1)
    return out


def analyse():
    res = {"disc": None, "gbi": None}
    d = v125const.disc_image()
    if d:
        res["disc"] = disc_params(d)
    imgs = {}
    for e in v125const.EDITIONS:
        p = os.path.join(v125const.ROOT, "input", "gbi", "apps", e, e + ".dol")
        imgs[e] = gbi_unpack.unpack(open(p, "rb").read())[0] if os.path.isfile(p) else None
    if any(imgs.values()):
        res["gbi"] = gbi_params(imgs)
    return res


def main(argv):
    r = analyse()
    d = r["disc"]
    if d is None:
        print("disc: absent")
    else:
        print("disc: r2 %s r13 %s" % (d["r2"], d["r13"]))
        print("  byte value: centred popcount x 7000 %s, per bit %s, nonlinearity %g"
              % (d["lut"]["is_centred_popcount_times_7000"], d["lut"]["per_bit"], d["lut"]["nonlinearity"]))
        print("  window: %d taps, sum %.9f, symmetric %s, %d negative, peak at %d"
              % (d["window"]["taps"], d["window"]["sum"], d["window"]["symmetric"], d["window"]["negative_taps"],
                 d["window"]["peak_index"]))
        print("  decimator -3 dB %d Hz; |H| %s" % (d["decimator"]["minus3db_hz"],
                                                  " ".join("%s:%.4f" % kv for kv in d["decimator"]["response"].items())))
        print("  resampler 128 x 4, phase sums %d..%d; |H| %s" % (
            d["resampler"]["row_sum_min"], d["resampler"]["row_sum_max"],
            " ".join("%s:%.3f" % kv for kv in d["resampler"]["response"].items())))
        print("  chain -3 dB %d Hz; |H| %s" % (d["chain"]["minus3db_hz"],
                                              " ".join("%s:%.3f" % kv for kv in d["chain"]["response"].items())))
        for s in d["steps"]:
            print("  step %(step)s ratio %(ratio).6f -> %(outputs_per_s).1f/s, %(vs_32000_pct)+.3f %% vs 32 000, "
                  "%(vs_measured_pct)+.3f %% vs 32 028.483" % s)
        print("  classes (bytes) %s; gain %g..%g monotone %s, max |g - (k/127)^2| %.3g; edgepos = first rising edge "
              "%s; masks 0xFF>>p %s" % (d["classes_bytes"], d["gain"]["first"], d["gain"]["last"], d["gain"]["monotone"],
                                        d["gain"]["square_law_127_max_dev"], d["edgepos"]["is_first_rising_edge_table"],
                                        d["masks_are_ff_shifted"]))
        print("  constants %s" % " ".join("%s=%r" % kv for kv in d["constants"].items()))
    for e, g in (r["gbi"] or {}).items():
        if g is None:
            print("%s: absent" % e)
            continue
        print("%s: int table %s float table %s; built by code %s; filter flag %s = %d (built at %s); default "
              "coefficients = analog %s; presets = gbi's %s; AESND rate doubles %d; AESND mixer microcode at %s" % (
                  e, g["int_table_at"], g["float_table_at"], g["built_by_code"], g["filter_flag_at"],
                  g["filter_flag_initial"], g["filter_flag_built_at"], g["default_coefs_are_analog"],
                  g["presets_equal_gbi"], g["aesnd_default_rate_doubles"], g["aesnd_mixer_at"]))
        for name in ("analog", "original"):
            print("  %-8s DC %.4f, -3 dB %d Hz, peak %.4f at %d Hz; |H| %s" % (
                name, g[name + "_dc"], g[name + "_minus3db_hz"], g[name + "_peak"][0], g[name + "_peak"][1],
                " ".join("%s:%.4f" % kv for kv in g[name + "_response"].items())))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(r, f, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
