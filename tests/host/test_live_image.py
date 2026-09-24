"""
tests/host/test_live_image.py — GitHub Issue #92: PHASE 6's ACCEPTANCE image
(poc/gbp-audio-live, GBP-AUDIO-007, live-0001), pinned to its base, to §V22 and to
the report the frozen gates read.

THE SUBTRACTION IS SHOWN BY DIFFING. RUN 37's image (drain-0001) is this image's base,
play-0001 is its base in turn: every function the chain did not need to touch is
diffed character for character and must be EQUAL, and every one it did touch differs
by lines NAMED here.

THE LOG IS THE INTERFACE. The image writes LIVE* records; tools/v22report.py turns them
into the report tools/v22accept.py (frozen before this image existed) decides on. So
the format strings are read out of the image's source, rendered at their worst case,
and fed back through the builder and the frozen gates here.

§V22's PROPERTIES THAT ARE PROPERTIES OF THE SOURCE are checked in the source: no SD
call before the session has ended (D2), X read only after it (§V22.9 A3), no print
inside C's window, and L read before any correction (§V22.8 (e)).

THE AUDIT IS EXERCISED, NOT COUNTED: when the listings exist, `live` passes this image
and fails play-0001's, and `play` fails this image.
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

LIVE_MAIN = os.path.join(ROOT, "poc", "gbp-audio-live", "source", "main.c")
LIVE_MAKEFILE = os.path.join(ROOT, "poc", "gbp-audio-live", "Makefile")
DRAIN_MAIN = os.path.join(ROOT, "poc", "gbp-audio-drain-probe", "source", "main.c")
DRAIN_MAKEFILE = os.path.join(ROOT, "poc", "gbp-audio-drain-probe", "Makefile")
PLAY_MAIN = os.path.join(ROOT, "poc", "gbp-play-session", "source", "main.c")
AUDIT = os.path.join(ROOT, "tools", "poc_audit.py")
LIVE_OUT = os.path.join(ROOT, "build", "poc", "gbp-audio-live")
PLAY_OUT = os.path.join(ROOT, "build", "poc", "gbp-play-session")
APLAY_C = os.path.join(ROOT, "src", "audio", "gbp_aplay.c")
ALIVE_H = os.path.join(ROOT, "src", "audio", "gbp_alive.h")
APLAY_H = os.path.join(ROOT, "src", "audio", "gbp_aplay.h")
RINGLOG_CONTENT_MAX = 256 - 7 - 1      # LOG_LINE_LEN, minus the "%06u " prefix and the NUL
TB = 40500000


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def function_text(src, name):
    m = re.search(r"^static (?:void|int) %s\([^;{]*\)\n\{" % re.escape(name), src, re.M)
    assert m, name
    j = src.index("\n}\n", m.start()) + 3
    return src[m.start():j]


def _diff(before, after, sign):
    import difflib
    return [l[1:] for l in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
            if l.startswith(sign) and not l.startswith(sign * 3)]


def srcs(makefile):
    return re.search(r"^SRCS := (.*)$", read(makefile), re.M).group(1).split()


def define(src, name):
    m = re.search(r"^#define\s+%s\s+(\S+)" % re.escape(name), src, re.M)
    assert m, name
    return int(m.group(1).rstrip("uUlL"), 0)


class TheSubtraction(unittest.TestCase):

    def test_the_untouched_functions_are_byte_identical_to_play_0001s(self):
        l, p = read(LIVE_MAIN), read(PLAY_MAIN)
        for name in ("input_step", "session_step", "offer_oldest_ready", "display_selftest", "video_setup",
                     "gx_setup", "on_draw_done", "selftest_submit_headless", "keylog_emit"):
            self.assertEqual(function_text(l, name), function_text(p, name), name)

    def test_pump_gained_exactly_the_live_slot_after_the_session_step(self):
        before, after = function_text(read(PLAY_MAIN), "pump"), function_text(read(LIVE_MAIN), "pump")
        self.assertEqual(_diff(before, after, "-"), [])
        self.assertEqual([x.strip() for x in _diff(before, after, "+")],
                         ["/* Issue #92: the chain's slot half -- the press record, the chain, the AI, the screen */",
                          "live_step();"])
        self.assertLess(after.index("session_step();"), after.index("live_step();"))

    def test_submit_ready_is_drain_0001s_but_for_its_comment(self):
        before, after = function_text(read(DRAIN_MAIN), "submit_ready"), function_text(read(LIVE_MAIN), "submit_ready")
        for x in _diff(before, after, "+") + _diff(before, after, "-"):
            self.assertTrue(x.strip().startswith(("/*", "*")), x)

    def test_the_sources_are_drain_0001s_with_the_chain_for_the_drain(self):
        self.assertEqual(set(srcs(LIVE_MAKEFILE)) - set(srcs(DRAIN_MAKEFILE)),
                         {"gbp_alive.c", "gbp_aplay.c", "gbp_adec.c", "gbp_aresamp.c"})
        self.assertEqual(set(srcs(DRAIN_MAKEFILE)) - set(srcs(LIVE_MAKEFILE)), {"gbp_adrain.c"})
        for absent in ("gbp_awindump.c", "gbp_asrc.c", "gbp_alisten.c"):
            self.assertNotIn(absent, srcs(LIVE_MAKEFILE))

    def test_one_hook_and_every_read_whole(self):
        l = read(LIVE_MAIN)
        self.assertIn("cfg.audio_tap = live_tap;", l)
        self.assertIn("cfg.session_end = &live_end;", l)
        self.assertNotIn("cfg.audio_len_live", l.split("int main(void)")[1].replace(
            "cfg.audio_len_live stays NULL", ""))
        self.assertNotRegex(l, r"gbp_awin_\w+\(")
        self.assertNotIn("cfg.awin", l)


class TheImageIsV22s(unittest.TestCase):
    """The numbers and the properties §V22 fixes, read out of the source."""

    def test_the_numbers(self):
        a, p = read(ALIVE_H), read(APLAY_H)
        self.assertEqual(define(a, "GBP_ALIVE_PERIOD"), 32)                     # one A: 128 Hz
        self.assertEqual(define(a, "GBP_ALIVE_CONTROL_BLOCKS"), 2048)           # §V19.11 A4.7
        self.assertEqual(define(a, "GBP_ALIVE_CONTROL_MIN"), 48)
        self.assertEqual(define(a, "GBP_ALIVE_ACCEPT_S"), 5)                    # A4.5
        self.assertEqual(define(a, "GBP_ALIVE_CONTROL_BOUND_S"), 10)            # A4.7
        self.assertGreaterEqual(define(a, "GBP_ALIVE_WINDOW_S"), 60)            # §V22.3
        self.assertGreaterEqual(define(p, "GBP_APLAY_RING"), 200)               # §V22.0, D2's x2
        self.assertEqual(define(p, "GBP_APLAY_RING"), 4096)                     # 1 s, 8 KiB (§V22.0)
        self.assertEqual(define(p, "GBP_APLAY_FRAMES") * 16, define(p, "GBP_APLAY_PUSHES") * 125)
        self.assertEqual(define(p, "GBP_APLAY_FRAMES") % 125, 0)                # acc 0 at every chunk
        self.assertEqual(define(p, "GBP_APLAY_CHUNK_BYTES") % 32, 0)
        self.assertEqual(define(p, "GBP_APLAY_L2_CHUNKS") * define(p, "GBP_APLAY_FRAMES"), 320000)   # 10 s
        m = read(LIVE_MAIN)
        self.assertEqual(define(m, "LIVE_L2_FROM_S"), 20)
        self.assertIn('#define TEST_ID "GBP-AUDIO-007"', m)
        self.assertIn("BUILD_ID   := live-0001", read(LIVE_MAKEFILE))

    def test_the_ring_size_is_said_not_to_fix_drift(self):
        self.assertIn("DOES NOT FIX drift", read(APLAY_H))

    def test_no_sd_call_before_the_session_has_ended(self):
        """§V22.0 / D2: every card call sits after the probe has returned."""
        m = read(LIVE_MAIN)
        body = m[m.index("int main(void)"):]
        probe = body.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);")
        for call in ("sdlog_stream_open(", "sdlog_stream_write(", "sdlog_stream_close(", "sdlog_save("):
            for k in [i.start() for i in re.finditer(re.escape(call), m)]:
                self.assertGreater(k, m.index("int main(void)") + probe, call)
        self.assertNotIn("sdlog_", m[:m.index("int main(void)")])

    def test_x_is_read_only_after_the_session(self):
        """§V22.9 A3: X is never acted on during the run; a press inside the window is recorded."""
        m = read(LIVE_MAIN)
        # the sites where the IMAGE acts on X (the static assert's GBP_PAD_BUTTON_X is not one). Through
        # the default input policy the pad's X also reaches the AGB as SELECT, as in play-0001; that is
        # the unchanged input path, and gbp_alive records the press as an `other` one (§V22.8 (r))
        x_sites = [i.start() for i in re.finditer(r"PAD_ButtonsDown\(0\) & PAD_BUTTON_X", m)]
        self.assertEqual(len(x_sites), 1)
        self.assertGreater(x_sites[0], m.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);"))
        self.assertIn("gbp_alive_buttons(&live, now, (uint16_t)(PAD_ButtonsHeld(PAD_CHAN0) & 0xFFFFu));",
                      function_text(m, "live_step"))

    def test_no_print_inside_cs_window(self):
        m = read(LIVE_MAIN)
        s = function_text(m, "live_screen")
        self.assertIn("live.phase == GBP_ALIVE_PROMPT", s)
        self.assertIn("live.phase == GBP_ALIVE_CONTROL", s)
        self.assertNotIn("GBP_ALIVE_WINDOW", s)
        for fn in ("live_step", "live_tap", "live_dma_cb"):
            self.assertNotIn("printf(", function_text(m, fn).replace("snprintf(", ""), fn)

    def test_l_is_read_before_any_correction(self):
        """§V22.8 (e): the tap hands L the sample the decoder just produced; the chain never sees L."""
        tap = function_text(read(LIVE_MAIN), "live_tap")
        self.assertLess(tap.index("gbp_adec_push_block(&adec, bytes)"), tap.index("gbp_alive_decoded("))
        self.assertNotIn("gbp_alive", read(APLAY_C))


# ---- the log ----------------------------------------------------------------------

def c_formats(src, tag):
    out = []
    for m in re.finditer(r'ringlog_printf\(&rl,\s*((?:"(?:[^"\\]|\\.)*"\s*)+),', src):
        fmt = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))
        if fmt.startswith(tag + " "):
            out.append(fmt)
    return out


WORST = {"%lu": "4294967295", "%llu": "18446744073709551615", "%llx": "ffffffffffffffff", "%x": "ffffffff",
         "%08lx": "ffffffff", "%u": "4294967295", "%d": "-2147483648"}
SPEC = r"%(?:08lx|llu|llx|lu|x|u|d|s)"


def worst_case(fmt, strings):
    it = iter(strings)
    return re.sub(SPEC, lambda m: WORST.get(m.group(0)) or next(it), fmt)


def render(fmt, values):
    return re.sub(SPEC, lambda m, it=iter(values): str(next(it)), fmt)


class NoLiveRecordCanBeTruncated(unittest.TestCase):

    def test_every_live_record_fits_the_ringlog_line_at_its_worst(self):
        m = read(LIVE_MAIN)
        tags = sorted(set(re.findall(r'"(LIVE[A-Z0-9]*) ', m)))
        self.assertGreaterEqual(len(tags), 14, tags)
        per_line = ",".join(["4294967295"] * 16)
        for tag in tags:
            for fmt in c_formats(m, tag):
                strings = {"LIVESEC": [per_line], "LIVEFILL": [per_line], "LIVEL2SAVE": ["x" * 159],
                           "LIVE": ["calibrate"]}.get(tag, [])
                line = worst_case(fmt, strings)
                self.assertLessEqual(len(line), RINGLOG_CONTENT_MAX, "%s renders %d characters" % (tag, len(line)))


class TheBuilderReadsWhatTheImageWrites(unittest.TestCase):
    """A synthetic log rendered from the image's OWN format strings, through
    tools/v22report.py and the FROZEN tools/v22accept.py."""

    def log(self, counts, phase="done", ticks=64 * TB, l=(8191, 32, 32), under=0, over=0, dup=222, drop=0,
            presses=(1, 0), save=(0, 0, 0), ctl=(63, 32, 32, 2048), gave_up=0):
        m = read(LIVE_MAIN)
        f = {tag: c_formats(m, tag)[0] for tag in
             ("LIVE", "LIVECTL", "LIVET", "LIVET2", "LIVEN", "LIVEL", "LIVEC", "LIVEM", "LIVEL2", "LIVEL2SAVE")}
        t0, origin = 0x100000000, 0x100000000 + 9 * TB
        lines = ["000001 IDENT test=GBP-AUDIO-007 app=gbp-audio-live build=live-0001 commit=abcdef0 libogc=x"]
        seq = [2]

        def put(fmt, vals):
            lines.append("%06u %s" % (seq[0], render(fmt, vals)))
            seq[0] += 1
        put(f["LIVE"], [phase, 1 if not gave_up else 0, gave_up, 0, 1, 0, presses[0], presses[1], 1])
        put(f["LIVECTL"], [ctl[0], ctl[1], ctl[2], ctl[3], 4096, 4096])
        put(f["LIVET"], [TB, "%x" % t0, "%x" % (t0 + 5 * TB), "%x" % (t0 + 8 * TB), "%x" % origin,
                         "%x" % (origin + 64 * TB)])
        put(f["LIVET2"], ["%x" % (origin + TB // 2), "%x" % (origin + 64 * TB), "%x" % (origin + ticks), 19146,
                          "%x" % origin])
        put(f["LIVEN"], [sum(counts) + 30000, sum(counts), sum(counts) + 30000, 0, 0, len(counts), 0])
        for k in range(0, len(counts), 16):
            put(c_formats(m, "LIVESEC")[0], [k, ",".join(str(c) for c in counts[k:k + 16])])
            put(c_formats(m, "LIVEFILL")[0], [k, ",".join("2048" for _ in counts[k:k + 16])])
        put(f["LIVEL"], [l[0], l[1], l[2], 0, l[0] + 1, sum(counts)])
        put(f["LIVEC"], [over, 0, under, under, dup, drop, 2034, 2030, 0, 0])
        put(f["LIVEM"], [2029, "%x" % (origin + TB // 2), "%x" % (origin + TB // 2 + 2028 * 1264440), 1000])
        put(f["LIVEL2"], [1, 1, 320, 320, 0, 40738, 58, 0, "0badf00d"])
        put(f["LIVEL2SAVE"], [save[0], save[1], save[2], 90000, "saved 90000 bytes"])
        return "\n".join(lines) + "\n"

    def evaluate(self, text, sidecar=None):
        import v22report
        import v22accept
        rep = v22report.build(text)
        return rep, v22accept.evaluate(rep, sidecar)

    def test_a_clean_run_passes_L_and_C(self):
        rep, r = self.evaluate(self.log([4096] * 64))
        self.assertEqual((r["L"]["verdict"], r["C"]["verdict"]), ("PASS", "PASS"), (r["L"]["why"], r["C"]["why"]))
        self.assertEqual(rep["l2_sidecar"], "present")
        self.assertEqual(len(rep["window"]["coverage"]), 64)
        self.assertAlmostEqual(r["M"]["rate_hz"], 1000 * 2028 * TB / (2028 * 1264440), places=3)

    def test_a_second_under_d1_is_a_drain_result(self):
        c = [4096] * 64
        c[30] = 4090
        rep, r = self.evaluate(self.log(c))
        self.assertEqual(r["L"]["verdict"], "INCONCLUSIVE")
        self.assertEqual(rep["window"]["not_drained"], 6)

    def test_an_underrun_fails_c_and_a_33_fails_l(self):
        rep, r = self.evaluate(self.log([4096] * 64, under=1, l=(8191, 32, 33)))
        self.assertEqual((r["L"]["verdict"], r["C"]["verdict"]), ("FAIL", "FAIL"))

    def test_a_session_that_ended_early_is_inconclusive(self):
        rep, r = self.evaluate(self.log([4096] * 40, phase="window", ticks=40 * TB + 1234))
        self.assertEqual(rep["window"]["ticks"], 40 * TB + 1234)
        self.assertEqual((r["L"]["verdict"], r["C"]["verdict"]), ("INCONCLUSIVE", "INCONCLUSIVE"))

    def test_a_press_inside_the_window_is_inconclusive(self):
        rep, r = self.evaluate(self.log([4096] * 64, presses=(1, 1)))
        self.assertEqual(r["L"]["verdict"], "INCONCLUSIVE")

    def test_a_failed_save_is_an_absent_record(self):
        import v22report
        rep = v22report.build(self.log([4096] * 64, save=(0, -1, -1)))
        self.assertTrue(rep["l2_sidecar"].startswith("absent: the log says its save failed"), rep["l2_sidecar"])
        rep = v22report.build(self.log([4096] * 64), sidecar_path="/nonexistent/l2.bin")
        self.assertTrue(rep["l2_sidecar"].startswith("absent: the file"), rep["l2_sidecar"])

    def test_a_control_that_gave_up_is_inconclusive(self):
        rep, r = self.evaluate(self.log([], phase="gave_up", ticks=0, gave_up=1, ctl=(20, 31, 33, 2048)))
        self.assertEqual(r["L"]["verdict"], "INCONCLUSIVE")


# ---- the audit ----------------------------------------------------------------------

class TheAuditDiscriminatesBothWays(unittest.TestCase):
    """Run the auditor on the real listings; never count its rules."""

    def _run(self, out_dir, profile):
        listing = os.path.join(out_dir, "audit", "elf.nm.txt")
        if not os.path.exists(listing):
            self.skipTest("%s is not built in this checkout" % out_dir)
        r = subprocess.run([sys.executable, AUDIT, os.path.join(out_dir, "audit"), "--profile", profile],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_live_passes_the_live_image(self):
        rc, out = self._run(LIVE_OUT, "live")
        self.assertEqual(rc, 0, out[:2000])
        self.assertIn("0 finding(s)", out)

    def test_live_fails_the_play_image(self):
        rc, out = self._run(PLAY_OUT, "live")
        self.assertNotEqual(rc, 0)
        self.assertIn("expected object missing: gbp_aplay.o", out)

    def test_play_fails_the_live_image(self):
        rc, out = self._run(LIVE_OUT, "play")
        self.assertNotEqual(rc, 0)

    def test_the_profile_is_derived_from_play(self):
        import poc_audit
        play, live = poc_audit.PROFILES["play"], poc_audit.PROFILES["live"]
        self.assertEqual(set(live["required_objects"]) - set(play["required_objects"]),
                         {"gbp_alive.o", "gbp_aplay.o", "gbp_adec.o", "gbp_aresamp.o", "gbp_aperiod.o",
                          "gbp_awin.o"})
        lifted = {"sdlog_stream_open", "sdlog_stream_write", "sdlog_stream_close"}
        self.assertEqual(set(play["forbidden_symbols"]) - set(live["forbidden_symbols"]), lifted)
        changed = lifted | {"gettime", "PAD_ButtonsHeld"}
        for s, want in play["symbol_callers"].items():
            if s not in changed:
                self.assertEqual(live["symbol_callers"][s], want, s)
        # the card is main's alone, after the session; the AI never leaves main, pump and its callback
        for s in ("sdlog_stream_open", "sdlog_stream_write", "sdlog_stream_close", "gbp_aplay_sidecar"):
            self.assertEqual(live["symbol_callers"][s], {"main": 1}, s)
        self.assertEqual(live["symbol_callers"]["AUDIO_InitDMA"], {"live_dma_cb": 1, "pump": 1})
        self.assertEqual(live["symbol_callers"]["gbp_adec_push_block"], {"live_tap": 1})


if __name__ == "__main__":
    unittest.main()
