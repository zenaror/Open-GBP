"""
tests/host/test_gbc_runs.py — GitHub Issue #55: the four GB/GBC runs of
`stream-0015` — RUN 24, 27, 28 and 29 — and everything claimed from them.

THREE CARTRIDGES, TWO MEDIA FAMILIES, AND A WINDOW THAT MOVES. The transition
of CONTROL bit 0x01 reproduces across Pokémon Crystal (twice), an Everdrive GB
X7 and a DMG Samurai Spirits; the Everdrive's arrival window is DISJOINT from
the other three's, which is what excludes elapsed time and the A1 write as
sufficient explanations. All of that is recomputed here rather than quoted,
because a finding that rests on four runs agreeing has to be checked against
four runs.

AND THE SAMPLES TESTED A METHODOLOGICAL DECISION. GBP-HW-275 rested on
unanimity across the stable replicas plus persistence, never on the value of
byte 0. Byte 0 takes four different values across the four runs and in two of
them does not move at all — so a reading based on it would have made the runs
contradict each other about the finding itself. The test demonstrates that.

The status argument is pinned too: the MEANING moved to FACT because the entry's
own bar was met AND the argument was written out, and the scope that travels
with it — one console, one GBP, this read sequence, and THE BIT IS NOT IN THE
ORIGINAL BYTE — is asserted with it.
"""
import hashlib
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL = os.path.join(ROOT, "captures", "local")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
REGISTERS = os.path.join(ROOT, "docs", "protocol", "REGISTERS.md")
TB = 40500000.0

GBC = {24: "5b8a98b5" and None, 27: "5b8a98b5c778675cc6047b03b95cd0ffd9655bdec64fcac6d31b7d6256b249c3",
       28: "10b64d342425be702e2e7170a87023ff0607d0ca8119e2502d26a8e50efe3bff",
       29: "a1be040ebc20de28f165bac4861ec1d13781d28083a247b9491767acb7351d24"}
RUNS = [24, 27, 28, 29]
EARLY = [24, 27, 29]          # the three ordinary cartridges
LATE = 28                     # the Everdrive
POINTS = ["P0", "A1-0", "A1-50US", "A1-500US", "A2-0", "A2-50US", "A2-500US", "A2-5MS",
          "A2-50MS", "EVENT", "PREUNMASK"]


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def path(n, kind=None):
    base = "GBP-VIDEO-004_stream-0015-run%d" % n
    return os.path.join(LOCAL, base + (".log" if kind is None else "-%s.bin" % kind))


def have():
    return all(os.path.exists(path(n)) for n in RUNS)


def reads(n):
    """read point -> (vote, byte 0, the set of the 31 stable replicas)."""
    out = {}
    for m in re.finditer(r"RAW ([A-Z0-9-]+) idx=4 [^\n]*sem_vote=([0-9a-f]+)[^\n]*data=([0-9a-f]{64})",
                         read(path(n))):
        tag, vote, data = m.groups()
        if tag in POINTS and tag not in out:
            out[tag] = (vote, data[:2], set(data[i:i + 2] for i in range(2, 64, 2)))
    return out


def bracket(n):
    """(last read showing 8e, first showing 8f), as (tag, since_control ticks)."""
    r = reads(n)
    snaps = dict((m.group(1), int(m.group(2))) for m in
                 re.finditer(r"SNAP tag=([A-Z0-9-]+) ticks=\d+ since_control=(\d+)", read(path(n))))
    last, first = None, None
    for tag in POINTS:
        if tag not in r:
            continue
        if r[tag][0] == "8e":
            last = tag
        elif r[tag][0] == "8f" and first is None:
            first = tag
    return (last, snaps[last]), (first, snaps[first])


def section():
    t = read(HW)
    return t[t.index("### V7.10 "):]


class TheArchiveIsWhatTheRecordSays(unittest.TestCase):
    def setUp(self):
        if not have():
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_every_hash_in_the_section_is_the_hash_on_disk(self):
        for n in (27, 28, 29):
            digest = hashlib.sha256(open(path(n), "rb").read()).hexdigest()
            self.assertEqual(digest, GBC[n], n)
            self.assertIn(digest, section(), "§V7.10 does not carry RUN %d's hash" % n)

    def test_three_sidecars_are_byte_identical_across_all_four_runs(self):
        for kind in ("idxcap", "full", "vi"):
            blobs = set()
            for n in RUNS:
                if not os.path.exists(path(n, kind)):
                    self.skipTest("no local archive on this host (captures/local is ignored)")
                blobs.add(open(path(n, kind), "rb").read())
            self.assertEqual(len(blobs), 1, "%s differs across the GB/GBC runs" % kind)
        self.assertIn("a session that captured nothing, four times", plain(section()))

    def test_every_log_is_complete_and_the_same_length(self):
        for n in RUNS:
            t = read(path(n))
            self.assertIn("dropped=0 truncated=0", t, n)
            self.assertIn("lines=171", t, n)


class TheTransitionReproducesAcrossThreeCartridges(unittest.TestCase):
    def setUp(self):
        if not have():
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_the_original_byte_is_clear_in_every_one(self):
        for n in RUNS:
            self.assertIn("CONTROL semantic orig=92 exp=8e", read(path(n)), n)
            self.assertEqual(reads(n)["P0"][0], "8e", n)

    def test_the_bit_sets_and_persists_in_every_one(self):
        for n in RUNS:
            r = reads(n)
            self.assertEqual(r["PREUNMASK"][0], "8f", n)
            self.assertEqual(r["PREUNMASK"][2], {"8f"}, "%s: the stable replicas disagree" % n)

    def test_the_guard_and_the_failed_restore_in_every_one(self):
        """§V7.10.6: a property of the image and the path, not of a cartridge."""
        for n in RUNS:
            t = read(path(n))
            self.assertIn("PREUNMASK ok=0 reason=control_changed", t, n)
            self.assertIn("readback_vote=93", t, n)
            self.assertIn("control_restore_ok=0", t, n)
            self.assertIn("status=anomaly_control_changed", t, n)
        p = plain(section())
        self.assertIn("a property of the image and the path, not of a cartridge", p)
        self.assertIn("That is a Phase 7 precondition", p)


class TheWindowIsCartridgeDependent(unittest.TestCase):
    def setUp(self):
        if not have():
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_the_three_ordinary_cartridges_flip_early_and_the_everdrive_late(self):
        for n in EARLY:
            (last, _), (first, _) = bracket(n)
            self.assertEqual((last, first), ("A1-50US", "A1-500US"), n)
        (last, _), (first, _) = bracket(LATE)
        self.assertEqual((last, first), ("A2-50US", "A2-500US"), LATE)

    def test_the_two_windows_are_disjoint(self):
        """The separation is the finding; a marginal overlap would not be one."""
        early_hi = max(bracket(n)[1][1] for n in EARLY)
        late_lo = bracket(LATE)[0][1]
        self.assertLess(early_hi, late_lo, "the windows overlap; the finding does not hold")
        self.assertAlmostEqual(early_hi * 1e6 / TB, 635.9, places=1)
        self.assertAlmostEqual(late_lo * 1e6 / TB, 698.0, places=1)
        p = plain(section())
        self.assertIn("The two brackets do not overlap", p)
        self.assertIn("This is a separation, not a marginal difference", p)

    def test_the_sd_load_explanation_is_excluded_by_timescale(self):
        """The first hypothesis any reader proposes, retired with checkable arithmetic."""
        sched = {}
        for n in RUNS:
            for m in re.finditer(r"SNAP tag=([A-Z0-9-]+) ticks=\d+ since_control=\d+ since_a1=(\d+)",
                                 read(path(n))):
                sched.setdefault(m.group(1), []).append(int(m.group(2)))
        # the probe's schedule is deterministic, which is what makes the arithmetic checkable
        for tag in ("A1-50US", "A1-500US", "A2-50US", "A2-500US"):
            self.assertLessEqual(max(sched[tag]) - min(sched[tag]), 7, tag)
        us = lambda tag: min(sched[tag]) * 1e6 / TB
        self.assertAlmostEqual(us("A1-500US"), 500.0, places=0)
        self.assertAlmostEqual(us("A2-500US"), 1012.0, places=0)
        # BOTH transitions are sub-millisecond; an SD OS load is tens to hundreds of ms
        self.assertLess(us("A2-500US"), 1100.0)
        p = plain(section())
        self.assertIn("EXCLUDED BY TIMESCALE", p)
        self.assertIn("two to three orders of magnitude", p)
        self.assertIn("BOTH ARE SUB-MILLISECOND", p)
        self.assertIn("it is written down as excluded rather than never raised", p)
        self.assertIn("NO MECHANISM IS NAMED HERE", p)

    def test_the_everdrive_stimulus_is_declared_not_assumed(self):
        p = plain(section())
        self.assertIn("O everdrive GB x7 sempre acessa o menu dele", p)
        self.assertIn("RUN 28's stimulus is the Everdrive's own menu and operating system", p)
        self.assertIn("a cartridge that always runs its own firmware first", p)
        # and the Phase 7 planning constraint is where the next list will meet it
        g = plain(read(os.path.join(ROOT, "docs", "research", "GBC_PATH.md")))
        self.assertIn("A PLANNING CONSTRAINT, declared by the Operator 2026-09-22", g)
        self.assertIn("tests \"GBP + Everdrive OS\", not \"GBP + game\"", g)

    def test_the_record_excludes_two_candidates_and_closes_nothing(self):
        p = plain(section())
        self.assertIn("ELAPSED TIME ALONE", p)
        self.assertIn("THE A1 WRITE ALONE", p)
        self.assertIn("EXCLUDED as a sufficient explanation", p)
        self.assertIn("U-GBP-036 DOES NOT CLOSE", p)
        self.assertIn("a contrast, not a mechanism", p)
        self.assertIn("which makes it a different stimulus in a way that is declared but not characterised", p)


class TheNegativeResultAboutDmgAndCgb(unittest.TestCase):
    def setUp(self):
        if not have():
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_the_dmg_cartridge_behaves_exactly_like_the_cgb_one(self):
        self.assertEqual([reads(29)[p][0] for p in POINTS if p in reads(29)],
                         [reads(24)[p][0] for p in POINTS if p in reads(24)])
        self.assertEqual(bracket(29)[0][0], bracket(24)[0][0])
        p = plain(section())
        self.assertIn("A NEGATIVE RESULT — bit 0x01 does not distinguish DMG from CGB", p)
        self.assertIn("separates the GB/GBC family from Game Boy Advance, and nothing finer", p)


class ByteZeroWouldHaveMadeThemContradict(unittest.TestCase):
    def setUp(self):
        if not have():
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_byte_zero_takes_four_values_and_is_constant_in_two_runs(self):
        b = dict((n, [reads(n)[p][1] for p in ("P0", "A1-500US", "PREUNMASK")]) for n in RUNS)
        self.assertEqual(b[24], ["ee", "ef", "ef"])
        self.assertEqual(set(b[27]), {"9f"})          # constant across the transition
        self.assertEqual(set(b[29]), {"9f"})          # constant
        self.assertEqual(b[28], ["de", "de", "df"])
        self.assertEqual(len({tuple(v) for v in b.values()}), 3)
        # the stable replicas agree with the vote in 43 of 44 reads; the one exception is
        # pinned exactly, because "they always agree" would be a claim these files refute
        deviations = []
        for n in RUNS:
            for tag, (vote, _, stable) in sorted(reads(n).items()):
                if stable != {vote}:
                    deviations.append((n, tag, sorted(stable - {vote}), vote))
        self.assertEqual(deviations, [(29, "A2-50US", ["9f"], "8f")], deviations)
        # and the deviating value is the one byte 0 holds throughout that run
        self.assertEqual(reads(29)["A2-50US"][1], "9f")
        p = plain(section())
        self.assertIn("the 31 stable replicas agree with the vote in 43 of 44 reads", p)
        self.assertIn("RUN 29 at A2-50US, where replica 8 reads 9f against a vote of 8f", p)
        self.assertIn("the vote is unaffected and no verdict rests on it", p)

    def test_the_record_states_the_consequence_rather_than_a_preference(self):
        p = plain(section())
        self.assertIn("BYTE 0 WOULD HAVE MADE THE RUNS CONTRADICT EACH OTHER", p)
        self.assertIn("the runs would have contradicted each other about the finding itself", p)
        self.assertIn("Third and fourth confirmation that the value is noise and the unanimity is the signal", p)


class TheStatusWasArguedNotAwarded(unittest.TestCase):
    def test_the_meaning_moved_to_FACT_with_its_scope(self):
        ev = plain(read(EVIDENCE))
        self.assertIn("THE STATUS, ARGUED RATHER THAN AWARDED", ev)
        self.assertIn("A bar being met is a reason to write the argument, not a substitute for it", ev)
        self.assertIn("WHAT BECOMES FACT", ev)
        self.assertIn("THE SCOPE, WHICH", ev)
        self.assertIn("THE BIT IS NOT IN THE ORIGINAL BYTE", ev)
        self.assertIn("WHY THIS IS NOT", ev)
        self.assertIn("bit 0x02's causal step stayed CORROBORATED because a rival explanation", ev)

    def test_the_register_row_carries_the_fact_and_the_scope(self):
        row = [l for l in read(REGISTERS).splitlines() if l.startswith("| 0x01 |")][0]
        self.assertIn("F (hw, four runs, three cartridges", row)
        self.assertIn("THE BIT IS NOT IN THE ORIGINAL BYTE", row)
        self.assertIn("WHEN it arrives is CARTRIDGE-DEPENDENT", row)
        self.assertIn("It does NOT distinguish DMG from CGB", row)
        self.assertNotIn("C, not F, for the MEANING", row)
        self.assertIn("U-GBP-036", row)

    def test_the_unknown_is_narrowed_and_open(self):
        u = read(UNKNOWNS)
        body = u[u.index("### U-GBP-036 —"):]
        self.assertIn("OPEN (opened 2026-09-22", u)
        p = plain(body)
        self.assertIn("A repeat answers \"does it reproduce\", never \"what causes it\"", p)
        self.assertNotIn("CLOSED", p)


if __name__ == "__main__":
    unittest.main()
