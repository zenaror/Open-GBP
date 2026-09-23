"""§V16's GATE — `QUESTION V` repaired: the same question, judged at BIT resolution.

FROZEN, forward only. A test diffs this file against the commit that introduced
it, and **it may not be applied to RUN 32 or RUN 34 to produce a verdict**
(§V16.3). Run on them it produces MEASUREMENTS, labelled as such.

WHAT WAS WRONG WITH THE OLD GATE (`GBP-HW-312`). `v11sweep.duty()` counts a byte
as high when it lies above the midpoint of its block's own extremes. Every block
this project has captured spans exactly 0x00..0xFF, so that midpoint is 127.5 and
the test reduces to `x >= 0x80` -- and 0x80 carries ONE bit in eight. RUN 34's V=3
low level is written with eight 0x80 bytes per cell, which the old gate counted
as sixty-four one-bits' worth of "high": its low level read 128 where RUN 32's
identical bit-level signal read 120, and the gate found no second level.

WHAT THE REPAIR IS, and it is one substitution. The per-block duty is the fraction
of ONE-BITS in the block (`v14repeat.bitduty`), which a 0x80 byte contributes 1/8
to rather than 8/8. It has no threshold and therefore no boundary for an edge
byte to land on. Every other part of the question is `v11sweep`'s, imported and
not copied: the onset slice, the flat tolerance, the modal levels, the order
gate, the move threshold, the refusals, the NO CELL and CARRIAGE FAILURE states.
**The question is unchanged; only the ruler is.**

WHY THE FLAT TOLERANCE STILL FITS. It is 1/256 of the cell about 0.5. A resting
window reads 1025.0-1025.3 of 2048 at bit level (§V11.16.3), i.e. within 0.0006
of 0.5, and the smallest predicted signal (V=3) deviates by about 0.024 -- forty
times the tolerance. Nothing about the old threshold was wrong for a bit-level
series; it was wrong for a byte-level one.

Nothing here reads a device, a clock or a file.
"""
import v11sweep
import v14repeat


def classify_window_bits(blocks):
    """`v11sweep.classify_window` with the per-block duty taken at bit
    resolution. Same states, same order of tests, same slice."""
    s = v11sweep.sliced(blocks)
    series = [v14repeat.bitduty(b) for b in s]
    out = {"blocks_used": len(s), "series": series,
           "alphabet": v11sweep.alphabet(s), "level_span": v11sweep.level_span(s)}
    if v11sweep.is_degenerate(s):
        out.update(state="NO CELL", deviation=None, period=None)
        return out
    if v11sweep.is_flat(series):
        out.update(state="CARRIAGE FAILURE", deviation=None, period=None)
        return out
    out["state"] = "CARRIES"
    out["deviation"] = v11sweep.observed_deviation(series)
    out["period"] = v11sweep.window_period(series)["period"]
    return out


def question_V_bits(windows, anchor_keys):
    """§V11.4's QUESTION V, verdict for verdict, with classify_window_bits in
    place of classify_window. The ORDER is the gate; the model comparison and
    the intercept are measurements beside it, exactly as in v11sweep."""
    bad = v11sweep.refusals(anchor_keys, "V")
    if bad:
        return {"verdict": "REFUSED",
                "why": "windows %s were not armed by B" % [b[0] for b in bad], "refused": bad}
    cls = [classify_window_bits(w) for w in windows]
    nocell = [i + 1 for i, c in enumerate(cls) if c["state"] == "NO CELL"]
    if nocell:
        return {"verdict": "INCONCLUSIVE", "windows": cls,
                "why": "windows %s have no two-level cell at all" % nocell}
    failures = [i + 1 for i, c in enumerate(cls) if c["state"] == "CARRIAGE FAILURE"]
    if failures:
        return {"verdict": "INCONCLUSIVE", "windows": cls,
                "why": "windows %s carried nothing" % failures}
    devs = [c["deviation"] for c in cls]
    if any(d is None for d in devs):
        return {"verdict": "INCONCLUSIVE", "windows": cls,
                "why": "a window has no two levels to measure a deviation from"}
    vols = list(v11sweep.AMPLITUDES[:len(devs)])
    span = devs[0] - devs[-1]
    ordered = all(devs[i] >= devs[i + 1] - v11sweep.ORDER_SLACK for i in range(len(devs) - 1))
    if span < v11sweep.MOVE_SPAN_MIN:
        verdict = "DOES NOT MOVE"
    elif not ordered:
        verdict = "MOVES, NOT ORDERED"
    else:
        verdict = "ORDERED"
    fit = v11sweep.fit_intercept(vols, devs)
    return {"verdict": verdict, "windows": cls, "volumes": vols, "deviations": devs,
            "span_bytes": span / v11sweep.BYTE, "ordered": ordered,
            "intercept_bytes": None if fit is None else fit[1] / v11sweep.BYTE,
            "models": v11sweep.compare_models(vols, devs)}


# ------------------------------------------------------------------ QUESTION L
# WHY A SECOND GATE EXISTS AT ALL. question_V's gate is the ORDER -- §V11.4 made
# the linear-vs-compressive comparison "a MEASUREMENT beside the verdict, never a
# gate". So an ORDERED verdict can take "the deviation falls with the volume" to
# FACT and can never take "the deviation is LINEAR in the volume" there. §V16.4
# asks for the run that would take the LINEAR model to FACT, and that needs a
# gate that decides linearity. Here it is, frozen before the run it judges.
#
# ITS TOLERANCE IS DERIVED FROM THE MODELS, NOT FROM THE RESIDUALS ALREADY SEEN.
# RUN 32 and RUN 34 put the linear errors at 0.03-0.11 bytes; a band chosen from
# those would be a band chosen with the data in hand. Instead: at every volume
# that is not the anchor, the measured deviation must lie within HALF THE GAP
# between the two predictions, on the linear side. That band is fixed by §V11.4's
# two formulas and the run's own V=15 window and by nothing else.

def question_L_bits(windows, anchor_keys):
    """LINEAR / COMPRESSIVE / NEITHER / INCONCLUSIVE / REFUSED, for a B run.

    Both models are re-anchored on THIS run's own V=15 window, as §V11.4
    specifies for the comparison, so the gate is self-contained in one run."""
    base = question_V_bits(windows, anchor_keys)
    if base["verdict"] in ("REFUSED", "INCONCLUSIVE"):
        return {"verdict": base["verdict"], "why": base.get("why"), "order": base}
    vols, devs = base["volumes"], base["deviations"]
    if v11sweep.ANCHOR_VOLUME not in vols:
        return {"verdict": "INCONCLUSIVE", "why": "no window measured the anchor volume"}
    a = devs[vols.index(v11sweep.ANCHOR_VOLUME)]
    rows, lin_ok, comp_ok = [], True, True
    for vol, d in zip(vols, devs):
        if vol == v11sweep.ANCHOR_VOLUME:
            continue
        lin = v11sweep.deviation_linear(vol, anchor=a)
        comp = v11sweep.deviation_compressive(vol, anchor=a)
        half = abs(lin - comp) / 2.0
        rows.append({"volume": vol, "measured": d, "linear": lin, "compressive": comp,
                     "half_gap": half})
        lin_ok = lin_ok and abs(d - lin) < half
        comp_ok = comp_ok and abs(d - comp) < half
    verdict = "LINEAR" if lin_ok else ("COMPRESSIVE" if comp_ok else "NEITHER")
    return {"verdict": verdict, "anchor": a, "rows": rows, "order": base}
