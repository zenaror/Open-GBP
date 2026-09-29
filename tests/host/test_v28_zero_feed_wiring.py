"""tests/host/test_v28_zero_feed_wiring.py -- GitHub Issue #129/#130: the structural companion to
tests/unit/test_v28_zero_feed_integration.c. That C test proves, against the real gbp_walker +
gbp_v28_3b + gbp_atrans2/gbp_aplay2/gbp_adec2 chain, that main.c's own PUMP ORDER lands a ROTATE
transition under a total feed stall -- but it reproduces that order in its own harness (main.c
itself cannot be compiled on the host, checked directly: it includes <gccore.h> and the rest of the
GameCube-only SDK, and no such harness exists anywhere in this project). This file closes that gap
from the other side: it reads main.c's OWN text and confirms the two call sites the reproduced
order is built from are not, in the real file, gated on feed or decode availability -- the specific
residual risk docs/research/DEVLOG.md's own 2026-09-27 "section 18" entry named: "a backstop placed
inside gbp_atrans2_step() cannot protect against the one thing that could actually stop `handed`
from advancing -- the future driver loop itself failing to call gbp_aplay2_irq_handoff()/
gbp_atrans2_step() on every real audio tick, e.g. by gating its own calls on feed or decode
availability."
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAIN = os.path.join(ROOT, "poc", "gbp-audio-v28", "source", "main.c")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def function_body(src, name):
    """The braced body of `static ... name(...)  { ... }`, by brace counting from the function's
    own opening brace -- robust to nested blocks, which a single regex is not."""
    m = re.search(r"\b%s\s*\([^)]*\)\s*\{" % re.escape(name), src)
    if not m:
        raise AssertionError("function %r not found in %s" % (name, MAIN))
    start = m.end() - 1
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError("unbalanced braces reading %r" % name)


class TheAIDMACallbackIsUnconditional(unittest.TestCase):
    """live_dma_cb() is a real hardware interrupt callback (AUDIO_RegisterDMACallback), so it
    cannot itself be skipped by application control flow the way a polled call could -- but its own
    BODY could still wrap the handoff in a feed-dependent condition. It must not."""

    def test_registered_as_the_real_ai_dma_callback(self):
        src = read(MAIN)
        self.assertIn("AUDIO_RegisterDMACallback(live_dma_cb)", src)

    def test_the_handoff_is_the_bodys_first_statement_no_condition_before_it(self):
        body = function_body(read(MAIN), "live_dma_cb")
        # strip the opening brace and any leading whitespace/comments; the first real statement
        # must be the handoff call itself, not an `if` guarding it.
        inner = body[1:].lstrip()
        while inner.startswith("/*"):
            inner = inner[inner.index("*/") + 2:].lstrip()
        # Issue #139: the callback's register READS (unconditional declarations, no `if`) and the tick read precede the handoff
        while re.match(r"const uint(?:32|64)_t \w+ = (?:\(uint32_t\)AUDIO_GetDMA\w+\(\)|gettime\(\));\s*", inner):
            inner = inner[re.match(r"const uint(?:32|64)_t \w+ = (?:\(uint32_t\)AUDIO_GetDMA\w+\(\)|gettime\(\));\s*", inner).end():]
        self.assertTrue(inner.startswith("const uint8_t *c = gbp_aplay2_irq_handoff("),
                         "live_dma_cb()'s own first statement must be the unconditional handoff, "
                         "got: %r" % inner[:80])
        self.assertNotIn("if (", body, "live_dma_cb() must contain no conditional at all")


class TheProduceStepDispatchIsUnconditionalOnFeed(unittest.TestCase):
    """live_step()'s own produce-or-step dispatch runs once the session's own scope is active
    (live.phase's own gate, carried over unchanged from sync-0001 -- not a feed/decode condition);
    inside that scope, the dispatch itself must not ALSO be gated on how much decoded feed happens
    to be available."""

    def test_the_session_scope_gate_is_the_one_carried_over_from_sync_0001(self):
        src = read(MAIN)
        self.assertIn(
            "if (live.phase == GBP_ALIVE_WINDOW || (sync_started && !gbp_walker_finished(&walker) "
            "&& live.phase == GBP_ALIVE_DONE)) {",
            src)

    def test_no_feed_or_decode_count_gates_the_dispatch(self):
        body = function_body(read(MAIN), "live_step")
        # the dispatch itself: `if (tr.active) { ... } else b = gbp_aplay2_produce(...)`. Find it
        # and confirm nothing between the session-scope gate and this line tests adec2's own count
        # or ready()/produced-style feed availability.
        i = body.index("if (tr.active) { if (gbp_atrans2_step(")
        self.assertNotIn("adec2.count", body[:i + 200].split("if (tr.active)")[0][-400:],
                          "no adec2.count (feed-availability) check must precede the dispatch")
        dispatch_and_after = body[i:i + 400]
        self.assertNotIn("adec2.count >", dispatch_and_after.split("if (!ai_started")[0],
                          "the dispatch itself (before the one-time AI-start check) must read no "
                          "feed-availability count")

    def test_the_handoff_used_to_start_the_ai_is_the_one_time_start_not_a_per_tick_gate(self):
        """the OTHER gbp_aplay2_irq_handoff() call site in main.c (main(): "M starts at the first
        one") is a ONE-TIME call guarded by `!ai_started`, never re-entered once the AI is running --
        confirmed here so a reader of this file's own two tests does not mistake it for a second,
        conditionally-skipped per-tick handoff."""
        body = function_body(read(MAIN), "live_step")
        # Issue #131: the literal >= 2u this line used to read was unreachable at AHEAD 1 by
        # construction -- gbp_aplay2_start_ready() replaces it, deriving the cushion from ahead.
        self.assertIn("if (!ai_started && gbp_aplay2_start_ready(&ap2, adec2.count)", body)
        self.assertIn("ai_started = 1;", body)
        # exactly one handoff call inside live_step (the AI-start one); the per-tick one lives in
        # live_dma_cb(), not here.
        self.assertEqual(body.count("gbp_aplay2_irq_handoff("), 1)


if __name__ == "__main__":
    unittest.main()
