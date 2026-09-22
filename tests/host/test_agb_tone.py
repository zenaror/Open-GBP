"""
tests/host/test_agb_tone.py — GitHub Issue #65: `agb-tone` against §V9's frozen
specification, and against the three requirements that are easy to get wrong.

THE ROM'S OWN CODE IS RUN, not read. The pure state machine and the picture are
compiled FOR THE HOST with the two hardware bases relocated — the only thing a
host test may move — exactly as `test_agb_indexed.py` does it, so what is
checked below is the code that will be on the cartridge.

WHAT CANNOT BE TESTED HERE, AND IS SAID RATHER THAN IMPLIED: **no sound**. The
host has no APU, so what these tests verify about the audio is the REGISTER
VALUES the ROM writes and the ORDER it writes them in, against §V9.3.2's table
and GBATEK's field layout. Whether a real AGB then emits 128.0 Hz is what the
physical run is for, and nothing here can stand in for it.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v9tone  # noqa: E402

ROM_SRC = os.path.join(ROOT, "stimulus", "agb-tone", "source", "main.c")
ROM_MK = os.path.join(ROOT, "stimulus", "agb-tone", "Makefile")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
TOP_MK = os.path.join(ROOT, "Makefile")

SCREEN_W, SCREEN_H = 240, 160

HARNESS = r'''
#include <stdio.h>
#include <string.h>

static unsigned char fake_vram[96 * 1024];
static unsigned char fake_io[1024];

#define AGB_IO_BASE   ((unsigned long)fake_io)
#define AGB_VRAM_BASE ((unsigned long)fake_vram)
#define main rom_main_unused
#include "main.c"
#undef main

static unsigned short io16(unsigned off) { return *(volatile unsigned short *)(fake_io + off); }

/* every APU register the ROM may touch, printed after each step so the test
 * sees the DEVICE's state and not the program's intention */
static void dump_apu(const char *tag)
{
    printf("APU %s 60=%04x 62=%04x 64=%04x 80=%04x 82=%04x 84=%04x\n", tag,
           io16(0x060), io16(0x062), io16(0x064), io16(0x080), io16(0x082), io16(0x084));
}

static void dump_state(struct tone_state *s)
{
    printf("STATE presses=%u freq_n=%u sounding=%u bg=%04x boxes=%u\n",
           s->presses, s->freq_n, s->sounding, tone_background(s), tone_boxes_filled(s));
}

/* the picture, as a coarse signature a test can compare: the colour at the
 * centre of each of the four boxes, plus the background at a corner */
static void dump_pixels(void)
{
    unsigned i;
    unsigned short *v = (unsigned short *)fake_vram;
    printf("PIX bg=%04x", v[2 * 240 + 2]);
    for (i = 0; i < 4; i++) {
        unsigned x = 12 + i * (40 + 16) + 20, y = 56 + 24;
        printf(" box%u=%04x", i, v[y * 240 + x]);
    }
    printf("\n");
}

int main(void)
{
    struct tone_state st;
    unsigned short seq[] = {
        0x03FF,          /* nothing held */
        0x03FE,          /* A down   (bit 0 low)  -> press 1 */
        0x03FF,          /* A up                  -> NOT a press */
        0x03FE,          /* A down                -> press 2 */
        0x03FF,
        0x03FE,          /* press 3 */
        0x03FF,
        0x03FE,          /* press 4 */
        0x03FF,
        0x03FE,          /* press 5: more than four */
    };
    unsigned i;
    tone_init(&st);
    apu_silence();
    dump_apu("reset");
    tone_paint(&st);
    dump_state(&st);
    dump_pixels();
    for (i = 0; i < sizeof seq / sizeof seq[0]; i++) {
        int pressed = tone_step(&st, seq[i]);
        if (pressed) { apu_play(st.freq_n); tone_paint(&st); }
        printf("STEP %u key=%04x pressed=%d\n", i, seq[i], pressed);
        dump_state(&st);
        if (pressed) { dump_apu("after"); dump_pixels(); }
    }
    /* a DIFFERENT key must count as a press too: the capture arms on any bit */
    tone_init(&st);
    tone_step(&st, 0x03FF);
    printf("OTHERKEY pressed=%d\n", tone_step(&st, 0x03FD));   /* B down */
    dump_state(&st);
    /* two keys going down in ONE sample is ONE press, as it is one rising edge
     * of the word for the capture */
    tone_init(&st);
    tone_step(&st, 0x03FF);
    printf("TWOKEYS pressed=%d\n", tone_step(&st, 0x03FC));
    dump_state(&st);
    return 0;
}
'''


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def _bounded(t, start):
    """From `start`'s heading to the NEXT top-level V heading, never to EOF.
    §V8's slices ran to the end of the document and had silently been reading
    §V9 for a whole checkpoint; §V10 is what made it visible. The fix is to
    BOUND the slice, not to move a pin -- the lesson of Issue #50."""
    i = t.index(start)
    j = t.find("\n## V", i + 1)
    return t[i:j] if j >= 0 else t[i:]


def v9_part():
    t = read(HW)
    return _bounded(t, "\n## V9 — GBP-AUDIO-002")


def define(src, name):
    m = re.search(r"^#define\s+%s\s+(\S+)" % re.escape(name), src, re.M)
    assert m, name
    return m.group(1)


def num(s):
    s = s.rstrip("uUlL")
    return int(s, 16) if s.lower().startswith("0x") else int(s)


def run_rom():
    if not os.path.exists("/usr/bin/cc") and not os.path.exists("/usr/bin/gcc"):
        return None
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "harness.c")
        with open(src, "w") as f:
            f.write(HARNESS)
        exe = os.path.join(d, "rom")
        cc = subprocess.run(["cc", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Wno-unused-function",
                             "-I", os.path.dirname(ROM_SRC), "-o", exe, src],
                            capture_output=True, text=True)
        if cc.returncode != 0:
            raise AssertionError("the ROM does not compile for the host:\n" + cc.stderr[-4000:])
        r = subprocess.run([exe], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        return r.stdout


class TheRegistersAreSectionV9sTable(unittest.TestCase):
    """The audio half, which is all a host can check — and it says so."""

    def test_the_two_notes_are_the_pre_registrations(self):
        src = read(ROM_SRC)
        self.assertEqual(num(define(src, "TONE_N1")), v9tone.N1)
        self.assertEqual(num(define(src, "TONE_N2")), v9tone.N2)
        self.assertEqual(num(define(src, "TONE_N1")), 1024)
        self.assertEqual(num(define(src, "TONE_N2")), 1792)
        # and the frequencies they mean, recomputed from GBATEK's formula
        self.assertAlmostEqual(v9tone.freq_hz(num(define(src, "TONE_N1"))), 128.0, places=9)
        self.assertAlmostEqual(v9tone.freq_hz(num(define(src, "TONE_N2"))), 512.0, places=9)

    def test_the_envelope_never_decays_and_the_length_flag_is_never_set(self):
        src = read(ROM_SRC)
        cnt_h = num(define(src, "TONE_CNT_H"))
        self.assertEqual((cnt_h >> 12) & 0xF, 15, "initial envelope volume")
        self.assertEqual((cnt_h >> 8) & 0x7, 0, "envelope STEP TIME must be 0: no decay")
        self.assertEqual((cnt_h >> 6) & 0x3, 2, "duty 50 %")
        self.assertEqual(cnt_h & 0x3F, 0, "length data")
        restart = num(define(src, "TONE_RESTART"))
        self.assertEqual(restart, 0x8000)
        self.assertEqual(restart & 0x4000, 0, "bit 14, the LENGTH FLAG, must never be set")
        # the checker's bug, named in the source so the reason survives
        self.assertIn("the LENGTH FLAG is never set", read(ROM_SRC))

    def test_soundcnt_h_is_written_which_the_checker_never_did(self):
        src = read(ROM_SRC)
        self.assertEqual(num(define(src, "TONE_CNT_RATIO")) & 0x3, 2, "PSG-to-output ratio 100 %")
        self.assertIn("SOUNDCNT_H IS WRITTEN", src)
        self.assertIn("§V8.6", src)

    def test_no_other_apu_register_is_touched(self):
        src = read(ROM_SRC)
        regs = set(re.findall(r"REG_SOUND\w*", src))
        self.assertEqual(regs, {"REG_SOUND1CNT_L", "REG_SOUND1CNT_H", "REG_SOUND1CNT_X",
                                "REG_SOUNDCNT_L", "REG_SOUNDCNT_H", "REG_SOUNDCNT_X"})
        for forbidden in ("0x068", "0x06C", "0x070", "0x078", "0x090", "0x0A0", "0x0A4"):
            self.assertNotIn(forbidden, src, "a second sound channel or the FIFOs")

    def test_what_a_host_cannot_check_is_stated(self):
        self.assertIn("no sound", __doc__)
        self.assertIn("Whether a real AGB then emits 128.0 Hz is what the\nphysical run is for", __doc__)


class TheRomRunsOnTheHostAndBehaves(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.out = run_rom()
        if cls.out is None:
            raise unittest.SkipTest("no host compiler")

    def apu(self, tag):
        m = re.findall(r"APU %s 60=(\w+) 62=(\w+) 64=(\w+) 80=(\w+) 82=(\w+) 84=(\w+)" % tag, self.out)
        return [tuple(int(x, 16) for x in g) for g in m]

    def states(self):
        return [(int(a), int(b), int(c), int(d, 16), int(e)) for a, b, c, d, e in
                re.findall(r"STATE presses=(\d+) freq_n=(\d+) sounding=(\d+) bg=(\w+) boxes=(\d+)", self.out)]

    def test_it_is_SILENT_until_the_first_press(self):
        """§V9's control window is armed BEFORE any press and RUN 30 showed the
        window is not silent at rest: if this ROM emitted from reset, that
        control would stop being a resting-state observation."""
        reset = self.apu("reset")
        self.assertEqual(len(reset), 1)
        self.assertEqual(reset[0], (0, 0, 0, 0, 0, 0), "the APU is not silent before the first press")
        first = self.states()[0]
        self.assertEqual(first[0], 0, "presses")
        self.assertEqual(first[2], 0, "sounding")

    def test_a_press_is_a_key_going_DOWN_and_the_release_is_not_a_press(self):
        steps = re.findall(r"STEP (\d+) key=(\w+) pressed=(\d)", self.out)
        got = [(int(i), int(p)) for i, _k, p in steps]
        # the sequence is: nothing, down, up, down, up, down, up, down, up, down
        self.assertEqual([p for _i, p in got], [0, 1, 0, 1, 0, 1, 0, 1, 0, 1])

    def test_the_notes_alternate_F1_F2_F1_F2(self):
        seen = [(s[0], s[1]) for s in self.states() if s[0] > 0]
        by_press = {}
        for presses, n in seen:
            by_press[presses] = n
        self.assertEqual(by_press[1], v9tone.N1)
        self.assertEqual(by_press[2], v9tone.N2)
        self.assertEqual(by_press[3], v9tone.N1)
        self.assertEqual(by_press[4], v9tone.N2)
        self.assertEqual(by_press[5], v9tone.N1, "the alternation continues rather than stopping")

    def test_the_device_gets_the_right_words_in_the_right_order(self):
        after = self.apu("after")
        self.assertEqual(len(after), 5)
        src = read(ROM_SRC)
        cnt_h, mix, ratio, master = (num(define(src, x)) for x in
                                     ("TONE_CNT_H", "TONE_CNT_MIX", "TONE_CNT_RATIO", "TONE_MASTER_ON"))
        for k, regs in enumerate(after):
            s1l, s1h, s1x, cl, ch, cx = regs
            self.assertEqual(s1l, 0, "no sweep: the note must not glide")
            self.assertEqual(s1h, cnt_h)
            self.assertEqual(cl, mix)
            self.assertEqual(ch, ratio)
            self.assertEqual(cx, master)
            n = v9tone.N1 if (k + 1) % 2 else v9tone.N2
            self.assertEqual(s1x, 0x8000 | n, "restart | n, with the length flag clear")
            self.assertEqual(s1x & 0x4000, 0)

    def test_the_counter_is_two_independent_readings_of_one_number(self):
        vals = [[int(x, 16) for x in re.findall(r"=(\w+)", line)]
                for line in self.out.splitlines() if line.startswith("PIX ")]
        self.assertEqual(len(vals), 6, "one picture at rest and one per press")
        src = read(ROM_SRC)
        on, off = num(define(src, "COL_BOX_ON")), num(define(src, "COL_BOX_OFF"))
        colours = [num(define(src, c)) for c in
                   ("COL_BLACK", "COL_RED", "COL_GREEN", "COL_BLUE", "COL_YELLOW", "COL_MAGENTA")]
        for count, row in enumerate(vals):
            bg, boxes = row[0], row[1:]
            self.assertEqual(bg, colours[count], "the background must change with the count")
            self.assertEqual(boxes, [on] * min(count, 4) + [off] * (4 - min(count, 4)),
                             "the boxes fill left to right, %d filled" % min(count, 4))
        # the two channels never coincide, so a missed fill is caught by the colour
        self.assertEqual(len(set(colours)), 6)
        self.assertNotIn(on, colours)

    def test_more_than_four_presses_is_visible(self):
        vals = [[int(x, 16) for x in re.findall(r"=(\w+)", line)]
                for line in self.out.splitlines() if line.startswith("PIX ")]
        src = read(ROM_SRC)
        self.assertEqual(vals[5][0], num(define(src, "COL_MAGENTA")))
        self.assertEqual(vals[5][1:], [num(define(src, "COL_BOX_ON"))] * 4)

    def test_any_key_counts_and_two_keys_at_once_are_one_press(self):
        self.assertIn("OTHERKEY pressed=1", self.out)
        self.assertIn("TWOKEYS pressed=1", self.out)
        tail = self.out[self.out.index("TWOKEYS"):]
        m = re.search(r"STATE presses=(\d+)", tail)
        self.assertEqual(int(m.group(1)), 1, "two keys in one sample is ONE rising edge of the word")


class ThePlumbingAndTheRecord(unittest.TestCase):

    def test_the_makefile_identity(self):
        mk = read(ROM_MK)
        self.assertEqual(re.search(r"^APP_NAME\s+:=\s+(\S+)", mk, re.M).group(1), "agb-tone")
        self.assertEqual(re.search(r"^STIM_ID\s+:=\s+(\S+)", mk, re.M).group(1), "tone-0001")
        self.assertIn("NOT PHYSICALLY EXECUTED", mk)
        self.assertIn("§V3.7 route 1", mk)

    def test_the_root_makefile_builds_it(self):
        t = read(TOP_MK)
        self.assertIn("STIM_TONE_ROM := build/stimulus/agb-tone/agb-tone.gba", t)
        self.assertIn("stimulus-tone:", t)
        self.assertIn(" stimulus-tone ", t[t.index(".PHONY:"):t.index(".PHONY:") + 600])

    def test_v9_is_unchanged_by_the_build(self):
        """#65 does not touch §V9. The notes the ROM carries must be §V9's, and
        the ROM is what moved to meet them."""
        s = plain(v9_part())
        self.assertIn("F1 1024 1024 128.0 Hz exact 128 bytes 32.0", s)
        self.assertIn("F2 1792 256 512.0 Hz exact 32 bytes 128.0", s)

    def test_the_identity_the_record_states_is_the_file_that_was_built(self):
        """§V9.14.1's hashes, against the files when they exist."""
        import hashlib
        s = plain(v9_part())
        canon = os.path.join(ROOT, "build", "stimulus", "agb-tone", "agb-tone.gba")
        deliv = os.path.join(ROOT, "build", "physical", "agb-tone-cart.gba")
        self.assertIn("e14ec62d67fa362274b639f9f173dbde02a84aefa185224998dd928628c6df48", s)
        self.assertIn("ff5298f08c4dd7665981dbe39d0eb5b282a1bd122aa60a31923cab967a3844a0", s)
        self.assertIn("1 404 B", s)
        for path, want in ((canon, "e14ec62d67fa362274b639f9f173dbde02a84aefa185224998dd928628c6df48"),
                           (deliv, "ff5298f08c4dd7665981dbe39d0eb5b282a1bd122aa60a31923cab967a3844a0")):
            if not os.path.exists(path):
                continue
            with open(path, "rb") as f:
                data = f.read()
            self.assertEqual(hashlib.sha256(data).hexdigest(), want, path)
            self.assertEqual(len(data), 1404, path)

    def test_the_appendix_says_what_a_host_cannot_check(self):
        s = plain(v9_part()[v9_part().index("### V9.14 "):])
        self.assertIn("There is no sound here", s)
        self.assertIn("Whether a real AGB then emits 128.0 Hz is exactly what the physical run is for", s)
        self.assertIn("It authorises no hardware and no staging", s)
        self.assertIn("the ROM is the only new artifact in this entire run", s)

    def test_v9tone_is_untouched(self):
        base = subprocess.run(["git", "-C", ROOT, "log", "--format=%H", "-1", "--grep",
                               "Issue #64 -- agb-tone designed and pre-registered"],
                              capture_output=True, text=True).stdout.strip()
        if not base:
            self.skipTest("the commit that introduced tools/v9tone.py is not in this checkout")
        then = subprocess.run(["git", "-C", ROOT, "show", "%s:tools/v9tone.py" % base],
                              capture_output=True, text=True, check=True).stdout
        self.assertEqual(read(os.path.join(ROOT, "tools", "v9tone.py")), then,
                         "tools/v9tone.py was edited by the build it was written before")


if __name__ == "__main__":
    unittest.main()
