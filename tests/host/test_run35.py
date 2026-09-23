"""tests/host/test_run35.py — RUN 35 ingested (Issue #85, GBP-AUDIO-006, HARDWARE_TESTS §V20).

The verdict first, as the Issue required of the ingestion: `question_L_bits`
returned LINEAR, and `GBP-HW-305` is FACT on it. Every figure §V20 quotes is
recomputed here from the archived sidecar when it is on this machine; the page's
own claims and the promotion are pinned from the sources, and never skip.

Three things are checked because they are the ones an ingestion can get wrong
quietly:

  * that the WRITE HAPPENED — GBP-HW-300 means a failed write leaves the previous
    run's files looking exactly like this run's, so RUN 35's bytes are compared
    against RUN 33's and RUN 34's, not just hashed;
  * that the gate is the one frozen BEFORE the run, byte for byte;
  * that RUN 34 is compared by THE SAME instrument — a first draft of §V20 quoted
    RUN 31's V=15 as RUN 34's, and this pins the correction.
"""
import hashlib
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frozen  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
LOCAL = os.path.join(ROOT, "captures", "local")
B35 = os.path.join(LOCAL, "GBP-AUDIO-006_stream-0016-run35-audio.bin")
L35 = os.path.join(LOCAL, "GBP-AUDIO-006_stream-0016-run35.log")
B34 = os.path.join(LOCAL, "GBP-AUDIO-003_stream-0016-run34-audio.bin")

SHA_BIN = "258790a4c43c901b9255273a537fdf73226a17fca1a76e626631c5890d38d7b6"
SHA_LOG = "7e7fc90752285a1c98bd78e19f74edd2d5ba312d38cde3e1946df5a423a2d493"
# the previous runs' bytes: a failed write would leave THESE in RUN 35's place
PRIOR = {"RUN 33 sidecar": "cfe472d36ba6040ecbedf9adfc601b73b501d401f363ccc78c20cafa136252b8",
         "RUN 33 log": "8c9d085e2ff3b043e292390103030eea34a26e5aeed5ff62143f4da943c3721e",
         "RUN 34 sidecar": "4db12f2ea62fee633c131b6bd38d971e6b60b1d2f9dae775eeb3ef17e20c58b0",
         "RUN 34 log": "b184311246a6d91df7915a5fdbf61f4b2f54ee24b75eadb508da0bdb012cb8af"}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def part():
    t = read(HW)
    i = t.index("\n## V20 — RUN 35 INGESTED")
    j = t.find("\n## V21 ", i)
    return t[i:] if j < 0 else t[i:j]


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class ThePageStatesTheVerdictFirst(unittest.TestCase):

    def test_the_verdict_leads_the_part(self):
        p = part()
        first = p[:p.index("### V20.1")]
        self.assertIn("`question_L_bits`\nreturned `LINEAR`", first)
        self.assertIn("before any commentary", first)

    def test_the_hashes_and_the_prior_runs_are_on_the_page(self):
        p = part()
        for h in (SHA_BIN, SHA_LOG):
            self.assertIn(h, p)
        for h in PRIOR.values():
            self.assertIn(h[:8], p, "§V20 must name the prior bytes it ruled out")
        self.assertIn("New bytes", p)

    def test_the_waits_are_said_to_be_kept_for_repetition_not_belief(self):
        """§V15.9 found the 20 s wait and the 5 s gaps have no job left. The Issue asked
        that their presence be said, explicitly, not to be belief."""
        p = re.sub(r"\s+", " ", part())
        self.assertIn("kept for REPETITION, not belief", p)
        self.assertIn("no known job left", p)
        self.assertIn("must never be read as such", p)

    def test_the_same_instrument_correction_is_recorded(self):
        p = re.sub(r"\s+", " ", part())
        self.assertIn("the same bit-resolution instrument", p)
        self.assertIn("29.9883", p)
        self.assertIn("RUN 31's V=15", p)
        self.assertNotIn("RUN 34 measured the same four volumes at 30.0625", p)


class GBP_HW_305_IsFACT(unittest.TestCase):

    def entry(self):
        t = read(EV)
        i = t.index("### GBP-HW-305 ")
        return t[i:t.index("\n### GBP-HW-306 ", i)]

    def test_the_heading_carries_a_dated_pointer_to_FACT_and_keeps_its_words(self):
        h = self.entry().splitlines()[0]
        # the original words stay, per the amend-on-top convention (Issue #49)
        self.assertIn("**CORROBORATED, not FACT**", h)
        # and the LAST bold segment is the pointer: a date, the Issue, the status now held
        segs = re.findall(r"\*\*([^*]+)\*\*", h)
        self.assertTrue(segs[-1].startswith("2026-09-23, Issue #85: FACT"), segs[-1])

    def test_the_body_says_which_two_objections_this_run_closed(self):
        b = re.sub(r"\s+", " ", self.entry())
        self.assertIn("different run and a different ROM", b)
        self.assertIn("the pre-registered gate declined", b)
        self.assertIn("one instrument, one cartridge and one console", b)
        self.assertIn("`U-GBP-012` is not closed by this", b)


class TheGateIsTheOneFrozenBeforeTheRun(unittest.TestCase):

    def test_v16bitgate_is_the_bytes_of_the_commit_that_froze_it(self):
        then = frozen.source("Issue #79 -- GBP-HW-305 decided", "tools/v16bitgate.py")
        self.assertEqual(then, read(os.path.join(ROOT, "tools", "v16bitgate.py")),
                         "the gate that judged RUN 35 was edited after it was frozen")


class TheArchiveRecomputes(unittest.TestCase):
    """Only where the raw run is archived; the page's figures are pinned above regardless."""

    def setUp(self):
        if not (os.path.exists(B35) and os.path.exists(L35)):
            self.skipTest("RUN 35 is not archived in this checkout (captures/local is ignored)")

    def test_the_archived_copies_are_the_recorded_bytes(self):
        self.assertEqual((os.path.getsize(B35), sha(B35)), (5243788, SHA_BIN))
        self.assertEqual((os.path.getsize(L35), sha(L35)), (90756, SHA_LOG))

    def test_the_write_happened(self):
        """GBP-HW-300: the previous run's files would look exactly like this run's."""
        got = {sha(B35), sha(L35)}
        for name, h in PRIOR.items():
            self.assertNotIn(h, got, "RUN 35 carries %s's bytes: the write did not happen" % name)

    def test_the_three_crc_channels_agree(self):
        import awinparse
        h, _a, _o = awinparse.parse(open(B35, "rb").read())
        self.assertEqual(h["total_crc32"], 0x6B1E8337)
        self.assertIn("total_crc=6b1e8337", read(L35))

    def test_question_L_bits_is_LINEAR_with_the_quoted_rows(self):
        import awinparse
        import v16bitgate as g
        _, _, a, w = awinparse.load(B35)
        k = [x["keys"] for x in a if x["kind"] == 1]
        r = g.question_L_bits(w[1:], k)
        self.assertEqual(r["verdict"], "LINEAR")
        self.assertAlmostEqual(r["anchor"] * 256, 29.8594, places=4)
        got = [(row["volume"], round(row["measured"] * 256, 4)) for row in r["rows"]]
        self.assertEqual(got, [(11, 21.9883), (7, 13.9922), (3, 5.9336)])
        self.assertEqual(r["order"]["verdict"], "ORDERED")

    def test_the_older_gates_repeat_RUN_34(self):
        import awinparse
        import v11sweep as v
        _, _, a, w = awinparse.load(B35)
        k = [x["keys"] for x in a if x["kind"] == 1]
        self.assertEqual(v.question_V(w[1:], k)["verdict"], "INCONCLUSIVE")
        self.assertEqual(v.question_E(w[1:], k, "V")["verdict"], "LEVELS DIFFER, NOT ORDERED")

    def test_RUN_34_by_the_same_instrument_is_within_0_19_bytes(self):
        if not os.path.exists(B34):
            self.skipTest("RUN 33 or RUN 34 is not archived in this checkout")
        import awinparse
        import v16bitgate as g
        dev = {}
        for lab, p in (("34", B34), ("35", B35)):
            _, _, a, w = awinparse.load(p)
            dev[lab] = [d * 256 for d in g.question_V_bits(w[1:], [x["keys"] for x in a if x["kind"] == 1])["deviations"]]
        self.assertAlmostEqual(dev["34"][0], 29.9883, places=4, msg="RUN 34's V=15, not RUN 31's 30.0625")
        self.assertLess(max(abs(a - b) for a, b in zip(dev["34"], dev["35"])), 0.19)


if __name__ == "__main__":
    unittest.main()
