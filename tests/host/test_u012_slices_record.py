"""tests/host/test_u012_slices_record.py -- GitHub Issue #118: the record of the slice decode, against the tool and
against what the record said before it (e2084ba, the commit before #118).

  * GBP-HW-340's table is formatted from tools/u012slices.py's own output;
  * every amendment is append-only: U-GBP-012, U-GBP-041, the two run sections, AUDIO.md's rows, and no other
    EVIDENCE entry changed;
  * no status moved: GBP-HW-315's heading is byte-identical, and GBP-HW-340 claims arithmetic, not hardware;
  * the correction is where a reader meets it: "L2 PASS" is separated from fidelity at both closures and on the
    protocol page, and the ~2 kHz limit is attributed to the decoder, never to the path.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import guards  # noqa: E402
from test_u012_slices import Result  # noqa: E402

BASE = "e2084ba7359299e80842187504b0201a12f11653"
EV, UN, HT = "docs/research/EVIDENCE.md", "docs/research/UNKNOWNS.md", "docs/research/HARDWARE_TESTS.md"
AU, DL = "docs/protocol/AUDIO.md", "docs/research/DEVLOG.md"
L2_SENTENCE = ("`L2 PASS` means the chain reproduces on the host what it produced on the console. It never meant the "
               "chain captures what the cartridge played.")


def now(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def then(path):
    b = guards.show(BASE, path)
    return b.decode("utf-8") if isinstance(b, bytes) else b


def entry(text, eid):
    m = re.search(r"^#{2,3} %s \S.*$" % re.escape(eid), text, re.M)
    nxt = re.search(r"^#{2,3} (?:GBP|ENV)-[A-Z]+-\d{3} ", text[m.end():], re.M)
    body = text[m.end():m.end() + nxt.start() if nxt else len(text)]
    if nxt:
        body = body[:body.rfind("\n---\n")]
    return m.group(0), body


def section(text, head_re, stop=r"^#{1,3} "):
    m = re.search(head_re, text, re.M)
    n = re.search(stop, text[m.end():], re.M)
    return text[m.start():m.end() + n.start() if n else len(text)]


def flat(s):
    return " ".join(s.split())


def rows_append_only(tc, old, new):
    """Every table row of the base page is still there, keyed by its first cell, and each of its cells is a prefix
    of the row's cell now: text is appended inside a cell, never replaced."""
    now_rows = dict((l.split(" | ")[0], l.split(" | ")) for l in new.splitlines() if l.startswith("| "))
    for line in old.splitlines():
        if not line.startswith("| "):
            continue
        cells = line.split(" | ")
        tc.assertIn(cells[0], now_rows, line[:60])
        got = now_rows[cells[0]]
        tc.assertEqual(len(got), len(cells), line[:60])
        for a, b in zip(cells, got):
            tc.assertTrue(b.startswith(a.rstrip(" |")), (cells[0][:40], a[:50]))

class TheTableIsTheTools(unittest.TestCase):
    def test_every_row_of_GBP_HW_340(self):
        _h, b = entry(now(EV), "GBP-HW-340")
        for run, r in sorted(Result.get().items()):
            for w in r["windows"]:
                d = w["decodes"]
                row = re.search(r"^RUN %d w%d +(.*)$" % (run, w["index"]), b, re.M).group(1).split()
                f0 = "%d" % w["f0_hz"] if w["f0_hz"] < 1000 else "1 024"
                want = ["%d" % w["period_blocks"]] + f0.split() + [
                    "%.4f" % d["pair"]["high"], "%.4f" % d["pair"]["ideal_high"],
                    "%.4f" % d["slice"]["high"], "%.4f" % d["slice"]["ideal_high"], "%.5f" % d["pair"]["corr"],
                    "3..%d" % max(d["pair"]["harmonics"]),
                    "%.4f" % max(abs(d["pair"]["harmonics"][n] - d["pair"]["ideal_harmonics"][n])
                                 for n in d["pair"]["harmonics"])]
                self.assertEqual(row, want, (run, w["index"]))
        sd = dict((run, r["controls"][0]["pair_sd_bits"]) for run, r in Result.get().items())
        self.assertIn("the pair decode's s.d. is %.3f bits (RUN 33) and %.3f bits (RUN 34)" % (sd[33], sd[34]), b)

    def test_the_summary_figures(self):
        _h, b = entry(now(EV), "GBP-HW-340")
        got = dict((w["period_blocks"], w["decodes"]["pair"]["high"]) for w in Result.get()[33]["windows"])
        self.assertIn("2.5 % (128 Hz), 5.0 % (256), 9.8 % (512) and 18.7 % (1 024)", flat(b))
        self.assertEqual([round(100 * got[p], 1) for p in (32, 16, 8, 4)], [2.5, 5.0, 9.8, 18.7])
        corr = min(w["decodes"]["pair"]["corr"] for r in Result.get().values() for w in r["windows"])
        self.assertGreaterEqual(corr, 0.99998)
        self.assertIn("correlation 0.99998 or better", flat(b))
        ib = dict(((run, w["index"]), w["decodes"]["in_band"]) for run, r in Result.get().items() for w in r["windows"])
        self.assertIn("at 512 Hz the block decode's |H3|/|H1| is %.3f against the pair decode's %.3f"
                      % (ib[(33, 2)][3]["block"], ib[(33, 2)][3]["pair"]), b)
        self.assertIn("at 256 Hz its |H7|/|H1| is %.3f against %.3f" % (ib[(33, 3)][7]["block"], ib[(33, 3)][7]["pair"]), b)
        self.assertIn("at 128 Hz its |H15|/|H1| is %.3f in RUN 33 w1 and %.3f in RUN 34 w1, against %.3f"
                      % (ib[(33, 1)][15]["block"], ib[(34, 1)][15]["block"], ib[(33, 1)][15]["pair"]), b)
        import u012slices
        c = u012slices.costs()
        thousands = lambda v: "%d %06.2f" % (int(v) // 1000, v - 1000 * (int(v) // 1000))   # the record's "4 070.59"
        self.assertIn("RUN 38 drained %s/s, so it needed %.2f samples/s of DUP = %.2f ms/s, and %.3f/s = %.2f ms/s was observed"
                      % (thousands(4096 - 1626 / 64.0), c["need_samples_per_s"]["RUN 38"], c["need_ms_per_s"]["RUN 38"],
                         c["observed_dup_per_s"]["RUN 38"], c["observed_dup_ms_per_s"]["RUN 38"]), flat(b))
        self.assertIn("RUN 42 drained %s/s: %.2f/s = %.2f ms/s." % (thousands(4096 - 465 / 64.0), c["need_samples_per_s"]["RUN 42"],
                                                                   c["need_ms_per_s"]["RUN 42"]), flat(b))
        self.assertIn("one correction per chunk      %.2f ms/s       %.2f ms/s    %.2f ms/s" % tuple(
            c["one_correction_per_chunk_ms_per_s"][k] for k in ("block", "pair", "slice")), b)


class OnTopNeverRewritten(unittest.TestCase):
    def test_no_earlier_evidence_entry_was_rewritten(self):
        """Every entry at the base still starts with its base text (later Issues append), and GBP-HW-340 follows."""
        old, new = then(EV), now(EV)
        ids = re.findall(r"^#{2,3} ((?:GBP|ENV)-[A-Z]+-\d{3}) ", old, re.M)
        self.assertGreater(len(ids), 400)                                     # both heading levels are guarded
        for eid in ids:
            h0, b0 = entry(old, eid)
            h1, b1 = entry(new, eid)
            self.assertTrue(h1.startswith(h0) and b1.startswith(b0.rstrip("\n")), eid)
        self.assertEqual(re.findall(r"^#{2,3} ((?:GBP|ENV)-[A-Z]+-\d{3}) ", new, re.M)[:len(ids) + 1], ids + ["GBP-HW-340"])

    def test_the_unknowns(self):
        old, new = then(UN), now(UN)
        for uid, stop in (("U-GBP-012", r"^## U-GBP-013 "), ("U-GBP-041", r"^## U-GBP-\d{3} ")):
            h0 = re.search(r"^## %s .*$" % uid, old, re.M).group(0)
            h1 = re.search(r"^## %s .*$" % uid, new, re.M).group(0)
            self.assertTrue(h1.startswith(h0), uid)
            s0, s1 = section(old, r"^## %s " % uid, stop), section(new, r"^## %s " % uid, stop)
            self.assertTrue(s1[len(h1):].startswith(s0[len(h0):].rstrip("\n")), uid)
            self.assertIn("2026-09-24, Issue #118", s1[len(s0):], uid)
        h012 = re.search(r"^## U-GBP-012 .*$", new, re.M).group(0)
        self.assertIn("Issue #118: the FORMAT half answered for the archived tones", h012)
        self.assertIn("Hz conditional on U-GBP-041", h012)
        self.assertIn("(OPERATOR OBSERVATION)", h012)
        self.assertNotIn('answered "full"', new)
        self.assertEqual(re.search(r"^## U-GBP-041 .*$", new, re.M).group(0),
                         re.search(r"^## U-GBP-041 .*$", old, re.M).group(0))       # a consistency, no pointer
        self.assertIn("STAYS OPEN for the physical half", new)

    def test_the_run_sections(self):
        old, new = then(HT), now(HT)
        for sec, num in (("V25.12", "V25.12.10"), ("V26.11", "V26.11.9")):
            s0 = section(old, r"^### %s " % re.escape(sec))
            s1 = section(new, r"^### %s " % re.escape(sec))
            self.assertTrue(s1.startswith(s0.rstrip("\n")), sec)
            added = s1[len(s0.rstrip("\n")):]
            self.assertEqual(re.findall(r"^#### (\S+) ", added, re.M)[0], num, sec)     # later Issues append after
            self.assertIn(L2_SENTENCE, flat(added), sec)
            self.assertIn("Este decodificador entrega 4096 amostras por segundo", flat(added), sec)
        # the words the procedures froze (§V25.9, §V26.9), unchanged
        self.assertEqual(old.count("- Este decodificador entrega 4096 amostras por segundo: nada acima de ~2 kHz passa."),
                         new.count("- Este decodificador entrega 4096 amostras por segundo: nada acima de ~2 kHz passa."))
        self.assertGreaterEqual(new.count("- Este decodificador entrega 4096 amostras por segundo: nada acima de ~2 kHz passa."), 2)
        for head in (r"^### V25\.7 ", r"^### V25\.9 ", r"^### V26\.9 "):
            self.assertEqual(section(new, head), section(old, head), head)

    def test_the_protocol_page(self):
        old, new = then(AU), now(AU)
        rows_append_only(self, old, new)
        key = "| The live chain, run once"
        o = [l for l in old.splitlines() if l.startswith(key)][0].split(" | ")
        n = [l for l in new.splitlines() if l.startswith(key)][0].split(" | ")
        self.assertEqual(n[1], o[1] + " **2026-09-24, Issue #118:** `L2 PASS` means the chain reproduces on the host what "
                               "it produced on the console; it never meant the chain captures what the cartridge played "
                               "(`GBP-HW-340`).")                                # a pure append to that cell
        self.assertEqual(n[2:], o[2:])
        self.assertIn("| Slice decode (2026-09-24, Issue #118) |", new)
        self.assertIn("`L2 PASS` means the chain reproduces on the host what it produced on the console", new)
        self.assertIn("it never meant the chain captures what the cartridge played (`GBP-HW-340`)", new)
        self.assertIn("Since Issue #118 the format half is answered for the archived tones (`GBP-HW-340`)", new)
        for line in old.splitlines():
            if line.startswith("| The layout |") or line.startswith("| Steps |"):
                self.assertIn(line, new)


class TheStatusesAndTheCorrection(unittest.TestCase):
    def test_GBP_HW_315_is_untouched_and_340_claims_arithmetic(self):
        old, new = then(EV), now(EV)
        self.assertEqual(entry(new, "GBP-HW-315"), entry(old, "GBP-HW-315"))
        h, b = entry(new, "GBP-HW-340")
        for tok in ("FACT (arithmetic on the archive, recomputable)", "conditional on uniform slices (`U-GBP-041`, a HYPOTHESIS)",
                    "`GBP-HW-315` is not extended", "no game's blocks exist in the archive"):
            self.assertIn(tok, h, tok)
        self.assertIn(L2_SENTENCE, flat(b))
        self.assertIn("It is not a property of the path.", b)
        self.assertIn('"9bit / 32.768kHz"', b)
        self.assertIn("Consistency is not a test of it, and the HYPOTHESIS stands.", b)
        self.assertIn("acabei de testar neles e realmente la nao tem atraso de audio (alem de nao sair abafado)", flat(b))
        self.assertIn("as transcribed by the Orchestrator in #118's body", flat(b))
        self.assertNotIn('"full"', b)
        self.assertIn("raw sha256 `bf31d679…85046c`, printed `d8f41214…ade2aa9`", flat(b))

    def test_the_devlog_is_appended(self):
        old, new = then(DL), now(DL)
        self.assertTrue(new.startswith(old.rstrip("\n")))
        self.assertIn("## 2026-09-24 — Issue #118: does decoding the slices recover the bandwidth?", new)


if __name__ == "__main__":
    unittest.main()
