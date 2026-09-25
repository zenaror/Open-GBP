"""tests/host/test_v28ahead.py -- GitHub Issue #122: tools/v28ahead.py, how fast the chain puts a chunk back into READY
after the AI takes one, the margin that leaves against a producer stop at each GBP_APLAY_AHEAD, and the chain's latency
at each (TARGET, AHEAD). DESCRIPTIVE; a measurement and an arithmetic for the design, never a gate.

On constructions: the refill is the first flush_queue AFTER a callback, never one before it; a chunk's arm is the tag of
the production step that finished it; a flush_queue with no production step before it is refused; the latency depends
on TARGET + 128 x AHEAD only. From the SOURCE and the RECORDS: the tag's bit 0 is the 8-push arm, the images start the AI
only at READY >= 2 and call the producer once per pump run, the default is 4 chunks, the largest stall is GBP-HW-320's.
Then the versioned traces are pinned (RUN 39, RUN 40) with the pump-slot rates of the traced and the game runs, the
latency table, and the ring's offset predicted against the one RUN 43 measured.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v28ahead  # noqa: E402

TB = 40500000


def read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


def section(text, heading):
    i = text.index(heading)
    j = text.find("\n### ", i + 1)
    return text[i:j if j >= 0 else len(text)]


def ms(x):
    return int(round(x * TB / 1000.0))


class OnConstructions(unittest.TestCase):
    def rep(self, callbacks, steps, tags=None):
        r = {"callbacks": [[c, c + 100] for c in callbacks], "steps": steps}
        if tags is not None:
            r["step_tag"] = tags
        return r

    def test_the_refill_is_the_first_flush_after_the_callback(self):
        steps = [[ms(0.5), ms(0.6), "flush_queue", 0],             # before the callback: not its refill
                 [ms(12.0), ms(13.0), "flush_queue", 0],
                 [ms(14.0), ms(15.0), "flush_queue", 0]]
        r = v28ahead.refills(self.rep([ms(10.0)], steps))
        self.assertEqual(len(r), 1)
        self.assertAlmostEqual(r[0][0], 3.0, places=3)
        self.assertEqual(r[0][1], 16)                               # an untagged trace is RUN 39's 16-push calls

    def test_a_callback_with_no_flush_after_it_has_no_refill(self):
        self.assertEqual(v28ahead.refills(self.rep([ms(10.0)], [[ms(1), ms(2), "flush_queue", 0]])), [])

    def test_the_arm_is_the_tag_of_the_step_that_finished_the_chunk(self):
        steps = [[ms(10.5), ms(11.0), "produce", 0], [ms(11.0), ms(11.1), "flush_queue", 0],
                 [ms(41.5), ms(42.0), "produce", 0], [ms(42.0), ms(42.1), "flush_queue", 0]]
        tags = [0b101, 0, 0b110, 0]                                 # bit 0: 1 = 8 pushes
        r = v28ahead.refills(self.rep([ms(10.0), ms(41.0)], steps, tags))
        self.assertEqual([a for _v, a in r], [8, 16])

    def test_a_flush_with_no_production_before_it_is_refused(self):
        with self.assertRaises(ValueError):
            v28ahead.refills(self.rep([ms(10.0)], [[ms(11.0), ms(11.1), "flush_queue", 0]], [0]))

    def test_the_latency_depends_on_target_plus_128_ahead_only(self):
        for t, a in ((512, 1), (384, 2), (256, 3)):
            self.assertAlmostEqual(v28ahead.latency_ms(t, a), v28ahead.latency_ms(t + 128, a - 1), places=9)
        self.assertAlmostEqual(v28ahead.latency_ms(256, 2) - v28ahead.latency_ms(256, 1), 31.25, places=9)

    def test_the_take_s_arrivals_raise_the_mean(self):
        self.assertAlmostEqual(v28ahead.mean_fill_offset(1e12), -(16.5 + 64.0), places=6)   # an instant take
        self.assertGreater(v28ahead.mean_fill_offset(3000.0), v28ahead.mean_fill_offset(4000.0))


class TheSourceSaysWhatTheToolSays(unittest.TestCase):
    def test_bit_0_of_the_tag_is_the_8_push_arm(self):
        src = read("poc/gbp-audio-split/source/main.c")
        self.assertIn("bit 0 the chunk's APPLIED arm (1 = 8-push\n * steps)", src)
        self.assertIn("return (uint8_t)(((ap.cur_step == GBP_ASPLIT_HALF_PUSHES) ? 1u : 0u)", src)

    def test_the_images_start_the_ai_at_two_ready_chunks_and_keep_four(self):
        self.assertIn("gbp_aplay_ready(&ap) >= 2u", read("poc/gbp-audio-sync/source/main.c"))
        self.assertIn("#define GBP_APLAY_AHEAD            4u", read("src/audio/gbp_aplay.h"))

    def test_one_production_call_per_pump_run_in_8_push_steps(self):
        h = read("src/audio/gbp_aplay.h")
        self.assertIn("#define GBP_APLAY_PUSHES         128u", h)
        self.assertIn("#define GBP_APLAY_STEP_PUSHES      8u", h)
        self.assertEqual(128 // 8, v28ahead.TAKE_RUNS)
        self.assertIn("else b = gbp_aplay_produce(&ap, &adec);", read("poc/gbp-audio-sync/source/main.c"))

    def test_the_largest_stall_is_gbp_hw_320_s(self):
        e = section(read("docs/research/EVIDENCE.md"), "### GBP-HW-320 ")
        self.assertIn("took 24.43 ms", e.splitlines()[0])
        self.assertEqual(v28ahead.LARGEST_STALL_MS, 24.43)


class TheTraces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = v28ahead.analyse()

    def test_nothing_was_dropped_and_no_mute_ran(self):
        for n, cb in (("39", 2030), ("40", 2031)):
            x = self.r["traced"][n]
            self.assertEqual((x["callbacks"], x["flush_queue"], x["dropped"]), (cb, 2035, 0))
            self.assertEqual(sum(d["n"] for d in x["arms"].values()), 2030)
            self.assertAlmostEqual(x["period_ms"], 31.222, places=3)
            # one chunk queued per hand-off interval, but for one: the refill is the producer's, not a transition's
            self.assertEqual(x["flushes_per_interval"], {"1": cb - 2, "2": 1})

    def test_run39_sixteen_push_calls(self):
        d = self.r["traced"]["39"]["arms"]
        self.assertEqual(sorted(d), ["16"])
        self.assertEqual((round(d["16"]["median"], 2), round(d["16"]["p99"], 2), round(d["16"]["max"], 2)),
                         (2.42, 3.43, 3.66))

    def test_run40_the_runtime_s_eight_push_arm(self):
        d = self.r["traced"]["40"]["arms"]
        self.assertEqual((d["8"]["n"], d["16"]["n"]), (1015, 1015))
        self.assertEqual((round(d["8"]["median"], 2), round(d["8"]["p99"], 2), round(d["8"]["max"], 2)),
                         (4.86, 5.86, 6.12))
        self.assertEqual((round(d["16"]["median"], 2), round(d["16"]["max"], 2)), (2.43, 3.59))

    def test_the_pump_slot_rates(self):
        got = dict((n, round(x["pump_per_s"])) for n, x in self.r["traced"].items())
        got.update((n, round(v)) for n, v in self.r["games_pump_per_s"].items())
        self.assertEqual(got, {"39": 3801, "40": 3787, "41": 3933, "42": 3889, "43": 3676})

    def test_the_margins(self):
        m = dict((a, round(v, 1)) for a, v in self.r["margin_ms"].items())
        self.assertEqual(m, {"1": 25.1, "2": 56.3, "3": 87.6, "4": 118.8})

    def test_the_latency_table(self):
        got = dict((t, [round(self.r["latency_ms"][t][str(a)], 1) for a in (4, 3, 2, 1)]) for t in self.r["latency_ms"])
        self.assertEqual(got, {"512": [279.2, 247.9, 216.7, 185.4], "384": [247.9, 216.7, 185.4, 154.2],
                               "256": [216.7, 185.4, 154.2, 122.9], "192": [201.0, 169.8, 138.5, 107.3],
                               "146": [189.8, 158.6, 127.3, 96.1]})

    def test_the_offset_predicted_and_measured(self):
        self.assertEqual(round(self.r["mean_fill_offset_run43"], 2), -71.59)
        m = self.r["measured_offset_run43"]
        self.assertEqual(sorted(m, key=int), ["384", "512", "1536", "2048", "3584"])
        self.assertEqual([m[t]["n"] for t in ("384", "512", "1536", "2048", "3584")], [9, 53, 1, 64, 4])
        for t, d in m.items():
            self.assertTrue(-71.7 <= d["min"] <= d["mean"] <= d["max"] <= -70.6, (t, d))
        # the prediction sits within half a sample of every measured mean
        self.assertTrue(all(abs(d["mean"] - self.r["mean_fill_offset_run43"]) < 0.5 for d in m.values()))

    def test_the_deficit(self):
        c, a, d = self.r["deficit_run43"]
        self.assertEqual((round(c, 2), round(a, 2), round(d, 2)), (4099.64, 4089.18, 10.47))
        self.assertEqual((round(128 / d, 1), round(d / 4.096, 2), round(c / 128 - d, 2)), (12.2, 2.56, 21.56))

    def test_the_ladder(self):
        self.assertEqual([(t, a, s_, round(l, 1)) for t, a, s_, l in self.r["ladder_ms"]],
                         [(704, 4, 1216, 326.0), (576, 4, 1088, 294.8), (448, 4, 960, 263.5), (320, 4, 832, 232.3),
                          (192, 4, 704, 201.0), (192, 3, 576, 169.8), (192, 2, 448, 138.5), (192, 1, 320, 107.3)])
        steps = [b[3] - a[3] for a, b in zip(self.r["ladder_ms"], self.r["ladder_ms"][1:])]
        self.assertTrue(all(abs(x + 31.25) < 1e-9 for x in steps))            # one step = 128 samples = 31.25 ms

    def test_the_startup_second_excluded_is_the_ramp(self):
        import v27report
        s = v27report.build(read("captures/fixtures/hw-gamecube-gbp-2026-09-25-sync-0001-run43.log"))["seconds"]
        self.assertEqual([round(x["fill"] - x["target"], 2) for x in s[4:7]], [-103.19, -79.31, -70.88])
        self.assertEqual(v28ahead.STARTUP_S, 6)


if __name__ == "__main__":
    unittest.main()
