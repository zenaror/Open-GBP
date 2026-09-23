"""
tests/host/test_run13_prereg.py — RUN 13 pre-registration (HARDWARE_TESTS
§V6.24, GitHub Issue #14): GBP-VIDEO-007 / GBP-VIDEO-008 with coord-0002 on
the unchanged stream-0013, frozen BEFORE hardware.

Pinned: the identities are the frozen ones (the RUN 12 DOL, coord-0002's
canonical and delivery, the corrected vvi.py); the five run13 names are
reserved exactly once in §V6.24 and once in the handoff and nowhere else; the
gates are prospective (no result, no evidence ID, no executed date, an
unfilled RUN 13 column); the source gate RUN 12 failed is named as the first
admissibility gate; the two verdicts stay independent; SUPERSEDED stays
instrumentation semantics; the display chain is topology, Morph 2K is outside;
fifteen literal steps; and nothing in the runtime, the stimuli, the analyzers,
the formats or the fixtures moved. Nothing here runs a program.
"""
import hashlib
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
DEVLOG = os.path.join(ROOT, "docs", "research", "DEVLOG.md")
FX = os.path.join(ROOT, "captures", "fixtures")

DOL_SHA = "5391c3fe962dc4b2f4e493f3846ac7407ded064c58f5d4bb583a51e5a725dd79"
FUNCTIONAL = "7d7a6d8acf4e3985034f9ad4f5041fec751181d0"
CANON2_SHA = "319dacb759dd2f78b420691a896387b727accf5d9483f152a6a096865c95093f"
DELIV2_SHA = "276ad987c4cd0cefc7d7c532b86a7f5c336cf6603a32509f80f17aac9a56f700"
CANON1_SHA = "90343b64eda9602c173364171637cd1068f265c385464361b40ec073b11f0a1f"
NAMES = [
    "captures/local/GBP-VIDEO-004_stream-0013-run13.log",
    "captures/local/GBP-VIDEO-004_stream-0013-run13-idxcap.bin",
    "captures/local/GBP-VIDEO-004_stream-0013-run13-disp.bin",
    "captures/local/GBP-VIDEO-004_stream-0013-run13-full.bin",
    "captures/local/GBP-VIDEO-004_stream-0013-run13-vi.bin",
]
_C = {}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def flat(s):
    return re.sub(r"\s+", " ", s)


def plain(s):
    return flat(s).replace("`", "").replace("**", "")


def prereg():
    if "p" not in _C:
        t = read(HW)
        i = t.index("### V6.24 ")
        j = t.find("### V6.25 ", i)
        _C["p"] = t[i:] if j < 0 else t[i:j]
    return _C["p"]


def body():
    return "\n".join(prereg().splitlines()[1:])


def part(n):
    t = prereg()
    i = t.index("#### V6.24.%d " % n)
    j = t.find("#### V6.24.%d " % (n + 1), i)
    return t[i:] if j < 0 else t[i:j]


class TheSectionExists(unittest.TestCase):
    def test_twelve_parts_in_order_and_the_heading_carries_the_status(self):
        t = prereg()
        pos = [t.index("#### V6.24.%d " % n) for n in range(1, 13)]
        self.assertEqual(pos, sorted(pos))
        head = t.splitlines()[0]
        for tok in ("RUN 13", "coord-0002", "PRE-REGISTERED 2026-09-20 (GitHub Issue #14)", "EXECUTED 2026-09-21 (Hardware Issue #15)",
                    "INGESTED in §V6.25 (Issue #16)", "kept verbatim as provenance"):
            self.assertIn(tok, head, tok)

    def test_it_follows_v6_23_and_the_result_follows_it_as_v6_25(self):
        t = read(HW)
        self.assertEqual(t.count("### V6.24 "), 1)
        self.assertLess(t.index("### V6.23 "), t.index("### V6.24 "))
        self.assertEqual(t.count("### V6.25 "), 1)
        self.assertLess(t.index("### V6.24 "), t.index("### V6.25 "))
        self.assertNotIn("### V6.26 ", t)
        v6 = [l for l in t.splitlines() if l.startswith("## V6 ")]
        self.assertEqual(len(v6), 1)
        self.assertIn("RUN 13 PRE-REGISTERED (Issue #14, §V6.24), EXECUTED (Issue #15), INGESTED (Issue #16, §V6.25): GBP-VIDEO-007 = PASS · GBP-VIDEO-008 = PASS", v6[0])


class IdentitiesAreTheFrozenOnes(unittest.TestCase):
    def test_the_dol_is_run_12s_not_rebuilt(self):
        p = part(2)
        self.assertIn(DOL_SHA, p)
        self.assertIn("506 496 B", p)
        self.assertIn(FUNCTIONAL, p)
        self.assertIn("OPENGBP-IDENT gbp-video-stream-probe stream-0013 7d7a6d8", p)
        self.assertIn("TEST_ID GBP-VIDEO-004", p)
        self.assertIn("build/swiss/12-stream/boot.dol", p)
        self.assertIn("NOT rebuilt, no stream-0014", part(1))
        self.assertIn("13-stream", p)                                   # the optional copy: decided, and the decision recorded
        self.assertIn("deliberately NOT created", p)

    def test_the_stimulus_is_coord_0002_verified_not_re_derived(self):
        p = part(2)
        self.assertIn(CANON2_SHA, p)
        self.assertIn(DELIV2_SHA, p)
        self.assertEqual(p.count("3 620 B"), 2)
        self.assertIn("build/stimulus/agb-coord2/agb-coord2.gba", p)
        self.assertIn("build/physical/agb-coord2-cart.gba", p)
        self.assertIn("captures/fixtures/stimulus-coord-0002-canonical.gba", p)
        self.assertIn("payload from 0x0C0 byte-identical", p)
        self.assertIn("0x004..0x09F", p)
        self.assertIn("NOR / Mode B", p)
        self.assertIn("NOT re-derived", p)
        self.assertIn(CANON1_SHA[:8], p)                                  # coord-0001 named as the thing NOT to substitute
        self.assertIn("not to be substituted", p)

    def test_the_canonical_fixture_carries_the_same_identity(self):
        with open(os.path.join(FX, "stimulus-coord-0002-canonical.gba"), "rb") as f:
            data = f.read()
        self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (3620, CANON2_SHA))

    def test_the_tools_named_are_the_current_accepted_ones(self):
        p = plain(part(2))
        self.assertIn("tools/vvi.py the CORRECTED implementation of the GBP-VID-035 repair (commit 0ee8aac, §V6.21)", p)
        self.assertIn("tools/vindex.py frozen semantics, unchanged", p)
        self.assertIn("tools/vfull.py frozen RUN 12 semantics, unchanged", p)
        self.assertIn("tools/icoord.py the OGBPCOORD1 oracle, unchanged", p)
        self.assertIn("frozen-at-run vvi result stays history", p)

    def test_do_not_run_on_mismatch_and_nothing_rebuilt_to_pass(self):
        p = part(2)
        self.assertIn("DO NOT RUN", p)
        self.assertIn("No artifact is rebuilt or", p)


class NamesAreReservedExactlyOnce(unittest.TestCase):
    def test_the_five_names_appear_exactly_once_in_the_pre_registration(self):
        p = prereg()
        for n in NAMES:
            self.assertEqual(p.count(n), 1, n)
        self.assertIn("TAKEN even if the run aborts", plain(p))
        self.assertIn("cp --update=none", p)
        self.assertIn("never overwrite runs 1", plain(p))
        self.assertIn("verify none of them exists", plain(p))

    def test_the_names_are_reserved_nowhere_else_in_hardware_tests(self):
        t = read(HW)
        for n in NAMES:
            self.assertEqual(t.count(n), 1, n)
        self.assertEqual(len(re.findall(r"captures/local/\S*run13\S*", t)), 5)
        # RUN 14 / RUN 15 (Issue #20), RUN 16 (Issue #23), RUN 17 / RUN 18 (Issue #28, §V7.3) and RUN 19 / RUN 20 (Issue #34, §V7.5) are reserved;
        # nothing beyond them
        self.assertEqual(len(re.findall(r"captures/local/\S*run(?:3[5-9]|[4-9]\d)\S*", t)), 0)   # run21 / run22: Issue #41, §V7.6; run30: Issue #58, §V8 (GBP-AUDIO-001, reserved and not on disk); run31: Issue #64, §V9 (GBP-AUDIO-002, reserved and not on disk); run32: nothing beyond RUN 31 exists (Issue #67); run33: Issue #75, §V13 (GBP-AUDIO-004, reserved and not on disk); run34: §V14 (GBP-AUDIO-003 repeated, reserved and not on disk)

    def test_the_handoff_reserves_the_same_five_names_once_and_the_run_12_names_stay(self):
        h = read(HANDOFF)
        for n in NAMES:
            self.assertEqual(h.count(n), 1, n)
        for n in NAMES:
            self.assertEqual(h.count(n.replace("run13", "run12")), 1, n)
        self.assertIn("RUN 13 was executed and ingested", plain(h))

    def test_the_photograph_is_optional_and_not_one_of_the_five(self):
        p = part(4)
        self.assertIn("never required for PASS", p)
        self.assertIn("never one of the five names", p)
        self.assertIn("not frame-accurate evidence", p)

    def test_the_ingestion_archived_under_exactly_the_reserved_names(self):
        import json
        with open(os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-21-idxcap-run13-struct.json")) as f:
            raw = json.load(f)["raw"]
        self.assertEqual([raw[k]["archived_as"] for k in ("log", "idxcap", "disp", "full", "vi")], NAMES)


class GatesAreProspective(unittest.TestCase):
    def test_no_result_no_evidence_id_no_executed_run(self):
        p = body()
        self.assertNotRegex(p, r"GBP-HW-\d{3}")
        self.assertNotRegex(p, r"GBP-VID-03[6-9]|GBP-VID-0[4-9]\d")
        self.assertNotIn("RESULT", p)
        self.assertNotRegex(p, r"EXECUTED 2026")
        self.assertNotRegex(p, r"ingested 2026|ingested on")
        self.assertIn("Nothing here is evidence", p)
        self.assertIn("no evidence ID is allocated", p)
        self.assertIn("PRE-REGISTERED / NOT RUN", part(12))

    def test_the_comparison_table_has_no_run_13_value_pre_filled(self):
        p = part(11)
        rows = [l for l in p.splitlines() if re.match(r"^[A-Za-z].*\s{2,}\S.*\s{2,}--", l)]
        self.assertGreaterEqual(len(rows), 18)
        for l in rows:
            self.assertRegex(l, r"--(\s+\(.*\))?\s*$", l)

    def test_the_source_gate_run_12_failed_comes_first_and_is_unchanged(self):
        p = flat(part(7))
        for phrase in ("dropped=0", "truncated=0", "not-before 5000 ms", "64 consecutive structural closes", "target = 2048 retained records",
                       "OBSERVED_CONTIGUOUS", "intact = 2048", "INVALID_CANONICAL_STRIP = 0", "no mixed block ids", "BLOCK_INDEX correct",
                       "STATUS.FAULT = 0", "NOT gated: a particular first FRAME_ID", "THIS IS THE GATE RUN 12 FAILED",
                       "never repaired, trimmed or filtered", "first real hand-off < 400 ms", "zero interior source -> display drops",
                       "zero reorder", "max defer depth <= 1", "p99 <= 1.0 ms, max <= 2.5 ms", "OGBPFULL1 v1, OGBPVI1 v1",
                       "no tolerance invented"):
            self.assertIn(phrase, p, phrase)

    def test_no_first_frame_id_and_no_appearance_k_is_assumed(self):
        self.assertIn("NOT gated: a particular first FRAME_ID", flat(part(7)))
        self.assertIn("no first FRAME_ID is assumed", flat(part(9)))


class TheTwoVerdictsAreIndependent(unittest.TestCase):
    def test_each_experiment_has_its_own_three_outcomes(self):
        for n in (8, 9):
            p = part(n)
            self.assertEqual(p.count("PASS          "), 1, n)
            self.assertEqual(p.count("FAIL          "), 1, n)
            self.assertEqual(p.count("INCONCLUSIVE  "), 1, n)

    def test_they_say_so(self):
        p = flat(prereg())
        self.assertIn("ONE physical session, TWO independent verdicts", p)
        self.assertIn("may not promote, demote or excuse the other", p)
        self.assertIn("Neither verdict consults the other's evidence", p)

    def test_008_is_the_content_blind_rule_with_the_unchanged_tools(self):
        p = plain(part(8))
        self.assertIn("sample frame_index = origin + 256*i, i = 0..7", p)
        self.assertIn("mechanically the first retained scientific frame_index", p)
        self.assertIn("do not retune the oracle after seeing data", p)
        self.assertIn("38 400 consumed source words == icoord.expected_video(frame_id, x, y)", p)
        self.assertIn("(oracle | 0x8000)", p)
        self.assertIn("wanted / opened / completed = 8 / 8 / 8", p)
        self.assertIn("U-GBP-029", p)
        self.assertIn("U-GBP-034", p)

    def test_007_uses_the_corrected_vvi_and_keeps_superseded_as_instrumentation(self):
        p = plain(part(9))
        self.assertIn("corrected current tools/vvi.py", p)
        self.assertIn("R_k = [k*480, k*480 + 40)", p)
        self.assertIn("digit = k mod 10", p)
        self.assertIn("SUPERSEDED records remain instrumentation semantics only", p)
        self.assertIn("nothing about physical scanout is inferred from them", p)
        self.assertIn("PASS does NOT bind the observation to one frame", p)
        self.assertIn("never fed into the tool", p)
        self.assertIn("CLAIM-D", p)


class TopologyIsRecordedNotClaimed(unittest.TestCase):
    def test_the_declared_chain_is_held_at_run_12s(self):
        p = part(3)
        for item in ("the same physical GameCube as RUN 12", "the same physical unit as RUN 12", "BBA                PRESENT",
                     "Ethernet           DISCONNECTED", "analog composite video / RCA", "RCA-to-HDMI converter", "1080p",
                     "HYDIS HV150UX2", "M.NT68676.2A", "iMac G3"):
            self.assertIn(item, p, item)
        f = flat(p)
        self.assertIn("CONVERTER's output, not the native GameCube signal", f)
        self.assertIn("TOPOLOGY only", f)
        for item in ("no pixel-perfect output", "no native 1080p", "no converter-scaling correctness", "no display latency", "no physical per-pixel equality"):
            self.assertIn(item, f, item)

    def test_morph_2k_and_q80t_are_outside_run_13(self):
        f = flat(part(3))
        self.assertIn("explicitly OUTSIDE RUN 13", f)
        for item in ("S-Video", "Bitfunx composite cable", "Morph 2K", "Samsung Q80T", "must not be mixed with RUN 13"):
            self.assertIn(item, f, item)
        n = flat(part(10))
        for item in ("Morph 2K behaviour", "Samsung Q80T behaviour", "cheap RCA → HDMI scaling", "K = 8 sampled frames", "Phase 11",
                     "RUN 12 remains historical and INCONCLUSIVE"):
            self.assertIn(item, n, item)

    def test_the_handoff_carries_the_same_boundaries(self):
        h = read(HANDOFF)
        self.assertIn("HYDIS HV150UX2", h)
        self.assertIn("Morph 2K", h)
        self.assertRegex(h, r"RUN 13[^\n]*PRE-REGISTERED|PRE-REGISTERED[^\n]*RUN 13")
        self.assertRegex(h, r"RUN 13[^\n]*EXECUTED|EXECUTED[^\n]*RUN 13")
        self.assertIn("That RUN 13 established more than its two boundaries.", h)


class TheProcedureAndTheIdentityGate(unittest.TestCase):
    def test_fifteen_literal_steps_no_frame_counting_no_stopwatch(self):
        p = part(6)
        for n in range(1, 16):
            self.assertIsNotNone(re.search(r"^\s*%d  " % n, p, re.M), "step %d" % n)
        self.assertIsNone(re.search(r"^\s*16  ", p, re.M))
        for tok in ("No frame counting, no stopwatch", "do not stop it early", "reserved run13 names", "Do not infer an exact frame number"):
            self.assertIn(tok, p, tok)

    def test_the_identity_gate_names_the_exact_triplet_and_do_not_run(self):
        p = part(5)
        self.assertIn("gbp-video-stream-probe / stream-0013 / 7d7a6d8", p)
        self.assertIn("no -dirty", p)
        self.assertIn("3 620 B", p)
        self.assertIn("276ad987...6f700", p)
        self.assertIn("If ANY identity differs: DO NOT RUN", p)
        self.assertIn("double check", p)


class NothingElseMoved(unittest.TestCase):
    def test_the_devlog_records_the_checkpoint_as_pre_registration_only(self):
        d = read(DEVLOG)
        i = d.rindex("## 2026-09-20 — Issue #14")
        j = d.find("\n## 2026", i + 1)
        e = d[i:j if j > 0 else None]
        self.assertIn("RUN 13 pre-registered", e)
        self.assertIn("NOT RUN", e)
        self.assertIn("no hardware, no flash", e)
        self.assertNotRegex(e, r"GBP-HW-\d{3}")

    def test_part_12_says_what_was_not_authorized_and_the_runtime_ids_are_unchanged(self):
        p = part(12)
        self.assertIn("the runtime, coord-0001, coord-0002, the analyzers, the formats, the fixtures, the evidence rows or the gates (none was made)", flat(p))
        self.assertIn("Hardware Issue", p)
        m = read(os.path.join(ROOT, "poc", "gbp-video-stream-probe", "Makefile"))
        # RUN 13 ran the unchanged stream-0013; since Issue #19 (2026-09-21) the tree
        # declares a later member of the series and keeps stream-0013 in its history.
        self.assertIn("stream-0013 is stream-0012 plus the GBP-VIDEO-007/008", m)
        decl = re.search(r"^BUILD_ID\s*:=\s*stream-(\d{4})$", m, re.M)
        self.assertIsNotNone(decl)
        self.assertGreaterEqual(int(decl.group(1)), 13)
        for mk, sid in (("agb-coord", "coord-0001"), ("agb-coord2", "coord-0002")):
            self.assertIsNotNone(re.search(r"^STIM_ID\s*:=\s*%s$" % sid, read(os.path.join(ROOT, "stimulus", mk, "Makefile")), re.M))


if __name__ == "__main__":
    unittest.main()
