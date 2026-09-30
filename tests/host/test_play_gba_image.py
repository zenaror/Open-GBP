"""tests/host/test_play_gba_image.py -- GitHub Issue #153 (the BUILD half): poc/gbp-play-gba, the GBA play image of Phase 7's E5, against HARDWARE_TESTS.md V31's design.

What main.c cannot be compiled or driven for on the host is read from its own text, by REACHABILITY from main() (not by a token grep: a token in a comment, a string or a dead function is not a call --
tests/host/test_v28_plans.py's helpers, the structural-test shape Issue #137 established). Checked here: the image is the V28 chassis' COPY (the frozen sources unchanged); the plan and the stores are the
tools' arithmetic; no research handler, transition machine, DMA mark, label or C-stick is linked or reachable; the audio is configured once by the plain setter at T256 A1 and the library default is
untouched; the DMA starts only through start_ready; the cartridge declaration is reachable only after the session and never from the pump; every record V31.3/V31.2/V31.4 names is written;
the Makefile, the identity and the reserved slot name.
"""
import hashlib
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
import v28budget as b  # noqa: E402
import poc_audit  # noqa: E402
import test_v28_plans as tp  # noqa: E402

POC = os.path.join(ROOT, "poc", "gbp-play-gba")
MAIN = os.path.join(POC, "source", "main.c")
MAKEFILE = os.path.join(POC, "Makefile")
V28 = os.path.join(ROOT, "poc", "gbp-audio-v28")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def stripped():
    return tp.strip_for_calls(read(MAIN))


def defs():
    return tp.function_defs(stripped())


class TheV28ImageIsUntouched(unittest.TestCase):
    """The play image is a COPY: poc/gbp-audio-v28 is an executed image whose sources are frozen and which reproduces at its own commit (Issue #153, V31.1)."""

    def test_the_frozen_sources_are_byte_identical_to_what_they_were(self):
        self.assertEqual(sha(os.path.join(V28, "source", "main.c")), "a821c331970cd11dd348c226c03c81999be990797cfc0bbc9ec43f06d40ec73b")
        self.assertEqual(sha(os.path.join(V28, "Makefile")), "4c6bfd1646d1f0197247463724f666a6f03e2f93816a754a6b330ced40affbf1")


class ThePlanAndTheStoresAreTheToolsArithmetic(unittest.TestCase):
    def test_the_stores_are_sized_for_the_wall_of_the_plan(self):
        m = read(MAIN)
        names, secs, cap = tp.python_plan("play_gba")
        wall = cap + b.WALL_ABOVE_SESSION_S
        self.assertEqual((cap, wall), (420, 485))
        for macro, want in (("PLAY_EVENT_RECORDS", b.need(wall, b.GUARD_EVENTS_PER_S)), ("PLAY_FRAME_RECORDS", b.need(wall, b.GUARD_FRAMES_PER_S)), ("CORR_CAP", b.need(wall, b.GUARD_CORR_PER_S))):
            got = int(re.search(r"#define %s\s+(\d+)u" % macro, m).group(1))
            self.assertEqual(got, want, macro)
        self.assertEqual((38315, 29100, 18915), (b.need(wall, 79), b.need(wall, 60), b.need(wall, 39)), "the V31.2 table's 300 s row")
        self.assertIn("#define V28_WALL_S          485u", m)
        self.assertIn("#define V28_SESSION_CAP_S   GBP_V28_PLAY_GBA_CAP_S", m)

    def test_every_store_is_smaller_than_run_57s_the_largest_allocation_that_booted_and_saved(self):
        m = read(MAIN)
        self.assertLess(int(re.search(r"#define PLAY_EVENT_RECORDS\s+(\d+)u", m).group(1)), 42107)
        self.assertLess(int(re.search(r"#define PLAY_FRAME_RECORDS\s+(\d+)u", m).group(1)), 31980)
        self.assertLess(int(re.search(r"#define CORR_CAP\s+(\d+)u", m).group(1)), 20787)
        self.assertLess(485, 533)

    def test_the_plan_is_the_play_plan_and_nothing_else(self):
        code = tp.code(read(MAIN))
        self.assertIn("&GBP_V28_PLAY_GBA", code)
        for other in ("GBP_V28_VALIDATION_RUN", "GBP_V28_PERCEPTUAL_NO_PHASE1", "GBP_V28_DIAG_3A_STALL", "GBP_V28_DIAG_LOSS"):
            self.assertNotIn(other, code)


class NoResearchMachineryIsLinkedOrReachable(unittest.TestCase):
    RESEARCH = ("gbp_atrans2", "gbp_v28_3a", "gbp_v28_3b", "gbp_v28_sweep", "gbp_v28_nulling", "gbp_v28_loss_(?!ctr)", "gbp_v28_dma", "v28_dma", "v28_cut", "v28_dispatch_phase_start", "console_font_8x16",
                "label_render", "draw_label_quad", "V28MARK", "V28DMA", "GBP_V28_DMA_MARK", "cs_edge", "cs_read", "CS_THRESHOLD", "cs_dead_until", "v28_control")

    def test_main_c_names_none_of_it(self):
        code = tp.code(read(MAIN))
        for tok in self.RESEARCH:
            self.assertNotRegex(code, r"\b%s" % (tok if "(?!" in tok else re.escape(tok)), tok)
        self.assertNotIn("GBP_V28_PLAN_", code, "no per-plan conditional: there is one plan")

    def test_the_makefile_links_none_of_it(self):
        srcs = self.srcs()
        for o in ("gbp_atrans2.c", "gbp_v28_3a.c", "gbp_v28_3b.c", "gbp_v28_sweep.c", "gbp_v28_nulling.c", "gbp_v28_loss.c", "gbp_v28_dma.c"):
            self.assertNotIn(o, srcs)
        for o in ("main.c", "gbp_aplay2.c", "gbp_adec2.c", "gbp_aresamp2.c", "gbp_walker.c", "gbp_play_under.c", "gbp_cartdecl.c", "gbp_alive.c", "sdlog.c"):
            self.assertIn(o, srcs)
        defines = re.search(r"^DEFINES\s*:=(.*?)\n\n", read(MAKEFILE), re.M | re.S).group(1)
        self.assertNotIn("DMA_MARK", defines)
        self.assertNotIn("PLAN", defines)

    def srcs(self):
        t = read(MAKEFILE)
        return re.search(r"^SRCS\s*:=\s*(.*)$", t, re.M).group(1).split()

    def test_every_source_the_makefile_names_exists_and_every_one_main_needs_is_named(self):
        for s in self.srcs():
            found = [os.path.join(d, s) for d in ("source", "../../src/common", "../../src/log", "../../src/gbp", "../../src/audio", "../../src/platform") if os.path.exists(os.path.join(POC, d, s))]
            self.assertTrue(found, "%s is named in SRCS and exists nowhere" % s)


class TheAudioIsConfiguredOnceAtT256A1(unittest.TestCase):
    def test_the_setter_and_not_the_transition_machine(self):
        d = defs()
        main = d["main"]
        self.assertEqual(len(re.findall(r"gbp_aplay2_set_target\s*\(", stripped())), 1)
        self.assertIn("gbp_aplay2_set_target(&ap2, PLAY_TARGET);", main)
        self.assertNotRegex(main, r"ap2\.ahead\s*=[^=]", "no direct write to the chain's AHEAD: the library's own value is asserted equal instead (review of the build half)")
        self.assertLess(main.index("gbp_aplay2_set_target(&ap2, PLAY_TARGET);"), main.index("gbp_vstate_probe_run("), "the chain is configured before the session")
        self.assertLess(main.index("gbp_aplay2_init(&ap2"), main.index("gbp_aplay2_set_target(&ap2, PLAY_TARGET);"))
        m = read(MAIN)
        self.assertIn("#define PLAY_TARGET  GBP_V28_T256", m)
        self.assertIn("#define PLAY_AHEAD   GBP_V28_A1", m)
        self.assertIn("_Static_assert(PLAY_TARGET == 4096u && PLAY_AHEAD == 1u", m)
        self.assertIn("ap2.step_pushes = gbp_v28_step_hook;", main)

    def test_the_library_default_is_untouched(self):
        h = read(os.path.join(ROOT, "src", "audio", "gbp_aplay2.h"))
        self.assertRegex(h, r"#define GBP_APLAY2_TARGET\s+\(\(uint32_t\)\(\(\(uint64_t\)GBP_ADEC2_RATE \* GBP_APLAY2_CUSHION_US\) / 1000000u\)\)\s+/\* 8192 \*/")
        self.assertIn("#define GBP_APLAY2_CUSHION_US   125000u", h)
        self.assertRegex(h, r"#define GBP_APLAY2_AHEAD\s+1u")
        self.assertIn("#define GBP_V28_T256   (GBP_V28_OLD_T256 * GBP_V28_NATIVE_RATIO)", read(os.path.join(ROOT, "src", "audio", "gbp_v28_ladder.h")))

    def test_the_dma_starts_only_through_start_ready_and_the_hand_off_callback_is_bare(self):
        d = defs()
        self.assertEqual(len(re.findall(r"AUDIO_StartDMA\s*\(", stripped())), 1)
        ls = d["live_step"]
        i = ls.index("AUDIO_StartDMA")
        self.assertIn("gbp_aplay2_start_ready(&ap2, adec2.count)", ls[:i], "never a literal >= 2u: unreachable at AHEAD 1 (RUN 48/49)")
        self.assertEqual(len(re.findall(r"ap2\.playing = 1u;", stripped())), 1)
        cb = d["live_dma_cb"]
        self.assertEqual(re.sub(r"\s+", " ", cb).strip(), "{ const uint8_t *c = gbp_aplay2_irq_handoff(&ap2, gettime()); AUDIO_InitDMA((u32)(size_t)c, GBP_APLAY2_CHUNK_BYTES); }",
                         "the callback is the perceptual image's: the hand-off and AUDIO_InitDMA, nothing else")
        self.assertIn("AUDIO_RegisterDMACallback(live_dma_cb);", d["main"])

    def test_the_hand_off_ordinal_is_stored_by_the_library_at_the_increment(self):
        c = read(os.path.join(ROOT, "src", "audio", "gbp_aplay2.c"))
        self.assertIn("p->under_handed[n] = p->handed + 1u;", c)
        self.assertIn("p->under_t[n] = t;", c)
        self.assertIn("if (n < GBP_APLAY2_UNDER_CAP) {", c)


class ThePhasesAreTimedAndNothingTheOperatorPressesMovesThem(unittest.TestCase):
    def test_no_c_stick_no_phase_complete_no_handler(self):
        code = tp.code(read(MAIN))
        self.assertNotRegex(code, r"gbp_walker_phase_complete")
        self.assertNotRegex(code, r"\bcs_\w+|\bCS_\w+", "no C-stick control: the sub-stick is read only as part of the input sample (the KEY record)")
        ls = defs()["live_step"]
        self.assertEqual(len(re.findall(r"gbp_walker_stop\s*\(", ls)), 1)
        self.assertEqual(len(re.findall(r"gbp_walker_tick\s*\(", ls)), 1)
        self.assertIn("gbp_walker_stop(&walker, now, 0)", ls)
        self.assertIn("gbp_walker_tick(&walker, now, 0)", ls)
        self.assertIn("GBP_WALKER_TICK_FINISHED", ls)

    def test_the_walker_starts_at_the_origin_with_the_play_plan(self):
        d = defs()
        self.assertIn("gbp_walker_start(&walker, V28_PLAN, live.tb_hz, live.t_origin);", d["live_tap_body"])


class EveryRecordTheDesignNamesIsWrittenAndReadable(unittest.TestCase):
    def test_the_records_in_main(self):
        m = tp.code(read(MAIN))
        raw = read(MAIN)
        for tok in ('"PLAYCFG plan=play_gba', "ENVMEM bss_end=", "ENVSTORE frames=", "ENVPLAY safety_s=", "V28C underruns=", "V28C2 discarded=", "V28CORR n=", "V28TAPS taps=", "V28PHC p=", "V28PHD p=",
                    "SYNCPE p=", "SYNCPH phase=", "V28END stop="):
            self.assertIn(tok, raw, tok)
        d = defs()["main"]
        for fn in ("gbp_play_under_fmt_startup", "gbp_play_under_summarize", "gbp_play_under_fmt_und", "gbp_play_under_fmt_sum", "gbp_cartdecl_fmt", "gbp_cartdecl_step", "v28_phase_report"):
            self.assertRegex(d, r"\b%s\s*\(" % fn, fn)
        self.assertIn("GBP_APLAY2_UNDER_CAP", d)
        self.assertIn("PLAYSTARTUP t_dma=none", raw, "a run whose DMA never started says so")
        self.assertIn("extern char __bss_end[];", m)

    def test_the_under_records_come_from_the_callbacks_arrays_after_the_dma_stopped(self):
        d = defs()["main"]
        self.assertLess(d.index("AUDIO_RegisterDMACallback(NULL);"), d.index("gbp_play_under_summarize"))
        self.assertIn("ap2.under_handed, ap2.under_t, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K", d)
        self.assertIn("ap2.under_t[q]", d)

    def test_the_startup_ring_and_ready_are_read_once_at_the_dma_start(self):
        ls = defs()["live_step"]
        self.assertEqual(len(re.findall(r"play_ring_at_dma\s*=", ls)), 1)
        self.assertLess(ls.index("play_ring_at_dma ="), ls.index("ap2.playing = 1u;"))
        self.assertLess(ls.index("play_ready_at_dma ="), ls.index("gbp_aplay2_irq_handoff(&ap2, now)"))

    def test_the_record_lines_fit_the_log_line(self):
        raw = read(MAIN)
        self.assertIn("#define LOG_LINE_LEN 256", raw)
        # the longest format string of the records this image adds, with every numeric field at its widest, stays under the ringlog's 248 usable characters
        env = re.search(r'"ENVMEM bss_end=%08lx arena1_lo=%08lx arena1_hi=%08lx arena1_free=%lu frames_bytes=%lu events_bytes=%lu "\s*"corr_bytes=%lu log_bytes=%lu xfb=3x%lu"', raw)
        self.assertIsNotNone(env)
        worst = "ENVMEM bss_end=%s arena1_lo=%s arena1_hi=%s arena1_free=%s frames_bytes=%s events_bytes=%s corr_bytes=%s log_bytes=%s xfb=3x%s" % (
            "ffffffff", "ffffffff", "ffffffff", "4294967295", "4294967295", "4294967295", "4294967295", "4294967295", "4294967295")
        self.assertLess(len(worst), 248)
        cfg = "PLAYCFG plan=play_gba navigate_s=4294967295 play_bound_s=4294967295 session_cap_s=4294967295 wall_s=4294967295 target=4294967295 ahead=4294967295 step=4294967295 startup_k=4294967295 cold_start=set_target mode=GBA"
        self.assertLess(len(cfg), 248)


class TheDeclarationIsMadeAfterTheSessionAndNeverReachesTheCartridge(unittest.TestCase):
    def test_it_is_in_main_after_the_probe_and_never_in_anything_the_pump_reaches(self):
        d = defs()
        main = d["main"]
        self.assertLess(main.index("gbp_vstate_probe_run("), main.index("gbp_cartdecl_step("), "the selection is after the session")
        self.assertLess(main.index("in_transport = 0;"), main.index("gbp_cartdecl_step("), "after the transport is torn down: nothing it does is forwarded to the cartridge")
        pump_side = tp.reachable_functions(d, "pump") | tp.reachable_functions(d, "live_tap") | tp.reachable_functions(d, "live_dma_cb")
        for fn in pump_side:
            self.assertNotIn("gbp_cartdecl", d[fn], "%s is reachable from the pump / tap / DMA callback and touches the declaration" % fn)
            self.assertNotIn("decl_draw", d[fn])
        self.assertEqual(len(re.findall(r"gbp_cartdecl_fmt\s*\(", stripped())), 1)
        self.assertEqual(len(re.findall(r"ringlog_printf\(&rl, \"%s\", decl\)", read(MAIN))), 1)

    def test_the_line_is_written_once_before_the_first_save_and_the_selection_is_locked(self):
        main = defs()["main"]
        i = main.index("gbp_cartdecl_fmt(")
        j = main.index("sdlog_save(")
        self.assertLess(i, j, "the declaration is in the ringlog BEFORE the save")
        self.assertIn("if (!decl_locked) {", main[i - 400:i])
        self.assertIn("decl_locked = 1;", main[i - 400:i])
        self.assertIn("if (!decl_locked) {\n                const uint32_t before", main.replace("\r", ""), "the selection stops changing once the save was asked")

    def test_the_default_is_undeclared(self):
        main = defs()["main"]
        self.assertIn("uint32_t decl_idx = GBP_CARTDECL_UNDECLARED;", main)
        self.assertIn("int decl_confirmed = 0, decl_locked = 0;", main)


class TheIdentityAndTheBuild(unittest.TestCase):
    def test_identity(self):
        m = read(MAIN)
        self.assertIn('#define TEST_ID "GBP-PLAY-002"', m)
        self.assertIn('#define OPENGBP_APP_NAME "gbp-play-gba"', m)
        mk = read(MAKEFILE)
        self.assertIn("APP_NAME   := gbp-play-gba", mk)
        self.assertIn("BUILD_ID   ?= vehicle-0001", mk)
        for tok in ("-DOPENGBP_APP_NAME", "-DOPENGBP_BUILD_ID", "-DOPENGBP_GIT_COMMIT"):
            self.assertIn(tok, mk)
        self.assertIn("IDENT test=%s app=%s build=%s commit=%s libogc=%s", m)
        self.assertIn('"OPENGBP-PLAY READY %s test=%s\\n"', m)
        self.assertIn('printf("  Build : %s   Commit: %s   Plan: play_gba\\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);', m)

    def test_warnings_are_enabled_and_none_is_silenced(self):
        mk = read(MAKEFILE)
        self.assertIn("-Wall -Wextra -Wshadow", mk)
        self.assertNotIn("-w ", mk.replace("-Wall", ""))
        self.assertNotIn("-Wno-", mk)
        self.assertNotRegex(read(MAIN), r"#pragma\s+GCC\s+diagnostic")

    def test_clean_removes_its_own_directory_and_the_output_is_outside_git(self):
        mk = read(MAKEFILE)
        self.assertIn("@rm -rf $(ROOT)/build/poc/$(APP_NAME)", mk)
        self.assertIn("OUTDIR  ?= $(ROOT)/build/poc/$(APP_NAME)", mk)

    def test_the_slot_is_pinned_to_the_recorded_hash_and_nothing_else_moved(self):
        """AMENDED ON TOP (Hardware Issue #154, 2026-09-30): at the build half the slot name was reserved and absent from the manifest; the Orchestrator then ordered the staging and the
        row carries exactly the hash HARDWARE_TESTS V31.8 records. Nothing else in the manifest moved (tests/host/test_swiss_export.py pins the frozen set)."""
        tsv = read(os.path.join(ROOT, "tools", "swiss-layout.tsv"))
        rows = [l.split("\t") for l in tsv.split("\n") if l and not l.startswith("#")]
        mine = [r for r in rows if "gbp-play-gba" in "\t".join(r)]
        self.assertEqual(mine, [["28", "vehicle", "gbp-play-gba", "gbp-play-gba.dol", "gbp-play-gba", "vehicle", "1", "a02bcfa3b84ccd363d7bad54c8e72411d9f2e9a49595963903d1feeac4acf5d2"]])
        self.assertIn("a02bcfa3b84ccd363d7bad54c8e72411d9f2e9a49595963903d1feeac4acf5d2", read(os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")))


class TheSessionFlowSurvivesTheCopy(unittest.TestCase):
    """Review of the build half: the structural tests above missed deleting these. Each is a line of the session flow whose removal no host run can show."""

    def test_the_end_of_the_session_stops_the_dma_before_the_feed_does(self):
        ls = defs()["live_step"]
        self.assertIn("ending = live_end || (sync_started && gbp_walker_finished(&walker));", ls)
        self.assertLess(ls.index("ending = live_end"), ls.index("gbp_aplay2_produce("), "the end is tested before the production branch")
        self.assertIn("if (!ending && (live.phase == GBP_ALIVE_WINDOW", ls)
        self.assertIn("} else if (ai_started && !ai_stopped && ending) {", ls)
        self.assertEqual(len(re.findall(r"ai_stopped = 1;", ls)), 1)
        self.assertEqual(len(re.findall(r"AUDIO_StopDMA\s*\(", ls)), 1)
        self.assertEqual(len(re.findall(r"play_t_last_step = now;", ls)), 1)
        self.assertLess(ls.index("play_t_last_step = now;"), ls.index("gbp_aplay2_produce("))

    def test_the_walker_finish_ends_the_session_and_the_edges_are_logged(self):
        d = defs()
        ls = d["live_step"]
        self.assertIn("if (gbp_walker_finished(&walker)) live_end = 1;", ls)
        self.assertIn("} else if (session.end_requested) {\n        live_end = 1;", ls)
        self.assertIn("syncpe_edges();", ls)
        self.assertIn("z_can_act = 1; session.end_requested = 0;", ls)
        self.assertIn("syncpe_edges", tp.reachable_functions(d, "pump"))
        self.assertIn("if (sync_started && gbp_walker_finished(&walker)) live_end = 1;", d["live_tap_body"])

    def test_the_under_records_are_written_for_every_recorded_underrun_with_the_right_stamps(self):
        main = defs()["main"]
        self.assertIn("for (q = 0u; q < us.recorded; q++) {", main)
        self.assertIn("gbp_play_under_fmt_startup(rec, sizeof rec, t_ai_start, GBP_PLAY_STARTUP_K, play_ring_at_dma, play_ready_at_dma);", main)
        self.assertIn("t_feed_end = play_t_last_step + tb_hz / 100u;", main)
        self.assertIn("ap2.under_t, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, t_feed_end);", main)
        self.assertIn("ap2.under_handed[q] > GBP_PLAY_STARTUP_K && ap2.under_t[q] > t_feed_end", main, "the per-record flag uses the summary's own rule")

    def test_the_final_screen_ignores_the_games_buttons_and_never_loses_an_unsaved_log(self):
        main = defs()["main"]
        i = main.index("uint32_t settle")
        self.assertIn("PAD_ButtonsHeld(0) == 0u", main[i:], "waits for every button to be released")
        self.assertLess(main.index("PAD_ButtonsHeld(0) == 0u"), main.index("gbp_cartdecl_step("))
        self.assertIn("settle < 300u", main, "the wait is bounded")
        self.assertIn("settle < 60u", main, "and every edge is ignored for a second afterwards")
        self.assertIn("if ((saved && (down & PAD_BUTTON_START)) || start_held >= 90u) break;", main, "START exits at once only after a save; else it takes a 1.5 s hold")
        self.assertNotRegex(main, r"if \(down & PAD_BUTTON_START\) break;")

    def test_after_the_lock_the_screen_shows_what_the_log_says(self):
        main = defs()["main"]
        i = main.index("decl_locked = 1;")
        self.assertIn("if (!decl_confirmed) decl_idx = GBP_CARTDECL_UNDECLARED;", main[i:i + 200])
        self.assertLess(main.index("if (!decl_confirmed) decl_idx = GBP_CARTDECL_UNDECLARED;"), main.index("gbp_cartdecl_fmt("))

    def test_no_final_screen_line_exceeds_the_console_width(self):
        raw = read(MAIN)
        i = raw.index("#define DECL_ROW 16")
        block = raw[i:raw.index("int main(void)")]
        for m in re.finditer(r'printf\("((?:[^"\\]|\\.)*)"', block):
            text = m.group(1).replace("\\n", "").replace("\\x1b", "\x1b")
            if "\x1b[" in text and ";0H" in text and len(text) < 12:
                continue
            widest = len(re.sub(r"%l?[ud]|%-?(\d+)s|%s", lambda mm: " " * (int(mm.group(1)) if mm.group(1) else (22 if mm.group(0) == "%s" else 2)), text))
            self.assertLessEqual(widest, 79, text)


OUT = os.path.join(ROOT, "build", "poc", "gbp-play-gba")


class TheAudit(unittest.TestCase):
    """HARDWARE_TESTS.md V31.5: the poc_audit profile of the new POC (`vehicle`: the `live` profile with the V28 chassis' chain named) and the interrupt path's identity with the physically
    validated GBP-VIDEO-001 build's. The listings need the image built in this checkout (skipped, with the ledger's reason, otherwise); the profile's own shape is pinned from its source below."""

    def test_profile_vehicle_reports_no_finding(self):
        audit = os.path.join(OUT, "audit")
        if not os.path.isdir(audit) or not os.path.isfile(os.path.join(audit, "elf.nm.txt")):
            self.skipTest("%s is not built in this checkout" % "gbp-play-gba")
        findings = poc_audit.audit_dir(audit, "vehicle")[0]
        self.assertEqual(findings, [])
        for other in ("live", "sync"):
            self.assertNotEqual(poc_audit.audit_dir(audit, other)[0], [], "the %s profile must FAIL this image: a profile that passes everything pins nothing" % other)

    def test_the_handlers_match_GBP_VIDEO_001(self):
        for arm in ("ext", "base"):
            path = os.path.join(OUT, "isr-audit-%s.txt" % arm)
            if not os.path.isfile(path):
                self.skipTest("%s is not built in this checkout" % "gbp-play-gba")
            ref = os.path.join(ROOT, "build", "poc", "gbp-video-capture-probe", "isr-audit-%s.txt" % arm)
            if not os.path.isfile(ref):
                self.skipTest("%s is not built in this checkout" % "gbp-video-capture-probe")
            self.assertEqual(read(path), read(ref), arm)

    def test_the_profile_names_what_changed(self):
        p = poc_audit.PROFILES["vehicle"]
        for o in ("gbp_aplay2.o", "gbp_adec2.o", "gbp_aresamp2.o", "gbp_walker.o", "gbp_play_under.o", "gbp_cartdecl.o"):
            self.assertIn(o, p["required_objects"])
        for o in ("gbp_aplay.o", "gbp_adec.o", "gbp_aresamp.o"):
            self.assertNotIn(o, p["required_objects"])
        for f in ("sdlog_stream_open", "sdlog_stream_write", "sdlog_stream_close"):
            self.assertIn(f, p["forbidden_symbols"], "no sidecar: the streaming writer is banned again")
            self.assertIn(f, p["main_must_not_call"])
        for f in ("gbp_aplay2_mute", "gbp_aplay2_drop_front", "gbp_aplay2_arm_l2"):
            self.assertEqual(p["symbol_callers"][f], {}, f)
        for f in ("gbp_atrans2_begin", "gbp_atrans2_step"):
            self.assertIn(f, p["elf_forbidden"], "no transition machine is linked")
        self.assertEqual(p["symbol_callers"]["gbp_aplay2_set_target"], {"main": 1}, "the configuration is ONE call, in main")
        self.assertEqual(p["symbol_callers"]["gbp_aplay2_start_ready"], {"pump": 1})
        self.assertEqual(p["symbol_callers"]["gbp_cartdecl_fmt"], {"main": 1})
        self.assertEqual(p["symbol_callers"]["gbp_walker_tick"], {"pump": 1})
        self.assertEqual(p["symbol_callers"]["gbp_walker_stop"], {"pump": 1})
        for o in ("gbp_aplay2.o", "gbp_adec2.o", "gbp_aresamp2.o", "gbp_walker.o"):
            self.assertEqual(p["object_must_not_reference"][o], poc_audit._CAPTURE_SYMBOLS, "%s keeps the capture family's bar" % o)
        self.assertTrue(set(p["object_may_only_reference"]) >= {"gbp_aplay2.o", "gbp_adec2.o", "gbp_aresamp2.o", "gbp_walker.o", "gbp_play_under.o", "gbp_cartdecl.o"})
        self.assertEqual(p["object_may_only_reference"]["gbp_walker.o"], ("memset",))
        self.assertEqual(p["irq_write_sites"], poc_audit.PROFILES["live"]["irq_write_sites"], "every interrupt-path pin of live is part of this profile")
        self.assertEqual(p["control_write_sites"], poc_audit.PROFILES["live"]["control_write_sites"])


class TheMakefileTargets(unittest.TestCase):
    def test_the_targets_exist_and_are_phony_and_nothing_is_staged(self):
        mk = read(os.path.join(ROOT, "Makefile"))
        phony = re.search(r"^\.PHONY:.*$", mk, re.M).group(0)
        for t in ("vehicle", "vehicle-audit", "vehicle-dolphin"):
            self.assertIn(" %s" % t, phony + " ")
            self.assertRegex(mk, re.compile(r"^%s:" % re.escape(t) if t != "vehicle-audit" else r"\$\(eval \$\(call ISR_COMPARE_TARGET,vehicle-audit,\$\(VEHICLE_OUT\)\)\)", re.M))
        self.assertIn("POC_AUDIT_RULE,$(VEHICLE_OUT),vehicle", mk)
        self.assertIn("make --no-print-directory -C poc/gbp-play-gba clean; make --no-print-directory -C poc/gbp-play-gba", mk, "each build removes the whole output directory first")
        self.assertIn('-e GIT_DIRTY="$(VEHICLE_GIT_DIRTY)"', mk)
        self.assertIn("git status --porcelain --untracked-files=normal -- src poc/gbp-play-gba tools", mk, "an untracked source makes the image -dirty")
        self.assertIn("git -C \"$(CURDIR)\" status --porcelain --untracked-files=normal -- ../../src ../../poc/gbp-play-gba ../../tools", read(MAKEFILE))
        self.assertNotIn("gbp-play-gba", re.search(r"^POCS\s*:=.*$", mk, re.M).group(0), "`make build` does not build it (as with poc/gbp-audio-v28)")
        self.assertIn("'OPENGBP-PLAY RESULT status=abort_inconsistent stop=failure service=0 deliveries=0 restore=1'", mk)


if __name__ == "__main__":
    unittest.main()
