"""tests/host/test_error_not_absence.py — an error may not be reported as an absence (Issue #83).

THE PRINCIPLE, as the Orchestrator put it deciding §V18.7: Issue #81's defect was
never about gcc. It was **an error condition rendered as an absence** — something
that went wrong, reported as something that was not there. Patterns B, C and D are
that shape in different clothes; F and H are a second shape, **a record that
certifies itself**.

This file is the behavioural half for B, F and H. Each case drives the real code
with one condition simulated, and requires the outcome to be a FAILURE where the
old code produced a skip, a `continue`, or a quiet agreement.

  B  `git show <commit>:<path>` fails for two different reasons. Absent COMMIT is a
     real "cannot check here" and skips. Absent PATH in a commit that IS here means
     the file moved or the test names it wrongly — a defect, and it now fails.

  F  seventeen freeze tests found their base with `git log -1 --grep <phrase>`, so a
     later commit repeating the phrase silently moved the base to the newest match.
     The hash is pinned now, and a phrase that matches more than one commit fails at
     the moment it becomes ambiguous.

  H  `build/swiss/INDEX.txt` is written by the same `make swiss` that writes the
     slots, so a slot agreeing with it proves only self-consistency. What an outside
     record fixes is the image that was PHYSICALLY EXECUTED, so a re-export that kept
     the executed commit's name on different bytes now fails (§V3.28's own warning).

Nothing here writes to the repository: the conditions are simulated inside a fresh
interpreter, and `build/archive` and `build/swiss` are never touched.
"""
import json
import os
import subprocess
import sys
import unittest

HOST = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HOST))


def drive(script):
    r = subprocess.run([sys.executable, "-c", script, HOST], capture_output=True, text=True,
                       cwd=HOST, timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


B_DRIVER = r'''
import json, sys, unittest
sys.path.insert(0, sys.argv[1])
import guards
out = {}
# an absent COMMIT is a legitimate "cannot check here"
try:
    guards.show("0" * 40, "tests/host/guards.py")
    out["absent_commit"] = "returned"
except unittest.SkipTest as e:
    out["absent_commit"] = "skip:" + str(e)[:60]
except AssertionError as e:
    out["absent_commit"] = "fail:" + str(e)[:60]
# a path missing from a commit that IS here is a DEFECT
try:
    guards.show("HEAD", "tests/host/a-path-that-never-existed.py")
    out["absent_path"] = "returned"
except unittest.SkipTest as e:
    out["absent_path"] = "skip:" + str(e)[:60]
except AssertionError as e:
    out["absent_path"] = "fail:" + str(e)[:120]
print(json.dumps(out))
'''

F_DRIVER = r'''
import io, json, sys, unittest
sys.path.insert(0, sys.argv[1])
import frozen
PHRASE = "Issue #80 -- predictions frozen"
out = {}
real = frozen._matches
# the collision this exists to catch: the phrase now names two commits
frozen._matches = lambda p: ["a" * 40, "b" * 40]
try:
    frozen.base(PHRASE)
    out["collision"] = "returned"
except AssertionError as e:
    out["collision"] = "fail:" + str(e)[:140]
except unittest.SkipTest as e:
    out["collision"] = "skip:" + str(e)[:80]
# and a real freeze test, driven through the same collision, must FAIL not skip
res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
    unittest.defaultTestLoader.loadTestsFromNames(
        ["test_v17pred.TheRecordIsHonestAboutWhatWasSeen.test_the_module_is_not_edited_after_its_commit"]))
out["freeze_test"] = {"failed": len(res.failures) + len(res.errors), "skipped": len(res.skipped),
                      "run": res.testsRun}
# the phrase pointing somewhere else than the pin is also a defect
frozen._matches = lambda p: ["c" * 40]
try:
    frozen.base(PHRASE)
    out["moved"] = "returned"
except AssertionError as e:
    out["moved"] = "fail:" + str(e)[:100]
frozen._matches = real
print(json.dumps(out))
'''

H_DRIVER = r'''
import io, json, sys, unittest
sys.path.insert(0, sys.argv[1])
import test_staged_artifacts as m
out = {}
SLOT, (want, doc, commit, size) = "11-color", m.EXECUTED["11-color"]
# a re-export that kept the EXECUTED commit's name on different bytes
m.staged_slots = lambda base: {SLOT: __import__("os").path.join(m.ROOT, "tests", "host", "guards.py")}
m.index_rows = lambda: {SLOT: {"test_id": "GBP-VIDEO-003", "build_id": "color-0002",
                               "commit": commit, "size": size, "sha256": want, "source": "x"}}
res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
    unittest.defaultTestLoader.loadTestsFromNames(
        ["test_staged_artifacts.TheStagedImagesAreWhatTheRecordsName.test_a_rebuilt_slot_is_never_mistaken_for_the_executed_image"]))
out["kept_executed_commit"] = {"failed": len(res.failures) + len(res.errors),
                               "skipped": len(res.skipped), "run": res.testsRun}
out["message"] = (res.failures[0][1][-400:] if res.failures else "")
# the honest case: the index names a DIFFERENT commit, so the divergence is explicit
m.index_rows = lambda: {SLOT: {"test_id": "GBP-VIDEO-003", "build_id": "color-0002",
                               "commit": "7d7a6d8", "size": size, "sha256": want, "source": "x"}}
res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
    unittest.defaultTestLoader.loadTestsFromNames(
        ["test_staged_artifacts.TheStagedImagesAreWhatTheRecordsName.test_a_rebuilt_slot_is_never_mistaken_for_the_executed_image"]))
out["names_another_commit"] = {"failed": len(res.failures) + len(res.errors),
                               "skipped": len(res.skipped), "run": res.testsRun}
print(json.dumps(out))
'''


class B_AnAbsentPathIsNotAnAbsentHistory(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.out = drive(B_DRIVER)

    def test_an_absent_commit_skips(self):
        self.assertTrue(self.out["absent_commit"].startswith("skip:"), self.out["absent_commit"])

    def test_a_path_missing_from_a_present_commit_fails(self):
        """The fourteen sites turned this into the same skip as an absent commit, so a
        freeze test could go quiet about a file that had been renamed out from under it."""
        self.assertTrue(self.out["absent_path"].startswith("fail:"), self.out["absent_path"])
        self.assertIn("moved or misnamed path", self.out["absent_path"])


class F_AFreezeTestMayNotChooseItsOwnBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.out = drive(F_DRIVER)

    def test_a_phrase_that_names_two_commits_fails(self):
        self.assertTrue(self.out["collision"].startswith("fail:"), self.out["collision"])
        self.assertIn("would have moved", self.out["collision"])

    def test_a_phrase_that_names_another_commit_than_the_pin_fails(self):
        self.assertTrue(self.out["moved"].startswith("fail:"), self.out["moved"])

    def test_a_real_freeze_test_fails_under_the_collision_rather_than_skipping(self):
        """Under `git log -1 --grep` this test would have silently compared the frozen tool
        against the NEWEST matching commit and passed."""
        r = self.out["freeze_test"]
        self.assertEqual((r["run"], r["skipped"]), (1, 0), r)
        self.assertEqual(r["failed"], 1, r)


class H_ARecordMayNotCertifyItself(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.out = drive(H_DRIVER)

    def test_a_rebuild_carrying_the_executed_commits_name_fails(self):
        r = self.out["kept_executed_commit"]
        self.assertEqual((r["run"], r["skipped"]), (1, 0), r)
        self.assertEqual(r["failed"], 1, r)
        self.assertIn("must never carry", self.out["message"])

    def test_a_rebuild_that_names_its_own_commit_is_accepted(self):
        """The rule is not "the slot must be the executed image" — a later export is
        legitimate. What it may not do is wear the executed image's identity."""
        r = self.out["names_another_commit"]
        self.assertEqual((r["run"], r["failed"], r["skipped"]), (1, 0, 0), r)


if __name__ == "__main__":
    unittest.main()
