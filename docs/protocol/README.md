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

`INPUT.md` — the KEYPAD / input path consolidated after GBP-INPUT-001 and
GBP-INPUT-002 (2026-09-21): the window and the 16-bit word, its polarity, the
bit assignment and the history of its status, the write cadence of the
references and of the runtime, the controller mapping marked as this project's
POLICY, and what is not established; every row carries its evidence id and a
status of F or C.

`AUDIO.md` — the AUDIO path consolidated after Phase 6's research runs
(2026-09-24): the window and its rate, what one block carries, the decode and
its amplitude law, what draining the window costs, this project's playback
chain marked as DESIGN, and the open questions by id; every row carries its
evidence id and a status of F or C.

`REGISTERS.md` and `INITIALIZATION.md` were reconstructed from software in
Phase 2 and have since been verified on this project's hardware wherever a row
cites a `GBP-HW-` id; rows without one are still static analysis. Status
letters and evidence ids point to `../research/EVIDENCE.md`.

**This index states no claim's status.** Each page carries its own, beside the
evidence id it rests on. When this index restated them, it drifted from the
page it indexed and gave the reader a second, stale answer for the L/R order
(Issue #96).
