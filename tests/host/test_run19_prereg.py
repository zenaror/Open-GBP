"""
tests/host/test_run19_prereg.py — RUN 19 / RUN 20 pre-registration (HARDWARE_TESTS
§V7.3-style, §V7.5; GitHub Issue #34): GBP-INPUT-003, the Phase 5 acceptance
pair — a real game, both controllers, the same actions — frozen BEFORE hardware.

Pinned: the criterion is the Operator's sentence, quoted, read in his terms and
not reinterpreted; the run is a pair (RUN 19 the generic pad, RUN 20 the original
pad) with one literal action list (13 steps, 19 presses, every GBA key at least
once) and a per-step report; W / S are read from his reports, K (the machine
half) from the two KEY records with its definitions frozen, beside W / S and
never merged; failure is reachable and informative; stream-0015 serves, is
verified on disk, NOT rebuilt, and its ~40 s window is stated with a longer
session recorded as a build change; the cartridge and its status (three values)
are declared before each run, WarioWare ORIGINAL recommended with its reason and
Road Rage named with the caveat wherever it is cited, the Operator's sentence
recorded as a relayed intention with its ambiguity; the standing declarations
are cited; the ten names are reserved once in §V7.5 and once in the handoff,
absent on disk, none for run 21+; the recovery block is byte-identical to
§V7.1.7's; no result, no id, no executed date; Phase 5's closure is not decided;
§V7.1–§V7.4 are the bytes of 868d053 and the chapter heading only grew; nothing
under the untouchable paths moved. Nothing here runs a program.
"""
import glob
import os
import re
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
ROADMAP = os.path.join(ROOT, "docs", "ROADMAP.md")
DEVLOG = os.path.join(ROOT, "docs", "research", "DEVLOG.md")
DOL_SHA = "dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49"
BASE_COMMIT = "868d053"                   # origin/main before Issue #34
CRITERION = "ambos os controles funcionam e tem que apresentar o mesmo comportamento"
NAMES = ["captures/local/GBP-VIDEO-004_stream-0015-run%d%s" % (n, s)
         for n in (19, 20) for s in (".log", "-idxcap.bin", "-disp.bin", "-full.bin", "-vi.bin")]
LIST = [("START", 1), ("A", 2), ("DOWN", 2), ("UP", 1), ("A", 1), ("RIGHT", 3), ("LEFT", 2), ("B", 2), ("L", 1), ("R", 1), ("SELECT", 1), ("START", 2)]
_C = {}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def flat(s):
    return re.sub(r"\s+", " ", s)


def plain(s):
    return flat(s).replace("`", "").replace("**", "")


def git_show(path, commit=BASE_COMMIT):
    r = subprocess.run(["git", "-C", ROOT, "show", "%s:%s" % (commit, path)], capture_output=True, text=True)
    return None if r.returncode != 0 else r.stdout


def prereg():
    if "p" not in _C:
        t = read(HW)
        i = t.index("### V7.5 ")
        j = t.find("### V7.6 ", i)
        _C["p"] = t[i:] if j < 0 else t[i:j]
    return _C["p"]


def body():
    return "\n".join(prereg().splitlines()[1:])


def part(n, text=None):
    t = prereg() if text is None else text
    i = t.index("#### V7.5.%d " % n)
    j = t.find("#### V7.5.%d " % (n + 1), i)
    return t[i:] if j < 0 else t[i:j]


def v71_part(n, text):
    i = text.index("#### V7.1.%d " % n)
    j = text.find("#### V7.1.%d " % (n + 1), i)
    return text[i:] if j < 0 else text[i:j]


def block_after(p, heading):
    i = p.index(heading)
    j = p.index("```text", i)
    return p[j:p.index("```", j + 7) + 3]


class TheSectionExists(unittest.TestCase):
    def test_twelve_parts_in_order_and_the_heading_carries_the_status(self):
        t = prereg()
        pos = [t.index("#### V7.5.%d " % n) for n in range(1, 13)]
        self.assertEqual(pos, sorted(pos))
        self.assertNotIn("#### V7.5.13 ", t)
        head = t.splitlines()[0]
        for tok in ("RUN 19 / RUN 20", "GBP-INPUT-003", "the Phase 5 acceptance run", "PRE-REGISTERED 2026-09-21 (GitHub Issue #34)", "NOT RUN / NOT AUTHORISED HERE"):
            self.assertIn(tok, head, tok)
        full = read(HW)
        self.assertEqual((full.count("### V7.5 "), full.count("\n## V7 ")), (1, 1))
        self.assertLess(full.index("### V7.4 "), full.index("### V7.5 "))
        v7 = [l for l in full.splitlines() if l.startswith("## V7 ")][0]
        for tok in ("RUN 19 / RUN 20 PRE-REGISTERED (Issue #34, §V7.5)", "GBP-INPUT-003", "NOT RUN / NOT AUTHORISED HERE"):
            self.assertIn(tok, v7, tok)
        self.assertIn("whether Phase 5 then CLOSES is NOT decided here", plain(t.split("#### V7.5.1 ")[0]))


class TheCriterionIsHisAndTheRunIsAPair(unittest.TestCase):
    def test_the_criterion_is_quoted_read_in_his_terms_and_not_reinterpreted(self):
        p = plain(part(1))
        for tok in (CRITERION, "tanto o paralelo como original", "not to be reinterpreted after the run", "not restated into something easier to gate",
                    "the run is a PAIR", "a machine half", "never replaces it and never decides the criterion by itself",
                    "this run serves acceptance and never the join", "§V7.4's FACTs stand where they stand"):
            self.assertIn(tok, p, tok)
        self.assertEqual(prereg().count(CRITERION), 2, "quoted in the criterion part and read in the verdicts, nowhere else")

    def test_the_numbering_the_experiment_and_the_instruments(self):
        p = plain(part(2))
        for tok in ("RUN 19 (the generic third-party pad) and RUN 20 (the original Nintendo pad), in that order", "the next two numbers above every reserved one",
                    "GBP-INPUT-003", "W \"funcionam\"", "S \"o mesmo comportamento\"", "K the machine half",
                    "WarioWare ORIGINAL cartridge, in two regional versions (Japanese, American) -- the Orchestrator's RECOMMENDATION",
                    "an original removes it", "Road Rage The Simpsons: Road Rage, declared by the Operator as a \"paralelo\" -- an UNOFFICIAL cartridge (a repro)",
                    "na RUN estou usando ez-flash e o road rage paralelo apenas", "a RELAYED INTENTION, with its ambiguity stated",
                    "the relay's confidence is not the record's", "THE STATUS AXIS HAS AT LEAST THREE VALUES", "a ROM DELIVERED BY THE FLASHCART",
                    "before RUN 19, and again before RUN 20", "does not choose for him beyond the recommendation",
                    "comparing them is NOT part of this run", "No counting, no timing, no pacing"):
            self.assertIn(tok, p, tok)
        # wherever Road Rage is cited, its unofficial status travels with it
        t = plain(prereg())
        for m in re.finditer(r"Road Rage", t):
            window = t[max(0, m.start() - 400):m.end() + 400]
            self.assertRegex(window, r"UNOFFICIAL|unofficial|repro|paralelo", t[m.start():m.end() + 80])

    def test_the_image_serves_with_its_window_stated_and_a_longer_session_recorded_not_proposed(self):
        p = part(3)
        self.assertIn(DOL_SHA, p)
        self.assertIn("514 880 B", p)
        f = plain(p)
        for tok in ("OPENGBP-IDENT gbp-video-stream-probe stream-0015 da06500", "NOT rebuilt", "why it serves", "it carries the KEY record",
                    "the image whose routing is FACT for all ten word bits on BOTH pads", "no staging, no rebuild",
                    "THE GAME IS CONTROLLABLE FOR ROUGHLY 40 SECONDS FROM ITS OWN BOOT", "+40.340 s", "+0.11 s after CONTROL",
                    "A longer session needs a build change (time_target / witness_target) -- RECORDED, NOT PROPOSED, not authorised here",
                    "NO analyzer decodes a game's frames and NO analyzer computes the machine half", "the definitions are frozen HERE so the ingestion cannot tune them",
                    "DO NOT RUN"):
            self.assertIn(tok, f, tok)

    def test_the_topology_cites_the_standing_declarations_and_declares_the_rest(self):
        f = plain(part(4))
        for tok in ("DECLARED HARDWARE INVENTORY", "CITED, not asked again", "STANDING DECLARATION (2026-09-21, Issue #35",
                    "ate que seja solicitado para remover ou conectar o cabo", "ate que eu anuncie o contrario", "INCONCLUSIVE on that item (V7.1.4)",
                    "DECLARED BEFORE RUN 19 and the SAME for RUN 20", "an ORIGINAL cartridge, an UNOFFICIAL cartridge (\"paralelo\" / repro), or a ROM run from the EZ-Flash",
                    "A change of cartridge between the two runs makes the pair INCONCLUSIVE for S", "THE VARIABLE of this pair",
                    "RUN 19 = the GENERIC third-party GameCube controller", "RUN 20 = the ORIGINAL Nintendo GameCube controller", "declared per run, never assumed",
                    "trigger_threshold=0", "X or Y as SELECT, Z never sent"):
            self.assertIn(tok, f, tok)


class TheNamesTheGateAndTheProcedure(unittest.TestCase):
    def test_the_ten_names_once_in_the_part_once_in_the_handoff_none_on_disk_none_beyond(self):
        p, t, h = prereg(), read(HW), read(HANDOFF)
        for n in NAMES:
            self.assertEqual(p.count(n), 1, n)
            self.assertEqual(t.count(n), 1, n)
            self.assertEqual(h.count(n), 1, n)
            self.assertFalse(os.path.exists(os.path.join(ROOT, n)), n)
        self.assertEqual(len(re.findall(r"captures/local/\S*run19\S*", t)), 5)
        self.assertEqual(len(re.findall(r"captures/local/\S*run20\S*", t)), 5)
        self.assertEqual(len(re.findall(r"captures/local/\S*run(?:2[1-9]|[3-9]\d)\S*", t)), 0)
        self.assertEqual(glob.glob(os.path.join(ROOT, "captures", "local", "*stream-0015-run19*")) + glob.glob(os.path.join(ROOT, "captures", "local", "*stream-0015-run20*")), [])
        f = plain(part(5))
        for tok in ("TAKEN even if a run aborts, never starts, or RUN 20 is never executed", "Verified absent on 2026-09-21", "never a sixth file"):
            self.assertIn(tok, f, tok)

    def test_the_identity_gate(self):
        g = plain(part(6))
        for tok in ("/media/rafael/SD_GC/Open-GBP/12-stream/boot.dol", DOL_SHA, "514 880 B", "re-verified before EACH boot", "MOVED ASIDE, never deleted",
                    "the same cartridge in RUN 20", "If ANY identity differs: DO NOT RUN"):
            self.assertIn(tok, g, tok)

    def test_the_action_list_is_literal_covers_every_key_and_fits_the_window(self):
        p = part(7)
        self.assertIn("13 steps, 19 presses", p)
        self.assertEqual(sum(n for _, n in LIST), 19)
        self.assertEqual({k for k, _ in LIST}, {"A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "L", "R"}, "every one of the ten GBA keys")
        table = block_after(p, "**The action list")
        for n in range(1, 14):
            self.assertIsNotNone(re.search(r"^\s*%d\s{2,}" % n, table, re.M), "step %d" % n)
        self.assertIsNone(re.search(r"^\s*14\s{2,}", table, re.M))
        f = plain(p)
        for tok in ("game-agnostic at the level of the GBA keys", "It is about the PADS, which is what the criterion is about", "not a script to time and not \"play for a while\"",
                    "the D-pad, not the stick", "RESPONDED (and what) / NO RESPONSE / OTHER / N/A", "The list is performed as written even where a step is N/A",
                    "the pair is compared on the common prefix", "byte-identical to V7.1.7's", "a difference is a result (V7.5.9)"):
            self.assertIn(tok, f, tok)
        self.assertEqual(p.count("START x1, then START x1 again"), 1)
        # the expected press sequence of the record table is the list, in order
        seq = [k for k, n in LIST for _ in range(n)]
        self.assertIn("expected press sequence (the list)      " + ", ".join(seq), part(11))

    def test_two_checklists_and_the_recovery_block_byte_identical_to_v7_1(self):
        p = part(7)
        self.assertEqual(len(p.split("```text")), 5)           # the recovery block, the list, the two checklists
        run19 = block_after(p, "**RUN 19 — the action list on the GENERIC")
        run20 = block_after(p, "**RUN 20 — the SAME action list on the ORIGINAL")
        for n in range(1, 12):
            self.assertIsNotNone(re.search(r"^\s*%d  " % n, run19, re.M), "run19 step %d" % n)
        self.assertIsNone(re.search(r"^\s*12  ", run19, re.M))
        for n in range(1, 9):
            self.assertIsNotNone(re.search(r"^\s*%d  " % n, run20, re.M), "run20 step %d" % n)
        self.assertIsNone(re.search(r"^\s*9  ", run20, re.M))
        f = plain(p)
        for tok in ("Declare the cartridge: the title, its FORM (original / unofficial / a ROM on the EZ-Flash)", "dd545c01...3a49",
                    "those presses are in the KEY record and are not part of the list", "reserved run19 names", "reserved run20 names",
                    "the SAME cartridge, in the same form, booting the same way (declare it again)", "note the last step reached"):
            self.assertIn(tok, f, tok)
        self.assertIn("Do not infer a frame number, a latency or a timing from anything seen by eye", f)
        t = read(HW)
        v71 = t[t.index("### V7.1 "):t.index("### V7.2 ")]
        self.assertEqual(block_after(p, "**Recovery procedure"), block_after(v71_part(7, v71), "**Recovery procedure"))


class GatesVerdictsAndNonClaims(unittest.TestCase):
    def test_no_result_no_new_id_no_executed_run(self):
        p = body()
        self.assertNotRegex(p, r"GBP-HW-27[2-9]|GBP-HW-2[8-9]\d|GBP-HW-[3-9]\d\d")
        self.assertNotIn("RESULT", p)
        self.assertNotRegex(p, r"EXECUTED 2026|ingested 2026|ingested on")
        self.assertIn("Nothing here is evidence", p)
        self.assertIn("no evidence ID\nis allocated", p)
        self.assertIn("PRE-REGISTERED / NOT RUN", part(12))

    def test_the_shared_gates_add_the_list_and_the_pairs_own(self):
        f = plain(part(8))
        for tok in ("KEY RECORD as §V7.3.8", "INCONCLUSIVE for K (the machine half) and its W / S readings stand on the Operator's report alone",
                    "the CONTENT IS A GAME: no tally, nothing decoded, no claim read from the pixels", "a cartridge change between the runs is INCONCLUSIVE for S",
                    "THE LIST performed as V7.5.7 lists it", "the KEY record's press sequence is the machine's witness that the list was followed",
                    "a run ended by the recovery power-off is INCONCLUSIVE for that run"):
            self.assertIn(tok, f, tok)

    def test_the_verdicts_answer_his_sentence_with_failure_reachable_and_the_machine_half_beside(self):
        p = part(9)
        for label in ("WORKS         ", "DOES NOT WORK ", "SAME          ", "DIFFERENT     ", "AGREE         ", "EXPLAINED     ", "FINDING       ", "INCONCLUSIVE  "):
            self.assertEqual(len(re.findall(r"^%s" % re.escape(label), p, re.M)), 1, label)
        f = plain(p)
        for tok in ("K never decides W or S", "QUESTION W -- \"funcionam\"", "QUESTION S -- \"o mesmo comportamento\"",
                    "THE CRITERION \"%s\" holds when W = WORKS on BOTH pads AND S = SAME" % CRITERION,
                    "Any other combination is stated exactly as it fell (which pad, which step, which key) and is an informative result",
                    "Whether Phase 5 CLOSES on it is NOT decided here", "never a failed run",
                    "the ordered list of rising edges of the word bits across the completed KEY lines (rc=ok, n order, from 0000",
                    "cut off at the first rising edge of START", "Compared over the steps both runs reached",
                    "it is exactly the difference the criterion's machine half exists to show", "read beside S, not instead of it",
                    "what K cannot conclude what the game received or did", "the routing (§V7.4's FACTs stand and are not the subject)",
                    "the live description is quoted, never paraphrased into a verdict", "reports every intermediate quantity"):
            self.assertIn(tok, f, tok)
        self.assertEqual(f.count("DOES NOT WORK"), 1)
        self.assertEqual(f.count("DIFFERENT"), 1, "the label once; the reading rules name no verdict")

    def test_phase_5s_closure_is_not_decided_and_the_record_is_empty(self):
        f = plain(part(10))
        for tok in ("What it does NOT decide: whether Phase 5 closes", "Issue #17, PHASE4_ASSESSMENT.md", "after the run, never anticipated by the pre-registration",
                    "the routing (FACT, §V7.4, not the subject)", "GB / GBC (Phase 7, Issue #31)"):
            self.assertIn(tok, f, tok)
        p = part(11)
        rows = [l for l in p.splitlines() if re.match(r"^[A-Za-z].*\s{2,}--", l)]
        self.assertGreaterEqual(len(rows), 18)
        for l in rows:
            self.assertRegex(l, r"--(\s+--)*(\s+\(.*\))?\s*$", l)
        self.assertIn("beyond the ~40 s window and the 13 steps", plain(p))


class NothingElseMoved(unittest.TestCase):
    def test_v7_1_to_v7_4_are_the_bytes_of_the_base_and_the_heading_only_grew(self):
        old = git_show("docs/research/HARDWARE_TESTS.md")
        if old is None:
            self.skipTest("the base commit is not available in this checkout")
        new = read(HW)
        self.assertEqual(new[new.index("### V7.1 "):new.index("### V7.5 ")].rstrip("\n"), old[old.index("### V7.1 "):].rstrip("\n"))
        old_head = [l for l in old.splitlines() if l.startswith("## V7 ")][0]
        new_head = [l for l in new.splitlines() if l.startswith("## V7 ")][0]
        self.assertTrue(new_head.startswith(old_head))
        self.assertEqual(old[:old.index("\n## V7 ")], new[:new.index("\n## V7 ")], "everything before the chapter untouched")

    def test_the_records(self):
        h = plain(read(HANDOFF))
        for tok in ("RUN 19 and RUN 20 (GBP-INPUT-003", "issue 34", "validate #34", "That RUN 19 / RUN 20 have run, or that Phase 5 is closed",
                    "Its run IS pre-registered (Issue #34", "Phase 5's closure NOT decided by it"):
            self.assertIn(tok, h, tok)
        r = plain(read(ROADMAP))
        for tok in ("Pre-registered 2026-09-21 (GitHub Issue #34)", CRITERION, "NOT RUN / NOT AUTHORISED HERE", "Whether this phase then closes is an assessment step of its own"):
            self.assertIn(tok, r, tok)
        d = read(DEVLOG)
        i = d.rindex("## 2026-09-21 — Issue #34")
        e = plain(d[i:])
        for tok in ("the criterion in the Operator's words", "a relayed intention with its ambiguity stated", "Phase 5's closure is an assessment step of its own",
                    "No hardware; no staging; no build; no code"):
            self.assertIn(tok, e, tok)
        self.assertNotRegex(e, r"GBP-HW-27[2-9]")

    def test_nothing_under_the_untouchable_paths_changed_against_the_base(self):
        r = subprocess.run(["git", "-C", ROOT, "cat-file", "-e", BASE_COMMIT], capture_output=True)
        if r.returncode != 0:
            self.skipTest("the base commit is not available in this checkout")
        r = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", BASE_COMMIT, "--", "src", "poc", "tools", "Makefile", "stimulus", "captures/fixtures",
                            "docs/protocol", "docs/hardware", "docs/research/EVIDENCE.md", "docs/research/UNKNOWNS.md"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "", "changed against the base: " + r.stdout)
        r = subprocess.run(["git", "-C", ROOT, "ls-files", "--others", "--exclude-standard", "--", "src", "poc", "tools", "stimulus", "captures/fixtures", "docs/protocol", "docs/hardware"],
                           capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "", "untracked files under the guarded paths: " + r.stdout)


if __name__ == "__main__":
    unittest.main()
