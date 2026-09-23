"""
tests/host/test_run17_prereg.py — RUN 17 / RUN 18 pre-registration (HARDWARE_TESTS
§V7.3, GitHub Issue #28): GBP-INPUT-002, the machine-join runs of stream-0015 —
the KEY record joined to the checker's counters — frozen BEFORE hardware.

Pinned: Question One is answered from the code and from RUN 14 / RUN 15's data
before any gate (per press NOT supported; per interval a consistency check only,
the counts within an interval not distinct; the whole-run join binds by the
distinct totals; FACT reachable; pacing EXCLUDED); the identity is stream-0015
(514 880 B, dd545c01…, da06500, NOT rebuilt) and stream-0014 is preserved to
build/archive/ first, reproducible from 0ff8355; the numbering is resolved (RUN
16 keeps the menu reading); the ten run17 / run18 names appear once in §V7.3
and once in the handoff, none exists on disk, none for run19+; the gates are
prospective (no result, no new id, no executed date); a failed join is
reachable and informative; the recovery procedure is byte-identical to
§V7.1.7's; the Operator's channel stays beside the join; §V7.1 and §V7.2 are
the bytes of 48e5c24; INPUT.md's correction is dated and the routing stays C;
nothing under src/, poc/, tools/, Makefile, stimulus/ or captures/fixtures
moved. Nothing here runs a program.
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import unittest

import artifacts  # noqa: E402  (tests/host is on the path)

import guards

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
ROADMAP = os.path.join(ROOT, "docs", "ROADMAP.md")
DEVLOG = os.path.join(ROOT, "docs", "research", "DEVLOG.md")
INPUT_MD = os.path.join(ROOT, "docs", "protocol", "INPUT.md")
DOL_SHA = "dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49"
PREV_SHA = "ef76a170c10d335e62c017e53f74c60e410e44f5ce2fbca6774ab43c68ec0b9c"
BASE_COMMIT = "48e5c24"                   # origin/main before Issue #28
NAMES = ["captures/local/GBP-VIDEO-004_stream-0015-run%d%s" % (n, s)
         for n in (17, 18) for s in (".log", "-idxcap.bin", "-disp.bin", "-full.bin", "-vi.bin")]
LABELS = ["L", "R", "UP", "DOWN", "LEFT", "RIGHT", "START", "SELECT", "A", "B"]
_C = {}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def flat(s):
    return re.sub(r"\s+", " ", s)


def plain(s):
    return flat(s).replace("`", "").replace("**", "")


def git_show(path, commit=BASE_COMMIT):
    """Issue #83 (B): an absent COMMIT skips; a path missing from a commit that IS
    here fails, because that is a moved file and not an absent history."""
    return guards.show(commit, path)


def prereg():
    if "p" not in _C:
        t = read(HW)
        i = t.index("### V7.3 ")
        j = t.find("### V7.4 ", i)
        _C["p"] = t[i:] if j < 0 else t[i:j]
    return _C["p"]


def body():
    return "\n".join(prereg().splitlines()[1:])


def part(n, text=None):
    t = prereg() if text is None else text
    i = t.index("#### V7.3.%d " % n)
    j = t.find("#### V7.3.%d " % (n + 1), i)
    return t[i:] if j < 0 else t[i:j]


def v71_part(n, text):
    i = text.index("#### V7.1.%d " % n)
    j = text.find("#### V7.1.%d " % (n + 1), i)
    return text[i:] if j < 0 else text[i:j]


def block_after(p, heading):
    i = p.index(heading)
    j = p.index("```text", i)
    return p[j:p.index("```", j + 7) + 3]


class TheSectionExists(unittest.TestCase):
    def test_twelve_parts_in_order_and_the_heading_carries_the_status(self):
        t = prereg()
        pos = [t.index("#### V7.3.%d " % n) for n in range(1, 13)]
        self.assertEqual(pos, sorted(pos))
        self.assertNotIn("#### V7.3.13 ", t)
        head = t.splitlines()[0]
        for tok in ("RUN 17 / RUN 18", "GBP-INPUT-002", "PRE-REGISTERED 2026-09-21 (GitHub Issue #28)", "NOT RUN / NOT AUTHORISED HERE",
                    "CORROBORATED to FACT"):
            self.assertIn(tok, head, tok)
        full = read(HW)
        self.assertEqual((full.count("### V7.3 "), full.count("\n## V7 ")), (1, 1))
        self.assertLess(full.index("### V7.2 "), full.index("### V7.3 "))
        v7 = [l for l in full.splitlines() if l.startswith("## V7 ")][0]
        for tok in ("RUN 17 / RUN 18 PRE-REGISTERED (Issue #28, §V7.3)", "GBP-INPUT-002", "NOT RUN / NOT AUTHORISED HERE"):
            self.assertIn(tok, v7, tok)


class QuestionOneIsAnsweredFromTheCodeAndTheData(unittest.TestCase):
    def test_the_granularities_and_the_answer(self):
        p = plain(part(1))
        for tok in ("GBP_VFULL_K 8u", "GBP_VFULL_SPACING 256u", "4.286 s", "keysDown()",
                    "R +2 and B +2 share the first interval of RUN 14", "R +2 and DOWN +2",
                    "per press, in time NOT SUPPORTED", "per interval a CONSISTENCY CHECK, not a binding", "the whole run SUPPORTED, AND IT BINDS",
                    "no timing, no boundary rule, no pacing, and no human link", "FACT is REACHABLE", "with stream-0015 exactly as it is",
                    "Input latency stays out of reach", "pacing the walk to the sample cadence is EXCLUDED", "recorded, not proposed, none authorised here",
                    "this part stops at the totals"):
            self.assertIn(tok, p, tok)

    def test_the_figures_are_the_ones_the_code_and_the_runs_carry(self):
        h = read(os.path.join(ROOT, "src", "gbp", "gbp_vfull.h"))
        self.assertRegex(h, r"#define GBP_VFULL_K\s+8u")
        self.assertRegex(h, r"#define GBP_VFULL_SPACING\s+256u")
        self.assertAlmostEqual(256 / 59.727, 4.286, places=3)
        for run, deltas in ((14, {"R": 2, "A": 3, "B": 2}), (15, {"R": 2, "UP": 3, "DOWN": 2})):
            with open(os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-21-idxcap-run%d-struct.json" % run), encoding="utf-8") as f:
                smp = json.load(f)["tally_frames"]["samples"]
            v = lambda i: [0 if x == "blank" else int(x) for x in smp[i]["vector_as_read"]]
            d01 = {LABELS[k]: v(1)[k] - v(0)[k] for k in range(10) if v(1)[k] != v(0)[k]}
            self.assertEqual(d01, deltas, "the first interval's increments, from the fixture")
            self.assertEqual(sorted(d01.values()), [2, 2, 3], "two buttons up by the same amount in one interval: not distinct")
            self.assertAlmostEqual(smp[0]["s_after_control"], 6.084, places=2)
            self.assertAlmostEqual(smp[7]["s_after_control"], 36.087, places=2)


class IdentitiesAreTheFrozenOnes(unittest.TestCase):
    def test_the_dol_is_the_issue_27_candidate_not_rebuilt(self):
        p = part(3)
        self.assertIn(DOL_SHA, p)
        self.assertIn("514 880 B", p)
        self.assertIn("OPENGBP-IDENT gbp-video-stream-probe stream-0015 da06500", p)
        self.assertIn("NOT rebuilt", plain(p))
        self.assertIn("DO NOT RUN", p)

    def test_stream_0014_is_preserved_first_and_reproducible(self):
        p = plain(part(3))
        for tok in ("12-stream, REUSED AGAIN", "build/archive/gbp-video-stream-probe-stream-0014-0ff8355.dol", "ef76a170...0b9c", "513 152 B",
                    "REPRODUCIBLE", "GIT_COMMIT=0ff8355 GIT_DIRTY= make build", "The staging itself is NOT performed by this part",
                    "NO analyzer parses the KEY record", "frozen HERE so the ingestion cannot tune it"):
            self.assertIn(tok, p, tok)
        g = plain(part(6))
        for tok in ("/media/rafael/SD_GC/Open-GBP/12-stream/boot.dol", DOL_SHA, "514 880 B",
                    "If it still reads ef76a170...0b9c (stream-0014), the copy did not happen: DO NOT RUN", "WITHOUT rebuilding",
                    "If ANY identity differs: DO NOT RUN"):
            self.assertIn(tok, g, tok)
        # Hardware Issue #32 (2026-09-21) preserved stream-0014 before staging stream-0015 (§V7.3.6 steps 1-3); the archive, when present, is the exact bytes
        arch = os.path.join(ROOT, "build", "archive", "gbp-video-stream-probe-stream-0014-0ff8355.dol")
        artifacts.optional(self, arch, "the preserved stream-0014 archive is not in this checkout")   # Issue #83 (D)
        self.assertEqual((os.path.getsize(arch), hashlib.sha256(open(arch, "rb").read()).hexdigest()), (513152, PREV_SHA))

    def test_the_built_artifact_if_present_is_the_one_named(self):
        info = os.path.join(ROOT, "build", "poc", "gbp-video-stream-probe", "build-info.txt")
        if not os.path.exists(info):
            self.skipTest("no build metadata on this host")
        t = read(info)
        if "build_id=stream-0015" not in t:
            self.skipTest("the tree builds a different stream candidate")
        if "commit=da06500" not in t:
            # rebuilt at a later commit by a later code checkpoint (Issue #39): not the artifact this section names
            self.skipTest("the stream-0015 artifact on this host was rebuilt at another commit; the named one is da06500's")
        self.assertIn("sha256_dol=" + DOL_SHA, t)
        self.assertIn("commit=da06500\n", t)

    def test_the_staged_slot_holds_one_of_the_two_named_images(self):
        """Issue #83 (D), and THE ONE SITE THAT WAS PROVABLY DEAD. This check used to be the
        last three lines of the test above, behind THREE skipTest calls; Issue #83's runtime
        instrumentation showed the condition was NEVER EVALUATED on this host, because the
        third skip always fires here. What is staged has nothing to do with what the tree
        builds, so it is its own test and does not inherit those skips."""
        swiss = os.path.join(ROOT, "build", "swiss", "12-stream", "boot.dol")
        artifacts.optional(self, swiss, "nothing is staged under build/swiss")
        with open(swiss, "rb") as f:
            self.assertIn(hashlib.sha256(f.read()).hexdigest(), (PREV_SHA, DOL_SHA),
                          "the Swiss slot holds stream-0014 (before Hardware Issue #32) or stream-0015 (staged under it)")


class TheNumberingAndTheNames(unittest.TestCase):
    def test_the_numbering_is_resolved_and_stated(self):
        p = plain(part(2))
        for tok in ("RUN 17 and RUN 18", "RESOLUTION, stated", "RUN 16 stays the menu reading", "a new run always takes the next number above every reserved one",
                    "No reserved name changes experiment", "GBP-INPUT-002", "RUN 17 the checker's counted walk A", "RUN 18 the checker's counted walk B",
                    "why both", "Why not one 55-press walk", "what the Operator does that is new NOTHING", "43, plus any retry",
                    "The AGS test ROM is NOT a fallback here"):
            self.assertIn(tok, p, tok)

    def test_the_ten_names_once_in_the_part_once_in_the_handoff_none_on_disk_none_beyond(self):
        p, t, h = prereg(), read(HW), read(HANDOFF)
        for n in NAMES:
            self.assertEqual(p.count(n), 1, n)
            self.assertEqual(t.count(n), 1, n)
            self.assertEqual(h.count(n), 1, n)
            # Hardware Issue #32 (2026-09-21) executed RUN 17 / RUN 18: the names are USED (Issue #33 ingested them, §V7.4, tests/host/test_run17.py)
        self.assertEqual(len(re.findall(r"captures/local/\S*run17\S*", t)), 5)
        self.assertEqual(len(re.findall(r"captures/local/\S*run18\S*", t)), 5)
        self.assertEqual(len(re.findall(r"captures/local/\S*run(?:3[6-9]|[4-9]\d)\S*", t)), 0)   # run19 / run20: Issue #34, §V7.5; run21 / run22: Issue #41, §V7.6; run30: Issue #58, §V8 (GBP-AUDIO-001, reserved and not on disk); run31: Issue #64, §V9 (GBP-AUDIO-002, reserved and not on disk); run32: nothing beyond RUN 31 exists (Issue #67); run33: Issue #75, §V13 (GBP-AUDIO-004, reserved and not on disk); run34: §V14 (GBP-AUDIO-003 repeated, reserved and not on disk); run35: §V16.5 (rides along, reserved)
        self.assertEqual(len(re.findall(r"captures/local/\S*stream-0014-run16\S*", t)), 5, "the run16 names of V7.1.5 untouched (retired by Issue #33, never reassigned)")
        self.assertEqual(len(re.findall(r"captures/local/\S*stream-0015-run16\S*", t)), 5, "the names RUN 16 actually used (§V7.4.3, Issue #33)")
        # Issue #47 (2026-09-22): RUN 23 and RUN 24 were executed by the Operator and their artifacts are archived
        # (§V7.7), so the "nothing beyond the reserved runs" boundary moves past them; 21 and 22 stay reserved and
        # absent, which is the part of this pin that is still alive
        self.assertEqual(glob.glob(os.path.join(ROOT, "captures", "local", "*stream-0015-run2[12]*")), [])   # nothing beyond the reserved runs (19 / 20: Issue #34)
        f = plain(part(5))
        for tok in ("TAKEN even if a run aborts, never starts, or RUN 18 is never executed", "cp --update=none", "Verified absent on 2026-09-21",
                    "The run16 names of V7.1.5 are untouched", "The KEY record lives inside the .log file"):
            self.assertIn(tok, f, tok)


class GatesAreProspectiveAndAFailedJoinIsReachable(unittest.TestCase):
    def test_no_result_no_new_id_no_executed_run(self):
        p = body()
        self.assertNotRegex(p, r"GBP-HW-26[6-9]|GBP-HW-2[7-9]\d|GBP-HW-[3-9]\d\d")
        self.assertNotIn("RESULT", p)
        self.assertNotRegex(p, r"EXECUTED 2026")
        self.assertNotRegex(p, r"ingested 2026|ingested on")
        self.assertIn("Nothing here is evidence", p)
        self.assertIn("no evidence ID is allocated", p)
        self.assertIn("PRE-REGISTERED / NOT RUN", part(12))

    def test_the_record_table_has_no_value_pre_filled(self):
        p = part(11)
        rows = [l for l in p.splitlines() if re.match(r"^[A-Za-z].*\s{2,}--", l)]
        self.assertGreaterEqual(len(rows), 20)
        for l in rows:
            self.assertRegex(l, r"--(\s+--)*(\s+\(.*\))?\s*$", l)
        self.assertIn("expected vector (arithmetic)            1,2,0,0,0,0,6,5,3,4  1,2,3,4,5,6,0,0,0,0", p)

    def test_the_verdicts_per_bit_and_the_channels_kept_apart(self):
        p = part(9)
        for label in ("FACT          ", "FACT-SWAPPED  ", "NOT CLOSED    ", "UNDECIDED     ", "INCONCLUSIVE  "):
            self.assertEqual(len(re.findall(r"^%s" % re.escape(label), p, re.M)), 1, label)
        f = plain(p)
        for tok in ("reads two machine records and nothing else", "A1", "A2", "A3", "COUNTS only with rc=ok", "starting from 0000",
                    "R_b the number of 0 -> 1 transitions", "END STATE", "at least TWO such samples, all identical",
                    "blank read as 0 (the V7.1.9 wording mismatch, recorded again, not smoothed)",
                    "a physical FACT for this hardware, by machine end to end", "a physical FACT the other way", "It is NOT a failure of the run: the join closed",
                    "the two machine ends disagree", "an INFORMATIVE result about the instrumentation or the transport, never a failed run",
                    "the routing stays CORROBORATED", "those bits, and only those, are not bound in this run",
                    "QUESTION I -- the interval check, RECORDED, never a gate", "B = 3 source frames (~50 ms)", "NOT a latency figure and NOT tuned afterwards",
                    "NO latency figure is derived from it", "never fed into the join", "never merged",
                    "reports every intermediate quantity", "the ingestion cannot tune them"):
            self.assertIn(tok, f, tok)

    def test_the_shared_gates_add_the_key_record_and_make_truncated_zero_a_gate_again(self):
        f = plain(part(8))
        for tok in ("truncated=0 -- now a gate again", "PHYSICALLY VALIDATES the repair", "KEYLOG events = emitted, lost = 0, truncated = 0, overwritten = 0",
                    "every KEY line parses under GBP_INPUT_EVENT_FMT", "events = INPUT first + change + retry", "an unknown glyph aborts the reading",
                    "RECORDED, not judged", "a recovery power-off is INCONCLUSIVE for the join"):
            self.assertIn(tok, f, tok)


class TheProcedureAndTheRecovery(unittest.TestCase):
    def test_two_checklists_and_the_recovery_block_byte_identical_to_v7_1(self):
        p = part(7)
        self.assertIn("**RUN 17 — the checker's counted walk A", p)
        self.assertIn("**RUN 18 — the checker's counted walk B", p)
        self.assertEqual(len(p.split("```text")), 4)           # the recovery block and the two checklists
        run17 = block_after(p, "**RUN 17 — the checker")
        run18 = block_after(p, "**RUN 18 — the checker")
        for n in range(1, 14):
            self.assertIsNotNone(re.search(r"^\s*%d  " % n, run17, re.M), "run17 step %d" % n)
        self.assertIsNone(re.search(r"^\s*14  ", run17, re.M))
        for n in range(1, 10):
            self.assertIsNotNone(re.search(r"^\s*%d  " % n, run18, re.M), "run18 step %d" % n)
        self.assertIsNone(re.search(r"^\s*10  ", run18, re.M))
        self.assertEqual(p.count("NEVER one press per button"), 2)
        f = plain(p)
        for tok in ("The KEYPAD write is no longer a first", "byte-identical to V7.1.7's", "to pace the walk to the samples",
                    "L x1, R x2, A x3, B x4, SELECT (the X button of the GameCube pad) x5, START x6",
                    "L x1, R x2, UP x3, DOWN x4, LEFT x5, RIGHT x6 -- the D-pad, not the stick", "dd545c01...3a49",
                    "If it reads ef76a170...0b9c, the stream-0014 image is still on the card: DO NOT RUN",
                    "per-run subdirectory under logs/", "reserved run17 names", "reserved run18 names", "If the checker cannot be booted at all: do NOT run"):
            self.assertIn(tok, f, tok)
        self.assertIn("Do not infer a frame number, a latency or a timing from anything seen by eye", f)
        t = read(HW)
        v71 = t[t.index("### V7.1 "):t.index("### V7.2 ")]
        self.assertEqual(block_after(p, "**Recovery procedure"), block_after(v71_part(7, v71), "**Recovery procedure"))

    def test_the_topology_cites_the_inventory_and_declares_the_rest(self):
        f = plain(part(4))
        for tok in ("DECLARED HARDWARE INVENTORY", "cited, not asked again", "a declaration, never an inference", "generic third-party",
                    "the scope of any L/R statement follows the pad declared", "DECLARED per run", "the join reads the FRAMES, not the screen"):
            self.assertIn(tok, f, tok)

    def test_what_a_fact_changes_and_what_is_not_measured(self):
        f = plain(part(10))
        for tok in ("stays closed; this part does not reopen it", "FACT (hw, the run)", "by the ingestion checkpoint, under its own authorisation, never here",
                    "input latency (V7.3.1: out of reach of this sampling)", "a real game, which is a separate run with its own contract"):
            self.assertIn(tok, f, tok)


class NothingElseMoved(unittest.TestCase):
    def test_v7_1_and_v7_2_are_the_bytes_of_the_base(self):
        old = git_show("docs/research/HARDWARE_TESTS.md")  # Issue #83 (B): absent COMMIT skips, absent PATH fails
        new = read(HW)
        self.assertEqual(new[new.index("### V7.1 "):new.index("### V7.3 ")].rstrip("\n"), old[old.index("### V7.1 "):].rstrip("\n"))
        old_head = [l for l in old.splitlines() if l.startswith("## V7 ")][0]
        new_head = [l for l in new.splitlines() if l.startswith("## V7 ")][0]
        self.assertTrue(new_head.startswith(old_head))
        self.assertEqual(new[:new.index("\n## V7 ")], old[:old.index("\n## V7 ")], "everything before the chapter untouched")

    def test_input_md_is_corrected_on_its_date_and_the_routing_stays_c(self):
        t = read(INPUT_MD)
        self.assertNotIn("recorded, not\nimplemented", t)
        self.assertIn("recorded on 2026-09-21 as not implemented — implemented the same day in `stream-0015`", re.sub(r"\s+", " ", t))
        # Issue #33 (2026-09-21) then ingested RUN 17 / RUN 18: the routing is FACT (hw, the runs) and the page says so with its history
        # (tests/host/test_run17.py pins the promotion); this checkpoint's dated correction is kept inside that history
        self.assertIn("pre-registered to spend it, `HARDWARE_TESTS.md` §V7.3", t)
        self.assertIn("was\nCORROBORATED, not FACT, until the join later that day", t)

    def test_the_records(self):
        d = read(DEVLOG)
        i = d.rindex("## 2026-09-21 — Issue #28")
        j = d.find("\n## 2026", i + 1)
        e = d[i:j if j > 0 else None]
        for tok in ("Question One", "FACT is reachable per bit", "NOT RUN / NOT AUTHORISED HERE", "pacing the walk is EXCLUDED", "no hardware, no code, no build, no staging"):
            self.assertIn(tok, e, tok)
        self.assertNotRegex(e, r"GBP-HW-26[6-9]")
        h = plain(read(HANDOFF))
        for tok in ("issue 28", "RUN 17 and RUN 18 (GBP-INPUT-002", "That the interval-wise join binds the routing"):   # the trail's `next` moved on with Issue #33
            self.assertIn(tok, h, tok)
        self.assertIn("Pre-registered 2026-09-21 (GitHub Issue #28)", plain(read(ROADMAP)))

    def test_nothing_under_the_untouchable_paths_changed_against_the_base(self):
        if not guards.base_available(BASE_COMMIT):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE_COMMIT)
        changed = guards.changed_since(BASE_COMMIT, ["src", "poc", "tools", "Makefile", "stimulus"])   # Issue #29: tracked AND untracked, one implementation
        # Issue #65 (2026-09-22) BUILT stimulus/agb-tone (tone-0001), §V9's two-frequency stimulus: a new
        # stimulus ROM beside the four the family already had. It touches no runtime path, no image and no
        # slot; §V9.14 records its identity and tests/host/test_agb_tone.py runs its own code on the host.
        changed = changed - {"stimulus/agb-tone/Makefile", "stimulus/agb-tone/source/main.c"}
        # Issue #70 (2026-09-22) BUILT stimulus/agb-sweep (sweep-0001), §V11's TWO-AXIS stimulus: a new
        # stimulus ROM beside the five the family now has, and agb-tone is NOT touched (a test pins it
        # byte-identical). It touches no runtime path, no image and no slot; §V11.15 records its
        # identity and tests/host/test_agb_sweep.py runs its own code on the host.
        changed = changed - {"stimulus/agb-sweep/Makefile", "stimulus/agb-sweep/source/main.c"}
        # Issue #64 (2026-09-22) pre-registered agb-tone (§V9) and made its constructions executable BEFORE
        # the ROM exists: tools/v9tone.py is exercised on SYNTHETIC vectors only, reads no run, authorises
        # nothing and promotes nothing.
        changed = changed - {"tools/v9tone.py"}
        # Issue #69 (2026-09-22) pre-registered the amplitude sweep (§V11) and froze its constructions
        # BEFORE stimulus/agb-sweep exists: tools/v11sweep.py runs on SYNTHETIC vectors only, reads no
        # run, authorises nothing and promotes nothing. It is the fourth outing of the same discipline.
        changed = changed - {"tools/v11sweep.py"}
        # Issue #74 (2026-09-23) added tools/geckorx.py, the HOST receiver for the Operator's Pico
        # Gecko. It reads a serial port and writes bytes to a file; it touches no image, no POC and
        # no runtime path, and CLAUDE.md §14 forbids anything coming to depend on the device.
        changed = changed - {"tools/geckorx.py"}
        # Issue #75 (2026-09-23) pre-registered U-GBP-038's separator (§V13) and froze its
        # construction BEFORE the run: tools/v13sep.py runs on SYNTHETIC vectors only, borrows
        # v11sweep's classifier unchanged, reads no run and authorises nothing.
        changed = changed - {"tools/v13sep.py"}
        # §V14 (2026-09-23) froze the METHOD of RUN 34's measurement before the run:
        # tools/v14repeat.py contains no gate, reproduces §V11.16.7 exactly, reads no run.
        changed = changed - {"tools/v14repeat.py"}
        # Issue #79 (2026-09-23): tools/v16bitgate.py, QUESTION V repaired at bit resolution and
        # QUESTION L, frozen forward only; it imports v11sweep and edits nothing.
        changed = changed - {"tools/v16bitgate.py"}
        # Issue #80 (2026-09-23): tools/v17pred.py (the predictions, frozen first) and
        # tools/v17decode.py (the H-PWM decoder); they read the captures and touch no image.
        changed = changed - {"tools/v17pred.py", "tools/v17decode.py"}
        # Issue #81 (2026-09-23): the AUDIO decode as runtime code -- src/audio/ (the decoder, the
        # replay backend, the 125/16 resampler and its generated table), its generator
        # tools/gen_aresamp.py, and RUN 33 / RUN 34's raw sidecars versioned as fixtures. Host-tested
        # only: no image links src/audio/, and no POC, slot or runtime path changed.
        changed = changed - {"src/audio/gbp_adec.c", "src/audio/gbp_adec.h", "src/audio/gbp_asrc.c",
                             "src/audio/gbp_asrc.h", "src/audio/gbp_aresamp.c", "src/audio/gbp_aresamp.h",
                             "src/audio/gbp_aresamp_coef.h", "tools/gen_aresamp.py", "captures/README.md",
                             "captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz",
                             "captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run34-audio.bin.gz"}
        # Issue #82 (2026-09-23): tools/v18block.py, what one AUDIO block contains, measured on the
        # versioned fixtures (§V18). Descriptive, no gate; it reads captures and touches no image.
        changed = changed - {"tools/v18block.py"}
        # Issue #84 (2026-09-23): tools/v19drain.py, §V19's three gates, FROZEN BEFORE the run
        # (GBP-AUDIO-005). Synthetic vectors only; it reads no capture and authorises nothing.
        changed = changed - {"tools/v19drain.py"}
        # Issue #84: src/audio/gbp_adrain.* -- GBP-AUDIO-005's phase machine and coverage
        # counter, host-tested only (tests/unit/test_gbp_adrain.c). No image links it yet.
        changed = changed - {"src/audio/gbp_adrain.c", "src/audio/gbp_adrain.h"}
        # Issue #84 (2026-09-23) BUILT GBP-AUDIO-005's image, drain-0001 (§V19.11 A4.1): play-0001 plus
        # the drain's period decoder (src/audio/gbp_aperiod.*, host-tested), the POC that carries it, and
        # tools/v19report.py, the log -> report builder frozen before the run. The service path gains two
        # optional hooks, NULL in every earlier build (tests/unit/test_gbp_video_state.c proves the operation
        # stream identical), and tests/host/test_drain_image.py diffs the image against play-0001.
        changed = changed - {"poc/gbp-audio-drain-probe/Makefile", "poc/gbp-audio-drain-probe/source/main.c",
                             "src/audio/gbp_aperiod.c", "src/audio/gbp_aperiod.h", "tools/v19report.py"}
        # Issue #87 (2026-09-23) restored `make build` at HEAD: since #59 the service module references the
        # AUDIO window, so these four POCs link gbp_awin.c the way they link gbp_vwitness.c, cfg.awin NULL.
        # No executed artifact is rebuilt or relabelled; tests/host/test_poc_link_closure.py keeps the class
        # from recurring unobserved.
        changed = changed - {"poc/gbp-play-session/Makefile", "poc/gbp-video-stream-probe/Makefile",
                             "poc/gbp-video-state-probe/Makefile", "poc/gbp-video-color-probe/Makefile"}
        # Issue #62 (2026-09-22) ingested RUN 30 and needed two READERS that did not exist: awinparse.py,
        # a strict parser for the OGBPAW1 sidecar, and tprime.py, §V7.9's decision rule. Both only read and
        # report; the VERDICT constructions stay in tools/v8audio.py, which tests/host/test_run30.py diffs
        # against the commit that wrote it.
        changed = changed - {"tools/awinparse.py", "tools/tprime.py"}
        # Issue #59 (2026-09-22) BUILT the image §V8 needs: the AUDIO window and its OGBPAW1 sidecar
        # (src/gbp/gbp_awin*, host-testable, no libogc) and the POC that carries them, stream-0016. The
        # service path gains ONE optional config field and ONE call after the AUDIO drain and its commit;
        # no device operation is added, removed or reordered (tests/host/test_awin_image.py diffs it).
        changed = changed - {"src/gbp/gbp_awin.c", "src/gbp/gbp_awin.h",
                             "src/gbp/gbp_awindump.c", "src/gbp/gbp_awindump.h",
                             "poc/gbp-audio-window-probe/Makefile",
                             "poc/gbp-audio-window-probe/source/main.c"}
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
        # Issue #39 (2026-09-21) built the playable image: the session end in the service-path module (tests/host/test_play_image.py pins it), a new POC, its audit profile and its Swiss slot
        self.assertTrue(changed <= {"src/gbp/gbp_vstate_probe.c", "src/gbp/gbp_vstate_probe.h", "src/gbp/gbp_session.c", "src/gbp/gbp_session.h", "poc/gbp-play-session/Makefile", "poc/gbp-play-session/source/main.c", "tools/poc_audit.py", "tools/swiss-layout.tsv", "Makefile"}, "changed against the base: " + " ".join(sorted(changed)))
        # Issue #33 (2026-09-21) added the RUN 16 / 17 / 18 fixtures and promoted the consolidated pages (tests/host/test_run17.py pins both)
        changed2 = guards.changed_since(BASE_COMMIT, ["captures/fixtures"])   # Issue #29: tracked AND untracked, one implementation
        # Issue #81 (2026-09-23): RUN 33 / RUN 34's raw audio sidecars, versioned as replay fixtures
        # (captures/README.md); the first fixtures since RUN 18, and they touch none of the above.
        changed2 = changed2 - {"captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz",
                               "captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run34-audio.bin.gz"}
        for line in sorted(changed2):
            self.assertRegex(line, r"-run1[678]-", line)
        changed3 = guards.changed_since(BASE_COMMIT, ["docs/protocol", "docs/hardware"])   # Issue #29: tracked AND untracked, one implementation
        self.assertTrue(changed3 <= {"docs/protocol/INPUT.md", "docs/protocol/REGISTERS.md", "docs/protocol/INITIALIZATION.md",
                                                  "docs/hardware/GBS-DOL.md", "docs/hardware/ARCHITECTURE.md"}, " ".join(sorted(changed3)))


if __name__ == "__main__":
    unittest.main()
