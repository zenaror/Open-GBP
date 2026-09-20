#!/usr/bin/env python3
"""
tools/icoord.py — the offline model of the CONTROLLED COORDINATE stimulus,
`coord-0001`, contract OGBPCOORD1 (HARDWARE_TESTS §V6.6, GitHub Issue #7).

THIS IS NOT THE ROM. It is what the ROM (stimulus/agb-coord) is compared
against word for word on the host (tests/host/test_agb_coord.py), and what
tools/vfull.py decodes a physical full-frame sample against. It is pure
Python, imports nothing from the GameCube side, and never sees a sidecar.

WHAT IS INHERITED, UNCHANGED, FROM OGBPIDX1 (tools/istim.py, not edited)
  the FLAG column, the 54-bit STRIP-L payload in its four row variants, the
  guard column at x = 55, SYNC, CRC-8, STATUS, the symbols ZERO / ONE / FLAG /
  GUARD, the 24-bit frame id. The canonical witness bytes (STRIP-L, local row
  0, x = 1..54) are therefore BYTE-IDENTICAL between the two stimuli, which is
  what lets tools/vindex.py, gbp_vwitness and the not-before gate apply to a
  coord-0001 run without change.

WHAT IS NEW
  x = 56..238   FIELD    value(x, y) = y*183 + (x-56): 0..29279, injective over
                         the 29 280 field pixels, bit 15 clear, static
  x = 239       GUARD    0x0000
  glyph          for frame_id in R_k = [k*P, k*P + W), k >= 1, P = 480, W = 40:
                 the seven-segment digit (k mod 10), 48x80 at (123, 40), and six
                 8x8 squares at (123 + 8*i, 128), i = 0..5, MSB left, showing
                 frame_id - k*P; both 0x7FFF, drawn INTO the field
  removed        STRIP-R and the moving bar

The oracle is TOTAL on 0 <= x < 240, 0 <= y < 160 and depends on frame_id
only through the strip payload and the glyph schedule. Nothing here knows the
GameCube renderer; `swap_outer` is the physically established outer-group
exchange (GBP-HW-131) applied to describe what the VIDEO window carries.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import istim  # noqa: E402  (frozen; imported, never edited)

# ---------------------------------------------------------------- geometry ---
WIDTH, HEIGHT = istim.WIDTH, istim.HEIGHT           # 240 x 160
BLOCKS, LINES_PER_BLOCK = istim.BLOCKS, istim.LINES_PER_BLOCK
BLOCK_BYTES, LINE_STRIDE = istim.BLOCK_BYTES, istim.LINE_STRIDE

X_FLAG = istim.X_FLAG                               # 0
STRIP_L = istim.STRIP_L                             # 1..54
X_GUARD_A = istim.X_GUARD_A                         # 55
FIELD_X0 = 56
FIELD_X1 = 238
FIELD_W = FIELD_X1 - FIELD_X0 + 1                   # 183
FIELD = range(FIELD_X0, FIELD_X1 + 1)
X_GUARD_C = 239
FIELD_PIXELS = FIELD_W * HEIGHT                     # 29280
FIELD_MAX = FIELD_PIXELS - 1                        # 29279

ZERO, ONE, FLAG, GUARD = istim.ZERO, istim.ONE, istim.FLAG, istim.GUARD
STATUS_MARGIN_INIT = istim.STATUS_MARGIN_INIT
STATUS_FAULT_MASK = istim.STATUS_FAULT_MASK

# ----------------------------------------------------------------- glyph ----
GLYPH_P, GLYPH_W = 480, 40
GLYPH_X0, GLYPH_Y0 = 123, 40
GLYPH_COLS, GLYPH_ROWS = 48, 80
SEG_T = 8
SQ_X0, SQ_Y0, SQ_N, SQ_SIZE = 123, 128, 6, 8
GLYPH_COLOUR = 0x7FFF
# bit 0 a top, 1 b top-right, 2 c bottom-right, 3 d bottom, 4 e bottom-left,
# 5 f top-left, 6 g middle
SEG_OF_DIGIT = (0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F)


def field(x: int, y: int) -> int:
    if not (FIELD_X0 <= x <= FIELD_X1 and 0 <= y < HEIGHT):
        raise ValueError("not a field pixel")
    return y * FIELD_W + (x - FIELD_X0)


def field_inverse(value: int):
    """The (x, y) a field value names — what makes a displacement map possible."""
    if not (0 <= value <= FIELD_MAX):
        return None
    return (FIELD_X0 + value % FIELD_W, value // FIELD_W)


def schedule(frame_id: int):
    """(k, phase): the appearance ordinal and the frame's position in the period."""
    return frame_id // GLYPH_P, frame_id % GLYPH_P


def glyph_shown(frame_id: int) -> bool:
    k, phase = schedule(frame_id)
    return k >= 1 and phase < GLYPH_W


def appearance_range(k: int) -> range:
    """R_k, the frame ids that carry digit k mod 10."""
    if k < 1:
        raise ValueError("appearances start at k = 1")
    return range(k * GLYPH_P, k * GLYPH_P + GLYPH_W)


def glyph_lit(digit: int, gx: int, gy: int) -> bool:
    s = SEG_OF_DIGIT[digit]
    top, bottom = gy < 44, gy >= 36
    if s & 0x01 and gy < SEG_T:
        return True
    if s & 0x08 and gy >= GLYPH_ROWS - SEG_T:
        return True
    if s & 0x40 and 36 <= gy < 44:
        return True
    if s & 0x02 and gx >= GLYPH_COLS - SEG_T and top:
        return True
    if s & 0x04 and gx >= GLYPH_COLS - SEG_T and bottom:
        return True
    if s & 0x20 and gx < SEG_T and top:
        return True
    if s & 0x10 and gx < SEG_T and bottom:
        return True
    return False


def glyph_at(frame_id: int, x: int, y: int):
    """The glyph word at (x, y) for this frame, or None when the field shows."""
    k, phase = schedule(frame_id)
    if not (k >= 1 and phase < GLYPH_W):
        return None
    if GLYPH_X0 <= x < GLYPH_X0 + GLYPH_COLS and GLYPH_Y0 <= y < GLYPH_Y0 + GLYPH_ROWS:
        return GLYPH_COLOUR if glyph_lit(k % 10, x - GLYPH_X0, y - GLYPH_Y0) else None
    if SQ_X0 <= x < SQ_X0 + SQ_N * SQ_SIZE and SQ_Y0 <= y < SQ_Y0 + SQ_SIZE:
        i = (x - SQ_X0) // SQ_SIZE                      # square 0..5, MSB left
        return GLYPH_COLOUR if (phase >> (SQ_N - 1 - i)) & 1 else None
    return None


# ------------------------------------------------------- the pixel function ---
def expected_agb(frame_id: int, x: int, y: int, status: int = STATUS_MARGIN_INIT) -> int:
    """TOTAL on 0 <= x < 240, 0 <= y < 160: the AGB framebuffer word the ROM
    writes. Bit 15 is never set by the stimulus."""
    if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
        raise ValueError("pixel out of range")
    b, row = y >> 2, y & 3
    if x == X_FLAG:
        return FLAG
    if x in (X_GUARD_A, X_GUARD_C):
        return GUARD
    if x in STRIP_L:
        v = istim.strip_variants(frame_id, b, status)
        bits = v["L_plain"] if row in (0, 2) else v["L_inv"]
        return ONE if bits[x - STRIP_L.start] else ZERO
    g = glyph_at(frame_id, x, y)
    if g is not None:
        return g
    return field(x, y)


swap_outer = istim.swap_outer


def expected_video(frame_id: int, x: int, y: int, status: int = STATUS_MARGIN_INIT) -> int:
    """The consumed colour15 word the VIDEO window carries (GBP-HW-131)."""
    return swap_outer(expected_agb(frame_id, x, y, status))


def render_agb(frame_id: int, status: int = STATUS_MARGIN_INIT):
    return [[expected_agb(frame_id, x, y, status) for x in range(WIDTH)] for y in range(HEIGHT)]


def render_video(frame_id: int, status: int = STATUS_MARGIN_INIT):
    return [[swap_outer(w) for w in row] for row in render_agb(frame_id, status)]


def witness_words(frame_id: int, block_index: int, status: int = STATUS_MARGIN_INIT,
                  flag15_at_origin: bool = False):
    """The 54 consumed word16 of the canonical witness: STRIP-L, local row 0.
    Identical to istim.witness_words for the same arguments, by construction."""
    y = block_index * LINES_PER_BLOCK + istim.WITNESS_LOCAL_ROW
    out = []
    for x in istim.WITNESS_STRIP:
        w = swap_outer(expected_agb(frame_id, x, y, status))
        if flag15_at_origin and block_index == 0 and x == 0:
            w |= 0x8000
        out.append(w)
    return out


# -------------------------------------------------- the wire, block by block ---
def render_block_raw(frame_id: int, block_index: int, flag15_at_origin: bool = False,
                     filler: int = 0x00, status: int = STATUS_MARGIN_INIT) -> bytes:
    """One 0xF00 VIDEO block as the wire carries it: bytes 1/3 = the consumed
    word high/low, bytes 0/2 = filler (U-GBP-029, never read by anything)."""
    out = bytearray(BLOCK_BYTES)
    for row in range(LINES_PER_BLOCK):
        y = block_index * LINES_PER_BLOCK + row
        for x in range(WIDTH):
            w = expected_video(frame_id, x, y, status)
            if flag15_at_origin and block_index == 0 and row == 0 and x == 0:
                w |= 0x8000
            o = row * LINE_STRIDE + x * 4
            out[o + 0] = filler & 0xFF
            out[o + 1] = (w >> 8) & 0xFF
            out[o + 2] = filler & 0xFF
            out[o + 3] = w & 0xFF
    return bytes(out)


def render_frame_raw(frame_id: int, flag15_at_origin: bool = True, filler: int = 0x00,
                     status: int = STATUS_MARGIN_INIT) -> bytes:
    return b"".join(render_block_raw(frame_id, b, flag15_at_origin, filler, status) for b in range(BLOCKS))


# ------------------------------------------------------------- tiled oracle ---
TILE_W = TILE_H = 4
TILES_X, TILES_Y = WIDTH // TILE_W, HEIGHT // TILE_H          # 60 x 40
TEX_TEXELS = WIDTH * HEIGHT                                  # 38400
RGB5A3_OPAQUE = 0x8000


def tile_index(x: int, y: int) -> int:
    """gbp_vpix's tile order, stated independently: tiles left to right then
    top to bottom; inside a tile the four rows of four texels are consecutive."""
    tx, ty, ix, iy = x // TILE_W, y // TILE_H, x % TILE_W, y % TILE_H
    return (ty * TILES_X + tx) * (TILE_W * TILE_H) + iy * TILE_W + ix


def tiled_oracle(frame_id: int, status: int = STATUS_MARGIN_INIT):
    """`oracle | 0x8000` in tile order: what a correct renderer input holds."""
    tex = [0] * TEX_TEXELS
    for y in range(HEIGHT):
        for x in range(WIDTH):
            tex[tile_index(x, y)] = expected_video(frame_id, x, y, status) | RGB5A3_OPAQUE
    return tex


# ----------------------------------------------------------- self-checks ----
def _main(argv):
    if len(argv) >= 2 and argv[1] == "check":
        vals = [field(x, y) for y in range(HEIGHT) for x in FIELD]
        assert len(set(vals)) == FIELD_PIXELS and max(vals) == FIELD_MAX
        for fid in (0, 1, 479, 480, 481, 519, 520, 960, 1440, 1920):
            fr = render_agb(fid)
            assert all(w < 0x8000 for row in fr for w in row)
            for b in range(BLOCKS):
                assert witness_words(fid, b) == istim.witness_words(fid, b), (fid, b)
        print("icoord: field injective (%d values), witness identical to OGBPIDX1, bit 15 never set" % FIELD_PIXELS)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
