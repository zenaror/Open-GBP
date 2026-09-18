#!/usr/bin/env python3
"""Offline reference model for the CONTROLLED indexed video stimulus.

THIS IS NOT THE ROM. It is the model the ROM will later be verified against, and
the model the analyzer will decode with. It exists first, on purpose: the
signature-feasibility question (DDR-2) and the geometry proofs can be answered
here for nothing, and a ROM written before them would have to be rewritten.

WHAT IS FROZEN HERE AND WHAT IS NOT
-----------------------------------
FACT      the consumed projection `word16 = (b1 << 8) | b3`, the 240x160
          geometry, 4 raster lines per VIDEO block, 40 blocks per frame, line
          stride 960 (GBP-HW-074..087, 123, 128)
FACT      the VIDEO window exchanges the two OUTER 5-bit groups relative to the
          AGB framebuffer (GBP-HW-131, U-GBP-011 CLOSED)
UNKNOWN   what sets bit 15, and whether it can appear anywhere but (0,0)
          (U-GBP-034). Nothing here depends on it.
DESIGN    every constant in this file: the layout, the symbols, the payload
          format, the CRC parameters, the palette, the bar rule. They are a
          PROPOSAL until a research document freezes them.

Run `python3 tools/istim.py gate` for the DDR-2 signature-feasibility report.
"""
from __future__ import annotations

import sys

# ---------------------------------------------------------------- geometry ---
WIDTH, HEIGHT = 240, 160
BLOCKS = 40
LINES_PER_BLOCK = 4
BLOCK_BYTES = 0xF00                      # 4 lines x 240 pixels x 4 bytes
LINE_STRIDE = WIDTH * 4                  # 960

# Column plan. The three GUARD columns and the FLAG column make the two strips
# impossible to run into each other, and make an off-by-one in the decoder show
# up as a guard violation rather than as a plausible-looking bit.
X_FLAG      = 0
STRIP_L     = range(1, 55)               # 54 columns
X_GUARD_A   = 55
CONTENT     = range(56, 184)             # 128 columns = 32 cells of 4
X_GUARD_B   = 184
STRIP_R     = range(185, 239)            # 54 columns
X_GUARD_C   = 239

# SYNC 8 | FRAME_ID 24 | BLOCK_INDEX 6 | STATUS 8 | CRC8 8
STRIP_BITS  = 54
PAYLOAD_BITS = 24 + 6 + 8                # what the CRC protects

# ----------------------------------------------------------------- symbols ---
# Chosen so that every instrumentation value is a FIXED POINT of the outer-group
# exchange: the frame-ID decode therefore does not depend on U-GBP-011's result
# being right, only on the consumed projection being right.
ZERO  = 0x0000       # -> 0x0000 after the exchange
ONE   = 0x7FFF       # -> 0x7FFF
FLAG  = 0x03E0       # -> 0x03E0 (the middle 5-bit group does not move)
GUARD = 0x0000       # -> 0x0000

# CONTENT palette, AGB BGR555 (bits 0-4 R, 5-9 G, 10-14 B), bit 15 never set.
PAL16 = tuple(0x0842 * k for k in range(16))     # a 16-step grey ramp
BAR   = 0x7C00                                   # AGB: pure blue; distinct from PAL16

BAR_CELLS   = 2          # 8 pixels
CELL        = 4
# 32 content cells, a 2-cell bar: start cells 0..30, so 31 phases. 31 is prime,
# so every multiplier that is not a multiple of 31 is coprime with it. The
# period was 35 while CONTENT was 144 px wide; the STATUS field cost 8 columns
# per strip and CONTENT shrank to 128 px. Documented, not hidden.
BAR_PERIOD  = 31

ID_BITS     = 24
ID_MOD      = 1 << ID_BITS
SYNC        = 0xB2       # 1011 0010

# ---------------------------------------------------------------- STATUS ----
# The stimulus's own verdict on whether IT stayed inside VBlank, carried in the
# CRC-protected payload because it is part of the decisive gate.
#
#   bit 7     FAULT    sticky latch, set the first time an update ends outside
#                      the VBlank window or exceeds the tick budget, never
#                      cleared for the rest of that boot
#   bits 6..0 VMARGIN  the monotone MINIMUM over all updates so far of the
#                      scanlines of VBlank still remaining when the update
#                      finished, clamped to 0..127 and initialised to 127
#                      ("no update measured yet"). It only ever decreases.
STATUS_BITS       = 8
STATUS_FAULT_MASK = 0x80
STATUS_MARGIN_MASK = 0x7F
STATUS_MARGIN_INIT = 0x7F

# GBA facts the mechanism rests on (GBATEK, external/gbatek/gba.md):
VCOUNT_VBLANK_FIRST = 160    # VCOUNT 160..227 are the hidden VBlank scanlines
VCOUNT_LAST         = 227
TIMER_PRESCALER     = 1      # 0=F/1 1=F/64 2=F/256 3=F/1024
TIMER_HZ            = 16777216 // 64        # 262144 Hz, 3.8147 us per tick
VBLANK_CYCLES       = 83776                 # 68 lines x 1232
VBLANK_TICKS        = VBLANK_CYCLES // 64   # 1309 ticks of the F/64 timer

# ------------------------------------------------------------------- CRC-8 ---
# Fully specified so no library convention is inherited:
#   register width      8 bits
#   polynomial          0x07  (x^8 + x^2 + x + 1), Koopman-free plain notation
#   init                0xFF
#   input order         MSB-first: FRAME_ID bit 23 down to bit 0, then
#                       BLOCK_INDEX bit 5 down to bit 0  (30 bits total)
#   zero augmentation   NONE (the message is not followed by 8 zero bits)
#   feedback            fb = ((crc >> 7) & 1) ^ inbit
#                       crc = ((crc << 1) & 0xFF) ^ (0x07 if fb else 0)
#   reflection          none, on input or output
#   xorout              0x00
#   result              the final register value, transmitted MSB-first
CRC8_POLY, CRC8_INIT, CRC8_XOROUT = 0x07, 0xFF, 0x00


def crc8_bits(bits) -> int:
    crc = CRC8_INIT
    for b in bits:
        fb = ((crc >> 7) & 1) ^ (b & 1)
        crc = (crc << 1) & 0xFF
        if fb:
            crc ^= CRC8_POLY
    return crc ^ CRC8_XOROUT


def payload_bits(frame_id: int, block_index: int, status: int = STATUS_MARGIN_INIT):
    """The 38 payload bits, MSB-first:
    FRAME_ID[23..0] || BLOCK_INDEX[5..0] || STATUS[7..0].

    STATUS is inside the CRC because it is part of the decisive gate: a run
    whose FAULT bit is set cannot support a source-integrity claim, so the bit
    must be as protected as the ID it qualifies."""
    if not 0 <= frame_id < ID_MOD:
        raise ValueError("frame_id out of range")
    if not 0 <= block_index < BLOCKS:
        raise ValueError("block_index out of range")
    if not 0 <= status < 256:
        raise ValueError("status out of range")
    bits = [(frame_id >> i) & 1 for i in range(ID_BITS - 1, -1, -1)]
    bits += [(block_index >> i) & 1 for i in range(5, -1, -1)]
    bits += [(status >> i) & 1 for i in range(STATUS_BITS - 1, -1, -1)]
    assert len(bits) == PAYLOAD_BITS
    return bits


def crc8_payload(frame_id: int, block_index: int, status: int = STATUS_MARGIN_INIT) -> int:
    return crc8_bits(payload_bits(frame_id, block_index, status))


def strip_bits(frame_id: int, block_index: int, status: int = STATUS_MARGIN_INIT):
    """The full 54-bit strip word:
    SYNC[8] || FRAME_ID[24] || BLOCK_INDEX[6] || STATUS[8] || CRC8[8]."""
    sync = [(SYNC >> i) & 1 for i in range(7, -1, -1)]
    pay = payload_bits(frame_id, block_index, status)
    crc = crc8_payload(frame_id, block_index, status)
    crcb = [(crc >> i) & 1 for i in range(7, -1, -1)]
    out = sync + pay + crcb
    assert len(out) == STRIP_BITS
    return out


def strip_variants(frame_id: int, block_index: int, status: int = STATUS_MARGIN_INIT):
    """The four (order, polarity) forms actually painted.

    row 4b+0 / 4b+2 : L = plain,     R = reversed+inverted
    row 4b+1 / 4b+3 : L = inverted,  R = reversed
    """
    b = strip_bits(frame_id, block_index, status)
    inv = [1 - v for v in b]
    return {
        "L_plain": b,
        "L_inv": inv,
        "R_rev_inv": list(reversed(inv)),
        "R_rev": list(reversed(b)),
    }


# ------------------------------------------------------------------ content ---
def background(x: int, y: int) -> int:
    return PAL16[(((x - CONTENT.start) >> 2) + (y >> 2)) & 15]


# The per-block phase multiplier MUST be coprime with BAR_PERIOD, or blocks
# collapse onto a few phases. The first proposal used 7, and gcd(7, 35) = 7 gave
# only 5 distinct phases across the 40 blocks — caught by the geometry tests
# before any ROM existed. 8 is coprime with 35 and yields 35 distinct phases;
# 40 > 35, so five pairs of blocks necessarily share one. That is acceptable
# because the bar is a FRESHNESS witness, never an identifier: the strip
# identifies, the bar only shows that this block's picture moved.
BAR_PHASE_MUL = 8
assert BAR_PERIOD % BAR_PHASE_MUL != 0


def barpos(frame_id: int, block_index: int) -> int:
    return (frame_id + BAR_PHASE_MUL * block_index) % BAR_PERIOD


def bar_range(frame_id: int, block_index: int) -> range:
    x0 = CONTENT.start + CELL * barpos(frame_id, block_index)
    return range(x0, x0 + CELL * BAR_CELLS)


# ------------------------------------------------------- the pixel function ---
def expected_agb(frame_id: int, x: int, y: int, status: int = STATUS_MARGIN_INIT) -> int:
    """TOTAL on 0 <= x < 240, 0 <= y < 160. The AGB framebuffer word this ROM
    will write; bit 15 is never set by the stimulus."""
    if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
        raise ValueError("pixel out of range")
    b = y >> 2
    row = y & 3
    if x == X_FLAG:
        return FLAG
    if x in (X_GUARD_A, X_GUARD_B, X_GUARD_C):
        return GUARD
    v = strip_variants(frame_id, b, status)
    if x in STRIP_L:
        bits = v["L_plain"] if row in (0, 2) else v["L_inv"]
        return ONE if bits[x - STRIP_L.start] else ZERO
    if x in STRIP_R:
        bits = v["R_rev_inv"] if row in (0, 2) else v["R_rev"]
        return ONE if bits[x - STRIP_R.start] else ZERO
    if x in bar_range(frame_id, b):
        return BAR
    return background(x, y)


def swap_outer(w: int) -> int:
    """The physically confirmed mapping (GBP-HW-131): the two OUTER 5-bit groups
    are exchanged; the middle group does not move; bit 15 is not a colour bit."""
    return ((w & 0x001F) << 10) | (w & 0x03E0) | ((w >> 10) & 0x001F)


def render_agb(frame_id: int, status: int = STATUS_MARGIN_INIT):
    return [[expected_agb(frame_id, x, y, status) for x in range(WIDTH)] for y in range(HEIGHT)]


def render_video(frame_id: int, status: int = STATUS_MARGIN_INIT):
    """The consumed colour15 words the analyzer should see."""
    return [[swap_outer(w) for w in row] for row in render_agb(frame_id, status)]


# ---------------------------------------------------- raw block and gbp_vsig ---
def render_block_raw(frame_id: int, block_index: int, flag15_at_origin: bool = False,
                     filler: int = 0x00, status: int = STATUS_MARGIN_INIT) -> bytes:
    """One 0xF00 VIDEO block as the wire carries it.

    Bytes 0 and 2 of every pixel are FILLER here: nothing in this experiment
    reads them (U-GBP-029 stays open and is reported separately). Bytes 1 and 3
    carry the consumed word, high then low.
    """
    out = bytearray(BLOCK_BYTES)
    for row in range(LINES_PER_BLOCK):
        y = block_index * LINES_PER_BLOCK + row
        for x in range(WIDTH):
            w = swap_outer(expected_agb(frame_id, x, y, status))
            if flag15_at_origin and block_index == 0 and row == 0 and x == 0:
                w |= 0x8000
            o = row * LINE_STRIDE + x * 4
            out[o + 0] = filler
            out[o + 1] = (w >> 8) & 0xFF
            out[o + 2] = filler
            out[o + 3] = w & 0xFF
    return bytes(out)


def vsig_block(raw: bytes) -> int:
    """EXACT reimplementation of src/gbp/gbp_vsig.c:gbp_vsig_block().

    MATHEMATICS. The 3840-byte block is read as 240 groups of 16 bytes; each
    group is four source pixels. For pixel j (0..959) let w_j = (b1 << 8) | b3 be
    the consumed word WITH BIT 15 INCLUDED — this function does not mask it.
    Then, with j = row*240 + x and 240 even, the parity of j is the parity of x:

        S   = sum over k of ( w_{2k} * 2^16 + w_{2k+1} ),  k = 0..479
            = 2^16 * (sum of w over EVEN x) + (sum of w over ODD x)
        sig = (S mod 2^32 + floor(S / 2^32)) mod 2^32

    It is an ADDITIVE CHECKSUM with a single end-around fold, not a hash:
      * it is invariant under any permutation of pixels within one parity class;
      * w_a + w_b = w_c + w_d gives a collision directly;
      * S < 960 * 2^32, so the fold adds at most 959 and can itself wrap.
    Its output is 32 bits. It DETECTS nothing it was not designed to detect and
    PROVES no pixel equality.
    """
    if len(raw) != BLOCK_BYTES:
        return 0
    total = 0
    for it in range(240):
        p = it * 16
        d0 = (raw[p + 1] << 24) | (raw[p + 3] << 16) | (raw[p + 5] << 8) | raw[p + 7]
        d1 = (raw[p + 9] << 24) | (raw[p + 11] << 16) | (raw[p + 13] << 8) | raw[p + 15]
        total += d0 + d1
    return ((total & 0xFFFFFFFF) + (total >> 32)) & 0xFFFFFFFF


def vsig_block_fast(frame_id: int, block_index: int, flag15_at_origin: bool = False,
                    status: int = STATUS_MARGIN_INIT) -> int:
    """The same value, computed from the parity decomposition instead of bytes."""
    even = odd = 0
    for row in range(LINES_PER_BLOCK):
        y = block_index * LINES_PER_BLOCK + row
        for x in range(WIDTH):
            w = swap_outer(expected_agb(frame_id, x, y, status))
            if flag15_at_origin and block_index == 0 and row == 0 and x == 0:
                w |= 0x8000
            if x & 1:
                odd += w
            else:
                even += w
    total = (even << 16) + odd
    return ((total & 0xFFFFFFFF) + (total >> 32)) & 0xFFFFFFFF


def expected_sigs(frame_id: int, flag15_at_origin: bool = False):
    return [vsig_block_fast(frame_id, b, flag15_at_origin) for b in range(BLOCKS)]


# ------------------------------------------------------------- the decoder ---
VALID_UNANIMOUS      = "VALID_UNANIMOUS"
VALID_MAJORITY       = "VALID_MAJORITY"
INVALID_NO_MAJORITY  = "INVALID_NO_MAJORITY"
CRC_FAILURE          = "CRC_FAILURE"
SYNC_FAILURE         = "SYNC_FAILURE"
COPY_DISAGREEMENT    = "COPY_DISAGREEMENT"

MAJORITY_MIN = 5          # of 8; an ERROR-RECOVERY POLICY, not a proof


def _symbol(word16: int):
    """ID decoding is on colour15 ONLY: bit 15 cannot change a decoded bit."""
    c = word16 & 0x7FFF
    if c == ZERO:
        return 0
    if c == ONE:
        return 1
    return None


def decode_strip_copy(words, kind: str):
    """`words` are the 46 consumed word16 of one strip in one row."""
    raw = [_symbol(w) for w in words]
    if any(v is None for v in raw):
        return None
    if kind in ("R_rev_inv", "R_rev"):
        raw = list(reversed(raw))
    if kind in ("L_inv", "R_rev_inv"):
        raw = [1 - v for v in raw]
    return raw


def decode_block(rows, block_index: int):
    """`rows` is 4 lists of 240 consumed word16 for one VIDEO block."""
    kinds = [("L_plain", "R_rev_inv"), ("L_inv", "R_rev"),
             ("L_plain", "R_rev_inv"), ("L_inv", "R_rev")]
    copies, sync_fail, crc_fail = [], 0, 0
    for row in range(LINES_PER_BLOCK):
        kl, kr = kinds[row]
        for xs, kind in ((STRIP_L, kl), (STRIP_R, kr)):
            bits = decode_strip_copy([rows[row][x] for x in xs], kind)
            if bits is None:
                continue
            sync = 0
            for v in bits[:8]:
                sync = (sync << 1) | v
            if sync != SYNC:
                sync_fail += 1
                continue
            pay = bits[8:8 + PAYLOAD_BITS]
            crc = 0
            for v in bits[8 + PAYLOAD_BITS:]:
                crc = (crc << 1) | v
            if crc8_bits(pay) != crc:
                crc_fail += 1
                continue
            fid = 0
            for v in pay[:24]:
                fid = (fid << 1) | v
            bidx = 0
            for v in pay[24:30]:
                bidx = (bidx << 1) | v
            st = 0
            for v in pay[30:38]:
                st = (st << 1) | v
            copies.append((fid, bidx, st))

    res = {"copies_valid": len(copies), "sync_failures": sync_fail,
           "crc_failures": crc_fail, "frame_id": None, "block_index_field": None,
           "status": None, "index_ok": False, "outcome": None}
    if not copies:
        res["outcome"] = SYNC_FAILURE if sync_fail else (CRC_FAILURE if crc_fail else INVALID_NO_MAJORITY)
        return res
    counts = {}
    for c in copies:
        counts[c] = counts.get(c, 0) + 1
    best, n = max(counts.items(), key=lambda kv: kv[1])
    if n < MAJORITY_MIN:
        res["outcome"] = INVALID_NO_MAJORITY if len(counts) > 1 else INVALID_NO_MAJORITY
        return res
    res["frame_id"], res["block_index_field"], res["status"] = best
    res["index_ok"] = (best[1] == block_index)
    res["outcome"] = VALID_UNANIMOUS if (n == 8 and len(counts) == 1) else (
        VALID_MAJORITY if len(counts) == 1 else COPY_DISAGREEMENT)
    if len(counts) > 1:
        res["outcome"] = COPY_DISAGREEMENT
    return res


# ------------------------------------------------- the CANONICAL WITNESS ----
# ONE strip copy per VIDEO block, preserved LOSSLESSLY as the original consumed
# word16. The choice is STRIP-L, LOCAL ROW 0 of the block, i.e. screen row 4*b:
# it is the first line of the block on the wire, so a runtime copy is a single
# contiguous stride at the head of the delivery and needs no buffering of the
# rest of the block.
#
# The runtime would preserve WORDS. It would not decode, not interpret and not
# decide. All of that stays offline.
WITNESS_STRIP = STRIP_L
WITNESS_LOCAL_ROW = 0
WITNESS_WORDS_PER_BLOCK = STRIP_BITS                 # 54
WITNESS_BYTES_PER_BLOCK = WITNESS_WORDS_PER_BLOCK * 2      # 108
WITNESS_BYTES_PER_FRAME = WITNESS_BYTES_PER_BLOCK * BLOCKS  # 4320


def witness_words(frame_id: int, block_index: int, status: int = STATUS_MARGIN_INIT,
                  flag15_at_origin: bool = False):
    """The 54 consumed word16 a runtime would copy for one block."""
    y = block_index * LINES_PER_BLOCK + WITNESS_LOCAL_ROW
    out = []
    for x in WITNESS_STRIP:
        w = swap_outer(expected_agb(frame_id, x, y, status))
        if flag15_at_origin and block_index == 0 and WITNESS_LOCAL_ROW == 0 and x == 0:
            w |= 0x8000
        out.append(w)
    return out


# Capacity for the first decisive run, DERIVED rather than picked:
#   expected 30 s population           30 x 59.737 Hz = 1792.1 frames
#   + 10 % (clock tolerance, and the capture window is TICK-bounded, not
#     frame-bounded, so the population is not exactly 1792)   = 1971.3
#   smallest power of two above that                          = 2048
#   footprint 2048 x 4320 B = 8.44 MiB, against the 13.97 MiB stream-0003
#   leaves free; a future candidate would commit 18.47 MiB of 24.00.
# Reaching it is `witness_store_full`: the run STOPS storing and the decisive
# claim becomes INCONCLUSIVE. Nothing is ever silently overwritten.
WITNESS_CAPACITY_FRAMES = 2048
WITNESS_CAPACITY_BYTES = WITNESS_CAPACITY_FRAMES * WITNESS_BYTES_PER_FRAME

INVALID_CANONICAL_STRIP = "INVALID_CANONICAL_STRIP"
CANONICAL_OK = "CANONICAL_OK"


def decode_canonical(words, block_index: int):
    """The decisive decoder. Lossless in, structured out, no scoring.

    flag15 is split off and REPORTED; it can never change a decoded bit.
    """
    if len(words) != WITNESS_WORDS_PER_BLOCK:
        return {"outcome": INVALID_CANONICAL_STRIP, "reason": "length"}
    flag15 = [i for i, w in enumerate(words) if w & 0x8000]
    bits = []
    for w in words:
        c = w & 0x7FFF
        if c == ZERO:
            bits.append(0)
        elif c == ONE:
            bits.append(1)
        else:
            return {"outcome": INVALID_CANONICAL_STRIP, "reason": "symbol",
                    "flag15_indices": flag15}
    sync = 0
    for v in bits[:8]:
        sync = (sync << 1) | v
    if sync != SYNC:
        return {"outcome": INVALID_CANONICAL_STRIP, "reason": "sync",
                "flag15_indices": flag15}
    pay = bits[8:8 + PAYLOAD_BITS]
    crc = 0
    for v in bits[8 + PAYLOAD_BITS:]:
        crc = (crc << 1) | v
    if crc8_bits(pay) != crc:
        return {"outcome": INVALID_CANONICAL_STRIP, "reason": "crc",
                "flag15_indices": flag15}
    fid = 0
    for v in pay[:24]:
        fid = (fid << 1) | v
    bidx = 0
    for v in pay[24:30]:
        bidx = (bidx << 1) | v
    st = 0
    for v in pay[30:38]:
        st = (st << 1) | v
    return {"outcome": CANONICAL_OK, "frame_id": fid, "block_index_field": bidx,
            "index_ok": bidx == block_index, "status": st,
            "fault": bool(st & STATUS_FAULT_MASK),
            "vmargin": st & STATUS_MARGIN_MASK,
            "flag15_indices": flag15}


# ------------------------------------------- frame-level classification ----
MIXED_BLOCK_IDS        = "MIXED_BLOCK_IDS"
MISPLACED_BLOCK_INDEX  = "MISPLACED_BLOCK_INDEX"
FRAME_OK               = "FRAME_OK"


def classify_frame(block_witnesses):
    """`block_witnesses` is 40 lists of 54 consumed word16, in delivery order."""
    res = {"blocks": [], "outcome": None, "frame_id": None,
           "status": None, "fault": None, "vmargin": None}
    for b, w in enumerate(block_witnesses):
        res["blocks"].append(decode_canonical(w, b))
    if any(d["outcome"] != CANONICAL_OK for d in res["blocks"]):
        res["outcome"] = INVALID_CANONICAL_STRIP
        return res
    if any(not d["index_ok"] for d in res["blocks"]):
        res["outcome"] = MISPLACED_BLOCK_INDEX
        return res
    ids = {d["frame_id"] for d in res["blocks"]}
    if len(ids) != 1:
        res["outcome"] = MIXED_BLOCK_IDS
        return res
    sts = {d["status"] for d in res["blocks"]}
    if len(sts) != 1:
        res["outcome"] = MIXED_BLOCK_IDS          # the status is part of the id'd payload
        return res
    res["outcome"] = FRAME_OK
    res["frame_id"] = ids.pop()
    res["status"] = sts.pop()
    res["fault"] = bool(res["status"] & STATUS_FAULT_MASK)
    res["vmargin"] = res["status"] & STATUS_MARGIN_MASK
    return res


# -------------------------------------------- modular source classification ---
# Factual names only: none of them attributes a mechanism, and "SOURCE LOSS" is
# deliberately absent as a name for raw data.
OBSERVED_ID_CONTIGUOUS = "OBSERVED_ID_CONTIGUOUS"
OBSERVED_DUPLICATE_ID  = "OBSERVED_DUPLICATE_ID"
OBSERVED_ID_GAP        = "OBSERVED_ID_GAP"
UNRESOLVED_HALF_RANGE  = "UNRESOLVED_HALF_RANGE"
OBSERVED_REORDER       = "OBSERVED_REORDER"

# kept as aliases so older text does not silently change meaning
CONTIGUOUS       = OBSERVED_ID_CONTIGUOUS
FORWARD_GAP      = OBSERVED_ID_GAP
REORDER_BACKWARD = OBSERVED_REORDER

HALF = 1 << (ID_BITS - 1)


def classify_delta(prev_id: int, id_n: int) -> str:
    d = (id_n - prev_id) % ID_MOD
    if d == 0:
        return OBSERVED_DUPLICATE_ID
    if d == 1:
        return CONTIGUOUS
    if d < HALF:
        return FORWARD_GAP
    if d == HALF:
        return UNRESOLVED_HALF_RANGE
    return REORDER_BACKWARD


# ------------------------------------------------------------------- gates ---
def ddr2_gate(n_ids: int, window: int, progress=None):
    """Sliding-window distinctness of the expected signatures.

    For every block index and every pair of frame IDs closer than `window`,
    require sig(f, b) != sig(f', b). Reports what was TESTED; it proves nothing
    about IDs outside the tested range.
    """
    seen = [dict() for _ in range(BLOCKS)]
    collisions = []
    for f in range(n_ids):
        sigs = expected_sigs(f)
        for b in range(BLOCKS):
            s = sigs[b]
            prev = seen[b].get(s)
            if prev is not None and f - prev < window:
                collisions.append((b, prev, f, s))
            seen[b][s] = f
        if progress and f % progress == 0:
            print("  ... f=%d collisions=%d" % (f, len(collisions)), file=sys.stderr)
    return collisions


def _main(argv):
    if len(argv) > 1 and argv[1] == "gate":
        n = int(argv[2]) if len(argv) > 2 else 200
        w = int(argv[3]) if len(argv) > 3 else 4096
        c = ddr2_gate(n, w)
        print("DDR-2 sliding-window gate: ids=%d window=%d blocks=%d" % (n, w, BLOCKS))
        print("collisions: %d" % len(c))
        for b, f0, f1, s in c[:10]:
            print("  block %2d: f=%d and f=%d share sig 0x%08x" % (b, f0, f1, s))
        return 0 if not c else 1
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))


# ---------------------------------------- the decisive population (§18/§19) ---
# THE STATUS DELAY, stated exactly.
#
# Per VBlank N the ROM will: read the timer and VCOUNT; set f := N; paint the
# strips with the latch AS IT STANDS, which reflects updates 0..N-1; paint the
# bars; read the timer and VCOUNT again; fold the result into the latch, which
# now reflects update N.
#
# So: STATUS carried by frame f certifies updates 0 .. f-1, and NEVER f itself.
#
# Combined with the unobservable edges, for observed intact frames A..Z:
#   * frame Z's own update is uncertified — only a frame later than Z would
#     carry a latch covering it, and there is none;
#   * the latch is STICKY, so frame Z's STATUS already covers every update from
#     0 to Z-1 at once;
#   * therefore the DECISIVE frames are A..Z-1 and the decisive transitions are
#     A->A+1 ... (Z-2)->(Z-1).
STATUS_CERTIFIES_UP_TO_OFFSET = -1     # frame f certifies updates up to f - 1


def decisive_population(frames):
    """`frames` is the ordered list of classify_frame() results for the capture.

    Returns the pre-registered decisive set and, explicitly, what was excluded
    and why. It never guesses across a break: a frame that is not FRAME_OK ends
    the run of decisive frames.
    """
    intact = [(i, f) for i, f in enumerate(frames) if f["outcome"] == FRAME_OK]
    out = {"observed_intact": len(intact), "decisive_frames": [],
           "decisive_transitions": [], "excluded": [], "fault_seen": None,
           "verdict": None}
    if len(intact) < 2:
        out["verdict"] = "INCONCLUSIVE_TOO_FEW_INTACT_FRAMES"
        return out

    last = intact[-1]
    out["excluded"].append(("trailing_frame_uncertified",
                            "frame id 0x%06x: no later STATUS certifies its own update"
                            % last[1]["frame_id"]))
    out["excluded"].append(("leading_edge",
                            "AGB frames before id 0x%06x are unobservable"
                            % intact[0][1]["frame_id"]))
    out["excluded"].append(("trailing_edge",
                            "AGB frames after id 0x%06x are unobservable"
                            % last[1]["frame_id"]))

    # the sticky latch carried by the LAST intact frame covers every update
    # from 0 up to (that frame's id - 1), which is the whole decisive set
    out["fault_seen"] = any(f["fault"] for _, f in intact)

    decisive = intact[:-1]
    out["decisive_frames"] = [f["frame_id"] for _, f in decisive]
    for (ia, a), (ib, b) in zip(decisive, decisive[1:]):
        out["decisive_transitions"].append(
            (a["frame_id"], b["frame_id"], classify_delta(a["frame_id"], b["frame_id"])))

    if out["fault_seen"]:
        out["verdict"] = "STIMULUS_INVALID_FOR_DECISIVE_CLAIM"
    elif not out["decisive_transitions"]:
        out["verdict"] = "INCONCLUSIVE_TOO_FEW_INTACT_FRAMES"
    elif all(c == OBSERVED_ID_CONTIGUOUS for _, _, c in out["decisive_transitions"]):
        out["verdict"] = "OBSERVED_CONTIGUOUS"
    else:
        out["verdict"] = "OBSERVED_DISCONTINUITY"
    return out
