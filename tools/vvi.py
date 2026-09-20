#!/usr/bin/env python3
"""
tools/vvi.py — the strict OGBPVI1 parser and the GBP-VIDEO-007 SOFTWARE chain
(HARDWARE_TESTS §V6.4, §V6.8, §V6.15; GitHub Issue #7).

    tools/vvi.py analyse <vi.bin> [--idxcap <idxcap.bin>] [--disp <disp.bin>]

WHAT THIS TOOL IS, AND IS NOT
  It joins three machine records into the identity chain of §V6.4:
    OGBPIDXCAP1  frame_index <-> frame_id (every retained record decodes its own id)
    OGBPDISP2    frame_index -> SELECTED_NEW hand-over, xfb_target, t_decision, retrace
    OGBPVI1      hand-over -> the pump's first observation that libogc2 reports the
                 handed XFB as current, with the VI framebuffer-base registers read back
  and tabulates, per appearance k of the coord-0001 glyph, R_k (the frame ids
  that carry the digit), H_k (the retained ones that were handed to the VI)
  and L_k (the handed ones that were observed current with consistent
  registers). ALL OF IT IS SOFTWARE EVIDENCE (CLAIM-C). The tool has no field,
  flag or input for what a person saw; the operator's report is placed beside
  this table by the ingestion, never fed into it. Nothing here classifies
  physical visibility, and a PASS / FAIL of GBP-VIDEO-007 is not computed here.
"""
from __future__ import annotations

import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import istim  # noqa: E402

MAGIC, END = b"OGBPVI1\x00", b"OGBPVEND"
VERSION, HEADER, RECORD, FOOTER = 1, 0x100, 64, 12
F_LATCHED, F_SUPERSEDED = 1, 2
FLAG_TRUNCATED, FLAG_OVERFLOW = 1, 2
GLYPH_P, GLYPH_W = 480, 40


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


def s32(b, o):
    v = u32(b, o)
    return v - 0x100000000 if v & 0x80000000 else v


def ident(b, o):
    f = b[o:o + 32]
    if f[-1] != 0:
        raise ValueError("identity not terminated")
    s = f.split(b"\0", 1)[0]
    if any(f[len(s):]):
        raise ValueError("identity has bytes after its terminator")
    return s.decode("ascii")


def parse(data: bytes) -> dict:
    """Strict: the mirror of gbp_vvidump_parse(). Raises ValueError."""
    n = len(data)
    if n < HEADER + FOOTER or data[:8] != MAGIC:
        raise ValueError("short file or bad magic")
    h = data[:HEADER]
    if u16(h, 8) != VERSION or u16(h, 0xA) != HEADER or u32(h, 0x10) != RECORD:
        raise ValueError("unsupported version / sizes")
    if u32(h, HEADER - 4) != crc32(h[:HEADER - 4]):
        raise ValueError("header CRC mismatch")
    info = {"flags": u32(h, 0xC), "records_cap": u32(h, 0x14), "records_n": u32(h, 0x18), "tb_hz": u32(h, 0x1C),
            "xfb_slots": u32(h, 0x20), "handed": u32(h, 0x24), "latched": u32(h, 0x28), "superseded": u32(h, 0x2C),
            "overflow": u32(h, 0x30), "observe_calls": u32(h, 0x34), "awaiting_at_end": s32(h, 0x38),
            "off_records": u32(h, 0x3C), "off_footer": u32(h, 0x40), "total_size": u64(h, 0x48),
            "header_crc32": u32(h, HEADER - 4)}
    if info["flags"] & ~(FLAG_TRUNCATED | FLAG_OVERFLOW):
        raise ValueError("unknown flag")
    if info["records_n"] > info["records_cap"] or info["off_records"] != HEADER:
        raise ValueError("bounds")
    if info["off_footer"] != HEADER + info["records_n"] * RECORD or info["total_size"] != info["off_footer"] + FOOTER or n != info["total_size"]:
        raise ValueError("declared size is not the real size")
    if any(h[0xD0:HEADER - 4]):
        raise ValueError("reserved header bytes not zero")
    info["test_id"], info["build_id"], info["app"], info["commit"] = (ident(h, 0x50), ident(h, 0x70), ident(h, 0x90), ident(h, 0xB0))
    f = info["off_footer"]
    if data[f:f + 8] != END:
        raise ValueError("footer magic missing")
    info["total_crc32"] = u32(data, f + 8)
    if info["total_crc32"] != crc32(data[:f]):
        raise ValueError("total CRC mismatch")
    recs = []
    for i in range(info["records_n"]):
        r = data[HEADER + i * RECORD:HEADER + (i + 1) * RECORD]
        fl = u16(r, 0xA)
        if fl & ~(F_LATCHED | F_SUPERSEDED) or (fl & F_LATCHED and fl & F_SUPERSEDED):
            raise ValueError("record %d: flags" % i)
        if any(r[0x30:0x3C]):
            raise ValueError("record %d: reserved" % i)
        if not (fl & F_LATCHED) and (u64(r, 0x20) or u32(r, 0x1C)):
            raise ValueError("record %d: latch fields on an unlatched record" % i)
        if crc32(r[:0x3C]) != u32(r, 0x3C):
            raise ValueError("record %d: record CRC mismatch" % i)
        recs.append({"frame_index": u32(r, 0), "life": u32(r, 4), "xfb": s16(r, 8), "flags": fl,
                     "phys": u32(r, 0xC), "t_handed": u64(r, 0x10), "retrace_handed": u32(r, 0x18),
                     "retrace_latch": u32(r, 0x1C), "t_latch": u64(r, 0x20),
                     "vi14": u16(r, 0x28), "vi15": u16(r, 0x2A), "vi18": u16(r, 0x2C), "vi19": u16(r, 0x2E),
                     "latched": bool(fl & F_LATCHED), "superseded": bool(fl & F_SUPERSEDED)})
    info["records"] = recs
    return info


def load(path):
    with open(path, "rb") as f:
        return parse(f.read())


# ------------------------------------------------ the VI register model ----
def regs_consistent(rec):
    """libogc2 __setFbbRegs: for a MEM1 address (< 0x01000000) flag bit 12 is 0
    and TFBL = the physical base (bits 23..16 in reg14[7:0], 15..0 in reg15);
    BFBL is the same base (single-field) or base + one line (double-field).
    Returns (top_matches, bottom_plausible, observed_top)."""
    if not rec["latched"]:
        return (False, False, None)
    flag = (rec["vi14"] >> 12) & 1
    top = ((rec["vi14"] & 0xFF) << 16) | rec["vi15"]
    bottom = ((rec["vi18"] & 0xFF) << 16) | rec["vi19"]
    phys = rec["phys"] & 0xFFFFFF
    if flag:
        top <<= 5
        bottom <<= 5
    return (top == phys, bottom in (phys, phys + 1280), top)


# -------------------------------------------------------------- the joins ---
def idx_map(idx_info):
    """{frame_index: frame_id} for the retained records whose STRIP-L decodes
    (tools/vidxcap.load() output; the decode is the FROZEN istim one)."""
    out = {}
    for r in idx_info["records"]:
        ids = set()
        for b in range(40):
            d = istim.decode_canonical(r["witness"][b], b)
            if d["outcome"] == istim.CANONICAL_OK and d["index_ok"]:
                ids.add(d["frame_id"])
        if len(ids) == 1:
            out[r["frame_index"]] = ids.pop()
    return out


def chain(fi_to_fid, disp_info, vi_info, appearances=(1, 2, 3, 4), P=GLYPH_P, W=GLYPH_W):
    """Per appearance k: R_k, the retained frame_index set, H_k, L_k — SOFTWARE only."""
    selected = {}
    for r in disp_info["life"]:
        if r["frame_index"] != 0xFFFFFFFF and r["disposition"] == 1:      # SELECTED_NEW
            selected[r["frame_index"]] = r
    targets = {}
    for e in disp_info.get("events", []):
        if e.get("decision") == 1:
            targets[e["frame_index"]] = e["xfb_target"]
    latched = {}
    for v in vi_info["records"]:
        if v["latched"]:
            latched.setdefault(v["frame_index"], []).append(v)
    rows = []
    for k in appearances:
        R = set(range(k * P, k * P + W))
        retained = {fi: fid for fi, fid in fi_to_fid.items() if fid in R}
        H = {fi: selected[fi] for fi in retained if fi in selected}
        L = {}
        for fi in H:
            for v in latched.get(fi, []):
                ok_top, ok_bottom, _ = regs_consistent(v)
                if ok_top:
                    L[fi] = v
        rows.append({"k": k, "digit": k % 10, "R": sorted(R), "retained": len(retained), "H": len(H), "L": len(L),
                     "first_handed_t": min((h["t_decision"] for h in H.values()), default=None),
                     "first_latch_t": min((v["t_latch"] for v in L.values()), default=None),
                     "xfb_targets": sorted({targets.get(fi, -2) for fi in H})})
    return rows


def format_report(vi_info, rows=None):
    out = ["OGBPVI1 %s / %s / %s / %s" % (vi_info["test_id"], vi_info["build_id"], vi_info["app"], vi_info["commit"]),
           "  records %d/%d  handed %d latched %d superseded %d overflow %d observe_calls %d awaiting_at_end %d flags 0x%x" % (
               vi_info["records_n"], vi_info["records_cap"], vi_info["handed"], vi_info["latched"], vi_info["superseded"],
               vi_info["overflow"], vi_info["observe_calls"], vi_info["awaiting_at_end"], vi_info["flags"]),
           "  header/total CRC-32 %08x / %08x" % (vi_info["header_crc32"], vi_info["total_crc32"])]
    cons = [regs_consistent(r) for r in vi_info["records"] if r["latched"]]
    out.append("  register readback: %d/%d latched records name the handed XFB as TFBL; %d bottom fields plausible" % (
        sum(1 for c in cons if c[0]), len(cons), sum(1 for c in cons if c[1])))
    if rows:
        out.append("  k digit |R_k| retained |H_k| |L_k|   first t_handed   first t_latch   xfb")
        for r in rows:
            out.append("  %d   %d    %2d      %3d     %3d   %3d   %16s %16s   %s" % (
                r["k"], r["digit"], len(r["R"]), r["retained"], r["H"], r["L"],
                r["first_handed_t"], r["first_latch_t"], r["xfb_targets"]))
    out.append("SOFTWARE CHAIN ONLY (CLAIM-C). This tool does not know what the operator saw and does not classify GBP-VIDEO-007.")
    return "\n".join(out)


def main(argv):
    if len(argv) < 3 or argv[1] != "analyse":
        print(__doc__)
        return 2
    vi_info = load(argv[2])
    rows = None
    if "--idxcap" in argv and "--disp" in argv:
        import vidxcap
        import vdisp
        fi_to_fid = idx_map(vidxcap.load(argv[argv.index("--idxcap") + 1]))
        rows = chain(fi_to_fid, vdisp.load(argv[argv.index("--disp") + 1]), vi_info)
    print(format_report(vi_info, rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
