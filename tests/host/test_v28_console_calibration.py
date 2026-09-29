"""Issue #136: the host harness of the ROTATE landing is calibrated to the console's OWN figures, and this test is what stops
that calibration from drifting back into an assumption.

Why it exists. The first design of the mutes (and every host proof of the old mechanism) used a host that ran 16 pump calls a
period, fed the ring exactly what the DMA consumes and began every move with the ring ABOVE target. The console does none of
those (RUN 52's log: 124.8 calls a period, a feed 0.5 % slow, moves begun 956-1878 samples BELOW target). An adversarial review
caught it. Here the constants the C test and the ladder header carry are recomputed from the raw RUN 52 log, so that editing the
harness back toward the host's own settled state fails.

The raw log is private (`logs/`, `captures/local/`, never versioned); without it the tests skip, like the other archive checks."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LANDING_C = os.path.join(ROOT, "tests", "unit", "test_v28_sweep_landing.c")
LADDER_H = os.path.join(ROOT, "src", "audio", "gbp_v28_ladder.h")
LOGS = [os.path.join(ROOT, "logs", "run52", "GBP-AUDIO-V28_v28-validation-0001.log"),
        os.path.join(ROOT, "captures", "local", "GBP-AUDIO-V28_v28-validation-0001-run52.log")]
LOG_SHA256 = "6b80c29ef29b550a58cbb4a7a90cb583a4097cf2877c5a5e0886b84b01b9a214"
TB_HZ = 40_500_000
PERIOD_S = 2048 / 65536


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def run52():
    for p in LOGS:
        if os.path.isfile(p):
            import hashlib
            with open(p, "rb") as f:
                if hashlib.sha256(f.read()).hexdigest() == LOG_SHA256:
                    return read(p)
    return None


def c_int_list(src, name):
    m = re.search(r"%s\[\d+\]\s*=\s*\{([^}]*)\}" % re.escape(name), src)
    return [int(x) for x in re.findall(r"-?\d+", m.group(1))]


class TheHarnessIsTheConsoles(unittest.TestCase):
    def setUp(self):
        self.log = run52()
        if self.log is None:
            self.skipTest("the RUN 52 raw log is not on this host (logs/ and captures/local/ are private)")

    def test_the_begin_rings_are_the_ones_the_console_measured(self):
        """meas_ring - from_target for every sweep move that follows another move (n = 1..27), RUN 52's V28_SWEEPM."""
        frm, meas = {}, {}
        for n, ft in re.findall(r"V28_SWEEP n=(\d+) klass=\d mech=\d from_t=(\d+)", self.log):
            frm[int(n)] = int(ft)
        for n, mr in re.findall(r"V28_SWEEPM n=(\d+) meas_t=\d+ meas_a=\d meas_ring=(\d+)", self.log):
            meas[int(n)] = int(mr)
        offs = {n: meas[n] - frm[n] for n in meas if n >= 1}
        gate = [offs[n] for n in range(1, 18)]           # the 17 GATE moves that follow another move
        src = read(LANDING_C)
        table = c_int_list(src, "BEGIN_OFF")
        self.assertEqual(len(table), 17)
        self.assertEqual(sorted(table), sorted(gate), "BEGIN_OFF is not RUN 52's measured begin rings (GATE n=1..17)")
        self.assertTrue(all(-2000 < v < -900 for v in table), "a begin ring above target is the error the review caught")
        prelude = meas[0] - frm[0]
        self.assertEqual(int(re.search(r"#define BEGIN_OFF_START \((-\d+)\)", src).group(1)), prelude)
        self.assertEqual(prelude, -2666)

    def test_the_ladder_deficits_are_the_worst_of_them(self):
        frm, meas = {}, {}
        for n, ft in re.findall(r"V28_SWEEP n=(\d+) klass=\d mech=\d from_t=(\d+)", self.log):
            frm[int(n)] = int(ft)
        for n, mr in re.findall(r"V28_SWEEPM n=(\d+) meas_t=\d+ meas_a=\d meas_ring=(\d+)", self.log):
            meas[int(n)] = int(mr)
        worst_step = max(frm[n] - meas[n] for n in range(1, 28))
        worst_start = frm[0] - meas[0]
        h = read(LADDER_H)
        self.assertEqual(int(re.search(r"#define GBP_V28_BEGIN_DEFICIT_STEP\s+(\d+)u", h).group(1)), worst_step)
        self.assertEqual(int(re.search(r"#define GBP_V28_BEGIN_DEFICIT_START\s+(\d+)u", h).group(1)), worst_start)

    def test_the_pump_rate_is_the_consoles(self):
        m = re.search(r"V28_3B n=0 .*?t_set=([0-9a-f]+) t_done=([0-9a-f]+) .*?samples=(\d+)", self.log)
        t_set, t_done, samples = int(m.group(1), 16), int(m.group(2), 16), int(m.group(3))
        hold_s = (t_done - t_set) / TB_HZ
        calls = samples / (hold_s / PERIOD_S)
        self.assertAlmostEqual(calls, 124.8, delta=0.5)
        src = read(LANDING_C)
        self.assertRegex(src, r"static uint32_t calls_pp = 125u;")

    def test_the_feed_deficit_is_the_consoles(self):
        m = re.search(r"V28C underruns=\d+ .*? dup=(\d+) drop=(\d+) produced=(\d+)", self.log)
        dup, drop, produced = int(m.group(1)), int(m.group(2)), int(m.group(3))
        deficit = (dup - drop) / produced / 2048           # net corrections per chunk over one chunk of pushes
        self.assertAlmostEqual(deficit, 0.0054, delta=0.0006)
        src = read(LANDING_C)
        self.assertIn("0.995", src)                          # the case that models it
        self.assertIn("0.99", src)                           # twice the measurement: sizes the mute, not an operating point


class TheHarnessCannotRepeatTheError(unittest.TestCase):
    """Log-free: the C test itself asserts, on every run, that a move began BELOW target (checked in the source text)."""

    def test_every_run_begins_from_a_measured_ring_and_the_test_says_so(self):
        src = read(LANDING_C)
        self.assertIn("mv->mute == ST ? BEGIN_OFF_START : BEGIN_OFF[", src)
        self.assertIsNotNone(re.search(r"begin ring guard", src))
        self.assertIn("out->begin_high += (int32_t)adec.count - (int32_t)mv->from_t > -900;", src)


if __name__ == "__main__":
    unittest.main()
