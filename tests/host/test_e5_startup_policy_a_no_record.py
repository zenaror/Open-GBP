"""tests/host/test_e5_startup_policy_a_no_record.py -- GitHub Issue #157 (forward only, after Issue #156): the startup profile and Policy A of RUN 61 / RUN 62 / RUN 63.

HARDWARE_TESTS.md V31.6 and V31.8 listed "the startup profile" and "Policy A" among the records the vehicle keeps; V31.10 recorded them "owed, not passed". V31.12 and GBP-HW-384
settle the debt as NOT READABLE IN THESE LOGS: the vehicle's log carries no record of either. What is held here, each checked, not assumed:

  * THE ARCHIVE is the recorded one (sha256 pinned; a mismatch is a defect, never a skip).
  * THE CENSUS: the counter is validated before it is believed -- the record lines equal the header's `lines=` in every log, the same counter finds the records in a synthetic line
    and in the archived logs of the images that had the gates (play-0001, GBP-AUDIO RUN 41 / 43 / 44), and does NOT count `PLAYSTARTUP` (the play image's own record) as `STARTUP`.
    On the three vehicle logs it reads 0.
  * THE SOURCE CHECK over every file the vehicle links (the Makefile's SRCS, resolved through its own search path, and every header they include) at 6396851 and at the BASE:
    0 format strings for the five tags or OGBPDISP / OGBPDISP2; the same scanner finds the formats in the audio images' sources (its positive control).
  * THE RECORDS: V31.6, V31.8, V31.10, GBP-HW-382 and GBP-HW-383 of the BASE are found now block by block, each body starting with its body of then (both heading levels; V31.10's
    table cell by cell, a cell may only grow); V31.12 and GBP-HW-384 exist once each, start their blocks and follow the base's last section / id; V31.12 says NOT READABLE IN THESE LOGS
    and never says the two gates passed; the HANDOFF and the DEVLOG carry the state.
The archive is under captures/local (ignored by Git): those tests skip, with the registered reason, on a host without it. The reader's own line is tested in test_playread.py.
"""
import hashlib
import os
import posixpath
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import guards  # noqa: E402

BASE = "f98a11bf033193e15b9bd0202f7a8650a25598e2"       # origin/main when #157 was dispatched (Issue #156 pushed)
BUILD = "6396851dbf8ce22e364aba62613ad4ed71ac6bb4"      # the commit vehicle-0001 was built at (HARDWARE_TESTS.md V31.8)
LOCAL = os.path.join(ROOT, "captures", "local")
HT, EV, DEVLOG, HANDOFF = "docs/research/HARDWARE_TESTS.md", "docs/research/EVIDENCE.md", "docs/research/DEVLOG.md", "docs/HANDOFF.md"
VEHICLE = {61: ("GBP-PLAY-002_vehicle-0001-run61.log", "9a8120351db9e129620d53708f190ba3acfdfd0cd23179452f09d775f67ce0cd", 1971),
           62: ("GBP-PLAY-002_vehicle-0001-run62.log", "56575eb5e1573daa25f63574193fc7953c93debe6cde35e3bff7410fb9594b33", 1963),
           63: ("GBP-PLAY-002_vehicle-0001-run63.log", "ddc8381e144072ede3d477c3fadcc262aba4af590594ddf4b1ebea9a212267f2", 1737)}
CONTROLS = ("GBP-PLAY-001_play-0001-run21.log", "GBP-PLAY-001_play-0001-run22.log", "GBP-PLAY-001_play-0001-run25.log", "GBP-PLAY-001_play-0001-run26.log",
            "GBP-AUDIO-010_game-0001-run41.log", "GBP-AUDIO-012_sync-0001-run43.log", "GBP-AUDIO-013_stream-0016-run44.log")
TAGS = ("STARTUP", "STARTUPT", "STARTUPV", "STREAMINV", "DISPSRC")
SEC = "### V31.12 The startup profile and Policy A of RUN 61 / RUN 62 / RUN 63: NOT READABLE IN THESE LOGS"
EV_HEAD = r"^#{2,3} ((?:GBP|ENV)-[A-Z]+-\d{3}) .*$"
NO_SKIP_NO_ARCHIVE = "no local archive on this host (captures/local is ignored)"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def base(rel):
    b = guards.show(BASE, rel)
    return b.decode("utf-8") if isinstance(b, bytes) else b


def flat(s):
    return " ".join(s.replace("`", "").replace("**", "").split())


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# THE COUNTER (the census). Its commands in V31.12 are the grep equivalents of these.
# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def census(text):
    header = int(re.search(r"^lines=(\d+) ", text, re.M).group(1))
    tags = re.findall(r"^\d{6} (\S+)", text, re.M)
    return {"header": header, "records": len(tags), "tag_hits": [t for t in tags if t in TAGS],
            "word_lines": len([l for l in text.split("\n") if re.search(r"\b(STARTUP|STARTUPT|STARTUPV|STREAMINV|DISPSRC|OGBPDISP2)\b", l)]),
            "substring_lines": [l for l in text.split("\n") if re.search(r"STARTUP|STREAMINV|DISPSRC|OGBPDISP", l)], "distinct": len(set(tags))}


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# THE SOURCE SCANNER: every file a Makefile links, resolved the way the Makefile does, at a commit.
# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
SRC_DIRS = ["src/common", "src/log", "src/gbp", "src/audio", "src/platform"]
FORMAT = re.compile(r'"(?:STARTUP|STARTUPT|STARTUPV|STREAMINV|DISPSRC|OGBPDISP2?)(?:[ "\\%])')
BARE = re.compile(r"STREAMINV|DISPSRC|OGBPDISP|\bSTARTUPT\b|\bSTARTUPV\b")


def tag_of(line):
    """The record name a format string on `line` begins with."""
    return re.sub(r'^"|[ "\\%]$', "", FORMAT.search(line).group(0))


def tree(commit):
    out = subprocess.run(["git", "-C", ROOT, "ls-tree", "-r", "--name-only", commit, "src", "poc"], capture_output=True, text=True, check=True).stdout
    return set(out.split("\n"))


def resolve_include(including, header, dirs, files_in_tree):
    """The way the compiler resolves `#include "header"`: first relative to the including file's own directory (so "../gbp/x.h" works), then in each -I directory; normalised."""
    for base_dir in [posixpath.dirname(including)] + list(dirs):
        p = posixpath.normpath(posixpath.join(base_dir, header))
        if p in files_in_tree:
            return p
    return None


def scan(commit, poc):
    """(sources, files, format hits, bare lines) over the files poc/<poc>/Makefile links at `commit`."""
    files_in_tree = tree(commit)
    mk = guards.show(commit, "poc/%s/Makefile" % poc)
    srcs = re.search(r"^SRCS := (.*(?:\\\n.*)*)", mk, re.M).group(1).replace("\\\n", " ").split()
    dirs = ["poc/%s/source" % poc] + SRC_DIRS
    files, queue = {}, []
    for s in srcs:
        hit = [d + "/" + s for d in dirs if d + "/" + s in files_in_tree]
        assert hit, "%s: %s resolves nowhere" % (poc, s)
        files[hit[0]] = guards.show(commit, hit[0])
        queue.append(hit[0])
    while queue:
        f = queue.pop()
        for h in re.findall(r'^#\s*include\s+"([^"]+)"', files[f], re.M):
            p = resolve_include(f, h, dirs, files_in_tree)
            assert p is not None, "%s: #include \"%s\" resolves nowhere -- a header the closure would silently miss (the closure must not drop what it cannot find)" % (f, h)
            if p not in files:
                files[p] = guards.show(commit, p)
                queue.append(p)
    hits = [(f, i + 1) for f, t in sorted(files.items()) for i, l in enumerate(t.split("\n")) if FORMAT.search(l)]
    bare = [(f, i + 1) for f, t in sorted(files.items()) for i, l in enumerate(t.split("\n")) if BARE.search(l)]
    return srcs, files, hits, bare


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
class TheCounterIsValidatedBeforeItIsBelieved(unittest.TestCase):
    """A zero that cannot be otherwise is not a finding: the counter must be shown to find the records it looks for."""

    def synthetic(self, extra):
        lines = ["IDENT test=X", "PLAYSTARTUP t_dma=1 k=64 ring_at_dma=4097 ready_at_dma=1"] + extra
        body = "\n".join("%06d %s" % (i, l) for i, l in enumerate(lines))
        return "# OPENGBP-LOG v1\nlines=%d dropped=0 truncated=0\n%s\n# --- end ---\n" % (len(lines), body)

    def test_it_finds_each_tag_in_a_synthetic_log_and_reads_the_header_against_the_records(self):
        extra = ["STARTUP mode=normal selftest_run=1", "STARTUPT tb_hz=1", "STARTUPV have_first=1", "STREAMINV checks=1 failures=0", "DISPSRC handoffs=1"]
        c = census(self.synthetic(extra))
        self.assertEqual(c["tag_hits"], list(TAGS))
        self.assertEqual((c["header"], c["records"]), (7, 7))
        self.assertEqual(c["word_lines"], 5)

    def test_playstartup_is_not_a_startup_record_and_the_bare_substring_does_see_it(self):
        c = census(self.synthetic([]))
        self.assertEqual(c["tag_hits"], [])
        self.assertEqual(c["word_lines"], 0)
        self.assertEqual(len(c["substring_lines"]), 1)
        self.assertIn(" PLAYSTARTUP ", c["substring_lines"][0])

    def test_a_header_that_disagrees_with_the_records_is_visible(self):
        t = self.synthetic(["STARTUP mode=normal"]).replace("lines=3", "lines=9")
        c = census(t)
        self.assertNotEqual(c["header"], c["records"])

    def test_the_sidecar_name_is_found_as_a_whole_word(self):
        self.assertEqual(census(self.synthetic(["NOTE OGBPDISP2 sidecar written"]))["word_lines"], 1)


class TheArchivedLogsReadAsRecorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = {r: os.path.join(LOCAL, f) for r, (f, _h, _n) in VEHICLE.items()}
        if not all(os.path.isfile(p) for p in cls.paths.values()):
            raise unittest.SkipTest("no local archive on this host (captures/local is ignored)")
        for r, p in cls.paths.items():
            assert sha(p) == VEHICLE[r][1], "captures/local's RUN %d archive is not the recorded one (a defect in the archive, never a skip)" % r
        cls.text = {}
        for r, p in cls.paths.items():
            with open(p, encoding="utf-8", errors="replace") as f:
                cls.text[r] = f.read()

    def test_the_census_of_the_three_vehicle_logs(self):
        for r, t in self.text.items():
            c = census(t)
            self.assertEqual((c["header"], c["records"]), (VEHICLE[r][2],) * 2, "RUN %d: the counter must see every record the header says" % r)
            self.assertEqual(c["tag_hits"], [], r)
            self.assertEqual(c["word_lines"], 0, r)
            self.assertEqual(c["distinct"], 98, r)
            self.assertEqual(len(c["substring_lines"]), 1, r)
            self.assertRegex(c["substring_lines"][0], r"^\d{6} PLAYSTARTUP t_dma=[0-9a-f]+ k=64 ring_at_dma=4097 ready_at_dma=1$")

    def test_the_vehicle_writes_no_sidecar(self):
        mine = sorted(f for f in os.listdir(LOCAL) if f.startswith("GBP-PLAY-002_vehicle-0001"))
        self.assertEqual(mine, sorted(v[0] for v in VEHICLE.values()), "captures/local holds only the three .log files of this build id: no OGBPDISP2 sidecar")

    def test_the_positive_controls_find_four_of_the_five_tags_in_every_archived_log_that_had_the_gates(self):
        paths = [os.path.join(LOCAL, f) for f in CONTROLS]
        if not all(os.path.isfile(p) for p in paths):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        for p in paths:
            with open(p, encoding="utf-8", errors="replace") as f:
                c = census(f.read())
            self.assertEqual(c["header"], c["records"], p)
            self.assertEqual(sorted(c["tag_hits"]), ["STARTUP", "STARTUPT", "STARTUPV", "STREAMINV"], p)
            self.assertEqual(c["word_lines"], 4, p)

    def test_the_section_quotes_the_census_integers(self):
        s = flat(section(read(HT), SEC))
        for r, (f, _h, n) in VEHICLE.items():
            self.assertIn(flat("%s %d %d 0 0 1" % (f, n, n)), s, f)
        for f in CONTROLS:
            self.assertIn(f, s, f)


def section(text, head):
    i = text.index(head)
    j = text.find("\n### ", i + 1)
    return text[i:j if j > 0 else len(text)]


class TheSourceCheck(unittest.TestCase):
    def test_the_vehicles_files_carry_no_format_string_at_the_build_and_at_the_base(self):
        for c in (BUILD, BASE):
            if not guards.base_available(c):
                self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % c)
        scans = {c: scan(c, "gbp-play-gba") for c in (BUILD, BASE)}
        for c, (srcs, files, hits, bare) in scans.items():
            self.assertEqual((len(srcs), len(files)), (35, 79), c)
            self.assertEqual(hits, [], "a format string for a startup-profile / Policy A record in what the vehicle links (the stop rule of Issue #157): %s" % c)
            self.assertEqual(bare, [("src/gbp/gbp_input.h", 295), ("src/gbp/gbp_vqueue.h", 251)], c)
            self.assertNotIn("src/gbp/gbp_vdisp.c", files)
            self.assertNotIn("gbp_vdisp.c", srcs)
        self.assertEqual(scans[BUILD][1], scans[BASE][1], "the 79 files are byte-identical at the build commit and at the base")
        for p in ("src/gbp/gbp_input.h", "src/gbp/gbp_vqueue.h"):
            line = scans[BASE][1][p].split("\n")[294 if "input" in p else 250].lstrip()
            self.assertTrue(line.startswith("*") or line.startswith("/*") or line.startswith("//"), "the mention is in a comment: %s" % line)

    def test_a_header_reached_only_by_a_parent_directory_include_is_in_the_closure(self):
        """Positive control by the include path: src/platform/hsp_backend_irq.c includes "../gbp/gbp_irq_oneshot.h", which resolves only relative to the including file. The first version
        of the scanner resolved against the -I directories alone, dropped it without a word and counted 78 files; the closure is 79 (35 .c + 44 headers)."""
        if not guards.base_available(BASE):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE)
        files_in_tree = tree(BASE)
        dirs = ["poc/gbp-play-gba/source"] + SRC_DIRS
        self.assertIn('#include "../gbp/gbp_irq_oneshot.h"', guards.show(BASE, "src/platform/hsp_backend_irq.c"))
        self.assertEqual(resolve_include("src/platform/hsp_backend_irq.c", "../gbp/gbp_irq_oneshot.h", dirs, files_in_tree), "src/gbp/gbp_irq_oneshot.h")
        self.assertIsNone(resolve_include("src/platform/hsp_backend_irq.c", "../gbp/gbp_irq_oneshot.h", dirs, set(files_in_tree) - {"src/gbp/gbp_irq_oneshot.h"}),
                          "a header that is not in the tree resolves to None (scan() asserts on that instead of dropping it)")
        # the old rule joined the directory and the name WITHOUT normalising: that path is not in the tree, which is what hid the header
        self.assertNotIn("src/platform/../gbp/gbp_irq_oneshot.h", files_in_tree)
        self.assertIsNone(resolve_include("src/platform/x.c", "no_such_header_anywhere.h", dirs, files_in_tree), "an include that resolves nowhere is reported as None, and scan() asserts on it")
        _srcs, files, _hits, _bare = scan(BASE, "gbp-play-gba")
        self.assertIn("src/gbp/gbp_irq_oneshot.h", files)
        self.assertIn("src/platform/hsp_backend_irq.c", files)
        self.assertEqual(len([f for f in files if f.endswith(".h")]), 44)
        self.assertEqual(len(files), 79)

    def test_the_vehicles_parent_and_the_vehicle_itself_hold_no_format_string(self):
        if not guards.base_available(BASE):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE)
        for path in ("poc/gbp-audio-v28/source/main.c", "poc/gbp-play-gba/source/main.c"):
            for i, l in enumerate(guards.show(BASE, path).split("\n")):
                self.assertIsNone(FORMAT.search(l), "%s:%d" % (path, i + 1))

    def test_the_same_scanner_finds_the_formats_in_the_audio_images_sources_its_positive_control(self):
        if not guards.base_available(BASE):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE)
        for poc in ("gbp-audio-game", "gbp-audio-live", "gbp-audio-split"):
            _s, files, hits, _b = scan(BASE, poc)
            kinds = sorted(set(tag_of(files[f].split("\n")[ln - 1]) for f, ln in hits))
            self.assertEqual(kinds, ["STARTUP", "STARTUPT", "STARTUPV", "STREAMINV"], poc)
        _s, files, hits, _b = scan(BASE, "gbp-video-stream-probe")
        self.assertIn("DISPSRC", set(tag_of(files[f].split("\n")[ln - 1]) for f, ln in hits), "DISPSRC's format is in the video-stream probe's sources")

    def test_the_code_the_section_cites_is_where_it_says(self):
        if not guards.base_available(BASE):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE)
        mc = guards.show(BASE, "poc/gbp-play-gba/source/main.c").split("\n")
        self.assertEqual(mc[969].strip(), "gbp_startup_profile(&startup, GBP_STARTUP_MODE);")
        self.assertEqual(mc[171].strip(), "#ifndef GBP_STARTUP_MODE")
        self.assertEqual(mc[172].strip(), "#define GBP_STARTUP_MODE GBP_STARTUP_NORMAL")
        self.assertEqual(mc[827].strip(), "static void submit_ready(int buf, struct gbp_vqueue *account)")
        self.assertEqual(mc[873].strip(), "static void offer_oldest_ready(void)")
        self.assertIn("xfb = gbp_vpresent_xfb_target(&present, cur);", "\n".join(mc[827:872]))
        mk = guards.show(BASE, "poc/gbp-play-gba/Makefile").split("\n")
        self.assertEqual(mk[25].strip(), "STARTUP_MODE ?= GBP_STARTUP_NORMAL")
        self.assertEqual(mk[53].strip(), "-DGBP_STARTUP_MODE=$(STARTUP_MODE)")
        root = guards.show(BASE, "Makefile")
        vehicle = root[root.index("\nvehicle:\n"):root.index("\nvehicle-dolphin:")]
        self.assertNotIn("STARTUP_MODE", vehicle, "the root vehicle target passes no STARTUP_MODE")
        gs = guards.show(BASE, "poc/gbp-play-gba/source/main.c")
        self.assertIn('"OPENGBP-PLAY SELFTEST ok=%d', gs)
        self.assertIn("gecko_puts(line);", gs)
        self.assertTrue(mc[1026].strip().startswith("snprintf(line, sizeof line,"))                                  # the summary is formatted at :1027-1032 ...
        self.assertEqual(mc[1032].strip(), "gecko_puts(line);")                                                    # ... and sent to the Gecko only, at :1033
        self.assertIn('printf("  SELF-TEST display path: %s', mc[1033])                                           # the reduced verdict: the screen (:1034-1035)
        self.assertIn('selftest_ok ? "ok" : "NOT OK"', mc[1034])
        self.assertIn("selftest_ok = (selftest_converted && selftest_released && selftest_sci_clean &&", mc[350])   # :351-355 -- ok needs sci_clean ...
        self.assertIn("gbp_vpresent_invariant_failures(&present) == 0u) ? 1 : 0;", mc[354])                      # ... and inv_fail == 0
        self.assertIn("in_selftest_ok = gbp_input_selftest();", mc[1035])
        self.assertIn('"INPUT selftest=%d steps=', mc[1144])                                                     # :1145 -- the INPUT path's self-test record
        self.assertNotIn("ringlog_printf", "".join(mc[1033:1037]), "neither self-test line of the display path goes to the SD log")


class TheEarlierRecordsAreOnTopUnchanged(unittest.TestCase):
    def blocks(self, text):
        heads = list(re.finditer(r"^#{1,4} .*$", text, re.M))
        out = [("", text[:heads[0].start()] if heads else text)]
        for i, m in enumerate(heads):
            out.append((m.group(0), text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]))
        return out

    def body(self, b):
        b = b.rstrip("\n")
        if b.endswith("\n---"):
            b = b[:-4].rstrip("\n")
        return b

    def walk(self, old, new):
        """Every block of `old`, in order, is found in `new` under a heading that starts with its heading, its body starting with its body of then. Returns the blocks checked."""
        o, n = self.blocks(old), self.blocks(new)
        j = 0
        for h0, b0 in o:
            while j < len(n) and not n[j][0].startswith(h0):
                j += 1
            self.assertLess(j, len(n), "the block %r is gone or its heading changed" % h0[:70])
            self.assertTrue(n[j][1].startswith(self.body(b0)), "the text under %r changed above its end" % h0[:70])
            j += 1
        return len(o)

    def test_v31_6_v31_8_v31_10_are_found_block_by_block_at_both_heading_levels(self):
        old_t, new_t = base(HT), read(HT)
        for head, least in (("### V31.6 ", 2), ("### V31.8 ", 3), ("### V31.10 ", 2)):
            self.assertGreaterEqual(self.walk(section(old_t, head), section(new_t, head)), least, head)
        self.assertGreater(self.walk(old_t, new_t), 1300)

    def test_v31_10s_table_is_cell_by_cell_and_its_owed_row_is_untouched(self):
        def rows(s):
            return [[c.strip() for c in l.strip().strip("|").split("|")] for l in s.split("\n") if l.startswith("| ") and not l.startswith("| ---")]
        old_r, new_r = rows(section(base(HT), "### V31.10 ")), rows(section(read(HT), "### V31.10 "))
        self.assertGreater(len(old_r), 10)
        for ro in old_r:
            cands = [rn for rn in new_r if rn[0] == ro[0]]
            self.assertTrue(cands, ro[0])
            rn = cands[0]
            self.assertEqual(len(rn), len(ro))
            for co, cn in zip(ro, rn):
                self.assertTrue(cn.startswith(co), "a cell of V31.10's table changed: %r -> %r" % (co[:60], cn[:60]))
        owed = [r for r in old_r if r[0] == "startup profile, Policy A"]
        self.assertEqual(len(owed), 1)
        self.assertEqual(owed[0][1:], ["survive, their own readers", "NOT READ in this ingestion (#155 does not list them, and no reader of them was run on a sidecar-less play log)", "owed, not passed"])
        self.assertIn("SURVIVE (records the vehicle keeps)", section(read(HT), "### V31.6 "))      # the corrected sentence stays where it was written
        self.assertIn("survive and are read by their own readers", section(read(HT), "### V31.8 "))

    def test_the_evidence_entries_gbp_hw_382_and_383_and_the_whole_file_are_on_top(self):
        old_t, new_t = base(EV), read(EV)
        self.assertGreater(self.walk(old_t, new_t), 440)
        for eid in ("GBP-HW-382", "GBP-HW-383"):
            o = re.search(r"^### %s .*$" % eid, old_t, re.M).group(0)
            n = re.search(r"^### %s .*$" % eid, new_t, re.M).group(0)
            self.assertEqual(o, n, "%s's heading, status included, is untouched" % eid)

    def test_the_devlog_is_on_top(self):
        self.assertGreater(self.walk(base(DEVLOG), read(DEVLOG)), 380)


class TheNewRecords(unittest.TestCase):
    def test_v31_12_exists_once_starts_its_block_and_follows_v31_11(self):
        t = read(HT)
        self.assertEqual(t.count(SEC), 1)
        self.assertEqual(len(re.findall(r"^### V31\.12 ", t, re.M)), 1)
        heads = [m.group(0) for m in re.finditer(r"^### V31\.\d+ ", t, re.M)]
        self.assertEqual(heads[heads.index("### V31.11 ") + 1], "### V31.12 ", "V31.12 follows V31.11 once, in order")
        self.assertEqual(heads.count("### V31.12 "), 1)
        self.assertLess(t.index("### V31.11 "), t.index(SEC))
        self.assertEqual(t[t.index(SEC) - 2:t.index(SEC)], "\n\n")

    def test_v31_12_says_not_readable_and_never_says_the_two_gates_passed(self):
        s = section(read(HT), SEC)
        self.assertIn("NOT READABLE IN THESE LOGS", s)
        self.assertIn("NOT READABLE IN THESE LOGS (no record)", s)
        rest = s
        for phrase in ("passed by `-DGBP_STARTUP_MODE", "target passes no `STARTUP_MODE`"):
            rest = rest.replace(phrase, "")
        rest = re.sub(r"\b(?:not|never)\s+(?:closed\s+)?(?:as\s+)?passed", "", rest, flags=re.I)          # the only forms in which the word may appear: negated
        self.assertIsNone(re.search(r"\bpass", rest, re.I), "V31.12 must not say either gate passed: %s" % (re.search(r".{40}\bpass.{20}", rest, re.I | re.S) or "").__repr__())

    def test_v31_12_says_what_it_must(self):
        s = flat(section(read(HT), SEC))
        for tok in ("f98a11b", "closed as NO RECORD", "WRONG for the startup profile and Policy A", "What the vehicle keeps of them is CODE",
                    "not an observation of the run", "UNKNOWN at run level", "the first real hand-off time", "have_first", "presented_synthetic",
                    "it is NOT a physical one", "Gecko only", "A RECOMMENDATION, not built here", "GBP_VDISP_LIFE_CAP", "OGBPDISP2",
                    "The stop rule written before the reading", "was not triggered", "PLAYSTARTUP", "GBP-HW-384", "post-hoc gate",
                    "main.c:1034-1035", "main.c:351-355", "is UNKNOWN", "INPUT selftest=1", "the self-test of the INPUT path, not the display's", "The exact binary (AGENTS.md §5)",
                    "build/swiss/28-vehicle/boot.dol", "a02bcfa3b84ccd363d7bad54c8e72411d9f2e9a49595963903d1feeac4acf5d2", "strings -n 4", "0 / 0 / 0"):
            self.assertIn(tok, s, tok)
        self.assertIn("does NOT do", s)
        self.assertIn("edit §V31.6, §V31.8, §V31.10", s)

    def test_gbp_hw_384_exists_once_follows_gbp_hw_383_and_keeps_the_statuses_apart(self):
        t = read(EV)
        ids = [m.group(1) for m in re.finditer(EV_HEAD, t, re.M)]
        self.assertEqual(ids.count("GBP-HW-384"), 1)
        self.assertEqual(ids.count("GBP-HW-383"), 1)
        self.assertEqual(ids[ids.index("GBP-HW-383") + 1], "GBP-HW-384")
        i = t.index("### GBP-HW-384 ")
        j = t.find("\n### ", i + 1)
        e = flat(t[i:j if j > 0 else len(t)])
        self.assertTrue(e.startswith("### GBP-HW-384"))
        self.assertIn("FACT (code / data, recomputable)", e)
        self.assertIn("UNKNOWN", e)
        self.assertIn("NOT READABLE IN THESE LOGS (no record)", e)
        self.assertIn("never as passed", e)
        self.assertIn("§V31.12", e)
        self.assertNotIn("CORROBORATED", e, "no status other than FACT / UNKNOWN is awarded here")
        self.assertNotIn("HYPOTHESIS", e)
        self.assertIn("1971 / 1963 / 1737", e)
        self.assertIn("35 .c", e)
        self.assertIn("79 files in all", e)

    def test_the_handoff_and_the_devlog_carry_the_state_on_top(self):
        h = read(HANDOFF)
        for head in ("## Current blocker / current question\n\n", "## Next safe action\n\n"):
            i = h.index(head) + len(head)
            sec = h[i:h.index("\n## ", i)]
            self.assertTrue(sec.startswith("**2026-10-05 (Issue #157), on top: "), head)
            self.assertEqual(sec.count("Issue #157), on top:"), 1)
            self.assertIn("**2026-10-05 (Issue #156), on top:", sec)
            self.assertIn("**2026-10-05 (Issue #155), on top:", sec)
            self.assertLess(sec.index("Issue #157"), sec.index("Issue #156"))
        self.assertIn("the next safe action is Issue #158 (build the play image vehicle-0002, which also writes the startup profile and the Policy A invariants to its SD log", h)
        d = read(DEVLOG)
        self.assertEqual(len(re.findall(r"^## 2026-10-05 — Issue #157: ", d, re.M)), 1)
        self.assertLess(d.index("## 2026-10-05 — Issue #156: "), d.index("## 2026-10-05 — Issue #157: "))


if __name__ == "__main__":
    unittest.main()
