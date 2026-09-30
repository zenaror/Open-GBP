"""tests/host/test_gbmode_run59_ingest.py -- GitHub Issue #147 (RUN 59): the ingested readings, re-derived from the archived log by the frozen reader.

The numbers HARDWARE_TESTS.md V29.12 and GBP-HW-378 quote are recomputed here from captures/local (ignored by Git, so the test skips, with the registered reason, on a host
without the archive). The reader is the one frozen at 4d6fe06; the descriptive readings (the counts against the GBA family, the frame-close cadence) are recomputed apart from it.
"""
import hashlib
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gbmode_read as g  # noqa: E402

LOCAL = os.path.join(ROOT, "captures", "local")
RUN59 = os.path.join(LOCAL, "GBP-VIDEO-004_gbmode-0001-run59.log")
HASHES = {"": "f41971ef5a58a63106741b656a010067dd1c91a97680d9c1bddf0f87f2102369",
          "-disp.bin": "2a16140f6759a16e02034e261ca0978564f6c02e93a05afe3cc8255ac8211ba3",
          "-full.bin": "db2c85e9ec60824d5985359b30aedd32fa5e71995688afc76cd82cb1a83d6ded",
          "-idxcap.bin": "5687d3b34bf0763cb05c2625105f982231459779587e1f821e34c1466b471f3c",
          "-vi.bin": "79a97eee5ebe98fc84644028bbcd5861c7ac312ee6aa4dd3252b3145f6ae9ee7"}
DOC = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EVID = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
HZ = 40500000


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def episodes(text):
    out = []
    for m in re.finditer(r"EPISODE i=(\d+) .*open_frame=(\d+) close_frame=(\d+) t_open=([0-9a-f]+) t_close=([0-9a-f]+)", text):
        out.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4), 16), int(m.group(5), 16)))
    return out


def section(path, head):
    with open(path, encoding="utf-8") as f:
        d = f.read()
    i = d.index(head)
    j = d.find("\n### ", i + 1)
    return d[i:j if j > 0 else len(d)]


class TheArchivedLogReadsAsRecorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(RUN59):
            raise unittest.SkipTest("no local archive on this host (captures/local is ignored)")
        for suffix, want in HASHES.items():
            p = RUN59 if suffix == "" else os.path.join(LOCAL, "GBP-VIDEO-004_gbmode-0001-run59" + suffix)
            assert sha(p) == want, "captures/local's RUN 59 archive (%s) is not the recorded one (a defect in the archive, never a skip)" % (suffix or ".log")
        with open(RUN59, encoding="utf-8", errors="replace") as f:
            cls.text = f.read()
        cls.o = g.read(g.parse(cls.text), build="gbmode-0001", commit="4d6fe06")

    def test_the_gates_and_the_tokens(self):
        out = g.render(self.o)
        for tok in ("GATE identity           PASS", "GATE log_complete       PASS", "GATE control_record     PASS", "GATE gb_media_attested  PASS first at A1-500US",
                    "Q1_SERVICE    SERVICE_RAN_TO_TARGET deliveries=254649 acks=254649 rearms=254649",
                    "Q2_VIDEO      GBA_STRUCTURE closed=2403 complete=2383 incomplete=10 blocks/frame=39.98 qualified=1",
                    "Q3_AUDIO      AUDIO_COUNT_AS_GBA audio=164732 ratio=1.715",
                    "Q4_RESTORE    RESTORE_HOLDS_BIT read-back 93 against original 92 ok=1",
                    "CONTROLTOL n=14 first_site=PREUNMASK first_vote=8f exp=8e restore=1",
                    "KEYPAD        IDLE_ONLY first=1 refresh=7872",
                    "fact bit0_snapshots                 20", "fact strict_bit_snapshots_before_teardown []", "fact episodes                       59",
                    "fact witness_records                2048/2048 target_reached=1"):
            self.assertIn(tok, out, tok)

    def test_the_raw_records_the_prose_quotes(self):
        t = self.text
        for tok in ("lines=690 dropped=0 truncated=0", "commit=4d6fe06", "build_id=gbmode-0001", "CONTROL semantic orig=92 exp=8e",
                    "PREUNMASK ok=1 reason=- intsr13=1,1 intmr13=0,0 control=8f irq=0500/0500",
                    "COUNTERS unmasks=254649 deliveries=254649 acks=254649 rearms=254649", "audio=164732 video=96076/96076", "isr_w1c=254649", "control_ok=1",
                    "VSTATE end status=ok_structured_change_observed class=ok reason=- stop=witness_target_reached restore=ok", "errors=0 transport_ok=1",
                    "STREAMSRC closed=2403 complete=2383 incomplete=10 quarantined=0 anomaly=10",
                    "FRAMECAP frames=2403 complete=2393 incomplete=10", "INTERVALS 30:1,34:4,37:1,38:4,40:2393",
                    "WITQUAL policy=consecutive_structural_complete", "STREAMWIT records=2048/2048",
                    "CONTROLTOL n=14 first_site=PREUNMASK first_vote=8f exp=8e restore=1 policy=bit0x01_only",
                    "CTLW tag=RESTORE addr=01400000 semantic=92", "IRQW tag=STOP addr=01d00000 before=0400 write=8eaa",
                    "RESTORE control_restore_ok=1 irq_stop_write_ok=1 irq_stop_readback_ok=1", "arinfo_restore_ok=1",
                    "INPUT selftest=1 steps=184425 invalid=0 no_base=0 key_changes=0 attempts=7873 completed=7873 failed=0 first=1 change=0 refresh=7872"):
            self.assertIn(tok, t, tok)
        self.assertIn("episodes=59 stable=48 unstable=11", t)

    def test_every_count_is_one_frame_under_the_gba_family(self):
        base = {}
        for n in ("run16", "run17", "run18", "run23"):
            p = os.path.join(LOCAL, "GBP-VIDEO-004_stream-0015-%s.log" % n)
            if not os.path.isfile(p):
                self.skipTest("no local archive on this host (captures/local is ignored)")
            with open(p, encoding="utf-8", errors="replace") as f:
                tx = f.read()
            m = re.search(r"COUNTERS unmasks=(\d+) deliveries=(\d+) .* audio=(\d+) video=(\d+)/", tx)
            base[n] = tuple(int(x) for x in m.groups())[1:]
        lo = [min(v[i] for v in base.values()) for i in range(3)]
        hi = [max(v[i] for v in base.values()) for i in range(3)]
        m = re.search(r"COUNTERS unmasks=(\d+) deliveries=(\d+) .* audio=(\d+) video=(\d+)/", self.text)
        run59 = tuple(int(x) for x in m.groups())[1:]
        self.assertEqual(run59, (254649, 164732, 96076))
        self.assertEqual((lo, hi), ([254722, 164791, 96109], [254746, 164793, 96111]))
        for i in range(3):
            self.assertLess(run59[i], lo[i], "every count is under the four baselines'")
            self.assertLess((lo[i] - run59[i]) * 10000 // lo[i], 4, "under by 0.03-0.04 % at most, as the record says")
        self.assertEqual(lo[2] - run59[2], 33)

    def test_the_frame_close_cadence_the_prose_quotes(self):
        def fps(text):
            return {i: (c - o) / ((tc - to) / float(HZ)) for (i, o, c, to, tc) in episodes(text) if c - o >= 30}
        got = fps(self.text)
        self.assertEqual(sorted(got), [2, 3])
        self.assertEqual(round(got[2], 3), 59.729)
        self.assertEqual(round(got[3], 3), 59.722)
        for n in ("run16", "run17"):
            p = os.path.join(LOCAL, "GBP-VIDEO-004_stream-0015-%s.log" % n)
            if not os.path.isfile(p):
                self.skipTest("no local archive on this host (captures/local is ignored)")
            with open(p, encoding="utf-8", errors="replace") as f:
                for v in fps(f.read()).values():
                    self.assertTrue(59.727 <= round(v, 3) <= 59.728, v)


    def test_bit_0x80_was_set_in_every_control_read_so_the_forced_bit_was_not_varied(self):
        reads = [(m.group(1), int(m.group(2), 16)) for m in re.finditer(r"RAW ([\w-]+) idx=4 .*sem_vote=([0-9a-f]{2})", self.text)]
        before_stop = [v for (tag, v) in reads if tag != "FINAL"]
        self.assertGreater(len(before_stop), 20)
        self.assertTrue(all(v & 0x80 for v in before_stop), "a CONTROL read before the STOP word without bit 0x80: the record's limit 6 would be wrong")
        self.assertEqual(sorted(set(before_stop)), [0x8e, 0x8f, 0x92, 0x93])
        self.assertEqual([v for (tag, v) in reads if tag == "FINAL"], [0x00], "the last read, after the STOP word")
        self.assertIn("CONTROL semantic orig=92 exp=8e", self.text)

    def test_the_witness_started_one_frame_earlier(self):
        m = re.search(r"WITQUAL .* warmup_disqualified=(\d+) qualify_frame=(\d+) .* first_record_frame=(\d+)", self.text)
        self.assertEqual(tuple(int(x) for x in m.groups()), (20, 354, 355))
        self.assertEqual(2403 - 355, 2048)

    def test_the_duration_the_prose_quotes(self):
        t0 = int(re.search(r"CTLW tag=EXP .*t_after=(\d+)", self.text).group(1))
        t1 = int(re.search(r"CTLW tag=RESTORE .*t_after=(\d+)", self.text).group(1))
        self.assertAlmostEqual((t1 - t0) / float(HZ), 40.35, delta=0.02)


class TheRecordCarriesTheOperatorsWordsAndTheLimits(unittest.TestCase):
    def test_his_words_are_verbatim_in_the_section(self):
        s = section(DOC, "### V29.12 RUN 59 EXECUTED AND INGESTED")
        for w in ("Piscou uns textos do fundo no boot, mas depois exibiu normalmente a imagem do jogo. Ela aparentou estar um pouco acelerada.",
                  "Sim, reconheci",
                  "Parecia resolucao nativa do GBA, só que no formato quadrado que ela tem nativamente (acho que 3:2)",
                  "foi impressão minha", "GBI 37.48 s, the Start-up Disc 37.57 s, our DOL 37.53 s",
                  "sim, rodei a 59 antes por ser mais rapida... mas fiz o power cycle"):
            self.assertIn(w, s, w)

    def test_the_section_states_what_it_does_not_establish(self):
        s = " ".join(section(DOC, "### V29.12 RUN 59 EXECUTED AND INGESTED").split())
        for tok in ("HAND STOPWATCH figures", "never timing evidence", "does not support", "not** read into Q1-Q4",
                    "What this run does NOT establish", "What the picture is", "GB-mode audio content", "GB-mode input",
                    "DMG against CGB", "The meaning of bit `0x01`", "closure only", "were archived but **not read**"):
            self.assertIn(tok, s, tok)

    def test_the_prose_numbers_are_the_ones_the_log_gives(self):
        s = " ".join(section(DOC, "### V29.12 RUN 59 EXECUTED AND INGESTED").split())
        for tok in ("254 649", "164 732", "96 076", "59.729", "59.722", "0.03-0.04 %", "33 video blocks", "7 873 keypad writes of the idle word (the first one and 7 872 refreshes)",
                    "`qualify_frame=354`, `first_record_frame=355`", "182-632 µs", "78 (RUN 16), 31 (RUN 17), 31 (RUN 18) and 9 (RUN 23)",
                    "was ALREADY SET in this image's CONTROL byte", "NOT tested by this run", "IN THIS BOOT (one boot, not repeated)",
                    "the handheld arm of the isolating comparison proposed on Issue #147 was not done", "The isolating comparison is left open"):
            self.assertIn(tok, s, tok)
        for banned in ("Nothing is left to propose", "were not needed for this service", "Deliveries DID arrive without it", "the device accepted them"):
            self.assertNotIn(banned, s, banned)

    def test_the_evidence_entry_does_not_promote(self):
        e = " ".join(section(EVID, "### GBP-HW-378 ").split())
        for tok in ("promotes nothing into `docs/hardware/` or `docs/protocol/`", "FACT (the readings, one boot", "OPERATOR OBSERVATION", "never timing evidence"):
            self.assertIn(tok, e, tok)


if __name__ == "__main__":
    unittest.main()
