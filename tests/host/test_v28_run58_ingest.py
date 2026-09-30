"""tests/host/test_v28_run58_ingest.py -- GitHub Issue #142 (RUN 58): the ingested readings, re-derived from the archived log by the tools.

The numbers HARDWARE_TESTS.md V28.33 and GBP-HW-376 quote are recomputed here from captures/local (ignored by Git, so the test skips, with the registered reason, on a host
without the archive). The O1 scoring is redone from the confirmed rungs alone, apart from the tool, and the Operator's verbatim words are checked to be in the record.
"""
import hashlib
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v28null  # noqa: E402
import v28verdict  # noqa: E402

RUN58 = os.path.join(ROOT, "captures", "local", "GBP-AUDIO-V28_v28-perceptual-0001-run58.log")
SHA = "098fad302214b9e784aabd8f1c8bd7f2fde5e826fb2115f93161e93ead26addb"
DOC = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EVID = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")


def section(path, head):
    with open(path, encoding="utf-8") as f:
        d = f.read()
    i = d.index(head)
    j = d.find("\n### ", i + 1)
    return d[i:j if j > 0 else len(d)]


class TheArchivedLogReadsAsRecorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(RUN58):
            raise unittest.SkipTest("no local archive on this host (captures/local is ignored)")
        with open(RUN58, "rb") as f:
            raw = f.read()
        assert hashlib.sha256(raw).hexdigest() == SHA, "captures/local's RUN 58 archive is not the recorded one (a defect in the archive, never a skip)"
        cls.text = raw.decode("utf-8", "replace")
        cls.a = v28null.analyse(cls.text, "M1")

    def test_the_settings_as_recorded(self):
        rows = self.a["settings"]
        self.assertEqual(self.a["n"], 8)
        self.assertEqual([r["start"] for r in rows], [2, 2, 5, 6, 0, 5, 0, 0])
        self.assertEqual([r["rung"] for r in rows], [5, 2, 0, 3, 0, 7, 2, 1])
        self.assertEqual([round(r["L"], 1) for r in rows], [183.5, 261.7, 324.4, 230.4, 324.4, 121.0, 261.7, 293.1])
        self.assertEqual([r["top_refused"] for r in rows], [3, 2, 0, 0, 14, 0, 0, 0])
        self.assertEqual([r["floor_refused"] for r in rows], [0] * 8)
        self.assertEqual([r["cls"] for r in rows], ["interior"] * 4 + ["top"] + ["interior"] * 3)
        self.assertEqual((self.a["k_floor"], self.a["k_top"], self.a["interior"]), (0, 1, 7))
        self.assertEqual(self.a["suspect"], 0)
        self.assertEqual(self.a["inconsistent"], 0)

    def test_the_mechanistic_gate_and_the_verdict(self):
        self.assertEqual(self.a["gates"], {"fill": (8, 8), "ready": (8, 8), "underruns": (8, 8), "overflow": (8, 8)})
        self.assertEqual(self.a["missing_mech"], 0)
        self.assertAlmostEqual(self.a["null_L"], 261.7, places=1)
        self.assertIn("NULL ESTIMATED from the 7 uncensored setting(s) of 8", self.a["verdict"])
        self.assertIn("biased DOWN", self.a["verdict"])

    def test_o1_by_the_registered_rule_redone_from_the_rungs(self):
        rungs = [r["rung"] for r in self.a["settings"]]
        uncens = sorted(r["rung"] for r in self.a["settings"] if r["cls"] == "interior")
        self.assertEqual(uncens, [0, 1, 2, 2, 3, 5, 7])
        med = uncens[len(uncens) // 2]
        self.assertEqual(med, 2)
        within_u = sum(1 for x in uncens if abs(x - med) <= 2)
        within_all = sum(1 for x in rungs if abs(x - med) <= 2)
        self.assertEqual((within_u, len(uncens), within_all, len(rungs)), (5, 7, 6, 8))
        self.assertGreaterEqual(within_u * 3, len(uncens) * 2, "O1's 2/3 bar")
        self.assertLess((within_u - 1) * 3, len(uncens) * 2, "the margin is ONE setting: one fewer in the window and O1 reads INCOHERENT")
        self.assertEqual(len(set(rungs)), 6, "six distinct confirmed rungs")
        self.assertEqual((min(rungs), max(rungs)), (0, 7), "the whole ladder")

    def test_the_verdict_tool_and_the_phase_records(self):
        out = v28verdict.render(v28verdict.analyse(self.text))
        self.assertIn("ADMISSIBILITY: PASS", out)
        self.assertIn("p0 navigate    32.2 s  blocks_in 131492  loss 0.301 %", out)
        self.assertIn("underruns 1 (1.9/min)", out)
        self.assertIn("240.0 s  blocks_in 980005  loss 0.309 %", out)
        self.assertIn("underruns 0 (0.0/min)", out)
        for tok in ("V28CFG plan=perceptual_no_phase1", "V28TAPS taps=1160993 taps_failed=0 wrong_len=0 blocks_in=1111498", "ENVSTORE frames=25500/16384 events=33575/4096 corr_cap=16575 fault=- ok=1"):
            self.assertIn(tok, self.text, tok)
        self.assertIn("V28C underruns=1 overflow=0", self.text, "the run's only underrun is the one in navigate")

    def test_the_per_setting_records_the_prose_quotes(self):
        import re
        nm = [(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))) for m in
              re.finditer(r"V28_NULLM n=(\d+) ring=(\d+) ready=(\d+) underruns=(\d+) overflow=(\d+)", self.text)]
        self.assertEqual([(r, y) for (_n, r, y, _u, _o) in nm],
                         [(3254, 2), (6096, 4), (10240, 4), (4016, 4), (10080, 4), (2701, 0), (5772, 3), (8208, 3)])
        self.assertTrue(all(u == 0 and o == 0 for (_n, _r, _y, u, o) in nm))
        # confirm times, seconds after the nulling phase began (V28PHC p=1 t0)
        t0 = int(re.search(r"V28PHC p=1 ended=1 t0=([0-9a-f]+)", self.text).group(1), 16)
        ts = [int(m.group(1), 16) for m in re.finditer(r"V28_NULL n=\d+ .* t=([0-9a-f]+)", self.text)]
        got = [round((t - t0) / v28null.TB_HZ, 1) for t in ts]
        self.assertEqual(got, [57.5, 99.5, 129.4, 139.6, 170.9, 187.2, 206.9, 230.2])
        # the stick events: 36 LEFT, 9 RIGHT, 8 UP acted (kind 4), the DOWN that began the nulling and one LEFT in navigate
        ev = re.findall(r"SYNCCS dir=(\w) kind=(\d+) acted=(\d+)", self.text)
        from collections import Counter
        self.assertEqual(sorted(Counter(ev).items()),
                         [(("D", "0", "3"), 1), (("L", "0", "0"), 1), (("L", "4", "1"), 36), (("R", "4", "1"), 9), (("U", "4", "1"), 8)])
        self.assertEqual(len(ev), 55)

    def test_the_underrun_is_the_navigate_phase_s(self):
        import re
        p0 = re.search(r"V28PHC p=0 .*underruns=(\d+)", self.text)
        p1 = re.search(r"V28PHC p=1 .*underruns=(\d+)", self.text)
        self.assertEqual((int(p0.group(1)), int(p1.group(1))), (1, 0))
        out = v28verdict.render(v28verdict.analyse(self.text))
        line = [l for l in out.splitlines() if l.strip().startswith("p0 navigate")][0]
        self.assertIn("underruns 1 (1.9/min)", line)

    def test_the_chance_of_passing_o1_with_no_discrimination_by_exact_enumeration(self):
        """The registered rule as the tool scores it, under uniform independent rungs: the figure the record quotes (70.6 %), not a fixed-window binomial."""
        import itertools

        def o1(r):
            s_ = sorted(r)
            med = s_[len(s_) // 2]
            return sum(1 for x in s_ if abs(x - med) <= 2) * 3 >= len(s_) * 2
        ok = sum(1 for r in itertools.product(range(8), repeat=7) if o1(r))
        self.assertEqual((ok, 8 ** 7), (1481502, 2097152))
        self.assertEqual(round(100.0 * ok / 8 ** 7, 1), 70.6)


class TheRecordCarriesTheOperatorsWordsAndTheLimits(unittest.TestCase):
    def test_his_words_are_verbatim_in_the_section(self):
        s = section(DOC, "### V28.33 RUN 58 EXECUTED AND INGESTED")
        for w in ("fiquei em duvida em quase todos, todos pareciam bem parecidos.",
                  "tinha momentos que todos pareciam iguais. devia mudar micro segundos",
                  "não, pois todos eram muito identicos",
                  "em alguns momentos so ouvi o que parecia picotes, mas depois estabilizou"):
            self.assertIn(w, s, w)

    def test_the_section_states_what_it_does_not_establish(self):
        s = " ".join(section(DOC, "### V28.33 RUN 58 EXECUTED AND INGESTED").split())
        for tok in ("The audio-versus-video offset in milliseconds", "That a null exists in this range",
                    "The instrument's discrimination was not tested in this run",
                    "One tension is recorded, not reconciled", "NOT linked",
                    "No runtime constant was changed by this ingestion",
                    "the Executor states the options and their limits, does not choose", "1 481 502 of 2 097 152 draws (70.6 %)", "T512 A1 and L = 183.7 ms", "was NOT asked to rank the rungs"):
            self.assertIn(tok, s, tok)

    def test_the_evidence_entry_does_not_promote(self):
        e = " ".join(section(EVID, "### GBP-HW-376 ").split())
        for tok in ("promotes nothing into `docs/hardware/` or `docs/protocol/`", "UNKNOWN (whether a null exists in this range",
                    "post hoc, not registered", "OPERATOR OBSERVATION", "70.6 %"):
            self.assertIn(tok, e, tok)


if __name__ == "__main__":
    unittest.main()
