"""tests/host/test_podman_build_env.py -- GitHub Issue #159: the build environment moves from Docker to rootless Podman.

What is held here, each checked rather than assumed (the container itself is NOT started by the suite: the reproduction gate is a procedure recorded in the DEVLOG,
because `make test-python` neither has the container toolchain nor should start it):

  * THE ENTRY POINT: `COMPOSE` is overridable (a command-line or environment value wins) and its default is `podman compose`, the choice the DEVLOG argues. No recipe line
    of the Makefile names `docker` any more; every container recipe goes through $(COMPOSE) / $(IN_CONTAINER).
  * THE USER NAMESPACE: compose.yaml reads `userns_mode` from LOCAL_USERNS (a Docker engine rejects `keep-id`, so it is a variable), the Makefile defaults it to `keep-id`,
    and the old `user: "${LOCAL_UID}:${LOCAL_GID}"` and the bind mount are unchanged.
  * THE IMAGE: the Dockerfile's FROM is the pinned base and has no COPY / ADD, which is what makes `.dockerignore`'s `*` safe; the build context therefore sends nothing.
  * THE GATE'S PINS: the two shas the reproduction was measured against are the ones in tools/swiss-layout.tsv (rows 28 and 27), so a pin cannot move without this test saying so.
  * THE RECORDS: the DEVLOG entry and the two HANDOFF paragraphs exist, start their blocks, carry the identities, and nothing older was edited or removed (the DEVLOG
    and the HANDOFF only gained text since the base commit).
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

BASE = "c4ea872"        # origin/main when #159 was dispatched (Issue #157 pushed)
VEHICLE_PIN = "a02bcfa3b84ccd363d7bad54c8e72411d9f2e9a49595963903d1feeac4acf5d2"
GBMODE_PIN = "e33115e348fbf7c51dfadba61d52ea4c8b07e64874c69550a832ed07e494a497"
IMAGE_ID = "ba9cd72a4bd027736197633b7510d269e07a2bf2894ef95018a2f2606d32b859"
DIGEST = "sha256:13bb658d3f18903816617223f5d7c6f776d3db3ea806aae67f8d35a7a69d4c85"
DEVLOG, HANDOFF = "docs/research/DEVLOG.md", "docs/HANDOFF.md"
DEVLOG_HEAD = "## 2026-10-05 — Issue #159: the build environment moves from Docker to rootless Podman"
HANDOFF_BLOCKER = "**2026-10-05 (Issue #159), on top: the build environment is rootless Podman, not Docker**"
HANDOFF_NEXT = "**2026-10-05 (Issue #159), on top: Issue #159 is done"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def make_dry(*args, env=None):
    e = dict(os.environ)
    e.pop("COMPOSE", None)
    e.update(env or {})
    p = subprocess.run(["make", "-n", "--no-print-directory", "-C", ROOT] + list(args), capture_output=True, text=True, env=e)
    assert p.returncode == 0, "make -n %s failed:\n%s%s" % (" ".join(args), p.stdout, p.stderr)
    return p.stdout


class ComposeEntryPoint(unittest.TestCase):
    def test_default_is_podman_compose(self):
        out = make_dry("env-check")
        self.assertIn("podman compose run --rm -T -e GIT_COMMIT=", out)
        self.assertNotIn("docker compose", out)

    def test_command_line_override_wins(self):
        out = make_dry("env-check", "COMPOSE=sentinel-engine compose-x")
        self.assertIn("sentinel-engine compose-x run --rm -T -e GIT_COMMIT=", out)
        self.assertNotIn("podman compose", out)

    def test_environment_override_wins(self):
        out = make_dry("env-check", env={"COMPOSE": "env-engine compose-y"})
        self.assertIn("env-engine compose-y run --rm -T -e GIT_COMMIT=", out)

    def test_every_container_target_goes_through_the_variable(self):
        # the targets with a container recipe: IN_CONTAINER ones and the two that spell $(COMPOSE) themselves (vehicle, shell)
        for target in ("build", "vehicle", "gbmode-session", "shell"):
            out = make_dry(target, "COMPOSE=sentinel-engine")
            self.assertIn("sentinel-engine run --rm", out, target)

    def test_no_recipe_line_names_docker(self):
        # comments may say Docker (history, the Docker engine as an override); a recipe line may not
        for n, line in enumerate(read("Makefile").splitlines(), 1):
            if line.startswith("\t") and re.search(r"\bdocker\b", line):
                self.fail("Makefile:%d is a recipe line that names docker: %s" % (n, line.strip()))

    def test_the_default_is_declared_once_with_question_equals(self):
        lines = [x for x in read("Makefile").splitlines() if re.match(r"^COMPOSE\s*[:?+]?=", x)]
        self.assertEqual(lines, ["COMPOSE ?= podman compose"])


class UserNamespace(unittest.TestCase):
    def test_compose_yaml_reads_userns_mode_from_a_variable(self):
        c = read("compose.yaml")
        self.assertIn('userns_mode: "${LOCAL_USERNS:-}"', c)
        self.assertIn('user: "${LOCAL_UID}:${LOCAL_GID}"', c)
        self.assertIn("- .:/workspace", c)
        self.assertNotIn("keep-id\"", c.split("userns_mode:")[1].split("\n")[0])   # the value is not hardcoded: Docker rejects keep-id

    def test_makefile_defaults_keep_id_and_exports_it(self):
        self.assertIn("export LOCAL_USERNS ?= keep-id", read("Makefile"))

    def _exported(self, env_extra):
        env = {k: v for k, v in os.environ.items() if k != "LOCAL_USERNS"}
        env.update(env_extra)
        p = subprocess.run(["make", "-C", ROOT, "--no-print-directory", "--eval", "zz-print-userns:\n\t@printf '[%s]' \"$$LOCAL_USERNS\"", "zz-print-userns"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout

    def test_the_variable_reaches_the_recipe_environment(self):
        self.assertEqual(self._exported({}), "[keep-id]")

    def test_a_docker_engine_can_empty_it(self):
        self.assertEqual(self._exported({"LOCAL_USERNS": ""}), "[]")


class Image(unittest.TestCase):
    def test_dockerfile_is_the_pinned_base_with_no_copy(self):
        d = read("Dockerfile").splitlines()
        self.assertEqual(d[0], "FROM ghcr.io/extremscorner/libogc2:20260805")
        for line in d:
            self.assertFalse(re.match(r"\s*(COPY|ADD)\b", line), line)

    def test_dockerignore_excludes_everything(self):
        rules = [x.strip() for x in read(".dockerignore").splitlines() if x.strip() and not x.startswith("#")]
        self.assertEqual(rules, ["*"])


class GatePins(unittest.TestCase):
    def rows(self):
        out = {}
        for line in read("tools/swiss-layout.tsv").splitlines():
            if line and not line.startswith("#"):
                f = line.split("\t")
                out[f[0]] = f
        return out

    def test_the_two_reproduced_images_are_the_pinned_ones(self):
        r = self.rows()
        self.assertEqual(r["28"][1:3], ["vehicle", "gbp-play-gba"])
        self.assertEqual(r["28"][7], VEHICLE_PIN)
        self.assertEqual(r["27"][1:3], ["gbmode", "gbp-video-stream-probe"])
        self.assertEqual(r["27"][7], GBMODE_PIN)


class Records(unittest.TestCase):
    def test_devlog_entry_exists_once_and_carries_the_identities(self):
        d = read(DEVLOG)
        self.assertEqual(d.count(DEVLOG_HEAD), 1)
        entry = d[d.index(DEVLOG_HEAD):]
        for must in (IMAGE_ID, DIGEST, VEHICLE_PIN, GBMODE_PIN, "6396851", "4d6fe06", "podman compose", "keep-id", ".dockerignore", "EQUAL"):
            self.assertIn(must, entry, must)
        self.assertEqual(entry.count("EQUAL"), 2, "exactly the two reproductions are recorded as equal")
        self.assertNotIn("MISMATCH", entry)

    def test_handoff_paragraphs_lead_their_sections(self):
        h = read(HANDOFF)
        for heading, para in (("## Current blocker / current question\n\n", HANDOFF_BLOCKER), ("## Next safe action\n\n", HANDOFF_NEXT)):
            self.assertEqual(h.count(heading), 1)
            self.assertTrue(h.split(heading)[1].startswith(para), heading)
        self.assertIn("ba9cd72a4bd0", h)
        self.assertIn(DIGEST, h)

    def _only_insertions(self, rel):
        try:
            old = guards.show(BASE, rel)
        except Exception:
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE)
        old = old.decode("utf-8") if isinstance(old, bytes) else old
        removed = [x for x in difflib.unified_diff(old.splitlines(), read(rel).splitlines(), lineterm="", n=0)
                   if x.startswith("-") and not x.startswith("---")]
        self.assertEqual(removed, [], "%s lost or changed lines of the base %s" % (rel, BASE))

    def test_devlog_and_handoff_only_gained_text(self):
        self._only_insertions(DEVLOG)
        self._only_insertions(HANDOFF)


if __name__ == "__main__":
    unittest.main()
