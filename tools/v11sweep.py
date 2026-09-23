"""§V11's constructions — GBP-AUDIO-003, the amplitude sweep.

FROZEN BEFORE THE ROM EXISTS, and before any data does. This module is written
from §V11's text and nothing in it may be adjusted once a run has happened: the
fourth outing of the discipline `tools/v7611.py`, `tools/v8audio.py` and
`tools/v9tone.py` established, and the first where the instrument, the run AND
the two competing models are all written before any of them exist. A test diffs
this file against the commit that introduced it.

WHAT IS HERE, AND WHY EACH PIECE IS SEPARATE.

  QUESTION V  the amplitude sweep. Does the duty of the 256-byte cell move with
              the envelope, in the order fixed in §V11.4?
  QUESTION F  the frequency ladder. Do the across-block periods hold the ratios
              the four notes predict (§V11.5)?
  QUESTION E  the alphabet. Do the block's BYTE LEVELS move with the schedule
              instead of the duty (§V11.6)?

**Neither verdict consults the other's evidence** — §V6.13's rule, and the
reason each question gets its own function with its own inputs.

THE ONE THING THIS MODULE REFUSES TO BE TOLD. Which schedule a run exercised is
**derived** from the `KEY` record and never declared: `gbp_awin_anchor` carries
`keys` per window, so a window armed by the wrong button is **refused** rather
than read as the other question. A and B are adjacent on the pad and the
consequence of confusing them is silent, which is exactly the class of error a
frozen construction is for.

Nothing here reads a device, a clock or a file. Synthetic vectors only.
"""

# --------------------------------------------------------------- the constants
# §V11.3's two schedules. THE ORDER IS PART OF THE EXPERIMENT: both put the
# already-measured point FIRST, because U-GBP-038 says window 1 is the one at
# risk of carrying nothing (§V10.6.3).

AMPLITUDES = (15, 11, 7, 3)              # SOUND1CNT_H envelope initial volume
FREQUENCY_N = (1024, 1792, 1536, 1920)   # SOUND1CNT_X's n; f = 131072 / (2048 - n)

# §V10.3.2: RUN 31 measured +-0.125 about the resting 0.500 at initial volume 15.
ANCHOR_VOLUME = 15
ANCHOR_DEVIATION = 0.125

# §V7.8.6 / GBP-HW-301. One drained block is one sample.
DRAIN_BLOCKS_PER_S = 4096.0
BLOCKS_PER_WINDOW = 256

# §V11.9. NOT a parameter: the largest onset yet observed is 18.32 ms = 75.0
# blocks (RUN 30 press 2); 96 blocks is 23.4375 ms, 28 % beyond it. RUN 31's own
# onset was block 44. Fixed HERE so it cannot be chosen after the data, which is
# the one decision §V9.15.5 had to name as post-hoc.
ONSET_SLICE_BLOCKS = 96

# §V11.7's tolerances, and nothing else decides anything.
RESTING_DUTY = 0.5
BYTE = 1.0 / 256.0                  # the duty's quantum: one byte of the cell
FLAT_TOLERANCE = 1.0 * BYTE         # within one byte of rest, in every block
ORDER_SLACK = 1.0 * BYTE            # a non-increasing step may go up by one byte
MOVE_SPAN_MIN = 8.0 * BYTE          # first minus last deviation, to refuse "all equal"
RATIO_TOLERANCE = 0.10              # §V9.8's, unchanged
MIN_RISING_EDGES = 3                # §V8.5.3's, unchanged
UNIFORMITY_MIN = 0.90               # §V9.8's, unchanged
LEVEL_SPAN_MIN = 2                  # QUESTION E: byte units, first minus last

# The GBA logical key bits the anchor records (gbp_input.h: A is key 0, B is 1).
KEY_A = 0x0001
KEY_B = 0x0002
AXIS_OF_KEY = {KEY_A: "F", KEY_B: "V"}   # A walks FREQUENCY, B walks VOLUME


def frequency_hz(n):
    """GBATEK. All four (2048 - n) are powers of two, so all four are exact."""
    return 131072.0 / (2048 - n)


def blocks_per_period(n):
    return DRAIN_BLOCKS_PER_S / frequency_hz(n)


# ------------------------------------------------------------- the two models
# §V11.4's competing predictions. BOTH are anchored on the measured deviation at
# volume 15, so neither depends on an absolute scale nobody has measured: what
# is being compared is the SHAPE of the fall, not its size.

def deviation_linear(volume, anchor=ANCHOR_DEVIATION):
    """H-PWM as stated: the duty's deviation is proportional to the magnitude,
    and the magnitude is proportional to the envelope's initial volume."""
    return anchor * (float(volume) / float(ANCHOR_VOLUME))


def deviation_compressive(volume, anchor=ANCHOR_DEVIATION):
    """The plausible competitor: a companding path. log2(1+V) normalised so that
    volume 15 gives the anchor exactly, which is what makes the two models
    coincide at the anchor and differ everywhere else."""
    import math
    return anchor * (math.log(1.0 + float(volume), 2.0) /
                     math.log(1.0 + float(ANCHOR_VOLUME), 2.0))


def model_separation_bytes(volumes=AMPLITUDES):
    """How far apart the two models are, in bytes of the 256-byte cell, at every
    volume that is not the anchor. §V11.4 claims >= 5 at every such point and
    > 9 at two of them; a test asserts that rather than trusting the prose, so
    an edit that narrows the experiment fails instead of weakening it quietly.
    """
    out = {}
    for v in volumes:
        if v == ANCHOR_VOLUME:
            continue
        out[v] = abs(deviation_linear(v) - deviation_compressive(v)) / BYTE
    return out


def fit_intercept(volumes, deviations):
    """§V11.4's NULL: a least-squares line through (volume, deviation). H-PWM
    linear predicts it passes through the origin, so the intercept is the null
    test AND IT COSTS NO WINDOW. Returns (slope, intercept); the intercept is
    reported in duty units, and in bytes by dividing by BYTE.

    THE REASON THE NULL IS NOT A FIFTH WINDOW: a window at volume 0 and a window
    that has not begun carrying (U-GBP-038) are the same picture -- flat, no
    edges. A design in which a window PREDICTS the failure signature cannot tell
    the two apart, so no window may predict it. See is_flat().
    """
    n = len(volumes)
    if n < 2 or n != len(deviations):
        return None
    mx = sum(volumes) / float(n)
    my = sum(deviations) / float(n)
    sxx = sum((x - mx) ** 2 for x in volumes)
    if sxx == 0.0:
        return None
    sxy = sum((volumes[i] - mx) * (deviations[i] - my) for i in range(n))
    slope = sxy / sxx
    return slope, my - slope * mx


# ------------------------------------------------------------ reading a window

def duty(block):
    """RUN 31's definition, unchanged (tests/host/test_run31.py): the fraction of
    the block's bytes above the midpoint of its own extremes."""
    lo, hi = min(block), max(block)
    mid = (lo + hi) / 2.0
    return sum(1 for x in block if x > mid) / float(len(block))


def alphabet(blocks):
    """QUESTION E's quantity: the distinct byte values a window contains. RUN 30
    held {00, 01, FE, FF} and RUN 31 {03, 07, FC}; if the duty holds at 0.500
    while THIS moves, the cell carries magnitude in its LEVELS."""
    s = set()
    for b in blocks:
        s.update(b)
    return sorted(s)


def level_span(blocks):
    a = alphabet(blocks)
    return (a[-1] - a[0]) if a else 0


def sliced(blocks, onset=ONSET_SLICE_BLOCKS):
    """§V11.9. The first `onset` blocks of a press window are discarded because
    the AGB has not reacted yet. FIXED, never chosen from the data."""
    return list(blocks[onset:])


def is_degenerate(blocks):
    """A block with ONE distinct byte value has no duty at all: the definition
    divides a block at the midpoint of its own extremes, and with lo == hi there
    is no midpoint to divide it at. A window of such blocks is reported as
    NO CELL -- neither a carriage failure nor a reading. It would be a finding in
    its own right, because every window observed so far (RUN 30, RUN 31) has had
    a two-level 256-byte cell."""
    return all(min(b) == max(b) for b in blocks)


def is_flat(series, tol=FLAT_TOLERANCE):
    """Every per-block duty within `tol` of rest. §V11.4: NO SCHEDULE ENTRY MAY
    PREDICT THIS, so a flat window is never a reading -- see classify_window."""
    return all(abs(x - RESTING_DUTY) <= tol for x in series)


def modal_levels(series):
    """The two duties a square wave spends its time at, as the most common value
    below rest and the most common above it. Returns (low, high, n_low, n_high)
    or None when the series does not have two sides."""
    lo = [x for x in series if x < RESTING_DUTY - FLAT_TOLERANCE]
    hi = [x for x in series if x > RESTING_DUTY + FLAT_TOLERANCE]
    if not lo or not hi:
        return None

    def mode(xs):
        counts = {}
        for x in xs:
            counts[x] = counts.get(x, 0) + 1
        best = max(counts.items(), key=lambda kv: (kv[1], -abs(kv[0] - RESTING_DUTY)))
        return best[0], best[1]

    l, nl = mode(lo)
    h, nh = mode(hi)
    return l, h, nl, nh


def observed_deviation(series):
    """Half the separation between the two modal levels -- the quantity the two
    models predict. None when the window has no two sides."""
    m = modal_levels(series)
    return None if m is None else (m[1] - m[0]) / 2.0


def rising_edges(series):
    """Indices where the series crosses rest upward. §V9.8's estimator works on
    these and on nothing else."""
    out = []
    for i in range(1, len(series)):
        if series[i - 1] <= RESTING_DUTY < series[i]:
            out.append(i)
    return out


def window_period(series):
    """§V9.8's rule, unchanged and inherited: at least three rising edges, the
    MEDIAN inter-edge interval, and at least 90 % of intervals equal to it."""
    e = rising_edges(series)
    if len(e) < MIN_RISING_EDGES:
        return {"period": None, "edges": len(e), "uniformity": 0.0,
                "why": "fewer than %d rising edges" % MIN_RISING_EDGES}
    gaps = [e[i + 1] - e[i] for i in range(len(e) - 1)]
    s = sorted(gaps)
    med = s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2.0
    u = sum(1 for g in gaps if g == med) / float(len(gaps))
    if u < UNIFORMITY_MIN:
        return {"period": None, "edges": len(e), "uniformity": u,
                "why": "uniformity below %.2f" % UNIFORMITY_MIN}
    return {"period": med, "edges": len(e), "uniformity": u, "why": None}


def classify_window(blocks):
    """One press window, reduced to what the three questions read. A FLAT window
    is reported as CARRIAGE FAILURE and never as a reading, because §V11.4's
    schedule contains no entry that predicts flat."""
    s = sliced(blocks)
    series = [duty(b) for b in s]
    out = {"blocks_used": len(s), "series": series,
           "alphabet": alphabet(s), "level_span": level_span(s)}
    if is_degenerate(s):
        out["state"] = "NO CELL"                # the two-level cell itself is absent
        out["deviation"] = None
        out["period"] = None
        return out
    if is_flat(series):
        out["state"] = "CARRIAGE FAILURE"       # U-GBP-038's signature, never volume 0
        out["deviation"] = None
        out["period"] = None
        return out
    out["state"] = "CARRIES"
    out["deviation"] = observed_deviation(series)
    out["period"] = window_period(series)["period"]
    out["period_detail"] = window_period(series)
    return out


# -------------------------------------------------- which schedule, DERIVED

def axis_of_window(keys):
    """The axis a window was armed on, from the anchor's own `keys`. Never
    declared, never inferred from the press ordinal."""
    if keys in AXIS_OF_KEY:
        return AXIS_OF_KEY[keys]
    return None          # zero, several bits, or a key that is neither A nor B


def derive_schedule(anchor_keys):
    """`anchor_keys` are the PRESS windows' keys in press order. Returns the
    axis every window agrees on, or 'MIXED', or 'UNKNOWN'."""
    axes = [axis_of_window(k) for k in anchor_keys]
    if not axes or any(a is None for a in axes):
        return "UNKNOWN"
    return axes[0] if len(set(axes)) == 1 else "MIXED"


def refusals(anchor_keys, axis):
    """The window ordinals (1-based) whose bit does not match the axis they are
    about to be read under. A question hands these back and answers NOTHING:
    a run where the wrong button was pressed must fail loudly, because A and B
    are adjacent and reading one as the other is silent."""
    bad = []
    for i, k in enumerate(anchor_keys):
        if axis_of_window(k) != axis:
            bad.append((i + 1, k))
    return bad


# ------------------------------------------------------------- the questions

def question_V(windows, anchor_keys):
    """§V11.4 — THE AMPLITUDE SWEEP, read under the B schedule.

    `windows` are the press windows' block lists in press order; `anchor_keys`
    their anchors' `keys`. The verdict is on the ORDER; the model comparison and
    the intercept are MEASUREMENTS reported beside it and decide nothing.
    """
    bad = refusals(anchor_keys, "V")
    if bad:
        return {"verdict": "REFUSED",
                "why": "windows %s were not armed by B" % [b[0] for b in bad],
                "refused": bad}
    cls = [classify_window(w) for w in windows]
    nocell = [i + 1 for i, c in enumerate(cls) if c["state"] == "NO CELL"]
    if nocell:
        return {"verdict": "INCONCLUSIVE", "windows": cls,
                "why": "windows %s have no two-level cell at all, which every window "
                       "observed so far has had -- a finding, and not this question's "
                       "answer" % nocell}
    failures = [i + 1 for i, c in enumerate(cls) if c["state"] == "CARRIAGE FAILURE"]
    if failures:
        return {"verdict": "INCONCLUSIVE", "windows": cls,
                "why": "windows %s carried nothing (U-GBP-038), and no schedule "
                       "entry predicts a flat window" % failures}
    devs = [c["deviation"] for c in cls]
    if any(d is None for d in devs):
        return {"verdict": "INCONCLUSIVE", "windows": cls,
                "why": "a window has no two levels to measure a deviation from"}
    vols = list(AMPLITUDES[:len(devs)])
    span = devs[0] - devs[-1]
    ordered = all(devs[i] >= devs[i + 1] - ORDER_SLACK for i in range(len(devs) - 1))
    if span < MOVE_SPAN_MIN:
        verdict = "DOES NOT MOVE"
    elif not ordered:
        verdict = "MOVES, NOT ORDERED"
    else:
        verdict = "ORDERED"
    fit = fit_intercept(vols, devs)
    out = {"verdict": verdict, "windows": cls, "volumes": vols, "deviations": devs,
           "span_bytes": span / BYTE, "ordered": ordered,
           "intercept_bytes": None if fit is None else fit[1] / BYTE,
           "slope": None if fit is None else fit[0]}
    out["models"] = compare_models(vols, devs)
    return out


def compare_models(volumes, deviations):
    """A MEASUREMENT beside QUESTION V's verdict, never a gate. Both models are
    re-anchored on the window that actually measured the anchor volume, so the
    comparison is of the SHAPE of the fall and not of an absolute scale."""
    if ANCHOR_VOLUME not in volumes:
        return {"why": "the anchor volume was not among the windows"}
    a = deviations[volumes.index(ANCHOR_VOLUME)]
    err = {}
    for name, f in (("linear", deviation_linear), ("compressive", deviation_compressive)):
        err[name] = sum(abs(deviations[i] - f(volumes[i], anchor=a))
                        for i in range(len(volumes))) / BYTE
    better = min(err, key=lambda k: err[k])
    return {"abs_error_bytes": err, "closer": better,
            "margin_bytes": abs(err["linear"] - err["compressive"])}


def question_F(windows, anchor_keys):
    """§V11.5 — THE FREQUENCY LADDER, read under the A schedule. Every pair of
    windows with a period must hold the ratio their two notes predict, within
    §V9.8's 10 %."""
    bad = refusals(anchor_keys, "F")
    if bad:
        return {"verdict": "REFUSED",
                "why": "windows %s were not armed by A" % [b[0] for b in bad],
                "refused": bad}
    cls = [classify_window(w) for w in windows]
    nocell = [i + 1 for i, c in enumerate(cls) if c["state"] == "NO CELL"]
    if nocell:
        return {"verdict": "INCONCLUSIVE", "windows": cls,
                "why": "windows %s have no two-level cell at all, which every window "
                       "observed so far has had -- a finding, and not this question's "
                       "answer" % nocell}
    failures = [i + 1 for i, c in enumerate(cls) if c["state"] == "CARRIAGE FAILURE"]
    if failures:
        return {"verdict": "INCONCLUSIVE", "windows": cls,
                "why": "windows %s carried nothing" % failures}
    got = [c["period"] for c in cls]
    want = [blocks_per_period(n) for n in FREQUENCY_N[:len(got)]]
    pairs, bad_pairs = [], []
    for i in range(len(got)):
        for j in range(i + 1, len(got)):
            if got[i] is None or got[j] is None or got[j] == 0:
                continue
            r, p = got[i] / float(got[j]), want[i] / want[j]
            pairs.append({"i": i + 1, "j": j + 1, "measured": r, "predicted": p})
            if abs(r - p) > RATIO_TOLERANCE * p:
                bad_pairs.append(pairs[-1])
    if not pairs:
        verdict = "INCONCLUSIVE"
    elif bad_pairs:
        verdict = "RATIOS DO NOT HOLD"
    else:
        verdict = "RATIOS HOLD"
    return {"verdict": verdict, "windows": cls, "periods": got, "predicted": want,
            "pairs": pairs, "failed_pairs": bad_pairs,
            "absent": [i + 1 for i, g in enumerate(got) if g is None]}


def question_E(windows, anchor_keys, axis):
    """§V11.6 — THE ALPHABET, its own reading with its own gate. It does NOT
    consult QUESTION V's verdict: a duty that holds at 0.500 while the LEVELS
    move is a direction, not a null result, and it has to be able to say so on
    its own evidence."""
    bad = refusals(anchor_keys, axis)
    if bad:
        return {"verdict": "REFUSED",
                "why": "windows %s do not match the %s schedule" % ([b[0] for b in bad], axis),
                "refused": bad}
    spans = [level_span(sliced(w)) for w in windows]
    alphas = [alphabet(sliced(w)) for w in windows]
    if len(set(tuple(a) for a in alphas)) == 1:
        verdict = "LEVELS STABLE"
    else:
        span = spans[0] - spans[-1]
        ordered = all(spans[i] >= spans[i + 1] for i in range(len(spans) - 1))
        if span < LEVEL_SPAN_MIN:
            verdict = "LEVELS DIFFER, NOT ORDERED"
        else:
            verdict = "LEVELS MOVE" if ordered else "LEVELS DIFFER, NOT ORDERED"
    return {"verdict": verdict, "alphabets": alphas, "spans": spans}
