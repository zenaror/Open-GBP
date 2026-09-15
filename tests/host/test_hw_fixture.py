"""
Regression on the physical capture of 2026-09-14 (GBP-PROBE-001, probe-0001,
commit 55ed6c1): the versioned replay fixture must hold the exact bytes the
GameCube logged, and the tools must not normalize them.
"""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import blockdiff  # noqa: E402

FIXTURE = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-14-probe-0001.gbpreplay")


def reads(path):
    out = []
    for line in open(path, encoding="utf-8"):
        if line.startswith("R "):
            parts = line.split()
            out.append((int(parts[1], 16), parts[2], bytes.fromhex(parts[3]) if len(parts) > 3 else b""))
    return out


class HardwareFixture(unittest.TestCase):
    def setUp(self):
        self.reads = reads(FIXTURE)

    def test_structure(self):
        self.assertEqual(len(self.reads), 20)                    # 6 raw + 4 handshake reads per mode
        self.assertTrue(all(rc == "ok" and len(d) == 32 for _, rc, d in self.reads))
        addrs = [a for a, _, _ in self.reads]
        self.assertEqual(addrs[:3], [0x01000000, 0x01400000, 0x01d00000])

    def test_mode_a_bytes_verbatim(self):
        a = self.reads[:10]
        self.assertEqual(a[0][2], b"\x00" * 32)                  # TEST initial
        self.assertEqual(a[1][2], b"\x00" * 32)                  # CONTROL
        self.assertEqual(a[2][2], b"\x90" * 32)                  # IRQ
        self.assertEqual(a[3][2], b"\x7c" + b"\x3c" * 31)        # C3 → byte 0 anomalous
        self.assertEqual(a[4][2], b"\xc7\xc3\xc3\xc3\xc3\xc3\xc7" + b"\xc3" * 25)  # 3C → bytes 0 and 6
        self.assertEqual(a[5][2], b"\x00" * 32)                  # FF
        self.assertEqual(a[6][2], b"\xff" * 32)                  # 00
        self.assertEqual(a[7][2], b"\x00" * 32)                  # TEST after handshake

    def test_mode_b_bytes_verbatim(self):
        b = self.reads[10:]
        irq = bytes.fromhex("ae8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae")
        self.assertEqual(b[1][2], b"\x94" + b"\x90" * 31)        # CONTROL first read
        self.assertEqual(b[2][2], irq)
        self.assertEqual(b[3][2], b"\x3c" * 32)                  # C3 clean in MODE B
        self.assertEqual(b[4][2], b"\xc7" + b"\xc3" * 31)        # 3C → byte 0 only
        self.assertEqual(b[8][2], b"\x90" * 32)                  # CONTROL second read
        self.assertEqual(b[9][2], irq)

    def test_blockdiff_findings(self):
        irq = bytes.fromhex("ae8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae")
        self.assertIsNone(blockdiff.period(irq))
        self.assertEqual(blockdiff.period_ignoring(irq, {0}), 4)
        self.assertEqual(blockdiff.anomalies(irq), [(0, 0xae, 0x8a)])
        self.assertEqual(blockdiff.anomalies(b"\x7c" + b"\x3c" * 31), [(0, 0x7c, 0x3c)])
        self.assertEqual(blockdiff.anomalies(b"\xc7\xc3\xc3\xc3\xc3\xc3\xc7" + b"\xc3" * 25),
                         [(0, 0xc7, 0xc3), (6, 0xc7, 0xc3)])
        # u32 view of the IRQ block: word 0 differs from the rest only in byte 0
        words = [int.from_bytes(irq[i:i + 4], "big") for i in range(0, 32, 4)]
        self.assertEqual(words[0], 0xae8aaeae)
        self.assertTrue(all(w == 0x8a8aaeae for w in words[1:]))

    def test_official_driver_readings_of_the_physical_blocks(self):
        """What each known driver would have concluded from these bytes."""
        irq = bytes.fromhex("ae8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae")
        # Start-up Disc: 16-bit IRQ from bytes 0x1D/0x1F; control from 0x1F; TEST check on byte 1
        self.assertEqual((irq[0x1d] << 8) | irq[0x1f], 0x8aae)
        for resp, pat in ((b"\x7c" + b"\x3c" * 31, 0xc3), (b"\xc7\xc3\xc3\xc3\xc3\xc3\xc7" + b"\xc3" * 25, 0x3c)):
            self.assertEqual(resp[1], (~pat) & 0xff)
        # GBI: majority vote per bit over the 32 bytes (byte registers),
        # bytes 1 mod 4 (hi) and 3 mod 4 (lo) for 16-bit registers
        def vote(bs):
            return sum(1 << b for b in range(8) if sum((x >> b) & 1 for x in bs) * 2 > len(bs))
        self.assertEqual(vote(b"\x7c" + b"\x3c" * 31), 0x3c)
        self.assertEqual(vote(b"\xc7\xc3\xc3\xc3\xc3\xc3\xc7" + b"\xc3" * 25), 0xc3)
        hi = vote(irq[1::4]); lo = vote(irq[3::4])
        self.assertEqual((hi << 8) | lo, 0x8aae)


if __name__ == "__main__":
    unittest.main()


NOGBP = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-nogbp-2026-09-14-probe-0001.gbpreplay")


class HardwareFixtureNoGbp(unittest.TestCase):
    """Baseline without the Game Boy Player (GBP-BASELINE-NOGBP-001)."""

    def test_metadata_header(self):
        head = open(NOGBP, encoding="utf-8").read().splitlines()[:5]
        self.assertIn("# SOURCE=physical GameCube", head)
        self.assertIn("# GBP_PRESENT=no", head)
        self.assertIn("# DOL=probe-0001", head)
        self.assertIn("# COMMIT=55ed6c1", head)
        head_gbp = open(FIXTURE, encoding="utf-8").read().splitlines()[:5]
        self.assertIn("# GBP_PRESENT=yes", head_gbp)

    def test_every_block_is_c0(self):
        rs = reads(NOGBP)
        self.assertEqual(len(rs), 20)
        for addr, rc, d in rs:
            self.assertEqual(rc, "ok")
            self.assertEqual(d, b"\xc0" * 32, hex(addr))

    def test_arinfo_sequence_identical_to_gbp_run(self):
        def arinfo(path):
            return [l.strip() for l in open(path, encoding="utf-8") if l.startswith("A ")]
        self.assertEqual(arinfo(NOGBP), arinfo(FIXTURE))
        self.assertEqual(arinfo(NOGBP)[:2], ["A r 0043", "A r 0043"])
        self.assertIn("A w 005b", arinfo(NOGBP))
        self.assertIn("A w 0043", arinfo(NOGBP))

    def test_pair_never_equivalent(self):
        """Regression: the two physical runs must never be normalized into the same data."""
        with_gbp = {(i, a): d for i, (a, _, d) in enumerate(reads(FIXTURE))}
        without = {(i, a): d for i, (a, _, d) in enumerate(reads(NOGBP))}
        self.assertEqual(with_gbp.keys(), without.keys())       # same transfers, same addresses
        differing = [k for k in with_gbp if with_gbp[k] != without[k]]
        self.assertEqual(len(differing), 20)                     # every block differs
        xor_nonzero = sum(1 for k in with_gbp for p, q in zip(with_gbp[k], without[k]) if p != q)
        self.assertEqual(xor_nonzero, 640)                       # every byte differs

    def test_official_criteria_on_both_runs(self):
        def vote(bs):
            return sum(1 << b for b in range(8) if sum((x >> b) & 1 for x in bs) * 2 > len(bs))
        patterns = [0xc3, 0x3c, 0xff, 0x00]
        # handshake reads are transfers 3..6 and 13..16 of each fixture
        for path, expect_pass in ((FIXTURE, True), (NOGBP, False)):
            rs = reads(path)
            for base in (3, 13):
                for k, pat in enumerate(patterns):
                    d = rs[base + k][2]
                    disc = d[1] == ((~pat) & 0xff)
                    gbi = vote(d) == ((~pat) & 0xff)
                    self.assertEqual(disc, expect_pass, (path, base, pat))
                    self.assertEqual(gbi, expect_pass, (path, base, pat))

    def test_blockdiff_pair_reports_all_blocks(self):
        b1 = {("A", "x"): b"\x3c" * 32}
        b2 = {("A", "x"): b"\xc0" * 32}
        rows, same, diff_ = blockdiff.pair_table(b1, b2)
        self.assertEqual((len(rows), same, diff_), (32, [], ["MODE A x"]))
        self.assertTrue(all(x == 0xfc for _, _, _, _, x in rows))
