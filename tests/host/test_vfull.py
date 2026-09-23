"""
tests/host/test_vfull.py — OGBPFULL1 and the GBP-VIDEO-008 analysis, driven
through the REAL C writer (src/gbp/gbp_vfull.c + gbp_vfulldump.c compiled on
the host) with frames rendered by the oracle, then mutated as the negative
controls §V6.5 and Issue #7 require: one pixel, a row shift, a column shift,
an axis swap, a 4x4 tile permutation, a block displacement, a texture defect,
generation mixing, incomplete and store-full paths, bytes 0/2 and bit 15 as
observations only, and the Python / host-gbp_vpix.c / oracle agreement.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import hostcc  # noqa: E402
import icoord  # noqa: E402
import vfull  # noqa: E402

SRC = os.path.join(ROOT, "src", "gbp")

GENERATOR = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_vfull.h"
#include "gbp_vfulldump.h"
#include "gbp_vpix.h"
static uint8_t raw_store[GBP_VFULL_RAW_STORE];
static uint16_t tex_store[GBP_VFULL_TEX_STORE];
static uint8_t frame[GBP_VFULL_RAW_BYTES];
static uint16_t tex[GBP_VFULL_TEX_TEXELS];
static uint8_t chunk[GBP_VFULLDUMP_CHUNK];
static int sink(void *ctx, const uint8_t *d, uint32_t n) { return fwrite(d, 1, n, (FILE *)ctx) != n; }
/* argv: out origin nsamples [frames on stdin: each 153600 raw bytes] ; mode per sample from argv[3+i]:
   C complete, I incomplete (39 blocks), G refused by generation after copy, T texture mutated after copy */
int main(int argc, char **argv)
{
    struct gbp_vfull f; struct gbp_vfulldump_info info; FILE *out; uint64_t w = 0; long n;
    unsigned i, ns, origin, b;
    if (argc < 4) return 2;
    origin = (unsigned)strtoul(argv[2], 0, 0); ns = (unsigned)strtoul(argv[3], 0, 0);
    gbp_vfull_init(&f, raw_store, tex_store, GBP_VFULL_SPACING);
    gbp_vfull_set_origin(&f, origin);
    for (i = 0; i < ns; i++) {
        const char mode = argv[4 + i][0];
        unsigned fi = origin + 256u * i; int s;
        struct gbp_vpix_stats st;
        if (fread(frame, 1, sizeof frame, stdin) != sizeof frame) return 3;
        s = gbp_vfull_want(&f, fi);
        if (s != (int)i) return 4;
        if (gbp_vfull_open(&f, s, fi, 1000u + fi, (uint16_t)(i & 3u), (uint16_t)(i & 1u), 10u + i, 5000u + fi)) return 5;
        memset(&st, 0, sizeof st);
        for (b = 0; b < GBP_VFULL_BLOCKS; b++) {
            if (mode == 'I' && b == 39u) break;
            if (gbp_vpix_block(frame + b * GBP_VFULL_BLOCK_RAW, b, tex, GBP_VFULL_TEX_TEXELS, &st)) return 6;
            if (mode == 'T' && b == 17u) tex[b * GBP_VFULL_BLOCK_TEX + 100u] ^= 0x0001u;
            if (gbp_vfull_block(&f, s, b, frame + b * GBP_VFULL_BLOCK_RAW, tex + b * GBP_VFULL_BLOCK_TEX)) return 7;
        }
        (void)gbp_vfull_convert_done(&f, s, 6000u + fi);
        if (mode == 'G') gbp_vfull_refuse(&f, s, GBP_VFULL_R_GENERATION);
        (void)gbp_vfull_decision(&f, s, 7000u + fi, 100u + i, (int16_t)(i & 1u), 1u);
    }
    /* one frame beyond the grid capacity, to prove it is counted and not stored */
    (void)gbp_vfull_want(&f, origin + 256u * GBP_VFULL_K);
    memset(&info, 0, sizeof info);
    info.tb_hz = 40500000u;
    if (gbp_vfulldump_set_identity(&info, "GBP-VIDEO-004", "stream-0013", "gbp-video-stream-probe", "abc1234")) return 8;
    out = fopen(argv[1], "wb"); if (!out) return 9;
    n = gbp_vfulldump_stream(&info, &f, chunk, sizeof chunk, sink, out, &w);
    fclose(out);
    return n > 0 ? 0 : 10;
}
'''


class Producer:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="opengbp-full-")
        self.bin = os.path.join(self.tmp, "gen")
        src = os.path.join(self.tmp, "gen.c")
        with open(src, "w") as f:
            f.write(GENERATOR)
        self.have, self.ok, self.err = hostcc.compile_c(["-std=gnu11", "-O1", "-I", SRC, "-o", self.bin, src,
                                                         os.path.join(SRC, "gbp_vfull.c"), os.path.join(SRC, "gbp_vfulldump.c"),
                                                         os.path.join(SRC, "gbp_vpix.c"), os.path.join(SRC, "gbp_crc32.c")])

    def write(self, path, frames, modes, origin=356):
        r = subprocess.run([self.bin, path, str(origin), str(len(frames))] + list(modes),
                           input=b"".join(frames), capture_output=True)
        assert r.returncode == 0, "generator rc=%d %r" % (r.returncode, r.stderr[:200])
        return path


PROD = Producer()
_RAW = {}


def raw_frame(fid, status=0x18, filler=0):
    key = (fid, status, filler)
    if key not in _RAW:
        _RAW[key] = icoord.render_frame_raw(fid, True, filler, status)
    return _RAW[key]


def frames_for(origin, n, status=0x18):
    """frame_index = origin + 256*i carries frame_id = frame_index - 283 (as run 11: 356 -> 73)."""
    return [raw_frame(origin + 256 * i - 283, status) for i in range(n)]


def mutate(raw, fn):
    b = bytearray(raw)
    fn(b)
    return bytes(b)


def set_word(b, x, y, word):
    o = (y // 4) * 0xF00 + (y % 4) * 960 + x * 4
    b[o + 1], b[o + 3] = (word >> 8) & 0xFF, word & 0xFF


def get_word(b, x, y):
    o = (y // 4) * 0xF00 + (y % 4) * 960 + x * 4
    return (b[o + 1] << 8) | b[o + 3]


class TheContainer(unittest.TestCase):
    def setUp(self):
        hostcc.require(self, PROD.have, PROD.ok, PROD.err)
        self.tmp = tempfile.mkdtemp(prefix="opengbp-full-t-")

    def path(self, name="full.bin"):
        return os.path.join(self.tmp, name)

    def test_the_c_writer_and_the_python_reader_agree_and_k_is_eight(self):
        p = PROD.write(self.path(), frames_for(356, 8), "C" * 8)
        info = vfull.load(p)
        self.assertEqual((info["records_n"], info["k_cap"], info["spacing"], info["origin"]), (8, 8, 256, 356))
        self.assertEqual((info["wanted"], info["opened"], info["completed"], info["refused"], info["skipped_capacity"]), (8, 8, 8, 0, 1))
        self.assertEqual(info["flags"] & vfull.FLAG_ORIGIN_SET, vfull.FLAG_ORIGIN_SET)
        self.assertEqual(info["flags"] & vfull.FLAG_CAPACITY_SKIPPED, vfull.FLAG_CAPACITY_SKIPPED)
        self.assertEqual(os.path.getsize(p), 0x100 + 8 * 230528 + 12)
        for i, r in enumerate(info["records"]):
            self.assertEqual((r["sample_index"], r["frame_index"], r["seq"], r["state"]), (i, 356 + 256 * i, 1356 + 256 * i, 2))
            self.assertEqual(r["present"], (1 << 40) - 1)
            self.assertEqual(r["raw"], frames_for(356, 8)[i])
            self.assertEqual(r["t_decision"], 7000 + 356 + 256 * i)
            self.assertEqual(r["xfb_target"], i & 1)

    def test_every_byte_flip_is_refused(self):
        p = PROD.write(self.path(), frames_for(356, 1), "C")
        data = bytearray(open(p, "rb").read())
        for i in list(range(0, 0x100, 7)) + list(range(0x100, 0x100 + 0x80, 5)) + [0x100 + 0x80 + 1234, 0x100 + 0x80 + 153600 + 999, len(data) - 3]:
            data[i] ^= 0x01
            with self.assertRaises(ValueError, msg="offset %d" % i):
                vfull.parse(bytes(data))
            data[i] ^= 0x01
        vfull.parse(bytes(data))
        with self.assertRaises(ValueError):
            vfull.parse(bytes(data[:-1]))

    def test_incomplete_refused_and_generation_mixing_are_never_a_frame(self):
        p = PROD.write(self.path(), frames_for(356, 3), ["C", "I", "G"])
        info = vfull.load(p)
        self.assertEqual([r["state"] for r in info["records"]], [2, 3, 3])
        self.assertEqual([r["reason"] for r in info["records"]], [0, 3, 1])
        self.assertEqual(info["records"][1]["blocks_raw"], 39)
        a = vfull.analyse(info)
        self.assertEqual([s["verdict"] for s in a["samples"]], ["PASS", "INCONCLUSIVE", "INCONCLUSIVE"])
        self.assertEqual(a["verdict"], "INCONCLUSIVE")     # 3 of K=8


class TheAnalysis(unittest.TestCase):
    """One sample at a time (origin 356, frame_id 73), the way a run would be judged."""

    def setUp(self):
        hostcc.require(self, PROD.have, PROD.ok, PROD.err)
        self.tmp = tempfile.mkdtemp(prefix="opengbp-full-a-")

    def one(self, raw, mode="C", name="s.bin"):
        p = PROD.write(os.path.join(self.tmp, name), [raw], [mode])
        return vfull.analyse_sample(vfull.load(p)["records"][0])

    def test_the_exact_frame_passes_and_the_three_conversions_agree(self):
        s = self.one(raw_frame(73))
        self.assertEqual(s["verdict"], "PASS", s)
        self.assertEqual((s["frame_id"], s["status"], s["colour15_mismatches"], s["displacement_class"]), (73, 0x18, 0, "NONE"))
        self.assertEqual((s["tex_vs_python"], s["tex_vs_oracle"]), (0, 0))
        self.assertEqual(s["tex_vs_c"], 0, "host gbp_vpix.c must agree (gcc present)")
        self.assertEqual(s["bit15"], [(0, 0)])
        self.assertEqual(s["bytes02"]["count"], 0)

    def test_a_glyph_frame_passes_too(self):
        s = self.one(raw_frame(3 * 480 + 7))
        self.assertEqual((s["verdict"], s["frame_id"], s["colour15_mismatches"]), ("PASS", 1447, 0))

    def test_one_pixel_fails(self):
        raw = mutate(raw_frame(73), lambda b: set_word(b, 130, 77, get_word(b, 130, 77) ^ 0x0001))
        s = self.one(raw)
        self.assertEqual((s["verdict"], s["colour15_mismatches"], s["displacement_class"]), ("FAIL", 1, "SINGLE_PIXEL"))
        self.assertEqual(s["colour15_first"][0][:2], (130, 77))

    def test_a_row_shift_is_classified(self):
        base = raw_frame(73)

        def shift(b):
            for y in range(8, 20):
                for x in range(56, 239):
                    set_word(b, x, y, get_word(base, x, y + 1))
        s = self.one(mutate(base, shift))
        self.assertEqual((s["verdict"], s["displacement_class"]), ("FAIL", "ROW_SHIFT"))

    def test_a_column_shift_is_classified(self):
        base = raw_frame(73)

        def shift(b):
            for y in range(20, 24):
                for x in range(60, 200):
                    set_word(b, x, y, get_word(base, x + 3, y))
        s = self.one(mutate(base, shift))
        self.assertEqual((s["verdict"], s["displacement_class"]), ("FAIL", "COLUMN_SHIFT"))

    def test_an_axis_swap_is_classified(self):
        base = raw_frame(73)

        def swap(b):
            for i in range(8, 24):
                for j in range(8, 24):
                    set_word(b, 56 + i, j, get_word(base, 56 + j, i))
        s = self.one(mutate(base, swap))
        self.assertEqual((s["verdict"], s["displacement_class"]), ("FAIL", "AXIS_SWAP"))

    def test_a_tile_permutation_is_classified(self):
        base = raw_frame(73)

        def perm(b):
            # swap two 4x4 tiles inside the field, and two more
            for (ax, ay, bx, by) in ((60, 8, 100, 24), (72, 40, 200, 60)):
                for j in range(4):
                    for i in range(4):
                        set_word(b, ax + i, ay + j, get_word(base, bx + i, by + j))
                        set_word(b, bx + i, by + j, get_word(base, ax + i, ay + j))
        s = self.one(mutate(base, perm))
        self.assertEqual((s["verdict"], s["displacement_class"]), ("FAIL", "TILE_PERMUTATION"))

    def test_a_block_displacement_is_caught_by_the_strip_and_the_field(self):
        base = raw_frame(73)

        def swap_blocks(b):
            a = base[5 * 0xF00:6 * 0xF00]
            c = base[9 * 0xF00:10 * 0xF00]
            b[5 * 0xF00:6 * 0xF00] = c
            b[9 * 0xF00:10 * 0xF00] = a
        s = self.one(mutate(base, swap_blocks))
        # the strips now carry BLOCK_INDEX != position -> the sample is refused before any pixel is judged
        self.assertEqual(s["verdict"], "INCONCLUSIVE")
        self.assertFalse(s["strips"]["consistent"])
        self.assertEqual(s["strips"]["index_ok"], 38)

    def test_a_texture_defect_fails_while_the_source_passes(self):
        s = self.one(raw_frame(73), mode="T")
        self.assertEqual(s["colour15_mismatches"], 0)
        self.assertEqual((s["verdict"], s["tex_vs_python"], s["tex_vs_oracle"], s["tex_vs_c"]), ("FAIL", 1, 1, 1))

    def test_bytes_0_and_2_are_observational_only(self):
        s = self.one(raw_frame(73, filler=0x80))
        self.assertEqual(s["verdict"], "PASS")
        self.assertEqual(s["bytes02"]["count"], 38400)

    def test_bit_15_elsewhere_is_reported_not_judged(self):
        raw = mutate(raw_frame(73), lambda b: set_word(b, 100, 50, get_word(b, 100, 50) | 0x8000))
        s = self.one(raw)
        self.assertEqual(s["verdict"], "PASS")
        self.assertEqual(s["bit15"], [(0, 0), (100, 50)])

    def test_a_faulted_stimulus_is_inconclusive(self):
        s = self.one(raw_frame(73, status=0x80 | 0x18))
        self.assertEqual((s["verdict"], s["fault"]), ("INCONCLUSIVE", True))

    def test_python_and_c_conversions_agree_on_arbitrary_bytes(self):
        import random
        rnd = random.Random(7)
        raw = bytes(rnd.getrandbits(8) for _ in range(153600))
        self.assertEqual(vfull.convert_py(raw), vfull.convert_c(raw))
        self.assertEqual(vfull.convert_py(raw_frame(480)), icoord.tiled_oracle(480, 0x18))


if __name__ == "__main__":
    unittest.main()
