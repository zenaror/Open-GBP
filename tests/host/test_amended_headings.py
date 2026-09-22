"""
tests/host/test_amended_headings.py — GitHub Issue #49: a heading that outlived
its status must carry a pointer to the amendment that changed it.

WHERE THIS CAME FROM. This project amends records ON TOP: the original words
stay and the correction is added below with its date and its Issue. That is the
right rule and it has one consequence that is easy to miss — when the amendment
changes a STATUS, the heading goes on saying what it said. Issue #48 found
`tools/reconcile.py` reporting GBP-HW-272 as HYPOTHESIS while the amendment in
its body had already moved that claim to CORROBORATED, in the one checkpoint
whose rule was that statuses are copied from EVIDENCE. The tool was fixed to
flag such entries. This test fixes the other half: the document.

THE RULE, recognised rather than introduced (`docs/RESEARCH_METHOD.md`, and the
precedent is `U-GBP-010`'s heading and `HARDWARE_TESTS.md` §V7's, both of which
have carried appended outcomes across many checkpoints): when an amendment
changes a claim's status, the heading gains a POINTER, appended after its
existing words, naming the date, the Issue and the status now held.

TWO THINGS MAKE THIS TEST WORTH HAVING RATHER THAN VACUOUS:

  * it drives its population from the TOOL, not from a list, so the next
    amended entry is caught without anybody remembering this file exists;
  * it asserts the population is not empty. A rule whose population has
    silently become zero passes forever and guards nothing.

And it guards the append itself: GBP-HW-272's heading must still START with the
exact words it had before the pointer was added. Rewriting a recorded claim is
the thing the convention exists to prevent, so a test that only checked for a
pointer would miss the failure that matters.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import reconcile  # noqa: E402

EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
METHOD = os.path.join(ROOT, "docs", "RESEARCH_METHOD.md")

# GBP-HW-272's heading EXACTLY as it stood before Issue #49 appended anything.
# Not a paraphrase: the bytes, so that "append only" is a checkable property.
ORIGINAL_272 = ("### GBP-HW-272 — the original CONTROL byte splits all 34 archived physical logs exactly at bit "
                "`0x02`: the 12 cartridge-less runs read `0x90`, the 22 runs with a cartridge read `0x92` — "
                "**FACT for the split**; that the bit REPORTS Game Pak presence is **HYPOTHESIS**, with an empty "
                "diagonal and a named breaker")

FLAG = "LATER AMENDMENT IN THE BODY"
# a pointer is a bold segment carrying a date and the Issue that made the change
POINTER = re.compile(r"\*\*\s*(\d{4}-\d{2}-\d{2})[^*]*Issue #(\d+)[^*]*\*\*")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def amended():
    """id -> heading, for every entry the sweep reports as carrying a later amendment."""
    return dict((i, head) for i, (status, head) in reconcile.evidence_status().items() if FLAG in status)


class EveryAmendedHeadingCarriesItsPointer(unittest.TestCase):
    def test_the_population_is_not_empty(self):
        """A rule with nothing in its population passes forever and guards nothing."""
        pop = amended()
        self.assertTrue(pop, "no entry is flagged as amended; either the flag broke or the tool did")
        self.assertIn("GBP-HW-272", pop, sorted(pop))

    def test_each_one_points_at_the_amendment_that_changed_it(self):
        for i, head in sorted(amended().items()):
            m = POINTER.search(head)
            self.assertTrue(m, "%s: the heading carries no dated pointer to its amendment:\n  %s" % (i, head))
            # the pointer is APPENDED: it is the last bold segment of the heading
            self.assertEqual(head.rindex(m.group(0)) + len(m.group(0)), len(head.rstrip()),
                             "%s: the pointer is not the last thing in the heading" % i)

    def test_the_words_before_the_pointer_are_the_words_that_were_there(self):
        """Append only. Rewriting a recorded claim is what the convention prevents."""
        ev = read(EVIDENCE)
        head = ev[ev.index("### GBP-HW-272 "):].splitlines()[0]
        self.assertTrue(head.startswith(ORIGINAL_272),
                        "GBP-HW-272's heading no longer starts with the words it had:\n  %s" % head)
        appended = head[len(ORIGINAL_272):]
        self.assertTrue(POINTER.search(appended), appended)
        p = plain(appended)
        self.assertIn("2026-09-22, Issue #47", p)
        self.assertIn("HYPOTHESIS → CORROBORATED", appended)
        self.assertIn("read it before copying a status from these words", p)
        self.assertIn("still NOT FACT", p)
        # and no status moved here: the amendment already held it
        self.assertIn("CLAIM 2 accordingly moves from HYPOTHESIS to CORROBORATED", plain(ev))


class TheConventionIsWrittenDownAsRecognised(unittest.TestCase):
    def test_it_is_in_the_method_with_its_precedent(self):
        m = plain(read(METHOD))
        self.assertIn("A heading that outlived its status — append the pointer, never rewrite the words", m)
        self.assertIn("recognised 2026-09-22, GitHub Issue #49", m)
        self.assertIn("This is recognised here, not introduced", m)
        self.assertIn("the heading gains a POINTER, appended after its existing words", m)
        self.assertIn("The existing words are not reordered, not softened and not requalified", m)
        self.assertIn("Appending a pointer is not a status change", m)
        # the precedent is cited, not invented
        self.assertIn("U-GBP-010", m)
        self.assertIn("appended across seven checkpoints", m)
        self.assertIn("tests/host/test_amended_headings.py", read(METHOD))

    def test_the_cited_precedent_is_really_in_those_pages(self):
        u = read(os.path.join(ROOT, "docs", "research", "UNKNOWNS.md"))
        h = read(os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md"))
        self.assertIn("## U-GBP-010 (P2 — **CLOSED 2026-09-21**", u)
        self.assertIn("2026-09-21, Issue #33: the routing FACT (hw, the runs) by the machine join of", u)
        self.assertIn("## V7 — GBP-INPUT-001:", h)
        self.assertIn("RUN 23 / RUN 24", h[h.index("## V7 — GBP-INPUT-001:"):].splitlines()[0])


if __name__ == "__main__":
    unittest.main()
