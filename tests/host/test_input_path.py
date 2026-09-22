"""
tests/host/test_input_path.py — the Phase 5 entry checkpoint (GitHub Issue #18,
2026-09-21): the input path reconstructed on paper.

Pinned: INPUT_PATH.md keeps L1 / L2 / L3 as separate sections and labels the
mapping a POLICY; the U-GBP-010 outcome is stated once, in the same words in
INPUT_PATH.md, UNKNOWNS.md and the ROADMAP, and the unknown was NOT closed by
that checkpoint (Issue #24, 2026-09-21, later closed it on RUN 14 / RUN 15);
the physical record was declared empty in INPUT_PATH.md (a dated statement);
no order is adopted (the words "adopted", "defaulted" appear only in their
negation); every evidence id the document cites exists; the keypad findings
continue the GBP-KEY namespace (002…005; 006 / 007 / 008 / 009 followed) and
Issue #18 minted no GBP-HW id (the highest is now 265, from Issue #24);
Dolphin's order stayed H in REGISTERS.md until Issue #26 promoted it to C
(never FACT); the external register lists Enhanced
mGBA with its exact commit; the ROADMAP's Phase 5 status and the HANDOFF row
exist; and the keypad code that Issue #19 (2026-09-21) later added is the
module §7 named.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOC = os.path.join(ROOT, "docs", "research", "INPUT_PATH.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
ROADMAP = os.path.join(ROOT, "docs", "ROADMAP.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
REGISTERS = os.path.join(ROOT, "docs", "protocol", "REGISTERS.md")
EXTERNAL = os.path.join(ROOT, "external", "README.md")
OUTCOME = "RESOLVED STATICALLY at CORROBORATED"
MGBA_COMMIT = "8692b26b6d882c049bc70958e0ef8ba0e607a4b7"
# test-id FAMILIES are not evidence ids: VIDEO / INIT / AV / PROBE / BASELINE were always excluded, and PLAY joins them
# with Issue #39 (GBP-PLAY-001 is the playable image's embedded id; its record in HARDWARE_TESTS comes with a pre-registration)
ID = re.compile(r"\b(GBP-(?!VIDEO|BBA|INIT|AV|PROBE|BASELINE|PLAY)[A-Z]+-\d{3}|ENV-[A-Z]+-\d{3}|U-GBP-\d{3}|U-ENV-\d{3})\b")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def flat(s):
    return re.sub(r"\s+", " ", s)


def defined_ids():
    ids = set()
    for p in (EVIDENCE, UNKNOWNS):
        for m in re.finditer(r"^#{2,4} +((?:GBP|ENV)-[A-Z]+-\d{3}|U-(?:GBP|ENV)-\d{3})\b", read(p), re.M):
            ids.add(m.group(1))
    return ids


class TheLayersAreKeptApart(unittest.TestCase):
    def test_three_layer_sections_in_order_and_the_policy_is_labelled(self):
        t = read(DOC)
        l1, l2, l3 = (t.index("## 1. L1 — the GBS-DOL KEYPAD window"), t.index("## 2. L2 — the logical GBA button set"),
                      t.index("## 3. L3 — GameCube controller → logical GBA"))
        self.assertLess(l1, l2)
        self.assertLess(l2, l3)
        self.assertIn("### 3.2 The policy — options and a recommendation (POLICY)", t)
        self.assertIn("never a device fact", flat(t))
        self.assertIn("The physical record starts from nothing.", t)

    def test_the_reference_survey_and_the_architecture_and_the_guarantee_exist(self):
        t = read(DOC)
        for h in ("## 4. Reference survey — provenance and authority (Deliverable B)",
                  "## 5. The static attempt on U-GBP-010 (Deliverable C)",
                  "## 6. Why no physical experiment is designed here (Deliverable D)",
                  "## 7. Input architecture on paper (Deliverable E)",
                  "## 8. The latency observability guarantee (Deliverable F)"):
            self.assertEqual(t.count(h), 1, h)
        f = flat(t)
        for s in ("gbp_input_map", "gbp_keypad_encode", "gbp_keypad_write", "write_block", "pump slot",
                  "gbp_time64", "40 500 000 Hz", "no latency figure or claim", "No existing sidecar semantics change",
                  "Stop-condition check"):
            self.assertIn(s, f, s)


class TheStaticAttemptIsStatedOnceAndStaysOpen(unittest.TestCase):
    def test_the_outcome_appears_in_the_three_records_and_the_unknown_closed_only_later_on_hardware(self):
        self.assertEqual(read(DOC).count("U-GBP-010 static attempt (2026-09-21): " + OUTCOME), 1)
        self.assertIn("Outcome: RESOLVED\nSTATICALLY at CORROBORATED; NOT closed", read(UNKNOWNS))
        self.assertIn(OUTCOME, flat(read(ROADMAP)))
        self.assertIn(OUTCOME, flat(read(HANDOFF)))
        m = re.search(r"^## U-GBP-010\b.*$", read(UNKNOWNS), re.M)
        self.assertIsNotNone(m)
        # the static attempt did not close it; RUN 14 / RUN 15 did (Issue #24, §V7.2), on the physical condition
        self.assertIn("CLOSED 2026-09-21", m.group(0))
        self.assertIn("RUN 14 and RUN 15", m.group(0))
        s5 = read(DOC).split("## 5.")[1].split("## 6.")[0]
        self.assertNotIn("NOT RESOLVABLE STATICALLY", s5)
        self.assertEqual(s5.count("RESOLVED STATICALLY"), 1)

    def test_no_order_is_adopted_or_defaulted_and_dolphin_stays_h(self):
        t = read(DOC)
        for phrase in ("no bit order was adopted", "nothing above is a physical FACT", "CORROBORATED**. It is **not** a physical FACT"):
            self.assertIn(phrase, t, phrase)
        f = flat(t)
        for phrase in ("no bit order was adopted, implemented, tabulated as Open-GBP's own, or defaulted",
                       "REGISTERS.md keeps Dolphin's order at H", "GBI's `0x0304` was **not** used as evidence"):
            self.assertIn(phrase, f.replace("`REGISTERS.md`", "REGISTERS.md"), phrase)
        regs = read(REGISTERS)
        self.assertNotIn("H (L/R bit order)", regs)          # Issue #26: C; Issue #33: F (hw, run-scoped) with the history kept
        self.assertIn("C — was H until 2026-09-21", regs)
        self.assertIn("L/R bit order: F (hw, run-scoped) since 2026-09-21", regs)
        self.assertIn("lo byte = GBA keys 0–7; hi bit0→L(key 9), bit1→R(key 8)", regs)

    def test_the_findings_use_the_keypad_namespace_and_mint_no_hardware_id(self):
        ev = read(EVIDENCE)
        for n in (2, 3, 4, 5):
            self.assertEqual(len(re.findall(r"^## GBP-KEY-%03d\b" % n, ev, re.M)), 1, n)
        # GBP-KEY-006 (Issue #19), GBP-KEY-007 (Issue #22), GBP-KEY-008 / 009 (Issue #24), GBP-KEY-010 (Issue #27) followed;
        # nothing beyond them
        self.assertEqual(re.findall(r"^## GBP-KEY-00[8-9]", ev, re.M), ["## GBP-KEY-008", "## GBP-KEY-009"])
        self.assertEqual(re.findall(r"^## GBP-KEY-01\d", ev, re.M), ["## GBP-KEY-010"])
        hw = max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M))
        self.assertEqual(hw, 294)   # GBP-HW-261…265: RUN 14 / RUN 15 (Issue #24); 266…271: RUN 16 / 17 / 18 (Issue #33)   # 272: Issue #46 (the CONTROL bit 0x02 split, FACT for the split / HYPOTHESIS for the cause); 273…277: Issue #47 (RUN 23 / RUN 24, §V7.7); 278…284: Issue #52 (RUN 21 / 22 / 25 / 26, §V7.8)   # 285…294: Issue #62 (RUN 30 ingested, §V8.13)
        self.assertNotRegex(read(DOC), r"GBP-HW-26[1-9]|GBP-HW-2[7-9]\d|GBP-HW-[3-9]\d\d")   # INPUT_PATH.md is the pre-run document
        # Issue #46 (2026-09-22) minted GBP-HW-272 and HANDOFF's trail names it; the sentinel moves to the next
        # free id so it keeps catching a record that cites evidence nobody has written yet
        for p in (ROADMAP, HANDOFF):
        # Issue #52 (2026-09-22) ingested RUN 21 / 22 / 25 / 26 and minted GBP-HW-278…284; the HANDOFF's
        # trail names them, which is what a trail is for. The sentinel moves to the next free id.
            # Issue #62 minted GBP-HW-285…294 when RUN 30 was ingested; the sentinel moves past them
            self.assertNotRegex(read(p), r"GBP-HW-29[5-9]|GBP-HW-[3-9]\d\d")
        self.assertIn("— FACT (static)", ev.split("## GBP-KEY-002")[1].split("\n")[0])
        self.assertIn("CORROBORATED for the encoding the references target; the physical routing NOT established",
                      ev.split("## GBP-KEY-004")[1].split("\n")[0])

    def test_every_id_the_document_cites_is_defined(self):
        defined = defined_ids()
        missing = sorted(i for i in set(ID.findall(read(DOC))) if i not in defined)
        self.assertEqual(missing, [])


class ProvenanceAndStateRecords(unittest.TestCase):
    def test_external_register_lists_enhanced_mgba_with_its_commit(self):
        t = read(EXTERNAL)
        self.assertIn("| `mgba/` (Enhanced mGBA) | https://github.com/extremscorner/mgba | 20251124", t)
        self.assertIn(MGBA_COMMIT, t)
        self.assertIn("never the physical KEYPAD format", t)
        self.assertIn(MGBA_COMMIT, read(DOC))

    def test_the_reference_identities_are_the_recorded_ones(self):
        t = read(DOC)
        self.assertIn("3dd3692f5931516b80915b38e795aa6092e4d4db43cd652bc396e0cba2b11b5d", t)
        self.assertIn("0b2c44ea75f85aa8d64ac3ad167c400f778becc58e886c53a44b9a67f46384b0", t)
        self.assertIn("c185d27ede09771fe93a3b520c576f646f937ed9", t)
        self.assertIn("64b5087aa45cd0187b8b239d77e54ee5eb2917d1", t)
        self.assertIn("proprietary, never a donor", flat(t))

    def test_roadmap_and_handoff_carry_the_phase_5_entry(self):
        r = flat(read(ROADMAP))
        # the status line grew with Issue #19 and again with Issue #24 (RUN 14 / RUN 15 executed and ingested)
        self.assertIn("Status: ENTERED 2026-09-21 (GitHub Issue #18, research / design), IMPLEMENTED AS SOFTWARE 2026-09-21 (GitHub Issue #19, candidate `stream-0014`) and PHYSICALLY EXECUTED 2026-09-21 — RUN 14 and RUN 15, GBP-INPUT-001 (Hardware Issue #21; ingested `HARDWARE_TESTS.md` §V7.2, GitHub Issue #24): Question M = PASS · Question O = AS-ASSIGNED in both runs", r)
        self.assertIn("A real game can be controlled reliably using the GameCube controller.", read(ROADMAP))
        h = flat(read(HANDOFF))
        self.assertIn("**Phase 5 — Input, implemented and physically executed (GBP-INPUT-001, GBP-INPUT-002: the routing FACT)**", h)   # Issue #24's row, Issue #33's title
        self.assertIn("The physical keypad record held these two runs and nothing else until Issue #33 added RUN 17 / RUN 18 / RUN 16", h)
        self.assertIn("That the KEYPAD L/R routing is a physical FACT beyond the runs' scope", h)   # Issue #33: FACT (hw, the runs), scoped

    def test_the_keypad_code_is_the_module_the_design_named(self):
        """Issue #18 shipped no code; Issue #19 (2026-09-21) implemented §7 as
        src/gbp/gbp_input.c under the three names the design used."""
        h = read(os.path.join(ROOT, "src", "gbp", "gbp_input.h"))
        for name in ("gbp_input_map", "gbp_keypad_encode", "gbp_keypad_write"):
            self.assertIn(name, h)
        self.assertIn("## 7. Input architecture on paper (Deliverable E)", read(DOC))


if __name__ == "__main__":
    unittest.main()
