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


def keylog(words, rc="ok", start_n=1, step=1):
    """A synthetic KEY record in the runtime's own format (GBP_INPUT_EVENT_FMT)."""
    out = ["000100 KEY n=%d act=first keys=0000 word=0000 t_poll=1 t_attempt=2 t_done=3 xfer=30 rc=%s" % (start_n, rc)]
    n = start_n
    for i, word in enumerate(words):
        n += step
        out.append("0001%02d KEY n=%d act=change keys=%04x word=%04x t_poll=%x t_attempt=%x t_done=%x xfer=31 rc=%s"
                   % (i + 1, n, word, word, 100 + i, 101 + i, 102 + i, rc))
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

    def test_K_refuses_to_invent_the_step_13_boundary(self):
        """The ambiguity Issue #50 told me to report rather than resolve."""
        seq, _ = v7611.press_sequence(words_of(keylog(HEAD)))
        k = v7611.question_K(seq, seq)
        self.assertEqual(k["verdict"], v7611.PENDING_AMENDMENT)
        self.assertIn("no machine rule for finding where step 13's ordinary play ends", k["why"])
        self.assertIn("Reported, not resolved", k["why"])
        # and the part that IS defined still computes
        self.assertEqual(k["head"]["verdict"], "AGREE")
        self.assertIn("compared over steps 2-12, 14 and 15", v7611.question_K.__doc__)
        self.assertIn("NOT IMPLEMENTED, BY REFUSAL", v7611.question_K.__doc__)


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
