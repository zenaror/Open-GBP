"""tests/host/test_v22accept.py -- §V22's gates on SYNTHETIC vectors only (GitHub Issue #92).

tools/v22accept.py is frozen before the POC exists. Every vector here is built in
this file; nothing reads a capture. Two things carry the weight:

  * the resampler the host uses for L2 IS the frozen gbp_aresamp: its output is
    compared sample for sample with the C source compiled on the host, and its
    resumption from a kept state with a continuous run;
  * each gate returns the verdict §V22 freezes on the vectors that sit at, and
    just past, its boundaries -- including (e), the reading without which L fails
    a healthy system by construction.
"""
import os
import random
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

import hostcc  # noqa: E402  (tests/host is on the path)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_aresamp  # noqa: E402
import v22accept as v  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
AUDIO = os.path.join(ROOT, "src", "audio")
TB = v.TB_HZ


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def part():
    t = read(HW)
    i = t.index("\n## V22 ")
    j = t.find("\n## V", i + 1)
    return t[i:j] if j >= 0 else t[i:]


# ------------------------------------------------------------------ synthetic builders

def square(n, period=32, lo=-8000, hi=8000, phase=0):
    """A decoded square tone, one int16 per AUDIO block."""
    return [hi if ((k + phase) % period) >= period // 2 else lo for k in range(n)]


def report(**over):
    r = {"test_id": "GBP-AUDIO-007", "build_id": "synthetic",
         "presses": {"a": 1, "other": 0},
         "control": {"ran": True, "gave_up": False, "blocks": 2048, "periods": 63, "pmin": 32, "pmax": 32},
         "window": {"ticks": 60 * TB + 5, "coverage": [4096] * 60,
                    "l": {"periods": 7679, "pmin": 32, "pmax": 32},
                    "not_drained": 0, "overflow": 0, "underrun": 0, "fill": [2048] * 60,
                    "corrections": {"dup": 222, "drop": 0}},
         "m": {"callbacks": 1922, "t_first": 0, "t_last": 0, "frames_per_callback": 1000}}
    for k, val in over.items():
        sect, _, key = k.partition("__")
        if key:
            r[sect][key] = val
        else:
            r[sect] = val
    return r


class Console:
    """What the POC will do, restated independently of the tool: ONE continuous
    resampler run from init, corrections between the ring and the resampler,
    chunks cut from its output, silence chunks handed without advancing it."""

    def __init__(self, warm, window, chunk_frames, chunks, dup=(), drop=(), silence=()):
        rows = gen_aresamp.table()
        self.rows = rows
        hist, hpos, acc = [0] * 16, 0, 0
        pre = [(x, False) for x in warm]
        body = []
        for i, x in enumerate(window):
            if i in drop:
                continue
            body.append(x)
            if i in dup:
                body.append(x)
        # the warm-up, continuously, and the state the window starts from
        for x, _ in pre:
            hist[hpos] = x
            hpos = (hpos + 1) % 16
            while acc < 125:
                acc += 16
            acc -= 125
        self.state = {"hist": list(hist), "hpos": hpos, "acc": acc}
        need = (chunks - len(silence)) * chunk_frames
        frames, used = [], 0
        for x in body:
            if len(frames) >= need:
                break
            hist[hpos] = x
            hpos = (hpos + 1) % 16
            while acc < 125:
                s = sum(rows[acc][m] * hist[(hpos + m) % 16] for m in range(16))
                q = (s + 16384) >> 15 if s >= 0 else -(((-s) + 16384) >> 15)
                frames.append(max(-32767, min(32767, q)))
                acc += 16
            acc -= 125
            used += 1
        # the kept stream is exactly what the window consumed
        kept_raw, pushes = [], 0
        for i, x in enumerate(window):
            if pushes >= used:
                break
            kept_raw.append(x)
            pushes += 0 if i in drop else (2 if i in dup else 1)
        self.decoded = kept_raw
        body_bytes = bytearray()
        k = 0
        for c in range(chunks):
            if c in silence:
                body_bytes += b"\x00" * (4 * chunk_frames)
            else:
                for y in frames[k:k + chunk_frames]:
                    body_bytes += struct.pack(">hh", y, y)
                k += chunk_frames
        self.crc = zlib.crc32(bytes(body_bytes)) & 0xFFFFFFFF
        self.events = ([(v.EV_DUP, i) for i in sorted(dup) if i < len(kept_raw)] +
                       [(v.EV_DROP, i) for i in sorted(drop) if i < len(kept_raw)] +
                       [(v.EV_SILENCE, c) for c in sorted(silence)])
        self.chunk_frames, self.chunks = chunk_frames, chunks

    def sidecar(self, **over):
        st = dict(self.state, **{k: over[k] for k in ("hist", "hpos", "acc") if k in over})
        decoded = over.get("decoded", self.decoded)
        events = over.get("events", self.events)
        crc = over.get("crc", self.crc)
        b = bytearray(v.L2_MAGIC)
        b += struct.pack(">6I", 1, self.chunk_frames, self.chunks, crc, st["acc"], st["hpos"])
        b += struct.pack(">16h", *st["hist"])
        b += struct.pack(">2I", len(decoded), len(events))
        for kind, idx in events:
            b += struct.pack(">2I", kind, idx)
        b += struct.pack(">%dh" % len(decoded), *decoded)
        b += struct.pack(">I", zlib.crc32(bytes(b)) & 0xFFFFFFFF)
        return bytes(b)


# ------------------------------------------------------------------ the resampler

HARNESS = r"""
#include <stdio.h>
#include <stdint.h>
#include "gbp_aresamp.h"
int main(int argc, char **argv) {
    FILE *in = fopen(argv[1], "rb"), *out = fopen(argv[2], "wb");
    struct gbp_aresamp r; int16_t x, y[GBP_ARESAMP_MAX_OUT];
    if (!in || !out) return 2;
    gbp_aresamp_init(&r);
    while (fread(&x, 2, 1, in) == 1) {
        uint32_t n = gbp_aresamp_push(&r, x, y);
        if (fwrite(y, 2, n, out) != n) return 3;
    }
    fclose(in); fclose(out); return 0;
}
"""


class TheHostResamplerIsTheFrozenOne(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="v22-")
        src = os.path.join(cls.tmp, "h.c")
        with open(src, "w") as f:
            f.write(HARNESS)
        cls.bin = os.path.join(cls.tmp, "h")
        cls.have, cls.ok, cls.err = hostcc.compile_c(
            ["-std=gnu11", "-O1", "-Wall", "-Wextra", "-I", AUDIO, "-o", cls.bin, src,
             os.path.join(AUDIO, "gbp_aresamp.c")])

    def test_bit_identical_to_the_C_source(self):
        hostcc.require(self, self.have, self.ok, self.err)
        rnd = random.Random(92)
        xs = [rnd.choice((-32768, 32767, 0, -1, 1)) if k % 97 == 0 else rnd.randint(-32768, 32767)
              for k in range(4000)] + square(1000)
        p = os.path.join(self.tmp, "in.s16")
        with open(p, "wb") as f:
            f.write(struct.pack("<%dh" % len(xs), *xs))
        subprocess.run([self.bin, p, p + ".out"], check=True, timeout=60)
        with open(p + ".out", "rb") as f:
            b = f.read()
        c_out = list(struct.unpack("<%dh" % (len(b) // 2), b))
        py_out, used = v.resample_from({"hist": [0] * 16, "hpos": 0, "acc": 0}, xs, 10 ** 9)
        self.assertEqual(used, len(xs))
        self.assertEqual(len(c_out), -((-125 * len(xs)) // 16))
        self.assertEqual(py_out, c_out)

    def test_resuming_from_a_kept_state_equals_a_continuous_run(self):
        xs = square(900, phase=5) + [rnd for rnd in random.Random(7).choices(range(-20000, 20000), k=300)]
        whole, _ = v.resample_from({"hist": [0] * 16, "hpos": 0, "acc": 0}, xs, 10 ** 9)
        for k in (160, 333, 777):
            c = Console(xs[:k], [], 1, 1)
            head = -((-125 * k) // 16)
            tail, _ = v.resample_from(c.state, xs[k:], 10 ** 9)
            self.assertEqual(whole[head:], tail, k)


# ------------------------------------------------------------------ QUESTION L

class QuestionL(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(v.question_L(report())["verdict"], "PASS")

    def test_a_constant_wrong_period_fails(self):
        self.assertEqual(v.question_L(report(window__l={"periods": 7926, "pmin": 31, "pmax": 31}))["verdict"], "FAIL")

    def test_not_constant_fails(self):
        self.assertEqual(v.question_L(report(window__l={"periods": 7679, "pmin": 32, "pmax": 33}))["verdict"], "FAIL")
        self.assertEqual(v.question_L(report(window__l={"periods": 0, "pmin": 0, "pmax": 0}))["verdict"], "FAIL")

    def test_press_count_is_exactly_one_A_and_nothing_else(self):
        for p in ({"a": 0, "other": 0}, {"a": 2, "other": 0}, {"a": 1, "other": 1}):
            self.assertEqual(v.question_L(report(presses=p))["verdict"], "INCONCLUSIVE", p)

    def test_a_missing_tone_is_inconclusive_never_fail(self):
        bad = [{"gave_up": True}, {"ran": False}, {"periods": 47}, {"pmin": 31}, {"pmax": 33}, {"blocks": 2047}]
        for b in bad:
            c = dict(report()["control"], **b)
            self.assertEqual(v.question_L(report(control=c))["verdict"], "INCONCLUSIVE", b)

    def test_the_window_is_C_s_and_at_least_60_s(self):
        self.assertEqual(v.question_L(report(window__ticks=60 * TB - 1))["verdict"], "INCONCLUSIVE")
        self.assertEqual(v.question_L(report(window__ticks=60 * TB))["verdict"], "PASS")

    def test_coverage_under_D1_is_a_drain_result(self):
        cov = [4096] * 60
        cov[17] = 4091                                   # 0.99878
        self.assertEqual(v.question_L(report(window__coverage=cov))["verdict"], "INCONCLUSIVE")
        cov[17] = 4092                                   # 0.99902, at D1's threshold
        self.assertEqual(v.question_L(report(window__coverage=cov))["verdict"], "PASS")

    def test_e_after_the_corrections_a_healthy_tone_would_fail(self):
        """§V22.8 (e), demonstrated: the decoder's rising-edge rule over a perfect 32-period tone
        with §V22.4's ~3.7 duplicates per second."""
        def periods(xs):
            prev, last, out = None, None, []
            for k, x in enumerate(xs):
                if prev is not None and prev <= 0 < x:
                    if last is not None:
                        out.append(k - last)
                    last = k
                prev = x
            return out
        tone = square(60 * 4096)
        self.assertEqual(set(periods(tone)), {32})
        dup = set(range(0, len(tone), 1108))             # 3.70 per second
        after = []
        for i, x in enumerate(tone):
            after.append(x)
            if i in dup:
                after.append(x)
        p = periods(after)
        self.assertEqual((min(p), max(p)), (32, 33))
        self.assertGreater(sum(1 for q in p if q == 33), 200)


# ------------------------------------------------------------------ QUESTION L2

class QuestionL2(unittest.TestCase):
    def small(self):
        self._saved = v.L2_MIN_FRAMES
        v.L2_MIN_FRAMES = 2000
        self.addCleanup(setattr, v, "L2_MIN_FRAMES", self._saved)

    def console(self, **kw):
        warm = square(1024, phase=3)
        window = square(4096, phase=3 + 1024)
        args = dict(chunk_frames=1000, chunks=4)
        args.update(kw)
        return Console(warm, window, **args)

    def test_full_length_pass_with_corrections_and_a_silence_chunk(self):
        warm = square(2048)
        window = square(45000, phase=2048)
        dup = set(range(300, 45000, 1108))
        c = Console(warm, window, 1000, 321, dup=dup, drop={5000}, silence={200})
        r = v.question_L2(c.sidecar())
        self.assertEqual(r["verdict"], "PASS", r["why"])
        self.assertEqual(r["frames"], 321000)

    def test_small_pass(self):
        self.small()
        c = self.console(dup={10, 900}, drop={400})
        self.assertEqual(v.question_L2(c.sidecar())["verdict"], "PASS")

    def test_one_changed_sample_fails(self):
        self.small()
        c = self.console()
        d = list(c.decoded)
        d[123] += 1
        r = v.question_L2(c.sidecar(decoded=d))
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("the host computes", r["why"])

    def test_a_wrong_kept_state_fails(self):
        self.small()
        c = self.console()
        h = list(c.state["hist"])
        # NOT hist[hpos]: that is the oldest sample, which the window's first push overwrites unread
        self.assertEqual(c.state["hpos"], 0)
        # a whole-sign error: a 1-LSB change of an old sample can vanish in the Q15 rounding and change
        # no byte handed to the AI, and then PASS is right -- the gate is exact on what was HANDED
        h[(c.state["hpos"] + 5) % 16] = -h[(c.state["hpos"] + 5) % 16]
        same = list(c.state["hist"])
        same[c.state["hpos"]] ^= 1
        self.assertEqual(v.question_L2(c.sidecar(hist=same))["verdict"], "PASS")
        self.assertEqual(v.question_L2(c.sidecar(hist=h))["verdict"], "FAIL")
        self.assertEqual(v.question_L2(c.sidecar(acc=(c.state["acc"] + 16) % 125))["verdict"], "FAIL")

    def test_an_unrecorded_correction_fails(self):
        self.small()
        c = self.console(dup={50})
        self.assertEqual(v.question_L2(c.sidecar(events=[]))["verdict"], "FAIL")

    def test_an_unrecorded_silence_chunk_fails(self):
        self.small()
        c = self.console(silence={1})
        self.assertEqual(v.question_L2(c.sidecar(events=[]))["verdict"], "FAIL")

    def test_the_kept_stream_is_exactly_what_the_window_used(self):
        self.small()
        c = self.console()
        r = v.question_L2(c.sidecar(decoded=c.decoded + [0]))
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("did not use", r["why"])
        r = v.question_L2(c.sidecar(decoded=c.decoded[:-1]))
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("yields", r["why"])

    def test_a_malformed_or_absent_record_fails_with_its_reason(self):
        self.small()
        c = self.console()
        good = c.sidecar()
        self.assertEqual(v.question_L2(None)["verdict"], "FAIL")
        for bad, why in ((b"X" + good[1:], "magic"), (good[:-1] + bytes([good[-1] ^ 1]), "own CRC-32"),
                         (good[:100], "malformed")):
            r = v.question_L2(bad)
            self.assertEqual(r["verdict"], "FAIL")
            self.assertIn(why, r["why"])
        for events in ([(v.EV_DUP, 7), (v.EV_DROP, 7)], [(9, 1)], [(v.EV_SILENCE, 4)], [(v.EV_DUP, 10 ** 6)]):
            r = v.question_L2(c.sidecar(events=events))
            self.assertEqual(r["verdict"], "FAIL", events)
            self.assertIn("malformed", r["why"])

    def test_the_window_is_at_least_10_s(self):
        c = self.console()                               # 4 chunks x 1000 frames, far under 320 000
        r = v.question_L2(c.sidecar())
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("10 s", r["why"])


# ------------------------------------------------------------------ QUESTION C and M

class QuestionC(unittest.TestCase):
    def test_pass_is_what_the_counters_say_never_no_loss(self):
        r = v.question_C(report())
        self.assertEqual(r["verdict"], "PASS")
        self.assertIn("NOT a claim of no loss", r["why"])
        self.assertEqual((len(r["coverage"]), len(r["fill"])), (60, 60))

    def test_overflow_or_underrun_fails_and_the_losses_stay_apart(self):
        for k in ("overflow", "underrun"):
            r = v.question_C(report(**{"window__" + k: 1}))
            self.assertEqual(r["verdict"], "FAIL", k)
        r = v.question_C(report(window__not_drained=99))
        self.assertEqual(r["verdict"], "PASS")           # NOT DRAINED is L's arm, reported here, never C's verdict
        self.assertEqual(r["not_drained"], 99)

    def test_under_60_s_is_inconclusive(self):
        self.assertEqual(v.question_C(report(window__ticks=59 * TB))["verdict"], "INCONCLUSIVE")


class MeasurementMAndTheCorrectionRate(unittest.TestCase):
    def test_the_ai_rate_from_callback_timestamps(self):
        for hz in (32000.0, v.AI_MODEL_HZ, 31990.0):
            n = 1922
            t_last = int(round((n - 1) * 1000 * TB / hz))
            m = v.measurement_M(report(m={"callbacks": n, "t_first": 0, "t_last": t_last,
                                          "frames_per_callback": 1000}))
            self.assertAlmostEqual(m["rate_hz"], hz, places=2)
        self.assertIsNone(v.measurement_M(report(m={"callbacks": 1, "t_first": 0, "t_last": 0,
                                                     "frames_per_callback": 1000}))["rate_hz"])

    def test_the_predicted_rate_is_stated_beside_the_observed(self):
        k = v.correction_rate(report(window__coverage=[4095.949] * 60))
        self.assertAlmostEqual(k["predicted_by_dolphin_model"], 3.695, places=3)
        self.assertAlmostEqual(k["observed_net_dup_per_s"], 222 / 60.0, places=3)


class TheCommandLine(unittest.TestCase):
    def test_it_prints_every_verdict_and_the_series(self):
        with tempfile.TemporaryDirectory() as d:
            j = os.path.join(d, "r.json")
            with open(j, "w") as f:
                import json
                json.dump(report(), f)
            out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v22accept.py"), j],
                                 capture_output=True, text=True, timeout=60, check=True).stdout
        for tok in ("  L   PASS", "  L2  FAIL          no L2 record", "  C   PASS",
                    "reported IN FULL, PASS or FAIL", "       s= 59  drained 4096  fill 2048"):
            self.assertIn(tok, out, tok)


class TheModuleAuthorisesNothing(unittest.TestCase):
    def test_it_reads_no_capture_and_writes_nothing(self):
        src = read(os.path.join(ROOT, "tools", "v22accept.py"))
        for forbidden in ("captures/", "logs/", "subprocess", '"w"', "'w'", '"wb"'):
            self.assertNotIn(forbidden, src, forbidden)
        self.assertEqual(src.count("open("), 2, "main() opens the report and the sidecar it is given, nothing else")


class ThePartIsWhatItSays(unittest.TestCase):
    def test_not_run_and_mints_nothing(self):
        p = part()
        self.assertIn("NOT RUN, NOT AUTHORISED HERE", p.splitlines()[1])
        self.assertNotRegex(p, r"^#{2,4} +GBP-HW-\d{3}")

    def test_the_readings_confirmed_before_freezing_are_in_it(self):
        p = part()
        for tok in ("L is read on the drain's decoded stream as it leaves\n  the decoder, before any §V22.4 correction",
                    "L is read over QUESTION C's window (≥ 60 s from the\n  origin)",
                    "§V19's CONTROL window as\n  §V19.11 A4.7 defines it",
                    "The resampler's state at the window's start is KEPT:",
                    "exactly as handed to\n  `AUDIO_InitDMA`",
                    "(u) underrun inside the L2 window", "(r) \"any press count but one\"",
                    "348c0c55f1c2101e8d0f1c3fad83d055008834b77900827e803f7936760bfce0"):
            self.assertIn(tok, p, tok)

    def test_the_decision_and_the_measurement_are_stated_before_the_run(self):
        p = part()
        for tok in ("**DECISION: counted drop/duplicate. NOT a ratio servo.**", "~**222 events in 60 s**",
                    "The AI figure is a HYPOTHESIS, not a premise.", "MEASUREMENT M",
                    "**No blinding is required and none is claimed.**", "`U-GBP-012`'s layout half stays open"):
            self.assertIn(tok, p, tok)


if __name__ == "__main__":
    unittest.main()
