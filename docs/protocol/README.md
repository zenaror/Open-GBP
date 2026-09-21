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

`REGISTERS.md` and `INITIALIZATION.md` were reconstructed from software in
Phase 2 and have since been verified on this project's hardware wherever a row
cites a `GBP-HW-` id; rows without one are still static analysis. Status
letters and evidence ids point to `../research/EVIDENCE.md`.
