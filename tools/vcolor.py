#!/usr/bin/env python3
"""vcolor.py — read an OGBPCOL1 sidecar and decide the GBP colour mapping.

    tools/vcolor.py info    <file>            header, caps, certification, teardown
    tools/vcolor.py frames  <file>            the frame history and why each was refused
    tools/vcolor.py diag    <file>            the R3 disagreement records, if any
    tools/vcolor.py bars    <file> [--frame N] the eight observed values, per bar
    tools/vcolor.py analyse <file> [--frame N] the whole decision, step by step
    tools/vcolor.py json    <file>            everything except the raw bytes

THIS TOOL, AND ONLY THIS TOOL, KNOWS WHAT THE STIMULUS IS. The GameCube probe
preserves three identical eligible frames without being able to recognise them;
the eight values below are the other half of the experiment, and keeping them
apart is what stops the runtime from deciding the question it is asking
(HARDWARE_TESTS §V3.11).

The decision procedure is exact and has no scoring (§V3.14, §V3.15):

  1. rebuild the 240 x 160 grid from the raw bytes, word = (b1 << 8) | b3
  2. split flag15 = word & 0x8000 from color15 = word & 0x7FFF
  3. require each of the eight 30-pixel bars to hold EXACTLY ONE color15 value
     over all 160 rows - no averaging, no majority, no tolerance
  4. apply every candidate transformation to the eight known stimulus values
  5. a hypothesis survives only if it reproduces ALL EIGHT observed values
  6. exactly one survivor is an answer; zero or several is INCONCLUSIVE, and the
     raw bytes stay preserved either way

What the eight bars can and cannot establish is reported with the result: they
pin the image of bits 0, 5 and 10 individually and of each 5-bit group as a set,
and they do NOT pin a permutation that fixes those three bits while rearranging
bits 1-4 inside a group (§V3.3, §V3.19).
"""
import hashlib
import json
import os
import struct
import sys

MAGIC = b"OGBPCOL1"
FOOTER = b"OGBPCEND"
VERSION = 1
HEADER_SIZE = 0x200
FOOTER_SIZE = 12
FRAME_REC = 48
CERT_REC = 40
DIAG_REC = 160
MAX_FRAMES = 1024
MAX_CERT = 3
MAX_DIAGS = 256
MAX_AUDIO_RAW = 3
RING_SLOTS_MAX = 4
BLOCKS = 40
BLOCK_SIZE = 0xF00
FRAME_BYTES = BLOCKS * BLOCK_SIZE
WIDTH, HEIGHT = 240, 160
BAR_W = 30
BARS = 8
ROW_STRIDE = WIDTH * 4          # 4 bytes per pixel group in the raw block
ROWS_PER_BLOCK = 4

FLAG_NAMES = [(0x0001, "service_ok"), (0x0002, "restore_ok"), (0x0004, "certified"),
              (0x0008, "hold_complete_RETIRED"), (0x0010, "partial"), (0x0020, "stage_a_aborted"),
              (0x0040, "frame_table_capped"), (0x0080, "raw_unrecoverable")]
FLAG_CERTIFIED = 0x0004
FLAG_HOLD_COMPLETE_RETIRED = 0x0008
FLAG_RAW_UNRECOVERABLE = 0x0080
RF_NAMES = [(0x0001, "restore_ok"), (0x0002, "handler_restored"), (0x0004, "mask_ok"),
            (0x0008, "control_ok"), (0x0010, "pi_sticky_final"), (0x0020, "arinfo_restore_ok"),
            (0x0040, "power_cycle_required")]
REASONS = ["eligible", "not_complete", "wrong_blocks", "anomaly", "resync",
           "majority_extra_quarantine", "source_deferred", "retired_pre_baseline",
           "ring_slot_unavailable"]
RETIRED_PRE_BASELINE = 7

# enum gbp_vstate_stop, verbatim. 10 and 11 exist so a reader never has to guess
# whether a run ran out of TIME or out of TABLE - they are different facts.
STOP_REASONS = {0: "none", 1: "nominal_negative", 2: "frame_store_cap", 3: "event_store_cap",
                4: "safety_budget", 5: "delivery_cap", 6: "no_next_cause", 7: "failure",
                8: "color_certified", 9: "color_search_window", 10: "color_frame_cap"}

# ---- the stimulus, in bar order, left to right -----------------------------
# Written by stimulus/agb-color-bars. In the AGB's own documented framebuffer
# layout (BGR555) these are black, red, green, blue, white and the least
# significant bit of red, of green and of blue - a statement about what the ROM
# STORES, never about which GBP bit is which channel.
STIMULUS = (0x0000, 0x001F, 0x03E0, 0x7C00, 0x7FFF, 0x0001, 0x0020, 0x0400)
BAR_X = tuple(range(0, WIDTH, BAR_W))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from avseq import crc32                                                # noqa: E402


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
    """Strict parser: magic, version, record sizes, header CRC, every count, the
    reserved areas, contiguous sections, the footer and the total CRC. Raises
    ValueError otherwise. Mirrors src/gbp/gbp_vcoldump.c exactly - the two must
    never disagree about what a valid file is."""
    if len(data) < HEADER_SIZE + FOOTER_SIZE or data[:8] != MAGIC:
        raise ValueError("not an OGBPCOL1 file")
    d = {"version": _u16(data, 0x008), "header_size": _u16(data, 0x00A)}
    if d["version"] != VERSION or d["header_size"] != HEADER_SIZE:
        raise ValueError("unsupported version %u / header size 0x%X" % (d["version"], d["header_size"]))
    for off, want, what in ((0x030, FRAME_REC, "frame"), (0x032, CERT_REC, "certified"),
                            (0x034, DIAG_REC, "diagnostic")):
        if _u16(data, off) != want:
            raise ValueError("unexpected %s record size %u" % (what, _u16(data, off)))
    if crc32(data[:HEADER_SIZE - 4]) != _u32(data, 0x1FC):
        raise ValueError("header CRC mismatch")
    d["header_crc32"] = _u32(data, 0x1FC)
    d["flags"] = _u32(data, 0x00C)
    if d["flags"] & ~0xFF:
        raise ValueError("unknown header flag bit set (%08x)" % d["flags"])
    if d["flags"] & FLAG_HOLD_COMPLETE_RETIRED:
        raise ValueError("the hold_complete flag is retired and must be zero")
    d["flag_names"] = _names(d["flags"], FLAG_NAMES)
    d["tb_hz"] = _u32(data, 0x010)
    d["frame_count"] = _u32(data, 0x014)
    d["cert_count"] = _u32(data, 0x018)
    d["diag_count"] = _u32(data, 0x01C)
    d["audio_raw_count"] = _u32(data, 0x020)
    d["video_block_size"] = _u32(data, 0x024)
    d["audio_block_size"] = _u32(data, 0x028)
    d["blocks_per_frame"] = _u32(data, 0x02C)
    if d["frame_count"] > MAX_FRAMES:
        raise ValueError("frame_count %u exceeds the cap" % d["frame_count"])
    if d["cert_count"] > MAX_CERT:
        raise ValueError("cert_count %u exceeds the raw budget" % d["cert_count"])
    if d["diag_count"] > MAX_DIAGS:
        raise ValueError("diag_count %u exceeds the store" % d["diag_count"])
    if d["audio_raw_count"] > MAX_AUDIO_RAW:
        raise ValueError("audio_raw_count %u exceeds the store" % d["audio_raw_count"])
    if d["video_block_size"] != BLOCK_SIZE or d["blocks_per_frame"] != BLOCKS:
        raise ValueError("this file does not describe 40 blocks of 0xF00")
    d["status_code"] = _u16(data, 0x036)
    d["stop_reason"] = _u16(data, 0x038)
    d["stop"] = STOP_REASONS.get(d["stop_reason"], "?")
    d["n_stable"] = _u16(data, 0x03A)
    d["cert_budget"] = _u16(data, 0x03C)
    d["hold_frames_cfg"] = _u16(data, 0x03E)
    if d["n_stable"] != 3 or d["cert_budget"] != MAX_CERT:
        raise ValueError("this file was not written under the versioned capture contract")
    if d["hold_frames_cfg"]:
        raise ValueError("hold_frames_cfg is retired and must be zero")
    certified = bool(d["flags"] & FLAG_CERTIFIED)
    lost = bool(d["flags"] & FLAG_RAW_UNRECOVERABLE)
    # A certified run with no raw is legal in EXACTLY one shape: the ring slots
    # did not survive to the teardown and the header says so. Anything else is a
    # file whose flags and sections disagree.
    if certified and d["cert_count"] == 0 and not lost:
        raise ValueError("the certified flag and cert_count disagree")
    if not certified and d["cert_count"] != 0:
        raise ValueError("the certified flag and cert_count disagree")
    if lost and (not certified or d["cert_count"] != 0):
        raise ValueError("raw_unrecoverable without a certified run, or next to raw")
    d["test_id"] = _id(data, 0x040)
    d["build_id"] = _id(data, 0x060)
    d["app"] = _id(data, 0x080)
    d["commit"] = _id(data, 0x0A0)
    d["off_frames"] = _u32(data, 0x0C0)
    d["off_cert"] = _u32(data, 0x0C4)
    d["off_diag"] = _u32(data, 0x0C8)
    d["off_video_raw"] = _u32(data, 0x0CC)
    d["off_audio_raw"] = _u32(data, 0x0D0)
    d["off_footer"] = _u32(data, 0x0D4)
    if any(data[0x0D8:0x0E0]) or any(data[0x1C8:0x1FC]):
        raise ValueError("reserved header bytes are not zero")
    for name, off in (("t_control_transform", 0x0E0), ("t_capture_start", 0x0E8), ("t_stop", 0x0F0),
                      ("t_certified", 0x0F8), ("t_teardown_begin", 0x100), ("t_teardown_end", 0x108),
                      ("capture_elapsed", 0x110), ("safety_elapsed", 0x118),
                      ("search_window_ticks", 0x120), ("hard_wallclock_ticks", 0x128)):
        d[name] = _u64(data, off)
    for name, off in (("max_deliveries", 0x130), ("frame_table_cap", 0x134), ("deliveries", 0x138),
                      ("video_completed", 0x13C), ("audio_drains", 0x140), ("isr_w1c", 0x144),
                      ("main_w1c", 0x148), ("frames_total", 0x14C), ("frames_eligible", 0x150),
                      ("frames_dropped", 0x154), ("runs_reset", 0x158), ("hold_frames", 0x15C),
                      ("hold_seen", 0x160), ("sig_mismatches", 0x164), ("run_len", 0x168),
                      ("run_first_index", 0x16C), ("disagreements_total", 0x194),
                      ("source_serviced", 0x198), ("source_other", 0x19C), ("non_source", 0x1A0),
                      ("diagnostics_preserved", 0x1A4), ("diagnostics_not_preserved", 0x1A8),
                      ("frames_quarantined", 0x1AC), ("frames_source_deferred", 0x1B0),
                      ("errors", 0x1B4), ("control_orig", 0x1B8), ("control_exp", 0x1BC),
                      ("restore_flags", 0x1C0), ("intmr_final", 0x1C4)):
        d[name] = _u32(data, off)
    if d["restore_flags"] & ~0x7F:
        raise ValueError("unknown restore flag bit set (%08x)" % d["restore_flags"])
    d["restore_names"] = _names(d["restore_flags"], RF_NAMES)
    d["frames_refused"] = [_u32(data, 0x170 + 4 * i) for i in range(len(REASONS))]
    if d["hold_frames"] or d["hold_seen"]:
        raise ValueError("the hold counters are retired and must be zero")
    if d["frames_refused"][RETIRED_PRE_BASELINE]:
        raise ValueError("refusal reason %u is retired and must be zero" % RETIRED_PRE_BASELINE)

    need = HEADER_SIZE
    if d["off_frames"] != need:
        raise ValueError("the frame table does not follow the header")
    need += d["frame_count"] * FRAME_REC
    if need != d["off_cert"]:
        raise ValueError("the certified table does not follow the frame table")
    need += d["cert_count"] * CERT_REC
    if need != d["off_diag"]:
        raise ValueError("the diagnostics do not follow the certified table")
    need += d["diag_count"] * DIAG_REC
    if need != d["off_video_raw"]:
        raise ValueError("the raw VIDEO section does not follow the diagnostics")
    need += d["cert_count"] * FRAME_BYTES
    if need != d["off_audio_raw"]:
        raise ValueError("the raw AUDIO section does not follow the raw VIDEO")
    need += d["audio_raw_count"] * d["audio_block_size"]
    if need != d["off_footer"]:
        raise ValueError("the footer does not follow the last section")
    if d["off_footer"] + FOOTER_SIZE != len(data):
        raise ValueError("file is truncated or has trailing bytes")
    if data[d["off_footer"]:d["off_footer"] + 8] != FOOTER:
        raise ValueError("footer magic missing")
    d["total_crc32"] = _u32(data, d["off_footer"] + 8)
    if crc32(data[:d["off_footer"]]) != d["total_crc32"]:
        raise ValueError("total CRC mismatch")

    d["frames"] = [_frame(data, d["off_frames"] + i * FRAME_REC) for i in range(d["frame_count"])]
    d["cert"] = [_cert(data, d["off_cert"] + i * CERT_REC, i) for i in range(d["cert_count"])]
    d["diags"] = [_diag(data, d["off_diag"] + i * DIAG_REC) for i in range(d["diag_count"])]
    d["_data"] = data
    return d


def _frame(b, o):
    f = {"t_first": _u64(b, o + 0x00), "t_last": _u64(b, o + 0x08), "index": _u32(b, o + 0x10),
         "blocks": _u32(b, o + 0x14), "flags": _u16(b, o + 0x18), "reason_code": _u16(b, o + 0x1A),
         "run_len_after": _u32(b, o + 0x1C), "sig0": _u32(b, o + 0x20), "sig39": _u32(b, o + 0x24)}
    if any(b[o + 0x28:o + FRAME_REC]):
        raise ValueError("frame record reserved bytes are not zero")
    if f["reason_code"] == RETIRED_PRE_BASELINE:
        raise ValueError("a frame record carries the retired refusal reason %u" % RETIRED_PRE_BASELINE)
    if f["reason_code"] >= len(REASONS):
        raise ValueError("unknown refusal reason %u" % f["reason_code"])
    f["reason"] = REASONS[f["reason_code"]]
    return f


def _cert(b, o, i):
    c = {"t_first": _u64(b, o + 0x00), "t_last": _u64(b, o + 0x08), "frame_index": _u32(b, o + 0x10),
         "blocks": _u32(b, o + 0x14), "raw_offset": _u32(b, o + 0x18),
         "ring_slot": _u16(b, o + 0x1C), "order": _u16(b, o + 0x1E),
         "sig0": _u32(b, o + 0x20), "sig39": _u32(b, o + 0x24)}
    if c["blocks"] != BLOCKS:
        raise ValueError("a certified frame must hold %u blocks, not %u" % (BLOCKS, c["blocks"]))
    if c["raw_offset"] != i * FRAME_BYTES:
        raise ValueError("certified frame %u points at 0x%X, not at its own slot" % (i, c["raw_offset"]))
    if c["order"] != i:
        raise ValueError("certified frame %u claims certification order %u" % (i, c["order"]))
    if c["ring_slot"] >= RING_SLOTS_MAX:
        raise ValueError("certified frame %u names ring slot %u" % (i, c["ring_slot"]))
    return c


def _diag(b, o):
    """The SHARED R3 record (v5 contract). Only the fields this experiment reports
    are decoded; the full contract lives in tools/vstate.py, which reads the same
    160 bytes from the vstate sidecar."""
    d = {"t": _u64(b, o + 0x00), "cycle": _u32(b, o + 0x08), "disc_value": _u16(b, o + 0x10),
         "gbi_value": _u16(b, o + 0x12), "read_kind_code": _u16(b, o + 0x14),
         "raw": list(b[o + 0x18:o + 0x38]), "delta": _u16(b, o + 0x60),
         "disc_extra_sources": _u16(b, o + 0x62), "majority_extra_sources": _u16(b, o + 0x64),
         "classification_code": _u16(b, o + 0x66), "authoritative_value": _u16(b, o + 0x68),
         "ack_value": _u16(b, o + 0x6A), "service_selected": _u16(b, o + 0x6C),
         "record_flags": _u16(b, o + 0x6E), "followup_state_code": b[o + 0x8C]}
    if any(b[o + 0x5C:o + 0x60]) or any(b[o + 0x9E:o + DIAG_REC]):
        raise ValueError("diagnostic reserved bytes are not zero")
    if d["record_flags"] & ~0x01FF:
        raise ValueError("unknown record flag bit set (%04x)" % d["record_flags"])
    if not 1 <= d["classification_code"] <= 3:
        raise ValueError("invalid classification %u" % d["classification_code"])
    if d["followup_state_code"] == 0 or d["followup_state_code"] > 4:
        raise ValueError("invalid follow-up state %u (FU_PENDING may never be serialized)"
                         % d["followup_state_code"])
    d["classification"] = {1: "source_serviced", 2: "source_other", 3: "non_source"}[d["classification_code"]]
    return d


# ---- reconstruction: raw bytes -> the 240 x 160 grid ------------------------
def frame_words(d, which=0):
    """Rebuilds one certified frame as 160 rows of 240 words, straight from the
    raw bytes. `word = (b1 << 8) | b3` is what both reference decoders consume;
    bytes 0 and 2 are preserved in the file and returned separately, never folded
    into the word (§V3.14, §V3.22)."""
    if which >= len(d["cert"]):
        raise ValueError("this file holds %u certified frame(s)" % len(d["cert"]))
    base = d["off_video_raw"] + d["cert"][which]["raw_offset"]
    data = d["_data"]
    rows, b1_rows, b3_rows, other_rows = [], [], [], []
    for block in range(BLOCKS):
        boff = base + block * BLOCK_SIZE
        for r in range(ROWS_PER_BLOCK):
            roff = boff + r * ROW_STRIDE
            row, b1s, b3s, others = [], [], [], []
            for x in range(WIDTH):
                g = roff + x * 4
                b0, b1, b2, b3 = data[g], data[g + 1], data[g + 2], data[g + 3]
                row.append((b1 << 8) | b3)
                b1s.append(b1)
                b3s.append(b3)
                others.append((b0, b2))
            rows.append(row)
            b1_rows.append(b1s)
            b3_rows.append(b3s)
            other_rows.append(others)
    if len(rows) != HEIGHT:
        raise ValueError("reconstructed %u rows, expected %u" % (len(rows), HEIGHT))
    return {"words": rows, "b1": b1_rows, "b3": b3_rows, "discarded": other_rows}


def split_flag(word):
    """flag15 and color15, kept apart for the whole analysis (§V3.16/§27)."""
    return word & 0x8000, word & 0x7FFF


def bar_values(grid):
    """For each of the eight 30-pixel bars, the set of color15 values over all 160
    rows. EXACT uniformity is required: one value per bar, or the run is
    inconclusive and the offenders are reported with coordinates."""
    out = []
    for b in range(BARS):
        x0 = BAR_X[b]
        seen = {}
        first_bad = None
        for y in range(HEIGHT):
            for x in range(x0, x0 + BAR_W):
                c = grid["words"][y][x] & 0x7FFF
                if c not in seen:
                    seen[c] = {"count": 0, "first": (x, y)}
                seen[c]["count"] += 1
        if len(seen) > 1 and first_bad is None:
            # the first coordinate holding anything other than the most common value
            main = max(seen.items(), key=lambda kv: kv[1]["count"])[0]
            for y in range(HEIGHT):
                for x in range(x0, x0 + BAR_W):
                    if (grid["words"][y][x] & 0x7FFF) != main:
                        first_bad = (x, y)
                        break
                if first_bad:
                    break
        out.append({"bar": b, "x0": x0, "x1": x0 + BAR_W - 1,
                    "values": {v: info["count"] for v, info in sorted(seen.items())},
                    "uniform": len(seen) == 1,
                    "value": next(iter(seen)) if len(seen) == 1 else None,
                    "first_divergence": first_bad,
                    "b1": grid["b1"][0][x0], "b3": grid["b3"][0][x0]})
    return out


def flag_map(grid):
    """Where bit 15 is set. The stimulus never writes it, so every coordinate here
    is something the path added (§V3.4)."""
    coords, per_block = [], [0] * BLOCKS
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if grid["words"][y][x] & 0x8000:
                per_block[y // ROWS_PER_BLOCK] += 1
                if len(coords) < 64:
                    coords.append((x, y))
    total = sum(per_block)
    first_word_of_block0 = bool(grid["words"][0][0] & 0x8000)
    return {"total": total, "per_block": per_block, "coords": coords,
            "first_word_of_block0": first_word_of_block0,
            "only_first_word": total == 1 and first_word_of_block0}


# ---- the candidate transformations -----------------------------------------
def _swap_outer(v):
    """H1: the two outer 5-bit groups exchanged, the middle one untouched."""
    return ((v & 0x001F) << 10) | (v & 0x03E0) | ((v >> 10) & 0x001F)


def _identity(v):
    """H2: the AGB framebuffer value carried through verbatim."""
    return v & 0x7FFF


def _byte_swap(v):
    """H3: the two consumed bytes exchanged before the word is assembled."""
    return (((v & 0xFF) << 8) | ((v >> 8) & 0xFF)) & 0x7FFF


def _reverse_group(g):
    return ((g & 1) << 4) | ((g & 2) << 2) | (g & 4) | ((g & 8) >> 2) | ((g & 16) >> 4)


def _intra_reverse(v):
    """H4: inside each 5-bit group, bit k -> bit 4-k."""
    return (_reverse_group((v >> 10) & 0x1F) << 10) | \
           (_reverse_group((v >> 5) & 0x1F) << 5) | _reverse_group(v & 0x1F)


def _complement(v):
    """H5: every colour bit inverted."""
    return (~v) & 0x7FFF


HYPOTHESES = (
    ("H2_identity", "the AGB framebuffer value, verbatim", _identity),
    ("H1_outer_group_swap", "the two outer 5-bit groups exchanged", _swap_outer),
    ("H3_byte_swap", "the two consumed bytes exchanged", _byte_swap),
    ("H4_intra_group_reversal", "bit k -> bit 4-k inside each group", _intra_reverse),
    ("H5_complement", "every colour bit inverted", _complement),
    ("H1_H4", "outer groups exchanged AND each group reversed",
     lambda v: _intra_reverse(_swap_outer(v))),
    ("H1_H3", "outer groups exchanged AND the bytes swapped",
     lambda v: _byte_swap(_swap_outer(v))),
)


def expected_vectors():
    """The eight values each hypothesis predicts, for the report."""
    return [{"name": n, "what": w, "expected": [f(v) for v in STIMULUS]} for n, w, f in HYPOTHESES]


def evaluate(observed):
    """Exact comparison, eight values, no score and no distance (§V3.15/§32)."""
    out = []
    for name, what, fn in HYPOTHESES:
        expected = [fn(v) for v in STIMULUS]
        matches = [e == o for e, o in zip(expected, observed)]
        out.append({"name": name, "what": what, "expected": expected,
                    "matches": matches, "all": all(matches),
                    "first_mismatch": None if all(matches) else matches.index(False)})
    return out


def certified_raw_equal(d):
    """THE gate of §V3.25, and the reason the runtime is allowed to be cheap.

    The probe decides its window from `sig[40]`, 160 bytes of per-block checksum
    that the state model computes anyway. That is a RUNTIME decision - "three
    signature-identical eligible frames" - and it is not the scientific claim. A
    checksum can collide; the bytes cannot. So before one pixel is interpreted,
    the three certified frames are compared here, byte for byte, 153 600 bytes
    each, offline, where a full-frame comparison delays no hardware.

    Returns {"ok", "n", "first_diff", "why"}. `ok` is True only for exactly three
    frames that are all exactly equal."""
    raws = [raw_frame(d, i) for i in range(len(d["cert"]))]
    r = {"n": len(raws), "first_diff": None, "ok": False, "why": ""}
    if len(raws) != MAX_CERT:
        r["why"] = ("%u certified raw frame(s) are present; the design certifies on %u and the "
                    "byte-exact check needs all of them" % (len(raws), MAX_CERT))
        return r
    for k in (1, 2):
        if raws[k] != raws[0]:
            for j in range(FRAME_BYTES):
                if raws[k][j] != raws[0][j]:
                    block = j // BLOCK_SIZE
                    inblock = j % BLOCK_SIZE
                    row = inblock // ROW_STRIDE
                    r["first_diff"] = {
                        "pair": (0, k), "offset": j, "block": block,
                        # the coordinate is derivable from the geometry alone, so
                        # it is reported: a difference at a known (x, y) is a very
                        # different finding from one in a discarded byte
                        "x": (inblock % ROW_STRIDE) // 4,
                        "y": block * ROWS_PER_BLOCK + row,
                        "byte_in_group": j % 4,
                        "consumed": (j % 4) in (1, 3),
                        "a": raws[0][j], "b": raws[k][j]}
                    break
            r["why"] = ("certified frames A and %s are NOT byte-identical, so the runtime's "
                        "signature agreement was not byte agreement" % "ABC"[k])
            return r
    r["ok"] = True
    return r


def raw_frame(d, which):
    """One certified frame's raw bytes, exactly as the file carries them."""
    if which >= len(d["cert"]):
        raise ValueError("this file holds %u certified frame(s)" % len(d["cert"]))
    base = d["off_video_raw"] + d["cert"][which]["raw_offset"]
    return d["_data"][base:base + FRAME_BYTES]


def analyse(d, which=0):
    """The whole decision for one certified frame. Returns a verdict of
    `resolved`, `inconclusive_*` or `no_certified_frame`, and never a guess."""
    out = {"frame": which, "stimulus": list(STIMULUS), "bar_x": list(BAR_X)}
    if not d["cert"]:
        out["verdict"] = "no_certified_frame"
        out["why"] = ("the run preserved no certified frame; nothing here can be decided and the "
                      "sidecar says why in its refusal counters")
        if d["flags"] & FLAG_RAW_UNRECOVERABLE:
            out["why"] = ("the run CERTIFIED but its ring slots did not survive to the teardown, "
                          "so the file carries no raw and claims none (raw_unrecoverable)")
        return out
    # §V3.25: byte equality first, mapping second. Never the other way round.
    eq = certified_raw_equal(d)
    out["certified_raw_equal"] = eq
    if not eq["ok"]:
        out["verdict"] = "inconclusive_certified_raw_mismatch"
        out["why"] = eq["why"]
        return out
    grid = frame_words(d, which)
    bars = bar_values(grid)
    out["bars"] = bars
    out["flag15"] = flag_map(grid)

    nonuniform = [b for b in bars if not b["uniform"]]
    if nonuniform:
        out["verdict"] = "inconclusive_bar_not_uniform"
        out["why"] = ("bar %d holds %d distinct colour values; the mapping is an exact comparison "
                      "or it is nothing, so no averaging and no majority is applied"
                      % (nonuniform[0]["bar"], len(nonuniform[0]["values"])))
        return out

    observed = [b["value"] for b in bars]
    out["observed"] = observed
    out["hypotheses"] = evaluate(observed)
    survivors = [h for h in out["hypotheses"] if h["all"]]
    out["survivors"] = [h["name"] for h in survivors]

    # orientation: the two bars that survive every bit permutation must sit where
    # the stimulus put them, or the analyser is reading x mirrored (§V3.5/§30)
    out["orientation"] = {
        "zero_bar": [b["bar"] for b in bars if b["value"] == 0x0000],
        "all_ones_bar": [b["bar"] for b in bars if b["value"] == 0x7FFF],
        "expected_zero_bar": 0, "expected_all_ones_bar": 4,
    }
    out["orientation"]["consistent"] = (out["orientation"]["zero_bar"] == [0] and
                                        out["orientation"]["all_ones_bar"] == [4])
    mirrored = [b["value"] for b in reversed(bars)]
    out["orientation"]["mirror_would_fit"] = any(
        all(f(v) == o for v, o in zip(STIMULUS, mirrored)) for _, _, f in HYPOTHESES)

    if len(survivors) == 1:
        out["verdict"] = "resolved"
        out["mapping"] = survivors[0]["name"]
        out["what"] = survivors[0]["what"]
    elif not survivors:
        out["verdict"] = "inconclusive_no_hypothesis"
        out["why"] = ("no candidate transformation reproduces all eight observed values. The raw "
                      "bytes are preserved; this is a new unknown, not a licence to pick the "
                      "closest fit")
    else:
        out["verdict"] = "inconclusive_ambiguous"
        out["why"] = ("%d hypotheses reproduce all eight values; the stimulus did not discriminate "
                      "them and must be refined (§V3.19)" % len(survivors))

    # what the eight bars can and cannot establish, stated with the result
    out["limits"] = [
        "the eight bars pin the image of bits 0, 5 and 10 individually and of each 5-bit group "
        "as a set",
        "they do NOT pin a permutation that fixes bits 0, 5 and 10 and rearranges only bits 1-4 "
        "inside a group; no reference suggests one, and §V3.19 holds the pattern that would "
        "close it",
        "this is evidence about AGB video mode 3 on the path this run exercised, and about "
        "nothing else",
    ]
    return out


def reference_comparison(mapping):
    """How the physical result sits against the two reference decoders. Stated
    after the measurement, never used to choose it (§V3.18)."""
    both = ("Both references read the word as (b1 << 8) | b3, force bit 15 and treat bits 14-10 "
            "as R: the Disc draws a GX_TF_RGB5A3 texture, GBI writes RGB5A3 tiles and its PNG "
            "writer maps bits 14-10 to R (VIDEO_PATH §2.3, §3.2).")
    if mapping == "H1_outer_group_swap":
        return [both, "The path exchanges the outer groups relative to AGB VRAM, so the references' "
                      "reading is the displayed truth and the Disc's embedded idle frame renders "
                      "as its author intended."]
    if mapping == "H2_identity":
        return [both, "The GBP hands the AGB framebuffer value through unchanged, so the references "
                      "render AGB red as blue and blue as red. That is a claim about a display "
                      "convention and it is checked against the Disc's own embedded frame, decoded "
                      "both ways side by side, before it is called anything (§V3.18)."]
    return [both, "The measured transformation is neither of the two readings the references "
                  "implement. Preserve, report, and open an unknown - a divergence is documented "
                  "as a divergence, never called a bug in a reference without the analysis that "
                  "earns the word."]


def info_text(d):
    tb = d["tb_hz"] or 1
    def secs(t):
        return "%u.%03u" % (t // tb, (t % tb) * 1000 // tb)
    out = ["file: OGBPCOL1 v%u  test=%s build=%s app=%s commit=%s"
           % (d["version"], d["test_id"], d["build_id"], d["app"], d["commit"]),
           "flags: %s" % (", ".join(d["flag_names"]) or "-"),
           "stop: %s (%u)   status_code=%u   tb_hz=%u"
           % (d["stop"], d["stop_reason"], d["status_code"], d["tb_hz"]),
           "",
           "capture: %s s   safety %s s of %s s   search window %s s"
           % (secs(d["capture_elapsed"]), secs(d["safety_elapsed"]),
              secs(d["hard_wallclock_ticks"]), secs(d["search_window_ticks"])),
           "service: deliveries=%u video=%u audio=%u isr_w1c=%u main_w1c=%u errors=%u"
           % (d["deliveries"], d["video_completed"], d["audio_drains"], d["isr_w1c"],
              d["main_w1c"], d["errors"]),
           "frames:  %u recorded (%u eligible, %u dropped past the table cap), runs reset %u"
           % (d["frames_total"], d["frames_eligible"], d["frames_dropped"], d["runs_reset"]),
           "refused: " + ", ".join("%s=%u" % (REASONS[i], d["frames_refused"][i])
                                   for i in range(1, len(REASONS)) if d["frames_refused"][i]) or "refused: none",
           "certified: %s  %u frame(s), %u bytes of raw   run_len=%u first_index=%u"
           % ("YES" if d["cert_count"] else "no", d["cert_count"],
              d["cert_count"] * FRAME_BYTES, d["run_len"], d["run_first_index"]),
           "runtime stability: sig[40], %u run(s) broken by a signature change; "
           "byte equality is decided here, offline" % d["sig_mismatches"],
           "certified slots: " + (", ".join("%s=ring%u(frame %u)" % ("ABC"[c["order"]], c["ring_slot"],
                                                                    c["frame_index"]) for c in d["cert"])
                                  or "none"),
           "R3: %u disagreement(s) - %u serviced, %u other, %u non-source; %u preserved, %u not; "
           "%u frame(s) quarantined, %u source-deferred"
           % (d["disagreements_total"], d["source_serviced"], d["source_other"], d["non_source"],
              d["diagnostics_preserved"], d["diagnostics_not_preserved"],
              d["frames_quarantined"], d["frames_source_deferred"]),
           "CONTROL: orig=%02x exp=%02x   restore: %s   INTMR final=%08x"
           % (d["control_orig"], d["control_exp"], ", ".join(d["restore_names"]) or "-",
              d["intmr_final"]),
           "",
           "THE COLOUR MAPPING IS NOT IN THIS FILE. It is decided offline from the raw bytes by",
           "`tools/vcolor.py analyse`; the sidecar carries evidence, never a conclusion."]
    return "\n".join(out)


def analyse_text(d, which=0):
    a = analyse(d, which)
    out = ["GBP-VIDEO-003 colour mapping, certified frame %u of %u" % (which, len(d["cert"])), ""]
    if a["verdict"] == "no_certified_frame":
        out += ["VERDICT: NO CERTIFIED FRAME", "  " + a["why"]]
        return "\n".join(out)
    if a["verdict"] == "inconclusive_certified_raw_mismatch":
        eq = a["certified_raw_equal"]
        out += ["VERDICT: INCONCLUSIVE - CERTIFIED RAW MISMATCH", "  " + a["why"]]
        if eq["first_diff"]:
            fd = eq["first_diff"]
            out.append("  first difference: frames %s and %s at byte 0x%X — block %u, x=%u y=%u, "
                       "byte %u of the group (%s), %02x vs %02x"
                       % ("ABC"[fd["pair"][0]], "ABC"[fd["pair"][1]], fd["offset"], fd["block"],
                          fd["x"], fd["y"], fd["byte_in_group"],
                          "consumed by the word" if fd["consumed"] else "discarded by both decoders",
                          fd["a"], fd["b"]))
        out += ["", "  The runtime decides its window from sig[40], which is a 160-byte checksum "
                    "vector, not the bytes. This is what that distinction is FOR: the probe agreed, "
                    "the bytes did not, and no colour mapping is attempted."]
        return "\n".join(out)
    out.append("the certified raw frames are byte-for-byte equal (%u x %u bytes), so the window "
               "the runtime found by signature really is one picture." % (MAX_CERT, FRAME_BYTES))
    out.append("")
    out.append("the eight bars, as the RAW bytes give them:")
    out.append("  bar   x range    stimulus   observed color15   flag15   b1 b3   uniform")
    for b in a["bars"]:
        obs = "%04x" % b["value"] if b["uniform"] else "%d values" % len(b["values"])
        out.append("  %d     %3u..%3u    %04x       %-16s   %s      %02x %02x   %s"
                   % (b["bar"], b["x0"], b["x1"], STIMULUS[b["bar"]], obs,
                      "see map", b["b1"], b["b3"], "yes" if b["uniform"] else "NO"))
    if not a.get("observed"):
        out += ["", "VERDICT: INCONCLUSIVE - " + a["why"]]
        if a["bars"]:
            bad = [b for b in a["bars"] if not b["uniform"]]
            for b in bad[:3]:
                out.append("  bar %d first divergence at (x=%s, y=%s), values: %s"
                           % (b["bar"], b["first_divergence"][0], b["first_divergence"][1],
                              ", ".join("%04x x%u" % (v, c) for v, c in b["values"].items())))
        return "\n".join(out)

    out += ["", "every candidate transformation, applied to the eight known stimulus values:"]
    for h in a["hypotheses"]:
        out.append("  %-24s %s   %s" % (h["name"], " ".join("%04x" % v for v in h["expected"]),
                                        "ALL EIGHT MATCH" if h["all"]
                                        else "no (first mismatch at bar %d)" % h["first_mismatch"]))
    out += ["", "  observed                 " + " ".join("%04x" % v for v in a["observed"])]
    out += ["", "orientation: the popcount-0 bar is bar %s and the all-ones bar is bar %s "
            "(expected 0 and 4): %s" % (a["orientation"]["zero_bar"], a["orientation"]["all_ones_bar"],
                                        "consistent" if a["orientation"]["consistent"] else "MIRRORED OR WRONG"),
            "             a mirrored reading would %s fit a candidate"
            % ("ALSO" if a["orientation"]["mirror_would_fit"] else "not")]
    f = a["flag15"]
    out += ["", "bit 15, which the stimulus never writes: %u pixel(s) carry it%s"
            % (f["total"], "; only the first word of block 0" if f["only_first_word"]
               else (", first at %s" % (f["coords"][0],) if f["coords"] else "")),
            "             per block: " + " ".join(str(n) for n in f["per_block"][:8]) + " ..."]
    out += [""]
    if a["verdict"] == "resolved":
        out += ["VERDICT: RESOLVED - %s (%s)" % (a["mapping"], a["what"]), ""]
        out += ["against the references:"] + ["  " + line for line in reference_comparison(a["mapping"])]
    else:
        out += ["VERDICT: INCONCLUSIVE - " + a["why"]]
    out += ["", "what this does and does not establish:"] + ["  - " + l for l in a["limits"]]
    return "\n".join(out)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd, path = argv[1], argv[2]
    which = int(argv[argv.index("--frame") + 1]) if "--frame" in argv else 0
    with open(path, "rb") as f:
        d = parse(f.read())
    if cmd == "info":
        print(info_text(d))
    elif cmd == "frames":
        print("%-6s %-8s %-8s %-26s %s" % ("index", "blocks", "flags", "reason", "run_len_after"))
        for fr in d["frames"]:
            print("%-6u %-8u %04x     %-26s %u"
                  % (fr["index"], fr["blocks"], fr["flags"], fr["reason"], fr["run_len_after"]))
    elif cmd == "diag":
        if not d["diags"]:
            print("no semantic disagreement was preserved in this run")
        for i, g in enumerate(d["diags"]):
            print("record %u: cycle %u  disc=%04x gbi=%04x delta=%04x  %s  auth=%04x ack=%04x flags=%04x"
                  % (i, g["cycle"], g["disc_value"], g["gbi_value"], g["delta"], g["classification"],
                     g["authoritative_value"], g["ack_value"], g["record_flags"]))
    elif cmd == "bars":
        a = analyse(d, which)
        print(json.dumps(a.get("bars", []), indent=1, default=str))
    elif cmd == "analyse":
        print(analyse_text(d, which))
    elif cmd == "json":
        print(json.dumps({k: v for k, v in d.items() if not k.startswith("_")}, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
