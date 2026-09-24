"""
tests/host/test_v24accept.py — §V24's QUESTION S (tools/v24accept.py, GitHub Issue #105), on synthetic vectors
only, before the image exists.

A builder makes a whole report the way Run B's builder will: AI callbacks, one chunk per cycle produced in
16-push or 8-push steps by the frozen pair-balanced assignment, every production step tagged in its spare
byte, and sweep-0002's tone with losses planted per cycle and per arm. Pinned: the assignment and its
refusal; the cycle -> arm rule and its counted exclusions; each verdict and the precedence between them;
that a low half arm is the finding, never a failure; and that what is reported beside the verdict is there.
"""
import io
import json
import os
import random
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import v24accept  # noqa: E402

TB = 40500000
P = TB / 4096.0
CB = 1264500
T0 = 10 ** 9
HALF, FULL = 1, 0


def build(ncyc, p_loss, seed=1, halve=True, skip=(), double=(), coverage=4090, tamper=None, dropped=0):
    """p_loss: {arm: probability of one loss in the cycle}, or a callable (cycle, arm) -> 0/1."""
    rng = random.Random(seed)
    ent = [T0 + 400000 + k * CB for k in range(ncyc + 1)]   # the tone runs before the first callback, so
                                                             # every planted loss sits in a bracketed half
    callbacks = [[e, e + 67] for e in ent]
    steps, tags = [], []
    arms = v24accept.arms(ncyc + 2)
    seq = -1
    produced_in = {}
    for c in range(ncyc):
        if c in skip:
            continue
        for extra in range(2 if c in double else 1):
            seq += 1
            arm = arms[seq]
            n, first, other = (16, 1800, 1000) if (arm == HALF and halve) else (8, 2819, 1985)
            t = ent[c] + 4000 + extra * 200000
            for i in range(n):
                d = first if i == 0 else other
                steps.append([t, t + d, "produce", t + d + 30])
                tags.append(arm | ((1 if i == 0 else 0) << 1) | ((seq & 63) << 2))
                t += d + 3000
            produced_in.setdefault(c, []).append(arm)
    # the tone, 16 samples per half-period, with at most one planted loss in the first tenth of a cycle
    total = int((ent[-1] - T0) / P)
    lose = set()
    for c in range(ncyc):
        if c not in produced_in or len(produced_in[c]) != 1:
            continue
        arm = produced_in[c][0]
        hit = p_loss(c, arm) if callable(p_loss) else (rng.random() < p_loss[arm])
        if hit:
            i = int((ent[c] + 20000 - T0) / P) + 1
            while i % 16 in (0, 14, 15):              # a plateau sample away from the transitions
                i += 1
            lose.add(i)
    decoded, ticks = [], []
    for i in range(total):
        if i in lose:
            continue
        h = i // 16
        decoded.append(0 if i % 16 == 15 else (20000 if h % 2 == 0 else -20000))
        ticks.append(int(T0 + i * P))
    if tamper is not None:
        tags[tamper] ^= 1
    secs = int((ent[-1] - T0) / TB)
    return {"tb_hz": TB, "test_id": "GBP-AUDIO-009", "build_id": "synthetic",
            "window": {"t_origin": ent[0], "t_end": ent[-1], "coverage": [coverage] * max(1, secs),
                       "framecap_session": 0},
            "audio": {"ticks": ticks, "decoded": decoded}, "video": {"ticks": [], "start": []},
            "ai_span": [ent[0], ent[-1]], "callbacks": callbacks, "steps": steps, "step_tag": tags,
            "recorder": {"tap_ticks_per_cycle": [0] * ncyc, "tap_max_write": 0},
            "trace": {"dropped": {"step_dropped": dropped}}}


def S(report, trials=400):
    return v24accept.evaluate(report, trials=trials, k_trials=50)["S"]


class TheAssignment(unittest.TestCase):
    def test_pair_balanced_and_pinned(self):
        a = v24accept.arms(4000)
        self.assertTrue(all(a[2 * j] != a[2 * j + 1] for j in range(2000)))
        self.assertEqual(sum(a), 2000)
        self.assertEqual(a[:16], [1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1])

    def test_xorshift32_is_the_textbook_one(self):
        x = v24accept._xorshift32(v24accept.XS_SEED)
        y = v24accept.XS_SEED
        y ^= (y << 13) & 0xFFFFFFFF
        y ^= y >> 17
        y ^= (y << 5) & 0xFFFFFFFF
        self.assertEqual(x, y)
        self.assertEqual(v24accept.XS_SEED, 0x9E3779B9)

    def test_a_tag_that_disagrees_is_refused_INCONCLUSIVE_never_a_FAIL(self):
        r = build(300, {HALF: 0.5, FULL: 0.5}, tamper=40)
        s = S(r)
        self.assertEqual(s["verdict"], "INCONCLUSIVE")
        self.assertTrue(s["refused"])
        self.assertIn("disagrees with the frozen assignment", s["why"])

    def test_overflowed_or_missing_tags_are_refused(self):
        self.assertIn("overflowed", S(build(200, {HALF: 0.5, FULL: 0.5}, dropped=3))["why"])
        r = build(200, {HALF: 0.5, FULL: 0.5})
        del r["step_tag"]
        self.assertIn("no arm tag", S(r)["why"])


class TheVerdicts(unittest.TestCase):
    def test_CAUSE_when_the_half_arm_loses_fewer(self):
        s = S(build(1200, {HALF: 0.4, FULL: 0.8}))
        self.assertEqual(s["verdict"], "CAUSE", s["why"])
        self.assertLess(s["p"], 0.05)
        self.assertLess(s["ci90"][1], 0.7)
        self.assertAlmostEqual(s["ratio"], 0.5, delta=0.08)

    def test_ACCOMMODATION_when_the_stretch_halves_and_the_losses_do_not_move(self):
        s = S(build(1200, lambda c, arm: 1))                   # one loss in every cycle, both arms
        self.assertEqual(s["verdict"], "ACCOMMODATION", s["why"])
        self.assertEqual(s["ci90"], [1.0, 1.0])
        self.assertLess(s["stretch_ratio"]["median"], 0.6)

    def test_NEITHER_when_the_stretch_did_not_halve(self):
        s = S(build(800, {HALF: 0.3, FULL: 0.8}, halve=False))
        self.assertEqual(s["verdict"], "NEITHER", s["why"])
        self.assertNotIn("p", s)                              # the gaps are not read

    def test_INCONCLUSIVE_when_the_full_arm_cannot_power_the_test(self):
        s = S(build(400, {HALF: 0.8, FULL: 0.8}))
        self.assertEqual(s["verdict"], "INCONCLUSIVE")
        self.assertIn("fewer than 250", s["why"])

    def test_a_LOW_HALF_ARM_is_the_finding_never_a_failure(self):
        s = S(build(800, {HALF: 0.0, FULL: 0.8}))
        self.assertEqual(s["arms"]["half"]["loss_gaps"], 0)
        self.assertEqual(s["verdict"], "CAUSE", s["why"])

    def test_INCONCLUSIVE_when_the_observer_gate_fails(self):
        s = S(build(800, {HALF: 0.4, FULL: 0.8}, coverage=4000))   # 96 undrained/s > 31.8
        self.assertEqual(s["verdict"], "INCONCLUSIVE")
        self.assertIn("observer gate", s["why"])

    def test_a_small_significant_reduction_is_CAUSE_and_reads_as_small(self):
        s = S(build(2000, lambda c, arm: 0 if (arm == HALF and c % 16 == 1) else 1))
        self.assertEqual(s["verdict"], "CAUSE", s["why"])
        self.assertGreater(s["ci90"][0], 0.90)                # ACCOMMODATION's condition also holds...
        self.assertIn("ratio 0.9", s["why"])                  # ...and the report says how small it is

    def test_UNRESOLVED_when_the_run_cannot_separate_them(self):
        """330 against 350 losses in 500 cycles per arm, a ratio of 0.943: too small to be significant, too
        uncertain for its 90 % CI to clear 0.90. Deterministic frequencies, so the vector is not a lucky draw."""
        seen = {HALF: 0, FULL: 0}

        def hit(c, arm):
            k = seen[arm]
            seen[arm] += 1
            return (k % 10 < 7) if arm == FULL else (k % 100 < 66)
        s = S(build(1000, hit), trials=2000)
        self.assertEqual((s["arms"]["half"]["loss_gaps"], s["arms"]["full"]["loss_gaps"]), (330, 350))
        self.assertEqual(s["verdict"], "UNRESOLVED", (s["why"], s.get("ci90")))
        self.assertIn("likely by design", s["why"])


class TheCyclesAndWhatIsReported(unittest.TestCase):
    def test_excluded_cycles_are_counted_and_the_250_is_on_the_analysed_ones(self):
        r = build(900, {HALF: 0.5, FULL: 0.9}, skip=set(range(0, 900, 10)), double={5, 15})
        s = S(r)
        ex = s["excluded_cycles"]
        self.assertEqual(ex["no_production_step"], 90)
        self.assertEqual(ex["two_chunks_steps"], 2)
        self.assertEqual(ex["open_last_cycle"], 1)
        self.assertEqual(s["arms"]["half"]["cycles"] + s["arms"]["full"]["cycles"], 900 - 90 - 2)

    def test_both_distributions_are_reported_at_the_same_quantiles(self):
        s = S(build(1200, {HALF: 0.4, FULL: 0.8}))
        for arm in ("half", "full"):
            a = s["arms"][arm]
            for key in ("stretch_ticks", "loss_gap_T", "noloss_production_gap_T"):
                self.assertEqual(sorted(a[key]), ["p10", "p25", "p50", "p75", "p90", "p99"], (arm, key))
        self.assertEqual(s["arms"]["full"]["stretch_ticks"]["p90"], 2819)   # the chunk-start step, 1/8 of them
        self.assertEqual(s["arms"]["half"]["stretch_ticks"]["p90"], 1000)   # 1/16 of them: not at p90
        self.assertIn("between-run variation is unknown", s["context_rate"]["note"])

    def test_the_defaults_are_frozen(self):
        self.assertEqual((v24accept.S_TRIALS, v24accept.S_SEED, v24accept.S_ALPHA), (20000, 24, 0.05))
        self.assertEqual((v24accept.NEITHER_RATIO_MAX, v24accept.ACCOMM_CI_LOW, v24accept.FULL_MIN_LOSSES),
                         (0.60, 0.90, 250))
        self.assertEqual(v24accept.QS, (0.10, 0.25, 0.50, 0.75, 0.90, 0.99))

    def test_the_command_line(self):
        r = build(700, {HALF: 0.3, FULL: 0.8})
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.json")
            with open(p, "w") as f:
                json.dump(r, f)
            orig = v24accept.S_TRIALS
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = v24accept.main(["v24accept.py", p, "--json", os.path.join(d, "o.json")])
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("  S   CAUSE", out)
            self.assertIn("CONTEXT, not the discriminator", out)
            with open(os.path.join(d, "o.json")) as f:
                self.assertEqual(json.load(f)["S"]["verdict"], "CAUSE")
            self.assertEqual(orig, v24accept.S_TRIALS)


class TheModuleAuthorisesNothing(unittest.TestCase):
    def test_it_reads_no_capture_and_carries_v23_over_unedited(self):
        with open(os.path.join(ROOT, "tools", "v24accept.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("captures/", src.split('"""', 2)[2])
        self.assertIn("import v23accept", src)
        self.assertIn("base = v23accept.evaluate(report, k_trials)", src)


class TheGatesAreNotEditedAfterTheyWereFrozen(unittest.TestCase):
    """The amend-on-top convention: the tool never changes; the part's frozen start never changes; numbered
    sections may be APPENDED -- a dated AMENDMENT before any hardware, or the record of the image built."""
    KEY = "Issue #105 -- §V24 transcribed, Run B's QUESTION S frozen"

    def part(self):
        with open(os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md"), encoding="utf-8") as f:
            t = f.read()
        i = t.index("\n## V24 ")
        j = t.find("\n## V25 ", i)
        return t[i:j] if j >= 0 else t[i:]

    def test_the_gates_are_the_bytes_of_the_commit_that_froze_them(self):
        import frozen
        with open(os.path.join(ROOT, "tools", "v24accept.py"), encoding="utf-8") as f:
            now = f.read()
        self.assertEqual(frozen.source(self.KEY, "tools/v24accept.py"), now,
                         "tools/v24accept.py was edited after it was frozen")

    def test_the_part_was_frozen_in_the_same_commit_and_only_grows(self):
        import frozen
        import re
        then = frozen.source(self.KEY, "docs/research/HARDWARE_TESTS.md")
        frozen_part = then[then.index("\n## V24 "):].rstrip("\n")
        now = self.part().rstrip("\n")
        self.assertTrue(now.startswith(frozen_part), "§V24's FROZEN bytes were edited -- appending is allowed")
        rest = now[len(frozen_part):].strip()
        if rest:
            self.assertRegex(rest, r"^### V24\.\d+ ", "anything appended must be a numbered section")
            for h in re.findall(r"^### V24\.(\d+) ", rest, re.M):
                self.assertGreater(int(h), 7, "an appended section reuses a frozen number")

    def test_the_transcription_is_the_comment_byte_for_byte(self):
        """The source, as the frozen text records its hash: the body re-levelled is the part's body."""
        p = self.part()
        for tok in ("c965ef8009218500b6f95151d2a7d615307bcb0154f7f5df39470f68969a5e08",
                    "d97a3ce1f48f0a77c38b775a3ee42193341a226dbdb601e0d189728b667c2427",
                    "d37d98729b9aa09865dc7ce2cf9c893b05862fc6d4ea9c9a6139bf99b0a57380",
                    "issuecomment-5817266651", "issuecomment-5817343526", "issuecomment-5817351397",
                    "CONFIRMED all eight before this commit", "NOT RUN, NOT AUTHORISED HERE"):
            self.assertIn(tok, p, tok)
        flat = " ".join(p.split())
        for tok in ("The signature of CAUSE is FEWER losses, not SHORTER loss gaps",
                    "A LOW HALF ARM IS THE FINDING, NEVER A FAILURE",
                    "the cause/accommodation distinction is made by the ARM CONTRAST, not per gap",
                    "INCONCLUSIVE, never a FAIL", "roughly a 20 % chance of UNRESOLVED"):
            self.assertIn(" ".join(tok.split()), flat.replace("**", ""), tok)


if __name__ == "__main__":
    unittest.main()
