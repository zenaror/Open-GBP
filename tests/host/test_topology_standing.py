"""
tests/host/test_topology_standing.py — GitHub Issue #35 (2026-09-21): the topology
the Operator declared for RUN 16 / 17 / 18 after their ingestion, and the two
STANDING declarations.

Pinned: §V7.4.2 carries BBA PRESENT / Ethernet DISCONNECTED and the display chain
UNCHANGED as OPERATOR DECLARATIONS with his literal words, and KEEPS the history
(recorded as absent at ingestion, not inferred; declared afterwards, by this
route, under this Issue); the two standing declarations are recorded with their
stated duration, cited by future pre-registrations, never a licence to infer,
with the INCONCLUSIVE-on-that-item rule beside them; the per-run list reduces to
the cartridge / boot screen and the controller; §V7.4.4's TOPOLOGY reads PASS
with the history; the three struct fixtures' topology block carries the same
and nothing else in them moved; GBP-HW-266 has the dated addendum and no id was
minted; HANDOFF's "Do not rediscover" row and a do-not-assume bullet carry the
standing part; §V7.1–§V7.3 and §V7.4's results are the bytes of aaee492;
nothing under the forbidden paths moved.
"""
import json
import os
import re
import subprocess
import unittest

import guards

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FX = os.path.join(ROOT, "captures", "fixtures")
P = "hw-gamecube-gbp-2026-09-21-"
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
DEVLOG = os.path.join(ROOT, "docs", "research", "DEVLOG.md")
README = os.path.join(ROOT, "captures", "README.md")
BASE_COMMIT = "aaee492"     # origin/main before Issue #35
W_BBA = "BBA como sempre (presente mas nao conectado no cabo)"
W_CHAIN = "video inalterado e ira permanecer assim ate que eu anuncie o contrario"
W_BBA_STANDING = "BBA também permanecera presente e sem cabo, ate que seja solicitado para remover ou conectar o cabo"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "")


def git_show(path, commit=BASE_COMMIT):
    r = subprocess.run(["git", "-C", ROOT, "show", "%s:%s" % (commit, path)], capture_output=True, text=True)
    return None if r.returncode != 0 else r.stdout


def v74(text=None):
    t = read(HW) if text is None else text
    i = t.index("### V7.4 ")
    j = t.find("### V7.5 ", i)
    return t[i:] if j < 0 else t[i:j]


def part(n, text=None):
    t = v74(text)
    i = t.index("#### V7.4.%d " % n)
    j = t.find("#### V7.4.%d " % (n + 1), i)
    return t[i:] if j < 0 else t[i:j]


def struct(run):
    with open(os.path.join(FX, P + "idxcap-run%d-struct.json" % run), encoding="utf-8") as f:
        return json.load(f)


class TheDeclarationIsRecordedWithItsHistory(unittest.TestCase):
    def test_v7_4_2_carries_the_declared_items_the_words_and_the_history(self):
        p = plain(part(2))
        for tok in ("BBA / ETHERNET PRESENT / DISCONNECTED -- his words: \"%s\"" % W_BBA, "DISPLAY CHAIN UNCHANGED", "his words: \"video inalterado\"",
                    "OPERATOR DECLARATION, given AFTER the ingestion and relayed by the Orchestrator (Issue #35, 2026-09-21)",
                    "THE HISTORY, KEPT: at ingestion (Issue #33) no per-run declaration of these two items existed",
                    "RECORDED AS ABSENT, NOT INFERRED", "the declaration above replaced that note under Issue #35",
                    "TOPOLOGY only; nothing about the display is claimed; the join reads the FRAMES, not the screen"):
            self.assertIn(tok, p, tok)
        self.assertIn("what was not declared at ingestion, and the declaration that followed (Issue #35)", part(2).splitlines()[0])
        self.assertEqual(part(2).count("DECLARED\n"), 2, "the two items are marked DECLARED, in the style of §V7.2.2")

    def test_the_standing_declarations_have_their_words_their_duration_and_their_limits(self):
        p = plain(part(2))
        for tok in ("STANDING Two of these are STANDING declarations -- operator declarations WITH A STATED DURATION, in his words: DECLARATIONS display chain",
                    "display chain \"%s\"" % W_CHAIN, "BBA \"%s\"" % W_BBA_STANDING,
                    "They hold until he announces a change, like the hardware inventory (Issue #25)",
                    "a future pre-registration CITES them instead of asking", "NOT a licence to infer", "do NOT make the topology \"known\"",
                    "stays DECLARED, by him, until he says otherwise", "that run is INCONCLUSIVE on that item exactly as V7.1.4 says",
                    "What still MUST be declared per run: the cartridge and its boot screen, and the controller",
                    "has used both (RUN 14 / 15 / 17 the generic, RUN 16 / 18 the original), so it is never assumed"):
            self.assertIn(tok, p, tok)

    def test_the_topology_gate_reads_pass_with_the_history_and_the_record_row_follows(self):
        g = plain(part(4))
        for tok in ("TOPOLOGY PASS for the items declared", "BBA PRESENT / Ethernet DISCONNECTED and the display chain UNCHANGED, declared by the Operator after the ingestion (Issue #35",
                    "HISTORY: at ingestion these two were NOT DECLARED, the line read PASS* and they were recorded as absent, not inferred",
                    "The gate text is unchanged; the reading is stated here"):
            self.assertIn(tok, g, tok)
        self.assertNotIn("TOPOLOGY PASS* for", g)
        r = plain(part(10))
        self.assertIn("BBA / Ethernet / chain (declared) BBA PRESENT, no Ethernet cable; display chain UNCHANGED -- declared after the ingestion (Issue #35; STANDING, V7.4.2); at ingestion NOT DECLARED, recorded as absent, not inferred", r)
        intro = plain(v74().split("#### V7.4.1 ")[0])
        self.assertIn("were NOT declared for these runs at ingestion and were recorded as absent -- the Operator declared them afterwards, the same day, and the declaration replaced that note under Issue #35 with the history kept", intro.replace("—", "--"))
        self.assertIn("the display chain (declared unchanged under Issue #35; not part of the join)", plain(part(12)))

    def test_the_fixtures_carry_the_declaration_and_nothing_else_in_them_moved(self):
        for run in (16, 17, 18):
            with self.subTest(run=run):
                s = struct(run)
                tp = s["topology_declared_by_operator"]
                self.assertTrue(tp["bba_ethernet"].startswith("PRESENT / DISCONNECTED -- DECLARED by the Operator after the ingestion (Issue #35, 2026-09-21)"))
                self.assertIn(W_BBA, tp["bba_ethernet"])
                self.assertTrue(tp["display_chain"].startswith("UNCHANGED -- the chain of §V7.1.4 / §V6.24.3"))
                self.assertIn("DECLARED by the Operator after the ingestion (Issue #35", tp["display_chain"])
                sd = tp["standing_declarations"]
                self.assertEqual((sd["display_chain"]["words"], sd["bba"]["words"]), (W_CHAIN, W_BBA_STANDING))
                for tok in ("WITH A STATED DURATION", "never a licence to infer", "INCONCLUSIVE on that item", "CITE these instead of asking"):
                    self.assertIn(tok, sd["what"], tok)
                self.assertIn("the cartridge and its boot screen; the controller", sd["what_still_varies_per_run"])
                self.assertIn("RECORDED AS ABSENT, NOT INFERRED", tp["declaration_history"])
                self.assertIn("replaced that note under Issue #35", tp["declaration_history"])
                self.assertIn("HISTORY: at ingestion these two were NOT DECLARED", s["verdicts"]["shared_gates"]["TOPOLOGY"])
                self.assertIn("regenerated_for_issue_35", s["tools"])
                old = git_show("captures/fixtures/" + P + "idxcap-run%d-struct.json" % run)
                if old is None:
                    self.skipTest("the base commit is not available in this checkout")
                o = json.loads(old)
                for k in ("bba_ethernet", "display_chain"):
                    self.assertTrue(o["topology_declared_by_operator"][k].startswith("NOT DECLARED"), "the base recorded the item as absent")
                o["topology_declared_by_operator"] = s["topology_declared_by_operator"]
                o["verdicts"]["shared_gates"]["TOPOLOGY"] = s["verdicts"]["shared_gates"]["TOPOLOGY"]
                o["tools"]["regenerated_for_issue_35"] = s["tools"]["regenerated_for_issue_35"]
                self.assertEqual(o, s, "every other section of the struct fixture is unchanged (the join, the verdicts, the records)")
        # the RUN 14 / RUN 15 records are history and untouched
        for run in (14, 15):
            self.assertIn("what still varies and must be declared per run: BBA and Ethernet state, the display chain, the cartridge and its boot screen, the controller",
                          struct(run)["topology_declared_by_operator"]["standing_note_for_future_pre_registrations"])


class TheRecordsAndTheFreeze(unittest.TestCase):
    def test_the_evidence_row_has_the_dated_addendum_and_no_id_was_minted(self):
        ev = read(EVIDENCE)
        b266 = ev[ev.index("### GBP-HW-266 "):ev.index("### GBP-HW-267 ")]
        self.assertIn("recorded as ABSENT,\nnot inferred", b266, "the history kept")
        self.assertIn("**2026-09-21, Issue #35 (declared after the ingestion; the note above kept as\nhistory):**", b266)
        for tok in (W_BBA, W_CHAIN, W_BBA_STANDING, "WITH A STATED DURATION", "NOT a licence to infer", "INCONCLUSIVE on that item", "no new id"):
            self.assertIn(tok, plain(b266), tok)
        self.assertEqual(max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 277)   # 272: Issue #46 (the CONTROL bit 0x02 split, FACT for the split / HYPOTHESIS for the cause)

    def test_the_handoff_carries_the_standing_declarations_where_a_pre_registration_will_meet_them(self):
        h = read(HANDOFF)
        row = [l for l in h.splitlines() if l.startswith("| **The console and the Game Boy Player are the same two units in every run of this project**")]
        self.assertEqual(len(row), 1)
        r = row[0]
        for tok in ("Two STANDING declarations (2026-09-21, Issue #35", W_CHAIN, W_BBA_STANDING, "WITH A STATED DURATION", "never a licence to infer",
                    "do not make the topology \"known\"", "INCONCLUSIVE on that item (§V7.1.4)",
                    "What still varies and MUST be declared per run: the cartridge and its boot screen, and the controller", "so it is never assumed",
                    "GBP-HW-261, GBP-HW-266", "§V7.2.2, §V7.4.2"):
            self.assertIn(tok, r, tok)
        self.assertNotIn("MUST be declared per run: BBA and Ethernet state", r)
        p = plain(h)
        for tok in ("- That the topology is known. It is DECLARED", "issue 35",   # the trail's `next` moved on with Issue #34
                    "at ingestion recorded absent, not inferred; history kept"):
            self.assertIn(tok, p, tok)
        self.assertIn("Issue #35", plain(read(README)))
        d = read(DEVLOG)
        # Issue #46 (2026-09-22): bounded to the Issue #35 entry. It ran to END OF FILE, so the sentinel below
        # fired on GBP-HW-272, minted by a later checkpoint and named in a later entry.
        e = d[d.rindex("## 2026-09-21 — Issue #35"):]
        e = e[:e.index("\n## ", 1)] if "\n## " in e[1:] else e
        for tok in (W_CHAIN, "WITH A STATED DURATION", "never a licence to infer", "No hardware; no code", "Issue #34 (the acceptance run) not started"):
            self.assertIn(tok, plain(e), tok)
        self.assertNotRegex(e, r"GBP-HW-27[2-9]")

    def test_v7_1_to_v7_3_and_v7_4s_results_are_the_bytes_of_the_base(self):
        old = git_show("docs/research/HARDWARE_TESTS.md")
        if old is None:
            self.skipTest("the base commit is not available in this checkout")
        new = read(HW)
        self.assertEqual(new[new.index("### V7.1 "):new.index("### V7.4 ")], old[old.index("### V7.1 "):old.index("### V7.4 ")])
        self.assertEqual(old[:old.index("\n## V7 ")], new[:new.index("\n## V7 ")])
        old_head = [l for l in old.splitlines() if l.startswith("## V7 ")][0]
        new_head = [l for l in new.splitlines() if l.startswith("## V7 ")][0]
        self.assertTrue(new_head.startswith(old_head), "the chapter heading only grows (Issue #34 appended the RUN 19 / RUN 20 clause)")
        # the results: every part of §V7.4 except the ones the Issue names (the intro, 2, 4, 10, 11, 12) is byte-identical
        for n in (1, 3, 5, 6, 7, 8, 9):
            self.assertEqual(part(n, new), part(n, old), "V7.4.%d untouched" % n)
        self.assertEqual(part(11, new).replace("declared under Issue #35 with that history", "").count("recorded as absent"), 1)

    def test_nothing_under_the_forbidden_paths_changed(self):
        if not guards.base_available(BASE_COMMIT):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE_COMMIT)
        changed = guards.changed_since(BASE_COMMIT, ["src", "poc", "tools", "Makefile", "stimulus", "docs/protocol", "docs/hardware"])   # Issue #29: tracked AND untracked, one implementation
        # Issue #29 (2026-09-21) added the promotion sweep tool; it reads the pages and judges nothing, and
        # Issue #44 (2026-09-22) hardened the staging tool against destroying a frozen slot: the manifest gained a frozen_sha256 column
        changed = changed - {"tools/reconcile.py", "tools/swiss_export.py", "tools/swiss-layout.tsv"}
        # Issue #46 (2026-09-22): the REGISTERS.md row for CONTROL bit 0x02 now separates the references' USAGE (C)
        # from this project's own measurement (F) from the causal reading (H), citing GBP-HW-272
        changed = changed - {"docs/protocol/REGISTERS.md"}
        # Issue #39 (2026-09-21) built the playable image: the session end in the service-path module (tests/host/test_play_image.py pins it), a new POC, its audit profile and its Swiss slot
        self.assertTrue(changed <= {"src/gbp/gbp_vstate_probe.c", "src/gbp/gbp_vstate_probe.h", "src/gbp/gbp_session.c", "src/gbp/gbp_session.h", "poc/gbp-play-session/Makefile", "poc/gbp-play-session/source/main.c", "tools/poc_audit.py", "tools/swiss-layout.tsv", "Makefile"}, "changed against the base: " + " ".join(sorted(changed)))
        changed2 = guards.changed_since(BASE_COMMIT, ["captures/fixtures"])   # Issue #29: tracked AND untracked, one implementation
        self.assertTrue(changed2 <= {"captures/fixtures/" + P + "idxcap-run%d-struct.json" % n for n in (16, 17, 18)}, " ".join(sorted(changed2)))
        # the guard's blind spot (Issue #29): untracked files are invisible to git diff -- none may exist under these paths


if __name__ == "__main__":
    unittest.main()
