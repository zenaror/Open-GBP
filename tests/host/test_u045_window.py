"""tests/host/test_u045_window.py -- GitHub Issue #116: the live family's AUDIO loss rates re-derived without L2's
window, by tools/u045window.py, from the versioned fixtures of RUN 38-42.

DESCRIPTIVE. Nothing here re-judges a gate: every published figure is first reproduced from the same fixtures, so
that the restated one is known to come from the same data by the same rule, with only the window taken out.

Pinned:
  * every whole-window rate the record published, reproduced (25.41, 27.86, 19.02, 7.547, 7.266; RUN 40's arms:
    0.2532 and 0.7416 gaps per cycle, 0.341 [0.306, 0.379], 8.39 and 9.23 blocks/s) -- and beside each, the rate
    outside the window and inside it;
  * the instrument's footprint, MEASURED in both traces: exactly 320 kept `process` steps, one per cycle over 320
    consecutive cycles, at the hand-off cycles of the kept chunks the arm tags name;
  * that the arms ARE balanced inside the window, and that balance does NOT cancel the contamination: the window
    multiplies the half arm's loss gaps per cycle by about 2.7 and the full arm's by about 1.07, so the half/full
    ratio is 0.270 outside and 0.692 inside, against 0.341 over both;
  * that the reimplemented QUESTION S arithmetic reproduces tools/v24accept.py's own output exactly on all the
    analysed cycles -- the reason a subset result can be trusted to the same rule;
  * `P` and the AI-cycle phase outside the window (GBP-HW-327's AUDIO statistics were all inside it).
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import u045window  # noqa: E402
import v24accept  # noqa: E402

TB = 40500000


class Derived(object):
    _d = None

    @classmethod
    def get(cls):
        if cls._d is None:
            reps = u045window.traces()
            cls._d = {"reps": reps, "d": u045window.derive(reports=reps)}
        return cls._d


def rate(n, s):
    return n / float(s)


class EveryRunPerWholeSecond(unittest.TestCase):
    WANT = {38: (1626, 1323, 303, 1298), 39: (1783, 1471, 312, 1446), 40: (1217, 963, 254, 947),
            41: (483, 320, 163, 312), 42: (465, 299, 166, 293)}

    def test_whole_outside_inside(self):
        ps = Derived.get()["d"]["per_second"]
        got = dict((n, (r["whole"]["blocks"], r["outside"]["blocks"], r["inside"]["blocks"],
                        r["outside_without_s30"]["blocks"])) for n, r in ps.items())
        self.assertEqual(got, self.WANT)
        for n, r in ps.items():
            self.assertEqual((r["whole"]["seconds"], r["outside"]["seconds"], r["inside"]["seconds"],
                              r["outside_without_s30"]["seconds"]), (64, 54, 10, 53))
            self.assertEqual(r["whole"]["blocks"], r["outside"]["blocks"] + r["inside"]["blocks"])

    def test_the_published_whole_window_rates_are_these(self):
        ps = Derived.get()["d"]["per_second"]
        self.assertEqual([round(rate(ps[n]["whole"]["blocks"], 64), 2) for n in (38, 39, 40)], [25.41, 27.86, 19.02])
        self.assertEqual([round(rate(ps[n]["whole"]["blocks"], 64), 3) for n in (41, 42)], [7.547, 7.266])
        self.assertEqual(v24accept.RUN38_RATE, 25.41)
        self.assertEqual(v24accept.RUN39_RATE, 27.86)

    def test_outside_and_inside_rates(self):
        ps = Derived.get()["d"]["per_second"]
        self.assertEqual([round(rate(ps[n]["outside"]["blocks"], 54), 3) for n in sorted(ps)],
                         [24.5, 27.241, 17.833, 5.926, 5.537])
        self.assertEqual([round(rate(ps[n]["inside"]["blocks"], 10), 1) for n in sorted(ps)],
                         [30.3, 31.2, 25.4, 16.3, 16.6])

    def test_the_distortion_grows_as_the_runtime_improves(self):
        """inside/outside rate, in integers: 10 x inside x 54 against outside x 10 x 10 -- rising run by run."""
        ps = Derived.get()["d"]["per_second"]
        # ratio of rates = (in / 10) / (out / 54) = 54 in / (10 out)
        r = dict((n, (54 * ps[n]["inside"]["blocks"], 10 * ps[n]["outside"]["blocks"])) for n in ps)
        self.assertEqual([round(a / float(b), 2) for a, b in (r[n] for n in sorted(r))], [1.24, 1.15, 1.42, 2.75, 3.0])

    def test_the_8_push_runs_ranges_and_the_edge_second(self):
        ps = Derived.get()["d"]["per_second"]
        self.assertEqual((ps[42]["inside"]["min"], ps[42]["outside"]["max"]), (11, 10))
        self.assertEqual((ps[41]["inside"]["min"], ps[41]["outside"]["max"]), (11, 11))
        self.assertEqual([ps[n]["lost"][30] for n in sorted(ps)], [25, 25, 16, 8, 6])


class TheFootprintIsMeasured(unittest.TestCase):
    def test_320_kept_process_steps_one_per_cycle(self):
        fp = Derived.get()["d"]["footprint"]
        for n, calls in ((39, 239189), (40, 237493)):
            self.assertEqual((fp[n]["crc_cycles"], fp[n]["armed_cycle"], fp[n]["process_calls"],
                              fp[n]["floor_ticks"]), ([625, 944], 620, calls, 200), n)
        self.assertEqual([fp[n]["crc_step_ticks"]["p50"] for n in (39, 40)], [2334, 2343])
        self.assertEqual((fp[40]["crc_from_ticks"] // (TB // 1000), fp[40]["crc_to_ticks"] // (TB // 1000)),
                         (20139, 30098))       # ms after t_origin: 20.139 s to 30.098 s
        h = open(os.path.join(ROOT, "src", "audio", "gbp_aplay.h"), encoding="utf-8").read()
        self.assertRegex(h, r"#define GBP_APLAY_L2_CHUNKS\s+320u")

    def test_at_the_hand_off_cycles_of_the_kept_chunks(self):
        """The first kept chunk is the first started after the arming; chunk s is handed at callback s - 1
        (hand-off 0 is the AI's start, not a callback); the CRC runs in the process step after it."""
        rep40 = Derived.get()["reps"][1]
        t_arm = rep40["window"]["t_origin"] + 20 * TB
        seq, first = -1, None
        for s, tag in zip(rep40["steps"], rep40["step_tag"]):
            if s[2] == "produce" and tag & 2:
                seq += 1
                if first is None and s[0] >= t_arm:
                    first = seq
        self.assertEqual(first, 626)
        self.assertEqual(Derived.get()["d"]["footprint"][40]["crc_cycles"], [first - 1, first + 320 - 2])

    def test_a_footprint_that_is_not_320_consecutive_cycles_is_refused(self):
        rep = {"callbacks": [[i * 1000, i * 1000 + 10] for i in range(700)], "window": {"t_origin": 0},
               "trace": {"calls": {"process": 1}, "floor": 200},
               "steps": [[i * 1000 + 50, i * 1000 + 300, "process", i * 1000 + 300] for i in range(0, 640, 2)]}
        with self.assertRaises(ValueError):
            u045window.footprint(rep)
        rep["steps"] = [[i * 1000 + 50, i * 1000 + 300, "process", i * 1000 + 300] for i in range(100, 420)]
        self.assertEqual(u045window.footprint(rep)["crc_cycles"], [100, 419])


class RUN40ByArmAndWindow(unittest.TestCase):
    def test_the_frozen_question_S_is_reproduced_on_all_cycles(self):
        rep40 = Derived.get()["reps"][1]
        frozen = v24accept.question_S(rep40, {"observer": {"sanity_ok": True, "mean_undrained": None}})
        mine = Derived.get()["d"]["arms"]["all"]
        self.assertEqual(frozen["verdict"], "CAUSE")
        self.assertEqual((mine["S"]["ratio"], mine["S"]["ci90"], mine["S"]["p"], mine["S"]["difference_per_cycle"]),
                         (frozen["ratio"], list(frozen["ci90"]), frozen["p"], frozen["difference_per_cycle"]))
        self.assertEqual((mine["half"]["cycles"], mine["half"]["loss_gaps"], mine["full"]["cycles"],
                          mine["full"]["loss_gaps"]),
                         (frozen["arms"]["half"]["cycles"], frozen["arms"]["half"]["loss_gaps"],
                          frozen["arms"]["full"]["cycles"], frozen["arms"]["full"]["loss_gaps"]))
        self.assertEqual([round(x, 3) for x in [mine["S"]["ratio"]] + mine["S"]["ci90"]], [0.341, 0.306, 0.379])

    def test_the_arms_are_balanced_inside(self):
        a = Derived.get()["d"]["arms"]
        self.assertEqual([(a[v]["half"]["cycles"], a[v]["full"]["cycles"]) for v in
                          ("all", "inside", "outside", "crc_only", "seconds_20_29")],
                         [(1015, 1014), (162, 163), (853, 851), (160, 160), (160, 160)])

    def test_and_balance_does_not_cancel_it(self):
        a = Derived.get()["d"]["arms"]
        g = dict((v, (a[v]["half"]["loss_gaps"], a[v]["half"]["cycles"], a[v]["full"]["loss_gaps"],
                      a[v]["full"]["cycles"])) for v in ("all", "inside", "outside"))
        self.assertEqual(g, {"all": (257, 1015, 752, 1014), "inside": (88, 162, 128, 163),
                             "outside": (169, 853, 624, 851)})
        # the window's factor on each arm's gaps per cycle, in integers: half x 2.74, full x 1.07
        self.assertEqual(round((88 * 853) / float(162 * 169), 2), 2.74)
        self.assertEqual(round((128 * 851) / float(163 * 624), 2), 1.07)

    def test_the_ratio_outside_inside_and_under_every_definition(self):
        a = Derived.get()["d"]["arms"]
        got = dict((v, [round(x, 3) for x in [a[v]["S"]["ratio"]] + a[v]["S"]["ci90"]]) for v in a)
        self.assertEqual(got, {"all": [0.341, 0.306, 0.379],
                               "inside": [0.692, 0.584, 0.819], "outside": [0.27, 0.235, 0.308],
                               "crc_only": [0.693, 0.583, 0.821], "not_crc": [0.27, 0.235, 0.306],
                               "seconds_20_29": [0.685, 0.574, 0.81], "other_seconds": [0.272, 0.237, 0.308]})
        for v in ("outside", "not_crc", "other_seconds"):
            self.assertLess(a[v]["S"]["p"], 1 / 20000.0 + 1e-12, v)

    def test_R_prior_and_the_residue_restated(self):
        a = Derived.get()["d"]["arms"]
        k = lambda x: rate(x["sum_k"] * TB, x["cycle_ticks"])
        cnt = lambda x: (4096 * x["cycle_ticks"] / float(TB) - x["counted_blocks"]) * TB / x["cycle_ticks"]
        self.assertEqual([round(k(a[v]["half"]), 2) for v in ("all", "outside", "inside")], [8.39, 6.5, 18.39])
        self.assertEqual([round(cnt(a[v]["half"]), 2) for v in ("all", "outside", "inside")], [9.23, 7.51, 18.32])
        self.assertEqual([round(k(a[v]["full"]), 2) for v in ("all", "outside", "inside")], [29.79, 29.28, 32.42])
        self.assertEqual((a["all"]["half"]["sum_k"], round(a["all"]["half"]["cycle_ticks"] / float(TB), 3)),
                         (266, 31.69))
        self.assertEqual([round(a[v]["half"]["loss_gaps"] / float(a[v]["half"]["cycles"]), 4)
                          for v in ("all", "outside")], [0.2532, 0.1981])

    def test_P_by_arm_and_the_six_process_losses(self):
        a = Derived.get()["d"]["arms"]
        self.assertEqual(a["all"]["half"]["P"], {"produce": 229, "neither": 22, "process": 6})
        self.assertEqual(a["all"]["full"]["P"], {"produce": 673, "neither": 79})
        self.assertEqual(a["inside"]["half"]["P"], {"produce": 76, "neither": 6, "process": 6})
        self.assertEqual(a["outside"]["half"]["P"], {"produce": 153, "neither": 16})
        self.assertEqual(a["outside"]["full"]["P"], {"produce": 556, "neither": 68})


class TheTracesOutsideTheWindow(unittest.TestCase):
    def test_P_and_the_phase(self):
        t = Derived.get()["d"]["traces"]
        got = dict((n, dict((side, (t[n][side]["cycles"], t[n][side]["loss_gaps"], t[n][side]["sum_k"],
                                    t[n][side]["P"], t[n][side]["first_tenth"])) for side in ("inside", "outside")))
                   for n in (39, 40))
        self.assertEqual(got[39], {"inside": (325, 252, 316, {"isr": 1, "produce": 220, "neither": 31}, 229),
                                   "outside": (1704, 1198, 1461, {"produce": 1057, "neither": 141}, 1078)})
        self.assertEqual(got[40], {"inside": (325, 216, 258, {"produce": 193, "process": 6, "neither": 17}, 187),
                                   "outside": (1705, 795, 954, {"produce": 711, "neither": 84}, 685)})
        for n in (39, 40):
            self.assertEqual(t[n]["outside"]["P_decision"], "P names `produce`")


class TheToolIsDescriptive(unittest.TestCase):
    def test_it_says_so_and_imports_only_frozen_rules(self):
        src = open(os.path.join(ROOT, "tools", "u045window.py"), encoding="utf-8").read()
        self.assertIn("DESCRIPTIVE", src)
        self.assertEqual(sorted(set(re.findall(r"^import (\w+)", src, re.M)) - {"bisect", "json", "os", "random",
                                                                                "sys"}),
                         ["u045arms", "v22report", "v23accept", "v23report", "v24accept", "v24report"])


if __name__ == "__main__":
    unittest.main()
