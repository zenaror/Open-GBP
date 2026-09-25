#!/usr/bin/env python3
"""
tools/awrparse.py — a strict reader for the OGBPAWR1 ride-along capture
(src/gbp/gbp_awr.h), written for GBP-AUDIO-012 (HARDWARE_TESTS §V27; GitHub
Issue #117).

IT IS A PARSER, NOT A CONSTRUCTION. It turns one file into a header and a list
of whole 4 096-byte blocks, and it refuses a file that does not satisfy the
contract rather than reading it optimistically:

  * the magic, the version and the block size;
  * the header CRC-32 over the first 0x7C bytes, and its reserved bytes;
  * the state, the counts and the instants against each other;
  * blocks_stored x 4096 == the bytes between the header and the footer;
  * the footer magic and the CRC-32 over EVERYTHING before the footer.

Its CRC is the runtime's own (`src/gbp/gbp_crc32.c`): the reflected 0xEDB88320
polynomial, initialised and finalised with 0xFFFFFFFF — zlib's CRC-32.

The blocks come back as a list of 4 096-byte `bytes` objects, the shape
tools/u012slices.py's `decode()` takes. Standard library only. THE FILE IS
OPENED READ-ONLY AND NEVER REWRITTEN.
"""
import struct
import zlib

MAGIC = b"OGBPAWR1"
END = b"OGBPAWRE"
VERSION = 1
HEADER_SIZE = 0x80
FOOTER_SIZE = 12
BLOCK_SIZE = 0x1000
CRC_OFFSET = HEADER_SIZE - 4
RESERVED = (0x64, 0x7C)

STATE = {0: "idle", 1: "armed", 2: "filling", 3: "done"}

# the header, field by field: (name, offset, format)
FIELDS = (
    ("version", 0x08, ">I"), ("block_size", 0x0C, ">I"),
    ("blocks_stored", 0x10, ">I"), ("blocks_cap", 0x14, ">I"),
    ("tb_hz", 0x18, ">I"), ("state", 0x1C, ">I"),
    ("t_arm", 0x20, ">Q"), ("t_first", 0x28, ">Q"), ("t_last", 0x30, ">Q"),
    ("copy_min", 0x38, ">I"), ("copy_max", 0x3C, ">I"), ("copy_sum", 0x40, ">Q"),
    ("copy_n", 0x48, ">I"), ("faults", 0x4C, ">I"), ("ignored", 0x50, ">I"),
    ("seen", 0x54, ">I"), ("seq_first", 0x58, ">I"), ("seq_last", 0x5C, ">I"),
    ("arm_refused", 0x60, ">I"),
    ("header_crc32", CRC_OFFSET, ">I"),
)


def crc32(b):
    """The runtime's gbp_crc32: zlib's CRC-32, bit for bit."""
    return zlib.crc32(b) & 0xFFFFFFFF


class AwrError(Exception):
    pass


def parse(data):
    """Returns (header, blocks): the header as a dict and the stored blocks as a
    list of 4 096-byte bytes objects, in the order stored. Raises AwrError on
    anything the contract does not allow; it never reads optimistically."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise AwrError("not bytes")
    data = bytes(data)
    if len(data) < HEADER_SIZE + FOOTER_SIZE:
        raise AwrError("file is %d bytes, shorter than a header and a footer (%d)"
                       % (len(data), HEADER_SIZE + FOOTER_SIZE))
    if data[:8] != MAGIC:
        raise AwrError("magic is %r, not %r" % (data[:8], MAGIC))
    h = dict((name, struct.unpack_from(fmt, data, off)[0]) for name, off, fmt in FIELDS)
    if h["version"] != VERSION:
        raise AwrError("version %d, not %d" % (h["version"], VERSION))
    if h["block_size"] != BLOCK_SIZE:
        raise AwrError("block size %d, not %d" % (h["block_size"], BLOCK_SIZE))
    if crc32(data[:CRC_OFFSET]) != h["header_crc32"]:
        raise AwrError("header CRC: stored %08x, computed %08x" % (h["header_crc32"], crc32(data[:CRC_OFFSET])))
    if any(data[i] for i in range(*RESERVED)):
        raise AwrError("reserved header bytes 0x%02X..0x%02X are not zero" % (RESERVED[0], RESERVED[1] - 1))
    if h["state"] not in STATE:
        raise AwrError("state %d is not one of %s" % (h["state"], sorted(STATE)))
    h["state_name"] = STATE[h["state"]]
    if h["blocks_cap"] == 0:
        raise AwrError("blocks_cap is 0")
    if h["blocks_stored"] > h["blocks_cap"]:
        raise AwrError("blocks_stored %d exceeds blocks_cap %d" % (h["blocks_stored"], h["blocks_cap"]))
    if h["state"] == 0 and (h["blocks_stored"] or h["t_arm"]):
        raise AwrError("idle with blocks or an arm instant")
    if h["state"] == 1 and h["blocks_stored"]:
        raise AwrError("armed (never filling) with %d blocks" % h["blocks_stored"])
    if h["state"] == 2 and h["blocks_stored"] == 0:
        raise AwrError("filling with no block")
    if h["state"] == 2 and h["blocks_stored"] >= h["blocks_cap"]:
        raise AwrError("filling with a full store")
    if h["blocks_stored"] == 0 and (h["t_first"] or h["t_last"] or h["seq_first"] or h["seq_last"]):
        raise AwrError("no block stored but a first/last instant or sequence is set")
    if h["t_last"] < h["t_first"]:
        raise AwrError("t_last %d before t_first %d" % (h["t_last"], h["t_first"]))
    if h["blocks_stored"] + h["ignored"] + h["faults"] != h["seen"]:
        raise AwrError("stored %d + ignored %d + faults %d != seen %d"
                       % (h["blocks_stored"], h["ignored"], h["faults"], h["seen"]))
    if h["copy_n"] == 0:
        if h["copy_min"] or h["copy_max"] or h["copy_sum"]:
            raise AwrError("copy statistics with copy_n 0")
    else:
        if h["copy_min"] > h["copy_max"]:
            raise AwrError("copy_min %d above copy_max %d" % (h["copy_min"], h["copy_max"]))
        if not (h["copy_min"] * h["copy_n"] <= h["copy_sum"] <= h["copy_max"] * h["copy_n"]):
            raise AwrError("copy_sum %d outside [min, max] x n" % h["copy_sum"])
    body = len(data) - HEADER_SIZE - FOOTER_SIZE
    if body != h["blocks_stored"] * BLOCK_SIZE:
        raise AwrError("%d bytes between header and footer, but blocks_stored %d x %d = %d"
                       % (body, h["blocks_stored"], BLOCK_SIZE, h["blocks_stored"] * BLOCK_SIZE))
    off_footer = HEADER_SIZE + body
    if data[off_footer:off_footer + 8] != END:
        raise AwrError("footer magic is %r, not %r" % (data[off_footer:off_footer + 8], END))
    h["total_crc32"] = struct.unpack_from(">I", data, off_footer + 8)[0]
    if crc32(data[:off_footer]) != h["total_crc32"]:
        raise AwrError("total CRC: stored %08x, computed %08x" % (h["total_crc32"], crc32(data[:off_footer])))
    h["off_footer"] = off_footer
    h["total_size"] = len(data)
    blocks = [data[HEADER_SIZE + k * BLOCK_SIZE:HEADER_SIZE + (k + 1) * BLOCK_SIZE]
              for k in range(h["blocks_stored"])]
    return h, blocks


def load(path):
    """(header, blocks) of the file at `path`, read once and never written."""
    with open(path, "rb") as f:
        data = f.read()
    return parse(data)


def describe(h):
    mean = h["copy_sum"] // h["copy_n"] if h["copy_n"] else 0
    span = h["t_last"] - h["t_first"] if h["blocks_stored"] else 0
    lines = [
        "OGBPAWR1 v%d  state %s  blocks %d of %d  tb_hz %d  size %d"
        % (h["version"], h["state_name"], h["blocks_stored"], h["blocks_cap"], h["tb_hz"], h["total_size"]),
        "t_arm %d  t_first %d  t_last %d  span %d ticks  seq %d..%d"
        % (h["t_arm"], h["t_first"], h["t_last"], span, h["seq_first"], h["seq_last"]),
        "seen %d  ignored %d  faults %d  arm_refused %d"
        % (h["seen"], h["ignored"], h["faults"], h["arm_refused"]),
        "copy ticks %d/%d/%d over %d  header_crc %08x  total_crc %08x"
        % (h["copy_min"], mean, h["copy_max"], h["copy_n"], h["header_crc32"], h["total_crc32"]),
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        sys.stderr.write("usage: awrparse.py <capture.awr>\n")
        sys.exit(2)
    try:
        header, blocks = load(sys.argv[1])
    except AwrError as e:
        sys.stderr.write("REFUSED: %s\n" % e)
        sys.exit(1)
    print(describe(header))
