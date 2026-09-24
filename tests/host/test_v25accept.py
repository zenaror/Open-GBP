"""
tests/host/test_v25accept.py — §V25's gates (tools/v25accept.py, GitHub Issue #110), on synthetic vectors
only, before the image exists.

Pinned: L2, C and M are tools/v22accept.py's, called and not copied, and L2's record reaches it only when the
report says it is present; R is a measurement against the prior, inclusive at both ends of its band, and
decides nothing; A is the Operator's verdict, overridden toward GAIN only on all three of §V25.7 3(b)'s
conditions, and GAIN is not PASS; V's video clause is E over the start-up signature of 13, located by the
frame store, and fails on E_outside != 0 in either direction; Phase 6 closes only on four PASSes; a window
that never opened leaves every gate INCONCLUSIVE; a malformed or contradictory declaration is refused.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import v22accept  # noqa: E402
import v25accept as v  # noqa: E402

TB = 40500000
AI0 = 5 * 10 ** 9


def report(**over):
    r = {"test_id": "GBP-AUDIO-010", "build_id": "synthetic", "commit": "0000000",
         "window_opened": True, "phase_reached": "done",
         "presses": {"a": 9, "other": 140}, "presses_after": 1, "press_before_prompt": False,
         "window": {"ticks": 64 * TB, "coverage": [4088] * 64,
                    "l": {"periods": 100, "pmin": 3, "pmax": 900},
                    "not_drained": 8 * 64, "overflow": 0, "underrun": 0, "fill": [2000] * 64,
                    "corrections": {"dup": 1500, "drop": 0}},
         "m": {"callbacks": 2031, "t_first": AI0, "t_last": AI0 + 2030 * 1264500, "frames_per_callback": 1000},
         "calibration": {"rest_sum": 4096 * 16384, "rest_n": 4096, "pmin": 16383, "pmax": 16386},
         "clipped": 0,
         "video": {"framecap_incomplete": 25, "stored": 25, "store_full": 0, "before": 13, "inside": 12,
                   "after": 0, "per_second": [0] * 64, "t_ai_start": AI0, "t_ai_stop": AI0 + int(63.38 * TB)},
         "l2_sidecar": "present"}
    for k, val in over.items():
        sect, _, key = k.partition("__")
        if key:
            r[sect][key] = val
        else:
            r[sect] = val
    return r


def declaration(**over):
    d = {"a_stability": "PASS",
         "defects": {k: "no" for k in v.DEFECTS},
         "a_words": "", "a_fidelity": "abafado, sem agudos",
         "picture": "normal", "picture_words": "", "controls": "responded", "controls_words": ""}
    for k, val in over.items():
        if k in v.DEFECTS:
            d["defects"][k] = val
        else:
            d[k] = val
    return d


class Spy:
    """Stands in for tools/v22accept.py's question_L2, so what reaches it can be checked."""

    def __init__(self, verdict="PASS"):
        self.calls = []
        self.verdict = verdict

    def __call__(self, sidecar):
        self.calls.append(sidecar)
        return {"verdict": self.verdict, "why": "spy", "silence_fraction": 0.0}


class WithL2(unittest.TestCase):
    def l2(self, verdict="PASS"):
        spy = Spy(verdict)
        saved = v22accept.question_L2
        v22accept.question_L2 = spy
        self.addCleanup(setattr, v22accept, "question_L2", saved)
        return spy


class QuestionR(unittest.TestCase):
    def R(self, not_drained, secs):
        return v.question_R(report(window__coverage=[4096 - 1] * secs, window__not_drained=not_drained))

    def test_the_prior_and_the_band_are_frozen(self):
        self.assertEqual((float(v.R_PRIOR), float(v.R_BAND[0]), float(v.R_BAND[1]), float(v.R_BESIDE)),
                         (8.39, 5.59, 12.59, 9.23))

    def test_as_expected_at_the_prior(self):
        r = self.R(839, 100)
        self.assertEqual((r["reading"], r["blocks_lost_per_s"]), ("AS EXPECTED", 8.39))

    def test_the_band_is_inclusive_at_both_ends(self):
        self.assertEqual(self.R(559, 100)["reading"], "AS EXPECTED")
        self.assertEqual(self.R(558, 100)["reading"], "BETTER")
        self.assertEqual(self.R(1259, 100)["reading"], "AS EXPECTED")
        self.assertEqual(self.R(1260, 100)["reading"], "WORSE")

    def test_RUN_40s_whole_window_would_read_WORSE(self):
        """Both arms together: 1217 over 64 s is 19.02 blocks/s -- a mixed run, far above the half arm's."""
        r = self.R(1217, 64)
        self.assertEqual(r["reading"], "WORSE")
        self.assertAlmostEqual(r["blocks_lost_per_s"], 19.015625)

    def test_the_per_second_series_is_the_blocks_each_second_lost(self):
        r = v.question_R(report(window__coverage=[4096, 4080, 4090], window__not_drained=22))
        self.assertEqual(r["per_second_lost"], [0, 16, 6])

    def test_not_measured_without_a_window(self):
        self.assertEqual(v.question_R(report(window_opened=False))["reading"], "NOT MEASURED")
        self.assertEqual(v.question_R(report(window__coverage=[]))["reading"], "NOT MEASURED")

    def test_the_reading_is_the_workload_never_the_audio_load(self):
        r = self.R(2000, 100)
        self.assertEqual(r["reading"], "WORSE")
        self.assertIn("this run's workload against RUN 40's", r["interpretation"])
        self.assertIn("never \"a game's audio load\"", r["interpretation"])
        self.assertEqual(len(r["differences"]), 5)
        self.assertIn("arrival jitter", r["beside_why"])
        self.assertIn("FLOOR, not an expectation", r["floor"])


class TheDeclaration(unittest.TestCase):
    def test_a_well_formed_declaration_passes_through(self):
        d = declaration()
        self.assertIs(v.check_declaration(d), d)

    def test_malformed_ones_are_refused(self):
        bad = [declaration(a_stability="OK"), declaration(dropouts="maybe"), declaration(picture="fine"),
               declaration(controls="yes"), declaration(a_words=None)]
        missing = declaration()
        del missing["defects"]["wobble"]
        bad.append(missing)
        for d in bad:
            with self.assertRaises(ValueError):
                v.check_declaration(d)

    def test_PASS_with_a_defect_marked_yes_is_contradictory_and_refused(self):
        with self.assertRaises(ValueError) as e:
            v.check_declaration(declaration(clicks="yes"))
        self.assertIn("re-ask him", str(e.exception))
        v.check_declaration(declaration(clicks="unsure"))      # unsure is not yes


class QuestionA(unittest.TestCase):
    def test_no_declaration_is_inconclusive(self):
        self.assertEqual(v.question_A(None, 0)["verdict"], "INCONCLUSIVE")

    def test_his_PASS_stands_whatever_the_clip_counter(self):
        self.assertEqual(v.question_A(declaration(), 500)["verdict"], "PASS")

    def test_GAIN_needs_all_three_conditions(self):
        for his in ("FAIL", "QUALIFIED"):
            self.assertEqual(v.question_A(declaration(a_stability=his, distortion="yes"), 7)["verdict"], "GAIN")
            # no clip: his verdict stands
            self.assertEqual(v.question_A(declaration(a_stability=his, distortion="yes"), 0)["verdict"], his)
            # another defect marked yes: instability is present whatever the gain
            self.assertEqual(v.question_A(declaration(a_stability=his, distortion="yes", dropouts="yes"),
                                          7)["verdict"], his)
            # distortion only unsure: not marked yes
            self.assertEqual(v.question_A(declaration(a_stability=his, distortion="unsure"), 7)["verdict"], his)

    def test_unsure_elsewhere_does_not_block_GAIN(self):
        a = v.question_A(declaration(a_stability="FAIL", distortion="yes", crackle="unsure"), 3)
        self.assertEqual(a["verdict"], "GAIN")
        self.assertEqual(a["defects_yes"], ["distortion"])
        self.assertIn("NOT instability", a["why"])
        self.assertIn("GAIN is not PASS", a["why"])

    def test_his_words_and_the_fidelity_are_carried_not_gated(self):
        a = v.question_A(declaration(a_stability="QUALIFIED", a_words="uns estalos raros"), 0)
        self.assertEqual((a["verdict"], a["a_words"], a["a_fidelity"]),
                         ("QUALIFIED", "uns estalos raros", "abafado, sem agudos"))
        self.assertIn("NOT gated", a["fidelity_note"])
        self.assertIn("~2 kHz", a["fidelity_note"])
        self.assertIn("L, R or a mix is UNKNOWN", a["fidelity_note"])
        self.assertIn("not a defect here", a["blinding"])


class QuestionV(unittest.TestCase):
    def test_holds_and_passes_with_his_report(self):
        vv = v.question_V(report(), declaration())
        self.assertEqual((vv["video"]["verdict"], vv["verdict"]), ("HOLDS", "PASS"))
        self.assertEqual((vv["video"]["E_outside"], vv["video"]["E_inside"]), (0, 12))

    def test_E_outside_nonzero_in_either_direction_does_not_hold(self):
        for before, after in ((14, 0), (12, 0), (13, 1)):
            r = report(video__before=before, video__after=after, video__inside=25 - before - after)
            vid = v.video_clause(r)
            self.assertEqual(vid["verdict"], "DOES NOT HOLD", (before, after))
            self.assertIn("start-up signature of 13 changed", vid["why"])

    def test_the_rate_bound_is_inclusive(self):
        span = 500 * TB                                       # 347 / 500 s = 0.694 exactly
        ok = report(video__inside=347, video__stored=360, video__framecap_incomplete=360,
                    video__t_ai_stop=AI0 + span)
        self.assertEqual(v.video_clause(ok)["verdict"], "HOLDS")
        over = report(video__inside=348, video__stored=361, video__framecap_incomplete=361,
                      video__t_ai_stop=AI0 + span)
        self.assertEqual(v.video_clause(over)["verdict"], "DOES NOT HOLD")

    def test_RUN_40s_own_figure_sits_just_above_the_rounded_bound(self):
        """44 over RUN 40's 63.3839 s is 0.69418/s; the frozen bound is the literal 0.694. Pinned so the
        knife edge is visible, not discovered."""
        r = report(video__inside=44, video__stored=57, video__framecap_incomplete=57,
                   video__t_ai_stop=AI0 + 2567047476)
        vid = v.video_clause(r)
        self.assertEqual(vid["verdict"], "DOES NOT HOLD")
        self.assertAlmostEqual(vid["rate"], 0.69418, places=5)

    def test_the_store_must_reconcile(self):
        self.assertEqual(v.video_clause(report(video__store_full=1))["verdict"], "INCONCLUSIVE")
        self.assertEqual(v.video_clause(report(video__stored=24))["verdict"], "INCONCLUSIVE")
        self.assertEqual(v.video_clause(report(video__inside=11))["verdict"], "INCONCLUSIVE")
        self.assertEqual(v.video_clause(report(video__t_ai_stop=AI0))["verdict"], "INCONCLUSIVE")

    def test_his_picture_or_controls_fail_it(self):
        self.assertEqual(v.question_V(report(), declaration(picture="not normal"))["verdict"], "NOT PASS")
        self.assertEqual(v.question_V(report(), declaration(controls="did not"))["verdict"], "NOT PASS")

    def test_a_definite_failure_is_reported_without_a_declaration(self):
        vv = v.question_V(report(video__before=14, video__inside=11), None)
        self.assertEqual(vv["verdict"], "NOT PASS")

    def test_no_declaration_leaves_a_holding_clause_inconclusive(self):
        self.assertEqual(v.question_V(report(), None)["verdict"], "INCONCLUSIVE")

    def test_the_label_and_the_context(self):
        vid = v.video_clause(report())
        self.assertIn("NOT a claim the video is unaffected", vid["label"])
        self.assertIn("0.19/s", vid["context"])
        self.assertIn("CONTEXT only", vid["context"])


class PhaseSix(WithL2):
    def test_closes_only_on_four_PASSes(self):
        self.l2("PASS")
        r = v.evaluate(report(), b"sidecar", declaration())
        self.assertEqual(r["phase6"]["verdict"], "CLOSES")
        self.assertEqual(r["phase6"]["clauses_not_pass"], [])

    def test_R_and_M_decide_nothing(self):
        self.l2("PASS")
        r = v.evaluate(report(window__not_drained=5000, m__callbacks=1), b"sidecar", declaration())
        self.assertEqual(r["R"]["reading"], "WORSE")
        self.assertEqual(r["phase6"]["verdict"], "CLOSES")

    def test_GAIN_leaves_the_phase_open(self):
        self.l2("PASS")
        r = v.evaluate(report(clipped=40), b"sidecar", declaration(a_stability="QUALIFIED", distortion="yes"))
        self.assertEqual(r["A"]["verdict"], "GAIN")
        self.assertEqual(r["phase6"]["verdict"], "STAYS OPEN")
        self.assertEqual([c["clause"] for c in r["phase6"]["clauses_not_pass"]], ["A"])

    def test_each_clause_alone_keeps_it_open_and_is_named(self):
        cases = {"L2": (dict(), "FAIL", declaration()),
                 "C": (dict(window__overflow=1), "PASS", declaration()),
                 "A": (dict(), "PASS", declaration(a_stability="FAIL", dropouts="yes")),
                 "V": (dict(video__before=14, video__inside=11), "PASS", declaration())}
        for name, (over, l2, decl) in cases.items():
            self.l2(l2)
            r = v.evaluate(report(**over), b"sidecar", decl)
            self.assertEqual(r["phase6"]["verdict"], "STAYS OPEN", name)
            self.assertEqual([c["clause"] for c in r["phase6"]["clauses_not_pass"]], [name], name)
            self.assertIn("a partial result is not a partial closure", r["phase6"]["why"])

    def test_a_short_window_is_C_INCONCLUSIVE_by_v22s_rule(self):
        self.l2("PASS")
        r = v.evaluate(report(window__ticks=59 * TB, window__coverage=[4090] * 59), b"sidecar", declaration())
        self.assertEqual(r["C"]["verdict"], "INCONCLUSIVE")

    def test_a_window_that_never_opened_decides_nothing(self):
        spy = self.l2("PASS")
        r = v.evaluate(report(window_opened=False, phase_reached="prompt"), b"sidecar", declaration())
        self.assertEqual([r[q]["verdict"] for q in ("L2", "C", "A", "V")], ["INCONCLUSIVE"] * 4)
        self.assertEqual(r["R"]["reading"], "NOT MEASURED")
        self.assertEqual(r["phase6"]["verdict"], "STAYS OPEN")
        self.assertEqual(spy.calls, [])

    def test_L2_receives_the_record_only_when_it_is_present(self):
        spy = self.l2("PASS")
        v.evaluate(report(), b"abc", declaration())
        v.evaluate(report(l2_sidecar="absent: the log says its save failed"), b"abc", declaration())
        self.assertEqual(spy.calls, [b"abc", None])
        r = v.evaluate(report(), None, declaration())
        self.assertEqual(r["L2"]["verdict"], "INCONCLUSIVE")
        self.assertEqual(len(spy.calls), 2)

    def test_the_real_L2_says_absent_is_inconclusive(self):
        r = v.evaluate(report(l2_sidecar="absent: never saved"), None, declaration())
        self.assertEqual(r["L2"]["verdict"], "INCONCLUSIVE")
        self.assertIn("ABSENT", r["L2"]["why"])


class WhatIsReportedBeside(WithL2):
    def test_calibration_clip_and_L_are_reported_never_gated(self):
        self.l2("PASS")
        r = v.evaluate(report(clipped=3), b"s", declaration())
        cal = r["reported"]["calibration"]
        self.assertEqual((cal["spread"], r["reported"]["clipped"]), (3, 3))
        self.assertIn("never gated", cal["note"])
        self.assertIn("DESCRIPTIVE", r["reported"]["l_note"])
        self.assertEqual(r["phase6"]["verdict"], "CLOSES")
        self.assertEqual(r["M"]["callbacks"], 2031)


class TheCommandLine(WithL2):
    def test_it_prints_every_gate_and_writes_the_json(self):
        self.l2("PASS")
        with tempfile.TemporaryDirectory() as d:
            paths = {}
            for name, obj in (("r", report()), ("d", declaration())):
                paths[name] = os.path.join(d, name + ".json")
                with open(paths[name], "w", encoding="utf-8") as f:
                    json.dump(obj, f)
            side = os.path.join(d, "l2.bin")
            with open(side, "wb") as f:
                f.write(b"x")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = v.main(["v25accept.py", paths["r"], "--sidecar", side, "--declaration", paths["d"],
                             "--json", os.path.join(d, "o.json")])
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            for tok in ("  L2  PASS", "  C   PASS", "  A   PASS", "  V   PASS", "  R   AS EXPECTED",
                        "NOT A GATE", "A-FIDELITY, his words, NOT gated", "PHASE 6  CLOSES"):
                self.assertIn(tok, out, tok)
            with open(os.path.join(d, "o.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["phase6"]["verdict"], "CLOSES")


class TheModuleAuthorisesNothing(unittest.TestCase):
    def test_it_reads_no_capture_and_takes_L2_C_M_from_v22_unedited(self):
        with open(os.path.join(ROOT, "tools", "v25accept.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("captures/", src.split('"""', 2)[2])
        for tok in ("import v22accept", "v22accept.question_L2(", "v22accept.question_C(report)",
                    "v22accept.measurement_M(report)"):
            self.assertIn(tok, src, tok)
        self.assertNotIn("def question_L2", src)
        self.assertNotIn("def question_C", src)


class TheGatesAreNotEditedAfterTheyWereFrozen(unittest.TestCase):
    """The amend-on-top convention: the tool never changes; the part's frozen start never changes; numbered
    sections may be APPENDED -- a dated AMENDMENT before any hardware, or the record of the image built."""
    KEY = "Issue #110 -- §V25 transcribed, Phase 6's real-cartridge gates frozen"

    def part(self):
        with open(os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md"), encoding="utf-8") as f:
            t = f.read()
        i = t.index("\n## V25 ")
        j = t.find("\n## V26 ", i)
        return t[i:j] if j >= 0 else t[i:]

    def test_the_gates_are_the_bytes_of_the_commit_that_froze_them(self):
        import frozen
        with open(os.path.join(ROOT, "tools", "v25accept.py"), encoding="utf-8") as f:
            now = f.read()
        self.assertEqual(frozen.source(self.KEY, "tools/v25accept.py"), now,
                         "tools/v25accept.py was edited after it was frozen")

    def test_the_part_was_frozen_in_the_same_commit_and_only_grows(self):
        import frozen
        import re
        then = frozen.source(self.KEY, "docs/research/HARDWARE_TESTS.md")
        frozen_part = then[then.index("\n## V25 "):].rstrip("\n")
        now = self.part().rstrip("\n")
        self.assertTrue(now.startswith(frozen_part), "§V25's FROZEN bytes were edited -- appending is allowed")
        rest = now[len(frozen_part):].strip()
        if rest:
            self.assertRegex(rest, r"^### V25\.\d+ ", "anything appended must be a numbered section")
            for h in re.findall(r"^### V25\.(\d+) ", rest, re.M):
                self.assertGreater(int(h), 8, "an appended section reuses a frozen number")

    def test_the_transcription_carries_its_sources_in_both_forms(self):
        p = self.part()
        for tok in ("00bb6df733d8944e47976021cc96d9cf43a57e1a48f95f050738be6a0c53ff38",
                    "783fe5c792058e5aca47c74524b6bd64e011510a0fb193fbf892399148e7ec69",
                    "4ea01d6999b91548a30e3397d2eb2159872f0f5bc1536a5104c5e4efe9a1d428",
                    "38a650c4b1d0ebabd067e6b1741e47827015519da9a38cbdd4331a74ef156b27",
                    "a891552be59692162c2c69bc3838e38688079277dd3eb1145cb6b920d8b9eb58",
                    "1af4eb12b17a9a56f8f08dd43a129a8dd78923b1bdd8e50984333e9f9876b877",
                    "c472d3c3b6deb8da91fe572c9f36e0a21a53fe05edf502b73629eb45c6e6a49e",
                    "8a200e62d6b053d52ab6ae8b05b50e2a58bbd2dce42a63392bb471b502eaf25c",
                    "issuecomment-5819226612", "issuecomment-5819294644", "issuecomment-5819315360",
                    "NOT RUN, NOT AUTHORISED HERE", "**appends one `\\n`**"):
            self.assertIn(tok, p, tok)

    def test_the_transcription_keeps_the_decisions_in_their_own_words(self):
        import re
        flat = " ".join(re.sub(r"^> ?", "", self.part().replace("**", ""), flags=re.M).split())
        for tok in ("My \"8.1 blocks/s\" was 8.11 GAPS/s — a unit error.",
                    "The chain cannot cost more because the samples are music.",
                    "A gain choice must not be scored as instability.",
                    "reading (a): `GAIN` is NOT `PASS`. Phase 6 stays open.",
                    "E outside the AI span = 0",
                    "nossa DOL nunca tocou som.. entao por onde ouvi foi no console GBA... no startup disc... "
                    "no GBI..... qualquer lugar",
                    "just ABOVE the frozen literal 0.694"):
            self.assertIn(" ".join(tok.split()), flat, tok)


if __name__ == "__main__":
    unittest.main()
