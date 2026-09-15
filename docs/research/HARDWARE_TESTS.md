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

### GBP-INIT-004 — bounded repeated HSP service: acknowledge, local re-arm, next cause, next delivery (designed 2026-09-15; NOT implemented, NOT released)

Status: design only (DEVLOG 2026-09-15 "GBP-INIT-004 designed"); no code,
no build, no hardware, no request. Depends on GBP-INIT-003B (executed:
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
