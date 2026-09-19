# Hardware Tests

Experiments actually executed on the physical GameCube (+ Game Boy Player).
One entry per executed test. Planned-but-not-run tests are listed at the
end so they are not mistaken for results.

Format:

```text
Test ID / Date / Build ID / Commit / DOL SHA-256
Setup (cartridge, Link Port, BBA, loader)
Steps performed
Observed result
Logs / captures
Conclusion and follow-ups (EVIDENCE / UNKNOWNS ids)
```

## Executed tests

### GBP-VIDEO-001 — 2026-09-16 — PASS (`ok_video_sequence_capture`)

**Physically executed 2026-09-16**, one run, no Game Pak. Build `video-0001`,
clean commit `6930dde` (`6930dde3074ae25ca2e3b3a1501a58ca055918b3`), DOL SHA-256
`856d3e91…fd65`. Raw evidence: log sha256
`ec3c366c8e885dea2631db74cc974d1cd2262cae59a6ee4732e08536a4bd6527` (270 580 B),
sequence sidecar sha256
`ce5134ff12f8a0b78a1f60c3c3f4be658fa1ecb66e078ae50a241f037edfe229` (403 948 B,
`OGBPSEQ1` v1). Fixture: `captures/fixtures/hw-gamecube-gbp-2026-09-16-video-0001.gbpreplay`
with its sidecar; the sidecar in `captures/fixtures/` is a byte-identical copy of
the console's file. Power cycle performed by the user.

**Operational result (FACT, this run).** 209 admitted cycles, 209 unmasks, 209
handler entries, 209 ACKs, 209 re-arms, 0 reentry, 0 missed entry, 0 unexpected
source, 0 uncertain write, 0 DMA timeout, 0 busy, `errors=0`, `transport_ok=1`,
`control_ok=1`. W1C budget: ISR 209 (one per delivery), main 0, teardown 1 —
210 in total. 88 VIDEO blocks (0xF00 at `0x01100000`) and 144 AUDIO blocks
(0x1000 at `0x01800000`), all completed; `bulk_transfers=232`,
`bulk_bytes=927744` = 88 × 0xF00 + 144 × 0x1000 exactly. Capture ended at
`target_reached` with the 210th cause latched and refused at the admission
point; no 89th VIDEO block was captured. `restore=ok`. ISR latency 34 ticks
median (0.84 µs), 95 maximum (2.3 µs). The log used 1794 of the ring's 3000
lines, 0 dropped, 0 truncated.

**Source distribution (measurement of this run, not a universal rate).** Of the
209 pending snapshots: 121 × `0x0400` (AUDIO only), 65 × `0x0100` (VIDEO only),
23 × `0x0500` (both). 121 + 23 = 144 AUDIO and 65 + 23 = 88 VIDEO, matching the
drain counts exactly.

**Frame-start boundaries (FACT, this run).** Recomputed from the raw first four
bytes of all 88 blocks: GBI's predicate and the Start-up Disc's predicate agree
on **every one of the 88 blocks (0 divergences)** and both give positions
0, 25, 65 — intervals 25 and 40. **One complete boundary-to-boundary interval of
exactly 40 VIDEO blocks was observed** (seq25 → seq65). The general "40 blocks
per frame" model is therefore CORROBORATED by three independent sources: the
Disc's constants, GBI's constants and this physical interval.

**The first interval of 25 is a startup transient, not a 25-block frame.** The
four VERIFY cycles at the start cost 34 792 ticks each against 3 101 for a lean
cycle (11×); the device's VIDEO block is single-buffered, so blocks produced
while the probe was still servicing were overwritten and never signalled as
separate causes. At the steady cadence (11 891 ticks per block) the 628 474
ticks of the first interval would carry ~37 blocks; 25 were captured. The probe
drained every VIDEO source it saw (88 selected, 88 attempted, 88 completed), so
the loss is on the device side, not ours. The log does not let the count of lost
blocks be proven exactly — see U-GBP-030.

**Timing (measurements of this run).**

| Interval | Ticks | ms | Note |
|---|---|---|---|
| seq0 → seq25 | 628 474 | 15.518 | startup transient, not one frame |
| seq25 → seq65 | 680 138 | 16.794 | one complete frame = **59.547 Hz** |
| seq25 → seq64 | 464 059 | 11.458 | the 39 active block gaps |
| seq64 → seq65 | 216 079 | 5.335 | the long gap that closes the frame |

Steady per-block gap: 11 891 ticks (0.294 ms) median over seq26..seq64.

**AUDIO-only gap.** Between the VIDEO block seq64 (cycle 141) and seq65 (cycle
164) there are exactly **22 consecutive AUDIO-only `0x0400` cycles** (142..163)
and no VIDEO source, spanning the 5.335 ms gap above. Reading that gap as the
AGB's vertical blanking is CORROBORATED by both references' frame structure; it
is not established by this single run alone.

**VIDEO payload (FACT, this run).** Under the byte 1 / byte 3 picking both
references perform, the 88 blocks carry exactly **two** semantic payloads:
85 blocks of 960 × `0x7FFF`, and 3 blocks — precisely seq 0, 25 and 65, the
frame starts — of `0xFFFF` followed by 959 × `0x7FFF`. The complete frame
seq25..seq64 is 40 blocks = 38 400 elements, uniform apart from the start marker
on its first element. Under the static 4 × 240 geometry that is 160 lines × 240,
all white; the geometry itself remains CORROBORATED from the references and is
not validated visually by this run.

**Byte 0 variability (FACT, this run).** Over the 84 480 pixel words of the 88
blocks, byte 0 differs from byte 1 in **688 words, always `ff`/`7f`**, and byte 2
never differs from byte 3 (0 cases). The exceptions **never** occur at the first
word of a 32-byte DMA line (0 of 10 560) and occur at a ~0.9 % rate at each of
the other seven positions. Crucially, the byte 1 / byte 3 payload of seq0 is
**byte-identical** to the GBP-AV-SERVICE-001 physical block although the raw
CRC-32s differ (`fe45ff08` vs `ef18fc8d`) and the exception counts differ (5 vs
9); both blocks give GBI checksum `0x7F0FFF10`. Byte 0 variability therefore does
**not** alter the payload either reference consumes. Whether it is a bus/DMA
artefact remains open — see U-GBP-029.

**Offline oracle (not a gate).** With the private inputs and the capture aligned
on its complete interval (seq25 = frame position 0), the physical frame matches
the references at exactly the positions they define as white and differs at
exactly the positions where they embed the logotype: GBI table A 28/40, the 12
mismatches being **exactly blocks 14..25**; table B 32/40, the 8 mismatches being
**exactly blocks 12..19**; the Disc's embedded frame 28/40, mismatches **exactly
14..25**. The physical per-block checksums are exactly two values — `0xFF0FFF0F`
(39 blocks) and `0x7F0FFF10` (1 block) — which are precisely table A entry 1
(all-white without the flag) and entry 0 (all-white with the flag). The AGB was
showing a **blank white screen**, not the boot logotype the references embed.
Nothing indicates a hardware or capture fault; the divergence identifies a
different device state. Note that `tools/avseq.py oracle` aligns on the first
boundary and reported `partial_match` using the transient 25 interval; the
corrected alignment above is the meaningful one — see the follow-up in the DEVLOG.

**AUDIO.** 144 drains, all completed, 9 payloads preserved by design (the first
8 successful drains and the last valid one): CRC-32 `46976584`, `6c7d6969`,
`93ae870e`, `eb52f01e`, `e6e2e1af`, `51669894`, `889c3d29`, `ae982577`,
`e36172fa`. The first eight (cycles 0,1,2,3,4,6,8,10) carry 16–36 nonzero bytes
of 4096; the last (cycle 207) carries 2178. No format or PCM interpretation is
attempted here. The other 135 drains have metadata and **no recorded bytes**.

**Teardown.** CPU masked, CONTROL `8c → 90`, IRQSTOPPRE `0x0500`, stop word
`IRQ := 0x8FAA` (`0x0500 | 0x8AAA`) read back `0x8AAA` with masks and bit 15
confirmed, one PI cleanup W1C (`00012000 → 00010000`, not sticky), handler
restored, INTMR bit 13 = 0 (`000001fa`), AR_INFO `005b → 0043` read back, FINAL
CONTROL `00` IRQ `9090`. The 210th cause was never delivered: it was latched,
refused at the admission point and closed by that single W1C.

**Implementation follow-up (not a defect of this run).** 2 632 017 ticks
(64.99 ms) elapse between the last WAIT_NEXT observation and the teardown's first
hardware write. `finish()` runs `summarize()` (CRC-32 and scans over 374 784
bytes) and `log_lean_cycles()` (1 230 formatted records) **before**
`teardown_video()`. The device stayed in the experimental CONTROL state and the
cause stayed latched for that extra 65 ms; the teardown then succeeded and
`restore=ok`. A future build should perform the hardware teardown first and
compute the summaries afterwards.

### SMOKE-HW-001 — 2026-09-14 — PASS

```text
Test ID     SMOKE-HW-001
Build ID    smoke-0002
Commit      55ed6c1
DOL         build/poc/smoke-test/smoke-test.dol
SHA-256     4175f21dcae4d4ef4ba2c46d9aad1cc16fced5520b5a57edb4b6e7806c54fe88
Setup       GameCube + Swiss + SD2SP2 (FAT); no cartridge; Game Boy Player not accessed
            (attached state not recorded — irrelevant to this test); Link Port and BBA irrelevant
Steps       copied DOL to SD, launched through Swiss, watched the heartbeat, pressed X, pressed START
```

Observed (user report + file written by the GameCube itself):

```text
# OPENGBP-LOG v1
test_id=SMOKE-HW-001
build_id=smoke-0002
commit=55ed6c1
lines=3 dropped=0 truncated=0
# --- records ---
000000 IDENT test=SMOKE-HW-001 app=smoke-test build=smoke-0002 commit=55ed6c1 libogc=libogc2 r2442.094b250
000001 VIDEO 640x480 tvmode=0 gecko=0
000002 STATE seconds=8 frames=537 lit=7363 hash=d97192c5 buttons_seen=0400
# --- end --- dropped=0
```

- START returned to Swiss (user confirmation).
- `tvmode=0` = NTSC; `frames=537` after `seconds=8` is consistent with a
  60 Hz VSync loop (8 × 60 plus the fraction of the ninth second).
- `lit=7363` and a stable identity-row hash match the Dolphin runs
  (6289–7502 lit pixels): the console rendered the same content.
- `buttons_seen=0400` = X was the only button held before saving;
  `gecko=0` = no USB Gecko, as expected on real hardware.
- The log file exists → SD2SP2 mount, directory creation, write and
  unmount worked (`src/platform/sdlog.c`).

Conclusion: the pipeline Docker → devkitPPC/libogc2 → elf2dol →
`tools/dolpad.py` → Swiss produces a DOL that runs on the real GameCube
with video, pad input and SD2SP2 logging, and exits cleanly. Recorded as
`ENV-HW-001`; closes `U-ENV-002`. **Nothing about the Game Boy Player
follows from this test.**

Raw log: transcription kept locally as
`captures/local/SMOKE-HW-001_smoke-0002.log` (ignored by Git; the
original file stays on the user's SD card).

### GBP-PROBE-001 — 2026-09-14 — completed (analysis in DEVLOG, evidence GBP-HW-001…006)

```text
Test ID     GBP-PROBE-001
Build ID    probe-0001
Commit      55ed6c1
DOL         build/poc/gbp-probe/gbp-probe.dol
SHA-256     36d8b23b14afbc191899ca0ddf4ad9b845cedf6c09a26b3d6a6187a8c2862994
Log         original file written by the GameCube: 4945 bytes,
            sha256 98ba20d5bcc32ba65138962dab37abe360659b634512c25423e1b879b96ff014,
            kept unmodified as captures/local/GBP-PROBE-001_probe-0001.log (ignored by Git;
            user's copy in logs/); versioned replay fixture:
            captures/fixtures/hw-gamecube-gbp-2026-09-14-probe-0001.gbpreplay (SOURCE = physical GameCube + GBP)
Capture     2026-09-14
Setup       real GameCube; Game Boy Player attached to the HSP for the whole run; NO Game Pak;
            GBP Link Port empty; PicoAdapterGB disconnected; Broadband Adapter physically
            attached, no Ethernet cable; 1 controller; 1 Memory Card; SD2SP2 (load + save)
Interaction none during acquisition; X pressed once afterwards (save), START once (exit to Swiss)
Screen      photo consistent with the log (corroborative only): AR_INFO 0043/0043/005b/0043
            restored=yes; MODE A reads 6/6 test match 2/4 byte1F 4 present=0; MODE B reads 6/6
            test match 3/4 byte1F 4 present=0; errors=0 transfers=28 timeouts=0 busy=0
```

Full log (verbatim):

```text
# OPENGBP-LOG v1
test_id=GBP-PROBE-001
build_id=probe-0001
commit=55ed6c1
libogc=libogc2 r2442.094b250 gecko=0
lines=45 dropped=0 truncated=0
# --- records ---
000000 IDENT test=GBP-PROBE-001 app=gbp-probe build=probe-0001 commit=55ed6c1 libogc=libogc2 r2442.094b250
000001 ENV bus_hz=162000000 tb_hz=40500000 dma_timeout_ms=200 csr=0804
000002 PROBE start npatterns=4 nindices=3 exp_code=3 mode_b=1
000003 ARINFO orig value=0043 size_code=3 exp_code=0 base=01000000
000004 ARINFO modeA value=0043 size_code=3 exp_code=0 base=01000000
000005 MODE A begin base=01000000
000006 RAW mode=A idx=0 addr=01000000 rc=ok ticks=31 polls=7 dspcr=0804 data=0000000000000000000000000000000000000000000000000000000000000000
000007 RAW mode=A idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 data=0000000000000000000000000000000000000000000000000000000000000000
000008 RAW mode=A idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 data=9090909090909090909090909090909090909090909090909090909090909090
000009 TESTW mode=A idx=0 pattern=c3 rc=ok ticks=30 polls=8 dspcr=0804
000010 TESTR mode=A idx=0 pattern=c3 expect=3c rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=1 data=7c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c
000011 TESTW mode=A idx=0 pattern=3c rc=ok ticks=31 polls=8 dspcr=0804
000012 TESTR mode=A idx=0 pattern=3c expect=c3 rc=ok ticks=37 polls=10 dspcr=0804 match_all=0 match_1f=1 data=c7c3c3c3c3c3c7c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3
000013 TESTW mode=A idx=0 pattern=ff rc=ok ticks=31 polls=8 dspcr=0804
000014 TESTR mode=A idx=0 pattern=ff expect=00 rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 data=0000000000000000000000000000000000000000000000000000000000000000
000015 TESTW mode=A idx=0 pattern=00 rc=ok ticks=31 polls=8 dspcr=0804
000016 TESTR mode=A idx=0 pattern=00 expect=ff rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 data=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
000017 RAW mode=A idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=0000000000000000000000000000000000000000000000000000000000000000
000018 RAW mode=A idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 data=0000000000000000000000000000000000000000000000000000000000000000
000019 RAW mode=A idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 data=9090909090909090909090909090909090909090909090909090909090909090
000020 ARINFO endA value=0043 size_code=3 exp_code=0 base=01000000
000021 MODE A end reads_ok=6 reads_failed=0 tests=4 match_all=2 match_1f=4 tests_failed=0 present=0
000022 ARINFO write mode=B value=005b rc=ok
000023 ARINFO modeB value=005b size_code=3 exp_code=3 base=01000000
000024 MODE B begin base=01000000
000025 RAW mode=B idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=0000000000000000000000000000000000000000000000000000000000000000
000026 RAW mode=B idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 data=9490909090909090909090909090909090909090909090909090909090909090
000027 RAW mode=B idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 data=ae8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000028 TESTW mode=B idx=0 pattern=c3 rc=ok ticks=31 polls=8 dspcr=0804
000029 TESTR mode=B idx=0 pattern=c3 expect=3c rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 data=3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c
000030 TESTW mode=B idx=0 pattern=3c rc=ok ticks=31 polls=8 dspcr=0804
000031 TESTR mode=B idx=0 pattern=3c expect=c3 rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=1 data=c7c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3
000032 TESTW mode=B idx=0 pattern=ff rc=ok ticks=31 polls=8 dspcr=0804
000033 TESTR mode=B idx=0 pattern=ff expect=00 rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 data=0000000000000000000000000000000000000000000000000000000000000000
000034 TESTW mode=B idx=0 pattern=00 rc=ok ticks=37 polls=10 dspcr=0804
000035 TESTR mode=B idx=0 pattern=00 expect=ff rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 data=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
000036 RAW mode=B idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=0000000000000000000000000000000000000000000000000000000000000000
000037 RAW mode=B idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 data=9090909090909090909090909090909090909090909090909090909090909090
000038 RAW mode=B idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 data=ae8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000039 ARINFO endB value=005b size_code=3 exp_code=3 base=01000000
000040 MODE B end reads_ok=6 reads_failed=0 tests=4 match_all=3 match_1f=4 tests_failed=0 present=0
000041 ARINFO restore value=0043 rc=ok
000042 ARINFO final value=0043 size_code=3 exp_code=0 base=01000000
000043 PROBE end modes=2 errors=0 changed=1 restored=1
000044 STATS transfers=28 timeouts=0 busy=0
# --- end --- dropped=0
```

Facts extracted from it are GBP-HW-001 … GBP-HW-006 in `EVIDENCE.md`;
the byte-level analysis, the backend audit and the interpretation of
`present=0` are in the DEVLOG entry of 2026-09-14. **`present=0` is the
output of the probe-0001 heuristic (all 32 bytes must equal the
complement), not a statement that the GBP was absent; it was attached.**

### GBP-BASELINE-NOGBP-001 — 2026-09-14 — completed (baseline without the Game Boy Player)

```text
Physical Run ID  GBP-BASELINE-NOGBP-001   (the log itself says test_id=GBP-PROBE-001: same DOL, not rebuilt)
Build ID         probe-0001
Commit           55ed6c1
DOL              build/poc/gbp-probe/gbp-probe.dol
SHA-256          36d8b23b14afbc191899ca0ddf4ad9b845cedf6c09a26b3d6a6187a8c2862994
Log              user's file logs/GBP-PROBE-001_probe-0001-semGBP.log, 4944 bytes,
                 sha256 03e930ff25f10ed25e610cc1ed14e92cd521a4c91d3eef40f4c52079ba19c8f9,
                 preserved unmodified as captures/local/GBP-BASELINE-NOGBP-001_probe-0001.log;
                 fixture captures/fixtures/hw-gamecube-nogbp-2026-09-14-probe-0001.gbpreplay
                 (SOURCE=physical GameCube, GBP_PRESENT=no)
Setup            same console; Game Boy Player physically REMOVED with the console powered off;
                 BBA attached without Ethernet; same single controller; same Memory Card; SD2SP2;
                 Swiss; no cartridge (n/a); no PicoAdapterGB; no interaction until X / START
Single variable  presence of the Game Boy Player (vs GBP-PROBE-001 of the same day)
```

Full log (verbatim):

```text
# OPENGBP-LOG v1
test_id=GBP-PROBE-001
build_id=probe-0001
commit=55ed6c1
libogc=libogc2 r2442.094b250 gecko=0
lines=45 dropped=0 truncated=0
# --- records ---
000000 IDENT test=GBP-PROBE-001 app=gbp-probe build=probe-0001 commit=55ed6c1 libogc=libogc2 r2442.094b250
000001 ENV bus_hz=162000000 tb_hz=40500000 dma_timeout_ms=200 csr=0804
000002 PROBE start npatterns=4 nindices=3 exp_code=3 mode_b=1
000003 ARINFO orig value=0043 size_code=3 exp_code=0 base=01000000
000004 ARINFO modeA value=0043 size_code=3 exp_code=0 base=01000000
000005 MODE A begin base=01000000
000006 RAW mode=A idx=0 addr=01000000 rc=ok ticks=31 polls=7 dspcr=0804 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000007 RAW mode=A idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000008 RAW mode=A idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000009 TESTW mode=A idx=0 pattern=c3 rc=ok ticks=31 polls=8 dspcr=0804
000010 TESTR mode=A idx=0 pattern=c3 expect=3c rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=0 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000011 TESTW mode=A idx=0 pattern=3c rc=ok ticks=31 polls=8 dspcr=0804
000012 TESTR mode=A idx=0 pattern=3c expect=c3 rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=0 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000013 TESTW mode=A idx=0 pattern=ff rc=ok ticks=31 polls=8 dspcr=0804
000014 TESTR mode=A idx=0 pattern=ff expect=00 rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=0 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000015 TESTW mode=A idx=0 pattern=00 rc=ok ticks=31 polls=8 dspcr=0804
000016 TESTR mode=A idx=0 pattern=00 expect=ff rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=0 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000017 RAW mode=A idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000018 RAW mode=A idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000019 RAW mode=A idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000020 ARINFO endA value=0043 size_code=3 exp_code=0 base=01000000
000021 MODE A end reads_ok=6 reads_failed=0 tests=4 match_all=0 match_1f=0 tests_failed=0 present=0
000022 ARINFO write mode=B value=005b rc=ok
000023 ARINFO modeB value=005b size_code=3 exp_code=3 base=01000000
000024 MODE B begin base=01000000
000025 RAW mode=B idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000026 RAW mode=B idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000027 RAW mode=B idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000028 TESTW mode=B idx=0 pattern=c3 rc=ok ticks=31 polls=8 dspcr=0804
000029 TESTR mode=B idx=0 pattern=c3 expect=3c rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=0 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000030 TESTW mode=B idx=0 pattern=3c rc=ok ticks=31 polls=8 dspcr=0804
000031 TESTR mode=B idx=0 pattern=3c expect=c3 rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=0 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000032 TESTW mode=B idx=0 pattern=ff rc=ok ticks=31 polls=8 dspcr=0804
000033 TESTR mode=B idx=0 pattern=ff expect=00 rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=0 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000034 TESTW mode=B idx=0 pattern=00 rc=ok ticks=30 polls=8 dspcr=0804
000035 TESTR mode=B idx=0 pattern=00 expect=ff rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=0 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000036 RAW mode=B idx=0 addr=01000000 rc=ok ticks=38 polls=10 dspcr=0804 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000037 RAW mode=B idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000038 RAW mode=B idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 data=c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
000039 ARINFO endB value=005b size_code=3 exp_code=3 base=01000000
000040 MODE B end reads_ok=6 reads_failed=0 tests=4 match_all=0 match_1f=0 tests_failed=0 present=0
000041 ARINFO restore value=0043 rc=ok
000042 ARINFO final value=0043 size_code=3 exp_code=0 base=01000000
000043 PROBE end modes=2 errors=0 changed=1 restored=1
000044 STATS transfers=28 timeouts=0 busy=0
# --- end --- dropped=0
```

Result: every block and every handshake read-back was `C0`×32 in both
modes; all 28 transfers completed (7–10 polls, 31–38 ticks); AR_INFO
`0043 → 005b → 0043`. Facts GBP-HW-007…009; pair analysis in the DEVLOG
entry of 2026-09-15.

### GBP-INIT-001 — 2026-09-15 — completed, GBP attached (status=ok)

```text
Test ID     GBP-INIT-001
Build ID    init-0001
Commit      a3d9668 (clean)
DOL         build/poc/gbp-init-probe/gbp-init-probe.dol
SHA-256     6068d1348792928b179bdd054bd2ce013fe5e0b7b25c8da7ac781c5f43b2a1e5
Log         logs/GBP-INIT-001_init-0001.log, 5497 bytes,
            sha256 d1e90daf81daa88d5303c9011d78ab245773f07e789e3e180ab7d0c468a7956e
            (original untouched; preserved copy captures/local/GBP-INIT-001_init-0001.log;
            fixture captures/fixtures/hw-gamecube-gbp-2026-09-15-init-0001.gbpreplay)
Setup       same as GBP-PROBE-001: GBP attached whole run, no Game Pak, Link Port empty,
            no PicoAdapterGB, BBA attached without Ethernet, 1 controller, 1 Memory Card,
            SD2SP2, Swiss; no interaction until X (save) / START (exit)
```

Full log (verbatim):

```text
# OPENGBP-LOG v1
test_id=GBP-INIT-001
build_id=init-0001
commit=a3d9668
libogc=libogc2 r2442.094b250 gecko=0
lines=49 dropped=0 truncated=0
# --- records ---
000000 IDENT test=GBP-INIT-001 app=gbp-init-probe build=init-0001 commit=a3d9668 libogc=libogc2 r2442.094b250
000001 ENV bus_hz=162000000 tb_hz=40500000 dma_timeout_ms=200 csr=0804
000002 INIT start exp_code=3 clear=10 set=0c idle_shape=1 npatterns=4
000003 ARINFO orig value=0043 size_code=3 exp_code=0 base=01000000
000004 ARINFO exp value=005b exp_code=3
000005 TESTW tag=DET idx=0 addr=01000000 pattern=c3 rc=ok ticks=29 polls=7 dspcr=0804
000006 TESTR tag=DET idx=0 addr=01000000 pattern=c3 expect=3c rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=1 match_b1=1 match_vote=1 vote=3c data=7c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c
000007 TESTW tag=DET idx=0 addr=01000000 pattern=3c rc=ok ticks=30 polls=8 dspcr=0804
000008 TESTR tag=DET idx=0 addr=01000000 pattern=3c expect=c3 rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=c3 data=c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3
000009 TESTW tag=DET idx=0 addr=01000000 pattern=ff rc=ok ticks=31 polls=8 dspcr=0804
000010 TESTR tag=DET idx=0 addr=01000000 pattern=ff expect=00 rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=00 data=0000000000000000000000000000000000000000000000000000000000000000
000011 TESTW tag=DET idx=0 addr=01000000 pattern=00 rc=ok ticks=31 polls=8 dspcr=0804
000012 TESTR tag=DET idx=0 addr=01000000 pattern=00 expect=ff rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=ff data=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
000013 DET verdict=present run=4 transport_ok=4 vote_ok=4 b1_ok=4 all32_ok=3
000014 PI tag=PRE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000015 INTMR unchanged value=000001fa bit13=0
000016 SNAP tag=S0 ticks=598792135 since_write=0
000017 PI S0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000018 RAW S0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=90 sem_b1f=90 data=9890909090909090909090909090909090909090909090909090909090909090
000019 RAW S0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=aa8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000020 RAW S0 idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=0000000000000000000000000000000000000000000000000000000000000000
000021 CONTROL semantic orig=90 exp=8c method=gbi-majority-vote transform=(v&~10)|0c
000022 CTLW tag=EXP addr=01400000 semantic=8c rc=ok ticks=31 polls=8 dspcr=0804 layout=gbi-replicated data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000023 SNAP tag=S1 ticks=598797204 since_write=56
000024 PI S1 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000025 RAW S1 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ec8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000026 RAW S1 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=ea8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000027 SNAP tag=S2 ticks=598799904 since_write=2756
000028 PI S2 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000029 RAW S2 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000030 RAW S2 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=aa8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000031 TRANSITION s1_s2=1
000032 SNAP tag=S3 ticks=598802867 since_write=5719
000033 PI S3 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000034 RAW S3 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000035 RAW S3 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=aa8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000036 CTLW tag=RESTORE addr=01400000 semantic=90 rc=ok ticks=31 polls=8 dspcr=0804 layout=gbi-replicated data=9090909090909090909090909090909090909090909090909090909090909090
000037 SNAP tag=S4 ticks=598806379 since_write=9231
000038 PI S4 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000039 RAW S4 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=90 sem_b1f=90 data=9890909090909090909090909090909090909090909090909090909090909090
000040 RAW S4 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=ea8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000041 CONTROL restore semantic=90 readback_vote=90 readback_b1f=90 ok=1
000042 ARINFO restore value=0043 rc=ok readback=0043 ok=1
000043 INIT end status=ok reason=- written=1 control_restored=1 arinfo_restored=1 intmr_restored=-1 errors=0 transport_ok=1
000044 SNAP tag=S5 ticks=598810935 since_write=13787
000045 PI S5 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000046 RAW S5 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=00 sem_b1f=00 data=0000000000000000000000000000000000000000000000000000000000000000
000047 RAW S5 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=9090 sem_gbi=9090 data=9890909090909090909090909090909090909090909090909090909090909090
000048 STATS transfers=23 timeouts=0 busy=0
# --- end --- dropped=0
```

Facts GBP-HW-011…018; snapshot/bit/timing analysis in the DEVLOG entry
of 2026-09-15 and `tools/blockdiff.py --snapshots`.

### GBP-INIT-BASELINE-NOGBP-001 — 2026-09-15 — completed, GBP removed (abort_not_present)

```text
Physical Run ID  GBP-INIT-BASELINE-NOGBP-001 (log says test_id=GBP-INIT-001; same DOL)
Build / Commit   init-0001 / a3d9668, DOL sha256 6068d134…a1e5
Log              logs/GBP-INIT-001_init-0001-semGBP.log, 2090 bytes,
                 sha256 97f7cc70409d6653cc7b723b2ae1012bef513da11398a4c33ae627f1289b6c5e
                 (preserved copy captures/local/GBP-INIT-001_init-0001-semGBP.log;
                 fixture captures/fixtures/hw-gamecube-nogbp-2026-09-15-init-0001.gbpreplay)
Setup            same as above with the Game Boy Player physically removed (console off for the swap)
```

Full log (verbatim):

```text
# OPENGBP-LOG v1
test_id=GBP-INIT-001
build_id=init-0001
commit=a3d9668
libogc=libogc2 r2442.094b250 gecko=0
lines=17 dropped=0 truncated=0
# --- records ---
000000 IDENT test=GBP-INIT-001 app=gbp-init-probe build=init-0001 commit=a3d9668 libogc=libogc2 r2442.094b250
000001 ENV bus_hz=162000000 tb_hz=40500000 dma_timeout_ms=200 csr=0804
000002 INIT start exp_code=3 clear=10 set=0c idle_shape=1 npatterns=4
000003 ARINFO orig value=0043 size_code=3 exp_code=0 base=01000000
000004 ARINFO exp value=005b exp_code=3
000005 TESTW tag=DET idx=0 addr=01000000 pattern=c3 rc=ok ticks=29 polls=7 dspcr=0804
000006 TESTR tag=DET idx=0 addr=01000000 pattern=c3 expect=3c rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=0 match_b1=0 match_vote=0 vote=c1 data=c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1
000007 TESTW tag=DET idx=0 addr=01000000 pattern=3c rc=ok ticks=30 polls=8 dspcr=0804
000008 TESTR tag=DET idx=0 addr=01000000 pattern=3c expect=c3 rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=0 match_b1=0 match_vote=0 vote=c1 data=c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1
000009 TESTW tag=DET idx=0 addr=01000000 pattern=ff rc=ok ticks=30 polls=8 dspcr=0804
000010 TESTR tag=DET idx=0 addr=01000000 pattern=ff expect=00 rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=0 match_b1=0 match_vote=0 vote=c1 data=c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1
000011 TESTW tag=DET idx=0 addr=01000000 pattern=00 rc=ok ticks=31 polls=8 dspcr=0804
000012 TESTR tag=DET idx=0 addr=01000000 pattern=00 expect=ff rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=0 match_b1=0 match_vote=0 vote=c1 data=c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1
000013 DET verdict=absent run=4 transport_ok=4 vote_ok=0 b1_ok=0 all32_ok=0
000014 ARINFO restore value=0043 rc=ok readback=0043 ok=1
000015 INIT end status=abort_not_present reason=absent written=0 control_restored=-1 arinfo_restored=1 intmr_restored=-1 errors=0 transport_ok=1
000016 STATS transfers=8 timeouts=0 busy=0
# --- end --- dropped=0
```

Result: every TEST read-back `C1`×32 (previous no-GBP baseline with
probe-0001: `C0`×32), verdict ABSENT, no CONTROL write, AR_INFO restored
(GBP-HW-019/020).

### GBP-INIT-002 — 2026-09-15 — completed, GBP attached (status=timeout_no_irq_observed, restore=ok)

```text
Test ID     GBP-INIT-002
Build ID    initirq-0001
Commit      4e3cb43 (clean)
DOL         build/poc/gbp-init-irq-probe/gbp-init-irq-probe.dol
SHA-256     1bd2bcf3f361e6482c888a523d45ea2fa2dc073f41918ebfab7803b1177343f2
Log         logs/GBP-INIT-002_initirq-0001.log, 6585 bytes,
            sha256 e7ec3d83212fb183d8209452e2ce46cf391a696ff8a41720fd9f7701dbf1ea1d
            (original untouched; preserved copy captures/local/GBP-INIT-002_initirq-0001.log;
            fixture captures/fixtures/hw-gamecube-gbp-2026-09-15-initirq-0001.gbpreplay with the
            physical time base and the interrupt path as it happened — the handler never ran)
Setup       GBP attached whole run, no Game Pak, Link Port empty, no PicoAdapterGB, BBA attached
            without Ethernet, 1 controller, 1 Memory Card, SD2SP2, Swiss; no interaction until
            X (save) / START (exit); console power-cycled afterwards
T_MAX       2000 ms (81000000 ticks at 40.5 MHz) — operational bound, not a GBP property
```

Full log (verbatim):

```text
# OPENGBP-LOG v1
test_id=GBP-INIT-002
build_id=initirq-0001
commit=4e3cb43
libogc=libogc2 r2442.094b250 gecko=0
lines=60 dropped=0 truncated=0
# --- records ---
000000 IDENT test=GBP-INIT-002 app=gbp-init-irq-probe build=initirq-0001 commit=4e3cb43 libogc=libogc2 r2442.094b250
000001 ENV bus_hz=162000000 tb_hz=40500000 dma_timeout_ms=200 t_max_ms=2000 csr=0804
000002 INITIRQ start exp_code=3 clear=10 set=0c idle_shape=1 npatterns=4 t_max_ms=2000 t_max_ticks=81000000 tb_hz=40500000
000003 ARINFO orig value=0043 size_code=3 exp_code=0 base=01000000
000004 ARINFO exp value=005b exp_code=3
000005 TESTW tag=DET idx=0 addr=01000000 pattern=c3 rc=ok ticks=35 polls=7 dspcr=0804
000006 TESTR tag=DET idx=0 addr=01000000 pattern=c3 expect=3c rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=1 match_b1=1 match_vote=1 vote=3c data=3d3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c
000007 TESTW tag=DET idx=0 addr=01000000 pattern=3c rc=ok ticks=31 polls=8 dspcr=0804
000008 TESTR tag=DET idx=0 addr=01000000 pattern=3c expect=c3 rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=1 match_b1=1 match_vote=1 vote=c3 data=d3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3
000009 TESTW tag=DET idx=0 addr=01000000 pattern=ff rc=ok ticks=31 polls=8 dspcr=0804
000010 TESTR tag=DET idx=0 addr=01000000 pattern=ff expect=00 rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=1 match_b1=1 match_vote=1 vote=00 data=1100000000000000000000000000000000000000000000000000000000000000
000011 TESTW tag=DET idx=0 addr=01000000 pattern=00 rc=ok ticks=31 polls=8 dspcr=0804
000012 TESTR tag=DET idx=0 addr=01000000 pattern=00 expect=ff rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=ff data=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
000013 DET verdict=present run=4 transport_ok=4 vote_ok=4 b1_ok=4 all32_ok=1
000014 PI tag=PRE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000015 PRECOND intsr13=0 intmr13=0 irq_path=1 ok=1 reason=-
000016 SNAP tag=S0 ticks=3267396886 since_write=0 since_unmask=0
000017 PI tag=S0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000018 RAW S0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=90 sem_b1f=90 data=9190909090909090909090909090909090909090909090909090909090909090
000019 RAW S0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=9b8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000020 RAW S0 idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=1100000000000000000000000000000000000000000000000000000000000000
000021 CONTROL semantic orig=90 exp=8c method=gbi-majority-vote transform=(v&~10)|0c
000022 IRQ install rc=ok old_handler=null
000023 CTLW tag=EXP addr=01400000 semantic=8c rc=ok ticks=31 polls=8 dspcr=0804 layout=gbi-replicated data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000024 SNAP tag=S1 ticks=3267402449 since_write=124 since_unmask=0
000025 PI tag=S1 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000026 RAW S1 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9d8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000027 RAW S1 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=9b8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000028 PI tag=UNMASKPRE rc=ok intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000029 UNMASK t_unmask=3267405264 rc=ok t_post=3267405297 dt_post=33
000030 PI tag=UNMASKPOST rc=ok intsr=00010000 intmr=000021fa intsr13=0 intmr13=1 fired=0
000031 IRQ mask tag=MAIN rc=ok
000032 WAIT fired=0 timed_out=1 polls=13871306 wait_ticks=81000012 wait_us=2000000 t_max_ms=2000 t_max_ticks=81000000
000033 SNAP tag=S2 ticks=3348406686 since_write=81004361 since_unmask=81001422
000034 PI tag=S2 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000035 PI tag=S2b intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000036 RAW S2 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9d8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000037 RAW S2 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8fae sem_gbi=8fae data=9f8fafae8f8fafae8f8fafae8f8fafae8f8fafae8f8fafae8f8fafae8f8fafae
000038 IRQ mask tag=TEARDOWN rc=ok
000039 HANDLER fired=0 count=0 t_entry=0 t_unmask=3267405264 latency_ticks=0 latency_us=0 reentry=0
000040 HANDLERPI intsr_before_ack=00000000 intmr_at_entry=00000000 intsr_after_ack=00000000 intmr_after_mask=00000000 reentry_intsr=00000000 reentry_intmr=00000000
000041 CTLW tag=RESTORE addr=01400000 semantic=90 rc=ok ticks=31 polls=8 dspcr=0804 layout=gbi-replicated data=9090909090909090909090909090909090909090909090909090909090909090
000042 SNAP tag=S3 ticks=3348412912 since_write=81010587 since_unmask=81007648
000043 PI tag=S3 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000044 RAW S3 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=90 sem_b1f=90 data=9190909090909090909090909090909090909090909090909090909090909090
000045 RAW S3 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8fae sem_gbi=8fae data=9f8fafae8f8fafae8f8fafae8f8fafae8f8fafae8f8fafae8f8fafae8f8fafae
000046 CONTROL restore semantic=90 readback_vote=90 readback_b1f=90 ok=1
000047 PI tag=CLEANUPCHK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000048 CLEANUP performed=0 intsr=00010000 intsr13=0 intmr13=0
000049 IRQ restore rc=ok ok=1 old_handler=null
000050 PI tag=MASKCHK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000051 MASK final intmr=000001fa intmr13=0 orig_intmr13=0 ok=1
000052 ARINFO restore value=0043 rc=ok readback=0043 ok=1
000053 SNAP tag=S4 ticks=3348418898 since_write=81016573 since_unmask=81013634
000054 PI tag=S4 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000055 RAW S4 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=00 sem_b1f=00 data=1100000000000000000000000000000000000000000000000000000000000000
000056 RAW S4 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=9090 sem_gbi=9090 data=9190909090909090909090909090909090909090909090909090909090909090
000057 FINAL arinfo=0043 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 control=00 irq=9090
000058 INITIRQ end status=timeout_no_irq_observed reason=no_irq26_within_t_max restore=ok restore_reason=- written=1 fired=0 count=0 timed_out=1 control_restored=1 handler_restored=1 mask_ok=1 arinfo_restored=1 cleanup=0 errors=0 transport_ok=1
000059 STATS transfers=21 timeouts=0 busy=0
# --- end --- dropped=0
```

Result: `timeout_no_irq_observed` / `no_irq26_within_t_max` — **not an
error**: no IRQ 26 was observed within the 2000 ms window, nothing more.
PRESENT 4/4 by both criteria (whole-block 1/4); handler installed with a
NULL previous handler; CONTROL `0x90 → 0x8C`; `__UnmaskIrq(IM_PI_HSP)`
physically changed INTMR `0x000001FA → 0x000021FA` and `__MaskIrq` changed it
back (GBP-HW-022); INTSR stayed `0x00010000` (bit 13 never set) in all 12
reads; the handler never entered (`fired=0 count=0`, HANDLERPI all zero);
wait 81000012 ticks = 2.0000003 s over 13871306 polls; the IRQ block read
`0x8AAE` in S0/S1 and `0x8FAE` in S2/S3 (bits 0x0400 and 0x0100 set, 24/32
bytes changed) while CONTROL stayed `0x8C`, and `0x8FAE` persisted after
the CONTROL restore (GBP-HW-024); S4 under the original AR_INFO read
`00` / `9090` again (GBP-HW-017, third observation); cleanup W1C not needed,
handler restored, INTMR final `0x1FA`, AR_INFO `0x0043`; 21 transfers, 0
timeouts/busy/errors, log 60 lines, 0 dropped/truncated (GBP-HW-021…026).
Analysis and next step: DEVLOG 2026-09-15 "GBP-INIT-002 executed".

### GBP-INIT-003A — 2026-09-15 — completed, GBP attached (status=ok_pi_cause_observed, restore=ok)

```text
Test ID     GBP-INIT-003A
Build ID    initirqa-0001
Commit      d956b1b (clean; release audit of the same day, PHYSICAL CANDIDATE READY)
DOL         build/poc/gbp-init-irq-program-probe/gbp-init-irq-program-probe.dol
SHA-256     8c225bd101a215982ac59d096630a9e13b34557e3cdf4eb8354298855232bfa5
Log         logs/GBP-INIT-003A_initirqa-0001.log, 13231 bytes,
            sha256 ae9117457039727026f00e9ccb349d4af3c85ee6f4f436d290cd40cc0e672ef8
            (original untouched; preserved copy captures/local/GBP-INIT-003A_initirqa-0001.log;
            fixture captures/fixtures/hw-gamecube-gbp-2026-09-15-initirqa-0001.gbpreplay with the
            physical time base, the three IRQ-register writes, the INTSR poll that saw bit 13 and
            the single PI W1C; PI HSP masked throughout, no interrupt path)
Setup       GBP attached whole run, no Game Pak, Link Port empty, no PicoAdapterGB, BBA attached
            without Ethernet, 1 controller, 1 Memory Card, SD2SP2, Swiss; no interaction until
            X (save) / START (exit); console power-cycled afterwards (mandatory)
Bounds      A1 samples +50 µs / +500 µs; A2 samples +50 µs … +2000 ms (operational, not GBP properties)
```

Full log (verbatim):

```text
# OPENGBP-LOG v1
test_id=GBP-INIT-003A
build_id=initirqa-0001
commit=d956b1b
libogc=libogc2 r2442.094b250 gecko=0 power_cycle_required=1
lines=102 dropped=0 truncated=0
# --- records ---
000000 IDENT test=GBP-INIT-003A app=gbp-init-irq-program-probe build=initirqa-0001 commit=d956b1b libogc=libogc2 r2442.094b250
000001 ENV bus_hz=162000000 tb_hz=40500000 dma_timeout_ms=200 t_max_ms=2000 a1_obs_us=50,500 a2_obs_us=50,500,5000,50000,500000,2000000 csr=0804
000002 INITIRQA start exp_code=3 clear=10 set=0c idle_shape=1 req_masks=0aaa req_set=8000 req_clear=7000 ack_or=8000 stop_or=8aaa tb_hz=40500000
000003 INITIRQA window a1_obs_ticks=2025,20250 a2_obs_ticks=2025,20250,202500,2025000,20250000,81000000 n_a1=2 n_a2=6 t_max_ms=2000 poll=1 end_on_event=1
000004 ARINFO orig value=0043 size_code=3 exp_code=0 base=01000000
000005 ARINFO exp value=005b exp_code=3
000006 TESTW tag=DET idx=0 addr=01000000 pattern=c3 rc=ok ticks=33 polls=7 dspcr=0804
000007 TESTR tag=DET idx=0 addr=01000000 pattern=c3 expect=3c rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=3c data=3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c
000008 TESTW tag=DET idx=0 addr=01000000 pattern=3c rc=ok ticks=31 polls=8 dspcr=0804
000009 TESTR tag=DET idx=0 addr=01000000 pattern=3c expect=c3 rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=1 match_b1=1 match_vote=1 vote=c3 data=c7c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3
000010 TESTW tag=DET idx=0 addr=01000000 pattern=ff rc=ok ticks=31 polls=8 dspcr=0804
000011 TESTR tag=DET idx=0 addr=01000000 pattern=ff expect=00 rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=00 data=0000000000000000000000000000000000000000000000000000000000000000
000012 TESTW tag=DET idx=0 addr=01000000 pattern=00 rc=ok ticks=30 polls=8 dspcr=0804
000013 TESTR tag=DET idx=0 addr=01000000 pattern=00 expect=ff rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=ff data=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
000014 DET verdict=present run=4 transport_ok=4 vote_ok=4 b1_ok=4 all32_ok=3
000015 PI tag=PRE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000016 PRECOND intsr13=0 intmr13=0 irq_path_required=0 poll_intsr=1 write_intsr=1 ticks=1 ok=1 reason=-
000017 SNAP tag=BASE ticks=4151222197 since_control=0 since_a1=0 since_a2=0 polls_before=0
000018 PI tag=BASE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000019 RAW BASE idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=90 sem_b1f=90 data=9090909090909090909090909090909090909090909090909090909090909090
000020 RAW BASE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=ae8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000021 RAW BASE idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=0000000000000000000000000000000000000000000000000000000000000000
000022 CONTROL semantic orig=90 exp=8c method=gbi-majority-vote transform=(v&~10)|0c
000023 IRQSHAPE tag=BASE disc=8aae gbi=8aae agree=1 masks_ok=1 bit15_ok=1 high_ok=1 req_masks=0aaa req_set=8000 req_clear=7000 ok=1 reason=-
000024 CTLW tag=EXP addr=01400000 semantic=8c rc=ok ticks=32 polls=8 dspcr=0804 t_after=4151227779 layout=gbi-replicated data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000025 SNAP tag=P0 ticks=4151228760 since_control=981 since_a1=0 since_a2=0 polls_before=0
000026 PI tag=P0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000027 RAW P0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000028 RAW P0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=ae8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000029 RAW P0 idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=0000000000000000000000000000000000000000000000000000000000000000
000030 P0CHK intsr13=0 intmr13=0 control=8c irq=8aae ok=1 reason=-
000031 RAW A1PRE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=ae8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000032 IRQSHAPE tag=A1PRE disc=8aae gbi=8aae agree=1 masks_ok=1 bit15_ok=1 high_ok=1 req_masks=0aaa req_set=8000 req_clear=7000 ok=1 reason=-
000033 A1 before=8aae ack_or=8000 ack_value=8aae formula=read|ack_or
000034 IRQW tag=A1 addr=01d00000 before=8aae write=8aae layout=gbi-u16-replicated rc=ok ticks=31 polls=8 dspcr=0804 t_after=4151233210 data=8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae
000035 SNAP tag=A1-0 ticks=4151233229 since_control=5450 since_a1=19 since_a2=0 polls_before=0
000036 PI tag=A1-0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000037 RAW A1-0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000038 RAW A1-0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=ae8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000039 SNAP tag=A1-50US ticks=4151235239 since_control=7460 since_a1=2029 since_a2=0 polls_before=295
000040 PI tag=A1-50US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000041 RAW A1-50US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000042 RAW A1-50US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=ae8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000043 SNAP tag=A1-500US ticks=4151253465 since_control=25686 since_a1=20255 since_a2=0 polls_before=3407
000044 PI tag=A1-500US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000045 RAW A1-500US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000046 RAW A1-500US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=ae8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000047 WINDOW tag=A1 deadlines=2/2 polls=3407 poll_errors=0 intsr13_seen=1 no_timebase=0
000048 RAW A2PRE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=ae8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000049 PI tag=A2PRE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000050 A2CHK irq_rc=ok pi_ok=1 intsr13=0 intmr13=0 ok=1
000051 A2 before=8aaa value=0000 formula=zero
000052 IRQW tag=A2 addr=01d00000 before=8aaa write=0000 layout=gbi-u16-replicated rc=ok ticks=31 polls=8 dspcr=0804 t_after=4151253956 data=0000000000000000000000000000000000000000000000000000000000000000
000053 SNAP tag=A2-0 ticks=4151253978 since_control=26199 since_a1=20768 since_a2=22 polls_before=0
000054 PI tag=A2-0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000055 RAW A2-0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000056 RAW A2-0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000057 SNAP tag=A2-50US ticks=4151255981 since_control=28202 since_a1=22771 since_a2=2025 polls_before=302
000058 PI tag=A2-50US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000059 RAW A2-50US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000060 RAW A2-50US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000061 SNAP tag=A2-500US ticks=4151274207 since_control=46428 since_a1=40997 since_a2=20251 polls_before=3425
000062 PI tag=A2-500US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000063 RAW A2-500US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000064 RAW A2-500US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000065 SNAP tag=A2-5MS ticks=4151456459 since_control=228680 since_a1=223249 since_a2=202503 polls_before=35042
000066 PI tag=A2-5MS intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000067 RAW A2-5MS idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000068 RAW A2-5MS idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000069 SNAP tag=A2-50MS ticks=4153278961 since_control=2051182 since_a1=2045751 since_a2=2025005 polls_before=351627
000070 PI tag=A2-50MS intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000071 RAW A2-50MS idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000072 RAW A2-50MS idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000073 SNAP tag=EVENT ticks=4155517524 since_control=4289745 since_a1=4284314 since_a2=4263568 polls_before=740497 poll_intsr=00012000
000074 PI tag=EVENT intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000075 RAW EVENT idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000076 RAW EVENT idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0400 sem_gbi=0400 data=0404040004040400040404000404040004040400040404000404040004040400
000077 WINDOW tag=A2 deadlines=4/6 polls=740497 poll_errors=0 ended_early=1 event=1 t_event=4155517524 intsr13_seen=1 t_end=4155517831 elapsed_ticks=4263875 elapsed_us=105280 no_timebase=0
000078 REGION log_count_start=31 log_count_end=31 formatted_inside=0
000079 TEARDOWN start control_written=1 irq_attempted=2 irq_completed=2 uncertain_writes=0 intsr13_seen=1 pi_policy=never_unmasked
000080 CTLW tag=RESTORE addr=01400000 semantic=90 rc=ok ticks=31 polls=8 dspcr=0804 t_after=4155554189 layout=gbi-replicated data=9090909090909090909090909090909090909090909090909090909090909090
000081 RAW TDCTL idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=90 sem_b1f=90 data=9090909090909090909090909090909090909090909090909090909090909090
000082 CONTROL restore semantic=90 rc=ok readback_rc=ok readback_vote=90 readback_b1f=90 ok=1
000083 RAW IRQSTOPPRE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0500 sem_gbi=0500 data=0505040005050500050505000505050005050500050505000505050005050500
000084 IRQSTOP pre rc=ok disc=0500 gbi=0500 stop_or=8aaa stop_value=8faa formula=read|stop_or comment=startup-disc-stop-shadow
000085 IRQW tag=STOP addr=01d00000 before=0500 write=8faa layout=gbi-u16-replicated rc=ok ticks=31 polls=8 dspcr=0804 t_after=4155558446 data=8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa
000086 RAW IRQSTOPPOST idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=ae8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000087 IRQSTOP post rc=ok disc=8aaa gbi=8aaa write_ok=1 readback_ok=1 masks_readback=1 bit15_readback=1
000088 PI tag=CLEANUPCHK intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000089 PI tag=CLEANUP intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000090 CLEANUP performed=1 value=00002000 rc=ok intsr_before=00012000 intsr_after=00010000 intsr13_after=0 sticky=0 ok=1
000091 ARINFO restore value=0043 rc=ok readback=0043 ok=1
000092 SNAP tag=FINAL ticks=4155563096 since_control=4335317 since_a1=4329886 since_a2=4309140 polls_before=0
000093 PI tag=FINAL intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000094 RAW FINAL idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=00 sem_b1f=00 data=0000000000000000000000000000000000000000000000000000000000000000
000095 RAW FINAL idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=9090 sem_gbi=9090 data=9090909090909090909090909090909090909090909090909090909090909090
000096 FINAL arinfo=0043 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 control=00 irq=9090 power_cycle_required=1
000097 INITIRQA end status=ok_pi_cause_observed reason=- restore=ok restore_reason=- power_cycle_required=1 errors=0 transport_ok=1
000098 WRITES control_written=1 irq_attempted=3 irq_completed=3 ctl_exp=1/1 a1=1/1 a2=1/1 stop=1/1 ctl_restore=1/1 uncertain=0 power_cycle_required=1 format=attempted/completed
000099 OBSERVED intsr13_seen=1 t_first_intsr13=4155517524 first_phase=A2 first_value=00012000 polls_at_first=740497 event=1 ended_early=1
000100 RESTORE control_restore_ok=1 irq_stop_write_ok=1 irq_stop_readback_ok=1 stop_masks_readback=1 stop_bit15_readback=1 pi_cleanup_performed=1 pi_cleanup_ok=1 pi_cleanup_sticky=0 arinfo_restore_ok=1
000101 STATS transfers=44 timeouts=0 busy=0
# --- end --- dropped=0
```

Result: `ok_pi_cause_observed`, `restore=ok`, 44 transfers, 0 timeouts /
busy / errors, 102 lines, 0 dropped / truncated, every write attempted =
completed (`uncertain=0`). PRESENT 4/4 by both criteria (whole-block 3/4:
the 3C handshake had byte 0 `C7`); PI `0x00010000` / `0x000001FA` at PRE,
BASE and P0 (bit 13 = 0 in both); BASE CONTROL `0x90`, IRQ `0x8AAE`
(`AE 8A AE AE / 8A 8A AE AE …`); CONTROL `0x90 → 0x8C` accepted; **A1**
`IRQ := 0x8AAE` read back `0x8AAA` 19 ticks (0.47 µs) later and at +50 µs /
+500 µs (bit 0x0004 cleared by writing 1; odd bits and bit 15 unchanged);
**A2** `IRQ := 0x0000` read back `0x0000` at +22 ticks, +50 µs, +500 µs, +5 ms,
+50 ms with CONTROL `0x8C` throughout and INTSR bit 13 = 0; **EVENT** at
t = 4155517524 = 4263568 ticks = 105.273 ms after A2: INTSR `0x00012000`
(bit 13 = 1) with INTMR `0x000001FA` (bit 13 = 0), CONTROL `0x8C`, IRQ
`0x0400` (`04 04 04 00 …`); window ended early (`deadlines=4/6`); teardown:
CONTROL `0x90` restored, IRQ read `0x0500` (`05 05 04 00 / 05 05 05 00 …`,
bit 0x0100 risen after the EVENT), stop `IRQ := 0x8FAA` read back `0x8AAA`
(both sources cleared by writing 1, masks and bit 15 read 1), CLEANUPCHK
INTSR `0x00012000` still set with the device sources gone, one `INTSR :=
0x2000` → `0x00010000`, AR_INFO `0x005B → 0x0043`, FINAL under code 0
`00` / `9090`. Evidence GBP-HW-027…034, GBP-PI-004, GBP-IRQ-007; analysis
in DEVLOG 2026-09-15 "GBP-INIT-003A executed".

**Logging defect found in this run (build initirqa-0001):** record
`000047 WINDOW tag=A1 … intsr13_seen=1` printed the run-global first-sighting
flag after the whole window had ended; the primary A1 records (`000036`,
`000040`, `000044`, `000049`) all read INTSR bit 13 = 0 and `000099 OBSERVED
first_phase=A2 t_first_intsr13=4155517524` places the first sighting in A2.
There was no INTSR bit 13 during A1. The log is preserved as written; later
builds print a phase-local `intsr13_in_phase` field (`src/gbp/gbp_initirqa_probe.c`);
the replay of the fixture through the corrected probe reports
`WINDOW tag=A1 … intsr13_in_phase=0`.

### GBP-INIT-003B — 2026-09-15 — completed, GBP attached (status=ok_delivery_observed, restore=ok)

```text
Test ID     GBP-INIT-003B
Build ID    initirqb-0001
Commit      d3da8cd (clean; release audit of the same day, PHYSICAL CANDIDATE READY)
DOL         build/poc/gbp-init-irq-deliver-probe/gbp-init-irq-deliver-probe.dol
SHA-256     821aa2b2893b6d66fd1398eaeb7de7c475862728e55dc0922d74042d0e9cb757
Log         logs/GBP-INIT-003B_initirqb-0001.log, 17471 bytes,
            sha256 bedb1f013176fec1b3de7c63c4147dfa6770f1eae8c9ec29ee82b027f9d7cf7c
            (original untouched; preserved copy captures/local/GBP-INIT-003B_initirqb-0001.log;
            fixture captures/fixtures/hw-gamecube-gbp-2026-09-15-initirqb-0001.gbpreplay with the
            physical time base, the four IRQ-register writes, the INTSR poll that saw bit 13, the
            interrupt path as it happened (install, unmask with the physical handler record, main
            re-mask, restore) and no main-loop PI W1C; 111 operations replay with 0 mismatches)
Setup       GBP attached whole run, no Game Pak, Link Port empty, no PicoAdapterGB, BBA attached
            without Ethernet, 1 controller, 1 Memory Card, SD2SP2, Swiss; no interaction until
            X (save) / START (exit); console power-cycled afterwards (mandatory)
Bounds      A1/A2 samples as 003A; T_DELIVERY 100 ms after the unmask (operational, not a GBP property)
```

Full log (verbatim):

```text
# OPENGBP-LOG v1
test_id=GBP-INIT-003B
build_id=initirqb-0001
commit=d3da8cd
libogc=libogc2 r2442.094b250 gecko=0 power_cycle_required=1
lines=140 dropped=0 truncated=0
# --- records ---
000000 IDENT test=GBP-INIT-003B app=gbp-init-irq-deliver-probe build=initirqb-0001 commit=d3da8cd libogc=libogc2 r2442.094b250
000001 ENV bus_hz=162000000 tb_hz=40500000 dma_timeout_ms=200 t_max_ms=2000 t_delivery_ms=100 t_delivery_ticks=4050000 a1_obs_us=50,500 a2_obs_us=50,500,5000,50000,500000,2000000 csr=0804
000002 INITIRQB start t_delivery_ms=100 t_delivery_ticks=4050000 ack_or=8000 src_mask=0555 odd_mask=0aaa bit15_mask=8000 high_mask=7000 install_point=after_latched_cause
000003 INITIRQA start exp_code=3 clear=10 set=0c idle_shape=1 req_masks=0aaa req_set=8000 req_clear=7000 ack_or=8000 stop_or=8aaa tb_hz=40500000
000004 INITIRQA window a1_obs_ticks=2025,20250 a2_obs_ticks=2025,20250,202500,2025000,20250000,81000000 n_a1=2 n_a2=6 t_max_ms=2000 poll=1 end_on_event=1
000005 ARINFO orig value=0043 size_code=3 exp_code=0 base=01000000
000006 ARINFO exp value=005b exp_code=3
000007 TESTW tag=DET idx=0 addr=01000000 pattern=c3 rc=ok ticks=30 polls=7 dspcr=0804
000008 TESTR tag=DET idx=0 addr=01000000 pattern=c3 expect=3c rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=3c data=3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c
000009 TESTW tag=DET idx=0 addr=01000000 pattern=3c rc=ok ticks=31 polls=8 dspcr=0804
000010 TESTR tag=DET idx=0 addr=01000000 pattern=3c expect=c3 rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=c3 data=c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3
000011 TESTW tag=DET idx=0 addr=01000000 pattern=ff rc=ok ticks=31 polls=8 dspcr=0804
000012 TESTR tag=DET idx=0 addr=01000000 pattern=ff expect=00 rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=00 data=0000000000000000000000000000000000000000000000000000000000000000
000013 TESTW tag=DET idx=0 addr=01000000 pattern=00 rc=ok ticks=31 polls=8 dspcr=0804
000014 TESTR tag=DET idx=0 addr=01000000 pattern=00 expect=ff rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=ff data=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
000015 DET verdict=present run=4 transport_ok=4 vote_ok=4 b1_ok=4 all32_ok=4
000016 PI tag=PRE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000017 PRECOND intsr13=0 intmr13=0 irq_path_required=0 poll_intsr=1 write_intsr=1 ticks=1 ok=1 reason=-
000018 SNAP tag=BASE ticks=3675594373 since_control=0 since_a1=0 since_a2=0 polls_before=0
000019 PI tag=BASE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000020 RAW BASE idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=90 sem_b1f=90 data=9090909090909090909090909090909090909090909090909090909090909090
000021 RAW BASE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000022 RAW BASE idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=0000000000000000000000000000000000000000000000000000000000000000
000023 CONTROL semantic orig=90 exp=8c method=gbi-majority-vote transform=(v&~10)|0c
000024 IRQSHAPE tag=BASE disc=8aae gbi=8aae agree=1 masks_ok=1 bit15_ok=1 high_ok=1 req_masks=0aaa req_set=8000 req_clear=7000 ok=1 reason=-
000025 CTLW tag=EXP addr=01400000 semantic=8c rc=ok ticks=30 polls=8 dspcr=0804 t_after=3675599972 layout=gbi-replicated data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000026 SNAP tag=P0 ticks=3675600975 since_control=1003 since_a1=0 since_a2=0 polls_before=0
000027 PI tag=P0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000028 RAW P0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000029 RAW P0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000030 RAW P0 idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=0000000000000000000000000000000000000000000000000000000000000000
000031 P0CHK intsr13=0 intmr13=0 control=8c irq=8aae ok=1 reason=-
000032 RAW A1PRE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000033 IRQSHAPE tag=A1PRE disc=8aae gbi=8aae agree=1 masks_ok=1 bit15_ok=1 high_ok=1 req_masks=0aaa req_set=8000 req_clear=7000 ok=1 reason=-
000034 A1 before=8aae ack_or=8000 ack_value=8aae formula=read|ack_or
000035 IRQW tag=A1 addr=01d00000 before=8aae write=8aae layout=gbi-u16-replicated rc=ok ticks=31 polls=8 dspcr=0804 t_after=3675605385 data=8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae
000036 SNAP tag=A1-0 ticks=3675605407 since_control=5435 since_a1=22 since_a2=0 polls_before=0
000037 PI tag=A1-0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000038 RAW A1-0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000039 RAW A1-0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000040 SNAP tag=A1-50US ticks=3675607411 since_control=7439 since_a1=2026 since_a2=0 polls_before=282
000041 PI tag=A1-50US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000042 RAW A1-50US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000043 RAW A1-50US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000044 SNAP tag=A1-500US ticks=3675625637 since_control=25665 since_a1=20252 since_a2=0 polls_before=3271
000045 PI tag=A1-500US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000046 RAW A1-500US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000047 RAW A1-500US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000048 WINDOW tag=A1 deadlines=2/2 polls=3271 poll_errors=0 intsr13_in_phase=0 no_timebase=0
000049 RAW A2PRE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000050 PI tag=A2PRE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000051 A2CHK irq_rc=ok pi_ok=1 intsr13=0 intmr13=0 ok=1
000052 A2 before=8aaa value=0000 formula=zero
000053 IRQW tag=A2 addr=01d00000 before=8aaa write=0000 layout=gbi-u16-replicated rc=ok ticks=30 polls=8 dspcr=0804 t_after=3675626133 data=0000000000000000000000000000000000000000000000000000000000000000
000054 SNAP tag=A2-0 ticks=3675626151 since_control=26179 since_a1=20766 since_a2=18 polls_before=0
000055 PI tag=A2-0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000056 RAW A2-0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000057 RAW A2-0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000058 SNAP tag=A2-50US ticks=3675628160 since_control=28188 since_a1=22775 since_a2=2027 polls_before=291
000059 PI tag=A2-50US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000060 RAW A2-50US idx=4 addr=01400000 rc=ok ticks=37 polls=10 dspcr=0804 sem_vote=8c sem_b1f=8c data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000061 RAW A2-50US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000062 SNAP tag=A2-500US ticks=3675646385 since_control=46413 since_a1=41000 since_a2=20252 polls_before=3276
000063 PI tag=A2-500US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000064 RAW A2-500US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000065 RAW A2-500US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000066 SNAP tag=A2-5MS ticks=3675828637 since_control=228665 since_a1=223252 since_a2=202504 polls_before=33582
000067 PI tag=A2-5MS intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000068 RAW A2-5MS idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000069 RAW A2-5MS idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000070 SNAP tag=A2-50MS ticks=3677651137 since_control=2051165 since_a1=2045752 since_a2=2025004 polls_before=336966
000071 PI tag=A2-50MS intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000072 RAW A2-50MS idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000073 RAW A2-50MS idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000074 SNAP tag=EVENT ticks=3679890204 since_control=4290232 since_a1=4284819 since_a2=4264071 polls_before=709726 poll_intsr=00012000
000075 PI tag=EVENT intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000076 RAW EVENT idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000077 RAW EVENT idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0400 sem_gbi=0400 data=0404040004040400040404000404040004040400040404000404040004040400
000078 WINDOW tag=A2 deadlines=4/6 polls=709726 poll_errors=0 ended_early=1 event=1 t_event=3679890204 intsr13_in_phase=1 t_end=3679890512 elapsed_ticks=4264379 elapsed_us=105293 no_timebase=0
000079 REGION log_count_start=32 log_count_end=32 formatted_inside=0
000080 CAUSE t_event=3679890204 since_a2=4264071 intsr=00012000 intmr=000001fa intsr13=1 intmr13=0 control=8c irq=0400
000081 IRQ install rc=ok old_handler=null record_count=0 record_fired=0
000082 SNAP tag=PREUNMASK ticks=3679926960 since_control=4326988 since_a1=4321575 since_a2=4300827 polls_before=0
000083 PI tag=PREUNMASK intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000084 PI tag=PREUNMASKb intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000085 RAW PREUNMASK idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000086 RAW PREUNMASK idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0500 sem_gbi=0500 data=0505000005050500050505000505050005050500050505000505050005050500
000087 PREUNMASK ok=1 reason=- intsr13=1,1 intmr13=0,0 control=8c irq=0500/0500 src=0500 odd=0000 bit15=0
000088 PI tag=UNMASKPRE rc=ok intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000089 UNMASK t_unmask=3679931504 rc=ok t_post=3679931761 dt_post=257
000090 PI tag=UNMASKPOST rc=ok intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 fired=1
000091 IRQ mask tag=MAIN rc=ok
000092 WAIT fired=1 timed_out=0 polls=1 wait_ticks=1987 wait_us=49 t_delivery_ms=100 t_delivery_ticks=4050000
000093 PI tag=REMASKCHK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000094 HANDLER fired=1 count=1 t_entry=3679931582 t_unmask=3679931504 latency_ticks=78 latency_us=1 reentry=0
000095 HANDLERPI intsr_at_entry=00012000 intmr_at_entry=000021fa intmr_after_mask=000001fa intsr_before_w1c=00012000 intsr_after_w1c=00010000 reentry_intsr=00000000 reentry_intmr=00000000
000096 HANDLERPI2 t_second=3679931730 dt_second=148 intsr_second=00010000 intmr_second=000001fa reentry_t=0
000097 DELIVERY fired=1 count=1 latency_ticks=78 latency_us=1 intsr13_entry=1 intmr13_entry=1 intmr13_after_mask=0 intsr13_before_w1c=1 intsr13_after_w1c=0 intsr13_second=0 intmr13_second=0 main_mask_ok=1 reentry=0
000098 SNAP tag=PREACK ticks=3679938859 since_control=4338887 since_a1=4333474 since_a2=4312726 polls_before=0
000099 PI tag=PREACK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000100 PI tag=PREACKb intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000101 RAW PREACK idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000102 RAW PREACK idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0500 sem_gbi=0500 data=0505050005050500050505000505050005050500050505000505050005050500
000103 PREACK intsr13=0,0 intmr13=0 control=8c irq=0500/0500 src_pending=0500
000104 ACK before=0500 ack_or=8000 ack_value=8500 formula=read|ack_or
000105 IRQW tag=ACK addr=01d00000 before=0500 write=8500 layout=gbi-u16-replicated rc=ok ticks=31 polls=8 dspcr=0804 t_after=3679943682 data=8500850085008500850085008500850085008500850085008500850085008500
000106 SNAP tag=POSTACK ticks=3679944700 since_control=4344728 since_a1=4339315 since_a2=4318567 polls_before=0
000107 PI tag=POSTACK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000108 PI tag=POSTACKb intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000109 RAW POSTACK idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000110 RAW POSTACK idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8000 sem_gbi=8000 data=8080000080800000808000008080000080800000808000008080000080800000
000111 POSTACK intsr13=0,0 intmr13=0 control=8c irq=8000/8000 src_pending=0000 bit15=1 ack=1/1
000112 MAINPICLEANUP site=POSTACK performed=0 intsr13=0 intmr13=0
000113 TEARDOWN start control_written=1 irq_attempted=3 irq_completed=3 uncertain_writes=0 intsr13_seen=1 pi_policy=never_unmasked
000114 CTLW tag=RESTORE addr=01400000 semantic=90 rc=ok ticks=30 polls=8 dspcr=0804 t_after=3679950480 layout=gbi-replicated data=9090909090909090909090909090909090909090909090909090909090909090
000115 RAW TDCTL idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=90 sem_b1f=90 data=9090909090909090909090909090909090909090909090909090909090909090
000116 CONTROL restore semantic=90 rc=ok readback_rc=ok readback_vote=90 readback_b1f=90 ok=1
000117 RAW IRQSTOPPRE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8500 sem_gbi=8500 data=8585000085850000858504008585040085850000858504008585000085850400
000118 IRQSTOP pre rc=ok disc=8500 gbi=8500 stop_or=8aaa stop_value=8faa formula=read|stop_or comment=startup-disc-stop-shadow
000119 IRQW tag=STOP addr=01d00000 before=8500 write=8faa layout=gbi-u16-replicated rc=ok ticks=31 polls=8 dspcr=0804 t_after=3679954723 data=8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa
000120 RAW IRQSTOPPOST idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000121 IRQSTOP post rc=ok disc=8aaa gbi=8aaa write_ok=1 readback_ok=1 masks_readback=1 bit15_readback=1
000122 PI tag=CLEANUPCHK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000123 CLEANUP performed=0 intsr=00010000 intsr13=0 intmr13=0 reason=intsr13_clear
000124 IRQ restore rc=ok ok=1 old_handler=null
000125 PI tag=MASKCHK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000126 MASK final intmr=000001fa intmr13=0 orig_intmr13=0 ok=1
000127 ARINFO restore value=0043 rc=ok readback=0043 ok=1
000128 SNAP tag=FINAL ticks=3679959967 since_control=4359995 since_a1=4354582 since_a2=4333834 polls_before=0
000129 PI tag=FINAL intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000130 RAW FINAL idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=00 sem_b1f=00 data=0000000000000000000000000000000000000000000000000000000000000000
000131 RAW FINAL idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=9090 sem_gbi=9090 data=9090909090909090909090909090909090909090909090909090909090909090
000132 FINAL arinfo=0043 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 control=00 irq=9090 power_cycle_required=1
000133 INITIRQB end status=ok_delivery_observed reason=- restore=ok restore_reason=- power_cycle_required=1 errors=0 transport_ok=1
000134 WRITES control_written=1 irq_attempted=4 irq_completed=4 ctl_exp=1/1 a1=1/1 a2=1/1 stop=1/1 ctl_restore=1/1 uncertain=0 power_cycle_required=1 format=attempted/completed
000135 OBSERVED intsr13_seen=1 t_first_intsr13=3679890204 first_phase=A2 first_value=00012000 polls_at_first=709726 event=1 ended_early=1
000136 RESTORE control_restore_ok=1 irq_stop_write_ok=1 irq_stop_readback_ok=1 stop_masks_readback=1 stop_bit15_readback=1 pi_cleanup_performed=0 pi_cleanup_ok=-1 pi_cleanup_sticky=0 arinfo_restore_ok=1
000137 ACKS ack=1/1 ack_value=8500 irq_pending=0500 skipped=0 reason=- isr_pi_w1c=1 main_pi_w1c=0 site=- sticky=0 uncertain=0
000138 RESTOREB handler_installed=1 handler_restored=1 old_handler=null mask_ok=1 intmr_final=000001fa pi_sticky_final=0 unmasked=1 masked_again=1
000139 STATS transfers=51 timeouts=0 busy=0
# --- end --- dropped=0
```

Result: `ok_delivery_observed`, `restore=ok`, 51 transfers, 0 timeouts /
busy / errors, 140 lines, 0 dropped / truncated, every write attempted =
completed (`ctl_exp 1/1, a1 1/1, a2 1/1, ack 1/1, stop 1/1, ctl_restore
1/1, uncertain=0`), `power_cycle_required=1`. PRESENT 4/4 by all three
criteria (no byte-0 extra anywhere in this run). **003A part reproduced:**
PI `0x00010000` / `0x000001FA` at PRE, BASE, P0; BASE CONTROL `0x90`, IRQ
`0x8AAE` (`8A 8A AE AE ×8`, byte 0 clean); CONTROL `0x90 → 0x8C`; **A1**
`IRQ := 0x8AAE` read back `0x8AAA` at +22 ticks, +50 µs, +500 µs; **A2**
`IRQ := 0x0000` read back `0x0000` at +18 ticks, +50 µs, +500 µs, +5 ms,
+50 ms with CONTROL `0x8C` and INTSR bit 13 = 0; **EVENT** at t =
3679890204 = 4264071 ticks = 105.286 ms after A2 (003A: 105.273 ms): INTSR
`0x00012000` with INTMR `0x000001FA`, CONTROL `0x8C`, IRQ `0x0400`
(`04 04 04 00 ×8`); window ended early (`deadlines=4/6`). **CAUSE →
install:** `IRQ_Request(26)` returned NULL, record clean. **PREUNMASK**
907.6 µs after the EVENT: INTSR `0x00012000` in both samples, INTMR
`0x000001FA` in both, CONTROL `0x8C`, IRQ `0x0500` — the second source
(0x0100) had appeared between the EVENT and PREUNMASK; all preconditions
met. **UNMASK** `t_unmask=3679931504`, `__UnmaskIrq` returned at
`t_post=3679931761` (257 ticks) with INTSR already `0x00010000`, INTMR
`0x000001FA` and `fired=1`: the handler ran inside the call. **Handler
record:** `t_entry=3679931582` (78 ticks = 1.926 µs after t_unmask), INTSR
at entry `0x00012000`, INTMR at entry `0x000021FA` (bit 13 = 1, as
delivered); after `__MaskIrq` INTMR `0x000001FA`; INTSR before the W1C
`0x00012000`; after the one W1C `0x00010000`; second read 148 ticks
(3.654 µs) after the entry: INTSR `0x00010000`, INTMR `0x000001FA`;
`count=1 fired=1 reentry=0`. Main re-mask idempotent (`REMASKCHK`
`0x000001FA`). **PREACK** 7277 ticks (179.7 µs) after the handler entry:
INTSR `0x00010000` in both samples, INTMR `0x000001FA`, CONTROL `0x8C`, IRQ
`0x0500` (`05 05 05 00 ×8`) — the device sources still pending, PI bit 13
not re-asserted. **Device ACK** `IRQ := 0x0500 | 0x8000 = 0x8500`
(`85 00 ×16`, completed); **POSTACK** 25 µs after the write: IRQ `0x8000`
(`80 80 00 00 ×8`: both sources cleared, bit 15 read 1, odd bits 0), INTSR
`0x00010000` in both samples, INTMR `0x000001FA`; no main-loop W1C
(`MAINPICLEANUP performed=0`). **Teardown:** CONTROL `0x90` restored
(`90 ×32`); IRQSTOPPRE ≈143 µs after POSTACK read IRQ `0x8500`
(`85 85 00 00 / 85 85 04 00 …`: sources 0x0100 and 0x0400 set again, after
the CONTROL restore); stop `IRQ := 0x8FAA` read back `0x8AAA`
(`masks_readback=1 bit15_readback=1`); CLEANUPCHK INTSR `0x00010000`
(bit 13 clear: no cleanup needed, `reason=intsr13_clear`); handler restored
(`old_handler=null`, rc ok); MASKCHK INTMR `0x000001FA` (`mask_ok=1`);
AR_INFO `0x005B → 0x0043`; FINAL under code 0 `00` / `9090`, INTSR
`0x00010000`, INTMR `0x000001FA`. Evidence GBP-HW-035…041, GBP-PI-005,
ENV-IRQ-003, GBP-IRQ-008; analysis in DEVLOG 2026-09-15 "GBP-INIT-003B
executed".

**Logging defect found in this run (build initirqb-0001):** record
`000113 TEARDOWN start … pi_policy=never_unmasked` was printed by the
shared 003A teardown with its own fixed label, although this run had
unmasked PI HSP once (`000089 UNMASK … rc=ok`, `000138 RESTOREB …
unmasked=1 masked_again=1`) and the handler had been delivered
(`000094 HANDLER fired=1 count=1`). The label is not evidence of anything;
the primary records are. The log is preserved as written; later builds
print the caller's real policy (`pi_policy=unmasked_once` for a run that
unmasked, `never_unmasked` otherwise — `gbp_initirqa_teardown_opts.pi_policy`,
regression-tested), and the replay of the fixture through the corrected
probe reports `pi_policy=unmasked_once`. Also in this record:
`irq_attempted=3 irq_completed=3` counts A1, A2 and the ACK — the stop
word is written after it; the final `WRITES` record counts 4/4. Not an
inconsistency.

### GBP-INIT-004 — 2026-09-16 — completed, GBP attached (status=anomaly_source_not_cleared, restore=ok; one cycle serviced, NO re-arm written)

```text
Test ID     GBP-INIT-004
Build ID    initirq4-0001
Commit      741630b (clean; release audit of 2026-09-16, PHYSICAL CANDIDATE READY)
DOL         build/poc/gbp-init-irq-service-probe/gbp-init-irq-service-probe.dol
SHA-256     1da0d7b4f47200e914aba46510921b4a49a9bb8f01fd40940ebf50bd94ad010c
Log         logs/GBP-INIT-004_initirq4-0001.log, 19247 bytes,
            sha256 c9167224cb57f1c0df4858fbb147bbe0f1cd1f544b04a71a594786f4f2ee775b
            (original untouched; preserved copy captures/local/GBP-INIT-004_initirq4-0001.log;
            fixture captures/fixtures/hw-gamecube-gbp-2026-09-16-initirq4-0001.gbpreplay with the
            physical time base, the four IRQ-register writes (A1, A2, ACK, stop — no re-arm), the
            INTSR poll that saw bit 13, the interrupt path as it happened (install, generation
            published masked, unmask with the physical multi-cycle handler record, main re-mask,
            restore) and no main-loop PI W1C; 112 operations replay with 0 mismatches to the
            physical result)
Setup       GBP attached whole run, no Game Pak, Link Port empty, no PicoAdapterGB, BBA attached
            without Ethernet, 1 controller, 1 Memory Card, SD2SP2, Swiss; no interaction until
            X (save) / START (exit); console power-cycled afterwards (mandatory)
Bounds      A1/A2 samples as 003A; T_DELIVERY 100 ms per cycle; T_NEXT_CAUSE 500 ms after a re-arm
            (never reached); MAX_CYCLES 3, MAX_REARMS 2 (operational, not GBP properties)
```

Full log (verbatim):

```text
# OPENGBP-LOG v1
test_id=GBP-INIT-004
build_id=initirq4-0001
commit=741630b
libogc=libogc2 r2442.094b250 gecko=0 power_cycle_required=1
lines=152 dropped=0 truncated=0
# --- records ---
000000 IDENT test=GBP-INIT-004 app=gbp-init-irq-service-probe build=initirq4-0001 commit=741630b libogc=libogc2 r2442.094b250
000001 ENV bus_hz=162000000 tb_hz=40500000 dma_timeout_ms=200 t_max_ms=2000 t_delivery_ms=100 t_next_cause_ms=500 max_cycles=3 max_rearms=2 a2_obs_us=50,500,5000,50000,500000,2000000 csr=0804
000002 INITIRQ4 start max_cycles=3 max_rearms=2 t_delivery_ms=100 t_delivery_ticks=4050000 t_next_cause_ms=500 t_next_cause_ticks=20250000 ack_or=8000 src_mask=0555 av_mask=0500 odd_mask=0aaa bit15_mask=8000 high_mask=7000
000003 INITIRQ4 policy handler=installed_once control=written_once_never_per_cycle rearm=irq_zero_after_clean_boundary_only ack=read_or_8000_av_only w1c_budget=isr1_main1_rearmpost0_teardown1
000004 INITIRQA start exp_code=3 clear=10 set=0c idle_shape=1 req_masks=0aaa req_set=8000 req_clear=7000 ack_or=8000 stop_or=8aaa tb_hz=40500000
000005 INITIRQA window a1_obs_ticks=2025,20250 a2_obs_ticks=2025,20250,202500,2025000,20250000,81000000 n_a1=2 n_a2=6 t_max_ms=2000 poll=1 end_on_event=1
000006 ARINFO orig value=0043 size_code=3 exp_code=0 base=01000000
000007 ARINFO exp value=005b exp_code=3
000008 TESTW tag=DET idx=0 addr=01000000 pattern=c3 rc=ok ticks=33 polls=7 dspcr=0804
000009 TESTR tag=DET idx=0 addr=01000000 pattern=c3 expect=3c rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=3c data=3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c
000010 TESTW tag=DET idx=0 addr=01000000 pattern=3c rc=ok ticks=37 polls=10 dspcr=0804
000011 TESTR tag=DET idx=0 addr=01000000 pattern=3c expect=c3 rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=1 match_b1=1 match_vote=1 vote=c3 data=c7c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3
000012 TESTW tag=DET idx=0 addr=01000000 pattern=ff rc=ok ticks=30 polls=8 dspcr=0804
000013 TESTR tag=DET idx=0 addr=01000000 pattern=ff expect=00 rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=00 data=0000000000000000000000000000000000000000000000000000000000000000
000014 TESTW tag=DET idx=0 addr=01000000 pattern=00 rc=ok ticks=31 polls=8 dspcr=0804
000015 TESTR tag=DET idx=0 addr=01000000 pattern=00 expect=ff rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=ff data=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
000016 DET verdict=present run=4 transport_ok=4 vote_ok=4 b1_ok=4 all32_ok=3
000017 PI tag=PRE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000018 PRECOND intsr13=0 intmr13=0 irq_path_required=0 poll_intsr=1 write_intsr=1 ticks=1 ok=1 reason=-
000019 SNAP tag=BASE ticks=1048815890 since_control=0 since_a1=0 since_a2=0 polls_before=0
000020 PI tag=BASE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000021 RAW BASE idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=90 sem_b1f=90 data=9090909090909090909090909090909090909090909090909090909090909090
000022 RAW BASE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=8e8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000023 RAW BASE idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=0000000000000000000000000000000000000000000000000000000000000000
000024 CONTROL semantic orig=90 exp=8c method=gbi-majority-vote transform=(v&~10)|0c
000025 IRQSHAPE tag=BASE disc=8aae gbi=8aae agree=1 masks_ok=1 bit15_ok=1 high_ok=1 req_masks=0aaa req_set=8000 req_clear=7000 ok=1 reason=-
000026 CTLW tag=EXP addr=01400000 semantic=8c rc=ok ticks=31 polls=8 dspcr=0804 t_after=1048821530 layout=gbi-replicated data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000027 SNAP tag=P0 ticks=1048822503 since_control=973 since_a1=0 since_a2=0 polls_before=0
000028 PI tag=P0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000029 RAW P0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000030 RAW P0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=8e8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000031 RAW P0 idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=0000000000000000000000000000000000000000000000000000000000000000
000032 P0CHK intsr13=0 intmr13=0 control=8c irq=8aae ok=1 reason=-
000033 RAW A1PRE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=8e8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000034 IRQSHAPE tag=A1PRE disc=8aae gbi=8aae agree=1 masks_ok=1 bit15_ok=1 high_ok=1 req_masks=0aaa req_set=8000 req_clear=7000 ok=1 reason=-
000035 A1 before=8aae ack_or=8000 ack_value=8aae formula=read|ack_or
000036 IRQW tag=A1 addr=01d00000 before=8aae write=8aae layout=gbi-u16-replicated rc=ok ticks=31 polls=8 dspcr=0804 t_after=1048826924 data=8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae
000037 SNAP tag=A1-0 ticks=1048826942 since_control=5412 since_a1=18 since_a2=0 polls_before=0
000038 PI tag=A1-0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000039 RAW A1-0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000040 RAW A1-0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=8e8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000041 SNAP tag=A1-50US ticks=1048828950 since_control=7420 since_a1=2026 since_a2=0 polls_before=295
000042 PI tag=A1-50US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000043 RAW A1-50US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000044 RAW A1-50US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=8e8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000045 SNAP tag=A1-500US ticks=1048847178 since_control=25648 since_a1=20254 since_a2=0 polls_before=3415
000046 PI tag=A1-500US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000047 RAW A1-500US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000048 RAW A1-500US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=8e8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000049 WINDOW tag=A1 deadlines=2/2 polls=3415 poll_errors=0 intsr13_in_phase=0 no_timebase=0
000050 RAW A2PRE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=8e8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000051 PI tag=A2PRE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000052 A2CHK irq_rc=ok pi_ok=1 intsr13=0 intmr13=0 ok=1
000053 A2 before=8aaa value=0000 formula=zero
000054 IRQW tag=A2 addr=01d00000 before=8aaa write=0000 layout=gbi-u16-replicated rc=ok ticks=31 polls=8 dspcr=0804 t_after=1048847666 data=0000000000000000000000000000000000000000000000000000000000000000
000055 SNAP tag=A2-0 ticks=1048847684 since_control=26154 since_a1=20760 since_a2=18 polls_before=0
000056 PI tag=A2-0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000057 RAW A2-0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000058 RAW A2-0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000059 SNAP tag=A2-50US ticks=1048849694 since_control=28164 since_a1=22770 since_a2=2028 polls_before=303
000060 PI tag=A2-50US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000061 RAW A2-50US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000062 RAW A2-50US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000063 SNAP tag=A2-500US ticks=1048867918 since_control=46388 since_a1=40994 since_a2=20252 polls_before=3418
000064 PI tag=A2-500US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000065 RAW A2-500US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000066 RAW A2-500US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000067 SNAP tag=A2-5MS ticks=1049050168 since_control=228638 since_a1=223244 since_a2=202502 polls_before=35041
000068 PI tag=A2-5MS intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000069 RAW A2-5MS idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000070 RAW A2-5MS idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000071 SNAP tag=A2-50MS ticks=1050872669 since_control=2051139 since_a1=2045745 since_a2=2025003 polls_before=351612
000072 PI tag=A2-50MS intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000073 RAW A2-50MS idx=4 addr=01400000 rc=ok ticks=31 polls=8 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000074 RAW A2-50MS idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0000000000000000000000000000000000000000000000000000000000000000
000075 SNAP tag=EVENT ticks=1053111645 since_control=4290115 since_a1=4284721 since_a2=4263979 polls_before=740559 poll_intsr=00012000
000076 PI tag=EVENT intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000077 RAW EVENT idx=4 addr=01400000 rc=ok ticks=31 polls=8 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000078 RAW EVENT idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0400 sem_gbi=0400 data=0404040004040400040404000404040004040400040404000404040004040400
000079 WINDOW tag=A2 deadlines=4/6 polls=740559 poll_errors=0 ended_early=1 event=1 t_event=1053111645 intsr13_in_phase=1 t_end=1053111989 elapsed_ticks=4264323 elapsed_us=105291 no_timebase=0
000080 REGION log_count_start=33 log_count_end=33 formatted_inside=0
000081 CAUSE n=0 t_cause=1053111645 since_a2=4263979 intsr=00012000 intmr=000001fa intsr13=1 intmr13=0 control=8c irq=0400/0400 av=0400 unexpected=0000
000082 IRQ install rc=ok old_handler=null record_count=0 record_fired=0
000083 MULTI install expected_gen=0 entries_total=0 generation_errors=0 anomaly_count=1 anomaly_fired=0 slots=3
000084 CYCLE n=0 start t_cause=1053111645 cause_irq=0400 immediate=0
000085 PREPARE n=0 gen=0 rc=ok intmr13=0 expected_gen=0 entries_total=0 generation_errors=0 slot_count=0 slot_fired=0
000086 SNAP tag=PREUNMASK-0 ticks=1053151004 since_control=4329474 since_a1=4324080 since_a2=4303338 polls_before=0
000087 PI tag=PREUNMASK-0 intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000088 PI tag=PREUNMASK-0b intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000089 RAW PREUNMASK-0 idx=4 addr=01400000 rc=ok ticks=35 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000090 RAW PREUNMASK-0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0500 sem_gbi=0500 data=8d05040005050500050505000505050005050500050505000505050005050500
000091 PREUNMASK n=0 ok=1 reason=- intsr13=1,1 intmr13=0,0 control=8c irq=0500/0500 src=0500 odd=0000 bit15=0
000092 PREUNMASK4 n=0 av=0500 unexpected=0000 expected_gen=0 slot_clean=1 t_cause=1053111645 since_rearm=0 ok=1
000093 PI tag=UNMASKPRE-0 rc=ok intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000094 UNMASK n=0 t_unmask=1053156576 rc=ok t_post=1053156832 dt_post=256
000095 PI tag=UNMASKPOST-0 rc=ok intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 fired=1
000096 IRQ mask tag=MAIN n=0 rc=ok
000097 WAIT n=0 fired=1 timed_out=0 polls=1 wait_ticks=2101 wait_us=51 t_delivery_ms=100 t_delivery_ticks=4050000
000098 PI tag=REMASKCHK-0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000099 HANDLER n=0 fired=1 count=1 t_entry=1053156665 t_unmask=1053156576 latency_ticks=89 latency_us=2 reentry=0
000100 HANDLERPI n=0 intsr_at_entry=00012000 intmr_at_entry=000021fa intmr_after_mask=000001fa intsr_before_w1c=00012000 intsr_after_w1c=00010000 reentry_intsr=00000000 reentry_intmr=00000000
000101 HANDLERPI2 n=0 t_second=1053156807 dt_second=142 intsr_second=00010000 intmr_second=000001fa reentry_t=0
000102 DELIVERY n=0 fired=1 count=1 latency_ticks=89 latency_us=2 intsr13_entry=1 intmr13_entry=1 intmr13_after_mask=0 intsr13_before_w1c=1 intsr13_after_w1c=0 intsr13_second=0 intmr13_second=0 main_mask_ok=1 reentry=0
000103 HANDLER4 n=0 expected_gen=0 entries_total=1 generation_errors=0 anomaly_count=1 anomaly_fired=0 deliveries_before=0
000104 SNAP tag=PREACK-0 ticks=1053165161 since_control=4343631 since_a1=4338237 since_a2=4317495 polls_before=0
000105 PI tag=PREACK-0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000106 PI tag=PREACK-0b intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000107 RAW PREACK-0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000108 RAW PREACK-0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0500 sem_gbi=0500 data=8505040005050500050505000505050005050500050505000505050005050500
000109 PREACK n=0 intsr13=0,0 intmr13=0 control=8c irq=0500/0500 src_pending=0500
000110 ACK n=0 before=0500 ack_or=8000 ack_value=8500 formula=read|ack_or
000111 IRQW tag=ACK-0 addr=01d00000 before=0500 write=8500 layout=gbi-u16-replicated rc=ok ticks=31 polls=8 dspcr=0804 t_after=1053170192 data=8500850085008500850085008500850085008500850085008500850085008500
000112 SNAP tag=POSTACK-0 ticks=1053171245 since_control=4349715 since_a1=4344321 since_a2=4323579 polls_before=0
000113 PI tag=POSTACK-0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000114 PI tag=POSTACK-0b intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000115 RAW POSTACK-0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=ac8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000116 RAW POSTACK-0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8400 sem_gbi=8400 data=8484040084840400848404008484040084840400848404008484040084840400
000117 POSTACK n=0 intsr13=0,0 intmr13=0 control=8c irq=8400/8400 src_pending=0400 bit15=1 ack=1/1
000118 MAINPICLEANUP n=0 site=POSTACK performed=0 intsr13=0 intmr13=0
000119 TEARDOWN4 variant=S3_cycle_aborted cycles_started=1 cycles_completed=0 rearms=0/0 deliveries=1 acks=1 unmasks=1
000120 TEARDOWN start control_written=1 irq_attempted=3 irq_completed=3 uncertain_writes=0 intsr13_seen=1 pi_policy=unmasked_per_cycle
000121 CTLW tag=RESTORE addr=01400000 semantic=90 rc=ok ticks=31 polls=8 dspcr=0804 t_after=1053177991 layout=gbi-replicated data=9090909090909090909090909090909090909090909090909090909090909090
000122 RAW TDCTL idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=90 sem_b1f=90 data=9090909090909090909090909090909090909090909090909090909090909090
000123 CONTROL restore semantic=90 rc=ok readback_rc=ok readback_vote=90 readback_b1f=90 ok=1
000124 RAW IRQSTOPPRE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8400 sem_gbi=8400 data=8484040084840400848404008484040084840400848404008484040084840400
000125 IRQSTOP pre rc=ok disc=8400 gbi=8400 stop_or=8aaa stop_value=8eaa formula=read|stop_or comment=startup-disc-stop-shadow
000126 IRQW tag=STOP addr=01d00000 before=8400 write=8eaa layout=gbi-u16-replicated rc=ok ticks=30 polls=8 dspcr=0804 t_after=1053182290 data=8eaa8eaa8eaa8eaa8eaa8eaa8eaa8eaa8eaa8eaa8eaa8eaa8eaa8eaa8eaa8eaa
000127 RAW IRQSTOPPOST idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=8e8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000128 IRQSTOP post rc=ok disc=8aaa gbi=8aaa write_ok=1 readback_ok=1 masks_readback=1 bit15_readback=1
000129 PI tag=CLEANUPCHK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000130 CLEANUP performed=0 intsr=00010000 intsr13=0 intmr13=0 reason=intsr13_clear
000131 IRQ restore rc=ok ok=1 old_handler=null
000132 PI tag=MASKCHK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000133 MASK final intmr=000001fa intmr13=0 orig_intmr13=0 ok=1
000134 ARINFO restore value=0043 rc=ok readback=0043 ok=1
000135 SNAP tag=FINAL ticks=1053187586 since_control=4366056 since_a1=4360662 since_a2=4339920 polls_before=0
000136 PI tag=FINAL intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000137 RAW FINAL idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=00 sem_b1f=00 data=0000000000000000000000000000000000000000000000000000000000000000
000138 RAW FINAL idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=9090 sem_gbi=9090 data=9090909090909090909090909090909090909090909090909090909090909090
000139 FINAL arinfo=0043 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 control=00 irq=9090 power_cycle_required=1
000140 INITIRQ4 end status=anomaly_source_not_cleared reason=source_pending_after_ack_cycle_0 restore=ok restore_reason=- teardown=S3_cycle_aborted power_cycle_required=1 errors=0 transport_ok=1
000141 WRITES control_written=1 irq_attempted=4 irq_completed=4 ctl_exp=1/1 a1=1/1 a2=1/1 stop=1/1 ctl_restore=1/1 uncertain=0 power_cycle_required=1 format=attempted/completed
000142 OBSERVED intsr13_seen=1 t_first_intsr13=1053111645 first_phase=A2 first_value=00012000 polls_at_first=740559 event=1 ended_early=1
000143 RESTORE control_restore_ok=1 irq_stop_write_ok=1 irq_stop_readback_ok=1 stop_masks_readback=1 stop_bit15_readback=1 pi_cleanup_performed=0 pi_cleanup_ok=-1 pi_cleanup_sticky=0 arinfo_restore_ok=1
000144 CYCLES requested=3 completed=0 causes=1 deliveries=1 acks=1 rearms=0 next_causes=0 reentry=0 unexpected=0 timeouts=0 isr_w1c=1 main_w1c=0 teardown_w1c=0
000145 CYCLE n=0 end cause=1 t_cause=1053111645 immediate=0 prepared=1 preunmask=1/- unmasked=1 fired=1 count=1 latency_ticks=89 delivered=1
000146 CYCLE n=0 ack=1/1 ack_value=8500 pending=0500 skipped=0 reason=- postack_irq=8400 main_w1c=0 sticky=0 unexpected=0000 site=- boundary=0
000147 CYCLE n=0 rearm=0/0 t_rearm=0 rearmpost=- rearmpost_ok=0 rearmpost_irq=0000 next_cause_polls=0 next_cause_timed_out=0
000148 TIMING n=0 cause_to_isr=45020/1111us isr_second=142 isr_to_preack=8496 ack_to_postack=1053 postack_to_rearm=0 rearm_to_next_cause=0/0us
000149 MULTI expected_gen=0 entries_total=1 generation_errors=0 anomaly_count=1 anomaly_fired=0 unmasks=1
000150 RESTORE4 handler_installed=1 handler_restored=1 old_handler=null mask_ok=1 intmr_final=000001fa pi_sticky_final=0 control_ok=1 uncertain=0
000151 STATS transfers=51 timeouts=0 busy=0
# --- end --- dropped=0
```

Result: `anomaly_source_not_cleared`, reason `source_pending_after_ack_cycle_0`,
`restore=ok`, teardown `S3_cycle_aborted`; 51 transfers, 0 timeouts / busy /
errors, 152 lines, 0 dropped / truncated, every write attempted = completed
(`ctl_exp 1/1, a1 1/1, a2 1/1, ack 1/1, stop 1/1, ctl_restore 1/1,
uncertain=0`), `power_cycle_required=1`. Counters: `requested=3 completed=0
causes=1 deliveries=1 acks=1 rearms=0 next_causes=0 reentry=0 unexpected=0
timeouts=0 isr_w1c=1 main_w1c=0 teardown_w1c=0`. **`completed=0` is
correct:** a cycle counts only after its clean boundary (ACK → POSTACK with
the acknowledged sources gone → PI clean); one delivery and one ACK did
happen, the boundary did not. **This is not a technical failure of the
experiment: the conservative clean boundary designed for 004 stopped the run
before the first re-arm.** PRESENT 4/4 by all three criteria with one
byte-0 extra in the handshake (`C7 C3…`, `all32_ok=3`).

**003A part reproduced (third run):** PI `0x00010000` / `0x000001FA` at PRE,
BASE, P0; BASE CONTROL `0x90`, IRQ `0x8AAE` (`8E 8A AE AE …`: byte-0 extra
0x04); CONTROL `0x90 → 0x8C` (every 0x8C read `AC 8C 8C …`: byte-0 extra
0x20); **A1** `IRQ := 0x8AAE` read back `0x8AAA` at +18 ticks, +50 µs,
+500 µs; **A2** `IRQ := 0x0000` (`t_after=1048847666`) read back `0x0000` at
+18 ticks, +50 µs, +500 µs, +5 ms, +50 ms with CONTROL `0x8C` and INTSR bit
13 = 0; **EVENT** at t = 1053111645 = **4263979 ticks = 105.283 ms after A2**
(003A 105.273 ms, 003B 105.286 ms): INTSR `0x00012000`, INTMR `0x000001FA`,
CONTROL `0x8C`, IRQ `0x0400` (`04 04 04 00 ×8`), window ended early
(`deadlines=4/6`, 740559 polls). One more point of the initial cadence
(U-GBP-014).

**Cycle 0 — install, generation, PREUNMASK:** `IRQ_Request(26,
hsp_backend_oneshot_isr_multi)` returned NULL, slot 0 clean, `MULTI install
expected_gen=0 entries_total=0 generation_errors=0 anomaly_count=1`;
`PREPARE n=0 gen=0` published with INTMR bit 13 = 0 (EVENT evidence).
**PREUNMASK-0** 971.8 µs after the EVENT: INTSR `0x00012000` in both
samples, INTMR `0x000001FA` in both, CONTROL `0x8C`, IRQ `0x0500` (`8D 05 04
00 / 05 05 05 00 ×7`: byte-0 extra 0x88, group-0 offset 2 = `04`) — the
second source 0x0100 had appeared, as in 003B; every precondition met.

**Delivery:** `t_unmask=1053156576`, `__UnmaskIrq` returned at
`t_post=1053156832` (256 ticks) with INTSR already `0x00010000`, INTMR
`0x000001FA`, `fired=1`: the handler ran inside the call (ENV-IRQ-003
again). **Multi-cycle handler record, slot 0:** `t_entry=1053156665` (**89
ticks = 2.198 µs** after t_unmask; 003B: 78), INTSR at entry `0x00012000`,
INTMR at entry `0x000021FA` (bit 13 = 1, as delivered); after `__MaskIrq`
INTMR `0x000001FA`; INTSR before the W1C `0x00012000`; after the one W1C
`0x00010000`; second read **142 ticks (3.506 µs)** after the entry: INTSR
`0x00010000`, INTMR `0x000001FA`; `count=1 fired=1 reentry=0`; `HANDLER4
expected_gen=0 entries_total=1 generation_errors=0 anomaly_count=1
anomaly_fired=0`. Main re-mask idempotent (`REMASKCHK-0 0x000001FA`,
`main_mask_ok=1`). This is a physical confirmation of the 003B mechanism
(GBP-PI-005) through the multi-cycle handler body and its generation
bookkeeping — an additional observation, not a new independent discovery.

**PREACK-0** 8496 ticks (209.8 µs) after the entry: INTSR `0x00010000` in
both samples, INTMR `0x000001FA`, CONTROL `0x8C`, IRQ `0x0500` (`85 05 04 00 /
05 05 05 00 ×7`) — both AV sources still pending on the device, no PI
re-assert (second observation of GBP-HW-039), no incidental acknowledge by
the handler (the ISR touches only the PI).

**ACK-0** `IRQ := 0x0500 | 0x8000 = 0x8500` (`85 00 ×16`), rc ok,
attempted 1 / completed 1, `t_after=1053170192`. Not a transport failure in
any sense: the write completed and its effect is visible in the read-back.

**POSTACK-0 — the central new observation:** snapshot at 1053171245 =
**1053 ticks = 26.000 µs after the ACK**: IRQ **`0x8400`** (`84 84 04 00 ×8`,
Disc == GBI), INTSR `0x00010000` in **both** samples, INTMR `0x000001FA`,
CONTROL `0x8C`. At that instant: bit 15 = 1, odd bits 0, source 0x0400
present, source 0x0100 absent, PI HSP bit 13 clear, CONTROL still in the
running state. The clean boundary requires `irq & 0x0555 == 0`; it read
0x0400 → `anomaly_source_not_cleared` → no second ACK, no re-arm, teardown
S3 with the CPU masked. **Restricted FACT (GBP-HW-045):** a source 0x0400 can
be present in the IRQ register with CONTROL 0x8C and bit 15 = 1 while PI
INTSR bit 13 stays 0. **What the evidence does not distinguish:** (A) the
ACK's W1C of bit 10 did not clear 0x0400 at all (while it did clear 0x0100),
from (B) 0x0400 was cleared and re-asserted within the 26 µs before the
sample. "ACK failed" is **not** a conclusion of this run (U-GBP-028).

**Comparison with 003B:** same PREACK `0x0500`, same ACK `0x8500`; 003B read
`0x8000` 25.1 µs after the ACK (both sources cleared) and `0x8500` at
IRQSTOPPRE ≈143 µs after POSTACK, **after** CONTROL had been restored to
0x90; 004 read `0x8400` 26.0 µs after the ACK **with CONTROL still 0x8C**.
The CONTROL change 0x8C → 0x90 is therefore not a necessary condition for
the reappearance of a source after the ACK. Two runs do not establish a
period or a mechanism; the 0x0100 source, present at 003B's IRQSTOPPRE, was
absent in 004 at +26 µs and at IRQSTOPPRE (≈+195 µs).

**Bit 15 (U-GBP-007, refined with caution):** the state "0x0400 present,
bit 15 = 1, odd bits 0, CONTROL 0x8C, PI bit 13 = 0" was observed at +26 µs
and persisted (IRQSTOPPRE `0x8400` after the CONTROL restore); no PI cause
was captured from the handler's W1C (t ≈ 1053156700) to FINAL (t =
1053187586, ≥ 0.76 ms) although the main loop never wrote INTSR again
(`main_w1c=0 teardown_w1c=0`, bit 13 is latched: FACT). Hence the model
"a present source implies an immediately latched HSP cause" is **rejected in
the observed conditions**; compatible hypotheses, none promoted: bit 15
holds / gates the external request; source status and request generation
have separate logic; the re-request condition (a new event, or the drain of
the block) had not occurred.

**Teardown (S3_cycle_aborted):** CONTROL `0x8C → 0x90` (`t_after=1053177991`,
+166.6 µs after POSTACK, read back `90 ×32`); IRQSTOPPRE `0x8400`
(unchanged); stop `IRQ := 0x8400 | 0x8AAA = 0x8EAA` (`8E AA ×16`) read back
`0x8AAA` (`masks_readback=1 bit15_readback=1`) — a third physically
validated stop combination (0x8FAA ×2 before); CLEANUPCHK INTSR `0x00010000`
(no cleanup needed); handler restored (`old_handler=null`, rc ok); MASKCHK
INTMR `0x000001FA`; AR_INFO `0x005B → 0x0043`; FINAL under code 0 `00` /
`9090`, INTSR `0x00010000`, INTMR `0x000001FA`. `restore=ok`.

**What this run did NOT test — explicit:** `rearm_attempted=0`,
`rearm_completed=0`, `next_causes=0`. No `IRQ := 0` was written after the
ACK; there is no physical evidence in this run about the re-arm, about a
next HSP cause after a re-arm or about a second delivery. The multi-cycle
continuation exists only in the host mock; **U-GBP-027 stays open.** The
next experiment is GBP-AV-SERVICE-001 (drained service → re-arm → next
cause, the Phase 4 entry), designed below (DEVLOG 2026-09-16 "next step
after GBP-INIT-004 decided"); GBP-INIT-004B (pending-source re-arm,
designed the same day) is kept below as an optional experiment, not
scheduled.

**Byte 0 / offset 2 (U-GBP-021 / U-GBP-025):** extras in this run — TEST
`C7` (pattern 3C read, `all32_ok=3`), CONTROL `AC` in all thirteen 0x8C reads,
IRQ `8E` in every 0x8AAE / 0x8AAA read (BASE, P0, A1PRE, A1-0 … A2PRE,
IRQSTOPPOST), `8D` at PREUNMASK-0 (0x0500) and `85` at PREACK-0 (0x0500);
none at EVENT (0x0400), POSTACK / IRQSTOPPRE (0x8400), FINAL (0x9090),
CONTROL 0x90 / 0x00, TEST 3C / 00 / FF. Disc and GBI readings agreed in every
read, the vote equalled byte 0x1F, detection PRESENT: byte 0 never fed a
decision. The offset-2 pattern held everywhere except group 0 of the two
0x0500 reads (`04` where it predicts `05`; 003B: `00`). That 003B had no
extra at all does not change the conclusion. Evidence GBP-HW-042…047,
GBP-IRQ-009; analysis in DEVLOG 2026-09-16 "GBP-INIT-004 executed".

### GBP-AV-SERVICE-001 — 2026-09-16 — completed, GBP attached (status=ok_service_rearm_cause_observed, restore=ok; first drained service, first re-arm, next cause observed and left latched)

```text
Test ID     GBP-AV-SERVICE-001
Build ID    avsvc-0001
Commit      d3a6d23 (clean; full d3a6d237fbec43e512ac85da2bbe93a903ff0f0c; release audit of
            2026-09-16, PHYSICAL CANDIDATE READY; build materialized the same day)
DOL         build/poc/gbp-av-service-probe/gbp-av-service-probe.dol
SHA-256     d9e6dccd6f6ac2a729cc1be904214dbaf6f0bd88ee2929244b185a5ba39556ff
Log         logs/GBP-AV-SERVICE-001_avsvc-0001.log, 23154 bytes,
            sha256 d0324b6d12f02984a0d748f896f1c16f724d69c0e3022bef5460f8ed32a03713
            (original untouched; preserved copy captures/local/GBP-AV-SERVICE-001_avsvc-0001.log;
            fixture captures/fixtures/hw-gamecube-gbp-2026-09-16-avsvc-0001.gbpreplay with the
            physical time base, the five IRQ-register writes (A1, A2, ACK, RE-ARM, stop), the INTSR
            poll that saw bit 13, the interrupt path as it happened (install, unmask with the
            physical one-shot record, main re-mask, restore), the two whole-block reads as "B"
            lines with their CRC-32, one teardown PI W1C and every raw block verbatim; 132
            operations replay with 0 mismatches / 0 exhausted / 0 blocks missing / 0 CRC
            mismatches to the physical result)
Sidecar     logs/GBP-AV-SERVICE-001_avsvc-0001-blocks.bin, 8204 bytes,
            sha256 1c17a2d77fa60b4446863032ced62cc3d2390625de2a42b120a195eb074edc1e
            (format version 2: magic OGBPBLK1, 256-byte header, AUDIO 0x1000 + VIDEO 0xF00, footer
            OGBPEND1; identities whole — Test ID GBP-AV-SERVICE-001, Build ID avsvc-0001, app
            gbp-av-service-probe, commit d3a6d23; header CRC-32 6174E52D, AUDIO FEC5E4E7, VIDEO
            FE45FF08, total 18E966CF, all four recomputed and equal; preserved copy
            captures/local/GBP-AV-SERVICE-001_avsvc-0001-blocks.bin; fixture copy
            captures/fixtures/hw-gamecube-gbp-2026-09-16-avsvc-0001-blocks.bin, byte-identical)
Setup       GBP attached whole run, no Game Pak; the bench of GBP-INIT-004 per the procedure (the
            log records no Link Port / BBA state), 1 controller, 1 Memory Card, SD2SP2, Swiss; no
            interaction until X (log, then sidecar) / START (exit); console power-cycled
            afterwards (mandatory)
Bounds      A1/A2 samples as 003A; T_DELIVERY 100 ms; T_DMA 200 ms per block; T_NEXT_CAUSE 500 ms
            after the re-arm (not consumed: the next cause was already latched at the first read)
            — operational, not GBP properties
```

Full log (verbatim):

```text
# OPENGBP-LOG v1
test_id=GBP-AV-SERVICE-001
build_id=avsvc-0001
commit=d3a6d23
libogc=libogc2 r2442.094b250 gecko=0 power_cycle_required=1 sidecar=GBP-AV-SERVICE-001_avsvc-0001-blocks.bin
lines=182 dropped=0 truncated=0
# --- records ---
000000 IDENT test=GBP-AV-SERVICE-001 app=gbp-av-service-probe build=avsvc-0001 commit=d3a6d23 libogc=libogc2 r2442.094b250
000001 ENV bus_hz=162000000 tb_hz=40500000 dma_timeout_ms=200 t_max_ms=2000 t_delivery_ms=100 t_next_cause_ms=500 a2_obs_us=50,500,5000,50000,500000,2000000 csr=0804 audio_buf=00069320 video_buf=00068420
000002 AVSVC start t_delivery_ms=100 t_delivery_ticks=4050000 t_next_cause_ms=500 t_next_cause_ticks=20250000 ack_or=8000 src_mask=0555 av_mask=0500 odd_mask=0aaa bit15_mask=8000 high_mask=7000
000003 AVSVC blocks audio_idx=8 audio_len=1000 audio_src=0400 video_idx=1 video_len=0f00 video_src=0100 order=audio_then_video prefill=00 bulk_read=1
000004 AVSVC policy handler=003b_ext_installed_once deliveries=1 snapshot=PRESVC_authoritative drain=selected_by_snapshot ack=pending|8000_from_PRESVC
000005 AVSVC policy2 postack=no_source_requirement rearm=irq_zero_after_pi_clean next_cause=observed_never_delivered w1c_budget=isr1_main1_nextcause0_teardown1
000006 INITIRQA start exp_code=3 clear=10 set=0c idle_shape=1 req_masks=0aaa req_set=8000 req_clear=7000 ack_or=8000 stop_or=8aaa tb_hz=40500000
000007 INITIRQA window a1_obs_ticks=2025,20250 a2_obs_ticks=2025,20250,202500,2025000,20250000,81000000 n_a1=2 n_a2=6 t_max_ms=2000 poll=1 end_on_event=1
000008 ARINFO orig value=0043 size_code=3 exp_code=0 base=01000000
000009 ARINFO exp value=005b exp_code=3
000010 TESTW tag=DET idx=0 addr=01000000 pattern=c3 rc=ok ticks=33 polls=7 dspcr=0804
000011 TESTR tag=DET idx=0 addr=01000000 pattern=c3 expect=3c rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=1 match_b1=1 match_vote=1 vote=3c data=7f3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c
000012 TESTW tag=DET idx=0 addr=01000000 pattern=3c rc=ok ticks=31 polls=8 dspcr=0804
000013 TESTR tag=DET idx=0 addr=01000000 pattern=3c expect=c3 rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=1 match_b1=1 match_vote=1 vote=c3 data=d3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3
000014 TESTW tag=DET idx=0 addr=01000000 pattern=ff rc=ok ticks=30 polls=8 dspcr=0804
000015 TESTR tag=DET idx=0 addr=01000000 pattern=ff expect=00 rc=ok ticks=34 polls=9 dspcr=0804 match_all=0 match_1f=1 match_b1=1 match_vote=1 vote=00 data=1100000000000000000000000000000000000000000000000000000000000000
000016 TESTW tag=DET idx=0 addr=01000000 pattern=00 rc=ok ticks=30 polls=8 dspcr=0804
000017 TESTR tag=DET idx=0 addr=01000000 pattern=00 expect=ff rc=ok ticks=34 polls=9 dspcr=0804 match_all=1 match_1f=1 match_b1=1 match_vote=1 vote=ff data=ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
000018 DET verdict=present run=4 transport_ok=4 vote_ok=4 b1_ok=4 all32_ok=1
000019 PI tag=PRE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000020 PRECOND intsr13=0 intmr13=0 irq_path_required=0 poll_intsr=1 write_intsr=1 ticks=1 ok=1 reason=-
000021 SNAP tag=BASE ticks=3387033147 since_control=0 since_a1=0 since_a2=0 polls_before=0
000022 PI tag=BASE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000023 RAW BASE idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=90 sem_b1f=90 data=9390909090909090909090909090909090909090909090909090909090909090
000024 RAW BASE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=9b8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000025 RAW BASE idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=0100000000000000000000000000000000000000000000000000000000000000
000026 CONTROL semantic orig=90 exp=8c method=gbi-majority-vote transform=(v&~10)|0c
000027 IRQSHAPE tag=BASE disc=8aae gbi=8aae agree=1 masks_ok=1 bit15_ok=1 high_ok=1 req_masks=0aaa req_set=8000 req_clear=7000 ok=1 reason=-
000028 CTLW tag=EXP addr=01400000 semantic=8c rc=ok ticks=31 polls=8 dspcr=0804 t_after=3387038809 layout=gbi-replicated data=8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000029 SNAP tag=P0 ticks=3387039780 since_control=971 since_a1=0 since_a2=0 polls_before=0
000030 PI tag=P0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000031 RAW P0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000032 RAW P0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=9b8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000033 RAW P0 idx=0 addr=01000000 rc=ok ticks=34 polls=9 dspcr=0804 data=0100000000000000000000000000000000000000000000000000000000000000
000034 P0CHK intsr13=0 intmr13=0 control=8c irq=8aae ok=1 reason=-
000035 RAW A1PRE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aae sem_gbi=8aae data=9b8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae8a8aaeae
000036 IRQSHAPE tag=A1PRE disc=8aae gbi=8aae agree=1 masks_ok=1 bit15_ok=1 high_ok=1 req_masks=0aaa req_set=8000 req_clear=7000 ok=1 reason=-
000037 A1 before=8aae ack_or=8000 ack_value=8aae formula=read|ack_or
000038 IRQW tag=A1 addr=01d00000 before=8aae write=8aae layout=gbi-u16-replicated rc=ok ticks=31 polls=8 dspcr=0804 t_after=3387044205 data=8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae8aae
000039 SNAP tag=A1-0 ticks=3387044227 since_control=5418 since_a1=22 since_a2=0 polls_before=0
000040 PI tag=A1-0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000041 RAW A1-0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000042 RAW A1-0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=9b8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000043 SNAP tag=A1-50US ticks=3387046235 since_control=7426 since_a1=2030 since_a2=0 polls_before=295
000044 PI tag=A1-50US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000045 RAW A1-50US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000046 RAW A1-50US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=9b8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000047 SNAP tag=A1-500US ticks=3387064455 since_control=25646 since_a1=20250 since_a2=0 polls_before=3413
000048 PI tag=A1-500US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000049 RAW A1-500US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000050 RAW A1-500US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=9b8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000051 WINDOW tag=A1 deadlines=2/2 polls=3413 poll_errors=0 intsr13_in_phase=0 no_timebase=0
000052 RAW A2PRE idx=d addr=01d00000 rc=ok ticks=41 polls=11 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=9b8abbaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000053 PI tag=A2PRE intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000054 A2CHK irq_rc=ok pi_ok=1 intsr13=0 intmr13=0 ok=1
000055 A2 before=8aaa value=0000 formula=zero
000056 IRQW tag=A2 addr=01d00000 before=8aaa write=0000 layout=gbi-u16-replicated rc=ok ticks=30 polls=8 dspcr=0804 t_after=3387064949 data=0000000000000000000000000000000000000000000000000000000000000000
000057 SNAP tag=A2-0 ticks=3387064970 since_control=26161 since_a1=20765 since_a2=21 polls_before=0
000058 PI tag=A2-0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000059 RAW A2-0 idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000060 RAW A2-0 idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0100000000000000000000000000000000000000000000000000000000000000
000061 SNAP tag=A2-50US ticks=3387066975 since_control=28166 since_a1=22770 since_a2=2026 polls_before=303
000062 PI tag=A2-50US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000063 RAW A2-50US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000064 RAW A2-50US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0100000000000000000000000000000000000000000000000000000000000000
000065 SNAP tag=A2-500US ticks=3387085200 since_control=46391 since_a1=40995 since_a2=20251 polls_before=3418
000066 PI tag=A2-500US intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000067 RAW A2-500US idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000068 RAW A2-500US idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0100000000000000000000000000000000000000000000000000000000000000
000069 SNAP tag=A2-5MS ticks=3387267450 since_control=228641 since_a1=223245 since_a2=202501 polls_before=35041
000070 PI tag=A2-5MS intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000071 RAW A2-5MS idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000072 RAW A2-5MS idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0100000000000000000000000000000000000000000000000000000000000000
000073 SNAP tag=A2-50MS ticks=3389089953 since_control=2051144 since_a1=2045748 since_a2=2025004 polls_before=351607
000074 PI tag=A2-50MS intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000075 RAW A2-50MS idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000076 RAW A2-50MS idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0000 sem_gbi=0000 data=0100000000000000000000000000000000000000000000000000000000000000
000077 SNAP tag=EVENT ticks=3391329164 since_control=4290355 since_a1=4284959 since_a2=4264215 polls_before=740594 poll_intsr=00012000
000078 PI tag=EVENT intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000079 RAW EVENT idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000080 RAW EVENT idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0400 sem_gbi=0400 data=1504000004040400040404000404040004040400040404000404040004040400
000081 WINDOW tag=A2 deadlines=4/6 polls=740594 poll_errors=0 ended_early=1 event=1 t_event=3391329164 intsr13_in_phase=1 t_end=3391329470 elapsed_ticks=4264521 elapsed_us=105296 no_timebase=0
000082 REGION log_count_start=35 log_count_end=35 formatted_inside=0
000083 CAUSE t_event=3391329164 since_a2=4264215 intsr=00012000 intmr=000001fa intsr13=1 intmr13=0 control=8c irq=0400/0400 av=0400 unexpected=0000
000084 IRQ install rc=ok old_handler=null record_count=0 record_fired=0
000085 SNAP tag=PREUNMASK ticks=3391366386 since_control=4327577 since_a1=4322181 since_a2=4301437 polls_before=0
000086 PI tag=PREUNMASK intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000087 PI tag=PREUNMASKb intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000088 RAW PREUNMASK idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000089 RAW PREUNMASK idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0500 sem_gbi=0500 data=1705010005050500050505000505050005050500050505000505050005050500
000090 PREUNMASK ok=1 reason=- intsr13=1,1 intmr13=0,0 control=8c irq=0500/0500 src=0500 odd=0000 bit15=0
000091 PREUNMASKAV av=0500 unexpected=0000 t_cause=3391329164 ok=1
000092 PI tag=UNMASKPRE rc=ok intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000093 UNMASK t_unmask=3391371622 rc=ok t_post=3391371862 dt_post=240
000094 PI tag=UNMASKPOST rc=ok intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 fired=1
000095 IRQ mask tag=MAIN rc=ok
000096 WAIT fired=1 timed_out=0 polls=1 wait_ticks=2060 wait_us=50 t_delivery_ms=100 t_delivery_ticks=4050000
000097 PI tag=REMASKCHK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000098 HANDLER fired=1 count=1 t_entry=3391371694 t_unmask=3391371622 latency_ticks=72 latency_us=1 reentry=0
000099 HANDLERPI intsr_at_entry=00012000 intmr_at_entry=000021fa intmr_after_mask=000001fa intsr_before_w1c=00012000 intsr_after_w1c=00010000 reentry_intsr=00000000 reentry_intmr=00000000
000100 HANDLERPI2 t_second=3391371841 dt_second=147 intsr_second=00010000 intmr_second=000001fa reentry_t=0
000101 DELIVERY fired=1 count=1 latency_ticks=72 latency_us=1 intsr13_entry=1 intmr13_entry=1 intmr13_after_mask=0 intsr13_before_w1c=1 intsr13_after_w1c=0 intsr13_second=0 intmr13_second=0 main_mask_ok=1 reentry=0
000102 SNAP tag=PRESVC ticks=3391379306 since_control=4340497 since_a1=4335101 since_a2=4314357 polls_before=0
000103 PI tag=PRESVC intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000104 PI tag=PRESVCb intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000105 RAW PRESVC idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000106 RAW PRESVC idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0500 sem_gbi=0500 data=1705010005050500050505000505050005050500050505000505050005050500
000107 PRESVC t=3391379306 intsr13=0,0 intmr13=0,0 control=8c irq=0500/0500 src=0500 av=0500 unexpected=0000 odd=0000 bit15=0 high=0000
000108 SVC start pending=0500 drain=0500 audio=1 video=1 order=audio_then_video ack_value=8500 ack_source=PRESVC t=3391379306
000109 AUDIOREAD idx=8 addr=01800000 len=1000 selected=1 attempted=1 completed=1 rc=ok t_start=3391385098 t_end=3391387790 dt=2692 wait_ticks=2475 polls=760 csr_before=0804 csr_after=0804
000110 VIDEOREAD idx=1 addr=01100000 len=0f00 selected=1 attempted=1 completed=1 rc=ok t_start=3391387818 t_end=3391390303 dt=2485 wait_ticks=2319 polls=712 csr_before=0804 csr_after=0804
000111 SVCEND drain=0500 selected=2 attempted=2 completed=2 ok=1 t_end=3391390303 dt_service=10997 audio_rc=ok video_rc=ok
000112 SNAP tag=POSTDRAIN ticks=3391394064 since_control=4355255 since_a1=4349859 since_a2=4329115 polls_before=0
000113 PI tag=POSTDRAIN intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000114 PI tag=POSTDRAINb intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000115 RAW POSTDRAIN idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000116 RAW POSTDRAIN idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0500 sem_gbi=0500 data=1705010005050500050505000505050005050500050504000505050005050500
000117 POSTDRAIN t=3391394064 intsr13=0,0 intmr13=0,0 control=8c irq=0500/0500 src=0500 av=0500 unexpected=0000 odd=0000 bit15=0 high=0000
000118 POSTDRAIN observation_only=1 relatch=0 av_after_drain=0500 pending_kept=0500
000119 ACK before=0500 ack_or=8000 ack_value=8500 formula=read|ack_or
000120 IRQW tag=ACK addr=01d00000 before=0500 write=8500 layout=gbi-u16-replicated rc=ok ticks=30 polls=8 dspcr=0804 t_after=3391399980 data=8500850085008500850085008500850085008500850085008500850085008500
000121 SNAP tag=POSTACK ticks=3391401028 since_control=4362219 since_a1=4356823 since_a2=4336079 polls_before=0
000122 PI tag=POSTACK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000123 PI tag=POSTACKb intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000124 RAW POSTACK idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000125 RAW POSTACK idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8000 sem_gbi=8000 data=8180000080800000808000008080000080800000808000008080000080800000
000126 POSTACK intsr13=0,0 intmr13=0 control=8c irq=8000/8000 src_pending=0000 bit15=1 ack=1/1
000127 MAINPICLEANUP site=POSTACK performed=0 intsr13=0 intmr13=0
000128 POSTACKAV t=3391401028 intsr13=0,0 intmr13=0,0 control=8c irq=8000/8000 src=0000 av=0000 unexpected=0000 odd=0000 bit15=1 high=0000
000129 POSTACKAV boundary=clean source_after_ack=0000 relatch=0 main_w1c=0 requirement=none
000130 PICLEAN intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 main_w1c=0 sticky=0 ok=1
000131 REARM t_rearm=3391408218 before=8000 value=0000 layout=gbi-u16-replicated after=drain_ack_pi_clean
000132 IRQW tag=REARM addr=01d00000 before=8000 write=0000 layout=gbi-u16-replicated rc=ok ticks=30 polls=8 dspcr=0804 t_after=3391408974 data=0000000000000000000000000000000000000000000000000000000000000000
000133 SNAP tag=REARMPOST ticks=3391409996 since_control=4371187 since_a1=4365791 since_a2=4345047 polls_before=0
000134 PI tag=REARMPOST intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000135 PI tag=REARMPOSTb intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000136 RAW REARMPOST idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=8c sem_b1f=8c data=9f8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c8c
000137 RAW REARMPOST idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0400 sem_gbi=0400 data=1504000004040400040404000404040004040400040404000404040004040400
000138 REARMPOST t=3391409996 since_rearm=1778 intsr13=1,1 intmr13=0,0 control=8c irq=0400/0400 src=0400 av=0400 unexpected=0000 odd=0000 bit15=0 high=0000 outcome=B_latched ok=1
000139 NEXTCAUSE found=1 immediate=1 t_next_cause=3391409996 since_rearm=1778 intsr=00012000 control=8c irq=0400/0400 av=0400 unexpected=0000 polls=0 delivered=0
000140 TEARDOWNAV variant=S4B_next_cause_latched deliveries=1 drained=2/2 acks=1 rearms=1/1 next_cause=1 unmasks=1
000141 TEARDOWN start control_written=1 irq_attempted=4 irq_completed=4 uncertain_writes=0 intsr13_seen=1 pi_policy=unmasked_once
000142 CTLW tag=RESTORE addr=01400000 semantic=90 rc=ok ticks=31 polls=8 dspcr=0804 t_after=3391417891 layout=gbi-replicated data=9090909090909090909090909090909090909090909090909090909090909090
000143 RAW TDCTL idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=90 sem_b1f=90 data=9190909090909090909090909090909090909090909090909090909090909090
000144 CONTROL restore semantic=90 rc=ok readback_rc=ok readback_vote=90 readback_b1f=90 ok=1
000145 RAW IRQSTOPPRE idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=0500 sem_gbi=0500 data=1705010005050500050505000505050005050500050505000505050005050500
000146 IRQSTOP pre rc=ok disc=0500 gbi=0500 stop_or=8aaa stop_value=8faa formula=read|stop_or comment=startup-disc-stop-shadow
000147 IRQW tag=STOP addr=01d00000 before=0500 write=8faa layout=gbi-u16-replicated rc=ok ticks=31 polls=8 dspcr=0804 t_after=3391422199 data=8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa8faa
000148 RAW IRQSTOPPOST idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=8aaa sem_gbi=8aaa data=9b8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa8a8aaaaa
000149 IRQSTOP post rc=ok disc=8aaa gbi=8aaa write_ok=1 readback_ok=1 masks_readback=1 bit15_readback=1
000150 PI tag=CLEANUPCHK intsr=00012000 intmr=000001fa intsr13=1 intmr13=0
000151 PI tag=CLEANUP intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000152 CLEANUP performed=1 value=00002000 rc=ok intsr_before=00012000 intsr_after=00010000 intsr13_after=0 sticky=0 ok=1
000153 IRQ restore rc=ok ok=1 old_handler=null
000154 PI tag=MASKCHK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000155 MASK final intmr=000001fa intmr13=0 orig_intmr13=0 ok=1
000156 ARINFO restore value=0043 rc=ok readback=0043 ok=1
000157 SNAP tag=FINAL ticks=3391428199 since_control=4389390 since_a1=4383994 since_a2=4363250 polls_before=0
000158 PI tag=FINAL intsr=00010000 intmr=000001fa intsr13=0 intmr13=0
000159 RAW FINAL idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=00 sem_b1f=00 data=0100000000000000000000000000000000000000000000000000000000000000
000160 RAW FINAL idx=d addr=01d00000 rc=ok ticks=34 polls=9 dspcr=0804 sem_disc=9090 sem_gbi=9090 data=9190909090909090909090909090909090909090909090909090909090909090
000161 FINAL arinfo=0043 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 control=00 irq=9090 power_cycle_required=1
000162 AVSVC end status=ok_service_rearm_cause_observed class=ok reason=- restore=ok restore_reason=- teardown=S4B_next_cause_latched power_cycle_required=1 errors=0 transport_ok=1
000163 WRITES control_written=1 irq_attempted=5 irq_completed=5 ctl_exp=1/1 a1=1/1 a2=1/1 stop=1/1 ctl_restore=1/1 uncertain=0 power_cycle_required=1 format=attempted/completed
000164 OBSERVED intsr13_seen=1 t_first_intsr13=3391329164 first_phase=A2 first_value=00012000 polls_at_first=740594 event=1 ended_early=1
000165 RESTORE control_restore_ok=1 irq_stop_write_ok=1 irq_stop_readback_ok=1 stop_masks_readback=1 stop_bit15_readback=1 pi_cleanup_performed=1 pi_cleanup_ok=1 pi_cleanup_sticky=0 arinfo_restore_ok=1
000166 SERVICE pass pending=0500 drain=0500 selected=2 attempted=2 completed=2 drain_uncertain=0 ack=1/1 ack_value=8500 source_after_ack=0000
000167 SERVICE rearm relatch_postdrain=0 relatch_postack=0 pi_clean=1 pi_sticky=0 rearm=1/1 rearmpost=B_latched next_cause=1 immediate=1 timed_out=0
000168 COUNTERS unmasks=1 deliveries=1 acks=1 rearms=1 next_causes=1 unexpected=0000 site=- isr_w1c=1 main_w1c=0 teardown_w1c=1 w1c_total=2 control_ok=1 uncertain=0
000169 BLOCK kind=audio idx=8 len=1000 present=1 valid=1 crc32=fec5e4e7 zeros=3969 distinct=3 w_off=0000,0540,0aa0,0fe0 first_word=01000000 gbi_frame_start=0
000170 BLOCKW kind=audio off=0000 data=0100000000000000000000000000000000000000000000000000000000000000
000171 BLOCKW kind=audio off=0540 data=0100000000000000000000000000000000000000000000000000000000000000
000172 BLOCKW kind=audio off=0aa0 data=0100000000000000000000000000000000000000000000000000000000000000
000173 BLOCKW kind=audio off=0fe0 data=0100000000000000000000000000000000000000000000000000000000000000
000174 BLOCK kind=video idx=1 len=0f00 present=1 valid=1 crc32=fe45ff08 zeros=0 distinct=2 w_off=0000,0500,0a00,0ee0 first_word=ffffffff gbi_frame_start=1
000175 BLOCKW kind=video off=0000 data=ffffffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff
000176 BLOCKW kind=video off=0500 data=7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff
000177 BLOCKW kind=video off=0a00 data=7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff
000178 BLOCKW kind=video off=0ee0 data=7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff7f7fffff
000179 TIMING cause_to_isr=42530/1050us isr_to_presvc=7612 presvc_to_ack=20674 service=10997/271us ack_to_postack=1048 postack_to_rearm=7190 rearm_to_next_cause=1778/43us
000180 RESTOREAV handler_installed=1 handler_restored=1 old_handler=null mask_ok=1 intmr_final=000001fa pi_sticky_final=0 unmasked=1 masked_again=1
000181 STATS transfers=58 timeouts=0 busy=0 bulk_transfers=2 bulk_bytes=7936
# --- end --- dropped=0
```

Result: `ok_service_rearm_cause_observed` (class `ok`), `restore=ok`,
teardown `S4B_next_cause_latched`, `errors=0 transport_ok=1 uncertain=0
timeouts=0 busy=0`, 58 transfers of which 2 whole-block (7936 bytes), 182
lines, `dropped=0 truncated=0`; `COUNTERS unmasks=1 deliveries=1 acks=1
rearms=1 next_causes=1 unexpected=0000 isr_w1c=1 main_w1c=0 teardown_w1c=1
w1c_total=2 control_ok=1 uncertain=0`; `WRITES irq_attempted=5
irq_completed=5` (A1, A2, ACK, RE-ARM, STOP). The sidecar was written after
the log (`sidecar=` in the log header) and parses with every CRC intact.
**GBP-AV-SERVICE-001 — PHYSICALLY EXECUTED 2026-09-16.** Every number
below was read from the two files, not from the run report.

**Stage 003A reproduced (fourth run):** detection PRESENT (`run=4
transport_ok=4 vote_ok=4 b1_ok=4 all32_ok=1`), AR_INFO `0x0043 → 0x005B`,
BASE CONTROL `0x90` / IRQ `0x8AAE`, transform `IRQ := 0x8C` at
`t_after=3387038809`, A1 `IRQ := 0x8AAE` read back `0x8AAA` (bit 2 cleared,
as in 003A/003B/004), A2 `IRQ := 0x0000` read back `0x0000` in five samples
(50 µs … 50 ms), CONTROL `0x8C` throughout. **First cause:** the INTSR poll
saw `0x00012000` at `t_event=3391329164` = **4264215 ticks = 105.289 ms after
A2** (003A 105.273, 003B 105.286, 004 105.283 ms: four runs within 16 µs)
with INTMR bit 13 = 0, CONTROL `0x8C`, IRQ `0x0400` (`15 04 00 00 / 04 04 04
00 ×7`); PREUNMASK 37222 ticks later: `0x0500` (`17 05 01 00 / 05 05 05 00
×7`), INTSR still `0x00012000` in two samples — the second source joined
within 0.92 ms, as before. Nothing new here beyond a fourth data point
(GBP-HW-048).

**Delivery (third CPU delivery, 003B extended one-shot installed once):**
`__UnmaskIrq` at `t_unmask=3391371622`, back at `+240` ticks with the
handler already run: `t_entry=3391371694` (**72 ticks = 1.778 µs**; 003B 78,
004 89), INTSR at entry `0x00012000`, INTMR `0x000021FA` (bit 13 = 1 as
delivered), after `__MaskIrq` `0x000001FA`, one W1C `0x00012000 →
0x00010000`, second read 147 ticks later `0x00010000` / `0x000001FA`,
`count=1 reentry=0`; UNMASKPOST `0x00010000` / `0x000001FA`; main re-mask
idempotent (REMASKCHK `0x000001FA`). A physical confirmation of GBP-PI-005
through the third handler body used so far — not a new discovery
(GBP-HW-048).

**PRESVC — the authoritative snapshot** at 3391379306 (7612 ticks = 188.0 µs
after the entry): INTSR `0x00010000` twice, INTMR `0x000001FA`, CONTROL
`0x8C`, IRQ **`0x0500`** (`17 05 01 00 / 05 05 05 00 ×7`, Disc == GBI), odd
bits 0, bit 15 = 0, high bits 0, unexpected 0 → `pending=0500 drain=0500
audio=1 video=1 ack_value=8500`, assigned once and never re-derived
(GBP-HW-049). Both AV sources pending, PI clear — the state of 003B's
PREACK and 004's PREACK-0, now the entry of a drain.

**AUDIO block, one whole-block DMA (GBP-HW-050, FACT):** index 0x8, ARAM
address `0x01800000`, length `0x1000`, `selected=1 attempted=1 completed=1
rc=ok`, `t_start=3391385098 t_end=3391387790` → **dt = 2692 ticks = 66.47 µs
around the call**, of which `wait_ticks=2475` (61.1 µs) of completion wait
in 760 CSR polls; DSP CSR `0x0804` before and after (no DMA in progress, no
stale completion flag, ARAM DMA interrupt masked). **VIDEO block, one
whole-block DMA (GBP-HW-051, FACT):** index 0x1, `0x01100000`, `0xF00`,
`completed=1 rc=ok`, `t_start=3391387818 t_end=3391390303` → **dt = 2485
ticks = 61.36 µs**, `wait_ticks=2319` (57.3 µs), 712 polls, CSR `0x0804`
before and after. AUDIO completed 28 ticks before VIDEO started (no
overlap), no timeout, no busy refusal, `STATS bulk_transfers=2
bulk_bytes=7936`. Per 32 bytes the two transfers took 21.0 and 20.7 ticks
of the time base (≈ 519 / 512 ns); Dolphin's model of 246 CPU ticks per 32
bytes at 486 MHz is ≈ 506 ns — an observation of one run each, not a rate
promoted to the model. **Service:** `SVCEND drain=0500 selected=2
attempted=2 completed=2 ok=1 dt_service=10997` = **271.5 µs** from the
PRESVC snapshot to the last completion (the snapshot's own reads and
logging included: the AUDIO call began 143 µs after the snapshot) — a
measurement of this probe, not a property of the hardware (GBP-HW-050/051).

**POSTDRAIN (observation only)** at 3391394064, 3761 ticks = 92.9 µs after
the VIDEO completion: INTSR `0x00010000` twice, INTMR `0x000001FA`, CONTROL
`0x8C`, IRQ **`0x0500`** (`17 05 01 00 / 05 05 05 00 ×4 / 05 05 04 00 / 05
05 05 00 ×2`), `relatch=0 av_after_drain=0500 pending_kept=0500`.
**Observational FACT (GBP-HW-052):** reading both blocks did not, by itself,
clear the two source bits within ≈ 93 µs of the last completion, and no PI
cause latched during or after the drain with bit 15 = 0 (≥ 552 µs after the
handler's W1C with both sources pending, extending 003B's 179.7 µs and 004's
209.8 µs). **Not concluded:** that a block read never alters the device's
internal state (a request counter, a buffer pointer, the next event) —
only the register's source bits were observed, at one instant.

**ACK after the drain:** `IRQ := 0x0500 | 0x8000 = 0x8500` (`85 00 ×16`, rc
ok, `t_after=3391399980`, attempted 1 / completed 1). **POSTACK** at
3391401028 = **1048 ticks = 25.88 µs later: IRQ `0x8000`** (`81 80 00 00 /
80 80 00 00 ×7`, Disc == GBI): both sources 0, bit 15 = 1, odd bits 0, high
bits 0, INTSR `0x00010000` twice, INTMR `0x000001FA`, CONTROL `0x8C`;
`MAINPICLEANUP performed=0`, `boundary=clean source_after_ack=0000
relatch=0 main_w1c=0`, PICLEAN `intsr=00010000 intmr=000001fa ok=1`.
**Comparison with 004 (no drain): same PREACK `0x0500`, same ACK `0x8500`,
26.0 µs later `0x8400`; here, after the drain, 25.9 µs later `0x8000`** —
and 003B, also without a drain, read `0x8000` at +25.1 µs. Safe
conclusion (GBP-HW-053): a service that drains the blocks before its ACK
was followed, in this run, by a source-clean read-back at the same
distance at which 004 saw 0x0400 again; the observable state after the
ACK differed between the drained and the undrained pass consistently with
the references' order (drain, then ACK / re-arm). **Not concluded:** a
microscopic causality (that the drain "consumed" the request, that the
0x0400 of 004 was a level the drain would have released, or a period):
003B's undrained ACK also read 0x8000 once. U-GBP-028 is partially
closed by this: an ACK after a drain can produce a source-clean snapshot;
whether the undrained 0x0400 of 004 was never cleared or re-asserted within
26 µs stays undetermined and non-blocking.

**RE-ARM — the first physical `IRQ := 0` after a serviced cycle (GBP-HW-054,
FACT):** written at `t_rearm=3391408218` (7190 ticks = 177.5 µs after the
POSTACK snapshot; PI verified clean immediately before: `PICLEAN … ok=1`),
`before=8000 value=0000` (`00 ×32`), rc ok, `t_after=3391408974`, attempted
1 / completed 1. Between the ACK and the re-arm (≥ 203 µs) bit 15 read 1
with both sources 0 and PI clear in every sample.

**NEXT HSP CAUSE — REARMPOST outcome B (GBP-HW-055, FACT):** snapshot at
3391409996 = **1778 ticks = 43.90 µs after t_rearm**: INTSR **`0x00012000`
in both samples** (bit 13 = 1), INTMR `0x000001FA` (bit 13 = 0: the CPU
stayed masked), CONTROL `0x8C`, IRQ **`0x0400`** (`15 04 00 00 / 04 04 04 00
×7`), unexpected 0, odd bits 0, bit 15 = 0, high bits 0 → `outcome=B_latched
ok=1`; `NEXTCAUSE found=1 immediate=1 t_next_cause=3391409996 since_rearm=1778
polls=0 delivered=0`. After service + ACK + PI clean + `IRQ := 0`, a new HSP
cause with a valid AV source was captured by the PI within 43.9 µs while
IRQ 26 stayed masked, and it was never delivered (no second unmask, no
second handler entry: `unmasks=1 deliveries=1`). **Not concluded:** that the
0x0400 request arose after the re-arm rather than being held (bit 15 = 1)
and released by it — the register was not sampled between the PICLEAN
read and the REARMPOST snapshot, and the interval 43.9 µs contains the
write itself; the first-request delay after A2 was 105 ms in four runs, so
"a new periodic event within 44 µs" and "a retained request released by
bit 15 → 0" are both compatible (U-GBP-027 investigative sub-item, not
blocking). Whichever it is, the runtime's loop — drain, ACK, re-arm, wait
for the next cause — was exercised once end to end on hardware.

**U-GBP-027, functional objective:** delivery → drained service → ACK → PI
clean → re-arm → next HSP cause: satisfied for one cycle. The practical
re-arm mechanics are physically validated (GBP-IRQ-010 "Service cycle" /
"Re-arm"); the purely investigative sub-items (whether the post-re-arm cause
is retained or new; the request period with no cartridge; the cost of a
missed block; sustained service over many cycles) move to non-blocking
follow-ups of the Phase 4 experiments.

**Phase 3 — formal decision.** The criterion recorded on 2026-09-16 (DEVLOG
"next step after GBP-INIT-004 decided": Phase 3 "closes with the first
physical service → re-arm → next cause") is met by this run: **PHASE 3
COMPLETE (2026-09-16)** — IRQ core validated by GBP-INIT-003B / 004, service,
re-arm and next cause validated by GBP-AV-SERVICE-001; the remaining
microscopic unknowns (U-GBP-027 sub-items, U-GBP-028, U-GBP-007's bit-15
mechanism) are non-blocking. Phase 4 was already entered by this probe (the
first physical AUDIO/VIDEO blocks) and is not concluded.

**Teardown (S4B_next_cause_latched, CPU masked, the second cause left to the
teardown by design):** `TEARDOWN start irq_attempted=4 irq_completed=4`;
CONTROL `0x8C → 0x90` (`t_after=3391417891`, read back `91 90 ×31` → 0x90);
IRQSTOPPRE **`0x0500`** — 0x0100 had joined 0x0400 between the REARMPOST
read and this read (≤ 12203 ticks = 301 µs after REARMPOST, an upper bound);
stop `IRQ := 0x0500 | 0x8AAA = 0x8FAA` (`8F AA ×16`) read back **`0x8AAA`**
(`masks_readback=1 bit15_readback=1`; the fourth stop-word validation:
0x8FAA in 003A/003B, 0x8EAA in 004); CLEANUPCHK INTSR `0x00012000` (the
latched second cause) → **one W1C `0x2000` → `0x00010000`, `sticky=0`**;
handler restored (`old_handler=null`, rc ok); MASKCHK INTMR `0x000001FA`
(`orig_intmr13=0`); AR_INFO `0x005B → 0x0043` (read back); FINAL under
expansion code 0: CONTROL `01 00 ×31` → 0x00, IRQ `91 90 ×31` → 0x9090, INTSR
`0x00010000`, INTMR `0x000001FA`; `RESTORE control_restore_ok=1
irq_stop_write_ok=1 irq_stop_readback_ok=1 stop_masks_readback=1
stop_bit15_readback=1 pi_cleanup_performed=1 pi_cleanup_ok=1
pi_cleanup_sticky=0 arinfo_restore_ok=1`; `RESTOREAV handler_installed=1
handler_restored=1 mask_ok=1 intmr_final=000001fa pi_sticky_final=0
unmasked=1 masked_again=1`. A new physical teardown combination
(GBP-HW-056): stop from 0x0500 with a latched PI cause, cleared by exactly
one W1C; `w1c_total=2` (ISR 1, main 0, teardown 1) within the budget of 3.

**AUDIO block, raw (GBP-HW-057; U-GBP-012 first hardware data):** 4096
bytes, CRC-32 `FEC5E4E7`, 3969 zero bytes, 3 distinct values (`00`, `01`,
`11`), first word `0x01000000`, GBI frame-start predicate 0 (not
applicable). Positions of the 127 non-zero bytes: 123 at offset 0 of a
32-byte line (`01` in 121 lines, `11` in lines 31 and 61; lines 3, 22, 33,
41 and 74 entirely zero) and four isolated `01` at in-line offsets 12, 30, 8
and 26 (absolute 0x08C, 0x49E, 0x8A8, 0xCBA). The four log windows (0x000,
0x540, 0xAA0, 0xFE0) match the sidecar byte for byte. **Not concluded:**
that this is PCM, PWM, silence or any structure (Dolphin's PWM model stays
HYPOTHESIS); whether the per-line byte 0 belongs to the payload or is the
32-byte-transfer byte-0 phenomenon of the register reads (U-GBP-021) —
its pattern (one non-zero byte per 32-byte line, nearly constant) resembles
it and is recorded as a hypothesis to test with repeated captures, not as
a fact.

**VIDEO block, raw (GBP-HW-058; U-GBP-008/011 first hardware data):** 3840
bytes, CRC-32 `FE45FF08`, 0 zero bytes, 2 distinct values (`7F`, `FF`),
first word **`0xFFFFFFFF`**, GBI frame-start predicate `(w & 0x80800000) ==
0x80800000` **true**. As 960 four-byte groups: group 0 `FF FF FF FF`, 954
groups `7F 7F FF FF`, 5 groups `FF 7F FF FF` (groups 41, 165, 186, 426, 578 —
at in-line offsets 4, 20, 8, 8, 8). The `hh hh ll ll` doubling of the
register reads holds in 955 groups and breaks in those five (byte 0 ≠ byte
1); their meaning (content, a transfer artifact, the same class as the
register byte-0 extras) is unknown. Windows 0x000, 0x500, 0xA00, 0xEE0
match the sidecar. **Not concluded:** the image, the color order
(U-GBP-011), that 0xF00 = 4 lines × 240 pixels (a DMA of 0xF00 bytes
completes regardless of the block's true size; the geometry stays
CORROBORATED by the references only).

**Byte 0 / offset 2 (U-GBP-021 / U-GBP-025; GBP-HW-059):** extras in this run
— TEST `7F` (0x43 over 3C), `D3` (0x10 over C3), `11` (0x11 over 00), none
over FF, `01` over the 00 pattern at BASE/P0; CONTROL `93` (0x03 over 90),
`9F` (0x13 over 8C) in all fifteen 0x8C reads, `91` (0x01 over 90) at TDCTL,
`01` over 00 at FINAL; IRQ `9B` (0x11 over 8A) in every 0x8AAE/0x8AAA read,
`01` over 00 in the five 0x0000 reads, `15` (0x11 over 04) in both 0x0400
reads, `17` (0x12 over 05) in the five 0x0500 reads, `81` (0x01 over 80) at
POSTACK, `91` (0x01 over 90) at FINAL. Disc and GBI readings agreed in every
read, `vote == byte 0x1F` everywhere, detection PRESENT: byte 0 fed no
decision. Offset ≡ 2 mod 4: the `lo | (hi & 0x05)` pattern held for every
0x8AAE / 0x8AAA / 0x0000 / 0x8000 / 0x9090 read except group 0 of A2PRE
(`BB` where it predicts `AA`; that read also took 41 ticks / 11 polls
instead of 34 / 9), for groups 1–7 of the 0x0400 and 0x0500 reads (group 0:
`00` / `01` where it predicts `04` / `05`; 003B/004: `00` / `04`), and broke
in group 5 of the POSTDRAIN 0x0500 read (`04`). All pinned byte by byte by
the fixture test. New catalogue values 0x03, 0x12, 0x13, 0x43; U-GBP-021
reinforced as non-blocking: byte 0 of a raw block never decides.

**What this run did NOT test — explicit:** a second delivery (forbidden by
design; `deliveries=1`); a second service pass or any cadence (one interval
of each kind: `rearm_to_next_cause=1778` ticks, and 0x0100 back within
≤ 301 µs of REARMPOST — no period from one run); the re-arm with an
unconsumed block (004B, optional); a second read of a drained block; the
content of the blocks (recorded, not interpreted); KEYPAD, SIO, a cartridge,
Dolphin's model (never reaches the service). Evidence GBP-HW-048…060,
GBP-IRQ-010; unknowns U-GBP-007/008/011/012/014/021/022/025/027/028 updated;
INITIALIZATION.md §14; REGISTERS.md / HSP.md notes; ROADMAP Phase 3
COMPLETE; POC README result; DEVLOG 2026-09-16 "GBP-AV-SERVICE-001
executed". Next Phase 4 experiment: GBP-VIDEO-001 (direction in the DEVLOG
entry; not designed here).

## Planned tests

### SMOKE-HW-001 — first physical run of `poc/smoke-test` (Phase 3 gate 1)

Executed and passed on 2026-09-14 — see "Executed tests" above.

### GBP-PROBE-001 — read-only GBS-DOL presence probe (Phase 3 gate 2)

Executed on 2026-09-14 — see "Executed tests" above. Full procedure with all fields
in `poc/gbp-probe/README.md`. Answers U-GBP-004 and U-GBP-008 and gives
the first hardware confirmation of GBP-HSP-001/GBP-TEST-001. Dolphin
validation (model only): `make probe-dolphin` passes with the HSP device
absent and with Dolphin's GBPlayer model.

```text
Question:    Does the TEST window echo inverted data, and is the 0xCC005012
             expansion code required for the DMA to reach the GBP?
Hypothesis:  With code 3 written, DMA-write 32×0xC3 to internal_size+0 then
             DMA-read returns 32×0x3C (or byte 0x1F == 0x3C); without the
             write the read returns something else (stale ARAM / zeros).
Why static analysis cannot answer: Dolphin ignores the size code; both
             drivers always write it.
Minimal test: 1) read 0xCC005012, 32-byte read of internal_size+0 (log raw
             block) 2) write code 3, repeat 3) write 32×0xC3, read, log raw
             block 4) repeat with 0x3C, 0xFF, 0x00 5) restore 0xCC005012.
             Also dump raw 32-byte reads of CONTROL (idx 0x4) and IRQ
             (idx 0xD) without writing them.
Expected:    step 3 read == ~pattern (at least byte 0x1F); CONTROL bits
             0x01/0x02 reflect the inserted cartridge; IRQ read has no
             even bits set while nothing runs.
Risk:        low — writes only the TEST window (what every driver writes
             first) and a GameCube-side register that libogc already
             probes. No CONTROL writes, no AGB power-on.
Output:      on-screen hex dump + SD2SP2 log with build id.
```

### GBP-BASELINE-NOGBP-001 — requested 2026-09-14, executed the same day (see "Executed tests")

Same DOL as GBP-PROBE-001 (`probe-0001`, commit `55ed6c1`, SHA-256
`36d8b23b14afbc191899ca0ddf4ad9b845cedf6c09a26b3d6a6187a8c2862994`), not
rebuilt; the log will therefore still say `test_id=GBP-PROBE-001`. The
physical run id is documentary only. Single intended variable versus
the 2026-09-14 run: the Game Boy Player is physically removed (console
powered off for the swap). Everything else unchanged (BBA attached
without cable, 1 controller, 1 Memory Card, SD2SP2, Swiss). Answers
U-GBP-016 and tells which of GBP-HW-003/004/005 and U-GBP-015 need the
device. Note: `sdlog.c` opens the report with mode `w`, so the copy of
`GBP-PROBE-001_probe-0001.log` on the SD card is overwritten — the user
must confirm a safe copy exists before running.

### GBP-INIT-002 — controlled GBI IRQ path after the validated CONTROL transform (designed 2026-09-15; executed 2026-09-15 — see "Executed tests" above)

Executed on 2026-09-15 with build `initirq-0001`, clean commit `4e3cb43`,
DOL SHA-256 `1bd2bcf3…43f2`, log sha256 `e7ec3d83…ea1d` (6585 bytes) — see
"Executed tests" above. The design below is kept as it was written before
the run; the implementation sets AR_INFO bits 3–5 before the detection
handshake (as GBP-INIT-001 did and as both references do).

```text
Question:    After the validated CONTROL transform (0x90 → 0x8C, GBI layout),
             does the GBS-DOL raise PI INTSR bit 13 once IRQ 26 is unmasked,
             and what does INTSR do immediately after a W1C of 0x2000 inside the
             handler, after re-masking, and after CONTROL is restored?
Answers:     first hardware observation of INTSR bit 13 = 1 (or its absence
             within T_MAX); part of U-GBP-022 (latched-and-W1C vs level); the
             latency between unmask and handler entry; U-GBP-021 samples for free.
Why static analysis cannot answer: Dolphin's PI/HSP model re-sets the cause on
             every device event and clears it on W1C (model, not hardware); the
             two references never read INTSR; GBI waits without a timeout.
Reference order followed: GBI (transform → IRQ_Request → __UnmaskIrq), with a
             one-shot self-masking handler instead of GBI's thread signal.
Not done:    idle unmask before the transform (rejected: Option D and the
             "stage A" variant); any write to the GBP IRQ register, KEYPAD,
             VIDEO, AUDIO, SIO.

Sequence:
  1. detection gate: TEST handshake, verdict must be PRESENT (else: no CONTROL
     write, no handler, no unmask; AR_INFO restored; log + screen)
  2. AR_INFO bits 3–5 := 3 (read back)
  3. S0: PI (INTSR, INTMR), CONTROL raw+semantic, IRQ raw+semantic
     preconditions: INTMR bit 13 == 0, INTSR bit 13 == 0, CONTROL idle shape
     ((v & 0x10) != 0 && (v & 0x0C) == 0); any failure → abort, never adjust
  4. old = IRQ_Request(IRQ_PI_HSP, handler)      — recorded; expected NULL
  5. CONTROL := (v & ~0x10) | 0x0C, GBI byte-replicated layout (validated)
  6. S1: PI, CONTROL, IRQ (IRQ 26 still masked)
  7. t_unmask = gettick(); PI read; __UnmaskIrq(IM_PI_HSP)
  8. wait until fired == 1 or (gettick() - t_unmask) >= T_MAX ticks
  9. __MaskIrq(IM_PI_HSP)                         — idempotent
 10. S2: PI read twice, CONTROL, IRQ; copy handler fields
     (fired, count, tb_entry, intsr_before, intmr_before, intsr_after, intmr_after)
 11. CONTROL := original semantic value (GBI layout)
 12. S3: PI, CONTROL, IRQ
 13. if INTSR bit 13 == 1: INTSR := 0x2000 (masked; Start-up Disc stop precedent); PI read
 14. IRQ_Request(IRQ_PI_HSP, old)
 15. AR_INFO restore (read back)
 16. S4: PI, CONTROL, IRQ; INTMR compared with S0
 17. screen summary; X saves the SD log; START exits
Handler (one-shot; PI MMIO only; no DMA, filesystem, printf, allocation, blocking):
     tb_entry = gettick(); intsr_before = INTSR; intmr_before = INTMR; count++;
     __MaskIrq(IM_PI_HSP); INTSR := 0x2000; intsr_after = INTSR; intmr_after = INTMR;
     fired = 1; return.   count > 1 → re-mask, return; main records "anomaly".
Shared state: 32-bit volatile fields only; copied by main after step 9.
Mandatory order (host regression when implemented):
     IRQ_Request < CONTROL experimental write < __UnmaskIrq; unmask never without a
     handler; unmask never before the transform.
Timeout:     T_MAX = 2000 ms proposed — operational/usability bound, not a hardware
             property; on expiry the result reads "no IRQ 26 within T_MAX".
Writes:      AR_INFO bits 3–5; TEST; CONTROL transform + restore; INTMR only via
             __MaskIrq/__UnmaskIrq; INTSR W1C 0x2000. Nothing else.
Restore (idempotent, same on every abort path): mask IRQ 26 → CONTROL original →
             observe PI → INTSR W1C if bit 13 set → previous handler → original mask
             state (expected masked; unmasked at S0 = abort) → AR_INFO → final
             snapshot; all before the SD flush and before returning to Swiss.
Expected records (names may change): PI tag=…, SNAP/RAW as in GBP-INIT-001,
             HANDLER fired= count= tb_entry= latency_ticks= latency_us=
             intsr_before= intmr_before= intsr_after= intmr_after=,
             UNMASK ticks= intsr= intmr=, TIMEOUT t_max_ms=, RESTORE …, INTSR W1C rc.
Risk:        low-medium — one new class of operation (PI HSP unmask with a
             handler); storm bounded by the handler's self-mask (INTMR gating is
             CORROBORATED, not yet observed for bit 13); AGB powered ≤ T_MAX
             without a cartridge then cut (GBI exit does the same); possible
             un-acknowledged device state (U-GBP-023) → power-cycle the console
             after the run.
Physical setup: identical to GBP-INIT-001 (no cartridge, SD2SP2, Swiss).
```

Release fields: Test ID GBP-INIT-002 · Build ID `initirq-0001` · DOL
`build/poc/gbp-init-irq-probe/gbp-init-irq-probe.dol` SHA-256
`1bd2bcf3f361e6482c888a523d45ea2fa2dc073f41918ebfab7803b1177343f2` · commit
`4e3cb43` · no cartridge · Link Port empty · PicoAdapterGB disconnected · BBA
attached, no cable · 1 controller · 1 Memory Card · SD2SP2 · executed as
planned; question answered: no IRQ 26 within 2000 ms under this sequence,
INTMR bit 13 physically toggled, IRQ block 0x8AAE → 0x8FAE (see the executed entry).

### GBP-INIT-003A — GBP IRQ-register programming with PI HSP masked throughout (designed 2026-09-15; implemented and executed 2026-09-15 — see "Executed tests" above)

Status: **PHYSICALLY EXECUTED 2026-09-15** (commit `d956b1b`, DOL sha256 `8c225bd1…bfa5`, log sha256 `ae911745…2ef8`). Design text kept below as written before the run. Code: `poc/gbp-init-irq-program-probe/`
(Test ID `GBP-INIT-003A`, Build ID `initirqa-0001`), logic in
`src/gbp/gbp_initirqa_probe.c`, write primitive `src/gbp/gbp_regwrite.c`
(GBI u16-replicated layout), base backend `src/platform/hsp_backend.c`
only (the interrupt-path object `hsp_backend_irq.c` is not linked).
The build reviewed so far comes from a dirty tree (`commit=664f0de-dirty`)
and is a review candidate only; the physical candidate is a clean build
after the review and a separate clean audit, and will be recorded here
with its SHA-256 before any hardware request. Validation without
hardware: `tests/unit/test_gbp_initirqa.c` (synthetic source/mask model
of the IRQ register, every abort/restore path, event order, "never"
properties, the physical init-0001/initirq-0001 prefixes up to the first
experimental write), `tools/poc_audit.py` on every linked object (no
INTMR store, no `__UnmaskIrq`/`IRQ_Request`/`IRQ_Free`/handler reference,
exactly three IRQ-register write sites), `make initirqa-dolphin` (absent →
`abort_not_present`; GBPlayer model → `abort_control_shape`, no write),
`tests/host/test_initirqa_replay.py` (synthetic fixture round trip; no
physical GBP-INIT-003A fixture exists). Design unchanged from the text
below; the implementation adds a BASE snapshot before the CONTROL write
(the IRQ shape is checked there and again at A1PRE), an INTMR bit-13
re-check at P0 and at A2PRE, and formats every record of the
experimental region only after the window (`REGION formatted_inside=0`). The two experimental writes are literally the values
of GBI's first loop pass (GBP-IRQ-004); the stop write is the Start-up
Disc's (GBP-IRQ-002/006). GBP-INIT-003B (delivery: handler + unmask) was
designed after 003A's physical result and implemented 2026-09-15 as a dirty
build (not executed): its own entry below.

```text
Question A1: with PI HSP masked, what does IRQ := irq_read | 0x8000 (GBI's acknowledge,
             u16 replicated 16×) change in the IRQ read-back — which source bits clear
             (0x0004; 0x0100/0x0400 if pending), do the odd masks and bit 15 stay, does
             INTSR bit 13 stay 0?
Question A2: after that acknowledge, what does IRQ := 0 (GBI's end-of-pass write, 32 × 00)
             change — masks 1/3/5/7/9/11 to 0? bit 15 to 0 or back to 1? sources kept /
             re-asserted? — and does a source that becomes visible afterwards raise INTSR
             bit 13 while delivery to the CPU stays masked?
Separates:   source acknowledge (A1) from mask/control programming (A2); never one write.
Why static analysis cannot answer: no reference reads the register back between its
             writes; Dolphin models neither masks nor bit 15 as the hardware shows them.
Protection:  PI HSP masked for the whole run — no handler, no __UnmaskIrq, no INTMR write;
             INTSR bit 13 = 1 can only be observed, never delivered. libogc2 keeps IRQ 26
             masked on its own (ENV-IRQ-002); Swiss does too.

Preconditions (abort, never adjust): PRESENT (both criteria); INTMR bit 13 == 0;
             INTSR bit 13 == 0; CONTROL idle shape ((v & 0x10) != 0, (v & 0x0C) == 0,
             vote == byte 0x1F).

Sequence:
  boot → PRESENT gate → AR_INFO bits 3–5 := 3 (readback) → PI preconditions → CONTROL baseline
  → CONTROL := (v & ~0x10) | 0x0C  (validated transform, GBI layout)
  → P0: ticks, INTSR, INTMR, CONTROL raw+semantic, IRQ raw+semantic
  → A1: irq_before_ack = IRQ read (raw kept); ack_value = irq_before_ack | 0x8000;
        IRQ := ack_value  — GBI 16-bit layout: the u16 replicated 16× (hh ll hh ll …), one
        32-byte DMA at base+0xD00000 (the IRQ half of GBI's 64-byte write); the source bits
        that read 1 are written as 1 on purpose (that is the W1C acknowledge GBI performs)
  → A1-0 immediately: ticks, INTSR, INTMR, CONTROL, IRQ; then one or two read-only samples
        within a short window (to tell W1C from re-assertion) — time-base spacing only
  → irq_before_zero = IRQ read (raw kept; sources may have re-asserted — recorded, not required
        to be 0)
  → A2: IRQ := 0  (32 × 00, GBI's FUN_80015da0 layout)
  → A2-0 immediately: ticks, INTSR, INTMR, CONTROL, IRQ
  → temporal samples, PI still masked: ≈ 50 µs, ≈ 500 µs, ≈ 5 ms, ≈ 50 ms, ≈ 500 ms, up to
        ≈ 2000 ms only while still useful; absolute/delta time base, busy-wait, structured
        records only (no formatting inside the window; the main loop formats afterwards)
  → teardown (PI still masked): CONTROL := original semantic value (GBI layout) → IRQ read →
        stop_irq = irq_read | 0x8AAA (Start-up Disc stop: masks of the six slots + bit 15;
        pending sources written as 1 = acknowledged under the W1C model) → IRQ := stop_irq
        (16-bit layout) → IRQ read → INTSR read → if bit 13 == 1: ONE INTSR := 0x2000, re-read
        → AR_INFO original (readback) → final snapshot
  → console power cycle: MANDATORY before any other software or test (shown on screen and in
        the README)
If INTSR bit 13 becomes 1 inside the window: no W1C, PI is masked; keep at least one snapshot
        with INTSR bit 13 = 1 together with the IRQ and CONTROL of the same moment; the window
        may then end early.
Valid outcomes (none is an error): sources cleared or not cleared or re-asserted by A1;
        masks answering or not answering A2; bit 15 changing in any way; INTSR bit 13
        staying 0 or rising at any point; CONTROL changing; another block layout.
Properties, to be tested automatically when implemented:
        irq handler installs = 0; __UnmaskIrq calls = 0; INTMR writes/toggles = 0 (INTMR is
        only read); CONTROL writes = 2; IRQ-register writes = 3 (A1, A2, stop); INTSR W1C ≤ 1
        (teardown only, only if bit 13 set); KEYPAD, VIDEO, AUDIO, SIOCTL, SIODATA, BBA:
        never touched; every DMA with the 200 ms timeout; screen and SD only after the
        teardown.
Writes (complete): AR_INFO bits 3–5; TEST (gate); CONTROL transform; IRQ A1 = read | 0x8000;
        IRQ A2 = 0; CONTROL restore; IRQ stop = read | 0x8AAA; PI INTSR W1C once if needed;
        AR_INFO restore. Never: INTMR, KEYPAD, VIDEO, AUDIO, SIO, BBA/network.
GBI fidelity: NOT a full reproduction — PI masked throughout; no KEYPAD := 0; no VIDEO/AUDIO/
        SIO transfers; snapshots between the operations; Start-up-Disc-style stop. The two
        experimental writes are literally GBI's first-pass values, in GBI's order:
        read | 0x8000, then 0.
Risks:  a device line asserted for up to ~2 s with PI masked (no CPU effect); a model error
        that leaves the device asserted behind CONTROL 0x10 (power cycle); bits 12–14
        written 0 (both references do the same). Cartridge not introduced; byte 0 kept as
        raw evidence only.
Physical setup: identical to GBP-INIT-002.
```

### GBP-INIT-003B — delivery of a latched HSP cause to the CPU as IRQ 26 (designed 2026-09-15; implemented and executed 2026-09-15 — see "Executed tests" above)

Status: **PHYSICALLY EXECUTED 2026-09-15** (build initirqb-0001, commit
d3da8cd, DOL sha256 `821aa2b2…b757`; result above, evidence
GBP-HW-035…041, GBP-PI-005, ENV-IRQ-003, GBP-IRQ-008). The paragraph
below is the pre-execution status kept for the history; the clean build
of d3da8cd was audited (PHYSICAL CANDIDATE READY, DEVLOG 2026-09-15
"GBP-INIT-003B release audit") and executed once; no second run is
requested. Pre-execution status: IMPLEMENTED — NOT PHYSICALLY EXECUTED —
DIRTY BUILD, NOT A PHYSICAL CANDIDATE; no hardware, no request (DEVLOG
2026-09-15 "GBP-INIT-003B designed" and "GBP-INIT-003B implemented"). Code:
`src/gbp/gbp_initirqb_probe.{h,c}` composed on the executed 003A module,
which was refactored into stages (`gbp_initirqa_run_cause`,
`gbp_initirqa_teardown`, snapshot helpers) without behavior change — its
2195 host checks and the physical initirqa-0001 replay are unchanged;
the extended one-shot body `gbp_irq_oneshot_service_ext()`
(`src/gbp/gbp_irq_oneshot.h`; the GBP-INIT-002 body kept verbatim);
`src/platform/hsp_backend_irq.c` (`hsp_backend_irq_transport_ext`,
`hsp_backend_oneshot_isr_ext`; the direct INTMR store of GBP-INIT-001
moved to `hsp_backend_intmr.c`, so the interrupt-path object holds none);
POC `poc/gbp-init-irq-deliver-probe/` (Test ID `GBP-INIT-003B`, Build ID
`initirqb-0001`, gecko prefix `OPENGBP-INITIRQB`, SD file
`GBP-INIT-003B_initirqb-0001.log`). Build under review: base HEAD
`fa6f35e`, tree dirty (`fa6f35e-dirty`), DOL sha256
`ee34d93ad2774a9365fa9afd8485558f78e2f53df939b35ee1a84220f581df80`
(383232 bytes, entry 0x80003100, 1 text + 1 data section, 32-byte
aligned, devkitPPC GCC 16.1.0, libogc2 r2442.094b250). Host validation
of that build: `tests/unit/test_gbp_initirqb.c` 1031 checks (≈40 mock
scenarios: delivery, level re-assert, delayed re-latch, W1C budget and
sticky, timeout, unmask ineffective, reentry, mask failure, install
failure, no IRQ path, every PREUNMASK abort, non-NULL previous handler,
ACK / stop / CONTROL / handler / AR_INFO restore failures, read failures,
no cause, stage aborts, call-time attempted/completed, wrapping time
base, worst-case line widths, ring overflow, event order and "never"
properties; the physical 003A fixture as the prefix up to the EVENT —
the probe stops at the handler install because the fixture has no
interrupt path, and the 003A teardown consumes every remaining line);
Python 124 tests including the synthetic round trip
`tests/host/test_initirqb_replay.py` (log → `tools/probelog.py` fixture
marked SYNTHETIC → replay → identical summary); `make initirqb-audit`:
`tools/isr_audit.py` on both handlers CLEAN (ext body 82 instructions,
base 70; only `__MaskIrq` called, exactly one INTSR store of 0x2000
after the mask, no INTMR store), `tools/poc_audit.py --profile 003b` 0
findings (`__UnmaskIrq` one call site `h_irq_unmask`, `IRQ_Request` only
`h_irq_install`/`h_irq_restore`, `__MaskIrq` only `h_irq_mask` + the two
handlers, INTMR stores 0, IRQ-register write sites 3 + 1, `main.o` uses
the ext constructor); `make initirqb-dolphin`: no HSP device →
`abort_inconsistent`, GBPlayer model → `abort_control_shape`, no write,
no install, no unmask, OSD off. **No physical GBP-INIT-003B fixture
exists and none is invented.** Before any hardware: a checkpoint commit,
a clean rebuild, a clean audit and a recorded hash. Precisions of the
implementation relative to the design below: (1) the ISR record keeps
the 002 field names `intsr_before_ack` / `intsr_after_ack` for
`intsr_at_entry` / `intsr_after_w1c` and names `intmr_final`
`intmr_second` (the log records use the 003B names); (2) an additional
status `anomaly_mask_failure` (INTMR bit 13 still 1 after the main
re-mask and one retry: no device ACK, teardown) and the
`abort_pre_unmask_state` reasons `read_failed` / `record_not_clear` /
`cause_lost` / `intmr13_unmasked` / `control_changed` /
`semantic_disagree` / `irq_state_unexpected`; (3) a device ACK whose
PREACK IRQ read failed or whose two readings disagree is skipped
(`ACK skipped=1 reason=`), the run continues to the teardown and the stop
word; (4) the 003A-stage aborts keep 003A's status names; (5) the ISR
wait is bounded twice (≈100 ticks and 4096 time-base reads); (6) the
teardown restores the previous handler before verifying the mask, as
designed, also on the anomaly paths (a persistent cause with an
ineffective mask hangs the CPU whichever handler is present — the power
cycle covers it). Design (unchanged) — depends on GBP-INIT-003A
(executed: GBP-HW-027…034, GBP-PI-004, GBP-IRQ-007), GBP-INIT-002
(GBP-HW-021…026), ENV-IRQ-001/002 (libogc2 dispatcher and mask API,
verified against the checkout `external/libogc2/libogc/irq.c`:
`IRQ_Request` only swaps the table entry under `_CPU_ISR_Disable`;
`__UnmaskIrq` rebuilds INTMR under `_CPU_ISR_Disable` and restores EE at
its end, so a pending `cause & mask` is taken as an exception before the
call returns; `__MaskIrq` is safe inside a handler), GBP-IRQ-002/003
(reference orders).

```text
Question:    With a real HSP cause already latched at the PI (INTSR bit 13 = 1) while IRQ 26 is
             masked (INTMR bit 13 = 0) — the state GBP-INIT-003A produced 105 ms after A2 — does
             __UnmaskIrq(IM_PI_HSP) deliver it to the CPU handler at once, and what does INTSR do
             after the handler's W1C while the device source is still pending (level/pulse
             discriminator, U-GBP-022 remaining part)?
Separates:   source generation (the 003A sequence, reproduced verbatim with PI masked) from the
             handler installation and from the unmask. One new variable: delivery.
Why static analysis cannot answer: libogc2 delivers `cause & mask` (ENV-IRQ-001), but no physical
             HSP cause has ever reached a CPU handler (INIT-002 unmasked with no cause; 003A had a
             cause with no unmask); no reference reads INTSR after its own W1C.

Handler installation point (options compared):
  A) before CONTROL/A1/A2 (GBP-INIT-002 order): inert while masked (IRQ_Request touches only the
     handler table); safe; but the 003A replica no longer runs "without a handler" and the install
     sits ~110 ms away from the unmask it serves.
  B) after INTSR bit 13 = 1 has been observed with PI masked, then unmask: the 003A part is
     reproduced with the same code path and the same auditable properties; the cause exists before
     the handler and before the unmask (clean causality); nothing can be lost (PI latch: FACT,
     GBP-HW-033); the install and the PREUNMASK snapshot (three DMAs, ~100 µs) touch nothing on
     the device; the precondition is checked after the install.  → CHOSEN.
  C) immediately before A2: no advantage over A or B, a third ordering with no reference precedent.
  All options: never unmask without a handler (ENV-IRQ-001 consequence 2); the previous handler is
  kept verbatim (NULL in GBP-INIT-002) and restored at the end.

Preconditions (abort, never adjust): as 003A — PRESENT (both criteria), INTMR bit 13 == 0 and
             INTSR bit 13 == 0 at the start, CONTROL idle shape, IRQ shape (BASE and A1PRE), INTMR
             bit 13 re-checked at P0 and A2PRE. Immediately before the unmask (PREUNMASK snapshot,
             taken AFTER the install): INTSR bit 13 == 1; INTMR bit 13 == 0; handler installed with
             record count 0; CONTROL vote == exp (0x8C); IRQ with both readings equal, at least one
             even source bit set (0x0555 mask — 0x0400 or 0x0500 as observed, not required exactly),
             odd bits 0 and bit 15 0 as A2 wrote them; raw[32] kept. Anything else →
             abort_pre_unmask_state (cause_lost / intmr13_unmasked / control_changed /
             irq_state_unexpected): no unmask, teardown.

Sequence:
  boot → PRESENT gate → AR_INFO[5:3] := 3 → PI preconditions → BASE → CONTROL := (v & ~0x10) | 0x0C
  → P0 → A1PRE → A1: IRQ := read | 0x8000 → A1-0, +50 µs, +500 µs → A2PRE → A2: IRQ := 0
  → A2-0, samples with INTSR polling up to 2000 ms, PI MASKED — exactly 003A
  → no cause within the bound: NO unmask → teardown → no_cause_within_tmax (valid evidence)
  → EVENT (first INTSR bit 13 = 1): snapshot as 003A; the window ends
  → IRQ_Request(IRQ_PI_HSP, oneshot): previous handler kept, record cleared; rc ≠ ok →
    abort_handler_install, no unmask
  → PREUNMASK: PI (two samples), CONTROL raw/semantic, IRQ raw/semantic → preconditions above
  → t_unmask := time base → __UnmaskIrq(IM_PI_HSP) → t_post_unmask := time base → PI (UNMASKPOST)
    [the exception is taken when __UnmaskIrq restores EE: the handler may run before the call
     returns, t_post_unmask is then already after it]
  → wait for record.fired up to T_DELIVERY, polling the record only (no DMA, no formatting)
  → __MaskIrq(IM_PI_HSP) (idempotent with the handler's own mask) → copy the record → INTMR bit 13
    must read 0 (else __MaskIrq again + anomaly flag)
  → PREACK: PI (two samples), CONTROL raw/semantic, IRQ raw/semantic       [pre-device-ack]
  → device ACK (fired path only): irq_pending := IRQ semantic (GBI vote, must equal the Disc
    reading, else abort_transport-class stop without the ACK); ack := irq_pending | 0x8000;
    IRQ := ack, u16 replicated — derived from the read, never hard-coded (0x8400 / 0x8500 expected)
  → POSTACK: PI (two samples), CONTROL, IRQ
  → if INTSR bit 13 == 1: ONE main-loop INTSR := 0x2000 + one re-read (main W1C budget spent)
  → teardown, PI masked: CONTROL := original → IRQ read → stop := read | 0x8AAA → IRQ := stop →
    IRQ read → CLEANUPCHK: if INTSR bit 13 == 1 and the main budget is unspent, ONE INTSR := 0x2000
    + re-read, else sticky recorded → IRQ_Request(26, old) → mask state verified (masked) →
    AR_INFO original → FINAL → screen: POWER CYCLE REQUIRED
  not fired within T_DELIVERY: __MaskIrq → PI read (did INTMR bit 13 become 1? is INTSR bit 13
    still 1?) → delivery_timeout (abort_unmask if INTMR bit 13 never became 1) → no device-ACK
    step (the stop word acknowledges the pending sources) → teardown as above.

ISR (gbp_irq_oneshot.h extended; audited by tools/isr_audit.py; PI MMIO and 32-bit stores only;
no DMA, no GBP access, no formatting, no allocation, no blocking, no loop except one fixed-count
time-base read):
   1. t_entry := time base        2. intsr_at_entry := INTSR      3. intmr_at_entry := INTMR
   4. count++                     5. __MaskIrq(IM_PI_HSP)         6. intmr_after_mask := INTMR
   7. INTSR := 0x2000 (once)      8. intsr_after_w1c := INTSR
   9. fixed ≈100-tick (2.5 µs) time-base read loop → t_second := time base; intsr_second := INTSR;
      intmr_final := INTMR
  10. first entry publishes its fields, then fired := 1; a second entry (anomaly) re-masks, does NOT
      write INTSR again, stores its INTSR/INTMR/time view in reentry fields; return.
  MASK → W1C order mandatory (R3). ISR W1C per run: exactly 1.

Level/pulse discriminator (U-GBP-022): at step 7 the device source (0x0400 / 0x0500) is still
  pending — nothing has acknowledged the device. intsr_after_w1c and intsr_second with bit 13 = 0,
  and PREACK bit 13 = 0 → the W1C clears the latched cause while the device source stays pending:
  compatible with a pulse/edge-latched cause or with a line deasserted independently of the
  source latch — NOT a proof of pulse. Bit 13 = 1 again at step 8, step 9 or PREACK (before the
  device ACK) → strong evidence of a level/re-asserting line. Both outcomes are valid; INTMR bit
  13 is 0 from step 5 on, so no second delivery can occur either way.

W1C policy (PI INTSR := 0x2000), auditable: ISR exactly 1; main loop at most 1 per run, at the
  first point where INTSR bit 13 reads 1 while masked — after the device ACK (POSTACK), otherwise
  at CLEANUPCHK — never both, never repeated; a bit still set after its W1C is recorded (sticky)
  and left to the power cycle. Maximum 2 per run.

Order ACK / CONTROL restore / STOP: ISR → PREACK → device ACK under CONTROL 0x8C → POSTACK → (main
  W1C) → CONTROL restore → STOP word → …  GBI acknowledges under the running CONTROL in its thread
  and never changes CONTROL during service; the Disc's handler acknowledges with CONTROL
  unchanged; both restore CONTROL 0x10 only at stop. "Restore before ACK" has no precedent.

GBI (GBP-IRQ-003/004): raw handler INTSR := 0x2000 → LWP_SemPost; thread: read IRQ → AUDIO/VIDEO/
  SIO reads → 64-byte write KEYPAD + IRQ := read | 0x8000 → CONTROL/SIOCTL read → IRQ := 0 → wait.
  Kept: PI W1C first in the handler; device ACK = read | 0x8000 (IRQ half only, u16 layout).
  Deliberately dropped: INTMR left open (003B masks first, one-shot), thread/semaphore, KEYPAD
  write, AUDIO/VIDEO/SIO reads, IRQ := 0 re-enable after the ACK (003B goes to the stop word).
Start-up Disc (GBP-IRQ-002): handler IRQ := shadowB | 0x8000 (device first) → INTSR := 0x2000 →
  read IRQ → write pending back → callbacks → IRQ := shadowB. A device-first write would
  acknowledge/hold the device before the PI W1C and blur the discriminator: 003B keeps GBI's
  PI-first handler order and the Disc's stop word; the Disc's mask-first stop discipline is already
  ours (ISR masks first, main stays masked). No element of the Disc order adds safety here.

T_DELIVERY:  100 ms (4 050 000 ticks) — a software margin, not a hardware property (002 measured the
             unmask call itself at 33 ticks; a latched cause is expected to be delivered inside the
             call). The cause window before it stays 003A's 2000 ms operational bound.

Statuses:    ok_delivery_observed; delivery_timeout (not a transport error); no_cause_within_tmax
             (not a transport error); abort_not_present; abort_inconsistent; abort_pi_precondition
             (start / P0 / A2PRE); abort_control_read; abort_control_shape; abort_irq_shape;
             abort_transport; abort_handler_install; abort_pre_unmask_state; abort_unmask (INTMR
             bit 13 never became 1 and nothing fired); anomaly_reentry (count > 1: best-effort
             teardown, power cycle, no repeat before analysis). Restore reported per step as in
             003A plus handler_restored, mask_ok, isr_pi_w1c, main_pi_w1c, main_pi_w1c_site.

Records:     count, fired, t_entry, t_unmask, t_post_unmask, latency ticks/µs, intsr_at_entry,
             intmr_at_entry, intmr_after_mask, intsr_after_w1c, t_second, intsr_second,
             intmr_final, reentry_intsr/intmr/t; PREUNMASK, UNMASKPOST, PREACK, POSTACK, stop,
             cleanup and FINAL snapshots with raw[32] and both readings; device ACK value and
             buffer; W1C sites. No formatting inside the ISR; the main loop formats only after
             re-masking; the 003A window keeps its no-formatting region.

Writes (complete): AR_INFO bits 3–5 (restored); TEST handshake; CONTROL transform and restore; IRQ
             register: A1 read | 0x8000, A2 0, device ACK read | 0x8000 (fired path only), stop
             read | 0x8AAA — four call sites of gbp_regwrite_irq_u16 (three used in the timeout
             path); INTMR only through __UnmaskIrq (once) and __MaskIrq (ISR, main, teardown);
             INTSR W1C: ISR 1 + main ≤ 1. Never: KEYPAD, VIDEO, AUDIO, SIOCTL, SIODATA, BBA, a
             direct INTMR store.

Properties to test automatically when implemented: unmask count = 1, only after the install and
             only with INTSR bit 13 = 1 observed; ISR mask before W1C (isr_audit) and exactly one ISR
             W1C; main W1C ≤ 1; INTMR stores = 0; handler installs = 1, restores = 1, restored
             handler == previous; IRQ write sites = 4; no KEYPAD/VIDEO/AUDIO/SIO access; no DMA
             while unmasked (mock invariant); the physical 003A fixture drives the probe verbatim
             up to the EVENT and stops at the install (no "I" lines) — regression of the replica.

Delivery counts as validated iff: fired = 1, count = 1, t_entry − t_unmask small and bounded,
             intmr_at_entry bit 13 = 1 and intmr_after_mask bit 13 = 0 (mask-first proven in the
             handler), intsr_at_entry bit 13 = 1, exactly one ISR W1C, INTMR bit 13 = 0 in every
             main read afterwards, device ACK completed with a consistent read-back (pending sources
             cleared, bit 15 = 1), handler restored, restore = ok. The level/pulse readings are
             observations, never pass/fail.
Still missing afterwards for a functional initialization: repeated service (ACK → IRQ := 0 → next
             cause) without losing causes; KEYPAD writes (both references write it on every
             service); CONTROL 0x04/0x08 at runtime (U-GBP-006); AUDIO/VIDEO DMA (Phases 4/6); a
             runtime-order unmask (source-to-delivery latency); a cartridge present (bit 2); sleep
             and serial sources.
Risks:       a storm if the mask-first order failed (mitigated: audited ISR, __MaskIrq physically
             proven, GBP-HW-022); a level line re-latching after the ISR W1C (no CPU effect, INTMR
             masked); device masks open with bit 15 = 1 between the ACK and the stop (~1 ms, GBI's
             steady state); a second source arriving between EVENT and unmask (allowed); every write
             has physical precedent (A1/A2/stop in 003A; the ACK is A1's form). Power cycle mandatory.
Physical setup: identical to GBP-INIT-003A. Not to be requested before implementation, audits and a
             clean candidate.
```

### GBP-INIT-004 — bounded repeated HSP service: acknowledge, local re-arm, next cause, next delivery (designed 2026-09-15; implemented 2026-09-15; executed 2026-09-16 — see "Executed tests" above)

Status: **PHYSICALLY EXECUTED 2026-09-16** (build initirq4-0001, commit
741630b, DOL sha256 `1da0d7b4…010c`; result above: one cycle delivered and
acknowledged, `anomaly_source_not_cleared` at POSTACK-0, **no re-arm
written**, evidence GBP-HW-042…047, GBP-IRQ-009). The clean build of
741630b was audited (PHYSICAL CANDIDATE READY, DEVLOG 2026-09-16
"GBP-INIT-004 release audit") and executed once; no second run of this
design is requested — the successor GBP-AV-SERVICE-001 (drained service,
below) replaces the clean-boundary premise; GBP-INIT-004B (below) stays
optional, not scheduled. The paragraph below is the
pre-execution status kept for the history. Pre-execution status:
IMPLEMENTED — NOT PHYSICALLY EXECUTED. DIRTY BUILD — NOT A PHYSICAL
CANDIDATE (DEVLOG 2026-09-15 "GBP-INIT-004 implemented"). The
design below is the specification; the implementation lives in
`poc/gbp-init-irq-service-probe/` (Test ID `GBP-INIT-004`, Build ID
`initirq4-0001`, gecko prefix `OPENGBP-INITIRQ4` — the provisional names
`initsvc-0001` / `OPENGBP-INITSVC` of the design entry were replaced by the
implementation request), `src/gbp/gbp_initirq4_probe.{h,c}`,
`src/gbp/gbp_irq_service.{h,c}` (the 003B cycle service extracted
verbatim; the 003B probe calls it and its physical fixture still pins every
record byte for byte), `src/gbp/gbp_irq_oneshot.h`
(`gbp_irq_multicycle_service`: generation wrapper around the unchanged
003B body), `src/platform/hsp_backend_irq_multi.{h,c}` (linked instead of
`hsp_backend_irq.c`), mock / replay (`I p <gen>`, optional) / probelog
(`PREPARE`, `REARM t_rearm`, `NEXTCAUSE t_end`) / audit profile `004`
extensions. The dirty build of 2026-09-15 (commit `23990c9-dirty`, DOL
sha256 `da19add0add883cf79c03bc1310b48adcac193cb3109f58cc025f39959ca0ef4`,
397280 bytes) exists for review only: it must never reach the hardware. No
physical GBP-INIT-004 fixture exists; the physical 003B fixture drives
cycle 0 of the 004 logic up to its POSTACK (cut before the CONTROL restore,
the first re-arm meets an exhausted script: the physical prefix ends before
the first re-arm variable, `rearms 0/1` is a synthetic boundary, never
evidence of a re-arm) and nothing after it is invented. The first cycle is
semantically equivalent to 003B at the protocol level (same device
transactions in the same order up to the POSTACK), not a byte-identical
handler. Implementation notes against this design: (a) the statuses
`abort_read_inconsistent` (Disc ≠ GBI at a per-cycle read) and
`cycles_completed_with_errors` (every cycle completed but restore /
transport / uncertainty not clean — the causal criterion below is never
reduced to "count == 3") were added; `delivery_timeout` carries its cycle
in the reason; (b) the generation is published with the last PI read as
the INTMR evidence (EVENT for cycle 0 — `IRQ_Request` cannot change INTMR,
ENV-IRQ-002 — REARMPOST / NEXTCAUSE afterwards), the two PREUNMASK samples
re-check it before any unmask; (c) REARMPOST classifies A/B/C/D/E and a
sixth case F (PI bit 13 = 1 with no source visible → `anomaly_rearm_state`),
and a NEXTCAUSE poll that saw bit 13 with no AV source is the same anomaly
(`nextcause_pi_without_source_cycle_N`); (d) the teardown variants are
labelled `TEARDOWN4 variant=` (`final_cycle`, `S2_before_unmask`,
`S3_cycle_aborted`, `S4_rearm_failed`, `S4A_rearmed_no_next_cause`,
`S4B_next_cause_latched`, `S4C_rearmpost_invalid`, `stage_a`); (e) on the
linked handler GCC duplicated the entry sequence (time base, PI reads,
count++, `__MaskIrq`) into the in-range and the out-of-range slot paths —
two `__MaskIrq` call sites, both before the single INTSR store; the audit
profile pins that count and the listing was inspected by hand; (f) the
executed 003B binary `d3da8cd` had the ACK call site in
`gbp_initirqb_probe.o`; rebuilt 003B binaries have it in `gbp_irq_service.o`
(profile `003b` updated) — they are not the executed binary either way.
Validation of the dirty build (host only): `tests/unit/test_gbp_initirq4.c`
3210 checks (C suite 7949 in 10 binaries, 003B still 1107 with its
physical fixture), Python 145 passed, `isr_audit` CLEAN on
`hsp_backend_oneshot_isr_multi` (107 instructions, one INTSR store of
0x2000 at 0x11c after the mask calls, no INTMR store, bounds check before
the slot arithmetic, `fired` stored last), `poc_audit --profile 004` 0
findings (5 IRQ-register write sites: A1/A2/STOP, ACK, REARM), 13 Dolphin
runs PASS with the OSD override (the two 004 runs end in the stage-A
aborts, never reaching a write, the install or the multi-cycle path),
the synthetic log → fixture → replay round trip identical. Depends on GBP-INIT-003B (executed:
GBP-HW-035…041, GBP-PI-005, ENV-IRQ-003, GBP-IRQ-008), GBP-INIT-003A,
GBP-INIT-002 and the reference service loops re-read from the binaries
on 2026-09-15 (GBI worker thread `0x8000bf30`, raw handler `0x8000b400`,
IRQ write helper `0x80015da0`; Start-up Disc handler `0x8008af08`, start
`0x8008bf84`, stop `0x8008be04`, mask-word builder `0x8008bcc4`;
decompiles under `build/analysis/`, never committed).

```text
Question:    After a real HSP cause has been delivered and serviced (ISR mask + PI W1C, device
             acknowledge IRQ := read | 0x8000) and the device has been re-armed with GBI's write
             IRQ := 0, does the GBS-DOL produce a NEW cause that is captured, delivered and serviced
             again — repeatedly, without a storm, without a lost cause and without accumulated
             state — and how long after the re-arm does the next cause arrive?
Not asked:   the first delivery (FACT, GBP-PI-005); the semantics of the sources, the masks, the
             W1C (FACT, GBP-IRQ-008); AUDIO/VIDEO/SIO data, KEYPAD, cartridge, callbacks, a runtime.
Why static analysis cannot answer: both references re-arm with bit 15 = 0 and wait unmasked; no
             reference reads the PI or the device between the re-arm and the next cause; the
             cadence of the requests and the effect of IRQ := 0 on a source that re-set since the
             acknowledge (003B: within ≤ 143 µs) exist only on the hardware.

Reference loops as re-read from the binaries (FACT, code):
  GBI thread 0x8000bf30, per pass (INTMR bit 13 open throughout; the first pass runs before any
  interrupt, GBP-IRQ-004):
    LWP_SemWait ← posted by the raw handler 0x8000b400 (INTSR := 0x2000, one PI W1C per interrupt,
      nothing else)
    → read IRQ (32 bytes at D00000; pending = vote(bytes ≡1 mod 4) << 8 | vote(bytes ≡3 mod 4))
    → dispatch on the value read: 0x0400 ARQ read AUDIO, 0x0100 ARQ read VIDEO, 0x0040 ARQ read
      SIODATA, 0x0010 64-byte KEYPAD write 0x0304/0x0300
    → ONE 64-byte write at CFFFE0: KEYPAD := pad state, IRQ := pending | 0x8000     (device ACK)
    → 64-byte read at 4FFFE0: CONTROL, SIOCTL (votes)
    → optional SIODATA write from a message queue
    → 64-byte write at 4FFFE0: CONTROL := value read (write-back), SIOCTL := value read (| 0x80)
    → video frame bookkeeping (RAM)
    → 32-byte write IRQ := 0 at D00000                                                (re-arm)
    → back to LWP_SemWait
  Exit: __MaskIrq(0x20) → IRQ_Free(26) → CONTROL := (read & 0xE3) | 0x10; no IRQ write.
  Facts used: (a) IRQ := 0 is the LAST device access of every pass, after the ACK, after the
  CONTROL/SIOCTL write-back; it is the step that returns the register to the waiting state
  (odd bits 0, bit 15 0); (b) the only PI W1C per interrupt is the raw handler's, taken before
  the thread runs; (c) CONTROL is written every pass with the value just read (write-back, no
  change); (d) KEYPAD is written every pass inside the ACK DMA; (e) immediately before waiting:
  IRQ = 0x0000, CONTROL as read (0x8C), INTMR bit 13 = 1, INTSR bit 13 = 0 unless a new event
  arrived during the pass (then the raw handler runs again at once and the thread loops).
  Start-up Disc handler 0x8008af08, per interrupt (EE = 0, DMAs under OSDisableInterrupts):
    IRQ := shadowB | 0x8000 (shadowB = odd bits of slots WITHOUT callback, 0 in the normal flow)
    → INTSR := 0x2000 → read IRQ → if pending & 0x0555: IRQ := pending (write-back = ACK),
      KEYPAD := pad, read CONTROL, callbacks (audio slot 4, video slot 5; a non-zero return
      suppresses the re-arm) → IRQ := shadowB (re-arm, bit 15 := 0) unless suppressed → return.
  Start 0x8008bf84: OSUnmaskInterrupts(0x20) FIRST, then read IRQ, IRQ := (read & ~shadowA) |
  shadowB (shadowA = 0x8000 | odd bits of slots WITH callback = 0x8AAA normally → IRQ := 0x0004
  from 0x8AAE: bit 15 and the odd bits cleared, the pending bit 2 written back), CONTROL |= 0x04,
  CONTROL &= ~0x10. Stop 0x8008be04: OSMaskInterrupts(0x20) → CONTROL &~4, &~8, |0x10, |0x80 →
  IRQ := read | shadowA → INTSR := 0x2000 → previous handler back.
  Common protocol (CORROBORATED by two independent implementations): PI W1C once per interrupt
  and before the re-arm; device ACK = write back the sources read (GBI with bit 15 = 1, the Disc
  after having set bit 15 at entry); bit 15 = 1 during the service, re-arm = bit 15 := 0 with
  the odd bits as the wait state (GBI 0, Disc shadowB); the Disc keeps bit 15 = 1 ("suppress")
  when an AV ring is full — bit 15 as a hold while servicing is the consistent reading of both
  drivers (still HYPOTHESIS physically, U-GBP-007). Both wait with INTMR bit 13 OPEN.

Choices of this experiment and why:
  Sources policy (AV-only continuation): this POC implements the service semantics of no source.
    The steady-state cycles may CONTINUE only on the two sources the drivers treat as the
    audio/video requests: AV_SOURCE_MASK = 0x0500 (0x0400, 0x0100, or both = 0x0500, in any
    order). At every point where the IRQ register is read after A2 (NEXTCAUSE-n, PREUNMASK-n,
    PREACK-n, POSTACK-n, REARMPOST-n) the probe computes
    `unexpected = irq & (0x0555 & ~0x0500)`; if it is not 0 (game pak 0x0004, sleep 0x0010,
    serial 0x0040, user 0x0001 — sources whose functional meaning this POC does not implement),
    the run keeps raw[32] and the PI/CONTROL/IRQ snapshot, records the source, and ends in the
    safe teardown: no unmask if no delivery of that cycle has happened yet, no REARM if it was
    seen after a delivery. Status anomaly_unexpected_source, reason unexpected_source_cycle_N.
    Not a transport failure and not an "invalid" source: it may be perfectly valid hardware
    behavior, only outside the scope of this experiment. The rule applies to the SERVICE causes
    after A2 and after every REARM; the initialization state is exempt: BASE 0x8AAE with the idle
    bit 2 set, A1 = read | 0x8000 acknowledging it (physically validated), A2 = 0 — the known
    physical path BASE 8AAE → A1 8AAA → A2 0000 → AV cause is kept verbatim.
  Order per cycle: ISR (mask → one PI W1C) → main re-mask → PREACK → device ACK `read | 0x8000`
    → POSTACK (clean boundary, below) → PI clean (≤ 1 main W1C, only if INTSR bit 13 reads 1) →
    REARM `IRQ := 0` → REARMPOST → masked wait for the next cause → PREUNMASK → unmask → ISR.
    Causal boundary of cycle N: delivery → ACK → POSTACK with the acknowledged AV sources gone →
    PI bit 13 = 0 → t_rearm → IRQ := 0  |  → new source / new PI bit 13 → t_next_cause → cycle
    N+1. A cause counts as evidence of the re-arm only if every step before the bar was
    established and t_next_cause > t_rearm; otherwise the run ends without crediting it. GBI's order for the
    ACK/re-arm pair (ACK first, re-arm last); the Disc's principle "PI cleared before the re-arm"
    (both references) → option A of the design question: guarantee INTSR bit 13 = 0 before the
    REARM, so that any bit 13 seen afterwards is a NEW cause. The Disc's entry write
    `shadowB | 0x8000` (hold first) is not reproduced: it would put a device write before the PI
    W1C and blur the 003B discriminator; GBI's order was physically validated in 003B.
  REARM formula: `IRQ := 0x0000`, u16 replicated 16× (32 × 00) — byte-identical to A2 (physically
    validated write) at a different point of the protocol (after an ACK, sources possibly pending).
    Logged as its own record kind (REARM / IRQW tag=REARM), never called A2 after cycle 1.
  CPU stays MASKED between cycles (INTMR bit 13 = 0 from the ISR's mask until the next PREUNMASK):
    causality and the 003B safety strategy are kept (unmask only with a latched cause, delivery
    inside __UnmaskIrq, one entry per cycle). Difference from the runtime (both references wait
    with the mask open and take the cause as it happens): documented, not a claim about the
    runtime; the measured re-arm-to-cause interval is unaffected (the PI latches while masked).
  Cycle 1 = the 003B path verbatim (CONTROL 0x8C → A1 → A2 → masked window → CAUSE → install →
    PREUNMASK → unmask → ISR → PREACK → ACK → POSTACK): no new variable before the first
    delivery. The new variables enter only after the first ACK: REARM, masked wait, next cause.
  MAX_CYCLES = 3 delivered causes (fixed constant): cycle 1 = the validated first delivery,
    cycle 2 = the first re-arm, cycle 3 = the re-arm repeated once (distinguishes "works once"
    from "works again"); REARMS = 2 (after cycles 1 and 2; none after cycle 3, so the run ends
    in 003B's acknowledged state and its validated teardown). 2 cycles cannot show repetition of
    the re-arm; 4 adds one more unmask window and no new question.
  Handler: ONE install for the whole run (option A): `IRQ_Request(26, multicycle)` after the first
    latched cause, restored at the teardown; the audited one-shot body of 003B is kept
    byte-for-byte for the first entry of each cycle (t_entry → INTSR → INTMR → count → __MaskIrq →
    INTMR → INTSR → one W1C → INTSR → ≈100-tick wait → t_second → INTSR → INTMR → fired) and
    wrapped by a slot selector. Generation semantics (unambiguous): cycles are indexed
    0…MAX_CYCLES−1; `records[i]` is write-once — zeroed at the install while masked, never reused,
    never cleared afterwards; `expected_gen` (the slot the next entry must use) is published by
    the main loop ONLY while INTMR bit 13 = 0, and is never changed while IRQ 26 could enter;
    the ISR reads `expected_gen` exactly once at entry and uses only that slot; a generation
    out of range → the anomaly slot (mask, entry state, NO W1C) → anomaly_reentry with reason
    generation_error; a slot already fired → the body's reentry branch (mask, reentry fields, NO
    W1C) → anomaly_reentry; `completed_cycles` is a COUNT (cycles whose slot was fired, copied
    by the main loop, acknowledged, and — for cycles 1 and 2 — re-armed and validated), not an
    index: the next `expected_gen` (= completed_cycles) is published only after cycle N was
    consumed by the main loop, with the CPU still masked, after POSTACK-N passed its boundary
    conditions, after the PI was verified clear and after REARM-N was executed and validated;
    `entries_total` counts every entry for reporting only and is never a decision input. The
    second ≈100-tick read stays (no new variable in an audited object; one more level/re-assert
    sample per cycle at no cost).
  Preconditions before EVERY unmask (cycle N; abort, never adjust): for N ≥ 1 the cause is
    later than the corresponding t_rearm (t_next_cause > t_rearm, wrap-safe); INTSR bit 13 = 1 in
    both PI samples; INTMR bit 13 = 0 in both; CONTROL vote = 0x8C and = byte 0x1F; IRQ readings
    equal; `irq & 0x0500` ≠ 0 and `irq & (0x0555 & ~0x0500)` = 0 (AV sources only, any of 0x0100 /
    0x0400 / 0x0500, never a fixed order); odd bits 0; bit 15 0; bits 12–14 0; `records[N]` clean
    (count 0, fired 0); expected_gen = N = completed_cycles. Failure → abort_pre_unmask_state with
    the cycle index and reason (an unexpected source → anomaly_unexpected_source instead); no
    unmask; teardown.
  PI W1C budget: ISR exactly 1 per delivered cycle (per slot, enforced by the body); main ≤ 1 per
    cycle, only at POSTACK-N if INTSR bit 13 reads 1 while masked, then ONE re-read; still 1 →
    anomaly_pi_sticky_after_ack, NO REARM, teardown (so that any bit 13 seen after `IRQ := 0`
    belongs to an occurrence later than the re-arm boundary, never to the previous cycle's
    latch); never at REARMPOST (a bit 13 there is the next cause, not garbage); teardown: the
    003A CLEANUPCHK budget of 1. Absolute maximum per run: 2 × MAX_CYCLES + 1 = 7, each site
    guarded by a flag, no loop.
  REARM-N is executed only after the clean boundary: POSTACK-N AV sources cleared, INTSR bit 13 =
    0 (after at most one main W1C), INTMR bit 13 = 0, CONTROL 0x8C, CPU masked, no reentry, no
    unexpected source. `IRQ := 0x0000` u16 replicated; t_rearm := the time base read immediately
    before the write; attempted/completed recorded.
  REARMPOST-N at once: time base, PI INTSR/INTMR (two samples), CONTROL raw + semantic, IRQ raw +
    semantic. Required to CONTINUE: CONTROL = 0x8C, INTMR bit 13 = 0, Disc = GBI reading, odd bits
    0, bit 15 0, bits 12–14 0. NOT required: IRQ source bits = 0 — a source that re-set since the
    ACK survives a write of 0 (W1C needs 1) and a new AV request may arrive immediately. Valid
    outcomes: (A) sources 0, INTSR bit 13 = 0 → start the masked wait; (B) AV source(s) ≠ 0 and
    INTSR bit 13 = 1 → a practically immediate cause: t_next_cause := REARMPOST's time base,
    NEXTCAUSE-N = this snapshot (the strongest bit-15-hold evidence, U-GBP-007: sources pending,
    odd bits 0, CONTROL 0x8C constant, only bit 15 changed 1 → 0); (C) AV source(s) ≠ 0 and INTSR
    bit 13 = 0 → preserved, keep polling the PI within T_NEXT_CAUSE, no mechanism assumed;
    (D) any source outside AV_SOURCE_MASK → anomaly_unexpected_source, teardown; (E) odd bits or
    bit 15 not 0, bits 12–14 set, CONTROL changed → anomaly_rearm_state, teardown (best-effort
    STOP with the current readback, no second re-arm). In (A)/(C) the poll that sees bit 13 gives
    t_next_cause and a NEXTCAUSE-N snapshot (PI, CONTROL, IRQ) as 003A's EVENT; the AV-only rule
    is applied to that snapshot too. No cause within T_NEXT_CAUSE → no_next_cause (cycle N; valid
    evidence: the re-armed device produced no request — the AV blocks are never consumed here,
    so a stream that stalls after unconsumed blocks would show exactly this), no unmask, teardown.
  CONTROL: 0x8C for the whole run; read at every snapshot; never written between the transform
    and the final restore (GBI's per-pass write-back writes the value it read — a no-op in value
    — and is not reproduced: no new write). A vote ≠ 0x8C at any cycle snapshot →
    anomaly_control_changed (cycle N), teardown (which restores the original value as always).
  KEYPAD, AUDIO/VIDEO/SIODATA reads, SIOCTL: not touched (never written/read so far; 003B showed
    the sources re-setting without any of them). Accepted deviation from both references,
    documented; KEYPAD belongs to Phase 5.
  Device ACK-N: read IRQ (PREACK-N, both readings must agree, else the ACK is skipped and the
    cycles stop; an unexpected source here → anomaly_unexpected_source, no ACK, teardown);
    ack := pending | 0x8000; u16 replicated; attempted before the call, completed on rc ok;
    exactly ONE ACK per cycle, never repeated. Failure → no REARM, abort_transport
    ack_write_failed (cycle N), teardown, power cycle.
  POSTACK-N as a clean boundary: read IRQ, read PI (two samples). REARM is allowed only if: ACK
    completed; Disc = GBI reading; CONTROL = 0x8C; INTMR bit 13 = 0; no reentry in the slot; the
    main re-mask confirmed; and the acknowledged AV source bits are gone — `irq & 0x0555` = 0
    (physically what 003B showed: 0x0500 → write 0x8500 → read back 0x8000). Source bits still
    set → anomaly_source_not_cleared, reason source_pending_after_ack_cycle_N, NO REARM, teardown
    (no second ACK); an unexpected source → anomaly_unexpected_source. Then the PI: INTSR bit 13 =
    1 → the cycle's single main W1C and one re-read; still 1 → anomaly_pi_sticky_after_ack, NO
    REARM. REARM-N: attempted/completed, readback; failure → no further unmask, abort_transport
    rearm_write_failed, teardown.
  Bit 15 as a by-product only: ACK-N leaves bit 15 = 1 (read back), REARM-N writes it 0 (read
    back), the next cause arrives with bit 15 = 0; the REARMPOST/NEXTCAUSE readings under a
    constant CONTROL 0x8C are the isolation U-GBP-007 lacked. No isolated bit-15 write.

Timeouts (operational bounds, never hardware properties):
  T_CAUSE_FIRST = 2000 ms after A2 (003A/003B: 105.27 / 105.29 ms);
  T_DELIVERY    = 100 ms after each unmask (003B: inside the call, 78 ticks);
  T_NEXT_CAUSE  = 500 ms after each REARM (003B: sources re-set ≤ 143 µs after the ACK; a
                  4096 Hz audio tick or a 60 Hz frame are both ≪ 500 ms; 2000 ms would only
                  lengthen the masked wait of a failing cycle). Worst-case run ≈ 2 + 3×0.1 +
                  2×0.5 = 3.3 s of experiment.

Statuses:    ok_cycles_completed (MAX_CYCLES delivered and acknowledged, REARMS re-arms, teardown
             ok); no_initial_cause (= 003B's no_cause_within_tmax, no install, no unmask);
             no_next_cause (cycle N: REARM done, no cause within T_NEXT_CAUSE; not a transport
             error); delivery_timeout / abort_unmask (cycle N, as 003B); abort_pre_unmask_state
             (cycle N + reason: read_failed / record_not_clear / generation_mismatch /
             cause_lost / intmr13_unmasked / control_changed / semantic_disagree /
             irq_state_unexpected / cause_before_rearm); anomaly_unexpected_source (cycle N,
             reason unexpected_source_cycle_N: a source outside AV_SOURCE_MASK at a service
             read — observed, preserved, not serviced; no unmask / no REARM); anomaly_reentry
             (cycle N; a fired slot re-entered, or generation_error for a generation out of
             range; no further cycle); anomaly_mask_failure (cycle N);
             anomaly_source_not_cleared (cycle N, reason source_pending_after_ack_cycle_N; one
             ACK only, no REARM); anomaly_pi_sticky_after_ack (cycle N; no REARM);
             anomaly_rearm_state (cycle N: odd bits / bit 15 / bits 12–14 / CONTROL wrong at
             REARMPOST; no unmask, best-effort STOP); anomaly_control_changed (cycle N);
             abort_transport (ack_write_failed / rearm_write_failed / read failures, cycle N);
             the 003A-stage aborts by their own names. None of the anomalies is a transport
             failure. Every status ends in the teardown.

Teardown at every point (CPU masked first in every case — the ISR's mask, the main re-mask,
  then MASKCHK with one retry; the local re-arm never left open):
  S0 stage-A abort (no CONTROL write): 003A teardown (AR_INFO only).
  S1 A1/A2 done, no initial cause: CONTROL restore → IRQ read → STOP := read | 0x8AAA (read = 0 →
     0x8AAA: the Disc's formula with nothing pending; supported by the field semantics — odd bits
     and bit 15 level-written, even bits written 0 are no-ops — and by the physical stop words
     0x8FAA/0x8FAA; the exact word 0x8AAA has not been written yet) → CLEANUPCHK → AR_INFO → FINAL.
  S2 cycle N delivered, before its ACK (reentry / mask failure): no ACK, no REARM → 003B teardown
     (the STOP word acknowledges the pending sources) → CLEANUPCHK (≤ 1) → handler restore →
     MASKCHK → AR_INFO → FINAL.
  S3 ACK-N done, before REARM-N (source not cleared / unexpected source after the delivery /
     sticky PI / control changed): bit 15 = 1, odd bits 0, sources as read → CONTROL restore →
     IRQ read → STOP := read | 0x8AAA (closes the odd bits; acknowledges whatever is pending,
     including a source this POC does not service) → as S2. No second ACK, no REARM.
  S4a REARM-N completed, IRQ still 0, no cause within T_NEXT_CAUSE: device armed (odd bits 0,
     bit 15 0) → CPU masked (already) → CONTROL restore → IRQ read = 0 → STOP := 0 | 0x8AAA =
     0x8AAA (the Disc's formula with nothing pending; supported by the field semantics — S1
     argument) → CLEANUPCHK (bit 13 expected 0; if a cause latched meanwhile: one W1C) → handler
     restore → MASKCHK → AR_INFO → FINAL.
  S4b REARM-N completed and a new source appeared (AV, PI latched or not) but no unmask happened
     (pre-unmask abort, cause before t_rearm, no_next_cause with a source pending, or an
     unexpected source after the re-arm): device: sources pending, armed; PI: bit 13 = 1 or 0,
     INTMR bit 13 = 0 → CONTROL restore → IRQ read → STOP := read | 0x8AAA (acknowledges and
     closes the source(s)) → CLEANUPCHK: bit 13 = 1 while masked → ONE W1C, re-read, sticky
     recorded → handler restore → MASKCHK → AR_INFO → FINAL (the Disc's stop order: device write,
     then INTSR := 0x2000). No unmask, no re-arm.
  S4c REARM-N read back an invalid state (anomaly_rearm_state): best-effort STOP with the current
     readback (`read | 0x8AAA` on whatever was read; if the read failed, 0x8AAA alone as 003A's
     rule), no second re-arm, no unmask, then as S4b. No ACK loop anywhere.
  S5 all cycles done (after ACK-3, POSTACK-3 boundary passed, no REARM): identical to 003B's
     validated teardown.
  Every path: power_cycle_required = 1 from the first experimental attempt, never cleared.

ISR (gbp_irq_oneshot.h, new multicycle wrapper around the unchanged extended body; audited by
  tools/isr_audit.py: only __MaskIrq callable, exactly one INTSR store of 0x2000 after the
  mask, no INTMR store, loops allowed; no DMA, no GBP access, no formatting, no allocation, no
  callbacks, no semaphores):
   gen := expected_gen (volatile read) ; entries_total++
   if gen < MAX_CYCLES: gbp_irq_oneshot_service_ext(&records[gen])   — first entry of the slot:
        the 003B sequence with its single W1C; a second entry of the same slot: mask, reentry
        fields, no W1C
   else: gbp_irq_oneshot_service_ext(&anomaly_slot) — same body, same guarantees
   return. Main reads records[gen] only after its own __MaskIrq and MASKCHK.

Records per cycle (fixed array in RAM, no allocation): cycle index; t_cause / t_next_cause
  (poll that saw bit 13), IRQ semantic at the cause, since_rearm and since_prev_cause;
  PREUNMASK snapshot (PI × 2, CONTROL, IRQ); t_unmask, t_post_unmask, latency; the slot's
  record (entry INTSR/INTMR, INTMR after mask, INTSR before/after the W1C, t_second, second
  INTSR/INTMR, count, reentry fields); REMASKCHK; PREACK snapshot; irq_pending, ack value,
  attempted/completed; POSTACK snapshot and its boundary verdict (av_cleared, unexpected,
  pi_clear); main W1C (site, sticky); t_rearm, REARM attempted/completed, REARMPOST snapshot
  (IRQ readback, CONTROL, PI × 2) and its outcome (A–E); the unexpected source value and the
  site where it was seen, if any; per-cycle timeouts. Run totals: cycles requested/completed
  (count), causes, deliveries, acks, rearms, boundaries established, reentries, unexpected
  sources, timeouts, ISR W1C, main W1C.

Log records (per cycle, short lines, raw[32] kept for every CONTROL/IRQ read): CYCLE start n=,
  CAUSE n= (cycle 1) / NEXTCAUSE n= t_next_cause= since_rearm= since_prev= irq= intsr= intmr=,
  SNAP tag=PREUNMASK-n (+ PI ×2, RAW ×2), PREUNMASK n= ok= reason=, PREPARE n= gen=,
  UNMASK n= t_unmask= t_post=, PI tag=UNMASKPOST-n, IRQ mask tag=MAIN n=, WAIT n=, PI
  tag=REMASKCHK-n, HANDLER n= …, HANDLERPI n= …, HANDLERPI2 n= …, DELIVERY n= …, SNAP
  tag=PREACK-n (+ PI ×2, RAW ×2), PREACK n= …, ACK n= before= ack_value=, IRQW tag=ACK-n …,
  SNAP tag=POSTACK-n, POSTACK n= … av_cleared= unexpected= boundary_ok=, MAINPICLEANUP n=
  site=POSTACK performed=, REARM n= t_rearm= value=0000, IRQW tag=REARM-n …, SNAP
  tag=REARMPOST-n (+ PI ×2, RAW ×2), REARMPOST n= irq= av= unexpected= odd= bit15= intsr13=
  outcome=A|B|C|D|E, UNEXPECTED n= site= irq= (raw block kept in the RAW record of that
  snapshot) …; end: CYCLES requested= completed= causes= deliveries= acks= boundaries= rearms=
  unexpected= reentry= sticky= timeouts= isr_w1c= main_w1c=, plus the 003A/003B end records
  (TEARDOWN with the
  real pi_policy label, WRITES, OBSERVED, RESTORE, ACKS, RESTOREB, FINAL). A REGION record per
  masked wait proves nothing was formatted inside it. Replay: the fixture grammar gains one
  optional line `I p <gen>` (PREPARE → the generation handed to the backend while masked); `I u`
  per cycle carries that cycle's slot record (the fixture generator already stops the record
  search at the next UNMASK).

Timing observations (individual values, no statistics beyond min/max with 2–3 samples, never a
  hardware specification): per cycle latency t_entry − t_unmask; dt_second; PREACK − t_entry;
  t_rearm − t_ack; **t_next_cause − t_rearm** (the new measurement: immediate vs. one request
  period); cause-to-cause interval; the first cause after A2 (third data point for U-GBP-014).

Writes (complete): the 003B set (AR_INFO bits 3–5 + restore; TEST handshake; CONTROL transform +
  final restore; IRQ A1, A2, ACK per cycle, STOP) plus REARM `IRQ := 0` after cycles 1 and 2 —
  IRQ-register write call sites: 3 (003A stage) + 1 (ACK) + 1 (REARM) = 5; INTMR only through one
  __UnmaskIrq per cycle (3 calls of one call site) and __MaskIrq; INTSR W1C: ISR 1 per delivery +
  main ≤ 1 per cycle + teardown ≤ 1. Never: KEYPAD, VIDEO, AUDIO, SIOCTL, SIODATA, BBA, a direct
  INTMR store, CONTROL between transform and restore.

Properties to test automatically when implemented: one install, one restore, restored handler ==
  previous; unmask count == deliveries ≤ MAX_CYCLES, each only after its own latched cause and
  PREUNMASK; ISR mask before W1C and exactly one W1C per delivered slot (isr_audit + mock);
  main W1C ≤ 1 per cycle; INTMR stores 0; IRQ write sites 5; REARM never before the cycle's ACK
  completed, never with a source bit still set at POSTACK, never with INTSR bit 13 = 1, never
  after an unexpected source; a cause with t_next_cause ≤ t_rearm never credited; no unmask on
  a non-AV source; one ACK per cycle; expected_gen written only while INTMR bit 13 = 0 and only
  after REARM validation; completed_cycles a count; no DMA while unmasked (mock invariant); no
  cycle beyond MAX_CYCLES; teardown from every state S0–S5 (S4a/b/c); the physical 003B fixture
  as the prefix up to its ACK/POSTACK (the run then diverges: REARM instead of the stop — the
  fixture ends there, replay stops cleanly at the first REARM as "unanswered" → abort_transport
  in the test, no line invented); mock scenarios: immediate cause at REARM (B), delayed cause
  (fixed delay, jittered), source pending at REARM without a PI bit (C), no cause after REARM
  (no_next_cause), unexpected source at the first cause / at NEXTCAUSE / at REARMPOST / at
  POSTACK / at PREACK (each: observed, no unmask or no REARM, teardown), source not cleared by
  the ACK, PI re-latch after ACK (cleared by the one W1C, and sticky), REARM state anomaly (odd
  bits or bit 15 read back 1), generation error, reentry in cycle 1/2/3, control change in
  cycle 2, ACK/REARM failures per cycle, delivery timeout in cycle 2, ring overflow, worst-case
  line widths with three cycles, wrapping time base across cycles.

Validation criteria (fixed in advance): `ok_cycles_completed` requires, all together: 3 valid
  deliveries (count 1 per slot, entries_total = 3, zero reentry); 2 complete boundaries
  ACK → POSTACK with the AV sources cleared → PI bit 13 = 0 → REARM read back with bit 15 = 0
  and odd bits 0; 2 subsequent causes each attributable in time to its own REARM (t_next_cause >
  t_rearm, within T_NEXT_CAUSE) and delivered after a clean PREUNMASK; zero unexpected sources
  at every service read; zero sticky PI; zero transport uncertainty (every write attempted =
  completed); CONTROL 0x8C at every cycle snapshot; INTMR bit 13 = 0 in every main-loop read;
  no PI W1C beyond the budget; handler restored; restore = ok. This is a causal criterion, not
  "count == 3". The timing values and the bit-15 readings are observations. no_next_cause in
  cycle 2 or 3 is a valid result (it would mean the device stops requesting when its blocks are
  not consumed — decisive for Phase 4's design), not a failure of the mechanics already
  validated; so is anomaly_unexpected_source (a source this POC does not service appeared).

Phase-3 closure criterion (proposed): if GBP-INIT-004 validates as above, the fundamental
  initialization and interrupt mechanics of the GBP path are closed (detection, AR_INFO,
  CONTROL start/restore, source W1C, local masks, cause generation, PI capture, CPU delivery,
  mask-first service, PI W1C, device ACK, local re-arm, repeated delivery, stop, restore) and
  Phase 4 (VIDEO) may start on the 004 service loop: reading the VIDEO block on 0x0100 is the
  next variable. Not required before Phase 4: the exact function of bit 15 (follow the
  references' pattern: 1 while servicing, 0 while waiting), the nature of the device line
  (U-GBP-022, P2), the byte-0/offset-2 patterns, KEYPAD (Phase 5), CONTROL 0x04/0x08 (U-GBP-006;
  the transform already sets them), AUDIO (Phase 6), SIO (Phase 10), a cartridge (Phase 7).
Risks:       a storm if the mask-first order failed in any cycle (mitigated: audited body, three
             physical entries expected); a level line held with the CPU masked (no effect); a
             cause lost between the ISR W1C and the ACK (one PI cause covers several device
             events — the ACK acknowledges all pending sources; recorded, not a loss for the
             device); the device stalling without AV consumption (valid result); the sleep (0x0010),
             game-pak (0x0004), serial (0x0040) or user (0x0001) sources appearing at a service
             read (observed and preserved, never serviced: anomaly_unexpected_source, teardown,
             the stop word acknowledges them); every write has physical precedent (0x0000 = A2,
             `read | 0x8000` = A1/ACK, `read | 0x8AAA` = stop); power cycle mandatory.
Physical setup: identical to GBP-INIT-003B; ≈ 3.5 s worst case; X to save, START, power off. Not
             to be requested before implementation, audits and a clean candidate.
```

### GBP-INIT-004B — pending-source re-arm: `IRQ := 0` with an AV source still pending, PI clear and the CPU masked (designed 2026-09-16; OPTIONAL, not scheduled — superseded as the next step by GBP-AV-SERVICE-001 the same day; NOT implemented, NOT released)

Status: design only, **OPTIONAL and not scheduled** (decision DEVLOG
2026-09-16 "next step after GBP-INIT-004 decided": the drained service
probe GBP-AV-SERVICE-001, below, is the next step; 004B would test a state
neither reference enters — a re-arm with an unconsumed block — whose
negative outcome would be ambiguous and whose positive outcome would
mainly characterize bit 15, which blocks nothing; kept as a later bit-15
experiment if ever needed); no code, no build, no hardware, no request.
The original design text follows unchanged. Successor of GBP-INIT-004 (executed
2026-09-16: one cycle delivered and acknowledged, POSTACK-0 read 0x8400
with CONTROL 0x8C and PI clear, the clean boundary "sources == 0" stopped
the run before any re-arm — GBP-HW-045). Depends on GBP-INIT-003B and 004
(GBP-PI-005, GBP-IRQ-008/009) and on the reference loops re-read on
2026-09-16 (both drain the block before the re-arm and never read the IRQ
register after the ACK; INITIALIZATION.md §13).

```text
Question:    With an AV source still pending in the IRQ register after the acknowledge (as the
             hardware showed 26 µs after IRQ := read | 0x8000: 0x8400, bit 15 = 1, masks 0, CONTROL
             0x8C, PI INTSR bit 13 = 0), does GBI's re-arm IRQ := 0 (bit 15 -> 0, masks 0) turn that
             pending source into a new HSP request — at once (a hold released), at the source's next
             event (~ms), or not at all within the bound (the drain is what re-arms)? And does the
             same installed handler then service the next cycle?
Not asked:   the first delivery (FACT ×2); whether the ACK clears or the source re-asserts within 26 µs
             (U-GBP-028, not blocking); the cadence of the requests; AUDIO/VIDEO data (no DMA of the
             blocks: that is design B, the Phase-4 entry); KEYPAD, cartridge, callbacks, a runtime.
Why static analysis cannot answer: neither reference re-arms with a source known to be pending
             (both drain first) and neither reads the register or the PI between ACK and re-arm.
What changes against GBP-INIT-004 (everything else verbatim: stage, handler, generation discipline,
             PREUNMASK per cycle, delivery, main re-mask, PREACK, ACK = read | 0x8000, W1C budget,
             teardown variants, power cycle):
  POSTACK acceptance (the "boundary"): ACK completed; Disc == GBI; CONTROL == 0x8C; CPU masked
             and INTMR bit 13 = 0; zero reentry; PI INTSR bit 13 = 0 after at most the cycle's one
             main W1C; bit 15 = 1; odd masks 0; bits 12–14 = 0; the pending sources, if any, are a
             subset of AV (0x0100 / 0x0400 / 0x0500); unexpected (irq & 0x0555 & ~0x0500) == 0.
             POSTACK may therefore read 0x8000 (clean) OR 0x8100 / 0x8400 / 0x8500 (AV pending under
             the bit-15 hold). "source == 0" is NOT required. A source outside AV, a sticky PI, a
             CONTROL change, a reentry or a mask failure abort as in 004.
  REARM-n (cycles 0 and 1 only): t_rearm -> IRQ := 0x0000 (u16 replicated), attempted/completed as
             004; then REARMPOST-n exactly as 004 (PI ×2, CONTROL, IRQ; no W1C): A quiet / B latched /
             C source-before-PI / D unexpected / E invalid / F PI-without-source.
  NEXTCAUSE-n: CPU still masked; INTSR polled ≤ T_NEXT_CAUSE = 500 ms (operational); a valid next
             cause needs INTSR13 = 1 AND an AV source present AND unexpected == 0 — a source without
             the PI latch does not count, a PI latch without a visible AV source is F. The next cause
             is classified `rearm_of_pending_source` when an AV source was already pending at
             POSTACK/REARMPOST, `new_source_occurrence` only when POSTACK read 0x8000 and REARMPOST A;
             it counts as a REARM CAUSE when t_hsp > t_rearm (wrap-safe), INTSR13 = 1 and an AV source
             is present. It is NOT required that the source appeared after the re-arm.
  Then: prepare(n+1) -> PREUNMASK-(n+1) -> unmask -> delivery -> ACK, as 004.
Records added: POSTACK boundary=pending_av|clean, NEXTCAUSE class=rearm_of_pending_source|
             new_source_occurrence, t_hsp - t_rearm per cycle (individual, no statistics), the
             POSTACK value per cycle.
Statuses:    as 004, with anomaly_source_not_cleared removed from the normal path (it survives only
             for a non-AV source, i.e. anomaly_unexpected_source); ok_cycles_completed requires 3
             deliveries, 3 ACKs, 2 completed re-arms, 2 REARM CAUSES each after its own t_rearm, zero
             unexpected / reentry / sticky PI / uncertain, transport ok, CONTROL 0x8C at every
             per-cycle check, restore ok. no_next_cause after a re-arm (500 ms) is a VALID physical
             result ("a pending source is not re-requested by the re-arm alone") and is reported as
             such, not as a failure; so is a cause only at the next event (latency in ms).
Safety envelope: CPU masked during ACK, re-arm and the wait (INTMR bit 13 = 0 verified before the
             re-arm and never opened before PREUNMASK-(n+1)); no source outside AV serviced; one
             re-arm per boundary; no PI W1C after the re-arm before the cause is observed (budget as
             004: ISR 1 per delivery, main ≤ 1 at POSTACK, none at REARMPOST/NEXTCAUSE, teardown ≤ 1);
             PREUNMASK mandatory for every cycle; MAX_CYCLES 3 / MAX_REARMS 2; no DMA of AUDIO/VIDEO;
             no unbounded loop; STOP best-effort read | 0x8AAA on every path; power cycle mandatory.
             If PI INTSR bit 13 is already 1 before the re-arm (after the cycle's one main W1C): do
             NOT re-arm, do not count causality, abort with cleanup (anomaly_pi_sticky_after_ack).
Teardowns:   S3 (abort inside a cycle before the re-arm), S4A (re-arm completed, no cause in 500 ms:
             STOP = read | 0x8AAA from whatever the register shows — 0x8AAA from 0, 0x8EAA from
             0x0400, etc. — reference-backed), S4B (cause latched, abort before the unmask: no ACK of
             the new cause, STOP = current | 0x8AAA), S4C (REARMPOST invalid), final (after cycle 2,
             no re-arm) — all as 004, all with the CPU masked first.
Validation criteria: the causal chain per re-arm: delivery(n) < ACK(n) < POSTACK(n) accepted <
             PI clean < t_rearm(n) < IRQ:=0 < t_hsp(n) < prepare(n+1) < unmask(n+1); the value of
             t_hsp - t_rearm is the observation (µs / ms / none); the runtime consequence is derived
             from it (drain before re-arm, or event-driven re-request) — no periodicity from one run.
Physical setup: identical to GBP-INIT-004; ≈ 3.5 s worst case; X to save, START, power off. Not to
             be requested before implementation, host tests (mock scenarios for every boundary
             outcome: clean, pending AV, non-AV, sticky PI; the physical 004 fixture as the prefix up
             to POSTACK-0 with the boundary marked), audits and a clean candidate.
```

### GBP-AV-SERVICE-001 — first drained HSP service: read the pending AUDIO/VIDEO blocks, acknowledge, re-arm, observe the next cause (Phase 4 entry; designed 2026-09-16; implemented 2026-09-16; executed 2026-09-16 — see "Executed tests" above)

Status: **PHYSICALLY EXECUTED 2026-09-16** on the clean candidate
`d3a6d23` (DOL sha256
`d9e6dccd6f6ac2a729cc1be904214dbaf6f0bd88ee2929244b185a5ba39556ff`;
release audit and build materialization of 2026-09-16, PHYSICAL CANDIDATE
READY) — result `ok_service_rearm_cause_observed`, `restore=ok`, one run:
see "Executed tests — GBP-AV-SERVICE-001" above (log and sidecar verbatim,
evidence GBP-HW-048…060, GBP-IRQ-010; Phase 3 COMPLETE). Implementation
history: DEVLOG 2026-09-16 "GBP-AV-SERVICE-001 implemented", "micro-audit",
"sidecar / cache audit", "release audit"; the earlier dirty builds
(`5ed9d93-dirty`) never reached the hardware. The implementation lives in `poc/gbp-av-service-probe/` (Test ID
`GBP-AV-SERVICE-001`, Build ID `avsvc-0001`, gecko prefix `OPENGBP-AVSVC`),
`src/gbp/gbp_avsvc_probe.{h,c}` (the probe: statuses, teardowns, the
service pass), `src/gbp/gbp_avblock.{h,c}` (one raw block: whole-block read
through the transport, summary, records), `src/gbp/gbp_avdump.{h,c}` (the
block sidecar), `src/gbp/gbp_crc32.{h,c}`, the transport's `read_bulk`
operation (`src/gbp/gbp_transport.h`) with its real backend
(`src/platform/hsp_backend.c`: the same DMA routine as every 32-byte
access with a length parameter; `DCFlushRange` before, `DCInvalidateRange`
after), the shared service's split ACK step
(`gbp_irq_service_ack_write_postack`: the 003B / 004 records unchanged,
pinned by their physical fixtures), the mock's bulk model, the replay's
`B` line, `tools/probelog.py` rules, `tools/avdump.py`, `tools/poc_audit.py`
profile `avsvc`, `sdlog_save_blob`. Implementation notes against the
design below: (a) the handler is the 003B extended one-shot installed once
(a second delivery is forbidden by design, so no generation wrapper — the
004 multi-cycle object is not linked); (b) PRESVC is the single
authoritative snapshot: the block set and the ACK value derive from it and
never from a later read (a source appearing during a drain is observed at
POSTDRAIN and never added to the pass — the references' single read); (c)
POSTDRAIN was added as an observation-only snapshot with the mandatory
consistency checks (a source outside AV there means no ACK); (d) the drain
failure statuses are named per source and per cause (`audio_dma_busy`,
`audio_dma_timeout`, `audio_dma_error`, the VIDEO three), VIDEO is never
started after a failed AUDIO read, `drain_uncertain` marks a timeout; (e)
`abort_presvc_state`, `anomaly_postack_shape` and
`anomaly_pi_sticky_after_service` name the PRESVC / POSTACK / PI-clean
deviations; `anomaly_source_not_cleared` does not exist; (f) the records
are `SVC start`, `AUDIOREAD`, `VIDEOREAD`, `SVCEND`, `POSTDRAIN`,
`POSTACKAV`, `PICLEAN`, `REARM`, `REARMPOST`, `NEXTCAUSE`, `TEARDOWNAV`,
`SERVICE`, `COUNTERS`, `BLOCK` / `BLOCKW`, `TIMING`, `RESTOREAV`, `AVSVC`
(the DUMP record of the design became the `SAVEBLOCKS` gecko line and the
on-screen status: the sidecar is written on X, after the run); (g) the
sidecar format is fixed and documented in `src/gbp/gbp_avdump.h` (format
version 2 after the micro-audit of 2026-09-16: magic `OGBPBLK1`, 256-byte
big-endian header with four 32-byte identity fields — Test ID, Build ID,
app, commit, 1..31 printable ASCII characters each, never truncated —
pending mask, lengths, per-block CRC-32, rc and timings, the two blocks, a
`OGBPEND1` footer with a total CRC-32) — a block never read has length 0; (h) the
physical 003B and 004 fixtures, cut before their device ACK, drive the
probe up to its PRESVC reads (the physical PREACK values) and its drain
then meets a transport without whole-block reads (`abort_bulk_unavailable`);
since the run, the physical fixture
`hw-gamecube-gbp-2026-09-16-avsvc-0001.gbpreplay` with its sidecar replays
the whole pass to the physical result. The design text follows unchanged
(the "Expected result" below was met: see the executed entry). Pre-implementation status: design only. The scheduled
successor of GBP-INIT-004; it replaces GBP-INIT-004B (above, now optional)
as the next physical experiment and is the entry experiment of Phase 4
(ROADMAP: "recorded hardware trace replay" and "buffer boundaries" start
with the first physically captured VIDEO block). Depends on GBP-INIT-003B
and 004 (GBP-PI-005, GBP-IRQ-008/009) and on the reference service loops
(INITIALIZATION.md §4 and §13; decompiles re-read 2026-09-16: GBI
`0x8000bf30` with `0x8000be48` / `0x8000bea4` / `0x80011c14` and the ARQ
`0x80061a68` / `0x800617b4` / `0x80061820` / `0x80061b3c`; Disc `0x8008af08`
with `0x8008cdc4` / `0x8008a764` / `0x8008a654` / `0x8008ed68` / `0x8008a480`
/ `0x8008b14c` / `0x80089c3c` / `0x80089cc8` / `0x80089ff4` / `0x8008a31c`).

Name: **GBP-AV-SERVICE-001**, not GBP-VIDEO-001 — with no cartridge both
AV sources are pending at the first delivery (0x0500 in 003B and 004) and
a VIDEO-only drain would leave the AUDIO block unconsumed, i.e. exactly the
untested pending-source re-arm of 004B; not GBP-SERVICE-001 — only the two
AV sources are serviced (a source outside 0x0500 is observed, never
serviced). GBP-VIDEO-001 stays reserved for the first VIDEO-content
experiment of Phase 4 (frame structure, with a cartridge). There is no
intermediate phase: this is the Phase 4 entry, and it carries the re-arm
validation that Phase 3 left open.

```text
Question:    After the validated delivery of an HSP cause, does ONE reference-style service pass —
             read IRQ (pending), drain every pending AV block with one whole-block DMA each (AUDIO
             0x1000 at base+0x800000, then VIDEO 0xF00 at base+0x100000: GBI order), ACK `IRQ :=
             pending | 0x8000`, re-arm `IRQ := 0x0000` — lead to a NEW PI HSP cause with a valid AV
             source within a bound, with the CPU masked throughout and no second delivery?
             Secondary: the raw content of the two blocks (length, DMA duration, CRC32, byte
             windows, whole bytes in a binary dump) preserved for the host, not interpreted.
Not asked:   the first delivery (FACT ×2); the meaning of the block bytes (U-GBP-008/011/012:
             recorded raw only); the cadence of the requests (one interval only, U-GBP-014); the
             re-arm with an unconsumed block (004B, optional); whether the drained block can be
             read a second time; KEYPAD, SIO, cartridge, BBA, rendering, playback, a second service.
Why static analysis cannot answer: both references drain and re-arm without reading the register
             back; whether the re-arm after a drain produces the next cause, and how soon, is
             hardware behavior. Why Dolphin cannot: its model re-sets the cause on every device
             event and ignores the masks (HSP.md §4); its blocks are model data.
Source mapping (revalidated): 0x0100 → VIDEO block (index 0x1, 0xF00) and 0x0400 → AUDIO block
             (index 0x8, 0x1000) is FACT in both reference codes (GBP-IRQ-005: Disc slot table
             0x0400 → 0x8008cdc4 → 0x8008a764 (base+0x800000, 0x1000), 0x0100 → 0x8008ed68 →
             0x8008a480 (base+0x100000, 0xF00); GBI `pending & 0x400` → 0x800000/0x1000, `& 0x100`
             → 0x100000/0xF00). On hardware only the OCCURRENCE is FACT: 0x0400 first, 0x0100 ≤ 1 ms
             later (GBP-HW-030/035/042) — the order of appearance says nothing about which block is
             which. The probe reads, for each bit, the block the references read for that bit, and
             never infers a mapping from timing.
Blocks (revalidated, GBP-VID-001 / GBP-AUD-001, REGISTERS.md §2): AUDIO = index 0x8 = base +
             0x800000, 0x1000 bytes; VIDEO = index 0x1 = base + 0x100000, 0xF00 bytes; both
             multiples of 32; direction ARAM → main memory (`0xCC005028` bit 15 = 1, the Disc's
             `0x80089c3c(buf, base+off, len, 1)`, `AR_StartDMA` dir 1); destination a 32-byte-
             aligned main-memory buffer, cache-invalidated (Disc `0x800687dc(buf, len)` before the
             DMA and again in the completion callback; GBI: ARQ). Both references issue ONE DMA of
             the whole length: the Disc programs `len` and polls `0x80089cc8` (1 s bound); GBI
             posts at priority 1 = the hi queue, whose service `0x800617b4` starts `AR_StartDMA`
             with the request's full length — the chunking of `0x80061820` (lo queue, chunk
             `0x3380`) is never used for GBP accesses (HSP.md §3 "chunk size 0x3C0" to be made
             precise). Reading a block as 120 / 128 separate 32-byte DMAs is not reference
             behavior and is not done.
GBI pass order (`0x8000bf30`, FACT code): SemWait → read IRQ (32 B at 0xD00000, voted) → set bit 15
             in the local copy → if 0x0400: post async AUDIO read (hi queue, callback 0x8000b75c)
             → if 0x0100: post async VIDEO read (callback 0x8000a8e0) → if 0x0040: SIODATA read →
             if 0x0010: KEYPAD 0x0304 / 0x0300 → SYNCHRONOUS 64-byte write at 0xCFFFE0 (KEYPAD :=
             pad state, IRQ := pending | 0x8000): it enters the same FIFO behind the block reads
             and its busy-wait (`0x80061b3c`, state == 2) returns only after it completed, so every
             drain is complete before the ACK completes → sync 64-byte read CONTROL + SIOCTL →
             optional SIODATA write → sync CONTROL + SIOCTL write-back → sync `IRQ := 0` (last
             device access) → loop. PI HSP stays unmasked (the raw handler only W1Cs and posts);
             the register is never re-read after the ACK; bit 15 is 0 during the drain (the
             previous pass ended with 0) and 1 from the ACK to the re-arm.
Disc order (`0x8008af08`, FACT code): `IRQ := shadowB | 0x8000` → PI W1C → read IRQ → write-back
             `IRQ := pending` (the ACK, BEFORE any drain) → KEYPAD → CONTROL read → slot 4
             (0x0400): when 0x0100 is pending as well (`0x801b34ca[4]` = 0x0100) the AUDIO block is
             read SYNCHRONOUSLY (`0x8008a654`: DMA + polled wait + message), otherwise
             asynchronously (`0x8008a764`, completion callback, return 1 suppresses the immediate
             re-arm) → slot 5 (0x0100): VIDEO read asynchronously (`0x8008a480`, callback, suppress)
             → `IRQ := shadowB` only when nothing is in flight; otherwise the ARAM-DMA-done
             handler `0x8008b14c` runs the completion callback (invalidate + message) and writes
             the re-arm. The Disc, too, orders AUDIO before VIDEO, never has two block DMAs in
             flight, and re-arms only after the LAST block DMA completed; bit 15 is 1 from the
             entry write to the re-arm. Under 0x0500 the whole service is the audio DMA (polled),
             the video DMA (interrupt) and the re-arm at video DMA done.
Strategy:    A — GBI-like: drain → ACK → REARM. Both references complete the drain before the
             re-arm; they differ only in whether the ACK precedes (Disc) or follows (GBI) the
             drain. A is chosen because (1) it keeps the 004 sequence ACK → POSTACK → REARM →
             REARMPOST → NEXTCAUSE unchanged and only inserts the drain before the ACK; (2) after
             a drain the ACK's W1C acts on consumed blocks, so the POSTACK read is a free data
             point for U-GBP-028; (3) the ACK value is the pre-drain read in both references. The
             physical 004 result (0x0400 present 26 µs after an ACK without drain, with bit 15 =
             1, PI clear) is what the Disc order lives with; it is not an argument against B, only
             against "sources == 0". Recorded deviations from GBI: the CPU stays masked from the
             delivery to the end (observability); the ACK is the 32-byte IRQ-only write of 003B /
             004, not GBI's 64-byte KEYPAD + IRQ write (KEYPAD untouched); CONTROL is read, not
             written back; SIOCTL / SIODATA untouched.
Sequence:    Stage A verbatim from 004 (detection, A1, A2 `IRQ := 0`, handler install, PREUNMASK-0,
             unmask, delivery through the audited multi-cycle handler, main re-mask + REMASKCHK);
             then SERVICE-0 with the CPU masked (INTMR bit 13 = 0 verified before every device
             write; T_DELIVERY 100 ms as 004):
  PRESVC     read IRQ (Disc and GBI readings must agree) → pending; read PI, CONTROL. Accept:
             (pending & 0x0555) ≠ 0; (pending & 0x0555 & ~0x0500) = 0 — else
             anomaly_unexpected_source: observed, nothing drained, teardown S3; odd bits 0, bit 15
             0, bits 12–14 0 (A2 wrote 0 and nothing wrote since) — else abort_presvc_state,
             teardown S3; CONTROL 0x8C — else anomaly_control_changed, teardown S3.
  AUDIOREAD  if pending & 0x0400: ONE DMA ARAM → MRAM, base+0x800000, 0x1000 bytes, into
             audio_raw[0x1000] (static, 32-byte aligned, zero-filled, flushed and invalidated
             before, invalidated after); completion by polling DSP CSR bit 5 with the existing
             backend rules (refuse if bit 9 or bit 5 is already set; T_DMA = 200 ms per transfer,
             operational — the Disc bounds at 1 s; clear bit 5 afterwards); t_start, t_end, polls,
             CSR before / after recorded.
  VIDEOREAD  if pending & 0x0100: the same with base+0x100000, 0xF00 bytes, into video_raw[0xF00].
             AUDIO then VIDEO as both references; one transfer per pending source, no retry, no
             second read of either block in this run; nothing else touches ARAM meanwhile
             (libogc AR / ARQ never initialized).
  SVCEND     every transfer completed (rc ok, no timeout, no busy refusal, CSR consistent) — else
             transport_failure_during_drain (audio_dma_failed | video_dma_failed): no ACK, no
             re-arm, teardown S3-DMA.
  ACK        `IRQ := pending | 0x8000` (u16 replicated ×16, one 32-byte write at base+0xD00000),
             pending = the PRESVC value, never a re-read: GBI writes `pending | 0x8000`, the Disc
             writes back the value it read; both use the pre-drain read. Attempted = completed
             required (else ack_write_failed: no re-arm, teardown S4-ACK).
  POSTACK    PI ×2, CONTROL, IRQ (observation; NO source requirement): accept CONTROL 0x8C; bit
             15 = 1; odd 0; bits 12–14 0; (irq & 0x0555 & ~0x0500) = 0; INTMR bit 13 = 0; zero
             reentry; INTSR bit 13 = 0 after at most ONE main W1C — a bit 13 = 1 here is recorded
             as relatch=1 (a cause latched during the service with bit 15 = 0, something GBI's
             unmasked design tolerates), cleared once, re-read; still 1 → anomaly_pi_sticky_
             after_ack, no re-arm, teardown S3-PI. The AV bits read anything: boundary=clean
             (0x8000) or pending_av (0x8100 / 0x8400 / 0x8500) — both accepted, both recorded
             (the U-GBP-028 data point after a drain). anomaly_source_not_cleared does not exist
             in this design.
  REARM      precondition: INTSR bit 13 = 0 and INTMR bit 13 = 0 on a fresh read; `IRQ := 0x0000`
             (GBI's value; u16 replicated), t_rearm; then REARMPOST exactly as 004 (PI ×2, CONTROL,
             IRQ; no W1C): A quiet / B PI latched with an AV source / C source present without PI
             / D unexpected source / E invalid read-back (odd bits or bit 15 read 1) / F PI without
             a source. E, D and F end the run (anomaly_rearm_state / anomaly_unexpected_source,
             teardown S4C).
  NEXTCAUSE  CPU still masked; INTSR polled (no W1C) ≤ T_NEXT_CAUSE = 500 ms (operational); on bit
             13 = 1: read IRQ once (src1) and CONTROL, t_hsp. Valid next cause iff INTSR bit 13 = 1
             AND (src1 & 0x0500) ≠ 0 AND (src1 & 0x0555 & ~0x0500) = 0 AND t_hsp > t_rearm (wrap-
             safe); B at REARMPOST counts, with t_hsp = the REARMPOST sample; C then a latch counts
             from the poll that saw bit 13. The cause is NOT unmasked, NOT delivered, NOT
             acknowledged: the run ends here (teardown S4B). No cause in 500 ms → S4A.
Cycles:      MAX_CYCLES 1, MAX_REARMS 1, deliveries 1: one full service + one re-arm + the
             observation of the next cause; no second delivery (the second cause stays latched and
             is acknowledged only by the teardown's PI W1C, after the stop word). Repeated,
             sustained service is the experiment after this one.
Data capture: audio_raw / video_raw are never modified after their DMA (raw evidence). After the
             timed region (teardown done, interrupts back to normal): CRC32 of each buffer,
             zero-byte count, distinct-value count, four 32-byte windows per block (offsets 0,
             0x20, the middle 32 bytes, the last 32 bytes), for VIDEO the first 32-bit word and the
             result of GBI's frame-start test `(w0 & 0x80800000) == 0x80800000` recorded as a raw
             flag (GBI's test, not a claim); then the text log to SD (ringlog → sdlog) and a
             binary dump `<test_id>_<build_id>.bin` (16-byte header: magic "OGBPBLK1", audio
             length, video length, flags; then audio_raw, then video_raw) written by a new sdlog
             blob function after the log file, never inside the timed region. No block bytes in
             the ringlog beyond the windows; no formatting inside the timed region; the on-screen
             summary shows both CRC32s so a failed SD write still leaves a checkable value. The
             fixture derived on the host: the `.gbpreplay` script plus a `-blocks.bin` sidecar
             (device output with no cartridge — not proprietary), SHA-256 of the raw log and of
             the dump computed on the host from `logs/`.
Records:     SVC start irq= pi= control= t=; AUDIOREAD addr=01800000 len=1000 rc= ticks= polls=
             csr_before= csr_after= t_start= t_end=; VIDEOREAD addr=01100000 len=0f00 (same
             fields); SVCEND drained= transfers= t_end=; ACK value= rc= t_after= (as 004);
             POSTACK … boundary=clean|pending_av relatch=0|1 (as 004 minus the source rule);
             PICLEAN n=; REARM value=0000 rc= t_rearm=; REARMPOST class= irq= pi= control=;
             NEXTCAUSE found=1 t_hsp= dt_rearm= irq= control= | found=0 t_end=; BLOCK
             kind=audio|video len= crc32= zeros= distinct= w0= w1= wmid= wlast= [first_word=
             gbi_frame_start=]; DUMP file= bytes= rc=; TEARDOWN …; STATS transfers= timeouts=
             busy=; AVSVC end status= …. Every record carries the time-base ticks of its sample;
             dt values are also given in µs (derived on the device from the known time base, the
             ticks stay primary).
PI policy:   CPU (INTMR bit 13) masked from the ISR's mask to the end; INTSR bit 13 observed after
             the ISR's W1C at PRESVC / POSTACK / REARMPOST / NEXTCAUSE and never delivered; a
             relatch during the service is recorded, not a failure; W1C budget: ISR 1, main ≤ 1 at
             POSTACK, none after the re-arm, teardown ≤ 1; no W1C loop. This is the probe's
             observability policy, not the runtime's (GBI never masks; the Disc services inside
             the handler with the mask untouched).
Statuses:    ok_service_rearm_next_cause (success); no_next_cause_after_service (re-arm completed,
             no cause in 500 ms — a VALID physical result, "one drained service + re-arm does not
             lead to a new request within 500 ms", reported as such, not as a failure); abort_*
             as 004 (stage A, handler install, pre-unmask state, unmask, read inconsistent,
             transport before the drain) plus abort_presvc_state; anomaly_unexpected_source
             (PRESVC / POSTACK / REARMPOST / NEXTCAUSE); transport_failure_during_drain
             (audio_dma_failed | video_dma_failed: timeout, busy refusal, CSR inconsistency);
             ack_write_failed; anomaly_pi_sticky_after_ack; rearm_write_failed;
             anomaly_rearm_state (E / F); anomaly_reentry / anomaly_generation /
             anomaly_mask_failure / anomaly_control_changed as 004;
             service_completed_with_errors (chain complete but restore / transport statistics /
             uncertainty not clean — never reduced to a count).
Success criterion (all together, fixed in advance): first delivery valid (generation 0, one entry,
             mask-first, one ISR W1C, zero reentry); PRESVC AV-only with odd bits 0 / bit 15 0;
             every pending AV block read by one completed DMA of the full length (0x1000 / 0xF00),
             no timeout, no busy refusal, ticks recorded; ACK completed (attempted = completed,
             Disc = GBI); POSTACK accepted (CONTROL 0x8C, PI clean after ≤ 1 W1C, bit 15 = 1, odd
             0, unexpected 0); REARM completed with REARMPOST A or B; a valid next cause within
             500 ms with t_hsp > t_rearm; INTMR bit 13 = 0 in every main-loop read; teardown
             complete, restore ok, transport errors 0, uncertain 0; the two blocks preserved (dump
             written, or CRC32 + windows in the log when the SD write fails). Then the re-arm
             mechanics after a drained service are physically established — U-GBP-027 items (1)
             and (2) for one cycle, (4) as a by-product; (3) cadence and (5) sustained service
             remain — Phase 3 closes, and Phase 4 continues with block interpretation, frame
             timing and repeated service. The value of t_hsp − t_rearm is the observation; no
             periodicity from one interval.
Safety:      CPU masked during the drain, the ACK, the re-arm and the wait; ONE new variable
             class: a whole-block ARAM → MRAM read of 0x1000 / 0xF00 — a read, reference-backed in
             both drivers, on the same DMA engine, the same register programming and the same
             polled-completion routine as every 32-byte access so far; static aligned buffers, no
             allocation; one transfer per source, no retry; T_DMA 200 ms per transfer, never a
             hardware property; no concurrent ARAM access; every device write has physical
             precedent (0x0000 = A2, `read | 0x8000` = A1 / ACK, `read | 0x8AAA` = stop); on any
             DMA failure: no ACK, no re-arm, STOP best-effort, restore, power cycle. A block read
             is a logical consumption in the references (the ACK then clears the status bit); it
             is never assumed destructive or non-destructive — the POSTACK / NEXTCAUSE readings
             are what says whether a drained source re-requests. Not tested here: reading a block
             twice.
Teardowns:   S3 (PRESVC rejected: unexpected source / state / CONTROL — nothing drained, no ACK, no
             re-arm), S3-DMA (a block DMA failed: no ACK, no re-arm), S4-ACK (ACK failed: no
             re-arm), S3-PI (sticky PI at POSTACK: no re-arm), S4C (REARMPOST invalid), S4A
             (re-armed, no cause in 500 ms), S4B (cause latched, not serviced — also the success
             path's teardown); all with the CPU masked first, STOP `read | 0x8AAA` best-effort
             from whatever the register shows, ≤ 1 teardown PI W1C, CONTROL restore, handler
             restore, AR_INFO restore, `power_cycle_required` never cleared.
Host validation before any candidate: mock scenarios (both sources pending / audio only / video
             only; DMA timeout on audio / on video; busy refusal; CSR inconsistency; unexpected
             source at each read; relatch during the service cleared by the one W1C, and sticky;
             REARMPOST A / B / C / D / E / F; no next cause; next cause with and without an AV
             source; ACK / REARM write failures; generation error; reentry; CONTROL change; ring
             overflow; worst-case line widths; wrapping time base; dump write failure); the
             physical 004 fixture as the prefix up to the delivery (cut before PREACK-0, the
             boundary marked — the drain and everything after it are never physical evidence
             before this probe runs); Dolphin execution of the whole path (model blocks, never
             truth; OSD off); isr_audit (handler unchanged from 004), poc_audit profile `avsvc`
             (5 logical IRQ write sites: A1, A2, ACK, REARM, STOP; 2 bulk-read sites; no other
             device write); reproducible build, 0 warnings; clean commit before any candidate.
Physical setup: identical to GBP-INIT-004 (GBP attached, no cartridge, PicoAdapterGB in the Link
             Port untouched, BBA idle, one controller, SD2SP2, Swiss); timed region ≈ 0.7 s worst
             case; X saves the log and the dump; START; power off. Not to be requested before
             implementation, host tests, audits and a clean candidate.
Compatibility: no SIOCTL / SIODATA / KEYPAD / BBA access; CONTROL only the validated transform and
             restore; the physical Link Port and every accessory on it untouched; Start-up Disc /
             GBI parity, rumble / GBP-aware features and the additive virtual Mobile Adapter
             unaffected; nothing of the probe becomes runtime architecture (Phase 4 starts from
             the evidence, not from the POC).
```

Files this design will need when implemented (listed, not created): `src/gbp/gbp_transport.h`
(a bulk read operation: `read_bulk(ctx, aram_addr, out, len, info)` with `len` a multiple of
32 and `out` 32-byte aligned; mock / replay / real implementations; a capability query),
`src/platform/hsp_backend.c` (the same DMA routine with a length parameter and a caller
buffer; cache maintenance over `len`), `src/gbp/gbp_av_service.{h,c}` (the service pass over
the transport: PRESVC → drains → ACK → POSTACK → REARM → REARMPOST → NEXTCAUSE, reusing the
003B/004 records and `gbp_irq_service_ack`), `src/gbp/gbp_avsvc_probe.{h,c}` (statuses,
teardowns, block summaries), `poc/gbp-av-service-probe/` (Test ID `GBP-AV-SERVICE-001`, Build
ID `avsvc-0001`, prefix `OPENGBP-AVSVC`), `src/platform/sdlog.c` (a blob writer for the dump),
mock knobs (per-source block content pattern and DMA duration, failure at transfer n, source
cleared or kept by the drain, relatch during the drain), replay op for a bulk read with the
payload in a `-blocks.bin` sidecar, `tools/probelog.py` rules for the new records and the
sidecar, `tools/poc_audit.py` profile `avsvc`, tests `tests/unit/test_gbp_avsvc.c` and
`tests/host/test_avsvc_replay.py`, Makefile targets `avsvc-dolphin` / `avsvc-audit`. Documents
to update after implementation and after execution: this file (executed entry), EVIDENCE.md
(GBP-HW-048 onwards; the first measured block DMA durations; a `GBP-AV-…` entry for the raw
blocks), UNKNOWNS.md (U-GBP-027 closure or reformulation, U-GBP-028 data point, U-GBP-008 /
011 / 012 first raw data, U-GBP-014 one interval), DEVLOG.md, INITIALIZATION.md (§14: the
service pass; R11 promotion if observed), REGISTERS.md (VIDEO / AUDIO rows: hardware column),
HSP.md (§3: the ARQ hi-queue precision and the first measured bandwidth), captures/README.md
(fixture + sidecar format), tests/README.md, poc/README.md.

### GBP-VIDEO-002 — does the AGB's own logotype screen ever reach the VIDEO stream without a Game Pak? A frame-signature scan over at least the nominal detector interval (Phase 4; designed and hardened four times 2026-09-16; build `vstate-0001` PHYSICALLY EXECUTED 2026-09-16, aborted; build `vstate-0002` PHYSICALLY EXECUTED 2026-09-17, aborted again — with the bytes)

Status: **PHYSICALLY EXECUTED 2026-09-16** (build `vstate-0001`, commit
`e8f3a69`, DOL SHA-256 `c73d49fa…19b9`). Result:

```text
GBP-VIDEO-002 PHYSICALLY EXECUTED
SERVICE ABORTED  — READ SEMANTIC DISAGREEMENT at cycle 51750 (GBP-HW-083)
FRAME CAPTURE VALID UNTIL ABORT — 489 frames, 477 of exactly 40 blocks
STRUCTURED STATE OBSERVED — settled vector matches GBI table B, 40/40 (GBP-HW-080)
RESTORE OK
```

The scientific negative target of 120 s of valid observation was **NOT REACHED**
(5.292 s accumulated), so this run makes **no negative claim**. The positive
objective — locate a structured state — was achieved observationally. The
executed entry and every measurement are in `docs/research/EVIDENCE.md`
(GBP-HW-074…087); the one thing the run could not record is U-GBP-032.

**Build `vstate-0002` — the same experiment, instrumented. PHYSICALLY EXECUTED
2026-09-17** (commit `8cbb28d`, DOL SHA-256 `8661e914…b91b`, log `fb127d79…de2a`
40 013 B, sidecar `f2ed596e…8c91` 12 588 B). Result:

```text
GBP-VIDEO-002 vstate-0002 PHYSICALLY EXECUTED
SERVICE ABORTED — READ SEMANTIC DISAGREEMENT at cycle 517 of 518 (GBP-HW-089)
DIAGNOSTIC OBJECTIVE: SUCCESS — the 32 raw bytes were preserved
  seven replicas 0x0100, the eighth 0x0500; Disc 0x0500 vs GBI 0x0100; XOR 0x0400 = AUDIO
RESTORE OK — the same final device state as every previous run
```

The service failure is **not** a failure of this build's experiment. The build
existed to answer one question — *what did the read that aborts this test
actually return?* — and it answered it on the first attempt, in 0.0842 s. The
scientific target (120 s of valid observation) was not approached and this run
makes **no** negative claim; it also makes no positive claim about the screen,
because it stopped 0.42 s before the change that vstate-0001 recorded. Nothing
here revises the geometry, the table B match or the animation: this run neither
confirms nor contradicts them. Evidence: GBP-HW-088…097. U-GBP-032 is answered;
U-GBP-033 is the mechanism, and it is open.

Operationally the run was clean: 518 unmasks, 518 deliveries, 518 ISR entries,
517 ACKs, 517 re-arms, 513 lean cycles + 4 verify, 336 AUDIO and 195 VIDEO drains
(531 bulk transfers, 2 125 056 bytes), 2 149 transfers, **0 reentry, 0 timeouts,
0 busy, 0 uncertain writes, 0 main-loop W1C, 0 teardown W1C, 0 counter
overflows**. Frame capture up to the abort: 5 frames, 4 complete, 1 incomplete, 2
resync, baseline valid at 0.077 s. Of the 517 completed cycles, 14 served both
sources, 322 AUDIO only and 181 VIDEO only — derived from the bulk counts
(336 + 195 − 517), and the byte total confirms it exactly
(336 × 0x1000 + 195 × 0xF00 = 2 125 056).

**What the previous, pre-execution description said, kept for the history:** The abort above is the only thing standing between this test and its
target, and the run could not say what caused it because the bytes were gone by
the time the probe reported. `vstate-0002` changes exactly one thing: at the
moment a semantic disagreement is detected, the 32 raw bytes already in the
transport's buffer are copied into a 96-byte record, together with the context
that describes that read (both 16-bit values, the read site, the cycle, the
64-bit timestamp, the frame and block position, INTSR at ISR entry and after the
W1C, INTMR at entry, the latency, the transfer's ticks and polls, the DMA status
before and after, and the expected CONTROL shape). One record; the first
disagreement wins; later attempts are only counted.

What did NOT change, and is the reason this build may replace the other in a
physical run without reopening anything already established: the disagreement is
still fatal and still aborts at the same point; there is no retry, no re-read, no
second opinion and no extra device access; the experiment, the caps, the
admission rule, the service cycle, the teardown and the stop precedence are
untouched; the ISR and the whole interrupt path are BYTE-IDENTICAL to the
GBP-VIDEO-001 build that was physically validated (`make vstate-audit` diffs both
one-shot bodies against `build/poc/gbp-video-capture-probe` and reports
"identical"); and a host run with the capture armed produces an operation stream
identical, operation by operation, to one without it. The cost is 96 bytes of
.bss (`struct gbp_vstate` 4 152 → 4 248 bytes; no other store changed) and no
work at all on the normal path — nothing is copied per delivery.

The sidecar carries the record as OGBPSEQ1 **v3**: v2 plus one section, at the
same offsets, under the same CRC, with three header fields taken from v2's
reserved area. v2 is frozen — the physical file of 2026-09-16 parses byte for
byte as it did the day it was consolidated — and the two versions are dispatched
explicitly so neither can read the other's file. `tools/vstate.py diag`
recomputes both readings offline from the preserved bytes and names the replicas
that differ.

That description was written against a dirty build. The physical candidate was
the CLEAN build of commit `8cbb28d`: DOL SHA-256
`8661e91413a2bb7f97bab86b3819813d38128cd033dacae40e68c1664e48b91b`, 433 376
bytes, entry `0x80003100`, reproduced byte-identically by two independent clean
rebuilds and released by the audit of 2026-09-17. The earlier dirty hash
`6f2f6b2c…6fe1` is discarded and must not be used to identify anything.

The pre-execution status paragraph follows, kept for the history:
**IMPLEMENTED 2026-09-16 — NOT PHYSICALLY EXECUTED. DIRTY BUILD — NOT A
PHYSICAL CANDIDATE.** The probe exists (`poc/gbp-video-state-probe/`, Build ID
`vstate-0001`) and passes every host test, audit and Dolphin gate; no hardware
has run it, no physical evidence exists for it, and this entry requests none. A
physical candidate requires a clean commit, a clean rebuild, the audits on that
build, a recorded hash and an explicit authorization (CLAUDE.md §18). The
implementation notes are at the end of this entry. Basis: GBP-VIDEO-001's
physical run (GBP-HW-062…073), the static trace of both references' recognition
machinery (`docs/research/VIDEO_PATH.md` §9) and U-GBP-030 / U-GBP-031.

```text
Question:    GBP-VIDEO-001 observed 39.2 ms of VIDEO — about 2.3 frames — starting 107 ms after the
             CONTROL transform that starts the AGB, and every captured block was uniform apart from
             the frame-start marker. Both references embed a recognisable screen and arm a detector
             for it at session start. So: over an observation at least as long as the nominal
             interval the Disc's own detector spans, in a session WITHOUT a Game Pak, does the VIDEO
             stream ever carry a frame other than the uniform one, and if so when, for how long and
             with what content?
Answers:     U-GBP-031; gives U-GBP-030 a run whose cadence is uniform from the first useful frame;
             and, if a structured frame is captured, the first physical check that the capture
             preserves structure inside a frame at all — with a uniform frame a reordering,
             duplication or loss of blocks is invisible.
Not asked:   colour naming (GBP-VIDEO-003 with a controlled source); rendering on the GameCube;
             KEYPAD writes; audio format; a cartridge.

--- 1. The detector interval: 120 s is a LOWER bound, and why -----------------------------------
The Disc's detector window is 24 000 iterations of the counter at r13-0x7014, incremented once per
invocation of FUN_8008B1AC while the session state is 2 and no completion callback is pending.
FUN_8008A930 registers that function through FUN_80067F24 — which stores its sixth argument as a
period at struct+0x1C and takes its seventh as the callback — with a period computed from the bus
clock at 0x800000F8 as ((bus >> 2) / 125000) * 5000 >> 3 = 202 500 ticks of the 40.5 MHz time base
= **5.000 ms exactly**.
             **There is no catch-up.** FUN_80067C4C, the scheduler insert, explicitly detects a
             deadline already in the past, divides the lateness by the period and advances the next
             fire time by (lateness / period) + 1 periods. Missed periods are DROPPED, never
             replayed. The counter therefore advances at most once per 5 ms.
             Consequences, stated separately so the earlier inversion cannot return:
               * nominal detector interval                    24 000 x 5 ms = **120.000 s**
               * minimum elapsed time to reach 24 000         **>= 120.000 s** (equality only if
                                                              every expected period increments)
               * actual wall-clock duration                   may be LONGER if invocations are
                                                              skipped or the state gates the counter
               * an upper wall-clock bound                    **NOT established** by the value 24 000
             A previous revision of this entry called 120 s an upper bound. That was inverted and is
             withdrawn.

--- 2. The scientific target, separated from the safety caps -------------------------------------
             **Scientific target.** MIN_VALID_OBSERVATION = **120.000 s measured on the u64 time
             base, accumulated AFTER baseline_valid.** The negative claim this experiment can make is
             "a structured state did not appear during a valid window of comparison", and before
             baseline_valid there is no reference to compare against, so that time cannot support
             the claim. The clock therefore starts at baseline_valid, not at capture start.
             Consequence, stated rather than hidden: the total capture necessarily lasts longer than
             120 s, by however long the baseline took.
             **This window is not placed where the Disc's is.** The Disc arms its detector at
             session start and its counter runs from there, because the Disc does not learn a
             baseline — it has the reference embedded. Our window starts later. Frames observed
             before baseline_valid are NOT discarded: they are recorded in full with the
             pre_baseline flag, and one that differs from its neighbours opens an EARLY_CANDIDATE
             episode with its raw frames (section 9). So an early screen is still captured as
             evidence; it simply does not count toward the 120 s of negative evidence.
             **Safety caps are a different thing** (section 19) and are never described as the
             official window: the frame store, the event store, the episode caps and a wall-clock
             admission budget exist to keep a hardware experiment bounded, not to define the
             observation.

--- 2b. Stop condition, normative, in strict precedence order -----------------------------------
             Evaluated once per admitted cycle. Higher rules win outright when several hold.

               1. fatal service error (the GBP-VIDEO-001 failure policy, unchanged)
                      -> stop  failure
               2. HARD_WALLCLOCK_LIMIT expired                                   (section 19)
                      -> stop  safety_budget.  This wins over an open episode and over the
                         finalisation tail: the state available is snapshotted, the episode is
                         marked truncated_by_safety, and the teardown runs immediately. A hard cap
                         that could be extended by 60 more frames would not be hard.
               3. frame store full  or  event store full
                      -> stop  frame_store_cap / event_store_cap.  If this happens during a
                         finalisation tail the tail ends there, tail_truncated_by_cap is set, and
                         this is NOT a fatal service error.
               4. baseline_valid and valid_observation_elapsed >= MIN_VALID_OBSERVATION
                      -> if no episode is open:  stop  nominal_negative
                      -> if an episode IS open:  enter the bounded finalisation tail — no new
                         episode may open, the current one closes on stabilisation or at
                         EPISODE_MAX_FRAMES, and the run then stops nominal_negative
               5. no next cause within T_NEXT_CAUSE with budget left
                      -> stop  no_next_cause
               6. delivery guard reached
                      -> stop  delivery_cap

             There is **no positive early stop** (section 6c). After the stop, in every case: the
             minimal RAM snapshot, then the hardware teardown immediately (section 16).
             The tail never raises the scientific requirement. Reported separately:
             valid_observation_at_target, tail_frames, tail_ticks, final capture_elapsed.

--- 3. Scale, corrected, and explicitly estimates -----------------------------------------------
             From GBP-VIDEO-001's measured rates — 5 327 deliveries/s, 2 243 VIDEO blocks/s,
             3 671 AUDIO blocks/s, 16.794 ms per frame — 120 s implies about **639 000 deliveries,
             269 000 VIDEO blocks, 440 000 AUDIO blocks and 7 150 complete frames**.
             These are ESTIMATES derived from one physical run. They are not physical caps and not
             properties of the device. GBP-VIDEO-002's own caps are set separately, below.

--- 4. Time base ---------------------------------------------------------------------------------
             2^32 / 40.5 MHz = **106.049 s**, shorter than 120 s: a u32 tick counter wraps inside a
             single run. Every recorded timestamp is **u64**.
             Mechanism: the 64-bit PowerPC time base read as the standard three-instruction retry —
             read TBU, read TBL, read TBU again, repeat while the two TBU reads differ — which is
             what libogc2's gettime() does. Monotonicity across the low-word wrap follows from the
             retry: a carry from TBL into TBU between the two TBU reads is detected and the read is
             repeated, so the pair is never taken from either side of the carry. The design uses
             libogc2's existing u64 API if its implementation is confirmed to be exactly that loop,
             and the explicit loop otherwise; the choice is recorded in the implementation, not left
             as "use u64".
             The transport keeps its existing u32 `ticks` operation for the bounded per-operation
             waits (T_DMA, T_DELIVERY, T_NEXT_CAUSE), where a wrap-safe unsigned difference over a
             sub-second interval is already correct and physically exercised. That contract is
             explicit: **u32 deltas for short waits, u64 for every recorded timestamp.**

--- 5. Frame-signature store: capacity, not a temporal target -----------------------------------
             Per observed frame, 192 bytes:
                 frame index                        u32
                 t_first_block, t_last_block        u64, u64
                 blocks in the frame                u16
                 flags (complete, disagreement, anomaly, pre_baseline, resync)   u16
                 40 semantic block checksums        40 x u32
             **16 384 frames = 3.00 MB.** At the one frame rate we have measured that is about
             275 s of wall time, but **that number is capacity, not a target**: the probe is not
             expected or required to consume it. The capacity exists for baseline acquisition and
             startup, for real variation in frame cadence, for incomplete intervals that still
             occupy slots, for the episode finalisation tail, and for structural margin. Chosen over
             8 192 frames (1.50 MB) because at that size the cap would likely have been the stop
             rather than a backstop.
             A frame carrying more than 40 blocks stores the first 40 and sets the anomaly flag; the
             block count is kept so nothing is silently dropped.
             **At the cap:** no overwrite, no silent wrap. The run stops, the hardware teardown runs
             immediately, FRAME_CAPTURE reports `frame_store_cap`, and SERVICE may still be `ok`.
             If the cap is reached **before** valid_observation_elapsed has reached 120 s, the
             negative result is **inconclusive** — `insufficient_observation_window` — and is
             reported as such. The classification always keys on valid_observation_elapsed, never on
             which cap fired.

--- 6. The signature, and why byte 0 cannot forge a change --------------------------------------
             The per-block signature is GBI's own checksum, over the semantic payload only: for each
             group of four bytes it consumes **byte 1 and byte 3** and nothing else, packing two
             consecutive pixels into a 32-bit word, accumulating 240 such pairs in 64 bits and
             storing the low 32 bits plus the carry count. Byte 0 and byte 2 are never read, so the
             688 byte-0 exceptions GBP-HW-070 measured **cannot** produce a structured-change false
             positive — that is a property of the algorithm, not a tuning choice. The function is
             physically verified: the GBP-AV-SERVICE-001 block and VIDEO-001 seq0, whose raw bytes
             differ, both give 0x7F0FFF10.
             Frame-start bit: it lives in byte 1 of the block's first word, so it is inside the
             checksum by construction (0xFFFF versus 0x7FFF changed block 0's value from
             0xFF0FFF0F to 0x7F0FFF10 in the physical run). Within a frame, block 0 always carries
             it, so frame-to-frame comparison at the same block position sees it consistently on
             both sides and it can never by itself mark a frame as changed. Both predicates are also
             recorded per block, separately from the checksum.
             The result is directly comparable offline with GBI's tables without any private data
             being embedded in the runtime.

--- 6b. The three clocks, and what counts as valid observation ----------------------------------
             All u64 on the 64-bit time base:
                 capture_elapsed            capture_start -> stop
                 baseline_elapsed           capture_start -> baseline_valid
                 valid_observation_elapsed  accumulated, and the only one the negative result uses
             valid_observation_elapsed advances ONLY while all of these hold: SERVICE is still ok,
             baseline_valid is set, and the stream is currently interpretable. It is accumulated per
             completed frame — the frame's own duration is added when the frame closes complete and
             interpretable — so a period that was not interpretable is never silently counted as
             negative evidence.
             **Anomaly accounting, deliberately conservative, three classes only:**
               (a) frame-invalidating — a predicate disagreement inside the frame, a frame closed
                   incomplete (no boundary within 48 blocks), or a frame carrying more than 40
                   blocks. The frame is recorded and flagged, it is NOT counted as a complete frame,
                   and **its duration is excluded** from valid_observation_elapsed.
               (b) region-invalidating — the frame assembler lost synchronisation (a boundary
                   arrived at an unexpected position mid-frame). The frame being assembled is
                   discarded, and valid_observation_elapsed stays paused until a complete 40-block
                   frame with an observed boundary is seen again. That resync gap is bounded by the
                   assembler itself and is reported as resync_frames.
               (c) run-ending — every failure GBP-VIDEO-001 already treats as fatal, unchanged: DMA
                   busy/timeout/error, ACK or re-arm not completed, PI sticky after one W1C,
                   reentry, missed entry, unexpected source, capacity. These stop the run.
             Nothing else pauses the clock. The rule is conservative on purpose: when in doubt the
             time does not count, so a negative result can only ever understate the observation.

--- 6c. There is no early positive stop, and why -------------------------------------------------
             A previous revision stopped the run as soon as an episode closed with stable_found.
             That is **withdrawn**, because the runtime contains no oracle and therefore cannot know
             that the first stable changed state is the state that motivated the experiment. The
             failure mode is concrete: baseline uniform -> an intermediate stable screen -> the
             expected screen twenty frames later. Stopping at the first stable state would preserve
             the intermediate screen and lose the one we came for.
             Every oracle-free alternative was considered and rejected:
               * "stop on the first stable change" — the case above;
               * "stop when MAX_EPISODES is reached" — a capacity condition, not a scientific one,
                 and section 10 does not stop there anyway;
               * "stop when a frame shows content in the block range the references use" — that is
                 the private layout smuggled into the runtime; refused on the same grounds as the
                 tables themselves;
               * "stop when a frame's block checksums are unusually diverse" — an arbitrary
                 heuristic that would fire on noise and still could not tell the intermediate screen
                 from the expected one.
             **No objective, oracle-free early-positive condition exists**, so the experiment has
             none. The probe runs until the scientific target, a cap, or a failure. Offline,
             tools/avseq.py classifies each preserved episode against the Disc's embedded frame and
             GBI tables A and B. This maximises the information a single physical run yields and
             keeps every private comparison off the console.

--- 7. Where the checksum runs — decided by the references, not by preference -------------------
             Traced in both binaries:
               * GBI (FUN_8000BF30), in source order: read IRQ (0xD00000) -> ARQ read AUDIO
                 (0x800000, 0x1000) -> ARQ read VIDEO (0x100000, 0xF00) -> **ACK**, the 64-byte write
                 at 0xCFFFE0 that spans the end of the KEYPAD window into the IRQ window ->
                 conversion and per-block checksum (stride 0x780) -> at block 0x27 the 40-entry table
                 comparison -> blk = (blk + 1) % 0x28 -> **RE-ARM**, the write at 0xD00000, which is
                 the LAST device access of the pass.
               * Start-up Disc: the compare does not sit in the service path at all. FUN_8008EDE8 is
                 a thread that blocks on a queue, converts and compares one block per message,
                 decoupled from the acknowledge and re-arm entirely.
             So GBI, the only reference with a single serial path, puts the work **between the ACK
             and the RE-ARM**. GBP-VIDEO-002 adopts that position:
                 READ -> AUDIO -> VIDEO DMA -> ACK -> PICLEAN -> **checksum** -> REARM -> WAIT_NEXT
             This does not lengthen DMA->ACK, and it does not leave a latched cause waiting: the
             re-arm is what invites the next cause, so deferring it defers the next cause rather
             than delaying the service of one already latched. The previous revision put the
             checksum after REARM; GBP-VIDEO-001 showed the next cause can latch almost immediately
             after a re-arm, so that position would have left it waiting. Withdrawn.
             **The checksum never runs inside the ISR.** The raw ring provides the buffering, so the
             block being hashed is never the block the next DMA targets.

--- 8. Checksum cost: measured and compared, with no invented threshold -------------------------
             The ~20 us figure quoted earlier is an estimate and is treated as one. A previous
             revision of this entry required "p95 below 25 % of the median lean cycle". That number
             had no physical basis and is **withdrawn**: there is nothing in the hardware evidence
             that makes 25 % meaningful rather than 15 % or 40 %.
             What is required instead is a measurement and a comparison, both mandatory before any
             physical candidate:
               (a) the per-block checksum cost in time-base ticks over at least 10 000 blocks,
                   reported as **min, median, p95 and max**, on the host and again on the built DOL;
               (b) the same synthetic scenario run **with and without** the checksum in the cycle,
                   comparing: service cadence (delivery-to-delivery interval), VIDEO block rate,
                   AUDIO block rate, the ACK-to-REARM interval, next-cause timing after the re-arm,
                   the latched interval, and any change in timeout or reentry behaviour.
             Reference points from GBP-VIDEO-001 for that comparison: 294 us median between VIDEO
             blocks, 77 us median lean cycle, 2 485 ticks (61 us) of VIDEO DMA, 5 327 deliveries/s.
             The gate is a review gate, not a number: the benchmark report accompanies the release
             audit, and a physical candidate is not released while any of those quantities has moved
             in a way the reviewer has not explicitly examined and accepted. If the cadence does
             move materially, the remedies are the ones already identified — hashing outside the
             cycle from the ring, or hashing only the halfwords a signature needs — and the choice
             is made with the measurements in hand rather than in advance.

--- 9. Baseline ----------------------------------------------------------------------------------
             baseline_valid is set only after **three consecutive complete frames**, each with an
             observed boundary, exactly 40 blocks, and identical 40-checksum vectors. That vector is
             the baseline. Frames observed before baseline_valid are fully recorded with the
             pre_baseline flag, and one that differs from its neighbours is preserved as an
             **EARLY_CANDIDATE** with its raw frames. Baseline learning never overwrites or discards
             such a frame. If baseline_valid is never reached, the run says so and every frame stays
             in the store.

--- 10. Episodes: a state machine, and monitoring never stops at the raw cap ---------------------
             Two signatures are kept, and they are not the same thing:
                 **original_baseline_signature** — the vector fixed once at baseline_valid. It is
                     never overwritten. It documents what the machine was showing when the valid
                     window opened, and every episode is reported relative to it.
                 **current_reference_signature** — initialised to the original baseline and replaced
                     by each closed episode's final stable signature. It is what change detection
                     compares against, so a second transition is detected relative to the state the
                     device actually settled into, not relative to the long-gone original.
             The state machine:
                 ARMED        current signature == current_reference_signature
                 CHANGED      a frame's signature differs from current_reference_signature
                              -> open an episode; preserve the last reference frame from the ring
                                 and this first changed frame; candidate := this signature;
                                 stable_count := 1
                 STABILISING  for each following frame:
                                 signature == candidate -> stable_count++
                                 otherwise              -> candidate := this signature,
                                                           stable_count := 1, and preserve this
                                                           frame if the episode's raw budget allows
                              when stable_count reaches **N_STABLE = 3** -> preserve one raw frame of
                              that stable state, mark stable_found, close the episode
                 CLOSED       current_reference_signature := the episode's final signature (or is
                              left unchanged if the episode closed unstable), and the machine
                              re-arms immediately. **The run does not stop here** (section 6c).
             N_STABLE = 3 because that is the same evidence threshold the baseline uses, so "stable"
             means one thing in both places; at 59.5 Hz it is 50 ms, short enough not to miss a
             brief screen. **Hard cap:** an episode closes unconditionally after
             **EPISODE_MAX_FRAMES = 60** frames (about 1 s) marked `unstable`. Episodes are never
             unbounded.
             **MAX_EPISODES = 4.** Raised from 3 for a named reason: the scenario that removed the
             early stop needs at least two episodes (intermediate screen, then the expected one),
             and GBP-VIDEO-001 showed an early transient that can plausibly consume one, so four
             leaves one spare. Footprint: up to 4 preserved raw frames per episode x 48 x 0xF00 =
             737 280 B per episode, x 4 = **2 949 120 B = 2.81 MiB** (section 21).
             **When the episode raw store is full — policy B, chosen over stopping.** The run does
             NOT end. `episode_store_full` is set, no further raw frames are preserved, and the
             signature monitor keeps running to the scientific target or a cap, counting further
             episodes in `episodes_not_preserved`. The justification is that the per-frame
             signatures are themselves primary evidence: GBI's table comparison is a checksum
             comparison, so an unpreserved episode still yields a directly comparable signature
             vector offline — only the pixels and the Disc's halfword comparison are lost. Ending
             the run at the raw cap would discard the remaining seconds of signature evidence for no
             safety benefit. **No episode is ever overwritten.**

--- 11. Raw preservation -------------------------------------------------------------------------
             VIDEO blocks are assembled into a ring of **3 raw frame slots**, each 48 x 0xF00 =
             180 KB (48 rather than 40 so an over-long frame is still captured whole). A partial
             frame is never preserved as if it were a frame.
             Per episode, up to **4** frames are copied out of the ring:
                 the last reference frame before the change; the first changed frame; the frame
                 immediately after it (context); and the stable-state frame, if one was found.
             Where those coincide the slot is reused, so 4 is an upper bound.
             3 episodes x 4 slots = 12 slots = **2.11 MB**, plus the 0.53 MB ring.

--- 12. AUDIO during a long run ------------------------------------------------------------------
             Every selected AUDIO source is drained, exactly as now — the protocol is unchanged and
             physically validated. No per-drain record and no per-drain raw. Aggregate counters only,
             plus the raw payload of the **first** and the **last** successful drain (two 0x1000
             buffers, 8 KB), with the existing rule that a failed drain never overwrites a valid one.

--- 13. Frame segmentation and predicate disagreement -------------------------------------------
             Both predicates are computed and recorded for every block. **The Start-up Disc
             predicate (bit 7 of byte 1) is the segmentation signal**, justified physically:
             GBP-HW-070 found byte 0 disagreeing with byte 1 in 688 of 84 480 words while byte 2
             never disagreed with byte 3, so byte 0 is the unstable byte; GBI's predicate depends on
             bytes 0 AND 1, the Disc's on byte 1 alone.
             On disagreement (which can only be GBI = 0 with Disc = 1, since GBI implies Disc):
             segmentation continues on the Disc predicate and **no boundary is fabricated or
             suppressed**; the frame is flagged `disagreement` but is NOT marked incomplete, because
             the boundary is real under the stable byte. Recorded: the total count, the first
             occurrence with its frame and block index, and the raw first four bytes of that block.
             If 40 blocks pass with no boundary at all, the frame is closed as **incomplete** and
             flagged; a boundary is never synthesised from an assumed period.

--- 14. Counters and widths ---------------------------------------------------------------------
             u64: every absolute timestamp, total elapsed ticks, total bytes transferred.
             u32: deliveries, audio drains, video drains, acks, rearms, isr_w1c, main_w1c, errors,
                  unexpected, reentry, timeouts, busy, frames observed, frames complete, frames
                  incomplete, episodes, events, every cap counter. At the estimated 639 000
                  deliveries a u32 has more than three orders of magnitude of margin, and each
                  counter carries an explicit overflow guard that ends the run rather than wrapping.
             u16 is used ONLY for per-frame quantities bounded by construction (block count <= 48,
             flag words). **No u16 counts anything that accumulates over the run.**

--- 15. Event store -----------------------------------------------------------------------------
             A bounded ring of **4 096 events x 64 B = 256 KB**. Never one event per delivery.
             Event types: capture_start, baseline_candidate, baseline_valid, early_candidate,
             predicate_disagreement, incomplete_interval, episode_open, episode_stable,
             episode_close, anomaly, cap_reached, stop, teardown_begin, teardown_end.
             Each event: **monotonic u32 sequence number** assigned when the operation is performed,
             u64 timestamp, type, and a small fixed payload. Detailed per-cycle records exist only
             for the first 8 cycles, the last 8 cycles, anomalies and the cycles inside a preserved
             episode. Textual formatting happens after the teardown.

--- 16. Teardown ordering -----------------------------------------------------------------------
             **stop condition -> minimal RAM snapshot -> HARDWARE TEARDOWN -> only then global
             checksums, summaries, textual formatting and the sidecar save.**
             Snapshotted before the teardown: final counters, last frame index and its timestamps,
             stop reason, baseline_valid and the baseline vector, episode descriptors, the PI state
             the last WAIT_NEXT observed, and the identity fields. The teardown depends on none of
             them. Dependency audit on the current code: summarize() reads only the store and the
             raw buffers and writes only records; log_lean_cycles() reads only the cycle records and
             the two block addresses, which the teardown does not change; the teardown reads no
             field either produces. Nothing needed for analysis is lost by tearing down first.

--- 17. Sidecar: streamed, never a second full copy in MEM1 -------------------------------------
             The file is about 5.5 MB — larger than any staging buffer that would be reasonable.
             After the teardown: open the output, write the header, then write the frame-signature
             store, the preserved episode frames and the event records **directly in chunks**
             through a single small buffer (64 KB), maintaining a running CRC-32 across everything
             written, then the footer carrying that CRC. No second integral copy of the sidecar
             exists in MEM1 at any point.
             Filesystem access remains forbidden during capture and service; the save happens only
             after the teardown has completed, on the user's keypress as today.
             OGBPSEQ1 is extended, not replaced: the existing header, cycle/VIDEO/AUDIO tables and
             raw sections keep their layout; new optional sections carry the frame-signature store,
             the episode descriptors and the event records; the header gains the u64 time-base
             fields and the sequence-number range. Format version 2; version 1 files stay readable
             and the v2 block sidecar of GBP-AV-SERVICE-001 is untouched.

--- 18. Save failure is not a hardware failure --------------------------------------------------
             Because the save happens after the teardown, a filesystem or card failure cannot
             invalidate the hardware result held in RAM. The two are reported separately:
             **hardware_result** (SERVICE / FRAME_CAPTURE / BASELINE / STRUCTURED_CHANGE / RESTORE)
             and **save_result** (ok / partial(sections written) / failed(reason)). A partial save
             names exactly which sections reached the card. There is never an automatic re-run: the
             hardware state after a run is not the state a fresh run starts from.

--- 19. Safety caps, kept separate from the scientific target ------------------------------------
             None of these defines the observation window. All exist so a hardware experiment is
             bounded whatever the device does. **None is derived from the 24 000 callbacks**: that
             number describes the Start-up Disc's detector, not our safety policy.
             **Why a wall-clock cap is necessary:** valid_observation_elapsed only advances while
             the stream is interpretable (section 6b), so a pathological stream — frames never
             completing, or a long region-invalidating gap — could accumulate the 120 s arbitrarily
             slowly while the frame store also fills slowly. Without a wall-clock bound the run
             would have no guaranteed end.

                 **HARD_WALLCLOCK_LIMIT_SECONDS = 180**
                 **HARD_WALLCLOCK_LIMIT_TICKS_U64 = 7 290 000 000** (180 x 40 500 000)

             Counted from **t_control_transform**, the first experimental write — the CONTROL
             transform 0x90 -> 0x8C that starts the AGB — because that is when the device leaves its
             idle state and a bounded hardware experiment genuinely begins. Counting from the first
             unmask would leave the 003A cause wait (up to T_FIRST_CAUSE = 2000 ms) outside the
             bound. The existing admission-budget mechanism, physically exercised in
             GBP-VIDEO-001, is reused with this epoch: it gates the admission of NEW cycles, an
             admitted cycle is transactional, and the budget never interrupts one.
             **Why 180 s**, as an experiment-safety policy and nothing else:
                 normal worst case      baseline (5 s generous) + 120 s target + 1 s tail = 126 s
                 margin over that       +54 s, so a slower cadence or a slow baseline does not trip
                                        the safety cap spuriously
                 against the store      180 s is 65 % of the frame store's ~275 s of capacity at the
                                        one cadence we have measured, which gives a clean three-way
                                        separation: the normal run ends on the scientific target
                                        with neither cap firing; a slow-clock pathology hits the
                                        180 s safety cap first; a fast-frame pathology (many short
                                        or incomplete frames) hits frame_store_cap first
             Note that 7 290 000 000 does not fit in 32 bits — an independent confirmation that the
             u64 time base of section 4 is mandatory rather than tidy.
                 MAX_FRAMES 16 384 · MAX_EVENTS 4 096 · MAX_EPISODES 4 · EPISODE_MAX_FRAMES 60 ·
                 N_STABLE 3 · MAX_DELIVERIES 2 000 000 (a guard, u32).
                 T_DELIVERY 100 ms, T_NEXT_CAUSE 100 ms, T_DMA 200 ms, T_FIRST_CAUSE 2000 ms —
                 unchanged and already physically exercised.
             **Safety versus the scientific target:** if HARD_WALLCLOCK_LIMIT fires before
             valid_observation_elapsed reaches MIN_VALID_OBSERVATION, the result is
             `ok_no_change_inconclusive` with stop reason `safety_budget` — **never**
             `nominal_negative`. Every stop records capture_elapsed, baseline_elapsed,
             valid_observation_elapsed and the stop reason.
             Stop reasons: `nominal_negative` · `frame_store_cap` · `event_store_cap` ·
             `safety_budget` · `delivery_cap` · `no_next_cause` · `failure`.

--- 20. Result matrix ---------------------------------------------------------------------------
             SERVICE            ok / failed(<reason>)
             FRAME_CAPTURE      ok / frame_store_cap / event_store_cap, with frames observed,
                                complete, incomplete, resync_frames, the interval histogram and the
                                disagreement count
             BASELINE           valid(after N frames, baseline_elapsed) / never_established
             STRUCTURED_CHANGE  **not a boolean.** A status plus counts:
                                    status            not_observed / observed
                                    episode_count     episodes opened
                                    stable_episodes   closed with stable_found
                                    unstable_episodes closed at EPISODE_MAX_FRAMES
                                    episodes_not_preserved  seen after the raw store filled
                                    episode_store_full      flag, may coexist with observed
                                    truncated_by_safety / tail_truncated_by_cap  flags
                                An episode is a change **relative to the reference signature of the
                                moment**, nothing more. It never means "the official frame was
                                found": only the offline oracle can say that.
             REFERENCE_MATCH    offline only: not_applicable / unavailable / not_observed / partial /
                                full, reported per preserved episode
             RESTORE            ok / failed
             SAVE               ok / partial(sections written) / failed(reason)
             Always reported: capture_elapsed, baseline_elapsed, valid_observation_elapsed,
             valid_observation_at_target, tail_frames, tail_ticks, complete and incomplete frames,
             anomalies by class, resync_frames, and the stop reason.
             Main statuses: `ok_structured_change_observed` (episode_count >= 1 and the run reached
             its target or a non-safety cap) · `ok_no_change_nominal_interval`
             (valid_observation_elapsed >= 120.000 s, episode_count == 0) ·
             `ok_no_change_inconclusive` (valid_observation_elapsed < 120.000 s for any reason,
             including any cap firing first) · plus the GBP-VIDEO-001 failure statuses unchanged.

             Worked examples:
               A. no episode, target reached
                    SERVICE=ok · FRAME_CAPTURE=ok · BASELINE=valid · STRUCTURED_CHANGE=not_observed
                    (episode_count=0) · REFERENCE_MATCH=not_applicable · RESTORE=ok · SAVE=ok
                    status ok_no_change_nominal_interval; wording "no structured change observed
                    during >= 120 s of valid post-baseline observation in this physical
                    configuration".
               B. several episodes, target reached
                    STRUCTURED_CHANGE=observed, episode_count=3, stable_episodes=2,
                    unstable_episodes=1 · REFERENCE_MATCH decided offline per episode ·
                    status ok_structured_change_observed. The run did NOT stop at the first stable
                    episode; each is classified offline.
               C. safety budget before the target
                    stop reason safety_budget · valid_observation_elapsed < 120 s ·
                    status ok_no_change_inconclusive (never nominal_negative) · RESTORE reported
                    independently.
               D. episode raw store full, monitoring continued
                    STRUCTURED_CHANGE=observed, episode_count=6, episode_store_full=1,
                    episodes_not_preserved=2 · the four preserved episodes have raw; the other two
                    have signatures only, which still support the GBI-table comparison offline.
                    That distinction is never collapsed.
               E. hard safety fired with an episode open
                    stop reason safety_budget · the open episode marked truncated_by_safety ·
                    status ok_no_change_inconclusive if the target was not reached, otherwise
                    ok_structured_change_observed · RESTORE reported independently of either.

--- 21. Memory budget, with the final episode policy --------------------------------------------
             Resident during capture:
                 text + data (GBP-VIDEO-001 measured 419 KB)                     ~0.45 MiB
                 frame-signature store 16 384 x 192 B                             3.00 MiB
                 raw working ring 3 x 48 x 0xF00                                  0.53 MiB
                 preserved episodes 4 x 4 x 48 x 0xF00                            2.81 MiB
                 event store 4 096 x 64 B                                         0.25 MiB
                 AUDIO first + last 2 x 0x1000                                    0.01 MiB
                 stack and libogc runtime                                        ~0.30 MiB
                                                                                ---------
                 resident subtotal                                               ~7.35 MiB
             Temporary, only after the teardown:
                 sidecar streaming chunk buffer                                   0.06 MiB
                                                                                ---------
                 total                                                           ~7.41 MiB of 24 MiB,
             leaving about **16.6 MiB**. GBP-VIDEO-001's image occupied 2.21 MiB. The sidecar file
             itself is roughly 6.3 MiB (signatures 3.00 + preserved raw 2.81 + events 0.25 + the
             existing sections) and is **never resident in full**: it is streamed in 64 KiB chunks
             with a running CRC after the teardown (section 17).

Physical setup: identical to GBP-VIDEO-001 — GameCube, GBP attached, NO Game Pak, Link Port empty,
             PicoAdapterGB disconnected, BBA attached without cable, 1 controller, 1 Memory Card,
             SD2SP2, Swiss. Power cycle mandatory afterwards. Expect two to five minutes of
             unattended running, then a multi-megabyte SD write on the keypress.

Risks:       by far the longest run attempted, bounded by the admission budget, the store caps and
             the per-operation timeouts, all physically exercised; a u32 timestamp anywhere would
             silently corrupt ordering after 106 s, which is why the width is both a requirement and
             a test; the checksum cost could perturb the cadence, which is why it is measured with a
             stated review trigger before any hardware request; the screen may never appear, which
             is itself the answer to U-GBP-031; a multi-megabyte SD write after the run.

Host tests to add with the implementation (all synthetic, none physical evidence):
             (1)  time base crossing the low-word wrap 0xFFFFFFFF -> 0x00000000: timestamps,
                  differences and ordering stay correct, and a deliberately truncated u32 path fails;
                  HARD_WALLCLOCK_LIMIT_TICKS_U64 = 7 290 000 000 is itself outside u32 and the test
                  asserts the comparison is done in 64 bits;
             (2)  a full nominal scan with ~639 000 synthetic deliveries: no counter overflows, no
                  per-delivery record, the event ring stays bounded;
             (3)  modelled callback progress delayed beyond 120 s: the run still reports its elapsed
                  valid observation correctly and the classification uses it;
             (4)  baseline takes several seconds: baseline_elapsed reflects it and
                  valid_observation_elapsed is still zero throughout;
             (5)  the 120 s clock starts only at baseline_valid; capture_elapsed exceeds it by
                  baseline_elapsed;
             (6)  the temporal target is reached exactly with no episode open: stop
                  nominal_negative on the first cycle at or past MIN_VALID_OBSERVATION;
             (7)  the target is reached with an episode OPEN: no cut mid-episode, the bounded tail
                  runs, no new episode opens during it, tail_frames and tail_ticks are reported and
                  the tail never exceeds EPISODE_MAX_FRAMES;
             (8)  **frame store cap during a tail**: the tail ends, tail_truncated_by_cap is set,
                  and it is NOT reported as a fatal service error;
             (9)  **HARD_WALLCLOCK_LIMIT fires with an episode open**: the safety cap wins over the
                  tail, the episode is marked truncated_by_safety and the teardown is immediate;
             (10) **safety budget before the target**: status ok_no_change_inconclusive with stop
                  reason safety_budget, never nominal_negative;
             (11) **no early stop on stable_found alone**: an episode closes with stable_found and
                  the run continues to the target, opening further episodes;
             (12) **the first stable change is not the desired one**: baseline -> intermediate
                  stable screen -> a different stable screen 20 frames later; both are preserved as
                  separate episodes and the withdrawn early-stop rule would have lost the second;
             (13) episode 1 closes, monitoring continues, episode 2 is opened and preserved;
             (14) **original_baseline_signature is never overwritten** while
                  current_reference_signature advances to each closed episode's final signature;
             (15) a change detected relative to current_reference_signature, not to the original
                  baseline, after one episode has closed;
             (16) **MAX_EPISODES reached**: the run does NOT stop; episode_store_full is set, no
                  further raw is preserved, signature monitoring continues and
                  episodes_not_preserved counts the rest; no episode is overwritten;
             (17) an episode that never stabilises closes at EPISODE_MAX_FRAMES marked unstable;
             (18) 120 s reached with several episodes already closed: status
                  ok_structured_change_observed with the per-episode counts intact;
             (19) frame_store_cap before the target: stop frame_store_cap, no overwrite, no wrap,
                  negative result classified ok_no_change_inconclusive;
             (20) an anomalous frame is not counted as negative evidence: class (a) excludes its
                  duration, class (b) pauses the clock until a clean complete frame returns;
             (21) byte-0 variation across a frame changes no semantic signature and opens no episode;
             (22) baseline formation: three identical complete 40-block frames set it; two do not; a
                  39- or 41-block interval does not;
             (23) a structured frame arriving before baseline_valid is preserved as EARLY_CANDIDATE;
             (24) predicate disagreement: recorded with count, first occurrence and raw_first4;
                  segmentation unaffected; the frame flagged but not incomplete;
             (25) an interval other than 40: histogram only, never a failure, no synthesised
                  boundary;
             (26) ACK -> checksum -> REARM ordering is what the cycle performs, and the
                  ACK-to-REARM interval is measured with and without the checksum;
             (27) the checksum benchmark reports min/median/p95/max and the with/without cadence
                  comparison, and asserts **no fixed threshold** — the test checks the report is
                  complete, not that a number is below a constant;
             (28) immediate teardown: no store, summary or format call occurs between the stop
                  condition and the first teardown hardware write;
             (29) deferred formatting preserves event ordering, including two events sharing one
                  tick, reconstructed from the sequence numbers;
             (30) sidecar streaming of a file larger than 1 MiB with a running CRC, and no second
                  full copy resident;
             (31) save failure after a successful teardown: hardware_result intact, save_result
                  failed or partial naming the sections written;
             (32) exact MEM1 capacity: the static footprint matches section 21, no overlap, DMA
                  targets 32-byte aligned.

Implementation notes (2026-09-16 — what the code added to the design above;
nothing here is a physical result, and NO physical GBP-VIDEO-002 data exists):

- **Files created.** `src/common/gbp_time64.{h,c}` (the 64-bit time base and its
  wrap-safe arithmetic), `src/gbp/gbp_vsig.{h,c}` (the per-block signature, both
  predicates, the bounded cost histogram), `src/gbp/gbp_vstate.{h,c}` (the frame
  assembler, the frame-signature store, the event store, the baseline, the
  episode state machine, the raw preservation policy, the AUDIO aggregate),
  `src/gbp/gbp_vstate_probe.{h,c}` (the service loop, the three clocks, the stop
  precedence, the immediate teardown, the bounded cycle records),
  `src/gbp/gbp_vstatedump.{h,c}` (the streamed sidecar and its strict parser),
  `poc/gbp-video-state-probe/` (Test ID `GBP-VIDEO-002`, Build ID `vstate-0001`,
  log prefix `OPENGBP-VSTATE`), `tools/vstate.py`, `tests/unit/test_gbp_vsig.c`,
  `tests/unit/test_gbp_vstate.c`, `tests/unit/test_gbp_video_state.c`,
  `tests/host/test_vstate.py`. Modified: the transport gained the optional
  `ticks64` operation, `sdlog` gained a streaming writer, the mock gained a
  64-bit clock, a per-index tick advance and a VIDEO fill hook, `poc_audit.py`
  gained the `vstate` profile and a per-object "must not reference" rule.
  `gbp_avseq*`, `gbp_video_probe` and `gbp_avseqdump` (GBP-VIDEO-001) are
  **untouched** and are not linked into this POC.

- **THE INTERRUPT PATH IS BYTE-IDENTICAL** to the build GBP-VIDEO-001 executed
  physically. `make vstate-audit` diffs both one-shot bodies against that build's
  and reports them identical (82 instructions, one `__MaskIrq` call, one INTSR
  store of 0x2000 after the mask, no INTMR store). One `__UnmaskIrq` call site,
  `IRQ_Request` only from the install/restore pair, no INTMR store anywhere.

- **The u64 time base is libogc2's `gettime()`**, and the choice is recorded
  rather than left open: its source (external/libogc2, commit ca03fb75) is
  EXACTLY the required loop — `mftbu / mftb / mftbu / cmpw / bne` — so the
  backend calls it instead of adding a second hand-written copy. The composition
  and retry RULE lives in `gbp_time64.c` as a pure function and is tested on the
  host across the low-word wrap. The audit pins one call site, in `h_ticks64`.

- **Seven IRQ-register write sites**, not six: 3 in the stage (A1/A2/STOP), 1 in
  the shared service (the verify cycles' ACK) and 3 in the probe. The third is
  not a new write path: GCC duplicates the single re-arm statement across the
  verify branch, and the disassembly shows `li r7,0` at both copies, so both
  write 0x0000. Pinned by `tools/poc_audit.py --profile vstate`.

- **Filesystem isolation is audited, not asserted.** The profile refuses any
  reference to `fopen`, `fwrite`, `fat*`, `sdlog_*` and their relatives from
  every object of the capture path; only `sdlog.o` may have them, and `main.o`
  calls it after the probe has returned from its teardown.

- **Three buffers for AUDIO raw, not two.** The design's budget line says "first
  + last, 2 x 0x1000". Two buffers cannot satisfy that same section's rule that a
  failed drain never overwrites a valid capture, because a drain writes before
  its status is known, so the implementation uses the first slot plus a ping-pong
  pair — 12 KiB, which still rounds to the same 0.01 MiB.

- **An early candidate consumes at most one episode descriptor.** Section 9 asks
  for a differing pre-baseline frame to be preserved with its raw. Preserving
  every such frame could exhaust all four descriptors before the baseline exists
  and leave none for a real episode, so the FIRST one keeps its raw and the rest
  are counted in `early_candidates`. Deliberate, bounded and reported.

- **"No boundary within 48 blocks" also pauses the clock.** Section 6b classifies
  it as frame-invalidating (class a). It also leaves the assembler without an
  anchor, so the implementation additionally raises the region anomaly, which is
  the direction section 6b's own principle requires — when in doubt the time does
  not count. Both counters are incremented, so neither reading is hidden.

- **Detailed cycle records:** the first 8, a rolling window of the last 8, up to
  8 anomalies and up to 64 cycles observed while an episode is open — 88 records
  of 128 bytes, against about 639 000 deliveries.

- **Sidecar: the OGBPSEQ1 family at version 2**, as section 17 asks. Same magic,
  same `OGBPEND1` footer, same identity rule, big-endian field by field, a
  0x200 header with the u64 clocks, a header CRC and a total CRC. The content is
  what the evidence became: a frame table, an event table, an episode table, the
  bounded cycle table and the preserved raw. Version 1 is untouched, still
  written by GBP-VIDEO-001 and still read by `tools/avseq.py`; both parsers check
  `version` and `header_size` first, and a host test proves neither can read the
  other. Streamed in 64 KiB chunks with a running CRC, only after the teardown.

- **Measured on the built DOL** (not predicted): text + data 0.41 MiB; the five
  evidence stores 6.602 MiB and every static of the probe 6.929 MiB; image ending
  at 0x8078D038, **MEM1 headroom 16.449 MiB**; zero overlaps; every DMA target
  32-byte aligned; the only static objects above 1 MB are the frame store and the
  episode raw store, so no second full copy of the sidecar exists. The design
  predicted ~7.41 MiB resident and ~16.6 MiB free.

- **The log does not grow with the run.** Measured at 200, 2 000, 20 000 and
  200 000 deliveries, the ring holds **214 lines at the moment of the teardown in
  every one of them**, and 293 when the report has been written; 0 dropped. The
  1024-line ring has more than three times the margin it needs, and nothing in the
  capture path formats per delivery.

- **The full nominal scan runs in the test suite**: about 800 000 synthetic
  deliveries, 399 000 VIDEO blocks, 9 983 frames, 120.0 s of accumulated valid
  observation, a run whose absolute timestamps cross 0x100000000, and no counter
  overflow. Every scenario is SYNTHETIC.

- **The signature cost is measured, and no threshold is applied.** Section 8
  requires (a) the per-block cost over at least 10 000 blocks as min / median /
  p95 / max and (b) the same scenario with and without the signature. Both run in
  the test suite. (a) on the host, over 20 000 blocks:

      min 260 ns   median 263 ns   p95 271 ns   max 4 489 ns   mean 267 ns

  taken from the bounded 1 KiB histogram, never from the mean, with each value
  carrying its own bucket width. (b) the same 4 000-delivery scenario twice:

      quantity              with      without     delta
      deliveries            4000      4000        0
      VIDEO blocks          2001      2001        0
      AUDIO drains          4000      4000        0
      frames assembled        50         0       +50
      ACK -> REARM (mean)     28        10       +18   (mock ticks)
      REARM -> next (mean)    60        60         0
      cause -> ACK (mean)    489       489         0

  The signature lengthens ACK -> REARM, which is where GBI does the equivalent
  work, and leaves the re-arm-to-next-cause and cause-to-ACK intervals untouched.
  **These are HOST and MOCK figures, not hardware ones**, and Dolphin's timing
  would not be a hardware figure either. The physical half needs the real 40.5 MHz
  base and a real run; the probe already records sig_ticks per cycle and
  min / median / p95 / max in the sidecar header, so it needs no new code. The
  gate stays a review gate: the report must be complete and a reviewer must accept
  it, and the arbitrary 25 % threshold stays withdrawn.

Microaudit of the dirty implementation (2026-09-16, source + objects + tests).
Six defects were found and fixed; all are small and unequivocal, and none
required a structural change. Every one is a variant of the same mistake —
**a derived or reconstructed value being reported as if it were measured**:

1. **The safety epoch was fabricated when no CONTROL write happened.** The u64
   epoch is reconstructed from the stage's 32-bit timestamp; that arithmetic ran
   even on the abort paths, where the timestamp is still 0, producing an epoch
   about 25 s in the FUTURE (observed in the Dolphin runs:
   `t_control_transform=7947f7fffffffe` against `t64_pre=7947f7c37eefa7`). The
   loop is never entered on those paths, so no safety decision was ever wrong,
   but the value reached the log and would have reached the sidecar header. Now
   the reconstruction runs only when the write completed, and the field carries
   the probe's own start with `epoch_ok = -1` otherwise.
2. **The reconstruction was not checked, only bounded by argument.** It now has
   a MEASURED bracket: two real u64 reads are taken around the stage, and the
   reconstructed epoch must land between them. If it does not, the earlier end
   is used — earlier than the true write, so the safety budget is over-counted
   and the cap fires sooner, never later. Independently, the window itself is
   bounded: 12 block transfers, each bounded by the transport's own operational
   timeout, with no polling loop, so a worst case of 2.4 s against the 106.049 s
   at which a 32-bit difference could become ambiguous — a factor of 44.
3. **`capture_elapsed` was derived from an unset start.** On an abort the
   capture clock never starts, and subtracting it from a real stop produced the
   absolute time base read back as a duration (`capture_s=842908848.305` in
   Dolphin). Every derived interval now requires both endpoints to be real.
4. **`gbp_replay_transport()` did not zero the transport struct**, unlike the
   other two full constructors. Callers declare it uninitialised, so the newly
   added `ticks64` operation came back indeterminate on a replay and
   `gbp_transport_has_time64()` would answer from garbage. Fixed with a `memset`
   and pinned by a poison test that also covers any operation added later.
5. **One log line was formatted between the stop decision and the first teardown
   write.** GBP-VIDEO-001's defect was 64.99 ms of summarising there; one
   fixed-size line is four orders of magnitude smaller, but the rule is now
   absolute: the probe formats NOTHING before the hardware is safe. The status
   line moved after the teardown.
6. **A comment overstated the delivery guard's margin** as "three orders of
   magnitude". The real figures are 3.13x over the 120 s estimate and 2.08x over
   the 180 s envelope at the one measured rate; three orders of magnitude is the
   margin of the u32 TYPE, which is what the design's section 14 says.

Re-verified after the fixes: C 17 binaries / 691 801 checks / 0 failures,
Python 260 passed, every audit 0 findings, both one-shot handler bodies still
byte-identical to the GBP-VIDEO-001 build's, both Dolphin gates PASS, and the
full synthetic scan unchanged at 798 640 deliveries with peak host memory
14.2 MiB. The DOL changed, so the hash recorded before the microaudit is
withdrawn.


- **Not promoted.** Nothing above is a physical result. U-GBP-030 and U-GBP-031
  stay open, 40 blocks per frame keeps the status `docs/research/EVIDENCE.md`
  gives it, and the colour naming stays CORROBORATED.


```text
Question:    Over a bounded sequence of delivered HSP causes serviced the reference way (read IRQ →
             drain AUDIO if 0x0400 → drain VIDEO if 0x0100 → ACK pending | 0x8000 → PI clean →
             IRQ := 0 → next cause), what is the physical VIDEO block stream: on which blocks a
             frame-start predicate is true (GBI's and the Disc's, separately), how many blocks lie
             between two consecutive true predicates, in which order the blocks arrive, at what
             intervals VIDEO and AUDIO sources appear, and does the repeated service stay stable
             (no reentry, no lost cause, no transport uncertainty)? Offline, and only offline, the
             captured blocks are compared with the idle screen both references embed
             (VIDEO_PATH.md §2.4, §3.3): an oracle for the content, never a gate for the hardware.
Not asked:   rendering on the GameCube; the color naming (R/G/B bit order stays C until a
             known-color cartridge, VIDEO-002 — and the decision whether VIDEO-001's data can
             raise it is taken after the run, not before); KEYPAD writes (kept out: one new
             variable — repetition); SIO; a cartridge; a second delivery per cycle; the AUDIO
             format.
Why not static / Dolphin: the references' constants say 40 blocks of 4 lines; the physical
             cadence, the predicates' occurrence, dropped or duplicated blocks and the source
             pattern per cause are hardware behavior; Dolphin ties its video IRQ to the audio
             phase and its blocks are model data.

New variable class (ONE): repetition of the validated pass over dozens of cycles with the CPU
             masked between deliveries. Everything else is the AVSVC sequence: same handler
             (003B extended one-shot), same drains (one DMA each), same ACK / PI clean / re-arm
             writes, same teardown family. No KEYPAD, no CONTROL change beyond the transform and
             its restore, no write without physical precedent.

Capture target and caps (operational; none is a hardware property; all evaluated at the
admission point, never in the middle of an accepted cycle):
             TARGET_VIDEO_BLOCKS = MAX_VIDEO_BLOCKS = 88 — the capacity of the block array and the
                 loop's normal end. Rationale, under the references' period of 40 as a working
                 HYPOTHESIS: the capture starts at an arbitrary phase, so the first true
                 predicate can come as late as the 40th block, and the next one 40 blocks later;
                 80 blocks guarantee one complete boundary→boundary interval only if the period is
                 40; 88 leaves 8 of margin. 48 blocks would guarantee at most ONE boundary and
                 never a complete interval; the earlier phrase "48 = one frame + 8" was wrong and
                 is withdrawn. 88 is capacity, not a hardware truth: if the physical period
                 differs, the boundary result reports what was seen. Target reached → no further
                 delivery is admitted "to look for something else": the final bounded observation
                 (WAIT_NEXT of the last cycle, below) runs, then the teardown, which acknowledges a
                 cause latched after the last re-arm.
             MAX_DELIVERIES 320 (AUDIO-only causes may outnumber VIDEO ones ≈ 2–3 : 1 if the
                 audio block rate is near Dolphin's 4096 Hz model — unknown; the bound protects,
                 the ratio is an observation). Reached → no further admission →
                 `ok_target_not_reached_delivery_cap` (SERVICE ok, CAPTURE delivery_cap), never a
                 transport failure. The AUDIO and cycle tables have MAX_DELIVERIES entries and
                 each admitted cycle drains at most one AUDIO block, so no separate AUDIO cap is
                 needed (MAX_AUDIO_BLOCKS = MAX_DELIVERIES by construction).
             MAX_RUNTIME_MS 1000 — the SERVICE-LOOP ADMISSION BUDGET (semantics below): the limit
                 for STARTING new cycles, not a wall-clock kill of a cycle already accepted.
                 Expired at the admission point → `ok_target_not_reached_runtime_cap` (SERVICE ok,
                 CAPTURE runtime_cap).
             T_NEXT_CAUSE 100 ms: the masked, read-only poll for the next cause after a re-arm,
                 part of the cycle that re-armed; it runs to min(T_NEXT_CAUSE, remaining admission
                 budget). Expired with budget left → `observation_no_next_cause` (nothing is
                 fabricated: no unmask without a latched cause, no write to provoke one).
             T_DELIVERY 100 ms: bound on the handler-entry wait after an unmask (the cause is
                 already latched, so the entry is expected inside the call; the bound only
                 catches an environment fault → anomaly_missed_entry).
             T_FIRST_CAUSE 2000 ms (the 003A stage, before the loop; as 003A/AVSVC).
             T_DMA 200 ms per transfer (as AVSVC); 32-byte transfers keep the transport's 200 ms
                 operational timeout; no retries anywhere.
             VERIFY_CYCLES 4: the first four admitted cycles take the AVSVC snapshots (PRESVC +
                 POSTDRAIN + POSTACK + REARMPOST with CONTROL / IRQ / PI reads and the AVSVC
                 checks); the remaining cycles run the lean path.

Service-loop admission budget — semantics (simple, testable):
             t0 := the time-base value at the first admission (the first unmask of the loop);
             ADMISSION_DEADLINE := t0 + MAX_RUNTIME_TICKS; remaining(t) := ADMISSION_DEADLINE − t as
             a wrap-safe unsigned difference on the 32-bit time base (as every probe so far).
             (1) CHECK_ADMISSION, evaluated before PREPARE / UNMASK of every cycle: a new cycle is
                 admitted only if remaining > 0, deliveries < MAX_DELIVERIES and video_blocks <
                 TARGET_VIDEO_BLOCKS; otherwise the loop ends normally (runtime_cap /
                 delivery_cap / target_reached) and the teardown follows — no unmask, no new
                 delivery; a cause already latched at the PI stays latched and is acknowledged by
                 the teardown (recorded as next_cause_at_end = yes, deliveries unchanged). A next
                 cause observed is NOT a cycle admitted.
             (2) An admitted cycle — the unmask executed and CONFIRM satisfied (fired == 1, count ==
                 1, reentry == 0) — is TRANSACTIONAL: READ → AUDIO if selected → VIDEO if selected →
                 ACK → PICLEAN → REARM completes in full even if the admission deadline expires
                 meanwhile. The deadline expiring between AUDIO and VIDEO changes nothing: VIDEO is
                 drained, the ACK is `pending | 0x8000` for the whole pending value (never a partial
                 ACK), the re-arm is written. The cycle is never abandoned because the deadline
                 passed; it ends only by completion or by a real failure (failure teardown).
             (3) Every step of the accepted cycle keeps its own bound, without retries: each DMA ≤
                 T_DMA (AUDIO ≤ 200 ms, VIDEO ≤ 200 ms), each 32-byte transfer ≤ its 200 ms
                 transport timeout (READ, ACK, REARM, the verify snapshots), PI cleanup = at most
                 one W1C and one re-read, handler-entry wait ≤ T_DELIVERY.
             (4) WAIT_NEXT after the re-arm belongs to the completion / observation of the cycle
                 that re-armed: a masked read-only poll of INTSR13 to min(T_NEXT_CAUSE, remaining).
                 If remaining is already 0 when it would start, it degenerates to a single read
                 (the observation is still recorded). If the deadline arrives during the wait
                 with no cause → the loop ends as runtime_cap with next_cause_at_end = no
                 ("no next cause before the cap") — no unmask, nothing fabricated. If the cause
                 appears before the deadline it stays latched and CHECK_ADMISSION decides; the
                 admission may still be refused (the deadline expired between the observation and
                 the admission, or a cap): the cause is left latched for the teardown.
             (5) Bounded overrun past ADMISSION_DEADLINE = the remaining work of the one cycle in
                 flight + WAIT_NEXT (never beyond the deadline) + the teardown. Conservative upper
                 bound, counting EVERY transfer at its 200 ms operational timeout (each such
                 timeout would also be a failure; typical values are microseconds): lean cycle
                 T_DELIVERY 0.1 s + READ 0.2 + AUDIO 0.2 + VIDEO 0.2 + ACK 0.2 + REARM 0.2 = 1.1 s;
                 verify cycle + 3 snapshots × 2 transfers = + 1.2 s → 2.3 s; teardown (CONTROL
                 restore, IRQSTOPPRE, STOP, IRQSTOPPOST, two FINAL reads) ≤ 1.2 s. Worst case wall
                 time of the loop and teardown ≈ 1.0 + 2.3 + 1.2 = 4.5 s; typical overrun < 1 ms.
                 The SD save (on X) is outside the budget.

State machine of the repeated service (CPU masked everywhere except inside the unmask call):

             INIT_ENTRY        the validated 003A stage found the first cause (PI13 = 1, INTMR13 =
                               0, PREUNMASK checks as AVSVC); t0 is taken at the first admission
             CHECK_ADMISSION   remaining > 0 ∧ deliveries < MAX_DELIVERIES ∧ video_blocks < TARGET
                               ∧ a cause is latched (PI13 = 1 observed) → PREPARE; otherwise →
                               TEARDOWN with CAPTURE = runtime_cap / delivery_cap /
                               target_reached (a latched cause stays latched: next_cause_at_end =
                               yes) or no_next_cause (WAIT_NEXT expired with budget left)
             PREPARE           verify INTMR13 == 0 by a read; verify the previous record was
                               consumed; reset the record (fired := 0, count := 0, reentry := 0,
                               timestamps and INTSR / INTMR fields := 0) — memory writes only, NO
                               write to INTSR or INTMR; PI13 == 1 is left INTACT
             UNMASK            one __UnmaskIrq: the latched cause is taken inside the call
                               (ENV-IRQ-003, F hw ×3); the ISR masks first, performs its ONE W1C,
                               records; t_unmask before, t_post_unmask after; entry wait ≤ T_DELIVERY
             CONFIRM           main re-mask (idempotent), read INTMR13 == 0; copy the record;
                               require fired == 1, count == 1, reentry == 0, INTSR at entry with
                               bit 13, INTMR at entry with bit 13, after-mask INTMR13 == 0,
                               after-W1C INTSR13 == 0; any other value → anomaly_reentry (count >
                               1), anomaly_missed_entry (fired == 0), anomaly_isr_state (the rest)
                               → failure TEARDOWN. Satisfied → deliveries := deliveries + 1; the
                               cycle is now ADMITTED and transactional
             SERVICE_TRANSACTION (completes in full regardless of the admission deadline):
               READ            read IRQ (32 B, Disc == GBI vote required) → pending; keep byte 0
                               and the group-0 offset-2 byte; pending & ~0x0500 ≠ 0 →
                               anomaly_unexpected_source (observed, not serviced: no ACK, no
                               re-arm); pending == 0 → anomaly_cause_without_source
               AUDIO           if pending & 0x0400: one DMA 0x1000 (destination per the AUDIO
                               policy)
               VIDEO           if pending & 0x0100: one DMA 0xF00 into video_blocks[n]; n := n + 1
               ACK             IRQ := pending | 0x8000 — the whole pending value, never partial
                               (attempted / completed counted; not completed → ack_write_failed)
               PICLEAN         read INTSR / INTMR; INTSR13 == 1 → ONE main W1C (counted as
                               relatch_postack) and re-read; still 1 → anomaly_pi_sticky; INTMR13
                               must read 0 in every main-loop read
               REARM           IRQ := 0x0000 (not completed → rearm_write_failed); t_rearm
             WAIT_NEXT         masked read-only poll of INTSR13 until 1 or min(T_NEXT_CAUSE,
                               remaining) (a single read if remaining == 0); the poll that sees 1
                               gives t_cause of the candidate next cycle and next_cause_observed
                               := yes; nothing is written to the PI here → CHECK_ADMISSION
             TEARDOWN          normal (cap / target / no next cause) or failure: CONTROL restore,
                               STOP word `read | 0x8AAA`, CLEANUPCHK → ≤ 1 W1C for a latched
                               cause, handler restore, AR_INFO restore; then the save
             W1C budget per cycle: ISR 1 (UNMASK), main ≤ 1 (PICLEAN only); NONE between
             WAIT_NEXT and the next UNMASK; the teardown ≤ 1. PI13 == 1 with an invalid source is
             an anomaly at READ, never cleared "to continue". A cycle admitted (CONFIRM
             satisfied) is never aborted because the deadline expired afterwards.

Handler and record reuse (`hsp_backend_oneshot_isr_ext`, 003B extended one-shot, installed once):
             Invariants before every unmask (PREPARE, all verified and logged on violation): CPU
             masked (INTMR bit 13 read 0); the previous record consumed (copied to the cycle
             record at CONFIRM); fired == 0, count == 0, reentry == 0; t_entry, t_second and the
             INTSR / INTMR fields zeroed (known); the handler still installed (installed once at
             the loop entry, never re-installed, never restored before the teardown); INTSR bit
             13 already 1 from a valid next cause (WAIT_NEXT) and admission granted. The
             preparation writes only the record in memory — never a PI register. Expected after
             the ISR (CONFIRM): fired == 1, count == 1, reentry == 0; anything else stops the loop.
             Why the reuse is safe: the ISR can run only between __UnmaskIrq (UNMASK) and its own
             first instruction __MaskIrq; main touches the record only after its own re-mask and
             an INTMR read showing bit 13 = 0 (CONFIRM, PREPARE), so no IRQ 26 can be taken while
             main reads or resets the record — exclusive access follows from the mask state,
             which is read, not assumed, before every access. No generation counter, no slot
             array (the 004 multi-cycle body is not linked); no second ISR.

Records (compact, binary, preallocated; formatted only after the loop):
             cycle[320]  : idx, pending, irq_byte0, irq_off2_g0, t_cause, t_unmask, t_entry,
                           latency, t_read, audio {selected, attempted, completed, rc, slot,
                           t_start, t_end, wait, crc32 when completed}, video {selected, attempted,
                           completed, rc, seq, t_start, t_end, wait}, ack {attempted, completed,
                           t_after}, pi {intsr_postack, main_w1c, intsr_after}, rearm {attempted,
                           completed, t_after}, wait_next {next_cause_observed, t_next, polls,
                           ended_by: cause / t_next_cause / admission_deadline}, isr {fired, count,
                           reentry, intsr_entry, intmr_entry, intsr_after_w1c}, flags (verify /
                           end reason)                                                      (~104 B)
             vblock[88]  : seq, cycle, pending, t_start, t_end, dt, wait, rc, crc32,
                           raw_first4[4], flag_gbi, flag_disc, flags_agree, byte0_exceptions,
                           undoubled_words (computed after the loop)                       (~48 B)
             ablock[320] : cycle, selected, attempted, completed, rc, slot, dt, crc32, first_word,
                           nonzero, unit0_nonzero                                          (~32 B)
             Buffers: `static uint8_t video_blocks[88][0xF00] ALIGN(32)` (337 920 B),
             `audio_first[8][0x1000]`, `audio_last[2][0x1000]` (ping-pong), all 32-byte aligned,
             bounds checked before each DMA; no malloc; no overwrite of a captured VIDEO block.

Frame-start predicates (recorded per VIDEO block, both, from raw_first4, raw never corrected):
             gbi_frame_start  := (u32_be(raw_first4) & 0x80800000) == 0x80800000
                                 — bit 7 of byte 0 AND bit 7 of byte 1 (GBI `FUN_8000BF30`)
             disc_frame_start := ((u16_be(raw_first4[0..1]) >> 7) & 1) != 0
                                 — bit 7 of byte 1 (Disc `FUN_8008A588`)
             flags_agree      := gbi_frame_start == disc_frame_start
             Note: gbi ⇒ disc by construction (GBI's condition contains the Disc's); disc = 1 with
             gbi = 0 means byte 1 has the bit and byte 0 does not — relevant precisely because the
             observed variability sits in byte 0 (GBP-HW-061, U-GBP-029). Neither predicate is
             chosen as the physical truth; both lists are reported.

AUDIO policy: AUDIO is drained on every cycle it is pending (before VIDEO, the references' order)
             and never left pending to simplify VIDEO. Raw preservation: the first 8 SUCCESSFUL
             AUDIO drains (audio_first[k], k advances only on rc == ok) and the LAST SUCCESSFUL
             one: drains beyond the first 8 alternate between audio_last[0] and audio_last[1];
             last_valid points to the buffer of the last COMPLETED drain and is updated only after
             the completion was seen (rc == ok, completion flag observed); a timeout / error lands
             in the other buffer and never overwrites the last valid capture nor is attributed to
             it. Per cycle the metadata records selected, attempted, completed, rc, slot, crc32
             (only when completed), first word, unit-0 statistic; the sidecar's AUDIO table
             carries them for every drain and names the cycle of each raw block kept.

Log:         one line per cycle (`CYC n=… pend=… lat=… isr=… a=… v=… ack=… pi=… rearm=… next=…
             end=…`), one per VIDEO block (`VBLK seq=… cyc=… dt=… crc=… f4=… gbi=… disc=… agree=…
             x0=… und=…`), the AVSVC records for the verify cycles, summaries (`SEQ`, `BOUNDARIES
             gbi=…`, `BOUNDARIES disc=…`, `SOURCES`, `TIMING`, `COUNTERS`, `ADMISSION` (t0,
             deadline, the reason and time of the last refusal), `MATRIX`, `RESTORE`), anomalies
             in detail only when they occur; ring ≥ 640 lines × 192 bytes; nothing formatted
             inside the loop; the ISR unchanged.

Sidecar:     a NEW sequence format (magic `OGBPSEQ1`, format 3 of the family; v2 untouched):
             256-byte header (identities as v2: Test ID / Build ID / app / commit, 32 bytes each,
             never truncated; tb_hz; counts: cycles, video blocks, audio drains, audio raw kept;
             sizes 0xF00 / 0x1000; section offsets; end reason and next_cause_at_end; flags;
             header CRC-32), the cycle table, the VIDEO table (per block: seq, cycle, pending,
             t_start, t_end, wait, rc, raw_first4[4], flag_gbi, flag_disc, flags_agree, CRC-32),
             the AUDIO table (per drain: cycle, selected/attempted/completed, rc, slot, dt,
             CRC-32, first word), the raw VIDEO blocks contiguous in sequence order, the raw
             AUDIO blocks kept (first 8 + last valid, each named by its cycle), footer
             `OGBPEND1` + CRC-32 of everything before it. Deterministic layout; partial saves
             carry the actual counts. Written on X after the log, as in AVSVC.

Failure policy (SERVICE failed): unexpected source, cause without source, DMA busy / timeout /
             error, ACK or re-arm write not completed, PI sticky after one W1C, reentry / missed
             entry / bad ISR state, record or buffer capacity reached before a cap (defensive) →
             stop the loop → bounded teardown (CONTROL restore, STOP word `read | 0x8AAA`, PI
             cleanup ≤ 1 W1C, handler restore, AR_INFO restore) → save everything captured so
             far. No run is discarded for a late failure. The caps, the admission deadline and
             the next-cause timeout are NOT failures; neither is a cause latched but not admitted.

Result matrix (every dimension always reported; the main status never hides one):
             SERVICE            ok / failed(<reason>)          — repeated service: exactly one ISR
                                entry per admitted delivery, 0 reentry, 0 unexpected source, 0
                                uncertain writes, 0 DMA timeout / busy / error, every admitted
                                cycle's ACK and re-arm completed, INTMR13 == 0 in every main read
             CAPTURE            target_reached / delivery_cap / runtime_cap / no_next_cause /
                                early_failure, with counts (deliveries, video blocks, audio drains)
                                and next_cause_at_end (yes / no: a cause latched when the loop
                                ended, acknowledged by the teardown, never counted as a delivery)
             BOUNDARIES_GBI     count + positions[] (sequence indices) + intervals[]
             BOUNDARIES_DISC    count + positions[] + intervals[]
             COMPLETE_INTERVAL  yes / no per predicate: yes iff count ≥ 2 (two consecutive true
                                predicates in the captured sequence give a complete interval); the
                                interval's length is the observation — 40 is the references'
                                hypothesis, NOT a requirement; N ≠ 40 is an important physical
                                result, never a failure; 0 or 1 boundary in 88 blocks leaves the
                                objective "complete frame interval observed" unsatisfied with the
                                capture operationally valid
             REFERENCE_CONTENT  full_match / partial_match / mismatch / insufficient_data —
                                computed OFFLINE by the host tool (below), never by the probe,
                                never a gate for SERVICE or CAPTURE
             RESTORE            ok / failed
             Main status (from SERVICE, CAPTURE and RESTORE only):
               ok_video_sequence_capture          SERVICE ok, CAPTURE target_reached, RESTORE ok,
                                                  raw blocks preserved, sidecar intact
               ok_target_not_reached_delivery_cap SERVICE ok, CAPTURE delivery_cap, RESTORE ok
               ok_target_not_reached_runtime_cap  SERVICE ok, CAPTURE runtime_cap, RESTORE ok —
                                                  with next_cause_at_end yes (a cause latched
                                                  after the last re-arm, admission refused) or
                                                  no (the deadline arrived during WAIT_NEXT
                                                  without a cause: "no next cause before the cap")
               observation_no_next_cause          SERVICE ok up to the last admitted cycle, the
                                                  device produced no cause within T_NEXT_CAUSE
                                                  with admission budget left
               <failure statuses>                 SERVICE failed (anomaly_* / *_dma_* /
                                                  *_write_failed / abort_*), CAPTURE early_failure
               plus restore_failed variants when the teardown did not restore
             Bytes that do not match the embedded idle screen are NEW EVIDENCE, not a failure.
             Example (not a failure): cycle N completed and its re-arm succeeded, WAIT_NEXT saw
             the next cause latched, the admission deadline expired before the next UNMASK →
             SERVICE ok, CAPTURE runtime_cap, next_cause_at_end yes, deliveries unchanged, the
             teardown's CLEANUPCHK acknowledges the latched cause with its single W1C.

Content oracle (offline, `tools/avseq.py`, after the run): using the boundary lists (per predicate)
             to align blocks to frame positions, compare block by block the physical payload
             transformed as the references do (bytes 1/3 → 16-bit, bit 15 forced, 4×4 tiled) with
             the Disc's embedded frame, and the GBI-style per-block checksum with GBI's tables; the
             reference data is read from the private inputs at tool run time (`input/extracted/…`
             at the documented addresses) and is never stored in the repository. Report per
             predicate: matches_disc (blocks matched / compared), matches_gbi, first_mismatch_block,
             first_mismatch_offset (byte offset inside the transformed block), and the verdict
             full_match (a complete frame matched block by block) / partial_match / mismatch /
             insufficient_data (no complete interval); when no boundary exists, a phase search
             over the 40 alignments is reported separately as best_phase, never applied silently.
             The tool also lists the blocks and both boundary lists, assembles a tentative frame
             under the references' interpretation and under alternatives side by side, and writes
             a PNG only under an explicit interpretation label. Our capture's checksums and the
             comparison results are ours to record; the references' assets stay private.

Color status: geometry and byte picking are statically strong in both references (GBP-VID-002/
             003). The color naming stays CORROBORATED. If VIDEO-001 captures a complete idle
             frame and the transformed physical frame equals the Disc's RGB5A3 frame byte for
             byte, that raises confidence and is documented as such; whether it is enough for a
             promotion or the controlled cartridge stays necessary is decided after the run, not
             now.

Cartridge:   NONE (Link Port untouched, BBA idle, no Game Pak): the AGB's idle screen is a known
             frame in both references — transport, order and boundaries are testable against
             it offline; a cartridge adds a moving image and content unknowns. A controlled
             cartridge or test ROM comes with VIDEO-002 for the pixel semantics only.

Procedure (once implemented, audited on a clean commit, hash recorded, authorized):
             1. Copy the DOL to the SD card, launch through Swiss, GBP attached, no Game Pak.
             2. Do not touch anything until the screen reports the status (≤ 6 s worst case).
             3. Press X once (log, then the sequence sidecar ≈ 0.4 MB), press START, power OFF.
             Expected files: sd:/open-gbp/GBP-VIDEO-001_video-0001.log and
             sd:/open-gbp/GBP-VIDEO-001_video-0001-seq.bin.

Risks:       the first sustained loop (bounded by the admission budget, the caps and the
             per-operation timeouts); AUDIO blocks overwritten by the device when a cycle lags
             (harmless for this experiment, visible in the cadence); a missed VIDEO block (the
             predicates resync the offline alignment; the sequence shows the gap); no KEYPAD
             writes (if the device needs them to keep streaming, the loop ends by T_NEXT_CAUSE —
             a finding, observation_no_next_cause); an SD write of ≈ 0.4 MB after the run; ring or
             table capacity (bounded, ends the loop with the data kept); byte-0 extras inside
             blocks (never decide; recorded per block with both predicates).
```

Implementation notes (2026-09-16, what the code added to the design above; nothing
here is a physical result):

- **No new ISR.** The 003B extended one-shot is installed ONCE and reused; between
  deliveries its record is cleared through a new transport operation
  `irq_record_reset` — **memory only**, refused by the real backend
  (`src/platform/hsp_backend_irq.c`) while INTMR bit 13 reads 1, and refused when no
  handler is installed. Both handler bodies are byte-identical to the
  GBP-AV-SERVICE-001 build's, pinned by `tests/host/test_isr_audit.py`; the ISR audit
  reports CLEAN (82 instructions, only `__MaskIrq` called, one INTSR store of 0x2000
  after the mask, no INTMR store).
- **The delivery step was split** into `gbp_irq_service_deliver_quiet` (transport
  operations and values only) and `gbp_irq_service_deliver_log` (formatting).
  `gbp_irq_service_deliver` is now the two in sequence, byte-identical to before —
  the physical 003B / 004 / AVSVC fixtures still replay unchanged. The probe calls
  the QUIET variant only: nothing is formatted between the unmask and the re-mask.
- **CHECK_ADMISSION is evaluated before the cycle record is bound**, so a full cycle
  table ends the loop as `delivery_cap` (a normal end), never as a capacity failure.
  A refused cycle performs no record reset and no PI access at all.
- **Log:** each cycle is five compact records formatted after the loop — `CYCU`
  (admission, PREPARE, the unmask), `CYCW` (the bounded wait and the re-mask), `CYCH`
  (the handler record in a replay line's field order), `CYCD` (the pending read, the
  drains, the ACK) and `CYCR` (PI clean, the re-arm, WAIT_NEXT) — plus a `RAW READ-n`
  line carrying the pending read verbatim (lean cycles only; a verify cycle's PRESVC
  snapshot already logged it). The design said "one line per cycle"; five carry every
  transport value, which is what lets a physical log regenerate a replay fixture.
  `tools/probelog.py` turns them into the same operation stream a verify cycle's
  detailed records produce, and skips a verify cycle's compact records so no
  operation is emitted twice. Ring: 3000 lines x 256 bytes in the POC — sized from the worst
  reachable demand (2614 lines measured, ~2658 derived: 320 deliveries with VIDEO on part
  of them), because a dropped line would break the log -> fixture -> replay chain.
- **Boundary lists too long for one line** are emitted as a `BOUNDARIES … positions=BPOS
  intervals=BINT` summary followed by chunked `BPOS` / `BINT` lines: nothing is truncated.
- **Six IRQ-register write sites**, not five: 3 in the stage (A1/A2/STOP), 1 in the
  shared service (the verify cycles' ACK, which also takes the POSTACK snapshot) and
  2 in the probe (the lean cycles' ACK, written without any formatting, and the
  re-arm). Pinned by `tools/poc_audit.py --profile video`.
- **The physical GBP-AV-SERVICE-001 fixture replays as the exact prefix of cycle 0**
  (`tests/unit/test_gbp_video.c`): with `max_deliveries = 1` all 132 of its operations
  are consumed in order, 0 mismatches, 0 exhaustion, the physical blocks delivered from
  its sidecar, the second cycle refused at the admission point, `next_cause_at_end = yes`
  and the latched cause acknowledged by the teardown's single W1C. That physical run is
  literally one cycle of this loop.
- **The offline oracle is real and anchored.** `tools/avseq.py` implements GBI's
  per-block checksum (the repacked byte 1 : byte 3 words accumulated in 64 bits, stored
  as the low 32 bits **plus the carry count**) and reproduces `0x7F0FFF10` for the
  physical GBP-AV-SERVICE-001 block — the value VIDEO_PATH.md §6 records as entry 0 of
  both of GBI's reference tables. Read at run time from the private inputs (never
  stored here), table A has content in blocks 14–25 and table B in 12–19, and the
  Disc's embedded frame at `0x801B45A0` reads white at its start: all three match the
  static description exactly. Without the private inputs the verdict is
  `reference_content=unavailable`.
- **Not promoted.** Nothing above is a physical result for GBP-VIDEO-001. The 40
  blocks per frame, the colour order and the physical block format remain as
  `docs/research/EVIDENCE.md` classifies them today.


Host tests added with the implementation (mock scenarios, every one a
bounded synthetic run; none is physical evidence): (1) a true predicate on
the first block; (2) the first true predicate on block 39 (0-based) and the
second on 79 — the worst-case phase that 88 still covers; (3) two flags 40
apart; (4) two flags N ≠ 40 apart — reported as an interval, SERVICE ok; (5)
one flag in 88 blocks — COMPLETE_INTERVAL no, main status unchanged; (6)
zero flags in 88 — same; (7) Disc = 1 / GBI = 0 (byte 1 bit 7 set, byte 0
clear) — both recorded, flags_agree = 0, no correction; (8) Disc = 1 / GBI =
1; (9) byte 0 altered without byte 1 (extras) — predicates unchanged when
byte 1 is unchanged, exceptions counted; (10) record reuse over ≥ 320 cycles
with the invariants checked before every unmask; (11) the PI latch preserved
between cycles — the mock asserts no INTSR write between WAIT_NEXT and
UNMASK; (12) no main W1C between the next cause and the next unmask (any
write there fails the test); (13) delivery cap before the target →
`ok_target_not_reached_delivery_cap`, the latched cause left for the
teardown; (14) runtime cap before the target → `ok_target_not_reached_runtime_cap`;
(15) the last valid AUDIO buffer preserved when the next AUDIO drain fails
(ping-pong, last_valid unchanged, the failed cycle's metadata says completed
= 0). Admission-budget cases: (16) the deadline already reached before the
first new cycle after t0 → zero new deliveries, CAPTURE runtime_cap; (17)
pending = 0x0500 with the deadline expiring during the AUDIO DMA → VIDEO
still drained, ACK 0x8500, re-arm written, then runtime_cap at the next
admission; (18) the deadline expiring after AUDIO and before VIDEO → same
property; (19) the deadline expiring during the VIDEO DMA → the cycle ends
bounded (its own T_DMA), ACK and re-arm written; (20) the next cause latched
before the deadline but the deadline expiring before the next UNMASK → no
new delivery, deliveries unchanged, the cause preserved and acknowledged by
the teardown, next_cause_at_end = yes; (21) the deadline expiring during
WAIT_NEXT without a cause → runtime_cap with next_cause_at_end = no, no
additional unmask; (22) never a partial ACK for pending = 0x0500 (the mock
asserts the ACK value equals pending | 0x8000 in every cycle, whatever the
clock); plus reentry (count = 2), missed entry, cause without source,
unexpected source, PI sticky, no next cause, target reached with a cause
latched after the last re-arm (final observation, no unmask, teardown
acknowledges), and the physical AVSVC fixture as the prefix of the first
cycle.

Files created by the implementation: `src/gbp/gbp_avseq.{h,c}` (the bounded
sequence core: records, buffers, both predicates, the boundary lists, the
compact log lines), `src/gbp/gbp_video_probe.{h,c}` (the state machine with
its admission point, statuses, matrix, teardowns, summaries),
`src/gbp/gbp_avseqdump.{h,c}` (the `OGBPSEQ1` sidecar),
`poc/gbp-video-capture-probe/` (Test ID `GBP-VIDEO-001`, Build ID
`video-0001`, prefix `OPENGBP-VIDEO`), `tools/avseq.py` (parser; cycle,
block and boundary listings; the offline oracle; frame grouping under the
references' hypothesis), mock extensions (a per-re-arm cause sequence, the
VIDEO first-four-bytes flag model with its three styles and a byte-0 extra,
per-read bulk failures, a scripted clock for the admission cases, the
record-reset operation and the "no main W1C between the re-arm and the next
unmask" detector), `tests/unit/test_gbp_avseq.c`,
`tests/unit/test_gbp_video.c`, `tests/host/test_avseq.py`,
`tests/host/test_video_replay.py`. Still future: the executed entry here,
EVIDENCE GBP-HW-06x, VIDEO_PATH.md §6–8 updates, `docs/protocol/VIDEO.md`
once physical, REGISTERS.md §2.2 — all of them only after a physical run.

---
### GBP-VIDEO-002-R3 (build `vstate-0003`) — service the IRQ window under semantic disagreement without ending the run — DESIGNED, HARDENED and IMPLEMENTED 2026-09-17; PHYSICALLY EXECUTED 2026-09-17; **PHYSICAL VALIDATION COMPLETE 2026-09-17 through the R4 re-run**

Two physical runs of GBP-VIDEO-002 ended on the same condition: one 32-byte read
of the IRQ window whose eight replicas did not all carry the same value. The
second preserved the bytes (GBP-HW-089…092) and the abort is now fully
characterised. This revision exists to make that condition survivable **without
losing evidence and without inventing semantics**, so that the 120 s scientific
window and, after it, GBP-VIDEO-003 become reachable.

**PHYSICALLY EXECUTED 2026-09-17** (commit `8c25df2`, DOL SHA-256
`baea30f5…b486`, log `9f81f19f…2e57` 86 378 B, sidecar `0a45d487…e6bc`
4 359 724 B). Result:

```text
GBP-VIDEO-002-R3 vstate-0003 PHYSICALLY EXECUTED
SCIENTIFIC TARGET REACHED — 120.009 s of valid observation in 175.848 s of capture
SERVICE ok, RESTORE ok, structured change OBSERVED (9 episodes, 7 stable)
23 SEMANTIC DISAGREEMENTS, ALL SOURCE_SERVICED, ALL SURVIVED (GBP-HW-100)
  the omitted AUDIO source was present in the next ordinary read 23/23 (GBP-HW-102)
DIAGNOSTIC CURRENT-CYCLE ATTRIBUTION FAILED — known producer defect (GBP-HW-104)
```

**PHYSICAL VALIDATION COMPLETE (2026-09-17).** R3's own run left the policy
strongly corroborated and its diagnostic attribution unproven, because the records
it produced were contaminated by the producer defect described below. The
`vstate-0004` run (GBP-VIDEO-002-R4) closed exactly that gap on the same hardware,
with the same policy and the same device operations: **29 `SOURCE_SERVICED`
disagreements, none fatal, every one carrying the authoritative value, service
decision, ACK and re-arm of its own cycle, in a sidecar that strict-validates
under the v5 cross-field rules** (GBP-HW-108…115). Every condition of §R3.21 is
now met:

```text
>= 1 SOURCE_SERVICED observed                   29
the run did not stop for them                   stop=nominal_negative
current-cycle attribution correct               29/29, 0 invariant failures
sidecar strict-valid                            C and Python v5 parsers
service continued                               1 114 005 cycles, errors=0
ACK and re-arm coherent with the record         29/29, t <= t_ack <= t_rearm <= t_next
follow-up per source correct                    29/29 PRESENT, absent = 0x0000
zero unexpected SOURCE_OTHER / NON_SOURCE       0 and 0
valid target reached                            120.009 s of 120 s
restore ok                                      handler restored, INTMR clean
```

One criterion was **conditional and did not arise**: no majority-extra
disagreement occurred in either run, so the quarantine path has never been
exercised physically. It stays host- and mock-tested, and nothing here claims
otherwise.

**The policy worked and the bookkeeping did not, and the two must not be
conflated.** The run is the first of this test to reach its target, the first to
survive a semantic disagreement at all, and it survived twenty-three. But the
records it produced carry `authoritative_value`, `service_selected`, `ack_value`,
`t_ack` and `t_rearm` belonging to a *later* cycle, so the versioned success
criterion of §R3.21 — that each event's ACK and re-arm be preserved — is **not**
satisfied. R3's physical validation was therefore **INCOMPLETE at the time of its
own run**; the policy behaviour was **strongly corroborated** (GBP-HW-106) and the
diagnostic fidelity objective **failed**. The R4 re-run above is what completed
it — and it completed it by re-observing the same policy on hardware, not by
argument.

Root cause, in the committed source: `gbp_vstate_diag_service()`,
`_ack()`, `_rearm()` — and equally `_payload()`, `_quarantined()`, `_deferred()` —
address `diags[diags_n - 1]`, "the newest record", and are called on **every**
service cycle. A record therefore keeps absorbing later cycles until the next
disagreement opens a new one. The fix is `vstate-0004` / OGBPSEQ1 v5, designed
below; it is RAM bookkeeping only and touches no hardware ordering.

Evidence: GBP-HW-098…107. The trusted/untrusted field split is GBP-HW-105, and it
follows from the number of write sites in the code, not from the data.

**Implementation status, 2026-09-17.** The design below is now implemented in
`src/gbp/gbp_vstate.{h,c}`, `src/gbp/gbp_vstate_probe.c`,
`src/gbp/gbp_vstatedump.{h,c}`, `poc/gbp-video-state-probe/` (Build ID
`vstate-0003`) and `tools/vstate.py`, with the host battery in
`tests/unit/test_gbp_video_state.c` and `tests/host/test_vstate.py`, and it **has
now been executed on hardware** (the result block above; evidence
GBP-HW-098…107). Its synthetic scenarios remain synthetic and are still not
evidence about the device; only the physical run is. The measured cost is in
R3.15. What follows is the specification the implementation was built to match,
and it stays the authority for R3 — including for the criterion the run did not
meet.

#### R3.1 The masks, taken from the versioned contract — not invented here

`docs/protocol/REGISTERS.md` §4 and the probe configuration already partition the
16 bits, and the four masks are exhaustive and disjoint
(`0x0555 | 0x0AAA | 0x7000 | 0x8000 = 0xFFFF`):

```text
SRC_MASK    0x0555   even bits 0,2,4,6,8,10 — the callback/source slots; the Disc's
                     own dispatch mask is `pending & 0x0555`
AV_MASK     0x0500   VIDEO 0x0100 + AUDIO 0x0400 — the two sources THIS experiment
                     services, and the only two whose full lifecycle is physically
                     established (observed pending, observed cleared by an ACK that
                     writes them as 1, observed re-delivered when not written)
ODD_MASK    0x0AAA   the "mask" bits paired with each source
HIGH_MASK   0x7000   bits 12-14, never observed set, never written
BIT15_MASK  0x8000   the entry/stop bit
```

Physical W1C evidence exists for `0x0004` (GBP-HW-028), `0x0100` and `0x0400`
(every ACK of GBP-AV-SERVICE-001, GBP-VIDEO-001 and both GBP-VIDEO-002 runs).
`0x0001`, `0x0010` and `0x0040` are source slots in the references' code and have
**never been observed set on this hardware**.

#### R3.2 The order of checks — the pending guard is independent of the delta

This ordering is normative, and it is the part most easily got wrong. Classifying
the disagreement does **not** replace any existing check; it is inserted between
them.

```text
1. transport            rc != GBP_OK                       -> FATAL (unchanged)
2. compose              authoritative per R3.3 (needs the non-source bits to agree)
3. shape / non-source   delta touches ~SRC_MASK             -> FATAL  NON_SOURCE
4. source class         delta touches SRC_MASK & ~AV_MASK   -> FATAL  SOURCE_OTHER
5. PENDING GUARD        (authoritative & SRC_MASK & ~AV_MASK) != 0
                                                            -> FATAL  anomaly_unexpected_source
6. disagreement class   delta != 0 and (delta & ~AV_MASK) == 0
                                                            -> NONFATAL SOURCE_SERVICED
7. service              drain the sources in authoritative & AV_MASK
```

Step 5 fires **on the authoritative value, whatever the delta is — including
`delta == 0`**. A read where both interpretations agree on `0x0104` is still fatal
`anomaly_unexpected_source`, exactly as today, because `0x0004` has no drain in
this probe. Nothing about the disagreement machinery weakens that guard, and the
test plan pins the `Disc = 0x0104, GBI = 0x0104, delta = 0x0000` case explicitly
(R3.22).

Classification, for the record:

```text
SOURCE_SERVICED    delta != 0 and (delta & ~AV_MASK) == 0     -> NONFATAL
SOURCE_OTHER       delta ⊆ SRC_MASK, (delta & ~AV_MASK) != 0  -> FATAL
NON_SOURCE         (delta & ~SRC_MASK) != 0                   -> FATAL
```

`SOURCE_OTHER` stays fatal for the same reason step 5 exists: such a source ends
the run under an independent rule anyway, and relaxing the disagreement rule there
would open a path past a source with no drain.

#### R3.3 Authority — and exactly how the u16 is composed

The rule is **not** "use the majority value". It is:

```text
outside SRC_MASK   the two readings MUST AGREE. They are not voted, not merged and
                   not chosen between: if they differ the class is NON_SOURCE and
                   the run ends. The value used is the agreed value, so no
                   semantics is invented for a field whose contract is open.
inside SRC_MASK    authoritative_sources = gbi_value & SRC_MASK   (bitwise majority)

authoritative = (agreed_value & ~SRC_MASK) | authoritative_sources
```

The Disc's last-replica value is **never overwritten and never discarded**: it is
carried in every record as `disc_value`, with `delta`,
`disc_extra_sources = disc & ~gbi & SRC_MASK` and
`majority_extra_sources = gbi & ~disc & SRC_MASK`.

**This is a design decision with a physical basis, not a FACT about what the
hardware intends.** It is a deliberate divergence from the Start-up Disc's
last-replica policy, recorded as such, and the basis is R3.5.

The probe **already** derives its service value from the GBI reading at both read
sites (`gbp_vstate_probe.c:937` and `:960`); today it simply refuses to proceed
unless the Disc reading agrees. R3 removes that refusal for `SOURCE_SERVICED` and
keeps everything else.

#### R3.4 ACK

Unchanged in form: `ack_value = authoritative | BIT15_MASK`. Only the source bits
of `authoritative` can differ from today's value, and only in a `SOURCE_SERVICED`
disagreement. The re-arm stays `IRQ := 0x0000`. No second read, no retry, no
re-read of any kind (R3.14).

#### R3.5 The two directions are not symmetric

**Disc extra — the observed case.** `gbi = 0x0100`, `disc = 0x0500`,
`disc_extra_sources = 0x0400`. The runtime services VIDEO, acknowledges `0x8100`
and re-arms. The AUDIO bit is never written as 1, so by GBP-HW-028 it is not
cleared; if it was genuinely asserted it stays pending, and GBP-HW-096 recorded
what followed a comparable re-arm: the next cause **74 ticks (1.83 µs)** later,
against AUDIO-source gaps of **9 885 to 11 303 ticks (244.1 to 279.1 µs)**
previously observed in that same run — **134× to 153× shorter, about 2.1 orders of
magnitude, far shorter than any previously observed AUDIO-source gap in that
run**. That is a description of what was measured. It is **not** a lower bound on
how soon a genuinely new source may arrive: no such bound has been established,
and none is claimed anywhere in this design.

**Majority extra — never observed.** `gbi = 0x0500`, `disc = 0x0100`,
`majority_extra_sources = 0x0400`. Here the majority would be the stale side if
five or more replicas carry a source the device has already cleared. Two distinct
consequences, and both are treated as open:

* the runtime drains a block the device may not have republished — handled by
  R3.11 (SUSPECT marking) and R3.12 (VIDEO quarantine);
* the ACK writes 1 to a source bit whose last replica reads 0. **GBP-HW-028 does
  not cover this**: it established only that writing 1 to a bit that *reads 1*
  clears it. The 1-on-0 case has never been exercised on this hardware, and this
  design does not assume it is a no-op. It is carried as an open item (R3.23) and
  the record preserves everything needed to describe the first occurrence: the
  `majority_extra` bit, the ACK value, the drained block's identity, the next
  cause and the next cycle's ordinary reading. **No extra read is performed to
  investigate it.**

**Both directions at once** is possible — `gbi = 0x0100`, `disc = 0x0400` gives
`delta = 0x0500` with one extra on each side — and the record carries the two
directions separately rather than a single signed difference.

#### R3.6 The follow-up episode — fields

Every nonfatal disagreement produces one bounded record, filled **only** from
values the normal path already produces. No extra hardware read exists to complete
a diagnostic, and a field that was not measured is written as a documented
sentinel rather than as a plausible number.

```text
from the disagreement cycle   cycle, t, raw32 verbatim, disc_value, gbi_value,
                              delta, disc_extra_sources, majority_extra_sources,
                              classification, authoritative, ack_value,
                              service_selected, read_kind, intsr/intmr/latency/
                              xfer/dma context (as in v3), frame_index,
                              block_in_frame, t_ack, t_rearm
from the NEXT cycle           t_next_cause, rearm_to_next_ticks,
                              next_pending_gbi, next_pending_disc, next_delta,
                              followup_state
gap statistics (this run)     min_gap_ticks / max_gap_ticks / count, per source,
                              as measured BEFORE this event — carried as data,
                              never as a threshold
```

`next_pending_disc` costs nothing: the next cycle's own read computes both
readings anyway.

#### R3.7 Follow-up states — factual only

The runtime records **what was observed**, never an inference about identity:

```text
FU_PENDING                 the record exists; the next cycle has not happened yet
FU_SOURCE_PRESENT_NEXT     EVERY omitted source was present in the next cause
FU_SOURCE_ABSENT_NEXT      at least one omitted source was NOT present, which
                           includes the partial case
FU_NO_NEXT_CAUSE           the run ended before a next cause
FU_UNKNOWN                 the follow-up could not be determined (documented reason)
```

**An event can omit more than one source, and the aggregate state must never be
read as more than it says.** `FU_SOURCE_PRESENT_NEXT` means *all* of them were
back; anything less is `FU_SOURCE_ABSENT_NEXT`, which therefore covers "none came
back" and "some came back" alike. That is deliberate: the aggregate can never
over-claim recovery. The exact split is always derivable from two stored fields
and is never guessed:

```text
present = disc_extra_sources &  (next_pending_gbi & SRC_MASK)
absent  = disc_extra_sources & ~(next_pending_gbi & SRC_MASK)
```

`tools/vstate.py` prints both masks and flags the partial case explicitly, and the
GBP-VIDEO-003 release analysis (§R3.21) must read those masks, **not** the
aggregate state alone.

**Which authority the comparison uses.** The next read's *authoritative source
set* — `next_pending_gbi & SRC_MASK`, the same reading the service loop acts on.
The next read's Disc value is stored beside it and is never consulted for this
decision: mixing the two authorities inside one series is the conflation this
whole policy exists to avoid. When the next read is itself `SOURCE_OTHER` or
`NON_SOURCE`, its own classification must be read alongside — the record preserves
both values so that is always possible.

There is **no runtime classification derived from a divisor of the observed gap**,
no `min_observed_gap / 8`, and no label asserting that a source "could not be
fresh". An earlier draft of this design had one; it was wrong, because it turned
the smallest gap a run happened to observe into a physical lower bound.

What is persisted so the offline tool can reason: `rearm_to_next_ticks`, the
presence or absence of each source in the next cause, and this run's own gap
statistics per source up to that moment. The quantitative comparison — "this
latency is N× shorter than the shortest gap seen so far" — is computed **offline**
by `tools/vstate.py`, presented as a ratio, and never stored as a verdict.

#### R3.8 Follow-up lifecycle, including consecutive disagreements

Each record has an explicit lifecycle, and the ordering when disagreements occur
back to back is normative:

```text
OPEN            created at the disagreement, follow-up fields = sentinel
WAIT_NEXT       the cycle closed (ACK, re-arm) and t_rearm is recorded
FILLED          the NEXT cycle's read supplied the follow-up fields
CLOSED_NO_NEXT  the run ended first -> FU_NO_NEXT_CAUSE
```

At most one record is in `WAIT_NEXT` at any time. When cycle *n+1* also disagrees,
the order is mandatory and not negotiable:

```text
1. use cycle n+1's normal read to FILL the follow-up of record N;
2. only then create record N+1 from that same read;
3. record N+1 enters WAIT_NEXT and waits for cycle n+2.
```

One read therefore serves two roles — it closes the previous record and opens the
next — and never fills the wrong one. Three consecutive disagreements
(N, N+1, N+2) are a required test case (R3.22).

#### R3.9 Store full and a pending follow-up

When `MAX_DISAGREEMENTS` has been reached, no new full record is created and the
counters continue. **Store-full must not prevent a record that already exists from
being completed.** The record in `WAIT_NEXT` is finalised from the next cycle's
read exactly as it would have been, and only the creation of a *new* record is
suppressed. The case "store full, last preserved record still waiting" is a
required test (R3.22).

#### R3.10 Read sites, and what a follow-up may support

```text
LEAN READ   selects service      -> majority-authoritative; SOURCE_SERVICED nonfatal;
                                    a full follow-up chain is meaningful here
PRESVC      selects service in a verify cycle -> same rule (it already uses the GBI value)
POSTDRAIN   observational        -> recorded and counted; never re-selects service
POSTACK     observational        -> same; its "source cleared" check compares against
                                    the authoritative value that was acknowledged,
                                    with the Disc value recorded beside it
```

A disagreement at an **observational** site is preserved and counted, but its
record carries `read_kind` and its follow-up state is `FU_UNKNOWN` with the reason
`observational_site`: the chain *omitted source → service decision → ACK → re-arm
→ next cause* did not happen there, and the record must not be readable as though
it had. Only disagreements from the read that actually selected service can carry
that narrative.

#### R3.11 Majority-extra service is SUSPECT

When `majority_extra_sources != 0`, the drains performed **only because of that
difference** are marked at the point of service:

```text
block flag   GBP_VSTATE_B_MAJORITY_EXTRA   on the AUDIO and/or VIDEO block drained
                                           for a source the Disc reading did not have
```

The service still happens — the policy is majority-authoritative and the design
does not want a second policy branch on the critical path — but the resulting data
**may not silently become scientific evidence**. For AUDIO, the bounded diagnostic
of R3.6 plus the block's CRC-32 and first word are kept, and nothing else changes,
because AUDIO payloads are not part of this experiment's scientific claim. For
VIDEO, R3.12 applies.

#### R3.12 VIDEO quarantine

A VIDEO block drained because the majority carried `0x0100` and the Disc reading
did not is quarantined, and so is the frame that contains it. This reuses the
frame-flag machinery that already exists rather than inventing a parallel one:

```text
new block flag   GBP_VSTATE_B_MAJORITY_EXTRA
new frame flag   GBP_VSTATE_F_MAJORITY_EXTRA  (set on the frame containing such a block)
consequence      the frame is ALSO treated as class (a) — GBP_VSTATE_F_ANOMALY:
                   * it never sets GBP_VSTATE_F_COUNTED, so its duration does not
                     enter valid_observation_elapsed;
                   * it is rejected as a baseline candidate and can never set
                     GBP_VSTATE_F_BASELINE;
                   * it cannot open, close or validate a structured-change episode;
                   * GBP-VIDEO-003 must exclude it from colour evidence.
preserved        its 40 signatures and, within the existing raw budget, its raw
                 blocks: the quarantine removes it from the scientific path, not
                 from the record
resync           nothing special. The frame is closed by the next boundary like any
                 other, the assembler state is untouched, no block is fabricated,
                 and the next frame starts clean. If the quarantined frame was the
                 reference the baseline search was building on, the search simply
                 continues from the next eligible frame, exactly as it does after
                 any class (a) anomaly.
storage          no new raw storage: the quarantined frame competes for the same
                 bounded episode/raw budget as any other frame
```

#### R3.13 Disc-extra VIDEO — the deferred drain

The mirror case: the Disc reading has `0x0100` and the majority does not. The
runtime does **not** drain VIDEO in that cycle. If the source was real it is not in
the ACK, so it stays pending and is serviced when it is next delivered.

The frame assembler is not told anything special and **no block is fabricated**.
The interval simply contains one fewer VIDEO block at that point, and the existing
rules decide what that means: a short interval becomes `incomplete`, and the
boundary logic may declare `resync` — the same outcomes the assembler already
produces for any interval that does not contain 40 blocks. What R3 adds is a
correlation marker so the offline analysis can tie the two together:

```text
new frame flag   GBP_VSTATE_F_SOURCE_DEFERRED   a disagreement inside this frame
                                                deferred a VIDEO drain
```

The flag is descriptive. It does not change completeness, does not invalidate the
frame by itself, and does not claim the deferred block was later recovered.

#### R3.14 What does not change

No retry. No second read. No re-read. No extra device access of any kind for
diagnostic purposes. The device operation stream of a run without disagreements
must remain **identical** to vstate-0002's, and the stream of a run with them must
differ only by the service selection the majority dictates and its ACK value. The
ISR and the whole interrupt path stay byte-identical to the GBP-VIDEO-001 build.

#### R3.15 Bounded store and memory budget

Every item of new RAM this design knows about, and nothing hidden in a rounding:

```text
what                                      bytes    basis
----------------------------------------- -------- ------------------------------------
diagnostic array  256 x 160                40 960  R3.24, exact
delta / disc_extra / majority_extra hists   3 x 256    768  R3.27, exact
aggregate counters  21 x u32                    84  R3.27, exact
gap statistics in RAM  6 slots                 192  24 B on the wire + a u64 last_cause_t
                                                    per source, rounded to 32 B per slot
follow-up bookkeeping                           16  wait_index, wait_active, capped flag,
                                                    diag_count
----------------------------------------- --------
known subtotal                              42 020
estimated bookkeeping overhead                <256  alignment, any small field the
                                                    implementation needs that this design
                                                    did not name
----------------------------------------- --------
estimated_R3_increment                    ~42 020 to 42 276 B  (~41 KiB)
```

Per-frame and per-block markers (`F_MAJORITY_EXTRA`, `F_SOURCE_DEFERRED`,
`B_MAJORITY_EXTRA`) are **new bits in existing flag words** and cost no bytes.

The quantities, named precisely, because an earlier draft conflated two of them
and called a subtotal a total:

```text
resident_store_bytes        6 922 240 B  the probe's own stores (frames, events, raw ring,
                                         episode raw, audio raw, cycle buffers) as reported
                                         by gbp_vstate_static_bytes() and logged as
                                         `static_bytes` — NOT the program's static memory
measured_total_bss          7 472 388 B  the `.bss` of the CLEAN vstate-0002 ELF; `.sbss`
                                         is a further 1 804 B, and the DOL header's BSS
                                         region, covering both plus alignment, is
                                         0x720C10 = 7 474 192 B
estimated_R3_increment        ~42 020 B  the table above, including an explicitly
                                         estimated bookkeeping allowance
estimated_total_bss         ~7 514 408 B ≈ 7.166 MiB, BEFORE the linker's alignment
                                         padding. AN ESTIMATE, not a measurement
MEASURED after implementation (2026-09-17), reconciled symbol by symbol against a
baseline built from commit `caacbba` with the same toolchain in the same session:

```text
symbol            vstate-0002   vstate-0003     delta   what it is
diag_store                  0        40 960   +40 960   256 x 160, the bounded store
sb.0                        0         1 024   + 1 024   the semantic block's staging
                                                        buffer in gbp_vstatedump_stream
vstate                  4 248         5 184   +   936   struct gbp_vstate: the aggregate
                                                        counters, 6 gap slots and 3x64 histograms
res.2                   6 728         6 744   +    16   struct gbp_vstate_result: the two
                                                        new provenance fields
info.0                    504           512   +     8   struct gbp_vstatedump_info: the
                                                        three new v4 header fields
hdr.0 -> hdr.1            512           512   +     0   the same 512-byte header buffer,
                                                        renamed by the compiler
                                        sum   +42 944
inter-symbol padding   14 677 B      14 693 B  +    16   measured as (section - Σ symbols)
                                      TOTAL   +42 960
.bss                7 472 372     7 515 332   +42 960   exact, no residual
```

There is no "misc" term: the sum of the symbol deltas plus the measured change in
inter-symbol padding is the section delta exactly.

**Correction.** An earlier report of this project gave the vstate-0002 baseline as
`.bss = 7 472 388 B`. Rebuilding commits `8cbb28d` and `caacbba` now, with the same
command, both give **7 472 372 B**; the 7 472 388 figure was 16 bytes off and is
superseded. The increment is therefore 42 944 B (41.9 KiB), not 42 928.

The increment exceeds the design estimate of ~42 020 B by 940 bytes, which is the
allowance this design labelled `estimated bookkeeping overhead`; the largest single
item inside it is the 1 024-byte staging buffer, whose purpose is documented at its
definition in `gbp_vstatedump_stream()` — write-only, derived from `st->sem`
immediately before the emit, touched only after the teardown, never a second source
of truth for any counter. The linker map is the authority and
the estimate is not retrofitted to match it.

Largest stack frames, measured, against the same baseline:

```text
gbp_vstate_probe_run        568 B -> 568 B   the service loop did NOT grow
gbp_vstate_diag_open            - ->  96 B   only on a disagreement
gbp_vstatedump_stream       840 B -> 872 B   the 160-byte record buffer
gbp_vstatedump_parse_v4     920 B -> 928 B   (as parse_v3 before; now a 24-byte forwarder)
```

Nothing grows with the number of disagreements.
MEM1_headroom               unchanged in kind: see the GBP-VIDEO-002 memory note above.
                                         R3 moves the resident stores by ~0.61 % and
                                         `.bss` by ~0.56 %; neither is near any limit
```

`N = 256` is chosen from footprint, not from a predicted rate — two events in two
runs support no rate at all. For scale only: at the **denser** of the two observed
occurrences (1 in 518 deliveries) 256 records would cover the first ~132 600
deliveries, about 21 s of a 120 s run, after which the counters continue alone; at
the sparser (1 in 51 751) a full 120 s run would produce about 14. Nothing is
stored per normal delivery.

#### R3.15b Events, log lines and the report are bounded independently of the store

A semantic disagreement emits **no event into the event store**. The only
disagreement event in this runtime is `EV_PREDICATE_DISAGREEMENT`, which belongs
to the frame-start predicates and is bounded by blocks, not by semantic events.
This is deliberate and normative: a nonfatal condition that can occur on a large
fraction of cycles must not be able to fill a 4 096-entry store and convert itself
into an `event_store_cap` stop. The run of 681 disagreements used 9 event slots.

The ring log prints the first `GBP_VSTATE_DIAG_LOG_MAX` = 8 records in full (four
lines each) plus one summary line, and nothing else scales with the number of
disagreements — neither with `diagnostics_preserved` nor with
`diagnostics_not_preserved`. The aggregate counters and the gap statistics are
two fixed lines plus at most six. Every record still reaches the sidecar.

#### R3.16 Stop conditions

A `SOURCE_SERVICED` disagreement **does not stop the run**. The stop precedence is
otherwise untouched: fatal > safety_budget > frame/event_store_cap > scientific
target > no_next_cause > delivery_cap. `diagnostic_store_full` behaves exactly like
`episode_store_full`: it is a flag and a counter, never a stop.

#### R3.17 Status matrix

`SEMANTIC_COHERENCE` becomes an independent dimension, so that a run that saw
disagreements and serviced them correctly is not reported as a service failure:

```text
SERVICE              ok | failed(reason)
FRAME_CAPTURE        ok | partial | invalid
SEMANTIC_COHERENCE   uniform | source_disagreements_observed(N) | failed(class,reason)
STRUCTURED_CHANGE    observed | not_observed
RESTORE              ok | failed
SAVE                 ok | partial | failed
```

`SERVICE=ok SEMANTIC_COHERENCE=source_disagreements_observed semantic_disagreements=N`
is a **successful** run. A `NON_SOURCE` or `SOURCE_OTHER` disagreement gives
`SERVICE=failed reason=READ_non_source_semantic_disagree_cycle_N` (or
`READ_source_other_…`) with `SEMANTIC_COHERENCE=failed`.

#### R3.18 Counters

```text
semantic_disagreements_total      source_serviced_disagreements
source_other_disagreements        non_source_disagreements
disc_extra_source_events          majority_extra_source_events
both_direction_events             majority_extra_video_services
majority_extra_audio_services     frames_quarantined
frames_source_deferred            diagnostics_preserved
diagnostics_not_preserved         diagnostic_store_full (flag)
followup_present / absent / no_next / unknown
delta_hist[64] / disc_extra_hist[64] / majority_extra_hist[64]
per-source gap statistics: min / max / count / last
```

All fixed-size; none grows with deliveries.

#### R3.19 OGBPSEQ1 v4

The single-record v3 section cannot carry an array, so the sidecar becomes
**version 4**. v1 (GBP-VIDEO-001), v2 (vstate-0001) and v3 (vstate-0002) are
historical and frozen; each is dispatched by its own strict rules and none can be
read as another. **No v3 field changes meaning in v4** — v4 only adds:

```text
0x1E0 u32 off_diag        same meaning as v3 (now the start of the record ARRAY)
0x1E4 u32 diag_count      same meaning (0..MAX_DISAGREEMENTS)
0x1E8 u16 diag_rec_size   same meaning (160 in v4, 96 in v3)
0x1EA u16 diag_flags      NEW: bit 0 = store capped
0x1EC u32 off_semantic    NEW: the fixed semantic-coherence block
0x1F0 u32 semantic_size   NEW: 1024
0x1F4..0x1FB reserved, must be zero
0x1FC u32 header CRC
```

Section order, contiguous and checked as today:

```text
header / frames / events / episodes / cycles / SEMANTIC BLOCK (1024)
      / diagnostics (diag_count x 160) / video raw / audio raw / footer
```

The 1 024-byte semantic block holds the counters and the three 64-entry histograms
(768 B of histogram plus counters, zero-padded). **The complete, normative byte
layouts of the v4 record and of that block are R3.24 to R3.29 below**; they are
part of this design, not of the implementation. To be revalidated at
implementation: header offsets, strict version dispatch for 1/2/3/4, checked
arithmetic, full CRC coverage of both new sections, `diag_count == 0`,
`diag_count == MAX`, the store-capped flag, and reserved-area zeroing.

`diag_flags`: **bit 0 = store_capped** (sticky, set the first time a disagreement
is not preserved because the array was full). Every other bit MUST be zero in this
version, and the parser **rejects a file carrying an unknown flag bit** rather than
ignoring it — a future meaning must arrive with a version, not silently.

**Sizing, named precisely** (an earlier draft mislabelled this). The complete v4
sidecar is:

```text
size = 0x200                                   header
     + frame_count    x 192                    frame table
     + event_count    x  64                    event table
     + episode_count  x 512                    episode descriptors
     + cycle_count    x 128                    sampled cycles
     + 1024                                    semantic block          <- v4
     + diag_count     x 160                    diagnostic records      <- v4
     + Σ(preserved frames) blocks x 0xF00      raw VIDEO
     + audio_raw_count x 0x1000                raw AUDIO
     + 12                                      footer
```

and therefore:

```text
maximum v4 semantic/diagnostic EXTENSION payload = 1 024 + 256 x 160 = 41 984 B
```

That is the **extension only**, not a maximum sidecar size: the file's total is
dominated by the preserved raw and the frame table, and a full-length run is
expected in the megabytes (the GBP-VIDEO-002 design note estimates ~6.3 MB for a
120 s run). No maximum total is invented here, because it depends on stores this
design does not change.

#### R3.20 The physical objective of vstate-0003

One question, and it is not the mechanism:

> **Does a majority-authoritative service policy survive real semantic
> disagreements without losing an observable source?**

Success looks like: the run reaches its scientific target or its safety cap rather
than a disagreement; every disagreement is classified and the first 256 are
preserved with their bytes; for each `disc_extra` event the follow-up records
whether the omitted source was present in the next cause and how long after the
re-arm; RESTORE ok. A run with **zero** disagreements is an inconclusive result for
this question, not a success — the policy would be untested — and must be reported
as such.

#### R3.21 Release gate for GBP-VIDEO-003

Objective and checkable, with no dependence on any runtime causal label, and
deliberately **not** requiring U-GBP-033 to be answered:

```text
1. one physical vstate-0003 run that observes >= 1 SOURCE_SERVICED disagreement
   and does not stop for it;
2. no observable source loss: for every disc_extra event the follow-up is
   FU_SOURCE_PRESENT_NEXT, or the FU_SOURCE_ABSENT_NEXT / FU_NO_NEXT_CAUSE cases
   are individually accounted for in the analysis;
3. zero NON_SOURCE and zero SOURCE_OTHER disagreements, or a documented decision
   about any that occurred;
4. if any majority-extra VIDEO service occurred: the quarantine behaved as
   specified (frame not counted, not a baseline, not structural) and the case is
   analysed explicitly BEFORE the colour experiment is authorised;
5. RESTORE ok and the same final device state as every previous run;
6. diagnostics preserved and the sidecar parsing strictly;
7. an observation window long enough to be relevant — the scientific target, or a
   stop the design already recognises as legitimate.
```

Colour needs a long uninterrupted observation of this service loop; it does not
need to know why the replicas differ.

#### R3.22 Test plan (host, synthetic, before any hardware)

```text
no disagreement                 the whole operation stream identical to vstate-0002's
Disc extra 0x0400               service VIDEO, ACK 0x8100, nonfatal, record + follow-up
Disc extra 0x0100               service AUDIO, ACK 0x8400, nonfatal; NO VIDEO block is
                                fabricated; the assembler reports the short interval
                                through its existing incomplete/resync rules and the
                                frame carries F_SOURCE_DEFERRED
majority extra 0x0400           service AUDIO+VIDEO, ACK 0x8500, nonfatal; the AUDIO
                                block is flagged B_MAJORITY_EXTRA and its CRC/first
                                word are kept
majority extra 0x0100           service occurs; the VIDEO block is flagged; the frame
                                gets F_MAJORITY_EXTRA + F_ANOMALY, never F_COUNTED,
                                never F_BASELINE, cannot validate structured change
both directions in one read     disc_extra and majority_extra both non-zero
multiple source bits            delta = 0x0500 handled as ONE event, not two
agreed unexpected source        Disc = 0x0104, GBI = 0x0104, delta = 0x0000
                                -> FATAL anomaly_unexpected_source (the guard is
                                independent of the delta)
disagreement only 0x0004        SOURCE_OTHER -> FATAL, reason names the class
delta outside SRC_MASK          NON_SOURCE -> FATAL (odd bit, bit 15, high bit, each)
mask-bit / bit15 / 0x1000       FATAL, one case each
three consecutive disagreements record N is FILLED from cycle N+1's read BEFORE
                                record N+1 is created; N+1 from N+2; no record ever
                                receives another's follow-up
store full + pending follow-up  with the store capped, the record still in WAIT_NEXT
                                is finalised; only NEW records are suppressed
N+1 disagreements               first N preserved byte-for-byte, counters keep
                                counting, diagnostic_store_full set, run continues
observational POSTACK disagree  recorded and counted; read_kind says so; follow-up is
                                FU_UNKNOWN/observational_site; no service narrative
no runtime gap-ratio label      no state is derived from a divisor of any observed
                                gap; the gap statistics are persisted as data and the
                                ratio is computed offline
no retry / no extra read        proven from the operation stream, as in vstate-0002
service selection by majority   the ONLY difference in the stream vs. the Disc policy
OGBPSEQ1 v3 frozen              the physical v3 file still parses, byte for byte
old physical fixtures           v1, v2, v3 and every replay unchanged
```

v4 strictness, as its own block of cases (R3.24, R3.27, R3.19):

```text
version dispatch        1, 2, 3 read by their own rules; 4 by v4's; 0, 5, 0xFFFF rejected
diag_count              0 accepted (no disagreement), 1 accepted, 256 accepted,
                        257 rejected
diag_rec_size           160 accepted; 96, 159, 161 and 0 rejected in a v4 file
semantic_size           1024 accepted; anything else rejected, including 0
semantic block tag      0x4F475342 required; block_version 1 required
record fields           classification in {1,2,3}; followup_state in {0..4} and never 0
                        in a saved file; followup_reason in {0..4};
                        payload_source in {0, 0x0100, 0x0400}
reserved areas          header 0x1F4..0x1FB, record 0x5C and 0x9E, semantic block
                        0x05C..0x06F and the per-slot reserved words: each rejected
                        when non-zero, one case per area
unknown flag bits       diag_flags bit 1..15 set -> rejected;
                        record_flags bit 8..15 set -> rejected;
                        semantic flags bit 1..15 set -> rejected
sentinel coherence      gap_count == 0 with gap_min != 0xFFFFFFFF -> rejected
                        followup_filled set with followup_state in {0,3,4} -> rejected
                        payload_valid set with payload_source == 0 -> rejected
offsets tampered        off_diag, off_semantic, diag_count, diag_rec_size and
                        semantic_size each moved with BOTH CRCs recomputed -> each
                        rejected by a structural rule, not by the CRC
section bounds          exact contiguity, zero overlap, footer ending exactly at the
                        file size, every section inside the total CRC
```

#### R3.23 Open items this design does not close

* **U-GBP-033** — the mechanism behind the replica non-uniformity. Untouched.
* **W1C 1-on-0** — the effect of an ACK writing 1 to a source bit whose last
  replica reads 0. GBP-HW-028 covers only 1-on-1. R3 will produce the first
  physical description of this case if it occurs, and assumes nothing about it.
* **Identity of a re-observed source** — that a source omitted by the majority
  appears in the next cause proves it was observed after the re-arm, and nothing
  more. Whether it is the same assertion is an offline question, to be classified
  CORROBORATED or HYPOTHESIS on the aggregate, never asserted by the runtime.
* **Majority-extra in general** — never observed. Its handling here is designed to
  describe the first occurrence safely, not to declare it benign.

This design does not explain the non-uniformity, does not assert that the majority
reading is what the hardware "means", and does not touch the runtime:
implementation, audit and a physical candidate are separate steps.

#### R3.24 Normative layout of the v4 diagnostic record — 160 bytes

Big-endian on the wire, written **field by field**; no native struct is ever
serialized, and no compiler padding reaches the file. Offsets `0x00..0x5F` are the
v3 record **verbatim** — same offsets, same types, same meanings — so the first 96
bytes of a v4 record and of a v3 record describe the same things. That is
structural continuity, not compatibility: see R3.25.

```text
off   size type  field                    meaning / validity
----- ---- ----- ------------------------ -------------------------------------------------
0x00    8  u64   t                        v3: time base at the read
0x08    4  u32   cycle                    v3: delivery ordinal
0x0C    4  u32   valid                    v3: 1 when the record is occupied
0x10    2  u16   disc_value               v3: the Start-up Disc reading
0x12    2  u16   gbi_value                v3: GBI's bitwise majority
0x14    2  u16   read_kind                v3: 0 LEAN, 1 PRESVC, 2 POSTDRAIN, 3 POSTACK, 4 OTHER
0x16    2  u16   attempts                 v3: disagreements seen, saturating at 0xFFFF
0x18   32  u8[]  raw                      v3: the 32 bytes verbatim
0x38    4  u32   intsr_entry              v3
0x3C    4  u32   intsr_after_w1c          v3
0x40    4  u32   intmr_entry              v3
0x44    4  u32   latency_ticks            v3
0x48    4  u32   xfer_ticks               v3
0x4C    2  u16   xfer_polls               v3
0x4E    2  u16   dma_status               v3
0x50    2  u16   dma_status_before        v3
0x52    2  u16   control_exp              v3
0x54    4  u32   frame_index              v3
0x58    4  u32   block_in_frame           v3
0x5C    4  u32   reserved0                v3: MUST be zero
----- ---- ----- ------------------------ -------------------------------------------------
0x60    2  u16   delta                    disc_value ^ gbi_value; always valid
0x62    2  u16   disc_extra_sources       disc & ~gbi & SRC_MASK; always valid
0x64    2  u16   majority_extra_sources   gbi & ~disc & SRC_MASK; always valid
0x66    2  u16   classification           1 SOURCE_SERVICED, 2 SOURCE_OTHER, 3 NON_SOURCE
                                          (0 is not a valid value)
0x68    2  u16   authoritative_value      the composed u16 of R3.3; always valid
0x6A    2  u16   ack_value                authoritative | 0x8000, or 0 when no ACK was
                                          written (fatal classes); validity = flag bit 6
0x6C    2  u16   service_selected         the source bits actually drained this cycle;
                                          0 is meaningful (nothing drained)
0x6E    2  u16   record_flags             see below
0x70    8  u64   t_ack                    valid iff flag bit 6 (ack_written)
0x78    8  u64   t_rearm                  valid iff flag bit 7 (rearm_written)
0x80    8  u64   t_next_cause             valid iff followup_state == FU_SOURCE_PRESENT_NEXT
                                          or FU_SOURCE_ABSENT_NEXT
0x88    2  u16   next_pending_gbi         valid under the same condition as t_next_cause
0x8A    2  u16   next_pending_disc        valid under the same condition
0x8C    1  u8    followup_state           0 FU_PENDING, 1 FU_SOURCE_PRESENT_NEXT,
                                          2 FU_SOURCE_ABSENT_NEXT, 3 FU_NO_NEXT_CAUSE,
                                          4 FU_UNKNOWN
0x8D    1  u8    followup_reason          0 none, 1 observational_site, 2 run_aborted,
                                          3 not_applicable (no source was omitted),
                                          4 internal_condition
0x8E    2  u16   payload_source           the single source bit the payload diagnostic
                                          describes (0x0100 or 0x0400); 0 = none
0x90    4  u32   payload_crc32            valid iff flag bit 1
0x94    4  u32   payload_first_word       valid iff flag bit 1
0x98    4  u32   gap_min_before_ticks     the smallest gap between causes of the OMITTED
                                          source observed in this run BEFORE this event;
                                          sentinel 0xFFFFFFFF when gap_count_before == 0
0x9C    2  u16   gap_count_before         how many gaps that statistic is built on;
                                          0 means "no statistic", never "a gap of zero"
0x9E    2  u16   reserved1                MUST be zero
----- ---- ----- ------------------------ -------------------------------------------------
                                          total 0xA0 = 160
```

`record_flags` bits, all others reserved and MUST be zero:

```text
bit 0  followup_filled          the 0x80..0x8B fields were written from a real next cycle
bit 1  payload_valid            payload_source / crc32 / first_word are measurements
bit 2  payload_second_omitted   both AV sources were majority-extra; only one is described
bit 3  frame_quarantined        a VIDEO block of this event was quarantined (R3.12)
bit 4  source_deferred_marked   a frame carried F_SOURCE_DEFERRED for this event (R3.13)
bit 5  service_incomplete       a selected drain did not complete
bit 6  ack_written              ack_value and t_ack are measurements
bit 7  rearm_written            t_rearm is a measurement
```

**Deliberately not stored, because they are exact functions of stored fields** —
storing them would create a second source of truth that can go inconsistent:
`next_delta = next_pending_gbi ^ next_pending_disc`, and
`rearm_to_next_ticks = t_next_cause - t_rearm` (valid when both are).

**Sentinel discipline.** No field uses `0` both as a measurement and as "absent".
Every field whose validity is conditional is governed by an explicit flag or by
`followup_state`, never by its own value; `gap_min_before_ticks` uses an explicit
out-of-range sentinel; `service_selected == 0` is a real measurement (nothing was
drained) and is always valid.

**Assertions the implementation is expected to carry** (compile-time where the
language allows, test-time otherwise):

```text
sizeof(record)            == 160
offsetof(delta)           == 0x60      offsetof(reserved1) == 0x9E
the first 96 bytes        byte-identical in layout to the v3 record
reserved0, reserved1      zero on write and rejected non-zero on parse
classification            in {1,2,3}   followup_state in {0..4}
followup_reason           in {0..4}    record_flags & ~0x00FF == 0
payload_source            in {0, 0x0100, 0x0400}
gap_count_before == 0     implies gap_min_before_ticks == 0xFFFFFFFF
```

#### R3.25 What "the first 96 bytes are v3" does and does not mean

It means the format evolved consciously: a reader that knows the v3 record knows
16 of the 20 fields of a v4 record, at the same offsets, with the same meanings.

It does **not** mean a v3 parser may read a v4 file, and the design forbids trying:
version dispatch happens before any field is read, `diag_rec_size` differs (96
against 160), and `diag_count` has different bounds. There is **no retroactive
semantics**:

```text
v3   diag_count <= 1      diag_rec_size == 96    single fatal diagnostic
v4   diag_count <= 256    diag_rec_size == 160   nonfatal, multiple, with follow-up
```

#### R3.26 Follow-up lifecycle, in the format

The state machine of R3.8 is represented by `followup_state` plus `record_flags`
bit 0, with no free text anywhere in the sidecar:

```text
runtime state    on the wire                              when it is written
---------------- ---------------------------------------- ----------------------------
OPEN             followup_state = FU_PENDING (0)          at the disagreement
                 bit 0 clear, 0x80..0x8B zero
WAIT_NEXT        unchanged on the wire; bit 7 set once     after the re-arm
                 t_rearm is measured
FILLED           followup_state = 1 or 2, bit 0 set,       from the NEXT cycle's read
                 0x80..0x8B are measurements
CLOSED_NO_NEXT   followup_state = FU_NO_NEXT_CAUSE (3)     at teardown, if still WAIT_NEXT
                 bit 0 clear, 0x80..0x8B zero
not applicable   followup_state = FU_UNKNOWN (4) with      at the disagreement, for an
                 followup_reason = 1 (observational_site)  observational read site,
                 or 3 (not_applicable) when the majority   or when disc_extra == 0
                 omitted nothing
```

A record that reaches the file with `followup_state == FU_PENDING` is a defect and
the strict parser rejects it: the teardown must resolve every record to 1, 2, 3
or 4.

#### R3.27 Normative layout of the semantic block — 1024 bytes

Fixed size, always present in a v4 file, always exactly 1024 bytes, entirely
inside the total CRC. Big-endian, field by field.

```text
off     size  field
------- ----- --------------------------------------------------------------
0x000     4   tag = 0x4F475342 ("OGSB")
0x004     2   block_version = 1
0x006     2   flags: bit 0 store_capped (sticky); all other bits MUST be zero
0x008     4   semantic_disagreements_total
0x00C     4   source_serviced_disagreements
0x010     4   source_other_disagreements
0x014     4   non_source_disagreements
0x018     4   disc_extra_source_events
0x01C     4   majority_extra_source_events
0x020     4   both_direction_events
0x024     4   majority_extra_video_services
0x028     4   majority_extra_audio_services
0x02C     4   frames_quarantined
0x030     4   frames_source_deferred
0x034     4   diagnostics_preserved
0x038     4   diagnostics_not_preserved
0x03C     4   followup_present
0x040     4   followup_absent
0x044     4   followup_no_next
0x048     4   followup_unknown
0x04C     4   observational_disagreements
0x050     4   service_selecting_disagreements
0x054     4   payload_diagnostics_captured
0x058     4   service_incomplete_events
0x05C    20   reserved, MUST be zero
0x070   144   gap statistics: 6 slots of 24 bytes, one per SRC_MASK bit, in
              ascending bit order (0x0001, 0x0004, 0x0010, 0x0040, 0x0100, 0x0400):
                  +0x00  2  u16 source_bit        the bit this slot describes
                  +0x02  2  u16 reserved          MUST be zero
                  +0x04  4  u32 gap_count         number of gaps measured
                  +0x08  4  u32 gap_min_ticks     0xFFFFFFFF when gap_count == 0
                  +0x0C  4  u32 gap_max_ticks     0 when gap_count == 0
                  +0x10  4  u32 gap_last_ticks    0 when gap_count == 0
                  +0x14  4  u32 reserved          MUST be zero
0x100   256   delta_hist[64], u32 each
0x200   256   disc_extra_hist[64], u32 each
0x300   256   majority_extra_hist[64], u32 each
------- ----- --------------------------------------------------------------
              total 0x400 = 1024
```

**Histogram index.** The six source bits of `SRC_MASK` are compressed to six index
bits, source bit `2k` to index bit `k`:

```text
idx(v) = Σ over k in 0..5 of  ((v >> (2*k)) & 1) << k

0x0001 -> 1     0x0004 -> 2     0x0010 -> 4
0x0040 -> 8     0x0100 -> 16    0x0400 -> 32
0x0500 -> 48    0x0000 -> 0
```

Index 0 therefore means "no source bits", which for `delta_hist` cannot occur (a
record only exists when `delta != 0` within the mask) and for the two directional
histograms means "no extra on that side" — a legitimate and frequent value.

`semantic_size` is exactly 1024 in v4; the parser rejects any other value rather
than trusting the header.

#### R3.28 Gap statistics — semantics

```text
what is measured   cause -> cause, per source bit: the interval between the
                   `t_cause` of two consecutive cycles whose authoritative pending
                   contained that bit. It is NOT ACK->ACK and NOT re-arm->cause
type               u32 ticks; the interval is a difference of two u64 clocks, and a
                   gap that does not fit in u32 (106 s at 40.5 MHz) saturates at
                   0xFFFFFFFE and sets no flag of its own — such a gap cannot occur
                   inside this experiment's caps, and saturation is preferable to a
                   silent wrap
when it starts     empty; the FIRST cause of a source produces no gap. gap_count is
                   the number of gaps, so a source seen once has gap_count == 0
sentinel           gap_count == 0 -> gap_min = 0xFFFFFFFF, gap_max = gap_last = 0.
                   A gap of 0 ticks is impossible between distinct causes, so 0 is
                   never a valid minimum
disagreement cycles are INCLUDED: the cause of a cycle that disagreed is a cause
                   like any other. Excluding them would bias the statistic toward
                   the quiet part of the run
per record         `gap_min_before_ticks` / `gap_count_before` are a snapshot of the
                   OMITTED source's statistic as it stood BEFORE the event, so the
                   offline ratio compares against what was known at that moment
status             these are measurements of one run. **No statistic here is a
                   physical lower bound on how soon a source may be asserted**, and
                   no runtime decision reads them
```

#### R3.29 Where `F_SOURCE_DEFERRED` lives, and what it may not imply

The deferred VIDEO block was never drained, so the marker cannot live on a block.
It lives on the frame **being assembled at the moment of the disagreement**:

```text
if a frame is open        that frame gets GBP_VSTATE_F_SOURCE_DEFERRED, and the
                          record sets record_flags bit 4
if no frame is open       no frame is created. The event exists only in the
                          diagnostic record (disc_extra_sources names the source)
                          and in the event store; record_flags bit 4 stays clear
```

No fictitious frame is ever created to carry a flag. The marker does not change
completeness, does not fabricate a block, does not claim the deferred source was
later recovered, and is not an input to any stop or classification rule. It exists
so the offline analysis can line up a short interval with the disagreement that
preceded it.

---

### GBP-VIDEO-002-R4 (build `vstate-0004`, OGBPSEQ1 v5) — give every diagnostic field an owner — DESIGNED, IMPLEMENTED and **PHYSICALLY EXECUTED 2026-09-17; PHYSICAL VALIDATION PASSED**

`vstate-0003` proved the service policy on hardware and produced records whose
current-cycle fields belong to the wrong cycle (GBP-HW-104). This revision fixes
the attribution and nothing else. It is **RAM bookkeeping and format only**: not
one hardware operation, ordering, count or timing changes, and the ISR is not
touched.

**PHYSICALLY EXECUTED 2026-09-17** (commit `b017e38`, DOL SHA-256
`b0ed33f0…97c5`, log `e8d9e2dd…c1a4` 86 390 B, sidecar `9d744a28…aaa1`
4 360 684 B, OGBPSEQ1 v5). Result:

```text
GBP-VIDEO-002-R4 vstate-0004 PHYSICALLY EXECUTED
SCIENTIFIC TARGET REACHED — 120.009 s of valid observation in 175.848 s of capture
SERVICE ok, RESTORE ok, structured change OBSERVED (9 episodes, 7 stable)
29 SEMANTIC DISAGREEMENTS, ALL SOURCE_SERVICED, ALL SURVIVED (GBP-HW-110)
  auth 0100 / service 0100 / ACK 8100 / flags 01c1 in 29 of 29 (GBP-HW-111)
  t <= t_ack <= t_rearm <= t_next_cause in 29 of 29, ZERO invariant failures
  the omitted AUDIO source present in the next ordinary read 29/29 (GBP-HW-113)
THE vstate-0003 PRODUCER DEFECT DOES NOT OCCUR ONCE
```

**What this validated, and what it did not.** The exercised path is
`SOURCE_SERVICED` with a **Disc-extra** source, 29 times. The v5 producer's other
branches did **not** occur in this run and are therefore not physically
validated: majority-extra disagreements (0), observational POSTDRAIN/POSTACK
disagreements (0), `SOURCE_OTHER` (0), `NON_SOURCE` (0), the payload diagnostic
(0), the quarantine and deferred markers (0) and every failure path. Those remain
host- and mock-tested only; §R4.10a lists the batteries that cover them.

Evidence: GBP-HW-108…115. The fixture is
`captures/fixtures/hw-gamecube-gbp-2026-09-17-vstate-0004.gbpreplay`.

**Implementation status, 2026-09-17.** The design below is implemented in
`src/gbp/gbp_vstate.{h,c}`, `src/gbp/gbp_vstate_probe.c`,
`src/gbp/gbp_vstatedump.{h,c}`, `poc/gbp-video-state-probe/` (Build ID
`vstate-0004`) and `tools/vstate.py`, with the host battery in
`tests/unit/test_gbp_video_state.c` and `tests/host/test_vstate.py`. Its
synthetic scenarios remain synthetic and are not evidence about the device; only
the physical run above is. What the implementation measured about ITSELF:

```text
                          vstate-0003 (HEAD 1ed1629)   vstate-0004 (dirty)   delta
.text                                       337 824               338 496     +672
.data                                        11 428                11 428        0
.sbss                                         1 804                 1 804        0
.bss                                      7 515 332             7 515 332        0
DOL BSS                                   7 517 136             7 517 136        0
stack: gbp_vstate_probe_run                     568                   584      +16
stack: gbp_vstate_diag_open                      96                    88       -8
stack: every current-cycle setter           leaf, no frame    leaf, no frame      0
code:  gbp_vstate_probe_run                  12 328                12 516     +188
```

Not one byte of resident storage was added: the fix is an argument, not a buffer.
The `.text` growth is the handle plumbing plus the v5 cross-field invariants,
which live in the same translation unit as the writer. No allocation anywhere
scales with the number of diagnostics.

#### R4.1 The defect, stated exactly

```c
/* vstate-0003, all six current-cycle setters */
d = &s->diags[s->diags_n - 1u];     /* "the newest record" */
```

called unconditionally from the service loop on every cycle. The lifecycle that
produces is:

```text
cycle N  disagreement  -> record N opened; its auth/service/ACK/re-arm are correct
cycles N+1 .. M-1      -> every one of them OVERWRITES record N's current-cycle fields
cycle M  disagreement  -> record M opened; N stops being overwritten, M starts
```

so what survives in record N is the state of cycle M−1. The measured signature
matches exactly: `t_ack(i)` sits 118–170 µs before the read of disagreement *i+1*,
and 96 µs before the stop for the last record.

#### R4.2a Every record write goes through the handle

One consequence is worth stating separately, because it is what makes the rule
checkable rather than merely intended: **no translation unit other than
`src/gbp/gbp_vstate.c` writes a diagnostic record.** The probe's transport and
ISR context for the read that opened a record arrives through
`gbp_vstate_diag_context()`, a handle-taking setter like every other; the
serializer and the ring log hold `const` pointers and only read. The store is
indexed from exactly one place, `diag_at()`, which is bounds-checked and total.

#### R4.2 The API: an explicit handle, never "the latest record"

`diag_open()` returns a handle — an index, or `GBP_VSTATE_DIAG_INVALID` — and
**every current-cycle setter takes that handle explicitly**:

```text
handle = gbp_vstate_diag_open(...)                  /* or INVALID */
gbp_vstate_diag_service   (s, handle, authoritative, selected, incomplete)
gbp_vstate_diag_payload   (s, handle, source, crc32, first_word)
gbp_vstate_diag_quarantined(s, handle)
gbp_vstate_diag_deferred  (s, handle)
gbp_vstate_diag_ack       (s, handle, ack_value, t_ack)
gbp_vstate_diag_rearm     (s, handle, t_rearm)
```

An `INVALID` handle is a documented, bounded no-op — the ordinary case, since most
cycles open no record. This is deliberately preferred over a
`current_diag_index` member: a global would be one more piece of state that can be
stale, and the whole defect being fixed is stale state. No API may derive the
target from `diags_n`.

#### R4.3 Two handles, two lifetimes

```text
service_diag_handle    belongs to the CURRENT transaction; receives the
                       current-cycle fields; conceptually dies at WAIT_NEXT and is
                       never inferred from "the latest record"
followup_wait_index    survives until the NEXT ordinary read; receives ONLY
                       t_next_cause, next_pending_*, followup_state/reason; is
                       cleared when filled
```

Neither substitutes for the other. A normal cycle that opens no record must not be
able to touch any field of a record that is merely waiting for its follow-up.

#### R4.4 Two diagnostics in one transaction

A service-selecting disagreement at READ/PRESVC can be followed, in the **same**
transaction, by an observational one at POSTDRAIN or POSTACK. The observational
record must not capture `service_diag_handle`:

```text
service_diag_handle    keeps pointing at the record that took the service decision
observational record   gets its own handle for its own read context, and receives
                       NO service, ACK, re-arm, payload or quarantine field
```

This is a second, independent reason the setters must take an explicit handle.
Required test cases: READ + POSTDRAIN, READ + POSTACK, PRESVC + POSTACK.

#### R4.5 Observational records in v5 — closed semantics

For a POSTDRAIN/POSTACK disagreement the record preserves its read — raw bytes,
both readings, delta, the two extra masks, classification, and the authoritative
interpretation of that read where it is defined — and asserts nothing about
service:

```text
service_selected   0          ACK_WRITTEN     0        REARM_WRITTEN 0
payload_valid      0          quarantine/deferred flags 0
followup_state     FU_UNKNOWN, reason observational_site
```

This closes a question the R3 design left open only implicitly, and it makes the
v5 invariants below simple enough to be checkable.

#### R4.6 The v5 producer lifecycle

```text
service_handle = INVALID

READ (one read, unchanged)
    fill the pending follow-up from THIS read FIRST
    classify, compose, guards                       (unchanged)
    if this read disagrees:
        h = diag_open(...)
        if the site selects service:  service_handle = h
        else:                         close h as FU_UNKNOWN/observational_site

    if service_handle valid: diag_service(service_handle, ...)
AUDIO drain, VIDEO drain                            (unchanged order)
    if service_handle valid: diag_payload / quarantined / deferred(service_handle, ...)
ACK                                                 (unchanged)
    if service_handle valid: diag_ack(service_handle, ...)
semantic / frame processing                         (unchanged)
REARM                                               (unchanged)
    if service_handle valid: diag_rearm(service_handle, ...)
    if service_handle valid and it has disc_extra and the re-arm was written:
        followup_wait_index = service_handle
    service_handle = INVALID
WAIT_NEXT
```

Store full: `service_handle` is `INVALID`, the counters still move, and no new
waiter is created. A record already waiting is still filled after the cap.

#### R4.7 OGBPSEQ1 v5

Same 160-byte record and same 1 024-byte semantic block — no new field is needed,
because the defect was never a missing field. The version exists to separate two
producers:

```text
v4   HISTORICAL, PHYSICALLY EXECUTED, KNOWN PRODUCER DEFECT
     current-cycle authoritative/service/ACK/REARM may belong to a later cycle
v5   correct attribution, enforced by strict cross-field invariants
```

v1, v2, v3 and v4 are **not** changed retroactively, and the v4 parser does **not**
acquire the new invariants: making them fatal would turn a real physical capture
into a parse failure. `tools/vstate.py` reports them as warnings for v4 instead
(`producer_warnings()`), which is how this file's defect is surfaced offline
without refusing the evidence.

#### R4.8 The v5 cross-field invariants

Recomputed, not trusted:

```text
from raw32          disc_value and gbi_value must EQUAL the recomputation
then                delta, disc_extra_sources, majority_extra_sources and
                    classification must equal their recomputation from those two
```

Authority, at a service-selecting site:

```text
(authoritative_value & SRC_MASK) == (gbi_value & SRC_MASK)
service_selected == authoritative_value & AV_MASK
non-source bits composed per §R3.3
```

Acknowledge:

```text
ACK_WRITTEN     -> ack_value == authoritative_value | 0x8000
not ACK_WRITTEN -> ack_value and t_ack carry the documented invalid encoding;
                   a plausible timestamp without its flag is refused
```

Timing — and this rule is **read-kind dependent**, which is the subtlety the v4
file exposes:

```text
service-selecting READ/PRESVC, fields valid:   t <= t_ack <= t_rearm
  and when a next cause exists:                t_rearm <= t_next_cause
observational POSTDRAIN/POSTACK:               NO such chain is required, because
  that read can legitimately happen after the ACK. §R4.5 makes ACK/REARM invalid
  in those records, so the chain does not apply at all.
```

There is deliberately **no** universal `t <= t_ack` rule for every read kind.

Follow-up:

```text
service-selecting with disc_extra != 0 and followup PRESENT/ABSENT
   -> REARM_WRITTEN set, t_next_cause valid, next_pending_* valid
   present = disc_extra_sources &  (next_pending_gbi & SRC_MASK)
   absent  = disc_extra_sources & ~(next_pending_gbi & SRC_MASK)
   PRESENT -> absent == 0        ABSENT -> absent != 0
FU_PENDING in a saved file       -> refused, as in v4
observational                    -> FU_UNKNOWN / observational_site
```

Majority-extra:

```text
payload_valid          -> payload_source is a source that was majority-extra,
                          selected, and whose drain completed
frame_quarantined      -> majority_extra_sources contains VIDEO
source_deferred_marked -> disc_extra_sources contains VIDEO
```

Whether a frame was open when the deferral happened is producer state that is not
serialized, and the parser does not pretend to check it.

#### R4.9 What the fix may not change

The device operation stream of a run without disagreements must stay
**byte-identical** to `vstate-0003`'s, and the stream of a run with them must stay
equivalent to the policy already validated: same READ count, same AUDIO and VIDEO
ordering, same ACK, same PI clean, same semantic/frame processing, same re-arm,
same WAIT_NEXT, same ISR, same INTMR handling. No retry, no second read.

#### R4.10a What the implementation added to the batteries

Executed, all synthetic:

```text
C  test_current_cycle_fields_survive_later_cycles   the defect's own shape: isolated
                                                    disagreements with many ordinary cycles
                                                    between them; every record keeps the ACK
                                                    and re-arm of ITS OWN cycle, and the
                                                    physical inversion (t_ack after the next
                                                    cause) must be absent. A second phase runs
                                                    one event and then thousands of cycles.
C  test_same_cycle_multiple_diagnostics             PRESVC + POSTDRAIN + POSTACK in one
                                                    transaction, three times over: one owner,
                                                    two witnesses, and no extra operation
C  test_markers_land_on_the_service_record_only     quarantine, deferral and payload go to the
                                                    record that selected the service; the
                                                    witnesses receive none of them
C  test_every_direction_costs_no_operation          the four directions against a reference run
                                                    that agrees on the serviced value: identical
                                                    reads, operations, bulk reads, IRQ writes
C  test_ack_and_rearm_failures_leave_no_false_claim a write that did not complete never becomes
                                                    a flag that says it did, and no waiter is
                                                    armed after a re-arm that never happened
C  test_v5_rejects_the_v4_defect                    nine tampers into the physical defect's
                                                    shapes, both CRCs recomputed each time
C  test_v5_record_round_trip                        a three-record file: observational with 32
                                                    distinct bytes, majority-extra with a
                                                    payload, Disc-extra with a filled follow-up
C  the INVALID-handle sweep                         every setter called with GBP_VSTATE_DIAG_
                                                    INVALID leaves the store byte-identical
C  test_ownership_survives_a_store_that_runs_out    A + B + C in one transaction with 0, 1, 2 and
                                                    3 free slots: whatever fitted, the markers of
                                                    the transaction reach A and every other
                                                    record is byte-identical
C  test_diag_close_touches_only_the_followup        the teardown sweep may move follow-up bytes
                                                    and nothing else; an already-closed record
                                                    does not move at all
C  test_majority_extra_only_never_waits             a record that omitted nothing is closed at
                                                    open as unknown/not_applicable and can never
                                                    be armed
C  the 256-record file                              a full store serializes and strict-parses;
                                                    257 declared is refused
py V5RejectsTheV4Defect                             the same tampers through the Python parser,
                                                    each one also put through the C parser
                                                    (`--parse`) so the two cannot disagree
py FrozenFormatsStayReadable                        v2, v3 and v4 still parse in BOTH
                                                    implementations, and the v4 defect stays a
                                                    non-fatal report derived from the content;
                                                    a v4 file that sets the v5 service flag is
                                                    refused by both, and the physical v4 file
                                                    proves dispatch is by CONTENT - it breaks
                                                    v5's rules in 22 records and is still
                                                    accepted through the v5 entry point
py ParserParity                                     one corpus - three physical files, three
                                                    synthetic files, seven tampers and a format-1
                                                    file - one verdict from each parser
```

#### R4.10 Test plan additions

Beyond the whole R3 battery, which must keep passing:

```text
the defect itself      a record is opened, several ordinary cycles run, and the
                       record's auth/service/ACK/re-arm are asserted UNCHANGED
same-transaction pairs READ+POSTDRAIN, READ+POSTACK, PRESVC+POSTACK: the
                       observational record gets no service fields and the
                       service record keeps its own
v5 parser              every cross-field invariant of §R4.8, each with both CRCs
                       recomputed so only the rule can refuse
a v4-shaped forgery    a v5 file carrying the v4 defect (t_ack > t_next, authority
                       not the majority) must be REFUSED by the v5 parser
the physical v4 file   must keep parsing under the v4 rules, unchanged, and must
                       keep producing its producer warnings
```

---

### GBP-VIDEO-003 (build `color-0001`, sidecar `OGBPCOL1` v1) — controlled colour mapping — DESIGN FINALIZED, IMPLEMENTED 2026-09-17, STRUCTURAL TIMING FIX APPLIED, **PHYSICALLY EXECUTED 2026-09-18 — the run CERTIFIED but the analyser REFUSED it at its own gate; see "GBP-VIDEO-003 / color-0001 — first physical run" at the end of this file**

**Implementation status, 2026-09-17.** The three components of §V3 exist and are
built by the project's own toolchain; **none of it has run on hardware**, no
observation in this repository comes from it, and no evidence ID belongs to it:

```text
stimulus   stimulus/agb-color-bars/           AGB Mode 3, devkitARM 15.2.0 in the
                                              project container, 1 076 B, header
                                              audited by tools/gbahdr.py
probe      poc/gbp-video-color-probe/         Test ID GBP-VIDEO-003, Build ID color-0001
capture    src/gbp/gbp_vcolor.{h,c}           eligibility, stability, hold, raw budget
format     src/gbp/gbp_vcoldump.{h,c}         OGBPCOL1 v1, writer and strict parser
analyser   tools/vcolor.py                    the offline decision, exact and unscored
tests      tests/unit/test_gbp_vcolor.c       capture + format, 281 checks
           tests/host/test_vcolor.py          analyser + parser + synthetic corpus
```

The probe reuses the service path of GBP-VIDEO-002 **as the same code**, not as a
copy: `gbp_vstate_probe_run()` gained a capture hook that is `NULL` in every
GBP-VIDEO-002 build, so the device operations, their order and the R3 policy are
literally the ones `vstate-0004` executed. A synthetic scenario runs the same
mock twice, with and without the capture attached, and requires identical IRQ
reads, whole-block drains, IRQ writes, operations and transfers.

**MICROAUDIT BLOCKER, 2026-09-17 — RAISED AND FIXED THE SAME DAY.** The first
implementation did full-frame work in the service-critical window and the
microaudit refused it. What it found, kept here because the refusal is the
useful part:

`gbp_vcolor_frame()` was called between the ACK and the RE-ARM and did up to
`memcmp` 153 600 + `memcpy` 153 600 bytes there, at every eligible frame close,
plus a 153 600-byte `memcmp` for each of 60 hold frames. Two ratios settled it,
and neither needs a memory-throughput assumption:

* **Bytes in that window rose ~81×** ((3 840 + 307 200) / 3 840). The only work
  ever measured there is the per-block signature — 3 840 bytes, median **823
  ticks** over 420 073 physical samples in `vstate-0004`.
* **Frequency of full-frame copies rose ~700×.** The architecture already had one
  there, `preserve_frame()`, and it was physically survived — but it ran **15
  times in 175.848 s**, not 59.73 times a second.

For scale, on the same run: RE-ARM → next cause was **77..94 ticks
(1.90..2.32 µs)** in 29/29 `SOURCE_SERVICED` events, a VIDEO block arrived every
**418.6 µs**, and a frame closed every **16.74 ms**. Operation-stream equivalence
with `vstate-0004` was proven and is *not* evidence about CPU time.

#### V3.23 The fix: the capture cannot touch a frame

`gbp_vcolor_frame()` now takes a frame record and a **slot index**. There is no
pointer parameter, so there is no capability through which 153 600 bytes could
reach it; a host test reads the declaration and pins that. Its whole cost is the
eligibility test, at most **40 word comparisons (160 bytes)** against the run's
reference signature vector, and a 40-byte record write.

The comparison uses `sig[40]`, the per-block checksum the state model already
computes in that same window, so the signature itself costs nothing new.

**A measurement boundary that must not be blurred.** The physical figure *median
823 ticks over 420 073 samples* belongs to `gbp_vsig_block()`, the existing
per-VIDEO-BLOCK signature. The new per-frame-close comparison of 40 words has
**not** been measured on hardware and is not described here as timing-neutral,
timing-equivalent or sub-tick. What is stated is what is true by construction:
bounded at 40 word comparisons and at most 160 bytes copied, no additional device
operation, replacing paths that moved 153 600 and 307 200 bytes.

The work table, per path, between ACK and RE-ARM — exact counts, read from the
generated code, not estimates:

| path | word comparisons | bytes copied | bytes zeroed | colour calls |
| --- | --- | --- | --- | --- |
| VIDEO block that closes no frame | 0 | 0 | 0 | none (hook not entered) |
| frame close, not eligible | 0 | 0 | 40 | `eligible`, `record` |
| frame close, no ring slot | 0 | 0 | 40 | `eligible`, `record` |
| frame close, starts a run | ≤ 40 | 160 (`ref_sig`) + 32 (`cert[0]`) | 40 | `eligible`, `record` |
| frame close, signature differs | ≤ 40 | 160 + 32 | 40 | `eligible`, `record` |
| frame close, second matching | 40 | 32 (`cert[1]`) | 40 | `eligible`, `record` |
| frame close, certification | 40 | 32 (`cert[2]`) | 40 | `eligible`, `record` |

The comparison loop is `li r11,40 / mtctr` in the generated code — exactly 40
iterations, early-exit on the first difference. `record()`'s one `memset` is
`li r5,40`, bounded by `sizeof(struct gbp_vcolor_frame)`. `gbp_vcolor_frame` is
170 instructions, `gbp_vcolor_eligible` 27 (leaf), `record` 69.

`gbp_vcolor_frame` is 170 PowerPC instructions and calls only
`gbp_vcolor_eligible` (27) and `record` (69, whose one `memset` is 40 bytes
bounded by its own type). Nothing in that path calls `memcpy`, `memcmp` or
`memmove`. The pre-existing 3 840-byte boundary-block copy inside
`gbp_vstate_block()` is unchanged and is the only bulk operation left in the
window.

#### V3.24 Where the certified bytes live, and why the ring has four slots

**Nothing is copied during capture.** The three certified frames stay where the
DMA wrote them, in the state model's ring, and the OGBPCOL1 writer streams them
from there after the teardown. The 460 800-byte staging buffer is gone.

That works only because of a lifecycle fact, and the fact is now a test rather
than an argument. On the boundary block that closes frame C, the assembler
**first** copies that block into slot `cur+1` and **then** closes C. With three
slots, `cur+1` is the slot holding frame A — so A is destroyed at the exact
instant the third consecutive frame closes, which is the instant it becomes
evidence. Driving the real assembler proves it both ways:

```text
4 slots   A=0  B=1  C=2   filling=3   -> all three intact, gbp_vcolor_slots_ok() = 1
3 slots   A=0  B=1  C=2   filling=0   -> A is the slot being filled, slots_ok() = 0
```

So the ring needs **four** slots — and only for this experiment. The count is no
longer a compile-time constant: it is derived at init from the size of the buffer
the caller supplies, clamped to [3, 4]. The vstate probe passes the same
552 960-byte buffer it always did and behaves exactly as before; the colour probe
passes 737 280 bytes. Net memory: **+184 320** for the fourth slot, **−460 800**
for the staging buffer that is gone.

**The stop position.** Certification happens inside the frame-close hook. The
current transaction then finishes normatively — signature, RE-ARM, diagnostic
close, follow-up arm, WAIT_NEXT — and the next `CHECK_ADMISSION` ends the run
*before* another delivery is admitted. No VIDEO block is drained after
certification, so the ring is frozen where certification left it. `next_cause_at_end`
records that a cause was pending, which is the shape every previous run used.

**The hold window is removed**, and the reason is structural, not a trim: serving
60 more frames would rotate the ring over A, B and C long before the window
ended. It was `REPORT ONLY` and was never part of the success condition, so
nothing that was evidence is lost. Its header fields stay at their offsets, must
be zero, and both parsers refuse a file that uses them. `0x164` is repurposed as
`sig_mismatches`.

**When the slots do not survive**, `gbp_vcolor_slots_ok()` says so before
anything is written: the file then carries the frame table and the diagnostics,
**no raw**, and the header flag `raw_unrecoverable`. A certified run with no raw
is legal in that one shape and in no other.

#### V3.25 What the runtime claims, and what the analyser claims

These are different sentences and the implementation keeps them apart:

```text
runtime    three signature-identical eligible frames
offline    the three certified raw frames are byte-for-byte equal
```

A checksum can collide; the bytes cannot. `tools/vcolor.py` therefore compares
all three certified frames byte for byte — 153 600 each — **before** one pixel is
interpreted, and reports `inconclusive_certified_raw_mismatch` with the first
differing offset if they are not equal. A host test builds exactly that case:
three certified records whose raw differs in one byte, and no mapping is
attempted. That is what makes the cheap runtime check safe.

**One refusal label is shadowed, and it is written down rather than left to be
discovered.** `gbp_vstate_block()` sets `F_MAJORITY_EXTRA` and `F_ANOMALY` on the
same frame, and the eligibility predicate reports the FIRST fault it finds, so a
frame quarantined by the majority is refused under `ANOMALY` and
`frames_refused[MAJORITY_EXTRA]` stays **0** in any real run. The exclusion
itself is unaffected — the frame is refused, which is the whole point — and the
authoritative count of quarantined frames is the state model's
`frames_quarantined`, carried in the sidecar at `0x1AC`. The predicate order is
the design's and was not changed to chase a nicer label. `SOURCE_DEFERRED`, by
contrast, is set without `F_ANOMALY` and IS produced.

`F_PRE_BASELINE` is no longer an eligibility exclusion. It was inherited from the
vstate change detector, which answers a different question; whether *that*
experiment's baseline had settled says nothing about this frame's integrity, the
protocol's correctness or the raw lifecycle. Refusal code 7 is retired, stays
reserved so the layout does not move, and both parsers refuse a file that uses
it. `FRAME_CAP` also gained its own stop reason: "the table filled" and "the
clock ran out" are different observations.

**The physical delivery dependency is untouched by all of this** and remains
UNRESOLVED (§V3.7).

#### V3.26 PHYSICAL PROCEDURE DEPENDENCY — the run can certify the wrong picture

A consequence of stopping at certification, found by the second microaudit and
recorded rather than patched over.

**The probe cannot see what the AGB is executing.** It certifies the first three
consecutive eligible frames whose block signatures agree, and it holds no
stimulus value by design (§V3.11) — that is what keeps the experiment
non-circular. So *any* still picture qualifies: a BIOS screen, a flash-cart menu
sitting idle, a blank or white framebuffer, a paused loader. At the 59.73 Hz the
physical runs measured, three frames span **~50 ms**, so this can happen almost
immediately after the first frame closes.

The timeline, from the code:

```text
stage A: CONTROL 0x90 -> 0x8C          the safety epoch
first admitted unmask                  t_capture_start, and the SEARCH_WINDOW starts here
first Disc boundary                    the assembler anchors
+40 VIDEO blocks                       frame 0 closes, the capture sees its first frame
+3 eligible frames with equal sig      certification, stop
```

There is **no readiness gate**: nothing in the protocol state tells the probe
that the controlled stimulus is the thing on screen, and adding one that
recognised the stimulus would re-introduce exactly the circularity §V3.11
forbids.

**What this does and does not cost.** It cannot produce a false scientific
result: the offline analyser refuses a frame whose eight bars are not uniform and
refuses any frame that fits no hypothesis, so a menu certifies and then resolves
to `inconclusive_bar_not_uniform` or `inconclusive_no_hypothesis`. What it costs
is the RUN: it ends inconclusive without ever having looked at the stimulus.

**Requirement, to be resolved together with the ROM delivery method (§V3.7):**

```text
PHYSICAL PROCEDURE DEPENDENCY: the controlled stimulus must be displayed
                               BEFORE the probe's capture begins
STATUS: unresolved, owned by the operator, blocks EXECUTION ONLY
```

Routes considered, none implemented and none verified here:

* **A — the delivery route boots the ROM directly**, so the AGB is already
  showing the bars when the GameCube side starts. Costs nothing and needs no
  code; whether any available route does this is part of §V3.7.
* **B — a GameCube-side arming step**, separating setup from capture. The probe
  deliberately reads no controller input before its teardown returns, so this
  would be a real design change and is NOT made here.
* **C — an objective protocol readiness signal.** None exists. Everything the
  model can observe about a picture is a signature, and a signature cannot say
  *which* picture without being told, which is the circularity again.
* **D — none of the above is proven.**

No arbitrary delay is added to hide this. The 10 s SEARCH_WINDOW is a bound on
how long a stable image is searched for, measured from `t_capture_start` (the
first admitted unmask); it is **not** time in which to boot a menu, choose a ROM
or navigate a loader, and it is not changed here.

Everything below the implementation notes is the specification the code was
written against, and it stays the authority.

#### V3.0 What this experiment is for

Four physical runs have established the VIDEO transport: the block is 0xF00
bytes, the geometry is 240 × 160 pixels in 40 blocks of 4 raster lines, the
stride is 240 × 4 bytes, both reference decoders consume **byte 1 and byte 3** of
each 4-byte group as `word = (b1 << 8) | b3`, and bit 15 of that word carries the
frame-start flag on the first word of block 0. **None of that is reopened here.**

What is still unresolved is the one thing no capture without a cartridge can
settle: **which five of the fifteen colour bits are which channel, and whether
the path applies any transformation on the way out**. Two reference decoders
agree on a reading (bits 14–10 = R), but they agree with each other, not with a
measurement: no pixel of a *known* colour has ever been captured. U-GBP-011 has
said exactly this since 2026-09-16 and is what this experiment closes.

#### V3.1 Three spaces, kept apart by name

The single most common way to get this wrong is to call a group of GBP bits
"red" before the experiment has said so. This design forbids it:

```text
1. STIMULUS VALUE     the 15-bit value software writes into AGB VRAM.
                      The AGB's own framebuffer layout is documented hardware
                      (BGR555: bits 0-4 R, 5-9 G, 10-14 B) and is used ONLY to
                      say what the stimulus writes - never to name a GBP bit.
2. GBP SOURCE WORD    (b1 << 8) | b3, reconstructed from the raw 0xF00 block.
                      Its fifteen colour bits are called C14_10, C9_5 and C4_0.
                      They have NO channel name until V3.14 assigns one.
3. DISPLAY INTERPRET. which human channel a group of GBP bits corresponds to.
                      This is what the references assert and what the experiment
                      measures.
```

Until this experiment succeeds, no document may write "bits 14–10 are red" as a
statement about the GBP. It may write "both references *read* bits 14–10 as red",
which is a fact about the references.

#### V3.2 The hypotheses the references actually support

Extracted from `docs/research/VIDEO_PATH.md` §2.3, §2.4, §3.2 and §4 — not
invented here, and deliberately not extended into arbitrary permutations:

| # | Hypothesis | Source-bit mapping (stimulus → GBP word) | Byte order | Channel mapping asserted | Evidence source |
|---|---|---|---|---|---|
| H1 | **Channel swap on the path** (the references' reading is the displayed truth) | stimulus `b` → GBP `b` with C14_10 ↔ C4_0 exchanged relative to the AGB framebuffer | `(b1 << 8) \| b3` | C14_10 = R, C9_5 = G, C4_0 = B | Disc draws the word as `GX_TF_RGB5A3` (§2.3); GBI's renderer writes RGB5A3 tiles and its PNG writer uses R = bits 14–10 (§3.2); the Disc's embedded idle frame renders its logo indigo under that reading (§2.4) |
| H2 | **Verbatim AGB order** (the GBP hands the framebuffer value through unchanged) | identity: GBP word = stimulus value | `(b1 << 8) \| b3` | C4_0 = R, C9_5 = G, C14_10 = B | the AGB's documented BGR555 framebuffer; Dolphin's model with mGBA's default `0x00BBGGRR` would produce this (§4, unverified, flagged as a divergence) |
| H3 | **Byte swap** | GBP word = `(b3 << 8) \| b1` of the stimulus, i.e. the two consumed bytes exchanged | reversed | whatever H1/H2 then implies | not asserted by any reference; included because the window doubles each byte (`hh hh ll ll`) and a swap would be invisible to every check made so far |
| H4 | **Intra-channel bit reversal** | within each 5-bit group, bit *k* → bit 4−*k* | `(b1 << 8) \| b3` | — | not asserted by any reference; included because no observation so far could have detected it |
| H5 | **Complement / stuck bits** | GBP word = `~stimulus & 0x7FFF`, or bits stuck at 0/1 | — | — | not asserted; the cheapest failure mode to rule out, and the one a single all-white capture would hide |

H1 and H2 differ **only** by exchanging the outer groups; every check performed
in this project so far — frame-start predicates, block checksums, byte-for-byte
comparison against the Disc's embedded frame — is invariant under that exchange,
which is precisely why four physical runs could not decide it.

**The prior, stated as a prior and not as a result.** The references' reading
renders the Disc's embedded logo indigo, and `VIDEO_PATH.md` §2.4 records indigo
as the real boot logo's colour; under H2 the same bytes would be crimson. That
makes H1 the expected outcome. It is an inference from a reference's embedded
asset, it is not physical evidence, and this experiment is designed to be
decisive either way — including the outcome where neither H1 nor H2 fits.

#### V3.3 The stimulus: eight vertical bars, 30 pixels each

A static AGB Mode 3 image, 240 × 160, 16-bit direct colour, no palette, no
scaling, all 160 lines identical:

```text
x 000..029   0x0000    zero reference          popcount 0
x 030..059   0x001F    low group, all five     popcount 5
x 060..089   0x03E0    middle group, all five  popcount 5
x 090..119   0x7C00    high group, all five    popcount 5
x 120..149   0x7FFF    all-bits reference      popcount 15
x 150..179   0x0001    bit 0 alone             popcount 1
x 180..209   0x0020    bit 5 alone             popcount 1
x 210..239   0x0400    bit 10 alone            popcount 1
```

Eight bars of 30 fill exactly 240 pixels. In the AGB's own documented order
those values are black, red, green, blue, white and the least significant bit of
red, of green and of blue — **written here for the record of what the AGB stores,
and never used by the analyser to name a GBP bit** (V3.1).

Why these eight and not others:

* `0x001F`, `0x03E0`, `0x7C00` isolate the three 5-bit groups: they reveal where
  each group lands **as a set**, which separates H1 from H2 and detects any
  group-level rearrangement;
* `0x0001`, `0x0020`, `0x0400` isolate the least significant bit of each group.
  Under H4 (intra-channel reversal) bit 0 would be observed at position 4, and
  the three full-group bars could never show it: **the low-bit bars are what make
  H4 falsifiable**, and without them a full-scale-primary-only pattern would
  leave a reversal indistinguishable from identity;
* `0x0000` and `0x7FFF` are the complement and stuck-bit controls (H5). Zero must
  stay zero and all-ones must stay all-ones under *any* bit permutation; if
  either fails, no permutation hypothesis can be true and the run says so instead
  of forcing one.

**What the eight bars determine, exactly.** They pin the image of bits 0, 5 and
10 individually, and the image of each 5-bit group as a set. They do **not** pin
a permutation that fixes bits 0, 5 and 10 and rearranges only bits 1–4 inside a
group. No reference suggests such a transformation and this design does not
chase it; V3.19 specifies the optional second pattern that would close it if
anyone ever needs to.

#### V3.4 Bit 15 is never written by the stimulus

Every pixel the stimulus writes has **bit 15 = 0**. That is not a detail: it is
what makes the flag observable. Any `bit15 = 1` seen in the GBP window then
cannot have come from the colour value, and its position — first word of block 0,
or elsewhere — is an independent observation about the frame-start flag
(GBP-HW-058 recorded the bytes; nothing has yet separated flag from colour).
Writing `0x8000` or `0xFFFF` as a colour would destroy that separation. A
deliberate experiment on what happens when VRAM *does* carry bit 15 is a
different test and is not mixed into this gate.

#### V3.5 Orientation

The bars have a known left-to-right order and the geometry is not reopened. The
analyser therefore checks x orientation as a *consequence*, not as an assumption:
the observed run boundaries must fall at x = 0, 30, 60, 90, 120, 150, 180 and
210, and the two invariant bars (`0x0000` at x 0–29 and `0x7FFF` at x 120–149)
must appear at those positions and nowhere else. A mirrored analyser would place
them at x 210–239 and x 90–119 and be refused. No extra spatial marker is added:
the pattern already carries the asymmetry, and a marker would add a colour value
whose interpretation is exactly what is under test.

#### V3.6 The stimulus ROM, specified deterministically

```text
target        AGB / GBA, 32-bit ARM or Thumb, no BIOS call that alters video
entry         standard GBA header, entry branch to main
display       REG_DISPCNT (0x04000000) := 0x0403
                mode 3 (bits 0-2 = 3), BG2 enabled (bit 10), everything else 0:
                no OBJ, no BG0/1/3, no window, no forced blank after setup
blending      REG_BLDCNT (0x04000050) := 0x0000, REG_MOSAIC := 0x0000
scroll/affine untouched: mode 3 has no scroll registers that affect the bitmap
palette       never read in mode 3 - there is no palette indirection to get wrong
VRAM writes   0x06000000 + (y * 240 + x) * 2 := bar value, for all y in 0..159
              and all x in 0..239, written once before the final loop
sprites       OAM cleared, OBJ disabled in DISPCNT
interrupts    REG_IE := 0, REG_IME := 0; no handler is installed and nothing
              after the initial fill writes VRAM again
sound         untouched; the GBP AUDIO window is drained by the probe but this
              experiment interprets nothing from it (V3.13)
final state   `for (;;) { }` - a tight infinite loop, no VBlank wait needed
              because nothing changes after the fill
```

The source must be one small auditable file with no graphics framework. Built in
the project's Docker environment with devkitARM if it is added there, or by any
reproducible toolchain that is recorded; the build records **ROM size, SHA-256,
toolchain identity and the source path**, and the run envelope carries that
SHA-256 so a capture can never be attributed to an unidentified image.

`.gba` header note: the ROM must carry a valid Nintendo logo header area or the
AGB refuses to boot it. That is a property of the delivery method (a flash cart
supplies a compliant header; a multiboot image is loaded past that check) and is
recorded with the ROM identity, not assumed.

#### V3.7 PHYSICAL EXECUTION DEPENDENCY — how the ROM reaches the AGB

**This repository documents no way to run a controlled GBA ROM on the physical
hardware.** There is no flash cart, no EverDrive, no EZ-Flash, no multiboot cable
and no ROM-delivery procedure anywhere in `docs/`, `CLAUDE.md` or any executed
test. Every physical run so far was explicitly *without a Game Pak*.

The design does not invent one. It records:

```text
PHYSICAL EXECUTION DEPENDENCY: controlled GBA ROM delivery method
STATUS: unresolved, owned by the operator, blocks EXECUTION ONLY - not design,
        not implementation, not review
```

Candidate routes, none verified here, listed so the operator can choose:

1. **A flash cart in the GBP's Game Pak slot.** The simplest route if one exists.
   Consequence for the probe: the cartridge-sensing bits of CONTROL (0x01 GB-type,
   0x02 present, `docs/hardware/GBS-DOL.md`) will differ from every previous run
   — see V3.8.
2. **Multiboot over the Link Port** from the GameCube through a GC↔GBA link
   cable, the mechanism the `gba-as-controller` family of projects uses and which
   CLAUDE.md §6.7 already names as a reference. Whether the *GBP's internal AGB*
   accepts a multiboot image in the state the Start-up-Disc-equivalent
   initialization leaves it in is **UNKNOWN**, and proving it would itself be an
   experiment.
3. **Any other loader the operator owns.** Recorded with its identity if used.

Routes 1 and 2 differ in one way that matters to this experiment: route 2 leaves
the Game Pak slot empty, so CONTROL keeps the shape all four previous runs saw.
Route 1 changes it. Both are acceptable; the run envelope records which was used.

> **RESOLVED 2026-09-18 — route 1.** The text above is preserved as the design
> record of what was unknown on 2026-09-17. The dependency is closed: the
> operator's **EZ-Flash Omega DE in NOR / Mode B** delivered the derived stimulus
> image to the internal AGB, and it has now carried two physical runs,
> `color-0001` and `color-0002`. Route 1's predicted consequence was observed
> exactly as written: `CONTROL orig=92` instead of the `90` every cartridge-less
> run saw, i.e. the presence bit `0x02` set (§V3.8). The packaging step uses
> official devkitPro `gbafix` for the header's logo area, outside Git, into an
> ignored path; no proprietary bytes enter this repository. Route 2 (multiboot)
> was never attempted and stays untested.
>
> `STATUS: RESOLVED (route 1, EZ-Flash Omega DE NOR / Mode B)`

#### V3.8 The probe, and what it may not redesign

New POC, `poc/gbp-video-color-probe/`, Test ID **GBP-VIDEO-003**, Build ID
`color-0001` (the family convention; the implementation round fixes it). It is a
new POC because its capture, its stop rule and its sidecar differ from
GBP-VIDEO-002's — **not** because anything in the service path changes.

It reuses, unchanged and without a second opinion, the path validated across
GBP-INIT-003A/003B/004, GBP-AV-SERVICE-001, GBP-VIDEO-001 and the four
GBP-VIDEO-002 runs:

```text
GBP detection and the AR_INFO expansion handling
the 003A stage: CONTROL read, shape checks, control_exp = (orig & ~0x10) | 0x0C
the 003B extended one-shot handler, byte-identical
__MaskIrq / __UnmaskIrq through libogc2 only
READ of the IRQ window (one read, 32 bytes)
AUDIO 0x1000 drain when pending, VIDEO 0xF00 drain when pending
ACK = pending | 0x8000, PI clean, REARM = IRQ := 0, WAIT_NEXT
the 003A teardown extended by the handler restore and the mask check
```

**The CONTROL byte with a Game Pak present.** `control_exp` is computed from what
the device reports — `(control_orig & ~0x10) | 0x0C` — so a cartridge-present
byte flows through the same transform with no code change. Its value will differ
from the `0x90 → 0x8C` every previous run saw, and that value is an
**observation of this run**, recorded, never a precondition. The stage's own
shape checks and the CONTROL readback still decide whether the run continues.

#### V3.9 The R3 policy is not relaxed for colour

GBP-VIDEO-003 reuses the semantic-disagreement policy exactly as physically
validated by `vstate-0004`:

```text
SOURCE_SERVICED (delta within AV_MASK)  nonfatal, counted, preserved; the run continues
Disc-extra                              the majority is authoritative; the omitted
                                        source is a recorded observation
majority-extra VIDEO                    the block is drained and the frame it lands in
                                        is QUARANTINED: it may never become colour evidence
SOURCE_OTHER / NON_SOURCE               fatal, exactly as today
the independent pending guard           fires on the authoritative value whatever the
                                        delta is, including delta == 0
```

A colour experiment is not a reason to weaken any of it. The one addition is a
consequence, not an exception: **a quarantined frame is excluded from evidence
selection** (V3.10), so a disagreement can cost the run a frame but can never
contaminate the mapping.

#### V3.10 What makes a frame eligible as colour evidence

A frame may be used for mapping only if **all** of these hold:

```text
complete                 exactly 40 blocks, in order, one frame-start boundary
no resync                the assembler was anchored throughout
no transport anomaly     every drain completed, rc ok, no timeout, no busy
F_ANOMALY                clear
F_MAJORITY_EXTRA         clear  (no block drained only because of the majority)
source-deferred          no VIDEO deferral inside the frame
quarantine               absent
stability                the frame belongs to a certified stable window (V3.11)
```

Anything short of that is recorded and not used. The probe never repairs a frame,
never fills a missing block and never averages: the mapping is an exact
comparison or it is nothing.

#### V3.11 Recognising the stimulus without assuming the answer

The probe must know the pattern is on screen without using the channel order it
is trying to measure. Three properties do that, and all three are invariant under
**any** bit permutation of the fifteen colour bits:

```text
1. STRUCTURE   each scanline is 8 runs of exactly 30 identical 4-byte groups,
               with boundaries at x = 0, 30, 60, 90, 120, 150, 180, 210, and the
               eight run values pairwise distinct
2. REPETITION  the 4 scanlines of a block are byte-identical to each other, and
               all 40 blocks of the frame are byte-identical except block 0's
               first word, which may differ only in the frame-start flag bits
3. POPCOUNT    the multiset of popcounts of the eight observed colour15 values is
               exactly { 0, 1, 1, 1, 5, 5, 5, 15 }
```

Property 3 is the elegant one: a permutation moves bits, it cannot change how
many are set, so the fingerprint identifies the pattern while saying nothing
about which bit went where. Together with the two invariant bars — the only
value with popcount 0 must sit at x 0–29 and the only one with popcount 15 at
x 120–149 — the probe can assert "this is the stimulus" with **zero** circularity.

A flash-cart menu, a BIOS screen or a partially drawn framebuffer fails property
1 or 3 immediately. No "wait a few seconds" rule is used anywhere.

#### V3.12 Stability, certification and the stop rule

```text
SEARCH       from the first admitted cycle, assemble frames and test V3.11 on
             each complete clean one. Bounded by the search window below.
CERTIFY      N_STABLE = 3 consecutive eligible frames whose raw per-block
             signatures are identical. N = 3 is the project's existing evidence
             threshold (GBP_VSTATE_N_STABLE / BASELINE_FRAMES, HARDWARE_TESTS
             §R2), not a new number invented here; at ~59.7 Hz it spans ~50 ms.
PRESERVE     the raw 0xF00 of all 40 blocks of the certified frame and of the two
             that follow it, if they are also eligible and identical - three
             frames of independent confirmation (V3.13).
HOLD         continue for HOLD_FRAMES = 60 more frames (~1 s, the project's
             existing EPISODE_MAX_FRAMES) and record whether the signature still
             holds. A change is REPORTED, never fatal, and never edits what was
             already preserved.
STOP         immediately after the hold window: status ok_color_frames_captured.
```

> **SUPERSEDED — the HOLD and STOP lines above are NOT what the implementation
> does, and must not be read as the current contract.** The design text is kept
> verbatim because it is what the implementation was reviewed against, but
> §V3.24 replaced both: there is **no hold window**, and the run **stops at
> certification**. The reason is structural, not a trim — serving 60 further
> frames would rotate the raw ring over the very frames the hold was meant to be
> confirming, so the hold and the preservation could not both exist. HOLD was
> `REPORT ONLY` and never part of the success condition, so nothing that was
> evidence was lost. The stop status is `color_certified`.
>
> The CERTIFY line above, by contrast, is unchanged and was always right: the
> design said "consecutive eligible frames whose raw per-block signatures are
> identical". The first implementation over-implemented it with a full-frame
> `memcmp`; the fix brought the code back to the specification rather than
> changing it.

Caps, each justified rather than inherited:

```text
SEARCH_WINDOW      10 s   two orders of magnitude more than the ~50 ms a visible
                          pattern needs to certify; enough for an operator to be
                          slow, short enough that a failed run costs nothing
HARD_WALLCLOCK     30 s   search + hold + teardown with a wide margin. The 120 s
                          and 180 s of the vstate probe are NOT inherited: that
                          target came from the Start-up Disc's detector window,
                          which has nothing to do with this question
FRAME_CAP        1 024    ~17 s of frames; the store only ever holds signatures
DELIVERY_CAP   250 000    ~40 s at the 6 336 deliveries/s measured in vstate-0004
RAW_BUDGET   3 frames    3 x 40 x 0xF00 = 460 800 B, plus 2 AUDIO blocks (8 KiB)
```

If the search window expires without a certified frame the run ends
`ok_stimulus_not_recognised` — operationally valid, scientifically
**INCONCLUSIVE**, and it says which of the three properties failed.

#### V3.13 Raw is the evidence

The sidecar preserves the **whole 0xF00 of all 40 blocks** for each certified
frame, exactly as the transport delivered them, plus the per-block context the
existing probes already record (cycle, pending value, predicates, transfer
timings, ISR fields). It preserves no converted image and no RGB triple: every
reconstruction — `word = (b1 << 8) | b3`, the split of bit 15, the per-bar
values, the hypothesis tests — happens offline from those bytes, so the decision
can be redone, and disputed, without the console.

Bytes 0 and 2 of every group, which no reference consumes, are preserved with the
rest. They are not interpreted; they have carried surprises before (GBP-HW-093)
and discarding them would be discarding evidence.

AUDIO is drained whenever pending, exactly as the validated path requires, and
summarised; its bytes are not interpreted by this experiment.

#### V3.14 The offline analysis, step by step

```text
1. load the certified frame's 40 raw blocks from the sidecar
2. rebuild the 240 x 160 grid of source words:
     block b, row r, pixel x  ->  offset b*0xF00 + r*960 + x*4
     word = (b1 << 8) | b3          b1 = byte 1, b3 = byte 3 of that group
3. split every word:   flag15 = word & 0x8000      color15 = word & 0x7FFF
4. structure check (V3.11) on every one of the 160 rows, independently
5. per bar, collect the set of color15 values over its 30 x 160 pixels.
   EXACT uniformity is required: one set, one element. Any second value is
   reported with its coordinates and the run is INCONCLUSIVE - no averaging,
   no majority, no tolerance
6. build the observed vector O = (o0 .. o7) in bar order
7. for each candidate hypothesis H, apply H to the stimulus vector
     S = (0x0000, 0x001F, 0x03E0, 0x7C00, 0x7FFF, 0x0001, 0x0020, 0x0400)
   and require H(S) == O in ALL EIGHT positions
8. report every hypothesis that survives, with the full table
9. map flag15 separately: the set of coordinates where it is 1, compared with
   the frame-start predicate's expectation (first word of block 0)
10. b1 and b3 are also recorded per bar, so a byte-swap hypothesis (H3) is
    testable without re-deriving the word
```

Step 7 is an exact equality over eight values, not a similarity score. "Closest
match" is not a decision procedure and is not used.

#### V3.15 How each hypothesis is distinguished

With `S` as above, the eight expected vectors are distinct for every candidate:

```text
stimulus      H2 identity   H1 group swap   H4 intra-reversal   H5 complement
0x0000        0x0000        0x0000          0x0000              0x7FFF
0x001F        0x001F        0x7C00          0x001F              0x7FE0
0x03E0        0x03E0        0x03E0          0x03E0              0x7C1F
0x7C00        0x7C00        0x001F          0x7C00              0x03FF
0x7FFF        0x7FFF        0x7FFF          0x7FFF              0x0000
0x0001        0x0001        0x0400          0x0010              0x7FFE
0x0020        0x0020        0x0020          0x0200              0x7FDF
0x0400        0x0400        0x0001          0x4000              0x7BFF
```

Read the table by column and the discriminations are immediate:

* **H1 vs H2** — the three full-group bars already separate them (`0x001F` is
  observed as `0x001F` or as `0x7C00`), and the low-bit bars confirm it
  independently (`0x0001` observed as `0x0001` or as `0x0400`). Two independent
  witnesses for the same conclusion, which is why a full-scale-only pattern would
  have been weaker;
* **H4** — invisible to the group bars (`0x001F` reversed is still `0x001F`) and
  unmistakable on the low-bit bars (`0x0001` → `0x0010`). This is the whole
  reason the low-bit bars exist;
* **H5** — announces itself on the two reference bars (`0x0000` → `0x7FFF`);
* **H3** — tested on the preserved `b1`/`b3` pair, not on the assembled word;
* **combinations** (say group swap *and* byte swap) are generated and tested
  mechanically from the same eight values; the table above lists the pure forms.

#### V3.16 When the experiment answers, and when it does not

**Success requires all of:**

```text
ROM identity known (size, SHA-256, toolchain) and recorded in the run envelope
the eight stimulus values known exactly, by construction
>= 1 certified eligible frame, raw bytes of all 40 blocks preserved
every bar exactly uniform across its 30 x 160 pixels
the low-bit controls consistent with the group controls
0x0000 and 0x7FFF behaving as the controls require
EXACTLY ONE candidate hypothesis reproducing all eight observed values
bit 15 analysed separately and never folded into a colour comparison
no quarantined, incomplete, resynced or anomalous frame used
restore ok, handler restored, INTMR clean, teardown complete
```

**INCONCLUSIVE if any of:** more than one hypothesis fits (the stimulus did not
discriminate — refine it, do not choose); none fits (preserve the raw, open a new
unknown, do not force an interpretation); a bar is not uniform; no frame is
certified; the pattern is never recognised; the run aborts on the disagreement
policy. Inconclusive is a result and is reported as one.

#### V3.17 What becomes FACT, and what stays open

On success the promotions are narrow and literal:

```text
FACT   the association between each observed group of GBP bits and the exact
       15-bit value the AGB framebuffer held, for this stimulus, on this unit,
       through this path
FACT   the exact transformation (identity, group exchange, byte order, ...) the
       physical path applied to those values
FACT   whatever bit 15 did while the stimulus never set it
```

Only **after** that may a document write "C14_10 is red", and only because the
AGB's own documented framebuffer layout says which channel the stimulus wrote.

**Still open afterwards:** whether the same mapping holds for AGB video modes
other than Mode 3, for GB/GBC titles, for a different GBP board revision or under
a different GBS-DOL state. One stimulus mode is evidence about that mode and this
path; extending it is a separate claim that needs its own justification.

**U-GBP-011** is the unknown this closes. **U-GBP-033 is untouched**: the replica
non-uniformity has nothing to do with colour order, and this experiment neither
needs it answered nor contributes to it.

#### V3.18 Comparing with the Start-up Disc and GBI

Once the transformation is known, the comparison is mechanical and is stated in
advance so the result cannot be chosen after the fact:

```text
both references read   word = (b1 << 8) | b3, force bit 15, treat bits 14-10 as R
                       (Disc: GX_TF_RGB5A3 texture; GBI: RGB5A3 tiles + PNG writer)
if H1 is confirmed     both references display the stimulus correctly; the GBP
                       path exchanges the outer groups relative to AGB VRAM, and
                       the references' reading is the displayed truth
if H2 is confirmed     both references render AGB red as blue and vice versa.
                       That is a claim about a display convention, checked against
                       the Disc's own embedded frame before it is called anything:
                       the same bytes decoded both ways, side by side
if neither fits        the references are consistent with each other and with
                       neither reading of the physical bytes: preserve, report,
                       open an unknown
```

A divergence between the physical result and a reference is **documented as a
divergence**, never called a bug in the reference without the analysis that
earns the word (`CLAUDE.md` §6.1). Dolphin's model is auxiliary throughout: its
mGBA-derived order (§4 of VIDEO_PATH) is a known suspected divergence and is
never evidence.

#### V3.19 Optional follow-up, not part of this gate

A second pattern with `0x0002 / 0x0004 / 0x0008 / 0x0010` (and the equivalents in
the other two groups) would pin every one of the fifteen bits individually rather
than three of them plus three sets. It is **not** required: no reference suggests
a transformation that fixes bits 0, 5 and 10 while rearranging bits 1–4, and this
design does not manufacture hypotheses to defeat. It is recorded here so that, if
the first run ever produces a residual ambiguity, the next step is already
written.

#### V3.20 Sidecar: a dedicated format, and why not OGBPSEQ1

Three options were considered:

```text
A. OGBPSEQ1 v5 (vstate)   REJECTED. Its contract is the vstate probe's: frame
                          signatures, a learned baseline, episodes, a structured
                          change, a 1024-byte semantic block about disagreement
                          policy. None of that describes this capture, and
                          stretching a versioned contract to fit a different
                          experiment is how formats stop meaning anything
B. OGBPSEQ1 v1 (VIDEO-001) CLOSE, but not reused: its shape - bounded cycle
                          table, VIDEO/AUDIO tables, raw blocks - is right, yet
                          it is the frozen format of a physically executed run
                          and it carries no notion of a certified frame
C. a new dedicated format  ADOPTED
```

`OGBPCOL1` version 1, modelled on v1's proven discipline (big-endian, fixed
offsets, field by field, no struct copy, no pointer, no RAM address, no padding,
reserved bytes zero, identity that does not fit is an error, header CRC + total
CRC + `OGBPEND1`-style footer, streamed after the teardown):

```text
header          identity, toolchain, tb_hz, counters, the stimulus ROM SHA-256,
                the eight expected stimulus values, the caps of V3.12, the
                certification result and the teardown record
frame table     one record per assembled frame: index, blocks, flags, eligibility,
                per-block raw signature, the structure/popcount verdict of V3.11
certified table one record per preserved frame: which frame, its 40 block offsets,
                the per-bar observed words and b1/b3 pairs as the PROBE saw them
                (a cross-check of the offline reconstruction, never its source)
cycle table     the bounded per-cycle records of the certified window
diag table      the R3 disagreement records, same 160-byte layout and the same
                v5 cross-field contract - the policy is shared, so its evidence
                format is shared
raw VIDEO       3 x 40 x 0xF00 whole blocks, verbatim
raw AUDIO       2 blocks, summarised elsewhere
footer          magic + CRC-32 of everything before it
```

The diagnostic record is reused deliberately: it is the one part of the vstate
contract that is genuinely about the shared service policy rather than about the
vstate experiment, and it has been physically validated (GBP-HW-111).

#### V3.21 Replay and offline reproducibility

The raw log becomes a versioned `.gbpreplay` fixture under `captures/fixtures/`
by the existing rule (raw in `logs/`, copy in `captures/local/`, fixture
identified by the raw hash and size), and the sidecar is preserved byte-identical
beside it. The host battery must then be able to:

```text
re-parse the sidecar strictly and refuse any tampering
rebuild the 240 x 160 words from the raw bytes alone
re-run the structure, popcount, uniformity and orientation checks
re-run every hypothesis in V3.15 and reproduce the same unique answer
reproduce the bit-15 map
do all of it with no console, no screenshot and no reference to the text log
```

A screenshot is never evidence here. The conclusion must survive as bytes.

#### V3.22 Run envelope (for the implementation round, not an authorization)

```text
Test ID:   GBP-VIDEO-003            Build ID: color-0001 (to be fixed at build)
DOL:       poc/gbp-video-color-probe (does not exist yet)
Stimulus:  the Mode 3 ROM of V3.3/V3.6, identity recorded, bit15 never written
Cartridge: depends on the delivery route chosen in V3.7 - recorded, not assumed
Link Port: empty unless the route needs it (route 2 uses it); recorded either way
BBA:       attached, no cable, as in every previous run
Steps:     launch through Swiss with the stimulus already running and visible,
           wait for the probe to report, press X to save, START, power OFF
After:     POWER CYCLE MANDATORY (CONTROL transform and IRQ writes, CLAUDE.md §18)
Answers:   which five bits are which channel, and what the path does to them
```

**This is a design, not a request.** No hardware run is authorized by this
section, the probe does not exist, the ROM does not exist, and the delivery
dependency of V3.7 is unresolved.

---

### PRE-HANDLER MASKED WAIT (build `vstate-prewait-5000`) — does the unit tolerate seconds between stage A and the handler? — **PHYSICALLY EXECUTED 2026-09-18; PASS for 5000 ms at that position**

**Why this run existed.** GBP-VIDEO-003 certifies on three consecutive
signature-identical eligible frames, and the probe itself starts the AGB
(CONTROL `0x90 -> 0x8C`, `gbp_initirqa_probe.c:649`). Capture opens 107 ms later
at the first unmask, and `vstate-0004` measured three identical clean frames
77 ms after that — so the colour capture would certify inside the AGB's boot
(§V3.26). The only position where an operator step could sit is between stage A
and the handler install: the AGB is already running, PI is masked, and nothing is
in flight. Whether the hardware tolerates *sitting* there was UNKNOWN. This run
answers that and only that.

```text
Test ID   GBP-VIDEO-002 (the vstate probe, unchanged apart from the wait)
Build ID  vstate-prewait-5000          commit 500429a
DOL       sha256 b5f0060a46d2e6429f494a9fa53d14acf07a97f61d01847acf0b6cb807a48709
          443 968 B, built from commit 500429a
          IDENTITY WARNING: the build path that produced it,
          build/poc/gbp-video-state-probe-prewait/gbp-video-state-probe.dol,
          rebuilds to a DIFFERENT hash at any other commit, because the commit
          identity is embedded in the image. What was physically validated is the
          vstate-prewait-5000 VARIANT at commit 500429a with the hash above. A
          rebuilt DOL inherits the source behaviour and NOT the physical status:
          compare its hash against b5f0060a... before calling it the tested
          artifact.
log       logs/GBP-VIDEO-002_vstate-prewait-5000.log
          45 943 B   sha256 20b5e2a78047fe355a16328021092a01cb7da3d5f790e1cd957c8858f3f7555d
sidecar   logs/GBP-VIDEO-002_vstate-prewait-5000-vstate.bin
          2 024 204 B  sha256 79a44f82eceeff4c81fcc4b40c6d58b2fcf68405f4c9b6a85cb9d83c63e69a28
          OGBPSEQ1 v5, header CRC valid, footer OGBPEND1, total CRC 4315e14a valid
```

**Result: PASS.** 5.000 000 22 s elapsed against 5 000 ms requested; CONTROL,
IRQ, INTSR and INTMR identical either side; handler install, PREUNMASK, first
unmask and first delivery all normal; 1 108 063 unmasks = deliveries = acks =
rearms; clean restore (GBP-HW-116 to GBP-HW-119).

**What this does NOT establish.** Only the duration and the position exercised.
Not 10 s, not 30 s, not an unbounded wait. And nothing about what the AGB was
displaying: the probe reads no VIDEO before the handler exists.

#### How this run must be classified

It ended on `stop=safety_budget`, `status=ok_no_change_inconclusive`, with
`capture_s=174.892`, `valid_s=119.608` against a 120 s target and
`valid_at_target=0`. **It is not a vstate run that reached its scientific
target**, and it must never be counted as one: the 5 s pause is inside the
180 s safety budget, so the budget expired 0.392 s of valid observation short.
That is the expected arithmetic of the diagnostic, not a failure — the question
it was built to answer is answered by the first six seconds of the run.

Classification, in full: **PREHANDLER MASKED-WAIT 5000 ms — PHYSICAL DIAGNOSTIC
PASS.** Nothing else.

#### Instrumentation defect, non-blocking

The log records `truncated=1`. The truncated line is `PREHANDLERWAIT`, which hit
the logger's 255-character line limit and ends at `intmr_po`. It costs nothing:
the `WAITPRE` and `WAITPOST` snapshots record CONTROL, IRQ, INTSR **and INTMR**
separately and in full, on their own lines, which is where the values quoted
above come from. Registered as an **INSTRUMENTATION DEFECT / NON-BLOCKING**; the
physical test does not need repeating.

**FIXED 2026-09-18**, after the defect recurred in `color-0001`. The record is
now split by subject into `PREHANDLERWAIT` (ms, want_ticks, begin, end, elapsed,
iters, done) and `PREHANDLERWAITSTATE` (the CONTROL / IRQ / INTSR / INTMR pair),
each well inside the 255-character line at every field's maximum width, and the
logger was **not** widened. Both are written after the wait ends and before the
handler is installed, so nothing moved in the critical path.
`tests/unit/test_gbp_video_state.c::test_prehandler_wait_records_fit_the_logger`
drives the probe at the physical magnitudes — the real 40.5 MHz base, the real
5000 ms wait, a clock origin that prints both timestamps at full width — and
asserts `truncated == 0`; it fails against the old single-line record, which is
how it was checked. **The two physical logs keep their `truncated=1` exactly as
recorded**: a log written before this change has one line, a log written after
has two, and the fixtures are never edited to match the newer code.

#### V3.27 The observability premise, tested and REJECTED

The arming audit had assumed an operator could watch for the colour bars and
press a button. That premise is false under Open-GBP, and the source says so:

* the Game Boy Player has no display of its own — AGB video reaches the
  GameCube only through the VIDEO window, over HSP;
* during the pre-handler wait the probe has drained nothing: every
  `gbp_avblock_read` and `gbp_vstate_video_target` call site is inside the
  service loop (`gbp_vstate_probe.c:1168, 1195, 1200, 1298`), which begins at the
  first unmask;
* and even afterwards nothing renders it. The GameCube framebuffer is a text
  console (`CON_Init`, `poc/gbp-video-color-probe/source/main.c:167-179`), and a
  repository-wide search finds exactly one `VIDEO_SetNextFramebuffer`, the
  console's own at line 174. No code path anywhere draws a captured VIDEO block.

So the answer to "can the operator see the bars while the probe waits?" is **B —
not visible**. The operator saw the bars in the delivery tests because GBI and
the Start-up Disc read the VIDEO window and render it; Open-GBP's probe does
neither.

**Consequence.** A controller-arm justified by "press when the bars appear" would
be a button pressed with no observability — no better than a fixed delay, and
worse for pretending to be evidence. It is not implemented.

What remains, and the recommendation:

| option | what it is | cost | verdict |
| --- | --- | --- | --- |
| **F — fixed pre-handler wait** | the mechanism this run just validated, enabled in the colour build | one config value | **recommended** |
| P — pre-arm preview/service | service and render VIDEO before arming, so the operator really can see | a display path, and the capture path running before the scientific window | large surface, new questions |
| C — stimulus recognition | the runtime waits until it sees the bars | — | **forbidden**: it is the circularity §V3.11 exists to prevent |

Option F audited against the colour build, all five answers YES: `t_capture_start`
is the first unmask (`gbp_vstate_probe.c:1065`) and therefore lands after the
wait; the SEARCH_WINDOW is measured from it (`:998`); no colour state exists
before the wait, because every `gbp_vstate_block` call is inside the loop; the
analyser still requires exactly uniform bars, an exact hypothesis match and
byte-identical A/B/C; and a capture that caught boot or a transition resolves to
`inconclusive_bar_not_uniform`, `inconclusive_no_hypothesis` or
`inconclusive_certified_raw_mismatch` — never a false mapping.

**Not yet enabled, and not yet claimed.** That 5 s is *enough* for the BIOS plus
cartridge boot to reach the bars is NOT established by anything here; only the
first physical colour run, or further physical evidence, can establish it. What
is established is that waiting 5 s there is safe.

#### V3.28 The fixed pre-handler wait, and the procedure for the first physical run

**What changed.** `color-0001` now sets `prehandler_wait_ms = 5000`. Nothing
else about the experiment moved: the stimulus, the eight bar values, the seven
hypotheses, `N_STABLE = 3`, the OGBPCOL1 v1 layout and every analyser gate are
byte-for-byte what the release audit at `e10423c` verified.

**Why, in one line.** The probe starts the AGB itself, capture opens 107 ms
later, and three signature-identical clean frames appear 77 ms after that
(§V3.26) — so without a wait the run certifies inside the boot animation. The
operator cannot compensate by watching, because nothing renders the AGB's video
at that point (§V3.27). The capture is therefore delayed, in the one position
where the AGB is running and no transaction is in flight.

**Where it sits, proven by test:**

```text
stage A (CONTROL 0x90 -> 0x8C, the AGB starts)
   -> fixed 5000 ms wait, PI masked, no handler, nothing in flight
   -> 003B handler install
   -> PREUNMASK
   -> first UNMASK  ==  t_capture_start
   -> first admitted service
   -> first closed frame reaches the colour hook
```

`t_control_transform <= wait_begin < wait_end <= t_capture_start` is asserted in
`tests/unit/test_gbp_video_state.c`, and a second test stops the run at the
first admitted delivery and shows the colour module still holds nothing: zero
frames, zero eligible, `run_len` zero, `ref_sig` untouched, no ring slot owned,
`gbp_vcolor_slots_ok()` false. The SEARCH_WINDOW is still measured from
`t_capture_start`, so it is unaffected by the wait.

**What 5000 ms means, stated exactly:**

| claim | status |
| --- | --- |
| the pre-handler position tolerates 5000 ms on this unit | **FACT** — GBP-HW-116…118 |
| 5000 ms is *enough* for the cartridge boot to reach the static bars | **UNKNOWN** |

The first colour run is therefore still an experiment, and "5 s is sufficient"
must not be written before physical evidence says so.

**The fail-safe if it is not enough.** A capture that opens on a boot screen, a
transition, or anything that is not the stimulus resolves to an INCONCLUSIVE
verdict, never to a mapping. The gates, in the order the analyser applies them:

1. fewer than three certified raw frames, or `raw A != raw B != raw C` byte for
   byte → `inconclusive_certified_raw_mismatch`, **before** any pixel is
   interpreted;
2. any of the eight 30-pixel bars not holding exactly one `color15` value →
   `inconclusive_bar_not_uniform` (a boot screen is not eight uniform bars);
3. an observed vector matching no hypothesis → `inconclusive_no_hypothesis`;
4. more than one hypothesis matching → `inconclusive_ambiguous`.

A wrong answer is not among the outcomes. The cost of an insufficient wait is a
spent run, not a false result.

**Build ID: still `color-0001`.** The identity names the experiment, and the
experiment is unchanged — same stimulus, same hypotheses, same frozen sidecar,
same analyser. What changed is *when capture opens*, which is procedure, not
experiment. A new id would suggest the scientific content moved and would break
the continuity between this candidate and the `e10423c` release audit. The
procedure is distinguished instead by the commit and the DOL hash, which is the
distinction this project already relies on.

#### V3.29 Physical procedure — first GBP-VIDEO-003 run

```text
Test ID:        GBP-VIDEO-003
Build ID:       color-0001
Cartridge:      EZ-Flash Omega DE, Mode B / NOR, holding the DERIVED delivery image
                sha256 bb741770e92ecdcf10f74ae32b01e338384047d8d82e4f14f2162ba9ec234fe3
                NOT the canonical stimulus 867bb8d6...f3ba, which has no Nintendo
                logo and will not boot from Mode B
Console:        physical GameCube + Game Boy Player DOL-017
Link Port:      nothing attached
BBA:            absent
Controller:     connected (port 1), used only for START/X after the run
Storage:        SD2SP2 with the DOL and space for the log and the sidecar;
                Memory Card as usual for Swiss
Launch:         Swiss
```

Steps:

```text
1.  cold power cycle
2.  Omega DE in Mode B / NOR with the derived delivery image
3.  launch the GBP-VIDEO-003 DOL through Swiss
4.  PRESS NOTHING from here until the run ends
5.  stage A starts the AGB
6.  the probe waits 5000 ms with PI masked - this is expected and silent
7.  capture begins automatically
8.  let the run finish on its own
9.  X saves the log and the sidecar
10. START exits
11. power-cycle the console
12. return both files
```

The operator does **not** need to see the bars, and could not: §V3.27. No input
enters the scientific window.

Expected on success: `stop=color_certified`, three certified frames, and a
sidecar that `tools/vcolor.py analyse` resolves to exactly one hypothesis. Every
other outcome is an inconclusive verdict that still produces a valid, strictly
parseable file — which is itself evidence about the wait.

---

### GBP-VIDEO-003 / color-0001 — first physical run — **EXECUTED 2026-09-18; the runtime PASSED, the analyser REFUSED, the verdict is INCONCLUSIVE**

```text
Test ID   GBP-VIDEO-003
Build ID  color-0001                   commit 9d8302d
DOL       build/poc/gbp-video-color-probe/gbp-video-color-probe.dol
          442 560 B   sha256 cc88e4c45559f11047ca657b78045e2fd2c5d646a1b68e7e453fcf796d177cf4
          IDENTITY WARNING: the device log records the commit and the build id,
          not a DOL hash, so the hash above is the build tree's at the declared
          commit 9d8302d. A rebuild at any other commit produces a DIFFERENT
          hash, because the commit identity is embedded in the image, and
          inherits the source behaviour but NOT the physical status. Compare
          hashes before calling any rebuilt DOL the tested artifact.
          build/swiss/11-color/boot.dol is a byte copy, not a second identity.
cartridge the controlled eight-bar AGB Mode 3 colour stimulus; CONTROL orig=92,
          i.e. the Game Pak presence bit 0x02 set (it reads 90 with no cartridge)
log       logs/GBP-VIDEO-003_color-0001.log
          40 790 B   sha256 28c5a06c8c852802b014fe8c97780d8e3a751166ad41be2e979e71ecb3f3bb8c
          kept in captures/local/, never versioned
sidecar   logs/GBP-VIDEO-003_color-0001-color.bin
          461 684 B  sha256 95595f9d9eb4945e42ee1653ade5a1cd72a3646d698cad254d32c84ba0762bb7
          OGBPCOL1 v1, header CRC 96002fc9 valid, footer OGBPCEND at 0x70B68,
          total CRC 19ebfbda valid, size == off_footer + 12
fixture   captures/fixtures/hw-gamecube-gbp-2026-09-18-color-0001.gbpreplay
          captures/fixtures/hw-gamecube-gbp-2026-09-18-color-0001-color.bin
```

**The runtime reached its target.** `stop=color_certified (8)`. The fixed 5000 ms
pre-handler wait elapsed in 202 500 008 ticks (5.000 000 20 s) with CONTROL, IRQ
and INTSR unchanged across it; capture then opened, frames went
`0 not_complete · 1 resync · 2, 3, 4 eligible`, and certification took the three
consecutive signature-identical eligible frames the design asks for. 440
deliveries = acks = rearms = unmasks (162 VIDEO, 288 AUDIO), 0 errors of any
class, 0 R3 disagreements, clean restore, `intmr_final=000001fa`. Capture 0.072 s
inside a 5.179 s / 30 s safety budget. GBP-HW-120, GBP-HW-121.

**The analyser refused it.** `tools/vcolor.py`, run unmodified:

```text
VERDICT: INCONCLUSIVE - CERTIFIED RAW MISMATCH
certified frames A and B are NOT byte-identical, so the runtime's signature
agreement was not byte agreement
first difference at byte 0x108 - block 0, x=66, y=0, byte_in_group 0,
consumed=False, a=83 b=03
```

Pairwise differing bytes A/B 2125, B/C 2073, A/C 2137, over all 40 blocks and all
160 rows. **This verdict stands.** GBP-HW-122.

**Where the differences are.** Every one of them is in byte 0 or byte 2 of its
four-byte group; bytes 1 and 3 — the only bytes either reference decoder reads —
differ in zero positions across all three pairs, so under
`word = (b1 << 8) | b3` the three certified frames are identical in 38 400 of
38 400 words. GBP-HW-123.

**Post-gate diagnostic projection, not the result.** Read through that
projection, each bar is uniform and identical in A, B and C, and the eight bars
map `0x0000 0x001F 0x03E0 0x7C00 0x7FFF 0x0001 0x0020 0x0400` →
`0x0000 0x7C00 0x03E0 0x001F 0x7FFF 0x0400 0x0020 0x0001`: the outer-group swap,
H1, on 8/8 bars; H2 survives only on the four swap-invariant controls. The
correct sentence is **"the post-gate diagnostic projection matches H1 exactly"**,
never "GBP colour mapping = H1". GBP-HW-124. **U-GBP-011 stays OPEN.**

**One thing this run isolated for free.** The flag word at x=0, y=0 is exactly
`0x8000` here — flag set, colour 0 — because bar 0 is black and the stimulus
never writes bit 15. Every earlier physical frame had `0xFFFF` there, where the
flag is indistinguishable from white. GBP-HW-125.

#### Why the gate is not being relaxed for this run

The gate's documented purpose is in §V3.25 and in `tools/vcolor.py` itself: *"a
checksum can collide; the bytes cannot"*. It exists to stop a `sig[40]` collision
from passing as frame stability — **not** as a claim that bytes 0 and 2 are part
of the picture. It is therefore stricter than the question it guards, and the
project's own pre-existing evidence already said so: GBP-VID-003 (2026-09-16)
records that bytes 0 and 2 are read by neither reference decoder; GBP-HW-058 and
GBP-HW-070 record the physical byte-0 deviations and state they do not alter what
either reference reads; U-GBP-021 forbids consuming byte 0; U-GBP-029 holds the
open question and already answers it operationally with *"the runtime rule stands
regardless: read pixels from bytes 1 and 3, as the references do"*; and
`src/gbp/gbp_vsig.h` excludes bytes 0 and 2 from the runtime signature citing
exactly that. None of this was discovered by `color-0001`.

That is precisely why the gate is not moved now. The criterion was pre-registered,
the run failed it, and re-reading the same bytes under a criterion chosen after
seeing them is not the experiment that was designed. `OGBPCOL1` v1 and
`tools/vcolor.py` stay frozen; `color-0001` stays INCONCLUSIVE; the fixture and
its measurements are pinned by `tests/host/test_vcolor.py::PhysicalColor0001` so
that a future relaxation of the gate fails loudly instead of quietly re-labelling
this run.

#### The next experiment — `color-0002`, pre-registered

1. **Write the contract first.** A new analyser version (`vcolor2` / `OGBPCOL2`,
   never an edit to v1) whose acceptance gate is the **consumed projection**
   `word = (b1 << 8) | b3`, justified in the document by GBP-VID-003 and
   U-GBP-029 *as they stood before any colour run*, with the full-raw comparison
   kept and reported as a separate mandatory diagnostic. State in advance what
   makes the run INCONCLUSIVE: a bar that is not uniform, two surviving
   hypotheses, none, or any difference in bytes 1/3.
2. **Do not reuse `color-0001` as the confirmation.** It is the run that
   motivated the contract; a new physical run judges it.
3. **Keep the stimulus unchanged** so the two runs are comparable, and keep the
   5000 ms wait, whose sufficiency in this position is now physical (GBP-HW-120).
4. **Report bytes 0/2 either way**, since U-GBP-029 is still open and every run
   with a non-uniform picture is new information for it.

#### Known instrumentation defect in this run — NON-BLOCKING

The log header declares `truncated=1`. The truncated line is `PREHANDLERWAIT`,
which hit the logger's 255-character limit and ends mid-token at `intmr_po`. This
is the same defect already registered for the `vstate-prewait-5000` run and it
costs nothing here either: `ms`, `want_ticks`, `begin`, `end`, `elapsed`, `iters`,
`done` and the CONTROL / IRQ / INTSR snapshots on both sides are all complete
before the cut, and only the trailing `intmr_post` value is lost while INTMR is
reported in full elsewhere in the same log. Recorded as an INSTRUMENTATION DEFECT
and not as a result of the experiment; the fix belongs to whichever round touches
the logger, not to this one.

---

## V4 — GBP-VIDEO-003 / color-0002: PRE-REGISTERED CONFIRMATORY CONTRACT — **EXECUTED 2026-09-18, CONTRACT PASSED, `CONFIRMED_EXACT_H1_OUTER_GROUP_SWAP`** (result in §V4.10)

**This section is written BEFORE the physical run it judges, and it is frozen by
the commit that adds it.** Its purpose is to remove one specific way of being
wrong: `color-0001`'s bytes are already known, so an acceptance criterion written
now could be shaped — deliberately or not — to fit them. Writing the criterion
down first, in a versioned file, with a distinct build id, is the only thing that
makes the next run's result mean anything.

**Any change to this contract after `color-0002` has physically run requires a
new experiment id (`color-0003`).** Editing §V4 after seeing its own data is
exactly the failure it exists to prevent.

### V4.1 Why there is a second experiment at all

`color-0001` ran on 2026-09-18 (§"GBP-VIDEO-003 / color-0001"). The capture did
everything it was designed to do — `stop=color_certified`, three eligible frames
with identical `sig[40]`, clean service and restore. Its **offline contract**
refused it: the gate required the three certified frames to be byte-identical
over all 153 600 raw bytes, and they differ in 2125 / 2073 / 2137 bytes pairwise
(GBP-HW-122).

Every one of those bytes is in position 0 or 2 of its four-byte group. Bytes 1
and 3 — the only bytes either reference decoder reads — differ in **zero**
positions, so the picture itself was identical in all three frames (GBP-HW-123).

**The root cause, named plainly.** The runtime's stability filter `sig[40]`
(`src/gbp/gbp_vsig.c`) consumes bytes 1 and 3 and nothing else, and always has.
`color-0001`'s offline gate compared all four. The two halves of the experiment
were looking at different data, and the mismatch — not the device, not the
capture — is what produced the refusal. `color-0002` makes them look at the same
bytes while keeping the offline comparison exact and authoritative.

### V4.2 What does NOT change

Everything except the offline contract. This is deliberate: two runs that differ
in one variable are comparable, and a stimulus or hypothesis tuned after seeing
`color-0001` would destroy that.

```text
stimulus            stimulus/agb-color-bars, unchanged
                    canonical    sha256 867bb8d681e815793792e5e85bf031967eec11c07d00dcb16e68b6c96520f3ba  (1076 B)
                    derived      sha256 bb741770e92ecdcf10f74ae32b01e338384047d8d82e4f14f2162ba9ec234fe3  (1076 B)
                                 the derived image is the canonical one with the header's logo area
                                 filled by official devkitPro gbafix; the payload past 0x0C0 is
                                 byte-identical, it is NEVER committed, and no proprietary bytes
                                 enter this repository at any point
values              0x0000 0x001F 0x03E0 0x7C00 0x7FFF 0x0001 0x0020 0x0400
                    eight 30-pixel bars, AGB Mode 3, bit 15 never written by the stimulus
hypotheses          the seven pre-registered transformations in tools/vcolor.py, frozen at bfbca70,
                    imported by tools/vcolor2.py as the same objects and never redefined
runtime             poc/gbp-video-color-probe, functionally unchanged
                    N_STABLE = 3, CERT_FRAMES = 3, SEARCH 10 s, HARD WALL-CLOCK 30 s
                    pre-handler wait = 5000 ms (GBP-VCOLOR_PREHANDLER_WAIT_MS)
                    the runtime still holds no stimulus value and cannot recognise a bar
sidecar             OGBPCOL1 v1, FROZEN at e10423c, unchanged
delivery            EZ-Flash Omega DE, NOR / Mode B, physical GBA and physical Game Boy Player
build id            color-0002   (the ONLY functional difference from color-0001)
```

**Why a new build id when the binary differs only in metadata.** Because the
build id is what `tools/vcolor2.py` keys its standing on. A contract written
after `color-0001` may not confirm `color-0001`, and the cleanest enforcement is
mechanical: the analyser emits a confirmatory verdict only for a sidecar whose
`build_id` is `color-0002`, and labels everything else RETROSPECTIVE.

### V4.3 The three domains

**A. TRANSPORT RAW DOMAIN** — the raw group `[b0 b1 b2 b3]`.

Bytes 0 and 2 are read by neither reference pixel decoder (GBP-VID-003,
2026-09-16), are physically variable (GBP-HW-058, GBP-HW-070, GBP-HW-126) and
remain semantically **UNKNOWN** (U-GBP-029). They are therefore **outside the
dependent variable of this experiment**.

This is *not* a claim that they are don't-care in general, and nothing here
licenses discarding them. They are preserved byte for byte in the sidecar, and
the full-raw comparison is computed and **reported on every run** as a mandatory
diagnostic — which is how U-GBP-029 keeps being fed rather than quietly closed.

**B. CONSUMED-WORD STABILITY DOMAIN** — the acceptance gate.

```text
word16 = (b1 << 8) | b3,  for each of the 240 x 160 = 38400 pixels

REQUIRE  A.word16[x,y] == B.word16[x,y] == C.word16[x,y]   for ALL 38400
```

**Bit 15 is inside this comparison and is not masked.** Any difference gives
`INCONCLUSIVE_CONSUMED_WORD_MISMATCH` and the analysis stops before a single
hypothesis is evaluated.

The projection is not invented here: GBP-VID-003 recorded it from both reference
decoders on 2026-09-16, before any colour run existed, and `src/gbp/gbp_vsig.h`
has excluded bytes 0 and 2 from the runtime signature since GBP-VIDEO-002 citing
the same evidence.

**C. COLOR MAPPING DOMAIN** — only after B and the flag check.

```text
flag15  = word16 & 0x8000        reported, never interpreted
color15 = word16 & 0x7FFF        the only thing the hypotheses ever see
```

Each of the eight 30-pixel bars must hold exactly **one** `color15` value across
its 160 rows. Comparison against the hypotheses is exact equality on all eight
values. **There is no score, no distance and no nearest fit.**

### V4.4 The flag15 rule, stated in advance

Before any mapping is evaluated:

- count the set flags in A, B and C;
- record their coordinates;
- require the three bitmaps to be **identical** → `FLAG15_STABLE`.

That equality already follows from the domain-B gate. It is asserted and reported
separately anyway, because "the flag map was stable" is a claim the record should
carry explicitly rather than by implication.

**`flag_count == 0` is NOT required.** Physical evidence already contradicts it:
every certified frame of `color-0001` carries exactly one set flag at x=0, y=0,
and so does every earlier physical frame (GBP-HW-125). A contract demanding zero
would refuse every real run.

**`FLAG15_STABLE` means reproducible across three frames of one run. It does not
mean understood.** No meaning is inferred here, and the status of what bit 15 *is*
stays exactly where GBP-VID-004 and GBP-HW-125 leave it.

### V4.5 The pre-registered hypothesis set and what each predicts

Exact vectors, computed from the frozen transformations and the frozen stimulus,
recorded here so that the prediction cannot be adjusted afterwards:

```text
                         bar0 bar1 bar2 bar3 bar4 bar5 bar6 bar7
stimulus                 0000 001F 03E0 7C00 7FFF 0001 0020 0400
H2_identity              0000 001F 03E0 7C00 7FFF 0001 0020 0400
H1_outer_group_swap      0000 7C00 03E0 001F 7FFF 0400 0020 0001
H3_byte_swap             0000 1F00 6003 007C 7F7F 0100 2000 0004
H4_intra_group_reversal  0000 001F 03E0 7C00 7FFF 0010 0200 4000
H5_complement            7FFF 7FE0 7C1F 03FF 0000 7FFE 7FDF 7BFF
H1_H4                    0000 7C00 03E0 001F 7FFF 4000 0200 0010
H1_H3                    0000 007C 6003 1F00 7F7F 0004 2000 0100
```

No two of these seven vectors are equal, so the stimulus discriminates the whole
pre-registered set: an ambiguous verdict would mean something went wrong, not
that the experiment was weak. `tests/host/test_vcolor2.py` pins that property.

**`color-0001`'s diagnostic projection produced the H1 row.** That is stated as
the reason to run a confirmatory experiment and for no other purpose. It may not
be used to change the stimulus, the hypotheses, the gate, a tolerance, a pixel
selection, a bar selection or an exception. **`color-0002` must be able to
falsify H1**, and it can: any of the seven can win, and so can none of them.

### V4.6 Exact success criterion

A confirmatory result requires **every** one of these:

```text
1  the sidecar parses under OGBPCOL1 v1, both CRCs recomputed and matching
2  exactly 3 certified frames, all with their raw preserved
3  consumed-word equality: 38400 of 38400 words identical across all three pairs
4  flag15 bitmaps identical across A, B and C
5  geometry valid: 40 blocks, 160 rows, 240 columns
6  all eight bars uniform in colour15
7  EXACTLY ONE pre-registered hypothesis reproduces all eight values exactly
8  the sidecar's build_id is color-0002

-> CONFIRMED_EXACT_<hypothesis>
```

### V4.7 Every inconclusive reason, enumerated in advance

```text
no_certified_frame                      the run preserved nothing to judge
inconclusive_certified_frame_count      not exactly three certified raw frames
inconclusive_consumed_word_mismatch     a consumed word differs between A, B or C
                                        (including a difference in bit 15 alone)
inconclusive_flag15_unstable            the flag bitmaps differ although the words do not
                                        — the two checks disagree, so the file is not trusted
inconclusive_geometry                   the frame does not reconstruct as 240 x 160
inconclusive_bar_not_uniform            a bar holds more than one colour15
inconclusive_no_hypothesis              none of the seven reproduces all eight values
inconclusive_ambiguous                  more than one does
retrospective_*                         the sidecar is not from build color-0002
```

An inconclusive run is a real outcome and is recorded as one. It is never
rescued by relaxing anything above.

### V4.8 What stays untouched

- `tools/vcolor.py` is **not modified** and gains **no new option**. Running it
  on `color-0001` must keep printing `INCONCLUSIVE - CERTIFIED RAW MISMATCH`
  forever; `tests/host/test_vcolor2.py` asserts that through the CLI, and also
  asserts the file has not changed since `bfbca70`.
- `OGBPCOL1` v1 is **not modified**. It already carries everything this contract
  reads: three certified records, three raw frames of 153 600 bytes with bytes 0
  and 2 intact, the identity fields and both CRCs. No v2 is needed, and the
  frozen header has not changed since `e10423c`.
- `color-0001` is **never re-labelled, re-judged or re-analysed as evidence**.
  Its fixture, its sidecar and its verdict stay exactly as ingested.

### V4.9 Physical procedure — identical to `color-0001`

```text
Test ID           GBP-VIDEO-003
Build ID          color-0002
DOL               build/poc/gbp-video-color-probe/gbp-video-color-probe.dol
                  exported as build/swiss/11-color/boot.dol (byte-identical copy)
                  the exact hash belongs to the commit it is built from: rebuild with
                  `make build`, read build/poc/gbp-video-color-probe/build-info.txt,
                  and confirm the commit there matches HEAD before the run
Cartridge         EZ-Flash Omega DE, NOR / Mode B
ROM               the derived stimulus image, sha256
                  bb741770e92ecdcf10f74ae32b01e338384047d8d82e4f14f2162ba9ec234fe3
                  built locally into an ignored path, never committed
Console           GameCube + Game Boy Player DOL-017
Link Port         EMPTY
BBA               ABSENT
Controller        connected, but NOTHING is pressed during the run
Logging           SD2SP2, launched through Swiss

Steps
  1  build, confirm the tree is clean and the commit in build-info.txt matches HEAD
  2  `make swiss`, copy build/swiss/11-color/boot.dol to the SD card
  3  put the derived stimulus image on the EZ-Flash Omega DE, NOR / Mode B
  4  insert the flash cart in the Game Boy Player
  5  power on, launch 11-color through Swiss
  6  DO NOT PRESS ANYTHING during the run: the probe starts the AGB itself and
     waits 5000 ms before the capture opens
  7  wait for the on-screen summary
  8  press X to write the log and the OGBPCOL1 sidecar
  9  press START to exit
 10  POWER CYCLE the console (the probe always requires it)
 11  return both files: GBP-VIDEO-003_color-0002.log and
     GBP-VIDEO-003_color-0002-color.bin

Question answered
  Under the contract above, and only under it: does exactly one pre-registered
  transformation reproduce all eight stimulus values? U-GBP-011 is closed by a
  CONFIRMED_EXACT verdict and by nothing else.
```

### V4.10 RESULT — executed 2026-09-18, the contract passed

```text
Test ID   GBP-VIDEO-003
Build ID  color-0002                   commit 39f1980
DOL       build/poc/gbp-video-color-probe/gbp-video-color-probe.dol
          442 592 B   sha256 d3c1f09efb105a0027d3bc596528448c579a234cbbe8306469d7f1222cbf29c1
          Built CLEAN at commit 39f1980 before the run, with no -dirty suffix, and
          build/swiss/11-color/boot.dol is a byte-identical copy of it. The log
          declares the same commit and build id. This is the first colour run whose
          candidate hash was fixed by a clean build at the exact commit the log names.
cartridge the controlled eight-bar AGB Mode 3 colour stimulus, derived image
          sha256 bb741770e92ecdcf10f74ae32b01e338384047d8d82e4f14f2162ba9ec234fe3
log       logs/GBP-VIDEO-003_color-0002.log
          40 900 B   sha256 194f92f916bbe77b2d445df98df46e00168b9b86197974cfe0c0795ded9b8ea1
          kept in captures/local/, never versioned
sidecar   logs/GBP-VIDEO-003_color-0002-color.bin
          461 684 B  sha256 f49c4cf2887ff1bdf2425cc7b0bbdad3a8d82a57c39f7d8894336147e3d48fd0
          OGBPCOL1 v1, header CRC f834e435, footer OGBPCEND at 0x70B68,
          total CRC f3f85d64 — all recomputed on ingestion, size == off_footer + 12
fixture   captures/fixtures/hw-gamecube-gbp-2026-09-18-color-0002.gbpreplay
          captures/fixtures/hw-gamecube-gbp-2026-09-18-color-0002-color.bin
```

**Neither the contract nor the analyser was touched between the pre-registration
and the run.** `tools/vcolor2.py` last changed at `a86b079`, the commit that
pre-registered it; `tools/vcolor.py` last changed at `bfbca70`. Verified by
`git log` and by an empty diff before the analysis was run.

#### The verdict, from the analyser run unmodified

```text
GBP-VIDEO-003 color analysis - CONTRACT color-0002 (tools/vcolor2.py)
file: test=GBP-VIDEO-003 build=color-0002 commit=39f1980

STANDING: CONFIRMATORY
B. CONSUMED-WORD STABILITY GATE   PASS: 38400 of 38400 words identical in A, B and C
C. FLAG15                         FLAG15_STABLE, count [1, 1, 1] at (0, 0)
D. BARS                           all eight uniform
   stimulus  0000 001F 03E0 7C00 7FFF 0001 0020 0400
   observed  0000 7C00 03E0 001F 7FFF 0400 0020 0001
E. HYPOTHESES                     H1_outer_group_swap ALL EIGHT; the other six fail
   orientation consistent: True

VERDICT: CONFIRMED_EXACT_H1_OUTER_GROUP_SWAP
```

Exit status 0. Every number above was **recomputed independently from the raw
bytes** before being accepted, including the per-bar colour over all 4800 pixels
of each bar in each of the three certified frames.

#### Each success criterion of §V4.6, checked

```text
1  sidecar parses under OGBPCOL1 v1, both CRCs recomputed and matching   PASS
2  exactly 3 certified frames, all with raw preserved (idx 2, 3, 4)      PASS
3  consumed-word equality 38400/38400 across all three pairs             PASS
4  flag15 bitmaps identical across A, B and C                            PASS
5  geometry valid: 40 blocks, 160 rows, 240 columns                      PASS
6  all eight bars uniform in colour15                                    PASS
7  exactly ONE pre-registered hypothesis reproduces all eight values     PASS
8  the sidecar's build_id is color-0002                                  PASS
```

#### Runtime, wait and restore

`stop=color_certified`; 440 unmasks = deliveries = acks = rearms (162/162 VIDEO,
288 AUDIO); 1840 transfers, 0 timeouts, 0 busy, 0 uncertain, 0 overflow,
`errors=0`, `transport_ok=1`, `SEMANTIC total=0`. Clean restore with readbacks,
`mask_ok=1`, `intmr_final=000001fa`, `pi_sticky_final=0`. Certification completed
66.635 ms after the capture opened; capture 0.072 s of a 5.179 s / 30 s budget.
GBP-HW-127.

The pre-handler wait elapsed 202 500 011 ticks (5.000 000 27 s) against 202 500 000
requested, `done=1`, with CONTROL, IRQ, INTSR and INTMR identical either side.
**The log header reads `truncated=0`** — the first physical confirmation that
splitting `PREHANDLERWAIT` into two records fixed the defect that marked both
earlier physical logs, with the trailing `intmr_post` now intact.

#### The full-raw diagnostic, reported as §V4A requires

```text
pair    total   byte0   byte1   byte2   byte3
A/B      2434    2222       0     212       0
B/C      2483    2244       0     239       0
A/C      2485    2264       0     221       0
```

40 of 40 blocks, 160 of 160 lines; first difference at `0x110`, block 0, x = 68,
y = 0, byte 0, `83` vs `03`. Bytes 1 and 3 differ nowhere. Evidence for
U-GBP-029, which stays OPEN. GBP-HW-133.

#### Cross-run corroboration, which the confirmation did not need

The three certified frames of `color-0001` and `color-0002` are byte-identical in
the consumed projection — 38 400 of 38 400 words in all three corresponding pairs
— across two physical runs at two commits with separate power cycles, while their
full raws differ in 2514, 2449 and 2481 bytes, again only in bytes 0 and 2.
GBP-HW-132. **`color-0001` is not re-judged by this**: it failed its own
pre-registered gate and stays `INCONCLUSIVE_CERTIFIED_RAW_MISMATCH` permanently.

#### What this run does NOT prove

- **Nothing about byte 0 or byte 2.** U-GBP-029 stays OPEN; this is its fifth
  corroboration and identifies no mechanism.
- **Nothing about why bit 15 is set.** The run shows the bit is not the colour
  value and is added on the path — the AGB wrote zero there — and that is all.
  The origin question is now **U-GBP-034**.
- **Nothing about U-GBP-033.** The pending-source mechanism is untouched.
- **No mapping outside what the stimulus discriminates.** Within a 5-bit group it
  pins bit 0, bit 5 and bit 10 individually and each group as a set; a permutation
  fixing those three while rearranging only bits 1–4 inside a group is not
  excluded. §V3.19 wrote that limit down before the run and holds the follow-up
  pattern; the run produced no residual ambiguity, so it is not triggered.
- **It does not make `color-0001` confirmatory in retrospect.** The analyser
  refuses to: `tools/vcolor2.py` reports any build other than `color-0002` as
  RETROSPECTIVE and never emits a `confirmed_*` verdict for it.

---

## V5 — GBP-VIDEO-004: SUSTAINED VIDEO STREAMING — DESIGN / PRE-REGISTRATION

**Status: DESIGN ONLY, 2026-09-18. Nothing here is implemented, nothing has
touched hardware, and no frozen format changes.** This section exists so that
the first streaming POC is built against a written specification instead of
against whatever seems reasonable at implementation time.

### V5.1 The ROADMAP requirement, quoted rather than paraphrased

`docs/ROADMAP.md`, Phase 4, verbatim:

> **GBP-VIDEO-004** — **NEXT**: sustained streaming with a real cartridge (frame
> pacing, dropped-block policy, output modes) — the bridge to Phase 7.

Phase 4's acceptance, verbatim:

> A real cartridge running on the physical GBP produces stable, correct video
> through the open-source runtime.

Phase 4's automated-test requirement, verbatim: *packet/register encoding; buffer
boundaries; frame conversion where applicable; deterministic synthetic frame
inputs; recorded hardware trace replay.*

And from the GBP-VIDEO-003 entry, which deliberately deferred the work to here:

> Rendering the frames on the GameCube is deliberately **not** part of this
> experiment … **First rendered frames and KEYPAD writes belong to a later step.**

**ROADMAP REQUIREMENT** is therefore exactly five things: sustained streaming, a
real cartridge, frame pacing, a dropped-block policy, output modes. Everything
below that is not one of those five is **PROPOSED DESIGN** and is labelled as
such.

### V5.2 Goal and non-goals

**Goal.** Establish, on physical hardware and with objective numbers, that the
Open-GBP service path can sustain the AGB's VIDEO stream for a defined duration
while a consumer outside the critical path assembles, converts and presents
frames, with every frame that is not presented accounted for by name.

**Non-goals**, each with the reason it is excluded:

| not in scope | why |
| --- | --- |
| audio playback | Phase 6. The service must keep *draining* AUDIO — see §V5.13 — but a sample never reaches the DAC here. |
| KEYPAD / controller input into the AGB | Phase 5. The roadmap defers it together with rendering. |
| scaling, aspect correction, filtering, presentation modes | Phase 9. §V5.12 marks them NON-BLOCKING UI POLICY. |
| A/V synchronisation | not named by the roadmap for Phase 4; claiming it would import a Phase 6 requirement. |
| network / BBA output | Phase 11. §V5.16 defines only the *interface shape* so Phase 7 and later can reuse it. |
| answering U-GBP-029, U-GBP-033 or U-GBP-034 | §V5.17 proves none of them blocks this experiment. |
| a general video runtime | this is an experiment with a pass criterion, not a product. |

### V5.3 Authority

Nothing in this design may weaken what physical runs already established. The
service order, the ACK/RE-ARM sequence, the disagreement policy and the teardown
are **authority**, reused byte for byte:

```text
interrupt → mask → read source → drain AUDIO → drain VIDEO → ACK
          → PI clean → signature + assembler → RE-ARM → wait next cause
```

`src/gbp/gbp_vstate_probe.c` records that order as
`read_audio_video_ack_piclean_sign_rearm_waitnext`, and it has survived
1 114 005 cycles in one run. **GBP-VIDEO-004 adds nothing to it.**

### V5.4 Dependency matrix — what is already proved

| dependency | status | source |
| --- | --- | --- |
| HSP service cycle: read, drain, ACK, re-arm, next cause | **FACT** | GBP-HW-062/063; GBP-AV-SERVICE-001 |
| One installed one-shot handler, 1:1 unmask/delivery/ack/rearm over ~1.1 M cycles | **FACT** | GBP-HW-117; `vstate-0004` |
| VIDEO block = 0xF00 bytes, one whole-block DMA | **FACT** | GBP-HW-051/058 |
| 40 blocks per frame, 4 raster lines × 240 px per block, line stride 960 B | **FACT** | GBP-HW-074…087 (legible 240×160 logotype) |
| Frame-start flag on the first pixel of a frame, both predicates agreeing | **FACT** | GBP-HW-069; GBP-HW-129 |
| Consumed pixel word = `(b1 << 8) \| b3` | **FACT** | GBP-VID-003; GBP-HW-123/128 |
| **Colour: the outer 5-bit groups are exchanged relative to AGB VRAM** | **FACT** | GBP-HW-131 (`color-0002`) |
| AGB frame cadence ≈ 59.727 Hz | **FACT** | GBP-HW-078 (477 intervals) |
| AGB and GameCube cadences are **not** synchronised; the runtime must tolerate slip | **FACT** (external observer), corroborated by GBP-HW-078 | GBP-PHY-003 |
| Frame classification: COMPLETE_40 / INCOMPLETE_SHORT / INCOMPLETE_LONG / PREDICATE_ANOMALY / RESYNC | **FACT (code)**, exercised physically | `src/gbp/gbp_vstate.h`; GBP-HW-074…087 |
| R3 semantic-disagreement policy: nonfatal, majority authoritative inside `SRC_MASK`, majority-extra quarantined | **FACT** (physically validated) | GBP-HW-108…115; §R3/§R4 |
| Raw ring with derived slot count, 3 or 4 slots, exact-match contract | **FACT (code)**, exercised physically | `gbp_vstate.c`; §V3.24 |
| Per-block signature `sig[40]` consuming bytes 1 and 3 only | **FACT (code)**, exercised physically | `gbp_vsig.c:15`; GBP-HW-128 |
| Clean teardown and restore with readback | **FACT** | GBP-HW-118; GBP-HW-127 |
| 5000 ms pre-handler wait sufficient in its position, this setup | **FACT** | GBP-HW-120, GBP-HW-127 |
| EZ-Flash Omega DE NOR / Mode B delivers a controlled ROM to the internal AGB | **FACT** | `color-0001`, `color-0002`; §V3.7 resolution |
| `GX_TF_RGB5A3` = 0x5 exists in this toolchain's `ogc/gx.h`, with `GX_InitTexObj` | **FACT (code)** | `libogc2:20260805`, verified in the container |
| The Start-up Disc renders the same stream as a 240×160 `GX_TF_RGB5A3` texture | **FACT (code)** | `VIDEO_PATH.md` §2.3 (`FUN_8008EFB4`, `FUN_80009044`) |
| Bytes 0 and 2 vary and mean nothing established | **UNKNOWN** | U-GBP-029 |
| What sets bit 15 | **UNKNOWN** | U-GBP-034 |
| Mechanism of IRQ-window replica non-uniformity | **UNKNOWN** | U-GBP-033 |
| Sustained streaming with a moving image | **UNKNOWN — this experiment** | — |
| Any GX pipeline in this repository | **DID NOT EXIST** when this design was written: every POC used `VIDEO_Init` + `CON_Init` on one XFB and printed text, and no POC had ever called `GX_Init`. **Changed 2026-09-18 by the implementation of this design** — `poc/gbp-video-stream-probe` is the first, and `main.o` is the only object in the tree permitted to name `GX_` (§V5.15, audit profile `stream`). | verified across `poc/` and `src/` |

**Nothing in this matrix needs re-running.** The two genuinely new things are a
*moving* source and a *consumer*.

### V5.5 What "sustained streaming" means — objective metrics

The term is made measurable here, before any run. Where the project has no
established threshold, the entry is marked **DESIGN DECISION REQUIRED (DDR)**
rather than given an invented number.

| metric | definition | threshold |
| --- | --- | --- |
| run duration | wall clock from the first unmask to the stop | **DDR** — must be justified against a real interval, as GBP-VIDEO-002's 120 s was justified against the Disc's own detector window. A duration chosen because it "feels long" is not a criterion. |
| complete frames | frames closed `COMPLETE_40` with no `F_ANOMALY` / `F_RESYNC` | counted, not thresholded |
| producer frame cadence | interval between consecutive frame-start boundaries | compared against 59.727 Hz (GBP-HW-078); a *deviation* is the finding, not a failure |
| VIDEO blocks per frame | histogram over the run | 40 expected; any other value is named |
| incomplete / resync frames | by the assembler's own classification | counted; **a non-zero count does not by itself fail the run** — it is data about a moving source |
| duplicate blocks | a block index arriving twice inside one frame interval | counted; expected 0 |
| source disagreements | R3 classes, unchanged | counted; fatal classes still fatal |
| service latency | READ→ACK, ACK→REARM, REARM→next cause | distribution per run, as `vstate-0004` already records |
| transport errors, timeouts, busy, uncertain writes | existing counters | **must be 0** — this is an invariant, not a metric |
| ring overruns | producer reused a slot a consumer was reading | **must be 0**, and the design detects it rather than assuming it (§V5.7) |
| consumer backlog | queue depth at each enqueue | max and histogram |
| frames dropped by the consumer | by policy, with the reason named | counted per reason; never silent |
| presented frames | frames actually put on screen | counted |
| restore correctness | the existing teardown checks | **must all pass** |

**The distinction that matters most:** *service* metrics decide PASS/FAIL,
*display* metrics describe behaviour. A dropped display frame is a policy outcome
and must never be confused with a lost VIDEO block.

### V5.6 Four cadences, and why they are not one

§V5 refuses to assume these are equal, because GBP-PHY-003 says they are not:

```text
A  GBP service clock      one IRQ per VIDEO/AUDIO block, at the AGB's own rate
B  assembled AGB frame    40 blocks -> one frame, measured 59.727 Hz (GBP-HW-078)
C  GameCube display       VI field rate, ~59.94 Hz NTSC
D  future writer/network  Phase 7+, entirely unconstrained
```

B and C differ by ≈ 0.213 Hz. That is **one repeated display frame roughly every
4.7 seconds**, about 26 in a 120 s run — an arithmetic consequence of two free
running clocks, predicted here *before* the run so that it can never be reported
as frame loss. GBP-PHY-003 records the same thing from the other side: the GBP
"does not do any fancy synchronization and just adds frames where it needs to".

Buffering is required exactly at the B→C boundary, and nowhere else in this
experiment. A→B is the assembler, which already exists.

### V5.7 Producer / consumer boundary

**The rule inherited from §V3.23, and the reason it exists.** The first colour
implementation did a 153 600-byte `memcmp` and `memcpy` between the ACK and the
RE-ARM; the microaudit refused it, and the fix — pass a *slot index*, never bytes
— is what made `color-0001` and `color-0002` possible. GBP-VIDEO-004 inherits
that rule unchanged.

**Forbidden in the service path**, without exception:

```text
GX anything          texture upload      DCFlushRange over a frame
filesystem / SD      networking / BBA    PAD reads
printf beyond the existing bounded ringlog
full-frame conversion, comparison or copy
any wait for presentation, VSync or a consumer
```

**The handoff is an integer.** When `gbp_vstate_block()` reports
`step.frame_closed && step.frame_complete`, the service writes one bounded record
— slot index, frame index, block count, flags, `t_first`, `t_last`, and a
**generation counter** — into a small lock-free ring, and returns to the RE-ARM.
It copies nothing and forms no pointer into the frame.

**PROPOSED DESIGN — the race is detected, not avoided by hope.** The consumer
reads the generation, converts the frame out of the ring slot, then reads the
generation again. If it changed, the producer reused the slot mid-conversion: the
converted frame is discarded and `consumer_slot_overrun` is incremented. This is
lock-free, costs the producer one store, and turns a silent tearing bug into a
counter. Four ring slots at 59.7 Hz give the consumer ~50 ms of margin, but the
design does not depend on that estimate being right — it measures it.

### V5.8 Buffering — the options, and the choice

| option | MEM1 | ownership | latency | consumer lag | effect on service | diagnosability |
| --- | --- | --- | --- | --- | --- | --- |
| double buffer | 2 × 76 800 | simple | 1 frame | stalls or tears | risk of coupling | poor: tearing is invisible |
| triple buffer | 3 × 76 800 | moderate | 1–2 frames | drops oldest | none | good |
| ring of assembled frames | N × 153 600 | moderate | N frames | drops oldest | none | good, but stores raw twice |
| **block ring + assembler + converted queue** | existing ring + N × 76 800 | producer owns the ring, consumer owns the queue | 1–2 frames | drops oldest | **none** | **best: every transition is a counter** |
| producer converts | — | — | — | — | **violates §V3.23** | — |

**PROPOSED DESIGN — the fourth.** The raw block ring already exists and is
already physically validated; adding a second raw ring would duplicate 153 600 B
per slot for nothing. The consumer converts once, into a queue of tiled textures,
which is also the only form the display can use.

**Queue depth: DESIGN DECISION REQUIRED.** Two is the minimum that lets the
display read one while the consumer writes another; three absorbs one late
conversion. Nothing in this repository measures conversion cost yet, so the
number is deferred to the first measurement rather than guessed.

### V5.9 Lost / missing block policy

**Service behaviour and display behaviour are different decisions and are kept
apart.** The hardware service is never delayed to rescue a picture.

The assembler already classifies every case; this design adds no new
classification, only a display consequence:

| assembler outcome | service | display |
| --- | --- | --- |
| `COMPLETE_40`, clean | continue | present |
| `INCOMPLETE_SHORT` (boundary early) | continue | **hold previous**, count `incomplete_short` |
| `INCOMPLETE_LONG` (>40, or 48 with no boundary) | continue | **hold previous**, count `incomplete_long` |
| `PREDICATE_ANOMALY` | continue | **hold previous**, count |
| `RESYNC` | continue, clock paused | **hold previous**, count |
| `F_MAJORITY_EXTRA` (quarantined) | continue | **never presented**, count — a quarantined frame may not become visual evidence any more than it may become colour evidence |
| `F_SOURCE_DEFERRED` | continue | descriptive only; does not change the decision |
| fatal disagreement class | **abort, teardown, restore** | run ends |

**Policy comparison, as §8 requires:**

| policy | verdict |
| --- | --- |
| `DROP_FRAME` (show nothing) | **rejected** — a black flash is indistinguishable from a device fault |
| `HOLD_PREVIOUS_FRAME` | **CHOSEN** — the display state is always a frame that really arrived, and the count of holds is the measurement |
| `PARTIAL_FRAME_WITH_DIAGNOSTIC` | **rejected for presentation** — it would require deciding what the missing blocks contain. **Never synthesise pixels.** The partial frame is still *recorded* for offline analysis; it is simply not displayed. |
| `RESYNC_ONLY` | insufficient alone — it says what the assembler does, not what the screen shows |

### V5.10 Colour conversion — where it lives, and how little it is

**The placement rule:** consumer only. Never the service path, never the ISR.

**The finding that makes this cheap.** GBP-HW-131 established that the device
already exchanges the outer 5-bit groups. The AGB writes BGR555 (R in bits 0–4);
the word delivered to the GameCube therefore has **R in bits 14–10**, which *is*
`GX_TF_RGB5A3` order with bit 15 = 1. So:

```text
texel = word16 | 0x8000        /* no channel arithmetic whatsoever */
```

This is exactly what both references do — the Disc ORs `FILL = 0x8000` into every
pixel and draws `GX_TF_RGB5A3` with no swap table (`VIDEO_PATH.md` §2.3). **The
only real work is the raster → 4×4-tile permutation**, 0xF00 raw bytes → 0x780
tiled bytes per block, 0x12C00 per frame, which is the same transformation
`FUN_8008EFB4` performs.

A `gbp_vpix` module is proposed for it — pure, hardware-free, host-testable
against synthetic frames and against the physical `color-0002` fixture, which
already carries eight known colours in known positions.

### V5.11 flag15 while U-GBP-034 is open

Conservative by construction:

- **preserved** in the raw block, which is never modified;
- **counted and reported** per frame — count and coordinates, exactly as
  `tools/vcolor2.py` does;
- **not consulted for presentation**: the texel ORs bit 15 on regardless, because
  RGB5A3 requires it for the opaque 5-5-5 interpretation, so masking it for
  display is arithmetically irrelevant and is never described as "discarding" it;
- **never allowed to alter service behaviour** — it does not gate, drop, delay or
  reclassify anything.

The frame-start *predicate* the assembler already uses is unchanged and is a
separate mechanism from the flag's unknown origin.

### V5.12 Output modes — the minimum that closes the item

The roadmap says "output modes" without enumerating them. Candidates, and the
scope decision:

| candidate | in scope? |
| --- | --- |
| A native 240×160 reconstruction presented on the GameCube | **YES — the minimum.** This is the "first rendered frames" the roadmap deferred to this step. |
| B GameCube framebuffer preview | same thing as A; not a separate mode |
| C scaled / aspect-corrected output | **NO — NON-BLOCKING UI POLICY**, Phase 9 |
| D network / BBA path | **NO** — Phase 11; only the interface shape is reserved (§V5.16) |
| E capture / debug output to SD | **PARTIAL** — the existing sidecar mechanism already preserves raw frames; no new output path |

**Minimum to declare GBP-VIDEO-004 complete: A.** One correctly converted,
correctly oriented 240×160 frame stream on screen, sustained, with the loss
policy of §V5.9 applied and every drop counted.

### V5.13 Audio

The service selects and drains AUDIO whenever the source bit is set, and a
selected source that is not drained is a fatal condition
(`gbp_vstate_diag_service_incomplete`). So the answer is forced by the validated
path, not chosen:

**A — keep draining AUDIO, do not play it, measure it.** Drain count, byte count
and completion are already recorded. No DAC, no mixer, no A/V sync. Phase 6 owns
playback.

### V5.14 Backpressure

**Never block the producer.** That is an invariant, not a preference: blocking the
service would delay the ACK or the RE-ARM and invalidate the one thing this
experiment is measuring.

**PROPOSED DESIGN: newest-complete-frame wins (drop-oldest), bounded queue.** A
frame the consumer never converted is counted as `dropped_before_convert`; a
converted frame the display never showed is `dropped_before_present`. Both are
reported per run with their maximum backlog, so "the consumer fell behind" is a
number and not an impression.

`drop-newest` is rejected: it would make the screen lag further behind the device
the busier the system got, which is the opposite of what a streaming path should
do.

### V5.15 Display path — grounded in this toolchain, not in preference

Verified inside `ghcr.io/extremscorner/libogc2:20260805`:

```text
/opt/devkitpro/libogc2/gamecube/include/ogc/gx.h      GX_TF_RGB5A3 = 0x5, GX_InitTexObj()
/opt/devkitpro/libogc2/gamecube/include/ogc/cache.h   DCFlushRange(), DCInvalidateRange()
/opt/devkitpro/libogc2/gamecube/include/ogc/video.h   VIDEO_Configure/SetNextFramebuffer/WaitVSync
```

| route | assessment |
| --- | --- |
| **GX texture, `GX_TF_RGB5A3`** | **RECOMMENDED.** The device's word *is* this format after the confirmed swap, so there is no per-pixel arithmetic — only the tile permutation. It is what the Start-up Disc does with the identical stream (`GX_InitTexObj(obj, fb, 240, 160, 5, …)`), so the approach is corroborated by a reference implementation rather than invented. Cost: GX must be initialised, which **no POC in this repository has ever done**. |
| direct XFB conversion | rejected: the GameCube XFB is YUV 4:2:2, so every pixel pair needs RGB→YUV arithmetic — strictly more work than the tile permutation, and no reference does it. |
| anything else in the repo/toolchain | none exists. |

**Known conflict to resolve at implementation time:** every existing probe calls
`CON_Init` on the XFB and prints its report there. A GX pipeline wants that
framebuffer. The POC must either keep the text report on a separate pass
(teardown-time, as today) or reserve a console region. **DESIGN DECISION
REQUIRED**, and it must not be solved by moving reporting into the service path.

### V5.16 Resolution, aspect, scaling

Minimum: **native 240×160, unscaled, centred.** Integer scaling, aspect handling
and filtering are **NON-BLOCKING UI POLICY** and belong to Phase 9. GBP-VIDEO-004
must not become a frontend; a run whose only defect is that the image is small is
a PASS.

### V5.17 Do the open unknowns block this?

| unknown | blocks GBP-VIDEO-004? | proof |
| --- | --- | --- |
| **U-GBP-029** (bytes 0/2) | **No.** The consumer reads bytes 1 and 3 only, which is what both references and the runtime signature already do. Bytes 0 and 2 never enter a texel. Their variation is orthogonal to every metric in §V5.5. |
| **U-GBP-033** (replica non-uniformity) | **No.** The policy that survives it is physically validated over 52 events across two long runs (GBP-HW-108…115, GBP-HW-119) and is reused unchanged. The mechanism does not have to be understood, only survived — which is the same standing under which GBP-VIDEO-003 was allowed to run. |
| **U-GBP-034** (bit 15's origin) | **No.** §V5.11 makes the bit inert for presentation: the texel sets it regardless, and it gates nothing. |

**None of the three blocks it.** If a streaming run produces new evidence for any
of them, that is recorded against the item and does not change this experiment's
verdict.

### V5.18 Physical matrix — the smallest sequence that can validate streaming

Three categories, kept strictly apart because they are different kinds of
evidence:

| category | what it is | what it can prove |
| --- | --- | --- |
| **CONTROLLED** | a stimulus this repository builds, delivered by the validated EZ-Flash Omega DE NOR / Mode B route | **ground truth.** With a frame index encoded in the image, the consumer knows exactly which AGB frames never arrived. This is the only category that can measure loss rather than infer it. |
| **REFERENCE** | an original commercial Game Pak | realism: a real workload with real timing. **No ground truth** — a repeated frame cannot be distinguished from a game that did not redraw. |
| **ALTERNATIVE** | any other ROM the operator owns on the flash cart | corroboration only; recorded with its identity |

**The smallest sequence: two runs.**

1. **CONTROLLED motion stimulus.** The decisive run. The design is the same idea
   that made `color-0002` decisive: a source whose truth is known by
   construction. **PROPOSED DESIGN — `stimulus/agb-motion`:** a Mode 3 image that
   changes every AGB frame and encodes its own frame number in a fixed pixel
   region, so the consumer can state exactly which frames arrived, in order, with
   no gaps unaccounted for. Continuous motion, no input, no peripheral, no
   sensor, boots to the pattern unattended — the properties §13 asks for, and all
   of them satisfiable by a ROM this repository builds and hashes.
2. **REFERENCE cartridge**, afterwards, as a realism check.

**This design deliberately does not name a commercial cartridge.** The repository
names none, the operator owns the choice, and a title written here would become a
requirement nobody agreed to. What it does record is the property list a suitable
one must have: continuous on-screen motion without input, no sensor or peripheral
dependency, reproducible from a cold boot.

### V5.19 Pacing instrumentation — bounded, and outside the ISR

**No megabytes of timing, and nothing written from the interrupt path.** The
existing discipline holds: preallocated ring, counters, bounded histograms.

Per completed frame, in the bounded record the producer already writes:
`t_first_block`, `t_last_block`, block count, flags, slot, generation. That is
enough to derive producer cadence offline without a single extra clock read in
the service path.

In the consumer, outside the critical path: convert-start and convert-end
timestamps, queue depth at enqueue and dequeue, present timestamp, and the drop
counters of §V5.14. **PROPOSED DESIGN:** fixed-bucket histograms rather than
per-frame arrays, so a long run costs constant memory.

### V5.20 The first POC, specified

```text
Test ID            GBP-VIDEO-004
Build ID           stream-0001                       (not yet allocated in any Makefile)
POC                poc/gbp-video-stream-probe/       (does not exist yet)
New source         src/gbp/gbp_vpix.{h,c}            raster -> RGB5A3 tile, pure, host-tested
                   src/gbp/gbp_vqueue.{h,c}          bounded frame queue + counters, pure
                   the display path stays in the POC, not in src/gbp
Reused unchanged   gbp_vstate_probe, gbp_vstate, gbp_vsig, gbp_avblock, gbp_irq_service,
                   gbp_initirqa, the R3 policy, the teardown
Input              CONTROLLED motion stimulus (run 1); REFERENCE cartridge (run 2)
Wait               the validated 5000 ms pre-handler wait, unchanged
Duration           DESIGN DECISION REQUIRED (§V5.5)
Buffers            existing raw ring + converted queue of depth DDR (§V5.8)
Instrumentation    §V5.19
Stop condition     duration reached, or a fatal service class, or a store cap
                   (each a distinct, named stop reason, as every probe already does)
Physical setup     GameCube + Game Boy Player DOL-017; EZ-Flash Omega DE NOR / Mode B;
                   Link Port EMPTY; BBA ABSENT; controller connected but untouched
                   during the run; SD2SP2 + Swiss; POWER CYCLE after the run
Swiss              a new number in the canonical range, not 11-color
```

### V5.21 PASS / INCONCLUSIVE / FAIL, pre-registered

```text
PASS
  every service invariant holds for the whole declared duration:
    transport errors = 0, timeouts = 0, busy = 0, uncertain writes = 0
    unmasks = deliveries = acks = rearms
    ring overruns = 0
    no fatal disagreement class
    teardown and restore all OK
  AND the consumer operated under the declared policy for the whole duration,
    with every non-presented frame accounted for by a named counter
  AND, for the CONTROLLED run, the arrived frame indices form an accounted
    sequence: every gap is explained by a counted loss, none unexplained

INCONCLUSIVE
  a store cap, buffer limit or instrumentation limit ended the run before the
  declared duration, or prevented a metric from being measured
  (an inconclusive run is a real outcome and is recorded as one)

FAIL
  any service invariant violated, or the frame-loss policy contradicted
  (for example a frame presented that the assembler did not close COMPLETE_40,
   or a quarantined frame reaching the screen)
```

**"Looks smooth" is not a criterion.** A visual observation may be recorded as an
auxiliary note, with a photograph if the operator wishes, and it is never the
gate.

### V5.22 Memory budget — real numbers from the current build

Measured on `build/poc/gbp-video-color-probe/gbp-video-color-probe.dol`
(`tools/dolinfo.py`, commit `39f1980`):

```text
text  0x052D80     339 328 B
data  0x019260     103 008 B
bss   0x762110   7 741 712 B     starting at 0x8006F0C8, ending at 0x807D11D8
                                 i.e. about 8.2 MiB of MEM1 (24 MiB) in use
```

Per-frame sizes, all exact:

```text
raw ring slot (48 blocks, the assembler's maximum)    184 320 B
one real 40-block frame on the wire                   153 600 B
converted GX RGB5A3 tiled frame (240 x 160 x 2)        76 800 B = 0x12C00
pixels per frame                                       38 400
```

GBP-VIDEO-004 can also *shrink* what the colour probe carried: the 16 384-entry
frame table (3.00 MiB) and the 4 × 4 episode raw store (2.81 MiB) exist for
GBP-VIDEO-002's change detector and are not needed by a streaming run. A
plausible budget — **to be confirmed at implementation, not claimed here** — is
the existing 4-slot ring (737 280 B) plus a converted queue of 3 (230 400 B) plus
a much smaller frame table, which lands well inside the ~16 MiB of MEM1 the
current build leaves free.

**Timing is NOT budgeted here.** The conversion is roughly 38 400 iterations of a
load/mask/or/store per frame and is memory-bound, but this repository has
measured nothing of the sort, and §18 forbids presenting an estimate as a
property. The first POC **measures** convert time and publishes the distribution;
until then the only safe statement is that the conversion is outside the service
path, where its cost cannot affect the device.

### V5.23 Timing-risk register

| risk | why it is plausible | mitigation designed in |
| --- | --- | --- |
| consumer slower than producer | conversion cost unmeasured | never blocks the producer; drop-oldest; counted (§V5.14) |
| producer reuses a slot mid-conversion | 4 slots, ~50 ms margin, but unmeasured | generation counter checked after conversion; counted as `consumer_slot_overrun` (§V5.7) |
| GX init perturbs the service path | GX has never run in this repository alongside the service | GX is initialised **before** the first unmask and touched only from the consumer; the probe records the same teardown checks as every previous run |
| VI VSync wait leaks into the service | easy mistake | no wait of any kind in the service path; the display runs on its own |
| the B↔C cadence beat is read as loss | ≈ 26 repeated display frames per 120 s | predicted here, before the run, with its arithmetic (§V5.6) |
| the text report competes with GX for the XFB | every existing probe uses `CON_Init` | DDR in §V5.15; must not be solved inside the service path |

### V5.24 The Phase 7 bridge

The roadmap calls this "the bridge to Phase 7" (cartridge compatibility). It is a
bridge in a precise sense: Phase 7 needs to run *arbitrary* cartridges and see
*correct* video, which requires exactly the abstractions this experiment forces
into existence:

```text
frame producer      the validated service + assembler, already physical
frame queue         bounded, drop-oldest, counted           <- new here
pixel conversion    raster -> RGB5A3 tile, pure and testable <- new here
consumer interface  "take the newest complete frame"         <- new here
backpressure metrics                                         <- new here
```

Phase 11's BBA path and Phase 9's presentation modes are *other consumers* of the
same queue. That is the whole reason to define the interface now — and the whole
reason **not** to implement either of them now.

### V5.25 Open questions this design does not answer

1. The run duration, and what justifies it (§V5.5) — **DDR**.
2. The converted-queue depth (§V5.8) — **DDR**, pending the first conversion-cost
   measurement.
3. How the text report and the GX pipeline share the framebuffer (§V5.15) —
   **DDR**.
4. Whether the motion stimulus's frame counter should be encoded in pixels the
   consumer reads, or in a region the offline analyser reads — affects whether the
   runtime can "recognise" its own stimulus, which §V3.11 warns against.
5. Whether a commercial reference cartridge is needed for Phase 4's acceptance or
   only for Phase 7 — the roadmap's acceptance sentence says "a real cartridge",
   and this design does not decide it unilaterally.

### V5.26 PRE-HARDWARE AUDIT of `stream-0001` — 2026-09-18 — **DECISION: B, SOFTWARE FIX REQUIRED BEFORE HARDWARE**

Audited at HEAD `22308c6` against the candidate built at `0816cbe`
(`gbp-video-stream-probe.dol`, 461 120 B, sha256 `0dc2c501…`, Swiss
`12-stream/boot.dol` byte-identical). No code was changed by this audit.

**One BLOCKER, three HIGH.** The candidate is not released for a physical run.

#### V5.26.1 The timeline, reconstructed from source rather than from the report

```text
unmask -> handler -> MASK IRQ 26 -> READ -> AUDIO -> VIDEO -> ACK -> PI clean
       -> signature + assembly -> [PUBLISH]  -> RE-ARM -> [PUMP slice] -> wait_next (busy poll)
```

Two facts the earlier report did not state, both load-bearing:

1. **The pump runs with IRQ 26 already masked.** `gbp_irq_service.c` step 7
   re-masks before the drain, so the GBP ISR **cannot** preempt the conversion.
   The §3 scenario of a handler firing mid-slice does not arise.
2. **`wait_next()` is a busy-poll on INTSR**, not an interrupt wait. A cause that
   arrives during the slice **latches** and is found by the next poll. Nothing is
   lost; detection is merely late.

Producer and consumer are therefore **the same thread**, sequentially. No memory
barrier, no `volatile` and no critical section is required for the queue. The only
asynchronous agent in the whole program is the GX draw-done callback, which
touches exactly one array — and that is where the blocker is.

#### V5.26.2 BLOCKER — the draw-done callback frees a buffer the GP still owns

`poc/gbp-video-stream-probe/source/main.c:195-200`

```c
static void on_draw_done(void)
{
    uint32_t i;
    for (i = 0; i < STREAM_TEX_BUFFERS; i++)
        if (tex_state[i] == TEX_SUBMITTED) tex_state[i] = TEX_FREE;
}
```

A DrawDone token certifies only the commands queued **before that token**. The
callback frees **every** submitted buffer. Simulating the real state machine:

```text
frame 1 -> buffer 0 SUBMITTED, token1 queued        state [S, F]  inflight [0]
frame 2 -> buffer 1 SUBMITTED, token2 queued        state [S, S]  inflight [0,1]
token1 fires -> the callback frees BOTH             state [F, F]  inflight [1]
frame 3 -> buffer 0   (genuinely free)              state [S, F]
frame 4 -> buffer 1   <-- the GP may still be reading it
```

The CPU refills a texture the GP still owns, which is precisely the collision the
implementation brief required to be impossible. Two aggravating properties:

- **It is invisible.** `no_free_buffer` does **not** increment in that sequence
  (the callback frees both before the next pump), so nothing in the log records
  it. The only symptom is a torn frame on screen — and §V5.21 explicitly refuses
  visual impression as a criterion.
- **The code has never run** (§V5.26.4).

The window requires token1 not to have fired within the ~6.6 ms the next frame's
40 slices take. The GP finishes one textured quad in microseconds, so it is
narrow — but `hsp_backend.c:62` holds `_CPU_ISR_Disable` across each ARAM DMA
(~61 µs per block read, GBP-HW-051), so GP interrupt delivery is deferred for a
substantial fraction of every cycle. Narrow is not absent, and the contract is
unsound regardless of the probability.

**Fix direction, NOT applied:** a per-submission token (`GX_SetDrawSync` /
`GX_GetDrawSync`), or a FIFO of submitted buffers so the callback frees only the
oldest, or refusing to submit while one frame is in flight.

#### V5.26.3 HIGH — the "164 µs of slack" justification is void

Measured from the 80 physical cycle records of `vstate-0004`:

```text
cause -> RE-ARM   (probe WORK)   min  76.6   median  78.3   max 2189.8 us
RE-ARM -> next    (real IDLE)    min   1.9   median  42.8   max  167.7 us
                                 p25   1.9   p75     88.6   p90  121.1 us
```

**34 % of cycles have an idle window of 1.9 µs** — the next cause is already
latched when the RE-ARM completes. The 164 µs quoted in the implementation round
is `capture_elapsed / deliveries`, i.e. the mean cycle **period** (work + idle),
not slack. A ~20 µs slice therefore exceeds the entire idle window on roughly a
third of cycles.

This is not by itself a defect: the cause latches and `wait_next` polls, so
nothing is lost. But the design's argument for the slice placement does not hold,
and whether the GBS-DOL tolerates late service is **UNKNOWN**. Classification of
the slice placement: **PLAUSIBLE BUT UNMEASURED**, not PROVEN SAFE.

#### V5.26.4 HIGH — the display path has never executed anywhere

The Dolphin smoke matched `OPENGBP-STREAM READY`, which is printed **before**
`gbp_vstate_probe_run()`. With no GBP model the probe aborts before any frame
closes, so `pump()` never runs. `GX_InitTexObj`, `GX_LoadTexObj`, `draw_quad`,
`GX_SetDrawDone`, `GX_CopyDisp` and `on_draw_done` have therefore **never been
executed** — not on hardware, not in Dolphin, not on the host. Only `GX_Init` and
`gx_setup()` are smoke-tested. The blocker of §V5.26.2 lives entirely inside that
unexecuted code.

#### V5.26.5 HIGH — the run cannot measure the perturbation it needs to measure

`GBP_VSTATE_CYC_FIRST = 8` and `GBP_VSTATE_CYC_LAST = 8`: sixteen per-cycle
timing records, both windows at the extremes, out of roughly 183 000 cycles in a
30 s run. The probe records aggregate slice min/max but **no** count of "a cause
was already pending while the slice ran" and no RE-ARM→next-cause distribution.

The question "did the consumer perturb the service?" is therefore answerable only
*indirectly*, through consequences already recorded: `frames_incomplete`, the
`INTERVALS` histogram, `timeouts`, and unmasks = deliveries = acks = rearms. That
is real evidence and it is the evidence that matters scientifically, but the
direct measurement the design promised is absent.

#### V5.26.6 MEDIUM and below

| id | severity | where | finding |
| --- | --- | --- | --- |
| F5 | MEDIUM | `main.c:324` | `if (!blk) { conv.next_row = GBP_VPIX_BLOCKS; break; } /* guard below rejects */` — the generation guard checks publish distance, not conversion completeness. If `gbp_vstate_ring_block()` ever returned NULL mid-frame, a half-converted texture would be committed and presented, mixing two generations. Unreachable in practice; the comment asserts a protection that does not exist. |
| F6 | MEDIUM | `main.c:268` | `GX_SetDrawDoneCallback()` is never uninstalled. After `main` returns the callback can still fire and write `tex_state[]`. Not a memory-safety fault (static BSS), but a dangling handler, and the teardown has never been exercised with GX active. |
| F7 | LOW | `main.c:307` | `no_free_buffer` cannot serve as evidence that the two-in-flight condition did not occur — see §V5.26.2. |
| F8 | LOW | `main.c:370` | `GX_CopyDisp(xfb_stream, …)` writes the framebuffer VI is scanning out. Tearing is expected and harmless, consistent with §V5.16, but it must never be read as frame loss. |
| F9 | INFO | `gbp_vqueue.c:33-38` | `gbp_vqueue_classify()` does not exclude `F_SOURCE_DEFERRED`, which `gbp_vcolor_eligible()` does. Design-sanctioned (§V5.9: "descriptive only"), so a frame refused as colour evidence may still be displayed. Stated here so it is a decision and not an oversight. |

#### V5.26.7 What the audit CLEARED

| item | verdict |
| --- | --- |
| RGB5A3 byte order (§12) | **CORRECT.** Decoding the physical `color-0002` frame through the real tile mapping gives bytes `80 00 / FC 00 / 83 E0 / 80 1F / FF FF / 84 00 / 80 20 / 80 01`, which GX reads as the eight measured colours with R in bits 14–10. Big-endian `uint16_t` stores are exactly what GX expects; no conversion is needed. |
| tile mapping (§13) | **CORRECT.** 240 % 4 = 0, 160 % 4 = 0, 60 × 40 tiles, 60 × 40 × 16 = 38 400 texels, 76 800 bytes, max index 38 399. Verified exhaustively: every pixel maps to a distinct texel and the texture is fully covered. |
| preemption / reentrancy (§4) | **NO DEFECT.** Producer and consumer are the same thread; the only asynchronous agent is the draw-done callback on a `volatile uint8_t` array, whose single-byte stores are atomic on PowerPC. |
| publication ordering (§9) | **NO BARRIER NEEDED**, for the same reason. `has_pending` is written last and read first, but the ordering is irrelevant within one thread. |
| R3 / eligibility (§10) | **PRESERVED.** The service order string is unchanged, both one-shot ISRs are byte-identical to the GBP-VIDEO-001 build, `poc_audit --profile stream` reports 0 findings, and the queue uses the assembler's flags rather than a copy. |
| cache coherency (§11) | **CORRECT ORDER.** `DCFlushRange(tex_buf[conv.buf], GBP_VPIX_TEX_BYTES)` is after the fill and the commit check and before `GX_InitTexObj`; 76 800 is a whole number of 32-byte lines, pinned by a static assertion. |
| instrumentation cost (§15) | **CHEAP.** `gbp_vpix.o` contains four `mulli` and **zero** `divw`; the /4 and %4 reduced to shifts. Two `gettick()` reads per slice, no printf, no filesystem, no GX in the service path. |
| memory (§18) | text 356 672 + data 104 192 + bss 2 742 204 = **3.05 MiB**, plus two XFBs of 614 400 from the arena = **4.23 MiB of 24**. No large stack arrays in `pump()` or `draw_quad()`. |

#### V5.26.8 Test quality — eight mutations, and the one that cannot be tested

| mutation | caught? |
| --- | --- |
| M1 remove the final generation check | CAUGHT (3 C) |
| M2 publish an incomplete frame | CAUGHT (6 C, 1 host) |
| M3 publish a quarantined frame | CAUGHT (5 C, 1 host) |
| M4 swap row/column inside a tile | CAUGHT (4 C) |
| M5 read byte 0 instead of byte 1 | CAUGHT (7 C) |
| M6 drop the presentation bit | CAUGHT (3 C) |
| M7 stop counting flag15 separately | CAUGHT (4 C) |
| M8 mailbox keeps the oldest, not the newest | CAUGHT (5 C) |

Every mutation of the two pure modules is caught. **The mutation that matters
most cannot be run at all**: `main.c` is target-only code with no behavioural
test, and the three host tests naming `on_draw_done`, `TEX_SUBMITTED` and
`TEX_FREE` assert only that those strings appear in the source. Breaking the
callback's logic is undetectable by the suite — which is exactly how the blocker
of §V5.26.2 got in.

#### V5.26.9 Decision

**B — CANDIDATE REQUIRES SOFTWARE FIX BEFORE HARDWARE.**

Required before a physical run:

1. **Fix the texture-ownership scheme** (§V5.26.2). This is the blocker.
2. **Make the two-in-flight condition observable** whatever the fix, so the log
   can show it did not occur.
3. **Add the perturbation counter** §V5.26.5 identifies — at minimum, a count of
   cycles in which a cause was already latched when the pump began, which is one
   `poll_intsr` read the pump already has the position for.
4. **Correct the §V5.26.6 F5 comment** and decide whether the abandon path should
   reject rather than commit.
5. **Restate the slice justification** from the measured idle window (§V5.26.3)
   instead of the mean cycle period, and re-classify it as PLAUSIBLE BUT
   UNMEASURED in the design.

Not required before a first run, but required before the experiment can close:
the CONTROLLED indexed motion stimulus of §V5.18 still does not exist, so a first
run can validate service, GX and operational pacing but **cannot** measure
source-frame loss against ground truth. A first smoke must never later be
described as evidence of zero dropped source frames.

### V5.27 `stream-0002` — the corrected candidate, 2026-09-18

**`stream-0001` is historical and stays REJECTED. Do not run it.** Its identity is
preserved unchanged: commit `0816cbe`, 461 120 B, sha256 `0dc2c501…`. Nothing in
this section re-labels it, and the build id was not reused.

#### V5.27.1 The blocker, fixed where it can be tested

The defect of §V5.26.2 was not "a careless callback". It was a state machine
living in `main.c`, which is target-only code with no behavioural test — the host
tests asserted only that the string `on_draw_done` appeared in the source. So the
fix moves the machine out:

```text
src/gbp/gbp_vpresent.{h,c}    ownership only. No GX, no VI, no libogc2.
                              Driven state by state by tests/unit/test_gbp_vstream.c
```

**The rule it enforces is the one that can be proved: AT MOST ONE DRAW-DONE TOKEN
IN FLIGHT.**

```text
FREE -> CPU_FILLING -> READY -> SUBMITTED -> (draw-done) -> FREE
```

- `gbp_vpresent_submit()` **refuses** while a token is pending, and counts
  `submit_blocked_inflight`. A READY buffer simply waits and is re-offered on the
  next slice boundary; the producer is never involved.
- `gbp_vpresent_draw_done()` releases **exactly one buffer, by index** — never
  "every SUBMITTED one". A callback arriving with nothing submitted releases
  nothing and increments `drawdone_spurious`.
- `gbp_vpresent_abandon()` and `gbp_vpresent_fill_done()` both **refuse** a
  SUBMITTED buffer, so the CPU cannot take back what the GP owns by any path.
- `gbp_vpresent_consistent()` states the invariant as code — at most one
  SUBMITTED, and `submitted` agreeing with `tex[]` — and the probe reports it.

Why one token rather than a queue of them: §V5.26.9 asked for the version that
can be proved. A token FIFO would also be correct and would need an argument
about ordering that this does not.

#### V5.27.2 Synchronisation, field by field

One asynchronous agent exists: the draw-done interrupt, which may call
`gbp_vpresent_draw_done()` and nothing else.

| field | writer(s) | reader(s) | width | rule |
| --- | --- | --- | --- | --- |
| `tex[i]` | main, callback | both | `volatile uint8_t`, aligned | single `stb`, atomic on PowerPC |
| `submitted` | main (set), callback (clear) | both | `volatile int`, aligned | single `stw`, atomic; main only sets it when it read −1, and nothing but main arms a token |
| every counter | its own side only | report, after the run | `uint32_t` | not shared across the boundary |
| `xfb_pending` | main | main | `int` | never touched by the callback |
| `conv`, `tex_buf[]` | main | main | — | the callback never reads them |

No barrier is required and none is used. The "concurrency" is one core and its
own interrupt handler, not two masters or a DMA engine; `sync`/`eieio` order
device traffic, which is not what is happening here. `volatile` is used for what
it is for — stopping the compiler from caching a value across the boundary — and
not as a stand-in for atomicity, which the widths already give.

The one ordering the caller must honour is stated on `gbp_vpresent_submit()`:
**mark first, arm second.** The buffer is SUBMITTED before `GX_SetDrawDone()` is
issued, so the callback can never observe a half-built submission.

#### V5.27.3 The framebuffer, which is a different question

`stream-0001` copied into the framebuffer the VI was scanning out (§V5.26 F8).
The earlier report said "two framebuffers", which was true and misleading: they
were the stream and the console, not a double buffer.

`stream-0002` keeps **three**: two for the stream, one for the console.
`gbp_vpresent_xfb_target()` answers "which may I copy into?" from two facts the
caller reads non-blockingly — `VIDEO_GetCurrentFramebuffer()` and the hand-over we
are still waiting on — and returns −1 when neither is safe, so the present is
**skipped and counted** (`xfb_skipped_busy`) rather than waited on.

No second asynchronous machine was added to do it: the retrace is *observed*
(`xfb_pending == current` retires the hand-over), never waited for.
`VIDEO_WaitVSync()` appears nowhere in the consumer path, and a host test asserts
that.

**Texture lifetime and framebuffer lifetime stay apart.** A DrawDone says the GP
finished reading the TEXTURE; it says nothing about the VI, and the module's two
halves share no state. A test drives a draw-done and an XFB hand-over against
each other to prove neither disturbs the other.

#### V5.27.4 The GBP comes first (§V5.26.3)

The claim `stream-0001` carried — "164 µs of slack" — was the mean cycle period
and is gone. The measured RE-ARM→next-cause window is median 42.8 µs with
**p25 = 1.9 µs**, so on about a third of cycles the next cause is already latched
when the RE-ARM completes.

The pump therefore **reads the cause first and does nothing when one is pending**:

```text
service loop, after the RE-ARM:
    poll INTSR  ->  pending?  ->  YES: pump_skipped_cause_pending++, return
                              ->  NO : one bounded slice, then poll again
```

It costs one extra `poll_intsr` per cycle. It does **not** remove the race of a
cause arriving *during* a slice — `cause_arrived_during_pump` counts that instead,
defined mechanically as "not pending before, pending after" and claiming nothing
about causality.

**The slice size is unchanged at one tile row and is still not a timing claim.**
It is a conservative bounded quantum; the position remains **PLAUSIBLE BUT
UNMEASURED** until the first physical run.

#### V5.27.5 What the first physical run will be able to measure

```text
STREAMPUMP   calls, slices started/completed, skipped_cause_pending,
             pending_before, pending_after, arrived_during
STREAMPUMPT  slice ticks min / max / mean / n, tile rows per slice
STREAMOWN    acquire attempts, no_cpu_texture, fills, abandons,
             submit success/attempts, blocked_inflight, blocked_shutdown
STREAMGX     drawdone callbacks, spurious, releases, xfb shown, xfb skipped,
             invariants consistent, in-flight at end, drained, callback restored
STREAMCONS   taken, converted, presented, overrun, superseded, repeats,
             no_cpu_texture, abandoned_no_raw, counters balance
```

Every one is a bounded increment or a min/max/sum; there is no per-slice log line
and no per-frame array. `no_free_buffer` is renamed `acquire_no_free_texture` and
documented as a throughput fact — §V5.26 F7 showed the old name being read as a
GPU-safety guarantee it never was.

#### V5.27.6 Teardown, in the one order that is safe

```text
gbp_vstate_probe_run() returns  — the Game Boy Player is already restored
  1. gbp_vpresent_shutdown()    no new fill, no new submit
  2. cfg.stream = 0, vq.pump = 0   no publish and no slice can be reached
  3. if still in flight: GX_DrawDone()   BLOCKING, and only here
  4. GX_SetDrawDoneCallback(previous)    nothing can call into us afterwards
  5. only now are the buffers dead
```

`GX_DrawDone()` appears **exactly once** in the program and a host test asserts it
is after `gbp_vstate_probe_run()` — it would have been forbidden anywhere in the
service path. The previous callback is captured at install and restored at
teardown, rather than assuming this program owns the hook for ever.

#### V5.27.7 The display path is no longer dead code (§V5.26.4)

`display_selftest()` walks the identical path once, before the probe, from a
**synthetic** frame built from pixel coordinates — it holds no stimulus value, so
it cannot teach the runtime what the experiment looks for (§V3.11). It runs
unconditionally, because a path exercised only when someone remembers is the path
that rots, and it costs one frame before the capture opens.

Dolphin now *asserts* it, instead of matching a line printed before anything
happened:

```text
OPENGBP-STREAM SELFTEST ok=1 converted=1 released=1 submits=1 drawdone=1 releases=1 xfb=1
```

So under Dolphin the conversion, the flush, `GX_InitTexObj`, `GX_LoadTexObj`, the
quad, `GX_SetDrawDone`, `GX_CopyDisp`, the **draw-done callback** and the release
all execute. That is auxiliary evidence about the code, and nothing about GBP
timing, pacing or the device (§V5.26, §27).

#### V5.27.8 Unchanged on purpose

- **R3 and the service order.** Both one-shot ISRs stay byte-identical to the
  physically validated GBP-VIDEO-001 build, and `poc_audit --profile stream`
  reports 0 findings.
- **`F_SOURCE_DEFERRED`** is still not excluded by `gbp_vqueue_classify()`.
  §V5.9's table says "descriptive only; does not change the decision", so the
  implementation and the contract agree and neither was changed (§V5.26 F9).
- **RGB5A3 and the tile mapping.** The audit cleared both against the physical
  `color-0002` frame; `texel = word | 0x8000`, no byteswap, and the eight-value
  test is kept.
- **The generation guard**, now exercised together with the new ownership machine.

The one correction §V5.26 F5 asked for is made: the `!blk` path used to mark the
frame complete and claim "the guard below rejects", which was false. It now
abandons the buffer, ends the conversion and counts `abandoned_no_raw`.

#### V5.27.9 Adversarial mutations, and the one that exposed a gap in the tests

Each mutation was applied, the suite run, and the source restored. The harness
was corrected mid-round: the first version used `git checkout` to revert, which
cannot revert an untracked file and silently reverts a legitimately modified one,
so three results were invalid (the build was broken and no test ran). Those were
re-run with a file-backup harness that also refuses to report a result when the
build fails.

| mutation | caught by |
| --- | --- |
| A1 callback frees every SUBMITTED buffer | **initially NOT caught**; caught (2 C) after the white-box test was added |
| A2 allow two draw-done tokens in flight | 1342 C checks |
| A3 let the CPU re-acquire a SUBMITTED texture | 16 C checks |
| A4 remove the final generation check | 3 C checks |
| A5 flush after marking the buffer READY | host ordering guard (1) |
| A8 byteswap the RGB5A3 texel | 4 C checks |
| A9 leave the draw-done callback installed after teardown | **initially NOT caught**; caught (host) after the teardown guard was added |
| A10 run the slice with a cause already latched | 18 C checks |

**A second harness defect, found by distrusting a result that looked too good.**
A9 first reported "CAUGHT (4 C failures)", which made no sense — it edits the
teardown, not anything a C unit test compiles. The four failures were A8's,
left over from a **stale build**: `tests/unit/Makefile` listed only `.c` files as
prerequisites, so mutating a *header* left the previous binary in place and the
next mutation inherited its failures. Re-run with a forced clean build, A9 was
**NOT caught** — nothing asserted that the draw-done callback is restored at all.

Both halves are fixed. `tests/unit/Makefile` now takes every shared header as a
prerequisite, so a header edit can never again be credited to the mutation after
it; and a host guard now asserts the teardown ORDER — probe returns, shutdown,
drain, restore — rather than the mere presence of the call. With those in place
A9 is caught and A5's genuine catch (the host ordering guard, not the residual C
failures) is confirmed on a clean build.

**A1 is the interesting one: it was NOT caught by the behavioural suite as it
stood.** With
the one-token rule in force, two buffers can never both be SUBMITTED through any
legitimate call sequence, so the "free every SUBMITTED buffer" loop never has a
second victim — the defect is **neutralised by the architecture rather than
detected by a test**.

That is defence working, and it is also one rule carrying everything: relax the
one-token rule later and the callback becomes dangerous again with nothing to say
so. `test_the_callback_releases_only_the_indexed_buffer()` now builds the
two-SUBMITTED state by hand — which no legitimate sequence can produce, and which
`gbp_vpresent_consistent()` correctly rejects — and requires the callback to
release exactly the buffer `submitted` names, in both index directions. With that
test in place the same mutation is **CAUGHT**, which is how the gap was confirmed
closed rather than assumed closed.

**What this says about the earlier round.** `stream-0001`'s defect was invisible
for exactly the same reason in reverse: nothing asserted the callback's contract,
only that its name appeared in the source. The lesson is not "write more tests";
it is that a contract enforced by an invariant somewhere else still needs its own
test, or the invariant becomes load-bearing without anyone knowing.

### V5.28 PRE-HARDWARE RE-AUDIT of `stream-0002` — 2026-09-18 — **DECISION: A, STREAM-0002 SAFE ENOUGH FOR FIRST SUPERVISED PHYSICAL SMOKE**

The third audit of this experiment, and the first one whose subject is a
candidate that a previous audit already rejected and a fix already repaired. Its
question was narrow and was set before any evidence was gathered: **is the exact
`stream-0002` artifact safe enough, and observable enough, for ONE supervised
physical smoke?** Not "is it correct", not "is streaming validated" — those are
§V5.21's job, offline, after a run exists.

Scope was limited to six areas: texture ownership and the one-token rule;
main ↔ callback synchronisation; XFB ownership; pump priority and observability;
the teardown callback lifecycle; and the validity of the display self-test.
RGB5A3, the tile mapping, R3, the colour mapping and the memory design were NOT
re-audited: `stream-0002` did not touch them and re-opening a settled decision
without new evidence is how an audit becomes a preference.

**No functional source was changed in this round, and none may be changed before
the run.** One finding (R1) would benefit from a functional correction; it is a
REPORTING defect, it is reported rather than fixed, and its correction is
pre-registered in §V5.28.10 and §V5.28.14 instead. The audited artifact is the
artifact that runs: **no rebuild, and no change under `src/`, `poc/` or `tools/`,
is permitted before the first physical smoke.**

**The answer to the question asked is YES.** The classification is **A**.

#### V5.28.1 The artifact, and that it is the one that was audited

```text
DOL          build/poc/gbp-video-stream-probe/gbp-video-stream-probe.dol
size         466 272 B
sha256       76fa1ff797a05aee37d50fe2b2ae1c7c7ffb2d57fb97166a1322a9c54f24831d
build id     stream-0002
commit       2457d51          (no -dirty)
swiss        build/swiss/12-stream/boot.dol — byte-identical
```

`git diff --name-only 2457d51..HEAD -- src/ poc/ tools/ tests/` is **empty**; the
only commit after the candidate touches `docs/HANDOFF.md`. The candidate's
identity therefore still holds at HEAD.

**Reproducibility (§V5.28 method note).** A detached worktree at `2457d51`, built
in the project container without touching the candidate tree, produced a
**byte-identical** DOL: 466 272 B, sha256 `76fa1ff7…`. The first attempt did not,
and the reason is worth recording because it will recur: inside the container a
`git worktree` cannot resolve `HEAD`, because its `.git` file points at a host
absolute path that does not exist in the container, so the Makefile's
`GIT_COMMIT`/`GIT_DIRTY` shell-outs fell back to `unknown` + `-dirty` and the
embedded identity string changed. With `GIT_COMMIT=2457d51 GIT_DIRTY=` the build
reproduces exactly. **The build is deterministic; the identity string is an
input to it.**

#### V5.28.2 Ownership — every transition, with its guard

| # | transition | code | guard | actor |
| --- | --- | --- | --- | --- |
| T1 | `—` → `CPU_FILLING` | `gbp_vpresent.c:37` | `!shutting_down` (`:34`), `tex[i]==FREE` (`:36`) | main |
| T2 | `CPU_FILLING` → `READY` | `gbp_vpresent.c:52` | `tex[idx]==CPU_FILLING` (`:51`) | main, **after** `DCFlushRange` (`main.c:388`, `:489`) |
| T3 | `CPU_FILLING` → `FREE` | `gbp_vpresent.c:64` | `tex[idx]!=SUBMITTED` (`:63`) | main (`main.c:384`, `:424`, `:446`, `:474`) |
| T4 | `READY` → `SUBMITTED` | `gbp_vpresent.c:81` | `!shutting_down` (`:73`), `tex[idx]==READY` (`:74`), `submitted<0` (`:78`) | main (`main.c:506`) |
| T5 | `submitted := idx` | `gbp_vpresent.c:82` | same call, one instruction after T4 | main |
| T6 | token armed | `main.c:516` `GX_SetDrawDone()` | reached only when T4/T5 returned 1 | main |
| T7 | `submitted := -1` | `gbp_vpresent.c:99` | `submitted>=0` (`:93`), else `drawdone_spurious` | **PE FINISH ISR** |
| T8 | `SUBMITTED` → `FREE` | `gbp_vpresent.c:100` | the **one** index read from `submitted` | **PE FINISH ISR** |
| T9 | XFB candidate chosen | `gbp_vpresent.c:111-115` | `i != current` **and** `i != xfb_pending` | main |
| T10 | `xfb_pending := idx` | `gbp_vpresent.c:124` | after `VIDEO_SetNextFramebuffer` + `VIDEO_Flush` (`main.c:524-525`) | main |
| T11 | `xfb_pending := -1` | `gbp_vpresent.c:134` | `xfb_pending == current` | main |
| T12 | `shutting_down := 1` | `gbp_vpresent.c:21` | — | main (`main.c:668`) |

The interrupt writes exactly two locations, T7 and T8, and T8's index comes from
T7's read. Everything else is main-side. That disjointness is the whole safety
argument, and it is machine-checked below rather than asserted.

#### V5.28.3 Exhaustive state enumeration — machine-checked, not argued

A breadth-first enumeration of a **superset** of the program was run: main may
begin any entry point with any index at any moment it is not already inside one,
and the draw-done interrupt may fire between **any two shared-memory accesses**
of any main-side function — including, adversarially, when no token is armed at
all. Every guard was transcribed from `gbp_vpresent.c` line by line.

```text
reachable states                        705
max simultaneously SUBMITTED buffers      1
P1  at most one tex[] entry SUBMITTED             HOLDS
P2  `submitted` agrees with tex[]                 HOLDS (outside the deliberate
                                                  :81→:82 transient)
P3  no MAIN-side write ever targets a SUBMITTED   HOLDS
```

The checker is not vacuous: injecting `stream-0001`-class defects into the
**model** breaks it exactly where it should. Removing the one-token guard makes
`max simultaneously SUBMITTED = 2` reachable in 54 states; letting `acquire()`
take a `SUBMITTED` buffer produces 393 P2/P3 violations, the first of them
`('P3', 'acquire:37', [SUBMITTED, FREE])`.

#### V5.28.4 Compiler ordering — PROVEN from the disassembly, not from "single core"

The question §8 asked is real and is **not** answered by "PowerPC is single-core":
single-core settles CPU atomicity and preemption, not whether the compiler may
sink the `SUBMITTED` marking past `GX_SetDrawDone()`.

Three independent facts, all read out of the shipped objects:

1. **No LTO.** `poc/gbp-video-stream-probe/Makefile:59` is `-std=gnu11 -g -O2
   -Wall -Wextra -Wshadow`. `gbp_vpresent_submit` lives in its own translation
   unit, so from `main.o` it is an opaque external call — a hard compiler barrier
   for anything it might touch.
2. **The stores retire before the return.** `powerpc-eabi-objdump -d` of the
   linked ELF, `gbp_vpresent_submit` at `0x8000e5cc`:

   ```text
   8000e614:  li    r10,3          ; SUBMITTED
   8000e618:  li    r3,1           ; the return value
   8000e61c:  stbx  r10,r9,r4      ; tex[idx] = SUBMITTED     <- volatile store 1
   8000e620:  stw   r4,4(r9)       ; submitted  = idx         <- volatile store 2
   8000e624:  lwz   r10,40(r9)     ; submit_success++
   8000e62c:  stw   r10,40(r9)
   8000e630:  blr
   ```

   Both volatile stores precede `blr`, in the source order ("mark first, arm
   second"), and the compiler emitted them as single naturally-aligned stores.
3. **The arming is strictly after the return, through a data dependency on the
   return value.** At the `main`/self-test site:

   ```text
   800039dc:  bl    8000e5cc <gbp_vpresent_submit>
   800039e0:  cmpwi r3,0
   800039e4:  bne   80004544            ; only when it returned non-zero
   ...
   80004544:  mr    r3,r24
   80004548:  bl    80004794 <submit_ready.part.0>   ; which arms at 80004908
   ```

   and at the `pump` site, `80004c2c bl gbp_vpresent_submit` / `80004c34 beq` /
   tail-call to `submit_ready.part.0`. `GX_SetDrawDone()` is at `0x80004908`,
   inside `.part.0`, i.e. unreachable except through a return of 1.

**Classification: PROVEN.** Not "plausible", not "by convention": the ordering is
visible in the shipped instruction stream and is enforced by a control dependency
the compiler cannot break.

#### V5.28.5 libogc2 semantics, revalidated against the real source

Consulted: `external/libogc2` at commit `ca03fb7534a9b67d3348ef76e3a3b379aee9392a`
(2026-09-12), `libogc/gx.c` and `libogc/video.c`. This matches the toolchain the
candidate links against (`libogc2 r2442.094b250`).

```text
GX_SetDrawDone()          gx.c:1606  IRQs off, GX_LOAD_BP_REG(0x45000002),
                                     GX_Flush(), _gxfinished = 0, return.
                                     NON-BLOCKING.                        CONFIRMED
GX_DrawDone()             gx.c:1629  the same, then LWP_ThreadSleep until
                                     _gxfinished. BLOCKING.               CONFIRMED
GX_SetDrawDoneCallback()  gx.c:1645  IRQs off, swaps drawDoneCB, RETURNS
                                     THE PREVIOUS ONE.                    CONFIRMED
the callback runs from    gx.c:450   __GXFinishInterruptHandler, i.e. the
                                     PE FINISH interrupt, in IRQ context.
IRQ_PI_PEFINISH           gx.c:470   IRQ_Request + __UnmaskIrq, _peReg[5]=0x0F.
                                     It is genuinely enabled.             CONFIRMED
VIDEO_SetNextFramebuffer  video.c:3337 HorVer.bufAddr = fb, shadow regs only.
                                     Touches NO VI register.              CONFIRMED
VIDEO_Flush()             video.c:3361 copies regs -> shdw_regs, flushFlag = 1,
                                     nextFb = HorVer.bufAddr. Still no VI
                                     register write, no wait.             CONFIRMED
the VI register write     video.c:3042 __VIRetraceHandler: if (flushFlag)
                                     __VISetRegs()
__VISetRegs()             video.c:2922 writes _viReg[] and THEN currentFb = nextFb
VIDEO_GetCurrentFramebuffer video.c:3072 returns currentFb
```

The last three lines are the ones that matter, and they say something stronger
than the design assumed: **`currentFb` changes at the same instant the VI
registers are written**, inside the retrace handler. So `VIDEO_GetCurrentFramebuffer()`
is not an approximation of "what the VI is scanning" — it is exactly the buffer
whose address the VI registers now hold.

One consequence must be written down because the teardown depends on it:
`drawDoneCB` is called on **every** PE FINISH, with no association to a
particular token, and `GX_DrawDone()` arms one of its own. §V5.28.9 works that
through.

#### V5.28.6 Five preemption timelines

| | timeline | reachable? | effect |
| --- | --- | --- | --- |
| **A** | callback fires between `submit()` returning 1 and `GX_SetDrawDone()` | **NO** | `submit()` returned 1 only because it read `submitted < 0` at `:78`. `submitted < 0` means the previous token has already been consumed, and the one-token rule forbids a second, so no unconsumed draw-done token exists in the FIFO and PE FINISH cannot assert. Modelled adversarially anyway in §V5.28.3: no state corruption even then. |
| **B** | callback fires between `GX_SetDrawDone()` and `GX_CopyDisp()` | **YES**, routinely | `draw_done` frees the texture and clears `submitted`. Nothing below that line in `submit_ready()` touches `tex[]`; the freed buffer may legitimately be re-acquired, because the token certified the GP finished reading it. **SAFE.** |
| **C** | callback fires inside `submit()`, between `:81` and `:82` | **NO** (same argument as A) | modelled: `submitted` is still `-1`, so `draw_done` counts `drawdone_spurious` and frees **nothing**; `:82` repairs the transient one instruction later. `gbp_vpresent_consistent()` is never called from the ISR, so the transient is unobservable. **SAFE.** |
| **D** | callback fires inside `gbp_vpix_block()` | **YES**, routinely | the ISR touches only `tex[submitted]` and `submitted`; the conversion writes only the pixels of a buffer in `CPU_FILLING`. Disjoint by P3. **SAFE.** |
| **E** | callback fires inside the GBP service path, between the ACK and the RE-ARM | **YES** | see below — the one timeline that is a real new risk. |

**Timeline E, stated honestly.** IRQ 26 (PI HSP) is masked for the whole probe
loop, which busy-polls INTSR (`gbp_vstate_probe.c:719`, `:1467`) — so the GBP
handler cannot preempt anything. But `IRQ_PI_PEFINISH` is unmasked by
`__GX_PEInit` and is never masked by this program, so the draw-done callback
**can** preempt the service path, including the ACK → RE-ARM window.

What that costs is bounded and visible: `on_draw_done` is a tail-call to
`gbp_vpresent_draw_done`, which the disassembly shows as ≤ 16 instructions, no
loop, no allocation, no device access, plus libogc's IRQ dispatch. It can happen
at most once per submitted frame — about 60/s against roughly 1000 service cycles
per second, so on the order of 6 % of cycles.

**This is a new interrupt source that `vstate-0004` did not have, and it is the
single thing the first physical run must be read for.** It is measurable after
the fact: the per-cycle records already carry `t_cause`, `t_ack` and `t_rearm`,
so a preempted cycle appears as an outlier in the existing histogram. Recorded as
finding **R3**; it is not a blocker, and it must not be described as "proved
harmless" until that histogram has been looked at.

#### V5.28.7 XFB ownership, against the VI semantics just established

The rule in `gbp_vpresent_xfb_target()` is: a buffer is unsafe if the VI is
scanning it (`current`), and unsafe if we handed it over and the VI has not yet
picked it up (`xfb_pending`). With the real semantics of §V5.28.5 those two
conditions are exactly `currentFb` and `nextFb`, which is the complete set of
buffers the VI may read. Nothing else in the program writes `nextFb` while the
capture runs — the only other `VIDEO_SetNextFramebuffer` calls are in
`video_setup()` and in the teardown, neither concurrent with the pump — so
`currentFb` can only ever become a buffer this code deliberately handed over.

The skip path (§11) is `-1` → `GX_Flush()` → `gbp_vqueue_note_repeat()`, a tail
call, with no loop and no `VIDEO_WaitVSync` anywhere in `submit_ready.part.0`
(`0x800049b0`..`0x800049e4`). Nothing can get stuck: `xfb_pending` is retired by
the next `xfb_target()` call, which observes `current` first, and the retrace that
retires it is at most one field away.

One residue is real and is recorded as **R5**: `GX_CopyDisp()` is queued and
`VIDEO_SetNextFramebuffer()` + `VIDEO_Flush()` follow immediately, without
waiting for the copy to complete. A retrace landing inside the copy window would
show one torn field. It is cosmetic, it is bounded to a single field, and §V5.21
already refuses "looks smooth" as a criterion — but it should not be described as
impossible.

#### V5.28.8 Cache ordering — also read out of the machine code

```text
80004c08:  bl   8002b178 <DCFlushRange>      ; r4 = 0x12C00 = 76 800 = exactly the buffer
80004c0c:  lbz  r4,36(r31)                   ; conv.buf
80004c14:  bl   8000e54c <gbp_vpresent_fill_done>
80004c2c:  bl   8000e5cc <gbp_vpresent_submit>
80004c34:  beq  ... else tail-call submit_ready.part.0 -> GX_SetDrawDone
```

The flush precedes the ownership hand-over and the token, in the shipped
instruction stream. Both are external calls, so the compiler could not have sunk
the flush past them, and it did not. The size is exact: `GBP_VPIX_TEX_BYTES %
32 == 0` is statically asserted (`main.c:184`), so the flush never touches memory
the buffer does not own.

#### V5.28.9 Teardown — the declared order, confirmed in machine code

```text
80003d90:  bl   gbp_vstate_probe_run     ; returns only after the GBP teardown + restore
80003d98:  bl   gbp_vpresent_shutdown    ; 1. no new fills, no new submissions
80003da4:  stw  r9(=0),344(r29)          ;    cfg.stream = 0
80003da8:  stw  r9(=0),4(r31)            ;    vq.pump    = 0
80003dac:  bl   gbp_vpresent_inflight
80003db4:  bne  80004534 -> bl GX_DrawDone ; 2. drain, BLOCKING, only now
80003dc0:  lwz  r3,-8480(r9)             ;    gx_prev_drawdone_cb
80003dc4:  bl   GX_SetDrawDoneCallback   ; 3. restore
80003dd4:  bl   VIDEO_SetNextFramebuffer ;    back to the console
```

The one subtlety §V5.28.5 forced into the open: `GX_DrawDone()` arms a **second**
token, and `_gxfinished` is satisfied by the **first** PE FINISH to arrive, which
may be the older one. So the second token can fire after `drawDoneCB` has been
restored. Both outcomes are safe and are counted: if the callback is still
installed, `gbp_vpresent_draw_done()` finds `submitted == -1` and increments
`drawdone_spurious` without freeing anything; if it has been restored,
`gx_prev_drawdone_cb` is `NULL` (nothing in libogc2 installs one) and the
interrupt does nothing. `drawdone_spurious` in the report is exactly the
observable that will say which happened.

`test_shutdown_stops_new_work_but_not_the_gp()` and
`test_a_spurious_callback_frees_nothing()` cover both, and the A9 mutation —
leaving the callback installed — is caught by the host guard that asserts the
probe → shutdown → drain → restore order.

Finding **R4 (LOW)**: that `GX_DrawDone()` is an **unbounded** wait, which
`CLAUDE.md` §18 forbids as a general rule. It runs after the Game Boy Player has
been restored, so the device is not at risk and the worst case is a hang at the
report stage with the operator present — but it is a rule this build does not
satisfy, and it is cheaper to bound it than to argue about it.

#### V5.28.10 The display self-test — and the one finding that needs a fix

The self-test does execute, and it executes the real path. Confirmed twice on the
exact candidate binary, once from the stored report and once by re-running the
Dolphin smoke in this round:

```text
OPENGBP-STREAM SELFTEST ok=1 converted=1 released=1 submits=1 drawdone=1 releases=1 xfb=1
```

`drawdone=1` is not self-reported bookkeeping. `on_draw_done` appears exactly
once in the whole linked disassembly — as its own symbol at `0x80004788`. There is
no `bl on_draw_done` and no branch to that address anywhere in the image; the
only materialisation of its address is `80003700 lis r3,-32768 / addi r3,r3,18312
/ bl GX_SetDrawDoneCallback`, i.e. `main.c:319`. **The callback can only have been
invoked by libogc2's PE FINISH handler.**

##### R1 — HIGH — the self-test permanently falsifies `gbp_vqueue_balanced()`

`display_selftest()` (`main.c:585`, before anything else) calls `submit_ready()`,
whose success path calls `gbp_vqueue_note_presented()` (`main.c:527`). That
increments `vq.consumer_frames_presented` for a **synthetic** frame that never
passed through `gbp_vqueue_take()` or `gbp_vqueue_commit()`, so
`consumer_frames_converted` is **not** incremented.

`gbp_vqueue_balanced()` (`gbp_vqueue.c:197`) asserts

```text
consumer_frames_converted == consumer_frames_presented + consumer_slot_overrun
```

which is therefore false from the first instruction of every run and stays false,
off by exactly one, for every subsequent frame. A host diagnostic reproducing the
exact call sequence gives:

```text
after self-test:     converted=0 presented=1 overrun=0   balanced=0
after 1 real frame:  converted=1 presented=2 overrun=0   balanced=0
```

and the candidate binary itself, under Dolphin with no Game Boy Player attached,
already prints on screen:

```text
CONSUMER taken=0 converted=0 presented=1  overrun=0 superseded=0 repeats=0  counters DO NOT BALANCE
```

**Consequence.** §V5.21's PASS clause "the consumer operated under the declared
policy … with every non-presented frame accounted for by a named counter" is the
clause `balanced` exists to answer, and the run's own indicator will read
`DO NOT BALANCE` on a perfectly good run.

**Its class, stated once and for all: R1 is a REPORTING defect, not a service
defect and not an ownership defect.** Nothing is corrupted, no ownership
invariant is touched, no hardware is at risk, and the device cannot observe it.
It is fully contained in one derived predicate: the raw counters the predicate is
computed from are all printed individually and are all correct. `converted`,
`presented`, `overrun`, `taken`, `published`, `dropped_before_convert` and every
other counter **remain authoritative**.

**The correction is NOT applied in this round** (the round forbids functional
changes). The smallest fix is that the self-test must not write into the queue's
consumer domain: either `submit_ready()` gains a "this frame did not come from
the queue" parameter, or the self-test performs its own present. A second option —
snapshotting `vq` after the self-test and reporting deltas — is larger and worse,
because it hides the crossing instead of removing it.

**Why it does not change the classification.** The offset is exactly `+1`, it is deterministic, it
is provable before the run, the affected counter is the only one the self-test
touches (every other `vq` counter is still `0` after it, verified), and the run
itself prints which correction applies: the `SELFTEST … xfb=` field is `1` when
the self-test took the presenting path and `0` when it took the repeat path. So
the identity can be pre-registered now, before the run, rather than rationalised
afterwards — which is the only form in which a correction like this is
acceptable:

```text
PRE-REGISTERED, BEFORE THE RUN:
  stream-0002 will print `counters DO NOT BALANCE`. That is expected and is NOT
  a FAIL. The identity to evaluate is

      consumer_frames_converted == (consumer_frames_presented - SELFTEST.xfb)
                                 + consumer_slot_overrun

  Every other clause of §V5.21 is evaluated unchanged. If the corrected identity
  does not hold, THAT is a FAIL.
```

##### Residual state after the self-test

`present` returns to all-`FREE` with `submitted == -1` (`selftest_released=1`,
`gbp_vpresent_consistent()` asserted in `selftest_ok`). `xfb_pending` is left at
the buffer the self-test handed over; it is retired by the first `xfb_target()`
of the run, one comparison, no wait. The `present.*` counters carry the
self-test's `+1` too, but consistently on both sides of every identity a reader
would form (`submit_success == texture_releases`,
`drawdone_callbacks == texture_releases + drawdone_spurious`), so only the queue
identity of R1 is affected.

#### V5.28.11 Observability and counter domains

The three domains — what the DEVICE did (`STREAMSRC`), what WE did to its frames
(`STREAMCONS`), what the SCREEN did (`STREAMGX`, `STREAMOWN`) — are correctly
separated in the report, with one leak, which is R1: the self-test writes into
the consumer domain.

**R2 — MEDIUM — two counters that can never differ.** In
`gbp_vstate_probe.c:1455-1463`, `cause_pending_after_pump` and
`cause_arrived_during_pump` are incremented under the *same* condition and are
therefore numerically identical by construction. The report prints both, side by
side, inviting a comparison that has no content. Worse, the first name
over-promises: the post-pump poll only happens when a cause was **not** pending
before, so `cause_pending_after_pump` is not "cycles with a cause pending after
the pump" — it is exactly `cause_arrived_during_pump`. The printed label "arrived
DURING a slice" is also loose: the counter also covers pump calls that started no
slice at all (`pump_slices_started` distinguishes those). Observability and
labelling only; no behaviour depends on it.

What the run **would** show if the ownership machine failed: `consistent=0`,
`inflight_at_end=1`, `drawdone_spurious > 0`, and `acquire_no_free_texture`
climbing. What it does **not** show directly is timeline E; that has to be read
out of the cycle histogram.

#### V5.28.12 Mutations — seven, re-run, all caught

Backup-based harness; **no `git checkout` was used on any file**, tracked or not.
Every file is restored from a byte copy and the restoration is verified by sha256
before the next mutation.

| | mutation | C unit | host guard | verdict |
| --- | --- | --- | --- | --- |
| A1 | `draw_done()` frees **every** `SUBMITTED` buffer — the exact `stream-0001` defect | 2 | 0 | **CAUGHT** |
| A2 | allow two tokens in flight | 2008 | 0 | **CAUGHT** |
| A3 | `acquire()` reuses a `SUBMITTED` texture | 680 | 0 | **CAUGHT** |
| A4 | remove the generation check | 3 | 0 | **CAUGHT** |
| A5 | flush **after** the ownership hand-over | 0 | 1 | **CAUGHT** |
| A9 | draw-done callback left installed after teardown | 0 | 1 | **CAUGHT** |
| A10 | pump ignores a latched cause | 2 | 0 | **CAUGHT** |

A1 is the one that matters: in the `stream-0001` round it was **NOT CAUGHT**, and
the white-box test `test_the_callback_releases_only_the_indexed_buffer()` added
in `stream-0002` now catches it. A5 and A9 live in `main.c`, which no C unit test
compiles, and are caught only by the host audit guards — which is exactly the
division those guards exist for.

**R6 — the harness itself had a defect, found and fixed in this round.** The
first pass restored files with `shutil.copy2`, which preserves mtime; `make` then
considered the restored source older than the mutant object and re-ran the
**previous mutant's binary**. That invalidated the C column of A3, A5 and A9 in
the first pass (all three reported a stale `C=680`). The harness now stamps
`os.utime(path, None)` after both the mutation and the restoration, the baseline
was rebuilt green (19 binaries, 670 468 + 118 713 + … checks, **0 failures**), and
every number in the table above is from the corrected run. This is the second
stale-build defect this harness has produced; both were caught by checking that
the restored tree still passes, which is now a mandatory step.

#### V5.28.13 Findings

| id | severity | finding | fix required before hardware? |
| --- | --- | --- | --- |
| **R1** | **HIGH** (reporting) | the display self-test increments `consumer_frames_presented`, so `gbp_vqueue_balanced()` carries a deterministic **+1** offset and is false for every run | **No.** Covered by the pre-registered corrected identity of §V5.28.10; raw counters are unaffected. Fixed in `stream-0003`, after the first run. |
| **R2** | MEDIUM | `cause_pending_after_pump` ≡ `cause_arrived_during_pump` by construction; both labels over-promise | No |
| **R3** | MEDIUM | PE FINISH is unmasked during the GBP service path, so the draw-done callback can preempt ACK → RE-ARM (~6 % of cycles, ≤ 16 instructions) | No — but the first run must be read for it |
| **R4** | LOW | the teardown's `GX_DrawDone()` is an unbounded wait, contrary to `CLAUDE.md` §18 | No (after the GBP is restored, operator present) |
| **R5** | LOW | `GX_CopyDisp()` is not awaited before `VIDEO_SetNextFramebuffer()`; a retrace inside the copy shows one torn field | No |
| **R6** | — | the mutation harness's stale-build defect (audit method, not the candidate) | fixed in this round |
| **R7** | LOW | the re-offer loop takes the lowest-index `READY` buffer, not the newest, so with both buffers `READY` an older frame can be shown after a newer one | No |
| **R8** | MEDIUM | `gbp_vpresent_consistent()` is evaluated only in the self-test and in the final report, so the run can say the invariants hold **at the end**, not throughout — and the printed word "HOLD" reads as the stronger claim | No |

**What the re-audit CLEARED, positively:**

- the one-token rule, by exhaustive enumeration of a superset of the program
  (705 states, max 1 `SUBMITTED`, no main-side write to a GP-owned buffer);
- the compiler ordering, PROVEN from the shipped instruction stream;
- the libogc2 semantics every non-blocking claim rests on, re-read from the
  pinned source rather than from memory;
- the XFB model, which turns out to correspond exactly to `currentFb`/`nextFb`;
- the cache-flush ordering, in machine code;
- the teardown order, in machine code, including the second-token case;
- that the display path really executes and the callback really comes from the
  hardware interrupt;
- the test suite's ability to detect all seven focused regressions.

#### V5.28.14 DECISION

```text
DECISION: A — STREAM-0002 SAFE ENOUGH FOR FIRST SUPERVISED PHYSICAL SMOKE

with one KNOWN REPORTING CONDITION, defined here BEFORE physical execution:

  gbp_vqueue_balanced() carries a DETERMINISTIC +1 presentation offset, caused
  by the pre-probe display self-test. The run WILL print
  `counters DO NOT BALANCE`. That is R1 and it is NOT a FAIL.

  The pre-registered corrected identity for the first physical run is

      converted == (presented - SELFTEST.xfb) + overrun

  Every other clause of §V5.21 is evaluated unchanged. If the CORRECTED identity
  does not hold, that IS a FAIL.
```

**The classification, stated so a later reader cannot misread it.** The audit
found no defect in the service path, no defect in the ownership machine and no
defect in the teardown. Every safety property it set out to check was proved:
the one-token rule by exhaustive enumeration (§V5.28.3), the compiler ordering
from the shipped instruction stream (§V5.28.4), the libogc2 semantics from the
pinned source (§V5.28.5), the XFB model against the real VI behaviour
(§V5.28.7), the cache ordering and the teardown order in machine code (§V5.28.8,
§V5.28.9). A candidate whose safety properties all hold is **A**, and labelling
it otherwise because one printed line needs a known correction would confuse a
reporting defect with a hardware risk. It is A.

**What R1 is, and what it is not.**

```text
R1 IS      a REPORTING defect: one counter in the CONSUMER domain is written by
           the pre-probe self-test, which is not a queue frame.
R1 IS NOT  a service defect, an ownership defect, a timing defect or anything
           the device can observe. It is fully contained in how one derived
           predicate prints.
```

**What stands, and what must not be done to it:**

```text
RAW COUNTERS REMAIN AUTHORITATIVE.  Every counter in STREAMSRC, STREAMCONS,
    STREAMOWN, STREAMGX, STREAMPUMP, STREAMPUMPT and STREAMPACE is printed
    individually and is unaffected by R1. `gbp_vqueue_balanced()` is a DERIVED
    predicate over them, and it is the only thing the offset touches.

ARTIFACT IDENTITY IS UNCHANGED.
    build id  stream-0002
    commit    2457d51   (clean, no -dirty)
    size      466 272 B
    sha256    76fa1ff797a05aee37d50fe2b2ae1c7c7ffb2d57fb97166a1322a9c54f24831d

NO REBUILD IS PERMITTED before this run. The artifact that was audited is the
    artifact that runs; a rebuild would produce a different identity and would
    invalidate every hash in §V5.28.1.

NO src/, poc/ OR tools/ CHANGE IS PERMITTED before this run, for the same
    reason. R1 and R8 are fixed in `stream-0003`, AFTER the first run exists.

THE CORRECTION WAS DEFINED BEFORE PHYSICAL EXECUTION. It is recorded here, in
    docs/HANDOFF.md and in docs/research/DEVLOG.md, at commit `f179393` and
    refined in the commit carrying this section — in every case before any
    physical run of `stream-0002`. It is a pre-registration, not a
    post-hoc rationalisation, and it may not be re-derived after seeing a
    result.
```

R3 must still be read out of this run's cycle histogram before anyone calls the
design timing-safe, and R8 means the run reports the invariants at its final
instant rather than throughout. Neither changes the classification: both are
things the first run is *for*.

#### V5.28.15 What a first run still cannot claim

The **CONTROLLED indexed motion stimulus of §V5.18 still does not exist** —
`stimulus/` contains only `agb-color-bars`, the static eight-bar GBP-VIDEO-003
ROM. A first run can therefore validate the service path, the GX path, the
ownership machine and operational pacing, but it **cannot** measure source-frame
loss against ground truth. No result from this run may later be described as
evidence of zero dropped source frames.

#### V5.28.16 The four questions the handoff pre-registered, answered

The previous handoff named four seams to attack first. They were attacked, and
two of them produced findings.

**1. The `submit_ready()` re-offer path — can a READY buffer be lost or
double-submitted?** Neither. `gbp_vpresent_submit()` refuses anything that is not
`READY`, so the state moves `READY → SUBMITTED` once and a second offer of the
same buffer is a no-op returning 0. A `READY` buffer cannot be lost either:
`acquire()` only takes `FREE`, so nothing overwrites it.

It *can*, however, be shown **out of order**, and that is **R7**. The re-offer
loop (`main.c:409-413`) scans `i = 0 … TEX_BUFFERS` and submits the **first**
`READY` buffer, not the newest. Both buffers can be `READY` simultaneously: if a
token is still pending when a conversion completes, that buffer stays `READY`,
the next pump acquires the other one and converts a newer frame into it, and if
the token clears in between, the newer frame can be submitted first — leaving the
older one to be re-offered, and shown, afterwards. Reaching it requires a
draw-done token to stay pending across a whole 40-slice frame conversion, which a
single textured quad makes very unlikely; it is structurally possible rather than
expected, it costs one out-of-order frame on screen, and it disturbs no counter
identity. Recorded, not fixed.

**2. The XFB rule when `VIDEO_GetCurrentFramebuffer()` returns neither stream
buffer.** `xfb_current_index()` (`main.c:189-197`) returns `-1`, and
`gbp_vpresent_xfb_target()` then excludes nothing on the `current` test and only
`xfb_pending` on the second. That is **correct**: if the VI is scanning `xfb_text`
then neither stream buffer is being read, and the only unsafe one is a hand-over
the VI has not yet picked up. The disassembly confirms the three-way lowering:
`800049e8 li r4,0` / `800049f0 li r4,1` / `8000492c li r4,-1`.

This is also the state during the report, and the teardown's
`VIDEO_SetNextFramebuffer(xfb_text)` at `80003dd4` runs **after**
`GX_SetDrawDoneCallback` has been restored, so no present can race it.

**3. Can `display_selftest()` be reached later?** No. It is called exactly once,
from `main` at `main.c:585`, and the compiler inlined it into `main` with no
loop back to it; the only `bl submit_ready.part.0` in `main` is at `80004548`,
inside the straight-line self-test sequence that falls through to the bounded
`VIDEO_WaitVSync` spin at `800039f0`. That spin is `600` iterations maximum and
sits before the capture opens.

**4. Is `gbp_vpresent_consistent()` checked often enough?** **No — this is R8.**
It is called from exactly three places (`main.c:398`, `:719`, `:772`): once inside
the self-test, and twice while formatting the final report. During the whole
30 s capture it is never evaluated. §V5.28.3 proves no reachable state violates
the invariants, so a periodic check is defence in depth rather than a necessity —
but the report prints `OWNER invariants HOLD`, which reads as a statement about
the run, and the evidence only supports a statement about its final instant. A
transient violation that repaired itself would be invisible.

The cheapest honest fix is not a new counter but a changed word: the run can only
claim `invariants hold AT END`. Evaluating the predicate inside `pump()` and
latching a sticky `consistent_violations` counter would let it claim the stronger
thing, and that belongs in `stream-0003` together with R1.

### V5.29 FIRST PHYSICAL SMOKE of `stream-0002` — 2026-09-18 — **ABORTED PRE-SERVICE: `store_or_bounds_invalid`**

```text
STATUS OF THE RUN

  PHYSICAL EXECUTION ATTEMPTED              yes
  GX SELF-TEST PHYSICALLY PASSED            yes
  GBP STREAM CAPTURE NOT STARTED            correct — it never opened
  ABORTED PRE-SERVICE                       store_or_bounds_invalid

  NOT "streaming failed". NOT "video failed". NOT "service failed".
  None of the three was exercised. No sustained-video claim of any kind may be
  attached to this run.
```

Artifact, unchanged and confirmed: `stream-0002`, commit `2457d51`, 466 272 B,
sha256 `76fa1ff797a05aee37d50fe2b2ae1c7c7ffb2d57fb97166a1322a9c54f24831d`.

#### V5.29.1 The abort path, exactly

There is exactly **one** site in the whole source that can produce this pair of
strings, and it is the first gate of the probe:

```text
poc/gbp-video-stream-probe/source/main.c:652   gbp_vstate_probe_run(&t, &rl, &cfg, &res)
  -> src/gbp/gbp_vstate_probe.c:790            if (!st || !gbp_vstate_storage_ok(st))
  -> src/gbp/gbp_vstate_probe.c:791              set_status(..., GBP_VSTATE_ABORT_STORE_UNAVAILABLE,
                                                            "store_or_bounds_invalid")
  -> src/gbp/gbp_vstate_probe.c:796              ringlog "VSTATE abort reason=store_or_bounds_invalid"
  -> src/gbp/gbp_vstate_probe.c:70               status name "abort_store_unavailable"
```

`gbp_video_probe.c:481` carries the same two strings but belongs to
GBP-VIDEO-001's probe, which this POC does not link into its run path. The
vstate site is the one that fired.

#### V5.29.2 Every predicate that can produce it

`gbp_vstate_storage_ok()` (`src/gbp/gbp_vstate.c:70-79`) is a conjunction of
twelve conditions, evaluated in this order:

| # | line | predicate | on this run |
| --- | --- | --- | --- |
| 0 | 790 | `!st` | false |
| 1 | 72 | `!s->frames` | false |
| 2 | 72 | `!s->events` | false |
| 3 | 72 | `!s->raw_ring` | false |
| 4 | 72 | `!s->episode_raw` | **TRUE — this is the one that fired** |
| 5 | 72 | `!s->audio_raw` | false |
| 6 | 73 | `s->frames_cap < GBP_VSTATE_MAX_FRAMES` | **TRUE** (4096 < 16384) |
| 7 | 73 | `s->events_cap < GBP_VSTATE_MAX_EVENTS` | false |
| 8 | 74 | `s->raw_ring_cap < GBP_VSTATE_RAW_RING_BYTES` | false |
| 9 | 75 | `s->raw_ring_slots < GBP_VSTATE_RAW_RING_SLOTS_MIN` | false |
| 10 | 76 | `s->episode_raw_cap < GBP_VSTATE_EPISODE_RAW_BYTES` | **TRUE** (0 < 2 949 120) |
| 11 | 77 | `s->audio_raw_cap < GBP_VSTATE_AUDIO_RAW_BYTES` | false |

**Three of the twelve fail. Short-circuit evaluation means #4 is the one that
actually fired**, at `gbp_vstate.c:72`.

#### V5.29.3 Why — read off the caller, not inferred

```c
/* poc/gbp-video-stream-probe/source/main.c:569-570 */
gbp_vstate_init(&vstate, frame_store, STREAM_MAX_FRAMES, event_store, GBP_VSTATE_MAX_EVENTS,
                raw_ring, sizeof raw_ring, 0, 0, audio_raw, sizeof audio_raw);
/*                                        ^^^^^ episode_raw = NULL, episode_raw_cap = 0 */
```

with `#define STREAM_MAX_FRAMES 4096u` (`main.c:163`), against
`GBP_VSTATE_MAX_FRAMES 16384u`.

This was **deliberate and documented**: `main.c:157-162` says "Streaming does not
need GBP-VIDEO-002's change detector, so the episode raw store (2.81 MiB) is not
allocated at all and the frame table is far smaller than the colour probe's 16384
entries", and §V5.22 proposed exactly that reduction. What nobody did was ask the
validator, or the model, whether the reduction was supported.

#### V5.29.4 It is supported by neither — the validator was RIGHT to refuse

Two sites dereference `episode_raw` with **no NULL check at all**:

```text
src/gbp/gbp_vstate_probe.c:812   memset(st->episode_raw, 0, GBP_VSTATE_EPISODE_RAW_BYTES);
                                 -> a 2 949 120-byte write starting at address 0

src/gbp/gbp_vstate.c:739         dst = s->episode_raw + (ep->raw_slot + ep->raw_frames) * 184320;
                                 memcpy(dst, src, n * 0xF00);
                                 -> preserve_frame(), reached whenever an episode opens
```

`preserve_frame()`'s only guard is `ep->raw_slot == 0xFFFFFFFFu`, and `raw_slot` is
assigned from `episodes_n` alone (`gbp_vstate.c:941`, `:964`) without ever
consulting `episode_raw`. Episodes open on ordinary signature changes, which a
moving picture produces constantly.

**So a NULL episode store is not a smaller model — it is a write to low memory.**
Had `gbp_vstate_storage_ok()` let the run start, `gbp_vstate_probe.c:812` would
have memset 2.81 MiB over the GameCube's exception vectors and OS low memory
**before the first device access**. The gate did its job.

This is stated in full because the tempting fix — relaxing the validator — is the
dangerous one. A diagnostic unit test now pins it
(`tests/unit/test_gbp_vstate.c`, `test_a_null_episode_store_must_stay_refused`).

#### V5.29.5 The physical bounds, reconstructed from the log

`ENVBUF` prints `MEM_VIRTUAL_TO_PHYSICAL(...)`, so every address below is
physical; add `0x80000000` for the cached virtual address. Sizes are the
`sizeof`s the build actually compiled.

```text
region         start        end       size  align  note
gx_fifo     0x0009df00 0x000ddf00   262144     32
tex_buf[0]  0x000de000 0x000f0c00    76800     32  gap 0x100 after gx_fifo
tex_buf[1]  0x000f0c00 0x00103800    76800     32  contiguous after tex_buf[0]
audio_raw   0x00111920 0x00114920    12288     32  gap 0xe120 after tex_buf[1]
raw_ring    0x00114920 0x001c8920   737280     32  contiguous after audio_raw
event_store 0x001c8920 0x00208920   262144      4  contiguous after raw_ring
frame_store 0x00208920 0x002c8920   786432      4  contiguous after event_store
```

```text
overlap                    NONE
alignment violation        NONE   (every DMA/GX target is 32-byte aligned)
out-of-range               NONE   (highest static byte 0x002c8920 = 2.78 MiB of 24 MiB)
integer overflow           NONE   (every start+size < 2^32; no product overflows)
wrong count / wrong sizeof NONE   (each size is exactly count x record, verified below)
BSS containment            OK     (BSS 0x80074d4c .. 0x80337d98, 2 895 948 B; every
                                  region above lies inside it)
```

The three XFBs come from `SYS_AllocateFramebuffer()` in the arena, above the BSS,
and are not part of this table.

**The memory layout is correct.** Nothing here is the problem, and the abort is
not a bounds violation in the ordinary sense: the word "bounds" in the reason
string covers the *capacity contract*, not an address range.

#### V5.29.6 `static_bytes=6922240`, decomposed

```text
gbp_vstate_static_bytes()  (src/gbp/gbp_vstate.c:85-92)

    frames       16384 x 192  =  3 145 728
  + events        4096 x  64  =    262 144
  + raw_ring   THREE slots    =    552 960
  + episode_raw               =  2 949 120
  + audio_raw                 =     12 288
                                ----------
                                  6 922 240     = the logged value, exactly
```

**What it measures: the CAPACITY CONSTANTS of the GBP-VIDEO-002 store model.**
It is computed entirely from `#define`s. It does not read `s`, it is not this
build's footprint, and it is not the BSS.

What `stream-0002` actually allocated:

```text
    frames        4096 x 192  =    786 432
  + events        4096 x  64  =    262 144
  + raw_ring    FOUR slots    =    737 280
  + episode_raw               =          0   NOT ALLOCATED
  + audio_raw                 =     12 288
                                ----------
                                  1 798 144
```

```text
difference  6 922 240 - 1 798 144 = 5 124 096
  frame table never allocated   (16384-4096) x 192  = +2 359 296
  episode store never allocated                      = +2 949 120
  raw ring larger than counted  (737 280 - 552 960)  =   -184 320
                                                       ----------
                                                        5 124 096
```

Answering §4's questions directly:

- **does it include memory outside the BSS?** No. Every term corresponds to a BSS
  array *in the colour and state probes*. In `stream-0002` two of the five terms
  correspond to nothing at all.
- **was the earlier memory report incomplete?** The earlier §V5.22 figures were
  measured on `gbp-video-color-probe` at commit `39f1980` (bss 7 741 712) and were
  never about this build. `stream-0002`'s real figures are text 0x057E40
  (360 000), data 0x019E20 (106 016), **bss 0x2C304C (2 895 948)**, plus three
  XFBs. The two numbers were never comparable and should not have been placed
  beside each other.
- **is there double counting?** No — but there is *phantom* counting: 5 124 096 B
  of the 6 922 240 does not exist in this build.
- **is any store dynamic?** No. `grep` over `src/gbp/` finds no `malloc`,
  `calloc`, `memalign`, `sbrk` or `SYS_GetArena*` anywhere. Every store is a
  static array supplied by the caller.
- **is the value only theoretical capacity?** **Yes.** For every build before this
  one the constants and the allocation happened to coincide (`gbp_vstate.c:81-84`
  already flags the 3-vs-4 slot discrepancy), so the number was accidentally true.
  For `stream-0002` it is a pure capacity constant and is **misleading in the log**.

#### V5.29.7 Comparison with the physically validated builds

Read from source, not from memory:

| build | frame table | raw ring | episode store | outcome |
| --- | --- | --- | --- | --- |
| `vstate-0004` — `poc/gbp-video-state-probe/source/main.c:129-133` | `GBP_VSTATE_MAX_FRAMES` = 16384 | `RAW_RING_BYTES`, 3 slots | `EPISODE_RAW_BYTES`, 2.81 MiB | **physically validated** |
| `color-0002` — `poc/gbp-video-color-probe/source/main.c:148-158` | 16384 | `RAW_RING_BYTES_4`, 4 slots | 2.81 MiB | **physically validated** |
| `stream-0002` — `poc/gbp-video-stream-probe/source/main.c:163-167` | **4096** | 4 slots | **absent (NULL, cap 0)** | **aborted pre-service** |

- **Did the same validator exist?** Yes, identical. `gbp_vstate_storage_ok()`'s
  `!s->episode_raw` and `frames_cap < MAX_FRAMES` checks date from `e8f3a69`, the
  original GBP-VIDEO-002 probe; `bfbca70` (colour) only *added* the
  `raw_ring_slots` check. It was never relaxed.
- **Did the same sizes exist?** No. `stream-0002` is the only build that ever
  supplied a reduced frame table or omitted the episode store.
- **Which GBP-VIDEO-004 change made the preflight fail?** `d611d8f`
  ("probe: add sustained GBP video display candidate") — i.e. **`stream-0001`**,
  the very first streaming candidate. `git show 0816cbe:…/main.c` confirms
  `STREAM_MAX_FRAMES 4096u` and `…, 0, 0, …` were already there. **`stream-0001`
  would have aborted identically.**

**Why three audits missed it.** §V5.26 audited the new code; §V5.28 explicitly
scoped the memory design out, on the stated grounds that "`stream-0002` did not
touch them". That grounds was applied against the wrong baseline: the memory
design *had* changed — in `stream-0001` — relative to every physically validated
build. **An audit's "unchanged, so out of scope" must be measured against the
last physically validated build, not against the previous candidate.** No host
test covered it either: `gbp_vstate_storage_ok()` has unit tests
(`test_gbp_vstate.c:552-565`), but nothing anywhere checked the POC's *call* to
it, and `main()` is not host-compiled.

#### V5.29.8 The GX self-test did not cause this

Checked objectively rather than assumed:

1. **`gbp_vstate_storage_ok()` reads no runtime state.** It reads six pointer
   fields and five capacities, all set by `gbp_vstate_init()`. It never calls an
   arena, heap or VI function.
2. **There is no runtime allocation anywhere in `src/gbp/`.** `grep` for `malloc`,
   `calloc`, `memalign`, `sbrk`, `SYS_GetArena`, `SYS_AllocateFramebuffer` returns
   only comments saying so.
3. **The ordering makes it impossible anyway.** `main()` runs `video_setup()`
   (`:551`, which performs all three `SYS_AllocateFramebuffer` calls),
   `gx_setup()` (`:552`), then `gbp_vstate_init()` (`:569`) — and only then
   `display_selftest()` (`:585`). The fields the predicate reads were fixed
   **before** the self-test ran.

**The validation does not depend on arena bounds, so no before/after arena
comparison is needed.** The self-test is not implicated, and its physical pass
stands on its own.

#### V5.29.9 Host reproduction

A diagnostic reproducing `main.c:569-570` verbatim and evaluating each predicate
separately:

```text
frames=… cap=4096          (GBP_VSTATE_MAX_FRAMES = 16384)
events=… cap=4096          (GBP_VSTATE_MAX_EVENTS = 4096)
raw_ring=… cap=737280 slots=4
episode_raw=(nil) cap=0    (GBP_VSTATE_EPISODE_RAW_BYTES = 2949120)
audio_raw=… cap=12288

  !s->episode_raw                                 *** TRUE -> REFUSES THE RUN ***
  frames_cap < GBP_VSTATE_MAX_FRAMES              *** TRUE -> REFUSES THE RUN ***
  episode_raw_cap < GBP_VSTATE_EPISODE_RAW_BYTES  *** TRUE -> REFUSES THE RUN ***
  (the other nine: false)

storage_ok() = 0
SHORT-CIRCUIT: the predicate that actually fires is #4  !s->episode_raw
gbp_vstate_static_bytes() = 6922240
```

The host reproduces the logged `static_bytes` **exactly**, which confirms the
reconstruction is of the same build and not an approximation. The predicate
evaluation needs no MEM1 addresses: it reads pointers for NULL-ness and integers
for magnitude, and the physical addresses in §V5.29.5 are all non-NULL.

#### V5.29.10 Classification

```text
C — ALLOCATION / CONFIGURATION BUG IN THE POC
    (with a contributing D — a stale capacity assumption in a DESIGN DOCUMENT)

NOT A — validator bug.       The validator is correct and protective; two
                             unguarded dereferences prove the store is required.
NOT B — overlap/bounds bug.  The physical layout is clean: no overlap, no
                             misalignment, no overflow, 2.78 MiB of 24 MiB used.
NOT E — insufficient memory. Roughly 21 MiB of MEM1 is free.
```

The two halves differ and should not be merged:

- **the episode store (C).** Omitting it is *unsupported by the model*, not merely
  unvalidated. §V5.22's claim that it "is not needed by a streaming run" was never
  checked against the dereference sites and is **false as the model is written**.
- **the frame table (D).** Reducing it to 4096 is *safe* — `gbp_vstate.c:824` bounds
  every write and raises `frame_store_full` — but `gbp_vstate_storage_ok()`
  enforces GBP-VIDEO-002's "the store holds the whole run" contract
  unconditionally, and nobody told it that a streaming run may stop earlier.

#### V5.29.11 The smallest correction — PROPOSED, NOT APPLIED

This round is not authorised to change `src/` or `poc/`. The patch below is the
proposal for the next round.

**Preferred: `poc/`-only, zero change to physically validated code.**

```diff
-#define STREAM_MAX_FRAMES 4096u
-static struct gbp_vstate_frame frame_store[STREAM_MAX_FRAMES];
+static struct gbp_vstate_frame frame_store[GBP_VSTATE_MAX_FRAMES];
 static struct gbp_vstate_event event_store[GBP_VSTATE_MAX_EVENTS];
 static uint8_t raw_ring[GBP_VSTATE_RAW_RING_BYTES_4] ATTRIBUTE_ALIGN(32);
+static uint8_t episode_raw[GBP_VSTATE_EPISODE_RAW_BYTES] ATTRIBUTE_ALIGN(32);
 static uint8_t audio_raw[GBP_VSTATE_AUDIO_RAW_BYTES] ATTRIBUTE_ALIGN(32);
@@
-    gbp_vstate_init(&vstate, frame_store, STREAM_MAX_FRAMES, event_store, GBP_VSTATE_MAX_EVENTS,
-                    raw_ring, sizeof raw_ring, 0, 0, audio_raw, sizeof audio_raw);
+    gbp_vstate_init(&vstate, frame_store, GBP_VSTATE_MAX_FRAMES, event_store, GBP_VSTATE_MAX_EVENTS,
+                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw,
+                    audio_raw, sizeof audio_raw);
```

Cost, exactly:

```text
frame table   (16384 - 4096) x 192  = +2 359 296
episode store                       = +2 949 120
                                      ----------
                                      +5 308 416 B  (+5.06 MiB)

bss  2 895 948 -> 8 204 364  (7.82 MiB)
plus text 360 000 + data 106 016 + three XFBs (about 1 843 200 B)
total about 10.0 MiB of MEM1's 24 MiB — comparable to the physically validated
colour probe (bss 7 741 712) and with roughly 14 MiB free.
```

**Required alongside it**, because the log is what a later reader will trust:

1. log the **actual** capacities, not only the constants. `VSTATE stores frames=…`
   currently prints `GBP_VSTATE_MAX_FRAMES` while the build had 4096 — the line
   that should have exposed this defect actively concealed it. It must print
   `s->frames_cap`, `s->events_cap`, `s->raw_ring_cap`, `s->episode_raw_cap`,
   `s->audio_raw_cap` beside the constants.
2. either make `gbp_vstate_static_bytes()` take the `struct gbp_vstate *` and
   report what was allocated, or rename it so it cannot be read as a footprint.
3. a host guard that parses the POC's `gbp_vstate_init()` call and requires a
   non-NULL episode store and `frames_cap >= GBP_VSTATE_MAX_FRAMES` — the check
   that was missing.

**Rejected alternative: relaxing the validator.** Making the episode store
genuinely optional requires guarding `gbp_vstate_probe.c:812` and
`gbp_vstate.c:739` *first*, in code shared with `vstate-0004` and `color-0002`,
both physically validated. That is a larger change with a re-audit cost, for a
2.81 MiB saving in a build with 14 MiB spare. It is not worth it now.

#### V5.29.12 Build-ID impact

```text
stream-0002 is now HISTORICAL: PHYSICALLY EXECUTED 2026-09-18, ABORTED
PRE-SERVICE. Its identity is preserved and is never reused or re-labelled:
commit 2457d51, 466 272 B, sha256 76fa1ff7...

The correction produces a NEW candidate, stream-0003, with a new commit and a
new hash. stream-0002 is never rebuilt.
```

`stream-0003` carries three changes, not one: this store fix, R1 (the
`gbp_vqueue_balanced()` +1 offset) and R8 (the invariants checked only at the
end). It needs its own pre-hardware audit, and that audit's scoping rule must be
measured against `color-0002`/`vstate-0004`, not against `stream-0002`.

### V5.30 `stream-0003` — the storage contract satisfied, R1 retired, R8 latched — 2026-09-18

**`stream-0002` stays historical: PHYSICALLY EXECUTED, GX SELF-TEST PASSED, GBP
CAPTURE NOT STARTED, ABORTED PRE-SERVICE.** Its identity is preserved unchanged —
commit `2457d51`, 466 272 B, sha256 `76fa1ff7…` — it is never rebuilt, never
re-labelled and never re-run, and GBP-HW-134…137 remain its evidence. Nothing
below re-interprets it as a streaming failure, because streaming was never
reached.

`stream-0003` is a new candidate carrying three corrections and nothing else.

#### V5.30.1 The storage fix — in the caller, never in the gate

```c
/* poc/gbp-video-stream-probe/source/main.c */
static struct gbp_vstate_frame frame_store[GBP_VSTATE_MAX_FRAMES];              /* was 4096 */
static uint8_t episode_raw[GBP_VSTATE_EPISODE_RAW_BYTES] ATTRIBUTE_ALIGN(32);   /* was absent */

gbp_vstate_init(&vstate, frame_store, (uint32_t)(sizeof frame_store / sizeof frame_store[0]),
                event_store, (uint32_t)(sizeof event_store / sizeof event_store[0]),
                raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw,
                audio_raw, sizeof audio_raw);
```

The capacities are now derived from the arrays themselves, so the declaration and
the call cannot drift apart. **`gbp_vstate_storage_ok()` was not weakened**: every
requirement it enforced before it enforces now, and a host guard asserts each one
textually so a future "make the POC pass" edit is visible.

Six `_Static_assert`s over the **actual arrays** back it up, so a shrink stops the
build instead of costing a physical run:

```text
sizeof frame_store / sizeof frame_store[0] >= GBP_VSTATE_MAX_FRAMES
sizeof event_store / sizeof event_store[0] >= GBP_VSTATE_MAX_EVENTS
sizeof raw_ring    >= GBP_VSTATE_RAW_RING_BYTES
sizeof raw_ring    %  GBP_VSTATE_RAW_FRAME_BYTES == 0
sizeof episode_raw >= GBP_VSTATE_EPISODE_RAW_BYTES
sizeof audio_raw   >= GBP_VSTATE_AUDIO_RAW_BYTES
```

#### V5.30.2 Configured versus required, everywhere

| what the code says | what it means |
| --- | --- |
| `gbp_vstate_required_capacity_bytes()` | the contract's CONSTANTS — 6 922 240, computed from `#define`s, reading no state. Formerly `gbp_vstate_static_bytes()`; the **value is unchanged**, so every historical log keeps its meaning exactly (§V5.29.6). |
| `gbp_vstate_configured_bytes(s)` | what THIS state was actually given. A store the caller omitted contributes **zero**, which is precisely what made the old number a phantom. |
| `gbp_vstate_storage_fault(s)` | the FIRST unmet requirement, by name, or NULL. `gbp_vstate_storage_ok()` is now *defined* as "this returns NULL", so the gate and the diagnostic can never diverge. |

Two log lines carry it, and the probe's abort now names the field:

```text
VSTATE storecfg frames=16384/16384 events=4096/4096 raw_ring=737280/552960
                slots=4/3 episode_raw=2949120/2949120 audio_raw=12288/12288
                configured_bytes=… required_bytes=6922240 fault=-
ENVSTORE  …the same, from the POC, before the probe is entered…
VSTATE abort reason=store_or_bounds_invalid field=episode_raw_null
```

and the POC prints a full human-readable fault block and a
`OPENGBP-STREAM STORAGE FATAL field=…` Gecko line **before** entering the probe.
The library gate stays generic; the useful diagnostic is the POC's (§15).

#### V5.30.3 Measured footprint — not inferred from "24 MiB is a lot"

```text
text  0x058CE0    363 744 B
data  0x01A4A0    107 680 B
bss   0x7D3074  8 204 404 B     0x80076264 .. 0x808492d8
DOL             471 680 B

predicted bss 8 204 364; measured 8 204 404; +40 B of linker alignment
```

Every store, resolved from the linked ELF rather than from the source:

```text
region          start        end         size  align  note
selftest_raw  0x80079c00 0x8009f400    153600     32
gx_fifo       0x8009f420 0x800df420    262144     32  gap 0x20
tex_buf       0x800df540 0x80104d40    153600     32  gap 0x120   (2 x 76 800)
diag_store    0x80104e10 0x8010ee10     40960      4  gap 0xd0
cyc_episode   0x80110258 0x80112258      8192      4  gap 0x1448
cyc_anomaly   0x80112258 0x80112658      1024      4  contiguous
cyc_last      0x80112658 0x80112a58      1024      4  contiguous
cyc_first     0x80112a58 0x80112e58      1024      4  contiguous
audio_raw     0x80112e60 0x80115e60     12288     32  gap 0x8
episode_raw   0x80115e60 0x803e5e60   2949120     32  contiguous
raw_ring      0x803e5e60 0x80499e60    737280     32  contiguous
event_store   0x80499e60 0x804d9e60    262144      4  contiguous
frame_store   0x804d9e60 0x807d9e60   3145728      4  contiguous
dma_buffer    0x807d9e60 0x807d9e80        32     32  contiguous
log_storage   0x807d9e80 0x80819e80    262144      4  contiguous

BSS           0x80076264 0x808492d8  8 204 404
arena         0x808492e0 0x81800000 16 477 472   three XFBs of 614 400 B come from here

overlap NONE · misalignment NONE · outside-BSS NONE · overflow NONE

text + data + bss + 3 XFB = 10 519 028 B = 10.03 MiB of MEM1's 24.00 MiB
arena remaining after the XFBs: 13.96 MiB
```

#### V5.30.4 Comparison against the physically validated baseline — the §V5.29 lesson, enforced

| | `vstate-0004` | `color-0002` | `stream-0002` | **`stream-0003`** |
| --- | --- | --- | --- | --- |
| frame table | `GBP_VSTATE_MAX_FRAMES` | `GBP_VSTATE_MAX_FRAMES` | **4096** | `GBP_VSTATE_MAX_FRAMES` |
| event store | `GBP_VSTATE_MAX_EVENTS` | `GBP_VSTATE_MAX_EVENTS` | `GBP_VSTATE_MAX_EVENTS` | `GBP_VSTATE_MAX_EVENTS` |
| raw ring | `RAW_RING_BYTES` (3) | `RAW_RING_BYTES_4` (4) | `RAW_RING_BYTES_4` (4) | `RAW_RING_BYTES_4` (4) |
| episode raw | `EPISODE_RAW_BYTES` | `EPISODE_RAW_BYTES` | **absent (NULL, 0)** | `EPISODE_RAW_BYTES` |
| audio raw | `AUDIO_RAW_BYTES` | `AUDIO_RAW_BYTES` | `AUDIO_RAW_BYTES` | `AUDIO_RAW_BYTES` |
| outcome | physically validated | physically validated | **aborted pre-service** | candidate |

A host guard (`test_the_stores_match_the_last_physically_validated_builds`) now
performs this comparison mechanically, against **`vstate-0004` and `color-0002`**,
resolving each POC's declarations rather than comparing argument spellings. The
rule it encodes: **shared VSTATE infrastructure is compared against the last
physically validated build, never against the previous candidate.**

#### V5.30.5 R1 retired — the self-test accounts for itself

`submit_ready()` takes the queue the presentation belongs to:

```c
static void submit_ready(int buf, struct gbp_vqueue *account);
...
if (account) gbp_vqueue_note_presented(account); else selftest_presents++;
```

The self-test passes `0`. Its own presentations and repeats are counted in
`selftest_presents` / `selftest_repeats`, so nothing is hidden — it is *moved*,
not suppressed.

`gbp_vqueue_pristine()` is new and is the assertion, not a comment: after the
self-test and immediately before `gbp_vstate_probe_run()`, **every scientific
counter must still be at its initial value**, and the answer is part of
`selftest_ok`, of the Gecko line and of the report.

Proved behaviourally, not by a source string
(`tests/unit/test_gbp_vstream.c`):

```text
a presentation accounted to NULL          -> pristine, balanced
the stream-0002 shape, ONE note_presented -> pristine FALSE, balanced FALSE
a repeat before the capture               -> balanced TRUE but pristine FALSE
                                             (which is why the POC asserts the
                                              stricter one)
a whole real queue frame                  -> balanced, with no correction
```

**The pre-registered R1 correction is retired for `stream-0003` only.**
`stream-0002`'s historical interpretation is unchanged: its run really did carry
the `+1`, GBP-HW-135 records it, and the corrected identity remains the right way
to read *that* log.

#### V5.30.6 R8 — the invariants latched, not sampled

`gbp_vpresent` now audits itself at every transition and latches a failure that
heals:

```text
audit(p)      at every main-side exit of acquire / fill_done / abandon / submit
audit_isr(p)  at both exits of draw_done
```

Main and interrupt keep **separate** counters (`invariant_failures` /
`invariant_failures_isr`), because a read-modify-write on one shared counter could
lose the interrupt's increment; the report sums them. Both saturate. The audit
**reads** state and writes only counters — the valid state machine is byte-for-byte
the behaviour `stream-0002` had, and a test asserts each guard is still present.

The `submit()` audit runs **after both stores**, never inside the deliberate
one-instruction transient between `tex[idx] = SUBMITTED` and `submitted = idx`.

The report now separates two different claims:

```text
STREAMINV checks=… failures=… main=…/… isr=…/… consistent_at_end=…
```

Proved behaviourally: a full legitimate lifecycle latches **zero**; an injected
two-SUBMITTED state is counted and **stays** counted after the state is healed and
a clean lifecycle is driven over the top of it; the two counters stay apart.

#### V5.30.7 What was deliberately NOT touched

R3's PE FINISH behaviour, the post-RE-ARM pump placement, the one-tile-row slice,
the RGB5A3 mapping, the generation guard, the R3 source-disagreement policy,
`F_SOURCE_DEFERRED`, the mailbox semantics, R5's `GX_CopyDisp` behaviour, R7's
READY selection order and the controlled-stimulus design are **unchanged**. The
timing instrumentation is unchanged, and the next physical run still reports
`pump calls / slices / completed / skipped_cause_pending / pending_before /
pending_after / arrived_during / ticks min·max·mean`. **The slice placement is
still not claimed to be timing-safe.**

#### V5.30.8 Dolphin — auxiliary, and what it did establish

```text
OPENGBP-STREAM READY    app=gbp-video-stream-probe build=stream-0003 …
OPENGBP-STREAM SELFTEST ok=1 converted=1 released=1 submits=1 drawdone=1
                        releases=1 xfb=1 sci_clean=1 inv_fail=0
OPENGBP-STREAM COUNTERS balanced=1 sci_clean_at_probe=1 inv_fail=0 inv_checks=4
                        consistent_at_end=1 storage_fault=-
RESULT: PASS
```

and on screen: `HARDWARE status=abort_inconsistent … teardown=stage_a`.

**That last line is the point.** `stream-0002` aborted at
`abort_store_unavailable` before the probe did anything; `stream-0003` passes the
storage gate and reaches stage A, where it aborts because Dolphin has no Game Boy
Player — which is exactly where `color-0002` and `vstate-0004` abort under
Dolphin. `balanced=1` with **no correction of any kind** is R1 retired, measured
on the binary. `storage_fault=-` is the contract satisfied, measured on the
binary.

Dolphin remains auxiliary and provides no GBP device. Nothing here is evidence
about sustained streaming.

#### V5.30.8b The exact candidate identity

```text
Test ID     GBP-VIDEO-004
Build ID    stream-0003
source      commit 03b32a9   (CLEAN, no -dirty suffix)
DOL         build/poc/gbp-video-stream-probe/gbp-video-stream-probe.dol
            471 648 B
            sha256 2f8e362e40b7e7dae1b3c2069a2a0fdb6376d22f43e3476cc7b28d7c13d199e3
Swiss       build/swiss/12-stream/boot.dol — byte-identical, hash verified.
            The slot is NOT renumbered; 12-stream now holds stream-0003, and
            stream-0001 / stream-0002 keep their identities in this document
            and in docs/HANDOFF.md.
toolchain   powerpc-eabi-gcc (devkitPPC) 16.1.0
            libogc2 r2442.094b250
            ghcr.io/extremscorner/libogc2:20260805
            ZERO warnings at -Wall -Wextra -Wshadow
text        0x058CE0    363 744 B
data        0x01A480    107 648 B
bss         0x7D307C  8 204 412 B     0x8007625C ..
```

The clean build's bss is 8 bytes above the dirty one measured in §V5.30.3,
because the embedded commit string is shorter; both are within 48 B of the
5 308 416-byte prediction, and the difference is linker alignment.

#### V5.30.9 Status

```text
IMPLEMENTED · SOFTWARE/HOST VALIDATED · PRE-SERVICE STORAGE FIXED ·
PHYSICAL CANDIDATE READY · NOT PHYSICALLY EXECUTED

Sustained streaming is NOT claimed to work. Nothing has streamed on hardware.
```

Gates: **19 unit binaries, 792 077 checks, 0 failures; 574 host tests OK**;
`make stream-audit` clean, with the interrupt path byte-identical to the
physically validated GBP-VIDEO-001 build; `make stream-dolphin` PASS.

#### V5.30.10 Next — a SMALL focused audit

The next step is **not** hardware. It is a pre-hardware audit limited to what this
round changed:

```text
1. the actual storage configuration, against vstate-0004 / color-0002
2. address and range sanity of the new layout
3. R1 isolation — that nothing reaches vq except through `account`
4. the R8 latch — that it observes and never writes a state bit
5. the ownership and timing instrumentation, UNCHANGED
6. the exact artifact identity
```

It should be much smaller than §V5.28, because the ownership machine, the
compiler ordering, the libogc2 semantics, the XFB model, the cache ordering and
the teardown were proved there and `stream-0003` did not touch them.

### V5.31 PRE-HARDWARE AUDIT of `stream-0003`, and Dolphin's EMULATED Game Boy Player — 2026-09-18 — **DECISION: A, READY FOR THE FIRST PHYSICAL GBP STREAM SMOKE**

Two things happened in this round and they must not be confused: a **short**
pre-hardware audit of the `stream-0003` candidate, and the correction of a
methodological premise about Dolphin that this project had been carrying.

#### V5.31.1 The artifact

```text
Build ID    stream-0003
commit      03b32a9   (CLEAN, no -dirty)
DOL         471 648 B   sha256 2f8e362e40b7e7dae1b3c2069a2a0fdb6376d22f43e3476cc7b28d7c13d199e3
Swiss       build/swiss/12-stream/boot.dol — byte-identical, verified
```

`git diff --name-only 03b32a9..HEAD -- src/ poc/ tools/` is **empty**: the only
commit after the candidate touched documentation and two host guards.

**Reproduced byte-for-byte** during this round: rebuilt from the same source with
`GIT_COMMIT=03b32a9 GIT_DIRTY=`, the DOL came back at exactly
`2f8e362e…`. (The rebuild happened because a warning check touched the sources;
it turned into a reproducibility proof, and the exact artifact was restored.)

#### V5.31.2 Storage, R1 and R8 — the short audit

Driven against the modules the candidate links, with the POC's exact
configuration:

```text
§3 STORAGE
  frames_cap      = 16384    (required 16384)      ok
  events_cap      = 4096     (required 4096)       ok
  raw_ring_cap    = 737280   slots 4 (req 552960 / 3)  ok
  episode_raw     = non-NULL                       ok
  episode_raw_cap = 2949120  (required 2949120)    ok
  audio_raw_cap   = 12288    (required 12288)      ok
  configured 7 106 560 B / required 6 922 240 B
  gbp_vstate_storage_fault() == NULL               ok
  gbp_vstate_storage_ok()    == 1                  ok

§5 R1
  after the self-test's exact shape: published=0 taken=0 converted=0
  presented=0 overrun=0 repeated=0 dropped=0
  gbp_vqueue_pristine() == 1                       ok
  gbp_vqueue_balanced() == 1, with NO correction   ok

§6 R8
  a full valid lifecycle:      failures=0 in 4 checks (main 3, isr 1)   ok
  an injected two-SUBMITTED state, observed by a transition: LATCHED    ok
  after healing: consistent_at_end == 1, and the failure STILL recorded ok
  the valid machine unchanged: acquire→CPU_FILLING, fill_done→READY,
  submit→SUBMITTED, one-token rule enforced, abandon refuses SUBMITTED,
  draw_done releases exactly the indexed buffer, nothing latched         ok
```

#### V5.31.3 Memory, re-validated from the linked ELF

```text
region        start        end          size  align  note
selftest_raw 0x80079c00 0x8009f400   153600     32
gx_fifo      0x8009f420 0x800df420   262144     32  gap 0x20
tex_buf      0x800df540 0x80104d40   153600     32  gap 0x120
diag_store   0x80104e10 0x8010ee10    40960      4  gap 0xd0
audio_raw    0x80112e60 0x80115e60    12288     32  gap 0x4050
episode_raw  0x80115e60 0x803e5e60  2949120     32  contiguous
raw_ring     0x803e5e60 0x80499e60   737280     32  contiguous
event_store  0x80499e60 0x804d9e60   262144      4  contiguous
frame_store  0x804d9e60 0x807d9e60  3145728      4  contiguous
dma_buffer   0x807d9e60 0x807d9e80       32     32  contiguous
log_storage  0x807d9e80 0x80819e80   262144      4  contiguous

BSS   0x8007625c..0x808492d8  8 204 412 B = 7.82 MiB
arena 0x808492e0..0x81800000; three XFBs leave 13.96 MiB
total text+data+bss+3 XFB = 10 519 004 B = 10.03 MiB of 24.00

no overlap · no misalignment · everything inside BSS · no overflow
```

#### V5.31.4 Timing and ownership parity

`git diff 2457d51..03b32a9` touches `gbp_vpix.{c,h}` in **zero** lines. The
33 changed lines in `gbp_vstate_probe.c` are the `VSTATE storecfg` line and the
`field=` on the abort; the 12 in `gbp_vqueue.c` are `gbp_vqueue_pristine()`.
**The post-RE-ARM pump placement, the one-tile-row slice, the cause precheck, the
pump timing counters, R3, the PE FINISH callback policy, the mailbox and the
generation guard are unchanged.**

**The pump placement remains PLAUSIBLE BUT UNMEASURED.**

#### V5.31.5 The premise about Dolphin was wrong, and here is what is true

Earlier rounds said "Dolphin has no Game Boy Player". That was **wrong as a
statement about the emulator** and only ever true of the *launch configuration*
the automated smokes used. (`docs/protocol/REGISTERS.md` had in fact been citing
Dolphin's GBP model for register semantics all along.)

**Dolphin 2606a — the exact installed Flatpak** (`org.DolphinEmu.dolphin-emu`,
branch `stable`, version `2606a`, flatpak commit `88a604c2…`, built 2026-08-11)
**ships a real emulated Game Boy Player.** Read out of the installed binary, not
inferred from master:

```text
HSP::CHSPDevice_GBPlayer     the HSP device
HSP::CGBPlayer_mGBA          backed by libmgba (HAS_LIBMGBA is on)
HSP::IGBPlayer               the interface
Source/Core/Core/HW/HSP/HSP_DeviceGBPlayer.cpp
config keys: HSPDevice, GBPlayerRom
```

How it is enabled, from the source of the matching tree
(`external/dolphin` @ `c185d27e`):

```text
Dolphin.Core.HSPDevice  = HSP::HSPDeviceType   None = 0, ARAMExpansion = 1, GBPlayer = 2
                          (MainSettings.cpp:252, default None)
Dolphin.GBA.GBPlayerRom = MAIN_GBA_ROM_PATHS[GBPLAYER_GBA_INDEX = 4]
                          (MainSettings.cpp:406, guarded by HAS_LIBMGBA)

GBA BIOS         NOT required — GBACore.cpp sets useBios = 0 and skipBios = 0,
                 so mGBA's HLE BIOS is used. Main.GBA.BIOS is optional.
Start-up Disc    NOT required — HSPManager::Init() creates the device from
                 Config::MAIN_HSP_DEVICE at hardware init, independent of what
                 software boots (HSP.cpp:19-22).
Reachability     the device is driven through ARAM DMA (DSP.cpp:511, :571),
                 which is exactly the path Open-GBP already uses.
Register select  address >> 20: Test 0x10, Video 0x11, Control 0x14,
                 SIOControl 0x15, Audio 0x18, SIOData 0x19, Keypad 0x1c, IRQ 0x1d
```

So: **a homebrew DOL can reach the emulated GBP directly. No Start-up Disc, no
GBA BIOS.**

#### V5.31.6 It was executed — and the A/B control proves the device is visible

The exact `stream-0003` DOL, in an **isolated** Dolphin profile
(`--user-dir …/dolphin-user-gbp`, every setting a session-only `-C` override,
nothing persisted, the operator's own configuration untouched):

| run | `HSPDevice` | cartridge | probe status | reason |
| --- | --- | --- | --- | --- |
| control | `0` (None) | — | `abort_inconsistent` | `inconsistent` |
| AGS | `2` (GBPlayer) | `input/AGS-rom.gba` | **`abort_control_shape`** | **`control_not_idle_shape`** |
| bars | `2` (GBPlayer) | `build/physical/agb-color-bars-cart.gba` | **`abort_control_shape`** | **`control_not_idle_shape`** |

**The abort changes, and the only variable is the HSP device.** That is the
evidence that the emulated GBP is instantiated *and* visible to the protocol
Open-GBP uses: the probe's AR_INFO stage succeeds (`arinfo=1`), it reads CONTROL
from the emulated device, and it rejects the value.

Both cartridges give the same result, so it is not ROM-specific.

#### V5.31.7 The first divergence, named exactly

```text
Open-GBP's 003A idle gate (gbp_initirqa_probe.c:48-49, :652-655)
    clear_mask = 0x10   must be SET   in the idle CONTROL  (CONTROL_MASK_IRQ)
    set_mask   = 0x0C   must be CLEAR in the idle CONTROL  (3V | 5V)
    hardware presents 0x90; the transform is 0x90 -> 0x8C

Dolphin's model (HSP_DeviceGBPlayer.cpp)
    u8 m_control{};                          zero at power-on
    Write:  m_control = value & 0xFC;        bits 0-1 are never writable
    Read:   ORs in CONTROL_CART_INSERTED 0x02 and CONTROL_CART_IS_GB 0x01 only
    ⇒ the power-on CONTROL a host reads is 0x02 (or 0x03), and
      bit 0x10 is NEVER set by the model itself
```

So `(orig & 0x10) == 0` and the gate fires, deterministically.

**This is a MODEL divergence, not an Open-GBP omission.** The gate is grounded in
physical observation, and relaxing a physically grounded gate to satisfy an
emulator would invert this project's authority hierarchy. Nothing in Open-GBP was
changed, and nothing needs to be.

Using §15's taxonomy: it is **B** — Dolphin instantiates the GBP, but its model
does not reproduce the hardware's power-on CONTROL. It is **not** A (the launch
configuration is correct and proven), and **not** D (Open-GBP performs the
initialisation the hardware sequence calls for; it simply refuses a device whose
CONTROL is not in the shape hardware presents).

A future *diagnostic-only* emulator mode could relax `require_idle_shape`, and it
would have to be opt-in, clearly labelled EMULATOR, and never the default. That
is a design question for another round, not a defect here.

#### V5.31.8 A second model divergence, recorded before anyone trips on it

Dolphin's VIDEO read (`HSP_DeviceGBPlayer.cpp`, `GBPRegister::Video`):

```cpp
const u16 color = m_scanlines[scanlines_pos++];
data[i + 0] = data[i + 1] = u8(color >> 8);
data[i + 2] = data[i + 3] = u8(color);
```

so **byte 0 == byte 1 and byte 2 == byte 3**. Physically they do not:
GBP-HW-133 measured byte 0 differing in 2 222 positions and byte 2 in 212,
while bytes 1 and 3 differed in **zero**. **Dolphin can therefore never be
evidence about U-GBP-029**, in either direction.

`CHSPDevice_GBPlayer::UpdateInterrupts()` also asserts the PI cause on
`(m_control & CONTROL_MASK_IRQ) == 0 && (m_irq & IRQ_ASSERTED) != 0`, which
`docs/protocol/REGISTERS.md` already records as not matching the hardware.

#### V5.31.9 What this does NOT settle

Dolphin stays **AUXILIARY**. Nothing from §V5.31 may promote a physical FACT, and
in particular it says nothing about the R3 hardware mechanism, the RE-ARM→next
cause timing, the physical PE FINISH perturbation, bytes 0 and 2, bit 15, or
source-frame loss. No video frame was produced by the emulated GBP in these runs,
because the probe stopped at the CONTROL gate; **there is no AGS picture to
report, and none is claimed.**

#### V5.31.10 Preserved emulator evidence

`captures/local/dolphin-gbp/` (ignored by Git, EMULATOR/AUXILIARY, never
physical), reproducible with `make stream-dolphin-gbp` and
`make stream-dolphin-gbp GBP_HSP=0`:

```text
report-hsp2.json   002eab96f31d17e488c2655a1a4f6c8bffb23f31d298cdf5e95452684fe5dd2e
screen-hsp2.png    221d2bb0299fe28895f56e3d6d438450624bd78764b907a015460040b416a9fe
dolphin-hsp2.log   584d768b7abcf3fa8dba25b14f725497c3d6517227d69911d670f722552ce2fe
report-hsp0.json   8c4923506f308c2f50c2281d42595982a7e0414a0592c73ac933ee75d431878b
screen-hsp0.png    1a518539eb53ad468c53aedb55c727ec4caf41c16b64dd7b56692f1c2ec47a63
dolphin-hsp0.log   db40bf2f4904b4ad420f898dec375983f5b94c5ad17b11153b6796127d90e84b

AGS-rom.gba        1 326 620 B
                   736b5ef7e17633aa7cff34390fa0337f7818abae5d264cd4954010a0540de7df
                   (verified before use; AGS Aging Cartridge v10.0)
colour cart        1 076 B  bb741770e92ecdcf10f74ae32b01e338384047d8d82e4f14f2162ba9ec234fe3
canonical stimulus 1 076 B  867bb8d681e815793792e5e85bf031967eec11c07d00dcb16e68b6c96520f3ba
```

#### V5.31.11 Findings and DECISION

| id | severity | finding |
| --- | --- | --- |
| S1 | — | the storage contract is satisfied; `gbp_vstate_storage_fault()` is NULL |
| S2 | — | R1 retired: the queue is pristine entering the probe, `balanced=1` with no correction |
| S3 | — | R8 latches a transient violation and still reports `consistent_at_end` separately |
| S4 | — | the memory layout is clean and 10.03 MiB of 24.00 |
| S5 | — | the timing instrumentation and the ownership machine are unchanged |
| D1 | model | Dolphin's GBP power-on CONTROL is `0x02`, hardware's is `0x90` — the emulated run stops at `control_not_idle_shape` |
| D2 | model | Dolphin's VIDEO read duplicates bytes 0↔1 and 2↔3; hardware does not (U-GBP-029) |

```text
DECISION: A — STREAM-0003 READY FOR THE FIRST PHYSICAL GBP STREAM SMOKE

No software defect was found. The storage contract that stopped stream-0002 is
satisfied and machine-checked, R1 is retired, R8 is latched, the memory layout is
clean, and the timing path is untouched.

D1 and D2 are DOLPHIN MODEL divergences. They do not block hardware — as §20 of
the round's own instructions says, a Dolphin failure to instantiate or drive the
GBP does not block a physical run when the candidate passes the software audit.
```

#### V5.31.12 The physical procedure, if the operator proceeds

```text
Test ID     GBP-VIDEO-004
Build ID    stream-0003     — the EXACT artifact, NO rebuild
DOL         471 648 B  sha256 2f8e362e40b7e7dae1b3c2069a2a0fdb6376d22f43e3476cc7b28d7c13d199e3
Swiss       12-stream/boot.dol (byte-identical copy)
Cartridge   any GBA cartridge the operator chooses; §V5.18 names properties,
            not a title. The controlled colour-bars cart is a reasonable first
            choice because a physical correspondence already exists for it.
Link Port   as the operator normally runs it; nothing here needs it
Steps       1. copy boot.dol to SD as 12-stream
            2. launch through Swiss with the cartridge already running
            3. DO NOT press anything for the 30 s capture
            4. press X to save the log, then START
            5. POWER CYCLE the console
Duration    SHORT and SUPERVISED: 30 s capture, 60 s safety cap
Objective   OPERATIONAL, TIMING and DISPLAY behaviour of the streaming path.
            This run is NOT a decisive frame-loss validation — the CONTROLLED
            indexed motion stimulus of §V5.18 does not exist, so source-frame
            loss cannot be measured against ground truth.
Read it     with §V5.21, unchanged. stream-0003 needs NO counter correction:
            `counters BALANCE` is expected, and `DO NOT BALANCE` would be a
            real finding this time.
Watch for   the per-cycle t_cause/t_ack/t_rearm histogram (R3), and
            STREAMINV failures=0 (R8) — the two things the run is for.
```

### V5.32 CONTROLLED indexed video stimulus — design round 2, offline model — 2026-09-18 — **VERDICT: B, ONE MORE REVISION BEFORE THE ROM**

**Nothing physical happened in this round and nothing physical changed.**
`stream-0003` is untouched: commit `03b32a9`, 471 648 B, sha256
`2f8e362e…199e3`, Swiss copy byte-identical. **The next physical action is still
the first supervised GBP stream smoke of that exact artifact**, and this round
does not alter it.

This round did what the previous design round could not: it **built the offline
reference model and ran the design against it**. Two of the design's own
assumptions did not survive, which is the entire reason the model was written
before the ROM.

#### V5.32.1 The source observation point — FROZEN

Traced in the real code. Per VIDEO block, in `gbp_vstate_probe.c`:

```text
:1394  sig = gbp_vsig_block(blk, 0xF00)     computed from the RAW block AT RECEIPT
:1397  majority-extra quarantine flagging
:1398  gbp_vstate_block(st, blk, …, sig, …)
         └─ gbp_vstate.c:1143  s->cur_sig[s->cur_blocks] = sig
         └─ on a boundary: close_frame()
              └─ gbp_vstate.c:876  sig_copy(f->sig, s->cur_sig)   ← frame record written
:1411  colour hook (only when cfg->color)
:1425  if (cfg->stream && step.frame_closed)
:1429     gbp_vqueue_publish(...)            ← PUBLICATION, strictly afterwards
```

**`struct gbp_vstate_frame` is written at frame close, strictly UPSTREAM of the
mailbox.** `frame_store[]` is never touched by the consumer, so
`dropped_before_convert`, `consumer_slot_overrun` and every display effect are
incapable of removing a frame from it.

**SOURCE OBSERVATION POINT = `close_frame()` in `src/gbp/gbp_vstate.c`.** Frozen.
No STOP condition; the architecture the experiment needs is already there.

#### V5.32.2 The observable population — the old wording was too strong

```text
OBSERVABLE POPULATION
  the transitions between consecutive frames stored in frame_store[], from the
  first to the last frame that decodes to an intact source ID

UNOBSERVABLE EDGES
  (a) AGB frames presented BEFORE the first stored frame. The capture opens
      whenever the probe opens it; blocks arriving before the first frame
      boundary are counted in `blocks_before_first_boundary` and are never
      turned into a frame.
  (b) AGB frames presented AFTER the last stored frame, for the same reason at
      the other end.
  (c) everything while frame_store is full (`frame_store_full`), where the run
      stops storing rather than wrapping.

CLAIM ALLOWED
  "between the first and last intact source frame IDs observed at the source
   layer, the ID sequence was contiguous, ordered and internally consistent"

CLAIM NOT ALLOWED
  "every frame the AGB presented during the capture window arrived"
  "zero source-frame loss"
```

Worked example, and it is not hypothetical:

```text
source presents   100, 101, 102, 103
capture observes       101, 102
observed sequence is CONTIGUOUS — and 100 and 103 are invisible.
```

**No anchor is proposed.** Inventing one to rescue the old wording would be
exactly the move this project forbids. An anchor is possible in principle (a
distinguished ID range painted at a known moment, or a source-side marker the
runtime could timestamp) and it is left as an explicit future question rather
than assumed away.

#### V5.32.3 CRC-8, specified bit by bit

```text
register        8 bits            polynomial  0x07  (x^8 + x^2 + x + 1)
init            0xFF              xorout      0x00
input order     MSB-first: FRAME_ID[23]…FRAME_ID[0], then BLOCK_INDEX[5]…[0]
                exactly 30 bits; NO zero augmentation
per bit         fb  = ((crc >> 7) & 1) ^ inbit
                crc = ((crc << 1) & 0xFF) ^ (0x07 if fb else 0)
reflection      none, input or output
result          the final register value, painted MSB-first
```

Known-answer vectors, locked in `tests/host/test_istim.py`:

| FRAME_ID | BLOCK_INDEX | 30-bit payload | CRC8 |
| --- | --- | --- | --- |
| `0x000000` | 0 | `000000000000000000000000000000` | `0xF6` |
| `0x000000` | 39 | `000000000000000000000000100111` | `0x03` |
| `0x000001` | 0 | `000000000000000000000001000000` | `0x31` |
| `0x000001` | 39 | `000000000000000000000001100111` | `0xC4` |
| `0xFFFFFF` | 0 | `111111111111111111111111000000` | `0x3F` |
| `0xFFFFFF` | 39 | `111111111111111111111111100111` | `0xCA` |
| `0x123456` | 17 | `000100100011010001010110010001` | `0xDC` |

A single-bit flip anywhere in the 30-bit payload always changes the CRC — tested
exhaustively over all 30 positions for three payloads.

#### V5.32.4 Modular classification — frozen, and the half-range is not a gap

```text
delta = (id_n − id_prev) mod 2^24

delta == 0            OBSERVED_DUPLICATE_ID
delta == 1            CONTIGUOUS
2 <= delta <  2^23    FORWARD_GAP          (delta − 1 source frames missing)
delta == 2^23         UNRESOLVED_HALF_RANGE   ← NEVER a forward gap
delta >  2^23         REORDER_BACKWARD
```

`0xFFFFFE → 0xFFFFFF → 0x000000 → 0x000001` is CONTIGUOUS at every step, tested.

#### V5.32.5 Bit 15 — the previous design got this wrong

The decoder reads `colour15 = word16 & 0x7FFF`, and both symbols are chosen
below bit 15. `ZERO|0x8000 → 0x0000` and `ONE|0x8000 → 0x7FFF`, so:

```text
bit 15 on a strip pixel CANNOT change a decoded ID bit
bit 15 on a strip pixel CANNOT make the CRC fail
```

**ID decoding ignores bit 15 by construction.** The flag's coordinate and count
are an **independent diagnostic channel** and an unexpected coordinate is a
**U-GBP-034 observation, not an ID-integrity failure**. `FLAG = 0x03E0` at
`x = 0` is kept precisely because U-GBP-034 asks for a first pixel that is
neither black nor white.

One asymmetry that matters and is easy to get wrong: **`gbp_vsig_block()` does
NOT mask bit 15**, so the device's flag at (0,0) does shift `sig[0]` of block 0
by `0x8000 << 16`. The reference model therefore renders both variants.

#### V5.32.6 What `gbp_vsig_block()` actually computes

```text
The 3840-byte block is 240 groups of 16 bytes = 4 pixels each. With
w_j = (b1 << 8) | b3 the consumed word of pixel j INCLUDING BIT 15, and
j = row*240 + x with 240 even (so parity(j) = parity(x)):

    S   = Σ_k ( w_{2k}·2^16 + w_{2k+1} )
        = 2^16 · Σ_{x even} w  +  Σ_{x odd} w
    sig = (S mod 2^32 + ⌊S / 2^32⌋) mod 2^32
```

Output 32 bits. It is an **additive checksum with a single end-around fold, not
a hash**:

* invariant under any permutation of pixels *within one parity class*;
* `w_a + w_b = w_c + w_d` is a collision, constructible by hand;
* `S < 960·2^32`, so the fold adds at most 959 and can itself wrap.

The Python model reproduces the C **exactly**, verified by compiling
`src/gbp/gbp_vsig.c` and comparing on real stimulus blocks.

#### V5.32.7 DDR-2 — ANSWERED, and the answer is NO

**The question was never statistical.** With the proposed layout the frame ID
contributes *nothing* to the signature, by construction:

```text
rows 4b+0 / 4b+2 paint the payload;  rows 4b+1 / 4b+3 paint its COMPLEMENT.
For 46 bits there are 23 odd and 23 even bit positions, so within each
(true, complement) row pair the count of ONE symbols per parity class is
EXACTLY 23, whatever the payload is.

measured: the ONE count per parity class is (92, 92) for every frame ID tested,
including 0, 1, 2, 0x5A5A5A and 0xFFFFFF.
```

The additive checksum only ever sees counts and positions weighted by parity, so
**the complement-pair design annihilates the ID exactly.** What remains is the
bar, whose position has period 35:

```text
sig(f, b) == sig(f + 35, b)          verified for all b, f < 12
distinct signature values per block over ALL f:  at most 35
actually observed within one period:             15   (20 of 35 phases collide)
```

So `sig[40]` cannot identify a frame ID, and **cannot even recover the bar
phase**. A sliding-window scan over 80 IDs with a 4096 window found 2 600
collisions, the first at Δ = 3 — but the scan is decoration: the period proof
settles it.

**The "8192" of the first proposal was never testable anyway.** The stimulus
starts at `frame_id = 0` at cartridge power-on, and the interval between that
and the capture is operator-dependent — Swiss navigation, DOL load, the 5 s
pre-handler wait. **The maximum absolute ID cannot be bounded from existing
behaviour, and this is stated rather than assumed away.** Only the *window* is
bounded: the 60 s safety cap gives ≤ 3 585 frames, so a search window of 4 096 is
derived, not chosen.

#### V5.32.8 Adversarial characterisation — what the checksum misses

CHARACTERISATION, never proof. Locked as tests so a later round cannot quietly
assume more.

| mutation | `gbp_vsig_block` |
| --- | --- |
| one consumed pixel, one bit, odd x | **detects** |
| one consumed pixel, one bit, even x | **detects** |
| bit 15 set on one pixel | **detects** |
| a block from the adjacent frame | **detects** |
| a block from frame + 35 | **misses** (structural period) |
| **strips substituted from another FRAME ID** | **misses** |
| **strips substituted from another BLOCK INDEX** | **misses** |
| a duplicated row | misses |
| a compensating +1/−1 on two same-parity pixels | misses |
| bytes 0 and 2 changed | misses **by design** (U-GBP-029 cannot move it) |

Failing to find a collision would never have proven one cannot exist; here
collisions were *constructed*, which is a different and stronger statement.

#### V5.32.9 Three layers, and what each may claim

```text
A. LOSSLESS PIXEL EVIDENCE — the consumed words themselves
   MAY CLAIM: everything. The strip is the authority for the frame ID.

B. ERROR-DETECTING CODE — SYNC, complement, 8-copy redundancy, CRC-8
   MAY CLAIM: a decoded ID that passes SYNC + CRC on ≥5 of 8 copies is very
   unlikely to be an accident, and a single-bit payload error is IMPOSSIBLE to
   miss. MAY NOT CLAIM: that the decoded ID is mathematically certain. CRC-8 is
   not collision-free; the 5-of-8 rule is an ERROR-RECOVERY POLICY, not a proof.

C. FINGERPRINT — gbp_vsig_block()
   MAY CLAIM: two blocks with different signatures are different.
   MAY NOT CLAIM: anything about the frame ID. §V5.32.7 and §V5.32.8 show it is
   blind to the ID and to strip substitution. It is NOT "lossless".
```

**LEVEL-1 VERDICT: B — `sig[40]` is not sufficiently discriminative even for
expected-frame identification.** It is not tuned, excused or relied on.

#### V5.32.10 Lossless witness — the cost of doing it properly

Preserving consumed word16 verbatim, at 59.737 Hz:

| option | B/frame | 30 s | 5 min | 30 min | 1 h |
| --- | --- | --- | --- | --- | --- |
| A all 8 strip copies | 29 440 | 52.8 MB | 528 MB | 3.17 GB | 6.33 GB |
| B one L + one R per block | 7 360 | 13.2 MB | 132 MB | 791 MB | 1.58 GB |
| **C one normalised copy per block** | **3 680** | **6.59 MB** | 66.0 MB | 396 MB | 791 MB |
| — raw frame, for scale | 153 600 | 275 MB | 2.75 GB | 16.5 GB | 33.0 GB |
| — the existing 192 B record | 192 | 0.34 MB | 3.44 MB | 20.6 MB | 41.3 MB |

MEM1 free after `stream-0003` is **13.96 MiB**. So **option C fits a 30 s run in
MEM1 with room to spare, option B is marginal, option A does not fit**, and
nothing fits 5 minutes. **No SD write in the critical path is proposed here**:
that needs its own timing design and this round does not have one.

**Option D, and it is the one to prefer:** a per-block **CRC-32** alongside the
existing signature — 4 B/block, 160 B/frame, the same cost as `sig[40]`, but
with a collision structure that is actually usable. It is **stimulus-agnostic**,
it would make a Level-1-style witness viable, and it does not require the runtime
to know anything about strips. **It is a `src/gbp/` change and is therefore NOT
made here**; it is the single highest-value follow-up.

#### V5.32.11 Stimulus-aware versus stimulus-agnostic

```text
STIMULUS-AGNOSTIC (preferred; the runtime preserves, the analyzer interprets)
  raw frames, or a bounded deterministic sample of them
  a per-block CRC-32 or any generic fingerprint
  every counter that already exists

STIMULUS-AWARE (must be declared as such, never disguised)
  preserving "the strip columns" — a fixed ROI at x∈[1,46]∪[193,238] IS
  stimulus-aware even though it decodes nothing. Options A, B and C above are
  ALL stimulus-aware for this reason.
```

If option C is chosen, the round that implements it must say plainly that the
runtime gained stimulus knowledge, and confine it to a retention rule that
decodes nothing and decides nothing.

#### V5.32.12 Duplicate semantics — renamed

`SOURCE_DUPLICATE` claimed a mechanism the evidence cannot support: a repeated ID
could be a transport duplication, a stimulus that held one ID across two source
periods, or a capture that sampled one presented frame twice. The label is
**`OBSERVED_DUPLICATE_ID`** and the mechanism is **UNKNOWN**. It may be
strengthened later only if the stimulus's update schedule is independently
proven.

#### V5.32.13 A real defect in the content pattern, found by the geometry tests

The first proposal used `barpos(f,b) = (f + 7·b) mod 35`. **gcd(7, 35) = 7**, so
the 40 blocks collapsed onto **5** distinct phases instead of spreading. The
multiplier is now **8** (coprime with 35), giving 35 distinct phases; 40 > 35, so
five pairs of blocks necessarily share one, which is acceptable because **the bar
is a freshness witness, never an identifier**.

Proved in tests: the bar always lies inside `x ∈ [48, 191]`; the last phase
touches exactly column 191; the previous bar is restorable from `background(x,y)`
alone, so the ROM needs no memory of it; `expected_agb(f,x,y)` is total on the
whole 240×160 domain and refuses out-of-range input instead of guessing.

#### V5.32.14 VBlank — an estimate, and what the ROM must measure

```text
strip pixels/frame   14 720     46 bits × 2 strips × 4 rows × 40 blocks
bar pixels/frame      2 560     8 px × (erase+draw) × 4 rows × 40 blocks
total                17 280 px = 8 640 32-bit VRAM stores × 2 cycles = 17 280 cycles
VBlank budget        83 776 cycles (GBATEK, FACT) → 20.6 % on the stores alone
```

**NOT counted, which is why this stays an ESTIMATE:** loop control and address
arithmetic over 40 × 4 × 2 strips; CRC-8 preparation (30 bit-iterations × 40
blocks, reducible to one table lookup per block by folding `crc8(frame_id)`
once); the bit-to-symbol expansion; and **the modulo**. ARM7TDMI has **no divide
instruction**, so `mod 35` becomes a call or a reciprocal sequence — the ROM must
use a running counter with compare-and-subtract instead.

**What the ROM must measure before this is a property:** the elapsed time from
the VBlank IRQ to the end of the update, read from a hardware timer, reported on
screen, and required to be less than the VBlank length on the real device.

#### V5.32.15 What 30 s gives

```text
~1 792 source frames, ~1 791 observed transitions
frame_store holds 16 384 frames = 274.3 s, so 30 s uses 11 % of it
per-frame records: 1 792 × 192 B = 0.34 MB
```

"Zero observed gaps" means **of ~1 791 observed transitions, none had Δ ≠ 1**. It
does **not** bound the loss rate below ~1/1 792, and it says **nothing** about the
unobservable edges of §V5.32.2. 30 s remains the proposal and is **not frozen**.

#### V5.32.16 Long-run

24-bit ID wraps after 2^24 / 59.737 Hz = **77.98 hours**, the wrap is defined and
the classification handles it. Nothing in the frame format prevents a long run.
SD streaming is **not** designed here.

#### V5.32.17 AGS versus the indexed stimulus

```text
AGS Aging Cartridge v10.0   WORKLOAD / REFERENCE — real timing, NO ground truth
stimulus/agb-indexed        CONTROLLED GROUND TRUTH — the only category that can
                            MEASURE loss instead of inferring it
```

#### V5.32.18 Verdict

```text
B — DESIGN NEEDS ONE MORE REVISION BEFORE THE ROM

The STIMULUS survived: geometry, symbols, payload, CRC, redundancy decoder,
modular classification and the content pattern are all proved in the offline
model, with one real defect found and fixed (the phase multiplier).

The SIGNATURE ARCHITECTURE did not. Level 1 is rejected outright — a C-grade
finding scoped to that sub-component, not to the stimulus.

What must be settled before the ROM is written:
  1. the witness strategy — option C (stimulus-aware strip retention, 6.6 MB for
     30 s) or option D (a stimulus-agnostic per-block CRC-32 in src/gbp);
  2. whether an anchor for the unobservable edges is wanted, or whether the
     narrowed claim of §V5.32.2 is accepted as the experiment's scope;
  3. the ROM's own VBlank measurement method.
None of them blocks the first physical smoke of stream-0003.
```

#### V5.32.19 Next implementation step

**Not the ROM.** Decide (1) above. If option D is chosen it is a small, testable
`src/gbp/` addition that must be audited like any other runtime change, and it
would make the witness stimulus-agnostic — which is the scientifically better
outcome and the one recommended here.

### V5.33 `stimulus/agb-indexed` — **CONTRACT FROZEN, format version OGBPIDX1 — 2026-09-18 — VERDICT: A**

**Nothing physical happened and nothing physical changed.** `stream-0003` is
untouched — commit `03b32a9`, 471 648 B, sha256 `2f8e362e…199e3`, Swiss copy
byte-identical — and **the next physical action is still the first supervised GBP
stream smoke of that exact artifact**. No ROM was written. No `src/` or `poc/`
file was touched.

Round 2 (§V5.32) ended at verdict B with three blockers. This round resolves all
three and freezes the contract.

#### V5.33.1 Blocker 1 — the decisive witness

`gbp_vsig_block()` is **accepted as not being an identifier** and is not tuned to
become one. §V5.32.7 proved the ID contributes nothing to it, §V5.32.8
constructed collisions. It stays as a generic historical diagnostic and **carries
no part of the decisive claim**.

```text
CANONICAL WITNESS  (the decisive evidence)
  ONE strip copy per VIDEO block, preserved LOSSLESSLY as the original consumed
  word16 — STRIP-L, LOCAL ROW 0 of the block, i.e. screen row 4*b, x = 1..54.
  54 words x 2 B = 108 B per block, 4 320 B per frame.
  Chosen because it is the FIRST LINE of the block on the wire: a runtime copy
  is one stride at the head of the delivery and needs no buffering.

DIAGNOSTIC REDUNDANCY  (not required by the decisive claim)
  the other seven copies — STRIP-L rows 1/2/3 and STRIP-R rows 0/1/2/3 — stay in
  the picture and are usable whenever raw or anomaly evidence exists.
```

**The canonical witness does NOT prove pixel-perfect equality of the frame.** It
proves exactly three things, and they are separate questions (§V5.33.7).

#### V5.33.2 Blocker 2 — the scientific claim, narrowed and pre-registered

```text
THE QUESTION
  "Between the first and last intact source-frame IDs observed at the
   PRE-PUBLICATION capture layer, was the observed source-ID sequence contiguous
   and ordered, with every captured frame composed of the expected 40 block
   indices carrying one consistent frame ID?"

NOT OBSERVABLE, and no claim is made about it:
  * AGB frames presented BEFORE the first intact observed ID
  * AGB frames presented AFTER  the last  intact observed ID

NO ANCHOR IS ADDED. A handshake or start trigger built only to make the edges
observable would enlarge the experiment for a question nobody has asked. The
narrowed scope is accepted. A later version may add one if a real question needs
the edges.
```

#### V5.33.3 Blocker 3 — the stimulus validates itself

Mode 3 has one framebuffer, so "the update finished inside VBlank" must be
**measured by the stimulus and carried in the payload**, not assumed.

Mechanism, from GBATEK (`external/gbatek/gba.md`, FACT):

```text
VCOUNT   0x04000006, read-only, LY 0..227; 160..227 ARE the VBlank scanlines
Timer    prescaler 1 = F/64 -> 16 777 216/64 = 262 144 Hz, 3.8147 us per tick
VBlank   68 lines, 83 776 cycles, 4.994 ms  ->  1 309 ticks of that timer
```

Both are free-running reads; nothing beyond the VBlank IRQ is needed.

```text
SOURCE_UPDATE_FAULT — a sticky latch, cleared only by a boot
  set when an update ends with VCOUNT outside [start, 227],
  or with elapsed ticks > the VBlank tick budget,
  and NEVER cleared for the rest of that boot.

VMARGIN — a monotone MINIMUM, 7 bits
  the smallest number of VBlank scanlines still remaining at the end of any
  update so far, clamped 0..127, initialised to 127 = "no update measured yet"
  (unreachable by a real margin, since VBlank is only 68 lines).
```

If `FAULT` is observed set anywhere in the run, the run is classified
**`STIMULUS_INVALID_FOR_DECISIVE_CLAIM`** — the stimulus itself is the thing in
doubt, and the source-integrity claim cannot be made without qualification.

#### V5.33.4 The frozen format — **OGBPIDX1**

```text
GEOMETRY (240 x 160, AGB Mode 3, Mode 4 stays a future optimisation, DDR-1 OPEN)
  x = 0          FLAG      1 px   0x03E0
  x = 1..54      STRIP-L  54 px   <- the CANONICAL WITNESS lives on local row 0
  x = 55         GUARD     1 px   0x0000
  x = 56..183    CONTENT 128 px   32 cells of 4
  x = 184        GUARD     1 px
  x = 185..238   STRIP-R  54 px
  x = 239        GUARD     1 px
                --------------
                 240 px, tiled exactly once — machine-checked

  block b = rows 4b .. 4b+3, b = 0..39; 40 x 4 = 160 rows

SYMBOLS (AGB BGR555, bit 15 NEVER written by the stimulus)
  ZERO  0x0000   ONE 0x7FFF   FLAG 0x03E0   GUARD 0x0000
  every one is a FIXED POINT of the confirmed outer-group exchange, so the ID
  decode does not depend on U-GBP-011's result at all

STRIP WORD, 54 bits, MSB-first
  SYNC         8   0xB2
  FRAME_ID    24
  BLOCK_INDEX  6
  STATUS       8   bit7 FAULT | bits6..0 VMARGIN
  CRC8         8   over the 38 bits FRAME_ID || BLOCK_INDEX || STATUS

  STATUS is INSIDE the CRC because it gates the decisive claim: the bit must be
  as protected as the ID it qualifies.

STRIP POLARITY AND ORDER
  row 4b+0 / 4b+2 : L = plain,    R = reversed + inverted
  row 4b+1 / 4b+3 : L = inverted, R = reversed

COUNTER
  FRAME_ID starts at 0 at cartridge power-on, +1 per AGB VBlank, 24 bits,
  wraps 0xFFFFFF -> 0x000000. Wrap horizon 2^24 / 59.737 Hz = 77.98 hours.

CONTENT
  background(x,y) = PAL16[((x-56)>>2 + y>>2) & 15], PAL16[k] = 0x0842*k
  barpos(f,b)     = (f + 8*b) mod 31,  bar = 2 cells of 4 px, colour 0x7C00
  gcd(8,31) = 1 and 31 is prime, so b = 0..30 give all 31 phases and b = 31..39
  necessarily repeat nine of them. The bar is a FRESHNESS witness, never an
  identifier. The period was 35 while CONTENT was 144 px; the STATUS field cost
  8 columns per strip and CONTENT shrank to 128 px.
```

#### V5.33.5 CRC-8 — specification and the FROZEN vectors

```text
register 8 bits · poly 0x07 · init 0xFF · xorout 0x00 · no reflection
input    MSB-first: FRAME_ID[23..0] || BLOCK_INDEX[5..0] || STATUS[7..0] = 38 bits
         NO zero augmentation
per bit  fb = ((crc>>7)&1) ^ inbit ; crc = ((crc<<1)&0xFF) ^ (0x07 if fb else 0)
result   the final register value, painted MSB-first
```

| FRAME_ID | BLOCK_INDEX | STATUS | CRC8 |
| --- | --- | --- | --- |
| `0x000000` | 0 | `0x7F` | `0xB6` |
| `0x000000` | 39 | `0x7F` | `0x73` |
| `0x000001` | 0 | `0x7F` | `0xED` |
| `0x000001` | 39 | `0x7F` | `0x28` |
| `0xFFFFFF` | 0 | `0x7F` | `0xC7` |
| `0xFFFFFF` | 39 | `0x7F` | `0x02` |
| `0x123456` | 17 | `0x42` | `0xD3` |
| `0x000000` | 0 | `0x00` | `0xCC` |
| `0x000000` | 0 | `0x80` | `0x45` |
| `0xFFFFFF` | 39 | `0xFF` | `0x8B` |

A single-bit flip anywhere in the 38-bit payload always changes the CRC, tested
exhaustively over all 38 positions for three payloads. **The old 30-bit vectors
of §V5.32.3 are retired, not carried forward** — the payload changed.

#### V5.33.6 Canonical decode rules — lossless in, structured out

```text
for each of the 54 witness words:
    flag15   = word16 & 0x8000        <- split off, REPORTED, never consumed
    colour15 = word16 & 0x7FFF
    ZERO  iff colour15 == 0x0000
    ONE   iff colour15 == 0x7FFF
    OTHER otherwise -> INVALID_CANONICAL_STRIP (reason "symbol")

then, in order, any failure ending the decode:
    SYNC must equal 0xB2                     -> reason "sync"
    CRC8 must match the 38-bit payload       -> reason "crc"
    BLOCK_INDEX must equal the delivery slot -> MISPLACED_BLOCK_INDEX

FRAME_ID and STATUS are emitted ONLY if everything above passed.
Bit 15 can never change a decoded bit and can never fail the CRC. An unexpected
flag coordinate is a U-GBP-034 observation, reported separately.
```

**CRC-8 is internal consistency, never authority.** The authority is the 54
preserved word16 themselves. The phrase "the CRC proves equality" is forbidden.

#### V5.33.7 What the decisive run proves — three separate things

```text
A  FRAME-ID SEQUENCE INTEGRITY    the observed IDs are contiguous and ordered
B  BLOCK COMPOSITION INTEGRITY    all 40 blocks of a frame carry ONE frame ID
C  BLOCK POSITION INTEGRITY       every BLOCK_INDEX equals its delivery slot

NOT proved: pixel fidelity outside the strip. That is a different question and
is not answered by this experiment.
```

Vocabulary, factual only — **"SOURCE LOSS" is not a name for raw data**:

```text
OBSERVED_ID_CONTIGUOUS · OBSERVED_ID_GAP · OBSERVED_DUPLICATE_ID
OBSERVED_REORDER · UNRESOLVED_HALF_RANGE
MIXED_BLOCK_IDS · MISPLACED_BLOCK_INDEX · INVALID_CANONICAL_STRIP
```

The strongest permitted interpretation of a gap: *"one or more source frame IDs
expected by the deterministic sequence were not observed at the pre-publication
capture layer."* **No mechanism is attributed.**

Modular classification, unchanged from §V5.32.4 and re-tested here, with
`delta == 2^23` remaining `UNRESOLVED_HALF_RANGE` and never a gap.

#### V5.33.8 The status delay, and the decisive population

```text
per VBlank N: read timer+VCOUNT; f := N; paint strips with the latch AS IT
STANDS (reflecting updates 0..N-1); paint bars; read timer+VCOUNT; fold into
the latch, which now reflects update N.

=> STATUS carried by frame f certifies updates 0 .. f-1, NEVER f itself.
```

For observed intact frames **A..Z**: the latch is sticky, so frame Z's STATUS
already covers every update from 0 to Z−1 at once; frame **Z**'s own update is
certified by nothing. **The decisive frames are A..Z−1 and the decisive
transitions are A→A+1 … (Z−2)→(Z−1).** For ~1 792 observed frames that is
~1 790 decisive transitions: one lost to the trailing edge, one to the status
delay. Both exclusions are reported by the analyzer, never silently dropped.

#### V5.33.9 Witness capacity — derived, and `witness_store_full`

```text
expected 30 s population       30 x 59.737 Hz = 1792.1 frames
+ 10 % (clock tolerance, and the capture window is TICK-bounded, not
  frame-bounded, so the population is not exactly 1792)      = 1971.3
smallest power of two above that                             = 2048

capacity 2048 frames x 4 320 B = 8 847 360 B = 8.44 MiB
stream-0003 commits 10.03 MiB of 24.00 and leaves 13.97 MiB free
a future candidate would commit 18.47 MiB and leave 5.53 MiB

witness_store_full  -> the run STOPS storing; the decisive claim becomes
                       INCONCLUSIVE. Nothing is ever silently overwritten.
```

60 s would need 15.48 MB and does **not** fit — which is why the first decisive
run is 30 s and why the safety cap cannot be used as the capacity basis.

#### V5.33.10 Where the copy would happen, and what it costs

The same scientific layer already frozen in §V5.32.1: from `blk` in
`gbp_vstate_probe.c` beside `gbp_vsig_block()`, **before**
`gbp_vqueue_publish()`. Per block: gather 54 word16 from the first line —
**108 loads, 54 stores, 216 of the block's 3 840 source bytes (5.6 %)**, against
a `gbp_vsig_block()` that already reads all 3 840. **This must be MEASURED on
hardware before anyone calls it timing-safe.**

#### V5.33.11 Stimulus-aware, said plainly

**Canonical strip retention is STIMULUS-AWARE instrumentation.** A fixed ROI at
`x ∈ [1,54]`, local row 0, is stimulus knowledge even though it decodes nothing.
It is acceptable here because this is a specific scientific POC, and only under
these conditions:

```text
does not change the GBP protocol
does not decide anything online
does not decode FRAME_ID online
preserves losslessly a PRE-REGISTERED ROI and nothing else
the analyzer stays offline
```

It must **not** be promoted into the generic runtime without a separate decision.

**Option D reclassified:** a per-block CRC-32 would be a *generic diagnostic
fingerprint*. It is **not** a decisive witness, **not** lossless, and **does not
replace** the canonical strip. Not implemented — avoiding scope creep.

#### V5.33.12 VBlank estimate — final layout, still an ESTIMATE

```text
strip pixels/frame  17 280   54 bits x 2 strips x 4 rows x 40 blocks
bar pixels/frame     2 560
total               19 840 px = 9 920 32-bit VRAM stores x 2 cycles = 19 840
VBlank budget       83 776 cycles  ->  23.7 % on VRAM stores alone

NOT counted, which is why this is an estimate:
  loop and address arithmetic over 320 inner runs
  payload/CRC generation (crc8(frame_id) folded once, then 40 table lookups)
  bit-to-symbol expansion, 54 bits x 8 copies = 432 decisions per frame
  timer and VCOUNT instrumentation, 4 MMIO reads per frame
  `mod 31` MUST NOT become a divide: ARM7TDMI has no divide instruction, so it
  is a running counter with compare-and-subtract
```

What the ROM must measure and carry: **update ticks (current and maximum),
VCOUNT before and after, and the overrun latch.** Only `FAULT` and `VMARGIN`
reach the payload; the rest forms them.

#### V5.33.13 The first decisive run

```text
duration 30 s (proposal, not frozen by precedent)
~1 792 source periods · ~1 791 internal transitions available
~1 790 DECISIVE transitions after the edge and the status delay
witness 7.74 MB of the 8.44 MiB capacity

permitted result:
  "0 OBSERVED_ID_GAP among N observable decisive transitions"
NOT permitted:
  any universal loss-rate guarantee, or any statement about the edges
```

#### V5.33.14 Long-run

FRAME_ID stays 24 bits, wrap 77.98 h, and the modular classification already
handles it. The 30 s witness retention does **not** have to solve long-run now;
the frame format does not prevent future external storage.

#### V5.33.15 VERDICT

```text
A — DESIGN READY TO FREEZE

resolved: observable claim · canonical witness · witness capacity · exact final
payload and layout · source-update validation and latch · status delay ·
classification rules · memory feasibility.

FROZEN as format version OGBPIDX1: layout, symbols, strip word, CRC parameters
and vectors, counter width and wrap, canonical witness coordinates,
classification rules, stimulus validity rules.

STILL OPEN and deliberately so:
  DDR-1  Mode 4 page flipping — Mode 3 keeps the baseline because it is the only
         mode with physical colour evidence; Mode 4 is a future optimisation
  the VBlank figure is an ESTIMATE until the ROM measures it on hardware

The ROM is NOT written in this round. The next checkpoint is its implementation,
and it does not block the first physical smoke of stream-0003.
```

**Evidence classes used above:** FACT — the consumed projection, the geometry,
the outer-group exchange, the GBATEK timing and VCOUNT figures. CORROBORATED —
the ≈59.727 Hz AGB rate. DESIGN DECISION — every constant of OGBPIDX1. HYPOTHESIS
— that a mixed frame, if observed, was mixed on the AGB→GBP→GameCube path;
the layer is not attributable by this experiment. UNKNOWN — U-GBP-029 and
U-GBP-034, neither of which this experiment depends on or resolves.

### V5.34 FIRST PHYSICAL GBP STREAM SMOKE — `stream-0003`, executed 2026-09-18 — **REAL CARTRIDGE VIDEO REACHED THE SCREEN**

```text
STATUS OF THE RUN

  PHYSICAL EXECUTION                     yes, exact stream-0003
  GBP SERVICE                            OPERATIONAL, 280 621 conserved cycles
  STREAM CONSUMER / DISPLAY PATH         PHYSICALLY EXERCISED end to end
  OWNERSHIP INVARIANTS                   HELD, 246 548 checks, 0 failures
  PUMP                                   PHYSICALLY MEASURED for the first time
  REAL CARTRIDGE VIDEO ON SCREEN         yes (operator observation + photographs)
  SOURCE-FRAME CONTINUITY                NOT YET DECIDABLE — no indexed stimulus

  TWO SOFTWARE DEFECTS FOUND. Both are in src/gbp, both are reported and NOT
  fixed here, and one of them cost 12.3 % of the publishable frames.
```

#### V5.34.1 Log identity, verified from the file

```text
logs/GBP-VIDEO-004_stream-0003.log
  88 705 B   sha256 62996c7d4fb282b1833c1d53060828baf3395d40154922c92e0add63004fa4ec
  test_id=GBP-VIDEO-004  build_id=stream-0003  commit=03b32a9
  libogc=libogc2 r2442.094b250  capture_s=30  safety_s=60
  lines=677  dropped=0  truncated=0  power_cycle_required=1  sidecar=none
```

Preserved as ignored local copies in `captures/local/`, with the operator's two
photographs (`…-1.jpeg` `564cb781…`, `…-2.jpeg` `326fbdd6…`).

#### V5.34.2 The storage fix is physically validated

```text
ENVSTORE frames=16384/16384 events=4096/4096 raw_ring=737280/552960 slots=4/3
         episode_raw=2949120/2949120 audio_raw=12288/12288
         configured_bytes=7106560 required_bytes=6922240 fault=- ok=1
```

**FACT: `stream-0003`'s storage preflight passed physically.** The `stream-0002`
pre-service blocker is resolved. **`stream-0002` is not re-interpreted**: it
still stands as PHYSICALLY EXECUTED, ABORTED PRE-SERVICE.

#### V5.34.3 Service conservation — FACT

```text
unmasks = deliveries = acks = rearms = 280 621      exact, all four equal
VIDEO   105 841 selected / 105 841 completed        every selected read completed
AUDIO   181 481 drained
timeouts=0 busy=0 overflow=0 uncertain=0 errors=0 transport_ok=1
transfers=1 129 255  bulk_transfers=287 322  bulk_bytes=1 149 775 616
```

`105 841 + 181 481 = 287 322 = bulk_transfers`, which exceeds `deliveries` by
6 701: **6 701 deliveries carried both an AUDIO and a VIDEO block**, the
multi-source cause the service path already handles. The identity is
`bulk_transfers = video + audio ≥ deliveries`, and it holds exactly.

**FACT: 280 621 consecutive service cycles conserved unmask→deliver→ack→re-arm
with zero transport faults of any kind.** This is by far the longest such run in
the project — `vstate-0004` conserved 2 228 013 IRQ writes over 175 s without a
consumer; this is the first time it was done **with a consumer, a converter and
a GX display attached**.

#### V5.34.4 The capture window — 44.323 s wall for 30.002 s of science

```text
CLOCKSEC capture_s=44.323 baseline_s=0.066 valid_s=30.002 safety_s=49.430
         target_s=30 limit_s=60
```

Traced to `gbp_vstate.c:884-892`: the scientific clock adds **each counted
frame's own span** `t_last_block − t_first_block` — the interval from a frame's
first VIDEO block to its last — and **never** the idle between the last block of
one frame and the first block of the next. The code comment says so: *"Its own
span is used, which slightly understates the period — the conservative
direction."* Only clean complete frames after `baseline_valid` count.

2 619 counted frames over 30.002 s ⇒ a mean intra-frame span of **11.46 ms**
against a **16.74 ms** frame period; the 5.28 ms/frame difference is the
inter-frame idle, which is exactly what is not counted.

**This is not a streaming effect.** `vstate-0004` shows the same relationship:
175.848 s wall for 120.009 s valid, ratio **1.465**; `stream-0003` 44.323 /
30.002 = **1.477**. **44.323 s is wall time and must never be quoted as the
scientific duration.**

#### V5.34.5 Frame assembly — and why the 13 incomplete frames are NOT source loss

```text
FRAMECAP  frames=2648 complete=2635 incomplete=13 resync=26 anomaly_region=13
          counted=2619 blocks=105841 pre_boundary=0 store_full=0
INTERVALS 1:1, 33:1, 34:3, 38:8, 40:2635
```

2 635 + 13 = 2 648 ✓. The interval histogram sums to 105 840 blocks; the 105 841st
was in the interval still open when the capture stopped ✓.

**Where they are is the whole answer.** Every one of the 13 incomplete intervals
occurred in the first 408 frames of 2 648 — the first ~6.9 s of a 44.3 s capture —
and **zero** occurred in the remaining 2 240 frames:

```text
frame    1  blocks  1     (the first partial interval, before the assembler had an anchor)
frames  11, 14, 18        34, 38, 38
frames 217, 220, 223      34, 38, 38
frames 251, 254, 257      34, 38, 38
frames 402, 405, 408      33, 38, 38
```

Four clusters of exactly three, each with the same 34/38/38 shape.

**The physically validated non-streaming baseline shows the same thing.**
`vstate-0004` (120 s target, no consumer): `INTERVALS 30:1, 34:4, 38:7, 40:10491`
with incomplete frames at indices **1, 32, 35, 38, 92, 95, 98, 192, 196** — the
same 34/38/38 clusters, also confined to the first ~200 of 10 503 frames.

| | `vstate-0004` (no streaming) | `stream-0003` (streaming) |
| --- | --- | --- |
| capture | 175.848 s | 44.323 s |
| frames | 10 503 | 2 648 |
| incomplete | 12 | 13 |
| resync | 24 | 26 |
| shapes | 34/38/38 clusters | 34/38/38 clusters |
| where | first ~200 frames | first 408 frames |

**CORROBORATED: the incomplete intervals and resyncs are a startup-region
phenomenon with the same signature in a physically validated run that had no
streaming consumer at all. Streaming did not measurably change them.** The
absolute counts are nearly equal across a 4× duration difference, which is what a
fixed startup cost looks like and is not what a per-frame rate looks like.

**What can and cannot be said:**

```text
FACT          13 intervals carried fewer than 40 VIDEO blocks between two
              observed boundaries, all within the first 408 frames
CORROBORATED  the same signature appears in vstate-0004 without streaming
UNKNOWN       whether blocks were lost, or boundaries were observed early/late,
              or causes coalesced. NOTHING in this log distinguishes them.
NOT PERMITTED calling any of them "source frame loss" — there is no ground
              truth in this run, which is precisely why OGBPIDX1 exists
```

#### V5.34.6 **DEFECT P2 — 324 frames refused because two flags share one bit**

```text
STREAMSRC  closed=2648 complete=2298 incomplete=13 quarantined=324 anomaly=13
           published=2298
STRUCTURED episodes=324 stable=324 unstable=0
SEMANTIC   maj_extra=0 quarantined=0       ← the R3 machinery saw NOTHING
```

The classification equation from code (`gbp_vqueue.c:gbp_vqueue_classify`) is
exact and closes: `2 298 + 13 + 324 + 13 = 2 648`, and
`2 635 − 324 − 13 = 2 298`. The question is why 324 complete 40-block frames were
quarantined while the R3 machinery reported **zero** majority-extra blocks.

**Root cause, in two lines of the same header:**

```c
/* src/gbp/gbp_vstate.h:109 */
#define GBP_VSTATE_F_MAJORITY_EXTRA  0x1000u   /* §R3.12 quarantine */
/* src/gbp/gbp_vstate.h:121 */
#define GBP_VSTATE_F_EPISODE_STABLE  0x1000u   /* the frame that closed an episode as stable */
```

**The same bit, in the same `GBP_VSTATE_F_*` frame-flag word.**
`gbp_vstate.c:1052` writes `f->flags |= GBP_VSTATE_F_EPISODE_STABLE`, and
`gbp_vqueue_classify()` tests `flags & GBP_VSTATE_F_MAJORITY_EXTRA` **first** and
returns `QUARANTINED`. So **every frame that closed a structured-change episode
as stable was misread as containing a majority-extra block and refused
publication.**

The physical arithmetic is exact: **324 episodes, all stable → 324 quarantined.**

**Answering §7's question directly: YES.** The quarantine is the VSTATE
structured-change scientific machinery reacting to ordinary changing cartridge
video — a real game repaints constantly, so episodes open and close continuously
(324 in 44.3 s ≈ 7.3/s, against **9 in 175.8 s** for `vstate-0004`'s far more
static picture). But the *mechanism* by which those frames were dropped is the
bit collision, not a deliberate policy.

Classification of the behaviour:

```text
A intentional temporary POC behaviour   NO — nothing intended this
B unsuitable for sustained video        YES — it discards 12.30 % of complete
                                        frames for a reason that does not exist
C required for protocol correctness     NO — the R3 quarantine it imitates never
                                        fired (maj_extra=0)
```

**Quantified effect on cadence:** 2 298 published over 44.323 s = **51.85 Hz**,
against 2 648 assembled frames over the same window = **59.74 Hz**. The measured
`publish_mean` of 780 519 ticks = **19.27 ms = 51.89 Hz** confirms it
independently. **The defect costs 13.2 % of the presentation cadence.**

**NOT FIXED HERE.** This round is not authorised to change `src/`. The proposal
is §V5.34.14.

#### V5.34.7 The streaming path physically ran

```text
STREAMCONS taken=2298 converted=2298 presented=2286 overrun=0
           dropped_before_convert=0 repeats=12 no_cpu_texture=0
           abandoned_no_raw=0
```

Every published frame was taken; every taken frame was converted; **no frame was
ever superseded in the mailbox and none overran the generation guard.** The
consumer kept up completely.

**FACT: PHYSICAL SUSTAINED STREAMING PATH EXERCISED** — published → mailbox take
→ 40-tile-row conversion → GX submit → draw-done → XFB present, 2 298 times over
44.3 s on real hardware with a real cartridge.

**NOT claimed: zero source-frame loss.** That requires OGBPIDX1 and does not
exist yet.

#### V5.34.8 **DEFECT P1 — `balanced=0` is an accounting predicate, not a conservation failure**

```text
converted=2298  presented=2286  overrun=0  repeats=12  balanced=0
xfb_presents=2287  xfb_skipped=12
```

R1 is not applicable: `STREAMSELFTEST sci_clean=1` and `own_presents=1` — the
self-test is isolated and its presentation is counted separately.

`gbp_vqueue_balanced()` asserts
`consumer_frames_converted == consumer_frames_presented + consumer_slot_overrun`.
**A converted frame has THREE terminal states, not two**, and the third is
reachable by design:

```text
main.c submit_ready(), after a successful gbp_vpresent_submit():
  xfb = gbp_vpresent_xfb_target(...)
  if (xfb >= 0) { GX_CopyDisp; VIDEO_SetNextFramebuffer; note_presented(); }
  else          { GX_Flush();  note_repeat(); }          <- the third state
```

The `else` branch is taken when **both** framebuffers are spoken for — one being
scanned out, one already handed over. The texture WAS submitted and drawn; only
the XFB copy was skipped, so the screen kept the previous image. That is
`display_frames_repeated`, and it is a legitimate terminal state of a converted
frame.

```text
the correct identity, proved from the state transitions:
    converted == presented + overrun + repeated
    2298     == 2286      + 0       + 12        ✓ exactly
```

Every branch is accounted: an overrun frame is abandoned before `submit_ready` is
reached; a refused submit (`blocked_inflight`) leaves the buffer READY to be
re-offered and contributes nothing until it is submitted once; a submitted
buffer reaches exactly one of `note_presented` / `note_repeat`.

**Classification: B — the predicate is missing a legitimate terminal state.**
Not a conservation failure. The run's data conserves perfectly under the correct
identity, which is locked as a unit test
(`test_the_physical_stream0003_counters_conserve`).

**NOT FIXED HERE.**

#### V5.34.9 XFB repeats and skips — exact correspondence

```text
xfb_presents 2287 == scientific presented 2286 + self-test own_presents 1   ✓
xfb_skipped    12 == display repeats 12                                     ✓
```

12 skips in 2 298 presentations = **0.52 %**. These are the expected pacing
outcome of a **two-framebuffer, never-wait** policy against an AGB source and a
VI that do not share a cadence (§V5.6 predicted the beat before the run). The
design refuses to wait for a retrace, so when both buffers are spoken for it
skips the copy and keeps the previous image.

**They are display repeats, not source losses**, and the vocabulary is
pre-registered: `repeated_on_display`, never "dropped". Whether a third
framebuffer would remove them is an open UI question, not a defect.

#### V5.34.10 Ownership — promoted from software-only to PHYSICAL

```text
STREAMOWN  acquire=120975 no_texture=0 fills=2299/120975 abandoned=118676
           submit=2299/2299 blocked_inflight=0 blocked_shutdown=0
STREAMGX   drawdone=2299 spurious=0 releases=2299 consistent_at_end=1
           inflight_at_end=0 drained=0 cb_restored=1
STREAMINV  checks=246548 failures=0 main=0/244249 isr=0/2299 consistent_at_end=1
```

`2 299 = 2 298 scientific + 1 self-test` for submits, draw-dones and releases —
the three are equal and `spurious=0`. `244 249 + 2 299 = 246 548` ✓.

**Promoted to PHYSICAL FACT:**

```text
the one-token rule held on hardware              2299 submits, 0 blocked_inflight
the callback released exactly one buffer         2299 releases, 0 spurious
the ownership invariants held THROUGHOUT         246 548 checks, 0 failures,
                                                 main side and interrupt side both
the teardown restored the previous callback      cb_restored=1
```

R8 is what makes the third line sayable: `stream-0002` could only have reported
the final instant. **This is the first physical evidence for the `gbp_vpresent`
machine, and it is the strongest kind — a latch that would have recorded a
violation that healed, and recorded none.**

`STREAMOWN abandoned=118676` is the designed idle path: the pump acquires a
texture, finds no new frame in the mailbox, and gives it straight back
(`2 299 + 118 676 = 120 975` ✓).

#### V5.34.11 The pump, measured for the first time

```text
STREAMPUMP  calls=280621 slices=91920 completed=2298
            skipped_cause_pending=70025 pending_before=70025
            pending_after=21527 arrived_during=21527
STREAMPUMPT ticks_min=1129 ticks_max=1663 ticks_mean=1361 n=91920
            tb_hz=40 500 000
```

```text
min   1129 ticks = 27.8765 us
max   1663 ticks = 41.0617 us
mean  1361 ticks = 33.6049 us
```

```text
skipped_cause_pending / calls = 70 025 / 280 621 = 24.95 %
arrived_during / slices       = 21 527 /  91 920 = 23.42 %
slices / calls                = 91 920 / 280 621 = 32.76 %
slices per completed frame    = 91 920 /   2 298 = 40.0   (exactly one tile row each)
```

**A quarter of all pump calls found a GBP cause already latched and yielded the
cycle**, which is the precheck doing precisely what §V5.27.4 built it for. A
further 23.4 % of the slices that did run saw a cause appear during them.

**`arrived_during` is a coincidence count and no causality may be read from it**
— the AGB delivers on its own schedule and a 33.6 µs slice inside a ~78 µs
service window will often overlap one.

Pacing, for the record: `publish_mean` 780 519 ticks = **19.27 ms**,
`convert_mean` 54 478 ticks = **1.345 ms** for a whole 40-row frame conversion.

#### V5.34.12 Pump safety — the strongest justified wording

```text
JUSTIFIED:  "the pump did not cause observable transport failure in this run"
            timeouts=0, busy=0, overflow=0, uncertain=0, errors=0,
            transport_ok=1, and unmask=deliver=ack=re-arm conserved exactly
            across 280 621 cycles

STILL UNKNOWN: its effect on frame completeness and source continuity.
            13 incomplete intervals and 26 resyncs exist; the baseline shows
            the same signature WITHOUT a pump, which is evidence but not proof
            of independence, and this run has no ground truth.

NOT JUSTIFIED: "the pump placement is timing-safe". One run, one cartridge,
            one 44 s window. The classification moves from PLAUSIBLE BUT
            UNMEASURED to MEASURED AND WITHOUT OBSERVED TRANSPORT EFFECT.
```

#### V5.34.13 R3 under streaming, and flag15

```text
SEMANTIC  total=42 serviced=42 other=0 non_source=0 disc_extra=42 maj_extra=0
          both=0 quarantined=0 deferred=0
SEMANTIC2 preserved=42 fu_present=42 fu_absent=0 fu_no_next=0 fu_unknown=0
```

42 R3 disagreements, **all** of class `disc_extra`, **all** serviced, **all**
with a follow-up cause present. Zero majority-extra, zero deferred, zero
unknown. This replicates the R3 pattern under a workload the previous runs did
not have — a real game's continuously changing video — and the follow-up
behaviour was 42/42 consistent.

**CORROBORATED, and the mechanism stays UNKNOWN. U-GBP-033 remains OPEN.**

```text
STREAMFLAG15 last_count=1 first_x=0 first_y=0
```

One bit-15 word per frame, at (0,0), consistent with every previous physical run.
**U-GBP-034 stays OPEN** — this observes position and count, not origin.

#### V5.34.14 `power_cycle_required=1` — NOT a new finding

`power_cycle_required` is set to **1 before every IRQ register write**
(`gbp_initirqa_probe.c:409` for the STOP word, `gbp_vstate_probe.c:1329` for each
ACK, `:1437` for each RE-ARM). It is a **latched marker meaning "this run wrote
the device's IRQ register, so its state may not be fully acknowledged"** —
exactly `CLAUDE.md` §18's standing rule. This run performed **561 244** such
writes, all completed, `uncertain_writes=0`.

The `FINAL` snapshot is taken at step 9 of the teardown, explicitly *"under the
restored AR_INFO"* (`gbp_initirqa_probe.c:483`), i.e. **after** `ARINFO restore
value=0043 readback=0043 ok=1` put the expansion window back to the original size
code. Under the original AR_INFO the GBP register window is not the experimental
one, so `control=00` and `irq=9292` are **not comparable** with values read under
`ARINFO exp value=005b`.

**The physically validated baselines settle it:**

| run | status | FINAL | `power_cycle_required` |
| --- | --- | --- | --- |
| `vstate-0004` (validated) | teardown accepted | `control=00 irq=9090` | 1 |
| `color-0002` (validated) | teardown accepted | `control=00 irq=9292` | 1 |
| `stream-0003` | — | `control=00 irq=9292` | 1 |

`stream-0003` reproduces `color-0002`'s FINAL values **exactly**. Intermediate
teardown reported `control_restore_ok=1 irq_stop_write_ok=1 irq_stop_readback_ok=1
pi_cleanup_ok=1 pi_cleanup_sticky=0 arinfo_restore_ok=1 handler_restored=1
mask_ok=1 intmr_final=00000ffa pi_sticky_final=0`.

**FACT: `power_cycle_required=1` is a by-construction latch, reproduced
identically by two physically validated runs, and is not evidence that the
hardware remained in a state requiring a power cycle.** The operator instruction
is unchanged — **power-cycle the GameCube/GBP before the next physical run** —
because it is the standing procedure, not because of a new problem.

#### V5.34.15 GX teardown — `drained=0` is the correct outcome

```c
if (gbp_vpresent_inflight(&present)) { GX_DrawDone(); gx_drained_at_teardown = 1; }
```

With `inflight_at_end=0` the branch is **not taken**, so `drained=0` is exactly
right: there was no token to drain, because all 2 299 had already been consumed
(`drawdone=2299 releases=2299 spurious=0`). Reading `drained=0` as a failure
would be reading the absence of a needed rescue as the absence of a rescue.

#### V5.34.16 What the screen showed

```text
LOG FACT              2 286 scientific GX presentations occurred; ownership
                      invariants held; 105 841 VIDEO transfers completed;
                      2 298 frames were published, converted and submitted

OPERATOR OBSERVATION  (supplied with two photographs, preserved in
                      captures/local/, EMULATOR-free, physical)
                      1. a rainbow/checkerboard pattern appeared first
                      2. then the actual cartridge game
                      3. the Game Boy boot logo was NOT seen
                      4. the game image looked normal
                      5. the picture was small and centred, near native size
```

**19A.1 — the startup image is the display self-test, confirmed from source.**
`display_selftest()` writes
`w = ((x >> 3) << 10) | ((y >> 3) << 5) | ((x ^ y) & 0x1F)` and presents it as
`GX_TF_RGB5A3`, where bits 14-10 are R, 9-5 G, 4-0 B. So **R = x>>3** (0..29
left→right in 8-pixel bands), **G = y>>3** (0..19 top→bottom in 8-pixel bands)
and **B = (x^y)&0x1F** (a fine XOR checkerboard). The photograph shows exactly
that: blue at top-left, red/pink at top-right, green at bottom-left, orange at
bottom-right, over an 8-pixel checkerboard of 30 × 20 cells — the frozen
240/8 × 160/8 geometry.

**CORROBORATED: the physical display self-test was not only counted in the log
(`ok=1 converted=1 released=1 own_presents=1`) but was visibly presented on the
real GameCube output.** Confirmed from the rendering code, not inferred from
appearance.

**19A.2 — the missing boot logo is EXPECTED FOR THIS POC.** The chronology:

```text
console power-on  -> the GBP and the cartridge start executing IMMEDIATELY
                     (the AGB is powered by the GameCube)
   ... Swiss boot, menu navigation, DOL load: OPERATOR-PACED, unbounded ...
DOL start         -> video_setup, gx_setup, display_selftest (the checkerboard)
                  -> on-screen banner, then
PREHANDLERWAIT    -> 5 000 ms with the AGB running and PI masked (GBP-HW-120)
003A sequence     -> CONTROL transform, handler install, first unmask
first delivery    -> the first VIDEO blocks reach the assembler
first closed frame-> EV seq=2 at f=0, immediately after capture_start
first presentation-> the first scientific GX present
```

The AGB's boot-logo sequence runs in the first ~2 s after cartridge power-on —
**before Swiss had even finished loading the DOL**. Open-GBP could not have
presented it, and this is a property of the POC's startup order, not evidence of
anything being dropped.

**No number of skipped source frames may be inferred from elapsed time.** That is
precisely the leading-edge limitation OGBPIDX1 pre-registered (§V5.33.2): frames
before the first observed intact ID are outside the observable population.

**19A.3 — the small centred image is by design, confirmed from source.**
`GX_InitTexObj(..., GBP_VPIX_WIDTH, GBP_VPIX_HEIGHT, GX_TF_RGB5A3, ...)` is
240×160 with `GX_NEAR` filtering, and `draw_quad()` emits a quad at
`x0 = (rmode->fbWidth − 240)/2`, `y0 = (rmode->efbHeight − 160)/2`. For the NTSC
480i mode that is **x0 = 200, y0 = 160, covering 37.5 % of the width, 33.3 % of
the height and 12.5 % of the area**. §V5.16 says it in as many words: *"Native
240x160, centred, unscaled. Scaling and aspect are Phase 9 policy and are
deliberately absent."*

**FACT FROM IMPLEMENTATION: `stream-0003` intentionally presents native-size
240×160 video, centred. OPERATOR OBSERVATION: the physical result appeared
correspondingly small and centred. This is NOT a rendering defect.**

**19A.4 — visual correctness, scoped.** The photographs show a rendered cartridge
title screen with recognisable structured graphics and **no gross colour-channel
swap** — yellow reads as yellow, blue as blue, which is what the confirmed
outer-group exchange (GBP-HW-131) plus `GX_REPLACE` should produce. They do
**not** prove zero tearing, correct pacing, zero frame loss, zero transient
corruption, perfect colour fidelity or source-frame continuity. Those stay
separate and open.

**19A.5 — the milestone, scoped exactly:**

```text
PHYSICAL REAL-CARTRIDGE VIDEO OUTPUT ACHIEVED

  scope: real DOL-017 Game Boy Player · real GBA cartridge · Open-GBP runtime ·
         physical GameCube video output · native-size 240x160 presentation ·
         sustained for this 44.3 s smoke run

  DOES NOT IMPLY: GBP-VIDEO-004 complete · zero source-frame loss ·
                  a universally timing-safe pump · final scaling or UI ·
                  correct pacing · absence of tearing
```

**19A.6 — photographs.** Recorded as OPERATOR/VISUAL evidence, kept in
`captures/local/` (ignored by Git, per the raw-evidence policy), hashes in
§V5.34.1. **They are not quantitative timing evidence and no scientific
classification above was changed because a photograph looks correct.**

#### V5.34.17 The two defects, and the runtime fix required before the next run

```text
P2  BIT COLLISION            HIGH   F_EPISODE_STABLE and F_MAJORITY_EXTRA are
    src/gbp/gbp_vstate.h:109/121  both 0x1000 in the same frame-flag word.
    Effect: 324 of 2 635 complete frames (12.30 %) refused, cadence 59.74 ->
    51.85 Hz. PROPOSED FIX: move F_EPISODE_STABLE to a free bit (0x4000 or
    0x8000 are unused in the frame word) — a one-line header change plus a test
    that the two constants differ. NOT APPLIED.

P1  ACCOUNTING PREDICATE     MEDIUM gbp_vqueue_balanced() omits the `repeated`
    src/gbp/gbp_vqueue.c:197      terminal state. PROPOSED FIX: assert
    converted == presented + overrun + repeated. NOT APPLIED.
```

**Both are `src/gbp` changes and this round is not authorised to make them.**
Both are locked as passing unit tests that assert the CURRENT behaviour together
with the arithmetic showing why it is wrong, so a future fix must be deliberate.

**A runtime fix IS required before the next physical run** — P2 discards 12 % of
the frames for a reason that does not exist, and no pacing or continuity
measurement made with it in place can be trusted.

### V5.35 `stimulus/agb-indexed` — the OGBPIDX1 ROM and analyzer, implemented — 2026-09-18

The contract frozen at §V5.33 is now implemented. **No hardware ran, `src/` and
`poc/` are untouched, and `stream-0003` is unchanged** (471 648 B,
`2f8e362e…199e3`, Swiss copy byte-identical).

#### V5.35.1 Identity

```text
stimulus/agb-indexed          stimulus_id indexed-0001
build/stimulus/agb-indexed/agb-indexed.gba
  2 460 B   sha256 379df0f7019ef7f1330bd4ad55274bde062a69d03d1c8cc1dc2a01018bdbc543
header  title OPENGBPINDEX · code IGBP · maker OG · complement 0x16
toolchain arm-none-eabi-gcc (devkitARM) 15.2.0, -O2 -Wall -Wextra -Wpedantic
          -Wshadow -Wconversion, gba.specs crt0, no library
build     make stimulus-indexed
status    IMPLEMENTED, NOT PHYSICALLY EXECUTED
```

**The Nintendo logo area is empty**, so an AGB cartridge boot would refuse this
image — the same standing limitation `agb-color-bars` carries. Delivery to the
Game Boy Player's internal AGB remains the EZ-Flash Omega DE NOR / Mode B route
(§V5.18); this repository does not supply the logo bytes.

#### V5.35.2 Architecture

One translation unit, one loop, no interrupts. The VBlank edge is **polled**, not
interrupt-driven, so nothing can preempt an update and nothing else can ever
write VRAM. Frame 0 is painted **complete before `REG_DISPCNT` selects mode 3**,
so no partially initialised picture is ever displayed (§30).

```text
boot      clear BLDCNT/BLDALPHA/BLDY/MOSAIC · IME=IE=0, IF=0xFFFF
          512 OAM halfwords := 0x0200 (every object disabled)
          Timer 0: TM0CNT_H = 0x0081 — enable, prescaler 1 = F/64
          crc_table_init(), paint_background(), update_frame(0, 0x7F, 0)
          REG_DISPCNT = 0x0403        <- mode 3 | BG2, and only then
loop      wait VCOUNT >= 160 to fall, then rise   (the VBlank edge)
          prev_phase := phase ; frame_id := (frame_id + 1) & 0xFFFFFF
          phase += 1, compare-and-subtract against 31
          status := snapshot of the latch AS IT STANDS
          vc0, t0 := VCOUNT, TM0CNT_L
          update_frame(frame_id, status, prev_phase)
          t1, vc1 := TM0CNT_L, VCOUNT
          fold the measurement into the latch
```

#### V5.35.3 STATUS, the latch, and the delay — implemented as frozen

`status` is snapshotted **before** `update_frame`, so **STATUS(f) certifies
updates 0..f−1 and never f itself** (§V5.33.8). The same byte goes into all 40
blocks and all 8 redundant copies, because it is an argument to the payload.

```c
fault = 1  when  vc1 < vc0  ||  vc1 > 227  ||  elapsed > 1309 ticks
```

`vc1 < vc0` catches an update that ran past scanline 227 and wrapped into the
visible area; `vc1 > 227` is unreachable given the 8-bit counter but is written
anyway; `elapsed > VBLANK_TICKS` catches an update longer than a whole VBlank at
the F/64 timer (83 776 cycles / 64 = 1 309 ticks). **The latch is sticky**: a test
asserts the string `fault = 0;` never appears inside the main loop.

`VMARGIN` is the **monotone minimum** of `227 − vc1`, clamped to 0..127 and
initialised to `0x7F` — a sentinel that is unreachable as a measurement, since
VBlank is only 68 scanlines. The analyzer never reinterprets it as a margin.

#### V5.35.4 Division-free, and proved

ARM7TDMI has no divide instruction, so a runtime `/` or `%` becomes a library
call in the VBlank path. **The ROM source contains neither**, asserted by a test
that greps the comment-stripped source for `/` and `%`. Every modulo is a
compare-and-subtract:

```c
phase += BAR_PHASE_MUL;  if (phase >= BAR_PERIOD) phase -= BAR_PERIOD;
bar_phase_base += 1u;    if (bar_phase_base >= BAR_PERIOD) bar_phase_base = 0;
```

The CRC is a 256-entry table built once at boot, outside VBlank. Per block the
whole 38-bit payload costs **three table lookups for FRAME_ID (folded once per
frame), six bitwise iterations for BLOCK_INDEX, and one lookup for STATUS** —
not 38 iterations.

#### V5.35.5 The ROM matches its model, word for word

The two hardware bases (`AGB_IO_BASE`, `AGB_VRAM_BASE`, `AGB_OAM_BASE`) are the
**only** thing a host test may relocate; their defaults are the real GBA
addresses and the ROM hash was byte-identical before and after the
parameterisation. `tests/host/test_agb_indexed.py` compiles the ROM's rendering
for the host against fake VRAM and compares it to `tools/istim.py`:

```text
38 400 of 38 400 AGB words exact, for frame ids
  0, 1, 2, 30, 31, 1000, 0x123456, 0xFFFFFF, 12345
  with STATUS 0x00, 0x05, 0x13, 0x40, 0x42, 0x7F, 0x80, 0xFF
canonical witness word for word for all 40 blocks, 3 frames
the ROM never writes bit 15                     (0 words with 0x8000 set)
frame 0 decodes intact before the mode is set   (FRAME_OK, id 0, status 0x7F)
```

#### V5.35.6 The analyzer, `tools/vindex.py`

Takes 40 blocks × 54 original consumed word16 and produces `frame_id`, `status`,
`id_valid`, `mixed_block_ids`, `misplaced_block_indices`,
`invalid_canonical_strips` with reasons, the bit-15 observations, and the
classification against the previous decisive frame. `analyze_run()` adds the
decisive population: `first_observed`, `last_observed`, `first_decisive`,
`last_decisive`, `edge_frames_excluded` and `decisive_transitions`.

Adversarially tested, one case per frozen classification: contiguous · gap ·
duplicate · reorder · half-range · wrap · mixed IDs · wrong block index · OTHER
symbol · wrong SYNC · wrong CRC · unexpected bit 15 · FAULT · status delay ·
too few intact frames. Plus a test that the formatted report contains neither
"dropped" nor "source loss".

Bit 15 is always split off (`flag15 = w & 0x8000`, `colour15 = w & 0x7FFF`),
**never** changes a decoded bit, and is reported separately. **U-GBP-034 stays
OPEN.**

#### V5.35.7 Static audit

```text
no heap            no malloc/calloc/free
no filesystem      no fopen/printf
no link cable      no SIOCNT, no 0x04000120/0x04000128/0x04000134
no serial          none
no GameCube        none
no logging         none
no division        no `/` and no `%` anywhere in the source
interrupts off     IME = 0, and the VBlank edge is POLLED
```

#### V5.35.8 VBlank status

**THEORETICALLY WITHIN VBLANK, AND SELF-INSTRUMENTED TO DETECT VIOLATION.**
The §V5.33.12 estimate stands at 19 840 VRAM-store cycles = 23.7 % of 83 776,
before loop control, CRC and instrumentation. **It is NOT "proven timing safe"**
— that is exactly why the FAULT latch exists, and why a run with FAULT set is
`STIMULUS_INVALID_FOR_DECISIVE_CLAIM`.

#### V5.35.9 What is deliberately NOT done

```text
witness retention in src/ or poc/    NOT implemented. The canonical witness is
  2 048 frames x 4 320 B = 8 847 360 B = 8.4375 MiB of operational capacity
  (§V5.33.9); witness_store_full would make a run INCONCLUSIVE. That is a
  runtime change and belongs to its own audited round.
the ROM has never run                on hardware or in an emulator
delivery to the internal AGB         unresolved, as for agb-color-bars
```
