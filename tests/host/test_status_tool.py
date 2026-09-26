"""tests/host/test_status_tool.py -- tools/status.sh, the read-only answer to "is anything happening?" (GitHub Issue
#124, asked by the Orchestrator for the Operator).

Held here, on a throwaway repository with a controlled process list (STATUS_PS):
  * every verdict it can give, and the one that matters most: with nothing running, nothing unpushed, a clean tree and
    an old last commit it says NOTHING VISIBLE IS HAPPENING, plainly, and never something reassuring;
  * commits ahead of origin/main read as WAITING TO PUSH, a gate or build in flight as ACTIVE with its elapsed time;
  * it is READ-ONLY: the repository's .git is byte for byte the same after it runs, and it never fetches.
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.path.join(ROOT, "tools", "status.sh")


def git(repo, *args, env=None):
    e = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
             GIT_COMMITTER_EMAIL="t@t", **(env or {}))
    return subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True, env=e, check=True).stdout


def snapshot(d):
    out = {}
    for base, _dirs, files in os.walk(d):
        for f in files:
            p = os.path.join(base, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, d)] = (hashlib.sha256(fh.read()).hexdigest(), os.stat(p).st_mtime_ns)
    return out


class TheStatusTool(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.repo = os.path.join(self.d, "repo")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        old = {"GIT_AUTHOR_DATE": "2000-01-01T00:00:00", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00"}
        with open(os.path.join(self.repo, "a.txt"), "w") as f:
            f.write("a\n")
        git(self.repo, "add", "a.txt")
        git(self.repo, "commit", "-q", "-m", "first", env=old)
        git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        self.ps = os.path.join(self.d, "ps.txt")
        self.set_ps("")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def set_ps(self, text):
        with open(self.ps, "w") as f:
            f.write(text)

    def run_tool(self):
        r = subprocess.run(["bash", TOOL, self.repo], capture_output=True, text=True, timeout=30,
                           env=dict(os.environ, STATUS_PS=self.ps))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_idle_is_said_plainly(self):
        out = self.run_tool()
        self.assertIn("to push: 0", out)
        self.assertIn("verdict: NOTHING VISIBLE IS HAPPENING", out)
        self.assertIn("(sees git and processes only; not reading, review agents or thinking)", out)

    def test_a_gate_in_flight_is_active_with_its_elapsed_time(self):
        self.set_ps("  125 make test-python\n  400 /usr/bin/python3 /home/x/.local/bin/pytest -q tests/host\n"
                    "   30 bash tools/status.sh\n")
        out = self.run_tool()
        self.assertIn("running: 6min   /usr/bin/python3 /home/x/.local/bin/pytest -q tests/host", out)
        self.assertIn("running: 2min   make test-python", out)
        self.assertFalse([l for l in out.splitlines() if l.startswith("running:") and "status.sh" in l])
        self.assertIn("verdict: ACTIVE -- 2 run(s) in flight", out)

    def test_unpushed_commits_are_the_gate_not_idleness(self):
        with open(os.path.join(self.repo, "b.txt"), "w") as f:
            f.write("b\n")
        git(self.repo, "add", "b.txt")
        git(self.repo, "commit", "-q", "-m", "second")
        out = self.run_tool()
        self.assertIn("to push: 1", out)
        self.assertIn("last commit: ", out)
        self.assertIn("second", out)
        self.assertIn("verdict: WAITING TO PUSH -- 1 commit(s) ahead of origin/main", out)

    def test_a_changed_tree_is_editing(self):
        with open(os.path.join(self.repo, "a.txt"), "w") as f:
            f.write("changed\n")
        out = self.run_tool()
        self.assertIn("working tree: 1 file(s) changed, not committed", out)
        self.assertIn("verdict: EDITING", out)

    def test_a_recent_commit_is_recent_not_active(self):
        with open(os.path.join(self.repo, "c.txt"), "w") as f:
            f.write("c\n")
        git(self.repo, "add", "c.txt")
        git(self.repo, "commit", "-q", "-m", "third")
        git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        out = self.run_tool()
        self.assertIn("verdict: RECENT -- last commit ", out)

    def test_it_writes_nothing(self):
        before = snapshot(os.path.join(self.repo, ".git"))
        self.run_tool()
        self.assertEqual(snapshot(os.path.join(self.repo, ".git")), before)
        with open(TOOL) as f:
            src = f.read()
        code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
        for verb in ("git fetch", "git pull", "git push", "git reset", "git checkout", "git clean", "update-ref"):
            self.assertNotIn(verb, code, verb)


if __name__ == "__main__":
    unittest.main()
