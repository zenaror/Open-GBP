#!/usr/bin/env python3
"""vstate.py — read and analyse a GBP-VIDEO-002 sidecar (OGBPSEQ1 format 2).

    tools/vstate.py info       <file>            header, clocks, counters, the result matrix
    tools/vstate.py frames     <file> [--limit N] the per-frame signature store
    tools/vstate.py events     <file>            the event store, in sequence order
    tools/vstate.py episodes   <file>            the episode descriptors and their preserved raw
    tools/vstate.py cycles     <file>            the bounded cycle records
    tools/vstate.py intervals  <file>            the observed boundary-to-boundary interval histogram
    tools/vstate.py signatures <file> [--frame N] one frame's 40 signatures
    tools/vstate.py oracle     <file> [--refdir D] the OFFLINE reference classification per episode
    tools/vstate.py extract    <file> <outdir>   the preserved raw frames and AUDIO blocks
    tools/vstate.py json       <file>            everything except the raw bytes

The sidecar is the OGBPSEQ1 family at version 2: same magic, same "OGBPEND1"
footer, same 32-byte identity fields, big-endian field by field, a header CRC
and a total CRC. Version 1 (GBP-VIDEO-001, tools/avseq.py) is a different
layout and is NOT read here; each parser checks `version` and `header_size`
before anything else, so neither can ever misread the other.

THE ORACLE IS HERE AND ONLY HERE. The probe carries no reference table,
checksum, pixel or block range. `oracle` reads the private inputs from
input/extracted/ at run time, classifies each preserved episode against the
Start-up Disc's embedded frame and GBI's two tables, and reports the result;
without those inputs the verdict is `reference_content=unavailable` and the
run's own hardware result is unaffected. Nothing private is ever written into
this repository.
"""
import json
import os
import struct
import sys

MAGIC = b"OGBPSEQ1"
FOOTER = b"OGBPEND1"
VERSION = 2
HEADER_SIZE = 0x200
FOOTER_SIZE = 12
FRAME_REC = 192
EVENT_REC = 64
EPISODE_REC = 512
CYCLE_REC = 128
FRAME_SIGS = 40
EPISODE_RAW_SLOTS = 4

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from avseq import (crc32, transform_block, gbi_block_checksum, _dol_read, _raw_image_read,
                       _find_reference, DISC_REF_VADDR, DISC_BLOCK_BYTES, GBI_IMAGE_BASE,
                       GBI_TABLE_A, GBI_TABLE_B, GBI_TABLE_ENTRIES)
except ImportError:                                                     # pragma: no cover
    raise

COMPLETENESS = {0: "unknown", 1: "complete_40", 2: "incomplete_short", 3: "incomplete_long",
                4: "predicate_anomaly", 5: "resync"}
FRAME_FLAGS = [(0x0001, "complete"), (0x0002, "disagreement"), (0x0004, "anomaly"),
               (0x0008, "pre_baseline"), (0x0010, "resync"), (0x0020, "early_candidate"),
               (0x0040, "overlong"), (0x0080, "raw_preserved"), (0x0100, "baseline"),
               (0x0200, "counted"), (0x0400, "tail"), (0x0800, "episode_change"),
               (0x1000, "episode_stable")]
EVENT_TYPES = {0: "none", 1: "capture_start", 2: "baseline_candidate", 3: "baseline_valid",
               4: "early_candidate", 5: "predicate_disagreement", 6: "incomplete_interval",
               7: "resync", 8: "episode_open", 9: "episode_stabilising", 10: "episode_stable",
               11: "episode_close", 12: "episode_store_full", 13: "anomaly", 14: "cap_reached",
               15: "safety_budget", 16: "scientific_target", 17: "tail_begin", 18: "stop",
               19: "teardown_begin", 20: "teardown_end"}
EPISODE_STATES = {0: "armed", 1: "changed", 2: "stabilising", 3: "closed"}
EPISODE_FLAGS = [(0x0001, "stable_found"), (0x0002, "capped"), (0x0004, "raw_preserved"),
                 (0x0008, "not_preserved"), (0x0010, "truncated_by_safety"), (0x0020, "tail"),
                 (0x0040, "early")]
STOP_REASONS = {0: "none", 1: "nominal_negative", 2: "frame_store_cap", 3: "event_store_cap",
                4: "safety_budget", 5: "delivery_cap", 6: "no_next_cause", 7: "failure"}
HEADER_FLAGS = [(0x0001, "service_ok"), (0x0002, "restore_ok"), (0x0004, "next_cause_at_end"),
                (0x0008, "partial"), (0x0010, "stage_a_aborted"), (0x0020, "baseline_valid"),
                (0x0040, "frame_store_full"), (0x0080, "event_store_full"),
                (0x0100, "episode_store_full"), (0x0200, "tail_truncated"),
                (0x0400, "counter_overflow")]
EPISODE_SHADOW = 0x80000000


def _u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def _u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def _u64(b, o):
    return struct.unpack_from(">Q", b, o)[0]


def _id(b, o):
    raw = b[o:o + 32]
    if b"\x00" not in raw:
        raise ValueError("identity field at 0x%X is not terminated (the format never truncates)" % o)
    text = raw.split(b"\x00", 1)[0]
    if any(raw[len(text):]):
        raise ValueError("identity field at 0x%X has bytes after its terminator" % o)
    return text.decode("ascii", "replace")


def _names(value, table):
    return [name for bit, name in table if value & bit]


def parse(data):
    """Strict parser: magic, version, record sizes, header CRC, section bounds, footer, total CRC,
    and the raw section's size derived from the episodes themselves. Raises ValueError otherwise."""
    if len(data) < HEADER_SIZE + FOOTER_SIZE or data[:8] != MAGIC:
        raise ValueError("not an OGBPSEQ1 file")
    d = {"version": _u16(data, 0x008), "header_size": _u16(data, 0x00A)}
    if d["version"] != VERSION or d["header_size"] != HEADER_SIZE:
        raise ValueError("unsupported version %u / header size 0x%X (this tool reads format 2; "
                         "GBP-VIDEO-001 files are format 1, read by tools/avseq.py)"
                         % (d["version"], d["header_size"]))
    for off, want, what in ((0x02C, FRAME_REC, "frame"), (0x02E, EVENT_REC, "event"),
                            (0x030, EPISODE_REC, "episode"), (0x032, CYCLE_REC, "cycle")):
        if _u16(data, off) != want:
            raise ValueError("unexpected %s record size %u" % (what, _u16(data, off)))
    if crc32(data[:HEADER_SIZE - 4]) != _u32(data, 0x1FC):
        raise ValueError("header CRC mismatch")
    if any(data[0x1E0:0x1FC]):
        raise ValueError("reserved header bytes are not zero")
    d["flags"] = _u32(data, 0x00C)
    d["flag_names"] = _names(d["flags"], HEADER_FLAGS)
    d["tb_hz"] = _u32(data, 0x010)
    d["frame_count"] = _u32(data, 0x014)
    d["event_count"] = _u32(data, 0x018)
    d["episode_count"] = _u32(data, 0x01C)
    d["cycle_count"] = _u32(data, 0x020)
    d["video_raw_frames"] = _u32(data, 0x024)
    d["audio_raw_count"] = _u32(data, 0x028)
    d["status_code"] = _u16(data, 0x034)
    d["stop_reason"] = _u16(data, 0x036)
    d["stop"] = STOP_REASONS.get(d["stop_reason"], "?")
    d["off_frames"] = _u32(data, 0x038)
    d["off_events"] = _u32(data, 0x03C)
    d["test_id"] = _id(data, 0x040)
    d["build_id"] = _id(data, 0x060)
    d["app"] = _id(data, 0x080)
    d["commit"] = _id(data, 0x0A0)
    d["off_episodes"] = _u32(data, 0x0C0)
    d["off_cycles"] = _u32(data, 0x0C4)
    d["off_video_raw"] = _u32(data, 0x0C8)
    d["off_audio_raw"] = _u32(data, 0x0CC)
    d["off_footer"] = _u32(data, 0x0D0)
    d["video_block_size"] = _u32(data, 0x0D4)
    d["audio_block_size"] = _u32(data, 0x0D8)
    d["frame_max_blocks"] = _u32(data, 0x0DC)
    for name, off in (("t_control_transform", 0x0E0), ("t_capture_start", 0x0E8), ("t_stop", 0x0F0),
                      ("capture_elapsed", 0x0F8), ("baseline_elapsed", 0x100),
                      ("valid_observation_elapsed", 0x108), ("valid_observation_at_target", 0x110),
                      ("safety_elapsed", 0x118), ("min_valid_observation_ticks", 0x120),
                      ("hard_wallclock_ticks", 0x128), ("t_teardown_begin", 0x130),
                      ("t_teardown_end", 0x138), ("t_baseline_valid", 0x188),
                      ("sig_samples", 0x190), ("sig_sum", 0x198), ("tail_ticks", 0x1B8)):
        d[name] = _u64(data, off)
    for name, off in (("deliveries", 0x140), ("video_completed", 0x144), ("audio_drains", 0x148),
                      ("frames_complete", 0x14C), ("frames_incomplete", 0x150), ("resync_frames", 0x154),
                      ("anomalies_frame", 0x158), ("anomalies_region", 0x15C),
                      ("boundaries_disc", 0x160), ("boundaries_gbi", 0x164), ("disagreements", 0x168),
                      ("episodes_opened", 0x16C), ("stable_episodes", 0x170),
                      ("unstable_episodes", 0x174), ("episodes_not_preserved", 0x178),
                      ("events_dropped", 0x17C), ("event_seq_last", 0x180),
                      ("baseline_frame_index", 0x184), ("sig_min", 0x1A0), ("sig_max", 0x1A4),
                      ("sig_median", 0x1A8), ("sig_p95", 0x1AC), ("sig_overflow", 0x1B0),
                      ("tail_frames", 0x1B4), ("cyc_first_n", 0x1C0), ("cyc_last_n", 0x1C4),
                      ("cyc_anomaly_n", 0x1C8), ("cyc_episode_n", 0x1CC),
                      ("baseline_sig0", 0x1D0), ("baseline_sig39", 0x1D4),
                      ("main_w1c", 0x1D8), ("isr_w1c", 0x1DC)):
        d[name] = _u32(data, off)
    d["header_crc32"] = _u32(data, 0x1FC)

    need = HEADER_SIZE
    if d["off_frames"] != need:
        raise ValueError("frame table is not at the end of the header")
    need += d["frame_count"] * FRAME_REC
    if need != d["off_events"]:
        raise ValueError("event table offset does not follow the frame table")
    need += d["event_count"] * EVENT_REC
    if need != d["off_episodes"]:
        raise ValueError("episode table offset does not follow the event table")
    need += d["episode_count"] * EPISODE_REC
    if need != d["off_cycles"]:
        raise ValueError("cycle table offset does not follow the episode table")
    need += d["cycle_count"] * CYCLE_REC
    if need != d["off_video_raw"]:
        raise ValueError("raw VIDEO offset does not follow the cycle table")
    if d["cyc_first_n"] + d["cyc_last_n"] + d["cyc_anomaly_n"] + d["cyc_episode_n"] != d["cycle_count"]:
        raise ValueError("the four cycle-record counts do not add up to cycle_count")
    if d["off_footer"] + FOOTER_SIZE != len(data):
        raise ValueError("file is truncated or has trailing bytes")
    if data[d["off_footer"]:d["off_footer"] + 8] != FOOTER:
        raise ValueError("footer magic missing")
    d["total_crc32"] = _u32(data, d["off_footer"] + 8)
    if crc32(data[:d["off_footer"]]) != d["total_crc32"]:
        raise ValueError("total CRC mismatch")

    d["frames"] = [_frame(data, d["off_frames"] + i * FRAME_REC) for i in range(d["frame_count"])]
    d["events"] = [_event(data, d["off_events"] + i * EVENT_REC) for i in range(d["event_count"])]
    d["episodes"] = [_episode(data, d["off_episodes"] + i * EPISODE_REC) for i in range(d["episode_count"])]
    d["cycles"] = [_cycle(data, d["off_cycles"] + i * CYCLE_REC) for i in range(d["cycle_count"])]
    raw = 0
    for ep in d["episodes"]:
        for k in range(ep["raw_frames"]):
            if ep["raw_frame_blocks"][k] > d["frame_max_blocks"]:
                raise ValueError("episode %u raw frame %u claims %u blocks" % (ep["index"], k, ep["raw_frame_blocks"][k]))
            raw += ep["raw_frame_blocks"][k] * d["video_block_size"]
    if d["off_video_raw"] + raw != d["off_audio_raw"]:
        raise ValueError("the raw VIDEO section does not match the episodes' preserved frames")
    if d["off_audio_raw"] + d["audio_raw_count"] * d["audio_block_size"] != d["off_footer"]:
        raise ValueError("the raw AUDIO section does not reach the footer")
    d["_data"] = data
    return d


def _frame(b, o):
    f = {"t_first_block": _u64(b, o + 0x00), "t_last_block": _u64(b, o + 0x08),
         "index": _u32(b, o + 0x10), "episode": _u32(b, o + 0x14),
         "blocks": _u16(b, o + 0x18), "flags": _u16(b, o + 0x1A),
         "disagreements": _u16(b, o + 0x1C), "completeness_code": _u16(b, o + 0x1E)}
    f["completeness"] = COMPLETENESS.get(f["completeness_code"], "?")
    f["flag_names"] = _names(f["flags"], FRAME_FLAGS)
    f["sig"] = list(struct.unpack_from(">%uI" % FRAME_SIGS, b, o + 0x20))
    f["duration"] = f["t_last_block"] - f["t_first_block"] if f["t_last_block"] >= f["t_first_block"] else 0
    f["episode_shadow"] = bool(f["episode"] & EPISODE_SHADOW)
    return f


def _event(b, o):
    e = {"t": _u64(b, o + 0x00), "seq": _u32(b, o + 0x08), "type_code": _u16(b, o + 0x0C),
         "flags": _u16(b, o + 0x0E), "a": _u32(b, o + 0x10), "b": _u32(b, o + 0x14),
         "c": _u32(b, o + 0x18), "d": _u32(b, o + 0x1C), "frame": _u32(b, o + 0x20),
         "episode": _u32(b, o + 0x24), "e": _u32(b, o + 0x28), "f": _u32(b, o + 0x2C),
         "t2": _u64(b, o + 0x30), "g": _u32(b, o + 0x38), "h": _u32(b, o + 0x3C)}
    e["type"] = EVENT_TYPES.get(e["type_code"], "?")
    return e


def _episode(b, o):
    ep = {"index": _u32(b, o + 0x00), "state_code": _u32(b, o + 0x04), "flags": _u32(b, o + 0x08),
          "open_frame": _u32(b, o + 0x0C), "close_frame": _u32(b, o + 0x10),
          "frames": _u32(b, o + 0x14), "stable_count": _u32(b, o + 0x18),
          "raw_frames": _u32(b, o + 0x1C), "t_open": _u64(b, o + 0x20), "t_close": _u64(b, o + 0x28)}
    ep["state"] = EPISODE_STATES.get(ep["state_code"], "?")
    ep["flag_names"] = _names(ep["flags"], EPISODE_FLAGS)
    ep["shadow"] = bool(ep["index"] & EPISODE_SHADOW)
    ep["raw_frame_index"] = list(struct.unpack_from(">%uI" % EPISODE_RAW_SLOTS, b, o + 0x30))
    ep["raw_frame_blocks"] = list(struct.unpack_from(">%uI" % EPISODE_RAW_SLOTS, b, o + 0x40))
    ep["raw_offset"] = list(struct.unpack_from(">%uI" % EPISODE_RAW_SLOTS, b, o + 0x50))
    ep["candidate"] = list(struct.unpack_from(">%uI" % FRAME_SIGS, b, o + 0x60))
    ep["final_sig"] = list(struct.unpack_from(">%uI" % FRAME_SIGS, b, o + 0x100))
    if ep["raw_frames"] > EPISODE_RAW_SLOTS:
        raise ValueError("episode %u claims %u raw frames" % (ep["index"], ep["raw_frames"]))
    if any(b[o + 0x1A0:o + EPISODE_REC]):
        raise ValueError("episode %u reserved bytes are not zero" % ep["index"])
    return ep


def _cycle(b, o):
    c = {"t_cause": _u64(b, o + 0x00), "t_unmask": _u64(b, o + 0x08), "t_entry": _u64(b, o + 0x10),
         "t_read": _u64(b, o + 0x18), "t_ack": _u64(b, o + 0x20), "t_rearm": _u64(b, o + 0x28),
         "t_next": _u64(b, o + 0x30), "index": _u32(b, o + 0x38), "frame_index": _u32(b, o + 0x3C),
         "pending": _u16(b, o + 0x40), "ack_value": _u16(b, o + 0x42), "kind_code": _u16(b, o + 0x44),
         "flags": _u16(b, o + 0x46), "audio_selected": b[o + 0x48], "audio_completed": b[o + 0x49],
         "video_selected": b[o + 0x4A], "video_completed": b[o + 0x4B], "main_w1c": b[o + 0x4C],
         "isr_count": b[o + 0x4D], "isr_reentry": b[o + 0x4E], "next_observed": b[o + 0x4F],
         "latency_ticks": _u32(b, o + 0x50), "audio_wait": _u32(b, o + 0x54),
         "video_wait": _u32(b, o + 0x58), "sig_ticks": _u32(b, o + 0x5C),
         "intsr_entry": _u32(b, o + 0x60), "intsr_after_w1c": _u32(b, o + 0x64),
         "intsr_postack": _u32(b, o + 0x68), "intsr_next": _u32(b, o + 0x6C),
         "block_in_frame": _u32(b, o + 0x70), "rc": _u32(b, o + 0x74)}
    c["kind"] = {0: "first", 1: "last", 2: "anomaly", 3: "episode"}.get(c["kind_code"], "?")
    return c


def episode_raw(d, ep_index, slot):
    """The bytes of one preserved raw frame (all its blocks, contiguous)."""
    ep = d["episodes"][ep_index]
    if slot >= ep["raw_frames"]:
        return None
    off = ep["raw_offset"][slot]
    n = ep["raw_frame_blocks"][slot] * d["video_block_size"]
    return d["_data"][off:off + n]


def audio_bytes(d, i):
    if i >= d["audio_raw_count"]:
        return None
    o = d["off_audio_raw"] + i * d["audio_block_size"]
    return d["_data"][o:o + d["audio_block_size"]]


def seconds(d, ticks):
    hz = d["tb_hz"] or 1
    return "%u.%03u" % (ticks // hz, (ticks % hz) * 1000 // hz)


def intervals(d):
    """The observed boundary-to-boundary interval histogram, rebuilt from the frame table.
    40 is the references' hypothesis and is never assumed: what is printed is what was seen."""
    hist = {}
    for f in d["frames"]:
        hist[f["blocks"]] = hist.get(f["blocks"], 0) + 1
    return dict(sorted(hist.items()))


def info_text(d):
    out = ["file: OGBPSEQ1 v%u  test=%s build=%s app=%s commit=%s"
           % (d["version"], d["test_id"], d["build_id"], d["app"], d["commit"]),
           "flags: %s" % (", ".join(d["flag_names"]) or "-"),
           "stop: %s   status_code=%u   tb_hz=%u" % (d["stop"], d["status_code"], d["tb_hz"]),
           "",
           "clocks (all 64-bit; a 32-bit tick counter wraps at %s s)" % seconds(d, 0xFFFFFFFF),
           "  epoch (CONTROL transform) %#018x" % d["t_control_transform"],
           "  capture start             %#018x" % d["t_capture_start"],
           "  stop                      %#018x" % d["t_stop"],
           "  capture_elapsed           %s s" % seconds(d, d["capture_elapsed"]),
           "  baseline_elapsed          %s s" % seconds(d, d["baseline_elapsed"]),
           "  valid_observation         %s s   (target %s s)"
           % (seconds(d, d["valid_observation_elapsed"]), seconds(d, d["min_valid_observation_ticks"])),
           "  valid_at_target           %s s" % seconds(d, d["valid_observation_at_target"]),
           "  safety_elapsed            %s s   (hard limit %s s)"
           % (seconds(d, d["safety_elapsed"]), seconds(d, d["hard_wallclock_ticks"])),
           "  teardown                  %#018x -> %#018x" % (d["t_teardown_begin"], d["t_teardown_end"]),
           "",
           "service: deliveries=%u video=%u audio=%u isr_w1c=%u main_w1c=%u"
           % (d["deliveries"], d["video_completed"], d["audio_drains"], d["isr_w1c"], d["main_w1c"]),
           "frames:  %u observed (%u complete, %u incomplete, %u resync); anomalies a=%u b=%u"
           % (d["frame_count"], d["frames_complete"], d["frames_incomplete"], d["resync_frames"],
              d["anomalies_frame"], d["anomalies_region"]),
           "predicates: boundaries_disc=%u boundaries_gbi=%u disagreements=%u  (segmentation: Disc)"
           % (d["boundaries_disc"], d["boundaries_gbi"], d["disagreements"]),
           "baseline: %s at frame %u  sig[0]=%08x sig[39]=%08x"
           % ("valid" if "baseline_valid" in d["flag_names"] else "NEVER ESTABLISHED",
              d["baseline_frame_index"], d["baseline_sig0"], d["baseline_sig39"]),
           "structured change: %s  episodes=%u stable=%u unstable=%u not_preserved=%u preserved=%u"
           % ("observed" if d["episodes_opened"] else "not_observed", d["episodes_opened"],
              d["stable_episodes"], d["unstable_episodes"], d["episodes_not_preserved"], d["episode_count"]),
           "tail: frames=%u ticks=%s s   events=%u (dropped %u, last seq %u)"
           % (d["tail_frames"], seconds(d, d["tail_ticks"]), d["event_count"], d["events_dropped"],
              d["event_seq_last"]),
           "signature cost (ticks): samples=%u min=%u median=%u p95=%u max=%u overflow=%u mean=%u"
           % (d["sig_samples"], d["sig_min"], d["sig_median"], d["sig_p95"], d["sig_max"],
              d["sig_overflow"], d["sig_sum"] // d["sig_samples"] if d["sig_samples"] else 0),
           "  (no threshold is applied: the design withdrew the arbitrary 25 % gate and requires"
           "  a measurement and a with/without cadence comparison reviewed by a person)",
           "raw: %u preserved frames, %u AUDIO blocks, file %u bytes, crc32 %08x"
           % (d["video_raw_frames"], d["audio_raw_count"], len(d["_data"]), d["total_crc32"]),
           "",
           "REFERENCE_MATCH is not in this file: it is computed offline by `oracle`, from the",
           "private inputs, and never by the probe."]
    return "\n".join(out)


def frames_text(d, limit=0):
    out = []
    fr = d["frames"][:limit] if limit else d["frames"]
    for f in fr:
        out.append("frame %5u blocks=%2u %-17s dur=%9u ep=%08x dis=%u sig0=%08x sig39=%08x %s"
                   % (f["index"], f["blocks"], f["completeness"], f["duration"], f["episode"],
                      f["disagreements"], f["sig"][0], f["sig"][FRAME_SIGS - 1],
                      ",".join(f["flag_names"])))
    if limit and len(d["frames"]) > limit:
        out.append("... %u more frames (use --limit 0 for all)" % (len(d["frames"]) - limit))
    return "\n".join(out)


def events_text(d):
    return "\n".join("seq %5u t=%#018x %-22s frame=%u ep=%08x a=%u b=%u c=%08x d=%u"
                     % (e["seq"], e["t"], e["type"], e["frame"], e["episode"], e["a"], e["b"],
                        e["c"], e["d"]) for e in d["events"])


def episodes_text(d):
    out = []
    for i, ep in enumerate(d["episodes"]):
        out.append("episode %u index=%08x%s state=%s flags=%s frames=%u stable_count=%u"
                   % (i, ep["index"], " SHADOW" if ep["shadow"] else "", ep["state"],
                      ",".join(ep["flag_names"]) or "-", ep["frames"], ep["stable_count"]))
        out.append("   frames %u..%u   t %#x -> %#x   raw %u/%u"
                   % (ep["open_frame"], ep["close_frame"], ep["t_open"], ep["t_close"],
                      ep["raw_frames"], EPISODE_RAW_SLOTS))
        for k in range(ep["raw_frames"]):
            out.append("   raw[%u] frame=%u blocks=%u at 0x%X"
                       % (k, ep["raw_frame_index"][k], ep["raw_frame_blocks"][k], ep["raw_offset"][k]))
        out.append("   candidate[0]=%08x final[0]=%08x" % (ep["candidate"][0], ep["final_sig"][0]))
    if not out:
        out.append("no episode descriptors: no structured change was preserved")
    out.append("# an episode is a change relative to the reference signature OF THE MOMENT.")
    out.append("# It never means the expected screen was found: only `oracle` can say that.")
    return "\n".join(out)


def cycles_text(d):
    return "\n".join(
        "%-8s n=%7u frame=%5u blk=%2u pend=%04x ack=%04x a=%u/%u v=%u/%u w1c=%u isr=%u/%u "
        "next=%u lat=%u sig_ticks=%u"
        % (c["kind"], c["index"], c["frame_index"], c["block_in_frame"], c["pending"], c["ack_value"],
           c["audio_selected"], c["audio_completed"], c["video_selected"], c["video_completed"],
           c["main_w1c"], c["isr_count"], c["isr_reentry"], c["next_observed"], c["latency_ticks"],
           c["sig_ticks"]) for c in d["cycles"])


def intervals_text(d):
    h = intervals(d)
    out = ["observed boundary-to-boundary intervals (blocks: frames)"]
    for k, v in h.items():
        out.append("  %3u: %u" % (k, v))
    out.append("# 40 is the references' hypothesis; this is what the hardware actually produced.")
    return "\n".join(out)


def oracle(d, refdir=None):
    """The OFFLINE classification of each PRESERVED episode against the Start-up Disc's embedded
    frame and GBI's two tables. This is the only place the capture meets the references' data, and
    it is never a gate for the hardware result. Without the private inputs the verdict is
    `unavailable`; the references' assets are read at run time and never stored here."""
    ref = _find_reference(refdir)
    out = {"reference_content": "unavailable", "refdir": ref["refdir"],
           "disc_available": bool(ref["disc_main_dol"]), "gbi_available": bool(ref["gbi_image"]),
           "episodes": []}
    table_a = table_b = None
    if ref["gbi_image"]:
        ta = _raw_image_read(ref["gbi_image"], GBI_IMAGE_BASE, GBI_TABLE_A, GBI_TABLE_ENTRIES * 4)
        tb = _raw_image_read(ref["gbi_image"], GBI_IMAGE_BASE, GBI_TABLE_B, GBI_TABLE_ENTRIES * 4)
        table_a = list(struct.unpack(">%uI" % GBI_TABLE_ENTRIES, ta)) if ta else None
        table_b = list(struct.unpack(">%uI" % GBI_TABLE_ENTRIES, tb)) if tb else None
    # our own measurement, independent of any reference: each episode's settled signature vector
    for i, ep in enumerate(d["episodes"]):
        item = {"episode": i, "index": "%08x" % ep["index"], "flags": ep["flag_names"],
                "raw_frames": ep["raw_frames"], "verdict": "insufficient_data",
                "signature_matches_table_a": None, "signature_matches_table_b": None,
                "blocks_compared": 0, "matches_disc": 0, "first_mismatch_block": None}
        sig = ep["final_sig"] if "stable_found" in ep["flag_names"] else ep["candidate"]
        item["signature"] = ["%08x" % s for s in sig]
        if table_a is not None:
            item["signature_matches_table_a"] = sum(1 for k in range(GBI_TABLE_ENTRIES) if sig[k] == table_a[k])
        if table_b is not None:
            item["signature_matches_table_b"] = sum(1 for k in range(GBI_TABLE_ENTRIES) if sig[k] == table_b[k])
        if ref["available"] and ep["raw_frames"]:
            # compare the LAST preserved raw frame (the settled state when there is one)
            slot = ep["raw_frames"] - 1
            raw = episode_raw(d, i, slot)
            blocks = ep["raw_frame_blocks"][slot]
            hits = 0
            compared = 0
            for pos in range(min(blocks, GBI_TABLE_ENTRIES)):
                b = raw[pos * d["video_block_size"]:(pos + 1) * d["video_block_size"]]
                if len(b) != d["video_block_size"]:
                    break
                compared += 1
                if ref["disc_main_dol"]:
                    expect = _dol_read(ref["disc_main_dol"], DISC_REF_VADDR + pos * DISC_BLOCK_BYTES, DISC_BLOCK_BYTES)
                    if expect is not None:
                        got = struct.pack(">%uH" % (DISC_BLOCK_BYTES // 2), *transform_block(b))
                        if got == expect:
                            hits += 1
                        elif item["first_mismatch_block"] is None:
                            item["first_mismatch_block"] = pos
            item["blocks_compared"] = compared
            item["matches_disc"] = hits
            if compared == 0:
                item["verdict"] = "insufficient_data"
            elif hits == compared:
                item["verdict"] = "full_match"
            elif hits:
                item["verdict"] = "partial_match"
            else:
                item["verdict"] = "mismatch"
        out["episodes"].append(item)
    if ref["available"]:
        out["reference_content"] = "computed"
    else:
        out["note"] = ("the private reference inputs are absent: the content oracle is not computed. "
                       "The run's own hardware result (SERVICE / frames / baseline / episodes / "
                       "RESTORE) is unaffected.")
    out["disclaimer"] = ("a signature or pixel match identifies WHICH screen an episode was; it is "
                         "never a gate for the hardware result, and bytes that do not match are new "
                         "evidence, not a failure.")
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, path = argv[0], argv[1]
    with open(path, "rb") as f:
        data = f.read()
    try:
        d = parse(data)
    except ValueError as e:
        print("vstate: %s" % e, file=sys.stderr)
        return 1
    if cmd == "info":
        print(info_text(d))
    elif cmd == "frames":
        limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 40
        print(frames_text(d, limit))
    elif cmd == "events":
        print(events_text(d))
    elif cmd == "episodes":
        print(episodes_text(d))
    elif cmd == "cycles":
        print(cycles_text(d))
    elif cmd == "intervals":
        print(intervals_text(d))
    elif cmd == "signatures":
        n = int(argv[argv.index("--frame") + 1]) if "--frame" in argv else 0
        if n >= len(d["frames"]):
            print("vstate: no frame %u" % n, file=sys.stderr)
            return 1
        f = d["frames"][n]
        print("frame %u blocks=%u %s" % (f["index"], f["blocks"], f["completeness"]))
        for k in range(FRAME_SIGS):
            print("  block %2u  %08x" % (k, f["sig"][k]))
    elif cmd == "oracle":
        refdir = argv[argv.index("--refdir") + 1] if "--refdir" in argv else None
        print(json.dumps(oracle(d, refdir), indent=1))
    elif cmd == "json":
        print(json.dumps({k: v for k, v in d.items() if not k.startswith("_")}, indent=1))
    elif cmd == "extract":
        if len(argv) < 3:
            print("extract needs an output directory", file=sys.stderr)
            return 2
        outdir = argv[2]
        os.makedirs(outdir, exist_ok=True)
        n = 0
        for i, ep in enumerate(d["episodes"]):
            for k in range(ep["raw_frames"]):
                b = episode_raw(d, i, k)
                with open(os.path.join(outdir, "episode-%02u-frame-%u-idx%05u.bin"
                                       % (i, k, ep["raw_frame_index"][k])), "wb") as f:
                    f.write(b)
                n += 1
        for i in range(d["audio_raw_count"]):
            with open(os.path.join(outdir, "audio-%02u.bin" % i), "wb") as f:
                f.write(audio_bytes(d, i))
        print("wrote %u preserved raw frame(s) and %u AUDIO block(s) to %s" % (n, d["audio_raw_count"], outdir))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
