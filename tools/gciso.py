#!/usr/bin/env python3
"""
gciso — read-only GameCube disc image (ISO/GCM) parser and extractor.

Disc layout (public format, see YAGCD chapter 13):

    0x0000  boot.bin      0x440 bytes: game id, name, DOL offset (0x420),
                          FST offset/size/max (0x424/0x428/0x42C), ...
    0x0440  bi2.bin       0x2000 bytes: debug monitor size, arena, country...
    0x2440  apploader     header 0x20 (date, entry, size, trailer size) + code
    <0x420> main.dol
    <0x424> fst.bin       file system table (root entry + entries + string table)

Usage:
    tools/gciso.py info <image>                  print header + file list
    tools/gciso.py extract <image> <outdir>      write boot.bin, bi2.bin,
                                                 apploader.img, main.dol,
                                                 fst.bin, files/... and
                                                 manifest.json (paths, sizes,
                                                 offsets, SHA-256)

The image is only ever opened for reading. Extraction output must stay in
an ignored/private directory when the disc is proprietary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional

DISC_MAGIC = 0xC2339F3D
BOOT_SIZE = 0x440
BI2_OFFSET = 0x440
BI2_SIZE = 0x2000
APPLOADER_OFFSET = 0x2440
APPLOADER_HDR = 0x20


class GcIsoError(ValueError):
    pass


@dataclass
class DiscHeader:
    game_id: str
    maker_code: str
    disc_number: int
    version: int
    audio_streaming: int
    stream_buffer_size: int
    magic: int
    game_name: str
    debug_monitor_offset: int
    debug_monitor_addr: int
    dol_offset: int
    fst_offset: int
    fst_size: int
    fst_max_size: int
    user_position: int
    user_length: int


@dataclass
class FstEntry:
    path: str
    is_dir: bool
    offset: int   # file data offset (files) or parent index (dirs)
    size: int     # file size (files) or next index (dirs)


@dataclass
class Apploader:
    date: str
    entry_point: int
    size: int
    trailer_size: int
    total_size: int


def sha256_of(fobj, offset: int, size: int, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    fobj.seek(offset)
    remaining = size
    while remaining > 0:
        data = fobj.read(min(chunk, remaining))
        if not data:
            raise GcIsoError("unexpected EOF at 0x%X" % (offset + size - remaining))
        h.update(data)
        remaining -= len(data)
    return h.hexdigest()


def parse_header(boot: bytes) -> DiscHeader:
    if len(boot) < BOOT_SIZE:
        raise GcIsoError("boot.bin too short")
    magic = struct.unpack_from(">I", boot, 0x1C)[0]
    if magic != DISC_MAGIC:
        raise GcIsoError("bad disc magic 0x%08X (expected 0x%08X)" % (magic, DISC_MAGIC))
    dbg_off, dbg_addr = struct.unpack_from(">II", boot, 0x400)
    # 0x408..0x41F unused
    dol_off, fst_off, fst_size, fst_max, user_pos, user_len = \
        struct.unpack_from(">IIIIII", boot, 0x420)
    return DiscHeader(
        game_id=boot[0:4].decode("ascii", "replace"),
        maker_code=boot[4:6].decode("ascii", "replace"),
        disc_number=boot[6], version=boot[7], audio_streaming=boot[8],
        stream_buffer_size=boot[9], magic=magic,
        game_name=boot[0x20:0x400].split(b"\0", 1)[0].decode("ascii", "replace"),
        debug_monitor_offset=dbg_off, debug_monitor_addr=dbg_addr,
        dol_offset=dol_off, fst_offset=fst_off, fst_size=fst_size,
        fst_max_size=fst_max, user_position=user_pos, user_length=user_len)


def parse_apploader(hdr: bytes) -> Apploader:
    date = hdr[0:0x10].split(b"\0", 1)[0].decode("ascii", "replace")
    entry, size, trailer = struct.unpack_from(">III", hdr, 0x10)
    return Apploader(date, entry, size, trailer, APPLOADER_HDR + size + trailer)


def parse_fst(fst: bytes) -> List[FstEntry]:
    if len(fst) < 12:
        raise GcIsoError("FST too short")
    root_next = struct.unpack_from(">I", fst, 8)[0]
    count = root_next
    strtab = 12 * count
    entries: List[FstEntry] = []
    dir_stack = [("", count)]  # (path prefix, end index)
    for i in range(1, count):
        flags_name, off, size = struct.unpack_from(">III", fst, 12 * i)
        is_dir = (flags_name >> 24) & 1
        name_off = flags_name & 0x00FFFFFF
        end = fst.index(b"\0", strtab + name_off)
        name = fst[strtab + name_off:end].decode("ascii", "replace")
        while len(dir_stack) > 1 and i >= dir_stack[-1][1]:
            dir_stack.pop()
        path = dir_stack[-1][0] + name
        entries.append(FstEntry(path, bool(is_dir), off, size))
        if is_dir:
            dir_stack.append((path + "/", size))
    return entries


def dol_total_size(dol_hdr: bytes) -> int:
    """Size of a DOL image = max(section offset + size) over used sections."""
    offs = struct.unpack_from(">18I", dol_hdr, 0x00)
    sizes = struct.unpack_from(">18I", dol_hdr, 0x90)
    end = 0x100
    for o, s in zip(offs, sizes):
        if s:
            end = max(end, o + s)
    return end


def read_image(path: str):
    f = open(path, "rb")
    f.seek(0, os.SEEK_END)
    total = f.tell()
    f.seek(0)
    hdr = parse_header(f.read(BOOT_SIZE))
    f.seek(APPLOADER_OFFSET)
    apl = parse_apploader(f.read(APPLOADER_HDR))
    f.seek(hdr.dol_offset)
    dol_size = dol_total_size(f.read(0x100))
    f.seek(hdr.fst_offset)
    fst = f.read(hdr.fst_size)
    entries = parse_fst(fst)
    return f, total, hdr, apl, dol_size, entries


def cmd_info(args) -> int:
    f, total, hdr, apl, dol_size, entries = read_image(args.image)
    with f:
        print("image        : %s (%d bytes)" % (args.image, total))
        print("game id      : %s%s  disc %d  version %d" % (hdr.game_id, hdr.maker_code,
                                                             hdr.disc_number, hdr.version))
        print("name         : %s" % hdr.game_name)
        print("apploader    : offset 0x%X  date %s  entry 0x%08X  size 0x%X (+trailer 0x%X)"
              % (APPLOADER_OFFSET, apl.date, apl.entry_point, apl.size, apl.trailer_size))
        print("main.dol     : offset 0x%X  size 0x%X (%d bytes)" % (hdr.dol_offset, dol_size, dol_size))
        print("fst          : offset 0x%X  size 0x%X  max 0x%X  entries %d"
              % (hdr.fst_offset, hdr.fst_size, hdr.fst_max_size, len(entries)))
        print("user area    : 0x%X + 0x%X" % (hdr.user_position, hdr.user_length))
        print("files:")
        for e in entries:
            if e.is_dir:
                print("  %s/" % e.path)
            else:
                print("  %-40s 0x%08X  %10d" % (e.path, e.offset, e.size))
    return 0


def cmd_extract(args) -> int:
    f, total, hdr, apl, dol_size, entries = read_image(args.image)
    out = args.outdir
    os.makedirs(os.path.join(out, "files"), exist_ok=True)
    manifest = {"image": os.path.abspath(args.image), "image_size": total,
                "image_sha256": None, "header": asdict(hdr), "apploader": asdict(apl),
                "parts": []}

    def dump(name, offset, size, dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        h = hashlib.sha256()
        f.seek(offset)
        with open(dest, "wb") as o:
            remaining = size
            while remaining > 0:
                data = f.read(min(1 << 20, remaining))
                if not data:
                    raise GcIsoError("EOF extracting %s" % name)
                o.write(data)
                h.update(data)
                remaining -= len(data)
        manifest["parts"].append({"name": name, "offset": offset, "size": size,
                                  "path": os.path.relpath(dest, out), "sha256": h.hexdigest()})

    with f:
        if not args.no_image_hash:
            manifest["image_sha256"] = sha256_of(f, 0, total)
        dump("boot.bin", 0, BOOT_SIZE, os.path.join(out, "sys", "boot.bin"))
        dump("bi2.bin", BI2_OFFSET, BI2_SIZE, os.path.join(out, "sys", "bi2.bin"))
        dump("apploader.img", APPLOADER_OFFSET, apl.total_size, os.path.join(out, "sys", "apploader.img"))
        dump("main.dol", hdr.dol_offset, dol_size, os.path.join(out, "sys", "main.dol"))
        dump("fst.bin", hdr.fst_offset, hdr.fst_size, os.path.join(out, "sys", "fst.bin"))
        for e in entries:
            if not e.is_dir:
                dump("files/" + e.path, e.offset, e.size, os.path.join(out, "files", *e.path.split("/")))
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as m:
        json.dump(manifest, m, indent=2)
    print("extracted %d parts to %s (manifest.json written)" % (len(manifest["parts"]), out))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="read-only GameCube disc image tool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info"); p.add_argument("image"); p.set_defaults(fn=cmd_info)
    p = sub.add_parser("extract"); p.add_argument("image"); p.add_argument("outdir")
    p.add_argument("--no-image-hash", action="store_true", help="skip hashing the whole image")
    p.set_defaults(fn=cmd_extract)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (OSError, GcIsoError) as e:
        print("gciso: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
