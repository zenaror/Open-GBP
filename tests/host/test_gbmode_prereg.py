"""
tests/host/test_gbmode_prereg.py -- GitHub Issue #146 (Phase 7's E3): HARDWARE_TESTS.md section V29, the pre-registration of RUN 59,
pinned: what it says is what the reader, the archive and the fence say.

  * the reader's tokens and constants are the ones the document freezes (a pre-registration whose rules differ from the tool that applies
    them is a reading chosen after the data);
  * the write inventory's "never made with GB media" column is RECOMPUTED from the four GB logs (RUN 24, 27, 28, 29) and the GBA column
    from RUN 17: an inventory that cannot be re-derived is a wish;
  * the Operator's questions are frozen, in Portuguese, and the document says they are recorded verbatim before any figure;
  * nothing is staged, no run outcome of RUN 58 is described, and the blinding vocabulary of Issue #128 is absent.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gbmode_read as g  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
LOCAL = os.path.join(ROOT, "captures", "local")


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def section():
    t = read(HW)
    i = t.index("## V29 — PHASE 7's E3")
    return t[i:]


def plain(s):
    return re.sub(r"\s+", " ", s.replace("`", "").replace("**", ""))


class TheRulesInTheDocumentAreTheToolsRules(unittest.TestCase):
    def test_every_token_the_reader_can_emit_is_in_the_document_and_the_other_way_round(self):
        doc = section()
        src = read(os.path.join(ROOT, "tools", "gbmode_read.py"))
        emitted = set(re.findall(r'"((?:SERVICE_RAN_TO_TARGET|SERVICE_RAN_ENDED_BY|REFUSED_AT_PREUNMASK_[A-Z_]+|ABORT_AT_LATER_GUARD|NO_DELIVERY|'
                                 r'OTHER_ENDING|GBA_STRUCTURE|DIFFERENT_STRUCTURE|NO_VIDEO|NOT_EVALUABLE|AUDIO_COUNT_AS_GBA|AUDIO_COUNT_DIFFERENT|'
                                 r'NO_AUDIO|AUDIO_WITHOUT_VIDEO|RESTORE_HOLDS_BIT|RESTORE_CLEARS_BIT|RESTORE_OTHER|NOT_REACHED|UNDETERMINED|UNKNOWN|SERVICE_RAN_TO_TARGET_WITH_ERRORS)[^ "%]*)', src))
        tokens = {re.match(r"[A-Z_]+", t).group(0) for t in emitted}
        self.assertGreaterEqual(len(tokens), 16)
        for t in tokens:
            base = "SERVICE_RAN_ENDED_BY" if t.startswith("SERVICE_RAN_ENDED_BY") else t
            self.assertIn(base, doc, "the reader can emit %s and the pre-registration does not name it" % t)

    def test_every_token_the_document_freezes_can_be_emitted_by_the_reader(self):
        """The other direction: a rival reading that is written and cannot be produced is a reading nobody can make."""
        doc = section()
        i = doc.index("### V29.7")
        block = doc[i:doc.index("**The baselines behind the numbers")]
        src = read(os.path.join(ROOT, "tools", "gbmode_read.py"))
        names = set()
        for line in block.split("\n"):
            m = re.match(r"(?:Q\d  |    )([A-Z][A-Z_/ <>a-z]{5,}?)(?:\s{3,}|$)", line)
            if not m:
                continue
            for part in m.group(1).split(" / "):
                tok = re.match(r"[A-Z][A-Z_]{5,}", part.strip())
                if tok:
                    names.add(tok.group(0))
        self.assertGreaterEqual(len(names), 16, names)
        for n in sorted(names):
            self.assertIn(n, src, "the pre-registration names the reading %s and the reader cannot emit it" % n)

    def test_the_constants_quoted_are_the_constants_applied(self):
        d = plain(section())
        self.assertEqual(g.BLOCKS_PER_FRAME, (39.9, 40.1))
        self.assertEqual(g.MAX_INCOMPLETE, 20)
        self.assertEqual(g.MIN_CLOSED, 300)
        self.assertEqual(g.AUDIO_PER_VIDEO, (1.60, 1.80))
        self.assertEqual(g.TOLERATED, 0x01)
        self.assertEqual(g.IDENT_BUILD, "gbmode-0001")
        for w in ("within 39.9-40.1", "incomplete<=20", "quarantined=0", "closed>=300", "within 1.60-1.80"):
            self.assertIn(w, d)

    def test_the_operators_questions_are_frozen_in_portuguese(self):
        d = section()
        for w in ("NÃO aperte NENHUM botão do controle durante a execução", "O que apareceu na TV durante a execução?",
                  "Você reconheceu a imagem como sendo do Pokémon Crystal?", "Como a imagem ocupava a tela da TV?", "ciclo de energia ANTES e DEPOIS -- sim / não",
                  "é o MESMO exemplar que você usou nos testes de 22/09", "DESLIGUE o console POR COMPLETO"):
            self.assertIn(w, d)
        p = plain(d)
        self.assertIn("recorded verbatim before any figure is computed or shown to him", p)
        self.assertIn("no threshold in V29.7 uses them", p)


class TheWriteInventoryIsRecomputed(unittest.TestCase):
    def logs(self, names):
        paths = [os.path.join(LOCAL, "GBP-VIDEO-004_stream-0015-%s.log" % n) for n in names]
        if not all(os.path.exists(p) for p in paths):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        return paths

    def test_no_service_write_was_ever_made_with_gb_media(self):
        for p in self.logs(["run24", "run27", "run28", "run29"]):
            t = read(p)
            self.assertIn(" COUNTERS unmasks=0 deliveries=0 acks=0 rearms=0 ", t, p)
            self.assertRegex(t, r"INPUT selftest=1 steps=0 .* attempts=0 completed=0 failed=0 first=0 change=0 refresh=0", p)
            self.assertNotIn("IRQW tag=ACK", t, p)
            self.assertNotIn("IRQW tag=REARM", t, p)
            # what WAS written with GB media: TEST x4, CONTROL exp, IRQ A1, A2, CONTROL restore, IRQ STOP, AR_INFO exp and restore
            self.assertEqual(len(re.findall(r" TESTW tag=DET ", t)), 4, p)
            for tag in ("CTLW tag=EXP", "IRQW tag=A1", "IRQW tag=A2", "CTLW tag=RESTORE", "IRQW tag=STOP", "ARINFO exp", "ARINFO restore"):
                self.assertIn(" " + tag, t, "%s: %s not written" % (p, tag))
            self.assertIn("teardown_w1c=1", t, p)

    def test_the_gba_columns_are_run_17s(self):
        (p,) = self.logs(["run17"])
        t = read(p)
        self.assertIn(" COUNTERS unmasks=254723 deliveries=254723 acks=254723 rearms=254723 ", t)
        self.assertIn("attempts=7898 completed=7898 failed=0 first=1 change=42 refresh=7855 retry=0", t)
        d = plain(section())
        for w in ("254 723", "7 898 (first 1, change 42, refresh 7 855)"):
            self.assertIn(w, d)

    def test_no_pak_baseline_is_run_23s(self):
        (p,) = self.logs(["run23"])
        self.assertIn(" COUNTERS unmasks=254746 deliveries=254746 ", read(p))
        self.assertIn("254 746", plain(section()))


class TheCandidateOfRecord(unittest.TestCase):
    """V29.10: the record names the commit the image was built at, and that commit is what the record says it is."""

    def test_the_marker_names_an_ancestor_that_carries_the_variant_target_and_the_frozen_poc(self):
        import subprocess
        d = read(HW)
        m = re.search(r"^CANDIDATE_COMMIT=([0-9a-f]{7,40})\s*$", d, re.M)
        self.assertIsNotNone(m, "V29.10 records no candidate commit")
        c = m.group(1)
        if subprocess.run(["git", "-C", ROOT, "cat-file", "-e", c + "^{commit}"], capture_output=True).returncode != 0:
            self.skipTest("the base commit is not in this checkout")
        self.assertEqual(subprocess.run(["git", "-C", ROOT, "merge-base", "--is-ancestor", c, "HEAD"]).returncode, 0)
        mk = subprocess.run(["git", "-C", ROOT, "show", c + ":Makefile"], capture_output=True, text=True).stdout
        self.assertIn("gbmode-session:", mk)
        self.assertIn("GBMODE_BUILD_ID ?= gbmode-0001", mk)
        a = subprocess.run(["git", "-C", ROOT, "show", c + ":poc/gbp-video-stream-probe/source/main.c"], capture_output=True, text=True).stdout
        b = subprocess.run(["git", "-C", ROOT, "show", "da06500:poc/gbp-video-stream-probe/source/main.c"], capture_output=True, text=True).stdout
        self.assertEqual(a, b)

    def test_the_record_names_the_hash_the_identity_and_what_was_not_run(self):
        d = plain(section())
        for w in ("e33115e348fbf7c51dfadba61d52ea4c8b07e64874c69550a832ed07e494a497", "516 544 B", "byte-identical", "Build : gbmode-0001 Commit: 4d6fe06",
                  "OPENGBP-IDENT gbp-video-stream-probe gbmode-0001 4d6fe06", "NOT RUN HERE", "NONE. tools/swiss-layout.tsv is untouched"):
            self.assertIn(w, d)


class TheFenceHolds(unittest.TestCase):
    FORBIDDEN = [r"\brungs?\b", r"\bladder\b", r"\bnulling\b", r"\bperceptual\b", r"\bAHEAD\b", r"\bT\d{3,4}\b", r"\bL\(", r"v28p", r"26-v28",
                 r"\bnull point\b", r"latency table"]

    def test_the_section_leaks_nothing_of_run_58(self):
        d = section()
        for pat in self.FORBIDDEN:
            self.assertIsNone(re.search(pat, d, re.I), "blinding vocabulary in section V29: " + pat)
        self.assertIn("RUN 58's ingestion goes first", d)

    def test_it_authorises_and_stages_nothing(self):
        d = plain(section())
        self.assertIn("NOT RUN, NOT AUTHORISED HERE", d)
        self.assertIn("RESERVED NAME ONLY", d)
        self.assertIn("No row in tools/swiss-layout.tsv, no pin, no export, no card write", d)
        self.assertIn("the card is untouched until RUN 58 has been run and archived", d)

    def test_the_one_variable_and_its_limits_are_stated(self):
        d = plain(section())
        for w in ("THE ONE NEW VARIABLE", "exactly four, and no more", "the SAME 3 443 device operations", "Nothing else is a variable",
                  "What the shared-source drift cannot exclude is stated, not hidden"):
            self.assertIn(w, d)


if __name__ == "__main__":
    unittest.main()
