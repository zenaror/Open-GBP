"""tests/host/test_gbmode_e4_prereg.py -- GitHub Issue #151: HARDWARE_TESTS.md V30 (E4, the L / R stretch) says what the reader does, what the repository holds, and nothing it must not.

The rival-reading table in the document is generated from the reader's own state machines and pinned to them; every reader token and every model is in the text; nothing is staged (slot 27 is
the RUN 59 pin, no slot 28 exists, the DOL hash is unchanged); the code facts the check rests on are read from the sources; the Operator's text is in Portuguese, in the button x count typography,
and carries no word for a change of the picture.
"""
import hashlib
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gbmode_e4_read as e  # noqa: E402

DOC = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
TSV = os.path.join(ROOT, "tools", "swiss-layout.tsv")
PIN = "e33115e348fbf7c51dfadba61d52ea4c8b07e64874c69550a832ed07e494a497"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def section():
    t = read(DOC)
    i = t.index("## V30 — PHASE 7's E4")
    return t[i:]


def plain(s):
    return " ".join(s.replace("`", "").replace("**", "").split())


class TheTextIsTheReadersAndTheRepositorys(unittest.TestCase):
    def test_the_rival_table_is_what_the_state_machines_predict(self):
        tr = [(100, 1, 0), (200, 0, 0), (400, 0, 1), (500, 0, 0), (700, 1, 0), (800, 0, 0)]
        reps = (150, 300, 450, 750)
        doc = section()
        i = doc.index("reading            L|after:")
        block = doc[i:doc.index("```", i)]
        rows = {}
        for line in block.splitlines()[1:]:
            m = re.match(r"^(\w+)\s+([SN])\s+([SN])\s+([SN])\s+([SN])\s", line)
            if m:
                rows[m.group(1)] = [m.group(k) == "S" for k in range(2, 6)]
        self.assertEqual(sorted(rows), sorted(e.MODELS), "the table has a row per model of the reader, no more and no fewer")
        for m in e.MODELS:
            self.assertEqual(rows[m], [e.model_state(m, tr, t) for t in reps], m)

    def test_every_token_and_every_model_is_in_the_text_and_the_other_way_round(self):
        d = section()
        for tok in ("INADMISSIBLE", "NO_LR_WORD_SENT", "CHANGED", "NOT_CHANGED_REACH_NOT_SHOWN", "PARTIAL", "INCONCLUSIVE_NOT_LEGIBLE"):
            self.assertIn(tok, d, tok)
            self.assertIn(tok, read(os.path.join(ROOT, "tools", "gbmode_e4_read.py")), tok)
        for m in e.MODELS:
            self.assertIn(m, d, m)
        src = read(os.path.join(ROOT, "tools", "gbmode_e4_read.py"))
        for tok in re.findall(r'return "([A-Z_]+)"', src):
            self.assertIn(tok, d, "the reader can return %s and the pre-registration does not name it" % tok)

    def test_the_thresholds_in_the_text_are_the_readers(self):
        d = plain(section())
        self.assertEqual((e.MARGIN_FRAMES, e.MIN_FRAMES, e.LEGIBLE_MIN, e.LEAK_STRETCHED, e.LEAK_WORDS, e.INBOX_WORDS), (30, 40, 0.90, 0.25, 1620, 540))
        for tok in ("30 frames (0.5 s)", "at least 40 legible frames", "at least 90 %", "25 % or more of the 1 620 outside words", "at most 2 %", "540 words", "1 620 words", "1 % to 25 %"):
            self.assertIn(tok, d, tok)

    def test_nothing_is_staged_and_the_image_is_the_run_59_one(self):
        rows = [l.split("\t") for l in read(TSV).splitlines() if re.match(r"^\d+\t", l)]
        nums = [int(r[0]) for r in rows]
        self.assertIn(27, nums)
        self.assertNotIn(28, nums, "a slot 28 exists: something was staged for E4, and this checkpoint stages nothing")
        row27 = [r for r in rows if r[0] == "27"][0]
        self.assertEqual(row27[-1].strip(), PIN)
        d = plain(section())
        self.assertIn("NOT AUTHORISED HERE", d)
        self.assertIn("NOTHING IS STAGED", d)
        self.assertIn("UNCHANGED", d)
        self.assertIn(PIN, d)

    def test_the_code_facts_the_check_rests_on(self):
        main = read(os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c"))
        self.assertIn("GBP_VFULL_K == 8u && GBP_VFULL_SPACING == 256u", main)
        self.assertIn("a join to the frame records needs no conversion", re.sub(r"\s*\n\s*\*\s*", " ", main))
        self.assertIn("#define KEYLOG_TAIL_RESERVE 64u", main)
        self.assertIn("PAD_ButtonsDown(0) & PAD_BUTTON_X", main)
        uses = [l for l in main.splitlines() if re.search(r"PAD_BUTTON_(?:L|R)\b", l)]
        self.assertTrue(uses and all("GBP_PAD_BUTTON_" in l and "==" in l for l in uses), "only the static asserts name the L and R buttons: nothing in the POC reacts to them: %r" % uses)
        self.assertIn("KEY n=%lu act=%s keys=%04x word=%04x t_poll=%llx t_attempt=%llx t_done=%llx xfer=%lu rc=%s", read(os.path.join(ROOT, "src", "gbp", "gbp_input.h")))
        desc = read(os.path.join(ROOT, "src", "gbp", "gbp_input.c"))
        self.assertIn("{ 0, 1, 2, 3, 4, 5, 6, 7, /* R -> bit */ 9, /* L -> bit */ 8 }", desc)
        self.assertEqual((e.L_BIT, e.R_BIT), (0x100, 0x200))

    def test_the_operators_text_is_portuguese_typographic_and_predicts_nothing(self):
        d = section()
        i = d.index("### V30.9")
        txt = d[i:d.index("### V30.10")]
        block = txt[txt.index("```text"):txt.index("```", txt.index("```text") + 7)]
        for tok in ("L (gatilho esquerdo, até o clique)  ×1", "R (gatilho direito, até o clique)  ×1", "NÃO aperte NADA", "ciclo de energia", "27-gbmode", "4d6fe06", "O QUE VOCÊ VIU",
                    "eu registro literalmente ANTES de te mostrar qualquer número do log", "nunca apague"):
            self.assertIn(tok, block, tok)
        self.assertEqual(block.count("L (gatilho esquerdo, até o clique)  ×1"), 2)
        self.assertNotRegex(block, r"[LR]\d", "digits glued to a button name")
        for banned in (r"estic", r"encher", r"preench", r"zoom", r"amplia", r"aument", r"cresc", r"expand", r"stretch", r"cheia", r"tela inteira", r"esperado", r"deve mudar", r"vai mudar"):
            self.assertIsNone(re.search(banned, block, re.I), "the Operator's text carries a word for a change of the picture: %r" % banned)
        self.assertIn("The text says nothing about what the picture may do", plain(txt))

    def test_the_reach_ambiguity_and_the_fallback_are_registered(self):
        d = plain(section())
        for tok in ("IT DOES NOT, and this is registered, not hidden", "no reading of this image can say that the AGB's register held the word in GB mode",
                    "narrowed", "HYPOTHESIS", "not the expectation", "ONE named variable", "NOT designed, built or authorised", "the SAME names as RUN 59's",
                    "The timeline is one observation", "one boot of one title, one console, one Game Boy Player"):
            self.assertIn(tok, d, tok)


class TheArchiveMatchesTheNumbersTheTextQuotes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = os.path.join(ROOT, "captures", "local", "GBP-VIDEO-004_gbmode-0001-run59-idxcap.bin")
        if not os.path.isfile(cls.p):
            raise unittest.SkipTest("no local archive on this host (captures/local is ignored)")
        with open(cls.p, "rb") as f:
            assert hashlib.sha256(f.read()).hexdigest() == "5687d3b34bf0763cb05c2625105f982231459779587e1f821e34c1466b471f3c", "the archive is not the recorded one"

    def test_the_windows_and_the_seconds_the_text_quotes(self):
        import vidxcap
        info = vidxcap.load(self.p)
        log = read(os.path.join(ROOT, "captures", "local", "GBP-VIDEO-004_gbmode-0001-run59.log"))
        tc = int(re.search(r"EPOCH t64_pre=[0-9a-f]+ t64_post=([0-9a-f]+)", log).group(1), 16)
        hz = info["tb_hz"]
        wins, cur = [], None
        for r in info["records"]:
            inbox, leak = e.frame_stats(r["witness"])
            self.assertEqual(leak, 0, "a strip word outside the baseline rectangle in frame %d" % r["frame_index"])
            ok = inbox / float(e.INBOX_WORDS) >= e.LEGIBLE_MIN
            if ok and cur is None:
                cur = [r["frame_index"], r["frame_index"], r["t_first_block"], r["t_first_block"]]
            elif ok:
                cur[1], cur[3] = r["frame_index"], r["t_first_block"]
            elif cur:
                wins.append(cur)
                cur = None
        if cur:
            wins.append(cur)
        self.assertEqual([(w[0], w[1]) for w in wins], [(355, 373), (1192, 1321), (1622, 1918), (2245, 2375)])
        secs = [((w[2] - tc) / float(hz), (w[3] - tc) / float(hz)) for w in wins]
        self.assertEqual([(round(a, 2), round(b, 2)) for a, b in secs], [(5.94, 6.24), (19.96, 22.12), (27.16, 32.11), (37.59, 39.76)])
        d = plain(section())
        for tok in ("355 .. 373", "1192 .. 1321", "1622 .. 1918", "2245 .. 2375", "5.94 .. 6.24", "19.96 .. 22.12", "27.16 .. 32.11", "37.59 .. 39.76", "in all 2 048 frames not one strip word outside"):
            self.assertIn(tok, d, tok)


if __name__ == "__main__":
    unittest.main()
