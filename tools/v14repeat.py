"""§V14's MEASUREMENT — RUN 34, §V11's amplitude sweep repeated with the repaired instrument.

THIS MODULE CONTAINS NO GATE. The verdict on RUN 34 is `tools/v11sweep.py`'s
`question_V`, unedited, exactly as it judged RUN 32. What is frozen here is only
the METHOD of the measurement reported beside that verdict, so that it cannot be
chosen after the data exists. A test diffs this file against the commit that
introduced it, and a second test shows it reproduces §V11.16.7's published
figures on RUN 32 to the last digit — the method is the one already used, not a
new one.

WHY A MEASUREMENT NEEDS FREEZING AT ALL. §V11.16.7 found that a block is a 1-bit
PWM pulse (GBP-HW-304) and that §V11.4's `duty()` counts whole BYTES, so it
quantises each sample to 8 bits. The measurement that fitted the linear model to
0.04 bytes was taken at BIT resolution, and it was defined during the ingestion.
Defining it again after RUN 34's data exists would be exactly the choice-after-
the-fact the discipline forbids, so it is defined here, now.

Nothing here reads a device, a clock or a file.
"""
import collections

import v11sweep

POPCOUNT = bytes(bin(i).count("1") for i in range(256))

# RUN 31's two carrying windows, envelope volume 15, at bit resolution (§V11.16.7,
# GBP-HW-305). The anchor both §V11.4 models are re-anchored on.
ANCHOR_V15 = 30.0625 / 256.0


def bitduty(block):
    """The fraction of one-bits in a block: the same quantity as §V11.4's duty(),
    at the resolution the bytes are actually written in."""
    return sum(POPCOUNT[x] for x in block) / float(len(block) * 8)


def deviation(blocks, onset=v11sweep.ONSET_SLICE_BLOCKS):
    """Half the separation between the two modal bit-duty levels of the sliced
    window, or None when the window has no two sides. §V11.16.7's definition."""
    series = [bitduty(b) for b in blocks[onset:]]
    lo = [x for x in series if x < 0.5 - 1e-6]
    hi = [x for x in series if x > 0.5 + 1e-6]
    if not lo or not hi:
        return None
    return (collections.Counter(hi).most_common(1)[0][0] -
            collections.Counter(lo).most_common(1)[0][0]) / 2.0


def fit(points):
    """Least-squares (slope, intercept) through (volume, deviation) pairs. The
    intercept is §V11.4.1's null."""
    n = len(points)
    mx = sum(p[0] for p in points) / float(n)
    my = sum(p[1] for p in points) / float(n)
    sxx = sum((p[0] - mx) ** 2 for p in points)
    slope = sum((p[0] - mx) * (p[1] - my) for p in points) / sxx
    return slope, my - slope * mx


def model_errors(points, anchor=ANCHOR_V15):
    """Total absolute error of each §V11.4 model, re-anchored on the MEASURED V=15,
    over the points that are not the anchor. A measurement, never a gate."""
    err = {"linear": 0.0, "compressive": 0.0}
    for volume, dev in points:
        if volume == v11sweep.ANCHOR_VOLUME:
            continue
        err["linear"] += abs(dev - v11sweep.deviation_linear(volume, anchor=anchor))
        err["compressive"] += abs(dev - v11sweep.deviation_compressive(volume, anchor=anchor))
    return err


def repeat_delta(first, second):
    """The difference between two runs' measurement of the same volume, in bytes
    of 256. What GBP-HW-305 names as needed before its reading can be FACT."""
    return (second - first) * 256.0
