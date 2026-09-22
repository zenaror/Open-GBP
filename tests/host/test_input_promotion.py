"""
tests/host/test_input_promotion.py — the promotion of the input path into the
consolidated documentation (GitHub Issue #26, 2026-09-21).

Pinned: the two stale statements are gone — INITIALIZATION.md's "KEYPAD,
never written" carries a dated supersession and a §15 records the first
physical writes; REGISTERS.md's KEYPAD row and §2.3, GBS-DOL.md's keypad row
and ARCHITECTURE.md's keypad plane state the L/R order as CORROBORATED and
never as FACT, with the generic-pad scope and GBP-KEY-009 beside it, and the
wrong "active-low" polarity is gone; the new docs/protocol/INPUT.md carries
only F / C rows, each with an id that exists, marks the controller mapping as
POLICY, and says what is not established; the page indexes list it; nothing
frozen moved — HARDWARE_TESTS §V7, the evidence headings and U-GBP-010 are the
bytes of 4e54583, no GBP-HW id was minted, nothing under src/, poc/, tools/
or Makefile changed.
"""
import os
import re
import subprocess
import unittest

import guards

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = lambda *p: os.path.join(ROOT, "docs", *p)
INPUT = D("protocol", "INPUT.md")
REGISTERS = D("protocol", "REGISTERS.md")
INIT = D("protocol", "INITIALIZATION.md")
VIDEO = D("protocol", "VIDEO.md")
GBSDOL = D("hardware", "GBS-DOL.md")
ARCH = D("hardware", "ARCHITECTURE.md")
EVIDENCE = D("research", "EVIDENCE.md")
UNKNOWNS = D("research", "UNKNOWNS.md")
HW = D("research", "HARDWARE_TESTS.md")
HANDOFF = D("HANDOFF.md")
ROADMAP = D("ROADMAP.md")
DEVLOG = D("research", "DEVLOG.md")
BASE = "4e5458397e4feef7b985db77aaad79bf11a05044"   # origin/main before Issue #26
PAGES_STATING_THE_ORDER = (INPUT, REGISTERS, GBSDOL, ARCH)
ID = re.compile(r"\b(GBP-(?!VIDEO|BBA|INIT|AV|PROBE|BASELINE|INPUT)[A-Z]+-\d{3}|ENV-[A-Z]+-\d{3}|U-GBP-\d{3}|U-ENV-\d{3})\b")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def flat(s):
    return re.sub(r"\s+", " ", s)


def git_show(path, commit=BASE):
    r = subprocess.run(["git", "-C", ROOT, "show", "%s:%s" % (commit, path)], capture_output=True, text=True)
    return None if r.returncode != 0 else r.stdout


def defined_ids():
    ids = set()
    for p in (EVIDENCE, UNKNOWNS):
        for m in re.finditer(r"^#{2,4} +((?:GBP|ENV)-[A-Z]+-\d{3}|U-(?:GBP|ENV)-\d{3})\b", read(p), re.M):
            ids.add(m.group(1))
    return ids


def rows(text):
    out = []
    for l in text.splitlines():
        if l.startswith("| ") and not l.startswith("| ---") and not re.match(r"^\| (Property|Bits|Who|GameCube) \|", l):
            out.append([c.strip() for c in re.split(r"(?<!\\)\|", l.strip()[1:-1])])
    return out


def fact_never_asserted_for_the_order(text):
    """Every 'FACT' that stands near a statement of the L/R order or the routing is a negation."""
    bad = []
    for m in re.finditer(r"\bFACT\b", text):
        pre = text[max(0, m.start() - 200):m.start()]
        if re.search(r"bit 8|bit 9|bits 8|L/R|L and R|routing|order", pre):
            if not re.search(r"\b(not|NOT|never|Never)\b", text[max(0, m.start() - 45):m.start()]):
                bad.append(text[max(0, m.start() - 80):m.end() + 20].replace("\n", " "))
    return bad


class TheStaleStatementsAreGoneWithTheirHistoryKept(unittest.TestCase):
    def test_initialization_supersedes_never_written_on_a_date_and_adds_the_dated_section(self):
        t = read(INIT)
        self.assertEqual(t.count("## 15. KEYPAD written on hardware — GBP-INPUT-001, RUN 14 / RUN 15 (2026-09-21)"), 1)
        for m in re.finditer(r"KEYPAD has never been\s+written|KEYPAD, never written", t):
            self.assertIn("2026-09-21", t[m.end():m.end() + 140], t[m.start():m.end() + 140])
        self.assertNotIn("KEYPAD (Phase 5),", t)
        self.assertEqual(t.count("KEYPAD (Phase 5 — written on hardware 2026-09-21, §15)"), 2)
        f = flat(t)
        for tok in ("Until 2026-09-21 every \"KEYPAD, never written\" above was true", "7 892 and 7 895 completed 32-byte writes at index 0xC",
                    "Question M = PASS", "not part of the interrupt service at all", "CORROBORATED, not FACT, for the L/R order",
                    "generic third-party pad", "GBP-HW-262", "GBP-HW-264", "GBP-HW-265", "GBP-KEY-006", "`INPUT.md`"):
            self.assertIn(tok, f, tok)
        old = git_show("docs/protocol/INITIALIZATION.md")
        if old is not None:
            before_15 = t[:t.index("## 15. KEYPAD written on hardware")]
            self.assertEqual(old.count("KEYPAD, never written"), before_15.count("KEYPAD, never written"), "history kept: the sentence stays, annotated")
            self.assertEqual(old.count("KEYPAD has never been"), before_15.count("KEYPAD has never been"))

    def test_registers_states_the_order_as_corroborated_with_its_history(self):
        t = read(REGISTERS)
        self.assertNotIn("H (L/R bit order)", t)
        row = [l for l in t.splitlines() if l.startswith("| 0xC | KEYPAD |")]
        self.assertEqual(len(row), 1)
        r = row[0]
        # Issue #33 (2026-09-21) promoted the row to F (hw, run-scoped) by RUN 17 / RUN 18 with this checkpoint's C kept as history
        for tok in ("L/R bit order: F (hw, run-scoped) since 2026-09-21", "C — was H until 2026-09-21", "then not FACT", "generic third-party pad", "GBP-KEY-009", "GBP-KEY-004",
                    "GBP-HW-262", "GBP-HW-265", "GBP-HW-270", "U-GBP-010 CLOSED", "`INPUT.md`", "lo byte = GBA keys 0–7; hi bit0→L(key 9), bit1→R(key 8)"):
            self.assertIn(tok, r, tok)
        self.assertEqual(t.count("### 2.3 KEYPAD word"), 1)
        s23 = t[t.index("### 2.3 KEYPAD word"):t.index("## 3. CONTROL register bits")]
        self.assertIn("C, not FACT", s23)                                             # the history of Issue #26
        self.assertIn("F (hw, run-scoped) since 2026-09-21", s23)                     # Issue #33
        self.assertIn("generic third-party pad", s23)
        self.assertIn("GBP-KEY-009", s23)

    def test_gbs_dol_and_architecture_rows_are_refreshed_and_the_wrong_polarity_is_gone(self):
        g = read(GBSDOL)
        self.assertNotIn("H (L/R order)", g)
        self.assertNotIn("order per Dolphin swapped", g)
        row = [l for l in g.splitlines() if l.startswith("| Keypad injection |")]
        self.assertEqual(len(row), 1)
        for tok in ("bit 8 = L, bit 9 = R", "1 = pressed", "C (L/R order)", "not FACT", "generic third-party pad", "GBP-KEY-009",
                    "GBP-HW-262", "GBP-HW-265", "`docs/protocol/INPUT.md`"):
            self.assertIn(tok, row[0], tok)
        self.assertIn("geometry F (hw)", flat(g), "the video row is untouched")
        a = read(ARCH)
        self.assertNotIn("active-low", a, "the KEYPAD window is 1 = pressed (GBP-KEY-001, GBP-KEY-005); the old row contradicted the evidence")
        row = [l for l in a.splitlines() if l.startswith("| Keypad |")]
        self.assertEqual(len(row), 1)
        for tok in ("1 = pressed", "opposite polarity", "bit 8 and R at bit 9", "not FACT", "generic third-party pad", "GBP-KEY-005", "GBP-HW-265", "../protocol/INPUT.md"):
            self.assertIn(tok, row[0], tok)
        self.assertIn("- KEYPAD word and the input path: `docs/protocol/INPUT.md`", a)

    def test_the_video_page_pointer_is_dated_and_the_indexes_list_the_new_page(self):
        v = read(VIDEO)
        self.assertNotIn("KEYPAD, never written (Phase 5)", v)
        self.assertIn("written on hardware 2026-09-21", v)
        for p, tok in ((D("protocol", "README.md"), "`INPUT.md`"), (D("README.md"), "protocol/INPUT.md"), (D("hardware", "README.md"), "../protocol/INPUT.md")):
            self.assertIn(tok, read(p), p)


def fact_for_the_order_is_run_scoped(text):
    """Issue #33 (2026-09-21): RUN 17 / RUN 18 made the routing FACT (hw, the runs). Every 'FACT' that stands near a
    statement of the L/R order or the routing is now either a negation (the history this promotion keeps) or the
    run-scoped one -- tied, within its sentence, to `(hw`, GBP-HW-270, the join or GBP-INPUT-002."""
    bad = []
    for m in re.finditer(r"\bFACT\b", text):
        pre = text[max(0, m.start() - 200):m.start()]
        if re.search(r"bit 8|bit 9|bits 8|L/R|L and R|routing|order", pre):
            if re.search(r"\b(not|NOT|never|Never)\b", text[max(0, m.start() - 45):m.start()]):
                continue
            ctx = text[max(0, m.start() - 160):m.end() + 160]
            if not re.search(r"\(hw|GBP-HW-270|the join|GBP-INPUT-002|machine join", ctx):
                bad.append(text[max(0, m.start() - 80):m.end() + 20].replace("\n", " "))
    return bad


class TheOrderWasCorroboratedUntilTheJoinAndThePadScopeTravelsWithIt(unittest.TestCase):
    def test_every_fact_about_the_order_is_the_run_scoped_one_or_a_kept_negation(self):
        """Until Issue #33 this test asserted that no page states the order or the routing as FACT
        (fact_never_asserted_for_the_order). RUN 17 / RUN 18 changed the fact; the pin now asserts the shape the
        promotion must keep: every FACT near the order is run-scoped and cites the join, and the history stays."""
        for p in PAGES_STATING_THE_ORDER:
            with self.subTest(page=os.path.relpath(p, ROOT)):
                self.assertEqual(fact_for_the_order_is_run_scoped(read(p)), [])
                t = flat(read(p))
                self.assertNotIn("order is established", t.lower())
                self.assertNotIn("order is fact", t.lower())
                self.assertIn("GBP-HW-270", t)
                self.assertRegex(t, r"not FACT|NOT FACT", "the history of Issue #26 kept on every page")

    def test_the_generic_pad_scope_accompanies_every_statement_of_the_order(self):
        for p in PAGES_STATING_THE_ORDER:
            with self.subTest(page=os.path.relpath(p, ROOT)):
                t = flat(read(p))
                hits = [m.start() for m in re.finditer(r"bit 8 = L|L/R bit order|L at bit 8 and R at bit 9|L at bit\s+8 and R at bit 9", t)]
                self.assertGreater(len(hits), 0)
                for h in hits:
                    window = t[h:h + 2200]
                    self.assertIn("generic", window, t[h:h + 120])
                    self.assertIn("third-party", window, t[h:h + 120])
                    self.assertRegex(window, r"not FACT|NOT FACT|not a physical FACT|FACT \(hw|F \(hw", t[h:h + 120])   # the status, stated (Issue #33: F (hw, run-scoped))

    def test_the_two_evidence_kinds_stay_apart_where_a_sentence_leans_on_them(self):
        f = flat(read(INPUT))
        self.assertIn("the frames are FACT as data and the Operator's report is OPERATOR OBSERVATION — they agree and are recorded apart", f)
        self.assertIn("in the Operator's report and, independently, in the preserved frames", f)


class TheConsolidatedInputPage(unittest.TestCase):
    def test_every_row_carries_an_existing_id_and_a_fact_or_corroborated_status(self):
        t = read(INPUT)
        R = rows(t)
        self.assertGreaterEqual(len(R), 16)
        defined = defined_ids()
        for cells in R:
            self.assertEqual(len(cells), 4, cells)
            self.assertRegex(cells[2], r"^(F|C)\b", "status must be F or C: " + " | ".join(cells))
            self.assertNotRegex(cells[2], r"\bH\b|\bU\b|HYPOTHESIS|UNKNOWN")
            ids = set(ID.findall(cells[3]))
            self.assertTrue(ids, "no id: " + " | ".join(cells))
            self.assertEqual(sorted(i for i in ids if i not in defined), [], cells[3])
        cited = set(ID.findall(t))
        self.assertEqual(sorted(i for i in cited if i not in defined), [])
        self.assertIn("U-GBP-010", cited)

    def test_the_page_states_its_boundaries_and_marks_the_mapping_as_policy(self):
        f = flat(read(INPUT))
        for tok in ("Nothing whose status is HYPOTHESIS or UNKNOWN is stated here as a property of the device",
                    "thinner than the video plane's", "a counting test ROM, not a game", "## 4. This project's controller mapping — POLICY, not a device fact",
                    "never a property of the GBS-DOL", "## 5. Not established — pointers only", "is **not assessed** by the two runs",
                    "whether the 5 ms refresh is needed or sufficient is not established", "observational, never a latency figure",
                    "GBP-KEY-009; recorded on 2026-09-21 as not implemented — implemented the same day in `stream-0015`", "`trigger_threshold=0`"):
            self.assertIn(tok, f, tok)
        policy_rows = [c for c in rows(read(INPUT)) if c[2].startswith("F (software; POLICY)")]
        self.assertEqual(len(policy_rows), 7)
        self.assertNotIn("Question M = PASS" + " for a game", f)


class NothingFrozenMovedAndNothingWasMinted(unittest.TestCase):
    def test_hardware_tests_v7_evidence_headings_and_u_gbp_010_are_the_bytes_of_the_base(self):
        old = git_show("docs/research/HARDWARE_TESTS.md")
        if old is None:
            self.skipTest("the base commit is not available in this checkout")
        new = read(HW)
        # Issue #28 appended §V7.3 and extended the chapter heading; §V7.1 and §V7.2 stay the bytes of the base
        old_head = old[old.index("\n## V7 "):].splitlines()[1]
        new_head = [l for l in new.splitlines() if l.startswith("## V7 ")][0]
        self.assertTrue(new_head.startswith(old_head), "the chapter heading grows, it does not change")
        self.assertEqual(new[new.index("### V7.1 "):new.index("### V7.3 ")].rstrip("\n"), old[old.index("### V7.1 "):].rstrip("\n"), "§V7.1 and §V7.2 untouched")
        ev_old, ev_new = git_show("docs/research/EVIDENCE.md"), read(EVIDENCE)
        heads = lambda t: [l for l in t.splitlines() if re.match(r"^#{2,4} +(GBP-KEY-00[1-9]|GBP-HW-26[1-5])\b", l)]
        # Issue #33 (2026-09-21) later extended GBP-KEY-004's heading (the routing FACT by RUN 17 / RUN 18) and minted GBP-HW-266…271;
        # this checkpoint changed no status: every heading of the base is a prefix of today's
        for a, b in zip(heads(ev_old), heads(ev_new)):
            self.assertTrue(b.startswith(a), (a, b))
        self.assertEqual(len(heads(ev_new)), len(heads(ev_old)))
        self.assertEqual(max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev_new, re.M)), 284, "266…271: #33; 272: #46; 273…277: #47; 278…284: #52, the four play-0001 sessions")
        u_old, u_new = git_show("docs/research/UNKNOWNS.md"), read(UNKNOWNS)
        h = lambda t: re.search(r"^## U-GBP-010\b.*$", t, re.M).group(0)
        self.assertTrue(h(u_new).startswith(h(u_old)))
        self.assertIn("Issue #26", u_new[u_new.index("## U-GBP-010"):u_new.index("## U-GBP-011")])

    def test_nothing_under_the_untouchable_paths_changed(self):
        if not guards.base_available(BASE):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE)
        changed = guards.changed_since(BASE, ["src", "poc", "tools", "Makefile", "stimulus", "captures/fixtures"])   # Issue #29: tracked AND untracked, one implementation
        # Issue #50 (2026-09-22) made §V7.6.11's frozen verdicts executable BEFORE RUN 21 / RUN 22's logs
        # existed: tools/v7611.py recomputes them and is exercised on SYNTHETIC vectors only, so the
        # ingestion cannot tune the constructions to the data. It reads no run and changes nothing.
        changed = changed - {"tools/v7611.py"}
        # Issue #29 (2026-09-21) added the promotion sweep tool; it reads the pages and judges nothing, and
        # Issue #44 (2026-09-22) hardened the staging tool against destroying a frozen slot: the manifest gained a frozen_sha256 column
        changed = changed - {"tools/reconcile.py", "tools/swiss_export.py", "tools/swiss-layout.tsv"}
        # Issue #27 (after this promotion) touched the input module and the stream probe; Issue #33 (2026-09-21) added the
        # RUN 16 / 17 / 18 fixtures (tests/host/test_run17.py pins them); nothing else here
        changed = changed
        allowed = {"src/gbp/gbp_input.c", "src/gbp/gbp_input.h", "poc/gbp-video-stream-probe/source/main.c", "poc/gbp-video-stream-probe/Makefile"}
        allowed |= {p for p in changed if re.search(r"^captures/fixtures/hw-gamecube-gbp-2026-09-21-(idxcap|stream-0015)-run1[678]-", p)}
        # Issue #39 (2026-09-21) built the playable image: the session end in the service-path module (tests/host/test_play_image.py pins it), a new POC, its audit profile and its Swiss slot
        allowed |= {"src/gbp/gbp_vstate_probe.c", "src/gbp/gbp_vstate_probe.h", "src/gbp/gbp_session.c", "src/gbp/gbp_session.h", "poc/gbp-play-session/Makefile", "poc/gbp-play-session/source/main.c", "tools/poc_audit.py", "tools/swiss-layout.tsv", "Makefile"}
        self.assertTrue(changed <= allowed, "changed against the base: " + " ".join(sorted(changed)))

    def test_the_records_of_the_checkpoint(self):
        d = read(DEVLOG)
        i = d.rindex("## 2026-09-21 — Issue #26")
        j = d.find("\n## 2026", i + 1)
        e = d[i:j if j > 0 else None]
        for tok in ("INPUT.md", "never written", "CORROBORATED, not FACT", "active-low", "POLICY", "no status", "GBP-KEY-009"):
            self.assertIn(tok, e, tok)
        self.assertNotRegex(e, r"GBP-HW-26[6-9]")
        h = flat(read(HANDOFF))
        self.assertIn("issue 26", h)
        self.assertNotIn("keeps Dolphin's order at H until", h)
        self.assertIn("Promoted 2026-09-21 (GitHub Issue #26)", flat(read(ROADMAP)))


if __name__ == "__main__":
    unittest.main()
