"""tests/host/test_alive_chain.py -- Phase 6's chain, end to end on the host, decided by
the FROZEN tools/v22accept.py (GitHub Issue #92, §V22, §V22.9).

A C harness links the image's own modules -- gbp_alive, gbp_aperiod, gbp_adec,
gbp_aresamp, gbp_aplay, all unchanged -- and runs a whole synthetic session on TWO
clocks: AUDIO blocks at the rate RUN 37 measured (245 757 per 60.000017 s) and AI
callbacks at Dolphin's 32 028.5 Hz, the HYPOTHESIS §V22.4 plans for. The cartridge is
a two-level H-PWM square of period 32 blocks, silent until the one A press.

What it proves before any hardware exists:
  * the sidecar the image writes is decidable by the frozen tool, and L2 PASSES on it
    -- with the counted corrections, and with a SILENCE chunk inside the window;
  * L, read before the corrections, is exactly 32; the corrections come at the rate
    §V22.4 predicts, as DUPs;
  * a starved producer is an UNDERRUN (C would FAIL) and still leaves L2 decidable,
    its silence fraction reported (§V22.8 (u), §V22.9 A2).
"""
import os
import subprocess
import sys
import tempfile
import unittest

import hostcc  # noqa: E402  (tests/host is on the path)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v22accept as v  # noqa: E402

AUDIO = os.path.join(ROOT, "src", "audio")
SOURCES = ["gbp_alive.c", "gbp_aperiod.c", "gbp_adec.c", "gbp_aresamp.c", "gbp_aplay.c"]

HARNESS = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_alive.h"
#include "gbp_aperiod.h"
#include "gbp_adec.h"
#include "gbp_aplay.h"

#define TB 40500000.0
static uint8_t pool[GBP_APLAY_POOL * GBP_APLAY_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY_CHUNK_BYTES];
static int16_t keep[GBP_APLAY_KEEP_CAP];
static struct gbp_aplay_event events[GBP_APLAY_EVENTS_CAP];
static int16_t ring[GBP_APLAY_RING];
static uint8_t blk[4096];
static uint8_t side[0x48 + 8 * GBP_APLAY_EVENTS_CAP + 2 * GBP_APLAY_KEEP_CAP + 4];

/* argv: out-sidecar  starve_from_s  starve_ms  ai_hz */
int main(int argc, char **argv) {
    struct gbp_alive a; struct gbp_aperiod per; struct gbp_adec d; static struct gbp_aplay p;
    const double block_dt = 60.000017284 * TB / 245757.0;
    const double ai_hz = atof(argv[4]);
    const double cb_dt = 1000.0 * TB / ai_hz;
    const double starve_from = atof(argv[2]), starve_ms = atof(argv[3]);
    double t_block = 1000.0, t_cb = 1e30;
    uint64_t k = 0, tone_from = 0; int started = 0, armed = 0, done = 0;
    gbp_alive_init(&a, 40500000u);
    gbp_aperiod_reset(&per, GBP_ALIVE_PERIOD);
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    gbp_alive_start(&a, 1000u);
    gbp_alive_buttons(&a, 1000u, 0u);
    while (!done) {
        if (t_block <= t_cb) {
            const uint64_t t = (uint64_t)t_block;
            int act, j;
            /* the cartridge: rest until the press, then a 32-block square */
            if (!tone_from && a.presses_a) tone_from = k;
            if (tone_from) memset(blk, ((k - tone_from) % 32u) >= 16u ? 0x1F : 0x07, sizeof blk);
            else memset(blk, 0x0F, sizeof blk);
            /* the A press, 6 s in, at the prompt */
            if (!a.presses_a && t_block > 1000.0 + 6.0 * TB) { gbp_alive_buttons(&a, t, 0x0100u); gbp_alive_buttons(&a, t + 1u, 0u); }
            act = gbp_alive_block(&a, t, d.count);
            if (act == GBP_ALIVE_DO_CALIBRATE) gbp_adec_calibrate(&d, blk);
            else if (act == GBP_ALIVE_DO_CONTROL) {
                (void)gbp_aperiod_feed(&per, blk, 4096u);
                if (per.blocks >= GBP_ALIVE_CONTROL_BLOCKS) {
                    gbp_alive_control_window(&a, t, gbp_aperiod_exact(&per, GBP_ALIVE_CONTROL_MIN), per.periods, per.pmin, per.pmax, per.blocks);
                    gbp_aperiod_reset(&per, GBP_ALIVE_PERIOD);
                }
            } else if (act == GBP_ALIVE_DO_DECODE) {
                if (gbp_adec_push_block(&d, blk) == 0) gbp_alive_decoded(&a, d.ring[(d.head + d.count - 1u) % d.cap]);
            }
            if (gbp_alive_finished(&a)) done = 1;
            /* the pump slot */
            if (a.phase == GBP_ALIVE_WINDOW) {
                const double since = (t_block - (double)a.t_origin) / TB;
                const int starving = starve_ms > 0.0 && since >= starve_from && since < starve_from + starve_ms / 1000.0;
                if (!armed && since >= 20.0) { gbp_aplay_arm_l2(&p); armed = 1; }
                for (j = 0; j < 2 && !starving; j++) { int b = gbp_aplay_produce(&p, &d); if (b >= 0) gbp_aplay_queue(&p, b); }
                gbp_aplay_process(&p);
                if (!started && d.count >= GBP_APLAY_TARGET && gbp_aplay_ready(&p) >= 2u) {
                    started = 1; p.playing = 1u;
                    (void)gbp_aplay_irq_handoff(&p, t);      /* the first block: not a callback */
                    p.measuring = 1u;                          /* M starts at the first callback, as the image */
                    t_cb = t_block + cb_dt;
                }
            }
            k++; t_block += block_dt;
        } else {
            (void)gbp_aplay_irq_handoff(&p, (uint64_t)t_cb);
            t_cb += cb_dt;
        }
    }
    gbp_aplay_process(&p);
    {
        FILE *f = fopen(argv[1], "wb");
        size_t n = gbp_aplay_sidecar(&p, side, sizeof side);
        if (!f || n == 0 || fwrite(side, 1, n, f) != n) return 2;
        fclose(f);
    }
    printf("phase=%s secs=%u overflow=%u underruns=%u dup=%u drop=%u produced=%u handed=%u\n",
           gbp_alive_phase_name(a.phase), a.secs_used, d.overflow, p.underruns, p.dup, p.drop, p.produced, p.handed);
    printf("l periods=%u pmin=%u pmax=%u control=%u/%u pmin=%u pmax=%u presses=%u/%u\n",
           a.l.periods, a.l.pmin, a.l.pmax, a.control_ok, a.control_periods, a.control_pmin, a.control_pmax,
           a.presses_a, a.presses_other);
    printf("l2 done=%u kept=%u window=%u silence=%u n_keep=%u events=%u cb=%u window_s=%.6f\n",
           p.l2.done, p.l2.kept_chunks, p.l2.window_chunks, p.l2.silence_chunks, p.l2.n_keep, p.l2.n_events,
           p.cb_count, (double)(a.t_end - a.t_origin) / TB);
    printf("m first=%llu last=%llu count=%u\n", (unsigned long long)p.cb_t_first, (unsigned long long)p.cb_t_last,
           p.cb_count);
    return 0;
}
"""


def parse(out):
    """'head k=v k=v' lines -> {'head:k': v}; a line whose first token is itself k=v -> {':k': v}."""
    flat = {}
    for line in out.splitlines():
        head = line.split()[0]
        for tok in line.split()[1:]:
            k, _, val = tok.partition("=")
            flat[(head if "=" not in head else "") + ":" + k] = val
        if "=" in head:
            k, _, val = head.partition("=")
            flat[":" + k] = val
    return flat


class TheChainIsDecidedByTheFrozenTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="alive-")
        src = os.path.join(cls.tmp, "h.c")
        with open(src, "w") as f:
            f.write(HARNESS)
        cls.bin = os.path.join(cls.tmp, "h")
        cls.have, cls.ok, cls.err = hostcc.compile_c(
            ["-std=gnu11", "-O2", "-Wall", "-Wextra", "-I", AUDIO, "-o", cls.bin, src] +
            [os.path.join(AUDIO, s) for s in SOURCES])
        cls.runs = {}

    def run_session(self, name, starve_from=0.0, starve_ms=0.0, ai_hz=v.AI_MODEL_HZ):
        hostcc.require(self, self.have, self.ok, self.err)
        if name not in self.runs:
            side = os.path.join(self.tmp, name + ".l2")
            r = subprocess.run([self.bin, side, str(starve_from), str(starve_ms), repr(ai_hz)],
                               capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(side, "rb") as f:
                self.runs[name] = (parse(r.stdout), f.read(), r.stdout)
        return self.runs[name]

    def test_a_clean_session_passes_L2_and_L(self):
        kv, side, out = self.run_session("clean")
        self.assertEqual(kv[":phase"], "done", out)
        r = v.question_L2(side)
        self.assertEqual(r["verdict"], "PASS", r["why"])
        self.assertEqual(r["silence_fraction"], 0.0)
        self.assertEqual((kv["l:pmin"], kv["l:pmax"]), ("32", "32"), out)
        self.assertEqual((kv[":underruns"], kv[":overflow"], kv[":drop"]), ("0", "0", "0"), out)
        self.assertEqual((kv["l:presses"]), "1/0")

    def test_the_corrections_come_at_the_predicted_rate(self):
        """§V22.4 FREEZES the predicted rate as the reading of the clock model, and the tool reports
        the observed one over C's window: (DUP - DROP) / window. The band is narrow so the two can
        be compared at all (gbp_aplay.h, THE CLOCKS)."""
        kv, side, out = self.run_session("clean")
        observed = (int(kv[":dup"]) - int(kv[":drop"])) / float(kv["l2:window_s"])
        predicted = v.AI_MODEL_HZ * 16 / 125 - 245757 / 60.000017284
        self.assertAlmostEqual(observed, predicted, delta=0.4, msg=out)
        self.assertEqual(int(kv[":drop"]), 0, out)

    def test_a_slower_ai_inverts_the_corrections(self):
        kv, side, out = self.run_session("slow", ai_hz=31990.0)
        self.assertGreater(int(kv[":drop"]), 3 * int(kv[":dup"]), out)
        self.assertEqual(v.question_L2(side)["verdict"], "PASS")

    def test_the_nominal_ai_needs_almost_nothing(self):
        kv, side, out = self.run_session("nominal", ai_hz=32000.0)
        self.assertLess(int(kv[":dup"]) + int(kv[":drop"]), 10, out)

    def test_a_starved_producer_underruns_and_L2_stays_decidable(self):
        kv, side, out = self.run_session("starved", starve_from=25.0, starve_ms=300.0)
        self.assertGreater(int(kv[":underruns"]), 0, out)                  # C would FAIL
        r = v.question_L2(side)
        self.assertEqual(r["verdict"], "PASS", r["why"])                    # and L2 is still decidable
        self.assertGreater(r["silence_fraction"], 0.0)                      # with its silence said
        self.assertEqual(int(kv["l2:silence"]), int(kv[":underruns"]), out)

    def test_m_measures_the_ai_clock_it_was_given(self):
        """§V22.5: frames x (callbacks - 1) / (last - first) recovers the AI's rate. The harness
        rounds each callback instant to a whole tick, so a few ppm is all the error allowed."""
        for name, hz in (("clean", v.AI_MODEL_HZ), ("slow", 31990.0), ("nominal", 32000.0)):
            kv, side, out = self.run_session(name, ai_hz=hz)
            m = v.measurement_M({"m": {"callbacks": int(kv["m:count"]), "t_first": int(kv["m:first"]),
                                       "t_last": int(kv["m:last"]), "frames_per_callback": 1000}})
            self.assertAlmostEqual(m["rate_hz"], hz, delta=hz * 5e-6, msg=out)

    def test_a_tampered_record_fails(self):
        kv, side, out = self.run_session("clean")
        b = bytearray(side)
        b[0x48 + 8 * int(kv["l2:events"]) + 1000] ^= 0x01                  # one kept sample
        import struct
        import zlib
        b[-4:] = struct.pack(">I", zlib.crc32(bytes(b[:-4])) & 0xFFFFFFFF)  # its own CRC made consistent
        self.assertEqual(v.question_L2(bytes(b))["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()
