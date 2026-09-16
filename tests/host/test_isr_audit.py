"""Tests for tools/isr_audit.py: the checker itself on synthetic listings,
and the real audit file when a GameCube build has produced it."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import isr_audit  # noqa: E402

GOOD = """
00000000 <other>:
   0:	4e 80 00 20 	blr

00000010 <hsp_backend_oneshot_isr>:
  10:	94 21 ff f0 	stwu    r1,-16(r1)
  14:	7c 08 02 a6 	mflr    r0
  18:	7d 4c 42 e6 	mftb    r10
  1c:	3d 20 cc 00 	lis     r9,-13312
  20:	81 69 30 00 	lwz     r11,12288(r9)
  24:	81 89 30 04 	lwz     r12,12292(r9)
  28:	38 60 00 20 	li      r3,32
  2c:	48 00 00 01 	bl      2c <hsp_backend_oneshot_isr+0x1c>
			2c: R_PPC_REL24	__MaskIrq
  30:	3d 20 cc 00 	lis     r9,-13312
  34:	38 00 20 00 	li      r0,8192
  38:	90 09 30 00 	stw     r0,12288(r9)
  3c:	4e 80 00 20 	blr

00000040 <after>:
  40:	4e 80 00 20 	blr
"""

BAD_ORDER = GOOD.replace("""  28:	38 60 00 20 	li      r3,32
  2c:	48 00 00 01 	bl      2c <hsp_backend_oneshot_isr+0x1c>
			2c: R_PPC_REL24	__MaskIrq
  30:	3d 20 cc 00 	lis     r9,-13312
  34:	38 00 20 00 	li      r0,8192
  38:	90 09 30 00 	stw     r0,12288(r9)
""", """  28:	38 00 20 00 	li      r0,8192
  2c:	90 09 30 00 	stw     r0,12288(r9)
  30:	38 60 00 20 	li      r3,32
  34:	48 00 00 01 	bl      34 <hsp_backend_oneshot_isr+0x24>
			34: R_PPC_REL24	__MaskIrq
""")

BAD_CALL = GOOD.replace("R_PPC_REL24\t__MaskIrq", "R_PPC_REL24\tprintf")
BAD_INDIRECT = GOOD.replace("  3c:	4e 80 00 20 	blr", "  3c:	4e 80 04 21 	bctrl\n  40:	4e 80 00 20 	blr")

# the extended one-shot of GBP-INIT-003B: PI base through lis+ori, two reads before the mask, one W1C,
# a bounded time-base loop, reads after it; record stores go through an untracked register
GOOD_EXT = """
00000050 <hsp_backend_oneshot_isr_ext>:
  50:	94 21 ff f0 	stwu    r1,-16(r1)
  54:	7c 08 02 a6 	mflr    r0
  58:	7d 4c 42 e6 	mftb    r10
  5c:	3d 20 cc 00 	lis     r9,-13312
  60:	61 29 30 00 	ori     r9,r9,12288
  64:	81 69 00 00 	lwz     r11,0(r9)
  68:	81 89 00 04 	lwz     r12,4(r9)
  6c:	38 60 00 20 	li      r3,32
  70:	48 00 00 01 	bl      70 <hsp_backend_oneshot_isr_ext+0x20>
			70: R_PPC_REL24	__MaskIrq
  74:	3d 20 cc 00 	lis     r9,-13312
  78:	61 29 30 00 	ori     r9,r9,12288
  7c:	81 89 00 04 	lwz     r12,4(r9)
  80:	38 00 20 00 	li      r0,8192
  84:	90 09 00 00 	stw     r0,0(r9)
  88:	81 69 00 00 	lwz     r11,0(r9)
  8c:	7d 4c 42 e6 	mftb    r10
  90:	7d 6c 42 e6 	mftb    r11
  94:	7d 6b 50 50 	subf    r11,r11,r10
  98:	28 0b 00 64 	cmplwi  r11,100
  9c:	41 80 ff f4 	blt     90 <hsp_backend_oneshot_isr_ext+0x40>
  a0:	81 69 00 00 	lwz     r11,0(r9)
  a4:	91 6a 00 08 	stw     r11,8(r10)
  a8:	4e 80 00 20 	blr
"""
TWO_W1C_EXT = GOOD_EXT.replace("  a0:	81 69 00 00 	lwz     r11,0(r9)", "  a0:	90 09 00 00 	stw     r0,0(r9)")
WRONG_VALUE_EXT = GOOD_EXT.replace("  80:	38 00 20 00 	li      r0,8192", "  80:	38 00 10 00 	li      r0,4096")
INTMR_STORE_EXT = GOOD_EXT.replace("  a0:	81 69 00 00 	lwz     r11,0(r9)", "  a0:	91 89 00 04 	stw     r12,4(r9)")
NO_W1C_EXT = GOOD_EXT.replace("  84:	90 09 00 00 	stw     r0,0(r9)", "  84:	91 6a 00 08 	stw     r11,8(r10)")


class IsrAuditChecker(unittest.TestCase):
    def test_clean_listing(self):
        items = isr_audit.extract_function(GOOD, "hsp_backend_oneshot_isr")
        self.assertIsNotNone(items)
        findings, calls = isr_audit.audit(items)
        self.assertEqual(findings, [])
        self.assertEqual(calls, ["__MaskIrq"])

    def test_w1c_before_mask_is_flagged(self):
        items = isr_audit.extract_function(BAD_ORDER, "hsp_backend_oneshot_isr")
        findings, _ = isr_audit.audit(items)
        self.assertTrue(any("mask must precede" in f for f in findings), findings)

    def test_foreign_call_is_flagged(self):
        items = isr_audit.extract_function(BAD_CALL, "hsp_backend_oneshot_isr")
        findings, _ = isr_audit.audit(items)
        self.assertTrue(any("printf" in f for f in findings), findings)

    def test_indirect_call_is_flagged(self):
        items = isr_audit.extract_function(BAD_INDIRECT, "hsp_backend_oneshot_isr")
        findings, _ = isr_audit.audit(items)
        self.assertTrue(any("indirect" in f for f in findings), findings)

    def test_missing_function(self):
        self.assertIsNone(isr_audit.extract_function(GOOD, "nope"))

    def test_extended_handler_with_loop_is_clean(self):
        items = isr_audit.extract_function(GOOD_EXT, "hsp_backend_oneshot_isr_ext")
        findings, calls = isr_audit.audit(items)
        self.assertEqual(findings, [])
        self.assertEqual(calls, ["__MaskIrq"])
        intsr, intmr = isr_audit.pi_store_sites(items)
        self.assertEqual([(st[1], st[4]) for st in intsr], [(0x84, 0x2000)])
        self.assertEqual(intmr, [])

    def test_second_intsr_store_is_flagged(self):
        items = isr_audit.extract_function(TWO_W1C_EXT, "hsp_backend_oneshot_isr_ext")
        findings, _ = isr_audit.audit(items)
        self.assertTrue(any("2 stores to PI INTSR" in f for f in findings), findings)

    def test_missing_intsr_store_is_flagged(self):
        items = isr_audit.extract_function(NO_W1C_EXT, "hsp_backend_oneshot_isr_ext")
        findings, _ = isr_audit.audit(items)
        self.assertTrue(any("0 stores to PI INTSR" in f for f in findings), findings)

    def test_wrong_w1c_value_is_flagged(self):
        items = isr_audit.extract_function(WRONG_VALUE_EXT, "hsp_backend_oneshot_isr_ext")
        findings, _ = isr_audit.audit(items)
        self.assertTrue(any("writes 0x1000, not 0x2000" in f for f in findings), findings)

    def test_intmr_store_is_flagged(self):
        items = isr_audit.extract_function(INTMR_STORE_EXT, "hsp_backend_oneshot_isr_ext")
        findings, _ = isr_audit.audit(items)
        self.assertTrue(any("store to PI INTMR" in f for f in findings), findings)

    def test_report_lists_the_stores(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = os.path.join(d, "x.txt")
        with open(p, "w") as f:
            f.write(GOOD_EXT)
        rep = os.path.join(d, "r.txt")
        self.assertEqual(isr_audit.main([p, "--symbol", "hsp_backend_oneshot_isr_ext", "--report", rep]), 0)
        with open(rep) as f:
            text = f.read()
        self.assertIn("instructions: 23", text)
        self.assertIn("intsr stores: 1 (0x84)", text)
        self.assertIn("intmr stores: 0", text)
        self.assertIn("result: CLEAN", text)
        self.assertEqual(isr_audit.main([p, "--symbol", "hsp_backend_oneshot_isr"]), 2)


AUDIT_FILE = os.path.join(ROOT, "build", "poc", "gbp-init-irq-probe", "hsp_backend_irq.objdump.txt")


@unittest.skipUnless(os.path.isfile(AUDIT_FILE), "run `make build initirq-audit` to produce the objdump")
class IsrAuditOnBuild(unittest.TestCase):
    def test_linked_handler_is_clean(self):
        with open(AUDIT_FILE, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        items = isr_audit.extract_function(text, "hsp_backend_oneshot_isr")
        self.assertIsNotNone(items, "hsp_backend_oneshot_isr not in the objdump")
        findings, calls = isr_audit.audit(items)
        self.assertEqual(findings, [])
        self.assertEqual(calls, ["__MaskIrq"])
        intsr, intmr = isr_audit.pi_store_sites(items)
        self.assertEqual(len(intsr), 1)
        self.assertEqual(intsr[0][4], 0x2000)
        self.assertEqual(intmr, [])


AUDIT_FILE_B = os.path.join(ROOT, "build", "poc", "gbp-init-irq-deliver-probe", "audit", "hsp_backend_irq.objdump.txt")


@unittest.skipUnless(os.path.isfile(AUDIT_FILE_B), "run `make build initirqb-audit` to produce the objdump")
class IsrAuditOnBuild003B(unittest.TestCase):
    """Both one-shot bodies as linked into gbp-init-irq-deliver-probe: only __MaskIrq called, no
    indirect call, exactly one INTSR store of 0x2000 after the mask, no INTMR store; the extended
    body (entry reads, INTMR read after the mask, bounded wait, second reads) is larger than the base."""

    def _audit(self, symbol):
        with open(AUDIT_FILE_B, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        items = isr_audit.extract_function(text, symbol)
        self.assertIsNotNone(items, "%s not in the objdump" % symbol)
        findings, calls = isr_audit.audit(items)
        self.assertEqual(findings, [], symbol)
        self.assertEqual(calls, ["__MaskIrq"], symbol)
        intsr, intmr = isr_audit.pi_store_sites(items)
        self.assertEqual([st[4] for st in intsr], [0x2000], symbol)
        self.assertEqual(intmr, [], symbol)
        return sum(1 for k, _, _ in items if k == "insn")

    def test_both_handlers_are_clean(self):
        n_base = self._audit("hsp_backend_oneshot_isr")
        n_ext = self._audit("hsp_backend_oneshot_isr_ext")
        self.assertGreater(n_ext, n_base)

    def test_no_intmr_store_anywhere_in_the_object(self):
        # every function of the interrupt-path object: the mask changes only through __MaskIrq/__UnmaskIrq
        import poc_audit
        with open(AUDIT_FILE_B, "r", encoding="utf-8", errors="replace") as f:
            funcs = poc_audit.parse_objdump(f.read())
        intmr, intsr = poc_audit.pi_stores(funcs)
        self.assertEqual(intmr, [])
        self.assertEqual(sorted(h[0] for h in intsr), ["hsp_backend_oneshot_isr", "hsp_backend_oneshot_isr_ext"])


AUDIT_FILE_AV = os.path.join(ROOT, "build", "poc", "gbp-av-service-probe", "audit", "hsp_backend_irq.objdump.txt")


@unittest.skipUnless(os.path.isfile(AUDIT_FILE_AV), "run `make build avsvc-audit` to produce the objdump")
class IsrAuditOnBuildAVSVC(unittest.TestCase):
    """GBP-AV-SERVICE-001 links the 002/003B interrupt object again (the extended one-shot is the
    handler installed; one delivery, no generation wrapper): both bodies clean, the multi-cycle
    handler absent from the object and from this build."""

    def _audit(self, symbol):
        with open(AUDIT_FILE_AV, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        items = isr_audit.extract_function(text, symbol)
        self.assertIsNotNone(items, "%s not in the objdump" % symbol)
        findings, calls = isr_audit.audit(items)
        self.assertEqual(findings, [], symbol)
        self.assertEqual(calls, ["__MaskIrq"], symbol)
        intsr, intmr = isr_audit.pi_store_sites(items)
        self.assertEqual([st[4] for st in intsr], [0x2000], symbol)
        self.assertEqual(intmr, [], symbol)
        return text

    def test_both_handlers_are_clean_and_the_multicycle_one_is_absent(self):
        text = self._audit("hsp_backend_oneshot_isr_ext")
        self._audit("hsp_backend_oneshot_isr")
        self.assertIsNone(isr_audit.extract_function(text, "hsp_backend_oneshot_isr_multi"))
        self.assertFalse(os.path.isfile(os.path.join(os.path.dirname(AUDIT_FILE_AV), "hsp_backend_irq_multi.objdump.txt")))

    def test_no_intmr_store_anywhere_in_the_object(self):
        import poc_audit
        with open(AUDIT_FILE_AV, "r", encoding="utf-8", errors="replace") as f:
            funcs = poc_audit.parse_objdump(f.read())
        intmr, intsr = poc_audit.pi_stores(funcs)
        self.assertEqual(intmr, [])
        self.assertEqual(sorted(h[0] for h in intsr), ["hsp_backend_oneshot_isr", "hsp_backend_oneshot_isr_ext"])


AUDIT_FILE_4 = os.path.join(ROOT, "build", "poc", "gbp-init-irq-service-probe", "audit", "hsp_backend_irq_multi.objdump.txt")


@unittest.skipUnless(os.path.isfile(AUDIT_FILE_4), "run `make build initirq4-audit` to produce the objdump")
class IsrAuditOnBuild004(unittest.TestCase):
    """The multi-cycle handler as linked into gbp-init-irq-service-probe (GBP-INIT-004): the
    generation wrapper around the unchanged extended body — only __MaskIrq called, no indirect
    call, exactly one INTSR store of 0x2000 after the mask, no INTMR store; the whole object stores
    INTSR only from that handler and from h_write_intsr, never INTMR. The 002/003B handlers are
    not in this object (they live in hsp_backend_irq.c, which the 004 POC does not link)."""

    def test_multicycle_handler_is_clean(self):
        with open(AUDIT_FILE_4, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        items = isr_audit.extract_function(text, "hsp_backend_oneshot_isr_multi")
        self.assertIsNotNone(items, "hsp_backend_oneshot_isr_multi not in the objdump")
        findings, calls = isr_audit.audit(items)
        self.assertEqual(findings, [])
        # two __MaskIrq call sites: GCC duplicates the entry sequence (time base, PI reads, count++, mask) into the
        # in-range and the out-of-range slot paths; both precede the single W1C store (manual inspection, DEVLOG)
        self.assertEqual(calls, ["__MaskIrq", "__MaskIrq"])
        intsr, intmr = isr_audit.pi_store_sites(items)
        self.assertEqual([st[4] for st in intsr], [0x2000])
        self.assertEqual(intmr, [])
        self.assertIsNone(isr_audit.extract_function(text, "hsp_backend_oneshot_isr"))
        self.assertIsNone(isr_audit.extract_function(text, "hsp_backend_oneshot_isr_ext"))

    def test_no_intmr_store_anywhere_in_the_object(self):
        import poc_audit
        with open(AUDIT_FILE_4, "r", encoding="utf-8", errors="replace") as f:
            funcs = poc_audit.parse_objdump(f.read())
        intmr, intsr = poc_audit.pi_stores(funcs)
        self.assertEqual(intmr, [])
        self.assertEqual(sorted(h[0] for h in intsr), ["hsp_backend_oneshot_isr_multi"])


if __name__ == "__main__":
    unittest.main()
