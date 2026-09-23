"""tests/host/test_v19_amendment4.py -- §V19.11 (AMENDMENT 4), GBP-HW-317 and
GBP-HW-316's narrowing (GitHub Issue #84, GBP-AUDIO-005).

AMENDMENT 4 was reached by checking premises against the archive, three times,
and each check found the premise wrong. So this file does the same thing in
code, in two halves:

  * the PAGE: what the amendment and the two entries say is pinned from the
    sources, and those tests never skip -- including the claims it must NOT
    make (a refuted attribution of the stalls, and a scene-change claim the
    archive contradicts);
  * the ARCHIVE: every figure the amendment and GBP-HW-317 quote is recomputed
    from the seven raw session logs when they are on this machine, by the
    method GBP-HW-316 used -- and that method is itself checked by reproducing
    GBP-HW-316's 68.06 / 68.59 before it is trusted with anything new.
"""
import hashlib
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
LOCAL = os.path.join(ROOT, "captures", "local")
TB_HZ = 40500000

# (label, image, file, size, sha256, frames, episodes, not_preserved, capture_s, deficit, AUDIO blocks)
SESSIONS = [
    ("RUN 21", "play-0001", "GBP-PLAY-001_play-0001-run21.log", 195301,
     "cae3ecfcd16ae319ad19968190560f900c0989ed7463f54da45e1dd5a4fc09c4", 16354, 544, 540, 273.810586, 72.16, 1121456),
    ("RUN 22", "play-0001", "GBP-PLAY-001_play-0001-run22.log", 168773,
     "a7bf2dbf014b6dca059e7b6a436e6bd81a1b01b28310bbd383cdea7b0d005c14", 12064, 420, 416, 201.995601, 71.98, 827302),
    ("RUN 25", "play-0001", "GBP-PLAY-001_play-0001-run25.log", 94398,
     "70b247675e6f116881872162f0900c8d79fd80f67e703ffb50dac4e0eb2d42a2", 3173, 27, 23, 53.130126, 68.00, 217553),
    ("RUN 26", "play-0001", "GBP-PLAY-001_play-0001-run26.log", 94354,
     "5fb2161b4306b3d21860da19bbf5390ffd1b17a80661598c17587ed5b382f15d", 1859, 27, 23, 31.124795, 67.16, 127420),
    ("RUN 33", "stream-0016", "GBP-AUDIO-004_stream-0016-run33.log", 91993,
     "8c9d085e2ff3b043e292390103030eea34a26e5aeed5ff62143f4da943c3721e", 1668, 15, 11, 27.932144, 68.06, 114342),
    ("RUN 34", "stream-0016", "GBP-AUDIO-003_stream-0016-run34.log", 92558,
     "b184311246a6d91df7915a5fdbf61f4b2f54ee24b75eadb508da0bdb012cb8af", 2302, 15, 11, 38.542869, 68.59, 157803),
    ("RUN 35", "stream-0016", "GBP-AUDIO-006_stream-0016-run35.log", 90756,
     "7e7fc90752285a1c98bd78e19f74edd2d5ba312d38cde3e1946df5a423a2d493", 2507, 15, 11, 41.979327, 67.32, 171880),
]
VISIBLE_RESYNC = [0, 9, 12, 15, 31, 34, 37, 91, 94, 97]
PRESERVED_OPEN, PRESERVED_CLOSE = [8, 30, 90, 150], [25, 89, 149, 197]


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def flat(s):
    return re.sub(r"\s+", " ", s)


def amendment():
    t = read(HW)
    i = t.index("\n### V19.11 **AMENDMENT 4")
    return t[i:t.index("\n## V20 ", i)]


def entry(ident, nxt=None):
    t = read(EV)
    i = t.index("### %s " % ident)
    j = t.find("\n### ", i + 1)
    return t[i:] if j < 0 else t[i:j]


class TheAmendmentIsWhereTheConventionPutsIt(unittest.TestCase):

    def test_it_follows_amendment_3_and_precedes_v20(self):
        t = read(HW)
        a3 = t.index("### V19.10 **AMENDMENT 3")
        a4 = t.index("### V19.11 **AMENDMENT 4 — 2026-09-23, BEFORE any hardware**")
        self.assertLess(a3, a4)
        self.assertLess(a4, t.index("\n## V20 "))

    def test_it_moves_no_gate(self):
        a = flat(amendment())
        self.assertIn("It moves no gate.", a)
        self.assertIn("D1's threshold, windows and boundary, D2's decision rule and QUESTION A's gate are as frozen", a)

    def test_v19_2s_heading_is_untouched(self):
        """A4.2: the heading STANDS -- it is not edited, and not corrected."""
        t = read(HW)
        self.assertIn("### V19.2 `QUESTION D1` — is the shortfall a startup cost or a steady-state incapacity? — "
                      "*(its `expected()` is superseded by AMENDMENT 2 B2)*", t)
        self.assertIn("The heading is not edited and is not corrected.", flat(amendment()))


class TheBaseAndItsSurvivingReason(unittest.TestCase):

    def test_the_base_is_play_0001_at_its_commit(self):
        a = flat(amendment())
        self.assertIn("play-0001 poc/gbp-play-session @ 2e48ca7", a)
        self.assertIn("`play-0001` is the minimal runtime: no research capture of any kind.", a)

    def test_the_refuted_attribution_does_not_appear_in_any_form(self):
        """The Orchestrator's instruction: the attribution of the stalls to the image's own
        instrumentation does not appear, in any form. They are the shared path's (GBP-HW-317)."""
        a = amendment().lower()
        for phrase in ("stalls are the probe", "probe's stalls", "stalls are stream-0016's",
                       "the probe's own episode", "stalls are the image's"):
            self.assertNotIn(phrase, a)

    def test_stream_0016_is_play_0001_plus_the_window_and_the_makefiles_say_so(self):
        """A4.1 is about the two EXECUTED images, so their lists are read at their own
        commits -- play-0001 at 2e48ca7, stream-0016 at 04121fe -- not at HEAD, where
        Issue #87 links gbp_awin.c into play's list to repair the #59 link regression."""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import guards

        def srcs(commit, rel):
            return set(re.search(r"^SRCS := (.*)$", guards.show(commit, rel), re.M).group(1).split())
        play = srcs("2e48ca7", "poc/gbp-play-session/Makefile")
        awin = srcs("04121fe", "poc/gbp-audio-window-probe/Makefile")
        self.assertEqual(awin - play, {"gbp_awin.c", "gbp_awindump.c"})
        self.assertEqual(play - awin, set())
        self.assertIn("gbp_vstate.c", play & awin)   # the shared episode tracker
        self.assertIn("stream-0016 = play-0001 + gbp_awin.c + gbp_awindump.c, and NOTHING else", flat(amendment()))

    def test_what_is_new_on_the_base_is_named(self):
        a = flat(amendment())
        self.assertIn("The per-second coverage counter that A6 requires is new code on this base,", a)
        self.assertIn("cfg->audio_len_live", a)
        self.assertIn("1511 operations, 0 differences", a)
        self.assertIn("AUDIO *and* VIDEO", a)

    def test_the_safety_bound_is_a3s_120(self):
        a = flat(amendment())
        self.assertIn("`PLAY_SAFETY_SECONDS` is 120, as A3 froze it.", a)
        self.assertIn("a safety bound is not raised to fit an experiment", a)


class ThePriorAndWhatItDoesNotSettle(unittest.TestCase):

    def test_the_four_sessions_are_on_the_page(self):
        a = amendment()
        for label, image, _f, _n, sha, _fr, _e, _np, cap, deficit, blocks in SESSIONS[:4]:
            row = [l for l in a.splitlines() if l.startswith(label + "  " + image)]
            self.assertEqual(len(row), 1, label)
            self.assertIn(sha[:8], row[0])
            self.assertIn("%.6f" % cap, row[0])
            self.assertIn("%.2f" % deficit, row[0])
            self.assertIn("{:,}".format(blocks).replace(",", " "), row[0])

    def test_the_prior_is_not_an_answer(self):
        a = flat(amendment())
        self.assertIn("Totals cannot show a single bad second, and a single bad second is exactly D1's question.", a)
        self.assertIn("The prior is a prior, not an answer.", a)

    def test_no_clock_sign_is_read_from_67_to_72(self):
        a = flat(amendment())
        self.assertIn("No clock sign is read from 67 → 72.", a)
        self.assertIn("not established", a)


class ALateEpisodeFailIsATrueFinding(unittest.TestCase):

    def test_the_sentence_is_verbatim(self):
        self.assertIn("> **A D1 FAIL caused by a late episode is a TRUE finding and must not be excused as\n"
                      "> an artefact.**", amendment())

    def test_its_reason_is_the_archive_and_the_scene_change_claim_is_not_adopted(self):
        a = flat(amendment())
        self.assertIn("It is not a claim that late episodes stall the drain; the archive says they have **not**", a)
        self.assertIn("**One claim was proposed during the review and is NOT adopted:** *\"a game changing "
                      "scenes would lose audio the same way\"*. The archive says the opposite.", a)

    def test_the_start_up_stalls_are_kept_out_of_d1_by_construction(self):
        a = flat(amendment())
        self.assertIn("CONTROL1 cannot pass, and so PHASE B cannot open, before 5.000 s after the "
                      "service's capture start.", a)
        # an early press is forwarded AND registered: never "press again", which would select 512 Hz
        self.assertIn("it is not lost and does not need repeating", a)
        self.assertIn("a second A press selects 512 Hz", a)
        self.assertIn("never a property of the hardware", a)
        # the arithmetic the construction rests on: frame 197 at 59.73 Hz is under the 5 s bound
        self.assertLess(197 / 59.73, 5.0)
        self.assertIn("about 3.30 s after frame 0", a)


class NotLikeForLikeAtItsTrueSize(unittest.TestCase):

    def test_the_window_copied_about_one_percent_and_the_page_says_so(self):
        a = flat(amendment())
        self.assertIn("1 280 of 114 342 / 157 803 / 171 880 blocks", a)
        self.assertIn("0.74–1.12 %", a)
        self.assertEqual((round(100 * 1280 / 171880, 2), round(100 * 1280 / 114342, 2)), (0.74, 1.12))
        self.assertIn("The whole-session comparison therefore says nothing about per-block work on EVERY block", a)

    def test_the_ceiling_is_computed_not_quoted(self):
        a = amendment()
        us = [round(t / TB_HZ * 1e6, 1) for t in (1309, 1437)]
        self.assertEqual(us, [32.3, 35.5])
        self.assertIn("32.3 - 35.5 us per armed block", a)
        self.assertAlmostEqual(1437 / TB_HZ * 4096 * 100, 14.5, places=1)
        self.assertIn("up to 14.5 % of a block's budget", a)
        self.assertIn("These are maxima; the log does not give the mean over armed blocks.", flat(a))

    def test_a_pass_does_not_locate_the_68(self):
        self.assertIn("D1 does not look at the start-up, so a PASS does not locate `stream-0016`'s 68 blocks.",
                      flat(amendment()))


class TheImplementationDefinitionsAreFixedBeforeData(unittest.TestCase):

    def section(self):
        a = amendment()
        return a[a.index("#### A4.7 Implementation definitions"):]

    def test_the_rising_edge_is_the_instrument_gbp_hw_313_used(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import v11sweep
        self.assertEqual(v11sweep.RESTING_DUTY, 0.5)
        self.assertEqual(int(v11sweep.RESTING_DUTY * 4096 * 8), 16384)
        self.assertIn("prev <= 16384 < cur", self.section())

    def test_a_period_across_a_length_change_belongs_to_neither_step(self):
        s = flat(self.section())
        self.assertIn("A period counts in a step only if BOTH its edges fall inside that step", s)

    def test_the_programmed_period_is_the_first_a_press(self):
        # GBATEK f = 131072 / (2048 - n), agb-sweep's first A entry n = 1024 -> 128 Hz -> 32 blocks
        self.assertEqual(4096 // (131072 // (2048 - 1024)), 32)
        self.assertIn("programmed 32 AUDIO blocks: agb-sweep's FIRST A press, 128.0 Hz", flat(self.section()))

    def test_the_control_uses_the_gates_own_rule(self):
        s = flat(self.section())
        self.assertIn("PASS iff at least 48 periods are counted and every one is exactly 32", s)
        self.assertIn("A second A press is NOT the recovery, because it selects 512 Hz", s)

    def test_the_d1_inconclusive_arm_is_resolved_and_recorded(self):
        s = flat(self.section())
        self.assertIn("That reading makes the gate unable to fail, so it cannot be the one meant.", s)
        self.assertIn("unchanged `counter_total` / `timebase_total` parameters", s)

    def test_the_d2_write_is_stated_and_placed(self):
        s = flat(self.section())
        self.assertIn("D2 write 65 536 bytes, ONE fwrite to a new file on the SD, issued from the pump slot", s)
        self.assertIn("The SD is mounted before the service starts, never during it", s)
        self.assertIn("The close's directory and FAT update is therefore OUTSIDE the measurement", s)


class TheEntries(unittest.TestCase):

    def test_gbp_hw_316_keeps_its_words_and_carries_the_dated_narrowing(self):
        e = entry("GBP-HW-316")
        h = e.splitlines()[0]
        self.assertIn("**FACT for the counts (raw logs); the location of the audio loss is an INFERENCE**", h)
        segs = re.findall(r"\*\*([^*]+)\*\*", h)
        self.assertTrue(segs[-1].startswith("2026-09-23, Issue #84: the stalls' LOCATION narrowed"), segs[-1])
        b = flat(e)
        self.assertIn("NARROWS \"all in the first ~100 frames\" -> 10 of 13 located in frames 0-97; "
                      "3 not located by the log", b)
        self.assertIn("all in the first\n         ~100 frames", e)   # the original text stays

    def test_gbp_hw_317_is_minted_with_its_class(self):
        e = entry("GBP-HW-317")
        h = e.splitlines()[0]
        self.assertIn("**FACT, a recomputable property of the archive; what produces the stalls is a HYPOTHESIS**", h)
        b = flat(e)
        self.assertIn("It is an arithmetic fit with three frames unlocated and no cost measured", b)
        self.assertIn("Three are not located.", b)
        for _l, _i, _f, _n, sha, frames, eps, notp, cap, deficit, _b in SESSIONS:
            self.assertIn(sha[:8], e)
            self.assertIn("%.6f" % cap, e)
        # the full hashes of the four play-0001 logs, which captures/README.md does not carry
        for s in SESSIONS[:4]:
            self.assertIn(s[4], e)

    def test_v18_6_stays_as_written_and_v18_10_narrows_it(self):
        t = read(HW)
        self.assertIn("- **It sits in 13 service stalls in the first ~100 frames (~1.7 s), identical in both runs.**", t)
        i = t.index("### V18.10 §V18.6's stall location, NARROWED")
        self.assertLess(t.index("### V18.9 "), i)
        self.assertLess(i, t.index("\n## V19 "))


class TheArchiveRecomputes(unittest.TestCase):
    """Only where the seven raw logs are archived; the page is pinned above regardless."""

    def setUp(self):
        if not all(os.path.exists(os.path.join(LOCAL, s[2])) for s in SESSIONS):
            self.skipTest("the seven drain-prior session logs are not archived in this checkout "
                          "(captures/local is ignored)")

    def log(self, s):
        with open(os.path.join(LOCAL, s[2]), "rb") as f:
            b = f.read()
        return b, b.decode("utf-8", "replace")

    def coverage(self, t):
        a = re.search(r"AUDIOAGG selected=(\d+) attempted=(\d+) completed=(\d+) failures=(\d+)", t)
        c = re.search(r"CLOCKS tb_hz=(\d+) .*?capture_elapsed=([0-9a-f]+)", t)
        self.assertEqual(int(c.group(1)), TB_HZ)
        n = int(a.group(3))
        el = int(c.group(2), 16) / TB_HZ
        return n, el, int(a.group(4))

    def test_the_method_first_reproduces_gbp_hw_316(self):
        """Before the method is trusted with new figures, it must give back the recorded ones."""
        got = {}
        for s in SESSIONS[4:6]:
            n, el, _ = self.coverage(self.log(s)[1])
            got[s[0]] = round(4096 * el - n, 2)
        self.assertEqual(got, {"RUN 33": 68.06, "RUN 34": 68.59})

    def test_the_bytes_are_the_recorded_bytes(self):
        for s in SESSIONS:
            b, _ = self.log(s)
            self.assertEqual((len(b), hashlib.sha256(b).hexdigest()), (s[3], s[4]), s[0])

    def test_coverage_and_deficit_and_the_rate_reproduces_the_count(self):
        for s in SESSIONS:
            n, el, failures = self.coverage(self.log(s)[1])
            self.assertEqual(n, s[10], s[0])
            self.assertEqual(round(el, 6), s[8], s[0])
            self.assertEqual(round(4096 * el - n, 2), s[9], s[0])
            self.assertEqual(failures, 0, s[0])
            # §V19.8 B1's standing check: the quoted rate, times the duration, gives back the count
            self.assertLess(abs(round(n / el, 2) * el - n), 1.0, s[0])

    def test_the_signature_is_invariant(self):
        for s in SESSIONS:
            t = self.log(s)[1]
            fc = re.search(r"FRAMECAP frames=(\d+) complete=(\d+) incomplete=(\d+) resync=(\d+)", t)
            self.assertEqual((int(fc.group(1)), int(fc.group(3)), int(fc.group(4))), (s[5], 13, 26), s[0])
            st = re.search(r"STRUCTURED status=\S+ episodes=(\d+) stable=\d+ unstable=\d+ not_preserved=(\d+) "
                           r"store_full=(\d) descriptors=(\d+) raw_slots=(\d+)", t)
            self.assertEqual(tuple(int(x) for x in st.groups()), (s[6], s[7], 1, 4, 16), s[0])
            eps = re.findall(r"EPISODE i=\d idx=\S+ state=\S+ flags=\S+ frames=\d+ stable_count=\d+ "
                             r"open_frame=(\d+) close_frame=(\d+) \S+ \S+ raw=(\d+/\d+)", t)
            self.assertEqual([int(o) for o, _c, _r in eps], PRESERVED_OPEN, s[0])
            self.assertEqual([int(c) for _o, c, _r in eps], PRESERVED_CLOSE, s[0])
            self.assertEqual({r for _o, _c, r in eps}, {"4/4"}, s[0])

    def test_ten_are_located_and_three_are_not(self):
        for s in SESSIONS:
            t = self.log(s)[1]
            ev = re.search(r"EVENTS n=(\d+) shown=(\d+) dropped=(\d+)", t)
            n_events = int(ev.group(1))
            self.assertEqual(int(ev.group(2)), 192, s[0])
            seqs = [int(x) for x in re.findall(r"EV seq=(\d+) ", t)]
            # the first 128 and the last 64, and nothing between
            self.assertEqual(seqs, list(range(1, 129)) + list(range(n_events - 63, n_events + 1)), s[0])
            resync = [int(f) for f in re.findall(r"type=resync f=(\d+)", t)]
            inc = [int(f) for f in re.findall(r"type=incomplete_interval f=(\d+)", t)]
            self.assertEqual(resync, VISIBLE_RESYNC, s[0])
            self.assertEqual(inc, [f + 1 for f in VISIBLE_RESYNC], s[0])
            # the fourth preserved episode opens beyond the last printed early event
            self.assertGreater(PRESERVED_OPEN[3], 130)

    def test_late_episodes_cost_no_incomplete_frame(self):
        """The decisive pair: 23x the late episodes, the same 13."""
        by = {s[0]: s for s in SESSIONS}
        self.assertEqual((by["RUN 21"][7], by["RUN 26"][7]), (540, 23))
        self.assertGreater(by["RUN 21"][7] / by["RUN 26"][7], 23)

    def test_the_audio_window_copied_1280_blocks_per_run(self):
        for s in SESSIONS[4:]:
            t = self.log(s)[1]
            m = re.search(r"AWIN fault=- complete=1 windows=5 closed=5 stored=(\d+) seen=(\d+) ignored=(\d+) .*? "
                          r"copy_ticks=(\d+)/(\d+)/(\d+) n=(\d+)", t)
            stored, seen, ignored = int(m.group(1)), int(m.group(2)), int(m.group(3))
            self.assertEqual((stored, seen, stored + ignored), (1280, s[10], s[10]), s[0])
            self.assertIn(int(m.group(6)), (1309, 1437, 1384), s[0])


if __name__ == "__main__":
    unittest.main()
