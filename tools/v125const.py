#!/usr/bin/env python3
"""
tools/v125const.py — GitHub Issue #125, steps 1 and 2: where the reference binaries hold the numbers the audio path
would need, and how the three GBI editions differ in them. No disassembler; addresses and counts only, never bytes.

    tools/v125const.py [--json <out>]

THE BINARIES, read from the private inputs and never written anywhere: gbi.dol, gbihf.dol and gbisr.dol, each unpacked
IN MEMORY by tools/gbi_unpack.py (XOR key + XZ) and taken as a raw image loaded at LOAD = 0x80003100 -- the load address
EVIDENCE.md records for gbi's unpacked image, and VERIFIED for gbihf and gbisr by tools/v125ref.py (their code builds the
addresses of the audio tables and presets at that load) -- and the Start-up Disc's main.dol
(input/extracted/gbp-disc/sys/main.dol), whose sections carry their own addresses (tools/dolinfo.py). Absent inputs are
reported absent.

WHAT IS COUNTED, per binary (a count is where the number is written, not a proof that the audio path uses it):
  imm       PowerPC immediates: li (addi rD,0,SIMM), ori, cmpwi/cmplwi, mulli -- 16-bit values
  const32   32-bit constants BUILT by lis rD,hi followed within LOOKAHEAD instructions by addi/ori rX,rD,lo, or used as
            the base of a load or store at displacement d off rD (hi + d: how an MMIO address such as the AI's
            0xCC006C00, or the AGB's SOUNDBIAS 0x04000088, is usually reached). For addi and the loads/stores rA = 0
            means a literal zero, so a lis of r0 is never their base. A lis counts ALONE (hi << 16) only when nothing
            in the lookahead consumes it that way. A count is of construction SITES: a lis read by several consumers
            that reach the same value counts once.
  word32    big-endian 32-bit words anywhere in the image equal to a target (tables, literal pools)
  word32le  the same targets as LITTLE-endian words (an embedded ARM/Thumb literal pool would hold them so)
  float     IEEE single and double constants anywhere in the image equal to a target rate (32000.0, 65536.0, ...)
  strings   printable ASCII runs holding an audio keyword, reported as (address, keyword) -- the text itself is not
            printed beyond the keyword
TARGETS: the AUDIO block 0x1000; the candidate rates 4096, 32768, 65536, 131072, 262144; SOUNDBIAS's default 0x0200 and
its address 0x04000088; the AI rates 32000, 32028, 48000; the resampler shapes 125, 256; the AI registers 0xCC006C00..0C
and the DSP audio-DMA registers 0xCC005030/32/36.

THE DIFFERENTIAL: for every target and kind, the three editions' counts side by side, and the targets whose counts
differ between gbi and gbihf -- by gbihf's name, the High-Fidelity edition, the fidelity decision set is what differs.
DESCRIPTIVE: a LEAD at most (#125 §4); what a reference writes says what it does, never what the hardware does.

Standard library only.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dolinfo  # noqa: E402
import gbi_unpack  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOAD = 0x80003100
LOOKAHEAD = 6
DFORM = range(32, 56)                  # lwz .. stfdu: the D-form loads and stores, base register rA, 16-bit displacement
EDITIONS = ("gbi", "gbihf", "gbisr")
DISC_DOL = os.path.join(ROOT, "input", "extracted", "gbp-disc", "sys", "main.dol")
IMM_TARGETS = (0x1000, 4096, 512, 125, 256, 32000, 32028, 32767)       # 16-bit ones (4096 == 0x1000, kept once)
C32_TARGETS = (0x1000, 32768, 65536, 131072, 262144, 0x0200, 32000, 32028, 48000, 0x04000088,
               0xCC006C00, 0xCC006C04, 0xCC006C08, 0xCC006C0C, 0xCC005030, 0xCC005032, 0xCC005036)
RATES = (4096.0, 32000.0, 32028.0, 32768.0, 48000.0, 65536.0, 131072.0, 262144.0)
KEYWORDS = ("sound", "audio", "stereo", "mono", "original", "volume", "bias", "sample", "rate", "latency",
            "buffer", "resampl", "surround", "dsp", "echo")


def editions_images():
    out = {}
    for e in EDITIONS:
        p = os.path.join(ROOT, "input", "gbi", "apps", e, e + ".dol")
        if not os.path.isfile(p):
            out[e] = None
            continue
        with open(p, "rb") as f:
            out[e] = [(LOAD, gbi_unpack.unpack(f.read())[0], True)]    # one region, treated as code and data
    return out


def disc_image():
    if not os.path.isfile(DISC_DOL):
        return None
    with open(DISC_DOL, "rb") as f:
        data = f.read()
    offs = struct.unpack_from(">18I", data, 0)
    addrs = struct.unpack_from(">18I", data, 0x48)
    sizes = struct.unpack_from(">18I", data, 0x90)
    regions = []
    for i in range(dolinfo.DOL_SECTIONS):
        if sizes[i]:
            regions.append((addrs[i], data[offs[i]:offs[i] + sizes[i]], i < dolinfo.DOL_TEXT_SECTIONS))
    return regions


def sext16(v):
    return v - 0x10000 if v & 0x8000 else v


def scan_code(regions):
    """(imm hits {value: [addr]}, const32 hits {value: [addr]}) over the code regions, word-aligned."""
    imm, c32 = {}, {}
    for base, buf, is_code in regions:
        if not is_code:
            continue
        n = len(buf) // 4
        words = struct.unpack_from(">%dI" % n, buf, 0)
        for i, w in enumerate(words):
            op = w >> 26
            rd, ra, lo = (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
            addr = base + 4 * i
            val = None
            if op == 14 and ra == 0:                     # li rD, SIMM
                val = sext16(lo) & 0xFFFFFFFF
            elif op in (24, 10, 11, 7):                  # ori / cmplwi / cmpwi / mulli
                val = lo if op in (24, 10) else sext16(lo) & 0xFFFFFFFF
            if val is not None and val in IMM_TARGETS:
                imm.setdefault(val, []).append(addr)
            if op == 15 and ra == 0:                     # lis rD, hi
                hi = lo << 16
                consumed = False
                for j in range(i + 1, min(n, i + 1 + LOOKAHEAD)):
                    w2 = words[j]
                    op2, ra2, lo2 = w2 >> 26, (w2 >> 16) & 31, w2 & 0xFFFF
                    rs2 = (w2 >> 21) & 31
                    v2 = None
                    if rd != 0 and (op2 == 14 or op2 in DFORM) and ra2 == rd:   # addi rX, rD, lo | load/store d(rD)
                        v2 = (hi + sext16(lo2)) & 0xFFFFFFFF
                    elif op2 == 24 and rs2 == rd:        # ori rX, rD, lo
                        v2 = hi | lo2
                    if v2 is not None:
                        consumed = True
                        if v2 in C32_TARGETS and addr not in c32.get(v2, []):    # one site per lis, not per consumer
                            c32.setdefault(v2, []).append(addr)
                if not consumed and hi in C32_TARGETS:
                    c32.setdefault(hi, []).append(addr)
    return imm, c32


def scan_data(regions, le=None):
    """(word32 {value: [addr]}, float {rate: [(addr, 's'|'d')]}) anywhere, 4-aligned words and 8-aligned doubles; with
    a dict for `le`, the targets found as little-endian words are added to it as {value: [addr]}."""
    w32, flt = {}, {}
    singles = dict((struct.unpack(">I", struct.pack(">f", r))[0], r) for r in RATES)
    doubles = dict((struct.unpack(">Q", struct.pack(">d", r))[0], r) for r in RATES)
    targets = set(C32_TARGETS) - {0x0200, 0x1000}      # small values are everywhere in data; kept to the imm scan
    swapped = dict((struct.unpack("<I", struct.pack(">I", t))[0], t) for t in targets)
    for base, buf, _is_code in regions:
        n = len(buf) // 4
        words = struct.unpack_from(">%dI" % n, buf, 0)
        for i, w in enumerate(words):
            addr = base + 4 * i
            if w in targets:
                w32.setdefault(w, []).append(addr)
            if le is not None and w in swapped:
                le.setdefault(swapped[w], []).append(addr)
            if w in singles:
                flt.setdefault(singles[w], []).append((addr, "s"))
            if i % 2 == 0 and i + 1 < n:
                q = (w << 32) | words[i + 1]
                if q in doubles:
                    flt.setdefault(doubles[q], []).append((addr, "d"))
    return w32, flt


def scan_strings(regions, minlen=4):
    """[(address, keyword)] for printable ASCII runs holding a keyword (case-insensitive)."""
    out = []
    for base, buf, _is_code in regions:
        start = None
        for k in range(len(buf) + 1):
            c = buf[k] if k < len(buf) else 0
            if 32 <= c < 127:
                if start is None:
                    start = k
                continue
            if start is not None and k - start >= minlen:
                s = buf[start:k].decode("ascii").lower()
                for kw in KEYWORDS:
                    if kw in s:
                        out.append((base + start, kw))
            start = None
    return out


def analyse_regions(regions):
    imm, c32 = scan_code(regions)
    w32le = {}
    w32, flt = scan_data(regions, w32le)
    strs = scan_strings(regions)
    kw = {}
    for _a, k in strs:
        kw[k] = kw.get(k, 0) + 1
    return {"imm": dict(("0x%X" % v, sorted(a)) for v, a in imm.items()),
            "const32": dict(("0x%08X" % v, sorted(a)) for v, a in c32.items()),
            "word32": dict(("0x%08X" % v, sorted(a)) for v, a in w32.items()),
            "word32le": dict(("0x%08X" % v, sorted(a)) for v, a in w32le.items()),
            "float": dict(("%g" % r, sorted(a)) for r, a in flt.items()),
            "keywords": kw, "strings": strs,
            "size": sum(len(b) for _base, b, _c in regions)}


def differential(res):
    """{kind: {target: {edition: count}}} for every target any edition holds, and the ones gbi and gbihf differ on."""
    table, differ = {}, []
    for kind in ("imm", "const32", "word32", "word32le", "float", "keywords"):
        keys = set()
        for e in EDITIONS:
            if res.get(e):
                keys |= set(res[e][kind])
        for k in sorted(keys):
            row = dict((e, (len(res[e][kind].get(k, [])) if kind != "keywords" else res[e][kind].get(k, 0))
                        if res.get(e) else None) for e in EDITIONS)
            table.setdefault(kind, {})[k] = row
            if row.get("gbi") != row.get("gbihf"):
                differ.append((kind, k, row))
    return table, differ


def analyse():
    res = {}
    for e, regions in editions_images().items():
        res[e] = analyse_regions(regions) if regions else None
    d = disc_image()
    res["disc"] = analyse_regions(d) if d else None
    table, differ = differential(res)
    return {"load": "0x%08X" % LOAD, "binaries": res, "differential": table, "gbi_vs_gbihf": differ}


def main(argv):
    r = analyse()
    for name, b in r["binaries"].items():
        if b is None:
            print("%s: absent" % name)
            continue
        print("%s: %d bytes" % (name, b["size"]))
        for kind in ("imm", "const32", "word32", "word32le", "float"):
            if b[kind]:
                print("  %-8s %s" % (kind, "  ".join("%s x%d" % (k, len(v)) for k, v in sorted(b[kind].items()))))
        print("  keywords %s" % "  ".join("%s x%d" % kv for kv in sorted(b["keywords"].items())))
    print("gbi vs gbihf, where the counts differ:")
    for kind, k, row in r["gbi_vs_gbihf"]:
        print("  %-8s %-12s %s" % (kind, k, "  ".join("%s %s" % (e, row[e]) for e in EDITIONS)))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(r, f, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
