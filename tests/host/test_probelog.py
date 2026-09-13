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
