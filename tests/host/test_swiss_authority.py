"""
tests/host/test_swiss_authority.py — neither build/poc nor build/swiss is an
authority, and every place that could believe otherwise is checked (GitHub
Issue #88).

WHAT WAS WRONG. INDEX.txt said "The AUTHORITY is the source path below, never
this copy", and swiss_export's docstring, two Makefile comments and HANDOFF
said the same. build/poc is a BUILD OUTPUT; it moves with HEAD. On 2026-09-23,
eleven of fourteen staged slots (01-11) held rebuilds exported at 7d7a6d8 under
the build ids of images that had run at other commits -- color-0002 ran as
d3c1f09e @ 39f1980, the card's 11-color is 5cab1543 @ 7d7a6d8 -- and the one
tool that turns build/poc into something the Operator boots copied every
unpinned slot on trust. The Orchestrator's own first table validated the
record against itself (the "pin" it read for 11-color was INDEX.txt's). This is
Issue #83's pattern H, a record that certifies itself, for the third time.

WHAT IS CHECKED HERE, so the corrected claim cannot quietly become false again:
  * NO TEXT claims build/poc (or the export) is an authority;
  * NO TOOL reads build/poc without being named here with the reason it may:
    a new reader fails this test until someone classifies it;
  * every PIN is a record: it appears in HARDWARE_TESTS.md, and the commit
    INDEX.txt states for it appears beside it there or in HANDOFF.md;
  * every INDEX row carries a STATUS, PINNED-VERIFIED exactly when the slot is
    frozen and its bytes are the pin, and UNPINNED-COPY otherwise;
  * `--index-only` copies nothing and removes nothing, and upgrades an INDEX
    written before the STATUS column existed.
"""
import hashlib
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import swiss_export  # noqa: E402

MANIFEST = os.path.join(ROOT, "tools", "swiss-layout.tsv")
SWISS = os.path.join(ROOT, "build", "swiss")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")

# The phrasings the corrected claim replaced. Each is how the old authority sentence was
# written somewhere; none may come back. (Assembled from pieces so this file does not match.)
FORBIDDEN = [
    "authority remains " + "`build/poc",
    "build/poc stays " + "the authority",
    "AUTHORITY stays " + "build/poc",
    "The AUTHORITY is " + "the source path",
    "which is the " + "authority. `build/swiss` is presentation",
    "authority never moves " + "out of build/poc",
]

# Every file under tools/ that names build/poc, and why it may. A NEW reader fails
# the test below until it is classified here -- the "cannot recur unobserved" rule.
BUILD_POC_READERS = {
    "tools/swiss_export.py": "copies build/poc into build/swiss; a FROZEN slot's source is verified against its "
                             "pin before anything is written (RULE 1), every other row is written UNPINNED-COPY",
    "tools/audit_listings.sh": "disassembles whatever build/poc holds for tools/poc_audit.py; it states no "
                               "identity and stages nothing",
    "tools/swiss-layout.tsv": "the manifest names each POC's output directory; it is data, not a reader",
}


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


class NothingClaimsBuildPocIsAnAuthority(unittest.TestCase):

    def files(self):
        out = [os.path.join(ROOT, "Makefile"), HANDOFF]
        for d in ("tools", ".github", os.path.join("tests", "host")):
            for dirpath, _dirs, names in os.walk(os.path.join(ROOT, d)):
                for n in names:
                    if n.endswith((".py", ".sh", ".tsv", ".md", ".txt")) and n != os.path.basename(__file__):
                        out.append(os.path.join(dirpath, n))
        return out

    def test_no_file_repeats_the_old_authority_sentence(self):
        hits = []
        for p in self.files():
            t = re.sub(r"\s+", " ", read(p))
            for phrase in FORBIDDEN:
                if phrase in t:
                    hits.append("%s: %r" % (os.path.relpath(p, ROOT), phrase))
        self.assertEqual(hits, [])

    def test_the_index_header_states_where_the_authority_is(self):
        # the header swiss_export writes, read from the code that writes it
        src = read(os.path.join(ROOT, "tools", "swiss_export.py"))
        self.assertIn("NEITHER THIS FILE NOR build/poc IS AN AUTHORITY.", src)
        self.assertIn("identified by the SHA-256 and commit in the records", src)
        self.assertIn("it has NO physical status -- booting it does NOT reproduce any executed run.", src)

    def test_the_pre_run_places_carry_the_warning_and_the_remedy(self):
        h = re.sub(r"\s+", " ", re.sub(r"\n>\s*", "\n", read(HANDOFF)))
        self.assertIn("BEFORE ANY RUN — THE CARD (2026-09-23, Issue #88).", h)
        self.assertIn("Slots 01–11 on the card are rebuilds exported at `7d7a6d8`", h)
        self.assertIn("The remedy, not applied:", h)
        t = re.sub(r"\s+", " ", read(os.path.join(ROOT, ".github", "ISSUE_TEMPLATE", "hardware-run.md")))
        self.assertIn("The slot booted must read `PINNED-VERIFIED` in `build/swiss/INDEX.txt`", t)


class NoToolReadsBuildPocWithoutAReason(unittest.TestCase):

    def test_every_reader_of_build_poc_under_tools_is_classified(self):
        found = set()
        for dirpath, _dirs, names in os.walk(os.path.join(ROOT, "tools")):
            for n in names:
                p = os.path.join(dirpath, n)
                if not os.path.isfile(p) or n.endswith((".pyc",)):
                    continue
                t = read(p)
                if "build/poc" in t or re.search(r"""["']build["']\s*,\s*["']poc["']""", t):
                    found.add(os.path.relpath(p, ROOT))
        self.assertEqual(sorted(found), sorted(BUILD_POC_READERS),
                         "a tool that reads build/poc must be classified in BUILD_POC_READERS with the reason "
                         "it may; build/poc is a build output, never a record")

    def test_the_exporter_verifies_a_frozen_source_before_writing(self):
        """RULE 1, read from the code: the pin check comes before the first copy."""
        src = read(os.path.join(ROOT, "tools", "swiss_export.py"))
        rule1 = src.index("# RULE 1, before anything is written or removed")
        first_copy = src.index("shutil.copyfile(src, dst)")
        self.assertLess(rule1, first_copy)


class EveryPinIsARecord(unittest.TestCase):

    def test_each_pin_and_its_commit_are_in_the_records(self):
        rows = [r for r in swiss_export.load(MANIFEST) if r["frozen_sha256"] != "-"]
        self.assertGreaterEqual(len(rows), 3)
        hw, handoff = read(HW), read(HANDOFF)
        idx = swiss_export.parse_index(SWISS) if os.path.isdir(SWISS) else {}
        for r in rows:
            pin = r["frozen_sha256"]
            self.assertIn(pin, hw, "%s's pin is not in HARDWARE_TESTS.md" % r["dir"])
            commit = idx.get(r["dir"], {}).get("commit")
            if not commit or commit == "-":
                continue
            near = False
            for doc in (hw, handoff):
                for m in re.finditer(re.escape(pin), doc):
                    if commit in doc[max(0, m.start() - 800): m.end() + 800]:
                        near = True
            self.assertTrue(near, "%s: INDEX says commit %s, and no record carries that commit beside the pin %s"
                                  % (r["dir"], commit, pin[:12]))


class TheIndexRowsCarryTheirStatus(unittest.TestCase):
    """The real INDEX, when something is staged: the claim is checkable ROW BY ROW."""

    def setUp(self):
        if not os.path.isfile(os.path.join(SWISS, "INDEX.txt")):
            self.skipTest("nothing is staged under build/swiss on this host")

    def test_pinned_verified_exactly_when_frozen_and_the_bytes_are_the_pin(self):
        frozen = {r["dir"]: r["frozen_sha256"] for r in swiss_export.load(MANIFEST) if r["frozen_sha256"] != "-"}
        text = read(os.path.join(SWISS, "INDEX.txt"))
        rows = [swiss_export.INDEX_ROW_RE.match(l) for l in text.splitlines()]
        rows = [m for m in rows if m]
        self.assertTrue(rows)
        for m in rows:
            slot, status = m.group(1), m.group(7)
            self.assertIsNotNone(status, "%s has no STATUS: INDEX.txt predates Issue #88; run "
                                         "tools/swiss_export.py --index-only" % slot)
            staged = os.path.join(SWISS, slot, "boot.dol")
            pinned = slot in frozen and os.path.isfile(staged) and sha256(staged) == frozen[slot]
            self.assertEqual(status, swiss_export.STATUS_PINNED if pinned else swiss_export.STATUS_COPY, slot)


class TheExporterWritesTheStatusAndIndexOnlyTouchesNothing(unittest.TestCase):
    """Exercised in a temporary root, never asserted."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="swiss-authority-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out = os.path.join(self.tmp, "build", "swiss")
        for name, body in (("p", b"PINNED BYTES, the image a run executed\n"), ("q", b"a copy of whatever was built\n")):
            d = os.path.join(self.tmp, "build", "poc", name)
            os.makedirs(d)
            with open(os.path.join(d, name + ".dol"), "wb") as f:
                f.write(body)
            with open(os.path.join(d, "build-info.txt"), "w") as f:
                f.write("build_id=%s-0001\ncommit=abc1234\n" % name)
            os.makedirs(os.path.join(self.tmp, "poc", name))
        self.pin = hashlib.sha256(b"PINNED BYTES, the image a run executed\n").hexdigest()
        self.manifest = os.path.join(self.tmp, "layout.tsv")
        with open(self.manifest, "w") as f:
            f.write("#number\tshort_name\tsource_poc\tdol\tout_dir\tmake_target\tenabled\tfrozen_sha256\n")
            f.write("70\tpin\tp\tp.dol\tp\tbuild\t1\t%s\n" % self.pin)
            f.write("71\tcopy\tq\tq.dol\tq\tbuild\t1\t-\n")

    def run_export(self, *extra):
        return swiss_export.main(["--root", self.tmp, "--out", self.out, "--manifest", self.manifest] + list(extra))

    def statuses(self):
        text = read(os.path.join(self.out, "INDEX.txt"))
        return {m.group(1): m.group(7) for m in map(swiss_export.INDEX_ROW_RE.match, text.splitlines()) if m}

    def snapshot(self):
        out = {}
        for dirpath, _dirs, names in os.walk(self.out):
            for n in names:
                if n != "INDEX.txt":
                    p = os.path.join(dirpath, n)
                    out[os.path.relpath(p, self.out)] = (sha256(p), os.stat(p).st_mtime_ns)
        return out

    def test_an_export_writes_pinned_verified_only_for_the_frozen_slot(self):
        self.assertEqual(self.run_export(), 0)
        self.assertEqual(self.statuses(), {"70-pin": swiss_export.STATUS_PINNED, "71-copy": swiss_export.STATUS_COPY})

    def test_index_only_copies_nothing_removes_nothing_and_upgrades_an_old_index(self):
        self.assertEqual(self.run_export(), 0)
        # turn the INDEX into one written before Issue #88: no STATUS column
        p = os.path.join(self.out, "INDEX.txt")
        old = [re.sub(r"\| (PINNED-VERIFIED|UNPINNED-COPY)\s+\| ", "| ", l) for l in read(p).splitlines()]
        with open(p, "w") as f:
            f.write("\n".join(old) + "\n")
        before = self.snapshot()
        # and move build/poc on: an index-only rewrite must not care, and must not copy it
        with open(os.path.join(self.tmp, "build", "poc", "q", "q.dol"), "wb") as f:
            f.write(b"a LATER build, never exported\n")
        self.assertEqual(self.run_export("--index-only"), 0)
        self.assertEqual(self.snapshot(), before, "--index-only changed a staged file")
        self.assertEqual(self.statuses(), {"70-pin": swiss_export.STATUS_PINNED, "71-copy": swiss_export.STATUS_COPY})
        self.assertIn("NEITHER THIS FILE NOR build/poc IS AN AUTHORITY.", read(p))

    def test_index_only_takes_no_slot_and_needs_a_staged_tree(self):
        self.assertEqual(self.run_export("--index-only", "--only", "70"), 2)
        self.assertEqual(self.run_export("--index-only"), 2)          # nothing staged yet
        self.assertFalse(os.path.exists(self.out))


if __name__ == "__main__":
    unittest.main()
