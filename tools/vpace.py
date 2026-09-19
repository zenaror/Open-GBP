"""
tools/vpace.py — the OFFLINE cadence/presentation model (HARDWARE_TESTS §V5.48).

It answers one question and refuses the neighbouring one:

  WHICH PRESENTATION POLICY PRESERVES EVERY INTERIOR SOURCE FRAME, IN ORDER,
  while converting ~59.727 Hz of source into ~59.940 Hz of display?

It is not a pacing implementation and it changes no runtime. It is separate from
tools/vindex.py (the frozen source authority) and from tools/vdisp.py (the
downstream trace reader) because it is a MODEL, and a model must never be able
to pass itself off as an observation.

---- THE DISTINCTION THIS WHOLE FILE RESTS ON ------------------------------

  SOURCE LOSS      an interior source frame never gets an eligible hand-off.
  DISPLAY REPEAT   a display interval shows the previous image again.
  RATE CONVERSION  N source frames mapped onto M display intervals, M > N.

They are not the same thing and a single counter must never stand for both.
`STREAMCONS repeats` in the current runtime does stand for both: every hold is
simultaneously one dropped source frame and one repeated display interval.

Because f_vi > f_src there are MORE display intervals than source frames, so
every source frame can have its own interval with some left over. A policy can
therefore be SOURCE-LOSSLESS and still contain display repeats — indeed it must
contain them. Over run 5's 34.27 s that is ~7.3 required repeats, against the 17
source frames the current policy actually dropped.

---- THE VI MODEL, VALIDATED BEFORE IT IS USED -----------------------------

Two parameters, both derived from the physical run and neither assumed:

  PERIOD   by FEASIBILITY over the sampled retrace counts -- a period is
           admissible only if every residual t - P*retrace fits one window of
           width P. A span ratio is biased by the phase difference between the
           first and last sample and is rejected.
  LATCH    a hand-over does not take effect at the very next boundary if it was
           issued too close to it. The margin is FITTED, and the fit is exact:
           with it, the model reproduces all 2114 recorded (current, pending)
           pairs and therefore every SELECTED/HOLD decision of run 5.

Without that margin three events disagree -- and they are exactly the three
holds where the sampled retrace had advanced, which is how the margin was found.
"""
import statistics
import sys

TB = 40500000.0


# ---------------------------------------------------------------- VI period --
def vi_period_feasible(samples, lo=674000.0, hi=678000.0, step=1.0):
    """`samples` is [(t, retrace), …]. Returns (lo, hi, best).

    A period P is admissible iff max(t - P*r) - min(t - P*r) < P: every sample
    must fit inside ONE interval of width P. Returns the admissible range so the
    uncertainty travels with the answer."""
    def spread(P):
        v = [t - P * r for t, r in samples]
        return max(v) - min(v)
    feas = []
    P = lo
    while P <= hi:
        if spread(P) < P:
            feas.append(P)
        P += step
    if not feas:
        return None
    best = min(feas, key=lambda p: spread(p) / p)
    return feas[0], feas[-1], best


def span_ratio_period(samples):
    """The WRONG estimator, kept so a test can show it is wrong: biased by the
    phase difference between the first and last sample."""
    a, b = samples[0], samples[-1]
    return (b[0] - a[0]) / (b[1] - a[1])


def vi_origin(samples, P):
    return min(t - P * r for t, r in samples)


def fit_latch_margin(events, P, origin, lo=0, hi=2400):
    """The margins for which the model reproduces EVERY recorded (current,
    pending). Returns (lo, hi) in time-base ticks, or None."""
    ok = [m for m in range(lo, hi) if replay_mismatches(events, P, origin, float(m)) == 0]
    return (ok[0], ok[-1]) if ok else None


def replay_mismatches(events, P, origin, margin):
    """Drives the XFB state machine over the RECORDED decisions and counts the
    events where the model's (current, pending) differs from the hardware's."""
    def bi(t):
        return int((t - origin) // P)
    cur = events[0]["xfb_current"]
    pend = events[0]["xfb_pending"]
    handed, bad = [], 0
    for e in events:
        k = bi(e["t"])
        while handed and handed[0][0] <= k:
            cur = handed.pop(0)[1]
        if pend >= 0 and pend == cur:
            pend = -1
        if cur != e["xfb_current"] or pend != e["xfb_pending"]:
            bad += 1
        if e["xfb_target"] >= 0:
            pend = e["xfb_target"]
            handed.append((bi(e["t"] + margin) + 1, e["xfb_target"]))
    return bad


# ------------------------------------------------------------------- policies --
class Display:
    """The observable framebuffer state machine, with `n` buffers.

    `current` is what the VI is scanning. `pending` is what has been handed over
    and has not become current yet. A hand-over latches at the first boundary
    after t + margin; that margin is the fitted physical one, not a guess."""

    def __init__(self, n, P, origin, margin, cur=0, pend=-1):
        self.n, self.P, self.origin, self.margin = n, P, origin, margin
        self.current, self.pending = cur, pend
        self.handed = []
        self.latches = []          # (boundary_index, buffer) actually latched

    def bi(self, t):
        return int((t - self.origin) // self.P)

    def advance(self, t):
        k = self.bi(t)
        while self.handed and self.handed[0][0] <= k:
            b, buf, tag = self.handed.pop(0)
            self.current = buf
            self.latches.append((b, buf, tag))
        if self.pending >= 0 and self.pending == self.current:
            self.pending = -1

    def target(self, t):
        """The module's own rule: any buffer that is neither current nor
        already handed over. -1 when there is none."""
        self.advance(t)
        for i in range(self.n):
            if i == self.current or i == self.pending:
                continue
            return i
        return -1

    def hand(self, t, buf, tag=None):
        """VIDEO_SetNextFramebuffer semantics: a SECOND hand-over before the
        boundary OVERWRITES the first. The frame that was overwritten never
        reaches the screen -- it is SUPERSEDED, which is a display loss even
        though the hand-off 'succeeded'. A policy that counts hand-offs instead
        of latches would report it as a success, so the superseded tag is
        returned rather than discarded."""
        b = self.bi(t + self.margin) + 1
        superseded = None
        if self.handed and self.handed[-1][0] == b:
            superseded = self.handed.pop()[2]
        self.pending = buf
        self.handed.append((b, buf, tag))
        return superseded


def simulate(frames, policy, n_xfb, P, origin, margin,
             retry_dt=6400.0, tex_buffers=2, horizon_pad=3):
    """`frames` is [(frame_index, t_ready)] in order, t_ready being the moment
    the frame reached the XFB decision.

    Returns a dict of the frozen metrics. `retry_dt` is the retry granularity a
    deferral policy would actually have: `pump()` runs about every 158 us in the
    physical run, so 6400 ticks is a deliberately PESSIMISTIC quarter of that.

    A deferred frame occupies a texture buffer. With `tex_buffers` textures, one
    filling and the rest holding, a deferral that lasts long enough for another
    frame to finish converting costs a texture -- and when none is free the
    SOURCE frame is the thing that gets lost. That is the mechanism this model
    exists to expose, so it is simulated rather than assumed away."""
    d = Display(n_xfb, P, origin, margin)
    pend_q = []                       # deferred frames, oldest first
    presented, dropped, deferred_max = [], [], 0
    superseded = []
    latency, ready_to_handoff = [], []
    handed_boundaries = set()

    def try_handoff(t):
        nonlocal pend_q
        while pend_q:
            fi, t_ready = pend_q[0]
            tgt = d.target(t)
            if tgt < 0:
                return
            sup = d.hand(t, tgt, fi)
            if sup is not None:
                superseded.append(sup)
            handed_boundaries.add(d.bi(t + margin) + 1)
            presented.append((fi, t))
            latency.append(t - t_ready)
            ready_to_handoff.append(t - t_ready)
            pend_q.pop(0)

    for idx, (fi, t_ready) in enumerate(frames):
        # retry opportunities between the previous frame and this one
        if pend_q:
            t = presented[-1][1] if presented else frames[0][1]
            t = max(t, pend_q[0][1])
            while t < t_ready:
                try_handoff(t)
                if not pend_q:
                    break
                t += retry_dt
        if policy == "baseline":
            tgt = d.target(t_ready)
            if tgt >= 0:
                sup = d.hand(t_ready, tgt, fi)
                if sup is not None:
                    superseded.append(sup)
                handed_boundaries.add(d.bi(t_ready + margin) + 1)
                presented.append((fi, t_ready))
                latency.append(0.0)
                ready_to_handoff.append(0.0)
            else:
                dropped.append(fi)
        else:
            # every deferral policy: queue in order, never overtake
            pend_q.append((fi, t_ready))
            deferred_max = max(deferred_max, len(pend_q))
            # TEXTURE BUDGET: one texture fills the next frame, the rest can
            # hold deferred ones. Beyond that the source frame is what is lost.
            if len(pend_q) > tex_buffers - 1:
                dropped.append(pend_q.pop(0)[0])
            try_handoff(t_ready)

    # drain after the last frame
    t = frames[-1][1]
    for _ in range(horizon_pad * int(P // retry_dt) + 4):
        if not pend_q:
            break
        t += retry_dt
        try_handoff(t)
    for fi, _ in pend_q:
        dropped.append(fi)

    # display intervals covered, and which repeated
    if presented:
        first_b = d.bi(presented[0][1])
        last_b = d.bi(presented[-1][1]) + 1
        total_intervals = last_b - first_b
        repeats = total_intervals - len(handed_boundaries)
    else:
        total_intervals = repeats = 0
    order_ok = [f for f, _ in presented] == sorted(f for f, _ in presented)
    return {
        "policy": policy, "n_xfb": n_xfb, "tex_buffers": tex_buffers,
        "frames": len(frames), "presented": len(presented),
        "source_dropped": len(dropped), "dropped_frames": dropped[:12],
        "superseded": len(superseded), "superseded_frames": superseded[:12],
        "never_displayed": len(dropped) + len(superseded),
        "display_intervals": total_intervals, "display_repeats": repeats,
        "max_deferred": deferred_max, "order_preserved": order_ok,
        "latency": _dist(latency), "ready_to_handoff": _dist(ready_to_handoff),
    }


def _dist(v):
    if not v:
        return None
    s = sorted(v)
    n = len(s)
    return {"n": n, "min": s[0], "p50": s[n // 2],
            "p95": s[min(n - 1, int(n * 0.95))],
            "p99": s[min(n - 1, int(n * 0.99))], "max": s[-1],
            "mean": statistics.mean(s)}


def fmt_dist(q, scale=1000.0 / TB):
    if not q:
        return "-"
    return ("n=%d  min %.3f  p50 %.3f  p95 %.3f  p99 %.3f  max %.3f ms"
            % (q["n"], q["min"] * scale, q["p50"] * scale, q["p95"] * scale,
               q["p99"] * scale, q["max"] * scale))


# ------------------------------------------------------------ physical replay --
def load_run(disp_path, idxcap_path=None):
    """The physical decision timeline. When an OGBPIDXCAP1 is supplied the
    scientific population is the EXACT frame_index join -- never the sidecar's
    legacy in_window flag, which is one frame early (GBP-VID-019)."""
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import vdisp
    d = vdisp.load(disp_path)
    KEY = vdisp.KEY_NONE
    ev = sorted([e for e in d["events"] if e["frame_index"] != KEY],
                key=lambda e: e["ordinal"])
    out = {"events": ev, "all_events": sorted(d["events"], key=lambda e: e["ordinal"]),
           "disp": d, "scientific": None}
    if idxcap_path:
        import vidxcap
        cap = vidxcap.load(idxcap_path)
        src = {r["frame_index"] for r in cap["records"]}
        out["scientific"] = src
        out["capture"] = cap
    return out


def source_rate(cap):
    r = cap["records"]
    return (len(r) - 1) * TB / (r[-1]["t_first_block"] - r[0]["t_first_block"])


# ---------------------------------------------------- parametric generation --
def observed_jitter(events, trim=0.0):
    """The measured OFFSET of each decision from a best-fit constant-rate line.

    This is the right quantity: the source runs at a fixed rate and what varies
    is where the consumer's decision lands relative to it. Taking successive
    interval differences instead would fold the rate into the noise.

    `trim` drops that fraction from each tail; the physical pool contains one
    48 ms decision gap, and a stress case built from a pool of independent
    draws would then place that outlier repeatedly, which is not what happened.
    The untrimmed pool is still returned for labelled stress runs."""
    # Fit against the FRAME INDEX, never the decision ordinal. Consecutive
    # decisions are not consecutive frames -- run 5 dropped 17 -- so an ordinal
    # fit bakes the missing frames into the slope and turns a 0.03 ms jitter
    # into a 33 ms "offset" that is really accumulated slope error.
    pts = [(float(e["frame_index"]), float(e["t"])) for e in events]
    x0, y0 = pts[0]
    xn, yn = pts[-1]
    slope = (yn - y0) / (xn - x0)
    off = [y - (y0 + (x - x0) * slope) for x, y in pts]
    if trim > 0:
        s = sorted(off)
        k = int(len(s) * trim)
        keep = set(s[k:len(s) - k]) if k else set(s)
        off = [x for x in off if x in keep]
    return slope, off


def make_frames(n, period, phase0, jitter=None, seed=1):
    """Source decision times: a nominal period, an initial phase, and an
    independent jitter OFFSET per frame.

    The offset is added to the nominal time, not accumulated into the interval.
    Accumulating it would be a random walk that drifts the source away from its
    own rate, and the physical source does not drift -- it is locked to the
    AGB's clock, and what varies is when the consumer's decision lands relative
    to it. Modelling it the other way answers a question the hardware never
    asked."""
    import random
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        off = rnd.choice(jitter) if jitter else 0.0
        out.append((i, float(phase0) + i * period + off))
    # Source frames cannot overtake one another: the assembler emits them in
    # index order. A jitter draw that would reorder them is unphysical, so the
    # time is clamped rather than the order being silently rewritten.
    for i in range(1, len(out)):
        if out[i][1] <= out[i - 1][1]:
            out[i] = (out[i][0], out[i - 1][1] + 1.0)
    return out


def sweep_phase(n_phases, frames_per_phase, src_period, P, margin,
                policy="defer", n_xfb=2, tex=2, jitter=None, retry_dt=6400.0):
    """Every initial source↔VI phase across one whole VI period. A policy that
    only works at the phase run 5 happened to start in is not a policy."""
    worst = {"drops": 0, "superseded": 0, "maxq": 0, "lat": 0.0, "phase": None}
    rows = []
    for k in range(n_phases):
        ph = k * P / n_phases
        fr = make_frames(frames_per_phase, src_period, ph, jitter, seed=k)
        r = simulate(fr, policy, n_xfb, P, 0.0, margin, retry_dt=retry_dt, tex_buffers=tex)
        lat = r["latency"]["max"] if r["latency"] else 0.0
        rows.append((ph, r["source_dropped"], r["superseded"], r["max_deferred"], lat,
                     r["display_repeats"], r["order_preserved"]))
        if (r["source_dropped"], r["superseded"], r["max_deferred"], lat) > \
           (worst["drops"], worst["superseded"], worst["maxq"], worst["lat"]):
            worst = {"drops": r["source_dropped"], "superseded": r["superseded"],
                     "maxq": r["max_deferred"], "lat": lat, "phase": ph}
    return {"rows": rows, "worst": worst,
            "total_drops": sum(r[1] for r in rows),
            "total_superseded": sum(r[2] for r in rows),
            "max_queue": max(r[3] for r in rows),
            "max_latency": max(r[4] for r in rows),
            "order_always": all(r[6] for r in rows)}
