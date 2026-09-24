"""tests/host/test_run42.py -- GitHub Issue #115: RUN 42 (GBP-AUDIO-011, game-0002, Yoshi's Island) ingested.

The verdicts are RECOMPUTED, never quoted. The console's log and its L2 record, versioned byte for byte
(captures/fixtures/hw-gamecube-gbp-2026-09-24-game-0002-run42.log and -run42-l2.bin), go through the frozen
tools/v26report.py (dc13f37) and tools/v26accept.py (f874cc6 = tools/v25accept.py at 4591f9b with V's start-up
clause replaced). Every output sealed with no declaration is reproduced to its hash, and so is every output after it,
with the declaration as the Orchestrator resolved it on #114 (-run42-declaration.json). V is checked in integers.

Two descriptive records are recomputed beside the verdicts and decide nothing: the loss rise inside L2's own
10-second keep window, in every run of the family (RUN 38-42); and the audio path's designed depth, from the units
src/audio/gbp_aplay.h declares and the ring fill the run measured.

The ingestion's text is checked against the tools and against itself (TheRecord): the printed block is the frozen
tool's output byte for byte, the closure never travels without the audio-to-video offset, and no record says more than
its evidence.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FXD = os.path.join(ROOT, "captures", "fixtures")
FX = os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-game-0002-run42")
LOG, L2, DECL = FX + ".log", FX + "-l2.bin", FX + "-declaration.json"
APLAY_H = os.path.join(ROOT, "src", "audio", "gbp_aplay.h")
APLAY_C = os.path.join(ROOT, "src", "audio", "gbp_aplay.c")
MAIN2 = os.path.join(ROOT, "poc", "gbp-audio-game2", "source", "main.c")

RAW = {LOG: ("aed7a481d879379bdb7afafe116270e9cf572d20e613294284d7e91566a2bf97", 115492),
       L2: ("45119c6f3e1ff416e8ad42434ea69bdeaff4d3d554bb3922e25fa18d2b22016d", 83208),
       DECL: ("b71071d924e4a98fbfd925b682e24685c220c5f25dff96d416d3d15d84f94837", None)}
# sealed at 1686d46 with no declaration (§V26.11)
SEALED = {"report": "1178828cbf7f5e9d80459450e501714db6dba7ccb3146585e77740a16e98899e",
          "verdicts": "06834e96eb3dfd3c7d4c26c8f1ff0440fd560e1e7e0c0d22c575e4aa0b415196",
          "accept": "e5c780c88cfcbc68cf59288a19030ed74c4770611c261416a421804159b12c3f"}
# opened with the declaration of issuecomment-5822492702 (by reference to issuecomment-5821017811)
FINAL = {"verdicts": "e996b2fb858c2bca2ac61cc73eeec595bd2ba5dd2b5243a84a5b64b1ceda405f",
         "accept": "372286fd6dccd0fe4fffd619b2efe9206cbc6eab32fa53938c9fea724116c370"}
FAMILY = {38: os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-live-0001-run38.log"),
          39: os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-trace-0001-run39.log"),
          40: os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-split-0001-run40.log"),
          41: os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-game-0001-run41.log"),
          42: LOG}


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Run(object):
    _done = None

    @classmethod
    def get(cls):
        if cls._done is None:
            with tempfile.TemporaryDirectory() as d:
                rj, aj, fj = (os.path.join(d, n) for n in ("report.json", "accept.json", "final.json"))
                subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v26report.py"), LOG, "--sidecar", L2,
                                "--json", rj], check=True, capture_output=True, timeout=300)
                sealed = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v26accept.py"), rj,
                                         "--sidecar", L2, "--json", aj], check=True, capture_output=True,
                                        timeout=300).stdout
                final = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v26accept.py"), rj,
                                        "--sidecar", L2, "--declaration", DECL, "--json", fj], check=True,
                                       capture_output=True, timeout=300).stdout
                blobs = {}
                for k, p in (("report", rj), ("accept", aj), ("final", fj)):
                    with open(p, "rb") as f:
                        blobs[k] = f.read()
            cls._done = {"blobs": blobs, "sealed": sealed, "final": final, "rep": json.loads(blobs["report"]),
                         "acc": json.loads(blobs["final"])}
        return cls._done


class TheFixtures(unittest.TestCase):
    def test_the_raws_are_the_consoles_files_byte_for_byte(self):
        for path, (h, n) in RAW.items():
            with open(path, "rb") as f:
                raw = f.read()
            self.assertEqual(sha(raw), h, path)
            if n is not None:
                self.assertEqual(len(raw), n, path)
        log = read(LOG)
        for tok in ("test=GBP-AUDIO-011 app=gbp-audio-game2 build=game-0002 commit=dc13f37",
                    "lines=881 dropped=0 truncated=0", "# --- end --- dropped=0",
                    "LIVEL2SAVE open=0 write=0 close=0 bytes=83208 status=saved",
                    "LIVEVBEFN before=14 listed=14 capped=0 cap=64", "CONTROL semantic orig=92"):
            self.assertIn(tok, log, tok)

    def test_the_declaration_is_the_orchestrators_resolution_by_reference(self):
        with open(DECL, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual((d["a_stability"], set(d["defects"].values()), d["picture"], d["controls"]),
                         ("PASS", {"no"}, "normal", "responded"))
        self.assertIn("As respostas de A até F seguem as mesmas", d["a_words"])
        self.assertIn("pelo menos do que notei", d["a_words"])
        self.assertIn("issuecomment-5822492702", d["source"])
        self.assertIn("issuecomment-5821017811", d["source"])

    def test_the_frozen_tools_reproduce_every_sealed_output_to_its_hash(self):
        r = Run.get()
        self.assertEqual(sha(r["blobs"]["report"]), SEALED["report"])
        self.assertEqual(sha(r["sealed"]), SEALED["verdicts"])
        self.assertEqual(sha(r["blobs"]["accept"]), SEALED["accept"])

    def test_and_every_output_after_the_declaration(self):
        r = Run.get()
        self.assertEqual(sha(r["final"]), FINAL["verdicts"])
        self.assertEqual(sha(r["blobs"]["final"]), FINAL["accept"])


class TheVerdicts(unittest.TestCase):
    def test_L2_C_A_PASS(self):
        a = Run.get()["acc"]
        self.assertEqual((a["L2"]["verdict"], a["L2"]["crc_kept"], a["L2"]["crc_host"], a["L2"]["frames"]),
                         ("PASS", 0x07A7632B, 0x07A7632B, 320000))
        self.assertEqual((a["C"]["verdict"], a["C"]["seconds"], a["C"]["overflow"], a["C"]["underrun"],
                          a["C"]["not_drained"]), ("PASS", 64.0, 0, 0, 465))
        self.assertEqual((a["A"]["verdict"], a["A"]["defects_yes"], a["A"]["clipped"]), ("PASS", [], 10331))

    def test_V_PASS_the_start_up_clause_in_the_familys_own_positions(self):
        v = Run.get()["acc"]["V"]
        vid = v["video"]
        self.assertEqual((v["verdict"], vid["verdict"]), ("PASS", "HOLDS"))
        self.assertEqual(vid["Q_indices"], [0, 9, 12, 15, 31, 34, 37, 91, 94, 97, 151, 154, 157])
        self.assertEqual((vid["P"]["index"], vid["bound"]), (339, 197))
        rep = Run.get()["rep"]
        p = [f for f in rep["video"]["before_frames"] if f[0] == 339][0]
        self.assertLessEqual(p[1], rep["t_press"])
        self.assertLess(rep["t_press"], p[3])
        self.assertEqual((rep["video"]["before"], rep["video"]["after"]), (14, 0))

    def test_V_rate_half_in_integers(self):
        rep = Run.get()["rep"]["video"]
        span = rep["t_ai_stop"] - rep["t_ai_start"]
        self.assertEqual((rep["inside"], span), (17, 2566726611))
        self.assertEqual((17 * 2567047476, 44 * span), (43639807092, 112935970884))
        self.assertLessEqual(17 * 2567047476, 44 * span)

    def test_phase_6_closes(self):
        p = Run.get()["acc"]["phase6"]
        self.assertEqual((p["verdict"], p["clauses_not_pass"]), ("CLOSES", []))


class TheLossRiseSitsInL2sKeepWindow(unittest.TestCase):
    """DESCRIPTIVE. L2 is armed LIVE_L2_FROM_S = 20 s into C's window and keeps 320 chunks (10 s); in every run of
    the family the lost blocks per second rise in window seconds 20-29 and fall back after."""

    def per_second_lost(self, path):
        t = read(path)
        secs = []
        for m in re.finditer(r"^\d{6} LIVESEC from=(\d+) counts=(\S+)$", t, re.M):
            secs += [int(x) for x in m.group(2).split(",")]
        self.assertRegex(t, r"l2_from_s=20 l2_chunks=320 ")
        return [4096 - c for c in secs[:64]]

    def test_every_run_loses_more_inside_the_window(self):
        got = {}
        for n, p in FAMILY.items():
            lost = self.per_second_lost(p)
            got[n] = (sum(lost[20:30]), sum(lost[:20]) + sum(lost[30:]))
        self.assertEqual(got, {38: (303, 1323), 39: (312, 1471), 40: (254, 963), 41: (163, 320), 42: (166, 299)})
        for n, (inside, outside) in got.items():
            self.assertGreater(inside * 54, outside * 10, n)            # a higher rate inside, in integers

    def test_on_the_8_push_runtime_the_ranges_separate_in_run_42_and_meet_in_run_41(self):
        got = {}
        for n in (41, 42):
            lost = self.per_second_lost(FAMILY[n])
            got[n] = (min(lost[20:30]), max(lost[:20] + lost[30:]))
        self.assertEqual(got, {41: (11, 11), 42: (11, 10)})             # strict in RUN 42 only

    def test_the_whole_window_against_the_54_s_outside(self):
        lost = self.per_second_lost(LOG)
        self.assertEqual((sum(lost), sum(lost[:20]) + sum(lost[30:])), (465, 299))
        self.assertEqual(Run.get()["acc"]["C"]["not_drained"], sum(lost))

    def test_the_window_is_where_the_chain_crcs_every_handed_chunk(self):
        src = read(APLAY_C)
        self.assertIn("p->l2.crc = gbp_aplay_crc_update(p->l2.crc, chunk(p, buf), GBP_APLAY_CHUNK_BYTES);", src)
        self.assertIn("for (i = 0; i < n; i++) state = crc_table[(state ^ data[i]) & 0xFFu] ^ (state >> 8);", src)
        self.assertRegex(read(MAIN2), r"#define LIVE_L2_FROM_S\s+20u")


class TheAudioPathsDepthInItsOwnUnits(unittest.TestCase):
    """DESCRIPTIVE, for U-GBP-046: the units are src/audio/gbp_aplay.h's; the ring fill is the run's own LIVEFILL."""

    def test_the_units(self):
        h = read(APLAY_H)
        self.assertIn("holding DECODED int16 samples,\n * one per AUDIO block", h)
        for tok in ("#define GBP_APLAY_RING          4096u", "#define GBP_APLAY_TARGET        2048u",
                    "#define GBP_APLAY_AHEAD            4u", "#define GBP_APLAY_PUSHES         128u",
                    "#define GBP_APLAY_FRAMES        1000u"):
            self.assertIn(tok, h, tok)
        self.assertIn("the callback programs block k while\n * k-1 plays", h)
        self.assertIn("LIVECFG2 ring=4096 target=2048 band=16 chunk_frames=1000 chunk_bytes=4000 pool=16 ahead=4",
                      read(LOG))

    def test_the_measured_ring_fill(self):
        fill = Run.get()["rep"]["window"]["fill"]
        self.assertEqual(fill[0], 0)                                     # before the AI starts
        f = fill[1:]
        self.assertEqual((len(f), min(f), max(f), sum(f)), (63, 1893, 2028, 123908))


HT = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UN = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
ROADMAP = os.path.join(ROOT, "docs", "ROADMAP.md")
README = os.path.join(ROOT, "captures", "README.md")


def flat(t):
    return " ".join(t.split())


def between(t, a, b):
    i = t.index(a)
    return t[i:t.index(b, i)]


class TheReadmeRows(unittest.TestCase):
    def test_the_readme_rows(self):
        rd = read(README)
        for suffix, tok in ((".log", "115 492 B, sha256 `aed7a481…a2bf97`"),
                            ("-l2.bin", "83 208 B, sha256 `45119c6f…22016d`"),
                            ("-declaration.json", "`issuecomment-5822492702`")):
            row = [ln for ln in rd.splitlines()
                   if ln.startswith("| `hw-gamecube-gbp-2026-09-24-game-0002-run42%s` |" % suffix)]
            self.assertEqual(len(row), 1, suffix)
            self.assertIn(tok, row[0], suffix)
            self.assertIn("`tests/host/test_run42.py`", row[0], suffix)
        self.assertEqual(RAW[LOG][0][:8] + "…" + RAW[LOG][0][-6:], "aed7a481…a2bf97")
        self.assertEqual(RAW[L2][0][:8] + "…" + RAW[L2][0][-6:], "45119c6f…22016d")


class TheRecord(unittest.TestCase):
    """The ingestion's text against the tools and against itself: the printed block is the tool's, the closure never
    travels without the offset, and no record says more than its evidence."""

    def v2611(self):
        t = read(HT)
        t = t[t.index("### V26.11 RUN 42"):]
        nl = t.index("\n") + 1
        m = re.search(r"^#{1,3} ", t[nl:], re.M)                     # the next heading at or above ###, if any
        return t if m is None else t[:nl + m.start()]

    def test_the_sections_in_order(self):
        t = self.v2611()
        heads = re.findall(r"^#### V26\.11\.(\d+) ", t, re.M)
        self.assertEqual(heads[:8], [str(i) for i in range(8)])
        self.assertEqual(heads, [str(i) for i in range(len(heads))])   # later Issues append on top, in order

    def test_the_printed_block_is_the_frozen_tools_output_byte_for_byte(self):
        sec = between(self.v2611(), "#### V26.11.3", "**V in its own terms.**")
        blk = re.search(r"```text\n(.*?)```", sec, re.S).group(1)
        self.assertEqual(blk, Run.get()["final"].decode("utf-8"))
        self.assertEqual(sha(blk.encode("utf-8")), FINAL["verdicts"])

    def test_after_is_quoted_from_the_json_and_the_log_and_the_gap_carried_forward(self):
        sec = flat(between(self.v2611(), "#### V26.11.3", "#### V26.11.4"))
        self.assertIn("000860 LIVEVINC ai=1 before=14 inside=17 after=0 stored=31 framecap=31", sec)
        self.assertIn("000860 LIVEVINC ai=1 before=14 inside=17 after=0 stored=31 framecap=31", read(LOG))
        self.assertEqual(Run.get()["rep"]["video"]["after"], 0)
        self.assertIn("none after", Run.get()["acc"]["V"]["video"]["why"])
        self.assertNotIn("after", Run.get()["final"].decode("utf-8").split("video: ", 1)[1].split("\n", 1)[0]
                         .replace("E outside", ""))                      # the gap: the printed line never shows it
        self.assertIn("every input a gate depends on appears in the PRINTED verdict", sec)
        self.assertIn('if v["after"] != 0', read(os.path.join(ROOT, "tools", "v26accept.py")))

    def test_the_closure_never_travels_without_the_offset(self):
        para = flat(between(self.v2611(), "`docs/ROADMAP.md`'s Phase 6 criterion", "#### V26.11.5"))
        self.assertIn("**Phase 6 closes on stable gameplay audio that carries an audio-path depth of about half a "
                      "second", para)
        self.assertTrue("GBI" in para and "Start-up Disc" in para)

    def test_the_depth_accounts_for_most_never_explains(self):
        docs = {n: flat(read(p)) for n, p in (("HT", HT), ("EV", EV), ("UN", UN))}
        self.assertIn("**In size it accounts for MOST of his estimate, not all of it.**",
                      flat(between(self.v2611(), "#### V26.11.5", "#### V26.11.6")))
        self.assertIn("The unaccounted residue is named, not absorbed.", docs["UN"])
        self.assertIn("It accounts for most of his \"próximo de 1 segundo\", not all of it; the residue is "
                      "unaccounted.", docs["EV"])
        for n, t in docs.items():
            self.assertNotRegex(t, r"(?i)explains? (?:his|the Operator's) (?:~?1 s|estimate|second)", n)

    def test_the_rise_names_its_class_and_its_refutation(self):
        sec = flat(between(self.v2611(), "#### V26.11.6", "#### V26.11.7"))
        ev = flat(between(read(EV), "### GBP-HW-338", "One console, one Game Boy Player, five runs."))
        for t in (sec, ev):
            self.assertIn("*the instrument perturbed the subject, and the perturbation was then attributed to the "
                          "subject", t)
            self.assertIn("RUN 38–40", t)
        self.assertIn("in RUN 41 the two ranges meet", ev)
        self.assertNotIn("do not overlap", ev)
        self.assertNotIn("do not even overlap", sec)

    def test_the_statuses(self):
        ev = read(EV)
        h337 = re.search(r"^### GBP-HW-337 .*$", ev, re.M).group(0)
        for tok in ("**Phase 6 closes**", "FACT (the frozen gates' results and counts, one run)",
                    "A and the offset are OPERATOR OBSERVATIONS", "the offset's cause is a HYPOTHESIS"):
            self.assertIn(tok, h337, tok)
        h338 = re.search(r"^### GBP-HW-338 .*$", ev, re.M).group(0)
        self.assertIn("FACT (counts over five archived runs, recomputable)", h338)
        self.assertIn("the cause is a HYPOTHESIS", h338)
        self.assertIn("**CORRECTED 2026-09-24 (GitHub Issue #115, RUN 42), on top; nothing above is rewritten.**",
                      between(ev, "### GBP-HW-336", "### GBP-HW-337"))
        un = read(UN)
        u46 = between(un, "## U-GBP-046 ", "input-and-video responsiveness OPERATOR OBSERVATION")
        for tok in ("**The status is HYPOTHESIS.**", "**What would refute it:**", "**No measured offset\n  exists.**"):
            self.assertIn(tok, u46, tok)

    def test_the_flat_copies_are_canonical(self):
        self.assertIn("canonical  the FLAT copies below; the earlier captures/local/run42/ duplicates were "
                      "cmp-checked and removed", self.v2611())

    def test_the_roadmap_carries_the_closure_and_the_offset_in_one_paragraph(self):
        body = between(read(ROADMAP), "## Phase 6 — Audio", "Implement and document").split("\n", 1)[1].strip()
        self.assertNotIn("\n\n", body)                                   # ONE paragraph
        para = flat(body)
        self.assertTrue(para.startswith("**Status: CLOSED 2026-09-24 (GitHub Issue #115, RUN 42"))
        for tok in ("GBI", "Start-up Disc", "próximo de 1 segundo", "accounts for most of that estimate, not all of "
                    "it; the residue is unaccounted", "U-GBP-046", "U-GBP-045"):
            self.assertIn(tok, para, tok)
        self.assertIn("A real cartridge produces stable audio without breaking video/input.", read(ROADMAP))


if __name__ == "__main__":
    unittest.main()
