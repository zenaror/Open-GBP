"""
tests/host/test_control_policy_replay.py -- GitHub Issue #145 (Phase 7's E2): the CONTROL comparison ignores bit 0x01
and nothing else. The gates of the Issue that a unit test cannot carry:

  (a) THE GBA ARCHIVE IS UNCHANGED. Every archived log that carries the snapshot records is replayed through the REAL
      check (tests/unit/test_gbp_control_policy --verdicts): every verdict is identical to the pre-policy one, and the
      PREUNMASK / restore verdicts equal the ones the hardware logged. A GBA log whose SEMANTIC reading (the majority vote,
      and byte 0x1F) has bit 0x01 set anywhere would be a FINDING, and the test says so instead of passing.
      A FINDING ABOUT THE RAW BLOCKS, recorded here because the Issue's words were wider: the raw 32-byte CONTROL blocks in
      the archive DO carry bit 0x01 in places -- byte 0 of the block in 18 GBA logs (the block's first byte is not the
      semantic value) and isolated other bytes in 7 GBA logs (10 raw bytes; found by the reviewer, recounted here) -- while
      the vote and byte 0x1F are clean in every one of them, so no guarded value differed. The gate reads the semantic
      readings because those are what the guards compare.
  (c) THE FOUR GB BOOTS (RUN 24, 27, 28, 29), replayed at the snapshots their logs record, now pass PREUNMASK's CONTROL
      clause and every other clause the logged fields let the real function evaluate. THE LOGS STOP AT THE ABORT: nothing
      past PREUNMASK is claimed, and the test asserts that no service record exists in them.
  (d) A GATE THAT CAN SAY NO. The pure C test is compiled against two MUTANTS of the policy header (a tolerance of
      nothing; a tolerance of two bits) and must FAIL on both: a test that agrees with any policy is not a test.
  (e) STRUCTURAL. The masked comparison is REACHED from each probe family's entry, by a walk over the call graph (not a
      token search), and no reachable function still compares the CONTROL vote for equality.

The archive half needs captures/local (ignored by Git) and skips, with the registered phrase, on a host without it.
"""
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

import hostcc
from test_v28_plans import strip_for_calls, function_defs, reachable_functions

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL = os.path.join(ROOT, "captures", "local")
UNIT = os.path.join(ROOT, "tests", "unit")
DRIVER_SRC = os.path.join(UNIT, "test_gbp_control_policy.c")

GB_RUNS = ["GBP-VIDEO-004_stream-0015-run24.log", "GBP-VIDEO-004_stream-0015-run27.log",
           "GBP-VIDEO-004_stream-0015-run28.log", "GBP-VIDEO-004_stream-0015-run29.log"]
# Issue #147: RUN 59 (gbmode-0001) is the first GB-mode session run under the E2 policy: its CONTROL snapshots carry bit 0x01, so the pre-policy verdict differs by design.
# It is named apart, not swept into GB_RUNS (those four aborted at PREUNMASK; this one did not).
GB_SESSION_RUN = "GBP-VIDEO-004_gbmode-0001-run59.log"
GB_SESSION_RUNS = (GB_SESSION_RUN, "GBP-VIDEO-004_gbmode-0001-run60.log")     # Issue #152: RUN 60 is the same image, a second boot


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def makefile_sources(root):
    """The unit Makefile's own source lists, so the driver is built from exactly what the suite builds."""
    mk = read(os.path.join(root, "tests", "unit", "Makefile"))

    def var(name):
        m = re.search(r"^%s\s*:=\s*(.*)$" % name, mk, re.M)
        return [w.replace("$(ROOT)", root) for w in m.group(1).split()]
    return var("LOG_SRC") + var("GBP_SRC") + var("MOCK_SRC")


def gcc_args(root, out):
    inc = ["-I" + os.path.join(root, d) for d in ("src/common", "src/log", "src/gbp", "src/audio", "tests/mocks")]
    return ["-std=gnu11", "-O1", "-w"] + inc + ["-o", out, os.path.join(root, "tests", "unit", "test_gbp_control_policy.c")] \
        + makefile_sources(root)


_DRIVER = {}


def driver():
    """Build (once) the real test binary from the tree; skip with no compiler, FAIL when the compiler refuses."""
    if "bin" not in _DRIVER:
        out = os.path.join(tempfile.mkdtemp(prefix="cpol-"), "test_gbp_control_policy")
        have, ok, err = hostcc.compile_c(gcc_args(ROOT, out))
        _DRIVER["r"] = (have, ok, err)
        _DRIVER["bin"] = out
    return _DRIVER["bin"], _DRIVER["r"]


def run_driver(lines):
    out, (have, ok, err) = driver()
    hostcc.require_here(have, ok, err, "tests/unit/test_gbp_control_policy.c")
    r = subprocess.run([out, "--verdicts"], input="\n".join(lines) + "\n", capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip().split("\n") if lines else []


# ---- the log records ----------------------------------------------------------------------------------------------
RE_SEM = re.compile(r"CONTROL semantic orig=([0-9a-f]+) exp=([0-9a-f]+)")
RE_RAW = re.compile(r"\bRAW (\S+) idx=4 .*?sem_vote=([0-9a-f]+) sem_b1f=([0-9a-f]+)")
RE_PRE = re.compile(r"\bPREUNMASK ok=(\d) reason=(\S+) intsr13=(\d),(\d) intmr13=(\d),(\d) control=([0-9a-f]+) "
                    r"irq=([0-9a-f]+)/([0-9a-f]+) src=([0-9a-f]+) odd=([0-9a-f]+) bit15=(\d)")
RE_RST = re.compile(r"CONTROL restore semantic=([0-9a-f]+) rc=(\S+) readback_rc=(\S+) readback_vote=([0-9a-f]+) "
                    r"readback_b1f=([0-9a-f]+) ok=(\d)")


def parse_log(path):
    """{orig, exp, snaps: [(tag, vote, b1f)] after the transform write, pre: (line fields, last RAW b1f), restore}."""
    rec = {"orig": None, "exp": None, "snaps": [], "pre": None, "restore": None, "service": False, "written": False}
    last_b1f = None
    for line in read(path).split("\n"):
        if " CTLW tag=EXP " in line:
            rec["written"] = True
        m = RE_SEM.search(line)
        if m and rec["orig"] is None:
            rec["orig"], rec["exp"] = int(m.group(1), 16), int(m.group(2), 16)
            continue
        m = RE_RAW.search(line)
        if m and rec["written"]:
            rec["snaps"].append((m.group(1), int(m.group(2), 16), int(m.group(3), 16)))
            last_b1f = int(m.group(3), 16)
            continue
        m = RE_PRE.search(line)
        if m and rec["pre"] is None:
            rec["pre"] = (m.groups(), last_b1f)
            continue
        m = RE_RST.search(line)
        if m and rec["restore"] is None:
            rec["restore"] = (int(m.group(1), 16), int(m.group(4), 16), int(m.group(5), 16), int(m.group(6)))
            continue
        if re.search(r"\b(PRESVC|POSTDRAIN|POSTACK|REARMPOST|SERVICE) ", line):
            rec["service"] = True
    return rec


def archive():
    if not os.path.isdir(LOCAL) or not glob.glob(os.path.join(LOCAL, "*.log")):
        raise unittest.SkipTest("no local archive on this host (captures/local is ignored)")
    return sorted(glob.glob(os.path.join(LOCAL, "*.log")))


class TheGbaArchiveIsUnchanged(unittest.TestCase):
    """(a)"""

    def test_every_verdict_is_the_pre_policy_verdict(self):
        logs = archive()
        seen_logs = seen_snaps = seen_pre = seen_rst = 0
        findings = []
        for p in logs:
            name = os.path.basename(p)
            if name in GB_RUNS or name in GB_SESSION_RUNS:
                continue
            rec = parse_log(p)
            if rec["exp"] is None or not rec["snaps"]:
                continue                      # a log without the snapshot records (a sidecar-only or non-probe log)
            seen_logs += 1
            lines = ["snap %x %x %x" % (rec["exp"], v, b) for (_t, v, b) in rec["snaps"]]
            for (tag, v, b), out in zip(rec["snaps"], run_driver(lines)):
                new, old = out.split()
                seen_snaps += 1
                self.assertEqual(new, old, "%s: snapshot %s vote=%02x b1f=%02x exp=%02x: the verdict moved" % (name, tag, v, b, rec["exp"]))
                if v & 0x01:
                    findings.append("%s %s vote=%02x" % (name, tag, v))
            if rec["pre"] is not None:
                (ok, why, i1, i2, m1, m2, ctl, irqg, irqd, _src, _odd, _b15), b1f = rec["pre"]
                if (i1, i2, m1, m2) == ("1", "1", "0", "0") and b1f is not None and why in ("-", "control_changed"):
                    (out,) = run_driver(["pre %x %x %x %x %x" % (rec["exp"], int(ctl, 16), b1f, int(irqd, 16), int(irqg, 16))])
                    seen_pre += 1
                    self.assertEqual(out.split()[0] == "OK", ok == "1", "%s: PREUNMASK verdict moved: %s vs logged ok=%s" % (name, out, ok))
            if rec["restore"] is not None:
                orig, back, _b1f, ok = rec["restore"]
                (out,) = run_driver(["restore %x %x" % (orig, back)])
                new, old = out.split()
                seen_rst += 1
                self.assertEqual(new, old, "%s: restore verdict moved" % name)
                self.assertEqual(new == "1", ok == 1, "%s: restore verdict differs from the logged ok=%d" % (name, ok))
        self.assertGreater(seen_logs, 30, "the archive holds fewer probe logs than expected: %d" % seen_logs)
        self.assertGreater(seen_snaps, 500)
        self.assertGreater(seen_pre, 20)
        self.assertGreater(seen_rst, 20)
        # bit 0x01 in a GBA log would be a FINDING to report, never a pass
        self.assertEqual(findings, [], "FINDING: a GBA log carries CONTROL bit 0x01: %s" % findings[:5])


class TheGbSessionBoot(unittest.TestCase):
    """Issue #147: RUN 59's snapshots, apart from the GBA archive: the bit the device sets is tolerated by the new check and refused by the old one, and nothing else differs."""

    def test_bit_0x01_is_the_only_difference_and_the_new_check_tolerates_it(self):
        archive()
        p = os.path.join(LOCAL, GB_SESSION_RUN)
        self.assertTrue(os.path.exists(p), "%s missing from the archive" % GB_SESSION_RUN)
        rec = parse_log(p)
        self.assertEqual((rec["orig"], rec["exp"]), (0x92, 0x8e))
        tags = [t for (t, _v, _b) in rec["snaps"]]
        window = rec["snaps"][:tags.index("POSTACK-3") + 1]      # through the last service pass, before the teardown's own writes (TDCTL, FINAL)
        outs = [o.split() for o in run_driver(["snap %x %x %x" % (rec["exp"], v, b) for (_t, v, b) in window])]
        for (_t, v, _b) in window:
            self.assertIn(v ^ rec["exp"], (0x00, 0x01))
        self.assertTrue(all(o[0] == "1" for o in outs), "the new check refuses a snapshot before the teardown")
        self.assertTrue(any(o[1] == "0" for o in outs), "the old check never failed: the exemption would be unfounded")
        self.assertTrue(any(v & 0x01 for (_t, v, _b) in window))


class TheFourGbBoots(unittest.TestCase):
    """(c): as far as the logs go, which is the abort."""

    def test_they_pass_the_control_clause_and_the_logs_stop_at_the_abort(self):
        archive()
        for name in GB_RUNS:
            p = os.path.join(LOCAL, name)
            self.assertTrue(os.path.exists(p), "%s missing from the archive" % name)
            rec = parse_log(p)
            self.assertEqual((rec["orig"], rec["exp"]), (0x92, 0x8e), name)
            # the snapshots: bit 0x01 clear before the device sets it, set from then on; the OLD verdict flips, the NEW one never
            tags = [t for (t, _v, _b) in rec["snaps"]]
            self.assertIn("PREUNMASK", tags, name)
            snaps = rec["snaps"][:tags.index("PREUNMASK") + 1]      # the guard's own window: through PREUNMASK, before the teardown
            lines = ["snap %x %x %x" % (rec["exp"], v, b) for (_t, v, b) in snaps]
            outs = [o.split() for o in run_driver(lines)]
            self.assertTrue(any(o[1] == "0" for o in outs), "%s: no snapshot ever failed the old check" % name)
            self.assertTrue(all(o[0] == "1" for o in outs), "%s: the new check refuses a snapshot" % name)
            for (_t, v, b) in snaps:
                self.assertIn(v ^ rec["exp"], (0x00, 0x01), "%s: a snapshot differs in more than bit 0x01" % name)
            # PREUNMASK: logged ok=0 control_changed; every OTHER clause the fields allow the real function to evaluate passes
            (ok, why, i1, i2, m1, m2, ctl, irqg, irqd, _s, _o, _b), b1f = rec["pre"]
            self.assertEqual((ok, why, ctl), ("0", "control_changed", "8f"), name)
            self.assertEqual((i1, i2, m1, m2), ("1", "1", "0", "0"))
            (out,) = run_driver(["pre %x %x %x %x %x" % (rec["exp"], int(ctl, 16), b1f, int(irqd, 16), int(irqg, 16))])
            self.assertEqual(out, "OK -", "%s: PREUNMASK would still refuse: %s" % (name, out))
            # the restore: the read-back holds 0x93 against the original 0x92
            orig, back, _b1f, ok = rec["restore"]
            self.assertEqual((orig, back, ok), (0x92, 0x93, 0), name)
            self.assertEqual(run_driver(["restore %x %x" % (orig, back)]), ["1 0"], name)
            # NOTHING PAST PREUNMASK is claimed: the run itself says no unmask, no delivery and no ack ever happened
            self.assertIn(" COUNTERS unmasks=0 deliveries=0 acks=0 ", read(p), "%s: a service cycle ran; the replay boundary is wrong" % name)
            self.assertFalse(rec["service"], "%s carries a service record: the replay boundary in the amendment is wrong" % name)


# ---- (d) the gate can say no --------------------------------------------------------------------------------------
def build_mutant(tmp, header_patch):
    dst = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(dst, "tests", "unit"))
    shutil.copytree(os.path.join(ROOT, "src"), os.path.join(dst, "src"))
    shutil.copytree(os.path.join(ROOT, "tests", "mocks"), os.path.join(dst, "tests", "mocks"))
    for f in ("Makefile", "test_gbp_control_policy.c"):
        shutil.copy(os.path.join(UNIT, f), os.path.join(dst, "tests", "unit", f))
    hp = os.path.join(dst, "src", "gbp", "gbp_control_policy.h")
    s = read(hp)
    s2 = header_patch(s)
    assert s2 != s, "the mutation did not change the header"
    with open(hp, "w", encoding="utf-8") as f:
        f.write(s2)
    out = os.path.join(tmp, "mutant")
    have, ok, err = hostcc.compile_c(gcc_args(dst, out))
    hostcc.require_here(have, ok, err, "the mutant of the policy header")
    return subprocess.run([out], capture_output=True, text=True)


class TheGateCanSayNo(unittest.TestCase):
    def test_a_strict_and_a_wider_policy_both_fail_the_pure_test(self):
        def strict(s):
            return s.replace("#define GBP_CONTROL_TOLERATED_MASK 0x01u", "#define GBP_CONTROL_TOLERATED_MASK 0x00u")

        def wide(s):
            return s.replace("#define GBP_CONTROL_TOLERATED_MASK 0x01u", "#define GBP_CONTROL_TOLERATED_MASK 0x03u")
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            with ThreadPoolExecutor(2) as ex:
                f1 = ex.submit(build_mutant, t1, strict)
                f2 = ex.submit(build_mutant, t2, wide)
                r1, r2 = f1.result(), f2.result()
        for label, r in (("tolerance of nothing", r1), ("tolerance of two bits", r2)):
            self.assertNotEqual(r.returncode, 0, "the pure test PASSED against %s: it cannot say no" % label)
            self.assertIn("FAIL", r.stderr)


# ---- (e) structural: the masked comparison is reached from the real paths --------------------------------------------
def load_defs():
    """{(file, function): body} over src/gbp, comments/strings/#if 0 stripped. Keyed by file because the static helpers
    (note_control, teardown) exist in several files under one name."""
    per = {}
    srcdir = os.path.join(ROOT, "src", "gbp")
    for f in sorted(glob.glob(os.path.join(srcdir, "*.c")) + glob.glob(os.path.join(srcdir, "*.h"))):
        for name, body in function_defs(strip_for_calls(read(f))).items():
            per[(os.path.basename(f), name)] = body
    return per


def resolve(per, cur_file, ident):
    if (cur_file, ident) in per:
        return [(cur_file, ident)]
    return [k for k in per if k[1] == ident]


def reach(per, root):
    seen, todo = set(), [root]
    while todo:
        k = todo.pop()
        if k in seen or k not in per:
            continue
        seen.add(k)
        for ident in set(re.findall(r"\b[A-Za-z_]\w*\b", per[k])):
            for r in resolve(per, k[0], ident):
                if r not in seen:
                    todo.append(r)
    return seen


ROOTS = {
    "vstate": ("gbp_vstate_probe.c", "gbp_vstate_probe_run"), "avsvc": ("gbp_avsvc_probe.c", "gbp_avsvc_probe_run"),
    "initirq4": ("gbp_initirq4_probe.c", "gbp_initirq4_probe_run"), "initirqb": ("gbp_initirqb_probe.c", "gbp_initirqb_probe_run"),
    "video": ("gbp_video_probe.c", "gbp_video_probe_run"),
}
EARLY = (("gbp_init_probe.c", "gbp_init_probe_run"), ("gbp_init_irq_probe.c", "gbp_initirq_probe_run"))
READING = re.compile(r"control_(?:vote|restore_vote|b1f)\b")


def _operand(text, start, step):
    """The operand of a comparison operator: from `start` in direction `step`, to the first &&, ||, ?, `,` or ; at depth 0, or the
    unmatched bracket that closes it."""
    depth, i, out = 0, start, []
    while 0 <= i < len(text):
        c = text[i]
        if c in ";{}" or (c == "?" and step > 0) or (c == "," and depth == 0):
            break
        if text[i:i + 2] in ("&&", "||") or (step < 0 and text[i - 1:i + 1] in ("&&", "||")):
            break
        if c in "([":
            depth += step
        elif c in ")]":
            depth -= step
        if depth < 0:
            break
        out.append(c)
        i += step
    return "".join(out if step > 0 else reversed(out))


def strict_hits(text):
    """A CONTROL READING (the vote, the byte-0x1F reading, the restore read-back) compared for equality with anything that is not
    another reading: the pre-policy shape, in any of these spellings -- ==/!= against an expected byte, an original byte, a cast, a
    literal; XOR; memcmp; switch. The one legitimate comparison of a reading is with the OTHER reading (vote against byte 0x1F). An
    ALIAS (`v = s->control_vote; v != exp`) is beyond a regex; the functional mutations of the unit tests are the primary gate."""
    hits = []
    for m in re.finditer(r"[!=]=", text):
        if text[m.start() - 1:m.start()] in "<>=!" or text[m.end():m.end() + 1] == "=":
            continue
        left = _operand(text, m.start() - 1, -1)
        right = _operand(text, m.end(), 1)
        if bool(READING.search(left)) != bool(READING.search(right)):
            hits.append((left + m.group(0) + right).strip())
    hits += [m.group(0) for m in re.finditer(r"memcmp\s*\([^;)]*control_(?:vote|restore_vote|b1f)", text)]
    hits += [m.group(0) for m in re.finditer(r"control_(?:vote|restore_vote|b1f)\s*\^|\^\s*[^;]*control_(?:vote|restore_vote|b1f)\b", text)]
    hits += [m.group(0) for m in re.finditer(r"switch\s*\([^)]*control_(?:vote|restore_vote|b1f)", text)]
    return hits


class TheMaskedComparisonIsReached(unittest.TestCase):
    def test_from_every_families_entry_to_the_policy_function(self):
        per = load_defs()
        self.assertIn(("gbp_control_policy.h", "gbp_control_agrees"), per)
        for fam, root in ROOTS.items():
            self.assertIn(root, per, "%s: entry %s not found" % (fam, root))
            live = reach(per, root)
            for want in (("gbp_control_policy.h", "gbp_control_agrees"), ("gbp_initirqa_probe.h", "gbp_initirqa_snapshot_control_agrees"),
                         ("gbp_initirqa_probe.c", "gbp_initirqa_teardown"), ("gbp_initirqa_probe.c", "teardown"),
                         ("gbp_irq_service.c", "gbp_irq_service_preunmask_check")):
                self.assertIn(want, live, "%s: %s is not reachable from %s" % (fam, want, root[1]))
            self.assertIn((root[0], "note_control") if fam != "initirqb" else ("gbp_initirqa_probe.c", "teardown"), live, fam)

    def test_the_guard_and_restore_sites_call_the_policy(self):
        per = load_defs()
        expect = {
            ("gbp_irq_service.c", "gbp_irq_service_preunmask_check"): "gbp_initirqa_snapshot_control_agrees",
            ("gbp_irq_service.c", "gbp_irq_service_ack"): "gbp_initirqa_snapshot_control_agrees",
            ("gbp_initirqa_probe.c", "teardown"): "gbp_control_agrees",
            ("gbp_initirqa_probe.h", "gbp_initirqa_snapshot_control_agrees"): "gbp_control_agrees",
            ("gbp_vstate_probe.c", "note_control"): "gbp_initirqa_snapshot_control_agrees",
            ("gbp_avsvc_probe.c", "note_control"): "gbp_initirqa_snapshot_control_agrees",
            ("gbp_initirq4_probe.c", "note_control"): "gbp_initirqa_snapshot_control_agrees",
            ("gbp_video_probe.c", "note_control"): "gbp_initirqa_snapshot_control_agrees",
        }
        for key, callee in expect.items():
            self.assertIn(key, per, key)
            self.assertRegex(per[key], r"\b%s\s*\(" % callee, "%s does not call %s" % (key, callee))
        # the restore compare, precisely: the read-back vote against the ORIGINAL byte goes through the policy
        self.assertRegex(per[("gbp_initirqa_probe.c", "teardown")], r"gbp_control_agrees\(res->control_restore_vote,\s*res->control_orig\)")

    def test_no_function_a_family_can_reach_still_compares_the_vote_for_equality(self):
        per = load_defs()
        for fam, root in ROOTS.items():
            live = reach(per, root)
            self.assertGreater(len(live), 20, "%s: the walk found almost nothing -- the parser broke" % fam)
            for k in sorted(live):
                self.assertEqual(strict_hits(per[k]), [], "%s reaches %s, which compares the CONTROL vote for equality" % (fam, k))

    def test_the_two_early_probes_that_keep_strict_equality_are_not_reachable_from_any_family(self):
        per = load_defs()
        for fam, root in ROOTS.items():
            live = reach(per, root)
            for e in EARLY:
                self.assertNotIn(e, live, "%s reaches the early probe %s, which still compares strictly" % (fam, e))
        # and they DO still compare strictly: this pair is the honest inventory of what was left alone
        hits = [k for k, body in per.items() if k[0] in ("gbp_init_probe.c", "gbp_init_irq_probe.c") and strict_hits(body)]
        self.assertTrue(hits, "the early probes no longer compare strictly: update the inventory (and this test)")

    def test_the_detector_fires_on_every_spelling_it_claims_and_ignores_comments_and_strings(self):
        spellings = [
            "int f(struct r *res, struct s *s) { if (s->control_vote != res->a.control_exp) return 1; return 0; }",
            "int f(struct s *s) { return s->control_b1f != res->a.control_exp; }",
            "int f(struct s *s) { return s->control_vote != (uint8_t)res->a.control_exp; }",
            "int f(struct s *s) { return s->control_vote == 0x8e; }",
            "int f(struct s *s) { return res->a.control_orig != res->control_restore_vote; }",
            "int f(struct s *s) { return (s->control_vote ^ res->a.control_exp) != 0; }",
            "int f(struct s *s) { return memcmp(&s->control_vote, &e, 1); }",
            "int f(struct s *s) { switch (s->control_vote) { case 0x8e: return 1; } return 0; }",
            "int f(void) { x = (res->control_restore_vote == res->control_orig); return x; }",
        ]
        for src in spellings:
            self.assertTrue(strict_hits(function_defs(strip_for_calls(src))["f"]), "the detector missed: " + src)
        allowed = [
            "int g(struct s *s) { return s->control_vote != s->control_b1f; }",                    # the consistency of the two readings
            "int g(struct s *s) { return s->control_rc != GBP_OK; }",
            "int g(struct r *res) { return res->control_orig == res->control_exp; }",              # the write decision, no reading
            "int g(struct r *res) { return (res->control_orig & cfg->clear_mask) == 0; }",
            'void g(void) { /* s->control_vote != res->a.control_exp */ const char *m = "control_vote != control_exp"; }',
        ]
        for src in allowed:
            self.assertEqual(strict_hits(function_defs(strip_for_calls(src))["g"]), [], "the detector flagged a legitimate line: " + src)


if __name__ == "__main__":
    unittest.main()
