"""tests/host/test_run39.py -- GitHub Issue #103: RUN 39 (GBP-AUDIO-008, Run A, trace-0001) ingested.

The verdicts are RECOMPUTED, never quoted. The console's own log and its trace sidecar, both
versioned byte for byte (captures/fixtures/hw-gamecube-gbp-2026-09-24-trace-0001-run39.log and
-run39-trace.bin), go through the frozen tools/v23report.py, tools/v23accept.py and tools/v23floor.py.
Every output sealed before either session read it is reproduced to its hash, §V23.13.9 must be exactly
what the gate tool prints, and the descriptive figures of §V23.13.8 are recomputed from the same
report. The record is checked for #103's order (the observer gate before P, P before K, K before the
floor rule), for saying what the run does NOT establish before any verdict, and for keeping the Gecko
gap stated, with the Operator's words apart from every hypothesis.
"""
import bisect
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v23accept  # noqa: E402
import v23floor  # noqa: E402
import v23report  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
README = os.path.join(ROOT, "captures", "README.md")
FX = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-24-trace-0001-run39")
LOG, L2, TRACE = FX + ".log", FX + "-l2.bin", FX + "-trace.bin"

RAW = {LOG: ("afc4a78f984b40bb49f20989420ed95789c5cfda47336fa71ad61e24ae85cc2e", 92076),
       L2: ("d70eb11c28d8e95fd5bbf2b958a807f2b43f07ba33cb1d55aea270a003883cc8", 83916),
       TRACE: ("4371dc13ce5741eb9e005cd2fa68cd0ddb7a4259d775b06199ea03ffdd6b184e", 1691756)}
# the sealed outputs, hashed before either session read them (§V23.13.1)
SEALED = {"report": "578272469f40fe3bced4a86262c7bbe6efd6b22a4f076dd230705fc3d082038c",
          "verdicts": "405c40033170309d4fc4ae9d21ae04c61f822f7d565294f7be403bfa5a08a38e",
          "accept": "40b22342abeaf13c7501497a0afb65669a40791101f55c9f6043d4eadabf056c",
          "floor": "ebdaaa6cc4f57f7340e9f35250a0cb75b38b3e53e2a8ed10bc1b34561a6bb661",
          "v2312": "9babd8096a493dcdc2d0ca830681c7536fab800861536a165d9fb91f44f0a5d8"}
TB = 40500000
T = TB / 4096.0


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def section():
    t = read(HW)
    i = t.index("\n### V23.13 ")
    j = t.find("\n### ", i + 1)
    j = t.find("\n## ", i + 1) if j < 0 else j
    return t[i:j] if j >= 0 else t[i:]


def entry(eid):
    t = read(EV)
    i = t.index("\n### %s " % eid)
    j = t.find("\n### ", i + 1)
    return t[i:j] if j >= 0 else t[i:]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def rule_v2312(acc, fl):
    """§V23.12 applied exactly as frozen: N bounded from P's gap histogram, S from tools/v23floor.py."""
    n = acc["P"]["counts"]["neither"]
    out = {"n": n, "n_floor_tool": fl["P"]["neither"], "T": T}
    if n != fl["P"]["neither"]:
        out["reading"] = "the two tools disagree on neither: the comparison is not made"
    elif n == 0:
        out["reading"] = "no gap went to neither; the comparison is not made"
    else:
        h = sorted(b for b, c in acc["P"]["gap_histogram_quarter_blocks"] for _ in range(c))
        n_lo = sum(b * T for b in h[:n])
        n_hi = sum((b + 0.25) * T for b in h[len(h) - n:])
        s_lo, s_hi = fl["sub_floor_total"]["time_ticks_min"], fl["sub_floor_total"]["time_ticks_max"]
        out.update(N_lo=n_lo, N_hi=n_hi, S_lo=s_lo, S_hi=s_hi)
        if n_lo > s_hi:
            out["reading"] = "the floor cannot account for neither"
        elif n_hi <= s_lo:
            out["reading"] = "the floor may account for it; totals cannot show that it did"
        else:
            out["reading"] = "the floor may account for it, unresolved at this resolution"
    return out


class Run(object):
    """Every output, computed once through the frozen tools' own entry points."""
    _done = None

    @classmethod
    def get(cls):
        if cls._done is None:
            with tempfile.TemporaryDirectory() as d:
                rj, fj = os.path.join(d, "report.json"), os.path.join(d, "floor.json")
                subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v23report.py"), LOG, TRACE,
                                "--json", rj], check=True, capture_output=True, timeout=120)
                out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v23accept.py"), rj],
                                     check=True, capture_output=True, timeout=600).stdout
                subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v23floor.py"), rj, "--json", fj],
                               check=True, capture_output=True, timeout=120)
                with open(rj, "rb") as f:
                    rep_bytes = f.read()
                with open(fj, "rb") as f:
                    floor_bytes = f.read()
            rep = json.loads(rep_bytes)
            acc = v23accept.evaluate(rep)
            fl = json.loads(floor_bytes)
            cls._done = {"rep_bytes": rep_bytes, "rep": rep, "printed": out, "acc": acc,
                         "acc_bytes": json.dumps(acc, sort_keys=True, default=list).encode(),
                         "floor_bytes": floor_bytes, "floor": fl}
            v = rule_v2312(acc, fl)
            cls._done["v2312"] = v
            cls._done["v2312_bytes"] = json.dumps(v, sort_keys=True).encode()
        return cls._done


class TheFixtures(unittest.TestCase):
    def test_the_raws_are_the_consoles_files_byte_for_byte(self):
        for path, (h, n) in RAW.items():
            with open(path, "rb") as f:
                raw = f.read()
            self.assertEqual((sha(raw), len(raw)), (h, n), path)
        log = read(LOG)
        for tok in ("test=GBP-AUDIO-008 app=gbp-audio-trace build=trace-0001 commit=c1beea1",
                    "lines=707 dropped=0 truncated=0",
                    "LIVETRACE a=260361 a_sat=0 v=167510 v_sat=4203 cb=2030 steps=18635 cycles=2031 cost_max=188 floor=200",
                    "LIVETRACE2 dropped=0/0/0/0/0/0 calls=239189/2035/239189",
                    "LIVETRACECLK reads=1024 gettime=0..4 transport=0..5",
                    "LIVETRACESAVE open=0 write=0 close=0 bytes=1691756 status=saved",
                    "LIVEL2SAVE open=0 write=0 close=0 bytes=83916 status=saved",
                    "CONTROL semantic orig=92"):
            self.assertIn(tok, log, tok)

    def test_the_frozen_tools_reproduce_every_sealed_output_to_its_hash(self):
        r = Run.get()
        self.assertEqual(sha(r["rep_bytes"]), SEALED["report"])
        self.assertEqual(sha(r["printed"]), SEALED["verdicts"])
        self.assertEqual(sha(r["acc_bytes"]), SEALED["accept"])
        self.assertEqual(sha(r["floor_bytes"]), SEALED["floor"])
        self.assertEqual(sha(r["v2312_bytes"]), SEALED["v2312"])

    def test_the_page_prints_exactly_what_the_tool_prints(self):
        s = section()
        block = s[s.index("#### V23.13.9"):]
        block = block[block.index("```text\n") + 8:]
        block = block[:block.index("\n```")]
        self.assertEqual(block, Run.get()["printed"].decode("utf-8").rstrip("\n"))


class TheVerdictsAreRecomputed(unittest.TestCase):
    def test_the_observer_gate_holds_and_the_recorder_is_light(self):
        o = Run.get()["acc"]["observer"]
        self.assertTrue(o["sanity_ok"])
        self.assertAlmostEqual(o["mean_undrained"], 27.859375)
        self.assertEqual((o["frames"], o["frames_max"]), (74, 86))
        p = o["primary"]
        self.assertEqual((p["cycles"], p["max_single_write_ticks"], p["max_total_per_cycle_ticks"]), (2030, 188, 2950))
        self.assertAlmostEqual(p["mean_total_per_cycle_ticks"], 2433.35, places=2)
        self.assertLess(p["mean_total_per_cycle_ticks"] / 1264500, 0.002)
        self.assertTrue(Run.get()["acc"]["transfers_to_run38"])

    def test_P_names_produce(self):
        a = Run.get()["acc"]
        self.assertEqual(a["P"]["counts"], {"recorder": 0, "isr": 1, "produce": 1279, "flush_queue": 0,
                                            "process": 0, "neither": 173})
        self.assertEqual(a["P"]["decision"], "P names `produce`")
        self.assertEqual((a["losses_located"], a["loss_gaps"], a["blocks_short_by_coverage"]), (1781, 1453, 1783))

    def test_K_is_not_coincident(self):
        k = Run.get()["acc"]["K"]
        self.assertEqual(k["verdict"], "NOT COINCIDENT")
        self.assertEqual((k["observed"], k["video_gaps"], k["trials"]), (2, 75, 20000))
        self.assertAlmostEqual(k["p_phase"], 0.98610)
        self.assertAlmostEqual(k["p_uniform"], 0.20470)

    def test_the_floor_rule_is_unresolved_and_takes_no_side(self):
        r = Run.get()
        v, fl = r["v2312"], r["floor"]
        self.assertEqual(v["reading"], "the floor may account for it, unresolved at this resolution")
        self.assertEqual((v["n"], v["S_lo"], v["S_hi"]), (173, 1276906, 2282798))
        self.assertEqual((round(v["N_lo"]), round(v["N_hi"])), (2133270, 3848785))
        self.assertEqual(fl["step_dropped"], 0)
        self.assertEqual(fl["sub_floor_total"]["count_min"], fl["sub_floor_total"]["count_max"])
        self.assertEqual(fl["sub_floor_total"]["count_max"], 461778)

    def test_f_the_incomplete_frames_and_where_they_fall(self):
        r = Run.get()
        self.assertEqual(r["acc"]["confinement"], {"before": 14, "inside": 74, "after": 0})
        self.assertEqual(r["rep"]["window"]["framecap_session"], 88)
        rep = r["rep"]
        gaps, _an = v23accept.video_gaps(rep["video"]["ticks"], rep["video"]["start"])
        v0, ai0 = rep["video"]["ticks"][0], rep["ai_span"][0]
        press = int(re.search(r"t_press=([0-9a-f]+)", read(LOG)).group(1), 16)
        self.assertAlmostEqual((press - v0) / TB, 5.662, places=3)
        self.assertTrue(all((g["t"] - v0) / TB < 2.64 or abs(g["t"] - press) / TB < 0.02
                            for g in gaps if g["t"] < ai0))


class TheDescriptiveFiguresAreRecomputed(unittest.TestCase):
    """§V23.13.8 and the K limitation: computed after the seal was opened, deciding nothing, and still
    recomputed here so the page cannot drift from the data."""

    @classmethod
    def setUpClass(cls):
        rep = Run.get()["rep"]
        at, dec = rep["audio"]["ticks"], rep["audio"]["decoded"]
        cls.losses = v23accept.audio_losses(dec, at)
        cls.lossg = set((x["g0"], x["g1"]) for x in cls.losses)
        cls.prod = [s for s in rep["steps"] if s[2] == "produce"]
        cls.ps = [s[0] for s in cls.prod]
        cls.ent = sorted(c[0] for c in rep["callbacks"])
        cls.at = at
        cls.rep = rep

    def phase(self, t):
        c = bisect.bisect_right(self.ent, t) - 1
        return None if c < 0 or c >= len(self.ent) - 1 else (t - self.ent[c]) / float(self.ent[c + 1] - self.ent[c])

    def overlaps(self, g0, g1):
        i = bisect.bisect_left(self.ps, g0 - 200000)
        while i < len(self.prod) and self.prod[i][0] <= g1:
            if min(g1, self.prod[i][1]) > max(g0, self.prod[i][0]):
                return True
            i += 1
        return False

    def test_the_losses_and_production_sit_in_the_first_tenth_of_the_cycle(self):
        lp = [self.phase(x["t"]) for x in self.losses]
        lp = [p for p in lp if p is not None]
        self.assertEqual((len(lp), sum(1 for p in lp if p < 0.1)), (1450, 1307))
        pp = [self.phase(s[0]) for s in self.prod]
        pp = [p for p in pp if p is not None]
        self.assertEqual((len(pp), sum(1 for p in pp if p < 0.1)), (16240, 16097))

    def test_in_that_phase_a_long_gap_holds_production_whether_or_not_a_block_was_lost(self):
        loss, other_long = [0, 0], [0, 0]
        for i in range(len(self.at) - 1):
            g0, g1 = self.at[i], self.at[i + 1]
            ph = self.phase(g1)
            if ph is None or ph >= 0.1:
                continue
            if (g0, g1) in self.lossg:
                loss[0] += self.overlaps(g0, g1)
                loss[1] += 1
            elif (g1 - g0) / T >= 1.25:
                other_long[0] += self.overlaps(g0, g1)
                other_long[1] += 1
        self.assertEqual(loss, [1253, 1307])                     # 95.9 %
        self.assertEqual(other_long, [2441, 2520])               # 96.9 %

    def test_the_video_step_is_coarser_than_the_frozen_window(self):
        vt, vs = self.rep["video"]["ticks"], self.rep["video"]["start"]
        d = sorted(vt[i + 1] - vt[i] for i in range(len(vt) - 1) if not vs[i + 1])
        self.assertEqual(d[len(d) // 2], 11212)
        self.assertGreater(d[len(d) // 2], Run.get()["acc"]["K"]["within_ticks"])
        dist = [x / T for x in Run.get()["acc"]["K"]["distances_ticks"]]
        self.assertEqual(sum(1 for x in dist if 1.0 < x <= 1.35), 19)
        vc = Run.get()["acc"]["video_confidence"]
        self.assertEqual(sum(1 for c in vc if c is not None and c < 1.2), 61)


class TheRecordSaysWhatItIs(unittest.TestCase):
    def test_what_it_does_not_establish_comes_before_any_verdict(self):
        s = section()
        first = min(s.index("#### V23.13.3"), s.index("#### V23.13.4"), s.index("#### V23.13.5"))
        self.assertLess(s.index("#### V23.13.0 What this run does NOT establish"), first)
        f = plain(s[:first])
        for tok in ("Not a fix. Not Phase 6's closure. Not a real cartridge. Nothing about U-GBP-012.",
                    "Run B is not designed here"):
            self.assertIn(tok, f, tok)

    def test_the_order_is_103s_observer_then_P_then_K_then_the_floor(self):
        s = section()
        idx = [s.index(h) for h in ("#### V23.13.3 The OBSERVER GATE", "#### V23.13.4 `QUESTION P`",
                                    "#### V23.13.5 `QUESTION K`", "#### V23.13.6 §V23.12's floor rule")]
        self.assertEqual(idx, sorted(idx))

    def test_the_gecko_gap_is_stated_and_nothing_is_promoted(self):
        f = plain(section())
        for tok in ("two independent channels", "o gecko estava conectado... mas pode ser que ele sofreu algum mal contado",
                    "OPERATOR OBSERVATION", "His HYPOTHESIS", "NOT established for RUN 39",
                    "a silent capture is uninformative, never negative", "cannot report a hangup"):
            self.assertIn(tok, f, tok)

    def test_the_floor_and_K_readings_take_no_side(self):
        f = plain(section())
        self.assertIn("No side is taken", f)
        self.assertIn("The verdict stands as frozen: NOT COINCIDENT at one AUDIO block", f)
        self.assertIn("This run's records do not separate the two", f)

    def test_the_evidence_statuses(self):
        self.assertIn("FACT (the counts and the frozen gate's result, one run)", plain(entry("GBP-HW-328")))
        e = plain(entry("GBP-HW-329"))
        self.assertIn("that production CAUSES the losses is a HYPOTHESIS", e)
        self.assertIn("This run does not separate the two", e)
        self.assertIn("one event at the VIDEO resolution is NOT decided", plain(entry("GBP-HW-330")))
        self.assertIn("CORROBORATED (same count, same frame positions)", plain(entry("GBP-HW-331")))
        for i in ("GBP-HW-328", "GBP-HW-329", "GBP-HW-330", "GBP-HW-331"):
            self.assertEqual(len(re.findall(r"^### %s " % i, read(EV), re.M)), 1, i)

    def test_the_unknown_is_rescoped_on_top(self):
        u = read(UNK)
        h = re.search(r"^## U-GBP-045 .*$", u, re.M).group(0)
        self.assertIn("Issue #103 (RUN 39)", h)
        self.assertIn("RESCOPED 2026-09-24 (GitHub Issue #103, RUN 39), on top; nothing above is rewritten.", u)

    def test_the_fixtures_are_listed(self):
        r = read(README)
        for s in (".log", "-l2.bin", "-trace.bin"):
            self.assertIn("hw-gamecube-gbp-2026-09-24-trace-0001-run39%s" % s, r)


if __name__ == "__main__":
    unittest.main()
