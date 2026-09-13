#!/usr/bin/env python3
"""
dolinfo — parse and validate Nintendo GameCube DOL executable headers.

The DOL format is simple and public: a 0x100-byte big-endian header with
7 text sections and 11 data sections (file offset / load address / size
tables), a BSS address/size, and an entry point.

Usage:
    tools/dolinfo.py <file.dol>            human-readable summary
    tools/dolinfo.py --json <file.dol>     machine-readable JSON

Exit status is nonzero when the file is not a structurally valid DOL.
The parser is also importable (see tests/host/test_dolinfo.py).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass, asdict, field
from typing import List

DOL_HEADER_SIZE = 0x100
DOL_TEXT_SECTIONS = 7
DOL_DATA_SECTIONS = 11
DOL_SECTIONS = DOL_TEXT_SECTIONS + DOL_DATA_SECTIONS

# GameCube physical RAM as seen through the cached mapping.
MEM1_BASE = 0x80000000
MEM1_END = 0x81800000  # 24 MiB

# Header layout (all u32 big-endian)
_OFF_TEXT_OFFSET = 0x00
_OFF_DATA_OFFSET = 0x1C
_OFF_TEXT_ADDR = 0x48
_OFF_DATA_ADDR = 0x64
_OFF_TEXT_SIZE = 0x90
_OFF_DATA_SIZE = 0xAC
_OFF_BSS_ADDR = 0xD8
_OFF_BSS_SIZE = 0xDC
_OFF_ENTRY = 0xE0


class DolError(ValueError):
    """Raised when the input is not a structurally valid DOL image."""


@dataclass
class DolSection:
    kind: str       # "text" or "data"
    index: int
    file_offset: int
    load_address: int
    size: int

    @property
    def end_address(self) -> int:
        return self.load_address + self.size

    @property
    def aligned32(self) -> bool:
        """True when address and size are both multiples of 32 bytes.

        The DOL format itself does not require this and physical loaders
        (IPL, Swiss) accept unaligned sections, but Dolphin 2606a rejects a
        DOL whose text/data sections are not 32-byte aligned in both
        address and size (Core/Boot/DolReader.cpp, DolReader::Initialize).
        """
        return (self.load_address & 31) == 0 and (self.size & 31) == 0


@dataclass
class DolInfo:
    file_size: int
    entry_point: int
    bss_address: int
    bss_size: int
    sections: List[DolSection] = field(default_factory=list)

    @property
    def text_sections(self) -> List[DolSection]:
        return [s for s in self.sections if s.kind == "text"]

    @property
    def data_sections(self) -> List[DolSection]:
        return [s for s in self.sections if s.kind == "data"]

    def section_containing(self, address: int):
        for s in self.sections:
            if s.load_address <= address < s.end_address:
                return s
        return None

    @property
    def unaligned_sections(self) -> List[DolSection]:
        return [s for s in self.sections if not s.aligned32]

    @property
    def dolphin_loadable(self) -> bool:
        """All sections satisfy Dolphin 2606a's 32-byte alignment rule."""
        return not self.unaligned_sections

    def to_dict(self) -> dict:
        d = asdict(self)
        for sd, s in zip(d["sections"], self.sections):
            sd["aligned32"] = s.aligned32
        d["text_section_count"] = len(self.text_sections)
        d["data_section_count"] = len(self.data_sections)
        d["dolphin_loadable"] = self.dolphin_loadable
        return d


def _u32s(buf: bytes, offset: int, count: int) -> List[int]:
    return list(struct.unpack_from(">%dI" % count, buf, offset))


def parse_dol(data: bytes) -> DolInfo:
    """Parse a DOL image from bytes. Raises DolError on structural problems."""
    if len(data) < DOL_HEADER_SIZE:
        raise DolError("file too small for DOL header (%d < %d bytes)"
                       % (len(data), DOL_HEADER_SIZE))

    offsets = _u32s(data, _OFF_TEXT_OFFSET, DOL_SECTIONS)
    addrs = _u32s(data, _OFF_TEXT_ADDR, DOL_SECTIONS)
    sizes = _u32s(data, _OFF_TEXT_SIZE, DOL_SECTIONS)
    bss_addr, bss_size, entry = _u32s(data, _OFF_BSS_ADDR, 3)

    info = DolInfo(file_size=len(data), entry_point=entry,
                   bss_address=bss_addr, bss_size=bss_size)

    for i in range(DOL_SECTIONS):
        if sizes[i] == 0 and offsets[i] == 0 and addrs[i] == 0:
            continue  # unused slot
        kind = "text" if i < DOL_TEXT_SECTIONS else "data"
        index = i if i < DOL_TEXT_SECTIONS else i - DOL_TEXT_SECTIONS
        sec = DolSection(kind, index, offsets[i], addrs[i], sizes[i])
        if sec.size == 0:
            raise DolError("%s section %d has offset/address but zero size" % (kind, index))
        if sec.file_offset < DOL_HEADER_SIZE:
            raise DolError("%s section %d overlaps the header (offset 0x%X)"
                           % (kind, index, sec.file_offset))
        if sec.file_offset + sec.size > len(data):
            raise DolError("%s section %d extends past end of file "
                           "(offset 0x%X size 0x%X file 0x%X)"
                           % (kind, index, sec.file_offset, sec.size, len(data)))
        if not (MEM1_BASE <= sec.load_address and sec.end_address <= MEM1_END):
            raise DolError("%s section %d load range 0x%08X-0x%08X outside MEM1"
                           % (kind, index, sec.load_address, sec.end_address))
        info.sections.append(sec)

    if not info.text_sections:
        raise DolError("no text sections")
    if info.section_containing(entry) is None or \
            info.section_containing(entry).kind != "text":
        raise DolError("entry point 0x%08X is not inside a text section" % entry)
    if entry & 3:
        raise DolError("entry point 0x%08X is not 4-byte aligned" % entry)
    if bss_size and not (MEM1_BASE <= bss_addr and bss_addr + bss_size <= MEM1_END):
        raise DolError("BSS 0x%08X+0x%X outside MEM1" % (bss_addr, bss_size))

    return info


def parse_dol_file(path: str) -> DolInfo:
    with open(path, "rb") as f:
        return parse_dol(f.read())


def format_summary(info: DolInfo) -> str:
    lines = [
        "file size   : %d bytes" % info.file_size,
        "entry point : 0x%08X" % info.entry_point,
        "bss         : 0x%08X size 0x%X (%d bytes)" % (info.bss_address, info.bss_size, info.bss_size),
        "sections    : %d text, %d data" % (len(info.text_sections), len(info.data_sections)),
        "dolphin ok  : %s" % ("yes" if info.dolphin_loadable else
                              "NO (section address/size not 32-byte aligned)"),
        "  kind idx  file_off   load_addr   end_addr    size     align32",
    ]
    for s in info.sections:
        lines.append("  %-4s %-3d  0x%06X   0x%08X  0x%08X  0x%06X  %s" %
                     (s.kind, s.index, s.file_offset, s.load_address, s.end_address, s.size,
                      "ok" if s.aligned32 else "NO"))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dol", help="path to .dol file")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--require-aligned", action="store_true",
                    help="exit 1 unless every section is 32-byte aligned (Dolphin rule)")
    ap.add_argument("--read", metavar="ADDR:LEN", action="append", default=[],
                    help="hex-dump LEN bytes at load address ADDR (e.g. 0x801b34c8:0x20)")
    args = ap.parse_args(argv)
    try:
        info = parse_dol_file(args.dol)
    except (OSError, DolError) as e:
        print("dolinfo: %s: %s" % (args.dol, e), file=sys.stderr)
        return 1
    if args.read:
        with open(args.dol, "rb") as f:
            blob = f.read()
        for spec in args.read:
            a, n = spec.split(":")
            addr, length = int(a, 16), int(n, 16)
            sec = info.section_containing(addr)
            if sec is None or addr + length > sec.end_address:
                print("dolinfo: 0x%08X+0x%X not inside a single section" % (addr, length), file=sys.stderr)
                return 1
            off = sec.file_offset + (addr - sec.load_address)
            chunk = blob[off:off + length]
            for i in range(0, len(chunk), 16):
                row = chunk[i:i + 16]
                print("%08X  %s  %s" % (addr + i, row.hex(" "),
                                        "".join(chr(b) if 32 <= b < 127 else "." for b in row)))
        return 0
    if args.require_aligned and not info.dolphin_loadable:
        for s in info.unaligned_sections:
            print("dolinfo: %s: %s section %d not 32-byte aligned (addr 0x%08X size 0x%X)"
                  % (args.dol, s.kind, s.index, s.load_address, s.size), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(info.to_dict(), indent=2))
    else:
        print(format_summary(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
