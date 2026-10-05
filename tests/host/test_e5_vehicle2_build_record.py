"""tests/host/test_e5_vehicle2_build_record.py -- GitHub Issue #158: the records of the build half of vehicle-0002 (HARDWARE_TESTS.md V31.13, the DEVLOG entry, the HANDOFF paragraphs).

Durable, append-only forms (no whole-file equality):
  * V31.13 exists once, starts its block, follows V31.12, and carries the identities: the candidate's DOL and unpadded SHA-256, the commit, the reproduced reference
    (a02bcfa3..., vehicle-0001's pin), the two rebuilds, the gate's verbatim output with its SAME verdict and its nine-function closure, the decisions of the central session
    (numbered symbols by content, gbp_v28_step_hook a fixed root, R1, A1, R4), what the gate does NOT establish (timing), R2 and R3, the reserved slot;
  * every block of the files as they stood at the last source commit (7d2f58f) is found now, under a heading that starts with its heading, its body starting with its body of
    then (both heading levels); EVIDENCE.md gained nothing (no run, no evidence);
  * the slot name 29-vehicle2 is in the record and nowhere in tools/swiss-layout.tsv;
  * the DEVLOG entry and the two HANDOFF paragraphs exist once, in order.
"""
import difflib
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import guards  # noqa: E402

BASE = "7d2f58fb60f0993e6a5d30b12bdc516dff9700de"   # the last source commit of Issue #158 (HEAD when the records were written)
HT, EV, DEVLOG, HANDOFF = "docs/research/HARDWARE_TESTS.md", "docs/research/EVIDENCE.md", "docs/research/DEVLOG.md", "docs/HANDOFF.md"
SEC = "### V31.13 THE BUILD HALF OF `vehicle-0002` — the GBA play image that also writes the startup profile and the Policy A invariants, BUILT at `7d2f58f`"
DOL = "02f89ccd1b07b10165d6d7b4287bf1b056a2a673661c89ad8e5b506fe56c55d8"
UNPADDED = "e3fa4b4a0a481057d4ccab7611fc5fb71da292f2ba6fcdb1212c0eadbdd71deb"
REFERENCE = "a02bcfa3b84ccd363d7bad54c8e72411d9f2e9a49595963903d1feeac4acf5d2"
DEVLOG_HEAD = "## 2026-10-05 — Issue #158: the play image `vehicle-0002` built at `7d2f58f`"
HANDOFF_BLOCKER = "**2026-10-05 (Issue #158), on top: the play image `vehicle-0002` is BUILT at `7d2f58f` and is a candidate"
HANDOFF_NEXT = "**2026-10-05 (Issue #158), on top: Issue #158 is done"
NEXT = "the next physical Phase 7 session, on vehicle-0002, to be pre-registered by its own hardware Issue"
CLOSURE = "draw_quad, gbp_v28_step_hook, live_dma_cb, live_tap, offer_oldest_ready, on_draw_done, pump, submit_ready, v28_phase_snap_take"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def base(rel):
    b = guards.show(BASE, rel)
    return b.decode("utf-8") if isinstance(b, bytes) else b


def flat(s):
    return " ".join(s.replace("`", "").replace("**", "").split())


def section(text, head):
    i = text.index(head)
    j = text.find("\n### ", i + 1)
    return text[i:j if j > 0 else len(text)]


def blocks(text):
    heads = list(re.finditer(r"^#{1,4} .*$", text, re.M))
    out = [("", text[:heads[0].start()] if heads else text)]
    for i, m in enumerate(heads):
        out.append((m.group(0), text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]))
    return out


def body(b):
    b = b.rstrip("\n")
    if b.endswith("\n---"):
        b = b[:-4].rstrip("\n")
    return b


class TheEarlierRecordsAreOnTopUnchanged(unittest.TestCase):
    def setUp(self):
        if not guards.base_available(BASE):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE)

    def walk(self, old, new):
        o, n = blocks(old), blocks(new)
        j = 0
        for h0, b0 in o:
            while j < len(n) and not n[j][0].startswith(h0):
                j += 1
            self.assertLess(j, len(n), "the block %r is gone or its heading changed" % h0[:70])
            self.assertTrue(n[j][1].startswith(body(b0)), "the text under %r changed above its end" % h0[:70])
            j += 1
        return len(o)

    def test_hardware_tests_devlog_and_handoff_only_gained_text(self):
        self.assertNotIn("### V31.13", base(HT))
        self.assertGreater(self.walk(base(HT), read(HT)), 1300)
        self.assertGreater(self.walk(base(DEVLOG), read(DEVLOG)), 380)
        # the HANDOFF gains its paragraphs ON TOP of each section, so its blocks no longer start with their old bodies: only insertions, no line lost or changed
        removed = [x for x in difflib.unified_diff(base(HANDOFF).splitlines(), read(HANDOFF).splitlines(), lineterm="", n=0)
                   if x.startswith("-") and not x.startswith("---")]
        self.assertEqual(removed, [])

    def test_v31_12_and_v31_8_are_untouched_block_by_block(self):
        for head in ("### V31.8 ", "### V31.12 "):
            self.assertGreaterEqual(self.walk(section(base(HT), head), section(read(HT), head)), 1, head)
            self.assertEqual(section(base(HT), head), section(read(HT), head), "%s: the section of then, nothing appended inside it" % head)

    def test_no_evidence_entry_no_run_no_evidence(self):
        ids_then = re.findall(r"^#{2,3} ((?:GBP|ENV)-[A-Z]+-\d{3}) ", base(EV), re.M)
        ids_now = re.findall(r"^#{2,3} ((?:GBP|ENV)-[A-Z]+-\d{3}) ", read(EV), re.M)
        self.assertEqual(ids_now, ids_then)
        self.assertEqual(ids_now[-1], "GBP-HW-384")
        self.assertEqual(read(EV), base(EV))


class TheNewSection(unittest.TestCase):
    def test_v31_13_exists_once_starts_its_block_and_follows_v31_12(self):
        t = read(HT)
        self.assertEqual(t.count(SEC), 1)
        self.assertEqual(len(re.findall(r"^### V31\.13 ", t, re.M)), 1)
        heads = [m.group(0) for m in re.finditer(r"^### V31\.\d+ ", t, re.M)]
        self.assertEqual(heads[heads.index("### V31.12 ") + 1], "### V31.13 ")
        self.assertEqual(t[t.index(SEC) - 2:t.index(SEC)], "\n\n")
        self.assertLess(t.index("### V31.12 "), t.index(SEC))
        # the parent heading of V31 is the one of then (the higher heading level)
        self.assertEqual(len(re.findall(r"^## V31 — PHASE 7's E5 VEHICLE: the GBA play image", t, re.M)), 1)
        self.assertLess(t.index("## V31 — PHASE 7's E5 VEHICLE"), t.index(SEC))

    def test_the_identities(self):
        s = section(read(HT), SEC)
        for tok in (DOL, UNPADDED, REFERENCE, "512 224 B", "512 244 B", "commit 7d2f58f", "OPENGBP-IDENT gbp-play-gba2 vehicle-0002 7d2f58f",
                    "V28MARK 0, V28DMA 0, -dirty 0", "the two DOLs byte-identical (cmp)", "--require-aligned: ok", "bc97ba3", "d8f8603", "f462c67", "d2fb332"):
            self.assertIn(tok, s, tok)
        self.assertIn("29-vehicle2 is RESERVED here and nowhere else", s)
        # AMENDED ON TOP (Hardware Issue #161, 2026-10-05): "nowhere in the manifest" is a claim about BASE (the commit these records were written on); it is asserted THERE, and the
        # manifest now carries exactly the one row the hardware Issue pinned
        then = base("tools/swiss-layout.tsv")
        self.assertNotIn("vehicle2", then)
        self.assertNotIn("gbp-play-gba2", then)
        rows = [l.split("\t") for l in read("tools/swiss-layout.tsv").split("\n") if l and not l.startswith("#")]
        self.assertEqual([r for r in rows if r[0] == "29"],
                         [["29", "vehicle2", "gbp-play-gba2", "gbp-play-gba2.dol", "gbp-play-gba2", "vehicle2", "1", "02f89ccd1b07b10165d6d7b4287bf1b056a2a673661c89ad8e5b506fe56c55d8"]])

    def test_the_gate_output_is_verbatim_and_passes(self):
        s = section(read(HT), SEC)
        i = s.index("**The gate on the candidate: the tool's full output, verbatim**")
        block = re.search(r"```text\n(hotpath_cmp -- the hot-path identity gate \(Issue #158\)\n.*?)\n```", s[i:], re.S).group(1)
        lines = block.split("\n")
        self.assertEqual(len(lines), 50)
        self.assertEqual(lines[-1], "RESULT: SAME -- 0 differences (the gate PASSES)")
        self.assertIn("differences: library 0, main.o 0", lines)
        self.assertIn("closure (reference, 9): " + CLOSURE, lines)
        self.assertIn("closure (candidate, 9): " + CLOSURE, lines)
        self.assertIn("compiler-numbered symbols compared by content (reference): CSWTCH.194 -> CSWTCH.N#3294394efed92df6", lines)
        self.assertIn("compiler-numbered symbols compared by content (candidate): CSWTCH.209 -> CSWTCH.N#3294394efed92df6", lines)
        data = [l for l in lines if l.startswith("named data objects compared by content")]
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0].split(": ", 1)[1], data[1].split(": ", 1)[1], "the 66 content keys are the same on both sides")
        self.assertIn("(reference, 66)", data[0])
        self.assertIn("linked objects: reference 35, candidate 36 (extra objects expected in the candidate only: gbp_startrec)", lines)
        self.assertIn("roots: pump, live_tap, live_dma_cb, on_draw_done, gbp_v28_step_hook", lines)
        self.assertIn("NOT ESTABLISHED: timing identity (code and data addresses move, and with them cache placement)", lines)

    def test_the_decisions_the_controls_and_what_is_not_established(self):
        s = flat(section(read(HT), SEC))
        for tok in ("Compiler-numbered local symbols are compared by CONTENT, never by number", "CSWTCH.222", "gbp_v28_step_hook is a FIXED root",
                    "ap2.step_pushes, src/audio/gbp_aplay2.c:175", "R1, after the heavy review", "every non-debug section of every library object by its BYTES",
                    "A1, after the heavy review", "R4:", "What it does NOT establish: TIMING identity", "(i) synthetic pairs", "RESULT: SAME -- 0 differences",
                    "RESULT: DIFFERENT -- 1524 difference(s)", "Real-data mutants", ".data.z_can_act → DIFFERENT (7)", "Before R1 each of them read SAME",
                    "What Dolphin does not say", "does not read the SD log", "It says nothing about the Game Boy Player"):
            self.assertIn(flat(tok), s, tok)

    def test_r2_and_r3(self):
        s = flat(section(read(HT), SEC))
        self.assertIn("= 92 (vehicle-0001: 87; the difference is the five new lines), against KEYLOG_TAIL_RESERVE 1280, which was not raised", s)
        self.assertIn("it is MEASURED (462 lines in RUN 17, another image, by the central session's review), not bounded", s)
        self.assertIn("the vehicle profile also passes vehicle-0002 and does not tell the two images apart", s)
        self.assertIn("an image's identity is its hash and its IDENT, not its profile", s)

    def test_no_run_no_verdict_no_evidence(self):
        s = flat(section(read(HT), SEC))
        self.assertIn("NOT PHYSICALLY EXECUTED, NOT STAGED, NOT PINNED, NO RUN AUTHORISED HERE", s)
        self.assertIn("no EVIDENCE.md entry", s)
        self.assertIn("No session verdict", s)
        self.assertNotRegex(s, r"(?i)\bphysically (?:validated|tested)\b(?! GBP-VIDEO-001)")


class TheStateFiles(unittest.TestCase):
    def test_the_devlog_entry(self):
        d = read(DEVLOG)
        self.assertEqual(d.count(DEVLOG_HEAD), 1)
        self.assertLess(d.index("## 2026-10-05 — Issue #159: "), d.index(DEVLOG_HEAD))
        e = d[d.index(DEVLOG_HEAD):]
        for tok in (DOL, "a02bcfa3", "3984 passed", "Next.", "next physical Phase 7 session, on `vehicle-0002`, to be pre-registered by its own hardware Issue"):
            self.assertIn(tok, e, tok)

    def test_the_handoff_paragraphs(self):
        h = read(HANDOFF)
        for heading, para in (("## Current blocker / current question\n\n", HANDOFF_BLOCKER), ("## Next safe action\n\n", HANDOFF_NEXT)):
            sec = h.split(heading)[1].split("\n## ")[0]
            self.assertEqual(sec.count(para), 1, heading)
            self.assertLess(sec.index(para), sec.index("Issue #159), on top:"), heading)
        self.assertIn(NEXT, h)
        self.assertIn(DOL, h)


if __name__ == "__main__":
    unittest.main()
