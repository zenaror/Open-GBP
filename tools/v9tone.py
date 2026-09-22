#!/usr/bin/env python3
"""
tools/v9tone.py — §V9's constructions, executable, written BEFORE the ROM
exists (GitHub Issue #64, 2026-09-22).

THIS IS THE THIRD OUTING OF THE SAME DISCIPLINE and the second time it has to
survive a surprise. tools/v8audio.py's predictions were written before the
audio image existed; RUN 30 then missed them, and the file was NOT edited --
the premise was named instead (§V8.13.5, U-GBP-037). The same rule governs this
file: it is written from §V9's frozen text, with no run in existence, and it
must not be adjusted to whatever RUN 31 produces. If a construction here looks
wrong against real data, that is a REPORT and a dated amendment.

WHAT MAKES §V9's TEST UNUSUAL, and it is worth stating in the code because it
is why the experiment can work at all: THE VERDICT IS A RATIO BETWEEN TWO
WINDOWS OF THE SAME RUN. period_bytes(F) = R / F for whatever the AUDIO
region's byte rate R is, so period(F1)/period(F2) = F2/F1 exactly and R cancels
out. The test needs no sample rate and assumes none -- which is the only reason
a question about an unmeasured rate can be decided by one session.

The sizing assumption (RUN 30's resting 256-byte square is n = 0, 64.0 Hz) is
used HERE for one thing only: predicting where the periods will land, so the
notes could be chosen. It is labelled, it is U-GBP-037's own inference, and no
verdict below reads it.
"""

SECTION = "docs/research/HARDWARE_TESTS.md §V9"

# ---------------------------------------------------------------- the channel
# GBATEK: f = 131072 / (2048 - n), with the 11-bit n in 0..2047. The lowest note
# the channel has is n = 0 -> 64.0 Hz, and there is nothing below it.
F_NUMERATOR = 131072
N_MAX = 2047
F_MIN_HZ = F_NUMERATOR / 2048.0            # 64.0

# ------------------------------------------------------------------ the notes
# §V9.3.2. A factor of FOUR, not two: a half-period miscount produces exactly a
# factor of 2, so a factor-2 design cannot distinguish "F2 is twice F1" from
# "I counted the other edge". Four is the smallest factor that error cannot make.
N1 = 1024        # 2048 - n = 1024 -> 128.0 Hz exactly
N2 = 1792        # 2048 - n =  256 -> 512.0 Hz exactly
RATIO = 4.0      # the frozen prediction: period(F1) / period(F2)

# §V9.3.1's SIZING ASSUMPTION, used only to predict where the periods land.
# RUN 30's resting square is 256 bytes; IF that is n = 0 then the region carries
# 16 384 bytes per second and period_bytes = (2048 - n) / 8.
SIZING_BYTES_PER_SECOND = 16384.0
BLOCK_BYTES = 4096

# §V9.5's resolvable window: above RUN 30's 8-byte transition runs by 3x, and
# short enough to repeat three times inside one block (§V8.5.3's minimum).
PERIOD_MIN_BYTES = 24
PERIOD_MAX_BYTES = BLOCK_BYTES // 3        # 1365

# --------------------------------------------------------------- §V9.8's bounds
MIN_EDGES_FOR_PERIOD = 3                   # inherited from §V8.5.3, unchanged
RATIO_TOL = 0.10                           # within 10 % of 4.000
UNIFORMITY = 0.90                          # 90 % of intervals equal to the median

PERIOD_ABSENT = "PERIOD ABSENT"
NOT_ESTIMATED = "NOT ESTIMATED (fewer than three rising edges)"


def freq_hz(n):
    """GBATEK's formula. Raises on an n the channel does not have."""
    if not (0 <= n <= N_MAX):
        raise ValueError("n must be 0..%d; %r is not a note this channel has" % (N_MAX, n))
    return F_NUMERATOR / float(2048 - n)


def predicted_period_bytes(n):
    """§V9.3.1: (2048 - n) / 8, UNDER THE SIZING ASSUMPTION and for no other
    purpose. Never read by a verdict."""
    return SIZING_BYTES_PER_SECOND / freq_hz(n)


def notes():
    """The two notes with everything §V9.3.2 states about them, recomputed."""
    out = []
    for label, n in (("F1", N1), ("F2", N2)):
        out.append({"label": label, "n": n, "divisor": 2048 - n, "hz": freq_hz(n),
                    "predicted_period_bytes": predicted_period_bytes(n),
                    "cycles_per_block": BLOCK_BYTES / predicted_period_bytes(n)})
    return out


def choice_is_sound():
    """§V9.3.2's constraints, as a check rather than a claim: both notes exact
    in Hz, both periods inside the resolvable window, both clear of RUN 30's
    resting 256 bytes, and the ratio exactly 4."""
    a, b = notes()
    return {
        "both_exact_hz": all(abs(x["hz"] - round(x["hz"])) < 1e-9 for x in (a, b)),
        "ratio_exact": abs(a["predicted_period_bytes"] / b["predicted_period_bytes"] - RATIO) < 1e-12,
        "both_resolvable": all(PERIOD_MIN_BYTES <= x["predicted_period_bytes"] <= PERIOD_MAX_BYTES
                               for x in (a, b)),
        "both_clear_of_rest": all(abs(x["predicted_period_bytes"] - 256.0) > 1e-9 for x in (a, b)),
        "short_period_over_transition_scale": b["predicted_period_bytes"] / 8.0,
    }


def rate_range_that_still_works():
    """§V9.5: the multiplier k on the sizing assumption for which BOTH periods
    stay inside the resolvable window."""
    a, b = notes()
    k_low = PERIOD_MIN_BYTES / b["predicted_period_bytes"]      # the short one must not shrink below
    k_high = PERIOD_MAX_BYTES / a["predicted_period_bytes"]     # the long one must not grow above
    return {"k_low": k_low, "k_high": k_high,
            "bytes_per_second_low": k_low * SIZING_BYTES_PER_SECOND,
            "bytes_per_second_high": k_high * SIZING_BYTES_PER_SECOND,
            "factor": k_high / k_low}


# ------------------------------------------------------- reading one window
def rising_edges(levels):
    """Indices where a two-level series goes low -> high, split at the midpoint
    of its own range. The first sample cannot be an edge."""
    if not levels:
        return []
    lo, hi = min(levels), max(levels)
    if hi == lo:
        return []
    mid = (hi + lo) / 2.0
    high = [x > mid for x in levels]
    return [i for i in range(1, len(high)) if high[i] and not high[i - 1]]


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def window_period(levels):
    """§V9.8: the MEDIAN inter-edge interval, from at least three rising edges,
    and only when at least 90 % of the intervals equal that median. A window
    that cannot manage that is not a square and says PERIOD ABSENT rather than
    being averaged into a number."""
    e = rising_edges(levels)
    if len(e) < MIN_EDGES_FOR_PERIOD:
        return {"period": PERIOD_ABSENT, "why": NOT_ESTIMATED, "edges": len(e)}
    gaps = [b - a for a, b in zip(e, e[1:])]
    med = _median(gaps)
    equal = sum(1 for g in gaps if g == med)
    frac = equal / float(len(gaps))
    if frac < UNIFORMITY:
        return {"period": PERIOD_ABSENT, "edges": len(e), "median": med, "uniformity": frac,
                "why": "only %.0f%% of the intervals equal the median; §V9.8 requires %.0f%%"
                       % (100 * frac, 100 * UNIFORMITY)}
    return {"period": med, "edges": len(e), "median": med, "uniformity": frac, "gaps": gaps}


# ------------------------------------------------------------- QUESTION R
def question_R(windows):
    """§V9.4's verdicts, in the words they were written in.

    `windows` is a list of dicts {"press": 1..4, "note": "F1"|"F2",
    "levels": [...]} -- the note is what the ROM was ASKED for at that press,
    which is known from the alternation and not from the bytes.
    """
    read = []
    for w in windows:
        if not w or not w.get("levels"):
            continue
        r = window_period(w["levels"])
        read.append({"press": w.get("press"), "note": w.get("note"), **r})
    usable = [r for r in read if r["period"] != PERIOD_ABSENT]
    by_note = {}
    for r in usable:
        by_note.setdefault(r["note"], []).append(r["period"])

    report = {"per_window": read, "by_note": by_note}
    if len(by_note) < 2:
        if read and not usable:
            report["verdict"] = "PERIOD ABSENT"
            report["why"] = ("no window carried a measurable alternation: the bytes did not change with "
                             "the press, or changed into something with no period")
            return report
        report["verdict"] = "INCONCLUSIVE"
        report["why"] = "fewer than two windows with DIFFERENT frequencies were captured"
        return report

    p1 = _median(by_note["F1"])
    p2 = _median(by_note["F2"])
    ratio = p1 / p2 if p2 else float("inf")
    report["period_F1"] = p1
    report["period_F2"] = p2
    report["ratio"] = ratio
    report["predicted_ratio"] = RATIO
    if abs(ratio - RATIO) <= RATIO_TOL * RATIO:
        report["verdict"] = "RATIO HOLDS"
        report["why"] = ("period(F1)/period(F2) = %.4f against the predicted %.4f: the periods follow "
                         "the notes, so a block is a re-read buffer at a fixed rate" % (ratio, RATIO))
        # the rate follows from EITHER window, and both are reported so they can be compared
        report["bytes_per_second"] = {"from_F1": freq_hz(N1) * p1, "from_F2": freq_hz(N2) * p2}
        return report
    report["verdict"] = "RATIO DOES NOT HOLD"
    report["why"] = ("period(F1)/period(F2) = %.4f, not %.4f. A REAL RESULT, not a failed run: the "
                     "re-read-buffer reading is wrong and U-GBP-037's second half is answered in the "
                     "negative" % (ratio, RATIO))
    if abs(ratio - 2.0) <= RATIO_TOL * 2.0:
        report["note"] = ("the quotient is ~2, which is exactly what a half-period miscount produces -- "
                          "§V9.3.2 chose a factor of 4 so that this case is DISTINGUISHABLE rather than "
                          "silently correct-looking")
    return report


# ------------------------------------------------------------- QUESTION C
def question_C(control_levels, run30_period=256.0):
    """§V9.7: what the control window contains on a DIFFERENT cartridge, read
    FIRST and deciding nothing about R."""
    if not control_levels:
        return {"verdict": "INCONCLUSIVE", "why": "no control window was captured"}
    r = window_period(control_levels)
    if r["period"] == PERIOD_ABSENT:
        if not rising_edges(control_levels):
            return {"verdict": "SILENCE", "period": PERIOD_ABSENT,
                    "why": "the window at rest carries no alternation at all on this cartridge, which "
                           "makes RUN 30's control the odd one out"}
        return {"verdict": "DIFFERENT SHAPE", "period": PERIOD_ABSENT, "detail": r,
                "why": "the window at rest alternates but has no stable period"}
    if abs(r["period"] - run30_period) < 1e-9:
        return {"verdict": "SAME SHAPE", "period": r["period"],
                "why": "a %g-byte square at rest on a second, unrelated cartridge: the resting wave is a "
                       "property of the PATH or of the GBP, not of the instrument" % run30_period}
    return {"verdict": "DIFFERENT SHAPE", "period": r["period"],
            "why": "the window at rest carries a square of %g bytes, not RUN 30's %g" % (r["period"], run30_period)}


if __name__ == "__main__":
    import json
    print(json.dumps({"notes": notes(), "choice": choice_is_sound(),
                      "rate_range": rate_range_that_still_works()}, indent=2))
