"""
tests/host/test_input_path.py — the Phase 5 entry checkpoint (GitHub Issue #18,
2026-09-21): the input path reconstructed on paper.

Pinned: INPUT_PATH.md keeps L1 / L2 / L3 as separate sections and labels the
mapping a POLICY; the U-GBP-010 outcome is stated once, in the same words in
INPUT_PATH.md, UNKNOWNS.md and the ROADMAP, and the unknown is NOT closed;
the physical record is declared empty; no order is adopted (the words
"adopted", "defaulted" appear only in their negation); every evidence id the
document cites exists; the keypad findings continue the GBP-KEY namespace
(002…005) and no GBP-HW id was minted (the highest stays 260); Dolphin's
order stays H in REGISTERS.md; the external register lists Enhanced mGBA with
its exact commit; the ROADMAP's Phase 5 status and the HANDOFF row exist;
and the keypad code that Issue #19 (2026-09-21) later added is the module §7 named.
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
ID = re.compile(r"\b(GBP-(?!VIDEO|BBA|INIT|AV|PROBE|BASELINE)[A-Z]+-\d{3}|ENV-[A-Z]+-\d{3}|U-GBP-\d{3}|U-ENV-\d{3})\b")


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
    def test_the_outcome_appears_in_the_three_records_and_the_unknown_is_open(self):
        self.assertEqual(read(DOC).count("U-GBP-010 static attempt (2026-09-21): " + OUTCOME), 1)
        self.assertIn("Outcome: RESOLVED\nSTATICALLY at CORROBORATED; NOT closed", read(UNKNOWNS))
        self.assertIn(OUTCOME, flat(read(ROADMAP)))
        self.assertIn(OUTCOME, flat(read(HANDOFF)))
        m = re.search(r"^## U-GBP-010\b.*$", read(UNKNOWNS), re.M)
        self.assertIsNotNone(m)
        self.assertNotIn("CLOSED", m.group(0))
        self.assertIn("OPEN", m.group(0))
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
        self.assertIn("C (existence/format), H (L/R bit order)", regs)
        self.assertIn("lo byte = GBA keys 0–7; hi bit0→L(key 9), bit1→R(key 8)", regs)

    def test_the_findings_use_the_keypad_namespace_and_mint_no_hardware_id(self):
        ev = read(EVIDENCE)
        for n in (2, 3, 4, 5):
            self.assertEqual(len(re.findall(r"^## GBP-KEY-%03d\b" % n, ev, re.M)), 1, n)
        self.assertNotRegex(ev, r"^## GBP-KEY-00[6-9]", re.M)
        hw = max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M))
        self.assertEqual(hw, 260)
        for p in (DOC, ROADMAP, HANDOFF):
            self.assertNotRegex(read(p), r"GBP-HW-26[1-9]|GBP-HW-2[7-9]\d|GBP-HW-[3-9]\d\d")
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
        self.assertIn("Status: ENTERED 2026-09-21 (GitHub Issue #18, research / design) and IMPLEMENTED AS SOFTWARE 2026-09-21 (GitHub Issue #19, candidate `stream-0014`, not executed); no KEYPAD write has been issued on hardware.", r)
        self.assertIn("A real game can be controlled reliably using the GameCube controller.", read(ROADMAP))
        h = flat(read(HANDOFF))
        self.assertIn("**Phase 5 — Input, implemented as software, unexecuted**", h)   # the row Issue #19 rewrote
        self.assertIn("the physical keypad record is empty.", h)
        self.assertIn("That the KEYPAD L/R order is established.", h)

    def test_the_keypad_code_is_the_module_the_design_named(self):
        """Issue #18 shipped no code; Issue #19 (2026-09-21) implemented §7 as
        src/gbp/gbp_input.c under the three names the design used."""
        h = read(os.path.join(ROOT, "src", "gbp", "gbp_input.h"))
        for name in ("gbp_input_map", "gbp_keypad_encode", "gbp_keypad_write"):
            self.assertIn(name, h)
        self.assertIn("## 7. Input architecture on paper (Deliverable E)", read(DOC))


if __name__ == "__main__":
    unittest.main()
