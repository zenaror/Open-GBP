"""The OGBPIDX1 ROM against its own reference model, and the analyzer.

The ROM's pure rendering logic is compiled FOR THE HOST with the two hardware
bases relocated (the only thing a host test may move) and compared word for word
against tools/istim.py. A stimulus that cannot be compared to its model is not a
measuring instrument.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import istim   # noqa: E402
import vindex  # noqa: E402

ROM_SRC = os.path.join(ROOT, "stimulus", "agb-indexed", "source", "main.c")

HARNESS = r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

/* fake hardware: 96 KiB VRAM, 1 KiB OAM, 1 KiB I/O */
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
    unsigned frame_id, status, prev_phase, phase;
    unsigned i;
    if (argc != 4) return 2;
    frame_id   = (unsigned)strtoul(argv[1], 0, 0);
    status     = (unsigned)strtoul(argv[2], 0, 0);
    prev_phase = (unsigned)strtoul(argv[3], 0, 0);

    crc_table_init();
    paint_background();
    /* bar_phase_base is the ROM's own (frame_id mod 31) counter */
    phase = 0;
    for (i = 0; i < frame_id; i++) { phase++; if (phase >= BAR_PERIOD) phase = 0; }
    bar_phase_base = phase;
    /* the corrected ROM publishes in two phases; the harness drives BOTH, so
     * what it compares against the model is what VBlank actually writes */
    prepare_frame(frame_id, (u8)status, prev_phase);
    publish_frame();

    for (i = 0; i < 240u * 160u; i++)
        printf("%04x\n", ((u16 *)fake_vram)[i]);
    return 0;
}
'''


class RomMatchesTheReferenceModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="agbidx-")
        src = os.path.join(cls.tmp, "harness.c")
        with open(src, "w") as f:
            f.write(HARNESS)
        cls.bin = os.path.join(cls.tmp, "harness")
        r = subprocess.run(["gcc", "-std=gnu11", "-O1", "-Wall", "-Wextra",
                            "-I", os.path.dirname(ROM_SRC),
                            "-o", cls.bin, src],
                           capture_output=True, text=True)
        cls.built = (r.returncode == 0)
        cls.err = r.stderr

    def _rom_frame(self, frame_id, status, prev_phase):
        r = subprocess.run([self.bin, str(frame_id), str(status), str(prev_phase)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        w = [int(x, 16) for x in r.stdout.split()]
        self.assertEqual(len(w), 240 * 160)
        return w

    def test_the_rom_renders_exactly_what_the_model_says(self):
        """§35: 38 400 of 38 400 AGB words, for a broad deterministic set."""
        if not self.built:
            self.skipTest("gcc unavailable: %s" % self.err[:200])
        cases = [(0, 0x7F), (1, 0x7F), (2, 0x40), (30, 0x00), (31, 0x7F),
                 (1000, 0x42), (0x123456, 0x05), (0xFFFFFF, 0xFF),
                 (0xFFFFFF, 0x80), (12345, 0x13)]
        for frame_id, status in cases:
            prev = (frame_id - 1) % istim.BAR_PERIOD
            rom = self._rom_frame(frame_id, status, prev)
            bad = 0
            first = None
            for y in range(istim.HEIGHT):
                for x in range(istim.WIDTH):
                    want = istim.expected_agb(frame_id, x, y, status)
                    got = rom[y * istim.WIDTH + x]
                    if got != want:
                        bad += 1
                        if first is None:
                            first = (x, y, hex(got), hex(want))
            self.assertEqual(bad, 0,
                             "f=0x%06x st=0x%02x: %d/%d words differ, first %s"
                             % (frame_id, status, bad, 240 * 160, first))

    def test_the_canonical_witness_matches_word_for_word(self):
        """§35: every block's canonical witness, as the analyzer would read it."""
        if not self.built:
            self.skipTest("gcc unavailable")
        for frame_id, status in ((0, 0x7F), (777, 0x21), (0xFFFFFF, 0x80)):
            prev = (frame_id - 1) % istim.BAR_PERIOD
            rom = self._rom_frame(frame_id, status, prev)
            for b in range(istim.BLOCKS):
                y = b * istim.LINES_PER_BLOCK + istim.WITNESS_LOCAL_ROW
                got = [istim.swap_outer(rom[y * istim.WIDTH + x]) for x in istim.WITNESS_STRIP]
                want = istim.witness_words(frame_id, b, status)
                self.assertEqual(got, want, "f=0x%06x b=%d" % (frame_id, b))

    def test_the_rom_never_writes_bit15(self):
        if not self.built:
            self.skipTest("gcc unavailable")
        rom = self._rom_frame(4242, 0x55, 4241 % istim.BAR_PERIOD)
        self.assertEqual([w for w in rom if w & 0x8000], [])

    def test_frame_zero_is_complete_before_the_mode_is_selected(self):
        """§30: no partially initialised visible frame. Frame 0 must already
        decode completely."""
        if not self.built:
            self.skipTest("gcc unavailable")
        rom = self._rom_frame(0, istim.STATUS_MARGIN_INIT, 0)
        w = []
        for b in range(istim.BLOCKS):
            y = b * 4
            w.append([istim.swap_outer(rom[y * 240 + x]) for x in istim.WITNESS_STRIP])
        r = vindex.analyze_frame(w)
        self.assertEqual(r["outcome"], vindex.FRAME_OK)
        self.assertEqual(r["frame_id"], 0)
        self.assertEqual(r["status"], istim.STATUS_MARGIN_INIT)


FAULT_HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
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

/* argv: a sequence of "vc0,vc1,elapsed" triples; prints the STATUS byte after
 * each one, so the sticky/monotone behaviour is observable step by step. */
int main(int argc, char **argv)
{
    struct agb_status s = { 0u, STATUS_MARGIN_INIT };
    int i;
    printf("%02x\n", status_byte(&s));
    for (i = 1; i < argc; i++) {
        unsigned vc0, vc1, el;
        if (sscanf(argv[i], "%u,%u,%u", &vc0, &vc1, &el) != 3) return 2;
        status_measure(&s, (u16)vc0, (u16)vc1, el);
        printf("%02x\n", status_byte(&s));
    }
    return 0;
}
'''


class TheValidatorIsTheAuthority(unittest.TestCase):
    """§V5.41: the stimulus decides whether it is usable, and that decision must
    be adversarially drivable. indexed-0001's FAULT bit was CORRECT -- the update
    really did take 14.9 VBlanks -- so none of these gates may be weakened to
    make a run pass."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="agbfault-")
        src = os.path.join(cls.tmp, "fault.c")
        with open(src, "w") as f:
            f.write(FAULT_HARNESS)
        cls.bin = os.path.join(cls.tmp, "fault")
        r = subprocess.run(["gcc", "-std=gnu11", "-O1", "-Wall", "-Wextra",
                            "-I", os.path.dirname(ROM_SRC), "-o", cls.bin, src],
                           capture_output=True, text=True)
        cls.built = (r.returncode == 0)
        cls.err = r.stderr

    def run_steps(self, *steps):
        if not self.built:
            self.skipTest("gcc unavailable: %s" % self.err[:200])
        r = subprocess.run([self.bin] + list(steps), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return [int(x, 16) for x in r.stdout.split()]

    # VBlank is lines 160..227; a publication that ends at line 200 used 40 of
    # the 68 available lines and 2000 of the 1309*... ticks -- pick values well
    # inside the budget.
    def test_A_an_update_inside_the_vblank_leaves_fault_clear(self):
        out = self.run_steps("160,200,900")
        self.assertEqual(out[0], 0x7F, "the sentinel is the starting state")
        self.assertEqual(out[1] & 0x80, 0x00, "FAULT must stay clear")
        self.assertEqual(out[1] & 0x7F, 227 - 200, "VMARGIN is the lines left")

    def test_B_an_update_that_overruns_sets_fault(self):
        # over the tick budget
        self.assertEqual(self.run_steps("160,200,1310")[1], 0x80)
        # VCOUNT wrapped: it left VBlank and came back round
        self.assertEqual(self.run_steps("200,170,900")[1], 0x80)
        # and the real indexed-0001 measurement: ~19 507 ticks
        self.assertEqual(self.run_steps("160,200,19507")[1], 0x80)

    def test_C_fault_is_sticky_for_the_rest_of_the_boot(self):
        out = self.run_steps("160,200,1310", "160,200,900", "160,161,900", "160,200,100")
        self.assertEqual(out[1], 0x80)
        for k, v in enumerate(out[2:], start=2):
            self.assertEqual(v & 0x80, 0x80, "FAULT cleared at step %d" % k)
            self.assertEqual(v, 0x80, "VMARGIN must stay 0 once FAULT is set")

    def test_D_vmargin_is_a_monotone_minimum(self):
        out = self.run_steps("160,180,900", "160,170,900", "160,190,900", "160,200,900")
        margins = [v & 0x7F for v in out[1:]]
        # 47, then a LARGER margin (57) which must be ignored, then 37, then 27
        self.assertEqual(margins, [227 - 180, 227 - 180, 227 - 190, 227 - 200],
                         "a larger margin must not raise VMARGIN: %r" % margins)
        self.assertEqual(margins, sorted(margins, reverse=True),
                         "VMARGIN may only move DOWN: %r" % margins)
        self.assertEqual(margins[-1], min(227 - 180, 227 - 170, 227 - 190, 227 - 200))
        self.assertTrue(all(v & 0x80 == 0 for v in out[1:]), "no FAULT in this sequence")

    def test_E_the_sentinel_cannot_masquerade_as_a_measurement(self):
        """0x7F is both the sentinel and the largest representable margin, so a
        real measurement can only ever LOWER it -- the sentinel can never be
        reproduced by a measurement that did not happen."""
        out = self.run_steps("160,160,900")
        self.assertEqual(out[0], 0x7F)
        self.assertEqual(out[1] & 0x7F, 0x43, "227-160 = 67 = 0x43")
        self.assertLess(out[1] & 0x7F, 0x7F, "any measurement is below the sentinel")
        # and a margin that would exceed the field is clamped, never wrapped
        self.assertEqual(self.run_steps("0,0,900")[1] & 0x7F, 0x7F)

    def test_F_the_status_byte_is_a_pure_function_of_the_latched_state(self):
        a = self.run_steps("160,200,900")
        b = self.run_steps("160,200,900")
        self.assertEqual(a, b, "the validator is deterministic")


class ThePublicationIsBounded(unittest.TestCase):
    """§V5.41: prepare in the visible period, publish in VBlank."""

    def code(self):
        return open(ROM_SRC).read()

    def test_the_vblank_path_is_publish_only(self):
        c = self.code()
        i_wait = c.index("while (REG_VCOUNT <  VCOUNT_VBLANK_FIRST)")
        i_t0 = c.index("t0 = REG_TM0CNT_L;", i_wait)
        i_t1 = c.index("t1 = REG_TM0CNT_L;", i_t0)
        measured = c[i_t0:i_t1]
        self.assertIn("publish_frame();", measured)
        for forbidden in ("crc_", "strip_word", "prepare_frame", "background_at"):
            self.assertNotIn(forbidden, measured,
                             "%s must not run inside the measured window" % forbidden)

    def test_prepare_runs_before_the_vblank_wait(self):
        c = self.code()
        i_prep = c.index("prepare_frame(frame_id, status, prev_phase_base);")
        i_wait = c.index("while (REG_VCOUNT >= VCOUNT_VBLANK_FIRST)", i_prep)
        self.assertLess(i_prep, i_wait, "PREPARE must happen in the visible period")

    def test_prepare_writes_no_vram(self):
        c = self.code()
        body = c[c.index("static void prepare_frame("):c.index("/* PUBLISH.")]
        self.assertNotIn("VRAM", body, "prepare must not touch VRAM")

    def test_publish_is_placed_in_iwram(self):
        self.assertIn('__attribute__((section(".iwram"), noinline))\nstatic void publish_frame',
                      self.code())

    def test_the_dma_is_explicit_about_width_and_count(self):
        c = self.code()
        self.assertIn("0x84000000u | (words >> 1)", c, "enable | 32-bit, count in words")
        self.assertIn("REG_DMA3SAD", c)
        self.assertIn("REG_DMA3DAD", c)

    def test_the_wait_states_are_set(self):
        self.assertIn("REG_WAITCNT = 0x4317u;", self.code())

class RomStaticAudit(unittest.TestCase):
    """§42: what the stimulus must NOT contain."""

    @staticmethod
    def code():
        with open(ROM_SRC, encoding="utf-8") as f:
            import re
            t = f.read()
            t = re.sub(r"/\*.*?\*/", " ", t, flags=re.S)
            return re.sub(r"//[^\n]*", " ", t)

    def test_no_heap_no_filesystem_no_link_no_serial(self):
        c = self.code()
        for bad in ("malloc", "calloc", "free(", "fopen", "printf", "SIOCNT",
                    "REG_SIO", "0x04000120", "0x04000128", "0x04000134"):
            self.assertNotIn(bad, c, bad)

    def test_no_division_anywhere(self):
        """ARM7TDMI has no divide instruction; a `/` or `%` on a runtime value
        becomes a library call. Only shifts and compare-subtract are allowed."""
        import re
        c = self.code()
        # `/` and `%` may appear only in the fixed table initialiser? there is none.
        self.assertNotRegex(c, r"[^/*]/[^/*=]", "a division survived in the ROM source")
        self.assertNotIn("%", c, "a modulo survived in the ROM source")

    def test_the_vblank_path_uses_compare_and_subtract(self):
        c = self.code()
        self.assertIn("if (phase >= BAR_PERIOD) phase -= BAR_PERIOD", c)
        self.assertIn("if (bar_phase_base >= BAR_PERIOD) bar_phase_base = 0", c)

    def test_the_frozen_constants_are_the_contract(self):
        c = self.code()
        for needed in ("#define STRIP_BITS   54u", "#define PAYLOAD_BITS 38u",
                       "#define SYNC_BYTE    0xB2u", "#define SYM_ZERO 0x0000u",
                       "#define SYM_ONE  0x7FFFu", "#define SYM_FLAG 0x03E0u",
                       "#define BAR_PERIOD  31u", "#define BAR_PHASE_MUL 8u",
                       "#define CONTENT_W  128u", "#define STATUS_MARGIN_INIT 0x7Fu",
                       "#define VCOUNT_VBLANK_FIRST 160u", "#define VCOUNT_LAST         227u",
                       "#define VBLANK_TICKS        1309u"):
            self.assertIn(needed, c, needed)

    def test_the_status_is_snapshotted_before_the_update(self):
        """§31/§18: STATUS(f) certifies updates 0..f-1."""
        c = self.code()
        i_status = c.index("status = status_byte(&st);")
        # indexed-0002 split the update in two: the snapshot must still come
        # first, and now BOTH halves must follow it, so the whole frame -- all
        # 40 blocks and both diagnostic copies -- carries one immutable STATUS.
        i_update = c.index("prepare_frame(frame_id, status, prev_phase_base);", i_status)
        i_pub = c.index("publish_frame();", i_update)
        assert i_status < i_update < i_pub
        # and the MEASUREMENT of this frame's publication lands after it, so it
        # can only ever reach the NEXT frame's STATUS
        i_meas = c.index("status_measure(&st, vc0, vc1, elapsed);", i_pub)
        self.assertLess(i_status, i_update)
        self.assertLess(i_pub, i_meas)

    def test_the_fault_latch_is_sticky(self):
        c = self.code()
        self.assertNotIn("fault = 0;", c.split("for (;;)")[1],
                         "the latch must never be cleared inside the loop")
        body = c[c.index("static void status_measure("):c.index("static u8 status_byte(")]
        self.assertIn("s->fault = 1;", body)
        self.assertNotIn("s->fault = 0;", body,
                         "the validator must never clear FAULT once it is set")

    def test_interrupts_are_disabled_and_vblank_is_polled(self):
        c = self.code()
        self.assertIn("REG_IME = 0;", c)
        self.assertIn("while (REG_VCOUNT >= VCOUNT_VBLANK_FIRST) { }", c)
        self.assertIn("while (REG_VCOUNT <  VCOUNT_VBLANK_FIRST) { }", c)

    def test_the_timer_is_free_running_at_f_over_64(self):
        c = self.code()
        self.assertIn("REG_TM0CNT_H = 0x0081u", c)


class AnalyzerAdversarial(unittest.TestCase):
    """§44: every classification the contract names, driven deliberately."""

    @staticmethod
    def f(fid, st=0x40):
        return [istim.witness_words(fid, b, st) for b in range(istim.BLOCKS)]

    def run_ids(self, ids, st=0x40):
        return vindex.analyze_run([self.f(i, st) for i in ids])

    def test_contiguous(self):
        r = self.run_ids([10, 11, 12, 13, 14])
        self.assertEqual(r["verdict"], vindex.OBSERVED_CONTIGUOUS)
        self.assertEqual(r["counts"].get(vindex.OBSERVED_ID_CONTIGUOUS), 3)

    def test_gap(self):
        r = self.run_ids([10, 11, 15, 16, 17])
        self.assertEqual(r["verdict"], vindex.OBSERVED_DISCONTINUITY)
        self.assertIn((11, 15, vindex.OBSERVED_ID_GAP), r["decisive_transitions"])

    def test_duplicate(self):
        r = self.run_ids([10, 11, 11, 12, 13])
        self.assertIn((11, 11, vindex.OBSERVED_DUPLICATE_ID), r["decisive_transitions"])
        self.assertEqual(r["verdict"], vindex.OBSERVED_DISCONTINUITY)

    def test_reorder(self):
        r = self.run_ids([10, 11, 9, 12, 13])
        self.assertIn((11, 9, vindex.OBSERVED_REORDER), r["decisive_transitions"])

    def test_half_range_is_never_a_gap(self):
        half = 1 << 23
        r = self.run_ids([10, 10 + half, 10 + half + 1, 10 + half + 2])
        kinds = [c for _, _, c in r["decisive_transitions"]]
        self.assertIn(vindex.UNRESOLVED_HALF_RANGE, kinds)
        self.assertNotIn(vindex.OBSERVED_ID_GAP, kinds)

    def test_wrap(self):
        r = self.run_ids([0xFFFFFD, 0xFFFFFE, 0xFFFFFF, 0x000000, 0x000001])
        self.assertEqual(r["verdict"], vindex.OBSERVED_CONTIGUOUS)

    def test_mixed_block_ids(self):
        frames = [self.f(10), self.f(11), self.f(12)]
        frames[1][20] = istim.witness_words(999, 20, 0x40)
        r = vindex.analyze_run(frames)
        self.assertTrue(r["frames"][1]["mixed_block_ids"])
        self.assertEqual(r["frames"][1]["outcome"], vindex.MIXED_BLOCK_IDS)
        self.assertEqual(r["counts"].get(vindex.MIXED_BLOCK_IDS), 1)

    def test_wrong_block_index(self):
        frames = [self.f(10), self.f(11), self.f(12)]
        frames[1][5], frames[1][6] = frames[1][6], frames[1][5]
        r = vindex.analyze_run(frames)
        self.assertEqual(r["frames"][1]["outcome"], vindex.MISPLACED_BLOCK_INDEX)
        self.assertEqual(sorted(r["frames"][1]["misplaced_block_indices"]), [5, 6])

    def test_other_symbol(self):
        frames = [self.f(10), self.f(11)]
        frames[1][3][11] = 0x1234
        r = vindex.analyze_run(frames)
        self.assertEqual(r["frames"][1]["outcome"], vindex.INVALID_CANONICAL_STRIP)
        self.assertEqual(r["frames"][1]["invalid_reasons"][3], "symbol")

    def test_wrong_sync(self):
        frames = [self.f(10), self.f(11)]
        w = frames[1][7]
        w[0] = istim.ONE if w[0] == istim.ZERO else istim.ZERO
        r = vindex.analyze_run(frames)
        self.assertEqual(r["frames"][1]["invalid_reasons"][7], "sync")

    def test_wrong_crc(self):
        frames = [self.f(10), self.f(11)]
        w = frames[1][9]
        w[30] = istim.ONE if w[30] == istim.ZERO else istim.ZERO
        r = vindex.analyze_run(frames)
        self.assertEqual(r["frames"][1]["invalid_reasons"][9], "crc")

    def test_unexpected_bit15_is_reported_and_changes_nothing(self):
        frames = [self.f(10), self.f(11)]
        frames[1][4][17] |= 0x8000
        frames[1][4][40] |= 0x8000
        r = vindex.analyze_run(frames)
        self.assertEqual(r["frames"][1]["outcome"], vindex.FRAME_OK)
        self.assertEqual(r["frames"][1]["frame_id"], 11)
        self.assertIn((4, 17), r["frames"][1]["flag15"])
        self.assertIn((4, 40), r["frames"][1]["flag15"])

    def test_fault_invalidates_the_decisive_claim(self):
        frames = [self.f(10), self.f(11, 0x40 | istim.STATUS_FAULT_MASK),
                  self.f(12), self.f(13)]
        r = vindex.analyze_run(frames)
        self.assertTrue(r["fault_seen"])
        self.assertEqual(r["verdict"], vindex.STIMULUS_INVALID)

    def test_the_status_delay_shortens_the_decisive_set(self):
        r = self.run_ids([100, 101, 102, 103])
        self.assertEqual(r["first_observed"], 100)
        self.assertEqual(r["last_observed"], 103)
        self.assertEqual(r["first_decisive"], 100)
        self.assertEqual(r["last_decisive"], 102)
        self.assertEqual(len(r["decisive_transitions"]), 2)

    def test_too_few_intact_frames(self):
        r = self.run_ids([7])
        self.assertEqual(r["verdict"], vindex.INCONCLUSIVE_TOO_FEW)

    def test_the_report_never_says_dropped(self):
        r = self.run_ids([10, 11, 15, 16])
        text = vindex.format_report(r).lower()
        self.assertNotIn("dropped", text)
        self.assertNotIn("source loss", text)
