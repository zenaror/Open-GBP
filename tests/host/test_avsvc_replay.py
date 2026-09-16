"""
GBP-AV-SERVICE-001 fixture round trip on SYNTHETIC data, and the physical
fixtures as prefixes of the service logic.

The synthetic path: the host mock run (tests/unit/test_gbp_avsvc.c --dump-log,
one drained service: AUDIO + VIDEO, a re-latch cleared by the single main W1C,
a re-arm, a delayed next cause) is written in the SD-log format together with
its block sidecar; tools/probelog.py turns the log into a replay script (marked
SYNTHETIC; its "B" lines carry the CRC-32 of each block, never the bytes), and
the probe logic run on that script with the sidecar attached reaches the same
result as the mock run — every time-base read, PI read, interrupt-path
operation, whole-block read and handler record answered by the fixture and
the sidecar, nothing invented. Without the sidecar the blocks are missing and
the replay says so. The generated files stay under build/ and are never placed
under captures/fixtures/.

The physical GBP-INIT-003A fixture (no interrupt path) stops at the install.
The physical GBP-INIT-003B and GBP-INIT-004 fixtures, cut before their device
ACK, are the real prefixes up to the delivery and the PRESVC reads; the drain
then meets a transport without whole-block reads (abort_bulk_unavailable).
The physical path: the GBP-AV-SERVICE-001 fixture of 2026-09-16 (build avsvc-0001,
commit d3a6d23) with its block sidecar replays end to end to the physical result;
without the sidecar the two blocks are reported missing (exit 1), never invented.
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

import avdump  # noqa: E402
import probelog  # noqa: E402

BIN = os.path.join(ROOT, "build", "tests", "unit", "test_gbp_avsvc")
OUTDIR = os.path.join(ROOT, "build", "tests", "unit")
NOTE = "SYNTHETIC: generated from the host mock (tests/unit/test_gbp_avsvc.c --dump-log); NOT physical data"
PHYSICAL_003A = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-15-initirqa-0001.gbpreplay")
PHYSICAL_003B = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-15-initirqb-0001.gbpreplay")
PHYSICAL_004 = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-16-initirq4-0001.gbpreplay")
PHYSICAL_AVSVC = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-16-avsvc-0001.gbpreplay")
PHYSICAL_AVSVC_BLOCKS = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-16-avsvc-0001-blocks.bin")
REPLAY_RE = re.compile(r"REPLAY step=(\d+) exhausted=(\d+) mismatches=(\d+) tick_polls=(\d+) timeline=(\d+) log_lines=(\d+) "
                       r"bulk_reads=(\d+) blocks_missing=(\d+) block_crc_mismatches=(\d+)")


def outdir():
    return OUTDIR if os.path.isdir(OUTDIR) else tempfile.mkdtemp()


def cut_before_ack(text, drop_prefix=None):
    """The physical script up to (not including) the 3rd IRQ-register write (the run's device ACK)."""
    lines = text.splitlines(True)
    n = 0
    out = []
    for l in lines:
        if l.startswith("W 01d00000"):
            n += 1
            if n == 3:
                break
        if drop_prefix and l.startswith(drop_prefix):
            continue
        out.append(l)
    out.append("# BOUNDARY: physical prefix ends here (cut before the device ACK); every operation after this line is\n"
               "# unavailable (exhausted script), NOT physical data; the whole-block reads never happened on hardware\n")
    return "".join(out)


@unittest.skipUnless(os.path.isfile(BIN), "run `make -C tests/unit` to build the test binary")
class AvsvcRoundTrip(unittest.TestCase):
    def test_mock_log_replays_to_the_same_result_with_the_sidecar(self):
        d = outdir()
        log = os.path.join(d, "avsvc-synthetic.log")
        blocks = os.path.join(d, "avsvc-synthetic-blocks.bin")
        fx = os.path.join(d, "avsvc-synthetic.gbpreplay")
        run1 = subprocess.run([BIN, "--dump-log", log, blocks], capture_output=True, text=True)
        self.assertEqual(run1.returncode, 0, run1.stdout + run1.stderr)
        summary_mock = [l for l in run1.stdout.splitlines() if l.startswith("SUMMARY ")]
        self.assertEqual(len(summary_mock), 1)
        self.assertIn("status=ok_service_rearm_cause_observed class=ok", summary_mock[0])
        with open(log, encoding="utf-8") as f:
            self.assertIn("# SYNTHETIC", f.read(400))
        header, records = probelog.parse_file(log)
        self.assertEqual(header["test_id"], "GBP-AV-SERVICE-001")
        self.assertEqual(header["source"], "host-mock")
        kinds = {r["kind"] for r in records}
        for k in ("AVSVC", "INITIRQA", "IRQSHAPE", "CTLW", "IRQW", "SNAP", "WINDOW", "REGION", "CAUSE", "IRQ", "PREUNMASK", "PREUNMASKAV",
                  "UNMASK", "WAIT", "HANDLER", "HANDLERPI", "HANDLERPI2", "DELIVERY", "PRESVC", "SVC", "AUDIOREAD", "VIDEOREAD", "SVCEND",
                  "POSTDRAIN", "ACK", "POSTACK", "POSTACKAV", "MAINPICLEANUP", "PICLEAN", "REARM", "REARMPOST", "NEXTCAUSE", "TEARDOWNAV",
                  "TEARDOWN", "IRQSTOP", "CLEANUP", "MASK", "RESTORE", "SERVICE", "COUNTERS", "BLOCK", "BLOCKW", "TIMING", "RESTOREAV"):
            self.assertIn(k, kinds)
        irqw = [r for r in records if r["kind"] == "IRQW"]
        self.assertEqual([r["fields"]["tag"] for r in irqw], ["A1", "A2", "ACK", "REARM", "STOP"])
        self.assertEqual(int(irqw[2]["fields"]["write"], 16), int(irqw[2]["fields"]["before"], 16) | 0x8000)
        self.assertEqual(irqw[3]["fields"]["write"], "0000")
        self.assertEqual(irqw[3]["fields"]["data"], "00" * 32)
        # the ACK value is the PRESVC value, not a later read
        presvc = [r for r in records if r["kind"] == "PRESVC"][0]["fields"]
        svc = [r for r in records if r["kind"] == "SVC" and r["tag"] == "start"][0]["fields"]
        self.assertEqual(svc["pending"], presvc["irq"].split("/")[0])
        self.assertEqual(int(svc["ack_value"], 16), int(svc["pending"], 16) | 0x8000)
        self.assertEqual(irqw[2]["fields"]["before"], svc["pending"])
        reads = [r for r in records if r["kind"] in ("AUDIOREAD", "VIDEOREAD")]
        self.assertEqual([r["kind"] for r in reads], ["AUDIOREAD", "VIDEOREAD"])
        self.assertEqual([(r["fields"]["addr"], r["fields"]["len"], r["fields"]["rc"]) for r in reads],
                         [("01800000", "1000", "ok"), ("01100000", "0f00", "ok")])
        self.assertLess(int(reads[0]["fields"]["t_end"]), int(reads[1]["fields"]["t_start"]))     # AUDIO completed before VIDEO started
        self.assertLess(int(reads[1]["fields"]["t_end"]), int(irqw[2]["fields"]["t_after"]))      # both before the ACK
        blocks_rec = {r["fields"]["kind"]: r["fields"] for r in records if r["kind"] == "BLOCK"}
        self.assertEqual((blocks_rec["audio"]["present"], blocks_rec["audio"]["valid"], blocks_rec["video"]["valid"]), ("1", "1", "1"))
        self.assertEqual(len([r for r in records if r["kind"] == "BLOCKW"]), 8)
        with open(log, encoding="utf-8") as f:
            self.assertNotIn("A" * 100, f.read())                                                    # no block hex dump in the text log
        region = [r for r in records if r["kind"] == "REGION"][0]
        self.assertEqual(region["fields"]["formatted_inside"], "0")
        self.assertEqual(len([r for r in records if r["kind"] == "UNMASK"]), 1)
        self.assertEqual(len([r for r in records if r["kind"] == "NEXTCAUSE"]), 1)
        counters = [r for r in records if r["kind"] == "COUNTERS"][0]["fields"]
        self.assertEqual((counters["unmasks"], counters["deliveries"], counters["acks"], counters["rearms"], counters["next_causes"],
                          counters["isr_w1c"], counters["main_w1c"], counters["teardown_w1c"], counters["w1c_total"]),
                         ("1", "1", "1", "1", "1", "1", "1", "1", "3"))
        # the sidecar: the same CRCs the log carries, both blocks, identity
        with open(blocks, "rb") as f:
            side = avdump.parse(f.read())
        self.assertEqual(side["test_id"], "GBP-AV-SERVICE-001")                    # the full Test ID (18 characters), never truncated
        self.assertEqual((side["build_id"], side["app"], side["commit"]), ("synthetic", "gbp-av-service-probe", "none"))
        self.assertEqual(header["test_id"], side["test_id"])                            # log header <-> sidecar identity
        self.assertEqual("%08x" % side["audio_crc32"], blocks_rec["audio"]["crc32"])
        self.assertEqual("%08x" % side["video_crc32"], blocks_rec["video"]["crc32"])
        self.assertEqual((side["audio_len"], side["video_len"], side["pending_irq"], side["drain_mask"]), (0x1000, 0xF00, 0x0500, 0x0500))
        self.assertTrue(side["audio_valid"] and side["video_valid"])
        # order of the records mirrors the sequence (first occurrences)
        keys = [(r["kind"], r["fields"].get("tag") or r.get("tag")) for r in records]

        def first(kind, tag=None):
            for i, (k, t) in enumerate(keys):
                if k == kind and (tag is None or t == tag):
                    return i
            self.fail("record %s tag=%s missing" % (kind, tag))
        order = [first("SNAP", "EVENT"), first("CAUSE"), first("IRQ"), first("SNAP", "PREUNMASK"), first("UNMASK"), first("HANDLER"),
                 first("SNAP", "PRESVC"), first("SVC"), first("AUDIOREAD"), first("VIDEOREAD"), first("SVCEND"), first("SNAP", "POSTDRAIN"),
                 first("ACK"), first("IRQW", "ACK"), first("SNAP", "POSTACK"), first("MAINPICLEANUP"), first("PICLEAN"), first("REARM"),
                 first("IRQW", "REARM"), first("SNAP", "REARMPOST"), first("NEXTCAUSE"), first("TEARDOWNAV"), first("CTLW", "RESTORE"),
                 first("IRQW", "STOP"), first("PI", "CLEANUPCHK"), first("MASK"), first("SNAP", "FINAL"), first("AVSVC", "end"),
                 first("BLOCK")]
        self.assertEqual(order, sorted(order), order)
        # fixture: the "B" lines carry addr/len/rc/crc32 and never bytes; the sidecar is the byte source
        self.assertEqual(probelog.main(["fixture", log, fx, "--note", NOTE]), 0)
        with open(fx, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("# SYNTHETIC", text)
        b_lines = [l for l in text.splitlines() if l.startswith("B ")]
        self.assertEqual(b_lines, ["B 01800000 00001000 ok %s" % blocks_rec["audio"]["crc32"], "B 01100000 00000f00 ok %s" % blocks_rec["video"]["crc32"]])
        self.assertEqual(text.count("W 01d00000 ok"), 5)
        self.assertEqual(text.count("I i null"), 1)
        self.assertEqual(text.count("I r"), 1)
        self.assertEqual(text.count("I m"), 1)
        self.assertEqual(text.count("I p "), 0)                          # no generation with the 003B handler
        self.assertEqual(text.count("P w "), 0)                          # INTMR never written directly
        self.assertEqual(text.count("P a "), 2)                          # the POSTACK main W1C and the teardown W1C
        i_u = [l for l in text.splitlines() if l.startswith("I u ")]
        self.assertEqual(len(i_u), 1)
        self.assertEqual(len(i_u[0].split()), 2 + 14)
        self.assertLess(len(text), 40000)
        # replay with the sidecar: the same result
        run2 = subprocess.run([BIN, "--replay", fx, blocks], capture_output=True, text=True)
        self.assertEqual(run2.returncode, 0, run2.stdout + run2.stderr)
        summary_replay = [l for l in run2.stdout.splitlines() if l.startswith("SUMMARY ")]
        self.assertEqual(summary_mock, summary_replay)
        m = REPLAY_RE.search(run2.stdout)
        self.assertIsNotNone(m, run2.stdout)
        self.assertEqual(m.groups()[1:], ("0", "0", "0", "1", m.group(6), "2", "0", "0"))
        # replay without the sidecar: the blocks are missing (zeros), reported, the run still completes (a different CRC)
        run3 = subprocess.run([BIN, "--replay", fx], capture_output=True, text=True)
        self.assertEqual(run3.returncode, 1, run3.stdout + run3.stderr)
        m = REPLAY_RE.search(run3.stdout)
        self.assertEqual((m.group(7), m.group(8), m.group(9)), ("2", "2", "0"))
        self.assertIn("status=ok_service_rearm_cause_observed", run3.stdout)
        self.assertNotEqual(summary_mock, [l for l in run3.stdout.splitlines() if l.startswith("SUMMARY ")])
        # a tampered sidecar (one byte) is rejected by the parser
        with open(blocks, "rb") as f:
            raw = bytearray(f.read())
        raw[0x80 + 7] ^= 0x01
        bad = os.path.join(d, "avsvc-synthetic-blocks-bad.bin")
        with open(bad, "wb") as f:
            f.write(raw)
        run4 = subprocess.run([BIN, "--replay", fx, bad], capture_output=True, text=True)
        self.assertEqual(run4.returncode, 1)
        self.assertIn("bad sidecar", run4.stderr)
        # synthetic scripts never enter captures/fixtures: every fixture there is physical or Dolphin model data; the only
        # AVSVC files there are the physical fixture of 2026-09-16 and its sidecar, and only a script that names a sidecar
        # (# BLOCKS=) may carry "B" lines
        for fx_path in glob.glob(os.path.join(ROOT, "captures", "fixtures", "*")):
            name = os.path.basename(fx_path)
            if "avsvc" in name.lower():
                self.assertIn(fx_path, (PHYSICAL_AVSVC, PHYSICAL_AVSVC_BLOCKS), fx_path)
            if fx_path.endswith(".gbpreplay"):
                with open(fx_path, encoding="utf-8") as f:
                    text = f.read()
                self.assertNotIn("SYNTHETIC", text[:4096], fx_path)
                if "\nB " in text:
                    self.assertIn("# SOURCE=physical GameCube", text[:4096], fx_path)
                    self.assertIn("# BLOCKS=", text[:4096], fx_path)
                    self.assertEqual(fx_path, PHYSICAL_AVSVC)
        self.assertFalse(fx.startswith(os.path.join(ROOT, "captures")))

    @unittest.skipUnless(os.path.isfile(PHYSICAL_003B), "physical GBP-INIT-003B fixture missing")
    def test_physical_003b_prefix_up_to_the_presvc_reads(self):
        with open(PHYSICAL_003B, encoding="utf-8") as f:
            text = f.read()
        cut = os.path.join(outdir(), "initirqb-0001-prefix-for-avsvc.gbpreplay")
        with open(cut, "w", encoding="utf-8") as f:
            f.write(cut_before_ack(text))
        run = subprocess.run([BIN, "--replay", cut], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)   # exhausted after the physical record: reported, not hidden
        summary = [l for l in run.stdout.splitlines() if l.startswith("SUMMARY ")][0]
        self.assertIn("status=abort_bulk_unavailable class=abort reason=bulk_read_unavailable", summary)
        self.assertIn("teardown=S3_service_aborted", summary)
        self.assertIn("cause=1 t_event=3679890204 handler=1 old=null unmasked=1 fired=1 count=1", summary)
        self.assertIn("pending=0500 drain=0500 drains=2/0/0 audio=-/0000 video=-/0000 drain_uncertain=0 ack_value=0000", summary)
        m = REPLAY_RE.search(run.stdout)
        self.assertIsNotNone(m, run.stdout)
        self.assertEqual(m.group(3), "0")                                # every recorded operation matched
        self.assertGreater(int(m.group(2)), 0)                           # exhausted only after the last recorded operation
        self.assertEqual((m.group(7), m.group(8)), ("0", "0"))           # no whole-block read was ever replayed from a physical record
        self.assertFalse(cut.startswith(os.path.join(ROOT, "captures")))

    @unittest.skipUnless(os.path.isfile(PHYSICAL_004), "physical GBP-INIT-004 fixture missing")
    def test_physical_004_prefix_up_to_the_presvc_reads(self):
        with open(PHYSICAL_004, encoding="utf-8") as f:
            text = f.read()
        cut = os.path.join(outdir(), "initirq4-0001-prefix-for-avsvc.gbpreplay")
        with open(cut, "w", encoding="utf-8") as f:
            f.write(cut_before_ack(text, drop_prefix="I p "))            # the generation line belongs to the 004 handler
        run = subprocess.run([BIN, "--replay", cut], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        summary = [l for l in run.stdout.splitlines() if l.startswith("SUMMARY ")][0]
        self.assertIn("status=abort_bulk_unavailable class=abort reason=bulk_read_unavailable", summary)
        self.assertIn("cause=1 t_event=1053111645 handler=1 old=null unmasked=1 fired=1 count=1 latency_ticks=89", summary)
        self.assertIn("pending=0500 drain=0500 drains=2/0/0", summary)
        m = REPLAY_RE.search(run.stdout)
        self.assertEqual((m.group(3), m.group(7), m.group(8)), ("0", "0", "0"))
        self.assertGreater(int(m.group(2)), 0)

    @unittest.skipUnless(os.path.isfile(PHYSICAL_AVSVC) and os.path.isfile(PHYSICAL_AVSVC_BLOCKS), "physical GBP-AV-SERVICE-001 fixture missing")
    def test_physical_avsvc_fixture_replays_to_the_physical_result(self):
        # 2026-09-16, avsvc-0001, commit d3a6d23: one delivery (72 ticks), PRESVC 0x0500, AUDIO 0x1000 then VIDEO 0xF00 by one
        # whole-block DMA each (bytes from the sidecar, CRCs fec5e4e7 / fe45ff08), POSTDRAIN still 0x0500, ACK 0x8500,
        # POSTACK 0x8000 with PI clear, no main W1C, re-arm 0x0000, REARMPOST B (INTSR bit 13 = 1, IRQ 0x0400) 1778 ticks
        # later, the next cause found at once and never delivered, teardown S4B with one W1C; every recorded operation
        # replays, nothing is invented
        run = subprocess.run([BIN, "--replay", PHYSICAL_AVSVC, PHYSICAL_AVSVC_BLOCKS], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        summary = [l for l in run.stdout.splitlines() if l.startswith("SUMMARY ")][0]
        for part in ("status=ok_service_rearm_cause_observed class=ok reason=- restore=ok restore_reason=- teardown=S4B_next_cause_latched",
                     "irq_attempted=5 irq_completed=5 ctl_exp=1/1 a1=1/1 a2=1/1 ack=1/1 rearm=1/1 stop=1/1 ctl_restore=1/1 uncertain=0",
                     "cause=1 t_event=3391329164 handler=1 old=null unmasked=1 fired=1 count=1 latency_ticks=72",
                     "pending=0500 drain=0500 drains=2/2/2 audio=ok/e4e7 video=ok/ff08 drain_uncertain=0 ack_value=8500 postack_irq=8000",
                     "source_after_ack=0000 relatch=0/0 main_w1c=0 pi_clean=1 sticky=0 rearmpost=B_latched next_cause=1 immediate=1 dt_next=1778",
                     "unexpected=0000 site=- isr_w1c=1 teardown_w1c=1 control_ok=1 pi_sticky_final=0",
                     "stop_post=8aaa pi_cleanup=1 handler_restored=1 mask_ok=1 arinfo_restore_ok=1 power_cycle_required=1 errors=0 transport_ok=1"):
            self.assertIn(part, summary)
        m = REPLAY_RE.search(run.stdout)
        self.assertIsNotNone(m, run.stdout)
        self.assertEqual(m.groups(), ("132", "0", "0", "0", "1", "179", "2", "0", "0"))

    @unittest.skipUnless(os.path.isfile(PHYSICAL_AVSVC), "physical GBP-AV-SERVICE-001 fixture missing")
    def test_physical_avsvc_fixture_without_its_sidecar_reports_the_blocks_missing(self):
        # the script carries no block bytes: without the sidecar both whole-block reads are counted missing and the
        # run exits 1; the buffers keep the probe's pre-fill (CRC suffixes 0011 / 3467), never the physical bytes
        run = subprocess.run([BIN, "--replay", PHYSICAL_AVSVC], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        summary = [l for l in run.stdout.splitlines() if l.startswith("SUMMARY ")][0]
        self.assertIn("drains=2/2/2 audio=ok/0011 video=ok/3467", summary)
        self.assertNotIn("audio=ok/e4e7", summary)
        m = REPLAY_RE.search(run.stdout)
        self.assertEqual((m.group(1), m.group(2), m.group(3), m.group(7), m.group(8), m.group(9)), ("132", "0", "0", "2", "2", "0"))

    @unittest.skipUnless(os.path.isfile(PHYSICAL_AVSVC) and os.path.isfile(PHYSICAL_AVSVC_BLOCKS), "physical GBP-AV-SERVICE-001 fixture missing")
    def test_physical_avsvc_fixture_rejects_a_tampered_sidecar(self):
        with open(PHYSICAL_AVSVC_BLOCKS, "rb") as f:
            raw = bytearray(f.read())
        raw[0x100 + 0x20] ^= 0x01                                        # one audio payload bit
        bad = os.path.join(outdir(), "avsvc-0001-blocks-tampered.bin")
        with open(bad, "wb") as f:
            f.write(raw)
        run = subprocess.run([BIN, "--replay", PHYSICAL_AVSVC, bad], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertIn("bad sidecar", run.stderr)
        self.assertFalse(bad.startswith(os.path.join(ROOT, "captures")))

    @unittest.skipUnless(os.path.isfile(PHYSICAL_003A), "physical GBP-INIT-003A fixture missing")
    def test_physical_003a_fixture_stops_at_the_install(self):
        run = subprocess.run([BIN, "--replay", PHYSICAL_003A], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        summary = [l for l in run.stdout.splitlines() if l.startswith("SUMMARY ")][0]
        self.assertIn("status=abort_handler_install class=abort reason=irq_ops_unavailable restore=ok restore_reason=- teardown=S2_before_unmask", summary)
        self.assertIn("cause=1 t_event=4155517524 handler=0 old=? unmasked=0 fired=0 count=0", summary)
        m = REPLAY_RE.search(run.stdout)
        self.assertEqual((m.group(2), m.group(3), m.group(4), m.group(5), m.group(7)), ("0", "0", "0", "1", "0"))


if __name__ == "__main__":
    unittest.main()
