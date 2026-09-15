"""Tests for tools/poc_audit.py: the checker on synthetic listings, and the
real audit directory when `make build initirqa-audit` has produced it."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import poc_audit  # noqa: E402

PROBE_GOOD = """
00000000 <gbp_initirqa_probe_run>:
   0:	94 21 ff f0 	stwu    r1,-16(r1)
   4:	48 00 00 01 	bl      4 <gbp_initirqa_probe_run+0x4>
			4: R_PPC_REL24	gbp_regwrite_control_byte
   8:	48 00 00 01 	bl      8 <gbp_initirqa_probe_run+0x8>
			8: R_PPC_REL24	gbp_regwrite_irq_u16
   c:	48 00 00 01 	bl      c <gbp_initirqa_probe_run+0xc>
			c: R_PPC_REL24	gbp_regwrite_irq_u16
  10:	3d 20 cc 00 	lis     r9,-13312
  14:	81 69 30 04 	lwz     r11,12292(r9)
  18:	4e 80 00 20 	blr

00000020 <teardown>:
  20:	48 00 00 01 	bl      20 <teardown>
			20: R_PPC_REL24	gbp_regwrite_control_byte
  24:	48 00 00 01 	bl      24 <teardown+0x4>
			24: R_PPC_REL24	gbp_regwrite_irq_u16
  28:	4e 80 00 20 	blr
"""

# the encodings devkitPPC GCC 16 actually emitted for src/platform/hsp_backend*.c
BACKEND_GOOD = """
00000000 <h_write_intsr>:
   0:	3d 20 cc 00 	lis     r9,-13312
   4:	38 60 00 00 	li      r3,0
   8:	61 29 30 00 	ori     r9,r9,12288
   c:	90 89 00 00 	stw     r4,0(r9)
  10:	4e 80 00 20 	blr

00000020 <h_read_pi>:
  20:	3d 20 cc 00 	lis     r9,-13312
  24:	38 60 00 00 	li      r3,0
  28:	61 29 30 00 	ori     r9,r9,12288
  2c:	81 49 00 00 	lwz     r10,0(r9)
  30:	91 44 00 00 	stw     r10,0(r4)
  34:	81 29 00 04 	lwz     r9,4(r9)
  38:	91 25 00 00 	stw     r9,0(r5)
  3c:	4e 80 00 20 	blr
"""

BACKEND_BAD_INTMR = BACKEND_GOOD + """
00000040 <h_write_intmr>:
  40:	3d 20 cc 00 	lis     r9,-13312
  44:	38 60 00 00 	li      r3,0
  48:	61 29 30 04 	ori     r9,r9,12292
  4c:	90 89 00 00 	stw     r4,0(r9)
  50:	4e 80 00 20 	blr
"""

# the other constant-materialization GCC uses: sign-extended displacement from lis -13311 (0xCC01)
BACKEND_BAD_INTMR_SIGNED = BACKEND_GOOD + """
00000040 <h_write_intmr>:
  40:	3d 20 cc 01 	lis     r9,-13311
  44:	90 89 30 04 	stw     r4,-53244(r9)
  48:	4e 80 00 20 	blr
"""

# a register whose value was forgotten (overwritten by a load) must not produce a hit
BACKEND_FORGOTTEN = BACKEND_GOOD + """
00000040 <other>:
  40:	3d 20 cc 00 	lis     r9,-13312
  44:	61 29 30 04 	ori     r9,r9,12292
  48:	81 29 00 00 	lwz     r9,0(r9)
  4c:	90 89 00 00 	stw     r4,0(r9)
  50:	4e 80 00 20 	blr
"""

BACKEND_BAD_UNMASK = BACKEND_GOOD + """
00000020 <h_irq_unmask>:
  20:	38 60 00 20 	li      r3,32
  24:	48 00 00 01 	bl      24 <h_irq_unmask+0x4>
			24: R_PPC_REL24	__UnmaskIrq
  28:	4e 80 00 20 	blr
"""

NM_GOOD = """80003100 T _start
80004000 T gbp_initirqa_probe_run
80004100 T gbp_regwrite_irq_u16
80004200 T gbp_regwrite_control_byte
80005000 T __UnmaskIrq
80005100 T __MaskIrq
"""


def make_dir(files):
    d = tempfile.mkdtemp()
    for name, text in files.items():
        with open(os.path.join(d, name), "w") as f:
            f.write(text)
    return d


class PocAuditChecker(unittest.TestCase):
    def test_clean(self):
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "hsp_backend.objdump.txt": BACKEND_GOOD, "elf.nm.txt": NM_GOOD})
        findings, report = poc_audit.audit_dir(d)
        self.assertEqual(findings, [])
        self.assertEqual(report["callsites"]["gbp_initirqa_probe.o"], {"gbp_regwrite_irq_u16": 3, "gbp_regwrite_control_byte": 2})
        self.assertEqual(report["irq_write_sites_total"], 3)
        self.assertEqual(report["intmr_stores"], [])
        self.assertIsNone(report["elf"]["hsp_backend_oneshot_isr"])
        self.assertEqual(poc_audit.main([d]), 0)

    def test_intmr_store_is_flagged_loads_are_not(self):
        for listing in (BACKEND_BAD_INTMR, BACKEND_BAD_INTMR_SIGNED):
            d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "hsp_backend.objdump.txt": listing, "elf.nm.txt": NM_GOOD})
            findings, report = poc_audit.audit_dir(d)
            self.assertTrue(any("stores to PI INTMR" in f and "h_write_intmr" in f for f in findings), findings)
            self.assertEqual(len(report["intmr_stores"]), 1)
            self.assertEqual(len(report["intsr_stores"]), 1)                  # h_write_intsr, allowed
            self.assertEqual(poc_audit.main([d]), 1)
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "hsp_backend.objdump.txt": BACKEND_GOOD, "elf.nm.txt": NM_GOOD})
        findings, report = poc_audit.audit_dir(d)
        self.assertEqual(findings, [])
        self.assertEqual(report["intsr_stores"][0][1], "h_write_intsr")
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "hsp_backend.objdump.txt": BACKEND_FORGOTTEN, "elf.nm.txt": NM_GOOD})
        findings, report = poc_audit.audit_dir(d)
        self.assertEqual(findings, [])
        self.assertEqual(report["intmr_stores"], [])

    def test_pi_stores_tracking(self):
        funcs = poc_audit.parse_objdump(BACKEND_BAD_INTMR_SIGNED)
        intmr, intsr = poc_audit.pi_stores(funcs)
        self.assertEqual([h[0] for h in intmr], ["h_write_intmr"])
        self.assertEqual([h[0] for h in intsr], ["h_write_intsr"])

    def test_unmask_reference_is_flagged(self):
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "hsp_backend.objdump.txt": BACKEND_BAD_UNMASK, "elf.nm.txt": NM_GOOD})
        findings, _ = poc_audit.audit_dir(d)
        self.assertTrue(any("__UnmaskIrq" in f for f in findings), findings)

    def test_mask_reference_is_reported_for_investigation(self):
        bad = BACKEND_GOOD.replace("<h_read_pi>", "<h_x>").replace("  3c:	4e 80 00 20 	blr", "  3c:	48 00 00 01 	bl      3c <h_x+0x1c>\n\t\t\t3c: R_PPC_REL24\t__MaskIrq\n  40:	4e 80 00 20 	blr")
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "hsp_backend.objdump.txt": bad, "elf.nm.txt": NM_GOOD})
        findings, _ = poc_audit.audit_dir(d)
        self.assertTrue(any("__MaskIrq" in f and "investigate" in f for f in findings), findings)

    def test_forbidden_object_and_wrong_callsite_counts(self):
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD.replace("teardown+0x4>\n\t\t\t24: R_PPC_REL24\tgbp_regwrite_irq_u16", "teardown+0x4>\n\t\t\t24: R_PPC_REL24\tother"),
                      "hsp_backend_irq.objdump.txt": BACKEND_GOOD, "elf.nm.txt": NM_GOOD})
        findings, _ = poc_audit.audit_dir(d)
        self.assertTrue(any("forbidden object linked: hsp_backend_irq.o" in f for f in findings), findings)
        self.assertTrue(any("calls gbp_regwrite_irq_u16 2 times (expected 3)" in f for f in findings), findings)

    def test_irq_write_from_another_object_is_flagged(self):
        other = "00000000 <main>:\n   0:\t48 00 00 01 \tbl      0 <main>\n\t\t\t0: R_PPC_REL24\tgbp_regwrite_irq_u16\n   4:\t4e 80 00 20 \tblr\n"
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "main.objdump.txt": other, "elf.nm.txt": NM_GOOD})
        findings, _ = poc_audit.audit_dir(d)
        self.assertTrue(any("main.o calls gbp_regwrite_irq_u16 (1)" in f for f in findings), findings)

    def test_elf_symbols(self):
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "elf.nm.txt": NM_GOOD + "80006000 T hsp_backend_oneshot_isr\n"})
        findings, _ = poc_audit.audit_dir(d)
        self.assertTrue(any("ELF defines hsp_backend_oneshot_isr" in f for f in findings), findings)
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "elf.nm.txt": "80003100 T _start\n"})
        findings, _ = poc_audit.audit_dir(d)
        self.assertTrue(any("ELF does not define gbp_initirqa_probe_run" in f for f in findings), findings)

    def test_missing_inputs(self):
        d = make_dir({})
        findings, _ = poc_audit.audit_dir(d)
        self.assertTrue(findings)
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD})
        findings, _ = poc_audit.audit_dir(d)
        self.assertTrue(any("elf.nm.txt missing" in f for f in findings), findings)

    def test_report_file(self):
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "hsp_backend.objdump.txt": BACKEND_GOOD, "elf.nm.txt": NM_GOOD})
        rep = os.path.join(d, "r.txt")
        self.assertEqual(poc_audit.main([d, "--report", rep]), 0)
        with open(rep) as f:
            text = f.read()
        self.assertIn("poc_audit: 0 finding(s)", text)
        self.assertIn("gbp_regwrite_irq_u16=3 gbp_regwrite_control_byte=2", text)


AUDIT_DIR = os.path.join(ROOT, "build", "poc", "gbp-init-irq-program-probe", "audit")
IRQ_BACKEND_OBJDUMP = os.path.join(ROOT, "build", "poc", "gbp-init-irq-probe", "hsp_backend_irq.objdump.txt")


@unittest.skipUnless(os.path.isfile(os.path.join(AUDIT_DIR, "elf.nm.txt")), "run `make build initirqa-audit` to produce the audit inputs")
class PocAuditOnBuild(unittest.TestCase):
    def test_linked_objects_are_clean(self):
        findings, report = poc_audit.audit_dir(AUDIT_DIR)
        self.assertEqual(findings, [])
        self.assertNotIn("hsp_backend_irq.o", report["objects"])
        self.assertIn("hsp_backend.o", report["objects"])
        self.assertEqual(report["callsites"]["gbp_initirqa_probe.o"], {"gbp_regwrite_irq_u16": 3, "gbp_regwrite_control_byte": 2})
        self.assertEqual(report["irq_write_sites_total"], 3)
        self.assertEqual(report["intmr_stores"], [])
        self.assertIsNone(report["elf"]["hsp_backend_oneshot_isr"])
        self.assertIsNone(report["elf"]["gbp_initirq_probe_run"])
        self.assertIsNotNone(report["elf"]["gbp_initirqa_probe_run"])
        self.assertEqual([h[1] for h in report["intsr_stores"]], ["h_write_intsr"])   # the one W1C primitive

    @unittest.skipUnless(os.path.isfile(IRQ_BACKEND_OBJDUMP), "run `make initirq-audit` to produce the GBP-INIT-002 backend objdump")
    def test_audit_fails_on_the_real_interrupt_path_object(self):
        # Negative control on real compiler output: the GBP-INIT-002 backend object
        # (INTMR store, IRQ_Request, __UnmaskIrq, the one-shot handler) must trip every check.
        d = tempfile.mkdtemp()
        for name in os.listdir(AUDIT_DIR):
            with open(os.path.join(AUDIT_DIR, name), "rb") as src, open(os.path.join(d, name), "wb") as dst:
                dst.write(src.read())
        with open(IRQ_BACKEND_OBJDUMP, "rb") as src, open(os.path.join(d, "hsp_backend_irq.objdump.txt"), "wb") as dst:
            dst.write(src.read())
        findings, report = poc_audit.audit_dir(d)
        self.assertTrue(any("forbidden object linked: hsp_backend_irq.o" in f for f in findings), findings)
        self.assertTrue(any("hsp_backend_irq.o references __UnmaskIrq" in f for f in findings), findings)
        self.assertTrue(any("hsp_backend_irq.o references IRQ_Request" in f for f in findings), findings)
        self.assertTrue(any("__MaskIrq" in f and "investigate" in f for f in findings), findings)
        self.assertTrue(any("stores to PI INTMR in h_write_intmr" in f for f in findings), findings)
        self.assertEqual(len(report["intmr_stores"]), 1)


if __name__ == "__main__":
    unittest.main()
