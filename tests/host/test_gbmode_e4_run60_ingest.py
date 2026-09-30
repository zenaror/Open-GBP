"""tests/host/test_gbmode_e4_run60_ingest.py -- GitHub Issue #152 (RUN 60, E4): the ingested readings, re-derived from the archived drop by the frozen readers.

The numbers HARDWARE_TESTS.md V30.11 and GBP-HW-380 quote are recomputed from captures/local (ignored by Git; those tests skip, with the registered reason, on a host without the archive):
the reader's verdict and cells, the press times, the aligned series (which frame the change starts and ends at), the identical windows and samples against RUN 59, the widened sample and the
scale model figures. The record's printed blocks are checked equal to the tools' output, and the Operator's words verbatim.
"""
import hashlib
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gbmode_e4_read as e  # noqa: E402

LOCAL = os.path.join(ROOT, "captures", "local")
B = "GBP-VIDEO-004_gbmode-0001-run60"
HASHES = {".log": "ecb1f6b4d66d923fd9f2b4555f880e0fd4bea1e88a98ea9840e96bcd9328de3e", "-disp.bin": "688be42f2d775cb1fa2057d036a718b776be616882ab55e06a212447352fc2e7",
          "-full.bin": "0bc39cc4e9c57e639ad13b3dcc55f60eee0527b33407ca7fdb15dea224539ed8", "-idxcap.bin": "7f6bd50be574b5c657dcb322f5b667288c00e6689d3514ea8813ac5eb12ea1c9",
          "-vi.bin": "757627aa056e5023e264a6fdcb705822e35c6fcc50b6cb55ef0bd44bc5e307a6"}
GECKO = os.path.join(LOCAL, "GECKO-GBP-VIDEO-004-run60.txt")
GECKO_SHA = "f8b11c51ecb4c7715db891938bf9e8eb45c785d4493cecb81df1511e12c37da0"
DOC = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EVID = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def section(path, head):
    d = read(path)
    i = d.index(head)
    j = d.find("\n### ", i + 1)
    return d[i:j if j > 0 else len(d)]


class TheArchivedDropReadsAsRecorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = {s: os.path.join(LOCAL, B + s) for s in HASHES}
        cls.paths[".log"] = os.path.join(LOCAL, B + ".log")
        if not (all(os.path.isfile(p) for p in cls.paths.values()) and os.path.isfile(GECKO)):
            raise unittest.SkipTest("no local archive on this host (captures/local is ignored)")
        for s, p in cls.paths.items():
            assert sha(p) == HASHES[s], "captures/local's RUN 60 archive (%s) is not the recorded one (a defect in the archive, never a skip)" % s
        assert sha(GECKO) == GECKO_SHA
        import vidxcap
        cls.text = read(cls.paths[".log"])
        cls.info = vidxcap.load(cls.paths["-idxcap.bin"])
        cls.o = e.read(cls.text, cls.info, "gbmode-0001", "4d6fe06", None)
        cls.tc = int(re.search(r"t_control_transform=([0-9a-f]+)", cls.text).group(1), 16)

    def test_the_verdict_and_the_cells(self):
        o = self.o
        self.assertEqual(o["verdict"], "CHANGED")
        self.assertEqual(o["consistent_models"], ["BOTH_TOGGLE"])
        self.assertEqual({k: (d["n"], d["leak"], d["verdict"]) for k, d in o["cells"].items()},
                         {"-|after:": (19, 0, "INSUFFICIENT"), "-|after:L": (118, 118, "STRETCHED"), "-|after:LR": (1, 0, "INSUFFICIENT"), "L|after:": (68, 68, "STRETCHED"),
                          "L|after:LR": (70, 70, "STRETCHED"), "R|after:L": (107, 0, "NOT_STRETCHED")})
        self.assertEqual((o["frames"], o["legible"], o["leak_frames"], o["partial_leak_frames"], o["transition_frames"], o["stray_leak_frames"]), (2048, 577, 355, 11, 194, 110))
        self.assertEqual((o["own_baseline_legible"], o["pre_press_leak_frames"], o["expected_window_frames_after_first_press"], o["expected_window_frames_dark"]), (41, 0, 536, 0))
        self.assertEqual((o["keys_n"], o["keys_failed"], o["other_keys"]), (6, 0, []))

    def test_the_presses_in_seconds_after_the_control_transform(self):
        hz = self.info["tb_hz"]
        got = [(p["key"], round((p["t_down"] - self.tc) / float(hz), 2), None if p["t_up"] is None else round((p["t_up"] - self.tc) / float(hz), 2)) for p in self.o["presses"]]
        self.assertEqual(got, [("L", 20.44, 22.57), ("R", 29.75, 32.55), ("L", 38.22, None)])
        self.assertIn("last_word=0100", self.text)

    def test_the_timeline_of_run_59_recurs_frame_for_frame(self):
        run59 = os.path.join(LOCAL, "GBP-VIDEO-004_gbmode-0001-run59-idxcap.bin")
        if not os.path.isfile(run59):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        import vidxcap
        other = vidxcap.load(run59)

        def wins(info):
            out, cur = [], None
            for r in info["records"]:
                inbox, _lx, _ly = e.frame_stats(r["witness"])
                ok = inbox / float(e.INBOX_WORDS) >= e.LEGIBLE_MIN
                if ok and cur is None:
                    cur = [r["frame_index"], r["frame_index"]]
                elif ok:
                    cur[1] = r["frame_index"]
                elif cur:
                    out.append(tuple(cur))
                    cur = None
            return out + ([tuple(cur)] if cur else [])
        self.assertEqual(wins(self.info), wins(other))
        self.assertEqual(wins(self.info), list(e.EXPECTED_WINDOWS))

    def test_the_aligned_series(self):
        hz = self.info["tb_hz"]
        keys = e.parse_keys(self.text)
        tr = e.transitions(keys)
        ps = e.presses(tr)
        fr = [{"frame_index": r["frame_index"], "t0": r["t_first_block"], "t1": r["t_last_block"], "witness": r["witness"]} for r in self.info["records"]]
        cf = e.classify_frames(fr, tr, ps, hz)
        runs, cur = [], None
        for c in cf:
            if c["strong"]:
                cur = [c["frame_index"], c["frame_index"]] if cur is None else [cur[0], c["frame_index"]]
            elif cur:
                runs.append(tuple(cur))
                cur = None
        if cur:
            runs.append(tuple(cur))
        self.assertEqual(runs, [(1214, 1321), (1622, 1769), (2277, 2375)])
        self.assertEqual(max(c["leak_y"] for c in cf), 0, "the border rows never leak")
        self.assertEqual((min(c["leak_x"] for c in cf if c["strong"]), max(c["leak_x"] for c in cf if c["strong"])), (1393, 1404))
        byi = {c["frame_index"]: c for c in cf}
        ms = lambda i, t: round((byi[i]["t"] - t) / float(hz) * 1000, 1)  # noqa: E731
        (_, l1, _), (_, r1, _), (_, l2, _) = [(p["key"], p["t_down"], p["t_up"]) for p in self.o["presses"]]
        self.assertEqual((ms(1213, l1), ms(1214, l1)), (-8.3, 8.4))
        self.assertEqual((ms(1769, r1), ms(1770, r1)), (-8.7, 8.0))
        self.assertEqual((ms(2276, l2), ms(2277, l2)), (4.8, 21.6))
        self.assertTrue(byi[1769]["strong"] and not byi[1770]["strong"] and not byi[2276]["strong"] and byi[2277]["strong"] and not byi[1213]["strong"] and byi[1214]["strong"])

    def test_the_samples_against_run_59(self):
        import vfull
        run59 = os.path.join(LOCAL, "GBP-VIDEO-004_gbmode-0001-run59-full.bin")
        if not os.path.isfile(run59):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        a = vfull.load(run59)["records"]
        b = vfull.load(self.paths["-full.bin"])["records"]
        diff = [sum(1 for x, y in zip(vfull.consumed_words(a[i]["raw"]), vfull.consumed_words(b[i]["raw"])) if (x & 0x7FFF) != (y & 0x7FFF)) for i in range(8)]
        self.assertEqual(diff, [0, 0, 0, 0, 0, 17408, 0, 0])
        import gbmode_picture as gp
        s = gp.analyse(self.paths["-full.bin"])["frames"]
        self.assertEqual(s[5]["bbox"], (0, 8, 239, 151))
        self.assertEqual((s[5]["size"], s[5]["distinct_words"], s[5]["distinct_colours"]), ((240, 144), 21, 20))
        self.assertEqual(s[6]["bbox"], (40, 8, 199, 151))
        self.assertEqual(s[5]["scaling"]["col"]["verdict"], "NO_PERIODIC_DUPLICATION")
        pa, pb = gp.pixels(a[5]["raw"]), gp.pixels(b[5]["raw"])
        src = [[pa[y][40 + x] & 0x7FFF for x in range(160)] for y in range(8, 152)]
        dst = [[pb[y][x] & 0x7FFF for x in range(240)] for y in range(8, 152)]
        palette = set(w for row in src for w in row)
        new = [w for row in dst for w in row if w not in palette]
        self.assertEqual((len(palette), len(set(new)), len(new)), (9, 10, 2442))
        nearest = sum(1 for y in range(144) for x in range(240) if src[y][min(159, x * 160 // 240)] == dst[y][x])
        self.assertEqual(round(100.0 * nearest / (144 * 240), 1), 92.9)
        rgb = lambda w: ((w >> 10) & 31, (w >> 5) & 31, w & 31)  # noqa: E731
        exact = near = 0
        for y in range(144):
            for x in range(240):
                pos = (x + 0.5) * 160 / 240 - 0.5
                i = int(pos // 1)
                f = pos - i
                c0, c1 = rgb(src[y][max(0, min(159, i))]), rgb(src[y][max(0, min(159, i + 1))])
                c = tuple(int(round(c0[k] * (1 - f) + c1[k] * f)) for k in range(3))
                q = rgb(dst[y][x])
                exact += c == q
                near += all(abs(c[k] - q[k]) <= 1 for k in range(3))
        self.assertEqual((round(100.0 * exact / (144 * 240), 1), round(100.0 * near / (144 * 240), 1)), (85.0, 98.8))

    def test_the_frames_that_differ_from_run_59_and_the_flip_offsets(self):
        run59 = os.path.join(LOCAL, "GBP-VIDEO-004_gbmode-0001-run59-idxcap.bin")
        if not os.path.isfile(run59):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        import vidxcap
        a = vidxcap.load(run59)["records"]
        diff = [x["frame_index"] for x, y in zip(a, self.info["records"]) if [[w & 0x7FFF for w in r] for r in x["witness"]] != [[w & 0x7FFF for w in r] for r in y["witness"]]]
        runs, cur = [], None
        for f in diff:
            if cur and f == cur[1] + 1:
                cur[1] = f
            else:
                if cur:
                    runs.append(tuple(cur))
                cur = [f, f]
        runs.append(tuple(cur))
        self.assertEqual((len(diff), runs), (417, [(1214, 1321), (1454, 1515), (1622, 1769), (2277, 2375)]))
        R = {r["frame_index"]: r for r in self.info["records"]}
        hz = self.info["tb_hz"]
        att = [(int(m.group(1)), int(m.group(2), 16)) for m in re.finditer(r"KEY n=(\d+) .*t_attempt=([0-9a-f]+) t_done", self.text)]
        ta = dict(att)
        off = lambda f, n: round((R[f]["t_first_block"] - ta[n]) / float(hz) * 1000, 2)  # noqa: E731
        self.assertEqual((off(1214, 2), off(1770, 4), off(2276, 6), off(2277, 6)), (2.67, 2.29, -0.9, 15.84))
        partial = [c for c in e.classify_frames([{"frame_index": r["frame_index"], "t0": r["t_first_block"], "t1": r["t_last_block"], "witness": r["witness"]} for r in self.info["records"]],
                                               e.transitions(e.parse_keys(self.text)), e.presses(e.transitions(e.parse_keys(self.text))), hz) if c["partial"]]
        self.assertEqual((partial[0]["frame_index"], partial[-1]["frame_index"], len(partial)), (1490, 1500, 11))

    def test_the_gecko_capture_facts(self):
        d = read(GECKO)
        self.assertEqual(os.path.getsize(GECKO), 3178)
        self.assertTrue(d.rstrip().endswith("OPENGBP-STREAM DONE"))
        self.assertRegex(d, r"SAVESIDECAR .*records=2048")
        self.assertIn("Arena Size", d.split("\n", 3)[0] + d.split("\n", 3)[1] + d.split("\n", 3)[2])

    def test_the_printed_blocks_are_the_tools_output(self):
        s = section(DOC, "### V30.11 RUN 60 EXECUTED AND INGESTED")
        blocks = re.findall(r"```text\n(GBMODE [^\n]*\n.*?)\n```", s, re.S)
        self.assertEqual(len(blocks), 2)
        d = self.paths[".log"][:-4]
        out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "gbmode_e4_read.py"), self.paths[".log"], self.paths["-idxcap.bin"], "--full", self.paths["-full.bin"],
                              "--build", "gbmode-0001", "--commit", "4d6fe06"], capture_output=True, text=True).stdout.rstrip("\n")
        self.assertEqual(blocks[0], out)
        out2 = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "gbmode_read.py"), self.paths[".log"], "--build", "gbmode-0001", "--commit", "4d6fe06"], capture_output=True, text=True).stdout.rstrip("\n")
        self.assertEqual(blocks[1], out2)


class TheRecordCarriesTheOperatorsWordsAndTheLimits(unittest.TestCase):
    def test_the_prose_figures_are_the_recomputed_ones(self):
        s = " ".join(section(DOC, "### V30.11 RUN 60 EXECUTED AND INGESTED").replace("`", "").replace("**", "").split())
        for tok in ("+8.4 ms", "+21.6 ms", "-8.7 ms", "+8.0 ms", "17 408 pixels", "92.9 %", "2 442 pixels", "98.8 %", "85.0 %", "0.37 s", "2.48 s", "0.52 s", "5.67 s", "exactly 417 of the 2 048 frames",
                    "1214..1321, 1454..1515, 1622..1769 and 2277..2375", "1 631", "all 11 partial-leak frames (1490..1500)", "99 strong legible frames", "+2.67 ms and +2.29 ms", "+15.84 ms",
                    "sim e sim", "SAVESIDECAR", "21 distinct words against 11", "4.7 s after the release", "2245..2275", "the ONE legible full frame of that state (sample 5, frame 1635)"):
            self.assertIn(tok, s, tok)
        self.assertNotIn("AVESIDECAR rc", s.replace("SAVESIDECAR", ""))
        self.assertNotIn("nearly square", s)
        self.assertNotIn("Start-up Disc / GBA-mode use", s)

    def test_his_words_are_verbatim_and_not_reconciled(self):
        s = " ".join(section(DOC, "### V30.11 RUN 60 EXECUTED AND INGESTED").split())
        for w in ("mesma coisa da run anterior", "o mesmo comportamento do GBA, L estica a tela e R volta a ser quadrado", "nada a declarar... apenas que esta sem som mesmo", "sim e sim",
                  "set beside the reading AFTER it existed; neither is reconciled toward the other", "the stream image drains the AUDIO window and does not play it"):
            self.assertIn(w, s, w)

    def test_the_limits_and_the_unlisted_reading_are_stated(self):
        s = " ".join(section(DOC, "### V30.11 RUN 60 EXECUTED AND INGESTED").replace("`", "").replace("**", "").split())
        for tok in ("Toggle against set / clear", "two UNLISTED readings predict the same cells", "L twice in a row", "Who does it", "HYPOTHESIS", "The reach of the word is shown by the effect", "INFERENCE: an interpolating horizontal scale, its kernel not identified",
                    "Which text was relayed to the Operator is the Orchestrator's record, not read here"):
            self.assertIn(tok, s, tok)
        e = " ".join(section(EVID, "### GBP-HW-380 ").replace("`", "").replace("**", "").split())
        for tok in ("promotes nothing into docs/hardware/ or docs/protocol/", "FACT (the readings, one boot", "INFERENCE", "UNKNOWN (toggle against set / clear"):
            self.assertIn(tok, e, tok)


if __name__ == "__main__":
    unittest.main()
