"""
tests/host/test_run14.py — RUN 14 and RUN 15: GBP-INPUT-001, the first physical
KEYPAD writes, on the unchanged stream-0014 (0ff8355) with the Enhanced Control
Checker's counted walks A and B; pre-registered HARDWARE_TESTS §V7.1 (Issue #20,
amended before hardware by Issue #23), executed under Hardware Issue #21,
ingested under Issue #24 (result §V7.2). Preserved as fixtures.

Both verdicts are read from §V7.1.9 as frozen before the runs and were fixed by
the Orchestrator before this ingestion: Question M = PASS and Question O =
AS-ASSIGNED in both runs. Everything here is RECOMPUTED from the versioned
fixtures, never restated: the INPUT machine gate re-parsed from the verbatim
summary records and its arithmetic; the ENVINPUT clip re-derived by rendering
the source format string; the tally vectors re-decoded from the OGBPFULL1 bytes
with the frozen tools/vfull.py parser and an exact glyph match; the two
channels (the Operator's vector, the machine vector) compared and kept apart;
Policy A, vdisp, the corrected vvi and vfull recomputed; §V7.1 byte-identical
to the last commit that changed it; nothing under the untouchable paths moved.
No test consults the Operator's report to decide a machine fact, and no test
promotes the routing beyond CORROBORATED.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import unittest

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
MAIN = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c")
INPUT_C = os.path.join(ROOT, "src", "gbp", "gbp_input.c")
TB = 40500000
LO, HI = 356, 2403
LABELS = ["L", "R", "UP", "DOWN", "LEFT", "RIGHT", "START", "SELECT", "A", "B"]
DOL_SHA = "ef76a170c10d335e62c017e53f74c60e410e44f5ce2fbca6774ab43c68ec0b9c"
OLD_SHA = "5391c3fe962dc4b2f4e493f3846ac7407ded064c58f5d4bb583a51e5a725dd79"
CHECKER_COMMIT = "76924c1371d7bf761f8b1ed45ab36f195cd1374f"
CHECKER_SHA = "53c212c73e814875fcbac16a4dc22ea5d6c752f85cdddc433db97439caef2b6e"
CANDIDATE_COMMIT = "0ff8355"
FROZEN_V71_COMMIT = "ed7dea264836b0bfdc4ed608e29ed41a81e6abc7"   # the last commit that changed §V7.1 (Issue #23); the ingestion's base
RUNS = {
    14: {"walk": [("L", 1), ("R", 2), ("A", 3), ("B", 4), ("SELECT", 5), ("START", 6)],
         "expected": [1, 2, 0, 0, 0, 0, 6, 5, 3, 4], "operator": "1 2 · · · ·  6 5 3 4",
         "log": (90652, "e2ba3d82fc23e5ccf6eb214abdf0c979e0807f276456220a1ab5b0a77b5d1d54"),
         "idxcap": (8946060, "d42ebb1adbf7afe358fb0a074a23267b031f581b04c0cd66d405a04fe1541de2"),
         "disp": (400396, "82bc7434acf30df78175d7bebd2dfc67caa4f5fa0d2088f1d423901da2540c7b"),
         "full": (1844492, "30c144d7aa3a6b4c485a783403b1ef6ee1316e523385befdcd806faa181e1b3c"),
         "vi": (152396, "ef0a1261ca1bd83dc8a4f16befc9c1372f0244c64d7565765bfbdf5b36a1927a"),
         "qual_sha": "08cb48f5f7dd406251464ae3e03240deb3ade7af1ba28ae99ffd422cf9d7d0d1",
         "input": dict(selftest=1, steps=183931, invalid=0, no_base=0, key_changes=42, attempts=7892, completed=7892, failed=0,
                       first=1, change=42, refresh=7849, retry=0, last_word="0000", last_rc="ok"),
         "inputt": ([30, 30, 38], 7892, [98, 169, 1046], 183931),
         "counters": 254618, "transfers": 1032712, "bulk": (260900, 1044042496), "irq": 509239,
         "first_handoff_ticks": 6696178, "eligible_ticks": 202507660,
         "idx_crc": ("c4d18caf", "03716e77"), "full_crc": ("33f665a5", "b48b2526"), "disp_crc": ("2c4ff3e4", "bfb0edf1"),
         "vi_crc": ("a118b51d", "2dac3866"), "events": 2392, "dispsrc": (15, 18), "deferred_join": (12, 14),
         "p99_max": (0.003210, 0.475383), "vi_counts": (2372, 4), "superseded": [334, 888, 889, 1734], "latch_2": [],
         "all_hist": {0: 15, 1: 2354, 2: 12, 3: 9, 4: 1}, "pump_skipped": 70687},
    15: {"walk": [("L", 1), ("R", 2), ("UP", 3), ("DOWN", 4), ("LEFT", 5), ("RIGHT", 6)],
         "expected": [1, 2, 3, 4, 5, 6, 0, 0, 0, 0], "operator": "1 2 3 4 5 6  · · · ·",
         "log": (90734, "1cab151b675a3b64694d6b6bfe80f41431dfad39241bfa246581d8e71c94034e"),
         "idxcap": (8946060, "be1785ceb91cc55289484e97bc6191b6518721ab2d190377777812e9515a94a8"),
         "disp": (400436, "7577a72b6cb2d2d4ac9673209f85b5f9cd40f84c5bb42d3b8c56e05a8a34133b"),
         "full": (1844492, "0c3e5612922b06325486dbaade3842f65dac6917b522483c5595159f14854b7b"),
         "vi": (152396, "fb6d12a7b99a98ffce7dc1050d9710b78cc9ddd5964fde737d0839c1450ef79f"),
         "qual_sha": "9554e6724334ac4d7d8b1970f6d9b49793931385790bbb5bdd462beda012ef22",
         "input": dict(selftest=1, steps=183942, invalid=0, no_base=0, key_changes=42, attempts=7895, completed=7895, failed=0,
                       first=1, change=42, refresh=7852, retry=0, last_word="0000", last_rc="ok"),
         "inputt": ([30, 30, 38], 7895, [98, 169, 1045], 183942),
         "counters": 254621, "transfers": 1032723, "bulk": (260899, 1044038400), "irq": 509245,
         "first_handoff_ticks": 6696209, "eligible_ticks": 202507561,
         "idx_crc": ("5b3b8523", "ec26bd10"), "full_crc": ("33f665a5", "166c946e"), "disp_crc": ("1d30dc23", "db31ca0a"),
         "vi_crc": ("9d714e79", "2fdfbc29"), "events": 2393, "dispsrc": (16, 21), "deferred_join": (13, 17),
         "p99_max": (0.003185, 0.475753), "vi_counts": (2373, 3), "superseded": [334, 888, 1172], "latch_2": [1169],
         "all_hist": {0: 15, 1: 2356, 2: 11, 3: 9, 4: 1}, "pump_skipped": 70679},
}
# the six glyphs transcribed from the frames (an unknown bitmap is a failure, never a guess)
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
    return os.path.join(FX, P + "stream-0014-run%d-%s.bin" % (run, kind))


def struct(run):
    k = ("s", run)
    if k not in _C:
        with open(path(run, "struct"), encoding="utf-8") as f:
            _C[k] = json.load(f)
    return _C[k]


def disp(run):
    k = ("d", run)
    if k not in _C:
        _C[k] = vdisp.load(path(run, "disp"))
    return _C[k]


def vi(run):
    k = ("v", run)
    if k not in _C:
        _C[k] = vvi.load(path(run, "vi"))
    return _C[k]


def full(run):
    k = ("f", run)
    if k not in _C:
        _C[k] = vfull.load(path(run, "full"))
    return _C[k]


def run13():
    if "r13" not in _C:
        with open(os.path.join(FX, P + "idxcap-run13-struct.json"), encoding="utf-8") as f:
            _C["r13"] = json.load(f)
    return _C["r13"]


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


def descriptor_from_source():
    """The ten bit positions of GBP_KEYPAD_DESCRIPTOR, read from its ONE place (never restated here)."""
    code = re.sub(r"/\*.*?\*/", "", read(INPUT_C), flags=re.S)
    m = re.search(r"GBP_KEYPAD_DESCRIPTOR\s*=\s*\{\s*\{([^}]*)\}\s*,\s*(\d+)\s*\}", code)
    assert m, "the descriptor initializer"
    return [int(x) for x in m.group(1).split(",")], int(m.group(2))


def lum(w):
    return ((w >> 10) & 31) + ((w >> 5) & 31) + (w & 31)


def cell(words, col, row, bg):
    return tuple("".join("#" if abs(lum(words[(row * 8 + dy) * 240 + col * 8 + dx]) - bg) > 20 else "." for dx in range(8)) for dy in range(8))


def read_tally(words):
    """The checker's `%2d` field at console column 22, rows 4..13, by EXACT glyph match; blank = no tally printed."""
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


def v72():
    t = read(HW)
    i = t.index("### V7.2 ")
    j = t.find("### V7.3 ", i)          # Issue #28 appended the RUN 17 / RUN 18 pre-registration after §V7.2
    return t[i:] if j < 0 else t[i:j]


class TheFixturesAreThePhysicalFiles(unittest.TestCase):
    def test_the_sidecar_fixtures_are_the_archived_bytes(self):
        for run, R in RUNS.items():
            for kind in ("disp", "full", "vi"):
                with self.subTest(run=run, kind=kind):
                    self.assertEqual((os.path.getsize(path(run, kind)), sha(path(run, kind))), R[kind])
            for i in (disp(run), vi(run), full(run)):
                self.assertEqual((i["test_id"], i["build_id"], i["commit"]), ("GBP-VIDEO-004", "stream-0014", CANDIDATE_COMMIT))

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
                    self.assertIn("-run%d" % run, s["raw"][k]["archived_as"])
                    self.assertNotIn("run%d" % run, s["raw"][k]["supplied_name"], "the console names carry no run number")
                self.assertIn("logs/" if run == 14 else "logs/run15/", s["raw"]["log"]["found_at"])
                for k in ("disp", "full", "vi", "qual"):
                    self.assertEqual(sha(os.path.join(ROOT, s["fixtures"][k]["path"])), s["fixtures"][k]["sha256"], k)
                self.assertEqual((s["dol"]["size"], s["dol"]["sha256"], s["dol"]["swiss_sha256"], s["dol"]["build"], s["dol"]["commit"]),
                                 (513152, DOL_SHA, DOL_SHA, "stream-0014", CANDIDATE_COMMIT))
                self.assertTrue(s["dol"]["commit_full"].startswith(CANDIDATE_COMMIT))
                self.assertEqual(s["dol"]["stream_0013_preserved"]["sha256"], OLD_SHA)
                self.assertEqual((s["stimulus"]["commit"], s["stimulus"]["prebuilt_rom"]["sha256"], s["stimulus"]["prebuilt_rom"]["size"]),
                                 (CHECKER_COMMIT, CHECKER_SHA, 69348))
                self.assertFalse(s["stimulus"]["flashed_image_hashed_by_executor"])
                self.assertEqual(s["tools"]["ingestion_head"], FROZEN_V71_COMMIT)
                self.assertEqual(s["github_issues"], {"pre_registration": 20, "amendment_before_hardware": 23, "hardware": 21,
                                                      "operator_inputs_outside_v7": 22, "ingestion": 24, "topology_declaration": 25})
                self.assertIn("cp --update=none", s["raw_receipt"]["archived"])
                self.assertIn("NOT versioned", s["fixtures"]["raw_log"])

    def test_the_archives_if_present_on_this_host_are_the_recorded_bytes(self):
        seen = 0
        for run, R in RUNS.items():
            for k in ("log", "idxcap", "disp", "full", "vi"):
                p = os.path.join(ROOT, struct(run)["raw"][k]["archived_as"])
                if os.path.exists(p):
                    seen += 1
                    self.assertEqual((os.path.getsize(p), sha(p)), R[k], p)
        if not seen:
            self.skipTest("no local archive on this host (captures/local is ignored)")


class TheInputMachineGate(unittest.TestCase):
    """The only machine facts of GBP-INPUT-001 (§V7.1.8): the runtime polled, encoded and wrote.
    Re-parsed from the verbatim summary records the struct quotes from the (unversioned) log."""

    def test_the_input_record_reparsed_meets_the_gate(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                s = struct(run)
                line = s["log_records_verbatim"]["INPUT"]
                self.assertRegex(line, r"^000666 INPUT ")
                f = kv(line)
                got = {k: (f[k] if k in ("last_word", "last_rc") else int(f[k])) for k in R["input"]}
                self.assertEqual(got, R["input"])
                self.assertEqual({k: s["input_machine_gate"]["INPUT"][k] for k in R["input"]}, R["input"], "the struct's fields are the parsed ones")
                g = s["input_machine_gate"]["gate"]
                self.assertTrue(g["MET"])
                self.assertTrue(all(v for k, v in g.items() if isinstance(v, bool)), g)
                self.assertEqual(got["attempts"], got["first"] + got["change"] + got["refresh"] + got["retry"])
                self.assertEqual(got["completed"], got["attempts"])
                self.assertEqual((got["failed"], got["retry"], got["invalid"], got["no_base"]), (0, 0, 0, 0))
                presses = sum(n for _, n in R["walk"])
                self.assertEqual((presses, got["key_changes"]), (21, 2 * presses), "consistent with the walk; not a record of which buttons")
                bits, pressed = descriptor_from_source()
                self.assertEqual((len(bits), pressed, g["descriptor_as_data"], g["pressed_is_one"]), (10, 1, bits, pressed))
                self.assertIn("not a record of WHICH buttons", g["key_changes_vs_walk"]["note"])

    def test_the_inputt_record_is_observational_and_its_counts_close(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                line = struct(run)["log_records_verbatim"]["INPUTT"]
                m = re.match(r"^000667 INPUTT write_ticks=(\d+)/(\d+)/(\d+) n=(\d+) step_ticks=(\d+)/(\d+)/(\d+) n=(\d+) units=min/mean/max$", line)
                self.assertIsNotNone(m, line)
                w, wn, st, sn = [int(m.group(i)) for i in (1, 2, 3)], int(m.group(4)), [int(m.group(i)) for i in (5, 6, 7)], int(m.group(8))
                self.assertEqual((w, wn, st, sn), R["inputt"])
                self.assertEqual((wn, sn), (R["input"]["attempts"], R["input"]["steps"]))
                t = struct(run)["input_machine_gate"]["INPUTT"]
                self.assertEqual((t["write_ticks_min_mean_max"], t["step_ticks_min_mean_max"]), (w, st))
                self.assertIn("never a latency claim", t["note"])

    def test_the_envinput_clip_is_rederived_from_the_source_format(self):
        """truncated=1: LOG_LINE_LEN 256 - 7 prefix - NUL = 248 payload; the ENVINPUT format of the main.c that RAN
        (stream-0014, 0ff8355) renders longer. Issue #27 repaired it in stream-0015 (ENVINPUT + ENVINPUT2), so the
        derivation reads the candidate's source from git, never the working tree."""
        src = git("show", "%s:poc/gbp-video-stream-probe/source/main.c" % CANDIDATE_COMMIT)
        if src is None:
            self.skipTest("the candidate commit is not available in this checkout")
        m = re.search(r'ringlog_printf\(&rl, "(ENVINPUT [^"]*)"', src)
        self.assertIsNotNone(m, "the ENVINPUT format string")
        fmt = m.group(1).replace("%llu", "%d").replace("%u", "%d")
        self.assertIn("#define LOG_LINE_LEN 256", src)
        for run, R in RUNS.items():
            with self.subTest(run=run):
                s = struct(run)
                line = s["log_records_verbatim"]["ENVINPUT"]
                self.assertTrue(line.startswith("000003 ENVINPUT "))
                saved = line[7:]
                self.assertEqual(len(saved), 248)
                f = kv(line)
                desc = [int(x) for x in f["desc"].split(",")]
                rendered = fmt % (int(f["stick_threshold"]), int(f["trigger_threshold"]), int(f["analog_ab_threshold"]), int(f["filter_opposites"]),
                                  int(f["refresh_ms"]), int(f["refresh_ticks"]), int(f["index"]), *desc, int(f["pressed_is_one"]), R["input"]["selftest"])
                self.assertEqual(len(rendered), 266)
                self.assertTrue(rendered.startswith(saved))
                self.assertEqual(rendered[248:], "ot_FACT selftest=1")
                self.assertTrue(saved.endswith("desc_status=CORROBORATED_n"))
                h = s["log_header"]
                self.assertEqual((h["lines"], h["dropped"], h["truncated"], h["end_dropped"]), (686, 0, 1, 0))
                tl = h["truncated_line"]
                self.assertEqual((tl["tag"], tl["seq"], tl["payload_chars_saved"], tl["rendered_payload_chars"], tl["lost_tail"], tl["only_clipped_record"]),
                                 ("ENVINPUT", 3, 248, 266, "ot_FACT selftest=1", True))
                self.assertEqual((h["longest_payload"]["tag"], h["longest_payload"]["chars"]), ("ENVINPUT", 248))
                # every other quoted summary record fits; STARTUPT is the next longest
                lens = {tag: len(l) - 7 for tag, l in s["log_records_verbatim"].items()}
                self.assertEqual(max(v for k, v in lens.items() if k != "ENVINPUT"), 218)
                self.assertEqual(lens["STARTUPT"], 218)
                bits, pressed = descriptor_from_source()
                self.assertEqual((f["refresh_ms"], f["refresh_ticks"], f["desc"], f["pressed_is_one"], f["stick_threshold"]),
                                 ("5", "202500", ",".join(str(b) for b in bits), str(pressed), "48"))

    def test_the_descriptor_is_the_one_place_data_unchanged_since_the_candidate(self):
        code = read(INPUT_C)
        bits, pressed = descriptor_from_source()
        self.assertEqual((bits[:8], bits[8], bits[9], pressed), (list(range(8)), 9, 8, 1))
        old = git("show", "%s:src/gbp/gbp_input.c" % CANDIDATE_COMMIT)
        if old is None:
            self.skipTest("the candidate commit is not available in this checkout")
        # Issue #27 (2026-09-21) implemented GBP-KEY-009 and repaired GBP-KEY-008 in the module and the probe
        # (stream-0015, not executed); the descriptor is kept exactly (U-GBP-010 closed AS-ASSIGNED)
        self.assertEqual(descriptor_from_source(), (bits, pressed))
        old_bits = re.search(r"GBP_KEYPAD_DESCRIPTOR\s*=\s*\{\s*\{([^}]*)\}\s*,\s*(\d+)\s*\}", re.sub(r"/\*.*?\*/", "", old, flags=re.S))
        self.assertEqual(([int(x) for x in old_bits.group(1).split(",")], int(old_bits.group(2))), (bits, pressed))


class TheTallyFramesAreFactAsData(unittest.TestCase):
    """The checker's screen is AGB video; the runs captured video. Re-decoded from the OGBPFULL1 bytes with
    the UNMODIFIED tools/vfull.py parser and consumed_words(), by exact glyph match -- never guessed."""

    def _samples(self, run):
        k = ("t", run)
        if k not in _C:
            out = []
            for rec in full(run)["records"]:
                words = vfull.consumed_words(rec["raw"])
                bg = lum(words[0])
                out.append({"rec": rec, "words": words, "vector": read_tally(words),
                            "title_lit": sum(1 for y in range(8, 16) for x in range(8, 240) if abs(lum(words[y * 240 + x]) - bg) > 20),
                            "distinct": len(set(words)), "bg": words[0], "tex_eq": rec["tex"] == vfull.convert_py(rec["raw"])})
            _C[k] = out
        return _C[k]

    def test_all_sixteen_samples_show_the_checker_screen_and_the_texture_is_the_conversion(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                i = full(run)
                self.assertEqual((i["records_n"], i["k_cap"], i["spacing"], i["origin"], i["completed"], i["refused"], i["blocks_copied"], i["want_calls"]),
                                 (8, 8, 256, 356, 8, 0, 320, 2377))
                self.assertEqual(("%08x" % i["header_crc32"], "%08x" % i["total_crc32"]), R["full_crc"])
                S = self._samples(run)
                self.assertEqual([s["rec"]["frame_index"] for s in S], [356 + 256 * k for k in range(8)])
                self.assertTrue(all(vfull.STATE[s["rec"]["state"]] == "COMPLETE" for s in S))
                self.assertTrue(all(s["tex_eq"] for s in S), "texture == Python conversion in every sample")
                self.assertTrue(all(s["title_lit"] == 522 and s["distinct"] == 3 and s["bg"] == 0xC578 for s in S))
                st = struct(run)["tally_frames"]
                self.assertEqual([s["vector"] for s in S], [x["vector_as_read"] for x in st["samples"]], "the struct's readings are the recomputed ones")
                self.assertTrue(st["texture_equals_convert_py_all"])
                self.assertEqual(st["glyph_table"], {v: list(k) for k, v in GLYPH.items()})

    def test_the_final_state_equals_the_walks_expectation_with_blank_as_never_incremented(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                V = [s["vector"] for s in self._samples(run)]
                final = V[-1]
                self.assertEqual([0 if x == "blank" else int(x) for x in final], R["expected"])
                self.assertEqual((final[0], final[1]), ("1", "2"), "L = 1, R = 2")
                first_final = next(k for k in range(8) if all(v == final for v in V[k:]))
                self.assertEqual(first_final, 3)
                self.assertEqual(V[0], ["1"] + ["blank"] * 9, "s0: L already at 1, nothing else moved")
                # the partials: every counter non-decreasing, and the moved set is a prefix of the walk order
                order = [b for b, _ in R["walk"]]
                prev = [0] * 10
                for v in V:
                    cur = [0 if x == "blank" else int(x) for x in v]
                    self.assertTrue(all(c >= p for c, p in zip(cur, prev)))
                    moved = {LABELS[i] for i in range(10) if cur[i] > 0}
                    self.assertEqual(moved, set(order[:len(moved)]), "the walk in its declared order")
                    self.assertTrue(all(cur[LABELS.index(b)] <= n for b, n in R["walk"]))
                    prev = cur
                self.assertEqual(set(LABELS) - set(order), {LABELS[i] for i in range(10) if final[i] == "blank"}, "unpressed counters are BLANK, never a digit")
                st = struct(run)["tally_frames"]
                self.assertEqual((st["final_state_from_sample"], st["final_equals_expected"], st["final_vector_blank_read_as_never_incremented"]),
                                 (3, True, R["expected"]))
                self.assertIn("BLANK", st["blank_vs_zero"])

    def test_the_sample_times_are_after_control_in_the_frames_time_base(self):
        for run in RUNS:
            with self.subTest(run=run):
                s = struct(run)
                t_control = int(kv(s["log_records_verbatim"]["STARTUPT"])["t_control"], 16)
                for smp, rec in zip(s["tally_frames"]["samples"], full(run)["records"]):
                    self.assertEqual(smp["t_take"], rec["t_take"])
                    self.assertAlmostEqual(smp["s_after_control"], (rec["t_take"] - t_control) / TB, places=5)
                t = [x["s_after_control"] for x in s["tally_frames"]["samples"]]
                self.assertAlmostEqual(t[0], 6.084, places=2)
                self.assertAlmostEqual(t[3], 18.943, places=2)
                self.assertAlmostEqual(t[7], 36.087, places=2)
                self.assertTrue(all(4.28 < b - a < 4.29 for a, b in zip(t, t[1:])), "256 frames at the source cadence")

    def test_the_two_channels_agree_digit_for_digit_and_are_kept_apart(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                s = struct(run)
                op = s["operator_report"]
                self.assertEqual(op["tally_vector_literal"], R["operator"])
                operator = [None if x == "·" else int(x) for x in R["operator"].split()]
                self.assertEqual(op["tally_vector"], operator)
                machine = [None if x == "blank" else int(x) for x in self._samples(run)[-1]["vector"]]
                self.assertEqual(machine, operator, "agreement, stated -- never merged")
                self.assertTrue(op["equals_expected_with_blank_as_no_count"])
                self.assertIn("OPERATOR OBSERVATION", op["source"])
                self.assertIn("never fed into a tool", op["source"])
                self.assertIn("BESIDE the machine channel", op["source"])
                self.assertIn("FACT (data, recomputable)", s["tally_frames"]["classification"])
                self.assertIn("NOT operator observation", s["tally_frames"]["classification"])
                self.assertIn("do not record which GameCube button was pressed", s["tally_frames"]["classification"])
                self.assertIn("not relayed per press", op["live_channel"])
                self.assertIn("unreadable", op["photograph"])


class TheVerdictsAsReadFromTheFrozenGate(unittest.TestCase):
    def test_m_pass_and_o_as_assigned_in_both_runs_within_their_boundary(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                v = struct(run)["verdicts"]
                self.assertEqual((v["question_M"]["verdict"], v["question_O"]["verdict"]), ("PASS", "AS-ASSIGNED"))
                self.assertEqual(v["question_M"]["buttons_observed"], [b for b, _ in R["walk"]])
                self.assertEqual(len(v["question_M"]["buttons_not_observed"]), 4)
                self.assertIn("Nothing about latency", v["question_M"]["means"])
                self.assertIn("CORROBORATED", v["question_O"]["means"])
                self.assertIn("not FACT", v["question_O"]["means"])
                self.assertEqual(v["shared_gates"]["INPUT_MACHINE"], "MET")
                self.assertTrue(v["shared_gates"]["IDENTITY_LOG"].startswith("PASS with one recorded exception"))
                self.assertIn("RECORDED, not judged", v["shared_gates"]["VIDEO_PATH"])
                self.assertIn("declared hardware inventory", v["shared_gates"]["TOPOLOGY"])   # Issue #25: the declaration joined the gate's reading
                self.assertIn("a declaration, not an inference", v["shared_gates"]["TOPOLOGY"])
                self.assertIn("a generic third-party controller", v["shared_gates"]["TOPOLOGY"])
                self.assertTrue(v["no_rerun_preregistered"])
                self.assertIn("NOT RUN", v["run_16"])
        # the union of the two runs observes all ten buttons
        seen = {b for R in RUNS.values() for b, _ in R["walk"]}
        self.assertEqual(seen, set(LABELS))

    def test_the_routing_stays_corroborated_with_its_four_links(self):
        for run in RUNS:
            with self.subTest(run=run):
                rc = struct(run)["verdicts"]["routing_classification"]
                self.assertEqual(rc["status"], "CORROBORATED, not FACT")
                self.assertEqual(len(rc["chain"]), 4)
                self.assertIn("NOT in the machine record", rc["chain"][3])
                self.assertIn("argument, not a record", rc["argument_not_record"])
                self.assertIn("NOT implemented", rc["what_would_make_it_FACT"])
        ev = read(EVIDENCE)
        head = ev[ev.index("### GBP-HW-265 "):].splitlines()[0]
        self.assertIn("CORROBORATED (the routing), not FACT", head)
        self.assertIn("## GBP-KEY-004 — The static result on the L/R order: the Start-up Disc, GBI and Dolphin's model all put L at word bit 8 and R at word bit 9, the reverse of KEYINPUT — CORROBORATED for the encoding the references target; the physical routing NOT established", ev)
        regs = read(os.path.join(ROOT, "docs", "protocol", "REGISTERS.md"))   # Issue #26: C; Issue #33: F (hw, run-scoped) by RUN 17 / RUN 18, history kept
        self.assertNotIn("H (L/R bit order)", regs)
        self.assertIn("C — was H until 2026-09-21", regs)
        self.assertIn("L/R bit order: F (hw, run-scoped) since 2026-09-21", regs)
        self.assertIn("The routing conclusion — the GameCube L reaching the AGB's L line — is a\nchain of four links", v72())

    def test_u_gbp_010_is_closed_on_its_own_condition_with_the_descriptor_kept(self):
        u = read(UNKNOWNS)
        m = re.search(r"^## U-GBP-010\b.*$", u, re.M)
        self.assertIn("CLOSED 2026-09-21", m.group(0))
        self.assertIn("AS-ASSIGNED", m.group(0))
        self.assertIn("CORROBORATED, not FACT", m.group(0))
        self.assertIn("the descriptor kept", m.group(0))
        block = u[m.start():u.index("## U-GBP-011")]
        self.assertIn('"a game\nthat distinguishes L/R (OPERATOR OBSERVATION)"', block, "the closing condition, quoted")
        self.assertIn("GBP-KEY-009", block)
        for run in RUNS:
            self.assertIn("CLOSED on its own stated condition", struct(run)["verdicts"]["u_gbp_010"])

    def test_the_post_run_topology_declaration_and_the_controller_scope(self):
        """Issue #25: the Operator's declaration, given after the runs, recorded as a declaration and mapped onto
        §V7.1.4; the Game Boy Player NOT SEPARATELY DECLARED (never inferred); the pad named for the first time,
        and the scope it puts on the L / R result stated where the verdicts are read. Nothing else moved."""
        for run in RUNS:
            with self.subTest(run=run):
                s = struct(run)
                tp = s["topology_declared_by_operator"]
                self.assertEqual(tp["declared_after_the_runs"]["issue"], 25)
                self.assertEqual(len(tp["declared_after_the_runs"]["items"]), 5)
                self.assertIn("DECLARED", tp["console"])
                # the Game Boy Player: DECLARED by the Operator's hardware inventory (one console, one GBP), never inferred
                self.assertIn("DECLARED HARDWARE INVENTORY", tp["game_boy_player"])
                self.assertIn("NOT an inference", tp["game_boy_player"])
                self.assertIn("exactly one Game Boy Player", tp["game_boy_player"])
                self.assertIn("first recorded as not", tp["game_boy_player"])
                self.assertIn("declared per run: BBA and Ethernet state, the display chain, the cartridge and its boot screen, the controller",
                              tp["standing_note_for_future_pre_registrations"])
                self.assertIn("GENERIC", tp["controller"])
                self.assertIn("NOT the one used", tp["controller"])
                self.assertIn("BBA conectado sem cabo de rede", tp["bba_present"])
                self.assertIn("UNCHANGED", tp["display_chain_declared"])
                self.assertEqual(tp["deviation_reported"], "none")
                for tok in ("DIGITAL CLICK", "trigger_threshold=0", "first two buttons", "third-party pad", "encouraging", "limit", "verdicts are unchanged"):
                    self.assertIn(tok, tp["controller_scope"], tok)
                self.assertIn("recorded as absent", tp["declaration_history"])
                self.assertIn("OPERATOR DECLARATION", tp["source"])
                # the scope claim is tied to data: the policy the run reported reads no analogue trigger
                self.assertEqual(kv(s["log_records_verbatim"]["ENVINPUT"])["trigger_threshold"], "0")
                self.assertEqual((s["verdicts"]["question_M"]["verdict"], s["verdicts"]["question_O"]["verdict"]), ("PASS", "AS-ASSIGNED"))
        self.assertIn("0 = the analogue triggers are not read", read(os.path.join(ROOT, "src", "gbp", "gbp_input.h")))
        s = plain(v72())
        for tok in ("OPERATOR DECLARATION, given AFTER the runs", "DECLARED HARDWARE INVENTORY", "NOT an inference from the console declaration",
                    "recorded as NOT SEPARATELY DECLARED, and the inventory declaration", "BBA conectado sem cabo de rede",
                    "ONE GENERIC (third-party) GameCube controller", "was NOT the one used", "RECORDED AS ABSENT, not inferred",
                    "The controller, and what it bounds (Issue #25).", "digital click of a third-party pad", "official Nintendo pad was not exercised",
                    "the same Game Boy Player by the Operator's declared hardware inventory (one console, one GBP) -- a declaration, not an inference",
                    "QUESTION M PASS PASS", "QUESTION O AS-ASSIGNED AS-ASSIGNED"):
            self.assertIn(tok, s, tok)
        self.assertNotIn("same GBP", s)
        ev = read(EVIDENCE)
        b261 = plain(ev[ev.index("### GBP-HW-261 "):ev.index("### GBP-HW-262 ")])
        for tok in ("OPERATOR DECLARATION, given after the runs", "declared hardware inventory", "not an inference from the console declaration",
                    "GENERIC, third-party", "was NOT the one used", "Scope the pad puts on the L / R result"):
            self.assertIn(tok, b261, tok)
        b265 = ev[ev.index("### GBP-HW-265 "):ev.index("### GBP-VID-034 ")]
        self.assertIn("**Scope of the pad (Issue #25):**", b265)
        self.assertIn("Question M = PASS and Question O = AS-ASSIGNED in RUN 14 and in RUN 15", b265.splitlines()[0], "the verdict row's heading is unchanged")
        self.assertNotIn("same GBP", b261)
        h = plain(read(HANDOFF))
        self.assertIn("The console and the Game Boy Player are the same two units in every run of this project", h)
        self.assertIn("What still varies and MUST be declared per run: BBA and Ethernet state, the display chain, the cartridge and its boot screen, and the controller", h)

    def test_the_blank_and_the_clip_are_recorded_not_smoothed_over(self):
        t = v72()
        self.assertIn("**The blank.**", t)
        self.assertIn("truncated=1 in BOTH runs", t)
        ev = read(EVIDENCE)
        self.assertIn("BLANK", ev[ev.index("### GBP-HW-265 "):ev.index("### GBP-VID-034 ")])
        self.assertEqual(len(re.findall(r"^## GBP-KEY-008 ", ev, re.M)), 1)
        self.assertEqual(len(re.findall(r"^## GBP-KEY-009 ", ev, re.M)), 1)
        self.assertIn("NOT repaired here", ev[ev.index("## GBP-KEY-008 "):].splitlines()[0])
        self.assertIn("NOT implemented", ev[ev.index("## GBP-KEY-009 "):].splitlines()[0])
        self.assertEqual(re.findall(r"^## GBP-KEY-01\d", ev, re.M), ["## GBP-KEY-010"])   # Issue #27: the record and the repair as software


class TheVideoPathRecordedNotJudged(unittest.TestCase):
    def test_vfull_is_inconclusive_by_construction_on_the_checkers_screen(self):
        for run in RUNS:
            with self.subTest(run=run):
                a = vfull.analyse(full(run), use_c=False)
                self.assertEqual(a["verdict"], "INCONCLUSIVE")
                self.assertEqual(len(a["samples"]), 8)
                self.assertTrue(all(s["verdict"] == "INCONCLUSIVE" and s["why"].startswith("STRIP-L inconsistent") for s in a["samples"]))
                o = struct(run)["official_vfull"]
                self.assertEqual((o["verdict"], o["texture_equals_convert_py"]), ("INCONCLUSIVE", "8/8"))
                self.assertIn("RECORDED, NOT A GATE", o["note"])

    def test_the_source_witness_facts_from_the_struct_and_the_projection(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                o = struct(run)["official_vindex"]
                self.assertEqual((o["verdict"], o["observed"], o["intact"], o["counts"], o["decisive_transitions"], o["fault_seen"]),
                                 ("INCONCLUSIVE_TOO_FEW_INTACT_FRAMES", 2048, 0, {"INVALID_CANONICAL_STRIP": 2048}, 0, None))
                self.assertEqual((o["header_crc32"], o["total_crc32"]), R["idx_crc"])
                self.assertEqual((o["records_n"], o["blocks_staged_placed"], o["frames_discarded"], o["every_record_all_40_blocks"]), (2048, [81921, 81921], 0, True))
                self.assertIn("target_reached", o["flags"])
                u = struct(run)["records_uniform"]
                self.assertEqual((u["n"], u["frame_index_range"], u["deviations"]), (2048, [LO, HI], []))
                self.assertEqual(u["every_record"], {"valid_blocks": 0, "index_ok": 0, "frame_id": None, "status": None,
                                                     "outcome": "INVALID_CANONICAL_STRIP", "invalid_by_reason": {"symbol": 40}})

    def test_vdisp_and_policy_a_recomputed(self):
        D = {v: k for k, v in vdisp.DISPOSITION.items()}
        LF = {name: bit for bit, name in vdisp.LF}
        for run, R in RUNS.items():
            with self.subTest(run=run):
                i = disp(run)
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
                self.assertEqual(vdisp.interior_vs_edge(i), {"open": 0, "interior": [], "edge": []})
                dd = [r for r in J if r["life_flags"] & LF["EVER_DEFERRED"]]
                self.assertEqual((len(dd), sum(r["defer_attempts"] for r in dd)), R["deferred_join"])
                lat = sorted(r["t_decision"] - r["t_convert_done"] for r in J)
                p99, mx = pct(lat, 0.99) * 1000.0 / TB, lat[-1] * 1000.0 / TB
                self.assertAlmostEqual(p99, R["p99_max"][0], places=5)
                self.assertAlmostEqual(mx, R["p99_max"][1], places=5)
                self.assertLessEqual(p99, 1.0)
                self.assertLessEqual(mx, 2.5)
                self.assertLess(len(dd), 0.01 * len(J), "why the p99 lands inside the never-deferred population (arithmetic, not a claim)")
                rt = [life[k]["retrace_decision"] for k in joined]
                d = [b - a for a, b in zip(rt, rt[1:])]
                self.assertEqual({k: d.count(k) for k in set(d)}, {1: 2039, 2: 7})
                self.assertEqual(vdisp.decision_intervals(i)["retrace_delta_hist"], R["all_hist"])
                pa = struct(run)["policy_a"]
                self.assertEqual((pa["joined"], pa["missing"], pa["interior_drops"], pa["reorder"], pa["deferred_join"], pa["display_repeat_intervals"]),
                                 (2047, [HI], 0, 0, list(R["deferred_join"]), 7))
                self.assertEqual(pa["frozen_latency_ms"]["p99"], R["p99_max"][0])
                self.assertEqual(set(pa["gates"].values()), {"PASS"})
                self.assertIn("not gates of GBP-INPUT-001", pa["note"])

    def test_the_corrected_vi_model_and_the_one_two_retrace_latch(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                v = vi(run)
                self.assertEqual((v["records_n"], v["records_cap"], v["handed"], v["latched"], v["superseded"], v["overflow"], v["observe_calls"], v["awaiting_at_end"]),
                                 (2377, 4096, 2377, R["vi_counts"][0], R["vi_counts"][1], 0, R["vi_counts"][0], 2376))
                self.assertEqual(("%08x" % v["header_crc32"], "%08x" % v["total_crc32"]), R["vi_crc"])
                self.assertEqual([r["frame_index"] for r in v["records"] if r["superseded"]], R["superseded"])
                self.assertEqual([r["frame_index"] for r in v["records"] if not r["latched"] and not r["superseded"]], [2402])
                latched = [r for r in v["records"] if r["latched"]]
                rc = [vvi.regs_consistent(r) for r in latched]
                self.assertEqual((sum(1 for t, _, _ in rc if t), sum(1 for _, b, _ in rc if b)), (len(latched), len(latched)))
                self.assertEqual(sorted({r["phys"] for r in latched}), [0x013a9f20, 0x0143ff40])
                two = [r["frame_index"] for r in latched if r["retrace_latch"] - r["retrace_handed"] != 1]
                self.assertEqual(two, R["latch_2"])
                self.assertTrue(all(r["retrace_latch"] - r["retrace_handed"] in (1, 2) for r in latched))
                m = struct(run)["vi_register_model"]
                self.assertEqual([x["frame_index"] for x in m["latched_more_than_one_retrace_after_handed"]], R["latch_2"])
                self.assertIn("NOT APPLICABLE", m["R_k_table"])

    def test_transport_startup_and_the_witness_window_from_the_verbatim_records(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                s = struct(run)
                c = kv(s["log_records_verbatim"]["COUNTERS"])
                self.assertEqual({int(c[k]) for k in ("unmasks", "deliveries", "acks", "rearms")}, {R["counters"]})
                self.assertEqual((c["video"], c["overflow"], c["uncertain"], c["control_ok"]), ("96109/96109", "0", "0", "1"))
                st = kv(s["log_records_verbatim"]["STATS"])
                self.assertEqual((int(st["transfers"]), int(st["timeouts"]), int(st["busy"]), int(st["bulk_transfers"]), int(st["bulk_bytes"])),
                                 (R["transfers"], 0, 0) + R["bulk"])
                w = kv(s["log_records_verbatim"]["WRITES"])
                self.assertEqual((int(w["irq_attempted"]), int(w["irq_completed"])), (R["irq"], R["irq"]))
                ve = kv(s["log_records_verbatim"]["VSTATE end"])
                self.assertEqual((ve["stop"], ve["errors"], ve["transport_ok"], ve["restore"]), ("witness_target_reached", "0", "1", "ok"))
                sv = kv(s["log_records_verbatim"]["STARTUPV"])
                self.assertEqual(int(sv["ticks_control_to_first_handoff"]), R["first_handoff_ticks"])
                self.assertLess(R["first_handoff_ticks"] * 1000.0 / TB, 400.0)
                self.assertAlmostEqual(s["startup"]["ms_control_to_first_handoff"], R["first_handoff_ticks"] * 1000.0 / TB, places=5)
                we = kv(s["log_records_verbatim"]["WITELIG"])
                self.assertEqual((int(we["ticks_control_to_eligible"]), we["released"], we["still_gated"]), (R["eligible_ticks"], "1", "0"))
                wq = kv(s["log_records_verbatim"]["WITQUAL"])
                self.assertEqual((wq["required"], wq["warmup_frames"], wq["qualify_frame"], wq["first_record_frame"], wq["resets"]), ("64", "356", "355", "356", "0"))
                self.assertEqual(kv(s["log_records_verbatim"]["WITELIG2"])["qual_streak_at_eligible"], "0")
                self.assertEqual(kv(s["log_records_verbatim"]["STREAMWIT"])["records"], "2048/2048")
                self.assertEqual(int(kv(s["log_records_verbatim"]["STREAMPUMP"])["skipped_cause_pending"]), R["pump_skipped"])
                self.assertEqual(kv(s["log_records_verbatim"]["STREAMINV"])["failures"], "0")

    def test_the_comparison_uses_run_13s_own_record_and_claims_no_mechanism(self):
        for run, R in RUNS.items():
            with self.subTest(run=run):
                c = struct(run)["comparison_vs_run13"]
                r13 = run13()
                self.assertEqual(c["build"], ["stream-0013", "stream-0014"])
                self.assertEqual(c["dol_sha256"], [OLD_SHA, DOL_SHA])
                self.assertEqual(c["source_verdict"], ["OBSERVED_CONTIGUOUS", "INCONCLUSIVE_TOO_FEW_INTACT_FRAMES"])
                self.assertEqual(c["first_handoff_ticks"], [r13["startup"]["ticks_control_to_first_handoff"], R["first_handoff_ticks"]])
                self.assertEqual(c["frozen_p99_max_ms"][0], [r13["policy_a"]["frozen_latency_ms"]["p99"], r13["policy_a"]["frozen_latency_ms"]["max"]])
                self.assertEqual(c["log_lines_dropped_truncated"], [[658, 0, 0], [686, 0, 1]])
                self.assertEqual(c["streampump_skipped_cause_pending"], [64364, R["pump_skipped"]])
                self.assertIn("not a tolerance", c["note"])
                self.assertIn("arithmetic on the distribution", c["deferrals_and_the_p99"])
        self.assertEqual((run13()["verdicts"]["GBP-VIDEO-007"]["verdict"], run13()["verdicts"]["GBP-VIDEO-008"]["verdict"]), ("PASS", "PASS"), "RUN 13 not re-judged")


class TheDocumentsAndTheFreeze(unittest.TestCase):
    def test_v7_2_follows_v7_1_with_twelve_parts_and_the_chapter_heading_carries_the_result(self):
        t = read(HW)
        self.assertEqual((t.count("### V7.1 "), t.count("### V7.2 "), t.count("\n## V7 ")), (1, 1, 1))
        self.assertLess(t.index("### V7.1 "), t.index("### V7.2 "))
        s = v72()
        pos = [s.index("#### V7.2.%d " % n) for n in range(1, 13)]
        self.assertEqual(pos, sorted(pos))
        self.assertNotIn("#### V7.2.13 ", s)
        head = s.splitlines()[0]
        for tok in ("RESULT, ingested 2026-09-21 (GitHub Issue #24)", "Question M = PASS", "Question O = AS-ASSIGNED", "U-GBP-010 CLOSED",
                    "CORROBORATED, not FACT"):
            self.assertIn(tok, head, tok)
        v7 = [l for l in t.splitlines() if l.startswith("## V7 ")][0]
        for tok in ("EXECUTED 2026-09-21 (Hardware Issue #21)", "INGESTED (Issue #24, §V7.2)", "QUESTION M = PASS", "QUESTION O = AS-ASSIGNED",
                    "RUN 16 NOT RUN", "NOT RUN / NOT AUTHORISED HERE at that checkpoint"):
            self.assertIn(tok, v7, tok)
        f = plain(s)
        for tok in ("1 2 · · · ·  6 5 3 4".replace("  ", " "), "1 2 3 4 5 6  · · · ·".replace("  ", " "), "key_changes = 42 = 2 × 21",
                    "The blank.", "one log line", "FACT as data", "recorded, not judged", "RUN 16 was not run",
                    "acceptance criterion", "byte-identical to ed7dea2"):
            self.assertIn(tok, f, tok)
        for n in ("captures/local/GBP-VIDEO-004_stream-0014-run14.log", "captures/local/GBP-VIDEO-004_stream-0014-run15-full.bin"):
            self.assertEqual(t.count(n), 1, "the reserved names appear once, in §V7.1.5")

    def test_v7_1_is_byte_identical_to_the_last_commit_that_changed_it(self):
        old = git("show", "%s:docs/research/HARDWARE_TESTS.md" % FROZEN_V71_COMMIT)
        if old is None:
            self.skipTest("the base commit is not available in this checkout")
        new = read(HW)
        old_slice = old[old.index("### V7.1 "):]
        new_slice = new[new.index("### V7.1 "):new.index("### V7.2 ")]
        self.assertEqual(new_slice.rstrip("\n"), old_slice.rstrip("\n"))
        self.assertEqual(old[:old.index("\n## V7 ")], new[:new.index("\n## V7 ")], "nothing before the V7 chapter moved")

    def test_the_evidence_rows_exist_once_and_carry_the_identities(self):
        ev = read(EVIDENCE)
        for n in range(261, 266):
            self.assertEqual(len(re.findall(r"^### GBP-HW-%d " % n, ev, re.M)), 1, n)
        self.assertEqual(max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 271)   # GBP-HW-266…271: RUN 16 / 17 / 18 (Issue #33)
        b261 = ev[ev.index("### GBP-HW-261 "):ev.index("### GBP-HW-262 ")]
        for run, R in RUNS.items():
            for k in ("log", "idxcap", "disp", "full", "vi"):
                self.assertIn("`%s…" % R[k][1][:8], b261, (run, k))
        self.assertIn("OPERATOR OBSERVATION (literal, relayed by the Orchestrator)", ev[ev.index("### GBP-HW-263 "):].splitlines()[0])
        self.assertIn("FACT (data, recomputable)", ev[ev.index("### GBP-HW-264 "):].splitlines()[0])
        self.assertIn("7 892 / 7 895", ev[ev.index("### GBP-HW-262 "):].splitlines()[0])
        self.assertIn("Declaration history, kept", b261)   # Issue #25 replaced the 'recorded as absent' note and kept its history
        for run in RUNS:
            self.assertEqual(struct(run)["evidence_ids"], ["GBP-HW-261", "GBP-HW-262", "GBP-HW-263", "GBP-HW-264", "GBP-HW-265", "GBP-KEY-008", "GBP-KEY-009"])

    def test_roadmap_handoff_devlog_and_readme_carry_the_executed_state(self):
        r = plain(read(ROADMAP))
        for tok in ("PHYSICALLY EXECUTED 2026-09-21 — RUN 14 and RUN 15, GBP-INPUT-001", "Question M = PASS · Question O = AS-ASSIGNED in both runs",
                    "U-GBP-010 CLOSED; the routing CORROBORATED, not FACT", "NOT yet assessed"):
            self.assertIn(tok, r, tok)
        self.assertIn("A real game can be controlled reliably using the GameCube controller.", read(ROADMAP))
        h = read(HANDOFF)
        # Issue #33 (2026-09-21) rewrote the Phase-5 title and the do-not-assume bullets when RUN 17 / RUN 18 made the routing FACT
        for tok in ("**Phase 5 — Input, implemented and physically executed (GBP-INPUT-001, GBP-INPUT-002: the routing FACT)**", "| **GBP-INPUT-001** (the first physical KEYPAD write; L/R order) |",
                    "issue 24", "That RUN 14 / RUN 15 made the L/R routing a FACT, or that RUN 16 answered", "That the KEYPAD L/R routing is a physical FACT beyond the runs' scope",
                    "That the input path is a finished feature because RUN 14 / RUN 15", "The physical keypad record held these two runs and nothing else until Issue #33"):
            self.assertIn(tok, h, tok)
        d = read(DEVLOG)
        e = d[d.rindex("## 2026-09-21 — Issue #24"):]
        for tok in ("GBP-HW-261", "GBP-KEY-008", "GBP-KEY-009", "Question M = PASS", "AS-ASSIGNED", "U-GBP-010 CLOSED", "no hardware, no code", "NOT implemented"):
            self.assertIn(tok, e, tok)
        rd = read(README)
        for run in RUNS:
            for name in ("stream-0014-run%d-disp.bin", "stream-0014-run%d-full.bin", "stream-0014-run%d-vi.bin", "idxcap-run%d-qual.bin"):
                self.assertIn("`" + P + name % run + "`", rd, name)

    def test_run_16_stays_reserved_and_absent(self):
        for s in (".log", "-idxcap.bin", "-disp.bin", "-full.bin", "-vi.bin"):
            n = "captures/local/GBP-VIDEO-004_stream-0014-run16" + s
            self.assertFalse(os.path.exists(os.path.join(ROOT, n)), n)
            self.assertEqual(read(HW).count(n), 1, n)
            self.assertEqual(read(HANDOFF).count(n), 1, n)

    def test_nothing_under_the_untouchable_paths_changed_against_the_base(self):
        r = subprocess.run(["git", "-C", ROOT, "cat-file", "-e", FROZEN_V71_COMMIT], capture_output=True)
        if r.returncode != 0:
            self.skipTest("the base commit is not available in this checkout")
        # docs/protocol and docs/hardware left this guard with the Issue #26 promotion; Issue #27 touched the input
        # module and the stream probe (the per-change record, the ENVINPUT repair) and nothing else under these paths
        r = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", FROZEN_V71_COMMIT, "--", "src", "poc", "tools", "Makefile", "stimulus"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        allowed = {"src/gbp/gbp_input.c", "src/gbp/gbp_input.h", "poc/gbp-video-stream-probe/source/main.c", "poc/gbp-video-stream-probe/Makefile"}
        self.assertTrue(set(r.stdout.split()) <= allowed, "changed against the base: " + r.stdout)
        r = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", FROZEN_V71_COMMIT, "--", "captures/fixtures"], capture_output=True, text=True)
        for line in r.stdout.split():
            self.assertRegex(line, r"-run1[45678]-", "only the RUN 14 / RUN 15 (Issue #24) and RUN 16 / 17 / 18 (Issue #33) fixtures were added: " + line)


if __name__ == "__main__":
    unittest.main()
