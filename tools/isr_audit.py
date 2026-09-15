#!/usr/bin/env python3
"""
isr_audit — static audit of the one-shot PI HSP interrupt handler that is
actually linked into a GameCube build (docs/protocol/INITIALIZATION.md §9
R8; EVIDENCE ENV-IRQ-002).

Input: the output of `powerpc-eabi-objdump -dr` on the object that
contains `hsp_backend_oneshot_isr` (src/platform/hsp_backend.c).

Checks, on the instructions of that function only:
  - every branch-and-link / relocation target is in the allow-list
    (libogc2's __MaskIrq is the only function it may call);
  - no indirect calls (bctrl / blrl);
  - no reference to memory-allocation, formatting, filesystem, DMA or
    GBP symbols (deny-list on relocation names);
  - the PI registers 0xCC003000/0xCC003004 are referenced (lis -13312 /
    0xcc00) and the time base is read (mftb);
  - exactly ONE store whose effective address is PI INTSR (0xCC003000),
    its value 0x2000 (the W1C acknowledge), placed after the first
    __MaskIrq call (mask before W1C), judged on instruction order inside
    the function; register values come from tools/poc_audit.py's
    track_registers (forward data flow over the control-flow graph: lis /
    li / ori / oris / addi / addis / mr, branch targets merge by
    agreement, loops converge, calls clobber the volatile GPRs), so both
    GCC encodings (`lis; ori; stw 0(r)` and `lis; stw disp(r)`) are seen,
    also when the PI base lives in a callee-saved register across an
    early-return path;
  - NO store whose effective address is PI INTMR (0xCC003004): the mask
    changes only through __MaskIrq.
Loops (the extended handler of GBP-INIT-003B waits a fixed number of
time-base ticks) are allowed; the instruction count is reported so the
handler's size can be compared between builds.

Usage:
    tools/isr_audit.py <objdump.txt> [--report out.txt] [--symbol NAME]
Exit status 0 = clean, 1 = violation, 2 = function not found / bad input.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poc_audit import STORE_MNEMONICS, track_registers, store_ea_and_value  # noqa: E402

ALLOWED_CALLS = {"__MaskIrq"}
DENIED_SUBSTRINGS = ("malloc", "free", "printf", "vsnprintf", "snprintf", "fopen", "fwrite", "fat",
                     "sdlog", "ringlog", "DCFlush", "DCInvalidate", "AR_", "ARQ", "dma", "read_block",
                     "write_block", "usb_", "gecko", "memcpy", "memset", "__UnmaskIrq", "IRQ_Request")

FUNC_RE = re.compile(r"^[0-9a-f]+ <(?P<name>[^>]+)>:\s*$")
INSN_RE = re.compile(r"^\s*(?P<off>[0-9a-f]+):\s+(?:[0-9a-f]{2} ){4}\s*(?P<mnem>\S+)(?:\s+(?P<ops>.*))?$")
RELOC_RE = re.compile(r"^\s*(?P<off>[0-9a-f]+):\s+(?P<type>R_PPC_\w+)\s+(?P<sym>\S+)")
PI_INTSR = 0xCC003000
PI_INTMR = 0xCC003004


def pi_store_sites(items):
    """(intsr_stores, intmr_stores): lists of (index, offset, mnemonic, operands, value_or_None)
    for every store whose effective address is PI INTSR / PI INTMR under the register values
    track_registers() proves on entry to that store (an unknown address never matches; a
    store the analysis cannot reach is dead code)."""
    insns, idxs = [], []
    relocs = set()
    for idx, (kind, off, payload) in enumerate(items):
        if kind == "insn":
            insns.append((off, payload[0], payload[1]))
            idxs.append(idx)
        else:
            relocs.add(off)
    states = track_registers(insns, relocs)
    intsr, intmr = [], []
    for (off, mn, ops), idx, regs in zip(insns, idxs, states):
        if regs is None or mn not in STORE_MNEMONICS:
            continue
        ea, value = store_ea_and_value(regs, mn, ops)
        if ea == PI_INTSR:
            intsr.append((idx, off, mn, ops, value))
        elif ea == PI_INTMR:
            intmr.append((idx, off, mn, ops, value))
    return intsr, intmr


def extract_function(text, name):
    """Returns the list of (kind, offset, payload) lines of function `name`:
    kind 'insn' -> (mnemonic, operands), kind 'reloc' -> (type, symbol)."""
    lines = text.splitlines()
    inside = False
    out = []
    for line in lines:
        m = FUNC_RE.match(line)
        if m:
            if inside:
                break
            inside = (m.group("name") == name)
            continue
        if not inside:
            continue
        if not line.strip():
            continue
        r = RELOC_RE.match(line)
        if r:
            out.append(("reloc", int(r.group("off"), 16), (r.group("type"), r.group("sym"))))
            continue
        i = INSN_RE.match(line)
        if i:
            out.append(("insn", int(i.group("off"), 16), (i.group("mnem"), i.group("ops") or "")))
    return out if inside else None


def audit(items):
    findings = []
    calls = []
    mftb = False
    pi_ref = False
    mask_index = None
    for idx, (kind, off, payload) in enumerate(items):
        if kind == "reloc":
            rtype, sym = payload
            sym_base = sym.split("+")[0].split("-")[0]
            if rtype in ("R_PPC_REL24", "R_PPC_ADDR24", "R_PPC_PLTREL24"):
                calls.append(sym_base)
                if sym_base not in ALLOWED_CALLS:
                    findings.append("call to %s is not allowed (allowed: %s)" % (sym_base, sorted(ALLOWED_CALLS)))
                elif sym_base == "__MaskIrq" and mask_index is None:
                    mask_index = idx
            for bad in DENIED_SUBSTRINGS:
                if bad in sym_base and sym_base not in ALLOWED_CALLS:
                    findings.append("reference to denied symbol %s" % sym_base)
                    break
            continue
        mnem, ops = payload
        if mnem in ("bctrl", "blrl", "bctr"):
            findings.append("indirect call/branch %s at 0x%x" % (mnem, off))
        if mnem == "mftb" or mnem == "mftbl" or (mnem == "mfspr" and "268" in ops):
            mftb = True
        if mnem == "lis" and ("-13312" in ops or "0xcc00" in ops or "52224" in ops or "-13311" in ops):
            pi_ref = True
        if mnem in ("sc",):
            findings.append("system call at 0x%x" % off)
    if not calls:
        findings.append("no call to __MaskIrq found (the handler must mask before acknowledging)")
    if not mftb:
        findings.append("no time-base read (mftb) found")
    if not pi_ref:
        findings.append("no PI register base (0xCC00xxxx) referenced")
    intsr_stores, intmr_stores = pi_store_sites(items)
    for st in intmr_stores:
        findings.append("store to PI INTMR at 0x%x (%s %s): the mask may change only through __MaskIrq" % (st[1], st[2], st[3]))
    if len(intsr_stores) != 1:
        findings.append("%d stores to PI INTSR (exactly one W1C acknowledge expected)%s"
                        % (len(intsr_stores), "" if not intsr_stores else ": " + ", ".join("0x%x" % st[1] for st in intsr_stores)))
    for st in intsr_stores:
        if st[4] != 0x2000:
            findings.append("INTSR store at 0x%x writes %s, not 0x2000" % (st[1], "an untracked value" if st[4] is None else "0x%x" % st[4]))
        if mask_index is None or st[0] < mask_index:
            findings.append("INTSR store at 0x%x precedes the __MaskIrq call (mask must precede the W1C)" % st[1])
    return findings, calls


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("objdump")
    ap.add_argument("--symbol", default="hsp_backend_oneshot_isr")
    ap.add_argument("--report", default=None)
    args = ap.parse_args(argv)
    with open(args.objdump, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    items = extract_function(text, args.symbol)
    if items is None:
        print("function %s not found in %s" % (args.symbol, args.objdump), file=sys.stderr)
        return 2
    findings, calls = audit(items)
    n_insn = sum(1 for k, _, _ in items if k == "insn")
    intsr_stores, intmr_stores = pi_store_sites(items)
    report = ["isr_audit: %s" % args.symbol, "instructions: %d" % n_insn,
              "calls: %s" % (", ".join(calls) if calls else "none"),
              "intsr stores: %d (%s)" % (len(intsr_stores), ", ".join("0x%x" % st[1] for st in intsr_stores) or "-"),
              "intmr stores: %d" % len(intmr_stores),
              "result: %s" % ("CLEAN" if not findings else "VIOLATION")]
    report += ["  - " + f for f in findings]
    report.append("--- listing ---")
    for kind, off, payload in items:
        if kind == "insn":
            report.append("  %4x: %-8s %s" % (off, payload[0], payload[1]))
        else:
            report.append("  %4x: %s %s" % (off, payload[0], payload[1]))
    out = "\n".join(report) + "\n"
    print(out, end="")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(out)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
