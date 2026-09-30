#!/usr/bin/env python3
"""
tools/gbmode_read.py -- the reader of the first GB-mode session past PREUNMASK (Issue #146, Phase 7's E3;
HARDWARE_TESTS.md section V29, RUN 59). It reads ONE console log and prints, for each pre-registered question, WHICH RIVAL
READING the log matches. It decides nothing about the Operator's words, which are recorded verbatim and never computed on.

WHY A TOOL AND NOT A PARAGRAPH. The instrument must discriminate: a reading written in prose after the data is a reading the data
chose. Every rule below was fixed BEFORE the run, from the archive of the same image family (stream-0015: RUN 16, 17, 18 on a GBA
cartridge and RUN 23 with no Game Pak, every one of which reached the witness target with the same counts), and it is tested against
those four logs and against the four aborted GB boots (RUN 24, 27, 28, 29), so that it is known to say "GBA structure" where that is
true and "refused at PREUNMASK" where that is true, before it is asked about a run nobody has seen.

WHAT A READING IS NOT. "GBA structure" is a statement about BLOCK COUNTS, frame closure and the witness's structural qualification.
It says nothing about what the picture SHOWS: the frame rate of a Game Boy program equals the GBA's, so equal counts are expected even
if the picture is wrong. The picture is the Operator's observation and the offline sidecars; `episodes` is reported, never judged.

Usage:  tools/gbmode_read.py LOG [--build gbmode-0001] [--commit SHORT] [--json]
"""
import argparse
import json
import re
import sys

IDENT_BUILD = "gbmode-0001"
TEST_ID = "GBP-VIDEO-004"          # the embedded id of the stream family: the IMAGE's id, not the experiment's (GBP-GBMODE-001)

# ---- the rules, fixed before the run -------------------------------------------------------------------------------------
# From RUN 16 / 17 / 18 / 23 (captures/local/GBP-VIDEO-004_stream-0015-run{16,17,18,23}.log), each of which ended at the
# witness target with: closed 2404, complete 2378-2380, incomplete 12-13, quarantined 0, video 96109-96111 blocks (40.0 per closed
# frame), audio 164791-164793 blocks (1.71 per video block), WITQUAL qualified=1, STREAMWIT 2048/2048.
BLOCKS_PER_FRAME = (39.9, 40.1)
MAX_INCOMPLETE = 20
MIN_CLOSED = 300                   # too few frames to say anything about structure
AUDIO_PER_VIDEO = (1.60, 1.80)

# CONTROL bits: the byte the runtime expects after its transform write is 0x8e (orig 0x92); the tolerated bit is 0x01 (Issue #145)
TOLERATED = 0x01


def _h(s):
    return int(s, 16)


def _kv(line):
    return dict(re.findall(r"(\w+)=(\S+)", line))


def parse(text):
    """The records the readings need; every field is None when its record is absent."""
    r = {"header": {}, "ident": None, "control": None, "snaps": [], "pre": None, "counters": None, "vend": None, "src": None,
         "witqual": None, "witness": None, "structured": None, "restore": None, "restore_rec": None, "input": None,
         "tol": None, "end_dropped": None, "teardown": None}
    r["malformed"] = []
    seen_exp = False
    for line in text.split("\n"):
        try:
            seen_exp = _parse_line(r, line, seen_exp)
        except (KeyError, ValueError, IndexError):
            r["malformed"].append(line[:60])          # a record cut mid-line (an SD-truncated log) is a finding, never a crash
    return r


def _parse_line(r, line, seen_exp):
    if True:
        m = re.match(r"(test_id|build_id|commit)=(\S+)$", line)
        if m:
            r["header"][m.group(1)] = m.group(2)
            return seen_exp
        m = re.match(r"lines=(\d+) dropped=(\d+) truncated=(\d+)", line)
        if m:
            r["header"]["lines"], r["header"]["dropped"], r["header"]["truncated"] = (int(m.group(i)) for i in (1, 2, 3))
            return seen_exp
        m = re.match(r"# --- end --- dropped=(\d+)", line)
        if m:
            r["end_dropped"] = int(m.group(1))
            return seen_exp
        m = re.match(r"\d+ (\S+) ?(.*)$", line)
        if not m:
            return seen_exp
        kind, rest = m.group(1), m.group(2)
        if kind == "IDENT":
            r["ident"] = _kv(rest)
        elif kind == "CONTROL" and rest.startswith("semantic orig="):
            k = _kv(rest)
            r["control"] = {"orig": _h(k["orig"]), "exp": _h(k["exp"])}
        elif kind == "CTLW" and "tag=EXP" in rest:
            seen_exp = True
        elif kind == "RAW" and seen_exp:
            mm = re.match(r"(\S+) idx=4 .*?sem_vote=([0-9a-f]+) sem_b1f=([0-9a-f]+)", rest)
            if mm:
                r["snaps"].append((mm.group(1), _h(mm.group(2)), _h(mm.group(3))))
        elif kind == "PREUNMASK" and r["pre"] is None and rest.startswith("ok="):
            k = _kv(rest)
            r["pre"] = {"ok": int(k["ok"]), "reason": k["reason"], "control": _h(k["control"]), "raw": rest}
        elif kind == "COUNTERS":
            k = _kv(rest)
            a, b = k["video"].split("/")
            r["counters"] = {"unmasks": int(k["unmasks"]), "deliveries": int(k["deliveries"]), "acks": int(k["acks"]),
                             "rearms": int(k["rearms"]), "audio": int(k["audio"]), "video": int(a), "video_all": int(b),
                             "control_ok": int(k["control_ok"])}
        elif kind == "VSTATE" and rest.startswith("end "):
            k = _kv(rest)
            r["vend"] = {"status": k["status"], "class": k.get("class"), "reason": k["reason"], "stop": k["stop"],
                         "restore": k.get("restore"), "teardown": k.get("teardown"),
                         "power_cycle_required": int(k.get("power_cycle_required", "-1")), "errors": int(k.get("errors", "-1"))}
        elif kind == "STREAMSRC":
            k = _kv(rest)
            r["src"] = {n: int(k[n]) for n in ("closed", "complete", "incomplete", "quarantined", "anomaly", "published")}
        elif kind == "WITQUAL":
            k = _kv(rest)
            r["witqual"] = {"qualified": int(k["qualified"]), "qualify_frame": int(k["qualify_frame"])}
        elif kind == "STREAMWIT":
            k = _kv(rest)
            a, b = k["records"].split("/")
            r["witness"] = {"records": int(a), "of": int(b), "target_reached": int(k["target_reached"])}
        elif kind == "STRUCTURED":
            k = _kv(rest)
            r["structured"] = {"status": k["status"], "episodes": int(k["episodes"]), "stable": int(k["stable"])}
        elif kind == "CONTROL" and rest.startswith("restore "):
            k = _kv(rest)
            r["restore"] = {"orig": _h(k["semantic"]), "vote": _h(k["readback_vote"]), "b1f": _h(k["readback_b1f"]), "ok": int(k["ok"])}
        elif kind == "RESTORE" and rest.startswith("control_restore_ok="):
            k = _kv(rest)
            r["restore_rec"] = {"control_restore_ok": int(k["control_restore_ok"])}
        elif kind == "INPUT" and rest.startswith("selftest="):
            k = _kv(rest)
            r["input"] = {n: int(k[n]) for n in ("key_changes", "attempts", "completed", "failed", "first", "change", "refresh", "retry")}
            r["input"]["last_word"] = _h(k["last_word"])
        elif kind == "CONTROLTOL":
            k = _kv(rest)
            r["tol"] = {"n": int(k["n"]), "first_site": k["first_site"], "first_vote": _h(k["first_vote"]), "exp": _h(k["exp"]),
                        "restore": int(k["restore"])}
        elif kind == "TEARDOWNVSTATE":
            r["teardown"] = _kv(rest)
    return seen_exp


def read(r, build=IDENT_BUILD, commit=None):
    """{gates, q1..q4, keypad, facts}: every entry a short token plus the numbers it rests on."""
    out = {"gates": {}, "facts": {}}
    g = out["gates"]
    h = r["header"]
    dirty = str(h.get("commit", "")).endswith("-dirty")
    ok_id = (h.get("build_id") == build and h.get("test_id") == TEST_ID and not dirty and
             (commit is None or h.get("commit") == commit) and (r["ident"] or {}).get("build") == build)
    g["identity"] = ("PASS%s" % ("" if commit is not None else " (commit not compared: give --commit)") if ok_id else
                     "FAIL build=%s test=%s commit=%s%s" % (h.get("build_id"), h.get("test_id"), h.get("commit"),
                                                            " -- a -dirty build is never a hardware candidate (CLAUDE.md 18)" if dirty else ""))
    g["log_complete"] = ("PASS" if h.get("dropped") == 0 and h.get("truncated") == 0 and r["end_dropped"] == 0 and not r["malformed"] else
                         "FAIL dropped=%s truncated=%s end=%s malformed_records=%d%s" % (
                             h.get("dropped"), h.get("truncated"), r["end_dropped"], len(r["malformed"]),
                             " (no end marker: the log is cut)" if r["end_dropped"] is None else ""))
    c = r["control"]
    g["control_record"] = ("PASS" if c and c["orig"] == 0x92 and c["exp"] == 0x8E else "FAIL %s" % (c,))
    exp = c["exp"] if c else 0x8E
    # the GUARD WINDOW: every snapshot before the teardown (TDCTL is the read-back after the restore, FINAL the one after the stop)
    bit0_snaps = [(t, v) for (t, v, b) in r["snaps"] if v & TOLERATED and v == b and t not in ("TDCTL", "FINAL")]
    # the guard's own window: every snapshot BEFORE the teardown (TDCTL is the read-back after the restore, FINAL the one after the stop)
    strict_snaps = [(t, v) for (t, v, b) in r["snaps"] if (v ^ exp) & ~TOLERATED & 0xFF and t not in ("TDCTL", "FINAL")]
    # WHAT THIS GATE IS: a MEASURED fact (CONTROL bit 0x01 read set after the transform, GBP-HW-275) used as the run's own attestation that the
    # device reported GB/GBC media; what the bit MEANS stays inferred (U-GBP-036 open), and it does not distinguish DMG from CGB
    g["gb_media_attested"] = ("PASS first at %s" % bit0_snaps[0][0]) if bit0_snaps else \
        "FAIL bit 0x01 never read set before the teardown: the device did not report GB/GBC media; a session below is NOT evidence about GB mode"
    out["facts"]["bit0_snapshots"] = len(bit0_snaps)
    out["facts"]["strict_bit_snapshots_before_teardown"] = [(t, "%02x" % v) for (t, v) in strict_snaps]
    inp = r["input"]
    if inp is None:
        out["keypad"] = "UNKNOWN (no INPUT record)"
    elif inp["key_changes"] == 0 and inp["change"] == 0 and inp["last_word"] == 0 and inp["failed"] == 0:
        out["keypad"] = "IDLE_ONLY first=%d refresh=%d" % (inp["first"], inp["refresh"])
    else:
        out["keypad"] = "DEVIATION non-idle word(s): key_changes=%d change=%d last_word=%04x failed=%d" % (
            inp["key_changes"], inp["change"], inp["last_word"], inp["failed"])

    # ---- Q1: does the session get past PREUNMASK, and does the AV service cycle run --------------------------------------
    pre, ct, ve = r["pre"], r["counters"], r["vend"]
    if pre is None:
        q1 = "NOT_REACHED no PREUNMASK record"
    elif pre["ok"] == 0:
        diff = (pre["control"] ^ exp) & 0xFF
        if pre["reason"] == "control_changed" and diff == TOLERATED:
            q1 = "REFUSED_AT_PREUNMASK_POLICY_ABSENT control=%02x differs from %02x in bit 0x01 only: the image does not carry the Issue #145 policy" % (pre["control"], exp)
        elif pre["reason"] == "control_changed":
            q1 = "REFUSED_AT_PREUNMASK_STRICT_BIT control=%02x exp=%02x differ in 0x%02x -- A FINDING" % (pre["control"], exp, diff & ~TOLERATED & 0xFF)
        else:
            q1 = "REFUSED_AT_PREUNMASK_OTHER_CLAUSE reason=%s" % pre["reason"]
    elif ve is not None and ve["status"] == "anomaly_control_changed":
        q1 = "ABORT_AT_LATER_GUARD %s -- a strict bit changed after PREUNMASK: A FINDING" % ve["reason"]
    elif ct is None or ve is None:
        q1 = "UNDETERMINED missing COUNTERS or VSTATE end"
    elif ct["deliveries"] == 0 and ct["unmasks"] == 0:
        q1 = "OTHER_ENDING PREUNMASK passed and NO unmask happened: status=%s reason=%s stop=%s" % (ve["status"], ve["reason"], ve["stop"])
    elif ct["deliveries"] == 0:
        q1 = "NO_DELIVERY unmasks=%d status=%s stop=%s" % (ct["unmasks"], ve["status"], ve["stop"])
    elif ve["stop"] == "witness_target_reached":
        bad = []
        if ve["errors"] != 0:
            bad.append("errors=%d" % ve["errors"])
        if ct["acks"] != ct["deliveries"] or ct["rearms"] != ct["deliveries"]:
            bad.append("acks=%d rearms=%d against deliveries=%d" % (ct["acks"], ct["rearms"], ct["deliveries"]))
        if ct["control_ok"] != 1:
            bad.append("control_ok=%d" % ct["control_ok"])
        if ve["restore"] != "ok":
            bad.append("restore=%s" % ve["restore"])
        if ve["class"] not in ("ok", None):
            bad.append("status=%s class=%s" % (ve["status"], ve["class"]))
        q1 = ("SERVICE_RAN_TO_TARGET deliveries=%d acks=%d rearms=%d" % (ct["deliveries"], ct["acks"], ct["rearms"])) if not bad else \
            "SERVICE_RAN_TO_TARGET_WITH_ERRORS " + "; ".join(bad) + " -- not the clean reading"
    elif ve["class"] == "ok" or ve["stop"] in ("safety_budget", "delivery_cap", "frame_store_cap", "event_store_cap"):
        q1 = "SERVICE_RAN_ENDED_BY_%s status=%s deliveries=%d" % (ve["stop"].upper(), ve["status"], ct["deliveries"])
    else:
        q1 = "OTHER_ENDING status=%s reason=%s stop=%s deliveries=%d" % (ve["status"], ve["reason"], ve["stop"], ct["deliveries"])
    out["q1_service"] = q1
    ran = ct is not None and ct["deliveries"] > 0 and pre is not None and pre["ok"] == 1

    # ---- Q2: VIDEO structure, against the family's GBA structure --------------------------------------------------------
    src, wq, wt = r["src"], r["witqual"], r["witness"]
    if not ran:
        q2 = "NOT_EVALUABLE the service cycle did not run"
    elif ct["video"] == 0:
        q2 = "NO_VIDEO deliveries=%d but zero VIDEO blocks" % ct["deliveries"]
    else:
        why = []
        closed = src["closed"] if src else 0
        bpf = ct["video"] / closed if closed else 0.0
        if closed < MIN_CLOSED:
            why.append("closed frames %d < %d" % (closed, MIN_CLOSED))
        if closed and not (BLOCKS_PER_FRAME[0] <= bpf <= BLOCKS_PER_FRAME[1]):
            why.append("%.2f VIDEO blocks per closed frame, outside %.1f-%.1f" % (bpf, *BLOCKS_PER_FRAME))
        if src and (src["incomplete"] > MAX_INCOMPLETE or src["quarantined"] != 0 or src["anomaly"] > MAX_INCOMPLETE):
            why.append("incomplete=%d quarantined=%d anomaly=%d" % (src["incomplete"], src["quarantined"], src["anomaly"]))
        if not (wq and wq["qualified"] == 1):
            why.append("the structural witness never qualified")
        q2 = ("GBA_STRUCTURE closed=%d complete=%d incomplete=%d blocks/frame=%.2f qualified=1 (closure only: says nothing about the picture)" % (
            closed, src["complete"], src["incomplete"], bpf)) if not why else ("DIFFERENT_STRUCTURE " + "; ".join(why))
        if wt:
            out["facts"]["witness_records"] = "%d/%d target_reached=%d" % (wt["records"], wt["of"], wt["target_reached"])
    out["q2_video"] = q2
    if r["structured"]:
        out["facts"]["episodes"] = r["structured"]["episodes"]        # reported, never judged: a change in the picture, not its correctness

    # ---- Q3: AUDIO blocks ------------------------------------------------------------------------------------------------
    if not ran:
        q3 = "NOT_EVALUABLE the service cycle did not run"
    elif ct["audio"] == 0:
        q3 = "NO_AUDIO zero AUDIO blocks (VIDEO blocks %d)" % ct["video"]
    elif ct["video"] == 0:
        q3 = "AUDIO_WITHOUT_VIDEO audio=%d" % ct["audio"]
    else:
        ratio = ct["audio"] / ct["video"]
        q3 = ("AUDIO_COUNT_AS_GBA audio=%d ratio=%.3f" % (ct["audio"], ratio)) if AUDIO_PER_VIDEO[0] <= ratio <= AUDIO_PER_VIDEO[1] \
            else "AUDIO_COUNT_DIFFERENT audio=%d ratio=%.3f outside %.2f-%.2f" % (ct["audio"], ratio, *AUDIO_PER_VIDEO)
    out["q3_audio"] = q3

    # ---- Q4: the restore read-back, and the record of the tolerance -------------------------------------------------------
    rs, tol = r["restore"], r["tol"]
    if rs is None:
        q4 = "NOT_REACHED no CONTROL restore record"
    else:
        orig = rs["orig"]
        if rs["vote"] == orig | TOLERATED and rs["b1f"] == rs["vote"]:
            q4 = "RESTORE_HOLDS_BIT read-back %02x against original %02x ok=%d" % (rs["vote"], orig, rs["ok"])
            if rs["ok"] != 1:
                q4 += " -- ok=0: the restore check REFUSED a read-back the policy tolerates (expected only in an image without the policy) -- A FINDING here"
        elif rs["vote"] == orig:
            q4 = "RESTORE_CLEARS_BIT read-back %02x = original ok=%d" % (rs["vote"], rs["ok"])
            if rs["ok"] != 1:
                q4 += " -- ok=0 on an exact read-back -- A FINDING"
        else:
            q4 = "RESTORE_OTHER read-back %02x b1f=%02x against original %02x ok=%d -- A FINDING" % (rs["vote"], rs["b1f"], orig, rs["ok"])
    out["q4_restore"] = q4
    if bit0_snaps and tol is None and pre is not None and pre["ok"] == 1:
        out["tolerance_record"] = "ABSENT although bit 0x01 was read and PREUNMASK passed: the record failed -- A FINDING"
    elif tol is not None:
        if rs is not None and tol["restore"] == 1 and rs["vote"] == rs["orig"]:
            out["facts"]["inconsistent"] = "CONTROLTOL says the restore read-back was tolerated but it read exactly the original"
        out["tolerance_record"] = "CONTROLTOL n=%d first_site=%s first_vote=%02x exp=%02x restore=%d" % (
            tol["n"], tol["first_site"], tol["first_vote"], tol["exp"], tol["restore"])
    else:
        out["tolerance_record"] = "none (no comparison found CONTROL differing in bit 0x01 alone)"
    if ve:
        out["facts"]["vstate_end"] = "status=%s stop=%s teardown=%s power_cycle_required=%d" % (ve["status"], ve["stop"], ve["teardown"], ve["power_cycle_required"])
    if ct:
        out["facts"]["counters"] = "unmasks=%d deliveries=%d video=%d audio=%d control_ok=%d" % (ct["unmasks"], ct["deliveries"], ct["video"], ct["audio"], ct["control_ok"])
    return out


def render(out):
    lines = ["GBMODE READ (GBP-GBMODE-001)"]
    for k, v in out["gates"].items():
        lines.append("  GATE %-18s %s" % (k, v))
    for k in ("q1_service", "q2_video", "q3_audio", "q4_restore"):
        lines.append("  %-13s %s" % (k.upper(), out[k]))
    lines.append("  %-13s %s" % ("TOLERANCE", out["tolerance_record"]))
    lines.append("  %-13s %s" % ("KEYPAD", out["keypad"]))
    for k, v in out["facts"].items():
        lines.append("  fact %-30s %s" % (k, v))
    lines.append("  NOT COMPUTED HERE: what the Operator saw on the TV; his words are recorded verbatim, before any figure is shown to him.")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("log")
    ap.add_argument("--build", default=IDENT_BUILD)
    ap.add_argument("--commit", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    with open(a.log, encoding="utf-8", errors="replace") as f:
        out = read(parse(f.read()), a.build, a.commit)
    print(json.dumps(out, indent=1) if a.json else render(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
