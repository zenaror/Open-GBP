"""tests/host/test_e5_breadth002_staging_record.py -- Hardware Issue #161, Part 0: the pin and staging of vehicle-0002 as slot 29-vehicle2, and its record.

Durable, append-only forms (no whole-file equality):
  * tools/swiss-layout.tsv row 29 is exactly the row the hardware Issue gives (the hash of V31.13), its frozen set is the 18 pins of the Issue, and the manifest of BASE (36c69d5)
    is a prefix-preserving ancestor: every row of BASE is still there, unchanged, and the only added row is 29;
  * HARDWARE_TESTS.md: everything from the heading of V32 to the end of V32.11 is found unchanged at BASE, V32.12 exists once, follows V32.11, and carries the staging facts
    (the pin, the export, the card's before / after counts and its one difference, the 18 pins, the stale-log check, the amended tests);
  * the DEVLOG entry exists once; the two HANDOFF paragraphs exist once each, each BEFORE the paragraph of Issue #160 it sits on top of, and neither cites the test-family id;
  * no evidence id was added (EVIDENCE.md has the ids of BASE and none else).
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import guards  # noqa: E402

BASE = "36c69d5305b66131515684d5ba1c243cafca4cec"   # origin/main when Hardware Issue #161's Part 0 was done
HT, EV, DEVLOG, HANDOFF, TSV = "docs/research/HARDWARE_TESTS.md", "docs/research/EVIDENCE.md", "docs/research/DEVLOG.md", "docs/HANDOFF.md", "tools/swiss-layout.tsv"
PIN = "02f89ccd1b07b10165d6d7b4287bf1b056a2a673661c89ad8e5b506fe56c55d8"
ROW29 = ["29", "vehicle2", "gbp-play-gba2", "gbp-play-gba2.dol", "gbp-play-gba2", "vehicle2", "1", PIN]
V32_HEAD = "## V32 — PHASE 7's E5 second breadth session"
V3212 = "### V32.12 The candidate PINNED as `29-vehicle2` and STAGED"
DEVLOG_HEAD = "## 2026-10-05 — Hardware Issue #161: `vehicle-0002` pinned as `29-vehicle2` and staged on the card (Part 0)"
HANDOFF_BLOCKER = "**2026-10-05 (Hardware Issue #161), on top: `vehicle-0002` is PINNED as `29-vehicle2` and STAGED on the SD2SP2 card; no run has happened**"
HANDOFF_NEXT = "**2026-10-05 (Hardware Issue #161), on top: Part 0 of Hardware Issue #161 (the staging) is done"
PREV_BLOCKER = "**2026-10-05 (Issue #160), on top: the next physical Phase 7 session on `vehicle-0002` is PRE-REGISTERED"
PREV_NEXT = "**2026-10-05 (Issue #160), on top: Issue #160 is done"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def base(rel):
    b = guards.show(BASE, rel)
    return b.decode("utf-8") if isinstance(b, bytes) else b


def rows(tsv):
    return [l.split("\t") for l in tsv.split("\n") if l and not l.startswith("#")]


def flat(s):
    return " ".join(s.replace("`", "").replace("**", "").split())


class TheManifest(unittest.TestCase):
    def test_row_29_is_exactly_the_pin_and_only_it_was_added(self):
        now, then = rows(read(TSV)), rows(base(TSV))
        self.assertEqual([r for r in now if r[0] == "29"], [ROW29])
        self.assertEqual([r for r in then if r[0] == "29"], [], "BASE already had a row 29")
        self.assertEqual([r for r in now if r[0] != "29"], then, "a row of BASE moved, changed or went away (nothing is renumbered)")

    def test_the_frozen_set_is_the_issues_eighteen(self):
        frozen = sorted("%s-%s" % (r[0], r[1]) for r in rows(read(TSV)) if r[7] != "-")
        self.assertEqual(len(frozen), 18)
        self.assertEqual(frozen[0], "12-stream")
        self.assertEqual(frozen[-1], "29-vehicle2")
        self.assertIn(PIN, read(HT).split(V32_HEAD, 1)[1])


class TheRecord(unittest.TestCase):
    def test_v32_up_to_v32_11_is_unchanged_and_v32_12_follows_once(self):
        now, then = read(HT), base(HT)
        self.assertEqual(now.count(V3212), 1)
        i_then, i_now = then.index(V32_HEAD), now.index(V32_HEAD)
        self.assertEqual(then[i_then:], now[i_now:i_now + len(then) - i_then], "V32.1-V32.11 (or something before them) was edited")
        self.assertLess(now.index("### V32.11 What this pre-registration does not do"), now.index(V3212))
        self.assertEqual(now.count("### V32.12 "), 1)

    def test_v32_12_carries_the_staging_facts(self):
        t = read(HT)
        d = flat(t[t.index(V3212):])
        for w in (PIN, "512 224 B", "7d2f58f", "Hardware Issue #161", "swiss_export.py --root . --only 29-vehicle2", "never `make swiss`".replace("`", ""),
                  "the ONLY difference is the new line for 29-vehicle2/boot.dol", "30 files before, 31 after", "INDEX.txt untouched (md5 e66e409d1522581f9b878b2e9858636f",
                  "all 18 pinned slots on the card read back equal to their pins", "no file named GBP-PLAY-002* or *vehicle-0002*", "no evidence id is allocated",
                  "test_swiss_export.py", "test_e5_breadth002_prereg.py", "test_play_gba_image.py", "no log was opened or read", "NOT rebuilt here",
                  "29 vehicle2 gbp-play-gba2 gbp-play-gba2.dol gbp-play-gba2 vehicle2 1 " + PIN):
            self.assertIn(w, d, w)

    def test_no_evidence_id_was_added(self):
        ids = lambda s: re.findall(r"^#{2,3} ((?:GBP|ENV)-[A-Z]+-\d{3}) ", s, re.M)
        self.assertEqual(ids(read(EV)), ids(base(EV)))

    def test_the_devlog_entry_exists_once_and_on_the_end(self):
        t = read(DEVLOG)
        self.assertEqual(t.count(DEVLOG_HEAD), 1)
        self.assertTrue(t.startswith(base(DEVLOG)[:2000]))
        d = flat(t[t.index(DEVLOG_HEAD):])
        for w in (PIN, "the card differs from before only by", "30 files before, 31 after", "the 18 pinned slots equal their pins", "no `GBP-PLAY-002*`".replace("`", ""),
                  "Part 1 (the Operator's run) and Part 2", "any log opened"):
            self.assertIn(w, d, w)


class TheHandoff(unittest.TestCase):
    def test_each_paragraph_is_present_once_before_the_one_it_sits_on(self):
        h = read(HANDOFF)
        for new, prev in ((HANDOFF_BLOCKER, PREV_BLOCKER), (HANDOFF_NEXT, PREV_NEXT)):
            self.assertEqual(h.count(new), 1, new)
            self.assertEqual(h.count(prev), 1, prev)
            self.assertLess(h.index(new), h.index(prev))
        i = h.index(HANDOFF_BLOCKER)
        self.assertIn(PIN, h[i:i + 1500])
        self.assertIn("clearance", h[h.index(HANDOFF_NEXT):h.index(HANDOFF_NEXT) + 800])
        self.assertNotIn("BREADTH", h[i:h.index(PREV_BLOCKER)])
        self.assertNotIn("BREADTH", h[h.index(HANDOFF_NEXT):h.index(PREV_NEXT)])

    def test_handoff_only_gained_text(self):
        import difflib
        then, now = base(HANDOFF).splitlines(), read(HANDOFF).splitlines()
        removed = [x for x in difflib.unified_diff(then, now, lineterm="", n=0) if x.startswith("-") and not x.startswith("---")]
        self.assertEqual(removed, [])


if __name__ == "__main__":
    unittest.main()
