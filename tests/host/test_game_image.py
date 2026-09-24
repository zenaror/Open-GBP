"""
tests/host/test_game_image.py — GitHub Issue #110: Phase 6's acceptance image on a real cartridge
(poc/gbp-audio-game, GBP-AUDIO-010, game-0001), pinned to live-0001, to §V25 and to the report its
frozen gates read.

WHAT CHANGED, SHOWN BY DIFFING (§V25.7 5, reading (r8)). live-0001 (poc/gbp-audio-live at feaf380,
RUN 38's image) is this image's base. Every line live-0001 has is here unchanged except its identity
(three lines) and a CLOSED list of lines the GAME blocks replace, each named below. Every added hunk
begins with a line marked GAME, or is an identity line. The functions no GAME block touches are
live-0001's character for character, and no function is added.

WHERE EACH CHANGE SITS. The press origin is set up in main before the service (GAME 1). The
hand-over writes sit in the presentation path, under the phase test, and nowhere else (GAME 2). The
frame store is walked in main after the session and before X (GAME 4).

THE LOG IS THE INTERFACE. The builder (tools/v25report.py, frozen with this image) is fed a log
rendered from THIS image's own format strings, and its report goes through the frozen gates
(tools/v25accept.py, 54383e6). Every new record fits the ringlog line at its worst.

THE AUDIT IS EXERCISED, NOT COUNTED: when the listings exist, `game` passes this image and fails
live-0001's.
"""
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(__file__))

import test_trace_image as tt  # noqa: E402  (the diff and format helpers, reused, not copied)
import v25accept  # noqa: E402
import v25report  # noqa: E402

GAME_MAIN = os.path.join(ROOT, "poc", "gbp-audio-game", "source", "main.c")
GAME_MAKEFILE = os.path.join(ROOT, "poc", "gbp-audio-game", "Makefile")
LIVE_MAIN = tt.LIVE_MAIN
LIVE_MAKEFILE = tt.LIVE_MAKEFILE
PROBE_C = os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.c")
GAME_OUT = os.path.join(ROOT, "build", "poc", "gbp-audio-game")
LIVE_OUT = tt.LIVE_OUT
TB = 40500000

IDENTITY = {
    '#define OPENGBP_APP_NAME "gbp-audio-live"': '#define OPENGBP_APP_NAME "gbp-audio-game"',
    '#define TEST_ID "GBP-AUDIO-007"': '#define TEST_ID "GBP-AUDIO-010"',
    '    printf("\\n  Open-GBP " TEST_ID "  PHASE 6\'s ACCEPTANCE IMAGE (HARDWARE_TESTS V22; NOT PHYSICALLY VALIDATED)\\n");':
        '    printf("\\n  Open-GBP " TEST_ID "  PHASE 6\'s ACCEPTANCE ON A REAL CARTRIDGE (HARDWARE_TESTS V25; NOT PHYSICALLY VALIDATED)\\n");',
}
# the ONLY other lines of live-0001 this image replaces, each inside a GAME block
REPLACED = {
    # GAME 3: the prompt, the press, and the console before the press stood on the tone
    '        printf("  >>> PRESS A ONCE NOW, and nothing else (within 30 s) <<<                         ");',
    '    if (!live_drawn_press && live.phase == GBP_ALIVE_CONTROL) {',
    '        printf("  A RECEIVED. DO NOT PRESS ANYTHING MORE. The tone plays for about 65 s.          ");',
    '        printf("  The report appears when it ends.                                                ");',
    '    printf("  Cartridge: agb-sweep (sweep-0002). Link Port: nothing. BBA: absent.\\n");',
    '    printf("  WAIT for the prompt below (about 5 s). Then press A ONCE and nothing else.\\n");',
    '    printf("  If no tone is found within 10 s the run ends: power-cycle and retry.\\n");',
    '    printf("  A second A press is NOT the fix -- it selects another tone. X does nothing until the end.\\n");',
    # GAME 4: `clipped` joins LIVEC
    '                            "handed=%lu starved=%lu log_overflow=%lu",',
    '                       (unsigned long)ap.log_overflow);',
    # GAME 5: no control line; the verdicts' tool; AUDIO is played here
    '    printf("  CONTROL %s%s: %lu periods, %lu..%lu\\n", live.control_ok ? "passed" : "DID NOT PASS",',
    '           live.control_gave_up ? " (gave up: power-cycle, retry)" : "", (unsigned long)live.control_periods,',
    '           (unsigned long)live.control_pmin, (unsigned long)live.control_pmax);',
    '    printf("  L2      %s: %lu chunks kept, %lu in the window (%lu silence). Verdicts: tools/v22accept.py.\\n",',
    '    printf("  SERVICE %s  deliveries=%lu  VIDEO %lu  AUDIO %lu (drained, NOT reproduced)  errors=%lu uncertain=%lu\\n",',
}
GAMED = ("submit_ready", "live_screen", "live_screen_report", "main")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class TheImageIsLive0001WithTheGameBlocks(unittest.TestCase):

    def test_live_0001_loses_only_its_identity_and_the_named_lines(self):
        removed = [l for r, _a, _j in tt.hunks(read(LIVE_MAIN), read(GAME_MAIN)) for l in r]
        self.assertEqual(sorted(removed), sorted(set(IDENTITY) | REPLACED))
        self.assertEqual(len(removed), len(set(removed)), "a named line was removed twice")

    def test_every_addition_is_the_header_an_identity_line_or_marked_GAME(self):
        for removed, added, j in tt.hunks(read(LIVE_MAIN), read(GAME_MAIN)):
            if removed and all(r in IDENTITY for r in removed):
                self.assertEqual(added, [IDENTITY[r] for r in removed], (removed, added))
            elif j <= 1 and not removed:
                self.assertTrue(all(l.startswith((" *", "/*")) for l in added), added[:3])
                self.assertIn("GBP-AUDIO-010, build game-0001", "\n".join(added[:3]))
            else:
                first = next(l for l in added if l.strip() not in ("", "{", "}"))
                self.assertIn("GAME", first, "a hunk at line %d is not marked GAME: %r" % (j + 1, first))

    def test_the_untouched_functions_are_live_0001s_character_for_character(self):
        live, game = tt.functions(read(LIVE_MAIN)), tt.functions(read(GAME_MAIN))
        self.assertGreaterEqual(len(live), 20, sorted(live))
        for name, text in live.items():
            if name not in GAMED:
                self.assertEqual(game.get(name), text, name)
        self.assertEqual(set(game), set(live), "no function added or removed")

    def test_the_sources_and_the_makefile_are_live_0001s_but_for_the_identity(self):
        self.assertEqual(tt.srcs(GAME_MAKEFILE), tt.srcs(LIVE_MAKEFILE))
        mk = read(GAME_MAKEFILE)
        self.assertRegex(mk, r"(?m)^APP_NAME\s*:=\s*gbp-audio-game$")
        self.assertRegex(mk, r"(?m)^BUILD_ID\s*:=\s*game-0001$")
        for r, _a, _j in tt.hunks(read(LIVE_MAKEFILE), mk):
            for l in r:
                self.assertTrue(l.startswith(("# Open-GBP GBP-AUDIO-007", "#     make -C", "# Outputs go to",
                                              "APP_NAME", "BUILD_ID")), l)

    def test_nothing_of_section_23_or_24_is_linked_or_named(self):
        m = read(GAME_MAIN)
        for tok in ("gbp_atrace", "gbp_asplit", "step_pushes", "video_tap"):
            self.assertNotIn(tok, re.sub(r"/\*.*?\*/", "", m, flags=re.S), tok)
        self.assertNotIn("gbp_atrace.c", tt.srcs(GAME_MAKEFILE))
        self.assertNotIn("gbp_asplit.c", tt.srcs(GAME_MAKEFILE))


class WhereEachChangeSits(unittest.TestCase):

    def test_GAME_1_the_press_origin_is_set_in_main_before_the_service(self):
        m = read(GAME_MAIN)
        self.assertRegex(m, r"(?m)^#define GAME_ORIGIN_DELAY_MS 1000u$")
        main = tt.functions(m)["main"]
        init = main.index("gbp_alive_init(&live, tb_hz);\n    /* GAME 1")
        call = main.index("gbp_alive_use_press_origin(&live, GAME_ORIGIN_DELAY_MS);")
        self.assertLess(init, call)
        self.assertLess(call, main.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);"))
        self.assertEqual(m.count("gbp_alive_use_press_origin("), 1)

    def test_GAME_2_the_hand_over_is_in_the_presentation_path_under_the_phase_test(self):
        m = read(GAME_MAIN)
        sub = tt.functions(m)["submit_ready"]
        block = ("    if (live.phase == GBP_ALIVE_DELAY || live.phase == GBP_ALIVE_WINDOW) {\n"
                 "        VIDEO_SetNextFramebuffer(xfb_stream_buf[xfb]);\n"
                 "        VIDEO_Flush();                    /* register write only; NEVER VIDEO_WaitVSync here */\n"
                 "    }\n")
        self.assertIn(block, sub)
        self.assertLess(sub.index("GX_CopyDisp(xfb_stream_buf[xfb], GX_TRUE);"), sub.index(block))
        self.assertLess(sub.index(block), sub.index("gbp_vpresent_xfb_handed(&present, xfb);"))
        self.assertEqual(m.count("VIDEO_SetNextFramebuffer(xfb_stream_buf"), 1)
        self.assertNotIn("VIDEO_WaitVSync", re.sub(r"/\*.*?\*/", "", sub, flags=re.S))   # the comment names it

    def test_GAME_4_the_frame_store_is_walked_after_the_session_and_before_X(self):
        main = tt.functions(read(GAME_MAIN))["main"]
        walk = main.index("\"LIVEVINC ai=")
        self.assertLess(main.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);"), walk)
        self.assertLess(walk, main.index("PAD_ButtonsDown(0) & PAD_BUTTON_X"))
        self.assertIn("if (fr->completeness == GBP_VSTATE_FRAME_COMPLETE_40) continue;", main)
        self.assertIn("if (!ai_started || fr->t_last_block < t_ai_start) {", main)
        self.assertIn("} else if (fr->t_last_block > t_ai_stop) {", main)

    def test_the_press_line_is_drawn_at_the_delay_before_the_window(self):
        scr = tt.functions(read(GAME_MAIN))["live_screen"]
        self.assertIn("live.phase == GBP_ALIVE_DELAY", scr)
        self.assertNotIn("GBP_ALIVE_WINDOW", scr)       # never a print inside C's window
        self.assertIn("Do NOT hold Z", scr)


class NoRecordCanBeTruncated(unittest.TestCase):

    def test_every_live_record_fits_the_ringlog_line_at_its_worst(self):
        m = read(GAME_MAIN)
        tags = sorted(set(re.findall(r'"(LIVE[A-Z0-9]*) ', m)))
        self.assertTrue({"LIVEGAME", "LIVECAL", "LIVEVINC", "LIVEVSEC", "LIVEC"} <= set(tags), tags)
        per_line = ",".join(["4294967295"] * 16)
        for tag in tags:
            fmts = tt.c_formats(m, tag)
            self.assertTrue(fmts, tag)
            for fmt in fmts:
                strings = {"LIVESEC": [per_line], "LIVEFILL": [per_line], "LIVEVSEC": [per_line],
                           "LIVEL2SAVE": ["x" * 159], "LIVE": ["calibrate"]}.get(tag, [])
                line = tt.worst_case(fmt.replace("%llu", "%llu"), strings)
                self.assertLessEqual(len(line), tt.RINGLOG_CONTENT_MAX, "%s renders %d characters" % (tag, len(line)))


# ---- the image's own formats, rendered, through the builder and the frozen gates ------------------

HEX = ("%llx", "%08lx", "%x")


def render_kv(fmt, values):
    """Each key=%spec of the image's own format filled from `values` by KEY, hex where the spec is."""
    def sub(mo):
        key, spec = mo.group(1), mo.group(2)
        v = values[key]
        return "%s=%s" % (key, ("%x" % v) if spec in HEX else v)
    return re.sub(r"(\w+)=(%(?:08lx|llu|llx|lu|x|u|d|s))", sub, fmt)


def fmt_of(src, tag):
    fmts = tt.c_formats(src, tag)
    assert len(fmts) == 1, (tag, fmts)
    return fmts[0]


def log(**over):
    m = read(GAME_MAIN)
    ai0, t_origin = 5 * 10 ** 9, 5 * 10 ** 9 - 20250000
    v = {
        "IDENT": dict(test="GBP-AUDIO-010", app="gbp-audio-game", build="game-0001", commit="abcdef0", libogc="x"),
        "LIVEGAME": dict(delay_ms=1000),
        "LIVE": dict(phase="done", control_ok=0, gave_up=0, early=0, windows=0, press_before_prompt=0,
                     presses_a=7, presses_other=212, presses_after=1),
        "LIVET": dict(tb_hz=TB, t0=10 ** 8, t_accept=10 ** 8 + 5 * TB, t_press=t_origin - TB, t_origin=t_origin,
                      t_end=t_origin + 64 * TB),
        "LIVET2": dict(t_ai_start=ai0, t_ai_stop=ai0 + 2567047476, t_last_block=t_origin + 64 * TB - 100,
                       gap_max=20000, gap_at=ai0 + 77),
        "LIVEL": dict(periods=3000, pmin=2, pmax=900, off=2999, edges=3001, samples=261600),
        "LIVEC": dict(overflow=0, lost=0, underruns=0, silences=0, dup=1500, drop=0, produced=2035, handed=2032,
                      starved=100, log_overflow=0, clipped=0),
        "LIVEM": dict(callbacks=2031, t_first=ai0 + 1264500, t_last=ai0 + 2031 * 1264500, frames_per_callback=1000),
        "LIVECAL": dict(rest_sum=4096 * 16384 + 3, rest_n=4096, pmin=16382, pmax=16386),
        "LIVEVINC": dict(ai=1, before=13, inside=12, after=0, stored=25, framecap=25, store_full=0, secs=64,
                         sec_overflow=0),
    }
    framecap = over.pop("framecap", None)
    for k, val in over.items():
        tag, _, key = k.partition("__")
        v[tag][key] = val
    secs = [4096 - 8] * 64
    vsec = [0] * 64
    for i in range(v["LIVEVINC"]["inside"]):
        vsec[(i * 5) % 64] += 1
    lines = []

    def emit(line):
        lines.append("%06d %s" % (len(lines), line))

    emit(render_kv("IDENT test=%s app=%s build=%s commit=%s libogc=%s", v["IDENT"]))
    if v["LIVEGAME"].get("delay_ms") is not None:
        emit(render_kv(fmt_of(m, "LIVEGAME"), v["LIVEGAME"]))
    emit("FRAMECAP frames=4254 complete=4229 incomplete=%d resync=26 anomaly_frame=2 anomaly_region=25 counted=4200 "
         "blocks=170159 pre_boundary=62 store_full=0" % (v["LIVEVINC"]["framecap"] if framecap is None else framecap))
    for tag in ("LIVE", "LIVET", "LIVET2"):
        emit(render_kv(fmt_of(m, tag), v[tag]))
    for k in range(0, 64, 16):
        emit(render_kv(fmt_of(m, "LIVESEC"), {"from": k, "counts": ",".join(map(str, secs[k:k + 16]))}))
    for k in range(0, 64, 16):
        emit(render_kv(fmt_of(m, "LIVEFILL"), {"from": k, "fill": ",".join(["2000"] * 16)}))
    for tag in ("LIVEL", "LIVEC", "LIVEM", "LIVECAL", "LIVEVINC"):
        emit(render_kv(fmt_of(m, tag), v[tag]))
    for k in range(0, v["LIVEVINC"]["secs"], 16):
        emit(render_kv(fmt_of(m, "LIVEVSEC"), {"from": k, "counts": ",".join(map(str, vsec[k:k + 16]))}))
    emit("LIVEL2SAVE open=0 write=0 close=0 bytes=83724 status=saved")
    return "\n".join(lines) + "\n"


class TheBuilderReadsTheImagesOwnFormats(unittest.TestCase):

    def test_the_report_is_what_the_log_says(self):
        r = v25report.build(log())
        self.assertEqual((r["test_id"], r["build_id"], r["window_opened"], r["phase_reached"]),
                         ("GBP-AUDIO-010", "game-0001", True, "done"))
        self.assertEqual((r["window"]["ticks"], len(r["window"]["coverage"]), r["window"]["not_drained"]),
                         (64 * TB, 64, 8 * 64))
        self.assertEqual((r["clipped"], r["calibration"]["pmin"], r["calibration"]["pmax"]), (0, 16382, 16386))
        vid = r["video"]
        self.assertEqual((vid["before"], vid["inside"], vid["after"], vid["stored"], vid["framecap_incomplete"]),
                         (13, 12, 0, 25, 25))
        self.assertEqual((len(vid["per_second"]), sum(vid["per_second"])), (64, 12))
        self.assertEqual(vid["t_ai_stop"] - vid["t_ai_start"], 2567047476)
        self.assertEqual(r["l2_sidecar"], "present")

    def test_through_the_frozen_gates(self):
        decl = {"a_stability": "PASS", "defects": {k: "no" for k in v25accept.DEFECTS}, "a_words": "",
                "a_fidelity": "abafado", "picture": "normal", "picture_words": "", "controls": "responded",
                "controls_words": ""}
        rep = v25report.build(log())
        rep["l2_sidecar"] = "absent: not supplied in this test"
        e = v25accept.evaluate(rep, None, decl)
        self.assertEqual((e["R"]["reading"], e["R"]["blocks_lost_per_s"]), ("AS EXPECTED", 8.0))
        self.assertEqual(e["C"]["verdict"], "PASS")
        self.assertEqual(e["V"]["video"]["verdict"], "HOLDS")
        self.assertEqual(e["V"]["verdict"], "PASS")
        self.assertEqual(e["A"]["verdict"], "PASS")
        self.assertEqual(e["L2"]["verdict"], "INCONCLUSIVE")          # absent here, so the phase stays open
        self.assertEqual(e["phase6"]["verdict"], "STAYS OPEN")
        self.assertEqual(e["M"]["callbacks"], 2031)

    def test_a_window_that_never_opened(self):
        r = v25report.build(log(LIVE__phase="prompt", LIVET__t_origin=0, LIVET__t_end=0, LIVET2__t_ai_start=0,
                                LIVET2__t_ai_stop=0, LIVEVINC__ai=0, LIVEVINC__before=25, LIVEVINC__inside=0,
                                LIVEVINC__secs=0))
        self.assertFalse(r["window_opened"])
        self.assertEqual(r["window"]["coverage"], [])
        e = v25accept.evaluate(r, None, None)
        self.assertEqual([e[q]["verdict"] for q in ("L2", "C", "A", "V")], ["INCONCLUSIVE"] * 4)

    def test_it_refuses_what_is_not_this_image_or_does_not_reconcile(self):
        with self.assertRaises(ValueError):
            v25report.build(log(LIVEGAME__delay_ms=None))
        with self.assertRaises(ValueError):
            v25report.build(log(framecap=26))
        with self.assertRaises(ValueError):
            v25report.build(log(LIVEVINC__secs=63))

    def test_the_probe_still_writes_the_FRAMECAP_the_builder_cross_checks(self):
        self.assertIn('"FRAMECAP frames=%lu complete=%lu incomplete=%lu ', read(PROBE_C))


class TheAuditIsExercised(unittest.TestCase):

    def _findings(self, out_dir, profile):
        import poc_audit
        if not os.path.exists(os.path.join(out_dir, "audit", "elf.nm.txt")):
            self.skipTest("%s is not built in this checkout" % out_dir)
        return poc_audit.audit_dir(os.path.join(out_dir, "audit"), profile)[0]

    def test_game_passes_the_game_image(self):
        self.assertEqual(self._findings(GAME_OUT, "game"), [])

    def test_game_fails_live_0001(self):
        f = self._findings(LIVE_OUT, "game")
        self.assertTrue(any("gbp_alive_use_press_origin" in x for x in f), f)
        self.assertTrue(any("VIDEO_SetNextFramebuffer call sites" in x for x in f), f)

    def test_live_also_passes_the_game_image_because_every_change_is_additive(self):
        self.assertEqual(self._findings(GAME_OUT, "live"), [])

    def test_the_profile_is_derived_from_live(self):
        import poc_audit
        live, game = poc_audit.PROFILES["live"], poc_audit.PROFILES["game"]
        self.assertEqual(set(game["elf_required"]) - set(live["elf_required"]), {"gbp_alive_use_press_origin"})
        self.assertEqual(set(game["main_must_call"]) - set(live["main_must_call"]), {"gbp_alive_use_press_origin"})
        self.assertEqual(game["symbol_callers"]["VIDEO_SetNextFramebuffer"], {"main": 2, "submit_ready": 1})
        self.assertEqual(game["required_objects"], live["required_objects"])


if __name__ == "__main__":
    unittest.main()
