"""tools/vcolor2.py — the pre-registered color-0002 analysis contract.

The one thing this contract must never do is make `color-0001` pass. It was
written after that run, with its bytes already known, so any path by which it
could retroactively confirm the hypothesis would make it worthless. The tests
below check the contract's gate, its refusals and its hypothesis handling, and
they check the two structural guarantees that keep it honest: the historical
analyser is untouched and still refuses `color-0001`, and a file from any build
other than `color-0002` can only ever come back RETROSPECTIVE.
"""
import os
import struct
import subprocess
import sys
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vcolor                                                           # noqa: E402
import vcolor2                                                          # noqa: E402
from test_vcolor import paint, build_file, BLOCK_SIZE, FRAME_BYTES, WIDTH, HEIGHT  # noqa: E402

STIM = vcolor.STIMULUS
H1 = tuple(((v & 0x1F) << 10) | (v & 0x03E0) | ((v >> 10) & 0x1F) for v in STIM)
PHYSICAL = os.path.join(ROOT, "captures", "fixtures",
                        "hw-gamecube-gbp-2026-09-18-color-0001-color.bin")


def with_build_id(blob, build_id):
    """The same file, re-stamped with a build id, both CRCs repaired."""
    b = bytearray(blob)
    b[0x060:0x080] = build_id.encode().ljust(0x20, b"\0")[:0x20]
    struct.pack_into(">I", b, 0x1FC, vcolor.crc32(bytes(b[:0x1FC])))
    body = bytes(b[:-12])
    return body + vcolor.FOOTER + struct.pack(">I", vcolor.crc32(body))


def analyse(frames, build_id="color-0002"):
    """`frames` is one frame (used for all three) or an explicit list of three."""
    if isinstance(frames, (bytes, bytearray)):
        frames = [frames] * 3
    blob = with_build_id(build_file(frames[0], raw_frames=list(frames)), build_id)
    return vcolor2.analyse(vcolor.parse(blob))


def bump(frame, x, y, byte_in_group, delta):
    """Change one byte of one pixel group, leaving everything else alone."""
    f = bytearray(frame)
    block, row = divmod(y, 4)
    g = block * BLOCK_SIZE + row * WIDTH * 4 + x * 4 + byte_in_group
    f[g] ^= delta
    return bytes(f)


class HistoricalVerdictIsPreserved(unittest.TestCase):
    """§2 and §9: color-0001 stays INCONCLUSIVE, permanently and reproducibly."""

    @unittest.skipUnless(os.path.isfile(PHYSICAL), "physical color-0001 sidecar missing")
    def test_the_frozen_analyser_still_refuses_the_physical_run(self):
        d = vcolor.parse(open(PHYSICAL, "rb").read())
        a = vcolor.analyse(d)
        self.assertEqual(a["verdict"], "inconclusive_certified_raw_mismatch")
        self.assertNotIn("mapping", a)

    @unittest.skipUnless(os.path.isfile(PHYSICAL), "physical color-0001 sidecar missing")
    def test_the_frozen_analyser_cli_still_prints_the_same_verdict(self):
        """The CLI, with no options, is what the record cites."""
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "vcolor.py"),
                            "analyse", PHYSICAL], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("INCONCLUSIVE - CERTIFIED RAW MISMATCH", r.stdout)

    def test_vcolor2_never_reaches_into_the_frozen_analysers_decision(self):
        """vcolor2 reuses vcolor's PARSER and its pre-registered hypotheses, and
        overrides nothing: the shared objects must be the same objects."""
        self.assertIs(vcolor2.vcolor.HYPOTHESES, vcolor.HYPOTHESES)
        self.assertIs(vcolor2.vcolor.STIMULUS, vcolor.STIMULUS)
        self.assertIs(vcolor2.vcolor.analyse, vcolor.analyse)

    def test_the_two_contracts_disagree_about_the_physical_run_on_purpose(self):
        if not os.path.isfile(PHYSICAL):
            self.skipTest("physical color-0001 sidecar missing")
        d = vcolor.parse(open(PHYSICAL, "rb").read())
        self.assertFalse(vcolor.certified_raw_equal(d)["ok"])       # the old gate fails
        self.assertTrue(vcolor2.consumed_words_equal(d)["ok"])      # the new gate passes
        # and that is exactly why the new one may not judge this run
        self.assertFalse(vcolor2.analyse(d)["confirmatory"])


class Standing(unittest.TestCase):
    """§14: a file that predates the contract can never come back confirmed."""

    def test_a_color_0001_build_id_is_retrospective(self):
        a = analyse(paint(H1), build_id="color-0001")
        self.assertFalse(a["confirmatory"])
        self.assertEqual(a["standing"], "RETROSPECTIVE / NON-CONFIRMATORY")
        self.assertTrue(a["verdict"].startswith("retrospective_exact_"))
        self.assertNotIn("confirmed", a["verdict"])

    def test_an_unset_build_id_is_retrospective(self):
        a = analyse(paint(H1), build_id="")
        self.assertFalse(a["confirmatory"])
        self.assertTrue(a["verdict"].startswith("retrospective_"))

    def test_only_color_0002_can_confirm(self):
        a = analyse(paint(H1), build_id="color-0002")
        self.assertTrue(a["confirmatory"])
        self.assertEqual(a["verdict"], "confirmed_exact_H1_outer_group_swap")

    @unittest.skipUnless(os.path.isfile(PHYSICAL), "physical color-0001 sidecar missing")
    def test_the_report_for_the_physical_run_says_it_confirms_nothing(self):
        text = vcolor2.analyse_text(vcolor.parse(open(PHYSICAL, "rb").read()))
        self.assertIn("RETROSPECTIVE / NON-CONFIRMATORY", text)
        self.assertIn("THIS CONFIRMS NOTHING", text)
        self.assertIn("U-GBP-011 is unaffected", text)
        self.assertNotIn("VERDICT: CONFIRMED", text)


class TheGate(unittest.TestCase):
    """§4B: 38 400 consumed words, bit 15 included, nothing masked."""

    def test_it_compares_exactly_thirty_eight_thousand_four_hundred_words(self):
        a = analyse(paint(H1))
        self.assertEqual(a["consumed_words_equal"]["compared"], 38400)
        self.assertEqual(vcolor2.CONSUMED_WORDS, WIDTH * HEIGHT)
        self.assertEqual(len(vcolor2.consumed_words(paint(H1))), 38400)

    def test_the_consumed_projection_is_exactly_bytes_one_and_three(self):
        f = paint(H1)
        c = vcolor2.consumed_bytes(f)
        self.assertEqual(len(c), FRAME_BYTES // 2)
        self.assertEqual(c, bytes(f[i] for i in range(len(f)) if i % 2 == 1))
        self.assertEqual(c, bytes(f[i] for i in range(len(f)) if i % 4 in (1, 3)))

    def test_bytes_zero_and_two_alone_never_fail_the_gate(self):
        """The whole reason this contract exists. Change every discarded byte in
        every group of frames B and C and the gate must still pass."""
        a = paint(H1)
        b = bytes((v ^ 0xFF) if i % 4 in (0, 2) else v for i, v in enumerate(a))
        c = bytes((v ^ 0x5A) if i % 4 in (0, 2) else v for i, v in enumerate(a))
        self.assertNotEqual(a, b)
        self.assertNotEqual(b, c)
        res = analyse([a, b, c])
        self.assertTrue(res["consumed_words_equal"]["ok"])
        self.assertEqual(res["verdict"], "confirmed_exact_H1_outer_group_swap")
        # and the full-raw diagnostic still REPORTS the difference, loudly
        self.assertFalse(res["full_raw_diagnostic"]["equal"])
        self.assertEqual(res["full_raw_diagnostic"]["by_byte_in_group"][1], 0)
        self.assertEqual(res["full_raw_diagnostic"]["by_byte_in_group"][3], 0)
        self.assertGreater(res["full_raw_diagnostic"]["by_byte_in_group"][0], 0)
        self.assertGreater(res["full_raw_diagnostic"]["by_byte_in_group"][2], 0)

    def test_one_bit_of_byte_one_fails_the_gate(self):
        a = paint(H1)
        res = analyse([a, bump(a, 100, 50, 1, 0x01), a])
        self.assertFalse(res["consumed_words_equal"]["ok"])
        self.assertEqual(res["verdict"], "inconclusive_consumed_word_mismatch")
        fd = res["consumed_words_equal"]["first_diff"]
        self.assertEqual((fd["x"], fd["y"]), (100, 50))
        self.assertEqual(fd["byte_in_group"], 1)
        self.assertNotIn("observed", res)                # it stopped before mapping

    def test_one_bit_of_byte_three_fails_the_gate(self):
        a = paint(H1)
        res = analyse([a, a, bump(a, 7, 159, 3, 0x01)])
        self.assertFalse(res["consumed_words_equal"]["ok"])
        self.assertEqual(res["verdict"], "inconclusive_consumed_word_mismatch")
        self.assertEqual(res["consumed_words_equal"]["first_diff"]["byte_in_group"], 3)
        self.assertNotIn("observed", res)

    def test_bit_fifteen_alone_fails_the_gate_and_is_not_masked(self):
        """§4B says bit 15 is inside the gate. A frame that differs ONLY in the
        flag - same colour everywhere - must still be refused."""
        a = paint(H1)
        b = bump(a, 3, 2, 1, 0x80)                       # set bit 15 of one pixel
        res = analyse([a, b, a])
        self.assertFalse(res["consumed_words_equal"]["ok"])
        self.assertEqual(res["verdict"], "inconclusive_consumed_word_mismatch")
        fd = res["consumed_words_equal"]["first_diff"]
        self.assertTrue(fd["differs_in_flag15"])
        self.assertFalse(fd["differs_in_color15"])       # colour identical, still refused
        self.assertNotIn("observed", res)

    def test_fewer_than_three_certified_frames_is_refused(self):
        blob = with_build_id(build_file(paint(H1), cert_count=1, frame_records=1), "color-0002")
        a = vcolor2.analyse(vcolor.parse(blob))
        self.assertFalse(a["consumed_words_equal"]["ok"])
        self.assertEqual(a["verdict"], "inconclusive_certified_frame_count")


class Flag15(unittest.TestCase):
    """§5: counted, located, required stable — and never interpreted."""

    def test_a_stable_flag_map_passes_and_is_reported(self):
        a = analyse(paint(H1))
        self.assertEqual(a["flag15"]["status"], "FLAG15_STABLE")
        self.assertTrue(a["flag15"]["stable"])
        self.assertEqual(a["flag15"]["counts"], [1, 1, 1])
        self.assertEqual(a["flag15"]["coords"][0], [(0, 0)])

    def test_a_flag_count_of_zero_is_not_required(self):
        """Physical evidence already shows one set flag per frame (GBP-HW-125),
        so a contract demanding zero would refuse every real run."""
        with_flag = analyse(paint(H1, flag_first_word=True))
        without = analyse(paint(H1, flag_first_word=False))
        self.assertEqual(with_flag["verdict"], "confirmed_exact_H1_outer_group_swap")
        self.assertEqual(without["verdict"], "confirmed_exact_H1_outer_group_swap")
        self.assertEqual(with_flag["flag15"]["counts"], [1, 1, 1])
        self.assertEqual(without["flag15"]["counts"], [0, 0, 0])
        self.assertFalse(with_flag["flag15"]["zero_required"])

    def test_many_flags_are_still_accepted_if_stable(self):
        """The contract asks for stability, not for a particular count."""
        f = bytearray(paint(H1, flag_first_word=False))
        for x in range(0, WIDTH, 17):                    # a scattered, reproducible bitmap
            f[x * 4 + 1] |= 0x80
        a = analyse(bytes(f))
        self.assertEqual(a["flag15"]["status"], "FLAG15_STABLE")
        self.assertEqual(a["flag15"]["counts"][0], len(range(0, WIDTH, 17)))
        self.assertEqual(a["verdict"], "confirmed_exact_H1_outer_group_swap")

    def test_the_report_refuses_to_explain_the_flag(self):
        text = vcolor2.analyse_text(vcolor.parse(
            with_build_id(build_file(paint(H1), raw_frames=[paint(H1)] * 3), "color-0002")))
        self.assertIn("FLAG15_STABLE", text)
        self.assertIn("nothing here claims a meaning", text)
        for word in ("frame start", "frame-start", "vblank", "means", "indicates"):
            self.assertNotIn(word, text.split("C. FLAG15")[1].split("D. BARS")[0].lower())


class Bars(unittest.TestCase):
    """§6: eight bars, one colour15 each, with the flag already split off."""

    def test_a_non_uniform_bar_is_refused(self):
        a = analyse(paint(H1, damage=(95, 40, 0x1234)))
        self.assertEqual(a["verdict"], "inconclusive_bar_not_uniform")
        self.assertNotIn("observed", a)

    def test_the_flag_pixel_does_not_make_bar_zero_non_uniform(self):
        """x=0,y=0 carries 0x8000 over a black bar. Split before analysis, bar 0
        is still one colour; if the split were missing this would be two."""
        a = analyse(paint(H1, flag_first_word=True))
        self.assertTrue(a["bars"][0]["uniform"])
        self.assertEqual(a["bars"][0]["value"], 0x0000)
        self.assertEqual(a["flag15"]["counts"], [1, 1, 1])


class HypothesisContract(unittest.TestCase):
    """§7 and §8: exact equality, one survivor, no score, and H1 falsifiable."""

    def test_exactly_h1_confirms(self):
        a = analyse(paint(H1))
        self.assertEqual(a["survivors"], ["H1_outer_group_swap"])
        self.assertEqual(a["verdict"], "confirmed_exact_H1_outer_group_swap")
        self.assertEqual(a["observed"], list(H1))

    def test_h1_is_falsifiable_by_this_contract(self):
        """§8: the contract must be able to come back NOT-H1. A verbatim frame
        confirms H2 instead, and one bar off confirms nothing."""
        verbatim = analyse(paint(STIM))
        self.assertEqual(verbatim["verdict"], "confirmed_exact_H2_identity")
        self.assertEqual(verbatim["survivors"], ["H2_identity"])

    def test_no_hypothesis_is_inconclusive_not_nearest_fit(self):
        off = list(H1)
        off[6] = 0x0021                                  # one bit away from 0x0020
        a = analyse(paint(off))
        self.assertEqual(a["verdict"], "inconclusive_no_hypothesis")
        self.assertEqual(a["survivors"], [])
        self.assertNotIn("mapping", a)

    def test_the_stimulus_discriminates_every_pre_registered_hypothesis(self):
        """Two survivors cannot arise from this stimulus: no two of the seven
        transformations produce the same eight values. That is a property of the
        stimulus design, and it is why an ambiguous verdict would mean something
        went wrong rather than that the experiment was weak."""
        vectors = {n: tuple(f(v) for v in vcolor.STIMULUS) for n, _, f in vcolor.HYPOTHESES}
        self.assertEqual(len(set(vectors.values())), len(vcolor.HYPOTHESES))

    def test_two_hypotheses_are_inconclusive(self):
        """The refusal branch still has to be right. The pre-registered set cannot
        produce two survivors (above), so the branch is exercised against a
        deliberately degenerate set, patched for this test only and asserted back
        afterwards - the frozen tuple is never edited."""
        degenerate = vcolor.HYPOTHESES + (("H1_twin", "the same transformation again",
                                           vcolor.HYPOTHESES[1][2]),)
        with unittest.mock.patch.object(vcolor, "HYPOTHESES", degenerate):
            a = analyse(paint(H1))
        self.assertEqual(sorted(a["survivors"]), ["H1_outer_group_swap", "H1_twin"])
        self.assertEqual(a["verdict"], "inconclusive_ambiguous")
        self.assertNotIn("mapping", a)
        # the real set is exactly as it was
        self.assertEqual(len(vcolor.HYPOTHESES), 7)
        self.assertEqual([n for n, _, _ in vcolor.HYPOTHESES][1], "H1_outer_group_swap")

    def test_there_is_no_score_anywhere(self):
        a = analyse(paint(H1))
        blob = repr(a).lower()
        for word in ("score", "distance", "closest", "best", "nearest", "confidence"):
            self.assertNotIn(word, blob)
        for h in a["hypotheses"]:
            self.assertIsInstance(h["all"], bool)
            self.assertEqual(len(h["matches"]), 8)

    def test_the_hypotheses_and_stimulus_are_the_pre_registered_ones(self):
        """§7: not edited to fit color-0001. They are vcolor's own objects, and
        vcolor.py has not been modified since the implementation checkpoint."""
        self.assertEqual(list(vcolor.STIMULUS),
                         [0x0000, 0x001F, 0x03E0, 0x7C00, 0x7FFF, 0x0001, 0x0020, 0x0400])
        self.assertEqual([n for n, _, _ in vcolor.HYPOTHESES],
                         ["H2_identity", "H1_outer_group_swap", "H3_byte_swap",
                          "H4_intra_group_reversal", "H5_complement", "H1_H4", "H1_H3"])
        r = subprocess.run(["git", "log", "--oneline", "-1", "--", "tools/vcolor.py"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertIn("bfbca70", r.stdout, "tools/vcolor.py changed; the freeze claim is void")


class FrozenFormat(unittest.TestCase):
    """§10: OGBPCOL1 v1 carries everything this contract needs, unchanged."""

    def test_the_contract_needs_no_format_change(self):
        self.assertEqual(vcolor.VERSION, 1)
        self.assertEqual(vcolor.MAGIC, b"OGBPCOL1")
        self.assertEqual(vcolor.HEADER_SIZE, 0x200)
        self.assertEqual((vcolor.FRAME_REC, vcolor.CERT_REC, vcolor.DIAG_REC), (48, 40, 160))
        self.assertEqual(vcolor.MAX_CERT, 3)

    def test_everything_the_contract_reads_comes_from_v1(self):
        a = analyse(paint(H1))
        for key in ("build_id", "consumed_words_equal", "flag15", "bars",
                    "observed", "full_raw_diagnostic"):
            self.assertIn(key, a)

    def test_the_frozen_header_was_not_edited(self):
        r = subprocess.run(["git", "log", "--oneline", "-1", "--", "src/gbp/gbp_vcoldump.h"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertIn("e10423c", r.stdout, "the frozen OGBPCOL1 v1 header changed")


class RuntimeParity(unittest.TestCase):
    """§11: nothing about the contract reaches the runtime."""

    def _read(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_the_runtime_still_knows_none_of_the_expected_values(self):
        for rel in ("src/gbp/gbp_vcolor.c", "src/gbp/gbp_vcolor.h",
                    "src/gbp/gbp_vcoldump.c", "poc/gbp-video-color-probe/source/main.c"):
            code = "\n".join(l for l in self._read(rel).splitlines()
                             if not l.strip().startswith(("*", "/*", "//")))
            for value in ("0x03E0", "0x7C00", "0x7FFF", "0x001F"):
                self.assertNotIn(value, code, "%s now contains %s" % (rel, value))

    def test_the_runtime_signature_consumes_the_same_bytes_as_the_gate(self):
        """§11: the runtime's sig[40] already reads bytes 1 and 3 and nothing
        else, which is why it is a sound pre-filter for this gate."""
        sig = self._read("src/gbp/gbp_vsig.h")
        self.assertIn("byte 1 and byte 3", sig)
        self.assertIn("bytes 0 and 2 are never read", sig)

    def test_the_wait_is_still_five_thousand(self):
        h = self._read("src/gbp/gbp_vcolor.h")
        self.assertIn("#define GBP_VCOLOR_PREHANDLER_WAIT_MS   5000u", h)

    def test_n_stable_is_still_three(self):
        h = self._read("src/gbp/gbp_vcolor.h")
        self.assertIn("#define GBP_VCOLOR_N_STABLE", h)
        self.assertIn("3u", h.split("#define GBP_VCOLOR_N_STABLE")[1].splitlines()[0])


class Cli(unittest.TestCase):
    def test_contract_prints_without_a_file(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "vcolor2.py"), "contract"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        for section in ("A. TRANSPORT RAW DOMAIN", "B. CONSUMED-WORD STABILITY GATE",
                        "C. FLAG15", "D. COLOR MAPPING DOMAIN", "E. SUCCESS", "F. STANDING"):
            self.assertIn(section, r.stdout)

    @unittest.skipUnless(os.path.isfile(PHYSICAL), "physical color-0001 sidecar missing")
    def test_analyse_on_the_physical_fixture(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "vcolor2.py"),
                            "analyse", PHYSICAL], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("RETROSPECTIVE / NON-CONFIRMATORY", r.stdout)
        self.assertIn("PASS: 38400 of 38400", r.stdout)
        self.assertIn("RETROSPECTIVE_EXACT_H1_OUTER_GROUP_SWAP", r.stdout)


if __name__ == "__main__":
    unittest.main()
