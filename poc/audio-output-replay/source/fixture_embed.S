/*
 * RUN 33's AUDIO-window sidecar, linked into the DOLPHIN FLOW variant ONLY
 * (make -C poc/audio-output-replay EMBED=1; GitHub Issue #86). Dolphin has no
 * SD2SP2, so without this the playback path would never run there. The console
 * image does not link this file: it reads the fixture from the card.
 */
    .section .rodata.aout_fixture,"a"
    .balign 32
    .global aout_embedded_fixture
aout_embedded_fixture:
    .incbin "run33-audio.bin"
    .global aout_embedded_fixture_end
aout_embedded_fixture_end:
