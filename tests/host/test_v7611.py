"""
tests/host/test_v7611.py — GitHub Issue #50: §V7.6.11's verdict constructions
exercised on SYNTHETIC vectors only, written before RUN 21 / RUN 22's logs
existed.

THE BOUND IS THE POINT. Not one assertion here reads RUN 21, RUN 22 or any
archived log for a verdict, and no output is compared against a real run's
numbers. One test parses archived KEY records — format only, that the lines
parse and `n` increases — because that is a parser question and not a verdict
question, and it is the only place a real file is opened.

WHY SYNTHETIC IS NOT A COMPROMISE HERE. The awkward branches are the ones that
will decide how the runs are read: a press that never became a word, a word
with no press behind it, a list cut short, a session the safety budget ended, a
KEY record that lost events, a transaction that faulted while the game played
fine. A real log will exercise at most one of those. So they are built here,
adversarially, while nobody knows what the runs will say — which is the whole
reason §V7.6.11 was frozen in the first place.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v7611  # noqa: E402

B = v7611.BIT
LOCAL = os.path.join(ROOT, "captures", "local")


def w(*keys):
    """A word with these keys held."""
    v = 0
    for k in keys:
        v |= 1 << B[k]
    return v


def press(*keys):
    """One press of each key in turn: rise then release, one word per state."""
    out = []
    for k in keys:
        out.append(w(k))
        out.append(0)
    return out


def keylog(words, rc="ok", start_n=1, step=1, times=None):
    """A synthetic KEY record in the runtime's own format (GBP_INPUT_EVENT_FMT).

    `times` supplies t_poll per word when a vector needs controlled timing (the
    rejected time-gap rule is demonstrated with it).
    """
    out = ["000100 KEY n=%d act=first keys=0000 word=0000 t_poll=1 t_attempt=2 t_done=3 xfer=30 rc=%s" % (start_n, rc)]
    n = start_n
    for i, word in enumerate(words):
        n += step
        tp = times[i] if times else 100 + i
        out.append("0001%02d KEY n=%d act=change keys=%04x word=%04x t_poll=%x t_attempt=%x t_done=%x xfer=31 rc=%s"
                   % (i + 1, n, word, word, tp, tp + 1, tp + 2, rc))
    return "\n".join(out)


def words_of(text):
    lines, problems = v7611.parse_key_lines(text)
    assert not problems, problems
    return v7611.completed_words(lines)


HEAD = press("START", "A", "A", "DOWN", "DOWN", "UP", "RIGHT", "RIGHT", "RIGHT",
             "LEFT", "LEFT", "B", "B", "L", "R", "SELECT", "A")

GOOD_RECORDS = {
    "header": {"test_id": "GBP-PLAY-001", "build_id": "play-0001", "commit": "2e48ca7",
               "dropped": 0, "truncated": 0},
    "COUNTERS": {"acks": 100, "rearms": 100, "unmasks": 100, "deliveries": 100, "isr_w1c": 100,
                 "errors": 0, "transport_ok": 1, "overflow": 0, "uncertain": 0, "restore_ok": 1,
                 "main_w1c": 0, "next_cause_at_end": 1},
    "STATS": {"timeouts": 0, "busy": 0},
    "INPUT": {"selftest": 1, "steps": 1000, "attempts": 40, "completed": 40, "failed": 0,
              "first": 1, "refresh": 5, "change": 34},
    "INPUTT": {}, "KEYLOG": {"events": 35, "emitted": 35, "lost": 0, "truncated": 0, "overwritten": 0},
    "SESSION": {"stop": "session_end", "status": "ok_session_ended", "teardown": "S5_session_end"},
    "STREAMPUMP": {}, "STREAMPUMPT": {}, "STARTUP": {"mode": "normal"}, "STARTUPT": {}, "STARTUPV": {},
}
REFERENCE = {"video_ack_rearm_ticks": 1197, "audio_ack_rearm_ticks": 12,
             "delivery_rate": 6329.0, "skipped_cause_pending_pct": 27.4}


def records(**over):
    import copy
    r = copy.deepcopy(GOOD_RECORDS)
    for k, v in over.items():
        if isinstance(v, dict) and k in r:
            r[k].update(v)
        else:
            r[k] = v
    return r


def reports_for(text, recs=None):
    recs = recs or records()
    lines, problems = v7611.parse_key_lines(text)
    return v7611.gate_reports(recs, lines, problems), lines, problems


class TheConstructionsAreTheFrozenOnes(unittest.TestCase):
    def test_a_key_line_counts_only_with_rc_ok(self):
        good = keylog(press("START"))
        bad = keylog(press("START"), rc="busy")
        # the runtime's own first line is act=first with word=0000, and §V7.6.11 says the
        # completed words run "in n order from 0000" -- so the sequence begins at the released
        # state whether or not that line is present, and a duplicate 0000 carries no edge
        self.assertEqual(words_of(good), [0x0000, 0x0000, w("START"), 0x0000])
        # rc != ok: no completed word beyond the implicit 0000
        lines, _ = v7611.parse_key_lines(bad)
        self.assertEqual(v7611.completed_words(lines), [0x0000])

    def test_rising_edges_are_edges_not_levels(self):
        # held across two words: one edge, not two
        words = [0x0000, w("A"), w("A", "B"), 0x0000]
        e = v7611.rising_edges(words)
        self.assertEqual(e[B["A"]], [1])
        self.assertEqual(e[B["B"]], [2])
        self.assertEqual(e[B["START"]], [])

    def test_the_press_sequence_cuts_the_menu_launch_presses_at_the_first_start(self):
        menu = press("A", "A", "DOWN")            # the flashcart menu, before the list
        seq, started = v7611.press_sequence(words_of(keylog(menu + HEAD)))
        self.assertTrue(started)
        self.assertEqual([k for _, k in seq], list(v7611.HEAD_SEQUENCE))

    def test_a_sequence_with_no_start_is_a_list_never_started(self):
        seq, started = v7611.press_sequence(words_of(keylog(press("A", "B"))))
        self.assertFalse(started)
        self.assertEqual(seq, [])
        self.assertEqual(v7611.question_K_head(seq, seq)["verdict"], "INCONCLUSIVE")


class TheAdversarialVectors(unittest.TestCase):
    def w_for(self, words, report, recs=None):
        recs = recs or records()
        reps, lines, problems = reports_for(keylog(words), recs)
        seq, _ = v7611.press_sequence(v7611.completed_words(lines))
        edges = v7611.rising_edges(v7611.completed_words(lines))
        return v7611.question_A_W(report, edges, set(k for _, k in seq),
                                  v7611.gate(reps, "KEY RECORD")["met"]), seq, reps

    def test_a_dropped_press_reads_NOT_SENT_and_names_the_end_of_the_chain(self):
        """He pressed L; no word carries it."""
        dropped = [x for x in HEAD]
        # remove L's rise/fall pair
        i = dropped.index(w("L"))
        del dropped[i:i + 2]
        rep = dict((k, "RESPONDED") for k in B)
        rep["L"] = "NO RESPONSE"
        verdicts, _, _ = self.w_for(dropped, rep)
        self.assertEqual(verdicts["L"][0], "DOES NOT WORK / NOT SENT")
        self.assertIn("UPSTREAM", verdicts["L"][1])

    def test_a_press_that_became_a_word_but_did_nothing_reads_SENT(self):
        rep = dict((k, "RESPONDED") for k in B)
        rep["B"] = "NO RESPONSE"
        verdicts, _, _ = self.w_for(HEAD, rep)
        self.assertEqual(verdicts["B"][0], "DOES NOT WORK / SENT")
        self.assertIn("DOWNSTREAM", verdicts["B"][1])

    def test_a_doubled_press_is_SPURIOUS_against_the_scripted_head(self):
        doubled = HEAD[:2] + press("A") + HEAD[2:]        # one extra A after START
        seq, _ = v7611.press_sequence(words_of(keylog(doubled)))
        sp = v7611.spurious(seq, v7611.HEAD_SEQUENCE)
        self.assertEqual(len(sp), 1, sp)
        self.assertEqual(sp[0]["key"], "A")

    def test_a_bit_that_rises_with_no_press_is_SPURIOUS_and_named_per_bit(self):
        ghost = HEAD[:2] + press("SELECT") + HEAD[2:]
        seq, _ = v7611.press_sequence(words_of(keylog(ghost)))
        sp = v7611.spurious(seq, v7611.HEAD_SEQUENCE)
        self.assertEqual([(s["key"], s["bit"]) for s in sp], [("SELECT", 2)])

    def test_a_stick_read_past_the_threshold_shows_as_a_dpad_bit(self):
        """§V7.6.11's own example: a D-pad bit from a stick read beyond ±48."""
        stick = HEAD[:2] + press("RIGHT") + HEAD[2:]
        seq, _ = v7611.press_sequence(words_of(keylog(stick)))
        sp = v7611.spurious(seq, v7611.HEAD_SEQUENCE)
        self.assertEqual(len(sp), 1)
        self.assertEqual(sp[0]["key"], "RIGHT")
        self.assertIn(sp[0]["bit"], (4, 5, 6, 7))

    def test_N_A_requires_the_bit_to_have_risen_and_says_so_when_it_did_not(self):
        """The single most valuable line in §V7.6.11, and it is machine-checked."""
        rep = dict((k, "RESPONDED") for k in B)
        rep["L"] = "N/A"
        verdicts, _, _ = self.w_for(HEAD, rep)
        self.assertEqual(verdicts["L"][0], "N/A")           # L rises in the head
        # now the same claim with the bit never rising
        dropped = [x for x in HEAD]
        i = dropped.index(w("L"))
        del dropped[i:i + 2]
        verdicts2, _, _ = self.w_for(dropped, rep)
        self.assertEqual(verdicts2["L"][0], "INCONCLUSIVE")
        self.assertIn("N/A REQUIRES the KEY record to show the bit rose", verdicts2["L"][1])

    def test_a_list_cut_short_is_read_on_the_common_prefix(self):
        short = HEAD[:10]                                   # stops in the middle of the head
        a, _ = v7611.press_sequence(words_of(keylog(HEAD)))
        b, _ = v7611.press_sequence(words_of(keylog(short)))
        k = v7611.question_K_head(a, b)
        self.assertEqual(k["verdict"], "AGREE")
        self.assertEqual(k["common_prefix"], 5)
        self.assertIn("common prefix", k["why"])

    def test_a_key_record_with_lost_events_is_inconclusive_for_the_machine_half(self):
        reps, lines, problems = reports_for(keylog(HEAD), records(KEYLOG={"lost": 3}))
        g = v7611.gate(reps, "KEY RECORD")
        self.assertFalse(g["met"])
        self.assertIn("lost=3", g["why"])
        self.assertIn("SENT / NOT SENT", g["scope"])
        rep = dict((k, "RESPONDED") for k in B)
        edges = v7611.rising_edges(v7611.completed_words(lines))
        verdicts = v7611.question_A_W(rep, edges, set(B), g["met"])
        self.assertTrue(all(v[0] == "INCONCLUSIVE" for v in verdicts.values()))

    def test_a_non_monotonic_n_is_caught_by_the_same_gate(self):
        text = keylog(HEAD, step=2)                          # n jumps by two
        reps, _, _ = reports_for(text)
        self.assertFalse(v7611.gate(reps, "KEY RECORD")["met"])
        self.assertIn("n is not increasing by one", v7611.gate(reps, "KEY RECORD")["why"])

    def test_an_unparsable_key_line_is_a_problem_not_a_silent_skip(self):
        text = keylog(HEAD) + "\n000999 KEY n=99 act=change keys=zzzz word=0000 rc=ok"
        lines, problems = v7611.parse_key_lines(text)
        self.assertEqual(len(problems), 1)
        self.assertIn("unparsable KEY line", problems[0])

    def test_a_session_ended_by_the_safety_budget_is_not_a_success_and_does_not_touch_W_S_or_T(self):
        recs = records(SESSION={"stop": "safety_budget", "status": "ok_safety", "teardown": "S5_safety"})
        reps, lines, _ = reports_for(keylog(HEAD), recs)
        g = v7611.gate(reps, "SESSION")
        self.assertFalse(g["met"])
        self.assertIn("the session gate ALONE", g["scope"])
        self.assertIn("not W, S or T", g["scope"])
        # W still reads what happened before the end
        edges = v7611.rising_edges(v7611.completed_words(lines))
        verdicts = v7611.question_A_W(dict((k, "RESPONDED") for k in B), edges, set(B),
                                      v7611.gate(reps, "KEY RECORD")["met"])
        self.assertEqual(verdicts["START"][0], "WORKS")
        # and T is untouched by the session gate
        self.assertEqual(v7611.question_T(recs, REFERENCE, reps)["verdict"], "NOMINAL")


class QuestionTAndTheOneInteraction(unittest.TestCase):
    def test_a_clean_transaction_with_nothing_moving_is_NOMINAL(self):
        recs = records(video_ack_rearm_ticks=900, audio_ack_rearm_ticks=12,
                       delivery_rate=6400.0, skipped_cause_pending_pct=27.4)
        reps, _, _ = reports_for(keylog(HEAD), recs)
        t = v7611.question_T(recs, REFERENCE, reps)
        self.assertEqual(t["verdict"], "NOMINAL")

    def test_a_quantity_moving_the_wrong_way_with_clean_accounting_is_ANOMALOUS(self):
        recs = records(video_ack_rearm_ticks=1500, audio_ack_rearm_ticks=12,
                       delivery_rate=6000.0, skipped_cause_pending_pct=27.4)
        reps, _, _ = reports_for(keylog(HEAD), recs)
        t = v7611.question_T(recs, REFERENCE, reps)
        self.assertEqual(t["verdict"], "ANOMALOUS")
        self.assertTrue(any("LONGER" in x for x in t["why"]))
        self.assertTrue(any("LOWER" in x for x in t["why"]))
        self.assertIn("a magnitude is not a verdict", t["note"])

    def test_the_audio_only_control_moving_is_reported_because_the_removal_does_not_predict_it(self):
        recs = records(video_ack_rearm_ticks=900, audio_ack_rearm_ticks=40,
                       delivery_rate=6400.0, skipped_cause_pending_pct=27.4)
        reps, _, _ = reports_for(keylog(HEAD), recs)
        t = v7611.question_T(recs, REFERENCE, reps)
        self.assertEqual(t["verdict"], "ANOMALOUS")
        self.assertTrue(any("AUDIO-only gap moved" in x for x in t["why"]))

    def test_skipped_cause_pending_is_reported_with_both_figures_and_no_threshold(self):
        recs = records(video_ack_rearm_ticks=900, audio_ack_rearm_ticks=12,
                       delivery_rate=6400.0, skipped_cause_pending_pct=41.0)
        reps, _, _ = reports_for(keylog(HEAD), recs)
        t = v7611.question_T(recs, REFERENCE, reps)
        self.assertEqual(t["verdict"], "ANOMALOUS")
        self.assertTrue(any("NO threshold invented after the fact" in x for x in t["why"]))

    def test_a_dirty_accounting_is_FAULT_and_FAULT_is_a_result(self):
        recs = records(COUNTERS={"errors": 1})
        reps, _, _ = reports_for(keylog(HEAD), recs)
        t = v7611.question_T(recs, REFERENCE, reps)
        self.assertEqual(t["verdict"], "FAULT")
        self.assertIn("a RESULT, not a failed run", t["note"])

    def test_an_anomaly_record_is_FAULT_even_with_clean_counters(self):
        recs = records(CYCA=[{"cycle": 12}])
        reps, _, _ = reports_for(keylog(HEAD), recs)
        t = v7611.question_T(recs, REFERENCE, reps)
        self.assertEqual(t["verdict"], "FAULT")
        self.assertTrue(any("CYCA" in x for x in t["why"]))

    def test_FAULT_with_the_session_completing_leaves_A_untouched_and_records_CONTEXT(self):
        """§V7.6.10's one interaction, the case that is easiest to get wrong."""
        i = v7611.one_interaction("FAULT", session_completed=True)
        self.assertEqual(i["A"], "READ ON ITS OWN RECORDS, UNCHANGED")
        self.assertIn("CONTEXT", i["why"])
        self.assertIn("NEVER A's verdict", i["why"])

    def test_FAULT_with_no_session_makes_A_inconclusive_and_says_why(self):
        i = v7611.one_interaction("FAULT", session_completed=False)
        self.assertEqual(i["A"], "INCONCLUSIVE")
        self.assertIn("nothing to play and nothing to judge", i["why"])
        self.assertIn("never as \"the game failed\"", i["why"])

    def test_nominal_and_anomalous_leave_A_alone(self):
        for v in ("NOMINAL", "ANOMALOUS"):
            self.assertEqual(v7611.one_interaction(v, True)["A"], "UNTOUCHED")


class QuestionSAndTheRefusalInK(unittest.TestCase):
    def test_S_is_SAME_only_when_both_channels_agree(self):
        rep = dict((k, "RESPONDED") for k in B)
        wv = dict((k, ("WORKS", "")) for k in B)
        s = v7611.question_A_S(wv, wv, rep, rep, "AGREE", same_instrument=True)
        self.assertTrue(all(v[0] == "SAME" for v in s.values()))

    def test_S_is_DIFFERENT_when_the_reports_differ_and_never_a_failed_run(self):
        a = dict((k, "RESPONDED") for k in B)
        b = dict(a); b["L"] = "N/A"
        wv = dict((k, ("WORKS", "")) for k in B)
        s = v7611.question_A_S(wv, wv, a, b, "AGREE", same_instrument=True)
        self.assertEqual(s["L"][0], "DIFFERENT")
        self.assertEqual(s["A"][0], "SAME")

    def test_S_is_INCONCLUSIVE_when_the_instrument_differed(self):
        rep = dict((k, "RESPONDED") for k in B)
        wv = dict((k, ("WORKS", "")) for k in B)
        s = v7611.question_A_S(wv, wv, rep, rep, "AGREE", same_instrument=False)
        self.assertTrue(all(v[0] == "INCONCLUSIVE" for v in s.values()))
        self.assertIn("different cartridge or boot path", s["A"][1])

    def test_K_is_the_head_and_its_tail_is_not_defined_rather_than_inconclusive(self):
        """§V7.6.15 (Issue #51): the amendment Issue #50's refusal earned."""
        seq, _ = v7611.press_sequence(words_of(keylog(HEAD)))
        k = v7611.question_K(seq, seq)
        self.assertEqual(k["verdict"], "AGREE")
        self.assertIn("steps 2-12 only (§V7.6.15)", k["scope"])
        self.assertEqual(k["tail"]["verdict"], v7611.NOT_DEFINED)
        self.assertEqual(k["tail"]["steps"], "14 and 15")
        # NOT inconclusive, and the reason the distinction matters is carried with it
        self.assertNotIn("INCONCLUSIVE", k["tail"]["verdict"])
        self.assertIn("no rerun would help", k["tail"]["why"])
        self.assertIn("named a comparison its own instrument cannot delimit", k["tail"]["why"])
        self.assertIn("K is computed over steps 2-12 only", v7611.question_K.__doc__)

    def test_nothing_returns_the_retired_pending_name(self):
        seq, _ = v7611.press_sequence(words_of(keylog(HEAD)))
        for result in (v7611.question_K(seq, seq), v7611.question_K_head(seq, seq)):
            self.assertNotIn(v7611.PENDING_AMENDMENT, repr(result))

    def test_K_uses_only_its_own_four_verdicts(self):
        """AGREE / EXPLAINED / FINDING / INCONCLUSIVE are K's vocabulary (§V7.6.11).

        A difference this code cannot attribute comes back as DIFFERS, which is
        stated as NOT a verdict: EXPLAINED needs the Operator's report, and the
        code does not decide that.
        """
        a, _ = v7611.press_sequence(words_of(keylog(HEAD)))
        swapped = HEAD[:2] + press("B") + HEAD[4:]          # A replaced by B at press 2
        b, _ = v7611.press_sequence(words_of(keylog(swapped)))
        k = v7611.question_K_head(a, b)
        self.assertIn(k["verdict"], ("FINDING", "DIFFERS"))
        if k["verdict"] == "DIFFERS":
            self.assertIn("not a verdict", k["note"])
            self.assertIn("EXPLAINED requires the Operator's report", k["note"])

    def test_a_list_key_he_reports_but_that_never_appears_is_a_FINDING(self):
        """§V7.6.11's second FINDING clause, which needs his channel."""
        dropped = [x for x in HEAD]
        i = dropped.index(w("L"))
        del dropped[i:i + 2]
        a, _ = v7611.press_sequence(words_of(keylog(HEAD)))
        b, _ = v7611.press_sequence(words_of(keylog(dropped)))
        rep = dict((k, "RESPONDED") for k in B)
        k = v7611.question_K_head(a, b, rep, rep)
        self.assertEqual(k["verdict"], "FINDING")
        self.assertTrue(any(x["key"] == "L" and x["pad"] == "B" for x in k["never_appeared"]), k)

    def test_S_over_the_sweep_reads_his_channel_alone_and_says_so(self):
        """§V7.6.15: S keeps both halves over the head and carries the note over the sweep."""
        rep = dict((k, "RESPONDED") for k in B)
        wv = dict((k, ("WORKS", "")) for k in B)
        head = v7611.question_A_S(wv, wv, rep, rep, "AGREE", True, segment="head")
        sweep = v7611.question_A_S(wv, wv, rep, rep, v7611.NOT_DEFINED, True, segment="sweep")
        self.assertTrue(all(v[0] == "SAME" for v in head.values()))
        self.assertTrue(all(v[2] is None for v in head.values()))
        # over the sweep S is still SAME -- his channel carries it -- and the machine half is named
        self.assertTrue(all(v[0] == "SAME" for v in sweep.values()))
        self.assertTrue(all(v7611.NOT_DEFINED in v[2] for v in sweep.values()))
        self.assertIn("his channel alone over steps 14-15", sweep["A"][1])


class TheParserAgreesWithTheRuntimesOwnFormat(unittest.TestCase):
    """Format only. No verdict is computed from an archived run in this file."""

    def test_the_archived_key_records_parse_and_n_increases(self):
        paths = [os.path.join(LOCAL, f) for f in sorted(os.listdir(LOCAL))] if os.path.isdir(LOCAL) else []
        paths = [p for p in paths if p.endswith(".log")]
        checked = 0
        for p in paths:
            with open(p, encoding="utf-8", errors="replace") as f:
                text = f.read()
            if " KEY n=" not in text:
                continue
            lines, problems = v7611.parse_key_lines(text)
            self.assertEqual(problems, [], p)
            ns = [l.n for l in lines]
            self.assertEqual(ns, sorted(ns), p)
            self.assertTrue(all(b - a == 1 for a, b in zip(ns, ns[1:])), p)
            checked += 1
        if not checked:
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_the_format_string_is_the_runtimes(self):
        h = open(os.path.join(ROOT, "src", "gbp", "gbp_input.h"), encoding="utf-8").read()
        m = re.search(r'#define GBP_INPUT_EVENT_FMT "([^"]+)"', h)
        self.assertTrue(m)
        for field in ("n=", "act=", "keys=", "word=", "t_poll=", "t_attempt=", "t_done=", "xfer=", "rc="):
            self.assertIn(field, m.group(1))
            self.assertIn(field, v7611.KEY_RE.pattern)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# The two rejected rules, implemented HERE and nowhere else, so that the reason
# they were rejected survives as a demonstration rather than as a paragraph.
# §V7.6.15 rejects both; `tools/v7611.py` implements neither.
# ---------------------------------------------------------------------------
def rejected_trailing_twelve(seq):
    """"the last twelve presses are steps 14 and 15" — rejected by §V7.6.15."""
    return [k for _, k in seq][-12:]


def rejected_largest_time_gap(lines):
    """"steps 14-15 begin after the longest pause" — rejected by §V7.6.15."""
    ok = [l for l in sorted(lines, key=lambda l: l.n) if l.rc == "ok"]
    rises = []
    prev = 0
    for l in ok:
        rose = l.word & ~prev
        prev = l.word
        if rose:
            for b in sorted(v7611.C):
                if rose & (1 << b):
                    rises.append((l.t_poll, v7611.C[b]))
    if len(rises) < 2:
        return [k for _, k in rises]
    gaps = [(rises[i + 1][0] - rises[i][0], i + 1) for i in range(len(rises) - 1)]
    _, cut = max(gaps)
    return [k for _, k in rises[cut:]]


class TheRejectedRulesAreDemonstratedWrong(unittest.TestCase):
    """§V7.6.15, and the Orchestrator's specific request on Issue #51.

    A paragraph saying "we rejected the trailing-twelve rule" is forgettable. A
    test showing it read the WRONG PRESSES WHILE LOOKING CORRECT is not. The
    vector is the realistic one: the Operator fumbles a single press in the
    closing sweep, which is exactly what a person does and exactly what the
    rule cannot survive.
    """

    def session(self, fumble=False, cutscene=True):
        """HEAD, then ordinary play, then step 14 (START ×2), then step 15's sweep.

        `cutscene` puts a pause INSIDE the play that is longer than the
        step-13 → step-14 transition, which §V7.6.15 says certainly happens in
        three minutes of platforming.
        """
        play = press("A", "RIGHT", "A", "B", "RIGHT", "A")
        step14 = press("START", "START")
        sweep = press(*v7611.SWEEP_SEQUENCE)
        if fumble:
            sweep = press("START", "A", "A") + press(*v7611.SWEEP_SEQUENCE[2:])   # one doubled A
        words = HEAD + play + step14 + sweep
        times, tick = [], 0
        for i in range(len(words)):
            # a long pause in the middle of the play, and a shorter one before step 14
            if cutscene and i == len(HEAD) + 6:
                tick += 10_000_000          # the cutscene
            elif i == len(HEAD) + len(play):
                tick += 2_000_000           # the step-13 -> step-14 transition, SHORTER than the cutscene
            else:
                tick += 1_000
            times.append(tick)
        text = keylog(words, times=times)
        lines, problems = v7611.parse_key_lines(text)
        assert not problems
        seq, started = v7611.press_sequence(v7611.completed_words(lines))
        assert started
        # the TRUE tail (steps 14 and 15), which the test knows because it built the vector
        # and which no rule reading only the KEY record can know
        true_tail = ["START", "START"] + ([k for k in v7611.SWEEP_SEQUENCE] if not fumble
                                          else ["START", "A", "A"] + list(v7611.SWEEP_SEQUENCE[2:]))
        return seq, lines, true_tail

    def test_the_amendments_K_is_unaffected_by_a_fumble_in_step_15(self):
        a, _, _ = self.session()
        b, _, _ = self.session(fumble=True)
        k = v7611.question_K(a, b)
        self.assertEqual(k["verdict"], "AGREE")
        self.assertEqual(k["head"]["common_prefix"], len(v7611.HEAD_SEQUENCE))
        self.assertEqual(k["tail"]["verdict"], v7611.NOT_DEFINED)

    def test_trailing_twelve_reads_the_wrong_presses_while_looking_correct(self):
        a, _, tail_a = self.session()
        b, _, tail_b = self.session(fumble=True)
        wa, wb = rejected_trailing_twelve(a), rejected_trailing_twelve(b)
        # on the clean run the rule happens to be right, which is what makes it tempting
        self.assertEqual(wa, tail_a)
        # on the fumbled run it is WRONG: the extra press pushed the window forward, so it
        # silently dropped the first START of step 14 and took a play press in its place
        self.assertNotEqual(wb, tail_b)
        self.assertEqual(wb, tail_b[1:])
        self.assertEqual(len(wa), len(wb))
        self.assertNotEqual(wa, wb)                      # and it reports a difference
        # THE FAILURE IS THAT ITS ANSWER LOOKS LIKE A REAL COMPARISON. Every element is a
        # valid key, the lengths match, and nothing in the output says the window slid -- a
        # reader would attribute the difference to the two pads.
        self.assertTrue(all(k in v7611.BIT for k in wb))
        first = next(i for i in range(len(wa)) if wa[i] != wb[i])
        self.assertEqual((wa[first], wb[first]), ("START", "A"),
                         "the rule reports START against A at the same position, from two runs "
                         "whose true segments both begin with START")

    def test_the_time_gap_rule_cuts_inside_the_play_and_answers_differently(self):
        _, lines_a, _ = self.session()
        seg = rejected_largest_time_gap(lines_a)
        # it cut at the cutscene, so its "steps 14-15" segment carries play presses
        self.assertNotEqual(seg[:2], ["START", "START"])
        self.assertGreater(len(seg), 12)
        # and it disagrees with the other rejected rule on the same clean run
        a, _, _ = self.session()
        self.assertNotEqual(seg, rejected_trailing_twelve(a))

    def test_the_two_rejected_rules_disagree_with_each_other_and_with_the_amendment(self):
        a, la, _ = self.session()
        b, lb, _ = self.session(fumble=True)
        answers = {
            "amendment (steps 2-12)": v7611.question_K(a, b)["verdict"] == "AGREE",
            "trailing twelve": rejected_trailing_twelve(a) == rejected_trailing_twelve(b),
            "largest time gap": rejected_largest_time_gap(la) == rejected_largest_time_gap(lb),
        }
        self.assertTrue(answers["amendment (steps 2-12)"], "the head is identical in both runs")
        self.assertFalse(answers["trailing twelve"], "the rejected rule reports a difference that is not there")
        # the three do not agree, which is the whole demonstration
        self.assertIn(False, list(answers.values()))
        self.assertIn(True, list(answers.values()))

    def test_the_amendment_says_why_both_were_rejected(self):
        hw = open(os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md"), encoding="utf-8").read()
        part = hw[hw.index("#### V7.6.15 "):hw.index("### V7.7 ")]
        p = re.sub(r"\s+", " ", part).replace("`", "").replace("**", "")
        self.assertIn("reads the wrong presses WHILE LOOKING CORRECT", p)
        self.assertIn("pauses longer than the step-13 -> step-14 transition certainly occur", p)
        self.assertIn("NOT DEFINED BY THE PRE-REGISTRATION", p)
        self.assertIn("never as INCONCLUSIVE", p)
        self.assertIn("NOTHING THE OPERATOR DOES CHANGES", p)
        self.assertIn("simultaneous two-key press that the scripted parts never use", p)
        self.assertIn("This is NOT added to RUN 21 / RUN 22", p)
        self.assertIn("Step 13 is the ordinary play; step 14 is START × 1 then START × 1", p)
