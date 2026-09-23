#!/usr/bin/env python3
"""
tools/v19drain.py — §V19's three gates, frozen BEFORE the run (GitHub Issue #84).

    tools/v19drain.py <report.json>

GBP-AUDIO-005. This module decides `QUESTION D1`, reports `QUESTION D2` and
decides `QUESTION A`, exactly as `HARDWARE_TESTS.md` §V19 and its two
pre-hardware amendments freeze them. It is written before the POC produces any
data and is exercised on SYNTHETIC vectors only
(`tests/host/test_v19drain.py`). Nothing here may be edited once data exists.

TERMINOLOGY, which §V19 AMENDMENT 1 A1 makes binding because the collision has
already cost this project premise errors:

    DMA GRANULE   32 bytes   -- GBP_BLOCK_SIZE, the transport's alignment unit
    AUDIO BLOCK   4096 bytes -- one H-PWM sample (GBP-HW-313)

"block" unqualified is never used below.

WHAT IS FROZEN HERE AND WHY EACH PART IS:

  D1  fixed 1.000 s windows, the first starting at exactly 3.000 s into PHASE B,
      boundaries in TICKS of the 40.5 MHz timebase (AMENDMENT 2 B2 -- one
      millisecond is 4.096 AUDIO blocks, which is the entire margin, so a
      millisecond boundary could hide all of it). expected(w) = 4096 by
      construction.

      AMENDMENT 1 A6 reads "a window that misses by one AUDIO block IS A FAIL",
      which admits two readings 3.096 AUDIO blocks apart: a literal one (any
      window under 4096 fails, i.e. an effective threshold of 0.99976) and the
      one where the +-1-block boundary noise may not RESCUE a window that has
      fallen under the threshold. AMENDMENT 2 B5 settles it in the second sense
      and twice over -- "the threshold cannot see a uniform shortfall below
      4.096 blocks/s", and "a PASS shall never be reported as 'no loss', only as
      'no window lost more than 4.096 blocks'". Neither sentence is true of the
      literal reading. So the threshold is 0.999 and A6 forbids the post-hoc
      rescue, which is what "stated in advance so it cannot be argued later"
      is for. The ambiguity is recorded in §V19.9 rather than resolved silently.

  D2  NO pass/fail. Nobody has measured an SD write during a drain, so any
      threshold now would be a number chosen to be met. What IS frozen is the
      rule it feeds: the decoded ring holds at least TWICE the largest stall.

  A   the gate is SEQUENCE synchronisation, never within-AUDIO-block fidelity
      (AMENDMENT 1 A7). Edge degradation is measured beside it and is never a
      PASS. A failed positive control gives INCONCLUSIVE, never SYNC-LOST
      (AMENDMENT 2 B3): "nothing was playing" and "the short read broke it" are
      different answers.

Standard library only. Reads a report; writes nothing; authorises nothing.
"""
import json
import os
import sys

# ---------------------------------------------------------------- frozen constants

TB_HZ = 40500000            # the console timebase every §V19 boundary is counted in
AUDIO_BLOCK = 4096          # bytes; one H-PWM sample
DMA_GRANULE = 32            # bytes; GBP_BLOCK_SIZE, the transport's alignment unit
RATE = 4096                 # AUDIO blocks per second (GBP-HW-301)

D1_START_S = 3.0            # the first window begins here, measured from PHASE B's start
D1_WINDOW_TICKS = TB_HZ     # exactly 1.000 s
D1_EXPECTED = 4096          # by construction of the window (AMENDMENT 2 B2)
D1_THRESHOLD = 0.999        # AMENDMENT 2 B5: stays here, and what it cannot see is stated.
                            # 0.999 x 4096 = 4092.1, so a window FAILS from 5 AUDIO blocks short.
                            # A6's +-1 boundary noise is 24.4 % of that margin and may not be
                            # invoked to rescue a window that has fallen under it.
D1_MIN_PHASE_S = 60.0       # PHASE B shorter than this is INCONCLUSIVE
D1_COUNTER_TOLERANCE = 1    # AUDIO blocks; timebase vs counter over the whole phase

N_SWEEP = (0x20, 0x100, 0x400)     # AMENDMENT 1 A1: all legal multiples of the DMA granule

_PC = [bin(i).count("1") for i in range(256)]


# ------------------------------------------------------------------- the short read

def sample_from_short_read(data, n=None):
    """AMENDMENT 2 B4, frozen: sample(N) = popcount(the N bytes actually read) * 4096/N.

    Exact on flat AUDIO blocks and NEVER at an edge (§V18.5). The PERIOD is
    unaffected either way, because it is carried by the sequence of levels and not
    by any one AUDIO block's value -- which is why QUESTION A reads sequence and
    not fidelity."""
    if n is None:
        n = len(data)
    if n <= 0 or n > AUDIO_BLOCK or n % DMA_GRANULE != 0:
        raise ValueError("N must be a positive multiple of the %d-byte DMA granule, at most one "
                         "AUDIO BLOCK: %r" % (DMA_GRANULE, n))
    return sum(_PC[b] for b in data[:n]) * AUDIO_BLOCK // n


def legal_n(n):
    """The transport's own rule (gbp_transport.c:62, hsp_backend.c:78): a positive
    multiple of the DMA granule, no larger than one AUDIO block."""
    return isinstance(n, int) and 0 < n <= AUDIO_BLOCK and n % DMA_GRANULE == 0


# ------------------------------------------------------------------- QUESTION D1

def d1_windows(counts, start_tick, first_tick=None):
    """The whole 1.000 s windows of PHASE B from t = 3.000 s on.

    `counts` is a list of (dma_completion_tick,) counts already bucketed by the POC:
    one u32 per second of PHASE B. `start_tick` is PHASE B's first tick. The final
    incomplete window is DISCARDED (AMENDMENT 1 A6), decided before the data."""
    t0 = start_tick + int(D1_START_S * TB_HZ)
    skip = (t0 - start_tick) // D1_WINDOW_TICKS
    whole = counts[skip:]
    if first_tick is not None and first_tick > t0:
        raise ValueError("PHASE B's counter starts after the first window")
    return whole


def question_D1(counts, phase_s, counter_total=None, timebase_total=None):
    """§V19.2 with AMENDMENT 2 B2 and B5.

    `counts`: one AUDIO-block count per second of PHASE B, in order, from its start.
    `phase_s`: PHASE B's measured length in seconds.
    `counter_total` / `timebase_total`: the two independent totals, compared for the
    INCONCLUSIVE arm.

    Returns the verdict AND the full per-second series, which §V19 requires to be
    reported beside it whether it passes or fails."""
    out = {"threshold": D1_THRESHOLD, "expected_per_window": D1_EXPECTED,
           "phase_s": phase_s, "windows": [], "worst": None, "verdict": None, "why": ""}
    if phase_s < D1_MIN_PHASE_S:
        out.update(verdict="INCONCLUSIVE", why="PHASE B ran %.3f s, under the frozen %.1f s"
                                               % (phase_s, D1_MIN_PHASE_S))
        return out
    if counter_total is not None and timebase_total is not None:
        if abs(counter_total - timebase_total) > D1_COUNTER_TOLERANCE:
            out.update(verdict="INCONCLUSIVE",
                       why="the timebase and the counter disagree by %d AUDIO blocks over the phase "
                           "(tolerance %d)" % (abs(counter_total - timebase_total), D1_COUNTER_TOLERANCE))
            return out
    whole = counts[int(D1_START_S):]
    if not whole:
        out.update(verdict="INCONCLUSIVE", why="no whole window exists at or after t = 3.000 s")
        return out
    rows = [{"window": i, "t_start_s": D1_START_S + i, "read": c,
             "coverage": c / float(D1_EXPECTED)} for i, c in enumerate(whole)]
    out["windows"] = rows
    worst = min(rows, key=lambda r: r["coverage"])
    out["worst"] = worst
    bad = [r for r in rows if r["coverage"] < D1_THRESHOLD]
    if bad:
        out.update(verdict="FAIL",
                   why="%d of %d windows below %.3f; worst window %d at %.5f (%d AUDIO blocks)"
                       % (len(bad), len(rows), D1_THRESHOLD, worst["window"], worst["coverage"], worst["read"]))
        return out
    # AMENDMENT 2 B5: a PASS is never "no loss"; it is a bound, and the bound is said
    out.update(verdict="PASS",
               why="no window lost more than %.3f AUDIO blocks (worst window %d at %.5f). "
                   "This does NOT mean no loss: a UNIFORM shortfall below %.3f blocks/s passes "
                   "this gate, and the per-second series is reported in full for that reason."
                   % (D1_EXPECTED * (1 - D1_THRESHOLD), worst["window"], worst["coverage"],
                      D1_EXPECTED * (1 - D1_THRESHOLD)))
    return out


def d1_uniform_shortfall_blind_spot(blocks_short, over_s):
    """AMENDMENT 2 B5, stated as code so it cannot be forgotten: what a uniform
    shortfall of `blocks_short` AUDIO blocks over `over_s` seconds does to the gate."""
    per_window = blocks_short / float(over_s)
    return {"per_window": per_window, "coverage": (D1_EXPECTED - per_window) / float(D1_EXPECTED),
            "passes": (D1_EXPECTED - per_window) / float(D1_EXPECTED) >= D1_THRESHOLD,
            "margin_blocks": D1_EXPECTED * (1 - D1_THRESHOLD)}


# ------------------------------------------------------------------- QUESTION D2

def question_D2(before, after, write_bytes, gap_blocks):
    """§V19.3. A MEASUREMENT, with no pass/fail on purpose: there is no prior value
    to test against, and inventing a threshold now would be a number chosen to be met.

    What IS frozen is the decision rule this feeds."""
    lost = gap_blocks
    return {"verdict": "MEASURED", "write_bytes": write_bytes,
            "blocks_lost": lost, "wall_ms": lost * 1000.0 / RATE,
            "coverage_before": before, "coverage_after": after,
            "ring_minimum_blocks": 2 * lost,
            "rule": "the decoded ring buffer shall hold at least TWICE the largest stall "
                    "measured here (§V19.3), and the POC that follows states its capacity "
                    "in those units"}


# -------------------------------------------------------------------- QUESTION A

def question_A(steps, control_before_phase, recovered):
    """§V19.4 with AMENDMENT 2 B3.

    `steps`: in sweep order, dicts with n, programmed_period, periods (the decoded
    periods seen across the step) and edge_recoverable (the fraction of one-step
    AUDIO blocks whose step index is still recoverable).
    `control_before_phase`: did the positive control taken IMMEDIATELY BEFORE the
    phase pass? A failure here is INCONCLUSIVE, never SYNC-LOST.
    `recovered`: did full AUDIO-block reads afterwards return to SYNC-OK?"""
    out = {"verdict": None, "why": "", "steps": [], "recovery": None}
    if not control_before_phase:
        out.update(verdict="INCONCLUSIVE",
                   why="the positive control immediately before PHASE A did not pass: the tone was "
                       "not established, so a desynchronised reading would be unattributable. "
                       "'Nothing was playing' and 'the short read broke it' are different answers "
                       "(§V19 AMENDMENT 2 B3). PHASE B and PHASE C remain valid.")
        return out
    for s in steps:
        if not legal_n(s["n"]):
            raise ValueError("N=%r is not a multiple of the %d-byte DMA granule" % (s["n"], DMA_GRANULE))
        periods = list(s["periods"])
        ok = bool(periods) and min(periods) == max(periods) == s["programmed_period"]
        row = {"n": s["n"], "programmed_period": s["programmed_period"],
               "period_min": min(periods) if periods else None,
               "period_max": max(periods) if periods else None,
               "sync": "SYNC-OK" if ok else "SYNC-LOST",
               # reported, NEVER folded into the verdict (§V19.4, AMENDMENT 1 A7)
               "edge_recoverable": s.get("edge_recoverable")}
        out["steps"].append(row)
        if not ok:
            out["recovery"] = "RECOVERS" if recovered else "NO-RECOVERY"
            out.update(verdict="SYNC-LOST",
                       why="N=0x%X lost sequence synchronisation (period %s..%s against the programmed %d); "
                           "the sweep stops at the first SYNC-LOST. %s"
                           % (s["n"], row["period_min"], row["period_max"], s["programmed_period"],
                              "Full reads recovered." if recovered else
                              "FULL READS DID NOT RECOVER: the remaining phases are void, power-cycle."),
                       )
            return out
    out["recovery"] = "RECOVERS" if recovered else "NO-RECOVERY"
    out.update(verdict="SYNC-OK",
               why="every N in the sweep held the programmed period exactly. This is SEQUENCE "
                   "synchronisation only: it does NOT mean the audio is intact within an AUDIO "
                   "block, and the edge-degradation figures beside it are the within-block answer "
                   "(§V19 AMENDMENT 1 A7).")
    return out


# ------------------------------------------------------------------------- report

def evaluate(report):
    """The three gates over one POC report."""
    b, c, a = report["phase_b"], report.get("phase_c"), report.get("phase_a")
    out = {"test_id": report.get("test_id"), "build_id": report.get("build_id"),
           "D1": question_D1(b["counts"], b["phase_s"], b.get("counter_total"), b.get("timebase_total"))}
    if c:
        out["D2"] = question_D2(c.get("coverage_before"), c.get("coverage_after"),
                                c.get("write_bytes"), c.get("gap_blocks"))
    if a:
        out["A"] = question_A(a["steps"], a["control_before_phase"], a.get("recovered", False))
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        r = evaluate(json.load(f))
    print("%s / %s" % (r.get("test_id"), r.get("build_id")))
    d1 = r["D1"]
    print("  D1 %-13s %s" % (d1["verdict"], d1["why"]))
    if d1["windows"]:
        print("     per-second coverage (reported IN FULL, PASS or FAIL):")
        for row in d1["windows"]:
            print("       t=%6.1f s  %5d  %.5f" % (row["t_start_s"], row["read"], row["coverage"]))
    if "D2" in r:
        d2 = r["D2"]
        print("  D2 %-13s %d AUDIO blocks = %.2f ms for a %d-byte write; ring >= %d blocks"
              % (d2["verdict"], d2["blocks_lost"], d2["wall_ms"], d2["write_bytes"], d2["ring_minimum_blocks"]))
    if "A" in r:
        qa = r["A"]
        print("  A  %-13s %s" % (qa["verdict"], qa["why"]))
        for s in qa["steps"]:
            print("       N=0x%-5X %-9s period %s..%s  edges recoverable %s"
                  % (s["n"], s["sync"], s["period_min"], s["period_max"], s["edge_recoverable"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
