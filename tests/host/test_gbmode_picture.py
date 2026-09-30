"""tests/host/test_gbmode_picture.py -- GitHub Issue #148: the picture tool reads geometry, border, colour and the scaling test, and the test can SAY NO.

Synthetic frames only (a seeded pseudo-random palette pattern, never retail content) drive the tool through every branch: a 1:1 picture inside a border, the same picture
nearest-neighbour scaled to the whole frame (the duplication test must FIND it, otherwise a clean reading on RUN 59 would mean nothing), a uniform frame, a picture placed
elsewhere, the bit-15 pixel, and the refusal to render outside the ignored roots. The archived RUN 59 sidecar (captures/local, ignored by Git) is recomputed against the numbers
HARDWARE_TESTS.md V29.13 and GBP-HW-379 quote; that part skips, with the registered reason, on a host without the archive.
"""
import hashlib
import os
import random
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gbmode_picture as gp  # noqa: E402

W, H = 240, 160
FULL = os.path.join(ROOT, "captures", "local", "GBP-VIDEO-004_gbmode-0001-run59-full.bin")
IDXCAP = os.path.join(ROOT, "captures", "local", "GBP-VIDEO-004_gbmode-0001-run59-idxcap.bin")
FULL_SHA = "db2c85e9ec60824d5985359b30aedd32fa5e71995688afc76cd82cb1a83d6ded"
IDXCAP_SHA = "5687d3b34bf0763cb05c2625105f982231459779587e1f821e34c1466b471f3c"
DOC = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EVID = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")


def raw_of(grid):
    """The inverse of vfull.consumed_words: a 240 x 160 grid of 16-bit words into the 153 600-byte raw layout (40 blocks of 0xF00, four lines of 960 bytes)."""
    raw = bytearray(153600)
    for y in range(H):
        b, line = y // 4, y % 4
        base = b * 0xF00 + line * 960
        for x in range(W):
            v = grid[y][x]
            o = base + x * 4
            raw[o + 1] = v >> 8
            raw[o + 3] = v & 0xFF
    return bytes(raw)


PALETTE = [0x0000] + [(r << 10) | (g << 5) | b for (r, g, b) in ((31, 31, 31), (24, 12, 9), (1, 8, 5), (0, 4, 5), (13, 8, 9), (5, 10, 4), (21, 21, 21), (10, 0, 10), (0, 0, 21))]


def picture(rng, w=160, h=144):
    """A structured pseudo-random picture: horizontal runs of a palette colour (never black), so neighbours are equal often but not always."""
    pic = []
    for _y in range(h):
        row, x = [], 0
        while x < w:
            n = rng.randint(1, 9)
            c = rng.choice(PALETTE[1:])
            row += [c] * n
            x += n
        pic.append(row[:w])
    return pic


def framed(pic, ox, oy, border=0x0000):
    g = [[border] * W for _ in range(H)]
    for y, row in enumerate(pic):
        for x, v in enumerate(row):
            g[oy + y][ox + x] = v
    return g


class TheToolReadsAndCanSayNo(unittest.TestCase):
    def test_a_one_to_one_picture_in_a_border(self):
        g = framed(picture(random.Random(1)), 40, 8)
        g[0][0] |= 0x8000
        a = gp.analyse_frame(raw_of(g))
        self.assertEqual((a["bbox"], a["size"]), ((40, 8, 199, 151), (160, 144)))
        self.assertEqual(a["border"], {"left": 40, "top": 8, "right": 40, "bottom": 8})
        self.assertEqual((a["border_word"], a["outside_is_border"]), (0x0000, True))
        self.assertEqual((a["bit15_count"], a["bit15_pixels"]), (1, [(0, 0)]))
        self.assertEqual((a["scaling"]["col"]["verdict"], a["scaling"]["row"]["verdict"]), ("NO_PERIODIC_DUPLICATION", "NO_PERIODIC_DUPLICATION"))
        self.assertEqual(a["inside_border_word_pixels"], 0)

    def test_the_duplication_test_finds_a_nearest_neighbour_stretch(self):
        """The instrument discriminates: the same picture stretched 1.5 x horizontally and 10/9 vertically (nearest neighbour) is FOUND at period 3 and period 10."""
        pic = picture(random.Random(2))
        g = [[pic[min(143, (y * 144) // 160)][min(159, (x * 160) // 240)] for x in range(W)] for y in range(H)]
        a = gp.analyse_frame(raw_of(g))
        self.assertEqual(a["size"], (240, 160))
        self.assertTrue(a["scaling"]["col"]["verdict"].startswith("DUPLICATION_AT_PERIOD_3"), a["scaling"]["col"]["verdict"])
        self.assertTrue(a["scaling"]["row"]["verdict"].startswith("DUPLICATION_AT_PERIOD_") and "10" in a["scaling"]["row"]["verdict"], a["scaling"]["row"]["verdict"])

    def test_a_period_that_cannot_discriminate_is_skipped_and_never_read_as_a_clean_no(self):
        """The reviewer's counterexample, made deterministic: period 3 has every phase at or above 0.95 (its forced phase included) while period 7 is evaluable."""
        real = gp.phase_rates

        def canned(px, box, axis, m):
            if m == 3:
                return [0.957, 0.957, 1.0]
            if m == 7:
                return [0.5, 0.9, 0.5, 0.5, 0.5, 0.5, 0.5]
            return [0.5] * m
        gp.phase_rates = canned
        try:
            v = gp.scaling(None, (0, 0, 1, 1))["col"]
        finally:
            gp.phase_rates = real
        self.assertNotEqual(v["verdict"], "NO_PERIODIC_DUPLICATION")
        self.assertEqual(v["verdict"], "PARTIAL_NO_DUPLICATION")
        self.assertEqual(v["skipped"], [3])
        self.assertNotIn(3, v["evaluated"])

    def test_a_forced_phase_in_an_evaluable_period_is_a_yes_even_with_other_periods_skipped(self):
        real = gp.phase_rates
        gp.phase_rates = lambda px, box, axis, m: ([1.0, 0.5, 0.5] if m == 3 else [0.99] * m)
        try:
            v = gp.scaling(None, (0, 0, 1, 1))["row"]
        finally:
            gp.phase_rates = real
        self.assertEqual(v["verdict"], "DUPLICATION_AT_PERIOD_3")

    def test_it_finds_a_doubling_too(self):
        pic = picture(random.Random(3), 120, 80)
        g = [[pic[y // 2][x // 2] for x in range(W)] for y in range(H)]
        a = gp.analyse_frame(raw_of(g))
        self.assertTrue(a["scaling"]["col"]["verdict"].startswith("DUPLICATION_AT_PERIOD_2"))
        self.assertTrue(a["scaling"]["row"]["verdict"].startswith("DUPLICATION_AT_PERIOD_2"))

    def test_a_uniform_frame_and_a_flat_picture_are_not_evaluable(self):
        a = gp.analyse_frame(raw_of([[0] * W for _ in range(H)]))
        self.assertIsNone(a["bbox"])
        self.assertIsNone(a["scaling"])
        flat = gp.analyse_frame(raw_of(framed([[0x7FFF] * 160 for _ in range(144)], 40, 8)))
        self.assertEqual(flat["size"], (160, 144))
        self.assertEqual((flat["scaling"]["col"]["verdict"], flat["scaling"]["row"]["verdict"]), ("NOT_EVALUABLE", "NOT_EVALUABLE"),
                         "a picture whose neighbours are all equal cannot discriminate: it must not read as 'no duplication'")

    def test_a_picture_elsewhere_and_a_stray_pixel_outside_the_box(self):
        g = framed(picture(random.Random(4), 100, 60), 17, 33)
        g[5][230] = 0x1234
        a = gp.analyse_frame(raw_of(g))
        self.assertEqual(a["bbox"], (17, 5, 230, 92))
        self.assertTrue(a["outside_is_border"])
        g2 = framed(picture(random.Random(4), 100, 60), 17, 33)
        a2 = gp.analyse_frame(raw_of(g2))
        self.assertEqual((a2["bbox"], a2["size"], a2["border"]), ((17, 33, 116, 92), (100, 60), {"left": 17, "top": 33, "right": 123, "bottom": 67}))

    def test_the_colours_are_decoded_r_high(self):
        g = framed([[0x6189] * 160 for _ in range(144)], 40, 8)
        a = gp.analyse_frame(raw_of(g))
        self.assertEqual(a["colours"][0], {"word": 0x6189, "count": 23040, "rgb5": (24, 12, 9)})

    def test_the_render_is_refused_outside_the_ignored_roots(self):
        with tempfile.TemporaryDirectory() as d:
            for target in (d, os.path.join(ROOT, "tools", "x"), os.path.join(ROOT, "docs", "y"), os.path.join(ROOT, "build", "analysis", "..", "..", "leak"),
                           os.path.join(ROOT, "captures", "fixtures")):
                with self.assertRaises(SystemExit, msg=target):
                    gp.render(FULL if os.path.exists(FULL) else __file__, target)
        self.assertEqual([os.path.relpath(r, ROOT) for r in gp.ALLOWED_RENDER_ROOTS], [os.path.join("captures", "local"), os.path.join("build", "analysis")])

    def test_a_symlink_out_of_the_ignored_roots_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            link = os.path.join(ROOT, "build", "analysis", "test_symlink_out")
            os.makedirs(os.path.dirname(link), exist_ok=True)
            try:
                os.symlink(d, link)
            except OSError:
                self.skipTest("symlinks unavailable")
            try:
                with self.assertRaises(SystemExit):
                    gp.render(FULL if os.path.exists(FULL) else __file__, link)
            finally:
                os.unlink(link)

    def test_render_without_a_directory_is_a_usage_error_not_a_crash(self):
        self.assertEqual(gp.main(["gbmode_picture.py", "x.bin", "--render"]), 2)

    def test_both_render_roots_are_ignored_by_git(self):
        for rel in ("captures/local/probe", "build/analysis/probe"):
            r = subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT)
            self.assertEqual(r.returncode, 0, rel + " is not ignored by Git")


class TheArchivedSidecarReadsAsRecorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (os.path.isfile(FULL) and os.path.isfile(IDXCAP)):
            raise unittest.SkipTest("no local archive on this host (captures/local is ignored)")
        for p, want in ((FULL, FULL_SHA), (IDXCAP, IDXCAP_SHA)):
            with open(p, "rb") as f:
                assert hashlib.sha256(f.read()).hexdigest() == want, "captures/local's RUN 59 sidecar is not the recorded one (a defect in the archive, never a skip)"
        cls.a = gp.analyse(FULL)

    def test_the_geometry_and_the_border(self):
        a = self.a
        self.assertEqual(a["records"], 8)
        self.assertEqual(a["union_bbox"], (40, 8, 199, 151))
        self.assertEqual(a["border_words"], [0x0000])
        self.assertTrue(a["all_outside_is_border"])
        boxes = [f["bbox"] for f in a["frames"]]
        self.assertEqual(boxes, [(40, 8, 199, 151), (110, 70, 129, 82), (80, 44, 159, 102), (83, 43, 156, 116), None, (40, 8, 199, 151), (40, 8, 199, 151), (131, 92, 139, 103)])
        full = [f for f in a["frames"] if f["bbox"] == (40, 8, 199, 151)]
        self.assertEqual([f["sample"] for f in full], [0, 5, 6])
        for f in full:
            self.assertEqual((f["size"], f["border"]), ((160, 144), {"left": 40, "top": 8, "right": 40, "bottom": 8}))
        self.assertEqual([f["inside_border_word_pixels"] for f in full], [0, 0, 518])

    def test_the_colours(self):
        fr = self.a["frames"]
        self.assertEqual([f["distinct_words"] for f in fr], [3, 4, 5, 6, 2, 11, 14, 5])
        self.assertEqual([f["distinct_colours"] for f in fr], [2, 3, 4, 5, 1, 10, 13, 4], "the flag-bit word 0x8000 at (0, 0) is a word, not a colour")
        self.assertEqual([(c["word"], c["count"]) for c in fr[0]["colours"]], [(0x7FFF, 23040), (0x0000, 15359), (0x8000, 1)])
        self.assertEqual([(c["word"], c["count"], c["rgb5"]) for c in fr[5]["colours"][:3]], [(0x0000, 15359, (0, 0, 0)), (0x6189, 6948, (24, 12, 9)), (0x0505, 4433, (1, 8, 5))])
        self.assertTrue(all(f["bit15_count"] == 1 and f["bit15_pixels"] == [(0, 0)] for f in fr), "bit 15 is set at pixel (0, 0) only, in every sample")

    def test_the_scaling_test_where_it_can_speak(self):
        v = {f["sample"]: (f["scaling"]["col"]["verdict"], f["scaling"]["row"]["verdict"]) if f["scaling"] else None for f in self.a["frames"]}
        clean = ("NO_PERIODIC_DUPLICATION", "NO_PERIODIC_DUPLICATION")
        ne = ("NOT_EVALUABLE", "NOT_EVALUABLE")
        self.assertEqual(v, {0: ne, 1: ne, 2: clean, 3: clean, 4: None, 5: clean, 6: clean, 7: ne})

    def test_the_duplication_test_finds_a_stretch_of_the_real_content_and_so_the_negative_means_something(self):
        """In memory only: samples 5 and 6's own 160 x 144 pixels, nearest-neighbour stretched to the whole window (nothing is stored)."""
        import vfull
        info = vfull.load(FULL)
        for si in (5, 6):
            px = gp.pixels(info["records"][si]["raw"])
            pic = [row[40:200] for row in px[8:152]]
            g = [[pic[min(143, (y * 144) // 160)][min(159, (x * 160) // 240)] for x in range(W)] for y in range(H)]
            box = (0, 0, W - 1, H - 1)
            v = gp.scaling(g, box)
            self.assertTrue(v["col"]["verdict"].startswith("DUPLICATION_AT_PERIOD_3"), v["col"]["verdict"])
            self.assertIn("10", v["row"]["verdict"])
            self.assertEqual(gp.scaling(px, (40, 8, 199, 151))["col"]["verdict"], "NO_PERIODIC_DUPLICATION")

    def test_the_rates_the_record_quotes(self):
        for si in (5, 6):
            import vfull
            px = gp.pixels(vfull.load(FULL)["records"][si]["raw"])
            box = (40, 8, 199, 151)
            for m in (2, 3):
                r = gp.phase_rates(px, box, "col", m)
                self.assertTrue(all(0.78 <= v <= 0.81 for v in r), r)
            for m in (9, 10):
                r = gp.phase_rates(px, box, "row", m)
                self.assertTrue(all(0.70 <= v <= 0.87 for v in r), r)
                self.assertLess(max(r), 0.99)

    def test_the_printed_block_in_the_record_is_the_tools_current_output(self):
        with open(DOC, encoding="utf-8") as f:
            d = f.read()
        i = d.index("### V29.13 RUN 59's picture")
        blk = d[d.index("```text\nGBMODE PICTURE", i) + len("```text\n"):]
        blk = blk[:blk.index("\n```")]
        self.assertEqual(blk, gp.format_report(self.a))

    def test_the_family_tools_are_inconclusive_by_construction(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "vfull.py"), "analyse", FULL], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout[-400:])
        self.assertEqual(r.stdout.count("INCONCLUSIVE: STRIP-L inconsistent"), 8)
        self.assertIn("VERDICT INCONCLUSIVE -- 8 sample(s) inconclusive", r.stdout)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "vindex.py"), "sidecar", IDXCAP], capture_output=True, text=True)
        self.assertIn("INVALID_CANONICAL_STRIP  2048", r.stdout)
        self.assertIn("VERDICT                INCONCLUSIVE_TOO_FEW_INTACT_FRAMES", r.stdout)

    def test_the_preserved_texture_equals_the_conversion_of_the_raw(self):
        import vfull
        info = vfull.load(FULL)
        self.assertEqual(len(info["records"]), 8)
        for r in info["records"]:
            self.assertEqual(r["tex"], vfull.convert_py(r["raw"]), "sample %d" % r["sample_index"])


class TheRecordStatesTheLimits(unittest.TestCase):
    def sect(self, path, head):
        with open(path, encoding="utf-8") as f:
            d = f.read()
        i = d.index(head)
        j = d.find("\n### ", i + 1)
        return " ".join(d[i:j if j > 0 else len(d)].split())

    def test_the_section_and_the_entry_carry_their_limits(self):
        s = self.sect(DOC, "### V29.13 RUN 59's picture")
        for tok in ("INCONCLUSIVE BY CONSTRUCTION", "No retail picture enters the repository", "the black border cannot be told from the picture's own black",
                    "at least 160 x 144", "his answer D is set beside the decode AFTER", "GBP-HW-131", "no oracle", "Pan Docs"):
            self.assertIn(tok, s, tok)
        e = self.sect(EVID, "### GBP-HW-379 ")
        for tok in ("promotes nothing into `docs/hardware/` or `docs/protocol/`", "FACT", "INFERENCE", "no retail picture"):
            self.assertIn(tok, e, tok)


if __name__ == "__main__":
    unittest.main()
