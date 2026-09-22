"""
tests/host/test_input_addenda.py — GitHub Issue #22 (2026-09-21): two Operator
inputs recorded after the RUN 14 / RUN 15 pre-registration, outside the frozen
§V7.

Pinned: HARDWARE_TESTS.md's `## V7` chapter is byte-identical to the commit that
froze it (848007a); the input module and its descriptor are unchanged since the
same commit; INPUT_PATH.md §10 records the rejected instrument with its reasons,
the Start-up Disc recollection with its classification, and the composition
with its two conditions and its weakness; EVIDENCE GBP-KEY-007 exists once as
OPERATOR OBSERVATION (recollection) and GBP-KEY-004's heading is unchanged;
REGISTERS.md kept H at that checkpoint; nothing under src/, poc/, tools/,
Makefile, docs/protocol or docs/hardware moved. Issue #24 (2026-09-21) then ingested RUN 14 / RUN 15
(§V7.2): U-GBP-010 is CLOSED, GBP-HW-261…265 and GBP-KEY-008 / 009 exist, and
the RUN 14 / RUN 15 fixtures were added -- the pins below say so.
"""
import os
import re
import subprocess
import unittest

import guards

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
INPUT_PATH = os.path.join(ROOT, "docs", "research", "INPUT_PATH.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
DEVLOG = os.path.join(ROOT, "docs", "research", "DEVLOG.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
REGISTERS = os.path.join(ROOT, "docs", "protocol", "REGISTERS.md")
FROZEN_COMMIT = "848007abfd1b7d2e21a6ef7582062e0ee9539d5a"   # Issue #20: §V7 pre-registered, then frozen by the Orchestrator


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def flat(s):
    return re.sub(r"\s+", " ", s)


def plain(s):
    return flat(s).replace("`", "").replace("**", "")


def git_show(path):
    r = subprocess.run(["git", "-C", ROOT, "show", "%s:%s" % (FROZEN_COMMIT, path)], capture_output=True, text=True)
    return None if r.returncode != 0 else r.stdout


def section10():
    t = read(INPUT_PATH)
    return t[t.index("## 10. Addenda after the pre-registration"):]


class TheFrozenThingsAreUntouched(unittest.TestCase):
    def test_the_parts_of_v7_issue_22_promised_not_to_touch_are_byte_identical(self):
        """Issue #22 touched nothing in §V7. Issue #23 later amended RUN 15 and added
        RUN 16 before hardware, so the whole-chapter comparison moved to
        test_run14_prereg.py; what stays pinned here is that Question One, the
        shared gates and the U-GBP-010 part are the frozen bytes."""
        old = git_show("docs/research/HARDWARE_TESTS.md")
        if old is None:
            self.skipTest("the frozen commit is not available in this checkout")
        now = read(HW)
        self.assertEqual(now.count("\n## V7 "), 1)
        def part(t, n):
            i = t.index("#### V7.1.%d " % n)
            j = t.find("#### V7.1.%d " % (n + 1), i)
            return t[i:] if j < 0 else t[i:j]
        for n in (1, 8, 10):
            self.assertEqual(part(now, n), part(old, n), n)

    def test_the_descriptor_and_the_policy_are_unchanged(self):
        """Issue #22 changed no code. Issue #27 (2026-09-21) later added the per-change
        record to the module; the descriptor and the policy stay the frozen bytes."""
        old = git_show("src/gbp/gbp_input.c")
        if old is None:
            self.skipTest("the frozen commit is not available in this checkout")
        def initializers(src):
            src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
            d = re.search(r"GBP_KEYPAD_DESCRIPTOR\s*=\s*\{\s*\{([^}]*)\}\s*,\s*(\d+)\s*\}", src)
            p = re.search(r"GBP_INPUT_POLICY_DEFAULT\s*=\s*\{(.*?)\};", src, re.S)
            return (re.sub(r"\s+", "", d.group(1)), d.group(2), re.sub(r"\s+", "", p.group(1)))
        self.assertEqual(initializers(read(os.path.join(ROOT, "src", "gbp", "gbp_input.c"))), initializers(old))
        self.assertIn("{ 0, 1, 2, 3, 4, 5, 6, 7, /* R -> bit */ 9, /* L -> bit */ 8 }, 1", read(os.path.join(ROOT, "src", "gbp", "gbp_input.c")))

    def test_nothing_under_the_untouchable_paths_changed(self):
        if not guards.base_available(FROZEN_COMMIT):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % FROZEN_COMMIT)
        # docs/protocol and docs/hardware left this guard with Issue #26 (the promotion); Issue #27 (the per-change
        # record and the ENVINPUT repair) touched the input module and the stream probe, and nothing else
        changed = guards.changed_since(FROZEN_COMMIT, ["src", "poc", "tools", "Makefile", "stimulus"])   # Issue #29: tracked AND untracked, one implementation
        # Issue #50 (2026-09-22) made §V7.6.11's frozen verdicts executable BEFORE RUN 21 / RUN 22's logs
        # existed: tools/v7611.py recomputes them and is exercised on SYNTHETIC vectors only, so the
        # ingestion cannot tune the constructions to the data. It reads no run and changes nothing.
        changed = changed - {"tools/v7611.py"}
        # Issue #58 (2026-09-22) pre-registered Phase 6's first physical run (§V8, GBP-AUDIO-001) and made its
        # three-model predictions executable BEFORE any build or log existed: tools/v8audio.py is exercised on
        # SYNTHETIC vectors only, reads no run, authorises nothing and promotes nothing.
        changed = changed - {"tools/v8audio.py"}
        # Issue #29 (2026-09-21) added the promotion sweep tool; it reads the pages and judges nothing, and
        # Issue #44 (2026-09-22) hardened the staging tool against destroying a frozen slot: the manifest gained a frozen_sha256 column
        changed = changed - {"tools/reconcile.py", "tools/swiss_export.py", "tools/swiss-layout.tsv"}
        allowed = {"src/gbp/gbp_input.c", "src/gbp/gbp_input.h", "poc/gbp-video-stream-probe/source/main.c", "poc/gbp-video-stream-probe/Makefile"}
        # Issue #39 (2026-09-21) built the playable image: the session end in the service-path module (tests/host/test_play_image.py pins it), a new POC, its audit profile and its Swiss slot
        allowed |= {"src/gbp/gbp_vstate_probe.c", "src/gbp/gbp_vstate_probe.h", "src/gbp/gbp_session.c", "src/gbp/gbp_session.h", "poc/gbp-play-session/Makefile", "poc/gbp-play-session/source/main.c", "tools/poc_audit.py", "tools/swiss-layout.tsv", "Makefile"}
        self.assertTrue(changed <= allowed, "changed against the frozen commit: " + " ".join(sorted(changed)))
        changed2 = guards.changed_since(FROZEN_COMMIT, ["captures/fixtures"])   # Issue #29: tracked AND untracked, one implementation
        for line in sorted(changed2):
            self.assertRegex(line, r"-run1[45678]-", "only the RUN 14 / RUN 15 (Issue #24) and RUN 16 / 17 / 18 (Issue #33) fixtures were added: " + line)


class TheRejectedInstrument(unittest.TestCase):
    def test_recorded_with_its_reasons_and_classification(self):
        s = plain(section10())
        for tok in ("### 10.1 An instrument evaluated and REJECTED", "romhacking.net/homebrew/142",
                    "OPERATOR OBSERVATION, not verified by the Executor", "roughly 21 seconds", "START press",
                    "does not support button combinations", "more than half the session",
                    "defeats the L + R-together observation outright", "Verdict: rejected as an instrument for RUN 14 and RUN 15",
                    "nothing from it enters the repository", "must accept simultaneous presses"):
            self.assertIn(tok, s, tok)


class TheRecollectionAndTheComposition(unittest.TestCase):
    def test_the_recollection_is_classified_and_corroborates_the_policy(self):
        s = plain(section10())
        for tok in ("### 10.2 The Operator's recollection of the Start-up Disc",
                    "OPERATOR OBSERVATION, and a recollection of past use, not an observation made under a pre-registered procedure",
                    "not verified by the Executor", "X and Y act as SELECT", "Y becomes L, X becomes R", "Start is START",
                    "Z opens the Disc's OSD", "Z unmapped", "the very button the Disc reserves for its OSD", "Phase 9 OSD"):
            self.assertIn(tok, s, tok)
        # every row of the corroboration table agrees
        rows = [l for l in section10().splitlines() if l.startswith("| ") and not l.startswith("| Recollection") and not l.startswith("| ---")]
        self.assertGreaterEqual(len(rows), 7)
        for l in rows:
            self.assertRegex(l, r"\| (yes[^|]*|consistent with the code's two modes) \|$", l)

    def test_the_composition_is_worked_out_with_its_conditions_and_its_weakness(self):
        s = plain(section10())
        for tok in ("### 10.3 The composition", "it holds as logic", "Term T1 (FACT, static", "PAD Y goes to word bit 8",
                    "Term T2 (the recollection", "Identification I", "the code has exactly two modes",
                    "Not verified by reading the Disc's option code path", "word bit 8 reaches the AGB as L, and bit 9 as R",
                    "As logic, yes, on two conditions", "Y acting as R", "the opposite conclusion",
                    "the detail memory is least reliable about", "does NOT change GBP-KEY-004's status (CORROBORATED, not FACT)",
                    "does NOT close U-GBP-010", "the descriptor stays exactly as it is", "REGISTERS.md keeps H",
                    "What would turn it into a recorded observation", "not part of §V7 and not a condition of RUN 14",
                    "never FACT"):
            self.assertIn(tok, s, tok)
        steps = section10()[section10().index("```text"):]
        for step in ("a", "b", "c", "d", "e"):
            self.assertIsNotNone(re.search(r"^\s*%s  " % step, steps, re.M), step)

    def test_the_evidence_row_and_the_unknown(self):
        ev = read(EVIDENCE)
        self.assertEqual(len(re.findall(r"^## GBP-KEY-007 ", ev, re.M)), 1)
        head = ev[ev.index("## GBP-KEY-007 "):].splitlines()[0]
        self.assertIn("OPERATOR OBSERVATION (recollection); changes no status", head)
        self.assertEqual(re.findall(r"^## GBP-KEY-00[8-9]", ev, re.M), ["## GBP-KEY-008", "## GBP-KEY-009"])   # Issue #24's findings
        self.assertIn("## GBP-KEY-004 — The static result on the L/R order: the Start-up Disc, GBI and Dolphin's model all put L at word bit 8 and R at word bit 9, the reverse of KEYINPUT — CORROBORATED for the encoding the references target; the physical routing NOT established", ev)
        body = plain(ev[ev.index("## GBP-KEY-007 "):ev.index("## GBP-VID-001 ")])
        for tok in ("recollection of past use", "not verified by the Executor", "GBP-KEY-004 stays CORROBORATED, not FACT",
                    "U-GBP-010 stays OPEN", "the descriptor is unchanged", "never FACT", "nothing physical was measured by this project"):
            self.assertIn(tok, body, tok)
        hw = max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M))
        self.assertEqual(hw, 284)   # GBP-HW-261…265: RUN 14 / RUN 15 (Issue #24); 266…271: RUN 16 / 17 / 18 (Issue #33)   # 272: Issue #46 (the CONTROL bit 0x02 split, FACT for the split / HYPOTHESIS for the cause); 273…277: Issue #47 (RUN 23 / RUN 24, §V7.7); 278…284: Issue #52 (RUN 21 / 22 / 25 / 26, §V7.8)
        u = read(UNKNOWNS)
        m = re.search(r"^## U-GBP-010\b.*$", u, re.M)
        self.assertIn("CLOSED 2026-09-21", m.group(0))   # closed by RUN 14 / RUN 15, not by the recollection
        self.assertIn("GBP-KEY-007", u)
        # Issue #26 promoted the order to C (never FACT) in REGISTERS.md; the H of this checkpoint is history
        self.assertNotIn("H (L/R bit order)", read(REGISTERS))
        self.assertIn("C — was H until 2026-09-21", read(REGISTERS))                      # the history kept
        self.assertIn("L/R bit order: F (hw, run-scoped) since 2026-09-21", read(REGISTERS))   # Issue #33: RUN 17 / RUN 18


class TheRecords(unittest.TestCase):
    def test_devlog_and_handoff(self):
        d = read(DEVLOG)
        i = d.rindex("## 2026-09-21 — Issue #22")
        j = d.find("\n## 2026", i + 1)
        e = d[i:j if j > 0 else None]
        for tok in ("REJECTED", "recollection", "GBP-KEY-007", "U-GBP-010 OPEN", "byte-identical", "no hardware, no code"):
            self.assertIn(tok, e, tok)
        self.assertNotRegex(e, r"GBP-HW-\d{3}")
        h = read(HANDOFF)
        self.assertIn("That the Operator's Start-up Disc recollection settles the L/R order.", h)
        self.assertIn("issue 22", h)


if __name__ == "__main__":
    unittest.main()
