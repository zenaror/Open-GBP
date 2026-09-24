"""tests/host/test_run36.py -- GitHub Issue #90: RUN 36 (AOUT-HW-001) ingested.

What PLAYED is recomputed from the console's own log (versioned byte for byte as
captures/fixtures/hw-gamecube-gbp-2026-09-23-aout-0002-run36.log) against the
sealed order (aout_order.h, §V21.6). The CLASS is recomputed by applying §V21.5's
first-match order to the inputs §V21.9 records, so the verdict is derived, never
quoted. What was HEARD is OPERATOR OBSERVATION and lives only in the documents;
this file checks that they say so, and say when each word was given.

The live Gecko capture lives under captures/local/ (ignored), so its checks skip
in a clone; everything else runs everywhere.
"""
import hashlib
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
README = os.path.join(ROOT, "captures", "README.md")
ORDER_H = os.path.join(ROOT, "poc", "audio-output-replay", "source", "aout_order.h")
FIXTURE = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-23-aout-0002-run36.log")
LOCAL_LOG = os.path.join(ROOT, "captures", "local", "AOUT-HW-001_aout-0002-run36.log")
GECKO = os.path.join(ROOT, "captures", "local", "GECKO-LIVE-run36-run37-orchestrator-capture.txt")

LOG_SHA256 = "d872a889257d56276ebafd36091231371ba7ecec619d6ec0a9d8df89d04a870a"
GECKO_SHA256 = "af2d1fe29ee6b987fe06b7e51b84fabe1c3af36e25c9813a882e14a4e79c1af3"
# §V21.1: RUN 33's press windows w1..w4 carry the sweep's A schedule in this order
PRESS_HZ = (128, 512, 256, 1024)
SEGMENT_FRAMES = 48500          # 32 500 tone + 16 000 gap, 6 208 inputs through the 125/16 resampler


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def sha256(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def section():
    t = read(HW)
    i = t.index("\n### V21.9 ")
    j = t.find("\n### V21.10 ", i + 1)
    k = t.find("\n## V", i + 1)
    ends = [x for x in (j, k) if x >= 0]
    return t[i:min(ends)] if ends else t[i:]


def evidence_entry():
    t = read(EV)
    i = t.index("\n### GBP-HW-318 ")
    j = t.find("\n### ", i + 1)
    return t[i:j] if j >= 0 else t[i:]


def sealed_order():
    m = re.search(r"AOUT_PLAY_ORDER\[4\]\s*=\s*\{([^}]*)\}", read(ORDER_H))
    return tuple(int(x) for x in m.group(1).split(","))


def plays(log_text):
    out = []
    for m in re.finditer(r"PLAY position=(\d+) window=w(\d+) expected_hz=(\d+) .*? first=(\d+) frames=(\d+) "
                         r"gap_first=(\d+) gap_frames=(\d+)", log_text):
        out.append(tuple(int(x) for x in m.groups()))
    return out


def relations(hz):
    return tuple("down" if b < a else "up" for a, b in zip(hz, hz[1:]))


# §V21.9.4: the ONE reading between his words and the verdict -- each word against the one before.
# "Normal" is the first tone's name and has no relation of its own; it is ranked between the two others
# only so that the word after it can be compared with it.
WORD_RANK = {"grave": 0, "normal": 1, "agudo": 2}


def read_words(words):
    r = [WORD_RANK[w.lower()] for w in words.split()]
    return tuple("down" if b < a else "up" for a, b in zip(r, r[1:]))


def classify(refused, counter_advanced, heard_anything, count, rel, expected):
    """§V21.5, in order, first match wins."""
    if refused or not counter_advanced:
        return "INCONCLUSIVE"
    if not heard_anything:
        return "SILENT"
    if count == 4 and tuple(rel) == tuple(expected):
        return "PASS"
    if count == 4:
        return "PITCHES-ORDER"
    if count in (2, 3):
        return "PITCHES-MERGED"
    return "PITCHES-NONE"


class WhatPlayed(unittest.TestCase):
    def test_the_fixture_is_the_raw_log_byte_for_byte(self):
        self.assertEqual(sha256(FIXTURE), LOG_SHA256)
        self.assertEqual(os.path.getsize(FIXTURE), 1371)

    def test_the_archived_copy_has_not_diverged(self):
        if not os.path.exists(LOCAL_LOG):
            self.skipTest("RUN 36's archived copy is not in this checkout (captures/local is ignored)")
        self.assertEqual(sha256(LOCAL_LOG), LOG_SHA256, "the archived copy and the fixture diverged")

    def test_the_log_names_the_build_and_touched_no_gbp(self):
        t = read(FIXTURE)
        for tok in ("test_id=AOUT-HW-001", "build_id=aout-0002", "commit=28cbb97", "gbp_touched=0",
                    "lines=9 dropped=0 truncated=0",
                    "ALISTEN rc=0 crc=d3dbd9a6 windows=5 tones=4 in=24832 frames=194000 blocks=640 lost=0 overflow=0 "
                    "seq_chunks=25 cycle_chunks=33",
                    "AOUTRUN dma_irqs=95 passes=2"):
            self.assertIn(tok, t, tok)

    def test_the_play_lines_are_the_sealed_order(self):
        order = sealed_order()
        p = plays(read(FIXTURE))
        self.assertEqual([x[0] for x in p], [1, 2, 3, 4])
        for pos, window, hz, first, frames, gap_first, gap_frames in p:
            src = order[pos - 1]
            self.assertEqual(window, src + 1)
            self.assertEqual(hz, PRESS_HZ[src])
            # whole segments, back to back from frame 0 (gbp_alisten_permute)
            self.assertEqual(first, (pos - 1) * SEGMENT_FRAMES)
            self.assertEqual((frames, gap_first - first, gap_frames), (32500, 32500, 16000))
        self.assertEqual(tuple(x[2] for x in p), (1024, 256, 512, 128))

    def test_the_expected_relations_follow_from_the_log_and_equal_the_seal(self):
        rel = relations([x[2] for x in plays(read(FIXTURE))])
        self.assertEqual(rel, ("down", "up", "down"))
        seal = read(HW)[read(HW).index("\n### V21.6 "):read(HW).index("\n### V21.7 ")]
        self.assertIn("expected       relations, positions 2, 3, 4 against the one before: down, up, down", seal)


class TheClassIsDerived(unittest.TestCase):
    EXPECTED = ("down", "up", "down")

    def test_the_four_words_read_one_way(self):
        self.assertEqual(read_words("Normal Grave agudo grave"), self.EXPECTED)

    def test_section_V21_5_gives_PASS_on_the_clean_report(self):
        rel = read_words("Normal Grave agudo grave")
        self.assertEqual(classify(False, True, True, 4, rel, self.EXPECTED), "PASS")

    def test_the_told_pattern_replayed_would_not_have_passed(self):
        # §V21.9.5: up, down, up was the only pattern he had been given; replaying it is PITCHES-ORDER
        self.assertEqual(classify(False, True, True, 4, ("up", "down", "up"), self.EXPECTED), "PITCHES-ORDER")
        self.assertTrue(all(a != b for a, b in zip(("up", "down", "up"), self.EXPECTED)))

    def test_boot_1_alone_would_have_been_inconclusive(self):
        self.assertEqual(classify(True, False, False, 0, (), self.EXPECTED), "INCONCLUSIVE")

    def test_absolute_labels_would_be_wrong_about_3_against_1(self):
        # §V21.9.6: "agudo" (tone 3, 512 Hz) against "Normal" (tone 1, 1024 Hz)
        hz = [x[2] for x in plays(read(FIXTURE))]
        self.assertGreater(WORD_RANK["agudo"], WORD_RANK["normal"])
        self.assertLess(hz[2], hz[0])


class TheLiveGeckoCapture(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(GECKO):
            self.skipTest("the RUN 36/37 Gecko capture is not archived in this checkout")
        with open(GECKO, "rb") as f:
            self.raw = f.read()
        self.lines = [l.decode("ascii", "replace") for l in self.raw.split(b"\n")]

    def test_identity_and_counts(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), GECKO_SHA256)
        self.assertEqual(len(self.raw), 7668)
        self.assertEqual(sum(1 for l in self.lines if l.startswith("OPENGBP-AOUT")), 14)
        self.assertEqual(sum(1 for l in self.lines if l.startswith("OPENGBP-DRAIN")), 10)

    def test_the_play_order_never_reached_it(self):
        self.assertFalse(any(re.search(r"position=|window=|expected_hz", l) for l in self.lines))

    def test_two_boots_the_first_refused_the_second_played_three_passes(self):
        a = [l for l in self.lines if l.startswith("OPENGBP-AOUT")]
        self.assertEqual(sum(1 for l in a if l.startswith("OPENGBP-AOUT READY")), 2)
        self.assertTrue(all("build=aout-0002 commit=28cbb97" in l for l in a if "READY" in l))
        self.assertEqual(a[1], "OPENGBP-AOUT FIXTURE rc=-2 sd:/open-gbp/aout/run33-audio.bin not found on the card")
        self.assertEqual(a[2], "OPENGBP-AOUT REFUSED got=-2 build_rc=0 crc=00000000 tones=0")
        boot2 = a[a.index("OPENGBP-AOUT DONE") + 1:]
        self.assertEqual(boot2[1:], [
            "OPENGBP-AOUT FIXTURE rc=5243788 read 5243788 bytes from sd:/open-gbp/aout/run33-audio.bin",
            "OPENGBP-AOUT BUILT rc=0 crc=d3dbd9a6 tones=4 frames=194000 chunks=25",
            "OPENGBP-AOUT PLAYING",
            "OPENGBP-AOUT PASS 1 dma_irqs=34",
            "OPENGBP-AOUT PASS 2 dma_irqs=67",
            "OPENGBP-AOUT SAVELOG rc=0 path=sd:/open-gbp/AOUT-HW-001_aout-0002.log",
            "OPENGBP-AOUT PASS 3 dma_irqs=100",
            "OPENGBP-AOUT STOPPED dma_irqs=103 passes=3",
            "OPENGBP-AOUT DONE"])
        # the log's own count at the X press sits between the Gecko's PASS 2 and PASS 3, where SAVELOG is
        at_save = int(re.search(r"AOUTRUN dma_irqs=(\d+) passes=2", read(FIXTURE)).group(1))
        p2, p3 = (int(re.search(r"dma_irqs=(\d+)", l).group(1)) for l in boot2 if " PASS 2 " in l or " PASS 3 " in l)
        self.assertLess(p2, at_save)
        self.assertLess(at_save, p3)


class TheRecordSaysWhatItIs(unittest.TestCase):
    def test_scope_comes_before_the_verdict(self):
        s = plain(section())
        self.assertLess(s.index("SCOPE, stated before the verdict"), s.index("Class: PASS"))
        for tok in ("It is not Phase 6's acceptance", "the audio works", "absolute pitch"):
            self.assertIn(tok, s, tok)

    def test_the_timeline_and_which_answer_governs(self):
        s = plain(section())
        for tok in ("00:06:11.547Z", "00:11:32.427Z", "00:20:03.146Z", "00:20:47.554Z", "00:22:11.007Z",
                    "00:22:26.364Z", "00:23:11.433Z", "The class rests on the 00:20:03.146Z report",
                    "POST-EXPOSURE confirmation", "no independent weight", "That is a READING",
                    "pelo menos na minha percepção foi assim", "apaguei o bin sem querer"):
            self.assertIn(tok, s, tok)

    def test_relations_not_absolute_pitch_and_what_stays_open(self):
        s = plain(section())
        for tok in ("never absolute-pitch agreement", "U-GBP-012 is untouched by this run",
                    "not by the medium", "Pending: hash 16-aout/boot.dol, 15-drain/boot.dol",
                    "It cannot support anything about RUN 37's phases"):
            self.assertIn(tok, s, tok)

    def test_the_evidence_entry_keeps_the_perception_where_it_belongs(self):
        e = plain(evidence_entry())
        self.assertIn("FACT (what played: log + Gecko) + OPERATOR OBSERVATION (what was heard)", e)
        for tok in ("The perception stays OPERATOR OBSERVATION, and is not promoted", "1024, 256, 512, 128 Hz",
                    "post-exposure confirmation", "Relations, never absolute pitch", "U-GBP-012 is untouched",
                    "not by the medium"):
            self.assertIn(tok, e, tok)

    def test_the_fixture_is_listed(self):
        self.assertIn("hw-gamecube-gbp-2026-09-23-aout-0002-run36.log", read(README))


if __name__ == "__main__":
    unittest.main()
