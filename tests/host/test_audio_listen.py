"""
tests/host/test_audio_listen.py — the sequence the console plays for Issue #86
(src/audio/gbp_alisten), checked on the versioned RUN 33 fixture.

AN OUTPUT-PATH TEST, NOT A GAME BOY PLAYER AUDIO TEST. Nothing here says anything
about capture, drain or timing. What it says is narrower and complete: every
sample the console will be handed is the sample #80's validated decoder and
#81's frozen resampler produce, in the order and with the gaps the POC states.

HOW. A C harness runs gbp_alisten_build() on the fixture and writes the output.
The REFERENCE is built independently, in Python, from the code that produced
#80's WAVs: tools/v17decode.decode() on v11sweep.sliced() of each press window,
calibrated on the control window, written as #80 wrote it (reference_int16),
repeated round(4096 / 160) times, 2048 zeros after each tone, through the integer
model of the 125/16 resampler (from tools/gen_aresamp's table). Equality of the two
is bit-identity of the decode AND of the resampling at once.
"""
import gzip
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awinparse  # noqa: E402
import hostcc  # noqa: E402
import v11sweep  # noqa: E402
import v17decode  # noqa: E402

AUDIO = os.path.join(ROOT, "src", "audio")
GBP = os.path.join(ROOT, "src", "gbp")
FIXTURE = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz")
RUN33_SIDECAR_SHA = "cfe472d36ba6040ecbedf9adfc601b73b501d401f363ccc78c20cafa136252b8"
RUN33_TOTAL_CRC = 0xD3DBD9A6
SCHEDULE_HZ = (128.0, 512.0, 256.0, 1024.0)       # agb-sweep's A schedule, RUN 33's four presses
OUT_RATE = 32000

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include "gbp_alisten.h"
static int16_t out[2u * GBP_ALISTEN_MAX_FRAMES];
int main(int argc, char **argv)
{
    FILE *f = fopen(argv[1], "rb");
    static uint8_t buf[6u << 20];
    size_t n;
    struct gbp_alisten_info info;
    int rc;
    unsigned t;
    if (!f) return 2;
    n = fread(buf, 1, sizeof buf, f);
    fclose(f);
    rc = gbp_alisten_build(buf, n, out, GBP_ALISTEN_MAX_FRAMES, &info);
    printf("rc=%d crc=%08x windows=%u controls=%u tones=%u segs=%u in=%u frames=%u blocks=%u lost=%u overflow=%u\n",
           rc, info.total_crc32, info.windows, info.controls, info.tones, info.segs, info.in_samples,
           info.out_frames, info.dec_blocks, info.dec_lost, info.dec_overflow);
    for (t = 0; t < info.tones; t++)
        printf("tone %u keys=%u sliced=%u repeats=%u first=%u frames=%u gap_first=%u gap_frames=%u\n", t,
               info.keys[t], info.sliced[t], info.repeats[t], info.seg_first[2 * t], info.seg_frames[2 * t],
               info.seg_first[2 * t + 1], info.seg_frames[2 * t + 1]);
    printf("segment probes %d %d %d\n", gbp_alisten_segment(&info, 0), gbp_alisten_segment(&info, info.seg_first[1]),
           gbp_alisten_segment(&info, info.out_frames));
    f = fopen(argv[2], "wb");
    fwrite(out, sizeof out[0], 2u * info.out_frames, f);
    fclose(f);
    return rc ? 1 : 0;
}
'''
SOURCES = [os.path.join(AUDIO, f) for f in ("gbp_alisten.c", "gbp_adec.c", "gbp_asrc.c", "gbp_aresamp.c")] + [
    os.path.join(GBP, f) for f in ("gbp_awindump.c", "gbp_awin.c", "gbp_crc32.c")]


# The reference is #81's own: the same two helpers, IMPORTED so they cannot drift apart --
# reference_int16 (#80's samples exactly as written to its WAVs) and resample_model (the C
# resampler restated in Python integers from gen_aresamp's table).
from test_audio_runtime import reference_int16, resample_model  # noqa: E402


class TheListeningSequence(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="alisten-")
        with gzip.open(FIXTURE, "rb") as f:
            cls.sidecar = f.read()
        cls.bin = os.path.join(cls.tmp, "run33.bin")
        with open(cls.bin, "wb") as f:
            f.write(cls.sidecar)
        src = os.path.join(cls.tmp, "h.c")
        with open(src, "w") as f:
            f.write(HARNESS)
        exe = os.path.join(cls.tmp, "h")
        have, ok, err = hostcc.compile_c(["-std=gnu11", "-O2", "-Wall", "-Wextra", "-I", AUDIO, "-I", GBP,
                                          "-o", exe, src] + SOURCES)
        hostcc.require_build(have, ok, err, "the gbp_alisten harness")
        out = os.path.join(cls.tmp, "out.s16")
        r = subprocess.run([exe, cls.bin, out], capture_output=True, text=True)
        cls.rc, cls.stdout = r.returncode, r.stdout
        with open(out, "rb") as f:
            raw = f.read()
        cls.pcm = list(struct.unpack("<%dh" % (len(raw) // 2), raw))

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def head(self):
        return dict(kv.split("=") for kv in self.stdout.splitlines()[0].split())

    def tones(self):
        out = []
        for line in self.stdout.splitlines()[1:]:
            if line.startswith("tone "):
                out.append({k: int(v) for k, v in (kv.split("=") for kv in line.split()[2:])})
        return out

    def test_the_fixture_is_run_33s_sidecar(self):
        import hashlib
        self.assertEqual(hashlib.sha256(self.sidecar).hexdigest(), RUN33_SIDECAR_SHA)
        self.assertEqual(len(self.sidecar), 5243788)

    def test_it_builds_four_tones_from_run_33(self):
        h = self.head()
        self.assertEqual(self.rc, 0, self.stdout)
        self.assertEqual(int(h["crc"], 16), RUN33_TOTAL_CRC)
        self.assertEqual((h["windows"], h["controls"], h["tones"], h["segs"]), ("5", "1", "4", "8"))
        self.assertEqual((h["lost"], h["overflow"]), ("0", "0"))
        for t in self.tones():
            self.assertEqual((t["keys"], t["sliced"], t["repeats"]), (1, 160, 26))   # A, 256 - 96, round(25.6)

    def test_the_output_is_the_reference_bit_for_bit(self):
        _, _, anc, wins = awinparse.load(self.bin)
        rest = v17decode.resting_level(wins[0])
        seq = []
        for w in wins[1:]:
            pcm = reference_int16(v17decode.decode(v11sweep.sliced(w), rest))
            self.assertEqual(len(pcm), 160)
            seq += pcm * max(1, int(round(4096 / float(len(pcm)))))
            seq += [0] * 2048
        model = resample_model(seq)
        left, right = self.pcm[0::2], self.pcm[1::2]
        self.assertEqual(left, right, "the two channels differ")
        self.assertEqual(len(left), len(model))
        self.assertEqual(left, model, "the console's samples are not the reference's")
        self.assertEqual(int(self.head()["in"]), len(seq))
        self.assertEqual(len(left) * 16, len(seq) * 125)        # 4096 -> 32 000, exactly

    def test_the_segments_tile_the_output(self):
        tones, frames = self.tones(), int(self.head()["frames"])
        at = 0
        for t in tones:
            self.assertEqual(t["first"], at)
            at += t["frames"]
            self.assertEqual(t["gap_first"], at)
            at += t["gap_frames"]
        self.assertEqual(at, frames)
        probes = self.stdout.splitlines()[-1].split()[2:]
        self.assertEqual(probes, ["0", "1", "-1"])

    def test_each_tone_is_its_scheduled_pitch_and_each_gap_is_silent(self):
        left = self.pcm[0::2]
        for t, hz in zip(self.tones(), SCHEDULE_HZ):
            seg = left[t["first"] + 64: t["first"] + t["frames"] - 64]
            mean = sum(seg) / float(len(seg))
            ups = sum(1 for a, b in zip(seg, seg[1:]) if a <= mean < b)
            got = ups * OUT_RATE / float(len(seg))
            self.assertLess(abs(got - hz) / hz, 0.02, "tone at %.1f Hz, expected %.1f" % (got, hz))
            # the 16-tap resampler rings out over 16 inputs = 125 outputs; after that, exact silence
            gap = left[t["gap_first"] + 128: t["gap_first"] + t["gap_frames"]]
            self.assertEqual(max(abs(x) for x in gap), 0, "the gap after the %.0f Hz tone is not silent" % hz)

    def test_a_short_buffer_is_an_error_not_a_truncation(self):
        # the same harness, but through the C API's own contract: re-run with a small cap
        src = os.path.join(self.tmp, "small.c")
        with open(src, "w") as f:
            f.write(HARNESS.replace("rc = gbp_alisten_build(buf, n, out, GBP_ALISTEN_MAX_FRAMES, &info);",
                                    "rc = gbp_alisten_build(buf, n, out, 1000u, &info);"))
        exe = os.path.join(self.tmp, "small")
        have, ok, err = hostcc.compile_c(["-std=gnu11", "-O2", "-I", AUDIO, "-I", GBP, "-o", exe, src] + SOURCES)
        hostcc.require(self, have, ok, err, "the short-buffer harness")
        r = subprocess.run([exe, self.bin, os.path.join(self.tmp, "small.s16")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("rc=-4 ", r.stdout)

    def test_a_damaged_sidecar_is_refused(self):
        bad = bytearray(self.sidecar)
        bad[0x400] ^= 0xFF                                     # a byte inside the first AUDIO block
        p = os.path.join(self.tmp, "bad.bin")
        with open(p, "wb") as f:
            f.write(bytes(bad))
        exe = os.path.join(self.tmp, "h")
        r = subprocess.run([exe, p, os.path.join(self.tmp, "bad.s16")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("rc=-1 ", r.stdout)                      # the total CRC catches it


if __name__ == "__main__":
    unittest.main()
