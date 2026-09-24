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
        # Issue #47 opened U-GBP-036 and it cites this document; what must stay true is that the item this
        # design document was ABOUT (U-GBP-017) does not lean on it, and that any citation names its Issue
        un = read(UNKNOWNS)
        u017 = un[un.index("## U-GBP-017 (P2) —"):un.index("\n## ", un.index("## U-GBP-017 (P2) —"))]
        self.assertNotIn("GBC_PATH", u017)
        u036 = un[un.index("### U-GBP-036 —"):]
        self.assertEqual(un.count("GBC_PATH"), u036.count("GBC_PATH"),
                         "UNKNOWNS cites the design document outside U-GBP-036, which Issue #47 opened for it")
        # Issue #47: §V7.7 ingests the two runs that answered this document's stated gap and cites it for
        # that reason. No PRE-REGISTRATION may reference it, which is what this pin was always about, so the
        # citation must live inside §V7.7 and nowhere else on the page.
        hw = read(HW)
        v77 = hw[hw.index("### V7.7 "):]
        self.assertEqual(hw.count("GBC_PATH"), v77.count("GBC_PATH"),
                         "a section other than the §V7.7 ingestion references the design document")

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
        ids = sorted(set(re.findall(r"\bGBP-HW-\d+\b", d)))
        # Issue #46 promoted this document's §3 finding (272); Issue #47 ingested the two runs that answered
        # its stated gap (274, 275) and explained what RUN 24 did not deliver (276). Every one of them was
        # minted ELSEWHERE, and the rule is unchanged: each must sit in a paragraph that names the Issue
        # that did the minting, so a reader can always tell a pointer from a promotion.
        self.assertEqual(ids, ["GBP-HW-272", "GBP-HW-274", "GBP-HW-275", "GBP-HW-276"],
                         "the design document names a hardware id it should not")
        for i in ids:
            for para in [q for q in re.split(r"\n\s*\n", d) if i in q]:
                self.assertRegex(plain(para), r"GitHub Issue #4[67]",
                                 "%s is named in a paragraph that does not say who promoted it" % i)
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
        # Issue #47: GBP-HW-274 cites this document too, because the expectation it refutes was written
        # here first — which is the whole reason that entry is a result and not a shrug. The rule is that
        # only entries ABOUT this document's content may cite it, and they are named.
        citing = set()
        for m in re.finditer(r"GBC_PATH", ev):
            head = ev[ev.rfind("\n### ", 0, m.start()):][:24]
            citing.add(head.strip().split(" ")[1] if " " in head.strip() else head.strip())
        self.assertEqual(sorted(citing), ["GBP-HW-272", "GBP-HW-274"],
                         "EVIDENCE cites the design document from an entry that is not about it")
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
        # Issue #47: two runs were added to the archive AFTER this document was written, and §3 is kept as
        # written on purpose — its value is that it predates them. So the document must state the counts of
        # the archive MINUS the runs its own amendment names, and the amendment must name them.
        later = {"GBP-VIDEO-004_stream-0015-run23.log": "90", "GBP-VIDEO-004_stream-0015-run24.log": "92",
                 "GBP-PLAY-001_play-0001-run21.log": "92", "GBP-PLAY-001_play-0001-run22.log": "92",
                 "GBP-PLAY-001_play-0001-run25.log": "92", "GBP-PLAY-001_play-0001-run26.log": "92",
                 "GBP-VIDEO-004_stream-0015-run27.log": "92",
                 "GBP-VIDEO-004_stream-0015-run28.log": "92", "GBP-VIDEO-004_stream-0015-run29.log": "92",
                 # Issue #62: RUN 30, a FOURTH image (stream-0016) with a GBA flash cartridge. It postdates
                 # this document by a day and is named in GBP-HW-272's amendment, not here.
                 "GBP-AUDIO-001_stream-0016-run30.log": "92",
                 # Issue #67: RUN 31, archived under the experiment's name while its contents say AUDIO-001
                 "GBP-AUDIO-002_stream-0016-run31.log": "92",
                 # Issue #72 (2026-09-23): RUN 32, agb-sweep, the 46th log
                 "GBP-AUDIO-003_stream-0016-run32.log": "92",
                 # Issue #78 (2026-09-23): RUN 33 and RUN 34, sweep-0002
                 "GBP-AUDIO-004_stream-0016-run33.log": "92",
                 "GBP-AUDIO-003_stream-0016-run34.log": "92",
                 # Issue #85 (2026-09-23): RUN 35, sweep-0002
                 "GBP-AUDIO-006_stream-0016-run35.log": "92",
                 # Issue #90 (2026-09-23): RUN 37, drain-0001 on sweep-0002
                 "GBP-AUDIO-005_drain-0001-run37.log": "92",
                 # Issue #99 (2026-09-24): RUN 38, live-0001 on sweep-0002
                 "GBP-AUDIO-007_live-0001-run38.log": "92",
                 # Issue #103 (2026-09-24): RUN 39, trace-0001 on sweep-0002
                 "GBP-AUDIO-008_trace-0001-run39.log": "92",
                 # Issue #107 (2026-09-24): RUN 40, split-0001 on sweep-0002
                 "GBP-AUDIO-009_split-0001-run40.log": "92",
                 # Issue #112 (2026-09-24): RUN 41, game-0001 on Yoshi's Island, a real cartridge
                 "GBP-AUDIO-010_game-0001-run41.log": "92",
                 # Issue #115 (2026-09-24): RUN 42, game-0002 on Yoshi's Island
                 "GBP-AUDIO-011_game-0002-run42.log": "92"}
        for b, v in later.items():
            self.assertEqual(origins.get(b), v, b)
            counts[v] -= 1
        self.assertIn("RUN 24", d)
        self.assertIn("THE GAP OF THIS SECTION WAS FILLED 2026-09-22 (GitHub Issue #47)", d)
        self.assertIn("orig = 0x90 %d logs" % counts["90"], d)
        self.assertIn("orig = 0x92 %d logs" % counts["92"], d)
        self.assertIn("in every one of the %d logs, with no exception in either direction" % sum(counts.values()), d)
        # bit 0x01 never set, which is the gap the design exists to fill
        self.assertTrue(all(int(v, 16) & 0x01 == 0 for v in origins.values()))
        self.assertIn("READ 0 IN ALL THIRTY-FOUR", d)
        self.assertEqual(sum(counts.values()), 34)
        # the cartridge-less era is the 0x90 one, by the runs' own names
        cartless = {f for f, v in origins.items() if v == "90"}
        # RUN 23 is the one cartridge-less log that is NOT from the early era, and that is precisely why it
        # matters: a LATE build with an empty slot. It is exempt from the era-name check and asserted apart.
        run23 = "GBP-VIDEO-004_stream-0015-run23.log"
        self.assertIn(run23, cartless)
        self.assertTrue(all(re.search(r"(init|initirq|initirqa|initirqb|initirq4|avsvc|video|vstate)", f)
                            for f in cartless - {run23}), sorted(cartless))
        # Issue #52: play-0001 is a THIRD image whose four sessions also read 0x92; it is neither a
        # "color" nor a "stream" build, so it is named rather than swept into the era regex
        cart = {f for f, v in origins.items() if v == "92"}
        play = {f for f in cart if "play-0001" in f}
        self.assertEqual(len(play), 4, sorted(play))
        # Issue #90: drain-0001 (RUN 37) is a further image built on play-0001's service path; named the
        # same way, for the same reason
        drain = {f for f in cart if "drain-0001" in f}
        self.assertEqual(len(drain), 1, sorted(drain))
        # Issue #99: live-0001 (RUN 38) is built on drain-0001; named the same way, for the same reason
        live = {f for f in cart if "live-0001" in f}
        self.assertEqual(len(live), 1, sorted(live))
        # Issue #103: trace-0001 (RUN 39) is live-0001 with read-only records; named the same way
        trace = {f for f in cart if "trace-0001" in f}
        self.assertEqual(len(trace), 1, sorted(trace))
        # Issue #107: split-0001 (RUN 40) is trace-0001 with production split; named the same way
        split = {f for f in cart if "split-0001" in f}
        self.assertEqual(len(split), 1, sorted(split))
        # Issue #112: game-0001 (RUN 41) is live-0001 with §V25's changes; named the same way
        game = {f for f in cart if "game-0001" in f}
        self.assertEqual(len(game), 1, sorted(game))
        # Issue #115: game-0002 (RUN 42) is game-0001 with one post-session record; named the same way
        game2 = {f for f in cart if "game-0002" in f}
        self.assertEqual(len(game2), 1, sorted(game2))
        self.assertTrue(all(re.search(r"(color|stream)", f)
                            for f in cart - play - drain - live - trace - split - game - game2))

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
