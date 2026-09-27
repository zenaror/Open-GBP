#!/usr/bin/env python3
"""
tools/v124route.py — the pre-registered, already-frozen predictions for `agb-route`'s two open
questions (docs/research/UNKNOWNS.md `U-GBP-047`, `U-GBP-048`), implemented before this round's
first physical run reads them (GitHub Issue #124's own predictions, sharpened by #125; wired for
the hardware-test round GitHub Issue #129 opens).

NOTHING NEW IS DECIDED HERE. Both verdicts are the predictions already on record, quoted at each
function below; this file supplies only the arithmetic each already states. It reuses
tools/v123frame.py's own per-slice (wA, wB) reading (streams 1 and 5's popcount, unedited) and
tools/v11sweep.py's own onset-slicing and axis-derivation (`sliced`, `derive_schedule`,
`refusals`, all unedited, both FROZEN constructions this file must not adjust) rather than
re-deriving any of them.

  question_stereo   U-GBP-047, sharpened by Issue #125: route-left (SOUNDCNT_L 0x1077) moves wA
                     with the tone and pins wB within noise of the rest width 128; route-right
                     (0x0177) moves wB and pins wA. The literal number is 128 (RUN 33 and RUN 34's
                     own control windows read exactly (128, 128), zero deviation over 4096
                     slices) — nothing here substitutes a run's own control-window reading for
                     it; that reading is only ever reported alongside the verdict, for a human to
                     compare, never used as the pin/move boundary itself.

                     THE PIN/MOVE CLASSIFIER IS RELATIVE, NOT ABSOLUTE (Orchestrator review,
                     Issue #130, before any capture was read): the control windows are silent on
                     BOTH sides, so they cannot show what crosstalk from an ACTIVE side does to a
                     nominally silent one. An absolute threshold on the "pinned" side's own
                     deviation risks a false negative for stereo if crosstalk moves it by more
                     than that threshold. So the two sides' deviations from 128 are compared to
                     EACH OTHER (pinned ~ 0, varying ~ 30, the Orchestrator's own illustrative
                     figures) — see MOVE_FLOOR / RELATIVE_PIN_RATIO below.
  question_bias     U-GBP-048: route-both's E reads resolution bits 14-15 = 0. ANY non-zero
                     resolution breaks the model (docs/research/UNKNOWNS.md, verbatim).

Standard library only. Nothing here reads a device, a clock or a file by itself — question_stereo
takes already-parsed anchors/windows (tools/awinparse.py's own shapes); question_bias takes a
16-bit value an Operator read off the ROM's own readout screen (an OPERATOR OBSERVATION — this
tool does not and cannot capture it; 14-audio has no frame-capture path of its own).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awinparse  # noqa: E402
import v11sweep  # noqa: E402
import v123frame  # noqa: E402

# RUN 33 and RUN 34's own control windows (tools/v123frame.py, run against the archived fixtures):
# (wA, wB) == (128, 128) in every one of 4096 control slices, zero deviation observed. The frozen
# prediction's own number.
REST_WIDTH = 128.0

# PROVISIONAL, not a measurement: RUN 33/34 show zero deviation at rest, so there is no real noise
# figure to calibrate either constant below against yet. The run's own raw numbers (every
# press window's mean, both sides' deviations) are reported alongside every verdict regardless of
# where these lines sit, so a human always reads the real figures, not just a pass/fail.

# The larger of the two sides' deviations from 128 must clear this to count as "varying" at all --
# otherwise neither side moved and no stereo verdict is drawn (both near rest is not evidence for
# either reading).
MOVE_FLOOR = 8.0

# The smaller deviation must be at most this FRACTION of the larger one to count as "small
# relative to it" (pinned). Two comparably large deviations (both moving, the 131 072 Hz rival's
# own prediction) or two comparably small ones are both INDETERMINATE, not a stereo reading.
RELATIVE_PIN_RATIO = 0.25

VARIANT_PREDICTION = {
    # Issue #125's own sharpened prediction on top of #124's.
    "left": {"moves": "wa", "pins": "wb"},
    "right": {"moves": "wb", "pins": "wa"},
}


def _mean_wa_wb(blocks):
    """The mean (wA, wB) over every slice of every block in `blocks` — tools/v123frame.py's own
    slice_record(), unedited (streams 1 and 5's popcount)."""
    was, wbs = [], []
    for blk in blocks:
        for i in range(len(blk) // v123frame.SLICE):
            rec = v123frame.slice_record(blk[i * v123frame.SLICE:(i + 1) * v123frame.SLICE])
            was.append(rec["wa"])
            wbs.append(rec["wb"])
    if not was:
        return None, None
    return sum(was) / float(len(was)), sum(wbs) / float(len(wbs))


def _deviation(values):
    """max |v - REST_WIDTH (128)| over `values`, ignoring None (an empty window); None if every
    value is None (unreadable)."""
    vs = [v for v in values if v is not None]
    return max(abs(v - REST_WIDTH) for v in vs) if vs else None


def _classify_stereo(dev_wa, dev_wb):
    """Amendment (a), Orchestrator review of Issue #130: RELATIVE, not absolute. Returns
    (wa_class, wb_class, separated). `separated` is False when the two deviations are not clearly
    separated (neither cleared MOVE_FLOOR, or the smaller is not small relative to the larger) --
    then both classes are "INDETERMINATE" and no stereo verdict is drawn from them."""
    if dev_wa is None or dev_wb is None:
        return "UNREADABLE", "UNREADABLE", False
    hi = max(dev_wa, dev_wb)
    lo = min(dev_wa, dev_wb)
    if hi < MOVE_FLOOR or lo > RELATIVE_PIN_RATIO * hi:
        return "INDETERMINATE", "INDETERMINATE", False
    wa_moved = dev_wa > dev_wb
    return ("MOVED" if wa_moved else "PINNED"), ("PINNED" if wa_moved else "MOVED"), True


def question_stereo(anchors, windows, variant):
    """U-GBP-047. `anchors`/`windows` are tools/awinparse.py's own parsed shapes (parse()'s
    anchors list; windows(), one block-list per anchor, same order). `variant` is "left" or
    "right" (route-left / route-right; route-both and route-bias0200 do not carry this
    prediction and are refused).

    Admissibility mirrors RUN 33/34's own checklist (HARDWARE_TESTS.md §V13.6): the schedule
    derived from the press windows' own `keys` must be "F" (every press on the pad's A, the SAME
    protocol RUN 33/34 used) with no refusals, and exactly one control window plus four press
    windows, closed, must be present.
    """
    if variant not in VARIANT_PREDICTION:
        raise ValueError("question_stereo is pre-registered for route-left/route-right only, not %r" % (variant,))

    press_anchor_idx = [i for i, a in enumerate(anchors) if a["kind"] == 1]
    control_anchor_idx = [i for i, a in enumerate(anchors) if a["kind"] == 0]
    press_keys = [anchors[i]["keys"] for i in press_anchor_idx]
    axis = v11sweep.derive_schedule(press_keys)
    bad = v11sweep.refusals(press_keys, axis)

    if axis != "F" or bad or len(control_anchor_idx) != 1 or len(press_anchor_idx) != 4:
        return {"admissible": False, "axis": axis, "refusals": bad,
                "control_windows": len(control_anchor_idx), "press_windows": len(press_anchor_idx)}
    if any(not (anchors[i]["flags"] & awinparse.F_CLOSED) for i in press_anchor_idx + control_anchor_idx):
        return {"admissible": False, "axis": axis, "refusals": bad, "why": "a window did not close"}

    control_blocks = windows[control_anchor_idx[0]]
    press_blocks = [windows[i] for i in press_anchor_idx]

    control_wa, control_wb = _mean_wa_wb(control_blocks)
    press_means = [_mean_wa_wb(v11sweep.sliced(b)) for b in press_blocks]
    press_wa = [m[0] for m in press_means]
    press_wb = [m[1] for m in press_means]

    dev_wa = _deviation(press_wa)
    dev_wb = _deviation(press_wb)
    wa_class, wb_class, separated = _classify_stereo(dev_wa, dev_wb)
    pred = VARIANT_PREDICTION[variant]
    expect_wa = "MOVED" if pred["moves"] == "wa" else "PINNED"
    expect_wb = "MOVED" if pred["moves"] == "wb" else "PINNED"
    prediction_holds = separated and wa_class == expect_wa and wb_class == expect_wb

    return {
        "admissible": True, "axis": axis,
        "control_wa": control_wa, "control_wb": control_wb,
        "press_wa": press_wa, "press_wb": press_wb,
        "deviation_wa": dev_wa, "deviation_wb": dev_wb,
        "separated": separated,
        "wa_class": wa_class, "wb_class": wb_class,
        "expected": {"wa": expect_wa, "wb": expect_wb},
        "prediction_holds": prediction_holds,
        "rest_width": REST_WIDTH, "move_floor": MOVE_FLOOR, "relative_pin_ratio": RELATIVE_PIN_RATIO,
    }


def question_bias(entry_value, entry_ok):
    """U-GBP-048's prediction on `E` (the ROM's entry read), an OPERATOR OBSERVATION: "route-both's
    E reads resolution bits 14-15 = 0 ... ANY non-zero resolution breaks the model." `entry_ok`
    is the readout's own dash/no-dash flag (the stub's marker present or absent, `bias.entry_ok`
    in stimulus/agb-route/source/main.c) — the prediction is not admissible to check without it,
    the same way the ROM itself shows four dashes rather than a value."""
    if not entry_ok:
        return {"admissible": False, "why": "the entry marker was absent (the stub did not run, or the "
                                             "readout showed four dashes)"}
    if not (0 <= entry_value <= 0xFFFF):
        raise ValueError("entry_value must be a 16-bit unsigned value, got %r" % (entry_value,))
    resolution = (entry_value >> 14) & 0x3
    return {"admissible": True, "entry": entry_value, "resolution_bits_14_15": resolution,
            "prediction_holds": resolution == 0}


def main(argv):
    if len(argv) < 3 or argv[1] not in ("left", "right"):
        print("usage: v124route.py left|right <sidecar-path>", file=sys.stderr)
        return 2
    variant, path = argv[1], argv[2]
    data, header, anchors, windows = awinparse.load(path)
    r = question_stereo(anchors, windows, variant)
    print("route-%s: %s" % (variant, r))
    return 0 if r.get("admissible") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
