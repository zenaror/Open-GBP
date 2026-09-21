# The input path — static basis for Phase 5 (2026-09-21, GitHub Issue #18)

Status of this document: **research**. It reconstructs the keypad path of the
physical Game Boy Player from the references, on paper, before Open-GBP has
ever written the KEYPAD window. Nothing here is consolidated documentation and
nothing is promoted. As written for Issue #18, no code existed for any of it
and **no bit order was adopted, implemented, tabulated as Open-GBP's own, or
defaulted**; the update below records what Issue #19 changed, and §1–§9 are
left as they were written. Evidence
classes as in `EVIDENCE.md`: **F (static)** = a property of the reference's
code or data that can be recomputed from the binary; **C** = corroborated by
independent sources; **H** = hypothesis; **U** = unknown. Where a statement
is a *policy* of this project it is labelled **POLICY** and is never a device
fact. Decompiled output derived from the proprietary binaries lives under
`build/analysis/ghidra18/` (ignored, never committed); this page describes
behaviour and cites addresses so the analysis can be reproduced headlessly
(`tools/README.md`, "Reverse-engineering workflow").

> **Update, 2026-09-21 (GitHub Issue #19).** The architecture of §7 is
> implemented — `src/gbp/gbp_input.c` behind the existing transport boundary,
> the step as the first statement of the stream probe's pump slot — and built
> as the candidate `stream-0014` (commit `0ff8355`, SHA-256 `ef76a170c10d335e62c017e53f74c60e410e44f5ce2fbca6774ab43c68ec0b9c`),
> which is **not executed anywhere**; no run is pre-registered. By the
> Operator's decision the encoding descriptor is now filled with the
> CORROBORATED assignment of §5 — bit 8 = L, bit 9 = R — in exactly one
> place, as data, with its status and its falsifier at the definition, so
> that the first physical run falsifies or keeps it. Nothing is promoted:
> `REGISTERS.md` keeps H, U-GBP-010 stays OPEN, and the order is still not a
> physical fact. The refresh policy §7 left open was frozen by the Issue:
> write on change plus a refresh every 5 ms, the Disc's period. EVIDENCE
> GBP-KEY-006 carries the software facts.

**The physical record starts from nothing.** Open-GBP has never issued a
KEYPAD write: every probe from GBP-PROBE-001 to RUN 13 kept the window
untouched by design (`INITIALIZATION.md` §9 R6, §14). The only keypad
evidence in the project before this checkpoint is static — GBP-KEY-001 and
GBP-VID-011 — and everything this checkpoint adds (GBP-KEY-002 … GBP-KEY-005)
is static as well. No confidence is inherited from the video work: the video
plane was measured on the device; the keypad plane has not been.

The document keeps three layers apart and does not let a statement from one
migrate into another:

```text
L1  the GBS-DOL KEYPAD window            what the device is written    (the device)
L2  the logical GBA button set           what a GBA program reads       (the GBA, not the GBP)
L3  GameCube controller -> logical GBA   what this project chooses      (POLICY, never a device fact)
```

## 1. L1 — the GBS-DOL KEYPAD window, as the references write it

| Property | What the references do | Status | Provenance |
| --- | --- | --- | --- |
| Window | register index 0xC, ARAM address `base + 0xC00000` (+ offset); written, never read, by every reference | F (static) | Disc `0x80089e40` (DMA to `base + 0xC00000`, direction write); GBI `0x8000c194` (64 B at `base + 0xCFFFE0`), `0x8000c060` (32 B at `base + 0xC00000`); Dolphin `GBPRegister::Keypad = 0x1c` = index 0xC (GBP-KEY-001) |
| Field | a 16-bit big-endian value in bytes 0x1E–0x1F of the 32-byte block | F (static) | Disc `0x80089e40`: stores `value >> 8` at staging byte 0x1E and `value & 0xFF` at 0x1F, flushes, DMAs the 32-byte staging buffer (the other 30 bytes are whatever the previous transfer left — the same convention as its IRQ write `0x80089ff4`); GBI `0x80015da0` / `0x80015da4` / `0x80015ddc`: the u16 replicated sixteen times, `hi lo hi lo …`, so bytes 0x1E/0x1F carry it too; Dolphin reads `data[0x1e]` (hi) and `data[0x1f]` (lo) |
| Offsets the software uses | `0x00000` (Disc, GBI at thread start), `0xFFFE0` (GBI's per-pass 64-byte block, whose second half lands at `base + 0xD00000` = IRQ), and `0x00020` (the second half of GBI's sleep pulse, below) | F (static) for the software; the device's mirroring is C for 0x00000 / 0xFFFE0 (GBP-HSP-004) and **not observed** for 0x00020 | GBI builds at `0x8000c184` and writes at `0x8000c194` (`0xcfffe0`, 64 B), builds at `0x8000c4b4` and writes at `0x8000c4c4` (`0xc00000`, 64 B); Dolphin ignores the offset (`address >> 20`) |
| Polarity at this window | **1 = pressed**: both drivers set bits for the buttons the user holds; the Disc's detection handshake sets bits 0xF0 to press the four directions; GBI's sleep pulse sets 0x0304 | F (static) for what the software writes; the device side is C through one external observation (§1.1) | Disc `0x8000822c` (mapping), `0x8008c31c` (injection); GBI `0x8000bf30`; GBP-KEY-001 |
| Bit assignment written by the references | bits 0–7 = A, B, Select, Start, Right, Left, Up, Down — the KEYINPUT order (§2); **bit 8 = L, bit 9 = R** — the reverse of KEYINPUT's bit 8 = R, bit 9 = L; bits 10–15 never set | F (static) per reference; the agreement of the Disc and GBI is **C** for the encoding the references target; what the device does with bits 8/9 is **not measured** (§5, U-GBP-010) | Disc `0x8000822c`; GBI `0x8000bf30` (`0x8000c904` region); Dolphin `HSP_DeviceGBPlayer.cpp:601–605` |
| Opposite directions | the Disc's setter clears both bits of a pair when both are set: `(v & 0xC0) == 0xC0 → v &= ~0xC0` (Up + Down), `(v & 0x30) == 0x30 → v &= ~0x30` (Left + Right) — a driver policy; it confirms the Disc treats bits 4/5 and 6/7 as the Right/Left and Up/Down pairs | F (static) | Disc `0x8008ad30` |
| Write cadence, Disc | on every HSP interrupt that carries a pending source, inside the handler right after the IRQ write-back and before the callbacks (the setter's one-shot callback, if one was given, is invoked right after that write and cleared), and on every 5.000 ms periodic tick while the AGB runs (state 2), i.e. ≥ 200 Hz; the word itself changes only when the application calls the setter | F (static) | Disc `0x8008af08+0x74`, `0x8008b1ac` (two call sites `0x8008b900`, `0x8008bac4`); the tick period GBP-VID-014 |
| Write cadence, GBI | once per service pass — every HSP interrupt — inside the same 64-byte DMA as the IRQ acknowledge (first 32 bytes KEYPAD := pad word, second 32 bytes IRQ := `read \| 0x8000`), plus `KEYPAD := 0` once at thread start before the CONTROL transform | F (static) | GBI `0x8000c04c`, `0x8000c060`, `0x8000c184` / `0x8000c194`; DEVLOG 2026-09-15 "GBI write layouts" |
| GBI's sleep pulse | on IRQ source 0x0010 it writes one 64-byte block at `base + 0xC00000`: first half 0x0304, second half 0x0300 — the second half lands at offset 0x20 of the KEYPAD window; 0x0304 sets bits 2, 8 and 9 (Select + both of bits 8/9), 0x0300 keeps bits 8 and 9. **It sets bits 8 and 9 together and discriminates nothing about their order** | F (static) | GBI `0x8000c4b4`; GBP-KEY-001 |
| Dolphin's model | `SetKeys(((hi & 1) << 9) \| ((hi & 2) << 7) \| lo)`: block byte 0x1E bit 0 → GBA key 9 (L), bit 1 → GBA key 8 (R), byte 0x1F → keys 0–7 unchanged; the source comment reads "L/R triggers (need to be flipped)". A model, AUXILIARY, not evidence; recorded in `REGISTERS.md` as **H** and left there | model | `external/dolphin` `c185d27`, `Source/Core/Core/HW/HSP/HSP_DeviceGBPlayer.cpp:601–605` |
| Physical status | **none**: no KEYPAD write has been issued on this project's hardware; nothing above is a physical FACT | — | `INITIALIZATION.md` §14 |

### 1.1 The one external corroboration, and its exact width

GBATEK ("Unlocking and Detecting Gameboy Player Functions") records, from the
AGB side, that while a game shows the Game Boy Player logo "the joypad data
will switch between values 03FFh (2 frames duration) and 030Fh (1 frame
duration)" — KEYINPUT with bits 4–7 low, i.e. Right, Left, Up and Down all
pressed. The Start-up Disc's detector (GBP-VID-011) drives exactly bits 0xF0
of its KEYPAD word for five ticks and clears them for five (`0x8008c31c`,
a 10-tick cycle of 50 ms at the 5 ms rate), once its embedded frame — the
44-colour logo GBATEK describes — has matched for 40 consecutive blocks.
The two observations fit: the bits the Disc sets at bits 4–7 of the window
are the bits the AGB sees cleared at KEYINPUT bits 4–7. That corroborates
the polarity (1 = pressed at the window) and the low-byte direction positions
**for those four bits**, from an external hardware observation and the
official driver together (GBP-KEY-005, C). It says nothing about bits 0–3 or
8–9, and it is not an Open-GBP measurement.

## 2. L2 — the logical GBA button set (the GBA, not the GBP)

From GBATEK `4000130h - KEYINPUT` (`external/gbatek`, commit `64b5087a`):

```text
bit  0 A   1 B   2 Select   3 Start   4 Right   5 Left   6 Up   7 Down   8 R   9 L   10-15 unused
0 = pressed, 1 = released; read once per frame is the recommended practice
```

mGBA's `enum GBAKey` (`include/mgba/internal/gba/input.h`) uses the same
numbering (A = 0 … R = 8, L = 9) as its emulator-side logical set, 1 =
pressed; Dolphin hands that enum's bit layout to its core (`SyncJoybus(…,
m_keys)`). Two things distinguish L2 from L1 and must not be blurred: the
KEYPAD window's polarity is the opposite of KEYINPUT's, and the references
write L and R at bits 8 and 9 in the opposite order to KEYINPUT's R and L.
Whether the device performs that exchange is exactly what is not measured
(§5).

## 3. L3 — GameCube controller → logical GBA: the references, and the policy

### 3.1 What each reference maps (F (static) for each; none is a device fact)

| Source | A | B | Select | Start | D-pad | Main stick | L / R | Z | X / Y | Other |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Start-up Disc** `0x8000822c`, default mode | A | B | X **or** Y | Start | D-pad | stick-derived direction flags of the disc's extended pad word (bits 24–27) feed the same four bits | digital L, R (SDK bits 6, 5) → bits 8, 9 | not sent (the Disc's own menu, per GBATEK) | Select | a second pad word OR-ed in (`0x80091ac4`, another device class, not traced); `0x8000a2e8` sends 0 (release all) on its path |
| **Start-up Disc**, alternate mode (`iVar1 == 1`) | A | B | L **or** R | Start | D-pad | bits 24–27 and 16–19 (two stick sources) | Y → bit 8, X → bit 9 | — | L / R | GBATEK: "optionally X/Y can be swapped with L/R" |
| **GBI** `0x8000bf30`, GameCube-pad tables (four entries each, OR-ed) | A or analogue A > 100 | B or analogue B > 100 | Z; and Y unless an option redirects it | Start | D-pad | 12-byte-stride table (the libogc `PADStatus` layout): both axes at ±50; 10-byte-stride table: X axis at ±25 | digital L, R or trigger > 100 → bits 8, 9 | Select | Y = Select (or the option's flag); X not sent | N64 pads (6-byte stride): L (0x2000) → bit 8, R (0x1000) → bit 9, stick as D-pad at ±40; a device read at `r13 + 0x1a8` with its own table (0x1400 → bit 8, 0x2800 → bit 9); two sub-tables chosen by an analogue signature inside the first table (not traced) |
| **Enhanced mGBA** `src/platform/wii/main.c:1373–1383, 1420` | A | B | X (and Y as an alias) | Start | D-pad | axis bound to Left/Right and Up/Down with dead zone 0x30 | digital L, R only (`PAD_TRIGGER_L/R` = the click bits) | GUI cancel / menu | Select | Wii remotes, Classic, DRC — not GameCube |

Divergences preserved, not resolved: Select is X or Y (Disc), X (mGBA), Z
and Y (GBI); Z is a menu button (Disc, mGBA) or Select (GBI); the triggers
count as L/R on their digital click only (Disc as traced, mGBA) or also past
an analogue threshold (GBI, > 100 of 255); the stick threshold differs (GBI
50 or 25 depending on the table, mGBA 48, the Disc's not traced); GBI reads
four ports and several device classes, the Disc's traced path reads one pad
structure. None of these is a hardware question.

### 3.2 The policy — options and a recommendation (POLICY)

Chosen by this project, revisable, never promoted as a device fact:

| Question | Options | Recommended | Why |
| --- | --- | --- | --- |
| A, B, Start, D-pad | 1:1 | 1:1 | every reference |
| Select | X and Y (Disc) · X (mGBA) · Z and Y (GBI) · configurable | X and Y both = Select; configurable later | the official mapping; leaves Z for the runtime |
| Z | to the game (Select) · reserved for the runtime's own UI | reserved, never sent to the game | the Disc reserves it for its menu; Open-GBP will need one button it owns |
| L / R | digital click only · click or analogue ≥ threshold | digital click by default; an analogue threshold as an option, off by default | the Disc as traced uses the click; GBI's 100/255 is a reasonable option, not a default to invent |
| Main stick | ignored · D-pad above a threshold | D-pad above a threshold, threshold a named constant validated in Phase 5's own test | all three references do it; the value (GBI 50 or 25, mGBA 48, the Disc's unknown) is not evidence |
| C-stick | ignored · D-pad (Disc alternate mode) | ignored | no reference maps it by default |
| Opposite directions held together | pass through · clear both | clear both (the Disc's setter) | a real D-pad cannot do it; the official driver filters it |
| Ports | port 1 · all four OR-ed (GBI) | port 1 first; more ports later | smallest correct thing |
| Hold / turbo | none · an option like GBI's Y flag (not traced) | none | Phase 9 territory |

**Addendum 2026-09-21 (GitHub Issue #22):** the Operator's recollection of
the Start-up Disc's behaviour on this hardware corroborates every row of
this table that the Disc decides — see §10.2 (OPERATOR OBSERVATION, a
recollection of past use; GBP-KEY-007). It changes no recommendation.

## 4. Reference survey — provenance and authority (Deliverable B)

| Reference | What was consulted | Authority |
| --- | --- | --- |
| **Nintendo Game Boy Player Start-up Disc** — `input/gbp-disc.iso` (`947a5523…177d`), `sys/main.dol` extracted 2026-09-21 with `tools/gciso.py`, sha256 `3dd3692f5931516b80915b38e795aa6092e4d4db43cd652bc396e0cba2b11b5d` (the identity `REGISTERS.md` records) | headless Ghidra 12.1.3 + GameCubeLoader, `tools/ghidra/OpenGbpFunc.java` decomp / refs / callsites: `0x80089e40` (KEYPAD write primitive), `0x8008ad30` (keypad state setter, callers `0x8000822c`, `0x8000a2e8`), `0x8000822c` (the controller → KEYPAD mapping), `0x8008b1ac` (5 ms tick), `0x8008c31c` (detection injection), `0x8008af08` (handler, KEYPAD site `+0x74`); the keypad word is the small-data global `r13 − 0x7028` (stores at `0x8008aab4`, `0x8008ad84/88/b8`, `0x8008b8e4`, `0x8008c350`) | **primary software reference** (official); its code is F (static); its intent for the hardware is C at most |
| **Game Boy Interface**, Standard Edition — `input/gbi/apps/gbi/gbi.dol` `8083636c1b341e712859f40356bf5934f4622fab7e7a658bd7e8cb4feeb616b1`, unpacked 2026-09-21 with `tools/gbi_unpack.py` to `0b2c44ea75f85aa8d64ac3ad167c400f778becc58e886c53a44b9a67f46384b0` (734 732 B), wrapped with `tools/bin2dol.py` at `0x80003100` | the same headless workflow: `0x8000bf30` (service thread: pad reading, mapping, the 64-byte KEYPAD + IRQ block, the sleep pulse), `0x80015da0` / `0x80015da4` / `0x80015ddc` (block builders), `0x8000c050` / `0x8000c060` (`KEYPAD := 0`); `_SDA_BASE_ = 0x800b4b20` read from the entry code, so the keypad word `r13 + 0x37c` = `0x800b4e9c` (stores at `0x8000c04c`, `0x8000c0f0`, `0x8000c904`, `0x8000cbc4`; read at `0x8000c174`) | **independent mature implementation**, not official; F (static) for its code |
| GBI's controller ROMs shipped in `input/gbi/`: `controller-gc.gba` (3 144 B, `d42070e17c4a45c7826ecdad63ab0d38420bdd70b34e5c69860ddbb95d737d82`), `controller-analog-gc.gba` (3 188 B, `66d510cf496e023a2b68ce7dd4a7db9f1e43fe383b856336bd8be197e12fa2c8`), `controller-n64.gba` (10 748 B, `c7cd5c77e5e327b78d35dbaebad7b6400f36b5c06ded952ed718997c694272ea`), `controller-analog-n64.gba` (10 772 B, `865dcee3877571930841f28e4ee7129782a7dcc7a1ab0aa1d0bfa0e7b3891cea`) | **present, hashed, not analysed**: GBA-side programs that display the controller state; behavioural references only, **proprietary, never a donor** — anything Open-GBP needs it writes itself (a future controlled stimulus is designed from scratch) | behavioural reference, not consulted for any claim here |
| **Dolphin** — `external/dolphin` `c185d27ede09771fe93a3b520c576f646f937ed9`, `Source/Core/Core/HW/HSP/HSP_DeviceGBPlayer.cpp` lines 595–606 (`case GBPRegister::Keypad`), `SetKeys`, `SyncJoybus` | the keypad model (§1) | **AUXILIARY**; a model, never hardware truth; its L/R order stays **H** in `REGISTERS.md` |
| **Enhanced mGBA** — **obtained 2026-09-21**: `external/mgba`, https://github.com/extremscorner/mgba, branch `20251124` (the repository's default), commit `8692b26b6d882c049bc70958e0ef8ba0e607a4b7` (shallow clone, ignored by Git, recorded in `external/README.md`) | `src/platform/wii/main.c` (`_pollGameInput`, `_mapKey` bindings, `mInputBindAxis`), `include/mgba/internal/gba/input.h`; the `gamecube/` platform directory holds only a CMake toolchain file — the GameCube build uses the Wii sources | a GameCube-side reference for polling and mapping (**L3**) and for the logical set (**L2**); it is an emulator: it never touches the physical KEYPAD window and carries **no authority on L1** (`CLAUDE.md` §6.6). The Orchestrator's note that the vendored `external/dolphin/Externals/mGBA` is a different thing (Dolphin's core) stands; that tree was not used for this survey |
| **GBATEK** — `external/gbatek` `64b5087aa45cd0187b8b239d77e54ee5eb2917d1`, `gba.md`: "4000130h - KEYINPUT", "Gameboy Player (Gamecube Joypad)", "Unlocking and Detecting Gameboy Player Functions" | L2, the documented official controller mapping (a figure, with "(?)" marks), the AGB-side detection observation (§1.1) | third-party documentation; the detection value is an external hardware observation |
| **libogc2** — `external/libogc2` `ca03fb75…392a`, `include/ogc/pad.h`, `libogc/pad.c` | `PADStatus` (button, sticks, triggers, analogue A/B, err), `PAD_ScanPads` / `PAD_ButtonsHeld` / `PAD_TriggerL` / `PAD_StickX`; the SI hardware polls the pads (`SI_EnablePolling`) and `PAD_ScanPads` copies the last response — so the sample instant precedes the call by up to one SI polling period | the toolchain's controller API (§7, §8) |

## 5. The static attempt on U-GBP-010 (Deliverable C)

U-GBP-010 asks the physical L/R bit order of the KEYPAD word. What the
binaries say, extracted independently for each reference and lined up
against the KEYINPUT order of §2 (word bit → GBA button the reference means
by it):

```text
word bit         0   1   2       3      4      5     6    7     8   9
KEYINPUT (L2)    A   B   Select  Start  Right  Left  Up   Down  R   L
Start-up Disc    A   B   X|Y     Start  Right  Left  Up   Down  L   R     0x8000822c, default mode
Start-up Disc    A   B   L|R     Start  Right  Left  Up   Down  Y   X     0x8000822c, alternate mode: Y -> bit 8, X -> bit 9, identifying nothing about L/R
GBI, GC pads     A   B   Z       Start  Right  Left  Up   Down  L   R     0x8000bf30
GBI, N64 pads    A   B   Z       Start  Right  Left  Up   Down  L   R     0x8000bf30 (0x2000 -> bit 8, 0x1000 -> bit 9)
Dolphin model    A   B   Select  Start  Right  Left  Up   Down  L   R     HSP_DeviceGBPlayer.cpp:605 (hi bit 0 -> key 9)
```

- Bits 0–7: every reference writes the KEYINPUT order — F (static) each,
  C across them; for bits 4–7 additionally C through the external detection
  observation (§1.1).
- Bits 8–9: the Start-up Disc's default mode puts **L** at bit 8 and **R**
  at bit 9 (its alternate mode moves Y and X there and says nothing about
  L/R); GBI does the same for GameCube pads and, independently through the
  N64 wire format (byte 1 bit 5 = L, bit 4 = R), for N64 pads; Dolphin's
  model does the same and says so in its comment. The Disc and GBI are independent implementations of the same
  hardware and one of them is the official driver. Under `AGENTS.md`, what
  each writes is **F (static)**, and their agreement makes the encoding they
  target **CORROBORATED**. It is **not** a physical FACT: no measurement shows
  the GBS-DOL routing bit 8 to the AGB's L line, and the routing cannot be
  read out of the GameCube side (the window is write-only in every
  reference; the AGB is the only observer). GBI's `0x0304` was **not** used
  as evidence — it sets bits 8 and 9 together.

```text
U-GBP-010 static attempt (2026-09-21): RESOLVED STATICALLY at CORROBORATED —
the references' encoding is bit 8 = L, bit 9 = R (the reverse of KEYINPUT);
the physical routing is not established, and U-GBP-010 stays OPEN on its
own closing condition (a physical test with a game that distinguishes L/R).
```

What this changes and what it does not: `REGISTERS.md` keeps Dolphin's order
at H (nothing here touches the promoted pages); no order is adopted or
defaulted in Open-GBP; the entry in `UNKNOWNS.md` records what was learned
and stays open. What would raise CORROBORATED to FACT: a machine-decoded
observation on this project's hardware of what the AGB reads when each bit
is written alone — a project-owned stimulus that publishes KEYINPUT into its
video frames, joined to the runtime's own write schedule (§6).

## 6. Why no physical experiment is designed here (Deliverable D)

Deliverable D was conditional on §5 returning NOT RESOLVABLE STATICALLY; it
did not, so no experiment is designed and none is designed "for
completeness". The item's own closing condition is a physical test with a
game, which Phase 5's first KEYPAD-writing run will provide as OPERATOR
OBSERVATION at no extra hardware cost. If the Orchestrator wants FACT rather
than CORROBORATED before an encoding is implemented, the instrument is the
ten-bit stimulus sketched in one sentence at the end of §5, designed in its
own Issue with its own pre-registration; it is not started here.

## 7. Input architecture on paper (Deliverable E)

Nothing below exists in code. Names are proposals. The hard constraint holds:
the video runtime, the validated service path (read → drain → ACK → PI clean
→ re-arm → wait), Policy A, the witness layer and every frozen format are
untouched by the design — the input step is *additive*, in the slot the
runtime already reserves for non-service work.

```text
                 host-testable, no hardware                       transport boundary (exists)
  PADStatus ──► gbp_input_map ──► logical GBA set ──► gbp_keypad_encode ──► u16 word ──► gbp_keypad_write ──► gbp_transport.write_block
               (L3 POLICY, data)                    (encoding DESCRIPTOR, data)            (32-byte block, GBI or Disc layout)
                                                                                              ├── real backend  (src/platform/hsp_backend.c, ARAM DMA)
                                                                                              ├── mock backend  (tests/mocks)
                                                                                              └── replay backend (recorded transfers)
```

| Element | Design | Testable how |
| --- | --- | --- |
| `gbp_input_map` | pure function: `PADStatus` (button word, sticks, triggers, analogue A/B) → a logical GBA button set (§2 numbering), driven by a **policy table** (§3.2) and thresholds passed in, never compiled-in as truth | host tests over synthetic `PADStatus` values: every button, stick thresholds at the boundary, opposite-direction filtering, ports |
| `gbp_keypad_encode` | pure function: logical set → the 16-bit KEYPAD word under an **encoding descriptor** (ten bit positions and the polarity) supplied as data. The descriptor is filled from evidence; **until the physical result exists it is not defaulted**, and the host tests test the *logic* (a descriptor is applied bit for bit, unused bits stay 0, encode∘decode is the identity) — never a hypothesised order | host tests with arbitrary synthetic descriptors |
| `gbp_keypad_write` | one 32-byte `write_block` at `base + (0xC << 20)`, layout chosen once and recorded: GBI's u16-replicated block (`gbp_regwrite_u16_layout` already exists for the IRQ register) or the Disc's bytes-0x1E/0x1F-only block; synchronous, bounded by the transport's polled completion like every register write; records `t_write` (§8) | through the existing mock and replay backends: the transfer's address, length and bytes are asserted like any other register write |
| Poll | `PAD_ScanPads()` + `PAD_ButtonsHeld / PAD_TriggerL / PAD_StickX …` from the **main loop**, never from the ISR | mock pad state on the host |

**Placement relative to the service cycle.** The runtime's service loop has
exactly one place for non-service work: after the RE-ARM, the pump slot,
which runs only when no cause is pending and yields the moment one is
(`gbp_vqueue_pump(cfg->stream, pending_pre)`, §V5.26 / §11; the consumer
slice has run there in every streaming run without an observable transport
effect, GBP-HW-140/150). The input step goes in that slot, before the
consumer slice or after it (to be decided by measurement, not here): poll,
map, encode, and — when the word changed or a refresh is due — one 32-byte
write. It never runs inside the ISR, never between the service read and the
re-arm, never overlaps a service DMA (single-threaded; the DMA engine is idle
in the slot), and its cost is one bounded transfer of the class HSP.md §3
measured. It does not touch `submit_ready()`, the witness, the disposition
trace or any format.

**Refresh policy (open, to be measured).** The Disc rewrites the word ≥ 200
times a second whether or not it changed; GBI rewrites it on every
interrupt. Whether the device *needs* a refresh for a held key is unknown
(nothing in the references says it does; both simply do it). Options: write
on change only; write on change plus a periodic refresh (the Disc's 5 ms as
the reference value); write every pump slot. Recommended for the first
implementation: on change plus a periodic refresh, period a named constant,
with the first physical run reporting whether a held key ever dropped
without a refresh — a measurable question, not a guess.

**Not proposed, and why.** GBI's combined 64-byte KEYPAD + IRQ acknowledge
would fold the keypad write into the ACK transaction of the validated
service path; that is a change to the service path and therefore a stop
condition, not a design choice. The Disc's in-handler write is inside the
ISR, which R8 forbids. Both are recorded as reference behaviour only.

**Stop-condition check.** The design requires no change to the video
runtime, the service path, Policy A, the witness layer or any frozen format:
the pump slot, the transport's `write_block` and the u16 layout helper all
exist; the input module is new code beside them. Nothing was found that
would need one of the frozen parts to move.

## 8. The latency observability guarantee (Deliverable F)

The Operator wants to measure, later:

```text
PAD poll -> KEYPAD write -> first source VIDEO frame that reacts -> texture conversion -> hand-off -> VI latch
```

The tail exists and is not touched: OGBPIDXCAP1 gives every retained source
frame its `frame_index`, `FRAME_ID` and `t_first_block`; OGBPDISP2 gives the
same `frame_index` its `t_take`, `t_convert_done`, `t_decision` and
`retrace_decision`; OGBPVI1 gives the hand-over its `t_handed` and `t_latch`.
All of them are 64-bit `gbp_time64` ticks of the 40 500 000 Hz time base,
read with the wrap-safe loop `gbp_time64.h` specifies and libogc2's
`gettime()` implements.

What the architecture guarantees, and nothing more:

1. **The head is expressible in the same time base.** `gbp_input` keeps two
   `uint64_t` instants in its state, read with the same `gettime()`:
   `t_poll` — taken immediately after `PAD_ScanPads()` returns (the SI
   hardware sampled the pad up to one SI polling period earlier, a bounded
   and stated offset, not an unknown) — and `t_write` — taken when
   `write_block` returns, the DMA completion having been polled, so the
   instant the device received the word is bounded by the transfer's own
   duration. Both are plain fields; nothing emits them.
2. **No existing sidecar semantics change.** The head is not written into
   OGBPIDXCAP1, OGBPDISP2 or OGBPVI1; if a future checkpoint wants it
   persisted, the choices — ring-log lines like `STARTUPV`, or a new sidecar
   with its own version — are open and are not made here.
3. **The reacting frame stays identifiable.** The join `frame_index ↔
   FRAME_ID` exists for every retained frame, and a project-owned stimulus
   can publish what it read from KEYINPUT into its frames (§5, last
   sentence), so the first frame that carries the new state has a
   `frame_index`, and the tail's timestamps follow from it. No design choice
   above hides that frame: the write is issued from the main loop at a known
   instant, not queued asynchronously as GBI's ARQ write is.

Explicitly not done, by the Issue's scope: no instrumentation, no timestamp
emitted, no sidecar, no format version, and **no latency figure or claim**
of any kind. Whether the Phase-4 pipeline adds display delay is a future
question; this section only keeps it askable.

## 9. What this document does not do

It implements nothing and writes nothing to the device. It adopts no bit
order: the tables describe the references, and Open-GBP's encoding
descriptor stays unfilled until a physical result exists. It promotes no
status, mints no `GBP-HW-` id (the static findings are GBP-KEY-002 …
GBP-KEY-005) and closes no unknown. It changes nothing under `src/`,
`poc/`, `tools/` or `Makefile`, and nothing in the video runtime, the service
path, Policy A, the witness layer or any frozen format.

**Update, 2026-09-21 (Issue #19):** the implementation now exists (the note
at the top); the descriptor is filled as CORROBORATED data by the Operator's
decision, not because a physical result exists. This section still describes
what the *document* does not do, and it is unchanged.

## 10. Addenda after the pre-registration (GitHub Issue #22, 2026-09-21)

Two pieces of Operator input arrived after RUN 14 / RUN 15 were
pre-registered (`HARDWARE_TESTS.md` §V7.1, frozen) and are recorded here,
not there. Every statement below carries its classification; nothing
changes a status, the descriptor, or §V7.

### 10.1 An instrument evaluated and REJECTED — the homebrew input-test ROM `romhacking.net/homebrew/142`

Reported by the Operator from using it (OPERATOR OBSERVATION, not verified
by the Executor): it starts roughly 21 seconds after the boot logo; it needs
a START press to reach the screen that shows the input state; and it does
not support button combinations — with two buttons held its text oscillates
between them. Against the ≈ 40 s window §V7.1.1 derives: ~3 s of BIOS logo
plus ~21 s of start-up puts its first observable state around 24 s after
the CONTROL transform, more than half the session; the START gate costs
more; and the missing combination support defeats the L + R-together
observation outright and leaves a ten-button walk to be read by a human in
under 15 s. **Verdict: rejected as an instrument for RUN 14 and RUN 15**; the
EZ-Flash Omega DE menu and the AGS test ROM stay the instruments. It is
third-party homebrew whose provenance and licence were not evaluated; it is
not a project artifact and nothing from it enters the repository. Rule drawn
from it: an instrument for this line must show its input state well inside
the window and must accept simultaneous presses.

### 10.2 The Operator's recollection of the Start-up Disc on this hardware — OPERATOR OBSERVATION (recollection); the L3 policy corroborated

The Operator states, from past use of the official Start-up Disc on this
hardware (relayed by the Orchestrator): X and Y act as SELECT; L and R act
as L and R; an OSD option INVERTS this — L and R become SELECT, Y becomes L,
X becomes R; the left analogue stick and the D-pad have the same effect; the
C stick has no effect; Start is START; Z opens the Disc's OSD (swap SELECT /
L-R, scaling, eject the Game Pak, and so on). **Classification: OPERATOR
OBSERVATION, and a recollection of past use, not an observation made under
a pre-registered procedure** — weaker than what RUN 14 will produce, and not
verified by the Executor.

| Recollection | The implemented default policy (`GBP_INPUT_POLICY_DEFAULT`, Issue #19) | Agrees |
| --- | --- | --- |
| X and Y act as SELECT | X and Y → Select | yes |
| L and R act as L and R | L → L, R → R on the digital click | yes |
| the left stick and the D-pad have the same effect | main stick as the D-pad beyond ±48 (the Disc's threshold unknown) | yes, threshold aside |
| the C stick has no effect | C stick unread | yes |
| Start is START | Start → Start | yes |
| Z opens the Disc's OSD | Z reserved for the runtime, never sent | yes — see below |
| an OSD option inverts SELECT and L/R | no counterpart yet (a later configuration item) | consistent with the code's two modes |

Until now the policy rested on the Disc's decompiled code (GBP-KEY-002);
this adds the Disc's observed behaviour on this very hardware, as a
recollection. One line worth keeping: the implementation follows the Disc
(X and Y as SELECT), not GBI (Z as SELECT), which leaves **Z unmapped — the
very button the Disc reserves for its OSD**: a free alignment for a future
Phase 9 OSD, recorded, not acted on.

### 10.3 The composition "Y → word bit 8 (static) + Y acts as L (observed)", evaluated — it holds as logic; OPERATOR OBSERVATION (recollection); changes no status

*Term T1 (FACT, static — §3.1, GBP-KEY-002).* In the Disc's alternate mode
(`+0x8c == 1` at `0x8000822c`) PAD Y goes to word bit 8, PAD X to word bit
9, and L and R to bit 2 (Select); in the default mode PAD L goes to bit 8,
PAD R to bit 9, and X and Y to bit 2.

*Term T2 (the recollection, §10.2).* With the swap option on, Y acts as L
and X as R while L and R act as SELECT; with it off, L acts as L, R as R,
and X and Y as SELECT.

*Identification I.* The swap option IS the decompiled alternate mode —
supported because the option's three described effects match mode 1's code
in every role (L and R → SELECT; X and Y taking the L/R roles) and the code
has exactly two modes. Not verified by reading the Disc's option code path.

*Composition.* Under I, T1 and T2 give: **word bit 8 reaches the AGB as L,
and bit 9 as R** — the assignment GBP-KEY-004 records, reached this time
through a chain whose second term is an observed effect on real hardware
rather than more code, independent of the static agreement of the Disc, GBI
and Dolphin. The default-mode chain (PAD L → bit 8; "L acts as L") composes
to the same answer, but "L acts as L" could be an expectation rather than an
observation; "Y acts as L" cannot, which is why the alternate-mode chain is
the stronger of the two.

*Does it hold?* As logic, yes, on two conditions: I, and the exactness of
T2's X/Y attribution — had the recollection Y and X exchanged (Y acting as
R), the same composition would yield bit 8 = R, the opposite conclusion; the
inference therefore rests on precisely the detail memory is least reliable
about.

*Classification and consequence, stated once.* OPERATOR OBSERVATION, a
recollection; recorded as GBP-KEY-007, consistent with GBP-KEY-004's
assignment and the first hardware-side term that assignment has ever had.
It does NOT change GBP-KEY-004's status (CORROBORATED, not FACT), does NOT
close U-GBP-010 (left OPEN for RUN 14), and the descriptor stays exactly as
it is; `REGISTERS.md` keeps H.

*What would turn it into a recorded observation.* A short written
re-verification on the official Start-up Disc, on this hardware, reported
literally — official software only, no Open-GBP code, no files, not part of
§V7 and not a condition of RUN 14; for the Orchestrator to attach to a
Hardware Issue if wanted:

```text
 a  Boot the official Start-up Disc (the Operator's own original) with the EZ-Flash Omega DE menu as the display
    instrument (or the AGS test ROM's controller test, launched from that menu).
 b  Default settings: press L; press R; press X; press Y -- one at a time. Record what the AGB reacted to each.
 c  Open the Disc's OSD with Z; enable its SELECT / L-R swap option; close the OSD.
 d  Press Y; press X; press L; press R -- one at a time. Record each as in b.
 e  Report literally, as OPERATOR OBSERVATION. Even recorded, it is never FACT: FACT needs the project-owned
    stimulus joined to the runtime's own records (§5, §7.1.10 of HARDWARE_TESTS).
```
