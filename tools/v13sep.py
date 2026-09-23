"""§V13's construction — `U-GBP-038`'s separator, frozen before the run.

FROZEN, and a test diffs this file against the commit that introduced it. Fifth
outing of the discipline `tools/v7611.py`, `v8audio.py`, `v9tone.py` and
`v11sweep.py` established.

WHAT IT DECIDES. `GBP-HW-307` left two readings of the same three runs and said
they were not separated:

    ORDINAL   the window in which the AGB's emission BEGINS carries nothing;
              the NEXT one carries, whenever it happens to fall.
    ELAPSED   nothing carries until some delay T after the emission begins, and
              every window that reaches past T carries.

THE SEPARATOR IS A SHORT GAP, NOT A LONG ONE, and §V11.16.9 said the opposite.
A long gap is where the two AGREE: ten seconds after the emission, ORDINAL says
"this is the next window, it carries" and ELAPSED says "ten seconds is past any
T we can still believe, it carries". They only disagree on a window that opens
BEFORE T, which is a window that opens SOON. §V11.16.9's sentence is corrected
on top, not deleted.

NEITHER PREDICATE NEEDS T, which is why the verdict is mechanical:

    ORDINAL is refuted by   any window after the emitting one that carries nothing
    ELAPSED is refuted by   a window that carries while a LATER one does not --
                            a single threshold cannot produce that

So the verdict is read off the carriage pattern ordered by offset, and the bound
on T falls out as a measurement beside it rather than as an input.

Nothing here reads a device or a clock. Synthetic vectors only.
"""

# §V11.16.9's bound on the delay, from RUN 31 and RUN 32 read with GBP-HW-306's
# correction (the first EMITTING press was press 2 in both, not press 1):
#   carriage had NOT begun one window-length after the emission  -> T > 0.0625 s
#   carriage HAD begun 3.320 s later (RUN 31) and 3.370 s (RUN 32) -> T <= 3.33 s
T_LOWER = 0.0625
T_UPPER = 3.33

# §V8.3.2's window: 256 blocks at §V7.8.6's drain cadence.
WINDOW_SECONDS = 256.0 / 4096.0          # 62.5 ms

# THE FLOOR ON A GAP, and it is not a preference. A press that arrives while a
# window is still filling is REFUSED and counted (`arm_refused_busy`,
# gbp_awin.c). A window fills in WINDOW_SECONDS, and the AGB needs up to ~18 ms
# to react, so anything under about 0.1 s risks a refusal -- which is VISIBLE,
# never silent, and is why the run reports the counter rather than assuming.
GAP_FLOOR = 0.10

# §V13.4's ladder, as offsets from the FIRST press in seconds. They are targets
# for the Operator, NOT tolerances: the log records each window's own `t_arm`
# and the analysis uses the measured values.
OFFSET_TARGETS = (0.0, 0.3, 1.2, 4.0)


def predict_ordinal(n):
    """ORDINAL: the emitting window is dead, every later one carries."""
    return [False] + [True] * (n - 1)


def predict_elapsed(offsets, t):
    """ELAPSED with a given delay: a window carries once it reaches past T.
    `t` is never supplied by the data -- this exists so the two predicates can
    be compared on synthetic vectors."""
    return [off + WINDOW_SECONDS > t for off in offsets]


def bound_from(offsets, carried):
    """What the observed pattern implies about T, as a half-open interval, or
    None when no single threshold fits. Reported BESIDE the verdict."""
    pairs = sorted(zip(offsets, carried))
    lo, hi = 0.0, float("inf")
    for off, c in pairs:
        if c:
            hi = min(hi, off + WINDOW_SECONDS)
        else:
            lo = max(lo, off + WINDOW_SECONDS)
    return None if lo >= hi else (lo, hi)


def question_S(offsets, carried):
    """§V13.5's gate. `offsets` are the MEASURED arm offsets from the first
    press; `carried` is one boolean per window, in the same order.

    The last window by offset is the POSITIVE CONTROL: both readings predict it
    carries, so a run where it does not is inadmissible for this question rather
    than evidence about it."""
    if len(offsets) != len(carried) or len(offsets) < 3:
        return {"verdict": "INADMISSIBLE", "why": "fewer than three windows to order"}
    order = sorted(range(len(offsets)), key=lambda i: offsets[i])
    first, last = order[0], order[-1]
    if not carried[last]:
        return {"verdict": "INADMISSIBLE",
                "why": "the positive control (the last window by offset) carried nothing, "
                       "so the run says nothing about either reading"}
    if carried[first]:
        return {"verdict": "INADMISSIBLE",
                "why": "the emitting window itself carried, which neither reading predicts "
                       "and which no run has shown"}

    seq = [carried[i] for i in order]
    monotone = all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1))
    ordinal_holds = seq == predict_ordinal(len(seq))
    out = {"order": order, "offsets": [offsets[i] for i in order], "carried": seq,
           "bound": bound_from(offsets, carried)}
    if not monotone:
        out["verdict"] = "BOTH REFUTED"
        out["why"] = ("a window carried while a later one did not, which no single "
                      "threshold can produce and which ORDINAL does not predict either")
    elif ordinal_holds:
        out["verdict"] = "NOT SEPARATED"
        out["why"] = ("only the emitting window is dead, which is what ORDINAL predicts and "
                      "what ELAPSED also predicts for a small enough T -- the run bounds T "
                      "instead of deciding between them")
    else:
        out["verdict"] = "ORDINAL REFUTED"
        out["why"] = ("a window after the emitting one carried nothing, which ORDINAL "
                      "forbids and a threshold explains")
    return out


def gaps(offsets):
    """The gap between each press and the one before it, in offset order."""
    o = sorted(offsets)
    return [o[i + 1] - o[i] for i in range(len(o) - 1)]


def gaps_are_admissible(offsets, floor=GAP_FLOOR):
    """Every gap must clear the floor, or a press may have been refused rather
    than captured. Returns the gaps that do not."""
    return [g for g in gaps(offsets) if g < floor]
