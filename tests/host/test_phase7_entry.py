"""
tests/host/test_phase7_entry.py — GitHub Issue #143: Phase 7's entry assessed, design only.

WHAT THE DOCUMENT MAY NOT DO IS THE TEST. Issue #143's fence is hard: nothing of RUN 58's expected
outcome may appear anywhere the Operator reads (#128 blinding), and the document authorises nothing.
The blinding check is a vocabulary check and can only catch the words it knows; it is here because the
cheapest leak is a careless noun, not a deliberate figure.

EVERY ID THE DOCUMENT CITES MUST EXIST. An entry id that is not in EVIDENCE.md / UNKNOWNS.md is a citation
to nothing; ranges are checked at both ends.

THE TWO CODE CLAIMS THE DOCUMENT LEANS ON ARE READ FROM THE TREE: that the CONTROL guard compares the vote
to the value the runtime wrote, and that the V28 chassis header says what section 2 quotes from it.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOC = os.path.join(ROOT, "docs", "research", "PHASE7_ENTRY.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s.replace("`", "").replace("*", ""))


class TheDocumentAuthorisesNothing(unittest.TestCase):
    def test_status_and_the_eight_sections(self):
        d = plain(read(DOC))
        self.assertIn("DESIGN AND ASSESSMENT ONLY", d)
        self.assertIn("It authorises nothing", d)
        self.assertIn("Phase 7 is not entered", d)
        heads = re.findall(r"^## (\d+)\. ", read(DOC), re.M)
        self.assertEqual(heads, [str(i) for i in range(1, 9)])

    def test_the_matrix_starts_empty_and_the_audio_setting_is_not_named(self):
        d = plain(read(DOC))
        self.assertIn("No row is invented here", d)
        self.assertIn("no OUTCOME cell filled that a run has not earned", d)
        self.assertIn("DECIDED BY RUN 58's INGESTION", d)
        self.assertIn("names none", d)


class TheOperatorsWordsAreVerbatimAndNothingIsInferred(unittest.TestCase):
    """Issue #143's comments 5901197211 and 5901202292, quoted; the open points stay open."""

    def test_verbatim(self):
        d = plain(read(DOC))
        for w in ["de GBA tenho apenas o simpsons road rage (paralelo), ez-flash omega DE (que tem o Yoshi Island na NOR), "
                  "WarioWare twisted (JP e US), Kingdom Hearts Chain of Memories (JP original)",
                  "DrillDozer é um jogo que libera vibracao no controle",
                  "mas tenho pokemon crystal original JP, pokemon pinball, toda gen1, gold e silver (Jogo com suporte a "
                  "paletas no color, mas funciona no GB original tb)",
                  "meus jogos de pokemon sao todos japoneses...", "tb tenho o flashcart MBC3000 v4",
                  "Seria pelo flashcart... esqueci de falar que tenho o everdrive 5x mini tambem", "originais",
                  "liga direto... mas ele so suporta MBC3, MBC30 e MBC5... e atualmente esta setado para MBC30, "
                  "com a rom da REON do Crystal"]:
            self.assertIn(w, d)

    def test_the_open_points_are_left_open(self):
        d = plain(read(DOC))
        for w in ["THE TWO TEXTS ARE NOT RECONCILED HERE", "and the two are not assumed to be the same game",
                  "any design that would must ask him first", "Whether the REON Crystal ROM is the same game as his original Crystal is not stated",
                  "its family and its boot behaviour are not stated and are not assumed",
                  "WHICH POKEMON PINBALL, which Gen 1 titles"]:
            self.assertIn(w, d)


class BlindingHolds(unittest.TestCase):
    """#128 section 3-4: nothing that reads as RUN 58's rungs, settings, figures or expectation."""

    FORBIDDEN = [r"\brungs?\b", r"\bladder\b", r"\bnulling\b", r"\bperceptual\b", r"\bAHEAD\b", r"\bT\d{3,4}\b",
                 r"\bL\(", r"v28p", r"26-v28", r"\bnull point\b", r"latency table", r"\bfloor\b.*\bceiling\b"]

    def test_no_forbidden_word(self):
        d = read(DOC)
        for pat in self.FORBIDDEN:
            self.assertIsNone(re.search(pat, d, re.I), "blinding vocabulary in the document: " + pat)

    def test_no_audio_millisecond_figure(self):
        # the only millisecond figure allowed is the video hand-off of GBP-HW-224 (CONTROL to first hand-off)
        for m in re.finditer(r"\d[\d.,]*\s*ms\b", read(DOC)):
            self.assertEqual(m.group(0), "164.696 ms", m.group(0))


class EveryCitedIdExists(unittest.TestCase):
    def setUp(self):
        self.ev = read(EVIDENCE)
        self.unk = read(UNKNOWNS)
        self.doc = read(DOC)

    def _has(self, prefix, n):
        pat = r"^#{2,4} %s-%s\b" % (prefix, n)
        return bool(re.search(pat, self.ev, re.M)) or bool(re.search(pat, self.unk, re.M))

    def test_ids_and_range_endpoints(self):
        found = 0
        for m in re.finditer(r"(GBP-HW|U-GBP|GBP-KEY|GBP-SIO)-(\d+)((?:\.\.\d+)|(?:, -\d+)*)", self.doc):
            prefix, first, tail = m.group(1), m.group(2), m.group(3)
            ids = [first]
            if tail.startswith(".."):
                ids.append(tail[2:])
            else:
                ids += re.findall(r"-(\d+)", tail)
            for n in ids:
                found += 1
                self.assertTrue(self._has(prefix, n), "cited id not in EVIDENCE/UNKNOWNS: %s-%s" % (prefix, n))
        self.assertGreater(found, 20)


class TheCodeClaimsAreReadFromTheTree(unittest.TestCase):
    def test_the_guard_compares_to_what_the_runtime_wrote(self):
        c = read(os.path.join(ROOT, "src", "gbp", "gbp_avsvc_probe.c"))
        # Issue #145 (amended on top): the comparison is now the policy's -- still against the byte the runtime wrote,
        # up to bit 0x01. The section-3.2 claim (a guard against what the runtime wrote) is unchanged; its spelling moved.
        self.assertIn("!gbp_initirqa_snapshot_control_agrees(s, res->a.control_exp)", c)
        self.assertIn("control_changed_PREUNMASK", c)
        self.assertIn("S2_before_unmask", c)

    def test_the_amendment_of_issue_145_is_appended_and_names_the_rule(self):
        d = plain(read(DOC))
        self.assertIn("Amendment \u2014 2026-09-29 (Issue #145): E2", d)
        self.assertIn("the Orchestrator chose the narrow mask", d)
        self.assertIn("nothing branches on bit 0x01", d)
        self.assertGreater(read(DOC).index("(Issue #145)"), read(DOC).index("(Issue #144)"))

    def test_the_v28_chassis_header_says_what_section_2_quotes(self):
        m = plain(read(os.path.join(ROOT, "poc", "gbp-audio-v28", "source", "main.c")))
        self.assertIn("video, vstate, vqueue, vpresent, GX, input, session, keylog, SD save/teardown, startup profile "
                      "-- ALL carried over UNCHANGED", m)

    def test_the_audio_page_lists_gbc_audio_as_not_established(self):
        a = plain(read(os.path.join(ROOT, "docs", "protocol", "AUDIO.md")))
        self.assertIn("GB/GBC-mode audio (Phase 7)", a)


class TheStaticReadingIsRecorded(unittest.TestCase):
    """Issue #144: the three entries, the inputs' hashes, the status line and the amendment."""

    HASHES = ["3dd3692f5931516b80915b38e795aa6092e4d4db43cd652bc396e0cba2b11b5d",
              "947a5523e7be9b93a986d1e4daca9e335713827df48adcb1dfe79c6a00ed177d",
              "8083636c1b341e712859f40356bf5934f4622fab7e7a658bd7e8cb4feeb616b1",
              "0b2c44ea75f85aa8d64ac3ad167c400f778becc58e886c53a44b9a67f46384b0"]

    def test_entries_and_hashes(self):
        ev = read(EVIDENCE)
        for i in ("GBP-CTL-002", "GBP-CTL-003", "GBP-KEY-011"):
            self.assertRegex(ev, r"(?m)^### %s \u2014 " % i)
        for h in self.HASHES:
            self.assertIn(h, ev)

    def test_status_line_and_amendment(self):
        rm = plain(read(os.path.join(ROOT, "docs", "ROADMAP.md")))
        self.assertIn("Status: ENTERED 2026-09-29 (GitHub Issue #144), static reading.", rm)
        d = plain(read(DOC))
        self.assertIn("Amendment \u2014 2026-09-29 (Issue #144)", d)
        self.assertIn("NEITHER reference compares CONTROL with a value it wrote", d)

    def test_the_amendment_is_after_the_committed_text(self):
        d = read(DOC)
        self.assertGreater(d.index("## Amendment"), d.index("## 8. What this document does not do"))


if __name__ == "__main__":
    unittest.main()
