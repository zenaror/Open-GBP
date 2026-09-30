"""
tests/host/test_gbmode_image.py -- GitHub Issue #146 (Phase 7's E3): THE ONE-VARIABLE CLAIM of the GB-mode session image, checked
where it can be checked. The image is the stream-0015 POC, UNCHANGED, built at a later commit under its own build id (`make
gbmode-session`); what can differ from the physically executed stream-0015 (commit da06500) is what the SHARED sources under src/
gained since. This file pins:

  1. the POC itself: main.c byte-identical to da06500's, the Makefile identical to what Issue #87 left, and the image built by the
     root Makefile's variant target, which edits and copies nothing;
  2. THE DRIFT INVENTORY: which sources the POC links, and exactly which of them differ from da06500's -- four .c files -- and why;
  3. that the additive hooks of those files sit behind config members the POC never sets (grep, and reachability by name);
  4. A DIFFERENTIAL RUN. The vstate probe of da06500's own tree and of the candidate's, both run through the mock's synthetic
     device with the same GBA-mode scenario, produce the SAME device operation stream, the same log, the same result; and with the
     device holding CONTROL bit 0x01 the old tree aborts at PREUNMASK while the new one proceeds with the SAME operation stream the GBA
     scenario made. That is the claim "the only behavioural change is Issue #145's policy", as a comparison and not a sentence;
  5. that nothing was staged: no slot row, no pin.

WHICH TREE. Before the candidate is built the tree is the working tree; once HARDWARE_TESTS section V29 records the candidate
(`CANDIDATE_COMMIT=<sha>`), every comparison here uses THAT commit, so later checkpoints that touch shared sources cannot move a
pinned candidate's claim (images reproduce at their own commit, HARDWARE_TESTS 23.9).
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import guards
import hostcc

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STREAM_COMMIT = "da06500"           # stream-0015 as physically executed (RUN 16-18, 23, 24, 27-29)
AWIN_LINK_COMMIT = "0da719d"        # Issue #87: the last commit that touched the POC (it links gbp_awin.c again)
POC = "poc/gbp-video-stream-probe"
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def git(*args, check=True):
    return subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, text=True, check=check).stdout


def candidate_commit():
    m = re.search(r"^CANDIDATE_COMMIT=([0-9a-f]{7,40})\s*$", read(HW), re.M)
    return m.group(1) if m else None


def need_base(tc):
    if not guards.base_available(STREAM_COMMIT):
        tc.skipTest("the base commit is not in this checkout")


def ref():
    """The commit the comparisons use, or "HEAD" for the record-less stage; the WORKING TREE is used wherever `cand()` is None."""
    return candidate_commit() or "HEAD"


def cand():
    return candidate_commit()


def show(path, at=None):
    """A file's text: at a commit, or (no candidate recorded yet, at=None) from the WORKING TREE, so an uncommitted change is seen."""
    at = at or cand()
    if at:
        return git("show", "%s:%s" % (at, path))
    return read(os.path.join(ROOT, path))


def has(path, at=None):
    at = at or cand()
    if at:
        return subprocess.run(["git", "-C", ROOT, "cat-file", "-e", "%s:%s" % (at, path)], capture_output=True).returncode == 0
    return os.path.exists(os.path.join(ROOT, path))


def diff_since_stream(path):
    """`git diff da06500 [candidate] -- path`: with no candidate, against the WORKING TREE."""
    c = cand()
    return git("diff", STREAM_COMMIT, c, "--", path) if c else git("diff", STREAM_COMMIT, "--", path)


def numstat_since_stream(path):
    c = cand()
    out = git("diff", "--numstat", STREAM_COMMIT, c, "--", path) if c else git("diff", "--numstat", STREAM_COMMIT, "--", path)
    a, r, _ = out.split()
    return int(a), int(r)


def stream_srcs():
    m = re.search(r"^SRCS\s*:=\s*(.*)$", show("%s/Makefile" % POC), re.M)
    return [w for w in m.group(1).split() if w != "main.c"]


SRC_DIRS = ("src/gbp", "src/common", "src/log", "src/platform")


def find_src(name, at=None):
    """Path of a linked source or header at a commit (`at`), or in the candidate / working tree when `at` is None."""
    for d in SRC_DIRS:
        p = os.path.normpath("%s/%s" % (d, name))          # main.c writes "../log/ringlog.h": git wants the normalised path
        if has(p, at):
            return p
    return None


def include_closure(roots, at=None):
    """Every project file (.c and .h) reachable from `roots` by `#include "..."`, at a commit or in the candidate / working tree."""
    seen, todo = {}, list(roots)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        p = find_src(name, at)
        seen[name] = p
        if p is None:
            continue
        text = show(p, at)
        text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
        todo.extend(m for m in re.findall(r'^\s*#\s*include\s+"([^"]+)"', text, re.M) if m not in seen)
    return seen


class ThePocIsNotEdited(unittest.TestCase):
    def test_main_c_is_byte_identical_to_stream_0015s(self):
        need_base(self)
        self.assertEqual(git("show", "%s:%s/source/main.c" % (STREAM_COMMIT, POC)), show("%s/source/main.c" % POC),
                         "the stream POC's main.c moved: the image is no longer stream-0015's program")

    def test_the_makefile_is_what_issue_87_left_and_nothing_since(self):
        need_base(self)
        moved = git("diff", AWIN_LINK_COMMIT, cand(), "--", POC) if cand() else git("diff", AWIN_LINK_COMMIT, "--", POC)
        self.assertEqual(moved, "", "the stream POC moved since Issue #87: the one-variable claim needs re-reading")
        d = git("diff", STREAM_COMMIT, AWIN_LINK_COMMIT, "--", "%s/Makefile" % POC)
        added = [l[1:] for l in d.split("\n") if l.startswith("+") and not l.startswith("+++")]
        self.assertTrue(any("gbp_awin.c" in l and l.startswith("SRCS") for l in added), "Issue #87's change is the awin link")

    def test_the_root_makefile_builds_the_variant_without_editing_or_copying_a_poc(self):
        mk = read(os.path.join(ROOT, "Makefile"))
        i = mk.index("gbmode-session:\n")
        rule = mk[i:mk.index("\n\n", i)]
        self.assertIn("-C poc/gbp-video-stream-probe", rule)
        self.assertIn("BUILD_ID=$(GBMODE_BUILD_ID)", rule)
        self.assertIn('OUTDIR="$$PWD/$(GBMODE_OUT)"', rule)
        self.assertIn("GBMODE_BUILD_ID ?= gbmode-0001", mk)
        self.assertNotIn("GIT_DIRTY=", rule)          # the identity comes from IN_CONTAINER, as for every other image
        self.assertFalse(os.path.exists(os.path.join(ROOT, "poc", "gbp-gbmode-probe")), "a copied POC would carry a second main.c")
        # dry run: one docker build of the stream POC with a new build id and a new out dir, nothing else
        r = subprocess.run(["make", "-n", "-C", ROOT, "gbmode-session"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("BUILD_ID=gbmode-0001", r.stdout)
        self.assertIn("build/poc/gbp-video-stream-probe-gbmode", r.stdout)
        self.assertEqual(r.stdout.count("make --no-print-directory -C poc/"), 1)

    def test_nothing_is_staged_or_pinned(self):
        layout = read(os.path.join(ROOT, "tools", "swiss-layout.tsv"))
        self.assertNotIn("gbmode", layout)
        self.assertIsNone(re.search(r"^27\t", layout, re.M), "slot 27 is reserved, not assigned: staging waits for RUN 58 and the Orchestrator")


class TheDriftInventory(unittest.TestCase):
    """What the shared sources gained since da06500, for the sources this POC LINKS -- the .c files AND the headers they include."""

    CHANGED_C = {"gbp_initirqa_probe.c": "CHANGED", "gbp_irq_service.c": "CHANGED", "gbp_vstate_probe.c": "CHANGED", "gbp_awin.c": "NEW"}
    # every header in the include closure of the linked sources that is new or differs from da06500's
    CHANGED_H = {"gbp_vstate_probe.h": "CHANGED", "gbp_initirqa_probe.h": "CHANGED", "gbp_control_policy.h": "NEW", "gbp_awin.h": "NEW"}
    # (lines added, lines removed) since da06500: a further edit of any of these files moves the count and must be declared here
    NUMSTAT = {"gbp_initirqa_probe.c": (26, 1), "gbp_irq_service.c": (6, 3), "gbp_vstate_probe.c": (62, 6), "gbp_awin.c": (186, 0)}
    # the ONLY lines of gbp_vstate_probe.c that stopped existing: the two CONTROL comparisons (Issue #145), the status name of the session-end
    # class (Issue #39) and the three uses of cfg->audio_len that the local `alen` replaced (Issue #84)
    VSTATE_REMOVED = [
        'case GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE: return "ok";',
        "if (s->control_rc == GBP_OK && (s->control_vote != res->a.control_exp || s->control_vote != s->control_b1f)) res->control_ok = 0;",
        "if (s->control_vote != res->a.control_exp || s->control_vote != s->control_b1f) {",
        'gbp_avblock_init(&res->audio, "audio", cfg->audio_index, cfg->audio_src, buf, GBP_VSTATE_AUDIO_BLOCK_SIZE, cfg->audio_len);',
        "gbp_vstate_audio_commit(st, slot, res->audio.completed, res->audio.completed ? cfg->audio_len : 0u, n);",
        "if (res->audio.completed) res->bytes_audio += cfg->audio_len;",
    ]

    def test_exactly_four_linked_c_files_differ_and_each_is_accounted_for(self):
        need_base(self)
        changed = {}
        for name in stream_srcs():
            new = find_src(name)
            old = find_src(name, STREAM_COMMIT)
            if new is None:
                self.fail("%s is in the POC's SRCS but not in the tree" % name)
            if old is None:
                changed[name] = "NEW"
            elif diff_since_stream(new) != "":
                changed[name] = "CHANGED"
        self.assertEqual(changed, self.CHANGED_C, "a linked source moved since stream-0015: declare it here with its Issue, and read the claim again")

    def test_the_headers_of_the_include_closure_are_inventoried_too(self):
        """A constant in a header (a target, a store size, a default) changes the image as surely as a .c line does."""
        need_base(self)
        roots = stream_srcs()
        new = include_closure(roots)
        old = include_closure([r for r in roots if find_src(r, STREAM_COMMIT)], STREAM_COMMIT)
        changed = {}
        for name, path in new.items():
            if not name.endswith(".h") or path is None:
                continue
            if name not in old or old[name] is None:
                changed[name] = "NEW"
            elif show(path) != show(old[name], STREAM_COMMIT):
                changed[name] = "CHANGED"
        # the POC's own main.c includes are covered by the same closure through its header list
        main_h = {m for m in re.findall(r'^\s*#\s*include\s+"([^"]+)"', show("%s/source/main.c" % POC), re.M)}
        for h in main_h:
            self.assertIsNotNone(find_src(h), "main.c includes %s and the tree does not have it" % h)
        for h, p in include_closure(sorted(main_h)).items():
            if p is None or not h.endswith(".h"):
                continue
            o = find_src(h, STREAM_COMMIT)
            if o is None:
                changed[h] = "NEW"
            elif show(p) != show(o, STREAM_COMMIT):
                changed[h] = "CHANGED"
        self.assertEqual(changed, self.CHANGED_H, "a header the image includes moved since stream-0015: declare it here with its Issue")

    def test_the_size_of_each_change_is_pinned(self):
        need_base(self)
        for name, want in self.NUMSTAT.items():
            self.assertEqual(numstat_since_stream(find_src(name)), want, "%s changed by a different number of lines than declared" % name)

    def test_why_each_one_moved(self):
        need_base(self)
        # gbp_irq_service.c: Issue #145 only (its exact lines are pinned by test_awin_image.py)
        for l in diff_since_stream("src/gbp/gbp_irq_service.c").split("\n"):
            if (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---")):
                self.assertTrue("control" in l.lower() or "Issue #145" in l, "gbp_irq_service.c changed for a reason other than Issue #145: %s" % l)
        # gbp_initirqa_probe.c: Issue #145 only (the policy, the tolerance record, the restore read-back)
        d = diff_since_stream("src/gbp/gbp_initirqa_probe.c")
        removed = [l[1:].strip() for l in d.split("\n") if l.startswith("-") and not l.startswith("---")]
        self.assertEqual(removed, ["res->control_restore_vote == res->control_orig) ? 1 : 0;"])
        # gbp_vstate_probe.c: Issue #145 (two comparisons) + the hooks of Issues #39, #59, #84 and #101 -- and the removed lines are EXACTLY these
        d = diff_since_stream("src/gbp/gbp_vstate_probe.c")
        removed = [l[1:].strip() for l in d.split("\n") if l.startswith("-") and not l.startswith("---")]
        self.assertEqual(removed, self.VSTATE_REMOVED, "gbp_vstate_probe.c lost a line that is not on the declared list: an existing behaviour moved")
        added = "\n".join(l[1:] for l in d.split("\n") if l.startswith("+") and not l.startswith("+++"))
        for tag in ("Issue #39", "Issue #59", "Issue #84", "Issue #101", "Issue #145"):
            self.assertIn(tag, added)
        for hook in ("cfg->session_end && *cfg->session_end", "if (cfg->awin) {", "cfg->audio_len_live ? *cfg->audio_len_live : cfg->audio_len",
                     "if (cfg->audio_tap)", "if (cfg->video_tap)"):
            self.assertIn(hook, added, "the hook %r is not in the diff: the inventory is stale" % hook)

    def test_the_pocs_main_never_sets_the_members_that_gate_every_hook(self):
        main = show("%s/source/main.c" % POC)
        for member in ("awin", "audio_tap", "video_tap", "session_end", "audio_len_live", "audio_tap_user", "video_tap_user"):
            self.assertIsNone(re.search(r"\bcfg\.%s\b|\bcfg->%s\b" % (member, member), main),
                              "the stream POC sets cfg.%s: a hook that was inert is now armed" % member)
        # the members are zero because the config's default is a memset: pin that the default leaves them NULL
        c = show("src/gbp/gbp_vstate_probe.c")
        i = c.index("void gbp_vstate_config_default(")
        body = c[i:c.index("\n}\n", i)]
        self.assertIn("memset(cfg, 0, sizeof *cfg)", body)
        for member in ("awin", "audio_tap", "video_tap", "session_end", "audio_len_live"):
            self.assertNotRegex(body, r"cfg->%s\s*=\s*[^0;]" % member)


class TheDeviceOperationStreamIsTheSame(unittest.TestCase):
    """4: the differential run."""

    @classmethod
    def setUpClass(cls):
        cls.err = None
        if not guards.base_available(STREAM_COMMIT):
            cls.err = "the base commit is not in this checkout"
            return
        cls.tmp = tempfile.mkdtemp(prefix="gbmode-")
        old = os.path.join(cls.tmp, "old")
        os.makedirs(old)
        subprocess.run("git -C '%s' archive %s src tests/mocks | tar -x -C '%s'" % (ROOT, STREAM_COMMIT, old), shell=True, check=True)
        cand = ref()
        if cand == "HEAD":
            new = ROOT
        else:
            new = os.path.join(cls.tmp, "new")
            os.makedirs(new)
            subprocess.run("git -C '%s' archive %s src tests/mocks | tar -x -C '%s'" % (ROOT, cand, new), shell=True, check=True)
        cls.bins = {}
        mk = read(os.path.join(ROOT, "tests", "unit", "Makefile"))

        def var(root, n):
            m = re.search(r"^%s\s*:=\s*(.*)$" % n, mk, re.M)
            return [w.replace("$(ROOT)", root) for w in m.group(1).split()]
        for label, root in (("old", old), ("new", new)):
            srcs = [s for s in var(root, "LOG_SRC") + var(root, "GBP_SRC") + var(root, "MOCK_SRC") if os.path.exists(s)]
            inc = ["-I" + os.path.join(root, d) for d in ("src/common", "src/log", "src/gbp", "src/audio", "tests/mocks")]
            out = os.path.join(cls.tmp, "optrace-" + label)
            have, ok, err = hostcc.compile_c(["-std=gnu11", "-O1", "-w"] + inc + ["-o", out, os.path.join(ROOT, "tests", "host", "gbmode_optrace.c")] + srcs)
            cls.have, cls.ok, cls.cerr = have, ok, err
            if not (have and ok):
                return
            cls.bins[label] = out

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "tmp", None):
            shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_bin(self, label, scenario):
        if self.err:
            self.skipTest("the base commit is not in this checkout")      # the only cause setUpClass records
        hostcc.require(self, self.have, self.ok, self.cerr, "the op-trace driver")
        r = subprocess.run([self.bins[label], scenario], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.split("\n")
        return ([l for l in lines if l.startswith("OP ")], [l for l in lines if l.startswith("LOG ")],
                [l for l in lines if l.startswith("RESULT ")])

    def test_the_gba_scenario_makes_the_same_operations_writes_the_same_log_and_ends_the_same(self):
        o_ops, o_log, o_res = self.run_bin("old", "gba")
        n_ops, n_log, n_res = self.run_bin("new", "gba")
        self.assertGreater(len(o_ops), 1000)
        self.assertEqual(o_ops, n_ops, "the device operation stream moved in a GBA-mode run")
        self.assertEqual(o_log, n_log, "a log line moved in a GBA-mode run")
        self.assertEqual(o_res, n_res)
        self.assertIn("status=ok_no_change_nominal_interval", n_res[0])

    def test_with_bit_0x01_held_the_old_tree_aborts_at_preunmask_and_the_new_one_makes_the_gba_operation_stream(self):
        o_ops, o_log, o_res = self.run_bin("old", "gb")
        n_ops, n_log, n_res = self.run_bin("new", "gb")
        g_ops, _g_log, _g_res = self.run_bin("new", "gba")
        self.assertIn("status=anomaly_control_changed", o_res[0])
        self.assertTrue(any("PREUNMASK ok=0 reason=control_changed" in l for l in o_log))
        self.assertLess(len(o_ops), 100)
        self.assertIn("status=ok_no_change_nominal_interval", n_res[0])
        self.assertFalse(any("PREUNMASK ok=0" in l for l in n_log))
        # THE POINT: with the bit held, the candidate makes exactly the operations it makes without it -- the policy adds no operation.
        # What a READ returns is the device's business (it returns 0x8d where the GBA run returns 0x8c); everything the RUNTIME does --
        # the kind, the address, the length, the result, and the bytes of every WRITE -- must be equal.
        self.assertEqual(self.runtime_side(n_ops), self.runtime_side(g_ops),
                         "the tolerated run's operation stream differs from the GBA run's: the policy is not the only variable")
        self.assertGreater(len(n_ops), 3000)

    READ_KINDS = {"0", "2", "14"}         # MOCK_AR_R, MOCK_RD, MOCK_RD_BULK

    def runtime_side(self, ops):
        out = []
        for l in ops:
            f = l.split()
            out.append(tuple(f[:6]) if f[1] not in self.READ_KINDS else tuple(f[:5]))
        return out


if __name__ == "__main__":
    unittest.main()
