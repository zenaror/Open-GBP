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
Phase 9 OSD, recorded, not acted on. Consistent with it, informally: in the
Operator's unregistered, incomplete trial of the candidate on 2026-09-21
(`HARDWARE_TESTS.md` §V7.1.2) every counter of the test ROM incremented
except under Z and the C stick, which produced nothing — OPERATOR
OBSERVATION from an unregistered trial, supporting no claim.

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

## 11. Addendum after RUN 14 / RUN 15 — §8's guarantee spent (GitHub Issue #27, 2026-09-21)

RUN 14 and RUN 15 executed and were ingested (`HARDWARE_TESTS.md` §V7.2;
U-GBP-010 CLOSED, the routing CORROBORATED, not FACT); the physical record no
longer starts from nothing — the sentence in §1 is dated. The one link the
machine record lacked was *which word the runtime sent at each change*, and
§8 kept exactly the instants that carry it. Issue #27 spends the guarantee:
`stream-0015` (`da06500`, not executed) emits one `KEY` ringlog line per
first / change / retry write with the word, the logical set and `t_poll`,
`t_attempt`, `t_done` in the transport's ticks64 base — the base of the
sidecars, so the join of §8 needs no conversion (GBP-KEY-009, GBP-KEY-010).
Choice 2 of §8 is therefore made: ring-log lines, no sidecar, no format
version, and no existing sidecar semantics changed; the head is bounded by
the ringlog's own capacity with a reserve for the post-run records. Nothing
in this addendum is a latency figure, and the routing stays CORROBORATED
until a run joins this record to an instrument showing what the AGB received.

## 12. The runtime image fit for playing a game — ASSESSED, NOT BUILT (GitHub Issue #38, 2026-09-21)

Issue #38 asked for a runtime image fit for the ROADMAP's Phase 5 acceptance
run — the one `stream-0015` is not — to be assessed first and built only if
the assessment held, with a stop rule: if removing the research
instrumentation turns out to be a redesign rather than a subtraction, say so
and stop. **This section is the assessment; the conclusion is STOP.** The
subtraction is real and clean, but it does not yield a usable acceptance
image: once the video witness is unbound, the image has no success stop, and
giving it one changes the service-path module the Issue forbids touching.
Nothing was built; no `BUILD_ID`, no run name, no code. Every statement
below is read from the source at `2e9e393` and is pinned by
`tests/host/test_game_image_assessment.py`.

### 12.1 What `stream-0015` is made of

`poc/gbp-video-stream-probe/source/main.c` owns everything that is not a
pure module. Read with the Issue's distinction — runtime versus research
instrumentation:

```text
RUNTIME (what a game needs)
  transport + service    hsp_backend + hsp_backend_irq (the one-shot handler, audited byte-identical to GBP-VIDEO-001's);
                         gbp_vstate_probe_run() -- the 003A stage, READ -> AUDIO -> VIDEO -> ACK -> PI clean -> assembly ->
                         RE-ARM -> next cause, with Policy R3; the state model's stores it REQUIRES by contract (frame
                         records 16384 x 192 B = 3.00 MiB, events 4096 x 64 B, raw ring 0.70 MiB, episode raw 2.81 MiB,
                         audio raw 12 KiB -- §V5.29: a smaller set is refused at the first gate, never a lighter model)
  presentation           gbp_vqueue (the mailbox) -> pump() (one tile row per slice, after the RE-ARM, under the
                         cause-pending yield) -> gbp_vpix -> GX (one RGB5A3 quad) -> two stream framebuffers; Policy A in
                         submit_ready() (the framebuffer question first, one draw-done token in flight, the oldest READY
                         texture offered first); gbp_vpresent's ownership machine; the display self-test before the device
  input + the record     input_step() -- the FIRST statement of pump(): PAD_ScanPads, gbp_input_map (policy), the ONE
                         descriptor, one 32-byte KEYPAD write through the same transport, on change and every 5 ms;
                         keylog_emit() -- one KEY ringlog line per first / change / retry write under the 64-line reserve
                         (GBP-KEY-010); both read the transport's clock only
  the log and the save   the ringlog (LOG_LINES 1024 x 256 B) and sdlog_save after the teardown
RESEARCH INSTRUMENTATION (what a game cannot use)
  the OGBPIDX1 witness   witness_store 2048 x 4 320 B = 8 847 360 B + witness_meta 98 304 B; the qualification streak and
                         the 5 000 ms eligibility gate (WITQUAL / WITELIG / WITELIG2, the release compare in pump()); the
                         witness step inside the service transaction; the STREAMWIT / STREAMWITT records; the OGBPIDXCAP1
                         sidecar (8 946 060 B). Bound by ONE statement: `cfg.witness = &wit;`
  the full-frame sampler full_raw 1 228 800 B + full_tex 614 400 B (K = 8, spacing 256); its origin = the witness's first
                         retained frame; one block copied per slice; gbp_vfull_* calls in pump() and submit_ready(); the
                         FULLSTORE record; the OGBPFULL1 sidecar
  the VI latch trace     vvi_recs 4096 x 64 B; the latch compare in pump(); gbp_vvi_handed in submit_ready(); VISTORE; the
                         OGBPVI1 sidecar
  the disposition trace  disp_life 4096 + disp_ev 8192 (OBSERVATIONAL, §V5.46: it records what Policy A decided and changes
                         nothing); gbp_vdisp_* calls in pump(), submit_ready(), on_draw_done() and the self-test; DISPTRACE /
                         DISPSRC / STARTUPV; the OGBPDISP2 sidecar; overflow is COUNTED (life_overflow) and the take returns
                         -1, which the callers already handle
```

### 12.2 The subtraction, as a subtraction

What comes out cleanly, and what removing it touches:

```text
the witness            unbind it: `cfg.witness = NULL` (main.c). Both witness stops in the state machine sit under
                       `if (cfg->witness)` and the predicates are null-safe (gbp_vwitness.c), so the service path needs no
                       change for this. Out with it: the store and its metadata (8.95 MB), the eligibility compare in pump(),
                       the qualification records, the sidecar and its save block. Out of the service transaction: the
                       witness step (gbp_vwitness_step is called from gbp_vstate_probe.c only when cfg->witness is set) --
                       so the service pass gets SHORTER, a timing change on the critical path to be re-measured, not assumed.
the full-frame sampler out: the two stores (1.84 MB), the origin, the want / open / block / convert_done / decision / refuse
                       calls, the FULLSTORE record, the sidecar. And with it the origin dependency Issue #37 found: there is
                       nothing left that needs the witness's first frame. This part of the Issue's simplification HOLDS.
the VI trace           out: the records (0.25 MB), the latch in pump(), the handed call in submit_ready(), VISTORE, the sidecar.
the disposition trace  keep or remove; both are defensible. Removing it edits every line of submit_ready() that records a
                       decision; keeping it costs 0.25 MB and overflows, counted, after 4096 lifecycles (~68 s at 59.7 Hz),
                       after which STARTUPV and the DISPSRC counts stay valid and the per-lifecycle trace is partial.
what it TOUCHES        textually: pump() and submit_ready() -- the presentation path's own two functions -- although no
                       decision, no order of GX calls and no XFB rule changes; every removed line is bookkeeping. The Issue's
                       "presentation path not touched" holds in substance and not in bytes, and that must be said.
the input path and     UNTOUCHED, byte-identical: input_step() is the first statement of pump() and does not reference the
the KEY record         witness, the sampler or the traces; keylog_emit() writes the ringlog under KEYLOG_TAIL_RESERVE; the
                       descriptor and the policy are src/gbp data. Nothing above changes a byte of either.
memory                 freed: 8 847 360 + 98 304 + 1 843 200 + 262 144 = 11 051 008 B; arena1_free would go from
                       1 650 688 B to about 12.7 MB. The state model's stores stay (the contract).
```

So far, a subtraction. The next question is the one that decides.

### 12.3 What ends a session once the witness is gone

`CHECK_ADMISSION` in `src/gbp/gbp_vstate_probe.c` is the ONLY place a stop
is evaluated, once per service cycle, in this order; with `cfg->witness`
NULL and `cfg->color` NULL the image of §12.2 has exactly these left:

```text
1  the safety budget    hard_wallclock_ticks from the CONTROL transform -- STREAM_SAFETY_SECONDS = 60 in main.c -> teardown
                        S5_safety_budget, stop=safety_budget, gbp_vstate_safety_stop(). By the probe's own words "it stops a
                        run that has gone wrong, it is never a success", and every pre-registration's SESSION gate reads
                        stop=witness_target_reached and nothing else.
2  the frame store cap  st->frame_store_full at GBP_VSTATE_MAX_FRAMES = 16384 closed frames -> S5_frame_store_cap. At 59.727 Hz
                        that is 274.3 s: an unbounded session ends here in 4.6 minutes, scored as "lost the bookkeeping".
3  the event store cap  4096 events -> S5_event_store_cap (events are anomalies and episodes; RUN 17 used few; not the binding
                        limit for a game, but a cap all the same).
4  the time target      DISABLED BY NAME (§V5.59 F5). Re-enabling it is not an answer: its success needs st->baseline_valid from
                        the change detector -- whether a baseline forms under a moving game is unknown -- and its success
                        stop is S5_target = NOMINAL_NEGATIVE, "no change observed": the wrong sentence for a game session.
5  the delivery cap     STREAM_MAX_DELIVERIES = 400 000 -> S5_delivery_cap, "the u32 guard, not a scientific bound"; at RUN 17's
                        6 314 deliveries/s about 63 s.
```

Two facts follow, both checkable in the source. (a) **Every remaining stop
is scored as the run going wrong.** The status the machine writes does not
tell them apart from a success: `finish()` uses `OK_NO_CHANGE_INCONCLUSIVE`
for the safety budget, the store caps, the witness target and the delivery
cap alike, and `gbp_vstate_main_status()` then reports
`ok_structured_change_observed` whenever an episode was seen (RUN 17's
`VSTATE end` reads `status=ok_structured_change_observed class=ok
stop=witness_target_reached`). What distinguishes the ends is the
`stop=` / `teardown=` field and the project's rule about which of them is a
success — and for a game session none of the five is. Raising
`STREAM_SAFETY_SECONDS` and `STREAM_MAX_DELIVERIES` (constants of main.c) moves
WHEN the run stops and never HOW the stop is scored; enlarging the frame
store (allowed by the contract, ~3× with the freed memory, ~13.7 min) moves
the bound and keeps the class. (b) **The POC cannot end the run as a
success.** `gbp_vstate_probe_run()` returns only after the teardown; the pump
hook is `void (*pump)(void *user)` with no return channel
(`gbp_vqueue.h`); `struct gbp_vstate_config` has no operator-end, session-target
or "stop now" field; the only caller-supplied stop conditions are the
witness and the colour capture, both wrong for this. Setting
`cfg.max_deliveries` from the pump to force `S5_delivery_cap` would end the
run — under a stop reason that says the u32 guard fired, which is a
misrecording, not a success stop.

**Therefore: with the witness unbound, an image of this shape has NO
success stop.** An acceptance run needs an answer for that, and "it will
probably be fine" is not one.

### 12.4 What an acceptance image needs — and why that is a redesign

```text
1  a SUCCESS stop for   an operator-ended session: the Z button, which the policy reserves for the runtime and never sends
   an input session     (INPUT.md §4), read in the pump where the pad is already scanned, signalled to the state machine
                        through a new config field (a caller-owned flag, or a callback), evaluated in CHECK_ADMISSION after
                        the safety budget and before the store caps, with its OWN stop reason (e.g. GBP_VSTATE_STOP_SESSION_END,
                        teardown S5_session_end) and its own place in the gates ("stop=session_end" as the SESSION success) --
                        and/or a wall-clock session target as a success, distinct from the disabled time target and from the
                        safety budget. Either one is a change to src/gbp/gbp_vstate_probe.{h,c}: the config struct, the
                        result, the stop enum, the names, CHECK_ADMISSION, and the unit tests that drive the run loop with the
                        mock transport (tests/unit/test_gbp_video_state.c). No device operation changes; the module does.
2  the caps             STREAM_SAFETY_SECONDS raised above the session's expected length and STREAM_MAX_DELIVERIES raised in
                        proportion (main.c; the semantics untouched: the safety budget stays the "gone wrong" stop, now
                        above the session).
3  the frame store cap  enlarge GBP_VSTATE_MAX_FRAMES for the image (the contract allows a LARGER set; ~3x fits the freed
                        memory, ~13.7 min) or keep 16384 and state the 274 s bound in the pre-registration as the session's
                        hard end (an image whose session ends at a store cap still ends as "lost the bookkeeping" unless
                        item 1 fires first).
4  the ringlog          LOG_LINES 1024 leaves about 700 lines after the pre-run and post-run records and the reserve -- about
                        350 presses; a game session at 1-2 presses/s exhausts it in 3-6 minutes and counts the surplus in
                        KEYLOG lost. Raise LOG_LINES (4096 lines = 1 MB; the freed memory covers it); the KEY line, the admit
                        rule and KEYLOG_TAIL_RESERVE unchanged, the headroom re-derived by the existing tests.
5  the disposition      keep (the presentation path stays textually closer to stream-0015's) and accept the counted overflow,
   trace                or remove it with the sidecar.
6  a new POC            a new directory under poc/ with its own main.c (the runtime of §12.1 without §12.1's instrumentation),
                        its own Makefile (the SRCS list without gbp_vwitness / gbp_vidxdump / gbp_vfull / gbp_vfulldump /
                        gbp_vvi / gbp_vvidump), a new BUILD_ID line (not stream-00xx: a different experiment), a new
                        poc_audit profile (the `stream` profile pins the four sidecar streams from main, the witness call
                        sites and gbp_vidxdump_stream -- a smaller image fails it by construction), the ISR compare unchanged
                        (the handler is hsp_backend_irq's), its own Dolphin smoke conditions (READY / SELFTEST / INPUTSELFTEST /
                        COUNTERS; the pump never runs there, so nothing about input or the session stop is covered), the next
                        Swiss number (13), the host tests that pin all of it.
7  its own              a game the Operator has that passes through the button path; the session's end declared before the
   pre-registration     run; the reserved names; the gates with the new SESSION success; the per-run declarations.
```

Items 1 and 6 are the reason this is a redesign and not a subtraction: a
usable image changes the service-path module (its admission logic, its
result, its stop vocabulary) and the audit tooling, which the Issue's own
constraints — "Policy A, the service path, the transport and the presentation
path are not touched; what comes out is research instrumentation, not
runtime" — rule out for this checkpoint. Both constraints cannot hold at
once with a usable image, and the Issue's rule for that case is to stop.
What holds under every item: the input path and the KEY record stay
byte-identical, the descriptor does not change, and the routing FACT of
§V7.4 is not disturbed.

### 12.5 The session length such an image gives

Bounded by the smallest of: the session end of item 1 (the Operator's, or
the target); the safety budget as configured (item 2); the frame store cap —
274.3 s at 16384 frames, ~13.7 min at 3× (item 3); the ringlog headroom in
presses — ~350 at 1024 lines, ~1 900 at 4096 (item 4); with the disposition
and VI traces (if kept) overflowing, counted, past ~68 s. None of these is a
property of the Game Boy Player; each is a bound of the image, to be stated
in the pre-registration.

### 12.6 What was not done

No code; no build; no `BUILD_ID`; no run name; nothing staged; §V7.1–§V7.5
untouched; the routing untouched; the Issue's constraints kept by stopping.
The redesign — items 1 to 7 — is a checkpoint of its own, for the
Orchestrator to open; it is not a silent expansion of this one.

## 13. The playable image — BUILT, NOT RUN (GitHub Issue #39, 2026-09-21)

Issue #39 opened the redesign §12.4 called for and decided the three things
§12 had left open: the operator ends the session with Z; the disposition
trace comes out; the image is sized for at least five minutes of play after
the game boots. This section records what was built, from the sources it is
read from (`tests/host/test_play_image.py` pins every claim to them), and
what it does NOT claim. Nothing here has run on hardware.

### 13.1 The image

```text
POC            poc/gbp-play-session            (Swiss slot 13 "play" in tools/swiss-layout.tsv; build/swiss NOT re-exported:
                                                12-stream keeps the stream-0015 the runs used)
embedded id    GBP-PLAY-001                    (the image's own; no run is pre-registered under it; one line to rename)
BUILD_ID       play-0001
commit         2e48ca7                         (the two code commits of Issue #39: 8c98f0c the module, 2e48ca7 the POC; clean, no -dirty)
SHA-256        d0ee3c29d04254d1b86d4f006291008876b5e886e07280d0421b7c1161c499de
size           487 968 B                       (stream-0015: 514 880 B)
warnings       0, none suppressed               (-Wall -Wextra -Wshadow; two from-scratch builds at 2e48ca7, byte-identical)
audit          make play-audit: 0 findings; the ext and base one-shot handlers IDENTICAL to the physically validated
               GBP-VIDEO-001 build's; the `play` profile finds 105 things wrong with the stream image and the `stream`
               profile 33 with this one (both directions run by the host test on the real listings)
Dolphin        make play-dolphin PASS, HSP device ABSENT: READY, SELFTEST ok=1 sci_clean=1 inv_fail=0, INPUTSELFTEST ok=1,
               ENVMEM arena1_free=5439488 (5 439 488 B), COUNTERS balanced=1 storage_fault=- (the enlarged stores pass the gate
               stream-0002 failed physically), SESSION requested=0 samples=0, RESULT status=abort_inconsistent class=abort
               reason=inconsistent stop=failure teardown=stage_a service=0 deliveries=0 restore=1.
               THE CEILING, as Issues #19 and #27 stated it: the probe stops before any service cycle, so the pump slot
               never runs -- the input path, the KEY record, the presentation of a real frame and the session end are
               NOT exercised in Dolphin. Auxiliary, never physical evidence.
status         NOT PHYSICALLY EXECUTED; no run name reserved; nothing pre-registered; nothing staged.
```

### 13.2 What came out, what stayed, and exactly what moved in the presentation path

Out (§12.2's subtraction, done): the OGBPIDX1 witness -- `cfg.witness` stays
NULL, so the witness step never runs inside the service transaction and the
two witness stops do not exist; no store (8 847 360 + 98 304 B), no
qualification, no eligibility gate; the full-frame sampler (1 843 200 B), the
VI latch trace (262 144 B), the disposition trace (§V5.46) and the four
sidecars. The witness MODULE is still linked, because
`src/gbp/gbp_vstate_probe.c` references its predicates under
`if (cfg->witness)`; the `play` audit profile pins those sites by count
exactly as the `stream` profile does (so the module is provably the same
code) and pins that nothing else in the image names a `gbp_vwitness_`
symbol.

Stayed, byte for byte: `keylog_emit()` and `input_step()` are the TEXT of
stream-0015's (the host test diffs the two function bodies); the descriptor,
the policy, the KEY line format and the admit rule are the shared `src/gbp`
data and code; the KEYPAD write is the same 32-byte write through the same
transport, on change and every 5 ms, first in the pump slot. The service
path's device operations, their order and Policy A are unchanged.

What moved, textually, in the presentation path -- and why "unchanged" is a
statement about behaviour, not bytes:

```text
pump()            REMOVED  the §V5.55 eligibility compare (gbp_vwitness_streak_gated / release_streak);
                           the §V6.8 VI latch (gbp_vvi_awaiting / vi_regs / gbp_vvi_latch);
                           at the take: gbp_vdisp_take, tex_life, the sampler's origin (gbp_vwitness_meta_at),
                           gbp_vfull_want / gbp_vfull_open, tex_sample;
                           gbp_vdisp_convert_first; the per-block gbp_vfull_block copy;
                           on the two abandon paths: gbp_vdisp_abandon, gbp_vfull_refuse, tex_sample / tex_life resets;
                           at the end: gbp_vdisp_convert_done, gbp_vfull_convert_done
                  ADDED    session_step() right after input_step(); tex_seq / tex_frame / tex_t_take at the take;
                           tex_t_done at the end; tex_seq resets on the abandon paths
                  KEPT     input_step() first; offer_oldest_ready(); acquire -> take -> one tile row per slice -> the
                           generation guard (gbp_vqueue_commit / still_valid) -> DCFlushRange -> fill_done -> offer
submit_ready()    REMOVED  pend / tstate / rt / inflight reads (they fed the trace), gbp_vdisp_defer,
                           gbp_vdisp_submit_refused, gbp_vdisp_submit, gbp_vdisp_decision, gbp_vfull_decision,
                           gbp_vvi_handed, tex_life
                  ADDED    the first real hand-off's record (first_real: frame index, t_take, t_convert_done, t_decision);
                           tex_seq reset
                  KEPT     Policy A verbatim in its decisions: xfb_target FIRST (defer = the texture stays READY, nothing
                           consumed); ONE token in flight (a refused submit is offered again); the GX ORDER draw ->
                           GX_SetDrawDone -> GX_CopyDisp -> GX_Flush -> VIDEO_SetNextFramebuffer -> VIDEO_Flush ->
                           xfb_handed; no wait anywhere
offer_oldest_ready()  the ordering key is the take ordinal tex_seq (assigned in take order) instead of the trace's
                           lifecycle index (assigned in take order): the same order, §V5.49 I2 kept by construction
on_draw_done()    REMOVED  gbp_vdisp_drawdone(gettime()): the callback now does exactly one thing and reads no clock
display_selftest / selftest_submit_headless   REMOVED the trace's take / convert_done / submit records
```

The `play` profile's `gettime` pins say the same from the listing: `main 5,
pump 2, submit_ready 1, h_ticks64 1`, and `on_draw_done` absent (stream:
`main 8, pump 5, submit_ready 2, on_draw_done 1`).

### 13.3 The session end

```text
the button      Z, held continuously for PLAY_SESSION_END_HOLD_MS = 250 ms (a tap does nothing) -- the one input the
                policy never sends to the AGB (INPUT.md §4), the button the Start-up Disc reserves for its own menu
where           session_step(), right after input_step() in the pump slot: it reads PAD_ButtonsHeld on the sample
                input_step() just took (no second scan, no SI transfer), takes the transport's ticks64, and feeds
                src/gbp/gbp_session -- a pure state machine with NO outward edge (the audit allowlists the object empty);
                the same admission as input_step(): nothing before the ARAM base is known
the flag        session.end_requested, installed once as cfg.session_end (the new field of struct gbp_vstate_config;
                NULL in every earlier build, and then the block does not exist)
the stop        CHECK_ADMISSION reads the flag ONCE per admitted cycle -- after the safety budget (safety always wins) and
                after the frame / event store caps (a run that lost its bookkeeping at the same admission is reported
                as the cap it hit), before the witness, colour, time-target and delivery stops -- and ends the run as
                stop=session_end  status=ok_session_ended (class ok)  teardown=S5_session_end
                THE ONLY SUCCESS. The transaction in flight completes whole (its ACK and its RE-ARM are written), the
                cause stays latched for the teardown, and the teardown is the one every admission stop gets.
the codes       GBP_VSTATE_STOP_SESSION_END and GBP_VSTATE_OK_SESSION_ENDED are APPENDED to their enums, never inserted:
                the frozen sidecar writers serialize the numeric codes (OGBPIDXCAP1 stop_reason / status_code)
the status      gbp_vstate_main_status returns ok_session_ended for that stop whatever the change detector saw: an
                ended game session is the run's normal end, not "structured change observed"
the record      SESSION end=Z hold_ms hold_ticks requested t_hold_begin t_requested samples held holds released after stop
                teardown; the gecko line OPENGBP-PLAY SESSION; the on-screen "SESSION ENDED BY THE OPERATOR (success)"
the tests       tests/unit/test_gbp_video_state.c drives the real probe against the mock: raised at the 7th RE-ARM ->
                deliveries = acks = rearms = 7, stop=session_end, ok_session_ended, S5_session_end, PI cleaned, CONTROL
                restored, the TEARDOWNVSTATE / VSTATE end / MATRIX lines; raised before the first delivery -> the first
                transaction still completes whole; the safety budget wins at the same admission; an opened episode does
                not change the status; with no flag installed nothing changes. tests/unit/test_gbp_session.c: the hold,
                the tap, the latch, the zero bound, a high 64-bit clock.
```

### 13.4 The sizing, and what bounds a session

None of these is a property of the Game Boy Player; each is a bound of this
image, stated so a pre-registration can state it.

```text
PLAY_SAFETY_SECONDS      720 s   the hard budget from the CONTROL transform (the AGB's boot included); a run the operator
                                 did not end; NEVER a success. Five minutes of play after a boot and a menu of up to seven.
PLAY_FRAME_RECORDS       45056   754 s at 59.727 Hz > 720 s: in a nominal stream (one closed frame per 40 VIDEO blocks)
                                 the safety budget always fires first; a pathological stream that closes frames faster
                                 ends the run as frame_store_cap -- visible. COST over the contract's 16384: +5 505 024 B.
PLAY_EVENT_RECORDS       16384   68 min at the four events per second a moving game can produce at most (one episode
                                 close per second of change: EPISODE_MAX_FRAMES = 60). COST over 4096: +786 432 B.
PLAY_MAX_DELIVERIES   6 000 000  the u32 guard above the budget: 720 s x RUN 17's 6 314/s = 4.55 M, 1.32x below it
                                 (a factor, as the design's guard always was); binds only above ~8 300/s.
LOG_LINES / reserve   8192 / 640 the ringlog DROPS when full (src/log/ringlog.c), so the reserve must cover the WHOLE
                                 post-run report -- the state machine's EV / CYC / READDISAGREE / SEM lines plus main's
                                 records: 462 lines after the last KEY line in RUN 17. KEY headroom: 8192 - 640 - ~240
                                 pre-run lines = ~7 300 KEY lines = ~3 650 presses (two lines per press). COST: +1 835 008 B.
memory (measured)     ENVMEM arena1_free=5439488 B in Dolphin (the same MEM1 layout as the console; a build fact, not
                                 a device fact). Freed by the subtraction 11 051 008 B; spent on the stores and the log
                                 8 126 464 B; stream-0015 had 1 650 688 B free on the console (RUN 17).
the session, then     ends by Z (success), else by the 720 s budget (gone wrong); the frame store, the event store and
                      the guard sit above it in a nominal stream; a KEY-heavy session loses KEY lines to the bound, counted
                      in KEYLOG lost, never the summaries.
```

### 13.5 The shorter service pass — stated, not assumed benign

The witness step ran INSIDE the service transaction of every stream build
since stream-0005: after the assembler consumed the VIDEO block and before
the publish and the RE-ARM (so after the ACK). RUN 17 measured it per VIDEO
block (`STREAMWITT`, n = 96 109): min 5, mean 70, max 1 547 ticks at
40.5 MHz = 0.12 / 1.73 / 38.2 µs. In this image the step does not exist, so
the ACK → RE-ARM gap of every VIDEO cycle is shorter by that amount, and the
next cause is invited that much sooner. The device sees the same operation
stream in the same order; only that gap changes.

What that shape has behind it: `stream-0003` (RUN 3, real cartridge video on
screen) and `stream-0004` (RUN 4) ran the service transaction WITHOUT a
witness step and WITH this presentation path -- the pre-witness shape. What
it does not have behind it: the input path, which has only ever run with the
witness step present (stream-0014 / stream-0015, RUN 14–18). So the
combination in this image -- the KEYPAD write in the pump slot and the
shorter transaction -- has NOT run.

What would measure it, and it is the first run of the image itself, because
no measurement of a hot-path gap exists off the device: the CYC records
(`t_ack` → `t_rearm` → `t_next` per cycle, first / last / anomaly), the
delivery rate against RUN 17's 6 314/s, `COUNTERS` (anomalies, uncertain,
errors, control_ok), `STREAMPUMP` (skipped_cause_pending against RUN 17's
share), `INPUT` retries and `KEYLOG` against RUN 17's log as the reference.
Until a run reads clean on those, the image's timing is UNCHECKED, and the
Issue's stop condition on this point was met by saying so here rather than
by not building: the shape has precedent and a measured delta, and the only
instrument that can check it is the run.

### 13.6 A finding about stream-0015, recorded, not acted on

stream-0015's `KEYLOG_TAIL_RESERVE` is 64 lines, justified against main's
own post-run records; the state machine's report that precedes them is
~430 lines (RUN 17: 462 after the last KEY line). Because the ringlog drops,
a run with more than ~330 KEY lines (~165 presses) would have dropped
report lines and set `dropped > 0`. RUN 14–18 were far below that (RUN 17:
43 KEY lines), so no executed run was affected; the frozen image is not
changed. The playable image's reserve of 640 is the correction.

### 13.7 What is open, and what this checkpoint did not do

- **U-GBP-035** — presentation behaviour during a long real-content session
  has NO instrument: the disposition trace is out by decision (it would have
  covered ~68 s of a multi-minute session and counted overflow for the
  rest), and a partial trace is not evidence about the session. Its own
  checkpoint, Phase 9 / Phase 12.
- No run; no pre-registration; no game chosen; §V7.1–§V7.5, every verdict,
  every evidence status and the routing FACT untouched; `build/swiss` not
  re-exported; nothing staged. **Superseded on the same day, in order:** the
  runs are pre-registered as RUN 21 / RUN 22 in `HARDWARE_TESTS.md` §V7.6
  (Issue #41) and the game is settled there (WarioWare, Inc.: Mega
  Microgame$!, a ROM on the flashcart). Still true: nothing is staged and
  nothing has run.

### 13.8 CORRECTION (2026-09-21, Issue #41) — the audit cross-check figure of §13.1

§13.1 records that the `play` profile "finds 105 things wrong with the stream
image". **The correct figure for the committed profile on the committed build
is 102.** The Orchestrator measured 102 independently and recorded what he
measured; this is the cause, verified here rather than guessed:

```text
what was measured   105, with the FIRST DRAFT of the `play` profile, on listings built from the working tree before the
                    module change was committed
what changed after  three pins of the profile were corrected against the real listing and committed with it:
                    gbp_keypad_write's call sites 1 -> 2 (GCC lays the one function out at two sites inside
                    gbp_input_step), and gbp_input_map / gbp_keypad_encode removed from elf_required (both are inlined
                    into gbp_input_step and garbage-collected from the ELF)
why the difference  those same three pins also fire against the STREAM image, which has the same two call sites and the
                    same two absent symbols. 105 - 3 = 102, reproduced exactly by running the draft profile and the
                    committed profile over the same listings.
what it does NOT    the property the figure illustrates, all three measured on the committed build:
  change            0 findings on the play image, 102 on the stream image, 33 for the `stream` profile on the play image.
                    The host test asserts the property (findings on this image = 0; more than twenty against each other
                    image, with named examples), never the exact count, so no test moved.
the process point   the same shape as the gate-figure rule: a figure measured against an intermediate state is not the
                    figure for the checkpoint. The rule was already held for the SUITE figure and not for this one.
```

The §13.1 line and the HANDOFF and DEVLOG entries of Issue #39 keep their
text with a pointer to this correction: the record of what was reported is
not rewritten, and the corrected figure is here.

## 14. A lesson for the next action list — put the boundary in the record (GitHub Issue #51, 2026-09-22)

**Not applied to RUN 21 / RUN 22.** Their checklist is in the Operator's hands
and may already have been executed; §V7.6.15's hard constraint is that nothing
he does changes. This is written for the list after them.

**What went wrong, in one sentence.** §V7.6.11 froze a machine comparison —
Question K over *"steps 2-12, 14 and 15"* — across a boundary that **no
machine can find**: steps 14 and 15 follow several minutes of unscripted play,
the runtime has no notion of a "step", and the Operator's channel carries no
`n` and no timestamp into the `KEY` record. The defect was found by making the
verdicts executable before any data existed (Issue #50) and amended on top
(§V7.6.15, Issue #51): K is computed over steps 2-12 only, and its tail is
recorded as `NOT DEFINED BY THE PRE-REGISTRATION` rather than INCONCLUSIVE.

**THE RULE FOR THE NEXT LIST.** Any action list that a machine will have to
segment must put a **machine-locatable boundary into the record itself**. The
cheapest known one:

```text
a SIMULTANEOUS TWO-KEY PRESS that the scripted parts never use
  in the record      two bits rising in ONE completed word -- unambiguous to a parser, and impossible to
                     confuse with an ordinary press, because every scripted step presses one key at a time
  for the Operator   one action, at the point where the segments divide
  what it buys       the segmentation is READ rather than inferred, so no rule has to be invented later and
                     no fumbled press can slide a window
```

**Why the alternatives are not alternatives** (demonstrated, not asserted, in
`tests/host/test_v7611.py`): a trailing-window rule is right on a clean run and
**silently wrong on a fumbled one** — one doubled press slides the window, and
the comparison then reads the wrong presses while every element of its output
still looks valid; and a time-gap rule invents a threshold that
`HARDWARE_TESTS.md` §V7.6.3 refuses, on facts that defeat it anyway, since a
cutscene, a menu or a death inside three minutes of play is a longer pause than
the transition it is trying to find.

**The general form of the lesson, which outlives this list.** A
pre-registration may only freeze a comparison its own instrument can
**delimit**. Freezing the arithmetic is not enough if the segment the
arithmetic runs over cannot be located in the record.
