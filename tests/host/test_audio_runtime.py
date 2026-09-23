"""tests/host/test_audio_runtime.py — Issue #81: the AUDIO decode as runtime code.

Four things are checked here, from the repository alone:

1. THE FIXTURES. RUN 33 and RUN 34's sidecars are versioned under
   captures/fixtures/ as lossless gzip. The .gz is pinned by hash, its content
   by the raw sidecar's hash (§V15), and re-compressing the content reproduces
   the .gz byte for byte, so the fixture is derivable from the raw and nothing
   else. When logs/ is present the raw itself is hashed too.

2. BIT-IDENTITY. src/audio/gbp_adec.c, fed through the replay backend
   src/audio/gbp_asrc.c, must produce EXACTLY the int16 samples that
   tools/v17decode.py writes — the code that produced #80's validated WAVs —
   on every window of both runs, the four press windows of each (the eight
   windows #80 decoded) and the two control windows as well. That comparison
   runs from the versioned fixtures and never needs captures/local. When #80's
   WAVs are on this machine they are compared too, frame for frame.

3. THE RESAMPLER. 4096 -> 32 000 Hz is 125/16; the ratio is checked as a count
   (after j inputs exactly ceil(125 j / 16) outputs), the C output as equal to
   an integer model of the same table, the table as equal to its generator,
   the passband as flat, and — the case the Issue singles out — the 1024 Hz
   window's FUNDAMENTAL as preserved. What that window's PEAK does is stated as
   a test as well, because it goes the other way from what one might expect.

4. STATIC PINS. No floating point, no allocation and no blocking call in the
   three runtime sources.
"""
import cmath
import gzip
import hashlib
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import awinparse  # noqa: E402
import hostcc  # noqa: E402
import gen_aresamp  # noqa: E402
import v11sweep  # noqa: E402
import v17decode  # noqa: E402

AUDIO = os.path.join(ROOT, "src", "audio")
FIXTURES = os.path.join(ROOT, "captures", "fixtures")
DECODED = os.path.join(ROOT, "captures", "local", "decoded")
README = os.path.join(ROOT, "captures", "README.md")

# label -> (fixture, fixture sha256, fixture size, raw sidecar in logs/, raw sha256, raw size)
RUNS = {
    "RUN33": ("hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz",
              "d6ca9c3b667767c612a72458e864b624d4da265d230c7151e961572a227bc4a6", 22338,
              "logs/run33/GBP-AUDIO-001_stream-0016-audio.bin",
              "cfe472d36ba6040ecbedf9adfc601b73b501d401f363ccc78c20cafa136252b8", 5243788),
    "RUN34": ("hw-gamecube-gbp-2026-09-23-stream-0016-run34-audio.bin.gz",
              "3578a8e727e439e4cec22e35f9831c06fc7777e672a9dafecf7eeb9533ef1e8a", 27037,
              "logs/run34/GBP-AUDIO-001_stream-0016-audio.bin",
              "4db12f2ea62fee633c131b6bd38d971e6b60b1d2f9dae775eeb3ef17e20c58b0", 5243788),
}

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_adec.h"
#include "gbp_asrc.h"
#include "gbp_aresamp.h"

static void put32(FILE *f, uint32_t v)
{
    fputc((int)(v & 0xFFu), f); fputc((int)((v >> 8) & 0xFFu), f);
    fputc((int)((v >> 16) & 0xFFu), f); fputc((int)((v >> 24) & 0xFFu), f);
}
static void put16(FILE *f, int16_t s)
{
    uint16_t v = (uint16_t)s;
    fputc((int)(v & 0xFFu), f); fputc((int)(v >> 8), f);
}
static uint8_t *slurp(const char *p, size_t *n)
{
    FILE *f = fopen(p, "rb"); long sz; uint8_t *b;
    if (!f) return NULL;
    fseek(f, 0, SEEK_END); sz = ftell(f); fseek(f, 0, SEEK_SET);
    b = (uint8_t *)malloc((size_t)sz ? (size_t)sz : 1u);
    if (fread(b, 1, (size_t)sz, f) != (size_t)sz) { fclose(f); free(b); return NULL; }
    fclose(f); *n = (size_t)sz; return b;
}

/* dec <sidecar> <out>: calibrate on window 0, decode every window through a
 * 16-sample ring, write per window (kind, keys, blocks, samples) and the samples. */
static int dec(const char *in, const char *outp)
{
    static struct gbp_asrc_replay r;
    static int16_t ring[16];
    struct gbp_adec d; struct gbp_asrc src; const uint8_t *blk; size_t n; uint32_t w;
    uint8_t *buf = slurp(in, &n); FILE *o; int rc;
    if (!buf) return 2;
    rc = gbp_asrc_replay_open(&r, buf, n);
    if (rc != 0) { fprintf(stderr, "open %d\n", rc); return 3; }
    gbp_adec_init(&d, ring, 16u);
    gbp_asrc_replay_select(&r, 0u);
    gbp_asrc_replay_source(&r, &src);
    while (src.next(src.ctx, &blk)) gbp_adec_calibrate(&d, blk);
    o = fopen(outp, "wb");
    put32(o, r.windows);
    for (w = 0; w < r.windows; w++) {
        int16_t s[4096]; uint32_t k = 0;
        gbp_asrc_replay_select(&r, w);
        gbp_asrc_replay_source(&r, &src);
        while (src.next(src.ctx, &blk)) {
            if (gbp_adec_push_block(&d, blk) != 0) return 4;
            while (k < 4096u && gbp_adec_pop(&d, &s[k])) k++;
        }
        put32(o, r.win[w].kind); put32(o, r.win[w].keys); put32(o, r.win[w].blocks); put32(o, k);
        { uint32_t i; for (i = 0; i < k; i++) put16(o, s[i]); }
    }
    put32(o, d.blocks_in); put32(o, d.lost); put32(o, d.overflow);
    fclose(o); free(buf);
    return 0;
}

/* rs <in.s16le> <out>: resample; write the per-input output counts, the final
 * accumulator, then the outputs. */
static int rs(const char *in, const char *outp)
{
    struct gbp_aresamp a; size_t n, i; uint8_t *buf = slurp(in, &n); FILE *o;
    int16_t *y; uint8_t *cnt; size_t ny = 0;
    if (!buf) return 2;
    y = (int16_t *)malloc((n / 2u) * GBP_ARESAMP_MAX_OUT * sizeof(int16_t) + 2u);
    cnt = (uint8_t *)malloc(n / 2u + 1u);
    gbp_aresamp_init(&a);
    for (i = 0; i < n / 2u; i++) {
        int16_t v = (int16_t)(uint16_t)(buf[2u * i] | (buf[2u * i + 1u] << 8));
        uint32_t k = gbp_aresamp_push(&a, v, &y[ny]);
        cnt[i] = (uint8_t)k; ny += k;
    }
    o = fopen(outp, "wb");
    put32(o, (uint32_t)(n / 2u)); fwrite(cnt, 1, n / 2u, o);
    put32(o, a.acc); put32(o, a.in_count); put32(o, a.out_count); put32(o, (uint32_t)ny);
    for (i = 0; i < ny; i++) put16(o, y[i]);
    fclose(o); free(buf); free(y); free(cnt);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 4 && strcmp(argv[1], "dec") == 0) return dec(argv[2], argv[3]);
    if (argc == 4 && strcmp(argv[1], "rs") == 0) return rs(argv[2], argv[3]);
    return 1;
}
'''

RUNTIME_SOURCES = ["gbp_adec.c", "gbp_asrc.c", "gbp_aresamp.c"]
LINKED = [os.path.join(AUDIO, f) for f in RUNTIME_SOURCES] + [
    os.path.join(ROOT, "src", "gbp", f) for f in ("gbp_awindump.c", "gbp_awin.c", "gbp_crc32.c")]


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def fixture_bytes(label):
    with open(os.path.join(FIXTURES, RUNS[label][0]), "rb") as f:
        return f.read()


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def s16(b, o, n):
    return list(struct.unpack_from("<%dh" % n, b, o))


def reference_int16(pcm):
    """#80's samples EXACTLY as written: v17decode.write_wav to a file, read back."""
    fd, p = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        v17decode.write_wav(p, pcm, 4096)
        with wave.open(p, "rb") as w:
            fr = w.readframes(w.getnframes())
        return s16(fr, 0, len(fr) // 2)
    finally:
        os.remove(p)


def wav_int16(path):
    with wave.open(path, "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 4096)
        fr = w.readframes(w.getnframes())
    return s16(fr, 0, len(fr) // 2)


def fundamental(xs, n0, n, samples_per_period):
    """Amplitude of the component at one frequency, over a WHOLE number of its periods."""
    X = sum(xs[n0 + k] * cmath.exp(-2j * math.pi * k / samples_per_period) for k in range(n))
    return 2.0 * abs(X) / n


def resample_model(xs):
    """The C resampler restated in Python integers, from the generator's table."""
    rows = gen_aresamp.table()
    hist, hpos, acc, out = [0] * 16, 0, 0, []
    for v in xs:
        hist[hpos] = v
        hpos = (hpos + 1) % 16
        while acc < 125:
            s = sum(rows[acc][m] * hist[(hpos + m) % 16] for m in range(16))
            q = (s + 16384) >> 15 if s >= 0 else -(((-s) + 16384) >> 15)
            out.append(max(-32767, min(32767, q)))
            acc += 16
        acc -= 125
    return out


class Harness(unittest.TestCase):
    """Builds the harness once, decompresses both fixtures once, decodes once."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="adec-")
        src = os.path.join(cls.tmp, "harness.c")
        with open(src, "w") as f:
            f.write(HARNESS)
        cls.bin = os.path.join(cls.tmp, "harness")
        cls.have_gcc, cls.built, cls.err = hostcc.compile_c(
            ["-std=gnu11", "-O1", "-Wall", "-Wextra", "-Wconversion", "-I", AUDIO,
             "-I", os.path.join(ROOT, "src", "gbp"), "-o", cls.bin, src] + LINKED)
        cls.raw, cls.dec = {}, {}
        for label in RUNS:
            p = os.path.join(cls.tmp, label + ".bin")
            cls.raw[label] = gzip.decompress(fixture_bytes(label))
            with open(p, "wb") as f:
                f.write(cls.raw[label])
            if cls.built:
                cls.dec[label] = cls._decode(p)

    @classmethod
    def _decode(cls, path):
        out = path + ".dec"
        r = subprocess.run([cls.bin, "dec", path, out], capture_output=True, text=True)
        assert r.returncode == 0, (r.returncode, r.stderr)
        with open(out, "rb") as f:
            b = f.read()
        nw, o, wins = u32(b, 0), 4, []
        for _ in range(nw):
            kind, keys, blocks, k = u32(b, o), u32(b, o + 4), u32(b, o + 8), u32(b, o + 12)
            wins.append({"kind": kind, "keys": keys, "blocks": blocks, "pcm": s16(b, o + 16, k)})
            o += 16 + 2 * k
        return {"windows": wins, "blocks_in": u32(b, o), "lost": u32(b, o + 4), "overflow": u32(b, o + 8)}

    def resample(self, xs):
        p = os.path.join(self.tmp, "rs-%d.s16" % len(xs))
        with open(p, "wb") as f:
            f.write(struct.pack("<%dh" % len(xs), *xs))
        r = subprocess.run([self.bin, "rs", p, p + ".out"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(p + ".out", "rb") as f:
            b = f.read()
        n = u32(b, 0)
        counts = list(b[4:4 + n])
        o = 4 + n
        acc, n_in, n_out, ny = u32(b, o), u32(b, o + 4), u32(b, o + 8), u32(b, o + 12)
        return {"counts": counts, "acc": acc, "in": n_in, "out": n_out, "y": s16(b, o + 16, ny)}

    def need_gcc(self):
        # ONLY a missing compiler skips (tests/host/hostcc.py, Issue #82).
        hostcc.require(self, self.have_gcc, self.built, self.err)


class TheFixturesAreTheRawSidecarsLosslessly(Harness):

    def test_each_fixture_is_pinned_by_hash_and_size(self):
        for label, (name, gz_sha, gz_size, _, raw_sha, raw_size) in RUNS.items():
            gz = fixture_bytes(label)
            self.assertEqual((len(gz), sha256(gz)), (gz_size, gz_sha), label)
            self.assertEqual((len(self.raw[label]), sha256(self.raw[label])), (raw_size, raw_sha), label)

    def test_recompressing_the_content_reproduces_the_fixture_byte_for_byte(self):
        """gzip -9 with mtime 0: the .gz is a function of the raw bytes and nothing else."""
        for label in RUNS:
            self.assertEqual(gzip.compress(self.raw[label], compresslevel=9, mtime=0),
                             fixture_bytes(label), label)

    def test_the_raw_drop_hashes_to_the_same_bytes_when_it_is_here(self):
        present = [l for l in RUNS if os.path.exists(os.path.join(ROOT, RUNS[l][3]))]
        if not present:
            self.skipTest("the raw sidecars are not in this checkout (logs/ is ignored)")
        for label in present:
            with open(os.path.join(ROOT, RUNS[label][3]), "rb") as f:
                self.assertEqual(sha256(f.read()), RUNS[label][4], label)

    def test_the_readme_names_each_fixture_with_its_raw_provenance(self):
        with open(README, encoding="utf-8") as f:
            t = f.read()
        for label, (name, gz_sha, _, raw_path, raw_sha, _) in RUNS.items():
            row = [l for l in t.splitlines() if l.startswith("| `%s`" % name)]
            self.assertEqual(len(row), 1, name)
            for s in (raw_path, raw_sha[:8], raw_sha[-5:], gz_sha[:8], "5 243 788 B", "mtime=0"):
                self.assertIn(s, row[0], (name, s))

    def test_the_host_parser_sees_five_windows_of_256_blocks_in_each(self):
        for label in RUNS:
            h, anc, off = awinparse.parse(self.raw[label])
            self.assertEqual([a["kind"] for a in anc], [0, 1, 1, 1, 1], label)
            self.assertEqual({a["blocks"] for a in anc}, {256}, label)


class TheRuntimeDecoderIsBitIdenticalToIssue80(Harness):

    def reference(self, label):
        _, _, anc, wins = awinparse.load(os.path.join(self.tmp, label + ".bin"))
        rest = v17decode.resting_level(wins[0])
        return anc, [reference_int16(v17decode.decode(w, rest)) for w in wins]

    def test_the_replay_backend_serves_the_windows_the_host_parser_reads(self):
        self.need_gcc()
        for label in RUNS:
            anc, _ = self.reference(label)
            got = [(w["kind"], w["keys"], w["blocks"]) for w in self.dec[label]["windows"]]
            self.assertEqual(got, [(a["kind"], a["keys"], a["blocks"]) for a in anc], label)

    def test_every_window_of_both_runs_is_bit_identical(self):
        """The eight press windows #80 decoded, and the two control windows besides:
        2 560 samples, compared as integers, none allowed to differ."""
        self.need_gcc()
        compared = 0
        for label in RUNS:
            _, ref = self.reference(label)
            got = [w["pcm"] for w in self.dec[label]["windows"]]
            self.assertEqual([len(g) for g in got], [256] * 5, label)
            for i, (g, r) in enumerate(zip(got, ref)):
                diff = [k for k in range(len(r)) if g[k] != r[k]]
                self.assertEqual(diff, [], "%s w%d: %d samples differ, first at %s"
                                 % (label, i, len(diff), diff[:1]))
                compared += len(r)
        self.assertEqual(compared, 2 * 5 * 256)

    def test_the_control_windows_decode_to_silence_on_average(self):
        """The rest IS the control window's mean, so its samples sum to (about) zero —
        a check that the calibration went where it should, not a new measurement."""
        self.need_gcc()
        for label in RUNS:
            c = self.dec[label]["windows"][0]["pcm"]
            self.assertLessEqual(abs(sum(c)) / float(len(c)), 1.0, label)

    def test_nothing_was_lost_or_dropped_and_every_block_was_counted(self):
        self.need_gcc()
        for label in RUNS:
            d = self.dec[label]
            self.assertEqual((d["blocks_in"], d["lost"], d["overflow"]), (5 * 256, 0, 0), label)

    def test_issue_80s_own_wavs_when_they_are_on_this_machine(self):
        self.need_gcc()
        present = [(l, i) for l in RUNS for i in range(1, 5)
                   if os.path.exists(os.path.join(DECODED, "%s_w%d_4096Hz.wav" % (l, i)))]
        if len(present) != 8:
            self.skipTest("the decoded WAVs of Issue #80 are not in this checkout (captures/local is ignored)")
        for label, i in present:
            want = wav_int16(os.path.join(DECODED, "%s_w%d_4096Hz.wav" % (label, i)))
            self.assertEqual(self.dec[label]["windows"][i]["pcm"], want, "%s w%d" % (label, i))


class TheResamplerIs125Over16Exactly(Harness):

    def test_the_table_is_what_the_generator_says(self):
        with open(os.path.join(AUDIO, "gbp_aresamp_coef.h"), encoding="utf-8") as f:
            self.assertEqual(f.read(), gen_aresamp.render())

    def test_every_phase_sums_to_one_and_phase_zero_is_the_identity(self):
        rows = gen_aresamp.table()
        self.assertEqual(len(rows), 125)
        self.assertEqual({sum(r) for r in rows}, {32768})
        self.assertEqual(rows[0], [0] * 7 + [32768] + [0] * 8)
        # the one tap that does not fit int16 -- the reason the table is int32_t
        self.assertGreater(max(v for r in rows for v in r), 32767)

    def test_after_j_inputs_exactly_ceil_125j_over_16_outputs_and_no_drift(self):
        """Output k is emitted by input floor(16 k / 125), so after j inputs the count is
        #{k : 16 k < 125 j} = ceil(125 j / 16), an integer identity with no remainder carried."""
        self.need_gcc()
        xs = [(i * 7919) % 20001 - 10000 for i in range(4096 + 13)]
        r = self.resample(xs)
        total = 0
        for j, c in enumerate(r["counts"], start=1):
            self.assertIn(c, (7, 8))
            total += c
            self.assertEqual(total, -((-125 * j) // 16), "after %d inputs" % j)
        self.assertEqual((r["in"], r["out"]), (4109, -((-125 * 4109) // 16)))
        # one second of input is exactly one second of output, and the phase is home
        r = self.resample(xs[:4096])
        self.assertEqual((r["out"], r["acc"]), (32000, 0))

    def test_the_c_output_equals_the_integer_model_of_the_same_table(self):
        self.need_gcc()
        xs = [int(20000 * math.sin(0.37 * i) + 9000 * math.sin(2.1 * i)) for i in range(700)]
        xs += [32767, -32767] * 20 + [0] * 40
        self.assertEqual(self.resample(xs)["y"], resample_model(xs))

    def test_the_passband_is_flat_to_a_hundredth_of_a_decibel_up_to_1024_hz(self):
        """A pure tone in, the same tone's amplitude out, over a whole number of periods
        of both rates. Gains are measured, not assumed: 0.9998 / 0.9996 / 1.0001 / 1.0007."""
        self.need_gcc()
        for f in (128, 256, 512, 1024):
            xs = [int(round(16000 * math.sin(2 * math.pi * f * n / 4096 + 0.3))) for n in range(4096)]
            y = self.resample(xs)["y"]
            a_in = fundamental(xs, 1024, 2048, 4096.0 / f)
            a_out = fundamental(y, 8000, 16000, 32000.0 / f)
            self.assertLess(abs(20 * math.log10(a_out / a_in)), 0.01, "%d Hz" % f)


class The1024HzWindow(Harness):
    """RUN 33 w4. §V17.6.1: four samples per period, four levels, not attenuated."""

    # the sliced region's first 128 samples = 32 periods; at 32 kHz the SAME span,
    # delayed by the resampler's 8-sample latency, is 1 000 samples = 32 periods
    IN0, IN_N = 104, 128
    OUT0, OUT_N = (104 + 8) * 125 // 16, 1000

    def window(self):
        self.need_gcc()
        x = self.dec["RUN33"]["windows"][4]["pcm"]
        y = self.resample(x)["y"]
        self.assertEqual(len(y), 2000)
        return x, y

    def test_the_source_is_a_pure_fundamental(self):
        """With four samples per period a series has three components: DC, 1024 Hz and
        the 2048 Hz Nyquist term. This window's Nyquist term is zero to 1/64 of an LSB,
        so what the 4096 Hz samples represent is ONE sine at 1024 Hz."""
        x, _ = self.window()
        s = x[self.IN0:self.IN0 + self.IN_N]
        nyq = sum(v * (-1) ** k for k, v in enumerate(s)) / float(len(s))
        self.assertLess(abs(nyq), 0.05)
        self.assertEqual(v11sweep.window_period([float(v) for v in s])["period"], 4)

    def test_the_resampler_preserves_its_fundamental(self):
        """Measured: 1.00065 (+0.006 dB). A resampler that attenuated this window
        would fail here; the bound is 0.1 dB."""
        x, y = self.window()
        a_in = fundamental(x, self.IN0, self.IN_N, 4.0)
        a_out = fundamental(y, self.OUT0, self.OUT_N, 31.25)
        self.assertLess(abs(20 * math.log10(a_out / a_in)), 0.1, (a_in, a_out))

    def test_its_peak_rises_and_that_is_correct(self):
        """SAID PLAINLY. The largest 4096 Hz sample is 24 690; the 32 kHz output peaks near
        30 870, 25 % HIGHER — because four samples per period miss the crest of the sine
        they sample, and a band-limited reconstruction puts the crest back. The output
        peak sits at the fundamental's amplitude, not at the largest sample. The largest
        sample of a four-per-period sine is cos(phase) of its amplitude, between 0.71 and
        1 (here 0.80), so a peak comparison can only ever read a GAIN at 1024 Hz — up to
        41 % — and neither a gain nor a loss is there: the fundamental is what to compare
        (the test above)."""
        x, y = self.window()
        a_in = fundamental(x, self.IN0, self.IN_N, 4.0)
        peak_in = max(abs(v) for v in x[self.IN0:self.IN0 + self.IN_N])
        peak_out = max(abs(v) for v in y[self.OUT0:self.OUT0 + self.OUT_N])
        self.assertGreater(peak_out, 1.2 * peak_in)
        self.assertLess(abs(peak_out - a_in) / a_in, 0.01)

    def test_issue_80s_48_khz_resampler_agrees_on_the_fundamental(self):
        """An independent construction (float, 32 taps, 375/32) reads the same amplitude."""
        x, y = self.window()
        _, _, _, wins = awinparse.load(os.path.join(self.tmp, "RUN33.bin"))
        rest = v17decode.resting_level(wins[0])
        z = v17decode.resample(v17decode.decode(wins[4], rest))
        # 48 kHz: 46.875 samples per period; that resampler is centred (no latency), so the
        # same 32 periods start at input 104 -> output 104 * 375 / 32
        a48 = fundamental(z, 104 * 375 // 32, 1500, 46.875) * v17decode.GAIN * 32767
        a32 = fundamental(y, self.OUT0, self.OUT_N, 31.25)
        self.assertLess(abs(20 * math.log10(a32 / a48)), 0.1, (a32, a48))


class TheRuntimeSourcesObeyTheDrainPathRules(unittest.TestCase):

    def sources(self):
        out = {}
        for f in RUNTIME_SOURCES + ["gbp_adec.h", "gbp_asrc.h", "gbp_aresamp.h", "gbp_aresamp_coef.h"]:
            with open(os.path.join(AUDIO, f), encoding="utf-8") as fh:
                t = fh.read()
            out[f] = re.sub(r"/\*.*?\*/", "", t, flags=re.S)   # code only, comments removed
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
        """Every datum is a fixed-width type. Plain `int` appears only as a status code:
        a return type, the source interface's return, and the one variable holding the
        parser's code."""
        for f, code in self.sources().items():
            self.assertIsNone(re.search(r"\b(unsigned|long|short|char)\b", code), f)
            self.assertEqual(set(re.findall(r"\bint\s+([a-z_]+)\s*[;=,\[]", code)) - {"rc"}, set(), f)
