"""
tests/host/test_ringlog_payloads.py — the GENERAL line-length guard of the stream
probe's ringlog records (Issue #27; the class GBP-VID-033 and GBP-KEY-008 belong to).

WHY. The ringlog stores a record in LOG_LINE_LEN = 256 bytes behind a
7-character `%06u ` prefix: 248 payload characters. Twice a summary record
rendered longer and was clipped on hardware — WITELIG (runs 9 and 10, repaired
in stream-0011) and ENVINPUT (RUN 14 and RUN 15, repaired in stream-0015). A
record that silently clips is a defect class, not an incident, so this guard
covers EVERY ringlog_printf of the probe and fails a test before a run does.

WHAT IT PROVES. For every record, the rendered length at the WORST CASE of
every conversion for this target's C types (powerpc-eabi, ILP32) with every
`%s` bounded by the vocabulary of its source (a table below; an unbounded `%s`
fails). Two tiers, stated honestly:
  * STRICT: the records this checkpoint owns or repaired, and the two of
    GBP-VID-033, must fit at the worst case, full stop.
  * RATCHET: four older records exceed 248 at the pure type-width worst case
    (a 32-bit counter printed with %lu is ten digits wide, and none of them can
    reach that in a 60 s run); their worst case is FROZEN here at the value it
    has today, so any edit that lets one grow — or any NEW record over 248 —
    fails; and their largest physical rendering in the versioned RUN 14 / RUN
    15 records is checked to be under the payload. Shrinking one is allowed
    and updates the table; silently growing one is not.
"""
import json
import os
import re
import subprocess
import unittest

import guards  # noqa: E402  (tests/host is on the path)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAIN = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c")
INPUT_H = os.path.join(ROOT, "src", "gbp", "gbp_input.h")
SRC_GBP = os.path.join(ROOT, "src", "gbp")
FX = os.path.join(ROOT, "captures", "fixtures")
PAYLOAD_MAX = 248
WIDTH = {"lu": 10, "ld": 11, "u": 10, "d": 11, "llu": 20, "lld": 20, "llx": 16, "lx": 8, "x": 8, "c": 1}
SPEC = re.compile(r"%(?:(\d+)\$)?([-+ #0]*)(\d+)?(?:\.(\d+))?(hh|h|ll|l|z|t|j)?([diouxXeEfgGcsp%])")
# every `%s` source, bounded by what it can print (checked against the sources below where they are code)
S_BOUND = [("TEST_ID", 13), ("OPENGBP_APP_NAME", 22), ("OPENGBP_BUILD_ID", 11), ("OPENGBP_GIT_COMMIT", 13), ("_V_STRING", 32),
           ("gbp_status_name(", 7), ("gbp_input_action_name(", 7), ("gbp_startup_mode_name(", 10),
           ("gbp_vstate_storage_fault(", 16), ("fault", 16)]
STRICT = ("ENVINPUT", "ENVINPUT2", "KEY", "KEYLOG", "WITELIG", "WITELIG2")
# the ratchet: the strict worst case of these records TODAY; a change to any of them must revisit this table
DEBT = {
    "DISPTRACE": 253,
    "ENVSTORE": 303,
    "INPUT": 269,
    "WITQUAL": 307
}
CANDIDATE_THAT_CLIPPED = "0ff8355"   # stream-0014: its single ENVINPUT record rendered to 266 (GBP-KEY-008)


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def strip_comments(src):
    return re.sub(r"//[^\n]*", " ", re.sub(r"/\*.*?\*/", " ", src, flags=re.S))


def split_args(s):
    """Top-level commas only: commas inside string literals, parentheses and brackets do not split."""
    out, depth, cur, quoted, i = [], 0, "", False, 0
    while i < len(s):
        ch = s[i]
        if quoted:
            cur += ch
            if ch == "\\":
                cur += s[i + 1]
                i += 1
            elif ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
            cur += ch
        elif ch in "([":
            depth += 1
            cur += ch
        elif ch in ")]":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    if cur.strip():
        out.append(cur.strip())
    return out


def calls(src, header):
    """Every ringlog_printf(...) of `src`: (tag, format, argument expressions)."""
    src = strip_comments(src)
    fmt_macros = dict(re.findall(r'#define (GBP_INPUT_EVENT_FMT) "((?:[^"\\]|\\.)*)"', header))
    m = re.search(r"#define GBP_INPUT_EVENT_ARGS\(e\) \\\n(.*?)\n(?=#define|\n)", header, re.S)
    args_macro = re.sub(r"\\\n", " ", m.group(1)) if m else ""
    out, i = [], 0
    while True:
        j = src.find("ringlog_printf(", i)
        if j < 0:
            return out
        k, depth, quoted = j + len("ringlog_printf("), 1, False
        while depth:
            ch = src[k]
            if quoted:
                if ch == "\\":
                    k += 1
                elif ch == '"':
                    quoted = False
            elif ch == '"':
                quoted = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            k += 1
        args = split_args(src[j + len("ringlog_printf("):k - 1])
        i = k
        fmt_expr = args[1]
        fmt = fmt_macros[fmt_expr] if fmt_expr in fmt_macros else "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', fmt_expr))
        fmt = fmt.encode().decode("unicode_escape")
        rest = args[2:]
        if len(rest) == 1 and rest[0].startswith("GBP_INPUT_EVENT_ARGS("):
            rest = split_args(args_macro)
        out.append((fmt.split(" ")[0], fmt, rest))


def worst_case(fmt, args):
    """The rendered length with every conversion at its maximum width; (length, unbounded %s sources, conversions)."""
    total, pos, ai, unbounded = 0, 0, 0, []
    for m in SPEC.finditer(fmt):
        total += m.start() - pos
        pos = m.end()
        conv, length, width = m.group(6), m.group(5) or "", m.group(3)
        if conv == "%":
            total += 1
            continue
        arg = args[ai] if ai < len(args) else ""
        ai += 1
        if conv == "s":
            w = None
            for key, bound in S_BOUND:
                if key in arg:
                    w = bound
                    break
            if w is None:
                unbounded.append(arg)
                w = 64
            total += w
            continue
        if conv in "pfeEgGaA":
            raise AssertionError("%r has no bounded worst case" % m.group(0))
        w = WIDTH[length + conv]
        if width and width.isdigit():
            w = max(w, int(width))
        total += w
    return total + len(fmt) - pos, unbounded, ai


def vocabulary(fn, files):
    for p in files:
        t = strip_comments(read(p))
        m = re.search(r"\b%s\s*\([^)]*\)\s*\{" % fn, t)
        if m:
            i = m.end() - 1
            depth, j = 0, i
            while True:
                depth += t[j] == "{"
                depth -= t[j] == "}"
                if depth == 0:
                    return re.findall(r'return "((?:[^"\\]|\\.)*)"', t[i:j + 1])
                j += 1
    return None


class EveryRecordIsBounded(unittest.TestCase):
    def setUp(self):
        self.calls = calls(read(MAIN), read(INPUT_H))
        self.worst = {}
        for tag, fmt, args in self.calls:
            w, unbounded, n = worst_case(fmt, args)
            self.assertEqual(unbounded, [], "an unbounded %%s in %s: document it in S_BOUND" % tag)
            self.assertEqual(n, len(args), "%s: %d conversions, %d arguments" % (tag, n, len(args)))
            self.worst[tag] = max(w, self.worst.get(tag, 0))

    def test_the_geometry_this_guard_assumes(self):
        self.assertIn("#define LOG_LINE_LEN 256", read(MAIN))
        self.assertIn('"%06u "', read(os.path.join(ROOT, "src", "log", "ringlog.c")))
        self.assertGreaterEqual(len(self.calls), 30)

    def test_the_string_vocabularies_are_the_ones_the_table_bounds(self):
        gbp = [os.path.join(d, f) for d in (SRC_GBP, os.path.join(ROOT, "src", "common"), os.path.join(ROOT, "src", "platform"))
               for f in sorted(os.listdir(d)) if f.endswith((".c", ".h"))] + [MAIN]   # gbp_startup_mode_name is static in gbp_startup.h
        for fn, bound in (("gbp_status_name", 7), ("gbp_input_action_name", 7), ("gbp_startup_mode_name", 10), ("gbp_vstate_storage_fault", 16)):
            words = vocabulary(fn, gbp)
            self.assertIsNotNone(words, fn)
            self.assertLessEqual(max(len(w) for w in words), bound, (fn, words))
        self.assertLessEqual(len("GBP-VIDEO-004"), 13)
        self.assertLessEqual(len("gbp-video-stream-probe"), 22)

    def test_the_strict_records_fit_at_the_worst_case(self):
        for tag in STRICT:
            self.assertIn(tag, self.worst, tag)
            self.assertLessEqual(self.worst[tag], PAYLOAD_MAX, "%s worst case %d > %d" % (tag, self.worst[tag], PAYLOAD_MAX))

    def test_no_new_record_exceeds_the_payload_and_the_debt_does_not_grow(self):
        for tag, w in sorted(self.worst.items()):
            if tag in DEBT:
                self.assertEqual(w, DEBT[tag], "%s: worst case %d, frozen %d — revisit the table on purpose" % (tag, w, DEBT[tag]))
            else:
                self.assertLessEqual(w, PAYLOAD_MAX, "%s worst case %d > %d: split it, as WITELIG and ENVINPUT were" % (tag, w, PAYLOAD_MAX))
        self.assertEqual(sorted(DEBT), sorted(t for t, w in self.worst.items() if w > PAYLOAD_MAX))

    def test_the_debt_records_never_rendered_near_the_payload_on_hardware(self):
        """The ratchet's justification, from data: in the versioned RUN 14 / RUN 15 records these formats
        rendered far below 248 (their counters are bounded by a 60 s run, not by their C type)."""
        seen = {}
        for run in (14, 15):
            with open(os.path.join(FX, "hw-gamecube-gbp-2026-09-21-idxcap-run%d-struct.json" % run), encoding="utf-8") as f:
                for tag, line in json.load(f)["log_records_verbatim"].items():
                    seen[tag.split(" ")[0]] = max(seen.get(tag.split(" ")[0], 0), len(line) - 7)
        for tag in DEBT:
            if tag in seen:
                self.assertLess(seen[tag], PAYLOAD_MAX - 20, (tag, seen[tag]))
        self.assertEqual(seen["ENVINPUT"], 248, "the stream-0014 clip, kept as data")


class TheRepairOfEnvinput(unittest.TestCase):
    def test_the_old_single_record_would_not_fit_and_the_guard_can_fail(self):
        src = guards.show(CANDIDATE_THAT_CLIPPED, "poc/gbp-video-stream-probe/source/main.c")  # Issue #83 (B): absent COMMIT skips, absent PATH fails
        old = {tag: (fmt, args) for tag, fmt, args in calls(src, read(INPUT_H))}
        w, _, _ = worst_case(*old["ENVINPUT"])
        self.assertGreater(w, PAYLOAD_MAX)
        self.assertNotIn("ENVINPUT2", old)

    def test_every_field_of_the_stream_0014_record_survives_across_the_two_records(self):
        now = {tag: fmt for tag, fmt, _ in calls(read(MAIN), read(INPUT_H))}
        fields = lambda fmt: set(re.findall(r"(\w+)=", fmt))
        old_fields = {"port", "policy", "stick_threshold", "trigger_threshold", "analog_ab_threshold", "filter_opposites", "refresh_ms",
                      "refresh_ticks", "layout", "index", "desc", "pressed_is_one", "desc_status", "selftest"}
        self.assertEqual(fields(now["ENVINPUT"]) | fields(now["ENVINPUT2"]), old_fields)
        self.assertEqual(fields(now["ENVINPUT"]) & fields(now["ENVINPUT2"]), set())
        self.assertIn("desc_status=CORROBORATED_not_FACT selftest=%d", now["ENVINPUT2"])
        src = strip_comments(read(MAIN))
        self.assertEqual(src.count('ringlog_printf(&rl, "ENVINPUT '), 1)
        self.assertEqual(src.count('ringlog_printf(&rl, "ENVINPUT2 '), 1)
        self.assertLess(src.index('"ENVINPUT port='), src.index('"ENVINPUT2 index='))
        self.assertLess(src.index('"ENVINPUT2 index='), src.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);"))


if __name__ == "__main__":
    unittest.main()
