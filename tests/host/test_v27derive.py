"""tests/host/test_v27derive.py -- GitHub Issue #120: tools/v27derive.py, RUN 43's descriptive figures beyond the
frozen gate, pinned on the versioned log (captures/fixtures/hw-gamecube-gbp-2026-09-25-sync-0001-run43.log).

The verdicts are tools/v27accept.py's and tests/host/test_run43.py recomputes them; this pins what the Issue asked
for beside them: the timeline, Phase 2's path setting by setting, the C-stick edges reconciled with the counters, M4
by dwell with its interval, and Phase 2's seconds by target. The dwell grouping and the interval are also checked on
a construction.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v27derive  # noqa: E402

LOG = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-25-sync-0001-run43.log")


class R(object):
    _r = None

    @classmethod
    def get(cls):
        if cls._r is None:
            with open(LOG, encoding="utf-8") as f:
                cls._r = v27derive.derive(f.read())
        return cls._r


def sec(s, target, phase=1, count=4090, mute=False, settling=False, und=0, ovf=0, fill=0.0):
    return {"s": s, "target": target, "phase": phase, "count": count, "mute": mute, "settling": settling,
            "underruns": und, "overflow": ovf, "fill": fill}


class OnAConstruction(unittest.TestCase):
    def test_dwells_are_runs_of_one_target(self):
        secs = [sec(0, 2048, phase=0), sec(1, 2048), sec(2, 2048, mute=True), sec(3, 512), sec(4, 512, settling=True),
                sec(5, 2048, count=4080), sec(6, 2048, phase=2)]
        d = v27derive.dwells(secs)
        self.assertEqual([(x["target"], x["seconds"], x["live"], x["settled"], x["lost"]) for x in d],
                         [(2048, 2, 1, 1, 6), (512, 2, 2, 1, 12), (2048, 1, 1, 1, 16)])

    def test_the_permutation_is_exact(self):
        deep = [{"lost": 10, "live": 1}, {"lost": 10, "live": 1}]
        shallow = [{"lost": 1, "live": 1}, {"lost": 1, "live": 1}]
        p = v27derive.permutation(deep, shallow)
        self.assertEqual(p["one_sided"], [1, 6])          # only the observed labelling is as low: 1 of C(4, 2)
        self.assertEqual(p["two_sided"], [2, 6])          # and its mirror is as extreme

    def test_the_interval_brackets_the_estimate_and_is_reproducible(self):
        deep = [{"lost": 7 * n, "live": n} for n in (5, 9, 12, 7)]
        shallow = [{"lost": 6 * n + k, "live": n} for n, k in ((6, 2), (10, -3), (8, 1), (11, 0))]
        a = v27derive.interval(deep, shallow, "lost", "live", draws=2000, seed=5)
        b = v27derive.interval(deep, shallow, "lost", "live", draws=2000, seed=5)
        self.assertEqual(a, b)
        r = v27derive.rate(shallow, "lost", "live") / v27derive.rate(deep, "lost", "live")
        self.assertLessEqual(a[0][0], r)
        self.assertGreaterEqual(a[0][1], r)


class TheIntervalsCoverage(unittest.TestCase):
    """Issue #120's second review: with six dwells a side the percentile interval is ANTI-CONSERVATIVE. Measured here,
    so the record cites a test and not a scratch script: equal rates (Poisson, the run's own pooled Phase 1 rate, 803
    blocks over 120 s), RUN 43's own dwell exposures, SIMS simulations of the tool's interval at DRAWS resamples
    each, all seeded. It excludes 1 in more than the nominal 10 % of them."""
    SIMS, DRAWS, LAM = 400, 1000, 803 / 120.0

    @staticmethod
    def poisson(rng, lam):
        import math
        L, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= rng.random()
            if p <= L:
                return k
            k += 1

    def test_the_interval_excludes_1_too_often_under_equal_rates(self):
        import random
        m = R.get()["m4"]
        deep = [d["live"] for d in m["dwells"] if d["target"] == 2048]
        shallow = [d["live"] for d in m["dwells"] if d["target"] == 512]
        self.assertEqual((deep, shallow), ([11, 10, 8, 3, 16, 1], [14, 10, 26, 3, 7, 11]))
        rng = random.Random(1200)
        excluded = 0
        for i in range(self.SIMS):
            dd = [{"lost": sum(self.poisson(rng, self.LAM) for _ in range(n)), "live": n} for n in deep]
            ss = [{"lost": sum(self.poisson(rng, self.LAM) for _ in range(n)), "live": n} for n in shallow]
            (lo, hi), _ = v27derive.interval(dd, ss, "lost", "live", draws=self.DRAWS, seed=i)
            excluded += hi < 1.0 or lo > 1.0
        self.assertGreater(excluded, 0.10 * self.SIMS)
        self.assertEqual(excluded, EXCLUDED)


EXCLUDED = 63                   # of 400: 15.75 %, against the nominal 10 %


class ThePermutationsSize(unittest.TestCase):
    """Issue #121's review: the rule the adoption produced asks for BOTH statistics to be calibrated against the
    design, and the primary one had only been argued exact. Measured here under the same null as TheIntervalsCoverage
    (equal rates, Poisson losses at 803/120 per second, RUN 43's dwell exposures, the same seed): how often the exact
    permutation of the 12 dwells rejects at one-sided 0.05 and at two-sided 0.10."""
    SIMS = 400

    def test_the_permutation_holds_its_nominal_size_under_equal_rates(self):
        import random
        m = R.get()["m4"]
        deep = [d["live"] for d in m["dwells"] if d["target"] == 2048]
        shallow = [d["live"] for d in m["dwells"] if d["target"] == 512]
        rng = random.Random(1200)
        one = two = 0
        for _ in range(self.SIMS):
            dd = [{"lost": sum(TheIntervalsCoverage.poisson(rng, TheIntervalsCoverage.LAM) for _ in range(n)), "live": n}
                  for n in deep]
            ss = [{"lost": sum(TheIntervalsCoverage.poisson(rng, TheIntervalsCoverage.LAM) for _ in range(n)), "live": n}
                  for n in shallow]
            p = v27derive.permutation(dd, ss)
            one += p["one_sided"][0] <= 0.05 * p["one_sided"][1]
            two += p["two_sided"][0] <= 0.10 * p["two_sided"][1]
        self.assertEqual((one, two), PERMUTATION_REJECTIONS)
        self.assertLessEqual(one, 0.05 * self.SIMS + 2 * (0.05 * 0.95 * self.SIMS) ** 0.5)
        self.assertLessEqual(two, 0.10 * self.SIMS + 2 * (0.10 * 0.90 * self.SIMS) ** 0.5)


PERMUTATION_REJECTIONS = (16, 36)       # of 400: 4.0 % at one-sided 0.05, 9.0 % at two-sided 0.10


class RUN43(unittest.TestCase):
    def test_the_timeline(self):
        t = R.get()["timeline"]
        self.assertEqual((t["stop"], t["reason"], t["secs"]), ("event_store_cap", "not_finished", 243))
        m = dict((x["what"], (round(x["from_capture_s"], 3), round(x["from_origin_s"], 3))) for x in t["marks"])
        self.assertEqual(m["press"], (6.560, -1.0))
        self.assertEqual(m["origin"], (7.560, 0.0))
        self.assertEqual(m["awr_last"], (7.719, 0.159))
        self.assertEqual(m["phase1_start"], (46.033, 38.473))
        self.assertEqual(m["phase1_end"], (195.216, 187.655))
        self.assertEqual(m["phase2_start"], (195.216, 187.655))
        self.assertEqual(m["stop"], (249.734, 242.174))
        self.assertNotIn("phase2_end", m)
        self.assertNotIn("phase3_start", m)

    def test_phase_2_setting_by_setting(self):
        p = R.get()["phase2"]
        self.assertEqual((p["p2_lo"], p["p2_hi"], p["p2_step"]), (384, 3584, 128))
        s0, s1 = p["settings"]
        self.assertEqual((s0["start"], s0["left"], s0["steps"], s0["refused"], s0["confirmed"]),
                         (896, "shallower", {"L": 5, "R": 1}, {"L_at_floor": 8}, 384))
        self.assertEqual(s0["path"], [896, 768, 640, 512, 384, 512, 384])
        self.assertEqual((s1["start"], s1["left"], s1["steps"], s1["refused"], s1["confirmed"], s1["level_at_stop"]),
                         (640, "deeper", {"L": 23, "R": 5}, {"L_at_top": 4}, None, 2944))
        self.assertEqual(s1["path"][:2] + s1["path"][-6:], [640, 768, 3584, 3456, 3328, 3200, 3072, 2944])
        self.assertEqual(max(s1["path"]), 3584)
        self.assertEqual(round(s0["t_start_s"], 3), 0.0)
        self.assertEqual(round(s1["t_start_s"], 3), 26.109)

    def test_the_c_stick_edges_reconcile(self):
        c = R.get()["cstick"]
        self.assertEqual((c["syncend_cs"], c["syncend_acted"], c["records"], c["acted"]), (84, 71, 84, 71))
        self.assertEqual(c["by_phase"], {"phase1": {"edges": 37, "acted": 36, "refused": 1, "busy": 0},
                                         "phase2": {"edges": 47, "acted": 35, "refused": 12, "busy": 0}})
        self.assertEqual((c["syncref"]["answer"], c["syncref"]["step_end"]), (1, 12))
        self.assertEqual(sum(v for k, v in c["syncref"].items()), 13)

    def test_m4_by_dwell(self):
        m = R.get()["m4"]
        d, s = m["arms"]["DEEP"], m["arms"]["SHALLOW"]
        self.assertEqual((d["dwells"], d["live_s"], d["settled_s"], d["lost"], d["underruns"], d["overflow"]),
                         (6, 49, 32, 355, 0, 0))
        self.assertEqual((s["dwells"], s["live_s"], s["settled_s"], s["lost"], s["underruns"], s["overflow"]),
                         (6, 71, 53, 448, 0, 0))
        self.assertEqual((round(d["per_s"], 3), round(s["per_s"], 3)), (7.245, 6.310))
        self.assertEqual((round(d["per_s_settled"], 3), round(s["per_s_settled"], 3)), (7.125, 6.094))
        self.assertEqual(round(s["underrun_rate_95_upper_per_s"], 4), round(3.0 / 71, 4))
        live, sett = m["ratio"]["live"], m["ratio"]["settled"]
        self.assertEqual((round(live["shallow_over_deep"], 3), [round(v, 3) for v in live["ci90"]]),
                         (0.871, [0.798, 0.977]))
        self.assertEqual((round(sett["shallow_over_deep"], 3), [round(v, 3) for v in sett["ci90"]]),
                         (0.855, [0.768, 0.974]))
        self.assertEqual([x["target"] for x in m["dwells"]], [512, 2048] * 6)
        # the percentile interval is anti-conservative with six dwells a side; the exact permutation beside it
        self.assertEqual(m["permutation"], {"one_sided": [63, 924], "two_sided": [126, 924]})

    def test_phase_2_seconds_at_the_floor(self):
        b = R.get()["phase2_seconds"]["384"]
        self.assertEqual((b["live_s"], b["settled_s"], b["lost"], b["underruns"], b["overflow"]), (13, 9, 93, 0, 0))
        self.assertEqual(round(b["fill_settled_mean"], 1), 312.9)
        self.assertEqual(sum(x["underruns"] for x in R.get()["phase2_seconds"].values()), 0)


if __name__ == "__main__":
    unittest.main()
