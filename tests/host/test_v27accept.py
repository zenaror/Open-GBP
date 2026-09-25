"""tests/host/test_v27accept.py -- the gates of HARDWARE_TESTS.md §V27 (GitHub Issue #117), frozen on synthetic
reports BEFORE the image exists. Every branch of every verdict is reached by a construction, and the counts §V27.10
froze are the ones the tool decides by. Nothing here reads hardware data.
"""
import copy
import os
import subprocess
import sys
import unittest
from fractions import Fraction
from math import comb

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v27accept as v  # noqa: E402

CFG = {"deep": 2048, "shallow": 512, "floor": 384, "mute_chunks": 16, "step_mute_chunks": 4, "p2_lo": 384,
       "p2_hi": 3584, "p2_step": 128, "p3_step": 32, "p3_dwell_s": 6, "caps": {"p1": 300, "p2": 240, "p3": 180,
                                                                                "session": 720}}


def schedule(first="REAL"):
    """12 REAL + 6 NULL in a fixed order whose first is REAL (the seeded order is the image's; any order is legal)."""
    s = ["REAL", "REAL", "NULL", "REAL", "NULL", "REAL", "REAL", "NULL", "REAL", "REAL", "NULL", "REAL", "NULL",
         "REAL", "REAL", "NULL", "REAL", "REAL"]
    assert s.count("REAL") == 12 and s.count("NULL") == 6 and s[0] == first
    return s


def switches(answers=None, initial="DEEP"):
    """The 18 switches a schedule produces from an initial level, each answered as the caller says
    ("predicted" answers every real switch in its predicted direction and every null SAME)."""
    level = CFG["deep"] if initial == "DEEP" else CFG["shallow"]
    out = []
    for i, kind in enumerate(schedule()):
        nxt = level if kind == "NULL" else (CFG["shallow"] if level == CFG["deep"] else CFG["deep"])
        sw = {"seq": i, "kind": kind, "from": level, "to": nxt, "t": 1000 + 10 * i, "discard": 1536 + 2048,
              "answer": None, "t_answer": None}
        if answers == "predicted":
            sw["answer"] = "SAME" if kind == "NULL" else v.predicted(sw)
        elif isinstance(answers, list):
            sw["answer"] = answers[i]
        if sw["answer"]:
            sw["t_answer"] = sw["t"] + 3
        out.append(sw)
        level = nxt
    return out


def seconds(deep_fill=2000.0, shallow_fill=470.0, underruns=None, overflow=None):
    """A session of 60 settled seconds per arm plus a few mute and settling seconds."""
    secs = []
    s = 0
    for target, fill in ((CFG["deep"], deep_fill), (CFG["shallow"], shallow_fill)):
        secs.append({"s": s, "phase": 1, "target": target, "mute": True, "settling": False, "count": 4090, "fill": 0,
                     "underruns": 0, "overflow": 0}); s += 1
        secs.append({"s": s, "phase": 1, "target": target, "mute": False, "settling": True, "count": 4090,
                     "fill": fill - 300, "underruns": 0, "overflow": 0}); s += 1
        for k in range(60):
            secs.append({"s": s, "phase": 1, "target": target, "mute": False, "settling": False, "count": 4090,
                         "fill": fill + (k % 3) - 1, "underruns": 0, "overflow": 0}); s += 1
    # Phase 2 seconds at the DEEP level are NOT the DEEP arm, whatever they hold
    for k in range(5):
        secs.append({"s": s, "phase": 2, "target": CFG["deep"], "mute": False, "settling": False, "count": 3000,
                     "fill": 100.0, "underruns": 7, "overflow": 7}); s += 1
    if underruns:
        for target, n in underruns.items():
            [x for x in secs if x["target"] == target and not x["mute"]][5]["underruns"] = n
    if overflow:
        for target, n in overflow.items():
            [x for x in secs if x["target"] == target and not x["mute"]][6]["overflow"] = n
    return secs


def report(**kw):
    r = {"test_id": "GBP-AUDIO-012", "build_id": "sync-0001", "commit": "0000000", "cfg": copy.deepcopy(CFG),
         "assign": {"seed": 0x1234, "initial": "DEEP", "schedule": schedule(), "p2_starts": [1024, 2560, 640],
                    "p2_dirs": ["LEFT_DEEPER", "LEFT_SHALLOWER", "LEFT_DEEPER"]},
         "press": {"t_press": 500, "before_prompt": False},
         "phases": {"p1": {"t_start": 600, "t_end": 1200, "ended": "complete"},
                    "p2": {"t_start": 1200, "t_end": 1500, "ended": "complete"},
                    "p3": {"t_start": 1500, "t_end": 1700, "ended": "complete"}},
         "switches": switches("predicted"),
         "nulling": [{"seq": 0, "start": 1024, "direction": "LEFT_DEEPER", "steps": 4, "target": 512, "t": 1300},
                     {"seq": 1, "start": 2560, "direction": "LEFT_SHALLOWER", "steps": 15, "target": 640, "t": 1400},
                     {"seq": 2, "start": 640, "direction": "LEFT_DEEPER", "steps": 1, "target": 512, "t": 1450}],
         "descent": [{"target": t, "kind": "STEP", "fill_mean": t - 20.0, "underruns": 0, "overflow": 0, "dup": 60,
                      "drop": 0, "lost": 30} for t in (384, 352, 320, 288, 256, 224, 192, 160)] +
                    [{"target": 128, "kind": "STEP", "fill_mean": 110.0, "underruns": 3, "overflow": 0, "dup": 0,
                      "drop": 0, "lost": 30},
                     {"target": 144, "kind": "BISECT", "fill_mean": 126.0, "underruns": 1, "overflow": 0, "dup": 0,
                      "drop": 0, "lost": 30},
                     {"target": 152, "kind": "BISECT", "fill_mean": 133.0, "underruns": 0, "overflow": 0, "dup": 40,
                      "drop": 0, "lost": 30}],
         "seconds": seconds(),
         "counters": {"underruns": 4, "overflow": 0, "silences": 0, "mute_chunks": 320, "dup": 1000, "drop": 5}}
    r.update(kw)
    return r


class TheNumbersAreTheFrozenOnes(unittest.TestCase):
    def test_the_counts_and_the_probability(self):
        self.assertEqual((v.REAL, v.NULL, v.D_CONFIRMS, v.D_REFUTES, v.NULLS_CHANGE_MAX, v.P2_MIN_SETTINGS),
                         (12, 6, 10, 6, 3, 3))
        self.assertEqual(v.P_CONFIRMS, Fraction(79, 4096))
        self.assertEqual(sum(comb(12, k) for k in range(10, 13)), 79)             # P(D >= 10 | 12, 1/2) = 79 / 2^12
        self.assertEqual((v.M1_BELOW, v.M1_ABOVE, v.SEP_TOL, v.DUP_FLOOR_MODEL), (256, 16, 256, 145))

    def test_the_predicted_direction(self):
        self.assertEqual(v.predicted({"kind": "REAL", "from": 2048, "to": 512}), "LESS")
        self.assertEqual(v.predicted({"kind": "REAL", "from": 512, "to": 2048}), "MORE")
        self.assertIsNone(v.predicted({"kind": "NULL", "from": 2048, "to": 2048}))


class QuestionM(unittest.TestCase):
    def test_the_construction_passes_M1_M2_M3(self):
        m = v.question_M(report())
        self.assertEqual((m["M1"], m["M2"], m["M3"]), ("PASS", "PASS", "PASS"))
        self.assertEqual((m["arms"]["DEEP"]["settled_seconds"], m["arms"]["DEEP"]["live_seconds"]), (60, 61))
        self.assertAlmostEqual(m["arms"]["DEEP"]["fill_mean"], 2000.0, places=6)
        self.assertEqual(m["separation_band"], [1280, 1792])
        self.assertAlmostEqual(m["separation"], 1530.0, places=6)
        self.assertAlmostEqual(m["M4"]["DEEP"], 6.0, places=6)                    # 4 096 - 4 090 per live second

    def test_M1_fails_when_an_arm_sits_outside_its_band(self):
        m = v.question_M(report(seconds=seconds(deep_fill=1700.0)))               # 2048 - 348: below TARGET - 256
        self.assertEqual(m["M1"], "FAIL")
        self.assertFalse(m["arms"]["DEEP"]["fill_ok"])

    def test_M1_fails_when_the_arms_do_not_separate(self):
        m = v.question_M(report(seconds=seconds(deep_fill=2000.0, shallow_fill=800.0)))   # both in band? no:
        self.assertFalse(m["arms"]["SHALLOW"]["fill_ok"])                                   # 800 > 512 + 16
        m = v.question_M(report(seconds=seconds(deep_fill=1800.0, shallow_fill=525.0)))   # both in band, sep 1275
        self.assertTrue(m["arms"]["DEEP"]["fill_ok"] and m["arms"]["SHALLOW"]["fill_ok"])
        self.assertFalse(m["separation_ok"])
        self.assertEqual(m["M1"], "FAIL")

    def test_M2_M3_see_underruns_and_overflow_in_live_seconds_only(self):
        m = v.question_M(report(seconds=seconds(underruns={512: 2})))
        self.assertEqual((m["M2"], m["arms"]["SHALLOW"]["underruns"]), ("FAIL", 2))
        m = v.question_M(report(seconds=seconds(overflow={2048: 1})))
        self.assertEqual(m["M3"], "FAIL")
        secs = seconds()
        [x for x in secs if x["mute"]][0]["underruns"] = 9                        # a mute second's counter is not read
        self.assertEqual(v.question_M(report(seconds=secs))["M2"], "PASS")

    def test_phase_2_seconds_at_an_arms_level_are_not_the_arm(self):
        m = v.question_M(report())
        self.assertEqual((m["arms"]["DEEP"]["live_seconds"], m["arms"]["DEEP"]["underruns"], m["M2"]), (61, 0, "PASS"))
        secs = [dict(x, phase=1) for x in seconds()]                             # the same seconds counted as Phase 1
        m = v.question_M(report(seconds=secs))
        self.assertEqual((m["arms"]["DEEP"]["live_seconds"], m["M2"], m["M3"]), (66, "FAIL", "FAIL"))

    def test_an_arm_with_no_settled_second_fails_M1_rather_than_passing_vacuously(self):
        secs = [s for s in seconds() if s["target"] != 512]
        m = v.question_M(report(seconds=secs))
        self.assertIsNone(m["arms"]["SHALLOW"]["fill_mean"])
        self.assertEqual(m["M1"], "FAIL")


class Phase1(unittest.TestCase):
    def verdict(self, **kw):
        return v.evaluate(report(**kw))["phase1"]

    def test_every_real_switch_predicted_and_every_null_same_CONFIRMS(self):
        p = self.verdict()
        self.assertEqual((p["verdict"], p["D"], p["null_change"], p["answered"]), ("CONFIRMS", 12, 0, 18))

    def test_D_10_confirms_and_D_9_does_not(self):
        base = switches("predicted")
        reals = [i for i, s in enumerate(base) if s["kind"] == "REAL"]
        for wrong, want in ((2, "CONFIRMS"), (3, "UNRESOLVED")):
            sw = copy.deepcopy(base)
            for i in reals[:wrong]:
                sw[i]["answer"] = "SAME"
            p = self.verdict(switches=sw)
            self.assertEqual((p["verdict"], p["D"]), (want, 12 - wrong), wrong)

    def test_D_6_refutes_by_SAME_and_by_reversal(self):
        base = switches("predicted")
        reals = [i for i, s in enumerate(base) if s["kind"] == "REAL"]
        sw = copy.deepcopy(base)
        for i in reals[:6]:
            sw[i]["answer"] = "SAME"
        self.assertEqual((self.verdict(switches=sw)["verdict"], self.verdict(switches=sw)["D"]), ("REFUTES", 6))
        sw = copy.deepcopy(base)
        for i in reals:
            sw[i]["answer"] = "MORE" if sw[i]["answer"] == "LESS" else "LESS"    # every direction reversed
        self.assertEqual((self.verdict(switches=sw)["verdict"], self.verdict(switches=sw)["D"]), ("REFUTES", 0))

    def test_nulls_judged_a_change_4_of_6_is_INCONCLUSIVE_whatever_D(self):
        base = switches("predicted")
        nulls = [i for i, s in enumerate(base) if s["kind"] == "NULL"]
        sw = copy.deepcopy(base)
        for i in nulls[:3]:
            sw[i]["answer"] = "MORE"
        self.assertEqual(self.verdict(switches=sw)["verdict"], "CONFIRMS")          # 3 of 6: still allowed
        sw[nulls[3]]["answer"] = "LESS"
        p = self.verdict(switches=sw)
        self.assertEqual((p["verdict"], p["D"], p["null_change"]), ("INCONCLUSIVE", 12, 4))

    def test_an_unanswered_switch_is_INCONCLUSIVE_the_cap(self):
        sw = switches("predicted")
        sw[-1]["answer"], sw[-1]["t_answer"] = None, None
        p = self.verdict(switches=sw)
        self.assertEqual((p["verdict"], p["answered"]), ("INCONCLUSIVE", 17))
        self.assertIn("cap", p["why"])

    def test_the_INCONCLUSIVE_arms_in_precedence(self):
        r = report(assign=None)
        self.assertEqual(v.evaluate(r)["phase1"]["verdict"], "VOID")                 # t5
        r = report(press={"t_press": 100, "before_prompt": True})
        self.assertEqual(v.evaluate(r)["phase1"]["verdict"], "INCONCLUSIVE")         # t3
        self.assertIn("(t3)", v.evaluate(r)["phase1"]["why"])
        r = report(seconds=seconds(deep_fill=1700.0))
        self.assertIn("(t1)", v.evaluate(r)["phase1"]["why"])                        # t1 before t2
        r = report(seconds=seconds(underruns={2048: 1}))
        self.assertIn("(t2)", v.evaluate(r)["phase1"]["why"])
        bad = report()
        bad["assign"]["schedule"] = bad["assign"]["schedule"][:17]
        self.assertEqual(v.evaluate(bad)["phase1"]["verdict"], "VOID")

    def test_a_schedule_of_the_wrong_shape_is_VOID_even_when_18_long(self):
        r = report()
        r["switches"][0]["kind"] = "NULL"                                          # 11 real + 7 null
        r["switches"][0]["to"] = r["switches"][0]["from"]
        self.assertEqual(v.evaluate(r)["phase1"]["verdict"], "VOID")


class Phase2(unittest.TestCase):
    def test_three_settings_measure_and_two_do_not(self):
        p = v.evaluate(report())["phase2"]
        self.assertEqual((p["verdict"], p["settings"], p["min"], p["max"]), ("MEASURED", 3, 512, 640))
        self.assertAlmostEqual(p["mean_s"], (512 + 640 + 512) / 3.0 / 4096, places=9)
        r = report()
        r["nulling"] = r["nulling"][:2]
        self.assertEqual(v.evaluate(r)["phase2"]["verdict"], "INCONCLUSIVE")

    def test_the_floor_is_named_when_reached(self):
        r = report()
        r["nulling"][0]["target"] = 384
        p = v.evaluate(r)["phase2"]
        self.assertEqual(p["at_floor"], 1)
        self.assertIn("bounded below", p["why"])

    def test_M1_and_blinding_void_it(self):
        self.assertEqual(v.evaluate(report(assign=None))["phase2"]["verdict"], "VOID")
        self.assertEqual(v.evaluate(report(seconds=seconds(deep_fill=1700.0)))["phase2"]["verdict"], "INCONCLUSIVE")


class Phase3(unittest.TestCase):
    def test_the_bisection_measures_the_edge(self):
        p = v.evaluate(report())["phase3"]
        self.assertEqual((p["verdict"], p["interval"], p["width"], p["model_inside"]), ("MEASURED", [144, 152], 8, True))

    def test_a_descent_that_stops_at_the_step_only_brackets(self):
        r = report()
        r["descent"] = [d for d in r["descent"] if d["kind"] == "STEP"]
        p = v.evaluate(r)["phase3"]
        self.assertEqual((p["verdict"], p["interval"], p["width"]), ("BRACKETED", [128, 160], 32))

    def test_no_underrun_and_no_rows(self):
        r = report()
        r["descent"] = [d for d in r["descent"] if d["underruns"] == 0]
        self.assertEqual(v.evaluate(r)["phase3"]["verdict"], "NO UNDERRUN")
        r["descent"] = []
        self.assertEqual(v.evaluate(r)["phase3"]["verdict"], "NOT RUN")

    def test_the_model_outside_the_interval_is_said(self):
        r = report()
        for d in r["descent"]:
            d["underruns"] = 1 if d["target"] <= 192 else 0
        p = v.evaluate(r)["phase3"]
        self.assertEqual((p["interval"], p["model_inside"]), ([192, 224], False))
        self.assertIn("OUTSIDE", p["why"])


class ThePrintedVerdictCarriesEveryInput(unittest.TestCase):
    def test_every_gate_input_is_printed(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.json")
            with open(p, "w") as f:
                json.dump(report(), f)
            out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v27accept.py"), p],
                                 capture_output=True, text=True, timeout=60).stdout
        for tok in ("DEEP 2048  SHALLOW 512  FLOOR 384", "assignment present; press before prompt False",
                    "fill mean 2000.0  in [1792, 2064] True", "fill mean 470.0  in [256, 528] True",
                    "M1 PASS  separation 1530.0 in [1280, 1792] True;  M2 PASS;  M3 PASS", "lost 366 = 6.000/s",
                    "PHASE 1  CONFIRMS     switches 18 (real 12, null 6), answered 18, D 12, nulls judged a change 0, "
                    "P(confirm | chance 1/2) 79/4096",
                    "switch  0 REAL 2048 ->  512", "answer LESS predicted LESS", "answer SAME predicted None",
                    "PHASE 2  MEASURED     3 settings; null TARGET 512..640", "PHASE 3  MEASURED",
                    "the threshold lies in (144, 152], width 8; the model's 145 inside",
                    "BISECT target  144  fill 126.0  underruns 1"):
            self.assertIn(tok, out, tok)


if __name__ == "__main__":
    unittest.main()
