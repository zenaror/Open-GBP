"""
tests/host/test_play_image.py — GitHub Issue #39: the playable runtime image
(poc/gbp-play-session, GBP-PLAY-001, play-0001), pinned to its sources.

What is pinned, and why each pin exists:
  - THE INPUT PATH AND THE KEY RECORD ARE BYTE-IDENTICAL to stream-0015's: the
    text of keylog_emit() and input_step() is diffed against
    poc/gbp-video-stream-probe/source/main.c; the descriptor, the policy and
    the KEY line format are the src/gbp data both images share (the routing
    FACT of §V7.4 was established with them);
  - THE SUBTRACTION: no witness bound, no witness store, no sampler, no VI
    trace, no disposition trace, no sidecar; the witness MODULE stays linked
    for the service-path module's predicates and main names none of it;
  - THE SESSION END: the module's new stop / status / config field and its
    precedence in CHECK_ADMISSION; the POC's hold and its wiring from the pump
    slot; the unit tests that drive it;
  - THE SIZING: the constants, the arithmetic behind the bounds, the ringlog
    reserve that covers the post-run report (462 lines in RUN 17);
  - THE AUDIT PROFILE is a real check: on the real listings (when built) the
    `play` profile passes this image, fails the stream image, and the `stream`
    profile fails this image;
  - THE PLUMBING: the POC list, the audit rules, the Dolphin target with its
    ceiling stated, the Swiss slot 13, the unit-test registration;
  - THE IDENTITY, when built: build-info and the DOL agree, BUILD_ID play-0001.
"""
import hashlib
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
PLAY_MAIN = os.path.join(ROOT, "poc", "gbp-play-session", "source", "main.c")
PLAY_MAKEFILE = os.path.join(ROOT, "poc", "gbp-play-session", "Makefile")
STREAM_MAIN = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c")
PROBE_H = os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.h")
PROBE_C = os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.c")
SESSION_H = os.path.join(ROOT, "src", "gbp", "gbp_session.h")
SESSION_C = os.path.join(ROOT, "src", "gbp", "gbp_session.c")
VSTATE_H = os.path.join(ROOT, "src", "gbp", "gbp_vstate.h")
UNIT_VS = os.path.join(ROOT, "tests", "unit", "test_gbp_video_state.c")
UNIT_SESSION = os.path.join(ROOT, "tests", "unit", "test_gbp_session.c")
UNIT_MAKEFILE = os.path.join(ROOT, "tests", "unit", "Makefile")
TOP_MAKEFILE = os.path.join(ROOT, "Makefile")
AUDIT = os.path.join(ROOT, "tools", "poc_audit.py")
LAYOUT = os.path.join(ROOT, "tools", "swiss-layout.tsv")
PLAY_OUT = os.path.join(ROOT, "build", "poc", "gbp-play-session")
STREAM_OUT = os.path.join(ROOT, "build", "poc", "gbp-video-stream-probe")
SRC_HZ = 59.727


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def define(src, name):
    m = re.search(r"^#define\s+%s\s+(\S+)" % re.escape(name), src, re.M)
    assert m, name
    return m.group(1)


def num(s):
    return int(s.rstrip("uUlL"))


def function_text(src, name):
    """From the DEFINITION `static void name(...)\n{` (not a forward declaration) to its closing brace."""
    m = re.search(r"^static void %s\([^;{]*\)\n\{" % re.escape(name), src, re.M)
    assert m, name
    j = src.index("\n}\n", m.start()) + 3
    return src[m.start():j]


class TheInputPathAndTheKeyRecordAreByteIdentical(unittest.TestCase):
    def test_the_two_functions_are_the_text_of_stream_0015s(self):
        p, s = read(PLAY_MAIN), read(STREAM_MAIN)
        for name in ("keylog_emit", "input_step"):
            self.assertEqual(function_text(p, name), function_text(s, name), name)
        # the record they emit is the shared format, taken and admitted by the shared module
        for tok in ("ringlog_printf(keylog_rl, GBP_INPUT_EVENT_FMT, GBP_INPUT_EVENT_ARGS(&e));",
                    "gbp_input_keylog_admit((uint32_t)keylog_rl->count, (uint32_t)keylog_rl->capacity, KEYLOG_TAIL_RESERVE)",
                    "gbp_input_init(&in_state, &GBP_INPUT_POLICY_DEFAULT, &GBP_KEYPAD_DESCRIPTOR, tb_hz);",
                    "act = gbp_input_step(&in_state, t, &s, t_poll);"):
            self.assertIn(tok, p, tok)
            self.assertIn(tok, s, tok)
        # the input step is the FIRST statement of pump(), as in stream-0015; the session step follows it
        pump = function_text(p, "pump")
        body = pump[pump.index("(void)user;"):]
        self.assertRegex(body, r"\(void\)user;\s*\n\s*/\*[^*]*\*/\s*\n\s*input_step\(\);\s*\n\s*/\*[^*]*\*/\s*\n\s*session_step\(\);")
        # the same pad-bit and error-code assertions guard the same module
        for tok in ("GBP_PAD_BUTTON_Z == PAD_BUTTON_Z", "GBP_PAD_ERR_NO_CONTROLLER == PAD_ERR_NO_CONTROLLER"):
            self.assertIn(tok, p)

    def test_the_reserve_and_the_ringlog_are_the_only_input_constants_that_differ(self):
        p, s = read(PLAY_MAIN), read(STREAM_MAIN)
        self.assertEqual(define(s, "KEYLOG_TAIL_RESERVE"), "64u")
        self.assertEqual(define(p, "KEYLOG_TAIL_RESERVE"), "640u")
        self.assertEqual(define(s, "LOG_LINES"), "1024")
        self.assertEqual(define(p, "LOG_LINES"), "8192")
        self.assertEqual(define(p, "LOG_LINE_LEN"), define(s, "LOG_LINE_LEN"))
        # the reason, stated where the constant is
        self.assertIn("the reserve must cover the WHOLE\n * post-run report", p)
        self.assertIn("462 lines in RUN 17", p)
        self.assertIn('_Static_assert(KEYLOG_TAIL_RESERVE >= 600u', p)
        self.assertIn('_Static_assert(LOG_LINES - KEYLOG_TAIL_RESERVE >= 7000u', p)
        # 8192 - 640 leaves the KEY headroom of a long session; the ringlog drops, it does not overwrite
        self.assertGreaterEqual(8192 - 640 - 240, 7000)
        self.assertIn("rl->dropped++;", read(os.path.join(ROOT, "src", "log", "ringlog.c")))


class TheSubtraction(unittest.TestCase):
    def test_no_witness_is_bound_and_no_instrumentation_is_named(self):
        p = read(PLAY_MAIN)
        self.assertNotIn("cfg.witness", p.replace("cfg.witness stays NULL", ""))
        for tok in ("gbp_vwitness_init", "witness_store", "gbp_vfull", "gbp_vvi", "gbp_vdisp", "gbp_vidxdump",
                    "sdlog_stream_open", "STREAM_WIT_NOT_BEFORE_MS", "gbp_vwitness_streak_gated", "tex_life"):
            self.assertNotIn(tok, p, tok)
        for inc in ("gbp_vwitness.h", "gbp_vidxdump.h", "gbp_vdisp.h", "gbp_vdispdump.h", "gbp_vfull.h", "gbp_vfulldump.h", "gbp_vvi.h", "gbp_vvidump.h"):
            self.assertNotIn('#include "%s"' % inc, p, inc)
        self.assertIn('#include "gbp_session.h"', p)
        # what replaced the trace's two runtime roles: the take ordinal and the first-frame record
        self.assertIn("tex_seq[buf] = ++take_seq;", p)
        self.assertIn("if (best < 0 || (tex_seq[i] != 0u && (best_seq == 0u || tex_seq[i] < best_seq))) {", p)
        self.assertIn("first_real.t_decision = t_dec;", p)
        # the draw-done callback reads no clock any more
        self.assertIn("static void on_draw_done(void)\n{\n    (void)gbp_vpresent_draw_done(&present);\n}", p)

    def test_the_makefile_links_no_instrumentation_but_keeps_the_witness_module(self):
        mk = read(PLAY_MAKEFILE)
        srcs = re.search(r"^SRCS := (.*)$", mk, re.M).group(1).split()
        for gone in ("gbp_vidxdump.c", "gbp_vdisp.c", "gbp_vdispdump.c", "gbp_vfull.c", "gbp_vfulldump.c", "gbp_vvi.c", "gbp_vvidump.c"):
            self.assertNotIn(gone, srcs, gone)
        for kept in ("gbp_vwitness.c", "gbp_vcolor.c", "gbp_vstate_probe.c", "gbp_input.c", "gbp_session.c", "hsp_backend_irq.c", "sdlog.c"):
            self.assertIn(kept, srcs, kept)
        stream_srcs = re.search(r"^SRCS := (.*)$", read(os.path.join(ROOT, "poc", "gbp-video-stream-probe", "Makefile")), re.M).group(1).split()
        self.assertEqual(set(stream_srcs) - set(srcs), {"gbp_vidxdump.c", "gbp_vdisp.c", "gbp_vdispdump.c", "gbp_vfull.c", "gbp_vfulldump.c", "gbp_vvi.c", "gbp_vvidump.c"})
        self.assertEqual(set(srcs) - set(stream_srcs), {"gbp_session.c"})
        self.assertIsNotNone(re.search(r"^BUILD_ID\s*:=\s*play-0001$", mk, re.M))
        self.assertIsNotNone(re.search(r"^APP_NAME\s*:=\s*gbp-play-session$", mk, re.M))
        self.assertIn("-Wall -Wextra -Wshadow", mk)

    def test_policy_a_and_the_gx_order_are_stream_0015s(self):
        p, s = read(PLAY_MAIN), read(STREAM_MAIN)
        order = ("draw_quad();", "GX_SetDrawDone();", "GX_CopyDisp(xfb_stream_buf[xfb], GX_TRUE);", "GX_Flush();",
                 "VIDEO_SetNextFramebuffer(xfb_stream_buf[xfb]);", "VIDEO_Flush();", "gbp_vpresent_xfb_handed(&present, xfb);")
        for src in (p, s):
            sr = function_text(src, "submit_ready")
            pos = [sr.index(t) for t in order]
            self.assertEqual(pos, sorted(pos))
            self.assertIn("xfb = gbp_vpresent_xfb_target(&present, cur);", sr)
            self.assertIn("if (!gbp_vpresent_submit(&present, buf))", sr)
            self.assertNotIn("VIDEO_WaitVSync(", sr)        # nothing waits in the present path (the comments say so, and so does the code)
        self.assertIn("if (!gbp_vqueue_commit(&vq, gbp_vqueue_still_valid(&vq, &conv.desc), conv.ticks)) {", p)


class TheSessionEnd(unittest.TestCase):
    def test_the_module_has_the_stop_the_status_and_the_flag(self):
        h, c = read(PROBE_H), read(PROBE_C)
        self.assertRegex(h, r"GBP_VSTATE_STOP_WITNESS_STORE_FULL,\s*\n(?:\s*/\*(?:[^*]|\*(?!/))*\*/\s*\n)?\s*GBP_VSTATE_STOP_SESSION_END\n\};")
        self.assertRegex(h, r"GBP_VSTATE_ANOMALY_REARM_STATE,\s*\n(?:\s*/\*(?:[^*]|\*(?!/))*\*/\s*\n)?\s*GBP_VSTATE_OK_SESSION_ENDED\n\} gbp_vstate_status;")
        self.assertIn("    const int *session_end;", h)
        self.assertIn('case GBP_VSTATE_STOP_SESSION_END: return "session_end";', c)
        self.assertIn('case GBP_VSTATE_OK_SESSION_ENDED: return "ok_session_ended";', c)
        self.assertIn('    case GBP_VSTATE_OK_SESSION_ENDED: return "ok";', c)
        self.assertIn("if (res->stop == GBP_VSTATE_STOP_SESSION_END) return GBP_VSTATE_OK_SESSION_ENDED;", c)
        # the precedence: after the safety budget and the two store caps, before the witness, the colour, the target and the guard
        i_safety = c.index('"S5_safety_budget"')
        i_frames = c.index('"S5_frame_store_cap"')
        i_events = c.index('"S5_event_store_cap"')
        i_session = c.index('"S5_session_end"')
        i_witness = c.index('"S5_witness_store_full"')
        i_target = c.index('"S5_target"')
        i_delivery = c.index('"S5_delivery_cap"')
        self.assertTrue(i_safety < i_frames < i_events < i_session < i_witness < i_target < i_delivery)
        self.assertIn("if (cfg->session_end && *cfg->session_end) {", c)
        self.assertIn('finish(x, GBP_VSTATE_OK_SESSION_ENDED, "-", "S5_session_end", GBP_VSTATE_STOP_SESSION_END);', c)
        # one flag read; no device access, no wait, no log line inside the block
        blk = c[c.index("if (cfg->session_end && *cfg->session_end) {"):c.index("/* 3a. GBP-VIDEO-004's indexed retention")]
        for forbidden in ("t->poll_intsr", "t->read_block", "t->read_pi", "t->write", "gbp_regwrite", "ringlog_printf", "now64(", "now32("):
            self.assertNotIn(forbidden, blk, forbidden)

    def test_the_module_is_pure_and_the_poc_wires_it_from_the_pump_slot(self):
        sh, sc, p = read(SESSION_H), read(SESSION_C), read(PLAY_MAIN)
        self.assertIn("int gbp_session_sample(struct gbp_session *s, int held, uint64_t now);", sh)
        code = re.sub(r"/\*.*?\*/", "", sc, flags=re.S)
        self.assertNotIn("#include", code.replace('#include "gbp_session.h"', ""))
        self.assertNotIn("memset", code)
        self.assertNotIn("(", code.replace("gbp_session_init(struct gbp_session *s, uint64_t hold_ticks)", "").replace(
            "gbp_session_sample(struct gbp_session *s, int held, uint64_t now)", "").replace("if (", "").replace("{ s->samples_after++; return 0; }", ""))
        self.assertIn("if (now - s->t_hold_begin >= s->hold_ticks) {", sc)
        self.assertIn("if (s->end_requested) { s->samples_after++; return 0; }", sc)
        self.assertEqual(define(p, "PLAY_SESSION_END_HOLD_MS"), "250u")
        self.assertIn("session_hold_ticks = ((uint64_t)tb_hz * PLAY_SESSION_END_HOLD_MS) / 1000u;", p)
        self.assertIn("gbp_session_init(&session, session_hold_ticks);", p)
        self.assertIn("cfg.session_end = &session.end_requested;", p)
        st = function_text(p, "session_step")
        self.assertIn("if (!t || !in_state.base) return;", st)
        self.assertIn("(PAD_ButtonsHeld(PAD_CHAN0) & PAD_BUTTON_Z) ? 1 : 0", st)
        self.assertIn("t->ticks64(t->ctx)", st)
        self.assertNotIn("PAD_ScanPads", st)       # no second scan: the sample input_step() took
        self.assertNotIn("gettime", st)
        # the records
        for tok in ('"SESSION end=Z hold_ms=%lu hold_ticks=%llu requested=%d', "OPENGBP-PLAY SESSION requested=%d", "OPENGBP-PLAY RESULT status=%s"):
            self.assertIn(tok, p, tok)

    def test_the_unit_tests_drive_the_stop_through_the_real_run_loop(self):
        t = read(UNIT_VS)
        for name in ("test_session_end_is_a_success", "test_session_end_never_interrupts_a_transaction", "test_session_end_loses_to_the_safety_budget",
                     "test_session_end_is_the_status_whatever_the_detector_saw", "test_session_end_absent_changes_nothing"):
            self.assertIn("static void %s(void)" % name, t, name)
            self.assertIn("    %s();" % name, t, name)
        for tok in ("CHECK(res.stop == GBP_VSTATE_STOP_SESSION_END);", "CHECK(res.status == GBP_VSTATE_OK_SESSION_ENDED);",
                    'CHECK(strcmp(res.teardown_variant, "S5_session_end") == 0);', "CHECK(res.a.pi_cleanup_performed == 1);",
                    "CHECK(res.deliveries == 7u);", "CHECK(res.acks == 7u);", "CHECK(res.rearms == 7u);",
                    "CHECK(res.stop == GBP_VSTATE_STOP_SAFETY_BUDGET);", "CHECK(defaults.session_end == 0);",
                    "CHECK(GBP_VSTATE_STOP_SESSION_END == GBP_VSTATE_STOP_WITNESS_STORE_FULL + 1);",
                    "CHECK(GBP_VSTATE_OK_SESSION_ENDED == GBP_VSTATE_ANOMALY_REARM_STATE + 1);"):
            self.assertIn(tok, t, tok)
        self.assertIn("test_gbp_session", read(UNIT_MAKEFILE))
        s = read(UNIT_SESSION)
        for name in ("test_a_tap_is_released_before_the_bound", "test_a_hold_reaching_the_bound_requests_once", "test_the_clock_may_sit_high"):
            self.assertIn(name, s)


class TheSizing(unittest.TestCase):
    def test_the_bounds_and_their_arithmetic(self):
        p = read(PLAY_MAIN)
        safety = num(define(p, "PLAY_SAFETY_SECONDS"))
        deliveries = num(define(p, "PLAY_MAX_DELIVERIES"))
        frames = num(define(p, "PLAY_FRAME_RECORDS"))
        events = num(define(p, "PLAY_EVENT_RECORDS"))
        self.assertEqual((safety, deliveries, frames, events), (720, 6000000, 45056, 16384))
        self.assertGreaterEqual(safety, 300 + 300)                      # five minutes of play after a five-minute boot
        self.assertGreater(frames / SRC_HZ, safety)                     # the frame store outlasts the budget: 754 s
        self.assertEqual(round(frames / SRC_HZ), 754)
        self.assertGreater(deliveries, safety * 6314)                   # the guard above RUN 17's rate: 4.55 M
        self.assertEqual(round(deliveries / 6314.0), 950)
        self.assertGreaterEqual(events, safety * 4)
        # what it costs over the contract, stated in the source
        self.assertEqual((frames - 16384) * 192, 5505024)
        self.assertEqual((events - 4096) * 64, 786432)
        self.assertIn("+5 505 024 B", p)
        self.assertIn("+786 432 B", p)
        self.assertEqual(define(read(VSTATE_H), "GBP_VSTATE_MAX_FRAMES"), "16384u")
        for tok in ("_Static_assert(PLAY_FRAME_RECORDS >= PLAY_SAFETY_SECONDS * 60u,", "_Static_assert(PLAY_EVENT_RECORDS >= PLAY_SAFETY_SECONDS * 4u,",
                    "_Static_assert(PLAY_MAX_DELIVERIES >= PLAY_SAFETY_SECONDS * 6314u,",
                    "static struct gbp_vstate_frame frame_store[PLAY_FRAME_RECORDS];", "static struct gbp_vstate_event event_store[PLAY_EVENT_RECORDS];",
                    "cfg.hard_wallclock_s = PLAY_SAFETY_SECONDS;", "cfg.max_deliveries = PLAY_MAX_DELIVERIES;", "gbp_vstate_config_disable_time_target(&cfg);"):
            self.assertIn(tok, p, tok)
        # the model caps at the CONFIGURED capacity, so a larger store is honoured, not ignored
        vs = read(os.path.join(ROOT, "src", "gbp", "gbp_vstate.c"))
        self.assertIn("if (s->frames_n >= s->frames_cap) {", vs)
        self.assertIn("if (s->events_n >= s->events_cap) {", vs)
        self.assertIn('if (s->frames_cap      < GBP_VSTATE_MAX_FRAMES)          return "frames_cap";', vs)


class TheAuditProfileIsARealCheck(unittest.TestCase):
    def test_the_profile_exists_and_forbids_what_the_stream_profile_requires(self):
        import poc_audit
        play, stream = poc_audit.PROFILES["play"], poc_audit.PROFILES["stream"]
        for obj in ("gbp_vidxdump.o", "gbp_vfull.o", "gbp_vfulldump.o", "gbp_vvi.o", "gbp_vvidump.o", "gbp_vdisp.o", "gbp_vdispdump.o"):
            self.assertIn(obj, play["forbidden_objects"], obj)
        for obj in ("gbp_vidxdump.o", "gbp_vfull.o", "gbp_vfulldump.o", "gbp_vvi.o", "gbp_vvidump.o"):
            self.assertIn(obj, stream["required_objects"], obj)
        for obj in ("gbp_vwitness.o", "gbp_input.o", "gbp_session.o", "gbp_vstate_probe.o", "hsp_backend_irq.o", "main.o"):
            self.assertIn(obj, play["required_objects"], obj)
        self.assertEqual(play["object_may_only_reference"]["gbp_session.o"], ())
        self.assertEqual(play["prefix_exempt_objects"]["gbp_vstate_probe.o"], ("gbp_vwitness_",))
        self.assertIn("gbp_vwitness_", play["forbidden_symbol_prefixes"])
        self.assertEqual(play["symbol_callers"]["gbp_session_sample"], {"pump": 1})
        self.assertEqual(play["symbol_callers"]["PAD_ButtonsHeld"], {"pump": 2})
        self.assertEqual(play["symbol_callers"]["PAD_ScanPads"], {"main": 2, "pump": 1})
        self.assertEqual(play["symbol_callers"]["gbp_vqueue_publish"], {"gbp_vstate_probe_run": 1})
        self.assertEqual(play["symbol_callers"]["gettime"], {"h_ticks64": 1, "main": 5, "pump": 2, "submit_ready": 1})
        self.assertEqual(play["symbol_callers"]["gbp_vwitness_init"], {})
        self.assertEqual(play["symbol_callers"]["sdlog_stream_open"], {})
        for s in ("gbp_vwitness_stage", "gbp_vwitness_place", "gbp_vwitness_commit", "gbp_vwitness_note_ticks"):
            self.assertEqual(play["symbol_callers"][s], stream["symbol_callers"][s], s)
        self.assertEqual(play["irq_write_sites"], stream["irq_write_sites"])
        self.assertEqual(play["intsr_store_sites"], stream["intsr_store_sites"])
        self.assertIn("sdlog_stream_open", play["main_must_not_call"])
        self.assertIn("gbp_session_sample", play["main_must_call"])

    @unittest.skipUnless(os.path.isfile(os.path.join(PLAY_OUT, "audit", "elf.nm.txt")) and os.path.isfile(os.path.join(STREAM_OUT, "audit", "elf.nm.txt")),
                         "run `make play-audit stream-audit` to audit the real listings")
    def test_on_the_real_listings_each_profile_rejects_the_other_image(self):
        import poc_audit
        ok, _ = poc_audit.audit_dir(os.path.join(PLAY_OUT, "audit"), "play")
        self.assertEqual(ok, [])
        cross1, _ = poc_audit.audit_dir(os.path.join(STREAM_OUT, "audit"), "play")
        self.assertTrue(any("forbidden object linked: gbp_vidxdump.o" in f for f in cross1), cross1[:5])
        self.assertTrue(any("main.o references gbp_vidxdump_stream" in f for f in cross1), cross1[:5])
        self.assertGreater(len(cross1), 20)
        cross2, _ = poc_audit.audit_dir(os.path.join(PLAY_OUT, "audit"), "stream")
        self.assertTrue(any("expected object missing: gbp_vidxdump.o" in f for f in cross2), cross2[:5])
        self.assertTrue(any("gbp_vwitness_gate_streak call sites {}" in f for f in cross2), cross2[:5])
        self.assertGreater(len(cross2), 20)


class ThePlumbing(unittest.TestCase):
    def test_the_top_level_makefile(self):
        m = read(TOP_MAKEFILE)
        # Issue #59 appended gbp-audio-window-probe; play-0001's own place in the list is what is pinned
        self.assertIsNotNone(re.search(r"^POCS\s*:=.* gbp-video-stream-probe gbp-play-session\b", m, re.M))
        for tok in ("PLAY_OUT := build/poc/gbp-play-session", "$(eval $(call POC_AUDIT_RULE,$(PLAY_OUT),play))",
                    "$(eval $(call ISR_COMPARE_TARGET,play-audit,$(PLAY_OUT)))",
                    "$(eval $(call ISR_RULE,$(PLAY_OUT),ext,hsp_backend_oneshot_isr_ext,hsp_backend_irq))",
                    "$(eval $(call ISR_RULE,$(PLAY_OUT),base,hsp_backend_oneshot_isr,hsp_backend_irq))",
                    "play-dolphin:", "--expect 'OPENGBP-PLAY SELFTEST ok=1'", "--expect 'OPENGBP-PLAY INPUTSELFTEST ok=1'",
                    "--expect 'OPENGBP-PLAY ENVMEM .*arena1_free=[1-9][0-9]*'", "--expect 'storage_fault=-'",
                    "--expect 'OPENGBP-PLAY SESSION requested=0 samples=0 held=0 holds=0 released=0 hold_ms=250'",
                    "--expect 'OPENGBP-PLAY RESULT status=abort_inconsistent class=abort reason=inconsistent stop=failure teardown=stage_a service=0 deliveries=0 restore=1'",
                    "so the pump slot never runs; nothing\n# about the input path, the KEY record, the presentation of a real frame or\n# the session end is exercised here."):
            self.assertIn(tok, m, tok)
        self.assertIn("play-audit play-dolphin", m[m.index(".PHONY:"):m.index(".PHONY:") + 400])

    def test_the_swiss_slot_is_13(self):
        rows = [l.split("\t") for l in read(LAYOUT).splitlines() if l and not l.startswith("#")]
        play = [r for r in rows if r[2] == "gbp-play-session"]
        # Issue #44 (2026-09-22) added the frozen_sha256 column: 13-play is staged on the Operator's card and its
        # bytes are pinned there, so the staging tool refuses to overwrite them
        self.assertEqual(play, [["13", "play", "gbp-play-session", "gbp-play-session.dol", "gbp-play-session", "build",
                                 "1", "d0ee3c29d04254d1b86d4f006291008876b5e886e07280d0421b7c1161c499de"]])
        # Hardware Issue #61 (2026-09-22) added 14-audio beside it; nothing was renumbered,
        # which is the property this line exists for.
        # 2026-09-23: 15-drain and 16-aout were added the same way (§V19.12, §V21.4), and
        # 17-live after them (§V22.11).
        self.assertEqual([r[0] for r in rows if r[0] < "80"], ["%02d" % i for i in range(1, 18)])

    def test_the_gecko_protocol_and_the_identity(self):
        p = read(PLAY_MAIN)
        self.assertIn('#define TEST_ID "GBP-PLAY-001"', p)
        self.assertIn('"OPENGBP-PLAY READY %s test=%s\\n"', p)
        self.assertIn('#define OPENGBP_APP_NAME "gbp-play-session"', p)


@unittest.skipUnless(os.path.isfile(os.path.join(PLAY_OUT, "build-info.txt")), "run `make build` first")
class TheBuiltImage(unittest.TestCase):
    def info(self):
        return dict(l.split("=", 1) for l in read(os.path.join(PLAY_OUT, "build-info.txt")).splitlines() if "=" in l)

    def test_build_info_and_the_dol_agree(self):
        info = self.info()
        self.assertEqual(info["app"], "gbp-play-session")
        self.assertEqual(info["build_id"], "play-0001")
        dol = os.path.join(PLAY_OUT, "gbp-play-session.dol")
        with open(dol, "rb") as f:
            blob = f.read()
        self.assertEqual(info["sha256_dol"], hashlib.sha256(blob).hexdigest())
        marker = ("OPENGBP-IDENT gbp-play-session play-0001 %s" % info["commit"]).encode("ascii")
        self.assertIn(marker, blob)
        self.assertEqual(blob.count(b"OPENGBP-IDENT "), 1)
        for lit in (b"OPENGBP-PLAY READY ", b"OPENGBP-PLAY SELFTEST ", b"OPENGBP-PLAY INPUTSELFTEST ", b"OPENGBP-PLAY ENVMEM ",
                    b"OPENGBP-PLAY COUNTERS ", b"OPENGBP-PLAY SESSION ", b"OPENGBP-PLAY RESULT ", b"GBP-PLAY-001"):
            self.assertIn(lit, blob, lit)
        for absent in (b"OGBPIDXCAP1", b"OGBPDISP", b"OGBPFULL1", b"OGBPVI1", b"WITQUAL", b"STREAMWIT "):
            self.assertNotIn(absent, blob, absent)
        self.assertEqual(len(blob) % 32, 0)


if __name__ == "__main__":
    unittest.main()
