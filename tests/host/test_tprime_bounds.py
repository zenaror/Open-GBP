"""
tests/host/test_tprime_bounds.py — GitHub Issue #54: T′'s two chosen thresholds
derived from the archive's own spread, and the one positional form that cannot
bite annotated rather than corrected.

WHY DERIVING IS NOT POST-HOC, and the test exists partly to keep that reasoning
attached to the numbers: T′ governs a FUTURE run. Using a quantity's historical
variation to bound a future measurement of it is how a control limit is set,
and the freeze holds as long as the number is fixed before the run it judges.

THE FIGURES ARE RECOMPUTED HERE, not quoted, so §V7.9.7 cannot drift from the
archive it was derived from. The derivation also turned up something worth more
than either number — `skipped_cause_pending` is a property of the BUILD, not of
the run — and that is pinned too, because without it a cross-build comparison
of that quantity reads as an anomaly.
"""
import os
import re
import glob
import statistics
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
METHOD = os.path.join(ROOT, "docs", "RESEARCH_METHOD.md")
CAPREADME = os.path.join(ROOT, "captures", "README.md")
LOCAL = os.path.join(ROOT, "captures", "local")
TB = 40500000.0


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def part(name):
    t = read(HW)
    i = t.index(name)
    nxt = [j for j in (t.find("\n#### V7.", i + 1), t.find("\n### V7.", i + 1)) if j != -1]
    return t[i:min(nxt)] if nxt else t[i:]


# Issue #54 derived the two bounds from the archive AS IT STOOD on 2026-09-22.
# A derivation is a statement about the data it used, so the population is pinned
# to those seven builds rather than to "whatever is on disk now": stream-0016
# joined the archive with RUN 30 (Issue #62) and is NOT part of this derivation.
# Re-deriving on a larger archive is a checkpoint with its own record, not
# something a test should do silently when a file appears.
DERIVATION_BUILDS = ("play-0001", "stream-0015", "stream-0014", "stream-0013",
                     "stream-0011", "stream-0010", "stream-0009")


def families(builds=DERIVATION_BUILDS):
    """build -> [(run, delivery/s, skipped %)] for every archived run of the
    derivation's builds that reached the service loop."""
    out = {}
    for f in sorted(glob.glob(os.path.join(LOCAL, "*.log"))):
        t = read(f)
        c = re.search(r"^\d+ COUNTERS ([^\n]+)$", t, re.M)
        p = re.search(r"^\d+ STREAMPUMP ([^\n]+)$", t, re.M)
        st = re.search(r"t_capture_start=([0-9a-f]+)", t)
        td = re.search(r"teardown_begin=([0-9a-f]+)", t)
        b = re.search(r"^build_id=(\S+)$", t, re.M)
        if not (c and p and st and td and b):
            continue
        cd = dict(re.findall(r"(\w+)=([\w/\.]+)", c.group(1)))
        pd = dict(re.findall(r"(\w+)=(\d+)", p.group(1)))
        dl = int(cd["deliveries"])
        win = (int(td.group(1), 16) - int(st.group(1), 16)) / TB
        if dl == 0 or win <= 1:
            continue
        if builds is not None and b.group(1) not in builds:
            continue
        out.setdefault(b.group(1), []).append(
            (os.path.basename(f), dl / win, 100.0 * int(pd["skipped_cause_pending"]) / int(pd["calls"])))
    return out


class TheBoundsAreDerivedFromTheArchive(unittest.TestCase):
    def setUp(self):
        self.fam = families()
        if len(self.fam) < 3:
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_the_population_is_the_one_the_record_states(self):
        n = sum(len(v) for v in self.fam.values())
        self.assertEqual((n, len(self.fam)), (17, 7))
        p = plain(part("#### V7.9.7"))
        self.assertIn("17 runs across 7 builds", p)
        # and the record says WHICH seven, so a later arrival cannot silently join them
        self.assertIn("stream-0016 joined the archive with RUN 30", p)

    def test_a_later_run_joins_the_archive_and_not_the_derivation(self):
        """RUN 30 (stream-0016) is in captures/local and must NOT be counted."""
        everything = families(builds=None)
        later = set(everything) - set(DERIVATION_BUILDS)
        if not later:
            self.skipTest("no post-derivation build is archived in this checkout")
        self.assertNotIn("stream-0016", self.fam)
        self.assertIn("stream-0016", everything)

    def test_the_delivery_bound_is_replaced_and_its_multiple_is_right(self):
        r = [x[1] for v in self.fam.values() for x in v]
        spread_pct = 100.0 * (max(r) - min(r)) / statistics.median(r)
        self.assertAlmostEqual(spread_pct, 0.110, places=2)
        p = plain(part("#### V7.9.7"))
        self.assertIn("observed between-build spread of the delivery rate is 0.110 %", p)
        self.assertIn("1 % - is 9.1 times that", p.replace("—", "-"))
        self.assertIn("The bound becomes 0.5 %, which is 4.5 × the observed full spread", p)
        self.assertIn('"not lower" = delivery rate >= 0.995 x the reference\'s', p)
        # the multiples are the ones the archive gives
        self.assertAlmostEqual(1.0 / spread_pct, 9.1, places=1)
        self.assertAlmostEqual(0.5 / spread_pct, 4.5, places=1)

    def test_the_skipped_bound_is_kept_and_its_multiple_is_right(self):
        s = [x[2] for v in self.fam.values() for x in v]
        spread = max(s) - min(s)
        self.assertAlmostEqual(spread, 2.512, places=2)
        p = plain(part("#### V7.9.7"))
        self.assertIn("2.512 percentage points, so 5 pp is 1.99 × it", p)
        self.assertIn("it needs no change", p)
        self.assertAlmostEqual(5.0 / spread, 1.99, places=2)

    def test_the_build_dependence_is_recorded_with_its_consequence(self):
        """The finding that matters more than either number."""
        within = max(max(x[2] for x in v) - min(x[2] for x in v) for v in self.fam.values() if len(v) > 1)
        self.assertLess(within, 0.05, "within a build the quantity should be flat")
        p = plain(part("#### V7.9.7"))
        self.assertIn("skipped_cause_pending is a property of the BUILD, not of the run", p)
        self.assertIn("it repeats to 0.027 percentage points", p)
        self.assertIn("a difference of up to about 2.5 pp against a reference of another build is ORDINARY "
                      "and is not a finding", p)
        self.assertIn("those two figures are two builds", p)
        self.assertAlmostEqual(within, 0.027, places=2)

    def test_the_form_of_every_rule_is_unchanged(self):
        p = plain(part("#### V7.9.7"))
        self.assertIn('"not longer" still carries no magnitude at all', p)
        self.assertIn("T′ may not be applied to RUN 17, 21, 22, 25 or 26 as a verdict", p)
        self.assertIn("No hardware is scheduled", p)
        self.assertIn("§V7.9.3 keeps its words and its form", p)
        # §V7.9's heading points at the amendment, per Issue #49's convention
        head = read(HW)[read(HW).index("### V7.9 QUESTION T′"):].splitlines()[0]
        self.assertIn("AMENDED 2026-09-22 (Issue #54, §V7.9.7)", head)

    def test_deriving_is_justified_where_the_numbers_are(self):
        p = plain(part("#### V7.9.7"))
        self.assertIn("Deriving a bound from a quantity's historical variation is not post-hoc, because T′ "
                      "governs a FUTURE run", p)


class TheColourNoteIsAnnotationNotCorrection(unittest.TestCase):
    def test_the_frozen_sentence_is_untouched_and_the_note_explains_it(self):
        c = read(CAPREADME)
        self.assertIn("Cross-run: its three certified frames are byte-identical to `color-0001`'s in the "
                      "consumed projection, 38400/38400 in all three pairs.", c)
        p = plain(c)
        self.assertIn("A note on one cross-run comparison — appended 2026-09-22 (GitHub Issue #54)", p)
        self.assertIn("Its words are unchanged and the claim is correct", p)
        self.assertIn("This is an annotation, not a correction", p)
        self.assertIn("The pairing in that sentence is ORDINAL", p)
        self.assertIn("it cannot bite", p)
        self.assertIn("no other pairing could give a different answer", p)
        self.assertIn("A later auditor would have to do the same work with no hint that it ends well", p)
        self.assertIn("this one is its harmless twin", p)

    def test_the_lesson_says_lapse_not_blind_spot(self):
        m = plain(read(METHOD))
        self.assertIn("IT WAS A LAPSE IN ONE TABLE, NOT A BLIND SPOT IN THE METHOD", m)
        self.assertIn("resolves each POC's declarations rather than comparing argument spellings", m)
        self.assertIn("it is an existing practice being written down, after one table failed to follow it", m)
        self.assertIn("A rule recorded as novel invites the reader to treat earlier work as suspect", m)


if __name__ == "__main__":
    unittest.main()
