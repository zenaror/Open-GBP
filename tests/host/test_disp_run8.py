"""
tests/host/test_disp_run8.py — RUN B / GBP-VIDEO-005: the NORMAL startup with a
REAL RETAIL cartridge (HARDWARE_TESTS §V5.54).

Machine evidence only. The operator's answers A-G are recorded in the docs, as
observation, and are never turned into synthetic machine data here. The
retail witness is NOT decoded: OGBPIDX semantics do not apply to it, and the
only fixture kept from it is the content-blind structural projection.

RUN B exercised stream-0009's OLD orchestration: the structural window still
opened at frame 223. It did NOT exercise the 5 s gate, and nothing here
pretends it did.
"""
import hashlib
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import vdisp  # noqa: E402

FX = os.path.join(ROOT, "captures", "fixtures")
DISP = os.path.join(FX, "hw-gamecube-gbp-2026-09-20-stream-0009-run8-disp.bin")
DISP_SHA = "2edadb49ab760e8c596368373a20fdfa6e3be67d5a44139327b7aa5a0b1a5a34"
TB = 40500000
KEY = vdisp.KEY_NONE
D = {v: k for k, v in vdisp.DISPOSITION.items()}
LF = {v: k for k, v in vdisp.LF}
# STARTUP / STARTUPV / WITQUAL as the physical log printed them
STARTUP = dict(mode="normal", selftest_visible=0, prehandler_wait_ms=0, presented_synthetic=0,
               headless_submits=1, first_frame_index=2, ticks_control_to_first_handoff=6670174)
WITQUAL = dict(required=64, resets=12, warmup_frames=223, warmup_disqualified=26,
               qualify_frame=222, first_record_frame=223)
_C = {}


def disp():
    if "d" not in _C:
        _C["d"] = vdisp.load(DISP)
    return _C["d"]


def log_line(tag):
    for d in (os.path.join("captures", "local"),):
        p = os.path.join(ROOT, d, "GBP-VIDEO-005_stream-0009-run8.log")
        if os.path.exists(p):
            for ln in open(p):
                if (" %s " % tag) in ln:
                    return dict(re.findall(r"(\w+)=([^\s]+)", ln.split(tag, 1)[1]))
    raise unittest.SkipTest("the run-8 log is not on this machine")


def pct(s, q):
    n = len(s)
    return s[min(n - 1, int(n * q))] if n else None


class TheArtifactIsTheOneThatRan(unittest.TestCase):
    def test_the_disp_fixture_is_the_physical_sidecar(self):
        with open(DISP, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), DISP_SHA)

    def test_it_is_the_same_binary_run_7_ran(self):
        i = disp()
        self.assertEqual((i["build_id"], i["commit"]), ("stream-0009", "59d2f57"))


class NormalStartupRepeated(unittest.TestCase):
    def test_the_startup_line_matches(self):
        s = log_line("STARTUP")
        for k in ("mode", "selftest_visible", "prehandler_wait_ms", "presented_synthetic", "headless_submits"):
            self.assertEqual(str(STARTUP[k]), s[k], k)

    def test_first_handoff_164_696_ms_within_half_a_millisecond_of_run_7(self):
        v = log_line("STARTUPV")
        t = int(v["ticks_control_to_first_handoff"])
        self.assertEqual(t, 6670174)
        ms = t * 1000.0 / TB
        self.assertAlmostEqual(ms, 164.695654, places=5)
        self.assertLess(ms, 400.0)
        self.assertLess(abs(6688749 - t) * 1000.0 / TB, 0.5)

    def test_the_selftest_ran_headless_again(self):
        st = [r for r in disp()["life"] if r["frame_index"] == KEY]
        self.assertEqual(len(st), 1)
        self.assertTrue(st[0]["life_flags"] & LF["SELFTEST"])
        self.assertEqual(st[0]["disposition"], D["TERMINAL_PENDING"])


class TheStructuralStartupTransientIsRepeatable(unittest.TestCase):
    """Same qualification point as run 7 on a DIFFERENT cartridge. That is a
    statement about the AGB/GBP boot's structure, not about content."""

    def test_witqual_is_identical_to_run_7(self):
        q = log_line("WITQUAL")
        for k, v in WITQUAL.items():
            self.assertEqual(int(q[k]), v, k)

    def test_the_four_preserved_episodes_match_run_7_descriptor_for_descriptor(self):
        p = os.path.join(ROOT, "captures", "local", "GBP-VIDEO-005_stream-0009-run8.log")
        if not os.path.exists(p):
            raise unittest.SkipTest("run-8 log absent")
        eps = re.findall(r"EPISODE i=(\d+) .* flags=(\S+) frames=(\d+) .* open_frame=(\d+) close_frame=(\d+) .* sig0=(\S+)", open(p).read())
        want = [("0", "0005", "18", "8", "25", "7f0fff10"), ("1", "0006", "60", "30", "89", "00000000"),
                ("2", "0006", "60", "90", "149", "00000000"), ("3", "0005", "48", "150", "197", "7f0fff10")]
        self.assertEqual(eps[:4], want)


class PolicyAOnRetailContent(unittest.TestCase):
    def test_container_intact(self):
        i = disp()
        self.assertEqual((i["life_overflow"], i["event_overflow"], i["drawdone_unmatched"], i["order_violations"]), (0, 0, 0, 0))
        self.assertEqual((i["decisions"], i["source_deferred_frames"], i["event_n"]), (2244, 43, 2287))
        self.assertEqual(i["decisions"] + i["source_deferred_frames"], i["event_n"])
        self.assertTrue(vdisp.usable(i)["usable_for_disposition_claim"])
        self.assertEqual(i["terminal_pending"], 2)

    def test_every_published_frame_handed_off_in_order_none_dropped(self):
        real = [r for r in disp()["life"] if r["frame_index"] != KEY]
        handed = sorted([r for r in real if r["disposition"] == D["SELECTED_NEW"]], key=lambda r: r["t_decision"])
        seq = [r["frame_index"] for r in handed]
        self.assertEqual(len(seq), 2244)
        self.assertEqual(seq, sorted(seq))
        self.assertEqual(len(seq), len(set(seq)))
        self.assertEqual(disp()["source_dropped_interior"], 0)

    def test_deferrals_and_latency(self):
        i = disp()
        dd = [r for r in i["life"] if r["life_flags"] & LF["EVER_DEFERRED"]]
        self.assertEqual((len(dd), sum(r["defer_attempts"] for r in dd), i["max_deferred_depth"]), (43, 97, 1))
        ev = {e["frame_index"]: e for e in i["events"] if e["decision"] == D["DEFERRED"]}
        self.assertTrue(all(r["retrace_decision"] == ev[r["frame_index"]]["retrace"] + 1 for r in dd))
        handed = [r for r in i["life"] if r["frame_index"] != KEY and r["disposition"] == D["SELECTED_NEW"]]
        lat = sorted(r["t_decision"] - r["t_convert_done"] for r in handed)
        self.assertLessEqual(pct(lat, 0.99) * 1000.0 / TB, 1.0)
        self.assertLessEqual(lat[-1] * 1000.0 / TB, 2.5)

    def test_seven_display_repeats_over_the_join_third_run_running(self):
        m = {r["frame_index"]: r for r in disp()["life"] if r["frame_index"] != KEY}
        h = sorted([m[k] for k in range(223, 2271) if m[k]["disposition"] == D["SELECTED_NEW"]], key=lambda r: r["t_decision"])
        rt = [r["retrace_decision"] for r in h]
        self.assertEqual(sum((b - a) - 1 for a, b in zip(rt, rt[1:])), 7)


if __name__ == "__main__":
    unittest.main()
