#!/usr/bin/env python3
"""
tools/v18block.py — what ONE 4096-byte AUDIO block contains, measured on the archive.

    tools/v18block.py <audio.bin> [--label RUN33]

GitHub Issue #82, HARDWARE_TESTS §V18. Inputs for the continuous-drain
pre-registration, from bytes already owned. It reads an OGBPAW1 sidecar and
reports, per window:

  IDENTITY  how many blocks have sixteen byte-identical 256-byte slices;
  SHAPE     the sixteen slice one-bit counts of every block: FLAT (spread at most
            FLAT_SPREAD bits) or one STEP between two flat plateaus -- or OTHER,
            which is reported, never folded into the first two;
  EDGES     in each PRESS window's sliced region (§V11.9, fixed at 96 blocks): the
            step blocks against the period #80's frozen predictions give
            (`v17pred.predict`, the axis derived from the KEY record exactly as #80
            derived it) -- one edge every P/2 blocks, and the slice index of each;
  ONE SLICE what reading one 256-byte slice instead of the block would give, in
            #81's int16 units (src/audio/gbp_adec.c's exact arithmetic).

DESCRIPTIVE. Nothing here is a gate, and no constant was tuned to reach an answer:
FLAT_SPREAD = 3 is the largest spread any non-step block shows (below it one block
of RUN 34 reads as OTHER). The flat / step split is IDENTICAL for every value from
3 to 61 bits over the whole archive -- the smallest plateau jump anywhere is 62, a
VOLUME change inside a block before a RUN 34 press window's onset slice -- and from
3 to 97 over the control windows plus the sliced regions, where the smallest jump
is 97.5. tests/host/test_v18block.py pins both ranges.
Standard library only; reads the capture, writes nothing.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awinparse  # noqa: E402
import v11sweep   # noqa: E402
import v17pred    # noqa: E402

BLOCK = 4096
SLICES = 16
SLICE = BLOCK // SLICES          # 256
FLAT_SPREAD = 3                  # bits; see the module docstring
FULL = 32767
_PC = [bin(i).count("1") for i in range(256)]


def slice_counts(block):
    """The one-bit count of each of the sixteen 256-byte slices, in slice order."""
    return [sum(_PC[x] for x in block[i * SLICE:(i + 1) * SLICE]) for i in range(SLICES)]


def byte_identical(block):
    """All sixteen slices byte for byte the same."""
    first = block[:SLICE]
    return all(block[i * SLICE:(i + 1) * SLICE] == first for i in range(1, SLICES))


def shape(counts, flat=FLAT_SPREAD):
    """FLAT, one STEP between two flat plateaus, or OTHER. A step's `k` is the first
    slice of the second plateau; `before` / `after` are the plateaus' mean counts."""
    if max(counts) - min(counts) <= flat:
        return {"kind": "flat", "spread": max(counts) - min(counts), "level": sum(counts) / float(SLICES)}
    for k in range(1, SLICES):
        a, b = counts[:k], counts[k:]
        if max(a) - min(a) <= flat and max(b) - min(b) <= flat:
            return {"kind": "step", "k": k, "before": sum(a) / float(len(a)), "after": sum(b) / float(len(b))}
    return {"kind": "other"}


def sample(p, rest_sum, rest_n):
    """#81's decoder (src/audio/gbp_adec.c), the same integers: the int16 sample for a
    block one-bit count p, given the calibration span's summed count and length."""
    num = (rest_n * p - rest_sum) * FULL
    den = 5 * 1024 * rest_n
    q, r = divmod(num, den)                  # floor division, 0 <= r < den
    if 2 * r > den or (2 * r == den and q & 1):
        q += 1
    return max(-FULL, min(FULL, q))


def window_edges(shapes, period, onset=v11sweep.ONSET_SLICE_BLOCKS):
    """The sliced region's step blocks, against an edge every P/2 blocks.

    `ok_spacing`: every gap between consecutive step blocks is exactly P/2.
    `ks`: the set of slice indices at which the steps fall.
    `neighbours_ok`: each step's first plateau equals the previous block's level and
    its second plateau the next block's, within FLAT_SPREAD -- which is what the
    slices being in TIME ORDER predicts, and nothing else here does."""
    half = int(period) // 2
    steps = [i for i in range(onset, len(shapes)) if shapes[i]["kind"] == "step"]
    gaps = [b - a for a, b in zip(steps, steps[1:])]
    nb_ok = True
    for i in steps:
        prev, nxt = shapes[i - 1], shapes[i + 1] if i + 1 < len(shapes) else None
        if prev["kind"] != "flat" or abs(prev["level"] - shapes[i]["before"]) > FLAT_SPREAD:
            nb_ok = False
        if nxt is not None and (nxt["kind"] != "flat" or abs(nxt["level"] - shapes[i]["after"]) > FLAT_SPREAD):
            nb_ok = False
    region = len(shapes) - onset
    return {"half": half, "steps": steps, "n_steps": len(steps), "gaps": sorted(set(gaps)),
            "ok_spacing": bool(steps) and all(g == half for g in gaps),
            "expected_n": (region // half, -(-region // half)),
            "ks": sorted({shapes[i]["k"] for i in steps}),
            "neighbours_ok": nb_ok,
            "other": sum(1 for s in shapes[onset:] if s["kind"] == "other")}


def one_slice_error(blocks, shapes, rest_sum, rest_n, j, onset=v11sweep.ONSET_SLICE_BLOCKS):
    """max |sample(16 * slice_j) - sample(block)| over the sliced region, split by shape."""
    worst = {"flat": 0, "step": 0}
    for b, s in zip(blocks[onset:], shapes[onset:]):
        c = slice_counts(b)
        d = abs(sample(SLICES * c[j], rest_sum, rest_n) - sample(sum(c), rest_sum, rest_n))
        if s["kind"] in worst:
            worst[s["kind"]] = max(worst[s["kind"]], d)
    return worst


def analyse(path):
    _, _, anc, wins = awinparse.load(path)
    press = [a for a in anc if a["kind"] == 1]
    axis = v11sweep.derive_schedule([a["keys"] for a in press])
    periods = [p["period"] for p in v17pred.predict(axis)] if axis in ("F", "V") else [None] * len(press)
    rest_sum = sum(sum(slice_counts(b)) for b in wins[0])
    rest_n = len(wins[0])
    out = {"axis": axis, "windows": []}
    for wi, w in enumerate(wins):
        shapes = [shape(slice_counts(b)) for b in w]
        row = {"index": wi, "kind": anc[wi]["kind"], "blocks": len(w),
               "identical": sum(1 for b in w if byte_identical(b)),
               "flat": sum(1 for s in shapes if s["kind"] == "flat"),
               "step": sum(1 for s in shapes if s["kind"] == "step"),
               "other": sum(1 for s in shapes if s["kind"] == "other"),
               "spreads": [sum(1 for s in shapes if s["kind"] == "flat" and s["spread"] == d)
                           for d in range(FLAT_SPREAD + 1)]}
        if anc[wi]["kind"] == 1:
            period = periods[press.index(anc[wi])]
            row["period"] = period
            row["edges"] = window_edges(shapes, period)
            row["one_slice"] = [one_slice_error(w, shapes, rest_sum, rest_n, j) for j in range(SLICES)]
        out["windows"].append(row)
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    label = argv[argv.index("--label") + 1] if "--label" in argv else os.path.basename(argv[1])
    r = analyse(argv[1])
    print("%s  axis %s" % (label, r["axis"]))
    tot = {"blocks": 0, "identical": 0}
    for w in r["windows"]:
        tot["blocks"] += w["blocks"]
        tot["identical"] += w["identical"]
        line = ("  w%d %-7s identical %3d  flat %3d (spread 0/1/2/3: %s)  step %3d  other %d"
                % (w["index"], "press" if w["kind"] == 1 else "control", w["identical"], w["flat"],
                   "/".join(str(n) for n in w["spreads"]), w["step"], w["other"]))
        print(line)
        if "edges" in w:
            e = w["edges"]
            worst_flat = max(x["flat"] for x in w["one_slice"])
            worst_step = max(x["step"] for x in w["one_slice"])
            print("      sliced: P %g -> an edge every %d; %d steps (expected %d..%d), gaps %s, slice index %s, "
                  "neighbours %s; one slice vs block: flat <= %d, step <= %d int16"
                  % (w["period"], e["half"], e["n_steps"], e["expected_n"][0], e["expected_n"][1], e["gaps"],
                     e["ks"], "match" if e["neighbours_ok"] else "DO NOT MATCH", worst_flat, worst_step))
    print("  run: %d of %d blocks byte-identical" % (tot["identical"], tot["blocks"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
