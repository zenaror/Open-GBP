"""tests/host/test_sync_image.py -- GitHub Issue #117: sync-0001 (GBP-AUDIO-012), the latency round's image
(HARDWARE_TESTS §V27), pinned to its base and to what §V27 requires of it.

  * THE BASE. poc/gbp-audio-sync/source/main.c is game-0002's main.c with named changes: the L2 keep gone, the
    session machine and the raw window added, the transition executor and the C-stick, the records, and NOTHING
    on the screen or the live channel derived from the arm, the target, the fill, the corrections or the answers.
  * THE RECORDS. Every SYNC* format string the image hands the ringlog stays within its 248 characters with every
    conversion at its type's widest value (found the first time: SYNCCFG was 257 with its real values, SYNCC 223
    of names alone, SYNCAWR 270 at the maxima; each is now split), and every tag the builder reads is printed.
  * THE AUDIT. Profile `sync` reports no finding, and the two one-shot handlers are byte-identical to GBP-VIDEO-001's,
    when the image is built in this checkout (otherwise skipped, and the skip is the ledger's).
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import poc_audit  # noqa: E402
import skip_ledger  # noqa: E402

MAIN = os.path.join(ROOT, "poc", "gbp-audio-sync", "source", "main.c")
BASE_MAIN = os.path.join(ROOT, "poc", "gbp-audio-game2", "source", "main.c")
MAKEFILE = os.path.join(ROOT, "poc", "gbp-audio-sync", "Makefile")
OUT = os.path.join(ROOT, "build", "poc", "gbp-audio-sync")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def code(src):
    """The C without its comments (a header comment may name what the code must not)."""
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", src, flags=re.S))


def functions(src):
    """name -> body text of every top-level `static ... name(...) {...}` and `int main(...)` in a C file: a
    one-line signature at column 0, the brace on the next line, as the project writes them."""
    out = {}
    for m in re.finditer(r"^(?:static\s+)?(?:const\s+)?(?:inline\s+)?[A-Za-z_][\w \t\*]*?\b(\w+)\s*\([^\n;{]*\)\s*\n\{",
                         src, re.M):
        name = m.group(1)
        i = m.end()
        depth = 1
        while depth and i < len(src):
            c = src[i]
            depth += (c == "{") - (c == "}")
            i += 1
        out[name] = src[m.start():i]
    return out


class TheBase(unittest.TestCase):
    # the transition executor lives in src/audio/gbp_atrans (tested against the real chain), not here
    ADDED = {"cs_read", "cs_edge", "sync_line_admit", "sync_trans_done", "sync_apply_plan", "sync_dwell_done", "sync_control",
             "sync_progress_text", "sync_progress_kv", "awr_sink", "sync_save_awr"}
    # submit_ready: the VI hand-over runs to the session's end (review before the commit: it stopped at 64 s)
    CHANGED = {"live_tap", "live_screen", "live_step", "live_screen_report", "submit_ready", "main"}

    def test_identity(self):
        src, mk = read(MAIN), read(MAKEFILE)
        self.assertIn('#define TEST_ID "GBP-AUDIO-012"', src)
        self.assertIn('#define OPENGBP_APP_NAME "gbp-audio-sync"', src)
        self.assertIn("APP_NAME   := gbp-audio-sync", mk)
        self.assertIn("BUILD_ID   := sync-0001", mk)
        self.assertTrue(re.search(r"^SRCS := .* gbp_aplay\.c gbp_async\.c gbp_atrans\.c gbp_awr\.c .*$", mk, re.M))
        self.assertIn("# Open-GBP GBP-AUDIO-012 — the latency round, sync-0001 (GitHub Issue #117, HARDWARE_TESTS §V27)", mk)
        self.assertNotIn("game-0002 (GitHub Issue #113", mk)
        self.assertIn("THE AUDIT PROFILE IS `sync`", mk)

    def test_every_function_of_game_0002_is_kept_or_named_as_changed(self):
        base, now = functions(read(BASE_MAIN)), functions(read(MAIN))
        self.assertEqual(len(base), 20)                              # the extractor sees game-0002 whole
        for name, body in base.items():
            if name in self.CHANGED:
                self.assertNotEqual(now.get(name), body, name)
            else:
                self.assertEqual(now.get(name), body, "%s differs from game-0002 and is not named as changed" % name)
        self.assertEqual(set(now) - set(base), self.ADDED)

    def test_no_L2_anywhere(self):
        src = code(read(MAIN))
        for tok in ("gbp_aplay_arm_l2", "gbp_aplay_sidecar", "LIVE_L2_FROM_S", "ap_keep", "l2_side", "LIVEL2",
                    "l2_armed", "-l2.bin"):
            self.assertNotIn(tok, src, tok)
        self.assertIn("gbp_aplay_init(&ap, ap_pool, ap_silence, NULL, NULL);", src)
        self.assertIn('l2=never', src)

    def test_the_session_and_the_raw_window_are_wired(self):
        src = read(MAIN)
        for tok in ("gbp_async_init(&sync, NULL);", "gbp_async_start(&sync, live.t_origin, sync_seed);",
                    "sync_seed = (uint32_t)live.t_press;", "gbp_async_block(&sync, t_done, fill_before);",
                    "gbp_async_second_counters(&sync, now, ap.underruns, adec.overflow);",
                    "gbp_async_tick(&sync, now)", "gbp_awr_arm(&awr, live.t_origin)",
                    "gbp_awr_block(&awr, bytes, len, t_done, live_taps)", "gbp_awr_note_cost(&awr,",
                    "gbp_awr_finish(&awr);", "#define SYNC_AWR_BLOCKS 640u",
                    "static uint8_t awr_store[SYNC_AWR_BLOCKS * GBP_AWR_BLOCK_SIZE] ATTRIBUTE_ALIGN(32);",
                    "adec.count >= ap.target && gbp_aplay_ready(&ap) >= 2u",
                    "#include \"gbp_atrans.h\"",
                    "if (sync_started && gbp_async_finished(&sync)) live_end = 1;",
                    "#define PLAY_SAFETY_SECONDS      785u", "#define PLAY_FRAME_RECORDS       47104u",
                    "#define KEYLOG_TAIL_RESERVE 1280u", "#define SYNC_PROMPT_BOUND_S 45u",
                    "if (sync_dwell_done(now)) sync_apply_plan(now);",
                    "gbp_atrans_begin(&trans, &ap, &adec, now, pl->mech, pl->mute_chunks, pl->pause_chunks, pl->discard, pl->to);",
                    "if (trans.active) { if (gbp_atrans_step(&trans, &ap, &adec, now, &b)) sync_trans_done(); }",
                    "r = trans.active ? 0 : gbp_async_tick(&sync, now);",
                    "if (sync_started && (!sync.finished || sync.p3_depth_pending)) {",
                    "if (sync.p3_depth_pending) { (void)sync_dwell_done(sync_last_now); sync_p3_drained++; }",
                    "sync_tx[trans_sw].done = 3u; sync_tx[trans_sw].mech = pl->mech;",
                    "dwell_starved0 = ap.ring_gated;", "x->starved = ap.ring_gated - dwell_starved0;",
                    "ap.ring_gated - dwell_starved0);",
                    "busy = trans.active && ((sync.phase <= GBP_ASYNC_P1 && d == CS_DOWN) ||",
                    "if (cut >= 0 && cut < (int32_t)GBP_ASYNC_SWITCH_CAP) sync_tx[cut].done = 2u;",
                    "trans_sw = (pl->kind == GBP_ASYNC_KIND_REAL || pl->kind == GBP_ASYNC_KIND_NULL) ? (int32_t)sync.switches - 1 : -1;",
"gbp_atrans_init(&trans);",
                    "static struct gbp_atrans trans;", "(unsigned long)trans.faults,", "(unsigned long)ap.dropped_front);",
                    "const uint64_t t_end = sync.p3_dwell_cut ? sync.ph[GBP_ASYNC_P3].t_end : sync.t_dwell_end;",
                    "if (k0 < s_set) k0 = s_set;",
                    "if (sync.phase != phase0 || (sync.phase <= GBP_ASYNC_P3 && sync.ph[sync.phase].ended != ended0)) sync_z_skips++;",
                    "if (sync_p2_lines < 200u && sync_line_admit()) {", "if (sync_cs_events <= 400u && sync_line_admit())",
                    "gbp_input_keylog_admit((uint32_t)keylog_rl->count, (uint32_t)keylog_rl->capacity, KEYLOG_TAIL_RESERVE))\n"
                    "        return 1;\n    sync_lines_lost++;"):
            self.assertIn(tok, src, tok)
        fs = functions(src)
        # the review's two blockers, pinned: the seeded initial level reaches the chain at the origin ...
        self.assertRegex(fs["live_tap"], r"gbp_async_start\(&sync, live\.t_origin, sync_seed\);\s*(?:/\*(?:[^*]|\*(?!/))*\*/\s*)?"
                                         r"gbp_aplay_set_target\(&ap, sync\.target\);")
        # ... and the VI hand-over runs on to the session's end, as the audio path does
        self.assertIn("    if (live.phase == GBP_ALIVE_DELAY || live.phase == GBP_ALIVE_WINDOW ||\n"
                      "        (sync_started && !sync.finished && live.phase == GBP_ALIVE_DONE)) {\n"
                      "        VIDEO_SetNextFramebuffer(xfb_stream_buf[xfb]);", fs["submit_ready"])
        self.assertEqual(src.count("VIDEO_SetNextFramebuffer(xfb_stream_buf"), 1)
        # the prompt's bound ends the run as prompt_expired, before the safety wall; the wall covers a press in time
        self.assertIn("now >= live.t_accept + (uint64_t)live.tb_hz * SYNC_PROMPT_BOUND_S", fs["live_step"])
        self.assertIn('sync_prompt_expired ? "prompt_expired" : "no_origin"', src)
        self.assertLessEqual(11 + 500 + 45 * 100 + 1000 + 720 * 1000, 785 * 1000)   # 0.11 + 5 + 45 + 1 + 720 s < 785 s, in ms
        self.assertGreaterEqual(47104, 785 * 60)
        # the expected block count over the window `got` spans, in ticks
        self.assertIn("(uint32_t)(((now - dwell_t0) * (uint64_t)GBP_ASYNC_RATE) / (uint64_t)live.tb_hz)", fs["sync_dwell_done"])
        # gbp_alive's own window end no longer ends the session once the origin came
        self.assertNotIn("if (gbp_alive_finished(&live)) live_end = 1;", src)
        self.assertIn("else if (!sync_started && gbp_alive_finished(&live)) live_end = 1;", src)

    def test_the_C_stick_mapping(self):
        f = functions(read(MAIN))["sync_control"]
        self.assertIn("if (d == CS_DOWN) acted = gbp_async_switch(&sync, now);", f)
        self.assertIn("else if (d == CS_LEFT) acted = gbp_async_answer(&sync, now, GBP_ASYNC_LESS);", f)
        self.assertIn("else if (d == CS_RIGHT) acted = gbp_async_answer(&sync, now, GBP_ASYNC_MORE);", f)
        self.assertIn("else acted = gbp_async_answer(&sync, now, GBP_ASYNC_SAME);", f)
        self.assertIn("if (d == CS_LEFT) acted = gbp_async_step(&sync, now, GBP_ASYNC_LEFT);", f)
        self.assertIn("else if (d == CS_UP) acted = gbp_async_confirm(&sync, now);", f)
        src = read(MAIN)
        self.assertIn("#define CS_THRESHOLD GBP_INPUT_POLICY_STICK_THRESHOLD", src)
        self.assertIn("#define CS_DEAD_MS   250u", src)
        self.assertIn("gbp_async_skip(&sync, now);", functions(src)["live_step"])   # Z = the next phase


class TheBlinding(unittest.TestCase):
    """§V27.9 O6 widened and §V27.10: nothing on the screen or the live channel is derived from the arm, the
    target, the fill, the corrections or the answers."""
    LEAKS = (r"ap\.target", r"sync\.target", r"sync\.level", r"sync\.initial", r"adec\.count", r"sec_fill",
             r"fill_mean", r"ap\.dup", r"ap\.drop", r"ap\.underruns", r"adec\.overflow", r"mute_handed", r"discarded",
             r"\.answer\b", r"sync\.sw\[", r"schedule", r"sync\.seed", r"p2_start", r"p2_dir", r"settings\[",
             r"depths\[", r"sec_target", r"sec_mute", r"trans\.", r"->to\b", r"->from\b")

    def printed_and_gecko(self):
        src = read(MAIN)
        fs = functions(src)
        # every printf/snprintf(line...)/gecko_puts site outside the SD-only ringlog_printf calls
        sites = []
        for name, body in fs.items():
            for m in re.finditer(r"(?:(?<![\w])printf|snprintf\(line, sizeof line,|gecko_puts)\s*\((.*?)\);", body, re.S):
                sites.append((name, m.group(0)))
        return sites

    def test_no_screen_or_gecko_site_carries_a_leak(self):
        for name, site in self.printed_and_gecko():
            for leak in self.LEAKS:
                self.assertIsNone(re.search(leak, site), "%s: a %r on the screen or the live channel" % (name, leak))

    def test_the_progress_texts_are_counts_only(self):
        fs = functions(read(MAIN))
        for name in ("sync_progress_text", "sync_progress_kv"):
            for leak in self.LEAKS:
                self.assertIsNone(re.search(leak, fs[name]), (name, leak))
            self.assertIn("sync.switches", fs[name])
            self.assertIn("awr.blocks_stored", fs[name])

    def test_the_run_prints_nothing_during_the_session(self):
        """live_step and the tap print nothing: the picture is on the VI and every print costs blocks."""
        fs = functions(read(MAIN))
        for name in ("live_step", "live_tap", "sync_control", "sync_apply_plan", "sync_dwell_done", "sync_trans_done",
                     "cs_edge"):
            self.assertNotIn("printf(", fs[name].replace("ringlog_printf(", ""), name)
            self.assertNotIn("gecko_puts(", fs[name], name)
        # the two prompt lines are drawn before the session, as game-0002's were
        self.assertEqual(fs["live_screen"].count("printf("), 6)

    def test_the_SD_records_carry_what_the_builder_reads(self):
        src = read(MAIN)
        for tag in ("SYNCCFG deep=", "SYNCCFG2 p3_min=", "SYNCCFG3 p3_confirm_s=%lu prompt_bound_s=%u",
                    "SYNCTX seq=%lu done=%u mech=%s mute=%lu rot=%lu res=%ld late=%u unmasked=%u topped=%lu",
                    "SYNCTXA begun=%lu completed=%lu faults=%lu rotate=%lu lates=%lu unmasked=%lu res=%ld..%ld",
                    "SYNCSEED seed=%08lx initial=%s", "SYNCSCHED n=%lu kinds=%s",
                    "SYNCP2CFG starts=%s dirs=%s",
                    "SYNCSW seq=%lu kind=%s from=%lu to=%lu t=%llx discard=%lu pause=%lu", "SYNCANS seq=%lu answer=%s t=%llx",
                    "SYNCP2 seq=%lu kind=%s from=%lu to=%lu t=%llx", "SYNCSET seq=%lu start=%lu dir=%c steps=%lu target=%lu t=%llx",
                    "SYNCDEPTH n=%lu kind=%s target=%lu fill16=%lu underruns=%lu overflow=%lu dup=%lu drop=%lu",
                    "SYNCPH phase=%lu t_start=%llx t_end=%llx ended=%s", '"SYNCSECC", "SYNCSECF", "SYNCSECT", "SYNCSECP", "SYNCSECM", "SYNCSECS",',
                    "SYNCC underruns=%lu overflow=%lu silences=%lu mute_handed=%lu", "SYNCC2 discarded=%lu starved_steps=%lu lost=%lu",
                    "SYNCP3 pending=%u drained=%lu refused_depth_done=%lu depths=%lu overflow=%lu",
                    "SYNCREF switch_unanswered=%lu switch_mute=%lu", "SYNCAWR blocks=%lu cap=%lu t_arm=%llx",
                    "SYNCAWRC copy_min=%lu copy_max=%lu copy_sum=%llu copy_n=%lu",
                    "SYNCEND reason=%s t=%llx secs=%lu phase=%u plans=%lu cs=%lu acted=%lu z=%lu cs_dead=%lu ",
                    "SYNCEND reason=%s t=%llx secs=0 phase=0 plans=0 cs=0 acted=0 z=0 cs_dead=%lu stop=%s",
                    "SYNCDEPTH2 n=%lu starved=%lu ready_in=%lu ready_out=%lu fill_in=%lu fill_out=%lu fill_n=%lu",
                    "SYNCAWRSAVE open=%d write=%d close=%d bytes=%lu status=%s",
                    "SYNCCS dir=%c phase=%u acted=%d busy=%d t=%llx",
                    "cs_busy=%lu preempts=%lu stop=%s", "handed=%lu ring_gated=%lu"):
            self.assertIn(tag, src, tag)


class TheRingLogWidths(unittest.TestCase):
    """Every SYNC* format string within the ringlog's 248 characters (LOG_LINE_LEN 256 - the 7-character sequence
    prefix - the terminator) with every conversion at its type's widest value. Read from main.c, not copied."""
    MAX = 256 - 7 - 1
    WIDTH = {"%lu": 10, "%u": 10, "%d": 11, "%ld": 11, "%llx": 16, "%llu": 20, "%08lx": 8, "%c": 1}
    # the %s conversions, by record, in order: the widest string each can carry (a record printed in two
    # forms, as SYNCEND is, may use fewer than declared)
    S = {"SYNCSEED": [7], "SYNCSCHED": [2 * 18 - 1], "SYNCP2CFG": [3 * 5 - 1, 3 * 2 - 1], "SYNCSW": [4],
         "SYNCANS": [4], "SYNCP2": [5], "SYNCDEPTH": [7], "SYNCPH": [8], "SYNCEND": [22, 22], "SYNCAWRSAVE": [159],
         "SYNCTX": [7]}
    # SYNCDEPTH's kind: STEP | BISECT | CONFIRM (7); SYNCTX's mech: ROTATE | HELD | UNMUTED (7); %ld: 11
    # SYNCEND's reason: the vstate stop names (widest witness_target_reached, 22), not_finished, prompt_expired

    def formats(self):
        src = read(MAIN)
        out = []
        for m in re.finditer(r'ringlog_printf\((?:&rl|keylog_rl),\s*((?:"(?:[^"\\]|\\.)*"\s*)+)', src):
            fmt = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))
            if fmt.startswith("SYNC"):
                out.append(fmt)
        return out

    def widest(self, fmt):
        tag = fmt.split(" ", 1)[0]
        convs = re.findall(r"%(?:08lx|llx|llu|lu|ld|u|d|c|s)", fmt)
        n = len(re.sub(r"%(?:08lx|llx|llu|lu|ld|u|d|c|s)", "", fmt))
        s_widths = list(self.S.get(tag, []))
        for c in convs:
            if c == "%s":
                self.assertTrue(s_widths, "%s: a %%s conversion with no declared width" % tag)
                n += s_widths.pop(0)
            else:
                n += self.WIDTH[c]
        return n

    def test_every_sync_format_string(self):
        fmts = self.formats()
        tags = set(f.split(" ", 1)[0] for f in fmts)
        for want in ("SYNCCFG", "SYNCCFG2", "SYNCCFG3", "SYNCTX", "SYNCTXA", "SYNCP3", "SYNCSEED", "SYNCSCHED", "SYNCP2CFG", "SYNCSW", "SYNCANS", "SYNCP2", "SYNCSET",
                     "SYNCDEPTH", "SYNCDEPTH2", "SYNCPH", "SYNCC", "SYNCC2", "SYNCREF", "SYNCAWR", "SYNCAWRC", "SYNCEND",
                     "SYNCAWRSAVE", "SYNCCS"):
            self.assertIn(want, tags)
        for fmt in fmts:
            self.assertLessEqual(self.widest(fmt), self.MAX, fmt[:40] + " -> %d" % self.widest(fmt))

    def test_the_per_second_series_lines(self):
        """`%s from=%lu %s=%s`: the tag (8), the offset, the widest name (`underruns`), 16 values of a uint32."""
        src = read(MAIN)
        self.assertIn('ringlog_printf(&rl, "%s from=%lu %s=%s", tags[f], (unsigned long)k2, names[f], sbuf);', src)
        self.assertIn("#define LIVE_SEC_PER_LINE 16u", src)
        self.assertIn("char sbuf[248];", src)
        self.assertIn("o < sizeof sbuf - 12u", src)
        line = 8 + len(" from=") + 10 + 1 + len("underruns") + 1 + 16 * 10 + 15
        self.assertLessEqual(line, self.MAX)

    def test_the_configuration_as_printed(self):
        """The first attempt printed one SYNCCFG of 257 characters with the real values: the record was cut."""
        cfg = ("SYNCCFG deep=2048 shallow=512 floor=384 mute=18 step_mute=4 p2_lo=384 p2_hi=3584 p2_step=128 p3_start=384 "
               "p3_step=32 p3_dwell_s=6 p3_bisect=2")
        cfg2 = ("SYNCCFG2 p3_min=128 cap_p1=300 cap_p2=240 cap_p3=180 cap_session=720 real=12 null=6 settling_s=2 "
                "awr_blocks=640 cfg_faults=0")
        self.assertLessEqual(len(cfg), self.MAX)
        self.assertLessEqual(len(cfg2), self.MAX)
        self.assertGreater(len(cfg) + 1 + len(cfg2) - len("SYNCCFG2 "), self.MAX)   # one line would not have fitted


class TheAudit(unittest.TestCase):
    def test_profile_sync_reports_no_finding(self):
        audit = os.path.join(OUT, "audit")
        if not os.path.isdir(audit) or not os.path.isfile(os.path.join(audit, "elf.nm.txt")):
            self.skipTest("%s is not built in this checkout" % "gbp-audio-sync")
        findings = poc_audit.audit_dir(audit, "sync")[0]
        self.assertEqual(findings, [])

    def test_the_handlers_match_GBP_VIDEO_001(self):
        for arm in ("ext", "base"):
            p = os.path.join(OUT, "isr-audit-%s.txt" % arm)
            if not os.path.isfile(p):
                self.skipTest("%s is not built in this checkout" % "gbp-audio-sync")
            ref = os.path.join(ROOT, "build", "poc", "gbp-video-capture-probe", "isr-audit-%s.txt" % arm)
            if not os.path.isfile(ref):
                self.skipTest("%s is not built in this checkout" % "gbp-video-capture-probe")
            self.assertEqual(read(p), read(ref), arm)

    def test_the_profile_names_what_changed(self):
        p = poc_audit.PROFILES["sync"]
        self.assertEqual(p["symbol_callers"]["gbp_aplay_arm_l2"], {})
        self.assertEqual(p["symbol_callers"]["gbp_aplay_sidecar"], {})
        self.assertNotIn("gbp_aplay_arm_l2", p["elf_required"])
        self.assertIn("gbp_aplay_arm_l2", p["elf_forbidden"])
        self.assertIn("gbp_async.o", p["required_objects"])
        self.assertIn("gbp_awr.o", p["required_objects"])
        self.assertEqual(p["symbol_callers"]["gbp_awr_block"], {"live_tap": 1})
        self.assertEqual(p["symbol_callers"]["sdlog_stream_write"], {"awr_sink": 1})


if __name__ == "__main__":
    unittest.main()
