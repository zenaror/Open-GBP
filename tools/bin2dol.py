#!/usr/bin/env python3
"""
bin2dol — wrap a raw PowerPC memory image into a minimal DOL with one text
section, so tools that only understand DOL (Ghidra GameCubeLoader,
dolinfo) can load it at a known address.

Usage: tools/bin2dol.py <image.bin> <load_addr_hex> <out.dol> [entry_hex]
"""
import struct
import sys


def main(argv):
    if len(argv) not in (3, 4):
        print(__doc__)
        return 2
    src, addr, dst = argv[0], int(argv[1], 16), argv[2]
    entry = int(argv[3], 16) if len(argv) == 4 else addr
    data = open(src, "rb").read()
    pad = (-len(data)) % 32
    data += b"\0" * pad
    hdr = bytearray(0x100)
    struct.pack_into(">I", hdr, 0x00, 0x100)      # text0 offset
    struct.pack_into(">I", hdr, 0x48, addr)       # text0 address
    struct.pack_into(">I", hdr, 0x90, len(data))  # text0 size
    struct.pack_into(">III", hdr, 0xD8, 0, 0, entry)
    open(dst, "wb").write(bytes(hdr) + data)
    print("%s: %d bytes at 0x%08X entry 0x%08X -> %s" % (src, len(data), addr, entry, dst))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
