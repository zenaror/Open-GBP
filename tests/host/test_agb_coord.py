"""
tests/host/test_agb_coord.py — the coord-0001 ROM (stimulus/agb-coord) against
its model (tools/icoord.py), word for word, on the host (Issue #7).

The harness compiles the ROM's own main.c with the three hardware bases
relocated to fake memory, drives PREPARE + PUBLISH for every frame up to the
one under test (the glyph is painted and erased at appearance edges, so the
VRAM of frame F is the result of frames 0..F), and dumps the 38 400 VRAM words.
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
import istim  # noqa: E402

ROM_SRC = os.path.join(ROOT, "stimulus", "agb-coord", "source", "main.c")
MAKEFILE = os.path.join(ROOT, "stimulus", "agb-coord", "Makefile")

HARNESS = r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static unsigned char fake_vram[96 * 1024];
static unsigned char fake_oam[1024];
static unsigned char fake_io[1024];
#define AGB_HOST_TEST 1
#define AGB_IO_BASE   ((unsigned long)fake_io)
#define AGB_VRAM_BASE ((unsigned long)fake_vram)
#define AGB_OAM_BASE  ((unsigned long)fake_oam)
#define main rom_main_unused
#include "main.c"
#undef main
int main(int argc, char **argv)
{
    unsigned frame_id, status, f, i;
    struct sched sc;
    if (argc != 3) return 2;
    frame_id = (unsigned)strtoul(argv[1], 0, 0);
    status   = (unsigned)strtoul(argv[2], 0, 0);
    crc_table_init();
    erase_tables_init();
    paint_background();
    sched_init(&sc);
    prepare_frame(0, (u8)status, &sc);
    publish_frame();
    for (f = 1; f <= frame_id; f++) {
        sched_advance(&sc);
        prepare_frame(f, (u8)status, &sc);
        publish_frame();
    }
    for (i = 0; i < 240u * 160u; i++) printf("%04x\n", ((u16 *)fake_vram)[i]);
    return 0;
}
'''


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def strip_comments(code):
    return re.sub(r"/\*.*?\*/", "", code, flags=re.S)


class RomMatchesTheModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="agbcoord-")
        src = os.path.join(cls.tmp, "harness.c")
        with open(src, "w") as f:
            f.write(HARNESS)
        cls.bin = os.path.join(cls.tmp, "harness")
        r = subprocess.run(["gcc", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-I", os.path.dirname(ROM_SRC),
                            "-o", cls.bin, src], capture_output=True, text=True)
        cls.built, cls.err = r.returncode == 0, r.stderr

    def _rom(self, frame_id, status):
        r = subprocess.run([self.bin, str(frame_id), str(status)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        w = [int(x, 16) for x in r.stdout.split()]
        self.assertEqual(len(w), 38400)
        return w

    def test_the_rom_renders_exactly_what_the_model_says(self):
        if not self.built:
            self.skipTest("gcc unavailable: %s" % self.err[:200])
        # frames before, at, inside, at the end of and after appearances 1 and 2, plus digit wrap
        cases = [(0, 0x7F), (1, 0x7F), (479, 0x18), (480, 0x18), (481, 0x18), (500, 0x42), (519, 0x18),
                 (520, 0x18), (521, 0x00), (960, 0x18), (999, 0x18), (1000, 0x18), (1440, 0xFF), (1920, 0x80)]
        for fid, st in cases:
            rom = self._rom(fid, st)
            bad, first = 0, None
            for y in range(160):
                for x in range(240):
                    want = icoord.expected_agb(fid, x, y, st)
                    got = rom[y * 240 + x]
                    if got != want:
                        bad += 1
                        if first is None:
                            first = (x, y, hex(got), hex(want))
            self.assertEqual(bad, 0, "f=%d st=0x%02x: %d words differ, first %s" % (fid, st, bad, first))

    def test_the_tenth_and_eleventh_appearances_wrap_the_digit(self):
        if not self.built:
            self.skipTest("gcc unavailable")
        for fid in (10 * 480, 11 * 480 + 39):
            rom = self._rom(fid, 0x18)
            self.assertTrue(all(rom[y * 240 + x] == icoord.expected_agb(fid, x, y, 0x18)
                                for y in range(40, 136) for x in range(122, 172)))

    def test_the_canonical_witness_is_byte_identical_to_ogbpidx1(self):
        if not self.built:
            self.skipTest("gcc unavailable")
        for fid, st in ((0, 0x7F), (480, 0x18), (2120, 0x18)):
            rom = self._rom(fid, st)
            for b in range(40):
                y = 4 * b
                got = [istim.swap_outer(rom[y * 240 + x]) for x in istim.WITNESS_STRIP]
                self.assertEqual(got, istim.witness_words(fid, b, st))
                d = istim.decode_canonical(got, b)
                self.assertEqual((d["outcome"], d["frame_id"], d["index_ok"]), (istim.CANONICAL_OK, fid, True))

    def test_the_rom_never_writes_bit_15(self):
        if not self.built:
            self.skipTest("gcc unavailable")
        for fid in (0, 480, 1000):
            self.assertTrue(all(w < 0x8000 for w in self._rom(fid, 0x18)))


class RomStaticAudit(unittest.TestCase):
    def test_no_heap_no_filesystem_no_link_no_serial_no_interrupt(self):
        body = strip_comments(read(ROM_SRC))
        for tok in ("malloc", "fopen", "printf", "REG_SIOCNT", "REG_RCNT", "__attribute__((interrupt", "irq"):
            self.assertNotIn(tok, body, tok)

    def test_no_division_anywhere(self):
        body = strip_comments(read(ROM_SRC))
        self.assertIsNone(re.search(r"[^/]/[^/]", body.replace("//", "")), "a division operator survived")
        self.assertNotIn("%", body)

    def test_the_vblank_path_is_publish_only_and_in_iwram(self):
        body = strip_comments(read(ROM_SRC))
        i = body.index("static void publish_frame(void)")
        j = body.index("int main(void)", i)
        pub = body[i:j]
        for tok in ("crc_", "strip_word", "glyph_lit", "field_at", "status_measure", "REG_TM0CNT", "REG_VCOUNT"):
            self.assertNotIn(tok, pub, tok)
        self.assertIn('__attribute__((section(".iwram"), noinline))\nstatic void publish_frame(void)', body)
        self.assertIn('__attribute__((section(".iwram"), noinline))\nstatic void prepare_frame(', body)
        self.assertIn("EWRAM_SECTION", body)

    def test_the_frozen_constants_and_the_schedule_are_the_contract(self):
        body = read(ROM_SRC)
        for line in ("#define FIELD_X0   56u", "#define FIELD_W    183u", "#define X_GUARD_C  239u",
                     "#define GLYPH_P      480u", "#define GLYPH_W      40u", "#define GLYPH_X0     123u",
                     "#define GLYPH_Y0     40u", "#define GLYPH_COLS   48u", "#define GLYPH_ROWS   80u",
                     "#define SQ_N         6u", "#define SQ_SIZE      8u", "#define SYM_ONE   0x7FFFu",
                     "#define SYM_FLAG  0x03E0u", "#define SYNC_BYTE    0xB2u", "#define STRIP_BITS   54u"):
            self.assertIn(line, body, line)
        self.assertNotIn("STRIP_R", body.replace("STRIP-R", ""))
        self.assertNotIn("BAR_PERIOD", body)

    def test_the_status_is_snapshotted_before_prepare_and_measured_around_publish(self):
        body = strip_comments(read(ROM_SRC))
        m = body.index("int main(void)")
        loop = body[m:]
        self.assertLess(loop.index("status = status_byte(&st);"), loop.index("prepare_frame(frame_id, status, &sc);"))
        self.assertLess(loop.index("t0 = REG_TM0CNT_L;"), loop.index("publish_frame();", loop.index("t0 = REG_TM0CNT_L;")))
        self.assertIn("status_measure(&st, vc0, vc1, elapsed);", loop)

    def test_the_makefile_carries_the_new_identity(self):
        m = read(MAKEFILE)
        self.assertIn("APP_NAME   := agb-coord", m)
        self.assertIn("STIM_ID    := coord-0001", m)
        self.assertIn("GAME_TITLE := OPENGBPCOORD", m)
        self.assertIn("GAME_CODE  := CGBP", m)


class BuiltArtifactIfPresent(unittest.TestCase):
    INFO = os.path.join(ROOT, "build", "stimulus", "agb-coord", "build-info.txt")

    def test_build_info_names_coord_0001_and_the_rom_hash(self):
        if not os.path.exists(self.INFO):
            self.skipTest("coord-0001 not built here (make stimulus-coord)")
        t = read(self.INFO)
        self.assertIn("stimulus_id=coord-0001", t)
        self.assertRegex(t, r"sha256_rom=[0-9a-f]{64}")
        self.assertIn("NOT PHYSICALLY EXECUTED", t)


if __name__ == "__main__":
    unittest.main()
