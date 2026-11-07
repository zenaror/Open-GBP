# Keypad/order fixture provenance

`fixtures/key-order/` contains derived text fixtures for the historical RUN 21,
22, 25 and 26 keypad/order checks. These are not complete raw captures. RUN 21/22
retain only STARTUPT; RUN 25/26 retain KEY, KEYLOG, SESSION and STARTUPT records.
Each selected line is byte-identical to its source line. No game/audio/video
payload, save or proprietary binary is included.

`manifest.json` pins original capture names, byte counts and SHA-256, the selection
predicate and original line numbers, and each excerpt's independent size/hash.
`tests/host/key_order_fixtures.py:extract` reproduces the selection when the original
is available. Public checks reject missing/corrupted excerpts. Full-capture tests
still require the originals and cannot mistake an excerpt for a full log. These
fixtures preserve historical keypad/order evidence; they do not validate a new
binary or supply new physical execution evidence.
