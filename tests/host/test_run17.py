"""
tests/host/test_run17.py — RUN 17, RUN 18 and RUN 16: GBP-INPUT-002, the machine
join, on stream-0015 (da06500) with the Enhanced Control Checker's counted walks
A (RUN 17, the generic third-party pad) and B (RUN 18, the ORIGINAL Nintendo pad),
and the optional EZ-Flash menu reading (RUN 16, original pad, executed last);
pre-registered HARDWARE_TESTS §V7.3 (Issue #28), executed under Hardware Issue
#32, ingested under Issue #33 (result §V7.4). Preserved as fixtures.

Everything here is RECOMPUTED from the versioned fixtures, never restated: the
INPUT and KEY RECORD gates re-parsed from the verbatim summary records; R_b
re-derived from the verbatim KEY lines (rc=ok, n order, from 0000); the tally
vectors re-decoded from the OGBPFULL1 bytes with the frozen tools/vfull.py
parser and an exact glyph match; the END STATE by §V7.3.9's rule; Question J per
bit and Question I per interval from the frozen definitions, then compared with
the struct's answers; the two channels compared and kept apart; RUN 16's
UNDECIDED and its aborted reading; truncated=0 with both ENVINPUT halves
complete; the video path; §V7.1 / §V7.2 / §V7.3 byte-identical to 09f289c; the
promotion carried into GBP-KEY-004 and the consolidated pages with its history;
nothing under the untouchable paths moved. No test consults the Operator's
report to decide a machine fact.
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import unittest

import artifacts  # noqa: E402  (tests/host is on the path)

import guards

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import vdisp  # noqa: E402
import vfull  # noqa: E402
import vqual  # noqa: E402
import vvi  # noqa: E402

FX = os.path.join(ROOT, "captures", "fixtures")
P = "hw-gamecube-gbp-2026-09-21-"
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
ROADMAP = os.path.join(ROOT, "docs", "ROADMAP.md")
DEVLOG = os.path.join(ROOT, "docs", "research", "DEVLOG.md")
README = os.path.join(ROOT, "captures", "README.md")
INPUT_C = os.path.join(ROOT, "src", "gbp", "gbp_input.c")
TB = 40500000
SRC_HZ = 59.727
B_FRAMES = 3
LO, HI = 356, 2403
LABELS = ["L", "R", "UP", "DOWN", "LEFT", "RIGHT", "START", "SELECT", "A", "B"]
C_OF_B = {0: "A", 1: "B", 2: "SELECT", 3: "START", 4: "RIGHT", 5: "LEFT", 6: "UP", 7: "DOWN", 8: "L", 9: "R"}
DOL_SHA = "dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49"
PREV_SHA = "ef76a170c10d335e62c017e53f74c60e410e44f5ce2fbca6774ab43c68ec0b9c"
OLD13_SHA = "5391c3fe962dc4b2f4e493f3846ac7407ded064c58f5d4bb583a51e5a725dd79"
CANDIDATE_COMMIT = "da06500"
BASE_COMMIT = "09f289c"                      # origin/main before Issue #33; the last commit that touched §V7 (§V7.3, Issue #28)
KEY_RE = re.compile(r"^(\d{6}) KEY n=(\d+) act=(\S+) keys=([0-9a-f]{4}) word=([0-9a-f]{4}) t_poll=([0-9a-f]+) t_attempt=([0-9a-f]+) t_done=([0-9a-f]+) xfer=(\d+) rc=(\S+)$")
RUNS = {
    17: {"walk": [("L", 1), ("R", 2), ("A", 3), ("B", 4), ("SELECT", 5), ("START", 6)], "bits": {8: 1, 9: 2, 0: 3, 1: 4, 2: 5, 3: 6},
         "expected": [1, 2, 0, 0, 0, 0, 6, 5, 3, 4], "operator": [1, 2, 0, 0, 0, 0, 6, 5, 3, 4], "pad": "GENERIC",
         "log": (96396, "85d8963752cb9fed95d9842d0109c56ce87e2951d94cca0ef666cb646184dc83"),
         "idxcap": (8946060, "e32af1a6c929ad81b3efad99d2d36d4aef3bd06e934eea01b2cef0da40b244ac"),
         "disp": (400716, "f3c9bcf6a2891d4e2e011dfa911ecc5f3199e16942e2c02f612ed3f47a78571b"),
         "full": (1844492, "75c94bdbae45174ccf09b66bf556566122456bbe1dcac833caffda5e1910ec82"),
         "vi": (152396, "ae8c484d494bf5405addc3f450d0c71a6caa40989ebc15f28dbba40bb1028fbc"),
         "qual_sha": "7117fd3017fe51ee1222a56483ff4ac5e01a475fa32d41cc47149f179ab2a66e",
         "input": dict(selftest=1, steps=184953, invalid=0, no_base=0, key_changes=42, attempts=7898, completed=7898, failed=0,
                       first=1, change=42, refresh=7855, retry=0, last_word="0000", last_rc="ok"),
         "keylog": dict(events=43, emitted=43, lost=0, truncated=0, overwritten=0, reserve=64), "emit": (924, 1580, 1707),
         "first_change": ("0200", "0100"), "end_from": 2, "lines": 731,
         "counters": 254723, "transfers": 1033033, "irq": 509449, "first_handoff_ticks": 6696114, "eligible_ticks": 202507982,
         "idx_crc": ("d8d0ec90", "eab4be5b"), "full_crc": ("3a33c9b2", "e1ca3790"), "disp_crc": ("87675c23", "f22be0eb"),
         "vi_crc": ("ea13ef17", "e8eb921d"), "events": 2400, "dispsrc": (23, 37), "deferred_join": (18, 29),
         "p99_max": (0.003753, 0.733506), "vi_counts": (2372, 4), "superseded": [888, 1734, 2293, 2295], "pump_skipped": 69770},
    18: {"walk": [("L", 1), ("R", 2), ("UP", 3), ("DOWN", 4), ("LEFT", 5), ("RIGHT", 6)], "bits": {8: 1, 9: 2, 6: 3, 7: 4, 5: 5, 4: 6},
         "expected": [1, 2, 3, 4, 5, 6, 0, 0, 0, 0], "operator": [1, 2, 3, 4, 5, 6, 0, 0, 0, 0], "pad": "ORIGINAL",
         "log": (95265, "242821fc72d61c6882be09b71015f21f3f43100453646ce4d7621beb784539c1"),
         "idxcap": (8946060, "6be30f1533c0bd0ba34cce6dc9ff45731a5e4a6f0c6fdfc8a8e116b59b358204"),
         "disp": (400676, "c95bb27fdda7f164627b0b6666ded889d29f054de0e534a162e814d8c3a4cb9e"),
         "full": (1844492, "4a724784ffb575bc57d406c26cf6176cacf17cbaca8c6e4fb528770bc8231d6d"),
         "vi": (152396, "69eff4d1631bc241371976fc9befb69b9311d69933f9ba60da74808633c1f0b5"),
         "qual_sha": "8f3315e5de34bb040c88f4ba9ec8b2c81cb0768159a5790537e39ba17158cfac",
         "input": dict(selftest=1, steps=184956, invalid=0, no_base=0, key_changes=42, attempts=7898, completed=7898, failed=0,
                       first=1, change=42, refresh=7855, retry=0, last_word="0000", last_rc="ok"),
         "keylog": dict(events=43, emitted=43, lost=0, truncated=0, overwritten=0, reserve=64), "emit": (871, 1585, 1748),
         "first_change": ("0200", "0100"), "end_from": 3, "lines": 722,
         "counters": 254728, "transfers": 1033048, "irq": 509459, "first_handoff_ticks": 6696200, "eligible_ticks": 202507544,
         "idx_crc": ("d22bc9a4", "e5b1c72f"), "full_crc": ("3a33c9b2", "2e006fef"), "disp_crc": ("d8d64f31", "56a3b332"),
         "vi_crc": ("10986153", "3aed1d64"), "events": 2399, "dispsrc": (22, 33), "deferred_join": (18, 25),
         "p99_max": (0.003728, 0.585975), "vi_counts": (2370, 6), "superseded": [614, 888, 894, 1172, 2017, 2018], "pump_skipped": 69772},
    16: {"walk": [("R", 4), ("L", 4), ("R", 4), ("L", 4)], "bits": {8: 8, 9: 8}, "expected": None, "operator": None, "pad": "ORIGINAL",
         "log": (93996, "20d0be5aef47c955f9caea4250e1ef8c7a35fff77ef1d54bafb9da53f2726a6d"),
         "idxcap": (8946060, "e07cb0b43e46260f57f65fccfa6427e412124e31b06c24cf28d58528a701f1c1"),
         "disp": (400796, "9da66d6e2210ee50ffa700ab7988e93fadb39b97a6257bda55146689e23f2e5e"),
         "full": (1844492, "3cfb7dd94dda106de31b41dcb5cc078a014774a735d907df3527baddd5f7af07"),
         "vi": (152396, "f98d0974fcc973adc2585a753bc6a668b55b83728bc2f1babfc3e84f3ab74266"),
         "qual_sha": "0e5685ee3d8139a479028e39591664d7ee760307ea1ae97c180d851380fdd973",
         "input": dict(selftest=1, steps=184929, invalid=0, no_base=0, key_changes=32, attempts=7890, completed=7890, failed=0,
                       first=1, change=32, refresh=7857, retry=0, last_word="0000", last_rc="ok"),
         "keylog": dict(events=33, emitted=33, lost=0, truncated=0, overwritten=0, reserve=64), "emit": (909, 1567, 1722),
         "first_change": ("0100", "0200"), "end_from": None, "lines": 712,
         "counters": 254722, "transfers": 1033022, "irq": 509447, "first_handoff_ticks": 6696327, "eligible_ticks": 202507716,
         "idx_crc": ("ecc19b35", "e3c45143"), "full_crc": ("3a33c9b2", "4f39f6f1"), "disp_crc": ("4f12f7e2", "4cdee7fa"),
         "vi_crc": ("10986153", "23af308e"), "events": 2402, "dispsrc": (25, 35), "deferred_join": (18, 25),
         "p99_max": (0.003728, 0.583210), "vi_counts": (2370, 6), "superseded": [614, 888, 1172, 1175, 2017, 2018], "pump_skipped": 69793},
}
GLYPH = {
    ("....##..", "...###..", "..####..", "....##..", "....##..", "....##..", "....##..", "........"): "1",
    ("...####.", "..##..##", "......##", ".....##.", "....##..", "...##...", "..######", "........"): "2",
    ("...####.", "..##..##", "......##", "....###.", "......##", "..##..##", "...####.", "........"): "3",
    ("....###.", "...####.", "..##.##.", ".##..##.", ".#######", ".....##.", ".....##.", "........"): "4",
    ("..######", "..##....", "..#####.", "......##", "......##", "..##..##", "...####.", "........"): "5",
    ("....###.", "...##...", "..##....", "..#####.", "..##..##", "..##..##", "...####.", "........"): "6",
}
BLANK = tuple(["........"] * 8)
_C = {}


def path(run, kind):
    if kind in ("qual", "struct"):
        return os.path.join(FX, P + "idxcap-run%d-%s.%s" % (run, kind, "json" if kind == "struct" else "bin"))
    return os.path.join(FX, P + "stream-0015-run%d-%s.bin" % (run, kind))


def struct(run):
    k = ("s", run)
    if k not in _C:
        with open(path(run, "struct"), encoding="utf-8") as f:
            _C[k] = json.load(f)
    return _C[k]


def full(run):
    k = ("f", run)
    if k not in _C:
        _C[k] = vfull.load(path(run, "full"))
    return _C[k]


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "")


def git(*args):
    r = subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, text=True)
    return None if r.returncode != 0 else r.stdout


def kv(line):
    out = {}
    for tok in line.split(" ")[2:]:
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
    return out


def pct(s, q):
    n = len(s)
    return s[min(n - 1, int(n * q))] if n else None


def lum(w):
    return ((w >> 10) & 31) + ((w >> 5) & 31) + (w & 31)


def cell(words, col, row, bg):
    return tuple("".join("#" if abs(lum(words[(row * 8 + dy) * 240 + col * 8 + dx]) - bg) > 20 else "." for dx in range(8)) for dy in range(8))


def read_tally(words):
    """The checker's `%2d` field at console column 22, rows 4..13, by EXACT glyph match; an unknown bitmap raises, never guesses."""
    bg = lum(words[0])
    out = []
    for i in range(10):
        c22, c23 = cell(words, 22, 4 + i, bg), cell(words, 23, 4 + i, bg)
        if c22 == BLANK and c23 == BLANK:
            out.append("blank")
        else:
            if c23 not in GLYPH or (c22 != BLANK and c22 not in GLYPH):
                raise AssertionError("unknown glyph at row %d: %r %r" % (4 + i, c22, c23))
            out.append(("" if c22 == BLANK else GLYPH[c22]) + GLYPH[c23])
    return out


def descriptor_from_source():
    """The ten bit positions of GBP_KEYPAD_DESCRIPTOR, read from its ONE place (never restated here)."""
    code = re.sub(r"/\*.*?\*/", "", read(INPUT_C), flags=re.S)
    m = re.search(r"GBP_KEYPAD_DESCRIPTOR\s*=\s*\{\s*\{([^}]*)\}\s*,\s*(\d+)\s*\}", code)
    assert m, "the descriptor initializer"
    return [int(x) for x in m.group(1).split(",")], int(m.group(2))


def key_lines(run):
    """The KEY lines re-parsed from the verbatim lines the struct quotes (the log itself is not versioned)."""
    k = ("k", run)
    if k not in _C:
        out = []
        for e in struct(run)["key_record"]["lines"]:
            m = KEY_RE.match(e["line"])
            assert m, e["line"]
            out.append({"n": int(m.group(2)), "act": m.group(3), "keys": int(m.group(4), 16), "word": int(m.group(5), 16),
                        "t_poll": int(m.group(6), 16), "t_attempt": int(m.group(7), 16), "t_done": int(m.group(8), 16), "xfer": int(m.group(9)), "rc": m.group(10)})
        _C[k] = out
    return _C[k]


def rising_edges(keys):
    """R_b and the edges, exactly as §V7.3.9 defines them: rc=ok only, n order, from 0000."""
    prev, R, edges = 0, [0] * 16, []
    for kk in keys:
        if kk["rc"] != "ok":
            continue
        for b in range(16):
            if (kk["word"] >> b) & 1 and not (prev >> b) & 1:
                R[b] += 1
                edges.append((kk["t_attempt"], b))
        prev = kk["word"]
    return R, edges


def samples(run):
    k = ("t", run)
    if k not in _C:
        out = []
        for rec in full(run)["records"]:
            words = vfull.consumed_words(rec["raw"])
            bg = lum(words[0])
            try:
                vec = read_tally(words)
            except AssertionError:
                vec = None
            out.append({"rec": rec, "vector": vec, "bg": words[0], "distinct": len(set(words)),
                        "title_lit": sum(1 for y in range(8, 16) for x in range(8, 240) if abs(lum(words[y * 240 + x]) - bg) > 20),
                        "tex_eq": rec["tex"] == vfull.convert_py(rec["raw"])})
        _C[k] = out
    return _C[k]


def v74():
    t = read(HW)
    i = t.index("### V7.4 ")
    j = t.find("### V7.5 ", i)
    return t[i:] if j < 0 else t[i:j]


class TheFixturesAreThePhysicalFiles(unittest.TestCase):
    def test_the_sidecar_fixtures_are_the_archived_bytes(self):
        for run, R in RUNS.items():
            for kind in ("disp", "full", "vi"):
                with self.subTest(run=run, kind=kind):
                    self.assertEqual((os.path.getsize(path(run, kind)), sha(path(run, kind))), R[kind])
            for i in (vdisp.load(path(run, "disp")), vvi.load(path(run, "vi")), full(run)):
                self.assertEqual((i["test_id"], i["build_id"], i["commit"]), ("GBP-VIDEO-004", "stream-0015", CANDIDATE_COMMIT))

    def test_the_qual_projections_name_the_raw_witnesses(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                self.assertEqual(sha(path(run, "qual")), R["qual_sha"])
                q = vqual.load(path(run, "qual"))
                self.assertEqual((q["records_n"], q["src_size"], q["src_sha256"]), (2048, R["idxcap"][0], R["idxcap"][1]))
                self.assertEqual([r["frame_index"] for r in q["records"]], list(range(LO, HI + 1)))
                self.assertTrue(all(r["blocks"] == 40 and r["completeness"] == 1 for r in q["records"]))

    def test_the_struct_carries_the_identities_hashed_on_receipt(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                s = struct(run)
                self.assertEqual((s["format"], s["run"]), ("OGBPIDX-STRUCT-1", run))
                for k in ("log", "idxcap", "disp", "full", "vi"):
                    self.assertEqual((s["raw"][k]["size"], s["raw"][k]["sha256"]), R[k], k)
                    self.assertIn("stream-0015-run%d" % run, s["raw"][k]["archived_as"])
                    self.assertNotIn("run%d" % run, s["raw"][k]["supplied_name"], "the console names carry no run number")
                    self.assertIn("logs/run%d/" % run, s["raw"][k]["found_at"])
                for k in ("disp", "full", "vi", "qual"):
                    self.assertEqual(sha(os.path.join(ROOT, s["fixtures"][k]["path"])), s["fixtures"][k]["sha256"], k)
                self.assertEqual((s["dol"]["size"], s["dol"]["sha256"], s["dol"]["swiss_sha256"], s["dol"]["build"], s["dol"]["commit"]),
                                 (514880, DOL_SHA, DOL_SHA, "stream-0015", CANDIDATE_COMMIT))
                self.assertTrue(s["dol"]["commit_full"].startswith(CANDIDATE_COMMIT))
                self.assertEqual((s["dol"]["stream_0014_preserved"]["sha256"], s["dol"]["stream_0013_preserved"]["sha256"]), (PREV_SHA, OLD13_SHA))
                self.assertEqual(s["github_issues"], {"pre_registration": 28, "hardware": 32, "ingestion": 33, "run16_reservation": 23, "candidate": 27, "topology_inventory": 25})
                self.assertEqual(s["execution_order"]["order"], ["run17", "run18", "run16"])
                self.assertEqual(s["runtime_embedded"], {"test_id": "GBP-VIDEO-004", "build_id": "stream-0015", "commit": CANDIDATE_COMMIT, "note": s["runtime_embedded"]["note"]})
                self.assertIn("cp --update=none", s["raw_receipt"]["archived"])
                self.assertIn("EVERY KEY LINE", s["fixtures"]["raw_log"])
                self.assertEqual(s["evidence_ids"], ["GBP-HW-%d" % n for n in range(266, 272)])
        self.assertIn("mv -n", struct(16)["raw_receipt"]["archived"])
        self.assertEqual(len(struct(16)["retired_names"]["names"]), 5)
        self.assertTrue(all("stream-0014-run16" in n for n in struct(16)["retired_names"]["names"]))

    def test_the_archives_if_present_on_this_host_are_the_recorded_bytes(self):
        # Issue #83 (D): this was already correct -- a `seen` counter and a skip when it stayed
        # zero -- and is written through the shared helper so that the rule "no conditional check
        # without an else" holds with NO exceptions, and its detector needs none either.
        want = {os.path.join(ROOT, struct(run)["raw"][k]["archived_as"]): R[k]
                for run, R in RUNS.items() for k in ("log", "idxcap", "disp", "full", "vi")}
        for p in artifacts.any_of(self, sorted(want), "no local archive on this host (captures/local is ignored)"):
            self.assertEqual((os.path.getsize(p), sha(p)), want[p], p)
        # the retired names never came into existence
        self.assertEqual(glob.glob(os.path.join(ROOT, "captures", "local", "*stream-0014-run16*")), [])
        self.assertEqual(glob.glob(os.path.join(ROOT, "captures", "local", "*unidentified*")), [])


class TheGatesFromTheVerbatimRecords(unittest.TestCase):
    def test_truncated_zero_with_both_envinput_halves_complete_validates_the_repair(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                s = struct(run)
                h = s["log_header"]
                self.assertEqual((h["lines"], h["dropped"], h["truncated"], h["end_dropped"]), (R["lines"], 0, 0, 0))
                v = s["log_records_verbatim"]
                self.assertTrue(v["ENVINPUT"].startswith("000003 ENVINPUT port=1 policy=default stick_threshold=48 trigger_threshold=0 "))
                self.assertTrue(v["ENVINPUT"].endswith("refresh_ms=5 refresh_ticks=202500 layout=gbi-u16-replicated"))
                bits, pressed = descriptor_from_source()
                self.assertEqual(v["ENVINPUT2"], "000004 ENVINPUT2 index=12 desc=%s pressed_is_one=%d desc_status=CORROBORATED_not_FACT selftest=1"
                                 % (",".join(str(b) for b in bits), pressed))
                lens = {tag: len(l) - 7 for tag, l in v.items()}
                self.assertEqual((lens["ENVINPUT"], lens["ENVINPUT2"], max(lens.values())), (170, 105, 218))
                self.assertLess(max(lens.values()), 248)
                self.assertEqual(h["envinput_repair_validated"]["limit"], 248)
                self.assertIn("PHYSICALLY VALIDATES", h["envinput_repair_validated"]["reading"])
                self.assertEqual(h["tag_counts"]["KEY"], R["keylog"]["emitted"])
                self.assertEqual(h["tag_counts"]["ENVINPUT2"], 1)

    def test_the_input_record_reparsed_meets_the_gate(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                s = struct(run)
                f = kv(s["log_records_verbatim"]["INPUT"])
                got = {k: (f[k] if k in ("last_word", "last_rc") else int(f[k])) for k in R["input"]}
                self.assertEqual(got, R["input"])
                self.assertEqual(got["attempts"], got["first"] + got["change"] + got["refresh"] + got["retry"])
                self.assertEqual(got["completed"], got["attempts"])
                self.assertEqual((got["failed"], got["retry"], got["invalid"], got["no_base"]), (0, 0, 0, 0))
                presses = sum(n for _, n in R["walk"])
                self.assertEqual(got["key_changes"], 2 * presses)
                g = s["input_machine_gate"]["gate"]
                self.assertTrue(g["MET"])
                self.assertTrue(all(v for k, v in g.items() if isinstance(v, bool)), g)
                bits, pressed = descriptor_from_source()
                self.assertEqual((g["descriptor_as_data"], g["pressed_is_one"], g["desc_status_as_reported"]), (bits, pressed, "CORROBORATED_not_FACT"))
                self.assertEqual((bits[8], bits[9]), (9, 8), "R -> bit 9, L -> bit 8: the assignment the join measured")
                m = re.match(r"^\d{6} INPUTT write_ticks=(\d+)/(\d+)/(\d+) n=(\d+) step_ticks=(\d+)/(\d+)/(\d+) n=(\d+) units=min/mean/max$", s["log_records_verbatim"]["INPUTT"])
                self.assertEqual(([int(m.group(i)) for i in (1, 2, 3)], int(m.group(4)), int(m.group(8))), ([30, 30, 38], R["input"]["attempts"], R["input"]["steps"]))
                self.assertIn("never a latency claim", s["input_machine_gate"]["INPUTT"]["note"])

    def test_the_key_record_gate_reparsed_from_the_verbatim_lines(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                s = struct(run)
                kl = kv(s["log_records_verbatim"]["KEYLOG"])
                self.assertEqual({k: int(kl[k]) for k in R["keylog"]}, R["keylog"])
                self.assertEqual(kl["emit_ticks"], "%d/%d/%d" % R["emit"])
                keys = key_lines(run)
                self.assertEqual(len(keys), R["keylog"]["emitted"])
                self.assertEqual([k["n"] for k in keys], list(range(1, len(keys) + 1)))
                self.assertTrue(all(k["rc"] == "ok" for k in keys))
                self.assertEqual({k["act"] for k in keys}, {"first", "change"})
                self.assertEqual((keys[0]["act"], keys[0]["word"]), ("first", 0))
                self.assertEqual(len(keys), R["input"]["first"] + R["input"]["change"] + R["input"]["retry"])
                self.assertTrue(all(k["t_poll"] <= k["t_attempt"] <= k["t_done"] for k in keys))
                self.assertTrue(all(a["t_attempt"] < b["t_attempt"] for a, b in zip(keys, keys[1:])))
                self.assertTrue(all(30 <= k["xfer"] <= 37 for k in keys))
                self.assertEqual(("%04x" % keys[1]["keys"], "%04x" % keys[1]["word"]), R["first_change"])
                # every press is a word and its 0000 release; no word outside the walk's buttons
                words = [k["word"] for k in keys[1:]]
                self.assertEqual(words[1::2], [0] * (len(words) // 2))
                allowed = {1 << b for b in R["bits"]}
                self.assertTrue(all(w in allowed for w in words[0::2]), "no navigation word: the machine's answer to how the run booted")
                self.assertTrue(s["key_record"]["gate"]["MET"])
                self.assertEqual(s["key_record"]["words_in_n_order"], ["%04x" % k["word"] for k in keys])

    def test_transport_startup_and_the_witness_window(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                s = struct(run)
                c = kv(s["log_records_verbatim"]["COUNTERS"])
                self.assertEqual({int(c[k]) for k in ("unmasks", "deliveries", "acks", "rearms")}, {R["counters"]})
                self.assertEqual((c["video"], c["overflow"], c["uncertain"], c["control_ok"]), ("96109/96109", "0", "0", "1"))
                st = kv(s["log_records_verbatim"]["STATS"])
                self.assertEqual((int(st["transfers"]), int(st["timeouts"]), int(st["busy"])), (R["transfers"], 0, 0))
                w = kv(s["log_records_verbatim"]["WRITES"])
                self.assertEqual((int(w["irq_attempted"]), int(w["irq_completed"])), (R["irq"], R["irq"]))
                ve = kv(s["log_records_verbatim"]["VSTATE end"])
                self.assertEqual((ve["stop"], ve["errors"], ve["transport_ok"], ve["restore"]), ("witness_target_reached", "0", "1", "ok"))
                sv = kv(s["log_records_verbatim"]["STARTUPV"])
                self.assertEqual(int(sv["ticks_control_to_first_handoff"]), R["first_handoff_ticks"])
                self.assertLess(R["first_handoff_ticks"] * 1000.0 / TB, 400.0)
                we = kv(s["log_records_verbatim"]["WITELIG"])
                self.assertEqual((int(we["ticks_control_to_eligible"]), we["released"], we["still_gated"]), (R["eligible_ticks"], "1", "0"))
                self.assertEqual(kv(s["log_records_verbatim"]["STREAMWIT"])["records"], "2048/2048")
                self.assertEqual(int(kv(s["log_records_verbatim"]["STREAMPUMP"])["skipped_cause_pending"]), R["pump_skipped"])
                self.assertEqual(kv(s["log_records_verbatim"]["STREAMINV"])["failures"], "0")
                self.assertEqual(kv(s["log_records_verbatim"]["ENVSTORE"])["fault"], "-")


class TheJoinRecomputedFromTheTwoMachineRecords(unittest.TestCase):
    """§V7.3.9, applied from the definitions -- then compared with the struct's answers, never read from them."""

    def test_r_b_from_the_key_lines(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                Rb, edges = rising_edges(key_lines(run))
                self.assertEqual({b: Rb[b] for b in range(16) if Rb[b]}, R["bits"])
                self.assertEqual(sum(Rb), sum(n for _, n in R["walk"]))
                j = struct(run)["join"]
                self.assertEqual([j["R_b"]["bit%d" % b] for b in range(16)], Rb)
                self.assertEqual(len(j["rising_edges"]), len(edges))

    def test_the_tally_frames_of_the_join_runs_decode_and_the_end_state_follows_the_rule(self):
        for run in (17, 18):
            with self.subTest(run=run):
                R = RUNS[run]
                i = full(run)
                self.assertEqual((i["records_n"], i["k_cap"], i["spacing"], i["origin"], i["completed"], i["refused"], i["blocks_copied"], i["want_calls"]),
                                 (8, 8, 256, 356, 8, 0, 320, 2377))
                self.assertEqual(("%08x" % i["header_crc32"], "%08x" % i["total_crc32"]), R["full_crc"])
                S = samples(run)
                self.assertEqual([s["rec"]["frame_index"] for s in S], [356 + 256 * k for k in range(8)])
                self.assertTrue(all(vfull.STATE[s["rec"]["state"]] == "COMPLETE" and s["tex_eq"] for s in S))
                self.assertTrue(all(s["title_lit"] == 522 and s["distinct"] == 3 and s["bg"] == 0xC578 and s["vector"] is not None for s in S))
                keys = key_lines(run)
                last_done = max(k["t_done"] for k in keys if k["rc"] == "ok")
                after = [s for s in S if s["rec"]["t_take"] > last_done]
                self.assertGreaterEqual(len(after), 2)
                self.assertTrue(all(s["vector"] == after[0]["vector"] for s in after), "the end state: identical after the last KEY line")
                end = after[0]["vector"]
                self.assertEqual([0 if x == "blank" else int(x) for x in end], R["expected"])
                self.assertEqual(8 - len(after), R["end_from"])
                st = struct(run)["tally_frames"]
                self.assertEqual([s["vector"] for s in S], [x["vector_as_read"] for x in st["samples"]], "the struct's readings are the recomputed ones")
                self.assertEqual(st["glyph_table"], {v: list(k) for k, v in GLYPH.items()})
                j = struct(run)["join"]
                self.assertEqual((j["end_state_exists"], j["end_state_vector_as_read"], j["samples_after_last_key_line"]), (True, end, [s["rec"]["sample_index"] for s in after]))
                # the partials advance in the walk's order and never decrease
                order = [b for b, _ in R["walk"]]
                prev = [0] * 10
                for s in S:
                    cur = [0 if x == "blank" else int(x) for x in s["vector"]]
                    self.assertTrue(all(c >= p for c, p in zip(cur, prev)))
                    moved = {LABELS[k] for k in range(10) if cur[k] > 0}
                    self.assertEqual(moved, set(order[:len(moved)]))
                    prev = cur

    def test_question_j_is_fact_for_every_pressed_bit_of_both_join_runs(self):
        for run in (17, 18):
            with self.subTest(run=run):
                R = RUNS[run]
                Rb, _ = rising_edges(key_lines(run))
                pressed = [b for b in range(16) if Rb[b]]
                S = samples(run)
                end = S[-1]["vector"]
                T = {LABELS[k]: (0 if end[k] == "blank" else int(end[k])) for k in range(10)}
                totals = {}
                for b in pressed:
                    totals.setdefault(Rb[b], []).append(b)
                self.assertTrue(all(len(v) == 1 for v in totals.values()), "pairwise distinct totals")
                verdict = {}
                for b in pressed:
                    cs = [c for c, t in T.items() if t == Rb[b]]
                    self.assertEqual(len(cs), 1, "exactly one counter reads R_b")
                    verdict[b] = "FACT" if cs[0] == C_OF_B[b] else "FACT-SWAPPED"
                self.assertEqual(set(verdict.values()), {"FACT"})
                self.assertEqual(sorted(verdict), sorted(R["bits"]))
                self.assertEqual(sum(T.values()), sum(Rb), "the sums agree")
                self.assertEqual([c for c, t in T.items() if t and t not in {Rb[b] for b in pressed}], [], "no counter moved by a value no pressed bit was sent")
                self.assertTrue(all(end[k] == "blank" for k in range(10) if R["expected"][k] == 0), "every unpressed counter blank")
                j = struct(run)["join"]
                self.assertEqual({int(k[3:]): v["verdict"] for k, v in j["question_J_per_bit"].items()}, verdict)
                self.assertEqual((j["closed"], j["sum_R_b_eq_sum_T_c"], j["T_c"]), (True, True, T))
                v = struct(run)["verdicts"]
                self.assertTrue(v["question_J_all_pressed_bits_FACT"])
                self.assertIn("no longer in the chain", v["routing_classification"]["no_human_link"])
        # across the two join runs every word bit 0..9 is bound, bits 8 and 9 in both
        both = {b for b in RUNS[17]["bits"]} & {b for b in RUNS[18]["bits"]}
        self.assertEqual(both, {8, 9})
        self.assertEqual(set(RUNS[17]["bits"]) | set(RUNS[18]["bits"]), set(range(10)))
        self.assertEqual((RUNS[17]["pad"], RUNS[18]["pad"]), ("GENERIC", "ORIGINAL"), "bits 8 and 9 on two independent controllers")

    def test_question_i_is_exact_in_every_interval_under_the_pre_registered_convention(self):
        FRAME = TB / SRC_HZ
        for run in (17, 18):
            with self.subTest(run=run):
                _, edges = rising_edges(key_lines(run))
                S = samples(run)
                bounds = [None] + [s["rec"]["t_take"] for s in S]
                vecs = [[0] * 10] + [[0 if x == "blank" else int(x) for x in s["vector"]] for s in S]
                statuses = []
                for i in range(len(S)):
                    lo, hi = bounds[i], bounds[i + 1]
                    inc = {LABELS[k]: vecs[i + 1][k] - vecs[i][k] for k in range(10) if vecs[i + 1][k] != vecs[i][k]}
                    sent, near = {}, 0
                    for t, b in edges:
                        if (lo is None or t > lo) and t <= hi:
                            sent[C_OF_B[b]] = sent.get(C_OF_B[b], 0) + 1
                            near += hi - t < B_FRAMES * FRAME
                    statuses.append("EXACT" if inc == sent else "OTHER")
                    self.assertEqual(near, 0, "no press within B of a boundary: no latency observation arises")
                self.assertEqual(statuses, ["EXACT"] * 8)
                q = struct(run)["join"]["question_I"]
                self.assertEqual((q["statuses"], q["all_exact"]), (statuses, True))
                self.assertIn("NOT a latency figure", q["convention"])

    def test_the_two_channels_agree_digit_for_digit_and_are_kept_apart(self):
        for run in (17, 18):
            with self.subTest(run=run):
                R = RUNS[run]
                s = struct(run)
                self.assertEqual(s["operator_report"]["tally_vector"], R["operator"])
                machine = [0 if x == "blank" else int(x) for x in samples(run)[-1]["vector"]]
                self.assertEqual(machine, R["operator"], "agreement, stated -- never merged")
                self.assertIn("OPERATOR OBSERVATION", s["operator_report"]["source"])
                self.assertIn("never fed into the join", s["operator_report"]["source"])
                v = s["verdicts"]
                self.assertEqual((v["question_M"]["verdict"], v["question_O"]["verdict"], v["channels_agree"]), ("PASS", "AS-ASSIGNED", True))
                self.assertIn("alone", v["question_M"]["read_from"])

    def test_run_16_is_undecided_by_the_rule_its_frames_are_the_menu_and_nothing_is_inferred(self):
        Rb, _ = rising_edges(key_lines(16))
        self.assertEqual({b: Rb[b] for b in range(16) if Rb[b]}, {8: 8, 9: 8}, "4 + 4 presses each: not distinct")
        words = [k["word"] for k in key_lines(16)[1:]][0::2]
        self.assertEqual(words, [0x0200] * 4 + [0x0100] * 4 + [0x0200] * 4 + [0x0100] * 4, "exactly the declared 4xR, 4xL, 4xR, 4xL")
        s = struct(16)
        self.assertEqual({int(k[3:]): v["verdict"] for k, v in s["join"]["question_J_per_bit"].items()}, {8: "UNDECIDED", 9: "UNDECIDED"})
        self.assertFalse(s["join"]["closed"])
        S = samples(16)
        self.assertTrue(all(vfull.STATE[x["rec"]["state"]] == "COMPLETE" and x["tex_eq"] for x in S))
        self.assertEqual([x["vector"] for x in S], [None] * 8, "the reader aborts on every sample: the menu, not the checker")
        self.assertEqual((S[0]["distinct"], S[0]["bg"]), (3, 0xF7BD), "s0 a near-blank screen")
        self.assertTrue(all(x["bg"] == 0x829A and x["distinct"] > 50 for x in S[1:]), "s1..s7 the menu")
        self.assertFalse(s["tally_frames"]["applicable"])
        ab = s["tally_frames"]["reader_abort"]
        self.assertEqual((ab["sample_index"], ab["row"], ab["label"]), (0, 9, "RIGHT"))
        self.assertNotIn(tuple(ab["col22"]), GLYPH)
        self.assertIn("NOT read here", s["tally_frames"]["content_blind_facts"]["note"])
        v = s["verdicts"]
        self.assertEqual((v["question_M"]["verdict"], v["question_O"]["verdict"]), ("PASS", "NOT READABLE"))
        self.assertIn("NOT inferred", v["question_O"]["reading"])
        op = s["operator_report"]
        self.assertIn("as abas funcionaram perfeitamente", op["report_literal"])
        self.assertIn("NOT separately reported", op["direction_per_trigger"])
        self.assertIn("the verdict WORKING", s["join"]["reading"])

    def test_the_topology_is_declared_per_run_and_the_absent_items_are_recorded_as_absent(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                tp = struct(run)["topology_declared_by_operator"]
                self.assertIn(R["pad"], tp["controller"])
                self.assertIn("DECLARED per run", tp["controller"])
                # Issue #35 (2026-09-21) recorded the Operator's declaration after the ingestion, keeping the absent note as history
                self.assertIn("DECLARED by the Operator after the ingestion (Issue #35", tp["bba_ethernet"])
                self.assertIn("RECORDED AS ABSENT, NOT INFERRED", tp["declaration_history"])
                self.assertIn("DECLARED by the Operator after the ingestion (Issue #35", tp["display_chain"])
                self.assertEqual(tp["deviation_reported"], "none")
                self.assertIn("DECLARED HARDWARE INVENTORY", tp["console"])
                self.assertEqual(kv(struct(run)["log_records_verbatim"]["ENVINPUT"])["trigger_threshold"], "0")
        self.assertIn("MENU", struct(16)["topology_declared_by_operator"]["cartridge_boot_screen"])
        self.assertIn("straight into", struct(17)["topology_declared_by_operator"]["cartridge_boot_screen"])
        self.assertIn("TWO independent controllers", struct(18)["topology_declared_by_operator"]["controller_scope"])


class TheVideoPathRecordedNotJudged(unittest.TestCase):
    def test_vfull_is_inconclusive_by_construction_and_the_containers_are_intact(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                a = vfull.analyse(full(run), use_c=False)
                self.assertEqual((a["verdict"], len(a["samples"])), ("INCONCLUSIVE", 8))
                o = struct(run)["official_vfull"]
                self.assertEqual((o["verdict"], o["texture_equals_convert_py"], o["completed"]), ("INCONCLUSIVE", "8/8", 8))
                v = struct(run)["official_vindex"]
                self.assertEqual((v["verdict"], v["observed"], v["intact"], v["counts"], v["every_record_all_40_blocks"]),
                                 ("INCONCLUSIVE_TOO_FEW_INTACT_FRAMES", 2048, 0, {"INVALID_CANONICAL_STRIP": 2048}, True))
                self.assertEqual((v["header_crc32"], v["total_crc32"]), R["idx_crc"])
        self.assertEqual(struct(17)["records_uniform"]["deviations"], [])
        self.assertEqual(struct(18)["records_uniform"]["deviations"], [])
        dev = struct(16)["records_uniform"]["deviations"]
        self.assertEqual([d["frame_index"] for d in dev], list(range(357, 411)), "RUN 16: the boot-screen frames before the menu carry `sync`")
        self.assertTrue(all("sync" in d["invalid_by_reason"] for d in dev))

    def test_vdisp_and_policy_a_recomputed(self):
        D = {v: k for k, v in vdisp.DISPOSITION.items()}
        LF = {name: bit for bit, name in vdisp.LF}
        for run, R in RUNS.items():
            with self.subTest(run=run):
                i = vdisp.load(path(run, "disp"))
                self.assertTrue(vdisp.usable(i)["usable_for_disposition_claim"])
                self.assertEqual((i["life_overflow"], i["event_overflow"], i["drawdone_unmatched"], i["order_violations"]), (0, 0, 0, 0))
                self.assertEqual((i["life_n"], i["decisions"], i["event_n"], i["source_deferred_frames"], i["source_defer_attempts"], i["max_deferred_depth"]),
                                 (2378, 2377, R["events"], R["dispsrc"][0], R["dispsrc"][1], 1))
                self.assertEqual(("%08x" % i["header_crc32"], "%08x" % i["total_crc32"]), R["disp_crc"])
                life = {r["frame_index"]: r for r in i["life"] if r["frame_index"] != vdisp.KEY_NONE}
                joined = [k for k in range(LO, HI + 1) if k in life]
                self.assertEqual((len(joined), [k for k in range(LO, HI + 1) if k not in life]), (2047, [HI]))
                J = [life[k] for k in joined]
                self.assertTrue(all(r["disposition"] == D["SELECTED_NEW"] for r in J))
                self.assertEqual([r["frame_index"] for r in sorted(J, key=lambda r: r["t_decision"])], list(range(LO, HI)))
                dd = [r for r in J if r["life_flags"] & LF["EVER_DEFERRED"]]
                self.assertEqual((len(dd), sum(r["defer_attempts"] for r in dd)), R["deferred_join"])
                lat = sorted(r["t_decision"] - r["t_convert_done"] for r in J)
                p99, mx = pct(lat, 0.99) * 1000.0 / TB, lat[-1] * 1000.0 / TB
                self.assertAlmostEqual(p99, R["p99_max"][0], places=5)
                self.assertAlmostEqual(mx, R["p99_max"][1], places=5)
                self.assertLessEqual(mx, 2.5)
                rt = [life[k]["retrace_decision"] for k in joined]
                d = [b - a for a, b in zip(rt, rt[1:])]
                self.assertEqual({k: d.count(k) for k in set(d)}, {1: 2039, 2: 7})
                pa = struct(run)["policy_a"]
                self.assertEqual((pa["joined"], pa["interior_drops"], pa["reorder"], pa["deferred_join"]), (2047, 0, 0, list(R["deferred_join"])))
                self.assertEqual(set(pa["gates"].values()), {"PASS"})

    def test_the_corrected_vi_model(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                v = vvi.load(path(run, "vi"))
                self.assertEqual((v["records_n"], v["handed"], v["latched"], v["superseded"], v["overflow"], v["awaiting_at_end"]),
                                 (2377, 2377, R["vi_counts"][0], R["vi_counts"][1], 0, 2376))
                self.assertEqual(("%08x" % v["header_crc32"], "%08x" % v["total_crc32"]), R["vi_crc"])
                self.assertEqual([r["frame_index"] for r in v["records"] if r["superseded"]], R["superseded"])
                latched = [r for r in v["records"] if r["latched"]]
                rc = [vvi.regs_consistent(r) for r in latched]
                self.assertEqual((sum(1 for t, _, _ in rc if t), sum(1 for _, b, _ in rc if b)), (len(latched), len(latched)))
                self.assertEqual(sorted({r["phys"] for r in latched}), [0x013aa640, 0x01440660])
                self.assertTrue(all(r["retrace_latch"] - r["retrace_handed"] == 1 for r in latched))


class TheDocumentsAndTheFreeze(unittest.TestCase):
    def test_v7_4_follows_v7_3_with_twelve_parts_and_the_chapter_heading_carries_the_result(self):
        t = read(HW)
        self.assertEqual((t.count("### V7.3 "), t.count("### V7.4 "), t.count("\n## V7 ")), (1, 1, 1))
        self.assertLess(t.index("### V7.3 "), t.index("### V7.4 "))
        s = v74()
        pos = [s.index("#### V7.4.%d " % n) for n in range(1, 13)]
        self.assertEqual(pos, sorted(pos))
        self.assertNotIn("#### V7.4.13 ", s)
        head = s.splitlines()[0]
        for tok in ("RESULT, ingested 2026-09-21 (GitHub Issue #33)", "QUESTION J = FACT", "two independent controllers", "physical FACT (hw, the runs)",
                    "QUESTION I EXACT", "RUN 16", "UNDECIDED", "Question O NOT READABLE", "truncated=0"):
            self.assertIn(tok, head, tok)
        v7 = [l for l in t.splitlines() if l.startswith("## V7 ")][0]
        for tok in ("EXECUTED 2026-09-21 (Hardware Issue #32) AND INGESTED (Issue #33, §V7.4)", "QUESTION J = FACT FOR ALL TEN WORD BITS",
                    "THE ROUTING A PHYSICAL FACT (hw, the runs)", "RUN 16 EXECUTED LAST", "GBP-KEY-008 VALIDATED"):
            self.assertIn(tok, v7, tok)
        f = plain(s)
        for tok in ("1, 2, 0, 0, 0, 0, 6, 5, 3, 4", "1, 2, 3, 4, 5, 6, 0, 0, 0, 0", "as abas funcionaram perfeitamente", "NOT separately reported",
                    "run17 14:13:32, run18 14:19:30, run16 14:22:08", "RETIRED", "PHYSICALLY VALIDATED", "no human count", "EXACT, 8 of 8",
                    "RECORDED AS ABSENT, NOT INFERRED", "está fazendo o boot semelhante ao comportamento do Startup disc e GBI", "Phase 9 work, not started",
                    "the verdict WORKING", "NOT READABLE", "byte-identical to 09f289c", "NOT assessed"):
            self.assertIn(tok, f, tok)
        self.assertEqual(s.count("FACT-SWAPPED none; NOT CLOSED none; UNDECIDED none; the join CLOSED, both runs"), 1)
        # the reserved run17 / run18 names appear once, in §V7.3.5; the run16 names once, in §V7.4.3; the retired names once, in §V7.1.5
        for n in ("captures/local/GBP-VIDEO-004_stream-0015-run17.log", "captures/local/GBP-VIDEO-004_stream-0015-run18-full.bin",
                  "captures/local/GBP-VIDEO-004_stream-0015-run16.log", "captures/local/GBP-VIDEO-004_stream-0015-run16-vi.bin",
                  "captures/local/GBP-VIDEO-004_stream-0014-run16.log"):
            self.assertEqual(t.count(n), 1, n)
            self.assertEqual(read(HANDOFF).count(n), 1, n)

    def test_v7_1_to_v7_3_are_byte_identical_to_the_base_and_the_heading_only_grew(self):
        old = guards.show(BASE_COMMIT, "docs/research/HARDWARE_TESTS.md")  # Issue #83 (B): absent COMMIT skips, absent PATH fails
        new = read(HW)
        self.assertEqual(new[new.index("### V7.1 "):new.index("### V7.4 ")].rstrip("\n"), old[old.index("### V7.1 "):].rstrip("\n"))
        old_head = [l for l in old.splitlines() if l.startswith("## V7 ")][0]
        new_head = [l for l in new.splitlines() if l.startswith("## V7 ")][0]
        self.assertTrue(new_head.startswith(old_head))
        self.assertEqual(old[:old.index("\n## V7 ")], new[:new.index("\n## V7 ")], "nothing before the V7 chapter moved")

    def test_the_evidence_rows_exist_once_and_carry_the_identities_and_the_promotion(self):
        ev = read(EVIDENCE)
        for n in range(266, 272):
            self.assertEqual(len(re.findall(r"^### GBP-HW-%d " % n, ev, re.M)), 1, n)
        self.assertEqual(max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 317)   # 272: Issue #46 (the CONTROL bit 0x02 split, FACT for the split / HYPOTHESIS for the cause)   # 285…294: Issue #62 (RUN 30 ingested, §V8.13)   # 295…300: Issue #67 (RUN 31 ingested, §V9.15); 301…302: #67's validation (the rate/layout split, U-GBP-039's probe); 303…307: #72, RUN 32; 308…311: #78, RUN 33 and RUN 34; 312: #79, duty()'s mechanism; 313: #80, the H-PWM decode; 314…316: #82, the block structure and the drain (§V18); 317: #84, the start-up stall invariance (§V19.11)
        b266 = ev[ev.index("### GBP-HW-266 "):ev.index("### GBP-HW-267 ")]
        for run, R in RUNS.items():
            for k in ("log", "idxcap", "disp", "full", "vi"):
                self.assertIn("`%s…`" % R[k][1][:8], b266, (run, k))
        self.assertIn("RETIRED", b266)
        self.assertIn("recorded as ABSENT", b266)
        heads = {n: ev[ev.index("### GBP-HW-%d " % n):].splitlines()[0] for n in range(266, 272)}
        self.assertIn("FACT (artifacts, identity, order) · OPERATOR OBSERVATION (declarations)", heads[266])
        self.assertIn("GBP-KEY-008's repair physically validated", heads[267])
        self.assertIn("OPERATOR OBSERVATION (literal, relayed by the Orchestrator)", heads[268])
        self.assertIn("FACT (data, recomputable)", heads[269])
        self.assertIn("FACT (the verdict record) · FACT (hw, the runs: the routing)", heads[270])
        self.assertIn("OPERATOR OBSERVATION (qualitative, not a measurement", heads[271])
        k4 = ev[ev.index("## GBP-KEY-004 "):].splitlines()[0]
        self.assertIn("the physical routing NOT established", k4, "the static result's heading kept")
        self.assertIn("2026-09-21, Issue #33: the physical routing ESTABLISHED as FACT (hw, the runs)", k4)
        body4 = ev[ev.index("## GBP-KEY-004 "):ev.index("## GBP-KEY-005 ")]
        self.assertIn("**2026-09-21, Issue #33 (the falsifier's outcome; promotion):**", body4)
        self.assertIn("with no human count in the chain", body4)
        for k, tok in ((8, "REPAIRED and PHYSICALLY VALIDATED"), (9, "the run happened and the join closed"), (10, "EXECUTED on hardware")):
            block = ev[ev.index("## GBP-KEY-%03d " % k):]
            block = block[:block.index("\n## ", 1)]
            self.assertIn(tok, block, k)
        u = read(UNKNOWNS)
        h = re.search(r"^## U-GBP-010\b.*$", u, re.M).group(0)
        self.assertIn("CLOSED 2026-09-21", h)
        self.assertIn("Issue #33: the routing FACT (hw, the runs)", h)
        self.assertIn("stays CLOSED", h)

    def test_the_consolidated_pages_carry_f_with_their_history_and_the_two_pad_scope(self):
        regs = read(os.path.join(ROOT, "docs", "protocol", "REGISTERS.md"))
        row = [l for l in regs.splitlines() if l.startswith("| 0xC | KEYPAD |")][0]
        for tok in ("L/R bit order: F (hw, run-scoped) since 2026-09-21", "C — was H until 2026-09-21", "GBP-HW-270", "no human count in the chain", "then not FACT"):
            self.assertIn(tok, row, tok)
        s23 = regs[regs.index("### 2.3 KEYPAD word"):regs.index("## 3. CONTROL register bits")]
        self.assertIn("**F (hw, run-scoped) since 2026-09-21** — RUN 17 (generic pad) and RUN 18 (original pad) bound bit 8 to L and bit 9 to R", s23)
        self.assertIn("History — C, not FACT (was H until 2026-09-21)", s23)
        self.assertIn("RUN 17 bound bits 0–3 (A, B, SELECT, START) and RUN 18 bits 4–7", s23)
        g = read(os.path.join(ROOT, "docs", "hardware", "GBS-DOL.md"))
        row = [l for l in g.splitlines() if l.startswith("| Keypad injection |")][0]
        for tok in ("F (hw, run-scoped; L/R order) since 2026-09-21", "history: **C (L/R order)** — H until 2026-09-21", "GBP-HW-270", "original Nintendo pad"):
            self.assertIn(tok, row, tok)
        a = read(os.path.join(ROOT, "docs", "hardware", "ARCHITECTURE.md"))
        row = [l for l in a.splitlines() if l.startswith("| Keypad |")][0]
        for tok in ("F (hw, run-scoped) for the L/R order since 2026-09-21", "history: C, not FACT", "five runs", "GBP-HW-270", "../protocol/INPUT.md"):
            self.assertIn(tok, row, tok)
        ini = read(os.path.join(ROOT, "docs", "protocol", "INITIALIZATION.md"))
        s15 = ini[ini.index("## 15. KEYPAD written on hardware"):]
        self.assertIn("CORROBORATED, not FACT, for the\nL/R order", s15, "the history kept")
        self.assertIn("is history from\nthat point", s15)
        self.assertIn("a physical FACT (hw, the runs), on two controllers (GBP-HW-270)", s15)
        ip = read(os.path.join(ROOT, "docs", "protocol", "INPUT.md"))
        for tok in ("the routing FACT after GBP-INPUT-002, the same day", "**The L/R order is a physical FACT (hw, the runs) since 2026-09-21 — and was\nCORROBORATED, not FACT, until the join later that day.**",
                    "F (hw, run-scoped) **since 2026-09-21** — RUN 17 (generic pad) and RUN 18 (original pad) each bound bit 8 to L and bit 9 to R",
                    "bits 0–3 are bound on the generic pad only\nand bits 4–7 on the original only", "RUN 16's direction per trigger (not\nreported, not inferred)",
                    "GBP-HW-270"):
            self.assertIn(tok, ip, tok)
        self.assertNotIn("| C, not FACT — the paragraph below is part of this row |", ip)
        self.assertNotIn("**The L/R order is CORROBORATED, not FACT.**", ip)
        self.assertNotIn("executed nowhere yet", ip)

    def test_roadmap_handoff_devlog_and_readme_carry_the_executed_state(self):
        r = plain(read(ROADMAP))
        for tok in ("EXECUTED AGAIN 2026-09-21 — RUN 17, RUN 18 and RUN 16 on stream-0015, GBP-INPUT-002", "Executed and ingested 2026-09-21 (GitHub Issues #32, #33)",
                    "The routing of the KEYPAD word to the AGB's keys is a physical FACT (hw, the runs)", "the acceptance criterion still NOT assessed"):
            self.assertIn(tok, r, tok)
        self.assertIn("Pre-registered 2026-09-21 (GitHub Issue #28)", r, "the pre-registration paragraph kept as history")
        h = read(HANDOFF)
        for tok in ("**Phase 5 — Input, implemented and physically executed (GBP-INPUT-001, GBP-INPUT-002: the routing FACT)**",
                    "**GBP-INPUT-002 image, EXECUTED**", "issue 32", "issue 33",
                    "That `stream-0015` is still unexecuted, or that the routing is still only", "That RUN 14 / RUN 15 made the L/R routing a FACT, or that RUN 16 answered",
                    "That the KEYPAD L/R routing is a physical FACT beyond the runs' scope", "history, not to be rewritten",
                    "the five stream-0014-run16 names in\nthe block above are RETIRED", "recorded absent, not inferred"):
            self.assertIn(tok, h, tok)
        d = read(DEVLOG)
        i = d.rindex("## 2026-09-21 — Issue #33")
        e = d[i:]
        for tok in ("Question J = FACT, all twelve readings", "UNDECIDED by the rule", "GBP-KEY-008's repair physically validated", "GBP-HW-266…271",
                    "recorded as absent, not inferred", "no hardware, no code, no gate change", "not pre-registered"):
            self.assertIn(tok, e, tok)
        rd = read(README)
        for run in RUNS:
            for name in ("stream-0015-run%d-disp.bin", "stream-0015-run%d-full.bin", "stream-0015-run%d-vi.bin", "idxcap-run%d-qual.bin"):
                self.assertIn("`" + P + name % run + "`", rd, name)

    def test_nothing_under_the_untouchable_paths_changed_against_the_base(self):
        if not guards.base_available(BASE_COMMIT):
            self.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % BASE_COMMIT)
        changed = guards.changed_since(BASE_COMMIT, ["src", "poc", "tools", "Makefile", "stimulus"])   # Issue #29: tracked AND untracked, one implementation
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
        # Issue #79 (2026-09-23): tools/v16bitgate.py, QUESTION V repaired at bit resolution and
        # QUESTION L, frozen forward only; it imports v11sweep and edits nothing.
        changed = changed - {"tools/v16bitgate.py"}
        # Issue #80 (2026-09-23): tools/v17pred.py (the predictions, frozen first) and
        # tools/v17decode.py (the H-PWM decoder); they read the captures and touch no image.
        changed = changed - {"tools/v17pred.py", "tools/v17decode.py"}
        # Issue #81 (2026-09-23): the AUDIO decode as runtime code -- src/audio/ (the decoder, the
        # replay backend, the 125/16 resampler and its generated table), its generator
        # tools/gen_aresamp.py, and RUN 33 / RUN 34's raw sidecars versioned as fixtures. Host-tested
        # only: no image links src/audio/, and no POC, slot or runtime path changed.
        changed = changed - {"src/audio/gbp_adec.c", "src/audio/gbp_adec.h", "src/audio/gbp_asrc.c",
                             "src/audio/gbp_asrc.h", "src/audio/gbp_aresamp.c", "src/audio/gbp_aresamp.h",
                             "src/audio/gbp_aresamp_coef.h", "tools/gen_aresamp.py", "captures/README.md",
                             "captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz",
                             "captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run34-audio.bin.gz"}
        # Issue #82 (2026-09-23): tools/v18block.py, what one AUDIO block contains, measured on the
        # versioned fixtures (§V18). Descriptive, no gate; it reads captures and touches no image.
        changed = changed - {"tools/v18block.py"}
        # Issue #84 (2026-09-23): tools/v19drain.py, §V19's three gates, FROZEN BEFORE the run
        # (GBP-AUDIO-005). Synthetic vectors only; it reads no capture and authorises nothing.
        changed = changed - {"tools/v19drain.py"}
        # Issue #84: src/audio/gbp_adrain.* -- GBP-AUDIO-005's phase machine and coverage
        # counter, host-tested only (tests/unit/test_gbp_adrain.c). No image links it yet.
        changed = changed - {"src/audio/gbp_adrain.c", "src/audio/gbp_adrain.h"}
        # Issue #84 (2026-09-23) BUILT GBP-AUDIO-005's image, drain-0001 (§V19.11 A4.1): play-0001 plus
        # the drain's period decoder (src/audio/gbp_aperiod.*, host-tested), the POC that carries it, and
        # tools/v19report.py, the log -> report builder frozen before the run. The service path gains two
        # optional hooks, NULL in every earlier build (tests/unit/test_gbp_video_state.c proves the operation
        # stream identical), and tests/host/test_drain_image.py diffs the image against play-0001.
        changed = changed - {"poc/gbp-audio-drain-probe/Makefile", "poc/gbp-audio-drain-probe/source/main.c",
                             "src/audio/gbp_aperiod.c", "src/audio/gbp_aperiod.h", "tools/v19report.py"}
        # Issue #87 (2026-09-23) restored `make build` at HEAD: since #59 the service module references the
        # AUDIO window, so these four POCs link gbp_awin.c the way they link gbp_vwitness.c, cfg.awin NULL.
        # No executed artifact is rebuilt or relabelled; tests/host/test_poc_link_closure.py keeps the class
        # from recurring unobserved.
        changed = changed - {"poc/gbp-play-session/Makefile", "poc/gbp-video-stream-probe/Makefile",
                             "poc/gbp-video-state-probe/Makefile", "poc/gbp-video-color-probe/Makefile"}
        # Issue #86 (2026-09-23) BUILT AOUT-HW-001, the OUTPUT-PATH image (not a GBP audio test): the
        # listening sequence (src/audio/gbp_alisten.*, bit-identical to the #80/#81 reference on RUN 33,
        # tests/host/test_audio_listen.py) and the POC that plays it through the AI. No GBP code is linked
        # into it (the `aout` audit profile), and no runtime path, image or slot changed.
        changed = changed - {"src/audio/gbp_alisten.c", "src/audio/gbp_alisten.h",
                             "poc/audio-output-replay/Makefile", "poc/audio-output-replay/source/main.c",
                             "poc/audio-output-replay/source/fixture_embed.S",
                             # §V21.6: aout-0002's sealed play order, drawn and committed before the code
                             "poc/audio-output-replay/source/aout_order.h"}
        # Issue #62 (2026-09-22) ingested RUN 30 and needed two READERS that did not exist: awinparse.py,
        # a strict parser for the OGBPAW1 sidecar, and tprime.py, §V7.9's decision rule. Both only read and
        # report; the VERDICT constructions stay in tools/v8audio.py, which tests/host/test_run30.py diffs
        # against the commit that wrote it.
        changed = changed - {"tools/awinparse.py", "tools/tprime.py"}
        # Issue #59 (2026-09-22) BUILT the image §V8 needs: the AUDIO window and its OGBPAW1 sidecar
        # (src/gbp/gbp_awin*, host-testable, no libogc) and the POC that carries them, stream-0016. The
        # service path gains ONE optional config field and ONE call after the AUDIO drain and its commit;
        # no device operation is added, removed or reordered (tests/host/test_awin_image.py diffs it).
        changed = changed - {"src/gbp/gbp_awin.c", "src/gbp/gbp_awin.h",
                             "src/gbp/gbp_awindump.c", "src/gbp/gbp_awindump.h",
                             "poc/gbp-audio-window-probe/Makefile",
                             "poc/gbp-audio-window-probe/source/main.c"}
        # Issue #50 (2026-09-22) made §V7.6.11's frozen verdicts executable BEFORE RUN 21 / RUN 22's logs
        # existed: tools/v7611.py recomputes them and is exercised on SYNTHETIC vectors only, so the
        # ingestion cannot tune the constructions to the data. It reads no run and changes nothing.
        changed = changed - {"tools/v7611.py"}
        # Issue #58 (2026-09-22) pre-registered Phase 6's first physical run (§V8, GBP-AUDIO-001) and made its
        # three-model predictions executable BEFORE any build or log existed: tools/v8audio.py is exercised on
        # SYNTHETIC vectors only, reads no run, authorises nothing and promotes nothing.
        changed = changed - {"tools/v8audio.py"}
        # Issue #29 (2026-09-21) added the promotion sweep tool; it reads the pages and judges nothing, and
        # Issue #44 (2026-09-22) hardened the staging tool against destroying a frozen slot: the manifest gained a frozen_sha256 column
        changed = changed - {"tools/reconcile.py", "tools/swiss_export.py", "tools/swiss-layout.tsv"}
        # Issue #39 (2026-09-21) built the playable image: the session end in the service-path module (tests/host/test_play_image.py pins it), a new POC, its audit profile and its Swiss slot
        self.assertTrue(changed <= {"src/gbp/gbp_vstate_probe.c", "src/gbp/gbp_vstate_probe.h", "src/gbp/gbp_session.c", "src/gbp/gbp_session.h", "poc/gbp-play-session/Makefile", "poc/gbp-play-session/source/main.c", "tools/poc_audit.py", "tools/swiss-layout.tsv", "Makefile"}, "changed against the base: " + " ".join(sorted(changed)))
        changed2 = guards.changed_since(BASE_COMMIT, ["captures/fixtures"])   # Issue #29: tracked AND untracked, one implementation
        # Issue #81 (2026-09-23): RUN 33 / RUN 34's raw audio sidecars, versioned as replay fixtures
        # (captures/README.md); the first fixtures since RUN 18, and they touch none of the above.
        changed2 = changed2 - {"captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz",
                               "captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run34-audio.bin.gz"}
        for line in sorted(changed2):
            self.assertRegex(line, r"-run1[678]-", "only the RUN 16 / 17 / 18 fixtures were added: " + line)
        changed3 = guards.changed_since(BASE_COMMIT, ["docs/protocol", "docs/hardware"])   # Issue #29: tracked AND untracked, one implementation
        self.assertTrue(changed3 <= {"docs/protocol/INPUT.md", "docs/protocol/REGISTERS.md", "docs/protocol/INITIALIZATION.md",
                                                  "docs/hardware/GBS-DOL.md", "docs/hardware/ARCHITECTURE.md"}, " ".join(sorted(changed3)))


if __name__ == "__main__":
    unittest.main()
