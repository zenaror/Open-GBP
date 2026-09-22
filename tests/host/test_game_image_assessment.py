"""
tests/host/test_game_image_assessment.py — GitHub Issue #38 (2026-09-21): the
runtime image fit for playing a game, ASSESSED and NOT BUILT (INPUT_PATH.md §12).

Pinned to the source the assessment is read from, so that the STOP decision is
falsifiable later: the one statement that binds the witness and the null-safe
stops behind it; the five stops that remain in CHECK_ADMISSION once the witness
is unbound and the status every one of them is scored with; the absence of any
session or operator-end field in the state machine's config and of any session
stop reason; the pump hook with no return channel; the constants the session
bounds are computed from (the safety budget, the delivery cap, the frame store
cap, the ringlog and its reserve); the freed memory arithmetic; the input path's
independence from the instrumentation. And that nothing was built: no new POC,
BUILD_ID still stream-0015, nothing under src/, poc/, tools/ or the Makefile
changed against 2e9e393.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAIN = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c")
MAKEFILE = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "Makefile")
VSTATE_PROBE_C = os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.c")
VSTATE_PROBE_H = os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.h")
VSTATE_H = os.path.join(ROOT, "src", "gbp", "gbp_vstate.h")
VWITNESS_H = os.path.join(ROOT, "src", "gbp", "gbp_vwitness.h")
VWITNESS_C = os.path.join(ROOT, "src", "gbp", "gbp_vwitness.c")
VQUEUE_H = os.path.join(ROOT, "src", "gbp", "gbp_vqueue.h")
VFULL_H = os.path.join(ROOT, "src", "gbp", "gbp_vfull.h")
VDISP_H = os.path.join(ROOT, "src", "gbp", "gbp_vdisp.h")
VVI_H = os.path.join(ROOT, "src", "gbp", "gbp_vvi.h")
INPUT_PATH = os.path.join(ROOT, "docs", "research", "INPUT_PATH.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
ROADMAP = os.path.join(ROOT, "docs", "ROADMAP.md")
DEVLOG = os.path.join(ROOT, "docs", "research", "DEVLOG.md")
BASE_COMMIT = "2e9e393"          # origin/main before Issue #38
SRC_HZ = 59.727


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "")


def define(path, name):
    m = re.search(r"^#define\s+%s\s+(\S+)" % re.escape(name), read(path), re.M)
    assert m, name
    return m.group(1)


def section12():
    t = read(INPUT_PATH)
    i = t.index("## 12. The runtime image fit for playing a game")
    j = t.find("\n## 13.", i)
    return t[i:] if j < 0 else t[i:j]


def check_admission():
    """The text of CHECK_ADMISSION: from its comment to the color block that follows the witness block."""
    t = read(VSTATE_PROBE_C)
    i = t.index("CHECK_ADMISSION: the ONLY place a stop condition is evaluated")
    j = t.index("4. the scientific target, measured on valid observation only", i)
    return t[i:j]


class TheInstrumentationIsSeparableFromTheRuntime(unittest.TestCase):
    def test_the_witness_is_bound_by_one_statement_and_its_stops_are_null_safe(self):
        main = read(MAIN)
        self.assertEqual(main.count("cfg.witness = &wit;"), 1)
        vs = read(VSTATE_PROBE_C)
        self.assertIn("if (cfg->witness) {", vs)
        self.assertIn("if (gbp_vwitness_store_full(cfg->witness)) {", vs)
        self.assertIn("if (gbp_vwitness_target_reached(cfg->witness)) {", vs)
        vw = read(VWITNESS_C)
        self.assertIn("return (w && w->target_reached) ? 1 : 0;", vw)
        self.assertIn("return (w && w->store_full) ? 1 : 0;", vw)
        # the witness step runs inside the service transaction only when bound
        self.assertRegex(vs, r"if \(cfg->witness\) \{\s*\n\s*.*\n\s*gbp_vwitness_step\(cfg->witness")

    def test_the_sampler_and_the_traces_are_instrumentation_and_the_input_path_does_not_reference_them(self):
        main = read(MAIN)
        for tok in ("gbp_vfull_set_origin(&full, gbp_vwitness_meta_at(&wit, 0)->frame_index);", "gbp_vvi_latch(&vvi", "gbp_vvi_handed(&vvi",
                    "gbp_vfulldump_stream(", "gbp_vvidump_stream(", "gbp_vidxdump_stream(", "gbp_vdispdump_stream("):
            self.assertIn(tok, main, tok)
        # input_step() and keylog_emit(): the KEY record's code touches none of the instrumentation
        i = main.index("static void keylog_emit(const struct gbp_transport *t)")
        j = main.index("static void pump(void *user)")
        block = main[i:j]
        for forbidden in ("wit", "full", "vvi", "disp"):
            self.assertNotRegex(block, r"\b%s\b" % forbidden, forbidden)
        self.assertIn("input_step();", main[main.index("static void pump(void *user)"):main.index("static void pump(void *user)") + 400])

    def test_the_memory_the_subtraction_frees(self):
        self.assertEqual((define(VWITNESS_H, "GBP_VWITNESS_TARGET"), define(VWITNESS_H, "GBP_VWITNESS_WORDS"), define(VWITNESS_H, "GBP_VWITNESS_BLOCKS")), ("2048u", "54u", "40u"))
        witness = 2048 * 54 * 40 * 2
        self.assertEqual(witness, 8847360)
        self.assertEqual((define(VFULL_H, "GBP_VFULL_K"), define(VFULL_H, "GBP_VFULL_SPACING")), ("8u", "256u"))
        full = 1228800 + 614400
        self.assertEqual(define(VVI_H, "GBP_VVI_CAP"), "4096u")
        vvi = 4096 * 64
        self.assertEqual(witness + 98304 + full + vvi, 11051008)
        self.assertIn("11 051 008 B", section12())


class OnceTheWitnessIsGoneNoStopIsASuccess(unittest.TestCase):
    def test_the_remaining_stops_and_the_status_each_is_scored_with(self):
        ca = check_admission()
        for variant, stop in (("S5_safety_budget", "GBP_VSTATE_STOP_SAFETY_BUDGET"), ("S5_frame_store_cap", "GBP_VSTATE_STOP_FRAME_STORE_CAP"),
                              ("S5_event_store_cap", "GBP_VSTATE_STOP_EVENT_STORE_CAP"), ("S5_witness_store_full", "GBP_VSTATE_STOP_WITNESS_STORE_FULL"),
                              ("S5_witness_target", "GBP_VSTATE_STOP_WITNESS_TARGET")):
            self.assertRegex(ca, r'finish\(x, GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE, "-", "%s",\s*%s\)' % (variant, stop), variant)
        vs = read(VSTATE_PROBE_C)
        self.assertRegex(vs, r'finish\(x, GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE, "-", "S5_delivery_cap", GBP_VSTATE_STOP_DELIVERY_CAP\)')
        self.assertIn("if (res->deliveries >= cfg->max_deliveries) {", vs)
        # the main status never keys on which cap fired: an ended session and a failed one read alike
        self.assertIn("if (st && st->episode_count > 0u) return GBP_VSTATE_OK_STRUCTURED_CHANGE_OBSERVED;", vs)
        self.assertIn("return GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE;", vs)
        self.assertIn("The classification keys on valid_observation_elapsed, NEVER on which\n * cap fired", vs)

    def test_no_session_stop_exists_and_the_poc_cannot_end_the_run(self):
        # THE STATE THE ASSESSMENT DESCRIBED: the module at the base commit. Issue #39 then added exactly the stop the
        # assessment found missing (tests/host/test_play_image.py pins it), so this test reads the header at BASE_COMMIT.
        r = subprocess.run(["git", "-C", ROOT, "cat-file", "-e", BASE_COMMIT], capture_output=True)
        if r.returncode != 0:
            self.skipTest("the base commit is not available in this checkout")
        h = subprocess.run(["git", "-C", ROOT, "show", "%s:src/gbp/gbp_vstate_probe.h" % BASE_COMMIT], capture_output=True, text=True, check=True).stdout
        enum = h[h.index("GBP_VSTATE_STOP_NONE = 0"):h.index("GBP_VSTATE_STOP_WITNESS_STORE_FULL")]
        self.assertNotRegex(enum, r"SESSION|OPERATOR", "no session / operator-end stop reason exists")
        cfg = h[h.index("struct gbp_vstate_config {"):h.index("static inline void gbp_vstate_config_disable_time_target")]
        cfg_fields = re.sub(r"/\*.*?\*/", "", cfg, flags=re.S)      # declarations only: the comments mention a future operator ARMING step, at the start
        self.assertNotRegex(cfg_fields, r"session|operator|stop_now|end_requested", "no session / operator-end field in the config")
        self.assertIn("it is exactly where a future operator\n     * ARMING step would have to sit", cfg)
        self.assertIn("void (*pump)(void *user);", read(VQUEUE_H), "the pump hook has no return channel")
        self.assertIn("if (q->pump) q->pump(q->pump_user);", read(os.path.join(ROOT, "src", "gbp", "gbp_vqueue.c")))
        self.assertIn("gbp_vstate_probe_run(&t, &rl, &cfg, &res);     /* returns only after the teardown */", read(MAIN))
        self.assertIn("gbp_vstate_config_disable_time_target(&cfg);", read(MAIN))
        self.assertEqual(define(VSTATE_PROBE_H, "GBP_VSTATE_MIN_VALID_OBSERVATION_DISABLED_TICKS"), "UINT64_MAX")
        # and the header of today carries the stop Issue #39 added on top of that state
        self.assertIn("GBP_VSTATE_STOP_SESSION_END", read(VSTATE_PROBE_H))

    def test_the_bounds_the_assessment_computes(self):
        self.assertEqual(define(MAIN, "STREAM_SAFETY_SECONDS"), "60u")
        self.assertEqual(define(MAIN, "STREAM_MAX_DELIVERIES"), "400000u")
        self.assertEqual(define(VSTATE_H, "GBP_VSTATE_MAX_FRAMES"), "16384u")
        self.assertEqual(define(VSTATE_H, "GBP_VSTATE_MAX_EVENTS"), "4096u")
        self.assertEqual(round(16384 / SRC_HZ, 1), 274.3)
        self.assertEqual(round(400000 / 6314.0), 63)
        self.assertEqual((define(MAIN, "LOG_LINES"), define(MAIN, "LOG_LINE_LEN"), define(MAIN, "KEYLOG_TAIL_RESERVE")), ("1024", "256", "64u"))
        self.assertEqual((define(VDISP_H, "GBP_VDISP_LIFE_CAP"), define(VDISP_H, "GBP_VDISP_EVENT_CAP")), ("4096u", "8192u"))
        self.assertEqual(round(4096 / SRC_HZ), 69)
        self.assertIn('By the probe\'s own words "it stops a run that has gone wrong, it is never a success"', plain(section12()))
        main = read(MAIN)
        self.assertIn("The safety cap is a different thing entirely: it stops a run that has gone", main)
        self.assertIn(" * wrong, it is never a success, and it stays at 60 s. */", main)
        self.assertIn("it remains the run's only time-based stop,\n * and it is a SAFETY stop, never a success.", read(VSTATE_PROBE_H))


class TheAssessmentIsRecordedAndNothingWasBuilt(unittest.TestCase):
    def test_section_12_carries_the_stop_and_the_redesign(self):
        s = plain(section12())
        for tok in ("ASSESSED, NOT BUILT (GitHub Issue #38, 2026-09-21)", "the conclusion is STOP",
                    "with the witness unbound, an image of this shape has NO success stop", "\"it will probably be fine\" is not one",
                    "cfg.witness = NULL", "the predicates are null-safe", "so the service pass gets SHORTER, a timing change on the critical path to be re-measured, not assumed",
                    "there is nothing left that needs the witness's first frame", "This part of the Issue's simplification HOLDS",
                    "The Issue's \"presentation path not touched\" holds in substance and not in bytes, and that must be said",
                    "UNTOUCHED, byte-identical: input_step() is the first statement of pump()",
                    "Every remaining stop is scored as the run going wrong", "moves WHEN the run stops and never HOW the stop is scored",
                    "The POC cannot end the run as a success", "void (*pump)(void *user)", "which is a misrecording, not a success stop",
                    "a SUCCESS stop for", "an operator-ended session: the Z button, which the policy reserves for the runtime and never sends",
                    "GBP_VSTATE_STOP_SESSION_END", "tests/unit/test_gbp_video_state.c", "274.3 s", "about 350 presses",
                    "a new POC", "a new poc_audit profile", "the next Swiss number (13)",
                    "Items 1 and 6 are the reason this is a redesign and not a subtraction", "Both constraints cannot hold at once with a usable image",
                    "the input path and the KEY record stay byte-identical, the descriptor does not change, and the routing FACT of §V7.4 is not disturbed",
                    "None of these is a property of the Game Boy Player", "No code; no build; no BUILD_ID; no run name; nothing staged"):
            self.assertIn(tok, s, tok)

    def test_the_records(self):
        h = plain(read(HANDOFF))
        for tok in ("ISSUE #38 (the runtime image fit for a game): ASSESSED, NOT BUILT -- STOP by the Issue's own rule", "issue 38 the runtime image fit for a game ASSESSED, NOT BUILT (INPUT_PATH.md §12)",
                    "That a smaller stream probe is an acceptance image"):
            self.assertIn(tok, h, tok)
        r = plain(read(ROADMAP))
        self.assertIn("The image for the acceptance run — assessed, not built (GitHub Issue #38, 2026-09-21)", r)
        self.assertIn("a redesign, its own checkpoint (docs/research/INPUT_PATH.md §12)", r)
        d = read(DEVLOG)
        e = plain(d[d.rindex("## 2026-09-21 — Issue #38"):])
        for tok in ("ASSESSED, NOT BUILT; STOP by the Issue's own rule", "leaves no success stop", "a redesign of the service-path module",
                    "the Issue's own rule applies: STOP", "No code, no build, no BUILD_ID"):
            self.assertIn(tok, e, tok)

    def test_nothing_was_built_and_nothing_under_the_untouchable_paths_changed(self):
        self.assertIsNotNone(re.search(r"^BUILD_ID\s*:=\s*stream-0015$", read(MAKEFILE), re.M))
        # the twelve POCs of the assessment's base, plus the one Issue #39 built afterwards (its own checkpoint)
        self.assertEqual(sorted(p for p in os.listdir(os.path.join(ROOT, "poc")) if os.path.isdir(os.path.join(ROOT, "poc", p))),
                         ["gbp-av-service-probe", "gbp-init-irq-deliver-probe", "gbp-init-irq-probe", "gbp-init-irq-program-probe", "gbp-init-irq-service-probe",
                          "gbp-init-probe", "gbp-play-session", "gbp-probe", "gbp-video-capture-probe", "gbp-video-color-probe", "gbp-video-state-probe",
                          "gbp-video-stream-probe", "smoke-test"])
        r = subprocess.run(["git", "-C", ROOT, "cat-file", "-e", BASE_COMMIT], capture_output=True)
        if r.returncode != 0:
            self.skipTest("the base commit is not available in this checkout")
        r = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", BASE_COMMIT, "--", "src", "poc", "tools", "Makefile", "stimulus", "captures/fixtures",
                            "docs/protocol", "docs/hardware", "docs/research/HARDWARE_TESTS.md", "docs/research/EVIDENCE.md", "docs/research/UNKNOWNS.md"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        # nothing was built UNDER ISSUE #38; Issue #39 (2026-09-21) built the playable image: the session end in the service-path module (tests/host/test_play_image.py pins it), a new POC, its audit profile and its Swiss slot
        self.assertTrue(set(r.stdout.split()) <= {"src/gbp/gbp_vstate_probe.c", "src/gbp/gbp_vstate_probe.h", "src/gbp/gbp_session.c", "src/gbp/gbp_session.h", "poc/gbp-play-session/Makefile", "poc/gbp-play-session/source/main.c", "tools/poc_audit.py", "tools/swiss-layout.tsv", "Makefile"} | {"docs/research/UNKNOWNS.md"}, "changed against the base: " + r.stdout)
        r = subprocess.run(["git", "-C", ROOT, "ls-files", "--others", "--exclude-standard", "--", "src", "poc", "tools", "stimulus", "captures/fixtures", "docs/protocol", "docs/hardware"],
                           capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "", "untracked files under the guarded paths: " + r.stdout)


if __name__ == "__main__":
    unittest.main()
