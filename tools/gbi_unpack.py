#!/usr/bin/env python3
"""
gbi_unpack — recover the executable image packed inside a Game Boy
Interface DOL (Extrems' Corner.org loader stub).

How the stub works (determined by static analysis of gbi.dol, see
docs/research/DEVLOG.md 2026-09-13): the DOL's data section holds a
28-byte build string ("libogc-rice r....") followed by a payload that is
XOR-obfuscated with the 40-byte copyright string found at the start of the
text section ("Copyright (c) 2026, Extrems' Corner.org\\0"), key byte index
= payload offset mod 40. De-XORed, the payload is an XZ stream (magic
FD 37 7A 58 5A 00). The stub decompresses it and jumps into it.

This tool only reads the input; the output is written to a path you choose
and must stay private (input/ or build/) because it is proprietary.

Usage:
    tools/gbi_unpack.py <gbi.dol> <out.bin>
"""
from __future__ import annotations

import hashlib
import lzma
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dolinfo  # noqa: E402

XZ_MAGIC = b"\xfd7zXZ\x00"
KEY_LEN = 40


def find_payload(data: bytes):
    """Return (key, payload_offset) or raise."""
    # Key: first KEY_LEN bytes of the first text section (copyright string).
    offs = struct.unpack_from(">18I", data, 0)
    sizes = struct.unpack_from(">18I", data, 0x90)
    text0 = offs[0]
    key = data[text0:text0 + KEY_LEN]
    if not key.startswith(b"Copyright"):
        raise ValueError("unexpected key at text0: %r" % key[:16])
    # Payload: search every data section for a de-XORed XZ magic.
    for i in range(7, 18):
        if sizes[i] == 0:
            continue
        sec = data[offs[i]:offs[i] + sizes[i]]
        for start in range(0, max(0, min(len(sec) - len(XZ_MAGIC) + 1, 0x1000))):
            probe = bytes(sec[start + j] ^ key[j % KEY_LEN] for j in range(len(XZ_MAGIC)))
            if probe == XZ_MAGIC:
                return key, offs[i] + start, offs[i] + sizes[i]
    raise ValueError("no XOR-obfuscated XZ payload found")


def unpack(data: bytes) -> bytes:
    key, start, end = find_payload(data)
    end = min(end, len(data))
    obf = data[start:end]
    plain = bytes(b ^ key[i % KEY_LEN] for i, b in enumerate(obf))
    dec = lzma.LZMADecompressor(format=lzma.FORMAT_XZ)
    out = dec.decompress(plain)
    return out, start, len(obf)


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 2:
        print(__doc__)
        return 2
    src, dst = argv
    with open(src, "rb") as f:
        data = f.read()
    try:
        out, start, size = unpack(data)
    except (ValueError, lzma.LZMAError) as e:
        print("gbi_unpack: %s" % e, file=sys.stderr)
        return 1
    with open(dst, "wb") as f:
        f.write(out)
    print("payload at 0x%X (%d bytes obfuscated) -> %d bytes, sha256 %s"
          % (start, size, len(out), hashlib.sha256(out).hexdigest()))
    print("input sha256 %s" % hashlib.sha256(data).hexdigest())
    head = out[:16]
    kind = "ELF" if head.startswith(b"\x7fELF") else "DOL?" if len(out) > 0x100 else "?"
    print("head: %s (%s)" % (head.hex(), kind))
    return 0


if __name__ == "__main__":
    sys.exit(main())
