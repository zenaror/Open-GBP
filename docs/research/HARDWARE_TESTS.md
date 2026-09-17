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
### GBP-VIDEO-002-R3 (build `vstate-0003`) — service the IRQ window under semantic disagreement without ending the run — DESIGNED and HARDENED 2026-09-17, IMPLEMENTED 2026-09-17, NOT PHYSICALLY EXECUTED

Two physical runs of GBP-VIDEO-002 ended on the same condition: one 32-byte read
of the IRQ window whose eight replicas did not all carry the same value. The
second preserved the bytes (GBP-HW-089…092) and the abort is now fully
characterised. This revision exists to make that condition survivable **without
losing evidence and without inventing semantics**, so that the 120 s scientific
window and, after it, GBP-VIDEO-003 become reachable.

**Implementation status, 2026-09-17.** The design below is now implemented in
`src/gbp/gbp_vstate.{h,c}`, `src/gbp/gbp_vstate_probe.c`,
`src/gbp/gbp_vstatedump.{h,c}`, `poc/gbp-video-state-probe/` (Build ID
`vstate-0003`) and `tools/vstate.py`, with the host battery in
`tests/unit/test_gbp_video_state.c` and `tests/host/test_vstate.py`. It has
**not** been executed on hardware: no observation in this repository comes from
it, and none of its synthetic scenarios is evidence about the device. The
measured cost is in R3.15. What follows is the specification the implementation
must match, and it stays the authority.

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
