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
  * the build wiring (BUILD_ID stream-0014, gbp_input.c in the POC, the unit test);
  * the documents keep the status: no "order is established" (REGISTERS.md kept H
    until Issue #26 promoted the order to C, never FACT);
    after Issue #24 (RUN 14 / RUN 15 ingested, §V7.2) U-GBP-010 is CLOSED and the
    highest GBP-HW id is 265.
"""
import os
import re
import subprocess
import unittest

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
        r = subprocess.run(["git", "-C", ROOT, "cat-file", "-e", BASE_COMMIT], capture_output=True)
        if r.returncode != 0:
            self.skipTest("the base commit is not available in this checkout")
        paths = ["src/gbp/" + f for f in SERVICE_PATH_FILES] + ["src/gbp/gbp_vstate_probe.h", "src/gbp/gbp_vqueue.h",
                 "src/gbp/gbp_transport.c", "src/gbp/gbp_transport.h", "src/gbp/gbp_regwrite.c",
                 "src/platform/hsp_backend.c", "src/platform/hsp_backend_irq.c", "tools"]   # docs/protocol and docs/hardware left this list with the Issue #26 promotion
        r = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", BASE_COMMIT, "--"] + paths,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "", "changed against the base: " + r.stdout)


class NothingEmitsTheHeadInstants(unittest.TestCase):
    def test_no_format_string_carries_t_poll_or_t_write(self):
        for p in (MAIN, INPUT_C):
            for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', read(p)):
                s = m.group(1)
                self.assertNotIn("t_poll", s, p)
                self.assertNotIn("t_write", s, p)
        c = strip_comments(read(INPUT_C))
        for bad in ("printf", "ringlog", "sdlog", "fopen"):
            self.assertNotIn(bad, c, bad)

    def test_the_head_instants_are_fields(self):
        h = read(INPUT_H)
        self.assertIn("uint64_t t_poll;", h)
        self.assertIn("uint64_t t_write;", h)


class TheBuildWiring(unittest.TestCase):
    def test_build_id_and_sources(self):
        m = read(STREAM_MAKE)
        self.assertIsNotNone(re.search(r"^BUILD_ID\s*:=\s*stream-0014$", m, re.M))
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
        self.assertNotIn("H (L/R bit order)", regs)          # Issue #26: C, never FACT
        self.assertIn("L/R bit order: C", regs)
        self.assertIn("not FACT", regs)
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
        self.assertEqual(hw, 265)   # GBP-HW-261…265 (Issue #24)


if __name__ == "__main__":
    unittest.main()
