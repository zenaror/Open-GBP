"""
tests/host/test_vqual.py — §V5.44.17, the CROSS-RUN REPLAY of the prospective
window against the three real OGBPIDX1 captures.

WHAT THIS FILE IS FOR

The window decides when to START measuring. A rule like that is only worth
anything if it can be shown to do one thing and refuse to do another:

  it MUST remove a startup transient
  it MUST NOT rescue a run whose producer was faulty
  it MUST NOT rescue a run whose producer duplicated every frame

The three physical runs are exactly those three cases, produced by a
byte-identical GameCube runtime, so they make a natural three-way control:

  run 1  producer FAULT latched          -> STIMULUS_INVALID_FOR_DECISIVE_CLAIM
  run 2  systemic 2:1 duplicate ids      -> OBSERVED_DISCONTINUITY
  run 3  one id gap inside startup only  -> OBSERVED_DISCONTINUITY as captured

WHAT IS AND IS NOT BEING CLAIMED

Run 3's recorded verdict does NOT change and this file asserts that it does not.
The capture stands as OBSERVED_DISCONTINUITY for ever; nothing here re-judges
it. What is computed is a COUNTERFACTUAL: given a policy fixed in advance, which
frames would a FUTURE run have retained, and what would the unmodified analyzer
have said about that population. That is a prediction about stream-0006, not a
re-reading of stream-0005.

The distinction from the forbidden "find the last resync and analyze everything
after it" is that the cut point here is produced by a rule that (a) is causal --
it only ever looks at frames already past, (b) is structural -- it cannot see
FRAME_ID, STATUS, SYNC, CRC-8 or a pixel, and (c) is fixed before the data, so
it cannot be steered to a verdict. Point (c) is not asserted on trust: the
plateau test below shows the run-3 verdict is the same for every N from 2 to
128, so N=64 is a time-margin choice on a flat range and not a fitted one.

The replay is executed by the REAL C state machine (test_gbp_vwitness --replay),
never by a Python restatement of it, and it is fed the structural projection
(tools/vqual.py) which physically cannot carry stimulus content.
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import vqual      # noqa: E402
import vidxcap    # noqa: E402
import vindex     # noqa: E402

BIN = os.path.join(ROOT, "build", "tests", "unit", "test_gbp_vwitness")
FIX = os.path.join(ROOT, "captures", "fixtures")
PRODUCTION_N = 64

# The warm-up each run costs under the production policy, and the verdict the
# unmodified analyzer returns for the population the window would have kept.
RUNS = {
    "run1": {"warmup": 70, "retained": 1978, "as_captured": "STIMULUS_INVALID_FOR_DECISIVE_CLAIM",
             "counterfactual": "STIMULUS_INVALID_FOR_DECISIVE_CLAIM"},
    "run2": {"warmup": 71, "retained": 1977, "as_captured": "OBSERVED_DISCONTINUITY",
             "counterfactual": "OBSERVED_DISCONTINUITY"},
    "run3": {"warmup": 70, "retained": 1978, "as_captured": "OBSERVED_DISCONTINUITY",
             "counterfactual": "OBSERVED_CONTIGUOUS"},
}

_CACHE = {}


def fixture(tag):
    return os.path.join(FIX, "hw-gamecube-gbp-2026-09-19-idxcap-%s-qual.bin" % tag)


def sidecar(tag):
    """The full capture is large and lives outside Git; the structural fixture
    derived from it is what the repository carries. Tests that need the witness
    words skip when the capture is not on this machine."""
    for d in ("logs", os.path.join("captures", "local")):
        p = os.path.join(ROOT, d, "GBP-VIDEO-004_stream-0005-%s-idxcap.bin" % tag)
        if os.path.exists(p):
            return p
    return None


def replay(tag, n=PRODUCTION_N):
    key = (tag, n)
    if key not in _CACHE:
        out = subprocess.run([BIN, "--replay", fixture(tag), str(n)],
                             capture_output=True, text=True, check=True).stdout
        _CACHE[key] = {k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)\b", out)}
    return _CACHE[key]


def verdict_from(tag, drop):
    """The UNMODIFIED analyzer over the records the window would have kept."""
    key = ("v", tag, drop)
    if key not in _CACHE:
        p = sidecar(tag)
        info = _CACHE.setdefault(("s", tag), vidxcap.load(p))
        sel = [r for r in info["records"][drop:] if r["blocks_captured"] == 40]
        rep = vindex.analyze_run([r["witness"] for r in sel])
        _CACHE[key] = (rep["verdict"], len(sel))
    return _CACHE[key]


def needs_capture(tag):
    if sidecar(tag) is None:
        raise unittest.SkipTest("the %s capture is not on this machine" % tag)


class TheFixtureCarriesStructureAndNothingElse(unittest.TestCase):
    def test_each_run_has_a_fixture_that_parses(self):
        for tag in RUNS:
            info = vqual.load(fixture(tag))
            self.assertEqual(info["records_n"], 2048, tag)
            self.assertEqual(info["src_size"], 8946060, tag)

    def test_the_fixture_is_exactly_what_the_sidecar_projects(self):
        """Provenance is checkable, not asserted: re-deriving from the raw
        capture must reproduce the versioned bytes."""
        for tag in RUNS:
            needs_capture(tag)
            with open(fixture(tag), "rb") as f:
                self.assertEqual(vqual.project(sidecar(tag)), f.read(), tag)

    def test_it_cannot_carry_a_single_stimulus_word(self):
        """Structural by construction. A fixture 1/362 the size of the capture
        has no room for 40x54 words per frame, and the four fields it does keep
        are the assembler's verdict on shape."""
        for tag in RUNS:
            n = os.path.getsize(fixture(tag))
            self.assertEqual(n, 0x40 + 2048 * 12 + 12, tag)
            self.assertLess(n * 300, 8946060, tag)
        for r in vqual.load(fixture("run3"))["records"]:
            self.assertEqual(set(r), {"frame_index", "blocks", "flags", "completeness"})

    def test_the_parser_refuses_damage(self):
        raw = bytearray(open(fixture("run3"), "rb").read())
        for name, mutate in (
                ("magic", lambda b: b.__setitem__(0, b[0] ^ 1)),
                ("header crc", lambda b: b.__setitem__(0x0C, b[0x0C] ^ 1)),
                ("a record", lambda b: b.__setitem__(0x40, b[0x40] ^ 1)),
                ("footer", lambda b: b.__setitem__(len(b) - 5, b[len(b) - 5] ^ 1)),
                ("truncation", lambda b: b.__delitem__(slice(len(b) - 1, len(b)))),
        ):
            bad = bytearray(raw)
            mutate(bad)
            with self.assertRaises(vqual.QualError, msg=name):
                vqual.parse(bytes(bad))


class TheWindowOpensWhereThePolicySaysItDoes(unittest.TestCase):
    def test_the_real_state_machine_replays_each_run(self):
        for tag, want in RUNS.items():
            r = replay(tag)
            self.assertEqual(r["required"], PRODUCTION_N, tag)
            self.assertEqual(r["warmup_frames"], want["warmup"], tag)
            self.assertEqual(r["records_out"], want["retained"], tag)
            self.assertEqual(r["first_retained_frame"], want["warmup"], tag)

    def test_the_transient_is_four_frames_in_every_run(self):
        """The same GameCube runtime produced all three, and each one starts
        with the same shape of disturbance: four frames the assembler refuses,
        all inside the first seven."""
        for tag in RUNS:
            self.assertEqual(replay(tag)["warmup_disqualified"], 4, tag)
            self.assertEqual(replay(tag)["resets"], 1, tag)

    def test_it_arms_the_instant_the_streak_completes_and_not_before(self):
        for tag in RUNS:
            r = replay(tag)
            self.assertEqual(r["qual_state"], 2, tag)              # ARMED
            self.assertEqual(r["streak_at_arm"], PRODUCTION_N, tag)
            self.assertEqual(r["streak_max"], PRODUCTION_N, tag)

    def test_record_zero_begins_at_block_zero(self):
        for tag in RUNS:
            self.assertEqual(replay(tag)["record0_block0"], 1, tag)
            self.assertEqual(replay(tag)["blocks_out_of_range"], 0, tag)

    def test_the_warm_up_costs_no_record_capacity(self):
        for tag, want in RUNS.items():
            r = replay(tag)
            self.assertEqual(r["records_in"] - r["warmup_frames"], want["retained"], tag)
            self.assertEqual(r["frames_seen"], want["retained"], tag)


class WhatTheUnmodifiedAnalyzerWouldHaveSaid(unittest.TestCase):
    """The counterfactual. The analyzer is imported, never edited."""

    def test_the_recorded_verdicts_are_untouched(self):
        """THE GUARD ON THIS WHOLE ROUND. The captures keep the verdicts they
        earned; a policy for future runs may not reach back and improve them."""
        for tag, want in RUNS.items():
            needs_capture(tag)
            self.assertEqual(verdict_from(tag, 0)[0], want["as_captured"], tag)

    def test_run3_startup_gap_sits_at_record_five_far_inside_the_transient(self):
        needs_capture("run3")
        info = _CACHE.setdefault(("s", "run3"), vidxcap.load(sidecar("run3")))
        full = [(i, r) for i, r in enumerate(info["records"]) if r["blocks_captured"] == 40]
        rep = vindex.analyze_run([r["witness"] for _, r in full])
        gaps = [(a, b) for a, b, c in rep["decisive_transitions"] if c != "OBSERVED_ID_CONTIGUOUS"]
        self.assertEqual(gaps, [(0x12, 0x14)], "run 3 has exactly one non-contiguous transition")
        at = next(full[n][0] for n, a in enumerate(rep["frames"])
                  if a["id_valid"] and a["frame_id"] == 0x14)
        self.assertEqual(at, 5)
        self.assertLess(at, RUNS["run3"]["warmup"] // 8)

    def test_the_window_removes_the_startup_gap(self):
        needs_capture("run3")
        v, n = verdict_from("run3", RUNS["run3"]["warmup"])
        self.assertEqual(v, "OBSERVED_CONTIGUOUS")
        self.assertEqual(n, RUNS["run3"]["retained"])

    def test_no_window_of_any_size_rescues_a_faulty_producer(self):
        """run 1 latched STATUS.FAULT. The window is structural and never reads
        STATUS, so it cannot clear one -- and must not appear to."""
        needs_capture("run1")
        for n in (2, 8, 64, 512):
            drop = replay("run1", n)["warmup_frames"]
            self.assertEqual(verdict_from("run1", drop)[0],
                             "STIMULUS_INVALID_FOR_DECISIVE_CLAIM", "N=%d" % n)

    def test_no_window_of_any_size_rescues_a_duplicating_producer(self):
        """run 2 published every source frame twice. That defect is spread over
        the whole capture, so no startup window can hide it."""
        needs_capture("run2")
        for n in (2, 8, 64, 512):
            drop = replay("run2", n)["warmup_frames"]
            self.assertEqual(verdict_from("run2", drop)[0], "OBSERVED_DISCONTINUITY", "N=%d" % n)

    def test_the_run3_verdict_does_not_depend_on_the_choice_of_N(self):
        """N=64 is not fitted. Two frames already clear the transient, and every
        N across a 64-fold range gives the same answer, so the number is a
        time-margin decision on a plateau rather than a tuned one."""
        needs_capture("run3")
        for n in (2, 4, 16, 64, 128):
            drop = replay("run3", n)["warmup_frames"]
            self.assertEqual(verdict_from("run3", drop)[0], "OBSERVED_CONTIGUOUS", "N=%d" % n)
        self.assertGreaterEqual(PRODUCTION_N, 32 * 2)


class TheQualificationCannotReachTheMeasurement(unittest.TestCase):
    """§V5.44.18, the STATIC guard.

    Two layers, because the code has two shapes. The state machine is its own
    translation unit, so the linker can be made to prove it: poc_audit's
    `object_may_only_reference` enumerates its outward edges and rejects every
    other one, so a decoder written next year is a finding without anyone
    remembering to forbid it. The predicate is a static function in a header and
    is inlined into its caller, so no object boundary contains it -- there the
    guard has to read the source, which is what this class does.

    Comments are stripped first. The predicate's own comment names FRAME_ID and
    STATUS in order to say it must not read them, and a check that could not
    tell that apart from reading them would be worthless."""

    HDR = os.path.join(ROOT, "src", "gbp", "gbp_vwitness_drive.h")

    # Every identifier the two predicate functions are allowed to name. This is
    # the assembler's structural vocabulary plus C itself -- no more.
    ALLOWED = {
        "static", "int", "const", "struct", "return", "if", "uint16_t",
        "gbp_vstate", "gbp_vstate_step", "st", "step", "fr",
        "gbp_vstate_frame", "gbp_vstate_frame_at",
        "gbp_vwitness_frame_qualifies", "gbp_vwitness_frame_shape_qualifies",
        "frame_closed", "resync", "frame_complete", "resync_pending",
        "frame_index", "completeness", "blocks", "flags",
        "GBP_VSTATE_FRAME_COMPLETE_40", "GBP_VWITNESS_BLOCKS",
        "GBP_VSTATE_F_ANOMALY", "GBP_VSTATE_F_DISAGREEMENT",
        "GBP_VSTATE_F_OVERLONG", "GBP_VSTATE_F_RESYNC",
    }

    # Naming any of these is the failure the round exists to prevent. The check
    # runs per IDENTIFIER, not per substring, because the two vocabularies
    # collide on one word: the OGBPIDX1 wire format has a SYNC byte (0xB2) that
    # the predicate may never read, and the assembler has a `resync` latch that
    # is precisely what the predicate is supposed to read. A substring test
    # cannot tell GBP_VSTATE_F_RESYNC from a stimulus SYNC, so the carve-out is
    # named rather than left to luck.
    FORBIDDEN = ("frame_id", "status", "sync", "crc", "color", "colour",
                 "vsig", "sig", "signature", "pixel", "barpos", "payload",
                 "strip", "expected", "baseline")
    SYNC_CARVE_OUT = {"resync", "resync_pending", "GBP_VSTATE_F_RESYNC"}

    @staticmethod
    def strip_comments(src):
        src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
        return re.sub(r"//[^\n]*", " ", src)

    def bodies(self):
        src = self.strip_comments(open(self.HDR).read())
        out = {}
        for name in ("gbp_vwitness_frame_shape_qualifies", "gbp_vwitness_frame_qualifies"):
            i = src.index(name + "(")
            j = src.index("{", i)
            depth, k = 0, j
            while True:
                if src[k] == "{":
                    depth += 1
                elif src[k] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            out[name] = src[i:k + 1]
        return out

    def test_both_predicate_functions_are_found(self):
        b = self.bodies()
        self.assertEqual(len(b), 2)
        for name, body in b.items():
            self.assertIn("return", body, name)

    def test_the_predicate_names_only_structural_vocabulary(self):
        for name, body in self.bodies().items():
            used = set(re.findall(r"[A-Za-z_]\w*", body))
            self.assertEqual(used - self.ALLOWED, set(),
                             "%s names something outside the structural vocabulary" % name)

    def offending(self, body):
        out = []
        for ident in sorted(set(re.findall(r"[A-Za-z_]\w*", body))):
            if ident in self.SYNC_CARVE_OUT:
                continue
            low = ident.lower()
            out += [(ident, bad) for bad in self.FORBIDDEN if bad in low]
        return out

    def test_the_predicate_names_nothing_from_the_stimulus(self):
        for name, body in self.bodies().items():
            self.assertEqual(self.offending(body), [], name)

    def test_the_carve_out_is_only_the_assemblers_latch(self):
        """The exemption must not become a hiding place: everything in it is a
        term of the assembler's state, never of the wire format."""
        for ident in self.SYNC_CARVE_OUT:
            self.assertIn("resync", ident.lower())
            self.assertIn(ident, self.ALLOWED | {"resync_pending", "resync"})

    def test_the_guard_would_notice_if_the_predicate_started_reading_content(self):
        """A guard nobody has seen fail is a guard nobody has tested."""
        for tampered in (
                "static int f(void) { return gbp_istim_frame_id(w) & 1; }",
                "static int f(void) { return status_fault(w) == 0; }",
                "static int f(void) { return sync_byte(w) == 0xB2; }",
                "static int f(void) { return crc8_ok(w); }",
                "static int f(void) { return expected_barpos(w) == b; }"):
            used = set(re.findall(r"[A-Za-z_]\w*", tampered))
            self.assertNotEqual(used - self.ALLOWED, set(), tampered)
            self.assertNotEqual(self.offending(tampered), [], tampered)

    def test_the_predicate_does_not_touch_the_frame_signatures(self):
        """THE SHARP EDGE, found by mutation M11.

        `struct gbp_vstate_frame` carries `sig[40]` -- forty signatures computed
        from block CONTENT -- and the predicate already holds an `fr` pointer.
        So `if (fr->sig[0] == 0u) return 0;` compiles, links, and passes every
        behavioural test in the suite while making the window depend on what the
        cartridge drew. Nothing in the type system stops it. This does."""
        for name, body in self.bodies().items():
            self.assertNotIn("sig", body, "%s reaches the content signatures" % name)
        mutant = "if (fr->sig[0] == 0u) return 0;"
        self.assertNotEqual(self.offending(mutant), [], "the guard would miss M11")
        self.assertIn("sig", {i for i in re.findall(r"[A-Za-z_]\w*", mutant)} - self.ALLOWED)

    def test_the_state_machine_reads_no_frame_content_either(self):
        """gbp_vwitness.c holds the streak, the arming and the one-way latch. It
        copies 54 words per staged block and is otherwise blind; it must never
        look at what it copied."""
        src = self.strip_comments(open(os.path.join(ROOT, "src", "gbp", "gbp_vwitness.c")).read())
        m = re.search(r"void gbp_vwitness_note_frame.*?\n}\n", src, re.S)
        self.assertIsNotNone(m)
        low = m.group(0).lower()
        for bad in ("frame_id", "status", "sync", "crc", "color", "staged", "scratch", "store"):
            self.assertNotIn(bad, low, "note_frame touches %r" % bad)

    def test_the_audit_profile_pins_the_state_machine_surface(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import poc_audit
        allow = poc_audit.PROFILES["stream"].get("object_may_only_reference", {})
        self.assertIn("gbp_vwitness.o", allow)
        self.assertEqual(set(allow["gbp_vwitness.o"]), {"memset", "__udivdi3"},
                         "the qualification state machine grew an outward edge")


if __name__ == "__main__":
    unittest.main()
