"""
tests/host/test_vvi.py — OGBPVI1 and the GBP-VIDEO-007 SOFTWARE chain, driven
through the REAL C writer (src/gbp/gbp_vvi.c + gbp_vvidump.c compiled on the
host): format and integrity, hand-over -> observed-current binding, the VI
register consistency model, missing / superseded latches, the joins with
synthetic OGBPIDXCAP1 / OGBPDISP2 structures, and the explicit proof that
nothing here classifies physical visibility.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import icoord  # noqa: E402
import vvi  # noqa: E402

SRC = os.path.join(ROOT, "src", "gbp")

GENERATOR = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_vvi.h"
#include "gbp_vvidump.h"
static struct gbp_vvi_rec recs[GBP_VVI_CAP];
static uint8_t chunk[GBP_VVIDUMP_CHUNK];
static int sink(void *ctx, const uint8_t *d, uint32_t n) { return fwrite(d, 1, n, (FILE *)ctx) != n; }
/* stdin lines: "H frame_index life xfb phys t retrace" or "L t retrace vi14 vi15 vi18 vi19" (latch of what is awaited) */
int main(int argc, char **argv)
{
    struct gbp_vvi v; struct gbp_vvidump_info info; FILE *out; uint64_t w = 0; long n; char line[256];
    if (argc != 2) return 2;
    gbp_vvi_init(&v, recs, GBP_VVI_CAP);
    while (fgets(line, sizeof line, stdin)) {
        if (line[0] == 'H') {
            unsigned fi, life, phys, rt; int xfb; unsigned long long t;
            if (sscanf(line + 1, "%u %u %d %x %llu %u", &fi, &life, &xfb, &phys, &t, &rt) != 6) return 3;
            (void)gbp_vvi_handed(&v, fi, life, (int16_t)xfb, phys, t, rt);
        } else if (line[0] == 'L') {
            unsigned rt, a, b, c, d; unsigned long long t;
            if (sscanf(line + 1, "%llu %u %x %x %x %x", &t, &rt, &a, &b, &c, &d) != 6) return 4;
            (void)gbp_vvi_latch(&v, t, rt, (uint16_t)a, (uint16_t)b, (uint16_t)c, (uint16_t)d);
        }
    }
    memset(&info, 0, sizeof info);
    info.tb_hz = 40500000u; info.xfb_slots = 2u;
    if (gbp_vvidump_set_identity(&info, "GBP-VIDEO-004", "stream-0013", "gbp-video-stream-probe", "abc1234")) return 5;
    out = fopen(argv[1], "wb"); if (!out) return 6;
    n = gbp_vvidump_stream(&info, &v, chunk, sizeof chunk, sink, out, &w);
    fclose(out);
    return n > 0 ? 0 : 7;
}
'''


class Producer:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="opengbp-vi-")
        self.bin = os.path.join(self.tmp, "gen")
        src = os.path.join(self.tmp, "gen.c")
        with open(src, "w") as f:
            f.write(GENERATOR)
        r = subprocess.run(["gcc", "-std=gnu11", "-O1", "-I", SRC, "-o", self.bin, src,
                            os.path.join(SRC, "gbp_vvi.c"), os.path.join(SRC, "gbp_vvidump.c"),
                            os.path.join(SRC, "gbp_crc32.c")], capture_output=True, text=True)
        self.ok, self.err = r.returncode == 0, r.stderr

    def write(self, path, script):
        r = subprocess.run([self.bin, path], input=script, capture_output=True, text=True)
        assert r.returncode == 0, "generator rc=%d %s" % (r.returncode, r.stderr[:200])
        return path


PROD = Producer()
XFB = {0: 0x00A60000, 1: 0x00B1C000}          # two MEM1 stream framebuffers (physical), synthetic


def regs_for(phys, bottom_offset=1280):
    return "%04x %04x %04x %04x" % ((phys >> 16) & 0xFF, phys & 0xFFFF, ((phys + bottom_offset) >> 16) & 0xFF, (phys + bottom_offset) & 0xFFFF)


def handoff(fi, life, xfb, t, rt):
    return "H %d %d %d %x %d %d\n" % (fi, life, xfb, XFB[xfb], t, rt)


def latch(t, rt, xfb, wrong=False):
    phys = XFB[xfb] ^ (0x20 if wrong else 0)
    return "L %d %d %s\n" % (t, rt, regs_for(phys))


class TheContainer(unittest.TestCase):
    def setUp(self):
        if not PROD.ok:
            self.skipTest("gcc unavailable: %s" % PROD.err[:200])
        self.tmp = tempfile.mkdtemp(prefix="opengbp-vi-t-")

    def path(self, name="vi.bin"):
        return os.path.join(self.tmp, name)

    def test_the_c_writer_and_the_python_reader_agree(self):
        p = PROD.write(self.path(), handoff(356, 7, 1, 1000, 50) + latch(1100, 51, 1) + handoff(357, 8, 0, 2000, 52))
        info = vvi.load(p)
        self.assertEqual((info["records_n"], info["handed"], info["latched"], info["superseded"], info["awaiting_at_end"]), (2, 2, 1, 0, 1))
        self.assertEqual(info["build_id"], "stream-0013")
        r = info["records"][0]
        self.assertEqual((r["frame_index"], r["life"], r["xfb"], r["phys"], r["t_handed"], r["retrace_handed"]), (356, 7, 1, XFB[1], 1000, 50))
        self.assertEqual((r["latched"], r["t_latch"], r["retrace_latch"]), (True, 1100, 51))
        self.assertEqual(vvi.regs_consistent(r), (True, True, XFB[1]))
        self.assertEqual((info["records"][1]["latched"], info["records"][1]["superseded"]), (False, False))

    def test_every_byte_flip_is_refused(self):
        p = PROD.write(self.path(), handoff(356, 7, 1, 1000, 50) + latch(1100, 51, 1))
        data = bytearray(open(p, "rb").read())
        for i in range(len(data)):
            data[i] ^= 0x01
            with self.assertRaises(ValueError, msg="offset %d" % i):
                vvi.parse(bytes(data))
            data[i] ^= 0x01
        vvi.parse(bytes(data))

    def test_superseded_and_missing_latches_stay_unlatched(self):
        p = PROD.write(self.path(), handoff(1, 1, 0, 100, 1) + handoff(2, 2, 1, 200, 2) + latch(250, 3, 1) + handoff(3, 3, 0, 300, 4))
        info = vvi.load(p)
        flags = [(r["latched"], r["superseded"]) for r in info["records"]]
        self.assertEqual(flags, [(False, True), (True, False), (False, False)])
        self.assertEqual((info["superseded"], info["latched"], info["awaiting_at_end"]), (1, 1, 2))
        self.assertEqual(vvi.regs_consistent(info["records"][0]), (False, False, None))

    def test_a_register_readback_that_names_another_buffer_is_inconsistent(self):
        p = PROD.write(self.path(), handoff(5, 5, 0, 100, 1) + latch(150, 2, 0, wrong=True))
        r = vvi.load(p)["records"][0]
        self.assertTrue(r["latched"])
        self.assertEqual(vvi.regs_consistent(r)[0], False)


class TheJoin(unittest.TestCase):
    def setUp(self):
        if not PROD.ok:
            self.skipTest("gcc unavailable")
        self.tmp = tempfile.mkdtemp(prefix="opengbp-vi-j-")

    def test_r_h_l_from_synthetic_records(self):
        # retained: frame_index 356.. carries frame_id 73.. ; appearance 1 = frame_id 480..519 -> frame_index 763..802
        fi_to_fid = {fi: fi - 283 for fi in range(356, 2404)}
        life = [{"frame_index": fi, "disposition": 1, "t_decision": 10 * fi, "retrace_decision": fi // 2}
                for fi in range(356, 2404) if fi not in (770, 771)]      # two frames never handed
        events = [{"decision": 1, "frame_index": fi, "xfb_target": fi & 1} for fi in range(356, 2404)]
        script = ""
        for fi in range(763, 803):
            if fi in (770, 771):
                continue
            script += handoff(fi, fi, fi & 1, 10 * fi, fi // 2)
            if fi != 790:                                               # one hand-over never observed current
                script += latch(10 * fi + 5, fi // 2 + 1, fi & 1)
        vi_info = vvi.load(PROD.write(os.path.join(self.tmp, "vi.bin"), script))
        rows = vvi.chain(fi_to_fid, {"life": life, "events": events}, vi_info, appearances=(1, 2))
        r1, r2 = rows
        self.assertEqual((r1["k"], r1["digit"], len(r1["R"]), r1["retained"], r1["H"], r1["L"]), (1, 1, 40, 40, 38, 37))
        self.assertEqual(r1["first_handed_t"], 7630)
        self.assertEqual(r1["first_latch_t"], 7635)
        self.assertEqual(r1["xfb_targets"], [0, 1])
        self.assertEqual((r2["retained"], r2["H"], r2["L"]), (40, 40, 0))     # nothing latched for k = 2 in this script

    def test_idx_map_uses_the_frozen_decoder_on_the_witness(self):
        idx = {"records": [{"frame_index": 356, "witness": [icoord.witness_words(73, b, 0x18) for b in range(40)]},
                           {"frame_index": 357, "witness": [icoord.witness_words(74, b, 0x18) for b in range(40)]},
                           {"frame_index": 358, "witness": [[0] * 54 for _ in range(40)]}]}
        self.assertEqual(vvi.idx_map(idx), {356: 73, 357: 74})


class ItDoesNotClassifyVisibility(unittest.TestCase):
    def test_the_module_has_no_visibility_input_and_says_so(self):
        with open(os.path.join(ROOT, "tools", "vvi.py"), encoding="utf-8") as f:
            src = f.read()
        body = re.sub(r'""".*?"""', "", src, flags=re.S)
        body = re.sub(r"#[^\n]*", "", body)
        for tok in ("seen", "visible", "observed_by", "operator_report", "scanout", "PASS", "FAIL", "INCONCLUSIVE"):
            self.assertNotIn(tok, body, tok)
        self.assertIn("SOFTWARE CHAIN ONLY", src)
        self.assertIn("does not classify GBP-VIDEO-007", src)

    def test_the_report_carries_the_boundary_line(self):
        if not PROD.ok:
            self.skipTest("gcc unavailable")
        p = PROD.write(os.path.join(tempfile.mkdtemp(), "vi.bin"), handoff(1, 1, 0, 100, 1))
        text = vvi.format_report(vvi.load(p))
        self.assertIn("SOFTWARE CHAIN ONLY", text)


if __name__ == "__main__":
    unittest.main()
