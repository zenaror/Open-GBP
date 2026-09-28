"""tests/host/test_v28_syncpe.py -- GitHub Issue #128 section 7 / #129/#130: the SYNCPE/SYNCPH
phase-edge grammar round-trips through tools/v28syncpe.py, and the exact format strings this test
pins are the ones poc/gbp-audio-v28/source/main.c actually emits (so the ingestion side and the
console side cannot drift apart silently, the same discipline test_sync_image.py's own
`test_the_SD_records_carry_what_the_builder_reads` uses for sync-0001).
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v28syncpe  # noqa: E402

MAIN = os.path.join(ROOT, "poc", "gbp-audio-v28", "source", "main.c")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class RoundTrip(unittest.TestCase):
    def test_syncpe_start_edge(self):
        line = "000123 SYNCPE p=0 edge=start t=1a2b3c why=none"
        r = v28syncpe.parse_syncpe(line)
        self.assertEqual(r, {"p": 0, "edge": "start", "t": 0x1a2b3c, "why": "none"})

    def test_syncpe_end_edge_every_why_value(self):
        for why in v28syncpe.WHY_VALUES:
            line = "SYNCPE p=3 edge=end t=ffff why=%s" % why
            r = v28syncpe.parse_syncpe(line)
            self.assertEqual(r["p"], 3)
            self.assertEqual(r["edge"], "end")
            self.assertEqual(r["t"], 0xffff)
            self.assertEqual(r["why"], why)

    def test_syncph_summary_line(self):
        line = "SYNCPH phase=2 t_start=100 t_end=200 ended=1 reason=complete"
        r = v28syncpe.parse_syncph(line)
        self.assertEqual(r, {"phase": 2, "t_start": 0x100, "t_end": 0x200, "ended": True, "reason": "complete"})

    def test_syncph_unended_phase_reads_ended_false(self):
        line = "SYNCPH phase=1 t_start=100 t_end=0 ended=0 reason=probe"
        r = v28syncpe.parse_syncph(line)
        self.assertFalse(r["ended"])
        self.assertEqual(r["reason"], "probe")

    def test_a_non_matching_line_is_none(self):
        self.assertIsNone(v28syncpe.parse_syncpe("SYNCPH phase=0 t_start=0 t_end=0 ended=0 reason=none"))
        self.assertIsNone(v28syncpe.parse_syncph("SYNCPE p=0 edge=start t=0 why=none"))
        self.assertIsNone(v28syncpe.parse_syncpe("KEYLOG events=1"))

    def test_an_out_of_vocabulary_why_is_none_not_silently_accepted(self):
        """A damaged/truncated physical log must not parse as if it were valid (CLAUDE.md section 11's
        "malformed data" case): main.c's own syncpe_why() is a closed switch that can never emit a
        value outside WHY_VALUES, but the reader must not assume the writer -- or the bytes read back
        off a physical SD card -- agree. Otherwise-well-formed lines, wrong vocabulary only."""
        self.assertIsNone(v28syncpe.parse_syncpe("SYNCPE p=0 edge=start t=10 why=bogus"))
        self.assertIsNone(v28syncpe.parse_syncph("SYNCPH phase=0 t_start=10 t_end=20 ended=1 reason=bogus"))

    def test_an_out_of_vocabulary_why_is_dropped_from_a_mixed_parse(self):
        text = "\n".join([
            "000001 SYNCPE p=0 edge=start t=10 why=none",
            "000002 SYNCPE p=0 edge=end t=20 why=bogus",
        ])
        recs = v28syncpe.parse(text)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["edge"], "start")

    def test_parse_mixed_log_in_order(self):
        text = "\n".join([
            "000001 IDENT test=x",
            "000002 SYNCPE p=0 edge=start t=10 why=none",
            "000003 SYNCPE p=0 edge=end t=20 why=complete",
            "000004 SYNCPH phase=0 t_start=10 t_end=20 ended=1 reason=complete",
        ])
        recs = v28syncpe.parse(text)
        self.assertEqual([r["kind"] for r in recs], ["SYNCPE", "SYNCPE", "SYNCPH"])
        self.assertEqual(recs[0]["edge"], "start")
        self.assertEqual(recs[1]["why"], "complete")
        self.assertEqual(recs[2]["reason"], "complete")

    def test_a_full_round_trip_preserves_every_field(self):
        """format (Python's %x stands in for ringlog_printf's own C %llx -- same hex text, no
        leading 0x, which is all the parser reads) -> parse -> the same fields back out."""
        formatted = "SYNCPE p=%u edge=%s t=%x why=%s" % (5, "end", 0xdeadbeef, "cap")
        r = v28syncpe.parse_syncpe(formatted)
        self.assertEqual(r, {"p": 5, "edge": "end", "t": 0xdeadbeef, "why": "cap"})


class GrammarMatchesTheSource(unittest.TestCase):
    """The format strings this parser is built against are the ones main.c actually writes."""

    def test_syncpe_format_strings_present(self):
        src = read(MAIN)
        self.assertIn('"SYNCPE p=%lu edge=start t=%llx why=none"', src)
        self.assertIn('"SYNCPE p=%lu edge=end t=%llx why=%s"', src)

    def test_syncph_format_string_present(self):
        src = read(MAIN)
        self.assertIn('"SYNCPH phase=%lu t_start=%llx t_end=%llx ended=%u reason=%s"', src)

    def test_why_values_match_syncpe_why(self):
        src = read(MAIN)
        for why in v28syncpe.WHY_VALUES:
            self.assertIn('"%s"' % why, src, "syncpe_why()/the backstop must be able to emit %r" % why)

    def test_the_backstop_loop_starts_at_phase_zero(self):
        """sync-0001's own bug (Issue #128 section 7): its SYNCPH loop started at j=1u. Not repeated here."""
        src = read(MAIN)
        self.assertIn("for (j = 0u; j < V28_PLAN->count; j++)", src)
        self.assertNotIn("for (j = 1u;", src)


class TheLastPhaseGetsItsOwnSyncpeEndEdge(unittest.TestCase):
    """RUN 51 (Issue #131/#133/#135): validation_run's own log carries `SYNCPE p=3 edge=start` with
    NO matching `edge=end` anywhere, for a run SYNCPH itself confirms reached phase 3 and ended it
    `reason=complete` (the backstop, `GrammarMatchesTheSource` above). The cause: sweep is
    validation_run's own LAST phase, and its own completion is detected in a SEPARATE, LATER block
    of `live_step()` than the one `syncpe_edges()` is called from (sweep's own tick must run AFTER
    that same pump slot's produce/step call, its own header comment) -- so a completion landing
    there is never observed by that tick's earlier `syncpe_edges()` call, and once it makes the
    walker `finished`, the block `syncpe_edges()` lives in is gated `!gbp_walker_finished(&walker)`
    and never runs again. The domain data was never at risk (SYNCPH's own backstop has it), only
    this one redundant edge-log line -- but every validation_run that ever finishes cleanly would
    silently lose it, forever, without this fix. `syncpe_edges()` is idempotent by construction (its
    own `syncpe_started_seen`/`syncpe_ended_seen` arrays), so a second call costs nothing."""

    def sweep_tick_block(self, src):
        i = src.index("/* sweep's own tick, AFTER the pump slot's produce/step call above")
        j = src.index("if (!ai_started && gbp_aplay2_start_ready", i)
        return src[i:j]

    def test_syncpe_edges_is_called_again_right_after_sweep_s_own_phase_complete(self):
        block = self.sweep_tick_block(read(MAIN))
        m = re.search(r"gbp_walker_phase_complete\(&walker, now, tr\.active\);\s*(?:/\*.*?\*/\s*)*syncpe_edges\(\);",
                      block, re.S)
        self.assertIsNotNone(m, "sweep's own TICK_PHASE_COMPLETE branch does not call syncpe_edges() again "
                              "immediately after gbp_walker_phase_complete() -- SYNCPE p=3 edge=end would "
                              "silently never be written for any run that reaches sweep's own natural end")

    def test_the_second_call_is_inside_the_phase_complete_branch_not_unconditional(self):
        """A second syncpe_edges() call OUTSIDE the `if (f & ...PHASE_COMPLETE)` branch would run
        every tick sweep is active, which is harmless (idempotent) but pointless work every frame;
        the fix belongs exactly where the gap is, not spread wider than the defect."""
        block = self.sweep_tick_block(read(MAIN))
        i = block.index("if (f & GBP_V28_SWEEP_TICK_PHASE_COMPLETE)")
        branch = block[i:]
        self.assertIn("syncpe_edges();", branch)
        # and NOT present before the branch even opens (a stray unconditional call earlier in the block)
        before = block[:i]
        self.assertNotIn("syncpe_edges();", before)


if __name__ == "__main__":
    unittest.main()
