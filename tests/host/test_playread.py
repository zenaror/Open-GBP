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


if __name__ == "__main__":
    unittest.main()
