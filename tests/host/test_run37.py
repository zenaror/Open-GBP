"""tests/host/test_run37.py -- GitHub Issue #91: RUN 37 (GBP-AUDIO-005) ingested.

The three verdicts are RECOMPUTED, never quoted: the console's own log (versioned
byte for byte as captures/fixtures/hw-gamecube-gbp-2026-09-23-drain-0001-run37.log)
goes through the frozen tools/v19report.py and the frozen tools/v19drain.py, and
§V19.14.1 must be exactly what they print. The explanation that follows the
verdicts is checked for saying what the data does NOT establish, because this is
the result the next phase is built on.
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
import v19drain  # noqa: E402
import v19report  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
README = os.path.join(ROOT, "captures", "README.md")
FIXTURE = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-23-drain-0001-run37.log")
LOCAL_D2 = os.path.join(ROOT, "captures", "local", "GBP-AUDIO-005_drain-0001-run37-d2.bin")

LOG_SHA256 = "24e2e588eef1d79ff32dd922cf577861fa2295fd2d6e68f08bb2071aee6b7fa8"
D2_SHA256 = "77007cd74a06dc54e5114d01a41d2721679d5668a0c20022fe102c87ad4d65b8"


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def section():
    t = read(HW)
    i = t.index("\n### V19.14 ")
    j = t.index("\n## V20 ", i)
    return t[i:j]


def entry(eid):
    t = read(EV)
    i = t.index("\n### %s " % eid)
    j = t.find("\n### ", i + 1)
    return t[i:j] if j >= 0 else t[i:]


def verdicts():
    return v19drain.evaluate(v19report.build(read(FIXTURE)))


def ctl(which):
    t = read(FIXTURE)
    a = dict(re.findall(r"(\w+)=(\S*)", re.search(r"DRAINCTL which=%s (.*)" % which, t).group(1)))
    b = dict(re.findall(r"(\w+)=(\S*)", re.search(r"DRAINCTL2 which=%s (.*)" % which, t).group(1)))
    a.update(b)
    return {k: int(v) for k, v in a.items() if v.isdigit()}


class TheFixture(unittest.TestCase):
    def test_is_the_raw_log_byte_for_byte(self):
        with open(FIXTURE, "rb") as f:
            raw = f.read()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), LOG_SHA256)
        self.assertEqual(len(raw), 92486)
        for tok in ("test_id=GBP-AUDIO-005", "build_id=drain-0001", "commit=897ea6c", "lines=710 dropped=0 truncated=0"):
            self.assertIn(tok, raw.decode("utf-8", "replace"), tok)

    def test_the_d2_file_is_the_fill_pattern(self):
        if not os.path.exists(LOCAL_D2):
            self.skipTest("RUN 37's d2 file is not archived in this checkout (captures/local is ignored)")
        with open(LOCAL_D2, "rb") as f:
            raw = f.read()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), D2_SHA256)
        self.assertEqual(raw, b"\xa5" * 65536)


class TheVerdictsAreRecomputed(unittest.TestCase):
    def test_D1_pass_and_its_series(self):
        d1 = verdicts()["D1"]
        self.assertEqual(d1["verdict"], "PASS")
        self.assertEqual(len(d1["windows"]), 57)
        self.assertEqual((d1["worst"]["window"], d1["worst"]["read"]), (45, 4095))
        off = [(r["t_start_s"], r["read"]) for r in d1["windows"] if r["read"] != 4096]
        self.assertEqual(off, [(48.0, 4095), (49.0, 4097), (53.0, 4095), (54.0, 4097), (55.0, 4095), (56.0, 4097),
                               (59.0, 4095)])
        rep = v19report.build(read(FIXTURE))["phase_b"]
        self.assertEqual((rep["counter_total"], rep["timebase_total"]), (245757, 245757))
        self.assertEqual(rep["counts"][:3], [4094, 4096, 4096])

    def test_D2_one_hundred_blocks_lost_not_delayed(self):
        rep = v19report.build(read(FIXTURE))["phase_c"]
        d2 = verdicts()["D2"]
        self.assertEqual((d2["verdict"], d2["blocks_lost"], d2["ring_minimum_blocks"], d2["write_bytes"]),
                         ("MEASURED", 100, 200, 65536))
        self.assertEqual(rep["seconds_spanned"], [65, 65])
        self.assertEqual((rep["coverage_before"], rep["coverage_after"]), (1.0, 1.0))
        self.assertAlmostEqual(rep["write_us"], 24430.716, places=2)
        counts = v19report.per_second(v19report.records(read(FIXTURE)))
        self.assertEqual(counts[64:67], [4096, 3996, 4096])     # lost, not delayed: 66 does not catch up

    def test_A_sync_lost_at_0x20_and_no_recovery(self):
        a = verdicts()["A"]
        self.assertEqual((a["verdict"], a["recovery"]), ("SYNC-LOST", "NO-RECOVERY"))
        self.assertEqual([(s["n"], s["sync"], s["period_min"], s["period_max"]) for s in a["steps"]],
                         [(0x20, "SYNC-LOST", 4, 8)])
        rep = v19report.build(read(FIXTURE))["phase_a"]
        self.assertTrue(rep["control_before_phase"])
        self.assertEqual((rep["steps"][0]["period_count"], rep["steps"][0]["off"], rep["steps"][0]["wrong_len"]),
                         (1537, 1537, 0))

    def test_the_controls_and_the_recovery_window(self):
        c2, r = ctl("control2"), ctl("recovery")
        self.assertEqual((c2["periods"], c2["pmin"], c2["pmax"], c2["off"]), (63, 32, 32, 0))
        self.assertEqual((r["periods"], r["pmin"], r["pmax"], r["off"], r["edges"], r["crossings"], r["wrong_len"]),
                         (64, 18, 32, 1, 65, 130, 0))
        self.assertEqual(32 - r["pmin"], 14)

    def test_the_page_prints_exactly_what_the_tool_prints(self):
        with tempfile.TemporaryDirectory() as d:
            j = os.path.join(d, "r.json")
            subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v19report.py"), FIXTURE, "--json", j],
                           check=True, capture_output=True, timeout=60)
            out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v19drain.py"), j],
                                 check=True, capture_output=True, text=True, timeout=60).stdout.rstrip("\n")
        s = section()
        block = s[s.index("#### V19.14.1"):]
        block = block[block.index("```text\n") + 8:]
        block = block[:block.index("\n```")]
        self.assertEqual(block, out)


class TheRecordSaysWhatItIs(unittest.TestCase):
    def test_verdicts_first_then_explanation(self):
        s = section()
        self.assertLess(s.index("#### V19.14.1 The verdicts"), s.index("#### V19.14.3"))
        self.assertIn("The gates ran UNEDITED", plain(s))

    def test_what_it_does_not_establish(self):
        s = plain(section())
        for tok in ('a PASS is never "no loss"', "What D1 does not answer: the start-up cost itself",
                    "Lost, not delayed", "What D2 does not answer", "is STRUCTURAL, not a measurement",
                    "Nothing was voided", "The log does not record where in the window it fell",
                    "N = 0x100 and N = 0x400 did not run", "Why N = 0x20 reads 4–8 is UNKNOWN",
                    "So the runtime is designed around FULL 0x1000 AUDIO reads", "SD writes stay out of the drain",
                    "U-GBP-042 is ANSWERED for N = 0x20: no"):
            self.assertIn(tok, s, tok)

    def test_the_evidence_statuses(self):
        e19, e20, e21 = (plain(entry(i)) for i in ("GBP-HW-319", "GBP-HW-320", "GBP-HW-321"))
        self.assertIn("FACT (the measurement, one run); \"the prior deficit is a start-up cost\" is CORROBORATED, not FACT",
                      e19)
        self.assertIn("LOST and not delayed", e20)
        self.assertIn("FACT (the gate's result); the MECHANISM is UNKNOWN", e21)
        self.assertIn("is a HYPOTHESIS", e21)
        for i in ("GBP-HW-319", "GBP-HW-320", "GBP-HW-321"):
            self.assertEqual(len(re.findall(r"^### %s " % i, read(EV), re.M)), 1, i)

    def test_u_gbp_042_answered_for_the_smallest_n_only(self):
        u = read(UNK)
        h = re.search(r"^## U-GBP-042 .*$", u, re.M).group(0)
        self.assertIn("ANSWERED FOR N = 0x20 by RUN 37, Issue #91: NO", h)
        self.assertIn("0x100 and 0x400 untested", h)

    def test_the_fixture_is_listed(self):
        self.assertIn("hw-gamecube-gbp-2026-09-23-drain-0001-run37.log", read(README))


if __name__ == "__main__":
    unittest.main()
