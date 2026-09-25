#!/usr/bin/env python3
"""
tools/u012game.py — GitHub Issue #120: RUN 43's ride-along, the first raw AUDIO blocks of a GAME ever stored
(`sync-0001`, GBP-AUDIO-012, Yoshi's Island). DESCRIPTIVE, host-side, on archived bytes; it decides nothing.

    tools/u012game.py [<OGBPAWR1 file, .gz accepted>] [--json <out>]
        (default: captures/local/GBP-AUDIO-012_sync-0001-run43-awr.bin, the flat archive copy; the raw window is
        NOT versioned -- it is 0.16 s of a commercial game's audio output, kept local pending that decision)

WHAT IT READS. tools/awrparse.py's strict parse of the container (640 whole 4 096-byte blocks, consecutive in the
drain's own tap count, with the instants of the first and the last), then tools/v18block.py's one-bit count of each
of a block's sixteen 256-byte slices. Nothing else. "Nominal" rates are 4 096 blocks/s, 32 768 pairs/s and 65 536
slices/s: every Hz figure below is CONDITIONAL on the sixteen slices being uniform in time (U-GBP-041) and on the
block rate; the counts in slices are not.

1. TRANSITIONS. A level change inside a block is an internal slice boundary i (1..15) where the counts either side
   differ by at least STEP_MIN one-bits. STEP_MIN = 6 is twice v18block.FLAT_SPREAD (the 1-3-bit spread of a flat
   block, U-GBP-043), and the figures are also printed at 4 and 8. Reported: how many land on EVEN and on ODD
   boundaries (GBP-HW-315 found every tone transition on an even one -- the pair grid), and the gaps between
   consecutive transitions of one block, in slices.
   WHETHER A CHANGE SPLITS A SLICE. If the source changed level at instants continuous in time and a slice
   integrated whatever fell inside it, the slice holding a change would read an intermediate count: the change
   would show as two steps of the SAME sign, one slice apart. `neighbours` counts, beside every transition, the
   steps at the adjacent internal boundaries (those not themselves transitions) of the same sign and of the
   opposite sign, by size (1, 2, >= 3 bits). Equal counts of both signs, and no transitions one slice apart, mean
   the changes do not split slices. TWO MODELS give that, and the capture cannot tell them apart: a source that
   quantises its output on a grid coinciding with the slices, read by slices that integrate; or a source changing at
   continuous instants, read by a slice that does NOT integrate over its interval (one read per slice). Which holds
   is U-GBP-012's physical half, what a slice's count integrates over.

2. THE HOLD PERIOD AND THE MISSING BLOCKS, fitted together. A game mixes at a fixed rate and holds each sample, so
   its level changes recur every P slices. Seen through the drain, a block the drain never delivered shifts every
   later change by 16 slices, i.e. by 16 mod P. The fit:
     * P0: the period that best aligns the first INIT_BLOCKS blocks' transitions (coherence R = |mean e^(2 pi i x/P)|,
       x the transition's slice index counted as if the blocks were contiguous), on a grid over [P_LO, P_HI];
     * G: the cumulative number of blocks missing before each stored block, by dynamic programming over G in
       0..GMAX, a stored block's cost being sum(1 - cos(2 pi x/P - phi)) over its transitions at x = 16 (k + G_k) + i
       and a new gap (1..3 blocks at once) costing MU; G_0 = 0;
     * P is then CHOSEN BY THE TOTAL COST, not by R alone: for every P on a grid of SCAN_STEP over P0 +- SCAN_SPAN,
       and again of FINE_STEP around the best, phi is taken from the first INIT_BLOCKS blocks, G is fitted, phi is
       refitted on every transition G places and G is fitted again; the P with the lowest cost (misfit plus MU per
       gap) wins. Choosing by R after G is fitted is circular -- a slightly wrong P is compensated by extra gaps
       (16 x 2 mod P is 0.83 slices, close to nothing) and keeps its own G; the first version of this tool did
       exactly that on RUN 43 and returned 14 missing blocks at a local optimum.
   Reported: P, the gaps (after which stored block, how many), R, and R's QUANTISATION BOUND sin(pi/P)/(pi/P) -- the
   coherence of changes that happen at uniform times but can only show at the next slice boundary. R at the bound
   means the placement leaves nothing to explain beyond that quantisation. Its sampling spread comes from R_DRAWS
   simulated sets of as many uniform phases (seed R_SEED). sigma_2sd is the rms displacement of the slice
   boundaries, in slices, that would pull R down to R - 2 sd (Gaussian displacement) UNDER THE CONTINUOUS MODEL:
   changes at continuous instants, each read at its (displaced) slice. It is NOT a bound on the slices under the
   other model of `neighbours`, a source quantised on the slice grid: a displacement inside the grid's margin then
   changes no slice's count, and nothing below one slice is tested (tests/host/test_u012_game.py,
   WhetherChangesSplitSlices, builds both). RUN 43 does not decide between the models, so sigma_2sd is kept as the
   tool's number and is never a record's bound.
   THE TIMING CROSS-CHECK is independent of the content: (t_last - t_first) x 4 096 / tb_hz - (n - 1) is how many
   block periods the header's own instants hold beyond the stored blocks. The two estimates are printed side by
   side; neither is adjusted to the other.

3. PER-BOUNDARY COUNTS: the transitions at each internal boundary 1..15, with the chi-square against uniform and its
   lower tail. Under the continuous model a slice longer or shorter than the others would catch more or fewer of a
   uniform-rate stream's changes. A source that already sits on a grid coinciding with the slices spreads its
   changes deterministically, so the counts are then far MORE even than chance, and the chi-square tests nothing.

4. THE BANDS. Only on GAP-FREE runs of stored blocks (from G), cut into segments of WELCH_BLOCKS blocks, each
   Hann-windowed and transformed (radix-2 FFT, checked against a direct DFT in the tests); energies are the windowed
   periodogram's, summed over segments, as fractions of the AC total:
     A  (0, 2 048] Hz            the runtime's one-value-per-block decode's whole band
     B  (2 048, game Nyquist]    the game's own band above it; the game Nyquist is 32 768 / P Hz
     C  (game Nyquist, 16 384]   the hold's images inside the pair decode's band
     D  (16 384, 32 768]         what only the slice decode carries
   for the pair decode (A+B+C = 1) and the slice decode (A+B+C+D = 1).
   WINDOW-FREE CROSS-CHECKS on every stored block, gaps or not:
     within_block  sum (slice - its block's mean)^2 / sum (slice - the window's mean)^2 -- the AC energy the block
                   decode cannot represent at all, whatever the frequency axis;
     within_pair   sum (slice - its pair's mean)^2 / the same total -- what only the slice decode carries.

5. THE FOLD. The runtime's value is the block's count: the sum of its sixteen slices, a boxcar and a decimation by
   sixteen with no anti-alias stage. Its response at f is |H(f)|^2 = (sin(16 pi f/65 536) / (16 sin(pi f/65 536)))^2,
   and everything above 2 048 Hz that survives it FOLDS onto the block decode's band. From the same Hann-windowed
   segments as the bands:
     folded_fraction  sum over f > 2 048 of |H|^2 P(f) / sum over f > 0 of |H|^2 P(f): the share of the block
                      decode's AC energy that is folded content;
     droop            1 - sum over f <= 2 048 of |H|^2 P(f) / sum over f <= 2 048 of P(f): the in-band energy the
                      boxcar itself removes (|H| is 0.64 at 2 048 Hz, not 1).
   An EXACT split in time (FFT brickwall on the unwindowed segment, then block sums) was the first version; on a
   construction it leaked a tone's energy across the cut, and the boxcar then amplified the leak against the tone
   (a pure 3 kHz tone read 0.61 folded, not 1), so it was replaced before any figure was recorded.

6. RESOLUTION: the window's length in block periods (the stored blocks plus the fitted missing ones), the longest
   gap-free run and the segment length, each as a bin width in Hz.

Standard library only; reads the file it is given (opened read-only), writes the JSON it is asked to.
"""
import cmath
import gzip
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import awrparse  # noqa: E402
import v18block  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, "captures", "local", "GBP-AUDIO-012_sync-0001-run43-awr.bin")

BLOCK_RATE = 4096
SLICES = v18block.SLICES                  # 16
CUT_HZ = 2048.0                           # the block decode's Nyquist
STEP_MIN = 6                              # 2 x v18block.FLAT_SPREAD
STEP_ALT = (4, 8)
INIT_BLOCKS = 64
P_LO, P_HI, P_STEP = 5.0, 8.0, 0.001
SCAN_SPAN, SCAN_STEP = 0.01, 0.0002        # the DP-cost scan around P0
FINE_SPAN, FINE_STEP = 0.0002, 0.00001     # and around its best
GMAX = 40
GAP_STEPS = (1, 2, 3)
MU = 3.0
WELCH_BLOCKS = 64
R_DRAWS, R_SEED = 2000, 120                # the quantisation bound's sampling spread


# ---- the bytes ------------------------------------------------------------------------------------------------------

def load(path):
    """(header, blocks): the container parsed strictly, gzip or not; the file is never written."""
    with open(path, "rb") as f:
        data = f.read()
    if path.endswith(".gz"):
        data = gzip.decompress(data)
    return awrparse.parse(data)


def slice_table(blocks):
    return [v18block.slice_counts(b) for b in blocks]


# ---- 1. transitions -------------------------------------------------------------------------------------------------

def transitions(S, step_min=STEP_MIN):
    """Per block, the internal boundaries i (1..15) where the counts either side differ by >= step_min."""
    return [[i for i in range(1, SLICES) if abs(s[i] - s[i - 1]) >= step_min] for s in S]


def parity(TR):
    even = sum(1 for tr in TR for i in tr if i % 2 == 0)
    odd = sum(1 for tr in TR for i in tr if i % 2 == 1)
    return {"even": even, "odd": odd}


def intervals(TR):
    out = {}
    for tr in TR:
        for a, b in zip(tr, tr[1:]):
            out[b - a] = out.get(b - a, 0) + 1
    return dict(sorted(out.items()))


# ---- 2. the hold period and the missing blocks ----------------------------------------------------------------------

def positions(TR, G=None):
    """Every transition's slice index, counted with G_k blocks missing before stored block k."""
    return [SLICES * (k + (G[k] if G else 0)) + i for k, tr in enumerate(TR) for i in tr]


def coherence(xs, P):
    """(R, phi): the resultant length and angle of e^(2 pi i x / P) over xs."""
    if not xs:
        return 0.0, 0.0
    z = sum(cmath.exp(2j * math.pi * x / P) for x in xs) / len(xs)
    return abs(z), cmath.phase(z)


def best_period(xs, lo, hi, step):
    """(R, P, phi) maximising R over the grid lo, lo + step, ..., hi (grid points computed, not accumulated)."""
    best = None
    n = int(round((hi - lo) / step))
    for j in range(n + 1):
        P = lo + j * step
        R, phi = coherence(xs, P)
        if best is None or R > best[0]:
            best = (R, P, phi)
    return best


def quantisation_bound(P):
    """The coherence of uniform-time changes that can only show at the next slice boundary: E|e^(2 pi i u/P)|,
    u uniform on [0, 1)."""
    a = math.pi / P
    return math.sin(a) / a


def fit_gaps(TR, P, phi, mu=MU, gmax=GMAX, steps=GAP_STEPS):
    """(G, cost): the cumulative missing blocks before each stored block, by dynamic programming (G_0 = 0)."""
    INF = float("inf")
    n = len(TR)
    cost = [0.0] + [INF] * gmax
    back = []
    for k in range(n):
        em = [sum(1.0 - math.cos(2 * math.pi * (SLICES * (k + g) + i) / P - phi) for i in TR[k])
              for g in range(gmax + 1)]
        nc, bk = [INF] * (gmax + 1), [0] * (gmax + 1)
        for g in range(gmax + 1):
            cands = [(cost[g], g)] if cost[g] < INF else []
            if k:
                cands += [(cost[g - d] + mu, g - d) for d in steps if g - d >= 0 and cost[g - d] < INF]
            if cands:
                c, pg = min(cands)
                nc[g], bk[g] = c + em[g], pg
        cost = nc
        back.append(bk)
    g = min(range(gmax + 1), key=lambda x: (cost[x], x))
    total = cost[g]
    G = [0] * n
    for k in range(n - 1, -1, -1):
        G[k] = g
        g = back[k][g]
    return G, total


def gaps_of(G):
    """[(after stored block, missing)] for every step of G."""
    return [(k - 1, G[k] - G[k - 1]) for k in range(1, len(G)) if G[k] != G[k - 1]]


def at_period(TR, P, mu=MU):
    """(cost, G, phi) at a FIXED P: phi from the first INIT_BLOCKS blocks, G fitted, phi refitted, G fitted again."""
    phi = coherence(positions(TR[:INIT_BLOCKS]), P)[1]
    G, _ = fit_gaps(TR, P, phi, mu)
    phi = coherence(positions(TR, G), P)[1]
    G, cost = fit_gaps(TR, P, phi, mu)
    return cost, G, phi


def grid(lo, hi, step):
    n = int(round((hi - lo) / step))
    return [lo + j * step for j in range(n + 1)]


def solve(TR, mu=MU):
    R0, P0, _ = best_period(positions(TR[:INIT_BLOCKS]), P_LO, P_HI, P_STEP)
    scan = [(at_period(TR, P, mu)[0], P) for P in grid(P0 - SCAN_SPAN, P0 + SCAN_SPAN, SCAN_STEP)]
    Pc = min(scan)[1]
    fine = [(at_period(TR, P, mu)[0], P) for P in grid(Pc - FINE_SPAN, Pc + FINE_SPAN, FINE_STEP)]
    cost, P = min(fine)
    cost, G, phi = at_period(TR, P, mu)
    return {"P0": P0, "R0_init": R0, "P": P, "phi": phi, "cost": cost, "R": coherence(positions(TR, G), P)[0],
            "G": G, "gaps": gaps_of(G), "missing": G[-1],
            "scan": [(round(Pv, 6), round(c, 3)) for c, Pv in scan]}


def bound_spread(n, P, draws=R_DRAWS, seed=R_SEED):
    """(mean, sd) of R for n changes quantised to the next boundary at uniform phases: the bound's sampling spread."""
    import random
    rng = random.Random(seed)
    vals = []
    for _ in range(draws):
        z = sum(cmath.exp(2j * math.pi * rng.random() / P) for _ in range(n)) / n
        vals.append(abs(z))
    m = sum(vals) / draws
    return m, math.sqrt(sum((v - m) ** 2 for v in vals) / draws)


def sigma_bound(R, bound, sd, P, k=2.0):
    """The rms boundary displacement, in slices, that would lower the coherence to R - k sd, under Gaussian
    displacement: R(sigma) = bound x exp(-(2 pi sigma / P)^2 / 2). 0 when R - k sd is at or above the bound."""
    lo = R - k * sd
    if lo >= bound:
        return 0.0
    return P / (2 * math.pi) * math.sqrt(-2.0 * math.log(lo / bound))


def timing_missing(h, n):
    """Block periods the header's own instants hold beyond the n stored blocks (a float, not rounded)."""
    return (h["t_last"] - h["t_first"]) * float(BLOCK_RATE) / h["tb_hz"] - (n - 1)


# ---- 3. per boundary --------------------------------------------------------------------------------------------------

def neighbours(S, TR):
    """Beside every transition, the steps at the adjacent internal boundaries that are not transitions themselves:
    {size: [same sign, opposite sign]} for sizes '1', '2', '3+' bits; and how many transitions sit one slice apart."""
    out = {"1": [0, 0], "2": [0, 0], "3+": [0, 0]}
    for s, tr in zip(S, TR):
        ts = set(tr)
        for i in tr:
            main = s[i] - s[i - 1]
            for j in (i - 1, i + 1):
                if j < 1 or j > SLICES - 1 or j in ts:
                    continue
                d = s[j] - s[j - 1]
                if d == 0:
                    continue
                key = "1" if abs(d) == 1 else ("2" if abs(d) == 2 else "3+")
                out[key][0 if (d > 0) == (main > 0) else 1] += 1
    adjacent = sum(1 for tr in TR for a, b in zip(tr, tr[1:]) if b - a == 1)
    return {"steps": out, "adjacent_transitions": adjacent}


def boundary_counts(TR):
    c = [0] * SLICES
    for tr in TR:
        for i in tr:
            c[i] += 1
    inner = c[1:]
    mean = sum(inner) / float(len(inner))
    chi2 = sum((v - mean) ** 2 / mean for v in inner) if mean else 0.0
    dof = len(inner) - 1
    return {"counts": inner, "chi2": chi2, "dof": dof, "lower_tail": chi2_cdf_even(chi2, dof)}


def chi2_cdf_even(x, k):
    """P(chi-square_k <= x) for an even k: 1 - e^(-x/2) sum_{i < k/2} (x/2)^i / i!. A value far below 0.5 says the
    counts are MORE even than independent draws would be -- the signature of a deterministic grid, not a test."""
    assert k % 2 == 0
    h, term, acc = x / 2.0, 1.0, 1.0
    for i in range(1, k // 2):
        term *= h / i
        acc += term
    return 1.0 - math.exp(-h) * acc


# ---- 4. bands --------------------------------------------------------------------------------------------------------

def fft(x):
    """Radix-2 iterative FFT of a power-of-two-length sequence (complex out)."""
    n = len(x)
    if n & (n - 1):
        raise ValueError("length %d is not a power of two" % n)
    a = [complex(v) for v in x]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    size = 2
    while size <= n:
        w = cmath.exp(-2j * math.pi / size)
        half = size // 2
        for s in range(0, n, size):
            wk = 1.0 + 0j
            for k in range(half):
                u, v = a[s + k], a[s + k + half] * wk
                a[s + k], a[s + k + half] = u + v, u - v
                wk *= w
        size *= 2
    return a


def ifft(X):
    n = len(X)
    return [v.conjugate() / n for v in fft([v.conjugate() for v in X])]


def runs(G):
    """Gap-free runs of stored blocks, [start, end) in stored-block indices."""
    out, s = [], 0
    for k in range(1, len(G)):
        if G[k] != G[k - 1]:
            out.append((s, k))
            s = k
    out.append((s, len(G)))
    return out


def segments(G, w=WELCH_BLOCKS):
    """Non-overlapping w-block segments inside the gap-free runs, [start, end)."""
    return [(a + j * w, a + (j + 1) * w) for a, b in runs(G) for j in range((b - a) // w)]


def series(S, a, b, per_block):
    group = SLICES // per_block
    return [float(sum(S[k][i * group:(i + 1) * group])) for k in range(a, b) for i in range(per_block)]


def band_energies(S, segs, per_block, edges):
    """Energy fractions of the Hann-windowed periodograms, summed over segments, in the bands (edges[j], edges[j+1]]."""
    fs = BLOCK_RATE * per_block
    acc = [0.0] * (len(edges) - 1)
    for a, b in segs:
        x = series(S, a, b, per_block)
        n = len(x)
        m = sum(x) / n
        win = [0.5 - 0.5 * math.cos(2 * math.pi * t / n) for t in range(n)]
        X = fft([(v - m) * wv for v, wv in zip(x, win)])
        for k in range(1, n // 2 + 1):
            f = k * fs / float(n)
            e = abs(X[k]) ** 2 * (1 if k == n // 2 else 2)
            for j in range(len(acc)):
                if edges[j] < f <= edges[j + 1]:
                    acc[j] += e
                    break
    tot = sum(acc)
    return [v / tot for v in acc] if tot else acc


def window_free(S):
    """The within-block and within-pair fractions of the window's AC energy, over every stored block."""
    allv = [v for s in S for v in s]
    m = sum(allv) / len(allv)
    tot = sum((v - m) ** 2 for v in allv)
    wb = sum((v - sum(s) / 16.0) ** 2 for s in S for v in s)
    wp = sum((s[2 * j + d] - (s[2 * j] + s[2 * j + 1]) / 2.0) ** 2 for s in S for j in range(8) for d in (0, 1))
    return {"within_block": wb / tot, "within_pair": wp / tot, "slice_sd": math.sqrt(tot / len(allv))}


# ---- 5. the fold -----------------------------------------------------------------------------------------------------

def boxcar2(f, n=SLICES, fs=BLOCK_RATE * SLICES):
    """|H(f)|^2 of the n-slice sum, normalised to 1 at 0 Hz."""
    if f == 0:
        return 1.0
    a = math.pi * f / fs
    return (math.sin(n * a) / (n * math.sin(a))) ** 2


def periodogram(S, segs, per_block):
    """[(f, P)] of the Hann-windowed periodograms summed over the segments (one-sided, DC excluded)."""
    fs = BLOCK_RATE * per_block
    acc = {}
    for a, b in segs:
        x = series(S, a, b, per_block)
        n = len(x)
        m = sum(x) / n
        win = [0.5 - 0.5 * math.cos(2 * math.pi * t / n) for t in range(n)]
        X = fft([(v - m) * wv for v, wv in zip(x, win)])
        for k in range(1, n // 2 + 1):
            f = k * fs / float(n)
            acc[f] = acc.get(f, 0.0) + abs(X[k]) ** 2 * (1 if k == n // 2 else 2)
    return sorted(acc.items())


def fold(S, segs, cut=CUT_HZ):
    """The share of the block decode's AC energy that is folded content, and the boxcar's in-band droop."""
    pg = periodogram(S, segs, SLICES)
    above = sum(boxcar2(f) * p for f, p in pg if f > cut)
    passed = sum(boxcar2(f) * p for f, p in pg)
    inband = sum(p for f, p in pg if f <= cut)
    kept = sum(boxcar2(f) * p for f, p in pg if f <= cut)
    return {"folded_fraction": above / passed if passed else 0.0,
            "droop": 1.0 - kept / inband if inband else 0.0, "segments": len(segs)}


# ---- the whole analysis ----------------------------------------------------------------------------------------------

def analyse(path=DEFAULT):
    h, blocks = load(path)
    S = slice_table(blocks)
    TR = transitions(S)
    fit = solve(TR)
    P = fit["P"]
    game_nyq = BLOCK_RATE * SLICES / 2.0 / P
    segs = segments(fit["G"])
    rs = runs(fit["G"])
    longest = max(b - a for a, b in rs)
    edges_pair = [0.0, CUT_HZ, game_nyq, BLOCK_RATE * 8 / 2.0]
    edges_slice = [0.0, CUT_HZ, game_nyq, BLOCK_RATE * 8 / 2.0, BLOCK_RATE * SLICES / 2.0]
    spread = bound_spread(sum(len(t) for t in TR), P)
    sigma = sigma_bound(fit["R"], quantisation_bound(P), spread[1], P)
    return {
        "header": {"blocks": len(blocks), "seq_first": h["seq_first"], "seq_last": h["seq_last"],
                   "t_first": h["t_first"], "t_last": h["t_last"], "tb_hz": h["tb_hz"],
                   "copy_min": h["copy_min"], "copy_max": h["copy_max"], "copy_sum": h["copy_sum"],
                   "copy_n": h["copy_n"]},
        "transitions": {"step_min": STEP_MIN, "n": sum(len(t) for t in TR), "parity": parity(TR),
                        "intervals": intervals(TR), "neighbours": neighbours(S, TR),
                        "alt": dict((str(t), {"parity": parity(transitions(S, t)),
                                              "intervals": intervals(transitions(S, t))}) for t in STEP_ALT)},
        "fit": {"P0_init_blocks": INIT_BLOCKS, "P0": fit["P0"], "R0_init": fit["R0_init"], "P": P, "phi": fit["phi"],
                "R": fit["R"], "cost": fit["cost"], "bound": quantisation_bound(P),
                "bound_spread": spread, "sigma_2sd": sigma, "gaps": fit["gaps"],
                "missing": fit["missing"], "scan": fit["scan"], "mu": MU,
                "hz_nominal": BLOCK_RATE * SLICES / P, "agb_cycles_nominal": P * 256.0,
                "robust_mu": dict((str(mu), solve(TR, mu)["gaps"] == fit["gaps"]) for mu in (1.0, 6.0))},
        "timing": {"missing_implied": timing_missing(h, len(blocks)),
                   "span_s": (h["t_last"] - h["t_first"]) / float(h["tb_hz"])},
        "boundaries": boundary_counts(TR),
        "bands": {"edges_hz": edges_slice, "game_nyquist_hz": game_nyq, "welch_blocks": WELCH_BLOCKS,
                  "segments": len(segs),
                  "pair": band_energies(S, segs, SLICES // 2, edges_pair),
                  "slice": band_energies(S, segs, SLICES, edges_slice)},
        "window_free": window_free(S),
        "fold": fold(S, segs),
        "resolution": {"window_slots": len(blocks) + fit["missing"],
                       "window_s": (len(blocks) + fit["missing"]) / float(BLOCK_RATE),
                       "window_bin_hz": BLOCK_RATE / float(len(blocks) + fit["missing"]),
                       "runs": rs, "longest_run_blocks": longest, "longest_run_bin_hz": BLOCK_RATE / float(longest),
                       "segment_bin_hz": BLOCK_RATE / float(WELCH_BLOCKS)},
    }


def main(argv):
    rest = list(argv[1:])
    out = None
    if "--json" in rest:
        j = rest.index("--json")
        out = rest[j + 1]
        del rest[j:j + 2]
    r = analyse(rest[0] if rest else DEFAULT)
    f, t, b = r["fit"], r["transitions"], r["bands"]
    print("u012game: %d blocks, tap seq %d..%d, span %.6f s" % (r["header"]["blocks"], r["header"]["seq_first"],
                                                              r["header"]["seq_last"], r["timing"]["span_s"]))
    print("  transitions >= %d bits: %d, even %d / odd %d boundaries; intervals %s"
          % (t["step_min"], t["n"], t["parity"]["even"], t["parity"]["odd"], t["intervals"]))
    print("  beside them, adjacent steps same/opposite sign: %s; transitions one slice apart: %d"
          % (t["neighbours"]["steps"], t["neighbours"]["adjacent_transitions"]))
    print("  hold period P %.5f slices (%.1f AGB cycles, %.1f Hz nominal); R %.4f against the bound %.4f "
          "(sampling mean %.4f, sd %.4f)" % (f["P"], f["agb_cycles_nominal"], f["hz_nominal"], f["R"], f["bound"],
                                             f["bound_spread"][0], f["bound_spread"][1]))
    print("  missing blocks: content %d at %s; header timing %.2f" % (f["missing"], f["gaps"],
                                                                        r["timing"]["missing_implied"]))
    print("  per-boundary counts %s chi2 %.2f on %d dof, lower tail %.4f"
          % (r["boundaries"]["counts"], r["boundaries"]["chi2"], r["boundaries"]["dof"], r["boundaries"]["lower_tail"]))
    print("  bands (edges %s Hz), %d segments of %d blocks" % (["%.0f" % e for e in b["edges_hz"]], b["segments"],
                                                               b["welch_blocks"]))
    print("    pair  " + "  ".join("%.4f" % v for v in b["pair"]))
    print("    slice " + "  ".join("%.4f" % v for v in b["slice"]))
    print("  window-free: within-block %.4f, within-pair %.4f" % (r["window_free"]["within_block"],
                                                                  r["window_free"]["within_pair"]))
    print("  fold: %.4f of the block decode's AC energy is folded content from above 2 048 Hz; the boxcar removes "
          "%.4f of the in-band energy" % (r["fold"]["folded_fraction"], r["fold"]["droop"]))
    print("  resolution: window %d block periods = %.3f Hz, longest gap-free run %d blocks = %.1f Hz, segment %.1f Hz"
          % (r["resolution"]["window_slots"], r["resolution"]["window_bin_hz"], r["resolution"]["longest_run_blocks"],
             r["resolution"]["longest_run_bin_hz"], r["resolution"]["segment_bin_hz"]))
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(r, fh, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
