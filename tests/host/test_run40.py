"""tests/host/test_run40.py -- GitHub Issue #107: RUN 40 (GBP-AUDIO-009, Run B, split-0001) ingested.

The verdicts are RECOMPUTED, never quoted. The console's own log and its version-2 trace sidecar, both
versioned byte for byte (captures/fixtures/hw-gamecube-gbp-2026-09-24-split-0001-run40.log and
-run40-trace.bin), go through the frozen tools/v24report.py and tools/v24accept.py (and the frozen
tools/v23floor.py, DESCRIPTIVE here). Every output sealed before either session read it is reproduced to its
hash, and §V24.10.9 must be exactly what the gate tool prints. The preconditions are checked in #107's order,
QUESTION S's figures are recomputed, and so are the two DESCRIPTIVE records of §V24.10.8: §V23.12's rule on
the totals, and what the floorless sample shows inside the sampled cycles. The record is checked for saying
what the run does NOT establish before any verdict, for its order, for its statuses, and for the Gecko pair.
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

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
README = os.path.join(ROOT, "captures", "README.md")
FX = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-24-split-0001-run40")
LOG, L2, TRACE = FX + ".log", FX + "-l2.bin", FX + "-trace.bin"

RAW = {LOG: ("e068ac044ca7a4412e3ff63c287d10c83a44152a183fbfb73f444f5941048171", 92195),
       L2: ("26286f0ad86138938771024ecff8d552cea3f8f01c7f03ef7fb0dd2021448541", 83724),
       TRACE: ("98e4b0f606ee46392bd9f85f0e1eb140bf0e6f1256f030e054b45e578f532302", 2505950)}
# the sealed outputs, hashed before either session read them (§V24.10.1)
SEALED = {"report": "8dbfdf16bae89abf1085322b763f09b769ece95fd8d929bc39bd7f3f9bf038fa",
          "verdicts": "4935e4f461183fb6c25e805680c294b6802613dbdb9e80df6936960c1dc304e7",
          "accept": "954c30cbe7569c5b212b047d8e1aeae1a3f7a5196a637ae24c40465266004b61",
          "floor": "ec814be22b390729bb7b08276e5033d5a23d8239d6200096defd801876892e35"}
TB = 40500000
T = TB / 4096.0


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def section():
    t = read(HW)
    i = t.index("\n### V24.10 ")
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


class Run(object):
    """Every output, computed once through the frozen tools' own entry points."""
    _done = None

    @classmethod
    def get(cls):
        if cls._done is None:
            with tempfile.TemporaryDirectory() as d:
                rj, aj, fj = (os.path.join(d, n) for n in ("report.json", "accept.json", "floor.json"))
                subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v24report.py"), LOG, TRACE,
                                "--json", rj], check=True, capture_output=True, timeout=300)
                out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v24accept.py"), rj, "--json", aj],
                                     check=True, capture_output=True, timeout=1200).stdout
                subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v23floor.py"), rj, "--json", fj],
                               check=True, capture_output=True, timeout=300)
                blobs = {}
                for k, p in (("report", rj), ("accept", aj), ("floor", fj)):
                    with open(p, "rb") as f:
                        blobs[k] = f.read()
            cls._done = {"blobs": blobs, "printed": out, "rep": json.loads(blobs["report"]),
                         "acc": json.loads(blobs["accept"]), "floor": json.loads(blobs["floor"])}
        return cls._done


class TheFixtures(unittest.TestCase):
    def test_the_raws_are_the_consoles_files_byte_for_byte(self):
        for path, (h, n) in RAW.items():
            with open(path, "rb") as f:
                raw = f.read()
            self.assertEqual((sha(raw), len(raw)), (h, n), path)
        log = read(LOG)
        for tok in ("test=GBP-AUDIO-009 app=gbp-audio-split build=split-0001 commit=d6dc4f8",
                    "lines=708 dropped=0 truncated=0",
                    "LIVESPLIT seed=9e3779b9 half=1018 full=1017 sample_every=8 sample=59006 sample_dropped=0",
                    "LIVETRACE2 dropped=0/0/0/0/0/0 calls=237493/2035/237493",
                    "LIVETRACESAVE open=0 write=0 close=0 bytes=2505950 status=saved",
                    "LIVEL2SAVE open=0 write=0 close=0 bytes=83724 status=saved",
                    "CONTROL semantic orig=92"):
            self.assertIn(tok, log, tok)

    def test_the_frozen_tools_reproduce_every_sealed_output_to_its_hash(self):
        r = Run.get()
        self.assertEqual(sha(r["blobs"]["report"]), SEALED["report"])
        self.assertEqual(sha(r["printed"]), SEALED["verdicts"])
        self.assertEqual(sha(r["blobs"]["accept"]), SEALED["accept"])
        self.assertEqual(sha(r["blobs"]["floor"]), SEALED["floor"])

    def test_the_page_prints_exactly_what_the_tool_prints(self):
        s = section()
        block = s[s.index("#### V24.10.9"):]
        block = block[block.index("```text\n") + 8:]
        block = block[:block.index("\n```")]
        self.assertEqual(block, Run.get()["printed"].decode("utf-8").rstrip("\n"))


class ThePreconditionsAndTheVerdict(unittest.TestCase):
    def test_1_the_arm_tags_agree(self):
        s = Run.get()["acc"]["S"]
        self.assertFalse(s["refused"])
        self.assertEqual(s["arms_checked_chunks"], 2035)
        self.assertEqual(Run.get()["rep"]["split"], {"half": 1018, "full": 1017, "seed": 0x9E3779B9})
        self.assertEqual(sum(Run.get()["rep"]["trace"]["dropped"].values()), 0)

    def test_2_the_observer_gate_holds(self):
        o = Run.get()["acc"]["observer"]
        self.assertTrue(o["sanity_ok"])
        self.assertAlmostEqual(o["mean_undrained"], 19.015625)
        self.assertEqual(o["frames"], 44)
        self.assertEqual((o["primary"]["max_total_per_cycle_ticks"], o["primary"]["max_single_write_ticks"]), (4336, 231))
        self.assertEqual(Run.get()["acc"]["P"]["counts"]["recorder"], 0)

    def test_3_the_variable_took(self):
        r = Run.get()["acc"]["S"]["stretch_ratio"]
        self.assertAlmostEqual(r["median"], 1025 / 1988.0)
        self.assertAlmostEqual(r["p90"], 1230 / 2869.0)
        self.assertLessEqual(max(r["median"], r["p90"]), 0.60)

    def test_4_question_S_is_CAUSE_and_large(self):
        s = Run.get()["acc"]["S"]
        self.assertEqual(s["verdict"], "CAUSE")
        self.assertEqual((s["arms"]["half"]["cycles"], s["arms"]["half"]["loss_gaps"]), (1015, 257))
        self.assertEqual((s["arms"]["full"]["cycles"], s["arms"]["full"]["loss_gaps"]), (1014, 752))
        self.assertAlmostEqual(s["ratio"], 0.3414, places=4)
        self.assertEqual([round(x, 3) for x in s["ci90"]], [0.306, 0.379])
        self.assertEqual(s["p"], 0.0)
        self.assertEqual(s["trials"], 20000)
        self.assertEqual(s["excluded_cycles"], {"no_production_step": 0, "two_chunks_steps": 1, "open_last_cycle": 1})
        self.assertEqual(s["losses_outside_analysed_cycles"], 4)

    def test_5_the_rest(self):
        a = Run.get()["acc"]
        self.assertEqual(a["P"]["counts"], {"recorder": 0, "isr": 0, "produce": 906, "flush_queue": 0,
                                            "process": 6, "neither": 101})
        self.assertEqual((a["K"]["verdict"], a["K"]["observed"], a["K"]["video_gaps"]), ("NOT COINCIDENT", 1, 44))
        self.assertEqual(a["confinement"], {"before": 13, "inside": 44, "after": 0})
        self.assertEqual(Run.get()["rep"]["sample"]["dropped"], 0)
        self.assertEqual(len(Run.get()["rep"]["sample"]["steps"]), 59006)


class TheDescriptiveRecords(unittest.TestCase):
    """§V24.10.8: each at its own status, neither borrowing the other's weight."""

    def test_V23_12_on_the_totals_is_unresolved_again(self):
        a, f = Run.get()["acc"], Run.get()["floor"]
        n = a["P"]["counts"]["neither"]
        h = sorted(b for b, c in a["P"]["gap_histogram_quarter_blocks"] for _ in range(c))
        n_lo, n_hi = sum(b * T for b in h[:n]), sum((b + 0.25) * T for b in h[len(h) - n:])
        s_lo, s_hi = f["sub_floor_total"]["time_ticks_min"], f["sub_floor_total"]["time_ticks_max"]
        self.assertEqual((n, round(n_lo), round(n_hi), s_lo, s_hi), (101, 1201355, 2246979, 1337026, 2249128))
        self.assertTrue(not n_lo > s_hi and not n_hi <= s_lo)          # the middle band: unresolved

    def test_inside_the_sampled_cycles_the_neither_gaps_hold_almost_no_chain_activity(self):
        rep = Run.get()["rep"]
        losses = v23accept.audio_losses(rep["audio"]["decoded"], rep["audio"]["ticks"])
        cands = []
        for s in rep["steps"]:
            cands.append((s[0], s[1]))
            if s[3] > s[1]:
                cands.append((s[1], s[3]))
        for e, x in rep["callbacks"]:
            cands.append((e, x))
        cands.sort()
        starts = [c[0] for c in cands]
        longest = max(c[1] - c[0] for c in cands)

        def touched(g0, g1):
            i = bisect.bisect_left(starts, g0 - longest)
            while i < len(cands) and cands[i][0] <= g1:
                if min(g1, cands[i][1]) > max(g0, cands[i][0]):
                    return True
                i += 1
            return False
        neither = [x for x in losses if not touched(x["g0"], x["g1"])]
        self.assertEqual(len(neither), 101)
        ent = [c[0] for c in rep["callbacks"]]
        samp = rep["sample"]["steps"]
        ss = [s[0] for s in samp]

        def coverage(g0, g1):
            i, tot = bisect.bisect_left(ss, g0 - 10000), 0
            while i < len(samp) and samp[i][0] <= g1:
                tot += max(0, min(g1, samp[i][1]) - max(g0, samp[i][0]))
                i += 1
            return tot / float(g1 - g0)
        sampled = [x for x in neither if bisect.bisect_right(ent, x["t"]) % 8 == 1]
        self.assertEqual(len(sampled), 12)
        self.assertTrue(all(coverage(x["g0"], x["g1"]) <= 0.002 for x in sampled))


class TheRecordSaysWhatItIs(unittest.TestCase):
    def test_what_it_does_not_establish_comes_before_any_verdict(self):
        s = section()
        self.assertLess(s.index("#### V24.10.0 What this run does NOT establish"), s.index("#### V24.10.3"))
        f = plain(s[:s.index("#### V24.10.3")])
        for tok in ("It is not a repair.", "Not Phase 6's closure. Not a real cartridge. Nothing about U-GBP-012.",
                    "K's resolution limit is untouched and cannot be addressed"):
            self.assertIn(tok, f, tok)

    def test_the_order_is_107s(self):
        s = section()
        idx = [s.index(h) for h in ("PRECONDITION 1 — the arm tags", "PRECONDITION 2 — the OBSERVER GATE",
                                    "PRECONDITION 3 — NEITHER", "#### V24.10.6 `QUESTION S`",
                                    "#### V24.10.7 Everything else", "#### V24.10.8 DESCRIPTIVE")]
        self.assertEqual(idx, sorted(idx))

    def test_the_descriptive_records_are_labelled_so(self):
        f = plain(section())
        for tok in ("an observation about those cycles, NOT a verdict about the run",
                    "an argument for pre-registering the question properly in a later run, not a decided result",
                    "the floor may account for it, unresolved at this resolution", "no side is taken",
                    "It is large, not a trifle"):
            self.assertIn(tok, f, tok)

    def test_the_gecko_pair_is_recorded_without_claiming_a_cause(self):
        f = plain(section())
        for tok in ("three channels", "Swiss's own boot text was confirmed arriving before the Operator pressed anything",
                    "RUN 39's capture was EMPTY", "RUN 40's is COMPLETE",
                    "it does not by itself establish what emptied RUN 39's", "nothing about the phases"):
            self.assertIn(tok, f, tok)

    def test_the_evidence_statuses(self):
        e = plain(entry("GBP-HW-332"))
        self.assertIn("FACT (the frozen gate's result on an interleaved, pair-balanced manipulation, one run)", e)
        self.assertIn("is CORROBORATED", e)
        self.assertIn("It is not a fix", e)
        e = plain(entry("GBP-HW-333"))
        self.assertIn("DESCRIPTIVE, 12 gaps in 1 cycle of 8, and decides nothing", e)
        self.assertIn("a HYPOTHESIS", e)
        for i in ("GBP-HW-332", "GBP-HW-333"):
            self.assertEqual(len(re.findall(r"^### %s " % i, read(EV), re.M)), 1, i)

    def test_the_unknown_is_rescoped_on_top(self):
        u = read(UNK)
        self.assertIn("Issue #107 (RUN 40)", re.search(r"^## U-GBP-045 .*$", u, re.M).group(0))
        self.assertIn("RESCOPED 2026-09-24 (GitHub Issue #107, RUN 40), on top; nothing above is rewritten.", u)

    def test_the_fixtures_are_listed(self):
        r = read(README)
        for s in (".log", "-l2.bin", "-trace.bin"):
            self.assertIn("hw-gamecube-gbp-2026-09-24-split-0001-run40%s" % s, r)


if __name__ == "__main__":
    unittest.main()
