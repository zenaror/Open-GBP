"""
tests/host/test_vdisp.py — the OGBPDISP1 parser and the downstream analyzer
(HARDWARE_TESTS §V5.46).

The file under test is produced by the C WRITER itself
(tests/unit/test_gbp_vdisp --dump), so the Python parser is checked against the
real writer and never against a Python re-implementation of it. Every scenario
is SYNTHETIC; nothing here has seen hardware.
"""
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import vdisp  # noqa: E402

BIN = os.path.join(ROOT, "build", "tests", "unit", "test_gbp_vdisp")
_CACHE = {}


def fixture():
    if "raw" not in _CACHE:
        if not os.path.exists(BIN):
            raise unittest.SkipTest("run `make -C tests/unit` first")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "disp.bin")
            subprocess.run([BIN, "--dump", p], check=True, capture_output=True)
            with open(p, "rb") as f:
                _CACHE["raw"] = f.read()
    return _CACHE["raw"]


def reseal(buf):
    """Repairs the header CRC and then the global CRC, so a check that sits
    behind them can be reached. Mirrors the C test's helper exactly."""
    import binascii
    b = bytearray(buf)
    struct.pack_into(">I", b, vdisp.HEADER_SIZE - 4,
                     binascii.crc32(bytes(b[:vdisp.HEADER_SIZE - 4])) & 0xFFFFFFFF)
    off = struct.unpack_from(">I", b, 0x50)[0]
    struct.pack_into(">I", b, off + 8, binascii.crc32(bytes(b[:off])) & 0xFFFFFFFF)
    return bytes(b)


class TheWriterAndTheParserAgree(unittest.TestCase):
    def test_a_c_written_file_parses(self):
        i = vdisp.parse(fixture())
        self.assertEqual(i["version"], 2)
        self.assertEqual(i["life_record_size"], 128)
        self.assertEqual(i["event_record_size"], 40)
        self.assertEqual(i["build_id"], "stream-0008")
        self.assertEqual(i["test_id"], "GBP-VIDEO-004")
        self.assertEqual(i["tb_hz"], 40500000)
        self.assertEqual(i["tex_slots"], 2)
        self.assertEqual(i["xfb_slots"], 2)

    def test_the_geometry_is_self_consistent(self):
        i = vdisp.parse(fixture())
        self.assertEqual(i["off_life"], vdisp.HEADER_SIZE)
        self.assertEqual(i["off_events"], i["off_life"] + i["life_n"] * 128)
        self.assertEqual(i["off_footer"], i["off_events"] + i["event_n"] * 40)
        self.assertEqual(i["total_size"], len(fixture()))
        self.assertEqual(len(i["life"]), i["life_n"])
        self.assertEqual(len(i["events"]), i["event_n"])

    def test_the_window_and_the_selftest_are_distinguishable(self):
        i = vdisp.parse(fixture())
        self.assertEqual(i["window_first_frame"], 70)
        self.assertTrue(i["flags"] & vdisp.F_WINDOW_OPENED)
        st = [r for r in i["life"] if r["life_flags"] & 0x02]
        self.assertEqual(len(st), 1)
        self.assertEqual(st[0]["frame_index"], vdisp.KEY_NONE)
        self.assertFalse(st[0]["life_flags"] & 0x01)      # never in the window
        # The sidecar's own bit is WITNESS_ARMED_AT_TAKE and is NOT a
        # population (GBP-VID-019). It still excludes the self-test by flag.
        armed = vdisp.witness_armed_at_take(i)
        self.assertNotIn(vdisp.KEY_NONE, [r["frame_index"] for r in armed])
        self.assertEqual([r["frame_index"] for r in armed], [70, 71, 72, 75, 73, 74])
        # and asking for the scientific population without a witness is refused
        with self.assertRaises(vdisp.DispError):
            vdisp.scientific(i)

    def test_warm_up_lifecycles_are_traced_but_not_scientific(self):
        """§V5.46.19: the trace starts at capture start so the warm-up stays
        diagnosable, and the qualified population is identified by a flag rather
        than by anyone counting records."""
        i = vdisp.parse(fixture())
        keys = [r["frame_index"] for r in i["life"] if r["frame_index"] != vdisp.KEY_NONE]
        self.assertIn(68, keys)                            # warm-up IS recorded
        self.assertIn(69, keys)
        self.assertNotIn(68, [r["frame_index"] for r in vdisp.witness_armed_at_take(i)])
        # with an explicit source set, the join is what defines the population
        sci = vdisp.scientific(i, {70, 71, 72})
        self.assertEqual([r["frame_index"] for r in sci], [70, 71, 72])


class TheDispositionsAreTheAuditedBranches(unittest.TestCase):
    def test_every_disposition_maps_to_a_real_branch(self):
        i = vdisp.parse(fixture())
        got = {vdisp.DISPOSITION[r["disposition"]]
               for r in vdisp.witness_armed_at_take(i)}
        self.assertEqual(got, {"SELECTED_NEW", "HOLD_PREVIOUS", "SLOT_OVERRUN", "OPEN"})

    def test_a_hold_is_a_drawn_frame_and_the_row_says_so(self):
        """THE POINT OF THE WHOLE TRACE. A hold is not a conversion miss and not
        a GX miss: the frame was converted, submitted AND drawn, and still found
        no writable framebuffer."""
        i = vdisp.parse(fixture())
        h = vdisp.holds(i)
        self.assertEqual(len(h), 1)
        row = h[0]
        self.assertEqual(row["frame_index"], 72)
        self.assertEqual(row["reason"], "XFB_BUSY")
        self.assertTrue(row["was_drawn"])
        self.assertEqual((row["xfb_current"], row["xfb_pending"]), (0, 1))
        # the previous frame is the one still on screen, not the held one
        self.assertEqual(row["prev_index"], 71)

    def test_a_hold_does_not_become_the_previous_frame(self):
        """A held frame never reached a framebuffer, so the screen still shows
        whatever was there and the NEXT event's `prev_index` must still name
        that older frame.

        The `assertTrue(after)` is not decoration. This test first shipped
        against a fixture that ended on the hold, so it iterated over an empty
        list and passed without checking anything; mutation M12 found it by
        surviving. A test that can pass vacuously is worse than no test."""
        i = vdisp.parse(fixture())
        hold = next(e for e in i["events"] if e["decision"] == 2)
        after = [e for e in i["events"] if e["ordinal"] > hold["ordinal"]]
        self.assertTrue(after, "the fixture must contain an event AFTER the hold")
        for e in after:
            self.assertNotEqual(e["prev_index"], 72,
                                "a held frame became the previous frame")
        self.assertEqual(after[0]["prev_index"], 71)

    def test_residuals_separate_interior_from_the_capture_edge(self):
        i = vdisp.parse(fixture())
        r = vdisp.interior_vs_edge(i)
        self.assertEqual(r["open"], 1)
        self.assertEqual(r["interior"], [])        # nothing lost mid-run
        self.assertEqual(r["edge"], [74])          # the frame the run ended on

    def test_latencies_skip_stages_that_never_happened(self):
        """A frame that was abandoned has no submit time, and a distribution
        that counted it would be reporting an interval that does not exist."""
        i = vdisp.parse(fixture())
        lat = vdisp.latencies(i, vdisp.witness_armed_at_take(i))
        self.assertEqual(lat["close_to_take"]["n"], 6)
        self.assertEqual(lat["submit_to_drawdone"]["n"], 4)   # not 6
        for q in lat.values():
            if q:
                self.assertGreaterEqual(q["min"], 0)


class TheParserRefusesDamage(unittest.TestCase):
    def mutate(self, fn, expect_msg=None, do_reseal=False):
        b = bytearray(fixture())
        fn(b)
        raw = reseal(bytes(b)) if do_reseal else bytes(b)
        with self.assertRaises(vdisp.DispError) as cm:
            vdisp.parse(raw)
        if expect_msg:
            self.assertIn(expect_msg, str(cm.exception))

    def test_bad_magic(self):
        self.mutate(lambda b: b.__setitem__(0, b[0] ^ 1), "magic")

    def test_bad_version(self):
        self.mutate(lambda b: b.__setitem__(0x09, 9), "version")

    def test_bad_header_crc(self):
        self.mutate(lambda b: b.__setitem__(0x38, b[0x38] ^ 1), "header CRC")

    def test_truncation(self):
        with self.assertRaises(vdisp.DispError):
            vdisp.parse(fixture()[:-1])
        with self.assertRaises(vdisp.DispError):
            vdisp.parse(fixture()[:8])

    def test_a_single_corrupt_life_byte(self):
        self.mutate(lambda b: b.__setitem__(vdisp.HEADER_SIZE, b[vdisp.HEADER_SIZE] ^ 1),
                    "global CRC")

    def test_a_single_corrupt_event_byte(self):
        i = vdisp.parse(fixture())
        off = i["off_events"]
        self.mutate(lambda b: b.__setitem__(off, b[off] ^ 1), "global CRC")

    def test_bad_footer(self):
        i = vdisp.parse(fixture())
        off = i["off_footer"]
        self.mutate(lambda b: b.__setitem__(off, b[off] ^ 1), "footer")

    def test_bad_global_crc(self):
        self.mutate(lambda b: b.__setitem__(len(b) - 1, b[len(b) - 1] ^ 1), "global CRC")

    def test_record_size_must_be_the_frozen_one(self):
        self.mutate(lambda b: b.__setitem__(0x13, 99), "record sizes", do_reseal=True)

    def test_a_count_beyond_its_capacity(self):
        self.mutate(lambda b: struct.pack_into(">I", b, 0x1C, 9999), "capacity", do_reseal=True)

    def test_inconsistent_sections(self):
        self.mutate(lambda b: struct.pack_into(">I", b, 0x1C, 1), "sections", do_reseal=True)

    def test_an_unknown_flag_bit(self):
        """0x40 is INTERIOR_LOSS in v2, so the unknown bit has to be a higher
        one -- and setting a KNOWN flag whose counter is zero is rejected too,
        by the flag/counter agreement check."""
        self.mutate(lambda b: b.__setitem__(0x0F, b[0x0F] | 0x80), "flag", do_reseal=True)

    def test_a_flag_must_agree_with_the_counter_it_summarises(self):
        """The dangerous direction: a file CLEARING interior_loss while its
        counter says frames were lost would read as a clean run. The C parser
        rejects it and the Python one must agree, or the two disagree about
        what a file means."""
        i = vdisp.parse(fixture())
        self.assertGreater(i["source_dropped_interior"], 0, "the fixture must have one")
        self.assertTrue(i["flags"] & vdisp.F_INTERIOR_LOSS)
        self.mutate(lambda b: b.__setitem__(0x0F, b[0x0F] & ~0x40),
                    "interior_loss", do_reseal=True)
        self.mutate(lambda b: b.__setitem__(0x0F, b[0x0F] | 0x20),
                    "order_violation", do_reseal=True)

    def test_reserved_bytes_must_be_zero(self):
        self.mutate(lambda b: b.__setitem__(0x108, 1), "reserved", do_reseal=True)

    def test_an_identity_with_bytes_after_its_terminator(self):
        def f(b):
            for k in range(4):
                b[0xA8 + 20 + k] = 0x41
        self.mutate(f, "terminator", do_reseal=True)

    def test_a_section_crc_catches_what_the_global_one_would_blame_elsewhere(self):
        i = vdisp.parse(fixture())
        # move a byte within the life section AND repair the global CRC: only
        # the section CRC can still see it.
        b = bytearray(fixture())
        b[vdisp.HEADER_SIZE] ^= 1
        with self.assertRaises(vdisp.DispError) as cm:
            vdisp.parse(reseal(bytes(b)))
        self.assertIn("lifecycle section CRC", str(cm.exception))
        self.assertGreater(i["life_crc32"], 0)

    def test_an_unknown_enum_is_refused(self):
        i = vdisp.parse(fixture())
        off = i["off_life"] + 0x54            # disposition of life record 0
        self.mutate(lambda b: struct.pack_into(">H", b, off, 99), "global CRC")


class WhatItMayNotClaim(unittest.TestCase):
    def test_without_the_witness_it_says_nothing_about_source_continuity(self):
        r = vdisp.format_report(vdisp.parse(fixture()))
        self.assertIn("says NOTHING about", r)
        self.assertIn("SCIENTIFIC WINDOW: NOT AVAILABLE", r)
        self.assertIn("will not substitute the flag for one", r)
        self.assertIn("tools/vindex.py", r)
        for forbidden in ("OBSERVED_CONTIGUOUS", "OBSERVED_ID_GAP", "FRAME_ID"):
            self.assertNotIn(forbidden, r)

    def test_it_is_not_the_source_analyzer(self):
        """A separate tool, on purpose: reusing OGBPIDX1's vocabulary for a
        display decision would make two different questions look like one."""
        src = open(os.path.join(ROOT, "tools", "vdisp.py")).read()
        self.assertNotIn("import vindex", src)
        self.assertNotIn("import istim", src)

    def test_usability_refuses_an_overflowed_trace(self):
        i = vdisp.parse(fixture())
        self.assertTrue(vdisp.usable(i)["usable_for_disposition_claim"])
        i["life_overflow"] = 3
        u = vdisp.usable(i)
        self.assertFalse(u["usable_for_disposition_claim"])
        self.assertTrue(any("overflow" in x for x in u["reasons"]))

    def test_the_report_renders(self):
        r = vdisp.format_report(vdisp.parse(fixture()))
        self.assertIn("OGBPDISP1", r)
        self.assertIn("EVERY HOLD, ONE ROW EACH", r)
        self.assertIn("XFB_BUSY", r)
        self.assertLess(len(r.splitlines()), 200, "normal frames must not be dumped")


class TheWiringInMainIsPinned(unittest.TestCase):
    """THE GAP THE MUTATION ROUND FOUND, AND WHAT IT IS WORTH.

    `main.c` has no behavioural test — that is the exact defect that let
    `stream-0001` ship a draw-done callback which freed every submitted buffer
    (§V5.26.2). The modules it wires are tested state by state; the WIRING is
    not, so mutating an argument inside main.c passed every suite.

    This is not a behavioural test and does not pretend to be one. It reads the
    source and pins the argument expressions the trace depends on, so a change
    to WHAT IS PASSED is a failure rather than a silent re-interpretation. It
    can be defeated by someone who edits it too; it cannot be defeated by
    someone who forgets."""

    MAIN = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c")

    @classmethod
    def setUpClass(cls):
        cls.src = open(cls.MAIN).read()

    @staticmethod
    def strip_comments(src):
        import re as _re
        src = _re.sub(r"/\*.*?\*/", " ", src, flags=_re.S)
        return _re.sub(r"//[^\n]*", " ", src)

    def test_the_key_comes_from_the_descriptor_and_nowhere_else(self):
        """The generic key must be the ASSEMBLER's frame index, carried by the
        descriptor. A literal, a counter or a texture index here would silently
        break every offline join."""
        self.assertIn("gbp_vdisp_take(&disp, conv.desc.frame_index, conv.desc.seq,", self.src)
        self.assertIn("conv.desc.slot, conv.desc.flags,", self.src)
        self.assertIn("conv.desc.t_last, gettime(),", self.src)

    def test_the_window_flag_is_the_witness_latch(self):
        """IN_WINDOW must come from the witness's own ARMED state, so OGBPIDX1
        takes no part in deciding which lifecycles are scientific."""
        self.assertIn("gbp_vwitness_armed(&wit), 0);", self.src)

    def test_the_texture_map_is_updated_at_take(self):
        self.assertIn("tex_life[buf] = conv.life;", self.src)

    def test_the_selftest_carries_the_sentinel_and_the_flag(self):
        self.assertIn("gbp_vdisp_take(&disp, GBP_VDISP_KEY_NONE,", self.src)
        i = self.src.index("gbp_vdisp_take(&disp, GBP_VDISP_KEY_NONE,")
        self.assertIn("(uint16_t)buf, 0, 1);", self.src[i:i + 400],
                      "the self-test must be in_window=0, selftest=1")

    def test_the_framebuffer_question_is_asked_before_the_submit(self):
        """POLICY A's whole shape. `stream-0007` asked GX first and the
        framebuffer afterwards, so an unpresentable frame had already consumed a
        token and was then discarded. The precheck must come FIRST, and the
        snapshot must still sit between xfb_target() and xfb_handed()."""
        s = self.src
        i_gate = s.index("if (!gbp_vpresent_submit(&present, buf))")
        i_tgt = s.index("xfb = gbp_vpresent_xfb_target(&present, cur);")
        self.assertLess(i_tgt, i_gate, "the framebuffer is asked about FIRST")
        self.assertIn("gbp_vdisp_defer(&disp, life, t_dec, rt, cur, pend,", s)
        self.assertNotIn("gbp_vqueue_note_repeat(account)", s,
                         "policy A never terminates a frame on a busy framebuffer")
        i_target = s.index("xfb = gbp_vpresent_xfb_target(&present, cur);")
        i_pend = s.index("pend = present.xfb_pending;")
        i_copy = s.index("GX_CopyDisp(xfb_stream_buf[xfb]")
        i_handed = s.index("gbp_vpresent_xfb_handed(&present, xfb);")
        i_branch = s.index("    if (xfb < 0) {")
        self.assertLess(i_target, i_pend, "the snapshot must follow xfb_target()")
        self.assertLess(i_pend, i_copy, "the snapshot must precede the copy")
        self.assertLess(i_pend, i_handed, "the snapshot must precede the hand-over")
        # AND IT MUST BE UNCONDITIONAL. Taken inside the hand-off branch, the
        # DEFER path -- the one policy A exists for -- would record an
        # uninitialised value.
        self.assertLess(i_pend, i_branch,
                        "the snapshot must be taken on BOTH paths, before the branch")
        self.assertEqual(s.count("pend = present.xfb_pending;"), 1,
                         "exactly one assignment, so there is one thing to order")
        # and the clock is read before the decision, not after it
        i_t = s.index("t_dec = gettime();")
        self.assertLess(i_t, i_target)

    def test_nothing_in_the_present_path_waits(self):
        """§V5.49.3. The deferral is a STATE, not a delay. A VIDEO_WaitVSync or
        a spin anywhere between the framebuffer question and the hand-over would
        turn a non-blocking policy into a blocking one inside the service path."""
        # Comments FIRST. The present path contains the comment "NEVER
        # VIDEO_WaitVSync here", and a guard that could not tell that apart from
        # a call would be worthless -- the same trap the §V5.44 predicate guard
        # had to be taught.
        s = self.strip_comments(self.src)
        i_tgt = s.index("xfb = gbp_vpresent_xfb_target(&present, cur);")
        i_hand = s.index("gbp_vpresent_xfb_handed(&present, xfb);")
        body = s[i_tgt:i_hand]
        for forbidden in ("VIDEO_WaitVSync", "while (", "for (", "usleep", "sleep"):
            self.assertNotIn(forbidden, body, "the present path grew a %r" % forbidden)
        # the ONE legitimate wait is in the self-test, before the capture opens
        i_self = s.index("static void display_selftest(void)")
        i_pump = s.index("static void pump(void *user)")
        self.assertIn("VIDEO_WaitVSync", s[i_self:i_pump])
        self.assertNotIn("VIDEO_WaitVSync", s[i_pump:i_tgt])

    def test_the_map_is_closed_after_the_decision(self):
        """§V5.49.13 M5. Clearing `tex_life[buf]` after a hand-off is INERT
        today, and provably so: the key is written when the texture is ACQUIRED
        (`tex_life[buf] = conv.life;`, before the conversion even starts), and
        it is read only under a `tex[i] == READY` guard -- so no reader can ever
        observe the stale value. The line is kept as defence in depth and pinned
        here, because the equivalence is a property of the READY guard, not of
        the map: a future reader that is not READY-gated would make it load
        bearing, and nothing else would notice."""
        s = self.src
        self.assertEqual(s.count("tex_life[buf] = -1;"), 1)
        self.assertLess(s.index("gbp_vdisp_decision(&disp, life"),
                        s.index("tex_life[buf] = -1;"),
                        "the map must be closed AFTER the decision is recorded")
        # and the write that makes the equivalence hold must still precede READY
        self.assertLess(s.index("tex_life[buf] = conv.life;"),
                        s.index("gbp_vpresent_fill_done(&present, (int)conv.buf)"),
                        "the key must be written before the texture can be offered")

    def test_the_selftest_verdict_requires_a_present(self):
        """A self-test whose eight offers all defer arms no token, so `inflight`
        is 0 and `selftest_released` passes vacuously. ok=1 must mean the
        display path RAN."""
        self.assertIn("selftest_presents >= 1u", self.src)

    def test_the_target_is_asked_once_and_never_re_read(self):
        """§V5.49.13 M13. The precheck proves a framebuffer is free AT THE
        DECISION, and `gbp_vpresent_submit` changes the presenter's state after
        that. Asking again between the submit and `GX_CopyDisp` would hand GX
        whatever the SECOND answer is -- including -1 -- and would discard the
        very answer the §V5.49.2 safety proof is about. One question, one
        answer, used."""
        s = self.strip_comments(self.src)
        self.assertEqual(s.count("gbp_vpresent_xfb_target("), 1,
                         "the framebuffer must be asked about exactly once")
        self.assertLess(s.index("gbp_vpresent_xfb_target("),
                        s.index("if (!gbp_vpresent_submit(&present, buf))"))

    def test_the_offer_is_by_age_and_not_by_slot(self):
        """§V5.49 I2. `gbp_vpresent_acquire()` hands out the LOWEST free texture
        and the old loop scanned from index 0, so a newer frame in a lower slot
        could overtake a deferred older one. Both offer sites must go through
        the age-ordered helper."""
        s = self.src
        self.assertIn("static void offer_oldest_ready(void)", s)
        self.assertIn("tex_life[i] < best_life", s)
        # the pump retry and the conversion-completion site both use it
        self.assertEqual(s.count("offer_oldest_ready();"), 2)
        # and no site offers a raw slot index to the queue account any more
        self.assertNotIn("submit_ready((int)conv.buf, &vq);", s)
        self.assertNotIn("{ submit_ready((int)i, &vq); break; }", s)

    def test_the_new_trace_tag_is_unique(self):
        """§V5.49.6. `STREAMDISP` already names the legacy conservation
        identity; two different lines under one tag is a trap for any parser
        that keys on it."""
        s = self.src
        tags = [ln.split('"')[1].split()[0]
                for ln in s.splitlines() if 'ringlog_printf(&rl, "' in ln]
        self.assertEqual(len(tags), len(set(tags)), "duplicate log tag: %s" % tags)
        self.assertIn("DISPTRACE", tags)
        self.assertIn("DISPSRC", tags)

    def test_the_terminal_close_runs_before_the_sidecar_is_written(self):
        s = self.src
        self.assertLess(s.index("gbp_vdisp_finish(&disp);"),
                        s.index("gbp_vdispdump_stream(&disp_info, &disp, disp_chunk,"))

    def test_the_callback_identifies_the_frame_by_the_released_index(self):
        """The ISR must use what the ownership module RETURNED, not a search and
        not a guess, or a token could be credited to the wrong generation."""
        self.assertIn("const int idx = gbp_vpresent_draw_done(&present);", self.src)
        self.assertIn("gbp_vdisp_drawdone(&disp, idx, gettime());", self.src)

    def test_the_callback_does_nothing_else(self):
        """Nothing may be added here: no allocation, no printf, no filesystem,
        no GBP service state. `stream-0001` is why."""
        s = self.src
        i = s.index("static void on_draw_done(void)")
        body = s[i:s.index("\n}", i)]
        for forbidden in ("printf", "malloc", "sdlog", "memcpy", "for (", "while ("):
            self.assertNotIn(forbidden, body, "on_draw_done grew a %r" % forbidden)

    def test_both_sidecars_are_written_after_the_teardown_and_from_main(self):
        s = self.src
        self.assertIn("gbp_vdispdump_stream(&disp_info, &disp, disp_chunk,", s)
        self.assertLess(s.index("gbp_vidxdump_stream("), s.index("gbp_vdispdump_stream("))

    def test_the_trace_is_initialised_before_anything_can_record(self):
        """The init must precede the display self-test CALL -- not its
        definition, which sits far earlier in the file. The self-test opens the
        first lifecycle, so an init after it would zero the record it just
        wrote."""
        s = self.src
        i_init = s.index("gbp_vdisp_init(&disp, disp_life")
        i_call = s.index("display_selftest();")
        self.assertLess(i_init, i_call)
        # the anchor must be UNIQUE to the call site: `gbp_vstate_probe_run(`
        # also appears in a comment near the top of the file, and indexing that
        # would compare against line 42 instead of the call.
        self.assertLess(i_init, s.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);"))


if __name__ == "__main__":
    unittest.main()
