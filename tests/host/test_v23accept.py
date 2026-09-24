"""tests/host/test_v23accept.py -- GitHub Issue #101: §V23's gates, exercised on SYNTHETIC vectors only.

Every construction here is built from the gate's own definitions, never from a run: a 128 Hz tone
drained at 4096 blocks/s with jitter and chosen losses, frames of 40 VIDEO blocks with chosen blocks
missing, AI callbacks every 31.222 ms, chain steps at chosen phases. The tests that matter most are
the ones §V23 exists for:
  - a completion gap of 1.94 block periods with NOTHING lost is not a loss (RUN 37's case, §V23.1);
  - two INDEPENDENT stalls that share one phase band are NOT COINCIDENT, although a uniform null
    would call them coincident at p < 0.001 (§V23.2 -- the gate must not rediscover the cadence);
  - a loss overlapping a recorder write goes to the recorder before the chain (§V23.8 (a)).
"""
import io
import json
import os
import random
import re
import sys
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v23accept as V  # noqa: E402

TB = V.TB_HZ
T = TB / 4096.0                       # one AUDIO block period, in ticks
P = TB * 1000 / 32028.483             # one AI chunk period
FRAME = TB / 59.727                   # one AGB frame
VBLOCK = TB * 4 * 1232 / 16777216.0   # one VIDEO block: 4 scanlines


def tone(n_blocks, lost, jitter=0.6, seed=1, t0=10 ** 9, late=None):
    """(decoded, ticks) of a 128 Hz tone drained block by block. Block k is readable during
    [k T, (k + 1) T); it is read at k T + u T, u in [0, jitter), unless it is in `lost`.
    `late` maps a block index to a fixed u, to place a read exactly."""
    rng = random.Random(seed)
    dec, ticks = [], []
    for k in range(n_blocks):
        if k in lost:
            continue
        h, j = divmod(k, 16)
        v = (25900 if h % 2 == 0 else -23150) if j < 15 else (7500 if h % 2 == 0 else -4760)
        u = late[k] if late and k in late else rng.uniform(0, jitter)
        dec.append(v)
        ticks.append(int(t0 + (k + u) * T))
    return dec, ticks


def frames(n_frames, missing, t0=10 ** 9, seed=2):
    """(ticks, start) of n_frames frames of 40 VIDEO blocks; `missing` holds (frame, block) pairs."""
    rng = random.Random(seed)
    ticks, start = [], []
    for f in range(n_frames):
        for b in range(40):
            if (f, b) in missing:
                continue
            ticks.append(int(t0 + f * FRAME + b * VBLOCK + rng.uniform(0, 0.3) * VBLOCK))
            start.append(1 if b == 0 else 0)
    return ticks, start


def callbacks(t0, span, isr=800):
    out, t = [], t0
    while t < t0 + span:
        out.append([int(t), int(t + isr)])
        t += P
    return out


def report(audio, video=None, cbs=(), steps=(), coverage=None, framecap=None, ai_span=None, tap=None):
    dec, tk = audio
    vt, vs = video if video else ([], [])
    return {"test_id": "SYNTH", "build_id": "synth", "commit": "0", "tb_hz": TB,
            "window": {"t_origin": tk[0], "t_end": tk[-1], "coverage": coverage or [4070] * 4,
                       "framecap_session": framecap},
            "audio": {"ticks": tk, "decoded": dec}, "video": {"ticks": vt, "start": vs},
            "ai_span": ai_span, "callbacks": [list(c) for c in cbs], "steps": [list(s) for s in steps],
            "recorder": {"tap_ticks_per_cycle": tap or [], "tap_max_write": 40}}


class LocatingAudioLossesWithNoThreshold(unittest.TestCase):
    def test_every_lost_block_is_found_in_its_half_and_timed_at_the_read_that_ends_its_gap(self):
        lost = {40, 200, 201, 999}
        dec, tk = tone(1600, lost)
        got = V.audio_losses(dec, tk)
        self.assertEqual([x["k"] for x in got], [1, 2, 1])
        self.assertEqual(sum(x["k"] for x in got), len(lost))
        kept = [k for k in range(1600) if k not in lost]
        for x, first_after in zip(got, (41, 202, 1000)):
            self.assertEqual(x["t"], tk[kept.index(first_after)])       # the completion that ENDS the gap
            self.assertEqual(x["g1"], x["t"])

    def test_a_gap_of_1_94_periods_with_nothing_lost_is_not_a_loss(self):
        """RUN 37's case: block 500 read at the very start of its period, 501 at the very end."""
        dec, tk = tone(1600, set(), late={500: 0.0, 501: 0.94})
        i = next(i for i in range(len(tk) - 1) if tk[i + 1] - tk[i] > 1.9 * T)
        self.assertGreater((tk[i + 1] - tk[i]) / T, 1.9)
        self.assertEqual(V.audio_losses(dec, tk), [])

    def test_each_loss_carries_its_confidence(self):
        dec, tk = tone(1600, {300}, jitter=0.1)
        (x,) = V.audio_losses(dec, tk)
        self.assertGreater(x["confidence"], 1.5)       # little jitter: the loss's gap stands out

    def test_a_lost_step_sample_is_still_found(self):
        dec, tk = tone(800, {47})                  # 47 is the step sample of half 2
        self.assertEqual([x["k"] for x in V.audio_losses(dec, tk)], [1])

    def test_the_two_lists_must_agree_in_length(self):
        with self.assertRaises(ValueError):
            V.audio_losses([1, 2, 3], [1, 2])


class TheVideoGapDefined(unittest.TestCase):
    def test_a_missing_block_is_found_at_the_largest_intra_frame_gap(self):
        vt, vs = frames(6, {(2, 17)})
        gaps, an = V.video_gaps(vt, vs)
        self.assertEqual(an, [])
        self.assertEqual(len(gaps), 1)
        g = gaps[0]
        self.assertAlmostEqual((g["g1"] - g["g0"]) / VBLOCK, 2.0, delta=0.35)
        self.assertGreater(g["confidence"], 1.3)
        # timed at the completion of the first VIDEO block after the missing one: block 18 of frame 2
        self.assertEqual(g["t"], vt[2 * 40 + 17])

    def test_the_vblank_never_counts(self):
        vt, vs = frames(6, set())
        self.assertEqual(V.video_gaps(vt, vs), ([], []))

    def test_a_lost_frame_start_block_is_located_at_the_vblank_it_follows(self):
        vt, vs = frames(6, {(3, 0)})
        gaps, an = V.video_gaps(vt, vs)
        self.assertEqual((len(gaps), an), (1, []))
        self.assertGreater((gaps[0]["g1"] - gaps[0]["g0"]) / VBLOCK, 10)   # the vblank plus the lost block

    def test_two_missing_in_one_frame(self):
        vt, vs = frames(6, {(1, 5), (1, 30)})
        self.assertEqual(len(V.video_gaps(vt, vs)[0]), 2)


def shared_stalls(n_cycles, video_every=3, phase=0.07, t0=10 ** 9):
    """ONE stall per selected cycle, at one phase after the callback, costing an AUDIO block AND a
    VIDEO block: the two losses are one event."""
    audio_lost, video_missing, stall_t = set(), set(), []
    for c in range(n_cycles):
        ts = t0 + c * P + phase * P
        k = int((ts - t0) / T) + 1
        audio_lost.add(k)
        if c % video_every == 0:
            stall_t.append(ts)
    return audio_lost, stall_t


class QuestionK(unittest.TestCase):
    def setUp(self):
        self.t0 = 10 ** 9
        self.n_cycles = 180
        self.n_blocks = int(self.n_cycles * P / T) + 64

    def vgaps_at(self, times):
        return [{"t": int(t), "g0": int(t - VBLOCK), "g1": int(t), "confidence": 2.0} for t in times]

    def test_one_stall_costing_both_is_COINCIDENT(self):
        """Stalls in 62 % of the cycles, each at its own phase in the same 1.5-3.5 ms band, each costing
        an AUDIO block; every third stall ALSO costs a VIDEO block, read in the same service pass. The
        phase-preserving null moves those VIDEO gaps to other cycles, where the stall -- if there is one --
        sits at another phase of the band: they then miss. Same event, so COINCIDENT."""
        rng = random.Random(11)
        n_cycles = 300
        n_blocks = int(n_cycles * P / T) + 64
        lost, stall_blocks = set(), []
        for c in range(n_cycles):
            if rng.random() < 0.62:
                k = int((c * P + rng.uniform(1.5e-3, 3.5e-3) * TB) / T)
                lost.add(k)
                stall_blocks.append(k)
        dec, tk = tone(n_blocks, lost, t0=self.t0)
        losses = V.audio_losses(dec, tk)
        kept = [k for k in range(n_blocks) if k not in lost]
        # the same stall's VIDEO block completes in the same pass, 2 600 ticks after the AUDIO read that ends it
        vt = [tk[kept.index(k + 1)] + 2600 for k in stall_blocks[::3]]
        k = V.question_K(losses, self.vgaps_at(vt), callbacks(self.t0, n_cycles * P), (tk[0], tk[-1]),
                         trials=3000)
        self.assertEqual(k["verdict"], "COINCIDENT", k["why"])
        self.assertLess(k["p_phase"], V.K_P)
        # a few are missed: jitter can make another gap of the half larger than the loss's own, and the
        # loss is then timed at the wrong read -- which is what each loss's confidence ratio reports
        self.assertGreaterEqual(k["observed"], 0.8 * len(vt))
        missed = [x for x in losses if x["confidence"] is not None and x["confidence"] < 1.2]
        self.assertTrue(missed, "the construction has close calls, and they are visible")

    def test_independent_stalls_sharing_one_phase_band_are_NOT_COINCIDENT(self):
        """The case §V23.2 was rewritten for: AUDIO losses 1-4 ms after the callback in most cycles,
        VIDEO losses 1-4 ms after the callback in other, independent cycles. A uniform null finds them
        'coincident' at p < 0.001; the phase-preserving null must not."""
        rng = random.Random(5)
        n_cycles = 300
        n_blocks = int(n_cycles * P / T) + 64
        lost = set()
        for c in range(n_cycles):
            if rng.random() < 0.62:
                lost.add(int((c * P + rng.uniform(1.5e-3, 3.5e-3) * TB) / T))
        dec, tk = tone(n_blocks, lost, t0=self.t0)
        losses = V.audio_losses(dec, tk)
        vt = [self.t0 + c * P + rng.uniform(1.5e-3, 3.5e-3) * TB for c in range(0, n_cycles, 3)]
        k = V.question_K(losses, self.vgaps_at(vt), callbacks(self.t0, n_cycles * P), (tk[0], tk[-1]),
                         trials=3000)
        self.assertEqual(k["verdict"], "NOT COINCIDENT", k["why"])
        self.assertGreater(k["p_phase"], V.K_P)
        self.assertLess(k["p_uniform"], V.K_P, "the uniform null WOULD have called this coincident")

    def test_fewer_than_ten_video_gaps_is_INCONCLUSIVE(self):
        dec, tk = tone(4000, {100, 900})
        k = V.question_K(V.audio_losses(dec, tk), self.vgaps_at([tk[99]] * 9), callbacks(tk[0], 4000 * T),
                         (tk[0], tk[-1]), trials=100)
        self.assertEqual(k["verdict"], "INCONCLUSIVE")

    def test_a_failed_observer_gate_makes_K_INCONCLUSIVE(self):
        lost, stall_t = shared_stalls(self.n_cycles)
        dec, tk = tone(self.n_blocks, lost, t0=self.t0)
        losses = V.audio_losses(dec, tk)
        vt = [min((x["t"] for x in losses), key=lambda a: abs(a - s)) + 2600 for s in stall_t]
        k = V.question_K(losses, self.vgaps_at(vt), callbacks(self.t0, self.n_cycles * P), (tk[0], tk[-1]),
                         trials=200, observer_ok=False)
        self.assertEqual(k["verdict"], "INCONCLUSIVE")
        self.assertIn("observer", k["why"])

    def test_the_default_is_twenty_thousand_sets_and_a_fixed_seed(self):
        self.assertEqual((V.K_TRIALS, V.K_P, V.K_MIN_VIDEO), (20000, 0.001, 10))
        dec, tk = tone(3000, {100, 700, 1500})
        losses = V.audio_losses(dec, tk)
        vg = self.vgaps_at([tk[i] for i in range(50, 3000, 250)])
        cb = callbacks(tk[0], 3000 * T)
        a = V.question_K(losses, vg, cb, (tk[0], tk[-1]), trials=500)
        b = V.question_K(losses, vg, cb, (tk[0], tk[-1]), trials=500)
        self.assertEqual((a["p_phase"], a["p_uniform"]), (b["p_phase"], b["p_uniform"]))


class QuestionP(unittest.TestCase):
    def loss(self, g0, g1):
        return {"t": g1, "g0": g0, "g1": g1, "k": 1}

    def test_the_longest_overlap_names_the_step(self):
        steps = [[1000, 5000, "produce", 5000], [9000, 9500, "flush_queue", 9500]]
        p = V.question_P([self.loss(2000, 12000)], steps, [])
        self.assertEqual(p["counts"]["produce"], 1)
        self.assertEqual(p["decision"], "P names `produce`")

    def test_ties_go_to_the_instrument_before_the_chain(self):
        """§V23.8 (a): deliberate -- it biases AGAINST naming the chain."""
        steps = [[1000, 2000, "produce", 3000]]          # the recorder wrote [2000, 3000): as long as the step
        p = V.question_P([self.loss(1000, 3000)], steps, [])
        self.assertEqual(p["counts"]["recorder"], 1)
        self.assertEqual(V.TIE_ORDER[:2], ("recorder", "isr"))

    def test_the_isr_window_is_a_candidate(self):
        p = V.question_P([self.loss(1000, 3000)], [], [[1200, 2900]])
        self.assertEqual(p["counts"]["isr"], 1)

    def test_neither_for_most_gaps_means_no_run_B_from_this_run(self):
        steps = [[1000, 2000, "produce", 2000]]
        losses = [self.loss(1000, 2000)] + [self.loss(10 ** 6 + i * 10 ** 4, 10 ** 6 + i * 10 ** 4 + 5000)
                                            for i in range(3)]
        p = V.question_P(losses, steps, [])
        self.assertEqual(p["counts"]["neither"], 3)
        self.assertEqual(p["decision"], "P names `neither` for most gaps: Run B is not designed from this run")

    def test_a_recorder_plurality_is_reported_as_a_finding(self):
        steps = [[1000, 1100, "produce", 3000]]
        p = V.question_P([self.loss(1000, 3000), self.loss(1050, 2900)], steps, [])
        self.assertEqual(p["names"], "recorder")
        self.assertIn("This instrumentation cannot answer the question at this granularity", p["decision"])
        self.assertIn("Run B is not designed from this run", p["decision"])

    def test_an_unknown_step_kind_is_refused(self):
        with self.assertRaises(ValueError):
            V.question_P([], [[1, 2, "resample_everything", 2]], [])


class TheObserverGate(unittest.TestCase):
    def test_the_count_bound_is_the_sanity_check_and_its_numbers(self):
        self.assertEqual((V.MEAN_UNDRAINED_MAX, V.FRAMECAP_WINDOW_MAX, V.FRAMECAP_SESSION_MAX), (31.8, 86, 99))
        dec, tk = tone(4000, set())
        vt, vs = frames(4, set(), t0=tk[0])
        r = report((dec, tk), (vt, vs), coverage=[4096 - 31, 4096 - 32])     # mean 31.5
        o = V.observer(r, [], 0)
        self.assertTrue(o["sanity_ok"])
        r["window"]["coverage"] = [4096 - 32, 4096 - 32]
        self.assertFalse(V.observer(r, [], 0)["sanity_ok"])

    def test_the_window_frames_bound_and_the_session_fallback(self):
        dec, tk = tone(4000, set())
        vt, vs = frames(4, set(), t0=tk[0])
        r = report((dec, tk), (vt, vs))
        self.assertTrue(V.observer(r, [], 86)["sanity_ok"])
        self.assertFalse(V.observer(r, [], 87)["sanity_ok"])
        r2 = report((dec, tk), None, framecap=99)
        o = V.observer(r2, [], 0)
        self.assertIn("whole-session FRAMECAP", o["frames_scope"])
        self.assertTrue(o["sanity_ok"])
        r2["window"]["framecap_session"] = 100
        self.assertFalse(V.observer(r2, [], 0)["sanity_ok"])

    def test_the_recorders_self_cost_is_reported_per_cycle(self):
        dec, tk = tone(4000, set())
        cb = callbacks(tk[0], 4000 * T)
        steps = [[cb[0][0] + 5000, cb[0][0] + 9000, "produce", cb[0][0] + 9400],
                 [cb[1][0] + 5000, cb[1][0] + 7000, "flush_queue", cb[1][0] + 7100]]
        r = report((dec, tk), None, cbs=cb, steps=steps, tap=[1000] * len(cb), framecap=50)
        pr = V.observer(r, [], 0)["primary"]
        self.assertEqual(pr["cycles"], len(cb))
        self.assertEqual(pr["max_single_write_ticks"], 400)
        self.assertEqual(pr["max_total_per_cycle_ticks"], 1400)


class TheWholeReport(unittest.TestCase):
    def build(self):
        t0 = 10 ** 9
        n_cycles = 150
        lost, stall_t = shared_stalls(n_cycles, t0=t0)
        dec, tk = tone(int(n_cycles * P / T) + 64, lost, t0=t0)
        cb = callbacks(t0, n_cycles * P)
        n_frames = int(n_cycles * P / FRAME)
        missing = set()
        for s in stall_t:
            f = int((s - t0) / FRAME)
            b = int((s - t0 - f * FRAME) / VBLOCK)
            if b < 39:
                missing.add((f, b + 1))
        vt, vs = frames(n_frames, missing, t0=t0 - 3 * FRAME)
        steps = [[int(t0 + c * P + 0.06 * P), int(t0 + c * P + 0.075 * P), "produce", int(t0 + c * P + 0.075 * P) + 30]
                 for c in range(n_cycles)]
        return report((dec, tk), (vt, vs), cbs=cb, steps=steps, coverage=[4070] * 4, framecap=40,
                      ai_span=[t0, t0 + int(n_cycles * P)], tap=[900] * len(cb))

    def test_evaluate_and_the_command_line(self):
        r = self.build()
        e = V.evaluate(r, trials=300)
        self.assertEqual(e["P"]["names"], "produce")
        self.assertIn(e["K"]["verdict"], ("COINCIDENT", "NOT COINCIDENT", "INCONCLUSIVE"))
        self.assertEqual(set(e["confinement"]), {"before", "inside", "after"})
        with io.StringIO() as buf, redirect_stdout(buf):
            import tempfile
            with tempfile.TemporaryDirectory() as d:
                p = os.path.join(d, "r.json")
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(r, f)
                V.K_TRIALS_SAVED, V.K_TRIALS = V.K_TRIALS, 300
                try:
                    V.main(["v23accept.py", p])
                finally:
                    V.K_TRIALS = V.K_TRIALS_SAVED
            out = buf.getvalue()
        for tok in ("OBSERVER  PRIMARY", "an UPPER BOUND, it includes the cost of measuring itself",
                    "SANITY", "A CHOSEN NUMBER", "  K   ", "the UNIFORM null, for comparison only",
                    "  P   no pass/fail", "(f) incomplete frames:", "close calls (largest gap < 1.2 x"):
            self.assertIn(tok, out, tok)

    def test_a_foreign_timebase_is_refused(self):
        r = self.build()
        r["tb_hz"] = 27000000
        with self.assertRaises(ValueError):
            V.evaluate(r, trials=10)


class TheModuleAuthorisesNothing(unittest.TestCase):
    def test_it_reads_no_capture_and_writes_nothing(self):
        with open(os.path.join(ROOT, "tools", "v23accept.py"), encoding="utf-8") as f:
            src = f.read()
        for forbidden in ("captures/", "logs/", "subprocess", '"w"', "'w'", '"wb"'):
            self.assertNotIn(forbidden, src, forbidden)
        self.assertEqual(src.count("open("), 1, "main() opens the report it is given, nothing else")


class TheGatesAreNotEditedAfterTheyWereFrozen(unittest.TestCase):
    """The base is pinned by HASH (tests/host/frozen.py). A gate edited after the image exists is not a
    pre-registration, and neither is one edited after the data does."""
    KEY = "Issue #101 -- §V23 transcribed, Run A's gates frozen"

    def test_the_gates_are_the_bytes_of_the_commit_that_froze_them(self):
        import frozen
        with open(os.path.join(ROOT, "tools", "v23accept.py"), encoding="utf-8") as f:
            now = f.read()
        self.assertEqual(frozen.source(self.KEY, "tools/v23accept.py"), now,
                         "tools/v23accept.py was edited after it was frozen")

    def test_the_part_was_frozen_in_the_same_commit_and_only_grows(self):
        """Byte-identical as the START of the part; numbered sections may be APPENDED -- a dated AMENDMENT,
        or the record of the image built (the amend-on-top convention of Issue #49)."""
        import frozen
        then = frozen.source(self.KEY, "docs/research/HARDWARE_TESTS.md")
        i = then.index("\n## V23 ")
        frozen_part = then[i:].rstrip("\n")
        now = ThePartSaysWhatItIs().part().rstrip("\n")
        self.assertTrue(now.startswith(frozen_part), "§V23's FROZEN bytes were edited -- appending is allowed")
        rest = now[len(frozen_part):].strip()
        if rest:
            self.assertRegex(rest, r"^### V23\.\d+ ", "anything appended must be a numbered section")
            for h in re.findall(r"^### V23\.(\d+) ", rest, re.M):
                self.assertGreater(int(h), 8, "an appended section reuses a frozen number")


class ThePartSaysWhatItIs(unittest.TestCase):
    def part(self):
        with open(os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md"), encoding="utf-8") as f:
            t = f.read()
        i = t.index("\n## V23 ")
        j = t.find("\n## V24 ", i)
        return t[i:j] if j >= 0 else t[i:]

    def test_not_run_and_mints_nothing(self):
        p = self.part()
        self.assertIn("NOT RUN, NOT AUTHORISED HERE", p.splitlines()[1])
        self.assertNotRegex(p, r"^#{2,4} +GBP-HW-\d{3}")

    def test_the_source_and_the_confirmation_are_hashed(self):
        p = self.part()
        for tok in ("e653bbf86b27a0dc75e887b781d52ffbbea90610fcce237408a3d92d984766c9",
                    "f0009a091ebe9aedc1affc8440c909ccbb68de1245d45a0b31157ac78119acbd",
                    "issuecomment-5814473348", "issuecomment-5814528526", "CONFIRMED all six before this commit"):
            self.assertIn(tok, p, tok)

    def test_the_premises_that_were_corrected_are_in_the_frozen_text(self):
        p = re.sub(r"\s+", " ", self.part())
        for tok in ("A completion gap above 1.5 block periods is **not** a lost block",
                    "The null must preserve the phase-lock we already established.",
                    "1.25x -- A CHOSEN NUMBER, NOT DERIVED", "There is no within-frame block index.",
                    "it biases AGAINST the finding we want", "The self-cost is an UPPER BOUND."):
            self.assertIn(tok, p, tok)


if __name__ == "__main__":
    unittest.main()
