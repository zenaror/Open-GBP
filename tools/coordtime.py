#!/usr/bin/env python3
"""
tools/coordtime.py — a reproducible cycle model of the frozen coord-0001 ROM
(HARDWARE_TESTS §V6.22, GBP-VID-034; GitHub Issue #12).

    tools/coordtime.py analyse [<agb-coord.gba>]       the full report
    tools/coordtime.py check                           the interpreter self-test

WHAT IT IS
  A minimal ARM7TDMI (ARM state) interpreter that executes the EXACT generated
  code of the frozen coord-0001 image (canonical 3 496 B, SHA-256 90343b64…),
  counting bus cycles with the GBATEK rules for this ROM's memory map:
    IWRAM   32-bit bus, 1/1/1                (the code and stack of PREPARE / PUBLISH)
    EWRAM   16-bit bus, 3/3/6 (2 wait states, the hardware default of 4000800h)
    ROM     16-bit bus, WAITCNT 4317h -> N 1+3 = 4, S 1+1 = 2 per 16-bit access
    VRAM    16-bit bus, 1/1/2               (DMA destination, VBlank only)
    I/O     32-bit bus, 1/1/1
  ARM7TDMI instruction cycles (GBATEK "ARM CPU Instruction Cycle Times"):
    ALU 1S (+1I shift by register) · LDR 1S+1N+1I · STR 2N · LDM nS+1N+1I ·
    STM (n-1)S+2N · B/BL/BX 2S+1N · {cond} false 1S
  DMA (GBATEK "Transfer Rate/Timing"): 2N + 2(n-1)S + 2I, read and write halves
  costed in their own regions.

WHAT IT MAY CLAIM
  The cost, in cycles, of PREPARE for every frame class of the schedule
  (ordinary, entry per digit, steady, exit), of PUBLISH per class, of the ROM-
  resident loop tail between them (as an interval, because the ROM prefetch
  buffer is not modelled cycle-exact), and therefore whether PREPARE for a given
  frame ends before or after the VBlank it must publish in.  The PUBLISH model
  is CALIBRATED against RUN 12's hardware-measured VMARGIN values (54 / 39 /
  38): a model that did not reproduce them would be wrong about the memory
  timing it shares with PREPARE.
WHAT IT MAY NOT CLAIM
  Anything about the Game Boy Player, the capture path or the display; the
  schedule of the glyph (that is tools/icoord.py's); any AGB behaviour outside
  the instructions it executes.  Its unknown terms are printed, never hidden.
"""
from __future__ import annotations

import hashlib
import os
import sys

ROM_SHA256 = "90343b64eda9602c173364171637cd1068f265c385464361b40ec073b11f0a1f"
ROM_SIZE = 3496

IWRAM_BASE, IWRAM_SIZE = 0x03000000, 0x8000
EWRAM_BASE, EWRAM_SIZE = 0x02000000, 0x40000
VRAM_BASE, VRAM_SIZE = 0x06000000, 0x18000
IO_BASE, IO_SIZE = 0x04000000, 0x400
OAM_BASE, OAM_SIZE = 0x07000000, 0x400
ROM_BASE = 0x08000000
SENTINEL = 0xFFFFFFF0

PREPARE_ADDR, PUBLISH_ADDR = 0x03000000, 0x0300047C
IWRAM_IMAGE_LEN = 0x630
PREPARE_HEAD = bytes.fromhex("2038e0e1f04f2de9")     # mvn r3, r0, lsr #16 ; push {r4-r9, sl, fp, lr}
PUBLISH_HEAD = bytes.fromhex("00c0a0e370402de9")     # mov ip, #0 ; push {r4, r5, r6, lr}
SEG_OF_DIGIT_ADDR = 0x08000758
CRC_TAB_ADDR = 0x03002C70
OP_DIGIT_ADDR, OP_SQ_ADDR = 0x0300064D, 0x0300064C
MAIN_AFTER_PUBLISH = 0x08000504      # the instruction after `bl __publish_frame_veneer`
MAIN_AFTER_PREPARE = 0x080004E0      # the first VCOUNT poll after `bl __prepare_frame_veneer`
MAIN_LOOP_HEAD = 0x0800048C

LINE_CYCLES = 1232
LINES = 228
FRAME_CYCLES = LINE_CYCLES * LINES     # 280 896
VBLANK_FIRST = 160
GLYPH_P, GLYPH_W = 480, 40
SEG = [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F]


# ----------------------------------------------------------------- memory ----
class Timing:
    """Per-region access costs. ewram_ws = wait states of 4000800h (2 by default);
    rom_n / rom_s = 16-bit ROM access cost (WAITCNT 4317h: 4 / 2); rom_code_s /
    rom_code_n = cost of a 32-bit ARM opcode fetch from ROM (prefetch bound)."""

    def __init__(self, ewram_ws=2, rom_n=4, rom_s=2, rom_code_s=None, rom_code_n=None):
        self.ewram16 = 1 + ewram_ws
        self.rom_n, self.rom_s = rom_n, rom_s
        self.rom_code_s = rom_code_s if rom_code_s is not None else 2 * rom_s     # two sequential halves
        self.rom_code_n = rom_code_n if rom_code_n is not None else rom_n + rom_s  # N half + S half

    def data(self, addr, width, seq):
        r = addr >> 24
        if r == 0x03:
            return 1
        if r == 0x02:
            return self.ewram16 * (2 if width == 32 else 1)
        if r == 0x08 or r == 0x09:
            first = self.rom_s if seq else self.rom_n
            return first + (self.rom_s if width == 32 else 0)
        if r == 0x06 or r == 0x05:
            return 2 if width == 32 else 1
        if r == 0x04 or r == 0x07:
            return 1
        raise ValueError("data access outside the modelled map: 0x%08x" % addr)

    def code(self, addr, seq):
        r = addr >> 24
        if r == 0x03:
            return 1
        if r == 0x08:
            return self.rom_code_s if seq else self.rom_code_n
        raise ValueError("code fetch outside the modelled map: 0x%08x" % addr)


class Mem:
    def __init__(self, rom, timing):
        self.iwram = bytearray(IWRAM_SIZE)
        self.ewram = bytearray(EWRAM_SIZE)
        self.vram = bytearray(VRAM_SIZE)
        self.io = bytearray(IO_SIZE)
        self.oam = bytearray(OAM_SIZE)
        self.rom = bytes(rom) + bytes(max(0, 0x1000000 - len(rom)))
        self.timing = timing
        self.dma_cycles = 0
        self.dma_log = []
        self.counts = {}                        # (region, width, kind) -> accesses by the CPU

    def _buf(self, addr):
        r = addr >> 24
        if r == 0x03:
            return self.iwram, addr & 0x7FFF
        if r == 0x02:
            return self.ewram, addr & 0x3FFFF
        if r == 0x06:
            return self.vram, addr & 0x1FFFF
        if r == 0x04:
            return self.io, addr & 0x3FF
        if r == 0x07:
            return self.oam, addr & 0x3FF
        if r in (0x08, 0x09):
            return self.rom, addr & 0x1FFFFFF
        raise ValueError("access outside the modelled map: 0x%08x" % addr)

    def read(self, addr, width, count=True):
        buf, off = self._buf(addr)
        n = width // 8
        if count:
            k = (addr >> 24, width, "r")
            self.counts[k] = self.counts.get(k, 0) + 1
        return int.from_bytes(buf[off:off + n], "little")

    def write(self, addr, width, value, count=True):
        buf, off = self._buf(addr)
        if buf is self.rom:
            raise ValueError("write to ROM at 0x%08x" % addr)
        n = width // 8
        if count:
            k = (addr >> 24, width, "w")
            self.counts[k] = self.counts.get(k, 0) + 1
        buf[off:off + n] = (value & ((1 << width) - 1)).to_bytes(n, "little")
        if addr == 0x040000DC and width == 32 and value & 0x80000000:
            self._dma3(value)

    def _dma3(self, cnt):
        src = self.read(0x040000D4, 32) & 0x0FFFFFFF
        dst = self.read(0x040000D8, 32) & 0x0FFFFFFF
        n = cnt & 0xFFFF or 0x10000
        width = 32 if cnt & 0x04000000 else 16
        step = width // 8
        t = self.timing
        cycles = t.data(src, width, False) + t.data(dst, width, False) + (n - 1) * (t.data(src, width, True) + t.data(dst, width, True)) + 2
        for i in range(n):
            self.write(dst + i * step, width, self.read(src + i * step, width, count=False), count=False)
        self.dma_cycles += cycles
        self.dma_log.append((src, dst, n, width, cycles))
        self.io[0xDC:0xE0] = (cnt & 0x7FFFFFFF).to_bytes(4, "little")


# -------------------------------------------------------------------- CPU ----
def _ror(v, n):
    n &= 31
    return ((v >> n) | (v << (32 - n))) & 0xFFFFFFFF if n else v


class CPU:
    def __init__(self, mem):
        self.m = mem
        self.r = [0] * 16
        self.N = self.Z = self.C = self.V = 0
        self.cycles = 0
        self.instructions = 0
        self.pc_trace = None

    # ---- helpers ----
    def _cond(self, c):
        N, Z, C, V = self.N, self.Z, self.C, self.V
        return (Z, not Z, C, not C, N, not N, V, not V, C and not Z, (not C) or Z,
                N == V, N != V, (not Z) and N == V, Z or N != V, True, False)[c]

    def _reg(self, i, pc_off=8):
        return (self.r[15] + pc_off) & 0xFFFFFFFF if i == 15 else self.r[i]

    def _shifter(self, instr):
        C = self.C
        if instr & (1 << 25):
            imm, rot = instr & 0xFF, ((instr >> 8) & 0xF) * 2
            val = _ror(imm, rot)
            return val, ((val >> 31) & 1) if rot else C, 0
        rm, kind, by_reg = instr & 0xF, (instr >> 5) & 3, (instr >> 4) & 1
        v = self._reg(rm, 12 if by_reg else 8)
        if by_reg:
            n = self.r[(instr >> 8) & 0xF] & 0xFF
            if n == 0:
                return v, C, 1
        else:
            n = (instr >> 7) & 0x1F
        if kind == 0:                                              # LSL
            if n == 0:
                return v, C, by_reg
            if n < 32:
                return (v << n) & 0xFFFFFFFF, (v >> (32 - n)) & 1, by_reg
            return 0, (v & 1) if n == 32 else 0, by_reg
        if kind == 1:                                              # LSR
            if n == 0 or n == 32:
                return 0, (v >> 31) & 1, by_reg
            if n < 32:
                return v >> n, (v >> (n - 1)) & 1, by_reg
            return 0, 0, by_reg
        if kind == 2:                                              # ASR
            if n == 0 or n >= 32:
                return (0xFFFFFFFF if v & 0x80000000 else 0), (v >> 31) & 1, by_reg
            s = v >> n
            if v & 0x80000000:
                s |= (0xFFFFFFFF << (32 - n)) & 0xFFFFFFFF
            return s, (v >> (n - 1)) & 1, by_reg
        if n == 0:                                                 # ROR #0 = RRX (imm form only)
            return ((C << 31) | (v >> 1)) & 0xFFFFFFFF, v & 1, by_reg
        n &= 31
        if n == 0:
            return v, (v >> 31) & 1, by_reg
        return _ror(v, n), (v >> (n - 1)) & 1, by_reg

    def _set_nz(self, v):
        self.N, self.Z = (v >> 31) & 1, 1 if v == 0 else 0

    def _add(self, a, b, carry_in, set_flags):
        r = a + b + carry_in
        res = r & 0xFFFFFFFF
        if set_flags:
            self._set_nz(res)
            self.C = 1 if r > 0xFFFFFFFF else 0
            self.V = 1 if ((a ^ res) & (b ^ res) & 0x80000000) else 0
        return res

    def _sub(self, a, b, carry_in, set_flags):          # a - b - !carry_in
        r = a - b - (0 if carry_in else 1)
        res = r & 0xFFFFFFFF
        if set_flags:
            self._set_nz(res)
            self.C = 1 if r >= 0 else 0
            self.V = 1 if ((a ^ b) & (a ^ res) & 0x80000000) else 0
        return res

    # ---- one instruction ----
    def step(self):
        pc = self.r[15]
        if pc == SENTINEL:
            raise StopIteration
        code = self.m.timing.code
        instr = self.m.read(pc, 32, count=False)
        self.instructions += 1
        if self.pc_trace is not None:
            self.pc_trace.append(pc)
        cond = instr >> 28
        if not self._cond(cond):
            self.cycles += code(pc, True)                 # {cond} false: 1S
            self.r[15] = pc + 4
            return
        top = (instr >> 25) & 7
        if (instr & 0x0FFFFFF0) == 0x012FFF10:            # BX
            target = self.r[instr & 0xF]
            if target != SENTINEL and target & 1:
                raise ValueError("Thumb target 0x%08x not supported" % target)
            self.r[15] = target & ~1
            self.cycles += 0 if target == SENTINEL else code(target, False) + 2 * code(target, True)
            return
        if top == 5:                                      # B / BL
            off = instr & 0xFFFFFF
            if off & 0x800000:
                off -= 0x1000000
            if instr & (1 << 24):
                self.r[14] = pc + 4
            target = (pc + 8 + (off << 2)) & 0xFFFFFFFF
            self.r[15] = target
            self.cycles += code(target, False) + 2 * code(target, True)
            return
        if top == 4:                                      # LDM / STM
            self._block(instr, pc)
            return
        if top in (2, 3):                                 # LDR / STR (word / byte)
            if top == 3 and instr & 0x10:
                raise ValueError("undefined instruction at 0x%08x" % pc)
            self._single(instr, pc)
            return
        if top in (0, 1):
            if top == 0 and (instr & 0x90) == 0x90:
                if (instr & 0x60) == 0:
                    raise ValueError("multiply at 0x%08x not modelled" % pc)
                self._half(instr, pc)
                return
            self._alu(instr, pc)
            return
        raise ValueError("unsupported instruction 0x%08x at 0x%08x" % (instr, pc))

    def _alu(self, instr, pc):
        opcode, S = (instr >> 21) & 0xF, (instr >> 20) & 1
        rn, rd = (instr >> 16) & 0xF, (instr >> 12) & 0xF
        op2, sc, by_reg = self._shifter(instr)
        a = self._reg(rn, 12 if by_reg else 8)
        C = self.C
        res = None
        if opcode == 0x0 or opcode == 0x8:                # AND / TST
            res = a & op2
        elif opcode == 0x1 or opcode == 0x9:              # EOR / TEQ
            res = a ^ op2
        elif opcode == 0x2 or opcode == 0xA:              # SUB / CMP
            res = self._sub(a, op2, 1, S)
        elif opcode == 0x3:                               # RSB
            res = self._sub(op2, a, 1, S)
        elif opcode == 0x4 or opcode == 0xB:              # ADD / CMN
            res = self._add(a, op2, 0, S)
        elif opcode == 0x5:                               # ADC
            res = self._add(a, op2, C, S)
        elif opcode == 0x6:                               # SBC
            res = self._sub(a, op2, C, S)
        elif opcode == 0x7:                               # RSC
            res = self._sub(op2, a, C, S)
        elif opcode == 0xC:                               # ORR
            res = a | op2
        elif opcode == 0xD:                               # MOV
            res = op2
        elif opcode == 0xE:                               # BIC
            res = a & ~op2 & 0xFFFFFFFF
        else:                                             # MVN
            res = ~op2 & 0xFFFFFFFF
        logical = opcode in (0x0, 0x1, 0x8, 0x9, 0xC, 0xD, 0xE, 0xF)
        if S and logical:
            self._set_nz(res)
            self.C = sc
        if opcode in (0x8, 0x9, 0xA, 0xB):
            if not S:
                raise ValueError("MRS/MSR at 0x%08x not modelled" % pc)
            self.cycles += self.m.timing.code(pc, True) + by_reg
            self.r[15] = pc + 4
            return
        if rd == 15:
            raise ValueError("ALU write to pc at 0x%08x not modelled" % pc)
        self.r[rd] = res
        self.cycles += self.m.timing.code(pc, True) + by_reg
        self.r[15] = pc + 4

    def _single(self, instr, pc):
        I, P, U, B, W, L = [(instr >> b) & 1 for b in (25, 24, 23, 22, 21, 20)]
        rn, rd = (instr >> 16) & 0xF, (instr >> 12) & 0xF
        if I:
            saved = (instr & ~(1 << 25)) & ~(1 << 4)          # register offset, shift by immediate
            off, _, _ = self._shifter(saved & ~(1 << 25))
        else:
            off = instr & 0xFFF
        base = self._reg(rn)
        addr = (base + off if U else base - off) & 0xFFFFFFFF if P else base
        width = 8 if B else 32
        t = self.m.timing
        if L:
            v = self.m.read(addr, width)
            if width == 32 and addr & 3:
                v = _ror(v, (addr & 3) * 8)
            self.cycles += t.code(pc, True) + t.data(addr, width, False) + 1
        else:
            v = self._reg(rd, 12) if rd == 15 else self.r[rd]
            self.m.write(addr, width, v)
            self.cycles += t.data(addr, width, False) + t.code(pc, False)
        if not P or W:
            self.r[rn] = (base + off if U else base - off) & 0xFFFFFFFF
        if L:
            if rd == 15:                                      # ldr pc, [pc, #-4]: the veneer form only
                if rn != 15:
                    raise ValueError("LDR pc at 0x%08x: only the veneer form is modelled" % pc)
                self.cycles += t.code(v, False) + 2 * t.code(v, True)
                self.r[15] = v & ~1
                return
            self.r[rd] = v
        self.r[15] = pc + 4

    def _half(self, instr, pc):
        P, U, I, W, L = [(instr >> b) & 1 for b in (24, 23, 22, 21, 20)]
        rn, rd, sh = (instr >> 16) & 0xF, (instr >> 12) & 0xF, (instr >> 5) & 3
        off = (((instr >> 8) & 0xF) << 4) | (instr & 0xF) if I else self.r[instr & 0xF]
        base = self._reg(rn)
        addr = (base + off if U else base - off) & 0xFFFFFFFF if P else base
        t = self.m.timing
        if L:
            if sh == 1:
                v = self.m.read(addr, 16)
            elif sh == 2:
                v = self.m.read(addr, 8)
                v = v - 0x100 if v & 0x80 else v
            else:
                v = self.m.read(addr, 16)
                v = v - 0x10000 if v & 0x8000 else v
            self.r[rd] = v & 0xFFFFFFFF
            self.cycles += t.code(pc, True) + t.data(addr, 16 if sh != 2 else 8, False) + 1
        else:
            if sh != 1:
                raise ValueError("unsupported store form at 0x%08x" % pc)
            self.m.write(addr, 16, self.r[rd] & 0xFFFF)
            self.cycles += t.data(addr, 16, False) + t.code(pc, False)
        if not P or W:
            self.r[rn] = (base + off if U else base - off) & 0xFFFFFFFF
        self.r[15] = pc + 4

    def _block(self, instr, pc):
        P, U, S, W, L = [(instr >> b) & 1 for b in (24, 23, 22, 21, 20)]
        if S:
            raise ValueError("LDM/STM with S at 0x%08x not modelled" % pc)
        rn, lst = (instr >> 16) & 0xF, instr & 0xFFFF
        regs = [i for i in range(16) if lst & (1 << i)]
        n = len(regs)
        base = self.r[rn]
        if U:
            start = base + 4 if P else base
            final = base + 4 * n
        else:
            start = base - 4 * n + (0 if P else 4)
            final = base - 4 * n
        t = self.m.timing
        addr = start
        first = True
        for i in regs:
            if L:
                v = self.m.read(addr, 32)
                self.cycles += t.data(addr, 32, not first)
                self.r[i] = v
            else:
                v = self._reg(i, 12) if i == 15 else self.r[i]
                self.m.write(addr, 32, v)
                self.cycles += t.data(addr, 32, not first)
            first = False
            addr += 4
        if W:
            self.r[rn] = final & 0xFFFFFFFF
        if L:
            self.cycles += t.code(pc, True) + 1
            if 15 in regs:
                target = self.r[15]
                if target == SENTINEL:
                    self.r[15] = SENTINEL
                    return
                self.cycles += t.code(target, False) + 2 * t.code(target, True)
                self.r[15] = target & ~1
                return
        else:
            self.cycles += t.code(pc, False)
        self.r[15] = pc + 4

    def run(self, until=SENTINEL, limit=50_000_000):
        while self.instructions < limit:
            if self.r[15] == until:
                return
            self.step()
        raise RuntimeError("instruction limit reached")


# --------------------------------------------------------------- the ROM -----
def load_rom(path, check=True):
    with open(path, "rb") as f:
        rom = f.read()
    if check:
        sha = hashlib.sha256(rom).hexdigest()
        if len(rom) != ROM_SIZE or sha != ROM_SHA256:
            raise ValueError("not the frozen coord-0001 image: %d B, sha256 %s" % (len(rom), sha))
    return rom


def iwram_image(rom):
    """The .iwram load image inside the ROM: located by the first words of
    prepare_frame and checked against the first words of publish_frame."""
    off = rom.find(PREPARE_HEAD)
    if off < 0 or rom.find(PREPARE_HEAD, off + 1) >= 0:
        raise ValueError("prepare_frame image not found exactly once in the ROM")
    img = rom[off:off + IWRAM_IMAGE_LEN]
    if img[PUBLISH_ADDR - PREPARE_ADDR:PUBLISH_ADDR - PREPARE_ADDR + 8] != PUBLISH_HEAD:
        raise ValueError("publish_frame image is not where the frozen build placed it")
    return off, img


def crc_table():
    tab = bytearray(256)
    for i in range(256):
        c = i
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
        tab[i] = c
    return bytes(tab)


class Model:
    def __init__(self, rom, timing=None, check=True):
        self.rom = rom
        self.timing = timing or Timing()
        self.img_off, self.img = iwram_image(rom)

    def _fresh(self):
        m = Mem(self.rom, self.timing)
        m.iwram[0:IWRAM_IMAGE_LEN] = self.img
        m.iwram[CRC_TAB_ADDR - IWRAM_BASE:CRC_TAB_ADDR - IWRAM_BASE + 256] = crc_table()
        return m

    SCHED = 0x03007F00
    SP = 0x03007E00

    def _sched(self, m, phase, k, digit):
        for i, v in enumerate((phase, k, digit)):
            m.write(self.SCHED + 4 * i, 32, v)

    def prepare(self, frame_id, status, phase, k, digit, trace=False):
        """Cycles of prepare_frame(frame_id, status, &sched) from IWRAM."""
        m = self._fresh()
        self._sched(m, phase, k, digit)
        c = CPU(m)
        c.r[0], c.r[1], c.r[2] = frame_id & 0xFFFFFF, status & 0xFF, self.SCHED
        c.r[13], c.r[14], c.r[15] = self.SP, SENTINEL, PREPARE_ADDR
        if trace:
            c.pc_trace = []
        c.run()
        cnt = m.counts
        acc = {"ewram_r16": cnt.get((0x02, 16, "r"), 0), "ewram_w16": cnt.get((0x02, 16, "w"), 0),
               "rom_r8": cnt.get((0x08, 8, "r"), 0), "iwram_r": sum(v for (r, w, k), v in cnt.items() if r == 0x03 and k == "r"),
               "iwram_w": sum(v for (r, w, k), v in cnt.items() if r == 0x03 and k == "w")}
        return {"cycles": c.cycles, "instructions": c.instructions, "access": acc,
                "op_digit": m.read(OP_DIGIT_ADDR, 8, count=False), "op_sq": m.read(OP_SQ_ADDR, 8, count=False), "trace": c.pc_trace}

    def publish(self, op_digit, op_sq):
        """Cycles of publish_frame() from IWRAM, DMA transfers included."""
        m = self._fresh()
        m.write(OP_DIGIT_ADDR, 8, op_digit)
        m.write(OP_SQ_ADDR, 8, op_sq)
        c = CPU(m)
        c.r[13], c.r[14], c.r[15] = self.SP, SENTINEL, PUBLISH_ADDR
        c.run()
        return {"cycles": c.cycles + m.dma_cycles, "cpu_cycles": c.cycles, "dma_cycles": m.dma_cycles,
                "dma_count": len(m.dma_log), "dma_units": sum(x[2] for x in m.dma_log), "instructions": c.instructions}

    def tail(self, phase_before, k, digit, vc1=173, vmargin=54):
        """Cycles of main's loop from the return of publish_frame to the entry of
        prepare_frame (ROM code): status_measure, sched_advance, frame_id,
        status_byte, the call through the veneer."""
        m = self._fresh()
        sp = 0x03007F00
        for i, v in enumerate((phase_before, k, digit)):
            m.write(sp + 4 * i, 32, v)
        m.write(0x04000006, 16, vc1)
        m.write(0x04000100, 16, 700)
        c = CPU(m)
        c.r[4], c.r[7], c.r[9] = 0x04000000, 0x04000100, 0x51D
        c.r[5], c.r[6], c.r[8] = 100, vmargin, 0
        c.r[10], c.r[11] = 160, 100                 # vc0, t0
        c.r[13], c.r[15] = sp, MAIN_AFTER_PUBLISH
        c.run(until=PREPARE_ADDR)
        return {"cycles": c.cycles, "instructions": c.instructions, "phase_after": m.read(sp, 32), "k_after": m.read(sp + 4, 32)}

    def poll(self, vcount):
        """One iteration of a VCOUNT wait loop in ROM (ldrh / cmp / b), and the
        cycles from prepare_frame's return to its first VCOUNT read."""
        m = self._fresh()
        m.write(0x04000006, 16, vcount)
        c = CPU(m)
        c.r[4], c.r[13], c.r[15] = 0x04000000, 0x03007F00, MAIN_AFTER_PREPARE
        c.step()                                    # ldrh r3, [r4, #6]
        first_read = c.cycles
        c.step()                                    # cmp
        c.step()                                    # bhi (taken while VCOUNT >= 160)
        return {"to_first_read": first_read, "iteration": c.cycles}


# ------------------------------------------------------------ the analysis ---
def frame_classes():
    out = [("ordinary (k>=1, 40<phase<480)", 200, 1, 1), ("pre-glyph (k=0)", 100, 0, 0), ("steady (phase 1)", 1, 1, 1),
           ("steady (phase 39)", 39, 1, 1), ("exit (phase 40)", 40, 1, 1)]
    for d in range(1, 10):
        out.append(("entry digit %d" % d, 0, d, d))
    return out


def unlit_pixels(digit):
    s = SEG[digit]
    lit = 0
    for gy in range(80):
        top, bottom = gy < 44, gy >= 36
        for gx in range(48):
            if ((s & 1) and gy < 8) or ((s & 8) and gy >= 72) or ((s & 0x40) and 36 <= gy < 44) or \
               ((s & 2) and gx >= 40 and top) or ((s & 4) and gx >= 40 and bottom) or \
               ((s & 0x20) and gx < 8 and top) or ((s & 0x10) and gx < 8 and bottom):
                lit += 1
    return 3840 - lit


def analyse(rom, timing=None):
    model = Model(rom, timing)
    res = {"prepare": {}, "publish": {}, "tail": {}, "poll": {}}
    for name, phase, k, digit in frame_classes():
        r = model.prepare(0x1234, 0x36, phase, k, digit)
        res["prepare"][name] = r
    res["publish"]["ordinary (strips only)"] = model.publish(0, 0)
    res["publish"]["entry (strips + digit paint + squares)"] = model.publish(1, 1)
    res["publish"]["steady (strips + squares)"] = model.publish(0, 1)
    res["publish"]["exit (strips + digit erase + squares erase)"] = model.publish(2, 2)
    res["tail"]["ordinary"] = model.tail(200, 1, 1)
    res["tail"]["entry (schedule wrap)"] = model.tail(479, 0, 0)
    res["poll"] = model.poll(170)
    return res


def budget(res, prev_publish="ordinary (strips only)", tail="entry (schedule wrap)"):
    """Cycles available to PREPARE between the end of the previous PUBLISH and the
    start of the next VBlank: FRAME_CYCLES - (poll detection + PUBLISH + loop tail)
    - the reaction to the first VCOUNT read after PREPARE returns."""
    d_pub = res["publish"][prev_publish]["cycles"]
    t_tail = res["tail"][tail]["cycles"]
    react = res["poll"]["to_first_read"]
    it = res["poll"]["iteration"]
    return {"frame_cycles": FRAME_CYCLES, "publish": d_pub, "tail": t_tail, "react": react, "poll_iteration": it,
            "max": FRAME_CYCLES - d_pub - t_tail - react,          # detection at the very first cycle of VBlank
            "min": FRAME_CYCLES - d_pub - t_tail - react - it}     # detection one poll iteration late


def format_report(rom, res, b, res_pf=None, b_pf=None):
    L = LINE_CYCLES
    out = ["coord-0001 cycle model — canonical %d B, sha256 %s" % (len(rom), hashlib.sha256(rom).hexdigest()[:16] + "…"),
           "memory model: IWRAM 1/1/1 · EWRAM 3/3/6 (2 WS) · ROM WAITCNT 4317h N 4 / S 2 per 16-bit · VRAM 1/1/2 · I/O 1",
           "", "PUBLISH (IWRAM code + DMA), against the hardware VMARGIN:"]
    for name, r in res["publish"].items():
        end_line = VBLANK_FIRST + r["cycles"] / L
        out.append("  %-46s %6d cycles = %6.2f lines -> ends at VCOUNT %6.2f -> VMARGIN %d..%d   (%d DMAs, %d units)" % (
            name, r["cycles"], r["cycles"] / L, end_line, 227 - int(end_line) - (1 if end_line % 1 > 0.999 else 0), 227 - int(end_line), r["dma_count"], r["dma_units"]))
    out.append("  measured (RUN 12, GBP-HW-251): ordinary 54 · entry 39 · exit 38 (one exit read 39, the knife-edge)")
    out.append("")
    out.append("LOOP TAIL in ROM (publish return -> prepare entry), no-prefetch bound%s:" % ("" if res_pf is None else " / with-prefetch bound"))
    for name, r in res["tail"].items():
        pf = "" if res_pf is None else " / %d" % res_pf["tail"][name]["cycles"]
        out.append("  %-24s %5d%s cycles (%d instructions)" % (name, r["cycles"], pf, r["instructions"]))
    out.append("  VCOUNT poll: %d cycles from prepare's return to the first read; %d per loop iteration%s" % (
        res["poll"]["to_first_read"], res["poll"]["iteration"], "" if res_pf is None else " (prefetch bound: %d / %d)" % (res_pf["poll"]["to_first_read"], res_pf["poll"]["iteration"])))
    out.append("")
    out.append("BUDGET for PREPARE of an ENTRY frame (previous publish ordinary; tail with the schedule wrap):")
    out.append("  %d - publish %d - tail %d - react %d = %d cycles (poll detected at VBlank start) .. %d (one iteration late)" % (
        b["frame_cycles"], b["publish"], b["tail"], b["react"], b["max"], b["min"]))
    if b_pf is not None:
        out.append("  with-prefetch bound: %d .. %d" % (b_pf["max"], b_pf["min"]))
    lo = min(b["min"], b_pf["min"] if b_pf else b["min"])
    hi = max(b["max"], b_pf["max"] if b_pf else b["max"])
    out.append("")
    out.append("PREPARE (IWRAM code; EWRAM tables; one ROM byte per glyph pixel):")
    out.append("  %-32s %8s %7s %6s %6s %6s %6s %5s  %s" % ("frame class", "cycles", "lines", "unlit", "ewr16", "eww16", "rom8", "ops", "vs budget [%d .. %d]" % (lo, hi)))
    for name, r in res["prepare"].items():
        unlit = unlit_pixels(int(name.split()[-1])) if name.startswith("entry") else "-"
        c = r["cycles"]
        a = r["access"]
        verdict = "OVER by %d..%d -> VBlank MISSED, previous FRAME_ID captured twice" % (c - hi, c - lo) if c >= hi else \
                  ("UNDER by %d..%d -> publishes in the next VBlank" % (lo - c, hi - c) if c < lo else "INSIDE the uncertainty band")
        out.append("  %-32s %8d %7.2f %6s %6d %6d %6d %5s  %s" % (name, c, c / L, unlit, a["ewram_r16"], a["ewram_w16"], a["rom_r8"],
                                                                 "%d/%d" % (r["op_digit"], r["op_sq"]), verdict))
    return "\n".join(out)


def sensitivity(rom, ws_values=(1, 2, 3), rom_n_values=(3, 4, 5)):
    """The verdict for the four RUN 12 entries under every combination of the two
    memory-timing terms that are not pinned by the ARM7TDMI datasheet, beside
    the PUBLISH end lines those same terms predict (the hardware read 54/39/38)."""
    rows = []
    for ws in ws_values:
        for rn in rom_n_values:
            t = Timing(ewram_ws=ws, rom_n=rn, rom_s=2)
            m = Model(rom, t)
            pub = {k: m.publish(*v)["cycles"] for k, v in (("ordinary", (0, 0)), ("entry", (1, 1)), ("exit", (2, 2)))}
            vm = {k: 227 - int(VBLANK_FIRST + c / LINE_CYCLES) for k, c in pub.items()}
            res = {"publish": {"ordinary (strips only)": {"cycles": pub["ordinary"]}},
                   "tail": {"entry (schedule wrap)": m.tail(479, 0, 0)}, "poll": m.poll(170)}
            b = budget(res)
            entries = {d: m.prepare(0x1234, 0x36, 0, d, d)["cycles"] for d in (1, 2, 3, 4)}
            verdict = "".join("M" if entries[d] >= b["max"] else ("-" if entries[d] < b["min"] else "?") for d in (1, 2, 3, 4))
            rows.append({"ewram_ws": ws, "rom_n": rn, "vmargin": vm, "budget": (b["min"], b["max"]), "entries": entries, "pattern": verdict,
                         "calibrated": (vm["ordinary"], vm["entry"]) == (54, 39) and vm["exit"] in (38, 39)})
    return rows


def format_sensitivity(rows):
    out = ["SENSITIVITY: verdict pattern for entries k=1..4 (M = VBlank missed, - = made, ? = inside the band); observed M--M",
           "  ews rom_n  VMARGIN ord/ent/exit (hw 54/39/38|39)  calib   budget            d1      d2      d3      d4   pattern"]
    for r in rows:
        v = r["vmargin"]
        out.append("  %d   %d      %2d / %2d / %2d                       %-5s   %d..%d  %6d  %6d  %6d  %6d   %s" % (
            r["ewram_ws"], r["rom_n"], v["ordinary"], v["entry"], v["exit"], "yes" if r["calibrated"] else "no", r["budget"][0], r["budget"][1],
            r["entries"][1], r["entries"][2], r["entries"][3], r["entries"][4], r["pattern"]))
    return "\n".join(out)


def selftest():
    """Hand-assembled sequences: the cycle rules and the semantics they rest on."""
    rom = bytes(0x1000)
    t = Timing()
    m = Mem(rom, t)

    def put(addr, words):
        for i, w in enumerate(words):
            m.write(addr + 4 * i, 32, w)
    # add r0, r1, r2 ; subs r3, r0, #1 ; ldr r4, [r5] ; strh r4, [r6] ; b +0 (to sentinel via bx lr)
    put(0x03000000, [0xE0810002, 0xE2503001, 0xE5954000, 0xE1C640B0, 0xE12FFF1E])
    m.write(0x02000010, 32, 0xDEADBEEF)
    c = CPU(m)
    c.r[1], c.r[2], c.r[5], c.r[6], c.r[14], c.r[15] = 5, 7, 0x02000010, 0x02000020, SENTINEL, 0x03000000
    c.run()
    assert c.r[0] == 12 and c.r[3] == 11 and c.r[4] == 0xDEADBEEF and m.read(0x02000020, 16) == 0xBEEF
    # cycles: add 1S=1 ; subs 1 ; ldr 1S + 1N(EWRAM 32 = 6) + 1I = 8 ; strh 1N(EWRAM 16 = 3) + 1N code = 4 ; bx to sentinel 0
    assert c.cycles == 1 + 1 + 8 + 4, c.cycles
    # conditional false costs 1S; a taken branch 2S+1N (IWRAM: 3)
    put(0x03000100, [0xE3500000, 0x03A01001, 0x13A01002, 0xEA000000, 0xE3A02007, 0xE12FFF1E])  # cmp r0,#0; moveq r1,#1; movne r1,#2; b +0 (skip next); mov r2,#7 (skipped); bx lr
    c = CPU(m)
    c.r[0], c.r[14], c.r[15] = 0, SENTINEL, 0x03000100
    c.run()
    assert (c.r[1], c.r[2]) == (1, 0) and c.cycles == 1 + 1 + 1 + 3, c.cycles
    # push / pop: stm (n-1)S+2N, ldm nS+1N+1I
    put(0x03000200, [0xE92D4030, 0xE8BD4030, 0xE12FFF1E])   # push {r4,r5,lr}; pop {r4,r5,lr}; bx lr
    c = CPU(m)
    c.r[4], c.r[5], c.r[13], c.r[14], c.r[15] = 9, 8, 0x03007F00, SENTINEL, 0x03000200
    c.run()
    assert c.r[13] == 0x03007F00 and c.cycles == (2 + 2) + (3 + 1 + 1), c.cycles
    # ROM code fetch costs and a ROM byte read from IWRAM code
    rom2 = bytearray(0x1000)
    rom2[0x758] = 0x5B
    m2 = Mem(bytes(rom2), t)
    for i, w in enumerate([0xE59F3008, 0xE5D33000, 0xE12FFF1E, 0x00000000, 0x08000758]):   # ldr r3,[pc,#8]; ldrb r3,[r3]; bx lr; pad; .word
        m2.write(0x03000300 + 4 * i, 32, w)
    c = CPU(m2)
    c.r[14], c.r[15] = SENTINEL, 0x03000300
    c.run()
    assert c.r[3] == 0x5B and c.cycles == (1 + 1 + 1) + (1 + 4 + 1), c.cycles    # ldr from IWRAM literal; ldrb from ROM N = 4
    # a shifter carry: movs r0, r1, lsr #1 sets C from bit 0
    put(0x03000400, [0xE1B000A1, 0xE12FFF1E])
    c = CPU(m)
    c.r[1], c.r[14], c.r[15] = 3, SENTINEL, 0x03000400
    c.run()
    assert c.r[0] == 1 and c.C == 1
    # DMA: 28 units, IWRAM -> VRAM, 32-bit: 1 + 2 + 27 * (1 + 2) + 2 = 86
    m3 = Mem(rom, t)
    m3.write(0x040000D4, 32, 0x03000970)
    m3.write(0x040000D8, 32, 0x06000000)
    m3.write(0x040000DC, 32, 0x8400001C)
    assert m3.dma_cycles == 86, m3.dma_cycles
    m3.write(0x040000D4, 32, 0x02000000)
    m3.write(0x040000DC, 32, 0x84000019)          # 25 units EWRAM -> VRAM: 6 + 2 + 24 * (6 + 2) + 2 = 202
    assert m3.dma_cycles == 86 + 202, m3.dma_cycles
    return True


def main(argv):
    if len(argv) >= 1 and argv[0] == "check":
        selftest()
        print("coordtime: self-test ok")
        return 0
    if len(argv) >= 1 and argv[0] == "analyse":
        path = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build", "stimulus", "agb-coord", "agb-coord.gba")
        rom = load_rom(path)
        res = analyse(rom)
        b = budget(res)
        res_pf = analyse(rom, Timing(rom_code_s=2))           # every ROM opcode half served by the prefetch buffer
        b_pf = budget(res_pf)
        print(format_report(rom, res, b, res_pf, b_pf))
        print()
        print(format_sensitivity(sensitivity(rom)))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
