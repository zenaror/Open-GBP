"""
tests/host/test_gbmode_read.py -- GitHub Issue #146 (Phase 7's E3): the reader of the first GB-mode session past PREUNMASK can say
NO. tools/gbmode_read.py prints, per pre-registered question, WHICH RIVAL READING a log matches. A reader that agrees with any log is
not an instrument, so this file feeds it (1) synthetic logs built to each rival reading, and (2) the archive's own controls -- the
four GBA/no-cartridge stream-0015 runs that must read "GBA structure" and the four aborted GB boots that must read "refused at
PREUNMASK, policy absent" -- so that it is known to discriminate before it is asked about a run nobody has seen.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gbmode_read as g  # noqa: E402
LOCAL = os.path.join(ROOT, "captures", "local")


def make_log(build="gbmode-0001", commit="abc1234", dropped=0, truncated=0, end_dropped=0, orig=0x92, exp=0x8E,
             raw_votes=(0x8E, 0x8E, 0x8F, 0x8F, 0x8F), pre_ok=1, pre_reason="-", pre_control=0x8F, counters=None, vend=None,
             src=None, witqual=1, witness="2048/2048", restore=(0x92, 0x93, 0x93, 1), tol="CONTROLTOL n=6 first_site=PREUNMASK-0 first_vote=8f exp=8e restore=1 policy=bit0x01_only",
             inp="selftest=1 steps=1 invalid=0 no_base=0 key_changes=0 attempts=7800 completed=7800 failed=0 first=1 change=0 refresh=7799 retry=0 last_word=0000 last_rc=ok",
             extra=""):
    c = dict(unmasks=254700, deliveries=254700, acks=254700, rearms=254700, audio=164791, video=96109, control_ok=1)
    c.update(counters or {})
    v = dict(status="ok_structured_change_observed", cls="ok", reason="-", stop="witness_target_reached", restore="ok",
             teardown="S5_witness_target", pcr=1, errors=0)
    v.update(vend or {})
    s = dict(closed=2404, complete=2378, incomplete=13, quarantined=0, anomaly=13, published=2378)
    s.update(src or {})
    L = ["# OPENGBP-LOG v1", "test_id=GBP-VIDEO-004", "build_id=%s" % build, "commit=%s" % commit, "libogc=x",
         "lines=100 dropped=%d truncated=%d" % (dropped, truncated), "# --- records ---",
         "000000 IDENT test=GBP-VIDEO-004 app=gbp-video-stream-probe build=%s commit=%s libogc=x" % (build, commit),
         "000034 CONTROL semantic orig=%02x exp=%02x method=gbi-majority-vote transform=(v&~10)|0c" % (orig, exp),
         "000036 CTLW tag=EXP addr=01400000 semantic=%02x rc=ok" % exp]
    for i, vote in enumerate(raw_votes):
        L.append("%06d RAW T%d idx=4 addr=01400000 rc=ok ticks=34 polls=9 dspcr=0804 sem_vote=%02x sem_b1f=%02x data=00" % (40 + i, i, vote, vote))
    if pre_ok is not None:
        L.append("000098 PREUNMASK ok=%d reason=%s intsr13=1,1 intmr13=0,0 control=%02x irq=0500/0500 src=0500 odd=0000 bit15=0" % (pre_ok, pre_reason, pre_control))
    if restore:
        L.append("000102 CONTROL restore semantic=%02x rc=ok readback_rc=ok readback_vote=%02x readback_b1f=%02x ok=%d" % restore)
        L.append("000124 RESTORE control_restore_ok=%d irq_stop_write_ok=1" % restore[3])
    if tol:
        L.append("000103 " + tol)
    L.append("000140 COUNTERS unmasks=%(unmasks)d deliveries=%(deliveries)d acks=%(acks)d rearms=%(rearms)d lean=0 verify=4 audio=%(audio)d video=%(video)d/%(video)d isr_w1c=0 main_w1c=0 teardown_w1c=1 overflow=0 uncertain=0 control_ok=%(control_ok)d" % c)
    L.append("000292 VSTATE end status=%s class=%s reason=%s stop=%s restore=%s teardown=%s power_cycle_required=%d errors=%d transport_ok=1" % (
        v["status"], v["cls"], v["reason"], v["stop"], v["restore"], v["teardown"], v["pcr"], v["errors"]))
    L.append("000145 STREAMSRC closed=%(closed)d complete=%(complete)d incomplete=%(incomplete)d quarantined=%(quarantined)d anomaly=%(anomaly)d published=%(published)d" % s)
    L.append("000717 WITQUAL policy=consecutive_structural_complete required=64 state=2 streak_max=64 resets=0 warmup_frames=356 warmup_disqualified=26 qualify_frame=355 qualified=%d armed=1 window_first_block=0 first_record_frame=356" % witqual)
    L.append("000727 STREAMWIT records=%s target=2048 frames_seen=2048 discarded=0 staged=1 placed=1 out_of_range=0 store_full=0 target_reached=1" % witness)
    L.append("000302 STRUCTURED status=observed episodes=31 stable=29 unstable=2 not_preserved=27 store_full=1 descriptors=4 raw_slots=16 tail_frames=0 tail_ticks=0 tail_truncated=0")
    if inp:
        L.append("000710 INPUT " + inp)
    if extra:
        L.append(extra)
    L.append("# --- end --- dropped=%d" % end_dropped)
    return "\n".join(L) + "\n"


def rd(**kw):
    return g.read(g.parse(make_log(**kw)))


class TheReaderSaysWhichRivalReadingMatches(unittest.TestCase):
    def test_the_expected_reading_the_service_runs_with_a_gba_structure(self):
        o = rd()
        self.assertEqual([o["gates"][k].split()[0] for k in ("identity", "log_complete", "control_record", "gb_media_attested")], ["PASS"] * 4)
        self.assertTrue(o["q1_service"].startswith("SERVICE_RAN_TO_TARGET"))
        self.assertTrue(o["q2_video"].startswith("GBA_STRUCTURE"))
        self.assertTrue(o["q3_audio"].startswith("AUDIO_COUNT_AS_GBA"))
        self.assertTrue(o["q4_restore"].startswith("RESTORE_HOLDS_BIT"))
        self.assertTrue(o["tolerance_record"].startswith("CONTROLTOL n=6"))
        self.assertTrue(o["keypad"].startswith("IDLE_ONLY"))

    def test_the_old_image_refused_at_preunmask_is_told_apart_from_a_strict_bit(self):
        o = rd(pre_ok=0, pre_reason="control_changed", pre_control=0x8F, counters=dict(unmasks=0, deliveries=0, audio=0, video=0, control_ok=0),
               vend=dict(status="anomaly_control_changed", cls="anomaly", reason="control_changed_PREUNMASK", stop="failure"), tol=None)
        self.assertTrue(o["q1_service"].startswith("REFUSED_AT_PREUNMASK_POLICY_ABSENT"))
        self.assertTrue(o["q2_video"].startswith("NOT_EVALUABLE"))
        o2 = rd(pre_ok=0, pre_reason="control_changed", pre_control=0x8E ^ 0x01 ^ 0x02, counters=dict(unmasks=0, deliveries=0, audio=0, video=0, control_ok=0), tol=None)
        self.assertTrue(o2["q1_service"].startswith("REFUSED_AT_PREUNMASK_STRICT_BIT"), o2["q1_service"])
        self.assertIn("A FINDING", o2["q1_service"])
        o3 = rd(pre_ok=0, pre_reason="irq_state_unexpected", counters=dict(unmasks=0, deliveries=0, audio=0, video=0, control_ok=1), tol=None)
        self.assertTrue(o3["q1_service"].startswith("REFUSED_AT_PREUNMASK_OTHER_CLAUSE"))

    def test_a_later_guard_tripping_on_a_strict_bit_is_a_finding(self):
        o = rd(vend=dict(status="anomaly_control_changed", cls="anomaly", reason="control_changed_POSTACK_cycle_3", stop="failure", teardown="S3_cycle_aborted"),
               counters=dict(deliveries=3, acks=2, rearms=2, video=120, audio=200))
        self.assertTrue(o["q1_service"].startswith("ABORT_AT_LATER_GUARD control_changed_POSTACK_cycle_3"))
        self.assertIn("A FINDING", o["q1_service"])

    def test_nothing_arrives(self):
        o = rd(counters=dict(deliveries=0, acks=0, rearms=0, video=0, audio=0),
               vend=dict(status="first_delivery_timeout", cls="observation", reason="-", stop="failure", teardown="S3"))
        self.assertTrue(o["q1_service"].startswith("NO_DELIVERY"))
        self.assertTrue(o["q2_video"].startswith("NOT_EVALUABLE"))
        o2 = rd(counters=dict(video=0, audio=500), src=dict(closed=0, complete=0, incomplete=0, anomaly=0, published=0))
        self.assertTrue(o2["q2_video"].startswith("NO_VIDEO"))
        self.assertTrue(rd(counters=dict(audio=0))["q3_audio"].startswith("NO_AUDIO"))

    def test_a_different_structure_is_told_apart_from_the_gba_one(self):
        cases = [dict(counters=dict(video=48000)),                       # 20 blocks per closed frame
                 dict(src=dict(incomplete=400, anomaly=400)),             # many frames never close
                 dict(src=dict(quarantined=3)),
                 dict(witqual=0),                                         # the structural witness never qualifies
                 dict(src=dict(closed=100, complete=90, incomplete=10, anomaly=10), counters=dict(video=4000))]
        for kw in cases:
            self.assertTrue(rd(**kw)["q2_video"].startswith("DIFFERENT_STRUCTURE"), (kw, rd(**kw)["q2_video"]))
        self.assertTrue(rd(counters=dict(audio=30000))["q3_audio"].startswith("AUDIO_COUNT_DIFFERENT"))

    def test_the_run_ended_by_the_safety_cap_is_not_read_as_reaching_the_target(self):
        o = rd(vend=dict(status="ok_no_change_inconclusive", cls="ok", reason="-", stop="safety_budget", teardown="S5"), witqual=0)
        self.assertTrue(o["q1_service"].startswith("SERVICE_RAN_ENDED_BY_SAFETY_BUDGET"))
        self.assertTrue(o["q2_video"].startswith("DIFFERENT_STRUCTURE"))

    def test_the_restore_readbacks(self):
        self.assertTrue(rd(restore=(0x92, 0x92, 0x92, 1))["q4_restore"].startswith("RESTORE_CLEARS_BIT"))
        o = rd(restore=(0x92, 0x9B, 0x9B, 0))
        self.assertTrue(o["q4_restore"].startswith("RESTORE_OTHER"))
        self.assertIn("A FINDING", o["q4_restore"])
        self.assertTrue(rd(restore=None)["q4_restore"].startswith("NOT_REACHED"))

    def test_bit_0x01_read_but_no_record_is_a_finding(self):
        o = rd(tol=None)
        self.assertIn("ABSENT although bit 0x01 was read", o["tolerance_record"])
        self.assertIn("A FINDING", o["tolerance_record"])

    def test_the_gates(self):
        self.assertTrue(rd(build="stream-0015")["gates"]["identity"].startswith("FAIL"))
        self.assertTrue(rd(dropped=3)["gates"]["log_complete"].startswith("FAIL"))
        self.assertTrue(rd(end_dropped=1)["gates"]["log_complete"].startswith("FAIL"))
        self.assertTrue(rd(orig=0x90, exp=0x8C)["gates"]["control_record"].startswith("FAIL"))
        o = rd(raw_votes=(0x8E, 0x8E, 0x8E), tol=None, restore=(0x92, 0x92, 0x92, 1))
        self.assertTrue(o["gates"]["gb_media_attested"].startswith("FAIL"))          # the bit never arrived: not evidence about GB mode

    def test_a_strict_bit_in_a_snapshot_before_the_teardown_is_listed(self):
        o = rd(raw_votes=(0x8E, 0x8F, 0x9F))
        self.assertEqual(o["facts"]["strict_bit_snapshots_before_teardown"], [("T2", "9f")])

    def test_a_keypad_word_that_was_not_idle_is_a_deviation_not_a_failure(self):
        o = rd(inp="selftest=1 steps=1 invalid=0 no_base=0 key_changes=2 attempts=7800 completed=7800 failed=0 first=1 change=2 refresh=7797 retry=0 last_word=0100 last_rc=ok")
        self.assertTrue(o["keypad"].startswith("DEVIATION"))
        self.assertTrue(o["q1_service"].startswith("SERVICE_RAN_TO_TARGET"))

    def test_a_degraded_service_is_not_the_predicted_reading(self):
        o = rd(vend=dict(status="capture_completed_with_errors", cls="errors", errors=37), counters=dict(acks=200000, rearms=199990, control_ok=0))
        self.assertTrue(o["q1_service"].startswith("SERVICE_RAN_TO_TARGET_WITH_ERRORS"), o["q1_service"])
        for w in ("errors=37", "acks=200000", "control_ok=0"):
            self.assertIn(w, o["q1_service"])
        self.assertTrue(rd(vend=dict(restore="error"))["q1_service"].startswith("SERVICE_RAN_TO_TARGET_WITH_ERRORS"))
        self.assertTrue(rd()["q1_service"].startswith("SERVICE_RAN_TO_TARGET deliveries"))

    def test_no_unmask_is_not_no_delivery(self):
        o = rd(counters=dict(unmasks=0, deliveries=0, acks=0, rearms=0, video=0, audio=0),
               vend=dict(status="abort_unmask", cls="abort", reason="unmask_failed", stop="failure", teardown="S2"))
        self.assertTrue(o["q1_service"].startswith("OTHER_ENDING"), o["q1_service"])
        self.assertTrue(rd(counters=dict(unmasks=1, deliveries=0, acks=0, rearms=0, video=0, audio=0),
                           vend=dict(status="first_delivery_timeout", cls="observation", stop="failure"))["q1_service"].startswith("NO_DELIVERY"))

    def test_a_dirty_commit_is_never_a_candidate(self):
        o = rd(commit="abc1234-dirty")
        self.assertTrue(o["gates"]["identity"].startswith("FAIL"))
        self.assertIn("-dirty", o["gates"]["identity"])
        self.assertIn("commit not compared", rd()["gates"]["identity"])
        self.assertEqual(g.read(g.parse(make_log()), commit="abc1234")["gates"]["identity"], "PASS")
        self.assertTrue(g.read(g.parse(make_log()), commit="zzzzzzz")["gates"]["identity"].startswith("FAIL"))

    def test_a_log_cut_in_the_middle_of_a_record_is_a_gate_failure_not_a_crash(self):
        full = make_log()
        for cut in (len(full) - 5, full.index("readback_vote") + 5, full.index("COUNTERS") + 40, full.index("STREAMSRC") + 30,
                    full.index("WITQUAL") + 60, full.index("INPUT selftest") + 30):
            o = g.read(g.parse(full[:cut]))
            self.assertTrue(o["gates"]["log_complete"].startswith("FAIL"), cut)

    def test_the_restore_check_refusing_a_tolerated_readback_is_flagged(self):
        o = rd(restore=(0x92, 0x93, 0x93, 0))
        self.assertTrue(o["q4_restore"].startswith("RESTORE_HOLDS_BIT"))
        self.assertIn("ok=0", o["q4_restore"])
        self.assertIn("A FINDING", o["q4_restore"])

    def test_a_bit_seen_only_after_the_stop_does_not_attest_gb_media(self):
        text = make_log(raw_votes=(0x8E, 0x8E, 0x8E)).replace("# --- end ---", "000200 RAW TDCTL idx=4 addr=1 rc=ok ticks=1 polls=1 dspcr=0 sem_vote=93 sem_b1f=93 data=00\n# --- end ---")
        o = g.read(g.parse(text))
        self.assertTrue(o["gates"]["gb_media_attested"].startswith("FAIL"))

    def test_q2_says_on_its_own_line_that_it_is_about_closure(self):
        self.assertIn("says nothing about the picture", rd()["q2_video"])

    def test_the_tool_prints_and_never_computes_the_operators_words(self):
        text = g.render(rd())
        self.assertIn("NOT COMPUTED HERE: what the Operator saw on the TV", text)


class TheArchiveControls(unittest.TestCase):
    """The reader against logs whose truth is already known."""

    def test_it_never_crashes_on_any_archived_log(self):
        import glob
        paths = sorted(glob.glob(os.path.join(LOCAL, "*.log")))
        if not paths:
            self.skipTest("no local archive on this host (captures/local is ignored)")
        for p in paths:
            with open(p, encoding="utf-8", errors="replace") as f:
                text = f.read()
            g.render(g.read(g.parse(text)))          # no exception, on every log of every family

    def logs(self, names):
        paths = [os.path.join(LOCAL, "GBP-VIDEO-004_stream-0015-%s.log" % n) for n in names]
        if not all(os.path.exists(p) for p in paths):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        return paths

    def test_the_gba_and_no_cartridge_runs_read_gba_structure(self):
        for p in self.logs(["run16", "run17", "run18", "run23"]):
            with open(p, encoding="utf-8", errors="replace") as f:
                o = g.read(g.parse(f.read()), build="stream-0015")
            self.assertTrue(o["q1_service"].startswith("SERVICE_RAN_TO_TARGET"), (p, o["q1_service"]))
            self.assertTrue(o["q2_video"].startswith("GBA_STRUCTURE"), (p, o["q2_video"]))
            self.assertTrue(o["q3_audio"].startswith("AUDIO_COUNT_AS_GBA"), (p, o["q3_audio"]))
            self.assertTrue(o["gates"]["gb_media_attested"].startswith("FAIL"), p)     # no GB bit in these: they are the GBA baseline

    def test_the_four_aborted_gb_boots_read_refused_at_preunmask_policy_absent(self):
        for p in self.logs(["run24", "run27", "run28", "run29"]):
            with open(p, encoding="utf-8", errors="replace") as f:
                o = g.read(g.parse(f.read()), build="stream-0015")
            self.assertTrue(o["q1_service"].startswith("REFUSED_AT_PREUNMASK_POLICY_ABSENT"), (p, o["q1_service"]))
            self.assertTrue(o["q2_video"].startswith("NOT_EVALUABLE"), p)
            self.assertTrue(o["gates"]["gb_media_attested"].startswith("PASS"), p)
            self.assertTrue(o["q4_restore"].startswith("RESTORE_HOLDS_BIT"), p)         # 0x93 against 0x92, as GBP-HW-276 records


if __name__ == "__main__":
    unittest.main()
