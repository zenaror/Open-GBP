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
         for n in (14, 15, 16) for s in (".log", "-idxcap.bin", "-disp.bin", "-full.bin", "-vi.bin")]
FROZEN_COMMIT = "848007abfd1b7d2e21a6ef7582062e0ee9539d5a"   # Issue #20's pre-registration; RUN 14's parts stay its bytes
CHECKER_COMMIT = "76924c1371d7bf761f8b1ed45ab36f195cd1374f"
CHECKER_SHA = "53c212c73e814875fcbac16a4dc22ea5d6c752f85cdddc433db97439caef2b6e"
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


def part(n, text=None):
    t = prereg() if text is None else text
    i = t.index("#### V7.1.%d " % n)
    j = t.find("#### V7.1.%d " % (n + 1), i)
    return t[i:] if j < 0 else t[i:j]


def frozen_prereg():
    import subprocess
    r = subprocess.run(["git", "-C", ROOT, "show", "%s:docs/research/HARDWARE_TESTS.md" % FROZEN_COMMIT], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    t = r.stdout
    return t[t.index("### V7.1 "):]


def block_after(p, heading):
    i = p.index(heading)
    j = p.index("```text", i)
    return p[j:p.index("```", j + 7) + 3]


class TheSectionExists(unittest.TestCase):
    def test_twelve_parts_in_order_and_the_heading_carries_the_status(self):
        t = prereg()
        pos = [t.index("#### V7.1.%d " % n) for n in range(1, 13)]
        self.assertEqual(pos, sorted(pos))
        self.assertNotIn("#### V7.1.13 ", t)
        head = t.splitlines()[0]
        for tok in ("RUN 14", "RUN 15", "GBP-INPUT-001", "PRE-REGISTERED 2026-09-21 (GitHub Issue #20)", "NOT RUN / NOT AUTHORISED HERE",
                    "AMENDED BEFORE HARDWARE (GitHub Issue #23, 2026-09-21): the Enhanced Control Checker is the instrument of RUN 14 and RUN 15; the EZ-Flash menu test becomes the optional RUN 16"):
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
    def test_the_fifteen_names_appear_exactly_once_in_the_pre_registration(self):
        p = prereg()
        for n in NAMES:
            self.assertEqual(p.count(n), 1, n)
        f = plain(p)
        for tok in ("TAKEN even if a run aborts", "cp --update=none", "never overwrite runs 1", "verify none of them exists",
                    "RUN 15 and RUN 16 write the SAME names as RUN 14", "BEFORE the next run boots"):
            self.assertIn(tok, f, tok)

    def test_the_names_are_reserved_nowhere_else_in_hardware_tests(self):
        t = read(HW)
        for n in NAMES:
            self.assertEqual(t.count(n), 1, n)
        self.assertEqual(len(re.findall(r"captures/local/\S*run14\S*", t)), 5)
        self.assertEqual(len(re.findall(r"captures/local/\S*run15\S*", t)), 5)
        self.assertEqual(len(re.findall(r"captures/local/\S*run16\S*", t)), 5)
        self.assertEqual(len(re.findall(r"captures/local/\S*run1[7-9]\S*", t)), 0)

    def test_the_handoff_reserves_the_same_fifteen_names_once_and_the_run_13_names_stay(self):
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
        self.assertEqual(glob.glob(os.path.join(ROOT, "captures", "local", "*run16*")), [])

    def test_the_photograph_is_optional_and_not_one_of_the_fifteen(self):
        p = part(5)
        self.assertIn("never required for PASS", p)
        self.assertIn("never one of the fifteen names", flat(p))
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
        self.assertGreaterEqual(len(rows), 16)
        for l in rows:
            self.assertRegex(l, r"--(\s+--)*(\s+\(.*\))?\s*$", l)
        # the only pre-filled rows are the arithmetic expectation and the staging already performed for #21
        self.assertIn("expected vector (arithmetic)            1,2,0,0,0,0,6,5,3,4  1,2,3,4,5,6,0,0,0,0", p)
        self.assertIn("stream-0013 preserved before staging    done 2026-09-21 (5391c3fe...dd79 at build/archive/, Hardware Issue #21)", p)

    def test_fail_is_reachable_and_swapped_is_informative(self):
        p = part(9)
        self.assertEqual(p.count("PASS          "), 1)
        self.assertEqual(p.count("FAIL          "), 1)
        self.assertEqual(p.count("AS-ASSIGNED   "), 1)
        self.assertEqual(p.count("SWAPPED       "), 1)
        self.assertEqual(p.count("INCONCLUSIVE  "), 2)
        f = plain(p)
        for tok in ("a pressed button's count appears at no counter at all", "RECORDED as the first physical fact about the write",
                    "RECORDED, EXPECTED-POSSIBLE, INFORMATIVE", "FALSIFIES the assignment GBP-KEY-004 records", "It is NOT a failure of the run",
                    "the descriptor's two entries swap in a later functional Issue", "OPERATOR OBSERVATION", "never fed into a tool",
                    "RUN 14 (walk A) 1, 2, 0, 0, 0, 0, 6, 5, 3, 4", "RUN 15 (walk B) 1, 2, 3, 4, 5, 6, 0, 0, 0, 0",
                    "The single-press walk is forbidden", "a zero where a count was expected", "an unexpected non-zero where 0 was",
                    "exactly one pi is consistent", "a walk cut by the target", "L and R come first", "the live channel",
                    "never overrides the vector by itself", "a photograph of the tally screen", "never evidence by itself",
                    "RUN 16, if ever run", "a run's verdict is COMPLETE for what that run answers"):
            self.assertIn(tok, f, tok)

    def test_the_machine_side_is_thin_and_says_so(self):
        f = plain(part(8))
        for tok in ("the ONLY machine facts this experiment has", "write-only", "the device never answers",
                    "polled, encoded and wrote, nothing more", "completed = attempts, failed = 0", "steps = 0",
                    "NOT gates of GBP-INPUT-001", "RECORDED, not judged", "never a latency claim"):
            self.assertIn(tok, f, tok)


class TheProcedureTheHazardAndTheRecovery(unittest.TestCase):
    def test_three_checklists_the_forbidden_walk_and_the_two_channels(self):
        p = part(7)
        self.assertIn("**RUN 14 — the checker's counted walk A (the first executed run; Hardware\nIssue #21, aligned by the Orchestrator):**", p)
        self.assertIn("**RUN 15 — the checker's counted walk B (follows RUN 14 in order; planned\nfor the same session; its own authorisation):**", p)
        self.assertIn("**RUN 16 — OPTIONAL and INDEPENDENT: the EZ-Flash menu's L/R tabs", p)
        self.assertEqual(len(p.split("```text")), 5)           # the recovery block and the three checklists
        run14 = block_after(p, "**RUN 14 — the checker")
        run15 = block_after(p, "**RUN 15 — the checker")
        run16 = block_after(p, "**RUN 16 — OPTIONAL")
        for n in range(1, 14):
            self.assertIsNotNone(re.search(r"^\s*%d  " % n, run14, re.M), "run14 step %d" % n)
        self.assertIsNone(re.search(r"^\s*14  ", run14, re.M))
        for n in range(1, 10):
            self.assertIsNotNone(re.search(r"^\s*%d  " % n, run15, re.M), "run15 step %d" % n)
        self.assertIsNone(re.search(r"^\s*10  ", run15, re.M))
        for n in range(1, 11):
            self.assertIsNotNone(re.search(r"^\s*%d  " % n, run16, re.M), "run16 step %d" % n)
        self.assertIsNone(re.search(r"^\s*11  ", run16, re.M))
        f = plain(p)
        for tok in ("THE FORBIDDEN WALK, and the two channels", "its END STATE cannot distinguish a permutation",
                    "records BOTH channels", "L x1, R x2, A x3, B x4, SELECT (the X button of the GameCube pad) x5, START x6",
                    "L x1, R x2, UP x3, DOWN x4, LEFT x5, RIGHT x6 -- the D-pad, not the stick", "about two presses per second",
                    "BEFORE the run ends", "Live channel: note, when you can see it, which labelled row moved",
                    "Optionally photograph the tally screen", "unregistered-trial-2026-09-21", "MOVED ASIDE", "never deleted",
                    "Stop rule: if RUN 14 showed no press reaching the cartridge at all", "a precondition of nothing",
                    "do not stop it early", "reserved run14 names", "reserved run15 names", "reserved run16 names",
                    "press X once to save", "power-cycle the console"):
            self.assertIn(tok, f, tok)
        self.assertEqual(p.count("NEVER one press per button"), 2)
        self.assertIn("Do not infer a frame number, a latency or a timing from anything seen by\neye", p)

    def test_the_frozen_parts_are_byte_identical_to_the_pre_registration(self):
        """Issue #23 amended the runs before any hardware; what Issue #20 froze and
        this amendment may not touch keeps its bytes: Question One, the shared
        admissibility gates, the hazard paragraph, the recovery block with the
        banner note, and the U-GBP-010 part."""
        old = frozen_prereg()
        if old is None:
            self.skipTest("the frozen commit is not available in this checkout")
        new = prereg()
        for n in (1, 8, 10):
            self.assertEqual(part(n, new), part(n, old), n)
        hz = lambda t: part(7, t)[part(7, t).index("**The hazard this run carries"):part(7, t).index("```text")]
        self.assertEqual(hz(new), hz(old))
        rec = lambda t: block_after(part(7, t), "**Recovery procedure")
        self.assertEqual(rec(new), rec(old))
        note = lambda t: part(7, t)[part(7, t).index("The on-screen banner line"):part(7, t).index("**RUN 14 — ")]
        self.assertIn("does not apply here", note(new))
        self.assertIn(note(new).split("**THE FORBIDDEN WALK")[0].strip(), note(old))
        for blk in ("DOL          build/poc/gbp-video-stream-probe/gbp-video-stream-probe.dol   513 152 B",
                    "console            the same physical GameCube as RUN 13 (operator declares)",
                    "DOL on SD    /media/rafael/SD_GC/Open-GBP/12-stream/boot.dol"):
            self.assertIn(blk, new)

    def test_the_amendment_is_dated_pre_hardware_and_says_who_authorises_what(self):
        p = plain(part(2))
        for tok in ("PRE-HARDWARE AMENDMENT — 2026-09-21, GitHub Issue #23", "No run had executed and no result existed",
                    "changing a gate after seeing data", "never a silent edit", "the ORDER OF EXECUTION and nothing else",
                    "RUN 14 the checker's counted walk A", "RUN 15 the checker's counted walk B",
                    "RUN 16 OPTIONAL and INDEPENDENT", "A NEGATIVE CONTROL", "Z unmapped, the C stick unread",
                    "not reconstructible by anyone but him", "so the reassignment is not silent",
                    "Hardware Issue #21 authorises RUN 14", "the Orchestrator's to align to walk A", "RUN 15 needs its own",
                    "Nothing in this part authorises anything", "Why the checker is the instrument of the first executed run",
                    "answers Question O strictly better", "the practical reason", "keysDown()", "VBlankIntrWait()", "consoleDemoInit()",
                    "no splash, no menu, no START gate", "A single-press-each walk is therefore FORBIDDEN", "1 + 2 + … + 10 = 55 presses",
                    "re-derived for a NOR boot", "55 fits only at a sustained two presses per second", "not with margin",
                    "RUN 14 = walk A (L 1, R 2, A 3, B 4, SELECT 5, START 6", "RUN 15 = walk B (L 1, R 2, UP 3, DOWN 4, LEFT 5, RIGHT 6",
                    "Recorded and NOT chosen", "The unregistered exploratory trial of 2026-09-21", "It is NOT RUN 14 and can never become it",
                    "supports no claim and touches no gate", "did NOT occur in the trial", "an informal observation, never a result",
                    "U-GBP-010 stays OPEN and the descriptor stays as it is", "Two channels, and why the distinct counts stay",
                    "make the END STATE self-describing", "Prior exposure, recorded so a future reader can weigh it", "no longer naive",
                    "what number is on the screen", "a photograph of the FINAL TALLY SCREEN"):
            self.assertIn(tok, p, tok)
        a = plain(part(3))
        for tok in ("https://github.com/nataliethenerd/enhancedcontrolcheckerGBA", CHECKER_COMMIT, "CC BY-SA 4.0", "69 348 B",
                    CHECKER_SHA, "NOTHING from it enters the repository", "never a gate", "boots straight into"):
            self.assertIn(tok, a, tok)
        g = plain(part(6))
        for tok in ("boots straight into the Enhanced Control Checker on its NOR", "unregistered trial of 2026-09-21", "MOVED ASIDE, never deleted",
                    "steps 1-3 above were performed on the host on 2026-09-21 under Hardware Issue #21"):
            self.assertIn(tok, g, tok)
        self.assertIn("Reassignment, stated (Issue #23, before any run)", plain(part(5)))
        self.assertIn("byte-identical to the pre-registration of Issue #20", plain(part(12)))
        self.assertIn("Hardware Issue #21 (RUN 14) is the Orchestrator's to align", plain(part(12)))

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
                    "booting STRAIGHT INTO IT", "The EZ-Flash menu is NOT required", "coord-0002 is no longer the NOR image",
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
