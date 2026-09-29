#!/usr/bin/env python3
"""tools/v28loss.py -- GitHub Issue #137 (U-GBP-050): reads the diag_loss image's SD log and applies the rule the Orchestrator
registered BEFORE the build.

    tools/v28loss.py <log> [--json <out>]

THE RULE (Issue #137, the Orchestrator's decision comment; HARDWARE_TESTS.md section V28.16):
  * loss of a hold = 1 - blocks_in / nominal, nominal = 4096 blocks/s x the window's own seconds;
  * the PRIMARY window is the LATE one (from t_start + late_s to the end: the first seconds after an arm changes settle); the
    whole-hold figure is printed beside it;
  * a factor's effect is the mean level difference across the counted cells, in percentage points:
        L: mean loss with the label ON  minus mean loss with it OFF    (positive: the label costs blocks)
        S: mean loss at 128 pushes a call minus mean loss at 64         (positive: the long step costs blocks)
  * |effect| > 0.2 points: COUPLED to the loss; |effect| < 0.05: NOT coupled; otherwise UNRESOLVED (0.05 and 0.2 included);
  * the final AHEAD-1 hold: the underrun count against the calibrated host's 14-15 in 60 s. A count near it confirms the
    host's model; ZERO refutes it only if the underrun path is proven reachable (the hooks column, the structural test).
Every comparison is made in exact fractions (fractions.Fraction) from the log's integers, never on a rounded decimal.
ADDED AFTER AN ADVERSARIAL REVIEW, none of which can turn a registered class into a stronger one: (a) the standard error of each
effect, from the pooled scatter of the repeated cells (8 degrees of freedom), and whether the class is stable at +-2 SE; (b) a
trend-adjusted estimate (the loss regressed on both factors and the hold's position) and whether it classifies the same; (c) the
design's balance (a cut or an off-point hold unbalances it). The HELD verdict is the registered class when it is balanced, stable
and agreed by the adjusted estimate, and UNRESOLVED otherwise, with the reason. The registered class is always printed too. WHAT COUNTS:
a CELL hold that is not partial and has its late snapshot; the warm-up and the final hold are printed and never counted.

Beside the loss, the histograms: how often each stretch is long (per second, per factor level), and the share of the time the
tap, its decode, the production calls and the whole pump call take. If the tap dominates and neither arm moves the loss, the
tap's own occupancy shows it. Standard library only.
"""
import json
import re
import sys
from fractions import Fraction

NOMINAL_BLOCKS_PER_S = 4096
COUPLED_PP = Fraction(1, 5)          # 0.2 percentage points
NOT_COUPLED_PP = Fraction(1, 20)     # 0.05
HOST_UNDERRUNS_LO, HOST_UNDERRUNS_HI = 14, 15
POISSON_LO, POISSON_HI = 7, 22       # 14.5 +- 2 x sqrt(14.5) = 6.9 .. 22.1
HIST_NAMES = ("tap", "decode", "prod", "pump", "label", "gap")
KIND_NAMES = {0: "warm", 1: "cell", 2: "final"}


def kv(text):
    return dict(re.findall(r"(\S+)=(\S+)", text))


def parse(text):
    """{cfg, taps, holds: {n: dict}, notes: [str]} from the log's V28LOSSCFG / V28TAPS / V28_LOSS / V28_LOSSC / V28_LOSSH lines.
    A record that is truncated or malformed (the ring log drops lines when full) is skipped with a NOTE, never a crash."""
    out = {"cfg": None, "taps": None, "holds": {}, "notes": []}
    for line in text.splitlines():
        m = re.match(r"^\d{6} (V28LOSSCFG|V28TAPS|V28_LOSS|V28_LOSSC|V28_LOSSH|V28_LOSSO) (.*)$", line)
        if not m:
            continue
        tag, rest = m.group(1), kv(m.group(2))
        try:
            if tag == "V28LOSSCFG":
                out["cfg"] = {k: int(v) for k, v in rest.items()}
            elif tag == "V28TAPS":
                out["taps"] = {"taps": int(rest["taps"]), "failed": int(rest["taps_failed"]), "wrong": int(rest["wrong_len"]),
                               "blocks_in": int(rest["blocks_in"]), "gap_max": int(rest["gap_max"])}
            elif tag == "V28_LOSS":
                n = int(rest["n"])
                h = out["holds"].setdefault(n, {"n": n, "win": {}, "hist": {}})
                h.update({"kind": int(rest["kind"]), "cyc": int(rest["cyc"]), "L": int(rest["L"]), "S": int(rest["S"]),
                          "ahead": int(rest["ahead"]), "target": int(rest["target"]), "partial": int(rest["partial"]),
                          "late": int(rest["late"]), "hooks": int(rest["hooks"]), "t_start": int(rest["t_start"], 16),
                          "t_late": int(rest["t_late"], 16), "t_end": int(rest["t_end"], 16),
                          "ring": [int(x) for x in rest["ring"].split(",")]})
            elif tag == "V28_LOSSO":
                n = int(rest["n"])
                h = out["holds"].setdefault(n, {"n": n, "win": {}, "hist": {}})
                h["obs_t"] = [int(x) for x in rest["obs_t"].split(",")]
                h["obs_a"] = [int(x) for x in rest["obs_a"].split(",")]
            elif tag == "V28_LOSSC":
                n = int(rest["n"])
                h = out["holds"].setdefault(n, {"n": n, "win": {}, "hist": {}})
                h["win"][rest["win"]] = {k: int(v) for k, v in rest.items() if k not in ("n", "win")}
                for need in ("blocks_in", "taps", "failed", "wrong", "underruns"):
                    if need not in h["win"][rest["win"]]:
                        raise KeyError(need)
            elif tag == "V28_LOSSH":
                n = int(rest["n"])
                h = out["holds"].setdefault(n, {"n": n, "win": {}, "hist": {}})
                h["hist"][rest["h"]] = {"count": int(rest["count"]), "sum": int(rest["sum"]), "max": int(rest["max"]),
                                        "edges": [int(x) for x in rest["edges"].split(",")],
                                        "bins": [int(x) for x in rest["bins"].split(",")]}
        except (KeyError, ValueError) as e:
            out["notes"].append("a truncated or malformed %s record was skipped (%s: %s)" % (tag, type(e).__name__, e))
            if tag == "V28_LOSSC" and "n" in rest and rest["n"].isdigit() and int(rest["n"]) in out["holds"]:
                out["holds"][int(rest["n"])]["win"].pop(rest.get("win"), None)
    return out


def seconds(ticks, tb_hz):
    return Fraction(ticks, tb_hz)


def loss_of(blocks, secs):
    """1 - blocks / (4096 x secs), exactly; None for an empty window."""
    if secs <= 0:
        return None
    return 1 - Fraction(blocks) / (NOMINAL_BLOCKS_PER_S * secs)


def hold_facts(h, tb_hz, cfg):
    """The hold's own windows, losses (exact) and flags."""
    f = {"n": h["n"], "ring": h["ring"], "kind": KIND_NAMES.get(h["kind"], "?"), "cyc": h["cyc"], "L": h["L"], "S": h["S"],
         "ahead": h["ahead"], "partial": bool(h["partial"]), "has_late": bool(h["late"]), "hooks": h["hooks"], "flags": [],
         "off_point": False}
    full, late = h["win"].get("full"), h["win"].get("late")
    if h["late"] and not late:
        f["flags"].append("the late window's record is missing: not counted")
        f["has_late"] = False
    f["secs_full"] = seconds(h["t_end"] - h["t_start"], tb_hz)
    f["loss_full"] = loss_of(full["blocks_in"], f["secs_full"]) if full else None
    if f["has_late"] and late:
        f["secs_late"] = seconds(h["t_end"] - h["t_late"], tb_hz)
        f["loss_late"] = loss_of(late["blocks_in"], f["secs_late"])
    else:
        f["secs_late"], f["loss_late"] = None, None
    for w, name in ((full, "full"), (late, "late")):
        if not w:
            continue
        if w["taps"] != w["blocks_in"]:
            f["flags"].append("%s: taps %d != blocks_in %d" % (name, w["taps"], w["blocks_in"]))
        if w["failed"] or w["wrong"]:
            f["flags"].append("%s: %d failed, %d wrong-length taps" % (name, w["failed"], w["wrong"]))
    # the OBSERVED operating point (gbp_aplay2's own target and ahead at the snapshots), against the intended one
    want_t, want_a = cfg["target"], h["ahead"]
    if "obs_t" not in h:
        f["off_point"] = True
        f["flags"].append("the observed operating point (V28_LOSSO) is missing: not counted")
    elif any(x != want_t for x in h["obs_t"]) or any(x != want_a for x in h["obs_a"]):
        f["off_point"] = True
        f["flags"].append("OFF POINT: observed target %s, ahead %s; intended %d, %d: not counted" % (
            h["obs_t"], h["obs_a"], want_t, want_a))
    f["window_full"], f["window_late"] = full, late
    f["hist"] = h["hist"]
    f["underruns"] = full["underruns"] if full else None
    f["underruns_late"] = late["underruns"] if late else None
    return f


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def classify(effect):
    """COUPLED / NOT COUPLED / UNRESOLVED from an exact effect in percentage points (strict: 0.2 and 0.05 themselves are UNRESOLVED)."""
    if effect is None:
        return "NOT EVALUABLE"
    a = abs(effect)
    if a > COUPLED_PP:
        return "COUPLED"
    if a < NOT_COUPLED_PP:
        return "NOT COUPLED"
    return "UNRESOLVED"


def gray_ok(cells):
    """Every consecutive pair of the cell holds (in the order the log gives them) differs in exactly one factor."""
    return all((a["L"] != b["L"]) + (a["S"] != b["S"]) == 1 for a, b in zip(cells, cells[1:]))


def isqrt_frac(x):
    """A float square root of a Fraction, for the standard error only (a printed figure and a +-2 SE band, never a threshold)."""
    return float(x) ** 0.5


def pooled_sd_pp(cells):
    """(sd in points, degrees of freedom) of the loss within a cell, pooled over the (L,S) cells' repeats; (None, 0) without repeats."""
    by = {}
    for h in cells:
        by.setdefault((h["L"], h["S"]), []).append(h["loss_late"] * 100)
    ss, df = Fraction(0), 0
    for xs in by.values():
        if len(xs) > 1:
            m = mean(xs)
            ss += sum((x - m) ** 2 for x in xs)
            df += len(xs) - 1
    if df < 1:
        return None, 0
    return isqrt_frac(ss / df), df


def solve(a, b):
    """Exact Gauss-Jordan over Fractions for a small square system; None when singular."""
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = next((r for r in range(c, n) if m[r][c] != 0), None)
        if p is None:
            return None
        m[c], m[p] = m[p], m[c]
        piv = m[c][c]
        m[c] = [x / piv for x in m[c]]
        for r in range(n):
            if r != c and m[r][c] != 0:
                f = m[r][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] for i in range(n)]


def adjusted_effects(cells):
    """The loss (points) regressed on an intercept, L (+-1/2), S (+-1/2) and the hold's position (centred): the effects with a linear
    drift taken out. Returns {"L": pp, "S": pp, "trend": pp per hold} (exact), or None when the design cannot support it."""
    if len(cells) < 5:
        return None
    ts = [Fraction(h["n"]) for h in cells]
    tm = sum(ts) / len(ts)
    rows = [[Fraction(1), Fraction(h["L"]) - Fraction(1, 2), Fraction(h["S"]) - Fraction(1, 2), t - tm] for h, t in zip(cells, ts)]
    y = [h["loss_late"] * 100 for h in cells]
    xtx = [[sum(r[i] * r[j] for r in rows) for j in range(4)] for i in range(4)]
    xty = [sum(r[i] * yy for r, yy in zip(rows, y)) for i in range(4)]
    beta = solve(xtx, xty)
    if beta is None:
        return None
    ss = sum((yy - sum(bj * rj for bj, rj in zip(beta, r))) ** 2 for r, yy in zip(rows, y))
    df = len(cells) - 4
    return {"L": beta[1], "S": beta[2], "trend": beta[3], "sd_pp": isqrt_frac(ss / df) if df >= 1 else None, "df": df}


def stable(effect, se):
    """The class does not change anywhere in effect +- 2 SE (on the magnitude); False without an SE."""
    if effect is None or se is None:
        return False
    a = abs(effect)
    lo, hi = max(Fraction(0), a - Fraction(2 * se).limit_denominator(10 ** 9)), a + Fraction(2 * se).limit_denominator(10 ** 9)
    return classify(lo) == classify(a) == classify(hi)


def occupancy(holds, name, tb_hz):
    """(sum of ticks, seconds) of one histogram over the holds -> the share of wall time."""
    ticks = sum(h["hist"][name]["sum"] for h in holds if name in h["hist"])
    secs = sum(h["secs_full"] for h in holds)
    return Fraction(ticks, 1), secs


def pooled(holds, name):
    bins = [0] * 5
    count = total = mx = 0
    edges = None
    for h in holds:
        x = h["hist"].get(name)
        if not x:
            continue
        edges = x["edges"]
        count += x["count"]
        total += x["sum"]
        mx = max(mx, x["max"])
        bins = [a + b for a, b in zip(bins, x["bins"])]
    return {"count": count, "sum": total, "max": mx, "bins": bins, "edges": edges}


def analyse(text):
    p = parse(text)
    if not p["cfg"]:
        raise ValueError("no V28LOSSCFG record: this is not a diag_loss log")
    cfg = p["cfg"]
    tb = cfg["tb_hz"]
    notes = list(p["notes"])
    holds = []
    for n in sorted(p["holds"]):
        if "kind" not in p["holds"][n]:
            notes.append("hold %d has counter or histogram records but no V28_LOSS record: skipped" % n)
            continue
        holds.append(hold_facts(p["holds"][n], tb, cfg))
    if len(holds) != cfg["holds"]:
        notes.append("V28LOSSCFG says %d holds, %d usable V28_LOSS records found" % (cfg["holds"], len(holds)))
    cell_holds = [h for h in holds if h["kind"] == "cell"]
    cells = [h for h in cell_holds if not h["partial"] and h["has_late"] and not h["off_point"] and h["loss_late"] is not None]
    dropped = [h for h in cell_holds if h not in cells]
    if dropped:
        notes.append("%d cell hold(s) not counted (partial, no late window, or off the intended point): %s" % (
            len(dropped), [h["n"] for h in dropped]))
    if not gray_ok(cell_holds):
        notes.append("the cell holds do NOT follow a one-flip walk: consecutive holds differ in more than one factor")
    if cfg.get("refused_done"):
        notes.append("hold_done() was refused %d time(s): the handler was acknowledged with nothing pending" % cfg["refused_done"])
    counts = {}
    for h in cells:
        counts[(h["L"], h["S"])] = counts.get((h["L"], h["S"]), 0) + 1
    balanced = len(counts) == 4 and len(set(counts.values())) == 1
    if not balanced:
        notes.append("the counted design is UNBALANCED (holds per cell %s): the marginal effects are confounded; verdicts are held" %
                     dict((str(k), v) for k, v in sorted(counts.items())))
    res = {"cfg": cfg, "taps": p["taps"], "holds": holds, "notes": notes, "counted": len(cells), "effects": {},
           "balanced": balanced, "counts": counts}
    sd_rep, df_rep = pooled_sd_pp(cells)
    adj = adjusted_effects(cells)
    res["adjusted"] = adj
    # the scatter the standard error is built from: what is LEFT after the trend fit when there is one (drift is not noise), else the
    # repeats of the same cell
    if adj and adj["sd_pp"] is not None:
        sd, df = adj["sd_pp"], adj["df"]
    else:
        sd, df = sd_rep, df_rep
    res["sd_pp"], res["sd_df"], res["sd_repeat_pp"] = sd, df, sd_rep

    for key, name, a_lv, b_lv in (("L", "label", "on", "off"), ("S", "step", "128", "64")):
        a = [h["loss_late"] for h in cells if h[key] == 1]
        b = [h["loss_late"] for h in cells if h[key] == 0]
        eff = (mean(a) - mean(b)) * 100 if a and b else None
        se = sd * (1.0 / len(a) + 1.0 / len(b)) ** 0.5 if (a and b and sd is not None) else None
        cls = classify(eff)
        adj_e = adj[key] if adj else None
        adj_cls = classify(adj_e)
        stab = stable(eff, se)
        if eff is None:
            held, why = "NOT EVALUABLE", "no cells at one of the levels"
        elif not balanced:
            held, why = "UNRESOLVED", "unbalanced design"
        elif se is None:
            held, why = "UNRESOLVED", "no repeated cell to estimate the scatter from"
        elif not stab:
            held, why = "UNRESOLVED", "class %s not stable at +-2 SE" % cls
        elif adj_cls != cls:
            held, why = "UNRESOLVED", "the trend-adjusted estimate classifies as %s" % adj_cls
        else:
            held, why = cls, "balanced, stable at +-2 SE, agreed by the trend-adjusted estimate"
        res["effects"][name] = {"a_level": a_lv, "b_level": b_lv, "n_a": len(a), "n_b": len(b), "mean_a": mean(a), "mean_b": mean(b),
                                "effect_pp": eff, "verdict": cls, "se_pp": se, "stable": stab, "adjusted_pp": adj_e,
                                "adjusted_verdict": adj_cls, "held": held, "held_why": why}
    res["mean_loss"] = mean([h["loss_late"] for h in cells])
    by_cell = {}
    for h in cells:
        by_cell.setdefault((h["L"], h["S"]), []).append(h["loss_late"])
    res["by_cell"] = by_cell
    levels = {}
    for key in ("L", "S"):
        for on in (1, 0):
            hs = [h for h in cells if h[key] == on]
            secs = sum(h["secs_full"] for h in hs)
            levels[(key, on)] = {"secs": secs, "hist": dict((n, pooled(hs, n)) for n in HIST_NAMES)}
    res["levels"] = levels
    res["overall"] = dict((n, pooled(cells, n)) for n in HIST_NAMES)
    res["overall_secs"] = sum(h["secs_full"] for h in cells)
    fin = [h for h in holds if h["kind"] == "final"]
    res["final"] = None
    if fin:
        h = fin[-1]
        res["final"] = {"n": h["n"], "partial": h["partial"], "secs": h["secs_full"], "underruns": h["underruns"],
                        "underruns_late": h["underruns_late"], "hooks": h["hooks"], "loss_full": h["loss_full"],
                        "loss_late": h["loss_late"], "ahead": h["ahead"], "off_point": h["off_point"]}
    return res


def f3(x, places=3):
    return "n/a" if x is None else "%.*f" % (places, float(x))


def render(res):
    tb = res["cfg"]["tb_hz"]
    out = []
    w = out.append
    w("diag_loss log: %d hold(s), %d counted cell hold(s); target %d, cells %d x %d cycles, hold %d s (late window from %d s)"
      % (len(res["holds"]), res["counted"], res["cfg"]["target"], res["cfg"]["cells"], res["cfg"]["cycles"],
         res["cfg"]["hold_s"], res["cfg"]["late_s"]))
    if res["taps"]:
        t = res["taps"]
        w("session taps: %d taps, %d failed, %d wrong-length, blocks_in %d (taps - blocks_in = %d), longest gap %d ticks"
          % (t["taps"], t["failed"], t["wrong"], t["blocks_in"], t["taps"] - t["blocks_in"], t["gap_max"]))
    for n in res["notes"]:
        w("NOTE: " + n)
    w("")
    w("per hold (loss = 1 - blocks_in / (4096 x seconds); LATE is the primary window):")
    w("  n  kind   cyc L S ahead  secs   loss_late%  loss_full%  underruns hooks  ring s/l/e")
    for h in res["holds"]:
        w("%3d  %-5s  %d   %d %d %d   %6s  %10s  %10s  %9s %5d  %s" % (
            h["n"], h["kind"], h["cyc"], h["L"], h["S"], h["ahead"], f3(h["secs_full"], 2),
            f3(None if h["loss_late"] is None else h["loss_late"] * 100), f3(None if h["loss_full"] is None else h["loss_full"] * 100),
            h["underruns"], h["hooks"], "/".join(str(x) for x in h["ring"])) + ("  PARTIAL" if h["partial"] else "") + ("".join("  [" + x + "]" for x in h["flags"])))
    w("")
    w("FACTOR EFFECTS (percentage points of loss, from the LATE windows; > 0.2 coupled, < 0.05 not coupled, between: unresolved):")
    for name, e in res["effects"].items():
        w("  %-5s %s (n=%d, mean %s%%) minus %s (n=%d, mean %s%%) = %s pp   REGISTERED CLASS: %s" % (
            name, e["a_level"], e["n_a"], f3(None if e["mean_a"] is None else e["mean_a"] * 100), e["b_level"], e["n_b"],
            f3(None if e["mean_b"] is None else e["mean_b"] * 100), f3(e["effect_pp"]), e["verdict"]))
        w("        SE %s pp (scatter %s pp after the trend fit, %d df; %s pp within repeated cells); stable at +-2 SE: %s; "
          "trend-adjusted %s pp -> %s" % (
              f3(e["se_pp"]), f3(res["sd_pp"]), res["sd_df"], f3(res["sd_repeat_pp"]), "yes" if e["stable"] else "NO",
              f3(e["adjusted_pp"]), e["adjusted_verdict"]))
        w("        HELD VERDICT: %s (%s)" % (e["held"], e["held_why"]))
    if res["adjusted"]:
        w("  drift (trend term): %s pp per hold" % f3(res["adjusted"]["trend"], 4))
    w("  mean loss over the counted cells: %s%%" % f3(None if res["mean_loss"] is None else res["mean_loss"] * 100))
    w("  by cell, in visit order (late loss %, repeats of one cell spread = drift or noise):")
    for (l, s_), xs in sorted(res["by_cell"].items(), reverse=True):
        w("    L=%d S=%d: %s   (range %s pp)" % (l, s_, "  ".join(f3(x * 100) for x in xs), f3((max(xs) - min(xs)) * 100)))
    w("")
    w("WHERE THE TIME GOES (share of wall time, over the counted cells; ticks at %d Hz):" % tb)
    for name in HIST_NAMES:
        o = res["overall"][name]
        if o["count"] == 0 or not res["overall_secs"]:
            continue
        share = Fraction(o["sum"], tb) / res["overall_secs"] * 100
        w("  %-6s %9d calls  mean %8.1f ticks  max %8d  %6.2f %% of wall time  bins %s (edges %s)" % (
            name, o["count"], o["sum"] / o["count"], o["max"], float(share), o["bins"], o["edges"]))
    w("HOW OFTEN EACH STRETCH IS LONG (bin counts per second of the WHOLE hold, by factor level; the top bin is the longest):")
    for name in ("pump", "prod", "tap", "gap"):
        for (key, on), lv in sorted(res["levels"].items()):
            x = lv["hist"][name]
            if not x["count"] or not lv["secs"]:
                continue
            w("  %-5s %s=%d: %s per s" % (name, key, on, ", ".join("%.2f" % float(Fraction(b) / lv["secs"]) for b in x["bins"])))
    w("")
    fin = res["final"]
    if fin:
        u = fin["underruns"]
        if u is None:
            verdict = "NOT EVALUABLE (no counters)"
        elif fin["partial"]:
            verdict = "PARTIAL hold: not evaluable against the 60 s prediction"
        elif fin["off_point"]:
            verdict = "OFF THE INTENDED POINT: not evaluable"
        elif HOST_UNDERRUNS_LO <= u <= HOST_UNDERRUNS_HI:
            verdict = "matches the calibrated host's %d-%d" % (HOST_UNDERRUNS_LO, HOST_UNDERRUNS_HI)
        elif u == 0:
            verdict = ("ZERO: refutes the host's model only if the underrun path is reachable "
                       "(hooks seen = %d, structural test)" % fin["hooks"])
        elif POISSON_LO <= u <= POISSON_HI:
            verdict = ("consistent with the host's %d-%d within Poisson noise (%d-%d, +-2 SD of a count near 14.5), not the point figure"
                       % (HOST_UNDERRUNS_LO, HOST_UNDERRUNS_HI, POISSON_LO, POISSON_HI))
        else:
            verdict = "differs from the host's %d-%d (outside %d-%d)" % (HOST_UNDERRUNS_LO, HOST_UNDERRUNS_HI, POISSON_LO, POISSON_HI)
        w("FINAL AHEAD-%d hold (%s s): %s underruns whole hold, %s in the late window (the underrun path fired %d times); "
          "loss %s%% late, %s%% whole -> %s" % (
              fin["ahead"], f3(fin["secs"], 1), u, fin["underruns_late"], fin["hooks"],
              f3(None if fin["loss_late"] is None else fin["loss_late"] * 100),
              f3(None if fin["loss_full"] is None else fin["loss_full"] * 100), verdict))
        w("  the host's 14-15 was computed at a 1.6 % deficit: compare it with THIS hold's own measured loss above before reading a mismatch")
    else:
        w("FINAL hold: none recorded")
    return "\n".join(out)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8", errors="replace") as fh:
        res = analyse(fh.read())
    print(render(res))
    if "--json" in argv:
        def enc(o):
            if isinstance(o, Fraction):
                return float(o)
            if isinstance(o, dict):
                return dict((str(k), enc(v)) for k, v in o.items())
            if isinstance(o, (list, tuple)):
                return [enc(v) for v in o]
            return o
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as fh:
            json.dump(enc(res), fh, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
