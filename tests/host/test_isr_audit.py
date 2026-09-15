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


if __name__ == "__main__":
    unittest.main()
