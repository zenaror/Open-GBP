#!/usr/bin/env python3
"""vstate.py — read and analyse a GBP-VIDEO-002 sidecar (OGBPSEQ1 format 2, 3 or 4).

    tools/vstate.py info       <file>            header, clocks, counters, the result matrix
    tools/vstate.py frames     <file> [--limit N] the per-frame signature store
    tools/vstate.py events     <file>            the event store, in sequence order
    tools/vstate.py episodes   <file>            the episode descriptors and their preserved raw
    tools/vstate.py cycles     <file>            the bounded cycle records
    tools/vstate.py intervals  <file>            the observed boundary-to-boundary interval histogram
    tools/vstate.py signatures <file> [--frame N] one frame's 40 signatures
    tools/vstate.py diag       <file>            the semantic-disagreement diagnostics, explained (v3/v4)
    tools/vstate.py semantic   <file>            the aggregate semantic-coherence block (v4)
    tools/vstate.py oracle     <file> [--refdir D] the OFFLINE reference classification per episode
    tools/vstate.py extract    <file> <outdir>   the preserved raw frames and AUDIO blocks
    tools/vstate.py json       <file>            everything except the raw bytes

Three versions of the family are read here, dispatched explicitly and each strict:
  v2  the FROZEN format of build vstate-0001, the first physical run. Not one
      byte of its contract moves.
  v3  v2 plus one section carrying the semantic-disagreement diagnostic
      (U-GBP-032), written by the instrumented build vstate-0002.
  v4  v3's successor, written by build vstate-0003: the 1024-byte semantic block
      and the 160-byte diagnostic record array. FROZEN and HISTORICAL, with a
      KNOWN PRODUCER DEFECT (GBP-HW-104) — a record's current-cycle fields may
      have been overwritten by a later service cycle. The parser is deliberately
      NOT tightened for it: refusing the only physical v4 file would destroy the
      evidence. `diag` reports the contradictions as non-fatal PRODUCER WARNINGS
      instead, and the trusted/untrusted split is GBP-HW-105.
Version 1 (GBP-VIDEO-001, tools/avseq.py) is a different layout and is NOT read
here. Every parser checks `version` and `header_size` before anything else, so
no file of one version can be read as another.

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
VERSIONS = (2, 3, 4, 5)    # 2, 3 and 4 are frozen physical formats; 5 is what vstate-0004 writes
VERSION = 5
DIAG_REC = 96              # the v3 record
DIAG_REC_V4 = 160          # the v4 record: the v3 one plus a 64-byte follow-up block
DIAG_REC_V5 = 160          # v5 keeps it, byte for byte: no field was ever missing
MAX_DIAGS = 256
SEMANTIC_SIZE = 1024
SEMANTIC_TAG = 0x4F475342  # "OGSB"
SEMANTIC_VERSION = 1
DIAGF_ALL = 0x0001         # bit 0 = store_capped
RECORD_FLAGS_ALL = 0x00FF      # v4: bits 8..15 reserved and zero
RECORD_FLAGS_ALL_V5 = 0x01FF   # v5 adds service_written (0x0100)
SRC_MASK = 0x0555
AV_MASK = 0x0500
GAP_NONE = 0xFFFFFFFF
GAP_SLOT_BITS = (0x0001, 0x0004, 0x0010, 0x0040, 0x0100, 0x0400)
CLASS_NAMES = {1: "source_serviced", 2: "source_other", 3: "non_source"}
FU_NAMES = {0: "pending", 1: "source_present_next", 2: "source_absent_next",
            3: "no_next_cause", 4: "unknown"}
FUR_NAMES = {0: "-", 1: "observational_site", 2: "run_aborted", 3: "not_applicable",
             4: "internal_condition"}
RECORD_FLAG_NAMES = ((0x0001, "followup_filled"), (0x0002, "payload_valid"),
                     (0x0004, "payload_second_omitted"), (0x0008, "frame_quarantined"),
                     (0x0010, "source_deferred"), (0x0020, "service_incomplete"),
                     (0x0040, "ack_written"), (0x0080, "rearm_written"),
                     (0x0100, "service_written"))
DF_FOLLOWUP_FILLED = 0x0001
DF_PAYLOAD_VALID = 0x0002
DF_PAYLOAD_SECOND = 0x0004
DF_FRAME_QUARANTINED = 0x0008
DF_SOURCE_DEFERRED = 0x0010
DF_SERVICE_INCOMPLETE = 0x0020
DF_ACK_WRITTEN = 0x0040
DF_REARM_WRITTEN = 0x0080
DF_SERVICE_WRITTEN = 0x0100
BIT15_MASK = 0x8000
SRC_VIDEO = 0x0100
SRC_AUDIO = 0x0400
SEM_COUNTERS = ("disagreements_total", "source_serviced", "source_other", "non_source",
                "disc_extra_events", "majority_extra_events", "both_direction_events",
                "majority_extra_video_services", "majority_extra_audio_services",
                "frames_quarantined", "frames_source_deferred", "diagnostics_preserved",
                "diagnostics_not_preserved", "followup_present", "followup_absent",
                "followup_no_next", "followup_unknown", "observational_disagreements",
                "service_selecting_disagreements", "payload_diagnostics_captured",
                "service_incomplete_events")
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
    # Explicit dispatch. v2 is the frozen physical format of build vstate-0001; v3 is v2 plus the
    # diagnostic section, written by the instrumented build. Neither is ever read as the other, and
    # GBP-VIDEO-001's format 1 belongs to tools/avseq.py.
    if d["version"] not in VERSIONS or d["header_size"] != HEADER_SIZE:
        raise ValueError("unsupported version %u / header size 0x%X (this tool reads formats 2, 3, 4 "
                         "and 5; GBP-VIDEO-001 files are format 1, read by tools/avseq.py)"
                         % (d["version"], d["header_size"]))
    for off, want, what in ((0x02C, FRAME_REC, "frame"), (0x02E, EVENT_REC, "event"),
                            (0x030, EPISODE_REC, "episode"), (0x032, CYCLE_REC, "cycle")):
        if _u16(data, off) != want:
            raise ValueError("unexpected %s record size %u" % (what, _u16(data, off)))
    if crc32(data[:HEADER_SIZE - 4]) != _u32(data, 0x1FC):
        raise ValueError("header CRC mismatch")
    d["off_semantic"] = d["semantic_size"] = d["diag_flags"] = 0
    if d["version"] == 2:
        # v2 is FROZEN: the whole area is reserved and must be zero, exactly as the physical
        # sidecar of 2026-09-16 has it.
        if any(data[0x1E0:0x1FC]):
            raise ValueError("v2 reserved header bytes are not zero")
        d["off_diag"] = d["diag_count"] = d["diag_rec_size"] = 0
    elif d["version"] in (4, 5):
        # v4 and v5 share ONE layout: every v3 field keeps its meaning and its
        # offset, and the block is at the same place in both. What separates them
        # is the producer contract, enforced per record below.
        d["off_diag"] = _u32(data, 0x1E0)
        d["diag_count"] = _u32(data, 0x1E4)
        d["diag_rec_size"] = _u16(data, 0x1E8)
        d["diag_flags"] = _u16(data, 0x1EA)
        d["off_semantic"] = _u32(data, 0x1EC)
        d["semantic_size"] = _u32(data, 0x1F0)
        if any(data[0x1F4:0x1FC]):
            raise ValueError("v%u reserved header bytes are not zero" % d["version"])
        if d["diag_count"] > MAX_DIAGS:
            raise ValueError("at most %u diagnostic records (%u claimed)" % (MAX_DIAGS, d["diag_count"]))
        if d["diag_rec_size"] != DIAG_REC_V4:
            raise ValueError("unexpected diagnostic record size %u in a v%u file"
                             % (d["diag_rec_size"], d["version"]))
        if d["semantic_size"] != SEMANTIC_SIZE:
            raise ValueError("unexpected semantic block size %u" % d["semantic_size"])
        if d["diag_flags"] & ~DIAGF_ALL:
            raise ValueError("unknown diag_flags bit set (%04x)" % d["diag_flags"])
    else:
        d["off_diag"] = _u32(data, 0x1E0)
        d["diag_count"] = _u32(data, 0x1E4)
        d["diag_rec_size"] = _u16(data, 0x1E8)
        if any(data[0x1EA:0x1FC]):
            raise ValueError("v3 reserved header bytes are not zero")
        if d["diag_count"] > 1:
            raise ValueError("at most one diagnostic record may exist (%u claimed)" % d["diag_count"])
        # The same rule the C parser applies, so the two never disagree on what is a valid file:
        # with a record present the size is exactly 96; with no record the writer still states 96,
        # and 0 is tolerated, but nothing else is.
        if d["diag_count"] and d["diag_rec_size"] != DIAG_REC:
            raise ValueError("unexpected diagnostic record size %u" % d["diag_rec_size"])
        if not d["diag_count"] and d["diag_rec_size"] not in (0, DIAG_REC):
            raise ValueError("unexpected diagnostic record size %u with no record" % d["diag_rec_size"])
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
    if d["version"] == 3:
        if need != d["off_diag"]:
            raise ValueError("diagnostic offset does not follow the cycle table")
        need += d["diag_count"] * DIAG_REC
    elif d["version"] in (4, 5):
        if need != d["off_semantic"]:
            raise ValueError("semantic block does not follow the cycle table")
        need += SEMANTIC_SIZE
        if need != d["off_diag"]:
            raise ValueError("diagnostic array does not follow the semantic block")
        need += d["diag_count"] * DIAG_REC_V4
    if need != d["off_video_raw"]:
        raise ValueError("raw VIDEO offset does not follow the %s" % ("diagnostic section" if d["version"] == 3 else "cycle table"))
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
    d["diag"] = _diag(data, d["off_diag"]) if d["version"] == 3 and d["diag_count"] else None
    d["diags"] = []
    d["semantic"] = None
    if d["version"] in (4, 5):
        d["semantic"] = _semantic(data, d["off_semantic"])
        d["diags"] = [_diag_v4(data, d["off_diag"] + i * DIAG_REC_V4, d["version"], i)
                      for i in range(d["diag_count"])]
        if d["diags"]:
            d["diag"] = d["diags"][0]
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



READ_KINDS = {0: "READ", 1: "PRESVC", 2: "POSTDRAIN", 3: "POSTACK", 4: "OTHER"}


def _diag(b, o):
    d = {"t": _u64(b, o + 0x00), "cycle": _u32(b, o + 0x08), "valid": _u32(b, o + 0x0C),
         "disc_value": _u16(b, o + 0x10), "gbi_value": _u16(b, o + 0x12),
         "read_kind_code": _u16(b, o + 0x14), "attempts": _u16(b, o + 0x16),
         "raw": list(b[o + 0x18:o + 0x38]),
         "intsr_entry": _u32(b, o + 0x38), "intsr_after_w1c": _u32(b, o + 0x3C),
         "intmr_entry": _u32(b, o + 0x40), "latency_ticks": _u32(b, o + 0x44),
         "xfer_ticks": _u32(b, o + 0x48), "xfer_polls": _u16(b, o + 0x4C),
         "dma_status": _u16(b, o + 0x4E), "dma_status_before": _u16(b, o + 0x50),
         "control_exp": _u16(b, o + 0x52), "frame_index": _u32(b, o + 0x54),
         "block_in_frame": _u32(b, o + 0x58)}
    d["read_kind"] = READ_KINDS.get(d["read_kind_code"], "?")
    if len(d["raw"]) != 32:
        raise ValueError("diagnostic record does not carry 32 raw bytes")
    if any(b[o + 0x5C:o + DIAG_REC]):
        raise ValueError("diagnostic reserved bytes are not zero")
    return d


def classify(disc, gbi):
    """The normative classification of §R3.2, in the normative ORDER: the bits with no
    contract first. 0 means the two readings agree."""
    delta = disc ^ gbi
    if delta == 0:
        return 0
    if delta & ~SRC_MASK & 0xFFFF:
        return 3                                     # non_source
    if delta & (SRC_MASK & ~AV_MASK) & 0xFFFF:
        return 2                                     # source_other
    return 1                                         # source_serviced


def authoritative(disc, gbi):
    """The composition of §R3.3: outside SRC_MASK the two readings must already agree, so
    taking either is taking the AGREED value and never a vote; inside SRC_MASK the bitwise
    majority wins. Project policy, not a fact about what the hardware intends."""
    return ((disc & ~SRC_MASK) | (gbi & SRC_MASK)) & 0xFFFF


def _validate_v5(d, i):
    """The v5 cross-field invariants of §R4.8, recomputed from the record's own 32 bytes and
    from the normative functions above — never from a stored derived value.

    They exist because a v4 producer could write a record whose current-cycle fields belonged
    to a LATER cycle (GBP-HW-104) and no rule refused it. In v5 each of these is fatal. They
    are NEVER applied to v2, v3 or v4: a frozen physical file keeps parsing as it always did.
    """
    def bad(msg):
        raise ValueError("v5 record %u: %s" % (i, msg))
    raw = bytes(d["raw"])
    fl = d["record_flags"]
    disc, gbi = d["disc_value"], d["gbi_value"]
    selects = d["read_kind"] in ("READ", "PRESVC")
    # 1. both readings, from the bytes themselves
    if read_disc(raw) != disc or read_gbi(raw) != gbi:
        bad("the stored readings are not what raw[32] recomputes (%04x/%04x vs %04x/%04x)"
            % (disc, gbi, read_disc(raw), read_gbi(raw)))
    # 2. every derived field, from those two
    if d["delta"] != (disc ^ gbi):
        bad("delta %04x is not disc ^ gbi" % d["delta"])
    if d["disc_extra_sources"] != (disc & SRC_MASK) & ~(gbi & SRC_MASK) & 0xFFFF:
        bad("disc_extra_sources %04x is not recomputable" % d["disc_extra_sources"])
    if d["majority_extra_sources"] != (gbi & SRC_MASK) & ~(disc & SRC_MASK) & 0xFFFF:
        bad("majority_extra_sources %04x is not recomputable" % d["majority_extra_sources"])
    if d["classification_code"] != classify(disc, gbi):
        bad("classification %u is not the normative one (%u)"
            % (d["classification_code"], classify(disc, gbi)))
    # 3. the composed authoritative value — the invariant the physical v4 file fails
    auth = authoritative(disc, gbi)
    if d["authoritative_value"] != auth:
        bad("authoritative %04x is not the composition of the two readings (%04x)"
            % (d["authoritative_value"], auth))
    # 4. the service decision, and the zero that must not be ambiguous
    if fl & DF_SERVICE_WRITTEN:
        if not selects:
            bad("an observational record claims a service decision")
        if d["service_selected"] != (auth & AV_MASK):
            bad("service_selected %04x is not authoritative & AV_MASK (%04x)"
                % (d["service_selected"], auth & AV_MASK))
    elif d["service_selected"] != 0:
        bad("service_selected %04x with no recorded service decision" % d["service_selected"])
    # 5. the ACK identity and its invalid encoding
    if fl & DF_ACK_WRITTEN:
        if not fl & DF_SERVICE_WRITTEN:
            bad("an ACK with no service decision")
        if d["ack_value"] != (auth | BIT15_MASK):
            bad("ack_value %04x is not authoritative | 0x8000 (%04x)"
                % (d["ack_value"], auth | BIT15_MASK))
        if d["t_ack"] < d["t"]:
            bad("t_ack is before the read that opened the record")
    elif d["ack_value"] or d["t_ack"]:
        bad("a plausible ACK without ACK_WRITTEN")
    # 6. the re-arm: never before the ACK, invalid without its flag
    if fl & DF_REARM_WRITTEN:
        if not fl & DF_ACK_WRITTEN:
            bad("a re-arm with no ACK")
        if d["t_rearm"] < d["t_ack"]:
            bad("t_rearm is before t_ack")
    elif d["t_rearm"]:
        bad("a plausible re-arm without REARM_WRITTEN")
    # 7. the follow-up, per source bit and against the majority only
    if d["followup_state_code"] in (1, 2):
        if not selects or d["disc_extra_sources"] == 0:
            bad("a follow-up verdict where no source was omitted")
        if not fl & DF_REARM_WRITTEN:
            bad("a next cause after a re-arm that was never written")
        if not fl & DF_FOLLOWUP_FILLED:
            bad("a follow-up verdict without followup_filled")
        if d["t_next_cause"] < d["t_rearm"]:
            bad("t_next_cause is before the re-arm")
        absent = d["disc_extra_sources"] & ~(d["next_pending_gbi"] & SRC_MASK) & 0xFFFF
        if (d["followup_state_code"] == 1) != (absent == 0):
            bad("the aggregate follow-up state contradicts the per-bit split")
    else:
        if d["t_next_cause"] or d["next_pending_gbi"] or d["next_pending_disc"]:
            bad("next-cause fields are set although no next cause was observed")
        if d["followup_state_code"] == 3 and not fl & DF_REARM_WRITTEN:
            bad("no_next_cause without a written re-arm")
    # 8. the observational contract
    if not selects:
        forbidden = (DF_SERVICE_WRITTEN | DF_ACK_WRITTEN | DF_REARM_WRITTEN | DF_PAYLOAD_VALID |
                     DF_PAYLOAD_SECOND | DF_FRAME_QUARANTINED | DF_SOURCE_DEFERRED |
                     DF_SERVICE_INCOMPLETE)
        if fl & forbidden:
            bad("an observational record claims current-service effects (%04x)" % (fl & forbidden))
        if d["followup_state_code"] != 4 or d["followup_reason_code"] != 1:
            bad("an observational record must be FU_UNKNOWN / observational_site")
    # 9. the payload provenance, and the two markers
    if fl & DF_PAYLOAD_VALID:
        if not fl & DF_SERVICE_WRITTEN:
            bad("a payload with no service decision")
        if not d["payload_source"] & d["majority_extra_sources"]:
            bad("payload_source %04x is not a majority-extra source" % d["payload_source"])
        if not d["payload_source"] & d["service_selected"]:
            bad("payload_source %04x was not serviced" % d["payload_source"])
        if (fl & DF_PAYLOAD_SECOND) and (d["majority_extra_sources"] & AV_MASK) != AV_MASK:
            bad("payload_second_omitted with only one eligible majority-extra source")
    elif fl & DF_PAYLOAD_SECOND:
        bad("payload_second_omitted without a payload")
    if (fl & DF_FRAME_QUARANTINED) and not d["majority_extra_sources"] & SRC_VIDEO:
        bad("frame_quarantined without majority-extra VIDEO")
    if (fl & DF_SOURCE_DEFERRED) and not d["disc_extra_sources"] & SRC_VIDEO:
        bad("source_deferred without Disc-extra VIDEO")
    # 10. a fatal class ends its transaction where it happened
    if d["classification_code"] != 1 and fl & (DF_ACK_WRITTEN | DF_REARM_WRITTEN):
        bad("a fatal-class record carries an ACK or a re-arm")


def _diag_v4(b, o, version=4, index=0):
    """One v4 or v5 record: the v3 half at the same offsets plus the follow-up block.
    The LAYOUT is identical; what differs is how strictly the fields must agree."""
    d = _diag(b, o)
    d["delta"] = _u16(b, o + 0x60)
    d["disc_extra_sources"] = _u16(b, o + 0x62)
    d["majority_extra_sources"] = _u16(b, o + 0x64)
    d["classification_code"] = _u16(b, o + 0x66)
    d["classification"] = CLASS_NAMES.get(d["classification_code"], "?")
    d["authoritative_value"] = _u16(b, o + 0x68)
    d["ack_value"] = _u16(b, o + 0x6A)
    d["service_selected"] = _u16(b, o + 0x6C)
    d["record_flags"] = _u16(b, o + 0x6E)
    d["t_ack"] = _u64(b, o + 0x70)
    d["t_rearm"] = _u64(b, o + 0x78)
    d["t_next_cause"] = _u64(b, o + 0x80)
    d["next_pending_gbi"] = _u16(b, o + 0x88)
    d["next_pending_disc"] = _u16(b, o + 0x8A)
    d["followup_state_code"] = b[o + 0x8C]
    d["followup_state"] = FU_NAMES.get(d["followup_state_code"], "?")
    d["followup_reason_code"] = b[o + 0x8D]
    d["followup_reason"] = FUR_NAMES.get(d["followup_reason_code"], "?")
    d["payload_source"] = _u16(b, o + 0x8E)
    d["payload_crc32"] = _u32(b, o + 0x90)
    d["payload_first_word"] = _u32(b, o + 0x94)
    d["gap_min_before_ticks"] = _u32(b, o + 0x98)
    d["gap_count_before"] = _u16(b, o + 0x9C)
    if any(b[o + 0x9E:o + DIAG_REC_V4]):
        raise ValueError("v%u record reserved bytes are not zero" % version)
    # The same rules the C parser applies, so neither can accept what the other refuses.
    # service_written (0x0100) exists only in v5; a v4 file keeps bits 8..15 zero.
    allowed = RECORD_FLAGS_ALL_V5 if version == 5 else RECORD_FLAGS_ALL
    if d["record_flags"] & ~allowed:
        raise ValueError("unknown record flag bit set (%04x)" % d["record_flags"])
    if d["classification_code"] not in CLASS_NAMES:
        raise ValueError("invalid classification %u" % d["classification_code"])
    if d["followup_state_code"] == 0 or d["followup_state_code"] not in FU_NAMES:
        raise ValueError("invalid follow-up state %u (FU_PENDING may never be serialized)"
                         % d["followup_state_code"])
    if d["followup_reason_code"] not in FUR_NAMES:
        raise ValueError("invalid follow-up reason %u" % d["followup_reason_code"])
    if d["payload_source"] not in (0, 0x0100, 0x0400):
        raise ValueError("invalid payload source %04x" % d["payload_source"])
    if (d["record_flags"] & 0x0002) and d["payload_source"] == 0:
        raise ValueError("payload_valid with no payload source")
    if (d["record_flags"] & 0x0001) and d["followup_state_code"] not in (1, 2):
        raise ValueError("followup_filled with state %s" % d["followup_state"])
    if d["gap_count_before"] == 0 and d["gap_min_before_ticks"] != GAP_NONE:
        raise ValueError("gap sentinel expected when gap_count_before is 0")
    d["flag_names"] = [n for m, n in RECORD_FLAG_NAMES if d["record_flags"] & m]
    # PER SOURCE BIT, derived from two stored fields and never from the aggregate
    # state: an event can omit more than one source, and "present" must never be
    # read as "all of them came back" unless it really was all of them.
    next_sources = d["next_pending_gbi"] & SRC_MASK
    d["followup_present_sources"] = d["disc_extra_sources"] & next_sources
    d["followup_absent_sources"] = d["disc_extra_sources"] & ~next_sources & 0xFFFF
    d["followup_partial"] = bool(d["followup_present_sources"]) and bool(d["followup_absent_sources"])
    # derived, never stored: a second source of truth can go inconsistent
    d["next_delta"] = d["next_pending_gbi"] ^ d["next_pending_disc"]
    d["rearm_to_next_ticks"] = (d["t_next_cause"] - d["t_rearm"]
                                if (d["record_flags"] & 0x0080) and d["followup_state_code"] in (1, 2)
                                else None)
    d["version"] = version
    if version == 5:
        _validate_v5(d, index)
    return d


def _semantic(b, o):
    """The fixed 1024-byte aggregate block."""
    if _u32(b, o) != SEMANTIC_TAG:
        raise ValueError("semantic block tag missing")
    if _u16(b, o + 4) != SEMANTIC_VERSION:
        raise ValueError("unsupported semantic block version %u" % _u16(b, o + 4))
    flags = _u16(b, o + 6)
    if flags & ~DIAGF_ALL:
        raise ValueError("unknown semantic block flag set (%04x)" % flags)
    if any(b[o + 0x05C:o + 0x070]):
        raise ValueError("semantic block reserved bytes are not zero")
    m = {"store_capped": bool(flags & 0x0001)}
    for i, name in enumerate(SEM_COUNTERS):
        m[name] = _u32(b, o + 0x008 + 4 * i)
    m["gaps"] = []
    for i, bit in enumerate(GAP_SLOT_BITS):
        g = o + 0x070 + 24 * i
        if _u16(b, g) != bit:
            raise ValueError("gap slot %u describes %04x, expected %04x" % (i, _u16(b, g), bit))
        if any(b[g + 2:g + 4]) or any(b[g + 0x14:g + 0x18]):
            raise ValueError("gap slot reserved bytes are not zero")
        slot = {"source": bit, "count": _u32(b, g + 4), "min_ticks": _u32(b, g + 8),
                "max_ticks": _u32(b, g + 12), "last_ticks": _u32(b, g + 16)}
        if slot["count"] == 0 and slot["min_ticks"] != GAP_NONE:
            raise ValueError("gap slot %04x has no samples but a minimum" % bit)
        m["gaps"].append(slot)
    m["delta_hist"] = [_u32(b, o + 0x100 + 4 * i) for i in range(64)]
    m["disc_extra_hist"] = [_u32(b, o + 0x200 + 4 * i) for i in range(64)]
    m["majority_extra_hist"] = [_u32(b, o + 0x300 + 4 * i) for i in range(64)]
    return m


def hist_index(v):
    """The six source bits compressed to six index bits: source bit 2k -> index bit k."""
    return sum(((v >> (2 * k)) & 1) << k for k in range(6))


def read_disc(raw):
    """The Start-up Disc reading: the LAST replica, bytes 0x1D and 0x1F. Nothing else."""
    return (raw[0x1D] << 8) | raw[0x1F]


def majority_byte(values):
    """GBI's vote, BITWISE over n samples: a bit is 1 only when strictly more than half carry it,
    so a tie resolves to 0 and the result need not equal any sample that was actually read."""
    out = 0
    n = len(values)
    for bit in range(8):
        if sum((v >> bit) & 1 for v in values) > n // 2:
            out |= 1 << bit
    return out


def read_gbi(raw):
    hi = [raw[4 * k + 1] for k in range(8)]
    lo = [raw[4 * k + 3] for k in range(8)]
    return (majority_byte(hi) << 8) | majority_byte(lo)


def explain_diag(d):
    """Explains a disagreement from the 32 preserved bytes alone. Recomputes both readings and
    checks them against the values the runtime persisted; a mismatch is reported as an
    inconsistency, never smoothed over. States no physical cause."""
    raw = d["raw"]
    out = {"cycle": d["cycle"], "read": d["read_kind"], "t": d["t"], "attempts": d["attempts"],
           "raw_hex": "".join("%02x" % b for b in raw),
           "stored_disc": d["disc_value"], "stored_gbi": d["gbi_value"]}
    out["recomputed_disc"] = read_disc(raw)
    out["recomputed_gbi"] = read_gbi(raw)
    out["consistent"] = (out["recomputed_disc"] == d["disc_value"] and
                         out["recomputed_gbi"] == d["gbi_value"])
    reps = []
    for k in range(8):
        reps.append({"replica": k,
                     "bytes": ["%02x" % raw[4 * k + j] for j in range(4)],
                     "value_if_this_replica": (raw[4 * k + 1] << 8) | raw[4 * k + 3],
                     "consumed": "%02x%02x" % (raw[4 * k + 1], raw[4 * k + 3]),
                     "discarded": "%02x %02x" % (raw[4 * k], raw[4 * k + 2])})
    out["replicas"] = reps
    hi = [raw[4 * k + 1] for k in range(8)]
    lo = [raw[4 * k + 3] for k in range(8)]
    out["majority_high"] = majority_byte(hi)
    out["majority_low"] = majority_byte(lo)
    # which consumed bytes differ from the majority, and which replicas they belong to
    odd_hi = [k for k in range(8) if hi[k] != out["majority_high"]]
    odd_lo = [k for k in range(8) if lo[k] != out["majority_low"]]
    out["replicas_differing_high"] = odd_hi
    out["replicas_differing_low"] = odd_lo
    out["disc_replica"] = 7
    out["disc_high_differs"] = 7 in odd_hi
    out["disc_low_differs"] = 7 in odd_lo
    out["differing_bits"] = out["recomputed_disc"] ^ out["recomputed_gbi"]
    # the bytes neither reading consumes, for comparison with the historical record
    out["discarded_bytes_differing"] = [
        4 * k + j for k in range(8) for j in (0, 2)
        if raw[4 * k + j] != majority_byte([raw[4 * i + j] for i in range(8)])]
    return out


def producer_warnings(d):
    """Cross-field checks that the v4 parser deliberately does NOT enforce.

    OGBPSEQ1 v4 is historical and physically executed; making these fatal would
    turn a real capture into a parse failure. They are reported instead, so an
    analysis can see that a record's current-cycle fields do not belong to the
    cycle that opened it. Returns a list of (record index, code, detail).

    The known producer defect of build vstate-0003: gbp_vstate_diag_service/_ack/
    _rearm address the newest record and run on every service cycle, so a record
    keeps absorbing later cycles until the next disagreement opens a new one.
    """
    out = []
    if d["version"] != 4:
        return out
    for i, g in enumerate(d.get("diags") or []):
        if (g["record_flags"] & 0x0040) and g["followup_state_code"] in (1, 2) and g["t_ack"] > g["t_next_cause"]:
            out.append((i, "ack_after_next_cause",
                        "t_ack %#x is later than t_next_cause %#x" % (g["t_ack"], g["t_next_cause"])))
        if g["read_kind"] in ("READ", "PRESVC") and \
           (g["authoritative_value"] & SRC_MASK) != (g["gbi_value"] & SRC_MASK):
            out.append((i, "authority_not_majority",
                        "authoritative sources %04x are not the GBI majority %04x"
                        % (g["authoritative_value"] & SRC_MASK, g["gbi_value"] & SRC_MASK)))
        if (g["record_flags"] & 0x0080) and g["followup_state_code"] in (1, 2) and g["t_rearm"] > g["t_next_cause"]:
            out.append((i, "rearm_after_next_cause",
                        "t_rearm %#x is later than t_next_cause %#x" % (g["t_rearm"], g["t_next_cause"])))
    return out


def diag_text_v4(d):
    """Every preserved record of a v4 file, plus the aggregates. States what was
    observed; asserts no physical cause."""
    out = []
    m = d["semantic"]
    out.append("semantic coherence: %u disagreement(s) — %u source_serviced, %u source_other, %u non_source"
               % (m["disagreements_total"], m["source_serviced"], m["source_other"], m["non_source"]))
    out.append("  directions: %u disc-extra, %u majority-extra, %u both; services: %u VIDEO, %u AUDIO"
               % (m["disc_extra_events"], m["majority_extra_events"], m["both_direction_events"],
                  m["majority_extra_video_services"], m["majority_extra_audio_services"]))
    out.append("  frames: %u quarantined, %u marked source-deferred" % (m["frames_quarantined"],
                                                                        m["frames_source_deferred"]))
    out.append("  records: %u preserved, %u not preserved%s"
               % (m["diagnostics_preserved"], m["diagnostics_not_preserved"],
                  "  (STORE CAPPED)" if m["store_capped"] else ""))
    out.append("  follow-up: %u present, %u absent, %u no-next, %u unknown"
               % (m["followup_present"], m["followup_absent"], m["followup_no_next"],
                  m["followup_unknown"]))
    gaps = [g for g in m["gaps"] if g["count"]]
    if gaps:
        out.append("  cause->cause gaps measured in this run (data, NOT a bound on anything):")
        for g in gaps:
            out.append("    source %04x  n=%-6u min=%-10u max=%-10u last=%u"
                       % (g["source"], g["count"], g["min_ticks"], g["max_ticks"], g["last_ticks"]))
    out.append("")
    for i, g in enumerate(d["diags"]):
        out.append("record %u: cycle %u, read %s, class %s, t=%#x" % (i, g["cycle"], g["read_kind"],
                                                                      g["classification"], g["t"]))
        out.append("  raw 32 bytes: %s" % "".join("%02x" % b for b in g["raw"]))
        out.append("  disc=%04x gbi=%04x delta=%04x  disc-extra=%04x majority-extra=%04x"
                   % (g["disc_value"], g["gbi_value"], g["delta"], g["disc_extra_sources"],
                      g["majority_extra_sources"]))
        out.append("  authoritative=%04x ack=%s serviced=%04x  flags: %s"
                   % (g["authoritative_value"],
                      "%04x" % g["ack_value"] if g["record_flags"] & 0x0040 else "not written",
                      g["service_selected"], ", ".join(g["flag_names"]) or "none"))
        e = explain_diag(g)
        out.append("  recomputed from the bytes: disc=%04x gbi=%04x  consistent: %s"
                   % (e["recomputed_disc"], e["recomputed_gbi"], e["consistent"]))
        if not e["consistent"]:
            out.append("  INCONSISTENT: do not use this record until that is explained.")
        out.append("  follow-up: %s%s" % (g["followup_state"],
                                          "" if g["followup_reason"] == "-" else " (%s)" % g["followup_reason"]))
        if g["followup_state_code"] in (1, 2):
            gap = ("%u" % g["gap_min_before_ticks"]) if g["gap_count_before"] else "no statistic yet"
            ratio = ""
            if g["gap_count_before"] and g["rearm_to_next_ticks"]:
                ratio = "  (%.1fx the smallest gap seen so far)" % (
                    g["gap_min_before_ticks"] / float(g["rearm_to_next_ticks"]))
            out.append("    the omitted source %s in the next cause; re-arm -> next cause = %s ticks%s"
                       % ("WAS present" if g["followup_state_code"] == 1 else "was NOT present",
                          g["rearm_to_next_ticks"], ratio))
            out.append("    smallest gap previously measured for that source: %s ticks (n=%u)"
                       % (gap, g["gap_count_before"]))
            out.append("    PRESENT means EVERY omitted source was in the next authoritative set;")
            out.append("    anything less is ABSENT, which includes the partial case.")
            out.append("    per source bit: present %04x, absent %04x%s"
                       % (g["followup_present_sources"], g["followup_absent_sources"],
                          "   <-- PARTIAL: some came back and some did not"
                          if g["followup_partial"] else ""))
            out.append("    presence proves the source was observed AFTER the re-arm. It does not")
            out.append("    prove it is the same assertion, and this tool does not claim it is.")
            out.append("    the next read's own Disc value was %04x; it is preserved but never"
                       % g["next_pending_disc"])
            out.append("    decides this, and a next read of its own fatal class must be read")
            out.append("    with its own classification in hand.")
        if g["record_flags"] & 0x0002:
            out.append("  payload served only by the majority: source %04x crc32 %08x first word %08x"
                       % (g["payload_source"], g["payload_crc32"], g["payload_first_word"]))
            out.append("    SUSPECT: this data must not be used as scientific evidence.")
        out.append("")
    w = producer_warnings(d)
    if w:
        out.append("PRODUCER WARNINGS (%d): this file's current-cycle fields do not all belong to"
                   % len(w))
        out.append("the cycle that opened their record. The file is structurally valid and its CRCs")
        out.append("verify; this is an attribution defect of the writer, not corruption.")
        for i, code, detail in w[:12]:
            out.append("  record %-3d %-24s %s" % (i, code, detail))
        if len(w) > 12:
            out.append("  ... and %d more" % (len(w) - 12))
        out.append("Fields that remain trustworthy: everything written at open (raw32, disc, gbi,")
        out.append("delta, extras, classification, context, gap snapshot) and everything written")
        out.append("through the follow-up handle (t_next_cause, next_pending_*, followup_*).")
        out.append("")
    out.append("This describes WHAT was observed. It asserts no physical cause: U-GBP-033 stays open.")
    return "\n".join(out)


def diag_text(d):
    if d["version"] in (4, 5):
        return diag_text_v4(d)
    if not d.get("diag"):
        if d["version"] != 3:
            return ("this file is format %u: the semantic-disagreement diagnostic exists only in "
                    "format 3, written by the instrumented build. The physical run of build "
                    "vstate-0001 is format 2 and did NOT preserve the bytes (U-GBP-032)." % d["version"])
        return "format 3, but no disagreement was captured in this run."
    e = explain_diag(d["diag"])
    out = ["semantic disagreement at cycle %u, read %s, t=%#x (attempts %u)"
           % (e["cycle"], e["read"], e["t"], e["attempts"]),
           "raw 32 bytes: %s" % e["raw_hex"], ""]
    out.append("the eight replicas (the window carries the 16-bit value eight times):")
    out.append("  %-3s %-14s %-9s %-9s" % ("k", "bytes", "consumed", "discarded"))
    for r in e["replicas"]:
        mark = ""
        if r["replica"] in e["replicas_differing_high"] or r["replica"] in e["replicas_differing_low"]:
            mark = "  <-- differs from the majority on a CONSUMED byte"
        out.append("  %-3d %-14s %-9s %-9s%s"
                   % (r["replica"], " ".join(r["bytes"]), r["consumed"], r["discarded"], mark))
    out += ["",
            "Start-up Disc reading: bytes 0x1D/0x1F (replica 7 only)  -> %04x" % e["recomputed_disc"],
            "GBI reading: bitwise majority over the eight replicas    -> %04x" % e["recomputed_gbi"],
            "  majority high byte %02x, majority low byte %02x" % (e["majority_high"], e["majority_low"]),
            "  replicas differing on the high byte: %s" % (e["replicas_differing_high"] or "none"),
            "  replicas differing on the low  byte: %s" % (e["replicas_differing_low"] or "none"),
            "  bits where the two readings differ: %04x" % e["differing_bits"],
            "",
            "bytes at offsets 4k+0 / 4k+2, which NEITHER reading consumes, that differ from their",
            "own majority: %s" % (e["discarded_bytes_differing"] or "none"),
            "  (every one of the 220 deviations logged before this build landed there)",
            ""]
    if e["consistent"]:
        out.append("the recomputed readings MATCH the values the runtime persisted: the record is")
        out.append("self-consistent and the serializer agrees with the decision that was taken.")
    else:
        out.append("INCONSISTENT: recomputed disc=%04x gbi=%04x against stored disc=%04x gbi=%04x."
                   % (e["recomputed_disc"], e["recomputed_gbi"], e["stored_disc"], e["stored_gbi"]))
        out.append("Do not use this record until that is explained.")
    out.append("")
    out.append("This describes WHAT the bytes were. It asserts no physical cause: U-GBP-032 stays open.")
    return "\n".join(out)

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
    elif cmd == "diag":
        print(diag_text(d))
    elif cmd == "semantic":
        # v4 and v5 both carry the block, at the same offset and with the same
        # layout; only the producer contract differs between them.
        if d["version"] not in (4, 5):
            print("this file is format %u: the semantic-coherence block exists only in formats 4 and 5"
                  % d["version"])
        else:
            print(json.dumps(d["semantic"], indent=1))
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
