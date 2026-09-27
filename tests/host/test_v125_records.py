"""tests/host/test_v125_records.py -- GitHub Issue #125: the records of the reference reading, against what the records
said before it and against the tool that recomputes their figures.

What is held here, in forms a later Issue's legitimate amendment does not break (#125's review found two that did):
  * ON TOP, NEVER REWRITTEN: every block of d2f109b (origin/main when #125 opened) in EVIDENCE, UNKNOWNS,
    RESEARCH_METHOD, HARDWARE_TESTS and the DEVLOG still starts its block now, in order (tests/host/test_v123_records.py's
    walk). GBP-AUD-002..004 follow the base's last id, once each, in order; later ids may follow them.
  * THE RECORDS DEFECT is in EVIDENCE's preamble, before the first entry: the cause (the rename of build/ and
    `rm -rf build.stale.*`, 2026-09-17), the cost, the standing hazard, and the two new shorthands with full hashes.
  * THE AMENDMENTS: #125's paragraph comes once in each of U-GBP-012, 041, 043, 046, 047 and 048, after the base text
    of the entry (later dated paragraphs may follow it); the headings of 046, 047 and 048 carry their pointer; the
    transport caveat travels with the 17.09 ms wherever it is quoted.
  * THE NOTES ON TOP of GBP-HW-348 (the #123 framing, corrected) and GBP-HW-349 (k, the architecture open) come once
    each, after the base text of their entries.
  * THE RULE is in RESEARCH_METHOD; the DEVLOG entry carries the committed manifest's hash.
  * THE MANIFEST and the refs targets are committed and well formed, and the manifest counts what EVIDENCE says; where
    the private outputs exist, every file it lists verifies, every analysis file on disk is listed, and each refs.tsv
    holds exactly its targets' order.
  * THE FIGURES ARE THE TOOL'S: on the private inputs, figures GBP-AUD-002 and GBP-AUD-003 quote from the references'
    tables are formatted from tools/v125ref.py's own output, each looked for in its own entry.
The claim checks below (no absolute drop claim, the transport caveat) read #125's own text only -- its three entries
and its stamped paragraphs -- so a later Issue's note may quote or discuss them freely.
"""
import hashlib
import math
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import test_v123_records as base  # noqa: E402
import v125const  # noqa: E402
import v125ref  # noqa: E402

BASE = "d2f109b"
EV, UN, DEVLOG, METHOD = base.EV, base.UN, base.DEVLOG, base.METHOD
MANIFEST = "docs/research/manifests/issue-125-ghidra125.sha256"
OUTPUTS = os.path.join(ROOT, "build", "analysis", "ghidra125")
NEW_EV = (("GBP-AUD-002", "GBI's audio path past the hand-off"),
          ("GBP-AUD-003", "the Start-up Disc's audio path past the hand-off"),
          ("GBP-AUD-004", "the two references on #125's four questions"))
NEW_UN = ("U-GBP-012", "U-GBP-041", "U-GBP-043", "U-GBP-046", "U-GBP-047", "U-GBP-048")
STAMP = "**2026-09-25 (GitHub Issue #125), on top"
TARGETS = "docs/research/manifests/issue-125-ghidra125.refs-targets.txt"
SCRATCH = ("hf", "sr", "hfproj", "srproj", "MANIFEST.sha256")      # the throw-away imports and the local copy


def entry(text, eid, head_re=base.EV_HEAD):
    e, _ids = base.entries(text, head_re)
    return e[eid]


def thin(n, nd=0):
    """8660 -> '8 660'; 31938.1 -> '31 938.1': the records' digit grouping."""
    s = ("%." + str(nd) + "f") % n
    whole, _, frac = s.partition(".")
    sign = "-" if whole.startswith("-") else ""
    whole = whole.lstrip("-")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return sign + " ".join(groups) + ("." + frac if frac else "")


def stamped(body):
    """#125's own paragraph in an entry's body: from its stamp to the next dated paragraph or the end."""
    i = body.index(STAMP)
    j = body.find("\n**2026-", i + 1)
    return body[i:j if j >= 0 else len(body)]


def own_text():
    """#125's own claims: the three GBP-AUD entries (cut before any later Issue's first dated on-top paragraph, the
    way stamped() cuts an UNKNOWNS entry) and its stamped UNKNOWNS paragraphs, flattened."""
    ev = base.now(EV)
    parts = []
    for eid, _ in NEW_EV:
        b = entry(ev, eid)[1]
        j = b.find("\n**2026-10")           # #125 itself is dated 2026-09-25; a later Issue's note starts later
        parts.append(b if j < 0 else b[:j])
    parts += [stamped(entry(base.now(UN), uid, base.UN_HEAD)[1]) for uid in NEW_UN]
    return parts


def with_base(fn):
    saved = base.BASE
    base.BASE = BASE
    try:
        return fn()
    finally:
        base.BASE = saved


class OnTopNeverRewritten(unittest.TestCase):
    def test_every_block_of_the_base_starts_its_block_now(self):
        for path in (EV, UN, METHOD, base.HT, DEVLOG):
            self.assertGreater(with_base(lambda: base.walk_on_top(self, path)), 20, path)

    def test_the_new_entries_follow_the_base_once_each(self):
        now_ids = [m.group(1) for m in re.finditer(base.EV_HEAD, base.now(EV), re.M)]
        at = now_ids.index("GBP-HW-352")
        self.assertEqual(now_ids[at + 1:at + 1 + len(NEW_EV)], [e for e, _ in NEW_EV])
        for eid, lead in NEW_EV:
            self.assertEqual(now_ids.count(eid), 1, eid)
            head = entry(base.now(EV), eid)[0]
            self.assertIn(lead, head, eid)
            self.assertTrue(head.startswith("### "), eid)
            self.assertIn("a LEAD for the hardware" if eid != "GBP-AUD-004" else "a LEAD from two implementations",
                          head, eid)
        self.assertEqual(now_ids.count("GBP-AUD-001"), 1)


class TheRecordsDefect(unittest.TestCase):
    def test_the_preamble_carries_cause_cost_hazard_and_shorthands(self):
        ev = base.now(EV)
        pre = ev[:ev.index("\n## ENV-DOL-001")]
        i = pre.index("**2026-09-25 (GitHub Issue #125), on top: where the static-analysis outputs went")
        self.assertLess(i, pre.rindex("\n---\n"))
        p = base.flat(pre[i:])
        for phrase in ("On 2026-09-17 at 16:02 UTC, working around a stale-dentry build failure, the Executor renamed "
                       "the whole `build/` tree to `build.stale.<pid>` and created an empty `build/`.",
                       "At 16:03 UTC it deleted the renamed tree with `rm -rf build.stale.*`",
                       "found nothing more to remove, but each of them would have repeated the loss.",
                       "The DEVLOG last cites the outputs on 2026-09-16",
                       "But checking any of them now means redoing that analysis, not reading a file.",
                       "**The hazard stands.**", "One wipe of `build/` would repeat the loss.", MANIFEST):
            self.assertIn(phrase, p)
        squeezed = "".join(pre[i:].split())
        for h in ("47598482ef6821ca41fed0b283a747c266c7524c7bd63897a63ccf4bd4cf5f67",
                  "2f59aac9b035efe130510adc951556adb006baed7ec512a83503991c0c41a231",
                  "c887877f375a0b2eac15435dc4cdbc075d0973dc83a69e8f11684647c077e9dd",
                  "4c44dc926e7200776e9c1798f2a04d3d02e8c9136a027890098110fb647b35a6"):
            self.assertIn(h, squeezed)


class TheAmendments(unittest.TestCase):
    def body(self, uid):
        return entry(base.now(UN), uid, base.UN_HEAD)

    def test_each_amendment_follows_its_base_body_once(self):
        then_un = with_base(lambda: base.entries(base.then(UN), base.UN_HEAD)[0])
        for uid in NEW_UN:
            _h, b = self.body(uid)
            old = base.base_body(then_un[uid][1])
            self.assertTrue(b.startswith(old), uid)
            self.assertEqual(b.count(STAMP), 1, uid)
            self.assertGreaterEqual(b.index(STAMP), len(old), uid)       # later dated paragraphs may follow it

    def test_the_headings_point_to_125(self):
        for uid in ("U-GBP-046", "U-GBP-047", "U-GBP-048"):
            self.assertIn("**2026-09-25, Issue #125:", self.body(uid)[0], uid)

    def test_the_contents(self):
        b = base.flat(self.body("U-GBP-046")[1])
        self.assertIn("**This is transport capacity, not an output cushion, and it does not compare with our 125 ms.**",
                      b)
        self.assertIn("**Neither corrects drift by counted DUP/DROP.**", b)
        self.assertIn("3.4 to 12.5 times shallower", b)
        b = base.flat(self.body("U-GBP-047")[1])
        self.assertIn("route-left (SOUNDCNT_L 0x1077) moves **wA** with the tone", b)
        self.assertIn("So both references put A in the AI frame's SECOND halfword.", b)
        self.assertIn("**Under that convention both put A on the LEFT.**", b)
        b = base.flat(self.body("U-GBP-048")[1])
        self.assertIn("route-both's E reads resolution 0", b)
        self.assertIn("A literal scan tests neither", b)
        b = base.flat(self.body("U-GBP-041")[1])
        self.assertIn("Its report proposes it for the opening of the next audio round (Round B)", b)
        self.assertIn("two dominant positions, per batch and stream", b)

    def test_no_absolute_drop_claim_in_125s_own_text(self):
        # the first review: both references DO pad and drop outside steady state; the claim is about drift only
        text = base.flat(" ".join(own_text()))
        for bad in ("No sample is ever inserted or dropped", "Neither reference ever repeats or drops a sample",
                    "Neither repeats or drops a sample", "Neither ever repeats or drops a sample",
                    "a drop on an overrun", "lose samples on an overrun"):
            self.assertNotIn(bad, text, bad)

    def test_the_transport_caveat_travels_with_the_figure_in_125s_own_text(self):
        found = 0
        for text in own_text():
            for m in re.finditer(r"17\.09 ms", text):
                found += 1
                para = text[max(0, text.rfind("\n\n", 0, m.start())):text.find("\n\n", m.end()) % (len(text) + 1)]
                self.assertTrue("transport" in para.lower(), para[:120])
        self.assertGreaterEqual(found, 3)                                  # not vacuous

    def test_the_notes_on_top_of_348_and_349(self):
        then_ev = with_base(lambda: base.entries(base.then(EV), base.EV_HEAD)[0])
        for eid, lead in (("GBP-HW-348", "the references' decode rate depends on the cartridge in one path"),
                          ("GBP-HW-349", "k is the current design's parameter; the architecture question is open.")):
            b = entry(base.now(EV), eid)[1]
            old = base.base_body(then_ev[eid][1])
            self.assertTrue(b.startswith(old), eid)
            self.assertEqual(b.count(STAMP), 1, eid)
            self.assertGreaterEqual(b.index(STAMP), len(old), eid)
            self.assertIn(lead, base.flat(stamped(b)), eid)


class TheRuleAndTheLog(unittest.TestCase):
    def test_the_deferral_rule(self):
        m = base.now(METHOD)
        i = m.index("### A deferral with no named successor is a decision to forget (2026-09-25, GitHub Issue #125)")
        self.assertLess(i, m.index("\n## Hardware test requests"))
        self.assertGreater(i, m.index("### A claim about the record's contents requires reading the record"))
        self.assertIn("**Rule: a deferral names its successor.**", base.flat(m[i:]))

    def test_the_devlog_entry(self):
        d = base.now(DEVLOG)
        i = d.index("## 2026-09-25 — Issue #125:")
        self.assertGreater(i, d.index("## 2026-09-25 — Issue #124:"))
        e = d[i:]
        with open(os.path.join(ROOT, MANIFEST), "rb") as f:
            self.assertIn(hashlib.sha256(f.read()).hexdigest(), e)
        self.assertIn("issuecomment-5842152314", e)


class TheManifest(unittest.TestCase):
    def lines(self):
        with open(os.path.join(ROOT, MANIFEST), encoding="utf-8") as f:
            return [l.rstrip("\n") for l in f if l.strip()]

    def test_it_is_well_formed_and_counts_what_evidence_says(self):
        lines = self.lines()
        paths = []
        for l in lines:
            m = re.match(r"^[0-9a-f]{64}  ((?:main|gbi-unpacked|gbihf-unpacked|gbisr-unpacked)\.dol/"
                         r"(?:decomp/[0-9a-f]{8}_FUN_[0-9a-f]{8}\.c|refs\.tsv))$", l)
            self.assertIsNotNone(m, l)
            paths.append(m.group(1))
        self.assertEqual(paths, sorted(paths))
        ndec = sum(1 for p in paths if "/decomp/" in p)
        self.assertEqual(len(paths) - ndec, 4)
        self.assertIn("It holds %d decompiles and 4 reference lists." % ndec, base.flat(base.now(EV)))
        self.assertIn("%d files, paths relative to build/analysis/ghidra125/" % len(paths), base.flat(base.now(DEVLOG)))

    def test_the_refs_targets_are_committed_one_line_per_program(self):
        with open(os.path.join(ROOT, TARGETS), encoding="utf-8") as f:
            rows = [l.rstrip("\n") for l in f if l.strip() and not l.startswith("#")]
        progs = [r.split("  ", 1)[0] for r in rows]
        self.assertEqual(sorted(progs), ["gbi-unpacked.dol", "gbihf-unpacked.dol", "gbisr-unpacked.dol", "main.dol"])
        for r in rows:
            self.assertRegex(r, r"^[a-z-]+\.dol  refs( [0-9a-f]{8})+$")

    def test_it_verifies_against_the_outputs_where_they_exist(self):
        if not os.path.isdir(OUTPUTS):
            self.skipTest("#125's analysis outputs are not in this checkout (build/ is ignored)")
        listed = {}
        for l in self.lines():
            h, p = l.split("  ", 1)
            listed[p] = h
        for p, h in listed.items():
            with open(os.path.join(OUTPUTS, p), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), h, p)
        on_disk = set()                                             # every analysis file, wherever it sits
        for dirpath, dirs, files in os.walk(OUTPUTS):
            rel = os.path.relpath(dirpath, OUTPUTS)
            if rel.split(os.sep)[0] in SCRATCH:
                dirs[:] = []
                continue
            for f in files:
                p = os.path.normpath(os.path.join(rel, f)).replace(os.sep, "/")
                if p not in SCRATCH and (p.endswith(".c") or p.endswith(".tsv")):
                    on_disk.add(p)
        self.assertEqual(on_disk, set(listed))                      # every analysis file listed, nothing listed missing
        with open(os.path.join(ROOT, TARGETS), encoding="utf-8") as f:
            rows = dict(l.rstrip("\n").split("  refs ", 1) for l in f if l.strip() and not l.startswith("#"))
        for prog, targets in rows.items():
            order = []
            for l in open(os.path.join(OUTPUTS, prog, "refs.tsv"), encoding="utf-8"):
                t = l.split("\t", 1)[0]
                if t and t not in order:
                    order.append(t)
            self.assertEqual(targets.split(), order, prog)


class TheFiguresAreTheTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = [os.path.join(ROOT, "input", "gbi", "apps", e, e + ".dol") for e in v125const.EDITIONS]
        if not (all(os.path.isfile(p) for p in paths) and os.path.isfile(v125const.DISC_DOL)):
            raise unittest.SkipTest("the private reference inputs are not present on this host")
        cls.r = v125ref.analyse()
        ev = base.now(EV)
        cls.disc = base.flat(entry(ev, "GBP-AUD-003")[1])          # each figure looked for in its own entry
        cls.gbi = base.flat(entry(ev, "GBP-AUD-002")[1])

    def test_the_disc(self):
        d = self.r["disc"]
        lo, hi = d["steps"][0], d["steps"][2]
        resp = d["decimator"]["response"]
        db = lambda k: 20 * math.log10(resp[k])
        want = ["**−3 dB at %s Hz**" % thin(d["decimator"]["minus3db_hz"]),
                "**−3 dB at %s Hz**, and" % thin(d["chain"]["minus3db_hz"]),
                "Its phases sum to %s–%s" % (thin(d["resampler"]["row_sum_min"]), thin(d["resampler"]["row_sum_max"])),
                "follows (k / 127)² to within %.1f × 10⁻⁶" % (d["gain"]["square_law_127_max_dev"] * 1e6),
                "linear, %s per bit" % thin(d["lut"]["per_bit"][0]),
                "the resampler's nominal step, %.6f, which is 32 768 / 32 000 = 1.024 truncated to 16.16"
                % d["steps"][1]["ratio"],
                "above it, the step is %.6f, which gives %s outputs/s" % (hi["ratio"], thin(hi["outputs_per_s"], 1)),
                "otherwise it is %.6f, which gives %s/s" % (lo["ratio"], thin(lo["outputs_per_s"], 1)),
                "These are −%.3f %% and +%.3f %% from the 32 028.483 Hz" % (-hi["vs_measured_pct"],
                                                                            lo["vs_measured_pct"]),
                "−%.1f dB at 5 256 Hz, **−3 dB at %s Hz**, −%.1f dB at 12 000 Hz and −%.1f dB at 16 384 Hz"
                % (-db("5256"), thin(d["decimator"]["minus3db_hz"]), -db("12000"), -db("16384")),
                "with %d negative taps" % d["window"]["negative_taps"]]
        self.assertEqual(d["classes_bytes"], [32, 16, 8, -1])
        self.assertTrue(d["edgepos"]["is_first_rising_edge_table"])
        for w in want:
            self.assertIn(w, self.disc)

    def test_gbi(self):
        g = self.r["gbi"]["gbi"]
        peak, at = g["analog_peak"]
        want = ["a peak of **%.3f (+%.1f dB) at %s Hz**" % (peak, 20 * math.log10(peak), thin(at)),
                "**−3 dB at %s Hz**" % thin(g["analog_minus3db_hz"]),
                "**−3 dB at %s Hz**" % thin(g["original_minus3db_hz"]),
                "%.3f at 5 256 Hz" % g["analog_response"]["5256"],
                "%.3f at 12 000 Hz" % g["analog_response"]["12000"],
                "%.3f at 5 256 Hz, %.3f at 12 000 Hz" % (g["original_response"]["5256"],
                                                        g["original_response"]["12000"]),
                "It is still %.3f at 32 768 Hz." % g["analog_response"]["32768"]]
        for w in want:
            self.assertIn(w, self.gbi)
        self.assertEqual(g["original_peak"][1], 0)                  # "falls monotonically from its maximum at DC"
        self.assertIn("falls monotonically from its maximum at DC", self.gbi)
        flags = "".join("%s %d " % (e, self.r["gbi"][e]["filter_flag_initial"]) for e in v125const.EDITIONS)
        self.assertEqual(flags, "gbi 1 gbihf 0 gbisr 1 ")
        raw = entry(base.now(EV), "GBP-AUD-002")[1]
        self.assertIn("GBI Standard  1   converter 3 by default", raw)
        self.assertIn("GBIHF         0   the digital converters by default", raw)
        for e, at in (("gbi", "0x800B0FC0"), ("gbihf", "0x800999A0"), ("gbisr", "0x800AAC20")):
            self.assertEqual(self.r["gbi"][e]["aesnd_mixer_at"], [at], e)    # "found once in each unpacked image"

    def test_the_microcode_and_the_provenance_are_recorded(self):
        ev = base.flat(entry(base.now(EV), "GBP-AUD-004")[1])
        self.assertIn(v125ref.AESND_MIXER_SHA256, ev.replace(" ", ""))
        self.assertIn("It identifies the MICROCODE, not the library version GBI linked", ev)
        pre = base.flat(base.now(EV)[:base.now(EV).index("\n## ENV-DOL-001")])
        self.assertIn("`libogc-rice r2191.2a08d95`", pre)
        self.assertIn("So it is FACT as the STUB's build banner.", pre)


if __name__ == "__main__":
    unittest.main()
