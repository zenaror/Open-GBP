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
  - a store of 0x2000 exists after the __MaskIrq call (mask before W1C),
    judged on instruction order inside the function.

Usage:
    tools/isr_audit.py <objdump.txt> [--report out.txt] [--symbol NAME]
Exit status 0 = clean, 1 = violation, 2 = function not found / bad input.
"""
from __future__ import annotations

import argparse
import re
import sys

ALLOWED_CALLS = {"__MaskIrq"}
DENIED_SUBSTRINGS = ("malloc", "free", "printf", "vsnprintf", "snprintf", "fopen", "fwrite", "fat",
                     "sdlog", "ringlog", "DCFlush", "DCInvalidate", "AR_", "ARQ", "dma", "read_block",
                     "write_block", "usb_", "gecko", "memcpy", "memset", "__UnmaskIrq", "IRQ_Request")

FUNC_RE = re.compile(r"^[0-9a-f]+ <(?P<name>[^>]+)>:\s*$")
INSN_RE = re.compile(r"^\s*(?P<off>[0-9a-f]+):\s+(?:[0-9a-f]{2} ){4}\s*(?P<mnem>\S+)(?:\s+(?P<ops>.*))?$")
RELOC_RE = re.compile(r"^\s*(?P<off>[0-9a-f]+):\s+(?P<type>R_PPC_\w+)\s+(?P<sym>\S+)")


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
    w1c_after_mask = False
    li_2000_seen_after_mask = False
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
        if mnem == "lis" and ("-13312" in ops or "0xcc00" in ops or "52224" in ops):
            pi_ref = True
        if mask_index is not None and idx > mask_index:
            if mnem == "li" and ("8192" in ops or "0x2000" in ops):
                li_2000_seen_after_mask = True
            if mnem in ("stw", "stwx") and li_2000_seen_after_mask:
                w1c_after_mask = True
        if mnem in ("sc",):
            findings.append("system call at 0x%x" % off)
    if not calls:
        findings.append("no call to __MaskIrq found (the handler must mask before acknowledging)")
    if not mftb:
        findings.append("no time-base read (mftb) found")
    if not pi_ref:
        findings.append("no PI register base (0xCC00xxxx) referenced")
    if mask_index is not None and not w1c_after_mask:
        findings.append("no 0x2000 store after the __MaskIrq call (mask must precede the W1C)")
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
    report = ["isr_audit: %s" % args.symbol, "instructions: %d" % n_insn,
              "calls: %s" % (", ".join(calls) if calls else "none"),
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
