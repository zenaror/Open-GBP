"""
tests/host/test_make_audit_deps.py — F3 (HARDWARE_TESTS §V5.59): the audit
targets of the top-level Makefile declare what they consume.

Before this round `make <x>-audit` disassembled whatever objects happened to be
in build/ (a `test -d obj` check was the only guard) and the stream / colour /
vstate audits compared their handler reports against the GBP-VIDEO-001 files
that ONLY `make video-audit` produced — so `stream-audit` had to be preceded by
`video-audit` by hand or it reported DIFFERENT against a stale or absent file.

Everything here runs `make -n` / `make -pn` (dry runs: nothing is built, no
container starts) against the real Makefile, so it fails the moment a target
goes back to consuming a file it does not depend on.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAKEFILE = os.path.join(ROOT, "Makefile")
VIDEO = "build/poc/gbp-video-capture-probe"
STREAM = "build/poc/gbp-video-stream-probe"
AUDITED = {
    "gbp-init-irq-program-probe": "003a", "gbp-init-irq-deliver-probe": "003b",
    "gbp-init-irq-service-probe": "004", "gbp-av-service-probe": "avsvc",
    "gbp-video-capture-probe": "video", "gbp-video-state-probe": "vstate",
    "gbp-video-color-probe": "color", "gbp-video-stream-probe": "stream",
}
COMPARING = {"stream-audit": STREAM, "color-audit": "build/poc/gbp-video-color-probe",
             "vstate-audit": "build/poc/gbp-video-state-probe"}
_C = {}


def make(*args):
    r = subprocess.run(["make", "-C", ROOT] + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def database():
    """{target: (prerequisites, recipe lines)} from `make -pn`."""
    if "db" not in _C:
        rc, out, err = make("-pn", "stream-audit")
        rules, cur = {}, None
        for line in out.splitlines():
            if line.startswith("\t") and cur:
                rules[cur][1].append(line.strip())
                continue
            if line.startswith("#"):
                continue                      # make -p annotates a rule with comment lines before its recipe
            m = re.match(r"^([^#\s][^:=]*?):(?!=)\s*(.*)$", line)
            if m:
                cur = m.group(1).strip()
                rules[cur] = (m.group(2).split(), [])
            elif not line.startswith("\t"):
                cur = None
        _C["db"] = rules
    return _C["db"]


def closure(target, db, seen=None):
    seen = set() if seen is None else seen
    for p in db.get(target, ([], []))[0]:
        if p not in seen:
            seen.add(p)
            closure(p, db, seen)
    return seen


def read_makefile():
    with open(MAKEFILE, encoding="utf-8") as f:
        return f.read()


class TheReferenceIsAPrerequisite(unittest.TestCase):
    def test_every_comparing_audit_depends_on_both_video_reports(self):
        db = database()
        for tgt in COMPARING:
            pre = db[tgt][0]
            self.assertIn(VIDEO + "/isr-audit-ext.txt", pre, tgt)
            self.assertIn(VIDEO + "/isr-audit-base.txt", pre, tgt)

    def test_no_audit_compares_a_file_it_does_not_depend_on(self):
        db = database()
        for tgt in COMPARING:
            deps = closure(tgt, db)
            for line in db[tgt][1]:
                for path in re.findall(r"build/poc/\S+?\.txt", line):
                    self.assertIn(path, deps, "%s compares %s without depending on it" % (tgt, path))

    def test_stream_audit_alone_builds_the_video_reference(self):
        """`make video-audit first` is gone: when the reference is out of date, the
        stream audit's own dry run contains the recipe that produces it."""
        rc, out, _ = make("-n", "-W", VIDEO + "/gbp-video-capture-probe.elf", "stream-audit")
        self.assertEqual(rc, 0, out)
        self.assertIn("tools/audit_listings.sh %s gbp-video-capture-probe" % VIDEO, out)
        self.assertIn("--symbol hsp_backend_oneshot_isr_ext --report %s/isr-audit-ext.txt" % VIDEO, out)
        self.assertIn("--symbol hsp_backend_oneshot_isr --report %s/isr-audit-base.txt" % VIDEO, out)
        # and the comparison comes AFTER the reference in the dry run
        self.assertLess(out.index("--report %s/isr-audit-base.txt" % VIDEO), out.index("cmp -s"))


class StaleObjectsAreRebuiltNotAudited(unittest.TestCase):
    def test_reports_are_file_targets_rooted_in_the_elf_and_the_sources(self):
        db = database()
        for poc, _profile in AUDITED.items():
            out = "build/poc/" + poc
            self.assertIn(out + "/" + poc + ".elf", db[out + "/audit/elf.nm.txt"][0], poc)
            self.assertIn("tools/audit_listings.sh", db[out + "/audit/elf.nm.txt"][0], poc)
            elf_pre = db[out + "/" + poc + ".elf"][0]
            self.assertIn("poc/%s/Makefile" % poc, elf_pre, poc)
            self.assertTrue(any(p.startswith("poc/%s/source/" % poc) for p in elf_pre), poc)
            self.assertIn("src/gbp/gbp_vwitness.c", elf_pre, poc)
            self.assertIn(out + "/audit/elf.nm.txt", db[out + "/poc-audit.txt"][0], poc)
            self.assertIn("tools/poc_audit.py", db[out + "/poc-audit.txt"][0], poc)

    def test_a_newer_poc_source_forces_the_container_build_before_the_audit(self):
        rc, out, _ = make("-n", "-W", "poc/gbp-video-stream-probe/source/main.c", "stream-audit")
        self.assertEqual(rc, 0, out)
        i = out.index("make --no-print-directory -C poc/gbp-video-stream-probe")
        j = out.index("tools/audit_listings.sh %s gbp-video-stream-probe" % STREAM)
        k = out.index("tools/poc_audit.py %s/audit --profile stream" % STREAM)
        self.assertLess(i, j)
        self.assertLess(j, k)

    def test_a_newer_shared_source_forces_the_rebuild_too(self):
        rc, out, _ = make("-n", "-W", "src/gbp/gbp_vwitness.c", "vstate-audit")
        self.assertEqual(rc, 0, out)
        self.assertIn("make --no-print-directory -C poc/gbp-video-state-probe", out)
        self.assertIn("tools/audit_listings.sh build/poc/gbp-video-state-probe gbp-video-state-probe", out)

    def test_a_newer_audit_tool_reruns_the_audit_but_not_the_build(self):
        # `-o` pins the ELF as up to date so the answer does not depend on the state of build/
        rc, out, _ = make("-n", "-W", "tools/poc_audit.py",
                          "-o", "build/poc/gbp-init-irq-program-probe/gbp-init-irq-program-probe.elf", "initirqa-audit")
        self.assertEqual(rc, 0, out)
        self.assertIn("tools/poc_audit.py build/poc/gbp-init-irq-program-probe/audit --profile 003a", out)
        self.assertNotIn("make --no-print-directory -C poc/", out)


class NothingIsSilent(unittest.TestCase):
    def test_no_audit_target_relies_on_a_test_f_check_or_asks_to_run_build_first(self):
        text = read_makefile()
        for m in re.finditer(r"^([a-z0-9]+-audit):[^\n]*\n((?:\t[^\n]*\n)*)", text, re.M):
            self.assertNotRegex(m.group(2), r"test -[fd] ", m.group(1))
            self.assertNotIn("run make build", m.group(2), m.group(1))
        self.assertNotIn("video-audit first", text.replace("no longer a thing", ""))

    def test_a_failing_recipe_leaves_no_half_written_report(self):
        self.assertIsNotNone(re.search(r"^\.DELETE_ON_ERROR:\s*$", read_makefile(), re.M))

    def test_the_listing_script_produces_both_listings_and_refuses_an_unbuilt_poc(self):
        with open(os.path.join(ROOT, "tools", "audit_listings.sh"), encoding="utf-8") as f:
            sh = f.read()
        self.assertIn("powerpc-eabi-objdump -dr", sh)
        self.assertIn("powerpc-eabi-objdump -r ", sh)
        self.assertIn("powerpc-eabi-nm", sh)
        self.assertIn("set -eu", sh)
        self.assertIn("exit 1", sh)

    def test_the_vstate_comparison_fails_on_a_difference_like_the_others(self):
        db = database()
        for tgt in COMPARING:
            recipe = "\n".join(db[tgt][1])
            self.assertIn('DIFFERENT"; exit 1', recipe, tgt)
            self.assertNotRegex(recipe, r"^diff ", tgt)


if __name__ == "__main__":
    unittest.main()
