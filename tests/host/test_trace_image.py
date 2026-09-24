"""
tests/host/test_trace_image.py — GitHub Issue #101: RUN A's image (poc/gbp-audio-trace,
GBP-AUDIO-008, trace-0001), pinned to live-0001, to §V23 and to the report its frozen gates read.

ONE VARIABLE, SHOWN BY DIFFING (§V23.4). live-0001 (poc/gbp-audio-live, RUN 38's image) is this
image's base. Every line live-0001 has is here unchanged but its identity -- the five lines named
below -- and every line added is either the new header or sits in a hunk that begins in a block
marked TRACE. Every function the recorder did not need is character for character live-0001's.
Inside the service transaction, the AI's callback and the pump slot, a TRACE block calls the
recorder and the clock and nothing else.

THE LOG AND THE TRACE ARE THE INTERFACE. The image writes LIVE* records and a trace sidecar;
tools/v23report.py turns both into the report tools/v23accept.py (frozen before this image
existed) reads. The recorder's own C (src/audio/gbp_atrace.c) is compiled on the host here, fed
a synthetic session, and its file goes through the builder and the frozen gates: every tick the
recorder was given comes back exactly, and the gates see the losses the session was built with.

THE AUDIT IS EXERCISED, NOT COUNTED: when the listings exist, `trace` passes this image and fails
live-0001's, and `live` fails this image.
"""
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(__file__))

import hostcc  # noqa: E402

TRACE_MAIN = os.path.join(ROOT, "poc", "gbp-audio-trace", "source", "main.c")
TRACE_MAKEFILE = os.path.join(ROOT, "poc", "gbp-audio-trace", "Makefile")
LIVE_MAIN = os.path.join(ROOT, "poc", "gbp-audio-live", "source", "main.c")
LIVE_MAKEFILE = os.path.join(ROOT, "poc", "gbp-audio-live", "Makefile")
ATRACE_C = os.path.join(ROOT, "src", "audio", "gbp_atrace.c")
ATRACE_H = os.path.join(ROOT, "src", "audio", "gbp_atrace.h")
VSIG_H = os.path.join(ROOT, "src", "gbp", "gbp_vsig.h")
AUDIT = os.path.join(ROOT, "tools", "poc_audit.py")
TRACE_OUT = os.path.join(ROOT, "build", "poc", "gbp-audio-trace")
LIVE_OUT = os.path.join(ROOT, "build", "poc", "gbp-audio-live")
RINGLOG_CONTENT_MAX = 256 - 7 - 1      # LOG_LINE_LEN, minus the "%06u " prefix and the NUL
TB = 40500000

# live-0001's identity, and what replaces it: the ONLY lines of live-0001 this image changes
IDENTITY = {
    '#define OPENGBP_APP_NAME "gbp-audio-live"': '#define OPENGBP_APP_NAME "gbp-audio-trace"',
    '#define TEST_ID "GBP-AUDIO-007"': '#define TEST_ID "GBP-AUDIO-008"',
    '    printf("\\n  Open-GBP " TEST_ID "  PHASE 6\'s ACCEPTANCE IMAGE (HARDWARE_TESTS V22; NOT PHYSICALLY VALIDATED)\\n");':
        '    printf("\\n  Open-GBP " TEST_ID "  RUN A, READ-ONLY TIMING (HARDWARE_TESTS V23; NOT PHYSICALLY VALIDATED)\\n");',
    '    printf("\\n  X = save log and L2 record to SD    START = exit    POWER CYCLE REQUIRED\\n");':
        '    printf("\\n  X = save log, L2 record and trace to SD    START = exit    POWER CYCLE REQUIRED\\n");',
    '                     "libogc=%s gecko=%d power_cycle_required=%d sidecar=l2 time_target=disabled safety_s=%lu "':
        '                     "libogc=%s gecko=%d power_cycle_required=%d sidecar=l2+trace time_target=disabled safety_s=%lu "',
}
# the functions whose bodies gained TRACE blocks; every other function is live-0001's
TRACED = ("live_tap", "live_dma_cb", "live_step", "main")
# what a TRACE block inside the tap, the VIDEO tap, the callback or the pump slot may call
ON_THE_PATH = ("live_tap", "live_vtap", "live_dma_cb", "live_step")
# every assignment the TRACE blocks make: their own locals, the callback record's own write time,
# the recorder's storage descriptor, and the VIDEO hook
TRACE_WRITES = {"q0", "w", "tr_entry", "x", "r", "y", "r->rec", "tr_s0", "tr_s1", "tr_st",
                "s.a_decoded", "s.a_delta", "s.a_sat", "s.v_rec", "s.v_sat", "s.cb", "s.step", "s.cycles",
                "cfg.video_tap", "cfg.video_tap_user", "tr_status", "t_write", "t_close", "tn", "t_open"}
PATH_CALLS = {"gettime", "ticks64", "gbp_atrace_audio", "gbp_atrace_video", "gbp_atrace_callback",
              "gbp_atrace_step", "gbp_atrace_step_rec", "gbp_atrace_cost"}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def hunks(before, after):
    """(removed, added, first line number in `after`) per difflib opcode that is not 'equal'."""
    import difflib
    a, b = before.splitlines(), after.splitlines()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            out.append((a[i1:i2], b[j1:j2], j1))
    return out


def functions(src):
    """name -> text of every top-level function definition."""
    out = {}
    for m in re.finditer(r"^(?:static )?[a-z_][\w ]*?\**\b(\w+)\(([^;{]*)\)\n\{", src, re.M):
        j = src.index("\n}\n", m.start()) + 3
        out[m.group(1)] = src[m.start():j]
    return out


def enclosing(src_lines, lineno):
    """The name of the function whose body contains line `lineno` (0-based), or None."""
    for k in range(lineno, -1, -1):
        m = re.match(r"^(?:static )?[a-z_][\w ]*?\**\b(\w+)\([^;]*\)$", src_lines[k])
        if m and k + 1 < len(src_lines) and src_lines[k + 1] == "{":
            return m.group(1)
        if src_lines[k] == "}" and k != lineno:
            return None
    return None


def srcs(makefile):
    return re.search(r"^SRCS := (.*)$", read(makefile), re.M).group(1).split()


def c_formats(src, tag, var="rl"):
    out = []
    for m in re.finditer(r'ringlog_printf\(&%s,\s*((?:"(?:[^"\\]|\\.)*"\s*)+),' % var, src):
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


class TheImageIsLive0001PlusTheRecorder(unittest.TestCase):

    def test_live_0001_loses_nothing_but_its_identity(self):
        removed = [l for r, _a, _j in hunks(read(LIVE_MAIN), read(TRACE_MAIN)) for l in r]
        self.assertEqual(sorted(removed), sorted(IDENTITY))

    def test_every_addition_is_the_header_an_identity_line_or_a_trace_block(self):
        after = read(TRACE_MAIN).splitlines()
        for removed, added, j in hunks(read(LIVE_MAIN), read(TRACE_MAIN)):
            if removed:
                self.assertEqual(added, [IDENTITY[r] for r in removed], (removed, added))
            elif j <= 1:                  # the new header, above live-0001's own
                self.assertTrue(all(l.startswith((" *", "/*")) for l in added), added[:3])
                self.assertIn("GBP-AUDIO-008, build trace-0001", "\n".join(added[:3]))
            else:
                self.assertIn("TRACE", added[0], "an added hunk at line %d is not marked TRACE: %r" % (j + 1, added[0]))

    def test_the_untouched_functions_are_live_0001s_character_for_character(self):
        live, trace = functions(read(LIVE_MAIN)), functions(read(TRACE_MAIN))
        self.assertGreaterEqual(len(live), 20, sorted(live))
        for name, text in live.items():
            if name not in TRACED:
                self.assertEqual(trace.get(name), text, name)
        self.assertEqual(set(trace) - set(live), {"live_vtap", "trace_put"})

    def test_on_the_path_a_trace_block_calls_the_recorder_and_the_clock_and_nothing_else(self):
        after = read(TRACE_MAIN).splitlines()
        seen = set()
        for removed, added, j in hunks(read(LIVE_MAIN), read(TRACE_MAIN)):
            if removed or j <= 1:
                continue
            text = "\n".join(added) + "\n"
            if "static void live_vtap(" in text:
                fn, body = "live_vtap", functions(text)["live_vtap"].split("\n{", 1)[1]
            else:
                fn, body = enclosing(after, j), text
            if fn not in ON_THE_PATH:
                continue
            seen.add(fn)
            code = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
            calls = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", code)) - {"if", "sizeof", "return"}
            self.assertLessEqual(calls, PATH_CALLS, "%s: %s" % (fn, sorted(calls - PATH_CALLS)))
        self.assertEqual(seen, set(ON_THE_PATH))

    def test_a_trace_hunk_writes_only_its_own_locals_and_the_records(self):
        """A hunk is judged by its first line, so a line of live-0001's state slipped in beside a TRACE
        line would pass the marker rule. This one reads every assignment an added hunk makes: each is to
        a local the TRACE block declares, to the record the recorder handed back, to the recorder's
        storage descriptor, or to the one hook it installs -- never to anything live-0001 already had."""
        targets = set()
        for removed, added, j in hunks(read(LIVE_MAIN), read(TRACE_MAIN)):
            if removed or j <= 1:
                continue
            code = re.sub(r"/\*.*?\*/", "", "\n".join(added), flags=re.S)
            code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
            targets |= set(re.findall(r"(\w+(?:(?:->|\.)\w+)*)\s*(?:\[[^\]]*\])?\s*(?:[-+*/%&|^]|<<|>>)?=(?!=)", code))
        self.assertEqual(targets, TRACE_WRITES, sorted(targets ^ TRACE_WRITES))

    def test_the_card_is_written_after_the_session_and_the_log_says_so(self):
        m = read(TRACE_MAIN)
        main = functions(m)["main"]
        run = main.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);")
        x = main.index("PAD_ButtonsDown(0) & PAD_BUTTON_X")
        emit = main.index("gbp_atrace_emit(")
        self.assertLess(run, x)
        self.assertLess(x, emit)
        self.assertLess(main.index("LIVETRACESAVE"), main.index("rc = sdlog_save("))
        self.assertLess(main.index("\"LIVETRACE a="), x)
        self.assertEqual(m.count("gbp_atrace_emit("), 1)
        self.assertIn("return sdlog_stream_write((struct sdlog_stream *)ctx, bytes, n);", functions(m)["trace_put"])

    def test_the_video_tap_flags_frame_starts_by_gbis_predicate(self):
        mask = int(re.search(r"#define GBP_VSIG_GBI_MASK (0x[0-9a-fA-F]+)u", read(VSIG_H)).group(1), 16)
        vtap = functions(read(TRACE_MAIN))["live_vtap"]
        self.assertIn("gbp_atrace_video(&tr, (w & 0x%08xu) == 0x%08xu, t_done);" % (mask, mask), vtap)
        self.assertIn("if (!completed) return;", vtap)
        self.assertIn("cfg.video_tap = live_vtap;", read(TRACE_MAIN))

    def test_the_sources_are_live_0001s_and_the_recorder(self):
        self.assertEqual(set(srcs(TRACE_MAKEFILE)) - set(srcs(LIVE_MAKEFILE)), {"gbp_atrace.c"})
        self.assertEqual(set(srcs(LIVE_MAKEFILE)) - set(srcs(TRACE_MAKEFILE)), set())
        mk = read(TRACE_MAKEFILE)
        self.assertRegex(mk, r"(?m)^APP_NAME\s*:=\s*gbp-audio-trace$")
        self.assertRegex(mk, r"(?m)^BUILD_ID\s*:=\s*trace-0001$")
        # everything but the header, the identity and the source list is live-0001's Makefile
        rest = [l for r, a, _j in hunks(read(LIVE_MAKEFILE), mk) for l in r]
        for l in rest:
            self.assertTrue(l.startswith(("# Open-GBP GBP-AUDIO-007", "#     make -C", "# Outputs go to",
                                          "APP_NAME", "BUILD_ID", "SRCS :=")), l)

    def test_the_recorder_is_preallocated_and_the_arena_is_asked(self):
        m = read(TRACE_MAIN)
        for arr in ("tr_a_dec[GBP_ATRACE_A_MAX]", "tr_a_del[GBP_ATRACE_A_MAX]", "tr_v_rec[GBP_ATRACE_V_MAX]",
                    "tr_cb[GBP_ATRACE_CB_MAX]", "tr_step[GBP_ATRACE_STEP_MAX]", "tr_cycles[GBP_ATRACE_CYCLES_MAX]"):
            self.assertRegex(m, r"(?m)^static [\w ]+ %s;$" % re.escape(arr))
        self.assertNotRegex(read(ATRACE_C), r"\b(malloc|calloc|realloc|free|printf|fopen|fwrite)\s*\(")


class NoTraceRecordCanBeTruncated(unittest.TestCase):

    def test_every_live_record_fits_the_ringlog_line_at_its_worst(self):
        m = read(TRACE_MAIN)
        tags = sorted(set(re.findall(r'"(LIVE[A-Z0-9]*) ', m)))
        self.assertTrue({"LIVETRACE", "LIVETRACE2", "LIVETRACESAVE"} <= set(tags), tags)
        status = int(re.search(r"char tr_status\[(\d+)\]", m).group(1))
        per_line = ",".join(["4294967295"] * 16)
        for tag in tags:
            for fmt in c_formats(m, tag):
                strings = {"LIVESEC": [per_line], "LIVEFILL": [per_line], "LIVEL2SAVE": ["x" * 159],
                           "LIVETRACESAVE": ["x" * (status - 1)], "LIVE": ["calibrate"]}.get(tag, [])
                line = worst_case(fmt, strings)
                self.assertLessEqual(len(line), RINGLOG_CONTENT_MAX, "%s renders %d characters" % (tag, len(line)))


# ---- the recorder, on the host, through the builder and the frozen gates ------------------------

DRIVER = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_atrace.h"
static int16_t a_dec[GBP_ATRACE_A_MAX];
static uint16_t a_del[GBP_ATRACE_A_MAX];
static struct gbp_atrace_sat a_sat[GBP_ATRACE_A_SAT_MAX];
static uint16_t v_rec[GBP_ATRACE_V_MAX];
static struct gbp_atrace_sat v_sat[GBP_ATRACE_V_SAT_MAX];
static struct gbp_atrace_cb cbs[GBP_ATRACE_CB_MAX];
static struct gbp_atrace_step steps[GBP_ATRACE_STEP_MAX];
static uint32_t cycles[GBP_ATRACE_CYCLES_MAX];
static struct gbp_atrace tr;
static uint8_t stage[4096];
static int put(void *ctx, const uint8_t *b, uint32_t n) { return fwrite(b, 1, n, (FILE *)ctx) == n ? 0 : -1; }
int main(int argc, char **argv)
{
    struct gbp_atrace_storage s;
    char kind;
    unsigned long long a, b, c, d;
    FILE *in, *out;
    if (argc != 4) return 2;
    s.a_decoded = a_dec; s.a_delta = a_del; s.a_sat = a_sat; s.v_rec = v_rec; s.v_sat = v_sat;
    s.cb = cbs; s.step = steps; s.cycles = cycles;
    gbp_atrace_init(&tr, &s, (uint32_t)strtoul(argv[3], 0, 10));
    in = fopen(argv[1], "r");
    if (!in) return 3;
    while (fscanf(in, " %c %llu %llu %llu %llu", &kind, &a, &b, &c, &d) == 5) {
        if (kind == 'A') { gbp_atrace_audio(&tr, (int16_t)(uint16_t)a, b); gbp_atrace_cost(&tr, (uint32_t)c); }
        else if (kind == 'V') { gbp_atrace_video(&tr, (int)a, b); gbp_atrace_cost(&tr, (uint32_t)c); }
        else if (kind == 'C') {
            struct gbp_atrace_cb *r = gbp_atrace_callback(&tr, a, b);
            if (r) r->rec = (uint32_t)c;
            gbp_atrace_cost(&tr, (uint32_t)c);
        } else if (kind == 'S') {
            struct gbp_atrace_step *st = gbp_atrace_step(&tr, (enum gbp_atrace_kind)(d >> 48), a, b);
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
P = 9888                  # ~one AUDIO block period, in ticks
B = 11890                 # VIDEO block spacing
F = 678000                # one frame
CB = 1278000              # AI callback period
T0 = 0x100000000


def session():
    """A synthetic session in the recorder's own event order, and what the report must say."""
    ev = []                                   # (t, order, line)
    # VIDEO: 30 frames of 40 blocks from T0; frame 10 loses block 20 (one VIDEO gap)
    vt, vs = [], []
    for fr in range(30):
        for i in range(40):
            if fr == 10 and i == 20:
                continue
            t = T0 + fr * F + i * B
            vt.append(t)
            vs.append(1 if i == 0 else 0)
            ev.append((t, 1, "V %d %d 25 0" % (1 if i == 0 else 0, t)))
    # AUDIO: 40 periods of the 128 Hz tone from 3 frames in; half 10 loses one plateau sample
    # (a 2-block gap), half 20 loses seven (an 8-block gap, which saturates the u16 delta)
    ta0 = T0 + 3 * F
    at, ad = [], []
    lost = {(10, 7)} | {(20, k) for k in range(2, 9)}
    for h in range(80):
        for k in range(16):
            if (h, k) in lost:
                continue
            v = 0 if k == 15 else (20000 if h % 2 == 0 else -20000)
            t = ta0 + (h * 16 + k) * P
            at.append(t)
            ad.append(v)
            ev.append((t, 2, "A %d %d 30 0" % (v & 0xFFFF, t)))
    # the AI callbacks, and after each the chain's three steps; one produce and one process
    # below the floor per cycle, counted and costed but not kept
    cbs, steps, below = [], [], []
    for n in range(12):
        e = T0 + 100000 + n * CB
        cbs.append([e, e + 800])
        ev.append((e, 0, "C %d %d 20 0" % (e, e + 800)))
        for off, dur, kind, rec in ((5000, 4000, "produce", 40), (9500, 50, "flush_queue", 12),
                                    (10000, 300, "process", 35), (20000, 100, "produce", 18),
                                    (30000, 90, "process", 16)):
            s0 = e + off
            ev.append((s0, 3, "S %d %d %d %d" % (s0, s0 + dur, s0 + dur + rec, KIND[kind] << 48)))
            if dur >= 200 or kind == "flush_queue":
                steps.append([s0, s0 + dur, kind, s0 + dur + rec])
            else:
                below.append((e, rec))
    # a long produce over the 2-block loss's whole gap, a long process over the 8-block one
    for (h, k), kind in (((10, 7), "produce"), ((20, 2), "process")):
        g0 = ta0 + (h * 16 + k - 1) * P
        g1 = ta0 + (h * 16 + k + (1 if kind == "produce" else 7)) * P
        ev.append((g0 - 500, 3, "S %d %d %d %d" % (g0 - 500, g1 + 500, g1 + 540, KIND[kind] << 48)))
        steps.append([g0 - 500, g1 + 500, kind, g1 + 540])
    ev.sort()
    # the per-cycle cost: cycle c holds every write after callback c-1 (cycle 0: before the first)
    cyc = [0] * (len(cbs) + 1)
    n = 0
    mx = 0
    for t, order, line in ev:
        f = line.split()
        if f[0] == "C":
            n += 1
            cost = int(f[3])
        elif f[0] in ("A", "V"):
            cost = int(f[3])
        else:
            s0, s1, r, kind = int(f[1]), int(f[2]), int(f[3]), int(f[4]) >> 48
            if s1 - s0 >= 200 or kind == 2:
                continue
            cost = r - s1
        cyc[n] += cost
        mx = max(mx, cost)
    steps.sort()
    want = {"audio": (at, ad), "video": (vt, vs), "callbacks": cbs, "steps": steps, "cycles": cyc, "cost_max": mx,
            "ta0": ta0}
    return "\n".join(l for _t, _o, l in ev) + "\n", want


class TheRecorderRoundTripsThroughTheBuilderAndTheGates(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.tmp.name
        with open(os.path.join(d, "driver.c"), "w") as f:
            f.write(DRIVER)
        cls.exe = os.path.join(d, "driver")
        cls.have, cls.ok, cls.err = hostcc.compile_c(
            ["-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror", "-I", os.path.join(ROOT, "src", "audio"),
             "-I", os.path.join(ROOT, "src", "gbp"), "-o", cls.exe, os.path.join(d, "driver.c"), ATRACE_C,
             os.path.join(ROOT, "src", "gbp", "gbp_crc32.c")])
        cls.events, cls.want = session()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def trace(self, tb=TB):
        hostcc.require(self, self.have, self.ok, self.err, "the recorder's host driver")
        ev = os.path.join(self.tmp.name, "events.txt")
        out = os.path.join(self.tmp.name, "trace-%d.bin" % tb)
        with open(ev, "w") as f:
            f.write(self.events)
        r = subprocess.run([self.exe, ev, out, str(tb)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, "rb") as f:
            return f.read()

    def log(self, data, **over):
        import v23report
        m = read(TRACE_MAIN)
        tr = v23report.parse_trace(data)
        origin = self.want["ta0"]
        counts = dict(a=len(tr["decoded"]), a_sat=len(tr["a_sat"]), v=len(tr["v_rec"]), v_sat=len(tr["v_sat"]),
                      cb=len(tr["callbacks"]), steps=len(tr["steps"]), cycles=len(tr["cycles"]))
        counts.update(over)
        lines = ["000001 IDENT test=GBP-AUDIO-008 app=gbp-audio-trace build=trace-0001 commit=abcdef0 libogc=x"]
        seq = [2]

        def put(fmt, vals):
            lines.append("%06u %s" % (seq[0], render(fmt, vals)))
            seq[0] += 1
        put(c_formats(m, "LIVE")[0], ["done", 1, 0, 0, 1, 0, 1, 0, 1])
        put(c_formats(m, "LIVET")[0], [TB, "%x" % T0, "%x" % (T0 + TB), "%x" % (T0 + 2 * TB), "%x" % origin,
                                       "%x" % (origin + 2 * TB)])
        put(c_formats(m, "LIVET2")[0], ["%x" % (T0 + 100000), "%x" % (T0 + 100000 + 11 * CB),
                                        "%x" % (origin + 2 * TB), 19776, "%x" % origin])
        put(c_formats(m, "LIVESEC")[0], [0, "4088,4096"])
        put(c_formats(m, "LIVETRACE")[0], [counts[k] for k in ("a", "a_sat", "v", "v_sat", "cb", "steps", "cycles")]
            + [tr["cost_max"], tr["floor"]])
        lines.append("%06u FRAMECAP frames=30 complete=29 incomplete=1 resync=0 anomaly_frame=0 anomaly_region=0 "
                     "counted=29 blocks=1199 pre_boundary=0 store_full=0" % seq[0])
        return "\n".join(lines) + "\n"

    def test_every_tick_the_recorder_was_given_comes_back_exactly(self):
        import v23report
        data = self.trace()
        rep = v23report.build(self.log(data), data)
        at, ad = self.want["audio"]
        self.assertEqual(rep["audio"]["ticks"], at)
        self.assertEqual(rep["audio"]["decoded"], ad)
        vt, vs = self.want["video"]
        self.assertEqual(rep["video"]["ticks"], vt)
        self.assertEqual(rep["video"]["start"], vs)
        self.assertEqual(rep["callbacks"], self.want["callbacks"])
        self.assertEqual(rep["steps"], self.want["steps"])
        self.assertEqual(rep["recorder"]["tap_before_first"], self.want["cycles"][0])
        self.assertEqual(rep["recorder"]["tap_ticks_per_cycle"], self.want["cycles"][1:])
        self.assertEqual(rep["recorder"]["tap_max_write"], self.want["cost_max"])
        self.assertEqual(rep["window"]["coverage"], [4088, 4096])
        self.assertEqual(rep["window"]["framecap_session"], 1)
        self.assertEqual(rep["trace"]["calls"], {"produce": 12 * 2 + 1, "flush_queue": 12, "process": 12 * 2 + 1})
        self.assertEqual(sum(rep["trace"]["dropped"].values()), 0)
        # the 8-block gap saturated the u16 delta and came back from the side ring
        self.assertEqual(len(v23report.parse_trace(data)["a_sat"]), 1)
        self.assertEqual(json.loads(json.dumps(rep)), rep)

    def test_the_frozen_gates_see_the_losses_the_session_was_built_with(self):
        import v23report
        import v23accept
        data = self.trace()
        r = v23accept.evaluate(v23report.build(self.log(data), data), trials=200)
        self.assertEqual((r["loss_gaps"], r["losses_located"]), (2, 8))
        self.assertEqual(r["P"]["counts"]["produce"], 1)
        self.assertEqual(r["P"]["counts"]["process"], 1)
        self.assertEqual(r["K"]["verdict"], "INCONCLUSIVE")          # one VIDEO gap, fewer than ten
        self.assertEqual(r["K"]["video_gaps"], 1)
        self.assertTrue(r["observer"]["sanity_ok"], r["observer"])

    def test_a_trace_that_is_not_this_logs_is_refused(self):
        import v23report
        data = self.trace()
        with self.assertRaisesRegex(ValueError, "not this log's"):
            v23report.build(self.log(data, a=1), data)

    def test_a_damaged_trace_is_refused(self):
        import v23report
        data = bytearray(self.trace())
        data[0x80] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC-32"):
            v23report.build(self.log(bytes(self.trace())), bytes(data))

    def test_another_timebase_is_refused(self):
        import v23report
        data = self.trace(tb=40000000)
        with self.assertRaisesRegex(ValueError, "timebase"):
            v23report.build(self.log(data), data)


class TheBuilderRefusesToGuessAbsoluteTime(unittest.TestCase):

    def test_a_saturated_delta_without_its_tick_is_refused(self):
        import v23report
        self.assertEqual(v23report.absolute(100, [0, 5, 0xFFFF, 7], [(2, 90000)], 0xFFFF, 0xFFFF, "AUDIO"),
                         [100, 105, 90000, 90007])
        with self.assertRaisesRegex(ValueError, "absolute time is lost"):
            v23report.absolute(100, [0, 5, 0xFFFF, 7], [], 0xFFFF, 0xFFFF, "AUDIO")

    def test_the_video_flag_is_not_part_of_the_delta(self):
        import v23report
        self.assertEqual(v23report.absolute(10, [0x8000, 0x8000 | 300, 0x7FFF | 0x8000], [(2, 5000)], 0x7FFF, 0x7FFF,
                                            "VIDEO"), [10, 310, 5000])


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

    def test_trace_passes_the_trace_image(self):
        rc, out = self._run(TRACE_OUT, "trace")
        self.assertEqual(rc, 0, out[:2000])
        self.assertIn("0 finding(s)", out)

    def test_trace_fails_the_live_image(self):
        rc, out = self._run(LIVE_OUT, "trace")
        self.assertNotEqual(rc, 0)
        self.assertIn("expected object missing: gbp_atrace.o", out)

    def test_live_fails_the_trace_image(self):
        rc, out = self._run(TRACE_OUT, "live")
        self.assertNotEqual(rc, 0)
        self.assertIn("sdlog_stream_write call sites", out)

    def test_the_profile_is_derived_from_live(self):
        import poc_audit
        live, trace = poc_audit.PROFILES["live"], poc_audit.PROFILES["trace"]
        self.assertEqual(set(trace["required_objects"]) - set(live["required_objects"]), {"gbp_atrace.o"})
        self.assertEqual(set(trace["forbidden_symbols"]), set(live["forbidden_symbols"]))
        moved = {"gettime", "sdlog_stream_open", "sdlog_stream_write", "sdlog_stream_close"}
        for s, want in live["symbol_callers"].items():
            if s not in moved:
                self.assertEqual(trace["symbol_callers"][s], want, s)
        # the recorder's entries: each from the one place §V23 put it; the card: main's, after the session
        self.assertEqual(trace["symbol_callers"]["gbp_atrace_audio"], {"live_tap": 1})
        self.assertEqual(trace["symbol_callers"]["gbp_atrace_video"], {"live_vtap": 1})
        self.assertEqual(trace["symbol_callers"]["gbp_atrace_callback"], {"live_dma_cb": 1})
        self.assertEqual(trace["symbol_callers"]["gbp_atrace_emit"], {"main": 1})
        self.assertEqual(trace["symbol_callers"]["sdlog_stream_write"], {"main": 1, "trace_put": 1})
        # the CRC stays off every recording entry
        for s in ("gbp_crc32_update", "gbp_crc32_init", "gbp_crc32_final"):
            for caller in trace["symbol_callers"][s]:
                self.assertNotIn(caller, ("gbp_atrace_audio", "gbp_atrace_video", "gbp_atrace_callback",
                                          "gbp_atrace_step", "gbp_atrace_step_rec", "gbp_atrace_cost"), s)

    def test_the_sidecar_helpers_are_reached_from_emit_only(self):
        """be16/be32/be64/put_bytes/flush are static: the listing names them by section, so the
        auditor cannot pin their callers. The source can."""
        src = read(ATRACE_C)
        fns = functions(src)
        for helper in ("be16", "be32", "be64", "put_bytes", "flush"):
            callers = sorted(n for n, t in fns.items() if n != helper and re.search(r"\b%s\(" % helper, t))
            self.assertLessEqual(set(callers), {"gbp_atrace_emit", "be16", "be32", "be64", "put_bytes"}, helper)
        for entry in ("gbp_atrace_audio", "gbp_atrace_video", "gbp_atrace_callback", "gbp_atrace_step",
                      "gbp_atrace_step_rec", "gbp_atrace_cost"):
            self.assertNotRegex(fns[entry], r"\b(be16|be32|be64|put_bytes|flush|gbp_crc32\w*)\(", entry)


if __name__ == "__main__":
    unittest.main()
