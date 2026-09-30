"""AGENTS.md and docs/HANDOFF.md — the agent-neutral entry layer.

A handoff that points at a file which does not exist, or that says a rebuilt
binary was physically tested, is worse than no handoff: it is confidently wrong
to the next agent, who has no chat history to correct it with. These tests check
the properties that would cause exactly that.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENTS = os.path.join(ROOT, "AGENTS.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
README = os.path.join(ROOT, "README.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
HWTESTS = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")

LINK = re.compile(r"\[[^\]]+\]\(([^)#]+)(#[^)]*)?\)")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class FilesExist(unittest.TestCase):
    def test_the_entry_layer_exists(self):
        for p in (AGENTS, HANDOFF):
            self.assertTrue(os.path.exists(p), p)


class Links(unittest.TestCase):
    """Every relative link in the entry layer must resolve. A dead pointer in a
    handoff sends the next agent looking for a file that never existed."""

    def _check(self, doc):
        base = os.path.dirname(doc)
        bad = []
        for m in LINK.finditer(read(doc)):
            target = m.group(1).strip()
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not os.path.exists(os.path.normpath(os.path.join(base, target))):
                bad.append(target)
        self.assertEqual(bad, [], "%s: unresolvable links %s" % (os.path.basename(doc), bad))

    def test_agents_links_resolve(self):
        self._check(AGENTS)

    def test_handoff_links_resolve(self):
        self._check(HANDOFF)

    def test_readme_links_resolve(self):
        self._check(README)

    def test_every_backticked_repo_path_in_the_handoff_exists(self):
        """Paths are quoted in prose too, not only in links. Only strings that
        are actually paths are checked: a bare `EVIDENCE.md` in a sentence is
        shorthand, while `docs/research/EVIDENCE.md` is a promise."""
        missing = []
        for m in re.finditer(r"`([A-Za-z0-9_./-]+\.(?:md|py|h|c|tsv|gba|dol))`", read(HANDOFF)):
            p = m.group(1)
            if "/" not in p:                  # prose shorthand, not a path
                continue
            if p.startswith("build/"):        # build outputs are not versioned
                continue
            if p.startswith("ogc/"):          # a toolchain header, not a repo path
                continue
            if p.startswith("/"):             # Issue #47: an ABSOLUTE path is the Operator's removable media
                continue                      # (the SD card, mounted only when it is in the reader); whether it
                                              # is plugged in is not a property of this tree, and this test says
                                              # in its own docstring that it checks REPO paths
            if not os.path.exists(os.path.join(ROOT, p)):
                missing.append(p)
        self.assertEqual(sorted(set(missing)), [],
                         "HANDOFF.md names paths that do not exist: %s" % sorted(set(missing)))


class References(unittest.TestCase):
    def test_referenced_evidence_ids_exist(self):
        """EVIDENCE.md uses `##` for its older entries and `###` for the newer
        ones, so the check is "defined as a heading", not "defined at one depth":
        a citation of GBP-HW-058 is as valid as one of GBP-HW-120."""
        ev = read(EVIDENCE)
        defined = set(re.findall(r"^#{2,3} (GBP-HW-\d{3})", ev, re.M))
        ids = set(re.findall(r"GBP-HW-\d{3}", read(HANDOFF)))
        self.assertTrue(ids, "the handoff cites no evidence at all")
        self.assertGreater(len(defined), 100, "the heading scan found almost nothing")
        missing = sorted(ids - defined)
        self.assertEqual(missing, [], "cited but not defined in EVIDENCE.md: %s" % missing)

    def test_referenced_unknowns_exist(self):
        unk = read(os.path.join(ROOT, "docs", "research", "UNKNOWNS.md"))
        for u in sorted(set(re.findall(r"U-GBP-\d{3}", read(HANDOFF)))):
            self.assertIn(u, unk, "%s cited by the handoff is not in UNKNOWNS.md" % u)

    def _buildable(self):
        """Every build id this tree can actually produce: a POC Makefile declares
        it, or the Swiss manifest builds it as a variant."""
        layout = read(os.path.join(ROOT, "tools", "swiss-layout.tsv"))
        makefiles = "".join(read(os.path.join(ROOT, "poc", d, "Makefile"))
                            for d in os.listdir(os.path.join(ROOT, "poc"))
                            if os.path.exists(os.path.join(ROOT, "poc", d, "Makefile")))
        return layout + makefiles + read(os.path.join(ROOT, "Makefile"))

    def test_referenced_build_ids_exist_in_the_tree(self):
        haystack = self._buildable()
        for bid in ("vstate-0004", "color-0002"):
            self.assertIn(bid, haystack, "%s is cited but not produced anywhere" % bid)
        self.assertIn("vstate-prewait", haystack)

    def test_a_retired_build_id_is_marked_historical_not_buildable(self):
        """color-0001 physically ran and can no longer be rebuilt from HEAD: the
        POC now declares color-0002. That is the intended state - the handoff
        must present it as history, not as something to launch."""
        haystack = self._buildable()
        self.assertNotIn("color-0001", haystack,
                         "color-0001 is buildable again; a historical run must not be reproducible "
                         "under its own id without a deliberate decision")
        text = read(HANDOFF)
        self.assertIn("color-0001", text)
        self.assertIn("color-0002", text)
        self.assertIn("PHYSICALLY EXECUTED", text)

    def test_swiss_manifest_is_referenced_and_real(self):
        self.assertIn("tools/swiss-layout.tsv", read(HANDOFF))
        self.assertTrue(os.path.exists(os.path.join(ROOT, "tools", "swiss-layout.tsv")))


class ArtifactIdentity(unittest.TestCase):
    """The distinction this project can least afford to blur."""

    PHYSICAL_PREWAIT_DOL = "b5f0060a46d2e6429f494a9fa53d14acf07a97f61d01847acf0b6cb807a48709"

    def test_the_handoff_records_the_exact_physical_prewait_hash(self):
        self.assertIn(self.PHYSICAL_PREWAIT_DOL, read(HANDOFF))

    def test_the_handoff_warns_that_a_rebuild_is_not_the_tested_artifact(self):
        text = read(HANDOFF)
        self.assertIn("does not inherit physical status", text.replace("\n", " "))
        self.assertIn("80-prewait", text)

    def test_no_document_claims_the_exported_dol_was_physically_executed(self):
        """`build/swiss/80-prewait/boot.dol` is a copy of whatever is built now.
        Nothing may say it is the DOL that ran on hardware."""
        bad = []
        for root, _dirs, files in os.walk(os.path.join(ROOT, "docs")):
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                p = os.path.join(root, fn)
                for line in read(p).splitlines():
                    low = line.lower()
                    if "80-prewait" in low and re.search(r"physically (executed|tested|validated)", low):
                        if "not" not in low and "warning" not in low:
                            bad.append("%s: %s" % (os.path.relpath(p, ROOT), line.strip()[:110]))
        self.assertEqual(bad, [], bad)

    def test_hardware_tests_carries_the_identity_warning(self):
        self.assertIn("IDENTITY WARNING", read(HWTESTS))


class ResumePrompt(unittest.TestCase):
    def test_the_prompt_exists_and_names_real_paths(self):
        text = read(HANDOFF)
        self.assertIn("## Canonical resume prompt", text)
        start = text.index("## Canonical resume prompt")
        prompt = text[start:]
        for p in ("AGENTS.md", "docs/HANDOFF.md"):
            self.assertIn(p, prompt)
            self.assertTrue(os.path.exists(os.path.join(ROOT, p)))

    def test_the_prompt_keeps_every_safeguard(self):
        prompt = read(HANDOFF)[read(HANDOFF).index("## Canonical resume prompt"):].lower()
        for phrase in ("do not modify anything yet",
                       "state baseline commit",
                       "physical hardware is the final authority",
                       "auxiliary",
                       "do not convert corroborated",
                       "compare the sha-256",
                       "do not change frozen formats",
                       "stop after the takeover report"):
            self.assertIn(phrase, prompt, "the resume prompt lost the safeguard %r" % phrase)

    def test_the_readme_points_at_the_handoff(self):
        text = read(README)
        self.assertIn("docs/HANDOFF.md", text)
        self.assertIn("AGENTS.md", text)
        self.assertIn("canonical resume prompt", text.lower())


class Baseline(unittest.TestCase):
    def test_the_state_baseline_commit_is_a_real_ancestor(self):
        m = re.search(r"STATE BASELINE COMMIT\s+([0-9a-f]{40})", read(HANDOFF))
        self.assertIsNotNone(m, "no STATE BASELINE COMMIT recorded")
        sha = m.group(1)
        r = subprocess.run(["git", "cat-file", "-e", sha + "^{commit}"], cwd=ROOT)
        self.assertEqual(r.returncode, 0, "%s is not a commit in this repository" % sha)
        r = subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=ROOT)
        self.assertEqual(r.returncode, 0, "%s is not an ancestor of HEAD" % sha)

    def test_the_staleness_check_is_documented(self):
        text = read(HANDOFF)
        self.assertIn("STALE", text)
        self.assertIn("git log --oneline", text)


class AgentsFile(unittest.TestCase):
    """AGENTS.md is the SINGLE normative source of project instructions.

    Issue #150 (2026-09-30): the Operator merged CLAUDE.md into AGENTS.md and removed CLAUDE.md, with no stub ("o arquivo claude.md nao existe mais... agora esta unificado
    tudo no AGENTS.md"). That decision SUPERSEDED the earlier two-file design these tests used to pin: AGENTS.md as a short "door" of fewer than 200 lines that pointed at a
    CLAUDE.md holding the policy. The door rule is gone on purpose; the pins below are the single-source design's.
    """

    def test_it_is_the_single_normative_source_and_carries_the_vocabulary_and_the_read_order(self):
        text = read(AGENTS)
        self.assertIn("single normative source of project instructions", text)
        self.assertIn("No agent-specific file may weaken or override these rules.", text)
        self.assertIn("Mandatory read order", text)
        order = text[text.index("# 1. Mandatory read order"):text.index("# 2. Project mission")]
        for f in ("AGENTS.md", "docs/HANDOFF.md", "README.md", "docs/ROADMAP.md", "docs/RESEARCH_METHOD.md", "docs/research/EVIDENCE.md",
                  "docs/research/HARDWARE_TESTS.md", "docs/research/UNKNOWNS.md", "docs/research/DEVLOG.md"):
            self.assertIn(f, order, "the read order lost " + f)
        vocab = text[text.index("# 4. Evidence vocabulary"):text.index("# 5.")]
        for w in ("FACT", "CORROBORATED", "HYPOTHESIS", "UNKNOWN"):
            self.assertIn(w, vocab)
        self.assertIn("# 3. Authority hierarchy", text)
        self.assertIn("REAL PHYSICAL HARDWARE", text)

    def test_it_holds_the_policy_that_used_to_live_in_the_other_file(self):
        """The 47 sections carry the permanent policies the old CLAUDE.md held (the map is in docs/HANDOFF.md)."""
        text = read(AGENTS)
        heads = re.findall(r"^# (\d+)\. (.+)$", text, re.M)
        self.assertEqual([int(n) for n, _ in heads], list(range(1, 48)), "the sections are numbered 1..47 without a gap")
        for title in ("Normal physical Link Port behavior is a permanent requirement", "Mobile Adapter is late-stage work", "Hardware research safety", "Dolphin",
                      "Commit discipline", "GitHub operational coordination", "Shared checkout rules", "Local RAG", "Core decision rule"):
            self.assertTrue(any(title in t for _, t in heads), "no section titled like %r" % title)

    def test_it_stays_a_policy_file_and_not_a_log(self):
        """The single source must not become the chronological project log (its own section 45)."""
        text = read(AGENTS)
        self.assertIn("Do not turn this file into a chronological project log.", text)
        self.assertIsNone(re.search(r"^#+ 20\d\d-\d\d-\d\d", text, re.M), "a dated log heading in AGENTS.md")
        self.assertIsNone(re.search(r"\bRUN \d{2}\b", text.split("# 39.")[0]), "a run result in the policy sections")

    def test_a_claude_md_if_one_ever_appears_only_points_at_the_single_source(self):
        """No CLAUDE.md exists (the Operator's decision). One MAY appear, as a compatibility entry point for a tool that looks for the name; it must then hold no policy."""
        path = os.path.join(ROOT, "CLAUDE.md")
        self.assertIn("`CLAUDE.md`, when present, is only a compatibility entry point", read(AGENTS))
        if not os.path.exists(path):
            return
        text = read(path)
        self.assertIn("AGENTS.md", text)
        self.assertLess(len(text.splitlines()), 20, "a CLAUDE.md that is not a pointer")
        self.assertIsNone(re.search(r"^#+ \d+\.", text, re.M), "a numbered policy section in CLAUDE.md")

    def test_the_live_entry_points_name_the_single_source_not_a_second_file(self):
        handoff, readme = read(HANDOFF), read(README)
        self.assertIn("single normative source", handoff)
        self.assertNotIn("](../CLAUDE.md)", handoff, "HANDOFF links a file that no longer exists")
        self.assertNotIn("](CLAUDE.md)", readme)
        self.assertIn("single normative source", readme)
        for p in (".github/PULL_REQUEST_TEMPLATE.md", ".github/ISSUE_TEMPLATE/checkpoint.md"):
            t = read(os.path.join(ROOT, p))
            self.assertIn("`AGENTS.md` §36", t)
            self.assertNotIn("`CLAUDE.md` §24", t)


class SectionMap(unittest.TestCase):
    """The old CLAUDE.md §N -> AGENTS.md § map (docs/HANDOFF.md) keeps the append-only records' citations resolvable."""

    def _map(self):
        h = read(HANDOFF)
        i = h.index("## AGENTS.md section map")
        return h[i:h.index("## Canonical resume prompt")]

    def test_every_old_section_1_to_31_is_mapped_and_every_target_exists(self):
        m = self._map()
        block = m[m.index("```text"):m.index("```", m.index("```text") + 7)]
        text = read(AGENTS)
        n_new = len(re.findall(r"^# \d+\. ", text, re.M))
        seen = set()
        for line in block.splitlines():
            row = re.match(r"^§(\d+)(?:\.\d)?\s+.*?\s{2,}(§\d+(?:, §\d+)*)(?: \(\+ [^)]*\))?(?: \([^)]*\))?\s", line + " ")
            if not row:
                continue
            seen.add(int(row.group(1)))
            for tgt in re.findall(r"§(\d+)", row.group(2)):
                self.assertTrue(1 <= int(tgt) <= n_new, "%s targets a missing section" % line[:60])
        self.assertEqual(sorted(seen), list(range(1, 32)), "an old section has no row")

    def test_the_map_says_what_was_dropped_and_leaves_the_records_alone(self):
        m = " ".join(self._map().split())
        for tok in ("keep their \"`CLAUDE.md` §N\" citations exactly as written", "no stub was created", "git show 5739f6b:CLAUDE.md",
                    "was dropped", "no single home", "carried only in part", "softened"):
            self.assertIn(tok, m, tok)


if __name__ == "__main__":
    unittest.main()
