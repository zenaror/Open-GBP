#!/usr/bin/env python3
"""
tools/v27report.py — the SD log of the latency round (sync-0001, GBP-AUDIO-012, HARDWARE_TESTS.md §V27) turned into
the report JSON that the frozen tools/v27accept.py reads. A BUILDER: it decides nothing.

    tools/v27report.py <log> [--json <out>]

THE RECORDS it reads (every one written by poc/gbp-audio-sync to the SD log only; the live channel carries none of
them), in the ringlog form `NNNNNN TAG k=v k=v ...`:
  IDENT      test= app= build= commit=
  SYNCCFG    deep= shallow= floor= mute= step_mute= p2_lo= p2_hi= p2_step= p3_start= p3_step= p3_dwell_s= p3_bisect=
  SYNCCFG2   p3_min= cap_p1= cap_p2= cap_p3= cap_session= real= null= settling_s= awr_blocks= cfg_faults=
  SYNCCFG3   p3_confirm_s= prompt_bound_s=             (the confirmation hold, §V27.14; the prompt's bound)
             (one configuration on two lines: the ringlog cuts at 248 characters)
  LIVE       phase= ... press_before_prompt=            LIVET   t0= t_accept= t_press= t_origin= t_end=  (hex)
  SYNCSEED   seed= initial=DEEP|SHALLOW                  the seed the runtime took at the A press
  SYNCSCHED  n=18 kinds=R,R,N,...                        the 18 switches as the runtime drew them
  SYNCP2CFG  starts=a,b,c dirs=D|S,D|S,D|S               the three Phase 2 starts and the LEFT direction (D deeper)
  SYNCSW     seq= kind=REAL|NULL from= to= t= discard= pause=      one per Phase 1 switch, in order
  SYNCANS    seq= answer=MORE|LESS|SAME t=                          one per answered switch
  SYNCP2     seq= kind=START|STEP from= to= t=                      every Phase 2 transition
  SYNCSET    seq= start= dir=D|S steps= target= t=                  one per confirmed Phase 2 setting
  SYNCDEPTH  n= kind=STEP|BISECT|CONFIRM target= fill16= underruns= overflow= dup= drop= lost= starved= t_start=
             t_end= partial=         (CONFIRM: §V27.14's hold at the highest failing depth; starved is gbp_aplay's
             ring_gated over the dwell -- a chunk WANTED, the ring short -- not its starved_steps)
             (a partial dwell -- cut by a cap, the session cap or Z -- with dup == 0 goes to `descent_unfinished`:
             no DUP YET observes nothing; one with dup > 0 has held (dup never decreases) and stays in `descent`;
             the CONFIRM hold stays in `descent`, cut or not -- the gate reads its length)
  SYNCDEPTH2 n= starved= ready_in= ready_out= fill_in= fill_out= fill_n=      (the dwell's drain, beside its row:
             the steps that wanted a chunk and found the ring short (ring_gated), the READY queue and the ring at the dwell's
             start and end, the whole seconds behind fill16 -- 0 makes fill_mean null)
  SYNCPH     phase=1|2|3 t_start= t_end= ended=complete|cap|session|z|null     (null: cut by a vstate stop)
  SYNCSECC/SYNCSECF/SYNCSECT/SYNCSECP/SYNCSECM/SYNCSECS/SYNCSECU/SYNCSECO   from=<k> <field>=v,v,...  (16 a line)
             the per-second arrays: blocks counted, mean fill x16, target, phase, mute flag, settling flag,
             underrun delta, overflow delta
  SYNCC      underruns= overflow= silences= mute_handed= dup= drop= produced= handed= ring_gated=
  SYNCTX     seq= done= mech=ROTATE|HELD|UNMUTED mute= rot= res= late= unmasked= topped=   one per switch: its
             transition as the executor carried it out. done: 1 landed, 2 cut (never), 3 begun and not landed
             (the session stopped under it), 0 never begun. masked
             (§V27.15, by content): ROTATE, landed, not unmasked -- a late rotation joins READY contiguously and
             a deepening or a null is contiguous whatever its rotations; res is the effective level minus the
             target (the ring, a chunk under way, READY beyond AHEAD - 1)
  SYNCTXA    begun= completed= faults= rotate= lates= unmasked= res=<min>..<max> converted= shorts= short_max=
             trim_max= trim_sum=                     (the executor over the whole session)
  SYNCC2     discarded= starved_steps= lost= blocks_in= ring_discarded= counter_faults= sec_overflow= lines_lost=
             trans_faults= dropped_front=      (starved_steps: every step under 129, the benign wait included --
             NOT §V27.14's starved, which is SYNCDEPTH's ring_gated delta)
  SYNCP3     pending= drained= refused_depth_done= depths= overflow=   (a cut dwell still unreported: pending 0
             expected; drained counts a row reported after the session by the backstop)
  SYNCREF    switch_unanswered= switch_mute= switch_exhausted= switch_phase= answer= step_mute= step_end= step_phase=
             step_value= confirm=                     (the session's refusals; the three lines are one counters dict)
  SYNCAWR    blocks= cap= t_arm= t_first= t_last= faults= ignored= seen= state=      (the ride-along)
  SYNCAWRC   copy_min= copy_max= copy_sum= copy_n=                                  (its copy cost)
  SYNCEND    reason=session|not_finished|no_origin|prompt_expired|<vstate stop name> t= secs= ... cs_dead= cs_busy=
             preempts= stop=   (cs_busy: plan-making C-stick edges refused while the executor landed the last
             plan; preempts: plans applied over a running one -- never, the module's tick waits for the executor)
             (stop= is the vstate stop name in every form; `session` is STOP_SESSION_END with the session finished)

THE LOG'S OWN HEADER (`lines= dropped= truncated=`, written by src/platform/sdlog.c) is read first: a log that
reports a truncated or a dropped line is REFUSED, because a record cut by the ringlog cannot be told from a
complete one by its text alone. A log whose session never started (SYNCEND reason=no_origin or prompt_expired,
secs=0: the A press never came, or came later than the prompt's bound) is REFUSED with that cause: there is
nothing to report, and building it would blame the build for an Operator who did not press.

THE SCHEDULE IS RECOMPUTED from the seed with the runtime's own generator (src/audio/gbp_async.c, documented in its
header) and the builder REFUSES a log whose SYNCSCHED differs from it: a schedule the seed does not explain is a
run whose blinding cannot be audited. The generator: xorshift32 (x ^= x << 13; x ^= x >> 17; x ^= x << 5; 32-bit)
seeded with `seed`; draw 1 -> the initial level (bit 0: 0 DEEP, 1 SHALLOW); the 18 slots start as 12 R then 6 N and
are shuffled by Fisher-Yates from i = 17 down to 1 with one draw each, j = x % (i + 1); if slot 0 is N it is swapped
with the first R; then three draws for the Phase 2 starts, each p2_lo + (x % 26) * p2_step; then three draws for
the directions (bit 0: 0 D, 1 S). A seed of 0 is replaced by 1 (xorshift32 is stuck at 0); the logged seed
stays 0. Pinned against the runtime's own vector for seed 0x9E3779B9 in tests/host/test_v27report.py.

Standard library only; reads the log it is given, writes the JSON it is asked to.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import v22report  # noqa: E402

TB_HZ = 40500000
SEC_TAGS = {"SYNCSECC": "counts", "SYNCSECF": "fill16", "SYNCSECT": "target", "SYNCSECP": "phase",
            "SYNCSECM": "mute", "SYNCSECS": "settling", "SYNCSECU": "underruns", "SYNCSECO": "overflow"}
P2_GRID = 26


def _xorshift32(x):
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= x >> 17
    x ^= (x << 5) & 0xFFFFFFFF
    return x & 0xFFFFFFFF


def schedule_from_seed(seed, real=12, null=6, p2_lo=384, p2_step=128):
    """The runtime's generator, in Python (see the module docstring). A seed of 0 is 1, as in the runtime."""
    x = _xorshift32(seed if seed else 1)
    initial = "SHALLOW" if x & 1 else "DEEP"
    slots = ["REAL"] * real + ["NULL"] * null
    for i in range(len(slots) - 1, 0, -1):
        x = _xorshift32(x)
        j = x % (i + 1)
        slots[i], slots[j] = slots[j], slots[i]
    if slots[0] == "NULL":
        k = slots.index("REAL")
        slots[0], slots[k] = slots[k], slots[0]
    starts = []
    for _ in range(3):
        x = _xorshift32(x)
        starts.append(p2_lo + (x % P2_GRID) * p2_step)
    dirs = []
    for _ in range(3):
        x = _xorshift32(x)
        dirs.append("LEFT_SHALLOWER" if x & 1 else "LEFT_DEEPER")
    return {"initial": initial, "schedule": slots, "p2_starts": starts, "p2_dirs": dirs}


def records(text):
    """tag -> [line body ...], every `NNNNNN TAG body` line, in order (v22report's regex reads LIVE* only)."""
    out = {}
    for m in re.finditer(r"^\d{6} ([A-Z][A-Z0-9]*) (.*)$", text, re.M):
        out.setdefault(m.group(1), []).append(m.group(2))
    return out


def _series(recs, tag, field, n):
    vals = []
    for line in recs.get(tag, []):
        kv = v22report._kv(line)
        if int(kv["from"]) != len(vals):
            raise ValueError("%s lines are not contiguous: from=%s after %d values" % (tag, kv["from"], len(vals)))
        vals += [int(c) for c in kv[field].split(",") if c]
    if len(vals) < n:
        raise ValueError("%s holds %d values for %d seconds" % (tag, len(vals), n))
    return vals[:n]


def _need(recs, tag):
    if tag not in recs:
        raise ValueError("no %s record: not a GBP-AUDIO-012 log" % tag)
    return v22report._kv(recs[tag][-1])


def _need_all(recs, *tags):
    """One dict from the last line of each of the tags (a record the image splits over lines); every tag needed."""
    out = {}
    for tag in tags:
        out.update(_need(recs, tag))
    return out


def _header_refusal(text):
    m = re.search(r"^lines=(\d+) dropped=(\d+) truncated=(\d+)$", text, re.M)
    if not m:
        raise ValueError("no `lines= dropped= truncated=` header: not an OPENGBP-LOG")
    if int(m.group(2)) or int(m.group(3)):
        raise ValueError("the log's header reports dropped=%s truncated=%s lines: a record may be cut or missing; refused"
                         % (m.group(2), m.group(3)))


def build(text):
    _header_refusal(text)
    recs = records(text)
    ident = _need(recs, "IDENT")
    c = _need_all(recs, "SYNCCFG", "SYNCCFG2", "SYNCCFG3")
    cfg = {"deep": int(c["deep"]), "shallow": int(c["shallow"]), "floor": int(c["floor"]),
           "mute_chunks": int(c["mute"]), "step_mute_chunks": int(c["step_mute"]), "p2_lo": int(c["p2_lo"]),
           "p2_hi": int(c["p2_hi"]), "p2_step": int(c["p2_step"]), "p3_start": int(c["p3_start"]),
           "p3_step": int(c["p3_step"]), "p3_dwell_s": int(c["p3_dwell_s"]), "p3_bisect": int(c["p3_bisect"]),
           "p3_min": int(c["p3_min"]),
           "caps": {"p1": int(c["cap_p1"]), "p2": int(c["cap_p2"]), "p3": int(c["cap_p3"]),
                    "session": int(c["cap_session"])},
           "real": int(c["real"]), "null": int(c["null"]), "settling_s": int(c["settling_s"]),
           "awr_blocks": int(c["awr_blocks"]), "p3_confirm_s": int(c["p3_confirm_s"]),
           "prompt_bound_s": int(c["prompt_bound_s"])}
    live = _need(recs, "LIVE")
    lt = _need(recs, "LIVET")
    press = {"t_press": int(lt["t_press"], 16), "t_origin": int(lt["t_origin"], 16),
             "before_prompt": live.get("press_before_prompt", "0") == "1"}

    assign = None
    if "SYNCSEED" in recs and "SYNCSCHED" in recs and "SYNCP2CFG" in recs:
        sd = _need(recs, "SYNCSEED")
        sc = _need(recs, "SYNCSCHED")
        p2 = _need(recs, "SYNCP2CFG")
        kinds = [{"R": "REAL", "N": "NULL"}[k] for k in sc["kinds"].split(",") if k]
        if len(kinds) != int(sc["n"]):
            raise ValueError("SYNCSCHED n=%s but %d kinds" % (sc["n"], len(kinds)))
        seed = int(sd["seed"], 16)
        gen = schedule_from_seed(seed, cfg["real"], cfg["null"], cfg["p2_lo"], cfg["p2_step"])
        starts = [int(v) for v in p2["starts"].split(",") if v]
        dirs = [{"D": "LEFT_DEEPER", "S": "LEFT_SHALLOWER"}[d] for d in p2["dirs"].split(",") if d]
        logged = {"initial": sd["initial"], "schedule": kinds, "p2_starts": starts, "p2_dirs": dirs}
        if logged != gen:
            raise ValueError("the logged schedule is not the one the seed %08x generates: logged %s, generated %s"
                             % (seed, logged, gen))
        assign = dict(gen, seed=seed)

    switches = []
    for line in recs.get("SYNCSW", []):
        kv = v22report._kv(line)
        sw = {"seq": int(kv["seq"]), "kind": kv["kind"], "from": int(kv["from"]), "to": int(kv["to"]),
              "t": int(kv["t"], 16), "discard": int(kv["discard"]), "pause": int(kv["pause"]),
              "answer": None, "t_answer": None}
        if sw["seq"] != len(switches):
            raise ValueError("SYNCSW seq=%d out of order after %d" % (sw["seq"], len(switches)))
        switches.append(sw)
    for line in recs.get("SYNCTX", []):
        kv = v22report._kv(line)
        seq = int(kv["seq"])
        if seq >= len(switches):
            raise ValueError("SYNCTX seq=%d for a switch that was never made" % seq)
        switches[seq]["tx"] = {"done": int(kv["done"]), "mech": kv["mech"], "mute": int(kv["mute"]),
                               "rotations": int(kv["rot"]), "residue": int(kv["res"]), "late": int(kv["late"]),
                               "unmasked": int(kv["unmasked"]), "topped": int(kv["topped"])}
        switches[seq]["tx"]["masked"] = (kv["mech"] == "ROTATE" and int(kv["done"]) == 1 and not int(kv["unmasked"]))
    for line in recs.get("SYNCANS", []):
        kv = v22report._kv(line)
        seq = int(kv["seq"])
        if seq >= len(switches):
            raise ValueError("SYNCANS seq=%d for a switch that was never made" % seq)
        if switches[seq]["answer"] is not None:
            raise ValueError("SYNCANS seq=%d answered twice" % seq)
        switches[seq]["answer"] = kv["answer"]
        switches[seq]["t_answer"] = int(kv["t"], 16)

    nulling = []
    for line in recs.get("SYNCSET", []):
        kv = v22report._kv(line)
        nulling.append({"seq": int(kv["seq"]), "start": int(kv["start"]),
                        "direction": {"D": "LEFT_DEEPER", "S": "LEFT_SHALLOWER"}[kv["dir"]],
                        "steps": int(kv["steps"]), "target": int(kv["target"]), "t": int(kv["t"], 16)})
    p2_transitions = []
    for line in recs.get("SYNCP2", []):
        kv = v22report._kv(line)
        p2_transitions.append({"seq": int(kv["seq"]), "kind": kv["kind"], "from": int(kv["from"]),
                               "to": int(kv["to"]), "t": int(kv["t"], 16)})
    descent, descent_unfinished = [], []
    extra = {}
    for line in recs.get("SYNCDEPTH2", []):
        kv = v22report._kv(line)
        extra[int(kv["n"])] = dict((k, int(kv[k])) for k in ("starved", "ready_in", "ready_out", "fill_in", "fill_out",
                                                              "fill_n"))
    for line in recs.get("SYNCDEPTH", []):
        kv = v22report._kv(line)
        x = extra.get(int(kv["n"]))
        row = {"n": int(kv["n"]), "kind": kv["kind"], "target": int(kv["target"]),
               "fill_mean": None if (x and x["fill_n"] == 0) else int(kv["fill16"]) / 16.0,
               "underruns": int(kv["underruns"]),
               "overflow": int(kv["overflow"]), "dup": int(kv["dup"]), "drop": int(kv["drop"]),
               "lost": int(kv["lost"]), "starved": int(kv["starved"]), "t_start": int(kv["t_start"], 16),
               "t_end": int(kv["t_end"], 16), "partial": int(kv.get("partial", "0"))}
        if x:
            if x["starved"] != row["starved"]:
                raise ValueError("SYNCDEPTH n=%d: starved %d but SYNCDEPTH2 says %d -- the same count, taken twice"
                                 % (row["n"], row["starved"], x["starved"]))
            row.update(x)
        # a dwell cut before its end (partial=1) with dup == 0 observes nothing: §V27.14's predicate is over the
        # whole dwell, and dup == 0 over the tens of ms before a cut only means no DUP YET (review round 3: a cut
        # 20 ms into 146 made (144, 146] a confident (146, 148]). It is carried beside, in descent_unfinished. A
        # cut dwell with dup > 0 HAS held -- dup never decreases, so the whole dwell's dup would be > 0 too -- and
        # stays. The CONFIRM hold stays whatever: the gate reads its length and its cut.
        (descent_unfinished if row["partial"] and row["dup"] == 0 and row["kind"] != "CONFIRM" else descent).append(row)
    phases = {"p1": None, "p2": None, "p3": None}
    for line in recs.get("SYNCPH", []):
        kv = v22report._kv(line)
        phases["p%s" % kv["phase"]] = {"t_start": int(kv["t_start"], 16), "t_end": int(kv["t_end"], 16),
                                       "ended": None if kv["ended"] == "null" else kv["ended"]}
    for k in phases:
        if phases[k] is None:
            phases[k] = {"t_start": None, "t_end": None, "ended": None}

    end = _need(recs, "SYNCEND")
    if end["reason"] in ("no_origin", "prompt_expired") or int(end["secs"]) == 0:
        raise ValueError("the session never started (SYNCEND reason=%s secs=%s): nothing to report; refused"
                         % (end["reason"], end["secs"]))
    n = int(end["secs"])
    cols = dict((name, _series(recs, tag, name, n)) for tag, name in SEC_TAGS.items())
    seconds = [{"s": i, "phase": cols["phase"][i], "target": cols["target"][i], "mute": bool(cols["mute"][i]),
                "settling": bool(cols["settling"][i]), "count": cols["counts"][i], "fill": cols["fill16"][i] / 16.0,
                "underruns": cols["underruns"][i], "overflow": cols["overflow"][i]} for i in range(n)]

    p3 = None
    if "SYNCP3" in recs:
        p3 = dict((k, int(v)) for k, v in _need(recs, "SYNCP3").items())
        if p3["pending"]:
            raise ValueError("SYNCP3 pending=1: a Phase 3 dwell was never reported -- its row is missing; refused")
    executor = None
    if "SYNCTXA" in recs:
        e = _need(recs, "SYNCTXA")
        lo, hi = e["res"].split("..")
        executor = dict((k, int(e[k])) for k in ("begun", "completed", "faults", "rotate", "lates", "unmasked",
                                                  "converted", "shorts", "short_max", "trim_max", "trim_sum"))
        executor.update(residue_min=int(lo), residue_max=int(hi))
    cc = _need_all(recs, "SYNCC", "SYNCC2", "SYNCREF")
    counters = dict((k, int(v)) for k, v in cc.items())
    awr = None
    if "SYNCAWR" in recs:
        a = _need_all(recs, "SYNCAWR", "SYNCAWRC")
        awr = {"blocks": int(a["blocks"]), "cap": int(a["cap"]), "t_arm": int(a["t_arm"], 16),
               "t_first": int(a["t_first"], 16), "t_last": int(a["t_last"], 16), "copy_min": int(a["copy_min"]),
               "copy_max": int(a["copy_max"]), "copy_sum": int(a["copy_sum"]), "copy_n": int(a["copy_n"]),
               "faults": int(a["faults"]), "ignored": int(a.get("ignored", "0")), "seen": int(a.get("seen", "0")),
               "state": int(a.get("state", "0"))}
    return {"test_id": ident.get("test"), "build_id": ident.get("build"), "commit": ident.get("commit"),
            "tb_hz": TB_HZ, "cfg": cfg, "assign": assign, "press": press, "phases": phases, "switches": switches,
            "nulling": nulling, "p2_transitions": p2_transitions, "descent": descent,
            "descent_unfinished": descent_unfinished, "seconds": seconds,
            "counters": counters, "awr": awr, "executor": executor, "p3": p3,
            "end": {"reason": end["reason"], "t": int(end["t"], 16), "secs": n,
                    "cs_busy": int(end.get("cs_busy", "0")), "preempts": int(end.get("preempts", "0"))}}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        r = build(f.read())
    print("%s / %s / %s: %d seconds, %d switches (%d answered), %d settings, %d depths, assignment %s, awr %s"
          % (r["test_id"], r["build_id"], r["commit"], r["end"]["secs"], len(r["switches"]),
             sum(1 for s in r["switches"] if s["answer"]), len(r["nulling"]), len(r["descent"]),
             "present" if r["assign"] else "ABSENT", "%d blocks" % r["awr"]["blocks"] if r["awr"] else "none"))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(r, f, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
