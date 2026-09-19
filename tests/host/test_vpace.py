"""
tests/host/test_vpace.py — the offline cadence model (HARDWARE_TESTS §V5.48).

A MODEL, and the tests exist mostly to stop it passing itself off as an
observation. The order matters: the model must reproduce the physical run
EXACTLY before any policy comparison is allowed to mean anything, so the
baseline-reproduction tests come first and the policy tests assert that they
ran.

Both physical inputs used here are versioned: the 287 772 B `OGBPDISP1` sidecar
and the 24 652 B `OGBPQUAL1` projection that carries the scientific
`frame_index` population. The 8.9 MB witness sidecar is not needed.
"""
import os
import statistics
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import vpace   # noqa: E402
import vdisp   # noqa: E402
import vqual   # noqa: E402

FIX = os.path.join(ROOT, "captures", "fixtures")
DISP = os.path.join(FIX, "hw-gamecube-gbp-2026-09-19-stream-0007-run5-disp.bin")
QUAL = os.path.join(FIX, "hw-gamecube-gbp-2026-09-19-idxcap-run5-qual.bin")
TB = vpace.TB
_C = {}


def model():
    """The physical model, fitted once: VI period, origin, latch margin."""
    if "m" not in _C:
        d = vdisp.load(DISP)
        allev = sorted(d["events"], key=lambda e: e["ordinal"])
        s = [(e["t"], e["retrace"]) for e in allev]
        lo, hi, P = vpace.vi_period_feasible(s)
        origin = vpace.vi_origin(s, P)
        mlo, mhi = vpace.fit_latch_margin(allev, P, origin)
        src = {r["frame_index"] for r in vqual.load(QUAL)["records"]}
        ev = [e for e in allev if e["frame_index"] != vdisp.KEY_NONE]
        frames = [(e["frame_index"], float(e["t"])) for e in ev if e["frame_index"] in src]
        _C["m"] = {"d": d, "allev": allev, "P": P, "P_lo": lo, "P_hi": hi,
                   "origin": origin, "margin": float((mlo + mhi) // 2),
                   "margin_lo": mlo, "margin_hi": mhi, "src": src,
                   "ev": ev, "frames": frames}
    return _C["m"]


class TheViModelIsFittedNotAssumed(unittest.TestCase):
    def test_the_period_is_pinned_by_feasibility_to_ntsc(self):
        m = model()
        self.assertLess(m["P_hi"] - m["P_lo"], 5.0, "the admissible range is tight")
        self.assertEqual(m["P"], 675675.0)
        self.assertAlmostEqual(TB / m["P"], 59.94006, places=4)

    def test_the_span_ratio_estimator_is_rejected_by_its_own_residuals(self):
        """It is kept in the tool so this test can show why it must not be used:
        it is biased by the phase difference between the first and last sample,
        and proposes a period its own data does not fit inside."""
        m = model()
        s = [(e["t"], e["retrace"]) for e in m["allev"]]
        bad = vpace.span_ratio_period(s)
        v = [t - bad * r for t, r in s]
        self.assertGreater(max(v) - min(v), bad)
        good = [t - m["P"] * r for t, r in s]
        self.assertLess(max(good) - min(good), m["P"])

    def test_a_latch_margin_is_required_and_is_bounded(self):
        """Without a setup margin the model gets three events wrong -- and they
        are exactly the three holds where the sampled retrace had advanced,
        which is how the margin was found."""
        m = model()
        self.assertEqual(vpace.replay_mismatches(m["allev"], m["P"], m["origin"], 0.0), 3)
        self.assertEqual(vpace.replay_mismatches(m["allev"], m["P"], m["origin"], m["margin"]), 0)
        self.assertGreater(m["margin_lo"], 0)
        self.assertLess(m["margin_hi"] / TB * 1e6, 30.0, "under 30 us")

    def test_the_model_reproduces_every_recorded_xfb_state(self):
        m = model()
        self.assertEqual(len(m["allev"]), 2114)
        self.assertEqual(vpace.replay_mismatches(m["allev"], m["P"], m["origin"], m["margin"]), 0)


class TheBaselineMustReproduceThePhysicalRun(unittest.TestCase):
    """§V5.48: no policy comparison is meaningful from a model that cannot
    reproduce the run it claims to model."""

    RECORDED_HOLDS = [334, 336, 345, 609, 620, 891, 893, 904, 1175, 1177, 1188,
                      1457, 1460, 1471, 1744, 2017, 2028]

    def sim(self, policy, n_xfb=2, tex=2, retry_dt=6400.0):
        m = model()
        return vpace.simulate(m["frames"], policy, n_xfb, m["P"], m["origin"],
                              m["margin"], retry_dt=retry_dt, tex_buffers=tex)

    def test_the_scientific_population_is_the_exact_join(self):
        m = model()
        self.assertEqual(len(m["src"]), 2048)
        self.assertEqual((min(m["src"]), max(m["src"])), (70, 2117))
        self.assertEqual(len(m["frames"]), 2047, "frame 2117 was never taken")

    def test_the_baseline_drops_the_same_seventeen_frames(self):
        r = self.sim("baseline")
        self.assertEqual(r["source_dropped"], 17)
        self.assertEqual(r["superseded"], 0)
        self.assertEqual(sorted(r["dropped_frames"]), self.RECORDED_HOLDS[:12])

    def test_the_baseline_drops_match_the_recorded_holds(self):
        m = model()
        rec = sorted(e["frame_index"] for e in m["ev"]
                     if e["decision"] == 2 and e["frame_index"] in m["src"])
        self.assertEqual(rec, self.RECORDED_HOLDS)


class TheRateArithmetic(unittest.TestCase):
    def test_the_display_has_more_intervals_than_the_source_has_frames(self):
        """The correction §V5.48.1 rests on: f_vi > f_src, so source-lossless is
        ACHIEVABLE and only display repeats are unavoidable."""
        m = model()
        f_vi = TB / m["P"]
        span = m["frames"][-1][1] - m["frames"][0][1]
        n_vi = span / m["P"]
        self.assertGreater(f_vi, 59.9)
        self.assertGreater(n_vi, len(m["frames"]), "more intervals than frames")
        required = n_vi - len(m["frames"]) + 1
        self.assertGreater(required, 5)
        self.assertLess(required, 10)

    def test_a_drop_and_a_repeat_are_counted_separately(self):
        """§V5.48: the runtime's single `repeats` counter stands for two things
        at once. The model must not. Each baseline drop costs one EXTRA display
        repeat on top of the ones the rate difference requires, and the two
        quantities have to add up exactly:

            baseline repeats  =  required repeats  +  baseline drops

        Without this, a model that folded drops into the repeat count would go
        unnoticed -- which is what mutation M3 did."""
        m = model()
        base = vpace.simulate(m["frames"], "baseline", 2, m["P"], m["origin"], m["margin"])
        loss = vpace.simulate(m["frames"], "defer", 2, m["P"], m["origin"], m["margin"])
        span = m["frames"][-1][1] - m["frames"][0][1]
        required = round(span / m["P"]) - len(m["frames"]) + 1
        self.assertEqual(base["source_dropped"], 17)
        self.assertEqual(base["display_repeats"], 24)
        self.assertEqual(loss["display_repeats"], 7)
        self.assertLessEqual(abs(loss["display_repeats"] - required), 1)
        self.assertEqual(base["display_repeats"],
                         loss["display_repeats"] + base["source_dropped"])

    def test_a_lossless_policy_produces_exactly_the_required_repeats(self):
        m = model()
        r = vpace.simulate(m["frames"], "defer", 2, m["P"], m["origin"], m["margin"])
        span = m["frames"][-1][1] - m["frames"][0][1]
        required = round(span / m["P"]) - len(m["frames"]) + 1
        self.assertEqual(r["source_dropped"], 0)
        self.assertEqual(r["superseded"], 0)
        self.assertLessEqual(abs(r["display_repeats"] - required), 1)


class TwoXfbDeferralIsSourceLossless(unittest.TestCase):
    """§V5.48 central question. If this fails, a third framebuffer is back on
    the table; if it passes, it is not."""

    def test_on_the_physical_replay(self):
        m = model()
        r = vpace.simulate(m["frames"], "defer", 2, m["P"], m["origin"], m["margin"])
        self.assertEqual(r["source_dropped"], 0)
        self.assertEqual(r["superseded"], 0)
        self.assertEqual(r["never_displayed"], 0)
        self.assertEqual(r["presented"], 2047)
        self.assertEqual(r["max_deferred"], 1, "one deferred frame, never two")
        self.assertTrue(r["order_preserved"])
        self.assertLess(r["latency"]["max"] / TB * 1000, 2.0, "max under 2 ms")

    def test_a_third_framebuffer_does_not_help_and_hides_the_loss(self):
        """It converts 17 drops into 17 SUPERSESSIONS: the same frames never
        reach the screen, because VIDEO_SetNextFramebuffer latches once per
        retrace however many buffers exist. A policy that counted hand-offs
        instead of latches would report this as a success."""
        m = model()
        r = vpace.simulate(m["frames"], "defer", 3, m["P"], m["origin"], m["margin"])
        self.assertEqual(r["source_dropped"], 0)
        self.assertEqual(r["superseded"], 17)
        self.assertEqual(r["never_displayed"], 17)

    def test_the_retry_granularity_matters_and_is_stated(self):
        """Retrying only once per source frame is not enough; retrying from
        pump() -- every ~158 us in the physical run -- is far more than enough."""
        m = model()
        coarse = vpace.simulate(m["frames"], "defer", 2, m["P"], m["origin"],
                                m["margin"], retry_dt=m["P"])
        self.assertGreater(coarse["source_dropped"], 0)
        fine = vpace.simulate(m["frames"], "defer", 2, m["P"], m["origin"],
                              m["margin"], retry_dt=6400.0)
        self.assertEqual(fine["source_dropped"], 0)


class ThePhaseSweepAndTheHorizon(unittest.TestCase):
    """A policy that only works at the phase run 5 happened to start in is not
    a policy."""

    def jitter(self):
        m = model()
        sci = [e for e in m["ev"] if e["frame_index"] in m["src"]]
        return vpace.observed_jitter(sci)

    def test_the_jitter_model_tracks_the_measured_source_rate(self):
        """Fitted on frame_index, never on the decision ordinal: 17 frames are
        missing from the decision sequence and an ordinal fit folds them into
        the slope."""
        m = model()
        slope, off = self.jitter()
        self.assertAlmostEqual(slope, 678084.0, delta=5.0)
        self.assertLess(max(abs(x) for x in off) / TB * 1000, 2.0,
                        "jitter is sub-millisecond, not multi-frame")

    def test_source_frames_never_overtake_one_another(self):
        _, off = self.jitter()
        fr = vpace.make_frames(400, 678084.0, 0.0, off, seed=3)
        self.assertEqual([i for i, _ in fr], sorted(i for i, _ in fr))
        self.assertTrue(all(b[1] > a[1] for a, b in zip(fr, fr[1:])))

    def test_the_overtake_clamp_is_exercised_not_merely_present(self):
        """With the measured jitter no draw ever reaches a neighbour, so the
        clamp is never reached and a mutation removing it is inert -- which the
        mutation round found. This forces it: a pool wider than the period MUST
        still come out in index order, because the assembler cannot emit frames
        out of order however the decisions land."""
        period = 678084.0
        wide = [-period, +period, 0.0, +2 * period, -2 * period]
        fr = vpace.make_frames(200, period, 0.0, wide, seed=5)
        self.assertEqual([i for i, _ in fr], list(range(200)),
                         "indices must stay in order")
        self.assertTrue(all(b[1] > a[1] for a, b in zip(fr, fr[1:])),
                        "times must stay strictly increasing")

    def test_every_initial_phase_is_lossless(self):
        m = model()
        _, off = self.jitter()
        s = vpace.sweep_phase(256, 400, 678084.0, m["P"], m["margin"], jitter=off)
        self.assertEqual(s["total_drops"], 0)
        self.assertEqual(s["total_superseded"], 0)
        self.assertEqual(s["max_queue"], 1)
        self.assertTrue(s["order_always"])
        self.assertLess(s["max_latency"] / TB * 1000, 3.0)

    def test_the_baseline_is_not(self):
        m = model()
        _, off = self.jitter()
        s = vpace.sweep_phase(256, 400, 678084.0, m["P"], m["margin"],
                              policy="baseline", jitter=off)
        self.assertGreater(s["total_drops"], 100)

    def test_the_queue_depth_is_measured_and_not_assumed(self):
        """max_deferred is 1 in every realistic case, so a mutation that hard
        codes 1 is inert on the real data -- the mutation round found that too.
        A retry granularity coarse enough to strand two frames makes the
        counter do real work, and it must report 2."""
        m = model()
        _, off = self.jitter()
        fr = vpace.make_frames(300, 678084.0, 0.0, off, seed=9)
        r = vpace.simulate(fr, "defer", 2, m["P"], 0.0, m["margin"],
                           retry_dt=4 * m["P"], tex_buffers=4)
        self.assertGreater(r["max_deferred"], 1,
                           "this configuration must strand more than one frame")

    def test_a_long_horizon_stays_bounded(self):
        m = model()
        _, off = self.jitter()
        n = 12000                      # ~3.3 minutes, ~42 beat periods
        fr = vpace.make_frames(n, 678084.0, 0.0, off, seed=11)
        r = vpace.simulate(fr, "defer", 2, m["P"], 0.0, m["margin"])
        self.assertEqual(r["source_dropped"], 0)
        self.assertEqual(r["superseded"], 0)
        self.assertEqual(r["max_deferred"], 1, "the queue does not grow with time")
        self.assertLess(r["latency"]["max"] / TB * 1000, 3.0, "no latency drift")
        required = round((fr[-1][1] - fr[0][1]) / m["P"]) - n + 1
        self.assertLessEqual(abs(r["display_repeats"] - required), 2)


class AdversarialJitter(unittest.TestCase):
    def sweep(self, scale, n=128):
        m = model()
        sci = [e for e in m["ev"] if e["frame_index"] in m["src"]]
        _, off = vpace.observed_jitter(sci)
        return vpace.sweep_phase(n, 300, 678084.0, m["P"], m["margin"],
                                 jitter=[x * scale for x in off])

    def test_it_survives_two_and_four_times_the_measured_spread(self):
        for scale in (2, 4):
            s = self.sweep(scale)
            self.assertEqual(s["total_drops"], 0, "scale %d" % scale)
            self.assertEqual(s["total_superseded"], 0, "scale %d" % scale)
            self.assertEqual(s["max_queue"], 1, "scale %d" % scale)

    def test_a_labelled_stress_run_still_does_not_lose_a_frame(self):
        """10x the physical spread. Labelled stress: no claim that hardware
        does this, only that the policy does not depend on lucky phase."""
        s = self.sweep(10, n=64)
        self.assertEqual(s["total_drops"], 0)
        self.assertEqual(s["max_queue"], 1)


if __name__ == "__main__":
    unittest.main()
