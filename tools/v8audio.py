#!/usr/bin/env python3
"""
tools/v8audio.py — §V8's predictions and verdict constructions, executable,
written BEFORE the image that would produce a log exists (GitHub Issue #58,
2026-09-22).

WHY THIS FILE EXISTS. §V8 pre-registers an experiment whose whole value is
that the three candidate models predict DIFFERENT BYTES FOR THE SAME WINDOW.
That value survives only if the constructions are fixed before the bytes are
seen: code written with a capture open beside it gets "fixed" until it gives a
clean answer, and every step of that feels like debugging. So this module was
written from §V8's frozen text alone -- no build exists, no run is authorised,
no log exists anywhere -- and its tests exercise it on SYNTHETIC vectors only.
It is the same discipline tools/v7611.py was written under (Issue #50).

WHAT IT DOES NOT DO. It authorises nothing and it promotes nothing. It decides
AU and SP only against the verdicts §V8.5.2 and §V8.4 wrote down first, with
the tolerances §V8.5.3 fixed first, and where the frozen text does not define
something THIS MODULE REFUSES TO INVENT IT -- see NOT_ESTIMATED, NOT_OBSERVED
and NOT_READABLE.

WHAT IT ASSUMES ABOUT THE BYTES. Only that a window arrives as a sequence of
4096-byte AUDIO blocks in drain order, and a silent control as another such
sequence from the SAME RUN (§V8.5.1). It does not know how the build emits
them; the sidecar's framing is the ingestion's problem, not the prediction's.
"""

SECTION = "docs/research/HARDWARE_TESTS.md §V8"

# ------------------------------------------------------------ the instrument
# §V8.2, restated from PHASE6_ENTRY.md §2 (the program read at its pinned
# commit, OUTSIDE this tree, CC BY-SA 4.0 -- behaviour described, nothing
# carried). These are what the program ASKS THE APU FOR, not what the GBP's
# AUDIO window carries: that gap is the experiment.
F_PHASE1_HZ = 131072.0 / (2048 - 1200)      # 154.57 Hz, the busy-wait phase
F_PHASE2_HZ = 131072.0 / (2048 - 0)         #  64.00 Hz, after the "stop"
ENVELOPE_STEP_S = 7.0 / 64.0                # 109.375 ms, 15 steps to silence
ENVELOPE_STEPS = 15
DUTY_CYCLE = (0.125, 0.25, 0.50, 0.75)      # advanced PER PRESS, not per button

# ------------------------------------------------------------ the transport
# §V8.2's cadence, recomputed from RUN 17's archive (§V7.8.6 and the #45
# correction). Not re-derived here.
BLOCK_BYTES = 4096
DRAINS_PER_S = 4094.4
BLOCK_MS = 1000.0 / DRAINS_PER_S            # 0.2442 ms

# ------------------------------------------------------------ the window
# §V8.3.2. BLOCKS_PER_WINDOW is 256 because 128 leaves less than one whole
# 64 Hz period in the worst case once the AGB-side detection latency is
# subtracted (§V8.3.1); the correction was made before any data existed.
BLOCKS_PER_WINDOW = 256
WINDOWS_PER_RUN = 4
GBA_FRAME_MS = 16.74                        # the worst-case detection latency

# ------------------------------------------------------------ the tolerances
# §V8.5.3, fixed there and not here.
PERIOD_TOL = 0.15                           # relative
MARK_FRACTION_TOL = 0.06                    # absolute
MIN_EDGES_FOR_PERIOD = 3                    # three rising edges = two intervals
MIN_PRESSES_FOR_MATCH = 2                   # "at least two of the four"

# Refusals. None of these is a failure and none of them is INCONCLUSIVE: the
# run is not inconclusive about a thing the pre-registration never defined.
NOT_ESTIMATED = "NOT ESTIMATED (fewer than three rising edges)"
NOT_OBSERVED = "NOT OBSERVED (not the same as: did not happen)"
NOT_READABLE = "NOT READABLE"

MODELS = ("PWM", "PCM", "BYTE0")


# ---------------------------------------------------------------- arithmetic

def blocks_for_ms(ms):
    """How many drained blocks a duration covers, at §V8.2's cadence."""
    return ms / BLOCK_MS


def period_blocks(freq_hz):
    """One period of a square wave, in drained blocks."""
    return (1000.0 / freq_hz) / BLOCK_MS


def window_plan():
    """§V8.3.2's arithmetic, computed rather than copied, so the doc's numbers
    are checkable against the constants they came from."""
    per_window_ms = BLOCKS_PER_WINDOW * BLOCK_MS
    worst_ms = per_window_ms - GBA_FRAME_MS
    decay_ms = ENVELOPE_STEPS * ENVELOPE_STEP_S * 1000.0
    decay_blocks = blocks_for_ms(decay_ms)
    total = BLOCKS_PER_WINDOW * WINDOWS_PER_RUN
    emitted = decay_blocks * WINDOWS_PER_RUN
    return {
        "blocks_per_window": BLOCKS_PER_WINDOW,
        "windows_per_run": WINDOWS_PER_RUN,
        "total_blocks": total,
        "total_bytes": total * BLOCK_BYTES,
        "window_ms": per_window_ms,
        "periods_phase2_per_window": per_window_ms / (1000.0 / F_PHASE2_HZ),
        "worst_case_ms": worst_ms,
        "worst_case_periods": worst_ms / (1000.0 / F_PHASE2_HZ),
        "decay_blocks_per_press": decay_blocks,
        "emitted_blocks": emitted,
        "kept_fraction": total / emitted,
        "envelope_steps_per_window": per_window_ms / (ENVELOPE_STEP_S * 1000.0),
    }


def duty_for_press(index):
    """§V8.2: the duty advances PER PRESS and repeats every four. `index` is
    0-based within the run's press order."""
    return DUTY_CYCLE[index % len(DUTY_CYCLE)]


def expected_mark_fraction(press_index):
    """The predicted mark fraction for a press -- 1:7, 1:3, 1:1, 3:1 in
    §V8.5's table are these same four numbers written as ratios."""
    return duty_for_press(press_index)


# --------------------------------------------------- reducing a block to one
# level, per model. §V8.5's table: each model claims a different thing about
# the same 4096 bytes, so each gets its own reduction and they are never
# mixed (§V8.5.3's last tolerance).

_PWM_SHAPES = tuple(((0xFF << (8 - n)) & 0xFF) for n in range(9))  # 00,80,C0..FF


def leading_ones(byte):
    n = 0
    for bit in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01):
        if not byte & bit:
            break
        n += 1
    return n


def is_pwm_shaped(block):
    """Dolphin's model: every byte's 1 bits are contiguous AND leading."""
    return all(b in _PWM_SHAPES for b in block)


def mirrored_x4(block):
    """§V8.5: PWM predicts the 0x1000 block is 0x400 bytes repeated four times.
    A check that costs nothing, and PCM predicts its negation."""
    q = len(block) // 4
    return block[0:q] == block[q:2 * q] == block[2 * q:3 * q] == block[3 * q:]


def byte0_sparse(block):
    """U-GBP-021's pattern: every non-zero byte sits at offset 0 of a 32-byte
    line. This is what the cartridge-less archive already shows."""
    return all(b == 0 for i, b in enumerate(block) if i % 32)


def block_level(block, model):
    """One scalar per block, in the model's own terms. Returns None when the
    block does not have the model's shape at all: a model that can absorb any
    block is not a model, so each reduction REFUSES the others' bytes (§V8.5)."""
    if model == "PWM":
        if not is_pwm_shaped(block):
            return None
        return sum(leading_ones(b) for b in block) / float(len(block))
    if model == "PCM":
        return sum(block) / float(len(block))
    if model == "BYTE0":
        if not byte0_sparse(block):
            return None
        return sum(block[i] for i in range(0, len(block), 32)) / float(len(block) // 32)
    raise ValueError("unknown model %r; §V8.5 names exactly %r" % (model, MODELS))


def level_series(blocks, model):
    """The per-block level series for a window, or None if any block refuses
    the model's shape."""
    out = []
    for b in blocks:
        lv = block_level(b, model)
        if lv is None:
            return None
        out.append(lv)
    return out


# ------------------------------------------------------ the two observables

def two_level_split(levels):
    """Split a level series at the midpoint of its range. Returns None when
    the series is constant -- silence predicts exactly that (§V8.5)."""
    if not levels:
        return None
    lo, hi = min(levels), max(levels)
    if hi == lo:
        return None
    mid = (hi + lo) / 2.0
    return [lv > mid for lv in levels]


def rising_edges(high):
    """Indices where the series goes low -> high. The first sample cannot be
    an edge: nothing precedes it."""
    return [i for i in range(1, len(high)) if high[i] and not high[i - 1]]


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def alternation_period(levels):
    """§V8.5.3: the MEDIAN inter-edge interval, estimated only from at least
    three rising edges. Fewer, and the period is NOT ESTIMATED."""
    high = two_level_split(levels)
    if high is None:
        return NOT_ESTIMATED
    edges = rising_edges(high)
    if len(edges) < MIN_EDGES_FOR_PERIOD:
        return NOT_ESTIMATED
    return _median([b - a for a, b in zip(edges, edges[1:])])


def mark_fraction(levels):
    """The mark-space ratio as the fraction of the series above the midpoint,
    measured over WHOLE periods only so a partial period cannot bias it."""
    high = two_level_split(levels)
    if high is None:
        return None
    edges = rising_edges(high)
    if len(edges) < 2:
        return None
    span = high[edges[0]:edges[-1]]
    return sum(1 for h in span if h) / float(len(span))


def period_matches(measured, predicted):
    if not isinstance(measured, (int, float)):
        return False
    return abs(measured - predicted) <= PERIOD_TOL * predicted


def mark_matches(measured, predicted):
    if measured is None:
        return False
    return abs(measured - predicted) <= MARK_FRACTION_TOL


# ------------------------------------------------------------ the transition

def find_transition(levels):
    """§V8.5's first row: the alternation period changes from ~26.5 to ~64
    blocks. Scans every split that leaves both halves able to carry an
    estimate and returns the first that matches BOTH predicted periods.

    Returns a dict, or NOT_OBSERVED -- which §V8.5.3 separates from a claim
    that the transition did not happen: a window anchored at the key change
    may simply not contain phase 1 (§V8.3.1)."""
    p1 = period_blocks(F_PHASE1_HZ)
    p2 = period_blocks(F_PHASE2_HZ)
    need = int(MIN_EDGES_FOR_PERIOD * p1)
    for split in range(need, len(levels) - need + 1):
        before = alternation_period(levels[:split])
        after = alternation_period(levels[split:])
        if period_matches(before, p1) and period_matches(after, p2):
            return {"split_block": split, "period_before": before,
                    "period_after": after, "predicted": (p1, p2)}
    return NOT_OBSERVED


# -------------------------------------------------------------- the control

def differs_from_control(window_levels, control_levels):
    """§V8.5.3: at least two rising edges where the control has none, OR a
    mark fraction differing by more than the tolerance. Both on the same
    model's reduction."""
    w_high = two_level_split(window_levels)
    c_high = two_level_split(control_levels)
    w_edges = rising_edges(w_high) if w_high is not None else []
    c_edges = rising_edges(c_high) if c_high is not None else []
    if len(w_edges) >= 2 and not c_edges:
        return True, "alternation in the window (%d rising edges) where the control has none" % len(w_edges)
    wm, cm = mark_fraction(window_levels), mark_fraction(control_levels)
    if wm is not None and cm is not None and abs(wm - cm) > MARK_FRACTION_TOL:
        return True, "mark fraction %.3f against the control's %.3f" % (wm, cm)
    return False, "indistinguishable from the within-run silent control"


# ------------------------------------------------------------- one window

def classify_window(blocks, control_blocks, press_index):
    """What one window says, per model, against §V8.5's table. Reports; it
    does not decide -- AU does, in question_AU."""
    out = {"press_index": press_index, "duty": duty_for_press(press_index), "models": {}}
    for model in MODELS:
        levels = level_series(blocks, model)
        control = level_series(control_blocks, model) if control_blocks else None
        if levels is None:
            out["models"][model] = {"shape": "REFUSED: the bytes do not have this model's shape"}
            continue
        r = {"shape": "accepted",
             "period": alternation_period(levels),
             "mark_fraction": mark_fraction(levels),
             "transition": find_transition(levels),
             "mirrored_x4": all(mirrored_x4(b) for b in blocks)}
        r["period_matches_phase2"] = period_matches(r["period"], period_blocks(F_PHASE2_HZ))
        r["duty_matches"] = mark_matches(r["mark_fraction"], expected_mark_fraction(press_index))
        if control is None:
            r["differs_from_control"] = None
            r["control_note"] = ("no silent control retained; §V8.5.1 makes AU's positive verdict "
                                 "unavailable without one")
        else:
            r["differs_from_control"], r["control_note"] = differs_from_control(levels, control)
        out["models"][model] = r
    return out


# --------------------------------------------------------------- QUESTION AU

def question_AU(windows, control_blocks):
    """§V8.5.2's four verdicts, in the words they were written in.

    `windows` is the list of captured windows in press order, each a list of
    4096-byte blocks. A missing press is a None entry, not a gap."""
    captured = [(i, w) for i, w in enumerate(windows) if w]
    if len(captured) < MIN_PRESSES_FOR_MATCH:
        return {"verdict": "INCONCLUSIVE",
                "why": "fewer than two windows captured (%d)" % len(captured),
                "per_window": []}
    if not control_blocks:
        return {"verdict": "INCONCLUSIVE",
                "why": "no within-run silent control was retained (§V8.5.1)",
                "per_window": [classify_window(w, None, i) for i, w in captured]}

    per_window = [classify_window(w, control_blocks, i) for i, w in captured]
    matched, differing = {}, 0
    for w in per_window:
        if any(m.get("differs_from_control") for m in w["models"].values()):
            differing += 1
        for model, m in w["models"].items():
            if m.get("period_matches_phase2") and m.get("duty_matches"):
                matched[model] = matched.get(model, 0) + 1

    best = [m for m, n in matched.items() if n >= MIN_PRESSES_FOR_MATCH]
    if best:
        return {"verdict": "CARRIES / PREDICTED SHAPE", "models": sorted(best),
                "why": "the predicted alternation period AND the press's duty on at least two of the "
                       "four presses, against the within-run control",
                "per_window": per_window}
    if differing >= 2:
        return {"verdict": "CARRIES / OTHER SHAPE",
                "why": "the windows differ from the silent control and REPEAT with the press, but not "
                       "into the predicted shape. A REAL RESULT: either the prediction or the reading "
                       "of the checker is wrong",
                "per_window": per_window}
    if differing == 1:
        # §V8.5.2: one window differing is a difference, not a repetition, and the pre-registration
        # refuses to read it as either verdict.
        return {"verdict": "INCONCLUSIVE",
                "why": "exactly one window differs from the control, which is a difference and not a "
                       "repetition",
                "per_window": per_window}
    return {"verdict": "DOES NOT CARRY",
            "why": "the windows are indistinguishable from the within-run silent control on every "
                   "captured press. A REAL RESULT, and one Phase 6 must have",
            "per_window": per_window}


# --------------------------------------------------------------- QUESTION SP

def question_SP(windows):
    """§V8.4: does the stop sequence fail as PHASE6_ENTRY §2.1 predicts -- a
    short 154.57 Hz phase followed by a long 64.00 Hz phase rather than
    silence? Read from the same blocks, on a SEPARATE gate: SP never makes AU
    inconclusive, and a wrong SP is a correction to this project's reading of
    the code, not a fault of the Operator's instrument."""
    seen = []
    for i, w in enumerate(windows):
        if not w:
            continue
        for model in MODELS:
            levels = level_series(w, model)
            if levels is None:
                continue
            tr = find_transition(levels)
            if tr is not NOT_OBSERVED:
                seen.append({"press_index": i, "model": model, "transition": tr})
                break
    if seen:
        return {"verdict": "AS PREDICTED", "evidence": seen,
                "why": "a 154.57 Hz phase followed by a 64.00 Hz phase, in %d of %d windows; the write "
                       "meant to end the sound removed the only stop that was armed"
                       % (len(seen), sum(1 for w in windows if w))}
    if not any(windows):
        return {"verdict": "UNREADABLE", "why": "no window was captured"}
    return {"verdict": NOT_OBSERVED,
            "why": "no window shows the two predicted periods either side of a split. §V8.3.1: a window "
                   "anchored at the key change may not contain phase 1 at all, so this is NOT a finding "
                   "that the stop worked"}


# ------------------------------------------------- the envelope, and the gate

def envelope_staircase(window_blocks):
    """§V8.3.2: one window spans 0.57 of an envelope step, so the 15-step
    decay is NOT a question this run can answer. Kept as a function so the
    refusal is executable rather than remembered."""
    return {"verdict": NOT_READABLE,
            "why": "one window of %d blocks spans %.2f of one envelope step (§V8.3.2); no verdict "
                   "depends on it" % (BLOCKS_PER_WINDOW, window_plan()["envelope_steps_per_window"])}


def identity_gate(declared, observed):
    """§V8.8: re-declared per run, never inherited. The hash of the Operator's
    own copy is a double check and never a gate on its own -- but if any
    identity DIFFERS on the day, DO NOT RUN."""
    differing = sorted(k for k in declared if k in observed and declared[k] != observed[k])
    if differing:
        return {"verdict": "DO NOT RUN", "differing": differing,
                "why": "§V8.8: an identity differs on the day (%s)" % ", ".join(differing)}
    missing = sorted(k for k in declared if k not in observed)
    if missing:
        return {"verdict": "DECLARED, NOT CHECKED", "missing": missing,
                "why": "the Operator's media is his; an unchecked identity is not a failed gate"}
    return {"verdict": "RE-DECLARED", "why": "every declared identity matches for THIS run"}
