"""tools/swiss_export.py and the versioned layout manifest.

The manifest is an OPERATIONAL INTERFACE: an operator reads `10-vstate` off a
television and launches it. So the properties worth testing are the ones that
would let the wrong DOL be launched — a duplicate number, a name Swiss
truncates, a source that does not exist — plus the one property that makes the
export safe to ignore entirely: the copy is byte for byte. Neither build/poc
nor the export is an authority (Issue #88, correcting this docstring): an
executed image is its recorded SHA-256 and commit, and only a FROZEN slot is
checked against it.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import swiss_export  # noqa: E402

MANIFEST = os.path.join(ROOT, "tools", "swiss-layout.tsv")


class Manifest(unittest.TestCase):
    def setUp(self):
        self.rows = swiss_export.load(MANIFEST)

    def test_it_parses_and_is_not_empty(self):
        self.assertTrue(self.rows)

    def test_numbers_are_two_digits_unique_and_sort_lexically(self):
        nums = [r["number"] for r in self.rows]
        self.assertEqual(len(nums), len(set(nums)), "a number is used twice")
        for n in nums:
            self.assertEqual(len(n), 2, "%r is not two digits" % n)
            self.assertTrue(n.isdigit())
        # two digits exist precisely so that lexical order == numeric order,
        # which is the order Swiss shows
        self.assertEqual(nums, sorted(nums))
        self.assertEqual([int(n) for n in nums], sorted(int(n) for n in nums))

    def test_short_names_are_unique(self):
        names = [r["short_name"] for r in self.rows]
        self.assertEqual(len(names), len(set(names)))

    def test_directory_names_stay_short(self):
        for r in self.rows:
            self.assertLessEqual(len(r["dir"]), swiss_export.MAX_DIR_NAME,
                                 "%r would be truncated in Swiss" % r["dir"])

    def test_every_source_poc_exists(self):
        for r in self.rows:
            p = os.path.join(ROOT, "poc", r["source_poc"])
            self.assertTrue(os.path.isdir(p), "missing POC %s" % r["source_poc"])

    def test_the_diagnostic_range_is_used_for_diagnostics(self):
        """80-89 is reserved for physical diagnostics; the canonical POCs stay below."""
        for r in self.rows:
            n = int(r["number"])
            if r["out_dir"] != r["source_poc"]:      # a variant build, not the POC itself
                self.assertGreaterEqual(n, 80, "%s is a variant and belongs in a diagnostic range" % r["dir"])
            else:
                self.assertLess(n, 80, "%s is a canonical POC and belongs below 80" % r["dir"])

    def test_a_duplicate_number_is_refused(self):
        self._refuse("01\tdup\tsmoke-test\tx.dol\tsmoke-test\tbuild\t1\t-\n")

    def test_a_one_digit_number_is_refused(self):
        self._refuse("7\tseven\tsmoke-test\tx.dol\tsmoke-test\tbuild\t1\t-\n")

    def test_a_long_directory_name_is_refused(self):
        self._refuse("70\tway-too-long-name\tsmoke-test\tx.dol\tsmoke-test\tbuild\t1\t-\n")

    def test_a_duplicate_short_name_is_refused(self):
        self._refuse("70\tsmoke\tsmoke-test\tx.dol\tsmoke-test\tbuild\t1\t-\n")

    def test_a_wrong_field_count_is_refused(self):
        self._refuse("70\tshort\tsmoke-test\n")   # three fields: still a wrong count against the eight

    def _refuse(self, extra_line):
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False) as f:
            f.write(open(MANIFEST).read())
            f.write(extra_line)
            path = f.name
        try:
            with self.assertRaises(ValueError):
                swiss_export.load(path)
        finally:
            os.unlink(path)


class Export(unittest.TestCase):
    """The export itself, against a synthetic build tree so the test needs no
    toolchain and cannot be confused by whatever happens to be built."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.rows = swiss_export.load(MANIFEST)
        for r in self.rows:
            d = os.path.join(self.tmp, "build", "poc", r["out_dir"])
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, r["dol"]), "wb") as f:
                f.write(("DOL:" + r["dir"]).encode() + os.urandom(64))
            with open(os.path.join(d, "build-info.txt"), "w") as f:
                f.write("build_id=%s\ncommit=deadbee\n" % r["short_name"])
        os.makedirs(os.path.join(self.tmp, "poc"), exist_ok=True)
        # The real manifest's ROWS, with the frozen column cleared: these tests exercise the export
        # MECHANICS against synthetic bytes, and a frozen slot refuses synthetic bytes by design
        # (that refusal is what FrozenSlotsCannotBeDestroyed proves, in its own temporary root).
        with open(os.path.join(self.tmp, "layout.tsv"), "w") as f:
            for line in open(MANIFEST):
                if line.strip() and not line.lstrip().startswith("#"):
                    parts = line.rstrip("\n").split("\t")
                    parts[-1] = "-"
                    line = "\t".join(parts) + "\n"
                f.write(line)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self):
        return swiss_export.main(["--root", self.tmp,
                                  "--manifest", os.path.join(self.tmp, "layout.tsv")])

    def test_every_enabled_entry_is_exported_as_boot_dol(self):
        self.assertEqual(self._run(), 0)
        for r in self.rows:
            if r["enabled"] != "1":
                continue
            p = os.path.join(self.tmp, "build", "swiss", r["dir"], "boot.dol")
            self.assertTrue(os.path.exists(p), "missing %s" % p)

    def test_the_copy_is_byte_identical(self):
        """The export must never become a second identity: same bytes, same hash."""
        self.assertEqual(self._run(), 0)
        for r in self.rows:
            if r["enabled"] != "1":
                continue
            src = os.path.join(self.tmp, "build", "poc", r["out_dir"], r["dol"])
            dst = os.path.join(self.tmp, "build", "swiss", r["dir"], "boot.dol")
            self.assertEqual(hashlib.sha256(open(src, "rb").read()).hexdigest(),
                             hashlib.sha256(open(dst, "rb").read()).hexdigest())

    def test_the_index_lists_every_export(self):
        self.assertEqual(self._run(), 0)
        text = open(os.path.join(self.tmp, "build", "swiss", "INDEX.txt")).read()
        for r in self.rows:
            if r["enabled"] == "1":
                self.assertIn(r["dir"], text)
        self.assertIn("AUTHORITY", text)

    def test_a_missing_dol_is_reported_not_faked(self):
        os.unlink(os.path.join(self.tmp, "build", "poc", self.rows[0]["out_dir"], self.rows[0]["dol"]))
        self.assertEqual(self._run(), 0)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "build", "swiss", self.rows[0]["dir"], "boot.dol")))
        text = open(os.path.join(self.tmp, "build", "swiss", "INDEX.txt")).read()
        self.assertIn("NOT EXPORTED", text)

    def test_the_export_only_clears_its_own_directory(self):
        other = os.path.join(self.tmp, "build", "poc", "keepme.txt")
        open(other, "w").write("keep")
        self.assertEqual(self._run(), 0)
        self.assertTrue(os.path.exists(other), "the export removed something outside build/swiss")

    def test_rerunning_is_clean(self):
        self.assertEqual(self._run(), 0)
        stray = os.path.join(self.tmp, "build", "swiss", "99-stale")
        os.makedirs(stray)
        open(os.path.join(stray, "boot.dol"), "w").write("old")
        self.assertEqual(self._run(), 0)
        self.assertFalse(os.path.exists(stray), "a stale export directory survived")


class ColourCandidate(unittest.TestCase):
    """§V3.28: the physical candidate for GBP-VIDEO-003 must be reachable in the
    operator layout under its canonical number, and it must be the same bytes as
    the build it came from."""

    def test_the_colour_poc_is_exported_under_its_canonical_number(self):
        rows = {r["short_name"]: r for r in swiss_export.load(MANIFEST)}
        self.assertIn("color", rows)
        r = rows["color"]
        self.assertEqual(r["dir"], "11-color")
        self.assertEqual(r["source_poc"], "gbp-video-color-probe")
        self.assertEqual(r["out_dir"], "gbp-video-color-probe")
        self.assertEqual(r["enabled"], "1")

    def test_the_diagnostic_is_a_different_entry(self):
        """80-prewait is the vstate probe with a wait, not this experiment."""
        rows = {r["short_name"]: r for r in swiss_export.load(MANIFEST)}
        self.assertIn("prewait", rows)
        self.assertNotEqual(rows["prewait"]["source_poc"], rows["color"]["source_poc"])
        self.assertEqual(rows["prewait"]["number"], "80")

    def test_the_exported_colour_dol_is_the_source_dol(self):
        """Skipped when nothing is built; when it is built, the bytes must match."""
        src = os.path.join(ROOT, "build", "poc", "gbp-video-color-probe",
                           "gbp-video-color-probe.dol")
        dst = os.path.join(ROOT, "build", "swiss", "11-color", "boot.dol")
        if not (os.path.exists(src) and os.path.exists(dst)):
            self.skipTest("run `make build && make swiss` to check the exported colour DOL")
        # The export is a snapshot: a later code checkpoint rebuilds the colour probe (it links the service-path
        # module, which Issue #39 changed) without re-exporting the staged layout, and must not -- build/swiss holds
        # what the operator launches. So the bytes are compared only when INDEX.txt says the export came from the
        # build this tree carries; otherwise the export is EARLIER, not wrong.
        info = os.path.join(ROOT, "build", "poc", "gbp-video-color-probe", "build-info.txt")
        index = os.path.join(ROOT, "build", "swiss", "INDEX.txt")
        if os.path.exists(info) and os.path.exists(index):
            commit = dict(l.split("=", 1) for l in open(info).read().splitlines() if "=" in l).get("commit", "-")
            row = [l for l in open(index).read().splitlines() if l.startswith("11-color ")]
            if row and ("| %s " % commit) not in row[0]:
                self.skipTest("build/swiss/11-color is the export of an earlier build (%s); the tree now builds the colour probe at %s"
                              % (row[0].split("|")[3].strip(), commit))
        self.assertEqual(hashlib.sha256(open(src, "rb").read()).hexdigest(),
                         hashlib.sha256(open(dst, "rb").read()).hexdigest())


class NotTracked(unittest.TestCase):
    def test_build_swiss_is_ignored_by_git(self):
        r = subprocess.run(["git", "check-ignore", "-q", "build/swiss"], cwd=ROOT)
        self.assertEqual(r.returncode, 0, "build/swiss must be ignored by Git")

    def test_no_exported_dol_is_tracked(self):
        r = subprocess.run(["git", "ls-files", "build/"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "")


class FrozenSlotsCannotBeDestroyed(unittest.TestCase):
    """GitHub Issue #44: the refusals are PROVED in a temporary root, never asserted.

    The hazard this protects against was live on 2026-09-21: `build/swiss/12-stream` held the image
    three physical runs executed, `build/poc` held a rebuild at another commit, and a full export
    would have replaced the slot, rewritten its INDEX row to agree, and left the Operator's SD as
    the only copy -- with exit code 0.
    """
    FROZEN = "a" * 0      # filled in setUp from the real bytes

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="swiss-frozen-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # a root with one POC that builds "new bytes", and an export tree already holding "old bytes"
        self.poc = os.path.join(self.tmp, "build", "poc", "p")
        os.makedirs(self.poc)
        self.src = os.path.join(self.poc, "p.dol")
        with open(self.src, "wb") as f:
            f.write(b"NEW BYTES, a rebuild at another commit\n")
        os.makedirs(os.path.join(self.tmp, "poc", "p"))
        self.out = os.path.join(self.tmp, "build", "swiss")
        os.makedirs(os.path.join(self.out, "70-frozen"))
        self.staged = os.path.join(self.out, "70-frozen", "boot.dol")
        with open(self.staged, "wb") as f:
            f.write(b"OLD BYTES, the image a physical run executed\n")
        self.frozen_hash = hashlib.sha256(open(self.staged, "rb").read()).hexdigest()
        self.manifest = os.path.join(self.tmp, "layout.tsv")
        self._write_manifest(self.frozen_hash)
        with open(os.path.join(self.out, "INDEX.txt"), "w") as f:
            f.write("Open-GBP - Swiss launch layout\n\n"
                    "%-12s | %-18s | %-22s | %-9s | %10s | %-64s | %s\n"
                    % ("DIR", "TEST ID", "BUILD ID", "COMMIT", "SIZE", "SHA-256", "SOURCE")
                    + "%-12s | %-18s | %-22s | %-9s | %10d | %s | %s\n"
                    % ("70-frozen", "THE-TEST-001", "frozen-0001", "deadbee", os.path.getsize(self.staged),
                       self.frozen_hash, "build/poc/p/p.dol"))

    def _write_manifest(self, frozen):
        with open(self.manifest, "w") as f:
            f.write("#number\tshort_name\tsource_poc\tdol\tout_dir\tmake_target\tenabled\tfrozen_sha256\n")
            f.write("70\tfrozen\tp\tp.dol\tp\tbuild\t1\t%s\n" % frozen)

    def _run(self, *extra_args):
        return swiss_export.main(["--root", self.tmp, "--out", self.out, "--manifest", self.manifest] + list(extra_args))

    def test_a_full_export_refuses_and_changes_nothing(self):
        before = open(self.staged, "rb").read()
        index_before = open(os.path.join(self.out, "INDEX.txt")).read()
        rc = self._run()
        self.assertNotEqual(rc, 0, "the export must REFUSE, not succeed")
        self.assertEqual(rc, 4)
        self.assertEqual(open(self.staged, "rb").read(), before, "the frozen slot's bytes were changed")
        self.assertEqual(open(os.path.join(self.out, "INDEX.txt")).read(), index_before,
                         "INDEX.txt was rewritten while the export was refusing")

    def test_only_another_slot_leaves_the_frozen_one_alone(self):
        os.makedirs(os.path.join(self.tmp, "poc", "q"))
        os.makedirs(os.path.join(self.tmp, "build", "poc", "q"))
        with open(os.path.join(self.tmp, "build", "poc", "q", "q.dol"), "wb") as f:
            f.write(b"a new slot's bytes\n")
        with open(self.manifest, "a") as f:
            f.write("71\tfresh\tq\tq.dol\tq\tbuild\t1\t-\n")
        before = open(self.staged, "rb").read()
        rc = self._run("--only", "71-fresh")
        self.assertEqual(rc, 0)
        self.assertEqual(open(self.staged, "rb").read(), before, "a --only export touched another slot")
        self.assertTrue(os.path.exists(os.path.join(self.out, "71-fresh", "boot.dol")))
        # and the frozen slot's INDEX row is CARRIED OVER, not recomputed from build/poc
        index = open(os.path.join(self.out, "INDEX.txt")).read()
        self.assertIn("frozen-0001", index, "the carried-over row lost the identity it recorded")
        self.assertIn("deadbee", index)
        self.assertIn(self.frozen_hash, index)

    def test_the_index_refuses_to_re_describe_a_frozen_slot_whose_bytes_moved(self):
        """If the staged bytes are not the pinned ones, the index must not learn a new identity for them."""
        with open(self.staged, "wb") as f:
            f.write(b"SOMETHING ELSE ENTIRELY\n")
        os.makedirs(os.path.join(self.tmp, "poc", "q"))
        os.makedirs(os.path.join(self.tmp, "build", "poc", "q"))
        with open(os.path.join(self.tmp, "build", "poc", "q", "q.dol"), "wb") as f:
            f.write(b"a new slot's bytes\n")
        with open(self.manifest, "a") as f:
            f.write("71\tfresh\tq\tq.dol\tq\tbuild\t1\t-\n")
        rc = self._run("--only", "71-fresh")
        self.assertEqual(rc, 5, "the index must refuse to describe a frozen slot it cannot vouch for")

    def test_an_export_that_writes_the_pinned_bytes_is_allowed(self):
        """The freeze is not a lock on the slot: it is a lock on the BYTES."""
        with open(self.src, "wb") as f:
            f.write(open(self.staged, "rb").read())
        rc = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(hashlib.sha256(open(self.staged, "rb").read()).hexdigest(), self.frozen_hash)

    def test_a_bad_frozen_column_is_refused_by_the_manifest(self):
        self._write_manifest("not-a-hash")
        with self.assertRaises(ValueError):
            swiss_export.load(self.manifest)

    def test_the_real_manifest_freezes_the_two_slots_the_records_name(self):
        rows = {r["dir"]: r["frozen_sha256"] for r in swiss_export.load(MANIFEST)}
        self.assertEqual(rows["12-stream"], "dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49")
        self.assertEqual(rows["13-play"], "d0ee3c29d04254d1b86d4f006291008876b5e886e07280d0421b7c1161c499de")
        # Hardware Issue #61 (2026-09-22) staged 14-audio, frozen from the start because it is
        # staged FOR a run that has not happened yet
        self.assertEqual(rows["14-audio"], "c3281a8c1382a1136a881c5548ef8238d69fa7862861d66741310b3d1f5f9c54")
        # Issue #84 / #86 (2026-09-23): the drain and output-path candidates, frozen from the start for
        # the one sitting the Operator decided on (§V19.12, §V21.4)
        self.assertEqual(rows["15-drain"], "4c80ab8a34d9260793e036beda513a9a23be86d04c61c0d653c6f79fc7333884")
        self.assertEqual(rows["16-aout"], "97f113ca0bbc9ec94e5ca945a2a34dae4f5bd5ff9386b2b8362cc32e8d7145e2")
        # Issue #92 (2026-09-23): Phase 6's acceptance image, frozen before its export (§V22.11)
        self.assertEqual(rows["17-live"], "c4b9ae23a95a96eae60de11106ba7d01521071fd3e0ce43b734e856719f5ee8d")
        # Issue #101 (2026-09-24): Run A's image, frozen before its export (§V23.9, §V23.10)
        self.assertEqual(rows["18-trace"], "5c08ea10db8eb2116c06a0b410cc72e4b41b903fef26c5e37aa244e1a9d953fe")
        # Issue #105 (2026-09-24): Run B's image, frozen before its export (§V24.8, §V24.9)
        self.assertEqual(rows["19-split"], "2afe3aa606e6a6682b8e1fbfc758bade253195047e9b5f9624aadfa1ea467d2d")
        self.assertEqual(sorted(d for d, f in rows.items() if f != "-"),
                         ["12-stream", "13-play", "14-audio", "15-drain", "16-aout", "17-live", "18-trace", "19-split"])
        # and every frozen hash is one HARDWARE_TESTS.md names, so the manifest cannot drift from the
        # record. ONE document, deliberately: an invariant that may be satisfied by either of two files
        # is weaker than one that must be satisfied by a named file, and this project has already paid
        # for a check whose scope widened for a good reason (Issue #29's three instances, #44's fourth).
        # stream-0016's identity is in §V8.12, a NEW dated part APPENDED to the frozen pre-registration:
        # frozen text keeps its words and the record grows on top.
        hw = open(os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md"), encoding="utf-8").read()
        for d, h in sorted(rows.items()):
            if h != "-":
                self.assertIn(h, hw, d)


if __name__ == "__main__":
    unittest.main()
