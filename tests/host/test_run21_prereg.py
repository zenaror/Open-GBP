"""
tests/host/test_run21_prereg.py — GitHub Issue #41: RUN 21 / RUN 22 are
PRE-REGISTERED in HARDWARE_TESTS §V7.6 (GBP-INPUT-004, `play-0001`'s first
runs) and NOT RUN.

The point of a pre-registration test is that the part cannot be tuned to data
that does not exist yet, so everything here is checked against something
INDEPENDENT of the future runs:

  - Question T's baseline table is RECOMPUTED from RUN 17's archived log, line
    by line: every figure §V7.6.3 quotes must be in that file or derivable from
    it by the arithmetic the section states;
  - the image's identity is the one Issue #39 recorded and, when the tree is
    built, what build-info says;
  - the two questions, their separate gates and the ONE interaction between
    them are pinned as written, including that a FAULT on T is a result;
  - the instrument is the settled one, with its form on the three-value axis,
    its attribution caveat beside the verdicts and its cartridge-hardware
    check recorded as made rather than presumed;
  - the action list obeys the separated notation (no digits glued to a button
    name, the count carrying × and whitespace, dual names for SELECT) and the
    frozen lists of §V7.1 / §V7.3 / §V7.5 keep their old text;
  - the two raw names are reserved exactly once, are absent from the tree, and
    no name above run22 exists anywhere;
  - nothing frozen moved: §V7.1–§V7.5 byte-identical, EVIDENCE untouched, no
    GBP-HW id minted, nothing under src/, poc/, tools/ or the Makefile.
"""
import os
import re
import subprocess
import unittest

import guards

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
ROADMAP = os.path.join(ROOT, "docs", "ROADMAP.md")
DEVLOG = os.path.join(ROOT, "docs", "research", "DEVLOG.md")
INPUT_PATH = os.path.join(ROOT, "docs", "research", "INPUT_PATH.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
RUN17_LOG = os.path.join(ROOT, "captures", "local", "GBP-VIDEO-004_stream-0015-run17.log")
BUILD_INFO = os.path.join(ROOT, "build", "poc", "gbp-play-session", "build-info.txt")
BASE = "fe79f22"                 # origin/main before Issue #41
DOL_SHA = "d0ee3c29d04254d1b86d4f006291008876b5e886e07280d0421b7c1161c499de"
DOL_SIZE = "487 968"
COMMIT = "2e48ca7"
NAMES = ["captures/local/GBP-PLAY-001_play-0001-run21.log",
         "captures/local/GBP-PLAY-001_play-0001-run22.log"]


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "")


def v76():
    t = read(HW)
    return t[t.index("### V7.6 RUN 21 / RUN 22"):]


def part(n):
    """One #### V7.6.n subsection."""
    t = v76()
    i = t.index("#### V7.6.%d " % n)
    j = t.find("#### V7.6.%d " % (n + 1), i)
    return t[i:] if j < 0 else t[i:j]


def run17():
    if not os.path.isfile(RUN17_LOG):
        return None
    return read(RUN17_LOG)


class ThePartExistsAndSaysWhatItIs(unittest.TestCase):
    def test_the_heading_and_the_chapter(self):
        h = v76().splitlines()[0]
        for tok in ("### V7.6 RUN 21 / RUN 22", "GBP-INPUT-004", "play-0001", "SEPARATE GATES",
                    "**PRE-REGISTERED 2026-09-21 (GitHub Issue #41)", "AMENDED BEFORE HARDWARE the same day",
                    "NOT RUN / NOT AUTHORISED HERE**"):
            self.assertIn(tok, h, tok)
        chapter = [l for l in read(HW).splitlines() if l.startswith("## V7 ")][0]
        self.assertIn("RUN 21 / RUN 22 PRE-REGISTERED (Issue #41, §V7.6)", chapter)
        self.assertIn("NOT RUN / NOT AUTHORISED HERE", chapter.split("Issue #41")[1])
        # the chapter heading GREW: the old one is a prefix of the new one
        old = subprocess.run(["git", "-C", ROOT, "show", "%s:docs/research/HARDWARE_TESTS.md" % BASE],
                             capture_output=True, text=True)
        if old.returncode == 0:
            old_chapter = [l for l in old.stdout.splitlines() if l.startswith("## V7 ")][0]
            self.assertTrue(chapter.startswith(old_chapter), "the chapter heading grows, it does not change")
        for n in range(1, 15):
            self.assertIn("#### V7.6.%d " % n, v76(), n)

    def test_the_two_questions_and_the_one_interaction(self):
        one = plain(part(1))
        for tok in ("§V6.13's rule applied", "neither verdict consults the other's evidence",
                    "QUESTION A Phase 5's acceptance", "QUESTION T the timing of the shortened service pass",
                    "a run whose service FAILED had no session to judge, so it is INCONCLUSIVE for A as well",
                    "T never reads the Operator's report; A never reads the cycle records",
                    "A timing anomaly is an EXPECTED POSSIBLE OUTCOME of this pair, not a failed run"):
            self.assertIn(tok, one, tok)
        ten = plain(part(10))
        for tok in ("T = FAULT and the run had no session", "Question A is INCONCLUSIVE for that run",
                    "T = FAULT but the session completed", "Question A is read on its own records, unchanged",
                    "NEVER A's verdict", "T = ANOMALOUS (accounting clean) -> Question A is untouched",
                    "Question T is untouched: T reads the machine records only"):
            self.assertIn(tok, ten, tok)


class QuestionTsBaselineIsRecomputedFromRun17(unittest.TestCase):
    """Every figure §V7.6.3 quotes is in RUN 17's archived log, or follows from it."""

    def setUp(self):
        self.log = run17()
        if self.log is None:
            self.skipTest("RUN 17's log is a local capture; not present in this checkout")
        self.three = part(3)

    def field(self, tag, key):
        m = re.search(r"^\d+ %s .*?\b%s=(\S+)" % (re.escape(tag), re.escape(key)), self.log, re.M)
        self.assertIsNotNone(m, "%s %s" % (tag, key))
        return m.group(1)

    def test_the_witness_step_and_its_share(self):
        self.assertEqual(self.field("STREAMWITT", "copy_ticks_min"), "5")
        self.assertEqual(self.field("STREAMWITT", "copy_ticks_mean"), "70")
        self.assertEqual(self.field("STREAMWITT", "copy_ticks_max"), "1547")
        self.assertEqual(self.field("STREAMWITT", "n"), "96109")
        self.assertIn("STREAMWITT 5 / 70 / 1 547 ticks, n = 96 109", self.three)
        self.assertIn("0.12 / 1.73 / 38.20 us", self.three)
        for ticks, us in ((5, 0.12), (70, 1.73), (1547, 38.20)):
            self.assertAlmostEqual(ticks / 40.5, us, places=2)
        self.assertIn("70 x 96 109 = 0.166 s of 40.248 s = 0.41 %", self.three)
        self.assertAlmostEqual(70 * 96109 / 40.5e6, 0.166, places=3)
        self.assertAlmostEqual(100 * (70 * 96109 / 40.5e6) / 40.248, 0.41, places=2)

    def test_the_cycle_gaps(self):
        gaps = []
        for tag in ("CYCFT", "CYCLT"):
            for line in re.findall(r"^\d+ %s i=(\d+) .*$" % tag, self.log, re.M):
                pass
        def gap(tag, i):
            m = re.search(r"^\d+ %s i=%d .*?ack=([0-9a-f]+) rearm=([0-9a-f]+) next=([0-9a-f]+)" % (tag, i), self.log, re.M)
            self.assertIsNotNone(m, "%s i=%d" % (tag, i))
            a, r, n = (int(x, 16) for x in m.groups())
            return r - a, n - r
        first = [gap("CYCFT", i) for i in (0, 1, 2)]
        self.assertEqual([g[0] for g in first], [1197, 895, 886])
        self.assertEqual([g[1] for g in first], [1171, 1067, 1067])
        last = [gap("CYCLT", i) for i in (6, 7)]
        self.assertEqual([g[0] for g in last], [12, 12])
        self.assertEqual([g[1] for g in last], [6663, 6661])
        self.assertIn("CYCFT i=0,1,2: 1 197 / 895 / 886 ticks", self.three)
        self.assertIn("(29.56 / 22.10 / 21.88 us)", self.three)
        self.assertIn("CYCLT i=6,7: 12 ticks (0.30 us)", self.three)
        self.assertIn("CYCFT 1 171 / 1 067 / 1 067; CYCLT 6 663 / 6 661", self.three)
        for ticks, us in ((1197, 29.56), (895, 22.10), (886, 21.88), (12, 0.30)):
            self.assertAlmostEqual(ticks / 40.5, us, places=2)

    def test_the_rates_the_accounting_and_the_rest(self):
        self.assertEqual(self.field("COUNTERS", "deliveries"), "254723")
        self.assertEqual(self.field("CLOCKSEC", "capture_s"), "40.248")
        self.assertIn("254 723 in capture_s 40.248", self.three)
        self.assertIn("6 329/s (capture clock) · 6 312/s (safety clock)", self.three)
        self.assertEqual(round(254723 / 40.248), 6329)
        self.assertEqual(round(254723 / 40.356), 6312)
        self.assertEqual(self.field("CLOCKSEC", "safety_s"), "40.356")
        for key, want in (("acks", "254723"), ("rearms", "254723"), ("unmasks", "254723"), ("lean", "254719"),
                          ("verify", "4"), ("isr_w1c", "254723"), ("main_w1c", "0"), ("teardown_w1c", "1"),
                          ("overflow", "0"), ("uncertain", "0"), ("control_ok", "1")):
            self.assertEqual(self.field("COUNTERS", key), want, key)
        self.assertIn("acks = rearms = unmasks = deliveries = 254 723; lean 254 719; verify 4; isr_w1c = deliveries;", self.three)
        self.assertIn("main_w1c = 0; teardown_w1c = 1; overflow = 0; uncertain = 0; control_ok = 1; errors = 0", self.three)
        self.assertEqual(self.field("STATS", "timeouts"), "0")
        self.assertEqual(self.field("STATS", "busy"), "0")
        self.assertEqual(self.field("STATS", "transfers"), "1033033")
        self.assertEqual(self.field("STATS", "bulk_transfers"), "260900")
        self.assertIn("STATS timeouts = 0, busy = 0, transfers 1 033 033, bulk 260 900", self.three)
        self.assertEqual(len(re.findall(r"^\d+ CYCA ", self.log, re.M)), 0)
        self.assertIn("CYCA: none written", self.three)
        self.assertEqual(self.field("STREAMPUMP", "calls"), "254723")
        self.assertEqual(self.field("STREAMPUMP", "slices"), "95080")
        self.assertEqual(self.field("STREAMPUMP", "skipped_cause_pending"), "69770")
        self.assertEqual(self.field("STREAMPUMP", "arrived_during"), "32442")
        self.assertIn("skipped_cause_pending 69 770 (27.4 %)", self.three)
        self.assertEqual(round(100 * 69770 / 254723, 1), 27.4)
        self.assertEqual((self.field("STREAMPUMPT", "ticks_min"), self.field("STREAMPUMPT", "ticks_mean"),
                          self.field("STREAMPUMPT", "ticks_max"), self.field("STREAMPUMPT", "n")),
                         ("1154", "1494", "2578", "95080"))
        self.assertIn("STREAMPUMPT 1 154 / 1 494 / 2 578 ticks, n = 95 080", self.three)
        self.assertEqual((self.field("INPUT", "steps"), self.field("INPUT", "attempts"), self.field("INPUT", "completed"),
                          self.field("INPUT", "failed"), self.field("INPUT", "retry")),
                         ("184953", "7898", "7898", "0", "0"))
        self.assertIn("INPUT steps 184 953, attempts = completed = 7 898, failed = 0, retry = 0;", self.three)
        self.assertIn("INPUTT write 30 / 30 / 38, step 95 / 160 / 1 106 ticks", self.three)
        self.assertIn("write_ticks=30/30/38", self.log)
        self.assertIn("step_ticks=95/160/1106", self.log)
        for key, want in (("events", "43"), ("emitted", "43"), ("lost", "0"), ("truncated", "0"), ("overwritten", "0")):
            self.assertEqual(self.field("KEYLOG", key), want, key)
        self.assertIn("KEYLOG events = emitted = 43, lost = 0, truncated = 0, overwritten = 0", self.three)
        self.assertEqual((self.field("STREAMINV", "checks"), self.field("STREAMINV", "failures")), ("189258", "0"))
        self.assertIn("STREAMINV checks 189 258, failures 0", self.three)
        self.assertIn("STREAMSRC closed 2 404, complete 2 378, incomplete 13, anomaly 13, published 2 378", self.three)
        self.assertEqual(self.field("STREAMSRC", "closed"), "2404")
        self.assertEqual(self.field("STREAMCONS", "presented"), "2377")

    def test_no_figure_is_a_threshold(self):
        p = plain(self.three)
        for tok in ("no figure here is a threshold and none is a tolerance",
                    "What is comparable is the SHAPE",
                    "A game also produces a different VIDEO / AUDIO mix than the indexed stimulus, so the rate is read with that stated, never against a fixed number",
                    "the first run is the measurement"):
            self.assertIn(tok, p, tok)


class QuestionAAndTheInstrument(unittest.TestCase):
    def test_the_criterion_is_his_and_the_machine_half_is_scoped(self):
        two = plain(part(2))
        for tok in ('"ambos os controles funcionam e tem que apresentar o mesmo comportamento… > tanto o paralelo como original."',
                    "not to be reinterpreted after the run",
                    "play-0001 writes NO frames at all", "What the game did is the OPERATOR'S CHANNEL, alone",
                    "whether the word was SENT AT ALL", "This pair addresses BOTH",
                    "its evidence is weaker per key than the checker's was, which is stated here rather than discovered at ingestion"):
            self.assertIn(tok, two, tok)

    def test_the_verdicts_split_a_failure_by_the_key_record(self):
        eleven = plain(part(11))
        for tok in ("QUESTION A / W", "SENT R_b rose as expected -> the runtime sent the word; the failure is DOWNSTREAM",
                    "NOT SENT R_b did not rise -> the press never became a word; the failure is UPSTREAM",
                    "N/A the game ignores the key", "NOT a failure", "SPURIOUS",
                    "QUESTION A / S", "QUESTION A / K", "QUESTION T -- the timing",
                    "NOMINAL", "ANOMALOUS", "FAULT", "THIS IS THE EXPECTED POSSIBLE OUTCOME",
                    "It is a RESULT, not a failed run",
                    "with no threshold invented after the fact"):
            self.assertIn(tok, eleven, tok)
        # the form's caveat sits beside the verdicts, and is not softened
        for tok in ("THE TITLE AND", "THE FORM,", "BESIDE THEM", "A ROM DELIVERED BY THE FLASHCART",
                    "WHICH of the three candidates", "If he declares an ORIGINAL, the caveat is lifted for that run",
                    "CANNOT BE ATTRIBUTED WITH CERTAINTY BETWEEN THE RUNTIME AND THE CARTRIDGE",
                    "A good instrument does not soften this"):
            self.assertIn(tok, eleven, tok)

    def test_three_candidates_are_named_each_evaluated_and_he_declares_at_run_time(self):
        four = plain(part(4))
        for tok in ('"nomeie os 3 jogos por enquanto... Quando eu testar eu informo."',
                    "THREE CANDIDATES ARE NAMED HERE and HE DECLARES AT RUN TIME which one he used",
                    "every candidate is evaluated HERE, before any data, so none can be chosen after the fact to suit a result",
                    "the two runs of the PAIR must use the SAME one",
                    # 1 WarioWare
                    "WarioWare, Inc.: Mega Microgame$! -- the NORMAL WarioWare, NOT Twisted",
                    '"sobre o WarioWare seria o WarioWare normal... Nao o Twisted."',
                    "A ROM DELIVERED BY THE FLASHCART, on the EZ-Flash Omega DE's NOR -- the third value of the status axis",
                    "THE CRISPEST FEEDBACK OF THE THREE", "a mapping error is not ambiguous",
                    "L, R, SELECT and possibly B are EXPECTED N/A",
                    "NO gyroscope, NO accelerometer or tilt sensor, NO solar sensor, NO rumble motor, NO real-time clock",
                    # 2 Emerald
                    "Pokemon Emerald", "HIS NOTE, recorded as his: he knows it uses L and R",
                    "COVERS THE MOST BUTTONS of the three", "a slower-paced game, so \"it responded reliably\" is a softer judgement",
                    "the Pokemon Emerald cartridge carries a REAL-TIME CLOCK", "FROM A FLASHCART the RTC may be ABSENT OR EMULATED",
                    "berry growth, tides and other time-of-day events -- NOT the input path",
                    "a reader must not later mistake a clock-driven oddity for an input finding",
                    # 3 Yoshi
                    "Super Mario Advance 3: Yoshi's Island", "recorded as HIS STATEMENT and NOT asserted by this part",
                    "he BELIEVES it uses L and R",
                    # the reason the choice got easier, and the caveats
                    "IT IS NOT THE CONSTRAINT IT WAS, and the reason is Issue #39",
                    "THE WINDOW IS GONE", "Removing that constraint is what Issue #39 bought",
                    "THE CAVEAT TRAVELS WITH EVERY CITATION, never silently and never softened",
                    "If he declares an ORIGINAL on the day, the caveat is lifted FOR THAT RUN",
                    "still rejected WarioWare: TWISTED",
                    "OWNS it as an ORIGINAL cartridge in two regional versions",
                    "The Simpsons: Road Rage, his earlier \"paralelo\", is not among the three",
                    "N/A IS NOT A FINDING", "a game that never asks for L is NOT evidence that L fails"):
            self.assertIn(tok, four, tok)
        # the three are named and nothing else is proposed as the instrument
        self.assertEqual(len(re.findall(r"^  \d  ", part(4), re.M)), 3)
        # the two gate items: 1 answered at run time by design, 2 ANSWERED before the runs (the amendment record)
        for tok in ("GATE ITEM 1", "GATE ITEM 2 -- ANSWERED", '"Sobre o Z, tudo bem"',
                    '"segurar Z encerra a sessao e vai para a tela para gerar os logs, correto?", confirmed',
                    "WHAT IS ANSWERED IS THE END, NOT THE 250 ms DURATION",
                    "If it is awkward, that is a FINDING of the run", "never a broken gate and never a reason to discard a run"):
            self.assertIn(tok, four, tok)

    def test_the_amendment_is_recorded_dated_and_additive(self):
        head = plain(v76()[:v76().index("#### V7.6.1")])
        for tok in ("AMENDED BEFORE HARDWARE the same day (Issue #41 continued)",
                    "GATE ITEM 2 ANSWERED by the Operator", "Question T's AUDIO-only control stated for what it is",
                    "THE AMENDMENT RECORD (2026-09-21, Issue #41 continued)",
                    "dated and never a silent edit", "the precedent is Issue #23's amendment of §V7.1 and Issue #37's of §V7.5",
                    "Two changes, both additive; nothing else in this part moves",
                    '"Sobre o Z, tudo bem."', "WHAT HE CONFIRMED IS THE END, NOT THE 250 ms DURATION SPECIFICALLY",
                    "that is a FINDING OF THE RUN", "The constant is one line of main.c and is changed by a checkpoint, never by the day",
                    "a CONTROL INSIDE THE SAME RUN"):
            self.assertIn(tok, head, tok)

    def test_the_audio_only_gap_is_the_control_inside_the_run(self):
        three = plain(part(3))
        for tok in ("THE CONTROL IS INSIDE THE SAME RUN, which is what makes this a measurement and not an assertion",
                    "an AUDIO-only cycle never had one", "the VIDEO cycles are the treatment", "the AUDIO-only cycles are the control",
                    "predicts them UNCHANGED at RUN 17's 12 ticks",
                    "needs no cross-run comparison at all",
                    "If BOTH gaps move, the cause is not the witness step and the run says so",
                    "RUN 17's table is its reference, not its authority"):
            self.assertIn(tok, three, tok)


class TheProcedureAndTheNotation(unittest.TestCase):
    def test_the_notation_rule_starts_here_and_the_frozen_lists_keep_their_text(self):
        nine = part(9)
        p = plain(nine)
        for tok in ("THE NOTATION, from here on", "L1 R2 A3", "PlayStation shoulder", "the compression was the project's, not his error",
                    "every operator-facing action list separates the button from its count, the count carries × and whitespace",
                    "The frozen lists of §V7.1, §V7.3 and §V7.5 keep their text"):
            self.assertIn(tok, p, tok)
        # the list itself obeys the rule: a count is always "× N" with whitespace, never glued to a name
        rows = [l for l in nine.splitlines() if re.match(r"^\s{0,3}\d{1,2}\s{3}\S", l)]
        self.assertGreaterEqual(len(rows), 14)
        for l in rows:
            self.assertNotRegex(l, r"\b(START|SELECT|A|B|L|R|UP|DOWN|LEFT|RIGHT|Z)\d", "digits glued to a name: " + l)
        # inside the action-list block only: prose about the rule is not a row of it
        block = nine[nine.index("step  action"):nine.index("```", nine.index("step  action"))]
        self.assertIn("×", block)
        for l in block.splitlines():
            if "×" in l:
                self.assertRegex(l, r"\S\s\s+×\s+\d", "the count must carry × with whitespace: " + l)
        self.assertIn("SELECT (the pad's X = GBA SELECT)", nine)          # dual-named
        # ordinary play, the N/A expectation, the session end
        for tok in ("LEANING ON ORDINARY PLAY", "PLAY THE GAME for about three minutes",
                    "EXPECT A COLUMN OF N/A, AND READ IT AS THE REAL ANSWER IT IS",
                    "L, R, SELECT and possibly B are expected N/A", "A game that never asks for L is NOT evidence that L fails",
                    "It is not a finding, it is not \"DOES NOT WORK\"",
                    "END THE SESSION: hold Z for about one", "K is computed over steps 2-12, 14 and 15",
                    "One press each in step 15 is allowed here, and was forbidden before"):
            self.assertIn(tok, p, tok)
        # the recovery procedure is the frozen one, byte for byte
        self.assertIn("""```text
If the AGB hangs, input behaves as if stuck, or a menu navigates by itself:
power the console off at the button, wait, power on. Do not try to correct
it with the controller. Record what was seen before the power-off.
```""", nine)

    def test_the_session_and_the_identity_gate(self):
        five, eight = plain(part(5)), plain(part(8))
        for tok in ("ONE file: sd:/open-gbp/GBP-PLAY-001_play-0001.log", "NO SIDECARS",
                    "BOUNDED BY THE OPERATOR, not by the runtime", "Z held 250 ms -> stop=session_end, the only success",
                    "THE WHOLE SESSION MUST FIT INSIDE 720 s", "NOT EXPORTED and NOT STAGED by this part",
                    "12-stream = stream-0015, dd545c01...3a49, untouched"):
            self.assertIn(tok, five, tok)
        for tok in ("/media/rafael/SD_GC/Open-GBP/13-play/boot.dol", "487 968 B", DOL_SHA,
                    "no sd:/open-gbp/GBP-PLAY-001_play-0001.log exists on the SD",
                    "MOVED ASIDE, never deleted", "If ANY identity differs: DO NOT RUN"):
            self.assertIn(tok, eight, tok)
        self.assertIn(DOL_SHA, plain(part(5)))
        self.assertIn(COMMIT, plain(part(5)))

    @unittest.skipUnless(os.path.isfile(BUILD_INFO), "run `make build` first")
    def test_the_named_artifact_is_the_built_one(self):
        info = dict(l.split("=", 1) for l in read(BUILD_INFO).splitlines() if "=" in l)
        if info.get("commit") != COMMIT:
            self.skipTest("the play image on this host is built at %s; the part names %s's" % (info.get("commit"), COMMIT))
        self.assertEqual(info["sha256_dol"], DOL_SHA)
        self.assertEqual(info["build_id"], "play-0001")
        self.assertEqual(os.path.getsize(os.path.join(ROOT, "build", "poc", "gbp-play-session", "gbp-play-session.dol")),
                         int(DOL_SIZE.replace(" ", "")))


class TheNamesAndTheEmptyRecord(unittest.TestCase):
    def test_the_two_names_are_reserved_once_and_now_also_appear_in_their_result(self):
        """Issue #52: the runs happened, so the reserved names are USED as well as reserved.

        The pin was "reserved exactly once and the file does not exist". After
        execution each name legitimately appears twice on the page — once in
        §V7.6.7's reservation and once in §V7.8.2's receipt — and the archived
        file DOES exist, which is the point of reserving a name. What survives
        of the original guard is the part still worth guarding: the name is
        reserved exactly once, it is never used for a THIRD thing, and nothing
        beyond the runs that have happened is named anywhere.
        """
        t = read(HW)
        reservation = t[t.index("#### V7.6.7 "):t.index("#### V7.6.8 ")]
        result = t[t.index("### V7.8 "):]
        for n in NAMES:
            self.assertEqual(reservation.count(n), 1, "%s is not reserved exactly once" % n)
            self.assertEqual(result.count(n), 1, "%s does not appear exactly once in its result" % n)
            self.assertEqual(t.count(n), 2, "%s appears somewhere other than its reservation and its result" % n)
        self.assertEqual(read(HANDOFF).count(NAMES[0]), 1)
        self.assertIn("Two names, where every previous pair reserved ten", plain(part(7)))
        self.assertIn("writes ONE file per run and no sidecars", plain(read(HANDOFF)))
        # no raw name above run22 anywhere
        self.assertEqual(re.findall(r"captures/local/\S*run(?:3[8-9]|[4-9]\d)\S*", t), [])   # the bound moves with the reservations it must not see; run30: Issue #58, §V8 (GBP-AUDIO-001, reserved and not on disk); run31: Issue #64, §V9 (GBP-AUDIO-002, reserved and not on disk); run32: nothing beyond RUN 31 exists (Issue #67)   # run36 / run37: Issue #90 (RUN 36 ingested, §V21.9) and #91
        self.assertEqual(re.findall(r"captures/local/\S*run(?:3[8-9]|[4-9]\d)\S*", read(HANDOFF)), [])   # the bound moves with the reservations it must not see; run30: Issue #58, §V8 (GBP-AUDIO-001, reserved and not on disk); run31: Issue #64, §V9 (GBP-AUDIO-002, reserved and not on disk); run32: nothing beyond RUN 31 exists (Issue #67)   # run36 / run37: Issue #90 (RUN 36 ingested, §V21.9) and #91

    def test_the_record_table_is_empty(self):
        table = part(13)
        i = table.index("field                                     RUN 21")
        rows = [l for l in table[i:].splitlines() if re.match(r"^\S.*  --", l)]
        self.assertGreaterEqual(len(rows), 25)
        for l in rows:
            # the CELLS are everything before the trailing "(hint)"; a hint may legitimately name what is expected
            cells = l.split("  (")[0]
            self.assertGreaterEqual(len(re.findall(r"(?<= )(--)(?= |$)", cells)), 1, l)
            self.assertNotRegex(cells, r"\bPASS\b|\bFAIL\b|\bWORKS\b|=\s*\d", "nothing is pre-filled: " + l)
        self.assertIn("nothing pre-filled", plain(table))

    def test_what_the_part_is_not(self):
        p = plain(part(14))
        for tok in ("Not authorised by this pre-registration: hardware execution",
                    "staging, exporting, copying or flashing anything", "slot 13-play is exported under the Hardware Issue",
                    "choosing the Operator's game for him beyond the requirement that it passes through the button path",
                    "deciding whether Phase 5 closes", "No new physical evidence ID exists",
                    "PRE-REGISTERED / NOT RUN / NOT AUTHORISED HERE"):
            self.assertIn(tok, p, tok)
        self.assertIn("Whether Phase 5 closes is still not decided by the runs", plain(part(2)))
        self.assertIn("What it does NOT decide: whether Phase 5 closes", plain(part(12)))


class TheCorrectionOfTheAuditFigure(unittest.TestCase):
    def test_the_correction_is_recorded_on_top_with_its_cause(self):
        s = plain(read(INPUT_PATH))
        self.assertIn("### 13.8 CORRECTION (2026-09-21, Issue #41) — the audit cross-check figure of §13.1", s)
        for tok in ("The correct figure for the committed profile on the committed build is 102",
                    "gbp_keypad_write's call sites 1 -> 2", "gbp_input_map / gbp_keypad_encode removed from elf_required",
                    "105 - 3 = 102", "0 findings on the play image, 102 on the stream image, 33 for the stream profile on the play image",
                    "The host test asserts the property", "never the exact count, so no test moved",
                    "a figure measured against an intermediate state is not the figure for the checkpoint"):
            self.assertIn(tok, s, tok)
        # the earlier text keeps its words
        self.assertIn("the `play` profile finds 105 things wrong with the stream image", read(INPUT_PATH))
        self.assertIn("CORRECTED to 102", read(HANDOFF))


class NothingFrozenMoved(unittest.TestCase):
    def test_the_earlier_parts_are_byte_identical_and_nothing_else_changed(self):
        if not guards.base_available(BASE):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE)
        old = subprocess.run(["git", "-C", ROOT, "show", "%s:docs/research/HARDWARE_TESTS.md" % BASE],
                             capture_output=True, text=True, check=True).stdout
        new = read(HW)
        self.assertEqual(new[new.index("### V7.1 "):new.index("### V7.6 ")].rstrip("\n"),
                         old[old.index("### V7.1 "):].rstrip("\n"), "§V7.1–§V7.5 byte-identical")
        changed = guards.changed_since(BASE, ["src", "poc", "tools", "Makefile", "stimulus", "captures/fixtures", "docs/protocol", "docs/hardware", "docs/research/EVIDENCE.md", "docs/research/UNKNOWNS.md"])   # Issue #29: tracked AND untracked, one implementation
        # Issue #65 (2026-09-22) BUILT stimulus/agb-tone (tone-0001), §V9's two-frequency stimulus: a new
        # stimulus ROM beside the four the family already had. It touches no runtime path, no image and no
        # slot; §V9.14 records its identity and tests/host/test_agb_tone.py runs its own code on the host.
        changed = changed - {"stimulus/agb-tone/Makefile", "stimulus/agb-tone/source/main.c"}
        # Issue #70 (2026-09-22) BUILT stimulus/agb-sweep (sweep-0001), §V11's TWO-AXIS stimulus: a new
        # stimulus ROM beside the five the family now has, and agb-tone is NOT touched (a test pins it
        # byte-identical). It touches no runtime path, no image and no slot; §V11.15 records its
        # identity and tests/host/test_agb_sweep.py runs its own code on the host.
        changed = changed - {"stimulus/agb-sweep/Makefile", "stimulus/agb-sweep/source/main.c"}
        # Issue #64 (2026-09-22) pre-registered agb-tone (§V9) and made its constructions executable BEFORE
        # the ROM exists: tools/v9tone.py is exercised on SYNTHETIC vectors only, reads no run, authorises
        # nothing and promotes nothing.
        changed = changed - {"tools/v9tone.py"}
        # Issue #69 (2026-09-22) pre-registered the amplitude sweep (§V11) and froze its constructions
        # BEFORE stimulus/agb-sweep exists: tools/v11sweep.py runs on SYNTHETIC vectors only, reads no
        # run, authorises nothing and promotes nothing. It is the fourth outing of the same discipline.
        changed = changed - {"tools/v11sweep.py"}
        # Issue #74 (2026-09-23) added tools/geckorx.py, the HOST receiver for the Operator's Pico
        # Gecko. It reads a serial port and writes bytes to a file; it touches no image, no POC and
        # no runtime path, and CLAUDE.md §14 forbids anything coming to depend on the device.
        changed = changed - {"tools/geckorx.py"}
        # Issue #75 (2026-09-23) pre-registered U-GBP-038's separator (§V13) and froze its
        # construction BEFORE the run: tools/v13sep.py runs on SYNTHETIC vectors only, borrows
        # v11sweep's classifier unchanged, reads no run and authorises nothing.
        changed = changed - {"tools/v13sep.py"}
        # §V14 (2026-09-23) froze the METHOD of RUN 34's measurement before the run:
        # tools/v14repeat.py contains no gate, reproduces §V11.16.7 exactly, reads no run.
        changed = changed - {"tools/v14repeat.py"}
        # Issue #79 (2026-09-23): tools/v16bitgate.py, QUESTION V repaired at bit resolution and
        # QUESTION L, frozen forward only; it imports v11sweep and edits nothing.
        changed = changed - {"tools/v16bitgate.py"}
        # Issue #80 (2026-09-23): tools/v17pred.py (the predictions, frozen first) and
        # tools/v17decode.py (the H-PWM decoder); they read the captures and touch no image.
        changed = changed - {"tools/v17pred.py", "tools/v17decode.py"}
        # Issue #81 (2026-09-23): the AUDIO decode as runtime code -- src/audio/ (the decoder, the
        # replay backend, the 125/16 resampler and its generated table), its generator
        # tools/gen_aresamp.py, and RUN 33 / RUN 34's raw sidecars versioned as fixtures. Host-tested
        # only: no image links src/audio/, and no POC, slot or runtime path changed.
        changed = changed - {"src/audio/gbp_adec.c", "src/audio/gbp_adec.h", "src/audio/gbp_asrc.c",
                             "src/audio/gbp_asrc.h", "src/audio/gbp_aresamp.c", "src/audio/gbp_aresamp.h",
                             "src/audio/gbp_aresamp_coef.h", "tools/gen_aresamp.py", "captures/README.md",
                             "captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz",
                             "captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run34-audio.bin.gz",
                             # Issue #90: RUN 36's console log, byte for byte (§V21.9)
                             "captures/fixtures/hw-gamecube-gbp-2026-09-23-aout-0002-run36.log",
                             # Issue #91: RUN 37's console log, byte for byte (§V19.14)
                             "captures/fixtures/hw-gamecube-gbp-2026-09-23-drain-0001-run37.log"}
        # Issue #82 (2026-09-23): tools/v18block.py, what one AUDIO block contains, measured on the
        # versioned fixtures (§V18). Descriptive, no gate; it reads captures and touches no image.
        changed = changed - {"tools/v18block.py"}
        # Issue #84 (2026-09-23): tools/v19drain.py, §V19's three gates, FROZEN BEFORE the run
        # (GBP-AUDIO-005). Synthetic vectors only; it reads no capture and authorises nothing.
        changed = changed - {"tools/v19drain.py"}
        # Issue #92 (2026-09-23): tools/v22accept.py, §V22's gates (Phase 6's acceptance), FROZEN
        # BEFORE the POC exists. Synthetic vectors only; it reads no capture and authorises nothing.
        changed = changed - {"tools/v22accept.py"}
        # Issue #92: Phase 6's acceptance image and its chain -- poc/gbp-audio-live, src/audio/gbp_alive.*
        # and gbp_aplay.* (host-tested: tests/unit, tests/host/test_alive_chain.py), and the report
        # builder frozen with it. No earlier image, path or module changed.
        changed = changed - {"poc/gbp-audio-live/Makefile", "poc/gbp-audio-live/source/main.c",
                             "src/audio/gbp_alive.c", "src/audio/gbp_alive.h", "src/audio/gbp_aplay.c",
                             "src/audio/gbp_aplay.h", "tools/v22report.py"}
        # Issue #84: src/audio/gbp_adrain.* -- GBP-AUDIO-005's phase machine and coverage
        # counter, host-tested only (tests/unit/test_gbp_adrain.c). No image links it yet.
        changed = changed - {"src/audio/gbp_adrain.c", "src/audio/gbp_adrain.h"}
        # Issue #84 (2026-09-23) BUILT GBP-AUDIO-005's image, drain-0001 (§V19.11 A4.1): play-0001 plus
        # the drain's period decoder (src/audio/gbp_aperiod.*, host-tested), the POC that carries it, and
        # tools/v19report.py, the log -> report builder frozen before the run. The service path gains two
        # optional hooks, NULL in every earlier build (tests/unit/test_gbp_video_state.c proves the operation
        # stream identical), and tests/host/test_drain_image.py diffs the image against play-0001.
        changed = changed - {"poc/gbp-audio-drain-probe/Makefile", "poc/gbp-audio-drain-probe/source/main.c",
                             "src/audio/gbp_aperiod.c", "src/audio/gbp_aperiod.h", "tools/v19report.py"}
        # Issue #87 (2026-09-23) restored `make build` at HEAD: since #59 the service module references the
        # AUDIO window, so these four POCs link gbp_awin.c the way they link gbp_vwitness.c, cfg.awin NULL.
        # No executed artifact is rebuilt or relabelled; tests/host/test_poc_link_closure.py keeps the class
        # from recurring unobserved.
        changed = changed - {"poc/gbp-play-session/Makefile", "poc/gbp-video-stream-probe/Makefile",
                             "poc/gbp-video-state-probe/Makefile", "poc/gbp-video-color-probe/Makefile"}
        # Issue #86 (2026-09-23) BUILT AOUT-HW-001, the OUTPUT-PATH image (not a GBP audio test): the
        # listening sequence (src/audio/gbp_alisten.*, bit-identical to the #80/#81 reference on RUN 33,
        # tests/host/test_audio_listen.py) and the POC that plays it through the AI. No GBP code is linked
        # into it (the `aout` audit profile), and no runtime path, image or slot changed.
        changed = changed - {"src/audio/gbp_alisten.c", "src/audio/gbp_alisten.h",
                             "poc/audio-output-replay/Makefile", "poc/audio-output-replay/source/main.c",
                             "poc/audio-output-replay/source/fixture_embed.S",
                             # §V21.6: aout-0002's sealed play order, drawn and committed before the code
                             "poc/audio-output-replay/source/aout_order.h"}
        # Issue #62 (2026-09-22) ingested RUN 30 and needed two READERS that did not exist: awinparse.py,
        # a strict parser for the OGBPAW1 sidecar, and tprime.py, §V7.9's decision rule. Both only read and
        # report; the VERDICT constructions stay in tools/v8audio.py, which tests/host/test_run30.py diffs
        # against the commit that wrote it.
        changed = changed - {"tools/awinparse.py", "tools/tprime.py"}
        # Issue #59 (2026-09-22) BUILT the image §V8 needs: the AUDIO window and its OGBPAW1 sidecar
        # (src/gbp/gbp_awin*, host-testable, no libogc) and the POC that carries them, stream-0016. The
        # service path gains ONE optional config field and ONE call after the AUDIO drain and its commit;
        # no device operation is added, removed or reordered (tests/host/test_awin_image.py diffs it).
        changed = changed - {"src/gbp/gbp_awin.c", "src/gbp/gbp_awin.h",
                             "src/gbp/gbp_awindump.c", "src/gbp/gbp_awindump.h",
                             "poc/gbp-audio-window-probe/Makefile",
                             "poc/gbp-audio-window-probe/source/main.c",
                             # the hook itself, and the audit profile that pins where it may be called from
                             "src/gbp/gbp_vstate_probe.c", "src/gbp/gbp_vstate_probe.h", "tools/poc_audit.py"}
        # Issue #50 (2026-09-22) made §V7.6.11's frozen verdicts executable BEFORE RUN 21 / RUN 22's logs
        # existed: tools/v7611.py recomputes them and is exercised on SYNTHETIC vectors only, so the
        # ingestion cannot tune the constructions to the data. It reads no run and changes nothing.
        changed = changed - {"tools/v7611.py"}
        # Issue #58 (2026-09-22) pre-registered Phase 6's first physical run (§V8, GBP-AUDIO-001) and made its
        # three-model predictions executable BEFORE any build or log existed: tools/v8audio.py is exercised on
        # SYNTHETIC vectors only, reads no run, authorises nothing and promotes nothing.
        changed = changed - {"tools/v8audio.py"}
        # Issue #29 (2026-09-21) added the promotion sweep tool; it reads the pages and judges nothing, and
        # Issue #44 (2026-09-22) hardened the staging tool against destroying a frozen slot: the manifest gained a frozen_sha256 column
        changed = changed - {"tools/reconcile.py", "tools/swiss_export.py", "tools/swiss-layout.tsv",
                             "Makefile",                      # Issue #44: the Makefile's help names the --only path
                             "docs/research/UNKNOWNS.md"}     # Issue #30: U-GBP-009 gained a PROCEDURE; its status
                                                              # did not move (tests/host/test_external_reference.py)
        # Issue #46 (2026-09-22) promoted the CONTROL bit 0x02 split as GBP-HW-272: the evidence entry, the REGISTERS.md row
        # separating USAGE (C) from this project's measurement (F) from the cause (H), and U-GBP-017's Needs list
        changed = changed - {"docs/protocol/REGISTERS.md", "docs/research/EVIDENCE.md"}
        # Issue #48 (2026-09-22) promoted the cartridge-sensing bits into the consolidated hardware pages:
        # the rows carried the references' usage only while the Keypad rows beside them carried their
        # hardware history, so they understated 36 runs. Statuses were COPIED from EVIDENCE, none changed.
        changed = changed - {"docs/hardware/GBS-DOL.md", "docs/hardware/ARCHITECTURE.md"}
        # Issue #95 (2026-09-24) promoted Phase 6 into docs/protocol/AUDIO.md (new), indexed it in README.md,
        # and corrected the stale audio rows its reconciliation sweep found (REGISTERS.md, INITIALIZATION.md,
        # ARCHITECTURE.md, GBS-DOL.md) as wording that cites EVIDENCE. Documentation only; no status moved.
        changed = changed - {"docs/protocol/AUDIO.md", "docs/protocol/README.md", "docs/protocol/INITIALIZATION.md",
                             "docs/protocol/REGISTERS.md", "docs/hardware/ARCHITECTURE.md", "docs/hardware/GBS-DOL.md"}
        # Issue #96 (2026-09-24) swept the consolidated set for pages disagreeing with the record:
        # VIDEO.md gained a pointer to AUDIO.md, docs/hardware/README.md its missing AUDIO.md entry.
        changed = changed - {"docs/protocol/VIDEO.md", "docs/hardware/README.md"}
        self.assertEqual(" ".join(sorted(changed)).strip(), "", "changed against the base: " + " ".join(sorted(changed)))

    def test_no_evidence_id_was_minted_and_the_records_agree(self):
        ev = read(EVIDENCE)
        # Issue #46 (2026-09-22) minted GBP-HW-272 (the CONTROL bit 0x02 split, from the archive); #41 minted none,
        # so the sentinel moves to the next free id and this guard goes on testing what it was written to test
        # 318: #90, RUN 36 ingested (the output path, heard); 319…321: #91, RUN 37; the sentinel moves again
        self.assertNotIn("GBP-HW-322", ev)   # 317: #84, the start-up stall invariance (an archive property)
        self.assertNotIn("GBP-PLAY-001", ev)
        h = plain(read(HANDOFF))
        for tok in ("ISSUE #41 (2026-09-21): RUN 21 / RUN 22 PRE-REGISTERED as GBP-INPUT-004", "issue 41",
                    "validate #41's pre-registration",
                    # the bullet was rewritten when Hardware Issue #43 staged the image (2026-09-21): what must still
                    # hold is that nothing has RUN, which is what the pin now reads
                    "That RUN 21 / RUN 22 have run.",
                    "That a column of N/A in the acceptance runs is a finding"):
            self.assertIn(tok, h, tok)
        self.assertIn("The acceptance pair, pre-registered — RUN 21 / RUN 22 (GitHub Issue #41", plain(read(ROADMAP)))
        d = read(DEVLOG)
        self.assertIn("## 2026-09-21 — Issue #41: RUN 21 / RUN 22 PRE-REGISTERED", d)
        self.assertIn("documentation only", plain(d[d.rindex("## 2026-09-21 — Issue #41"):]))


if __name__ == "__main__":
    unittest.main()
