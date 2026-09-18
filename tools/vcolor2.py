#!/usr/bin/env python3
"""vcolor2.py — the confirmatory analysis contract of GBP-VIDEO-003 / color-0002.

    tools/vcolor2.py analyse <color.bin>        the contract, applied
    tools/vcolor2.py contract                   the contract, printed, with no file

WHY THIS IS A SEPARATE FILE, AND NOT A FLAG ON `tools/vcolor.py`.

`color-0001` ran on 2026-09-18 with a pre-registered acceptance gate: the three
certified frames had to be byte-identical over all 153 600 raw bytes. They were
not — 2125, 2073 and 2137 bytes differ pairwise — and `tools/vcolor.py` refused
the run (GBP-HW-122). Every one of those bytes is in position 0 or 2 of its
four-byte group, which neither reference decoder reads, so the *picture* was
identical in all three frames (GBP-HW-123). That is a good reason to run a
second experiment under a better-aimed gate. It is **not** a reason to re-judge
`color-0001`, because a criterion chosen after seeing the bytes is not a
criterion.

So `tools/vcolor.py` is not touched, not imported *as a policy*, and not given a
new option. Its verdict for `color-0001` must stay reproducible forever, and the
cheapest way to guarantee that is for this contract to live somewhere else.

WHAT IS SHARED, DELIBERATELY. The OGBPCOL1 v1 parser, the eight-value stimulus
and the seven candidate transformations are imported from `vcolor` unchanged.
That is the point: if the hypotheses had been edited to fit what `color-0001`
showed, this file would have to say so, and it cannot — they are the same
objects, frozen at `e10423c`, from before any colour run existed.

WHAT IS DIFFERENT. One thing: the stability gate. See `CONTRACT` below.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vcolor                                                           # noqa: E402

# The experiment this contract was pre-registered for. A file from any other
# build is analysed happily and reported as RETROSPECTIVE: the contract exists
# to judge a run that had not happened when it was written, and it can never
# retroactively confirm one that had.
CONFIRMATORY_BUILD_ID = "color-0002"

WIDTH, HEIGHT = vcolor.WIDTH, vcolor.HEIGHT
CONSUMED_WORDS = WIDTH * HEIGHT                     # 38 400

CONTRACT = """\
GBP-VIDEO-003 / color-0002 — pre-registered analysis contract

A. TRANSPORT RAW DOMAIN — raw group [b0 b1 b2 b3]
   Bytes 0 and 2 are read by neither reference pixel decoder (GBP-VID-003,
   2026-09-16), are physically variable (GBP-HW-058, GBP-HW-070, GBP-HW-126)
   and remain semantically UNKNOWN (U-GBP-029). They are therefore OUTSIDE the
   dependent variable OF THIS EXPERIMENT. This is not a claim that they are
   don't-care in general, and nothing here licenses discarding them: the
   sidecar preserves every byte, and the full-raw comparison is computed and
   REPORTED on every run as a diagnostic.

B. CONSUMED-WORD STABILITY GATE — the acceptance criterion
   word16 = (b1 << 8) | b3, for each of the 240 x 160 = 38400 pixels.
   Require A.word16[x,y] == B.word16[x,y] == C.word16[x,y] for ALL 38400.
   Bit 15 is INSIDE this comparison and is not masked.
   Any difference -> INCONCLUSIVE_CONSUMED_WORD_MISMATCH, and the analysis
   stops before any hypothesis is evaluated.

C. FLAG15 — reported, never interpreted
   flag15 = word16 & 0x8000. Count and coordinates are recorded for A, B and C
   and the three bitmaps must be identical (FLAG15_STABLE). This follows from B
   and is asserted separately anyway. A count of zero is NOT required: physical
   evidence already shows one set flag per frame at x=0,y=0 (GBP-HW-125).
   FLAG15_STABLE means reproducible. It does not mean understood.

D. COLOR MAPPING DOMAIN — only after B and C
   color15 = word16 & 0x7FFF. Each of the eight 30-pixel bars must hold exactly
   one color15 value over its 160 rows, or INCONCLUSIVE_BAR_NOT_UNIFORM.
   The stimulus and the candidate transformations are the pre-registered ones,
   imported unchanged from tools/vcolor.py. Comparison is exact equality on all
   eight values. There is no score and no distance.

E. SUCCESS — every one of these, or it is inconclusive
   1 sidecar parses under OGBPCOL1 v1
   2 exactly 3 certified frames, all with raw preserved
   3 consumed-word equality, 38400 of 38400, across all three pairs
   4 flag15 bitmaps identical across A, B and C
   5 geometry valid: 40 blocks, 160 rows, 240 columns
   6 all eight bars uniform in color15
   7 EXACTLY ONE pre-registered hypothesis reproduces all eight values exactly
   -> CONFIRMED_EXACT_<hypothesis>

F. STANDING
   A confirmatory verdict is reserved for build_id "%s". Any other file is
   reported as RETROSPECTIVE / NON-CONFIRMATORY, whatever it contains.
""" % CONFIRMATORY_BUILD_ID


# ---- B. the consumed-word stability gate ------------------------------------
def consumed_bytes(raw):
    """Bytes 1 and 3 of every group, in order, as one bytes object.

    `raw[1::2]` is exactly that: group g occupies raw[4g..4g+3], so the odd
    indices are 4g+1 and 4g+3 and nothing else. Two frames agree on the picture
    if and only if these agree."""
    return raw[1::2]


def consumed_words(raw):
    """The 38 400 consumed words, bit 15 included."""
    c = consumed_bytes(raw)
    return [(c[i] << 8) | c[i + 1] for i in range(0, len(c), 2)]


def consumed_words_equal(d):
    """THE GATE. Exactly three certified frames, all 38 400 consumed words equal
    across every pair, bit 15 not masked.

    Returns {"ok", "n", "compared", "first_diff", "why"}."""
    n = len(d["cert"])
    r = {"n": n, "compared": 0, "first_diff": None, "ok": False, "why": ""}
    if n != vcolor.MAX_CERT:
        r["why"] = ("%u certified raw frame(s) are present; the design certifies on %u and the "
                    "consumed-word check needs all of them" % (n, vcolor.MAX_CERT))
        return r
    raws = [vcolor.raw_frame(d, i) for i in range(n)]
    for raw in raws:
        if len(raw) != vcolor.FRAME_BYTES:
            r["why"] = "a certified frame carries %u bytes, not %u" % (len(raw), vcolor.FRAME_BYTES)
            return r
    cons = [consumed_bytes(raw) for raw in raws]
    if len(cons[0]) != CONSUMED_WORDS * 2:
        r["why"] = "the consumed projection is %u bytes, expected %u" % (len(cons[0]), CONSUMED_WORDS * 2)
        return r
    r["compared"] = CONSUMED_WORDS
    for k in (1, 2):
        if cons[k] == cons[0]:
            continue
        for j in range(len(cons[0])):
            if cons[k][j] != cons[0][j]:
                w = j // 2                      # which pixel word
                a = (cons[0][w * 2] << 8) | cons[0][w * 2 + 1]
                b = (cons[k][w * 2] << 8) | cons[k][w * 2 + 1]
                r["first_diff"] = {
                    "pair": (0, k), "word_index": w,
                    "x": w % WIDTH, "y": w // WIDTH,
                    "block": (w // WIDTH) // vcolor.ROWS_PER_BLOCK,
                    "byte_in_group": 1 if j % 2 == 0 else 3,
                    "a": a, "b": b,
                    "differs_in_flag15": (a & 0x8000) != (b & 0x8000),
                    "differs_in_color15": (a & 0x7FFF) != (b & 0x7FFF)}
                break
        r["why"] = ("certified frames A and %s disagree on a consumed word, so the picture itself "
                    "was not stable" % "ABC"[k])
        return r
    r["ok"] = True
    return r


# ---- C. flag15, reported and never interpreted ------------------------------
def flag_bitmap(raw):
    """Coordinates where bit 15 of the consumed word is set."""
    c = consumed_bytes(raw)
    return tuple(i for i in range(CONSUMED_WORDS) if c[i * 2] & 0x80)


def flag_stability(d):
    """Counts, coordinates and whether the three bitmaps are identical.

    FLAG15_STABLE is a statement about reproducibility across three frames of one
    run. It carries no meaning for the bit, and this function deliberately offers
    none: the project's status for what bit 15 IS stays where it is."""
    maps = [flag_bitmap(vcolor.raw_frame(d, i)) for i in range(len(d["cert"]))]
    same = all(m == maps[0] for m in maps)
    return {"status": "FLAG15_STABLE" if same and maps else "FLAG15_UNSTABLE",
            "stable": bool(same and maps),
            "counts": [len(m) for m in maps],
            "coords": [[(i % WIDTH, i // WIDTH) for i in m[:8]] for m in maps],
            "zero_required": False,
            "note": "count and position only; no meaning is claimed or implied"}


# ---- A. the full-raw comparison, kept as a REPORTED diagnostic ---------------
def full_raw_diagnostic(d):
    """The gate `color-0001` was judged by, run here as a diagnostic and never as
    a gate. Reporting it on every run is what keeps U-GBP-029 fed."""
    out = {"equal": None, "by_byte_in_group": None, "first_diff": None, "pairs": {}}
    if len(d["cert"]) != vcolor.MAX_CERT:
        return out
    eq = vcolor.certified_raw_equal(d)
    out["equal"] = bool(eq["ok"])
    out["first_diff"] = eq["first_diff"]
    raws = [vcolor.raw_frame(d, i) for i in range(vcolor.MAX_CERT)]
    total = [0, 0, 0, 0]
    for a, b in ((0, 1), (1, 2), (0, 2)):
        c = [0, 0, 0, 0]
        x, y = raws[a], raws[b]
        for i in range(0, len(x), 4):
            for k in range(4):
                if x[i + k] != y[i + k]:
                    c[k] += 1
        out["pairs"]["%s/%s" % ("ABC"[a], "ABC"[b])] = c
        total = [t + v for t, v in zip(total, c)]
    out["by_byte_in_group"] = total
    return out


# ---- the contract, applied --------------------------------------------------
def analyse(d, which=0):
    """The whole decision under the color-0002 contract. Order is fixed: identity,
    then the consumed-word gate, then flag15, then geometry and bars, then the
    hypotheses. Nothing later can rescue something earlier."""
    out = {"contract": "color-0002", "frame": which,
           "stimulus": list(vcolor.STIMULUS), "bar_x": list(vcolor.BAR_X),
           "build_id": d.get("build_id", ""), "test_id": d.get("test_id", ""),
           "commit": d.get("commit", "")}

    # F. standing, decided from the file's own identity and nothing else
    confirmatory = out["build_id"] == CONFIRMATORY_BUILD_ID
    out["confirmatory"] = confirmatory
    out["standing"] = "CONFIRMATORY" if confirmatory else "RETROSPECTIVE / NON-CONFIRMATORY"
    if not confirmatory:
        out["standing_why"] = (
            "this contract was pre-registered for build_id %r; %r predates it, so this run is "
            "analysed as an implementation check of the contract and can confirm nothing"
            % (CONFIRMATORY_BUILD_ID, out["build_id"] or "(unset)"))

    # A. the full-raw comparison, reported first so it is never mistaken for a gate
    out["full_raw_diagnostic"] = full_raw_diagnostic(d)

    if not d["cert"]:
        out["verdict"] = _v(out, "no_certified_frame")
        out["why"] = ("the run preserved no certified frame; the sidecar's refusal counters say "
                      "why, and nothing here can be decided")
        return out

    # B. THE GATE
    gate = consumed_words_equal(d)
    out["consumed_words_equal"] = gate
    if not gate["ok"]:
        out["verdict"] = _v(out, "inconclusive_consumed_word_mismatch"
                            if gate["first_diff"] else "inconclusive_certified_frame_count")
        out["why"] = gate["why"]
        return out

    # C. flag15, asserted separately although B already implies it
    out["flag15"] = flag_stability(d)
    if not out["flag15"]["stable"]:
        out["verdict"] = _v(out, "inconclusive_flag15_unstable")
        out["why"] = ("the flag15 bitmaps differ between certified frames; this cannot happen once "
                      "the consumed words are equal, so it means the two checks disagree and the "
                      "file is not trusted")
        return out

    # D. geometry and bars, on color15 with flag15 already split off
    grid = vcolor.frame_words(d, which)
    if len(grid["words"]) != HEIGHT or any(len(r) != WIDTH for r in grid["words"]):
        out["verdict"] = _v(out, "inconclusive_geometry")
        out["why"] = "the reconstructed frame is not %u x %u" % (WIDTH, HEIGHT)
        return out
    bars = vcolor.bar_values(grid)
    out["bars"] = bars
    nonuniform = [b for b in bars if not b["uniform"]]
    if nonuniform:
        out["verdict"] = _v(out, "inconclusive_bar_not_uniform")
        out["why"] = ("bar %d holds %d distinct colour values at and after %s; the mapping is an "
                      "exact comparison or it is nothing"
                      % (nonuniform[0]["bar"], len(nonuniform[0]["values"]),
                         nonuniform[0]["first_divergence"]))
        return out

    observed = [b["value"] for b in bars]
    out["observed"] = observed
    out["hypotheses"] = vcolor.evaluate(observed)
    survivors = [h for h in out["hypotheses"] if h["all"]]
    out["survivors"] = [h["name"] for h in survivors]

    # orientation: the two permutation-invariant bars must sit where the stimulus
    # put them, or the frame is being read mirrored
    out["orientation"] = {
        "zero_bar": [b["bar"] for b in bars if b["value"] == 0x0000],
        "all_ones_bar": [b["bar"] for b in bars if b["value"] == 0x7FFF],
        "expected_zero_bar": 0, "expected_all_ones_bar": 4}
    out["orientation"]["consistent"] = (out["orientation"]["zero_bar"] == [0] and
                                        out["orientation"]["all_ones_bar"] == [4])

    if len(survivors) == 1:
        out["mapping"] = survivors[0]["name"]
        out["what"] = survivors[0]["what"]
        out["verdict"] = _v(out, "confirmed_exact_" + survivors[0]["name"])
    elif not survivors:
        out["verdict"] = _v(out, "inconclusive_no_hypothesis")
        out["why"] = ("no pre-registered transformation reproduces all eight observed values. The "
                      "raw bytes are preserved; this is a new unknown, not a licence to pick the "
                      "closest fit")
    else:
        out["verdict"] = _v(out, "inconclusive_ambiguous")
        out["why"] = ("%d hypotheses reproduce all eight values; the stimulus did not discriminate "
                      "them" % len(survivors))
    return out


def _v(out, verdict):
    """A retrospective run never produces a verdict string that reads as a
    confirmation, however it is grepped, logged or pasted."""
    if out["confirmatory"] or not verdict.startswith("confirmed_"):
        return verdict
    return "retrospective_" + verdict[len("confirmed_"):]


# ---- the report -------------------------------------------------------------
def analyse_text(d, which=0):
    a = analyse(d, which)
    L = []
    L.append("GBP-VIDEO-003 color analysis - CONTRACT color-0002 (tools/vcolor2.py)")
    L.append("file: test=%s build=%s commit=%s" % (a["test_id"], a["build_id"], a["commit"]))
    L.append("")
    L.append("STANDING: %s" % a["standing"])
    if not a["confirmatory"]:
        L.append("  %s" % a["standing_why"])
    L.append("")

    fr = a["full_raw_diagnostic"]
    L.append("A. TRANSPORT RAW DIAGNOSTIC (reported, never a gate)")
    if fr["equal"] is None:
        L.append("   not computed: this file does not carry three certified raw frames")
    elif fr["equal"]:
        L.append("   the three certified frames are byte-identical over all %u raw bytes"
                 % vcolor.FRAME_BYTES)
    else:
        L.append("   the three certified frames are NOT byte-identical over the full raw frame")
        for k, v in fr["pairs"].items():
            L.append("     %s differing bytes by position in group: b0=%-6d b1=%-6d b2=%-6d b3=%-6d"
                     % (k, v[0], v[1], v[2], v[3]))
        fd = fr["first_diff"]
        if fd:
            L.append("     first at 0x%X - block %d, x=%d, y=%d, byte %d, consumed=%s, %02x vs %02x"
                     % (fd["offset"], fd["block"], fd["x"], fd["y"], fd["byte_in_group"],
                        fd["consumed"], fd["a"], fd["b"]))
        L.append("     bytes 0 and 2 stay UNKNOWN (U-GBP-029); this line is evidence for it,")
        L.append("     not a decision about this experiment")
    L.append("")

    g = a.get("consumed_words_equal")
    L.append("B. CONSUMED-WORD STABILITY GATE  word16 = (b1 << 8) | b3, bit 15 included")
    if g is None:
        L.append("   not reached")
    elif g["ok"]:
        L.append("   PASS: %u of %u words identical in A, B and C" % (g["compared"], CONSUMED_WORDS))
    else:
        L.append("   FAIL: %s" % g["why"])
        fd = g["first_diff"]
        if fd:
            L.append("     first at word %d (x=%d, y=%d, block %d): %04x vs %04x  flag15 differs=%s "
                     "colour differs=%s" % (fd["word_index"], fd["x"], fd["y"], fd["block"],
                                            fd["a"], fd["b"], fd["differs_in_flag15"],
                                            fd["differs_in_color15"]))
    L.append("")

    f = a.get("flag15")
    if f:
        L.append("C. FLAG15  %s" % f["status"])
        L.append("   count per certified frame: %s" % (f["counts"],))
        L.append("   first coordinates: %s" % (f["coords"][0],))
        L.append("   a count of zero is NOT required, and nothing here claims a meaning")
        L.append("")

    if "bars" in a:
        L.append("D. BARS  colour15 with flag15 split off")
        for b in a["bars"]:
            L.append("   bar %d  x=%3d..%3d  %s" % (b["bar"], b["x0"], b["x1"],
                     ("uniform 0x%04X" % b["value"]) if b["uniform"]
                     else "NOT UNIFORM (%d values)" % len(b["values"])))
        L.append("")

    if "observed" in a:
        L.append("   stimulus  " + " ".join("%04X" % v for v in a["stimulus"]))
        L.append("   observed  " + " ".join("%04X" % v for v in a["observed"]))
        L.append("")
        L.append("E. HYPOTHESES  exact equality on all eight, no score")
        for h in a["hypotheses"]:
            L.append("   %-24s %s  %s" % (h["name"], "ALL EIGHT" if h["all"] else
                                          "no (first mismatch at bar %d)" % h["first_mismatch"],
                                          h["what"]))
        L.append("")
        L.append("   orientation consistent: %s" % a["orientation"]["consistent"])
        L.append("")

    L.append("VERDICT: %s" % a["verdict"].upper())
    if a.get("why"):
        L.append("  %s" % a["why"])
    if a["verdict"].startswith("confirmed_"):
        L.append("  %s" % a["what"])
        L.append("  This is a confirmatory result under the contract pre-registered before the run.")
    elif a["verdict"].startswith("retrospective_"):
        L.append("  %s" % a.get("what", ""))
        L.append("  THIS CONFIRMS NOTHING. The contract post-dates this run, so this output is an")
        L.append("  implementation check of the analyser, not evidence about the hypothesis.")
        L.append("  U-GBP-011 is unaffected by it.")
    return "\n".join(L) + "\n"


def main(argv):
    if len(argv) >= 2 and argv[1] == "contract":
        sys.stdout.write(CONTRACT)
        return 0
    if len(argv) < 3 or argv[1] != "analyse":
        sys.stderr.write(__doc__.split("\n\n")[0] + "\n\n"
                         "  tools/vcolor2.py analyse <color.bin>\n"
                         "  tools/vcolor2.py contract\n")
        return 2
    with open(argv[2], "rb") as f:
        d = vcolor.parse(f.read())
    sys.stdout.write(analyse_text(d))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
