"""
tests/host/test_split_image.py — GitHub Issue #105: RUN B's image (poc/gbp-audio-split, GBP-AUDIO-009,
split-0001), pinned to trace-0001, to §V24 and to the report its frozen gates read.

ONE VARIABLE, INTERLEAVED, SHOWN BY DIFFING (§V24.1). trace-0001 (poc/gbp-audio-trace, RUN 39's image) is
this image's base. Every line trace-0001 has is here unchanged but its identity and the ONE production-step
record, which is replaced by its tagged form; every line added is the new header or sits in a hunk that
begins with a SPLIT marker; every function the variable did not need is trace-0001's character for character.
On the drain path a SPLIT line reads the chain's state and calls the tagger and the recorder, nothing else.

THE ASSIGNMENT IS ONE SEQUENCE ON BOTH SIDES. The image's C (src/audio/gbp_asplit.c) is compiled on the host
and must give tools/v24accept.py's arms, chunk for chunk.

THE LOG AND THE TRACE ARE THE INTERFACE. A synthetic Run B session -- arms, tags, losses, callbacks, and
short steps only the floorless sample keeps -- goes through the recorder's own C in version 2, through the
report builder and through the FROZEN gates, and must come back with the same ticks, the same tags, the
sample where §V24.4 puts it, and the same QUESTION S verdict and counts as the session read directly.

THE AUDIT IS EXERCISED, NOT COUNTED: `split` passes this image and fails trace-0001's; `trace` fails this one.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(__file__))

import hostcc  # noqa: E402
import test_trace_image as tt  # noqa: E402

SPLIT_MAIN = os.path.join(ROOT, "poc", "gbp-audio-split", "source", "main.c")
SPLIT_MAKEFILE = os.path.join(ROOT, "poc", "gbp-audio-split", "Makefile")
TRACE_MAIN = os.path.join(ROOT, "poc", "gbp-audio-trace", "source", "main.c")
TRACE_MAKEFILE = os.path.join(ROOT, "poc", "gbp-audio-trace", "Makefile")
ASPLIT_C = os.path.join(ROOT, "src", "audio", "gbp_asplit.c")
ATRACE_C = os.path.join(ROOT, "src", "audio", "gbp_atrace.c")
AUDIT = os.path.join(ROOT, "tools", "poc_audit.py")
SPLIT_OUT = os.path.join(ROOT, "build", "poc", "gbp-audio-split")
TRACE_OUT = os.path.join(ROOT, "build", "poc", "gbp-audio-trace")
TB = 40500000

# trace-0001's lines this image changes, and what replaces each
CHANGED = {
    '#define OPENGBP_APP_NAME "gbp-audio-trace"': ['#define OPENGBP_APP_NAME "gbp-audio-split"'],
    '#define TEST_ID "GBP-AUDIO-008"': ['#define TEST_ID "GBP-AUDIO-009"'],
    '    printf("\\n  Open-GBP " TEST_ID "  RUN A, READ-ONLY TIMING (HARDWARE_TESTS V23; NOT PHYSICALLY VALIDATED)\\n");':
        ['    printf("\\n  Open-GBP " TEST_ID "  RUN B, SPLIT PRODUCTION (HARDWARE_TESTS V24; NOT PHYSICALLY VALIDATED)\\n");'],
    '        tr_st = gbp_atrace_step(&tr, GBP_ATRACE_PRODUCE, tr_s0, tr_s1);':
        ['        tr_st = gbp_atrace_step_tagged(&tr, GBP_ATRACE_PRODUCE, tr_s0, tr_s1,         /* SPLIT 2 */',
         '                                       split_tag(sp_cur0, sp_prod0, sp_push0));'],
}
SPLIT_WRITES = {"sp_cur0", "sp_prod0", "sp_push0", "tr_st", "ap.step_pushes", "ap.step_pushes_user", "tr.s.sample",
                "tr.sample_every", "worked"}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class TheImageIsTrace0001PlusTheVariable(unittest.TestCase):

    def test_trace_0001_loses_nothing_but_its_identity_and_the_one_record(self):
        for removed, added, _j in tt.hunks(read(TRACE_MAIN), read(SPLIT_MAIN)):
            if removed:
                self.assertEqual(len(removed), 1, removed)
                self.assertIn(removed[0], CHANGED)
                self.assertEqual(added, CHANGED[removed[0]])
        removed = [l for r, _a, _j in tt.hunks(read(TRACE_MAIN), read(SPLIT_MAIN)) for l in r]
        self.assertEqual(sorted(removed), sorted(CHANGED))

    def test_every_addition_is_the_header_or_a_split_block(self):
        for removed, added, j in tt.hunks(read(TRACE_MAIN), read(SPLIT_MAIN)):
            if removed:
                continue
            if j <= 1:
                self.assertTrue(all(l.startswith((" *", "/*")) for l in added), added[:3])
                self.assertIn("GBP-AUDIO-009, build split-0001", "\n".join(added[:3]))
                continue
            first = next(l for l in added if l.strip() not in ("", "{", "}"))
            self.assertIn("SPLIT", first, "an added hunk at line %d is not marked SPLIT: %r" % (j + 1, first))

    def test_the_untouched_functions_are_trace_0001s_character_for_character(self):
        trace, split = tt.functions(read(TRACE_MAIN)), tt.functions(read(SPLIT_MAIN))
        self.assertGreaterEqual(len(trace), 20)
        for name, text in trace.items():
            if name not in ("live_step", "main"):
                self.assertEqual(split.get(name), text, name)
        self.assertEqual(set(split) - set(trace), {"split_tag"})

    def test_a_split_hunk_writes_only_its_own_locals_the_hook_and_the_sample(self):
        targets = set()
        for removed, added, j in tt.hunks(read(TRACE_MAIN), read(SPLIT_MAIN)):
            if j <= 1:
                continue
            code = re.sub(r"/\*.*?\*/", "", "\n".join(added), flags=re.S)
            code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
            code = re.sub(r"^static [^;\n(]*;$", "", code, flags=re.M)     # one-line file-scope storage declarations
            targets |= set(re.findall(r"(\w+(?:(?:->|\.)\w+)*)\s*(?:\[[^\]]*\])?\s*(?:[-+*/%&|^]|<<|>>)?=(?!=)", code))
        self.assertEqual(targets, SPLIT_WRITES, sorted(targets ^ SPLIT_WRITES))

    def test_on_the_drain_path_split_calls_only_the_tagger_and_the_recorder(self):
        step = tt.functions(read(SPLIT_MAIN))["live_step"]
        lines = [l for l in step.splitlines() if "SPLIT" in l]
        body = "\n".join(lines) + "\n" + step[step.index("gbp_atrace_step_tagged("):].split(";", 1)[0]
        code = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
        calls = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", code)) - {"if", "sizeof"}
        self.assertEqual(calls, {"gbp_atrace_step_tagged", "split_tag"})
        tag = tt.functions(read(SPLIT_MAIN))["split_tag"]
        self.assertEqual(set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", tag.split("{", 1)[1])) - {"if", "return"}, set())

    def test_the_sources_are_trace_0001s_and_the_assignment(self):
        self.assertEqual(set(tt.srcs(SPLIT_MAKEFILE)) - set(tt.srcs(TRACE_MAKEFILE)), {"gbp_asplit.c"})
        self.assertEqual(set(tt.srcs(TRACE_MAKEFILE)) - set(tt.srcs(SPLIT_MAKEFILE)), set())
        mk = read(SPLIT_MAKEFILE)
        self.assertRegex(mk, r"(?m)^APP_NAME\s*:=\s*gbp-audio-split$")
        self.assertRegex(mk, r"(?m)^BUILD_ID\s*:=\s*split-0001$")

    def test_the_hook_and_the_sample_are_installed_once_in_main(self):
        m = tt.functions(read(SPLIT_MAIN))["main"]
        for tok in ("gbp_asplit_init(&asplit);", "ap.step_pushes = gbp_asplit_step_pushes;",
                    "ap.step_pushes_user = &asplit;", "tr.s.sample = tr_sample;", "tr.sample_every = 8u;"):
            self.assertEqual(m.count(tok), 1, tok)
        self.assertLess(m.index("gbp_aplay_init(&ap"), m.index("ap.step_pushes = gbp_asplit_step_pushes;"))
        self.assertLess(m.index("gbp_atrace_init(&tr"), m.index("tr.s.sample = tr_sample;"))

    def test_every_record_fits_the_ringlog_line_at_its_worst(self):
        m = read(SPLIT_MAIN)
        tags = sorted(set(re.findall(r'"(LIVE[A-Z0-9]*) ', m)))
        self.assertIn("LIVESPLIT", tags)
        status = int(re.search(r"char tr_status\[(\d+)\]", m).group(1))
        per_line = ",".join(["4294967295"] * 16)
        for tag in tags:
            for fmt in tt.c_formats(m, tag):
                strings = {"LIVESEC": [per_line], "LIVEFILL": [per_line], "LIVEL2SAVE": ["x" * 159],
                           "LIVETRACESAVE": ["x" * (status - 1)], "LIVE": ["calibrate"]}.get(tag, [])
                line = tt.worst_case(fmt, strings)
                self.assertLessEqual(len(line), tt.RINGLOG_CONTENT_MAX, "%s renders %d characters" % (tag, len(line)))


# ---- the assignment, the recorder in version 2, the builder and the frozen gates ----------------

ARMS_DRIVER = r"""
#include <stdio.h>
#include "gbp_asplit.h"
int main(void)
{
    struct gbp_asplit s;
    unsigned i;
    gbp_asplit_init(&s);
    for (i = 0; i < 4000u; i++) putchar('0' + gbp_asplit_arm(&s, i));
    return 0;
}
"""

TRACE_DRIVER = r"""
#include <stdio.h>
#include <stdlib.h>
#include "gbp_atrace.h"
static int16_t a_dec[GBP_ATRACE_A_MAX];
static uint16_t a_del[GBP_ATRACE_A_MAX];
static struct gbp_atrace_sat a_sat[GBP_ATRACE_A_SAT_MAX];
static uint16_t v_rec[GBP_ATRACE_V_MAX];
static struct gbp_atrace_sat v_sat[GBP_ATRACE_V_SAT_MAX];
static struct gbp_atrace_cb cbs[GBP_ATRACE_CB_MAX];
static struct gbp_atrace_step steps[GBP_ATRACE_STEP_MAX];
static struct gbp_atrace_step sample[GBP_ATRACE_SAMPLE_MAX];
static uint32_t cycles[GBP_ATRACE_CYCLES_MAX];
static struct gbp_atrace tr;
static uint8_t stage[4096];
static int put(void *ctx, const uint8_t *b, uint32_t n) { return fwrite(b, 1, n, (FILE *)ctx) == n ? 0 : -1; }
int main(int argc, char **argv)
{
    struct gbp_atrace_storage s;
    char kind;
    unsigned long long a, b, c, d, e;
    FILE *in, *out;
    if (argc != 3) return 2;
    s.a_decoded = a_dec; s.a_delta = a_del; s.a_sat = a_sat; s.v_rec = v_rec; s.v_sat = v_sat;
    s.cb = cbs; s.step = steps; s.cycles = cycles; s.sample = sample;
    gbp_atrace_init(&tr, &s, 40500000u);
    tr.sample_every = 8u;
    in = fopen(argv[1], "r");
    if (!in) return 3;
    while (fscanf(in, " %c %llu %llu %llu %llu %llu", &kind, &a, &b, &c, &d, &e) == 6) {
        if (kind == 'A') { gbp_atrace_audio(&tr, (int16_t)(uint16_t)a, b); gbp_atrace_cost(&tr, (uint32_t)c); }
        else if (kind == 'C') {
            struct gbp_atrace_cb *r = gbp_atrace_callback(&tr, a, b);
            if (r) r->rec = (uint32_t)c;
            gbp_atrace_cost(&tr, (uint32_t)c);
        } else if (kind == 'S') {
            struct gbp_atrace_step *st = gbp_atrace_step_tagged(&tr, (enum gbp_atrace_kind)d, a, b, (uint8_t)e);
            gbp_atrace_step_rec(&tr, st, b, c);
        } else return 4;
    }
    fclose(in);
    out = fopen(argv[2], "wb");
    if (!out) return 5;
    if (gbp_atrace_emit(&tr, put, out, stage, sizeof stage) == 0u) return 6;
    return fclose(out) == 0 ? 0 : 7;
}
"""
KIND = {"produce": 1, "flush_queue": 2, "process": 3}


class TheAssignmentIsOneSequenceOnBothSides(unittest.TestCase):
    def test_the_images_c_gives_the_hosts_arms(self):
        import v24accept
        with tempfile.TemporaryDirectory() as d:
            src, exe = os.path.join(d, "a.c"), os.path.join(d, "a")
            with open(src, "w") as f:
                f.write(ARMS_DRIVER)
            have, ok, err = hostcc.compile_c(["-std=gnu11", "-Wall", "-Wextra", "-Werror", "-I",
                                              os.path.join(ROOT, "src", "audio"), "-o", exe, src, ASPLIT_C])
            hostcc.require(self, have, ok, err, "the assignment's host driver")
            got = subprocess.run([exe], capture_output=True, text=True, check=True).stdout
        self.assertEqual([int(ch) for ch in got], v24accept.arms(4000))


class ARunBSessionRoundTripsThroughTheRecorderTheBuilderAndTheGates(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import test_v24accept as tv
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.tmp.name
        with open(os.path.join(d, "driver.c"), "w") as f:
            f.write(TRACE_DRIVER)
        cls.exe = os.path.join(d, "driver")
        cls.have, cls.ok, cls.err = hostcc.compile_c(
            ["-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror", "-I", os.path.join(ROOT, "src", "audio"),
             "-I", os.path.join(ROOT, "src", "gbp"), "-o", cls.exe, os.path.join(d, "driver.c"), ATRACE_C,
             os.path.join(ROOT, "src", "gbp", "gbp_crc32.c")])
        cls.direct = tv.build(700, {tv.HALF: 0.3, tv.FULL: 0.9}, seed=3)
        # the session in the recorder's own event order; each cycle also runs short process steps, which only
        # the floorless sample may keep
        ev = []
        for e, x in cls.direct["callbacks"]:
            ev.append((e, 0, "C %d %d 20 0 0" % (e, x)))
            ev.append((e + 150000, 2, "S %d %d %d 3 0" % (e + 150000, e + 150050, e + 150060)))
        for s, tag in zip(cls.direct["steps"], cls.direct["step_tag"]):
            ev.append((s[0], 2, "S %d %d %d %d %d" % (s[0], s[1], s[3], KIND[s[2]], tag)))
        for v, t in zip(cls.direct["audio"]["decoded"], cls.direct["audio"]["ticks"]):
            ev.append((t, 1, "A %d %d 30 0 0" % (v & 0xFFFF, t)))
        ev.sort()
        cls.events = "\n".join(l for _t, _o, l in ev) + "\n"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def trace(self):
        hostcc.require(self, self.have, self.ok, self.err, "the version-2 recorder's host driver")
        ev, out = os.path.join(self.tmp.name, "ev.txt"), os.path.join(self.tmp.name, "trace.bin")
        with open(ev, "w") as f:
            f.write(self.events)
        r = subprocess.run([self.exe, ev, out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, "rb") as f:
            return f.read()

    def log(self, data, **over):
        import v24report
        import v24accept
        m = read(SPLIT_MAIN)
        tr = v24report.parse_trace(data)
        d = self.direct
        arms = v24accept.arms(4000)
        chunks = sum(1 for t in d["step_tag"] if t & 2)
        half = sum(arms[:chunks])
        counts = dict(a=len(tr["decoded"]), a_sat=len(tr["a_sat"]), v=len(tr["v_rec"]), v_sat=len(tr["v_sat"]),
                      cb=len(tr["callbacks"]), steps=len(tr["steps"]), cycles=len(tr["cycles"]))
        seed = over.pop("seed", 0x9E3779B9)
        lines = ["000001 IDENT test=GBP-AUDIO-009 app=gbp-audio-split build=split-0001 commit=abcdef0 libogc=x"]
        seq = [2]

        def put(fmt, vals):
            lines.append("%06u %s" % (seq[0], tt.render(fmt, vals)))
            seq[0] += 1
        o, e = d["window"]["t_origin"], d["window"]["t_end"]
        put(tt.c_formats(m, "LIVE")[0], ["done", 1, 0, 0, 1, 0, 1, 0, 1])
        put(tt.c_formats(m, "LIVET")[0], [TB, "%x" % (o - TB), "%x" % o, "%x" % o, "%x" % o, "%x" % e])
        put(tt.c_formats(m, "LIVET2")[0], ["%x" % o, "%x" % e, "%x" % e, 19776, "%x" % o])
        cov = d["window"]["coverage"]
        for k in range(0, len(cov), 16):
            put(tt.c_formats(m, "LIVESEC")[0], [k, ",".join(str(c) for c in cov[k:k + 16])])
        put(tt.c_formats(m, "LIVETRACE")[0], [counts[k] for k in ("a", "a_sat", "v", "v_sat", "cb", "steps", "cycles")]
            + [tr["cost_max"], tr["floor"]])
        put(tt.c_formats(m, "LIVESPLIT")[0], ["%08x" % seed, half, chunks - half, tr["sample_every"],
                                              len(tr["sample"]), tr["sample_dropped"]])
        lines.append("%06u FRAMECAP frames=1 complete=1 incomplete=0 resync=0 anomaly_frame=0 anomaly_region=0 "
                     "counted=1 blocks=40 pre_boundary=0 store_full=0" % seq[0])
        return "\n".join(lines) + "\n"

    def test_the_ticks_the_tags_and_the_sample_come_back(self):
        import v24report
        data = self.trace()
        rep = v24report.build(self.log(data), data)
        d = self.direct
        self.assertEqual(rep["audio"]["ticks"], d["audio"]["ticks"])
        self.assertEqual(rep["steps"], d["steps"])                  # the short steps are under the floor
        self.assertEqual(rep["step_tag"], d["step_tag"])
        ent = [c[0] for c in d["callbacks"]]
        import bisect
        sampled = [s for s in rep["sample"]["steps"]]
        self.assertTrue(sampled)
        for s in sampled:                                            # only in cycles 1, 9, 17, ... (cb_n % 8 == 1)
            self.assertEqual((bisect.bisect_right(ent, s[0])) % 8, 1, s)
        short = [s for s in sampled if s[1] - s[0] == 50]
        self.assertEqual(len(short), len({bisect.bisect_right(ent, s[0]) for s in sampled}))   # one per sampled cycle
        kept = dict((s[0], t) for s, t in zip(rep["steps"], rep["step_tag"]))
        prod = [s for s in sampled if s[2] == "produce"]
        self.assertTrue(prod)
        for s in prod:                                               # the same tag in both records
            self.assertEqual(s[3], kept[s[0]], s)

    def test_the_frozen_gates_read_the_same_verdict_as_the_direct_session(self):
        import v24report
        import v24accept
        data = self.trace()
        through = v24accept.evaluate(v24report.build(self.log(data), data), trials=400, k_trials=50)["S"]
        direct = v24accept.evaluate(self.direct, trials=400, k_trials=50)["S"]
        self.assertEqual(through["verdict"], "CAUSE", through["why"])
        for k in ("verdict", "p", "ratio", "ci90", "excluded_cycles"):
            self.assertEqual(through[k], direct[k], k)
        self.assertEqual(through["arms"]["half"]["loss_gaps"], direct["arms"]["half"]["loss_gaps"])

    def test_a_foreign_seed_or_another_version_is_refused(self):
        import v24report
        data = self.trace()
        with self.assertRaisesRegex(ValueError, "frozen 0x9e3779b9"):
            v24report.build(self.log(data, seed=0x12345678), data)
        with self.assertRaisesRegex(ValueError, "version 1"):
            v24report.parse_trace(data[:8] + b"\x00\x00\x00\x01" + data[12:-4] +
                                  __import__("struct").pack(">I", __import__("zlib").crc32(
                                      data[:8] + b"\x00\x00\x00\x01" + data[12:-4]) & 0xFFFFFFFF))


class TheReportBuilderIsFrozenBeforeTheRun(unittest.TestCase):
    """tools/v24report.py decides nothing, but every choice it makes -- the version it accepts, the seed it
    refuses, the sample's absolute ticks -- is one the data could otherwise be argued into."""

    def test_v24report_is_the_bytes_of_the_commit_that_froze_it(self):
        import frozen
        then = frozen.source("Issue #105 -- split-0001 and its report builder", "tools/v24report.py")
        self.assertEqual(then, read(os.path.join(ROOT, "tools", "v24report.py")),
                         "tools/v24report.py was edited after it was frozen")


# ---- the audit ----------------------------------------------------------------------

class TheAuditDiscriminatesBothWays(unittest.TestCase):
    def _run(self, out_dir, profile):
        if not os.path.exists(os.path.join(out_dir, "audit", "elf.nm.txt")):
            self.skipTest("%s is not built in this checkout" % out_dir)
        r = subprocess.run([sys.executable, AUDIT, os.path.join(out_dir, "audit"), "--profile", profile],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_split_passes_the_split_image(self):
        rc, out = self._run(SPLIT_OUT, "split")
        self.assertEqual(rc, 0, out[:2000])

    def test_split_fails_the_trace_image(self):
        rc, out = self._run(TRACE_OUT, "split")
        self.assertNotEqual(rc, 0)
        self.assertIn("expected object missing: gbp_asplit.o", out)

    def test_trace_fails_the_split_image(self):
        rc, out = self._run(SPLIT_OUT, "trace")
        self.assertNotEqual(rc, 0)

    def test_the_profile_is_derived_from_trace(self):
        import poc_audit
        trace, split = poc_audit.PROFILES["trace"], poc_audit.PROFILES["split"]
        self.assertEqual(set(split["required_objects"]) - set(trace["required_objects"]), {"gbp_asplit.o"})
        moved = {"gbp_atrace_step", "gbp_crc32_update"}
        for s, want in trace["symbol_callers"].items():
            if s not in moved:
                self.assertEqual(split["symbol_callers"][s], want, s)
        self.assertEqual(split["symbol_callers"]["gbp_asplit_step_pushes"], {"main": 0})
        self.assertEqual(split["symbol_callers"]["gbp_atrace_step_tagged"], {"pump": 1, "gbp_atrace_step": 1})


if __name__ == "__main__":
    unittest.main()
