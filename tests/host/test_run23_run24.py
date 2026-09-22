"""
tests/host/test_run23_run24.py — GitHub Issue #47: the two UNREGISTERED runs of
`12-stream` the Operator performed on his own initiative, and everything about
them that a machine can check.

WHAT MAKES THESE RUNS UNUSUAL is not the hardware, it is the discipline
question: they had no pre-registration, so nothing here may take the shape of a
verdict. This file therefore pins TWO kinds of thing and keeps them apart:

  * what is RECOMPUTABLE from the two archives — the original bytes, the
    read-back trajectory, the bounded window in which bit 0x01 appears, the
    guard that refused the session, the accounting of a run that completed and
    one that did not;
  * what the RECORDS must say about them — that they were not pre-registered,
    that no PASS or FAIL is claimed, that run numbers 23 and 24 precede 21 and
    22 in wall-clock time, and that the hashes in §V7.7 are the hashes on disk.

The five-run contrast is the reason any of this carries weight, so it is
recomputed rather than quoted: one binary, one fixed sequence, the same read
points, four runs with a GBA cartridge, one with none, one with a Game Boy
Color cartridge, and exactly one of them moves.
"""
import hashlib
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LOCAL = os.path.join(ROOT, "captures", "local")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
REGISTERS = os.path.join(ROOT, "docs", "protocol", "REGISTERS.md")

RUN23 = "GBP-VIDEO-004_stream-0015-run23"
RUN24 = "GBP-VIDEO-004_stream-0015-run24"
GBA_RUNS = ["GBP-VIDEO-004_stream-0015-run18", "GBP-VIDEO-004_stream-0015-run17",
            "GBP-VIDEO-004_stream-0014-run15", "GBP-VIDEO-003_color-0002"]
READ_POINTS = ["P0", "A1-0", "A1-50US", "A1-500US", "A2-0", "A2-50MS", "EVENT", "PREUNMASK"]
TB_HZ = 40500000


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def log(name):
    return read(os.path.join(LOCAL, name + ".log"))


def have(*names):
    return all(os.path.exists(os.path.join(LOCAL, n + ".log")) for n in names)


def section():
    t = read(HW)
    i = t.index("### V7.7 ")
    return t[i:]


def votes(text):
    """Read point -> the majority-vote CONTROL byte the runtime recorded there."""
    out = {}
    for m in re.finditer(r"RAW ([A-Z0-9-]+) idx=4 [^\n]*sem_vote=([0-9a-f]+)", text):
        out.setdefault(m.group(1), m.group(2))
    return out


class TheArchivesAreWhatTheRecordSays(unittest.TestCase):
    def setUp(self):
        if not have(RUN23, RUN24):
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_every_hash_in_the_section_is_the_hash_on_disk(self):
        """The section's table and the files cannot drift apart without this failing."""
        rows = re.findall(r"^\s{2}(log|idxcap|disp|full|vi)\s+([\d ]+) B\s+([0-9a-f]{64})\s*$", section(), re.M)
        self.assertEqual(len(rows), 10, "§V7.7 should carry five files for each of the two runs")
        it = iter(rows)
        for run in (RUN23, RUN24):
            for _ in range(5):
                kind, size, digest = next(it)
                path = os.path.join(LOCAL, run + (".log" if kind == "log" else "-%s.bin" % kind))
                self.assertTrue(os.path.exists(path), path)
                with open(path, "rb") as f:
                    raw = f.read()
                self.assertEqual(len(raw), int(size.replace(" ", "")), path)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), digest, path)

    def test_both_logs_are_complete_and_carry_the_same_identity(self):
        for name in (RUN23, RUN24):
            t = log(name)
            self.assertIn("dropped=0 truncated=0", t, name)
            self.assertIn("# --- end --- dropped=0", t, name)
            self.assertIn("test_id=GBP-VIDEO-004", t, name)
            self.assertIn("build_id=stream-0015", t, name)
            self.assertIn("commit=da06500", t, name)
        # RUN 24 is SHORT, not truncated: the difference matters and is checked
        self.assertIn("lines=171", log(RUN24))
        self.assertIn("lines=689", log(RUN23))


class TheTrajectoryIsRecomputed(unittest.TestCase):
    def setUp(self):
        if not have(RUN23, RUN24, *GBA_RUNS):
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_the_original_bytes(self):
        self.assertIn("CONTROL semantic orig=90 exp=8c", log(RUN23))
        self.assertIn("CONTROL semantic orig=92 exp=8e", log(RUN24))
        # the GB/GBC cartridge gives the byte a GBA cartridge gives -- the negative of GBP-HW-274
        for name in GBA_RUNS:
            self.assertIn("CONTROL semantic orig=92 exp=8e", log(name), name)

    def test_only_the_gbc_run_moves(self):
        v23, v24 = votes(log(RUN23)), votes(log(RUN24))
        for k in READ_POINTS:
            self.assertEqual(v23[k], "8c", "RUN 23 moved at %s" % k)
        for name in GBA_RUNS:
            v = votes(log(name))
            for k in READ_POINTS:
                self.assertEqual(v[k], "8e", "%s moved at %s" % (name, k))
        # RUN 24: 0x8e up to A1-50US, 0x8f from A1-500US onward -- bit 0x01 and nothing else
        for k in ("P0", "A1-0", "A1-50US"):
            self.assertEqual(v24[k], "8e", k)
        for k in ("A1-500US", "A2-0", "A2-50MS", "EVENT", "PREUNMASK"):
            self.assertEqual(v24[k], "8f", k)
        self.assertEqual(int("8e", 16) ^ int("8f", 16), 0x01)

    def test_the_window_the_documents_state_is_the_window_the_ticks_give(self):
        t = log(RUN24)
        snaps = dict((m.group(1), int(m.group(2))) for m in
                     re.finditer(r"SNAP tag=([A-Z0-9-]+) ticks=\d+ since_control=(\d+)", t))
        lo, hi = snaps["A1-50US"], snaps["A1-500US"]
        self.assertEqual((lo, hi), (7518, 25742))
        lo_us, hi_us = lo * 1e6 / TB_HZ, hi * 1e6 / TB_HZ
        self.assertAlmostEqual(lo_us, 185.6, places=1)
        self.assertAlmostEqual(hi_us, 635.6, places=1)
        for doc in (section(), EVIDENCE, REGISTERS, UNKNOWNS):
            d = plain(doc if doc.startswith("### V7.7") else read(doc))
            self.assertIn("186–636 µs", d.replace("186-636 us", "186–636 µs"))

    def test_replica_zero_is_noisy_and_the_change_is_in_all_31_of_the_others(self):
        """The vote exists because replica 0 lies; the result must not rest on it.

        FOUR deviations among the OTHER 31 exist in this family, and two of them
        are the reason this result must be stated as unanimity-and-persistence
        rather than as a value: an isolated replica reads 0x8f twice in RUN 17,
        which had a GBA cartridge. RUN 24's change is in all 32 replicas and
        holds to the end of the run. The exact list is pinned so it cannot grow
        without somebody noticing, and §V7.7 carries it.
        """
        rep0_deviations, stable_deviations = 0, []
        seen = set()
        for name in (RUN23, RUN24) + tuple(GBA_RUNS):
            for m in re.finditer(r"RAW ([A-Z0-9-]+) idx=4 [^\n]*sem_vote=([0-9a-f]+)[^\n]*data=([0-9a-f]{64})", log(name)):
                tag, vote, data = m.group(1), m.group(2), m.group(3)
                if tag not in READ_POINTS or (name, tag) in seen:
                    continue
                seen.add((name, tag))
                reps = [data[i:i + 2] for i in range(0, 64, 2)]
                if reps[0] != vote:
                    rep0_deviations += 1
                for i, r in enumerate(reps[1:], start=1):
                    if r != vote:
                        stable_deviations.append((name.split("_")[1], tag, i, r, vote))
        self.assertGreater(rep0_deviations, 0, "replica 0 was expected to deviate somewhere in this family")
        self.assertEqual(stable_deviations, [
            ("stream-0015-run23", "A2-50MS", 14, "8a", "8c"),
            ("stream-0015-run17", "A2-50MS", 26, "8f", "8e"),
            ("stream-0015-run17", "PREUNMASK", 20, "8f", "8e"),
            ("stream-0014-run15", "P0", 18, "9e", "8e")], stable_deviations)
        s = plain(section())
        self.assertIn("bit 0x01 SET, in a run with a GBA cartridge", s)
        self.assertIn("the value 0x8f by itself is NOT unique to the GB/GBC run", s)
        self.assertIn("The result therefore rests on unanimity and persistence, never on the value alone", s)
        self.assertIn("No mechanism is claimed", s)
        # and RUN 24's flip is in every one of the 31, not in the noisy replica alone
        for m in re.finditer(r"RAW (A1-500US|A2-0|A2-50MS|EVENT|PREUNMASK) idx=4 [^\n]*data=([0-9a-f]{64})", log(RUN24)):
            reps = [m.group(2)[i:i + 2] for i in range(0, 64, 2)]
            self.assertEqual(set(reps[1:]), {"8f"}, m.group(1))


class TheRunThatCompletedAndTheRunThatDidNot(unittest.TestCase):
    def setUp(self):
        if not have(RUN23, RUN24):
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_run23_reached_its_witness_target_with_no_game_pak(self):
        t = log(RUN23)
        self.assertIn("status=ok_structured_change_observed", t)
        self.assertIn("stop=witness_target_reached", t)
        self.assertIn("restore=ok", t)
        self.assertIn("teardown=S5_witness_target", t)
        self.assertIn("errors=0 transport_ok=1", t)
        self.assertIn("STREAMWIT records=2048/2048 target=2048", t)
        self.assertIn("target_reached=1", t)
        self.assertIn("CONTROL restore semantic=90 rc=ok readback_rc=ok readback_vote=90 readback_b1f=90 ok=1", t)

    def test_run24_was_refused_by_the_guard_and_captured_nothing(self):
        t = log(RUN24)
        self.assertIn("PREUNMASK ok=0 reason=control_changed", t)
        self.assertIn("control=8f", t)
        self.assertIn("status=anomaly_control_changed", t)
        self.assertIn("reason=control_changed_PREUNMASK", t)
        self.assertIn("teardown=S2_before_unmask", t)
        self.assertIn("unmasks=0", t)
        self.assertIn("errors=0 transport_ok=1", t)          # nothing about the transport is implicated
        # nothing was captured, in every accounting the runtime keeps
        self.assertIn("t_capture_start=0", t)
        self.assertIn("STREAMWIT records=0/2048", t)
        self.assertIn("VISTORE handed=0", t)
        self.assertIn("DISPSRC handoffs=0", t)
        self.assertIn("have_first=0", t)
        # and the restore failed for the same one cause
        self.assertIn("readback_vote=93", t)
        self.assertIn("control_restore_ok=0", t)
        self.assertIn("power_cycle_required=1", t)

    def test_the_sidecars_hold_only_their_headers(self):
        for kind, limit in (("idxcap", 512), ("disp", 512), ("full", 512), ("vi", 512)):
            p = os.path.join(LOCAL, RUN24 + "-%s.bin" % kind)
            self.assertLess(os.path.getsize(p), limit, p)
            q = os.path.join(LOCAL, RUN23 + "-%s.bin" % kind)
            self.assertGreater(os.path.getsize(q), 100000, q)


class TheRecordSaysWhatTheseRunsAreNot(unittest.TestCase):
    def test_the_section_states_the_unregistered_status_and_claims_no_verdict(self):
        s = plain(section())
        for tok in ("They were not pre-registered",
                    "Therefore this section records NO PASS and NO FAIL",
                    "A verdict is a judgement against a gate written beforehand; no gate existed",
                    "WHAT IT IS NOT WORTH it is not a pre-registration OF THESE RUNS",
                    "the question was public first", "the discriminator was public",
                    "nobody can have chosen the analysis after seeing the data"):
            self.assertIn(tok, s, tok)

    def test_the_numbering_says_23_and_24_precede_21_and_22(self):
        s = plain(section())
        self.assertIn("RUN 23 / RUN 24 precede 21 and 22", s.replace("23 and 24 precede 21 and 22",
                                                                     "RUN 23 / RUN 24 precede 21 and 22"))
        self.assertIn("A run number is an allocation, not a clock", s)
        self.assertIn("the dates carry the chronology", s.lower())
        self.assertIn("RUN 21 / RUN 22 RESERVED and pre-registered for play-0001", s)

    def test_the_evidence_ids_exist_and_carry_their_statuses(self):
        ev = read(EVIDENCE)
        for n in range(273, 278):
            self.assertIn("### GBP-HW-%d " % n, ev, n)
        e = plain(ev)
        self.assertIn("RUN 23: a LATE build with NO Game Pak reads CONTROL 0x90", e)
        self.assertIn("the empty diagonal cell of GBP-HW-272 filled", e)
        self.assertIn("a NEGATIVE that closes a stated expectation", e)
        self.assertIn("FACT for the transition and the contrast; the MEANING stays an inference", e)
        self.assertIn("CORROBORATED, not FACT -- one run, one cartridge", e.replace("—", "--"))
        # the amendment on 272, and the status it moves
        self.assertIn("AMENDMENT 2026-09-22 (GitHub Issue #47)", e)
        self.assertIn("DISCONFIRMED BY MEASUREMENT", e)
        self.assertIn("CLAIM 2 accordingly moves from HYPOTHESIS to CORROBORATED", e)

    def test_the_unknown_is_open_and_017_did_not_close(self):
        u = read(UNKNOWNS)
        self.assertIn("### U-GBP-036 —", u)
        self.assertIn("OPEN (opened 2026-09-22, Issue #47", u)
        body = u[u.index("### U-GBP-036 —"):]
        for tok in ("WHAT triggers it", "WHY NOT AT POWER-ON", "IS THE WINDOW REAL",
                    "NOT scheduled and NOT authorised here"):
            self.assertIn(tok, plain(body), tok)
        u017 = u[u.index("## U-GBP-017 (P2) —"):]
        u017 = u017[:u017.index("\n## ", 1)]
        self.assertIn("the breaker RAN, unbidden", u017)
        self.assertNotIn("CLOSED", u017)
        self.assertNotIn("RESOLVED", u017)

    def test_the_operators_words_are_kept_as_his(self):
        s = section()
        self.assertIn("rodei o 12-stream sem cartucho", s)
        self.assertIn("nem chamou o boot logo do GameBoy", s)
        self.assertIn("OPERATOR OBSERVATION", s)
        # and the title of the cartridge is his reading, not an instrument's
        self.assertIn("the cartridge's title is his reading of the label, unverified by any instrument here",
                      plain(s))


if __name__ == "__main__":
    unittest.main()
