"""tests/host/test_run33_34.py — GitHub Issue #78: RUN 33 and RUN 34 ingested.

Every figure §V15 states is RECOMPUTED here from the archived raws with the
frozen constructions, never quoted. The verdicts are asserted to be exactly what
the unedited tools return — including the INADMISSIBLE and the INCONCLUSIVE —
because the temptation this checkpoint names is to read past its own gates when
the data looks better than the prediction.

The raws live under captures/local/ and logs/, both ignored, so the
recomputations skip in a clone; the document checks run everywhere.
"""
import os
import re
import struct
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v11sweep as v  # noqa: E402
import v13sep  # noqa: E402
import v14repeat as r  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
LOCAL = os.path.join(ROOT, "captures", "local")
B33 = os.path.join(LOCAL, "GBP-AUDIO-004_stream-0016-run33-audio.bin")
B34 = os.path.join(LOCAL, "GBP-AUDIO-003_stream-0016-run34-audio.bin")
B32 = os.path.join(LOCAL, "GBP-AUDIO-003_stream-0016-run32-audio.bin")
GECKO = os.path.join(LOCAL, "GECKO-LIVE-run33-run34-orchestrator-capture.txt")
TB = 40500000.0


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s.replace("\n> ", " ")).replace("`", "").replace("**", "").replace("*", "")


def part():
    t = read(HW)
    i = t.index("\n## V15 ")
    j = t.find("\n## V", i + 1)
    return (t[i:j] if j >= 0 else t[i:]).lstrip("\n")


def load(p):
    if not os.path.exists(p):
        raise unittest.SkipTest("RUN 33 or RUN 34 is not archived in this checkout")
    import awinparse
    return awinparse.load(p)


def press(anc):
    return [a for a in anc if a["kind"] == 1]


class TheRawsAreArchivedAndTheIssuesTableWasSwapped(unittest.TestCase):

    def test_the_hashes_on_the_page_are_the_files_hashes(self):
        import hashlib
        want = {("run33", "GBP-AUDIO-001_stream-0016.log"): "8c9d085e2ff3b043e292390103030eea34a26e5aeed5ff62143f4da943c3721e",
                ("run33", "GBP-AUDIO-001_stream-0016-audio.bin"): "cfe472d36ba6040ecbedf9adfc601b73b501d401f363ccc78c20cafa136252b8",
                ("run34", "GBP-AUDIO-001_stream-0016.log"): "b184311246a6d91df7915a5fdbf61f4b2f54ee24b75eadb508da0bdb012cb8af",
                ("run34", "GBP-AUDIO-001_stream-0016-audio.bin"): "4db12f2ea62fee633c131b6bd38d971e6b60b1d2f9dae775eeb3ef17e20c58b0"}
        seen = 0
        for (run, name), h in want.items():
            self.assertIn(h, part())
            p = os.path.join(ROOT, "logs", run, name)
            if os.path.exists(p):
                with open(p, "rb") as f:
                    self.assertEqual(hashlib.sha256(f.read()).hexdigest(), h, p)
                seen += 1
        if not seen:
            self.skipTest("the raw drop is not in this checkout (logs/ is ignored)")

    def test_the_swapped_pairing_in_the_issue_is_named(self):
        s = plain(part())
        self.assertIn("pairs each hash with the wrong suffix", s)
        self.assertIn("cfe472d3… and 4db12f2e… are the audio sidecars", s)


class ThreeChannelsAgreeOnTheSidecarCRC(unittest.TestCase):

    def test_the_footer_crc_is_the_one_the_gecko_and_the_sd_log_carried(self):
        for p, want in ((B33, 0xD3DBD9A6), (B34, 0x4C45D84F)):
            if not os.path.exists(p):
                self.skipTest("RUN 33 or RUN 34 is not archived in this checkout")
            with open(p, "rb") as f:
                raw = f.read()
            self.assertEqual(raw[-12:-4], b"OGBPAWND")
            self.assertEqual(struct.unpack(">I", raw[-4:])[0], want)
        log33 = os.path.join(LOCAL, "GBP-AUDIO-004_stream-0016-run33.log")
        self.assertIn("crc=d3dbd9a6", read(log33))
        if os.path.exists(GECKO):
            g = read(GECKO)
            self.assertIn("crc=d3dbd9a6", g)
            self.assertIn("crc=4c45d84f", g)

    def test_the_live_capture_is_kept_with_its_provenance_and_out_of_the_log_population(self):
        s = plain(part())
        self.assertIn("an Orchestrator-side capture of the Operator's hardware, not a project artefact", s)
        self.assertIn("must not join the population GBP-HW-272 is defined over", s)
        self.assertFalse(os.path.exists(GECKO.replace(".txt", ".log")))


class TheSchedulesAndTheOffsets(unittest.TestCase):

    def test_both_schedules_derive_and_nothing_is_refused(self):
        for p, axis in ((B33, "F"), (B34, "V")):
            _, _, anc, _ = load(p)
            keys = [a["keys"] for a in press(anc)]
            self.assertEqual(v.derive_schedule(keys), axis)
            self.assertEqual(v.refusals(keys, axis), [])

    def test_the_measured_offsets(self):
        for p, want in ((B33, (0.0, 0.267, 1.852, 4.688)), (B34, (0.0, 5.105, 10.310, 15.766))):
            _, _, anc, _ = load(p)
            pr = press(anc)
            got = [(a["t_arm"] - pr[0]["t_arm"]) / TB for a in pr]
            for g, w in zip(got, want):
                self.assertAlmostEqual(g, w, delta=0.001)
        _, _, anc, _ = load(B33)
        pr = press(anc)
        offs = [(a["t_arm"] - pr[0]["t_arm"]) / TB for a in pr]
        self.assertEqual(v13sep.gaps_are_admissible(offs), [])


class TheFrozenVerdictsAreWhatTheyAre(unittest.TestCase):

    def test_every_press_window_carries_by_the_frozen_classifier(self):
        for p in (B33, B34):
            _, _, _, wins = load(p)
            self.assertEqual([v.classify_window(w)["state"] for w in wins[1:]], ["CARRIES"] * 4)
            self.assertEqual(v.classify_window(wins[0])["state"], "CARRIAGE FAILURE")  # a flat control

    def test_QUESTION_S_is_INADMISSIBLE(self):
        _, _, anc, wins = load(B33)
        pr = press(anc)
        offs = [(a["t_arm"] - pr[0]["t_arm"]) / TB for a in pr]
        carried = [v.classify_window(w)["state"] == "CARRIES" for w in wins[1:]]
        res = v13sep.question_S(offs, carried)
        self.assertEqual(res["verdict"], "INADMISSIBLE")
        self.assertIn("the emitting window itself carried", res["why"])

    def test_QUESTION_V_is_INCONCLUSIVE_and_for_the_phase_reason(self):
        _, _, anc, wins = load(B34)
        res = v.question_V(wins[1:], [a["keys"] for a in press(anc)])
        self.assertEqual(res["verdict"], "INCONCLUSIVE")
        self.assertEqual(res["why"], "a window has no two levels to measure a deviation from")
        self.assertEqual([c["state"] for c in res["windows"]], ["CARRIES"] * 4)
        self.assertIsNone(res["windows"][3]["deviation"])

    def test_the_two_runs_agree_at_BIT_level_and_disagree_at_BYTE_level(self):
        import collections
        _, _, _, w32 = load(B32)
        _, _, _, w34 = load(B34)

        def levels(w, f, scale):
            c = collections.Counter(round(f(b) * scale) for b in w[v.ONSET_SLICE_BLOCKS:])
            return sorted(k for k, _ in c.most_common(2))
        self.assertEqual(levels(w32[4], v.duty, 256), [120, 136])
        self.assertEqual(levels(w34[4], v.duty, 256), [128, 136])     # the low side reads REST
        b32 = levels(w32[4], r.bitduty, 2048)
        b34 = levels(w34[4], r.bitduty, 2048)
        self.assertEqual(b32[0], b34[0])                              # 976 both
        self.assertLessEqual(abs(b32[1] - b34[1]), 1)                 # 1073 vs 1074

    def test_QUESTION_E(self):
        _, _, anc, wins = load(B34)
        res = v.question_E(wins[1:], [a["keys"] for a in press(anc)], "V")
        self.assertEqual(res["verdict"], "LEVELS DIFFER, NOT ORDERED")
        self.assertEqual(res["spans"], [255] * 4)
        self.assertEqual([len(a) for a in res["alphabets"]], [8, 10, 10, 11])

    def test_the_frozen_tools_are_unedited(self):
        for tool, grep in (("v11sweep.py", "Issue #69 -- the sweep pre-registered"),
                           ("v13sep.py", "Issue #75 -- U-GBP-038's separator pre-registered"),
                           ("v14repeat.py", "RUN 34 pre-registered")):
            base = subprocess.run(["git", "-C", ROOT, "log", "--format=%H", "-1", "--grep", grep],
                                  capture_output=True, text=True).stdout.strip()
            if not base:
                continue
            then = subprocess.run(["git", "-C", ROOT, "show", "%s:tools/%s" % (base, tool)],
                                  capture_output=True, text=True).stdout
            self.assertEqual(then, read(os.path.join(ROOT, "tools", tool)), tool)


class TheMeasurementBesideTheVerdict(unittest.TestCase):

    def test_the_four_amplitudes_in_one_run(self):
        _, _, _, w34 = load(B34)
        got = [r.deviation(w) * 256 for w in w34[1:]]
        for g, want in zip(got, (29.9883, 22.1094, 14.0977, 6.1211)):
            self.assertAlmostEqual(g, want, places=3)
        # V=11 against both predictions, which were written before the run
        self.assertAlmostEqual(abs(got[1] - v.deviation_linear(11, anchor=r.ANCHOR_V15) * 256), 0.06, delta=0.01)
        self.assertAlmostEqual(abs(got[1] - v.deviation_compressive(11, anchor=r.ANCHOR_V15) * 256), 4.83, delta=0.01)

    def test_the_repeat_and_the_fit(self):
        _, _, _, w31 = load(os.path.join(LOCAL, "GBP-AUDIO-002_stream-0016-run31-audio.bin"))
        _, _, _, w32 = load(B32)
        _, _, _, w34 = load(B34)
        self.assertAlmostEqual(r.repeat_delta(r.deviation(w32[3]), r.deviation(w34[3])), 0.0430, places=3)
        self.assertAlmostEqual(r.repeat_delta(r.deviation(w32[4]), r.deviation(w34[4])), 0.0664, places=3)
        self.assertAlmostEqual(r.repeat_delta(r.deviation(w31[3]), r.deviation(w34[1])), -0.0742, places=3)
        pts = [(15, r.deviation(w31[3]) * 256)] + [(V, r.deviation(w) * 256)
                                                  for V, w in zip(v.AMPLITUDES, w34[1:])]
        slope, icpt = r.fit(pts)
        self.assertAlmostEqual(slope, 1.9922, places=3)
        self.assertAlmostEqual(icpt, 0.1558, places=3)
        e = r.model_errors([(15, r.deviation(w31[3]))] + list(zip(v.AMPLITUDES,
                                                                   [r.deviation(w) for w in w34[1:]])))
        self.assertAlmostEqual(e["compressive"] / e["linear"], 92, delta=1)


class NothingIsPromotedPastItsOwnGate(unittest.TestCase):

    def test_GBP_HW_305_stays_CORROBORATED_with_its_repeat_named(self):
        ev = read(EV)
        h = [l for l in ev.split("\n") if l.startswith("### GBP-HW-305")][0]
        self.assertIn("NOT promoted", h)
        self.assertIn("still CORROBORATED", h)
        self.assertNotIn("FACT for the linearity", h)
        s = plain(part())
        self.assertIn("promoting past one's own gate because the numbers look good", s)

    def test_the_new_ids_are_308_to_311(self):
        ev = read(EV)
        self.assertEqual(max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 316)
        for i in range(308, 312):
            self.assertIn("### GBP-HW-%d" % i, ev)

    def test_the_unknowns(self):
        u = read(UNK)
        h39 = [l for l in u.split("\n") if l.startswith("## U-GBP-039")][0]
        self.assertIn("CLOSED 2026-09-23, Issue #78: PREMISE REFUTED", h39)
        self.assertIn("Closed as refuted, not as answered", plain(u))
        h38 = [l for l in u.split("\n") if l.startswith("## U-GBP-038")][0]
        self.assertIn("RESCOPED", h38)
        i = u.index("## U-GBP-012")
        self.assertNotIn("CLOSED", u[i:u.index("\n## U-GBP-013", i)])

    def test_the_hypothesis_is_weighed_and_NOT_concluded(self):
        s = plain(part())
        self.assertIn("So it is SUPPORTED and NOT ESTABLISHED, and two dead windows remain unexplained", s)
        self.assertIn("run sweep-0001 again", s)
        self.assertIn("It costs a flash, which is the Operator's to spend", s)

    def test_the_pre_registrations_keep_their_words_and_gain_only_a_pointer(self):
        t = read(HW)
        h13 = [l for l in t.split("\n") if l.startswith("## V13 — ")][0]
        h14 = [l for l in t.split("\n") if l.startswith("## V14 — ")][0]
        self.assertIn("NOT RUN, NOT AUTHORISED HERE", h13)
        self.assertIn("RUN 33 EXECUTED 2026-09-23 AND INGESTED (Issue #78, §V15)", h13)
        self.assertIn("NOT RUN, NOT AUTHORISED HERE", h14)
        self.assertIn("RUN 34 EXECUTED 2026-09-23 AND INGESTED (Issue #78, §V15)", h14)

    def test_nothing_beyond_run_34_is_claimed(self):
        self.assertNotIn("RUN 35", part())


if __name__ == "__main__":
    unittest.main()
