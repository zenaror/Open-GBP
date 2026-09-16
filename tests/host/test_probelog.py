"""Tests for tools/probelog.py on a synthetic device log."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import probelog  # noqa: E402

INV_C3 = "3c" * 32
LOG = """# OPENGBP-LOG v1
test_id=GBP-PROBE-001
build_id=probe-0001
commit=abc1234-dirty
lines=12 dropped=0 truncated=0
# --- records ---
000000 IDENT test=GBP-PROBE-001 app=gbp-probe build=probe-0001 commit=abc1234-dirty libogc=libogc2
000001 PROBE start npatterns=1 nindices=1 exp_code=3 mode_b=1
000002 ARINFO orig value=0043 size_code=3 exp_code=0 base=01000000
000003 ARINFO modeA value=0043 size_code=3 exp_code=0 base=01000000
000004 MODE A begin base=01000000
000005 RAW mode=A idx=0 addr=01000000 rc=ok ticks=120 polls=3 dspcr=0000 data=%s
000006 TESTW mode=A idx=0 pattern=c3 rc=ok ticks=100 polls=2 dspcr=0000
000007 TESTR mode=A idx=0 pattern=c3 expect=3c rc=ok ticks=110 polls=2 dspcr=0000 match_all=1 match_1f=1 data=%s
000008 RAW mode=A idx=0 addr=01000000 rc=timeout ticks=999 polls=500 dspcr=0200 data=-
000009 ARINFO endA value=0043 size_code=3 exp_code=0 base=01000000
000010 ARINFO write mode=B value=005b rc=ok
000011 ARINFO restore value=0043 rc=ok
000012 ARINFO final value=0043 size_code=3 exp_code=0 base=01000000
000013 PROBE end modes=2 errors=1 changed=1 restored=1
# --- end --- dropped=0
""" % (INV_C3, INV_C3)


class ProbeLog(unittest.TestCase):
    def setUp(self):
        self.header, self.records = probelog.parse_lines(LOG.splitlines(True))

    def test_header_and_records(self):
        self.assertEqual(self.header["build_id"], "probe-0001")
        kinds = [r["kind"] for r in self.records]
        self.assertEqual(kinds.count("ARINFO"), 6)
        raw = [r for r in self.records if r["kind"] == "RAW"]
        self.assertEqual(raw[0]["fields"]["data_bytes"], bytes.fromhex(INV_C3))
        self.assertNotIn("data_bytes", raw[1]["fields"])
        self.assertEqual([r["tag"] for r in self.records if r["kind"] == "ARINFO"],
                         ["orig", "modeA", "endA", "write", "restore", "final"])

    def test_gecko_prefixed_lines_are_accepted(self):
        _, recs = probelog.parse_lines(["OPENGBP-PROBE LOG 000002 ARINFO orig value=0043\n"])
        self.assertEqual(recs[0]["fields"]["value"], "0043")

    def test_fixture(self):
        fx = probelog.fixture(self.records).splitlines()
        self.assertEqual(fx[1], "A r 0043")
        self.assertIn("R 01000000 ok " + INV_C3, fx)
        self.assertIn("W 01000000 ok", fx)
        self.assertIn("R 01000000 timeout", fx)
        self.assertIn("A w 005b", fx)
        self.assertIn("A w 0043", fx)
        self.assertEqual(fx[-1], "A r 0043")

    def test_fixture_init_irq_records(self):
        # GBP-INIT-002 records: PI reads become "P r"; the unmask becomes
        # "T t_unmask", "I u <handler record>", "T t_post"; the wait becomes the
        # loop-exit and t_wait_end time-base values; mask/restore become "I m"/"I r";
        # the single main-loop acknowledge becomes "P a". HANDLER/HANDLERPI feed "I u".
        _, recs = probelog.parse_lines([
            "000030 PI tag=UNMASKPRE rc=ok intsr=00010000 intmr=000001fa intsr13=0 intmr13=0\n",
            "000031 UNMASK t_unmask=100 rc=ok t_post=110 dt_post=10\n",
            "000032 PI tag=UNMASKPOST rc=ok intsr=00010000 intmr=000021fa intsr13=0 intmr13=1 fired=0\n",
            "000033 IRQ mask tag=MAIN rc=ok\n",
            "000034 WAIT fired=0 timed_out=1 polls=5 wait_ticks=400 wait_us=9 t_max_ms=2000 t_max_ticks=400\n",
            "000040 HANDLER fired=0 count=0 t_entry=0 t_unmask=100 latency_ticks=0 latency_us=0 reentry=0\n",
            "000041 HANDLERPI intsr_before_ack=00000000 intmr_at_entry=00000000 intsr_after_ack=00000000 intmr_after_mask=00000000 reentry_intsr=00000000 reentry_intmr=00000000\n",
            "000050 CLEANUP performed=1 value=00002000 rc=ok intsr_before=00012000 intsr_after=00010000 intsr13_after=0\n",
            "000051 IRQ restore rc=ok ok=1 old_handler=null\n",
            "000052 CLEANUP performed=0 intsr=00010000 intsr13=0 intmr13=0\n",
        ])
        fx = probelog.fixture(recs).splitlines()[1:]
        self.assertEqual(fx, ["P r 00010000 000001fa",
                              "T 100",
                              "I u 0 0 0 00000000 00000000 00000000 00000000 00000000 00000000",
                              "T 110",
                              "P r 00010000 000021fa",
                              "T 500", "T 500",
                              "I m",
                              "P a 00002000",
                              "I r"])
        # a handler that ran: its record travels on the "I u" line, and the wait ends at the first poll
        _, recs = probelog.parse_lines([
            "000031 UNMASK t_unmask=100 rc=ok t_post=110 dt_post=10\n",
            "000034 WAIT fired=1 timed_out=0 polls=1 wait_ticks=20 wait_us=0 t_max_ms=2000 t_max_ticks=400\n",
            "000040 HANDLER fired=1 count=1 t_entry=115 t_unmask=100 latency_ticks=15 latency_us=0 reentry=0\n",
            "000041 HANDLERPI intsr_before_ack=00012000 intmr_at_entry=000021fa intsr_after_ack=00010000 intmr_after_mask=000001fa reentry_intsr=00000000 reentry_intmr=00000000\n",
            "000042 IRQ install rc=ok old_handler=nonnull\n",
        ])
        fx = probelog.fixture(recs).splitlines()[1:]
        self.assertEqual(fx, ["T 100",
                              "I u 1 1 115 00012000 000021fa 00010000 000001fa 00000000 00000000",
                              "T 110",
                              "T 120",
                              "I i nonnull"])

    def test_fixture_initirqa_records(self):
        # GBP-INIT-003A records: IRQW becomes "W addr rc" + "T t_after"; CTLW with t_after likewise;
        # the EVENT snapshot becomes "T ticks" + "P p <polled INTSR>" before its own PI read;
        # WINDOW tag=A2 gives the t_window_end read. Nothing is emitted for the poll counters.
        _, recs = probelog.parse_lines([
            "000020 CTLW tag=EXP addr=01400000 semantic=8c rc=ok ticks=101 polls=1 dspcr=0020 t_after=1300 layout=gbi-replicated data=" + "8c" * 32 + "\n",
            "000030 RAW A1PRE idx=d addr=01d00000 rc=ok ticks=102 polls=1 dspcr=0020 sem_disc=8aae sem_gbi=8aae data=" + "8a8aaeae" * 8 + "\n",
            "000031 IRQW tag=A1 addr=01d00000 before=8aae write=8aae layout=gbi-u16-replicated rc=ok ticks=103 polls=1 dspcr=0020 t_after=1400 data=" + "8aae" * 16 + "\n",
            "000032 SNAP tag=A1-0 ticks=1410 since_control=110 since_a1=10 since_a2=0 polls_before=0\n",
            "000033 PI tag=A1-0 intsr=00010000 intmr=000001fa intsr13=0 intmr13=0\n",
            "000040 IRQW tag=A2 addr=01d00000 before=8aaa write=0000 layout=gbi-u16-replicated rc=ok ticks=104 polls=1 dspcr=0020 t_after=1600 data=" + "00" * 32 + "\n",
            "000041 SNAP tag=EVENT ticks=1900 since_control=600 since_a1=500 since_a2=300 polls_before=30 poll_intsr=00012000\n",
            "000042 PI tag=EVENT intsr=00012000 intmr=000001fa intsr13=1 intmr13=0\n",
            "000043 WINDOW tag=A2 deadlines=3/6 polls=30 poll_errors=0 ended_early=1 event=1 t_event=1900 intsr13_seen=1 t_first_intsr13=1900 first_phase=A2 t_end=1910 elapsed_ticks=310 elapsed_us=7 no_timebase=0\n",
            "000050 IRQW tag=STOP addr=01d00000 before=0100 write=8baa layout=gbi-u16-replicated rc=timeout ticks=105 polls=9 dspcr=0200 t_after=2000 data=" + "8baa" * 16 + "\n",
        ])
        fx = probelog.fixture(recs).splitlines()[1:]
        self.assertEqual(fx, ["W 01400000 ok", "T 1300",
                              "R 01d00000 ok " + "8a8aaeae" * 8,
                              "W 01d00000 ok", "T 1400",
                              "T 1410",
                              "P r 00010000 000001fa",
                              "W 01d00000 ok", "T 1600",
                              "T 1900", "P p 00012000",
                              "P r 00012000 000001fa",
                              "T 1910",
                              "W 01d00000 timeout", "T 2000"])

    def test_fixture_initirqb_records(self):
        # GBP-INIT-003B: HANDLERPI names the same record fields intsr_at_entry / intsr_after_w1c, HANDLERPI2
        # appends five numbers to "I u" (intsr_before_w1c t_second intsr_second intmr_second reentry_t);
        # the POSTACK main-loop W1C becomes "P a" before the MAINCLEANUP re-read; the MAIN mask keeps
        # the 002 rule (WAIT time-base reads first).
        _, recs = probelog.parse_lines([
            "000075 IRQ install rc=ok old_handler=null\n",
            "000082 PI tag=UNMASKPRE rc=ok intsr=00012000 intmr=000001fa intsr13=1 intmr13=0\n",
            "000083 UNMASK t_unmask=1470 rc=ok t_post=1583 dt_post=113\n",
            "000084 PI tag=UNMASKPOST rc=ok intsr=00010000 intmr=000001fa intsr13=0 intmr13=0 fired=1\n",
            "000085 IRQ mask tag=MAIN rc=ok\n",
            "000086 WAIT fired=1 timed_out=0 polls=1 wait_ticks=123 wait_us=3 t_delivery_ms=100 t_delivery_ticks=400\n",
            "000087 PI tag=REMASKCHK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0\n",
            "000088 HANDLER fired=1 count=1 t_entry=1471 t_unmask=1470 latency_ticks=1 latency_us=0 reentry=0\n",
            "000089 HANDLERPI intsr_at_entry=00012000 intmr_at_entry=000021fa intmr_after_mask=000001fa intsr_before_w1c=00012000 intsr_after_w1c=00010000 reentry_intsr=00000000 reentry_intmr=00000000\n",
            "000090 HANDLERPI2 t_second=1573 dt_second=102 intsr_second=00010000 intmr_second=000001fa reentry_t=0\n",
            "000106 MAINPICLEANUP site=POSTACK performed=1 value=00002000\n",
            "000107 PI tag=MAINCLEANUP intsr=00010000 intmr=000001fa intsr13=0 intmr13=0\n",
            "000108 MAINPICLEANUP result rc=ok intsr_before=00012000 intsr_after=00010000 intsr13_after=0 sticky=0\n",
            "000118 IRQ restore rc=ok ok=1 old_handler=null\n",
        ])
        fx = probelog.fixture(recs).splitlines()[1:]
        self.assertEqual(fx, ["I i null",
                              "P r 00012000 000001fa",
                              "T 1470",
                              "I u 1 1 1471 00012000 000021fa 00010000 000001fa 00000000 00000000 00012000 1573 00010000 000001fa 0",
                              "T 1583",
                              "P r 00010000 000001fa",
                              "T 1593",
                              "I m",
                              "P r 00010000 000001fa",
                              "P a 00002000",
                              "P r 00010000 000001fa",
                              "I r"])
        # performed=0 emits nothing; a timed-out wait and the RETRY mask replay as in 002
        _, recs = probelog.parse_lines([
            "000083 UNMASK t_unmask=1470 rc=ok t_post=1583 dt_post=113\n",
            "000085 IRQ mask tag=MAIN rc=ok\n",
            "000086 WAIT fired=0 timed_out=1 polls=40 wait_ticks=400 wait_us=9 t_delivery_ms=100 t_delivery_ticks=400\n",
            "000087 PI tag=REMASKCHK intsr=00012000 intmr=000021fa intsr13=1 intmr13=1\n",
            "000088 IRQ mask tag=RETRY rc=ok\n",
            "000089 PI tag=REMASKCHK2 intsr=00012000 intmr=000001fa intsr13=1 intmr13=0\n",
            "000090 HANDLER fired=0 count=0 t_entry=0 t_unmask=1470 latency_ticks=0 latency_us=0 reentry=0\n",
            "000091 HANDLERPI intsr_at_entry=00000000 intmr_at_entry=00000000 intmr_after_mask=00000000 intsr_before_w1c=00000000 intsr_after_w1c=00000000 reentry_intsr=00000000 reentry_intmr=00000000\n",
            "000092 HANDLERPI2 t_second=0 dt_second=0 intsr_second=00000000 intmr_second=00000000 reentry_t=0\n",
            "000106 MAINPICLEANUP site=POSTACK performed=0 intsr13=0 intmr13=0\n",
        ])
        fx = probelog.fixture(recs).splitlines()[1:]
        self.assertEqual(fx, ["T 1470",
                              "I u 0 0 0 00000000 00000000 00000000 00000000 00000000 00000000 00000000 0 00000000 00000000 0",
                              "T 1583",
                              "T 1870", "T 1870",
                              "I m",
                              "P r 00012000 000021fa",
                              "I m",
                              "P r 00012000 000001fa"])

    def test_fixture_initirq4_records(self):
        # GBP-INIT-004: PREPARE publishes the generation ("I p", optional in a replay); the per-cycle records keep
        # the 003B kinds with an " n=" field and "-n" tags, so the rules above apply per cycle (each "I u" carries
        # its own cycle's HANDLER* record: the search stops at the next UNMASK); REARM's time base precedes the
        # IRQW tag=REARM-n write; a NEXTCAUSE snapshot is an EVENT-style snapshot (T + P p); a timed-out wait
        # emits the loop's last time-base read.
        _, recs = probelog.parse_lines([
            "000075 IRQ install rc=ok old_handler=null record_count=0 record_fired=0\n",
            "000076 PREPARE n=0 gen=0 rc=ok intmr13=0 expected_gen=0 entries_total=0 generation_errors=0 slot_count=0 slot_fired=0\n",
            "000083 UNMASK n=0 t_unmask=1470 rc=ok t_post=1583 dt_post=113\n",
            "000085 IRQ mask tag=MAIN n=0 rc=ok\n",
            "000086 WAIT n=0 fired=1 timed_out=0 polls=1 wait_ticks=123 wait_us=3 t_delivery_ms=100 t_delivery_ticks=400\n",
            "000088 HANDLER n=0 fired=1 count=1 t_entry=1471 t_unmask=1470 latency_ticks=1 latency_us=0 reentry=0\n",
            "000089 HANDLERPI n=0 intsr_at_entry=00012000 intmr_at_entry=000021fa intmr_after_mask=000001fa intsr_before_w1c=00012000 intsr_after_w1c=00010000 reentry_intsr=00000000 reentry_intmr=00000000\n",
            "000090 HANDLERPI2 n=0 t_second=1573 dt_second=102 intsr_second=00010000 intmr_second=000001fa reentry_t=0\n",
            "000100 IRQW tag=ACK-0 addr=01d00000 before=0500 write=8500 layout=gbi-u16-replicated rc=ok ticks=30 polls=8 dspcr=0804 t_after=1700 data=-\n",
            "000110 REARM n=0 t_rearm=1800 before=8000 value=0000 layout=gbi-u16-replicated after=clean_boundary\n",
            "000111 IRQW tag=REARM-0 addr=01d00000 before=8000 write=0000 layout=gbi-u16-replicated rc=ok ticks=30 polls=8 dspcr=0804 t_after=1810 data=-\n",
            "000112 SNAP tag=REARMPOST-0 ticks=1820 since_control=100 since_a1=90 since_a2=80 polls_before=0\n",
            "000120 SNAP tag=NEXTCAUSE-0 ticks=1900 since_control=100 since_a1=90 since_a2=80 polls_before=8 poll_intsr=00012000\n",
            "000121 NEXTCAUSE n=0 found=1 immediate=0 t_next_cause=1900 since_rearm=100 since_prev_cause=500 intsr=00012000 control=8c irq=0500/0500 av=0500 unexpected=0000 polls=8\n",
            "000122 PREPARE n=1 gen=1 rc=ok intmr13=0 expected_gen=1 entries_total=1 generation_errors=0 slot_count=0 slot_fired=0\n",
            "000130 UNMASK n=1 t_unmask=2470 rc=ok t_post=2583 dt_post=113\n",
            "000131 IRQ mask tag=MAIN n=1 rc=ok\n",
            "000132 WAIT n=1 fired=1 timed_out=0 polls=1 wait_ticks=123 wait_us=3 t_delivery_ms=100 t_delivery_ticks=400\n",
            "000133 HANDLER n=1 fired=1 count=1 t_entry=2471 t_unmask=2470 latency_ticks=1 latency_us=0 reentry=0\n",
            "000134 HANDLERPI n=1 intsr_at_entry=00012000 intmr_at_entry=000021fa intmr_after_mask=000001fa intsr_before_w1c=00012000 intsr_after_w1c=00010000 reentry_intsr=00000000 reentry_intmr=00000000\n",
            "000135 HANDLERPI2 n=1 t_second=2573 dt_second=102 intsr_second=00010000 intmr_second=000001fa reentry_t=0\n",
            "000140 REARM n=1 t_rearm=2800 before=8000 value=0000 layout=gbi-u16-replicated after=clean_boundary\n",
            "000141 NEXTCAUSE n=1 found=0 timed_out=1 t_end=4800 since_rearm=2000 polls=200 rearmpost=A_quiet t_next_cause_ticks=2000\n",
            "000150 IRQ restore rc=ok ok=1 old_handler=null\n",
        ])
        fx = probelog.fixture(recs).splitlines()[1:]
        self.assertEqual(fx, ["I i null",
                              "I p 0",
                              "T 1470",
                              "I u 1 1 1471 00012000 000021fa 00010000 000001fa 00000000 00000000 00012000 1573 00010000 000001fa 0",
                              "T 1583",
                              "T 1593",
                              "I m",
                              "W 01d00000 ok", "T 1700",
                              "T 1800",
                              "W 01d00000 ok", "T 1810",
                              "T 1820",
                              "T 1900", "P p 00012000",
                              "I p 1",
                              "T 2470",
                              "I u 1 1 2471 00012000 000021fa 00010000 000001fa 00000000 00000000 00012000 2573 00010000 000001fa 0",
                              "T 2583",
                              "T 2593",
                              "I m",
                              "T 2800",
                              "T 4800",
                              "I r"])

    def test_fixture_avsvc_records(self):
        # GBP-AV-SERVICE-001: a whole-block read is one "B" line between the two time-base reads that
        # bracket the call; its crc32 comes from the run's BLOCK record (only for a completed read); the
        # bytes are never in the script. The other service records emit nothing of their own.
        _, recs = probelog.parse_lines([
            "000095 SNAP tag=PRESVC ticks=1603 since_control=583 since_a1=563 since_a2=453 polls_before=0\n",
            "000101 SVC start pending=0500 drain=0500 audio=1 video=1 order=audio_then_video ack_value=8500 ack_source=PRESVC t=1603\n",
            "000102 AUDIOREAD idx=8 addr=01800000 len=1000 selected=1 attempted=1 completed=1 rc=ok t_start=1613 t_end=1623 dt=10 wait_ticks=384 polls=128 csr_before=0000 csr_after=0020\n",
            "000103 VIDEOREAD idx=1 addr=01100000 len=0f00 selected=1 attempted=1 completed=0 rc=timeout t_start=1633 t_end=1643 dt=10 wait_ticks=360 polls=120 csr_before=0000 csr_after=0200\n",
            "000104 SVCEND drain=0500 selected=2 attempted=2 completed=1 ok=0 t_end=1643 dt_service=40 audio_rc=ok video_rc=timeout\n",
            "000126 REARM t_rearm=1683 before=8000 value=0000 layout=gbi-u16-replicated after=drain_ack_pi_clean\n",
            "000141 NEXTCAUSE found=0 timed_out=1 t_end=3700 since_rearm=2017 polls=200 rearmpost=A_quiet t_next_cause_ticks=2000\n",
            "000170 BLOCK kind=audio idx=8 len=1000 present=1 valid=1 crc32=9897b144 zeros=17 distinct=256 w_off=0000,0540,0aa0,0fe0 first_word=dbe2e9f0 gbi_frame_start=1\n",
            "000171 BLOCKW kind=audio off=0000 data=dbe2e9f0f7fe050c131a21282f363d444b525960676e757c838a91989fa6adb4\n",
            "000175 BLOCK kind=video idx=1 len=0f00 present=1 valid=0 rc=timeout summary=-\n",
            "000180 VIDEOREAD idx=1 addr=01100000 len=0f00 selected=0 attempted=0 rc=-\n",
        ])
        fx = probelog.fixture(recs).splitlines()[1:]
        self.assertEqual(fx, ["T 1603",
                              "T 1613", "B 01800000 00001000 ok 9897b144", "T 1623",
                              "T 1633", "B 01100000 00000f00 timeout", "T 1643",
                              "T 1683",
                              "T 3700"])

    def test_fixture_video_records(self):
        """GBP-VIDEO-001: a lean cycle's compact records become the same operation stream a verify
        cycle's detailed records do — admission read, PREPARE PI read, the unmask and its handler
        record, the bounded wait, the re-mask, the pending read, the two whole-block reads, the ACK,
        the PI clean, the re-arm and WAIT_NEXT. A verify cycle's compact records are SKIPPED: its
        detailed records already produced those operations, and emitting both would double them."""
        log = """# OPENGBP-LOG v1
test_id=GBP-VIDEO-001
build_id=synthetic
# --- records ---
000000 CYCU n=5 verify=0 t_adm=1000 prep=00012000/000001fa/ok pre=00012000/000001fa t_unmask=1010 t_post=1020 post=00012000/000021fa rec0=0
000001 CYCW n=5 polls=1 timed_out=0 t_wait_end=1030 remask=00010000/000001fa retry=0 mask_ok=1
000002 CYCH n=5 rec=1,1,1015,00012000,000021fa,00010000,000001fa,00000000,00000000,00012000,0,00000000,00000000,0 lat=5 reentry=0
000003 RAW READ-5 idx=d addr=01d00000 rc=ok ticks=3 polls=1 dspcr=0020 sem_disc=0500 sem_gbi=0500 data=1705010005050500050505000505050005050500050505000505050005050500
000004 CYCD n=5 pend=0500 disc=0500 gbi=0500 b0=17 o2=01 t_read=1040 a=1/1/1/ok/5/1050/1060/2475/aabbccdd/01800000 v=1/1/1/ok/3/1070/1080/2319/01100000 ack=1/1/8500/1090
000005 CYCR n=5 pi=00010000/000001fa w1c=0 after=00010000 sticky=0 relatch=0/0 rearm=1/1/1100/1110 next=1/cause/1120/00012000/1 end=-
000006 VBLK seq=3 cyc=5 pend=0500 rc=ok completed=1 t_start=1070 t_end=1080 dt=10 wait=2319 polls=120 csr=0000/0020 crc32=deadbeef f4=ffffffff gbi=1 disc=1 agree=1 x0=0 und=0
# --- end --- dropped=0
"""
        header, records = probelog.parse_lines(log.splitlines())
        text = probelog.fixture(records)
        lines = [l for l in text.splitlines() if l and not l.startswith("#")]
        self.assertEqual(lines, [
            "T 1000",                                   # t_adm = now()
            "P r 00012000 000001fa",                    # PREPARE: the record reset writes no register
            "P r 00012000 000001fa",                    # the pre-unmask PI read
            "T 1010",                                   # t_unmask
            "I u 1 1 1015 00012000 000021fa 00010000 000001fa 00000000 00000000 00012000 0 00000000 00000000 0",
            "T 1020",                                   # t_post_unmask
            "P r 00012000 000021fa",
            "T 1030",                                   # t_wait_end
            "I m",
            "P r 00010000 000001fa",                    # the re-mask read
            "R 01d00000 ok 1705010005050500050505000505050005050500050505000505050005050500",
            "T 1040",                                   # t_read, after the block read
            "T 1050", "B 01800000 00001000 ok aabbccdd", "T 1060",      # AUDIO first
            "T 1070", "B 01100000 00000f00 ok deadbeef", "T 1080",      # then VIDEO, its CRC from the VBLK record
            "W 01d00000 ok", "T 1090",                  # the ACK, then t_after
            "P r 00010000 000001fa",                    # PICLEAN: bit 13 clear, so no W1C
            "T 1100", "W 01d00000 ok", "T 1110",        # t_rearm, the re-arm, t_after
            "T 1120", "P p 00012000",                   # WAIT_NEXT: the poll that saw the next cause
        ])

    def test_fixture_skips_a_verify_cycle_compact_records(self):
        log = """# OPENGBP-LOG v1
test_id=GBP-VIDEO-001
# --- records ---
000000 CYCU n=0 verify=1 t_adm=0 prep=00000000/00000000/ok pre=00012000/000001fa t_unmask=1010 t_post=1020 post=00012000/000021fa rec0=0
000001 CYCW n=0 polls=1 timed_out=0 t_wait_end=1030 remask=00010000/000001fa retry=0 mask_ok=1
000002 CYCD n=0 pend=0500 disc=0500 gbi=0500 b0=17 o2=01 t_read=1040 a=1/1/1/ok/0/1050/1060/2475/aabbccdd/01800000 v=1/1/1/ok/0/1070/1080/2319/01100000 ack=1/1/8500/1090
000003 CYCR n=0 pi=00010000/000001fa w1c=0 after=00010000 sticky=0 relatch=0/0 rearm=1/1/1100/1110 next=1/cause/1120/00012000/0 end=-
# --- end --- dropped=0
"""
        header, records = probelog.parse_lines(log.splitlines())
        lines = [l for l in probelog.fixture(records).splitlines() if l and not l.startswith("#")]
        self.assertEqual(lines, [])

    def test_fixture_video_admit_record(self):
        """A verify cycle's own ADMIT record carries the admission read and the PREPARE PI read."""
        log = """# OPENGBP-LOG v1
test_id=GBP-VIDEO-001
# --- records ---
000000 ADMIT n=2 t_adm=2000 remaining=500 deliveries=2 video=2 prep_intsr=00012000 prep_intmr=000001fa record=0/0
# --- end --- dropped=0
"""
        header, records = probelog.parse_lines(log.splitlines())
        lines = [l for l in probelog.fixture(records).splitlines() if l and not l.startswith("#")]
        self.assertEqual(lines, ["T 2000", "P r 00012000 000001fa"])

    def test_fixture_cleanup_ack_between_the_two_pi_reads(self):
        # The probe reads PI (CLEANUPCHK), writes INTSR once, re-reads PI (CLEANUP),
        # and only then logs the CLEANUP record: the "P a" line must sit between the
        # two "P r" lines, and must not be emitted twice.
        _, recs = probelog.parse_lines([
            "000060 PI tag=CLEANUPCHK intsr=00012000 intmr=000001fa intsr13=1 intmr13=0\n",
            "000061 PI tag=CLEANUP intsr=00010000 intmr=000001fa intsr13=0 intmr13=0\n",
            "000062 CLEANUP performed=1 value=00002000 rc=ok intsr_before=00012000 intsr_after=00010000 intsr13_after=0 sticky=0 ok=1\n",
        ])
        self.assertEqual(probelog.fixture(recs).splitlines()[1:],
                         ["P r 00012000 000001fa", "P a 00002000", "P r 00010000 000001fa"])
        _, recs = probelog.parse_lines([
            "000060 PI tag=CLEANUPCHK intsr=00010000 intmr=000001fa intsr13=0 intmr13=0\n",
            "000062 CLEANUP performed=0 intsr=00010000 intsr13=0 intmr13=0 reason=intsr13_clear\n",
        ])
        self.assertEqual(probelog.fixture(recs).splitlines()[1:], ["P r 00010000 000001fa"])

    def test_fixture_note_marks_synthetic_scripts(self):
        fx = probelog.fixture(self.records, note="SYNTHETIC: host mock, not physical data").splitlines()
        self.assertEqual(fx[1], "# SYNTHETIC: host mock, not physical data")
        self.assertEqual(fx[2], "A r 0043")
        fx = probelog.fixture(self.records, note=["a", "b"]).splitlines()
        self.assertEqual(fx[1:3], ["# a", "# b"])

    def test_check(self):
        findings, anomalies = probelog.check(self.header, self.records)
        self.assertEqual(anomalies, 1)              # the timed-out RAW
        self.assertTrue(any("mode A: 1 handshakes, 1 uniform inverse" in f for f in findings))

    def test_cli(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "x.log")
        with open(p, "w") as f:
            f.write(LOG)
        self.assertEqual(probelog.main(["fixture", p, os.path.join(d, "x.gbpreplay")]), 0)
        self.assertTrue(os.path.getsize(os.path.join(d, "x.gbpreplay")) > 0)
        self.assertEqual(probelog.main(["fixture", p, os.path.join(d, "y.gbpreplay"), "--note", "SYNTHETIC test"]), 0)
        with open(os.path.join(d, "y.gbpreplay")) as f:
            self.assertEqual(f.read().splitlines()[1], "# SYNTHETIC test")
        self.assertEqual(probelog.main(["check", p]), 1)


if __name__ == "__main__":
    unittest.main()
