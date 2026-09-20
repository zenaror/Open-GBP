"""
tests/host/test_poc_audit_data_reloc.py — F8 (HARDWARE_TESTS §V5.59): the
auditor sees relocations that live outside the text.

`objdump -dr` disassembles the code only, so a forbidden symbol reached from a
DATA initialiser — a function pointer in a table, a callback field — produced a
.data/.sdata relocation that tools/poc_audit.py never read (found in §V5.46,
carried as F8). The inputs here are REAL powerpc-eabi listings of three tiny
objects compiled with the project compiler (tests/host/fixtures/poc_audit_f8,
README there); nothing below matches C source text.
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import poc_audit  # noqa: E402

FX = os.path.join(ROOT, "tests", "host", "fixtures", "poc_audit_f8")


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


class TheFixturesAreRealListings(unittest.TestCase):
    def test_powerpc_objects_and_a_recorded_compiler(self):
        for d, obj in (("data_ref", "gbp_vwitness"), ("call", "gbp_vwitness"), ("addr_taken", "gbp_initirqa_probe")):
            for kind in (".objdump.txt", ".reloc.txt"):
                first = read(FX, d, obj + kind).lstrip().splitlines()[0]
                self.assertIn(obj + ".o:     file format elf32-powerpc", first, (d, kind))
        self.assertIn("powerpc-eabi-gcc (devkitPPC) 16.1.0", read(FX, "README.md"))
        for src in ("data_ref_fopen.c", "call_fopen.c", "addr_taken.c"):
            self.assertTrue(os.path.exists(os.path.join(FX, "src", src)), src)


class TheOldBlindSpot(unittest.TestCase):
    def test_the_text_disassembly_of_the_data_only_object_has_no_fopen_at_all(self):
        """This is the blind spot itself: what the pre-§V5.59 tool saw."""
        funcs = poc_audit.parse_objdump(read(FX, "data_ref", "gbp_vwitness.objdump.txt"))
        self.assertNotIn("fopen", poc_audit.reloc_symbols(funcs))
        self.assertEqual(poc_audit.call_count(funcs, "fopen"), 0)

    def test_the_relocation_listing_parser_finds_it_in_a_data_section(self):
        secs = poc_audit.parse_reloc_listing(read(FX, "data_ref", "gbp_vwitness.reloc.txt"))
        data = poc_audit.data_reloc_symbols(secs)
        self.assertIn("fopen", data)
        self.assertTrue(all(s.startswith(".sdata") or s.startswith(".data") or s.startswith(".rodata") for s in data["fopen"]), data["fopen"])
        # debug/unwind sections and the object's own section symbols are not outward edges
        self.assertTrue(any(s.startswith(".debug") for s in secs), "the -g listing carries debug sections")
        self.assertFalse(any(s.startswith(".") for s in data))
        self.assertFalse(any(sec.startswith((".debug", ".eh_frame")) for v in data.values() for sec in v))

    def test_an_addend_is_stripped_from_the_symbol(self):
        secs = poc_audit.parse_reloc_listing("x.o:     file format elf32-powerpc\n\nRELOCATION RECORDS FOR [.rodata]:\n"
                                             "OFFSET   TYPE              VALUE\n00000000 R_PPC_ADDR32      tbl+0x000002b0\n"
                                             "00000004 R_PPC_ADDR32      fopen-0x4\n")
        self.assertEqual([r[2] for r in secs[".rodata"]], ["tbl", "fopen"])


class NegativeControls(unittest.TestCase):
    def test_a_forbidden_filesystem_symbol_reached_only_from_data_is_caught(self):
        findings, report = poc_audit.audit_dir(os.path.join(FX, "data_ref"), "stream")
        hits = [f for f in findings if f.startswith("gbp_vwitness.o references fopen")]
        self.assertEqual(len(hits), 2, findings)                       # the allowlist AND the must-not list
        for h in hits:
            self.assertIn("data .sdata.gbp_vwitness_openers", h)
            self.assertIn("no call and no text reference", h)
            self.assertNotIn("from ", h)
        self.assertEqual(report["data_refs"]["gbp_vwitness.o"], {"fopen": [".sdata.gbp_vwitness_openers"]})
        self.assertEqual(report["reloc_listings"], [1, 1])
        self.assertIn("data references gbp_vwitness.o: fopen(.sdata.gbp_vwitness_openers)", poc_audit.format_report(findings, report))

    def test_the_equivalent_forbidden_call_remains_caught(self):
        findings, report = poc_audit.audit_dir(os.path.join(FX, "call"), "stream")
        hits = [f for f in findings if f.startswith("gbp_vwitness.o references fopen")]
        self.assertEqual(len(hits), 2, findings)
        for h in hits:
            self.assertIn("(from gbp_vwitness_note_frame)", h)
            self.assertNotIn("data ", h)
        self.assertEqual(report["data_refs"], {})
        self.assertNotIn("data references", poc_audit.format_report(findings, report))

    def test_an_address_taken_reference_does_not_inflate_an_exact_call_site_count(self):
        findings, report = poc_audit.audit_dir(os.path.join(FX, "addr_taken"), "003a")
        self.assertEqual(report["callsites"]["gbp_initirqa_probe.o"], {"gbp_regwrite_irq_u16": 3, "gbp_regwrite_control_byte": 2})
        self.assertEqual(report["irq_write_sites_total"], 3)
        self.assertFalse(any("calls gbp_regwrite_irq_u16" in f for f in findings), findings)
        self.assertFalse(any("calls gbp_regwrite_control_byte" in f for f in findings), findings)
        # the two address-takings are visible, and told apart from the calls
        self.assertEqual(report["data_refs"]["gbp_initirqa_probe.o"], {"gbp_regwrite_irq_u16": [".sdata.gbp_initirqa_irq_table"]})
        funcs = poc_audit.parse_objdump(read(FX, "addr_taken", "gbp_initirqa_probe.objdump.txt"))
        self.assertEqual(poc_audit.call_sites(funcs, "gbp_regwrite_irq_u16"), {"gbp_initirqa_probe_run": 3})
        self.assertIn("gbp_initirqa_probe_writer_address", poc_audit.reloc_symbols(funcs)["gbp_regwrite_irq_u16"])

    def test_a_missing_listing_is_a_finding_not_a_silent_downgrade(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "gbp_vwitness.objdump.txt"), "w") as f:
            f.write(read(FX, "data_ref", "gbp_vwitness.objdump.txt"))
        findings, report = poc_audit.audit_dir(d, "stream")
        self.assertTrue(any(f.startswith("gbp_vwitness.o: no relocation listing (gbp_vwitness.reloc.txt)") for f in findings), findings)
        self.assertEqual(report["reloc_listings"], [0, 1])
        self.assertFalse(any("references fopen" in f for f in findings), "without the listing the data edge is invisible -- which is why its absence is a finding")

    def test_a_forbidden_prefix_and_main_must_not_call_also_see_data(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "main.objdump.txt"), "w") as f:
            f.write("main.o:     file format elf32-powerpc\n\n\nDisassembly of section .text:\n\n00000000 <main>:\n   0:\t4e 80 00 20 \tblr\n")
        with open(os.path.join(d, "main.reloc.txt"), "w") as f:
            f.write("main.o:     file format elf32-powerpc\n\nRELOCATION RECORDS FOR [.data.cb]:\nOFFSET   TYPE              VALUE\n"
                    "00000000 R_PPC_ADDR32      net_init\n00000004 R_PPC_ADDR32      gbp_vqueue_publish\n")
        findings, _ = poc_audit.audit_dir(d, "stream")
        self.assertTrue(any(f.startswith("main.o references net_init (forbidden prefix net_; data .data.cb") for f in findings), findings)
        self.assertTrue(any(f.startswith("main.o references gbp_vqueue_publish (data .data.cb") for f in findings), findings)


if __name__ == "__main__":
    unittest.main()
