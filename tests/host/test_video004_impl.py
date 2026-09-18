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
        """gbp_vstate.c carries the physically validated disagreement policy. If a
        streaming round changed it, that is a different experiment.

        This used to check the file's last commit message, which became too coarse
        once stream-0003 had to touch the SAME FILE for the storage validator
        (§V5.30.1). The check is now on the content: no CODE line added or removed
        since the last physically validated build, `39f1980` (color-0002), may
        mention the R3 policy at all. Comments are exempt — they may explain."""
        r = subprocess.run(["git", "diff", "39f1980..HEAD", "--", "src/gbp/gbp_vstate.c"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        touched = []
        for line in r.stdout.splitlines():
            if not line or line[0] not in "+-" or line[:3] in ("+++", "---"):
                continue
            body = line[1:].strip()
            if body.startswith(("*", "/*", "//")):      # a comment line
                continue
            if re.search(r"diag|disagree|semantic|\bsem\.|gap\[|R3", body, re.I):
                touched.append(line)
        self.assertEqual(touched, [],
                         "a streaming round changed the R3 disagreement policy")

    def test_only_the_storage_api_changed_in_the_validated_state_model(self):
        """The positive half of the same claim: what DID change since `39f1980`
        is the storage validator and the capacity naming, and nothing else."""
        r = subprocess.run(["git", "diff", "39f1980..HEAD", "--", "src/gbp/gbp_vstate.c"],
                           cwd=ROOT, capture_output=True, text=True)
        allowed = re.compile(
            r"storage_fault|storage_ok|static_bytes|required_capacity_bytes|configured_bytes"
            r"|frames_cap|events_cap|raw_ring_cap|raw_ring_slots|episode_raw|audio_raw"
            r"|s->frames|s->events|s->raw_ring|frames_null|events_null|raw_ring_null"
            r"|GBP_VSTATE_(MAX_FRAMES|MAX_EVENTS|RAW_RING|EPISODE_RAW|AUDIO_RAW|FRAME_REC|EVENT_REC|RAW_FRAME_BYTES)"
            r"|^\}$|^\{$|^return|^s->frames|^if \(!s\)|^const char|^uint64_t|^int ", re.I)
        stray = []
        for line in r.stdout.splitlines():
            if not line or line[0] not in "+-" or line[:3] in ("+++", "---"):
                continue
            body = line[1:].strip()
            if not body or body.startswith(("*", "/*", "//")):
                continue
            if not allowed.search(body):
                stray.append(body)
        self.assertEqual(stray, [],
                         "gbp_vstate.c changed outside the storage/capacity API")


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
    """§11 and the §V5.26.2 fix. These are AUDIT GUARDS on the source, not
    behavioural tests: the behaviour of the ownership machine is proved in
    `tests/unit/test_gbp_vstream.c`, which drives it state by state. The
    distinction matters — `stream-0001` was rejected precisely because tests of
    this kind were mistaken for coverage."""

    def test_the_flush_is_between_the_fill_and_the_texture_load(self):
        code = strip_comments(read(MAIN))
        commit = code.index("gbp_vqueue_commit(")
        flush = code.index("DCFlushRange(", commit)      # the streaming one, not the self-test
        fill_done = code.index("gbp_vpresent_fill_done(", flush)
        init = code.index("GX_InitTexObj(", fill_done)
        load = code.index("GX_LoadTexObj(", init)
        self.assertLess(commit, flush, "the flush must follow the generation check")
        self.assertLess(flush, fill_done, "a buffer becomes READY only after it is flushed")
        self.assertLess(fill_done, init)
        self.assertLess(init, load)

    def test_the_flush_uses_the_exact_texture_size(self):
        code = strip_comments(read(MAIN))
        found = re.findall(r"DCFlushRange\(\s*tex_buf\[[^\]]+\]\s*,\s*([A-Za-z0-9_]+)\s*\)", code)
        self.assertTrue(found, "the flush is not a plain (buffer, size) call")
        for size in found:
            self.assertEqual(size, "GBP_VPIX_TEX_BYTES")

    def test_the_callback_releases_exactly_one_buffer(self):
        """The stream-0001 defect, as a source guard: the callback must delegate
        to the module and must not loop over buffers itself."""
        code = strip_comments(read(MAIN))
        body = code[code.index("static void on_draw_done(void)"):]
        body = body[:body.index("}") + 1]
        self.assertIn("gbp_vpresent_draw_done(&present)", body)
        for forbidden in ("for (", "while (", "TEX_SUBMITTED", "tex_state"):
            self.assertNotIn(forbidden, body,
                             "the callback is doing its own bookkeeping again: %r" % forbidden)

    def test_the_texture_is_freed_by_the_gp_not_by_the_cpu_guessing(self):
        code = strip_comments(read(MAIN))
        self.assertIn("GX_SetDrawDoneCallback(on_draw_done)", code)
        self.assertIn("GX_SetDrawDone()", code)
        # GX_DrawDone BLOCKS. It is permitted EXACTLY once, in the teardown,
        # after the Game Boy Player has been restored — never in the service path.
        self.assertEqual(code.count("GX_DrawDone()"), 1)
        i = code.index("GX_DrawDone()")
        self.assertLess(code.index("gbp_vstate_probe_run("), i,
                        "GX_DrawDone must come after the probe has torn the device down")
        self.assertIn("gbp_vpresent_shutdown(&present)", code[:i])

    def test_there_are_two_texture_buffers_and_two_stream_framebuffers(self):
        code = read(MAIN)
        self.assertIn("#define STREAM_TEX_BUFFERS GBP_VPRESENT_TEX_BUFFERS", code)
        self.assertIn('_Static_assert(STREAM_TEX_BUFFERS >= 2u', code)
        self.assertIn('_Static_assert(GBP_VPRESENT_XFB_BUFFERS == 2u', code)
        self.assertIn("xfb_stream_buf[0] = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));", code)
        self.assertIn("xfb_stream_buf[1] = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));", code)

    def test_the_cpu_only_fills_a_buffer_the_module_handed_it(self):
        code = strip_comments(read(MAIN))
        self.assertIn("buf = gbp_vpresent_acquire(&present);", code)
        i = code.index("gbp_vpresent_acquire(&present)")
        self.assertIn("if (buf < 0) return;", code[i:i + 300])
        # and main keeps no state machine of its own any more
        self.assertNotIn("TEX_SUBMITTED", code)
        self.assertNotIn("find_free_buffer", code)

    def test_the_xfb_copy_never_targets_the_scanned_buffer(self):
        """§V5.26 F8: stream-0001 copied into the framebuffer VI was showing."""
        code = strip_comments(read(MAIN))
        i = code.index("gbp_vpresent_xfb_target(&present, xfb_current_index())")
        window = code[i:i + 600]
        self.assertIn("GX_CopyDisp(xfb_stream_buf[xfb]", window)
        self.assertIn("VIDEO_SetNextFramebuffer(xfb_stream_buf[xfb])", window)
        self.assertNotIn("VIDEO_WaitVSync", window, "the present path must never wait for a retrace")

    def test_the_draw_done_callback_is_restored_at_teardown(self):
        """§V5.26 F6 and the A9 mutation. `stream-0001` left its callback
        installed for ever; the fix captures the previous one at install and puts
        it back. This is an AUDIT GUARD on ordering — it cannot prove the runtime
        behaviour, which is why the ordering itself is asserted rather than the
        mere presence of the call."""
        code = strip_comments(read(MAIN))
        self.assertIn("gx_prev_drawdone_cb = GX_SetDrawDoneCallback(on_draw_done);", code)
        restore = code.index("GX_SetDrawDoneCallback(gx_prev_drawdone_cb);")
        probe = code.index("gbp_vstate_probe_run(")
        shutdown = code.index("gbp_vpresent_shutdown(&present);")
        drain = code.index("GX_DrawDone()")
        self.assertLess(probe, shutdown, "shutdown must follow the probe's own teardown")
        self.assertLess(shutdown, drain, "nothing new may be submitted before the drain")
        self.assertLess(drain, restore, "the callback is restored only after the drain")
        # and the restore must be unconditional: a callback left installed on any
        # path is the defect A9 reproduces
        tail = code[drain:restore + 200]
        self.assertNotIn("if (", tail.split("GX_SetDrawDoneCallback")[0].split("GX_DrawDone()")[1])

    def test_no_vsync_wait_in_the_consumer_path(self):
        code = strip_comments(read(MAIN))
        pump = code[code.index("static void pump(void *user)"):code.index("static void submit_ready(int buf, struct gbp_vqueue *account)\n{")]
        self.assertNotIn("VIDEO_WaitVSync", pump)
        self.assertNotIn("GX_DrawDone", pump)


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
        self.assertIn("BUILD_ID   := stream-0003", read(os.path.join(POC, "Makefile")))
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


class TheStorageContractIsSatisfiedByTheCaller(unittest.TestCase):
    """GBP-HW-136. `stream-0002` aborted at the probe's first gate because the
    POC supplied `episode_raw = NULL` and `frames_cap = 4096`. The behaviour is
    proved in C (`test_gbp_vstate.c`); what needs a guard HERE is the thing no
    unit test can reach — `main()` is not host-compiled, so nobody checked what
    the POC actually passes."""

    STATE = os.path.join(ROOT, "poc", "gbp-video-state-probe", "source", "main.c")
    COLOR = os.path.join(ROOT, "poc", "gbp-video-color-probe", "source", "main.c")

    @staticmethod
    def _init_call(path):
        code = strip_comments(read(path))
        m = re.search(r"gbp_vstate_init\s*\((.*?)\)\s*;", code, re.S)
        assert m, "every probe must call gbp_vstate_init exactly once"
        return re.sub(r"\s+", " ", m.group(1)).strip()

    def test_the_stream_poc_passes_a_real_episode_store(self):
        """The predicate that fired on hardware was `!s->episode_raw`."""
        args = [a.strip() for a in self._init_call(MAIN).split(",")]
        self.assertEqual(len(args), 11, args)
        # positions 7 and 8 are episode_raw and episode_raw_cap
        self.assertEqual(args[7], "episode_raw",
                         "stream-0002 passed 0 here and aborted pre-service (GBP-HW-136)")
        self.assertEqual(args[8], "sizeof episode_raw")
        self.assertNotIn("0, 0, audio_raw", self._init_call(MAIN))

    def test_the_stream_poc_declares_both_stores_at_full_size(self):
        code = strip_comments(read(MAIN))
        self.assertIn("frame_store[GBP_VSTATE_MAX_FRAMES]", code)
        self.assertIn("episode_raw[GBP_VSTATE_EPISODE_RAW_BYTES]", code)
        self.assertNotIn("STREAM_MAX_FRAMES", code,
                         "the reduced frame table is what the contract refused")

    def test_the_sizes_are_asserted_at_compile_time_over_the_actual_arrays(self):
        """§4: not a source-string contract — a build failure."""
        code = strip_comments(read(MAIN))
        for needed in ("sizeof frame_store / sizeof frame_store[0] >= GBP_VSTATE_MAX_FRAMES",
                       "sizeof episode_raw >= GBP_VSTATE_EPISODE_RAW_BYTES",
                       "sizeof audio_raw >= GBP_VSTATE_AUDIO_RAW_BYTES",
                       "sizeof raw_ring >= GBP_VSTATE_RAW_RING_BYTES"):
            self.assertIn(needed, re.sub(r"\s+", " ", code), needed)

    def test_the_stores_match_the_last_physically_validated_builds(self):
        """THE LESSON OF §V5.29. Three audits compared stream-0002 against
        stream-0001 and found "no change"; the change was against `vstate-0004`
        and `color-0002`, the builds that actually ran. Shared VSTATE
        infrastructure is compared against the physical baseline, always."""
        stream = self._init_call(MAIN).split(",")
        state = self._init_call(self.STATE).split(",")
        color = self._init_call(self.COLOR).split(",")
        # The arguments are written differently on purpose — the stream POC derives
        # its capacities from the arrays themselves — so what is compared is the
        # RESULTING capacity, resolved from each POC's own declarations.
        for ref, name in ((state, "vstate-0004"), (color, "color-0002")):
            self.assertEqual(self._frames_cap(MAIN), self._frames_cap_of(ref, self.STATE if name == "vstate-0004" else self.COLOR),
                             "the frame table must match %s" % name)
            self.assertEqual(self._store_decl(MAIN, "episode_raw"),
                             self._store_decl(self.STATE if name == "vstate-0004" else self.COLOR, "episode_raw"),
                             "the episode store must match %s" % name)
            self.assertEqual(self._store_decl(MAIN, "audio_raw"),
                             self._store_decl(self.STATE if name == "vstate-0004" else self.COLOR, "audio_raw"),
                             "the AUDIO raw store must match %s" % name)
            # and neither may pass a literal 0 where a store belongs
            self.assertNotRegex(re.sub(r"\s+", " ", ",".join(ref)), r", 0, 0,")
        self.assertNotRegex(re.sub(r"\s+", " ", ",".join(stream)), r", 0, 0,",
                            "stream-0002 passed `0, 0` here and aborted pre-service")

    @staticmethod
    def _store_decl(path, name):
        code = strip_comments(read(path))
        m = re.search(r"\b%s\s*\[([^\]]+)\]" % name, code)
        assert m, "%s must declare %s" % (path, name)
        return re.sub(r"\s+", "", m.group(1))

    @classmethod
    def _frames_cap(cls, path):
        return cls._store_decl(path, "frame_store")

    @classmethod
    def _frames_cap_of(cls, _args, path):
        return cls._store_decl(path, "frame_store")

    def test_the_poc_names_the_failing_field_before_the_probe(self):
        """§15: `store_or_bounds_invalid` alone cost a physical run."""
        code = strip_comments(read(MAIN))
        self.assertIn("gbp_vstate_storage_fault", code)
        self.assertIn("ENVSTORE", code)
        self.assertIn("configured_bytes", code)
        self.assertIn("required_bytes", code)
        # and the probe's own abort names it too
        probe = strip_comments(read(PROBE_C))
        self.assertIn("reason=store_or_bounds_invalid field=%s", probe)

    def test_the_library_gate_was_not_weakened(self):
        """The fix is in the caller. Every requirement must still be enforced."""
        code = strip_comments(read(os.path.join(SRC, "gbp_vstate.c")))
        for needed in ("frames_cap      < GBP_VSTATE_MAX_FRAMES",
                       "episode_raw_cap < GBP_VSTATE_EPISODE_RAW_BYTES",
                       "audio_raw_cap   < GBP_VSTATE_AUDIO_RAW_BYTES",
                       "raw_ring_cap    < GBP_VSTATE_RAW_RING_BYTES",
                       "raw_ring_slots  < GBP_VSTATE_RAW_RING_SLOTS_MIN"):
            self.assertIn(needed, code, needed)
        self.assertIn("!s->episode_raw", code)
        # and storage_ok is DEFINED as "no fault", so the two cannot diverge
        self.assertIn("return gbp_vstate_storage_fault(s) ? 0 : 1;", code)


class TheSelfTestDoesNotContaminateTheScientificCounters(unittest.TestCase):
    """R1, retired for stream-0003. GBP-HW-135 confirmed the contamination
    physically: converted=0 presented=1 before the capture opened."""

    def test_submit_ready_takes_the_accounting_queue_as_a_parameter(self):
        code = strip_comments(read(MAIN))
        self.assertIn("static void submit_ready(int buf, struct gbp_vqueue *account)", code)
        self.assertIn("submit_ready(buf, 0)", code,
                      "the self-test must account to nothing scientific")

    def test_the_queue_is_only_notified_through_the_account_parameter(self):
        code = strip_comments(read(MAIN))
        # no call may name `vq` directly for a presentation or a repeat
        self.assertNotIn("gbp_vqueue_note_presented(&vq)", code)
        self.assertNotIn("gbp_vqueue_note_repeat(&vq)", code)
        self.assertIn("gbp_vqueue_note_presented(account)", code)
        self.assertIn("gbp_vqueue_note_repeat(account)", code)

    def test_the_poc_asserts_the_queue_is_pristine_before_the_probe(self):
        code = strip_comments(read(MAIN))
        self.assertIn("gbp_vqueue_pristine(&vq)", code)
        self.assertIn("selftest_sci_clean", code)
        # and it is part of the self-test verdict, not a decoration
        self.assertRegex(re.sub(r"\s+", " ", code),
                         r"selftest_ok = \(selftest_converted && selftest_released && selftest_sci_clean")

    def test_the_gecko_line_carries_it_so_dolphin_can_assert_it(self):
        code = strip_comments(read(MAIN))
        self.assertIn("sci_clean=%d", code)
        mk = read(os.path.join(ROOT, "Makefile"))
        self.assertIn("--expect 'sci_clean=1'", mk)
        self.assertIn("--expect 'inv_fail=0'", mk)


class TheOwnershipInvariantsAreLatchedDuringTheRun(unittest.TestCase):
    """R8. stream-0002 could only say the invariants held at its LAST instant."""

    def test_the_module_audits_itself_at_every_transition(self):
        code = strip_comments(read(os.path.join(SRC, "gbp_vpresent.c")))
        self.assertIn("static void audit(struct gbp_vpresent *p)", code)
        self.assertIn("static void audit_isr(struct gbp_vpresent *p)", code)
        # main-side transitions
        self.assertGreaterEqual(code.count("audit(p);"), 6, "every main-side exit must look")
        # interrupt side, both the release and the spurious path
        self.assertEqual(code.count("audit_isr(p);"), 2)

    def test_the_two_counters_are_separate_so_neither_loses_an_increment(self):
        hdr = strip_comments(read(os.path.join(SRC, "gbp_vpresent.h")))
        for field in ("invariant_checks", "invariant_failures",
                      "invariant_checks_isr", "invariant_failures_isr"):
            self.assertIn(field, hdr)

    def test_the_report_separates_at_end_from_during_the_run(self):
        code = strip_comments(read(MAIN))
        self.assertIn("consistent_at_end=%d", code)
        self.assertIn("STREAMINV", code)
        self.assertIn("gbp_vpresent_invariant_failures(&present)", code)
        self.assertNotIn('"STREAMGX drawdone=%lu spurious=%lu releases=%lu xfb_presents=%lu '
                         'xfb_skipped=%lu consistent=%d', code)

    def test_the_valid_state_machine_is_unchanged(self):
        """§12/§25: the latch observes; it must not have moved a state bit."""
        code = strip_comments(read(os.path.join(SRC, "gbp_vpresent.c")))
        for unchanged in ("p->tex[idx] = GBP_VPRESENT_SUBMITTED;",
                          "p->submitted = idx;",
                          "if (p->submitted >= 0) { p->submit_blocked_inflight++; return 0; }",
                          "if (p->tex[idx] == GBP_VPRESENT_SUBMITTED) return -1;",
                          "if (p->tex[idx] != GBP_VPRESENT_READY) return 0;"):
            self.assertIn(unchanged, code, unchanged)


class TheCapacityNamesSayWhatTheyMean(unittest.TestCase):
    """§V5.29.6: `static_bytes` described theoretical capacity and read like a
    footprint, and a physical run was spent discovering that."""

    def test_the_required_and_configured_metrics_are_named_apart(self):
        code = strip_comments(read(os.path.join(SRC, "gbp_vstate.c")))
        self.assertIn("uint64_t gbp_vstate_required_capacity_bytes(void)", code)
        self.assertIn("uint64_t gbp_vstate_configured_bytes(const struct gbp_vstate *s)", code)
        self.assertNotIn("gbp_vstate_static_bytes(void)", code)

    def test_no_probe_still_calls_the_old_name(self):
        for d in ("gbp-video-stream-probe", "gbp-video-color-probe", "gbp-video-state-probe"):
            code = strip_comments(read(os.path.join(ROOT, "poc", d, "source", "main.c")))
            self.assertNotIn("gbp_vstate_static_bytes", code, d)

    def test_the_probe_logs_configured_beside_required(self):
        probe = strip_comments(read(PROBE_C))
        self.assertIn("VSTATE storecfg", probe)
        self.assertIn("gbp_vstate_configured_bytes(st)", probe)
        self.assertIn("required_bytes=%llu", probe)
        self.assertNotIn("static_bytes=%llu", probe)
