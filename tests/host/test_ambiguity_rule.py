"""
tests/host/test_ambiguity_rule.py — GitHub Issue #56: the method rule that was
living in a phase's assessment, and the one thing that would undo the point of
moving it.

THE RULE: a later direct answer about the thing outranks a better reading of an
earlier ambiguous statement about it — and, operationally, when an Operator
statement is ambiguous the repair is to ASK about the thing rather than to
re-read the sentence more carefully.

WHAT THIS TEST IS REALLY FOR. The rule now exists in one place and is POINTED
AT from a second. That is deliberate: two copies of a rule drift apart, which
is the class Issue #29 exists about, and a rule about not letting records drift
should not begin by drifting. So the test's job is not to confirm the words
exist — it is to catch the day somebody "helpfully" pastes the rule's text into
AGENTS.md as well, and the day somebody rewrites §7b instead of leaving it as
the case the rule cites.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
METHOD = os.path.join(ROOT, "docs", "RESEARCH_METHOD.md")
AGENTS = os.path.join(ROOT, "AGENTS.md")
ASSESSMENT = os.path.join(ROOT, "docs", "research", "PHASE5_ASSESSMENT.md")

TITLE = "A later direct answer outranks a better reading of an earlier ambiguous one"
OLD_SENTENCE = "na RUN estou usando ez-flash e o road rage paralelo apenas"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def rule():
    t = read(METHOD)
    i = t.index("### " + TITLE)
    return t[i:t.index("\n### ", i + 1)]


class TheRuleIsInTheMethodWithItsCase(unittest.TestCase):
    def test_it_takes_the_shape_of_its_two_siblings(self):
        t = read(METHOD)
        for sibling in ("### A reference figure is defined by what the element CONTAINS",
                        "### A heading that outlived its status"):
            self.assertIn(sibling, t, sibling)
        head = "### %s (2026-09-22, GitHub Issue #56)" % TITLE
        self.assertIn(head, t)

    def test_both_halves_are_stated(self):
        p = plain(rule())
        self.assertIn("THE EVIDENCE HALF", p)
        self.assertIn("THE OPERATIONAL HALF", p)
        self.assertIn("THE REPAIR IS TO ASK ABOUT THE THING", p)
        self.assertIn("A more careful reading of an ambiguous sentence produces a more confident guess, "
                      "which is the failure mode, not the fix", p)

    def test_the_case_is_cited_and_the_old_sentence_is_left_unread(self):
        p = plain(rule())
        self.assertIn(OLD_SENTENCE, p)
        self.assertIn("EZ-Flash. Gravei a ROM na NOR e coloquei o flashcart no modo B", p)
        self.assertIn("It was flagged as ambiguous at the time rather than resolved, which was right", p)
        self.assertIn("The old sentence is still unread, and that is part of the rule rather than an "
                      "omission", p)


class TheRuleIsPointedAtAndNotCopied(unittest.TestCase):
    """The one failure that would undo the point of moving it."""

    def test_agents_carries_the_pointer(self):
        a = plain(read(AGENTS))
        self.assertIn("asks about the thing rather than re-reading the sentence more carefully", a)
        self.assertIn("docs/RESEARCH_METHOD.md", a)
        self.assertIn(TITLE, a)
        self.assertIn("two copies of a rule drift apart", a)

    def test_agents_does_NOT_carry_a_second_copy(self):
        a = read(AGENTS)
        # the distinctive body of the rule lives in ONE file
        for body in ("THE EVIDENCE HALF", "THE OPERATIONAL HALF", OLD_SENTENCE,
                     "Gravei a ROM na NOR"):
            self.assertNotIn(body, a, "AGENTS.md has grown a copy of the rule's body: %r" % body)
        # and the pointer is one bullet, not a section
        self.assertNotIn("### " + TITLE, a)

    def test_the_rule_body_exists_in_exactly_one_file(self):
        """Strict on purpose: even the DEVLOG entry that MOVED the rule points instead of
        copying, which is the only demonstration of the rule that costs nothing."""
        hits = []
        for base, _, files in os.walk(os.path.join(ROOT, "docs")):
            for fn in files:
                if fn.endswith(".md") and "THE OPERATIONAL HALF" in read(os.path.join(base, fn)):
                    hits.append(os.path.relpath(os.path.join(base, fn), ROOT))
        if os.path.exists(AGENTS) and "THE OPERATIONAL HALF" in read(AGENTS):
            hits.append("AGENTS.md")
        self.assertEqual(hits, ["docs/RESEARCH_METHOD.md"], hits)


class TheCaseKeepsItsWords(unittest.TestCase):
    def test_section_7b_is_intact_and_gained_only_a_pointer(self):
        t = read(ASSESSMENT)
        i = t.index("## 7b. An older ambiguity")
        body = t[i:t.index("\n## ", i + 1)]
        p = plain(body)
        # its original words, unchanged
        self.assertIn(OLD_SENTENCE, p)
        self.assertIn("was relayed as a settled choice of instrument and was not one", p)
        self.assertIn("a later, direct answer about the runs themselves is better evidence than a better "
                      "reading of an earlier ambiguous one", p)
        # and the appended pointer, which says it is a pointer
        self.assertIn("POINTER, appended 2026-09-22 (GitHub Issue #56), the words below unchanged", p)
        self.assertIn("This section remains the case", p)
        self.assertIn("Appending rather than rewriting is #49's convention", p)


if __name__ == "__main__":
    unittest.main()
