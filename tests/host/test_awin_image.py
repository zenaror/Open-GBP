"""
tests/host/test_awin_image.py — GitHub Issue #59: the AUDIO WINDOW image
(poc/gbp-audio-window-probe, GBP-AUDIO-001, stream-0016), pinned to its
sources and to HARDWARE_TESTS §V8.

THE SUBTRACTION IS THE POINT, and it is done by DIFFING, not by asserting.
Issue #59 item 4 asks for the service path and the input path "byte-identical,
demonstrated the way #39 demonstrated it -- the subtraction with the lines that
moved -- not asserted". So:

  * input_step(), session_step() and submit_ready() are diffed character for
    character against play-0001's and must be EQUAL;
  * keylog_emit() and pump() are diffed too, and the difference must be EXACTLY
    ONE added line each, and that line is NAMED here;
  * every strictly frozen service-path file is unchanged against the Issue #19
    base, and gbp_vstate_probe.c's diff against it must contain NO device
    operation -- the added lines are checked to be the window's hook and its
    two clock reads and nothing else.

THE WINDOW MAY NOT BE ECONOMISED. §V8.3.2 froze four windows of 256 blocks and
§V8.5.1 requires a control, and the constants are read out of the module and
checked against the pre-registration's own text. Issue #59: "if the store
budget cannot fund 4 MB, that is a finding to report, not a reason to shrink
the window".

THE AUDIT PROFILE IS EXERCISED, NOT COUNTED (#44's lesson, #59 item 6): when
the listings exist, `awin` passes this image and FAILS the play image, and
`play` FAILS this image. The test runs the auditor; it never counts its rules.
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import guards  # noqa: E402

AWIN_MAIN = os.path.join(ROOT, "poc", "gbp-audio-window-probe", "source", "main.c")
AWIN_MAKEFILE = os.path.join(ROOT, "poc", "gbp-audio-window-probe", "Makefile")
PLAY_MAIN = os.path.join(ROOT, "poc", "gbp-play-session", "source", "main.c")
AWIN_H = os.path.join(ROOT, "src", "gbp", "gbp_awin.h")
AWIN_C = os.path.join(ROOT, "src", "gbp", "gbp_awin.c")
DUMP_H = os.path.join(ROOT, "src", "gbp", "gbp_awindump.h")
DUMP_C = os.path.join(ROOT, "src", "gbp", "gbp_awindump.c")
PROBE_H = os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.h")
PROBE_C = os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.c")
VSTATE_H = os.path.join(ROOT, "src", "gbp", "gbp_vstate.h")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
TOP_MAKEFILE = os.path.join(ROOT, "Makefile")
UNIT_MAKEFILE = os.path.join(ROOT, "tests", "unit", "Makefile")
AUDIT = os.path.join(ROOT, "tools", "poc_audit.py")
AWIN_OUT = os.path.join(ROOT, "build", "poc", "gbp-audio-window-probe")
# the identity Hardware Issue #61 carries, recomputed by the Orchestrator from the clean tree
AWIN_DOL_SHA256 = "c3281a8c1382a1136a881c5548ef8238d69fa7862861d66741310b3d1f5f9c54"
PLAY_OUT = os.path.join(ROOT, "build", "poc", "gbp-play-session")

# origin/main at the start of Issue #19, the base every service-path freeze uses
BASE_COMMIT = "a877284bdda42ee77bbb52743eefd619c738574c"
SERVICE_PATH_FILES = ("gbp_vstate.c", "gbp_vqueue.c", "gbp_vwitness.c", "gbp_vpresent.c",
                      "gbp_vdisp.c", "gbp_vfull.c", "gbp_vvi.c", "gbp_irq_service.c", "gbp_vsig.c",
                      "gbp_vidxdump.c", "gbp_vdispdump.c", "gbp_vfulldump.c", "gbp_vvidump.c",
                      "gbp_vstatedump.c")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _bounded(t, start):
    """From `start`'s heading to the NEXT top-level V heading, never to EOF.
    §V8's slices ran to the end of the document and had silently been reading
    §V9 for a whole checkpoint; §V10 is what made it visible. The fix is to
    BOUND the slice, not to move a pin -- the lesson of Issue #50."""
    i = t.index(start)
    j = t.find("\n## V", i + 1)
    return t[i:j] if j >= 0 else t[i:]


def define(src, name):
    m = re.search(r"^#define\s+%s\s+(\S+)" % re.escape(name), src, re.M)
    assert m, name
    return m.group(1)


def num(s):
    return int(s.rstrip("uUlL"))


def function_text(src, name):
    m = re.search(r"^static (?:void|int) %s\([^;{]*\)\n\{" % re.escape(name), src, re.M)
    assert m, name
    j = src.index("\n}\n", m.start()) + 3
    return src[m.start():j]


def added_lines(before, after):
    """The lines `after` has that `before` does not, in order, ignoring pure
    moves: a real diff, not a set difference."""
    import difflib
    out = []
    for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0):
        if line.startswith("+") and not line.startswith("+++"):
            out.append(line[1:])
    return out


def removed_lines(before, after):
    import difflib
    out = []
    for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0):
        if line.startswith("-") and not line.startswith("---"):
            out.append(line[1:])
    return out


class TheSubtractionAgainstPlay0001(unittest.TestCase):
    """What moved, shown by diffing, and nothing else moved."""

    def test_the_input_step_and_the_session_step_are_byte_identical(self):
        a, p = read(AWIN_MAIN), read(PLAY_MAIN)
        for name in ("input_step", "session_step", "submit_ready", "offer_oldest_ready"):
            self.assertEqual(function_text(a, name), function_text(p, name), name)

    def test_keylog_emit_gained_exactly_one_line_and_here_it_is(self):
        a, p = read(AWIN_MAIN), read(PLAY_MAIN)
        before, after = function_text(p, "keylog_emit"), function_text(a, "keylog_emit")
        added = added_lines(before, after)
        self.assertEqual(removed_lines(before, after), [])
        self.assertEqual(len(added), 1, added)
        self.assertEqual(added[0].strip(),
                         "awin_note_event(&e);   /* Issue #59 (A): the anchor, BEFORE the ringlog's own bound */")
        # and it sits BEFORE the admission test, so the anchor never depends on the log's headroom
        self.assertLess(after.index("awin_note_event(&e);"), after.index("gbp_input_keylog_admit"))
        self.assertGreater(after.index("awin_note_event(&e);"), after.index("gbp_input_take_event"))

    def test_pump_gained_exactly_one_line_and_here_it_is(self):
        a, p = read(AWIN_MAIN), read(PLAY_MAIN)
        before, after = function_text(p, "pump"), function_text(a, "pump")
        added = added_lines(before, after)
        self.assertEqual(removed_lines(before, after), [])
        self.assertEqual([l.strip() for l in added],
                         ["/* Issue #59 (B): the control's gate and the capture's own success, after it. */",
                          "awin_gate();"])
        # the order of the slot is unchanged: the input step is still FIRST
        body = after[after.index("(void)user;"):]
        self.assertRegex(body, r"\(void\)user;\s*\n\s*/\*[^*]*\*/\s*\n\s*input_step\(\);")
        self.assertLess(body.index("input_step();"), body.index("session_step();"))
        self.assertLess(body.index("session_step();"), body.index("awin_gate();"))

    def test_the_two_insertions_touch_no_device_and_no_clock_of_their_own(self):
        a = read(AWIN_MAIN)
        for name in ("awin_note_event", "awin_gate"):
            body = function_text(a, name)
            for forbidden in ("hsp_", "gbp_regwrite", "gettime(", "PAD_", "sdlog", "printf", "ringlog"):
                self.assertNotIn(forbidden, body, "%s must not reach %s" % (name, forbidden))
        # the gate's only clock is the transport's, the same base the KEY record uses
        self.assertIn("t->ticks64(t->ctx)", function_text(a, "awin_gate"))


class TheServicePathIsUnchangedExceptForOneHook(unittest.TestCase):

    def test_every_strictly_frozen_file_is_byte_identical_to_the_base(self):
        if not guards.base_available(BASE_COMMIT):
            self.skipTest("the base commit is not in this checkout")
        changed = guards.changed_since(BASE_COMMIT, ["src/gbp/" + f for f in SERVICE_PATH_FILES])
        # Issue #65 (2026-09-22) BUILT stimulus/agb-tone (tone-0001), §V9's two-frequency stimulus: a new
        # stimulus ROM beside the four the family already had. It touches no runtime path, no image and no
        # slot; §V9.14 records its identity and tests/host/test_agb_tone.py runs its own code on the host.
        changed = changed - {"stimulus/agb-tone/Makefile", "stimulus/agb-tone/source/main.c"}
        # Issue #70 (2026-09-22) BUILT stimulus/agb-sweep (sweep-0001), §V11's TWO-AXIS stimulus: a new
        # stimulus ROM beside the five the family now has, and agb-tone is NOT touched (a test pins it
        # byte-identical). It touches no runtime path, no image and no slot; §V11.15 records its
        # identity and tests/host/test_agb_sweep.py runs its own code on the host.
        changed = changed - {"stimulus/agb-sweep/Makefile", "stimulus/agb-sweep/source/main.c"}
        # Issue #64 (2026-09-22) pre-registered agb-tone (§V9) and made its constructions executable BEFORE
        # the ROM exists: tools/v9tone.py is exercised on SYNTHETIC vectors only, reads no run, authorises
        # nothing and promotes nothing.
        changed = changed - {"tools/v9tone.py"}
        # Issue #69 (2026-09-22) pre-registered the amplitude sweep (§V11) and froze its constructions
        # BEFORE stimulus/agb-sweep exists: tools/v11sweep.py runs on SYNTHETIC vectors only, reads no
        # run, authorises nothing and promotes nothing. It is the fourth outing of the same discipline.
        changed = changed - {"tools/v11sweep.py"}
        # Issue #74 (2026-09-23) added tools/geckorx.py, the HOST receiver for the Operator's Pico
        # Gecko. It reads a serial port and writes bytes to a file; it touches no image, no POC and
        # no runtime path, and CLAUDE.md §14 forbids anything coming to depend on the device.
        changed = changed - {"tools/geckorx.py"}
        # Issue #62 (2026-09-22) ingested RUN 30 and needed two READERS that did not exist: awinparse.py,
        # a strict parser for the OGBPAW1 sidecar, and tprime.py, §V7.9's decision rule. Both only read and
        # report; the VERDICT constructions stay in tools/v8audio.py, which tests/host/test_run30.py diffs
        # against the commit that wrote it.
        changed = changed - {"tools/awinparse.py", "tools/tprime.py"}
        self.assertEqual(sorted(changed), [], "a frozen service-path file moved: %s" % sorted(changed))

    def test_the_probes_diff_adds_the_hook_and_no_device_operation(self):
        if not guards.base_available(BASE_COMMIT):
            self.skipTest("the base commit is not in this checkout")
        old = subprocess.run(["git", "-C", ROOT, "show", "%s:src/gbp/gbp_vstate_probe.c" % BASE_COMMIT],
                             capture_output=True, text=True, check=True).stdout
        added = [l.strip() for l in added_lines(old, read(PROBE_C)) if l.strip() and not l.strip().startswith(("*", "/*"))]
        # Issue #39 added the session-end read; Issue #59 adds the window hook. Nothing else.
        self.assertIn("if (cfg->awin) {", added)
        self.assertIn("gbp_awin_block(cfg->awin, buf, cfg->audio_len, n, res->audio.completed);", added)
        self.assertIn("gbp_awin_note_ticks(cfg->awin, (uint32_t)(q1 - q0));", added)
        # NO device operation was added by either issue
        for line in added:
            for op in ("gbp_avblock_read", "gbp_regwrite", "hsp_backend", "h_write", "h_read",
                       "gbp_irq_service_ack", "gbp_irq_service_deliver", "__UnmaskIrq", "__MaskIrq"):
                self.assertNotIn(op, line, "a device operation was added: %s" % line)

    def test_the_hook_runs_after_the_drain_and_its_commit(self):
        c = read(PROBE_C)
        drain = c.index("gbp_avblock_read(t, res->a.base, &res->audio, &res->a.errors);")
        commit = c.index("gbp_vstate_audio_commit(st, slot,")
        hook = c.index("if (cfg->awin) {")
        self.assertLess(drain, commit)
        self.assertLess(commit, hook)

    def test_the_config_field_is_appended_and_opaque(self):
        h = read(PROBE_H)
        self.assertIn("struct gbp_awin;", h)
        self.assertIn("struct gbp_awin *awin;", h)
        # appended AFTER session_end, so no earlier field moved
        self.assertLess(h.index("const int *session_end;"), h.index("struct gbp_awin *awin;"))
        # the header does not drag the window into every includer
        self.assertNotIn('#include "gbp_awin.h"', h)


class TheWindowIsThePreRegistrationsAndNotThisBuilds(unittest.TestCase):

    def test_the_constants_are_v8_3_2s(self):
        h = read(AWIN_H)
        self.assertEqual(num(define(h, "GBP_AWIN_BLOCKS")), 256)
        self.assertEqual(num(define(h, "GBP_AWIN_PRESS_WINDOWS")), 4)
        self.assertEqual(define(h, "GBP_AWIN_BLOCK_SIZE"), "0x1000u")
        self.assertEqual(define(h, "GBP_AWIN_WINDOWS"), "(1u")     # 1 + the press windows
        self.assertIn("(1u + GBP_AWIN_PRESS_WINDOWS)", h)
        # 5 x 256 x 4096
        self.assertEqual(5 * 256 * 0x1000, 5242880)

    def test_the_document_and_the_code_state_the_same_window(self):
        s = re.sub(r"\s+", " ", _bounded(read(HW), "\n## V8 — GBP-AUDIO-001"))
        self.assertIn("256 = 62.52 ms = 4.00 full periods", s)
        self.assertIn("total blocks 1 024", s)
        self.assertIn("total bytes 4 194 304 = 4.00 MB", s)
        # the press windows are the pre-registration's 4 x 256; the control is §V8.5.1's addition
        self.assertIn("the settled period before the first press", s)

    def test_the_store_is_asserted_at_compile_time_in_the_poc(self):
        a = read(AWIN_MAIN)
        self.assertIn("_Static_assert(sizeof awin_store == GBP_AWIN_STORE_BYTES", a)
        self.assertIn("_Static_assert(GBP_AWIN_BLOCKS == 256u && GBP_AWIN_PRESS_WINDOWS == 4u", a)
        self.assertIn("a build may not economise", a)
        self.assertIn("GBP_AWIN_BLOCK_SIZE == GBP_VSTATE_AUDIO_BLOCK_SIZE", a)

    def test_the_control_is_required_and_its_absence_is_not_hidden(self):
        h, c = read(AWIN_H), read(AWIN_C)
        self.assertIn("GBP_AWIN_CONTROL", h)
        # completion is the four PRESS windows; a missing control does not keep the run going
        body = c[c.index("int gbp_awin_complete("):]
        self.assertIn("for (i = 1u; i <= GBP_AWIN_PRESS_WINDOWS; i++)", body)


class TheBudgetIsStatedNotImprovised(unittest.TestCase):
    """Issue #59 item 3, and play-0001's own lesson (GBP-HW-282)."""

    def test_the_stores_outlast_the_safety_budget(self):
        a = read(AWIN_MAIN)
        safety = num(define(a, "PLAY_SAFETY_SECONDS"))
        frames = num(define(a, "PLAY_FRAME_RECORDS"))
        events = num(define(a, "PLAY_EVENT_RECORDS"))
        self.assertEqual(safety, 120)
        # the contract's minimum is honoured (a smaller set is refused at the first gate)
        vs = read(VSTATE_H)
        self.assertGreaterEqual(frames, num(define(vs, "GBP_VSTATE_MAX_FRAMES")))
        self.assertGreaterEqual(events, num(define(vs, "GBP_VSTATE_MAX_EVENTS")))
        # and BOTH outlast the budget at the frame rate: the bound that fires is the budget
        self.assertGreater(frames / 59.727, safety)
        self.assertGreater(events / 59.81, safety)
        # the compile-time versions of exactly those two claims
        self.assertIn("_Static_assert(PLAY_FRAME_RECORDS >= PLAY_SAFETY_SECONDS * 60u", a)
        self.assertIn("_Static_assert(PLAY_EVENT_RECORDS >= PLAY_SAFETY_SECONDS * 60u", a)

    def test_the_window_is_funded_from_named_stores_and_the_image_is_smaller(self):
        a, p = read(AWIN_MAIN), read(PLAY_MAIN)
        given_up = ((num(define(p, "PLAY_FRAME_RECORDS")) - num(define(a, "PLAY_FRAME_RECORDS"))) * 192
                    + (num(define(p, "PLAY_EVENT_RECORDS")) - num(define(a, "PLAY_EVENT_RECORDS"))) * 64)
        taken = 5 * 256 * 0x1000
        self.assertEqual(given_up, 6029312)
        self.assertEqual(taken, 5242880)
        self.assertGreater(given_up, taken)          # the image is SMALLER than play-0001
        self.assertIn("6 029 312 B given up, 5 242 880 B taken", a)
        self.assertIn("NOTHING WAS ECONOMISED ON THE WINDOW", a)
        # what it costs is named, not implied
        self.assertIn("WHAT THAT MAKES UNMEASURABLE HERE", a)

    def test_the_event_stores_rate_is_the_archives_and_not_play_0001s_assumption(self):
        a = read(AWIN_MAIN)
        self.assertIn("fills at the", a)
        self.assertIn("59.81/s", a)
        self.assertIn("would bound", a)


class TheAuditProfileDiscriminatesBothWays(unittest.TestCase):
    """Issue #59 item 6: run the auditor, do not count its rules."""

    def _run(self, out_dir, profile):
        listing = os.path.join(out_dir, "audit", "elf.nm.txt")
        if not os.path.exists(listing):
            self.skipTest("%s is not built in this checkout" % out_dir)
        r = subprocess.run([sys.executable, AUDIT, os.path.join(out_dir, "audit"), "--profile", profile],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_awin_passes_the_audio_image(self):
        rc, out = self._run(AWIN_OUT, "awin")
        self.assertEqual(rc, 0, out[:2000])
        self.assertIn("0 finding(s)", out)

    def test_awin_fails_the_play_image(self):
        rc, out = self._run(PLAY_OUT, "awin")
        self.assertNotEqual(rc, 0)
        self.assertIn("expected object missing: gbp_awin.o", out)

    def test_play_fails_the_audio_image(self):
        rc, out = self._run(AWIN_OUT, "play")
        self.assertNotEqual(rc, 0)

    def test_the_profile_is_derived_from_play_and_not_pasted(self):
        src = read(AUDIT)
        self.assertIn('def _awin_profile():', src)
        self.assertIn('copy.deepcopy(PROFILES["play"])', src)
        import poc_audit
        play, awin = poc_audit.PROFILES["play"], poc_audit.PROFILES["awin"]
        self.assertEqual(set(awin["required_objects"]) - set(play["required_objects"]),
                         {"gbp_awin.o", "gbp_awindump.o"})
        # the sink is reached from the service-path module and from nowhere else
        self.assertEqual(awin["symbol_callers"]["gbp_awin_block"], {"gbp_vstate_probe_run": 1})
        self.assertEqual(awin["symbol_callers"]["gbp_awin_arm_press"], {"pump": 1})


class ThePlumbing(unittest.TestCase):

    def test_the_poc_is_registered_everywhere_it_has_to_be(self):
        top = read(TOP_MAKEFILE)
        self.assertIn("gbp-audio-window-probe", define(top, "POCS") if False else top)
        self.assertIn("POC_AUDIT_RULE,$(AWIN_OUT),awin", top)
        self.assertIn("ISR_COMPARE_TARGET,awin-audit,$(AWIN_OUT)", top)
        self.assertIn("awin-dolphin:", top)
        self.assertIn("awin-audit awin-dolphin", top)
        unit = read(UNIT_MAKEFILE)
        self.assertIn("test_gbp_awin test_gbp_awindump", unit)
        self.assertIn("$(OUTDIR)/test_gbp_awin:", unit)
        self.assertIn("$(OUTDIR)/test_gbp_awindump:", unit)

    def test_the_build_id_and_the_test_id_are_v8s(self):
        mk, a = read(AWIN_MAKEFILE), read(AWIN_MAIN)
        self.assertEqual(define(mk, "") if False else re.search(r"^BUILD_ID\s+:=\s+(\S+)", mk, re.M).group(1),
                         "stream-0016")
        self.assertEqual(re.search(r"^APP_NAME\s+:=\s+(\S+)", mk, re.M).group(1), "gbp-audio-window-probe")
        self.assertIn('#define TEST_ID "GBP-AUDIO-001"', a)
        self.assertIn("gbp_awin.c gbp_awindump.c", mk)

    def test_the_slot_is_14_and_the_frozen_slots_are_not_touched(self):
        """Hardware Issue #61 authorised the staging of a NEW slot. 12-stream
        and 13-play keep their FROZEN hashes -- #44's refusal is what makes
        adding a slot beside them safe -- and 14-audio is frozen from the
        start, because it is staged FOR a run that has not happened yet."""
        rows = {}
        for line in read(os.path.join(ROOT, "tools", "swiss-layout.tsv")).splitlines():
            if line.startswith("#") or not line.strip():
                continue
            f = line.split("\t")
            rows[f[0]] = f
        self.assertEqual(rows["12"][1], "stream")
        self.assertEqual(rows["13"][1], "play")
        self.assertEqual(rows["12"][-1], "dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49")
        self.assertEqual(rows["13"][-1], "d0ee3c29d04254d1b86d4f006291008876b5e886e07280d0421b7c1161c499de")
        self.assertEqual(rows["14"][1], "audio")
        self.assertEqual(rows["14"][2], "gbp-audio-window-probe")
        self.assertEqual(rows["14"][3], "gbp-audio-window-probe.dol")
        self.assertEqual(rows["14"][6], "1")
        self.assertEqual(rows["14"][-1], AWIN_DOL_SHA256)
        # and it is a NEW number: nothing was renumbered
        self.assertNotIn("15", rows)

    def test_what_is_staged_is_the_image_this_checkpoint_built(self):
        """The slot's bytes, when it is staged in this checkout. The DOL's own
        hash is the authority; the manifest row repeats it and must agree."""
        import hashlib
        staged = os.path.join(ROOT, "build", "swiss", "14-audio", "boot.dol")
        if not os.path.exists(staged):
            self.skipTest("14-audio is not staged in this checkout")
        with open(staged, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), AWIN_DOL_SHA256)

    def test_the_dolphin_target_states_its_ceiling(self):
        top = read(TOP_MAKEFILE)
        block = top[top.index("# GBP-AUDIO-001 (Issue #59) in Dolphin"):top.index("awin-dolphin:")]
        self.assertIn("no window is armed", block)
        self.assertIn("AUXILIARY, never physical evidence", block)


class TheIdentityIsInTheRunsOwnRecord(unittest.TestCase):
    """Hardware Issue #61: §V8.12, a NEW dated part appended to the frozen
    pre-registration. The test that matters is not that §V8.12 exists -- it is
    that §V8.1 through §V8.11 did NOT MOVE to make room for it."""

    def _v8(self, text):
        return _bounded(text, "\n## V8 — GBP-AUDIO-001")

    def test_the_frozen_parts_are_byte_identical_to_the_pre_registration(self):
        """§V8.1 – §V8.11 as Issue #58 committed them, character for character."""
        base = subprocess.run(["git", "-C", ROOT, "log", "--format=%H", "-1", "--grep",
                               "Issue #58 -- Phase 6's first physical run pre-registered"],
                              capture_output=True, text=True).stdout.strip()
        if not base:
            self.skipTest("the pre-registration's commit is not in this checkout")
        old = subprocess.run(["git", "-C", ROOT, "show", "%s:docs/research/HARDWARE_TESTS.md" % base],
                             capture_output=True, text=True, check=True).stdout
        now, then = self._v8(read(HW)), self._v8(old)
        # "Frozen text keeps its words" is not "the section is byte-identical": §V8.10
        # gained a dated CORRECTION on top (§V8.10.1, Issue #62) and §V8.12 / §V8.13
        # were appended. What must hold is that every PARAGRAPH the pre-registration
        # wrote is still present verbatim AND IN ORDER -- insertions are allowed and
        # are exactly what a dated amendment is; a deletion or a reword is not.
        frozen = [para for para in then[then.index("### V8.1 "):].split("\n\n") if para.strip()]
        cur = now
        at = 0
        for para in frozen:
            j = cur.find(para, at)
            self.assertNotEqual(j, -1, "a paragraph of the pre-registration was changed or removed:\n%s"
                                % para[:200])
            at = j + len(para)

    def test_the_new_part_carries_the_identity_and_the_staging(self):
        s = re.sub(r"\s+", " ", read(HW)[read(HW).index("### V8.12 "):])
        for wanted in ("stream-0016", "04121fe", AWIN_DOL_SHA256, "498 496 B",
                       "14-audio", "READ BACK FROM THE CARD",
                       "dd545c01...3a49", "d0ee3c29...99de",
                       "53c212c7...2b6e", "DO NOT RUN"):
            self.assertIn(wanted, s, wanted)
        # and it still answers nothing
        self.assertIn("RUN 30 has not happened", s)
        self.assertIn("must not be adjusted to", s)
        self.assertIn("the files do not exist", s)

    def test_the_heading_gained_a_pointer_and_kept_its_words(self):
        head = [l for l in read(HW).splitlines() if l.startswith("## V8 — GBP-AUDIO-001")][0]
        self.assertIn("PRE-REGISTERED 2026-09-22 (GitHub Issue #58); NOT RUN, NOT AUTHORISED HERE", head)
        self.assertIn("THE IMAGE IS BUILT AND STAGED", head)
        self.assertIn("RUN 30 IS STILL NOT RUN", head)

    def test_the_devlog_points_at_it_instead_of_holding_it(self):
        d = read(os.path.join(ROOT, "docs", "research", "DEVLOG.md"))
        self.assertIn("recorded in `HARDWARE_TESTS.md` §V8.12", d)


class TheIdentityWhenBuilt(unittest.TestCase):

    def test_build_info_and_the_dol_agree(self):
        info = os.path.join(AWIN_OUT, "build-info.txt")
        if not os.path.exists(info):
            self.skipTest("the audio image is not built in this checkout")
        text = read(info)
        self.assertIn("build_id=stream-0016", text)
        self.assertIn("app=gbp-audio-window-probe", text)
        m = re.search(r"^sha256_dol=([0-9a-f]{64})$", text, re.M)
        self.assertTrue(m, "build-info carries no DOL hash")
        dol = os.path.join(AWIN_OUT, "gbp-audio-window-probe.dol")
        if os.path.exists(dol):
            import hashlib
            with open(dol, "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), m.group(1))


class NothingHereIsPhysicalEvidence(unittest.TestCase):

    def test_the_image_claims_no_run_and_no_authorisation(self):
        a = read(AWIN_MAIN)
        self.assertIn("it has never touched hardware", a)
        self.assertIn("NOT authorised here", a)
        mk = read(AWIN_MAKEFILE)
        self.assertIn("NOT PHYSICALLY EXECUTED", mk)
        self.assertIn("not staged", mk)

    def test_the_image_still_claims_no_result_of_its_own(self):
        """EXPIRED AND MOVED 2026-09-22 (Issue #62): this case asserted that RUN 30
        had not happened, and it has. What replaces it is the property that
        survived the run -- the IMAGE's own sources still claim nothing about
        what the window carries. The run's verdicts live in §V8.13, not here."""
        a = read(AWIN_MAIN)
        for forbidden in ("CARRIES", "the window carries the AGB", "PREDICTED SHAPE", "U-GBP-012 closed"):
            self.assertNotIn(forbidden, a, forbidden)
        self.assertIn("nothing here claims that the AUDIO window carries anything", a)


if __name__ == "__main__":
    unittest.main()
