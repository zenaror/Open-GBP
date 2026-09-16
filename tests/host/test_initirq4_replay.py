"""
GBP-INIT-004 fixture round trip on SYNTHETIC data, and the two physical
fixtures as prefixes of the 004 logic.

The synthetic path: the host mock run (tests/unit/test_gbp_initirq4.c
--dump-log, three cycles) is written in the SD-log format, tools/probelog.py
turns it into a replay script (clearly marked SYNTHETIC; it carries the
optional "I p <gen>" lines), and the probe logic run on that script reaches
the same result as the mock run — every time-base read, PI read, interrupt-
path operation, generation publication and handler record answered by the
fixture, nothing invented. The generated files stay under build/ and are
never placed under captures/fixtures/.

The physical GBP-INIT-003A fixture (no interrupt path) drives the stage
verbatim up to its EVENT and stops at the install. The physical GBP-INIT-003B
fixture (initirqb-0001) is the real prefix of cycle 0 up to its POSTACK: the
script is cut before the 003B CONTROL restore, so the first re-arm meets an
exhausted script (a re-arm was never recorded physically) — NO physical
GBP-INIT-004 fixture exists and none is fabricated here.
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

BIN = os.path.join(ROOT, "build", "tests", "unit", "test_gbp_initirq4")
OUTDIR = os.path.join(ROOT, "build", "tests", "unit")
NOTE = "SYNTHETIC: generated from the host mock (tests/unit/test_gbp_initirq4.c --dump-log); NOT physical data"
PHYSICAL_003A = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-15-initirqa-0001.gbpreplay")
PHYSICAL_003B = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-15-initirqb-0001.gbpreplay")
PHYSICAL_004 = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-16-initirq4-0001.gbpreplay")


@unittest.skipUnless(os.path.isfile(BIN), "run `make -C tests/unit` to build the test binary")
class Initirq4RoundTrip(unittest.TestCase):
    def test_mock_log_replays_to_the_same_result(self):
        outdir = OUTDIR if os.path.isdir(OUTDIR) else tempfile.mkdtemp()
        log = os.path.join(outdir, "initirq4-synthetic.log")
        fx = os.path.join(outdir, "initirq4-synthetic.gbpreplay")
        run1 = subprocess.run([BIN, "--dump-log", log], capture_output=True, text=True)
        self.assertEqual(run1.returncode, 0, run1.stdout + run1.stderr)
        summary_mock = [l for l in run1.stdout.splitlines() if l.startswith("SUMMARY ")]
        self.assertEqual(len(summary_mock), 1)
        with open(log, encoding="utf-8") as f:
            self.assertIn("# SYNTHETIC", f.read(400))
        header, records = probelog.parse_file(log)
        self.assertEqual(header["test_id"], "GBP-INIT-004")
        self.assertEqual(header["source"], "host-mock")
        kinds = {r["kind"] for r in records}
        for k in ("INITIRQ4", "INITIRQA", "IRQSHAPE", "CTLW", "IRQW", "SNAP", "WINDOW", "REGION", "CAUSE", "IRQ", "MULTI",
                  "CYCLE", "PREPARE", "PREUNMASK", "PREUNMASK4", "UNMASK", "WAIT", "HANDLER", "HANDLERPI", "HANDLERPI2",
                  "DELIVERY", "HANDLER4", "PREACK", "ACK", "POSTACK", "MAINPICLEANUP", "PICLEAN", "BOUNDARY", "REARM",
                  "REARMPOST", "NEXTCAUSE", "TEARDOWN4", "TEARDOWN", "IRQSTOP", "CLEANUP", "MASK", "RESTORE", "CYCLES",
                  "TIMING", "RESTORE4"):
            self.assertIn(k, kinds)
        irqw = [r for r in records if r["kind"] == "IRQW"]
        self.assertEqual([r["fields"]["tag"] for r in irqw], ["A1", "A2", "ACK-0", "REARM-0", "ACK-1", "REARM-1", "ACK-2", "STOP"])
        self.assertTrue(all(r["fields"]["layout"] == "gbi-u16-replicated" for r in irqw))
        for i in (3, 5):                                                  # every re-arm is the u16 0x0000 replicated
            self.assertEqual(irqw[i]["fields"]["write"], "0000")
            self.assertEqual(irqw[i]["fields"]["data"], "00" * 32)
        for i in (2, 4, 6):                                               # every ACK is read | 0x8000
            before = int(irqw[i]["fields"]["before"], 16)
            self.assertEqual(int(irqw[i]["fields"]["write"], 16), before | 0x8000)
        region = [r for r in records if r["kind"] == "REGION"][0]
        self.assertEqual(region["fields"]["formatted_inside"], "0")
        self.assertEqual(len([r for r in records if r["kind"] == "IRQ" and r["tag"] == "install"]), 1)
        self.assertEqual(len([r for r in records if r["kind"] == "UNMASK"]), 3)
        self.assertEqual([r["fields"]["gen"] for r in records if r["kind"] == "PREPARE"], ["0", "1", "2"])
        self.assertEqual([r["fields"]["found"] for r in records if r["kind"] == "NEXTCAUSE"], ["1", "1"])
        cycles = [r for r in records if r["kind"] == "CYCLES"][0]["fields"]
        self.assertEqual((cycles["requested"], cycles["completed"], cycles["deliveries"], cycles["acks"], cycles["rearms"],
                          cycles["next_causes"], cycles["isr_w1c"], cycles["main_w1c"], cycles["teardown_w1c"]),
                         ("3", "3", "3", "3", "2", "2", "3", "0", "0"))
        # the order of the per-cycle records mirrors the sequence (§43): first occurrences
        keys = [(r["kind"], r["fields"].get("tag"), r["fields"].get("n")) for r in records]
        def first(kind, tag=None, n=None):
            for i, (k, t, nn) in enumerate(keys):
                if k == kind and (tag is None or t == tag) and (n is None or nn == n):
                    return i
            self.fail("record %s tag=%s n=%s missing" % (kind, tag, n))
        order = [first("SNAP", "EVENT"), first("CAUSE"), first("IRQ"), first("PREPARE", n="0"), first("SNAP", "PREUNMASK-0"),
                 first("UNMASK", n="0"), first("HANDLER", n="0"), first("SNAP", "PREACK-0"), first("IRQW", "ACK-0"),
                 first("SNAP", "POSTACK-0"), first("PICLEAN", n="0"), first("REARM", n="0"), first("IRQW", "REARM-0"),
                 first("SNAP", "REARMPOST-0"), first("NEXTCAUSE", n="0"), first("PREPARE", n="1"), first("UNMASK", n="1"),
                 first("IRQW", "ACK-1"), first("IRQW", "REARM-1"), first("NEXTCAUSE", n="1"), first("PREPARE", n="2"),
                 first("UNMASK", n="2"), first("IRQW", "ACK-2"), first("TEARDOWN4"), first("CTLW", "RESTORE"), first("IRQW", "STOP"),
                 first("PI", "CLEANUPCHK"), first("MASK"), first("SNAP", "FINAL")]
        self.assertEqual(order, sorted(order), order)
        self.assertEqual(len([r for r in records if r["kind"] == "IRQW" and r["fields"]["tag"].startswith("REARM")]), 2)   # no REARM after cycle 2
        # fixture, marked synthetic, with the optional generation lines
        self.assertEqual(probelog.main(["fixture", log, fx, "--note", NOTE]), 0)
        with open(fx, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("# SYNTHETIC", text)
        self.assertEqual(text.count("W 01d00000 ok"), 8)
        self.assertEqual(text.count("I i null"), 1)
        self.assertEqual(text.count("I r"), 1)
        self.assertEqual([l for l in text.splitlines() if l.startswith("I p ")], ["I p 0", "I p 1", "I p 2"])
        i_u = [l for l in text.splitlines() if l.startswith("I u ")]
        self.assertEqual(len(i_u), 3)
        self.assertTrue(all(len(l.split()) == 2 + 14 for l in i_u))
        self.assertEqual(text.count("I m"), 3)
        self.assertEqual(text.count("P w "), 0)                         # INTMR never written directly
        self.assertEqual(text.count("P a "), 0)                         # no main-loop W1C in this scenario
        # replay
        run2 = subprocess.run([BIN, "--replay", fx], capture_output=True, text=True)
        self.assertEqual(run2.returncode, 0, run2.stdout + run2.stderr)
        summary_replay = [l for l in run2.stdout.splitlines() if l.startswith("SUMMARY ")]
        self.assertEqual(len(summary_replay), 1)
        self.assertEqual(summary_mock[0], summary_replay[0])
        self.assertIn("status=ok_cycles_completed", summary_replay[0])
        self.assertIn("cycles=3/3 completed=3 deliveries=3 acks=3 rearms=2/2 next_causes=2", summary_replay[0])
        m = re.search(r"REPLAY step=(\d+) exhausted=(\d+) mismatches=(\d+) tick_polls=(\d+) timeline=(\d+)", run2.stdout)
        self.assertIsNotNone(m, run2.stdout)
        self.assertEqual((m.group(2), m.group(3), m.group(4), m.group(5)), ("0", "0", "0", "1"))
        # the same script without its "I p" lines replays identically: the generation line is optional
        fx2 = os.path.join(outdir, "initirq4-synthetic-noprepare.gbpreplay")
        with open(fx2, "w", encoding="utf-8") as f:
            f.write("".join(l for l in text.splitlines(True) if not l.startswith("I p ")))
        run3 = subprocess.run([BIN, "--replay", fx2], capture_output=True, text=True)
        self.assertEqual(run3.returncode, 0, run3.stdout + run3.stderr)
        self.assertEqual([l for l in run3.stdout.splitlines() if l.startswith("SUMMARY ")], summary_replay)
        # synthetic scripts never enter captures/fixtures: every fixture there is physical or Dolphin model data
        for fx_path in glob.glob(os.path.join(ROOT, "captures", "fixtures", "*.gbpreplay")):
            with open(fx_path, encoding="utf-8") as f:
                head = f.read(4096)
            self.assertNotIn("SYNTHETIC", head, fx_path)
            self.assertTrue("# SOURCE=physical GameCube" in head or "MODEL DATA, NOT HARDWARE" in head, fx_path)
        self.assertFalse(fx.startswith(os.path.join(ROOT, "captures")))

    @unittest.skipUnless(os.path.isfile(PHYSICAL_004), "physical GBP-INIT-004 fixture missing")
    def test_physical_004_fixture_replays_to_the_physical_result(self):
        # 2026-09-16, initirq4-0001, commit 741630b: one delivery, one ACK, POSTACK-0 0x8400 with PI clear 26.0 us after the
        # ACK, anomaly_source_not_cleared, NO re-arm; every recorded operation replays, nothing after the record is invented
        run = subprocess.run([BIN, "--replay", PHYSICAL_004], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        summary = [l for l in run.stdout.splitlines() if l.startswith("SUMMARY ")][0]
        self.assertIn("status=anomaly_source_not_cleared reason=source_pending_after_ack_cycle_0 restore=ok restore_reason=- teardown=S3_cycle_aborted "
                      "verdict=present det=4/4 written=1 irq_attempted=4 irq_completed=4 ctl_exp=1/1 a1=1/1 a2=1/1 stop=1/1 ctl_restore=1/1 uncertain=0 "
                      "cause=1 t_event=1053111645 handler=1 old=null cycles=1/3 completed=0 deliveries=1 acks=1 rearms=0/0 next_causes=0 unexpected=0 "
                      "reentry=0 timeouts=0 gen_errors=0 entries=1 isr_w1c=1 main_w1c=0 teardown_w1c=0 control_ok=1 pi_sticky_final=0 "
                      "control_restore_ok=1 irq_stop_write_ok=1 stop_post=8aaa pi_cleanup=0 handler_restored=1 mask_ok=1 arinfo_restore_ok=1 "
                      "power_cycle_required=1 errors=0 transport_ok=1", summary)
        m = re.search(r"REPLAY step=(\d+) exhausted=(\d+) mismatches=(\d+) tick_polls=(\d+) timeline=(\d+)", run.stdout)
        self.assertEqual((m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)), ("112", "0", "0", "0", "1"))
        with open(PHYSICAL_004, encoding="utf-8") as f:
            head = f.read(4096)
        self.assertIn("# SOURCE=physical GameCube", head)
        self.assertNotIn("SYNTHETIC", head)

    @unittest.skipUnless(os.path.isfile(PHYSICAL_003B), "physical GBP-INIT-003B fixture missing")
    def test_physical_003b_fixture_is_the_prefix_of_cycle_0(self):
        with open(PHYSICAL_003B, encoding="utf-8") as f:
            text = f.read()
        # cut before the 003B CONTROL restore (the second "W 01400000 ok"): the physical run never re-armed
        first = text.index("\nW 01400000 ok")
        second = text.index("\nW 01400000 ok", first + 1)
        cut = os.path.join(OUTDIR if os.path.isdir(OUTDIR) else tempfile.mkdtemp(), "initirqb-0001-prefix-for-004.gbpreplay")
        with open(cut, "w", encoding="utf-8") as f:
            f.write(text[:second + 1])
            f.write("# BOUNDARY: physical prefix (GBP-INIT-003B initirqb-0001) ends here, before the first GBP-INIT-004 re-arm;\n"
                    "# every operation after this line is unavailable (exhausted script), NOT physical data\n")
        run = subprocess.run([BIN, "--replay", cut], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)   # exhausted at the re-arm: reported, not hidden
        summary = [l for l in run.stdout.splitlines() if l.startswith("SUMMARY ")][0]
        self.assertIn("status=abort_transport reason=rearm_write_failed_cycle_0", summary)
        self.assertIn("teardown=S4_rearm_failed", summary)
        self.assertIn("cause=1 t_event=3679890204 handler=1 old=null cycles=1/3 completed=1 deliveries=1 acks=1 rearms=0/1 next_causes=0 "
                      "unexpected=0 reentry=0 timeouts=0 gen_errors=0 entries=1 isr_w1c=1 main_w1c=0", summary)
        # rearms=0/1: the re-arm was issued to a transport whose physical record had ended (unavailable, rc=backend) —
        # a synthetic boundary, never evidence of a re-arm; the cut file stays under build/, never under captures/
        m = re.search(r"REPLAY step=(\d+) exhausted=(\d+) mismatches=(\d+) tick_polls=(\d+) timeline=(\d+)", run.stdout)
        self.assertIsNotNone(m, run.stdout)
        self.assertEqual(m.group(3), "0")                                 # no mismatch: every recorded operation matched
        self.assertGreater(int(m.group(2)), 0)                            # exhausted only after the last recorded operation
        self.assertEqual(m.group(5), "1")

    @unittest.skipUnless(os.path.isfile(PHYSICAL_003A), "physical GBP-INIT-003A fixture missing")
    def test_physical_003a_fixture_is_the_prefix_up_to_the_event(self):
        run = subprocess.run([BIN, "--replay", PHYSICAL_003A], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        summary = [l for l in run.stdout.splitlines() if l.startswith("SUMMARY ")][0]
        self.assertIn("status=abort_handler_install reason=irq_multi_ops_unavailable restore=ok restore_reason=- teardown=S2_before_unmask", summary)
        self.assertIn("written=1 irq_attempted=3 irq_completed=3 ctl_exp=1/1 a1=1/1 a2=1/1 stop=1/1 ctl_restore=1/1 uncertain=0", summary)
        self.assertIn("cause=1 t_event=4155517524 handler=0 old=? cycles=0/3 completed=0 deliveries=0 acks=0 rearms=0/0", summary)
        self.assertIn("teardown_w1c=1", summary)
        m = re.search(r"REPLAY step=(\d+) exhausted=(\d+) mismatches=(\d+) tick_polls=(\d+) timeline=(\d+)", run.stdout)
        self.assertEqual((m.group(2), m.group(3), m.group(4), m.group(5)), ("0", "0", "0", "1"))


if __name__ == "__main__":
    unittest.main()
