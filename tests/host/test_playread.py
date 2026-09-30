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


def log(commit="abc1234", underruns=None, post_feed=(), stop="session_end", status="ok_session_ended", extra=(), drop=(), loss_blocks=(4096 * 55 - 451, 4096 * 300 - 2457), target="4096",
        startup_count=None):
    """A play log's records, in the order main.c writes them. `underruns` is a list of (ordinal, ms) for the PLAYUND records."""
    und = underruns if underruns is not None else []
    k = 64
    pf_set = set(post_feed)                 # ordinals of `underruns` that are post-feed (teardown silence)
    startup = sum(1 for o, _ in und if o <= k) if startup_count is None else startup_count
    n_pf = sum(1 for o, _ in und if o in pf_set and o > k)
    after = len(und) - startup - n_pf
    first_after = next((o for o, _ in und if o > k and o not in pf_set), None)
    # phases: p0 55 s of capture, p1 300 s
    secs = (55, 300)
    t0 = 1_000_000_000
    lines = [
        "IDENT test=GBP-PLAY-002 app=gbp-play-gba build=vehicle-0001 commit=%s libogc=libogc2 r2442.094b250" % commit,
        "PLAYCFG plan=play_gba navigate_s=60 play_bound_s=300 session_cap_s=420 wall_s=485 target=%s ahead=1 step=64 startup_k=64 cold_start=set_target mode=GBA" % target,
        "ENVSTORE frames=29100/16384 events=38315/4096 corr_cap=18915 fault=- ok=1",
        "ENVMEM bss_end=80290000 arena1_lo=802a0000 arena1_hi=81700000 arena1_free=20000000 frames_bytes=5587200 events_bytes=2452160 corr_bytes=37830 log_bytes=2097152 xfb=3x614400",
        "KEYLOG events=17 emitted=17 lost=0 truncated=0 reserve=1280",
        "V28C underruns=%d overflow=0 silences=%d mute_handed=0 dup=10 drop=10 produced=1000 handed=1000 ring_gated=0" % (len(und), len(und)),
        "V28C2 discarded=0 starved_steps=5 lost=0 blocks_in=%d ring_discarded=0 dropped_front=0 cs=0 acted=0 syncpe_lost=0 lines_lost=0" % sum(loss_blocks),
        "V28CORR n=1000 overflow=0 min=0 max=3 mean_x100=200 cap=18915",
        "V28TAPS taps=%d taps_failed=0 wrong_len=0 blocks_in=%d gap_max=1 gap_at=1" % (sum(loss_blocks), sum(loss_blocks)),
    ]
    t = t0
    for p in (0, 1):
        t1 = t + secs[p] * TB
        lines.append("V28PHC p=%d ended=1 t0=%x t1=%x blocks_in=%d taps=%d failed=0 wrong=0 underruns=%d" % (p, t, t1, loss_blocks[p], loss_blocks[p],
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

    def test_the_capture_gate_catches_a_loss_or_a_short_tap(self):
        self.assertFalse(playread.analyse(log().replace("syncpe_lost=0", "syncpe_lost=3"))["capture"]["pass"])
        self.assertFalse(playread.analyse(log().replace("wrong_len=0", "wrong_len=2"))["capture"]["pass"])
        self.assertFalse(playread.analyse(log().replace("overflow=0 min", "overflow=4 min"))["capture"]["pass"])
        self.assertFalse(playread.analyse(log(drop=("V28TAPS",)))["capture"]["pass"])
        n = 4096 * 55 - 451 + 4096 * 300 - 2457
        t = log().replace("V28TAPS taps=%d" % n, "V28TAPS taps=%d" % (n - 1))
        self.assertFalse(playread.analyse(t)["capture"]["pass"], "taps != blocks_in")

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


if __name__ == "__main__":
    unittest.main()
