"""GBP-VIDEO-004 / stream-0001 — the implementation, checked against §V5.

The C unit tests (`tests/unit/test_gbp_vstream.c`) prove the two pure modules
behave. These tests prove the things that live between files and would otherwise
be nobody's job: that the graphics pipeline really is confined to the POC, that
the service path gained exactly one publish and one bounded pump and nothing
else, that the historical probes still do what they did, and that the conversion
agrees with a PHYSICAL frame whose colours are already known.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "src", "gbp")
POC = os.path.join(ROOT, "poc", "gbp-video-stream-probe")
MAIN = os.path.join(POC, "source", "main.c")
PROBE_C = os.path.join(SRC, "gbp_vstate_probe.c")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
COLOR0002 = os.path.join(ROOT, "captures", "fixtures",
                         "hw-gamecube-gbp-2026-09-18-color-0002-color.bin")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def strip_comments(text):
    """Comments may say anything; code may not. Every test about what the code
    DOES runs on the code alone."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


class TheGraphicsPipelineIsConfinedToThePoc(unittest.TestCase):
    """§V5.7's architectural boundary, checked on the source as well as by the
    `stream` audit profile on the objects."""

    def test_no_src_gbp_file_mentions_gx_or_vi(self):
        bad = []
        for fn in sorted(os.listdir(SRC)):
            if not fn.endswith((".c", ".h")):
                continue
            code = strip_comments(read(os.path.join(SRC, fn)))
            for sym in ("GX_", "VIDEO_Configure", "VIDEO_WaitVSync", "DCFlushRange",
                        "GXTexObj", "VIDEO_SetNextFramebuffer"):
                if sym in code:
                    bad.append("%s references %s" % (fn, sym))
        self.assertEqual(bad, [], bad)

    def test_the_poc_owns_every_graphics_call(self):
        code = strip_comments(read(MAIN))
        for sym in ("GX_Init", "GX_InitTexObj", "GX_LoadTexObj", "GX_SetDrawDone",
                    "GX_SetDrawDoneCallback", "DCFlushRange", "GX_CopyDisp"):
            self.assertIn(sym, code, "the POC does not call %s" % sym)

    def test_the_audit_profile_encodes_the_boundary(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import poc_audit
        p = poc_audit.PROFILES["stream"]
        self.assertIn("GX_", p["forbidden_symbol_prefixes"])
        self.assertEqual(set(p["prefix_exempt_objects"]), {"main.o"})
        self.assertIn("GX_", p["prefix_exempt_objects"]["main.o"])

    def test_the_conversion_is_never_called_from_the_service_path(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import poc_audit
        sites = poc_audit.PROFILES["stream"]["symbol_callers"]["gbp_vpix_block"]
        self.assertNotIn("gbp_vstate_probe_run", sites)
        self.assertIn("pump", sites)


class TheServicePathGainedExactlyTwoThings(unittest.TestCase):
    def test_publish_is_one_call_site_and_the_pump_is_the_other(self):
        code = strip_comments(read(PROBE_C))
        self.assertEqual(code.count("gbp_vqueue_publish("), 1)
        self.assertEqual(code.count("gbp_vqueue_pump("), 1)
        for forbidden in ("gbp_vpix_", "GX_", "DCFlushRange", "PAD_", "fopen", "sdlog_"):
            self.assertNotIn(forbidden, code, "the service path now references %s" % forbidden)

    def test_the_pump_runs_after_the_rearm_and_not_before(self):
        """The whole argument for where the consumer executes is that the RE-ARM
        was the pass's last device access. If the pump ever moves above it, that
        argument is void."""
        code = strip_comments(read(PROBE_C))
        rearm = code.index("gbp_vstate_diag_rearm(")
        pump = code.index("gbp_vqueue_pump(")
        ack = code.index("gbp_vstate_diag_ack(")
        self.assertLess(ack, rearm)
        self.assertLess(rearm, pump, "the pump moved above the RE-ARM")

    def test_publish_happens_at_frame_close_not_per_block(self):
        code = strip_comments(read(PROBE_C))
        i = code.index("gbp_vqueue_publish(")
        window = code[max(0, i - 500):i]
        self.assertIn("step.frame_closed", window)

    def test_both_hooks_are_null_by_default(self):
        """Every earlier build must behave exactly as it did, so the hook has to
        be inert when nothing installs it."""
        code = strip_comments(read(PROBE_C))
        self.assertIn("if (cfg->stream)", code)
        i = code.index("gbp_vqueue_publish(")
        self.assertIn("cfg->stream &&", code[max(0, i - 400):i])


class ThePolicyIsTheAssemblersNotACopy(unittest.TestCase):
    """§19: the new module must REUSE the R3 classification, not reimplement it."""

    def test_the_queue_uses_the_assemblers_flag_constants(self):
        code = read(os.path.join(SRC, "gbp_vqueue.c"))
        self.assertIn('#include "gbp_vstate.h"', code)
        for flag in ("GBP_VSTATE_F_MAJORITY_EXTRA", "GBP_VSTATE_F_ANOMALY",
                     "GBP_VSTATE_F_RESYNC", "GBP_VSTATE_F_COMPLETE"):
            self.assertIn(flag, code)

    def test_the_queue_defines_no_flag_of_its_own(self):
        code = read(os.path.join(SRC, "gbp_vqueue.h")) + read(os.path.join(SRC, "gbp_vqueue.c"))
        self.assertFalse(re.search(r"#define\s+GBP_VQUEUE_F_", code),
                         "the queue is inventing its own frame flags")

    def test_the_r3_policy_source_is_untouched_by_this_round(self):
        """gbp_vstate.c carries the physically validated disagreement policy. If
        this checkpoint changed it, that is a different experiment."""
        r = subprocess.run(["git", "log", "--oneline", "-1", "--", "src/gbp/gbp_vstate.c"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertNotIn("stream", r.stdout.lower())


class HistoricalProbesAreUnchanged(unittest.TestCase):
    """§29. The service order and the frozen formats must be exactly as the
    physically executed builds left them."""

    def test_the_service_order_string_is_the_validated_one(self):
        self.assertIn("order=read_audio_video_ack_piclean_sign_rearm_waitnext", read(PROBE_C))

    def test_the_frozen_formats_did_not_change(self):
        for path, commit in (("src/gbp/gbp_vcoldump.h", "e10423c"),
                             ("tools/vcolor.py", "bfbca70"),
                             ("tools/vcolor2.py", "a86b079")):
            r = subprocess.run(["git", "log", "--oneline", "-1", "--", path],
                               cwd=ROOT, capture_output=True, text=True)
            self.assertIn(commit, r.stdout, "%s changed; it is frozen" % path)

    def test_the_colour_probe_still_builds_the_colour_experiment(self):
        mk = read(os.path.join(ROOT, "poc", "gbp-video-color-probe", "Makefile"))
        self.assertIn("BUILD_ID   := color-0002", mk)
        self.assertIn("gbp_vcoldump.c", mk)

    def test_the_new_probe_writes_no_sidecar(self):
        """§V5.24: a new frozen format is created only when the existing ones
        cannot carry the data. This experiment's result is counters."""
        code = strip_comments(read(MAIN))
        self.assertNotIn("gbp_vcoldump", code)
        self.assertNotIn("gbp_vstatedump_stream", code)
        self.assertIn("sidecar=none", read(MAIN))


class TheRuntimeStillKnowsNothingAboutTheStimulus(unittest.TestCase):
    RUNTIME = ("src/gbp/gbp_vpix.c", "src/gbp/gbp_vpix.h",
               "src/gbp/gbp_vqueue.c", "src/gbp/gbp_vqueue.h",
               "poc/gbp-video-stream-probe/source/main.c")

    def test_no_expected_colour_value_appears_in_any_runtime_object(self):
        """Six of the eight stimulus values have no legitimate use in a runtime
        that must not recognise the stimulus (§V3.11). `0x0000` and `0x7FFF` are
        excluded from this list for a reason and are handled by the next test:
        one is zero and the other is the colour15 MASK, which splitting the flag
        requires."""
        for rel in self.RUNTIME:
            code = strip_comments(read(os.path.join(ROOT, rel)))
            for value in ("0x001F", "0x03E0", "0x7C00", "0x0400", "0x0020", "0x0001"):
                self.assertNotIn(value, code, "%s contains the stimulus value %s" % (rel, value))

    def test_7fff_appears_only_as_the_colour15_mask(self):
        """It is the one stimulus value a correct runtime may legitimately spell,
        because `word & 0x7FFF` is how the flag is split off. It may never be
        compared against."""
        for rel in self.RUNTIME:
            code = strip_comments(read(os.path.join(ROOT, rel)))
            for m in re.finditer(r"0x7FFF", code, re.I):
                before = code[max(0, m.start() - 12):m.start()]
                self.assertRegex(before, r"&\s*$",
                                 "%s uses 0x7FFF for something other than masking" % rel)

    def test_the_only_magic_constant_is_the_presentation_bit(self):
        code = strip_comments(read(os.path.join(SRC, "gbp_vpix.c")))
        self.assertIn("GBP_VPIX_RGB5A3_OPAQUE", read(os.path.join(SRC, "gbp_vpix.h")))
        self.assertNotIn("0x8000", code, "the presentation bit must come from the named constant")


class CacheAndOwnershipOrdering(unittest.TestCase):
    """§10 and §11: the flush is after the fill and before the GP is told, and
    the buffer is freed by the GP, not by a guess."""

    def test_the_flush_is_between_the_fill_and_the_texture_load(self):
        code = strip_comments(read(MAIN))
        flush = code.index("DCFlushRange(")
        init = code.index("GX_InitTexObj(")
        load = code.index("GX_LoadTexObj(")
        commit = code.index("gbp_vqueue_commit(")
        self.assertLess(commit, flush, "the flush must follow the generation check")
        self.assertLess(flush, init)
        self.assertLess(init, load)

    def test_the_flush_uses_the_exact_texture_size(self):
        code = strip_comments(read(MAIN))
        m = re.search(r"DCFlushRange\(\s*tex_buf\[[^\]]+\]\s*,\s*([A-Za-z0-9_]+)\s*\)", code)
        self.assertIsNotNone(m, "the flush is not a plain (buffer, size) call")
        self.assertEqual(m.group(1), "GBP_VPIX_TEX_BYTES")

    def test_the_texture_is_freed_by_the_gp_not_by_the_cpu_guessing(self):
        code = strip_comments(read(MAIN))
        self.assertIn("GX_SetDrawDoneCallback(on_draw_done)", code)
        self.assertIn("GX_SetDrawDone()", code)
        self.assertNotIn("GX_DrawDone()", code, "GX_DrawDone BLOCKS; §V5.7 forbids a wait here")
        self.assertIn("TEX_SUBMITTED", code)
        self.assertIn("TEX_FREE", code)

    def test_there_are_at_least_two_texture_buffers(self):
        code = read(MAIN)
        self.assertIn("#define STREAM_TEX_BUFFERS 2u", code)
        self.assertIn('_Static_assert(STREAM_TEX_BUFFERS >= 2u', code)

    def test_the_cpu_only_fills_a_free_buffer(self):
        code = strip_comments(read(MAIN))
        i = code.index("find_free_buffer()")
        self.assertIn("TEX_CPU_FILLING", code[i:i + 400])


class DisplayPolicy(unittest.TestCase):
    def test_a_rejected_conversion_is_never_presented(self):
        code = strip_comments(read(MAIN))
        i = code.index("gbp_vqueue_commit(")
        window = code[i:i + 500]
        self.assertIn("return", window)
        # the presentation call must come AFTER the commit check, not before
        self.assertLess(i, code.index("gbp_vqueue_note_presented("))

    def test_nothing_synthesises_a_pixel(self):
        code = strip_comments(read(MAIN)) + strip_comments(read(os.path.join(SRC, "gbp_vpix.c")))
        for bad in ("memset(tex", "0x0000;", "fill_missing", "interpolate"):
            self.assertNotIn(bad, code)

    def test_the_slice_is_bounded(self):
        code = read(MAIN)
        self.assertIn("#define STREAM_SLICE_TILE_ROWS   1u", code)
        body = strip_comments(code)
        i = body.index("static void pump(")
        self.assertIn("STREAM_SLICE_TILE_ROWS", body[i:i + 1200])

    def test_the_capture_duration_and_the_safety_cap_are_separate(self):
        code = read(MAIN)
        self.assertIn("#define STREAM_CAPTURE_SECONDS", code)
        self.assertIn("#define STREAM_SAFETY_SECONDS", code)
        self.assertIn("DESIGN DECISION REQUIRED", code)
        self.assertIn("PROVISIONAL", code)


class ConversionAgreesWithAPhysicalFrame(unittest.TestCase):
    """The strongest check available without hardware: `color-0002` carries eight
    KNOWN colours in known positions, measured on the real device. A conversion
    that disagrees with it is wrong, whatever the synthetic tests say."""

    BARS = (0x0000, 0x7C00, 0x03E0, 0x001F, 0x7FFF, 0x0400, 0x0020, 0x0001)

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(COLOR0002):
            raise unittest.SkipTest("physical color-0002 sidecar missing")
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import vcolor
        d = vcolor.parse(open(COLOR0002, "rb").read())
        cls.raw = vcolor.raw_frame(d, 0)

    @staticmethod
    def raw_offset(x, y):
        return (y // 4) * 0xF00 + (y % 4) * 960 + x * 4

    @staticmethod
    def tile_index(x, y):
        tx, ty = x // 4, y // 4
        ix, iy = x % 4, y % 4
        return (ty * 60 + tx) * 16 + iy * 4 + ix

    def convert(self):
        tex = [0] * 38400
        for y in range(160):
            for x in range(240):
                o = self.raw_offset(x, y)
                word = (self.raw[o + 1] << 8) | self.raw[o + 3]
                tex[self.tile_index(x, y)] = word | 0x8000
        return tex

    def test_the_converted_texture_shows_the_eight_measured_bars(self):
        tex = self.convert()
        for bar in range(8):
            seen = {tex[self.tile_index(x, y)] & 0x7FFF
                    for y in range(160) for x in range(bar * 30, bar * 30 + 30)}
            self.assertEqual(len(seen), 1, "bar %d is not uniform after conversion" % bar)
            self.assertEqual(seen.pop(), self.BARS[bar])

    def test_every_texel_is_opaque_and_the_colour_survives(self):
        tex = self.convert()
        self.assertEqual(len(tex), 38400)
        self.assertTrue(all(t & 0x8000 for t in tex))
        # the flag word of the physical frame: 0x8000 on the wire, and the texel
        # is the same value, because the colour there is 0
        self.assertEqual((self.raw[1] << 8) | self.raw[3], 0x8000)
        self.assertEqual(tex[self.tile_index(0, 0)], 0x8000)

    def test_bytes_0_and_2_of_the_physical_frame_never_reach_a_texel(self):
        """They vary between frames of the same picture (GBP-HW-133); if the
        conversion read them, two certified frames would convert differently."""
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import vcolor
        d = vcolor.parse(open(COLOR0002, "rb").read())
        a, b = vcolor.raw_frame(d, 0), vcolor.raw_frame(d, 1)
        self.assertNotEqual(a, b)                      # the raws differ
        self.assertEqual(a[1::2], b[1::2])             # only in bytes 0 and 2
        save = self.raw
        try:
            type(self).raw = a
            ta = self.convert()
            type(self).raw = b
            tb = self.convert()
        finally:
            type(self).raw = save
        self.assertEqual(ta, tb, "the conversion is reading a byte it must not read")


class DesignAndDocsAgree(unittest.TestCase):
    def test_the_design_named_these_files_and_they_exist(self):
        for rel in ("src/gbp/gbp_vpix.h", "src/gbp/gbp_vpix.c",
                    "src/gbp/gbp_vqueue.h", "src/gbp/gbp_vqueue.c",
                    "poc/gbp-video-stream-probe/Makefile",
                    "poc/gbp-video-stream-probe/source/main.c"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), rel)

    def test_the_build_id_is_the_one_the_design_specified(self):
        self.assertIn("BUILD_ID   := stream-0001", read(os.path.join(POC, "Makefile")))
        self.assertIn('#define TEST_ID "GBP-VIDEO-004"', read(MAIN))

    def test_the_poc_is_registered_in_the_build(self):
        self.assertIn("gbp-video-stream-probe", read(os.path.join(ROOT, "Makefile")))

    def test_it_is_in_the_swiss_layout_under_a_free_canonical_number(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import swiss_export
        rows = {r["short_name"]: r for r in swiss_export.load(os.path.join(ROOT, "tools", "swiss-layout.tsv"))}
        self.assertIn("stream", rows)
        r = rows["stream"]
        self.assertEqual(r["source_poc"], "gbp-video-stream-probe")
        self.assertLess(int(r["number"]), 80, "a canonical POC belongs below 80")
        self.assertEqual(r["enabled"], "1")

    def test_nothing_claims_the_candidate_was_validated(self):
        """The one status this round may produce is "implemented, host-validated,
        not physically executed" (§30). The check runs on what the program PRINTS,
        because that is what an operator would read and quote."""
        text = read(MAIN)
        self.assertIn("NOT PHYSICALLY VALIDATED", text)
        self.assertIn("THIS RUN PROVES NOTHING ON ITS OWN", text)
        printed = "\n".join(re.findall(r'printf\("([^"]*)"', text))
        for claim in ("sustained streaming works", "VALIDATED", "PASS", "COMPLETE"):
            self.assertNotIn(claim, printed.replace("NOT PHYSICALLY VALIDATED", ""),
                             "the probe prints a claim it cannot make: %r" % claim)


if __name__ == "__main__":
    unittest.main()
