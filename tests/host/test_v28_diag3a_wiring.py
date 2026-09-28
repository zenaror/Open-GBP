"""tests/host/test_v28_diag3a_wiring.py -- GitHub Issue #131: the diag_3a_stall plan and its own
V28DIAG record. main.c cannot be compiled or driven on the host (tests/unit/test_v28_zero_feed_
integration.c's own header comment; no such harness exists anywhere in this project) -- this is
the structural companion test_v28_anchor_wiring.py's own shape already established: it reads
main.c's OWN source text and confirms the wiring, not the behaviour.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAIN = os.path.join(ROOT, "poc", "gbp-audio-v28", "source", "main.c")


def read():
    with open(MAIN, encoding="utf-8") as f:
        return f.read()


class PlanSelector(unittest.TestCase):
    def test_diag_3a_stall_is_a_third_option_beside_the_two_frozen_plans(self):
        src = read()
        m = re.search(r"static const struct gbp_walker_plan \*const V28_PLAN =\s*"
                      r"#if defined\(GBP_V28_PLAN_PERCEPTUAL\)\s*\n\s*&GBP_V28_PERCEPTUAL_NO_PHASE1;\s*\n"
                      r"#elif defined\(GBP_V28_PLAN_DIAG_3A_STALL\)\s*\n\s*&GBP_V28_DIAG_3A_STALL;\s*\n"
                      r"#else\s*\n\s*&GBP_V28_VALIDATION_RUN;\s*\n#endif", src)
        self.assertIsNotNone(m, "V28_PLAN's own selector does not offer diag_3a_stall as a third arm")

    def test_the_plan_define_guard_accepts_exactly_one_of_three(self):
        src = read()
        self.assertIn("defined(GBP_V28_PLAN_VALIDATION) + defined(GBP_V28_PLAN_PERCEPTUAL) + "
                      "defined(GBP_V28_PLAN_DIAG_3A_STALL)", src)
        self.assertIn("!defined(GBP_V28_PLAN_VALIDATION) && !defined(GBP_V28_PLAN_PERCEPTUAL) && "
                      "!defined(GBP_V28_PLAN_DIAG_3A_STALL)", src)


class V28DiagRecord(unittest.TestCase):
    def test_v28diag_edge_is_scoped_to_the_diag_plan_only(self):
        """validation_run and perceptual_no_phase1 must stay byte-for-byte what they were --
        the Orchestrator's own instruction not to disturb validation_run while this is under
        diagnosis. The whole v28diag_edge() function, and every call to it, must sit inside
        #if defined(GBP_V28_PLAN_DIAG_3A_STALL)."""
        src = read()
        i = src.index("static void v28diag_edge(")
        # the #if guarding the function definition is the nearest preceding one
        pre = src[:i]
        guard_pos = pre.rindex("#if defined(GBP_V28_PLAN_DIAG_3A_STALL)")
        # and nothing closes that guard between it and the function
        self.assertNotIn("#endif", pre[guard_pos:])
        calls = list(re.finditer(r"v28diag_edge\(i,", src))
        self.assertEqual(len(calls), 2, "expected exactly one call at each phase edge (start, end)")
        for m in calls:
            # the nearest preceding #if/#endif pair must be the diag-only guard, still open
            before = src[:m.start()]
            last_if = before.rindex("#if defined(GBP_V28_PLAN_DIAG_3A_STALL)")
            self.assertNotIn("#endif", before[last_if:], "a v28diag_edge() call site is not inside the diag-only guard")

    def test_the_record_carries_every_field_the_orchestrator_asked_for(self):
        src = read()
        i = src.index("static void v28diag_edge(")
        j = src.index("\n}", i)
        body = src[i:j]
        for field in ("handed=", "mute_handed=", "produced=", "dropped_front=", "target=", "ahead=",
                     "ready=", "free_pool=", "begin_refused=", "begin_pending_ticks=",
                     "ai_started=", "ai_stopped=", "t_ai_start=", "t_ai_stop="):
            self.assertIn(field, body, "V28DIAG is missing %s" % field)
        # the free pool count is computed from the real pool state, not read from an existing counter
        self.assertIn("GBP_APLAY2_FREE", body)
        # begin_refused and begin_pending_ticks come from the real structs, not invented fields
        self.assertIn("tr.begin_refused_active", body)
        self.assertIn("s3a.begin_pending_ticks", body)

    def test_each_admission_is_checked_independently_of_syncpe_s_own(self):
        """A shared admit() check for both SYNCPE and V28DIAG would silently write a second line
        the ring's own capacity check never approved. Each record gets its own sync_line_admit()."""
        src = read()
        # within syncpe_edges(), there must be 4 independent sync_line_admit() calls: two for
        # SYNCPE (start/end) and two for V28DIAG (start/end)
        i = src.index("static void syncpe_edges(void)")
        j = src.index("\n}", src.index("for (i = 0; i < V28_PLAN->count", i))
        body = src[i:j]
        self.assertEqual(body.count("sync_line_admit()"), 4,
                         "expected 4 independent admission checks (SYNCPE x2, V28DIAG x2)")
