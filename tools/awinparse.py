#!/usr/bin/env python3
"""
tools/awinparse.py — a strict reader for the OGBPAW1 sidecar
(src/gbp/gbp_awindump.h), written for the ingestion of RUN 30 (GitHub Issue
#62).

IT IS A PARSER, NOT A CONSTRUCTION. The verdicts of §V8 live in
`tools/v8audio.py`, which was written before this image existed and is not
adjusted to anything the blocks contain (#50). This file only turns a 5.2 MB
file into windows and anchors, and it refuses a file that does not satisfy the
contract rather than reading it optimistically:

  * the magic, the version, the record size and the block size;
  * the header CRC-32 over the first 0xFC bytes;
  * the footer magic and the CRC-32 over EVERYTHING before the footer;
  * each anchor's own CRC-32 and its reserved bytes;
  * the offsets, the counts and the sum of the per-window block counts.

Its CRC is the runtime's own (`src/gbp/gbp_crc32.c`): the reflected 0xEDB88320
polynomial, initialised and finalised with 0xFFFFFFFF — zlib's CRC-32.

THE FILE IS OPENED READ-ONLY AND NEVER REWRITTEN. The raw drop in `logs/` is
the Operator's and is never touched; the copy under `captures/local/` is the
one read here.
"""
import struct
import zlib

MAGIC = b"OGBPAW1\0"
END = b"OGBPAWND"
VERSION = 1
HEADER_SIZE = 0x100
RECORD_SIZE = 128
FOOTER_SIZE = 12
BLOCK_SIZE = 0x1000
BLOCKS_PER_WINDOW = 256

F_CLOSED, F_INCOMPLETE, F_GAP = 0x0001, 0x0002, 0x0004
FLAG_TRUNCATED, FLAG_INCOMPLETE, FLAG_GAP, FLAG_REFUSED = 0x0001, 0x0002, 0x0004, 0x0008

KIND = {0: "control", 1: "press"}


def crc32(b):
    """The runtime's gbp_crc32: zlib's CRC-32, bit for bit."""
    return zlib.crc32(b) & 0xFFFFFFFF


class AwinError(Exception):
    pass


def _u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def _u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def _u64(b, o):
    return struct.unpack_from(">Q", b, o)[0]


def _ident(b, o):
    f = b[o:o + 32]
    if f[-1] != 0:
        raise AwinError("identity at 0x%X is not terminated" % o)
    s = f.split(b"\0", 1)[0]
    if any(c != 0 for c in f[len(s):]):
        raise AwinError("identity at 0x%X has bytes after its terminator" % o)
    return s.decode("ascii")


def parse(data):
    """Returns (header, anchors, blocks_offset). Raises AwinError on anything
    the C parser would refuse."""
    if len(data) < HEADER_SIZE + FOOTER_SIZE:
        raise AwinError("shorter than a header and a footer")
    if data[:8] != MAGIC:
        raise AwinError("magic is %r" % data[:8])
    h = {
        "version": _u16(data, 0x08), "header_size": _u16(data, 0x0A),
        "flags": _u32(data, 0x0C), "block_size": _u32(data, 0x10),
        "blocks_per_window": _u32(data, 0x14), "windows_n": _u32(data, 0x18),
        "record_size": _u32(data, 0x1C), "blocks_stored": _u32(data, 0x20),
        "blocks_seen": _u32(data, 0x24), "blocks_ignored": _u32(data, 0x28),
        "blocks_failed": _u32(data, 0x2C), "arms": _u32(data, 0x30),
        "arm_refused_busy": _u32(data, 0x34), "arm_refused_full": _u32(data, 0x38),
        "windows_closed": _u32(data, 0x3C), "tb_hz": _u32(data, 0x40),
        "ticks_min": _u32(data, 0x44), "ticks_max": _u32(data, 0x48),
        "ticks_n": _u32(data, 0x4C), "ticks_sum": _u64(data, 0x50),
        "off_records": _u32(data, 0x58), "off_blocks": _u32(data, 0x5C),
        "off_footer": _u32(data, 0x60), "total_size": _u64(data, 0x68),
        "test_id": _ident(data, 0x70), "build_id": _ident(data, 0x90),
        "app": _ident(data, 0xB0), "commit": _ident(data, 0xD0),
        "header_crc32": _u32(data, HEADER_SIZE - 4),
    }
    if h["version"] != VERSION or h["header_size"] != HEADER_SIZE:
        raise AwinError("version/header size")
    if h["record_size"] != RECORD_SIZE or h["block_size"] != BLOCK_SIZE:
        raise AwinError("record/block size")
    if crc32(data[:HEADER_SIZE - 4]) != h["header_crc32"]:
        raise AwinError("header CRC")
    if h["flags"] & ~(FLAG_TRUNCATED | FLAG_INCOMPLETE | FLAG_GAP | FLAG_REFUSED):
        raise AwinError("unknown header flags 0x%04X" % h["flags"])
    if any(data[i] for i in range(0xF0, HEADER_SIZE - 4)):
        raise AwinError("reserved header bytes are not zero")
    if h["off_records"] != HEADER_SIZE:
        raise AwinError("off_records")
    if h["off_blocks"] != HEADER_SIZE + h["windows_n"] * RECORD_SIZE:
        raise AwinError("off_blocks")
    if h["off_footer"] != h["off_blocks"] + h["blocks_stored"] * BLOCK_SIZE:
        raise AwinError("off_footer")
    if h["total_size"] != h["off_footer"] + FOOTER_SIZE or len(data) != h["total_size"]:
        raise AwinError("total size %d against %d bytes" % (h["total_size"], len(data)))
    if data[h["off_footer"]:h["off_footer"] + 8] != END:
        raise AwinError("footer magic")
    h["total_crc32"] = _u32(data, h["off_footer"] + 8)
    if crc32(data[:h["off_footer"]]) != h["total_crc32"]:
        raise AwinError("total CRC")

    anchors, off, total = [], 0, 0
    for i in range(h["windows_n"]):
        r = data[HEADER_SIZE + i * RECORD_SIZE:HEADER_SIZE + (i + 1) * RECORD_SIZE]
        if any(r[k] for k in range(0x58, 0x7C)):
            raise AwinError("record %d reserved bytes" % i)
        if crc32(r[:0x7C]) != _u32(r, 0x7C):
            raise AwinError("record %d CRC" % i)
        a = {
            "index": _u32(r, 0x00), "kind": _u32(r, 0x04), "ordinal": _u32(r, 0x08),
            "flags": _u32(r, 0x0C), "event_n": _u32(r, 0x10), "word": _u32(r, 0x14),
            "keys": _u32(r, 0x18), "blocks": _u32(r, 0x1C),
            "t_poll": _u64(r, 0x20), "t_attempt": _u64(r, 0x28), "t_done": _u64(r, 0x30),
            "t_arm": _u64(r, 0x38), "first_cycle": _u64(r, 0x40), "last_cycle": _u64(r, 0x48),
            "skipped": _u32(r, 0x50), "off": _u32(r, 0x54),
        }
        if a["index"] != i:
            raise AwinError("record %d says it is %d" % (i, a["index"]))
        if a["flags"] & ~(F_CLOSED | F_INCOMPLETE | F_GAP):
            raise AwinError("record %d flags" % i)
        if (a["flags"] & F_CLOSED) and (a["flags"] & F_INCOMPLETE):
            raise AwinError("record %d is closed AND incomplete" % i)
        if a["blocks"] > h["blocks_per_window"]:
            raise AwinError("record %d block count" % i)
        if (a["flags"] & F_CLOSED) and a["blocks"] != h["blocks_per_window"]:
            raise AwinError("record %d closed with %d blocks" % (i, a["blocks"]))
        if a["off"] != off:
            raise AwinError("record %d offset" % i)
        if (i == 0) != (a["kind"] == 0):
            raise AwinError("the control is window 0 and nothing else is")
        off += a["blocks"] * BLOCK_SIZE
        total += a["blocks"]
        anchors.append(a)
    if total != h["blocks_stored"]:
        raise AwinError("block counts do not sum to blocks_stored")
    return h, anchors, h["off_blocks"]


def windows(data, header, anchors, blocks_off):
    """The stored blocks of each window, in drain order, as a list of lists of
    bytes objects — the shape tools/v8audio.py's question_AU expects."""
    out, off = [], blocks_off
    for a in anchors:
        w = [data[off + k * BLOCK_SIZE: off + (k + 1) * BLOCK_SIZE] for k in range(a["blocks"])]
        off += a["blocks"] * BLOCK_SIZE
        out.append(w)
    return out


def load(path):
    with open(path, "rb") as f:
        data = f.read()
    h, a, o = parse(data)
    return data, h, a, windows(data, h, a, o)


if __name__ == "__main__":
    import sys
    data, h, anchors, wins = load(sys.argv[1])
    print("OGBPAW1 v%d  %s / %s / %s  commit %s" % (h["version"], h["test_id"], h["app"], h["build_id"], h["commit"]))
    print("size %d  header_crc %08x  total_crc %08x  flags %04x" % (h["total_size"], h["header_crc32"], h["total_crc32"], h["flags"]))
    print("windows %d  blocks_per_window %d  stored %d  seen %d  ignored %d  failed %d"
          % (h["windows_n"], h["blocks_per_window"], h["blocks_stored"], h["blocks_seen"], h["blocks_ignored"], h["blocks_failed"]))
    print("arms %d  refused busy %d / full %d  closed %d  tb_hz %d  copy ticks %d/%d/%d over %d"
          % (h["arms"], h["arm_refused_busy"], h["arm_refused_full"], h["windows_closed"], h["tb_hz"],
             h["ticks_min"], h["ticks_sum"] // max(h["ticks_n"], 1), h["ticks_max"], h["ticks_n"]))
    for a in anchors:
        print("  w%d %-7s ord=%d flags=%04x blocks=%d skipped=%d n=%d word=%04x cyc %d..%d"
              % (a["index"], KIND.get(a["kind"], "?"), a["ordinal"], a["flags"], a["blocks"],
                 a["skipped"], a["event_n"], a["word"], a["first_cycle"], a["last_cycle"]))
