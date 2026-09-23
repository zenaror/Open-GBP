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
        self.assertIn("EZ-Flash. Gravei a ROM na NOR e coloquei o flashcart no modo B", p)
        self.assertIn("the attribution caveat of §V7.6.11 STANDS, and it is now PERMANENT for this "
                      "instrument rather than pending an answer", p)
        self.assertIn("this is not a caveat nobody asked about, it is one that was asked, answered, and "
                      "kept", p)

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
            if "DECLINED" in body.splitlines()[0]:
                # THE POINT OF "DECLINED" IS THAT THE PRICE SURVIVES IT. Open means nobody
                # decided; retired means the evidence exists; declined means he weighed a priced
                # option and chose, so the price must still be there for the decision to be
                # reversible without re-deriving it.
                self.assertIn("the disposition", body, "residual %d is declined with no disposition" % (i + 1))
                self.assertIn("what is missing", body, "residual %d lost what it is missing" % (i + 1))
                self.assertIn("DECLINED, not retired and not open", body + block,
                              "the three states are not distinguished")
                continue
            if "ANSWERED" in body.splitlines()[0]:
                # an answered residual states what retired it AND what the answer was, because
                # "answered" without an outcome is worse than an open item: it looks closed
                self.assertIn("what retired it", body, "residual %d was answered by nothing" % (i + 1))
                self.assertIn("THE OUTCOME", body, "residual %d is answered with no outcome" % (i + 1))
                continue
            self.assertIn("what retires it", body, "residual %d has no exit" % (i + 1))
            self.assertIn("what it costs", body, "residual %d has no price" % (i + 1))
        p = plain(block)
        # the cheapest one is named as such, and the shape of the cheapest closure is stated
        self.assertIn("It WAS the cheapest item on this list, and it was paid", p)
        # Issue #57: that shape is now HISTORICAL -- it is the option the Operator weighed and
        # declined, and it is kept legible rather than deleted, because a declined option that
        # vanishes from the record cannot be reversed
        self.assertIn("That shape is now historical, and it is kept because a declined option has to stay "
                      "legible", p)
        self.assertIn("two sessions, a form in his hand, nothing to build", p)
        self.assertIn("exactly the option the Operator weighed and declined", p)
        # and R1 carries the lesson that produced it
        self.assertIn("it must be filled DURING the run", p)
        self.assertIn("a global report cannot become ten verdicts", p)

    def test_the_answered_residual_keeps_its_caveat_and_says_so(self):
        """R3 was the cheapest item and its answer was the one that keeps the limit."""
        p = plain(read(DOC))
        self.assertIn("THE ATTRIBUTION CAVEAT IS NOT LIFTED, AND IT IS NOW PERMANENT FOR THIS INSTRUMENT", p)
        self.assertIn("RECORDED AS PERMANENT, NOT PAID OFF", p)
        # an unanswered caveat and an answered-and-kept one must not look alike in a citation
        self.assertIn("an UNANSWERED caveat and an ANSWERED-AND-KEPT caveat look identical in a citation "
                      "unless the record says which", p)
        self.assertIn("GBP-HW-276 / -277", p)
        # the two volunteered details are kept as his, and the route is cited rather than interpreted
        self.assertIn("THE ROM IS IN NOR, and THE CARTRIDGE WAS IN MODE B", p)
        self.assertIn("what Mode B does inside the flashcart is not a claim this project makes", p)
        self.assertIn("§V3.7's route 1", p)

    def test_a_declined_residual_keeps_its_price_and_is_not_an_answer(self):
        """Issue #57: an unanswered item, an answered-and-kept one and a declined one
        must not look alike in a citation."""
        d = read(DOC)
        block = d[d.index("## 6. Named residuals"):d.index("## 7. ")]
        p = plain(block)
        self.assertIn("não vejo necessidade de outra run na fase 5", p)
        self.assertIn("OPEN nobody has decided", p)
        self.assertIn("RETIRED the evidence that closes it EXISTS", p)
        self.assertIn("DECLINED the Operator has weighed a priced option and chosen; THE EVIDENCE DOES NOT "
                      "EXIST and the residual is still named, with its price intact", p)
        self.assertIn("A declined residual keeps its price", p)
        # R1 and R2 are declined, and R1 still carries its full price
        r1 = block[block.index("R1  PER-KEY"):block.index("R2  THE CLOSING")]
        self.assertIn("DECLINED BY THE OPERATOR, 2026-09-22", r1)
        self.assertIn("what it costs", r1)
        self.assertIn("a ten-row form in his hand", plain(r1))

    def test_the_per_key_state_is_not_recorded_as_answered(self):
        p = plain(read(DOC))
        self.assertIn("the Operator judges the remaining resolution unnecessary, and the per-key resolution "
                      "is therefore NOT MEASURED", p)
        self.assertIn("It is not that the per-key question was answered", p)
        self.assertIn("W stays INCONCLUSIVE PER KEY", p)
        # his two halves are separated, and the record does not adopt his sentence as its own
        self.assertIn("\"ambos controles se comportam iguais\" SUPPORTED", p)
        self.assertIn("HIS OBSERVATION, and it stands as that", p)
        self.assertIn("which is not the same as adopting his sentence as its own", p)
        self.assertIn("it does not argue with the decision", p)

    def test_R4_survives_the_decline_and_says_what_it_now_rides_on(self):
        p = plain(read(DOC))
        self.assertIn("STILL OPEN, AND NOT AFFECTED BY R1's DECLINE", p)
        self.assertIn("ANY future physical run of ANY image satisfies it", p)
        self.assertIn("RIDES ON THE NEXT PHYSICAL RUN OF ANYTHING", p)
        self.assertIn("DECLINING R1 COSTS R4 NOTHING BUT TIME, and no door was closed", p)

    def test_the_older_ambiguity_is_closed_by_a_direct_answer_not_a_reading(self):
        p = plain(read(DOC))
        self.assertIn("na RUN estou usando ez-flash e o road rage paralelo apenas", p)
        self.assertIn("was relayed as a settled choice of instrument and was not one", p)
        self.assertIn("a later, direct answer about the runs themselves is better evidence than a better "
                      "reading of an earlier ambiguous one", p)


class TheAssessmentPromotedNothing(unittest.TestCase):
    def test_no_id_was_minted_and_no_status_moved(self):
        ev = read(EVIDENCE)
        self.assertEqual(max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 316)   # 285…294: Issue #62 (RUN 30 ingested, §V8.13)   # 295…300: Issue #67 (RUN 31 ingested, §V9.15); 301…302: #67's validation (the rate/layout split, U-GBP-039's probe); 303…307: #72, RUN 32; 308…311: #78, RUN 33 and RUN 34; 312: #79, duty()'s mechanism; 313: #80, the H-PWM decode; 314…316: #82, the block structure and the drain (§V18)
        self.assertEqual(max(int(n) for n in re.findall(r"^#{2,4} +U-GBP-(\d{3})\b", read(UNKNOWNS), re.M)), 43)   # 37, 38: Issue #62 (RUN 30)   # 39: Issue #67 (RUN 31)   # 40: Issue #72 (RUN 32, the first-press instrument defect)   # 41…43: Issue #82 (slice spacing, shorter reads, the in-block spread)
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
