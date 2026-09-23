"""
tests/host/test_agb_coord2.py — coord-0002 (stimulus/agb-coord2), the second
implementation of OGBPCOORD1 (HARDWARE_TESTS §V6.23, GitHub Issue #13).

Three independent parities, none of which uses an implementation buffer as the
oracle: (1) coord-0002 against the UNCHANGED tools/icoord.py model, word for
word over the whole 240 x 160 picture, for ordinary frames, every digit entry
0..9, steady frames as the counter squares change, every exit, the appearance
boundaries and the field's restoration after an exit; (2) the canonical
witness against the frozen istim words, CRC and STATUS included, for varied
STATUS values; (3) coord-0001 against coord-0002 -- both ROMs' own main.c,
compiled on the host and driven identically -- over the same 240 x 160 words
for identical logical (FRAME_ID, STATUS). A static audit pins the repair: the
entry path selects a boot-built table and neither computes a pixel nor reads
seg_of_digit, the ten tables are EWRAM NOLOAD, the precompute precedes the
display, and coord-0001's source is untouched.
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import hostcc  # noqa: E402
import icoord  # noqa: E402
import istim  # noqa: E402

ROM1_SRC = os.path.join(ROOT, "stimulus", "agb-coord", "source", "main.c")
ROM2_SRC = os.path.join(ROOT, "stimulus", "agb-coord2", "source", "main.c")
MAKEFILE2 = os.path.join(ROOT, "stimulus", "agb-coord2", "Makefile")
COORD1_SRC_SHA = "cf6db735e33ae1582ff996fd42c243ba000a59b2bde3b467163e69bf593c23d1"

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
#ifdef DIGITS
    glyph_tables_init();
#endif
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


def build(src_dir, name):
    tmp = tempfile.mkdtemp(prefix="agbcoord2-%s-" % name)
    src = os.path.join(tmp, "harness.c")
    with open(src, "w") as f:
        f.write(HARNESS)
    exe = os.path.join(tmp, "harness")
    have, ok, err = hostcc.compile_c(["-std=gnu11", "-O1", "-Wall", "-Wextra", "-I", src_dir, "-o", exe, src])
    return exe, have, ok, err


_B = {}


def rom(which, frame_id, status):
    if which not in _B:
        _B[which] = build(os.path.dirname(ROM1_SRC if which == 1 else ROM2_SRC), "c%d" % which)
    exe, have, ok, err = _B[which]
    hostcc.require_here(have, ok, err, "the coord-000%d ROM harness" % which)
    r = subprocess.run([exe, str(frame_id), str(status)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    w = [int(x, 16) for x in r.stdout.split()]
    assert len(w) == 38400
    return w


def diff_against_model(words, fid, st):
    bad, first = 0, None
    for y in range(160):
        row = y * 240
        for x in range(240):
            want = icoord.expected_agb(fid, x, y, st)
            if words[row + x] != want:
                bad += 1
                if first is None:
                    first = (x, y, hex(words[row + x]), hex(want))
    return bad, first


ENTRIES = [(k * 480, k % 10) for k in range(1, 11)]                        # digits 1..9 then 0 at k = 10


class Coord2MatchesTheUnchangedModel(unittest.TestCase):
    def test_ordinary_and_pre_glyph_frames(self):
        for fid, st in ((0, 0x7F), (1, 0x7F), (73, 0x36), (479, 0x36), (700, 0x27), (1439, 0x26), (2119, 0x26)):
            bad, first = diff_against_model(rom(2, fid, st), fid, st)
            self.assertEqual(bad, 0, "f=%d st=0x%02x first %s" % (fid, st, first))

    def test_every_digit_entry_0_to_9(self):
        for fid, digit in ENTRIES:
            self.assertEqual(icoord.glyph_shown(fid), True)
            bad, first = diff_against_model(rom(2, fid, 0x36), fid, 0x36)
            self.assertEqual(bad, 0, "entry f=%d digit %d first %s" % (fid, digit, first))

    def test_steady_frames_as_the_counter_squares_change(self):
        for fid in (481, 482, 483, 485, 488, 496, 511, 519, 961, 990, 1470, 1950):
            bad, first = diff_against_model(rom(2, fid, 0x27), fid, 0x27)
            self.assertEqual(bad, 0, "steady f=%d first %s" % (fid, first))

    def test_every_exit_and_the_field_restored_after_it(self):
        for k in range(1, 11):
            fid = k * 480 + 40
            for f in (fid, fid + 1):
                bad, first = diff_against_model(rom(2, f, 0x26), f, 0x26)
                self.assertEqual(bad, 0, "exit k=%d f=%d first %s" % (k, f, first))
            after = rom(2, fid + 1, 0x26)
            for y in range(40, 136):
                for x in range(122, 172):
                    self.assertEqual(after[y * 240 + x], icoord.field(x, y), "field not restored at (%d,%d) after exit k=%d" % (x, y, k))

    def test_the_appearance_boundaries(self):
        for k in (1, 2, 3, 4, 10):
            for fid in (k * 480 - 1, k * 480, k * 480 + 1, k * 480 + 39, k * 480 + 40, k * 480 + 41):
                bad, first = diff_against_model(rom(2, fid, 0x18), fid, 0x18)
                self.assertEqual(bad, 0, "boundary k=%d f=%d first %s" % (k, fid, first))

    def test_the_canonical_witness_is_ogbpidx1_byte_for_byte_with_crc_and_status(self):
        for fid, st in ((0, 0x7F), (480, 0x36), (960, 0x27), (1440, 0x26), (1920, 0x26), (2120, 0x18), (4800, 0x00), (4800, 0xFF), (777, 0x80)):
            words = rom(2, fid, st)
            for b in range(40):
                y = 4 * b
                got = [istim.swap_outer(words[y * 240 + x]) for x in istim.WITNESS_STRIP]
                self.assertEqual(got, istim.witness_words(fid, b, st))
                d = istim.decode_canonical(got, b)
                self.assertEqual((d["outcome"], d["frame_id"], d["status"], d["index_ok"]), (istim.CANONICAL_OK, fid, st, True))

    def test_bit_15_is_never_written(self):
        for fid in (0, 480, 1000, 4800):
            self.assertTrue(all(w < 0x8000 for w in rom(2, fid, 0x18)))


class Coord1AndCoord2PublishTheSameFrame(unittest.TestCase):
    """The intended 240 x 160 picture, not the strip alone, for identical logical
    (FRAME_ID, STATUS); both ROMs are driven from frame 0 by the same harness."""

    CASES = [(0, 0x7F), (479, 0x36), (480, 0x36), (481, 0x27), (500, 0x27), (519, 0x27), (520, 0x27), (521, 0x26),
             (959, 0x27), (960, 0x27), (1000, 0x27), (1001, 0x26), (1439, 0x26), (1440, 0x26), (1480, 0x26),
             (1919, 0x26), (1920, 0x26), (1921, 0x26), (1960, 0x26), (2400, 0x18), (2880, 0x18), (3360, 0x18),
             (3840, 0x18), (4320, 0x18), (4800, 0x18), (4839, 0x18), (4840, 0x18), (4841, 0x18), (5280, 0xFF)]

    def test_full_frame_equality(self):
        for fid, st in self.CASES:
            a, b = rom(1, fid, st), rom(2, fid, st)
            if a != b:
                i = next(i for i in range(38400) if a[i] != b[i])
                self.fail("f=%d st=0x%02x: coord-0001 and coord-0002 differ first at (%d,%d): %04x vs %04x" % (fid, st, i % 240, i // 240, a[i], b[i]))
            bad, first = diff_against_model(b, fid, st)
            self.assertEqual(bad, 0, "and coord-0002 f=%d differs from the model first at %s" % (fid, first))


class TheRepairIsInTheSourceAndCoord1IsUntouched(unittest.TestCase):
    def test_coord_0001_source_is_byte_identical_to_the_run_12_build_input(self):
        self.assertEqual(hashlib.sha256(read(ROM1_SRC).encode("utf-8")).hexdigest(), COORD1_SRC_SHA)

    def test_the_entry_path_builds_nothing_and_reads_no_rom_byte(self):
        body = strip_comments(read(ROM2_SRC))
        i = body.index("static void prepare_frame(")
        j = body.index("static void pub_copy32(", i)
        prep = body[i:j]
        for tok in ("glyph_lit", "seg_of_digit", "glyph_erase", "glyph_tables[sc->digit][", "GLYPH_ROWS; r++"):
            self.assertNotIn(tok, prep, tok)
        self.assertIn("glyph_sel = glyph_tables[sc->digit];", prep)
        self.assertIn("op_digit = OP_PAINT;", prep)
        self.assertNotIn("glyph_rows", body)

    def test_the_ten_tables_are_ewram_noload_and_built_before_the_display(self):
        body = strip_comments(read(ROM2_SRC))
        self.assertIn("static u16 glyph_tables[DIGITS][GLYPH_ROWS][GLYPH_SPAN_W] EWRAM_SECTION;", body)
        self.assertIn("#define DIGITS 10u", body)
        self.assertIn('#define EWRAM_SECTION __attribute__((section(".sbss")))', body)
        m = body.index("int main(void)")
        main = body[m:]
        self.assertLess(main.index("erase_tables_init();"), main.index("glyph_tables_init();"))
        self.assertLess(main.index("glyph_tables_init();"), main.index("paint_background();"))
        self.assertLess(main.index("glyph_tables_init();"), main.index("REG_DISPCNT = 0x0403u;"))
        self.assertLess(main.index("REG_DISPCNT = 0x0403u;"), main.index("for (;;) {"))
        self.assertEqual(main.count("glyph_tables_init();"), 1)

    def test_publish_dmas_the_selected_rows_from_the_same_span(self):
        body = strip_comments(read(ROM2_SRC))
        i = body.index("static void publish_frame(void)")
        j = body.index("int main(void)", i)
        pub = body[i:j]
        self.assertIn("pub_copy32(VRAM + (GLYPH_Y0 + r) * SCREEN_W + GLYPH_SPAN_X0, glyph_sel[r], GLYPH_SPAN_W);", pub)
        for tok in ("crc_", "strip_word", "glyph_lit", "field_at", "status_measure", "REG_TM0CNT", "REG_VCOUNT", "glyph_tables["):
            self.assertNotIn(tok, pub, tok)
        self.assertIn('__attribute__((section(".iwram"), noinline))\nstatic void publish_frame(void)', body)
        self.assertIn('__attribute__((section(".iwram"), noinline))\nstatic void prepare_frame(', body)

    def test_no_heap_no_filesystem_no_link_no_serial_no_interrupt_no_division(self):
        body = strip_comments(read(ROM2_SRC))
        for tok in ("malloc", "fopen", "printf", "REG_SIOCNT", "REG_RCNT", "__attribute__((interrupt", "irq"):
            self.assertNotIn(tok, body, tok)
        self.assertIsNone(re.search(r"[^/]/[^/]", body.replace("//", "")), "a division operator survived")
        self.assertNotIn("%", body)

    def test_the_frozen_constants_and_the_schedule_are_the_contract(self):
        body = read(ROM2_SRC)
        for line in ("#define FIELD_X0   56u", "#define FIELD_W    183u", "#define X_GUARD_C  239u",
                     "#define GLYPH_P      480u", "#define GLYPH_W      40u", "#define GLYPH_X0     123u",
                     "#define GLYPH_Y0     40u", "#define GLYPH_COLS   48u", "#define GLYPH_ROWS   80u",
                     "#define SQ_N         6u", "#define SQ_SIZE      8u", "#define SYM_ONE   0x7FFFu",
                     "#define SYM_FLAG  0x03E0u", "#define SYNC_BYTE    0xB2u", "#define STRIP_BITS   54u",
                     "#define GLYPH_COLOUR 0x7FFFu", "REG_WAITCNT = 0x4317u;"):
            self.assertIn(line, body, line)
        self.assertNotIn("STRIP_R", body.replace("STRIP-R", ""))

    def test_the_status_is_snapshotted_before_prepare_and_measured_around_publish(self):
        body = strip_comments(read(ROM2_SRC))
        loop = body[body.index("int main(void)"):]
        self.assertLess(loop.index("status = status_byte(&st);"), loop.index("prepare_frame(frame_id, status, &sc);"))
        self.assertLess(loop.index("t0 = REG_TM0CNT_L;"), loop.index("publish_frame();", loop.index("t0 = REG_TM0CNT_L;")))
        self.assertIn("status_measure(&st, vc0, vc1, elapsed);", loop)
        self.assertIn("while (REG_VCOUNT >= VCOUNT_VBLANK_FIRST) { }", loop)
        self.assertIn("while (REG_VCOUNT <  VCOUNT_VBLANK_FIRST) { }", loop)

    def test_the_makefile_carries_the_new_identity(self):
        m = read(MAKEFILE2)
        self.assertIn("APP_NAME   := agb-coord2", m)
        self.assertIn("STIM_ID    := coord-0002", m)
        self.assertIn("GAME_TITLE := OPENGBPCOOR2", m)
        self.assertIn("GAME_CODE  := CGB2", m)
        self.assertIn("build/stimulus/agb-coord2/", m)


class BuiltArtifactIfPresent(unittest.TestCase):
    INFO = os.path.join(ROOT, "build", "stimulus", "agb-coord2", "build-info.txt")

    def test_build_info_names_coord_0002(self):
        if not os.path.exists(self.INFO):
            self.skipTest("coord-0002 not built here (make stimulus-coord2)")
        t = read(self.INFO)
        self.assertIn("stimulus_id=coord-0002", t)
        self.assertRegex(t, r"sha256_rom=[0-9a-f]{64}")
        self.assertIn("NOT PHYSICALLY EXECUTED", t)


if __name__ == "__main__":
    unittest.main()
