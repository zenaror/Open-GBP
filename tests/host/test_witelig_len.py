"""
tests/host/test_witelig_len.py — the PERMANENT line-length guard for the
witness-eligibility reporting records (HARDWARE_TESTS §V5.58, GBP-VID-033).

WHY THIS EXISTS. stream-0010 emitted ONE `WITELIG` record. The ringlog stores
each record in LOG_LINE_LEN = 256 bytes after a 7-character `%06u ` prefix, so
the payload is at most 248 characters. Runs 9 and 10 each clipped that record
after `qual_streak_at_e`, losing `qual_streak_at_eligible=0`. The value was
recoverable from counters, but the field was not there.

WHAT THIS PROVES. Not that today's small physical values fit -- that the
records fit at the WORST-CASE rendered width of every conversion specifier for
this target's C types (powerpc-eabi, ILP32: long is 32-bit, long long 64-bit).
If someone adds a field, changes a specifier, or a value grows, the guard
fails before the hardware does.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAIN = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c")

LOG_LINE_LEN = 256          # main.c
PREFIX_LEN = 7              # ringlog.c: snprintf(line, line_len, "%06u ", seq)
PAYLOAD_MAX = LOG_LINE_LEN - PREFIX_LEN - 1   # 248: the NUL takes the last byte

# worst-case rendered width per conversion, for powerpc-eabi (ILP32)
WIDTH = {
    "lu": 10,   # 4294967295
    "ld": 11,   # -2147483648
    "u": 10,
    "d": 11,
    "llu": 20,  # 18446744073709551615
    "lld": 20,
    "llx": 16,  # ffffffffffffffff
    "lx": 8,
    "x": 8,
}
SPEC = re.compile(r"%(?:(\d+)\$)?([-+ #0]*)(\d+)?(?:\.(\d+))?(hh|h|ll|l|z|t|j)?([diouxXeEfgGcsp%])")

REQUIRED = {
    "WITELIG": ("policy=time_not_before", "origin=control", "not_before_ms=", "gated_at_init=1",
                "released=", "still_gated=", "t_eligible=", "ticks_control_to_eligible="),
    "WITELIG2": ("frames_seen_before_eligible=", "disqualified_before_eligible=",
                 "qual_streak_at_eligible=0"),
}


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"//[^\n]*", " ", src)


def format_string(src, tag):
    """The concatenated C string literal passed to ringlog_printf for `tag`."""
    i = src.index('ringlog_printf(&rl, "%s ' % tag)
    j = src.index(",", src.index('"', i + len("ringlog_printf(&rl, ")))
    # the format argument runs from the first quote to the comma that ends it,
    # possibly spanning adjacent literals
    seg = src[i:j]
    return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', seg))


def worst_case_width(fmt):
    """Length of `fmt` with every conversion replaced by its maximum width."""
    total = 0
    pos = 0
    for m in SPEC.finditer(fmt):
        total += m.start() - pos
        pos = m.end()
        length, conv, width = m.group(5) or "", m.group(6), m.group(3)
        if conv == "%":
            total += 1
            continue
        key = length + conv
        if conv in "sp" or conv in "eEfgGaA":
            raise AssertionError("%r has no bounded worst case; do not use it here" % m.group(0))
        w = WIDTH[key]
        if width and width.isdigit():
            w = max(w, int(width))
        total += w
    total += len(fmt) - pos
    return total


class BothRecordsFitAtWorstCase(unittest.TestCase):
    def setUp(self):
        self.src = strip_comments(open(MAIN).read())

    def test_the_ringlog_geometry_this_guard_assumes_is_the_one_in_source(self):
        self.assertIn("#define LOG_LINE_LEN 256", open(MAIN).read())
        rl = open(os.path.join(ROOT, "src", "log", "ringlog.c")).read()
        self.assertIn('"%06u "', rl)
        self.assertEqual(PAYLOAD_MAX, 248)

    def test_witelig_fits_at_worst_case(self):
        fmt = format_string(self.src, "WITELIG")
        w = worst_case_width(fmt)
        self.assertLessEqual(w, PAYLOAD_MAX, "WITELIG worst case %d > %d" % (w, PAYLOAD_MAX))

    def test_witelig2_fits_at_worst_case(self):
        fmt = format_string(self.src, "WITELIG2")
        w = worst_case_width(fmt)
        self.assertLessEqual(w, PAYLOAD_MAX, "WITELIG2 worst case %d > %d" % (w, PAYLOAD_MAX))

    def test_the_old_single_record_would_not_have_fit(self):
        """The guard must be able to FAIL: the stream-0010 format, reassembled,
        exceeds the payload at worst case -- and did so physically."""
        old = (format_string(self.src, "WITELIG") + " " +
               format_string(self.src, "WITELIG2")[len("WITELIG2 "):])
        self.assertGreater(worst_case_width(old), PAYLOAD_MAX)

    def test_every_required_field_is_present_and_the_tags_are_unique(self):
        for tag, fields in REQUIRED.items():
            fmt = format_string(self.src, tag)
            for f in fields:
                self.assertIn(f, fmt, "%s lacks %s" % (tag, f))
            self.assertEqual(self.src.count('ringlog_printf(&rl, "%s ' % tag), 1, tag)
        self.assertNotIn('"WITELIG2 policy', self.src)

    def test_no_field_of_the_stream_0010_contract_disappeared(self):
        all_fields = REQUIRED["WITELIG"] + REQUIRED["WITELIG2"]
        both = format_string(self.src, "WITELIG") + format_string(self.src, "WITELIG2")
        for f in all_fields:
            self.assertIn(f, both)
        self.assertEqual(len(all_fields), 11)

    def test_both_records_are_emitted_after_the_probe_returns_and_after_witqual(self):
        s = self.src
        probe = s.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);")
        self.assertLess(probe, s.index('"WITQUAL policy='))
        self.assertLess(s.index('"WITQUAL policy='), s.index('"WITELIG policy='))
        self.assertLess(s.index('"WITELIG policy='), s.index('"WITELIG2 '))
        # and never inside the capture hot path
        for fn in ("pump", "submit_ready", "on_draw_done"):
            m = re.search(r"^static [^\n;]*\b%s\s*\(" % fn, s, re.M)
            body_start = s.index("{", m.start())
            d, j = 0, body_start
            while True:
                d += s[j] == "{"
                d -= s[j] == "}"
                if d == 0:
                    break
                j += 1
            self.assertNotIn("WITELIG", s[body_start:j])


if __name__ == "__main__":
    unittest.main()
