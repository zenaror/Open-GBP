"""tests/host/test_run41.py -- GitHub Issue #112: RUN 41 (GBP-AUDIO-010, game-0001, Yoshi's Island) ingested.

The verdicts are RECOMPUTED, never quoted. The console's log and its L2 record, versioned byte for byte
(captures/fixtures/hw-gamecube-gbp-2026-09-24-game-0001-run41.log and -run41-l2.bin), go through the frozen
tools/v25report.py (6129104) and tools/v25accept.py (as amended at 4591f9b). Every output sealed before the
Operator's declaration was relayed is reproduced to its hash, and so is every output after it, with the
declaration as the Orchestrator structured it on #111 (-run41-declaration.json). §V25.12's printed block must be
exactly what the gate tool prints. The descriptive figures of §V25.12 are recomputed from the same log.
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
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
README = os.path.join(ROOT, "captures", "README.md")
FX = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-24-game-0001-run41")
LOG, L2, DECL = FX + ".log", FX + "-l2.bin", FX + "-declaration.json"

RAW = {LOG: ("dfea2f1a641970cf303ef7e4f903070bf950e00191a9aac28841bfff67be2d38", 94768),
       L2: ("eca8e0185d88b034632afcd227bdbfe3885d12b5909855412079eb01a69d03a8", 83190),
       DECL: ("f0f3fbde1494611ea0f6e8c52660a74421416ebc36a0e88c40344626d572bcb7", None)}
# sealed at f385b07 with no declaration, before the Operator's words reached this session (§V25.12.1)
SEALED = {"report": "b195215a3ec8581f492181b8b190db03f5ef884d76df619176d1359f9f628424",
          "verdicts": "25e373a118261f5076dea0fff4ab619554f0085b5575018cd3f5751728e7417c",
          "accept": "b2cc15fa318108c2965a88585e07c2c2104717d652293fbb5c9ab092557fa918"}
# opened with the declaration of issuecomment-5821017811
FINAL = {"verdicts": "d1022e3532364f6aa2bce79be56534e88a9856d7ff76f1217ed0cb05ffdd45d3",
         "accept": "9edd994ab16f89bcd0efeffddbfa2bbb5e6663f4cd47296f862f6d265082a11c"}
TB = 40500000


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def kv(s):
    return dict(re.findall(r"(\w+)=(\S*)", s))


class Run(object):
    """Every output, computed once through the frozen tools' own entry points."""
    _done = None

    @classmethod
    def get(cls):
        if cls._done is None:
            with tempfile.TemporaryDirectory() as d:
                rj, aj, fj = (os.path.join(d, n) for n in ("report.json", "accept.json", "final.json"))
                subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v25report.py"), LOG, "--sidecar", L2,
                                "--json", rj], check=True, capture_output=True, timeout=300)
                sealed = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v25accept.py"), rj,
                                         "--sidecar", L2, "--json", aj], check=True, capture_output=True,
                                        timeout=300).stdout
                final = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "v25accept.py"), rj,
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
        for tok in ("test=GBP-AUDIO-010 app=gbp-audio-game build=game-0001 commit=6129104",
                    "LIVEGAME origin=press delay_ms=1000 control=none picture=press_to_window_end",
                    "LIVEL2SAVE open=0 write=0 close=0 bytes=83190 status=saved",
                    "FRAMECAP frames=4493 complete=4452 incomplete=41 ",
                    "LIVEVINC ai=1 before=14 inside=27 after=0 stored=41 framecap=41 store_full=0 secs=64",
                    "CONTROL semantic orig=92", "status=ok_session_ended"):
            self.assertIn(tok, log, tok)

    def test_the_declaration_is_the_orchestrators_structuring_of_the_operators_words(self):
        with open(DECL, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["a_stability"], "PASS")
        self.assertEqual(set(d["defects"].values()), {"no"})
        self.assertIn("pelo menos do que notei", d["a_words"])
        self.assertEqual((d["a_fidelity"], d["picture"], d["controls"]), ("so o abafado", "normal", "responded"))
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
    def test_L2_PASS(self):
        l2 = Run.get()["acc"]["L2"]
        self.assertEqual((l2["verdict"], l2["crc_kept"], l2["crc_host"], l2["frames"]),
                         ("PASS", 0x178E3C3F, 0x178E3C3F, 320000))
        self.assertEqual(l2["silence_fraction"], 0.0)

    def test_C_PASS(self):
        c = Run.get()["acc"]["C"]
        self.assertEqual((c["verdict"], c["seconds"], c["overflow"], c["underrun"], c["not_drained"]),
                         ("PASS", 64.0, 0, 0, 483))

    def test_A_PASS_his_verdict(self):
        a = Run.get()["acc"]["A"]
        self.assertEqual((a["verdict"], a["his_verdict"], a["defects_yes"], a["clipped"]), ("PASS", "PASS", [], 2084))

    def test_V_NOT_PASS_on_the_start_up_clause_alone(self):
        v = Run.get()["acc"]["V"]
        vid = v["video"]
        self.assertEqual((v["verdict"], vid["verdict"], vid["E_outside"], vid["E_inside"]),
                         ("NOT PASS", "DOES NOT HOLD", 1, 27))
        self.assertEqual((v["picture"], v["controls"]), ("normal", "responded"))
        rep = Run.get()["rep"]["video"]
        span = rep["t_ai_stop"] - rep["t_ai_start"]
        self.assertEqual((rep["before"], rep["after"], span), (14, 0, 2566709992))
        # the rate half, in RUN 40's integers (§V25.10): it HOLDS
        self.assertEqual((27 * 2567047476, 44 * span), (69310281852, 112935239648))
        self.assertLessEqual(27 * 2567047476, 44 * span)

    def test_phase_6_stays_open_on_V_alone(self):
        p = Run.get()["acc"]["phase6"]
        self.assertEqual(p["verdict"], "STAYS OPEN")
        self.assertEqual([c["clause"] for c in p["clauses_not_pass"]], ["V"])

    def test_R_and_M_decide_nothing(self):
        a = Run.get()["acc"]
        self.assertEqual((a["R"]["reading"], round(a["R"]["blocks_lost_per_s"], 3)), ("AS EXPECTED", 7.547))
        self.assertEqual(round(a["M"]["rate_hz"], 3), 32028.476)


class TheDescriptiveFigures(unittest.TestCase):
    """§V25.12: reported beside the verdicts; none of them moves one."""

    def test_the_before_frames_the_log_can_show(self):
        log = read(LOG)
        lt = kv(re.search(r"^\d{6} LIVET (.*)$", log, re.M).group(1))
        l2 = kv(re.search(r"^\d{6} LIVET2 (.*)$", log, re.M).group(1))
        t0, tp, ta = int(lt["t0"], 16), int(lt["t_press"], 16), int(l2["t_ai_start"], 16)
        evs = [kv(m) for m in re.findall(r"^\d{6} EV (.*)$", log, re.M)]
        head = [e for e in evs if int(e["seq"]) <= 128]
        self.assertIn("EVENTS n=2177 shown=192 dropped=0", log)
        self.assertIn("EVGAP omitted=1985", log)
        self.assertAlmostEqual((int(head[-1]["t"], 16) - t0) / float(TB), 2.170, places=3)
        seen = [int(e["f"]) for e in evs if e["type"] == "incomplete_interval" and int(e["t"], 16) < ta]
        self.assertEqual(seen, [1, 10, 13, 16, 32, 35, 38, 92, 95, 98])      # GBP-HW-317's visible ten
        self.assertEqual(14 - len(seen), 4)                                    # unseen, in (2.170 s, 11.872 s)
        self.assertEqual([round((x - t0) / float(TB), 3) for x in (tp, int(lt["t_origin"], 16), ta)],
                         [10.248, 11.248, 11.872])

    def test_the_four_preserved_start_up_episodes_are_the_same(self):
        log = read(LOG)
        opens = [int(kv(m)["open_frame"]) for m in re.findall(r"^\d{6} EPISODE (.*)$", log, re.M)]
        self.assertEqual(opens, [8, 30, 90, 150])
        self.assertIn("STRUCTURED status=observed episodes=182 stable=169 unstable=13 not_preserved=178", log)

    def test_the_clip_and_the_calibration(self):
        r = Run.get()["rep"]
        self.assertEqual(r["clipped"], 2084)
        c = r["calibration"]
        self.assertEqual((c["rest_sum"], c["rest_n"], c["pmin"], c["pmax"]), (66882991, 4096, 13571, 19390))
        self.assertAlmostEqual(c["rest_sum"] / float(c["rest_n"]), 16328.86, places=2)

    def test_both_channels_rose_in_the_same_ten_seconds(self):
        a = Run.get()["acc"]
        lost, vs = a["R"]["per_second_lost"], a["V"]["video"]["per_second"]
        self.assertEqual((sum(lost[20:30]), sum(lost)), (163, 483))
        self.assertAlmostEqual((sum(lost) - sum(lost[20:30])) / 54.0, 5.93, places=2)
        self.assertEqual((sum(vs[17:30]), sum(vs)), (16, 27))

    def test_the_episode_counts_against_run_40(self):
        r40 = read(os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-24-split-0001-run40.log"))
        self.assertIn("EVENTS n=370 ", r40)
        self.assertIn("EVENTS n=2177 ", read(LOG))


if __name__ == "__main__":
    unittest.main()
