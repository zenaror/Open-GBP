#!/usr/bin/env python3
"""tools/playread.py -- reads a gbp-play-gba (GBP-PLAY-002) SD log and prints what the session's own records say, gate by gate, with the gates a play log CANNOT carry named as VOID
instead of reported as passed (HARDWARE_TESTS.md V31.6). GitHub Issue #153, the build half.

    tools/playread.py <log-file>

THE RECORDS ARE THE V28 CHASSIS' where they survive (IDENT, VSTATE end, V28C, V28C2, V28CORR, V28TAPS, V28PHC/V28PHD, SYNCPE/SYNCPH, KEYLOG) and the play image's own where they
are new (PLAYCFG, ENVMEM, PLAYSTARTUP, PLAYUND, PLAYUNDER, CARTDECL). Nothing here is a verdict the Issue has not frozen: it computes the figures, says which gate each belongs to and
never decides the fallback rule (Issue #142's: one rung deeper per evidence, the Orchestrator's call) -- it prints the rule's ONLY input, `after_startup`.

WHAT IT REFUSES TO SAY. (1) A `-dirty` commit is printed as NOT A CANDIDATE. (2) A research record that only the V28 research phases write (V28_NULLM, V28_3BM, V28_SWEEP, V28_3A, ...) in a play log
is reported as UNEXPECTED, not read. (3) The gates that read them (fill at the target and READY per confirm, the 3b chunk-start mean, the sweep's landings) are VOID, by name. (4) A store-cap stop
is a ROW that says so (the status reads ok_no_change_inconclusive), not a failed run. (5) The Operator's observation and the CARTDECL line are DECLARATIONS, never machine readings.

Standard library only. The per-phase loss is tools/v28verdict.py's own phase_loss() (Issue #138), unchanged.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v28verdict  # noqa: E402

TEST_ID = "GBP-PLAY-002"
PHASE_NAMES = {0: "navigate", 1: "play"}
STARTUP_K_DEFAULT = 64
LOSS_BAND = (0.0010, 0.0040)          # 0.10-0.40 % per phase (V31.6, from Issue #138's band)
STORE_CAP_STOPS = ("event_store_cap", "frame_store_cap")
RESEARCH_ONLY = ("V28_3A", "V28_3B", "V28_3BM", "V28ANCHOR", "V28_SWEEP", "V28_SWEEPM", "V28_SWEEPC", "V28_SWEEP_VERDICT", "V28_NULL", "V28_NULLM",
                 "V28_LOSS", "V28LOSSCFG", "V28LABEL", "V28DMA", "V28DMAP", "V28DMAR", "V28MARK", "V28MARKS", "SYNCCS")
VOID_GATES = ("fill at the target and READY at AHEAD - 1 or AHEAD per confirm (V28_NULLM)",
              "the chunk-start mean of 3b (V28_3BM)",
              "the sweep's landings (V28_SWEEP*)")
SURVIVING_NOT_RECOMPUTED = ("the startup profile", "Policy A", "the KEY record", "the CONTROL record (orig=92; a GBA cartridge: the bit 0x01 guard is not exercised)")


def kv(rest):
    return v28verdict.kv(rest)


def records(text):
    """[(tag, rest)] for every `<6-digit seq> TAG rest` log line, in order."""
    out = []
    for m in re.finditer(r"^\d{6} (\S+)(?: (.*))?$", text, re.M):
        out.append((m.group(1), m.group(2) or ""))
    return out


def last(recs, tag):
    r = [rest for t, rest in recs if t == tag]
    return kv(r[-1]) if r else None


def every(recs, tag):
    return [kv(rest) for t, rest in recs if t == tag]


def analyse(text):
    recs = records(text)
    out = {"problems": [], "notes": []}
    ident = last(recs, "IDENT")
    out["ident"] = ident
    if ident is None:
        out["problems"].append("no IDENT record")
    else:
        out["test_ok"] = ident.get("test") == TEST_ID
        if not out["test_ok"]:
            out["problems"].append("IDENT test=%s, not %s: this is not a play-image log" % (ident.get("test"), TEST_ID))
        out["dirty"] = ident.get("commit", "").endswith("-dirty")
    out["cfg"] = last(recs, "PLAYCFG")
    if out["cfg"] is None:
        out["problems"].append("no PLAYCFG record")
    else:
        if out["cfg"].get("target") != "4096" or out["cfg"].get("ahead") != "1":
            out["notes"].append("PLAYCFG target=%s ahead=%s: NOT the T256 A1 setting of V31.1" % (out["cfg"].get("target"), out["cfg"].get("ahead")))
    out["unexpected"] = sorted(set(t for t, _ in recs if t in RESEARCH_ONLY))
    # the service and transport gates
    ends = [kv(rest) for t, rest in recs if t == "VSTATE" and rest.startswith("end ")]
    end = ends[-1] if ends else None
    out["vstate_end"] = end
    if end is None:
        out["problems"].append("no `VSTATE end` record")
    else:
        out["service"] = {"status": end.get("status"), "stop": end.get("stop"), "restore": end.get("restore"),
                          "errors": end.get("errors"), "transport_ok": end.get("transport_ok")}
        out["store_cap_row"] = end.get("stop") in STORE_CAP_STOPS
        out["service"]["pass"] = (end.get("errors") == "0" and end.get("transport_ok") == "1" and end.get("restore") == "ok"
                                  and (end.get("status") == "ok_session_ended" or out["store_cap_row"]))
    # the capture's integrity
    c2, corr, taps, c = last(recs, "V28C2"), last(recs, "V28CORR"), last(recs, "V28TAPS"), last(recs, "V28C")
    cap = []
    if c2 is None:
        cap.append("no V28C2 record")
    else:
        for f in ("lost", "syncpe_lost", "lines_lost"):
            if int(c2.get(f, "0")) != 0:
                cap.append("V28C2 %s=%s (nonzero)" % (f, c2[f]))
    if corr is None:
        cap.append("no V28CORR record")
    elif int(corr.get("overflow", "0")) != 0:
        cap.append("V28CORR overflow=%s (nonzero)" % corr["overflow"])
    if taps is None:
        cap.append("no V28TAPS record")
    else:
        if taps.get("taps") != taps.get("blocks_in"):
            cap.append("V28TAPS taps=%s != blocks_in=%s" % (taps.get("taps"), taps.get("blocks_in")))
        for f in ("taps_failed", "wrong_len"):
            if int(taps.get(f, "0")) != 0:
                cap.append("V28TAPS %s=%s (nonzero)" % (f, taps[f]))
    kl = last(recs, "KEYLOG")
    out["keylog"] = kl
    if kl is not None and (int(kl.get("lost", "0")) or int(kl.get("truncated", "0"))):
        out["notes"].append("KEYLOG lost=%s truncated=%s: the KEY record is not complete" % (kl.get("lost"), kl.get("truncated")))
    out["capture"] = {"pass": not cap, "problems": cap}
    # phases
    syncph = every(recs, "SYNCPH")
    out["phases"] = [{"phase": int(p["phase"]), "name": PHASE_NAMES.get(int(p["phase"]), "?"), "ended": p.get("ended") == "1", "reason": p.get("reason")} for p in syncph]
    # loss per phase
    pl = v28verdict.phase_loss(text)
    out["loss"] = []
    for r in pl["rows"]:
        loss = float(r["loss"]) if r["loss"] is not None else None
        out["loss"].append({"p": r["p"], "name": PHASE_NAMES.get(r["p"], "?"), "secs": float(r["secs"]), "loss": loss, "underruns": r["underruns"],
                            "in_band": loss is not None and LOSS_BAND[0] <= loss <= LOSS_BAND[1], "ended": r["ended"]})
    # underruns: the chain's total, the phase counts, and the start-up apart
    under = {"total": int(c["underruns"]) if c and "underruns" in c else None, "by_phase": dict((r["p"], r["underruns"]) for r in pl["rows"])}
    st = last(recs, "PLAYSTARTUP")
    und = every(recs, "PLAYUND")
    summ = last(recs, "PLAYUNDER")
    under["startup_record"] = st
    under["records"] = [{"n": int(u["n"]), "handed": int(u["handed"]), "since_dma_ms": int(u["since_dma_ms"]), "post_feed": u.get("post_feed") == "1"} for u in und]
    if summ is None:
        under["summary"] = None
        if st is not None and st.get("t_dma") != "none":
            out["problems"].append("no PLAYUNDER record")
    else:
        s = dict((k, (None if v == "-" else int(v))) for k, v in summ.items())
        under["summary"] = s
        k = s.get("k")
        inc = []
        cfg_k = int(out["cfg"]["startup_k"]) if out["cfg"] and out["cfg"].get("startup_k", "").isdigit() else None
        if k != STARTUP_K_DEFAULT or (cfg_k is not None and cfg_k != k):
            inc.append("k=%s in PLAYUNDER, %s in PLAYCFG, registered %d: the start-up delimiter is not the registered one" % (k, cfg_k, STARTUP_K_DEFAULT))
        if s["startup"] + s["after_startup"] + s["post_feed"] != s["total"]:
            inc.append("startup + after_startup + post_feed != total")
        if under["total"] is not None and s["total"] != under["total"]:
            inc.append("PLAYUNDER total=%d != V28C underruns=%d" % (s["total"], under["total"]))
        if under["by_phase"] and sum(under["by_phase"].values()) != (under["total"] if under["total"] is not None else s["total"]):
            inc.append("the phase underruns (V28PHC) sum to %d, not the session's %d" % (sum(under["by_phase"].values()), under["total"] if under["total"] is not None else s["total"]))
        if len(und) != min(s["total"], 64):
            inc.append("%d PLAYUND record(s) for %d underrun(s) (expected %d)" % (len(und), s["total"], min(s["total"], 64)))
        recs_u = under["records"]
        if sum(1 for u in recs_u if u["handed"] <= k) != s["startup"]:
            inc.append("the PLAYUND ordinals do not give startup=%d at k=%s" % (s["startup"], k))
        pf = sum(1 for u in recs_u if u["handed"] > k and u["post_feed"])
        if s["post_feed"] < pf:
            inc.append("PLAYUNDER post_feed=%d but %d PLAYUND record(s) are post-feed" % (s["post_feed"], pf))
        if s["post_feed"] > pf and not (recs_u and recs_u[-1]["post_feed"]):
            inc.append("PLAYUNDER post_feed=%d exceeds the %d post-feed PLAYUND record(s) and the last record is not post-feed (the unrecorded ones could not be post-feed)" % (s["post_feed"], pf))
        first = next((u["handed"] for u in recs_u if u["handed"] > k and not u["post_feed"]), None)
        if first != s["first_after_handed"]:
            inc.append("first_after_handed=%s but the PLAYUND records give %s" % (s["first_after_handed"], first))
        if any(u["handed"] == 1 for u in recs_u):
            inc.append("a PLAYUND with handed=1: the start's own hand-off cannot underrun (start_ready needs a ready chunk); the premise of the ordinals is violated")
        if any(b["handed"] <= a["handed"] for a, b in zip(recs_u, recs_u[1:])):
            inc.append("the PLAYUND ordinals do not rise")
        under["inconsistent"] = inc
        if inc:
            out["problems"].extend("underrun record: " + i for i in inc)
    out["under"] = under
    # the declaration
    decl = [rest for t, rest in recs if t == "CARTDECL"]
    out["cartdecl"] = decl[-1] if decl else None
    if len(decl) > 1:
        out["problems"].append("%d CARTDECL lines (one expected)" % len(decl))
    out["envmem"] = last(recs, "ENVMEM")
    env = last(recs, "ENVSTORE")
    out["envstore"] = env
    return out


def render(out):
    L = []
    i = out["ident"] or {}
    L.append("PLAYREAD  test=%s build=%s commit=%s" % (i.get("test", "?"), i.get("build", "?"), i.get("commit", "?")))
    if out.get("dirty"):
        L.append("  IDENTITY: the commit carries -dirty: NOT A CANDIDATE (AGENTS.md: hardware is never tested with a -dirty build)")
    if out["cfg"]:
        c = out["cfg"]
        L.append("  PLAYCFG: target=%s ahead=%s step=%s k=%s play_bound_s=%s cap=%s wall=%s cold_start=%s mode=%s" % (
            c.get("target"), c.get("ahead"), c.get("step"), c.get("startup_k"), c.get("play_bound_s"), c.get("session_cap_s"), c.get("wall_s"), c.get("cold_start"), c.get("mode")))
    for n in out["notes"]:
        L.append("  note: %s" % n)
    s = out.get("service")
    if s:
        L.append("SERVICE/TRANSPORT: %s  (status=%s stop=%s restore=%s errors=%s transport_ok=%s)" % ("PASS" if s["pass"] else "FAIL", s["status"], s["stop"], s["restore"], s["errors"], s["transport_ok"]))
        if out.get("store_cap_row"):
            L.append("  STORE-CAP ROW: the session ended at %s (status reads ok_no_change_inconclusive); a row of the matrix, not a failed run" % s["stop"])
    L.append("CAPTURE: %s" % ("PASS" if out["capture"]["pass"] else "FAIL"))
    for p in out["capture"]["problems"]:
        L.append("  - %s" % p)
    for ph in out["phases"]:
        L.append("  phase %d (%s): %s, reason=%s" % (ph["phase"], ph["name"], "ended" if ph["ended"] else "not ended", ph["reason"]))
    for r in out["loss"]:
        band = "" if (r["in_band"] or r["loss"] is None) else "   OUTSIDE the 0.10-0.40 % band: a ROW that says so"
        L.append("LOSS p%d (%s): %s over %.1f s%s" % (r["p"], r["name"], "n/a" if r["loss"] is None else "%.3f %%" % (r["loss"] * 100), r["secs"], band))
    u = out["under"]
    L.append("UNDERRUNS: V28C total=%s, by phase %s" % (u["total"], ", ".join("p%d=%d" % (p, n) for p, n in sorted(u["by_phase"].items())) or "-"))
    if u["startup_record"]:
        L.append("  PLAYSTARTUP: %s" % " ".join("%s=%s" % kv_ for kv_ in u["startup_record"].items()))
    for r in u["records"]:
        L.append("  PLAYUND n=%d handed=%d since_dma_ms=%d%s" % (r["n"], r["handed"], r["since_dma_ms"], "  POST-FEED (teardown silence)" if r["post_feed"] else ""))
    if u["summary"]:
        q = u["summary"]
        L.append("  PLAYUNDER: startup=%s after_startup=%s post_feed=%s first_after_handed=%s unrecorded=%s total=%s k=%s" % (
            q["startup"], q["after_startup"], q["post_feed"], "-" if q["first_after_handed"] is None else q["first_after_handed"], q["unrecorded"], q["total"], q["k"]))
        L.append("  THE FALLBACK RULE'S ONLY INPUT (Issue #142): after_startup=%d (post_feed, the silence of a teardown whose feed had stopped, is NOT in it and is not a finding about the setting). This tool does not apply the rule; one rung per evidence is the Orchestrator's call, and the Operator's report of picotes is recorded beside the count, never substituted for it." % q["after_startup"])
    L.append("CARTDECL (an OPERATOR DECLARATION, not a machine reading): %s" % (out["cartdecl"] if out["cartdecl"] else "no line: UNDECLARED"))
    if out["envmem"]:
        L.append("ENVMEM: arena1_free=%s (the floor of GBP-HW-262 is 1650688) frames_bytes=%s events_bytes=%s corr_bytes=%s" % (
            out["envmem"].get("arena1_free"), out["envmem"].get("frames_bytes"), out["envmem"].get("events_bytes"), out["envmem"].get("corr_bytes")))
    L.append("SURVIVE, not recomputed here (their own readers): %s" % "; ".join(SURVIVING_NOT_RECOMPUTED))
    L.append("VOID IN A PLAY LOG (no record exists; NOT reported as passed): %s" % "; ".join(VOID_GATES))
    if out["unexpected"]:
        L.append("UNEXPECTED research record(s) in a play log, not read: %s" % ", ".join(out["unexpected"]))
    for p in out["problems"]:
        L.append("PROBLEM: %s" % p)
    return "\n".join(L)


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        text = f.read()
    print(render(analyse(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
