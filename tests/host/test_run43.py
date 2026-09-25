"""tests/host/test_run43.py -- GitHub Issue #120: RUN 43 (GBP-AUDIO-012, sync-0001, Yoshi's Island) ingested.

The verdicts are RECOMPUTED, never quoted. The console's log, versioned byte for byte
(captures/fixtures/hw-gamecube-gbp-2026-09-25-sync-0001-run43.log), goes through the frozen tools/v27report.py (7c3bffd)
and tools/v27accept.py (4e4bce9), with and without the Operator's declaration (-run43-declaration.json, his words
verbatim from #119); every output is reproduced to its hash, and the printed block of HARDWARE_TESTS.md §V27.20.3 is
the gate's output byte for byte.

The ingestion's text is checked against the tools and against what the record said before it (c496f0b, the recount,
the commit before the ingestion's records): EVIDENCE and HARDWARE_TESTS and DEVLOG only grow at their ends, the
unknowns only gain a pointer on their heading and a section at their end, and the figures the entries quote are the
descriptive tools' (tools/v27derive.py and tools/vevents.py, run here; for tools/u012game.py the record is checked
here, on every host, against test_u012_game.PINS, and PINS against the tool in test_u012_game.RUN43 where the raw
window is present). No record says more than its evidence: A is not direction, the floor is not the correction's floor,
the bound is on the sum and not the residue, the slices' uniformity is not promoted, no pace is claimed impossible, and
the latency proposal travels with its cost.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import guards  # noqa: E402
import test_u012_game as ride  # noqa: E402  -- only its PINS table; its TestCases are collected in their own file
import v27derive  # noqa: E402
import vevents  # noqa: E402

FX = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-25-sync-0001-run43")
LOG, DECL = FX + ".log", FX + "-declaration.json"
LOCAL = os.path.join(ROOT, "captures", "local")
BASE = "c496f0b"
EV, UN, HT, DL, RM = ("docs/research/EVIDENCE.md", "docs/research/UNKNOWNS.md", "docs/research/HARDWARE_TESTS.md",
                      "docs/research/DEVLOG.md", "captures/README.md")

RAW = {"log": ("fd0652c36d6b0d649fc58b0db4aab844287d2121067ca3e22d63208a252ae4bc", 151285),
       "awr": ("a70ce4c11effad1c843a9dca49b76f9cf2f2eafc7c5becf4567071a7af735f80", 2621580),
       "gecko": ("82a89d7073d3acc78b443bfdc61bafb48c5b012f6605ac70816ee0f0bc85c0db", 3221)}
DECL_SHA = "546ef0ea79087832a8316066939cefc75dcb664deb5146605a93e4c6b7eac95b"
OUT = {"report": "4374a4654f35c24eecca0c145c2854c6a9b769c0c9b6567b202395cd826da262",
       "verdicts": "bd74fce7ed2bfc18f630a153dc7321af465430067a7bca883fed6dd8664d1916",
       "accept": "c8348b12099995a25ccccc21ae6a2017d81b00501cc9aac2846a1fb50aff4c46",
       "verdicts_nodecl": "ad4a8ced1252610fd9877146f067a9f05ab79125021307a1782a5a0b735c833e",
       "accept_nodecl": "4fbed15416a556fc30ab5158a335170c796b8b2e9b5295ff493e8179958935cf"}


def read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def then(path):
    b = guards.show(BASE, path)
    return b.decode("utf-8") if isinstance(b, bytes) else b


def flat(s):
    return " ".join(s.replace("`", "").replace("*", "").split())


def entry(text, eid):
    m = re.search(r"^### %s \S.*$" % re.escape(eid), text, re.M)
    nxt = re.search(r"^### (?:GBP|ENV)-[A-Z]+-\d{3} ", text[m.end():], re.M)
    return m.group(0), text[m.end():m.end() + nxt.start() if nxt else len(text)]


def v2720():
    t = read(HT)
    return t[t.index("### V27.20 "):]


class Run(object):
    _done = None

    @classmethod
    def get(cls):
        if cls._done is None:
            tools = os.path.join(ROOT, "tools")
            with tempfile.TemporaryDirectory() as d:
                rj, aj, nj = (os.path.join(d, n) for n in ("report.json", "accept.json", "nodecl.json"))
                subprocess.run([sys.executable, os.path.join(tools, "v27report.py"), LOG, "--json", rj], check=True,
                               capture_output=True, timeout=300)
                v = subprocess.run([sys.executable, os.path.join(tools, "v27accept.py"), rj, "--declaration", DECL,
                                    "--json", aj], check=True, capture_output=True, timeout=300).stdout
                vn = subprocess.run([sys.executable, os.path.join(tools, "v27accept.py"), rj, "--json", nj],
                                    check=True, capture_output=True, timeout=300).stdout
                blobs = {}
                for k, p in (("report", rj), ("accept", aj), ("accept_nodecl", nj)):
                    with open(p, "rb") as f:
                        blobs[k] = f.read()
            cls._done = {"blobs": blobs, "verdicts": v, "verdicts_nodecl": vn, "acc": json.loads(blobs["accept"])}
        return cls._done


class TheFiles(unittest.TestCase):
    def test_the_fixtures_are_the_raw_bytes(self):
        with open(LOG, "rb") as f:
            b = f.read()
        self.assertEqual((sha(b), len(b)), RAW["log"])
        with open(DECL, "rb") as f:
            self.assertEqual(sha(f.read()), DECL_SHA)

    def test_the_flat_archive_when_present(self):
        names = {"log": "GBP-AUDIO-012_sync-0001-run43.log", "awr": "GBP-AUDIO-012_sync-0001-run43-awr.bin",
                 "gecko": "GECKO-LIVE-run43-orchestrator-capture.txt"}
        for k, n in names.items():
            p = os.path.join(LOCAL, n)
            if not os.path.isfile(p):
                self.skipTest("the RUN 43 flat archive is not in this checkout (captures/local is ignored)")
            with open(p, "rb") as f:
                b = f.read()
            self.assertEqual((sha(b), len(b)), RAW[k], n)

    def test_the_declaration_is_his_words(self):
        with open(DECL, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["A"], "Sim percebi")
        self.assertEqual(d["B"], "Parecia sincronizado . Acredito que cheguei no fim da escala da esquerda, que diminuía ..")
        self.assertEqual((d["C"], d["D"], d["E"], d["F"]), ("", "Pass", "Normal", "Responderam"))
        self.assertEqual(d["G"], "Nada a declarar por enquanto")
        self.assertIn("issuecomment-5832543719", d["source"])


class TheVerdictsRecomputed(unittest.TestCase):
    def test_every_output_to_its_hash(self):
        r = Run.get()
        self.assertEqual(sha(r["blobs"]["report"]), OUT["report"])
        self.assertEqual(sha(r["verdicts"]), OUT["verdicts"])
        self.assertEqual(sha(r["blobs"]["accept"]), OUT["accept"])
        self.assertEqual(sha(r["verdicts_nodecl"]), OUT["verdicts_nodecl"])
        self.assertEqual(sha(r["blobs"]["accept_nodecl"]), OUT["accept_nodecl"])

    def test_the_declaration_gates_nothing(self):
        r = Run.get()
        with_d = r["verdicts"].decode("utf-8").splitlines()
        without = r["verdicts_nodecl"].decode("utf-8").splitlines()
        self.assertEqual(with_d[:-1], without)
        self.assertTrue(with_d[-1].startswith("  DECLARATION (his words, gating nothing): "))

    def test_the_verdicts(self):
        a = Run.get()["acc"]
        p1, p2, p3, m = a["phase1"], a["phase2"], a["phase3"], a["M"]
        self.assertEqual((p1["verdict"], p1["D"], p1["null_change"], p1["answered"], p1["real"], p1["nulls"]),
                         ("CONFIRMS", 12, 3, 18, 12, 6))
        self.assertEqual(p2["verdict"], "INCONCLUSIVE")
        self.assertEqual(p3["verdict"], "NOT RUN")
        self.assertEqual((m["M1"], m["M2"], m["M3"]), ("PASS", "PASS", "PASS"))
        self.assertEqual((m["arms"]["DEEP"]["lost_blocks"], m["arms"]["SHALLOW"]["lost_blocks"]), (355, 448))


class TheRecord(unittest.TestCase):
    def test_the_printed_block_is_the_gate_byte_for_byte(self):
        s = v2720()
        block = s[s.index("#### V27.20.3 "):s.index("#### V27.20.4 ")]
        body = block[block.index("```text\n") + len("```text\n"):block.rindex("```")]
        self.assertEqual(body, Run.get()["verdicts"].decode("utf-8"))

    def test_the_declaration_block_is_his_words(self):
        s = v2720()
        block = s[s.index("#### V27.20.2 "):s.index("#### V27.20.3 ")]
        with open(DECL, encoding="utf-8") as f:
            d = json.load(f)
        for k in "ABDEFG":
            self.assertIn("%s. %s\n" % (k, d[k]), block, k)
        self.assertIn("\nC.\n", block)

    def test_the_entries_exist_once_in_order_after_gbp_hw_340(self):
        ev = read(EV)
        ids = re.findall(r"^### (GBP-HW-3\d\d) ", ev, re.M)
        self.assertEqual(ids[-7:], ["GBP-HW-340", "GBP-HW-341", "GBP-HW-342", "GBP-HW-343", "GBP-HW-344",
                                    "GBP-HW-345", "GBP-HW-346"])
        for i in ("GBP-HW-341", "GBP-HW-342", "GBP-HW-343", "GBP-HW-344", "GBP-HW-345", "GBP-HW-346"):
            self.assertEqual(len(re.findall(r"^### %s " % i, ev, re.M)), 1, i)

    def test_the_statuses_say_no_more_than_the_evidence(self):
        ev = read(EV)
        h, b = entry(ev, "GBP-HW-341")
        self.assertIn("FACT (the frozen gate's result, one run, one Operator)", h)
        self.assertIn("`U-GBP-046`'s cushion HYPOTHESIS becomes CORROBORATED", h)
        self.assertIn("`A`'s words are not evidence of direction", h)
        self.assertIn("D comes only from the answers the console recorded as he pressed them.", flat(b))
        h, b = entry(ev, "GBP-HW-342")
        self.assertIn("Phase 2 INCONCLUSIVE by (t4), as frozen", h)
        self.assertIn("the null point is CENSORED at the floor", h)
        self.assertIn("It does not bound the residue by 0.25–0.28 s.", flat(b))
        self.assertIn("Nothing about U-GBP-045's cost side is inferred from where Phase 2 bottomed out.", flat(b))
        h, b = entry(ev, "GBP-HW-343")
        self.assertIn("FACT (counts, one run; the interval is a resampling of whole dwells)", h)
        h, b = entry(ev, "GBP-HW-344")
        self.assertIn("Not established: that no pace could have finished all three phases.", flat(b))
        self.assertIn("The Orchestrator's.", b)
        self.assertIn("The Executor's.", b)
        self.assertIn("the Executor set the safety wall at 785 s and sized the FRAME store for it", flat(b))
        self.assertIn("(§V27.17, defect 6)", flat(b))
        h, b = entry(ev, "GBP-HW-345")
        self.assertIn("that the slices are uniform in time stays a HYPOTHESIS", h)
        self.assertNotIn("CORROBORATED", h)
        self.assertIn("It is **not versioned**", b)
        self.assertNotIn("0.064", b)                      # the continuous model's number is no bound on these slices
        h, b = entry(ev, "GBP-HW-346")
        self.assertIn("every Hz figure is conditional on uniform slices and on the block rate", h)

    def test_the_m4_table_is_the_tool(self):
        with open(LOG, encoding="utf-8") as f:
            m = v27derive.derive(f.read())["m4"]
        b = flat(entry(read(EV), "GBP-HW-343")[1])
        d, s = m["arms"]["DEEP"], m["arms"]["SHALLOW"]
        self.assertIn("DEEP 0.5 s 6 49 355 %.3f 32 %d %.3f 0 0" % (d["per_s"], d["lost_settled"], d["per_s_settled"]),
                      b)
        self.assertIn("SHALLOW 0.125 s 6 71 448 %.3f 53 %d %.3f 0 0"
                      % (s["per_s"], s["lost_settled"], s["per_s_settled"]), b)
        r, rs = m["ratio"]["live"], m["ratio"]["settled"]
        self.assertIn("%.3f (90 %%: %.3f-%.3f) %.3f (%.3f-%.3f)" % (r["shallow_over_deep"], r["ci90"][0], r["ci90"][1],
                                                                    rs["shallow_over_deep"], rs["ci90"][0],
                                                                    rs["ci90"][1]), b)

    def test_the_event_rate_is_the_tool(self):
        with open(LOG, encoding="utf-8") as f:
            r = vevents.analyse(f.read())
        b = flat(entry(read(EV), "GBP-HW-344")[1])
        self.assertIn("RUN 43 sync-0001 16 384 5 249.734 14 912 %.2f %.4f %.1f s" % (r["per_s"], r["per_frame"],
                                                                                  r["permits_s"]["measured"]), b)
        self.assertIn("%.1f s at one per frame" % r["permits_s"]["one_per_frame"], b)
        self.assertIn("%.1f s at the episode path's ceiling" % r["permits_s"]["episode_ceiling"], b)

    def test_the_game_window_figures_are_the_pinned_ones(self):
        P = ride.PINS
        b345 = flat(entry(read(EV), "GBP-HW-345")[1])
        for tok in ("changes >= 6 one-bits %s: %d on EVEN boundaries, %d on ODD" % ("1 286", P["even"], P["odd"]),
                    "P = %s slices" % P["P"], "= %s AGB cycles at 256 per slice" % P["cycles"], "%s Hz nominal" % P["hz"],
                    "after stored blocks " + " ".join(str(g) for g in P["gaps"]),
                    "%s block periods beyond the 640 stored" % P["timing"],
                    "R = %s against the quantisation bound %s (sampling sd %s)" % (P["R"], P["bound"], P["sd"]),
                    " ".join(str(c) for c in P["boundaries"]) + " chi-square %s on 14 dof" % P["chi2"],
                    "lower tail %s" % P["tail"],
                    "same sign %d, opposite %d" % tuple(P["neighbours"]["3+"])):
            self.assertIn(tok, b345, tok)
        b346 = flat(entry(read(EV), "GBP-HW-346")[1])
        for tok in ("pair decode (32 768/s) " + " ".join(P["pair"]) + " - " + P["above_pair"],
                    "slice decode (65 536/s) " + " ".join(P["slice"]) + " " + P["above_slice"],
                    "within a block %s" % P["within_block"], "within a pair %s" % P["within_pair"],
                    "%s of its AC energy is folded content" % P["fold"], "removes %s of the in-band energy" % P["droop"],
                    "the window, %d block periods, %s Hz" % (P["slots"], P["window_hz"]),
                    "%d blocks, %s Hz" % (P["longest"], P["run_hz"]), "a segment %s Hz" % P["segment_hz"]):
            self.assertIn(tok, b346, tok)
        u = read(UN)
        u41 = flat(u[u.index("**2026-09-25, Issue #120 (RUN 43) — the test this item named"):u.index("\n## U-GBP-042 ")])
        for tok in ("%d of %s changes fall on ODD boundaries" % (P["odd"], "1 286"), "coherence of %s" % P["R"],
                    "must have %s, with a sampling sd of %s" % (P["bound"], P["sd"]),
                    "lower tail %s" % P["tail"]):
            self.assertIn(tok, u41, tok)
        self.assertNotIn("0.064", u41)

    def test_the_latency_proposal_travels_with_its_cost(self):
        s = v2720()
        block = s[s.index("#### V27.20.7 "):s.index("#### V27.20.8 ")]
        prop = block[block.index("```text\n"):block.rindex("```")]
        for tok in ("0.125 s", "exercised as an ARM", "0.871", "0.798-0.977", "no underrun, no overflow",
                    "0.042/s", "THE VALUE THE RUN SUPPORTS", "0.09375 s", "Not adopted", "unsupported"):
            self.assertIn(tok, prop, tok)
        self.assertIn("`TARGET` is not changed here.", block)

    def test_the_unknowns_carry_their_pointers(self):
        u = read(UN)
        for uid, tok in (("U-GBP-012", "2026-09-25, Issue #120 (RUN 43): the first raw blocks of a GAME"),
                         ("U-GBP-041", "2026-09-25, Issue #120 (RUN 43): the two-slice grid is the SOURCE's"),
                         ("U-GBP-041", "the slices' uniformity passed one test at slice resolution and stays a HYPOTHESIS"),
                         ("U-GBP-045", "2026-09-25, Issue #120 (RUN 43): at 0.125 s of cushion against 0.5 s"),
                         ("U-GBP-046", "2026-09-25, Issue #120 (RUN 43): the cushion HYPOTHESIS is CORROBORATED")):
            self.assertIn(tok, re.search(r"^## %s .*$" % uid, u, re.M).group(0), uid)
        self.assertIn("STAYS OPEN for the physical half", re.search(r"^## U-GBP-012 .*$", u, re.M).group(0))
        self.assertIn("the item STAYS OPEN", re.search(r"^## U-GBP-046 .*$", u, re.M).group(0))
        self.assertIn("**The status is HYPOTHESIS.**", u)          # the old words stay; the pointer is on top


class OnTopNeverRewritten(unittest.TestCase):
    def test_the_research_records_only_grow_at_their_ends(self):
        for p in (EV, HT, DL):
            self.assertTrue(read(p).startswith(then(p)), p)

    def test_the_unknowns_only_gain_a_pointer_and_a_section(self):
        old, new = then(UN), read(UN)
        first = re.search(r"^#{2,3} U-(?:ENV|GBP)-\d{3} ", old, re.M).start()
        self.assertTrue(new.startswith(old[:first]), "the preamble")
        items = re.findall(r"^(#{2,3}) (U-(?:ENV|GBP)-\d{3}) ", old, re.M)
        self.assertGreater(len(items), 40)
        for lvl, uid in items:
            h0 = re.search(r"^%s %s .*$" % (lvl, uid), old, re.M)
            h1 = re.search(r"^%s %s .*$" % (lvl, uid), new, re.M)
            self.assertTrue(h1.group(0).startswith(h0.group(0)), uid)
            n0 = re.search(r"^#{2,3} U-(?:ENV|GBP)-\d{3} ", old[h0.end():], re.M)
            n1 = re.search(r"^#{2,3} U-(?:ENV|GBP)-\d{3} ", new[h1.end():], re.M)
            b0 = old[h0.end():h0.end() + n0.start() if n0 else len(old)]
            b1 = new[h1.end():h1.end() + n1.start() if n1 else len(new)]
            core = b0.rstrip("\n").rsplit("\n---", 1)[0] if b0.rstrip("\n").endswith("---") else b0.rstrip("\n")
            self.assertTrue(b1.startswith(core), uid)

    def test_the_readme_rows_are_kept(self):
        old, new = then(RM).split("\n"), read(RM).split("\n")
        self.assertEqual([l for l in new if l in set(old)], old)


if __name__ == "__main__":
    unittest.main()
