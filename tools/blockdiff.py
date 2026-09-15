#!/usr/bin/env python3
"""
blockdiff — deterministic byte/word analysis of 32-byte GBP blocks.

    tools/blockdiff.py <device-log>            analyze every RAW/TESTR block, pair MODE A/B
    tools/blockdiff.py --hex <A> [<B>]         analyze one block (64 hex digits), or diff two
    tools/blockdiff.py --pair <log1> <log2>    byte-by-byte table of every block of log1 vs log2
                                               (offset, value in log1, value in log2, xor);
                                               exit 1 if the two logs are block-for-block identical

For each block: bytes at every offset, u16/u32 big-endian views, the set of
distinct byte values with their offsets, and the smallest period p
(1,2,4,8,16) for which block[i] == block[i+p] for all i, plus the offsets
that break the next-larger structure ("anomalies"). For a pair: XOR per
offset and the differing bit positions. Nothing is normalized.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probelog  # noqa: E402


def period(b: bytes):
    for p in (1, 2, 4, 8, 16):
        if all(b[i] == b[i + p] for i in range(len(b) - p)):
            return p
    return None


def period_ignoring(b: bytes, skip):
    """Smallest period when the offsets in `skip` are ignored."""
    for p in (1, 2, 4, 8, 16):
        if all(b[i] == b[i + p] for i in range(len(b) - p) if i not in skip and i + p not in skip):
            return p
    return None


def anomalies(b: bytes):
    """Offsets whose byte differs from the value that the rest of the block
    agrees on (majority per offset-class of period 4, i.e. i mod 4)."""
    out = []
    for cls in range(4):
        vals = [b[i] for i in range(cls, len(b), 4)]
        maj = max(set(vals), key=vals.count)
        for i in range(cls, len(b), 4):
            if b[i] != maj:
                out.append((i, b[i], maj))
    return out


def describe(name: str, b: bytes) -> str:
    lines = []
    lines.append("%s: %s" % (name, b.hex()))
    lines.append("  u8  : " + " ".join("%02x" % x for x in b))
    lines.append("  u16 : " + " ".join("%04x" % int.from_bytes(b[i:i + 2], "big") for i in range(0, 32, 2)))
    lines.append("  u32 : " + " ".join("%08x" % int.from_bytes(b[i:i + 4], "big") for i in range(0, 32, 4)))
    vals = {}
    for i, x in enumerate(b):
        vals.setdefault(x, []).append(i)
    lines.append("  distinct: " + ", ".join("%02x@%s" % (v, o) for v, o in sorted(vals.items())))
    p = period(b)
    an = anomalies(b)
    lines.append("  period: %s%s" % (p, "" if p else " (none <=16)"))
    if an:
        lines.append("  anomalies vs per-offset-class majority: " +
                     ", ".join("off %d = %02x (class value %02x, extra bits %02x, missing bits %02x)"
                               % (i, v, m, v & ~m & 0xff, m & ~v & 0xff) for i, v, m in an))
        lines.append("  period ignoring anomalies: %s" % period_ignoring(b, {i for i, _, _ in an}))
    return "\n".join(lines)


def diff(name: str, a: bytes, b: bytes) -> str:
    lines = ["%s: A vs B" % name]
    x = bytes(p ^ q for p, q in zip(a, b))
    lines.append("  xor : " + " ".join("%02x" % v for v in x))
    dif = [(i, a[i], b[i]) for i in range(32) if a[i] != b[i]]
    if not dif:
        lines.append("  identical")
    else:
        lines.append("  differing offsets: " + ", ".join(
            "%d(%02x->%02x bits %s)" % (i, p, q, ",".join(str(k) for k in range(8) if (p ^ q) >> k & 1))
            for i, p, q in dif))
    return "\n".join(lines)


def blocks_from_log(path):
    header, records = probelog.parse_file(path)
    out = {}   # (mode, label) -> bytes
    seen = {}
    for r in records:
        f = r["fields"]
        if r["kind"] == "RAW" and f.get("data_bytes"):
            key = (f["mode"], "RAW idx=%s" % f["idx"])
            n = seen.get(key, 0) + 1
            seen[key] = n
            out[(f["mode"], "RAW idx=%s #%d" % (f["idx"], n))] = f["data_bytes"]
        elif r["kind"] == "TESTR" and f.get("data_bytes"):
            out[(f["mode"], "TESTR pattern=%s expect=%s" % (f["pattern"], f["expect"]))] = f["data_bytes"]
    return out


def pair_table(blocks1, blocks2, name1="with_GBP", name2="without_GBP"):
    """Rows: (label, offset, v1, v2, xor). Returns (rows, identical_blocks, differing_blocks)."""
    rows, same, diff_ = [], [], []
    for key in blocks1:
        if key not in blocks2:
            continue
        a, b = blocks1[key], blocks2[key]
        label = "MODE %s %s" % key
        (same if a == b else diff_).append(label)
        for i in range(32):
            rows.append((label, i, a[i], b[i], a[i] ^ b[i]))
    return rows, same, diff_


def format_pair(rows, same, diff_, name1, name2):
    out = ["block                                    off  %-11s %-11s xor" % (name1, name2)]
    last = None
    for label, i, v1, v2, x in rows:
        if label != last:
            out.append("")
            last = label
        out.append("%-40s %3d  %02x          %02x          %02x%s" % (label, i, v1, v2, x, "" if x == 0 else "  *"))
    out.append("")
    out.append("identical blocks: %d  differing blocks: %d" % (len(same), len(diff_)))
    for l in diff_:
        out.append("  differs: " + l)
    return "\n".join(out)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--pair":
        b1, b2 = blocks_from_log(argv[1]), blocks_from_log(argv[2])
        rows, same, diff_ = pair_table(b1, b2)
        print(format_pair(rows, same, diff_, "with_GBP", "without_GBP"))
        return 1 if not diff_ else 0
    if argv[0] == "--hex":
        a = bytes.fromhex(argv[1])
        print(describe("A", a))
        if len(argv) > 2:
            b = bytes.fromhex(argv[2])
            print(describe("B", b))
            print(diff("A/B", a, b))
        return 0
    blocks = blocks_from_log(argv[0])
    labels = []
    for (m, l) in blocks:
        if l not in labels:
            labels.append(l)
    for l in labels:
        for m in ("A", "B"):
            if (m, l) in blocks:
                print(describe("MODE %s %s" % (m, l), blocks[(m, l)]))
        if ("A", l) in blocks and ("B", l) in blocks:
            print(diff(l, blocks[("A", l)], blocks[("B", l)]))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
