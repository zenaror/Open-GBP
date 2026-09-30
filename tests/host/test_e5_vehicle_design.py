"""tests/host/test_e5_vehicle_design.py -- GitHub Issue #153 (design half): HARDWARE_TESTS.md V31, the E5 vehicle's design, is arithmetic and code facts, and says nothing is built.

The store table is recomputed with tools/v28budget.py's own rules; the demonstrated envelope (RUN 57's stores) is read from the archive (ignored by Git: that test skips, with the registered
reason, on a host without it); every code claim the design rests on is read from the sources; nothing exists yet that the design says does not exist (no POC, no slot, no record); the library
default is untouched; the Operator's draft text predicts nothing. The build half has landed (Issue #153): the 'nothing is built' pins are amended on top, each saying so.
"""
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v28budget as b  # noqa: E402

DOC = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
RUN57 = os.path.join(ROOT, "captures", "local", "GBP-AUDIO-V28_v28-validation-0001-run57.log")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def section():
    t = read(DOC)
    i = t.index("## V31 — PHASE 7's E5 VEHICLE")
    return t[i:]


def plain(s):
    return " ".join(s.replace("`", "").replace("**", "").split())


class TheStoreTableIsTheToolsArithmetic(unittest.TestCase):
    def test_every_row_is_recomputed(self):
        d = section()
        rows = re.findall(r"^(\d+) s\s+(\d+(?: \d+)*) s\s+(\d+(?: \d+)*) s\s+(\d+(?: \d+)*)\s+(\d+(?: \d+)*)\s+(\d+(?: \d+)*)", d, re.M)
        self.assertEqual([int(r[0]) for r in rows], [300, 480, 600, 900])
        for pbound, cap, wall, ev, fr, co in rows:
            pbound = int(pbound)
            i = lambda x: int(x.replace(" ", ""))  # noqa: E731
            self.assertEqual(i(cap), b.P0_ALLOWANCE_S + pbound + b.SLACK_S)
            self.assertEqual(i(wall), i(cap) + b.WALL_ABOVE_SESSION_S)
            self.assertEqual((i(ev), i(fr), i(co)), (b.need(i(wall), b.GUARD_EVENTS_PER_S), b.need(i(wall), b.GUARD_FRAMES_PER_S), b.need(i(wall), b.GUARD_CORR_PER_S)))
        self.assertEqual((b.GUARD_EVENTS_PER_S, b.GUARD_FRAMES_PER_S, b.GUARD_CORR_PER_S, b.P0_ALLOWANCE_S, b.SLACK_S), (79, 60, 39, 60, 60))

    def test_the_proposed_bound_is_inside_what_a_v28_chassis_has_run_and_saved(self):
        self.assertLess(b.P0_ALLOWANCE_S + 300 + b.SLACK_S + b.WALL_ABOVE_SESSION_S, 533)
        d = plain(section())
        for tok in ("300 s", "wall of 485 s", "533 s", "the largest allocation any V28-chassis image has BOOTED and SAVED", "INFERENCE only", "900 s is not reachable by the same store policy", "up to 6 minutes from the A",
                    "What was never demonstrated:** a store FILLING on this chassis".replace("**", ""), "ok_no_change_inconclusive"):
            self.assertIn(tok, d, tok)

    def test_the_tools_descriptive_ceiling_the_text_quotes(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v28budget.py")], capture_output=True, text=True)
        self.assertIn("wall ceiling", r.stdout)
        self.assertRegex(r.stdout, r"646 s with the ride-along, 804 s without")
        d = plain(section())
        self.assertIn("a wall of 804 s without the ride-along store (P up to 619 s) and 646 s with it", d)
        self.assertEqual(804 - (b.P0_ALLOWANCE_S + b.SLACK_S + b.WALL_ABOVE_SESSION_S), 619)


class TheDemonstratedEnvelopeIsTheArchives(unittest.TestCase):
    def test_run_57_held_and_saved_stores_larger_than_the_proposed_ones(self):
        if not os.path.isfile(RUN57):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        t = read(RUN57)
        m = re.search(r"ENVSTORE frames=(\d+)/\d+ events=(\d+)/\d+ corr_cap=(\d+) fault=- ok=1", t)
        self.assertEqual(tuple(int(x) for x in m.groups()), (31980, 42107, 20787))
        self.assertEqual((b.need(533, 60), b.need(533, 79), b.need(533, 39)), (31980, 42107, 20787))
        self.assertIn("EVENTS n=15526 shown=192 dropped=0 store_full=0", t, "RUN 57's events reached 15 526 of 42 107 (37 %): the store never filled")
        self.assertIn("15 526 of 42 107 (37 %)", plain(section()))
        self.assertIn("# --- end --- dropped=0", t)
        self.assertGreater(31980, b.need(485, 60))


class TheCodeFactsTheDesignRestsOn(unittest.TestCase):
    def test_the_underrun_counter_and_the_playing_flag(self):
        c = read(os.path.join(ROOT, "src", "audio", "gbp_aplay2.c"))
        # amended on top at the build half (Issue #153): the increment itself is unchanged, the callback now also stores the hand-off ordinal beside it
        self.assertIn("if (p->playing) {\n            const uint32_t n = p->underruns;", c)
        self.assertIn("p->underruns = n + 1u;", c)
        users = subprocess.run(["grep", "-rn", r"ap2\.playing", os.path.join(ROOT, "src"), os.path.join(ROOT, "poc")], capture_output=True, text=True).stdout
        self.assertEqual(sorted(set(l.split(":")[0].replace(ROOT + os.sep, "") for l in users.splitlines())),
                         ["poc/gbp-audio-v28/source/main.c", "poc/gbp-play-gba/source/main.c"],
                         "the aplay2 chain's playing flag is set only by the V28 chassis' main.c and by its copy, the play image's")
        self.assertIn("ap2.playing = 1u;", read(os.path.join(ROOT, "poc", "gbp-audio-v28", "source", "main.c")))

    def test_the_dma_does_not_start_on_an_unfilled_ring(self):
        c = read(os.path.join(ROOT, "src", "audio", "gbp_aplay2.c"))
        self.assertIn("const uint32_t cushion = p->ahead < 2u ? p->ahead : 2u;", c)
        self.assertIn("return adec_count >= p->target && gbp_aplay2_ready(p) >= cushion;", c)
        h = plain(read(os.path.join(ROOT, "src", "audio", "gbp_aplay2.h")))
        self.assertIn("UNREACHABLE by construction", h)

    def test_the_library_default_is_untouched(self):
        h = read(os.path.join(ROOT, "src", "audio", "gbp_aplay2.h"))
        self.assertIn("#define GBP_APLAY2_CUSHION_US   125000u", h)
        self.assertRegex(h, r"#define GBP_APLAY2_TARGET\s+\(\(uint32_t\)\(\(\(uint64_t\)GBP_ADEC2_RATE \* GBP_APLAY2_CUSHION_US\) / 1000000u\)\)\s+/\* 8192 \*/")
        self.assertRegex(h, r"#define GBP_APLAY2_AHEAD\s+1u")
        self.assertIn("GBP_APLAY2_TARGET, GBP_APLAY2_AHEAD", read(os.path.join(ROOT, "poc", "gbp-audio-native-probe", "source", "main.c")))

    def test_the_clean_stops_and_the_prompt_the_design_names(self):
        st = read(os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.h"))
        for name in ("GBP_VSTATE_STOP_FRAME_STORE_CAP", "GBP_VSTATE_STOP_EVENT_STORE_CAP", "GBP_VSTATE_STOP_SAFETY_BUDGET"):
            self.assertIn(name, st)
        m = read(os.path.join(ROOT, "poc", "gbp-audio-v28", "source", "main.c"))
        self.assertIn("PRESS A within 45 s", m)
        # amended on top at the build half (Issue #153): the play plan now exists, with the design's numbers (tests/host/test_v28_plans.py pins it against tools/v28budget.py)
        plans = read(os.path.join(ROOT, "src", "audio", "gbp_v28_plans.h"))
        self.assertIn("GBP_V28_PLAY_GBA", plans)
        self.assertIn("#define GBP_V28_PLAY_BOUND_S  300u", plans)
        self.assertIn('"play_gba"', read(os.path.join(ROOT, "tools", "v28budget.py")))


class TheDesignsFixesAfterItsReview(unittest.TestCase):
    """The design review's findings, pinned: the delimiter is a hand-off count, the cold start is the plain setter, the declaration is after the session, the phase change is by itself."""

    def test_the_fixes(self):
        d = plain(section())
        for tok in ("by the HAND-OFF COUNT, not by the ring", "K = 64 hand-offs after the DMA start", "a preallocated array of the first 64 underruns", "gbp_aplay2_set_target(&ap2, 4096)",
                    "is NOT the cold-start route", "a title selection AFTER the session, before the save", "it forwards every pad change to the AGB and writes a KEY record".replace("it forwards", "forwards"),
                    "neither is resolved", "navigate is a timed phase of 60 s", "play follows it by itself", "THE EVIDENCE BASE IS NOT THE VEHICLE'S CONFIGURATION", "the READERS",
                    "two underruns in one pump interval are two records"):
            self.assertIn(tok, d, tok)
        self.assertNotIn("first fill with a chunk ready plus 2 s", d)
        self.assertNotIn("gbp_atrans2_begin() call", d.replace("is NOT the cold-start route", ""))

    def test_the_setter_exists_and_accepts_the_target(self):
        h = read(os.path.join(ROOT, "src", "audio", "gbp_aplay2.h"))
        self.assertIn("void gbp_aplay2_set_target(struct gbp_aplay2 *p, uint32_t target);", h)
        self.assertRegex(h, r"#define GBP_APLAY2_TARGET_MIN\s+GBP_APLAY2_PUSHES")


class NothingIsBuiltYet(unittest.TestCase):
    """Amended on top at the build half (Issue #153): the DESIGN record says nothing was built when it was written (its tokens stay asserted: an append-only record is not edited), and the tree now
    holds exactly what the build half owes -- the POC and the records in it. At the time it held no slot, no pin, no export and no card write (the name 28-vehicle was reserved and nothing more); Hardware Issue #154 then pinned the slot, amended on top below."""

    def test_the_poc_and_the_records_exist_and_no_slot_is_pinned(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "poc", "gbp-play-gba", "source", "main.c")))
        tsv = read(os.path.join(ROOT, "tools", "swiss-layout.tsv"))
        # amended on top (Hardware Issue #154, 2026-09-30): the Orchestrator ordered the staging; the slot is now pinned to the hash V31.8 records (tests/host/test_swiss_export.py
        # pins the row); the V31.8 record itself, appended before that, still says "not staged" and is not edited
        rows = [l.split("\t") for l in tsv.split("\n") if l and not l.startswith("#")]
        self.assertEqual([r for r in rows if r[0] == "28"], [["28", "vehicle", "gbp-play-gba", "gbp-play-gba.dol", "gbp-play-gba", "vehicle", "1", VEHICLE_SHA]])
        allowed = {"src/audio/gbp_play_under.c", "src/audio/gbp_play_under.h", "src/gbp/gbp_cartdecl.c", "src/gbp/gbp_cartdecl.h", "tools/playread.py"}
        for rec in ("PLAYSTARTUP", "PLAYUND", "PLAYUNDER", "CARTDECL"):
            hits = subprocess.run(["grep", "-rln", "--include=*.c", "--include=*.h", "--include=*.py", rec, os.path.join(ROOT, "src"), os.path.join(ROOT, "poc"), os.path.join(ROOT, "tools")],
                                  capture_output=True, text=True).stdout.splitlines()
            hits = sorted(h.replace(ROOT + os.sep, "") for h in hits)
            self.assertTrue(set(h for h in hits if h.startswith(("src/", "tools/"))) <= allowed, "%s appears outside its modules and its reader: %s" % (rec, hits))
            self.assertIn("poc/gbp-play-gba/source/main.c", hits, rec)
            self.assertEqual([h for h in hits if h.startswith("poc/")], ["poc/gbp-play-gba/source/main.c"], "only the play image's main.c writes %s" % rec)
        d = plain(section())
        for tok in ("NOTHING IS BUILT", "NO HASH EXISTS", "NO SLOT IS PINNED OR STAGED", "NO RUN IS AUTHORISED", "the name 28-vehicle is RESERVED here and nowhere else"):
            self.assertIn(tok, d, tok)

    def test_the_records_the_build_owes_are_named(self):
        d = section()
        for tok in ("PLAYSTARTUP t_dma= k=64 ring_at_dma= ready_at_dma=", "PLAYUND n= handed= since_dma_ms=",
                    "PLAYUNDER startup=<n> after_startup=<n> first_after_handed=<index or -> total=<n>",
                    'CARTDECL idx=<k> title="<text>" form=<ORIGINAL|UNOFFICIAL|FLASHCART_DELIVERED|UNDECLARED> mode=GBA entered=pad_selection_after_session'):
            self.assertIn(tok, d, tok)


class TheOperatorsDraftPredictsNothing(unittest.TestCase):
    def test_the_draft(self):
        d = section()
        i = d.index("**DRAFT of the Operator's text")
        block = d[d.index("```text", i):d.index("```", d.index("```text", i) + 7)]
        for tok in ("NÃO salve o jogo", "28-vehicle / boot.dol", "ESQUERDA / DIREITA", "A ×1", "X ×1", "com as suas palavras", "ciclo de energia", "PRESS A within 45 s", "até 6 minutos"):
            self.assertIn(tok, block, tok)
        self.assertNotRegex(block, r"\b(?:[LRABXYZ]|START)\d", "digits glued to a button name")
        for banned in (r"esperad", r"perfeit", r"sem falhas", r"suave", r"cristalin", r"vai (?:tocar|ouvir|aparecer|soar|parecer)", r"deve (?:tocar|soar|parecer|aparecer)", r"ouvir[áa]"):
            self.assertIsNone(re.search(banned, block, re.I), banned)
        self.assertIn("Nothing is predicted to him", plain(d))


class TheTitlesAreTheOperatorsAndTheRejectedOneIsReadNotReused(unittest.TestCase):
    def test_order_and_reasons(self):
        d = plain(section())
        for tok in ("Yoshi's Island (SMA3), on the EZ-Flash Omega DE NOR", "the KNOWN CONTROL", "Kingdom Hearts: Chain of Memories (JP, original)", "NOT to save in the game", "let any save the game starts finish",
                    "The Simpsons: Road Rage (unofficial", "WarioWare: Twisted (JP and US)", "§V7.5.2", "The KEY record exists for any title", "VOID IN A PLAY LOG", "Drill Dozer", "a ROW and not a failed run"):
            self.assertIn(tok, d, tok)
        self.assertLess(d.index("Yoshi's Island (SMA3)"), d.index("Kingdom Hearts: Chain of Memories"))
        self.assertLess(d.index("Kingdom Hearts: Chain of Memories"), d.index("The Simpsons: Road Rage"))


def build_section():
    d = section()
    i = d.index("### V31.8 THE BUILD HALF")
    j = d.find("\n### ", i + 10)
    return d[i:j if j >= 0 else len(d)]


VEHICLE_COMMIT = "6396851"
VEHICLE_SHA = "a02bcfa3b84ccd363d7bad54c8e72411d9f2e9a49595963903d1feeac4acf5d2"
VEHICLE_UNPADDED_SHA = "c9322e3fbb0bb8d62cbf2982d48203760c7843726783c1d2922b64e30965cf34"


class TheBuildRecordV318(unittest.TestCase):
    """Issue #153, the build half: V31.8 records the image, its identity, what the build decided, and the frozen Operator text."""

    def test_identity_and_build_record(self):
        d = build_section()
        for tok in (VEHICLE_COMMIT, VEHICLE_SHA, VEHICLE_UNPADDED_SHA, "509 952 B", "GBP-PLAY-002", "vehicle-0001", "byte-identical (cmp)", "IDENTICAL to the physically validated GBP-VIDEO-001 build's",
                    "0 findings", "42 and the sync profile 99", "the absent-device abort path only", "28-vehicle is RESERVED and nothing more", "NOT PHYSICALLY EXECUTED, NOT STAGED, NOT PINNED, NO RUN AUTHORISED HERE",
                    "GIT_COMMIT=6396851 GIT_DIRTY= make vehicle", "an untracked source under src/, poc/gbp-play-gba/ or tools/ dirty"):
            self.assertIn(tok, plain(d), tok)

    def test_the_built_dol_is_the_recorded_one_when_it_is_built_here_at_that_commit(self):
        out = os.path.join(ROOT, "build", "poc", "gbp-play-gba")
        info = os.path.join(out, "build-info.txt")
        if not os.path.isfile(info) or ("commit=%s\n" % VEHICLE_COMMIT) not in read(info):
            self.skipTest("gbp-play-gba is not built in this checkout")
        import hashlib
        with open(os.path.join(out, "gbp-play-gba.dol"), "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), VEHICLE_SHA)
        with open(os.path.join(out, "gbp-play-gba.unpadded.dol"), "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), VEHICLE_UNPADDED_SHA)

    def test_the_decisions_the_review_changed_are_recorded(self):
        d = plain(build_section())
        for tok in ("POST-FEED, a finding of the review", "post_feed=0|1", "which is NOT in after_startup", "tested before the production branch", "The fallback rule reads after_startup, and only that",
                    "START exits at once only after a successful save, otherwise on a 1.5 s hold", "waits, bounded at 5 s, for every button to be released", "entered=none",
                    "The transition machine is not linked at all", "the struct grew by 768 B", "Inherited from the V28 chassis and not changed"):
            self.assertIn(tok, d, tok)

    def test_the_frozen_text_carries_the_no_save_instruction_for_original_cartridges_and_predicts_nothing(self):
        d = build_section()
        i = d.index("ANTES\n 1.")
        block = d[i:d.index("```", i)]
        for tok in ("commit=6396851", "28-vehicle / boot.dol", "Kingdom Hearts (cartucho ORIGINAL): NÃO crie nem sobrescreva um save", "não aceite \"salvar\"", "A ×1", "X ×1", "com as suas palavras",
                    "ciclo de energia", "PRESS A within 45 s", "SOLTE todos os botões", "GBP-PLAY-002_vehicle-0001*"):
            self.assertIn(tok, block, tok)
        self.assertNotRegex(block, r"\b(?:[LRABXYZ]|START)\d", "digits glued to a button name")
        for banned in (r"esperad", r"perfeit", r"sem falhas", r"suave", r"cristalin", r"vai (?:tocar|ouvir|aparecer|soar|parecer)", r"deve (?:tocar|soar|parecer|aparecer)", r"ouvir[áa]"):
            self.assertIsNone(re.search(banned, block, re.I), banned)
        self.assertIn("Nothing is predicted to him", plain(d))
        self.assertIn("on his ORIGINAL cartridges (title 2) he is told NOT to create or overwrite a save", plain(d))
        req = d[d.index("Test ID:                    GBP-BREADTH-001"):]
        for tok in ("Build ID:                   vehicle-0001, commit 6396851", VEHICLE_SHA, "NO save created or overwritten", "Physical Link Port state:   nothing connected", "Question answered:"):
            self.assertIn(tok, req, tok)


class TheStagingRecordV319(unittest.TestCase):
    def test_v31_9_records_the_pin_and_the_card_verification(self):
        t = read(DOC)
        d = plain(t[t.index("### V31.9 The candidate PINNED as"):])
        for w in (VEHICLE_SHA, "Hardware Issue #154", "the ONLY difference is the new line for 28-vehicle/boot.dol", "29 files before, 30 after", "INDEX.txt untouched (md5 e66e409d1522581f9b878b2e9858636f)",
                  "all 17 pinned slots on the card read back equal to their pins", "26-v28p and 27-gbmode byte-identical to before", "no file named GBP-PLAY-002* or *vehicle-0001* anywhere on the card", "none: 28-vehicle is the play POC's own program"):
            self.assertIn(w, d, w)


if __name__ == "__main__":
    unittest.main()
