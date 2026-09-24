"""
tests/host/test_hardware_pages_cartridge_bits.py — GitHub Issue #48: the
cartridge-sensing rows of `docs/hardware/` now carry their hardware history,
and the two ways that could go wrong are pinned.

WHY THIS TEST IS NARROW, deliberately. Issue #29 measured the general
"every consolidated row must cite EVIDENCE" gate and declined to build it: it
would have been about 18 % false on the rows it could compare and blind to
84 % of them. What replaced it was an instruction to sweep before a promotion —
and this checkpoint is that instruction paying for itself, because the sweep
found these two rows citing nothing. So the test here guards THESE rows and
nothing else.

A CONSOLIDATED PAGE IS WHERE A FUTURE READER STOPS, and that is the whole risk:

  * **the read point is the result.** "A GB/GBC Game Pak sets bit 0x01" is
    false as written — the bit is CLEAR in the original byte and arrives
    186–636 µs later. A row without the read point would be worse than the row
    that said nothing.
  * **a status without its falsifier is more confident than its evidence.**
    "Nobody has yet watched the bit change while only the cartridge changed"
    travels with the status onto the page, in the same row.
  * **the value alone is not the discriminator.** Byte 0 prints `8f` in 23 of
    RUN 17's 26 reads and RUN 17 had a GBA cartridge; the count is recomputed
    here from the log so the page cannot drift from it.

And the negative that keeps the promotion honest: no id was minted, and
`GBP-CTL-001` keeps the status it had, because what the software does with the
register and what the device reports are different propositions.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GBSDOL = os.path.join(ROOT, "docs", "hardware", "GBS-DOL.md")
ARCH = os.path.join(ROOT, "docs", "hardware", "ARCHITECTURE.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
RUN17 = os.path.join(ROOT, "captures", "local", "GBP-VIDEO-004_stream-0015-run17.log")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def row(path, prefix):
    rows = [l for l in read(path).splitlines() if l.startswith(prefix)]
    assert len(rows) == 1, (path, prefix, len(rows))
    return rows[0]


class BothRowsCarryTheirHardwareHistory(unittest.TestCase):
    def rows(self):
        return (("GBS-DOL.md", row(GBSDOL, "| Cartridge sensing |")),
                ("ARCHITECTURE.md", row(ARCH, "| Control/status |")))

    def test_each_row_cites_at_least_one_hardware_id(self):
        """The sweep of Issue #48 found these two rows citing none."""
        for name, r in self.rows():
            ids = set(re.findall(r"\bGBP-HW-\d{3}\b", r))
            self.assertTrue(ids, "%s: the row cites no GBP-HW id" % name)
            self.assertIn("GBP-HW-272", ids, name)
            self.assertIn("GBP-HW-273", ids, name)
            self.assertIn("GBP-HW-274", ids, name)
            self.assertIn("GBP-HW-275", ids, name)
            # the amendment is what moved 272's second claim; a citation without it misleads
            self.assertIn("amendment", r, name)

    def test_each_row_carries_the_falsifier_beside_the_status(self):
        for name, r in self.rows():
            p = plain(r)
            self.assertIn("nobody has yet watched the bit change while only the cartridge changed", p, name)
            self.assertIn("C, not F, for the causal reading", p, name)

    def test_the_type_bit_row_carries_its_read_point(self):
        """Flattening this into 'a GB/GBC Game Pak sets bit 0x01' would erase the finding."""
        for name, r in self.rows():
            p = plain(r)
            self.assertIn("186", p, name)
            self.assertIn("636", p, name)
            self.assertRegex(p, r"CLEAR in the original byte|bit is CLEAR in the original byte", name)
            self.assertIn("indistinguishable from a GBA cartridge", p, name)
            self.assertIn("U-GBP-036", r, name)
            self.assertRegex(p, r"[Ww]hy it arrives late is UNKNOWN", name)
            self.assertIn("C, not F, for the MEANING", p, name)

    def test_each_row_says_the_value_alone_is_not_the_discriminator(self):
        for name, r in self.rows():
            p = plain(r)
            self.assertIn("23 of RUN 17's 26 reads", p, name)
            self.assertIn("unanimity", p, name)
            self.assertIn("persistence", p, name)

    def test_the_byte_zero_count_on_the_pages_is_the_count_in_the_log(self):
        if not os.path.exists(RUN17):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        reads = re.findall(r"RAW [A-Z0-9-]+ idx=4 [^\n]*data=([0-9a-f]{64})", read(RUN17))
        self.assertEqual(len(reads), 26)
        self.assertEqual(sum(1 for d in reads if d[:2] == "8f"), 23)
        for name, r in self.rows():
            self.assertIn("23 of RUN 17's 26 reads", plain(r), name)


class TheePromotionMintedNothingAndChangedNoStatus(unittest.TestCase):
    def test_no_id_was_minted(self):
        ev = read(EVIDENCE)
        self.assertEqual(max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 318)   # 285…294: Issue #62 (RUN 30 ingested, §V8.13)   # 295…300: Issue #67 (RUN 31 ingested, §V9.15); 301…302: #67's validation (the rate/layout split, U-GBP-039's probe); 303…307: #72, RUN 32; 308…311: #78, RUN 33 and RUN 34; 312: #79, duty()'s mechanism; 313: #80, the H-PWM decode; 314…316: #82, the block structure and the drain (§V18); 317: #84, the start-up stall invariance; 318: #90, RUN 36 (§V19.11)   # 318: Issue #90 (RUN 36 ingested, the output path heard: §V21.9)
        self.assertEqual(max(int(n) for n in re.findall(r"^#{2,4} +U-GBP-(\d{3})\b",
                                                        read(os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")), re.M)), 44)   # 37, 38: Issue #62 (RUN 30); 39: Issue #67 (RUN 31); 40: #72; 41…43: Issue #82 (slice spacing, shorter reads, the in-block spread); 44: #84, the start-up stalls

    def test_gbp_ctl_001_keeps_the_status_it_had(self):
        """Its claim is what the SOFTWARE does; the device's byte is a different proposition."""
        ev = read(EVIDENCE)
        body = ev[ev.index("## GBP-CTL-001 "):]
        body = body[:body.index("\n## ", 1)]
        self.assertIn("**Status:** CORROBORATED for usage of 0x01–10x".replace("10x", "0x10")[:40], body)
        self.assertIn("**HYPOTHESIS** for the meaning\nof 0x20–0x80", body)
        p = plain(body)
        self.assertIn("THE STATUS LINE ABOVE IS UNCHANGED and nothing here revises it", p)
        self.assertIn("the byte the DEVICE reports is a different proposition", p)
        self.assertIn("Neither upgrades the other", p)
        for i in ("GBP-HW-272", "GBP-HW-273", "GBP-HW-274", "GBP-HW-275", "U-GBP-036"):
            self.assertIn(i, body, i)


if __name__ == "__main__":
    unittest.main()
