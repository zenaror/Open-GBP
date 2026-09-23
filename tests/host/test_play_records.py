"""
tests/host/test_play_records.py — GitHub Issue #39: the records of the playable
image (`play-0001`) agree with each other and with the artifact.

INPUT_PATH.md §13, UNKNOWNS U-GBP-035, the HANDOFF (state block, build table,
next action, trail, do-not-assume, Swiss note), ROADMAP Phase 5 and the DEVLOG
carry the same identity, the same bounds and the same caveats; when the image
is built on this host at the recorded commit, build-info agrees with them.
Nothing frozen moved: §V7.1–§V7.5, EVIDENCE.md, the run numbers.
"""
import os
import re
import subprocess
import unittest

import guards

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INPUT_PATH = os.path.join(ROOT, "docs", "research", "INPUT_PATH.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
ROADMAP = os.path.join(ROOT, "docs", "ROADMAP.md")
DEVLOG = os.path.join(ROOT, "docs", "research", "DEVLOG.md")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
PLAY_MAIN = os.path.join(ROOT, "poc", "gbp-play-session", "source", "main.c")
BUILD_INFO = os.path.join(ROOT, "build", "poc", "gbp-play-session", "build-info.txt")
COMMIT = "2e48ca7"
SHA = "d0ee3c29d04254d1b86d4f006291008876b5e886e07280d0421b7c1161c499de"
SIZE = "487 968"
BASE = "3e6aad1"      # origin/main before Issue #39


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "")


def section13():
    t = read(INPUT_PATH)
    i = t.index("## 13. The playable image")
    j = t.find("\n## 14.", i)
    return t[i:] if j < 0 else t[i:j]


class TheIdentityIsOneEverywhere(unittest.TestCase):
    def test_the_records_name_the_same_build(self):
        for path in (INPUT_PATH, HANDOFF, ROADMAP, DEVLOG):
            t = read(path)
            self.assertIn(COMMIT, t, path)
            self.assertIn("play-0001", t, path)
        for path in (INPUT_PATH, HANDOFF, DEVLOG):
            self.assertIn(SHA, read(path), path)
            self.assertIn(SIZE, plain(read(path)), path)
        self.assertRegex(read(HANDOFF), r"\| \*\*GBP-PLAY-001 / the playable image \(Issue #39\)\*\* \| `play-0001` \| `%s` \| `%s` \| \*\*NOT PHYSICALLY EXECUTED" % (COMMIT, SHA))

    @unittest.skipUnless(os.path.isfile(BUILD_INFO), "run `make build` first")
    def test_the_built_artifact_if_at_the_recorded_commit_is_the_recorded_one(self):
        info = dict(l.split("=", 1) for l in read(BUILD_INFO).splitlines() if "=" in l)
        if info.get("commit") != COMMIT:
            self.skipTest("the play image on this host is built at %s, the recorded identity is %s's" % (info.get("commit"), COMMIT))
        self.assertEqual(info["sha256_dol"], SHA)
        self.assertEqual(str(os.path.getsize(os.path.join(ROOT, "build", "poc", "gbp-play-session", "gbp-play-session.dol"))), SIZE.replace(" ", ""))


class TheRecordsSayWhatTheImageIs(unittest.TestCase):
    def test_section_13(self):
        s = plain(section13())
        for tok in ("BUILT, NOT RUN (GitHub Issue #39, 2026-09-21)", "Nothing here has run on hardware",
                    "NOT PHYSICALLY EXECUTED; no run name reserved; nothing pre-registered; nothing staged",
                    "the pump slot never runs -- the input path, the KEY record, the presentation of a real frame and the session end are NOT exercised in Dolphin",
                    "keylog_emit() and input_step() are the TEXT of stream-0015's",
                    "why \"unchanged\" is a statement about behaviour, not bytes", "gbp_vdisp_take", "first_real", "the take ordinal tex_seq",
                    "Z, held continuously for PLAY_SESSION_END_HOLD_MS = 250 ms", "THE ONLY SUCCESS", "APPENDED to their enums, never inserted",
                    "PLAY_SAFETY_SECONDS 720 s", "PLAY_FRAME_RECORDS 45056", "754 s at 59.727 Hz > 720 s", "+5 505 024 B", "+786 432 B",
                    "LOG_LINES / reserve 8192 / 640", "462 lines after the last KEY line in RUN 17", "+1 835 008 B",
                    "The shorter service pass — stated, not assumed benign", "min 5, mean 70, max 1 547 ticks", "0.12 / 1.73 / 38.2 µs",
                    "stream-0003 (RUN 3, real cartridge video on screen) and stream-0004 (RUN 4)", "has NOT run",
                    "it is the first run of the image itself", "the image's timing is UNCHECKED",
                    "A finding about stream-0015, recorded, not acted on", "U-GBP-035",
                    "No run; no pre-registration; no game chosen"):
            self.assertIn(tok, s, tok)
        # the memory arithmetic in the section is consistent
        self.assertEqual(8847360 + 98304 + 1843200 + 262144, 11051008)
        self.assertEqual(5505024 + 786432 + 1835008, 8126464)
        self.assertIn("8 126 464 B", s)

    def test_the_unknown_and_the_other_records(self):
        u = plain(read(UNKNOWNS))
        self.assertIn("### U-GBP-035 — how does the presentation path behave over a long real-content session", u)
        self.assertIn("OPEN (opened 2026-09-21, Issue #39; no instrument yet; not blocking)", u)
        self.assertIn("no run of play-0001 should be read as answering it", u)
        h = plain(read(HANDOFF))
        for tok in ("ISSUE #39 (the playable image): BUILT, NOT RUN", "issue 39 THE PLAYABLE IMAGE BUILT, NOT RUN",
                    # the trail's `next` line is orchestrator-owned and moves every checkpoint (Issue #41 moved it):
                    # the durable pin is the trail entry itself, above
                    "That play-0001 has run, or that its timing was checked",
                    "That stop=session_end is anything but the only success of a play session",
                    "That the disposition question is answered for a long session", # Hardware Issue #43 staged it on 2026-09-21; what the section must still say is the RULE
                    "a code checkpoint never exports; staging is a HARDWARE Issue's step",
                    "Stage one slot, never the tree"):
            self.assertIn(tok, h, tok)
        r = plain(read(ROADMAP))
        self.assertIn("The image for the acceptance run — built, not run (GitHub Issue #39, 2026-09-21)", r)
        self.assertIn("unchecked until its first run", r)
        d = read(DEVLOG)
        e = plain(d[d.rindex("## 2026-09-21 — Issue #39"):])
        for tok in ("the playable image BUILT, NOT RUN", "unchecked until the first run", "No run, no pre-registration, no game, nothing staged"):
            self.assertIn(tok, e, tok)

    def test_the_source_agrees_with_the_records(self):
        p = read(PLAY_MAIN)
        for tok in ("#define PLAY_SAFETY_SECONDS      720u", "#define PLAY_FRAME_RECORDS       45056u", "#define PLAY_EVENT_RECORDS       16384u",
                    "#define PLAY_MAX_DELIVERIES      6000000u", "#define PLAY_SESSION_END_HOLD_MS 250u", "#define LOG_LINES 8192", "#define KEYLOG_TAIL_RESERVE 640u"):
            self.assertIn(tok, p, tok)


class NothingFrozenMoved(unittest.TestCase):
    def test_hardware_tests_evidence_and_the_run_numbers(self):
        if not guards.base_available(BASE):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE)
        changed = guards.changed_since(BASE, ["docs/research/HARDWARE_TESTS.md", "docs/research/EVIDENCE.md", "docs/protocol", "docs/hardware", "captures/fixtures", "stimulus"])   # Issue #29: tracked AND untracked, one implementation
        # Issue #65 (2026-09-22) BUILT stimulus/agb-tone (tone-0001), §V9's two-frequency stimulus: a new
        # stimulus ROM beside the four the family already had. It touches no runtime path, no image and no
        # slot; §V9.14 records its identity and tests/host/test_agb_tone.py runs its own code on the host.
        changed = changed - {"stimulus/agb-tone/Makefile", "stimulus/agb-tone/source/main.c"}
        # Issue #70 (2026-09-22) BUILT stimulus/agb-sweep (sweep-0001), §V11's TWO-AXIS stimulus: a new
        # stimulus ROM beside the five the family now has, and agb-tone is NOT touched (a test pins it
        # byte-identical). It touches no runtime path, no image and no slot; §V11.15 records its
        # identity and tests/host/test_agb_sweep.py runs its own code on the host.
        changed = changed - {"stimulus/agb-sweep/Makefile", "stimulus/agb-sweep/source/main.c"}
        # Issue #64 (2026-09-22) pre-registered agb-tone (§V9) and made its constructions executable BEFORE
        # the ROM exists: tools/v9tone.py is exercised on SYNTHETIC vectors only, reads no run, authorises
        # nothing and promotes nothing.
        changed = changed - {"tools/v9tone.py"}
        # Issue #69 (2026-09-22) pre-registered the amplitude sweep (§V11) and froze its constructions
        # BEFORE stimulus/agb-sweep exists: tools/v11sweep.py runs on SYNTHETIC vectors only, reads no
        # run, authorises nothing and promotes nothing. It is the fourth outing of the same discipline.
        changed = changed - {"tools/v11sweep.py"}
        # Issue #74 (2026-09-23) added tools/geckorx.py, the HOST receiver for the Operator's Pico
        # Gecko. It reads a serial port and writes bytes to a file; it touches no image, no POC and
        # no runtime path, and CLAUDE.md §14 forbids anything coming to depend on the device.
        changed = changed - {"tools/geckorx.py"}
        # Issue #75 (2026-09-23) pre-registered U-GBP-038's separator (§V13) and froze its
        # construction BEFORE the run: tools/v13sep.py runs on SYNTHETIC vectors only, borrows
        # v11sweep's classifier unchanged, reads no run and authorises nothing.
        changed = changed - {"tools/v13sep.py"}
        # §V14 (2026-09-23) froze the METHOD of RUN 34's measurement before the run:
        # tools/v14repeat.py contains no gate, reproduces §V11.16.7 exactly, reads no run.
        changed = changed - {"tools/v14repeat.py"}
        # Issue #62 (2026-09-22) ingested RUN 30 and needed two READERS that did not exist: awinparse.py,
        # a strict parser for the OGBPAW1 sidecar, and tprime.py, §V7.9's decision rule. Both only read and
        # report; the VERDICT constructions stay in tools/v8audio.py, which tests/host/test_run30.py diffs
        # against the commit that wrote it.
        changed = changed - {"tools/awinparse.py", "tools/tprime.py"}
        # Issue #46 (2026-09-22) promoted the CONTROL bit 0x02 split as GBP-HW-272: the evidence entry, the REGISTERS.md
        # row that now separates the references' USAGE (C) from this project's measurement (F) from the cause (H), and
        # U-GBP-017's Needs list, which records one of its three items answered and stays OPEN at P2
        changed = changed - {"docs/protocol/REGISTERS.md", "docs/research/EVIDENCE.md", "docs/research/UNKNOWNS.md"}
        # Issue #48 (2026-09-22) promoted the cartridge-sensing bits into the consolidated hardware pages:
        # the rows carried the references' usage only while the Keypad rows beside them carried their
        # hardware history, so they understated 36 runs. Statuses were COPIED from EVIDENCE, none changed.
        changed = changed - {"docs/hardware/GBS-DOL.md", "docs/hardware/ARCHITECTURE.md"}
        # Issue #41 (2026-09-21) pre-registered RUN 21 / RUN 22 as §V7.6 (tests/host/test_run21_prereg.py pins it) -- the ONLY change allowed here since: §V7.6 appended, §V7.1-§V7.5 byte-identical (that test checks it)
        self.assertTrue(changed <= {"docs/research/HARDWARE_TESTS.md"}, "frozen paths changed: " + " ".join(sorted(changed)))
        hw = read(HW)
        # the image's runs are pre-registered now; what must still hold is that NOTHING RAN and no id was minted
        self.assertIn("### V7.6 RUN 21 / RUN 22", hw)
        self.assertIn("NOT RUN / NOT AUTHORISED HERE", hw[hw.index("### V7.6 RUN 21 / RUN 22"):].splitlines()[0])
        # Issue #47 (2026-09-22) ingested RUN 23 / RUN 24 in §V7.7; the pin moves to the next unused number so it
        # goes on asserting that THIS checkpoint (the play-0001 build) executed nothing
        # Issue #64 (2026-09-22) reserved RUN 31 in §V9's pre-registration; the pin moves again to the
        # next unused number, and it still asserts what it was written to assert
        # Issue #69 (2026-09-22) reserved RUN 32 in §V11's; same move, same reason -- a RESERVED name is
        # not a run, and the pin's job is to catch a checkpoint that claims one
        # Issue #75 (2026-09-23) reserved RUN 33 in §V13's. Same move again.
        # §V14 (2026-09-23) reserved RUN 34, the repeat of §V11's sweep. And again.
        self.assertNotIn("RUN 35", hw)
        self.assertNotIn("GBP-HW-308", read(EVIDENCE))    # no evidence id minted by a build or a pre-registration
        # Issue #46 (2026-09-22) minted GBP-HW-272 from the ARCHIVE, not from a build: the sentinel moves to the
        # next free id so this guard keeps testing what it was written to test
        self.assertNotIn("GBP-PLAY-001", read(EVIDENCE))


if __name__ == "__main__":
    unittest.main()
