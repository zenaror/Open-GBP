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
