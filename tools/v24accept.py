#!/usr/bin/env python3
"""
tools/v24accept.py — the gates of HARDWARE_TESTS.md §V24 (GitHub Issue #105), Run B: split `produce`,
hold total work constant, and separate CAUSE from ACCOMMODATION.

    tools/v24accept.py <report JSON> [--json <out>]

FROZEN BEFORE THE IMAGE EXISTS, on synthetic vectors only (tests/host/test_v24accept.py). Everything §V24.6
carries over from §V23 -- the observer gate and its bounds, the `recorder` category, the attribution rule,
QUESTION P's no-pass/fail, §V23.7's VIDEO gap, QUESTION K -- is computed by the FROZEN tools/v23accept.py
and not re-implemented here. Only the interleaved variable and QUESTION S are new.

QUESTION S (§V24.2, with §V24.7's confirmed readings (r1)-(r8) and its three additions)

  THE ARMS   each AI chunk is produced in 16-push steps (FULL) or 8-push steps (HALF), pair-balanced: chunks
             2j and 2j+1 take opposite arms, and which comes first is bit j of xorshift32 seeded 0x9E3779B9
             (r6). Every production step carries its chunk's arm, a first-step mark and seq mod 64 in its
             spare byte; the host rebuilds the sequence and REFUSES the run -- INCONCLUSIVE, never a FAIL --
             if the tags disagree, or if the step records overflowed. Checked before any verdict.
  CYCLES     a cycle is the span between two AI callbacks; it takes the arm of the one chunk whose production
             steps fall in it (r5). No production step, steps of two chunks, or the last, open cycle: excluded
             and COUNTED. A loss maps to the cycle of the callback entry before its completion tick.
  NEITHER    the half arm's kept production steps are not at about half the full arm's: median OR p90 ratio
             > 0.60 (a chosen allowance: the per-call overhead doubles in count)
  INCONCLUSIVE  the observer gate fails, or the FULL arm has fewer than 250 loss gaps in the analysed cycles
             (r3). A LOW HALF ARM IS THE FINDING, NEVER A FAILURE.
  CAUSE      the half arm has fewer loss gaps per cycle: permutation over the analysed cycles, statistic
             mean(half) - mean(full), 20 000 permutations, seed 24, one-sided p = fraction <= observed,
             alpha = 0.05 (r2). Reported with its CI, so a small one reads as small (r4).
  ACCOMMODATION  the 90 % CI of mean(half)/mean(full) -- a bootstrap over cycles within each arm, percentile,
             20 000 resamples, seed 24 (r1) -- lies entirely above 0.90: a reduction larger than 10 % is
             ruled out
  UNRESOLVED neither CAUSE nor ACCOMMODATION. With no true effect this happens ~20 % of the time BY DESIGN
             (the A/A check on RUN 39, §V24.7): it is a likely outcome, not a run gone wrong.
  PRECEDENCE refusal -> NEITHER -> INCONCLUSIVE -> CAUSE -> ACCOMMODATION -> UNRESOLVED (r4)

REPORTED BESIDE THE VERDICT, per arm, at p10 p25 p50 p75 p90 p99 (r7; the element at floor(q (n - 1)) of the
sorted values): the production stretch (kept production step durations), the loss-gap lengths, and the
lengths of no-loss gaps that hold a kept production step (r8). The excluded cycles with their reasons. The
aggregate rate as CONTEXT with RUN 38's 25.41/s and RUN 39's 27.86/s, between-run variation unknown (§V24.3).

THE REPORT is tools/v23accept.py's, plus:
  "step_tag":  [int per step in "steps"]   the spare byte: bit 0 arm (1 = HALF), bit 1 a chunk's first step,
                                            bits 2..7 the chunk's seq mod 64; 0 for a step that is not produce
  "trace":     {"dropped": {"step_dropped": int, ...}, ...}   as tools/v23report.py writes it

Standard library only. Reads the report it is given; writes nothing unless asked.
"""
import bisect
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import v23accept  # noqa: E402

TB_HZ = 40500000
XS_SEED = 0x9E3779B9
HALF, FULL = 1, 0
HALF_PUSHES, FULL_PUSHES = 8, 16
NEITHER_RATIO_MAX = 0.60        # §V24.2: a CHOSEN allowance, the per-call overhead doubles in count
S_ALPHA = 0.05                  # §V24.2
ACCOMM_CI_LOW = 0.90            # §V24.2: a reduction larger than 10 % ruled out
CI_Q = (0.05, 0.95)             # the 90 % percentile interval (r1)
S_TRIALS = 20000                # (r1), (r2)
S_SEED = 24                     # (r1), (r2)
FULL_MIN_LOSSES = 250           # (r3): |log 0.8| / (1.645 + 0.84) = 0.0898 -> 2 / SE^2 = 248 -> 250
QS = (0.10, 0.25, 0.50, 0.75, 0.90, 0.99)   # (r7)
RUN38_RATE, RUN39_RATE = 25.41, 27.86       # §V24.3: context only


def _xorshift32(x):
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= x >> 17
    x ^= (x << 5) & 0xFFFFFFFF
    return x & 0xFFFFFFFF


def arms(n):
    """The frozen assignment of chunks 0..n-1: HALF (1) or FULL (0)."""
    out, words, x = [], [], XS_SEED
    for seq in range(n):
        j = seq // 2
        while len(words) <= j // 32:
            x = _xorshift32(x)
            words.append(x)
        bit = (words[j // 32] >> (j % 32)) & 1
        out.append(bit if seq % 2 == 0 else 1 - bit)
    return out


def quantiles(values):
    v = sorted(values)
    if not v:
        return None
    return dict(("p%d" % round(q * 100), v[int(q * (len(v) - 1))]) for q in QS)


def _refuse(why):
    return {"verdict": "INCONCLUSIVE", "why": why, "refused": True}


def question_S(report, base, trials=S_TRIALS):
    steps, tags = report.get("steps", []), report.get("step_tag")
    if tags is None or len(tags) != len(steps):
        return _refuse("the report carries no arm tag for every step: the arms cannot be read")
    if report.get("trace", {}).get("dropped", {}).get("step_dropped", 0):
        return _refuse("the step records overflowed: the arm tags cannot be verified (§V24.7)")
    # (r6): rebuild the chunk sequence from the first-step marks and check every production step's tag
    seq, seqs, prod = -1, [], []
    for s, tag in zip(steps, tags):
        if s[2] != "produce":
            continue
        if tag & 2:
            seq += 1
        if seq < 0:
            return _refuse("a production step precedes the first chunk's first step: the tags are unreadable")
        seqs.append(seq)
        prod.append((s, tag))
    want = arms(seq + 1)
    for (s, tag), q in zip(prod, seqs):
        if (tag >> 2) & 63 != q & 63 or (tag & 1) != want[q]:
            return _refuse("the image's arm tag disagrees with the frozen assignment at chunk %d (§V24.7 (r6))" % q)

    # (r5): cycles and their arms
    ent = sorted(c[0] for c in report.get("callbacks", []))
    ncyc = max(0, len(ent) - 1)
    chunks = [set() for _ in range(ncyc)]
    for (s, _tag), q in zip(prod, seqs):
        c = bisect.bisect_right(ent, s[0]) - 1
        if 0 <= c < ncyc:
            chunks[c].add(q)
    arm_of, excluded = {}, {"no_production_step": 0, "two_chunks_steps": 0, "open_last_cycle": 1 if ent else 0}
    for c in range(ncyc):
        if not chunks[c]:
            excluded["no_production_step"] += 1
        elif len(chunks[c]) > 1:
            excluded["two_chunks_steps"] += 1
        else:
            arm_of[c] = want[next(iter(chunks[c]))]

    # losses per analysed cycle
    a = report["audio"]
    losses = v23accept.audio_losses(a["decoded"], a["ticks"])
    count = dict((c, 0) for c in arm_of)
    loss_len = {HALF: [], FULL: []}
    outside = 0
    for x in losses:
        c = bisect.bisect_right(ent, x["t"]) - 1
        if c in count:
            count[c] += 1
            loss_len[arm_of[c]].append((x["g1"] - x["g0"]) / (TB_HZ / 4096.0))
        else:
            outside += 1

    # the stretch: kept production step durations, by arm
    stretch = {HALF: [], FULL: []}
    for (s, tag), q in zip(prod, seqs):
        stretch[want[q]].append(s[1] - s[0])
    # (r8): no-loss gaps that hold a kept production step, by the arm of the cycle holding the gap's end
    lossg = set((x["g0"], x["g1"]) for x in losses)
    starts = [s[0] for s, _t in prod]
    ticks = a["ticks"]
    noloss = {HALF: [], FULL: []}
    for i in range(len(ticks) - 1):
        g0, g1 = ticks[i], ticks[i + 1]
        if (g0, g1) in lossg:
            continue
        c = bisect.bisect_right(ent, g1) - 1
        if c not in arm_of:
            continue
        k = bisect.bisect_left(starts, g0 - 200000)
        while k < len(prod) and prod[k][0][0] <= g1:
            if min(g1, prod[k][0][1]) > max(g0, prod[k][0][0]):
                noloss[arm_of[c]].append((g1 - g0) / (TB_HZ / 4096.0))
                break
            k += 1

    h_counts = [count[c] for c in sorted(count) if arm_of[c] == HALF]
    f_counts = [count[c] for c in sorted(count) if arm_of[c] == FULL]
    per_arm = {}
    for name, arm, cnt in (("half", HALF, h_counts), ("full", FULL, f_counts)):
        per_arm[name] = {"cycles": len(cnt), "loss_gaps": sum(cnt),
                         "mean_per_cycle": (sum(cnt) / float(len(cnt))) if cnt else None,
                         "stretch_ticks": quantiles(stretch[arm]), "stretch_steps": len(stretch[arm]),
                         "loss_gap_T": quantiles(loss_len[arm]),
                         "noloss_production_gap_T": quantiles(noloss[arm]), "noloss_production_gaps": len(noloss[arm])}
    obs = base["observer"]
    out = {"refused": False, "arms_checked_chunks": seq + 1, "excluded_cycles": excluded,
           "losses_outside_analysed_cycles": outside, "arms": per_arm,
           "context_rate": {"this_run": obs.get("mean_undrained"), "RUN 38": RUN38_RATE, "RUN 39": RUN39_RATE,
                            "note": "context only: between-run variation is unknown from these runs (§V24.3)"}}

    # NEITHER
    sh, sf = per_arm["half"]["stretch_ticks"], per_arm["full"]["stretch_ticks"]
    if not sh or not sf:
        out.update(verdict="NEITHER", why="an arm has no kept production step: the variable cannot be seen to take")
        return out
    r_med, r_p90 = sh["p50"] / float(sf["p50"]), sh["p90"] / float(sf["p90"])
    out["stretch_ratio"] = {"median": r_med, "p90": r_p90, "max": NEITHER_RATIO_MAX}
    if r_med > NEITHER_RATIO_MAX or r_p90 > NEITHER_RATIO_MAX:
        out.update(verdict="NEITHER", why="the stretches did not halve (median ratio %.3f, p90 ratio %.3f, max %.2f): "
                                          "the variable did not take, and the gaps are not read" % (r_med, r_p90,
                                                                                                  NEITHER_RATIO_MAX))
        return out
    # INCONCLUSIVE
    if not obs.get("sanity_ok"):
        out.update(verdict="INCONCLUSIVE", why="the observer gate failed (§V23.3, carried over by §V24.6)")
        return out
    if per_arm["full"]["loss_gaps"] < FULL_MIN_LOSSES:
        out.update(verdict="INCONCLUSIVE", why="the FULL arm has %d loss gaps in the analysed cycles, fewer than %d "
                                               "(r3): the test is not powered" % (per_arm["full"]["loss_gaps"],
                                                                                  FULL_MIN_LOSSES))
        return out
    # CAUSE: the permutation (r2)
    counts = h_counts + f_counts
    nh = len(h_counts)
    mean = lambda v: sum(v) / float(len(v))
    obs_d = mean(h_counts) - mean(f_counts)
    rng = random.Random(S_SEED)
    idx = list(range(len(counts)))
    hits = 0
    for _ in range(trials):
        rng.shuffle(idx)
        sh_ = sum(counts[i] for i in idx[:nh])
        d = sh_ / float(nh) - (sum(counts) - sh_) / float(len(counts) - nh)
        if d <= obs_d:
            hits += 1
    p = hits / float(trials)
    # the CI (r1)
    rng = random.Random(S_SEED)
    ratios = []
    for _ in range(trials):
        bh = sum(rng.choices(h_counts, k=len(h_counts))) / float(len(h_counts))
        bf = sum(rng.choices(f_counts, k=len(f_counts))) / float(len(f_counts))
        ratios.append(bh / bf if bf else float("inf"))
    ratios.sort()
    ci = (ratios[int(CI_Q[0] * (trials - 1))], ratios[int(CI_Q[1] * (trials - 1))])
    ratio = mean(h_counts) / mean(f_counts) if mean(f_counts) else float("inf")
    out.update(p=p, ratio=ratio, ci90=list(ci), trials=trials, difference_per_cycle=obs_d)
    if p < S_ALPHA:
        out.update(verdict="CAUSE", why="the half arm has fewer loss gaps per cycle: ratio %.3f, 90 %% CI [%.3f, %.3f], "
                                        "one-sided permutation p = %.5f < %.2f" % (ratio, ci[0], ci[1], p, S_ALPHA))
    elif ci[0] > ACCOMM_CI_LOW:
        out.update(verdict="ACCOMMODATION", why="the stretch halved and the 90 %% CI [%.3f, %.3f] of the half/full loss "
                                                "ratio lies entirely above %.2f: a reduction larger than 10 %% is ruled "
                                                "out" % (ci[0], ci[1], ACCOMM_CI_LOW))
    else:
        out.update(verdict="UNRESOLVED", why="neither CAUSE (p = %.5f) nor ACCOMMODATION (90 %% CI [%.3f, %.3f]): the "
                                             "run lacked the precision to separate them; ~20 %% likely by design even "
                                             "with no effect" % (p, ci[0], ci[1]))
    return out


def evaluate(report, trials=S_TRIALS, k_trials=v23accept.K_TRIALS):
    base = v23accept.evaluate(report, k_trials)
    base["S"] = question_S(report, base, trials)
    return base


def _q(d):
    return "  ".join("%s %s" % (k, ("%.2f" % v) if isinstance(v, float) else v) for k, v in d.items()) if d else "-"


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        report = json.load(f)
    r = evaluate(report)
    s = r["S"]
    print("%s / %s" % (r["test_id"], r["build_id"]))
    o = r["observer"]
    print("  OBSERVER  SANITY mean undrained %s /s (<= %.1f); %s %s (<= %d) -> %s   PRIMARY %s"
          % (None if o["mean_undrained"] is None else "%.2f" % o["mean_undrained"], o["mean_undrained_max"],
             o["frames_scope"], o["frames"], o["frames_max"], "HOLDS" if o["sanity_ok"] else "FAILS",
             json.dumps(o["primary"], sort_keys=True)))
    print("  P   %s   %s" % (r["P"]["decision"], json.dumps(r["P"]["counts"], sort_keys=True)))
    print("  K   %s   %s" % (r["K"]["verdict"], r["K"]["why"]))
    print("  S   %-14s %s" % (s["verdict"], s["why"]))
    if not s.get("refused"):
        print("      excluded cycles: %s; losses outside analysed cycles %d"
              % (json.dumps(s["excluded_cycles"], sort_keys=True), s["losses_outside_analysed_cycles"]))
        for name in ("half", "full"):
            a = s["arms"][name]
            print("      %s  cycles %d  loss gaps %d  mean/cycle %s" % (name, a["cycles"], a["loss_gaps"],
                  None if a["mean_per_cycle"] is None else "%.4f" % a["mean_per_cycle"]))
            print("            stretch (ticks, %d steps)  %s" % (a["stretch_steps"], _q(a["stretch_ticks"])))
            print("            loss-gap length (T)        %s" % _q(a["loss_gap_T"]))
            print("            no-loss production gap (T, %d)  %s" % (a["noloss_production_gaps"],
                                                                      _q(a["noloss_production_gap_T"])))
        c = s["context_rate"]
        print("      CONTEXT, not the discriminator: this run %s /s; RUN 38 %.2f /s; RUN 39 %.2f /s -- %s"
              % (None if c["this_run"] is None else "%.2f" % c["this_run"], c["RUN 38"], c["RUN 39"], c["note"]))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(r, f, sort_keys=True, default=list)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
