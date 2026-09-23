"""§V17's PREDICTIONS — what a correct H-PWM decode of RUN 33 and RUN 34 must show.

FROZEN IN ITS OWN COMMIT, before the decoder exists and before any decoded
output is produced. A test diffs this file against that commit.

EVERYTHING IS DERIVED FROM THE ROM AND GBATEK, NOTHING FROM THE CAPTURE. The two
schedules are parsed out of `stimulus/agb-sweep/source/main.c` rather than
retyped, and the frequency is GBATEK's f = 131072 / (2048 - n).

ONE AXIS PER RUN, AND THE MODULE CANNOT BE ASKED OTHERWISE. `agb-sweep` walks the
FREQUENCY schedule on A and the VOLUME schedule on B, never both. Issue #80
first read the two tables side by side and predicted RUN 34's windows at
128/512/256/1024 Hz; RUN 34 was four B presses, so every window is 128.0 Hz and
only the volume moves. `predict(axis)` takes the axis -- which the decoder
derives from the capture's own KEY record (§V11.8) -- so that error cannot be
made through this module.

WHAT THE LAYOUT HYPOTHESIS PREDICTS, AND WHAT IT DOES NOT.
  H-PWM's layout: one drained block is ONE sample, at 4096 samples/s, and the
  sample is the block's DUTY. So:
    - each window's decoded series has period (2048 - n) / 32 samples  -- a claim
      about the TIMEBASE and the sample definition; this is the gate
    - on the B axis, the decoded amplitude falls as the volume falls    -- a claim
      that the sample VALUE tracks the AGB's output; this is the gate too
  It makes NO claim about how the amplitude varies with FREQUENCY. That is a
  property of the analog chain between the AGB's PSG and whatever the path
  samples, not of the layout. It is therefore kept OUT of the gate and reported
  beside it.

A DISCLOSURE, because it bears on that last choice. While checking Issue #80's
premise, the across-block period and the per-window deviation of both runs were
measured before this module was written. The periods have no free parameter
here -- (2048 - n) / 32 is fixed by the ROM -- so having seen them cannot have
tuned anything. The deviations are why amplitude-versus-frequency is kept out of
the gate: RUN 33's 1024 Hz window was seen to read lower than its 128 Hz window,
and writing a tolerance to fit that would be tuning, while writing "equal" would
be asserting a claim about the analog chain that H-PWM never made.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROM_SRC = os.path.join(ROOT, "stimulus", "agb-sweep", "source", "main.c")

SAMPLE_RATE = 4096               # GBP-HW-301: one drained block = one sample
PERIOD_TOLERANCE = 1             # samples; see period_band()
UNIFORMITY_MIN = 0.90            # §V9.8's, unchanged


def _table(name):
    src = open(ROM_SRC, encoding="utf-8").read()
    m = re.search(r"%s\[SWEEP_STEPS\] = \{([^}]*)\}" % name, src)
    if not m:
        raise ValueError("%s not found in the ROM source" % name)
    return tuple(int(x.strip().rstrip("uU")) for x in m.group(1).split(",") if x.strip())


def freq_n():
    return _table("SWEEP_FREQ_N")


def volumes():
    return _table("SWEEP_VOLUME")


def frequency_hz(n):
    """GBATEK: f = 131072 / (2048 - n)."""
    return 131072.0 / (2048 - n)


def period_samples(n):
    """The predicted period of the decoded series, in samples at SAMPLE_RATE.
    Exact for every n in the schedule, because 2048 - n is a multiple of 32."""
    return SAMPLE_RATE / frequency_hz(n)


def predict(axis):
    """One (n, frequency, period, volume) row per press window, in press order.

    axis "F" -- the pad's A walked the frequency schedule; the volume stays at
                its FIRST entry, which is where a pure-A run leaves it.
    axis "V" -- the pad's B walked the volume schedule; the frequency stays at
                its first entry, 128.0 Hz.
    """
    fn, vol = freq_n(), volumes()
    if axis == "F":
        pairs = [(n, vol[0]) for n in fn]
    elif axis == "V":
        pairs = [(fn[0], v) for v in vol]
    else:
        raise ValueError("predict() takes one axis, 'F' or 'V', never both: got %r" % (axis,))
    return [{"n": n, "frequency_hz": frequency_hz(n), "period": period_samples(n), "volume": v}
            for n, v in pairs]


def period_band(period, tol=PERIOD_TOLERANCE):
    """What the gate accepts for one window: a period within one sample of the
    prediction.

    WHY ONE SAMPLE. The decoded period is the median interval between rising
    crossings of an integer-indexed series, so it is itself an integer (or a
    half-integer median); one sample is the smallest non-zero tolerance such an
    estimator admits. The path's measured drain rate is 4094.4/s (§V7.8.6), 0.04 %
    from 4096 -- far less than one sample over any period in the schedule -- so
    an exact match is what the hypothesis predicts and one sample is slack for
    the estimator, not for the physics.

    WHAT IT COSTS, said rather than hidden. In hertz the band is asymmetric and
    widens as the period shrinks: at 128.0 Hz (32 samples) it is 124.1-132.1 Hz;
    at 1024.0 Hz (4 samples) it is 819-1365 Hz. The 1024 Hz window is therefore
    only WEAKLY resolved -- four samples per period is two from the Nyquist
    limit -- and a pass there says less than a pass at 128 Hz.
    """
    return (period - tol, period + tol)
