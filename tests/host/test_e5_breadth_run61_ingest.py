"""tests/host/test_e5_breadth_run61_ingest.py -- GitHub Issue #155 (Hardware Issue #154): RUN 61 / RUN 62 / RUN 63, GBP-BREADTH-001 on vehicle-0001, ingested.

What is held here, each checked, not assumed:
  * THE ARCHIVE is the recorded one (sha256 pinned; a mismatch is a defect, never a skip) and equals the Operator's raw originals where they are on this host.
  * THE FROZEN READER'S OUTPUT is the record's, byte for byte: tools/playread.py is run AS IT STOOD at 18f9eb8 (extracted from git with the tools it imports), so the
    forward-only repair of Issue #156 cannot break this test and cannot rewrite what the frozen instrument said (`CAPTURE: FAIL` included).
  * THE CAPTURE MECHANISM: every figure of HARDWARE_TESTS.md V31.10's table is recomputed from the logs (whole-session and per-phase taps / blocks_in, the pre-origin
    window in seconds, the first A press -> origin, the zero-loss counters), and the same whole-session inequality is re-read in RUN 54-58's archived logs.
  * THE CODE FACTS the record cites (tools/playread.py:105; poc/gbp-play-gba/source/main.c:373, :469, :1011) are read at 18f9eb8.
  * THE GATES: loss per phase in the band, the underrun split, ENVMEM, the stores, the service gate, CARTDECL, gecko=0.
  * THE RECORDS: on top of 18f9eb8 (tests/host/test_v123_records.py's walk) in EVIDENCE, HARDWARE_TESTS, DEVLOG and UNKNOWNS; GBP-HW-382 / 383 once each after
    GBP-HW-381; "no capture loss" is CORROBORATED and never FACT; the fallback rule recorded as the central session's call; the Operator's words verbatim and apart;
    CARTDECL a declaration; the procedural deviation in its four parts, in order.
The archive is under captures/local (ignored by Git): those tests skip, with the registered reason, on a host without it.
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import guards  # noqa: E402
import test_v123_records as walk  # noqa: E402

BASE = "18f9eb8452a4ce818e24502a612125b44264e753"      # origin/main when #155 was dispatched; the reader's frozen state
LOCAL = os.path.join(ROOT, "captures", "local")
RAW = os.path.join(ROOT, "logs", "run61")
RUNS = {61: ("GBP-PLAY-002_vehicle-0001-run61.log", "9a8120351db9e129620d53708f190ba3acfdfd0cd23179452f09d775f67ce0cd", "GBP-PLAY-002_vehicle-0001-1.log"),
        62: ("GBP-PLAY-002_vehicle-0001-run62.log", "56575eb5e1573daa25f63574193fc7953c93debe6cde35e3bff7410fb9594b33", "GBP-PLAY-002_vehicle-0001-2.log"),
        63: ("GBP-PLAY-002_vehicle-0001-run63.log", "ddc8381e144072ede3d477c3fadcc262aba4af590594ddf4b1ebea9a212267f2", "GBP-PLAY-002_vehicle-0001-3.log")}
V28 = {54: "GBP-AUDIO-V28_v28-diagloss-0001-run54.log", 55: "GBP-AUDIO-V28_v28-validation-0001-run55.log", 56: "GBP-AUDIO-V28_v28-validation-0001-run56.log",
       57: "GBP-AUDIO-V28_v28-validation-0001-run57.log", 58: "GBP-AUDIO-V28_v28-perceptual-0001-run58.log"}
TB = 40500000
NOMINAL = 4096
HT, EV, DEVLOG, UN, HANDOFF = walk.HT, walk.EV, walk.DEVLOG, walk.UN, "docs/HANDOFF.md"
HEAD = "### V31.10 RUN 61 / RUN 62 / RUN 63 EXECUTED AND INGESTED"
OPERATOR = ("sim, joguei na ordem.. os logs -1 -2 e -3 se referem na ordem solicitada, respecitivamente... eu que renomeei dessa forma... e nao teve gecko",
            "sobre as respostas, sao as mesmas para os 3 titulos", "Ciclo de energia SIM", "b - ouvi os sons dos jogos normalmente", "C - mesma coisa da B",
            "D - controles responderam", "E - nada estranho", "f - nada a declarar", "B - vi os jogos normalmente.")


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def flat(s):
    return " ".join(s.replace("`", "").replace("**", "").split())


def v31_10():
    t = read(HT)
    i = t.index(HEAD)
    j = t.find("\n### ", i + 1)
    return t[i:j if j > 0 else len(t)]


def ev(eid):
    e, _ = walk.entries(read(EV), walk.EV_HEAD)
    h, body = e[eid]
    return h + body


def kv(rest):
    return dict(re.findall(r'(\w+)=("[^"]*"|\S+)', rest))


def recs(text, tag):
    return [kv(m.group(1)) for m in re.finditer(r"^\d{6} %s (.*)$" % re.escape(tag), text, re.M)]


def thin(n):
    s = "%d" % n
    out = []
    while len(s) > 3:
        out.insert(0, s[-3:])
        s = s[:-3]
    return " ".join([s] + out)


def figures(text):
    """V31.10's capture table for one log, recomputed."""
    taps = recs(text, "V28TAPS")[0]
    phc = recs(text, "V28PHC")
    first_key = int(recs(text, "KEY")[0]["t_done"], 16)
    first_a = [k for k in recs(text, "KEY") if int(k["keys"], 16) & 1][0]
    origin = int([p for p in phc if p["p"] == "0"][0]["t0"], 16)
    agg = recs(text, "AUDIOAGG")[0]
    rate = int(agg["completed"]) / float(recs(text, "CLOCKSEC")[0]["capture_s"])
    d = int(taps["taps"]) - int(taps["blocks_in"])
    return {"taps": int(taps["taps"]), "blocks_in": int(taps["blocks_in"]), "d": d, "nominal_s": d / float(NOMINAL), "measured_s": d / rate,
            "key_origin_s": (origin - first_key) / float(TB), "a_origin_s": (origin - int(first_a["t_done"], 16)) / float(TB), "first_a_n": first_a["n"],
            "phases": [(int(p["blocks_in"]), int(p["taps"]), int(p["failed"]), int(p["wrong"])) for p in phc],
            "outside_blocks": int(taps["blocks_in"]) - sum(int(p["blocks_in"]) for p in phc), "outside_taps": int(taps["taps"]) - sum(int(p["taps"]) for p in phc),
            "taps_failed": int(taps["taps_failed"]), "wrong_len": int(taps["wrong_len"]), "agg": agg, "c2": recs(text, "V28C2")[0], "corr": recs(text, "V28CORR")[0]}


class TheArchiveReadsAsRecorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = {r: os.path.join(LOCAL, f) for r, (f, _, _) in RUNS.items()}
        if not all(os.path.isfile(p) for p in cls.paths.values()):
            raise unittest.SkipTest("no local archive on this host (captures/local is ignored)")
        for r, p in cls.paths.items():
            assert sha(p) == RUNS[r][1], "captures/local's RUN %d archive is not the recorded one (a defect in the archive, never a skip)" % r
        cls.text = {}
        for r, p in cls.paths.items():
            with open(p, encoding="utf-8", errors="replace") as f:
                cls.text[r] = f.read()
        cls.fig = {r: figures(t) for r, t in cls.text.items()}
        cls.sec = flat(v31_10())

    def test_the_archive_equals_the_operators_raw_originals(self):
        raws = [os.path.join(RAW, raw) for _f, _h, raw in RUNS.values()]
        if not all(os.path.isfile(p) for p in raws):
            self.skipTest("raw log not available locally")
        for r, (f, h, raw) in RUNS.items():
            with open(os.path.join(RAW, raw), "rb") as a, open(self.paths[r], "rb") as b:
                self.assertEqual(a.read(), b.read(), "RUN %d: the archive copy differs from %s" % (r, raw))

    def test_the_frozen_readers_output_is_the_records_byte_for_byte(self):
        if not guards.base_available(BASE):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE)
        blocks = re.findall(r"```text\n(PLAYREAD  test=GBP-PLAY-002 [^\n]*\n.*?)\n```", v31_10(), re.S)
        self.assertEqual(len(blocks), 3)
        with tempfile.TemporaryDirectory() as tmp:
            arch = subprocess.run(["git", "archive", BASE, "tools"], cwd=ROOT, capture_output=True, check=True).stdout
            subprocess.run(["tar", "-x", "-C", tmp], input=arch, check=True)
            reader = os.path.join(tmp, "tools", "playread.py")
            for blk, r in zip(blocks, (61, 62, 63)):
                out = subprocess.run([sys.executable, reader, self.paths[r]], capture_output=True, text=True)
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertEqual(blk, out.stdout.rstrip("\n"), "RUN %d's block is not what the frozen reader prints" % r)
                self.assertIn("\nCAPTURE: FAIL\n  - V28TAPS taps=%d != blocks_in=%d\n" % (self.fig[r]["taps"], self.fig[r]["blocks_in"]), blk)
                self.assertIn("idx=%d " % (r - 60), blk)

    def test_the_capture_table_is_the_logs(self):
        f = self.fig
        rows = (("V28TAPS taps (whole session)", [thin(f[r]["taps"]) for r in RUNS]),
                ("V28TAPS blocks_in (whole session)", [thin(f[r]["blocks_in"]) for r in RUNS]),
                ("taps - blocks_in", [thin(f[r]["d"]) for r in RUNS]),
                ("at the nominal 4 096 blocks a second", ["%.3f s" % f[r]["nominal_s"] for r in RUNS]),
                ("at the session's measured tap rate (*)", ["%.3f s" % f[r]["measured_s"] for r in RUNS]),
                ("first KEY record -> the origin (V28PHC p0 t0)", ["%.3f s" % f[r]["key_origin_s"] for r in RUNS]),
                ("the gap to the measured-rate figure", ["%.1f ms" % (1000 * abs(f[r]["key_origin_s"] - f[r]["measured_s"])) for r in RUNS]),
                ("the first A press (KEY n=2) -> the origin", ["%.3f s" % f[r]["a_origin_s"] for r in RUNS]),
                ("V28PHC p0 (navigate) taps = blocks_in", [thin(f[r]["phases"][0][0]) for r in RUNS]),
                ("V28PHC p1 (play) taps = blocks_in", [thin(f[r]["phases"][1][0]) for r in RUNS]))
        for label, cells in rows:
            self.assertIn(flat(label + " " + " ".join(cells)), self.sec, label)
        for r in RUNS:
            self.assertEqual(f[r]["first_a_n"], "2")
            self.assertEqual(len(f[r]["phases"]), 2)
            for b, t, fail, wrong in f[r]["phases"]:
                self.assertEqual((b, fail, wrong), (t, 0, 0), "RUN %d: a phase where taps != blocks_in or a tap failed" % r)
            self.assertEqual(f[r]["outside_blocks"], 1)
            self.assertEqual(f[r]["outside_taps"], f[r]["d"] + 1)
            self.assertEqual((f[r]["taps_failed"], f[r]["wrong_len"]), (0, 0))
            self.assertEqual(tuple(f[r]["c2"][k] for k in ("lost", "syncpe_lost", "lines_lost")), ("0", "0", "0"))
            a = f[r]["agg"]
            self.assertEqual((int(a["selected"]), int(a["attempted"]), int(a["completed"]), a["failures"]), (f[r]["taps"],) * 3 + ("0",))
            self.assertEqual(f[r]["corr"]["overflow"], "0")
            self.assertGreater(f[r]["d"], 0, "the two counters must be able to differ, or per-phase equality is a zero by construction")
        self.assertIn("(%s ms at the nominal rate)" % " / ".join("%.1f" % (1000 * abs(f[r]["key_origin_s"] - f[r]["nominal_s"])) for r in RUNS), self.sec)
        self.assertIn("taps outside the phases: %s" % " / ".join(thin(f[r]["outside_taps"]) for r in RUNS), self.sec)

    def test_the_gates_are_the_logs(self):
        s = self.sec
        loss, dma_ms = {}, []
        for r, t in self.text.items():
            end = [x for x in re.findall(r"^\d{6} VSTATE (end .*)$", t, re.M)][-1]
            e = kv(end)
            self.assertEqual((e["status"], e["stop"], e["restore"], e["errors"], e["transport_ok"]), ("ok_session_ended", "session_end", "ok", "0", "1"))
            self.assertEqual([(p["phase"], p["ended"], p["reason"]) for p in recs(t, "SYNCPH")], [("0", "1", "cap"), ("1", "1", "cap")])
            loss[r] = ["%.3f %%" % (100 * (1 - int(p["blocks_in"]) / (NOMINAL * (int(p["t1"], 16) - int(p["t0"], 16)) / float(TB)))) for p in recs(t, "V28PHC")]
            for x in loss[r]:
                self.assertTrue(0.10 <= float(x.split()[0]) <= 0.40, x)
            self.assertEqual(recs(t, "PLAYUNDER")[0], {"startup": "1", "after_startup": "0", "post_feed": "0", "first_after_handed": "-", "unrecorded": "0", "total": "1", "k": "64"})
            self.assertEqual([(u["n"], u["handed"], u["since_dma_ms"], u["post_feed"]) for u in recs(t, "PLAYUND")], [("0", "2", "0", "0")])
            st = recs(t, "PLAYSTARTUP")[0]
            self.assertEqual((st["k"], st["ring_at_dma"], st["ready_at_dma"]), ("64", "4097", "1"))
            self.assertEqual([p["underruns"] for p in recs(t, "V28PHC")], ["1", "0"])
            self.assertEqual((recs(t, "V28C")[0]["underruns"], recs(t, "V28C")[0]["silences"]), ("1", "1"))
            self.assertEqual(recs(t, "ENVMEM")[0]["arena1_free"], "6742016")
            self.assertEqual(recs(t, "EVENTS")[0]["store_full"], "0")
            self.assertEqual(recs(t, "FRAMECAP")[0]["store_full"], "0")
            self.assertRegex(t, r"(?m)^libogc=[^\n]* gecko=0 ")
            self.assertRegex(t, r"(?m)^\d{6} CONTROL semantic orig=92 exp=8e ")
            self.assertEqual(len(recs(t, "CARTDECL")), 1)
            self.assertEqual(recs(t, "CARTDECL")[0]["idx"], str(r - 60))
            self.assertEqual(recs(t, "SESSION")[0]["requested"], "0")
            self.assertEqual((recs(t, "KEYLOG")[0]["lost"], recs(t, "KEYLOG")[0]["truncated"], recs(t, "INPUT")[0]["failed"]), ("0", "0", "0"))
            dma, origin = int(st["t_dma"], 16), int(recs(t, "V28PHC")[0]["t0"], 16)
            dma_ms.append("%.1f" % ((dma - origin) / float(TB) * 1000))
        self.assertIn("p0 %s / %s / %s; p1 %s / %s / %s" % (loss[61][0][:-2], loss[62][0][:-2], loss[63][0][:-2] + " %", loss[61][1][:-2], loss[62][1][:-2], loss[63][1][:-2] + " %"), s)
        self.assertIn("at the DMA start, %s ms after the origin" % " / ".join(dma_ms), s)
        ev_ = [int(recs(self.text[r], "EVENTS")[0]["n"]) for r in RUNS]
        self.assertIn("EVENTS n= %s of 38 315" % " / ".join(thin(n) for n in ev_), s)
        self.assertIn("(57.6 % at most", s)
        self.assertEqual(round(100.0 * max(ev_) / 38315, 1), 57.6)
        fr = [int(recs(self.text[r], "FRAMECAP")[0]["frames"]) for r in RUNS]
        self.assertIn("FRAMECAP %s of 29 100" % " / ".join(thin(n) for n in fr), s)
        caps = [float(recs(self.text[r], "CLOCKSEC")[0]["capture_s"]) for r in RUNS]
        self.assertIn("%.1f / %.1f / %.1f a second over the capture" % tuple(n / c for n, c in zip(ev_, caps)), s)

    def test_the_v28_chassis_logs_carry_the_same_inequality(self):
        paths = {r: os.path.join(LOCAL, f) for r, f in V28.items()}
        if not all(os.path.isfile(p) for p in paths.values()):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        for r, p in paths.items():
            with open(p, encoding="utf-8", errors="replace") as fh:
                t = fh.read()
            taps = recs(t, "V28TAPS")[0]
            self.assertGreater(int(taps["taps"]), int(taps["blocks_in"]), r)
            sep = " against " if r == 54 else " / "
            self.assertIn("RUN %d (%s%s%s" % (r, thin(int(taps["taps"])), sep, thin(int(taps["blocks_in"]))), self.sec, r)
            phc = recs(t, "V28PHC")
            self.assertEqual(bool(phc), r != 54)
            for x in phc:
                self.assertEqual((x["blocks_in"], x["failed"], x["wrong"]), (x["taps"], "0", "0"), r)
            if phc:
                self.assertEqual(int(taps["blocks_in"]) - sum(int(x["blocks_in"]) for x in phc), 1, r)
        g4 = flat(read(HT)[read(HT).index("### V28.33 RUN 58"):read(HT).index("### V28.34 ")])
        self.assertIn("980 005 = 980 005", g4)


class TheCodeTheRecordCites(unittest.TestCase):
    def test_the_lines_at_the_base(self):
        pr = guards.show(BASE, "tools/playread.py").split("\n")
        self.assertEqual(pr[104].strip(), 'if taps.get("taps") != taps.get("blocks_in"):')
        mc = guards.show(BASE, "poc/gbp-play-gba/source/main.c").split("\n")
        self.assertEqual(mc[372].strip(), "#define GAME_ORIGIN_DELAY_MS 1000u")
        self.assertEqual(mc[468].strip(), "live_taps++;")
        self.assertIn("static void live_tap_body", mc[464])
        self.assertEqual(mc[1010].strip(), "gbp_alive_use_press_origin(&live, GAME_ORIGIN_DELAY_MS);")
        self.assertIn("gecko_present = usb_isgeckoalive(GECKO_CHANNEL);", "\n".join(mc))


class TheRecordsAreOnTopAndSayWhatTheyMay(unittest.TestCase):
    def test_every_block_of_the_base_starts_its_block_now(self):
        for path, least in ((EV, 440), (HT, 1300), (DEVLOG, 380), (UN, 50)):
            self.assertGreater(walk.walk_on_top(self, path), least, path)

    def test_the_new_ids_follow_the_bases_last_once_each(self):
        ids = [m.group(1) for m in re.finditer(walk.EV_HEAD, read(EV), re.M)]
        i = ids.index("GBP-HW-381")
        self.assertEqual(ids[i + 1:i + 3], ["GBP-HW-382", "GBP-HW-383"])
        self.assertEqual((ids.count("GBP-HW-382"), ids.count("GBP-HW-383")), (1, 1))
        t = read(HT)
        self.assertEqual(t.count(HEAD), 1)
        self.assertGreater(t.index(HEAD), t.index("### V31.9 The candidate PINNED as"))

    def test_no_capture_loss_is_corroborated_and_never_fact(self):
        s, e = flat(v31_10()), flat(ev("GBP-HW-382"))
        self.assertIn('"No capture loss inside the phases" is CORROBORATED, NOT FACT', s)
        self.assertIn("no capture loss inside the phases CORROBORATED, NOT FACT", e)
        self.assertIn("CORROBORATED, NOT FACT: no capture loss inside the phases.", e)
        for text in (s, e):
            self.assertIsNone(re.search(r"capture loss[^.;]{0,80}\bFACT\b", text.replace("NOT FACT", "")), "a sentence calls no capture loss FACT")
            self.assertIn("Issue #156", text)
        self.assertIn("acts FORWARD only: it does not re-judge RUN 61-63", s)
        what = ('(here "capture loss" means a tap counted and not decoded; the drain\'s block loss against the nominal rate, 0.174-0.179 % per phase, '
                'is a separate figure and is not what this statement covers)')
        self.assertIn(flat(what), s)
        self.assertIn(flat(what), e)
        self.assertIn("CAPTURE: FAIL", s)

    def test_the_fallback_rule_is_the_central_sessions_call(self):
        s, e = flat(v31_10()), flat(ev("GBP-HW-382"))
        self.assertIn("THE CENTRAL SESSION'S CALL (the Orchestrator seat), recorded as such, not this record's", s)
        self.assertIn("No rung moves: T256 A1 stands", s)
        self.assertIn("the central session (the Orchestrator seat) records that no rung moves and T256 A1 stands", e)
        self.assertIn("That call is the central session's; this entry records it and makes none.", e)

    def test_the_operators_words_are_verbatim_and_apart(self):
        s = v31_10()
        for w in OPERATOR:
            self.assertIn(w, s, w)
        self.assertIn("It was not reinterpreted (AGENTS.md §7.2)", s)
        self.assertIn("neither substituted for the other, neither reconciled toward the other", s)
        self.assertIn("`CARTDECL` is an OPERATOR DECLARATION, not a machine reading", s)
        e = ev("GBP-HW-382")
        for w in ("vi os jogos normalmente.", "ouvi os sons dos jogos normalmente", "controles responderam", "nada estranho", "nada a declarar", "Ciclo de energia SIM"):
            self.assertIn(w, e, w)
        self.assertIn("an OPERATOR DECLARATION, not a machine reading", e)

    def test_the_procedural_deviation_has_its_four_parts_in_order(self):
        s = v31_10()
        dev = s[s.index("**PROCEDURAL DEVIATION"):]
        at = [dev.index(p) for p in ("- **Fact.**", "- **Mitigation.**", "- **Demonstrated consequence.**", "- **Not concluded.**")]
        self.assertEqual(at, sorted(at))
        for p in ("- **Fact.**", "- **Mitigation.**", "- **Demonstrated consequence.**", "- **Not concluded.**"):
            self.assertEqual(dev.count(p), 1, p)
        for tok in ("copied the three logs off the card and renamed them himself", "There was no Gecko capture", "The power cycle is DECLARED", "nothing is voided by it"):
            self.assertIn(tok, s, tok)

    def test_the_cross_reference_to_v31_3_is_appended_and_v31_3_is_not_edited(self):
        s = v31_10()
        self.assertIn("**Cross-reference (forward only; V31.3 is not edited).** V31.3's sentence \"RUN 55-58 each show exactly one, in `navigate` (p0)\" is right per phase", s)
        self.assertIn("RUN 55, 56 and 57 record `V28C underruns=2` (V28PHC p0 1 and p1 1; GBP-HW-367 already reads RUN 55 so), RUN 58 records 1 (p0)", s)
        self.assertIn("RUN 55-58 each show exactly one, in `navigate` (p0)", read(HT)[read(HT).index("### V31.3 "):read(HT).index("### V31.4 ")])

    def test_the_cross_reference_figures_are_the_logs(self):
        paths = {r: os.path.join(LOCAL, V28[r]) for r in (55, 56, 57, 58)}
        if not all(os.path.isfile(p) for p in paths.values()):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        want = {55: ("2", ["1", "1", "0", "0"]), 56: ("2", ["1", "1", "0", "0"]), 57: ("2", ["1", "1", "0", "0"]), 58: ("1", ["1", "0"])}
        for r, p in paths.items():
            with open(p, encoding="utf-8", errors="replace") as fh:
                t = fh.read()
            self.assertEqual((recs(t, "V28C")[0]["underruns"], [x["underruns"] for x in recs(t, "V28PHC")]), want[r], r)

    def test_the_handoff_carries_the_state_on_top(self):
        h = read(HANDOFF)
        for head in ("## Current blocker / current question\n\n", "## Next safe action\n\n"):
            i = h.index(head) + len(head)
            sec = h[i:h.index("\n## ", i)]
            self.assertIn("**2026-10-05 (Issue #155), on top:", sec, head)
        self.assertIn("T256 A1 stands", h)
        self.assertIn("Issue #156", h)


if __name__ == "__main__":
    unittest.main()
