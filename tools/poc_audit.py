#!/usr/bin/env python3
"""
poc_audit — static audit of the objects linked into a GameCube POC that
must keep the PI HSP interrupt masked (GBP-INIT-003A).

Input: a directory holding `<object>.objdump.txt` (powerpc-eabi-objdump
-dr of every object of the POC) and `elf.nm.txt` (powerpc-eabi-nm of the
linked ELF), produced by `make initirqa-audit`.

Checks (each one a finding when violated):
  objects     none of the forbidden objects is linked (hsp_backend_irq.o,
              gbp_init_irq_probe.o, gbp_init_probe.o);
  symbols     no object of the POC references __UnmaskIrq, IRQ_Request,
              IRQ_Free, hsp_backend_oneshot_isr; a reference to __MaskIrq is
              reported for investigation (none is expected);
  intmr       no store instruction in any object targets PI INTMR
              (0xCC003004). Register values are tracked through lis / ori /
              oris / addi / addis / li / mr inside each function, so both
              GCC encodings are caught: `lis -13312; ori 12292; stw 0(r)`
              and `lis -13311; stw -53244(r)`. Loads are allowed (INTMR is
              read-only here). Stores to INTSR (0xCC003000, the W1C
              acknowledge) are counted and listed, not flagged;
  callsites   gbp_initirqa_probe.o calls gbp_regwrite_irq_u16 exactly three
              times (A1, A2, STOP) and gbp_regwrite_control_byte exactly
              twice (EXP, RESTORE); no other object calls the IRQ write
              primitive; the primitive itself is the only caller of the
              transport's write_block for index D (it is the only place
              that builds the u16-replicated buffer);
  elf         the linked ELF defines gbp_initirqa_probe_run and
              gbp_regwrite_irq_u16, and does not define
              hsp_backend_oneshot_isr, gbp_initirq_probe_run or
              gbp_init_probe_run.
libogc2 itself defines and uses __UnmaskIrq (VIDEO/PAD/EXI setup); that
is library-internal and outside "our" objects, so the symbol check is
done on the POC's objects (relocations), not on the ELF.

Usage:  tools/poc_audit.py <audit-dir> [--report FILE] [--json]
Exit status 0 when there is no finding.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

FORBIDDEN_OBJECTS = ("hsp_backend_irq.o", "gbp_init_irq_probe.o", "gbp_init_probe.o")
FORBIDDEN_SYMBOLS = ("__UnmaskIrq", "IRQ_Request", "IRQ_Free", "hsp_backend_oneshot_isr")
INVESTIGATE_SYMBOLS = ("__MaskIrq",)
ELF_REQUIRED = ("gbp_initirqa_probe_run", "gbp_regwrite_irq_u16", "gbp_regwrite_control_byte")
ELF_FORBIDDEN = ("hsp_backend_oneshot_isr", "gbp_initirq_probe_run", "gbp_init_probe_run", "hsp_backend_irq_transport")
IRQ_WRITE_SITES = {"gbp_initirqa_probe.o": 3}
CONTROL_WRITE_SITES = {"gbp_initirqa_probe.o": 2}

FUNC_RE = re.compile(r"^[0-9a-f]+ <([^>]+)>:\s*$")
INSN_RE = re.compile(r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{2} ){4}\s*(\S+)\s*(.*)$")
RELOC_RE = re.compile(r"^\s*([0-9a-f]+): (R_PPC_\w+)\s+(\S+)")
STORE_MNEMONICS = ("stw", "sth", "stb", "stwu", "sthu", "stbu", "stwx", "sthx", "stbx", "stwux", "sthux", "stbux",
                   "stwbrx", "sthbrx", "stmw", "stfs", "stfd", "stfsu", "stfdu", "stfsx", "stfdx")
NO_GPR_WRITE = ("cmpw", "cmpwi", "cmplw", "cmplwi", "cmpd", "cmpdi", "cmpld", "cmpldi", "mtlr", "mtctr", "mtcrf", "mtspr",
                "mtmsr", "mtsr", "sync", "isync", "eieio", "dcbf", "dcbi", "dcbst", "dcbz", "icbi", "nop", "b", "bl",
                "blr", "bctr", "bctrl", "bdnz", "bdz", "beq", "bne", "blt", "bgt", "ble", "bge", "beq+", "bne+", "blt+",
                "bgt+", "ble+", "bge+", "beq-", "bne-", "blt-", "bgt-", "ble-", "bge-", "bns", "bso", "twi", "tw", "sc",
                "rfi", "crclr", "crset", "crxor", "creqv", "cror", "crand", "crnor", "crandc", "crorc", "crnand", "mcrf")
PI_INTSR = 0xCC003000
PI_INTMR = 0xCC003004


def parse_objdump(text):
    """Returns (functions: {name: [items]}) where items are ('insn', addr, mnemonic, operands) or ('reloc', addr, type, symbol)."""
    funcs = {}
    cur = None
    for line in text.splitlines():
        m = FUNC_RE.match(line)
        if m:
            cur = m.group(1)
            funcs[cur] = []
            continue
        if cur is None:
            continue
        m = RELOC_RE.match(line)
        if m:
            funcs[cur].append(("reloc", int(m.group(1), 16), m.group(2), m.group(3)))
            continue
        m = INSN_RE.match(line)
        if m:
            funcs[cur].append(("insn", int(m.group(1), 16), m.group(2), m.group(3).strip()))
    return funcs


def reloc_symbols(funcs):
    out = {}
    for name, items in funcs.items():
        for it in items:
            if it[0] == "reloc":
                out.setdefault(it[3], []).append(name)
    return out


def _imm(s):
    s = s.strip()
    return int(s, 16) if s.lower().startswith(("0x", "-0x")) else int(s)


def pi_stores(funcs):
    """Store instructions whose effective address is PI INTMR or PI INTSR.
    Register contents are tracked per function through the instructions
    GCC uses to materialize constants (lis/li/ori/oris/addi/addis/mr); any
    other instruction that writes a GPR forgets that register. Returns
    (intmr_hits, intsr_hits) as lists of (function, addr, mnemonic, operands)."""
    intmr, intsr = [], []
    for name, items in funcs.items():
        regs = {}
        for it in items:
            if it[0] != "insn":
                continue
            _, addr, mn, ops = it
            parts = [p.strip() for p in ops.split(",")] if ops else []
            try:
                if mn == "lis" and len(parts) == 2:
                    regs[parts[0]] = (_imm(parts[1]) & 0xFFFF) << 16
                elif mn == "li" and len(parts) == 2:
                    regs[parts[0]] = _imm(parts[1]) & 0xFFFFFFFF
                elif mn == "ori" and len(parts) == 3 and parts[1] in regs:
                    regs[parts[0]] = regs[parts[1]] | (_imm(parts[2]) & 0xFFFF)
                elif mn == "oris" and len(parts) == 3 and parts[1] in regs:
                    regs[parts[0]] = regs[parts[1]] | ((_imm(parts[2]) & 0xFFFF) << 16)
                elif mn in ("addi", "addic") and len(parts) == 3 and parts[1] in regs:
                    regs[parts[0]] = (regs[parts[1]] + _imm(parts[2])) & 0xFFFFFFFF
                elif mn == "addis" and len(parts) == 3 and parts[1] in regs:
                    regs[parts[0]] = (regs[parts[1]] + (_imm(parts[2]) << 16)) & 0xFFFFFFFF
                elif mn == "mr" and len(parts) == 2 and parts[1] in regs:
                    regs[parts[0]] = regs[parts[1]]
                elif mn in STORE_MNEMONICS:
                    ea = None
                    m = re.search(r"(-?\d+)\((r\d+)\)", ops)
                    if m and m.group(2) in regs:
                        ea = (regs[m.group(2)] + int(m.group(1))) & 0xFFFFFFFF
                    elif not m and len(parts) == 3 and parts[1] in regs and parts[2] in regs:   # indexed form
                        ea = (regs[parts[1]] + regs[parts[2]]) & 0xFFFFFFFF
                    if ea == PI_INTMR:
                        intmr.append((name, addr, mn, ops))
                    elif ea == PI_INTSR:
                        intsr.append((name, addr, mn, ops))
                    if mn.endswith("u") or mn.endswith("ux"):            # update forms write the base register
                        if m:
                            regs.pop(m.group(2), None)
                elif mn in NO_GPR_WRITE or mn.startswith("b"):
                    pass
                elif parts and re.match(r"^r\d+$", parts[0]):
                    regs.pop(parts[0], None)                            # unknown value from here on
            except ValueError:
                if parts and re.match(r"^r\d+$", parts[0]):
                    regs.pop(parts[0], None)
    return intmr, intsr


def intmr_stores(funcs):
    return pi_stores(funcs)[0]


def call_count(funcs, symbol):
    n = 0
    for items in funcs.values():
        for it in items:
            if it[0] == "reloc" and it[2] == "R_PPC_REL24" and it[3] == symbol:
                n += 1
    return n


def parse_nm(text):
    defined = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3:
            defined[parts[2]] = parts[1]
        elif len(parts) == 2:
            defined[parts[1]] = parts[0]
    return defined


def audit_dir(path):
    findings = []
    report = {"objects": [], "symbols": {}, "intmr_stores": [], "intsr_stores": [], "callsites": {}, "elf": {}}
    files = sorted(glob.glob(os.path.join(path, "*.objdump.txt")))
    if not files:
        findings.append("no *.objdump.txt in %s" % path)
        return findings, report
    objects = {}
    for f in files:
        obj = os.path.basename(f)[:-len(".objdump.txt")] + ".o"
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            objects[obj] = parse_objdump(fh.read())
        report["objects"].append(obj)
    for bad in FORBIDDEN_OBJECTS:
        if bad in objects:
            findings.append("forbidden object linked: %s" % bad)
    irq_sites_total = 0
    for obj, funcs in objects.items():
        syms = reloc_symbols(funcs)
        for s in FORBIDDEN_SYMBOLS:
            if s in syms:
                findings.append("%s references %s (from %s)" % (obj, s, ", ".join(sorted(set(syms[s])))))
                report["symbols"].setdefault(obj, []).append(s)
        for s in INVESTIGATE_SYMBOLS:
            if s in syms:
                findings.append("%s references %s — investigate (from %s)" % (obj, s, ", ".join(sorted(set(syms[s])))))
                report["symbols"].setdefault(obj, []).append(s)
        intmr_hits, intsr_hits = pi_stores(funcs)
        for hit in intmr_hits:
            findings.append("%s stores to PI INTMR in %s at 0x%x: %s %s" % (obj, hit[0], hit[1], hit[2], hit[3]))
            report["intmr_stores"].append([obj] + [str(x) for x in hit])
        for hit in intsr_hits:
            report["intsr_stores"].append([obj] + [str(x) for x in hit])
        n_irq = call_count(funcs, "gbp_regwrite_irq_u16")
        n_ctl = call_count(funcs, "gbp_regwrite_control_byte")
        report["callsites"][obj] = {"gbp_regwrite_irq_u16": n_irq, "gbp_regwrite_control_byte": n_ctl}
        irq_sites_total += n_irq
        want = IRQ_WRITE_SITES.get(obj)
        if want is not None and n_irq != want:
            findings.append("%s calls gbp_regwrite_irq_u16 %d times (expected %d)" % (obj, n_irq, want))
        if want is None and n_irq:
            findings.append("%s calls gbp_regwrite_irq_u16 (%d) — only the probe may" % (obj, n_irq))
        want = CONTROL_WRITE_SITES.get(obj)
        if want is not None and n_ctl != want:
            findings.append("%s calls gbp_regwrite_control_byte %d times (expected %d)" % (obj, n_ctl, want))
    for obj, want in IRQ_WRITE_SITES.items():
        if obj not in objects:
            findings.append("expected object missing: %s" % obj)
    report["irq_write_sites_total"] = irq_sites_total
    nm_path = os.path.join(path, "elf.nm.txt")
    if os.path.isfile(nm_path):
        with open(nm_path, "r", encoding="utf-8", errors="replace") as fh:
            defined = parse_nm(fh.read())
        for s in ELF_REQUIRED:
            report["elf"][s] = defined.get(s)
            if s not in defined:
                findings.append("ELF does not define %s" % s)
        for s in ELF_FORBIDDEN:
            report["elf"][s] = defined.get(s)
            if s in defined:
                findings.append("ELF defines %s (must not be linked)" % s)
        report["elf"]["__UnmaskIrq"] = defined.get("__UnmaskIrq")
    else:
        findings.append("elf.nm.txt missing")
    return findings, report


def format_report(findings, report):
    out = ["poc_audit: %d finding(s)" % len(findings)]
    for f in findings:
        out.append("  FINDING " + f)
    out.append("objects: " + ", ".join(report["objects"]))
    for obj, c in sorted(report["callsites"].items()):
        if c["gbp_regwrite_irq_u16"] or c["gbp_regwrite_control_byte"]:
            out.append("callsites %s: gbp_regwrite_irq_u16=%d gbp_regwrite_control_byte=%d"
                       % (obj, c["gbp_regwrite_irq_u16"], c["gbp_regwrite_control_byte"]))
    out.append("irq write sites total: %d" % report.get("irq_write_sites_total", 0))
    out.append("intmr stores: %d" % len(report["intmr_stores"]))
    out.append("intsr stores (W1C acknowledge, allowed): %d%s" % (len(report["intsr_stores"]),
               " — " + ", ".join("%s:%s" % (h[0], h[1]) for h in report["intsr_stores"]) if report["intsr_stores"] else ""))
    for k, v in sorted(report["elf"].items()):
        out.append("elf %s: %s" % (k, "defined (%s)" % v if v else "absent"))
    if report["elf"].get("__UnmaskIrq"):
        out.append("note: __UnmaskIrq is defined by libogc2 and used by its own VIDEO/PAD/EXI setup; no POC object references it")
    return "\n".join(out)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    path = argv[0]
    report_path = None
    as_json = False
    i = 1
    while i < len(argv):
        if argv[i] == "--report" and i + 1 < len(argv):
            report_path = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            as_json = True
            i += 1
        else:
            print("unknown argument", argv[i], file=sys.stderr)
            return 2
    findings, report = audit_dir(path)
    text = json.dumps({"findings": findings, "report": report}, indent=1) if as_json else format_report(findings, report)
    print(text)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(format_report(findings, report) + "\n")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
