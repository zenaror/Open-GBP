#!/usr/bin/env python3
"""
tools/v124taps.py — GitHub Issue #124, Round A: does a 32-tap resampler change the native decode's output in band,
against the 16-tap one, by more than the source's own quantisation can carry? DESCRIPTIVE, host-side, on archived bytes.

    tools/v124taps.py [--json <out>]            the first rule, 16 taps at beta 5.65
    tools/v124taps.py --sweep [--json <out>]    the beta sweep at 16 taps

PRE-REGISTERED. This docstring, the constants below and the decision rule were committed BEFORE the tool was run on any
archived capture; the commit that adds them carries only tests on constructions. The result is recorded with that
commit's hash.

THE SIGNAL. The native decode chosen on #124 (Decision 1): per slice, x = wA + wB -- the one-bits of stream 1 (A) and
stream 5 (B) of the slice (tools/v123frame.py, GBP-HW-347) -- summed BEFORE the resampler: one value per slice, 65 536
a second nominal (the Hz conditional on uniform slices, U-GBP-041). Its step is one integer.

THE FILTERS. The 16-tap candidate is tools/v123chain.py's (16 taps a phase, Kaiser beta 5.65); the 32-tap candidates
are BOTH of v123chain's 32-tap ones (beta 5.65 and 7.86). Each is the prototype v123chain.prototype(taps, beta,
65 536, 16 000, 125): symmetric, taps x 125 + 1 coefficients, its centre on an integer index. The resampler is
65 536 -> 32 000 (L / M = 125 / 256). Each filter is evaluated ZERO-PHASE, at the SAME instants (output m at input time
m x 256 / 125): y_N[m] = sum_n x[n] h_N[256 m - 125 n + c_N], c_N the centre. So the two outputs differ only by what
the filters do to the waveform, never by their delays; the delays are a latency (GBP-HW-350), not this question. The
first and last GUARD outputs of each run are dropped (the kernels' reach).

THE RUNS. RUN 33 and RUN 34: every awin window, each a run of consecutive blocks. RUN 43: the gap-free runs of stored
blocks that tools/u012game.py's fit places (GBP-HW-345); absent from a checkout without captures/local.

THE MEASURE. d = y_16 - y_32, for each 32-tap candidate. Its power in a band [0, B] -- B = 5 256 Hz (the game's band,
GBP-HW-346) and B = 12 000 Hz -- from Hann-windowed periodograms of SEG outputs, summed over every segment of every run
of the capture: P_B(d) = sum over bins 0 < f <= B, and the DC bin, of |D_k|^2 / (SEG x sum w^2), one-sided bins
doubled. RMS_B(d) = sqrt(P_B(d) / segments).

THE FLOOR, fixed before any capture is read. The source's own quantisation: x is an integer, so its quantisation error
is taken as white and uniform over one step, variance 1/12 at 65 536 a second -- the most stringent reading (one
integer step on the SUM; two independent streams would give 1/6). Through a resampler of unit passband gain its power
in [0, B] is (1/12) x B / 32 768:
      B = 5 256 Hz   floor RMS 0.1156 steps
      B = 12 000 Hz  floor RMS 0.1747 steps

THE DECISION RULE. 16 taps are SETTLED ON EVIDENCE when RMS_B(d) < floor(B) in BOTH bands, against BOTH 32-tap
candidates, on EVERY capture present (RUN 33, RUN 34, and RUN 43 where the checkout has it). Any excess -> NOT SETTLED,
with the capture, band, candidate and the ratio RMS / floor reported; the trade against AHEAD is then made on #124,
not here.

REPORTED BESIDE IT, descriptive, not a gate:
  fold-in    each filter's in-band output from the input's content ABOVE 16 000 Hz: x split exactly into x_lo + x_hi by
             one FFT over the run (zero-padded to a power of two, the split taken back to the run's length), the
             output of x_hi measured in [0, B] as above -- what the filter lets alias into the band, in steps RMS and
             against the floor;
  signal     RMS_B of y_16 itself, the scale the difference sits under;
  max |d|    the largest single-output difference, in steps.

THE BETA SWEEP -- a second pre-registration (#124), committed and pushed before the sweep is run. The first rule
returned NOT SETTLED: one cell over the floor, RUN 33 in [0, 12 000] Hz, the 16-tap filter's passband roll-off (with
its fold-in at 0.55 of the floor). Kaiser beta trades exactly those two, so the 16-tap DESIGN is swept and the
CRITERION IS UNCHANGED:
  the grid      beta in BETA_GRID, 16 taps, cut-off 16 000 Hz, nothing else varied;
  the model     every kernel -- each 16-tap candidate and both 32-tap references -- normalised PER PHASE, every phase
                summing to 1, as the chain's coefficient table is (gbp_aresamp_coef.h: every phase sums to 32 768).
                The first rule's kernels were normalised as a whole; their phases' unequal DC gains turn x's ~256 DC
                into a pattern at multiples of 256 Hz: 0.015 steps RMS between 16 and 32 taps at beta 5.65, over the
                floor on its own at beta 2.0. The first rule's verdict stands as recorded; beta 5.65 is in this grid,
                so its design is re-measured under the chain's normalisation beside it, never in its place;
  the test      each beta against BOTH 32-tap candidates, both bands, every capture present -- THE SAME settled() rule;
  the choice    among the betas that pass, the one whose worst cell (largest RMS / floor over captures, bands and
                references) is smallest; ties to the larger beta (more stopband);
  the fallback  if NO beta passes, the default is 32 taps -- the Orchestrator's pre-commitment on #124. Which of the
                two 32-tap betas is not decided by this sweep; both candidates' figures go to #124.

Standard library only; reads the captures, writes the JSON it is asked to.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import u012game  # noqa: E402
import v123chain  # noqa: E402
import v123frame  # noqa: E402

FIN, FOUT, L, M = 65536, 32000, 125, 256
CUTOFF = 16000.0
SIXTEEN = (16, 5.65)
THIRTY_TWO = ((32, 5.65), (32, 7.86))
BANDS = (5256.0, 12000.0)
SEG = 256                                   # outputs a periodogram segment: 8 ms, 125 Hz bins
GUARD = 40                                  # outputs dropped at each end of a run (32 taps reach 16 inputs = 7.8 outputs)
FOLD_HZ = 16000.0                           # the output's Nyquist: content above it can only alias
BETA_GRID = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 5.65, 6.5, 7.86)   # the sweep's 16-tap betas, registered before it ran


def floor_rms(band_hz):
    """The source's quantisation floor in [0, B], in steps: white, variance 1/12 at FIN, unit passband gain."""
    return math.sqrt((1.0 / 12.0) * band_hz / (FIN / 2.0))


def kernel(taps, beta, per_phase=False):
    """(coefficients, centre). v123chain's prototype, normalised as a whole (sum L); with per_phase, every phase -- the
    coefficients one output uses, a residue class mod L -- scaled to sum 1, as gbp_aresamp_coef.h's table is."""
    h = v123chain.prototype(taps, beta, FIN, CUTOFF, L)
    if per_phase:
        sums = [sum(h[r::L]) for r in range(L)]
        h = [v / sums[i % L] for i, v in enumerate(h)]
    return h, (len(h) - 1) // 2


def resample(x, h, c):
    """Zero-phase 125/256: y[m] = sum_n x[n] h[256 m - 125 n + c], every m whose kernel lies inside x."""
    n_out = (len(x) - 1) * L // M + 1
    y = []
    for m in range(n_out):
        base = M * m + c
        lo = max(0, -(-(base - (len(h) - 1)) // L))          # smallest n with index <= len(h) - 1
        hi = min(len(x) - 1, base // L)                       # largest n with index >= 0
        acc = 0.0
        for n in range(lo, hi + 1):
            acc += x[n] * h[base - L * n]
        y.append(acc)
    return y


def band_power(seq, band_hz, fs=FOUT, seg=SEG):
    """(summed one-sided Hann periodogram power in [0, band], segments) over the non-overlapping segments of seq."""
    win = [0.5 - 0.5 * math.cos(2 * math.pi * t / seg) for t in range(seg)]
    w2 = sum(v * v for v in win)
    total, nseg = 0.0, 0
    for s in range(0, len(seq) - seg + 1, seg):
        X = u012game.fft([seq[s + t] * win[t] for t in range(seg)])
        p = abs(X[0]) ** 2
        for k in range(1, seg // 2 + 1):
            if k * fs / float(seg) > band_hz:
                break
            p += abs(X[k]) ** 2 * (1 if k == seg // 2 else 2)
        total += p / (seg * w2)
        nseg += 1
    return total, nseg


def split(x, fold_hz=FOLD_HZ, fs=FIN):
    """x = lo + hi exactly: hi is x's content above fold_hz, by one FFT over the run zero-padded to a power of two."""
    n = 1
    while n < len(x):
        n *= 2
    X = u012game.fft(list(x) + [0.0] * (n - len(x)))
    for k in range(n):
        f = min(k, n - k) * fs / float(n)
        if f <= fold_hz:
            X[k] = 0j
    hi = [v.real for v in u012game.ifft(X)][:len(x)]
    return [a - b for a, b in zip(x, hi)], hi


def trimmed(y, guard=GUARD):
    return y[guard:len(y) - guard] if len(y) > 2 * guard else []


class Acc(object):
    def __init__(self):
        self.p, self.n, self.maxabs = 0.0, 0, 0.0

    def add(self, seq, band_hz):
        p, n = band_power(seq, band_hz)
        self.p += p
        self.n += n
        if seq:
            self.maxabs = max(self.maxabs, max(abs(v) for v in seq))

    def rms(self):
        return math.sqrt(self.p / self.n) if self.n else None


def measure(runs, sixteen=SIXTEEN, per_phase=False):
    """runs: [[x values]]. The difference, fold-in and signal figures of every filter and band, for the 16-tap design
    `sixteen` (taps, beta) against both 32-tap candidates; per_phase normalises every kernel as the chain's table."""
    ks = dict((("N%d_b%.2f" % f), kernel(f[0], f[1], per_phase)) for f in (sixteen,) + THIRTY_TWO)
    k16 = "N%d_b%.2f" % sixteen
    out = {"bands": {}, "runs": len(runs), "inputs": sum(len(x) for x in runs)}
    for B in BANDS:
        diff = dict((name, Acc()) for name in ks if name != k16)
        fold = dict((name, Acc()) for name in ks)
        sig = Acc()
        for x in runs:
            lo, hi = split(x)
            ys = dict((name, resample(x, h, c)) for name, (h, c) in ks.items())
            for name in diff:
                diff[name].add(trimmed([a - b for a, b in zip(ys[k16], ys[name])]), B)
            for name, (h, c) in ks.items():
                fold[name].add(trimmed(resample(hi, h, c)), B)
            sig.add(trimmed(ys[k16]), B)
        fl = floor_rms(B)
        out["bands"]["%d" % B] = {
            "floor_rms": fl,
            "segments": sig.n,
            "signal_rms_16": sig.rms(),
            "diff": dict((name, {"rms": a.rms(), "ratio_to_floor": (a.rms() / fl) if a.rms() is not None else None,
                                 "max_abs": a.maxabs}) for name, a in diff.items()),
            "fold": dict((name, {"rms": a.rms(), "ratio_to_floor": (a.rms() / fl) if a.rms() is not None else None})
                         for name, a in fold.items())}
    return out


def settled(result):
    """The pre-registered rule on one capture: every band, every 32-tap candidate, RMS below the floor."""
    return all(d["rms"] is not None and d["rms"] < b["floor_rms"]
               for b in result["bands"].values() for d in b["diff"].values())


def worst_ratio(results):
    """The largest RMS / floor over the captures, bands and 32-tap references of one design."""
    return max(d["ratio_to_floor"] for r in results for b in r["bands"].values() for d in b["diff"].values())


def choose(by_beta):
    """The registered choice: {beta: [capture results]} -> (beta, worst) of the passing beta with the smallest worst
    cell, ties to the larger beta; or (None, None) when none passes -- the fallback, 32 taps."""
    passing = [(worst_ratio(rs), -beta, beta) for beta, rs in by_beta.items() if all(settled(r) for r in rs)]
    if not passing:
        return None, None
    w, _nb, beta = min(passing)
    return beta, w


def sweep(runs_by_capture, grid=BETA_GRID):
    """Every beta of the grid at 16 taps against both 32-tap candidates, on every capture given ({name: runs})."""
    names = sorted(runs_by_capture)
    by_beta = dict((beta, [measure(runs_by_capture[n], (16, beta), per_phase=True) for n in names]) for beta in grid)
    out = {"grid": list(grid), "captures": names, "betas": {}}
    for beta, rs in by_beta.items():
        out["betas"]["%.2f" % beta] = {
            "settled": all(settled(r) for r in rs), "worst_ratio": worst_ratio(rs),
            "ratios": dict((n, dict((B, dict((k, d["ratio_to_floor"]) for k, d in b["diff"].items()))
                                    for B, b in r["bands"].items())) for n, r in zip(names, rs))}
    beta, w = choose(by_beta)
    out["chosen_beta"], out["chosen_worst"] = beta, w
    out["fallback_32_taps"] = beta is None
    return out


# ---- the captures ---------------------------------------------------------------------------------------------------

def x_of_block(blk):
    return [float(r["wa"] + r["wb"]) for r in
            (v123frame.slice_record(blk[i * 256:(i + 1) * 256]) for i in range(16))]


def tone_runs(name):
    kind, path = v123frame.CAPTURES[name]
    return [[v for blk in blocks for v in x_of_block(blk)] for _w, blocks in v123frame.load(kind, path)]


def game_runs():
    kind, path = v123frame.CAPTURES["RUN43"]
    if not os.path.isfile(path):
        return None
    h, blocks = u012game.load(path)
    S = u012game.slice_table(blocks)
    fit = u012game.solve(u012game.transitions(S))
    return [[v for blk in blocks[a:b] for v in x_of_block(blk)] for a, b in u012game.runs(fit["G"])]


def analyse():
    res = {}
    for name in ("RUN33", "RUN34"):
        res[name] = measure(tone_runs(name))
    g = game_runs()
    res["RUN43"] = measure(g) if g is not None else None
    present = [r for r in res.values() if r is not None]
    return {"captures": res, "settled_16": all(settled(r) for r in present),
            "captures_present": sorted(k for k, v in res.items() if v is not None)}


def analyse_sweep():
    runs = dict((n, tone_runs(n)) for n in ("RUN33", "RUN34"))
    g = game_runs()
    if g is not None:
        runs["RUN43"] = g
    return sweep(runs)


def main_sweep(argv):
    r = analyse_sweep()
    for beta, b in sorted(r["betas"].items(), key=lambda kv: float(kv[0])):
        cells = "; ".join("%s %s" % (n, " ".join("%s:%s" % (B, "/".join("%.3f" % v for _k, v in sorted(d.items())))
                                                   for B, d in sorted(rb.items(), key=lambda kv: float(kv[0]))))
                          for n, rb in sorted(b["ratios"].items()))
        print("beta %s  %s  worst %.4f   %s" % (beta, "PASS" if b["settled"] else "fail", b["worst_ratio"], cells))
    if r["fallback_32_taps"]:
        print("no beta passes on %s: the registered fallback, 32 taps" % ", ".join(r["captures"]))
    else:
        print("chosen: beta %.2f, worst cell %.4f of the floor (captures %s)" % (
            r["chosen_beta"], r["chosen_worst"], ", ".join(r["captures"])))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(r, f, sort_keys=True)
    return 0


def main(argv):
    if "--sweep" in argv:
        return main_sweep(argv)
    r = analyse()
    for name, c in r["captures"].items():
        if c is None:
            print("%s: absent in this checkout (captures/local is ignored)" % name)
            continue
        print("%s: %d runs, %d inputs" % (name, c["runs"], c["inputs"]))
        for B, b in c["bands"].items():
            print("  [0, %s Hz]: floor %.4f steps RMS; signal (16 taps) %.3f; %d segments" % (
                B, b["floor_rms"], b["signal_rms_16"], b["segments"]))
            for name2, d in b["diff"].items():
                print("    16 - %-10s RMS %.6f = %.4f x floor; max |d| %.4f steps" % (
                    name2, d["rms"], d["ratio_to_floor"], d["max_abs"]))
            for name2, f in b["fold"].items():
                print("    fold-in %-10s RMS %.6f = %.4f x floor" % (name2, f["rms"], f["ratio_to_floor"]))
    print("16 taps SETTLED ON EVIDENCE: %s (captures %s)" % (r["settled_16"], ", ".join(r["captures_present"])))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(r, f, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
