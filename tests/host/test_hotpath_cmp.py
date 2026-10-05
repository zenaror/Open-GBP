"""tests/host/test_hotpath_cmp.py -- GitHub Issue #158: tools/hotpath_cmp.py, the hot-path identity gate, and its instrument control (i).

Control (i) of the Issue: SYNTHETIC listing pairs, written in this file as complete build directories (the `objdump -dr` / `objdump -r` listings
tools/audit_listings.sh writes, and an `obj/main.o` ELF32 big-endian object built here byte by byte):
  * a pair differing ONLY by shifted addresses and section addends reads SAME;
  * one changed instruction, one changed relocation symbol, one changed string literal referenced from the closure, a function added to the
    closure EACH read DIFFERENT.
An instrument that can only say SAME proves nothing (an instrument must discriminate): every DIFFERENT case is the SAME pair with ONE thing changed.
Controls (ii) and (iii) run on real builds (the vehicle-0001 reproduction); their full outputs are the record's, not this file's.
"""
import os
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import hotpath_cmp  # noqa: E402


# ------------------------------------------------------------------------------------------------ a minimal ELF32 big-endian relocatable object
def elf_object(sections, symbols):
    """sections: [(name, bytes or None for NOBITS)]; symbols: [(name, section name, value, size, kind)] with kind func/object/notype."""
    names = [""] + [n for n, _ in sections] + [".symtab", ".strtab", ".shstrtab"]
    shstr = b"\0"
    name_off = {"": 0}
    for n in names[1:]:
        name_off[n] = len(shstr)
        shstr += n.encode() + b"\0"
    strtab = b"\0"
    sym_entries = [struct.pack(">IIIBBH", 0, 0, 0, 0, 0, 0)]
    sec_index = {n: i + 1 for i, (n, _) in enumerate(sections)}
    for n, _ in sections:                                   # one section symbol per section (STT_SECTION, local)
        sym_entries.append(struct.pack(">IIIBBH", 0, 0, 0, 3, 0, sec_index[n]))
    kinds = {"notype": 0, "object": 1, "func": 2}
    for name, sec, value, size, kind in symbols:
        off = len(strtab)
        strtab += name.encode() + b"\0"
        sym_entries.append(struct.pack(">IIIBBH", off, value, size, kinds[kind], 0, sec_index[sec]))
    symtab = b"".join(sym_entries)
    body = b""
    layout = []
    base = 52
    for n, data in sections:
        layout.append((n, base + len(body), 0 if data is None else len(data), data is None))
        if data is not None:
            body += data
            while len(body) % 4:
                body += b"\0"
    symtab_off = base + len(body)
    body += symtab
    strtab_off = base + len(body)
    body += strtab
    shstr_off = base + len(body)
    body += shstr
    while len(body) % 4:
        body += b"\0"
    shoff = base + len(body)
    nsec = len(names)
    header = b"\x7fELF" + bytes([1, 2, 1, 0]) + b"\0" * 8
    header += struct.pack(">HHIIIIIHHHHHH", 1, 20, 1, 0, 0, shoff, 0, 52, 0, 0, 40, nsec, nsec - 1)
    shdrs = [struct.pack(">IIIIIIIIII", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)]
    for (n, off, size, nobits) in layout:
        shdrs.append(struct.pack(">IIIIIIIIII", name_off[n], 8 if nobits else 1, 0, 0, off, size, 0, 0, 4, 0))
    shdrs.append(struct.pack(">IIIIIIIIII", name_off[".symtab"], 2, 0, 0, symtab_off, len(symtab), nsec - 2, 1 + len(sections), 4, 16))
    shdrs.append(struct.pack(">IIIIIIIIII", name_off[".strtab"], 3, 0, 0, strtab_off, len(strtab), 0, 0, 1, 0))
    shdrs.append(struct.pack(">IIIIIIIIII", name_off[".shstrtab"], 3, 0, 0, shstr_off, len(shstr), 0, 0, 1, 0))
    return header + body + b"".join(shdrs)


# ------------------------------------------------------------------------------------------------ an `objdump -dr` listing
def dr_listing(path, text_sections):
    """text_sections: [(section, [(function, base, [(raw, text, [(pos, type, target)])])])]. Returns the listing text."""
    out = [f"{path}:     file format elf32-powerpc", ""]
    for sec, funcs in text_sections:
        out += ["", f"Disassembly of section {sec}:", ""]
        for fname, base, insns in funcs:
            out.append(f"{base:08x} <{fname}>:")
            addr = base
            for raw, text, relocs in insns:
                out.append(f"{addr:4x}:\t{raw} \t{text}")
                for pos, rtype, target in relocs:
                    out.append(f"\t\t\t{addr + pos:x}: {rtype}\t{target}")
                addr += 4
            out.append("")
    return "\n".join(out) + "\n"


def r_listing(path, sections):
    out = [f"{path}:     file format elf32-powerpc", ""]
    for sec, rows in sections:
        out += [f"RELOCATION RECORDS FOR [{sec}]:", "OFFSET   TYPE              VALUE"]
        out += [f"{o:08x} {t:<17} {v}" for o, t, v in rows]
        out += ["", ""]
    return "\n".join(out)


def build(variant="base"):
    """A synthetic build directory's contents for one variant. 'base' = the reference; 'shifted' = the same code at other addresses and section
    addends; the other variants = 'shifted' with ONE thing changed."""
    shifted = variant != "base"
    # data layout: `pad` before `counter` in .bss moves its section addend; the strings sit at another offset of the string section; the constant too
    bss_pad = 0x40 if shifted else 0x10
    str_pad = b"zz-unrelated\0" if shifted else b"x\0"
    cst_pad = b"\0\0\0\0" * (3 if shifted else 1)
    literal = b"FMT n=%lu" if variant != "string" else b"FMT n=%lx"
    strsec = str_pad + literal + b"\0"
    cstsec = cst_pad + b"\x43\x20\x00\x00"
    bss_symbols = [("pad", ".bss", 0, bss_pad, "object"), ("counter", ".bss", bss_pad, 4, "object")]
    # code layout: in the shifted builds an unrelated function sits before `pump` in the same .text section, so every address moves
    filler = [("4e 80 00 20", "blr", [])] * (5 if shifted else 1)
    pump_base = len(filler) * 4
    helper_base = pump_base + 12 * 4
    # named data of main.o (R1 of the review: compared by CONTENT): an initialised variable behind a pad that moves its section addend, and a
    # constant table whose relocation points at another table (recursion). 'dataval' / 'nested' change one byte; 'libdata' a library's data.
    data_pad = 8 if shifted else 4
    datasec = b"\0" * data_pad + (b"\0\0\0\x02" if variant == "dataval" else b"\0\0\0\x01")
    plan = b"\0\0\0\0\0\0\0\x02"
    phases = b"\0\0\0\x3c\0\0\x01" + (b"\x2d" if variant == "nested" else b"\x2c")
    libdata = b"\0\0\0\x06" if variant == "libdata" else b"\0\0\0\x05"
    called = "helper"
    # compiler-numbered symbols (decision 1): a switch table and a clone. 'renumbered' gives them other numbers with the same content;
    # 'cswtch_bytes' / 'cswtch_reloc' / 'clone_content' keep the reference's numbers and change the content
    cs_n, clone_n = (9, 3) if variant == "renumbered" else (7, 0)
    cswtch = b"\0\0\0\0" + (b"\0\0\0\x02" if variant == "cswtch_bytes" else b"\0\0\0\x01")
    cswtch_target = ".rodata.pump.str1.4" + ("" if variant == "cswtch_reloc" else f"+0x{len(str_pad):x}")
    clone = [("38 60 00 03" if variant == "clone_content" else "38 60 00 02", "li      r3," + ("3" if variant == "clone_content" else "2"), []),
             ("40 82 ff fc", f"bne     0 <helper.part.{clone_n}>", []),
             ("4e 80 00 20", "blr", [])]
    printer = "ringlog_printf" if variant != "relocsym" else "ringlog_vprintf"
    pump = [
        ("94 21 ff f0", "stwu    r1,-16(r1)", []),
        ("3d 20 00 00", "lis     r9,0", [(2, "R_PPC_ADDR16_HA", f".bss+0x{bss_pad:x}")]),
        ("80 69 00 00", "lwz     r3,0(r9)" if variant != "insn" else "lwz     r3,4(r9)", [(2, "R_PPC_ADDR16_LO", f".bss+0x{bss_pad:x}")]),
        ("3c 80 00 00", "lis     r4,0", [(2, "R_PPC_ADDR16_HA", f".rodata.pump.str1.4+0x{len(str_pad):x}")]),
        ("3c a0 00 00", "lis     r5,0", [(2, "R_PPC_ADDR16_HA", f".rodata.cst4+0x{len(cst_pad):x}")]),
        ("48 00 00 01", f"bl      {pump_base + 20:x} <pump+0x14>", [(0, "R_PPC_REL24", printer)]),
        # a PC-relative branch the assembler resolved, to another function of the same section: its displacement (raw bytes) and hex target move
        (f"48 00 00 {(helper_base - (pump_base + 24)) & 0xff:02x}", f"b       {helper_base:x} <{called}>", []),
        ("3c c0 00 00", "lis     r6,0", [(2, "R_PPC_ADDR16_HA", f".rodata.CSWTCH.{cs_n}")]),
        ("48 00 00 01", f"bl      {pump_base + 32:x} <pump+0x20>", [(0, "R_PPC_REL24", f".text.helper.part.{clone_n}")]),
        ("3c e0 00 00", "lis     r7,0", [(2, "R_PPC_ADDR16_HA", f".data+0x{data_pad:x}")]),
        ("3d 00 00 00", "lis     r8,0", [(2, "R_PPC_ADDR16_HA", ".rodata.plan")]),
        ("4e 80 00 20", "blr", []),
    ]
    funcs = [("filler", 0, filler), ("pump", pump_base, pump),
             (called, helper_base, [("38 60 00 01", "li      r3,1", []), ("4e 80 00 20", "blr", [])])]
    if variant == "addfunc":
        funcs[-1] = (called, helper_base, [("48 00 00 01", f"bl      {helper_base:x} <{called}>", [(0, "R_PPC_REL24", ".text.extra")]),
                                           ("4e 80 00 20", "blr", [])])
    tex = [(".text", funcs), (".text.live_tap", [("live_tap", 0, [("4e 80 00 20", "blr", [])])]),
           (".text.live_dma_cb", [("live_dma_cb", 0, [("4e 80 00 20", "blr", [])])]),
           (".text.on_draw_done", [("on_draw_done", 0, [("48 00 00 00", "b       0 <on_draw_done>", [(0, "R_PPC_REL24", "gbp_vpresent_draw_done")])])]),
           (".text.gbp_v28_step_hook", [("gbp_v28_step_hook", 0, [("38 60 00 40", "li      r3,64", []), ("4e 80 00 20", "blr", [])])]),
           (f".text.helper.part.{clone_n}", [(f"helper.part.{clone_n}", 0, clone)])]
    text_size = (len(filler) + len(pump) + 2) * 4
    sections = [(".text", b"\0" * text_size), (".text.live_tap", b"\0" * 4), (".text.live_dma_cb", b"\0" * 4), (".text.on_draw_done", b"\0" * 4),
                (".text.gbp_v28_step_hook", b"\0" * 8), (f".text.helper.part.{clone_n}", b"\0" * 12),
                (".bss", None), (".rodata.pump.str1.4", strsec), (".rodata.cst4", cstsec), (f".rodata.CSWTCH.{cs_n}", cswtch),
                (".data", datasec), (".rodata.plan", plan), (".rodata.plan_phases", phases)]
    symbols = [("filler", ".text", 0, len(filler) * 4, "func"), ("pump", ".text", pump_base, len(pump) * 4, "func"),
               (called, ".text", helper_base, 8, "func"), ("live_tap", ".text.live_tap", 0, 4, "func"),
               ("live_dma_cb", ".text.live_dma_cb", 0, 4, "func"), ("on_draw_done", ".text.on_draw_done", 0, 4, "func"),
               ("gbp_v28_step_hook", ".text.gbp_v28_step_hook", 0, 8, "func"), (f"helper.part.{clone_n}", f".text.helper.part.{clone_n}", 0, 12, "func"),
               (f"CSWTCH.{cs_n}", f".rodata.CSWTCH.{cs_n}", 0, 8, "object"), ("dpad", ".data", 0, data_pad, "object"), ("flag", ".data", data_pad, 4, "object"),
               ("plan", ".rodata.plan", 0, 8, "object"), ("plan_phases", ".rodata.plan_phases", 0, 8, "object")] + bss_symbols
    if variant == "addfunc":
        tex.append((".text.extra", [("extra", 0, [("4e 80 00 20", "blr", [])])]))
        sections.append((".text.extra", b"\0" * 4))
        symbols.append(("extra", ".text.extra", 0, 4, "func"))
    obj_path = "/w/build/poc/" + ("ref" if not shifted else "cand") + "/obj/"
    files = {
        "main.objdump.txt": dr_listing(obj_path + "main.o", tex),
        "main.reloc.txt": r_listing(obj_path + "main.o", [(".text", [(0x24, "R_PPC_REL24", "ringlog_printf")]),
                                                         (f".rodata.CSWTCH.{cs_n}", [(0, "R_PPC_ADDR32", cswtch_target)]),
                                                         (".rodata.plan", [(0, "R_PPC_ADDR32", ".rodata.plan_phases")])]),
        "lib.objdump.txt": dr_listing(obj_path + "lib.o", [(".text.lib", [("lib", 0, [("4e 80 00 20", "blr", [])])])]),
        # the .debug relocations differ between the two builds (the -g directory): excluded by rule
        "lib.reloc.txt": r_listing(obj_path + "lib.o", [(".text.lib", [(0, "R_PPC_REL24", "memcpy")]),
                                                        (".debug_info", [(0x10 if shifted else 0x8, "R_PPC_ADDR32", ".debug_str+0x" + ("40" if shifted else "20"))])]),
        # the library's own object: its sections are compared by their bytes (R1), the listings carry none
        "obj:lib.o": elf_object([(".text.lib", b"\x4e\x80\x00\x20"), (".data.libv", libdata), (".bss.libz", None)],
                                [("lib", ".text.lib", 0, 4, "func"), ("libv", ".data.libv", 0, 4, "object"), ("libz", ".bss.libz", 0, 0, "object")]),
    }
    return files, elf_object(sections, symbols)


def write_build(root, files, elf, extra_objects=()):
    os.makedirs(os.path.join(root, "audit"))
    os.makedirs(os.path.join(root, "obj"))
    for name, text in files.items():
        if name.startswith("obj:"):
            with open(os.path.join(root, "obj", name[4:]), "wb") as f:
                f.write(text)
            continue
        with open(os.path.join(root, "audit", name), "w", encoding="utf-8") as f:
            f.write(text)
    for x in extra_objects:
        for suffix in (".objdump.txt", ".reloc.txt"):
            with open(os.path.join(root, "audit", x + suffix), "w", encoding="utf-8") as f:
                f.write(f"/w/obj/{x}.o:     file format elf32-powerpc\n\nsomething\n")
    with open(os.path.join(root, "obj", "main.o"), "wb") as f:
        f.write(elf)


class SyntheticPairs(unittest.TestCase):
    """Control (i): each case is the reference against ONE candidate variant; the expected verdict is written per case."""

    def compare(self, variant, extras_in_cand=(), extras_arg=(), roots=hotpath_cmp.DEFAULT_ROOTS, ref_variant="base"):
        with tempfile.TemporaryDirectory() as d:
            ref, cand = os.path.join(d, "ref"), os.path.join(d, "cand")
            write_build(ref, *build(ref_variant))
            write_build(cand, *build(variant), extra_objects=extras_in_cand)
            lines, rc = hotpath_cmp.run(ref, cand, list(extras_arg), roots)
        return "\n".join(lines), rc

    def test_shifted_addresses_and_addends_read_same(self):
        out, rc = self.compare("shifted")
        self.assertEqual(rc, 0, out)
        self.assertIn("RESULT: SAME -- 0 differences", out)
        # the pair really differs: the raw listings are not equal, so SAME is the normalisation's doing and not a degenerate input
        a, b = build("base")[0]["main.objdump.txt"], build("shifted")[0]["main.objdump.txt"]
        self.assertNotEqual(a, b)
        self.assertIn("closure (reference, 7): gbp_v28_step_hook, helper, helper.part.N#", out)
        self.assertIn("compiler-numbered symbols compared by content (reference): CSWTCH.7 -> CSWTCH.N#", out)

    def test_same_content_under_another_compiler_number_reads_same(self):
        """decision 1: CSWTCH.7 -> CSWTCH.9 and helper.part.0 -> helper.part.3, the content unchanged"""
        out, rc = self.compare("renumbered")
        self.assertEqual(rc, 0, out)
        self.assertIn("CSWTCH.9 -> CSWTCH.N#", out)
        self.assertIn("(helper.part.3)", out)
        ref_key = [ln for ln in out.splitlines() if ln.startswith("compiler-numbered symbols compared by content (reference)")][0].split(" -> ")[-1]
        self.assertIn(ref_key.split(",")[0].strip(), out.split("(candidate):", 1)[1])

    def test_same_compiler_number_other_content_reads_different(self):
        """decision 1, the other way round: the number kept, the content changed -- a table's bytes, a table's relocation, a clone's code"""
        for variant, needle in (("cswtch_bytes", "R_PPC_ADDR16_HA sym:CSWTCH.N#"), ("cswtch_reloc", "R_PPC_ADDR16_HA sym:CSWTCH.N#"),
                                ("clone_content", "helper.part.N#")):
            out, rc = self.compare(variant)
            self.assertEqual(rc, 1, f"{variant}\n{out}")
            self.assertIn("RESULT: DIFFERENT", out)
            self.assertIn(needle, out)
        out, _ = self.compare("clone_content")
        self.assertIn("is in the reference closure only", out)
        self.assertIn("(same stem helper.part.N: the two contents)", out)
        self.assertIn("li r3,3", out)

    def test_named_data_is_compared_by_content(self):
        """R1: the same data at another address reads SAME (the 'shifted' pair moves .data's addend); a changed initialised variable, a changed
        table reached through another table's relocation, and a changed library data section each read DIFFERENT"""
        a, b = build("base")[0]["main.objdump.txt"], build("shifted")[0]["main.objdump.txt"]
        self.assertIn(".data+0x4", a)
        self.assertIn(".data+0x8", b)
        out, rc = self.compare("shifted")
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"named data objects compared by content \(reference, \d+\): .*flag@[0-9a-f]{16}.*plan@[0-9a-f]{16}.*plan_phases@")
        for variant, needle in (("dataval", "sym:flag@"), ("nested", "sym:plan@")):
            out, rc = self.compare(variant)
            self.assertEqual(rc, 1, f"{variant}\n{out}")
            self.assertIn("DIFFERENCE: pump: 1 differing instruction(s)", out)
            self.assertIn(needle, out)
        out, rc = self.compare("libdata")
        self.assertEqual(rc, 1, out)
        self.assertIn("DIFFERENCE: lib.o section contents differ (non-debug sections, read from the object): .data.libv", out)
        self.assertIn("differences: library 1, main.o 0", out)

    def test_a_missing_library_object_makes_the_gate_unreadable(self):
        files, elf = build("shifted")
        files = dict(files)
        del files["obj:lib.o"]
        with tempfile.TemporaryDirectory() as d:
            write_build(os.path.join(d, "r"), *build("base"))
            write_build(os.path.join(d, "c"), files, elf)
            lines, rc = hotpath_cmp.run(os.path.join(d, "r"), os.path.join(d, "c"), [], hotpath_cmp.DEFAULT_ROOTS)
        self.assertEqual(rc, 2, "\n".join(lines))

    def test_one_changed_instruction_reads_different(self):
        out, rc = self.compare("insn")
        self.assertEqual(rc, 1, out)
        self.assertIn("DIFFERENCE: pump: 1 differing instruction(s)", out)
        self.assertIn("RESULT: DIFFERENT", out)

    def test_one_changed_relocation_symbol_reads_different(self):
        out, rc = self.compare("relocsym")
        self.assertEqual(rc, 1, out)
        self.assertIn("DIFFERENCE: pump: 1 differing instruction(s)", out)
        self.assertIn("R_PPC_REL24 ringlog_vprintf", out)

    def test_one_changed_string_literal_reads_different(self):
        out, rc = self.compare("string")
        self.assertEqual(rc, 1, out)
        # two instructions: the one loading the literal, and the switch table whose relocation points at the same literal (compared by content)
        self.assertIn("DIFFERENCE: pump: 2 differing instruction(s)", out)
        self.assertIn("FMT n=%lx", out)

    def test_a_function_added_to_the_closure_reads_different(self):
        out, rc = self.compare("addfunc")
        self.assertEqual(rc, 1, out)
        self.assertIn("extra is in the candidate closure only", out)

    def test_an_unresolvable_target_is_a_difference_even_when_both_sides_agree(self):
        files, elf = build("base")
        files = dict(files)
        files["main.objdump.txt"] = files["main.objdump.txt"].replace(".rodata.cst4+0x4", ".sdata2+0x8")
        with tempfile.TemporaryDirectory() as d:
            write_build(os.path.join(d, "r"), files, elf)
            write_build(os.path.join(d, "c"), files, elf)
            lines, rc = hotpath_cmp.run(os.path.join(d, "r"), os.path.join(d, "c"), [], hotpath_cmp.DEFAULT_ROOTS)
        out = "\n".join(lines)
        self.assertEqual(rc, 1, out)
        self.assertIn("unresolvable relocation target (reference): pump+0x10: R_PPC_ADDR16_HA .sdata2+0x8", out)
        self.assertIn("unresolvable relocation target (candidate)", out)

    def test_a_missing_root_makes_the_gate_unreadable(self):
        out, rc = self.compare("shifted", roots=hotpath_cmp.DEFAULT_ROOTS + ("not_there",))
        self.assertEqual(rc, 2, out)
        self.assertIn("RESULT: UNREADABLE", out)

    def test_the_extra_object_is_allowed_only_when_named_and_present(self):
        out, rc = self.compare("shifted", extras_in_cand=("gbp_startrec",), extras_arg=("gbp_startrec",))
        self.assertEqual(rc, 0, out)
        out, rc = self.compare("shifted", extras_in_cand=("gbp_startrec",))
        self.assertEqual(rc, 1, out)
        self.assertIn("gbp_startrec is linked into the candidate and not into the reference", out)
        out, rc = self.compare("shifted", extras_arg=("gbp_startrec",))
        self.assertEqual(rc, 1, out)
        self.assertIn("the extra object gbp_startrec is not linked into the candidate", out)

    def test_a_changed_library_object_reads_different(self):
        files, elf = build("shifted")
        files = dict(files)
        files["lib.objdump.txt"] = files["lib.objdump.txt"].replace("blr", "nop")
        with tempfile.TemporaryDirectory() as d:
            write_build(os.path.join(d, "r"), *build("base"))
            write_build(os.path.join(d, "c"), files, elf)
            lines, rc = hotpath_cmp.run(os.path.join(d, "r"), os.path.join(d, "c"), [], hotpath_cmp.DEFAULT_ROOTS)
        out = "\n".join(lines)
        self.assertEqual(rc, 1, out)
        self.assertIn("DIFFERENCE: lib.objdump.txt differs", out)

    def test_a_library_relocation_outside_debug_reads_different(self):
        files, elf = build("shifted")
        files = dict(files)
        files["lib.reloc.txt"] = files["lib.reloc.txt"].replace("memcpy", "memmove")
        with tempfile.TemporaryDirectory() as d:
            write_build(os.path.join(d, "r"), *build("base"))
            write_build(os.path.join(d, "c"), files, elf)
            lines, rc = hotpath_cmp.run(os.path.join(d, "r"), os.path.join(d, "c"), [], hotpath_cmp.DEFAULT_ROOTS)
        out = "\n".join(lines)
        self.assertEqual(rc, 1, out)
        self.assertIn("DIFFERENCE: lib.reloc.txt differs outside the .debug sections", out)


class ElfReader(unittest.TestCase):
    def test_symbols_and_section_bytes_round_trip(self):
        files, elf = build("shifted")
        syms, sections = hotpath_cmp.read_elf(elf)
        by = {(s.name, s.kind): s for s in syms}
        self.assertEqual(by[("counter", "object")].value, 0x40)
        self.assertEqual(by[("counter", "object")].section, ".bss")
        self.assertEqual(by[("pump", "func")].value, 20)
        self.assertIn((".rodata.cst4", "section"), by)
        self.assertEqual(sections[".rodata.cst4"][-4:], b"\x43\x20\x00\x00")
        self.assertEqual(sections[".bss"], b"")

    def test_not_an_elf_is_refused(self):
        with self.assertRaises(ValueError):
            hotpath_cmp.read_elf(b"not an elf at all" * 4)


class Normalisation(unittest.TestCase):
    def test_the_target_classes(self):
        files, elf = build("shifted")
        syms, sections = hotpath_cmp.read_elf(elf)
        obj = hotpath_cmp.MainObj(hotpath_cmp.parse_disassembly(files["main.objdump.txt"]), syms, sections)
        res = hotpath_cmp.Resolver(obj)
        self.assertRegex(res.target(".bss+0x40")[0], r"^sym:counter@[0-9a-f]{16}$")
        self.assertRegex(res.target(".bss+0x42")[0], r"^sym:counter@[0-9a-f]{16}\+0x2$")
        self.assertEqual(res.target(".rodata.cst4+0xc")[0], "cst4:43200000")
        self.assertEqual(res.target(".rodata.pump.str1.4+0xd")[0], "str:b'FMT n=%lu'")
        self.assertEqual(res.target(".text+0x14")[:2], ("func:pump", "pump"))
        self.assertEqual(res.target("ringlog_printf")[:2], ("ringlog_printf", None))
        self.assertEqual(res.target("helper")[:2], ("helper", "helper"))
        self.assertFalse(res.target(".sdata2+0x8")[2])
        self.assertFalse(res.target(".rodata.cst4+0x100")[2])

    def test_a_resolved_branch_ignores_bytes_and_hex_target_but_keeps_mnemonic_and_operands(self):
        f = hotpath_cmp.parse_disassembly(
            "Disassembly of section .text.f:\n\n00000000 <f>:\n   0:\t40 9e 00 10 \tbne     cr7,10 <f+0x10>\n")["f"]
        g = hotpath_cmp.parse_disassembly(
            "Disassembly of section .text:\n\n00000100 <f>:\n 100:\t40 9e 00 99 \tbne     cr7,110 <f+0x10>\n")["f"]
        h = hotpath_cmp.parse_disassembly(
            "Disassembly of section .text:\n\n00000100 <f>:\n 100:\t40 9e 00 99 \tbne     cr6,110 <f+0x10>\n")["f"]
        obj = hotpath_cmp.MainObj({"f": f}, [], {})
        res = hotpath_cmp.Resolver(obj)
        nf = hotpath_cmp.normalise_function(f, res)[0]
        self.assertEqual(nf, ["BR bne cr7, <f+0x10>"])
        self.assertEqual(nf, hotpath_cmp.normalise_function(g, res)[0])
        self.assertNotEqual(nf, hotpath_cmp.normalise_function(h, res)[0])


if __name__ == "__main__":
    unittest.main()
