"""
tests/host/test_phase5_assessment.py — GitHub Issue #42: Phase 5 assessed
against its acceptance criterion.

THE VERDICT IS A JUDGEMENT AND A TEST CANNOT CHECK A JUDGEMENT. What it can
check is that the judgement is stated once and identically everywhere, that the
evidence it leans on is the evidence that exists, and that the things which
would make it dishonest are absent:

  * the verdict says the same words in the assessment, the ROADMAP and the
    HANDOFF — a phase whose status differs between three documents has no
    status;
  * the last two days' tooling is excluded from the evidence BY NAME, because
    a checkpoint that improved how the project decides things is the easiest
    thing to mistake for progress against a criterion about controlling a game;
  * every residual carries what retires it AND what that costs — "a residual
    without a price is a wish";
  * nothing was promoted: no id minted, no status moved, and the per-pad
    corroboration the head runs add is explicitly NOT a promotion.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOC = os.path.join(ROOT, "docs", "research", "PHASE5_ASSESSMENT.md")
ROADMAP = os.path.join(ROOT, "docs", "ROADMAP.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")

VERDICT = "SATISFIED WITH NAMED RESIDUALS"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


class TheVerdictIsStatedOnceAndIdentically(unittest.TestCase):
    def test_all_three_documents_say_the_same_thing(self):
        self.assertIn("**VERDICT: %s.**" % VERDICT, read(DOC))
        self.assertIn("**PHASE 5 VERDICT: %s.**" % VERDICT, read(DOC))
        self.assertIn("PHASE 5 VERDICT — %s" % VERDICT, plain(read(ROADMAP)))
        self.assertIn(VERDICT, read(HANDOFF))
        # and no other verdict word appears as this phase's outcome
        for other in ("PHASE 5 VERDICT: SATISFIED.", "PHASE 5 VERDICT: NOT SATISFIED"):
            self.assertNotIn(other, read(DOC))

    def test_the_roadmap_carries_the_assessment_and_nothing_more(self):
        r = plain(read(ROADMAP))
        self.assertIn("ASSESSED 2026-09-22 (GitHub Issue #42)", r)
        self.assertIn("docs/research/PHASE5_ASSESSMENT.md", r)
        self.assertIn("The assessment promotes nothing, mints no id and changes no status", r)


class TheEvidenceIsWeighedHonestly(unittest.TestCase):
    def test_the_infrastructure_is_excluded_by_name(self):
        p = plain(read(DOC))
        self.assertIn("None of them is a game being controlled", p)
        self.assertIn("If the criterion is met, it is met by the runs", p)
        for tok in ("guards", "skip ledger", "tools/v7611.py", "reconciliation sweep"):
            self.assertIn(tok, p, tok)

    def test_each_term_is_assessed_with_what_it_does_not_reach(self):
        d = read(DOC)
        for term in ('"A real game"', '"using the GameCube controller"', '"controlled"', '"reliably"'):
            self.assertIn(term, d, term)
        self.assertEqual(d.count("What it does not reach"), 3)
        p = plain(d)
        self.assertIn("the Operator's definition of reliably, fixed before any data existed and therefore "
                      "binding on this assessment", p)

    def test_the_against_side_is_named_and_not_absorbed(self):
        p = plain(read(DOC))
        self.assertIn("W is INCONCLUSIVE for every key in all four runs", p)
        self.assertIn("A global impression is not ten verdicts", p)
        self.assertIn("step 15, the closing sweep of the ten keys AFTER minutes of play, was never performed "
                      "on either pad", p)
        self.assertIn("has no scripted evidence at all", p)
        self.assertIn("Question T is INCONCLUSIVE", p)
        self.assertIn("He declared the title and not the form", p)
        self.assertIn("the attribution caveat of §V7.6.11 stands and cannot be lifted", p)

    def test_both_sides_of_the_verdict_are_argued(self):
        p = plain(read(DOC))
        self.assertIn("Why not NOT SATISFIED", p)
        self.assertIn("Why not SATISFIED", p)
        self.assertIn("The phase's goal was demonstrated", p)
        self.assertIn("quietly lowering the bar the project set for itself", p)
        self.assertIn("The middle is not a compromise, it is the accurate description", p)

    def test_the_head_runs_corroborate_and_do_not_promote(self):
        p = plain(read(DOC))
        self.assertIn("rests on the Operator having pressed the list in order, with no independent witness, "
                      "so it CORROBORATES and promotes nothing", p)
        self.assertIn("the per-pad corroboration of §4 is not a promotion", p)


class EveryResidualHasAPrice(unittest.TestCase):
    def test_six_residuals_each_with_what_retires_it_and_what_it_costs(self):
        d = read(DOC)
        block = d[d.index("## 6. Named residuals"):d.index("## 7. ")]
        self.assertIn("A residual without a price is a wish", plain(block))
        starts = [m.start() for m in re.finditer(r"^R\d  [A-Z]", block, re.M)]
        self.assertEqual(len(starts), 6, starts)
        # each residual carries BOTH halves inside its own block, which is the rule
        for i, s in enumerate(starts):
            body = block[s:starts[i + 1]] if i + 1 < len(starts) else block[s:]
            self.assertIn("what retires it", body, "residual %d has no exit" % (i + 1))
            self.assertIn("what it costs", body, "residual %d has no price" % (i + 1))
        p = plain(block)
        # the cheapest one is named as such, and the shape of the cheapest closure is stated
        self.assertIn("THE CHEAPEST ITEM ON THIS LIST", p)
        self.assertIn("R1 + R2 + R4 are ONE run per pad", p)
        self.assertIn("two sessions, a form in his hand, and nothing to build", p)
        # and R1 carries the lesson that produced it
        self.assertIn("it must be filled DURING the run", p)
        self.assertIn("a global report cannot become ten verdicts", p)

    def test_the_unpayable_case_is_stated_rather_than_assumed_away(self):
        p = plain(read(DOC))
        self.assertIn("an original cartridge he may not own -- in which case the caveat is permanent for this "
                      "instrument and is recorded as such, not paid off", p.replace("—", "--"))


class TheAssessmentPromotedNothing(unittest.TestCase):
    def test_no_id_was_minted_and_no_status_moved(self):
        ev = read(EVIDENCE)
        self.assertEqual(max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 284)
        self.assertEqual(max(int(n) for n in re.findall(r"^#{2,4} +U-GBP-(\d{3})\b", read(UNKNOWNS), re.M)), 36)
        self.assertNotRegex(read(DOC), r"^### GBP-", re.M)
        p = plain(read(DOC))
        self.assertIn("It promotes nothing and mints no evidence id", p)
        self.assertIn("the routing stays FACT (run-scoped) exactly as §V7.4 left it", p)

    def test_the_sweep_outcome_is_recorded_including_nothing(self):
        p = plain(read(DOC))
        self.assertIn("Outcome: nothing to correct", p)
        self.assertIn("This is recorded including the \"nothing\"", p)
        self.assertIn("checked and left, not overlooked", p)

    def test_the_owners_of_what_phase_5_does_not_establish_are_named(self):
        block = read(DOC)
        block = block[block.index("## 7. What Phase 5 does NOT establish"):block.index("## 8. ")]
        for owner in ("Phase 6", "Phase 7", "Phase 8", "Phase 9", "Phase 12", "U-GBP-035", "U-GBP-036"):
            self.assertIn(owner, block, owner)

    def test_the_standing_declaration_carries_exactly_what_supports_it(self):
        p = plain(read(DOC))
        self.assertIn("what now supports that is K = AGREE over the scripted head", p)
        self.assertIn("That is exactly what supports it, and no more", p)
        self.assertIn("it says nothing about what the game did with them", p)


if __name__ == "__main__":
    unittest.main()
