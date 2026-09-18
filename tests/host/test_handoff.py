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
            if not os.path.exists(os.path.join(ROOT, p)):
                missing.append(p)
        self.assertEqual(sorted(set(missing)), [],
                         "HANDOFF.md names paths that do not exist: %s" % sorted(set(missing)))


class References(unittest.TestCase):
    def test_referenced_evidence_ids_exist(self):
        ev = read(EVIDENCE)
        ids = set(re.findall(r"GBP-HW-\d{3}", read(HANDOFF)))
        self.assertTrue(ids, "the handoff cites no evidence at all")
        missing = [i for i in sorted(ids) if ("### %s" % i) not in ev]
        self.assertEqual(missing, [], "cited but not defined in EVIDENCE.md: %s" % missing)

    def test_referenced_unknowns_exist(self):
        unk = read(os.path.join(ROOT, "docs", "research", "UNKNOWNS.md"))
        for u in sorted(set(re.findall(r"U-GBP-\d{3}", read(HANDOFF)))):
            self.assertIn(u, unk, "%s cited by the handoff is not in UNKNOWNS.md" % u)

    def test_referenced_build_ids_exist_in_the_tree(self):
        """A build id in the artifact table must be findable: either a POC
        Makefile declares it, or the Swiss manifest builds it as a variant."""
        layout = read(os.path.join(ROOT, "tools", "swiss-layout.tsv"))
        makefiles = "".join(read(os.path.join(ROOT, "poc", d, "Makefile"))
                            for d in os.listdir(os.path.join(ROOT, "poc"))
                            if os.path.exists(os.path.join(ROOT, "poc", d, "Makefile")))
        haystack = layout + makefiles + read(os.path.join(ROOT, "Makefile"))
        for bid in ("vstate-0004", "color-0001"):
            self.assertIn(bid, haystack, "%s is cited but not produced anywhere" % bid)
        self.assertIn("vstate-prewait", haystack)

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
    def test_it_is_vendor_neutral_in_role(self):
        text = read(AGENTS)
        self.assertIn("Mandatory read order", text)
        self.assertIn("FACT", text)
        self.assertIn("CORROBORATED", text)
        self.assertIn("HYPOTHESIS", text)
        self.assertIn("UNKNOWN", text)
        # it points at CLAUDE.md rather than duplicating it
        self.assertIn("CLAUDE.md", text)

    def test_it_stays_a_door_not_the_building(self):
        """If AGENTS.md grows into a second copy of the documentation it will
        drift out of sync with it, which is the failure it exists to prevent."""
        self.assertLess(len(read(AGENTS).splitlines()), 200)

    def test_claude_md_points_at_the_neutral_layer(self):
        text = read(os.path.join(ROOT, "CLAUDE.md"))
        self.assertIn("AGENTS.md", text)
        self.assertIn("docs/HANDOFF.md", text)


if __name__ == "__main__":
    unittest.main()
