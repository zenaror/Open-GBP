"""
tests/host/test_external_reference.py — GitHub Issue #30: the gbhwdb reference
is recorded with its provenance, nothing third-party is committed, the raw log
drop is clean again, and U-GBP-009 gained a procedure without gaining an answer.

The property that matters most here is a negative one: a page documenting
SOMEBODY ELSE'S Game Boy Player must never become evidence about the
Operator's. So the tests check that no board revision is attributed to this
project's unit, that the reference says so in as many words, and that the
photographs the Operator supplied are out of `logs/` (which is the raw drop of
physical runs) without having been deleted.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXTERNAL = os.path.join(ROOT, "external", "README.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
PHOTOS = ("gekkio-1_03_pcb_front.jpg", "gekkio-1_04_pcb_back.jpg")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


class TheReferenceIsRecordedWithItsProvenance(unittest.TestCase):
    def test_the_web_reference_table_exists_and_carries_what_a_url_needs(self):
        e = plain(read(EXTERNAL))
        for tok in ("Web references — consulted, NOT checked out, NOTHING vendored",
                    "A page is not a repository: there is no commit to pin",
                    "https://gbhwdb.gekkio.fi/consoles/gbs/gekkio-1.html",
                    "CC BY-SA 4.0", "the site's source code is MIT",
                    "SOMEBODY ELSE'S Game Boy Player", "catalogued as gekkio-1",
                    "DOL-GBS-10",
                    "It is NOT evidence about the Operator's unit",
                    "scopes, qualifies or explains NOTHING about any run this project has executed",
                    "a PROCEDURE, not an answer"):
            self.assertIn(tok, e, tok)

    def test_the_licence_was_checked_and_is_the_reason_nothing_is_committed(self):
        e = plain(read(EXTERNAL))
        for tok in ("Why the photographs are not in the repository",
                    "moved, not deleted", "external/gbhwdb/",
                    "The licence would in fact permit redistribution with attribution — and that is exactly why they stay out",
                    "CC BY-SA's share-alike term would reach a repository that carries them",
                    "a URL costs nothing and avoids the question"):
            self.assertIn(tok, e, tok)

    def test_the_discrepancy_is_recorded_not_resolved(self):
        e = plain(read(EXTERNAL))
        for tok in ("One discrepancy, recorded rather than resolved",
                    "U3 as an NEC D442012A0Y", "gives the WRAM as U2", "the GBS-DOL as U4",
                    "the difference is noted and left open"):
            self.assertIn(tok, e, tok)


class NothingThirdPartyIsCommittedAndTheLogDropIsClean(unittest.TestCase):
    def test_no_photograph_is_tracked_anywhere_in_the_repository(self):
        import subprocess
        r = subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True, text=True, check=True)
        tracked = r.stdout.splitlines()
        for name in PHOTOS:
            self.assertFalse([p for p in tracked if p.endswith(name)], name)
        self.assertFalse([p for p in tracked if p.startswith("external/") and p != "external/README.md"],
                         "only external/README.md is tracked")

    def test_they_are_out_of_the_raw_log_drop_and_where_the_reference_says(self):
        logs = os.path.join(ROOT, "logs")
        if not os.path.isdir(logs):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        self.assertFalse(os.path.isdir(os.path.join(logs, "motherboard")),
                         "logs/ is the raw drop of physical runs; the board photographs do not belong in it")
        for name in PHOTOS:
            self.assertFalse(os.path.exists(os.path.join(logs, name)), name)
        # moved, not deleted: when the machine still has them, they are where the reference says
        dest = os.path.join(ROOT, "external", "gbhwdb")
        if os.path.isdir(dest):
            for name in PHOTOS:
                self.assertTrue(os.path.exists(os.path.join(dest, name)),
                                "%s is neither in logs/ nor in external/gbhwdb/: it must be MOVED, never deleted" % name)


class TheUnknownGainedAProcedureAndNoAnswer(unittest.TestCase):
    def section(self):
        t = read(UNKNOWNS)
        i = t.index("## U-GBP-009 ")
        return t[i:t.index("\n## ", i)]

    def test_the_status_did_not_move(self):
        s = self.section()
        self.assertIn("## U-GBP-009 (P3) — Board-revision differences", s)
        self.assertIn("the user's unit revision is unknown", s)
        self.assertIn("The status does not\nchange: this stays OPEN, P3, and NO revision is attributed to the Operator's\nunit.", s)
        # the first paragraph is untouched
        self.assertIn("DOL-GBS-01/10/20, CPU AGB A vs A E, 16 Mb vs 128 Mb RAM. No behavioral\ndifference is documented anywhere;", s)

    def test_the_procedure_and_the_standing_decision_are_both_there(self):
        s = plain(self.section())
        for tok in ("A procedure exists, added 2026-09-22 (GitHub Issue #30)",
                    "printed on the PCB itself, as DOL-GBS-xx beside the \"© 2003 Nintendo\" line",
                    "a matter of LOOKING, not of measuring",
                    "IT DOCUMENTS SOMEBODY ELSE'S CONSOLE",
                    "no revision may be inferred from it for ours",
                    "THE OPERATOR WILL NOT BE ASKED TO OPEN HIS UNIT",
                    "Recorded so the decision is not revisited by accident",
                    "if a divergence appears between what this project measures and what another source reports"):
            self.assertIn(tok, s, tok)

    def test_no_revision_is_attributed_to_this_project_anywhere(self):
        """The one thing this source must never be allowed to do."""
        for p in (UNKNOWNS, EVIDENCE, os.path.join(ROOT, "docs", "hardware", "GBS-DOL.md"),
                  os.path.join(ROOT, "docs", "HANDOFF.md")):
            t = read(p)
            for m in re.finditer(r"DOL-GBS-(01|10|20)\b", t):
                window = plain(t[max(0, m.start() - 260):m.start() + 260])
                self.assertNotRegex(window, r"(the Operator's|the user's|our|this project's) (unit|console|board|Game Boy Player) is",
                                    "%s attributes a board revision to this project's hardware" % os.path.relpath(p, ROOT))


if __name__ == "__main__":
    unittest.main()
