"""
GBP-INIT-003B fixture round trip on SYNTHETIC data, and the physical
GBP-INIT-003A fixture as the real prefix of the 003B logic.

No physical GBP-INIT-003B run exists (the experiment is implemented, not
executed), so no fixture of it exists either and none is invented: the
host mock run (tests/unit/test_gbp_initirqb.c --dump-log) is written in the
SD-log format, tools/probelog.py turns it into a replay script (clearly
marked SYNTHETIC), and the probe logic run on that script reaches the same
result as the mock run — every time-base read, PI read, interrupt-path
operation and the handler record answered by the fixture, nothing invented.
The generated files stay under build/ and are never placed under
captures/fixtures/. The physical 003A fixture (2026-09-15) drives the 003B
probe verbatim up to its EVENT and, having no interrupt path, stops at the
handler install with the 003A teardown.
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

BIN = os.path.join(ROOT, "build", "tests", "unit", "test_gbp_initirqb")
OUTDIR = os.path.join(ROOT, "build", "tests", "unit")
NOTE = "SYNTHETIC: generated from the host mock (tests/unit/test_gbp_initirqb.c --dump-log); NOT physical data"
PHYSICAL_003A = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-15-initirqa-0001.gbpreplay")


@unittest.skipUnless(os.path.isfile(BIN), "run `make -C tests/unit` to build the test binary")
class InitirqbRoundTrip(unittest.TestCase):
    def test_mock_log_replays_to_the_same_result(self):
        outdir = OUTDIR if os.path.isdir(OUTDIR) else tempfile.mkdtemp()
        log = os.path.join(outdir, "initirqb-synthetic.log")
        fx = os.path.join(outdir, "initirqb-synthetic.gbpreplay")
        run1 = subprocess.run([BIN, "--dump-log", log], capture_output=True, text=True)
        self.assertEqual(run1.returncode, 0, run1.stdout + run1.stderr)
        summary_mock = [l for l in run1.stdout.splitlines() if l.startswith("SUMMARY ")]
        self.assertEqual(len(summary_mock), 1)
        with open(log, encoding="utf-8") as f:
            self.assertIn("# SYNTHETIC", f.read(400))
        header, records = probelog.parse_file(log)
        self.assertEqual(header["test_id"], "GBP-INIT-003B")
        self.assertEqual(header["source"], "host-mock")
        kinds = {r["kind"] for r in records}
        for k in ("INITIRQB", "INITIRQA", "IRQSHAPE", "CTLW", "IRQW", "SNAP", "WINDOW", "REGION", "CAUSE", "IRQ", "PREUNMASK",
                  "UNMASK", "WAIT", "HANDLER", "HANDLERPI", "HANDLERPI2", "DELIVERY", "PREACK", "ACK", "POSTACK",
                  "MAINPICLEANUP", "TEARDOWN", "IRQSTOP", "CLEANUP", "MASK", "RESTORE", "ACKS", "RESTOREB"):
            self.assertIn(k, kinds)
        irqw = [r for r in records if r["kind"] == "IRQW"]
        self.assertEqual([r["fields"]["tag"] for r in irqw], ["A1", "A2", "ACK", "STOP"])
        self.assertTrue(all(r["fields"]["layout"] == "gbi-u16-replicated" for r in irqw))
        self.assertEqual(irqw[2]["fields"]["write"], "8400")             # device ACK = read (0400) | 0x8000
        self.assertEqual(irqw[2]["fields"]["data"], "8400" * 16)
        region = [r for r in records if r["kind"] == "REGION"][0]
        self.assertEqual(region["fields"]["formatted_inside"], "0")
        install = [r for r in records if r["kind"] == "IRQ" and r["tag"] == "install"]
        self.assertEqual(len(install), 1)
        unmask = [r for r in records if r["kind"] == "UNMASK"]
        self.assertEqual(len(unmask), 1)
        # the install follows the EVENT (point B), the unmask follows the PREUNMASK check
        idx = {k: i for i, k in enumerate(
            [(r["kind"], r["fields"].get("tag")) for r in records])}
        order = [("SNAP", "EVENT"), ("CAUSE", None), ("IRQ", None), ("SNAP", "PREUNMASK"), ("PREUNMASK", None),
                 ("UNMASK", None), ("WAIT", None), ("HANDLER", None), ("DELIVERY", None), ("SNAP", "PREACK"),
                 ("IRQW", "ACK"), ("SNAP", "POSTACK"), ("MAINPICLEANUP", None), ("CTLW", "RESTORE"), ("IRQW", "STOP"),
                 ("PI", "CLEANUPCHK"), ("MASK", None), ("SNAP", "FINAL"), ("INITIRQB", None)]
        first = {}
        for i, r in enumerate(records):
            key = (r["kind"], r["fields"].get("tag"))
            first.setdefault(key, i)
            first.setdefault((r["kind"], None), i)
        positions = [first[k] if k in first else first[(k[0], None)] for k in order]
        # INITIRQB start precedes everything; use the "end" record for the last position
        positions[-1] = max(i for i, r in enumerate(records) if r["kind"] == "INITIRQB")
        self.assertEqual(positions, sorted(positions), list(zip(order, positions)))
        # fixture, marked synthetic
        self.assertEqual(probelog.main(["fixture", log, fx, "--note", NOTE]), 0)
        with open(fx, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("# SYNTHETIC", text)
        self.assertIn("P p ", text)
        self.assertEqual(text.count("W 01d00000 ok"), 4)
        self.assertEqual(text.count("I i null"), 1)
        self.assertEqual(text.count("I r"), 1)
        i_u = [l for l in text.splitlines() if l.startswith("I u ")]
        self.assertEqual(len(i_u), 1)
        self.assertEqual(len(i_u[0].split()), 2 + 14)                  # nine 002 numbers + five extended ones
        self.assertGreaterEqual(text.count("I m"), 1)
        self.assertEqual(text.count("P a 00002000"), 1)                 # the POSTACK main-loop W1C of this scenario
        self.assertEqual(text.count("P w "), 0)                         # INTMR never written directly
        # replay
        run2 = subprocess.run([BIN, "--replay", fx], capture_output=True, text=True)
        self.assertEqual(run2.returncode, 0, run2.stdout + run2.stderr)
        summary_replay = [l for l in run2.stdout.splitlines() if l.startswith("SUMMARY ")]
        self.assertEqual(len(summary_replay), 1)
        self.assertEqual(summary_mock[0], summary_replay[0])
        self.assertIn("status=ok_delivery_observed", summary_replay[0])
        self.assertIn("fired=1 count=1", summary_replay[0])
        self.assertIn("main_pi_w1c=1 site=POSTACK", summary_replay[0])
        m = re.search(r"REPLAY step=(\d+) exhausted=(\d+) mismatches=(\d+) tick_polls=(\d+) timeline=(\d+)", run2.stdout)
        self.assertIsNotNone(m, run2.stdout)
        self.assertEqual((m.group(2), m.group(3), m.group(4), m.group(5)), ("0", "0", "0", "1"))
        # synthetic scripts never enter captures/fixtures; no GBP-INIT-003B fixture exists there
        for fx_path in glob.glob(os.path.join(ROOT, "captures", "fixtures", "*.gbpreplay")):
            with open(fx_path, encoding="utf-8") as f:
                head = f.read(2048)
            self.assertNotIn("SYNTHETIC", head, fx_path)
            self.assertNotIn("GBP-INIT-003B", head, fx_path)
            self.assertNotIn("initirqb", os.path.basename(fx_path))
        self.assertFalse(fx.startswith(os.path.join(ROOT, "captures")))

    @unittest.skipUnless(os.path.isfile(PHYSICAL_003A), "physical GBP-INIT-003A fixture missing")
    def test_physical_003a_fixture_is_the_prefix_up_to_the_event(self):
        run = subprocess.run([BIN, "--replay", PHYSICAL_003A], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        summary = [l for l in run.stdout.splitlines() if l.startswith("SUMMARY ")][0]
        self.assertIn("status=abort_handler_install reason=irq_ops_unavailable restore=ok restore_reason=-", summary)
        self.assertIn("written=1 irq_attempted=3 irq_completed=3 ctl_exp=1/1 a1=1/1 a2=1/1 ack=0/0 stop=1/1 ctl_restore=1/1 uncertain=0", summary)
        self.assertIn("cause=1 t_event=4155517524 handler=0 old=? preunmask=0/- unmasked=0 fired=0 count=0", summary)
        self.assertIn("main_pi_w1c=1 site=CLEANUP sticky=0", summary)
        self.assertIn("stop_post=8aaa pi_cleanup=1 handler_restored=-1 mask_ok=-1 arinfo_restore_ok=1 power_cycle_required=1", summary)
        m = re.search(r"REPLAY step=(\d+) exhausted=(\d+) mismatches=(\d+) tick_polls=(\d+) timeline=(\d+)", run.stdout)
        self.assertEqual((m.group(2), m.group(3), m.group(4), m.group(5)), ("0", "0", "0", "1"))


if __name__ == "__main__":
    unittest.main()
