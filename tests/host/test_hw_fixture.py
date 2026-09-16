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


INITIRQ4 = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-16-initirq4-0001.gbpreplay")
INITIRQ4_LOG = os.path.join(ROOT, "captures", "local", "GBP-INIT-004_initirq4-0001.log")


class HardwareFixtureInitIrq4(unittest.TestCase):
    """GBP-INIT-004 (2026-09-16, build initirq4-0001, commit 741630b): the first run of
    the bounded repeated-service experiment. One cycle was delivered and acknowledged;
    26.0 us after the ACK the IRQ register read 0x8400 (source 0x0400 present under
    bit 15 = 1, CONTROL 0x8C, PI bit 13 clear), so the conservative clean boundary
    ended the run: anomaly_source_not_cleared, NO re-arm written. The fixture carries
    the console's time base (T), the four IRQ-register writes (A1 0x8AAE, A2 0x0000,
    ACK 0x8500, stop 0x8EAA — no re-arm), the INTSR poll that saw bit 13 (P p), the
    interrupt path as it happened (I i, the generation I p 0, I u with the physical
    multi-cycle handler record, I m, I r), no main-loop PI W1C, and every raw block
    verbatim including this run's byte-0 extras."""

    def lines(self):
        return [l.rstrip("\n") for l in open(INITIRQ4, encoding="utf-8")]

    def ops(self):
        return [l for l in self.lines() if l and not l.startswith("#")]

    def test_metadata_header(self):
        head = self.lines()[:20]
        for expect in ("# SOURCE=physical GameCube", "# GBP_PRESENT=yes", "# TEST_ID=GBP-INIT-004", "# BUILD_ID=initirq4-0001",
                       "# COMMIT=741630b", "# DOL_SHA256=1da0d7b4f47200e914aba46510921b4a49a9bb8f01fd40940ebf50bd94ad010c",
                       "# LOG_SHA256=c9167224cb57f1c0df4858fbb147bbe0f1cd1f544b04a71a594786f4f2ee775b", "# LOG_SIZE=19247",
                       "# CAPTURED=2026-09-16"):
            self.assertIn(expect, head)
        self.assertTrue(any("PHYSICALLY EXECUTED 2026-09-16" in l for l in head))
        self.assertTrue(any("NO RE-ARM WAS EXECUTED" in l for l in head))
        self.assertFalse(any("SYNTHETIC" in l for l in head))

    @unittest.skipUnless(os.path.isfile(INITIRQ4_LOG), "raw log not available locally")
    def test_records_regenerate_from_the_raw_log(self):
        import hashlib
        import probelog
        raw = open(INITIRQ4_LOG, "rb").read()
        self.assertEqual(len(raw), 19247)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "c9167224cb57f1c0df4858fbb147bbe0f1cd1f544b04a71a594786f4f2ee775b")
        header, records = probelog.parse_file(INITIRQ4_LOG)
        self.assertEqual((header["test_id"], header["build_id"], header["commit"]), ("GBP-INIT-004", "initirq4-0001", "741630b"))
        self.assertEqual(len(records), 152)
        gen = [l for l in probelog.fixture(records).splitlines() if l and not l.startswith("#")]
        self.assertEqual(gen, self.ops())
        kinds = {r["kind"] for r in records}
        for k in ("PREPARE", "PREUNMASK4", "HANDLER4", "HANDLERPI2", "TEARDOWN4", "RESTORE4", "INITIRQ4", "P0CHK", "A2CHK"):
            self.assertIn(k, kinds)                                       # record kinds with digits are parsed
        end = [r for r in records if r["kind"] == "INITIRQ4" and r["fields"].get("status")][0]["fields"]
        self.assertEqual((end["status"], end["reason"], end["restore"], end["teardown"], end["errors"], end["transport_ok"]),
                         ("anomaly_source_not_cleared", "source_pending_after_ack_cycle_0", "ok", "S3_cycle_aborted", "0", "1"))
        cyc = [r for r in records if r["kind"] == "CYCLES"][0]["fields"]
        self.assertEqual((cyc["requested"], cyc["completed"], cyc["causes"], cyc["deliveries"], cyc["acks"], cyc["rearms"], cyc["next_causes"],
                          cyc["reentry"], cyc["unexpected"], cyc["isr_w1c"], cyc["main_w1c"], cyc["teardown_w1c"]),
                         ("3", "0", "1", "1", "1", "0", "0", "0", "0", "1", "0", "0"))
        w = [r for r in records if r["kind"] == "WRITES"][0]["fields"]
        self.assertEqual((w["irq_attempted"], w["irq_completed"], w["uncertain"]), ("4", "4", "0"))     # A1, A2, ACK, STOP — no re-arm
        h = [r for r in records if r["kind"] == "HANDLER"][0]["fields"]
        self.assertEqual((h["n"], h["fired"], h["count"], h["t_entry"], h["t_unmask"], h["latency_ticks"], h["reentry"]),
                         ("0", "1", "1", "1053156665", "1053156576", "89", "0"))
        hp = [r for r in records if r["kind"] == "HANDLERPI"][0]["fields"]
        self.assertEqual((hp["intsr_at_entry"], hp["intmr_at_entry"], hp["intmr_after_mask"], hp["intsr_before_w1c"], hp["intsr_after_w1c"]),
                         ("00012000", "000021fa", "000001fa", "00012000", "00010000"))
        hp2 = [r for r in records if r["kind"] == "HANDLERPI2"][0]["fields"]
        self.assertEqual((hp2["t_second"], hp2["dt_second"], hp2["intsr_second"], hp2["intmr_second"], hp2["reentry_t"]),
                         ("1053156807", "142", "00010000", "000001fa", "0"))
        post = [r for r in records if r["kind"] == "POSTACK"][0]["fields"]
        self.assertEqual((post["intsr13"], post["intmr13"], post["control"], post["irq"], post["src_pending"], post["bit15"], post["ack"]),
                         ("0,0", "0", "8c", "8400/8400", "0400", "1", "1/1"))
        multi = [r for r in records if r["kind"] == "MULTI" and "unmasks" in r["fields"]][0]["fields"]
        self.assertEqual((multi["expected_gen"], multi["entries_total"], multi["generation_errors"], multi["anomaly_count"], multi["unmasks"]),
                         ("0", "1", "0", "1", "1"))
        win = [r for r in records if r["kind"] == "WINDOW" and r["fields"].get("tag") == "A2"][0]["fields"]
        self.assertEqual((win["polls"], win["intsr13_in_phase"], win["t_event"], win["elapsed_us"]), ("740559", "1", "1053111645", "105291"))
        self.assertEqual([r["kind"] for r in records if r["kind"] in ("REARM", "REARMPOST", "NEXTCAUSE", "PICLEAN", "BOUNDARY")], [])

    def test_interrupt_path_as_it_happened(self):
        ops = self.ops()
        self.assertEqual(len(ops), 112)
        i_lines = [l for l in ops if l.startswith("I ")]
        self.assertEqual(i_lines, ["I i null", "I p 0",
                                   "I u 1 1 1053156665 00012000 000021fa 00010000 000001fa 00000000 00000000 00012000 1053156807 00010000 000001fa 0",
                                   "I m", "I r"])
        i = ops.index("I i null"); p = ops.index("I p 0"); u = ops.index(i_lines[2]); m = ops.index("I m"); r = ops.index("I r")
        self.assertGreater(i, ops.index("P p 00012000"))                  # installed after the EVENT
        self.assertLess(i, p); self.assertLess(p, u)                       # generation published before the unmask …
        self.assertEqual(ops[p + 1], "T 1053151004")                       # … and before the PREUNMASK-0 snapshot
        self.assertEqual(ops[u - 1], "T 1053156576")                       # t_unmask read before __UnmaskIrq
        self.assertEqual(ops[u + 1], "T 1053156832")                       # t_post_unmask after the call (256 ticks: the handler ran inside)
        self.assertEqual(ops[u + 2], "P r 00010000 000001fa")              # UNMASKPOST: cause cleared by the ISR, mask closed
        self.assertEqual(ops[m - 1], "T 1053158677")                       # t_wait_end (t_unmask + 2101), then the main re-mask
        self.assertEqual(ops[m + 1], "P r 00010000 000001fa")              # REMASKCHK
        self.assertGreater(r, ops.index("T 1053182290"))                   # after the stop word's t_after
        self.assertEqual(ops[r + 1], "P r 00010000 000001fa")              # MASKCHK
        self.assertEqual(ops[r + 2], "A w 0043")                           # then the AR_INFO restore

    def test_writes_polls_and_acknowledge(self):
        ops = self.ops()
        self.assertEqual(ops.count("W 01d00000 ok"), 4)                    # A1, A2, ACK, STOP: NO re-arm
        self.assertEqual(ops.count("W 01400000 ok"), 2)                    # CONTROL transform, restore: never per cycle
        self.assertEqual(ops.count("W 01000000 ok"), 4)                    # TEST handshake only
        self.assertEqual(ops.count("P p 00012000"), 1)
        self.assertEqual([l for l in ops if l.startswith("P a")], [])      # no main-loop PI W1C
        pi = [l for l in ops if l.startswith("P r ")]
        self.assertEqual(len(pi), 25)
        self.assertTrue(all(l.endswith(" 000001fa") for l in pi))          # INTMR bit 13 never set in a main-loop read
        self.assertEqual(pi.count("P r 00012000 000001fa"), 4)             # EVENT, PREUNMASK-0 ×2, UNMASKPRE-0
        self.assertEqual(pi.count("P r 00010000 000001fa"), 21)            # every other read, all after the ISR's W1C
        a = ops.index("W 01d00000 ok", ops.index("I m"))                   # the ACK write (after the re-mask)
        self.assertEqual(ops[a + 1], "T 1053170192")
        self.assertEqual(ops[a + 2], "T 1053171245")                       # POSTACK-0 snapshot 1053 ticks = 26.0 us later
        self.assertEqual(ops[a + 3], "P r 00010000 000001fa"); self.assertEqual(ops[a + 4], "P r 00010000 000001fa")
        self.assertTrue(ops[a + 6].startswith("R 01d00000 ok 8484040084840400"))   # 0x8400: 0x0400 present, bit 15 = 1

    def test_irq_register_reads_verbatim(self):
        irq = [d for a, rc, d in reads(INITIRQ4) if a == 0x01d00000]
        self.assertEqual(len(irq), 19)
        hx = [d.hex() for d in irq]
        self.assertEqual(hx[0], "8e8aaeae" + "8a8aaeae" * 7)               # BASE 0x8AAE with the byte-0 extra 0x04
        self.assertEqual(hx[1], hx[0]); self.assertEqual(hx[2], hx[0])     # P0, A1PRE
        self.assertEqual(hx[3], "8e8aaaaa" + "8a8aaaaa" * 7)               # A1-0: bit 2 cleared by A1
        for i in (4, 5, 6):
            self.assertEqual(hx[i], hx[3])                                 # A1-50US, A1-500US, A2PRE
        for i in range(7, 12):
            self.assertEqual(hx[i], "00" * 32)                             # A2-0 … A2-50MS
        self.assertEqual(hx[12], "04040400" * 8)                           # EVENT 0x0400, no extra
        self.assertEqual(hx[13], "8d050400" + "05050500" * 7)              # PREUNMASK-0 0x0500 (byte 0 extra 0x88; group 0 offset 2 = 04)
        self.assertEqual(hx[14], "85050400" + "05050500" * 7)              # PREACK-0 0x0500 (byte 0 extra 0x80; group 0 offset 2 = 04)
        self.assertEqual(hx[15], "84840400" * 8)                           # POSTACK-0 0x8400: 0x0400 present, 0x0100 absent, bit 15 = 1
        self.assertEqual(hx[16], "84840400" * 8)                           # IRQSTOPPRE 0x8400 (after the CONTROL restore): unchanged
        self.assertEqual(hx[17], "8e8aaaaa" + "8a8aaaaa" * 7)              # IRQSTOPPOST 0x8AAA after the stop 0x8EAA
        self.assertEqual(hx[18], "90" * 32)                                # FINAL under expansion code 0: 0x9090
        ctl = [d.hex() for a, rc, d in reads(INITIRQ4) if a == 0x01400000]
        self.assertEqual(len(ctl), 16)
        self.assertEqual(ctl[0], "90" * 32)
        self.assertTrue(all(c == "ac" + "8c" * 31 for c in ctl[1:14]))     # P0 … POSTACK-0: 0x8C with the byte-0 extra 0x20 in every read
        self.assertEqual(ctl[14], "90" * 32)                               # TDCTL after the restore
        self.assertEqual(ctl[15], "00" * 32)                               # FINAL under expansion code 0
        test = [d.hex() for a, rc, d in reads(INITIRQ4) if a == 0x01000000]
        self.assertEqual(test[:4], ["3c" * 32, "c7" + "c3" * 31, "00" * 32, "ff" * 32])   # handshake: one byte-0 extra (0x04)

    def test_timeline(self):
        ts = [int(l.split()[1]) for l in self.lines() if l.startswith("T ")]
        self.assertEqual(len(ts), 25)
        self.assertEqual(ts, sorted(ts))                                   # no wrap inside this run
        for t in (1048847666, 1053111645, 1053111989, 1053151004, 1053156576, 1053156832, 1053158677, 1053165161, 1053170192, 1053171245,
                  1053177991, 1053182290, 1053187586):
            self.assertIn(t, ts)
        self.assertEqual(1053111645 - 1048847666, 4263979)                 # EVENT 105.283 ms after A2 (003B: 4264071, 003A: 4263568)
        self.assertEqual(1053156832 - 1053156576, 256)                     # __UnmaskIrq call including the handler
        self.assertEqual(1053165161 - 1053156665, 8496)                    # PREACK-0 209.8 us after the handler entry
        self.assertEqual(1053171245 - 1053170192, 1053)                    # POSTACK-0 26.0 us after the ACK

    def test_offset2_pattern_exceptions_are_documented_not_consumed(self):
        # U-GBP-025: the empirical `lo | (hi & 0x05)` pattern holds for every 0x8AAE, 0x8AAA, 0x0000, 0x0400, 0x8400, 0x8AAA
        # and 0x9090 read of this run and for groups 1–7 of the two 0x0500 reads, but NOT for group 0 of either
        # 0x0500 read (`04` where the pattern predicts `05`, as 003B's group 0 `00` did). Pinned as bytes.
        irq = [d for a, rc, d in reads(INITIRQ4) if a == 0x01d00000]
        def mids(d):
            return [d[4 * g + 2] for g in range(8)]
        def predicted(d):
            return [d[4 * g + 3] | (d[4 * g + 1] & 0x05) for g in range(8)]
        for i in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15, 16, 17, 18):
            self.assertEqual(mids(irq[i]), predicted(irq[i]), irq[i].hex())
        for i in (13, 14):
            self.assertEqual(mids(irq[i]), [0x04] + [0x05] * 7)            # PREUNMASK-0 / PREACK-0 0x0500: group 0 breaks the pattern
            self.assertEqual(predicted(irq[i]), [0x05] * 8)


AVSVC = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-16-avsvc-0001.gbpreplay")
AVSVC_BLOCKS = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-16-avsvc-0001-blocks.bin")
AVSVC_LOG = os.path.join(ROOT, "captures", "local", "GBP-AV-SERVICE-001_avsvc-0001.log")
AVSVC_LOG_BLOCKS = os.path.join(ROOT, "captures", "local", "GBP-AV-SERVICE-001_avsvc-0001-blocks.bin")


class HardwareFixtureAvsvc(unittest.TestCase):
    """GBP-AV-SERVICE-001 (2026-09-16, build avsvc-0001, commit d3a6d23): the first drained
    service pass on hardware. One delivery (72 ticks), PRESVC 0x0500, AUDIO 0x1000 and VIDEO
    0xF00 each read by one whole-block DMA (2692 / 2485 ticks around the call), POSTDRAIN still
    0x0500 with PI clear, ACK 0x8500, POSTACK 0x8000 26 us later with PI clear and no main
    W1C, re-arm 0x0000, REARMPOST 43.9 us later: INTSR bit 13 = 1 with IRQ 0x0400 (outcome
    B), the next cause found at once and never delivered, teardown S4B (stop 0x8FAA -> 0x8AAA,
    one PI W1C). The script carries the console's time base (T), the five IRQ-register writes
    (A1, A2, ACK, REARM, STOP), the INTSR poll that saw bit 13, the interrupt path as it
    happened (I i, I u with the physical extended one-shot record, I m, I r), the two
    whole-block reads as "B" lines whose bytes live in the sidecar next to the script, one
    teardown W1C (P a) and every raw block verbatim."""

    def lines(self):
        return [l.rstrip("\n") for l in open(AVSVC, encoding="utf-8")]

    def ops(self):
        return [l for l in self.lines() if l and not l.startswith("#")]

    def test_metadata_header(self):
        import hashlib
        head = [l for l in self.lines() if l.startswith("#")]
        for needle in ("# SOURCE=physical GameCube", "# GBP_PRESENT=yes", "# PHYSICAL_RUN_ID=GBP-AV-SERVICE-001", "# TEST_ID=GBP-AV-SERVICE-001",
                       "# BUILD_ID=avsvc-0001", "# DOL=avsvc-0001", "# COMMIT=d3a6d23",
                       "# DOL_SHA256=d9e6dccd6f6ac2a729cc1be904214dbaf6f0bd88ee2929244b185a5ba39556ff",
                       "# LOG_SHA256=d0324b6d12f02984a0d748f896f1c16f724d69c0e3022bef5460f8ed32a03713", "# LOG_SIZE=23154",
                       "# BLOCKS=hw-gamecube-gbp-2026-09-16-avsvc-0001-blocks.bin",
                       "# BLOCKS_SHA256=1c17a2d77fa60b4446863032ced62cc3d2390625de2a42b120a195eb074edc1e", "# BLOCKS_SIZE=8204",
                       "# CAPTURED=2026-09-16", "# generated by tools/probelog.py from a device log"):
            self.assertIn(needle, head)
        self.assertTrue(any(l.startswith("# NOTE=GBP-AV-SERVICE-001 PHYSICALLY EXECUTED 2026-09-16") for l in head))
        self.assertFalse(any("SYNTHETIC" in l for l in head))
        with open(AVSVC_BLOCKS, "rb") as f:
            raw = f.read()
        self.assertEqual(len(raw), 8204)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "1c17a2d77fa60b4446863032ced62cc3d2390625de2a42b120a195eb074edc1e")
        if os.path.isfile(AVSVC_LOG_BLOCKS):
            with open(AVSVC_LOG_BLOCKS, "rb") as f:
                self.assertEqual(f.read(), raw)                            # the fixture's sidecar is the console's file, byte for byte
        if os.path.isfile(AVSVC_LOG):
            with open(AVSVC_LOG, "rb") as f:
                log = f.read()
            self.assertEqual((len(log), hashlib.sha256(log).hexdigest()), (23154, "d0324b6d12f02984a0d748f896f1c16f724d69c0e3022bef5460f8ed32a03713"))

    @unittest.skipUnless(os.path.isfile(AVSVC_LOG), "local raw log not present (captures/local is not versioned)")
    def test_records_regenerate_from_the_raw_log(self):
        import probelog
        header, records = probelog.parse_file(AVSVC_LOG)
        self.assertEqual((header["test_id"], header["build_id"], header["commit"]), ("GBP-AV-SERVICE-001", "avsvc-0001", "d3a6d23"))
        with open(AVSVC_LOG, encoding="utf-8") as f:
            self.assertIn("sidecar=GBP-AV-SERVICE-001_avsvc-0001-blocks.bin", f.read(400))   # the log names its sidecar
        self.assertEqual(len(records), 182)
        gen = [l for l in probelog.fixture(records).splitlines() if l and not l.startswith("#")]
        self.assertEqual(gen, self.ops())
        kinds = {r["kind"] for r in records}
        for k in ("AVSVC", "PREUNMASKAV", "PRESVC", "SVC", "AUDIOREAD", "VIDEOREAD", "SVCEND", "POSTDRAIN", "POSTACKAV", "PICLEAN", "REARM",
                  "REARMPOST", "NEXTCAUSE", "TEARDOWNAV", "SERVICE", "COUNTERS", "BLOCK", "BLOCKW", "TIMING", "RESTOREAV"):
            self.assertIn(k, kinds)
        end = [r for r in records if r["kind"] == "AVSVC" and r["fields"].get("status")][0]["fields"]
        self.assertEqual((end["status"], end["class"], end["restore"], end["teardown"], end["errors"], end["transport_ok"], end["power_cycle_required"]),
                         ("ok_service_rearm_cause_observed", "ok", "ok", "S4B_next_cause_latched", "0", "1", "1"))
        c = [r for r in records if r["kind"] == "COUNTERS"][0]["fields"]
        self.assertEqual((c["unmasks"], c["deliveries"], c["acks"], c["rearms"], c["next_causes"], c["unexpected"], c["isr_w1c"], c["main_w1c"],
                          c["teardown_w1c"], c["w1c_total"], c["control_ok"], c["uncertain"]), ("1", "1", "1", "1", "1", "0000", "1", "0", "1", "2", "1", "0"))
        h = [r for r in records if r["kind"] == "HANDLER"][0]["fields"]
        self.assertEqual((h["fired"], h["count"], h["t_entry"], h["t_unmask"], h["latency_ticks"], h["reentry"]), ("1", "1", "3391371694", "3391371622", "72", "0"))
        hp = [r for r in records if r["kind"] == "HANDLERPI"][0]["fields"]
        self.assertEqual((hp["intsr_at_entry"], hp["intmr_at_entry"], hp["intmr_after_mask"], hp["intsr_before_w1c"], hp["intsr_after_w1c"]),
                         ("00012000", "000021fa", "000001fa", "00012000", "00010000"))
        reads = {r["kind"]: r["fields"] for r in records if r["kind"] in ("AUDIOREAD", "VIDEOREAD")}
        self.assertEqual((reads["AUDIOREAD"]["addr"], reads["AUDIOREAD"]["len"], reads["AUDIOREAD"]["rc"], reads["AUDIOREAD"]["dt"],
                          reads["AUDIOREAD"]["wait_ticks"], reads["AUDIOREAD"]["polls"], reads["AUDIOREAD"]["csr_before"], reads["AUDIOREAD"]["csr_after"]),
                         ("01800000", "1000", "ok", "2692", "2475", "760", "0804", "0804"))
        self.assertEqual((reads["VIDEOREAD"]["addr"], reads["VIDEOREAD"]["len"], reads["VIDEOREAD"]["rc"], reads["VIDEOREAD"]["dt"],
                          reads["VIDEOREAD"]["wait_ticks"], reads["VIDEOREAD"]["polls"]), ("01100000", "0f00", "ok", "2485", "2319", "712"))
        t = [r for r in records if r["kind"] == "TIMING"][0]["fields"]
        self.assertEqual((t["cause_to_isr"], t["isr_to_presvc"], t["presvc_to_ack"], t["service"], t["ack_to_postack"], t["postack_to_rearm"],
                          t["rearm_to_next_cause"]), ("42530/1050us", "7612", "20674", "10997/271us", "1048", "7190", "1778/43us"))
        win = [r for r in records if r["kind"] == "WINDOW" and r["fields"].get("tag") == "A2"][0]["fields"]
        self.assertEqual((win["polls"], win["intsr13_in_phase"], win["t_event"], win["elapsed_us"]), ("740594", "1", "3391329164", "105296"))
        st = [r for r in records if r["kind"] == "STATS"][0]["fields"]
        self.assertEqual((st["transfers"], st["timeouts"], st["busy"], st["bulk_transfers"], st["bulk_bytes"]), ("58", "0", "0", "2", "7936"))
        # the BLOCK / BLOCKW records of the log describe the sidecar's bytes
        import avdump
        with open(AVSVC_BLOCKS, "rb") as f:
            info = avdump.parse(f.read())
        blk = {r["fields"]["kind"]: r["fields"] for r in records if r["kind"] == "BLOCK"}
        self.assertEqual((blk["audio"]["crc32"], blk["audio"]["zeros"], blk["audio"]["distinct"], blk["audio"]["first_word"], blk["audio"]["gbi_frame_start"]),
                         ("fec5e4e7", "3969", "3", "01000000", "0"))
        self.assertEqual((blk["video"]["crc32"], blk["video"]["zeros"], blk["video"]["distinct"], blk["video"]["first_word"], blk["video"]["gbi_frame_start"]),
                         ("fe45ff08", "0", "2", "ffffffff", "1"))
        self.assertEqual(int(blk["audio"]["zeros"]), info["audio"].count(0))
        self.assertEqual(int(blk["video"]["zeros"]), info["video"].count(0))
        windows = {(r["fields"]["kind"], int(r["fields"]["off"], 16)): r["fields"]["data"] for r in records if r["kind"] == "BLOCKW"}
        self.assertEqual(sorted(windows), [("audio", 0x0), ("audio", 0x540), ("audio", 0xAA0), ("audio", 0xFE0),
                                           ("video", 0x0), ("video", 0x500), ("video", 0xA00), ("video", 0xEE0)])
        for (kind, off), hx in windows.items():
            self.assertEqual(info[kind][off:off + 32].hex(), hx)

    def test_interrupt_path_and_block_reads_as_they_happened(self):
        ops = self.ops()
        self.assertEqual(len(ops), 132)
        i_lines = [l for l in ops if l.startswith("I ")]
        self.assertEqual(i_lines, ["I i null",
                                   "I u 1 1 3391371694 00012000 000021fa 00010000 000001fa 00000000 00000000 00012000 3391371841 00010000 000001fa 0",
                                   "I m", "I r"])                         # one delivery; no generation line (003B extended one-shot)
        i = ops.index("I i null"); u = ops.index(i_lines[1]); m = ops.index("I m"); r = ops.index("I r")
        self.assertGreater(i, ops.index("P p 00012000"))                  # installed after the EVENT
        self.assertEqual(ops[u - 1], "T 3391371622")                       # t_unmask read before __UnmaskIrq
        self.assertEqual(ops[u + 1], "T 3391371862")                       # t_post_unmask (240 ticks: the handler ran inside)
        self.assertEqual(ops[u + 2], "P r 00010000 000001fa")              # UNMASKPOST: cause cleared by the ISR, mask closed
        self.assertEqual(ops[m - 1], "T 3391373682")                       # t_wait_end, then the main re-mask
        self.assertEqual(ops[m + 1], "P r 00010000 000001fa")              # REMASKCHK
        b_lines = [l for l in ops if l.startswith("B ")]
        self.assertEqual(b_lines, ["B 01800000 00001000 ok fec5e4e7", "B 01100000 00000f00 ok fe45ff08"])
        a = ops.index(b_lines[0]); v = ops.index(b_lines[1])
        self.assertEqual((ops[a - 1], ops[a + 1]), ("T 3391385098", "T 3391387790"))    # AUDIO: 2692 ticks around the call
        self.assertEqual((ops[v - 1], ops[v + 1]), ("T 3391387818", "T 3391390303"))    # VIDEO: 2485 ticks, after AUDIO completed
        self.assertEqual(ops[a - 2], "R 01d00000 ok 1705010005050500050505000505050005050500050505000505050005050500")   # PRESVC 0x0500
        self.assertLess(m, a); self.assertLess(v, ops.index("W 01d00000 ok", v))       # masked before the drain; ACK after the drain
        self.assertGreater(r, ops.index("P a 00002000"))                   # restored after the teardown W1C
        self.assertEqual(ops[r + 1], "P r 00010000 000001fa")              # MASKCHK
        self.assertEqual(ops[r + 2], "A w 0043")                           # then the AR_INFO restore

    def test_writes_polls_acknowledge_and_rearm(self):
        ops = self.ops()
        self.assertEqual(ops.count("W 01d00000 ok"), 5)                    # A1, A2, ACK, REARM, STOP
        self.assertEqual(ops.count("W 01400000 ok"), 2)                    # CONTROL transform, restore
        self.assertEqual(ops.count("W 01000000 ok"), 4)                    # TEST handshake only
        self.assertEqual(ops.count("P p 00012000"), 1)
        self.assertEqual([l for l in ops if l.startswith("P a")], ["P a 00002000"])   # one W1C, in the teardown
        pi = [l for l in ops if l.startswith("P r ")]
        self.assertEqual(len(pi), 30)
        self.assertTrue(all(l.endswith(" 000001fa") for l in pi))          # INTMR bit 13 never set in a main-loop read
        self.assertEqual(pi.count("P r 00012000 000001fa"), 7)             # EVENT, PREUNMASK ×2, UNMASKPRE, REARMPOST ×2, CLEANUPCHK
        self.assertEqual(pi.count("P r 00010000 000001fa"), 23)
        w = [k for k, l in enumerate(ops) if l == "W 01d00000 ok"]
        ack, rearm, stop = w[2], w[3], w[4]
        self.assertEqual(ops[ack - 1], "R 01d00000 ok 1705010005050500050505000505050005050500050504000505050005050500")   # POSTDRAIN 0x0500 (group 5: 04)
        self.assertEqual(ops[ack + 1], "T 3391399980")
        self.assertEqual(ops[ack + 2], "T 3391401028")                     # POSTACK snapshot 1048 ticks = 25.9 us after the ACK
        self.assertEqual(ops[ack + 3], "P r 00010000 000001fa"); self.assertEqual(ops[ack + 4], "P r 00010000 000001fa")
        self.assertEqual(ops[ack + 6], "R 01d00000 ok 8180000080800000808000008080000080800000808000008080000080800000")   # 0x8000
        self.assertEqual(ops[rearm - 1], "T 3391408218")                   # t_rearm
        self.assertEqual(ops[rearm + 1], "T 3391408974")
        self.assertEqual(ops[rearm + 2], "T 3391409996")                   # REARMPOST snapshot 1778 ticks after t_rearm
        self.assertEqual(ops[rearm + 3], "P r 00012000 000001fa"); self.assertEqual(ops[rearm + 4], "P r 00012000 000001fa")
        self.assertEqual(ops[rearm + 6], "R 01d00000 ok 1504000004040400040404000404040004040400040404000404040004040400")   # 0x0400
        self.assertEqual(ops[rearm + 7], "W 01400000 ok")                  # the teardown begins at once (no next-cause poll)
        self.assertEqual(ops[stop - 1], "R 01d00000 ok 1705010005050500050505000505050005050500050505000505050005050500")   # IRQSTOPPRE 0x0500
        self.assertEqual(ops[stop + 2], "R 01d00000 ok 9b8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa")   # IRQSTOPPOST 0x8AAA
        self.assertEqual(ops[stop + 3:stop + 6], ["P r 00012000 000001fa", "P a 00002000", "P r 00010000 000001fa"])   # cleanup of the latched cause

    def test_irq_register_reads_verbatim(self):
        irq = [d for a, rc, d in reads(AVSVC) if a == 0x01d00000]
        self.assertEqual(len(irq), 21)
        hx = [d.hex() for d in irq]
        self.assertEqual(hx[0], "9b8aaeae" + "8a8aaeae" * 7)               # BASE 0x8AAE with the byte-0 extra 0x11
        self.assertEqual(hx[1], hx[0]); self.assertEqual(hx[2], hx[0])     # P0, A1PRE
        self.assertEqual(hx[3], "9b8aaaaa" + "8a8aaaaa" * 7)               # A1-0: bit 2 cleared by A1
        self.assertEqual(hx[4], hx[3]); self.assertEqual(hx[5], hx[3])     # A1-50US, A1-500US
        self.assertEqual(hx[6], "9b8abbaa" + "8a8aaaaa" * 7)               # A2PRE: group 0 offset 2 reads bb (0xAA | 0x11)
        for i in range(7, 12):
            self.assertEqual(hx[i], "01" + "00" * 31)                      # A2-0 … A2-50MS: 0x0000 with the byte-0 extra 0x01
        self.assertEqual(hx[12], "15040000" + "04040400" * 7)              # EVENT 0x0400 (byte 0 extra 0x11; group 0 offset 2 = 00)
        self.assertEqual(hx[13], "17050100" + "05050500" * 7)              # PREUNMASK 0x0500 (byte 0 extra 0x12; group 0 offset 2 = 01)
        self.assertEqual(hx[14], hx[13])                                   # PRESVC 0x0500 — the authoritative read
        self.assertEqual(hx[15], "17050100" + "05050500" * 4 + "05050400" + "05050500" * 2)   # POSTDRAIN 0x0500: group 5 offset 2 = 04
        self.assertEqual(hx[16], "81800000" + "80800000" * 7)              # POSTACK 0x8000: both sources clear, bit 15 = 1
        self.assertEqual(hx[17], hx[12])                                   # REARMPOST 0x0400 after IRQ := 0
        self.assertEqual(hx[18], hx[13])                                   # IRQSTOPPRE 0x0500 (after the CONTROL restore)
        self.assertEqual(hx[19], hx[3])                                    # IRQSTOPPOST 0x8AAA after the stop 0x8FAA
        self.assertEqual(hx[20], "91" + "90" * 31)                         # FINAL under expansion code 0: 0x9090
        ctl = [d.hex() for a, rc, d in reads(AVSVC) if a == 0x01400000]
        self.assertEqual(len(ctl), 18)
        self.assertEqual(ctl[0], "93" + "90" * 31)                         # BASE 0x90 (byte-0 extra 0x03)
        self.assertTrue(all(c == "9f" + "8c" * 31 for c in ctl[1:16]))     # P0 … REARMPOST: 0x8C with the byte-0 extra 0x13 in all fifteen reads
        self.assertEqual(ctl[16], "91" + "90" * 31)                        # TDCTL after the restore
        self.assertEqual(ctl[17], "01" + "00" * 31)                        # FINAL under expansion code 0
        test = [d.hex() for a, rc, d in reads(AVSVC) if a == 0x01000000]
        self.assertEqual(test[:4], ["7f" + "3c" * 31, "d3" + "c3" * 31, "11" + "00" * 31, "ff" * 32])   # handshake: extras 0x43 / 0x10 / 0x11
        self.assertEqual(test[4:], ["01" + "00" * 31] * 2)                 # BASE / P0 TEST reads

    def test_timeline(self):
        ts = [int(l.split()[1]) for l in self.lines() if l.startswith("T ")]
        self.assertEqual(len(ts), 33)
        self.assertEqual(ts, sorted(ts))                                   # no wrap inside this run
        for t in (3387033147, 3387064949, 3391329164, 3391329470, 3391366386, 3391371622, 3391371862, 3391373682, 3391379306, 3391385098,
                  3391387790, 3391387818, 3391390303, 3391394064, 3391399980, 3391401028, 3391408218, 3391408974, 3391409996, 3391417891,
                  3391422199, 3391428199):
            self.assertIn(t, ts)
        self.assertEqual(3391329164 - 3387064949, 4264215)                 # EVENT 105.289 ms after A2 (004: 4263979, 003B: 4264071, 003A: 4263568)
        self.assertEqual(3391371862 - 3391371622, 240)                     # __UnmaskIrq call including the handler (entry at +72)
        self.assertEqual(3391379306 - 3391371694, 7612)                    # PRESVC 187.9 us after the handler entry
        self.assertEqual(3391387790 - 3391385098, 2692)                    # AUDIO 0x1000 whole-block read, 66.5 us around the call
        self.assertEqual(3391390303 - 3391387818, 2485)                    # VIDEO 0xF00 whole-block read, 61.4 us
        self.assertEqual(3391390303 - 3391379306, 10997)                   # service 271.5 us from PRESVC to the last completion
        self.assertEqual(3391401028 - 3391399980, 1048)                    # POSTACK 25.9 us after the ACK
        self.assertEqual(3391409996 - 3391408218, 1778)                    # REARMPOST 43.9 us after the re-arm: INTSR bit 13 = 1 again

    def test_offset2_pattern_exceptions_are_documented_not_consumed(self):
        # U-GBP-025: the empirical `lo | (hi & 0x05)` pattern of the byte at offset 2 of each 4-byte group holds for
        # every 0x8AAE / 0x8AAA / 0x0000 / 0x8000 / 0x9090 read of this run except group 0 of A2PRE (bb), for groups
        # 1–7 of the 0x0400 and 0x0500 reads (group 0: 00 / 01 where it predicts 04 / 05), and breaks in group 5 of
        # the POSTDRAIN 0x0500 read (04). Pinned as bytes; both references and Open-GBP read offsets 1 and 3 only.
        irq = [d for a, rc, d in reads(AVSVC) if a == 0x01d00000]
        def mids(d):
            return [d[4 * g + 2] for g in range(8)]
        def predicted(d):
            return [d[4 * g + 3] | (d[4 * g + 1] & 0x05) for g in range(8)]
        for i in (0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 16, 19, 20):
            self.assertEqual(mids(irq[i]), predicted(irq[i]), irq[i].hex())
        self.assertEqual(mids(irq[6]), [0xBB] + [0xAA] * 7)               # A2PRE 0x8AAA
        for i in (12, 17):
            self.assertEqual(mids(irq[i]), [0x00] + [0x04] * 7)            # EVENT / REARMPOST 0x0400
        for i in (13, 14, 18):
            self.assertEqual(mids(irq[i]), [0x01] + [0x05] * 7)            # PREUNMASK / PRESVC / IRQSTOPPRE 0x0500
        self.assertEqual(mids(irq[15]), [0x01, 0x05, 0x05, 0x05, 0x05, 0x04, 0x05, 0x05])   # POSTDRAIN 0x0500


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
