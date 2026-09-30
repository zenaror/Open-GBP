#!/usr/bin/env python3
"""tools/gbmode_e4_read.py -- the reader of PHASE 7's E4, the L / R stretch in GB mode (GitHub Issue #151; HARDWARE_TESTS.md V30).

    python3 tools/gbmode_e4_read.py <log> <idxcap.bin> [--full <full.bin>] --build gbmode-0001 --commit 4d6fe06 [--json]

FROZEN WITH THE PRE-REGISTRATION, before any data. It joins three records the UNCHANGED gbmode-0001 image already writes on one time base (OGBPIDXCAP1 / OGBPDISP2 / OGBPVI1 use the
transport's ticks64, and so does the KEY record):

  the KEY records     (log)      one line per change of the KEYPAD word, with t_done (the instant the write returned): the word in force is known at every instant;
  the strip records   (idxcap)   for EVERY frame of the witness window, 40 blocks x 54 words of local row 0, x = 1..54 (rows y = 4b);
  the samples         (full)     8 complete frames at witness frame 256 i (optional; described, never a verdict).

WHAT IT DECIDES, AND NOTHING ELSE. Whether the delivered frames carry picture words OUTSIDE the baseline rectangle x 40..199, y 8..151 (RUN 59, HARDWARE_TESTS V29.13, GBP-HW-379), per
KEYPAD state, on the frames that can show it. It does not say what a television showed; it does not say why; it says nothing about a frame that is dark where the border would be.

  LEGIBLE   a frame whose strip words inside the baseline rectangle (blocks 2..37 x x 40..54: 36 x 15 = 540 words) are at least 90 % non-black. Only a legible frame can show a change.
  LEAK      the strip words OUTSIDE the rectangle (x 1..39 in all 40 blocks, and x 40..54 in blocks 0, 1, 38, 39: 1 620 words) that are non-black. RUN 59: 0 in all 2 048 frames.
  cell      (the keys held, the completed presses so far) at the frame's time; a frame within 30 frames (0.5 s) of a change of the L / R bits is a TRANSITION frame and is excluded from
            the cells (the latency from the write to the delivered frame is not measured); the aligned series is printed apart, descriptively.
  STRETCHED / NOT_STRETCHED / MIXED / INSUFFICIENT   a cell with at least 40 legible frames of which >= 90 % / <= 2 % / else leak; fewer than 40: INSUFFICIENT. A frame with a leak
            of 1 % .. 25 % of the 1 620 words is PARTIAL (counted, never classified).

The rival readings are IMPLEMENTED here as state machines over the same KEY timeline (NOTHING, L_MOMENTARY, R_MOMENTARY, EITHER_MOMENTARY, L_LATCH, R_LATCH, L_TOGGLE, R_TOGGLE,
BOTH_TOGGLE) and the reader prints which of them the evaluable cells are CONSISTENT with. Several can remain (that is stated, never resolved by picking one). NOTHING is also what "the word
never reached the AGB in GB mode" predicts: the write returns ok either way, and the AGB's keypad window is write-only, so NO reading of this image separates the two (V30).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gbmode_read  # noqa: E402
import vidxcap  # noqa: E402

FRAME_HZ = 59.7275
L_BIT, R_BIT = 0x0100, 0x0200
LEGIBLE_MIN = 0.90
LEAK_WORDS = 1620
INBOX_WORDS = 540
LEAK_STRETCHED = 0.25          # a frame is a LEAK frame at or above this share of the 1 620 outside words
LEAK_PARTIAL = 0.01            # between this and the line above: PARTIAL
MARGIN_FRAMES = 30
MIN_FRAMES = 40
CELL_STRETCHED, CELL_NOT = 0.90, 0.02
KEY_RE = re.compile(r"KEY n=(\d+) act=(\w+) keys=([0-9a-f]{4}) word=([0-9a-f]{4}) t_poll=([0-9a-f]+) t_attempt=([0-9a-f]+) t_done=([0-9a-f]+) xfer=(\d+) rc=(\w+)")
MODELS = ("NOTHING", "L_MOMENTARY", "R_MOMENTARY", "EITHER_MOMENTARY", "L_LATCH", "R_LATCH", "L_TOGGLE", "R_TOGGLE", "BOTH_TOGGLE")


def parse_keys(text):
    out = []
    for m in KEY_RE.finditer(text):
        out.append({"n": int(m.group(1)), "act": m.group(2), "keys": int(m.group(3), 16), "word": int(m.group(4), 16), "t_done": int(m.group(7), 16), "rc": m.group(9)})
    return out


def transitions(keys):
    """The ordered changes of the L / R bits (rc ok only). Each: (t, l_now, r_now)."""
    tr, l, r = [], 0, 0
    for k in sorted((k for k in keys if k["rc"] == "ok"), key=lambda k: k["t_done"]):
        nl, nr = 1 if k["word"] & L_BIT else 0, 1 if k["word"] & R_BIT else 0
        if (nl, nr) != (l, r):
            tr.append((k["t_done"], nl, nr))
            l, r = nl, nr
    return tr


def presses(tr):
    """Down edges and completed presses in order: [(key, t_down, t_up or None)]."""
    out, l, r, open_ = [], 0, 0, {}
    for t, nl, nr in tr:
        for key, was, now in (("L", l, nl), ("R", r, nr)):
            if now and not was:
                open_[key] = len(out)
                out.append([key, t, None])
            if was and not now and key in open_:
                out[open_.pop(key)][2] = t
        l, r = nl, nr
    return [tuple(p) for p in out]


def other_keys(keys):
    """Any word bit other than L / R set in a written word: a recorded deviation."""
    return sorted({k["word"] & ~(L_BIT | R_BIT) for k in keys if k["rc"] == "ok" and k["word"] & ~(L_BIT | R_BIT)})


def frame_stats(witness):
    inbox = leak = 0
    for b, row in enumerate(witness):
        edge = b in (0, 1, 38, 39)
        for i, v in enumerate(row):
            x = 1 + i
            nz = (v & 0x7FFF) != 0
            if x >= 40 and not edge:
                inbox += nz
            elif nz:
                leak += 1
    return inbox, leak


def cell_of(t, tr, ps):
    """(held, completed) at t: held is '-', 'L', 'R' or 'LR'; completed is the sequence of presses finished before t."""
    l = r = 0
    for tt, nl, nr in tr:
        if tt <= t:
            l, r = nl, nr
    held = ("L" if l else "") + ("R" if r else "") or "-"
    done = "".join(k for k, _d, u in ps if u is not None and u <= t)
    return "%s|after:%s" % (held, done)


def near_transition(t, tr, hz):
    return any(abs(t - tt) < MARGIN_FRAMES / FRAME_HZ * hz for tt, _l, _r in tr)


def classify_frames(frames, tr, ps, hz):
    """Per frame: legible, leak fraction, cell, transition flag."""
    out = []
    for f in frames:
        inbox, leak = frame_stats(f["witness"])
        t = (f["t0"] + f["t1"]) // 2
        out.append({"frame_index": f["frame_index"], "t": t, "legible": inbox / float(INBOX_WORDS) >= LEGIBLE_MIN, "leak": leak / float(LEAK_WORDS),
                    "cell": cell_of(t, tr, ps), "transition": near_transition(t, tr, hz)})
    return out


def cells_of(cf):
    cells = {}
    for c in cf:
        if not c["legible"] or c["transition"]:
            continue
        d = cells.setdefault(c["cell"], {"n": 0, "leak": 0, "partial": 0})
        d["n"] += 1
        if c["leak"] >= LEAK_STRETCHED:
            d["leak"] += 1
        elif c["leak"] >= LEAK_PARTIAL:
            d["partial"] += 1
    for d in cells.values():
        if d["n"] < MIN_FRAMES:
            d["verdict"] = "INSUFFICIENT"
        elif d["leak"] >= CELL_STRETCHED * d["n"]:
            d["verdict"] = "STRETCHED"
        elif d["leak"] <= CELL_NOT * d["n"] and d["partial"] <= CELL_NOT * d["n"]:
            d["verdict"] = "NOT_STRETCHED"
        else:
            d["verdict"] = "MIXED"
    return cells


def model_state(model, tr, t):
    """The stretch state each rival reading predicts at time t, from the same KEY timeline."""
    l = r = 0
    latch = False
    toggles = 0
    for tt, nl, nr in tr:
        if tt > t:
            break
        if model == "L_LATCH" and nl and not l:
            latch = True
        if model == "R_LATCH" and nr and not r:
            latch = True
        if model == "L_TOGGLE" and nl and not l:
            toggles += 1
        if model == "R_TOGGLE" and nr and not r:
            toggles += 1
        if model == "BOTH_TOGGLE" and ((nl and not l) or (nr and not r)):
            toggles += 1
        l, r = nl, nr
    if model == "NOTHING":
        return False
    if model == "L_MOMENTARY":
        return bool(l)
    if model == "R_MOMENTARY":
        return bool(r)
    if model == "EITHER_MOMENTARY":
        return bool(l or r)
    if model in ("L_LATCH", "R_LATCH"):
        return latch
    return bool(toggles % 2)


def consistent_models(cf, tr):
    """Which rival readings agree with every evaluable cell (STRETCHED or NOT_STRETCHED); the cell's frames are compared one by one."""
    cells = cells_of(cf)
    ev = {k for k, d in cells.items() if d["verdict"] in ("STRETCHED", "NOT_STRETCHED")}
    res = []
    for m in MODELS:
        ok = True
        for c in cf:
            if not c["legible"] or c["transition"] or c["cell"] not in ev:
                continue
            want = cells[c["cell"]]["verdict"] == "STRETCHED"
            if model_state(m, tr, c["t"]) != want:
                ok = False
                break
        if ok:
            res.append(m)
    return res, cells


def overall(gates_ok, keys, ps, cells):
    """The registered ordering: INADMISSIBLE, NO_LR_WORD_SENT, CHANGED, INCONCLUSIVE_NOT_LEGIBLE, NOT_CHANGED_REACH_NOT_SHOWN, else PARTIAL."""
    sent = {k for k, _d, _u in ps}
    if not gates_ok:
        return "INADMISSIBLE"
    if not sent:
        return "NO_LR_WORD_SENT"
    pressed = {k: d["verdict"] for k, d in cells.items() if k != "-|after:" and d["verdict"] != "INSUFFICIENT"}
    if any(v == "STRETCHED" for v in pressed.values()):
        return "CHANGED"
    if not pressed:
        return "INCONCLUSIVE_NOT_LEGIBLE"
    held_evaluated = {c for c in "LR" for k in pressed if c in k.split("|")[0]}
    if all(v == "NOT_STRETCHED" for v in pressed.values()) and sent <= held_evaluated:
        return "NOT_CHANGED_REACH_NOT_SHOWN"
    return "PARTIAL"


def read(log_text, idx_info, build, commit, full_info=None):
    r = gbmode_read.parse(log_text)
    g = gbmode_read.read(r, build, commit)
    gates = g["gates"]
    gates_ok = all(v.startswith("PASS") for v in gates.values())
    keys = parse_keys(log_text)
    tr = transitions(keys)
    ps = presses(tr)
    hz = idx_info["tb_hz"]
    frames = [{"frame_index": rec["frame_index"], "t0": rec["t_first_block"], "t1": rec["t_last_block"], "witness": rec["witness"]} for rec in idx_info["records"]]
    cf = classify_frames(frames, tr, ps, hz)
    models, cells = consistent_models(cf, tr)
    out = {"gates": gates, "gates_ok": gates_ok, "keys_n": len(keys), "keys_failed": sum(1 for k in keys if k["rc"] != "ok"), "other_keys": other_keys(keys),
           "presses": [{"key": k, "t_down": d, "t_up": u} for k, d, u in ps], "frames": len(cf), "legible": sum(1 for c in cf if c["legible"]),
           "leak_frames": sum(1 for c in cf if c["leak"] >= LEAK_STRETCHED), "partial_leak_frames": sum(1 for c in cf if LEAK_PARTIAL <= c["leak"] < LEAK_STRETCHED),
           "transition_frames": sum(1 for c in cf if c["transition"] and c["legible"]), "cells": cells, "consistent_models": models,
           "verdict": overall(gates_ok, keys, ps, cells)}
    if full_info is not None:
        import gbmode_picture
        smp = []
        for rec in full_info["records"]:
            a = gbmode_picture.analyse_frame(rec["raw"])
            smp.append({"sample": rec["sample_index"], "frame_index": rec["frame_index"], "cell": cell_of(rec["t_take"], tr, ps), "bbox": a["bbox"], "size": a["size"],
                        "outside_is_border": a["outside_is_border"]})
        out["samples"] = smp
    return out


def render(o):
    L = ["GBMODE E4 READ (GitHub Issue #151)"]
    for k, v in o["gates"].items():
        L.append("  GATE %-20s %s" % (k, v))
    L.append("  KEY records %d (failed writes %d); L / R presses: %s" % (o["keys_n"], o["keys_failed"],
             ", ".join("%s down %x up %s" % (p["key"], p["t_down"], ("%x" % p["t_up"]) if p["t_up"] else "never") for p in o["presses"]) or "none"))
    L.append("  other KEYPAD bits written: %s" % (", ".join("0x%04x" % b for b in o["other_keys"]) or "none"))
    L.append("  frames %d, legible %d, leak frames %d, partial-leak frames %d, legible transition frames excluded %d" % (o["frames"], o["legible"], o["leak_frames"], o["partial_leak_frames"], o["transition_frames"]))
    for k in sorted(o["cells"]):
        d = o["cells"][k]
        L.append("  CELL %-16s legible frames %4d  leak %4d  partial %3d   %s" % (k, d["n"], d["leak"], d["partial"], d["verdict"]))
    L.append("  CONSISTENT rival readings: %s" % (", ".join(o["consistent_models"]) or "none of them"))
    for s in o.get("samples", []):
        L.append("  SAMPLE %d frame %d cell %-14s box %s size %s outside-is-border %s" % (s["sample"], s["frame_index"], s["cell"], s["bbox"], s["size"], s["outside_is_border"]))
    L.append("  VERDICT %s" % o["verdict"])
    L.append("  NOT COMPUTED HERE: what the Operator saw; whether a NOT_STRETCHED cell means 'no stretch' or 'the word never reached the AGB in GB mode' (the two are not separable by this image).")
    return "\n".join(L)


def main(argv):
    a = argv[1:]
    js = "--json" in a
    a = [x for x in a if x != "--json"]
    opts = {}
    for k in ("--full", "--build", "--commit"):
        if k in a:
            i = a.index(k)
            opts[k] = a[i + 1]
            del a[i:i + 2]
    if len(a) != 2 or "--build" not in opts or "--commit" not in opts:
        print(__doc__.split("\n\n")[0])
        return 2
    with open(a[0], encoding="utf-8", errors="replace") as f:
        text = f.read()
    idx = vidxcap.load(a[1])
    full = None
    if "--full" in opts:
        import vfull
        full = vfull.load(opts["--full"])
    o = read(text, idx, opts["--build"], opts["--commit"], full)
    print(json.dumps(o, indent=1, default=list) if js else render(o))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
