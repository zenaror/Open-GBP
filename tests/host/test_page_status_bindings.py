"""
tests/host/test_page_status_bindings.py — GitHub Issue #96: where a consolidated page binds a
status to ONE evidence id, the status must be one the record gives that id; and the indexes
state no status at all.

THE DEFECT CLASS. Two consolidated documents gave the reader different answers to one question:
`docs/protocol/README.md` read the L/R order as CORROBORATED while `INPUT.md` read it as a
physical FACT, which is what `GBP-HW-270` records. The same sweep found `ARCHITECTURE.md` binding
F to `GBP-PHY-001`, whose status is CORROBORATED. The consolidated set exists so that a reader
does not have to go back to `EVIDENCE.md` to decide which page to believe.

WHY THIS IS NOT THE GATE ISSUE #29 REFUSED. #29 measured that comparing a table ROW's status
cell with an entry's status is a category error: a row carries a compound, aspect-scoped status
("C (format and polarity …); F (hw, run-scoped)") and cites several ids. This guard compares
nothing of that kind. It reads only the two forms in which a page binds ONE status letter to ONE
id, where the comparison means what it says.

A. A STATUS BOUND TO ONE ID. Only two forms are bindings:
   T  a table whose header has cells named exactly "Status" and "Evidence", in a row whose
      Status cell is one letter (F, C, H or U, bold or not) and whose Evidence cell cites
      exactly one id;
   P  anywhere: a status letter followed by " (" and a parenthesis that cites exactly one id,
      as in "**F** (GBP-IRQ-002)" or "**U** (U-GBP-022)".
   For an EVIDENCE id, the letter must be a status the entry NAMES: in its heading (appended
   pointers included, `RESEARCH_METHOD.md` "A heading that outlived its status"), in a
   "**Status:**" statement, or in a bold segment of its body that begins with a status word
   ("**FACT (hardware):**"). For an UNKNOWNS id the letter must be H or U, and the entry must
   not be CLOSED unless its heading also says REOPENED.

B. THE INDEXES STATE NO STATUS. `docs/protocol/README.md` and `docs/hardware/README.md` contain
   no status word and no bold status letter. The README line that motivated #96 cited no id, so
   guard A could never have seen it; B removes the place it lived instead.

WHAT A GREEN RUN DOES NOT MEAN. It does not mean the consolidated set agrees with the record.
  * Coverage. Measured 2026-09-24, after #96's corrections: 42 bindings (form T 12, form P 30),
    against 287 page lines that cite a defined id.
    A status next to several ids, a compound status cell ("C (usage), H (name)"), a status in
    words, prose that implies a status without naming one, and every claim that cites no id
    all escape A.
  * Membership, not equality. An entry that names several statuses (compound, or amended on
    top) accepts any of them, so a page quoting the superseded status of an amended entry passes.
  * Aspect. It cannot tell whether the bound status is about the same aspect of the claim.
  * A plain-letter status in an index escapes B.
  * It judges pages against the record, never the record itself.
The reconciliation sweep (`tools/reconcile.py`, `RESEARCH_METHOD.md`) remains the instruction for
everything above. THERE IS NO EXCEPTION LIST HERE, AND THERE MUST NOT BE ONE: a binding that
disagrees is corrected by the record or escalated, and a form that binds falsely is narrowed as a
form, never excused line by line (#83's own finding: an exception list is where the next defect
hides).
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
PAGE_DIRS = ("docs/protocol", "docs/hardware")
INDEXES = ("docs/protocol/README.md", "docs/hardware/README.md")
ID = re.compile(r"\b((?:GBP|ENV)-[A-Z]+-\d{3}|U-(?:GBP|ENV)-\d{3})\b")
WORD = {"FACT": "F", "CORROBORATED": "C", "HYPOTHESIS": "H", "UNKNOWN": "U"}
STATUS_WORD = r"(FACT|CORROBORATED|HYPOTHESIS|UNKNOWN)"
HEAD = re.compile(r"^#{1,4} .*$", re.M)
ENTRY = re.compile(r"^#{2,4} +((?:GBP|ENV)-[A-Z]+-\d{3}|U-(?:GBP|ENV)-\d{3})\b(.*)$")
# form P: the letter may follow "**" ("**H (U-GBP-004):**"), never a word, "/", "." or "-"
PROSE = re.compile(r"(?:\*\*([FCHU])\*\*|(?<![\w/.\-])([FCHU])) \(([^()]*)\)")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def entries():
    """id -> (heading remainder, body), the body ending at the next heading of any level."""
    out = {}
    for p in (EVIDENCE, UNKNOWNS):
        text = read(p)
        heads = list(HEAD.finditer(text))
        for k, h in enumerate(heads):
            m = ENTRY.match(h.group(0))
            if m:
                end = heads[k + 1].start() if k + 1 < len(heads) else len(text)
                out[m.group(1)] = (m.group(2), text[h.end():end])
    return out


def named(heading, body):
    """The status letters an EVIDENCE entry names; see the module docstring, guard A."""
    s = {WORD[w] for w in re.findall(r"\b" + STATUS_WORD + r"\b", heading)}
    for st in re.findall(r"\*\*Status:?\*\*:?(.+?)(?:\n\n|\Z)", body, re.S):
        s |= {WORD[w] for w in re.findall(r"\b" + STATUS_WORD + r"\b", st)}
    s |= {WORD[w] for w in re.findall(r"\*\*" + STATUS_WORD + r"\b[^*]*\*\*", body)}
    return s


def bindings(text):
    """(line number, form, id, letter) for every binding of form T or P in one page's text."""
    out = []
    header = None
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if "Status" in cells and "Evidence" in cells:
                header = (cells.index("Status"), cells.index("Evidence"), len(cells))
            elif header and len(cells) == header[2] and not set(line) <= set("|-: "):
                letter = re.fullmatch(r"(\*\*)?([FCHU])(\*\*)?", cells[header[0]])
                ids = set(ID.findall(cells[header[1]]))
                if letter and len(ids) == 1:
                    out.append((n, "T", ids.pop(), letter.group(2)))
        elif not line.strip():
            header = None
        for m in PROSE.finditer(line):
            ids = set(ID.findall(m.group(3)))
            if len(ids) == 1:
                out.append((n, "P", ids.pop(), m.group(1) or m.group(2)))
    return out


def violations(text, ents):
    """Every binding in `text` whose letter the record does not give its id (test ids are skipped)."""
    bad = []
    for n, form, i, letter in bindings(text):
        if i not in ents:
            continue   # a test id (GBP-INIT-002 …), not evidence; test_page_citations checks it exists
        heading, body = ents[i]
        if i.startswith("U-"):
            closed = re.search(r"\bCLOSED\b", heading) and not re.search(r"\bREOPENED\b", heading)
            if letter not in "HU":
                bad.append((n, form, i, letter, "an open question is never bound to F or C"))
            elif closed:
                bad.append((n, form, i, letter, "the unknown is CLOSED"))
        elif letter not in named(heading, body):
            bad.append((n, form, i, letter, "the record names %s" % ("".join(sorted(named(heading, body))) or "no status")))
    return bad


def index_statuses(text):
    return re.findall(r"\b" + STATUS_WORD + r"\b|\*\*[FCHU]\*\*", text)


def pages():
    for d in PAGE_DIRS:
        for fn in sorted(os.listdir(os.path.join(ROOT, d))):
            if fn.endswith(".md"):
                yield d + "/" + fn, read(os.path.join(ROOT, d, fn))


class ABoundStatusIsOneTheRecordGives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ents = entries()

    def test_every_binding_on_every_consolidated_page(self):
        bad = ["%s:%d form %s binds %s to %s: %s" % ((rel,) + v[:2] + (v[3], v[2], v[4]))
               for rel, t in pages() for v in violations(t, self.ents)]
        self.assertEqual(bad, [], "\n".join(bad))

    def test_it_sees_enough_to_be_worth_running(self):
        """A parser that silently stopped matching would pass everything; these floors are
        below the 2026-09-24 counts (form T 12, form P 30) so a real page edit does not trip them,
        and far above zero so a broken form does."""
        found = [b for _rel, t in pages() for b in bindings(t)]
        self.assertGreaterEqual(sum(1 for b in found if b[1] == "T"), 8, found)
        self.assertGreaterEqual(sum(1 for b in found if b[1] == "P"), 20, found)


class BTheIndexesStateNoStatus(unittest.TestCase):
    def test_neither_index_names_a_status(self):
        for rel in INDEXES:
            self.assertEqual(index_statuses(read(os.path.join(ROOT, rel))), [], rel)


class WhatItCatchesAndWhatItDoesNot(unittest.TestCase):
    """The guard run on text built here, so each claim in the docstring is exercised."""

    @classmethod
    def setUpClass(cls):
        cls.ents = entries()

    def bad(self, text):
        return [(v[2], v[3]) for v in violations(text, self.ents)]

    def test_a_status_the_record_does_not_give_is_caught_in_both_forms(self):
        # GBP-HW-301 is CORROBORATED; the Orchestrator's own drift in #95 was calling the rate FACT
        self.assertEqual(self.bad("the rate is **F** (GBP-HW-301)."), [("GBP-HW-301", "F")])
        self.assertEqual(self.bad("the rate is **C** (GBP-HW-301)."), [])
        # the row #96's sweep found, as it read before the fix
        table = "| Claim | Status | Evidence |\n|---|---|---|\n| Three known board revisions | F | GBP-PHY-001 (gbhwdb) |\n"
        self.assertEqual(self.bad(table), [("GBP-PHY-001", "F")])
        self.assertEqual(self.bad(table.replace("| F |", "| C |")), [])

    def test_an_open_question_is_never_bound_to_a_fact_and_a_closed_one_is_not_pointed_at(self):
        self.assertEqual(self.bad("the layout is **F** (U-GBP-012)."), [("U-GBP-012", "F")])
        self.assertEqual(self.bad("the layout is **U** (U-GBP-012)."), [])
        # U-GBP-010 was CLOSED on 2026-09-21 (the L/R order); pointing at it as open is stale
        self.assertEqual(self.bad("the L/R order is **U** (U-GBP-010)."), [("U-GBP-010", "U")])

    def test_what_escapes_escapes(self):
        """Stated limits, pinned so nobody reads more into a green run than there is."""
        self.assertEqual(bindings("the rate is **F** (GBP-HW-301, GBP-HW-319)."), [])   # two ids
        self.assertEqual(bindings("the rate is a FACT (GBP-HW-301)."), [])               # a word
        self.assertEqual(bindings("the L/R order CORROBORATED, not FACT"), [])           # no id: README's line
        self.assertEqual(bindings("| C (usage), H (name) | GBP-CTL-001 |"), [])          # no header row
        # membership: GBP-HW-305 was CORROBORATED before Issue #85 made it FACT; both pass
        self.assertEqual(self.bad("**C** (GBP-HW-305)"), [])
        self.assertEqual(self.bad("**F** (GBP-HW-305)"), [])

    def test_guard_b_catches_the_line_that_motivated_it(self):
        self.assertTrue(index_statuses("the bit assignment with its status (the L/R order CORROBORATED, not FACT)"))
        self.assertTrue(index_statuses("its rate, **C**"))
        self.assertEqual(index_statuses("every row carries its evidence id and a status of F or C"), [])

    def test_the_limits_stay_written(self):
        doc = __doc__
        for tok in ("WHAT A GREEN RUN DOES NOT MEAN", "Membership, not equality", "every claim that cites no id",
                    "THERE IS NO EXCEPTION LIST HERE", "It judges pages against the record, never the record itself"):
            self.assertIn(tok, doc, tok)


if __name__ == "__main__":
    unittest.main()
