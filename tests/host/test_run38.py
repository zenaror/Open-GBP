"""tests/host/test_run38.py -- GitHub Issue #99: RUN 38 (GBP-AUDIO-007, Phase 6's acceptance) ingested.

The verdicts are RECOMPUTED, never quoted. The console's own log and its L2 record,
both versioned byte for byte (captures/fixtures/hw-gamecube-gbp-2026-09-24-live-0001-run38.log
and -run38-l2.bin), go through the frozen tools/v22report.py and the frozen
tools/v22accept.py, and §V22.12.2 must be exactly what they print. The explanation
that follows the verdicts is checked for saying what the data does NOT establish,
and for recording the Operator's exposed answer as the Orchestrator set it down.
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v22accept  # noqa: E402
import v22report  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
README = os.path.join(ROOT, "captures", "README.md")
FX = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-24-live-0001-run38")
LOG, SIDE = FX + ".log", FX + "-l2.bin"

LOG_SHA256 = "05dc5b5ad8e4b5f7e8206efa715fc84cba591ba31ea9e677878fc5c2cd443b18"
SIDE_SHA256 = "e5b66cf618cf0b8b63147431bc5c7e995f8a4607a8697833fe6bec8a17e3d9d3"
# the sealed outputs, hashed before either session read them (§V22.12.1)
REPORT_SHA256 = "4198339161d02bdb7841c9bd12782859507a8b780304eadcace5eea363742179"
PRINTED_SHA256 = "12fee5d3113328ca10c768ffd024a759ace07483820eb2467b4687bb9951693a"


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def section():
    t = read(HW)
    i = t.index("\n### V22.12 ")
    j = t.find("\n### ", i + 1)
    j = t.find("\n## ", i + 1) if j < 0 else j
    return t[i:j] if j >= 0 else t[i:]


def entry(eid):
    t = read(EV)
    i = t.index("\n### %s " % eid)
    j = t.find("\n### ", i + 1)
    return t[i:j] if j >= 0 else t[i:]


def report():
    return v22report.build(read(LOG), SIDE)


def verdicts():
    with open(SIDE, "rb") as f:
        return v22accept.evaluate(report(), f.read())


def tools_output():
    with tempfile.TemporaryDirectory() as d:
        j = os.path.join(d, "r.json")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v22report.py"), LOG, "--sidecar", SIDE,
                        "--json", j], check=True, capture_output=True, timeout=60)
        with open(j, "rb") as f:
            rep = f.read()
        out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v22accept.py"), j, SIDE],
                             check=True, capture_output=True, timeout=120).stdout
    return rep, out


class TheFixtures(unittest.TestCase):
    def test_the_log_is_the_raw_log_byte_for_byte(self):
        with open(LOG, "rb") as f:
            raw = f.read()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), LOG_SHA256)
        self.assertEqual(len(raw), 91726)
        for tok in ("test_id=GBP-AUDIO-007", "build_id=live-0001", "commit=9341ca7", "lines=703 dropped=0 truncated=0"):
            self.assertIn(tok, raw.decode("utf-8", "replace"), tok)

    def test_the_l2_record_is_present_and_is_the_raw_file(self):
        with open(SIDE, "rb") as f:
            raw = f.read()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SIDE_SHA256)
        self.assertEqual(len(raw), 83916)
        self.assertIn("LIVEL2SAVE open=0 write=0 close=0 bytes=83916 status=saved", read(LOG))
        self.assertEqual(report()["l2_sidecar"], "present")          # §V22.9 A1: PRESENT, so L2 is decidable

    def test_the_tools_reproduce_the_sealed_outputs_byte_for_byte(self):
        rep, out = tools_output()
        self.assertEqual(hashlib.sha256(rep).hexdigest(), REPORT_SHA256)
        self.assertEqual(hashlib.sha256(out).hexdigest(), PRINTED_SHA256)


class TheVerdictsAreRecomputed(unittest.TestCase):
    def test_L_inconclusive_by_the_drain_arm(self):
        v, r = verdicts(), report()
        self.assertEqual(v["L"]["verdict"], "INCONCLUSIVE")
        self.assertIn("a drain result, not a playback one", v["L"]["why"])
        self.assertEqual((r["control"]["periods"], r["control"]["pmin"], r["control"]["pmax"]), (61, 32, 32))
        self.assertEqual((r["presses"]["a"], r["presses"]["other"]), (1, 0))
        cov = r["window"]["coverage"]
        self.assertEqual((len(cov), min(cov), max(cov), sum(cov)), (64, 4060, 4081, 260518))
        self.assertTrue(all(c < 0.999 * 4096 for c in cov))
        self.assertEqual(r["window"]["not_drained"], 1626)
        self.assertEqual(r["window"]["l"], {"periods": 8191, "pmin": 29, "pmax": 32})

    def test_the_losses_are_small_and_many(self):
        gap = int(re.search(r"LIVET2 .*gap_max=(\d+)", read(LOG)).group(1))
        self.assertEqual(gap, 21757)
        self.assertLess(gap / 40.5e6, 2.3 / 4096)                    # 0.537 ms: 2.2 block periods
        self.assertIn("FRAMECAP frames=4232 complete=4150 incomplete=82 resync=164", read(LOG))

    def test_L2_pass_exactly(self):
        v = verdicts()
        self.assertEqual(v["L2"]["verdict"], "PASS")
        self.assertIn("3b453778", v["L2"]["why"])
        self.assertIn("320 chunks x 1000 frames", v["L2"]["why"])
        self.assertEqual(v["L2"]["silence_fraction"], 0.0)

    def test_C_pass_and_not_no_loss(self):
        v, r = verdicts(), report()
        self.assertEqual(v["C"]["verdict"], "PASS")
        self.assertEqual((r["window"]["overflow"], r["window"]["underrun"]), (0, 0))
        self.assertEqual(r["window"]["corrections"], {"dup": 1965, "drop": 0})
        self.assertIn("it is NOT a claim of no loss", v["C"]["why"])
        fill = r["window"]["fill"]
        self.assertEqual((min(fill[1:]), max(fill), fill[1], fill[-1]), (1808, 2001, 1889, 2001))
        self.assertIn("silences=0", read(LOG))

    def test_M_corroborates_dolphins_model(self):
        v = verdicts()
        m = v["M"]
        self.assertAlmostEqual(m["rate_hz"], 32028.483, places=3)
        self.assertEqual(m["callbacks"], 2030)
        self.assertLess(abs(m["ppm_vs_dolphin_model"]), 0.5)
        self.assertAlmostEqual(m["ppm_vs_nominal"], 890.1, places=1)
        k = v["corrections"]
        self.assertAlmostEqual(k["observed_net_dup_per_s"], 30.703, places=3)
        self.assertAlmostEqual(k["predicted_by_dolphin_model"], 29.050, places=3)
        self.assertAlmostEqual(k["predicted_by_measured_ai"], 29.052, places=3)
        # §V22.4's frozen figure was ~3.7/s from RUN 37's drain; the observed rate is ~8x it
        self.assertGreater(k["observed_net_dup_per_s"] / 3.695, 8.0)

    def test_the_page_prints_exactly_what_the_tool_prints(self):
        _rep, out = tools_output()
        s = section()
        block = s[s.index("#### V22.12.2"):]
        block = block[block.index("```text\n") + 8:]
        block = block[:block.index("\n```")]
        self.assertEqual(block, out.decode("utf-8").rstrip("\n"))


class TheRecordSaysWhatItIs(unittest.TestCase):
    def test_what_it_does_not_establish_comes_before_the_verdicts(self):
        s = section()
        self.assertLess(s.index("#### V22.12.0 What this run does NOT establish"), s.index("#### V22.12.2 The verdicts"))
        f = plain(s[:s.index("#### V22.12.2")])
        for tok in ("Not GB/GBC", "Not a real game's audio", "Not latency, not synchronisation with video, not mixing",
                    "U-GBP-012's layout half stays open"):
            self.assertIn(tok, f, tok)

    def test_the_exposure_paragraph_is_verbatim_and_his_words_are_kept_apart(self):
        s = section()
        para = ("The Operator's corroboration for RUN 38 was EXPOSED before it was given. The\n"
                "Orchestrator published underruns=0, overflow=0, drop=0 and l=8191/29..32 to him,\n"
                "in a summary, before putting §V22.6's two questions. His answer is recorded with\n"
                "that fact beside it and carries no independent weight on \"continuous or broken\".")
        self.assertIn(para, s)
        self.assertIn(para, entry("GBP-HW-326"))
        f = plain(s)
        for tok in ("ouvi o tom", "um pouco \"vibrando\"", "2026-09-24T11:47:10.357Z",
                    "survives the exposure", "His attribution, his speaker or the volume, is his HYPOTHESIS",
                    "fits neither of §V22.6's two categories"):
            self.assertIn(tok, f, tok)

    def test_the_limitation_found_by_data_is_recorded_not_repaired(self):
        f = plain(section())
        for tok in ("M says the clock model is right", "§V22.4 stands as written, with this beside it",
                    "The reading assumed that the composed image drains at drain-0001's rate",
                    "No gate FAILED. One gate did not PASS", "this section does not make it"):
            self.assertIn(tok, f, tok)

    def test_the_evidence_statuses(self):
        self.assertIn("FACT (the counts and the gate's result, one run); that the chain's added work costs the drain "
                      "is a HYPOTHESIS", plain(entry("GBP-HW-322")))
        self.assertIn("FACT (the gate's result, one run)", plain(entry("GBP-HW-323")))
        self.assertIn('a PASS is not "no loss"', plain(entry("GBP-HW-324")))
        self.assertIn("it CORROBORATES Dolphin's model", plain(entry("GBP-HW-325")))
        self.assertIn("OPERATOR OBSERVATION, EXPOSED", plain(entry("GBP-HW-326")))
        for i in ("GBP-HW-322", "GBP-HW-323", "GBP-HW-324", "GBP-HW-325", "GBP-HW-326"):
            self.assertEqual(len(re.findall(r"^### %s " % i, read(EV), re.M)), 1, i)

    def test_the_new_unknown(self):
        h = re.search(r"^## U-GBP-045 .*$", read(UNK), re.M).group(0)
        self.assertIn("P1", h)
        self.assertIn("vibrando", h)

    def test_the_fixtures_are_listed(self):
        r = read(README)
        self.assertIn("hw-gamecube-gbp-2026-09-24-live-0001-run38.log", r)
        self.assertIn("hw-gamecube-gbp-2026-09-24-live-0001-run38-l2.bin", r)


if __name__ == "__main__":
    unittest.main()
