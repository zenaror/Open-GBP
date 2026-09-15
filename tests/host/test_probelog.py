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
        self.assertEqual(probelog.main(["check", p]), 1)


if __name__ == "__main__":
    unittest.main()
