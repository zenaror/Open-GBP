"""
tests/host/test_control_bit_split.py — GitHub Issue #46: the promotion of the
CONTROL bit `0x02` split, and the line that promotion must not cross.

TWO CLAIMS WITH TWO STATUSES, and the whole point is that they stay apart.

  CLAIM 1, FACT.        The original CONTROL byte reads `0x90` in the 12
                        archived logs from cartridge-less runs and `0x92` in
                        the 22 from runs with a cartridge — bit `0x02` alone,
                        34 times, no exception. It is FACT because it is
                        RECOMPUTABLE FROM THE FILES, so this test recomputes
                        it: from the logs, and by running the very command the
                        evidence entry offers to a reader.
  CLAIM 2, HYPOTHESIS.  That the bit REPORTS Game Pak presence. The archive
                        pairs no late build with an empty slot, so cartridge
                        and build era are not separated. This test pins the
                        NEGATIVE: no page anywhere under docs/ may state that
                        causal reading as FACT or CORROBORATED.

The negative is the half that rots quietly. A promotion is a moment; the
temptation to let "F" spread from the split to the cause is permanent, and it
would be invisible in a diff a year from now. So the rule is machine-checked in
the only form that survives rewording: the word FACT may stand beside bit
`0x02` and the word "presence" only in a sentence that says it is the SPLIT
that is fact.

It also pins what must NOT happen to `U-GBP-017`: one of its three Needs is
answered, the item stays OPEN at P2, and no test here lets it close.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LOCAL = os.path.join(ROOT, "captures", "local")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
REGISTERS = os.path.join(ROOT, "docs", "protocol", "REGISTERS.md")
DOCS = os.path.join(ROOT, "docs")

CARTLESS = ["avsvc-0001", "init-0001", "initirq-0001", "initirq4-0001", "initirqa-0001", "initirqb-0001",
            "video-0001", "vstate-0001", "vstate-0002", "vstate-0003", "vstate-0004", "vstate-prewait-5000"]
WITH_CART = ["color-0001", "color-0002", "stream-0003", "stream-0004", "stream-0005", "stream-0005-run2",
             "stream-0005-run3", "stream-0006-run4", "stream-0007-run5", "stream-0008-run6", "stream-0009-run7",
             "stream-0009-run8", "stream-0010-run10", "stream-0010-run9", "stream-0011-run11", "stream-0013-run12",
             "stream-0013-run13", "stream-0014-run14", "stream-0014-run15", "stream-0015-run16",
             "stream-0015-run17", "stream-0015-run18"]


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def entry():
    """The GBP-HW-272 entry, alone."""
    d = read(EVIDENCE)
    i = d.index("### GBP-HW-272 ")
    j = d.index("\n### ", i + 1)
    return d[i:j]


def docs_markdown():
    for base, _, files in os.walk(DOCS):
        for fn in sorted(files):
            if fn.endswith(".md"):
                yield os.path.join(base, fn)


class TheSplitIsRecomputedNotQuoted(unittest.TestCase):
    """CLAIM 1 is FACT because of this, and for no other reason."""

    def origins(self):
        out = {}
        for fn in sorted(os.listdir(LOCAL)):
            if not fn.endswith(".log"):
                continue
            m = re.search(r"CONTROL semantic orig=([0-9a-f]+)", read(os.path.join(LOCAL, fn)))
            if m:
                out[fn.split("_", 1)[1][:-4]] = int(m.group(1), 16)
        return out

    def setUp(self):
        if not os.path.isdir(LOCAL) or not any(f.endswith(".log") for f in os.listdir(LOCAL)):
            self.skipTest("no local archive on this host (captures/local is ignored)")

    def test_the_split_is_in_the_files(self):
        o = self.origins()
        self.assertEqual(len(o), 34, "the archive carries %d logs with the field, not 34" % len(o))
        self.assertEqual(sorted(b for b, v in o.items() if v == 0x90), sorted(CARTLESS))
        self.assertEqual(sorted(b for b, v in o.items() if v == 0x92), sorted(WITH_CART))
        self.assertEqual(sorted(set(o.values())), [0x90, 0x92])
        # the difference is that bit and nothing else, which is the claim
        self.assertEqual(0x90 ^ 0x92, 0x02)
        for b, v in o.items():
            self.assertEqual(v & ~0x02, 0x90, b)
            self.assertEqual(v & 0x01, 0, "%s: bit 0x01 is not 0" % b)

    def test_the_entry_enumerates_exactly_those_logs(self):
        o = self.origins()
        e = entry()
        for b in sorted(o):
            self.assertIn(b, e, "GBP-HW-272 does not enumerate %s" % b)
        # and enumerates nothing the archive does not have: the two lists in the
        # entry's own table are compared as SETS against the two families of files
        block = e[e.index("```text"):e.index("```", e.index("```text") + 8)]
        listed = {}
        for value, want in (("0x90", 0x90), ("0x92", 0x92)):
            seg = block[block.index("orig = %s" % value):]
            seg = seg[:seg.index("\norig = ")] if "\norig = " in seg else seg[:seg.index("difference")]
            listed[want] = set(re.findall(r"\b(?:stream|vstate|color|initirq[a-b4]?|init|avsvc|video)-[0-9a-z-]+", seg))
        self.assertEqual(listed[0x90], {b for b, v in o.items() if v == 0x90})
        self.assertEqual(listed[0x92], {b for b, v in o.items() if v == 0x92})
        self.assertEqual(len(listed[0x90]), 12)
        self.assertEqual(len(listed[0x92]), 22)
        self.assertIn("12 logs", plain(e))
        self.assertIn("22 logs", plain(e))

    def test_the_six_logs_without_the_field_are_accounted_for_not_dropped(self):
        """A curated 34 would not be FACT. The rule has to be mechanical."""
        missing = [f for f in sorted(os.listdir(LOCAL))
                   if f.endswith(".log") and "CONTROL semantic orig=" not in read(os.path.join(LOCAL, f))]
        self.assertEqual(len(missing), 6, missing)
        e = plain(entry())
        self.assertIn("The selection rule is mechanical, not curated", e)
        self.assertIn("None of the six was dropped by a judgement about what it showed", e)
        for tok in ("probe-0001", "smoke-0002", "init-0001-semGBP"):
            self.assertIn(tok, e, tok)
        # the two device-less runs really do abort before reading a register
        for f in ("GBP-INIT-001_init-0001-semGBP.log",):
            self.assertIn("abort_not_present", read(os.path.join(LOCAL, f)))

    def test_the_command_the_entry_offers_a_reader_actually_runs(self):
        """'Anyone can re-derive it' is a claim like any other, so it is tested."""
        m = re.search(r"```text\n(grep -ho [^\n]+)\n", entry())
        self.assertTrue(m, "GBP-HW-272 carries no runnable derivation")
        out = subprocess.run(["bash", "-c", m.group(1)], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = dict((v, int(n)) for n, v in re.findall(r"\s*(\d+) CONTROL semantic orig=([0-9a-f]+)", out.stdout))
        self.assertEqual(got, {"90": 12, "92": 22}, out.stdout)
        # and the entry prints the same output it would produce
        for line in ("     12 CONTROL semantic orig=90", "     22 CONTROL semantic orig=92"):
            self.assertIn(line, entry())


class TheTwoClaimsAreKeptApart(unittest.TestCase):
    def test_the_entry_states_both_statuses_and_which_is_which(self):
        e = plain(entry())
        self.assertIn("FACT for the split", e)
        self.assertIn("that the bit REPORTS Game Pak presence is HYPOTHESIS", e)
        self.assertIn("CLAIM 1 — the split. FACT.", e)
        self.assertIn("CLAIM 2 — that bit 0x02 reports Game Pak presence. HYPOTHESIS. Not FACT, and not CORROBORATED either.", e)
        self.assertIn("This is FACT because anyone can re-derive it from the files", e)
        self.assertIn("Unlikely is not measured", e)

    def test_the_confound_is_in_the_entry_with_its_empty_diagonal(self):
        e = plain(entry())
        self.assertIn("The two-by-two has an empty diagonal", e)
        self.assertIn("no Game Pak 12 logs 0x90 NONE", e)
        self.assertIn("Game Pak NONE 22 logs 0x92", e)
        self.assertIn("are not separated by this archive", e)

    def test_the_breaker_is_named_and_is_not_authorised_here(self):
        e = plain(entry())
        self.assertIn("one boot of 12-stream with the cartridge REMOVED", e)
        self.assertIn("Not pre-registered and not authorised here", e)
        self.assertIn("it is not folded into RUN 21 / RUN 22", e)
        self.assertIn("play-0001 cannot do it", e)

    def test_dolphin_is_refused_as_corroboration_for_the_right_reason(self):
        e = plain(entry())
        self.assertIn("Dolphin is not corroboration for this", e)
        self.assertIn("bit 2 of the IRQ register (index 0xD)", e)
        self.assertIn("a different bit in a different register", e)
        # and the usage/measurement distinction is stated, not implied
        self.assertIn("not a second independent measurement of what the DEVICE reports", e)

    def test_the_limits_ride_with_it(self):
        e = plain(entry())
        for tok in ("One console, one Game Boy Player, one flashcart as the only cartridge ever inserted",
                    "one instant of one sequence", "nothing about a GB/GBC cartridge"):
            self.assertIn(tok, e, tok)

    def test_the_reconciliation_sweep_recorded_its_outcome_including_nothing(self):
        e = plain(entry())
        self.assertIn("THE RECONCILIATION SWEEP", e)
        self.assertIn("outcome recorded INCLUDING \"nothing\"", e)
        self.assertIn("Nothing had to be corrected, relocated or weakened, and that is the finding rather than an absence of one", e)
        self.assertIn("If the sweep had found a page asserting the causal claim, that page would have been corrected here", e)
        for tok in ("GBP-CTL-001", "U-GBP-017", "REGISTERS.md", "GBS-DOL.md", "ARCHITECTURE.md"):
            self.assertIn(tok, e, tok)


class TheCausalClaimIsNowhereStatedAsSettled(unittest.TestCase):
    """THE NEGATIVE. This is the test that has to outlive the checkpoint."""

    CAUSAL = re.compile(r"(0x02|CART_INSERTED)[^.]{0,200}?presen[ct]|presen[ct][^.]{0,200}?(0x02|CART_INSERTED)", re.I)
    SETTLED = re.compile(r"\b(FACT|CORROBORATED)\b")

    @staticmethod
    def units(text):
        """Paragraph, or single table row.

        THE UNIT MATTERS MORE THAN THE PATTERNS, and getting it wrong is how this
        test would have passed while doing nothing. The first version split on
        sentence punctuation, so "bit 0x02 reports Game Pak presence; this is
        FACT." became two units — the claim in one, its status in the other — and
        the injected offender sailed through. A claim and the word that settles it
        live in the same paragraph or the same row; that is the unit.
        """
        for block in re.split(r"\n\s*\n", text):
            if block.lstrip().startswith("|"):
                for line in block.splitlines():
                    yield line
            else:
                yield block

    def test_no_page_calls_the_causal_reading_fact_or_corroborated(self):
        offenders = []
        for path in docs_markdown():
            for sent in self.units(read(path)):
                if not self.CAUSAL.search(sent) or not self.SETTLED.search(sent):
                    continue
                # Allowed: a sentence that names WHICH proposition is settled — the SPLIT
                # (this project's measurement) or the references' USAGE of the bit — or one
                # that says in as many words that the causal reading is NOT settled. What is
                # forbidden is the bare upgrade: "bit 0x02 reports presence" + FACT.
                p = plain(sent)
                if ("split" in p.lower() or "HYPOTHESIS" in p or "Not FACT" in p or "differ" in p.lower()
                        or "usage" in p.lower()):
                    continue
                offenders.append((os.path.relpath(path, ROOT), p[:160]))
        self.assertEqual(offenders, [], "a page states the bit-0x02 causal reading as settled:\n%s" %
                         "\n".join("%s: %s" % o for o in offenders))

    def test_the_register_page_carries_three_separate_markers_on_that_row(self):
        row = [l for l in read(REGISTERS).splitlines() if l.startswith("| 0x02 |")]
        self.assertEqual(len(row), 1, row)
        r = row[0]
        self.assertIn("C (usage)", r)                       # what the references do with the bit
        self.assertIn("F (hw, 34 logs", r)                  # what this project measured
        self.assertIn("H for the CAUSE", r)                 # the step between them
        self.assertIn("GBP-HW-272", r)
        # bit 0x01's row states its single state as NOT a result
        r1 = [l for l in read(REGISTERS).splitlines() if l.startswith("| 0x01 |")][0]
        self.assertIn("ONE OBSERVED STATE", r1)
        self.assertIn("one state is not a result", r1)
        self.assertIn("GBP-HW-272", r1)
        # and the page says why the two columns are different claims
        p = plain(read(REGISTERS))
        self.assertIn("The usage column and the hardware column are different claims", p)
        self.assertIn("Neither upgrades the other", p)

    def test_the_guard_bites(self):
        """A negative that cannot fail is decoration. This is the offender it exists for."""
        offender = "On hardware, bit 0x02 reports Game Pak presence; this is FACT."
        u = list(self.units(offender))
        self.assertEqual(len(u), 1)
        self.assertTrue(self.CAUSAL.search(u[0]) and self.SETTLED.search(u[0]))
        p = plain(u[0])
        self.assertFalse("split" in p.lower() or "HYPOTHESIS" in p or "Not FACT" in p
                         or "differ" in p.lower() or "usage" in p.lower(),
                         "the allow-list would let the bare upgrade through")
        # the table-row form too
        row = "| 0x02 | read -> status flag present | ... | CART_INSERTED | FACT |"
        self.assertEqual(len(list(self.units(row))), 1)
        self.assertTrue(self.CAUSAL.search(row) and self.SETTLED.search(row))

    def test_the_split_itself_is_allowed_to_be_fact(self):
        """The negative must not be so wide that it forbids the promotion."""
        self.assertIn("FACT", entry())
        self.assertTrue(self.CAUSAL.search(entry()))


class TheUnknownStaysOpen(unittest.TestCase):
    def body(self):
        d = read(UNKNOWNS)
        i = d.index("## U-GBP-017 (P2) —")
        j = d.index("\n## ", i + 1)
        return d[i:j]

    def test_it_is_not_closed_and_keeps_its_priority(self):
        b = self.body()
        self.assertIn("U-GBP-017 (P2)", b)
        self.assertIn("The item stays\nOPEN at P2 and nothing here closes it", b)
        self.assertNotIn("RESOLVED", b)
        self.assertNotIn("CLOSED", b)
        # it is still in the open part of the page: the resolved section comes later
        d = read(UNKNOWNS)
        res = d.find("# Resolved")
        if res == -1:
            res = d.find("## Resolved")
        if res != -1:
            self.assertLess(d.index("## U-GBP-017 (P2) —"), res)

    def test_one_need_is_answered_the_other_two_are_not(self):
        b = plain(self.body())
        self.assertIn("run with a cartridge ANSWERED FROM THE ARCHIVE, FOR BIT 0x02 ONLY, 2026-09-22", b)
        self.assertIn("repeat run STILL OPEN", b)
        self.assertIn("run after a stop sequence STILL OPEN", b)
        self.assertIn("It had already happened 22 times", b)
        self.assertIn("GBP-HW-272, FACT for the split", b)
        self.assertIn("That the bit REPORTS presence stays HYPOTHESIS", b)
        self.assertIn("the meaning of 0x10 and 0x80", b)
        self.assertIn("GBP-HW-272 speaks about ONE bit of the byte and says nothing about the rest", b)
        # the original Needs sentence is kept, not rewritten
        self.assertIn("Needs: repeat run, run with a cartridge, run after a controlled stop sequence", b)


if __name__ == "__main__":
    unittest.main()
