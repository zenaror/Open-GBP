#!/usr/bin/env python3
"""OGBPIDXCAP1 reader — the adapter between a physical witness sidecar and the
OGBPIDX1 analyzer core.

It is deliberately a SEPARATE module from `tools/vindex.py`. The analyzer core
decides what a sequence of frame IDs means; this file decides only whether a
file is a trustworthy record of what the hardware observed. Keeping them apart
is what lets the analyzer be tested against synthetic witnesses that never came
from a file, and lets the file format change without touching one line of the
classification logic.

WHAT IT REFUSES, AND WHY THAT IS THE POINT (HARDWARE_TESTS §V5.39.7)

A decisive source-continuity claim is only worth making about a capture that is
demonstrably complete. So a sidecar is `usable_for_decisive_claim` only when

    the file parses, every CRC matches, and no reserved byte is set
    the run stopped BECAUSE the witness target was reached
    the store never refused a commit
    the record count is exactly the declared target

Anything else — a safety-budget stop, a store-cap stop, a short file, a
truncated writer, one bad record — yields INCONCLUSIVE. Overflow is never a
normal end of this experiment (§V5.39.3), and a partial capture that happens to
look contiguous is not evidence that it was.

NOTHING HERE DECODES OGBPIDX1. The 54 words per block come out exactly as the
wire carried them, bit 15 included; SYNC, FRAME_ID, BLOCK_INDEX, STATUS and the
CRC-8 are the analyzer's business, offline.
"""
from __future__ import annotations

import binascii
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MAGIC = b"OGBPIDXC"
END = b"OGBPEND1"
VERSION = 1
HEADER_SIZE = 0x180
FOOTER_SIZE = 12
META_SIZE = 0x30
WITNESS_WORDS = 54
WITNESS_BLOCKS = 40
WITNESS_STRIP_X0 = 1                                        # STRIP-L starts at x = 1
WITNESS_STRIP_ROW = 0                                       # local row 0 of the block
WITNESS_BYTES = WITNESS_WORDS * WITNESS_BLOCKS * 2          # 4320
RECORD_SIZE = META_SIZE + WITNESS_BYTES                      # 4368
ID_FIELD = 32

FLAG_STORE_FULL = 0x0001
FLAG_TARGET_REACHED = 0x0002
FLAG_TRUNCATED = 0x0004
FLAG_SERVICE_OK = 0x0008
FLAG_STOP_IS_TARGET = 0x0010
FLAG_ALL = 0x001F

FLAG_NAMES = [
    (FLAG_STORE_FULL, "store_full"),
    (FLAG_TARGET_REACHED, "target_reached"),
    (FLAG_TRUNCATED, "truncated"),
    (FLAG_SERVICE_OK, "service_ok"),
    (FLAG_STOP_IS_TARGET, "stop_is_target"),
]


class SidecarError(Exception):
    """The file is not a trustworthy OGBPIDXCAP1 record."""


def stop_reasons(header_path=None):
    """The probe's stop enum, READ FROM THE HEADER rather than copied into this
    file. A tool that hard-codes a runtime enum drifts from it silently the
    first time someone inserts a value; this one cannot."""
    path = header_path or os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.h")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"enum\s+gbp_vstate_stop\s*\{(.*?)\}", text, re.S)
    if not m:
        m = re.search(r"\bGBP_VSTATE_STOP_NONE\s*=\s*0,(.*?)\}", text, re.S)
        body = "GBP_VSTATE_STOP_NONE = 0," + m.group(1) if m else ""
    else:
        body = m.group(1)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    out, nxt = {}, 0
    for item in body.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            name, val = item.split("=", 1)
            nxt = int(val.strip(), 0)
            name = name.strip()
        else:
            name = item
        if not re.fullmatch(r"GBP_VSTATE_STOP_\w+", name):
            continue
        out[name] = nxt
        nxt += 1
    return out


def _id(buf):
    if buf[-1] != 0:
        raise SidecarError("identity field is not terminated")
    s = buf.split(b"\x00", 1)[0]
    if b"\x00" in buf[len(s) + 1:].rstrip(b"\x00"):
        raise SidecarError("identity field has a byte after the terminator")
    return s.decode("ascii", "replace")


def parse(data: bytes) -> dict:
    """Strict parse. Raises SidecarError with a specific reason, never a
    generic 'bad file' — an operator has to know which thing went wrong."""
    if len(data) < HEADER_SIZE + FOOTER_SIZE:
        raise SidecarError("shorter than a header plus a footer")
    if data[:8] != MAGIC:
        raise SidecarError("magic is not %r" % MAGIC)

    h = data[:HEADER_SIZE]
    version, header_size = struct.unpack_from(">HH", h, 0x08)
    if version != VERSION:
        raise SidecarError("unsupported version %d" % version)
    if header_size != HEADER_SIZE:
        raise SidecarError("header size %d is not 0x%X" % (header_size, HEADER_SIZE))

    header_crc = struct.unpack_from(">I", h, HEADER_SIZE - 4)[0]
    if header_crc != binascii.crc32(h[:HEADER_SIZE - 4]) & 0xFFFFFFFF:
        raise SidecarError("header CRC-32 mismatch")

    info = {
        "version": version,
        "header_size": header_size,
        "flags": struct.unpack_from(">I", h, 0x0C)[0],
        "record_size": struct.unpack_from(">I", h, 0x10)[0],
        "records_cap": struct.unpack_from(">I", h, 0x14)[0],
        "records_n": struct.unpack_from(">I", h, 0x18)[0],
        "witness_words": struct.unpack_from(">I", h, 0x1C)[0],
        "witness_blocks": struct.unpack_from(">I", h, 0x20)[0],
        "strip_x0": struct.unpack_from(">I", h, 0x24)[0],
        "strip_row": struct.unpack_from(">I", h, 0x28)[0],
        "block_bytes": struct.unpack_from(">I", h, 0x2C)[0],
        "line_stride": struct.unpack_from(">I", h, 0x30)[0],
        "target_frames": struct.unpack_from(">I", h, 0x34)[0],
        "stop_reason": struct.unpack_from(">H", h, 0x38)[0],
        "status_code": struct.unpack_from(">H", h, 0x3A)[0],
        "tb_hz": struct.unpack_from(">I", h, 0x3C)[0],
        "frames_seen": struct.unpack_from(">I", h, 0x40)[0],
        "frames_discarded": struct.unpack_from(">I", h, 0x44)[0],
        "blocks_staged": struct.unpack_from(">I", h, 0x48)[0],
        "blocks_placed": struct.unpack_from(">I", h, 0x4C)[0],
        "blocks_out_of_range": struct.unpack_from(">I", h, 0x50)[0],
        "copy_ticks_min": struct.unpack_from(">I", h, 0x54)[0],
        "copy_ticks_max": struct.unpack_from(">I", h, 0x58)[0],
        "copy_ticks_n": struct.unpack_from(">I", h, 0x5C)[0],
        "copy_ticks_sum": struct.unpack_from(">Q", h, 0x60)[0],
        "t_first_record": struct.unpack_from(">Q", h, 0x68)[0],
        "t_last_record": struct.unpack_from(">Q", h, 0x70)[0],
        "off_records": struct.unpack_from(">I", h, 0x78)[0],
        "off_footer": struct.unpack_from(">I", h, 0x7C)[0],
        "total_size": struct.unpack_from(">Q", h, 0x80)[0],
        "header_crc32": header_crc,
    }
    info["test_id"] = _id(h[0x88:0x88 + ID_FIELD])
    info["build_id"] = _id(h[0xA8:0xA8 + ID_FIELD])
    info["app"] = _id(h[0xC8:0xC8 + ID_FIELD])
    info["commit"] = _id(h[0xE8:0xE8 + ID_FIELD])

    if info["flags"] & ~FLAG_ALL:
        raise SidecarError("unknown flag bits set: 0x%04x" % info["flags"])
    if any(h[0x108:HEADER_SIZE - 4]):
        raise SidecarError("reserved header bytes are not zero")
    if info["record_size"] != RECORD_SIZE:
        raise SidecarError("record size %d is not %d" % (info["record_size"], RECORD_SIZE))
    if info["witness_words"] != WITNESS_WORDS or info["witness_blocks"] != WITNESS_BLOCKS:
        raise SidecarError("witness geometry is not the frozen 54 x 40")
    if info["off_records"] != HEADER_SIZE:
        raise SidecarError("records do not start at the header size")
    if info["records_n"] > info["records_cap"]:
        raise SidecarError("more records than the declared capacity")
    if info["target_frames"] > info["records_cap"]:
        raise SidecarError("the target exceeds the capacity")
    body = info["records_n"] * RECORD_SIZE
    if info["off_footer"] != HEADER_SIZE + body:
        raise SidecarError("the footer offset does not match the record count")
    if info["total_size"] != info["off_footer"] + FOOTER_SIZE:
        raise SidecarError("the declared total size is inconsistent")
    if len(data) != info["total_size"]:
        raise SidecarError("the file is %d bytes, the header declares %d"
                           % (len(data), info["total_size"]))

    if data[info["off_footer"]:info["off_footer"] + 8] != END:
        raise SidecarError("footer magic is missing")
    info["total_crc32"] = struct.unpack_from(">I", data, info["off_footer"] + 8)[0]
    if info["total_crc32"] != binascii.crc32(data[:info["off_footer"]]) & 0xFFFFFFFF:
        raise SidecarError("whole-file CRC-32 mismatch")

    if (info["flags"] & FLAG_TARGET_REACHED) and info["records_n"] < info["target_frames"]:
        raise SidecarError("target_reached is declared with fewer records than the target")

    records = []
    for i in range(info["records_n"]):
        off = info["off_records"] + i * RECORD_SIZE
        rec = data[off:off + RECORD_SIZE]
        frame_index, blocks, flags, completeness, disagreements, captured = \
            struct.unpack_from(">IHHHHI", rec, 0)
        t_first, t_last, present = struct.unpack_from(">QQQ", rec, 0x10)
        rec_crc = struct.unpack_from(">I", rec, 0x28)[0]
        if struct.unpack_from(">I", rec, 0x2C)[0] != 0:
            raise SidecarError("record %d: reserved word is not zero" % i)
        want = binascii.crc32(rec[:0x28])
        want = binascii.crc32(rec[META_SIZE:], want) & 0xFFFFFFFF
        if want != rec_crc:
            raise SidecarError("record %d: CRC-32 mismatch" % i)
        if present >> WITNESS_BLOCKS:
            raise SidecarError("record %d: a presence bit past block 39" % i)
        if bin(present).count("1") != captured:
            raise SidecarError("record %d: blocks_captured disagrees with the bitmap" % i)
        words = struct.unpack_from(">%dH" % (WITNESS_WORDS * WITNESS_BLOCKS), rec, META_SIZE)
        records.append({
            "frame_index": frame_index,
            "blocks": blocks,
            "flags": flags,
            "completeness": completeness,
            "disagreements": disagreements,
            "blocks_captured": captured,
            "present": present,
            "t_first_block": t_first,
            "t_last_block": t_last,
            "witness": [list(words[b * WITNESS_WORDS:(b + 1) * WITNESS_WORDS])
                        for b in range(WITNESS_BLOCKS)],
        })
    info["records"] = records
    return info


def load(path: str) -> dict:
    with open(path, "rb") as f:
        return parse(f.read())


def usability(info: dict, stops=None) -> dict:
    """Whether this capture may support a DECISIVE source-continuity claim.

    Separated from `parse` on purpose: a file can be perfectly well formed and
    still be the wrong kind of evidence. Both answers are reported."""
    stops = stops or stop_reasons()
    want = stops.get("GBP_VSTATE_STOP_WITNESS_TARGET")
    reasons = []
    if info["flags"] & FLAG_STORE_FULL:
        reasons.append("the witness store refused a commit (store_full)")
    if info["flags"] & FLAG_TRUNCATED:
        reasons.append("the writer did not finish (truncated)")
    if want is None:
        reasons.append("the probe's stop enum could not be read")
    elif info["stop_reason"] != want:
        reasons.append("the run did not stop on the witness target (stop_reason=%d)"
                       % info["stop_reason"])
    if not (info["flags"] & FLAG_TARGET_REACHED):
        reasons.append("the target was never reached")
    if info["records_n"] != info["target_frames"]:
        reasons.append("records_n %d is not the target %d"
                       % (info["records_n"], info["target_frames"]))
    if info["blocks_out_of_range"]:
        reasons.append("%d blocks landed outside the 40-block geometry"
                       % info["blocks_out_of_range"])
    return {"usable_for_decisive_claim": not reasons, "reasons": reasons}


def complete_frames(info: dict):
    """The witness sets of frames whose 40 blocks were all captured, in capture
    order, with their records. A frame missing a block cannot be classified by
    the analyzer core, which requires 40 — it is reported, never padded."""
    full = (1 << WITNESS_BLOCKS) - 1
    return [r for r in info["records"] if r["present"] == full]


def flag_names(flags: int):
    return [n for bit, n in FLAG_NAMES if flags & bit]


def format_info(info: dict, stops=None) -> str:
    u = usability(info, stops)
    stops = stops or stop_reasons()
    rev = {v: k for k, v in stops.items()}
    full = complete_frames(info)
    L = ["OGBPIDXCAP1 sidecar",
         "  identity             %s / %s / %s / %s"
         % (info["test_id"], info["build_id"], info["app"], info["commit"]),
         "  records              %d of %d (target %d)"
         % (info["records_n"], info["records_cap"], info["target_frames"]),
         "  frames seen/discarded %d / %d" % (info["frames_seen"], info["frames_discarded"]),
         "  blocks staged/placed  %d / %d  (out of range %d)"
         % (info["blocks_staged"], info["blocks_placed"], info["blocks_out_of_range"]),
         "  all-40-block frames  %d" % len(full),
         "  stop                 %s (%d)"
         % (rev.get(info["stop_reason"], "?"), info["stop_reason"]),
         "  flags                %s" % (", ".join(flag_names(info["flags"])) or "-"),
         "  witness copy ticks   min %d max %d mean %d over %d (tb_hz %d)"
         % (info["copy_ticks_min"], info["copy_ticks_max"],
            info["copy_ticks_sum"] // info["copy_ticks_n"] if info["copy_ticks_n"] else 0,
            info["copy_ticks_n"], info["tb_hz"]),
         "  header/total CRC-32  %08x / %08x" % (info["header_crc32"], info["total_crc32"]),
         "  decisive-claim ready %s" % u["usable_for_decisive_claim"]]
    for r in u["reasons"]:
        L.append("      REFUSED: %s" % r)
    return "\n".join(L)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    try:
        print(format_info(load(sys.argv[1])))
    except SidecarError as e:
        print("SIDECAR REJECTED: %s" % e)
        sys.exit(1)
