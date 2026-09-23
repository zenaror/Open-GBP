"""
tests/host/test_input_impl.py — the input path implemented (GitHub Issue #19,
2026-09-21): the structural guarantees the checkpoint promised, pinned.

  * the KEYPAD bit assignment is DEFINED in exactly one place (src/gbp/gbp_input.c),
    its initializer's digit sequence appears nowhere else in src/, poc/, tests/ or
    tools/, and the definition's comment carries CORROBORATED / NOT FACT, the ids
    GBP-KEY-004 and U-GBP-010, and the falsifier;
  * no test anywhere names the bit of L or R: this file and the C unit test only
    consume the descriptor as data;
  * the refresh period is one named constant, 5 ms, with its rationale;
  * the pump-slot insertion is the first statement of pump(), reads the clock only
    through the transport (no gettime()/gettick() in input_step), and the service
    path / the frozen writers do not reference the input module;
  * nothing emits t_poll / t_write;
  * the build wiring (BUILD_ID stream-0014, since Issue #27 stream-0015, gbp_input.c in the POC, the unit test);
  * the documents keep the status: no "order is established" (REGISTERS.md kept H
    until Issue #26 promoted the order to C, never FACT);
    after Issue #24 (RUN 14 / RUN 15 ingested, §V7.2) U-GBP-010 is CLOSED and the
    highest GBP-HW id is 265.
"""
import os
import re
import subprocess
import unittest

import guards

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "src", "gbp")
INPUT_C = os.path.join(SRC, "gbp_input.c")
INPUT_H = os.path.join(SRC, "gbp_input.h")
MAIN = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c")
STREAM_MAKE = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "Makefile")
UNIT_MAKE = os.path.join(ROOT, "tests", "unit", "Makefile")
UNIT_TEST = os.path.join(ROOT, "tests", "unit", "test_gbp_input.c")
DOCS = os.path.join(ROOT, "docs")
BASE_COMMIT = "a877284bdda42ee77bbb52743eefd619c738574c"   # origin/main at the start of Issue #19
DEF_RE = re.compile(r"^const struct gbp_keypad_descriptor GBP_KEYPAD_DESCRIPTOR\s*=\s*\{\s*\{([^}]*)\}\s*,\s*(\d)\s*\}\s*;", re.M)
SERVICE_PATH_FILES = ("gbp_vstate_probe.c", "gbp_vstate.c", "gbp_vqueue.c", "gbp_vwitness.c", "gbp_vpresent.c",
                      "gbp_vdisp.c", "gbp_vfull.c", "gbp_vvi.c", "gbp_irq_service.c", "gbp_vsig.c",
                      "gbp_vidxdump.c", "gbp_vdispdump.c", "gbp_vfulldump.c", "gbp_vvidump.c", "gbp_vstatedump.c")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def strip_comments(code):
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return re.sub(r"//[^\n]*", "", code)


def source_files(*dirs):
    for d in dirs:
        for dirpath, _, files in os.walk(os.path.join(ROOT, d)):
            for fn in files:
                if fn.endswith((".c", ".h", ".py", ".md", ".txt")):
                    yield os.path.join(dirpath, fn)


def descriptor_sequence():
    m = DEF_RE.search(read(INPUT_C))
    assert m is not None
    digits = re.sub(r"/\*.*?\*/", "", m.group(1))
    return ",".join(x.strip() for x in digits.split(",") if x.strip()), m


class TheAssignmentLivesInOnePlace(unittest.TestCase):
    def test_defined_exactly_once_in_the_repository(self):
        hits = []
        for p in source_files("src", "poc", "tests", "tools"):
            if p.endswith((".c", ".h")) and DEF_RE.search(read(p)):
                hits.append(os.path.relpath(p, ROOT))
        self.assertEqual(hits, ["src/gbp/gbp_input.c"])

    def test_the_initializer_sequence_appears_nowhere_else(self):
        seq, _ = descriptor_sequence()
        self.assertEqual(len(seq.split(",")), 10)
        for p in source_files("src", "poc", "tests", "tools"):
            if os.path.abspath(p) == INPUT_C:
                continue
            body = read(p).replace(" ", "").replace("\n", "")
            self.assertNotIn(seq, body, os.path.relpath(p, ROOT))

    def test_the_definition_carries_its_status_and_its_falsifier(self):
        t = read(INPUT_C)
        _, m = descriptor_sequence()
        before = t[:m.start()]
        block = before[before.rfind("/*"):]
        for phrase in ("CORROBORATED", "NOT FACT", "GBP-KEY-004", "U-GBP-010", "OPEN", "FALSIFIES", "ONE line", "Issue #19"):
            self.assertIn(phrase, block, phrase)
        self.assertNotIn("established", block.lower())

    def test_no_test_names_the_bit_of_l_or_r(self):
        """A test that could only pass under the chosen order would be the stop
        condition Issue #19 names. The unit test asserts validity, the identity and
        bit-for-bit application under synthetic descriptors; it never compares
        bit[GBP_GBA_L] or bit[GBP_GBA_R] with a number, and this file does not either."""
        for p in (UNIT_TEST, __file__):
            code = strip_comments(read(p))
            self.assertIsNone(re.search(r"bit\s*\[\s*GBP_GBA_[LR]\s*\]\s*==\s*\d", code), p)
            self.assertIsNone(re.search(r"GBP_KEYPAD_DESCRIPTOR\.bit\s*\[\s*[89]\s*\]", code), p)
        unit = strip_comments(read(UNIT_TEST))
        self.assertIn("D_REVERSED", unit)
        self.assertIn("D_SCRAMBLED", unit)
        self.assertIn("D_ACTIVE_LOW", unit)

    def test_the_selftest_is_pure_and_names_no_bit(self):
        code = strip_comments(read(INPUT_C))
        body = code[code.index("int gbp_input_selftest(void)"):]
        self.assertIsNone(re.search(r"bit\s*\[\s*GBP_GBA_[LR]\s*\]", body))
        self.assertNotIn("write_block", body)


class TheRefreshPolicyIsOneNamedConstant(unittest.TestCase):
    def test_single_definition_with_the_rationale(self):
        h = read(INPUT_H)
        self.assertEqual(len(re.findall(r"^#define GBP_INPUT_REFRESH_MS 5u$", h, re.M)), 1)
        block = h[:h.index("#define GBP_INPUT_REFRESH_MS 5u")]
        block = block[block.rfind("/*"):]
        for phrase in ("Start-up Disc", "5.000 ms", "NEITHER reference proves", "CLAUDE.md §18", "physical run"):
            self.assertIn(phrase, block, phrase)
        for p in source_files("src", "poc", "tests"):
            if os.path.abspath(p) != INPUT_H and p.endswith((".c", ".h")):
                self.assertNotIn("#define GBP_INPUT_REFRESH_MS", read(p), p)


class ThePumpSlotInsertion(unittest.TestCase):
    def test_the_step_is_the_first_statement_of_pump(self):
        code = strip_comments(read(MAIN))
        i = code.index("static void pump(void *user)\n{")
        body = code[i:]
        first = re.search(r"\{\s*uint32_t t0, t1, row, n;\s*\(void\)user;\s*([a-z_]+\(\);)", body)
        self.assertIsNotNone(first)
        self.assertEqual(first.group(1), "input_step();")
        self.assertEqual(code.count("input_step();"), 1)

    def test_the_step_reads_the_clock_through_the_transport_only(self):
        code = strip_comments(read(MAIN))
        i = code.index("static void input_step(void)")
        j = code.index("static void pump(void *user)", i)
        body = code[i:j]
        self.assertNotIn("gettime(", body)
        self.assertNotIn("gettick(", body)
        self.assertIn("PAD_ScanPads()", body)
        self.assertIn("t->ticks64(t->ctx)", body)
        self.assertIn("gbp_input_step(&in_state, t, &s, t_poll)", body)
        # the pins the stream audit keeps: the gettime sites of pump() are unchanged in number
        pump = code[j:code.index("static void submit_ready(int buf, struct gbp_vqueue *account)\n{", j)]
        self.assertEqual(pump.count("gettime("), 5)

    def test_the_transport_is_armed_before_the_run_and_disarmed_after(self):
        code = strip_comments(read(MAIN))
        arm = code.index("in_transport = &t;")
        run = code.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);")
        disarm = code.index("in_transport = 0;")
        self.assertLess(arm, run)
        self.assertLess(run, disarm)
        self.assertLess(code.index("vq.pump = 0;"), disarm)

    def test_the_service_path_and_the_frozen_writers_do_not_reference_the_input(self):
        for fn in SERVICE_PATH_FILES:
            body = read(os.path.join(SRC, fn))
            self.assertNotIn("gbp_input", body, fn)
            self.assertNotIn("PAD_", body, fn)
            self.assertNotIn("KEYPAD_DESCRIPTOR", body, fn)

    def test_the_service_path_and_the_frozen_writers_are_byte_identical_to_the_base(self):
        if not guards.base_available(BASE_COMMIT):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE_COMMIT)
        paths = ["src/gbp/" + f for f in SERVICE_PATH_FILES] + ["src/gbp/gbp_vstate_probe.h", "src/gbp/gbp_vqueue.h",
                 "src/gbp/gbp_transport.c", "src/gbp/gbp_transport.h", "src/gbp/gbp_regwrite.c",
                 "src/platform/hsp_backend.c", "src/platform/hsp_backend_irq.c", "tools"]   # docs/protocol and docs/hardware left this list with the Issue #26 promotion
        changed = guards.changed_since(BASE_COMMIT, paths)   # Issue #29: tracked AND untracked, one implementation
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
        # Issue #62 (2026-09-22) ingested RUN 30 and needed two READERS that did not exist: awinparse.py,
        # a strict parser for the OGBPAW1 sidecar, and tprime.py, §V7.9's decision rule. Both only read and
        # report; the VERDICT constructions stay in tools/v8audio.py, which tests/host/test_run30.py diffs
        # against the commit that wrote it.
        changed = changed - {"tools/awinparse.py", "tools/tprime.py"}
        # Issue #50 (2026-09-22) made §V7.6.11's frozen verdicts executable BEFORE RUN 21 / RUN 22's logs
        # existed: tools/v7611.py recomputes them and is exercised on SYNTHETIC vectors only, so the
        # ingestion cannot tune the constructions to the data. It reads no run and changes nothing.
        changed = changed - {"tools/v7611.py"}
        # Issue #58 (2026-09-22) pre-registered Phase 6's first physical run (§V8, GBP-AUDIO-001) and made its
        # three-model predictions executable BEFORE any build or log existed: tools/v8audio.py is exercised on
        # SYNTHETIC vectors only, reads no run, authorises nothing and promotes nothing.
        changed = changed - {"tools/v8audio.py"}
        # Issue #39 (2026-09-21) added the operator's session end to the service-path module -- one flag read in
        # CHECK_ADMISSION, a stop reason, a status, a config field; no device operation added, removed or reordered
        # (tests/host/test_play_image.py pins the change) -- and the `play` audit profile and the Swiss slot to tools/
        # Issue #29 (2026-09-21) added the promotion sweep tool under tools/; it reads the pages and judges nothing
        self.assertTrue(changed <= {"src/gbp/gbp_vstate_probe.c", "src/gbp/gbp_vstate_probe.h", "tools/poc_audit.py",
                                    "tools/swiss-layout.tsv", "tools/reconcile.py",
                                    # Issue #44 (2026-09-22): the staging tool's frozen-slot refusal
                                    "tools/swiss_export.py"},
                        "changed against the base: " + " ".join(sorted(changed)))


class NothingEmitsTheHeadInstants(unittest.TestCase):
    def test_the_head_instants_are_emitted_only_through_the_key_line(self):
        """Issue #19 emitted no head instant anywhere. Issue #27 (GBP-KEY-009) spends
        INPUT_PATH.md §8's guarantee: t_poll and t_done are carried ONLY by the one
        KEY format of gbp_input.h (a ringlog line from the pump slot), never by a
        sidecar or a frozen format; the module formats nothing but that render."""
        h = read(INPUT_H)
        fmt = re.search(r'#define GBP_INPUT_EVENT_FMT "((?:[^"\\]|\\.)*)"', h).group(1)
        self.assertIn("t_poll=%llx", fmt)
        self.assertIn("t_done=%llx", fmt)
        for p in (MAIN, INPUT_C):
            for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', read(p)):
                s = m.group(1)
                self.assertNotIn("t_poll", s, (p, s))
                self.assertNotIn("t_write", s, (p, s))
        c = read(INPUT_C)
        self.assertEqual(c.count("printf"), 1, "the module's only formatting is gbp_input_event_render()")
        self.assertIn("return snprintf(dst, cap, GBP_INPUT_EVENT_FMT, GBP_INPUT_EVENT_ARGS(e));", c)
        for fn in ("gbp_vidxdump.c", "gbp_vdispdump.c", "gbp_vfulldump.c", "gbp_vvidump.c", "gbp_vwitness.c", "gbp_vdisp.c", "gbp_vfull.c", "gbp_vvi.c"):
            self.assertNotIn("t_poll", read(os.path.join(SRC, fn)), fn)

    def test_the_head_instants_are_fields(self):
        h = read(INPUT_H)
        self.assertIn("uint64_t t_poll;", h)
        self.assertIn("uint64_t t_write;", h)


class TheBuildWiring(unittest.TestCase):
    def test_build_id_and_sources(self):
        m = read(STREAM_MAKE)
        self.assertIsNotNone(re.search(r"^BUILD_ID\s*:=\s*stream-0015$", m, re.M))   # Issue #27: the per-change record and the ENVINPUT repair
        self.assertIn("stream-0014 is stream-0013 plus the INPUT PATH", m)
        self.assertIn("NOT PHYSICALLY EXECUTED", m)
        srcs = re.search(r"^SRCS := (.*)$", m, re.M).group(1).split()
        self.assertIn("gbp_input.c", srcs)
        self.assertIn("gbp_regwrite.c", srcs)
        u = read(UNIT_MAKE)
        self.assertIn(" test_gbp_input", u)
        self.assertIn("$(OUTDIR)/test_gbp_input: test_gbp_input.c $(ROOT)/src/gbp/gbp_input.c", u)

    def test_the_poc_pins_libogc2s_bits_at_compile_time(self):
        code = read(MAIN)
        self.assertIn("GBP_PAD_BUTTON_L == PAD_BUTTON_L", code)
        self.assertIn("GBP_PAD_BUTTON_R == PAD_BUTTON_R", code)
        self.assertIn("GBP_PAD_ERR_NONE == PAD_ERR_NONE", code)


class TheDocumentsKeepTheStatus(unittest.TestCase):
    def test_registers_h_unknown_open_no_promotion(self):
        regs = read(os.path.join(DOCS, "protocol", "REGISTERS.md"))
        self.assertNotIn("H (L/R bit order)", regs)          # Issue #26: C; Issue #33: F (hw, run-scoped) by RUN 17 / RUN 18, history kept
        self.assertIn("C — was H until 2026-09-21", regs)
        self.assertIn("L/R bit order: F (hw, run-scoped) since 2026-09-21", regs)
        unk = read(os.path.join(DOCS, "research", "UNKNOWNS.md"))
        m = re.search(r"^## U-GBP-010\b.*$", unk, re.M)
        self.assertIsNotNone(m)
        self.assertIn("CLOSED 2026-09-21", m.group(0))   # Issue #24: closed AS-ASSIGNED with the descriptor kept
        self.assertIn("CORROBORATED, not FACT", m.group(0))
        for fn in ("research/INPUT_PATH.md", "research/EVIDENCE.md", "HANDOFF.md", "ROADMAP.md", "research/DEVLOG.md"):
            for line in read(os.path.join(DOCS, fn)).splitlines():
                low = line.lower()
                if "order is established" in low or "order is now fact" in low or "order is fact" in low:
                    # allowed only as the thing NOT to assume (a do-not-assume bullet) or as a negation
                    self.assertTrue(line.lstrip().startswith("- **That") or "no document says" in low
                                    or "not established" in low, fn + ": " + line)
        ev = read(os.path.join(DOCS, "research", "EVIDENCE.md"))
        hw = max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M))
        self.assertEqual(hw, 302)   # GBP-HW-261…265 (Issue #24); 266…271 (Issue #33)   # 272: Issue #46 (the CONTROL bit 0x02 split, FACT for the split / HYPOTHESIS for the cause); 273…277: Issue #47 (RUN 23 / RUN 24, §V7.7); 278…284: Issue #52 (RUN 21 / 22 / 25 / 26, §V7.8)   # 285…294: Issue #62 (RUN 30 ingested, §V8.13)   # 295…300: Issue #67 (RUN 31 ingested, §V9.15); 301…302: #67's validation (the rate/layout split, U-GBP-039's probe)


if __name__ == "__main__":
    unittest.main()
