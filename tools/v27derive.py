#!/usr/bin/env python3
"""
tools/v27derive.py — GitHub Issue #120: RUN 43's DESCRIPTIVE figures beyond the frozen gate (`sync-0001`,
GBP-AUDIO-012, HARDWARE_TESTS.md §V27). The verdicts are tools/v27accept.py's, frozen at 4e4bce9, and nothing here
re-judges them; this reads the same log through the same builder (tools/v27report.py, frozen at 7c3bffd) and adds
what the Issue asked for and the gate does not print.

    tools/v27derive.py <log> [--json <out>]

1. THE TIMELINE, in seconds from the capture's start (CLOCKS capture_start) and from the ORIGIN (LIVET t_origin):
   the A press, the origin, the raw window (SYNCAWR t_first..t_last), each phase's start and end (SYNCPH) and the
   stop (SYNCEND t, `stop=`).

2. PHASE 2's PATH, every C-stick edge of Phase 2 (the in-run SYNCCS records: direction, acted, busy) in time order
   beside the transitions it caused (SYNCP2: START / STEP, from, to) and the confirmations (SYNCSET), cut into
   settings at each START; per setting the seeded LEFT direction (SYNCP2CFG), the steps taken each way, the edges
   REFUSED and where the level stood when they were (at the scale's floor p2_lo, at its top p2_hi, elsewhere), and
   the confirmed target -- or, for the setting the stop cut, the level it stood at.

3. THE C-STICK EDGES RECONCILED: SYNCEND's cs and acted against the in-run records, by phase, and the refusals
   against SYNCREF's counters.

4. M4 BY DWELL. Phase 1's seconds (the builder's per-second arrays) grouped into DWELLS: maximal runs of consecutive
   Phase 1 seconds at one arm's target. Per arm: lost AUDIO blocks (4 096 - count) over the non-mute seconds (the
   gate's M4) and over the settled seconds (M1's), the underruns and the overflow; the SHALLOW / DEEP ratio of the
   loss rates with a 90 % interval from resampling whole dwells within each arm (BOOT draws, seed BOOT_SEED -- a
   dwell, not a second, is the unit, because the arms alternate by dwell and seconds inside one are not independent);
   and, for an arm with no underrun in N non-mute seconds, the rule-of-three bound 3/N per second (95 %, Poisson).
   WITH SIX DWELLS AN ARM THE PERCENTILE INTERVAL IS ANTI-CONSERVATIVE (Issue #120's review: under equal rates with
   RUN 43's dwell exposures it excluded 1 in about 15 % of simulations, nominal 10 %). So the EXACT PERMUTATION of the
   arm labels over the dwells is printed beside it: every way of choosing which dwells are SHALLOW (C(12, 6) = 924
   for RUN 43), the one-sided p (a ratio at or below the observed) and the two-sided p (|log ratio| at or above).
   No instrument runs in Phase 1 (the raw window closes in Phase 0), so GBP-HW-338's three ways coincide: the whole
   phase, outside the instrument, and nothing inside.

5. PHASE 2's SECONDS BY TARGET: non-mute and settled seconds, lost blocks and underruns at each target Phase 2
   visited, and the mean settled fill against it. Phase 2 is not an arm: its seconds are where the Operator's
   adjustment took the level, not a design.

Standard library only; reads the log it is given, writes the JSON it is asked to.
"""
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import v27report  # noqa: E402

BLOCKS_PER_S = 4096
BOOT, BOOT_SEED = 20000, 120
REC = re.compile(r"^\d{6} (\S+) (.*)$")


def kv(rest):
    return dict(tok.split("=", 1) for tok in rest.split() if "=" in tok)


def records(text, tags):
    out = []
    for line in text.splitlines():
        m = REC.match(line)
        if m and m.group(1) in tags:
            out.append((m.group(1), kv(m.group(2))))
    return out


def one(text, tag):
    r = [d for t, d in records(text, (tag,))]
    if len(r) != 1:
        raise ValueError("%d %s records, not 1" % (len(r), tag))
    return r[0]


def timeline(text, rep):
    tb = rep["tb_hz"]
    t0 = int(one(text, "CLOCKS")["capture_start"], 16)
    livet = one(text, "LIVET")
    org = int(livet["t_origin"], 16)
    awr = one(text, "SYNCAWR")
    end = one(text, "SYNCEND")
    marks = [("capture_start", t0), ("press", int(livet["t_press"], 16)), ("origin", org),
             ("awr_first", int(awr["t_first"], 16)), ("awr_last", int(awr["t_last"], 16))]
    for d in [d for t, d in records(text, ("SYNCPH",))]:
        marks.append(("phase%s_start" % d["phase"], int(d["t_start"], 16)))
        if d["t_end"] not in ("0", ""):
            marks.append(("phase%s_end" % d["phase"], int(d["t_end"], 16)))
    marks.append(("stop", int(end["t"], 16)))
    return {"tb_hz": tb, "stop": end["stop"], "reason": end["reason"], "secs": int(end["secs"]),
            "marks": [{"what": w, "from_capture_s": (t - t0) / float(tb), "from_origin_s": (t - org) / float(tb)}
                      for w, t in sorted(marks, key=lambda x: x[1])]}


def phase2_path(text, rep):
    tb = rep["tb_hz"]
    cfg = one(text, "SYNCCFG")
    lo, hi = int(cfg["p2_lo"]), int(cfg["p2_hi"])
    p2cfg = one(text, "SYNCP2CFG")
    dirs = p2cfg["dirs"].split(",")
    p2s = [d for t, d in records(text, ("SYNCPH",)) if d["phase"] == "2"]
    t_p2 = int(p2s[0]["t_start"], 16)
    ev = []
    for tag, d in records(text, ("SYNCCS", "SYNCP2", "SYNCSET")):
        t = int(d["t"], 16)
        if tag == "SYNCCS" and d.get("phase") != "2":
            continue
        if tag == "SYNCP2" and t < t_p2:
            continue
        # at one instant: the edge, then the confirmation that closes the current setting, then the START of the
        # next (the runtime writes all three on the UP that confirms)
        ev.append((t, {"SYNCCS": 0, "SYNCSET": 1, "SYNCP2": 2}[tag], tag, d))
    ev.sort(key=lambda x: (x[0], x[1]))
    settings, cur, level = [], None, None
    rows = []
    for t, _, tag, d in ev:
        rel = (t - t_p2) / float(tb)
        if tag == "SYNCP2" and d["kind"] == "START":
            if cur is not None:
                settings.append(cur)
            cur = {"index": len(settings), "start": int(d["to"]), "left": "shallower" if dirs[len(settings)] == "S"
                   else "deeper", "t_start_s": rel, "steps": {"L": 0, "R": 0}, "refused": {}, "path": [int(d["to"])],
                   "confirmed": None}
            level = int(d["to"])
        elif tag == "SYNCP2" and cur is not None:
            level = int(d["to"])
            cur["path"].append(level)
        elif tag == "SYNCCS" and cur is not None:
            if d["dir"] in ("L", "R"):
                if d["acted"] == "1":
                    cur["steps"][d["dir"]] += 1
                else:
                    where = "floor" if level == lo else ("top" if level == hi else "inside")
                    key = "%s_at_%s" % (d["dir"], where)
                    cur["refused"][key] = cur["refused"].get(key, 0) + 1
        elif tag == "SYNCSET" and cur is not None:
            cur["confirmed"] = int(d["target"])
        rows.append({"t_s": rel, "tag": tag, "fields": dict((k, v) for k, v in d.items() if k != "t")})
    if cur is not None:
        cur["level_at_stop"] = level
        settings.append(cur)
    return {"p2_lo": lo, "p2_hi": hi, "p2_step": int(cfg["p2_step"]), "settings": settings, "rows": rows}


def cstick(text):
    cs = [d for t, d in records(text, ("SYNCCS",))]
    end = one(text, "SYNCEND")
    ref = one(text, "SYNCREF")
    by = {}
    for d in cs:
        k = "phase%s" % d["phase"]
        b = by.setdefault(k, {"edges": 0, "acted": 0, "refused": 0, "busy": 0})
        b["edges"] += 1
        b["acted"] += d["acted"] == "1"
        b["refused"] += d["acted"] != "1"
        b["busy"] += d.get("busy") == "1"
    return {"syncend_cs": int(end["cs"]), "syncend_acted": int(end["acted"]), "records": len(cs),
            "acted": sum(1 for d in cs if d["acted"] == "1"), "by_phase": by,
            "syncref": dict((k, int(v)) for k, v in ref.items())}


def dwells(seconds, phase=1):
    out = []
    for s in seconds:
        if s.get("phase") != phase:
            continue
        if out and out[-1]["target"] == s["target"] and out[-1]["last"] == s["s"] - 1:
            d = out[-1]
        else:
            d = {"target": s["target"], "secs": [], "last": None}
            out.append(d)
        d["secs"].append(s)
        d["last"] = s["s"]
    for d in out:
        live = [x for x in d["secs"] if not x["mute"]]
        sett = [x for x in live if not x["settling"]]
        d.update(first=d["secs"][0]["s"], seconds=len(d["secs"]), live=len(live), settled=len(sett),
                 lost=sum(BLOCKS_PER_S - x["count"] for x in live),
                 lost_settled=sum(BLOCKS_PER_S - x["count"] for x in sett),
                 underruns=sum(x["underruns"] for x in live), overflow=sum(x["overflow"] for x in live))
        del d["secs"]
        del d["last"]
    return out


def rate(ds, key, n):
    den = sum(d[n] for d in ds)
    return sum(d[key] for d in ds) / float(den) if den else None


def interval(deep, shallow, key, n, draws=BOOT, seed=BOOT_SEED):
    rng = random.Random(seed)
    ratios = []
    for _ in range(draws):
        bd = [rng.choice(deep) for _ in deep]
        bs = [rng.choice(shallow) for _ in shallow]
        a, b = rate(bd, key, n), rate(bs, key, n)
        if a and b is not None:
            ratios.append(b / a)
    ratios.sort()
    return [ratios[int(0.05 * len(ratios))], ratios[int(0.95 * len(ratios)) - 1]], len(ratios)


def m4(rep):
    ds = dwells(rep["seconds"])
    cfg = rep["cfg"]
    arms = {"DEEP": [d for d in ds if d["target"] == cfg["deep"]],
            "SHALLOW": [d for d in ds if d["target"] == cfg["shallow"]]}
    per = {}
    for name, a in arms.items():
        live = sum(d["live"] for d in a)
        per[name] = {"dwells": len(a), "live_s": live, "settled_s": sum(d["settled"] for d in a),
                     "lost": sum(d["lost"] for d in a), "lost_settled": sum(d["lost_settled"] for d in a),
                     "per_s": rate(a, "lost", "live"), "per_s_settled": rate(a, "lost_settled", "settled"),
                     "underruns": sum(d["underruns"] for d in a), "overflow": sum(d["overflow"] for d in a),
                     "underrun_rate_95_upper_per_s": (3.0 / live) if live and not sum(d["underruns"] for d in a)
                     else None}
    ratio = {}
    for key, n, tag in (("lost", "live", "live"), ("lost_settled", "settled", "settled")):
        r = rate(arms["SHALLOW"], key, n) / rate(arms["DEEP"], key, n)
        ci, draws = interval(arms["DEEP"], arms["SHALLOW"], key, n)
        ratio[tag] = {"shallow_over_deep": r, "ci90": ci, "draws": draws}
    return {"dwells": ds, "arms": per, "ratio": ratio, "boot": {"draws": BOOT, "seed": BOOT_SEED},
            "permutation": permutation(arms["DEEP"], arms["SHALLOW"])}


def permutation(deep, shallow, key="lost", n="live"):
    """The exact permutation test of the arm labels over the dwells: (one-sided p, two-sided p, arrangements)."""
    import itertools
    import math
    allds = deep + shallow
    k = len(shallow)

    def r(sh, dp):
        return rate(sh, key, n) / rate(dp, key, n)
    obs = r(shallow, deep)
    one = two = total = 0
    for idx in itertools.combinations(range(len(allds)), k):
        sh = [allds[i] for i in idx]
        dp = [allds[i] for i in range(len(allds)) if i not in idx]
        v = r(sh, dp)
        total += 1
        one += v <= obs + 1e-12
        two += abs(math.log(v)) >= abs(math.log(obs)) - 1e-12
    return {"one_sided": [one, total], "two_sided": [two, total]}


def phase2_seconds(rep):
    out = {}
    for s in rep["seconds"]:
        if s.get("phase") != 2 or s["mute"]:
            continue
        b = out.setdefault(str(s["target"]), {"live_s": 0, "settled_s": 0, "lost": 0, "underruns": 0,
                                              "overflow": 0, "fill_settled": []})
        b["live_s"] += 1
        b["lost"] += BLOCKS_PER_S - s["count"]
        b["underruns"] += s["underruns"]
        b["overflow"] += s["overflow"]
        if not s["settling"]:
            b["settled_s"] += 1
            b["fill_settled"].append(s["fill"])
    for b in out.values():
        f = b.pop("fill_settled")
        b["fill_settled_mean"] = sum(f) / len(f) if f else None
    return dict(sorted(out.items(), key=lambda kv_: int(kv_[0])))


def derive(text):
    rep = v27report.build(text)
    return {"test_id": rep["test_id"], "build_id": rep["build_id"], "commit": rep["commit"],
            "timeline": timeline(text, rep), "phase2": phase2_path(text, rep), "cstick": cstick(text),
            "m4": m4(rep), "phase2_seconds": phase2_seconds(rep)}


def main(argv):
    rest = list(argv[1:])
    out = None
    if "--json" in rest:
        j = rest.index("--json")
        out = rest[j + 1]
        del rest[j:j + 2]
    with open(rest[0], encoding="utf-8", errors="replace") as f:
        r = derive(f.read())
    print("%s / %s / %s" % (r["test_id"], r["build_id"], r["commit"]))
    for m in r["timeline"]["marks"]:
        print("  %-14s %9.3f s from the capture's start  %9.3f s from the origin"
              % (m["what"], m["from_capture_s"], m["from_origin_s"]))
    for s in r["phase2"]["settings"]:
        print("  setting %d: start %d, LEFT %s, steps L %d R %d, refused %s, path %s, confirmed %s%s"
              % (s["index"], s["start"], s["left"], s["steps"]["L"], s["steps"]["R"], s["refused"], s["path"],
                 s["confirmed"], ", level at the stop %d" % s["level_at_stop"] if "level_at_stop" in s else ""))
    c = r["cstick"]
    print("  C-stick: SYNCEND cs %d acted %d; records %d acted %d; %s; SYNCREF %s"
          % (c["syncend_cs"], c["syncend_acted"], c["records"], c["acted"], c["by_phase"], c["syncref"]))
    for name, a in r["m4"]["arms"].items():
        print("  %-7s %d dwells, %d live s (%d settled): lost %d = %.3f/s (settled %.3f/s), underruns %d, overflow %d"
              % (name, a["dwells"], a["live_s"], a["settled_s"], a["lost"], a["per_s"], a["per_s_settled"],
                 a["underruns"], a["overflow"]))
    for tag, x in r["m4"]["ratio"].items():
        print("  SHALLOW/DEEP loss rate over %s seconds %.3f, 90 %% by dwell %.3f..%.3f"
              % (tag, x["shallow_over_deep"], x["ci90"][0], x["ci90"][1]))
    pm = r["m4"]["permutation"]
    print("  exact permutation of the dwells: one-sided p %d/%d, two-sided %d/%d"
          % (pm["one_sided"][0], pm["one_sided"][1], pm["two_sided"][0], pm["two_sided"][1]))
    for t, b in r["phase2_seconds"].items():
        print("  phase 2 at %5s: %2d live s (%2d settled), lost %3d, underruns %d, settled fill %s"
              % (t, b["live_s"], b["settled_s"], b["lost"], b["underruns"],
                 "-" if b["fill_settled_mean"] is None else "%.1f" % b["fill_settled_mean"]))
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(r, f, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
