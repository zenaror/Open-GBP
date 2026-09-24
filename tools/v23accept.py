#!/usr/bin/env python3
"""
tools/v23accept.py — the gates of HARDWARE_TESTS.md §V23 (GitHub Issue #101), Run A: which step of the
AI chunk cycle starves the service path, and do the two losses coincide.

    tools/v23accept.py <report.json>

FROZEN with §V23's text, in the same commit, before the image exists, and exercised on synthetic
vectors only (tests/host/test_v23accept.py). It reads a report it does not know how to make; the
image's report builder makes it. It decides only what §V23 says it decides.

WHAT IT COMPUTES, §V23 by section

  §V23.1  every AUDIO loss, located with NO threshold. The window's decoded stream is kept whole. It
          is a 128 Hz square wave of 16-sample half-periods: 15 plateau samples and one step sample.
          A half-period of 16 - k samples holds k undrained blocks. The loss is timed from the largest
          completion gap inside that half, at the completion that ENDS it (reading (t) of §V23.8).
  §V23.7  every VIDEO gap. Frames are bounded by their frame-start blocks. A frame of 40m - k blocks
          (m frames by its duration) has its k missing blocks at its k largest gaps between
          consecutive completions. The gap before a frame-start block is the vblank and never counts.
          Each is timed at the completion after the gap. Beside it is the confidence: the frame's
          largest intra-frame gap over its second largest.
  §V23.2  QUESTION K. For every VIDEO gap, the distance to the nearest AUDIO loss; coincident within
          one AUDIO block period. The null keeps each VIDEO gap's phase after its preceding callback
          and moves it to another callback cycle, reading (k). COINCIDENT at p < 0.001. The uniform
          null is printed, labelled. A KNOWN, ACCEPTED PROPERTY: drawing only callbacks whose shifted
          time stays inside the AUDIO span biases the draw slightly toward the interior.
  §V23.3  QUESTION P. Every AUDIO loss is attributed to a named chain step, the ISR window, the
          recorder or `neither`, by the longest overlap with the loss's gap interval, reading (a).
          The tie order -- recorder, ISR, then the steps -- is deliberate: it biases AGAINST naming
          the chain, which is the conservative direction for an observer-effect concern.
          It has no pass/fail; the decision rule's words are reading (n). THE OBSERVER GATE: the
          recorder's self-cost is PRIMARY, reported with no threshold (reading (s)). The count bound
          is the SANITY check: a mean undrained of at most 31.8 blocks/s, and the window's incomplete
          frames at most 86 (reading (f)), or whole-session FRAMECAP at most 99 where the window's
          records are absent.

THE REPORT (JSON; every tick in the console's 40.5 MHz timebase)

  {"test_id", "build_id", "commit", "tb_hz",
   "window":    {"t_origin", "t_end", "coverage": [blocks drained per whole 1.000 s],
                 "framecap_session": int or null},
   "audio":     {"ticks": [completion tick per decoded sample], "decoded": [int16 per sample]},
   "video":     {"ticks": [completion tick per VIDEO block], "start": [1 if a frame-start block]},
                                                   over the WHOLE session, so reading (f)'s premise can
                                                   be tested: where the incomplete frames fall
   "ai_span":   [t_ai_start, t_ai_stop],
   "callbacks": [[entry, exit], ...]               every AI DMA callback in the window
   "steps":     [[start, end, kind, rec_end], ...] kind in STEP_KINDS; [end, rec_end] is the
                                                   recorder's own write of this record
   "recorder":  {"tap_ticks_per_cycle": [...], "tap_max_write": int}   the per-block stores in the
                                                   taps, which are too many to keep one by one}

Standard library only. Reads the report it is given; writes nothing.
"""
import bisect
import json
import math
import random
import sys

TB_HZ = 40500000
BLOCKS_PER_S = 4096
HALF = 16                       # samples per half-period of sweep-0002's first A tone (128 Hz)
LEVEL = 10000                   # |decoded| above this is a plateau; between -LEVEL and LEVEL, a step
BLOCKS_PER_FRAME = 40
COINCIDENCE_BLOCKS = 1          # §V23.2: within one AUDIO block period
K_P = 0.001
K_TRIALS = 20000
K_SEED = 23
K_MIN_VIDEO = 10
MEAN_UNDRAINED_MAX = 31.8       # §V23.3: 1.25 x RUN 38's 25.41 -- A CHOSEN NUMBER, NOT DERIVED
FRAMECAP_WINDOW_MAX = 86        # §V23.8 (f): 1.25 x (82 - 13)
FRAMECAP_SESSION_MAX = 99       # §V23.3's fallback: (82 - 13) x 1.25 + 13
STEP_KINDS = ("produce", "flush_queue", "process")
TIE_ORDER = ("recorder", "isr") + STEP_KINDS


# ------------------------------------------------------------------------------ §V23.1 AUDIO

def half_periods(decoded):
    """(mark, next mark) of every half-period. A mark is the index of the half's STEP sample, its last.
    When the step sample was not drained, the plateau jumps straight to the opposite level, and the mark
    is the index of the plateau's LAST sample: the half that lost its step then measures 15, and the next
    measures 16. (A mark between the two samples would make both halves 15.5, and rounding would hide
    the loss entirely.)"""
    cls = ["H" if v > LEVEL else "L" if v < -LEVEL else "E" for v in decoded]
    marks = []
    for i in range(len(decoded) - 1):
        if cls[i] == "E":
            marks.append(i)
        elif cls[i] != cls[i + 1] and cls[i + 1] != "E":
            marks.append(i)
    return [(marks[j], marks[j + 1]) for j in range(len(marks) - 1)]


def audio_losses(decoded, ticks):
    """Every located loss: {"t", "g0", "g1", "k", "confidence"}; t is the completion that ends the half's
    largest gap. The confidence is that gap over the half's second largest, as §V23.7 reports for VIDEO:
    jitter can make a gap with nothing lost larger than the loss's own (a loss's gap lies in (T, 3T); RUN
    37's jitter reached 1.94T), and then the loss is timed at the wrong read of its half. Reported, it
    decides nothing."""
    if len(decoded) != len(ticks):
        raise ValueError("%d decoded samples but %d completion ticks" % (len(decoded), len(ticks)))
    out = []
    for a, b in half_periods(decoded):
        k = HALF - (b - a)
        if k <= 0:
            continue
        lo, hi = a, min(b, len(ticks) - 1)
        if hi <= lo:
            continue
        gaps = sorted(((ticks[i + 1] - ticks[i], i) for i in range(lo, hi)), reverse=True)
        best = gaps[0][1]
        conf = gaps[0][0] / float(gaps[1][0]) if len(gaps) > 1 and gaps[1][0] > 0 else None
        out.append({"t": ticks[best + 1], "g0": ticks[best], "g1": ticks[best + 1], "k": k, "confidence": conf})
    return out


# ------------------------------------------------------------------------------ §V23.7 VIDEO

def video_gaps(ticks, start):
    """(gaps, anomalies). A gap is {"t", "g0", "g1", "confidence"}; an anomaly is a frame with more
    blocks than its duration allows."""
    if len(ticks) != len(start):
        raise ValueError("%d VIDEO ticks but %d frame-start flags" % (len(ticks), len(start)))
    starts = [i for i, s in enumerate(start) if s]
    if len(starts) < 3:
        return [], []
    intervals = sorted(ticks[starts[j + 1]] - ticks[starts[j]] for j in range(len(starts) - 1))
    frame = intervals[len(intervals) // 2]
    gaps, anomalies = [], []
    for j in range(len(starts) - 1):
        a, b = starts[j], starts[j + 1]
        m = max(1, int(round((ticks[b] - ticks[a]) / float(frame))))
        k = BLOCKS_PER_FRAME * m - (b - a)
        inside = sorted(((ticks[i + 1] - ticks[i], i) for i in range(a, b - 1)), reverse=True)
        if k < 0:
            anomalies.append({"frame_start": ticks[a], "blocks": b - a, "frames": m})
            continue
        if k == 0 or not inside:
            continue
        conf = inside[0][0] / float(inside[1][0]) if len(inside) > 1 and inside[1][0] > 0 else None
        for g, i in inside[:k]:
            gaps.append({"t": ticks[i + 1], "g0": ticks[i], "g1": ticks[i + 1], "confidence": conf})
    return gaps, anomalies


# ------------------------------------------------------------------------------ §V23.2 QUESTION K

def _coincident(times, audio_t, within):
    n = 0
    for t in times:
        i = bisect.bisect_left(audio_t, t)
        d = min(abs(t - audio_t[j]) for j in (i - 1, i) if 0 <= j < len(audio_t)) if audio_t else None
        if d is not None and d <= within:
            n += 1
    return n


def question_K(losses, vgaps, callbacks, span, tb=TB_HZ, trials=K_TRIALS, seed=K_SEED, observer_ok=True):
    within = COINCIDENCE_BLOCKS * tb / float(BLOCKS_PER_S)
    audio_t = sorted(x["t"] for x in losses)
    vt = sorted(v["t"] for v in vgaps)
    dist = []
    for t in vt:
        i = bisect.bisect_left(audio_t, t)
        cands = [abs(t - audio_t[j]) for j in (i - 1, i) if 0 <= j < len(audio_t)]
        dist.append(min(cands) if cands else None)
    observed = sum(1 for d in dist if d is not None and d <= within)
    out = {"video_gaps": len(vt), "observed": observed, "within_ticks": within,
           "distances_ticks": sorted(d for d in dist if d is not None)}
    if len(vt) < K_MIN_VIDEO:
        out.update(verdict="INCONCLUSIVE", why="%d VIDEO gaps in the window, fewer than %d" % (len(vt), K_MIN_VIDEO),
                   p_phase=None, p_uniform=None)
        return out
    entries = sorted(c[0] for c in callbacks)
    lo, hi = span
    rng = random.Random(seed)
    placed = []
    for t in vt:
        c = bisect.bisect_right(entries, t) - 1
        placed.append((c, t - entries[c]) if c >= 0 else (None, None))
    hits_phase = hits_uniform = 0
    for _ in range(trials):
        moved = []
        for (c, phase), t in zip(placed, vt):
            new = t                                    # a gap with no callback before it stays where it is
            if c is not None:
                for _try in range(64):
                    c2 = rng.randrange(len(entries))
                    if c2 != c and lo <= entries[c2] + phase <= hi:
                        new = entries[c2] + phase
                        break
            moved.append(new)
        if _coincident(moved, audio_t, within) >= observed:
            hits_phase += 1
        if _coincident([rng.uniform(lo, hi) for _t in vt], audio_t, within) >= observed:
            hits_uniform += 1
    out["p_phase"] = hits_phase / float(trials)
    out["p_uniform"] = hits_uniform / float(trials)
    out["trials"] = trials
    if not observer_ok:
        out.update(verdict="INCONCLUSIVE", why="the observer gate's count bound failed (§V23.3)")
    elif out["p_phase"] < K_P:
        out.update(verdict="COINCIDENT", why="%d of %d VIDEO gaps within one AUDIO block of an AUDIO loss; "
                                             "phase-preserving null p = %.5f" % (observed, len(vt), out["p_phase"]))
    else:
        out.update(verdict="NOT COINCIDENT", why="%d of %d VIDEO gaps within one AUDIO block of an AUDIO loss; "
                                                 "phase-preserving null p = %.5f" % (observed, len(vt), out["p_phase"]))
    return out


# ------------------------------------------------------------------------------ §V23.3 QUESTION P

def _overlap(a0, a1, b0, b1):
    return max(0, min(a1, b1) - max(a0, b0))


def question_P(losses, steps, callbacks, tb=TB_HZ):
    cands = []
    for s in steps:
        start, end, kind, rec_end = s
        if kind not in STEP_KINDS:
            raise ValueError("unknown chain step kind %r" % kind)
        cands.append((start, end, kind))
        if rec_end > end:
            cands.append((end, rec_end, "recorder"))
    for entry, exit_ in callbacks:
        cands.append((entry, exit_, "isr"))
    cands.sort()
    starts = [c[0] for c in cands]
    longest = max((c[1] - c[0] for c in cands), default=0)
    counts = dict((k, 0) for k in TIE_ORDER + ("neither",))
    hist = {}
    per = tb / float(BLOCKS_PER_S)
    for x in losses:
        g0, g1 = x["g0"], x["g1"]
        best, best_ov = None, 0
        i = bisect.bisect_left(starts, g0 - longest)
        while i < len(cands) and cands[i][0] <= g1:
            c0, c1, kind = cands[i]
            ov = _overlap(g0, g1, c0, c1)
            if ov > best_ov or (ov == best_ov and ov > 0 and TIE_ORDER.index(kind) < TIE_ORDER.index(best)):
                best, best_ov = kind, ov
            i += 1
        counts[best or "neither"] += 1
        b = int((g1 - g0) / per * 4) / 4.0            # in quarter AUDIO block periods
        hist[b] = hist.get(b, 0) + 1
    total = len(losses)
    named = max(TIE_ORDER, key=lambda k: (counts[k], -TIE_ORDER.index(k))) if total else None
    if total == 0:
        decision = "no AUDIO loss was located"
    elif counts["neither"] * 2 > total:
        decision = "P names `neither` for most gaps: Run B is not designed from this run"
    elif counts["neither"] >= counts[named]:
        decision = "P names `neither` more than any step, but not for most gaps"
    elif named == "recorder":
        decision = ("P names the recorder: the instrument, not the chain. This instrumentation cannot answer "
                    "the question at this granularity; the next attempt needs a lighter instrument or a different "
                    "method, and Run B is not designed from this run")
    else:
        decision = "P names `%s`" % named
    return {"losses": total, "counts": counts, "names": named, "decision": decision,
            "gap_histogram_quarter_blocks": sorted(hist.items())}


def observer(report, vgaps_in_window, vgap_frames, tb=TB_HZ):
    """PRIMARY: the recorder's self-cost, reported. SANITY: the count bounds, decided."""
    w = report["window"]
    cov = w["coverage"]
    mean_und = (BLOCKS_PER_S * len(cov) - sum(cov)) / float(len(cov)) if cov else None
    rec = report.get("recorder", {})
    tap = rec.get("tap_ticks_per_cycle", [])
    step_writes = [s[3] - s[1] for s in report.get("steps", []) if s[3] > s[1]]
    cycles = len(report.get("callbacks", []))
    per_cycle = {}
    entries = sorted(c[0] for c in report.get("callbacks", []))
    for s in report.get("steps", []):
        if s[3] > s[1]:
            c = bisect.bisect_right(entries, s[1]) - 1
            per_cycle[c] = per_cycle.get(c, 0) + (s[3] - s[1])
    totals = [per_cycle.get(c, 0) + (tap[c] if c < len(tap) else 0) for c in range(cycles)] if cycles else []
    primary = {"cycles": cycles,
               "max_single_write_ticks": max(step_writes + [rec.get("tap_max_write", 0)]) if (step_writes or rec) else None,
               "max_total_per_cycle_ticks": max(totals) if totals else None,
               "mean_total_per_cycle_ticks": sum(totals) / float(len(totals)) if totals else None}
    if report.get("video", {}).get("ticks"):
        frames, bound, scope = vgap_frames, FRAMECAP_WINDOW_MAX, "incomplete frames in C's window (§V23.8 (f))"
    else:
        frames, bound, scope = w.get("framecap_session"), FRAMECAP_SESSION_MAX, \
            "whole-session FRAMECAP (the window's VIDEO records are absent)"
    ok_und = mean_und is not None and mean_und <= MEAN_UNDRAINED_MAX
    ok_fc = frames is not None and frames <= bound
    return {"primary": primary, "mean_undrained": mean_und, "mean_undrained_max": MEAN_UNDRAINED_MAX,
            "frames": frames, "frames_max": bound, "frames_scope": scope,
            "sanity_ok": bool(ok_und and ok_fc)}


# ------------------------------------------------------------------------------ the report

def evaluate(report, trials=K_TRIALS):
    tb = report.get("tb_hz", TB_HZ)
    if tb != TB_HZ:
        raise ValueError("timebase %d is not the 40.5 MHz every §V23 window is counted in" % tb)
    a, v = report["audio"], report.get("video", {"ticks": [], "start": []})
    losses = audio_losses(a["decoded"], a["ticks"])
    vg, anomalies = video_gaps(v["ticks"], v["start"])
    span = (a["ticks"][0], a["ticks"][-1]) if a["ticks"] else (0, 0)
    vg = [g for g in vg if span[0] <= g["t"] <= span[1]]
    obs = observer(report, vg, _frames_with_gaps(v["ticks"], v["start"], span), tb)
    k = question_K(losses, vg, report.get("callbacks", []), span, tb, trials, observer_ok=obs["sanity_ok"])
    p = question_P(losses, report.get("steps", []), report.get("callbacks", []), tb)
    w = report["window"]
    blocks_short = BLOCKS_PER_S * len(w["coverage"]) - sum(w["coverage"])
    confinement = _confinement(v["ticks"], v["start"], report.get("ai_span"))
    return {"test_id": report.get("test_id"), "build_id": report.get("build_id"),
            "losses_located": sum(x["k"] for x in losses), "loss_gaps": len(losses),
            "audio_confidence": [x["confidence"] for x in losses], "video_confidence": [g["confidence"] for g in vg],
            "blocks_short_by_coverage": blocks_short, "video_anomalies": anomalies,
            "K": k, "P": p, "observer": obs, "confinement": confinement,
            "transfers_to_run38": obs["sanity_ok"]}


def _confinement(ticks, start, ai_span):
    """§V23.8 (f): where the session's incomplete frames fall -- before the AI starts, inside its span,
    after it stops. The window's bound assumed them confined to the span."""
    if not ai_span or not ticks:
        return None
    gaps, _an = video_gaps(ticks, start)
    starts = [ticks[i] for i, s in enumerate(start) if s]
    where = {"before": set(), "inside": set(), "after": set()}
    for g in gaps:
        f = bisect.bisect_right(starts, g["g0"]) - 1
        key = "before" if g["t"] < ai_span[0] else "after" if g["t"] > ai_span[1] else "inside"
        where[key].add(f)
    return dict((k, len(v)) for k, v in where.items())


def _frames_with_gaps(ticks, start, span):
    """The number of FRAMES with at least one missing block, inside the span."""
    gaps, _an = video_gaps(ticks, start)
    starts = [ticks[i] for i, s in enumerate(start) if s]
    frames = set()
    for g in gaps:
        if span[0] <= g["t"] <= span[1]:
            frames.add(bisect.bisect_right(starts, g["g0"]) - 1)
    return len(frames)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        report = json.load(f)
    r = evaluate(report)
    per = TB_HZ / float(BLOCKS_PER_S)
    print("%s / %s" % (r["test_id"], r["build_id"]))
    o = r["observer"]
    pr = o["primary"]
    print("  OBSERVER  PRIMARY  the recorder's self-cost over %s cycles -- an UPPER BOUND, it includes the cost of "
          "measuring itself: largest single write %s ticks, largest total per cycle %s ticks, mean total per cycle "
          "%s ticks"
          % (pr["cycles"], pr["max_single_write_ticks"], pr["max_total_per_cycle_ticks"],
             None if pr["mean_total_per_cycle_ticks"] is None else "%.1f" % pr["mean_total_per_cycle_ticks"]))
    print("            SANITY   mean undrained %s /s (<= %.1f, A CHOSEN NUMBER); %s %s (<= %d) -> %s"
          % (None if o["mean_undrained"] is None else "%.2f" % o["mean_undrained"], o["mean_undrained_max"],
             o["frames_scope"], o["frames"], o["frames_max"], "HOLDS" if o["sanity_ok"] else "FAILS"))
    if not r["transfers_to_run38"]:
        print("            the count bound failed: QUESTION P's attribution does NOT transfer to RUN 38; the records "
              "stand only as observations about this image's own losses")
    print("  LOSSES    %d undrained blocks located in %d gaps; %d blocks short by the per-second coverage"
          % (r["losses_located"], r["loss_gaps"], r["blocks_short_by_coverage"]))
    ac, vc = r["audio_confidence"], r["video_confidence"]
    print("            close calls (largest gap < 1.2 x the second largest): AUDIO %d of %d, VIDEO %d of %d"
          % (sum(1 for c in ac if c is not None and c < 1.2), len(ac),
             sum(1 for c in vc if c is not None and c < 1.2), len(vc)))
    k = r["K"]
    print("  K   %-15s %s" % (k["verdict"], k["why"]))
    if k.get("p_uniform") is not None:
        print("      the UNIFORM null, for comparison only: p = %.5f" % k["p_uniform"])
    print("      distances to the nearest AUDIO loss, in AUDIO block periods: %s"
          % ", ".join("%.2f" % (d / per) for d in k["distances_ticks"]))
    p = r["P"]
    print("  P   no pass/fail -- %s" % p["decision"])
    print("      %s" % "  ".join("%s %d" % (c, p["counts"][c]) for c in TIE_ORDER + ("neither",)))
    print("      gap durations, in AUDIO block periods (quarters): %s"
          % "  ".join("%.2f:%d" % (b, n) for b, n in p["gap_histogram_quarter_blocks"]))
    c = r["confinement"]
    if c is not None:
        print("  (f) incomplete frames: %d before the AI starts, %d inside its span, %d after it stops%s"
              % (c["before"], c["inside"], c["after"],
                 "" if c["after"] == 0 else " -- NOT confined to the span the window's bound assumed"))
    if r["video_anomalies"]:
        print("  VIDEO anomalies (more blocks than the frame's duration allows): %d" % len(r["video_anomalies"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
