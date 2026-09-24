# Protocol / programming reference

`REGISTERS.md` — register windows, DMA transfer format, CONTROL/IRQ bit
tables, VIDEO/AUDIO/KEYPAD data formats.

`INITIALIZATION.md` — detection, interrupt setup, start, per-IRQ service,
watchdog, stop, and the internal serial state machine as used by the
official Start-up Disc and by Game Boy Interface.

`VIDEO.md` — the VIDEO path consolidated after Phase 4 (2026-09-21): the
block, the frame, the service under sustained video, the startup up to the
first real hand-off, and the presentation-path structure the runtime relies
on; every row carries its evidence id and a status of F or C.

`INPUT.md` — the KEYPAD / input path consolidated after GBP-INPUT-001
(2026-09-21): the window and the 16-bit word, its polarity, the bit assignment
with its status (the L/R order CORROBORATED, not FACT, observed through a
generic third-party pad), the write cadence of the references and of the
runtime, the controller mapping marked as this project's POLICY, and what is
not established; every row carries its evidence id and a status of F or C.

`AUDIO.md` — the AUDIO path consolidated after Phase 6's research runs
(2026-09-24): the window and its rate (4 096 blocks/s, CORROBORATED, not FACT),
what one block carries (a 1-bit PWM pulse over sixteen 256-byte cells, FACT for
the structure), the decode (CORROBORATED) and its amplitude law (FACT), what
draining the window costs, this project's playback chain marked as DESIGN, and
the open questions by id; every row carries its evidence id and a status of F
or C.

`REGISTERS.md` and `INITIALIZATION.md` were reconstructed from software in
Phase 2 and have since been verified on this project's hardware wherever a row
cites a `GBP-HW-` id; rows without one are still static analysis. Status
letters and evidence ids point to `../research/EVIDENCE.md`.
