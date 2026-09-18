"""tools/swiss_export.py and the versioned layout manifest.

The manifest is an OPERATIONAL INTERFACE: an operator reads `10-vstate` off a
television and launches it. So the properties worth testing are the ones that
would let the wrong DOL be launched — a duplicate number, a name Swiss
truncates, a source that does not exist — plus the one property that makes the
export safe to ignore entirely: the copy is byte for byte, so the authority
never moves out of build/poc.
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
        self._refuse("01\tdup\tsmoke-test\tx.dol\tsmoke-test\tbuild\t1\n")

    def test_a_one_digit_number_is_refused(self):
        self._refuse("7\tseven\tsmoke-test\tx.dol\tsmoke-test\tbuild\t1\n")

    def test_a_long_directory_name_is_refused(self):
        self._refuse("70\tway-too-long-name\tsmoke-test\tx.dol\tsmoke-test\tbuild\t1\n")

    def test_a_duplicate_short_name_is_refused(self):
        self._refuse("70\tsmoke\tsmoke-test\tx.dol\tsmoke-test\tbuild\t1\n")

    def test_a_wrong_field_count_is_refused(self):
        self._refuse("70\tshort\tsmoke-test\n")

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
        shutil.copy(MANIFEST, os.path.join(self.tmp, "layout.tsv"))

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
        self.assertEqual(hashlib.sha256(open(src, "rb").read()).hexdigest(),
                         hashlib.sha256(open(dst, "rb").read()).hexdigest())


class NotTracked(unittest.TestCase):
    def test_build_swiss_is_ignored_by_git(self):
        r = subprocess.run(["git", "check-ignore", "-q", "build/swiss"], cwd=ROOT)
        self.assertEqual(r.returncode, 0, "build/swiss must be ignored by Git")

    def test_no_exported_dol_is_tracked(self):
        r = subprocess.run(["git", "ls-files", "build/"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
