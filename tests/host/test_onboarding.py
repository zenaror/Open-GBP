"""tests/host/test_onboarding.py -- Issue #162: docs/ONBOARDING.md, the orientation page for an agent with no chat history, and the minimum
current-state corrections that came with it (the Gitea archive retired on 2026-10-06; the HANDOFF role table's snapshot).

A starting page that points at a file which does not exist, or that sounds like policy, is worse than none: the next agent has no chat
to correct it with. Durable forms only (no whole-file equality of a living document):
  * the page exists once, opens with the "orientation, not authority" statement and defers to AGENTS.md, and docs/README.md lists it;
  * every repository path it cites (in backticks or as a relative link) exists; machine-local paths -- build outputs, the Operator's raw
    drops and private inputs, the ignored archive, the external checkouts, the Operator's untracked .codex/ folder, absolute or home
    paths -- are properties of a host, not of this tree, and are not checked (as test_handoff.py does for build/ and absolute paths);
  * every Issue number it cites is at most #162, the highest when it was written; every evidence or unknown id it cites is defined;
  * its "known stale" section names what only the Operator can authorise (AGENTS.md sections 37, 39-42 and 17; the HANDOFF role table);
  * docs/HANDOFF.md carries the dated note once, ahead of Hardware Issue #161's paragraph, and only gained text against BASE;
  * README.md no longer carries the old Gitea sentence and carries the new one;
  * AGENTS.md is byte-identical to BASE as of the commit that added the page (before that commit exists: the working tree), so a later,
    authorised AGENTS.md edit does not turn this checkpoint's guard red.
"""
import difflib
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import guards  # noqa: E402

BASE = "5383653b1c280c24a0f5aa4f7cd37d560dc359e8"   # origin/main when Issue #162 was dispatched
PAGE = "docs/ONBOARDING.md"
HIGHEST_ISSUE = 163   # amended on top by Issue #163 (was 162): the page's known-stale section now cites it
OPENING = "**This page is orientation, not authority.**"
HANDOFF_NOTE = "**2026-10-06 (Issue #162), on top: a new agent starts at `docs/ONBOARDING.md`**"
PREV_BLOCKER = "**2026-10-05 (Hardware Issue #161), on top: `vehicle-0002` is PINNED as `29-vehicle2` and STAGED on the SD2SP2 card; no run has happened**"
OLD_README = "The former Gitea remote is kept as a non-canonical archive."
NEW_README = "The former Gitea archive was retired on 2026-10-06; GitHub is the only remote."
LOCAL_PREFIXES = ("build/", "logs/", "input/", "captures/local/", "external/", ".codex/", "origin/")
ROOT_FILES = ("AGENTS.md", "README.md", "Makefile", "Dockerfile", "compose.yaml", "INITIAL_PROMPT.md")
PATHLIKE = re.compile(r"`([A-Za-z0-9_.~/-]+)`")
LINK = re.compile(r"\[[^\]]+\]\(([^)#]+)(#[^)]*)?\)")
ID = re.compile(r"\b((?:GBP|ENV)-[A-Z]+-\d{3}|U-(?:GBP|ENV)-\d{3})\b")


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def flat(s):
    return " ".join(s.split())


def section(text, heading):
    i = text.index(heading) + len(heading)
    j = text.find("\n## ", i)
    return text[i:] if j < 0 else text[i:j]


class ThePage(unittest.TestCase):
    def test_it_exists_once(self):
        found = [os.path.relpath(os.path.join(d, f), ROOT) for d, _, fs in os.walk(os.path.join(ROOT, "docs")) for f in fs if f.upper().startswith("ONBOARDING")]
        found += [f for f in os.listdir(ROOT) if f.upper().startswith("ONBOARDING")]
        self.assertEqual(found, [PAGE])

    def test_it_opens_as_orientation_and_defers_to_the_sources(self):
        t = read(PAGE)
        lines = t.splitlines()
        self.assertTrue(lines[0].startswith("# Open-GBP onboarding"), lines[0])
        self.assertEqual(lines[1], "")
        self.assertTrue(lines[2].startswith(OPENING), lines[2])
        head = flat(t[:t.index("\n## ")])
        for w in ("It is neither evidence nor policy.", "is the single normative source of project instructions",
                  "When this page and a source it points at disagree, the source wins", "never instructions and never a source to cite",
                  "(recollection)"):
            self.assertIn(w, head, w)

    def test_docs_readme_lists_it(self):
        d = read("docs/README.md")
        block = d[d.index("```text"):d.index("```", d.index("```text") + 3)]
        self.assertIn("ONBOARDING.md", block)

    def test_it_stays_short(self):
        self.assertLessEqual(len(read(PAGE).splitlines()), 360, "an orientation page, not a copy of the notes")


class WhatItCites(unittest.TestCase):
    def test_every_cited_repository_path_exists(self):
        t = read(PAGE)
        missing = []
        for p in PATHLIKE.findall(t):
            if p.startswith(("/", "~")) or p.startswith(LOCAL_PREFIXES):
                continue
            if "/" in p:
                if not os.path.exists(os.path.join(ROOT, p.rstrip("/"))):
                    missing.append(p)
            elif p in ROOT_FILES and not os.path.exists(os.path.join(ROOT, p)):
                missing.append(p)
            elif p.endswith((".md", ".py", ".tsv", ".sh", ".java")) and p not in ROOT_FILES:
                # bare record names are shorthand for a file in the documented directories; it must still be one of them
                if not any(os.path.exists(os.path.join(ROOT, d, p)) for d in ("docs", "docs/research", "tools", "tests/host")):
                    missing.append(p)
        for m in LINK.finditer(t):
            target = m.group(1).strip()
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not os.path.exists(os.path.normpath(os.path.join(ROOT, "docs", target))):
                missing.append(target)
        self.assertEqual(sorted(set(missing)), [], "the page cites paths that do not exist")

    def test_the_path_check_sees_the_page(self):
        """A control for the check above: it must actually be reading paths, and a made-up one must fail it."""
        t = read(PAGE)
        seen = [p for p in PATHLIKE.findall(t) if "/" in p and not p.startswith(LOCAL_PREFIXES + ("/", "~"))]
        self.assertGreater(len(seen), 20)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "docs/research/NO_SUCH_RECORD.md")))

    def test_every_cited_issue_number_is_at_most_the_highest(self):
        nums = [int(n) for n in re.findall(r"#(\d+)\b", read(PAGE))]
        self.assertTrue(nums)
        self.assertEqual([n for n in nums if not 1 <= n <= HIGHEST_ISSUE], [])
        for n in (60, 137, 142, 149, 150, 153, 155, 156, 157, 159, 161, 162):
            self.assertIn(n, nums, n)

    def test_every_cited_evidence_or_unknown_id_is_defined(self):
        defined = set()
        for rel in ("docs/research/EVIDENCE.md", "docs/research/UNKNOWNS.md"):
            defined |= set(re.findall(r"^#{2,4} +((?:GBP|ENV)-[A-Z]+-\d{3}|U-(?:GBP|ENV)-\d{3})\b", read(rel), re.M))
        hw = read("docs/research/HARDWARE_TESTS.md")
        cited = set(ID.findall(read(PAGE)))
        self.assertTrue(cited)
        self.assertEqual(sorted(i for i in cited if i not in defined and i not in hw), [])

    def test_known_stale_names_what_only_the_operator_can_authorise(self):
        """Amended on top by Issue #163: the three AGENTS.md items (sections 37, 39-42 and 17) were authorised by the Operator on 2026-10-06 and are
        recorded as resolved; what stays pending is the HANDOFF role table (the one remaining "(Operator)" item)."""
        s = flat(section(read(PAGE), "## 5. Known stale"))
        self.assertIn("his authorisation is **pending**", s)
        for w in ("Resolved by Issue #163", "\"Current role assignment\" table", "retired by the Operator on 2026-10-06", "retired on 2026-10-05"):
            self.assertIn(w, s, w)
        items = [l for l in section(read(PAGE), "## 5. Known stale").splitlines() if l.startswith("- **(Operator)**")]
        self.assertEqual(len(items), 1, "only the HANDOFF role table remains pending since Issue #163")


class TheCorrections(unittest.TestCase):
    def test_the_handoff_note_is_present_once_ahead_of_the_previous_top_paragraph(self):
        h = read("docs/HANDOFF.md")
        sec = section(h, "## Current blocker / current question")
        self.assertEqual(h.count(HANDOFF_NOTE), 1)
        self.assertEqual(sec.count(HANDOFF_NOTE), 1)
        self.assertLess(sec.index(HANDOFF_NOTE), sec.index(PREV_BLOCKER))
        i = h.index(HANDOFF_NOTE)
        note = h[i:h.index(PREV_BLOCKER)]
        for w in ("the Gitea archive", "the Operator removed it on 2026-10-06", "GitHub (`origin`) is the only remote", "\"Current role assignment\" table",
                  "not by editing them", "`AGENTS.md` §37", "await the Operator's authorisation"):
            self.assertIn(w, note, w)
        self.assertNotIn("BREADTH", note)

    def test_the_handoff_only_gained_text(self):
        then, now = guards.show(BASE, "docs/HANDOFF.md").splitlines(), read("docs/HANDOFF.md").splitlines()
        removed = [x for x in difflib.unified_diff(then, now, lineterm="", n=0) if x.startswith("-") and not x.startswith("---")]
        self.assertEqual(removed, [], "a HANDOFF row, table or paragraph was edited; corrections go on top")

    def test_the_readme_drops_the_gitea_sentence(self):
        r = flat(read("README.md"))
        self.assertNotIn(OLD_README, r)
        self.assertEqual(r.count(NEW_README), 1)
        self.assertIn(OLD_README, flat(guards.show(BASE, "README.md")), "the BASE sentence this test retires")

    def test_agents_md_is_untouched_by_this_checkpoint(self):
        guards.show(BASE, "AGENTS.md")          # skips (registered) when BASE is absent; fails if the path is

        def raw(commit):
            return subprocess.run(["git", "-C", ROOT, "show", "%s:AGENTS.md" % commit], capture_output=True, check=True).stdout

        r = subprocess.run(["git", "-C", ROOT, "log", "--diff-filter=A", "--format=%H", "--", PAGE], capture_output=True, text=True)
        added = r.stdout.split()
        if added:
            now = raw(added[-1])
        else:
            with open(os.path.join(ROOT, "AGENTS.md"), "rb") as f:
                now = f.read()
        self.assertEqual(now, raw(BASE), "AGENTS.md changed in Issue #162, which did not authorise it")


if __name__ == "__main__":
    unittest.main()
