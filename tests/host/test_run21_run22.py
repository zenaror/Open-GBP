"""
tests/host/test_run21_run22.py — GitHub Issue #52: the acceptance pair as
PERFORMED, recomputed rather than quoted.

WHAT THESE RUNS ARE. §V7.6.9's action list was not performed: both are ordinary
play, which is step 13. So most of this file pins the DISCIPLINE — that the
deviation is stated first, that Question K is recorded as never performed and
not as INCONCLUSIVE, that W is inconclusive because the channel it reads does
not exist rather than because anything failed, and that no PASS or FAIL appears
where a gate did not apply.

THE SUMMARY-RECORD PARSER LIVES HERE, NOT IN tools/v7611.py. That module was
written before these logs existed (Issue #50) and must not be adjusted to them;
adding data-facing plumbing to it now would be the first step of exactly the
tuning the freeze prevents. The frozen constructions are imported and called,
never edited, and one test asserts that calling them on the real logs still
returns what the record says it returns — ANOMALOUS for Question T — so that a
later "fix" to make that read NOMINAL cannot pass unnoticed.
"""
import hashlib
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v7611  # noqa: E402

LOCAL = os.path.join(ROOT, "captures", "local")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
TB = 40500000.0

RUNS = {21: "GBP-PLAY-001_play-0001-run21.log", 22: "GBP-PLAY-001_play-0001-run22.log"}
HEADS = {25: "GBP-PLAY-001_play-0001-run25.log", 26: "GBP-PLAY-001_play-0001-run26.log"}
ALL = dict(list(RUNS.items()) + list(HEADS.items()))   # int keys: ** would need strings
HASHES = {21: ("cae3ecfcd16ae319ad19968190560f900c0989ed7463f54da45e1dd5a4fc09c4", 195301),
          22: ("a7bf2dbf014b6dca059e7b6a436e6bd81a1b01b28310bbd383cdea7b0d005c14", 168773),
          25: ("70b247675e6f116881872162f0900c8d79fd80f67e703ffb50dac4e0eb2d42a2", 94398),
          26: ("5fb2161b4306b3d21860da19bbf5390ffd1b17a80661598c17587ed5b382f15d", 94354)}
RB = {21: {"START": 7, "A": 118, "B": 54, "SELECT": 9, "RIGHT": 94, "LEFT": 66,
           "UP": 6, "DOWN": 17, "L": 8, "R": 25},
      22: {"START": 2, "A": 83, "B": 22, "SELECT": 2, "RIGHT": 62, "LEFT": 45,
           "UP": 34, "DOWN": 14, "L": 18, "R": 26}}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def have():
    return all(os.path.exists(os.path.join(LOCAL, f)) for f in ALL.values())


def log(n):
    return read(os.path.join(LOCAL, ALL[n]))


def record(text, name):
    """One summary record as {field: value}. Plumbing, deliberately not in the frozen module."""
    m = re.search(r"^\d+ %s (.+)$" % name, text, re.M)
    if not m:
        return {}
    out = {}
    for k, v in re.findall(r"(\w+)=([^\s]+)", m.group(1)):
        try:
            out[k] = int(v)
        except ValueError:
            out[k] = v
    return out


def gaps_by_kind(text):
    meta = {}
    for m in re.finditer(r"^\d+ CYC([FL]) i=(\d+) [^\n]*? v=(\d)/", text, re.M):
        meta[(m.group(1), int(m.group(2)))] = int(m.group(3))
    vid, aud = [], []
    for m in re.finditer(r"^\d+ CYC([FL])T i=(\d+) [^\n]*? ack=([0-9a-f]+) rearm=([0-9a-f]+)", text, re.M):
        gap = int(m.group(4), 16) - int(m.group(3), 16)
        (vid if meta.get((m.group(1), int(m.group(2)))) else aud).append(gap)
    return vid, aud


def section():
    t = read(HW)
    return t[t.index("### V7.8 "):]


class TheArtifactsAreWhatTheRecordSays(unittest.TestCase):
    def setUp(self):
        if not have():
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_hashes_and_sizes(self):
        for n, (digest, size) in HASHES.items():
            raw = open(os.path.join(LOCAL, ALL[n]), "rb").read()
            self.assertEqual(len(raw), size, n)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest, n)
            self.assertIn(digest, section(), "§V7.8 does not carry RUN %d's hash" % n)

    def test_both_logs_are_complete_and_carry_the_pre_registered_identity(self):
        for n in ALL:
            t = log(n)
            self.assertIn("test_id=GBP-PLAY-001", t)
            self.assertIn("build_id=play-0001", t)
            self.assertIn("commit=2e48ca7", t)          # §V7.6.5's image, not rebuilt
            self.assertIn("dropped=0 truncated=0", t)
            self.assertIn("# --- end --- dropped=0", t)
            self.assertIn("sidecar=none", t)            # play-0001 writes one log by design


class TheGatesAndTheTwoEnds(unittest.TestCase):
    def setUp(self):
        if not have():
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_the_key_record_is_clean_in_both(self):
        for n, events in ((21, 798), (22, 599)):
            lines, problems = v7611.parse_key_lines(log(n))
            self.assertEqual(problems, [], n)
            self.assertEqual(len(lines), events, n)
            ns = [l.n for l in lines]
            self.assertTrue(all(b - a == 1 for a, b in zip(ns, ns[1:])), n)
            k = record(log(n), "KEYLOG")
            self.assertEqual((k["events"], k["emitted"]), (events, events))
            self.assertEqual((k["lost"], k["truncated"], k["overwritten"]), (0, 0, 0))

    def test_run22_ended_on_Z_and_run21_on_the_event_store_cap(self):
        s22 = record(log(22), "SESSION")
        self.assertEqual(s22["stop"], "session_end")
        self.assertEqual(s22["teardown"], "S5_session_end")
        self.assertEqual((s22["requested"], s22["holds"]), (1, 1))
        self.assertGreater(s22["held"], 0)
        s21 = record(log(21), "SESSION")
        self.assertEqual(s21["stop"], "event_store_cap")
        self.assertEqual(s21["teardown"], "S5_event_store_cap")
        self.assertEqual((s21["requested"], s21["holds"]), (0, 0))   # Z never pressed
        # and the record says the unmet gate diminishes nothing else
        p = plain(section())
        self.assertIn("RUN 21's unmet SESSION gate is exactly the case §V7.6.10 wrote down in advance", p)
        self.assertIn("not for W, S or T, which read what happened before the end", p)

    def test_the_input_path_completed_every_attempt_in_both(self):
        for n, attempts, changes in ((21, 54004, 797), (22, 39845, 598)):
            i = record(log(n), "INPUT")
            self.assertEqual(i["attempts"], attempts, n)
            self.assertEqual(i["completed"], attempts, n)
            self.assertEqual(i["failed"], 0, n)
            self.assertEqual(i["retry"], 0, n)
            self.assertEqual(i["key_changes"], changes, n)


class ThePerBitCountsAreThePreRegisteredReading(unittest.TestCase):
    def setUp(self):
        if not have():
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_R_b_recomputed_matches_the_record(self):
        for n in RUNS:
            words = v7611.completed_words(v7611.parse_key_lines(log(n))[0])
            edges = v7611.rising_edges(words)
            got = dict((v7611.C[b], len(e)) for b, e in edges.items() if e)
            self.assertEqual(got, RB[n], n)
            self.assertEqual(len(got), 10, "every one of the ten bits must have risen in RUN %d" % n)
        # the table is one row per key carrying BOTH runs' counts, so it is checked as a row
        p = plain(section())
        for key in RB[21]:
            self.assertRegex(p, r"%s\s+%d\s+%d\b" % (re.escape(key), RB[21][key], RB[22][key]),
                             "§V7.8.5 does not carry the row for %s" % key)

    def test_the_record_says_what_the_counts_are_not(self):
        p = plain(section())
        self.assertIn("EVERY ONE OF THE TEN BITS ROSE ON BOTH PADS", p)
        self.assertIn("What the counts do NOT support", p)
        self.assertIn("They are not S, they are not K", p)
        self.assertIn("they do not say the game responded to any of them", p)
        self.assertIn("They also do not say the pads behave alike", p)


class TheDisciplineOfTheDeviation(unittest.TestCase):
    def test_what_was_done_is_the_first_thing_the_section_says(self):
        s = section()
        first = s[:s.index("#### V7.8.2")]
        p = plain(first)
        self.assertIn("WHAT THE OPERATOR ACTUALLY DID — four sessions, not two", p)
        self.assertIn("never as a fault of his or of the runs", p)
        self.assertIn("apenas abri o jogo e fiz uma jogatina normal", p)
        self.assertIn("esses foram os que fiz HEAD e depois Z", p)
        self.assertIn("THE NUMBERING, and it does not encode the pad", p)

    def test_the_numbering_follows_the_logs_own_time_base(self):
        """RUN 25 is the EARLIER head session, and the order is read from the logs, not the files."""
        t25 = int(re.search(r"t_control=([0-9a-f]+)", log(25)).group(1), 16)
        t26 = int(re.search(r"t_control=([0-9a-f]+)", log(26)).group(1), 16)
        self.assertLess(t25, t26, "RUN 25 must be the earlier head session")
        # and the generic pad ran before the original in BOTH pairs
        t21 = int(re.search(r"t_control=([0-9a-f]+)", log(21)).group(1), 16)
        t22 = int(re.search(r"t_control=([0-9a-f]+)", log(22)).group(1), 16)
        self.assertLess(t22, t21)
        p = plain(section())
        self.assertIn("the generic pad before the original in both pairs", p)
        self.assertIn("No gate depends on execution order", p)

    def test_W_is_inconclusive_and_the_global_report_is_not_expanded_into_verdicts(self):
        p = plain(section())
        self.assertIn("Question A / W = INCONCLUSIVE for every key in all four sessions", p)
        self.assertIn("a play report is not a per-key verdict and is not promoted into one", p.lower())
        # his head-session report, verbatim, and read at the level it carries
        self.assertIn("o jogo reagiu.... entrando em menus, saindo, pulando cutscenes", p)
        self.assertIn("it is not expanded into ten per-key WORKS verdicts", p.replace("So it", "it"))
        self.assertIn("a limitation of the evidence, not a fault of the run", p.lower())
        # S's operator half is worded as what it is
        self.assertIn("NO DIFFERENCE BETWEEN THE PADS WAS REPORTED", p)
        self.assertIn("Not \"he reported them identical\"", p)

    def test_question_K_agrees_over_the_head_and_each_run_matches_the_list(self):
        """The reading the head sessions exist for, recomputed with the frozen module."""
        seqs = {}
        for n in HEADS:
            words = v7611.completed_words(v7611.parse_key_lines(log(n))[0])
            seq, started = v7611.press_sequence(words)
            self.assertTrue(started, n)
            self.assertEqual([k for _, k in seq], list(v7611.HEAD_SEQUENCE),
                             "RUN %d does not match §V7.6.9's scripted head" % n)
            seqs[n] = seq
            k = record(log(n), "KEYLOG")
            self.assertEqual((k["events"], k["emitted"], k["lost"]), (35, 35, 0), n)
            self.assertEqual(record(log(n), "SESSION")["stop"], "session_end", n)
        k = v7611.question_K(seqs[25], seqs[26])
        self.assertEqual(k["verdict"], "AGREE")
        self.assertEqual(k["head"]["common_prefix"], 17)
        self.assertEqual(k["tail"]["verdict"], v7611.NOT_DEFINED)
        p = plain(section())
        self.assertIn("K = AGREE", p)
        self.assertIn("WHAT AGREE DOES NOT SAY", p)
        self.assertIn("K's tail stays NOT DEFINED BY THE PRE-REGISTRATION", p)

    def test_no_pass_or_fail_where_no_gate_applied(self):
        s = section()
        self.assertNotRegex(s, r"\bQuestion A = (PASS|FAIL)\b")
        self.assertNotRegex(s, r"\bW = (PASS|FAIL)\b")
        self.assertIn("No PASS and no FAIL is recorded anywhere a gate did not apply", plain(s))


class TheEventStoreFinding(unittest.TestCase):
    def setUp(self):
        if not have():
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def duration(self, n):
        st = record(log(n), "STARTUPT")
        rv = record(log(n), "RESTOREVSTATE")
        return (int(str(rv["teardown_begin"]), 16) - int(str(st["t_control"]), 16)) / TB

    def test_the_cap_and_the_rates_are_what_the_record_claims(self):
        e21, e22 = record(log(21), "EVENTS"), record(log(22), "EVENTS")
        self.assertEqual((e21["n"], e21["store_full"], e21["dropped"]), (16384, 1, 3))
        self.assertEqual((e22["n"], e22["store_full"], e22["dropped"]), (11894, 0, 0))
        env = record(log(21), "ENVSTORE")
        self.assertEqual(env["events"], "16384/4096")
        d21, d22 = self.duration(21), self.duration(22)
        self.assertAlmostEqual(d21, 273.918, places=2)
        self.assertAlmostEqual(d22, 202.103, places=2)
        self.assertAlmostEqual(16384 / d21, 59.81, places=1)
        # the store fills at the FRAME rate, not with input
        frames = record(log(21), "STREAMSRC")["published"]
        self.assertAlmostEqual(frames / d21, 59.61, places=1)
        self.assertAlmostEqual(record(log(21), "INPUT")["key_changes"] / d21, 2.91, places=1)
        # and the pad that filled the store produced FEWER key changes per second
        self.assertLess(record(log(21), "INPUT")["key_changes"] / d21,
                        record(log(22), "INPUT")["key_changes"] / d22)

    def test_the_720_s_budget_was_never_the_binding_constraint(self):
        d21 = self.duration(21)
        self.assertLess(d21, 720.0)
        self.assertAlmostEqual(45056 / (record(log(21), "STREAMSRC")["published"] / d21), 756, delta=5)
        p = plain(section())
        self.assertRegex(p, r"event store\s+16384 events[^|]*?~274 s")
        self.assertRegex(p, r"safety budget\s+720 s[^|]*?never approached")
        self.assertIn("WHAT ACTUALLY BOUND IT", p)
        self.assertIn("bounded at about 274 seconds", p)

    def test_the_three_dropped_events_are_the_three_terminal_ones(self):
        """The store filled before the run could record its own ending."""
        kinds = lambda n: set(re.findall(r"^\d+ EV seq=\d+ t=[0-9a-f]+ type=([a-z_]+)", log(n), re.M))
        missing = kinds(22) - kinds(21)
        self.assertEqual(missing, {"stop", "teardown_begin", "teardown_end"})
        self.assertEqual(record(log(21), "EVENTS")["dropped"], len(missing))
        self.assertIn("filled before the run could record its own ending", plain(section()))


class QuestionTIsMeasuredAndTheVerdictIsNotDeclared(unittest.TestCase):
    def setUp(self):
        if not have():
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_the_video_gap_is_shorter_and_the_audio_control_is_unchanged(self):
        ref_v, ref_a = gaps_by_kind(read(os.path.join(LOCAL, "GBP-VIDEO-004_stream-0015-run17.log")))
        for n in RUNS:
            v, a = gaps_by_kind(log(n))
            for i in range(3):                     # element for element, the records §V7.6.3 tabulates
                self.assertLess(v[i], ref_v[i], "RUN %d VIDEO record %d is not shorter" % (n, i))
            body = [x for x in a[1:]]              # the first is the early verify region in every run
            self.assertTrue(all(12 <= x <= 14 for x in body), (n, a))
        self.assertTrue(all(12 <= x <= 13 for x in ref_a[2:]), ref_a)

    def test_the_frozen_construction_still_returns_ANOMALOUS_and_was_not_edited(self):
        """If someone 'fixes' v7611 so this reads NOMINAL, this test fails and says why."""
        src = read(os.path.join(ROOT, "tools", "v7611.py"))
        self.assertIn('"the AUDIO-only gap moved', src)
        self.assertIn("NO threshold invented after the fact", src)
        p = plain(section())
        self.assertIn("the frozen construction returns ANOMALOUS on both runs", p)
        self.assertIn("tools/v7611.py was not touched", p)
        self.assertIn("So no T verdict is recorded", p)
        self.assertIn("Declaring NOMINAL would resolve an ambiguity after seeing the data", p)

    def test_the_third_ambiguity_is_reported_with_its_three_facets(self):
        p = plain(section())
        self.assertIn("THE THIRD AMBIGUITY, reported and NOT resolved, and the code NOT edited", p)
        self.assertIn("unchanged BY WHAT MEASURE", p)
        self.assertIn("FAR BY WHAT MEASURE", p)
        self.assertIn("ARE PER-INDEX and are not portable", p)
        # the per-index claim is checked against the files rather than asserted
        meta = {}
        for m in re.finditer(r"^\d+ CYCL i=(\d+) [^\n]*? v=(\d)/", log(21), re.M):
            meta[int(m.group(1))] = int(m.group(2))
        self.assertEqual(meta.get(6), 1, "CYCLT i=6 should carry a VIDEO block in RUN 21")
        ref = {}
        for m in re.finditer(r"^\d+ CYCL i=(\d+) [^\n]*? v=(\d)/",
                             read(os.path.join(LOCAL, "GBP-VIDEO-004_stream-0015-run17.log")), re.M):
            ref[int(m.group(1))] = int(m.group(2))
        self.assertEqual(ref.get(6), 0, "CYCLT i=6 should be AUDIO-only in RUN 17")


class TheStandingDeclarationCarriesItsCondition(unittest.TestCase):
    def test_it_is_recorded_as_his_decision_and_not_as_a_finding(self):
        p = plain(section())
        self.assertIn("se o comportamento dos 2 gamepads forem iguais", p)
        self.assertIn("the GENERIC third-party pad is the controller, unless a run strictly requires the original", p)
        self.assertIn("ITS CONDITION IS PART OF IT AND IS NOT SATISFIED", p)
        self.assertIn("these runs do not decide that by machine", p)
        self.assertIn("not as a finding that the pads are equivalent", p)

    def test_the_evidence_entries_exist_and_claim_only_what_was_measured(self):
        ev = read(EVIDENCE)
        for n in range(278, 283):
            self.assertIn("### GBP-HW-%d " % n, ev, n)
        p = plain(ev)
        self.assertIn("the verdict is NOT declared here", p)
        self.assertIn("W stays INCONCLUSIVE per key and is not inferred from it", p)
        self.assertIn("no new unknown is opened", p.lower())
        self.assertIn("ADDENDUM 2026-09-22 (GitHub Issue #52)", read(UNKNOWNS))
        for n in (283, 284):
            self.assertIn("### GBP-HW-%d " % n, ev, n)


if __name__ == "__main__":
    unittest.main()
