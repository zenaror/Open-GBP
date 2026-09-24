"""
tests/host/test_game2_image.py — GitHub Issue #113: Phase 6's second-attempt image (poc/gbp-audio-game2, GBP-AUDIO-011,
game-0002), pinned to game-0001, to §V26 and to the report its frozen gates read.

ONE VARIABLE, SHOWN BY DIFFING (§V26.2). game-0001 (poc/gbp-audio-game at 6129104, RUN 41's image) is this image's
base. Every line game-0001 has is here unchanged but its identity (three lines); every added hunk is the new header
or begins with a line marked GAME 6; every function but main is game-0001's character for character; the sources
and the Makefile are game-0001's but for the identity.

WHERE IT SITS. The record is written in main after the session, after LIVEVINC/LIVEVSEC and before X, by the same
before-AI predicate LIVEVINC counts.

THE LOG IS THE INTERFACE. tools/v26report.py (frozen with this image) is fed a log rendered from THIS image's own
format strings, and its report goes through the frozen tools/v26accept.py (f874cc6): RUN 39's case and RUN 40's
case hold, a frame one later fails, and the builder refuses a list that disagrees with its own counts.
"""
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(__file__))

import test_game_image as tg  # noqa: E402  (game-0001's pins and log renderer, reused, not copied)
import test_trace_image as tt  # noqa: E402
import v26accept  # noqa: E402
import v26report  # noqa: E402

G2_MAIN = os.path.join(ROOT, "poc", "gbp-audio-game2", "source", "main.c")
G2_MAKEFILE = os.path.join(ROOT, "poc", "gbp-audio-game2", "Makefile")
G1_MAIN, G1_MAKEFILE = tg.GAME_MAIN, tg.GAME_MAKEFILE
G2_OUT = os.path.join(ROOT, "build", "poc", "gbp-audio-game2")
TB = 40500000

IDENTITY = {
    '#define OPENGBP_APP_NAME "gbp-audio-game"': '#define OPENGBP_APP_NAME "gbp-audio-game2"',
    '#define TEST_ID "GBP-AUDIO-010"': '#define TEST_ID "GBP-AUDIO-011"',
    '    printf("\\n  Open-GBP " TEST_ID "  PHASE 6\'s ACCEPTANCE ON A REAL CARTRIDGE (HARDWARE_TESTS V25; NOT PHYSICALLY VALIDATED)\\n");':
        '    printf("\\n  Open-GBP " TEST_ID "  PHASE 6\'s ACCEPTANCE, SECOND ATTEMPT (HARDWARE_TESTS V26; NOT PHYSICALLY VALIDATED)\\n");',
}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class TheImageIsGame0001PlusOneRecord(unittest.TestCase):
    def test_game_0001_loses_nothing_but_its_identity(self):
        removed = [l for r, _a, _j in tt.hunks(read(G1_MAIN), read(G2_MAIN)) for l in r]
        self.assertEqual(sorted(removed), sorted(IDENTITY))

    def test_every_addition_is_the_header_an_identity_line_or_marked_GAME_6(self):
        for removed, added, j in tt.hunks(read(G1_MAIN), read(G2_MAIN)):
            if removed:
                self.assertEqual(added, [IDENTITY[r] for r in removed], (removed, added))
            elif j <= 1:
                self.assertTrue(all(l.startswith((" *", "/*")) for l in added), added[:3])
                self.assertIn("GBP-AUDIO-011, build game-0002", "\n".join(added[:3]))
            else:
                first = next(l for l in added if l.strip() not in ("", "{", "}"))
                self.assertIn("GAME 6", first, "a hunk at line %d is not marked GAME 6: %r" % (j + 1, first))

    def test_every_function_but_main_is_game_0001s(self):
        g1, g2 = tt.functions(read(G1_MAIN)), tt.functions(read(G2_MAIN))
        self.assertEqual(set(g1), set(g2))
        for name, text in g1.items():
            if name != "main":
                self.assertEqual(g2[name], text, name)

    def test_the_sources_and_the_makefile(self):
        self.assertEqual(tt.srcs(G2_MAKEFILE), tt.srcs(G1_MAKEFILE))
        mk = read(G2_MAKEFILE)
        self.assertRegex(mk, r"(?m)^APP_NAME\s*:=\s*gbp-audio-game2$")
        self.assertRegex(mk, r"(?m)^BUILD_ID\s*:=\s*game-0002$")
        for r, _a, _j in tt.hunks(read(G1_MAKEFILE), mk):
            for l in r:
                self.assertTrue(l.startswith(("# Open-GBP GBP-AUDIO-010", "#     make -C", "# Outputs go to",
                                              "APP_NAME", "BUILD_ID")), l)

    def test_the_record_sits_after_the_session_with_livevincs_predicate(self):
        main = tt.functions(read(G2_MAIN))["main"]
        rec = main.index('"LIVEVBEF i=')
        self.assertLess(main.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);"), rec)
        self.assertLess(main.index('"LIVEVSEC from='), rec)
        self.assertLess(rec, main.index("PAD_ButtonsDown(0) & PAD_BUTTON_X"))
        self.assertIn("if (ai_started && fr->t_last_block >= t_ai_start) continue;", main)
        self.assertIn("if (!ai_started || fr->t_last_block < t_ai_start) {", main)         # LIVEVINC's, unchanged
        self.assertIn("vstate.frames[f + 1u].t_first_block", main)
        self.assertRegex(read(G2_MAIN), r"(?m)^#define GAME_BEFORE_LIST_CAP 64u$")

    def test_the_new_records_fit_the_ringlog_line_at_their_worst(self):
        m = read(G2_MAIN)
        for tag in ("LIVEVBEF", "LIVEVBEFN"):
            fmts = tt.c_formats(m, tag)
            self.assertEqual(len(fmts), 1, tag)
            self.assertLessEqual(len(tt.worst_case(fmts[0], [])), tt.RINGLOG_CONTENT_MAX, tag)


# ---- the builder and the frozen gates, on a log rendered from THIS image's formats -------------------------------

SIG = [1, 10, 13, 16, 32, 35, 38, 92, 95, 98, 152, 155, 158]
FRAME = 678000
T0 = 10 ** 8


def log(press_frame=True, extra=(), listed_override=None, before_override=None):
    ai0 = 5 * 10 ** 9
    t_press = ai0 - 20250000 - TB                   # tg.log's LIVET t_press
    before = [(i, T0 + i * FRAME) for i in SIG + list(extra)]
    if press_frame:
        before.append((612, t_press - 150000))
    before.sort()
    n = len(before) if before_override is None else before_override
    base = tg.log(IDENT__test="GBP-AUDIO-011", IDENT__build="game-0002", LIVEVINC__before=n,
                  LIVEVINC__stored=n + 12, LIVEVINC__framecap=n + 12)
    m = read(G2_MAIN)
    lines = base.rstrip("\n").split("\n")
    fb, fn = tg.fmt_of(m, "LIVEVBEF"), tg.fmt_of(m, "LIVEVBEFN")
    extra_lines = []
    for k, (idx, first) in enumerate(before[:listed_override] if listed_override is not None else before):
        extra_lines.append(tg.render_kv(fb, {"i": k, "idx": idx, "t_first": first, "t_last": first + 660000,
                                              "t_next": first + FRAME}))
    listed = len(extra_lines)
    extra_lines.append(tg.render_kv(fn, {"before": n, "listed": listed, "capped": 0, "cap": 64}))
    for i, (o, c) in enumerate(((8, 25), (30, 89), (90, 149), (150, 197))):
        extra_lines.append("EPISODE i=%d idx=%08x state=closed flags=0005 frames=18 stable_count=3 open_frame=%d "
                           "close_frame=%d" % (i, i + 1, o, c))
    lines += ["%06d %s" % (len(lines) + k, l) for k, l in enumerate(extra_lines)]
    return "\n".join(lines) + "\n"


class TheBuilderAndTheFrozenGates(unittest.TestCase):
    def evaluate(self, text):
        rep = v26report.build(text)
        rep["l2_sidecar"] = "absent: not supplied in this test"
        return rep, v26accept.evaluate(rep, None, None)

    def test_RUN_39s_case_holds(self):
        rep, e = self.evaluate(log())
        self.assertEqual((len(rep["video"]["before_frames"]), rep["video"]["episodes_close_max"]), (14, 197))
        self.assertEqual(rep["t_press"], 5 * 10 ** 9 - 20250000 - TB)
        vid = e["V"]["video"]
        self.assertEqual((vid["verdict"], vid["P"]["index"], vid["Q_indices"]), ("HOLDS", 612, SIG))

    def test_RUN_40s_case_holds(self):
        _rep, e = self.evaluate(log(press_frame=False))
        self.assertEqual((e["V"]["video"]["verdict"], e["V"]["video"]["P"]), ("HOLDS", None))

    def test_a_frame_beyond_the_span_fails(self):
        _rep, e = self.evaluate(log(extra=(400,)))
        self.assertEqual(e["V"]["video"]["verdict"], "DOES NOT HOLD")

    def test_the_builder_refuses_a_list_that_disagrees_with_its_counts(self):
        with self.assertRaises(ValueError):
            v26report.build(log(listed_override=10))
        with self.assertRaises(ValueError):
            v26report.build(tg.log())                          # a game-0001 log: no LIVEVBEFN
        with self.assertRaises(ValueError):
            v26report.build(log(before_override=13))           # LIVEVINC before=13 but 14 listed

    def test_no_episode_record_is_a_null_bound_and_the_gate_declines(self):
        text = "\n".join(l for l in log().split("\n") if " EPISODE " not in l) + "\n"
        rep, e = self.evaluate(text)
        self.assertIsNone(rep["video"]["episodes_close_max"])
        self.assertEqual(e["V"]["video"]["verdict"], "INCONCLUSIVE")


class TheReportBuilderIsFrozenBeforeTheRun(unittest.TestCase):
    def test_v26report_and_the_image_are_the_bytes_of_the_commit_that_froze_them(self):
        import frozen
        key = "Issue #113 -- game-0002 and its report builder"
        self.assertEqual(frozen.source(key, "tools/v26report.py"), read(os.path.join(ROOT, "tools", "v26report.py")),
                         "tools/v26report.py was edited after it was frozen")
        self.assertEqual(frozen.source(key, "poc/gbp-audio-game2/source/main.c"), read(G2_MAIN),
                         "game-0002's source was edited after the candidate was built")


class TheAuditIsExercised(unittest.TestCase):
    def test_the_game_profile_passes_game_0002(self):
        import poc_audit
        if not os.path.exists(os.path.join(G2_OUT, "audit", "elf.nm.txt")):
            self.skipTest("%s is not built in this checkout" % G2_OUT)
        self.assertEqual(poc_audit.audit_dir(os.path.join(G2_OUT, "audit"), "game")[0], [])


if __name__ == "__main__":
    unittest.main()
