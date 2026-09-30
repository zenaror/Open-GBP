"""tests/host/test_run_order_deviation.py -- GitHub Issue #149: the RUN 59 -> RUN 58 order is recorded as a PROCEDURAL DEVIATION, the four items apart, and the checks it reports are recomputed.

The amendment (HARDWARE_TESTS.md V29.14) and its cross-reference (V28.34) are checked against the Operator's own list; the log checks (no artefact collision, identity, no carried-over
CONTROL state, the one PI record that differs and why it is not carried state) are recomputed from captures/local (ignored by Git: that part skips, with the registered reason, on a
host without the archive).
"""
import datetime
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DOC = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
LOCAL = os.path.join(ROOT, "captures", "local")
L58 = os.path.join(LOCAL, "GBP-AUDIO-V28_v28-perceptual-0001-run58.log")
L59 = os.path.join(LOCAL, "GBP-VIDEO-004_gbmode-0001-run59.log")
L57 = os.path.join(LOCAL, "GBP-AUDIO-V28_v28-validation-0001-run57.log")
HZ = 40500000


def section(head):
    with open(DOC, encoding="utf-8") as f:
        d = f.read()
    i = d.index(head)
    j = d.find("\n### ", i + 1)
    return d[i:j if j > 0 else len(d)]


def plain(s):
    return " ".join(s.replace("`", "").replace("**", "").split())


class TheAmendmentKeepsTheOperatorsFourItemsApart(unittest.TestCase):
    def test_the_heading_and_the_four_items_in_order(self):
        s = section("### V29.14 PROCEDURAL DEVIATION")
        self.assertIn("PROCEDURAL DEVIATION", s.splitlines()[0])
        pos = [s.index(h) for h in ("**1. The observable fact.**", "**2. The mitigation.**", "**3. The consequence actually demonstrated",
                                    "**4. What is NOT concluded.**")]
        self.assertEqual(pos, sorted(pos))

    def test_the_operators_words_are_verbatim(self):
        s = section("### V29.14 PROCEDURAL DEVIATION")
        for w in ("Registrar na ingestão do RUN 59 o desvio procedimental confirmado pelo Operator: apesar da ordem recomendada pelo clearance ser RUN 58 → RUN 59, o RUN 59 foi executado primeiro (mtimes: 06:06 para RUN 59 e 06:15 para RUN 58).",
                  "Não tratar isso como se a ordem tivesse sido cumprida. Registrar explicitamente como procedural deviation.",
                  "sim, rodei a 59 antes por ser mais rapida... mas fiz o power cycle"):
            self.assertIn(w, s, w)

    def test_item_1_is_the_fact_and_item_4_converts_nothing(self):
        s = plain(section("### V29.14 PROCEDURAL DEVIATION"))
        i1, i2, i3, i4 = (s.index(h) for h in ("1. The observable fact.", "2. The mitigation.", "3. The consequence actually demonstrated", "4. What is NOT concluded."))
        fact, mit, cons, notc = s[i1:i2], s[i2:i3], s[i3:i4], s[i4:]
        self.assertIn("RUN 59 (gbmode-0001, Game Boy Color cartridge) ran before RUN 58", fact)
        self.assertIn("06:06", fact)
        self.assertIn("06:15", fact)
        self.assertIn("NOT an independent check", fact)
        self.assertNotIn("power cycle was declared", fact, "the mitigation is item 2, not item 1")
        self.assertIn("power cycle was declared before and after RUN 59", mit)
        self.assertIn("distinct", mit)
        self.assertIn("Found: none.", cons)
        self.assertIn("What the checks can and cannot see", cons)
        self.assertIn('not written as "the order is irrelevant"', notc)
        self.assertIn('not written as "the run is invalidated"', notc)
        self.assertIn("Neither run's verdict, token or score changes", notc)
        self.assertIn("no repetition is proposed", notc)
        for banned in ("the order is irrelevant.", "is invalidated.", "were invalidated"):
            self.assertNotIn(banned, cons + fact + mit)

    def test_the_time_statement_claims_no_utc_and_no_admissibility_decision(self):
        s = plain(section("### V29.14 PROCEDURAL DEVIATION"))
        self.assertNotIn("UTC", s)
        self.assertIn("three hours earlier on the same console (the cause is not established", s)
        self.assertIn("This amendment does not re-decide admissibility", s.replace("this amendment", "This amendment"))
        self.assertNotIn("each admissible by its own registered gates", s)
        self.assertIn("recorded as such in §V28.33, not as his words", s)
        self.assertIn("3 of the 10 runs of the family", s)
        self.assertIn("opening paragraph (verbatim, 2026-09-30", s)

    def test_the_cross_reference_reclassifies_nothing(self):
        s = plain(section("### V28.34 Cross-reference"))
        self.assertIn("NOT to be read as compliant", s)
        self.assertIn("§V29.14", s)
        self.assertIn("RUN 58 is not reclassified here", s)
        self.assertNotIn("invalid", s.replace('"run invalidated"', ""))

    def test_the_committed_sections_are_appended_not_rewritten(self):
        with open(DOC, encoding="utf-8") as f:
            d = f.read()
        self.assertLess(d.index("### V29.12 RUN 59 EXECUTED AND INGESTED"), d.index("### V29.14 PROCEDURAL DEVIATION"))
        self.assertLess(d.index("### V28.33 RUN 58 EXECUTED AND INGESTED"), d.index("### V28.34 Cross-reference"))
        self.assertEqual(d.count("### V29.14 PROCEDURAL DEVIATION"), 1)


class TheLogChecksAreRecomputed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (os.path.isfile(L58) and os.path.isfile(L59) and os.path.isfile(L57)):
            raise unittest.SkipTest("no local archive on this host (captures/local is ignored)")
        texts = []
        for p in (L58, L59, L57):
            with open(p, encoding="utf-8", errors="replace") as f:
                texts.append(f.read())
        cls.t58, cls.t59, cls.t57 = texts

    def test_identity_and_distinct_names(self):
        self.assertIn("build_id=v28-perceptual-0001", self.t58)
        self.assertIn("commit=22d0328", self.t58)
        self.assertIn("app=gbp-audio-v28-perceptual_no_phase1", self.t58)
        self.assertIn("build_id=gbmode-0001", self.t59)
        self.assertIn("commit=4d6fe06", self.t59)
        self.assertIn("app=gbp-video-stream-probe", self.t59)
        self.assertNotEqual(os.path.basename(L58).split("_")[0], os.path.basename(L59).split("_")[0])
        self.assertTrue(all(w in self.t58 for w in ("lines=1348 dropped=0 truncated=0", "# --- end --- dropped=0")))
        self.assertIn("lines=690 dropped=0 truncated=0", self.t59)

    def test_no_control_state_carried_into_run_58(self):
        def votes(t):
            from collections import Counter
            return Counter(m.group(1) for m in re.finditer(r"sem_vote=([0-9a-f]{2})", t))
        self.assertIn("CONTROL semantic orig=92 exp=8e", self.t58)
        self.assertEqual(dict(votes(self.t58)), {"92": 2, "8e": 23, "00": 1})
        self.assertEqual(dict(votes(self.t58)), dict(votes(self.t57)), "the same distribution as the previous run of the family")
        self.assertFalse(any(int(v, 16) & 0x01 for v in votes(self.t58) if v != "00"), "a CONTROL read of RUN 58 carries bit 0x01")
        self.assertIn("PREUNMASK ok=1 reason=- intsr13=1,1 intmr13=0,0 control=8e irq=0500/0500", self.t58)
        self.assertIn("RAW TDCTL idx=4", self.t59)
        self.assertRegex(self.t59, r"RAW TDCTL idx=4 .*sem_vote=93")

    def test_the_time_bases_agree_with_the_order_without_being_independent(self):
        t59 = int(re.search(r"teardown_begin=([0-9a-f]+)", self.t59).group(1), 16)
        t58 = int(re.search(r"V28PHC p=0 ended=1 t0=([0-9a-f]+)", self.t58).group(1), 16)
        base = datetime.datetime(2000, 1, 1)
        d59 = base + datetime.timedelta(seconds=t59 / float(HZ))
        d58 = base + datetime.timedelta(seconds=t58 / float(HZ))
        self.assertEqual((d59.strftime("%H:%M:%S"), d58.strftime("%H:%M:%S")), ("09:06:17", "09:10:52"))
        t58_end = int(re.search(r"teardown_begin=([0-9a-f]+)", self.t58).group(1), 16) if "teardown_begin=" in self.t58 else None
        if t58_end is not None:
            self.assertEqual((base + datetime.timedelta(seconds=t58_end / float(HZ))).strftime("%H:%M:%S"), "09:15:24")
        self.assertLess(d59, d58)

    def test_no_dsp_status_carried_from_run_59(self):
        d58 = re.findall(r"dspcr=([0-9a-f]{4})", self.t58)
        d59 = re.findall(r"dspcr=([0-9a-f]{4})", self.t59)
        d57 = re.findall(r"dspcr=([0-9a-f]{4})", self.t57)
        self.assertEqual((set(d58), len(d58)), ({"0814"}, 86))
        self.assertEqual(set(d57), {"0814"})
        self.assertEqual((set(d59), len(d59)), ({"0804"}, 86))
        for t in (self.t58, self.t57, self.t59):
            self.assertIn("ARINFO orig value=0043", t)
        self.assertIn("gecko=0", self.t58.split("\n", 6)[3] + self.t58.split("\n", 6)[4])

    def test_the_one_pi_record_that_differs_is_a_family_wide_timing_variation(self):
        def rec(t):
            return re.search(r"PI tag=UNMASKPOST-1 .*intsr=([0-9a-f]+) ", t).group(1), int(re.search(r"UNMASK n=1 .*dt_post=(\d+)", t).group(1))
        self.assertEqual(rec(self.t58), ("00012000", 15))
        self.assertEqual(rec(self.t57), ("00010000", 225))
        family = {"50": ("00010000", 22), "51": ("00010000", 230), "52": ("00010000", 232), "53": ("00010000", 241), "55": ("00012000", 23), "56": ("00012000", 21)}
        for n, want in family.items():
            p = os.path.join(LOCAL, "GBP-AUDIO-V28_v28-validation-0001-run%s.log" % n)
            if not os.path.isfile(p):
                self.skipTest("no local archive on this host (captures/local is ignored)")
            with open(p, encoding="utf-8", errors="replace") as f:
                self.assertEqual(rec(f.read()), want, n)
        p54 = os.path.join(LOCAL, "GBP-AUDIO-V28_v28-diagloss-0001-run54.log")
        if not os.path.isfile(p54):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        with open(p54, encoding="utf-8", errors="replace") as f:
            self.assertEqual(rec(f.read()), ("00010000", 20))
        self.assertEqual(rec(self.t59), ("00010000", 16))
        self.assertEqual(rec(self.t57), ("00010000", 225))
        allrec = list(family.values()) + [("00010000", 20), ("00012000", 15), ("00010000", 225), ("00010000", 16)]
        self.assertEqual(sum(1 for r in allrec if r[0] == "00012000"), 3, "bit 13 set in 3 of the 10 runs that have the record")
        self.assertEqual(len(allrec), 10)


if __name__ == "__main__":
    unittest.main()
