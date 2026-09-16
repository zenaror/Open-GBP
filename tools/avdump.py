#!/usr/bin/env python3
"""
avdump — parse the block sidecar of GBP-AV-SERVICE-001 (`<TestID>_<BuildID>-blocks.bin`,
written by src/gbp/gbp_avdump.c) on the host: the raw AUDIO / VIDEO blocks of one run
with the identity (test ID, build ID, app, commit — four 32-byte fields, never truncated), the
pending-source mask, the lengths, the per-block CRC-32s and the DMA timings. The layout (format
version 2, big-endian, fixed offsets, 256-byte header) is documented in src/gbp/gbp_avdump.h.

Usage:
    tools/avdump.py info    <blocks.bin>              header fields, CRC checks, byte windows
    tools/avdump.py extract <blocks.bin> <outdir>     writes audio.bin / video.bin (present blocks only)
    tools/avdump.py json    <blocks.bin>              machine-readable header (no bytes)
Exit status 0 when the file parses and every CRC matches; 1 otherwise.

Importable: parse(data) -> dict (raises ValueError with the same codes as the C parser),
serialize(info, audio, video) -> bytes (for synthetic host tests; never for evidence).
"""
from __future__ import annotations

import json
import os
import struct
import sys
import zlib

MAGIC = b"OGBPBLK1"
END = b"OGBPEND1"
VERSION = 2
HEADER_SIZE = 0x100
FOOTER_SIZE = 12
ID_FIELD, ID_MAX = 32, 31
OFF_TEST_ID, OFF_BUILD_ID, OFF_APP, OFF_COMMIT, OFF_AUDIO_INDEX, OFF_HEADER_CRC = 0x40, 0x60, 0x80, 0xA0, 0xC0, 0xFC
FLAG_AUDIO_PRESENT, FLAG_AUDIO_VALID, FLAG_VIDEO_PRESENT, FLAG_VIDEO_VALID = 1, 2, 4, 8
RC_NAMES = {0: "ok", 1: "timeout", 2: "busy", 3: "param", 4: "backend"}


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


def parse(data):
    """Parses a sidecar. Returns a dict with the header fields, `audio` / `video` bytes
    (None when absent) and the CRC verdicts. Raises ValueError("-N: …") like the C parser."""
    if len(data) < HEADER_SIZE + FOOTER_SIZE or data[:8] != MAGIC:
        raise ValueError("-1: too short or bad magic")
    version, header_size = struct.unpack(">HH", data[8:12])
    if version != VERSION or header_size != HEADER_SIZE:
        raise ValueError("-2: unsupported version %d / header size %d" % (version, header_size))
    header_crc = struct.unpack(">I", data[OFF_HEADER_CRC:OFF_HEADER_CRC + 4])[0]
    if crc32(data[:OFF_HEADER_CRC]) != header_crc:
        raise ValueError("-3: header CRC mismatch")
    (flags, pending_irq, drain_mask, audio_len, video_len, audio_crc, video_crc, audio_rc, video_rc,
     audio_wait, video_wait, audio_dt, video_dt, tb_hz) = struct.unpack(">IHHIIIIIIIIIII", data[0x0C:0x40])
    test_id = _id(data[OFF_TEST_ID:OFF_TEST_ID + ID_FIELD], False)
    build_id = _id(data[OFF_BUILD_ID:OFF_BUILD_ID + ID_FIELD], False)
    app = _id(data[OFF_APP:OFF_APP + ID_FIELD], True)
    commit = _id(data[OFF_COMMIT:OFF_COMMIT + ID_FIELD], True)
    audio_index, video_index = struct.unpack(">II", data[OFF_AUDIO_INDEX:OFF_AUDIO_INDEX + 8])
    if data[OFF_AUDIO_INDEX + 8:OFF_HEADER_CRC].strip(b"\0"):
        raise ValueError("-8: reserved header bytes are not zero")
    need = HEADER_SIZE + audio_len + video_len + FOOTER_SIZE
    if audio_len > 0x100000 or video_len > 0x100000 or len(data) < need:
        raise ValueError("-4: truncated payload (need %d, have %d)" % (need, len(data)))
    p = HEADER_SIZE + audio_len + video_len
    if data[p:p + 8] != END:
        raise ValueError("-5: footer magic missing")
    total_crc = struct.unpack(">I", data[p + 8:p + 12])[0]
    if crc32(data[:p]) != total_crc:
        raise ValueError("-6: total CRC mismatch")
    audio = data[HEADER_SIZE:HEADER_SIZE + audio_len] if audio_len else None
    video = data[HEADER_SIZE + audio_len:p] if video_len else None
    if audio is not None and crc32(audio) != audio_crc:
        raise ValueError("-7: audio CRC mismatch")
    if video is not None and crc32(video) != video_crc:
        raise ValueError("-7: video CRC mismatch")
    return {
        "version": version, "flags": flags, "pending_irq": pending_irq, "drain_mask": drain_mask,
        "audio_present": bool(flags & FLAG_AUDIO_PRESENT), "audio_valid": bool(flags & FLAG_AUDIO_VALID),
        "video_present": bool(flags & FLAG_VIDEO_PRESENT), "video_valid": bool(flags & FLAG_VIDEO_VALID),
        "audio_len": audio_len, "video_len": video_len, "audio_crc32": audio_crc, "video_crc32": video_crc,
        "audio_rc": RC_NAMES.get(audio_rc, str(audio_rc)), "video_rc": RC_NAMES.get(video_rc, str(video_rc)),
        "audio_wait_ticks": audio_wait, "video_wait_ticks": video_wait, "audio_dt_ticks": audio_dt, "video_dt_ticks": video_dt,
        "tb_hz": tb_hz, "test_id": test_id, "build_id": build_id, "app": app, "commit": commit,
        "audio_index": audio_index, "video_index": video_index, "header_crc32": header_crc, "total_crc32": total_crc,
        "size": need, "trailing_bytes": len(data) - need, "audio": audio, "video": video,
    }


def serialize(info, audio=b"", video=b""):
    """The inverse layout, for synthetic host tests only (never a source of evidence)."""
    audio = audio or b""
    video = video or b""
    h = bytearray(HEADER_SIZE)
    h[0:8] = MAGIC
    struct.pack_into(">HH", h, 8, VERSION, HEADER_SIZE)
    struct.pack_into(">IHHIIIIIIIIIII", h, 0x0C, info.get("flags", 0), info.get("pending_irq", 0), info.get("drain_mask", 0),
                     len(audio), len(video), crc32(audio) if audio else 0, crc32(video) if video else 0,
                     info.get("audio_rc", 0), info.get("video_rc", 0), info.get("audio_wait_ticks", 0), info.get("video_wait_ticks", 0),
                     info.get("audio_dt_ticks", 0), info.get("video_dt_ticks", 0), info.get("tb_hz", 0))
    for off, key, may_be_empty in ((OFF_TEST_ID, "test_id", False), (OFF_BUILD_ID, "build_id", False), (OFF_APP, "app", True), (OFF_COMMIT, "commit", True)):
        s = info.get(key, "")
        if not _id_ok(s, may_be_empty):
            raise ValueError("identity %s does not fit the rule (1..%d printable ASCII characters without spaces): %r" % (key, ID_MAX, s))
        b = s.encode("ascii")
        h[off:off + len(b)] = b                                     # the rest of the field stays zero
    struct.pack_into(">II", h, OFF_AUDIO_INDEX, info.get("audio_index", 8), info.get("video_index", 1))
    struct.pack_into(">I", h, OFF_HEADER_CRC, crc32(bytes(h[:OFF_HEADER_CRC])))
    body = bytes(h) + audio + video
    return body + END + struct.pack(">I", crc32(body))


def _windows(b, n=4):
    if not b:
        return []
    L = len(b)
    offs = [0, (L // 3) & ~31, (2 * L // 3) & ~31, max(L - 32, 0)]
    return [(o, b[o:o + 32].hex()) for o in offs]


def info_text(d):
    out = ["avdump: %s_%s app=%s commit=%s size=%d bytes%s" % (d["test_id"], d["build_id"], d["app"], d["commit"], d["size"],
                                                               " (+%d trailing)" % d["trailing_bytes"] if d["trailing_bytes"] else ""),
           "pending_irq=%04x drain_mask=%04x tb_hz=%d flags=%#x" % (d["pending_irq"], d["drain_mask"], d["tb_hz"], d["flags"])]
    for kind in ("audio", "video"):
        out.append("%s: index=%d present=%d valid=%d len=%#x rc=%s crc32=%08x wait_ticks=%d dt_ticks=%d" % (
            kind, d[kind + "_index"], d[kind + "_present"], d[kind + "_valid"], d[kind + "_len"], d[kind + "_rc"],
            d[kind + "_crc32"], d[kind + "_wait_ticks"], d[kind + "_dt_ticks"]))
        b = d[kind]
        if b:
            zeros = b.count(0)
            out.append("  zeros=%d distinct=%d first_word=%08x gbi_frame_start=%d" % (
                zeros, len(set(b)), int.from_bytes(b[:4], "big"), int((int.from_bytes(b[:4], "big") & 0x80800000) == 0x80800000)))
            for o, hx in _windows(b):
                out.append("  off=%04x %s" % (o, hx))
    out.append("format: version %d header %#x bytes; crc: header ok, total ok, blocks ok" % (d["version"], HEADER_SIZE))
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
        print("avdump: %s: %s" % (path, e))
        return 1
    if cmd == "info":
        print(info_text(d))
        return 0
    if cmd == "json":
        j = {k: v for k, v in d.items() if k not in ("audio", "video")}
        print(json.dumps(j, indent=1))
        return 0
    if cmd == "extract":
        if len(argv) < 3:
            print("extract needs an output directory", file=sys.stderr)
            return 2
        os.makedirs(argv[2], exist_ok=True)
        for kind in ("audio", "video"):
            if d[kind]:
                with open(os.path.join(argv[2], kind + ".bin"), "wb") as f:
                    f.write(d[kind])
                print("wrote %s (%d bytes, crc32 %08x)" % (os.path.join(argv[2], kind + ".bin"), len(d[kind]), d[kind + "_crc32"]))
        return 0
    print("unknown command", cmd, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
