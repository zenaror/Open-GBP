"""tests/host/test_agents_md_alignment.py -- Issue #163: AGENTS.md aligned with three facts that changed on 2026-10-05/06 (the Gitea archive
retired, the local RAG retired, the build under rootless Podman), by the Operator's explicit authorisation, with no renumbering and no change
of rule.

AGENTS.md is the single normative source. An edit to it is authorised sentence by sentence, so the guard is by blocks and durable forms:
  * the 47 numbered sections still exist once, in order, with the titles they had at BASE (Issue #162's HEAD) except 39-42, whose operative
    text moved from a retired tool to the OMM and `git grep`;
  * the strings of the retired tools and of the old Docker and Gitea sentences are gone; the section 16 text is byte-identical to BASE;
  * every section outside {the preamble, 1, 17, 31, 37, 39-42, 44} is byte-identical to BASE, and inside the others the removed and added
    lines are exactly the listed sentences (39-42 are checked by the statements they must keep and the ones they must not carry);
  * the principle of 39 (a hit is a pointer, never authority; the stale-copy rule), the dirty-tree rule of 40, the retrieval procedure of 41
    and the exclusion list of 42 survive;
  * HANDOFF carries the dated note once ahead of Issue #162's, only gained text, and the DEVLOG entry exists once.
AGENTS.md is read as of the commit that added this test (before that commit exists: the working tree), so a later, separately authorised
edit does not turn this checkpoint's guard red.
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

BASE = "76d5b3711bb6f021f06fb88d5367110baa7fdf89"   # origin/main when Issue #163 was dispatched (Issue #162 pushed)
ME = "tests/host/test_agents_md_alignment.py"
CHANGED = {1, 17, 31, 37, 39, 40, 41, 42, 44}
HANDOFF_NOTE = "**2026-10-06 (Issue #163), on top: `AGENTS.md` is aligned with three facts that changed on 2026-10-05/06"
PREV_NOTE = "**2026-10-06 (Issue #162), on top: a new agent starts at `docs/ONBOARDING.md`**"
DEVLOG_HEAD = "## 2026-10-06 — Issue #163: `AGENTS.md` aligned with"

GONE = ("Open-GBP-RAG", "rag_query.py", "rag_index.py", "gitea-archive", "git.home.zsrv", "Docker compilation", "project Docker environment",
        "Verify the Docker build environment", "If the RAG exists", "rag_query", "open-gbp.sqlite", "--allow-dirty", "an RAG snippet")

# (removed lines, added lines) per changed section other than 39-42
EXPECTED = {
    0: (["5. A OMM e o RAG local (seção 39) servem para localizar; nenhum dos dois prova nada sozinho."],
        ["5. A OMM e o `git grep` (seção 39) servem para localizar; nenhum dos dois prova nada sozinho."]),
    1: (["Issue title, or an RAG snippet."], ["Issue title, or a search hit."]),
    17: (["* Docker compilation;"], ["* container compilation (rootless Podman, §16);"]),
    31: (["The following must not enter the RAG or other derived project artifacts:"],
         ["The following must not enter the OMM or other derived project artifacts:"]),
    37: (["The former Gitea remote is an archive and is non-canonical:", "", "```text", "https://git.home.zsrv.com.br/zenaror/Open-GBP", "```",
          "gitea-archive   = archive, push disabled", "The Orchestrator moves workflow labels."],
         ["A Gitea archive existed until the Operator retired it on 2026-10-06. GitHub is", "the only remote.",
          "The Orchestrator seat moves workflow labels. In the current topology that seat",
          "is the central session; the planner only prepares texts and recommendations."]),
    44: (["3. Verify the Docker build environment.", "10. Compile entirely through the project Docker environment."],
         ["3. Verify the container build environment (rootless Podman, §16).",
          "10. Compile entirely through the project container environment (rootless Podman,", "    §16)."]),
}


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def flat(s):
    return " ".join(s.split())


def sections(text):
    parts = re.split(r"(?m)^(?=# \d+\. )", text)
    d = {0: parts[0]}
    for p in parts[1:]:
        d[int(re.match(r"# (\d+)\.", p).group(1))] = p
    return d


def agents_now():
    r = subprocess.run(["git", "-C", ROOT, "log", "--diff-filter=A", "--format=%H", "--", ME], capture_output=True, text=True)
    added = r.stdout.split()
    if added:
        return subprocess.run(["git", "-C", ROOT, "show", "%s:AGENTS.md" % added[-1]], capture_output=True, text=True, check=True).stdout
    return read("AGENTS.md")


def diff_lines(then, now):
    out = [x for x in difflib.unified_diff(then.splitlines(), now.splitlines(), lineterm="", n=0) if not x.startswith(("---", "+++", "@@"))]
    return [x[1:] for x in out if x.startswith("-")], [x[1:] for x in out if x.startswith("+")]


class TheSections(unittest.TestCase):
    def setUp(self):
        self.base = guards.show(BASE, "AGENTS.md")
        self.now = agents_now()
        self.B, self.N = sections(self.base), sections(self.now)

    def test_the_forty_seven_sections_exist_once_in_order(self):
        heads = re.findall(r"(?m)^# (\d+)\. (.+)$", self.now)
        self.assertEqual([int(k) for k, _ in heads], list(range(1, 48)))
        base = dict((int(k), t) for k, t in re.findall(r"(?m)^# (\d+)\. (.+)$", self.base))
        for k, t in heads:
            if int(k) not in (39, 40, 41, 42):
                self.assertEqual(t, base[int(k)], "section %s was retitled" % k)

    def test_sections_39_to_42_are_retitled_for_the_omm_and_git_grep(self):
        titles = dict((int(k), t) for k, t in re.findall(r"(?m)^# (\d+)\. (.+)$", self.now))
        self.assertEqual(titles[39], "Locating history — OMM and git grep")
        self.assertEqual(titles[40], "Derived indexes and dirty working trees")
        self.assertEqual(titles[41], "Retrieval procedure")
        self.assertEqual(titles[42], "What is deliberately excluded from the OMM")

    def test_the_retired_strings_are_gone(self):
        for s in GONE:
            self.assertNotIn(s, self.now, s)
        self.assertEqual(re.findall(r"\bRAG\b", self.now), ["RAG"], "the only mention of the RAG is the one-sentence history in section 39")
        self.assertIn("The local RAG was retired by the Operator on 2026-10-05.", self.now)

    def test_section_16_is_byte_identical_and_still_podman(self):
        self.assertEqual(self.N[16], self.B[16])
        self.assertIn("rootless Podman", self.N[16])
        self.assertIn("systemctl --user start podman.socket", self.N[16])

    def test_every_section_outside_the_changed_set_is_byte_identical(self):
        for k in sorted(set(self.B) - CHANGED - {0, 39, 40, 41, 42}):
            self.assertEqual(self.N[k], self.B[k], "section %d changed" % k)

    def test_the_changed_lines_are_exactly_the_listed_sentences(self):
        for k, (rem, add) in EXPECTED.items():
            r, a = diff_lines(self.B[k], self.N[k])
            self.assertEqual((r, a), (rem, add), "section %d (0 = the preamble)" % k)

    def test_the_preamble_is_otherwise_byte_identical(self):
        old, new = EXPECTED[0][0][0], EXPECTED[0][1][0]
        self.assertEqual(self.N[0], self.B[0].replace(old, new))
        self.assertEqual(self.B[0].count(old), 1)


class TheRewrittenSections(unittest.TestCase):
    def setUp(self):
        self.N = sections(agents_now())

    def test_39_keeps_the_principle_and_the_stale_copy_rule(self):
        s = flat(self.N[39])
        for w in ("The local RAG was retired by the Operator on 2026-10-05.", "`search`, `search_sources`, `read_source`", "`git grep` on `origin/main`",
                  "making a scientific decision;", "changing an evidence status;", "classifying a run;", "writing an experimental gate;",
                  "editing code based on historical project state;", "making a claim about what the historical record does or does not contain;",
                  "A search hit is a pointer, not a finding.", "open the canonical file;", "inspect the indicated line range;",
                  "read enough surrounding context;", "verify the current canonical state;", "cite the canonical file/evidence record (file:line at a commit)",
                  "Never cite the OMM or any search tool itself.", "If a claim's only support is a search hit, it is unsupported.",
                  "The OMM's copies of documents are of a specific commit.", "`git diff --stat <commit> origin/main`",
                  "treat all hits as leads and re-read the canonical source."):
            self.assertIn(w, s, w)
        for w in ("Issues;", "commit messages;", "`EVIDENCE.md`;", "reports;", "documentation;", "Operator communication."):
            self.assertIn(w, self.N[39], w)

    def test_40_is_the_dirty_tree_rule(self):
        s = flat(self.N[40])
        self.assertIn("Do not build a derived index, or record unpushed text as canonical, while:", s)
        self.assertIn("git status --porcelain", self.N[40])
        self.assertIn("is non-empty.", s)
        self.assertIn("must be checked against `origin/main` before being used for scientific or historical claims.", s)
        self.assertIn("The Orchestrator does not edit Open-GBP files.", s)

    def test_41_keeps_the_procedure_without_the_old_tools_options(self):
        s = flat(self.N[41])
        for w in ("Locate first", "Prefer 2–4 narrow searches over one broad query.", "evidence ID;", "unknown ID;", "build ID;", "run number;", "section;",
                  "register;", "protocol term.", "Open only the canonical ranges that are decisive.",
                  "Do not load huge append-only documents wholesale unless necessary."):
            self.assertIn(w, s, w)
        for tok in ("GBP-HW-272", "U-GBP-010", "play-0001", "RUN 13", "KEYPAD", "CONTROL 0x02"):
            self.assertIn(tok, self.N[41], tok)
        for w in ("--top", "--source", "--path"):
            self.assertNotIn(w, self.N[41], w)

    def test_42_keeps_the_exclusion_list(self):
        block = self.N[42][self.N[42].index("```text"):self.N[42].index("```", self.N[42].index("```text") + 7)]
        self.assertEqual(block.splitlines()[1:], ["input/", "captures/", "logs/", "build/", "external/", ".git/", "ROMs", "DOLs", "BINs", "images"])
        s = flat(self.N[42])
        self.assertIn("must not enter the OMM or any other derived artifact", s)
        self.assertIn("Private proprietary inputs and raw evidence must be accessed directly when needed.", s)
        self.assertIn("navigation mechanisms, not an evidence store.", s)

    def test_37_names_github_as_the_only_remote(self):
        s = flat(self.N[37])
        self.assertIn("https://github.com/zenaror/Open-GBP", s)
        self.assertIn("A Gitea archive existed until the Operator retired it on 2026-10-06. GitHub is the only remote.", s)
        self.assertIn("origin = GitHub, fetch/push", s)
        self.assertIn("Never force-push or rewrite history.", s)
        self.assertNotIn("git.home", self.N[37])


class TheRecords(unittest.TestCase):
    def test_the_handoff_note_is_present_once_ahead_of_issue_162s(self):
        h = read("docs/HANDOFF.md")
        sec = h[h.index("## Current blocker / current question"):]
        self.assertEqual(h.count(HANDOFF_NOTE), 1)
        self.assertEqual(sec.count(HANDOFF_NOTE), 1)
        self.assertLess(sec.index(HANDOFF_NOTE), sec.index(PREV_NOTE))
        note = flat(h[h.index(HANDOFF_NOTE):h.index(PREV_NOTE)])
        for w in ("no section renumbered, no rule changed", "§37", "§39-§42", "§17 and §44", "`docs/ONBOARDING.md` §5 is updated", "**No blocker.**"):
            self.assertIn(w, note, w)

    def test_the_handoff_only_gained_text_against_base(self):
        then = guards.show(BASE, "docs/HANDOFF.md").splitlines()
        removed = [x for x in difflib.unified_diff(then, read("docs/HANDOFF.md").splitlines(), lineterm="", n=0)
                   if x.startswith("-") and not x.startswith("---")]
        self.assertEqual(removed, [], "a HANDOFF row, table or paragraph was edited; corrections go on top")

    def test_the_devlog_entry_exists_once_and_the_devlog_only_gained_text(self):
        d = read("docs/research/DEVLOG.md")
        self.assertEqual(d.count(DEVLOG_HEAD), 1)
        then = guards.show(BASE, "docs/research/DEVLOG.md").splitlines()
        removed = [x for x in difflib.unified_diff(then, d.splitlines(), lineterm="", n=0) if x.startswith("-") and not x.startswith("---")]
        self.assertEqual(removed, [], "a DEVLOG entry was edited; entries are appended")

    def test_onboarding_records_the_three_items_as_resolved(self):
        t = read("docs/ONBOARDING.md")
        s = flat(t[t.index("## 5. Known stale"):t.index("## 6.")])
        self.assertIn("Resolved by Issue #163", s)
        self.assertEqual(len([l for l in t[t.index("## 5. Known stale"):t.index("## 6.")].splitlines() if l.startswith("- **(Operator)**")]), 1)
        self.assertNotIn("`AGENTS.md` §17 lists", s)


if __name__ == "__main__":
    unittest.main()
