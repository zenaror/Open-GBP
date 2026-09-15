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


INITIRQ = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-15-initirq-0001.gbpreplay")


INITIRQA = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-15-initirqa-0001.gbpreplay")
INITIRQA_LOG = os.path.join(ROOT, "captures", "local", "GBP-INIT-003A_initirqa-0001.log")
INITIRQB = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-15-initirqb-0001.gbpreplay")
INITIRQB_LOG = os.path.join(ROOT, "captures", "local", "GBP-INIT-003B_initirqb-0001.log")


class HardwareFixtureInitIrqB(unittest.TestCase):
    """GBP-INIT-003B (2026-09-15, build initirqb-0001, commit d3da8cd): the first
    delivery of a real HSP cause to a CPU handler as IRQ 26. The fixture carries
    the physical time base (T), the four IRQ-register writes (A1 0x8AAE, A2
    0x0000, device ACK 0x8500, stop 0x8FAA), the INTSR poll that saw bit 13
    (P p), the interrupt path as it happened (I i / I u with the physical
    handler record / I m / I r), no main-loop PI W1C, and every raw block
    verbatim, including the offset-2 bytes that break the U-GBP-025 pattern."""

    def lines(self):
        return [l.rstrip("\n") for l in open(INITIRQB, encoding="utf-8")]

    def ops(self):
        return [l for l in self.lines() if l and not l.startswith("#")]

    def test_metadata_header(self):
        head = self.lines()[:16]
        for expect in ("# SOURCE=physical GameCube", "# GBP_PRESENT=yes", "# TEST_ID=GBP-INIT-003B",
                       "# BUILD_ID=initirqb-0001", "# COMMIT=d3da8cd",
                       "# DOL_SHA256=821aa2b2893b6d66fd1398eaeb7de7c475862728e55dc0922d74042d0e9cb757",
                       "# LOG_SHA256=bedb1f013176fec1b3de7c63c4147dfa6770f1eae8c9ec29ee82b027f9d7cf7c",
                       "# LOG_SIZE=17471"):
            self.assertIn(expect, head)
        self.assertTrue(any("pi_policy=never_unmasked" in l and "label defect" in l for l in head))
        self.assertFalse(any("SYNTHETIC" in l for l in head))

    @unittest.skipUnless(os.path.isfile(INITIRQB_LOG), "raw log not available locally")
    def test_records_regenerate_from_the_raw_log(self):
        import hashlib
        import probelog
        raw = open(INITIRQB_LOG, "rb").read()
        self.assertEqual(len(raw), 17471)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "bedb1f013176fec1b3de7c63c4147dfa6770f1eae8c9ec29ee82b027f9d7cf7c")
        header, records = probelog.parse_file(INITIRQB_LOG)
        self.assertEqual(header["test_id"], "GBP-INIT-003B")
        self.assertEqual(header["build_id"], "initirqb-0001")
        self.assertEqual(header["commit"], "d3da8cd")
        self.assertEqual(len(records), 140)
        gen = [l for l in probelog.fixture(records).splitlines() if l and not l.startswith("#")]
        self.assertEqual(gen, self.ops())
        # label defect of build initirqb-0001: the shared teardown printed its own policy although this run had unmasked once
        td = [r for r in records if r["kind"] == "TEARDOWN"][0]["fields"]
        self.assertEqual(td["pi_policy"], "never_unmasked")
        self.assertEqual((td["irq_attempted"], td["irq_completed"]), ("3", "3"))         # the stop word had not been written yet
        rb = [r for r in records if r["kind"] == "RESTOREB"][0]["fields"]
        self.assertEqual((rb["unmasked"], rb["masked_again"], rb["handler_restored"]), ("1", "1", "1"))
        w = [r for r in records if r["kind"] == "WRITES"][0]["fields"]
        self.assertEqual((w["irq_attempted"], w["irq_completed"]), ("4", "4"))          # A1, A2, ACK, STOP
        # the physical handler record, verbatim
        h = [r for r in records if r["kind"] == "HANDLER"][0]["fields"]
        self.assertEqual((h["fired"], h["count"], h["t_entry"], h["t_unmask"], h["latency_ticks"], h["reentry"]),
                         ("1", "1", "3679931582", "3679931504", "78", "0"))
        hp = [r for r in records if r["kind"] == "HANDLERPI"][0]["fields"]
        self.assertEqual((hp["intsr_at_entry"], hp["intmr_at_entry"], hp["intmr_after_mask"], hp["intsr_before_w1c"], hp["intsr_after_w1c"]),
                         ("00012000", "000021fa", "000001fa", "00012000", "00010000"))
        hp2 = [r for r in records if r["kind"] == "HANDLERPI2"][0]["fields"]
        self.assertEqual((hp2["t_second"], hp2["dt_second"], hp2["intsr_second"], hp2["intmr_second"], hp2["reentry_t"]),
                         ("3679931730", "148", "00010000", "000001fa", "0"))
        # the PI poll counters of the device run stay in the log only (the replay polls once per sample)
        win = [r for r in records if r["kind"] == "WINDOW" and r["fields"].get("tag") == "A2"][0]["fields"]
        self.assertEqual((win["polls"], win["intsr13_in_phase"], win["t_event"]), ("709726", "1", "3679890204"))

    def test_interrupt_path_as_it_happened(self):
        ops = self.ops()
        self.assertEqual(len(ops), 111)
        i_lines = [l for l in ops if l.startswith("I ")]
        self.assertEqual(i_lines, ["I i null",
                                   "I u 1 1 3679931582 00012000 000021fa 00010000 000001fa 00000000 00000000 00012000 3679931730 00010000 000001fa 0",
                                   "I m", "I r"])
        u = ops.index(i_lines[1])
        self.assertEqual(ops[u - 1], "T 3679931504")                     # t_unmask read before __UnmaskIrq
        self.assertEqual(ops[u + 1], "T 3679931761")                     # t_post_unmask after the call (257 ticks: the handler ran inside)
        self.assertEqual(ops[u + 2], "P r 00010000 000001fa")            # UNMASKPOST: cause already cleared by the ISR, mask already closed
        self.assertEqual(ops[ops.index("I m") - 1], "T 3679933491")      # t_wait_end (t_unmask + 1987), then the main re-mask
        self.assertEqual(ops[ops.index("I m") + 1], "P r 00010000 000001fa")   # REMASKCHK
        i = ops.index("I i null")
        self.assertGreater(i, ops.index("P p 00012000"))                 # installed after the EVENT
        self.assertLess(i, u)
        r = ops.index("I r")
        self.assertGreater(r, ops.index("T 3679954723"))                 # after the stop word's t_after
        self.assertEqual(ops[r + 1], "P r 00010000 000001fa")            # MASKCHK
        self.assertEqual(ops[r + 2], "A w 0043")                         # then the AR_INFO restore

    def test_writes_polls_and_acknowledge(self):
        ops = self.ops()
        self.assertEqual(ops.count("W 01d00000 ok"), 4)                  # A1, A2, ACK, STOP
        self.assertEqual(ops.count("W 01400000 ok"), 2)                  # CONTROL transform, restore
        self.assertEqual(ops.count("W 01000000 ok"), 4)                  # TEST handshake only
        self.assertEqual(ops.count("P p 00012000"), 1)                   # the poll that saw INTSR bit 13
        self.assertEqual([l for l in ops if l.startswith("P a")], [])    # no main-loop PI W1C: the ISR's W1C was the only one
        pi = [l for l in ops if l.startswith("P r ")]
        self.assertEqual(len(pi), 25)
        self.assertTrue(all(l.endswith(" 000001fa") for l in pi))        # INTMR bit 13 never set in a main-loop read
        self.assertEqual(pi.count("P r 00012000 000001fa"), 4)           # EVENT, PREUNMASK ×2, UNMASKPRE
        self.assertEqual(pi.count("P r 00010000 000001fa"), 21)          # every other read, including every one after the ISR
        p = ops.index("P p 00012000")
        self.assertEqual(ops[p - 1], "T 3679890204")
        self.assertEqual(ops[p + 1], "P r 00012000 000001fa")

    def test_irq_register_reads_verbatim(self):
        irq = [d for a, rc, d in reads(INITIRQB) if a == 0x01d00000]
        self.assertEqual(len(irq), 19)
        hx = [d.hex() for d in irq]
        self.assertEqual(hx[0], "8a8aaeae" * 8)                          # BASE 0x8AAE — no byte-0 extra in this run
        self.assertEqual(hx[1], hx[0]); self.assertEqual(hx[2], hx[0])   # P0, A1PRE
        self.assertEqual(hx[3], "8a8aaaaa" * 8)                          # A1-0: bit 2 cleared by A1
        for i in (4, 5, 6):                                              # A1-50US, A1-500US, A2PRE
            self.assertEqual(hx[i], hx[3])
        for i in range(7, 12):                                           # A2-0 … A2-50MS
            self.assertEqual(hx[i], "00" * 32)
        self.assertEqual(hx[12], "04040400" * 8)                         # EVENT 0x0400
        self.assertEqual(hx[13], "05050000" + "05050500" * 7)            # PREUNMASK 0x0500 (group 0: offset 2 = 00)
        self.assertEqual(hx[14], "05050500" * 8)                         # PREACK 0x0500: sources still pending after the ISR's W1C
        self.assertEqual(hx[15], "80800000" * 8)                         # POSTACK 0x8000: sources cleared by the ACK, bit 15 read 1
        self.assertEqual(hx[16], "85850000" * 2 + "85850400" * 2 + "85850000" + "85850400" + "85850000" + "85850400")   # IRQSTOPPRE 0x8500
        self.assertEqual(hx[17], "8a8aaaaa" * 8)                         # IRQSTOPPOST 0x8AAA
        self.assertEqual(hx[18], "90" * 32)                              # FINAL under expansion code 0: 0x9090
        ctl = [d.hex() for a, rc, d in reads(INITIRQB) if a == 0x01400000]
        self.assertEqual(len(ctl), 16)
        self.assertEqual(ctl[0], "90" * 32)
        self.assertTrue(all(c == "8c" * 32 for c in ctl[1:14]))          # P0 … POSTACK: 0x8C, no byte-0 extra
        self.assertEqual(ctl[14], "90" * 32)                             # TDCTL after the restore
        self.assertEqual(ctl[15], "00" * 32)                             # FINAL under expansion code 0
        test = [d.hex() for a, rc, d in reads(INITIRQB) if a == 0x01000000]
        self.assertEqual(test[:4], ["3c" * 32, "c3" * 32, "00" * 32, "ff" * 32])   # handshake, no byte-0 extras

    def test_timeline(self):
        ts = [int(l.split()[1]) for l in self.lines() if l.startswith("T ")]
        self.assertEqual(len(ts), 25)
        self.assertEqual(ts, sorted(ts))                                 # no wrap inside this run
        for t in (3675626133, 3679890204, 3679890512, 3679926960, 3679931504, 3679931761, 3679933491, 3679938859, 3679943682, 3679944700, 3679954723, 3679959967):
            self.assertIn(t, ts)
        self.assertEqual(3679890204 - 3675626133, 4264071)               # EVENT 105.29 ms after A2 (003A: 4263568)
        self.assertEqual(3679931761 - 3679931504, 257)                   # __UnmaskIrq call including the handler
        self.assertEqual(3679938859 - 3679931582, 7277)                  # PREACK 179.7 us after the handler entry

    def test_offset2_pattern_exceptions_are_documented_not_consumed(self):
        # U-GBP-025: the empirical `lo | (hi & 0x05)` pattern of the byte at offset 2 of each 4-byte group
        # holds for the 0x8AAE, 0x8AAA, 0x0000, 0x0400, 0x8000, 0x8AAA and 0x9090 reads of this run and for
        # groups 1–7 of the PREUNMASK 0x0500 read, but NOT for group 0 of that read (00) and NOT for any
        # group of the IRQSTOPPRE 0x8500 read (00 or 04 where the pattern predicts 05). Pinned as bytes.
        irq = [d for a, rc, d in reads(INITIRQB) if a == 0x01d00000]
        def mids(d):
            return [d[4 * g + 2] for g in range(8)]
        def predicted(d):
            return [d[4 * g + 3] | (d[4 * g + 1] & 0x05) for g in range(8)]
        for i in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 17, 18):
            self.assertEqual(mids(irq[i]), predicted(irq[i]), irq[i].hex())
        self.assertEqual(mids(irq[13]), [0x00] + [0x05] * 7)             # PREUNMASK 0x0500: group 0 breaks the pattern
        self.assertEqual(mids(irq[16]), [0x00, 0x00, 0x04, 0x04, 0x00, 0x04, 0x00, 0x04])   # IRQSTOPPRE 0x8500: no group follows it
        self.assertEqual(predicted(irq[16]), [0x05] * 8)


class HardwareFixtureInitIrqA(unittest.TestCase):
    """GBP-INIT-003A (2026-09-15, commit d956b1b): the first physical write of the
    GBP IRQ register with PI HSP masked throughout. The fixture carries the
    physical time base (T), the three IRQ-register writes (A1 0x8AAE, A2 0x0000,
    stop 0x8FAA), the INTSR poll that saw bit 13 (P p), the single PI W1C (P a)
    and every raw block verbatim."""

    def lines(self):
        return [l.rstrip("\n") for l in open(INITIRQA, encoding="utf-8")]

    def ops(self):
        return [l for l in self.lines() if l and not l.startswith("#")]

    def test_metadata_header(self):
        head = self.lines()[:16]
        for expect in ("# SOURCE=physical GameCube", "# GBP_PRESENT=yes", "# TEST_ID=GBP-INIT-003A",
                       "# BUILD_ID=initirqa-0001", "# COMMIT=d956b1b",
                       "# DOL_SHA256=8c225bd101a215982ac59d096630a9e13b34557e3cdf4eb8354298855232bfa5",
                       "# LOG_SHA256=ae9117457039727026f00e9ccb349d4af3c85ee6f4f436d290cd40cc0e672ef8",
                       "# LOG_SIZE=13231"):
            self.assertIn(expect, head)
        self.assertTrue(any("WINDOW tag=A1 intsr13_seen=1" in l and "formatter defect" in l for l in head))

    @unittest.skipUnless(os.path.isfile(INITIRQA_LOG), "raw log not available locally")
    def test_records_regenerate_from_the_raw_log(self):
        import hashlib
        import probelog
        raw = open(INITIRQA_LOG, "rb").read()
        self.assertEqual(len(raw), 13231)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "ae9117457039727026f00e9ccb349d4af3c85ee6f4f436d290cd40cc0e672ef8")
        _, records = probelog.parse_file(INITIRQA_LOG)
        gen = [l for l in probelog.fixture(records).splitlines() if l and not l.startswith("#")]
        self.assertEqual(gen, self.ops())
        # the source log's WINDOW A1 record carries the global flag (build defect), the primary records do not
        win = [r for r in records if r["kind"] == "WINDOW" and r["fields"].get("tag") == "A1"]
        self.assertEqual(win[0]["fields"]["intsr13_seen"], "1")
        a1_pi = [r for r in records if r["kind"] == "PI" and r["fields"].get("tag") in ("A1-0", "A1-50US", "A1-500US", "A2PRE")]
        self.assertEqual(len(a1_pi), 4)
        self.assertTrue(all(r["fields"]["intsr13"] == "0" for r in a1_pi))
        obs = [r for r in records if r["kind"] == "OBSERVED"][0]["fields"]
        self.assertEqual((obs["first_phase"], obs["t_first_intsr13"]), ("A2", "4155517524"))

    def test_writes_polls_and_acknowledge(self):
        ops = self.ops()
        self.assertEqual(len(ops), 85)
        self.assertEqual(ops.count("W 01d00000 ok"), 3)               # A1, A2, STOP
        self.assertEqual(ops.count("W 01400000 ok"), 2)               # CONTROL transform, restore
        self.assertEqual(ops.count("W 01000000 ok"), 4)               # TEST handshake only
        self.assertEqual(ops.count("P p 00012000"), 1)                # the poll that saw INTSR bit 13
        self.assertEqual(ops.count("P a 00002000"), 1)                # one PI W1C
        self.assertEqual([l for l in ops if l.startswith("I ")], [])  # no interrupt path: PI stayed masked
        a = ops.index("P a 00002000")
        self.assertEqual(ops[a - 1], "P r 00012000 000001fa")         # CLEANUPCHK: latched cause, INTMR masked
        self.assertEqual(ops[a + 1], "P r 00010000 000001fa")         # cleared by the W1C
        pi = [l for l in ops if l.startswith("P r ")]
        self.assertTrue(all(l.endswith(" 000001fa") for l in pi))      # INTMR bit 13 never set
        self.assertEqual(pi.count("P r 00012000 000001fa"), 2)        # EVENT snapshot and CLEANUPCHK
        # the P p line sits right after the EVENT time-base read and before the EVENT PI read
        p = ops.index("P p 00012000")
        self.assertEqual(ops[p - 1], "T 4155517524")
        self.assertEqual(ops[p + 1], "P r 00012000 000001fa")

    def test_irq_register_reads_verbatim(self):
        irq = [d for a, rc, d in reads(INITIRQA) if a == 0x01d00000]
        self.assertEqual(len(irq), 16)
        hx = [d.hex() for d in irq]
        self.assertEqual(hx[0], "ae8aaeae" + "8a8aaeae" * 7)          # BASE 0x8AAE
        self.assertEqual(hx[1], hx[0])                                 # P0
        self.assertEqual(hx[2], hx[0])                                 # A1PRE
        self.assertEqual(hx[3], "ae8aaaaa" + "8a8aaaaa" * 7)          # A1-0: bit 2 cleared by A1
        self.assertEqual(hx[4], hx[3]); self.assertEqual(hx[5], hx[3]); self.assertEqual(hx[6], hx[3])   # A1-50US, A1-500US, A2PRE
        for i in range(7, 12):                                          # A2-0, +50us, +500us, +5ms, +50ms
            self.assertEqual(hx[i], "00" * 32)
        self.assertEqual(hx[12], "04040400" * 8)                       # EVENT 0x0400
        self.assertEqual(hx[13], "05050400" + "05050500" * 7)          # IRQSTOPPRE 0x0500
        self.assertEqual(hx[14], "ae8aaaaa" + "8a8aaaaa" * 7)          # IRQSTOPPOST 0x8AAA
        self.assertEqual(hx[15], "90" * 32)                            # FINAL under expansion code 0: 0x9090
        ctl = [d.hex() for a, rc, d in reads(INITIRQA) if a == 0x01400000]
        self.assertEqual(ctl[0], "90" * 32)
        self.assertTrue(all(c == "ac" + "8c" * 31 for c in ctl[1:11]))   # P0 … EVENT: 0x8C with byte-0 extra 0x20
        self.assertEqual(ctl[11], "90" * 32)                           # TDCTL after the restore
        self.assertEqual(ctl[12], "00" * 32)                           # FINAL under expansion code 0

    def test_timeline_and_deadlines(self):
        ts = [int(l.split()[1]) for l in self.lines() if l.startswith("T ")]
        self.assertEqual(len(ts), 18)
        self.assertEqual(ts, sorted(ts))                               # no wrap inside this run
        self.assertIn(4155517524, ts)                                  # EVENT
        self.assertIn(4155517831, ts)                                  # end of the window
        t_a2 = 4151253956
        self.assertEqual(4155517524 - t_a2, 4263568)                   # 105.27 ms at 40.5 MHz
        self.assertNotIn(4151253956 + 20250000, ts)                    # the 500 ms sample was never reached

    def test_offset2_pattern_is_documented_not_consumed(self):
        # U-GBP-025: in every state recorded so far the byte at offset 2 of each 4-byte group equals
        # lo | (hi & 0x05); this test pins the observation, it does not assert a meaning.
        for a, rc, d in reads(INITIRQA):
            if a != 0x01d00000:
                continue
            for g in range(1, 8):
                hi, lo, mid = d[4 * g + 1], d[4 * g + 3], d[4 * g + 2]
                self.assertEqual(mid, lo | (hi & 0x05), d.hex())


class HardwareFixtureInitIrq(unittest.TestCase):
    """GBP-INIT-002 (2026-09-15, commit 4e3cb43): the physical run of the
    first PI HSP unmask. The fixture carries the physical time base (T),
    the interrupt-path operations as they happened (I), and a handler
    record of zeros — the handler never ran; no interrupt is replayed."""

    def lines(self):
        return [l.rstrip("\n") for l in open(INITIRQ, encoding="utf-8")]

    def test_metadata_header(self):
        head = self.lines()[:12]
        for expect in ("# SOURCE=physical GameCube", "# GBP_PRESENT=yes", "# TEST_ID=GBP-INIT-002",
                       "# BUILD_ID=initirq-0001", "# COMMIT=4e3cb43",
                       "# DOL_SHA256=1bd2bcf3f361e6482c888a523d45ea2fa2dc073f41918ebfab7803b1177343f2",
                       "# LOG_SHA256=e7ec3d83212fb183d8209452e2ce46cf391a696ff8a41720fd9f7701dbf1ea1d",
                       "# LOG_SIZE=6585"):
            self.assertIn(expect, head)

    def test_interrupt_path_as_it_happened(self):
        ls = self.lines()
        ops = [l for l in ls if l and not l.startswith("#")]
        self.assertEqual([l for l in ops if l.startswith("I ")],
                         ["I i null", "I u 0 0 0 00000000 00000000 00000000 00000000 00000000 00000000", "I m", "I m", "I r"])
        self.assertNotIn("P a 00002000", ops)                       # no main-loop acknowledge was needed
        pi = [l for l in ops if l.startswith("P r ")]
        self.assertEqual(pi.count("P r 00010000 000021fa"), 1)      # INTMR bit 13 = 1 exactly once: after __UnmaskIrq
        self.assertEqual(pi.count("P r 00010000 000001fa"), len(pi) - 1)
        self.assertTrue(all(l.startswith("P r 00010000 ") for l in pi))   # INTSR bit 13 never set
        # order: install < CONTROL write < unmask < mask; restore after the last mask, AR_INFO restore after it
        i = {k: ops.index(k) for k in ("I i null", "I m", "I r")}
        unmask = next(n for n, l in enumerate(ops) if l.startswith("I u "))
        ctlw = [n for n, l in enumerate(ops) if l == "W 01400000 ok"]
        self.assertLess(i["I i null"], ctlw[0])
        self.assertLess(ctlw[0], unmask)
        self.assertLess(unmask, i["I m"])
        last_mask = max(n for n, l in enumerate(ops) if l == "I m")
        self.assertLess(last_mask, i["I r"])
        self.assertLess(i["I r"], ops.index("A w 0043"))
        self.assertLess(ctlw[1], i["I r"])                          # CONTROL restored before the handler is removed

    def test_timeline(self):
        ts = [int(l.split()[1]) for l in self.lines() if l.startswith("T ")]
        self.assertEqual(len(ts), 10)
        self.assertEqual(ts, sorted(ts))
        self.assertIn(3267405264, ts)                                # t_unmask
        self.assertEqual(ts.count(3267405264 + 81000012), 2)         # loop exit and t_wait_end: 2.0000003 s at 40.5 MHz
        self.assertAlmostEqual(81000012 / 40.5e6, 2.0, places=5)

    def test_irq_block_8aae_to_8fae_verbatim(self):
        rs = [d for a, rc, d in reads(INITIRQ) if a == 0x01d00000]
        self.assertEqual(len(rs), 5)                                 # S0..S4
        s1, s2, s3, s4 = rs[1], rs[2], rs[3], rs[4]
        self.assertEqual(rs[0], s1)
        self.assertEqual(s1.hex(), "9b8aaeae" + "8a8aaeae" * 7)
        self.assertEqual(s2.hex(), "9f8fafae" + "8f8fafae" * 7)
        self.assertEqual(s3, s2)                                     # persists after the CONTROL restore
        self.assertEqual(s4.hex(), "91" + "90" * 31)                 # expansion code 0 view
        changed = [k for k in range(32) if s1[k] != s2[k]]
        self.assertEqual(len(changed), 24)
        self.assertEqual([k for k in range(32) if s1[k] == s2[k]], [k for k in range(3, 32, 4)])
        for k in range(1, 8):
            self.assertEqual([s1[4 * k + j] ^ s2[4 * k + j] for j in range(4)], [0x05, 0x05, 0x01, 0x00])
        for b, disc, gbi in ((s1, 0x8aae, 0x8aae), (s2, 0x8fae, 0x8fae)):
            self.assertEqual((b[0x1D] << 8) | b[0x1F], disc)
            hi = blockdiff.majority_byte(bytes(b[4 * k + 1] for k in range(8)))
            lo = blockdiff.majority_byte(bytes(b[4 * k + 3] for k in range(8)))
            self.assertEqual((hi << 8) | lo, gbi)
        self.assertEqual(0x8aae ^ 0x8fae, 0x0500)

    def test_control_stable_across_the_window(self):
        cs = [d for a, rc, d in reads(INITIRQ) if a == 0x01400000]
        self.assertEqual([c.hex()[:4] for c in cs], ["9190", "9d8c", "9d8c", "9190", "1100"])
        self.assertEqual(cs[1], cs[2])                               # S1 == S2: CONTROL unchanged while IRQ changed
        for c, sem in zip(cs, (0x90, 0x8c, 0x8c, 0x90, 0x00)):
            self.assertEqual(c[31], sem)
            self.assertTrue(all(x == sem for x in c[1:]))

    def test_test_handshake_byte0_extras(self):
        rs = [d for a, rc, d in reads(INITIRQ) if a == 0x01000000]
        self.assertEqual([r[0] for r in rs[:4]], [0x3d, 0xd3, 0x11, 0xff])
        self.assertEqual([r[1] for r in rs[:4]], [0x3c, 0xc3, 0x00, 0xff])
