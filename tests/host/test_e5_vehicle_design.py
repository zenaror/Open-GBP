"""tests/host/test_e5_vehicle_design.py -- GitHub Issue #153 (design half): HARDWARE_TESTS.md V31, the E5 vehicle's design, is arithmetic and code facts, and says nothing is built.

The store table is recomputed with tools/v28budget.py's own rules; the demonstrated envelope (RUN 57's stores) is read from the archive (ignored by Git: that test skips, with the registered
reason, on a host without it); every code claim the design rests on is read from the sources; nothing exists yet that the design says does not exist (no POC, no slot, no record); the library
default is untouched; the Operator's draft text predicts nothing. When the build half lands, the 'nothing is built' pins are the ones that are amended on top.
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
        for tok in ("300 s", "wall of 485 s", "533 s", "the largest wall a V28-chassis image has RUN AND SAVED", "INFERENCE only", "900 s is not reachable by the same store policy"):
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
        self.assertIn("# --- end --- dropped=0", t)
        self.assertGreater(31980, b.need(485, 60))


class TheCodeFactsTheDesignRestsOn(unittest.TestCase):
    def test_the_underrun_counter_and_the_playing_flag(self):
        c = read(os.path.join(ROOT, "src", "audio", "gbp_aplay2.c"))
        self.assertIn("if (p->playing) p->underruns = p->underruns + 1u;", c)
        users = subprocess.run(["grep", "-rn", r"ap2\.playing", os.path.join(ROOT, "src"), os.path.join(ROOT, "poc")], capture_output=True, text=True).stdout
        self.assertEqual(sorted(set(l.split(":")[0].replace(ROOT + os.sep, "") for l in users.splitlines())),
                         ["poc/gbp-audio-v28/source/main.c"], "the aplay2 chain's playing flag is set only by the V28 chassis' main.c")
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
        plans = read(os.path.join(ROOT, "src", "audio", "gbp_v28_plans.h"))
        self.assertNotIn("PLAY", plans, "a play plan exists: the build half has landed and this pin is amended on top")


class NothingIsBuiltYet(unittest.TestCase):
    def test_no_poc_no_slot_no_record(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, "poc", "gbp-play-gba")))
        tsv = read(os.path.join(ROOT, "tools", "swiss-layout.tsv"))
        self.assertNotIn("vehicle", tsv)
        self.assertNotIn("\n28\t", "\n" + tsv)
        for rec in ("PLAYSTARTUP", "PLAYUND", "PLAYUNDER", "CARTDECL"):
            hits = subprocess.run(["grep", "-rln", rec, os.path.join(ROOT, "src"), os.path.join(ROOT, "poc"), os.path.join(ROOT, "tools")], capture_output=True, text=True).stdout.split()
            self.assertEqual(hits, [], "%s exists in the tree: the build half has landed and this pin is amended on top" % rec)
        d = plain(section())
        for tok in ("NOTHING IS BUILT", "NO HASH EXISTS", "NO SLOT IS PINNED OR STAGED", "NO RUN IS AUTHORISED", "the name 28-vehicle is RESERVED here and nowhere else"):
            self.assertIn(tok, d, tok)

    def test_the_records_the_build_owes_are_named(self):
        d = section()
        for tok in ("PLAYSTARTUP t_dma= t_fill_reached= t_end= ring= ready= underruns_before=", "PLAYUND n= t= since_end_ms= phase= ring= ready= handed=",
                    "PLAYUNDER startup=<n> after_startup=<n> first_after_ms=<ms or -> total=<n>",
                    'CARTDECL idx=<k> title="<text>" form=<ORIGINAL|UNOFFICIAL|FLASHCART_DELIVERED|UNDECLARED> mode=GBA entered=pad_selection'):
            self.assertIn(tok, d, tok)


class TheOperatorsDraftPredictsNothing(unittest.TestCase):
    def test_the_draft(self):
        d = section()
        i = d.index("**DRAFT of the Operator's text")
        block = d[d.index("```text", i):d.index("```", d.index("```text", i) + 7)]
        for tok in ("NÃO salve o jogo", "28-vehicle", "ESQUERDA / DIREITA", "A ×1", "X ×1", "com as suas palavras", "ciclo de energia"):
            self.assertIn(tok, block, tok)
        self.assertNotRegex(block, r"\b(?:[LRABXYZ]|START)\d", "digits glued to a button name")
        for banned in (r"esperad", r"perfeit", r"sem falhas", r"suave", r"cristalin", r"vai (?:tocar|ouvir|aparecer|soar|parecer)", r"deve (?:tocar|soar|parecer|aparecer)", r"ouvir[áa]"):
            self.assertIsNone(re.search(banned, block, re.I), banned)
        self.assertIn("Nothing is predicted to him", plain(d))


class TheTitlesAreTheOperatorsAndTheRejectedOneIsReadNotReused(unittest.TestCase):
    def test_order_and_reasons(self):
        d = plain(section())
        for tok in ("Yoshi's Island (SMA3), on the EZ-Flash Omega DE NOR", "the KNOWN CONTROL", "Kingdom Hearts: Chain of Memories (JP, original)", "NOT to save in the game",
                    "The Simpsons: Road Rage (unofficial", "WarioWare: Twisted (JP and US)", "§V7.5.2", "the per-title input gate cannot be evaluated", "Drill Dozer", "a ROW and not a failed run"):
            self.assertIn(tok, d, tok)
        self.assertLess(d.index("Yoshi's Island (SMA3)"), d.index("Kingdom Hearts: Chain of Memories"))
        self.assertLess(d.index("Kingdom Hearts: Chain of Memories"), d.index("The Simpsons: Road Rage"))


if __name__ == "__main__":
    unittest.main()
