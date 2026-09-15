"""
GBP-INIT-003A fixture round trip on SYNTHETIC data.

No physical GBP-INIT-003A log exists (the experiment has not been executed
on hardware). This test proves the tooling path that a physical log will
take: the host mock run (tests/unit/test_gbp_initirqa.c --dump-log) is
written in the SD-log format, tools/probelog.py turns it into a replay
script (clearly marked SYNTHETIC), and the probe logic run on that script
reaches the same result as the mock run — every time-base read answered
by the fixture, nothing invented. The generated files stay under build/
and are never placed under captures/fixtures/.
"""
import glob
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import probelog  # noqa: E402

BIN = os.path.join(ROOT, "build", "tests", "unit", "test_gbp_initirqa")
OUTDIR = os.path.join(ROOT, "build", "tests", "unit")
NOTE = "SYNTHETIC: generated from the host mock (tests/unit/test_gbp_initirqa.c --dump-log); NOT physical data"


@unittest.skipUnless(os.path.isfile(BIN), "run `make -C tests/unit` to build the test binary")
class InitirqaRoundTrip(unittest.TestCase):
    def test_mock_log_replays_to_the_same_result(self):
        outdir = OUTDIR if os.path.isdir(OUTDIR) else tempfile.mkdtemp()
        log = os.path.join(outdir, "initirqa-synthetic.log")
        fx = os.path.join(outdir, "initirqa-synthetic.gbpreplay")
        run1 = subprocess.run([BIN, "--dump-log", log], capture_output=True, text=True)
        self.assertEqual(run1.returncode, 0, run1.stdout + run1.stderr)
        summary_mock = [l for l in run1.stdout.splitlines() if l.startswith("SUMMARY ")]
        self.assertEqual(len(summary_mock), 1)
        header, records = probelog.parse_file(log)
        self.assertEqual(header["test_id"], "GBP-INIT-003A")
        self.assertEqual(header["source"], "host-mock")
        kinds = {r["kind"] for r in records}
        for k in ("INITIRQA", "IRQSHAPE", "CTLW", "IRQW", "SNAP", "WINDOW", "REGION", "TEARDOWN", "IRQSTOP", "CLEANUP", "RESTORE"):
            self.assertIn(k, kinds)
        irqw = [r for r in records if r["kind"] == "IRQW"]
        self.assertEqual([r["fields"]["tag"] for r in irqw], ["A1", "A2", "STOP"])
        self.assertTrue(all(r["fields"]["layout"] == "gbi-u16-replicated" for r in irqw))
        self.assertEqual(irqw[1]["fields"]["data"], "00" * 32)
        event = [r for r in records if r["kind"] == "SNAP" and r["fields"]["tag"] == "EVENT"]
        self.assertEqual(len(event), 1)
        region = [r for r in records if r["kind"] == "REGION"][0]
        self.assertEqual(region["fields"]["formatted_inside"], "0")
        # fixture, marked synthetic
        self.assertEqual(probelog.main(["fixture", log, fx, "--note", NOTE]), 0)
        with open(fx, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("# SYNTHETIC", text)
        self.assertIn("P p ", text)
        self.assertEqual(text.count("W 01d00000 ok"), 3)
        # replay
        run2 = subprocess.run([BIN, "--replay", fx], capture_output=True, text=True)
        self.assertEqual(run2.returncode, 0, run2.stdout + run2.stderr)
        summary_replay = [l for l in run2.stdout.splitlines() if l.startswith("SUMMARY ")]
        self.assertEqual(len(summary_replay), 1)
        strip = lambda s: re.sub(r" a1_polls=\d+ a2_polls=\d+", "", s)   # the deadline loops poll once per sample in a replay
        self.assertEqual(strip(summary_mock[0]), strip(summary_replay[0]))
        self.assertIn("status=ok_pi_cause_observed", summary_replay[0])
        self.assertIn("event=1 ended_early=1", summary_replay[0])
        m = re.search(r"REPLAY step=(\d+) exhausted=(\d+) mismatches=(\d+) tick_polls=(\d+) timeline=(\d+)", run2.stdout)
        self.assertIsNotNone(m, run2.stdout)
        self.assertEqual((m.group(2), m.group(3), m.group(4), m.group(5)), ("0", "0", "0", "1"))
        # never a fixture under captures/
        self.assertEqual(glob.glob(os.path.join(ROOT, "captures", "fixtures", "*initirqa*")), [])
        self.assertEqual(glob.glob(os.path.join(ROOT, "captures", "fixtures", "*003a*")), [])


if __name__ == "__main__":
    unittest.main()
