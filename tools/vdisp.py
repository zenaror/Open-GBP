"""
tools/vdisp.py — the OGBPDISP1 downstream analyzer (HARDWARE_TESTS §V5.46).

DELIBERATELY SEPARATE FROM tools/vindex.py. That one is the authority on the
SOURCE layer and its verdict vocabulary is frozen; this one describes what
happened to a frame AFTERWARDS, which is a different population with different
terminals. Reusing OGBPIDX1's labels for a display decision would make two
unrelated questions look like one.

WHAT IT MAY AND MAY NOT CLAIM
  MAY    which stages each source frame reached, when, and which exact branch
         ended it; the distribution of latencies between stages; the interval
         and phase of presentation decisions
  MAY NOT anything about source-frame ID continuity. That is vindex's answer and
         it needs the witness. Given an OGBPIDXCAP1 file explicitly, this tool
         will JOIN on the generic frame index -- it still does not re-derive the
         source verdict.

A "presentation decision" here is one submit_ready() call that got past the
token gate. It is NOT a retrace: this runtime has no VI-driven display loop, so
presents are source-driven and an opportunity cannot precede its own frame.
"""
import binascii
import struct
import sys

MAGIC, END = b"OGBPDISP", b"OGBPDEND"
VERSION, HEADER_SIZE, FOOTER_SIZE = 1, 0x100, 12
LIFE_SIZE, EVENT_SIZE = 96, 40

F_INTACT, F_LIFE_OVERFLOW, F_EVENT_OVERFLOW = 0x01, 0x02, 0x04
F_DRAWDONE_UNMATCHED, F_WINDOW_OPENED = 0x08, 0x10
F_ALL = 0x1F
FLAG_NAMES = [(F_INTACT, "intact"), (F_LIFE_OVERFLOW, "life_overflow"),
              (F_EVENT_OVERFLOW, "event_overflow"),
              (F_DRAWDONE_UNMATCHED, "drawdone_unmatched"),
              (F_WINDOW_OPENED, "window_opened")]

KEY_NONE = 0xFFFFFFFF

DISPOSITION = {0: "OPEN", 1: "SELECTED_NEW", 2: "HOLD_PREVIOUS",
               3: "SLOT_OVERRUN", 4: "ABANDONED_NO_RAW"}
REASON = {0: "NONE", 1: "XFB_BUSY", 2: "XFB_SHUTDOWN"}
LF = [(0x01, "IN_WINDOW"), (0x02, "SELFTEST"), (0x04, "CONVERTED"),
      (0x08, "SUBMITTED"), (0x10, "DRAWDONE"), (0x20, "DECIDED")]


class DispError(ValueError):
    pass


def _id(buf):
    i = buf.find(b"\0")
    if i < 0:
        raise DispError("an identity field has no terminator")
    if any(buf[i:]):
        raise DispError("an identity field has bytes after its terminator")
    return buf[:i].decode("ascii", "replace")


def parse(data: bytes) -> dict:
    """Strict. Raises DispError with a specific reason, never a generic one."""
    if len(data) < HEADER_SIZE + FOOTER_SIZE:
        raise DispError("shorter than a header plus a footer")
    if data[:8] != MAGIC:
        raise DispError("magic is not %r" % MAGIC)
    version, header_size = struct.unpack_from(">HH", data, 0x08)
    if version != VERSION:
        raise DispError("unsupported version %d" % version)
    if header_size != HEADER_SIZE:
        raise DispError("header size %d is not 0x%X" % (header_size, HEADER_SIZE))
    header_crc32 = struct.unpack_from(">I", data, HEADER_SIZE - 4)[0]
    if header_crc32 != binascii.crc32(data[:HEADER_SIZE - 4]) & 0xFFFFFFFF:
        raise DispError("header CRC-32 mismatch")

    i = {"version": version, "header_size": header_size, "header_crc32": header_crc32}
    (i["flags"], i["life_record_size"], i["event_record_size"], i["life_cap"],
     i["life_n"], i["event_cap"], i["event_n"], i["life_overflow"],
     i["event_overflow"], i["drawdone_unmatched"], i["decisions"], i["tb_hz"],
     i["tex_slots"], i["xfb_slots"], i["window_first_frame"], i["off_life"],
     i["off_events"], i["off_footer"], i["life_crc32"],
     i["event_crc32"]) = struct.unpack_from(">20I", data, 0x0C)
    i["total_size"] = struct.unpack_from(">Q", data, 0x60)[0]
    if i["life_record_size"] != LIFE_SIZE or i["event_record_size"] != EVENT_SIZE:
        raise DispError("record sizes are not the frozen ones")
    if i["flags"] & ~F_ALL:
        raise DispError("unknown flag bits set: 0x%04x" % i["flags"])
    if i["life_n"] > i["life_cap"] or i["event_n"] > i["event_cap"]:
        raise DispError("a count exceeds its capacity")
    body = i["life_n"] * LIFE_SIZE + i["event_n"] * EVENT_SIZE
    if i["off_life"] != HEADER_SIZE or \
       i["off_events"] != i["off_life"] + i["life_n"] * LIFE_SIZE or \
       i["off_footer"] != HEADER_SIZE + body or \
       i["total_size"] != i["off_footer"] + FOOTER_SIZE or len(data) != i["total_size"]:
        raise DispError("the sections do not fit the file")
    if any(data[0xE8:HEADER_SIZE - 4]):
        raise DispError("reserved header bytes are not zero")
    for name, off in (("test_id", 0x68), ("build_id", 0x88), ("app", 0xA8), ("commit", 0xC8)):
        i[name] = _id(data[off:off + 32])
    if data[i["off_footer"]:i["off_footer"] + 8] != END:
        raise DispError("footer magic is not %r" % END)
    i["total_crc32"] = struct.unpack_from(">I", data, i["off_footer"] + 8)[0]
    if i["total_crc32"] != binascii.crc32(data[:i["off_footer"]]) & 0xFFFFFFFF:
        raise DispError("global CRC-32 mismatch")
    if i["life_crc32"] != binascii.crc32(
            data[i["off_life"]:i["off_life"] + i["life_n"] * LIFE_SIZE]) & 0xFFFFFFFF:
        raise DispError("lifecycle section CRC-32 mismatch")
    if i["event_crc32"] != binascii.crc32(
            data[i["off_events"]:i["off_events"] + i["event_n"] * EVENT_SIZE]) & 0xFFFFFFFF:
        raise DispError("event section CRC-32 mismatch")

    i["life"] = []
    for k in range(i["life_n"]):
        o = i["off_life"] + k * LIFE_SIZE
        fi, seq = struct.unpack_from(">II", data, o)
        times = struct.unpack_from(">7Q", data, o + 0x08)
        rt_take, rt_dec, cticks, refus = struct.unpack_from(">4I", data, o + 0x40)
        slot, tex, disp, reason = struct.unpack_from(">4H", data, o + 0x50)
        src_flags, life_flags = struct.unpack_from(">II", data, o + 0x58)
        if disp not in DISPOSITION:
            raise DispError("life %d: unknown disposition %d" % (k, disp))
        if reason not in REASON:
            raise DispError("life %d: unknown reason %d" % (k, reason))
        i["life"].append({
            "i": k, "frame_index": fi, "seq": seq,
            "t_close": times[0], "t_take": times[1], "t_convert_first": times[2],
            "t_convert_done": times[3], "t_submit": times[4], "t_drawdone": times[5],
            "t_decision": times[6], "retrace_take": rt_take, "retrace_decision": rt_dec,
            "convert_ticks": cticks, "submit_refusals": refus,
            "slot": slot, "tex": tex, "disposition": disp, "reason": reason,
            "src_flags": src_flags, "life_flags": life_flags,
        })
    i["events"] = []
    for k in range(i["event_n"]):
        o = i["off_events"] + k * EVENT_SIZE
        t = struct.unpack_from(">Q", data, o)[0]
        ordinal, retrace, fi, prev = struct.unpack_from(">4I", data, o + 0x08)
        cur, pend, tgt = struct.unpack_from(">3h", data, o + 0x18)
        tex, dec, reason, ts0, ts1, infl = struct.unpack_from(">6B", data, o + 0x1E)
        newest = struct.unpack_from(">I", data, o + 0x24)[0]
        if dec not in DISPOSITION or reason not in REASON:
            raise DispError("event %d: unknown decision/reason" % k)
        i["events"].append({
            "i": k, "t": t, "ordinal": ordinal, "retrace": retrace,
            "frame_index": fi, "prev_index": prev, "xfb_current": cur,
            "xfb_pending": pend, "xfb_target": tgt, "tex": tex,
            "decision": dec, "reason": reason, "tex_state": (ts0, ts1),
            "inflight": infl, "newest_source": newest,
        })
    return i


def load(path): 
    with open(path, "rb") as f:
        return parse(f.read())


def flag_names(flags):
    return [n for b, n in FLAG_NAMES if flags & b] or ["-"]


def life_flag_names(flags):
    return [n for b, n in LF if flags & b] or ["-"]


def usable(info):
    """Whether this trace may support a DECISIVE disposition claim. Separate
    from `parse` on purpose: a file can be well formed and still be the wrong
    evidence."""
    why = []
    if info["life_overflow"]:
        why.append("the lifecycle array overflowed (%d lost)" % info["life_overflow"])
    if info["event_overflow"]:
        why.append("the event array overflowed (%d lost)" % info["event_overflow"])
    if info["drawdone_unmatched"]:
        why.append("%d draw-done tokens matched no lifecycle" % info["drawdone_unmatched"])
    if info["decisions"] != info["event_n"]:
        why.append("decisions %d but only %d events stored" % (info["decisions"], info["event_n"]))
    if not (info["flags"] & F_WINDOW_OPENED):
        why.append("the qualified source window never opened")
    return {"usable_for_disposition_claim": not why, "reasons": why}


def scientific(info):
    """Lifecycles inside the qualified source window, self-test excluded. The
    self-test is excluded by its FLAG, not by its position."""
    return [r for r in info["life"]
            if (r["life_flags"] & 0x01) and not (r["life_flags"] & 0x02)]


def _q(vals):
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    return {"n": n, "min": s[0], "p50": s[n // 2],
            "p90": s[min(n - 1, (n * 9) // 10)], "max": s[-1],
            "mean": sum(s) // n}


def latencies(info, rows=None):
    """Stage-to-stage costs, in time-base ticks, over rows that reached both
    ends of each pair. A stage that never happened carries 0 and is skipped, so
    a distribution never silently includes an invented interval."""
    rows = scientific(info) if rows is None else rows
    pairs = (("close_to_take", "t_close", "t_take"),
             ("take_to_convert_first", "t_take", "t_convert_first"),
             ("convert_first_to_done", "t_convert_first", "t_convert_done"),
             ("convert_done_to_submit", "t_convert_done", "t_submit"),
             ("submit_to_drawdone", "t_submit", "t_drawdone"),
             ("drawdone_to_decision", "t_drawdone", "t_decision"),
             ("close_to_decision", "t_close", "t_decision"))
    out = {}
    for name, a, b in pairs:
        out[name] = _q([r[b] - r[a] for r in rows if r[a] and r[b] and r[b] >= r[a]])
    return out


def decision_intervals(info):
    """Interval between consecutive presentation DECISIONS, and the retrace
    ordinals they fell on."""
    ev = [e for e in info["events"] if e["frame_index"] != KEY_NONE]
    dt = [b["t"] - a["t"] for a, b in zip(ev, ev[1:]) if b["t"] >= a["t"]]
    dr = [b["retrace"] - a["retrace"] for a, b in zip(ev, ev[1:])]
    return {"interval_ticks": _q(dt), "retrace_delta": _q(dr),
            "retrace_delta_hist": _hist(dr)}


def _hist(vals):
    h = {}
    for v in vals:
        h[v] = h.get(v, 0) + 1
    return dict(sorted(h.items()))


def holds(info):
    """One compact causal row per HOLD, which is the whole point of the trace.
    Normal frames are not dumped."""
    out = []
    for e in info["events"]:
        if e["decision"] != 2:
            continue
        r = next((x for x in info["life"] if x["frame_index"] == e["frame_index"]
                  and x["t_decision"] == e["t"]), None)
        out.append({
            "ordinal": e["ordinal"], "frame_index": e["frame_index"],
            "prev_index": e["prev_index"], "reason": REASON[e["reason"]],
            "xfb_current": e["xfb_current"], "xfb_pending": e["xfb_pending"],
            "retrace": e["retrace"], "t": e["t"],
            "tex_state": e["tex_state"], "inflight": e["inflight"],
            "newest_source": e["newest_source"],
            # THE DISCRIMINATOR. A hold with a newer frame already waiting is
            # "the pipeline was behind"; a hold with an empty mailbox is "the
            # framebuffer was busy and nothing was lost by waiting".
            "newer_frame_waiting": (e["newest_source"] != KEY_NONE
                                    and e["newest_source"] > e["frame_index"]),
            "convert_ticks": r["convert_ticks"] if r else None,
            "submit_refusals": r["submit_refusals"] if r else None,
            "was_drawn": bool(r and (r["life_flags"] & 0x10)),
        })
    return out


def join_witness(info, idxcap_path):
    """Joins the SOURCE witness to the trace on the generic frame index.

    It does NOT re-derive the source verdict; run tools/vindex.py for that. What
    it answers is coverage: which scientifically retained source frames have a
    downstream lifecycle, and what became of them."""
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import vidxcap
    cap = vidxcap.load(idxcap_path)
    src = {r["frame_index"] for r in cap["records"]}
    by_key = {r["frame_index"]: r for r in info["life"] if r["frame_index"] != KEY_NONE}
    joined, missing = [], []
    for k in sorted(src):
        r = by_key.get(k)
        (joined if r else missing).append(k)
    hist = {}
    for k in joined:
        d = DISPOSITION[by_key[k]["disposition"]]
        hist[d] = hist.get(d, 0) + 1
    return {"source_records": len(src), "joined": len(joined),
            "not_in_trace": len(missing),
            "not_in_trace_first": missing[:8],
            "disposition": dict(sorted(hist.items())),
            "capture_build": cap["build_id"]}


def interior_vs_edge(info):
    """A frame that never reached a terminal is a RESIDUAL. It is only a finding
    when it is INTERIOR -- a later frame did reach one -- because the last
    frames of a capture are always mid-flight when the run stops."""
    rows = [r for r in info["life"] if not (r["life_flags"] & 0x02)]
    open_rows = [r for r in rows if r["disposition"] == 0]
    if not open_rows:
        return {"open": 0, "interior": [], "edge": []}
    last_terminal = max((r["i"] for r in rows if r["disposition"] != 0), default=-1)
    interior = [r["frame_index"] for r in open_rows if r["i"] < last_terminal]
    edge = [r["frame_index"] for r in open_rows if r["i"] >= last_terminal]
    return {"open": len(open_rows), "interior": interior, "edge": edge}


def format_report(info, idxcap=None) -> str:
    u = usable(info)
    sci = scientific(info)
    dh, rh = {}, {}
    for r in sci:
        dh[DISPOSITION[r["disposition"]]] = dh.get(DISPOSITION[r["disposition"]], 0) + 1
        if r["disposition"] == 2:
            rh[REASON[r["reason"]]] = rh.get(REASON[r["reason"]], 0) + 1
    ivl = decision_intervals(info)
    res = interior_vs_edge(info)
    L = ["OGBPDISP1 downstream disposition trace",
         "  identity             %s / %s / %s / %s" % (info["test_id"], info["build_id"],
                                                       info["app"], info["commit"]),
         "  lifecycles           %d of %d" % (info["life_n"], info["life_cap"]),
         "  events (decisions)   %d of %d  (decisions taken %d)" % (info["event_n"], info["event_cap"], info["decisions"]),
         "  flags                %s" % ", ".join(flag_names(info["flags"])),
         "  tb_hz / tex / xfb    %d / %d / %d" % (info["tb_hz"], info["tex_slots"], info["xfb_slots"]),
         "  window opens at      %s" % ("-" if info["window_first_frame"] == KEY_NONE
                                        else info["window_first_frame"]),
         "  header/total CRC-32  %08x / %08x" % (info["header_crc32"], info["total_crc32"]),
         "  disposition-claim ready %s" % u["usable_for_disposition_claim"]]
    for why in u["reasons"]:
        L.append("      - " + why)
    L += ["", "  SCIENTIFIC WINDOW (self-test excluded)",
          "    lifecycles         %d" % len(sci)]
    for k, v in sorted(dh.items()):
        L.append("    %-18s %d" % (k, v))
    if rh:
        L.append("    HOLD reasons:")
        for k, v in sorted(rh.items()):
            L.append("      %-16s %d" % (k, v))
    L += ["", "  RESIDUALS",
          "    open               %d  (interior %d, capture-edge %d)"
          % (res["open"], len(res["interior"]), len(res["edge"]))]
    if res["interior"]:
        L.append("    INTERIOR OPEN FRAMES: %s" % res["interior"][:8])
    L += ["", "  LATENCIES (time-base ticks; n/min/p50/p90/max)"]
    for name, q in latencies(info, sci).items():
        L.append("    %-24s %s" % (name, "-" if not q else
                 "n=%d %d/%d/%d/%d" % (q["n"], q["min"], q["p50"], q["p90"], q["max"])))
    q = ivl["interval_ticks"]
    L += ["", "  PRESENTATION DECISIONS",
          "    interval           %s" % ("-" if not q else
              "n=%d %d/%d/%d/%d" % (q["n"], q["min"], q["p50"], q["p90"], q["max"])),
          "    retrace delta hist %s" % ivl["retrace_delta_hist"]]
    h = holds(info)
    if h:
        L += ["", "  EVERY HOLD, ONE ROW EACH (%d)" % len(h),
              "    ord     frame    prev  cur pend  retrace  drawn  newer?  reason"]
        for x in h:
            L.append("    %-7d %-8d %-5d %3d %4d %8d  %-5s  %-6s  %s"
                     % (x["ordinal"], x["frame_index"], x["prev_index"],
                        x["xfb_current"], x["xfb_pending"], x["retrace"],
                        "yes" if x["was_drawn"] else "NO",
                        "yes" if x["newer_frame_waiting"] else "no", x["reason"]))
    if idxcap:
        j = join_witness(info, idxcap)
        L += ["", "  JOIN WITH THE SOURCE WITNESS (%s)" % j["capture_build"],
              "    source records     %d" % j["source_records"],
              "    with a lifecycle   %d" % j["joined"],
              "    NOT in the trace   %d %s" % (j["not_in_trace"],
                                                j["not_in_trace_first"] or ""),
              "    disposition        %s" % j["disposition"]]
    else:
        L += ["", "  No OGBPIDXCAP1 supplied: this report says NOTHING about",
              "  source-frame ID continuity. Run tools/vindex.py for that."]
    return "\n".join(L)


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    if not a:
        print(__doc__)
        print("usage: vdisp.py <FILE-disp.bin> [FILE-idxcap.bin]")
        return 2
    info = load(a[0])
    print(format_report(info, a[1] if len(a) > 1 else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
