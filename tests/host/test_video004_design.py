"""HARDWARE_TESTS.md §V5 — the GBP-VIDEO-004 design / pre-registration.

A design document is only worth what it commits to before the run. These tests
check the commitments that would be easiest to quietly lose: that every section
§24 of the brief required is actually present, that the open decisions are marked
open instead of being given invented numbers, that nothing claims to have been
implemented or run, and that the two rules the colour work paid for — no
full-frame work in the service path, and never synthesise pixels — are stated
rather than assumed.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
ROADMAP = os.path.join(ROOT, "docs", "ROADMAP.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def flat(text):
    """Prose wraps. A documentation test must survive a reflow, so every match
    against prose runs over whitespace-collapsed text."""
    return " ".join(text.split())


def v5():
    """The §V5 block only, so a match somewhere else in a 7800-line file cannot
    satisfy a test about §V5."""
    text = read(HW)
    i = text.index("## V5 — GBP-VIDEO-004")
    return text[i:]


class SectionsExist(unittest.TestCase):
    REQUIRED = [
        "V5.1", "V5.2", "V5.3", "V5.4", "V5.5", "V5.6", "V5.7", "V5.8", "V5.9",
        "V5.10", "V5.11", "V5.12", "V5.13", "V5.14", "V5.15", "V5.16", "V5.17",
        "V5.18", "V5.19", "V5.20", "V5.21", "V5.22", "V5.23", "V5.24", "V5.25",
    ]

    def test_every_numbered_subsection_is_present_and_in_order(self):
        t = v5()
        positions = []
        for s in self.REQUIRED:
            m = re.search(r"^### %s " % re.escape(s), t, re.M)
            self.assertIsNotNone(m, "§%s is missing" % s)
            positions.append(m.start())
        self.assertEqual(positions, sorted(positions), "the subsections are out of order")

    def test_the_topics_the_brief_required_are_each_covered(self):
        t = v5().lower()
        for topic in ("goal", "non-goal", "authority", "dependency matrix",
                      "producer / consumer", "buffering", "colour conversion",
                      "backpressure", "memory budget", "timing-risk register",
                      "phase 7 bridge", "open questions"):
            self.assertIn(topic, flat(t), "the design does not cover %r" % topic)


class ItCommitsNothingItHasNotDone(unittest.TestCase):
    def test_it_says_plainly_that_nothing_is_implemented_or_run(self):
        t = v5()
        head = flat(t[:t.index("### V5.1")])
        self.assertIn("DESIGN ONLY", head)
        self.assertIn("Nothing here is implemented", head)
        self.assertIn("nothing has touched hardware", head)
        self.assertIn("no frozen format changes", head)

    def test_it_claims_no_evidence_id(self):
        """A design may cite evidence; it may not ALLOCATE one. The ceiling is not
        a constant — GBP-VIDEO-004 has since produced GBP-HW-134…137 — so it is
        read from EVIDENCE.md, which is the file that owns the numbering."""
        ev = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
        with open(ev, encoding="utf-8") as f:
            allocated = {int(c) for c in re.findall(r"^### GBP-HW-(\d{3})", f.read(), re.M)}
        self.assertTrue(allocated, "EVIDENCE.md allocates no ids at all")
        cited = set(re.findall(r"GBP-HW-(\d{3})", v5()))
        self.assertTrue(cited, "the design cites no evidence at all")
        self.assertLessEqual(max(int(c) for c in cited), max(allocated),
                             "§V5 cites an evidence id that EVIDENCE.md has not allocated")

    def test_it_does_not_budget_timing_as_a_property(self):
        t = v5()
        self.assertIn("Timing is NOT budgeted here", flat(t))
        self.assertIn("measures", t.split("### V5.22")[1].split("### V5.23")[0])

    def test_the_design_still_describes_the_poc_it_specified(self):
        """§V5.20 names the POC and the two modules. They were written on
        2026-09-18, the round after the design; the names must still match, or
        the design and the code have drifted apart."""
        t = v5().split("### V5.20")[1].split("### V5.21")[0]
        for name in ("poc/gbp-video-stream-probe/", "src/gbp/gbp_vpix",
                     "src/gbp/gbp_vqueue", "stream-0001", "GBP-VIDEO-004"):
            self.assertIn(name, t, "§V5.20 no longer names %r" % name)

    def test_the_specified_files_were_built_where_the_design_said(self):
        for rel in ("src/gbp/gbp_vpix.h", "src/gbp/gbp_vpix.c",
                    "src/gbp/gbp_vqueue.h", "src/gbp/gbp_vqueue.c",
                    "poc/gbp-video-stream-probe/Makefile",
                    "poc/gbp-video-stream-probe/source/main.c"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, rel)),
                            "%s was specified by §V5.20 and does not exist" % rel)


class OpenDecisionsStayOpen(unittest.TestCase):
    """§4 of the brief: no arbitrary thresholds. Where the project has no basis
    for a number, the design must say so instead of inventing one."""

    def test_the_three_open_decisions_are_marked(self):
        t = v5()
        self.assertGreaterEqual(t.count("DESIGN DECISION REQUIRED"), 3)

    def test_duration_is_not_given_an_invented_number(self):
        row = [l for l in v5().splitlines() if l.startswith("| run duration")]
        self.assertEqual(len(row), 1)
        self.assertIn("DDR", row[0])
        self.assertIn("feels long", row[0])

    def test_queue_depth_is_deferred_to_a_measurement(self):
        t = flat(v5().split("### V5.8")[1].split("### V5.9")[0])
        self.assertIn("Queue depth: DESIGN DECISION REQUIRED", t)
        self.assertIn("Nothing in this repository measures conversion cost yet", t)
        self.assertIn("deferred to the first measurement rather than guessed", t)

    def test_open_questions_are_enumerated(self):
        t = v5().split("### V5.25")[1]
        self.assertGreaterEqual(len(re.findall(r"^\d+\. ", t, re.M)), 4)


class TheRulesThePreviousWorkPaidFor(unittest.TestCase):
    def test_the_service_path_exclusion_list_is_explicit(self):
        t = v5().split("### V5.7")[1].split("### V5.8")[0]
        for forbidden in ("GX", "filesystem", "networking", "PAD",
                          "full-frame conversion"):
            self.assertIn(forbidden, t, "the forbidden list lost %r" % forbidden)
        self.assertIn("V3.23", flat(t), "the rule must cite the audit that produced it")

    def test_pixels_are_never_synthesised(self):
        t = v5()
        self.assertIn("Never synthesise pixels", flat(t))
        self.assertIn("HOLD_PREVIOUS_FRAME", t)
        # and the rejected policies are named, not silently dropped
        for policy in ("DROP_FRAME", "PARTIAL_FRAME_WITH_DIAGNOSTIC", "RESYNC_ONLY"):
            self.assertIn(policy, t)

    def test_a_quarantined_frame_may_not_be_displayed(self):
        t = v5()
        self.assertIn("F_MAJORITY_EXTRA", t)
        self.assertIn("never presented", flat(t))

    def test_the_producer_is_never_blocked(self):
        self.assertIn("Never block the producer", flat(v5()))

    def test_looks_smooth_is_refused_as_a_criterion(self):
        t = v5().split("### V5.21")[1].split("### V5.22")[0]
        self.assertIn("is not a criterion", flat(t))


class GroundedInRealArtifacts(unittest.TestCase):
    """The design's factual claims must point at things that exist."""

    def test_the_colour_conversion_rests_on_the_confirmed_mapping(self):
        t = v5().split("### V5.10")[1].split("### V5.11")[0]
        self.assertIn("GBP-HW-131", t)
        self.assertIn("0x8000", t)

    def test_the_toolchain_claims_name_real_headers(self):
        t = v5().split("### V5.15")[1].split("### V5.16")[0]
        for h in ("ogc/gx.h", "ogc/cache.h", "ogc/video.h"):
            self.assertIn(h, t)
        self.assertIn("GX_TF_RGB5A3", t)

    def test_exactly_one_poc_initialises_gx_and_the_design_records_that(self):
        """§V5.4 originally said no POC had ever called GX_Init. Implementing the
        design made that false, which is recorded there with its date rather than
        rewritten. ONE such POC until Issue #39 (2026-09-21): the playable image
        is built from the stream probe and owns the same display path, so there
        are exactly TWO, and no object under src/gbp may reach GX in either."""
        hits = []
        for root, _dirs, files in os.walk(os.path.join(ROOT, "poc")):
            for fn in files:
                if fn.endswith((".c", ".h")) and "GX_Init" in read(os.path.join(root, fn)):
                    hits.append(os.path.relpath(os.path.join(root, fn), ROOT))
        self.assertEqual(sorted(hits), ["poc/gbp-play-session/source/main.c", "poc/gbp-video-stream-probe/source/main.c"], hits)
        self.assertIn("Changed 2026-09-18 by the implementation of this design", flat(v5()))

    def test_the_cadence_arithmetic_is_right(self):
        t = v5()
        self.assertIn("59.727", t)
        self.assertIn("59.94", t)
        beat = 59.94 - 59.727
        self.assertAlmostEqual(1.0 / beat, 4.69, places=1)
        self.assertIn("4.7 seconds", flat(t))
        self.assertAlmostEqual(120 * beat, 25.6, places=1)
        self.assertIn("26 in a 120 s run", flat(t))

    def test_the_frame_sizes_are_exact(self):
        t = v5().split("### V5.22")[1]
        self.assertEqual(40 * 0xF00, 153600)
        self.assertEqual(240 * 160 * 2, 0x12C00)
        for n in ("184 320", "153 600", "76 800", "38 400"):
            self.assertIn(n, t)

    def test_no_commercial_cartridge_is_named(self):
        t = v5().split("### V5.18")[1].split("### V5.19")[0]
        self.assertIn("deliberately does not name a commercial cartridge", flat(t))


class UnknownsAreNotClosedBySideEffect(unittest.TestCase):
    def test_the_three_open_unknowns_are_argued_not_assumed(self):
        t = v5().split("### V5.17")[1].split("### V5.18")[0]
        for u in ("U-GBP-029", "U-GBP-033", "U-GBP-034"):
            self.assertIn(u, t)
        self.assertIn("None of the three blocks it", flat(t))

    def test_they_are_still_open_in_unknowns_md(self):
        unk = read(os.path.join(ROOT, "docs", "research", "UNKNOWNS.md"))
        for u in ("U-GBP-029", "U-GBP-033", "U-GBP-034"):
            m = re.search(r"^#{2,3} %s\b.*$" % u, unk, re.M)
            self.assertIsNotNone(m, "%s is not defined" % u)
            self.assertNotIn("CLOSED", m.group(0),
                             "%s was closed without evidence in this round" % u)


class PointersResolve(unittest.TestCase):
    def test_the_roadmap_points_at_the_design(self):
        t = flat(read(ROADMAP))
        self.assertIn("HARDWARE_TESTS §V5", t)
        self.assertIn("not implemented, not run", t)

    def test_the_roadmap_no_longer_contradicts_itself_about_video_003(self):
        t = flat(read(ROADMAP))
        self.assertNotIn("§V3.0 to §V3.25), NOT PHYSICALLY EXECUTED", t)
        self.assertIn("PHYSICALLY EXECUTED twice on 2026-09-18", t)

    def test_the_delivery_dependency_is_marked_resolved(self):
        t = read(HW)
        self.assertIn("STATUS: RESOLVED (route 1, EZ-Flash Omega DE NOR / Mode B)", t)

    def test_the_handoff_names_the_active_candidate_and_keeps_the_rejected_one(self):
        """Several builds now exist for one Test ID. A reader who skims this file
        must come away knowing which was rejected before hardware, which ran, and
        what its run did and did not establish.

        `NOT PHYSICALLY EXECUTED` was asserted here while stream-0002 was still a
        candidate. It has since RUN — and aborted pre-service — so the assertion
        is now that its physical outcome is recorded, not that it is absent."""
        t = flat(read(HANDOFF))
        self.assertIn("GBP-VIDEO-004", t)
        self.assertIn("HARDWARE_TESTS.md` §V5", t)
        self.assertIn("stream-0002", t)
        self.assertIn("REJECTED before hardware — DO NOT RUN", t)
        self.assertIn("0dc2c50101b5cc6c3906e89f845b89d4d218ccd7ee05ff04764de68b1169d275", t)
        # stream-0002's physical outcome, and that it is never read as a
        # streaming failure (GBP-HW-137). The full wording lives in §V5.29,
        # which owns it permanently; the handoff must keep the verdict and the
        # identity so a reader cannot pick up the wrong DOL.
        self.assertIn("ABORTED PRE-SERVICE", t)
        self.assertIn("store_or_bounds_invalid", t)
        self.assertIn("not a streaming failure", t)
        self.assertIn("76fa1ff797a05aee37d50fe2b2ae1c7c7ffb2d57fb97166a1322a9c54f24831d", t)
        # and the candidate that supersedes it
        self.assertIn("stream-0003", t)
        hw = flat(read(HW))
        self.assertIn("GBP STREAM CAPTURE NOT STARTED", hw)
        self.assertIn('NOT "streaming failed"', hw)

    def test_the_storage_cause_and_its_two_traps_survive(self):
        """The cause is one predicate and the log actively concealed it. Both
        facts have to survive or a later round will re-derive them the expensive
        way. They now live in §V5.29, which owns them permanently; the handoff
        keeps the field name so the next reader recognises it on sight."""
        hw = flat(read(HW))
        self.assertIn("!s->episode_raw", hw)
        self.assertIn("gbp_vstate_probe.c:790", hw)
        # the gate was right: two unguarded dereferences
        self.assertIn("gbp_vstate_probe.c:812", hw)
        self.assertIn("gbp_vstate.c:739", hw)
        # and the two traps
        self.assertIn("static_bytes=6922240", hw)
        self.assertIn("1 798 144", hw)
        # the handoff keeps the field name and the gate
        t = flat(read(HANDOFF))
        self.assertIn("episode_raw_null", t)
        self.assertIn("gbp_vstate_probe.c:790", t)

    def test_the_handoff_keeps_the_corrected_slack_number(self):
        """The 164 us figure was the mean cycle period, not slack. The MEASURED
        window must survive in the handoff, or a later round will reuse the wrong
        one — which is how it got in."""
        t = flat(read(HANDOFF))
        self.assertIn("42.8", t)
        self.assertIn("p25 = 1.9", t)
        self.assertIn("PLAUSIBLE BUT UNMEASURED", t)


if __name__ == "__main__":
    unittest.main()
