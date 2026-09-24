"""GBP-VIDEO-003: the OGBPCOL1 parser and the offline colour analyser.

Every file here is SYNTHETIC. No hardware has run this experiment, the stimulus
ROM has never reached an AGB, and nothing in this file is evidence about the
device: these tests check that the ANALYSER would reach the right conclusion, and
refuse to reach one, from bytes whose meaning the test itself chose.

The corpus is built by painting the eight bars into a real 40 x 0xF00 frame and
then writing a real OGBPCOL1 file around it, so the parser, the reconstruction
and the decision are exercised on the same bytes a console would produce.
"""
import os
import re
import struct
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import vcolor                                                          # noqa: E402

BIN = os.path.join(ROOT, "build", "tests", "unit", "test_gbp_vcolor")
OUTDIR = os.path.join(ROOT, "build", "tests", "unit")

HEADER_SIZE = vcolor.HEADER_SIZE
FRAME_REC = vcolor.FRAME_REC
CERT_REC = vcolor.CERT_REC
BLOCKS = vcolor.BLOCKS
BLOCK_SIZE = vcolor.BLOCK_SIZE
FRAME_BYTES = vcolor.FRAME_BYTES
WIDTH, HEIGHT = vcolor.WIDTH, vcolor.HEIGHT


def paint(values, flag_first_word=True, mirror=False, damage=None):
    """One 40 x 0xF00 frame holding the eight bars, in the GBP's own wire shape:
    four bytes per pixel, the word in bytes 1 and 3, bytes 0 and 2 carrying
    something that must never reach the decision."""
    vals = list(reversed(values)) if mirror else list(values)
    frame = bytearray(FRAME_BYTES)
    for y in range(HEIGHT):
        block, row = divmod(y, 4)
        base = block * BLOCK_SIZE + row * WIDTH * 4
        for x in range(WIDTH):
            w = vals[x // vcolor.BAR_W]
            if flag_first_word and y == 0 and x == 0:
                w |= 0x8000                      # the frame-start flag, where the references put it
            g = base + x * 4
            frame[g + 0] = 0x5A                  # a byte no reference consumes
            frame[g + 1] = (w >> 8) & 0xFF
            frame[g + 2] = 0xA5                  # ditto
            frame[g + 3] = w & 0xFF
    if damage:
        x, y, value = damage
        block, row = divmod(y, 4)
        g = block * BLOCK_SIZE + row * WIDTH * 4 + x * 4
        frame[g + 1] = (value >> 8) & 0xFF
        frame[g + 3] = value & 0xFF
    return bytes(frame)


def build_file(frame_bytes, cert_count=3, frame_records=3, certified=True,
               raw_frames=None, slots=None, orders=None, raw_unrecoverable=False,
               hold_flag=False, hold_cfg=0, hold_frames=0, hold_seen=0, retired_reason=0,
               audio_raw=0):
    """A real OGBPCOL1 file around the given frame(s).

    `cert_count` defaults to THREE now, because the design certifies on three and
    the analyser refuses to map anything until all three are present and equal.
    `raw_frames` overrides the raw section frame by frame, which is how the
    signature-collision case is built: three certified records whose bytes are
    NOT the same."""
    from avseq import crc32
    frames = b""
    for i in range(frame_records):
        r = bytearray(FRAME_REC)
        struct.pack_into(">Q", r, 0x00, 1000 + i)
        struct.pack_into(">Q", r, 0x08, 1100 + i)
        struct.pack_into(">I", r, 0x10, i)
        struct.pack_into(">I", r, 0x14, BLOCKS)
        struct.pack_into(">H", r, 0x18, 0x0001)
        struct.pack_into(">H", r, 0x1A, 0)
        struct.pack_into(">I", r, 0x1C, i + 1)
        frames += bytes(r)
    cert = b""
    for i in range(cert_count):
        r = bytearray(CERT_REC)
        struct.pack_into(">Q", r, 0x00, 1000 + i)
        struct.pack_into(">Q", r, 0x08, 1100 + i)
        struct.pack_into(">I", r, 0x10, i)
        struct.pack_into(">I", r, 0x14, BLOCKS)
        struct.pack_into(">I", r, 0x18, i * FRAME_BYTES)
        struct.pack_into(">H", r, 0x1C, (slots[i] if slots else i))
        struct.pack_into(">H", r, 0x1E, (orders[i] if orders else i))
        struct.pack_into(">I", r, 0x20, 0x11110000 + i)
        struct.pack_into(">I", r, 0x24, 0x22220000 + i)
        cert += bytes(r)
    if raw_frames is not None:
        raw = b"".join(raw_frames)
    else:
        raw = frame_bytes * cert_count

    h = bytearray(HEADER_SIZE)
    h[0:8] = vcolor.MAGIC
    struct.pack_into(">H", h, 0x008, 1)
    struct.pack_into(">H", h, 0x00A, HEADER_SIZE)
    flags = 0x0001 | 0x0002 | (0x0004 if certified else 0)
    if hold_flag:
        flags |= 0x0008
    if raw_unrecoverable:
        flags |= 0x0080
    struct.pack_into(">I", h, 0x00C, flags)
    struct.pack_into(">I", h, 0x010, 40500000)
    struct.pack_into(">I", h, 0x014, frame_records)
    struct.pack_into(">I", h, 0x018, cert_count)
    struct.pack_into(">I", h, 0x01C, 0)
    struct.pack_into(">I", h, 0x020, audio_raw)
    struct.pack_into(">I", h, 0x024, BLOCK_SIZE)
    struct.pack_into(">I", h, 0x028, 0x1000)
    struct.pack_into(">I", h, 0x02C, BLOCKS)
    struct.pack_into(">H", h, 0x030, FRAME_REC)
    struct.pack_into(">H", h, 0x032, CERT_REC)
    struct.pack_into(">H", h, 0x034, 160)
    struct.pack_into(">H", h, 0x03A, 3)
    struct.pack_into(">H", h, 0x03C, 3)
    struct.pack_into(">H", h, 0x03E, hold_cfg)
    struct.pack_into(">I", h, 0x15C, hold_frames)
    struct.pack_into(">I", h, 0x160, hold_seen)
    struct.pack_into(">I", h, 0x170 + 4 * vcolor.RETIRED_PRE_BASELINE, retired_reason)
    for off, name in ((0x040, b"GBP-VIDEO-003"), (0x060, b"color-0001"),
                      (0x080, b"gbp-video-color-probe"), (0x0A0, b"synthetic")):
        h[off:off + len(name)] = name
    off_frames = HEADER_SIZE
    off_cert = off_frames + len(frames)
    off_diag = off_cert + len(cert)
    off_video = off_diag
    off_audio = off_video + len(raw)
    audio = b"\x5A" * (audio_raw * 0x1000)
    off_footer = off_audio + len(audio)
    struct.pack_into(">I", h, 0x0C0, off_frames)
    struct.pack_into(">I", h, 0x0C4, off_cert)
    struct.pack_into(">I", h, 0x0C8, off_diag)
    struct.pack_into(">I", h, 0x0CC, off_video)
    struct.pack_into(">I", h, 0x0D0, off_audio)
    struct.pack_into(">I", h, 0x0D4, off_footer)
    struct.pack_into(">I", h, 0x1FC, crc32(bytes(h[:0x1FC])))
    body = bytes(h) + frames + cert + raw + audio
    return body + vcolor.FOOTER + struct.pack(">I", crc32(body))


def observed(values, **kw):
    """The analyser's verdict for a frame painted with `values`."""
    d = vcolor.parse(build_file(paint(values, **kw)))
    return vcolor.analyse(d)


class Hypotheses(unittest.TestCase):
    """Section 31/32: the candidate transformations, applied to the eight known
    stimulus values, compared exactly."""

    def test_every_hypothesis_predicts_a_distinct_vector(self):
        vectors = [tuple(h["expected"]) for h in vcolor.expected_vectors()]
        self.assertEqual(len(set(vectors)), len(vectors))

    def test_the_low_bit_bars_are_what_make_H4_falsifiable(self):
        """Section 33, mechanically: with only the three full-group bars and the
        two references, identity and intra-group reversal are INDISTINGUISHABLE.
        The three single-bit bars are the entire reason the design can refuse H4."""
        hs = vcolor.expected_vectors()
        by_name = {h["name"]: h["expected"] for h in hs}
        first_five = {n: tuple(v[:5]) for n, v in by_name.items()}
        self.assertEqual(first_five["H2_identity"], first_five["H4_intra_group_reversal"])
        self.assertEqual(first_five["H1_outer_group_swap"], first_five["H1_H4"])
        # and with all eight they separate
        self.assertNotEqual(tuple(by_name["H2_identity"]), tuple(by_name["H4_intra_group_reversal"]))
        self.assertNotEqual(tuple(by_name["H1_outer_group_swap"]), tuple(by_name["H1_H4"]))

    def test_black_and_white_are_fixed_points_of_every_bit_permutation(self):
        """Section 34. 0x0000 and 0x7FFF are fixed by every hypothesis that PERMUTES
        the fifteen colour bits, so they cannot identify one - which is precisely
        what makes them controls for the failures a permutation cannot explain.

        Two candidates are not colour-bit permutations and the controls do catch
        them: the complement inverts both, and a BYTE swap crosses the flag
        boundary - the high byte holds only seven colour bits, so 0x7FFF comes back
        as 0x7F7F with one bit lost. That is a real property of the transformation,
        not a defect of the control."""
        permutations = ("H1_outer_group_swap", "H2_identity", "H4_intra_group_reversal", "H1_H4")
        for name, _, fn in vcolor.HYPOTHESES:
            if name in permutations:
                self.assertEqual(fn(0x0000), 0x0000, name)
                self.assertEqual(fn(0x7FFF), 0x7FFF, name)
        self.assertEqual(vcolor._complement(0x0000), 0x7FFF)
        self.assertEqual(vcolor._complement(0x7FFF), 0x0000)
        self.assertEqual(vcolor._byte_swap(0x0000), 0x0000)
        self.assertEqual(vcolor._byte_swap(0x7FFF), 0x7F7F)


class SyntheticCorpus(unittest.TestCase):
    """Section 39: one painted frame per outcome the analyser must produce."""

    def test_identity(self):
        a = observed([vcolor._identity(v) for v in vcolor.STIMULUS])
        self.assertEqual(a["verdict"], "resolved")
        self.assertEqual(a["mapping"], "H2_identity")

    def test_outer_group_swap(self):
        a = observed([vcolor._swap_outer(v) for v in vcolor.STIMULUS])
        self.assertEqual(a["verdict"], "resolved")
        self.assertEqual(a["mapping"], "H1_outer_group_swap")

    def test_byte_swap(self):
        a = observed([vcolor._byte_swap(v) for v in vcolor.STIMULUS])
        self.assertEqual(a["verdict"], "resolved")
        self.assertEqual(a["mapping"], "H3_byte_swap")

    def test_intra_group_reversal(self):
        a = observed([vcolor._intra_reverse(v) for v in vcolor.STIMULUS])
        self.assertEqual(a["verdict"], "resolved")
        self.assertEqual(a["mapping"], "H4_intra_group_reversal")

    def test_complement(self):
        a = observed([vcolor._complement(v) for v in vcolor.STIMULUS])
        self.assertEqual(a["verdict"], "resolved")
        self.assertEqual(a["mapping"], "H5_complement")

    def test_no_hypothesis_fits(self):
        """A transformation nobody proposed: the analyser must say so and stop,
        not pick the nearest candidate."""
        weird = [(v ^ 0x2222) & 0x7FFF for v in vcolor.STIMULUS]
        a = observed(weird)
        self.assertEqual(a["verdict"], "inconclusive_no_hypothesis")
        self.assertEqual(a["survivors"], [])

    def test_a_bar_that_is_not_uniform(self):
        a = observed(list(vcolor.STIMULUS), damage=(35, 77, 0x1234))
        self.assertEqual(a["verdict"], "inconclusive_bar_not_uniform")
        bad = [b for b in a["bars"] if not b["uniform"]]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["bar"], 1)
        self.assertEqual(bad[0]["first_divergence"], (35, 77))
        self.assertEqual(bad[0]["values"][0x1234], 1)

    def test_a_mirrored_frame_is_reported_not_corrected(self):
        """Section 30: if x were mirrored the invariant bars would move, and the
        analyser must say the orientation is wrong rather than flip the data."""
        a = observed(list(vcolor.STIMULUS), mirror=True)
        self.assertFalse(a["orientation"]["consistent"])
        self.assertEqual(a["orientation"]["zero_bar"], [7])
        self.assertEqual(a["orientation"]["all_ones_bar"], [3])
        self.assertTrue(a["orientation"]["mirror_would_fit"])

    def test_the_verdict_names_its_limits(self):
        a = observed(list(vcolor.STIMULUS))
        self.assertEqual(a["verdict"], "resolved")
        text = " ".join(a["limits"])
        self.assertIn("do NOT pin a permutation", text)
        self.assertIn("bits 1-4", text)
        self.assertIn("mode 3", text)


class Flag15(unittest.TestCase):
    """Section 27/37: bit 15 is mapped separately and never folded into colour."""

    def test_the_flag_is_split_from_the_colour(self):
        a = observed(list(vcolor.STIMULUS))
        self.assertEqual(a["verdict"], "resolved")          # the flag did not disturb bar 0
        f = a["flag15"]
        self.assertEqual(f["total"], 1)
        self.assertTrue(f["first_word_of_block0"])
        self.assertTrue(f["only_first_word"])
        self.assertEqual(f["per_block"][0], 1)
        self.assertEqual(sum(f["per_block"][1:]), 0)

    def test_without_the_flag_nothing_claims_one(self):
        a = observed(list(vcolor.STIMULUS), flag_first_word=False)
        self.assertEqual(a["flag15"]["total"], 0)
        self.assertFalse(a["flag15"]["only_first_word"])

    def test_a_flag_on_every_pixel_does_not_change_the_colour_decision(self):
        d = vcolor.parse(build_file(paint([v | 0x8000 for v in vcolor.STIMULUS],
                                          flag_first_word=False)))
        a = vcolor.analyse(d)
        self.assertEqual(a["verdict"], "resolved")
        self.assertEqual(a["mapping"], "H2_identity")
        self.assertEqual(a["flag15"]["total"], WIDTH * HEIGHT)


class ByteOrder(unittest.TestCase):
    """Section 36: b1 and b3 are preserved and reported, so H3 is testable
    without transforming the raw."""

    def test_b1_and_b3_are_reported_per_bar(self):
        a = observed(list(vcolor.STIMULUS))
        for bar in a["bars"]:
            v = vcolor.STIMULUS[bar["bar"]]
            expected_b1 = (v >> 8) & 0xFF
            if bar["bar"] == 0:
                expected_b1 |= 0x80          # bar 0 starts at the frame-start flag
            self.assertEqual(bar["b1"], expected_b1, bar["bar"])
            self.assertEqual(bar["b3"], v & 0xFF, bar["bar"])

    def test_the_discarded_bytes_are_preserved_and_never_used(self):
        d = vcolor.parse(build_file(paint(list(vcolor.STIMULUS))))
        grid = vcolor.frame_words(d, 0)
        self.assertEqual(grid["discarded"][0][0], (0x5A, 0xA5))
        self.assertEqual(grid["discarded"][159][239], (0x5A, 0xA5))
        # and they do not enter the decision
        self.assertEqual(vcolor.analyse(d)["mapping"], "H2_identity")


class ReferenceComparison(unittest.TestCase):
    """Section 38: the comparison is stated after the measurement, never used to
    make it."""

    def test_each_outcome_has_its_own_reading(self):
        swap = " ".join(vcolor.reference_comparison("H1_outer_group_swap"))
        ident = " ".join(vcolor.reference_comparison("H2_identity"))
        other = " ".join(vcolor.reference_comparison("H3_byte_swap"))
        for text in (swap, ident, other):
            self.assertIn("bits 14-10", text)
        self.assertIn("displayed truth", swap)
        self.assertIn("render AGB red as blue", ident)
        self.assertIn("open an unknown", other)


class TheRuntimeCannotRecogniseTheStimulus(unittest.TestCase):
    """THE CIRCULARITY GATE (§V3.11, and §26 of the implementation contract).

    The eight stimulus values belong to the ROM and to this analyser. If the
    GameCube runtime held them, it could decide that it had found the pattern -
    and that decision would be the experiment's own answer used as its input.
    So the runtime is checked for the two constants that appear nowhere else in
    this project: 0x03E0 and 0x7C00. Every other stimulus value collides with a
    legitimate mask or a small integer (0x0000, 0x0001, 0x001F, 0x0020, 0x0400,
    0x7FFF), which is why these two carry the check."""

    RUNTIME = ("src/gbp/gbp_vcolor.c", "src/gbp/gbp_vcolor.h",
               "src/gbp/gbp_vcoldump.c", "src/gbp/gbp_vcoldump.h",
               "src/gbp/gbp_vstate_probe.c", "src/gbp/gbp_vstate.c",
               "poc/gbp-video-color-probe/source/main.c")

    def test_no_stimulus_constant_is_in_the_runtime(self):
        import re
        pattern = re.compile(r"0x0*(3e0|7c00)\b", re.IGNORECASE)
        for rel in self.RUNTIME:
            path = os.path.join(ROOT, rel)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    self.assertIsNone(pattern.search(line), "%s:%d holds a stimulus value: %s"
                                      % (rel, n, line.strip()))

    def test_the_analyser_is_where_they_live(self):
        with open(os.path.join(ROOT, "tools", "vcolor.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("0x03E0", text)
        self.assertIn("0x7C00", text)
        self.assertEqual(vcolor.STIMULUS,
                         (0x0000, 0x001F, 0x03E0, 0x7C00, 0x7FFF, 0x0001, 0x0020, 0x0400))
        with open(os.path.join(ROOT, "stimulus", "agb-color-bars", "source", "main.c"),
                  encoding="utf-8") as f:
            rom = f.read()
        for v in ("0x0000u", "0x001Fu", "0x03E0u", "0x7C00u", "0x7FFFu", "0x0001u", "0x0020u", "0x0400u"):
            self.assertIn(v, rom)

    def test_the_stimulus_never_sets_bit_15(self):
        """Section 7/§V3.4: with bit 15 always zero in VRAM, any flag the window
        carries is demonstrably not the colour value."""
        for v in vcolor.STIMULUS:
            self.assertEqual(v & 0x8000, 0, "%04x" % v)


@unittest.skipUnless(os.path.isfile(BIN), "build the unit tests first (make -C tests/unit)")
class WrittenByTheRealWriter(unittest.TestCase):
    """The C writer and the Python parser must agree on the same bytes: the file
    the console would produce is the file this tool reads."""

    def setUp(self):
        self.path = os.path.join(OUTDIR, "vcolor-host.bin")
        subprocess.run([BIN, "--dump", self.path], check=True, capture_output=True)
        with open(self.path, "rb") as f:
            self.data = f.read()
        self.d = vcolor.parse(self.data)

    def test_it_parses_and_carries_what_the_writer_said(self):
        self.assertEqual(self.d["version"], 1)
        self.assertEqual(self.d["test_id"], "GBP-VIDEO-003")
        self.assertEqual(self.d["build_id"], "color-0001")
        self.assertEqual(self.d["cert_count"], 3)
        self.assertEqual(self.d["frame_count"], 3)
        self.assertEqual(self.d["diag_count"], 1)
        self.assertIn("certified", self.d["flag_names"])
        self.assertEqual(len(self.d["cert"]), 3)
        for i, c in enumerate(self.d["cert"]):
            self.assertEqual(c["blocks"], BLOCKS)
            self.assertEqual(c["raw_offset"], i * FRAME_BYTES)

    def test_the_shared_r3_record_survives_the_other_container(self):
        """Section 21: the RECORD is shared with OGBPSEQ1 v5, the CONTAINER is not."""
        g = self.d["diags"][0]
        self.assertEqual(g["disc_value"], 0x0500)
        self.assertEqual(g["gbi_value"], 0x0100)
        self.assertEqual(g["delta"], 0x0400)
        self.assertEqual(g["classification"], "source_serviced")
        self.assertEqual(g["authoritative_value"], 0x0100)
        self.assertEqual(g["ack_value"], 0x8100)
        self.assertEqual(g["record_flags"], 0x01C1)
        self.assertEqual(g["followup_state_code"], 1)
        # and it recomputes from its own raw bytes, exactly as in the vstate file
        import vstate
        raw = bytes(g["raw"])
        self.assertEqual(vstate.read_disc(raw), 0x0500)
        self.assertEqual(vstate.read_gbi(raw), 0x0100)

    def test_the_cli_reports_without_deciding(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "vcolor.py"), "info", self.path],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OGBPCOL1 v1", r.stdout)
        self.assertIn("THE COLOUR MAPPING IS NOT IN THIS FILE", r.stdout)

    def test_the_analyser_refuses_bytes_that_are_not_the_stimulus(self):
        """The C writer paints an arbitrary pattern, not the colour bars. The
        analyser must decline to conclude anything from it - which is exactly what
        protects the experiment from a flash-cart menu that happened to hold
        still for three frames."""
        a = vcolor.analyse(self.d)
        self.assertIn(a["verdict"], ("inconclusive_bar_not_uniform", "inconclusive_no_hypothesis"))


class CertifiedRawEquality(unittest.TestCase):
    """§V3.25: the runtime decides its window from sig[40]; the BYTES are decided
    here. These tests exist to prove that the cheap runtime check is safe only
    because this expensive offline one exists."""

    def test_three_equal_frames_pass_the_gate_and_reach_the_mapping(self):
        d = vcolor.parse(build_file(paint(vcolor.STIMULUS)))
        eq = vcolor.certified_raw_equal(d)
        self.assertTrue(eq["ok"])
        self.assertEqual(eq["n"], 3)
        self.assertIsNone(eq["first_diff"])
        self.assertEqual(vcolor.analyse(d)["verdict"], "resolved")

    def test_a_signature_collision_is_caught_offline(self):
        """The decisive case. Three certified records, so the runtime believed it
        had three identical frames; one raw byte differs, so it did not. No
        colour mapping may be attempted from that."""
        good = paint(vcolor.STIMULUS)
        bad = bytearray(good)
        bad[BLOCK_SIZE * 7 + 41] ^= 0x20
        d = vcolor.parse(build_file(good, raw_frames=[good, good, bytes(bad)]))
        eq = vcolor.certified_raw_equal(d)
        self.assertFalse(eq["ok"])
        self.assertEqual(eq["first_diff"]["pair"], (0, 2))
        self.assertEqual(eq["first_diff"]["block"], 7)
        # §32: the coordinate is derivable, so it is reported
        fd = eq["first_diff"]
        self.assertEqual(fd["offset"], BLOCK_SIZE * 7 + 41)
        self.assertEqual(fd["y"], 7 * 4 + (41 // (240 * 4)))
        self.assertEqual(fd["x"], (41 % (240 * 4)) // 4)
        self.assertEqual(fd["byte_in_group"], 1)
        self.assertTrue(fd["consumed"])
        a = vcolor.analyse(d)
        self.assertEqual(a["verdict"], "inconclusive_certified_raw_mismatch")
        # §31: NOTHING downstream of the gate was computed
        for k in ("observed", "bars", "flag15", "candidates", "orientation"):
            self.assertNotIn(k, a)
        text = vcolor.analyse_text(d)
        self.assertIn("CERTIFIED RAW MISMATCH", text)
        self.assertIn("x=", text)
        self.assertNotIn("H2_identity", text)

    def test_the_second_frame_is_checked_too(self):
        good = paint(vcolor.STIMULUS)
        bad = bytearray(good)
        bad[0] ^= 0xFF
        d = vcolor.parse(build_file(good, raw_frames=[good, bytes(bad), good]))
        eq = vcolor.certified_raw_equal(d)
        self.assertFalse(eq["ok"])
        self.assertEqual(eq["first_diff"]["pair"], (0, 1))
        self.assertEqual(eq["first_diff"]["offset"], 0)

    def test_fewer_than_three_certified_frames_never_maps(self):
        for n in (1, 2):
            d = vcolor.parse(build_file(paint(vcolor.STIMULUS), cert_count=n))
            self.assertFalse(vcolor.certified_raw_equal(d)["ok"])
            self.assertEqual(vcolor.analyse(d)["verdict"], "inconclusive_certified_raw_mismatch")

    def test_the_gate_runs_before_any_interpretation(self):
        """§31: the order is parse, availability, byte equality, geometry, bars,
        hypotheses. A spy on the geometry step proves nothing downstream of the
        gate is even reached when the bytes disagree."""
        good = paint(vcolor.STIMULUS)
        bad = bytearray(good)
        bad[123] ^= 0x01
        d = vcolor.parse(build_file(good, raw_frames=[good, good, bytes(bad)]))
        calls = []
        real = vcolor.frame_words
        vcolor.frame_words = lambda *a, **k: (calls.append(a), real(*a, **k))[1]
        try:
            a = vcolor.analyse(d)
        finally:
            vcolor.frame_words = real
        self.assertEqual(a["verdict"], "inconclusive_certified_raw_mismatch")
        self.assertEqual(calls, [], "frame_words must not run once the gate failed")
        # and with equal bytes the same spy shows it DOES run
        d2 = vcolor.parse(build_file(good))
        calls2 = []
        vcolor.frame_words = lambda *a, **k: (calls2.append(a), real(*a, **k))[1]
        try:
            vcolor.analyse(d2)
        finally:
            vcolor.frame_words = real
        self.assertEqual(len(calls2), 1)

    def test_a_certified_run_whose_ring_slots_were_lost(self):
        """The runtime certified but could not recover the bytes. The file says
        so, carries no raw, and the analyser reports it instead of guessing."""
        d = vcolor.parse(build_file(paint(vcolor.STIMULUS), cert_count=0, raw_unrecoverable=True))
        a = vcolor.analyse(d)
        self.assertEqual(a["verdict"], "no_certified_frame")
        self.assertIn("raw_unrecoverable", a["why"])


class RetiredFields(unittest.TestCase):
    """The hold window and the PRE_BASELINE refusal are gone. A file that uses
    either was written by a producer this parser does not describe."""

    def _refused(self, **kw):
        with self.assertRaises(ValueError):
            vcolor.parse(build_file(paint(vcolor.STIMULUS), **kw))

    def test_the_hold_flag_is_refused(self):
        self._refused(hold_flag=True)

    def test_the_hold_counters_are_refused(self):
        self._refused(hold_cfg=60)
        self._refused(hold_frames=1)
        self._refused(hold_seen=1)

    def test_the_retired_refusal_reason_is_refused(self):
        self._refused(retired_reason=1)

    def test_the_audio_raw_cap(self):
        for n in (0, 1, 2, 3):
            d = vcolor.parse(build_file(paint(vcolor.STIMULUS), audio_raw=n))
            self.assertEqual(d["audio_raw_count"], n)
        with self.assertRaises(ValueError):
            vcolor.parse(build_file(paint(vcolor.STIMULUS), audio_raw=4))

    def test_raw_unrecoverable_may_not_sit_next_to_raw(self):
        self._refused(raw_unrecoverable=True)

    def test_a_certified_flag_without_raw_needs_the_explanation(self):
        with self.assertRaises(ValueError):
            vcolor.parse(build_file(paint(vcolor.STIMULUS), cert_count=0, certified=True))


class CertifiedRecordIdentity(unittest.TestCase):
    """§19: a certified frame must be identifiable without the frame table, and
    two of them may never name the same bytes."""

    def test_the_record_carries_slot_order_and_signatures(self):
        d = vcolor.parse(build_file(paint(vcolor.STIMULUS), slots=[2, 3, 0]))
        self.assertEqual([c["ring_slot"] for c in d["cert"]], [2, 3, 0])
        self.assertEqual([c["order"] for c in d["cert"]], [0, 1, 2])
        self.assertEqual(d["cert"][1]["sig0"], 0x11110001)
        self.assertEqual(d["cert"][2]["sig39"], 0x22220002)

    def test_a_slot_that_cannot_exist_is_refused(self):
        with self.assertRaises(ValueError):
            vcolor.parse(build_file(paint(vcolor.STIMULUS), slots=[0, 1, vcolor.RING_SLOTS_MAX]))

    def test_a_wrong_certification_order_is_refused(self):
        with self.assertRaises(ValueError):
            vcolor.parse(build_file(paint(vcolor.STIMULUS), orders=[0, 2, 1]))


class TimingContract(unittest.TestCase):
    """The microaudit blocked the first implementation because the capture did
    full-frame work between the ACK and the RE-ARM. These tests read the runtime
    source and refuse to let that come back."""

    RUNTIME = ["src/gbp/gbp_vcolor.c", "src/gbp/gbp_vcolor.h"]

    def _src(self):
        out = ""
        for f in self.RUNTIME:
            with open(os.path.join(ROOT, f)) as fh:
                out += fh.read()
        return out

    def test_the_capture_module_calls_no_bulk_memory_operation(self):
        """memcmp, memcpy and memmove over a frame cannot appear here at all. The
        one memset is the init of a fixed-size struct, which is bounded by its
        own type."""
        src = self._src()
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("*"))
        for bad in ("memcmp", "memmove"):
            self.assertNotIn(bad, code, "%s must not appear in the capture module" % bad)
        self.assertNotIn("memcpy", code, "memcpy must not appear in the capture module")

    def test_the_hook_cannot_receive_frame_bytes(self):
        """A parameter is a capability. gbp_vcolor_frame() takes a slot INDEX, so
        there is no pointer through which 153 600 bytes could reach it."""
        with open(os.path.join(ROOT, "src/gbp/gbp_vcolor.h")) as fh:
            h = fh.read()
        decl = h[h.index("int gbp_vcolor_frame("):]
        decl = decl[:decl.index(";")]
        self.assertIn("int slot", decl)
        self.assertNotIn("uint8_t", decl)
        self.assertNotIn("raw", decl)

    def test_the_probe_does_not_read_the_ring_in_the_service_path(self):
        """gbp_vstate_closed_frame_raw() returns a pointer and is the expensive
        form. The service path must use the slot form."""
        with open(os.path.join(ROOT, "src/gbp/gbp_vstate_probe.c")) as fh:
            src = fh.read()
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("*"))
        self.assertIn("gbp_vstate_closed_frame_slot", code)
        self.assertNotIn("gbp_vstate_closed_frame_raw", code)


class PreHandlerWait(unittest.TestCase):
    """§V3.28: the fixed pre-handler wait belongs to THIS experiment and to no
    other build, and enabling it changed nothing about the format, the stimulus
    or the analyser."""

    def _read(self, rel):
        with open(os.path.join(ROOT, rel)) as f:
            return f.read()

    def test_the_colour_build_asks_for_5000_ms(self):
        h = self._read("src/gbp/gbp_vcolor.h")
        m = re.search(r"#define\s+GBP_VCOLOR_PREHANDLER_WAIT_MS\s+(\d+)u", h)
        self.assertIsNotNone(m, "the colour build declares no pre-handler wait")
        self.assertEqual(int(m.group(1)), 5000)
        poc = self._read("poc/gbp-video-color-probe/source/main.c")
        self.assertIn("cfg.prehandler_wait_ms = GBP_VCOLOR_PREHANDLER_WAIT_MS;", poc)

    def test_the_shared_default_is_still_zero(self):
        """Every other build must be unaffected: the probe's own default is 0,
        so nothing inherits this experiment's procedure by accident."""
        c = self._read("src/gbp/gbp_vstate_probe.c")
        self.assertIn("cfg->prehandler_wait_ms = 0u;", c)

    def test_no_other_poc_enables_a_wait(self):
        enabled = []
        pocdir = os.path.join(ROOT, "poc")
        for d in sorted(os.listdir(pocdir)):
            main = os.path.join(pocdir, d, "source", "main.c")
            if not os.path.exists(main):
                continue
            text = open(main).read()
            if "prehandler_wait_ms" not in text:
                continue
            if d == "gbp-video-color-probe":
                continue
            # GBP-VIDEO-004 USED to reuse the physically validated 5000 ms,
            # because §V5.20 said a streaming capture must not open inside the
            # cartridge's boot. §V5.52 separated the two questions: the capture
            # still must not open inside the boot, but the OPERATOR should see
            # the boot, so the wait became a property of the startup PROFILE.
            # The normal profile asks for zero and the diagnostic profile for
            # the value GBP-HW-120 validated. What this guard still enforces is
            # the thing it was written for: no POC invents a wait of its own.
            # Issue #39: the playable image is built from the stream probe and takes the wait from the same profile
            # Issue #59: and the audio window image is built from the playable one, with the same line
            # Issue #84: and so is the drain image (§V19.11 A4.1), line for line
            # Issue #92: and so is the live image (Phase 6's acceptance, built on the drain image)
            # Issue #101: and so is Run A's image, live-0001 with the recorder (§V23)
            # Issue #105: and Run B's, trace-0001 with production split (§V24)
            # Issue #110: and the real-cartridge image, live-0001 with §V25's changes
            if d in ("gbp-video-stream-probe", "gbp-play-session", "gbp-audio-window-probe", "gbp-audio-drain-probe",
                     "gbp-audio-live", "gbp-audio-trace", "gbp-audio-split", "gbp-audio-game"):
                self.assertIn("cfg.prehandler_wait_ms = startup.prehandler_wait_ms;", text)
                self.assertNotIn("cfg.prehandler_wait_ms = 5000u;", text)
                h = self._read("src/gbp/gbp_startup.h")
                self.assertIn("#define GBP_STARTUP_DIAGNOSTIC_WAIT_MS 5000u", h)
                self.assertIn("s->prehandler_wait_ms = 0u;", h)
                continue
            # the vstate POC carries the diagnostic hook, whose default is 0 and
            # which only a dedicated diagnostic build overrides
            if d == "gbp-video-state-probe":
                self.assertIn("#define GBP_VSTATE_PREHANDLER_WAIT_MS 0", text)
                continue
            enabled.append(d)
        self.assertEqual(enabled, [], "these POCs set a pre-handler wait: %s" % enabled)

    def test_the_wait_is_not_in_the_service_loop(self):
        """It sits between stage A and the handler install. If it ever moved
        into the loop it would be delaying live transactions."""
        c = self._read("src/gbp/gbp_vstate_probe.c")
        wait = c.index("res->prehandler_wait_ms = cfg->prehandler_wait_ms;")
        install = c.index("res->h.install_rc = t->irq_install")
        loop = c.index("/* ---- CHECK_ADMISSION")
        stage_a = c.index("crc = gbp_initirqa_run_cause(")
        self.assertLess(stage_a, wait, "the wait must come after stage A")
        self.assertLess(wait, install, "the wait must come before the handler install")
        self.assertLess(install, loop, "the service loop must come after both")

    def test_no_controller_input_reaches_the_probe(self):
        """Arming by button was rejected (§V3.27), so the run must not depend on
        one. The shared probe has no PAD at all; in the colour POC the only
        controller reads before the run are PAD_Init and the fatal-transport
        gate, which exits instead of continuing."""
        self.assertNotIn("PAD_", self._read("src/gbp/gbp_vstate_probe.c"))
        poc = self._read("poc/gbp-video-color-probe/source/main.c")
        run = poc.index("gbp_vstate_probe_run(")
        fatal_exit = poc.rindex("exit(1);", 0, run)
        # nothing between the last abort path and the run may touch the controller:
        # that is the stretch a real run actually executes
        live = poc[fatal_exit:run]
        self.assertNotIn("PAD_", live,
                         "a controller read was added on the path that reaches the run")
        # and every PAD before that point is one of the known, non-scientific uses
        for hit in re.finditer(r"PAD_[A-Za-z_]+", poc[:fatal_exit]):
            self.assertIn(hit.group(0),
                          ("PAD_Init", "PAD_ScanPads", "PAD_ButtonsDown", "PAD_BUTTON_START"),
                          hit.group(0))

    def test_the_frozen_format_did_not_move(self):
        self.assertEqual(vcolor.CERT_REC, 40)
        self.assertEqual(vcolor.FRAME_REC, 48)
        self.assertEqual(vcolor.DIAG_REC, 160)
        self.assertEqual(vcolor.HEADER_SIZE, 0x200)
        self.assertEqual(vcolor.VERSION, 1)
        h = self._read("src/gbp/gbp_vcoldump.h")
        self.assertIn("#define GBP_VCOLDUMP_CERT_REC     40u", h)
        self.assertIn("#define GBP_VCOLDUMP_VERSION      1u", h)

    def test_the_experiment_itself_did_not_move(self):
        self.assertEqual(list(vcolor.STIMULUS), [0x0000, 0x001F, 0x03E0, 0x7C00, 0x7FFF,
                                                 0x0001, 0x0020, 0x0400])
        self.assertEqual(len(vcolor.HYPOTHESES), 7)
        h = self._read("src/gbp/gbp_vcolor.h")
        self.assertIn("#define GBP_VCOLOR_N_STABLE      3u", h)
        self.assertIn("#define GBP_VCOLOR_BLOCKS        40u", h)

    def test_the_runtime_still_does_not_know_the_stimulus(self):
        """Enabling a wait must not have smuggled the answer into the runtime."""
        for rel in ("src/gbp/gbp_vcolor.c", "src/gbp/gbp_vcolor.h",
                    "poc/gbp-video-color-probe/source/main.c"):
            code = "\n".join(l for l in self._read(rel).splitlines()
                              if not l.strip().startswith(("*", "/*", "//")))
            for value in ("0x03E0", "0x7C00", "0x7FFF"):
                self.assertNotIn(value, code, "%s now contains %s" % (rel, value))


class PhysicalColor0001(unittest.TestCase):
    """The first physical GBP-VIDEO-003 run, pinned against its versioned sidecar.

    This class asserts what was MEASURED, not what it means. The official gate
    did not pass on this run, so nothing here closes U-GBP-011: the bar vector
    below is a post-gate diagnostic projection and is labelled as one wherever
    the project writes it down.
    """

    SIDECAR = os.path.join(ROOT, "captures", "fixtures",
                           "hw-gamecube-gbp-2026-09-18-color-0001-color.bin")
    SHA256 = "95595f9d9eb4945e42ee1653ade5a1cd72a3646d698cad254d32c84ba0762bb7"
    STIMULUS = (0x0000, 0x001F, 0x03E0, 0x7C00, 0x7FFF, 0x0001, 0x0020, 0x0400)
    # H1: exchange bits 14-10 with bits 4-0, green (bits 9-5) fixed
    H1 = (0x0000, 0x7C00, 0x03E0, 0x001F, 0x7FFF, 0x0400, 0x0020, 0x0001)

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(cls.SIDECAR):
            raise unittest.SkipTest("physical color-0001 sidecar missing")
        with open(cls.SIDECAR, "rb") as f:
            cls.raw = f.read()
        cls.d = vcolor.parse(cls.raw)
        cls.frames = [vcolor.raw_frame(cls.d, i) for i in range(3)]

    def test_the_fixture_is_the_ingested_bytes(self):
        import hashlib
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), self.SHA256)

    def test_the_official_gate_still_refuses_this_run(self):
        """Regression against a silent reinterpretation: if someone ever relaxes
        certified_raw_equal(), this run must stop being INCONCLUSIVE loudly."""
        r = vcolor.certified_raw_equal(self.d)
        self.assertFalse(r["ok"])
        self.assertEqual(r["n"], 3)
        fd = r["first_diff"]
        self.assertEqual(fd["pair"], (0, 1))
        self.assertEqual(fd["offset"], 0x108)
        self.assertEqual((fd["block"], fd["x"], fd["y"]), (0, 66, 0))
        self.assertEqual((fd["a"], fd["b"]), (0x83, 0x03))
        # the analyser already says it itself: the byte that stopped the run is
        # one neither reference decoder reads
        self.assertEqual(fd["byte_in_group"], 0)
        self.assertFalse(fd["consumed"])

    def test_every_raw_difference_is_in_a_byte_no_decoder_reads(self):
        counts = {}
        for a, b in ((0, 1), (1, 2), (0, 2)):
            c = [0, 0, 0, 0]
            x, y = self.frames[a], self.frames[b]
            for i in range(0, len(x), 4):
                for k in range(4):
                    if x[i + k] != y[i + k]:
                        c[k] += 1
            counts[(a, b)] = c
        self.assertEqual(counts[(0, 1)], [1878, 0, 247, 0])
        self.assertEqual(counts[(1, 2)], [1815, 0, 258, 0])
        self.assertEqual(counts[(0, 2)], [1860, 0, 277, 0])

    def test_the_consumed_projection_is_identical_in_all_three_frames(self):
        """word = (b1 << 8) | b3 is not invented here: GBP-VID-003 recorded it
        from both reference decoders on 2026-09-16, before this run."""
        proj = [[(f[i] << 8) | f[i + 2] for i in range(1, len(f), 4)] for f in self.frames]
        self.assertEqual(len(proj[0]), 240 * 160)
        self.assertEqual(proj[0], proj[1])
        self.assertEqual(proj[1], proj[2])

    def test_flag15_is_one_word_per_frame_at_the_origin_over_a_black_pixel(self):
        for f in self.frames:
            w = [(f[i] << 8) | f[i + 2] for i in range(1, len(f), 4)]
            hits = [i for i, v in enumerate(w) if v & 0x8000]
            self.assertEqual(hits, [0])
            # the first run in which bit 15 is separable from the colour: the
            # earlier physical frames all had 0xFFFF here, where it is not
            self.assertEqual(w[0], 0x8000)

    def test_the_post_gate_diagnostic_bar_vector(self):
        for f in self.frames:
            w = [((f[i] << 8) | f[i + 2]) & 0x7FFF for i in range(1, len(f), 4)]
            for bar in range(8):
                seen = {w[y * 240 + x] for y in range(160)
                        for x in range(bar * 30, bar * 30 + 30)}
                self.assertEqual(len(seen), 1, "bar %d is not uniform" % bar)
                self.assertEqual(seen.pop(), self.H1[bar])
        # H2, the verbatim AGB reading, survives only on the swap-invariant bars
        agree = sum(1 for b in range(8) if self.H1[b] == self.STIMULUS[b])
        self.assertEqual(agree, 4)

    def test_the_run_certified_three_frames(self):
        self.assertEqual(len(self.d["cert"]), 3)
        self.assertEqual([c["frame_index"] for c in self.d["cert"]], [2, 3, 4])
        self.assertEqual([c["blocks"] for c in self.d["cert"]], [40, 40, 40])
        self.assertEqual([c["ring_slot"] for c in self.d["cert"]], [2, 3, 0])


if __name__ == "__main__":
    unittest.main()
