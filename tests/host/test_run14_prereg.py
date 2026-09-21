"""
tests/host/test_run14_prereg.py — RUN 14 / RUN 15 pre-registration (HARDWARE_TESTS
§V7.1, GitHub Issue #20): GBP-INPUT-001, the first physical KEYPAD write, in two
staged runs of the unchanged stream-0014, frozen BEFORE hardware.

Pinned: Question One is answered from the code (the stop path, the derived
window, the two-run consequence, no code or build change); the identity is
the frozen one (stream-0014, 0ff8355, ef76a170…, 513 152 B, NOT rebuilt); the
Swiss slot decision is recorded with stream-0013 preserved and reproducible
from 7d7a6d8; the ten reserved names appear exactly once in §V7.1 and once in
the handoff and nowhere else, and none exists on disk; the gates are
prospective (no result, no evidence ID, no executed date); FAIL is reachable
and a swapped L/R is an informative outcome, not a failure of the run; the
machine side and the human side are kept apart; the recovery procedure and
its hazard are present; the AGS-ROM policy line is present; U-GBP-010's
closing condition is restated with neither outcome making the routing FACT;
the future stimulus is recorded and unstarted; and nothing under src/, poc/,
tools/, Makefile, docs/protocol or docs/hardware moved. Nothing here runs a
program.
"""
import glob
import os
import re
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
DEVLOG = os.path.join(ROOT, "docs", "research", "DEVLOG.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
DOL_SHA = "ef76a170c10d335e62c017e53f74c60e410e44f5ce2fbca6774ab43c68ec0b9c"
OLD_SHA = "5391c3fe962dc4b2f4e493f3846ac7407ded064c58f5d4bb583a51e5a725dd79"
BASE_COMMIT = "e258160bb6034427984765203dd36c1486a86dae"
NAMES = ["captures/local/GBP-VIDEO-004_stream-0014-run%d%s" % (n, s)
         for n in (14, 15) for s in (".log", "-idxcap.bin", "-disp.bin", "-full.bin", "-vi.bin")]
_C = {}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def flat(s):
    return re.sub(r"\s+", " ", s)


def plain(s):
    return flat(s).replace("`", "").replace("**", "")


def prereg():
    if "p" not in _C:
        t = read(HW)
        i = t.index("### V7.1 ")
        j = t.find("### V7.2 ", i)
        _C["p"] = t[i:] if j < 0 else t[i:j]
    return _C["p"]


def body():
    return "\n".join(prereg().splitlines()[1:])


def part(n):
    t = prereg()
    i = t.index("#### V7.1.%d " % n)
    j = t.find("#### V7.1.%d " % (n + 1), i)
    return t[i:] if j < 0 else t[i:j]


class TheSectionExists(unittest.TestCase):
    def test_twelve_parts_in_order_and_the_heading_carries_the_status(self):
        t = prereg()
        pos = [t.index("#### V7.1.%d " % n) for n in range(1, 13)]
        self.assertEqual(pos, sorted(pos))
        self.assertNotIn("#### V7.1.13 ", t)
        head = t.splitlines()[0]
        for tok in ("RUN 14", "RUN 15", "GBP-INPUT-001", "PRE-REGISTERED 2026-09-21 (GitHub Issue #20)", "NOT RUN / NOT AUTHORISED HERE"):
            self.assertIn(tok, head, tok)

    def test_it_is_the_v7_chapter_after_v6_and_the_v6_record_is_untouched(self):
        t = read(HW)
        self.assertEqual(t.count("### V7.1 "), 1)
        self.assertEqual(t.count("## V7 "), 1)
        self.assertLess(t.index("### V6.25 "), t.index("## V7 "))
        self.assertLess(t.index("## V7 "), t.index("### V7.1 "))
        self.assertNotIn("### V6.26 ", t)
        v7 = [l for l in t.splitlines() if l.startswith("## V7 ")][0]
        self.assertIn("NOT RUN / NOT AUTHORISED HERE", v7)
        self.assertIn("GBP-INPUT-001", v7)


class QuestionOneIsAnsweredFromTheCode(unittest.TestCase):
    def test_the_stop_path_the_window_and_the_consequence(self):
        p = plain(part(1))
        for tok in ("gbp_vwitness_target_reached", "S5_witness_target", "GBP_VSTATE_STOP_WITNESS_TARGET", "teardown_hardware",
                    "in_transport = 0", "VIDEO_SetNextFramebuffer(xfb_text)", "POWER CYCLE REQUIRED",
                    "does NOT keep the AGB running with video after the target",
                    "5000 ms after CONTROL", "5.000151 s", "64 consecutive structural closes", "6.067203 s",
                    "2048 records", "59.727133 Hz", "34.27 s", "~40.4 s after the CONTROL transform",
                    "stop=witness_target_ reached", "2 256 143 ticks", "Nothing in the runtime extends the window",
                    "One session cannot be relied on to carry both", "TWO RUNS of the SAME image",
                    "RUN 14 = stage 1", "RUN 15 = stage 2", "needs no code, constant, profile or build change",
                    "NOT requested here"):
            self.assertIn(tok, p, tok)

    def test_the_figures_are_the_ones_the_code_and_run_13_carry(self):
        src = read(os.path.join(ROOT, "src", "gbp", "gbp_vwitness.h"))
        self.assertIn("#define GBP_VWITNESS_TARGET      2048u", src)
        self.assertIn("#define GBP_VWITNESS_QUAL_REQUIRED 64u", src)
        main = read(os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c"))
        self.assertIn("#define STREAM_WIT_NOT_BEFORE_MS 5000u", main)
        self.assertIn("#define STREAM_SAFETY_SECONDS    60u", main)
        probe = read(os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.c"))
        self.assertIn('"S5_witness_target"', probe)
        self.assertIn("in_transport = 0;", main)
        # 2047 / 59.727133 = 34.27 s, as stated
        self.assertAlmostEqual(2047 / 59.727133, 34.27, places=2)
        self.assertAlmostEqual(6.067203 + 2047 / 59.727133, 40.34, places=2)


class IdentitiesAreTheFrozenOnes(unittest.TestCase):
    def test_the_dol_is_the_issue_19_candidate_not_rebuilt(self):
        p = part(3)
        self.assertIn(DOL_SHA, p)
        self.assertIn("513 152 B", p)
        self.assertIn("OPENGBP-IDENT gbp-video-stream-probe stream-0014 0ff8355", p)
        self.assertIn("TEST_ID GBP-VIDEO-004", p)
        self.assertIn("NOT rebuilt", p)
        self.assertIn("DO NOT RUN", p)
        self.assertIn("No artifact is rebuilt or", p)

    def test_the_swiss_slot_decision_preserves_and_reproduces_stream_0013(self):
        p = plain(part(3))
        for tok in ("12-stream, REUSED", OLD_SHA, "506 496 B", "the exact image RUN 12 and RUN 13 executed",
                    "/media/rafael/SD_GC/Open-GBP/12-stream/boot.dol", "cp --update=none build/swiss/12-stream/boot.dol",
                    "build/archive/gbp-video-stream-probe-stream-0013-7d7a6d8.dol", "REPRODUCIBLE", "commit 7d7a6d8",
                    "ghcr.io/extremscorner/libogc2:20260805", "NOT performed by this part", "NOTHING for RUN 14 / RUN 15",
                    "build/physical"):
            self.assertIn(tok, p, tok)
        g = plain(part(6))
        self.assertIn("/media/rafael/SD_GC/Open-GBP/12-stream/boot.dol", g)
        self.assertIn(DOL_SHA, g)
        self.assertIn("If it still reads 5391c3fe...dd79 (stream-0013), the copy did not happen: DO NOT RUN", g)
        self.assertIn("WITHOUT rebuilding", g)

    def test_the_built_artifact_if_present_is_the_one_named(self):
        info = os.path.join(ROOT, "build", "poc", "gbp-video-stream-probe", "build-info.txt")
        if not os.path.exists(info):
            self.skipTest("no build metadata on this host")
        t = read(info)
        if "build_id=stream-0014" not in t:
            self.skipTest("the tree builds a different stream candidate")
        self.assertIn("sha256_dol=" + DOL_SHA, t)
        self.assertIn("commit=0ff8355\n", t)


class NamesAreReservedExactlyOnce(unittest.TestCase):
    def test_the_ten_names_appear_exactly_once_in_the_pre_registration(self):
        p = prereg()
        for n in NAMES:
            self.assertEqual(p.count(n), 1, n)
        f = plain(p)
        for tok in ("TAKEN even if a run aborts", "cp --update=none", "never overwrite runs 1", "verify none of them exists",
                    "RUN 15 writes the SAME names as RUN 14", "BEFORE RUN 15 boots"):
            self.assertIn(tok, f, tok)

    def test_the_names_are_reserved_nowhere_else_in_hardware_tests(self):
        t = read(HW)
        for n in NAMES:
            self.assertEqual(t.count(n), 1, n)
        self.assertEqual(len(re.findall(r"captures/local/\S*run14\S*", t)), 5)
        self.assertEqual(len(re.findall(r"captures/local/\S*run15\S*", t)), 5)
        self.assertEqual(len(re.findall(r"captures/local/\S*run1[6-9]\S*", t)), 0)

    def test_the_handoff_reserves_the_same_ten_names_once_and_the_run_13_names_stay(self):
        h = read(HANDOFF)
        for n in NAMES:
            self.assertEqual(h.count(n), 1, n)
        for n in NAMES[:5]:
            self.assertEqual(h.count(n.replace("stream-0014-run14", "stream-0013-run13")), 1, n)

    def test_none_of_the_names_exists_on_disk(self):
        for n in NAMES:
            self.assertFalse(os.path.exists(os.path.join(ROOT, n)), n)
        self.assertEqual(glob.glob(os.path.join(ROOT, "captures", "local", "*run14*")), [])
        self.assertEqual(glob.glob(os.path.join(ROOT, "captures", "local", "*run15*")), [])

    def test_the_photograph_is_optional_and_not_one_of_the_ten(self):
        p = part(5)
        self.assertIn("never required for PASS", p)
        self.assertIn("never one of the\nten names", p)
        self.assertIn("not frame-accurate evidence", p)


class GatesAreProspective(unittest.TestCase):
    def test_no_result_no_evidence_id_no_executed_run(self):
        p = body()
        self.assertNotRegex(p, r"GBP-HW-\d{3}")
        self.assertNotRegex(p, r"GBP-KEY-00[7-9]|GBP-KEY-0[1-9]\d")
        self.assertNotIn("RESULT", p)
        self.assertNotRegex(p, r"EXECUTED 2026")
        self.assertNotRegex(p, r"ingested 2026|ingested on")
        self.assertIn("Nothing here is evidence", p)
        self.assertIn("no evidence ID is allocated", p)
        self.assertIn("PRE-REGISTERED / NOT RUN", part(12))

    def test_the_record_table_has_no_value_pre_filled(self):
        p = part(11)
        rows = [l for l in p.splitlines() if re.match(r"^[A-Za-z].*\s{2,}--", l)]
        self.assertGreaterEqual(len(rows), 15)
        for l in rows:
            self.assertRegex(l, r"--(\s+--)?(\s+\(.*\))?\s*$", l)

    def test_fail_is_reachable_and_swapped_is_informative(self):
        p = part(9)
        self.assertEqual(p.count("PASS          "), 1)
        self.assertEqual(p.count("FAIL          "), 1)
        self.assertEqual(p.count("AS-ASSIGNED   "), 1)
        self.assertEqual(p.count("SWAPPED       "), 1)
        self.assertEqual(p.count("INCONCLUSIVE  "), 2)
        f = plain(p)
        for tok in ("admissible run, INPUT machine gate met (writes completed, failed = 0), and the report says the cartridge did not respond",
                    "RECORDED as the first physical fact about the write", "RECORDED, EXPECTED-POSSIBLE, INFORMATIVE",
                    "FALSIFIES the assignment GBP-KEY-004 records", "It is NOT a failure of the run",
                    "the descriptor's two entries swap in a later functional Issue", "OPERATOR OBSERVATION",
                    "never fed into a tool", "a stage's verdict is COMPLETE for what that stage answers"):
            self.assertIn(tok, f, tok)

    def test_the_machine_side_is_thin_and_says_so(self):
        f = plain(part(8))
        for tok in ("the ONLY machine facts this experiment has", "write-only", "the device never answers",
                    "polled, encoded and wrote, nothing more", "completed = attempts, failed = 0", "steps = 0",
                    "NOT gates of GBP-INPUT-001", "RECORDED, not judged", "never a latency claim"):
            self.assertIn(tok, f, tok)


class TheProcedureTheHazardAndTheRecovery(unittest.TestCase):
    def test_two_staged_checklists_and_the_stage_2_condition(self):
        p = part(7)
        self.assertIn("**RUN 14 — stage 1, the EZ-Flash menu (always executed first):**", p)
        self.assertIn("**RUN 15 — stage 2, the AGS test ROM (conditional; executed only if RUN 14's\nQuestion M is PASS for both L and R, whatever Question O read):**", p)
        blocks = p.split("```text")
        self.assertEqual(len(blocks), 4)                       # the recovery block and the two checklists
        run14, run15 = blocks[2], blocks[3]
        for n in range(1, 14):
            self.assertIsNotNone(re.search(r"^\s*%d  " % n, run14, re.M), "run14 step %d" % n)
        self.assertIsNone(re.search(r"^\s*14  ", run14, re.M))
        for n in range(1, 11):
            self.assertIsNotNone(re.search(r"^\s*%d  " % n, run15, re.M), "run15 step %d" % n)
        self.assertIsNone(re.search(r"^\s*11  ", run15, re.M))
        for tok in ("do not stop it early", "reserved run14 names", "reserved run15 names", "press X once to save",
                    "power-cycle the console", "L, R, A, B, Select (X), Start, Up, Down, Left, Right",
                    "hold L and R together", "Do not press any other button during the run"):
            self.assertIn(tok, p, tok)
        self.assertIn("Do not infer a frame number, a latency or a timing from anything seen by\neye", p)

    def test_the_recovery_procedure_and_its_hazard(self):
        f = plain(part(7))
        for tok in ("power the console off at the button, wait, power on", "Do not try to correct it with the controller",
                    "No Open-GBP build has ever issued a KEYPAD write in any environment", "INPUT steps=0",
                    "only against the mock backend", "launch something unattended", "CLAUDE.md §18",
                    "DO NOT PRESS ANYTHING during the run", "does not apply here"):
            self.assertIn(tok, f, tok)

    def test_the_ags_rom_policy_line_and_the_topology(self):
        f = plain(part(4))
        for tok in ("proprietary Nintendo material", "NOTHING from it enters the repository", "no image, no dump, no extracted asset",
                    "no hash requirement", "CLAUDE.md §7", "ONE GameCube controller in port 1", "PAD_CHAN0",
                    "configured to show its MENU at boot", "coord-0002 may stay on the NOR and is NOT launched",
                    "HYDIS HV150UX2", "TOPOLOGY only"):
            self.assertIn(tok, f, tok)
        self.assertIn("stay OUTSIDE RUN 14 and RUN 15", flat(part(4)))


class TheUnknownAndTheFutureOption(unittest.TestCase):
    def test_u_gbp_010_is_restated_and_not_closed(self):
        f = plain(part(10))
        for tok in ("closes on a game that distinguishes L from R, as OPERATOR OBSERVATION",
                    "AS-ASSIGNED closes it with the assignment kept", "SWAPPED closes it the other way",
                    "Neither outcome makes the routing a physical FACT", "stays CORROBORATED after either result",
                    "project-owned stimulus that publishes KEYINPUT into its own video frames"):
            self.assertIn(tok, f, tok)
        u = read(UNKNOWNS)
        m = re.search(r"^## U-GBP-010\b.*$", u, re.M)
        self.assertIn("OPEN", m.group(0))
        self.assertNotIn("CLOSED", m.group(0))
        self.assertIn("§V7.1", u)

    def test_the_future_stimulus_is_recorded_and_unstarted(self):
        f = plain(part(10))
        for tok in ("Recorded future option, NOT started", "like the old tests", "indexed-0003 / color-0002 / coord-0001 / coord-0002",
                    "the only route to FACT for U-GBP-010", "latency", "the first source VIDEO frame that reacts",
                    "RUN 14 comes first", "the wrong order"):
            self.assertIn(tok, f, tok)
        self.assertIn("recorded, not\nstarted", part(12))


class NothingElseMoved(unittest.TestCase):
    def test_the_devlog_and_the_handoff_record_the_checkpoint_as_pre_registration_only(self):
        d = read(DEVLOG)
        i = d.rindex("## 2026-09-21 — Issue #20")
        j = d.find("\n## 2026", i + 1)
        e = d[i:j if j > 0 else None]
        for tok in ("RUN 14", "RUN 15", "NOT RUN", "no hardware, no flash, no build", "GBP-INPUT-001"):
            self.assertIn(tok, e, tok)
        self.assertNotRegex(e, r"GBP-HW-\d{3}")
        h = read(HANDOFF)
        self.assertRegex(h, r"RUN 14[^\n]*PRE-REGISTERED|PRE-REGISTERED[^\n]*RUN 14")
        self.assertIn("That RUN 14 or RUN 15 has run", h)

    def test_part_12_says_what_was_not_authorized(self):
        f = plain(part(12))
        for tok in ("hardware execution", "staging, copying or flashing anything", "any change to the runtime, the descriptor, the policy, the analyzers, the formats, the fixtures, the evidence rows or the gates (none was made)",
                    "promoting the L/R order", "closing U-GBP-010", "updating docs/protocol/INITIALIZATION.md", "No new physical evidence ID exists"):
            self.assertIn(tok, f, tok)

    def test_nothing_under_the_untouchable_paths_changed_against_the_base(self):
        r = subprocess.run(["git", "-C", ROOT, "cat-file", "-e", BASE_COMMIT], capture_output=True)
        if r.returncode != 0:
            self.skipTest("the base commit is not available in this checkout")
        r = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", BASE_COMMIT, "--", "src", "poc", "tools", "Makefile",
                            "docs/protocol", "docs/hardware", "captures/fixtures", "stimulus"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "", "changed against the base: " + r.stdout)


if __name__ == "__main__":
    unittest.main()
