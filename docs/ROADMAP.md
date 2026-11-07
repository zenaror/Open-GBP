# Product roadmap

These are product goals and acceptance boundaries, not a current work queue or a
claim that a phase is complete. Physical hardware remains the target. Later layers
must not depend on unvalidated assumptions in earlier ones. Host and emulator
results remain distinct from physical evidence throughout these phases.

## Phase 0 — Reproducible environment

Pinned container/toolchain and deterministic ELF/DOL generation.

Acceptance: Record the pinned image/tool versions and hashes. Rebuild a known source revision
byte for byte, and inspect the resulting ELF/DOL independently.

## Phase 1 — Project and test infrastructure

An independently created smoke POC, host mocks and reproducible validation.

Acceptance: Compile an independently created POC, exercise display/input without undocumented
writes, and retain deterministic host and emulator smoke checks.

## Phase 2 — Reference analysis

Document observable interfaces from attributed references without distributing proprietary code.

Acceptance: Hash each legal reference input, attribute conclusions to exact source locations,
and preserve disagreements between hardware, the official disc, GBI and emulators.

## Phase 3 — Detection and initialization

Identify and initialize the physical Player, with bounded recovery and exact artifact identity.

Acceptance: Observe positive and absent-device cases, reproduce justified initialization, and
validate bounded failure/reset behavior on the physical Player.

## Phase 4 — Video

Present real-cartridge video and validate source geometry, continuity and presentation limitations separately.

Acceptance: Check geometry, pixel interpretation, frame integrity, delivery and presentation
separately. Preserve dropped/corrupted-frame evidence and avoid aggregate claims.

## Phase 5 — Input

Deliver GameCube controller input with explicit mapping, cadence and cartridge behavior.

Acceptance: Check encoding and release state on the host, then validate controller actions,
held buttons and recovery against identified cartridges on the physical Player.

## Phase 6 — Audio

Capture and present real audio with independently measured continuity, buffering and latency.

Acceptance: Check decoding, sample/channel ordering and queues on the host; separately measure
physical capture, playback, underruns, continuity and audiovisual timing.

## Phase 7 — Cartridge compatibility

Exercise GBA, GB and GBC separately, including GBP-aware behavior, rumble and cartridge-specific hardware; do not generalize across modes.

Acceptance: Use an explicit cartridge/mode matrix with exact build identities. A pass for one
GBA cartridge does not establish GB/GBC compatibility or GBP-specific features.

## Phase 8 — Physical Link Port regression

Preserve normal multiplayer, physical Mobile Adapter GB, PicoAdapterGB and other peripherals.

Acceptance: Regress the physical connector with a second handheld and representative accessories.
Retain normal Link operation with the virtual adapter disabled.

## Phase 9 — Standalone runtime parity

Provide useful presentation/configuration and normal Player functionality comparable to the official disc and GBI, including pixel-perfect scaling options.

Acceptance: Validate usable display, configuration, input, audio and lifecycle behavior in normal
play. Compare feature behavior with attributed references, without assuming parity.

## Phase 10 — Internal SIO research

First observe known cartridge activity read-only, then isolate routing, IRQ and response behavior on real hardware.

Acceptance: Pre-register one routing or IRQ question per experiment, preserve external Link
behavior, and require cartridge-observed evidence before claiming an internal response.

## Phase 11 — BBA networking

Independently validate detection, configuration, nonblocking I/O, timeouts, queues and reconnects against a host peer.

Acceptance: Exercise an automated host peer, loss/disconnect/reconnect and bounded timeouts.
Show that network delays cannot block serial or other timing-critical work.

## Phase 12 — Runtime stabilization

Keep transport boundaries testable, preserve timing and lifecycle behavior, and validate startup/shutdown and long sessions.

Acceptance: Exercise startup, shutdown, failure recovery and sustained sessions. Preserve
repeatable host regressions and exact physical evidence for timing-sensitive claims.

## Phase 13 — Optional virtual Mobile Adapter

Integrate protocol/network support only after the preceding foundations are sufficiently understood; never degrade normal physical operation.

Acceptance: Keep protocol/network integration optional and additive. Regress physical Mobile
Adapter, PicoAdapterGB, multiplayer, rumble and normal cartridge operation.

The research method defines permanent compatibility and hardware safety
requirements. These goals do not authorize experimental writes, original-cartridge
save changes, speculative serial routing or automatic deployment to physical media.
