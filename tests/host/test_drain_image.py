"""
tests/host/test_drain_image.py — GitHub Issue #84: the CONTINUOUS-DRAIN image
(poc/gbp-audio-drain-probe, GBP-AUDIO-005, drain-0001), pinned to its base,
to its pre-registration and to the report the frozen gates read.

THE SUBTRACTION IS SHOWN BY DIFFING, as Issue #59 did it for stream-0016.
§V19.11 A4.1 makes play-0001 the base, so every function the drain did not need
to touch is diffed character for character against play-0001's and must be
EQUAL, and every function it did touch differs by lines NAMED here.

THE LOG IS THE INTERFACE. The image writes DRAIN* records; tools/v19report.py
turns them into the report tools/v19drain.py (frozen at 364be84) decides on. A
format the image writes and the parser does not read -- or a line the ringlog
truncates -- would lose the run AFTER it was made. So the format strings are
read out of the image's source, rendered at their worst case, and fed back
through the parser and the frozen gates here.

THE AUDIT IS EXERCISED, NOT COUNTED: when the listings exist, `drain` passes this
image and fails play-0001's, and `play` fails this image.
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

DRAIN_MAIN = os.path.join(ROOT, "poc", "gbp-audio-drain-probe", "source", "main.c")
DRAIN_MAKEFILE = os.path.join(ROOT, "poc", "gbp-audio-drain-probe", "Makefile")
PLAY_MAIN = os.path.join(ROOT, "poc", "gbp-play-session", "source", "main.c")
PLAY_MAKEFILE = os.path.join(ROOT, "poc", "gbp-play-session", "Makefile")
AUDIT = os.path.join(ROOT, "tools", "poc_audit.py")
DRAIN_OUT = os.path.join(ROOT, "build", "poc", "gbp-audio-drain-probe")
PLAY_OUT = os.path.join(ROOT, "build", "poc", "gbp-play-session")
ADRAIN_H = os.path.join(ROOT, "src", "audio", "gbp_adrain.h")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
RINGLOG_CONTENT_MAX = 256 - 7 - 1      # LOG_LINE_LEN, minus the "%06u " prefix and the NUL


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


def added_lines(before, after):
    return _diff(before, after, "+")


def removed_lines(before, after):
    return _diff(before, after, "-")


def define(src, name):
    m = re.search(r"^#define\s+%s\s+(\S+)" % re.escape(name), src, re.M)
    assert m, name
    return int(m.group(1).rstrip("uUlL"), 0)


def srcs(makefile):
    return re.search(r"^SRCS := (.*)$", read(makefile), re.M).group(1).split()


class TheSubtractionAgainstPlay0001(unittest.TestCase):

    def test_the_untouched_functions_are_byte_identical(self):
        d, p = read(DRAIN_MAIN), read(PLAY_MAIN)
        for name in ("input_step", "session_step", "offer_oldest_ready", "display_selftest",
                     "video_setup", "gx_setup", "on_draw_done", "selftest_submit_headless"):
            self.assertEqual(function_text(d, name), function_text(p, name), name)

    def test_keylog_emit_gained_exactly_one_line(self):
        before, after = function_text(read(PLAY_MAIN), "keylog_emit"), function_text(read(DRAIN_MAIN), "keylog_emit")
        self.assertEqual(removed_lines(before, after), [])
        self.assertEqual([l.strip() for l in added_lines(before, after)],
                         ["drain_note_event(&e);   /* Issue #84: the A press, BEFORE the ringlog's own bound */"])
        self.assertLess(after.index("drain_note_event(&e);"), after.index("gbp_input_keylog_admit"))

    def test_pump_gained_exactly_the_drain_slot_after_the_session_step(self):
        before, after = function_text(read(PLAY_MAIN), "pump"), function_text(read(DRAIN_MAIN), "pump")
        self.assertEqual(removed_lines(before, after), [])
        self.assertEqual([l.strip() for l in added_lines(before, after)],
                         ["/* Issue #84: the drain's slot half -- the D2 mark and the two screens */",
                          "drain_step();"])
        self.assertLess(after.index("input_step();"), after.index("session_step();"))
        self.assertLess(after.index("session_step();"), after.index("drain_step();"))

    def test_submit_ready_lost_only_the_vi_hand_over(self):
        """A4.1: the frame is still converted, drawn and copied; only the two VI
        register writes are gone, so the prompt stays readable."""
        before, after = function_text(read(PLAY_MAIN), "submit_ready"), function_text(read(DRAIN_MAIN), "submit_ready")
        self.assertEqual([l.strip() for l in removed_lines(before, after)],
                         ["VIDEO_SetNextFramebuffer(xfb_stream_buf[xfb]);",
                          "VIDEO_Flush();                    /* register write only; NEVER VIDEO_WaitVSync here */"])
        for l in added_lines(before, after):
            self.assertTrue(l.strip().startswith(("/*", "*")), l)       # comments only
        for kept in ("draw_quad();", "GX_SetDrawDone();", "GX_CopyDisp(xfb_stream_buf[xfb], GX_TRUE);",
                     "gbp_vpresent_xfb_handed(&present, xfb);", "gbp_vqueue_note_presented(account);"):
            self.assertIn(kept, after)

    def test_the_sources_are_play_0001s_plus_three(self):
        self.assertEqual(set(srcs(DRAIN_MAKEFILE)) - set(srcs(PLAY_MAKEFILE)),
                         {"gbp_adrain.c", "gbp_aperiod.c", "gbp_awin.c"})
        self.assertEqual(set(srcs(PLAY_MAKEFILE)) - set(srcs(DRAIN_MAKEFILE)), set())
        self.assertNotIn("gbp_awindump.c", srcs(DRAIN_MAKEFILE))   # no window sidecar

    def test_the_window_is_linked_and_never_bound(self):
        d = read(DRAIN_MAIN)
        self.assertNotRegex(d, r"gbp_awin_\w+\(")                 # main names no window function
        self.assertNotIn("cfg.awin", d)
        self.assertIn("cfg.audio_tap = drain_tap;", d)
        self.assertIn("cfg.audio_len_live = &drain_len;", d)
        self.assertIn("cfg.session_end = &drain_end;", d)


class ThePreRegistrationsNumbersAreTheImages(unittest.TestCase):
    """§V19.11 A4.7 and §V19.7 A3, read out of the source rather than restated."""

    def test_the_drain_constants(self):
        d = read(DRAIN_MAIN)
        self.assertEqual(define(d, "DRAIN_PROGRAMMED_PERIOD"), 32)
        self.assertEqual(define(d, "DRAIN_CONTROL_BLOCKS"), 2048)
        self.assertEqual(define(d, "DRAIN_CONTROL_MIN_PERIODS"), 48)
        self.assertEqual(define(d, "DRAIN_D2_BYTES"), 65536)
        self.assertEqual(define(d, "DRAIN_D2_MARK_S"), 65)
        self.assertEqual(define(d, "PLAY_SAFETY_SECONDS"), 120)          # A3, not play-0001's 720
        self.assertEqual(define(read(PLAY_MAIN), "PLAY_SAFETY_SECONDS"), 720)

    def test_the_phase_machines_bounds(self):
        h = read(ADRAIN_H)
        self.assertEqual(define(h, "GBP_ADRAIN_ACCEPT_S"), 5)
        self.assertEqual(define(h, "GBP_ADRAIN_CONTROL1_BOUND_S"), 10)
        self.assertEqual((define(h, "GBP_ADRAIN_B_SECONDS"), define(h, "GBP_ADRAIN_C_SECONDS"),
                          define(h, "GBP_ADRAIN_A_STEP_SECONDS"), define(h, "GBP_ADRAIN_A_STEPS")), (60, 10, 3, 3))
        self.assertEqual((define(h, "GBP_ADRAIN_N0"), define(h, "GBP_ADRAIN_N1"), define(h, "GBP_ADRAIN_N2")),
                         (0x20, 0x100, 0x400))

    def test_the_amendment_states_the_same_numbers(self):
        t = read(HW)
        a = t[t.index("#### A4.7 Implementation definitions"):t.index("\n## V20 ")]
        for s in ("2 048 AUDIO blocks (0.5 s)", "at least 48 periods", "65 536 bytes", "65.000 s",
                  "capture start + 5.000 s", "bounded at 10 s", "32 AUDIO blocks"):
            self.assertIn(s, re.sub(r"\s+", " ", a), s)

    def test_the_budget_fits_the_safety_bound(self):
        # B + C + A + three control windows, against A3's 120 s; the rest is the Operator's press
        self.assertLess(60 + 10 + 9 + 3 * 0.5, 120 - 30)


# ------------------------------------------------------------------ the log as the interface

def c_formats(src, tag):
    """Every ringlog_printf format beginning with `tag `, its C string pieces joined."""
    out = []
    for m in re.finditer(r'ringlog_printf\(&rl,\s*((?:"(?:[^"\\]|\\.)*"\s*)+),', src):
        fmt = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))
        if fmt.startswith(tag + " "):
            out.append(fmt)
    return out


WORST = {"%lu": "4294967295", "%llu": "18446744073709551615", "%llx": "ffffffffffffffff", "%x": "ffffffff",
         "%u": "4294967295", "%d": "-2147483648"}


def worst_case(fmt, strings):
    """Render a format with every number at its type maximum and each %s from `strings`."""
    it = iter(strings)
    return re.sub(r"%(?:llu|llx|lu|x|u|d|s)", lambda m: WORST.get(m.group(0)) or next(it), fmt)


def render(fmt, values):
    return re.sub(r"%(?:llu|llx|lu|x|u|d|s)", lambda m, it=iter(values): str(next(it)), fmt)


class NoDrainRecordCanBeTruncated(unittest.TestCase):

    def test_every_drain_record_fits_the_ringlog_line_at_its_worst(self):
        d = read(DRAIN_MAIN)
        tags = sorted(set(re.findall(r'"(DRAIN[A-Z0-9]*) ', d)))
        self.assertGreaterEqual(len(tags), 12, tags)
        longest_status = "x" * 159                    # d2_status[160]
        per_line = ",".join(["4294967295"] * 16)      # DRAIN_SEC_PER_LINE counts at u32 max
        for tag in tags:
            for fmt in c_formats(d, tag):
                strings = {"DRAINSEC": [per_line], "DRAIND2S": [longest_status], "DRAIND2OPEN": [longest_status],
                           "DRAIN": ["recovery"], "DRAINCTL": ["recovery"], "DRAINCTL2": ["recovery"]}.get(tag, [])
                line = worst_case(fmt, strings)
                self.assertLessEqual(len(line), RINGLOG_CONTENT_MAX, "%s renders %d characters" % (tag, len(line)))

    def test_the_per_second_buffer_holds_a_whole_line(self):
        d = read(DRAIN_MAIN)
        m = re.search(r"char buf\[(\d+)\];", d)
        self.assertGreater(int(m.group(1)), len(",".join(["4294967295"] * 16)))


class TheParserReadsWhatTheImageWrites(unittest.TestCase):
    """A synthetic log rendered from the image's OWN format strings, through
    tools/v19report.py and the FROZEN tools/v19drain.py."""

    def synthetic_log(self, counts, d2=True, a=((1, 1, 60, 32, 32), (1, 1, 60, 32, 32), (1, 1, 60, 32, 32)),
                      control2_ok=1, recovered=1):
        d = read(DRAIN_MAIN)
        tb = 40500000
        t_b = 0x1000000000
        f = {tag: c_formats(d, tag)[0] for tag in ("DRAIN", "DRAINN", "DRAINT", "DRAIND1", "DRAIND2", "DRAINGAP")}
        lines = ["000001 IDENT test=GBP-AUDIO-005 app=gbp-audio-drain-probe build=drain-0001 commit=abcdef0 libogc=x"]
        seq = [2]

        def put(fmt, vals):
            lines.append("%06u %s" % (seq[0], render(fmt, vals)))
            seq[0] += 1
        put(f["DRAIN"], ["recovery" if recovered else "void", 1, 0, 0, control2_ok, 0, recovered, 3])
        put(f["DRAINN"], [sum(counts), 0, sum(counts), 0, len(counts), 0, 1, 0])
        put(f["DRAINT"], [tb, "%x" % (t_b - 5 * tb), "%x" % (t_b - 5 * tb + 5 * tb), "%x" % (t_b - tb),
                          "%x" % t_b, "%x" % (t_b + 60 * tb + 100)])
        put(f["DRAIND1"], [sum(counts[:60]), sum(counts[:60]), 60 * tb + 100])
        w0, w1 = t_b + 65 * tb + 5000, t_b + 65 * tb + 5000 + tb // 20     # a 50 ms write in second 65
        put(f["DRAIND2"], [0 if d2 else -1, 0 if d2 else 1, 0, 65536, 1 if d2 else 0, "%x" % w0, "%x" % w1])
        put(f["DRAINGAP"], [300, "%x" % t_b, tb // 20, "%x" % w1])
        sec_fmt = c_formats(d, "DRAINSEC")[0]
        for k in range(0, len(counts), 16):
            put(sec_fmt, [k, ",".join(str(c) for c in counts[k:k + 16])])
        a1, a2 = c_formats(d, "DRAINA")[0], c_formats(d, "DRAINA2")[0]
        for k, (ran, ok, per, pmin, pmax) in enumerate(a):
            put(a1, [k, "%x" % (0x20, 0x100, 0x400)[k], ran, ok, 12288, per, pmin, pmax])
            put(a2, [k, 0 if ok else 1, per + 1, 2 * per + 1, 0, 0])
        return "\n".join(lines) + "\n"

    def evaluate(self, log):
        import v19report
        import v19drain
        rep = v19report.build(log)
        return rep, v19drain.evaluate(rep)

    def test_a_clean_run_passes_d1_and_measures_d2_and_a(self):
        counts = [4096] * 81
        counts[65] = 4096 - 180                        # the D2 write's own second
        rep, out = self.evaluate(self.synthetic_log(counts))
        self.assertEqual(rep["test_id"], "GBP-AUDIO-005")
        self.assertEqual(len(rep["phase_b"]["counts"]), 60)
        self.assertEqual(out["D1"]["verdict"], "PASS")
        self.assertEqual(len(out["D1"]["windows"]), 57)               # seconds 3..59, reported in full
        self.assertEqual(out["D2"]["blocks_lost"], 180)
        self.assertAlmostEqual(out["D2"]["wall_ms"], 180 * 1000.0 / 4096)
        self.assertEqual(out["D2"]["ring_minimum_blocks"], 360)
        self.assertEqual(rep["phase_c"]["coverage_before"], 1.0)
        self.assertEqual(rep["phase_c"]["seconds_spanned"], [65, 65])
        self.assertEqual(out["A"]["verdict"], "SYNC-OK")
        self.assertEqual(out["A"]["recovery"], "RECOVERS")

    def test_five_blocks_short_in_one_window_fails_d1(self):
        counts = [4096] * 81
        counts[40] = 4091
        _, out = self.evaluate(self.synthetic_log(counts))
        self.assertEqual(out["D1"]["verdict"], "FAIL")
        self.assertEqual(out["D1"]["worst"]["window"], 37)            # second 40 is window 37 from t = 3 s

    def test_the_first_three_seconds_are_not_windows(self):
        counts = [4096] * 81
        counts[0], counts[2] = 3000, 3500                             # the tone's start, before 3.000 s
        _, out = self.evaluate(self.synthetic_log(counts))
        self.assertEqual(out["D1"]["verdict"], "PASS")

    def test_no_write_leaves_d2_unmeasured_not_guessed(self):
        import v19report
        rep = v19report.build(self.synthetic_log([4096] * 81, d2=False))
        self.assertIsNone(rep["phase_c"])
        self.assertIn("UNMEASURED", rep["phase_c_unmeasured"])

    def test_a_lost_step_stops_the_sweep(self):
        a = ((1, 1, 60, 32, 32), (1, 0, 58, 31, 33), (0, 0, 0, 0, 0))
        rep, out = self.evaluate(self.synthetic_log([4096] * 81, a=a, recovered=0))
        self.assertEqual([s["n"] for s in rep["phase_a"]["steps"]], [0x20, 0x100])   # the third never ran
        self.assertEqual(out["A"]["verdict"], "SYNC-LOST")
        self.assertEqual(out["A"]["recovery"], "NO-RECOVERY")

    def test_a_failed_second_control_is_inconclusive_never_sync_lost(self):
        a = ((0, 0, 0, 0, 0),) * 3
        _, out = self.evaluate(self.synthetic_log([4096] * 81, a=a, control2_ok=0))
        self.assertEqual(out["A"]["verdict"], "INCONCLUSIVE")

    def test_a_short_phase_b_is_inconclusive(self):
        import v19drain
        import v19report
        rep = v19report.build(self.synthetic_log([4096] * 81))
        rep["phase_b"]["phase_s"] = 59.9
        self.assertEqual(v19drain.evaluate(rep)["D1"]["verdict"], "INCONCLUSIVE")


class TheReportBuilderIsFrozenBeforeTheRun(unittest.TestCase):
    """tools/v19report.py decides nothing, but every choice in it could be argued
    into by data: it is the bytes of the commit that built the image, or the
    report the gates read is not the one that was frozen."""

    def test_v19report_is_the_bytes_of_the_commit_that_froze_it(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import frozen
        then = frozen.source("Issue #84 -- the drain report builder", "tools/v19report.py")
        self.assertEqual(then, read(os.path.join(ROOT, "tools", "v19report.py")),
                         "the report builder was edited after it was frozen")

    def test_the_gates_are_still_the_ones_frozen_at_364be84(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import frozen
        then = frozen.source("Issue #84 -- §V19 transcribed", "tools/v19drain.py")
        self.assertEqual(then, read(os.path.join(ROOT, "tools", "v19drain.py")))


class TheAuditDiscriminatesBothWays(unittest.TestCase):
    """Run the auditor on the real listings; never count its rules."""

    def _run(self, out_dir, profile):
        listing = os.path.join(out_dir, "audit", "elf.nm.txt")
        if not os.path.exists(listing):
            self.skipTest("%s is not built in this checkout" % out_dir)
        r = subprocess.run([sys.executable, AUDIT, os.path.join(out_dir, "audit"), "--profile", profile],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_drain_passes_the_drain_image(self):
        rc, out = self._run(DRAIN_OUT, "drain")
        self.assertEqual(rc, 0, out[:2000])
        self.assertIn("0 finding(s)", out)

    def test_drain_fails_the_play_image(self):
        rc, out = self._run(PLAY_OUT, "drain")
        self.assertNotEqual(rc, 0)
        self.assertIn("expected object missing: gbp_adrain.o", out)

    def test_play_fails_the_drain_image(self):
        rc, out = self._run(DRAIN_OUT, "play")
        self.assertNotEqual(rc, 0)

    def test_the_profile_is_derived_from_play(self):
        import poc_audit
        play, drain = poc_audit.PROFILES["play"], poc_audit.PROFILES["drain"]
        self.assertEqual(set(drain["required_objects"]) - set(play["required_objects"]),
                         {"gbp_adrain.o", "gbp_aperiod.o", "gbp_awin.o"})
        # the play profile's pins all survive, except the three stream functions it lifts
        lifted = {"sdlog_stream_open", "sdlog_stream_write", "sdlog_stream_close"}
        self.assertEqual(set(play["forbidden_symbols"]) - set(drain["forbidden_symbols"]), lifted)
        for s, want in play["symbol_callers"].items():
            if s not in lifted:
                self.assertEqual(drain["symbol_callers"][s], want, s)
        # the tap's work is the tap's alone
        self.assertEqual(drain["symbol_callers"]["gbp_adrain_block"], {"drain_tap": 1})
        self.assertEqual(drain["symbol_callers"]["sdlog_stream_write"], {"pump": 1})


if __name__ == "__main__":
    unittest.main()
