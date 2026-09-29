"""tests/host/test_v28_diag_loss_wiring.py -- GitHub Issue #137: what poc/gbp-audio-v28/source/main.c does with the LOSS handler.

main.c cannot be compiled or driven on the host, so the wiring is checked the only way it can be: in the real source (the shape
test_v28_anchor_wiring.py and test_v28_plans.py established -- a harness that calls the handler itself models the wiring as
INTENDED, not as WRITTEN). What must hold:
  * every instrument (histograms, the loss handler, the arms) is compiled ONLY into the diag_loss image: validation_run and the
    perceptual image keep their own timing byte for byte;
  * the arms are applied where they act: the label block of submit_ready is skipped while the label is off, and the step hook
    answers from the handler's cell; both read the handler's INVERTED fields, so a zeroed struct (before the phase starts) is the
    production image;
  * the phase's tick, its acknowledgement and its cut are wired, in the right order relative to the slot's own produce call;
  * the underrun edge is read ONCE a slot outside the phase switch.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAIN = os.path.join(ROOT, "poc", "gbp-audio-v28", "source", "main.c")
DIAG = "GBP_V28_PLAN_DIAG_LOSS"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def code(src):
    return re.sub(r"/\*.*?\*/|//[^\n]*", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)


def function_body(src, name):
    m = re.search(r"\b%s\s*\([^\n;]*\)\s*\n\{" % re.escape(name), src)
    assert m, name
    i = m.end() - 1
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise AssertionError(name)


def diag_regions(src):
    """[(lineno, text, active)] where `active` is True when the line is compiled ONLY if GBP_V28_PLAN_DIAG_LOSS is defined
    (the innermost conditional chain needs it: `#if defined(GBP_V28_PLAN_DIAG_LOSS)` or an `#elif` of the same, not its `#else`)."""
    stack = []          # each entry: True when the current branch of that conditional requires DIAG
    out = []
    for n, line in enumerate(src.splitlines(), 1):
        t = line.strip()
        if re.match(r"#\s*if(n?def)?\b", t):
            stack.append(bool(re.search(r"\b%s\b" % DIAG, t)) and "!defined(%s)" % DIAG not in t.replace(" ", ""))
        elif re.match(r"#\s*elif\b", t):
            stack[-1] = bool(re.search(r"\b%s\b" % DIAG, t))
        elif re.match(r"#\s*else\b", t):
            stack[-1] = False
        elif re.match(r"#\s*endif\b", t):
            stack.pop()
        out.append((n, line, any(stack)))
    return out


class InstrumentsAreOnlyInTheDiagImage(unittest.TestCase):
    IDENT = re.compile(r"\b(loss_hist|loss_ctr|loss_snapshot|loss_step_pushes|gbp_v28_loss_\w+|gbp_v28_hist_\w+|gbp_v28_hists_\w+|"
                       r"struct gbp_v28_(?:loss|hist)\w*|loss\.\w+|&loss\b|v28_loss_report\w*|GBP_V28_(?:LOSS|H_|NHIST)\w*)")

    def test_every_use_sits_in_a_region_only_that_image_compiles(self):
        src = read(MAIN)
        bad = []
        for n, line, active in diag_regions(code(src)):
            s = line.strip()
            if active or not self.IDENT.search(line):
                continue
            if s.startswith("#define") or s.startswith("#include"):
                continue        # the empty fallbacks of the macros (V28_NOTE, loss_gap_note) are the point
            if re.fullmatch(r"V28_(?:NOTE|TICKS)\(.*\);", s):
                continue        # a statement that IS such a macro use expands to nothing outside the diag image
            # the dispatcher/cut cases name the handler INSIDE their own #if, checked above; the case labels themselves are enum names
            bad.append((n, s[:100]))
        self.assertEqual(bad, [], "instrument code outside a GBP_V28_PLAN_DIAG_LOSS-only region: %s" % bad)

    def test_the_fallback_macros_expand_to_nothing_or_the_production_value(self):
        src = code(read(MAIN))
        i = src.index("#define V28_LABEL_ON()          (loss.label_off == 0u)")
        j = src.index("#else", i)
        tail = src[j:j + 400]
        self.assertRegex(tail, r"#else\s*#define V28_LABEL_ON\(\)\s+1\s")
        self.assertRegex(tail, r"#define V28_TICKS\(var\)\s*\n")
        self.assertRegex(tail, r"#define V28_NOTE\(id, t0\)\s*\n")
        self.assertRegex(tail, r"#define loss_gap_note\(d\)\s+\(\(void\)0\)")


class TheArmsAreApplied(unittest.TestCase):
    def test_the_label_block_is_skipped_while_off_and_only_that_block(self):
        body = function_body(code(read(MAIN)), "submit_ready")
        m = re.search(r"if \(V28_LABEL_ON\(\)\) \{(.*?)\n    \}\n\n    GX_SetDrawDone", body, re.S)
        self.assertIsNotNone(m, "the label block is not wrapped in if (V28_LABEL_ON())")
        blk = m.group(1)
        for needed in ("v28_label_text(", "label_render(", "draw_label_quad();", "label_ticks_last"):
            self.assertIn(needed, blk)
        outside = body.replace(m.group(0), "")
        self.assertNotIn("draw_label_quad", outside, "a label draw outside the gated block would draw with the label OFF")
        self.assertNotIn("label_render(", outside)
        self.assertNotIn("v28_label_text(", outside)
        self.assertIn("draw_quad();", outside, "the main quad is drawn regardless of the arm")

    def test_the_arms_read_the_inverted_fields(self):
        src = code(read(MAIN))
        self.assertIn("#define V28_LABEL_ON()          (loss.label_off == 0u)", src)
        self.assertRegex(function_body(src, "loss_step_pushes"),
                         r"return loss\.step_half \? GBP_V28_LOSS_STEP_HALF : GBP_V28_LOSS_STEP_FULL;")

    def test_the_step_hook_is_installed_only_in_the_diag_image_and_the_histograms_initialised(self):
        src = read(MAIN)
        for n, line, active in diag_regions(code(src)):
            if "ap2.step_pushes = loss_step_pushes" in line or "gbp_v28_hists_init(loss_hist)" in line:
                self.assertTrue(active, "%s at line %d is not diag-only" % (line.strip(), n))
        self.assertIn("ap2.step_pushes = loss_step_pushes;", src)
        self.assertIn("gbp_v28_hists_init(loss_hist);", src)
        self.assertLess(src.index("gbp_v28_hists_init(loss_hist);"), src.index("cfg.audio_tap = live_tap;"),
                        "the histograms must be initialised before the first tap can note into them")

    def test_no_other_image_installs_a_step_hook(self):
        src = code(read(MAIN))
        self.assertEqual(len(re.findall(r"\.step_pushes\s*=", src)), 1)


class ThePhaseIsWired(unittest.TestCase):
    def live_step(self):
        return function_body(code(read(MAIN)), "live_step")

    def test_the_loss_case_snapshots_then_reports_the_underrun_then_ticks_then_acknowledges(self):
        m = re.search(r"case GBP_WALKER_LOSS: \{(.*?)break;\s*\}", self.live_step(), re.S)
        self.assertIsNotNone(m)
        blk = m.group(1)
        order = [blk.index(x) for x in ("loss_snapshot(&loss_ctr);", "gbp_v28_loss_underrun_observed(&loss, now);",
                                        "gbp_v28_loss_tick(&loss, &tr, &ap2, &adec2, now, &loss_ctr, loss_hist)",
                                        "gbp_v28_loss_hold_done(&loss);", "gbp_walker_phase_complete(&walker, now, tr.active)")]
        self.assertEqual(order, sorted(order), "snapshot -> underrun hook -> tick -> hold_done -> phase_complete")
        self.assertRegex(blk, r"if \(f & GBP_V28_LOSS_TICK_HOLD_DONE\) gbp_v28_loss_hold_done")
        self.assertRegex(blk, r"if \(f & GBP_V28_LOSS_TICK_PHASE_COMPLETE\) \(void\)gbp_walker_phase_complete")

    def test_the_tick_comes_before_the_slots_produce_call(self):
        body = self.live_step()
        self.assertLess(body.index("gbp_v28_loss_tick("), body.index("gbp_aplay2_produce(&ap2, &adec2)"),
                        "the entry's landing is read from tr.active AFTER the slot's own step: tick first, produce below")

    def test_the_underrun_count_is_read_once_a_slot_outside_the_switch(self):
        body = self.live_step()
        self.assertEqual(len(re.findall(r"v28_underrun_new\(\)", body)), 1)
        self.assertLess(body.index("const uint32_t underrun_now = v28_underrun_new();"),
                        body.index("switch (gbp_walker_current_kind(&walker))"))
        for h in ("gbp_v28_3a_underrun_observed(&s3a, now)", "gbp_v28_3b_underrun_observed(&s3b, now)"):
            self.assertRegex(body, r"if \(underrun_now\) %s" % re.escape(h))
        # the loss handler is told once per underrun (bounded), so its hooks column is the count, not the number of slots
        self.assertRegex(body, r"for \(u = 0u; u < underrun_now && u < 64u; u\+\+\) gbp_v28_loss_underrun_observed\(&loss, now\);")

    def test_the_underrun_delta_is_wrap_safe_and_keeps_its_snapshot_between_phases(self):
        body = function_body(code(read(MAIN)), "v28_underrun_new")
        self.assertIn("const uint32_t fresh = now_n - seen;", body)
        self.assertIn("seen = now_n;", body)

    def test_a_cut_acknowledges_like_3a_and_3b(self):
        body = function_body(code(read(MAIN)), "v28_cut")
        m = re.search(r"case GBP_WALKER_LOSS:(.*?)break;", body, re.S)
        self.assertIsNotNone(m)
        blk = m.group(1)
        self.assertLess(blk.index("gbp_v28_loss_cut(&loss, now, &loss_ctr, loss_hist);"),
                        blk.index("gbp_v28_loss_hold_done(&loss);"))
        self.assertLess(blk.index("loss_snapshot(&loss_ctr);"), blk.index("gbp_v28_loss_cut("),
                        "the cut's end counters are read at the cut, not left from the last tick")
        self.assertIn("if (loss.hold_pending) gbp_v28_loss_hold_done(&loss);", blk,
                      "a cut with no hold running (an entry, between holds) owes no acknowledgement: refused_done stays 0")

    def test_the_dispatcher_starts_it_from_the_walkers_own_index(self):
        body = function_body(code(read(MAIN)), "v28_dispatch_phase_start")
        self.assertIn("gbp_v28_loss_start(&loss, live.tb_hz, now);", body)


class TheInstrumentsMeasureTheRightThings(unittest.TestCase):
    def test_every_histogram_has_a_writer_and_the_tap_wraps_its_body(self):
        src = code(read(MAIN))
        for h in ("GBP_V28_H_TAP", "GBP_V28_H_DECODE", "GBP_V28_H_PROD", "GBP_V28_H_PUMP", "GBP_V28_H_LABEL"):
            self.assertIn(h, src, "%s is never noted" % h)
        self.assertIn("loss_gap_note(t_done - live_last_t)", src)
        tap = function_body(src, "live_tap")
        self.assertRegex(tap, r"live_tap_body\(user, bytes, len, t_done, completed\);")
        self.assertIn("cfg.audio_tap = live_tap;", src)
        pump = function_body(src, "pump")
        self.assertRegex(pump, r"pump_body\(user\);")

    def test_the_decode_timing_wraps_the_decode_alone_and_keeps_its_result_test(self):
        body = function_body(code(read(MAIN)), "live_tap_body")
        m = re.search(r"V28_TICKS\(dec_t0\);\s*const uint32_t pushed = gbp_adec2_push_block\(&adec2, bytes\);\s*"
                      r"V28_NOTE\(GBP_V28_H_DECODE, dec_t0\);\s*if \(pushed == 0\)", body)
        self.assertIsNotNone(m, "the decode call must sit between its own two tick reads, result test unchanged")

    def test_the_counters_the_handler_snapshots_are_the_ones_the_tap_and_the_chain_keep(self):
        body = function_body(code(read(MAIN)), "loss_snapshot")
        for field, src_expr in (("target", "ap2.target"), ("ahead", "ap2.ahead"), ("blocks_in", "adec2.blocks_in"), ("taps", "live_taps"), ("taps_failed", "live_taps_failed"),
                                ("wrong_len", "live_wrong_len"), ("underruns", "ap2.underruns"), ("starved", "ap2.starved_steps"),
                                ("produced", "ap2.produced"), ("handed", "ap2.handed"), ("ring_gated", "ap2.ring_gated"),
                                ("ring", "adec2.count")):
            self.assertRegex(body, r"c->%s = \(?u?i?n?t?3?2?_?t?\)?\(?%s" % (field, re.escape(src_expr)), field)


if __name__ == "__main__":
    unittest.main()
