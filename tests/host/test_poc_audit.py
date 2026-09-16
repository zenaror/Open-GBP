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

MAIN_A_GOOD = """
00000000 <main>:
   0:	48 00 00 01 	bl      0 <main>
			0: R_PPC_REL24	gbp_initirqa_probe_run
   4:	4e 80 00 20 	blr
"""

# ---- GBP-INIT-003B profile (synthetic listings) ----
# since GBP-INIT-004 the device ACK call site lives in the shared service object (gbp_irq_service.o); the
# 003B probe object calls the stage, the service and the teardown
PROBE_B_GOOD = """
00000000 <gbp_initirqb_probe_run>:
   0:	94 21 ff f0 	stwu    r1,-16(r1)
   4:	48 00 00 01 	bl      4 <gbp_initirqb_probe_run+0x4>
			4: R_PPC_REL24	gbp_initirqa_run_cause
   8:	48 00 00 01 	bl      8 <gbp_initirqb_probe_run+0x8>
			8: R_PPC_REL24	gbp_irq_service_ack
   c:	48 00 00 01 	bl      c <gbp_initirqb_probe_run+0xc>
			c: R_PPC_REL24	gbp_initirqa_teardown
  10:	4e 80 00 20 	blr
"""

SERVICE_GOOD = """
00000000 <gbp_irq_service_deliver>:
   0:	48 00 00 01 	bl      0 <gbp_irq_service_deliver>
			0: R_PPC_REL24	gbp_rawlog_read_pi
   4:	4e 80 00 20 	blr

00000010 <gbp_irq_service_ack>:
  10:	48 00 00 01 	bl      10 <gbp_irq_service_ack>
			10: R_PPC_REL24	gbp_regwrite_irq_u16
  14:	4e 80 00 20 	blr
"""

IRQ_BACKEND_GOOD = """
00000000 <h_irq_install>:
   0:	48 00 00 01 	bl      0 <h_irq_install>
			0: R_PPC_REL24	IRQ_Request
   4:	4e 80 00 20 	blr

00000010 <h_irq_restore>:
  10:	48 00 00 01 	bl      10 <h_irq_restore>
			10: R_PPC_REL24	IRQ_Request
  14:	4e 80 00 20 	blr

00000020 <h_irq_mask>:
  20:	38 60 00 20 	li      r3,32
  24:	48 00 00 01 	bl      24 <h_irq_mask+0x4>
			24: R_PPC_REL24	__MaskIrq
  28:	4e 80 00 20 	blr

00000030 <h_irq_unmask>:
  30:	38 60 00 20 	li      r3,32
  34:	48 00 00 01 	bl      34 <h_irq_unmask+0x4>
			34: R_PPC_REL24	__UnmaskIrq
  38:	4e 80 00 20 	blr

00000040 <hsp_backend_oneshot_isr>:
  40:	38 60 00 20 	li      r3,32
  44:	48 00 00 01 	bl      44 <hsp_backend_oneshot_isr+0x4>
			44: R_PPC_REL24	__MaskIrq
  48:	3d 20 cc 00 	lis     r9,-13312
  4c:	38 00 20 00 	li      r0,8192
  50:	90 09 30 00 	stw     r0,12288(r9)
  54:	4e 80 00 20 	blr

00000060 <hsp_backend_oneshot_isr_ext>:
  60:	38 60 00 20 	li      r3,32
  64:	48 00 00 01 	bl      64 <hsp_backend_oneshot_isr_ext+0x4>
			64: R_PPC_REL24	__MaskIrq
  68:	3d 20 cc 00 	lis     r9,-13312
  6c:	61 29 30 00 	ori     r9,r9,12288
  70:	38 00 20 00 	li      r0,8192
  74:	90 09 00 00 	stw     r0,0(r9)
  78:	4e 80 00 20 	blr
"""

MAIN_B_GOOD = """
00000000 <main>:
   0:	48 00 00 01 	bl      0 <main>
			0: R_PPC_REL24	hsp_backend_irq_transport_ext
   4:	48 00 00 01 	bl      4 <main+0x4>
			4: R_PPC_REL24	gbp_initirqb_probe_run
   8:	4e 80 00 20 	blr
"""

NM_B_GOOD = NM_GOOD + """80004300 T gbp_initirqb_probe_run
80004400 T gbp_initirqa_run_cause
80004500 T gbp_initirqa_teardown
80004600 T hsp_backend_oneshot_isr
80004700 T hsp_backend_oneshot_isr_ext
80004800 T hsp_backend_irq_transport
80004900 T hsp_backend_irq_transport_ext
80005200 T IRQ_Request
"""


def dir_003b(**override):
    files = {"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "gbp_initirqb_probe.objdump.txt": PROBE_B_GOOD,
             "gbp_irq_service.objdump.txt": SERVICE_GOOD,
             "hsp_backend.objdump.txt": BACKEND_GOOD, "hsp_backend_irq.objdump.txt": IRQ_BACKEND_GOOD,
             "main.objdump.txt": MAIN_B_GOOD, "elf.nm.txt": NM_B_GOOD}
    for k, v in override.items():
        if v is None:
            files.pop(k)
        else:
            files[k] = v
    return make_dir(files)


# ---- GBP-INIT-004 profile (synthetic listings): the multi-cycle interrupt object replaces hsp_backend_irq.o ----
PROBE_4_GOOD = """
00000000 <gbp_initirq4_probe_run>:
   0:	94 21 ff f0 	stwu    r1,-16(r1)
   4:	48 00 00 01 	bl      4 <gbp_initirq4_probe_run+0x4>
			4: R_PPC_REL24	gbp_initirqa_run_cause
   8:	48 00 00 01 	bl      8 <gbp_initirq4_probe_run+0x8>
			8: R_PPC_REL24	gbp_irq_service_deliver
   c:	48 00 00 01 	bl      c <gbp_initirq4_probe_run+0xc>
			c: R_PPC_REL24	gbp_irq_service_ack
  10:	48 00 00 01 	bl      10 <gbp_initirq4_probe_run+0x10>
			10: R_PPC_REL24	gbp_regwrite_irq_u16
  14:	48 00 00 01 	bl      14 <gbp_initirq4_probe_run+0x14>
			14: R_PPC_REL24	gbp_initirqa_teardown
  18:	4e 80 00 20 	blr
"""

# the handler as GCC lays it out: the entry sequence (time base, PI reads, count++, __MaskIrq) duplicated into
# the in-range and the out-of-range slot paths, one INTSR store after both (tools/poc_audit.py profile 004)
IRQ_MULTI_BACKEND_GOOD = """
00000000 <hm_irq_install>:
   0:	48 00 00 01 	bl      0 <hm_irq_install>
			0: R_PPC_REL24	IRQ_Request
   4:	4e 80 00 20 	blr

00000010 <hm_irq_restore>:
  10:	48 00 00 01 	bl      10 <hm_irq_restore>
			10: R_PPC_REL24	IRQ_Request
  14:	4e 80 00 20 	blr

00000020 <hm_irq_mask>:
  20:	38 60 00 20 	li      r3,32
  24:	48 00 00 01 	bl      24 <hm_irq_mask+0x4>
			24: R_PPC_REL24	__MaskIrq
  28:	4e 80 00 20 	blr

00000030 <hm_irq_unmask>:
  30:	38 60 00 20 	li      r3,32
  34:	48 00 00 01 	bl      34 <hm_irq_unmask+0x4>
			34: R_PPC_REL24	__UnmaskIrq
  38:	4e 80 00 20 	blr

00000040 <hm_irq_prepare>:
  40:	38 60 00 00 	li      r3,0
  44:	4e 80 00 20 	blr

00000060 <hsp_backend_oneshot_isr_multi>:
  60:	38 60 00 20 	li      r3,32
  64:	48 00 00 01 	bl      64 <hsp_backend_oneshot_isr_multi+0x4>
			64: R_PPC_REL24	__MaskIrq
  68:	3d 20 cc 00 	lis     r9,-13312
  6c:	61 29 30 00 	ori     r9,r9,12288
  70:	38 00 20 00 	li      r0,8192
  74:	90 09 00 00 	stw     r0,0(r9)
  78:	4e 80 00 20 	blr
  7c:	38 60 00 20 	li      r3,32
  80:	48 00 00 01 	bl      80 <hsp_backend_oneshot_isr_multi+0x20>
			80: R_PPC_REL24	__MaskIrq
  84:	4b ff ff e4 	b       68 <hsp_backend_oneshot_isr_multi+0x8>
"""

MAIN_4_GOOD = """
00000000 <main>:
   0:	48 00 00 01 	bl      0 <main>
			0: R_PPC_REL24	hsp_backend_irq_transport_multi
   4:	48 00 00 01 	bl      4 <main+0x4>
			4: R_PPC_REL24	gbp_initirq4_probe_run
   8:	4e 80 00 20 	blr
"""

NM_4_GOOD = NM_GOOD + """80004300 T gbp_initirq4_probe_run
80004400 T gbp_initirqa_run_cause
80004500 T gbp_initirqa_teardown
80004550 T gbp_irq_service_deliver
80004560 T gbp_irq_service_ack
80004600 T hsp_backend_oneshot_isr_multi
80004900 T hsp_backend_irq_transport_multi
80005200 T IRQ_Request
"""


def dir_004(**override):
    files = {"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "gbp_irq_service.objdump.txt": SERVICE_GOOD,
             "gbp_initirq4_probe.objdump.txt": PROBE_4_GOOD, "hsp_backend.objdump.txt": BACKEND_GOOD,
             "hsp_backend_irq_multi.objdump.txt": IRQ_MULTI_BACKEND_GOOD, "main.objdump.txt": MAIN_4_GOOD, "elf.nm.txt": NM_4_GOOD}
    for k, v in override.items():
        if v is None:
            files.pop(k)
        else:
            files[k] = v
    return make_dir(files)


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
        self.assertIn("profile: 003a", text)
        self.assertIn("gbp_regwrite_irq_u16=3 gbp_regwrite_control_byte=2", text)

    def test_003a_main_and_intsr_site_rules(self):
        # main.o must call the 003A entry point and nothing of the interrupt path; h_write_intsr is the only INTSR store
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "hsp_backend.objdump.txt": BACKEND_GOOD,
                      "main.objdump.txt": MAIN_A_GOOD, "elf.nm.txt": NM_GOOD})
        findings, report = poc_audit.audit_dir(d)
        self.assertEqual(findings, [])
        self.assertEqual(report["intsr_store_sites"], {"h_write_intsr": 1})
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "hsp_backend.objdump.txt": BACKEND_GOOD,
                      "main.objdump.txt": MAIN_B_GOOD, "elf.nm.txt": NM_GOOD})
        findings, _ = poc_audit.audit_dir(d)
        self.assertTrue(any("main.o references hsp_backend_irq_transport_ext" in f for f in findings), findings)
        self.assertTrue(any("main.o does not reference gbp_initirqa_probe_run" in f for f in findings), findings)
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "hsp_backend.objdump.txt": BACKEND_GOOD + IRQ_BACKEND_GOOD.split("00000060")[0].replace("<hsp_backend_oneshot_isr>", "<other_w1c>").split("00000000 <h_irq_install>")[0], "elf.nm.txt": NM_GOOD})
        d = make_dir({"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "hsp_backend.objdump.txt": BACKEND_GOOD.replace("<h_write_intsr>", "<h_write_intsr_x>"), "elf.nm.txt": NM_GOOD})
        findings, _ = poc_audit.audit_dir(d)
        self.assertTrue(any("PI INTSR store sites" in f for f in findings), findings)


class PocAuditChecker003B(unittest.TestCase):
    def test_clean(self):
        d = dir_003b()
        findings, report = poc_audit.audit_dir(d, "003b")
        self.assertEqual(findings, [])
        self.assertEqual(report["profile"], "003b")
        self.assertEqual(report["irq_write_sites_total"], 4)
        self.assertEqual(report["callsites"]["gbp_initirqb_probe.o"], {"gbp_regwrite_irq_u16": 0, "gbp_regwrite_control_byte": 0})
        self.assertEqual(report["callsites"]["gbp_irq_service.o"], {"gbp_regwrite_irq_u16": 1, "gbp_regwrite_control_byte": 0})
        self.assertEqual(report["symbol_callers"], {"__UnmaskIrq": {"h_irq_unmask": 1},
                                                    "IRQ_Request": {"h_irq_install": 1, "h_irq_restore": 1},
                                                    "__MaskIrq": {"h_irq_mask": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1}})
        self.assertEqual(report["intsr_store_sites"], {"h_write_intsr": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1})
        self.assertEqual(report["intmr_stores"], [])
        self.assertEqual(poc_audit.main([d, "--profile", "003b"]), 0)
        self.assertEqual(poc_audit.main([d, "--profile", "nope"]), 2)
        # the same objects fail the 003A profile (interrupt path linked)
        findings, _ = poc_audit.audit_dir(d, "003a")
        self.assertTrue(any("forbidden object linked: hsp_backend_irq.o" in f for f in findings), findings)
        self.assertTrue(any("forbidden object linked: gbp_initirqb_probe.o" in f for f in findings), findings)
        self.assertTrue(any("hsp_backend_irq.o references __UnmaskIrq" in f for f in findings), findings)
        self.assertTrue(any("gbp_irq_service.o calls gbp_regwrite_irq_u16 (1)" in f for f in findings), findings)

    def test_second_unmask_site_is_flagged(self):
        d = dir_003b(**{"main.objdump.txt": MAIN_B_GOOD.replace("gbp_initirqb_probe_run", "__UnmaskIrq")})
        findings, _ = poc_audit.audit_dir(d, "003b")
        self.assertTrue(any(f.startswith("__UnmaskIrq call sites") for f in findings), findings)
        self.assertTrue(any("main.o does not reference gbp_initirqb_probe_run" in f for f in findings), findings)

    def test_irq_request_from_elsewhere_is_flagged(self):
        d = dir_003b(**{"hsp_backend_irq.objdump.txt": IRQ_BACKEND_GOOD.replace("<h_irq_restore>", "<h_irq_other>")})
        findings, _ = poc_audit.audit_dir(d, "003b")
        self.assertTrue(any(f.startswith("IRQ_Request call sites") for f in findings), findings)

    def test_base_transport_constructor_in_main_is_flagged(self):
        d = dir_003b(**{"main.objdump.txt": MAIN_B_GOOD.replace("hsp_backend_irq_transport_ext", "hsp_backend_irq_transport")})
        findings, _ = poc_audit.audit_dir(d, "003b")
        self.assertTrue(any("main.o references hsp_backend_irq_transport" in f for f in findings), findings)
        self.assertTrue(any("main.o does not reference hsp_backend_irq_transport_ext" in f for f in findings), findings)

    def test_wrong_irq_write_site_counts(self):
        d = dir_003b(**{"gbp_irq_service.objdump.txt": SERVICE_GOOD.replace("gbp_rawlog_read_pi", "gbp_regwrite_irq_u16")})
        findings, _ = poc_audit.audit_dir(d, "003b")
        self.assertTrue(any("gbp_irq_service.o calls gbp_regwrite_irq_u16 2 times (expected 1)" in f for f in findings), findings)
        d = dir_003b(**{"gbp_initirqb_probe.objdump.txt": PROBE_B_GOOD.replace("gbp_irq_service_ack", "gbp_regwrite_irq_u16")})
        findings, _ = poc_audit.audit_dir(d, "003b")
        self.assertTrue(any("gbp_initirqb_probe.o calls gbp_regwrite_irq_u16 (1)" in f for f in findings), findings)
        d = dir_003b(**{"gbp_initirqb_probe.objdump.txt": PROBE_B_GOOD.replace("gbp_irq_service_ack", "gbp_regwrite_control_byte")})
        findings, _ = poc_audit.audit_dir(d, "003b")
        self.assertTrue(any("gbp_initirqb_probe.o calls gbp_regwrite_control_byte (1)" in f for f in findings), findings)

    def test_handler_without_w1c_or_with_intmr_store_is_flagged(self):
        d = dir_003b(**{"hsp_backend_irq.objdump.txt": IRQ_BACKEND_GOOD.replace("  74:	90 09 00 00 	stw     r0,0(r9)", "  74:	60 00 00 00 	nop")})
        findings, _ = poc_audit.audit_dir(d, "003b")
        self.assertTrue(any("PI INTSR store sites" in f for f in findings), findings)
        d = dir_003b(**{"hsp_backend_irq.objdump.txt": IRQ_BACKEND_GOOD.replace("  74:	90 09 00 00 	stw     r0,0(r9)", "  74:	90 09 00 04 	stw     r0,4(r9)")})
        findings, _ = poc_audit.audit_dir(d, "003b")
        self.assertTrue(any("stores to PI INTMR in hsp_backend_oneshot_isr_ext" in f for f in findings), findings)

    def test_missing_and_forbidden_objects(self):
        d = dir_003b(**{"hsp_backend_irq.objdump.txt": None})
        findings, _ = poc_audit.audit_dir(d, "003b")
        self.assertTrue(any("expected object missing: hsp_backend_irq.o" in f for f in findings), findings)
        d = dir_003b(**{"hsp_backend_intmr.objdump.txt": BACKEND_BAD_INTMR.split("00000040")[1].join(["\n00000040", ""])})
        findings, _ = poc_audit.audit_dir(d, "003b")
        self.assertTrue(any("forbidden object linked: hsp_backend_intmr.o" in f for f in findings), findings)
        self.assertTrue(any("stores to PI INTMR in h_write_intmr" in f for f in findings), findings)
        d = dir_003b(**{"elf.nm.txt": NM_B_GOOD + "80006000 T hsp_backend_intmr_transport\n"})
        findings, _ = poc_audit.audit_dir(d, "003b")
        self.assertTrue(any("ELF defines hsp_backend_intmr_transport" in f for f in findings), findings)
        d = dir_003b(**{"elf.nm.txt": NM_GOOD})
        findings, _ = poc_audit.audit_dir(d, "003b")
        self.assertTrue(any("ELF does not define hsp_backend_oneshot_isr_ext" in f for f in findings), findings)


class PocAuditChecker004(unittest.TestCase):
    """GBP-INIT-004 profile on synthetic listings: hsp_backend_irq_multi.o instead of hsp_backend_irq.o, one
    __UnmaskIrq site, IRQ_Request from the install/restore pair, __MaskIrq from the mask primitive and the
    multi-cycle handler (two sites there, GCC's duplicated entry sequence), 3 + 1 + 1 IRQ write sites
    (stage / service ACK / probe REARM), no INTMR store."""

    def test_clean(self):
        d = dir_004()
        findings, report = poc_audit.audit_dir(d, "004")
        self.assertEqual(findings, [])
        self.assertEqual(report["profile"], "004")
        self.assertEqual(report["callsites"]["gbp_initirqa_probe.o"], {"gbp_regwrite_irq_u16": 3, "gbp_regwrite_control_byte": 2})
        self.assertEqual(report["callsites"]["gbp_irq_service.o"], {"gbp_regwrite_irq_u16": 1, "gbp_regwrite_control_byte": 0})
        self.assertEqual(report["callsites"]["gbp_initirq4_probe.o"], {"gbp_regwrite_irq_u16": 1, "gbp_regwrite_control_byte": 0})
        self.assertEqual(report["irq_write_sites_total"], 5)
        self.assertEqual(report["intmr_stores"], [])
        self.assertEqual(report["intsr_store_sites"], {"h_write_intsr": 1, "hsp_backend_oneshot_isr_multi": 1})
        self.assertEqual(report["symbol_callers"], {"__UnmaskIrq": {"hm_irq_unmask": 1},
                                                    "IRQ_Request": {"hm_irq_install": 1, "hm_irq_restore": 1},
                                                    "__MaskIrq": {"hm_irq_mask": 1, "hsp_backend_oneshot_isr_multi": 2}})
        self.assertEqual(poc_audit.main([d, "--profile", "004"]), 0)

    def test_old_interrupt_object_is_forbidden(self):
        # the 002/003B object (its handlers, its transport constructors) must not be linked: found by object name,
        # by symbol reference and by ELF symbol
        d = dir_004(**{"hsp_backend_irq.objdump.txt": IRQ_BACKEND_GOOD, "elf.nm.txt": NM_4_GOOD + "80006000 T hsp_backend_oneshot_isr_ext\n"})
        findings, _ = poc_audit.audit_dir(d, "004")
        self.assertTrue(any("forbidden object linked: hsp_backend_irq.o" in f for f in findings), findings)
        self.assertTrue(any("ELF defines hsp_backend_oneshot_isr_ext" in f for f in findings), findings)
        self.assertTrue(any(f.startswith("__UnmaskIrq call sites") for f in findings), findings)
        d = dir_004(**{"main.objdump.txt": MAIN_4_GOOD.replace("hsp_backend_irq_transport_multi", "hsp_backend_irq_transport_ext")})
        findings, _ = poc_audit.audit_dir(d, "004")
        self.assertTrue(any("main.o references hsp_backend_irq_transport_ext" in f for f in findings), findings)
        self.assertTrue(any("main.o does not reference hsp_backend_irq_transport_multi" in f for f in findings), findings)
        d = dir_004(**{"hsp_backend_irq_multi.objdump.txt": None})
        findings, _ = poc_audit.audit_dir(d, "004")
        self.assertTrue(any("expected object missing: hsp_backend_irq_multi.o" in f for f in findings), findings)

    def test_second_unmask_site_and_wrong_write_sites_are_flagged(self):
        d = dir_004(**{"gbp_initirq4_probe.objdump.txt": PROBE_4_GOOD.replace("gbp_initirqa_teardown", "__UnmaskIrq")})
        findings, _ = poc_audit.audit_dir(d, "004")
        self.assertTrue(any(f.startswith("__UnmaskIrq call sites") for f in findings), findings)
        d = dir_004(**{"gbp_initirq4_probe.objdump.txt": PROBE_4_GOOD.replace("gbp_initirqa_teardown", "gbp_regwrite_irq_u16")})
        findings, _ = poc_audit.audit_dir(d, "004")
        self.assertTrue(any("gbp_initirq4_probe.o calls gbp_regwrite_irq_u16 2 times (expected 1)" in f for f in findings), findings)
        d = dir_004(**{"main.objdump.txt": MAIN_4_GOOD.replace("gbp_initirq4_probe_run", "gbp_regwrite_irq_u16")})
        findings, _ = poc_audit.audit_dir(d, "004")
        self.assertTrue(any("main.o calls gbp_regwrite_irq_u16 (1)" in f for f in findings), findings)
        d = dir_004(**{"gbp_initirq4_probe.objdump.txt": PROBE_4_GOOD.replace("gbp_initirqa_teardown", "gbp_regwrite_control_byte")})
        findings, _ = poc_audit.audit_dir(d, "004")
        self.assertTrue(any("gbp_initirq4_probe.o calls gbp_regwrite_control_byte (1)" in f for f in findings), findings)

    def test_handler_without_w1c_or_with_intmr_store_or_extra_mask_is_flagged(self):
        d = dir_004(**{"hsp_backend_irq_multi.objdump.txt": IRQ_MULTI_BACKEND_GOOD.replace("  74:	90 09 00 00 	stw     r0,0(r9)", "  74:	60 00 00 00 	nop")})
        findings, _ = poc_audit.audit_dir(d, "004")
        self.assertTrue(any("PI INTSR store sites" in f for f in findings), findings)
        d = dir_004(**{"hsp_backend_irq_multi.objdump.txt": IRQ_MULTI_BACKEND_GOOD.replace("  74:	90 09 00 00 	stw     r0,0(r9)", "  74:	90 09 00 04 	stw     r0,4(r9)")})
        findings, _ = poc_audit.audit_dir(d, "004")
        self.assertTrue(any("stores to PI INTMR in hsp_backend_oneshot_isr_multi" in f for f in findings), findings)
        d = dir_004(**{"hsp_backend_irq_multi.objdump.txt": IRQ_MULTI_BACKEND_GOOD.replace("<hm_irq_prepare>:\n  40:	38 60 00 00 	li      r3,0",
                                                                                          "<hm_irq_prepare>:\n  40:	48 00 00 01 	bl      40 <hm_irq_prepare>\n\t\t\t40: R_PPC_REL24\t__MaskIrq")})
        findings, _ = poc_audit.audit_dir(d, "004")
        self.assertTrue(any(f.startswith("__MaskIrq call sites") for f in findings), findings)
        d = dir_004(**{"hsp_backend_irq_multi.objdump.txt": IRQ_MULTI_BACKEND_GOOD.replace("  84:	4b ff ff e4 	b       68 <hsp_backend_oneshot_isr_multi+0x8>", "  84:	4e 80 00 20 	blr")})
        findings, _ = poc_audit.audit_dir(d, "004")
        self.assertEqual(findings, [])                                    # the count of mask sites is what the profile pins, not their layout


# ---- GBP-AV-SERVICE-001 profile (synthetic listings): the 003B interrupt object again, the whole-block read from the probe ----
PROBE_AV_GOOD = """
00000000 <gbp_avsvc_probe_run>:
   0:	94 21 ff f0 	stwu    r1,-16(r1)
   4:	48 00 00 01 	bl      4 <gbp_avsvc_probe_run+0x4>
			4: R_PPC_REL24	gbp_initirqa_run_cause
   8:	48 00 00 01 	bl      8 <gbp_avsvc_probe_run+0x8>
			8: R_PPC_REL24	gbp_irq_service_deliver
   c:	48 00 00 01 	bl      c <gbp_avsvc_probe_run+0xc>
			c: R_PPC_REL24	gbp_avblock_read
  10:	48 00 00 01 	bl      10 <gbp_avsvc_probe_run+0x10>
			10: R_PPC_REL24	gbp_avblock_read
  14:	48 00 00 01 	bl      14 <gbp_avsvc_probe_run+0x14>
			14: R_PPC_REL24	gbp_irq_service_ack_write_postack
  18:	48 00 00 01 	bl      18 <gbp_avsvc_probe_run+0x18>
			18: R_PPC_REL24	gbp_regwrite_irq_u16
  1c:	48 00 00 01 	bl      1c <gbp_avsvc_probe_run+0x1c>
			1c: R_PPC_REL24	gbp_initirqa_teardown
  20:	4e 80 00 20 	blr
"""

SERVICE_AV_GOOD = """
00000000 <gbp_irq_service_deliver>:
   0:	48 00 00 01 	bl      0 <gbp_irq_service_deliver>
			0: R_PPC_REL24	gbp_rawlog_read_pi
   4:	4e 80 00 20 	blr

00000010 <gbp_irq_service_ack>:
  10:	48 00 00 01 	bl      10 <gbp_irq_service_ack>
			10: R_PPC_REL24	gbp_irq_service_ack_write_postack
  14:	4e 80 00 20 	blr

00000020 <gbp_irq_service_ack_write_postack>:
  20:	48 00 00 01 	bl      20 <gbp_irq_service_ack_write_postack>
			20: R_PPC_REL24	gbp_regwrite_irq_u16
  24:	4e 80 00 20 	blr
"""

AVBLOCK_GOOD = """
00000000 <gbp_avblock_read>:
   0:	48 00 00 01 	bl      0 <gbp_avblock_read>
			0: R_PPC_REL24	gbp_block_addr
   4:	4e 80 00 20 	blr
"""

SMALL_GOOD = """
00000000 <f>:
   0:	4e 80 00 20 	blr
"""

MAIN_AV_GOOD = """
00000000 <main>:
   0:	48 00 00 01 	bl      0 <main>
			0: R_PPC_REL24	hsp_backend_irq_transport_ext
   4:	48 00 00 01 	bl      4 <main+0x4>
			4: R_PPC_REL24	gbp_avsvc_probe_run
   8:	48 00 00 01 	bl      8 <main+0x8>
			8: R_PPC_REL24	gbp_avdump_serialize
   c:	48 00 00 01 	bl      c <main+0xc>
			c: R_PPC_REL24	sdlog_save_blob
  10:	4e 80 00 20 	blr
"""

NM_AV_GOOD = NM_GOOD + """80004300 T gbp_avsvc_probe_run
80004400 T gbp_initirqa_run_cause
80004500 T gbp_initirqa_teardown
80004550 T gbp_irq_service_deliver
80004560 T gbp_irq_service_ack_write_postack
80004570 T gbp_avblock_read
80004580 T gbp_avdump_serialize
80004590 T gbp_crc32
80004600 T hsp_backend_oneshot_isr
80004700 T hsp_backend_oneshot_isr_ext
80004900 T hsp_backend_irq_transport_ext
80005000 T sdlog_save_blob
80005200 T IRQ_Request
"""


def dir_avsvc(**override):
    files = {"gbp_initirqa_probe.objdump.txt": PROBE_GOOD, "gbp_irq_service.objdump.txt": SERVICE_AV_GOOD,
             "gbp_avsvc_probe.objdump.txt": PROBE_AV_GOOD, "gbp_avblock.objdump.txt": AVBLOCK_GOOD, "gbp_avdump.objdump.txt": SMALL_GOOD,
             "gbp_crc32.objdump.txt": SMALL_GOOD, "sdlog.objdump.txt": SMALL_GOOD, "hsp_backend.objdump.txt": BACKEND_GOOD,
             "hsp_backend_irq.objdump.txt": IRQ_BACKEND_GOOD, "main.objdump.txt": MAIN_AV_GOOD, "elf.nm.txt": NM_AV_GOOD}
    for k, v in override.items():
        if v is None:
            files.pop(k)
        else:
            files[k] = v
    return make_dir(files)


class PocAuditCheckerAVSVC(unittest.TestCase):
    """GBP-AV-SERVICE-001 profile on synthetic listings: hsp_backend_irq.o (the 003B extended one-shot) linked, the
    multi-cycle object forbidden, one __UnmaskIrq site, __MaskIrq from the mask primitive and the two handlers, the
    whole-block read exactly twice from the probe, the deliver and the ACK-from-a-value services exactly once from
    it, the PREACK ACK variant never called, 3 + 1 + 1 IRQ write sites, no INTMR store, no ARQ/AR/GX/audio/net symbol."""

    def test_clean(self):
        d = dir_avsvc()
        findings, report = poc_audit.audit_dir(d, "avsvc")
        self.assertEqual(findings, [])
        self.assertEqual(report["profile"], "avsvc")
        self.assertEqual(report["callsites"]["gbp_avsvc_probe.o"], {"gbp_regwrite_irq_u16": 1, "gbp_regwrite_control_byte": 0})
        self.assertEqual(report["irq_write_sites_total"], 5)
        self.assertEqual(report["intsr_store_sites"], {"h_write_intsr": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1})
        self.assertEqual(report["symbol_callers"]["gbp_avblock_read"], {"gbp_avsvc_probe_run": 2})
        self.assertEqual(report["symbol_callers"]["gbp_irq_service_deliver"], {"gbp_avsvc_probe_run": 1})
        self.assertEqual(report["symbol_callers"]["gbp_irq_service_ack_write_postack"], {"gbp_avsvc_probe_run": 1, "gbp_irq_service_ack": 1})
        self.assertEqual(report["symbol_callers"]["gbp_irq_service_ack"], {})
        self.assertEqual(poc_audit.main([d, "--profile", "avsvc"]), 0)

    def test_second_unmask_or_second_delivery_path_is_flagged(self):
        d = dir_avsvc(**{"gbp_avsvc_probe.objdump.txt": PROBE_AV_GOOD.replace("gbp_initirqa_teardown", "__UnmaskIrq")})
        findings, _ = poc_audit.audit_dir(d, "avsvc")
        self.assertTrue(any(f.startswith("__UnmaskIrq call sites") for f in findings), findings)
        d = dir_avsvc(**{"gbp_avsvc_probe.objdump.txt": PROBE_AV_GOOD.replace("gbp_initirqa_teardown", "gbp_irq_service_deliver")})
        findings, _ = poc_audit.audit_dir(d, "avsvc")
        self.assertTrue(any(f.startswith("gbp_irq_service_deliver call sites") for f in findings), findings)

    def test_wrong_bulk_read_or_ack_variant_is_flagged(self):
        d = dir_avsvc(**{"gbp_avsvc_probe.objdump.txt": PROBE_AV_GOOD.replace("gbp_initirqa_teardown", "gbp_avblock_read")})
        findings, _ = poc_audit.audit_dir(d, "avsvc")
        self.assertTrue(any(f.startswith("gbp_avblock_read call sites") for f in findings), findings)
        d = dir_avsvc(**{"gbp_avsvc_probe.objdump.txt": PROBE_AV_GOOD.replace("gbp_irq_service_ack_write_postack", "gbp_irq_service_ack")})
        findings, _ = poc_audit.audit_dir(d, "avsvc")
        self.assertTrue(any(f.startswith("gbp_irq_service_ack call sites") for f in findings), findings)
        self.assertTrue(any(f.startswith("gbp_irq_service_ack_write_postack call sites") for f in findings), findings)
        d = dir_avsvc(**{"main.objdump.txt": MAIN_AV_GOOD.replace("sdlog_save_blob", "gbp_irq_service_ack")})
        findings, _ = poc_audit.audit_dir(d, "avsvc")
        self.assertTrue(any("main.o references gbp_irq_service_ack" in f for f in findings), findings)
        self.assertTrue(any("main.o does not reference sdlog_save_blob" in f for f in findings), findings)

    def test_forbidden_objects_symbols_and_prefixes(self):
        d = dir_avsvc(**{"hsp_backend_irq_multi.objdump.txt": IRQ_MULTI_BACKEND_GOOD})
        findings, _ = poc_audit.audit_dir(d, "avsvc")
        self.assertTrue(any("forbidden object linked: hsp_backend_irq_multi.o" in f for f in findings), findings)
        d = dir_avsvc(**{"gbp_avblock.objdump.txt": None})
        findings, _ = poc_audit.audit_dir(d, "avsvc")
        self.assertTrue(any("expected object missing: gbp_avblock.o" in f for f in findings), findings)
        for bad in ("ARQ_PostRequestAsync", "AR_StartDMA", "AUDIO_Init", "ASND_Init", "GX_Init", "net_init", "DSP_Init", "SI_Transfer", "SIOCTL_x"):
            d = dir_avsvc(**{"gbp_avblock.objdump.txt": AVBLOCK_GOOD.replace("gbp_block_addr", bad)})
            findings, _ = poc_audit.audit_dir(d, "avsvc")
            self.assertTrue(any("gbp_avblock.o references %s (forbidden prefix" % bad in f for f in findings), (bad, findings))
        d = dir_avsvc(**{"elf.nm.txt": NM_AV_GOOD + "80006000 T hsp_backend_oneshot_isr_multi\n80006100 T GX_Init\n"})
        findings, _ = poc_audit.audit_dir(d, "avsvc")
        self.assertTrue(any("ELF defines hsp_backend_oneshot_isr_multi" in f for f in findings), findings)
        self.assertTrue(any("ELF defines GX_Init" in f for f in findings), findings)
        d = dir_avsvc(**{"hsp_backend_irq.objdump.txt": IRQ_BACKEND_GOOD.replace("  74:	90 09 00 00 	stw     r0,0(r9)", "  74:	90 09 00 04 	stw     r0,4(r9)")})
        findings, _ = poc_audit.audit_dir(d, "avsvc")
        self.assertTrue(any("stores to PI INTMR in hsp_backend_oneshot_isr_ext" in f for f in findings), findings)


AUDIT_DIR = os.path.join(ROOT, "build", "poc", "gbp-init-irq-program-probe", "audit")
AUDIT_DIR_B = os.path.join(ROOT, "build", "poc", "gbp-init-irq-deliver-probe", "audit")
AUDIT_DIR_4 = os.path.join(ROOT, "build", "poc", "gbp-init-irq-service-probe", "audit")
AUDIT_DIR_AV = os.path.join(ROOT, "build", "poc", "gbp-av-service-probe", "audit")
IRQ_BACKEND_OBJDUMP = os.path.join(ROOT, "build", "poc", "gbp-init-irq-probe", "hsp_backend_irq.objdump.txt")
INTMR_BACKEND_OBJDUMP = os.path.join(ROOT, "build", "poc", "gbp-init-probe", "hsp_backend_intmr.objdump.txt")


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

    @unittest.skipUnless(os.path.isfile(IRQ_BACKEND_OBJDUMP) and os.path.isfile(INTMR_BACKEND_OBJDUMP),
                         "run `make initirq-audit` to produce the GBP-INIT-002 backend and GBP-INIT-001 INTMR objdumps")
    def test_audit_fails_on_the_real_interrupt_path_objects(self):
        # Negative control on real compiler output: the GBP-INIT-002 interrupt-path object
        # (IRQ_Request, __UnmaskIrq, __MaskIrq, the one-shot handlers) and the GBP-INIT-001
        # INTMR object (the only direct INTMR store) must trip every 003A check.
        d = tempfile.mkdtemp()
        for name in os.listdir(AUDIT_DIR):
            with open(os.path.join(AUDIT_DIR, name), "rb") as src, open(os.path.join(d, name), "wb") as dst:
                dst.write(src.read())
        with open(IRQ_BACKEND_OBJDUMP, "rb") as src, open(os.path.join(d, "hsp_backend_irq.objdump.txt"), "wb") as dst:
            dst.write(src.read())
        with open(INTMR_BACKEND_OBJDUMP, "rb") as src, open(os.path.join(d, "hsp_backend_intmr.objdump.txt"), "wb") as dst:
            dst.write(src.read())
        findings, report = poc_audit.audit_dir(d)
        self.assertTrue(any("forbidden object linked: hsp_backend_irq.o" in f for f in findings), findings)
        self.assertTrue(any("forbidden object linked: hsp_backend_intmr.o" in f for f in findings), findings)
        self.assertTrue(any("hsp_backend_irq.o references __UnmaskIrq" in f for f in findings), findings)
        self.assertTrue(any("hsp_backend_irq.o references IRQ_Request" in f for f in findings), findings)
        self.assertTrue(any("__MaskIrq" in f and "investigate" in f for f in findings), findings)
        self.assertTrue(any("stores to PI INTMR in h_write_intmr" in f for f in findings), findings)
        self.assertTrue(any("PI INTSR store sites" in f for f in findings), findings)     # the two handlers' W1C
        self.assertEqual(len(report["intmr_stores"]), 1)
        self.assertEqual(report["intmr_stores"][0][0], "hsp_backend_intmr.o")


@unittest.skipUnless(os.path.isfile(os.path.join(AUDIT_DIR_B, "elf.nm.txt")), "run `make build initirqb-audit` to produce the audit inputs")
class PocAuditOnBuild003B(unittest.TestCase):
    def test_linked_objects_are_clean(self):
        findings, report = poc_audit.audit_dir(AUDIT_DIR_B, "003b")
        self.assertEqual(findings, [])
        for obj in ("hsp_backend_irq.o", "hsp_backend.o", "gbp_initirqa_probe.o", "gbp_irq_service.o", "gbp_initirqb_probe.o", "main.o"):
            self.assertIn(obj, report["objects"])
        for obj in ("hsp_backend_intmr.o", "hsp_backend_irq_multi.o", "gbp_init_irq_probe.o", "gbp_init_probe.o", "gbp_initirq4_probe.o"):
            self.assertNotIn(obj, report["objects"])
        self.assertEqual(report["callsites"]["gbp_initirqa_probe.o"], {"gbp_regwrite_irq_u16": 3, "gbp_regwrite_control_byte": 2})
        self.assertEqual(report["callsites"]["gbp_initirqb_probe.o"], {"gbp_regwrite_irq_u16": 0, "gbp_regwrite_control_byte": 0})
        self.assertEqual(report["callsites"]["gbp_irq_service.o"], {"gbp_regwrite_irq_u16": 1, "gbp_regwrite_control_byte": 0})
        self.assertEqual(report["irq_write_sites_total"], 4)
        self.assertEqual(report["intmr_stores"], [])
        self.assertEqual(report["intsr_store_sites"], {"h_write_intsr": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1})
        self.assertEqual(report["symbol_callers"], {"__UnmaskIrq": {"h_irq_unmask": 1},
                                                    "IRQ_Request": {"h_irq_install": 1, "h_irq_restore": 1},
                                                    "__MaskIrq": {"h_irq_mask": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1}})
        for s in ("gbp_initirqb_probe_run", "hsp_backend_oneshot_isr_ext", "hsp_backend_irq_transport_ext", "__UnmaskIrq"):
            self.assertIsNotNone(report["elf"][s], s)
        for s in ("gbp_initirq_probe_run", "gbp_init_probe_run", "hsp_backend_intmr_transport"):
            self.assertIsNone(report["elf"][s], s)

    def test_profiles_are_mutually_exclusive_on_the_builds(self):
        # the 003B objects fail the 003A profile and (when built) the 003A objects fail the 003B profile
        findings, _ = poc_audit.audit_dir(AUDIT_DIR_B, "003a")
        self.assertTrue(any("forbidden object linked: hsp_backend_irq.o" in f for f in findings), findings)
        self.assertTrue(any("forbidden object linked: gbp_initirqb_probe.o" in f for f in findings), findings)
        self.assertTrue(any("hsp_backend_irq.o references __UnmaskIrq" in f for f in findings), findings)
        self.assertTrue(any("gbp_irq_service.o calls gbp_regwrite_irq_u16 (1)" in f for f in findings), findings)
        if os.path.isfile(os.path.join(AUDIT_DIR, "elf.nm.txt")):
            findings, _ = poc_audit.audit_dir(AUDIT_DIR, "003b")
            self.assertTrue(any("expected object missing: hsp_backend_irq.o" in f for f in findings), findings)
            self.assertTrue(any("expected object missing: gbp_initirqb_probe.o" in f for f in findings), findings)
            self.assertTrue(any(f.startswith("__UnmaskIrq call sites") for f in findings), findings)


@unittest.skipUnless(os.path.isfile(os.path.join(AUDIT_DIR_4, "elf.nm.txt")), "run `make build initirq4-audit` to produce the audit inputs")
class PocAuditOnBuild004(unittest.TestCase):
    def test_linked_objects_are_clean(self):
        findings, report = poc_audit.audit_dir(AUDIT_DIR_4, "004")
        self.assertEqual(findings, [])
        for obj in ("hsp_backend_irq_multi.o", "hsp_backend.o", "gbp_initirqa_probe.o", "gbp_irq_service.o", "gbp_initirq4_probe.o", "main.o"):
            self.assertIn(obj, report["objects"])
        for obj in ("hsp_backend_irq.o", "hsp_backend_intmr.o", "gbp_initirqb_probe.o", "gbp_init_irq_probe.o", "gbp_init_probe.o"):
            self.assertNotIn(obj, report["objects"])
        self.assertEqual(report["callsites"]["gbp_initirqa_probe.o"], {"gbp_regwrite_irq_u16": 3, "gbp_regwrite_control_byte": 2})
        self.assertEqual(report["callsites"]["gbp_irq_service.o"], {"gbp_regwrite_irq_u16": 1, "gbp_regwrite_control_byte": 0})
        self.assertEqual(report["callsites"]["gbp_initirq4_probe.o"], {"gbp_regwrite_irq_u16": 1, "gbp_regwrite_control_byte": 0})
        self.assertEqual(report["irq_write_sites_total"], 5)          # A1, A2, STOP (stage) + ACK (service) + REARM (probe): logical sites
        self.assertEqual(report["intmr_stores"], [])
        self.assertEqual(report["intsr_store_sites"], {"h_write_intsr": 1, "hsp_backend_oneshot_isr_multi": 1})
        self.assertEqual(report["symbol_callers"], {"__UnmaskIrq": {"hm_irq_unmask": 1},
                                                    "IRQ_Request": {"hm_irq_install": 1, "hm_irq_restore": 1},
                                                    "__MaskIrq": {"hm_irq_mask": 1, "hsp_backend_oneshot_isr_multi": 2}})   # see the profile
        for s in ("gbp_initirq4_probe_run", "gbp_irq_service_deliver", "gbp_irq_service_ack", "hsp_backend_oneshot_isr_multi",
                  "hsp_backend_irq_transport_multi", "__UnmaskIrq"):
            self.assertIsNotNone(report["elf"][s], s)
        for s in ("gbp_initirq_probe_run", "gbp_init_probe_run", "gbp_initirqb_probe_run", "hsp_backend_intmr_transport",
                  "hsp_backend_oneshot_isr", "hsp_backend_oneshot_isr_ext", "hsp_backend_irq_transport", "hsp_backend_irq_transport_ext"):
            self.assertIsNone(report["elf"][s], s)

    def test_profiles_are_mutually_exclusive_on_the_builds(self):
        findings, _ = poc_audit.audit_dir(AUDIT_DIR_4, "003b")
        self.assertTrue(any("forbidden object linked: hsp_backend_irq_multi.o" in f for f in findings), findings)
        self.assertTrue(any("expected object missing: hsp_backend_irq.o" in f for f in findings), findings)
        self.assertTrue(any("forbidden object linked: gbp_initirq4_probe.o" in f for f in findings), findings)
        findings, _ = poc_audit.audit_dir(AUDIT_DIR_4, "003a")
        self.assertTrue(any("hsp_backend_irq_multi.o references __UnmaskIrq" in f for f in findings), findings)
        self.assertTrue(any("gbp_initirq4_probe.o calls gbp_regwrite_irq_u16 (1)" in f for f in findings), findings)
        if os.path.isfile(os.path.join(AUDIT_DIR_B, "elf.nm.txt")):
            findings, _ = poc_audit.audit_dir(AUDIT_DIR_B, "004")
            self.assertTrue(any("forbidden object linked: hsp_backend_irq.o" in f for f in findings), findings)
            self.assertTrue(any("expected object missing: hsp_backend_irq_multi.o" in f for f in findings), findings)
            self.assertTrue(any("forbidden object linked: gbp_initirqb_probe.o" in f for f in findings), findings)


@unittest.skipUnless(os.path.isfile(os.path.join(AUDIT_DIR_AV, "elf.nm.txt")), "run `make build avsvc-audit` to produce the audit inputs")
class PocAuditOnBuildAVSVC(unittest.TestCase):
    def test_linked_objects_are_clean(self):
        findings, report = poc_audit.audit_dir(AUDIT_DIR_AV, "avsvc")
        self.assertEqual(findings, [])
        for obj in ("hsp_backend_irq.o", "hsp_backend.o", "gbp_initirqa_probe.o", "gbp_irq_service.o", "gbp_avblock.o", "gbp_avdump.o",
                    "gbp_crc32.o", "gbp_avsvc_probe.o", "sdlog.o", "main.o"):
            self.assertIn(obj, report["objects"])
        for obj in ("hsp_backend_irq_multi.o", "hsp_backend_intmr.o", "gbp_initirqb_probe.o", "gbp_initirq4_probe.o", "gbp_init_irq_probe.o",
                    "gbp_init_probe.o"):
            self.assertNotIn(obj, report["objects"])
        self.assertEqual(report["callsites"]["gbp_initirqa_probe.o"], {"gbp_regwrite_irq_u16": 3, "gbp_regwrite_control_byte": 2})
        self.assertEqual(report["callsites"]["gbp_irq_service.o"], {"gbp_regwrite_irq_u16": 1, "gbp_regwrite_control_byte": 0})
        self.assertEqual(report["callsites"]["gbp_avsvc_probe.o"], {"gbp_regwrite_irq_u16": 1, "gbp_regwrite_control_byte": 0})
        self.assertEqual(report["irq_write_sites_total"], 5)          # A1, A2, STOP (stage) + ACK (service) + REARM (probe)
        self.assertEqual(report["intmr_stores"], [])
        self.assertEqual(report["intsr_store_sites"], {"h_write_intsr": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1})
        self.assertEqual(report["symbol_callers"], {"__UnmaskIrq": {"h_irq_unmask": 1},
                                                    "IRQ_Request": {"h_irq_install": 1, "h_irq_restore": 1},
                                                    "__MaskIrq": {"h_irq_mask": 1, "hsp_backend_oneshot_isr": 1, "hsp_backend_oneshot_isr_ext": 1},
                                                    "gbp_avblock_read": {"gbp_avsvc_probe_run": 2},
                                                    "gbp_irq_service_deliver": {"gbp_avsvc_probe_run": 1},
                                                    "gbp_irq_service_ack_write_postack": {"gbp_avsvc_probe_run": 1, "gbp_irq_service_ack": 1},
                                                    "gbp_irq_service_ack": {}})
        for s in ("gbp_avsvc_probe_run", "gbp_avblock_read", "gbp_avdump_serialize", "gbp_crc32", "hsp_backend_oneshot_isr_ext",
                  "hsp_backend_irq_transport_ext", "sdlog_save_blob", "__UnmaskIrq"):
            self.assertIsNotNone(report["elf"][s], s)
        for s in ("gbp_initirq4_probe_run", "gbp_initirqb_probe_run", "hsp_backend_oneshot_isr_multi", "hsp_backend_irq_transport_multi",
                  "hsp_backend_intmr_transport", "ARQ_Init", "AR_Init", "AUDIO_Init", "ASND_Init", "GX_Init", "net_init"):
            self.assertIsNone(report["elf"][s], s)

    def test_whole_block_read_cache_sequence_and_single_dma_routine(self):
        # the compiled whole-block read: argument rule, DCFlushRange (write back + invalidate) BEFORE the one DMA,
        # DCInvalidateRange AFTER it, nothing else; the 32-byte read keeps its own flush/invalidate pair
        with open(os.path.join(AUDIT_DIR_AV, "hsp_backend.objdump.txt"), "r", encoding="utf-8", errors="replace") as f:
            funcs = poc_audit.parse_objdump(f.read())
        self.assertIn("h_read_bulk", funcs)
        calls = [it[3] for it in funcs["h_read_bulk"] if it[0] == "reloc" and it[2] == "R_PPC_REL24"]
        self.assertEqual(calls, ["gbp_bulk_args_ok", "DCFlushRange", ".text.dma_len", "DCInvalidateRange"], calls)
        self.assertIn("dma_len", funcs)                                    # one DMA routine shared with the 32-byte accesses
        calls32 = [it[3] for it in funcs["h_read_block"] if it[0] == "reloc" and it[2] == "R_PPC_REL24"]
        self.assertGreaterEqual(calls32.count("DCInvalidateRange"), 2)
        self.assertEqual(calls32.count("DCFlushRange"), 1)
        for name, items in funcs.items():
            for it in items:
                if it[0] == "reloc":
                    self.assertFalse(it[3].startswith(("AR_", "ARQ_")), (name, it[3]))   # libogc's ARAM subsystem never touched

    def test_sidecar_written_only_after_the_run_and_never_by_the_service_objects(self):
        # main.o: every save call sits after the probe entry in the instruction stream (the X/START loop);
        # the objects that run the experiment reference no file, SD, serializer or gecko symbol at all
        def calls(obj):
            with open(os.path.join(AUDIT_DIR_AV, obj + ".objdump.txt"), "r", encoding="utf-8", errors="replace") as f:
                funcs = poc_audit.parse_objdump(f.read())
            return [(name, it[1], it[3]) for name, items in funcs.items() for it in items if it[0] == "reloc" and it[2] == "R_PPC_REL24"]
        main_calls = calls("main")
        offs = {sym: off for name, off, sym in main_calls if name == "main"}
        for sym in ("gbp_avsvc_probe_run", "sdlog_save", "gbp_avsvc_dump_info", "gbp_avdump_serialize", "sdlog_save_blob", "PAD_ScanPads"):
            self.assertIn(sym, offs, sym)
        self.assertLess(offs["gbp_avsvc_probe_run"], offs["sdlog_save"])
        self.assertLess(offs["sdlog_save"], offs["gbp_avsvc_dump_info"])
        self.assertLess(offs["gbp_avsvc_dump_info"], offs["gbp_avdump_serialize"])
        self.assertLess(offs["gbp_avdump_serialize"], offs["sdlog_save_blob"])
        self.assertEqual(sum(1 for name, _o, sym in main_calls if sym == "gbp_avsvc_probe_run"), 1)
        self.assertEqual(sum(1 for name, _o, sym in main_calls if sym == "sdlog_save_blob"), 1)
        forbidden = ("sdlog_", "fopen", "fwrite", "fclose", "fatMount", "fatUnmount", "gbp_avdump_serialize", "gbp_avdump_parse",
                     "usb_", "printf", "malloc", "free")
        for obj in ("gbp_avsvc_probe", "gbp_avblock", "gbp_irq_service", "gbp_initirqa_probe", "hsp_backend", "hsp_backend_irq", "gbp_crc32"):
            for _name, _off, sym in calls(obj):
                self.assertFalse(any(sym.startswith(f) for f in forbidden), (obj, sym))

    def test_profiles_are_mutually_exclusive_on_the_builds(self):
        findings, _ = poc_audit.audit_dir(AUDIT_DIR_AV, "004")
        self.assertTrue(any("forbidden object linked: hsp_backend_irq.o" in f for f in findings), findings)
        self.assertTrue(any("expected object missing: hsp_backend_irq_multi.o" in f for f in findings), findings)
        findings, _ = poc_audit.audit_dir(AUDIT_DIR_AV, "003b")
        self.assertTrue(any("expected object missing: gbp_initirqb_probe.o" in f for f in findings), findings)
        findings, _ = poc_audit.audit_dir(AUDIT_DIR_AV, "003a")
        self.assertTrue(any("hsp_backend_irq.o references __UnmaskIrq" in f for f in findings), findings)
        if os.path.isfile(os.path.join(AUDIT_DIR_4, "elf.nm.txt")):
            findings, _ = poc_audit.audit_dir(AUDIT_DIR_4, "avsvc")
            self.assertTrue(any("forbidden object linked: hsp_backend_irq_multi.o" in f for f in findings), findings)
            self.assertTrue(any("expected object missing: gbp_avblock.o" in f for f in findings), findings)
        if os.path.isfile(os.path.join(AUDIT_DIR_B, "elf.nm.txt")):
            findings, _ = poc_audit.audit_dir(AUDIT_DIR_B, "avsvc")
            self.assertTrue(any("forbidden object linked: gbp_initirqb_probe.o" in f for f in findings), findings)
            self.assertTrue(any("expected object missing: gbp_avsvc_probe.o" in f for f in findings), findings)


if __name__ == "__main__":
    unittest.main()
