#!/usr/bin/env python3
"""
tools/vfull.py — the strict OGBPFULL1 parser and the GBP-VIDEO-008 analysis
(HARDWARE_TESTS §V6.5, §V6.8, §V6.15; GitHub Issue #7).

    tools/vfull.py analyse <full.bin> [--no-c]      the analysis, exit 0 PASS / 1 FAIL / 2 INCONCLUSIVE
    tools/vfull.py info <full.bin>                  the container, no verdict

WHAT IT DECIDES, PER SAMPLE, AND NOTHING ELSE
  CLAIM-A  the source frame was acquired completely: 40 blocks present, every
           block's STRIP-L decodes to ONE frame_id with CRC OK and BLOCK_INDEX
           equal to its position, and all 38 400 consumed words (bytes 1/3,
           bit 15 masked) equal the oracle tools/icoord.expected_video at the
           frame's OWN frame_id and STATUS.
  CLAIM-B  the source -> texture conversion is full-frame correct: the
           preserved texture equals (1) the Python specification of the
           conversion below, (2) the host-built src/gbp/gbp_vpix.c, and (3)
           the tiled oracle | 0x8000.
  Bit 15 (U-GBP-034) and bytes 0/2 (U-GBP-029) are REPORTED, never corrected,
  never in the verdict. A mismatch is CLASSIFIED with a displacement map:
  because the coordinate field is injective, the observed value at (x, y)
  names the source coordinate it came from.

The verdict stops at the texture. Nothing here says what a television showed.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import icoord  # noqa: E402
import istim  # noqa: E402

MAGIC, END = b"OGBPFULL", b"OGBPFEND"
VERSION, HEADER, META, FOOTER = 1, 0x100, 0x80, 12
RAW, TEX_BYTES, TEXELS = 153600, 76800, 38400
RECORD = META + RAW + TEX_BYTES                     # 230528
K, BLOCKS, BLOCK_RAW, TEX_ROW = 8, 40, 0xF00, 0x780
FLAG_TRUNCATED, FLAG_ORIGIN_SET, FLAG_CAPACITY_SKIPPED = 1, 2, 4
FLAG_ALL = 7
STATE = {0: "EMPTY", 1: "OPEN", 2: "COMPLETE", 3: "REFUSED"}
REASON = {0: "none", 1: "generation", 2: "no_raw", 3: "incomplete", 4: "abandoned"}
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "gbp")


def crc32(b):
    return zlib.crc32(b) & 0xFFFFFFFF


def u16(b, o):
    return (b[o] << 8) | b[o + 1]


def u32(b, o):
    return int.from_bytes(b[o:o + 4], "big")


def u64(b, o):
    return int.from_bytes(b[o:o + 8], "big")


def s16(b, o):
    v = u16(b, o)
    return v - 0x10000 if v & 0x8000 else v


def ident(b, o):
    f = b[o:o + 32]
    if f[-1] != 0:
        raise ValueError("identity not terminated")
    s = f.split(b"\0", 1)[0]
    if any(f[len(s):]):
        raise ValueError("identity has bytes after its terminator")
    return s.decode("ascii")


# ------------------------------------------------------------------ parser ---
def parse(data: bytes) -> dict:
    """Strict: the mirror of gbp_vfulldump_parse(). Raises ValueError."""
    n = len(data)
    if n < HEADER + FOOTER or data[:8] != MAGIC:
        raise ValueError("short file or bad magic")
    h = data[:HEADER]
    if u16(h, 8) != VERSION or u16(h, 0xA) != HEADER:
        raise ValueError("unsupported version / header size")
    if u32(h, 0x10) != RECORD or u32(h, 0x14) != META:
        raise ValueError("unsupported record / meta size")
    if u32(h, HEADER - 4) != crc32(h[:HEADER - 4]):
        raise ValueError("header CRC mismatch")
    info = {"flags": u32(h, 0xC), "records_n": u32(h, 0x18), "k_cap": u32(h, 0x1C), "spacing": u32(h, 0x20),
            "origin": u32(h, 0x24), "raw_bytes": u32(h, 0x28), "tex_bytes": u32(h, 0x2C), "blocks": u32(h, 0x30),
            "block_bytes": u32(h, 0x34), "tex_row_bytes": u32(h, 0x38), "width": u32(h, 0x3C), "height": u32(h, 0x40),
            "tb_hz": u32(h, 0x44), "want_calls": u32(h, 0x48), "wanted": u32(h, 0x4C), "opened": u32(h, 0x50),
            "completed": u32(h, 0x54), "refused": u32(h, 0x58), "skipped_capacity": u32(h, 0x5C),
            "blocks_copied": u32(h, 0x60), "off_records": u32(h, 0x64), "off_footer": u32(h, 0x68),
            "total_size": u64(h, 0x70), "header_crc32": u32(h, HEADER - 4)}
    if info["flags"] & ~FLAG_ALL:
        raise ValueError("unknown flag")
    if info["k_cap"] != K or info["records_n"] > K:
        raise ValueError("K is not 8 or too many records")
    if (info["raw_bytes"], info["tex_bytes"], info["blocks"], info["block_bytes"], info["tex_row_bytes"],
            info["width"], info["height"]) != (RAW, TEX_BYTES, BLOCKS, BLOCK_RAW, TEX_ROW, 240, 160):
        raise ValueError("geometry mismatch")
    if info["off_records"] != HEADER:
        raise ValueError("records offset")
    body = info["records_n"] * RECORD
    if info["off_footer"] != HEADER + body or info["total_size"] != info["off_footer"] + FOOTER or n != info["total_size"]:
        raise ValueError("declared size is not the real size")
    if any(h[0xF8:HEADER - 4]):
        raise ValueError("reserved header bytes not zero")
    info["test_id"], info["build_id"], info["app"], info["commit"] = (ident(h, 0x78), ident(h, 0x98), ident(h, 0xB8), ident(h, 0xD8))
    f = info["off_footer"]
    if data[f:f + 8] != END:
        raise ValueError("footer magic missing")
    info["total_crc32"] = u32(data, f + 8)
    if info["total_crc32"] != crc32(data[:f]):
        raise ValueError("total CRC mismatch")
    recs = []
    for i in range(info["records_n"]):
        o = HEADER + i * RECORD
        r = data[o:o + RECORD]
        m = r[:META]
        rec = {"sample_index": u32(m, 0), "frame_index": u32(m, 4), "seq": u32(m, 8), "life": u32(m, 0xC),
               "slot": u16(m, 0x10), "tex": u16(m, 0x12), "state": u16(m, 0x14), "reason": u16(m, 0x16),
               "blocks_raw": u16(m, 0x18), "blocks_tex": u16(m, 0x1A), "retrace_decision": u32(m, 0x1C),
               "present": u64(m, 0x20), "t_take": u64(m, 0x28), "t_convert_done": u64(m, 0x30),
               "t_decision": u64(m, 0x38), "xfb_target": s16(m, 0x40), "disposition": u16(m, 0x42),
               "record_crc32": u32(m, 0x78)}
        if rec["sample_index"] >= K or rec["state"] not in (1, 2, 3):
            raise ValueError("record %d: sample index / state" % i)
        if any(m[0x44:0x78]) or u32(m, 0x7C) != 0:
            raise ValueError("record %d: reserved bytes" % i)
        pop = bin(rec["present"]).count("1")
        if rec["present"] >> BLOCKS or pop != rec["blocks_raw"] or pop != rec["blocks_tex"]:
            raise ValueError("record %d: present / block counts" % i)
        if rec["state"] == 2 and pop != BLOCKS:
            raise ValueError("record %d: COMPLETE without 40 blocks" % i)
        if crc32(m[:0x78] + r[META:]) != rec["record_crc32"]:
            raise ValueError("record %d: record CRC mismatch" % i)
        rec["raw"] = bytes(r[META:META + RAW])
        tb = r[META + RAW:]
        rec["tex"] = [u16(tb, 2 * t) for t in range(TEXELS)]
        recs.append(rec)
    info["records"] = recs
    return info


def load(path: str) -> dict:
    with open(path, "rb") as f:
        return parse(f.read())


# ------------------------------------------------- the conversion, stated ---
def consumed_words(raw: bytes):
    """38 400 words in raster order: word16 = (byte1 << 8) | byte3 (GBP-VID-003)."""
    out = [0] * TEXELS
    for y in range(160):
        b, line = y // 4, y % 4
        base = b * BLOCK_RAW + line * 960
        for x in range(240):
            o = base + x * 4
            out[y * 240 + x] = (raw[o + 1] << 8) | raw[o + 3]
    return out


def convert_py(raw: bytes):
    """The Python SPECIFICATION of gbp_vpix: tile order + the RGB5A3 opaque bit."""
    words = consumed_words(raw)
    tex = [0] * TEXELS
    for y in range(160):
        for x in range(240):
            tex[icoord.tile_index(x, y)] = words[y * 240 + x] | 0x8000
    return tex


_C_HARNESS = r'''
#include <stdio.h>
#include <stdint.h>
#include "gbp_vpix.h"
static uint8_t raw[153600]; static uint16_t tex[38400];
int main(void) { struct gbp_vpix_stats st; size_t i;
  if (fread(raw, 1, sizeof raw, stdin) != sizeof raw) return 2;
  if (gbp_vpix_frame(raw, sizeof raw, tex, 38400, &st)) return 3;
  for (i = 0; i < 38400; i++) { unsigned char b[2] = { (unsigned char)(tex[i] >> 8), (unsigned char)tex[i] }; fwrite(b, 1, 2, stdout); }
  return 0; }
'''
_c_bin = None


def c_converter():
    """The host-built src/gbp/gbp_vpix.c, or None when gcc is unavailable."""
    global _c_bin
    if _c_bin is not None:
        return _c_bin or None
    d = tempfile.mkdtemp(prefix="opengbp-vpix-")
    src = os.path.join(d, "conv.c")
    with open(src, "w") as f:
        f.write(_C_HARNESS)
    exe = os.path.join(d, "conv")
    r = subprocess.run(["gcc", "-std=gnu11", "-O1", "-I", SRC, "-o", exe, src, os.path.join(SRC, "gbp_vpix.c")],
                       capture_output=True, text=True)
    _c_bin = exe if r.returncode == 0 else ""
    return _c_bin or None


def convert_c(raw: bytes):
    exe = c_converter()
    if not exe:
        return None
    r = subprocess.run([exe], input=raw, capture_output=True)
    if r.returncode != 0 or len(r.stdout) != TEX_BYTES:
        raise RuntimeError("host gbp_vpix.c failed: rc=%d" % r.returncode)
    return [u16(r.stdout, 2 * t) for t in range(TEXELS)]


# --------------------------------------------------------------- analysis ---
def decode_strips(words):
    """Every block's STRIP-L (local row 0, x = 1..54) through the FROZEN decoder."""
    per = []
    for b in range(BLOCKS):
        y = 4 * b
        per.append(istim.decode_canonical([words[y * 240 + x] for x in istim.WITNESS_STRIP], b))
    ok = [d for d in per if d["outcome"] == istim.CANONICAL_OK]
    ids = {d["frame_id"] for d in ok}
    sts = {d["status"] for d in ok}
    consistent = len(ok) == BLOCKS and len(ids) == 1 and all(d["index_ok"] for d in ok) and len(sts) == 1
    return {"blocks_ok": len(ok), "frame_ids": sorted(ids), "statuses": sorted(sts),
            "index_ok": sum(1 for d in ok if d["index_ok"]), "consistent": consistent,
            "frame_id": next(iter(ids)) if len(ids) == 1 else None,
            "status": next(iter(sts)) if len(sts) == 1 else None,
            "fault": any(d.get("fault") for d in ok)}


def classify(mismatches):
    """A displacement class from the mismatched pixels, using the injective field."""
    if not mismatches:
        return "NONE"
    disp = set()
    swapped = 0
    in_field = 0
    for x, y, got, _want in mismatches:
        if not (icoord.FIELD_X0 <= x <= icoord.FIELD_X1):
            continue
        in_field += 1
        src = icoord.field_inverse(icoord.swap_outer(got & 0x7FFF))
        if src is None:
            disp.add(("not_a_field_value",))
            continue
        sx, sy = src
        disp.add((sx - x, sy - y))
        if sx - icoord.FIELD_X0 == y and sy == x - icoord.FIELD_X0:
            swapped += 1
    if in_field == 0:
        return "OUTSIDE_FIELD"
    if in_field == 1:
        return "SINGLE_PIXEL"
    if swapped == in_field:
        return "AXIS_SWAP"
    if len(disp) == 1:
        (d,) = disp
        if d == ("not_a_field_value",):
            return "NOT_A_FIELD_VALUE"
        dx, dy = d
        if dx == 0 and dy % 4 == 0:
            return "BLOCK_DISPLACEMENT" if _whole_blocks(mismatches) else "ROW_SHIFT"
        if dx == 0:
            return "ROW_SHIFT"
        if dy == 0:
            return "COLUMN_SHIFT"
        return "SHIFT"
    if _per_tile_constant(mismatches):
        return "TILE_PERMUTATION"
    return "UNKNOWN"


def _whole_blocks(mismatches):
    rows = {y for _x, y, _g, _w in mismatches}
    return all(all(4 * (y // 4) + r in rows for r in range(4)) for y in rows)


def _per_tile_constant(mismatches):
    tiles = {}
    for x, y, got, _w in mismatches:
        if not (icoord.FIELD_X0 <= x <= icoord.FIELD_X1):
            return False
        src = icoord.field_inverse(icoord.swap_outer(got & 0x7FFF))
        if src is None:
            return False
        tiles.setdefault((x // 4, y // 4), set()).add((src[0] - x, src[1] - y))
    return all(len(v) == 1 for v in tiles.values()) and len(tiles) > 1


def analyse_sample(rec, use_c=True):
    out = {"sample_index": rec["sample_index"], "frame_index": rec["frame_index"], "seq": rec["seq"],
           "state": STATE[rec["state"]], "reason": REASON.get(rec["reason"], rec["reason"])}
    if rec["state"] != 2:
        out["verdict"] = "INCONCLUSIVE"
        out["why"] = "sample not COMPLETE (%s, %s)" % (out["state"], out["reason"])
        return out
    words = consumed_words(rec["raw"])
    strips = decode_strips(words)
    out["strips"] = strips
    if not strips["consistent"]:
        out["verdict"] = "INCONCLUSIVE"
        out["why"] = "STRIP-L inconsistent: %s" % strips
        return out
    fid, st = strips["frame_id"], strips["status"]
    out["frame_id"], out["status"], out["fault"] = fid, st, strips["fault"]
    # bit 15 and bytes 0/2: reported, never in the verdict
    out["bit15"] = [(i % 240, i // 240) for i, w in enumerate(words) if w & 0x8000]
    dev = []
    raw = rec["raw"]
    for y in range(160):
        base = (y // 4) * BLOCK_RAW + (y % 4) * 960
        for x in range(240):
            o = base + x * 4
            if raw[o] or raw[o + 2]:
                dev.append((x, y, raw[o], raw[o + 2]))
    out["bytes02"] = {"count": len(dev), "first": dev[:8]}
    # CLAIM-A: colour15 against the oracle at the frame's OWN id and status
    mism = []
    for y in range(160):
        for x in range(240):
            got = words[y * 240 + x] & 0x7FFF
            want = icoord.expected_video(fid, x, y, st)
            if got != want:
                mism.append((x, y, got, want))
    out["colour15_mismatches"] = len(mism)
    out["colour15_first"] = mism[:8]
    out["displacement_class"] = classify(mism)
    # CLAIM-B: the preserved texture against the three references
    tex = rec["tex"]
    py = convert_py(raw)
    oracle = icoord.tiled_oracle(fid, st)
    # the oracle has no bit-15 knowledge of the wire: the texture ORs it in, so compare on the OR'd form
    out["tex_vs_python"] = sum(1 for a, b in zip(tex, py) if a != b)
    out["tex_vs_oracle"] = sum(1 for a, b in zip(tex, oracle) if a != b)
    if use_c:
        c = convert_c(raw)
        out["tex_vs_c"] = None if c is None else sum(1 for a, b in zip(tex, c) if a != b)
    else:
        out["tex_vs_c"] = None
    if strips["fault"]:
        out["verdict"] = "INCONCLUSIVE"
        out["why"] = "STATUS.FAULT set: the stimulus left VBlank"
    elif mism or out["tex_vs_python"] or out["tex_vs_oracle"] or out["tex_vs_c"]:
        out["verdict"] = "FAIL"
        out["why"] = "colour15 %d (%s); tex vs python %d, oracle %d, c %s" % (
            len(mism), out["displacement_class"], out["tex_vs_python"], out["tex_vs_oracle"], out["tex_vs_c"])
    else:
        out["verdict"] = "PASS"
        out["why"] = "38 400 words equal; texture == python == oracle%s" % ("" if out["tex_vs_c"] is None else " == c")
    return out


def analyse(info, use_c=True):
    samples = [analyse_sample(r, use_c) for r in info["records"]]
    verdicts = [s["verdict"] for s in samples]
    if info["records_n"] < K or not (info["flags"] & FLAG_ORIGIN_SET):
        overall, why = "INCONCLUSIVE", "%d of %d samples present, origin_set=%d" % (
            info["records_n"], K, 1 if info["flags"] & FLAG_ORIGIN_SET else 0)
    elif "FAIL" in verdicts:
        overall, why = "FAIL", "%d sample(s) fail" % verdicts.count("FAIL")
    elif "INCONCLUSIVE" in verdicts:
        overall, why = "INCONCLUSIVE", "%d sample(s) inconclusive" % verdicts.count("INCONCLUSIVE")
    else:
        overall, why = "PASS", "every sample: CLAIM-A and CLAIM-B, at the texture"
    return {"verdict": overall, "why": why, "samples": samples,
            "boundary": "source -> converted texture only; nothing about the VI, the XFB or a display"}


def format_report(info, a):
    out = ["OGBPFULL1 %s / %s / %s / %s" % (info["test_id"], info["build_id"], info["app"], info["commit"]),
           "  records %d of K=%d  spacing %d  origin %d  flags 0x%x" % (info["records_n"], info["k_cap"], info["spacing"], info["origin"], info["flags"]),
           "  want_calls %d wanted %d opened %d completed %d refused %d skipped_capacity %d blocks_copied %d" % (
               info["want_calls"], info["wanted"], info["opened"], info["completed"], info["refused"],
               info["skipped_capacity"], info["blocks_copied"]),
           "  header/total CRC-32 %08x / %08x" % (info["header_crc32"], info["total_crc32"])]
    for s in a["samples"]:
        line = "  sample %d frame_index %d seq %d %s" % (s["sample_index"], s["frame_index"], s["seq"], s["state"])
        if "frame_id" in s:
            line += " frame_id %d status 0x%02x colour15 mismatches %d class %s tex(py/oracle/c) %s/%s/%s bit15 %s bytes02 %d" % (
                s["frame_id"], s["status"], s["colour15_mismatches"], s["displacement_class"],
                s["tex_vs_python"], s["tex_vs_oracle"], s["tex_vs_c"], s["bit15"][:4], s["bytes02"]["count"])
        out.append(line + "  -> " + s["verdict"] + ": " + s["why"])
    out.append("VERDICT %s -- %s" % (a["verdict"], a["why"]))
    out.append("BOUNDARY " + a["boundary"])
    return "\n".join(out)


def main(argv):
    if len(argv) < 3 or argv[1] not in ("analyse", "info"):
        print(__doc__)
        return 2
    info = load(argv[2])
    if argv[1] == "info":
        print(format_report(info, {"samples": [], "verdict": "-", "why": "info only", "boundary": "-"}))
        return 0
    a = analyse(info, use_c="--no-c" not in argv)
    print(format_report(info, a))
    return {"PASS": 0, "FAIL": 1}.get(a["verdict"], 2)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
