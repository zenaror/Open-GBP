#!/usr/bin/env python3
"""
dolpad — rewrite a DOL so every text/data section has a 32-byte-multiple
size (and 32-byte-aligned file offset), padding with zero bytes.

Why this exists
    devkitPro's elf2dol emits section sizes equal to the ELF PT_LOAD
    segment sizes, which are generally not multiples of 32. The DOL format
    does not require 32-byte sizes and physical loaders (IPL, Swiss) load
    such files fine, but Dolphin 2606a refuses to boot them:

        E[BOOT]: Text section 0 is not 32-byte aligned: address = ..., size = ...
        (Core/Boot/DolReader.cpp, DolReader::Initialize returns false)

    Padding the sizes makes one artifact valid for both Dolphin and real
    hardware.

Safety rules enforced here (the tool fails loudly instead of guessing):
    * load addresses must already be 32-byte aligned (we never move code);
    * the padded memory range of a section must not overlap the original
      range of any other section (zero padding must never clobber bytes
      that another section loads);
    * the output re-parses as a valid DOL with the same entry point, BSS,
      section addresses and original payload bytes.

Padding may extend into the BSS region or into linker alignment gaps; both
are zero-filled by the runtime anyway.

Usage:
    tools/dolpad.py <in.dol> <out.dol>
    tools/dolpad.py --check <file.dol>       exit 1 if padding would be needed

Importable: pad_dol(bytes) -> bytes, raises dolinfo.DolError.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dolinfo  # noqa: E402

ALIGN = 32


def _align_up(n: int, a: int = ALIGN) -> int:
    return (n + a - 1) // a * a


def pad_dol(data: bytes) -> bytes:
    """Return a new DOL image with 32-byte-multiple section sizes."""
    info = dolinfo.parse_dol(data)

    for s in info.sections:
        if s.load_address % ALIGN:
            raise dolinfo.DolError(
                "%s section %d load address 0x%08X is not 32-byte aligned; "
                "dolpad only pads sizes, it never relocates" % (s.kind, s.index, s.load_address))

    # Memory-overlap check against the ORIGINAL ranges of other sections.
    padded = {(s.kind, s.index): _align_up(s.size) for s in info.sections}
    for s in info.sections:
        new_end = s.load_address + padded[(s.kind, s.index)]
        for o in info.sections:
            if o is s:
                continue
            if s.load_address < o.end_address and o.load_address < new_end:
                raise dolinfo.DolError(
                    "padding %s section %d to 0x%08X-0x%08X would overlap %s section %d "
                    "(0x%08X-0x%08X)" % (s.kind, s.index, s.load_address, new_end,
                                          o.kind, o.index, o.load_address, o.end_address))

    # Rebuild: header + sections laid out in original section order, each
    # payload zero-padded, file offsets 32-byte aligned.
    hdr = bytearray(data[:dolinfo.DOL_HEADER_SIZE])
    body = bytearray()
    offsets = [0] * dolinfo.DOL_SECTIONS
    addrs = [0] * dolinfo.DOL_SECTIONS
    sizes = [0] * dolinfo.DOL_SECTIONS
    for s in sorted(info.sections, key=lambda x: x.file_offset):
        slot = s.index if s.kind == "text" else dolinfo.DOL_TEXT_SECTIONS + s.index
        payload = data[s.file_offset:s.file_offset + s.size]
        new_size = padded[(s.kind, s.index)]
        file_off = dolinfo.DOL_HEADER_SIZE + len(body)
        offsets[slot] = file_off
        addrs[slot] = s.load_address
        sizes[slot] = new_size
        body += payload + b"\0" * (new_size - s.size)
    struct.pack_into(">%dI" % dolinfo.DOL_SECTIONS, hdr, 0x00, *offsets)
    struct.pack_into(">%dI" % dolinfo.DOL_SECTIONS, hdr, 0x48, *addrs)
    struct.pack_into(">%dI" % dolinfo.DOL_SECTIONS, hdr, 0x90, *sizes)
    out = bytes(hdr) + bytes(body)

    # Post-conditions.
    new = dolinfo.parse_dol(out)
    if not new.dolphin_loadable:
        raise dolinfo.DolError("internal error: output still unaligned")
    if (new.entry_point, new.bss_address, new.bss_size) != \
            (info.entry_point, info.bss_address, info.bss_size):
        raise dolinfo.DolError("internal error: header fields changed")
    by_key_new = {(s.kind, s.index): s for s in new.sections}
    for s in info.sections:
        n = by_key_new[(s.kind, s.index)]
        if n.load_address != s.load_address or n.size != padded[(s.kind, s.index)]:
            raise dolinfo.DolError("internal error: section %s %d mismatch" % (s.kind, s.index))
        if out[n.file_offset:n.file_offset + s.size] != data[s.file_offset:s.file_offset + s.size]:
            raise dolinfo.DolError("internal error: payload of %s %d changed" % (s.kind, s.index))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="pad DOL section sizes to 32-byte multiples")
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--check", action="store_true",
                    help="only report; exit 1 if the input needs padding")
    args = ap.parse_args(argv)
    try:
        with open(args.input, "rb") as f:
            data = f.read()
        info = dolinfo.parse_dol(data)
        if args.check:
            if info.dolphin_loadable:
                print("dolpad: %s: already 32-byte aligned" % args.input)
                return 0
            for s in info.unaligned_sections:
                print("dolpad: %s: %s section %d size 0x%X not aligned"
                      % (args.input, s.kind, s.index, s.size))
            return 1
        if not args.output:
            ap.error("output path required unless --check")
        out = pad_dol(data)
    except (OSError, dolinfo.DolError) as e:
        print("dolpad: %s: %s" % (args.input, e), file=sys.stderr)
        return 1
    with open(args.output, "wb") as f:
        f.write(out)
    print("dolpad: %s -> %s (%d -> %d bytes, %d section(s) padded)"
          % (args.input, args.output, len(data), len(out), len(info.unaligned_sections)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
