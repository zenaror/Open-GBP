"""tests/host/test_u045_window_record.py -- GitHub Issue #116: the record of the re-derivation, against the tool
and against what the record said before it.

Two properties matter and each is checked, not assumed:

  * ON TOP, NEVER REWRITTEN. Every amended entry, heading and section still STARTS with the exact text it had at
    16e9c9f, the commit before #116; the amendment is what follows. A pointer appended to a heading is the only
    change a heading may carry. The frozen pre-registration sections that quote the priors are byte-identical.
  * THE TABLES ARE THE TOOL'S. GBP-HW-339's per-run and per-arm figures are formatted from tools/u045window.py's
    own output, so a record that drifted from the data fails here.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import guards  # noqa: E402
import reconcile  # noqa: E402
from test_u045_window import Derived  # noqa: E402

BASE = "16e9c9f4e317dd231e2d1607cd0a37e7faef30c1"      # origin/main when #116 was opened
EV = "docs/research/EVIDENCE.md"
UN = "docs/research/UNKNOWNS.md"
HT = "docs/research/HARDWARE_TESTS.md"
AUDIO = "docs/protocol/AUDIO.md"
METHOD = "docs/RESEARCH_METHOD.md"
DEVLOG = "docs/research/DEVLOG.md"
TB = 40500000
AMENDED = ("GBP-HW-322", "GBP-HW-324", "GBP-HW-327", "GBP-HW-328", "GBP-HW-329", "GBP-HW-332", "GBP-HW-333",
           "GBP-HW-334", "GBP-HW-335", "GBP-HW-336", "GBP-HW-337", "GBP-HW-338")
POINTED = ("GBP-HW-327", "GBP-HW-332")
MARK = "**RE-DERIVED 2026-09-24 (GitHub Issue #116), on top; nothing above is rewritten"


def now(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def then(path):
    return guards.show(BASE, path).decode("utf-8") if isinstance(guards.show(BASE, path), bytes) \
        else guards.show(BASE, path)


def entry(text, eid):
    m = re.search(r"^#{2,3} %s \S.*$" % re.escape(eid), text, re.M)
    nxt = re.search(r"^#{2,3} (?:GBP|ENV)-[A-Z]+-\d{3} ", text[m.end():], re.M)
    body = text[m.end():m.end() + nxt.start() if nxt else len(text)]
    if nxt:
        body = body[:body.rfind("\n---\n")]
    return m.group(0), body


def section(text, head_re, stop=r"^#{1,3} "):
    m = re.search(head_re, text, re.M)
    n = re.search(stop, text[m.end():], re.M)
    return text[m.start():m.end() + n.start() if n else len(text)]


def rows_append_only(tc, old, new):
    """Every table row of the base page is still there, keyed by its first cell, and each of its cells is a prefix
    of the row's cell now: text is appended inside a cell, never replaced."""
    now_rows = dict((l.split(" | ")[0], l.split(" | ")) for l in new.splitlines() if l.startswith("| "))
    for line in old.splitlines():
        if not line.startswith("| "):
            continue
        cells = line.split(" | ")
        tc.assertIn(cells[0], now_rows, line[:60])
        got = now_rows[cells[0]]
        tc.assertEqual(len(got), len(cells), line[:60])
        for a, b in zip(cells, got):
            tc.assertTrue(b.startswith(a.rstrip(" |")), (cells[0][:40], a[:50]))

class OnTopNeverRewritten(unittest.TestCase):
    def test_every_amended_entry_keeps_its_text_and_ends_with_the_amendment(self):
        old, new = then(EV), now(EV)
        for eid in AMENDED:
            h0, b0 = entry(old, eid)
            h1, b1 = entry(new, eid)
            self.assertTrue(h1.startswith(h0), eid)
            self.assertEqual(h1 == h0, eid not in POINTED, eid)
            self.assertTrue(b1.startswith(b0.rstrip("\n")), "%s: the text above the amendment changed" % eid)
            tail = b1[len(b0.rstrip("\n")):]
            self.assertEqual(tail.count(MARK), 1, eid)
            self.assertIn("GBP-HW-339", tail, eid)

    def test_the_pointers_are_the_last_bold_segment_and_carry_the_issue(self):
        for eid in POINTED:
            h, _b = entry(now(EV), eid)
            last = re.findall(r"\*\*[^*]+\*\*", h)[-1]
            self.assertIn("2026-09-24, Issue #116", last, eid)
            self.assertIn("the statuses stand", last, eid)
            self.assertEqual(reconcile.heading_pointer(h), last.strip("* ").strip(), eid)

    def test_no_other_entry_was_rewritten(self):
        """Every entry that existed at the base is still there, in order, and still STARTS with its base text;
        later Issues may append to any of them and add entries after GBP-HW-339."""
        old, new = then(EV), now(EV)
        ids = re.findall(r"^#{2,3} ((?:GBP|ENV)-[A-Z]+-\d{3}) ", old, re.M)
        self.assertGreater(len(ids), 400)                                     # both heading levels are guarded
        for eid in ids:
            if eid in AMENDED:
                continue
            h0, b0 = entry(old, eid)
            h1, b1 = entry(new, eid)
            self.assertTrue(h1.startswith(h0) and b1.startswith(b0.rstrip("\n")), eid)
        new_ids = re.findall(r"^#{2,3} ((?:GBP|ENV)-[A-Z]+-\d{3}) ", new, re.M)
        self.assertEqual(new_ids[:len(ids) + 1], ids + ["GBP-HW-339"])

    def test_U_GBP_045_heading_and_body(self):
        old, new = then(UN), now(UN)
        h0 = re.search(r"^## U-GBP-045 .*$", old, re.M).group(0)
        h1 = re.search(r"^## U-GBP-045 .*$", new, re.M).group(0)
        self.assertTrue(h1.startswith(h0))
        self.assertIn("Issue #116", re.findall(r"\*\*[^*]+\*\*", h1)[-1])
        s0 = section(old, r"^## U-GBP-045 ")
        s1 = section(new, r"^## U-GBP-045 ")
        self.assertTrue(s1[len(h1):].startswith(s0[len(h0):].rstrip("\n")))
        self.assertIn("**RE-DERIVED 2026-09-24 (GitHub Issue #116), on top; nothing above is rewritten.**", s1)
        for uid in re.findall(r"^## (U-GBP-\d{3}) ", old, re.M):                # every other item: append-only,
            if uid == "U-GBP-045":                                              # heading and body separately
                continue
            a, b = section(old, r"^## %s " % uid, r"^## U-GBP-\d{3} "), section(new, r"^## %s " % uid, r"^## U-GBP-\d{3} ")
            ha, hb = a.split("\n", 1)[0], b.split("\n", 1)[0]
            self.assertTrue(hb.startswith(ha), uid)
            self.assertTrue(b[len(hb):].startswith(a[len(ha):].rstrip("\n")), uid)

    def test_the_run_sections_gain_a_final_subsection_and_nothing_else(self):
        old, new = then(HT), now(HT)
        for sec, num in (("V22.12", "V22.12.10"), ("V23.13", "V23.13.10"), ("V24.10", "V24.10.10"),
                         ("V25.12", "V25.12.9"), ("V26.11", "V26.11.8")):
            s0 = section(old, r"^### %s " % re.escape(sec))
            s1 = section(new, r"^### %s " % re.escape(sec))
            self.assertTrue(s1.startswith(s0.rstrip("\n")), sec)
            added = s1[len(s0.rstrip("\n")):]
            heads = re.findall(r"^#### (\S+) ", added, re.M)
            self.assertEqual(heads[0], num, sec)                             # later Issues append after it
            self.assertIn("RE-DERIVED 2026-09-24 (GitHub Issue #116), on top", added, sec)
            self.assertIn("no verdict is re-judged", added, sec)

    def test_the_frozen_priors_are_not_edited(self):
        old, new = then(HT), now(HT)
        for head in (r"^### V25\.2 ", r"^### V25\.8 ", r"^### V24\.3 ", r"^### V24\.0 ", r"^#### The observer gate$"):
            self.assertEqual(section(new, head), section(old, head), head)


class TheTablesAreTheTools(unittest.TestCase):
    def test_GBP_HW_339_per_run(self):
        _h, b = entry(now(EV), "GBP-HW-339")
        ps = Derived.get()["d"]["per_second"]

        def blocks(n):
            return ("%d" % n) if n < 1000 else "%d %03d" % (n // 1000, n % 1000)

        for n, r in sorted(ps.items()):
            w, o, i, o53 = r["whole"]["blocks"], r["outside"]["blocks"], r["inside"]["blocks"], \
                r["outside_without_s30"]["blocks"]
            dec = 2 if n < 41 else 3
            row = re.search(r"^RUN %d +(.*)$" % n, b, re.M).group(1)
            cells = ["%s = %s/s" % (c, r) for c, r in re.findall(r"(\d{1,3}(?: \d{3})?) = +([\d.]+)/s", row)]
            self.assertEqual(cells, ["%s = %.*f/s" % (blocks(w), dec, w / 64.0),
                                     "%s = %.*f/s" % (blocks(o), dec, o / 54.0),
                                     "%s = %.1f/s" % (blocks(i), i / 10.0),
                                     "%s = %.*f/s" % (blocks(o53), dec, o53 / 53.0)], n)

    def test_GBP_HW_339_per_arm(self):
        _h, b = entry(now(EV), "GBP-HW-339")
        a = Derived.get()["d"]["arms"]
        for label, v in (("all (published)", "all"), ("outside", "outside"), ("inside", "inside")):
            h, f, s = a[v]["half"], a[v]["full"], a[v]["S"]
            row = re.search(r"^%s +(.*)$" % re.escape(label), b, re.M).group(1).split()
            nums = " ".join(row).replace("1 015", "1015").replace("1 014", "1014")
            self.assertEqual(nums.split(), ["%d" % h["cycles"], "%d" % h["loss_gaps"],
                                            "%.4f" % (h["loss_gaps"] / float(h["cycles"])),
                                            "%.2f" % (h["sum_k"] * TB / float(h["cycle_ticks"])),
                                            "%d" % f["cycles"], "%d" % f["loss_gaps"],
                                            "%.4f" % (f["loss_gaps"] / float(f["cycles"])),
                                            "%.2f" % (f["sum_k"] * TB / float(f["cycle_ticks"])),
                                            "%.3f" % s["ratio"], "%.3f-%.3f" % tuple(s["ci90"])], v)

    def test_the_amendments_quote_the_tools_figures(self):
        ev = now(EV)
        for eid, toks in (("GBP-HW-332", ("0.270", "0.235-0.308", "0.1981", "2.74", "1.07", "69–77 %")),
                          ("GBP-HW-335", ("5.926", "6.50", "7.51")),
                          ("GBP-HW-337", ("5.537", "16.6")),
                          ("GBP-HW-333", ("17.83", "`produce` 711, `neither` 84, `process` 0, of 795")),
                          ("GBP-HW-329", ("`produce` 1 057, `neither` 141 of 1 198", "1 078 of 1 198 (90 %)")),
                          ("GBP-HW-334", ("`produce` 153 (91 %), `neither` 16 of 169",
                                          "`produce` 556 (89 %), `neither` 68 of 624"))):
            _h, b = entry(ev, eid)
            for tok in toks:
                self.assertIn(tok, b, (eid, tok))


class TheStatusesDidNotMove(unittest.TestCase):
    def test_GBP_HW_339s_statuses(self):
        h, b = entry(now(EV), "GBP-HW-339")
        self.assertIn("— FACT (recomputable counts", h)
        self.assertIn("that the kept `process` steps ARE L2's CRC is CORROBORATED", h)
        self.assertIn("no status of an earlier entry moves", h)
        self.assertIn("That the CRC causes the rise stays a HYPOTHESIS (`GBP-HW-338`).", b)

    def test_the_heading_statuses_of_the_amended_entries_are_the_old_ones(self):
        old, new = then(EV), now(EV)
        for eid in AMENDED:
            h0, _ = entry(old, eid)
            h1, _ = entry(new, eid)
            self.assertEqual(h1[:len(h0)], h0, eid)


class TheRuleAndTheOtherPlaces(unittest.TestCase):
    def test_the_rule_where_instruments_are_designed(self):
        m = now(METHOD)
        sec = section(m, r"^### An instrument that runs during part of a measurement window has a cost inside that "
                         r"window \(2026-09-24, GitHub Issue #116\)$")
        flat = " ".join(sec.split())
        for tok in ("Either measure the cost and report it separately, or do not run the instrument during the "
                    "measurement.",
                    "A figure integrated over a window that contains the instrument is a figure about the "
                    "instrument and the subject together.",
                    "Report every rate three ways: over the whole window, outside the instrument's span, and "
                    "inside it.",
                    "A balanced or interleaved design does not excuse this."):
            self.assertIn(tok, flat, tok)
        self.assertLess(m.index("## Trace-driven testing"), m.index(sec), "under Trace-driven testing")
        self.assertLess(m.index(sec), m.index("## Hardware test requests"))

    def test_the_protocol_page(self):
        a = now(AUDIO)
        self.assertIn("**2026-09-24, Issue #116, restated on top:**", a)
        self.assertIn("the ratio is **0.270** (90 % CI 0.235–0.308), a 69–77 % reduction", a)
        self.assertIn("**2026-09-24, Issue #116:** 0.60 % outside the 10 s L2 window, 0.74 % inside it, `GBP-HW-339`", a)
        self.assertIn("second (24.50 outside the L2 instrument's window, `GBP-HW-339`)", a)
        old = then(AUDIO)
        self.assertIn("(90 % CI 0.306–0.379), a 62–69 % reduction", a)          # the published figure stays
        # ONE declared insertion: #116's note on "The live chain, run once" sits INSIDE the cell's parenthesis, not at
        # its end, so that row is checked with the note removed; every other row is cell-wise append-only.
        key = "| The live chain, run once"
        note = "; **2026-09-24, Issue #116:** 0.60 % outside the 10 s L2 window, 0.74 % inside it, `GBP-HW-339`"
        row = [l for l in a.splitlines() if l.startswith(key)][0]
        self.assertIn(note, row)
        rows_append_only(self, old, a.replace(row, row.replace(note, "")))

    def test_the_header_comment(self):
        h = now("src/audio/gbp_aplay.h")
        self.assertIn(" * RESTATED 2026-09-24 (GitHub Issue #116), a comment only:", h)
        self.assertIn("8-push calls lost 0.341 of the 16-push calls' loss gaps per AI cycle (GBP-HW-332)", h)  # kept
        self.assertLess(h.index("8-push calls lost 0.341"), h.index(" * RESTATED 2026-09-24 (GitHub Issue #116)"))
        self.assertRegex(h, r"#define GBP_APLAY_STEP_PUSHES\s+8u")

    def test_the_devlog(self):
        d = now(DEVLOG)
        self.assertIn("## 2026-09-24 — Issue #116: the live family's AUDIO loss rates re-derived without L2's "
                      "window", d)
        self.assertTrue(then(DEVLOG).rstrip("\n") in d and d.startswith(then(DEVLOG).rstrip("\n")))


if __name__ == "__main__":
    unittest.main()
