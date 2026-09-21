"""
tests/host/test_run12_prereg.py — RUN 12 pre-registration (HARDWARE_TESTS
§V6.19, GitHub Issue #8): GBP-VIDEO-007 / GBP-VIDEO-008 frozen BEFORE hardware.

Pinned here: the identities are copied exactly from the frozen §V6.18.2 record
and from the build metadata of the artifacts on disk; the five raw names are
reserved exactly once in §V6.19 and again in the handoff; the gates are
prospective (no result, no evidence ID, no run recorded as executed); the two
verdicts stay independent; the operator's display chain is recorded as topology
and not as a pixel claim; the future Morph 2K topologies are outside RUN 12;
and nothing about the runtime, the stimulus or the analyzers is touched by the
pre-registration. Nothing here runs a program or reads a raw physical file.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
DEVLOG = os.path.join(ROOT, "docs", "research", "DEVLOG.md")
STREAM_MAKE = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "Makefile")
COORD_MAKE = os.path.join(ROOT, "stimulus", "agb-coord", "Makefile")

DOL_SHA = "5391c3fe962dc4b2f4e493f3846ac7407ded064c58f5d4bb583a51e5a725dd79"
CANON_SHA = "90343b64eda9602c173364171637cd1068f265c385464361b40ec073b11f0a1f"
DELIV_SHA = "a769cc11afcb93cfc1cf89bf9bb59554533662c051e25b475f3943e7bdbb994f"
FUNCTIONAL = "7d7a6d8acf4e3985034f9ad4f5041fec751181d0"
NAMES = [
    "captures/local/GBP-VIDEO-004_stream-0013-run12.log",
    "captures/local/GBP-VIDEO-004_stream-0013-run12-idxcap.bin",
    "captures/local/GBP-VIDEO-004_stream-0013-run12-disp.bin",
    "captures/local/GBP-VIDEO-004_stream-0013-run12-full.bin",
    "captures/local/GBP-VIDEO-004_stream-0013-run12-vi.bin",
]
_C = {}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def flat(s):
    return re.sub(r"\s+", " ", s)


def plain(s):
    """One line, no code or bold markup: the pins are about the words."""
    return flat(s).replace("`", "").replace("**", "")


def prereg():
    """§V6.19 only: from its heading up to the RUN 12 result (§V6.20), which is
    a separate part written AFTER the run and pinned by test_run12."""
    if "p" not in _C:
        t = read(HW)
        i = t.index("### V6.19 ")
        j = t.find("### V6.20 ", i)
        _C["p"] = t[i:] if j < 0 else t[i:j]
    return _C["p"]


def prereg_body():
    """The pre-registration without its heading line (the heading carries the
    run's status, which changed when the run was executed and ingested)."""
    return "\n".join(prereg().splitlines()[1:])


def part(n):
    t = prereg()
    i = t.index("#### V6.19.%d " % n)
    j = t.find("#### V6.19.%d " % (n + 1), i)
    return t[i:] if j < 0 else t[i:j]


class TheSectionExists(unittest.TestCase):
    def test_twelve_parts_in_order_and_the_heading_says_not_run(self):
        t = prereg()
        pos = [t.index("#### V6.19.%d " % n) for n in range(1, 13)]
        self.assertEqual(pos, sorted(pos))
        head = t.splitlines()[0]
        self.assertIn("RUN 12", head)
        self.assertIn("PRE-REGISTERED 2026-09-20 (GitHub Issue #8)", head)
        # Issue #10: the heading now carries the outcome; the body below it stays the contract as written
        self.assertIn("EXECUTED 2026-09-20 (Hardware Issue #9)", head)
        self.assertIn("GBP-VIDEO-007 INCONCLUSIVE", head)
        self.assertIn("GBP-VIDEO-008 INCONCLUSIVE", head)
        self.assertIn("\u00a7V6.20", head)

    def test_the_result_follows_it_as_v6_20_then_the_repair_note_and_nothing_else(self):
        t = read(HW)
        self.assertEqual(t.count("### V6.19 "), 1)
        self.assertEqual(t.count("### V6.20 "), 1)
        self.assertEqual(t.count("### V6.21 "), 1)          # Issue #11: GBP-VID-035 repaired, a post-run note
        self.assertEqual(t.count("### V6.22 "), 1)          # Issue #12: GBP-VID-034 root cause, research after the run
        self.assertEqual(t.count("### V6.23 "), 1)          # Issue #13: coord-0002, the timing-safe implementation, not run
        self.assertEqual(t.count("### V6.24 "), 1)          # Issue #14: RUN 13 pre-registered with coord-0002, not run
        self.assertLess(t.index("### V6.19 "), t.index("### V6.20 "))
        self.assertLess(t.index("### V6.20 "), t.index("### V6.21 "))
        self.assertLess(t.index("### V6.21 "), t.index("### V6.22 "))
        self.assertLess(t.index("### V6.22 "), t.index("### V6.23 "))
        self.assertLess(t.index("### V6.23 "), t.index("### V6.24 "))
        self.assertNotIn("### V6.25 ", t)
        self.assertNotRegex(t, r"\n## V7 ")


class IdentitiesAreCopiedExactly(unittest.TestCase):
    def test_dol_size_hash_and_commit(self):
        p = part(2)
        self.assertIn(DOL_SHA, p)
        self.assertIn("506 496 B", p)
        self.assertIn(FUNCTIONAL, p)
        self.assertIn("OPENGBP-IDENT gbp-video-stream-probe stream-0013 7d7a6d8", p)
        self.assertIn("TEST_ID GBP-VIDEO-004", p)
        self.assertIn("build/swiss/12-stream/boot.dol", p)
        self.assertIn("byte-identical", p)

    def test_stimulus_hashes_sizes_and_route(self):
        p = part(2)
        self.assertIn(CANON_SHA, p)
        self.assertIn(DELIV_SHA, p)
        self.assertEqual(p.count("3 496 B"), 2)
        self.assertIn("build/stimulus/agb-coord/agb-coord.gba", p)
        self.assertIn("build/physical/agb-coord-cart.gba", p)
        self.assertIn("NOR / Mode B", p)
        self.assertIn("IS re-flashed", p)

    def test_the_identities_match_the_frozen_implementation_record(self):
        """§V6.18.2 froze them; §V6.19.2 must repeat them, never restate them."""
        t = read(HW)
        impl = t[t.index("### V6.18 "):t.index("### V6.19 ")]
        for ident in (DOL_SHA, CANON_SHA, DELIV_SHA, "506 496 B", "3 496 B"):
            self.assertIn(ident, impl)
            self.assertIn(ident, part(2))

    def test_the_build_ids_are_the_ones_the_tree_declares(self):
        self.assertIsNotNone(re.search(r"^BUILD_ID\s*:=\s*stream-0013$", read(STREAM_MAKE), re.M),
                             "stream-0013 must still be the declared build")
        self.assertIsNotNone(re.search(r"^STIM_ID\s*:=\s*coord-0001$", read(COORD_MAKE), re.M))

    def test_the_built_artifacts_if_present_carry_the_pre_registered_identity(self):
        info = os.path.join(ROOT, "build", "poc", "gbp-video-stream-probe", "build-info.txt")
        if not os.path.exists(info):
            self.skipTest("run `make build` to produce the build metadata")
        t = read(info)
        self.assertIn("build_id=stream-0013", t)
        if "sha256_dol=" + DOL_SHA in t:
            self.assertIn("commit=7d7a6d8\n", t)
        else:
            # a rebuild at another commit is a DIFFERENT artifact; it must never claim the hash
            self.assertNotIn("commit=7d7a6d8\n", t)

    def test_it_says_verified_on_disk_not_rebuilt_and_do_not_run_on_mismatch(self):
        p = part(2)
        self.assertIn("verified on disk", p.lower())
        self.assertIn("not rebuilt", p.lower())
        self.assertIn("DO NOT RUN", p)
        self.assertIn("No replacement artifact", p)
        self.assertIn("EMPTY", p)                      # git diff over the runtime since the functional commit


class NamesAreReservedExactlyOnce(unittest.TestCase):
    def test_the_five_names_appear_exactly_once_in_the_pre_registration(self):
        p = prereg()
        for n in NAMES:
            self.assertEqual(p.count(n), 1, n)
        self.assertIn("TAKEN even if the run aborts", plain(p))
        self.assertIn("cp --update=none", p)
        self.assertIn("never overwrite runs 1", plain(p))

    def test_the_names_are_reserved_nowhere_else_in_hardware_tests(self):
        t = read(HW)
        for n in NAMES:
            self.assertEqual(t.count(n), 1, n)
        self.assertEqual(len(re.findall(r"captures/local/\S*run12\S*", t)), 5)

    def test_the_handoff_names_the_same_five_files_once_and_they_are_taken(self):
        h = read(HANDOFF)
        for n in NAMES:
            self.assertEqual(h.count(n), 1, n)
        self.assertIn("RUN 12 was executed and ingested", plain(h))
        self.assertIn("its five names are TAKEN", plain(h))

    def test_the_photograph_is_optional_and_not_one_of_the_five(self):
        p = part(4)
        self.assertIn("never required for PASS", p)
        self.assertIn("never one of the five names", p)
        self.assertIn("frame-accurate", p)


class GatesAreProspective(unittest.TestCase):
    def test_no_result_no_evidence_id_no_executed_run(self):
        """The contract body was written before the run and must still read that way;
        the result lives in §V6.20 and cites the evidence ids there."""
        p = prereg_body()
        self.assertNotRegex(p, r"GBP-HW-\d{3}")
        self.assertNotRegex(p, r"GBP-VID-03[4-9]|GBP-VID-0[4-9]\d")
        self.assertNotIn("RESULT", p)
        self.assertNotRegex(p, r"EXECUTED 2026")
        self.assertNotRegex(p, r"ingested 2026|ingested on")
        self.assertIn("Nothing here is evidence", p)
        self.assertIn("no evidence ID is allocated", p)
        self.assertIn("No new physical evidence ID exists", part(12))

    def test_the_comparison_table_has_no_run_12_value_pre_filled(self):
        p = part(11)
        rows = [l for l in p.splitlines() if re.match(r"^[A-Za-z].*\s{2,}\S.*\s{2,}--", l)]
        self.assertGreaterEqual(len(rows), 16)
        for l in rows:
            self.assertRegex(l, r"--(\s+\(.*\))?\s*$", l)   # the RUN 12 column is "--", optionally annotated
        self.assertNotIn("GBP-VIDEO-008 verdict                   n/a                               PASS", p)

    def test_the_inherited_gates_are_stated_and_none_is_result_shaped(self):
        p = flat(part(7))
        for phrase in ("dropped=0", "truncated=0", "5000-ms not-before", "64 consecutive structural closes",
                       "target = 2048 retained records", "OBSERVED_CONTIGUOUS", "intact = 2048",
                       "INVALID_CANONICAL_STRIP = 0", "STATUS.FAULT = 0", "NOT gated: a particular FRAME_ID start value",
                       "first real hand-off < 400 ms", "zero interior source -> display drops", "zero reorder",
                       "max defer depth <= 1", "p99 <= 1.0 ms, max <= 2.5 ms", "OGBPFULL1 v1, OGBPVI1 v1",
                       "never repaired or trimmed", "equality is not demanded"):
            self.assertIn(phrase, p, phrase)

    def test_no_frame_id_start_and_no_appearance_k_is_assumed(self):
        self.assertIn("NOT gated: a particular FRAME_ID start value", flat(part(7)))
        self.assertIn("NOT assumed prospectively", flat(part(9)))


class TheTwoVerdictsAreIndependent(unittest.TestCase):
    def test_each_experiment_has_its_own_three_outcomes(self):
        for n in (8, 9):
            p = part(n)
            self.assertEqual(p.count("PASS          "), 1, n)
            self.assertEqual(p.count("FAIL          "), 1, n)
            self.assertEqual(p.count("INCONCLUSIVE  "), 1, n)

    def test_they_say_so(self):
        p = flat(prereg())
        self.assertIn("ONE physical session producing TWO independent verdicts", p)
        self.assertIn("may not promote, demote or excuse the other", p)
        self.assertIn("Neither verdict consults the other's evidence", p)
        self.assertIn("PASS for one experiment and INCONCLUSIVE or FAIL for the other", p)

    def test_008_is_the_content_blind_rule_and_the_oracle_is_never_retuned(self):
        p = plain(part(8))
        self.assertIn("sample frame_index = origin + 256*i, i = 0..7", p)
        self.assertIn("mechanically the first retained witness frame_index", p)
        self.assertIn("do not retune the oracle after seeing a failure", p)
        self.assertIn("38 400 consumed words", p)
        self.assertIn("icoord.expected_video(frame_id, x, y)", p)
        self.assertIn("(oracle | 0x8000)", p)
        self.assertIn("U-GBP-029", p)
        self.assertIn("U-GBP-034", p)
        self.assertIn("CLAIM-A for the sampled frames; CLAIM-B", p)

    def test_007_binds_to_the_appearance_set_not_a_frame(self):
        p = plain(part(9))
        self.assertIn("R_k = [k*480, k*480 + 40)", p)
        self.assertIn("digit = k mod 10", p)
        self.assertIn("PASS does NOT bind the observation to one exact frame", p)
        self.assertIn("never ingested as machine evidence", p)
        self.assertIn("never turns this into a stronger per-frame claim", p)
        self.assertIn("CLAIM-D", p)


class TopologyIsRecordedNotClaimed(unittest.TestCase):
    def test_the_declared_chain_is_present_with_the_1080p_caveat(self):
        p = part(3)
        for item in ("analog composite video / RCA", "RCA-to-HDMI converter", "1080p", "HYDIS HV150UX2",
                     "M.NT68676.2A", "iMac G3", "BBA                PRESENT", "Ethernet           DISCONNECTED",
                     "same GameCube as RUN 10 / RUN 11"):
            self.assertIn(item, p, item)
        self.assertIn("CONVERTER's output, not a claim about the native GameCube signal", flat(p))
        self.assertIn("TOPOLOGY DECLARATION only", p)

    def test_the_chain_is_denied_every_fidelity_claim(self):
        p = flat(part(3))
        for item in ("physical pixel-perfect output", "native 1080p output by the GameCube",
                     "correctness of the converter's scaling", "display latency", "pixel equality"):
            self.assertIn(item, p, item)
        n = flat(part(10))
        for item in ("per-frame physical scanout accounting", "physical display pixel equality", "tearing absence",
                     "pixel-perfect output", "converter's scaling", "K = 8 population", "Link Port", "Phase 11",
                     "GBP-VID-032"):
            self.assertIn(item, n, item)

    def test_morph_2k_is_explicitly_outside_run_12(self):
        p = flat(part(3))
        self.assertIn("explicitly OUTSIDE RUN 12", p)
        self.assertIn("S-Video", p)
        self.assertIn("Bitfunx composite cable", p)
        self.assertIn("Morph 2K", p)
        self.assertIn("Samsung Q80T", p)
        self.assertIn("must not be mixed with RUN 12, nor with each other", p)
        self.assertIn("nothing about them is pre-registered here", p)

    def test_the_handoff_carries_the_same_boundaries(self):
        h = read(HANDOFF)
        self.assertIn("HYDIS HV150UX2", h)
        self.assertIn("Morph 2K", h)
        self.assertIn("not part of RUN 12", h)
        # Issue #10: the run happened; the handoff must say what it did NOT establish
        self.assertIn("That RUN 12 established scanout or fidelity.", h)
        self.assertRegex(h, r"GBP-VIDEO-007 INCONCLUSIVE[^\n]*GBP-VIDEO-008\s+INCONCLUSIVE|GBP-VIDEO-007\s+INCONCLUSIVE[^\n]*GBP-VIDEO-008 INCONCLUSIVE")


class TheProcedureAndTheIdentityGate(unittest.TestCase):
    def test_fourteen_literal_steps_and_no_frame_counting(self):
        p = part(6)
        for n in range(1, 15):
            self.assertIsNotNone(re.search(r"^\s*%d  " % n, p, re.M), "step %d" % n)
        self.assertIn("Do not infer a frame number", p)
        self.assertIn("do not stop it early", p)
        self.assertIn("BEFORE copying", p)
        self.assertIn("count frames by eye", p)

    def test_the_identity_gate_names_the_exact_triplet_and_do_not_run(self):
        p = part(5)
        self.assertIn("gbp-video-stream-probe / stream-0013 / 7d7a6d8", p)
        self.assertIn("no -dirty", p)
        self.assertIn("3 496 B", p)
        self.assertIn("a769cc11...994f", p)
        self.assertIn("If ANY identity differs: DO NOT RUN", p)
        self.assertIn("double check", p)


class NothingElseMoved(unittest.TestCase):
    def test_the_devlog_records_the_checkpoint_as_documentation_only(self):
        d = read(DEVLOG)
        i = d.rindex("## 2026-09-20 — Issue #8")
        e = d[i:]
        self.assertIn("RUN 12 pre-registered", e)
        self.assertIn("nothing run", e)
        self.assertIn("No hardware execution", e)

    def test_the_pre_registration_touches_no_runtime_stimulus_or_analyzer(self):
        """The section says it and the part-12 list says it; the tree keeps its frozen ids."""
        p = part(12)
        self.assertIn("runtime, stimulus, analyzer or frozen-format", p)
        self.assertIn("none were made", p)
        self.assertIn("Hardware Issue", p)


if __name__ == "__main__":
    unittest.main()
