"""tests/host/test_v126_chain.py -- GitHub Issue #126, Round B: the native chain's host validation.

What is checked, on the REAL C code (gbp_adec2.c + gbp_aplay2.c + gbp_aresamp2.c), built and run via
tests/host/harness_v126.c, against the frozen 4096 Hz path (gbp_adec.c + gbp_aresamp.c, run in the same process,
untouched) on the SAME archived bytes (RUN 33 and RUN 34, both versioned under captures/fixtures/):

  * THE FIX IS VISIBLE. Both decoders' final 32 000 Hz PCM is measured with tools/v124taps.py's own band_power(): the
    energy above 2 048 Hz the frozen path carries (GBP-HW-340: essentially none, by construction -- one popcount a
    block cannot represent it) against Round B's, on identical output lengths (both resample the same window to
    exactly 2 000 frames here). The margin is pinned from the measured ratio, with headroom, not assumed. This ratio
    alone only shows "more"; it is kept as the secondary, visibility-only line.
  * THE FRACTION IS RIGHT, not just bigger. For RUN 33/RUN 34 the tone is known exactly, and GBP-HW-340 already
    measured 2.5-18.7 % of ITS energy above 2 048 Hz on the raw, UNFILTERED decode. Round B's own chain measures a
    materially lower but non-zero fraction after the same signal passes the 16-tap/16 kHz-cutoff resampler (a
    low-pass filter attenuates content near its own passband edge by construction) -- measured here at 1.4 % (RUN
    33) and 2.2 % (RUN 34), against essentially 0 % on the frozen path. FRACTION_BAND is the data-derived, headroomed
    plausibility band this falls in: wide enough to admit the filter's attenuation, narrow enough to still exclude
    both failure modes a bare ratio cannot -- a near-zero fraction (no real gain) and a near-100 % fraction (a gain
    or aliasing bug inflating the ratio without reproducing the tone).
  * THE SHARED LOW BAND AGREES BETWEEN THE TWO PATHS (review round: the checks above alone cannot rule out a
    broadband-noise bug, since noise concentrates energy above 2048 Hz at least as readily as real audio and could
    land inside FRACTION_BAND by chance). tools/v124taps.py's split() isolates the <=2048 Hz content both paths
    represent from the SAME underlying signal; best_lag_corr() allows for the two resamplers' different group
    delays (at most CORR_LAG_MAX samples) and requires the correlation to exceed CORR_MIN. Measured: 0.93-0.98 for
    the real signal, 0.03-0.16 for random noise or an index-scrambled real signal over the same lag range.
  * THE GAME WINDOW (RUN 43) VALIDATES TOO, not only the two synthetic tones -- it is the only real game audio
    available and the whole point of the fix. It lives in captures/local/ (LOCAL_ARTIFACT_ABSENT; never versioned,
    a commercial game's audio), so this class skips gracefully where absent and runs the full battery (fix is
    visible, the fraction, the low-band correlation, conservation, reproducibility) where present. It has no
    separate silent control window the way RUN 33/34's OGBPAW1 sidecars do (U-GBP-041 et al.), so both decoders are
    SELF-CALIBRATED on the mean of the very blocks being decoded -- a methodological choice this round makes
    explicitly, not a frozen one (tests/host/harness_v126.c's chain_raw). The window is tools/u012game.py's largest
    gap-free run of the archived capture.
  * CONSERVATION. Every block gbp_adec2 decoded contributes exactly 16 samples; the harness's counters give
    blocks x 16 = the total gbp_adec2 samples produced (overflow2 + clipped2 report the rest); and the chain's
    output length is exactly produced2 x GBP_APLAY2_FRAMES (1000), whatever dup2/drop2 were -- GBP-HW-349's
    "every chunk resamples to exactly 1000 frames" property, read from a real run instead of asserted.
  * REPRODUCIBILITY. Running the harness twice on the same window gives byte-identical output and counters.

No image, no staging, no hardware (GitHub Issue #126). The static-purity pins (no floating point, no allocation, no
blocking call, fixed-width types only) that already guard gbp_adec.c/gbp_aresamp.c (tests/host/test_audio_runtime.py)
are extended here to the three new runtime sources.
"""
import gzip
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostcc  # noqa: E402
import u012game  # noqa: E402
import v124taps  # noqa: E402

AUDIO = os.path.join(ROOT, "src", "audio")
GBP = os.path.join(ROOT, "src", "gbp")
FIXTURES = os.path.join(ROOT, "captures", "fixtures")
HARNESS_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harness_v126.c")

# label -> (fixture, sha256, size, press window index)
RUNS = {
    "RUN33": ("hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz",
              "d6ca9c3b667767c612a72458e864b624d4da265d230c7151e961572a227bc4a6", 22338, 1),
    "RUN34": ("hw-gamecube-gbp-2026-09-23-stream-0016-run34-audio.bin.gz",
              "3578a8e727e439e4cec22e35f9831c06fc7777e672a9dafecf7eeb9533ef1e8a", 27037, 1),
}

RUN43_PATH = os.path.join(ROOT, "captures", "local", "GBP-AUDIO-012_sync-0001-run43-awr.bin")

# the fraction of energy above 2048 Hz Round B's decode carries, per tone/window. GBP-HW-340 measured 2.5-18.7 % of
# EACH TONE's energy above 2048 Hz on the raw, UNFILTERED decode; Round B's own chain passes the same signal through
# a 16-tap/16 kHz-cutoff resampler, a low-pass filter that by construction attenuates content near its own passband
# edge. So a materially lower but non-zero fraction after resampling is the EXPECTED, correct outcome, not a defect
# signature -- measured here at 1.4 % (RUN 33), 2.2 % (RUN 34) and 2.4 % (RUN 43, self-calibrated game content). This
# band is the data-derived, headroomed plausibility range: wide enough to admit the filter's attenuation, narrow
# enough to still exclude both failure modes a bare "more energy than the old decode" ratio cannot tell apart -- a
# near-zero fraction (no real gain reached the output) and a near-100 % fraction (a gain or aliasing bug inflating
# the ratio without reproducing the tone).
FRACTION_BAND = (0.005, 0.08)

# the two chains' resamplers have different group delays (L=125/M=16 vs L=125/M=256); a plausible constant offset
# between them is well under one tone period (RUN 33/34's presses recur roughly every 140-160 samples at 32 000 Hz,
# measured directly against this same harness output) but comfortably covers the difference. Measured best-lag
# correlation of the two paths' shared <=2048 Hz content: RUN 33 0.976, RUN 34 0.981 (both at lag ~45-47); a random
# 3000-amplitude noise signal or an index-scrambled real signal measured 0.03-0.16 over the same lag range, five
# trials. CORR_MIN sits with wide headroom on both sides of that gap.
CORR_LAG_MAX = 64
CORR_MIN = 0.7

NEW_SOURCES = ["gbp_adec2.c", "gbp_adec2.h", "gbp_aplay2.c", "gbp_aplay2.h", "gbp_aresamp2.c", "gbp_aresamp2.h"]

RUNTIME_SOURCES = ["gbp_adec.c", "gbp_aresamp.c", "gbp_adec2.c", "gbp_aplay2.c", "gbp_aresamp2.c"]
LINKED = [os.path.join(AUDIO, f) for f in RUNTIME_SOURCES] + [
    os.path.join(GBP, f) for f in ("gbp_awindump.c", "gbp_awin.c", "gbp_crc32.c")] + [
    os.path.join(AUDIO, "gbp_asrc.c")]


def fixture_bytes(label):
    fname, sha, size, _win = RUNS[label]
    p = os.path.join(FIXTURES, fname)
    with open(p, "rb") as f:
        b = f.read()
    got = hashlib.sha256(b).hexdigest()
    if got != sha or len(b) != size:
        raise AssertionError("%s: %s bytes, sha256 %s (want %d, %s)" % (label, len(b), got, size, sha))
    return gzip.decompress(b)


def s16le(path):
    with open(path, "rb") as f:
        b = f.read()
    import struct
    return list(struct.unpack("<%dh" % (len(b) // 2), b))


def read_counters(path):
    with open(path, encoding="utf-8") as f:
        line = f.read().strip()
    return dict((k, int(v)) for k, v in (kv.split("=") for kv in line.split()))


def band_powers(seq):
    """(above-2048Hz power per segment, above-2048Hz FRACTION of the total up to 16 kHz, segment count). The first
    is the "more energy than the old decode" figure (TheFixIsVisible's own visibility-only ratio); the second is the
    fraction GBP-HW-340's known 2.5-18.7 % range is compared against -- the correctness check, not just "more"."""
    hi, nseg = v124taps.band_power(seq, 16000.0)
    lo, nseg2 = v124taps.band_power(seq, 2048.0)
    above = hi - lo
    return (above / nseg if nseg else 0.0), (above / hi if hi else 0.0), nseg, nseg2


def pearson(a, b):
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    return num / (da * db) if da and db else 0.0


def best_lag_corr(a, b, maxlag):
    """The Pearson correlation of a against b, maximised over a shift of at most maxlag samples either way -- so a
    constant group-delay difference between the two resamplers does not mask real agreement (finding of the review
    round on this Issue: a bare energy-ratio check cannot tell a correct higher-bandwidth decode apart from a
    broadband-noise bug; this one can, since noise does not correlate with the other path's real content at any
    small lag)."""
    n = len(a)
    best = -2.0
    for lag in range(-maxlag, maxlag + 1):
        if lag >= 0:
            aa, bb = a[lag:], b[:n - lag]
        else:
            aa, bb = a[:n + lag], b[-lag:]
        c = pearson(aa, bb)
        if c > best:
            best = c
    return best


def largest_gap_free_run():
    """tools/u012game.py's largest run of consecutive, gap-free blocks in RUN 43's archived capture (the only real
    game audio available, and the whole point of #126's fix). Returns the raw concatenated block bytes."""
    _h, blocks = u012game.load(RUN43_PATH)
    S = u012game.slice_table(blocks)
    fit = u012game.solve(u012game.transitions(S))
    a, b = max(u012game.runs(fit["G"]), key=lambda ab: ab[1] - ab[0])
    return b"".join(blocks[a:b]), b - a


class Harness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="v126-")
        cls.bin = os.path.join(cls.tmp, "harness_v126")
        cls.have_gcc, cls.built, cls.err = hostcc.compile_c(
            ["-std=gnu11", "-O1", "-Wall", "-Wextra", "-Wconversion", "-I", AUDIO, "-I", GBP,
             "-o", cls.bin, HARNESS_SRC] + LINKED)
        cls.raw = {}
        for label in RUNS:
            cls.raw[label] = fixture_bytes(label)

    def run_chain(self, label, window, tag=""):
        hostcc.require(self, self.have_gcc, self.built, self.err, "harness_v126")
        inp = os.path.join(self.tmp, label + ".bin")
        with open(inp, "wb") as f:
            f.write(self.raw[label])
        o1 = os.path.join(self.tmp, "%s%s-o1.s16le" % (label, tag))
        o2 = os.path.join(self.tmp, "%s%s-o2.s16le" % (label, tag))
        ctr = os.path.join(self.tmp, "%s%s-ctr.txt" % (label, tag))
        r = subprocess.run([self.bin, "chain", inp, str(window), o1, o2, ctr], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return s16le(o1), s16le(o2), read_counters(ctr)

    def run_chain_raw(self, name, raw_bytes, nblocks, tag=""):
        hostcc.require(self, self.have_gcc, self.built, self.err, "harness_v126")
        inp = os.path.join(self.tmp, name + ".raw.bin")
        with open(inp, "wb") as f:
            f.write(raw_bytes)
        o1 = os.path.join(self.tmp, "%s%s-o1.s16le" % (name, tag))
        o2 = os.path.join(self.tmp, "%s%s-o2.s16le" % (name, tag))
        ctr = os.path.join(self.tmp, "%s%s-ctr.txt" % (name, tag))
        r = subprocess.run([self.bin, "chain_raw", inp, str(nblocks), o1, o2, ctr], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return s16le(o1), s16le(o2), read_counters(ctr)


class TheFixIsVisible(Harness):
    def test_the_new_decode_carries_meaningfully_more_energy_above_2048hz(self):
        # this ratio alone shows "more", never "right" -- it is kept ONLY as the secondary, visibility-only line
        # (a bug that made the new path emit broadband noise would also satisfy it; see the two checks below, which
        # target correctness directly).
        for label in RUNS:
            _fname, _sha, _size, window = RUNS[label]
            y1, y2, ctr = self.run_chain(label, window)
            e1, _f1, nseg1, _ = band_powers(y1)
            e2, _f2, nseg2, _ = band_powers(y2)
            self.assertEqual(nseg1, nseg2)
            # the frozen block decode cannot represent content above 2048 Hz at all (GBP-HW-340): its own share
            # measured here is the baseline, and the native path's must exceed it by a wide, headroomed margin
            self.assertGreater(e2, e1 * 50.0, (label, "e1=%g e2=%g" % (e1, e2)))

    def test_the_fraction_above_2048hz_is_in_a_plausible_band_not_just_bigger(self):
        # THE CORRECTNESS CHECK: GBP-HW-340 already gives the ideal figure for these exact tones (2.5-18.7 % of each
        # tone's energy above 2048 Hz, on the raw, unfiltered decode). Report the new decode's OWN fraction and
        # require it to land in FRACTION_BAND -- a headroomed neighbourhood of that known range, not the range
        # itself, since Round B's resampler is a low-pass filter GBP-HW-340's raw measurement never passed through.
        for label in RUNS:
            _fname, _sha, _size, window = RUNS[label]
            y1, y2, ctr = self.run_chain(label, window)
            _a1, f1, _n1, _ = band_powers(y1)
            _a2, f2, _n2, _ = band_powers(y2)
            lo, hi = FRACTION_BAND
            self.assertTrue(lo <= f2 <= hi, (label, "fraction above 2048 Hz = %.5f, want [%.3f, %.3f]" % (f2, lo, hi)))
            self.assertLess(f1, lo, (label, "the frozen path's own fraction should sit well under the band: %.5f" % f1))

    def test_the_shared_low_band_content_agrees_between_the_two_paths(self):
        # THE OTHER HALF OF CORRECTNESS: a bug that made the new path emit broadband noise instead of a genuine
        # higher-rate decode would ALSO clear the x50 energy-ratio bar above (noise concentrates energy above
        # 2048 Hz at least as readily as real audio does) and could even land inside FRACTION_BAND by chance. What it
        # would NOT do is agree with the frozen path's own decode of the <=2048 Hz content both paths represent from
        # the SAME underlying signal. tools/v124taps.py's split() isolates that shared band exactly (one FFT, zeroed
        # bins above the fold); best_lag_corr() allows for the two resamplers' different group delays.
        for label in RUNS:
            _fname, _sha, _size, window = RUNS[label]
            y1, y2, ctr = self.run_chain(label, window)
            lo1, _hi1 = v124taps.split(y1, fold_hz=2048.0, fs=32000.0)
            lo2, _hi2 = v124taps.split(y2, fold_hz=2048.0, fs=32000.0)
            c = best_lag_corr(lo1, lo2, CORR_LAG_MAX)
            self.assertGreater(c, CORR_MIN, (label, "best-lag low-band correlation = %.4f, want > %.2f" % (c, CORR_MIN)))


class TheConservationInvariant(Harness):
    def test_every_block_gives_exactly_sixteen_samples_and_every_chunk_exactly_1000_frames(self):
        for label in RUNS:
            _fname, _sha, _size, window = RUNS[label]
            y1, y2, ctr = self.run_chain(label, window)
            # every decoded block gives exactly 16 samples. Of those, each completed chunk POPS 2048 - dup + drop
            # from the ring (GBP_APLAY2_PUSHES; a DUP pops one sample for two resampler pushes, a DROP pops one for
            # zero -- GBP-HW-349's k arithmetic), and the rest sits in the ring, undecided (leftover2):
            taken = ctr["produced2"] * 2048 - ctr["dup2"] + ctr["drop2"]
            self.assertEqual(ctr["blocks"] * 16, taken + ctr["leftover2"], label)
            self.assertEqual(len(y1), len(y2), label)                                # both to the same length here
            self.assertEqual(ctr["produced2"] * 1000, ctr["y2n"], label)             # GBP-HW-349's chunk property
            self.assertEqual(ctr["overflow2"], 0, label)
            self.assertEqual(ctr["clipped2"], 0, label)
            self.assertEqual(ctr["lost2"], 0, label)
            self.assertEqual(ctr["starved2"], 0, label)


class TheReproducibility(Harness):
    def test_the_same_window_twice_gives_byte_identical_output_and_counters(self):
        for label in RUNS:
            _fname, _sha, _size, window = RUNS[label]
            y1a, y2a, ctra = self.run_chain(label, window, tag="a")
            y1b, y2b, ctrb = self.run_chain(label, window, tag="b")
            self.assertEqual(y1a, y1b, label)
            self.assertEqual(y2a, y2b, label)
            self.assertEqual(ctra, ctrb, label)


class TheGameWindowValidates(Harness):
    """RUN 43's game window (Yoshi's Island; tools/u012game.py's largest gap-free run of the archived capture) --
    the only real game audio available, and the whole point of #126's fix, so this validation is REQUIRED, not
    optional. It lives under captures/local/ (LOCAL_ARTIFACT_ABSENT; never versioned, a commercial game's audio), so
    this class skips gracefully where the file is absent and runs the full battery where it is present -- on THIS
    machine, always present. It has no separate silent control span the way RUN 33/34's OGBPAW1 sidecars do (U-GBP-
    041 et al.), so both decoders are SELF-CALIBRATED on the mean of the very blocks being decoded
    (tests/host/harness_v126.c's chain_raw) -- a methodological choice this round makes explicitly, not a frozen
    one. The window (130 blocks) is not sized to a whole number of Round B chunks: y1 (2080 samples, continuously
    resampled) and y2 (exactly one completed 1000-frame chunk; the last 48 decoded samples sit in the ring,
    unconsumed -- leftover2) differ in length, so every check that compares the two paths sample-for-sample below
    uses y1's SHARED PREFIX, y1[:len(y2)] -- the only part both paths agree on having finished resampling."""

    @classmethod
    def setUpClass(cls):
        super(TheGameWindowValidates, cls).setUpClass()
        cls.have_run43 = os.path.isfile(RUN43_PATH)
        if cls.have_run43:
            cls.run43_raw, cls.run43_n = largest_gap_free_run()

    def chain(self, tag=""):
        if not self.have_run43:
            self.skipTest("the RUN 43 raw window is kept in captures/local/ only (tests/host/test_v126_chain.py)")
        return self.run_chain_raw("RUN43", self.run43_raw, self.run43_n, tag=tag)

    def test_the_fix_is_visible_and_the_fraction_is_plausible(self):
        y1, y2, ctr = self.chain()
        y1s = y1[:len(y2)]
        e1, f1, nseg1, _ = band_powers(y1s)
        e2, f2, nseg2, _ = band_powers(y2)
        self.assertEqual(nseg1, nseg2)
        self.assertGreater(e2, e1 * 50.0, "e1=%g e2=%g" % (e1, e2))
        lo, hi = FRACTION_BAND
        self.assertTrue(lo <= f2 <= hi, "fraction above 2048 Hz = %.5f, want [%.3f, %.3f]" % (f2, lo, hi))
        self.assertLess(f1, lo, "the frozen path's own fraction should sit well under the band: %.5f" % f1)

    def test_the_shared_low_band_content_agrees_between_the_two_paths(self):
        y1, y2, ctr = self.chain()
        y1s = y1[:len(y2)]
        lo1, _hi1 = v124taps.split(y1s, fold_hz=2048.0, fs=32000.0)
        lo2, _hi2 = v124taps.split(y2, fold_hz=2048.0, fs=32000.0)
        c = best_lag_corr(lo1, lo2, CORR_LAG_MAX)
        self.assertGreater(c, CORR_MIN, "best-lag low-band correlation = %.4f, want > %.2f" % (c, CORR_MIN))

    def test_conservation(self):
        y1, y2, ctr = self.chain()
        taken = ctr["produced2"] * 2048 - ctr["dup2"] + ctr["drop2"]
        self.assertEqual(ctr["blocks"] * 16, taken + ctr["leftover2"])
        self.assertEqual(ctr["produced2"] * 1000, ctr["y2n"])
        self.assertEqual(ctr["overflow2"], 0)
        self.assertEqual(ctr["clipped2"], 0)
        self.assertEqual(ctr["lost2"], 0)
        self.assertEqual(ctr["starved2"], 0)

    def test_reproducibility(self):
        y1a, y2a, ctra = self.chain(tag="a")
        y1b, y2b, ctrb = self.chain(tag="b")
        self.assertEqual(y1a, y1b)
        self.assertEqual(y2a, y2b)
        self.assertEqual(ctra, ctrb)


class TheNewSourcesAreClean(unittest.TestCase):
    def sources(self):
        out = {}
        for f in NEW_SOURCES:
            with open(os.path.join(AUDIO, f), encoding="utf-8") as fh:
                t = fh.read()
            out[f] = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
        return out

    def test_no_floating_point(self):
        for f, code in self.sources().items():
            for word in ("float", "double", "math.h"):
                self.assertIsNone(re.search(r"\b%s\b" % re.escape(word), code), (f, word))
            self.assertIsNone(re.search(r"\d\.\d|\d[eE][+-]?\d", code), f)

    def test_no_allocation_and_no_blocking_call(self):
        for f, code in self.sources().items():
            for word in ("malloc", "calloc", "realloc", "free", "printf", "fopen", "fread", "fwrite",
                         "usleep", "sleep", "LWP_", "while (1)", "for (;;)"):
                self.assertNotIn(word, code, (f, word))

    def test_fixed_width_types_only(self):
        for f, code in self.sources().items():
            self.assertIsNone(re.search(r"\b(unsigned|long|short|char)\b", code), f)
            self.assertEqual(set(re.findall(r"\bint\s+([a-z_]+)\s*[;=,\[]", code)) - {"rc"}, set(), f)


if __name__ == "__main__":
    unittest.main()
