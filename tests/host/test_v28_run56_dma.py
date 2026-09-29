"""tests/host/test_v28_run56_dma.py -- GitHub Issue #139: the AI DMA hand-off semantics READ at every callback's entry (RUN 56's image), as WRITTEN in main.c, and the reader
that applies the pre-registered readings (HARDWARE_TESTS.md V28.23)."""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import test_v28_diag_loss_wiring as W  # noqa: E402
import v28latency as V  # noqa: E402
import v28verdict  # noqa: E402

MAIN = W.MAIN


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class TheCallbackOnlyReads(unittest.TestCase):
    def cb(self):
        return W.function_body(W.code(read(MAIN)), "live_dma_cb")

    def test_the_two_reads_come_first_and_the_third_after_the_init_and_the_note_last(self):
        b = self.cb()
        order = [b.index(x) for x in ("AUDIO_GetDMAStartAddr()", "AUDIO_GetDMABytesLeft()", "gbp_aplay2_irq_handoff(&ap2, t)",
                                      "AUDIO_InitDMA((u32)(size_t)c, GBP_APLAY2_CHUNK_BYTES)",
                                      "gbp_v28_dma_note(&v28_dma, dma_addr, dma_left, t, c, (uint32_t)AUDIO_GetDMAStartAddr())")]
        self.assertEqual(order, sorted(order), "the note (and its third read) come after the init: the init is delayed only by the two entry reads")
        self.assertEqual(len(re.findall(r"AUDIO_\w+\(", b)), 4, "three reads (two at the entry, one after the init) and the init the callback always made")
        self.assertEqual(len(re.findall(r"AUDIO_Get\w+\(", b)), 3)

    def test_the_callbacks_behaviour_is_what_it_was(self):
        b = self.cb()
        self.assertIn("const uint8_t *c = gbp_aplay2_irq_handoff(&ap2, t);", b)
        self.assertIn("AUDIO_InitDMA((u32)(size_t)c, GBP_APLAY2_CHUNK_BYTES);", b)
        self.assertEqual(len(re.findall(r"AUDIO_(?:Start|Stop|Set|Register|Init)\w*\(", b)), 1, "no register is written beyond the init it always did")

    def test_the_module_never_touches_the_device(self):
        for f in ("gbp_v28_dma.c", "gbp_v28_dma.h"):
            src = W.code(read(os.path.join(ROOT, "src", "audio", f)))
            self.assertNotRegex(src, r"\bAUDIO_|_dspReg|\bgettime\b|printf|malloc", f)

    def test_the_seed_is_the_first_chunk_before_the_dma_starts(self):
        src = W.code(read(MAIN))
        i = src.index("first = gbp_aplay2_irq_handoff(&ap2, now);")
        blk = src[i:i + 500]
        self.assertLess(blk.index("gbp_v28_dma_seed(&v28_dma, first);"), blk.index("AUDIO_InitDMA((u32)(size_t)first"))
        self.assertLess(blk.index("AUDIO_InitDMA((u32)(size_t)first"), blk.index("AUDIO_StartDMA();"))

    def test_the_state_is_initialised_before_the_first_callback_can_fire(self):
        src = W.code(read(MAIN))
        i = src.index("gbp_v28_dma_init(&v28_dma);")
        self.assertLess(i, src.index("cfg.audio_tap = live_tap;"))
        self.assertLess(i, src.index("AUDIO_RegisterDMACallback(live_dma_cb);"), "the callback is registered after the state exists")
        self.assertLess(i, src.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);"), "and the service loop, which starts the DMA, runs after it")

    def test_the_records_are_printed_at_teardown_in_the_sd_log_only(self):
        src = read(MAIN)
        self.assertIn('"V28DMA n=%lu prev1=%lu prev2=%lu none=%lu same12=%lu left_min=%lu left_max=%lu left_mean=%lu bins=%lu,%lu,%lu,%lu,%lu,%lu"', src)
        self.assertIn('"V28DMAP new=%lu kept=%lu amb=%lu other=%lu"', src)
        self.assertIn('"V28DMAR i=%lu addr=%lx left=%lu ret1=%lx ret2=%lx dt=%lu"', src)
        self.assertNotRegex(src, r"(?<![\w])(?:printf|gecko_puts)\([^;]*V28DMA")
        widths = {"lu": 10, "llu": 20, "llx": 16, "lx": 8, "u": 3, "s": 7}
        for fmt in ("V28DMA n=%lu prev1=%lu prev2=%lu none=%lu same12=%lu left_min=%lu left_max=%lu left_mean=%lu bins=%lu,%lu,%lu,%lu,%lu,%lu",
                    "V28DMAP new=%lu kept=%lu amb=%lu other=%lu",
                    "V28DMAR i=%lu addr=%lx left=%lu ret1=%lx ret2=%lx dt=%lu"):
            n = 7 + len(re.sub(r"%(?:llu|llx|lu|lx|u|s)", "", fmt)) + sum(widths[t] for t in re.findall(r"%(llu|llx|lu|lx|u|s)", fmt))
            self.assertLess(n, 250, fmt[:10])


def dma_line(n=1000, prev1=None, prev2=0, none=0, same12=0, left_min=3950, left_max=3990, left_mean=3970, bins=None, post=None):
    prev1 = n - 1 - prev2 - none - same12 if prev1 is None else prev1
    bins = bins or (0, 0, 0, 0, n, 0)
    return ("000700 V28DMA n=%d prev1=%d prev2=%d none=%d same12=%d left_min=%d left_max=%d left_mean=%d bins=%s"
            % (n, prev1, prev2, none, same12, left_min, left_max, left_mean, ",".join(str(b) for b in bins))
            + ("" if post is None else "\n000700 V28DMAP new=%d kept=%d amb=%d other=%d" % tuple(post)))


class TheReadings(unittest.TestCase):
    def test_r1_the_assumed_semantics(self):
        r = V.dma_semantics(dma_line())
        self.assertEqual((r["reading"], r["offset_ms"]), ("R1", 0.0))

    def test_r1_is_proof_only_when_the_register_keeps_the_active_blocks_address(self):
        wt = V.dma_semantics(dma_line(post=(999, 0, 1, 0)))
        self.assertEqual((wt["reading"], wt["latch"]), ("R1", "write-through"))
        self.assertIn("CANNOT exclude AHEAD + 2", wt["why"])
        self.assertIn("NOT proof", wt["why"])
        ka = V.dma_semantics(dma_line(post=(0, 999, 1, 0)))
        self.assertEqual((ka["reading"], ka["latch"]), ("R1", "keeps-active"))
        self.assertIn("the address arm is informative: AHEAD + 1", ka["why"])
        mixed = V.dma_semantics(dma_line(post=(500, 499, 1, 0)))
        self.assertEqual(mixed["latch"], "mixed")
        self.assertIn("not proven", mixed["why"])
        none = V.dma_semantics(dma_line())
        self.assertNotIn("latch", none)
        self.assertIn("not read in this log", none["why"])

    def test_r1_under_a_write_through_register_is_a_bounded_row_never_a_zero_shift(self):
        """RUN 56's ingestion caught the tool printing "shifts by +0.000 ms" for exactly this reading."""
        wt = V.dma_semantics(dma_line(post=(999, 0, 1, 0)))
        self.assertEqual((wt["offset_ms"], wt["offset_max_ms"]), (0.0, V.PERIOD_MS))
        ka = V.dma_semantics(dma_line(post=(0, 999, 1, 0)))
        self.assertEqual(ka["offset_max_ms"], 0.0)
        unread = V.dma_semantics(dma_line())
        self.assertEqual(unread["offset_max_ms"], V.PERIOD_MS, "no post read: the upper end is not excluded either")
        m = {"target": 4096, "ahead": 1, "hold_s": 60.0, "calls_per_period": 122.8, "feed_hz": 65288.0, "blocks_s": 4080.5, "loss": 0.00379, "delta": 0.00467,
             "tau_ms": 8.14, "feed_tau": 531.0, "mean_cs": 3827, "mean_ring": 3097, "min_ring_late": 2256, "c_min": 3773.0, "ring_mean_model": 3069.0,
             "L_mean_ms": 121.01, "L_low_ms": 120.18, "L_of_target_ms": 121.03, "in_domain": True, "underrun_seen": 0, "chunk_starts": 1914, "dma": wt}
        out = V.render(m)
        self.assertIn("BOUNDED under this reading: +0.000 to +31.222 ms", out)
        self.assertNotIn("shifts by +0.000", out)
        m["dma"] = ka
        self.assertIn("shifts by +0.000 ms", V.render(m))

    def test_the_verdict_prints_the_register_after_the_init(self):
        out = v28verdict.render(v28verdict.analyse(dma_line(post=(999, 0, 1, 0))))
        self.assertIn("DMA REGISTER AFTER THE INIT (post: new 999, kept 0, ambiguous 1, other 0)", out)
        self.assertIn("cannot separate AHEAD + 1 from AHEAD + 2", out)

    def test_r2_ahead_plus_two_shifts_every_row_up_a_chunk(self):
        r = V.dma_semantics(dma_line(prev1=1, prev2=998))
        self.assertEqual(r["reading"], "R2")
        self.assertAlmostEqual(r["offset_ms"], V.PERIOD_MS)

    def test_r3_a_finished_block_shifts_every_row_down_a_chunk(self):
        r = V.dma_semantics(dma_line(left_min=10, left_max=60, left_mean=30, bins=(1000, 0, 0, 0, 0, 0)))
        self.assertEqual(r["reading"], "R3")
        self.assertAlmostEqual(r["offset_ms"], -V.PERIOD_MS)

    def test_r4_anything_else_is_unresolved_and_names_why(self):
        r = V.dma_semantics(dma_line(none=300))
        self.assertEqual(r["reading"], "R4")
        self.assertIsNone(r["offset_ms"])
        self.assertIn("none of the registered readings", r["why"])
        r = V.dma_semantics(dma_line(bins=(0, 0, 0, 900, 100, 0), left_mean=3400))          # the address right, the bytes left not
        self.assertEqual(r["reading"], "R4")

    def test_the_thresholds(self):
        # 99 % of the classified for the address, 95 % of the callbacks for the bytes left
        self.assertEqual(V.dma_semantics(dma_line(n=1000, none=9))["reading"], "R1")        # 99.1 %
        self.assertEqual(V.dma_semantics(dma_line(n=1000, none=11))["reading"], "R4")       # 98.9 %
        self.assertEqual(V.dma_semantics(dma_line(bins=(0, 0, 0, 50, 950, 0)))["reading"], "R1")   # 95 % with >= 3 500 left
        self.assertEqual(V.dma_semantics(dma_line(bins=(0, 0, 0, 51, 949, 0)))["reading"], "R4")

    def test_silences_are_not_classified_and_too_few_callbacks_are_unresolved(self):
        r = V.dma_semantics(dma_line(n=1000, same12=200))
        self.assertEqual(r["reading"], "R1")
        self.assertEqual(r["classified"], 799)
        r = V.dma_semantics(dma_line(n=40))
        self.assertEqual(r["reading"], "R4")
        self.assertIn("too few", r["why"])

    def test_a_log_without_the_record_reads_none_and_the_tools_say_assumed(self):
        self.assertIsNone(V.dma_semantics("000001 IDENT x"))
        self.assertIn("ASSUMED", V.render(None))
        self.assertIn("not read in this log", v28verdict.render(v28verdict.analyse("000001 IDENT x\n" + "SYNCPH phase=0 t_start=1 t_end=2 ended=1 reason=complete")))

    def test_the_verdict_prints_the_reading(self):
        text = dma_line(prev1=1, prev2=998)
        out = v28verdict.render(v28verdict.analyse(text))
        self.assertIn("DMA SEMANTICS (V28DMA, 1000 callbacks", out)
        self.assertIn("R2", out)


if __name__ == "__main__":
    unittest.main()
