#!/usr/bin/env python3
"""
avseq — parse the sequence sidecar of GBP-VIDEO-001 (`<TestID>_<BuildID>-seq.bin`, written by
src/gbp/gbp_avseqdump.c) on the host: the cycle table, the VIDEO and AUDIO tables and the raw
blocks of one bounded capture, with the identity (test ID, build ID, app, commit — four 32-byte
fields, never truncated). The layout (magic `OGBPSEQ1`, format version 1, big-endian, fixed
offsets, 256-byte header) is documented in src/gbp/gbp_avseqdump.h.

This tool is also the ONLY content oracle of the experiment: the probe never compares a captured
block with anything on the console (its status comes from SERVICE, CAPTURE and RESTORE alone).
The comparison against the idle-screen frame both references embed happens here, offline, and
only when the private inputs are present under `input/extracted/`; without them the verdict is
`reference_content=unavailable`, which is never a failure of the run.

Usage:
    tools/avseq.py info       <seq.bin>                header, counts, matrix, CRC checks
    tools/avseq.py cycles     <seq.bin>                the cycle table, one line per delivery
    tools/avseq.py video      <seq.bin>                the VIDEO table with both frame-start predicates
    tools/avseq.py audio      <seq.bin>                the AUDIO table
    tools/avseq.py boundaries <seq.bin>                both boundary lists, intervals, complete-interval verdict
    tools/avseq.py extract    <seq.bin> <outdir>       the raw blocks as files (video-<seq>.bin, audio-<slot>.bin)
    tools/avseq.py frames     <seq.bin> [--phase N]    blocks grouped into frames under the references' reading
    tools/avseq.py oracle     <seq.bin> [--refdir DIR] the offline content comparison (see above)
    tools/avseq.py json       <seq.bin>                machine-readable header and tables (no raw bytes)
Exit status 0 when the file parses and every CRC matches; 1 otherwise.

Importable: parse(data) -> dict (raises ValueError with the same codes as the C parser).
Nothing here reproduces reference data: the private assets stay under input/ and are read only
at run time; only OUR measurements and the comparison verdict are printed or stored.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import zlib

MAGIC = b"OGBPSEQ1"
END = b"OGBPEND1"
VERSION = 1
HEADER_SIZE = 0x100
FOOTER_SIZE = 12
CYCLE_REC, VIDEO_REC, AUDIO_REC = 96, 48, 32
ID_FIELD, ID_MAX = 32, 31
OFF_TEST_ID, OFF_BUILD_ID, OFF_APP, OFF_COMMIT = 0x40, 0x60, 0x80, 0xA0
OFF_RESERVED, RESERVED_LEN, OFF_HEADER_CRC = 0xF0, 12, 0xFC
VIDEO_BLOCK_SIZE, AUDIO_BLOCK_SIZE = 0x0F00, 0x1000
MAX_VIDEO_BLOCKS, MAX_DELIVERIES, AUDIO_RAW_SLOTS = 88, 320, 10
FLAG_SERVICE_OK, FLAG_RESTORE_OK, FLAG_NEXT_CAUSE_AT_END, FLAG_PARTIAL, FLAG_STAGE_A_ABORTED = 1, 2, 4, 8, 16
RC_NAMES = {0: "ok", 1: "timeout", 2: "busy", 3: "param", 4: "backend"}
END_NAMES = {0: "none", 1: "target_reached", 2: "delivery_cap", 3: "runtime_cap", 4: "no_next_cause", 5: "early_failure"}
NEXT_NAMES = {0: "none", 1: "cause", 2: "t_next_cause", 3: "admission_deadline", 4: "single_read"}
SLOT_NONE, SLOT_LAST = 0xFF, 0x80
# the references' raster, from docs/research/VIDEO_PATH.md (GBP-VID-002/003): a VIDEO block carries
# four scanlines of 240 pixel words; both references consume bytes 1 and 3 of each 32-bit word
BLOCK_LINES, LINE_PIXELS, FRAME_BLOCKS_HYPOTHESIS = 4, 240, 40


def crc32(data):
    return zlib.crc32(data) & 0xFFFFFFFF


def _id_ok(s, may_be_empty):
    """The identity rule: 1..31 (or 0..31) characters, printable ASCII without spaces (0x21..0x7E)."""
    if len(s) > ID_MAX or (not s and not may_be_empty):
        return False
    return all(0x21 <= ord(c) <= 0x7E for c in s)


def _id(b, may_be_empty):
    """An identity field as read: a NUL inside the field, only zero bytes after it, only rule bytes before."""
    if b"\0" not in b:
        raise ValueError("-8: identity field without terminator")
    s, rest = b.split(b"\0", 1)
    if rest.strip(b"\0"):
        raise ValueError("-8: identity field padding is not zero")
    text = s.decode("ascii", "replace")
    if not _id_ok(text, may_be_empty):
        raise ValueError("-8: identity field breaks the rule: %r" % text)
    return text


def _u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def _u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


# ---- the frame-start predicates, from the raw first four bytes; neither is "the" truth ----
def flag_gbi(first4):
    """GBI FUN_8000BF30: bit 7 of byte 0 AND bit 7 of byte 1 of the first 32-bit word."""
    return 1 if (struct.unpack(">I", bytes(first4))[0] & 0x80800000) == 0x80800000 else 0


def flag_disc(first4):
    """Start-up Disc FUN_8008A588: bit 7 of byte 1 alone."""
    return 1 if ((struct.unpack(">H", bytes(first4[:2]))[0] >> 7) & 1) else 0


def parse(data):
    """Parses a sidecar. Raises ValueError with the same negative codes as gbp_avseqdump_parse."""
    if len(data) < HEADER_SIZE + FOOTER_SIZE or data[:8] != MAGIC:
        raise ValueError("-1: too short or bad magic")
    d = {"version": _u16(data, 0x08), "header_size": _u16(data, 0x0A)}
    if d["version"] != VERSION or d["header_size"] != HEADER_SIZE:
        raise ValueError("-2: unsupported version or header size")
    d["cycle_rec"], d["video_rec"], d["audio_rec"] = _u16(data, 0x2C), _u16(data, 0x2E), _u16(data, 0x30)
    if (d["cycle_rec"], d["video_rec"], d["audio_rec"]) != (CYCLE_REC, VIDEO_REC, AUDIO_REC):
        raise ValueError("-2: unsupported record size")
    d["header_crc32"] = _u32(data, OFF_HEADER_CRC)
    if crc32(data[:OFF_HEADER_CRC]) != d["header_crc32"]:
        raise ValueError("-3: header CRC mismatch")
    if data[OFF_RESERVED:OFF_RESERVED + RESERVED_LEN].strip(b"\0"):
        raise ValueError("-9: reserved bytes are not zero")
    flags = _u32(data, 0x0C)
    d["flags"] = flags
    d["service_ok"] = bool(flags & FLAG_SERVICE_OK)
    d["restore_ok"] = bool(flags & FLAG_RESTORE_OK)
    d["next_cause_at_end"] = bool(flags & FLAG_NEXT_CAUSE_AT_END)
    d["partial"] = bool(flags & FLAG_PARTIAL)
    d["stage_a_aborted"] = bool(flags & FLAG_STAGE_A_ABORTED)
    d["tb_hz"] = _u32(data, 0x10)
    d["cycle_count"], d["video_count"] = _u32(data, 0x14), _u32(data, 0x18)
    d["audio_count"], d["audio_raw_count"] = _u32(data, 0x1C), _u32(data, 0x20)
    d["video_block_size"], d["audio_block_size"] = _u32(data, 0x24), _u32(data, 0x28)
    d["capture_result"] = _u16(data, 0x32)
    d["capture"] = END_NAMES.get(d["capture_result"], "?")
    d["status_code"], d["end_reason"] = _u16(data, 0x34), _u16(data, 0x36)
    d["off_cycles"], d["off_video_table"] = _u32(data, 0x38), _u32(data, 0x3C)
    d["test_id"] = _id(data[OFF_TEST_ID:OFF_TEST_ID + ID_FIELD], False)
    d["build_id"] = _id(data[OFF_BUILD_ID:OFF_BUILD_ID + ID_FIELD], False)
    d["app"] = _id(data[OFF_APP:OFF_APP + ID_FIELD], True)
    d["commit"] = _id(data[OFF_COMMIT:OFF_COMMIT + ID_FIELD], True)
    d["off_audio_table"], d["off_video_raw"] = _u32(data, 0xC0), _u32(data, 0xC4)
    d["off_audio_raw"], d["off_footer"] = _u32(data, 0xC8), _u32(data, 0xCC)
    d["target_video_blocks"], d["max_deliveries"] = _u32(data, 0xD0), _u32(data, 0xD4)
    d["admission_budget_ticks"], d["t0"] = _u32(data, 0xD8), _u32(data, 0xDC)
    d["admission_deadline"], d["boundaries_gbi"] = _u32(data, 0xE0), _u32(data, 0xE4)
    d["boundaries_disc"], d["video_raw_stored"] = _u32(data, 0xE8), _u32(data, 0xEC)
    if (d["cycle_count"] > MAX_DELIVERIES or d["video_count"] > MAX_VIDEO_BLOCKS or
            d["audio_count"] > MAX_DELIVERIES or d["audio_raw_count"] > AUDIO_RAW_SLOTS or
            d["video_raw_stored"] > d["video_count"]):
        raise ValueError("-4: a count is beyond the design bound")
    if d["video_block_size"] != VIDEO_BLOCK_SIZE or d["audio_block_size"] != AUDIO_BLOCK_SIZE:
        raise ValueError("-2: unexpected block size")
    end_cycles = d["off_cycles"] + d["cycle_count"] * CYCLE_REC
    end_video = d["off_video_table"] + d["video_count"] * VIDEO_REC
    end_audio = d["off_audio_table"] + d["audio_count"] * AUDIO_REC
    end_vraw = d["off_video_raw"] + d["video_raw_stored"] * VIDEO_BLOCK_SIZE
    end_araw = d["off_audio_raw"] + d["audio_raw_count"] * AUDIO_BLOCK_SIZE
    if (d["off_cycles"] != HEADER_SIZE or end_cycles != d["off_video_table"] or end_video != d["off_audio_table"] or
            end_audio != d["off_video_raw"] or end_vraw != d["off_audio_raw"] or end_araw != d["off_footer"]):
        raise ValueError("-4: the tables are not contiguous")
    if d["off_footer"] + FOOTER_SIZE > len(data):
        raise ValueError("-4: the footer falls outside the file")
    if data[d["off_footer"]:d["off_footer"] + 8] != END:
        raise ValueError("-5: footer magic missing")
    d["total_crc32"] = _u32(data, d["off_footer"] + 8)
    if crc32(data[:d["off_footer"]]) != d["total_crc32"]:
        raise ValueError("-6: total CRC mismatch")
    d["cycles"] = [_cycle(data, d["off_cycles"] + i * CYCLE_REC) for i in range(d["cycle_count"])]
    d["video"] = [_vblock(data, d["off_video_table"] + i * VIDEO_REC) for i in range(d["video_count"])]
    d["audio"] = [_ablock(data, d["off_audio_table"] + i * AUDIO_REC) for i in range(d["audio_count"])]
    for v in d["video"]:
        if not v["completed"]:
            if v["raw_len"]:
                raise ValueError("-4: an incomplete VIDEO record carries a raw length")
            continue
        if (v["raw_len"] != VIDEO_BLOCK_SIZE or v["raw_off"] < d["off_video_raw"] or v["raw_off"] + v["raw_len"] > end_vraw or
                (v["raw_off"] - d["off_video_raw"]) % VIDEO_BLOCK_SIZE):
            raise ValueError("-4: a VIDEO raw offset falls outside the raw section")
        if v["summarized"] and crc32(data[v["raw_off"]:v["raw_off"] + v["raw_len"]]) != v["crc32"]:
            raise ValueError("-7: a VIDEO block's CRC does not match its bytes")
    for a in d["audio"]:
        if a["raw_index"] == 0xFFFF:
            continue
        if a["raw_index"] >= d["audio_raw_count"]:
            raise ValueError("-4: an AUDIO raw index is beyond the stored blocks")
        o = d["off_audio_raw"] + a["raw_index"] * AUDIO_BLOCK_SIZE
        if a["summarized"] and crc32(data[o:o + AUDIO_BLOCK_SIZE]) != a["crc32"]:
            raise ValueError("-7: an AUDIO block's CRC does not match its bytes")
    d["_data"] = data
    return d


def _slot_name(slot):
    if slot == SLOT_NONE:
        return "-"
    if slot & SLOT_LAST:
        return "last%d" % (slot & 1)
    return str(slot)


def _cycle(b, o):
    f1, f2 = b[o + 6], b[o + 7]
    return {
        "idx": _u16(b, o + 0), "pending": _u16(b, o + 2), "irq_byte0": b[o + 4], "irq_off2_g0": b[o + 5],
        "verify": bool(f1 & 1), "audio_selected": bool(f1 & 2), "audio_attempted": bool(f1 & 4),
        "audio_completed": bool(f1 & 8), "video_selected": bool(f1 & 16), "video_attempted": bool(f1 & 32),
        "video_completed": bool(f1 & 64), "next_observed": bool(f1 & 128),
        "ack_attempted": bool(f2 & 1), "ack_completed": bool(f2 & 2), "rearm_attempted": bool(f2 & 4),
        "rearm_completed": bool(f2 & 8), "main_w1c": bool(f2 & 16), "pi_sticky": bool(f2 & 32),
        "relatch_postack": bool(f2 & 64), "admitted": bool(f2 & 128),
        "audio_rc": RC_NAMES.get(b[o + 8], "?"), "video_rc": RC_NAMES.get(b[o + 9], "?"),
        "audio_slot": _slot_name(b[o + 10]), "end_reason": END_NAMES.get(b[o + 11], "?"),
        "video_seq": _u16(b, o + 12), "ack_value": _u16(b, o + 14),
        "isr_fired": b[o + 16], "isr_count": b[o + 17], "isr_reentry": b[o + 18],
        "next_ended_by": NEXT_NAMES.get(b[o + 19], "?"),
        "t_cause": _u32(b, o + 0x14), "t_unmask": _u32(b, o + 0x18), "t_entry": _u32(b, o + 0x1C),
        "latency": _u32(b, o + 0x20), "t_read": _u32(b, o + 0x24),
        "t_audio_start": _u32(b, o + 0x28), "t_audio_end": _u32(b, o + 0x2C),
        "t_video_start": _u32(b, o + 0x30), "t_video_end": _u32(b, o + 0x34),
        "t_ack_after": _u32(b, o + 0x38), "t_rearm": _u32(b, o + 0x3C), "t_rearm_after": _u32(b, o + 0x40),
        "t_next": _u32(b, o + 0x44), "intsr_entry": _u32(b, o + 0x48), "intmr_entry": _u32(b, o + 0x4C),
        "intsr_after_w1c": _u32(b, o + 0x50), "intsr_postack": _u32(b, o + 0x54), "intsr_next": _u32(b, o + 0x58),
        "audio_crc32": _u32(b, o + 0x5C),
    }


def _vblock(b, o):
    f = b[o + 7]
    first4 = list(b[o + 8:o + 12])
    return {
        "seq": _u16(b, o + 0), "cycle": _u16(b, o + 2), "pending": _u16(b, o + 4),
        "rc": RC_NAMES.get(b[o + 6], "?"), "completed": bool(f & 1),
        "flag_gbi": 1 if (f & 2) else 0, "flag_disc": 1 if (f & 4) else 0, "flags_agree": bool(f & 8),
        "summarized": bool(f & 16), "raw_first4": first4,
        "t_start": _u32(b, o + 0x0C), "t_end": _u32(b, o + 0x10), "wait_ticks": _u32(b, o + 0x14),
        "crc32": _u32(b, o + 0x18), "raw_off": _u32(b, o + 0x1C), "raw_len": _u32(b, o + 0x20),
        "byte0_exceptions": _u16(b, o + 0x24), "undoubled_words": _u16(b, o + 0x26),
        "polls": _u16(b, o + 0x28), "csr_before": _u16(b, o + 0x2A), "csr_after": _u16(b, o + 0x2C),
    }


def _ablock(b, o):
    f = b[o + 2]
    return {
        "cycle": _u16(b, o + 0), "selected": bool(f & 1), "attempted": bool(f & 2), "completed": bool(f & 4),
        "raw_kept": bool(f & 8), "summarized": bool(f & 16), "rc": RC_NAMES.get(b[o + 3], "?"),
        "slot": _slot_name(b[o + 4]), "raw_index": _u16(b, o + 6),
        "t_start": _u32(b, o + 8), "t_end": _u32(b, o + 0x0C), "wait_ticks": _u32(b, o + 0x10),
        "crc32": _u32(b, o + 0x14), "first_word": _u32(b, o + 0x18),
        "nonzero": _u16(b, o + 0x1C), "unit0_nonzero": _u16(b, o + 0x1E),
    }


def video_bytes(d, seq):
    """The raw bytes of the VIDEO block with sequence index `seq`, or None when it did not complete."""
    for v in d["video"]:
        if v["seq"] == seq and v["completed"] and v["raw_len"]:
            return d["_data"][v["raw_off"]:v["raw_off"] + v["raw_len"]]
    return None


def audio_bytes(d, raw_index):
    if raw_index >= d["audio_raw_count"]:
        return None
    o = d["off_audio_raw"] + raw_index * AUDIO_BLOCK_SIZE
    return d["_data"][o:o + AUDIO_BLOCK_SIZE]


def boundaries(d, predicate):
    """Positions (sequence indices) and intervals of the blocks where `predicate` ("gbi" / "disc")
    is true, over the COMPLETED blocks in sequence order. A complete frame interval exists iff two
    consecutive true predicates were captured (count >= 2); the interval length is the observation,
    never a requirement — the references' 40 is a hypothesis."""
    key = "flag_%s" % predicate
    pos = [v["seq"] for v in d["video"] if v["completed"] and v[key]]
    iv = [pos[i + 1] - pos[i] for i in range(len(pos) - 1)]
    return {"predicate": predicate, "count": len(pos), "positions": pos, "intervals": iv,
            "complete_interval": len(pos) >= 2}


# ---- the reference transform and checksum, applied to OUR bytes only ----
def transform_block(raw, force_bit15=True):
    """Both references consume bytes 1 and 3 of each 32-bit pixel word and assemble a 16-bit value
    (docs/research/VIDEO_PATH.md §2.2/§3.2): pixel = byte 1 : byte 3. Returns the block's 960
    halfwords; `force_bit15` reproduces the RGB5A3 opaque bit both presenters set. This transforms
    OUR captured bytes; it reproduces no reference data."""
    out = []
    for k in range(0, len(raw) - 3, 4):
        v = (raw[k + 1] << 8) | raw[k + 3]
        out.append((v | 0x8000) if force_bit15 else v)
    return out


def gbi_block_checksum(raw):
    """GBI's per-block checksum (`FUN_8000BF30`): 240 iterations repack four source words into two
    32-bit words (byte 1 : byte 3 of each) and accumulate them in 64 bits; the stored entry is the
    low 32 bits plus the carry count. Verified against the physical GBP-AV-SERVICE-001 block, whose
    checksum is 0x7F0FFF10 — entry 0 of both reference tables (VIDEO_PATH.md §6)."""
    total = 0
    for it in range(LINE_PIXELS):
        o = it * 16
        w0, w1, w2, w3 = raw[o:o + 4], raw[o + 4:o + 8], raw[o + 8:o + 12], raw[o + 12:o + 16]
        d0 = (w0[1] << 24) | (w0[3] << 16) | (w1[1] << 8) | w1[3]
        d1 = (w2[1] << 24) | (w2[3] << 16) | (w3[1] << 8) | w3[3]
        total += d0 + d1
    return ((total & 0xFFFFFFFF) + (total >> 32)) & 0xFFFFFFFF


def _dol_read(path, vaddr, length):
    """`length` bytes at the virtual address `vaddr` of a GameCube DOL, or None when no section
    covers it. The file stays private: only the bytes needed for a comparison are read, never stored."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 0x100:
        return None
    offs = struct.unpack_from(">18I", data, 0x00)
    addrs = struct.unpack_from(">18I", data, 0x48)
    sizes = struct.unpack_from(">18I", data, 0x90)
    for o, a, n in zip(offs, addrs, sizes):
        if n and a <= vaddr and vaddr + length <= a + n:
            k = o + (vaddr - a)
            return data[k:k + length] if k + length <= len(data) else None
    return None


def _raw_image_read(path, base, vaddr, length):
    """`length` bytes at `vaddr` of a raw image linked at `base` (the unpacked GBI executable)."""
    with open(path, "rb") as f:
        data = f.read()
    k = vaddr - base
    if k < 0 or k + length > len(data):
        return None
    return data[k:k + length]


DISC_REF_VADDR, DISC_REF_BYTES, DISC_BLOCK_BYTES = 0x801B45A0, 0x12C00, 0x780
GBI_IMAGE_BASE, GBI_TABLE_A, GBI_TABLE_B, GBI_TABLE_ENTRIES = 0x80003100, 0x800B0E78, 0x800B0F18, 40


def _find_reference(refdir):
    """The private inputs, read only at run time and never stored in the repository. Returns a dict
    describing what is available; the assets themselves stay under input/."""
    if not refdir:
        refdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "input", "extracted")
    disc = os.path.join(refdir, "gbp-disc", "sys", "main.dol")
    gbi = os.path.join(refdir, "gbi", "gbi-unpacked.bin")
    return {"refdir": refdir, "disc_main_dol": disc if os.path.isfile(disc) else None,
            "gbi_image": gbi if os.path.isfile(gbi) else None,
            "available": os.path.isfile(disc) or os.path.isfile(gbi)}


def oracle(d, refdir=None):
    """The offline content comparison — the ONLY place the capture meets the references' embedded
    data, and never a gate for SERVICE or CAPTURE. Without the private inputs the verdict is
    `insufficient_data` with `reference_content=unavailable`. Our measurements (per-block GBI
    checksums, match counts, the first mismatch) are ours to record; the references' assets are
    read at run time from input/ and never stored in this repository."""
    ref = _find_reference(refdir)
    out = {"reference_content": "unavailable", "verdict": "insufficient_data", "refdir": ref["refdir"],
           "disc_available": bool(ref["disc_main_dol"]), "gbi_available": bool(ref["gbi_image"]),
           "blocks_compared": 0, "matches_disc": 0, "matches_gbi": 0,
           "first_mismatch_block": None, "first_mismatch_offset": None}
    for p in ("gbi", "disc"):
        out["boundaries_" + p] = boundaries(d, p)
    blocks = [v for v in d["video"] if v["completed"]]
    # our own measurement, independent of the references: every completed block's GBI checksum
    out["checksums"] = [{"seq": v["seq"], "gbi_checksum": "%08x" % gbi_block_checksum(video_bytes(d, v["seq"]))}
                        for v in blocks]
    if not ref["available"]:
        out["note"] = ("the private reference inputs are absent: the content oracle is not computed. "
                       "The capture's own result (SERVICE / CAPTURE / RESTORE) is unaffected.")
        return out
    b = boundaries(d, "gbi")
    if not b["complete_interval"]:
        out["reference_content"] = "insufficient_data"
        out["note"] = ("the private inputs are present but the capture has no complete frame interval "
                       "under the GBI predicate: no alignment is assumed and no phase is applied silently. "
                       "Run `frames --phase N` to inspect an explicit alignment.")
        out["best_phase"] = None
        return out
    # align: the first boundary is frame position 0; blocks follow in sequence order
    first, period = b["positions"][0], (b["intervals"][0] if b["intervals"] else FRAME_BLOCKS_HYPOTHESIS)
    out["alignment"] = {"first_boundary_seq": first, "observed_period": period,
                        "reference_period_hypothesis": FRAME_BLOCKS_HYPOTHESIS}
    disc_hits = gbi_hits = compared = 0
    table_a = table_b = None
    if ref["gbi_image"]:
        ta = _raw_image_read(ref["gbi_image"], GBI_IMAGE_BASE, GBI_TABLE_A, GBI_TABLE_ENTRIES * 4)
        tb = _raw_image_read(ref["gbi_image"], GBI_IMAGE_BASE, GBI_TABLE_B, GBI_TABLE_ENTRIES * 4)
        table_a = list(struct.unpack(">%uI" % GBI_TABLE_ENTRIES, ta)) if ta else None
        table_b = list(struct.unpack(">%uI" % GBI_TABLE_ENTRIES, tb)) if tb else None
    for v in blocks:
        if v["seq"] < first:
            continue
        pos = (v["seq"] - first) % period
        if pos >= FRAME_BLOCKS_HYPOTHESIS:
            continue                                   # outside the references' 40-block frame
        raw = video_bytes(d, v["seq"])
        compared += 1
        if ref["disc_main_dol"]:
            expect = _dol_read(ref["disc_main_dol"], DISC_REF_VADDR + pos * DISC_BLOCK_BYTES, DISC_BLOCK_BYTES)
            if expect is not None:
                got = struct.pack(">%uH" % (DISC_BLOCK_BYTES // 2), *transform_block(raw))
                if got == expect:
                    disc_hits += 1
                elif out["first_mismatch_block"] is None:
                    out["first_mismatch_block"] = v["seq"]
                    out["first_mismatch_offset"] = next((i for i in range(len(expect)) if got[i] != expect[i]), None)
        if table_a is not None:
            c = gbi_block_checksum(raw)
            if c == table_a[pos] or (table_b is not None and c == table_b[pos]):
                gbi_hits += 1
    out["blocks_compared"] = compared
    out["matches_disc"] = disc_hits
    out["matches_gbi"] = gbi_hits
    best = max(disc_hits, gbi_hits)
    if compared == 0:
        out["reference_content"] = "insufficient_data"
        out["verdict"] = "insufficient_data"
    elif best == compared and compared >= FRAME_BLOCKS_HYPOTHESIS:
        out["reference_content"] = out["verdict"] = "full_match"
    elif best > 0:
        out["reference_content"] = out["verdict"] = "partial_match"
    else:
        out["reference_content"] = out["verdict"] = "mismatch"
    out["note"] = ("bytes that do not match the embedded idle screen are NEW EVIDENCE, not a failure: "
                   "the capture's own result is unaffected.")
    return out


def frames(d, phase=0):
    """Groups the captured blocks into frames of FRAME_BLOCKS_HYPOTHESIS blocks starting at `phase`.
    The grouping is the references' HYPOTHESIS, printed as such: the physical interval measured by
    boundaries() is the observation."""
    blocks = [v for v in d["video"] if v["completed"]]
    out = []
    for i in range(phase, len(blocks), FRAME_BLOCKS_HYPOTHESIS):
        group = blocks[i:i + FRAME_BLOCKS_HYPOTHESIS]
        out.append({"first_seq": group[0]["seq"], "blocks": len(group),
                    "complete": len(group) == FRAME_BLOCKS_HYPOTHESIS,
                    "starts_on_boundary_gbi": bool(group[0]["flag_gbi"]),
                    "starts_on_boundary_disc": bool(group[0]["flag_disc"])})
    return out


def info_text(d):
    lines = []
    lines.append("file      %s v%u header=0x%X footer=0x%X bytes=%u" %
                 (MAGIC.decode(), d["version"], d["header_size"], d["off_footer"], d["off_footer"] + FOOTER_SIZE))
    lines.append("identity  test=%s build=%s app=%s commit=%s" % (d["test_id"], d["build_id"], d["app"], d["commit"]))
    lines.append("capture   %s  cycles=%u video=%u (raw %u) audio=%u (raw %u) tb_hz=%u" %
                 (d["capture"], d["cycle_count"], d["video_count"], d["video_raw_stored"],
                  d["audio_count"], d["audio_raw_count"], d["tb_hz"]))
    lines.append("matrix    service=%s restore=%s next_cause_at_end=%s partial=%s stage_a_aborted=%s status_code=%u" %
                 (d["service_ok"], d["restore_ok"], d["next_cause_at_end"], d["partial"], d["stage_a_aborted"],
                  d["status_code"]))
    lines.append("admission t0=%u deadline=%u budget_ticks=%u target=%u max_deliveries=%u" %
                 (d["t0"], d["admission_deadline"], d["admission_budget_ticks"], d["target_video_blocks"],
                  d["max_deliveries"]))
    for p in ("gbi", "disc"):
        b = boundaries(d, p)
        lines.append("boundary  %-4s count=%u complete_interval=%s positions=%s intervals=%s" %
                     (p, b["count"], b["complete_interval"],
                      ",".join(str(x) for x in b["positions"]) or "-",
                      ",".join(str(x) for x in b["intervals"]) or "-"))
    lines.append("header    stored=%u in-file=%u   (the probe's own counts)" % (d["boundaries_gbi"], d["boundaries_disc"]))
    lines.append("crc       header=%08x total=%08x  (both verified)" % (d["header_crc32"], d["total_crc32"]))
    lines.append("content   reference_content=unavailable unless tools/avseq.py oracle finds the private inputs")
    return "\n".join(lines)


def cycles_text(d):
    out = ["idx pend ack  v a  vseq slot  isr    lat      t_read    ack_ok rearm w1c next            end"]
    for c in d["cycles"]:
        out.append("%3u %04x %04x %s %s %5s %-5s %u/%u/%u %-8u %-9u %s     %s     %u   %-15s %s" %
                   (c["idx"], c["pending"], c["ack_value"],
                    "V" if c["video_selected"] else "-", "A" if c["audio_selected"] else "-",
                    c["video_seq"] if c["video_selected"] else "-", c["audio_slot"],
                    c["isr_fired"], c["isr_count"], c["isr_reentry"], c["latency"], c["t_read"],
                    "ok" if c["ack_completed"] else "NO", "ok" if c["rearm_completed"] else "NO",
                    1 if c["main_w1c"] else 0, c["next_ended_by"], c["end_reason"]))
    return "\n".join(out)


def video_text(d):
    out = ["seq cyc pend rc     first4      gbi disc agree x0   und   crc32    dt       wait"]
    for v in d["video"]:
        out.append("%3u %3u %04x %-6s %02x%02x%02x%02x   %u   %u    %u     %-4u %-5u %08x %-8u %u" %
                   (v["seq"], v["cycle"], v["pending"], v["rc"], v["raw_first4"][0], v["raw_first4"][1],
                    v["raw_first4"][2], v["raw_first4"][3], v["flag_gbi"], v["flag_disc"],
                    1 if v["flags_agree"] else 0, v["byte0_exceptions"], v["undoubled_words"], v["crc32"],
                    (v["t_end"] - v["t_start"]) & 0xFFFFFFFF, v["wait_ticks"]))
    return "\n".join(out)


def audio_text(d):
    out = ["cyc sel att comp rc     slot  raw   crc32    first_word nonzero unit0 dt"]
    for a in d["audio"]:
        out.append("%3u  %u   %u   %u   %-6s %-5s %-5s %08x %08x   %-7u %-5u %u" %
                   (a["cycle"], a["selected"], a["attempted"], a["completed"], a["rc"], a["slot"],
                    a["raw_index"] if a["raw_index"] != 0xFFFF else "-", a["crc32"], a["first_word"],
                    a["nonzero"], a["unit0_nonzero"], (a["t_end"] - a["t_start"]) & 0xFFFFFFFF))
    return "\n".join(out)


def boundaries_text(d):
    out = []
    for p in ("gbi", "disc"):
        b = boundaries(d, p)
        out.append("predicate %s" % p)
        out.append("  count             %u" % b["count"])
        out.append("  positions         %s" % (",".join(str(x) for x in b["positions"]) or "-"))
        out.append("  intervals         %s" % (",".join(str(x) for x in b["intervals"]) or "-"))
        out.append("  complete_interval %s" % ("yes" if b["complete_interval"] else "no"))
        if b["intervals"]:
            uniq = sorted(set(b["intervals"]))
            out.append("  observed interval %s  (the references' 40 is a HYPOTHESIS, not a requirement)" %
                       (",".join(str(x) for x in uniq)))
    return "\n".join(out)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, path = argv[0], argv[1]
    with open(path, "rb") as f:
        data = f.read()
    try:
        d = parse(data)
    except ValueError as e:
        print("avseq: %s" % e, file=sys.stderr)
        return 1
    if cmd == "info":
        print(info_text(d))
    elif cmd == "cycles":
        print(cycles_text(d))
    elif cmd == "video":
        print(video_text(d))
    elif cmd == "audio":
        print(audio_text(d))
    elif cmd == "boundaries":
        print(boundaries_text(d))
    elif cmd == "frames":
        phase = 0
        if "--phase" in argv:
            phase = int(argv[argv.index("--phase") + 1])
        for fr in frames(d, phase):
            print("frame first_seq=%u blocks=%u complete=%s boundary_gbi=%s boundary_disc=%s" %
                  (fr["first_seq"], fr["blocks"], fr["complete"], fr["starts_on_boundary_gbi"],
                   fr["starts_on_boundary_disc"]))
        print("# the grouping of %u blocks per frame is the references' HYPOTHESIS; "
              "the measured intervals are in `boundaries`" % FRAME_BLOCKS_HYPOTHESIS)
    elif cmd == "oracle":
        refdir = argv[argv.index("--refdir") + 1] if "--refdir" in argv else None
        o = oracle(d, refdir)
        print(json.dumps({k: v for k, v in o.items() if not k.startswith("_")}, indent=1))
    elif cmd == "json":
        print(json.dumps({k: v for k, v in d.items() if not k.startswith("_")}, indent=1))
    elif cmd == "extract":
        if len(argv) < 3:
            print("extract needs an output directory", file=sys.stderr)
            return 2
        outdir = argv[2]
        os.makedirs(outdir, exist_ok=True)
        n = 0
        for v in d["video"]:
            b = video_bytes(d, v["seq"])
            if b is None:
                continue
            with open(os.path.join(outdir, "video-%03u.bin" % v["seq"]), "wb") as f:
                f.write(b)
            n += 1
        for i in range(d["audio_raw_count"]):
            with open(os.path.join(outdir, "audio-%02u.bin" % i), "wb") as f:
                f.write(audio_bytes(d, i))
        print("wrote %u VIDEO block(s) and %u AUDIO block(s) to %s" % (n, d["audio_raw_count"], outdir))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
