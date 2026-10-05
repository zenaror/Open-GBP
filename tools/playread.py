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

THE CAPTURE GATE IS PER PHASE (V28PHC: taps == blocks_in, failed 0, wrong 0 in every phase; Issue #156, HARDWARE_TESTS.md V31.11); the whole-session taps - blocks_in is printed as information (the pre-origin window).

WHICH IMAGE (Issue #158) is decided by IDENT `build=`, cross-checked with `app=` (vehicle-0001 <-> gbp-play-gba, vehicle-0002 <-> gbp-play-gba2), NEVER by which records are present: deciding by
presence would turn a vehicle-0002 log that lost its records into the harmless "no record in this image" line, a failure path that could never fire. vehicle-0001: the Issue #157 line, unchanged,
and any of the five startup / Policy A tags in such a log is a problem. vehicle-0002: the startup block -- the HARDWARE_TESTS.md V5.53.2 checklist rows, each MET / NOT MET / MISSING with its
source, thresholds as written there and in V5.52.15-17 (none new); a missing record is MISSING, never passed. Any other build id: a problem, and neither block. The reader prints ROWS: whether a
NOT MET row fails a session is that session's hardware Issue's pre-registration, never this tool's.

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
SURVIVING_NOT_RECOMPUTED = ("the KEY record", "the CONTROL record (orig=92; a GBA cartridge: the bit 0x01 guard is not exercised)")
# Issue #157 (HARDWARE_TESTS.md V31.12): V31.6 / V31.8 listed these two among the records the vehicle keeps. It keeps them as CODE; its log carries no record of either (no STARTUP / STARTUPT /
# STARTUPV / STREAMINV record, no OGBPDISP2 sidecar). Printed apart, as information: no gate, threshold or verdict reads this tuple.
NO_RECORD_IN_THIS_IMAGE_LOG = ("the startup profile", "Policy A")
# Issue #158: the image is the IDENT build id, cross-checked with the app name; the five records vehicle-0002 writes at teardown (src/gbp/gbp_startrec)
IMAGES = {"vehicle-0001": "gbp-play-gba", "vehicle-0002": "gbp-play-gba2"}
STARTREC_TAGS = ("STARTUP", "STARTUPT", "STARTUPV", "STREAMINV", "STREAMSELFTEST")
FIRST_HANDOFF_BOUND_MS = 400          # HARDWARE_TESTS.md V5.52.15 (frozen), V5.53.2 / V5.57.8 "< 400 ms": the strict form, compared in integers


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
        for f in ("taps_failed", "wrong_len"):
            if int(taps.get(f, "0")) != 0:
                cap.append("V28TAPS %s=%s (nonzero)" % (f, taps[f]))
    # THE TAP GATE IS PER PHASE (V28PHC), as P6 / G4 always read it (Issue #156, HARDWARE_TESTS.md V31.11). The whole-session V28TAPS counters do not count over the same span: taps
    # count from the first tap, blocks_in from the press origin (main.c: live_taps++ in the tap callback; gbp_alive_use_press_origin), so their difference is the PRE-ORIGIN
    # window of every healthy play log, a figure to print, never a verdict.
    phc = every(recs, "V28PHC")
    syncph_phases = set(kv_.get("phase") for kv_ in every(recs, "SYNCPH"))
    phase_cap = []
    for x in phc:
        row = {"p": x["p"], "taps": int(x["taps"]), "blocks_in": int(x["blocks_in"]), "failed": int(x["failed"]), "wrong": int(x["wrong"])}
        phase_cap.append(row)
        if row["taps"] != row["blocks_in"]:
            cap.append("V28PHC p=%s taps=%d != blocks_in=%d" % (row["p"], row["taps"], row["blocks_in"]))
        if row["failed"] != 0:
            cap.append("V28PHC p=%s failed=%d (nonzero)" % (row["p"], row["failed"]))
        if row["wrong"] != 0:
            cap.append("V28PHC p=%s wrong=%d (nonzero)" % (row["p"], row["wrong"]))
    if not phc:
        cap.append("no V28PHC record (the tap gate is per phase)")
    for ph in sorted(syncph_phases - set(r["p"] for r in phase_cap)):
        cap.append("phase %s has a SYNCPH record and no V28PHC record: its tap gate cannot be read" % ph)
    out["phase_capture"] = phase_cap
    out["pre_origin"] = None
    if taps is not None and taps.get("taps", "").isdigit() and taps.get("blocks_in", "").isdigit():
        out["pre_origin"] = {"taps": int(taps["taps"]), "blocks_in": int(taps["blocks_in"]), "diff": int(taps["taps"]) - int(taps["blocks_in"])}
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
    # Issue #158: which image, by the IDENT build id (cross-checked with app=), never by record presence
    image = None
    if ident is not None:
        build, app = ident.get("build"), ident.get("app")
        if build in IMAGES:
            image = build
            if app != IMAGES[build]:
                out["problems"].append("IDENT app=%s does not match build=%s (expected app=%s)" % (app, build, IMAGES[build]))
        else:
            out["problems"].append("unknown build id %s: no record expectation" % build)
    out["image"] = image
    out["startrec"] = None
    if image == "vehicle-0001":
        for tag in STARTREC_TAGS:
            if any(t == tag for t, _ in recs):
                out["problems"].append("a vehicle-0001 log cannot carry %s" % tag)
    elif image == "vehicle-0002":
        out["startrec"] = startup_block(recs)
        for tag in STARTREC_TAGS:
            n = sum(1 for t, _ in recs if t == tag)
            if n > 1:
                out["problems"].append("%d %s records (one expected)" % (n, tag))
    return out


def _int(d, key):
    v = d.get(key) if d is not None else None
    return int(v) if v is not None and re.fullmatch(r"\d+", v) else None


def startup_block(recs):
    """vehicle-0002's startup block: the V5.53.2 checklist rows, each (row, status, source) with status MET / NOT MET / MISSING, plus the information lines. No verdict."""
    su, st, sv, inv, sft = (last(recs, t) for t in STARTREC_TAGS)
    rows = []

    def row(name, need, ok, source):
        if any(r is None for r in need):
            rows.append((name, "MISSING", source + " -- record missing, NOT passed"))
        else:
            rows.append((name, "MET" if ok() else "NOT MET", source))

    def field(rec, tag, key):
        return "%s %s=%s" % (tag, key, rec.get(key, "<absent>") if rec is not None else "<no record>")

    row("mode normal", [su], lambda: su.get("mode") == "normal", field(su, "STARTUP", "mode"))
    row("visible synthetic = 0", [su], lambda: su.get("normal_clean") == "1" and su.get("presented_synthetic") == "0",
        "%s, %s" % (field(su, "STARTUP", "normal_clean"), field(su, "STARTUP", "presented_synthetic")))
    row("pre-handler wait = 0", [su], lambda: su.get("prehandler_wait_ms") == "0", field(su, "STARTUP", "prehandler_wait_ms"))
    row("black framebuffer initialisation", [su], lambda: su.get("clear_fb") == "1", field(su, "STARTUP", "clear_fb"))
    row("first real hand-off observed", [sv], lambda: sv.get("have_first") == "1", field(sv, "STARTUPV", "have_first"))
    ticks, tb = _int(sv, "ticks_control_to_first_handoff"), _int(st, "tb_hz")
    src = "%s, %s" % (field(sv, "STARTUPV", "ticks_control_to_first_handoff"), field(st, "STARTUPT", "tb_hz"))
    if ticks is not None and tb:
        src += " (%.3f ms, information only; the comparison is ticks x 1000 < %d x tb_hz = %d ticks)" % (ticks * 1000.0 / tb, FIRST_HANDOFF_BOUND_MS, FIRST_HANDOFF_BOUND_MS * tb // 1000)
    # a hand-off that never happened has ticks 0, which would be under any bound: the row needs have_first=1 (a zero that could not be otherwise is not a pass)
    row("first real hand-off < 400 ms from CONTROL", [sv, st], lambda: (sv.get("have_first") == "1" and ticks is not None and tb is not None and tb > 0
                                                                       and ticks * 1000 < FIRST_HANDOFF_BOUND_MS * tb), src)
    rows.append(("no transport failure", "SEE SERVICE/TRANSPORT", "the reader's own service and transport gate above (V5.53.2's transport row)"))
    chk, fail = _int(inv, "checks"), _int(inv, "failures")
    split = None
    if inv is not None:
        m1 = re.fullmatch(r"(\d+)/(\d+)", inv.get("main", ""))
        m2 = re.fullmatch(r"(\d+)/(\d+)", inv.get("isr", ""))
        if m1 and m2:
            split = (int(m1.group(1)), int(m1.group(2)), int(m2.group(1)), int(m2.group(2)))     # main failures, main checks, isr failures, isr checks
    inv_src = "STREAMINV checks=%s failures=%s main=%s isr=%s (main= and isr= are failures/checks)" % (
        (inv or {}).get("checks", "<absent>"), (inv or {}).get("failures", "<absent>"), (inv or {}).get("main", "<absent>"), (inv or {}).get("isr", "<absent>")) if inv is not None else "STREAMINV <no record>"
    why = []
    if inv is not None:
        if chk is None or fail is None or split is None:
            why.append("a field is absent or unreadable")
        else:
            if fail != 0:
                why.append("failures=%d" % fail)
            if chk == 0:
                why.append("checks=0: a zero that could not be otherwise is not clean")
            if chk != split[1] + split[3]:
                why.append("checks=%d != main %d + isr %d" % (chk, split[1], split[3]))
            if fail != split[0] + split[2]:
                why.append("failures=%d != main %d + isr %d" % (fail, split[0], split[2]))
    row("Policy A invariants clean", [inv], lambda: not why, inv_src + ("" if not why else " -- " + "; ".join(why)))
    info = []
    if sft is None:
        info.append("STREAMSELFTEST: MISSING (NOT passed)")
    else:
        info.append("STREAMSELFTEST (information): ok=%s converted=%s released=%s own_presents=%s own_repeats=%s sci_clean=%s" % tuple(
            sft.get(k, "<absent>") for k in ("ok", "converted", "released", "own_presents", "own_repeats", "sci_clean")))
    if inv is not None:
        info.append("STREAMINV consistent_at_end=%s (information)" % inv.get("consistent_at_end", "<absent>"))
    missing = [t for t, r in zip(STARTREC_TAGS, (su, st, sv, inv, sft)) if r is None]
    return {"rows": rows, "info": info, "missing": missing}


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
    for r in out["phase_capture"]:
        L.append("  tap gate, phase %s (V28PHC): taps=%d blocks_in=%d failed=%d wrong=%d" % (r["p"], r["taps"], r["blocks_in"], r["failed"], r["wrong"]))
    po = out["pre_origin"]
    if po:
        L.append("  INFORMATION, not a verdict: whole-session V28TAPS taps=%d blocks_in=%d, taps - blocks_in = %d (taps count from the first tap, blocks_in from the press origin: the pre-origin window)" % (
            po["taps"], po["blocks_in"], po["diff"]))
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
    if out.get("image") == "vehicle-0001":
        L.append("NO RECORD IN THIS IMAGE'S LOG, NOT READABLE HERE and NOT reported as passed (HARDWARE_TESTS.md V31.12): %s -- the vehicle keeps them as code; its log carries no STARTUP / STARTUPT / STARTUPV / STREAMINV record and no OGBPDISP2 sidecar" % "; ".join(NO_RECORD_IN_THIS_IMAGE_LOG))
    elif out.get("image") == "vehicle-0002":
        sr = out["startrec"]
        L.append("STARTUP PROFILE (vehicle-0002; the HARDWARE_TESTS.md V5.53.2 checklist rows, thresholds of V5.52.15-17; ROWS, not a session verdict -- that is the session's own pre-registration):")
        for t in sr["missing"]:
            L.append("  %s record: MISSING (NOT passed)" % t)
        for name, status, source in sr["rows"]:
            L.append("  [%s] %s: %s" % (status, name, source))
        for x in sr["info"]:
            L.append("  %s" % x)
        L.append("  Policy A's drops / supersessions / reorder / depth / latency: NO RECORD (no OGBPDISP2; not built). Never reported as passed.")
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
