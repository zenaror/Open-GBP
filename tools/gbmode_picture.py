#!/usr/bin/env python3
"""tools/gbmode_picture.py -- what an OGBPFULL1 sidecar's raw frames hold, in words and numbers: geometry, border, colour (GitHub Issue #148).

    python3 tools/gbmode_picture.py <full.bin> [--json] [--render DIR]

It reads the raw VIDEO-window frames of an OGBPFULL1 sidecar through the FROZEN parser (`tools/vfull.py`: `load()`, `consumed_words()`, word16 = (byte1 << 8) | byte3
in raster order, GBP-VID-003) and reports, per complete sample:

  GEOMETRY   the bounding box of every pixel whose 15 colour bits are not the border colour, and whether the box is the whole 240 x 160 frame;
  BORDER     the border colour (the majority word of the frame's outer ring), whether every pixel outside the box is that word, the border's four widths;
  COLOUR     the distinct words and their counts, decoded under the reading GBP-HW-131 fixes for AGB Mode 3 video (bit 15 flag, bits 14-10 R, 9-5 G, 4-0 B); that the same
             reading holds on the GB-mode path is an INFERENCE, not shown by GBP-HW-131. The bit-15 pixels are reported, never interpreted (U-GBP-034), and the distinct-COLOUR
             count masks bit 15 (a word 0x8000 at pixel (0, 0) is the flag bit alone);
  SCALING    a duplication test, per period 2..12 and per axis: the rate at which a pixel equals its right (or lower) neighbour, by phase inside the box. A nearest-neighbour
             scaler forces one phase of a period to 1.0. EVERY PERIOD IS JUDGED ON ITS OWN: a period whose phases are all at or above 0.95 (or lack MIN_PAIRS comparisons) cannot
             discriminate and is SKIPPED, and the verdict names the periods evaluated and the periods skipped -- NO_PERIODIC_DUPLICATION is printed only when all eleven were
             evaluated and none had a forced phase. A yes is a CANDIDATE, never proof (content can have its own period, RUN 17's checker screen; tile art gives false positives at
             periods 4, 8, 10 and 12), and the test says nothing about a smoothing scaler (extra distinct colours would be its trace: reported beside it).

WHAT IT DOES NOT DO. It decides nothing about what a television showed, the colours' fidelity to the game (no oracle exists for retail content), the VI/XFB path, or timing.
It NEVER writes an image into the repository: `--render` is refused unless DIR is inside captures/local/ or build/analysis/ (both ignored by Git); a rendered frame of a
retail game is a private derived artefact. The verdicts of the family's own tools on retail content (`tools/vfull.py analyse`, `tools/vindex.py sidecar`,
`tools/vvi.py`) are INCONCLUSIVE BY CONSTRUCTION -- their oracle is a coordinate stimulus -- and are not rescued here.
"""
import json
import os
import struct
import sys
import zlib
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import vfull  # noqa: E402

W, H = 240, 160
PERIODS = range(2, 13)
FORCED = 0.99          # a phase at or above this rate is "forced equal"
UNIFORM = 0.95         # the test cannot discriminate when even the lowest phase is at or above this
MIN_PAIRS = 200        # comparisons a phase needs before its rate is read
ALLOWED_RENDER_ROOTS = (os.path.join(ROOT, "captures", "local"), os.path.join(ROOT, "build", "analysis"))


def pixels(raw):
    w = vfull.consumed_words(raw)
    return [w[y * W:(y + 1) * W] for y in range(H)]


def rgb5(word):
    return ((word >> 10) & 31, (word >> 5) & 31, word & 31)


def border_word(px):
    ring = [px[0][x] for x in range(W)] + [px[H - 1][x] for x in range(W)] + [px[y][0] for y in range(H)] + [px[y][W - 1] for y in range(H)]
    ring = [v & 0x7FFF for v in ring]
    return Counter(ring).most_common(1)[0][0]


def bbox_of(px, bw):
    xs, ys = [], []
    for y in range(H):
        row = px[y]
        for x in range(W):
            if (row[x] & 0x7FFF) != bw:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def phase_rates(px, box, axis, m):
    x0, y0, x1, y1 = box
    eq, tot = [0] * m, [0] * m
    if axis == "col":
        for y in range(y0, y1 + 1):
            row = px[y]
            for x in range(x0, x1):
                k = (x - x0) % m
                tot[k] += 1
                eq[k] += (row[x] & 0x7FFF) == (row[x + 1] & 0x7FFF)
    else:
        for y in range(y0, y1):
            a, b = px[y], px[y + 1]
            k = (y - y0) % m
            for x in range(x0, x1 + 1):
                tot[k] += 1
                eq[k] += (a[x] & 0x7FFF) == (b[x] & 0x7FFF)
    return [(e / t if t >= MIN_PAIRS else None) for e, t in zip(eq, tot)]


def scaling(px, box):
    """Per axis, each period judged on its own. verdict: DUPLICATION_AT_PERIOD_<m>_.. (some evaluated period has a forced phase), NOT_EVALUABLE (no period evaluated),
    NO_PERIODIC_DUPLICATION (all periods evaluated, none forced), or PARTIAL_NO_DUPLICATION (some periods evaluated and clean, others skipped: never read as a clean no)."""
    out = {}
    for axis in ("col", "row"):
        found, evaluated, skipped, rates = [], [], [], {}
        for m in PERIODS:
            r = phase_rates(px, box, axis, m)
            if any(v is None for v in r) or min(r) >= UNIFORM:
                skipped.append(m)
                continue
            evaluated.append(m)
            rates[m] = [round(v, 3) for v in r]
            if max(r) >= FORCED:
                found.append(m)
        if found:
            verdict = "DUPLICATION_AT_PERIOD_" + "_".join(map(str, found))
        elif not evaluated:
            verdict = "NOT_EVALUABLE"
        elif skipped:
            verdict = "PARTIAL_NO_DUPLICATION"
        else:
            verdict = "NO_PERIODIC_DUPLICATION"
        out[axis] = {"verdict": verdict, "evaluated": evaluated, "skipped": skipped, "rates": rates}
    return out


def analyse_frame(raw):
    px = pixels(raw)
    bw = border_word(px)
    box = bbox_of(px, bw)
    words = Counter(v for row in px for v in row)
    b15 = [(x, y) for y in range(H) for x in range(W) if px[y][x] & 0x8000]
    res = {"border_word": bw, "bbox": box, "distinct_words": len(words), "distinct_colours": len(set(v & 0x7FFF for v in words)),
           "colours": [{"word": v, "count": n, "rgb5": rgb5(v & 0x7FFF)} for v, n in words.most_common()],
           "bit15_pixels": b15[:8], "bit15_count": len(b15)}
    if box is None:
        res.update({"size": None, "border": None, "outside_is_border": True, "scaling": None})
        return res
    x0, y0, x1, y1 = box
    res["size"] = (x1 - x0 + 1, y1 - y0 + 1)
    res["border"] = {"left": x0, "top": y0, "right": W - 1 - x1, "bottom": H - 1 - y1}
    out_ok = all((px[y][x] & 0x7FFF) == bw for y in range(H) for x in range(W) if not (x0 <= x <= x1 and y0 <= y <= y1))
    res["outside_is_border"] = out_ok
    res["scaling"] = scaling(px, box)
    res["inside_border_word_pixels"] = sum(1 for y in range(y0, y1 + 1) for x in range(x0, x1 + 1) if (px[y][x] & 0x7FFF) == bw)
    return res


def analyse(path):
    info = vfull.load(path)
    frames = []
    for r in info["records"]:
        if r["state"] != 2:
            frames.append({"sample": r["sample_index"], "frame_index": r["frame_index"], "state": r["state"], "skipped": True})
            continue
        a = analyse_frame(r["raw"])
        a.update({"sample": r["sample_index"], "frame_index": r["frame_index"], "state": r["state"], "skipped": False})
        frames.append(a)
    done = [f for f in frames if not f["skipped"]]
    boxes = [f["bbox"] for f in done if f["bbox"]]
    union = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)) if boxes else None
    return {"identity": (info["test_id"], info["build_id"], info["commit"]), "records": info["records_n"], "frames": frames, "union_bbox": union,
            "border_words": sorted({f["border_word"] for f in done}), "all_outside_is_border": all(f["outside_is_border"] for f in done)}


def render(path, outdir):
    """Write PNGs of the frames, refused outside the ignored roots."""
    real = os.path.realpath(outdir)
    if not any(real == os.path.realpath(r) or real.startswith(os.path.realpath(r) + os.sep) for r in ALLOWED_RENDER_ROOTS):
        raise SystemExit("refused: a rendered frame of retail content is written only under captures/local/ or build/analysis/ (both ignored by Git)")
    os.makedirs(real, exist_ok=True)
    info = vfull.load(path)
    for r in info["records"]:
        if r["state"] != 2:
            continue
        px = pixels(r["raw"])
        rows = []
        for y in range(H):
            row = bytearray()
            for x in range(W):
                for c in rgb5(px[y][x] & 0x7FFF):
                    row.append((c << 3) | (c >> 2))
            rows.append(bytes(row))
        raw = b"".join(b"\0" + r_ for r_ in rows)

        def chunk(t, d):
            return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
        with open(os.path.join(real, "sample%d.png" % r["sample_index"]), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def format_report(a):
    o = ["GBMODE PICTURE (GitHub Issue #148)  %s / %s / %s   %d records" % (a["identity"] + (a["records"],))]
    for f in a["frames"]:
        if f["skipped"]:
            o.append("  sample %d frame_index %d: state %d, not analysed (not COMPLETE)" % (f["sample"], f["frame_index"], f["state"]))
            continue
        head = "  sample %d frame_index %d:" % (f["sample"], f["frame_index"])
        if f["bbox"] is None:
            o.append(head + " no pixel differs from the border word 0x%04x (an entirely uniform frame); distinct words %d (colours %d)" % (f["border_word"], f["distinct_words"], f["distinct_colours"]))
        else:
            o.append(head + " box x %d..%d y %d..%d = %d x %d, border L%d T%d R%d B%d, border word 0x%04x, outside the box everything is the border word: %s" % (
                f["bbox"][0], f["bbox"][2], f["bbox"][1], f["bbox"][3], f["size"][0], f["size"][1], f["border"]["left"], f["border"]["top"], f["border"]["right"], f["border"]["bottom"],
                f["border_word"], f["outside_is_border"]))
            o.append("      border-word pixels inside the box %d; distinct words %d (colours %d); scaling: columns %s, rows %s" % (
                f["inside_border_word_pixels"], f["distinct_words"], f["distinct_colours"], f["scaling"]["col"]["verdict"], f["scaling"]["row"]["verdict"]))
            for ax in ("col", "row"):
                if f["scaling"][ax]["skipped"]:
                    o.append("      %s periods skipped (cannot discriminate): %s" % (ax, f["scaling"][ax]["skipped"]))
        top = ", ".join("0x%04x x%d (R%d G%d B%d)" % (c["word"], c["count"], c["rgb5"][0], c["rgb5"][1], c["rgb5"][2]) for c in f["colours"][:6])
        o.append("      colours (most frequent first; R,G,B = bits 14-10, 9-5, 4-0): " + top)
        o.append("      bit-15 pixels: %d at %s" % (f["bit15_count"], f["bit15_pixels"]))
    o.append("  UNION of the boxes: %s; border words seen: %s; every pixel outside every box is its frame's border word: %s" % (
        a["union_bbox"], ", ".join("0x%04x" % v for v in a["border_words"]), a["all_outside_is_border"]))
    return "\n".join(o)


def main(argv):
    args = argv[1:]
    render_dir = None
    if "--render" in args:
        i = args.index("--render")
        if i + 1 >= len(args):
            print("usage: gbmode_picture.py <full.bin> [--json] [--render DIR]")
            return 2
        render_dir = args[i + 1]
        del args[i:i + 2]
    js = "--json" in args
    args = [x for x in args if x != "--json"]
    if len(args) != 1:
        print("usage: gbmode_picture.py <full.bin> [--json] [--render DIR]")
        return 2
    a = analyse(args[0])
    if render_dir:
        render(args[0], render_dir)
    print(json.dumps(a, indent=1, default=list) if js else format_report(a))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
