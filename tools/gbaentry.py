#!/usr/bin/env python3
"""
tools/gbaentry.py — point an AGB ROM's entry branch at a stub of its own, and prove what was changed.

    tools/gbaentry.py <rom.gba> <rom.elf> <symbol>

GitHub Issue #124, Round C. devkitARM's GBA crt0 owns the first word of the ROM: `b rom_header_end`, which falls into
its start_vector. A ROM that must read an I/O register BEFORE crt0 runs -- `agb-route`'s first SOUNDBIAS read -- needs
that word to branch to its own stub instead, and the stub branches on to crt0's start_vector itself. This tool makes
that one change and nothing else:

  * it reads <symbol>'s address from the ELF's symbol table (ELF32, little-endian; standard library only);
  * it REQUIRES the ROM's first word to be crt0's branch to 0x080000C0 (0xEA00002E), or already the branch this tool
    writes (a rebuild is idempotent), and refuses anything else;
  * it REQUIRES the stub to be ARM code inside the image, past the header (word-aligned, bit 0 clear -- the BIOS
    enters the ROM in ARM state);
  * it writes the ARM branch 0xEA000000 | ((target - 0x08000000 - 8) >> 2) and prints both words.

The header's complement check does not cover 0x000..0x003, so tools/gbahdr.py's check is unchanged by it; gbahdr and
gbaderive still see an ARM branch there. Nothing past the first word changes.
"""
import struct
import sys

ROM_BASE = 0x08000000
CRT0_ENTRY = 0xEA00002E                     # crt0's `b rom_header_end`: 0x08000000 + 8 + 4 x 0x2E = 0x080000C0


def elf_symbol(elf, name):
    """(value, size) of a symbol in an ELF32 little-endian file's .symtab."""
    if elf[:4] != b"\x7fELF" or elf[4] != 1 or elf[5] != 1:
        raise ValueError("not an ELF32 little-endian file")
    shoff, = struct.unpack_from("<I", elf, 0x20)
    shentsize, shnum = struct.unpack_from("<HH", elf, 0x2E)
    sections = [struct.unpack_from("<IIIIIIIIII", elf, shoff + i * shentsize) for i in range(shnum)]
    for s in sections:
        if s[1] != 2:                                   # SHT_SYMTAB
            continue
        strtab = sections[s[6]]                         # sh_link
        for off in range(s[4], s[4] + s[5], s[9]):      # sh_offset, sh_size, sh_entsize
            st_name, st_value, st_size = struct.unpack_from("<III", elf, off)
            end = elf.index(b"\0", strtab[4] + st_name)
            if elf[strtab[4] + st_name:end].decode("ascii", "replace") == name:
                return st_value, st_size
    raise KeyError("symbol %s not found" % name)


def branch_to(target):
    """The ARM B instruction at ROM_BASE that lands on target."""
    delta = target - ROM_BASE - 8
    if delta % 4 or not (-(1 << 25) <= delta < (1 << 25)):
        raise ValueError("target 0x%08X is not reachable by an ARM branch from the entry" % target)
    return 0xEA000000 | ((delta >> 2) & 0x00FFFFFF)


def patch(rom, elf, symbol):
    """The patched ROM and a report; raises on anything the tool must refuse."""
    addr, size = elf_symbol(elf, symbol)
    if addr & 3:
        raise ValueError("%s at 0x%08X is not word-aligned ARM code (Thumb bit or misaligned)" % (symbol, addr))
    off = addr - ROM_BASE
    if not (0xC0 <= off < len(rom) - 4):
        raise ValueError("%s at 0x%08X lies outside the image past the header" % (symbol, addr))
    new = branch_to(addr)
    old = struct.unpack_from("<I", rom, 0)[0]
    if old not in (CRT0_ENTRY, new):
        raise ValueError("the entry word is 0x%08X, neither crt0's branch 0x%08X nor this stub's 0x%08X"
                         % (old, CRT0_ENTRY, new))
    out = bytearray(rom)
    struct.pack_into("<I", out, 0, new)
    return bytes(out), {"symbol": symbol, "address": addr, "size": size, "old": old, "new": new}


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    rom_path, elf_path, symbol = argv[1:4]
    with open(rom_path, "rb") as f:
        rom = f.read()
    with open(elf_path, "rb") as f:
        elf = f.read()
    try:
        out, r = patch(rom, elf, symbol)
    except (ValueError, KeyError) as e:
        print("refusing: %s" % e, file=sys.stderr)
        return 1
    with open(rom_path, "wb") as f:
        f.write(out)
    print("entry  0x%08X -> 0x%08X  (b %s at 0x%08X, %d bytes)" % (r["old"], r["new"], symbol, r["address"], r["size"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
