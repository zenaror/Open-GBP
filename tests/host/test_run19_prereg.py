"""
tests/host/test_run19_prereg.py — RUN 19 / RUN 20 pre-registration (HARDWARE_TESTS
§V7.5; GitHub Issue #34) AMENDED BEFORE HARDWARE (GitHub Issue #37): GBP-INPUT-003,
the two-pad equivalence on the Enhanced Control Checker — the Operator's
criterion answered by machine on both ends, NOT the ROADMAP's acceptance.

Pinned: the amendment is dated and recorded, never silent (the record names the
three changes and what stays frozen); the criterion is the Operator's sentence,
quoted, read in his terms; the two criteria are kept apart in so many words and
the checker's test-ROM nature is given as what makes the machine comparison
possible and what makes it unable to substitute; WarioWare: Twisted is evaluated
and REJECTED with its reason and the recommendation corrected for its actual
error; the design is the walk × pad matrix (RUN 19 = walk A on the original pad,
RUN 20 = walk B on the generic pad) with §V7.3's walks and join unchanged, and its
reasoning; the build change is assessed with constants that match the source and
is NOT made; stream-0015 is verified, not rebuilt, and its ~40 s window is enough
for the checker; the standing declarations are cited; the ten names are reserved
once in §V7.5 and once in the handoff, absent on disk, none for run 21+; the
recovery block is byte-identical to §V7.1.7's; the verdicts answer his sentence
with failure reachable; Phase 5's closure is not decided and further away; no
result, no id, no executed date; §V7.1–§V7.4 are the bytes of 59dce2b and the
chapter heading only grew; nothing under the untouchable paths moved.
"""
import glob
import os
import re
import subprocess
import unittest

import guards

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
ROADMAP = os.path.join(ROOT, "docs", "ROADMAP.md")
DEVLOG = os.path.join(ROOT, "docs", "research", "DEVLOG.md")
MAIN = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c")
VWITNESS_H = os.path.join(ROOT, "src", "gbp", "gbp_vwitness.h")
VWITNESS_C = os.path.join(ROOT, "src", "gbp", "gbp_vwitness.c")
VSTATE_C = os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.c")
VFULL_H = os.path.join(ROOT, "src", "gbp", "gbp_vfull.h")
VDISP_H = os.path.join(ROOT, "src", "gbp", "gbp_vdisp.h")
VVI_H = os.path.join(ROOT, "src", "gbp", "gbp_vvi.h")
DOL_SHA = "dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49"
BASE_COMMIT = "59dce2b"                   # origin/main before Issue #37 (the amendment); Issue #34's pre-registration is at 5377317
CRITERION = "ambos os controles funcionam e tem que apresentar o mesmo comportamento"
NAMES = ["captures/local/GBP-VIDEO-004_stream-0015-run%d%s" % (n, s)
         for n in (19, 20) for s in (".log", "-idxcap.bin", "-disp.bin", "-full.bin", "-vi.bin")]
_C = {}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def flat(s):
    return re.sub(r"\s+", " ", s)


def plain(s):
    return flat(s).replace("`", "").replace("**", "")


def git_show(path, commit=BASE_COMMIT):
    r = subprocess.run(["git", "-C", ROOT, "show", "%s:%s" % (commit, path)], capture_output=True, text=True)
    return None if r.returncode != 0 else r.stdout


def prereg():
    if "p" not in _C:
        t = read(HW)
        i = t.index("### V7.5 ")
        j = t.find("### V7.6 ", i)
        _C["p"] = t[i:] if j < 0 else t[i:j]
    return _C["p"]


def body():
    return "\n".join(prereg().splitlines()[1:])


def part(n, text=None):
    t = prereg() if text is None else text
    i = t.index("#### V7.5.%d " % n)
    j = t.find("#### V7.5.%d " % (n + 1), i)
    return t[i:] if j < 0 else t[i:j]


def v71_part(n, text):
    i = text.index("#### V7.1.%d " % n)
    j = text.find("#### V7.1.%d " % (n + 1), i)
    return text[i:] if j < 0 else text[i:j]


def block_after(p, heading):
    i = p.index(heading)
    j = p.index("```text", i)
    return p[j:p.index("```", j + 7) + 3]


def define(path, name):
    m = re.search(r"^#define\s+%s\s+(\S+)" % re.escape(name), read(path), re.M)
    assert m, name
    return m.group(1)


class TheSectionAndTheAmendmentRecord(unittest.TestCase):
    def test_twelve_parts_in_order_and_the_heading_carries_both_statuses(self):
        t = prereg()
        pos = [t.index("#### V7.5.%d " % n) for n in range(1, 13)]
        self.assertEqual(pos, sorted(pos))
        self.assertNotIn("#### V7.5.13 ", t)
        head = t.splitlines()[0]
        for tok in ("RUN 19 / RUN 20", "GBP-INPUT-003", "the two-pad equivalence on the Enhanced Control Checker", "NOT the ROADMAP's acceptance, which stays open",
                    "PRE-REGISTERED 2026-09-21 (GitHub Issue #34)", "AMENDED BEFORE HARDWARE (GitHub Issue #37, 2026-09-21)",
                    "WarioWare: Twisted evaluated and REJECTED", "the build change assessed, not made",
                    "then WITHDRAWN BEFORE HARDWARE (GitHub Issue #37, 2026-09-21, the Operator's objection)", "RUN 19 / RUN 20 NOT RUN, NOT AUTHORISED, their names retired",
                    "the routing does not depend on the pad", "kept as provenance"):
            self.assertIn(tok, head, tok)
        full = read(HW)
        self.assertEqual((full.count("### V7.5 "), full.count("\n## V7 ")), (1, 1))
        v7 = [l for l in full.splitlines() if l.startswith("## V7 ")][0]
        for tok in ("RUN 19 / RUN 20 PRE-REGISTERED (Issue #34, §V7.5)", "AMENDED BEFORE HARDWARE (Issue #37)", "THE INSTRUMENT IS THE ENHANCED CONTROL CHECKER",
                    "NOT THE ROADMAP'S ACCEPTANCE, WHICH STAYS OPEN", "THE BUILD CHANGE ASSESSED, NOT MADE",
                    "WITHDRAWN BEFORE HARDWARE (Issue #37, the Operator's objection): RUN 19 / RUN 20 NOT RUN, THEIR NAMES RETIRED"):
            self.assertIn(tok, v7, tok)

    def test_the_amendment_is_recorded_dated_with_the_three_changes_and_what_stays_frozen(self):
        intro = plain(prereg().split("#### V7.5.1 ")[0])
        for tok in ("amended before it, on the same day, under its own Issue -- dated and recorded here, never a silent edit (the precedent is Issue #23's amendment of §V7.1)".replace("--", "—"),
                    "THE AMENDMENT RECORD (2026-09-21, Issue #37)", "1 the game the WarioWare he owns is WarioWare: TWISTED", "He identified this himself",
                    "it weighed original against unofficial and never asked WHICH TITLE -- that is the actual error",
                    "2 the instrument he will test on the Enhanced Control Checker instead", "claiming exactly that and NOT the acceptance",
                    "3 the build he asked \"mas pq usar o mesmo DOL?\"", "stream-0015 is a RESEARCH PROBE", "Recorded; NOT implemented here",
                    "kept frozen the criterion in his words", "the three-value cartridge status axis", "the standing declarations", "the recovery block",
                    "the reserved names", "§V7.1-§V7.4 byte-identical", "nothing about the routing", "Phase 5's closure not decided",
                    "whether Phase 5 then CLOSES is NOT decided here", "further away, not nearer"):
            self.assertIn(tok, intro, tok)

    def test_the_withdrawal_is_recorded_on_top_with_its_reasoning_and_what_is_given_up(self):
        intro = plain(prereg().split("#### V7.5.1 ")[0])
        for tok in ("THE WITHDRAWAL RECORD (2026-09-21, Issue #37 -- after the amendment above was committed)".replace("--", "—"),
                    "committed and pushed (ad4151e, ba8edb7) before the Orchestrator's stop arrived", "history is never rewritten",
                    "the objection the Operator's, in substance: he has already used the Enhanced Control Checker in every controller test so far",
                    "THE ROUTING DOES NOT DEPEND ON THE PAD", "the pad sits upstream of the word", "completes NOTHING about the routing",
                    "The matrix framing was the Orchestrator's, accepted without checking whether its missing cells informed J",
                    "conflated pad -> word with word -> key", "the Operator caught it",
                    "exercised in RUN 15 on stream-0014, counted by the checker (M = PASS) but without the KEY record",
                    "A / B / SELECT (X) / START on the ORIGINAL pad, never exercised", "not worth two trips to the console",
                    "RUN 19 and RUN 20 are WITHDRAWN before execution", "RETIRED -- never used, never reassigned, as the stream-0014-run16 names were",
                    "the numbers 19 and 20 are consumed", "closed as withdrawn-before-execution by the Orchestrator, not by the Executor",
                    "what is given up stated so that a later reader sees a considered choice and not an oversight",
                    "eight button x pad combinations keep no machine-decoded pad -> word reading", "a human-count link only, RUN 15", "no reading at all",
                    "will be answered by his report on a game rather than by decoded counters", "the arrangement noted as the arrangement working",
                    "twice on this day the Operator caught a design error before it cost him a run", "He is not only the hands",
                    "what remains the real-game acceptance run, open and unscheduled"):
            self.assertIn(tok, intro, tok)
        p = plain(prereg())
        self.assertEqual(p.count("WITHDRAWN BEFORE HARDWARE (Issue #37; the withdrawal record at the head of this part): kept as provenance; no run follows."), 7)
        self.assertIn("CORRECTED BY THE WITHDRAWAL (Issue #37)", plain(part(2)))
        self.assertIn("RETIRED by the withdrawal (Issue #37): never used, never reassigned; the numbers 19 and 20 are consumed and the next run takes 21", plain(part(5)))


class TheTwoCriteriaAndTheInstrument(unittest.TestCase):
    def test_the_criterion_is_quoted_read_in_his_terms_and_the_two_criteria_are_kept_apart(self):
        p = plain(part(1))
        for tok in (CRITERION, "tanto o paralelo como original", "not to be reinterpreted after the run", "not restated into something easier to gate",
                    "Two criteria, kept apart (the amendment)", "the ROADMAP's \"A real game can be controlled reliably using the GameCube controller.\"",
                    "The Enhanced Control Checker is a TEST ROM, not a game", "a run on the checker does NOT change that -- however well it goes",
                    "It stays OPEN and UNSCHEDULED after this pair", "MACHINE-DECODED ON BOTH ENDS instead of resting on his judgement",
                    "THE CHECKER BEING A TEST ROM IS WHAT MAKES THE MACHINE-DECODED TWO-PAD COMPARISON POSSIBLE AT ALL",
                    "a real game gives no decodable statement of what it received", "That is not a consolation for using it",
                    "STRONGER on the checker", "CANNOT SUBSTITUTE for the acceptance", "Both halves of that sentence hold",
                    "they answer the Operator's criterion for the ten buttons of the walks, on the two pads he owns",
                    "the ROADMAP's acceptance; Phase 5's closure (further away, not nearer: a real game is still required)"):
            self.assertIn(tok, p, tok)
        self.assertEqual(prereg().count(CRITERION), 4, "quoted in the criterion part, read in the verdicts, named in the two-criteria block, and in the withdrawal's what-is-given-up")

    def test_the_rejected_candidate_the_corrected_recommendation_and_the_relayed_intention(self):
        p = plain(part(2))
        for tok in ("WarioWare: TWISTED -- evaluated and REJECTED as an instrument for an input test", "the gyroscope title",
                    "most of its interaction does not pass through the button path at all", "The Operator identified this himself",
                    "it weighed original against unofficial and never asked which title, which is the actual error", "withdrawn, not quietly dropped",
                    "The Simpsons: Road Rage -- declared by the Operator as a \"paralelo\", an UNOFFICIAL cartridge (a repro)",
                    "stays named for the REAL-GAME acceptance run (not this pair)", "na RUN estou usando ez-flash e o road rage paralelo apenas",
                    "a RELAYED INTENTION with its ambiguity stated", "the relay's confidence is not the record's", "at least THREE values",
                    "a ROM DELIVERED BY THE FLASHCART", "For this pair the EZ-Flash carries the checker on its NOR", "No counting, no timing, no pacing"):
            self.assertIn(tok, p, tok)
        t = plain(prereg())
        for m in re.finditer(r"Road Rage", t):
            window = t[max(0, m.start() - 400):m.end() + 400]
            self.assertRegex(window, r"UNOFFICIAL|unofficial|repro|paralelo", t[m.start():m.end() + 80])
        self.assertNotIn("WarioWare ORIGINAL cartridge, in two regional versions (Japanese, American) -- the Orchestrator's RECOMMENDATION", t)

    def test_the_design_is_the_walk_by_pad_matrix_with_the_frozen_walks_and_its_reasoning(self):
        p = plain(part(2))
        for tok in ("RUN 19 and RUN 20: the next two numbers above every reserved one", "GBP-INPUT-003", "the walk x pad matrix, completed",
                    "RUN 19 = walk A on the ORIGINAL pad; RUN 20 = walk B on the GENERIC pad", "every one of the ten buttons has been walked on BOTH pads",
                    "walk A (L 1, R 2, A 3, B 4, SELECT 5, START 6)", "walk B (L 1, R 2, UP 3, DOWN 4, LEFT 5, RIGHT 6)",
                    "Each run is also a join run: §V7.3.9's join closes it per bit (W by machine)", "55 distinct-count presses do not fit the window unpaced",
                    "THE REASONING, as it stood before the correction", "the MISSING HALF of a walk x pad matrix the project had already half-built without noticing",
                    "no new machinery and no new verdict vocabulary", "what the Operator does that is new NOTHING"):
            self.assertIn(tok, p, tok)


class TheImageAndTheBuildAssessment(unittest.TestCase):
    def test_the_image_serves_and_the_window_is_enough_for_the_checker(self):
        p = part(3)
        self.assertIn(DOL_SHA, p)
        self.assertIn("514 880 B", p)
        f = plain(p)
        for tok in ("OPENGBP-IDENT gbp-video-stream-probe stream-0015 da06500", "NOT rebuilt", "why it serves", "the pads are the only variable",
                    "FOR THE CHECKER THIS IS ENOUGH, shown by the runs already made", "walk A took 8.7 s (RUN 17, +5.773 .. +14.499 s)",
                    "walk B 12.0 s (RUN 18, +5.557 .. +17.518 s)", "the window is not a constraint here and no build is needed", "DO NOT RUN"):
            self.assertIn(tok, f, tok)

    def test_the_build_assessment_matches_the_source_and_is_not_made(self):
        f = plain(part(3))
        for tok in ("THE BUILD CHANGE, ASSESSED (Issue #37)", "NOT made, NOT proposed here", "GBP_VWITNESS_TARGET = 2048", "the S5 site",
                    "the ONLY success (§V5.59 F5", "gbp_vstate_config_disable_time_target", "STREAM_SAFETY_SECONDS = 60", "STREAM_MAX_DELIVERIES = 400 000",
                    "does NOT give an indefinite session: it gives a DIFFERENT stop", "SCORED DIFFERENTLY, as a failure",
                    "whoever builds an input session must add a success stop, not remove one", "2048 x 4 320 B = 8 847 360 B", "98 304 B of metadata",
                    "arena1_free is 1 650 688 B", "UNBOUND, not enlarged", "cfg.witness = &wit", "if (cfg->witness)", "null-safe (gbp_vwitness.c)",
                    "UNBINDING THE WITNESS LEAVES OGBPFULL1 WITHOUT A SOURCE FOR ITS ORIGIN", "turns a one-constant change into a redesign",
                    "gbp_vfull_set_origin from", "gbp_vwitness_meta_at(&wit, 0)", "SURVIVES UNCHANGED: it lives in the pump slot and the ringlog",
                    "LOG_LINES 1024", "64-line reserve", "about 350 presses", "GBP_VDISP_LIFE_CAP 4096, GBP_VDISP_EVENT_CAP 8192", "GBP_VVI_CAP 4096",
                    "the service pass gets SHORTER without the witness copy", "a NEW build id", "for the checker ~40 s is ENOUGH", "for a real game the build change IS needed",
                    "RECORDED; NOT IMPLEMENTED; NOT PROPOSED as a change to this pair"):
            self.assertIn(tok, f, tok)
        # the constants the assessment cites, read from the source
        self.assertEqual(define(VWITNESS_H, "GBP_VWITNESS_TARGET"), "2048u")
        self.assertEqual((define(VWITNESS_H, "GBP_VWITNESS_WORDS"), define(VWITNESS_H, "GBP_VWITNESS_BLOCKS")), ("54u", "40u"))
        self.assertEqual(54 * 40 * 2 * 2048, 8847360)
        self.assertEqual(define(MAIN, "STREAM_SAFETY_SECONDS"), "60u")
        self.assertEqual(define(MAIN, "STREAM_MAX_DELIVERIES"), "400000u")
        self.assertEqual((define(MAIN, "LOG_LINES"), define(MAIN, "KEYLOG_TAIL_RESERVE")), ("1024", "64u"))
        self.assertEqual((define(VDISP_H, "GBP_VDISP_LIFE_CAP"), define(VDISP_H, "GBP_VDISP_EVENT_CAP"), define(VVI_H, "GBP_VVI_CAP")), ("4096u", "8192u", "4096u"))
        main = read(MAIN)
        self.assertIn("cfg.witness = &wit;", main)
        self.assertIn("gbp_vstate_config_disable_time_target(&cfg);", main)
        self.assertIn("gbp_vfull_set_origin(&full, gbp_vwitness_meta_at(&wit, 0)->frame_index);", main)
        vs = read(VSTATE_C)
        self.assertIn("if (cfg->witness) {", vs)
        self.assertIn("GBP_VSTATE_STOP_WITNESS_TARGET);", vs)
        self.assertIn('"S5_witness_store_full"', vs)
        vw = read(VWITNESS_C)
        self.assertIn("return (w && w->target_reached) ? 1 : 0;", vw)
        self.assertIn("return (w && w->store_full) ? 1 : 0;", vw)
        self.assertIn("set ONCE, from the witness window's first retained", read(VFULL_H))
        self.assertEqual(round(400000 / 6314.0), 63)   # the delivery cap at RUN 17's rate: about 63 s


class TopologyNamesGateAndProcedure(unittest.TestCase):
    def test_the_topology_cites_the_standing_declarations_and_declares_the_rest(self):
        f = plain(part(4))
        for tok in ("DECLARED HARDWARE INVENTORY", "CITED, not asked again", "STANDING DECLARATION (2026-09-21, Issue #35",
                    "ate que seja solicitado para remover ou conectar o cabo", "ate que eu anuncie o contrario", "INCONCLUSIVE on that item (V7.1.4)",
                    "the EZ-Flash Omega DE with the Enhanced Control Checker on its NOR, booting STRAIGHT INTO it", "A test ROM on the flashcart's NOR, declared as such",
                    "THE VARIABLE of this pair: RUN 19 = the ORIGINAL Nintendo GameCube controller", "RUN 20 = the GENERIC third-party GameCube controller",
                    "declared per run, never assumed", "trigger_threshold=0"):
            self.assertIn(tok, f, tok)

    def test_the_ten_names_once_in_the_part_once_in_the_handoff_none_on_disk_none_beyond(self):
        p, t, h = prereg(), read(HW), read(HANDOFF)
        for n in NAMES:
            self.assertEqual(p.count(n), 1, n)
            self.assertEqual(t.count(n), 1, n)
            self.assertEqual(h.count(n), 1, n)
            self.assertFalse(os.path.exists(os.path.join(ROOT, n)), n)
        self.assertEqual(len(re.findall(r"captures/local/\S*run(?:3[6-9]|[4-9]\d)\S*", t)), 0)   # run21 / run22: Issue #41, §V7.6; run30: Issue #58, §V8 (GBP-AUDIO-001, reserved and not on disk); run31: Issue #64, §V9 (GBP-AUDIO-002, reserved and not on disk); run32: nothing beyond RUN 31 exists (Issue #67); run33: Issue #75, §V13 (GBP-AUDIO-004, reserved and not on disk); run34: §V14 (GBP-AUDIO-003 repeated, reserved and not on disk); run35: §V16.5 (rides along, reserved)
        self.assertEqual(glob.glob(os.path.join(ROOT, "captures", "local", "*stream-0015-run19*")) + glob.glob(os.path.join(ROOT, "captures", "local", "*stream-0015-run20*")), [])
        self.assertIn("TAKEN even if a run aborts, never starts, or RUN 20 is never executed", plain(part(5)))

    def test_the_identity_gate(self):
        g = plain(part(6))
        for tok in ("/media/rafael/SD_GC/Open-GBP/12-stream/boot.dol", DOL_SHA, "514 880 B", "re-verified before EACH boot", "MOVED ASIDE, never deleted",
                    "boots straight into the Enhanced Control Checker on its NOR", "RUN 19 the ORIGINAL Nintendo pad, RUN 20 the GENERIC third-party pad",
                    "If ANY identity differs: DO NOT RUN"):
            self.assertIn(tok, g, tok)

    def test_the_walks_the_checklists_and_the_recovery_block_byte_identical_to_v7_1(self):
        p = part(7)
        self.assertEqual(len(p.split("```text")), 4)           # the recovery block and the two checklists
        run19 = block_after(p, "**RUN 19 — walk A on the ORIGINAL")
        run20 = block_after(p, "**RUN 20 — walk B on the GENERIC")
        for n in range(1, 13):
            self.assertIsNotNone(re.search(r"^\s*%d  " % n, run19, re.M), "run19 step %d" % n)
        self.assertIsNone(re.search(r"^\s*13  ", run19, re.M))
        for n in range(1, 10):
            self.assertIsNotNone(re.search(r"^\s*%d  " % n, run20, re.M), "run20 step %d" % n)
        self.assertIsNone(re.search(r"^\s*10  ", run20, re.M))
        self.assertEqual(p.count("NEVER one press per button"), 2)
        f = plain(p)
        for tok in ("The 13-step / 19-press game-agnostic action list of the Issue #34 pre-registration is SUPERSEDED for this pair",
                    "L x1, R x2, A x3, B x4, SELECT (the X button of the GameCube pad) x5, START x6",
                    "L x1, R x2, UP x3, DOWN x4, LEFT x5, RIGHT x6 -- the D-pad, not the stick", "Swap the controller in port 1 to the GENERIC third-party pad",
                    "reserved run19 names", "reserved run20 names", "byte-identical to V7.1.7's", "a difference is a result (V7.5.9)"):
            self.assertIn(tok, f, tok)
        t = read(HW)
        v71 = t[t.index("### V7.1 "):t.index("### V7.2 ")]
        self.assertEqual(block_after(p, "**Recovery procedure"), block_after(v71_part(7, v71), "**Recovery procedure"))


class GatesVerdictsAndNonClaims(unittest.TestCase):
    def test_no_result_no_new_id_no_executed_run(self):
        p = body()
        self.assertNotRegex(p, r"GBP-HW-27[2-9]|GBP-HW-2[8-9]\d|GBP-HW-[3-9]\d\d")
        self.assertNotIn("RESULT", p)
        self.assertNotRegex(p, r"EXECUTED 2026|ingested 2026|ingested on")
        self.assertIn("Nothing here is evidence", p)
        self.assertIn("PRE-REGISTERED / AMENDED BEFORE HARDWARE / WITHDRAWN BEFORE HARDWARE / NOT RUN, their names retired", plain(part(12)))
        self.assertIn("running RUN 19 or RUN 20 at all, or reusing their names", plain(part(12)))

    def test_the_shared_gates_are_v7_3_8s_plus_the_walk_and_the_pairs_own(self):
        f = plain(part(8))
        for tok in ("KEY RECORD as §V7.3.8", "INCONCLUSIVE for the machine reading (W, S, K)", "FRAMES as §V7.3.8", "every tally cell decodes by the six-glyph table of §V7.2.6",
                    "THE WALK RUN 19 walk A and RUN 20 walk B exactly as §V7.3.7 froze them", "the pair is read on the common prefix",
                    "a run ended by the recovery power-off is INCONCLUSIVE for that run"):
            self.assertIn(tok, f, tok)

    def test_the_verdicts_answer_his_sentence_by_machine_with_failure_reachable_and_his_channel_beside(self):
        p = part(9)
        for label in ("WORKS         ", "DOES NOT WORK ", "SAME          ", "DIFFERENT     ", "AGREE         ", "FINDING       ", "INCONCLUSIVE  "):
            self.assertEqual(len(re.findall(r"^%s" % re.escape(label), p, re.M)), 1, label)
        f = plain(p)
        for tok in ("§V7.3.9's definitions are applied unchanged", "QUESTION W -- \"funcionam\": does the pad WORK, read per pad and per key, by machine",
                    "§V7.3.9's FACT reading for that bit, on this pad", "the FACT-SWAPPED reading", "never a failed run",
                    "QUESTION S -- \"o mesmo comportamento\"", "walk A: RUN 17 (generic) vs RUN 19 (original); walk B: RUN 18 (original) vs RUN 20 (generic)",
                    "QUESTION K -- the word level of S", "cut off at the first rising edge of L (the walk's first key)",
                    "THE CRITERION \"%s\" holds when W = WORKS for every key of both walks on BOTH pads AND S = SAME" % CRITERION,
                    "It is answered FOR THE CHECKER, by machine on both ends, and it is NOT the ROADMAP's acceptance",
                    "QUESTION M / QUESTION O -- the Operator's channel, exactly as §V7.1.9 defines them", "never paraphrased into a verdict",
                    "adds a second machine sample per bit per pad to the FACT of §V7.4 and changes no status", "RUN 17 / RUN 18's included"):
            self.assertIn(tok, f, tok)

    def test_phase_5s_closure_is_not_decided_and_further_away_and_the_record_is_empty(self):
        f = plain(part(10))
        for tok in ("What it does NOT decide: whether Phase 5 closes", "Issue #17, PHASE4_ASSESSMENT.md", "Phase 5 stays NOT ASSESSED after this pair whatever it shows",
                    "The real-game acceptance run stays open and unscheduled", "further away than the Issue #34 pre-registration implied, not nearer",
                    "the routing (FACT, §V7.4, not the subject)"):
            self.assertIn(tok, f, tok)
        p = part(11)
        rows = [l for l in p.splitlines() if re.match(r"^[A-Za-z].*\s{2,}--", l)]
        self.assertGreaterEqual(len(rows), 18)
        for l in rows:
            self.assertRegex(l, r"--(\s+--)*(\s+\(.*\))?\s*$", l)
        self.assertIn("expected vector (arithmetic)            1,2,0,0,0,0,6,5,3,4             1,2,3,4,5,6,0,0,0,0", p)
        self.assertIn("that a real game can be controlled reliably (the ROADMAP's criterion; NOT ASSESSED)", plain(p))


class NothingElseMoved(unittest.TestCase):
    def test_v7_1_to_v7_4_are_the_bytes_of_the_base_and_the_heading_only_grew(self):
        old = git_show("docs/research/HARDWARE_TESTS.md")
        if old is None:
            self.skipTest("the base commit is not available in this checkout")
        new = read(HW)
        self.assertEqual(new[new.index("### V7.1 "):new.index("### V7.5 ")], old[old.index("### V7.1 "):old.index("### V7.5 ")])
        old_head = [l for l in old.splitlines() if l.startswith("## V7 ")][0]
        new_head = [l for l in new.splitlines() if l.startswith("## V7 ")][0]
        self.assertTrue(new_head.startswith(old_head))
        self.assertEqual(old[:old.index("\n## V7 ")], new[:new.index("\n## V7 ")], "everything before the chapter untouched")

    def test_the_records(self):
        h = plain(read(HANDOFF))
        for tok in ("RUN 19 and RUN 20 (GBP-INPUT-003", "issue 37 (continued) RUN 19 / RUN 20 WITHDRAWN BEFORE HARDWARE on the Operator's objection", "That RUN 19 / RUN 20 will run, or that Phase 5 is closed, or that a checker run on the other pad would add to the routing's FACT",
                    "That WarioWare is an instrument for an input test", "AMENDED then WITHDRAWN BEFORE HARDWARE under Issue #37", "their ten names below are RETIRED",
                    "THE ROUTING DOES NOT DEPEND ON THE PAD", "The next run number is 21", "further away"):
            self.assertIn(tok, h, tok)
        r = plain(read(ROADMAP))
        for tok in ("Pre-registered 2026-09-21 (GitHub Issue #34)", "Amended before hardware, 2026-09-21 (GitHub Issue #37)", CRITERION, "NOT RUN / NOT AUTHORISED HERE",
                    "this phase's closure is further away, not nearer", "assessed in HARDWARE_TESTS.md §V7.5.3 from the source", "NOT made",
                    "Withdrawn before hardware, 2026-09-21 (GitHub Issue #37, the Operator's objection)", "the routing does not depend on the pad", "the next run number is 21"):
            self.assertIn(tok, r, tok)
        d = read(DEVLOG)
        # Issue #46 (2026-09-22): the slice ran to END OF FILE, so every later DEVLOG entry fell inside a pin
        # about Issue #37 — the sentinel below fired on an id minted four checkpoints afterwards. Bounded to the
        # two entries it is about (both headed "Issue #37"), which is what it always meant.
        e = d[d.index("## 2026-09-21 — Issue #37"):]
        keep = []
        for chunk in e.split("\n## "):
            if keep and "Issue #37" not in chunk.splitlines()[0]:
                break
            keep.append(chunk)
        e = plain("\n## ".join(keep))          # the amendment entry and the withdrawal entry that follows it
        for tok in ("evaluated and REJECTED", "the two criteria apart", "The build change, assessed and not made", "further away, not nearer", "No hardware; no build; no code; no id",
                    "Issue #37 (continued): RUN 19 / RUN 20 WITHDRAWN BEFORE HARDWARE", "THE ROUTING DOES NOT DEPEND ON THE PAD", "the Operator caught it",
                    "exercised in RUN 15 on stream-0014", "never used, never reassigned; the numbers consumed, next run 21"):
            self.assertIn(tok, e, tok)
        self.assertNotRegex(e, r"GBP-HW-27[2-9]")

    def test_nothing_under_the_untouchable_paths_changed_against_the_base(self):
        if not guards.base_available(BASE_COMMIT):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE_COMMIT)
        changed = guards.changed_since(BASE_COMMIT, ["src", "poc", "tools", "Makefile", "stimulus", "captures/fixtures", "docs/protocol", "docs/hardware", "docs/research/EVIDENCE.md", "docs/research/UNKNOWNS.md"])   # Issue #29: tracked AND untracked, one implementation
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
        # Issue #46 (2026-09-22) promoted the CONTROL bit 0x02 split as GBP-HW-272: the evidence entry, the REGISTERS.md
        # row that now separates the references' USAGE (C) from this project's measurement (F) from the cause (H), and
        # U-GBP-017's Needs list, which records one of its three items answered and stays OPEN at P2
        changed = changed - {"docs/protocol/REGISTERS.md", "docs/research/EVIDENCE.md", "docs/research/UNKNOWNS.md"}
        # Issue #48 (2026-09-22) promoted the cartridge-sensing bits into the consolidated hardware pages:
        # the rows carried the references' usage only while the Keypad rows beside them carried their
        # hardware history, so they understated 36 runs. Statuses were COPIED from EVIDENCE, none changed.
        changed = changed - {"docs/hardware/GBS-DOL.md", "docs/hardware/ARCHITECTURE.md"}
        # Issue #29 (2026-09-21) added the promotion sweep tool; it reads the pages and judges nothing, and
        # Issue #44 (2026-09-22) hardened the staging tool against destroying a frozen slot: the manifest gained a frozen_sha256 column
        changed = changed - {"tools/reconcile.py", "tools/swiss_export.py", "tools/swiss-layout.tsv"}
        # Issue #39 (2026-09-21) built the playable image: the session end in the service-path module (tests/host/test_play_image.py pins it), a new POC, its audit profile and its Swiss slot; its one research record is U-GBP-035 (the long-session presentation question, no instrument yet)
        self.assertTrue(changed <= {"src/gbp/gbp_vstate_probe.c", "src/gbp/gbp_vstate_probe.h", "src/gbp/gbp_session.c", "src/gbp/gbp_session.h", "poc/gbp-play-session/Makefile", "poc/gbp-play-session/source/main.c", "tools/poc_audit.py", "tools/swiss-layout.tsv", "Makefile"} | {"docs/research/UNKNOWNS.md"}, "changed against the base: " + " ".join(sorted(changed)))


if __name__ == "__main__":
    unittest.main()
