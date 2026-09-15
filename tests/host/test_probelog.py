"""Tests for tools/probelog.py on a synthetic device log."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import probelog  # noqa: E402

INV_C3 = "3c" * 32
LOG = """# OPENGBP-LOG v1
test_id=GBP-PROBE-001
build_id=probe-0001
commit=abc1234-dirty
lines=12 dropped=0 truncated=0
# --- records ---
000000 IDENT test=GBP-PROBE-001 app=gbp-probe build=probe-0001 commit=abc1234-dirty libogc=libogc2
000001 PROBE start npatterns=1 nindices=1 exp_code=3 mode_b=1
000002 ARINFO orig value=0043 size_code=3 exp_code=0 base=01000000
000003 ARINFO modeA value=0043 size_code=3 exp_code=0 base=01000000
000004 MODE A begin base=01000000
000005 RAW mode=A idx=0 addr=01000000 rc=ok ticks=120 polls=3 dspcr=0000 data=%s
000006 TESTW mode=A idx=0 pattern=c3 rc=ok ticks=100 polls=2 dspcr=0000
000007 TESTR mode=A idx=0 pattern=c3 expect=3c rc=ok ticks=110 polls=2 dspcr=0000 match_all=1 match_1f=1 data=%s
000008 RAW mode=A idx=0 addr=01000000 rc=timeout ticks=999 polls=500 dspcr=0200 data=-
000009 ARINFO endA value=0043 size_code=3 exp_code=0 base=01000000
000010 ARINFO write mode=B value=005b rc=ok
000011 ARINFO restore value=0043 rc=ok
000012 ARINFO final value=0043 size_code=3 exp_code=0 base=01000000
000013 PROBE end modes=2 errors=1 changed=1 restored=1
# --- end --- dropped=0
""" % (INV_C3, INV_C3)


class ProbeLog(unittest.TestCase):
    def setUp(self):
        self.header, self.records = probelog.parse_lines(LOG.splitlines(True))

    def test_header_and_records(self):
        self.assertEqual(self.header["build_id"], "probe-0001")
        kinds = [r["kind"] for r in self.records]
        self.assertEqual(kinds.count("ARINFO"), 6)
        raw = [r for r in self.records if r["kind"] == "RAW"]
        self.assertEqual(raw[0]["fields"]["data_bytes"], bytes.fromhex(INV_C3))
        self.assertNotIn("data_bytes", raw[1]["fields"])
        self.assertEqual([r["tag"] for r in self.records if r["kind"] == "ARINFO"],
                         ["orig", "modeA", "endA", "write", "restore", "final"])

    def test_gecko_prefixed_lines_are_accepted(self):
        _, recs = probelog.parse_lines(["OPENGBP-PROBE LOG 000002 ARINFO orig value=0043\n"])
        self.assertEqual(recs[0]["fields"]["value"], "0043")

    def test_fixture(self):
        fx = probelog.fixture(self.records).splitlines()
        self.assertEqual(fx[1], "A r 0043")
        self.assertIn("R 01000000 ok " + INV_C3, fx)
        self.assertIn("W 01000000 ok", fx)
        self.assertIn("R 01000000 timeout", fx)
        self.assertIn("A w 005b", fx)
        self.assertIn("A w 0043", fx)
        self.assertEqual(fx[-1], "A r 0043")

    def test_fixture_init_irq_records(self):
        # GBP-INIT-002 records: PI reads become "P r"; the unmask becomes
        # "T t_unmask", "I u <handler record>", "T t_post"; the wait becomes the
        # loop-exit and t_wait_end time-base values; mask/restore become "I m"/"I r";
        # the single main-loop acknowledge becomes "P a". HANDLER/HANDLERPI feed "I u".
        _, recs = probelog.parse_lines([
            "000030 PI tag=UNMASKPRE rc=ok intsr=00010000 intmr=000001fa intsr13=0 intmr13=0\n",
            "000031 UNMASK t_unmask=100 rc=ok t_post=110 dt_post=10\n",
            "000032 PI tag=UNMASKPOST rc=ok intsr=00010000 intmr=000021fa intsr13=0 intmr13=1 fired=0\n",
            "000033 IRQ mask tag=MAIN rc=ok\n",
            "000034 WAIT fired=0 timed_out=1 polls=5 wait_ticks=400 wait_us=9 t_max_ms=2000 t_max_ticks=400\n",
            "000040 HANDLER fired=0 count=0 t_entry=0 t_unmask=100 latency_ticks=0 latency_us=0 reentry=0\n",
            "000041 HANDLERPI intsr_before_ack=00000000 intmr_at_entry=00000000 intsr_after_ack=00000000 intmr_after_mask=00000000 reentry_intsr=00000000 reentry_intmr=00000000\n",
            "000050 CLEANUP performed=1 value=00002000 rc=ok intsr_before=00012000 intsr_after=00010000 intsr13_after=0\n",
            "000051 IRQ restore rc=ok ok=1 old_handler=null\n",
            "000052 CLEANUP performed=0 intsr=00010000 intsr13=0 intmr13=0\n",
        ])
        fx = probelog.fixture(recs).splitlines()[1:]
        self.assertEqual(fx, ["P r 00010000 000001fa",
                              "T 100",
                              "I u 0 0 0 00000000 00000000 00000000 00000000 00000000 00000000",
                              "T 110",
                              "P r 00010000 000021fa",
                              "T 500", "T 500",
                              "I m",
                              "P a 00002000",
                              "I r"])
        # a handler that ran: its record travels on the "I u" line, and the wait ends at the first poll
        _, recs = probelog.parse_lines([
            "000031 UNMASK t_unmask=100 rc=ok t_post=110 dt_post=10\n",
            "000034 WAIT fired=1 timed_out=0 polls=1 wait_ticks=20 wait_us=0 t_max_ms=2000 t_max_ticks=400\n",
            "000040 HANDLER fired=1 count=1 t_entry=115 t_unmask=100 latency_ticks=15 latency_us=0 reentry=0\n",
            "000041 HANDLERPI intsr_before_ack=00012000 intmr_at_entry=000021fa intsr_after_ack=00010000 intmr_after_mask=000001fa reentry_intsr=00000000 reentry_intmr=00000000\n",
            "000042 IRQ install rc=ok old_handler=nonnull\n",
        ])
        fx = probelog.fixture(recs).splitlines()[1:]
        self.assertEqual(fx, ["T 100",
                              "I u 1 1 115 00012000 000021fa 00010000 000001fa 00000000 00000000",
                              "T 110",
                              "T 120",
                              "I i nonnull"])

    def test_fixture_initirqa_records(self):
        # GBP-INIT-003A records: IRQW becomes "W addr rc" + "T t_after"; CTLW with t_after likewise;
        # the EVENT snapshot becomes "T ticks" + "P p <polled INTSR>" before its own PI read;
        # WINDOW tag=A2 gives the t_window_end read. Nothing is emitted for the poll counters.
        _, recs = probelog.parse_lines([
            "000020 CTLW tag=EXP addr=01400000 semantic=8c rc=ok ticks=101 polls=1 dspcr=0020 t_after=1300 layout=gbi-replicated data=" + "8c" * 32 + "\n",
            "000030 RAW A1PRE idx=d addr=01d00000 rc=ok ticks=102 polls=1 dspcr=0020 sem_disc=8aae sem_gbi=8aae data=" + "8a8aaeae" * 8 + "\n",
            "000031 IRQW tag=A1 addr=01d00000 before=8aae write=8aae layout=gbi-u16-replicated rc=ok ticks=103 polls=1 dspcr=0020 t_after=1400 data=" + "8aae" * 16 + "\n",
            "000032 SNAP tag=A1-0 ticks=1410 since_control=110 since_a1=10 since_a2=0 polls_before=0\n",
            "000033 PI tag=A1-0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0\n",
            "000040 IRQW tag=A2 addr=01d00000 before=8aaa write=0000 layout=gbi-u16-replicated rc=ok ticks=104 polls=1 dspcr=0020 t_after=1600 data=" + "00" * 32 + "\n",
            "000041 SNAP tag=EVENT ticks=1900 since_control=600 since_a1=500 since_a2=300 polls_before=30 poll_intsr=00012000\n",
            "000042 PI tag=EVENT intsr=00012000 intmr=000001fa intsr13=1 intmr13=0\n",
            "000043 WINDOW tag=A2 deadlines=3/6 polls=30 poll_errors=0 ended_early=1 event=1 t_event=1900 intsr13_seen=1 t_first_intsr13=1900 first_phase=A2 t_end=1910 elapsed_ticks=310 elapsed_us=7 no_timebase=0\n",
            "000050 IRQW tag=STOP addr=01d00000 before=0100 write=8baa layout=gbi-u16-replicated rc=timeout ticks=105 polls=9 dspcr=0200 t_after=2000 data=" + "8baa" * 16 + "\n",
        ])
        fx = probelog.fixture(recs).splitlines()[1:]
        self.assertEqual(fx, ["W 01400000 ok", "T 1300",
                              "R 01d00000 ok " + "8a8aaeae" * 8,
                              "W 01d00000 ok", "T 1400",
                              "T 1410",
                              "P r 00010000 000001fa",
                              "W 01d00000 ok", "T 1600",
                              "T 1900", "P p 00012000",
                              "P r 00012000 000001fa",
                              "T 1910",
                              "W 01d00000 timeout", "T 2000"])

    def test_fixture_initirqb_records(self):
        # GBP-INIT-003B: HANDLERPI names the same record fields intsr_at_entry / intsr_after_w1c, HANDLERPI2
        # appends five numbers to "I u" (intsr_before_w1c t_second intsr_second intmr_second reentry_t);
        # the POSTACK main-loop W1C becomes "P a" before the MAINCLEANUP re-read; the MAIN mask keeps
        # the 002 rule (WAIT time-base reads first).
        _, recs = probelog.parse_lines([
            "000075 IRQ install rc=ok old_handler=null\n",
            "000082 PI tag=UNMASKPRE rc=ok intsr=00012000 intmr=000001fa intsr13=1 intmr13=0\n",
            "000083 UNMASK t_unmask=1470 rc=ok t_post=1583 dt_post=113\n",
            "000084 PI tag=UNMASKPOST rc=ok intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 fired=1\n",
            "000085 IRQ mask tag=MAIN rc=ok\n",
            "000086 WAIT fired=1 timed_out=0 polls=1 wait_ticks=123 wait_us=3 t_delivery_ms=100 t_delivery_ticks=400\n",
            "000087 PI tag=REMASKCHK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0\n",
            "000088 HANDLER fired=1 count=1 t_entry=1471 t_unmask=1470 latency_ticks=1 latency_us=0 reentry=0\n",
            "000089 HANDLERPI intsr_at_entry=00012000 intmr_at_entry=000021fa intmr_after_mask=000001fa intsr_before_w1c=00012000 intsr_after_w1c=00010000 reentry_intsr=00000000 reentry_intmr=00000000\n",
            "000090 HANDLERPI2 t_second=1573 dt_second=102 intsr_second=00010000 intmr_second=000001fa reentry_t=0\n",
            "000106 MAINPICLEANUP site=POSTACK performed=1 value=00002000\n",
            "000107 PI tag=MAINCLEANUP intsr=00010000 intmr=000001fa intsr13=0 intmr13=0\n",
            "000108 MAINPICLEANUP result rc=ok intsr_before=00012000 intsr_after=00010000 intsr13_after=0 sticky=0\n",
            "000118 IRQ restore rc=ok ok=1 old_handler=null\n",
        ])
        fx = probelog.fixture(recs).splitlines()[1:]
        self.assertEqual(fx, ["I i null",
                              "P r 00012000 000001fa",
                              "T 1470",
                              "I u 1 1 1471 00012000 000021fa 00010000 000001fa 00000000 00000000 00012000 1573 00010000 000001fa 0",
                              "T 1583",
                              "P r 00010000 000001fa",
                              "T 1593",
                              "I m",
                              "P r 00010000 000001fa",
                              "P a 00002000",
                              "P r 00010000 000001fa",
                              "I r"])
        # performed=0 emits nothing; a timed-out wait and the RETRY mask replay as in 002
        _, recs = probelog.parse_lines([
            "000083 UNMASK t_unmask=1470 rc=ok t_post=1583 dt_post=113\n",
            "000085 IRQ mask tag=MAIN rc=ok\n",
            "000086 WAIT fired=0 timed_out=1 polls=40 wait_ticks=400 wait_us=9 t_delivery_ms=100 t_delivery_ticks=400\n",
            "000087 PI tag=REMASKCHK intsr=00012000 intmr=000021fa intsr13=1 intmr13=1\n",
            "000088 IRQ mask tag=RETRY rc=ok\n",
            "000089 PI tag=REMASKCHK2 intsr=00012000 intmr=000001fa intsr13=1 intmr13=0\n",
            "000090 HANDLER fired=0 count=0 t_entry=0 t_unmask=1470 latency_ticks=0 latency_us=0 reentry=0\n",
            "000091 HANDLERPI intsr_at_entry=00000000 intmr_at_entry=00000000 intmr_after_mask=00000000 intsr_before_w1c=00000000 intsr_after_w1c=00000000 reentry_intsr=00000000 reentry_intmr=00000000\n",
            "000092 HANDLERPI2 t_second=0 dt_second=0 intsr_second=00000000 intmr_second=00000000 reentry_t=0\n",
            "000106 MAINPICLEANUP site=POSTACK performed=0 intsr13=0 intmr13=0\n",
        ])
        fx = probelog.fixture(recs).splitlines()[1:]
        self.assertEqual(fx, ["T 1470",
                              "I u 0 0 0 00000000 00000000 00000000 00000000 00000000 00000000 00000000 0 00000000 00000000 0",
                              "T 1583",
                              "T 1870", "T 1870",
                              "I m",
                              "P r 00012000 000021fa",
                              "I m",
                              "P r 00012000 000001fa"])

    def test_fixture_cleanup_ack_between_the_two_pi_reads(self):
        # The probe reads PI (CLEANUPCHK), writes INTSR once, re-reads PI (CLEANUP),
        # and only then logs the CLEANUP record: the "P a" line must sit between the
        # two "P r" lines, and must not be emitted twice.
        _, recs = probelog.parse_lines([
            "000060 PI tag=CLEANUPCHK intsr=00012000 intmr=000001fa intsr13=1 intmr13=0\n",
            "000061 PI tag=CLEANUP intsr=00010000 intmr=000001fa intsr13=0 intmr13=0\n",
            "000062 CLEANUP performed=1 value=00002000 rc=ok intsr_before=00012000 intsr_after=00010000 intsr13_after=0 sticky=0 ok=1\n",
        ])
        self.assertEqual(probelog.fixture(recs).splitlines()[1:],
                         ["P r 00012000 000001fa", "P a 00002000", "P r 00010000 000001fa"])
        _, recs = probelog.parse_lines([
            "000060 PI tag=CLEANUPCHK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0\n",
            "000062 CLEANUP performed=0 intsr=00010000 intsr13=0 intmr13=0 reason=intsr13_clear\n",
        ])
        self.assertEqual(probelog.fixture(recs).splitlines()[1:], ["P r 00010000 000001fa"])

    def test_fixture_note_marks_synthetic_scripts(self):
        fx = probelog.fixture(self.records, note="SYNTHETIC: host mock, not physical data").splitlines()
        self.assertEqual(fx[1], "# SYNTHETIC: host mock, not physical data")
        self.assertEqual(fx[2], "A r 0043")
        fx = probelog.fixture(self.records, note=["a", "b"]).splitlines()
        self.assertEqual(fx[1:3], ["# a", "# b"])

    def test_check(self):
        findings, anomalies = probelog.check(self.header, self.records)
        self.assertEqual(anomalies, 1)              # the timed-out RAW
        self.assertTrue(any("mode A: 1 handshakes, 1 uniform inverse" in f for f in findings))

    def test_cli(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "x.log")
        with open(p, "w") as f:
            f.write(LOG)
        self.assertEqual(probelog.main(["fixture", p, os.path.join(d, "x.gbpreplay")]), 0)
        self.assertTrue(os.path.getsize(os.path.join(d, "x.gbpreplay")) > 0)
        self.assertEqual(probelog.main(["fixture", p, os.path.join(d, "y.gbpreplay"), "--note", "SYNTHETIC test"]), 0)
        with open(os.path.join(d, "y.gbpreplay")) as f:
            self.assertEqual(f.read().splitlines()[1], "# SYNTHETIC test")
        self.assertEqual(probelog.main(["check", p]), 1)


if __name__ == "__main__":
    unittest.main()
