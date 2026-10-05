"""tests/host/test_playread.py -- GitHub Issue #153 (the build half): tools/playread.py, the reader of a gbp-play-gba log, on SYNTHETIC logs written in this file (no physical run exists).

Each gate has a POSITIVE control (a clean log that must read clean) and a NEGATIVE one (the same log with one thing wrong that must be caught): a reader that can only say 'fine' proves nothing.
What the reader must NOT do is tested too: decide the fallback rule, read a research record, report a void gate as passed, or call a -dirty build a candidate.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import playread  # noqa: E402

TB = 40_500_000


PRE_ORIGIN = 26266          # RUN 61's whole-session taps - blocks_in (HARDWARE_TESTS.md V31.10): taps count from the first tap, blocks_in from the press origin


def log(commit="abc1234", underruns=None, post_feed=(), stop="session_end", status="ok_session_ended", extra=(), drop=(), loss_blocks=(4096 * 55 - 451, 4096 * 300 - 2457), target="4096",
        startup_count=None, pre_origin=PRE_ORIGIN, phase_taps=None, phase_failed=(0, 0), phase_wrong=(0, 0)):
    """A play log's records, in the order main.c writes them. `underruns` is a list of (ordinal, ms) for the PLAYUND records.

    THE TAP RECORDS ARE THE CHASSIS' REAL SHAPE (Issue #156): per phase taps == blocks_in (V28PHC), and the whole-session V28TAPS taps exceeds blocks_in by `pre_origin` (the taps counted
    before the press origin and, by design, not decoded; `pre_origin=0` is the shape the reader's first tests wrongly assumed). The whole-session blocks_in is the phases' sum + 1, as in
    every archived log with phase records (V31.10). `phase_taps` overrides the per-phase taps; `phase_failed` / `phase_wrong` the per-phase counters."""
    und = underruns if underruns is not None else []
    k = 64
    pf_set = set(post_feed)                 # ordinals of `underruns` that are post-feed (teardown silence)
    startup = sum(1 for o, _ in und if o <= k) if startup_count is None else startup_count
    n_pf = sum(1 for o, _ in und if o in pf_set and o > k)
    after = len(und) - startup - n_pf
    first_after = next((o for o, _ in und if o > k and o not in pf_set), None)
    # phases: p0 55 s of capture, p1 300 s
    secs = (55, 300)
    blocks_session = sum(loss_blocks) + 1
    ptaps = tuple(phase_taps) if phase_taps is not None else tuple(loss_blocks)
    t0 = 1_000_000_000
    lines = [
        "IDENT test=GBP-PLAY-002 app=gbp-play-gba build=vehicle-0001 commit=%s libogc=libogc2 r2442.094b250" % commit,
        "PLAYCFG plan=play_gba navigate_s=60 play_bound_s=300 session_cap_s=420 wall_s=485 target=%s ahead=1 step=64 startup_k=64 cold_start=set_target mode=GBA" % target,
        "ENVSTORE frames=29100/16384 events=38315/4096 corr_cap=18915 fault=- ok=1",
        "ENVMEM bss_end=80290000 arena1_lo=802a0000 arena1_hi=81700000 arena1_free=20000000 frames_bytes=5587200 events_bytes=2452160 corr_bytes=37830 log_bytes=2097152 xfb=3x614400",
        "KEYLOG events=17 emitted=17 lost=0 truncated=0 reserve=1280",
        "V28C underruns=%d overflow=0 silences=%d mute_handed=0 dup=10 drop=10 produced=1000 handed=1000 ring_gated=0" % (len(und), len(und)),
        "V28C2 discarded=0 starved_steps=5 lost=0 blocks_in=%d ring_discarded=0 dropped_front=0 cs=0 acted=0 syncpe_lost=0 lines_lost=0" % blocks_session,
        "V28CORR n=1000 overflow=0 min=0 max=3 mean_x100=200 cap=18915",
        "V28TAPS taps=%d taps_failed=0 wrong_len=0 blocks_in=%d gap_max=1 gap_at=1" % (blocks_session + pre_origin, blocks_session),
    ]
    t = t0
    for p in (0, 1):
        t1 = t + secs[p] * TB
        lines.append("V28PHC p=%d ended=1 t0=%x t1=%x blocks_in=%d taps=%d failed=%d wrong=%d underruns=%d" % (p, t, t1, loss_blocks[p], ptaps[p], phase_failed[p], phase_wrong[p],
                     sum(1 for o, _ in und if (o <= 1760) == (p == 0)) if False else (len(und) if p == 1 else 0)))
        lines.append("V28PHD p=%d dup=5 drop=5 starved=1 produced=500 handed=500 gated=0 ring=4096,4200" % p)
        t = t1
    lines.append("PLAYSTARTUP t_dma=%x k=64 ring_at_dma=4100 ready_at_dma=1" % t0)
    for n, (o, ms) in enumerate(und[:64]):
        lines.append("PLAYUND n=%d handed=%d since_dma_ms=%d post_feed=%d" % (n, o, ms, 1 if (o in pf_set and o > k) else 0))
    lines.append("PLAYUNDER startup=%d after_startup=%d post_feed=%d first_after_handed=%s unrecorded=%d total=%d k=64" % (
        startup, after if startup_count is None else len(und) - startup - n_pf, n_pf, "-" if first_after is None else first_after, max(0, len(und) - 64), len(und)))
    lines.append("SYNCPH phase=0 t_start=1 t_end=2 ended=1 reason=cap")
    lines.append("SYNCPH phase=1 t_start=2 t_end=3 ended=1 reason=session")
    lines.append("VSTATE end status=%s class=ok reason=- stop=%s restore=ok restore_reason=- teardown=S5_session_end power_cycle_required=1 errors=0 transport_ok=1" % (status, stop))
    lines.extend(extra)
    lines = [l for l in lines if not any(l.startswith(d) for d in drop)]
    return "\n".join("%06d %s" % (i, l) for i, l in enumerate(lines)) + "\n"


class TheCleanLog(unittest.TestCase):
    def test_a_clean_log_reads_clean(self):
        o = playread.analyse(log())
        self.assertEqual(o["problems"], [])
        self.assertTrue(o["service"]["pass"])
        self.assertTrue(o["capture"]["pass"])
        self.assertEqual(o["under"]["summary"]["after_startup"], 0)
        self.assertFalse(o["dirty"])
        self.assertIsNone(o["cartdecl"])
        for r in o["loss"]:
            self.assertTrue(r["in_band"], r)

    def test_the_loss_is_the_v28_readers_own_arithmetic(self):
        o = playread.analyse(log(loss_blocks=(4096 * 55 - 55 * 4096 // 500, 4096 * 300 - 300 * 4096 // 500)))
        self.assertAlmostEqual(o["loss"][0]["loss"], 0.002, places=4)
        o = playread.analyse(log(loss_blocks=(4096 * 55, 4096 * 300 * 98 // 100)))
        self.assertTrue(o["loss"][0]["loss"] == 0.0 and not o["loss"][0]["in_band"], "0 % is below the band too: a loss that cannot be 0 is a finding")
        self.assertFalse(o["loss"][1]["in_band"], "2 % is outside the band")


class TheUnderrunInstrument(unittest.TestCase):
    def test_startup_and_after_startup_are_apart(self):
        o = playread.analyse(log(underruns=[(2, 62), (500, 15625), (9000, 281000)]))
        s = o["under"]["summary"]
        self.assertEqual((s["startup"], s["after_startup"], s["first_after_handed"], s["total"]), (1, 2, 500, 3))
        self.assertEqual(o["problems"], [])
        text = playread.render(o)
        self.assertIn("THE FALLBACK RULE'S ONLY INPUT (Issue #142): after_startup=2", text)
        self.assertIn("does not apply the rule", text)

    def test_the_reader_never_decides_the_rule(self):
        text = playread.render(playread.analyse(log(underruns=[(700, 21875)])))
        for banned in ("RUNG DEEPER", "A2", "move to", "next build", "PASS the rule", "FAIL the rule"):
            self.assertNotIn(banned, text)

    def test_an_inconsistent_summary_is_a_problem_not_a_reading(self):
        bad = log(underruns=[(2, 62), (500, 15625)]).replace("startup=1 after_startup=1", "startup=2 after_startup=0 post_feed=0")
        o = playread.analyse(bad)
        self.assertTrue(any("ordinals do not give startup" in p for p in o["problems"]), o["problems"])
        bad2 = log(underruns=[(500, 15625)]).replace("total=1 k=64", "total=2 k=64")
        self.assertTrue(any("total" in p for p in playread.analyse(bad2)["problems"]))
        bad3 = log(underruns=[(500, 15625)], drop=("PLAYUND n=",))
        self.assertTrue(any("PLAYUND record(s)" in p for p in playread.analyse(bad3)["problems"]))

    def test_post_feed_silence_is_apart_and_never_after_startup(self):
        o = playread.analyse(log(underruns=[(300, 9375), (9000, 281250), (9001, 281281)], post_feed=(9000, 9001)))
        s = o["under"]["summary"]
        self.assertEqual((s["after_startup"], s["post_feed"], s["first_after_handed"], s["total"]), (1, 2, 300, 3))
        self.assertEqual(o["problems"], [])
        text = playread.render(o)
        self.assertIn("POST-FEED (teardown silence)", text)
        self.assertIn("after_startup=1 (post_feed", text)

    def test_the_consistency_checks_fire(self):
        base = log(underruns=[(500, 15625)])
        # k is not the registered one
        self.assertTrue(any("not the registered one" in p for p in playread.analyse(base.replace("k=64", "k=1000"))["problems"]))
        self.assertTrue(any("not the registered one" in p for p in playread.analyse(base.replace("startup_k=64", "startup_k=32"))["problems"]))
        # the phases do not sum to the session total
        self.assertTrue(any("sum to" in p for p in playread.analyse(base.replace("wrong=0 underruns=1", "wrong=0 underruns=0"))["problems"]))
        # first_after_handed disagrees with the records
        self.assertTrue(any("first_after_handed" in p for p in playread.analyse(base.replace("first_after_handed=500", "first_after_handed=501"))["problems"]))
        # an impossible ordinal 1
        one = log(underruns=[(1, 0)])
        self.assertTrue(any("handed=1" in p for p in playread.analyse(one)["problems"]))
        # ordinals that do not rise
        two = log(underruns=[(500, 15625), (499, 15700)])
        self.assertTrue(any("do not rise" in p for p in playread.analyse(two)["problems"]))
        # a clean log has none of these
        self.assertEqual(playread.analyse(base)["problems"], [])

    def test_a_missing_summary_is_a_problem(self):
        o = playread.analyse(log(drop=("PLAYUNDER",)))
        self.assertIn("no PLAYUNDER record", o["problems"])

    def test_a_dma_that_never_started_has_no_summary_and_is_no_problem(self):
        t = log(drop=("PLAYUNDER", "PLAYSTARTUP")) + "000099 PLAYSTARTUP t_dma=none k=64 reason=dma_never_started\n"
        o = playread.analyse(t)
        self.assertNotIn("no PLAYUNDER record", o["problems"])


class TheGatesThatSurviveAndTheOnesThatDoNot(unittest.TestCase):
    def test_the_service_gate_catches_a_failure_and_reads_a_store_cap_as_a_row(self):
        bad = log().replace("errors=0 transport_ok=1", "errors=1 transport_ok=1")
        self.assertFalse(playread.analyse(bad)["service"]["pass"])
        bad = log().replace("errors=0 transport_ok=1", "errors=0 transport_ok=0")
        self.assertFalse(playread.analyse(bad)["service"]["pass"])
        row = playread.analyse(log(stop="event_store_cap", status="ok_no_change_inconclusive"))
        self.assertTrue(row["store_cap_row"])
        self.assertTrue(row["service"]["pass"], "a store-cap stop is a ROW, not a failed service")
        self.assertIn("STORE-CAP ROW", playread.render(row))
        failed = playread.analyse(log(stop="failure", status="abort_inconsistent"))
        self.assertFalse(failed["service"]["pass"])

    def test_the_capture_gate_catches_a_loss(self):
        self.assertFalse(playread.analyse(log().replace("syncpe_lost=0", "syncpe_lost=3"))["capture"]["pass"])
        self.assertFalse(playread.analyse(log().replace("wrong_len=0", "wrong_len=2"))["capture"]["pass"])
        self.assertFalse(playread.analyse(log().replace("taps_failed=0", "taps_failed=1"))["capture"]["pass"])
        self.assertFalse(playread.analyse(log().replace("overflow=0 min", "overflow=4 min"))["capture"]["pass"])
        self.assertFalse(playread.analyse(log(drop=("V28TAPS",)))["capture"]["pass"])

    def test_the_void_gates_are_named_and_a_research_record_is_unexpected(self):
        text = playread.render(playread.analyse(log()))
        self.assertIn("VOID IN A PLAY LOG", text)
        for g in ("V28_NULLM", "V28_3BM", "V28_SWEEP"):
            self.assertIn(g, text)
        self.assertIn("NOT reported as passed", text)
        o = playread.analyse(log(extra=("V28_3BM n=0 ring0=1 min_ring_late=1 samples_late=1 mean_ring=1 mean_cs=1 chunk_starts=1",)))
        self.assertEqual(o["unexpected"], ["V28_3BM"])
        self.assertIn("UNEXPECTED research record", playread.render(o))

    def test_a_dirty_build_is_not_a_candidate_and_a_foreign_log_is_refused(self):
        o = playread.analyse(log(commit="abc1234-dirty"))
        self.assertTrue(o["dirty"])
        self.assertIn("NOT A CANDIDATE", playread.render(o))
        foreign = log().replace("test=GBP-PLAY-002", "test=GBP-AUDIO-V28")
        self.assertTrue(any("not a play-image log" in p for p in playread.analyse(foreign)["problems"]))

    def test_a_setting_other_than_t256_a1_is_noted(self):
        o = playread.analyse(log(target="8192"))
        self.assertTrue(any("NOT the T256 A1 setting" in n for n in o["notes"]))

    def test_the_declaration_is_printed_as_a_declaration(self):
        line = 'CARTDECL idx=2 title="Kingdom Hearts: Chain of Memories (JP)" form=ORIGINAL mode=GBA entered=pad_selection_after_session'
        o = playread.analyse(log(extra=(line,)))
        self.assertEqual(o["cartdecl"], line.split(" ", 1)[1])
        self.assertIn("an OPERATOR DECLARATION, not a machine reading", playread.render(o))
        self.assertIn("UNDECLARED", playread.render(playread.analyse(log())))
        two = playread.analyse(log(extra=(line, line)))
        self.assertTrue(any("2 CARTDECL lines" in p for p in two["problems"]))


class TheTapGateIsPerPhase(unittest.TestCase):
    """Issue #156 (HARDWARE_TESTS.md V31.11). The gate P6 / G4 always read is per phase (V28PHC): taps == blocks_in, failed 0, wrong 0 in EVERY phase. The whole-session V28TAPS taps
    exceeds blocks_in by the pre-origin window in every healthy log (taps count from the first tap, blocks_in from the press origin), so that difference is printed, never judged.
    The positive control HAS the window (log() default, RUN 61's 26 266): a control without it agreed with the bug the reader had."""

    def test_a_healthy_log_with_a_pre_origin_window_passes(self):
        text = log()
        o = playread.analyse(text)
        self.assertEqual(o["pre_origin"]["diff"], PRE_ORIGIN, "the control carries the pre-origin window")
        self.assertGreater(o["pre_origin"]["taps"], o["pre_origin"]["blocks_in"])
        self.assertTrue(o["capture"]["pass"], o["capture"]["problems"])
        self.assertEqual(o["capture"]["problems"], [])
        self.assertEqual([(r["p"], r["taps"] == r["blocks_in"], r["failed"], r["wrong"]) for r in o["phase_capture"]], [("0", True, 0, 0), ("1", True, 0, 0)])

    def test_the_whole_session_difference_is_information_never_a_verdict(self):
        for pre in (0, 1, 26266, 27567, 49495, 10 ** 7):
            o = playread.analyse(log(pre_origin=pre))
            self.assertTrue(o["capture"]["pass"], "pre_origin=%d: %s" % (pre, o["capture"]["problems"]))
            self.assertEqual(o["pre_origin"]["diff"], pre)
        text = playread.render(playread.analyse(log()))
        self.assertIn("INFORMATION, not a verdict: whole-session V28TAPS taps=%d blocks_in=%d, taps - blocks_in = %d" % (
            4096 * 355 - 451 - 2457 + 1 + PRE_ORIGIN, 4096 * 355 - 451 - 2457 + 1, PRE_ORIGIN), text)
        self.assertIn("pre-origin window", text)
        self.assertIn("CAPTURE: PASS", text)
        self.assertIn("tap gate, phase 0 (V28PHC): taps=", text)

    def test_the_old_reader_failed_the_healthy_log(self):
        """THE REPRODUCTION (Issue #156, run on the old code first): the reader as it stood at 18f9eb8 -- frozen by test_e5_breadth_run61_ingest.py -- compared the whole-session counters
        and read this very log as a capture failure, while it reads clean with pre_origin=0, the shape the earlier tests synthesised. Pinned here so the repair's premise stays checkable."""
        import subprocess
        import tempfile
        import guards
        base = "18f9eb8452a4ce818e24502a612125b44264e753"
        if not guards.base_available(base):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % base)
        with tempfile.TemporaryDirectory() as tmp:
            arch = subprocess.run(["git", "archive", base, "tools"], cwd=ROOT, capture_output=True, check=True).stdout
            subprocess.run(["tar", "-x", "-C", tmp], input=arch, check=True)
            reader = os.path.join(tmp, "tools", "playread.py")
            for name, text, expect in (("realistic", log(), "CAPTURE: FAIL\n  - V28TAPS taps=%d != blocks_in=%d\n" % (4096 * 355 - 451 - 2457 + 1 + PRE_ORIGIN, 4096 * 355 - 451 - 2457 + 1)),
                                       ("no pre-origin window", log(pre_origin=0), "CAPTURE: PASS\n")):
                path = os.path.join(tmp, name.replace(" ", "_") + ".log")
                with open(path, "w") as f:
                    f.write(text)
                out = subprocess.run([sys.executable, reader, path], capture_output=True, text=True)
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertIn(expect, out.stdout, name)
            # and the repaired reader reads both as a pass
            self.assertTrue(playread.analyse(log())["capture"]["pass"])
            self.assertTrue(playread.analyse(log(pre_origin=0))["capture"]["pass"])

    def test_a_per_phase_mismatch_fails_in_either_phase_and_either_direction(self):
        loss = (4096 * 55 - 451, 4096 * 300 - 2457)
        for phase_taps, expect in (((loss[0] - 1, loss[1]), "V28PHC p=0 taps=%d != blocks_in=%d" % (loss[0] - 1, loss[0])),
                                   ((loss[0], loss[1] + 1), "V28PHC p=1 taps=%d != blocks_in=%d" % (loss[1] + 1, loss[1])),
                                   ((loss[0] + 5, loss[1] - 5), "V28PHC p=0 taps=%d != blocks_in=%d" % (loss[0] + 5, loss[0]))):
            o = playread.analyse(log(phase_taps=phase_taps))
            self.assertFalse(o["capture"]["pass"], phase_taps)
            self.assertIn(expect, o["capture"]["problems"])
            self.assertIn("CAPTURE: FAIL", playread.render(o))
        # both phases wrong: both are named
        o = playread.analyse(log(phase_taps=(loss[0] - 1, loss[1] - 1)))
        self.assertEqual(sum(1 for p in o["capture"]["problems"] if p.startswith("V28PHC p=")), 2)

    def test_a_nonzero_failed_or_wrong_in_a_phase_fails(self):
        for kw, expect in (({"phase_failed": (1, 0)}, "V28PHC p=0 failed=1 (nonzero)"), ({"phase_failed": (0, 7)}, "V28PHC p=1 failed=7 (nonzero)"),
                           ({"phase_wrong": (2, 0)}, "V28PHC p=0 wrong=2 (nonzero)"), ({"phase_wrong": (0, 3)}, "V28PHC p=1 wrong=3 (nonzero)")):
            o = playread.analyse(log(**kw))
            self.assertFalse(o["capture"]["pass"], kw)
            self.assertEqual(o["capture"]["problems"], [expect])

    def test_the_gate_cannot_pass_by_having_nothing_to_read(self):
        """A per-phase gate that reads no phase passes vacuously: no V28PHC at all, one phase's record missing, is a FAIL, never a pass. (A `V28PHC` with a missing or non-numeric field never reads as a pass: the reader's own per-phase loop (`int()` in `analyse()`) raises `KeyError`/`ValueError` before any verdict is printed; `tools/v28verdict.py`'s `phase_loss`, called after it and unchanged, would also raise when that phase's `V28PHD` is present and skips the record when it is absent. A malformed record is a crash of the reader, not a FAIL line; this repair does not change that.)"""
        o = playread.analyse(log(drop=("V28PHC",)))
        self.assertFalse(o["capture"]["pass"])
        self.assertTrue(any("no V28PHC record" in p for p in o["capture"]["problems"]), o["capture"]["problems"])
        one = "\n".join(l for l in log().split("\n") if " V28PHC p=1 " not in l)
        o = playread.analyse(one)
        self.assertFalse(o["capture"]["pass"])
        self.assertTrue(any("phase 1 has a SYNCPH record and no V28PHC" in p for p in o["capture"]["problems"]), o["capture"]["problems"])

    def test_the_whole_session_checks_that_stay(self):
        """taps_failed and wrong_len (V28TAPS), V28C2's lost / syncpe_lost / lines_lost and V28CORR's overflow still decide, alongside the per-phase tap gate."""
        for old, new in (("taps_failed=0", "taps_failed=9"), ("wrong_len=0", "wrong_len=9"), (" lost=0 blocks_in", " lost=9 blocks_in"), ("syncpe_lost=0", "syncpe_lost=9"),
                         ("lines_lost=0", "lines_lost=9"), ("overflow=0 min", "overflow=9 min")):
            o = playread.analyse(log().replace(old, new, 1))
            self.assertFalse(o["capture"]["pass"], old)
            self.assertTrue(o["capture"]["problems"], old)

    def test_a_malformed_v28phc_is_a_crash_of_the_reader_not_a_fail_line(self):
        """Stated, not endorsed (the central session's decision on Issue #156): a V28PHC whose `taps` is non-numeric, or has no `taps` field, makes analyse() raise before any verdict.
        It never reads as a pass; turning it into a FAIL line would be another checkpoint."""
        text = log()
        self.assertIn(" V28PHC p=0 ended=1 ", text)
        bad = text.replace("taps=%d failed=0 wrong=0" % (4096 * 55 - 451), "taps=xx failed=0 wrong=0", 1)
        self.assertNotEqual(bad, text)
        with self.assertRaises(ValueError):
            playread.analyse(bad)
        missing = text.replace(" taps=%d failed=0 wrong=0" % (4096 * 55 - 451), " failed=0 wrong=0", 1)
        self.assertNotEqual(missing, text)
        with self.assertRaises(KeyError):
            playread.analyse(missing)


class TheRepairedReaderOnTheArchivedPlayLogs(unittest.TestCase):
    """The repaired reader's reading of RUN 61 / 62 / 63 (the archive under captures/local, hash-pinned by test_e5_breadth_run61_ingest.py's RUNS), labelled as that: the repaired
    reader's reading, not a re-judgement of what the frozen reader printed (which that test keeps byte for byte)."""

    def test_the_three_logs_read_capture_pass_with_their_pre_origin_windows(self):
        import hashlib
        from test_e5_breadth_run61_ingest import RUNS
        local = os.path.join(ROOT, "captures", "local")
        paths = {r: os.path.join(local, f) for r, (f, _h, _raw) in RUNS.items()}
        if not all(os.path.isfile(p) for p in paths.values()):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        window = {61: 26266, 62: 27567, 63: 25994}
        phases = {61: (245321, 1226658), 62: (245329, 1226652), 63: (245333, 1226642)}
        for r, p in paths.items():
            with open(p, "rb") as f:
                raw = f.read()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), RUNS[r][1], "RUN %d: the archive is not the recorded one (a defect, never a skip)" % r)
            o = playread.analyse(raw.decode("utf-8", errors="replace"))
            self.assertTrue(o["capture"]["pass"], (r, o["capture"]["problems"]))
            self.assertEqual(o["pre_origin"]["diff"], window[r], r)
            self.assertEqual([(x["taps"], x["blocks_in"], x["failed"], x["wrong"]) for x in o["phase_capture"]],
                             [(phases[r][0], phases[r][0], 0, 0), (phases[r][1], phases[r][1], 0, 0)], r)


class TheStartupProfileAndPolicyAAreNotReportedAsSurvivingRecords(unittest.TestCase):
    """Issue #157 (HARDWARE_TESTS.md V31.12). V31.6 / V31.8 and the reader listed 'the startup profile' and 'Policy A' among the records the vehicle keeps; its log carries no record of
    either. The reader prints them on a line of their own, naming the reason; the SURVIVE line keeps the KEY and the CONTROL records. An informational line: it decides nothing, and every
    gate's reading of a synthetic log is what it was."""

    NAMES = ("the startup profile", "Policy A")

    def lines(self, text):
        return text.split("\n")

    def test_the_survive_line_no_longer_names_the_two_gates_and_the_new_line_does(self):
        text = playread.render(playread.analyse(log()))
        survive = [l for l in self.lines(text) if l.startswith("SURVIVE, not recomputed here")]
        self.assertEqual(len(survive), 1)
        for n in self.NAMES:
            self.assertNotIn(n, survive[0])
        self.assertIn("the KEY record", survive[0])
        self.assertIn("the CONTROL record (orig=92", survive[0])
        norec = [l for l in self.lines(text) if l.startswith("NO RECORD IN THIS IMAGE'S LOG")]
        self.assertEqual(len(norec), 1)
        for n in self.NAMES:
            self.assertIn(n, norec[0])
        for token in ("HARDWARE_TESTS.md V31.12", "NOT reported as passed", "STARTUP / STARTUPT / STARTUPV / STREAMINV", "OGBPDISP2"):
            self.assertIn(token, norec[0])
        self.assertEqual([l for l in self.lines(text) if "the startup profile" in l or "Policy A" in l], norec, "the two names appear on that one line and nowhere else")

    def test_the_line_is_the_same_whatever_the_log_says_and_changes_no_gate(self):
        """Informational: a clean log, a log with an after-start-up underrun and a -dirty one print the same line; the gate fields of analyse() carry nothing of it."""
        want = [l for l in self.lines(playread.render(playread.analyse(log()))) if l.startswith("NO RECORD IN THIS IMAGE'S LOG")]
        for text in (log(underruns=[(500, 15625)]), log(commit="abc1234-dirty"), log(loss_blocks=(4096 * 55, 4096 * 300 * 98 // 100))):
            got = [l for l in self.lines(playread.render(playread.analyse(text))) if l.startswith("NO RECORD IN THIS IMAGE'S LOG")]
            self.assertEqual(got, want)
        o = playread.analyse(log())
        self.assertEqual(o["problems"], [])
        for key, val in o.items():
            self.assertNotIn("Policy A", repr(val), key)
            self.assertNotIn("startup profile", repr(val), key)

    def test_the_constants_say_it(self):
        self.assertEqual(playread.NO_RECORD_IN_THIS_IMAGE_LOG, self.NAMES)
        for n in self.NAMES:
            self.assertNotIn(n, playread.SURVIVING_NOT_RECOMPUTED)
        self.assertEqual(len(playread.SURVIVING_NOT_RECOMPUTED), 2)

    def test_the_whole_line_order_is_survive_then_the_new_line_then_void(self):
        text = playread.render(playread.analyse(log()))
        i, j, k = (text.index(x) for x in ("SURVIVE, not recomputed", "NO RECORD IN THIS IMAGE'S LOG", "VOID IN A PLAY LOG"))
        self.assertLess(i, j)
        self.assertLess(j, k)



# ---------------------------------------------------------------------------------------------------------------- Issue #158: vehicle-0002's startup block
import hashlib  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402

sys.path.insert(0, HERE)
import guards  # noqa: E402

UNIT_TEST = os.path.join(ROOT, "tests", "unit", "test_gbp_startrec.c")
LOCAL = os.path.join(ROOT, "captures", "local")
STARTREC_BASE = "bc97ba36713779dcbe0310902d195f019d6839ff"     # origin/main when #158 was resumed: the reader as it stood before the vehicle-0002 block
VEHICLE1_LOGS = {61: ("GBP-PLAY-002_vehicle-0001-run61.log", "9a8120351db9e129620d53708f190ba3acfdfd0cd23179452f09d775f67ce0cd"),
                 62: ("GBP-PLAY-002_vehicle-0001-run62.log", "56575eb5e1573daa25f63574193fc7953c93debe6cde35e3bff7410fb9594b33"),
                 63: ("GBP-PLAY-002_vehicle-0001-run63.log", "ddc8381e144072ede3d477c3fadcc262aba4af590594ddf4b1ebea9a212267f2")}
RUN17_LOG = ("GBP-VIDEO-004_stream-0015-run17.log", "85d8963752cb9fed95d9842d0109c56ce87e2951d94cca0ef666cb646184dc83")   # HARDWARE_TESTS.md:23416


def unit_expected():
    """The five lines the C unit test expects the writer to produce: ONE source of truth for writer and reader."""
    with open(UNIT_TEST, encoding="utf-8") as f:
        src = f.read()
    got = dict(re.findall(r'static const char \*const EXPECT_(\w+) = "([^"]*)";', src))
    return {"STARTUP": got["STARTUP"], "STARTUPT": got["STARTUPT"], "STARTUPV": got["STARTUPV"], "STREAMINV": got["STREAMINV"], "STREAMSELFTEST": got["STREAMSELFTEST"]}


def v2log(edit=None, drop_tags=(), ident=("gbp-play-gba2", "vehicle-0002"), **kw):
    """the synthetic play log above, as a vehicle-0002 log: IDENT names the image, and the five records are the unit test's lines (`edit`: {tag: (old, new)})"""
    recs = unit_expected()
    for tag, (old, new) in (edit or {}).items():
        assert old in recs[tag], (tag, old)
        recs[tag] = recs[tag].replace(old, new)
    lines = tuple(recs[t] for t in playread.STARTREC_TAGS if t not in drop_tags)
    text = log(extra=lines, **kw)
    return text.replace("app=gbp-play-gba build=vehicle-0001", "app=%s build=%s" % ident)


def rows(text):
    o = playread.analyse(text)
    return o, dict((name, status) for name, status, _src in o["startrec"]["rows"]) if o["startrec"] else None


def sha256(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class TheVehicle2StartupBlock(unittest.TestCase):
    """Issue #158: the image is decided by IDENT build= (cross-checked with app=), never by record presence; vehicle-0002's block prints the V5.53.2 checklist rows MET / NOT MET / MISSING;
    no session verdict. Each control is judged per case."""

    ROWS = ("mode normal", "visible synthetic = 0", "pre-handler wait = 0", "black framebuffer initialisation", "first real hand-off observed",
            "first real hand-off < 400 ms from CONTROL", "Policy A invariants clean")

    def test_the_unit_tests_lines_read_every_row_met(self):
        text = v2log()
        o, r = rows(text)
        self.assertEqual(o["problems"], [])
        self.assertEqual(o["image"], "vehicle-0002")
        for name in self.ROWS:
            self.assertEqual(r[name], "MET", name)
        self.assertEqual(r["no transport failure"], "SEE SERVICE/TRANSPORT")
        out = playread.render(o)
        self.assertNotIn("NO RECORD IN THIS IMAGE'S LOG", out, "the vehicle-0001 line is not printed for a vehicle-0002 log")
        self.assertIn("Policy A's drops / supersessions / reorder / depth / latency: NO RECORD (no OGBPDISP2; not built)", out)
        self.assertNotIn("Policy A passed", out)
        self.assertIn("165.336 ms, information only", out)
        self.assertIn("STREAMSELFTEST (information): ok=1 converted=1 released=1 own_presents=0 own_repeats=0 sci_clean=1", out)
        self.assertIn("STREAMINV consistent_at_end=1 (information)", out)
        block = out[out.index("STARTUP PROFILE (vehicle-0002"):out.index("VOID IN A PLAY LOG")]
        self.assertNotRegex(block, r"\b(PASS|FAIL)\b", "rows, never a session verdict")

    def test_one_negative_per_row(self):
        cases = [
            ("mode normal", {"STARTUP": ("mode=normal", "mode=diagnostic")}),
            ("visible synthetic = 0", {"STARTUP": ("normal_clean=1", "normal_clean=0")}),
            ("visible synthetic = 0", {"STARTUP": ("presented_synthetic=0", "presented_synthetic=1")}),
            ("pre-handler wait = 0", {"STARTUP": ("prehandler_wait_ms=0", "prehandler_wait_ms=5000")}),
            ("black framebuffer initialisation", {"STARTUP": ("clear_fb=1", "clear_fb=0")}),
            ("first real hand-off observed", {"STARTUPV": ("have_first=1", "have_first=0")}),
            ("first real hand-off < 400 ms from CONTROL", {"STARTUPV": ("ticks_control_to_first_handoff=6696114", "ticks_control_to_first_handoff=16200000")}),
            ("Policy A invariants clean", {"STREAMINV": ("failures=0 main=0/186880", "failures=1 main=1/186880")}),
            ("Policy A invariants clean", {"STREAMINV": ("checks=189258 failures=0 main=0/186880 isr=0/2378", "checks=0 failures=0 main=0/0 isr=0/0")}),
            ("Policy A invariants clean", {"STREAMINV": ("isr=0/2378", "isr=0/2377")}),
            ("Policy A invariants clean", {"STREAMINV": ("main=0/186880", "main=1/186880")}),
        ]
        for name, edit in cases:
            o, r = rows(v2log(edit=edit))
            self.assertEqual(r[name], "NOT MET", (name, edit))
            for other in self.ROWS:
                if other != name and not (name == "first real hand-off observed" and other == "first real hand-off < 400 ms from CONTROL"):
                    self.assertEqual(r[other], "MET", (other, edit))

    def test_no_first_hand_off_fails_the_400_ms_row_too_although_its_ticks_would_be_under_any_bound(self):
        o, r = rows(v2log(edit={"STARTUPV": ("have_first=1", "have_first=0")}))
        self.assertEqual(r["first real hand-off < 400 ms from CONTROL"], "NOT MET")
        o, r = rows(v2log(edit={"STARTUPV": ("have_first=1 first_frame_index=3 t_take=c8a1b2 t_convert_done=c9b2c3 t_decision=cac3d4 ticks_control_to_first_handoff=6696114",
                                             "have_first=0 first_frame_index=0 t_take=0 t_convert_done=0 t_decision=0 ticks_control_to_first_handoff=0")}))
        self.assertEqual(r["first real hand-off < 400 ms from CONTROL"], "NOT MET", "the writer's own have_first=0 line: ticks 0, which a bare comparison would pass")

    def test_the_400_ms_bound_is_strict_and_in_integers(self):
        _o, r = rows(v2log(edit={"STARTUPV": ("=6696114", "=16199999")}))
        self.assertEqual(r["first real hand-off < 400 ms from CONTROL"], "MET")
        _o, r = rows(v2log(edit={"STARTUPV": ("=6696114", "=16200000")}))
        self.assertEqual(r["first real hand-off < 400 ms from CONTROL"], "NOT MET", "exactly 400 ms at 40 500 000 Hz: the strict form of V5.53.2 / V5.57.8")
        self.assertEqual(playread.FIRST_HANDOFF_BOUND_MS * 40500000 // 1000, 16200000)

    def test_each_record_missing_reads_missing(self):
        depends = {"STARTUP": ("mode normal", "visible synthetic = 0", "pre-handler wait = 0", "black framebuffer initialisation"),
                   "STARTUPT": ("first real hand-off < 400 ms from CONTROL",),
                   "STARTUPV": ("first real hand-off observed", "first real hand-off < 400 ms from CONTROL"),
                   "STREAMINV": ("Policy A invariants clean",), "STREAMSELFTEST": ()}
        for tag, rowsdep in depends.items():
            text = v2log(drop_tags=(tag,))
            o, r = rows(text)
            out = playread.render(o)
            self.assertIn("  %s record: MISSING (NOT passed)" % tag, out, tag)
            for name in self.ROWS:
                self.assertEqual(r[name], "MISSING" if name in rowsdep else "MET", (tag, name))
            if tag == "STREAMSELFTEST":
                self.assertIn("STREAMSELFTEST: MISSING (NOT passed)", out)
        o, r = rows(v2log(drop_tags=playread.STARTREC_TAGS))
        self.assertEqual(set(r[n] for n in self.ROWS), {"MISSING"}, "a vehicle-0002 log that lost every record is MISSING throughout, never the vehicle-0001 line")
        self.assertNotIn("NO RECORD IN THIS IMAGE'S LOG", playread.render(o))

    def test_a_vehicle_0001_log_cannot_carry_the_records(self):
        recs = unit_expected()
        for tag in playread.STARTREC_TAGS:
            o = playread.analyse(log(extra=(recs[tag],)))
            self.assertIn("a vehicle-0001 log cannot carry %s" % tag, o["problems"])
            out = playread.render(o)
            self.assertIn("NO RECORD IN THIS IMAGE'S LOG", out)
            self.assertNotIn("STARTUP PROFILE (vehicle-0002", out)

    def test_an_unknown_build_id_is_refused_and_neither_block_is_printed(self):
        o = playread.analyse(v2log(ident=("gbp-play-gba2", "vehicle-0003")))
        self.assertIn("unknown build id vehicle-0003: no record expectation", o["problems"])
        out = playread.render(o)
        self.assertNotIn("NO RECORD IN THIS IMAGE'S LOG", out)
        self.assertNotIn("STARTUP PROFILE", out)

    def test_the_app_name_is_cross_checked(self):
        o = playread.analyse(v2log(ident=("gbp-play-gba", "vehicle-0002")))
        self.assertIn("IDENT app=gbp-play-gba does not match build=vehicle-0002 (expected app=gbp-play-gba2)", o["problems"])
        o = playread.analyse(log().replace("app=gbp-play-gba build=", "app=gbp-play-gba2 build="))
        self.assertIn("IDENT app=gbp-play-gba2 does not match build=vehicle-0001 (expected app=gbp-play-gba)", o["problems"])

    def test_a_duplicated_record_is_a_problem(self):
        recs = unit_expected()
        o = playread.analyse(v2log().replace("\n", "\n", 1) + "999999 %s\n" % recs["STARTUPV"])
        self.assertIn("2 STARTUPV records (one expected)", o["problems"])


class TheParserOnRealData(unittest.TestCase):
    """RUN 17 (GBP-VIDEO-004, stream-0015): its STARTUPV has the stream probe's t_drawdone shape, so this also shows the parser reads by key."""

    def test_run17(self):
        p = os.path.join(LOCAL, RUN17_LOG[0])
        if not os.path.isfile(p):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        self.assertEqual(sha256(p), RUN17_LOG[1], "the archived RUN 17 log is not the recorded one (a defect, never a skip)")
        with open(p, encoding="utf-8", errors="replace") as f:
            recs = playread.records(f.read())
        b = playread.startup_block(recs)
        r = dict((n, (s, src)) for n, s, src in b["rows"])
        self.assertEqual(b["missing"], [])
        self.assertIn("ticks_control_to_first_handoff=6696114", r["first real hand-off < 400 ms from CONTROL"][1])   # HARDWARE_TESTS.md:23470
        self.assertEqual(r["first real hand-off < 400 ms from CONTROL"][0], "MET")
        self.assertIn("STREAMINV checks=189258 failures=0 ", r["Policy A invariants clean"][1])                        # HARDWARE_TESTS.md:24706
        self.assertEqual(r["Policy A invariants clean"][0], "MET")
        for name in TheVehicle2StartupBlock.ROWS:
            self.assertEqual(r[name][0], "MET", name)


class TheVehicle1ReadingIsByteIdentical(unittest.TestCase):
    """Issue #158: for the three archived vehicle-0001 logs, the reader's FULL output is the base reader's, byte for byte (the base extracted with git archive)."""

    def test_full_output_identity(self):
        paths = dict((r, os.path.join(LOCAL, f)) for r, (f, _h) in VEHICLE1_LOGS.items())
        if not all(os.path.isfile(p) for p in paths.values()):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        for r, p in paths.items():
            self.assertEqual(sha256(p), VEHICLE1_LOGS[r][1], "RUN %d's archive is not the recorded one (a defect, never a skip)" % r)
        if not guards.base_available(STARTREC_BASE):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % STARTREC_BASE)
        with tempfile.TemporaryDirectory() as tmp:
            arch = subprocess.run(["git", "archive", STARTREC_BASE, "tools"], cwd=ROOT, capture_output=True, check=True).stdout
            subprocess.run(["tar", "-x", "-C", tmp], input=arch, check=True)
            for r, p in sorted(paths.items()):
                old = subprocess.run([sys.executable, os.path.join(tmp, "tools", "playread.py"), p], capture_output=True)
                new = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "playread.py"), p], capture_output=True)
                self.assertEqual(old.returncode, 0, old.stderr)
                self.assertEqual(new.returncode, 0, new.stderr)
                self.assertEqual(new.stdout, old.stdout, "RUN %d: the reader's output on a vehicle-0001 log moved" % r)
                self.assertIn(b"NO RECORD IN THIS IMAGE'S LOG", new.stdout)


if __name__ == "__main__":
    unittest.main()
