"""
tests/host/test_gbc_path.py — GitHub Issue #31: the GB/GBC design document
(`docs/research/GBC_PATH.md`) says what it is allowed to say, and its one
derived result is RECOMPUTED from the archived logs rather than quoted.

The document is design-only Phase 7 material written while Phase 5 is current,
so most of what matters is what it does NOT do: no run, no pre-registration, no
evidence id, no status change, no phase crossing. That is pinned here, together
with the substance a later checkpoint will rely on:

  * the two Operator observations stay OPERATOR OBSERVATION, the second
    explicitly a recollection;
  * his architectural framing is CHECKED against docs/hardware rather than
    adopted, and the places the pages are silent are named;
  * the CONTROL split (12 logs without a Game Pak read 0x90, 22 with one read
    0x92, bit 0x01 never once set) is RE-DERIVED from captures/local when the
    archive is present, so the document cannot drift from the logs;
  * the experiments carry their gates and their verdicts, including the
    not-changed and not-sent outcomes, before any hardware.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOC = os.path.join(ROOT, "docs", "research", "GBC_PATH.md")
LOCAL = os.path.join(ROOT, "captures", "local")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
REGISTERS = os.path.join(ROOT, "docs", "protocol", "REGISTERS.md")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


class ItIsDesignOnlyAndSaysSo(unittest.TestCase):
    def test_the_status_line_and_the_non_authorisation(self):
        d = plain(read(DOC))
        for tok in ("Status of this document: research, DESIGN ONLY",
                    "It authorises nothing", "Phase 5 is current; Phase 7 is two gates ahead",
                    "CLAUDE.md §26 permits crossing a gate early only for a blocking feasibility question and none of this is one",
                    "No run, no pre-registration, no code, no evidence id, no status change",
                    "Do not assume behavior observed in GBA mode also applies to GB/GBC mode",
                    "no phase-gate crossing", "is offered to a promotion checkpoint, not performed here"):
            self.assertIn(tok, d, tok)

    def test_it_mints_nothing_and_touches_no_status(self):
        d = read(DOC)
        self.assertEqual(re.findall(r"\bGBP-GBC-\d+\b", d), [])
        # it may CITE an open unknown, but it must not restate its status
        self.assertIn("U-GBP-017", d)
        self.assertIn("U-GBP-017 stays open", plain(d))
        self.assertNotIn("GBC_PATH", read(UNKNOWNS))
        self.assertNotIn("GBC_PATH", read(HW))     # no pre-registration references it

    def test_a_promotion_made_elsewhere_may_be_POINTED_AT_but_never_performed_here(self):
        """GitHub Issue #46 promoted this document's §3 finding as GBP-HW-272.

        The original guard forbade the string `GBP-HW-2` outright, which was the
        right rule while nothing had been promoted and the wrong one afterwards:
        a dangling offer nobody can follow is not an improvement on a design
        document that mints its own id. So the rule is now the distinction the
        Issue turns on — the document may say WHERE a promotion happened, and
        may not BE one. Every hardware id it names sits in the pointer
        paragraph, the pointer names the Issue and the file that did the
        minting, and the offer paragraphs keep the words they had.
        """
        d = read(DOC)
        ids = re.findall(r"\bGBP-HW-\d+\b", d)
        self.assertEqual(sorted(set(ids)), ["GBP-HW-272"], "the design document names a hardware id it should not")
        paras = [p for p in re.split(r"\n\s*\n", d) if "GBP-HW-272" in p]
        self.assertEqual(len(paras), 1, "GBP-HW-272 is named outside the single pointer paragraph")
        p = plain(paras[0])
        self.assertIn("PROMOTED 2026-09-22 (GitHub Issue #46) as GBP-HW-272", p)
        self.assertIn("the split is FACT", p)
        self.assertIn("the causal reading is HYPOTHESIS", p)
        self.assertIn("without closing the item", p)
        self.assertIn("The paragraphs below are the offer as this document made it, kept as written", p)
        # the design text still disclaims minting, and still offers rather than promotes
        pd = plain(d)
        self.assertIn("This document mints no evidence id and changes no status", pd)
        self.assertIn("is offered to a promotion checkpoint, not performed here", pd)
        # the pointer is not dangling: the id exists, in the file that minted it
        self.assertIn("### GBP-HW-272 ", read(EVIDENCE))
        # and EVIDENCE names this document only as PROVENANCE, inside that entry
        ev = read(EVIDENCE)
        for m in re.finditer(r"GBP_PATH|GBC_PATH", ev):
            entry = ev.rfind("\n### ", 0, m.start())
            self.assertTrue(ev[entry:entry + 20].startswith("\n### GBP-HW-272"),
                            "EVIDENCE cites the design document outside GBP-HW-272")
        self.assertIn("which offered it and promoted nothing", plain(ev))

    def test_the_observations_stay_the_operators(self):
        d = plain(read(DOC))
        for tok in ("Both are OPERATOR OBSERVATION", "his report, not a recorded test, and not promoted by being written down",
                    "simply runs the tests and ends to generate the LOG",
                    "mode not supported, not the runtime breaks on unexpected media",
                    "Recorded explicitly as a recollection of using the Disc, not a test performed for this project",
                    "No log of 1.1 exists in this repository"):
            self.assertIn(tok, d, tok)


class TheFramingIsCheckedNotAdopted(unittest.TestCase):
    def test_it_separates_agreement_from_silence(self):
        d = plain(read(DOC))
        for tok in ("WHERE THE PAGES AGREE", "WHERE THE PAGES ARE SILENT, so his account is not confirmed by them",
                    "the NEC custom chip on the Game Boy Player board that sits between the GameCube HSP and the CPU AGB A",
                    "nothing in docs/ says how a CPU AGB A runs a GB/GBC cartridge",
                    "It is general Game Boy Advance knowledge, not a finding of this project, and this document does not adopt it",
                    "the L / R screen stretch in GB/GBC mode is the AGB's OWN behaviour",
                    "THIS PROJECT'S RUNTIME ALREADY INJECTS THAT WORD", "It is a PREDICTION, not a claim",
                    "Nothing in his framing contradicts the pages"):
            self.assertIn(tok, d, tok)

    def test_the_quoted_page_sentence_is_really_in_the_page(self):
        self.assertIn("the NEC custom chip on the Game Boy Player board that sits", read(os.path.join(ROOT, "docs", "hardware", "GBS-DOL.md")))
        # and the CONTROL bits the document leans on are the ones REGISTERS.md records
        reg = read(REGISTERS)
        self.assertIn("CART_IS_GB", reg)
        self.assertIn("CART_INSERTED", reg)


class TheDerivedResultIsRecomputedFromTheArchive(unittest.TestCase):
    def control_origins(self):
        out = {}
        for fn in sorted(os.listdir(LOCAL)):
            if not fn.endswith(".log"):
                continue
            m = re.search(r"CONTROL semantic orig=([0-9a-f]+)", read(os.path.join(LOCAL, fn)))
            if m:
                out[fn] = m.group(1)
        return out

    def test_the_split_the_document_states_is_the_split_the_logs_carry(self):
        if not os.path.isdir(LOCAL):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        origins = self.control_origins()
        if not origins:
            self.skipTest("no local archive on this host (captures/local is ignored)")
        counts = {}
        for v in origins.values():
            counts[v] = counts.get(v, 0) + 1
        self.assertEqual(sorted(counts), ["90", "92"], "the archive carries a CONTROL value the document does not know: %s" % counts)
        d = plain(read(DOC))
        self.assertIn("orig = 0x90 %d logs" % counts["90"], d)
        self.assertIn("orig = 0x92 %d logs" % counts["92"], d)
        self.assertIn("in every one of the %d logs, with no exception in either direction" % sum(counts.values()), d)
        # bit 0x01 never set, which is the gap the design exists to fill
        self.assertTrue(all(int(v, 16) & 0x01 == 0 for v in origins.values()))
        self.assertIn("READ 0 IN ALL THIRTY-FOUR", d)
        self.assertEqual(sum(counts.values()), 34)
        # the cartridge-less era is the 0x90 one, by the runs' own names
        cartless = {f for f, v in origins.items() if v == "90"}
        self.assertTrue(all(re.search(r"(init|initirq|initirqa|initirqb|initirq4|avsvc|video|vstate)", f) for f in cartless), sorted(cartless))
        self.assertTrue(all(re.search(r"(color|stream)", f) for f, v in origins.items() if v == "92"))

    def test_the_document_says_what_the_split_does_not_support(self):
        d = plain(read(DOC))
        for tok in ("What this supports, stated carefully and NOT promoted here",
                    "promoting it belongs to a promotion checkpoint the Orchestrator opens",
                    "This document mints no evidence id and changes no status",
                    "What it does NOT support. Nothing about bit 0x01, which has one observed state",
                    "one console, one GBP, one flashcart as the only cartridge"):
            self.assertIn(tok, d, tok)


class TheExperimentsCarryTheirGates(unittest.TestCase):
    def test_experiment_one_predicts_before_the_data(self):
        d = plain(read(DOC))
        for tok in ("EXPERIMENT ONE — the cartridge type bit, at the cost of one boot",
                    "It needs no new code and no new image",
                    "The prediction, written before the data",
                    "orig = 0x93", "orig = 0x92 (indistinguishable from a GBA cartridge)", "orig = 0x90 (a different and more interesting result)",
                    "The verdict is the byte, not an interpretation of it",
                    "which is a finding and not a failure", "What it would not establish"):
            self.assertIn(tok, d, tok)

    def test_experiment_two_has_a_reachable_negative_and_a_machine_half(self):
        d = plain(read(DOC))
        for tok in ("EXPERIMENT TWO — the L/R stretch, the Operator's prediction made testable",
                    "the SENT / NOT SENT split of §V7.6.11 applies unchanged",
                    "THE MACHINE CANNOT SAY the picture \"filled the screen\"",
                    "NOT CHANGED the word was sent (KEY record) and nothing changed. A REAL RESULT",
                    "the first divergence between GBA and GB/GBC mode this project would have measured",
                    "NOT SENT the word never left the runtime: an input-path finding, not a GB/GBC finding",
                    "The order matters", "§4.1 before §4.2"):
            self.assertIn(tok, d, tok)

    def test_the_delivery_section_verifies_rather_than_assumes(self):
        d = plain(read(DOC))
        for tok in ("Everdrive GB X7", "controlled delivery of a chosen image",
                    "to be verified when Phase 7 opens, never assumed",
                    "its menu is in the measurement", "the same question the EZ-Flash menu raised for GBA",
                    "the three-value axis is kept", "nothing is inferred from the GBA route",
                    # which cartridge is a GATE ITEM he answers at the launch, not a premise this design needs now
                    "WHICH CARTRIDGE IS A GATE ITEM, answered at the launch and not a premise of this design",
                    "titles he does not know", "would be blocked on something nobody can answer from here",
                    "Title unknown, an unofficial GB/GBC cartridge, booted straight in\" is a complete and admissible declaration",
                    "judged on the day from what is on screen, not from a title nobody has"):
            self.assertIn(tok, d, tok)


if __name__ == "__main__":
    unittest.main()
