"""tests/host/test_agb_route.py -- GitHub Issue #124, Round C: `agb-route`, `agb-sweep`'s stimulus with its LEFT/RIGHT
routing as a build mode and SOUNDBIAS read three times.

THE ROM'S OWN CODE IS RUN, not read, as tests/host/test_agb_sweep.py does it: the C is compiled FOR THE HOST with the
hardware bases relocated onto buffers. What is required here:

  * ROUTE-BOTH IS THE ARCHIVED STIMULUS. `agb-sweep` and `agb-route` (route-both) are driven through the same key
    sequences and the APU registers must hold the same words after every press, with the same read-back marks and the
    same state; the one-side builds differ in SOUNDCNT_L alone (0x1077, 0x0177). And the text of everything that writes
    the APU is `agb-sweep`'s, the mix constant's definition apart.
  * SOUNDBIAS IS READ, NEVER WRITTEN by main.c; entry.S reads it before any store and writes it only in route-bias0200,
    after the read.
  * THE READOUT DECODES: the three rows the screen shows read back, through an independent font table here, as the
    values the three reads saw; the entry row is four dashes when the stub's marker is absent; the route bars sit on
    the edges the build names.
  * THE BUILT IMAGES, where `make stimulus-route` has run: the entry word branches to bias_entry, the stub's words are
    the expected instructions reading the expected literals, the header is valid, and crt0's clear and copy targets
    (the linker map) lie outside palette RAM, as the record's disassembly finding says.

WHAT A HOST CANNOT CHECK, said rather than implied: no sound, no real SOUNDBIAS, and whether the readout is legible on
his converter. The physical run is for those, and #124 authorises none.
"""
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest

import hostcc  # noqa: E402  (tests/host is on the path)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gbaentry  # noqa: E402
import gbahdr  # noqa: E402

ROUTE_SRC = os.path.join(ROOT, "stimulus", "agb-route", "source", "main.c")
ENTRY_SRC = os.path.join(ROOT, "stimulus", "agb-route", "source", "entry.S")
ROUTE_MK = os.path.join(ROOT, "stimulus", "agb-route", "Makefile")
SWEEP_SRC = os.path.join(ROOT, "stimulus", "agb-sweep", "source", "main.c")
BUILD = os.path.join(ROOT, "build", "stimulus", "agb-route")
VARIANTS = {"both": 0x1177, "left": 0x1077, "right": 0x0177, "bias0200": 0x1177}
HASHES = {"both": "90854581793af57252438200f2d4f6ac03253cd6c1f1bcddad2432f3ceec5dc2",
          "left": "aff3d210043026b8fc6a8e04a5ea25c7cde40fe0d0a0f3daa1495f65e1c4a571",
          "right": "1a1b69abb02374b67d6ec01f5133b86762915ab9e4c70f62addc25fa26752f5f",
          "bias0200": "41d386870b24ff0eb4ca65225ae9fdfc54e1df67c8ed66cf5278ba3d4a24fa2c"}

# an independent 3x5 font: row r of a glyph is bits 2..0, bit 2 the left column
FONT = {"0": (7, 5, 5, 5, 7), "1": (2, 6, 2, 2, 7), "2": (7, 1, 7, 4, 7), "3": (7, 1, 7, 1, 7), "4": (5, 5, 7, 1, 1),
        "5": (7, 4, 7, 1, 7), "6": (7, 4, 7, 5, 7), "7": (7, 1, 1, 1, 1), "8": (7, 5, 7, 5, 7), "9": (7, 5, 7, 1, 7),
        "A": (7, 5, 7, 5, 5), "B": (6, 5, 6, 5, 6), "C": (7, 4, 4, 4, 7), "D": (6, 5, 5, 5, 6), "E": (7, 4, 7, 4, 7),
        "F": (7, 4, 7, 4, 4), "-": (0, 0, 7, 0, 0)}

DRIVE = r'''
static unsigned short io16(unsigned off) { return *(volatile unsigned short *)(fake_io + off); }
static void dump_apu(const char *tag)
{
    printf("APU %s 60=%04x 62=%04x 64=%04x 80=%04x 82=%04x 84=%04x\n", tag,
           io16(0x060), io16(0x062), io16(0x064), io16(0x080), io16(0x082), io16(0x084));
}
static void drive(const char *tag, const unsigned short *seq, unsigned n)
{
    struct sweep_state st;
    unsigned i;
    sweep_init(&st);
    apu_silence();
    printf("RUN %s\n", tag);
    dump_apu("reset");
    for (i = 0; i < n; i++) {
        int pressed = sweep_step(&st, seq[i]);
        if (pressed && !st.spoiled) apu_play(sweep_freq_n(&st), sweep_volume(&st));
        printf("STEP %u key=%04x pressed=%d presses=%u spoiled=%u n=%u vol=%u marks=%04x\n", i, seq[i], pressed,
               st.presses, st.spoiled, sweep_freq_n(&st), sweep_volume(&st), apu_marks);
        if (pressed) dump_apu("after");
    }
}
static void drive_all(void)
{
    static const unsigned short b_run[] = {
        0x03FF, 0x03FD, 0x03FF, 0x03FD, 0x03FF, 0x03FD, 0x03FF, 0x03FD, 0x03FF, 0x03FD };
    static const unsigned short a_run[] = {
        0x03FF, 0x03FE, 0x03FF, 0x03FE, 0x03FF, 0x03FE, 0x03FF, 0x03FE };
    static const unsigned short mixed[] = { 0x03FF, 0x03FD, 0x03FF, 0x03FE, 0x03FF, 0x03FD };
    static const unsigned short other[] = { 0x03FF, 0x037F };
    drive("B", b_run, sizeof b_run / sizeof b_run[0]);
    drive("A", a_run, sizeof a_run / sizeof a_run[0]);
    drive("MIXED", mixed, sizeof mixed / sizeof mixed[0]);
    drive("OTHER", other, sizeof other / sizeof other[0]);
}
'''

SWEEP_HARNESS = r'''
#include <stdio.h>
static unsigned char fake_vram[96 * 1024];
static unsigned char fake_io[1024];
#define AGB_IO_BASE   ((unsigned long)fake_io)
#define AGB_VRAM_BASE ((unsigned long)fake_vram)
#define main rom_main_unused
#include "main.c"
#undef main
''' + DRIVE + r'''
int main(void) { drive_all(); return 0; }
'''

ROUTE_HARNESS = r'''
#include <stdio.h>
static unsigned char fake_vram[96 * 1024];
static unsigned char fake_io[1024];
static unsigned char fake_pal[1024];
#define AGB_IO_BASE   ((unsigned long)fake_io)
#define AGB_VRAM_BASE ((unsigned long)fake_vram)
#define AGB_PAL_BASE  ((unsigned long)fake_pal)
#define main rom_main_unused
#include "main.c"
#undef main
''' + DRIVE + r'''
static unsigned short px(unsigned x, unsigned y) { return ((unsigned short *)fake_vram)[y * 240u + x]; }
static void set16(unsigned char *base, unsigned off, unsigned short v) { *(unsigned short *)(base + off) = v; }

static void readout(const char *tag, unsigned short bias_reg, unsigned short stash, int marker)
{
    struct sweep_state st;
    unsigned r, d, row, k, b;
    set16(fake_io, 0x088, bias_reg);
    set16(fake_pal, 0x3FC, stash);
    set16(fake_pal, 0x3FE, marker ? 0xB1A5u : 0x0000u);
    route_boot(&st);
    printf("BOOT %s", tag);
    for (r = 0; r < 3u; r++) {
        unsigned y0 = RD_Y0 + r * RD_ROW_H;
        printf(" row%u=", r);
        for (d = 0; d < 4u; d++) {
            for (row = 0; row < 5u; row++) {
                unsigned bits = 0;
                for (k = 0; k < 3u; k++)
                    if (px(RD_X0 + d * (RD_DIGIT_W + RD_GAP) + k * RD_SCALE + RD_SCALE / 2u,
                           y0 + row * RD_SCALE + RD_SCALE / 2u) == COL_WHITE)
                        bits |= 4u >> k;
                printf("%u", bits);
            }
            printf(d < 3u ? "," : "");
        }
        printf(" cells%u=", r);
        for (b = 0; b < 16u; b++) {
            unsigned short c = px(RD_X0 + b * (RD_CELL_W + RD_CELL_GAP) + RD_CELL_W / 2u, y0 + RD_CELL_Y + RD_CELL_H / 2u);
            printf("%c", c == COL_WHITE ? '1' : (c == COL_GREY ? '0' : '.'));
        }
    }
    printf(" barL=%04x barR=%04x mid=%04x bias_after=%04x\n", px(4u, 80u), px(235u, 80u), px(120u, 150u),
           io16(0x088));
}

/* after a press with every read-back mark lit: the four 12x12 marks and what the bars cover */
static void marks_and_bars(void)
{
    struct sweep_state st;
    unsigned k, x, y, whole = 0u, cyan_out = 0u, orange_top = 0u;
    sweep_init(&st);
    (void)sweep_step(&st, 0x03FFu);
    (void)sweep_step(&st, 0x03FEu);
    apu_marks = 0x000Fu;
    sweep_paint(&st);
    for (k = 0; k < 4u; k++) {
        unsigned ok = 1u;
        for (y = MARK_Y; y < MARK_Y + MARK_W; y++)
            for (x = MARK_X0 + k * (MARK_W + MARK_GAP); x < MARK_X0 + k * (MARK_W + MARK_GAP) + MARK_W; x++)
                if (px(x, y) != COL_CYAN) ok = 0u;
        whole += ok;
    }
    for (y = 0; y < SCREEN_H; y++)
        for (x = 0; x < SCREEN_W; x++) {
            int in_mark = 0;
            for (k = 0; k < 4u; k++)
                if (y >= MARK_Y && y < MARK_Y + MARK_W && x >= MARK_X0 + k * (MARK_W + MARK_GAP) &&
                    x < MARK_X0 + k * (MARK_W + MARK_GAP) + MARK_W) in_mark = 1;
            if (px(x, y) == COL_CYAN && !in_mark) cyan_out++;
            if (px(x, y) == COL_ORANGE && y < BOX_Y) orange_top++;
        }
    printf("MARKS whole=%u cyan_outside=%u orange_above_boxes=%u bar=%04x\n", whole, cyan_out, orange_top,
           px(4u, BOX_Y + 10u) == COL_ORANGE || px(235u, BOX_Y + 10u) == COL_ORANGE ? COL_ORANGE : 0u);
}

int main(void)
{
    readout("default", 0x0200u, 0x0200u, 1);
    readout("res1", 0x4200u, 0x4200u, 1);
    readout("mixed", 0x4200u, 0x0200u, 1);
    readout("nomarker", 0x0200u, 0x0200u, 0);
    readout("digits", 0x89ABu, 0xCDEFu, 1);
    readout("more", 0x0123u, 0x4567u, 1);
    set16(fake_io, 0x088, 0x5A5Au);
    drive_all();
    printf("BIAS after the drives %04x\n", io16(0x088));
    marks_and_bars();
    return 0;
}
'''

_OUT = {}


def build_run(harness, src_dir, defines=(), key=None):
    key = key or (harness[:40], src_dir, defines)
    if key in _OUT:
        return _OUT[key]
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "harness.c")
        with open(src, "w") as f:
            f.write(harness)
        exe = os.path.join(d, "rom")
        args = ["-std=gnu11", "-O1", "-Wall", "-Wextra", "-Wno-unused-function", "-I", src_dir]
        args += ["-D%s" % x for x in defines] + ["-o", exe, src]
        have, ok, err = hostcc.compile_c(args, cc="cc")
        hostcc.require_build(have, ok, err, "the agb-route ROM harness")
        r = subprocess.run([exe], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
    _OUT[key] = r.stdout
    return r.stdout


def sweep_out():
    return build_run(SWEEP_HARNESS, os.path.dirname(SWEEP_SRC))


def route_out(mix=0x1177):
    return build_run(ROUTE_HARNESS, os.path.dirname(ROUTE_SRC), ("ROUTE_MIX=0x%04Xu" % mix,))


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def drives(out):
    """The drive lines (RUN / STEP / APU) only."""
    return [l for l in out.splitlines() if l.startswith(("RUN ", "STEP ", "APU "))]


def boots(out):
    return dict((m.group(1), m.group(2)) for m in re.finditer(r"^BOOT (\S+) (.*)$", out, re.M))


def decode(boot):
    """(the three rows as strings of hex digits or dashes, their cells, the bar colours)."""
    rows, cells = [], []
    inv = dict((v, k) for k, v in FONT.items())
    for r in range(3):
        digits = re.search(r"row%d=(\S+)" % r, boot).group(1).split(",")
        rows.append("".join(inv.get(tuple(int(c) for c in g), "?") for g in digits))
        cells.append(re.search(r"cells%d=(\S+)" % r, boot).group(1))
    bars = dict(re.findall(r"(barL|barR|mid|bias_after)=(\w+)", boot))
    return rows, cells, bars


def section(src, start, end):
    i = src.index(start)
    return src[i:src.index(end, i)]


class RouteBothIsTheArchivedStimulus(unittest.TestCase):
    def test_the_apu_holds_the_same_words_after_every_press(self):
        a, b = drives(sweep_out()), drives(route_out(0x1177))
        self.assertEqual(len([l for l in a if l.startswith("APU after")]), 13)      # 5 + 4 + 3 + 1 presses
        self.assertEqual(a, b)

    def test_the_one_side_builds_differ_in_soundcnt_l_alone(self):
        a = drives(sweep_out())
        for mix in (0x1077, 0x0177):
            b = drives(route_out(mix))
            self.assertEqual(len(a), len(b))
            for la, lb in zip(a, b):
                if la.startswith("APU after"):
                    self.assertEqual(re.sub(r" 80=\w+", "", la), re.sub(r" 80=\w+", "", lb))
                    was = re.search(r" 80=(\w+)", la).group(1)       # 1177 once played, 0000 if never (a spoiled run)
                    self.assertEqual(re.search(r" 80=(\w+)", lb).group(1), "%04x" % mix if was == "1177" else was)
                else:
                    self.assertEqual(la, lb)

    def test_the_text_that_writes_the_apu_is_agb_sweeps(self):
        s, r = read(SWEEP_SRC), read(ROUTE_SRC)
        for start, end in (("/* ---- §V11.3's two schedules", "/* SOUNDCNT_L: channel 1 on both sides"),
                           ("/* SOUNDCNT_H: PSG-to-output ratio", "/* ---- colours"),
                           ("enum sweep_axis {", "u16 sweep_background"),
                           ("static void apu_silence(void)", "static void wait_vblank(void)")):
            self.assertEqual(section(s, start, end), section(r, start, end), start)

    def test_the_mix_definition_is_the_only_difference_and_route_both_is_0x1177(self):
        r = read(ROUTE_SRC)
        self.assertIn("#ifndef ROUTE_MIX\n#define ROUTE_MIX 0x1177u\n#endif", r)
        self.assertIn("#define SWEEP_CNT_MIX ROUTE_MIX", r)
        self.assertIn("#define SWEEP_CNT_MIX 0x1177u", read(SWEEP_SRC))
        self.assertIn('#error "ROUTE_MIX must be 0x1177 (both), 0x1077 (left) or 0x0177 (right)"', r)

    def test_the_makefile_builds_the_four_images_one_value_apart(self):
        mk = read(ROUTE_MK)
        self.assertIn("VARIANTS       := both left right bias0200", mk)
        for v, mix in VARIANTS.items():
            self.assertIn("MIX_%s" % v, mk)
            self.assertRegex(mk, r"MIX_%s\s+:= 0x%04Xu" % (v, mix))
        self.assertIn("FORCE_bias0200 := 0x0200", mk)
        self.assertEqual(len(re.findall(r"^FORCE_\w+", mk, re.M)), 1)


class SoundbiasIsReadNeverWritten(unittest.TestCase):
    def test_main_never_writes_it(self):
        code = re.sub(r"/\*.*?\*/", " ", read(ROUTE_SRC), flags=re.S)
        self.assertNotRegex(code, r"REG_SOUNDBIAS\s*=[^=]")
        self.assertEqual(len(re.findall(r"=\s*REG_SOUNDBIAS\s*;", code)), 2)      # M and I
        out = route_out(0x1177)
        self.assertIn("BIAS after the drives 5a5a", out)
        for b in boots(out).values():
            self.assertEqual(decode(b)[2]["bias_after"], re.search(r"bias_after=(\w+)", b).group(1))

    def test_the_stub_reads_before_it_stores_and_writes_only_under_force_bias(self):
        e = read(ENTRY_SRC)
        code = [l.split("@")[0].strip() for l in e.split("*/", 1)[1].splitlines()]
        code = [l for l in code if l and not l.startswith(".") and not l.endswith(":")]
        self.assertEqual(code[:2], ["ldr     r0, =0x04000088", "ldrh    r1, [r0]"])
        stores_r0 = [i for i, l in enumerate(code) if re.match(r"strh\s+r1, \[r0\]$", l)]
        self.assertEqual(len(stores_r0), 1)
        i = stores_r0[0]
        self.assertEqual(code[i - 2:i], ["#ifdef FORCE_BIAS", "ldr     r1, =FORCE_BIAS"])
        self.assertEqual(code[i + 1], "#endif")
        self.assertEqual(code[-2:], ["ldr     r0, =start_vector", "bx      r0"])
        self.assertIn("ldr     r2, =0x050003FC", code)
        self.assertIn("ldr     r3, =0xB1A5", code)

    def test_the_stash_is_where_main_reads_it(self):
        r = read(ROUTE_SRC)
        self.assertIn("#define AGB_PAL_BASE  0x05000000u", r)
        self.assertIn("#define BIAS_STASH ((volatile u16 *)((unsigned long)AGB_PAL_BASE + 0x3FCu))", r)
        self.assertIn("#define BIAS_MARK  0xB1A5u", r)


class TheReadoutDecodes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = boots(route_out(0x1177))

    def test_the_font_is_unambiguous(self):
        self.assertEqual(len(set(FONT.values())), len(FONT))

    def test_each_row_reads_back_its_value(self):
        # rows: E (the stub's stash), M, I (the register, twice)
        for tag, (e, m, i) in (("default", ("0200", "0200", "0200")), ("res1", ("4200", "4200", "4200")),
                               ("mixed", ("0200", "4200", "4200")), ("digits", ("CDEF", "89AB", "89AB")),
                               ("more", ("4567", "0123", "0123"))):
            rows, cells, _bars = decode(self.b[tag])
            self.assertEqual(rows, [e, m, i], tag)
            for v, c in zip((e, m, i), cells):
                self.assertEqual(c, format(int(v, 16), "016b"), tag)

    def test_the_entry_row_is_dashes_when_the_stub_did_not_run(self):
        rows, cells, _bars = decode(self.b["nomarker"])
        self.assertEqual(rows, ["----", "0200", "0200"])
        self.assertEqual(cells[0], "." * 16)                             # no cells drawn for it

    def test_the_route_bars_name_the_build(self):
        orange, black = "021f", "0000"
        for mix, want in ((0x1177, (orange, orange)), (0x1077, (orange, black)), (0x0177, (black, orange))):
            bars = decode(boots(route_out(mix))["default"])[2]
            self.assertEqual((bars["barL"], bars["barR"]), want, hex(mix))


def built(v):
    d = os.path.join(BUILD, v)
    paths = dict((k, os.path.join(d, "agb-route-%s.%s" % (v, k))) for k in ("gba", "elf", "map"))
    paths["dis"] = os.path.join(d, "crt0.dis")
    paths["info"] = os.path.join(d, "build-info.txt")
    return paths


class TheBarsNeverCoverTheMarks(unittest.TestCase):
    def test_every_mark_stays_whole_and_the_bars_stay_below_them(self):
        # U-GBP-040's four read-back marks, all lit, are intact 12x12 cyan squares on every build; no other pixel is
        # cyan; no orange above the boxes (the mark band and the top rail are never covered)
        for mix in (0x1177, 0x1077, 0x0177):
            m = re.search(r"^MARKS whole=(\d+) cyan_outside=(\d+) orange_above_boxes=(\d+) bar=(\w+)$",
                          route_out(mix), re.M)
            self.assertEqual(m.groups(), ("4", "0", "0", "021f"), hex(mix))

    def test_orange_is_the_bars_alone(self):
        r = re.sub(r"/\*.*?\*/", " ", read(ROUTE_SRC), flags=re.S)
        self.assertEqual(len(re.findall(r"\bCOL_ORANGE\b", r)), 3)           # the define and the two bars


class TheBuiltImages(unittest.TestCase):
    def need(self, v):
        p = built(v)
        if not all(os.path.isfile(x) for x in p.values()):
            self.skipTest("stimulus not built: run `make stimulus-route`")
        return p

    def stub_words(self, rom, elf, v):
        addr, size = gbaentry.elf_symbol(elf, "bias_entry")
        off = addr - gbaentry.ROM_BASE
        n = size // 4
        return addr, list(struct.unpack_from("<%dI" % n, rom, off))

    def literal(self, words, addr, i):
        """The value word i loads: an ARM `ldr rX, [pc, #imm]` reads the pool; the assembler turns `ldr rX, =c` into
        `mov rX, #c` when c is an ARM immediate (0x0200 is), so that form is decoded too."""
        w = words[i]
        if w & 0xFFF00000 == 0xE3A00000:                                  # mov rX, #imm8 ror (2 * rot)
            imm, rot = w & 0xFF, ((w >> 8) & 0xF) * 2
            return ((imm >> rot) | (imm << (32 - rot))) & 0xFFFFFFFF if rot else imm
        self.assertEqual(w & 0xFFFF0FFF & 0xFFFF0000, 0xE59F0000, hex(w))
        target = addr + 4 * i + 8 + (w & 0xFFF)
        return words[(target - addr) // 4]

    def test_the_entry_branches_to_the_stub(self):
        for v in VARIANTS:
            p = self.need(v)
            with open(p["gba"], "rb") as f:
                rom = f.read()
            with open(p["elf"], "rb") as f:
                elf = f.read()
            addr, _size = gbaentry.elf_symbol(elf, "bias_entry")
            self.assertEqual(struct.unpack_from("<I", rom, 0)[0], gbaentry.branch_to(addr), v)
            info = gbahdr.describe(rom)
            self.assertEqual(gbahdr.problems(info), [], v)
            # re-applying the patch is a no-op: the tool accepts its own branch and writes the same word
            again, r = gbaentry.patch(rom, elf, "bias_entry")
            self.assertEqual(again, rom, v)

    def test_the_stubs_words_are_the_read_the_stash_and_the_branch(self):
        for v in VARIANTS:
            p = self.need(v)
            with open(p["gba"], "rb") as f:
                rom = f.read()
            with open(p["elf"], "rb") as f:
                elf = f.read()
            addr, w = self.stub_words(rom, elf, v)
            start, _ = gbaentry.elf_symbol(elf, "start_vector")
            self.assertEqual(self.literal(w, addr, 0), 0x04000088, v)
            self.assertEqual(w[1], 0xE1D010B0, v)                          # ldrh r1, [r0]
            self.assertEqual(self.literal(w, addr, 2), 0x050003FC, v)
            self.assertEqual(w[3], 0xE1C210B0, v)                          # strh r1, [r2]
            self.assertEqual(self.literal(w, addr, 4), 0xB1A5, v)
            self.assertEqual(w[5], 0xE1C230B2, v)                          # strh r3, [r2, #2]
            k = 6
            if v == "bias0200":
                self.assertEqual(self.literal(w, addr, 6), 0x0200, v)
                self.assertEqual(w[7], 0xE1C010B0, v)                      # strh r1, [r0]: after the read
                k = 8
            self.assertEqual(self.literal(w, addr, k), start, v)
            self.assertEqual(w[k + 1], 0xE12FFF10, v)                      # bx r0
            self.assertNotIn(0xE1C010B0, w[:6], v)                         # no store to SOUNDBIAS before the read

    def test_crt0_clears_and_copies_nothing_in_palette_ram(self):
        # the record's disassembly finding: crt0's clear/copy targets are these linker symbols plus the whole of EWRAM
        # (computed: 64 << 12 bytes from 0x40000 << 7); every one lies in EWRAM or IWRAM, none in 0x05000000..0x050003FF
        syms = ("__sbss_start__", "__sbss_end__", "__bss_start__", "__bss_end__", "__data_start__", "__data_end__",
                "__iwram_start__", "__iwram_end__", "__ewram_start", "__ewram_end", "__iwram_overlay_start")
        for v in VARIANTS:
            p = self.need(v)
            mp = read(p["map"])
            for s in syms:
                m = re.search(r"^\s+0x([0-9a-f]{8,16})\s+%s\s*=" % re.escape(s), mp, re.M)
                if m is None:
                    m = re.search(r"^\s+0x([0-9a-f]{8,16})\s+%s\b" % re.escape(s), mp, re.M)
                self.assertIsNotNone(m, (v, s))
                a = int(m.group(1), 16)
                self.assertTrue(0x02000000 <= a <= 0x02040000 or 0x03000000 <= a <= 0x03008000, (v, s, hex(a)))
            dis = read(p["dis"])
            self.assertIn("<bias_entry>:", dis, v)                             # the stub is in the record too
            self.assertIn("ldrh\tr1, [r0]", dis, v)
            for want in ("movs\tr1, #64", "lsls\tr1, r1, #12", "lsls\tr0, r1, #7", "bl\t"):
                self.assertIn(want, dis, (v, want))
            words = [int(x, 16) for x in re.findall(r"\.word\t0x([0-9a-f]{8})", dis)]
            self.assertFalse([w for w in words if 0x05000000 <= w <= 0x050003FF and w != 0x050003FC], v)

    def test_the_images_are_the_ones_the_record_names(self):
        # GBP-HW-352 records these four hashes; a rebuild of unchanged sources reproduces them byte for byte
        import hashlib
        ev = read(os.path.join(ROOT, "docs", "research", "EVIDENCE.md"))
        for v, h in HASHES.items():
            self.assertIn("%-15s sha256 %s" % ("route-" + v, h), ev, v)
            p = self.need(v)
            with open(p["gba"], "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), h, v)

    def test_the_build_info_names_the_variant_and_crt0(self):
        for v, mix in VARIANTS.items():
            p = self.need(v)
            info = read(p["info"])
            self.assertIn("variant=%s\n" % v, info)
            self.assertIn("route_mix=0x%04Xu\n" % mix, info)
            self.assertIn("force_bias=%s\n" % ("0x0200" if v == "bias0200" else "none"), info)
            self.assertRegex(info, r"sha256_gba_crt0=[0-9a-f]{64}\n")


if __name__ == "__main__":
    unittest.main()
