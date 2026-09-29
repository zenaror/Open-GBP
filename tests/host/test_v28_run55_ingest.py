"""tests/host/test_v28_run55_ingest.py -- GitHub Issue #139 (RUN 55): the two things the ingestion repaired forward.

1. tools/v28verdict.py printed, unconditionally, that the 3B flag "is set by a hook main.c does not call, so 'clean' means UNOBSERVED". True at
   33de2db (RUN 51-53), FALSE since 4a3c003 wired the hooks: RUN 55's report said it of a hold whose hook demonstrably fired in the same run (3a's
   confirm at 2304 ended on its underrun). A caveat that outlived its truth. The note is conditioned on evidence in the log (or the build's ancestry).
2. main.c's 3a per-depth delta snapshot began at boot, so 3a's first row carried navigate's underrun and 13 088 dup (RUN 55: session underruns 2 against
   p0 1 + 3a rows 2). It is re-taken when 3a starts.
"""
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import test_v28_diag_loss_wiring as W  # noqa: E402
import test_v28verdict as TV  # noqa: E402
import v28verdict  # noqa: E402

MAIN = W.MAIN
RUN55 = os.path.join(ROOT, "captures", "local", "GBP-AUDIO-V28_v28-validation-0001-run55.log")
RUN53 = os.path.join(ROOT, "captures", "local", "GBP-AUDIO-V28_v28-validation-0001-run53.log")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def log_with(extra, commit="7e0dc0c"):
    return "\n".join(["000000 IDENT test=GBP-AUDIO-V28 app=x build=v28-validation-0001 commit=%s libogc=libogc2" % commit,
                      TV.full_clean_log(), TV.b3_hold(1), TV.anchor_line(),
                      "V28C underruns=2 overflow=0 silences=2 mute_handed=215 dup=60703 drop=16 produced=7799 handed=7927 ring_gated=1",
                      TV.a3_confirm(2304, underruns=1)] + extra)


PHC = ["V28PHC p=0 ended=1 t0=1 t1=2 blocks_in=10 taps=10 failed=0 wrong=0 underruns=1",
       "V28PHD p=0 dup=13088 drop=0 starved=0 produced=1 handed=1 gated=1 ring=1,2",
       "V28PHC p=1 ended=1 t0=2 t1=3 blocks_in=10 taps=10 failed=0 wrong=0 underruns=1",
       "V28PHD p=1 dup=1 drop=0 starved=0 produced=1 handed=1 gated=1 ring=1,2"]


class TheNoteFollowsTheBuild(unittest.TestCase):
    def render(self, text):
        return v28verdict.render(v28verdict.analyse(text))

    def test_a_run_55_shaped_log_carries_no_unobserved_note(self):
        out = self.render(log_with(PHC + ["V28TAPS taps=10 taps_failed=0 wrong_len=0 blocks_in=10 gap_max=1 gap_at=1"]))
        self.assertNotIn("UNOBSERVED", out)
        self.assertNotIn("does not call", out)
        self.assertIn("the underrun hook is live in this build", out)
        self.assertIn("'clean' is OBSERVED", out)

    def test_each_marker_alone_is_enough(self):
        for marker in ("V28TAPS taps=1 taps_failed=0 wrong_len=0 blocks_in=1 gap_max=1 gap_at=1",
                       "V28LOSSCFG target=4096 tb_hz=40500000 holds=0", PHC[0]):
            live, why = v28verdict.hooks_live(log_with([marker], commit="deadbee"))
            self.assertTrue(live, marker)
            self.assertIn("printed only by builds after 4a3c003", why)

    def test_an_old_shaped_log_keeps_the_caution(self):
        out = self.render(log_with([], commit="33de2db"))
        self.assertIn("'clean' means UNOBSERVED", out)
        self.assertNotIn("the underrun hook is live", out)

    def test_a_log_from_a_descendant_of_the_wiring_commit_is_live_by_ancestry_alone(self):
        try:
            ok = subprocess.run(["git", "-C", ROOT, "merge-base", "--is-ancestor", "4a3c003", "HEAD"], capture_output=True).returncode == 0
        except OSError:
            ok = False
        if not ok:
            self.skipTest("this checkout cannot show 4a3c003's ancestry")
        head = subprocess.check_output(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"]).decode().strip()
        live, why = v28verdict.hooks_live(log_with([], commit=head))
        self.assertTrue(live)
        self.assertIn("descends from 4a3c003", why)
        # and a commit before it is not
        old = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "4a3c003~1"], capture_output=True).stdout.decode().strip()
        self.assertFalse(v28verdict.hooks_live(log_with([], commit=old))[0])

    def test_the_real_logs_of_both_kinds(self):
        if not (os.path.isfile(RUN55) and os.path.isfile(RUN53)):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        self.assertNotIn("UNOBSERVED", self.render(read(RUN55)))
        self.assertIn("UNOBSERVED", self.render(read(RUN53)))


class TheBoundaryDoubleCount(unittest.TestCase):
    def test_the_accounting_by_phase_names_the_first_row(self):
        text = "\n".join(PHC + ["V28C underruns=2 overflow=0 silences=2 mute_handed=1 dup=1 drop=0 produced=1 handed=1 ring_gated=1",
                                "V28_3A n=0 target=6144 kind=0 partial=0 underruns=1 overflow=0 dup=16191 drop=16 starved=416 t_set=1 t_done=2",
                                "V28_3A n=1 target=5632 kind=0 partial=0 underruns=1 overflow=0 dup=3073 drop=0 starved=0 t_set=1 t_done=2"])
        ua = v28verdict.underrun_accounting(text)
        self.assertEqual(ua["by_phase"], {0: 1, 1: 1})
        self.assertEqual(ua["s3a"], 2)
        self.assertEqual(ua["boundary_double_count"], 1)

    def test_no_phase_records_no_claim(self):
        ua = v28verdict.underrun_accounting("V28C underruns=2 overflow=0 silences=2 mute_handed=1 dup=1 drop=0 produced=1 handed=1 ring_gated=1")
        self.assertNotIn("by_phase", ua)
        self.assertNotIn("boundary_double_count", ua)

    def test_main_retakes_the_3a_delta_snapshot_when_3a_starts(self):
        src = W.code(read(MAIN))
        self.assertIn("static uint32_t d0_underruns, d0_overflow, d0_dup, d0_drop, d0_ring_gated;", src)
        # file scope, not a function-local static that begins at zero
        i = src.index("static uint32_t d0_underruns")
        self.assertLess(i, src.index("static void v28_dispatch_phase_start"))
        body = W.function_body(src, "v28_dispatch_phase_start")
        m = re.search(r"case GBP_WALKER_DESCENT_3A:(.*?)break;", body, re.S)
        self.assertIsNotNone(m)
        blk = m.group(1)
        self.assertIn("gbp_v28_3a_start(&s3a, live.tb_hz, now);", blk)
        for f in ("d0_underruns = (uint32_t)ap2.underruns;", "d0_overflow = (uint32_t)adec2.overflow;", "d0_dup = (uint32_t)ap2.dup;",
                  "d0_drop = (uint32_t)ap2.drop;", "d0_ring_gated = (uint32_t)ap2.ring_gated;"):
            self.assertIn(f, blk)
        live = W.function_body(src, "live_step")
        self.assertNotIn("static uint32_t d0_", live, "the per-depth snapshot must not be a zero-initialised local static again")


if __name__ == "__main__":
    unittest.main()
