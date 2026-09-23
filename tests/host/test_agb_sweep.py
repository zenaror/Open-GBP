"""tests/host/test_agb_sweep.py — GitHub Issue #70: `agb-sweep` against §V11's
frozen specification, and against the one requirement §V11 could not have:
**the screen must name the axis**.

THE ROM'S OWN CODE IS RUN, not read. The state machine and the picture are
compiled FOR THE HOST with the two hardware bases relocated — the only thing a
host test may move — exactly as `test_agb_tone.py` and `test_agb_indexed.py` do
it, so what is checked below is the code that will be on the cartridge. The
schedules are compared against `tools/v11sweep.py`, the frozen construction,
rather than against numbers retyped here: the ROM and the analysis must agree by
construction or the run measures something the ingestion is not expecting.

WHAT CANNOT BE TESTED HERE, AND IS SAID RATHER THAN IMPLIED: **no sound**. The
host has no APU, so what is verified about the audio is the REGISTER VALUES the
ROM writes and the ORDER it writes them in, against §V11.3's schedules and
GBATEK's field layout. Whether a real AGB then emits 128.0 Hz at envelope
volume 7 is what the physical run is for, and nothing here can stand in for it.
**Nor can a host test say the screen is legible on his converter** — geometry is
checked, visibility is not.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v11sweep  # noqa: E402

ROM_SRC = os.path.join(ROOT, "stimulus", "agb-sweep", "source", "main.c")
ROM_MK = os.path.join(ROOT, "stimulus", "agb-sweep", "Makefile")
TONE_SRC = os.path.join(ROOT, "stimulus", "agb-tone", "source", "main.c")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
TOP_MK = os.path.join(ROOT, "Makefile")

SCREEN_W, SCREEN_H = 240, 160
WHITE, GREY, BLACK, RED = 0x7FFF, 0x2108, 0x0000, 0x001F

HARNESS = r'''
#include <stdio.h>

static unsigned char fake_vram[96 * 1024];
static unsigned char fake_io[1024];

#define AGB_IO_BASE   ((unsigned long)fake_io)
#define AGB_VRAM_BASE ((unsigned long)fake_vram)
#define main rom_main_unused
#include "main.c"
#undef main

static unsigned short io16(unsigned off) { return *(volatile unsigned short *)(fake_io + off); }
static unsigned short px(unsigned x, unsigned y)
{ return ((unsigned short *)fake_vram)[y * 240u + x]; }

static void dump_apu(const char *tag)
{
    printf("APU %s 60=%04x 62=%04x 64=%04x 80=%04x 82=%04x 84=%04x\n", tag,
           io16(0x060), io16(0x062), io16(0x064), io16(0x080), io16(0x082), io16(0x084));
}

static void dump_marks(void) { printf("MARKS %04x\n", apu_marks); }

static void dump_state(struct sweep_state *s)
{
    printf("STATE presses=%u axis=%u spoiled=%u f_step=%u v_step=%u n=%u vol=%u sounding=%u bg=%04x\n",
           s->presses, s->axis, s->spoiled, s->f_step, s->v_step,
           sweep_freq_n(s), sweep_volume(s), s->sounding, sweep_background(s));
}

/* the picture as a signature: the background at a corner, the TOP and BOTTOM
 * half of each box, and both rails */
static void dump_pixels(void)
{
    unsigned i;
    printf("PIX bg=%04x railF=%04x railV=%04x bands=%04x/%04x",
           px(2u, 26u), px(120u, 8u), px(120u, 152u), px(4u, 40u), px(4u, 56u));
    for (i = 0; i < 4; i++) {
        unsigned x = 16u + i * (40u + 16u) + 20u;
        printf(" box%u=%04x/%04x", i, px(x, 32u + 24u), px(x, 32u + 48u + 24u));
    }
    printf("\n");
}

static void drive(const char *tag, const unsigned short *seq, unsigned n)
{
    struct sweep_state st;
    unsigned i;
    sweep_init(&st);
    apu_silence();
    dump_apu("reset");
    sweep_paint(&st);
    printf("RUN %s\n", tag);
    dump_state(&st);
    dump_pixels();
    for (i = 0; i < n; i++) {
        int pressed = sweep_step(&st, seq[i]);
        if (pressed) {
            if (!st.spoiled) apu_play(sweep_freq_n(&st), sweep_volume(&st));
            sweep_paint(&st);
        }
        printf("STEP %u key=%04x pressed=%d\n", i, seq[i], pressed);
        dump_state(&st);
        if (pressed) { dump_apu("after"); dump_marks(); dump_pixels(); }
    }
}

int main(void)
{
    /* 0x03FF = nothing held; a bit LOW means that key is down */
    static const unsigned short b_run[] = {
        0x03FF, 0x03FD, 0x03FF, 0x03FD, 0x03FF, 0x03FD, 0x03FF, 0x03FD, 0x03FF, 0x03FD };
    static const unsigned short a_run[] = {
        0x03FF, 0x03FE, 0x03FF, 0x03FE, 0x03FF, 0x03FE, 0x03FF, 0x03FE };
    static const unsigned short mixed[] = { 0x03FF, 0x03FD, 0x03FF, 0x03FE, 0x03FF, 0x03FD };
    static const unsigned short both[]  = { 0x03FF, 0x03FC };
    static const unsigned short other[] = { 0x03FF, 0x037F };   /* START */
    drive("B", b_run, sizeof b_run / sizeof b_run[0]);
    drive("A", a_run, sizeof a_run / sizeof a_run[0]);
    drive("MIXED", mixed, sizeof mixed / sizeof mixed[0]);
    drive("BOTH", both, sizeof both / sizeof both[0]);
    drive("OTHER", other, sizeof other / sizeof other[0]);
    return 0;
}
'''


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def _bounded(t, start):
    i = t.index(start)
    j = t.find("\n## V", i + 1)
    return t[i:j] if j >= 0 else t[i:]


def v11_part():
    return _bounded(read(HW), "\n## V11 — GBP-AUDIO-003")


def define(src, name):
    m = re.search(r"^#define\s+%s\s+(\S+)" % re.escape(name), src, re.M)
    assert m, name
    return m.group(1)


def num(s):
    s = s.rstrip("uUlL")
    return int(s, 16) if s.lower().startswith("0x") else int(s)


_OUT = []


def run_rom():
    if _OUT:
        return _OUT[0]
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "harness.c")
        with open(src, "w") as f:
            f.write(HARNESS)
        exe = os.path.join(d, "rom")
        cc = subprocess.run(["cc", "-std=gnu11", "-O1", "-Wall", "-Wextra",
                             "-Wno-unused-function", "-I", os.path.dirname(ROM_SRC),
                             "-o", exe, src], capture_output=True, text=True)
        if cc.returncode != 0:
            raise AssertionError("the ROM does not compile for the host:\n" + cc.stderr[-4000:])
        r = subprocess.run([exe], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
    _OUT.append(r.stdout)
    return _OUT[0]


def block(out, tag):
    """The lines of one drive() run."""
    i = out.index("RUN %s\n" % tag)
    j = out.find("\nRUN ", i + 1)
    return out[i:j] if j >= 0 else out[i:]


def states(b):
    return re.findall(r"^STATE (.*)$", b, re.M)


def fields(line):
    return dict((k, v) for k, v in (kv.split("=") for kv in line.split()))


def pixels(b):
    return re.findall(r"^PIX (.*)$", b, re.M)


def pressed_states(b):
    """Only the STATE lines that follow a step which WAS a press. A STATE is
    printed after every sample, so filtering on `sounding` would also pick up
    the releases in between."""
    out, lines = [], b.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^STEP \d+ key=\w+ pressed=1$", line)
        if m and i + 1 < len(lines) and lines[i + 1].startswith("STATE "):
            out.append(fields(lines[i + 1][len("STATE "):]))
    return out


# ------------------------------------------------ the schedules are §V11's

class TheSchedulesAreTheFrozenOnes(unittest.TestCase):
    """The ROM and tools/v11sweep.py must agree BY CONSTRUCTION: a run whose
    instrument and whose analysis disagree measures something nobody
    pre-registered."""

    def test_the_four_notes_are_tools_v11sweeps(self):
        src = read(ROM_SRC)
        m = re.search(r"SWEEP_FREQ_N\[SWEEP_STEPS\] = \{([^}]*)\}", src)
        self.assertTrue(m)
        got = tuple(num(x.strip()) for x in m.group(1).split(",") if x.strip())
        self.assertEqual(got, v11sweep.FREQUENCY_N)
        self.assertEqual([v11sweep.frequency_hz(n) for n in got],
                         [128.0, 512.0, 256.0, 1024.0])

    def test_the_four_volumes_are_tools_v11sweeps(self):
        src = read(ROM_SRC)
        m = re.search(r"SWEEP_VOLUME\[SWEEP_STEPS\] = \{([^}]*)\}", src)
        self.assertTrue(m)
        got = tuple(num(x.strip()) for x in m.group(1).split(",") if x.strip())
        self.assertEqual(got, v11sweep.AMPLITUDES)

    def test_the_document_carries_the_same_two_schedules(self):
        s = v11_part()
        self.assertIn("n = 1024 -> 1792 -> 1536 -> 1920", s)
        self.assertIn("initial volume 15 -> 11 -> 7 -> 3", s)


class TheRegistersAreSectionV11sTable(unittest.TestCase):

    def test_the_length_flag_is_never_set_and_the_envelope_never_decays(self):
        src = read(ROM_SRC)
        self.assertEqual(num(define(src, "SWEEP_RESTART")), 0x8000)
        # bit 14, the length flag, is never set anywhere in the CODE. Comments may name
        # register addresses like 0x4000080, which is why the search strips them first
        # (Issue #73 added GBATEK's 4000060h..4000081h range to a comment).
        code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        code = re.sub(r"//[^\n]*", "", code)
        self.assertNotIn("0x4000", code)
        # SOUND1CNT_H = volume<<12 | 0x0080: direction 0, STEP TIME 0, duty 2
        self.assertIn("(((u16)(v) << 12) | 0x0080u)", src)
        for volume in v11sweep.AMPLITUDES:
            word = (volume << 12) | 0x0080
            self.assertEqual(word & 0x0700, 0, "step time must be 0 at volume %d" % volume)
            self.assertEqual((word >> 6) & 3, 2, "duty must be 50 %% at volume %d" % volume)
            self.assertEqual(word >> 12, volume)

    def test_volume_15_reproduces_agb_tones_word_exactly(self):
        """A four-press A run must put the APU in RUN 31's state, or the 'a
        pure-A run is a superset of RUN 31' argument is not true."""
        self.assertEqual((15 << 12) | 0x0080, num(define(read(TONE_SRC), "TONE_CNT_H")))

    def test_soundcnt_h_is_written_and_the_mix_matches_agb_tone(self):
        src, tone = read(ROM_SRC), read(TONE_SRC)
        self.assertEqual(num(define(src, "SWEEP_CNT_RATIO")), num(define(tone, "TONE_CNT_RATIO")))
        self.assertEqual(num(define(src, "SWEEP_CNT_MIX")), num(define(tone, "TONE_CNT_MIX")))
        self.assertEqual(num(define(src, "SWEEP_MASTER_ON")), num(define(tone, "TONE_MASTER_ON")))

    def test_no_other_apu_register_is_touched(self):
        src = read(ROM_SRC)
        touched = set(re.findall(r"REG_SOUND\w*", src))
        self.assertEqual(touched, {"REG_SOUND1CNT_L", "REG_SOUND1CNT_H", "REG_SOUND1CNT_X",
                                   "REG_SOUNDCNT_L", "REG_SOUNDCNT_H", "REG_SOUNDCNT_X"})

    def test_what_a_host_cannot_check_is_stated(self):
        self.assertIn("no sound", __doc__)
        self.assertIn("Nor can a host test say the screen is legible", __doc__)


# --------------------------------------------------- the ROM, actually run

class TheRomRunsOnTheHostAndBehaves(unittest.TestCase):

    def test_it_is_SILENT_until_the_first_press(self):
        out = run_rom()
        reset = re.findall(r"^APU reset (.*)$", out, re.M)
        self.assertTrue(reset)
        for line in reset:
            for kv in line.split():
                self.assertTrue(kv.endswith("=0000"), "APU not clear at reset: " + line)
        first = states(block(out, "B"))[0]
        self.assertEqual(fields(first)["sounding"], "0")

    def test_a_press_is_a_key_going_DOWN_and_the_release_is_not(self):
        b = block(run_rom(), "B")
        steps = re.findall(r"^STEP \d+ key=(\w+) pressed=(\d)$", b, re.M)
        self.assertEqual([p for _, p in steps], list("0101010101"))

    def test_the_B_run_walks_the_volumes_and_never_leaves_128_hz(self):
        pressed = pressed_states(block(run_rom(), "B"))
        self.assertEqual([int(x["vol"]) for x in pressed], [15, 11, 7, 3, 3])
        for x in pressed:
            self.assertEqual(int(x["n"]), v11sweep.FREQUENCY_N[0])

    def test_the_A_run_walks_the_notes_and_never_leaves_volume_15(self):
        pressed = pressed_states(block(run_rom(), "A"))
        self.assertEqual([int(x["n"]) for x in pressed], list(v11sweep.FREQUENCY_N))
        for x in pressed:
            self.assertEqual(int(x["vol"]), v11sweep.AMPLITUDES[0])

    def test_the_schedules_HOLD_at_the_last_entry(self):
        """§V11.3: a fifth press must change nothing that is sounding."""
        b = block(run_rom(), "B")
        st = [fields(x) for x in states(b)]
        last = st[-1]
        self.assertEqual(last["presses"], "5")
        self.assertEqual(int(last["vol"]), v11sweep.AMPLITUDES[-1])
        self.assertEqual(int(last["v_step"]), 3)

    def test_the_device_gets_the_right_words_in_the_right_order(self):
        b = block(run_rom(), "B")
        after = re.findall(r"^APU after (.*)$", b, re.M)
        self.assertEqual(len(after), 5)
        for i, line in enumerate(after):
            f = fields(line)
            volume = v11sweep.AMPLITUDES[min(i, 3)]
            self.assertEqual(f["62"], "%04x" % ((volume << 12) | 0x0080))
            self.assertEqual(f["64"], "%04x" % (0x8000 | v11sweep.FREQUENCY_N[0]))
            self.assertEqual(f["84"], "0080")     # master enable, written first
            self.assertEqual(f["82"], "0002")     # SOUNDCNT_H, 100 %
            self.assertEqual(f["80"], "1177")
            self.assertEqual(f["60"], "0000")     # no sweep: the note must not glide

    def test_the_master_enable_is_written_before_any_channel_register(self):
        src = read(ROM_SRC)
        body = src[src.index("static u16 apu_apply"):]
        self.assertLess(body.index("REG_SOUNDCNT_X"), body.index("REG_SOUND1CNT_H"))


# ------------------------------------------- THE SCREEN NAMES THE AXIS

class TheScreenNamesTheAxisAndNotOnlyTheCount(unittest.TestCase):
    """Issue #70's one new requirement. §V11.8 refuses a wrong-button run only
    AFTER the trip; this is what lets him see it at the first press."""

    def test_at_the_FIRST_press_the_B_run_fills_the_LOWER_half(self):
        p = pixels(block(run_rom(), "B"))
        first = fields(p[1])                       # p[0] is before any press
        self.assertEqual(first["box0"], "%04x/%04x" % (GREY, WHITE))
        self.assertEqual(first["railV"], "%04x" % WHITE)
        self.assertNotEqual(first["railF"], "%04x" % WHITE)

    def test_at_the_FIRST_press_the_A_run_fills_the_UPPER_half(self):
        p = pixels(block(run_rom(), "A"))
        first = fields(p[1])
        self.assertEqual(first["box0"], "%04x/%04x" % (WHITE, GREY))
        self.assertEqual(first["railF"], "%04x" % WHITE)
        self.assertNotEqual(first["railV"], "%04x" % WHITE)

    def test_the_two_runs_are_distinguishable_at_every_press(self):
        pb, pa = pixels(block(run_rom(), "B")), pixels(block(run_rom(), "A"))
        for i in range(1, 5):
            self.assertNotEqual(fields(pb[i])["box0"], fields(pa[i])["box0"])
            self.assertNotEqual(fields(pb[i])["railV"], fields(pa[i])["railV"])

    def test_the_background_still_carries_the_count(self):
        p = pixels(block(run_rom(), "B"))
        self.assertEqual([fields(x)["bg"] for x in p[:5]],
                         ["0000", "001f", "03e0", "7c00", "03ff"])

    def test_more_than_four_presses_is_MAGENTA_exactly_as_in_agb_tone(self):
        p = pixels(block(run_rom(), "B"))
        self.assertEqual(fields(p[5])["bg"], "7c1f")
        self.assertEqual(num(define(read(ROM_SRC), "COL_MAGENTA")),
                         num(define(read(TONE_SRC), "COL_MAGENTA")))

    def test_the_half_is_as_big_as_agb_tones_whole_box(self):
        """Legibility is not testable on a host; the GEOMETRY that was argued
        for is. A filled half must be 40x48, the block he already read."""
        src = read(ROM_SRC)
        self.assertEqual(num(define(src, "BOX_W")), 40)
        self.assertEqual(num(define(src, "BOX_H")), 96)
        self.assertEqual(num(define(src, "BOX_H")) // 2, 48)
        tone = read(TONE_SRC)
        self.assertEqual(num(define(tone, "BOX_W")), 40)
        self.assertEqual(num(define(tone, "BOX_H")), 48)

    def test_the_boxes_fit_the_screen_and_are_centred(self):
        src = read(ROM_SRC)
        n, w, gap, x0 = (num(define(src, k)) for k in ("BOX_N", "BOX_W", "BOX_GAP", "BOX_X0"))
        span = n * w + (n - 1) * gap
        self.assertEqual(span, 208)
        self.assertEqual(x0, (SCREEN_W - span) // 2)
        self.assertLessEqual(num(define(src, "BOX_Y")) + num(define(src, "BOX_H")),
                             SCREEN_H - num(define(src, "RAIL_H")))


class ASpoiledRunIsLOUDAndSTICKY(unittest.TestCase):
    """The two ways a run is spoiled get DIFFERENT signals, because they have
    different costs: a fifth press leaves four good windows, a stray press
    leaves none."""

    def test_pressing_the_other_button_spoils_the_run(self):
        m = block(run_rom(), "MIXED")
        st = [fields(x) for x in states(m)]
        self.assertEqual(st[1]["spoiled"], "0")      # press 1 on B is fine
        self.assertEqual(st[-1]["spoiled"], "1")

    def test_it_STICKS_and_the_audio_freezes(self):
        m = block(run_rom(), "MIXED")
        after = re.findall(r"^APU after (.*)$", m, re.M)
        self.assertEqual(len(after), 3)          # the APU is READ after every press
        self.assertEqual(len(set(after)), 1,
                         "the APU changed after the run was spoiled:\n" + "\n".join(after))
        st = pressed_states(m)
        self.assertEqual([x["spoiled"] for x in st], ["0", "1", "1"])

    def test_both_keys_in_one_sample_spoils_it(self):
        st = [fields(x) for x in states(block(run_rom(), "BOTH"))]
        self.assertEqual(st[-1]["spoiled"], "1")
        self.assertEqual(st[-1]["presses"], "1")     # one rising edge of the word

    def test_any_other_key_spoils_it_because_the_capture_arms_on_any_bit(self):
        st = [fields(x) for x in states(block(run_rom(), "OTHER"))]
        self.assertEqual(st[-1]["spoiled"], "1")
        # and §V11.8 really does refuse such a window
        self.assertIsNone(v11sweep.axis_of_window(0x0008))
        self.assertEqual(v11sweep.derive_schedule([0x0008] * 4), "UNKNOWN")

    def test_the_bands_are_drawn_and_nothing_else_is(self):
        p = pixels(block(run_rom(), "MIXED"))
        last = fields(p[-1])
        self.assertIn(last["bg"], ("%04x" % RED, "%04x" % WHITE))
        # the boxes are gone: every sampled half takes a band colour, never grey
        for half in last["box0"].split("/") + last["box3"].split("/"):
            self.assertIn(half, ("%04x" % RED, "%04x" % WHITE))

    def test_the_stripes_cannot_be_confused_with_any_valid_state(self):
        """What identifies the spoiled screen is not a COLOUR -- the background
        is already red at count 1 -- but that ADJACENT BANDS DIFFER, which no
        valid state ever produces. `bands` samples two band rows in the left
        margin, outside every box."""
        for good in ("B", "A"):
            for line in pixels(block(run_rom(), good)):
                a, b = fields(line)["bands"].split("/")
                self.assertEqual(a, b, "a valid state produced a band pattern: " + line)
        for bad in ("MIXED", "BOTH", "OTHER"):
            a, b = fields(pixels(block(run_rom(), bad))[-1])["bands"].split("/")
            self.assertNotEqual(a, b, "the spoiled screen is not striped in " + bad)
            self.assertEqual({a, b}, {"%04x" % RED, "%04x" % WHITE})
        self.assertNotIn("BAND_H", read(TONE_SRC))


# ---------------------------------------------------- the plumbing

class ThePlumbingAndTheRecord(unittest.TestCase):

    def test_the_makefile_identity(self):
        mk = read(ROM_MK)
        self.assertIn("APP_NAME   := agb-sweep", mk)
        self.assertIn("STIM_ID    := sweep-0002", mk)   # Issue #73: U-GBP-040's fix
        self.assertIn("GAME_TITLE := OPENGBPSWEEP", mk)
        self.assertIn("GAME_CODE  := SGBP", mk)
        self.assertLessEqual(len("OPENGBPSWEEP"), 12)

    def test_the_root_makefile_builds_it(self):
        mk = read(TOP_MK)
        self.assertIn("stimulus-sweep:", mk)
        self.assertIn("make --no-print-directory -C stimulus/agb-sweep", mk)
        self.assertIn("stimulus-sweep", re.search(r"^\.PHONY:.*$", mk, re.M).group(0))

    def test_agb_tone_is_not_touched_by_this_build(self):
        base = subprocess.run(["git", "-C", ROOT, "log", "--format=%H", "-1", "--grep",
                               "Issue #65 -- agb-tone built"], capture_output=True,
                              text=True).stdout.strip()
        if not base:
            self.skipTest("the commit that built agb-tone is not in this checkout")
        d = subprocess.run(["git", "-C", ROOT, "diff", "--stat", base, "--",
                            "stimulus/agb-tone"], capture_output=True, text=True).stdout
        self.assertEqual(d.strip(), "", "stimulus/agb-tone changed since it was built")

    def test_the_warnings_are_on(self):
        mk = read(ROM_MK)
        for flag in ("-Wall", "-Wextra", "-Wpedantic", "-Wshadow", "-Wconversion"):
            self.assertIn(flag, mk)

    def test_v11_is_unchanged_by_the_build(self):
        """§V11's gates decided nothing yet and this checkpoint may not move
        them: the build implements the specification, it does not amend it."""
        base = subprocess.run(["git", "-C", ROOT, "log", "--format=%H", "-1", "--grep",
                               "Issue #69 -- the sweep pre-registered"],
                              capture_output=True, text=True).stdout.strip()
        if not base:
            self.skipTest("the commit that wrote §V11 is not in this checkout")
        then = subprocess.run(["git", "-C", ROOT, "show", "%s:tools/v11sweep.py" % base],
                              capture_output=True, text=True).stdout
        self.assertEqual(then, read(os.path.join(ROOT, "tools", "v11sweep.py")))

    def test_the_identity_the_record_states_is_the_file_that_was_built(self):
        """§V11.15.1's hashes, against the files when they exist. They are under
        build/, which Git ignores, so a clone has neither -- but on the machine
        that built them a drifting record fails here."""
        import hashlib
        canon = os.path.join(ROOT, "build", "stimulus", "agb-sweep", "agb-sweep.gba")
        deliv = os.path.join(ROOT, "build", "physical", "agb-sweep-cart.gba")
        # Issue #73 (2026-09-23) rebuilt as sweep-0002 with U-GBP-040's fix, so build/ now
        # holds THAT. §V11.15.1 keeps sweep-0001's hashes as the record of what RUN 32 ran;
        # they are reproducible only by rebuilding at that commit, which is why the check
        # follows the CURRENT record (§V11.17.1) and the older one is pinned as text.
        want = {canon: "5ba0f2cb874d10ce9b49ac8fc652559bc42e98eb1020b44d9d12b7637b56e84b",
                deliv: "9596ddee9d3f969b21264384391656df91ab23cb91042f5162b1f696a80195f2"}
        seen = 0
        for path, h in want.items():
            if not os.path.exists(path):
                continue
            with open(path, "rb") as f:
                data = f.read()
            self.assertEqual(hashlib.sha256(data).hexdigest(), h, path)
            self.assertEqual(len(data), 2352, path)
            seen += 1
        if not seen:
            self.skipTest("neither build artifact is in this checkout (build/ is ignored)")

    def test_the_delivered_image_is_the_canonical_rom_past_the_header(self):
        """gbaderive's own guarantee, re-checked here rather than trusted: the
        two files may differ ONLY in the 156-byte logo area and the complement,
        so what he flashes is the ROM this repository can rebuild."""
        canon = os.path.join(ROOT, "build", "stimulus", "agb-sweep", "agb-sweep.gba")
        deliv = os.path.join(ROOT, "build", "physical", "agb-sweep-cart.gba")
        if not (os.path.exists(canon) and os.path.exists(deliv)):
            self.skipTest("the build artifacts are not in this checkout (build/ is ignored)")
        with open(canon, "rb") as f:
            c = f.read()
        with open(deliv, "rb") as f:
            d = f.read()
        self.assertEqual(len(c), len(d))
        self.assertEqual(c[0xC0:], d[0xC0:])
        self.assertTrue(any(d[0x04:0x04 + 156]))
        self.assertFalse(any(c[0x04:0x04 + 156]))
        differ = {i for i in range(0xC0) if c[i] != d[i]}
        self.assertTrue(differ <= set(range(0x04, 0x04 + 156)) | {0xBD}, sorted(differ)[:8])

    def test_the_appendix_states_the_identity_and_that_nothing_ran(self):
        s = v11_part()
        self.assertIn("### V11.15", s)
        self.assertIn("sweep-0001", s)
        self.assertIn("NEVER RUN", s)
        self.assertIn("1 960", s)          # sweep-0001, what RUN 32 ran
        self.assertIn("71c79811c67970322d31c5715b8384100db2fae171be8c67e9ed5550831711c9", s)
        self.assertIn("13ed1108e0b1ba9ad9328c1230802fe0f1b72b1a885cd6c2087487c5c690b865", s)
        self.assertIn("2 352", s)          # sweep-0002, U-GBP-040's fix
        self.assertIn("9596ddee9d3f969b21264384391656df91ab23cb91042f5162b1f696a80195f2", s)


class TheFieldLayoutIsPinnedToGbatekAndNotToMemory(unittest.TestCase):
    """§V11.15.7. The register tests assert `volume << 12` -- OUR READING of the
    field layout. RUN 31 corroborated the FREQUENCY field by measuring it, but
    agb-tone only ever used volume 15, so the envelope volume field is
    corroborated by no run. These read the layout out of the VENDORED GBATEK
    and check the ROM against it, which is the one thing an mGBA rung would
    have added (§V11.15.7 declines it for that reason)."""

    GBATEK = os.path.join(ROOT, "external", "gbatek", "gba.md")

    def table(self):
        if not os.path.exists(self.GBATEK):
            self.skipTest("external/gbatek is not in this checkout")
        t = read(self.GBATEK)
        i = t.index("## 4000062h - SOUND1CNT")
        return t[i:i + 900]

    def test_bits_12_to_15_are_the_initial_volume(self):
        self.assertRegex(self.table(), r"12-15\s+R/W\s+Initial Volume of envelope")
        # and the ROM puts the volume exactly there
        self.assertIn("(((u16)(v) << 12) | 0x0080u)", read(ROM_SRC))

    def test_step_time_zero_really_means_no_envelope(self):
        self.assertRegex(self.table(), r"8-10\s+R/W\s+Envelope Step-Time.*0=No Envelope")
        for volume in v11sweep.AMPLITUDES:
            self.assertEqual(((volume << 12) | 0x0080) & 0x0700, 0)

    def test_duty_two_is_the_fifty_percent_square(self):
        self.assertRegex(self.table(), r"6-7\s+R/W\s+Wave Pattern Duty")
        self.assertIn("2: 50%", self.table())
        self.assertEqual((0x0080 >> 6) & 3, 2)

    def test_the_length_value_is_used_only_with_the_bit_the_rom_never_sets(self):
        self.assertIn("The Length value is used only if Bit 6 in NR14 is set", self.table())
        self.assertEqual(num(define(read(ROM_SRC), "SWEEP_RESTART")) & 0x4000, 0)

    def test_gbatek_gives_a_SECOND_reason_the_null_is_not_in_the_schedule(self):
        """§V11.4.1 excluded volume 0 because it is indistinguishable from a
        window that has not begun carrying. GBATEK adds that it is No Sound
        outright -- so it would not have been a faint tone to extrapolate from."""
        self.assertRegex(self.table(), r"Initial Volume of envelope\s+\(1-15, 0=No Sound\)")
        self.assertNotIn(0, v11sweep.AMPLITUDES)
        for volume in v11sweep.AMPLITUDES:
            self.assertTrue(1 <= volume <= 15)
        s = plain(v11_part()[v11_part().index("#### V11.15.7"):])
        self.assertIn("a SECOND, independent reason the null is not in the", s)

    def test_the_assessment_records_the_measurement_and_the_decline(self):
        s = plain(v11_part()[v11_part().index("#### V11.15.7"):])
        self.assertIn("ASSESSED AND DECLINED", s)
        self.assertIn("12 / 12", s)
        self.assertIn("no mutation is committed", s)
        self.assertIn("considered and left, not missed", s)
        self.assertIn("mGBA's APU is a MODEL", s)
        self.assertIn("No figure from it may ever enter EVIDENCE.md", s)


class TheFirstPressFixIsAppliedAndMeasuresItself(unittest.TestCase):
    """U-GBP-040 (Issue #73). The fix and the measurement are the same two
    lines: every press applies the register set TWICE, and between the two
    passes the R/W registers are read back so the ROM can say WHICH one did not
    hold. A host cannot reproduce the defect — the fake IO keeps every write —
    so what is checked here is that the mechanism is in place and that a healthy
    device draws nothing extra."""

    def test_every_press_applies_the_register_set_twice(self):
        src = read(ROM_SRC)
        body = src[src.index("static void apu_play"):]
        body = body[:body.index("\n}")]
        self.assertEqual(body.count("apu_apply(n, volume)"), 2)
        self.assertIn("the same writes again, unconditionally", body)

    def test_the_two_passes_are_identical_so_no_press_differs_from_another(self):
        """A conditional retry would make press 1 take a different path from
        presses 2-4, which is the very thing that went wrong."""
        src = read(ROM_SRC)
        body = src[src.index("static void apu_play"):]
        body = body[:body.index("\n}")]
        self.assertNotIn("if", body)

    def test_the_read_back_covers_the_register_the_hypothesis_implicates(self):
        src = read(ROM_SRC)
        self.assertIn("APU_BAD_CNT_L", src)
        self.assertIn("if (REG_SOUNDCNT_L != SWEEP_CNT_MIX)", src)
        # SOUND1CNT_X is deliberately NOT compared, and the reason is written down
        self.assertIn("SOUND1CNT_X is NOT read back", src)
        self.assertIn("bits 0-5 are the write-only length", src)

    def test_SOUNDCNT_L_is_inside_the_range_GBATEK_says_is_reset(self):
        """The hypothesis rests on 0x4000080 being inside 0x60..0x81, and
        0x4000082 being outside it. Both read out of the vendored GBATEK."""
        g = os.path.join(ROOT, "external", "gbatek", "gba.md")
        if not os.path.exists(g):
            self.skipTest("external/gbatek is not in this checkout")
        self.assertIn("all PSG\nregisters at 4000060h..4000081h are reset to zero", read(g))
        self.assertTrue(0x60 <= 0x80 <= 0x81)      # SOUNDCNT_L, inside
        self.assertFalse(0x60 <= 0x82 <= 0x81)     # SOUNDCNT_H, outside

    def test_a_healthy_device_draws_NOTHING_extra(self):
        """The picture §V11.15.3 describes must be unchanged when the mask is
        zero, or the fix would have changed the instrument."""
        out = run_rom()
        for line in re.findall(r"^MARKS (\w+)$", out, re.M):
            self.assertEqual(line, "0000")
        for tag in ("B", "A"):
            for line in pixels(block(out, tag)):
                pass
        # the marks live in the free band under the top rail, clear of everything
        src = read(ROM_SRC)
        y, w = num(define(src, "MARK_Y")), num(define(src, "MARK_W"))
        self.assertGreaterEqual(y, num(define(src, "RAIL_H")))
        self.assertLessEqual(y + w, num(define(src, "BOX_Y")))
        self.assertIn("NOTHING is drawn when it is zero", src)

    def test_the_hypothesis_is_LABELLED_and_not_asserted(self):
        src = read(ROM_SRC)
        self.assertIn("A HYPOTHESIS, LABELLED AS ONE AND NOT PROMOTED BY THIS ROM", src)
        self.assertIn("measured rather than argued", src)

    def test_agb_tone_is_STILL_untouched_by_the_fix(self):
        base = subprocess.run(["git", "-C", ROOT, "log", "--format=%H", "-1", "--grep",
                               "Issue #65 -- agb-tone built"], capture_output=True,
                              text=True).stdout.strip()
        if not base:
            self.skipTest("the commit that built agb-tone is not in this checkout")
        d = subprocess.run(["git", "-C", ROOT, "diff", "--stat", base, "--",
                            "stimulus/agb-tone"], capture_output=True, text=True).stdout
        self.assertEqual(d.strip(), "")


class TheOperatorsPreFlightCheckIsSizedHonestly(unittest.TestCase):
    """§V11.15.6. He put agb-tone in his own GBA unasked and it made sound. That
    is a second channel and a free pre-flight step -- and it is NOT evidence
    about AGB behaviour, which the page has to say in its own words or somebody
    will cite it as one."""

    def part(self):
        """§V11.15.6 ALONE. Bounded at the next subsection, not run to the end
        of the document -- the slice defect this project met three times in one
        day, and §V11.15.7 cites GBP-HW-276 in its own text."""
        s = v11_part()
        i = s.index("#### V11.15.6")
        j = s.find("\n#### ", i + 1)
        return s[i:j] if j >= 0 else s[i:]

    def test_the_quote_is_carried_and_labelled_an_operator_observation(self):
        s = self.part()
        self.assertIn("OPERATOR OBSERVATION", s)
        # the quote wraps across a blockquote line, so it is matched flattened
        self.assertIn("testei no console GBA e ela sai som normal",
                      plain(s.replace("\n> ", " ")))

    def test_the_limits_are_stated_and_no_id_is_minted(self):
        s = plain(self.part())
        self.assertIn("he HEARD it", s)
        self.assertIn("his console is NOT", s)          # the table wraps it over two lines
        self.assertIn("the GBP's internal AGB INTERNAL AGB reached through GBS-DOL", s)
        self.assertIn("The two are not the same device", s)
        self.assertIn("the unit is UNDECLARED", s)
        self.assertIn("SO IT IS NOT EVIDENCE", s)
        self.assertIn("it mints no id", s)
        # MINTING is a heading; citing an id in prose is not minting one
        self.assertIsNone(re.search(r"^#{2,4} +GBP-[A-Z]+-\d{3}\b", self.part(), re.M))
        self.assertIsNone(re.search(r"GBP-[A-Z]+-\d{3}", self.part()))

    def test_it_is_a_check_and_not_a_gate_and_v1113_is_not_edited(self):
        s = self.part()
        self.assertIn("CHECK, NOT A GATE", s)
        self.assertIn("§V11.13's action list is frozen and is NOT edited", plain(s))
        self.assertIn("It replaces nothing", s)
        self.assertIn(" 0.5 ", s)
        # and §V11.13 really does still say what it said
        v13 = v11_part()
        self.assertIn("WAIT 20 SECONDS", v13)
        self.assertIn("USE THE SAME BUTTON ALL FOUR TIMES", v13)

    def test_the_step_checks_the_axes_which_is_why_it_is_worth_more_here(self):
        s = plain(self.part())
        self.assertIn("A CHANGES THE PITCH while", s)   # the table column wraps
        self.assertIn("B CHANGES THE LOUDNESS", s)
        self.assertIn("a wrong-button run is a DIFFERENT EXPERIMENT", s)
        self.assertIn("a ROM that PASSES this has told us NOTHING about the Game Boy Player", s)


if __name__ == "__main__":
    unittest.main()
